"""Glory of Generals 3 game data: JSON tables, string tables, terrain definitions and sprite atlases."""
import json
import os
import re

from wc4btl.gamedata import Atlas

ARMY_SHORT = {101: "INF", 102: "ARM", 103: "ART", 104: "TNK", 105: "HAR", 106: "HTK", 201: "SUB", 202: "DD",
              203: "CA", 204: "BB", 205: "CV", 206: "TR"}
# English for BuildingSettings' Chinese names (城市 city, 工厂 factory, 机场 airfield, 港口 port, 油矿区 oil field,
# 煤矿区 coal mine, 附属城区 suburb, 小油井/大油井 small/large oil well)
BUILDING_EN = {101: "City Lv1", 102: "City Lv2", 103: "City Lv3", 104: "Factory", 107: "Airfield", 109: "Port",
               112: "Oil field", 113: "Coal mine", 114: "Suburb", 115: "Small oil well", 116: "Large oil well"}
# English for def_terraintype.xml / def_mapterrain.xml names (translated from the game's Chinese)
TERRAIN_TYPE_EN = {0: "Plain", 1: "Sea", 2: "Snow", 3: "Desert", 4: "Swamp", 5: "Woods", 6: "Forest", 7: "Hills",
                   8: "Low mountains", 9: "High mountains", 10: "River", 11: "Decoration", 12: "Port (embark)",
                   13: "Port (landing)"}
TERRAIN_EN = {1: "Plain", 2: "Ocean", 3: "Snowfield", 4: "Desert", 11: "Swamp (earth)", 12: "Swamp (grass)",
              13: "Swamp (snow)", 14: "Swamp (sand)", 21: "Forest", 22: "Tropical forest", 23: "Boreal forest",
              24: "Palms (snow)", 25: "Cactus", 31: "Hills (earth)", 32: "Low mountains (earth)",
              33: "High mountains (earth)", 34: "Hills (grass)", 35: "Low mountains (grass)",
              36: "High mountains (grass)", 37: "Hills (snow)", 38: "Low mountains (snow)",
              39: "High mountains (snow)", 40: "Hills (desert)", 41: "Low mountains (desert)",
              42: "High mountains (desert)", 44: "High mountains (grass, snowcap)", 46: "River 1", 47: "River 2",
              48: "River 3", 49: "Estuary", 50: "Beach edge", 51: "Farmland", 52: "Dunes", 53: "Decoration (earth)",
              54: "Decoration (grass)", 55: "Decoration (snow)", 56: "Decoration (desert)", 57: "Farmland (snow)"}
GROUND_NAMES = {0: "Earth", 1: "Grass", 2: "Desert", 3: "Snow", 4: "Other"}
LANGS = ("en", "cn", "tw", "ja", "ko")
ATLASES = ("terrain", "mountain", "rivers", "buildings", "battleres", "image/image_flag", "image/image_generalhead",
           "image/image_fortification", "image/image_army_icon")


def is_gog3_assets(assets):
    return bool(assets) and os.path.isdir(os.path.join(assets, "luac")) and \
        os.path.exists(os.path.join(assets, "json", "ExArmySettings.json"))


class Gog3Game:
    KIND = "gog3"

    def __init__(self, work, lang="en"):
        from wc4btl.gamedata import find_assets
        self.work = work
        self.assets = find_assets(work) if work else None
        self.lang = lang if lang in LANGS else "en"
        self.log = []
        self.strings = {}
        self.tables = {}
        self.terrains = {}          # id -> {"name", "type", "plants", "tiles": {idx: image}}
        self.terrain_types = {}     # type -> (name, movement cost, defence)
        self.atlases = {}
        if not self.assets:
            return
        for name in ("Army", "ExArmy", "General", "Country", "Building", "Fortification", "Stage", "UnitedStage",
                     "ChallengeStage", "Reinforcement"):
            path = os.path.join(self.assets, "json", name + "Settings.json")
            try:
                rows = json.load(open(path, encoding="utf-8-sig"))
                if name == "Reinforcement":
                    self.tables[name] = rows
                else:
                    self.tables[name] = {r["Id"]: r for r in rows}
                self.log.append(("ok", "%s: %d rows" % (os.path.basename(path), len(rows))))
            except (OSError, ValueError) as e:
                self.tables[name] = [] if name == "Reinforcement" else {}
                self.log.append(("error", "%s: %s" % (path, e)))
        self._load_strings()
        self._load_terrain()
        for a in ATLASES:
            xml = os.path.join(self.assets, a + ".xml")
            if os.path.exists(xml):
                at = Atlas(xml)
                self.atlases[os.path.basename(a)] = at
                self.log.append(("ok" if at.image_path else "warn", "atlas %s: %d sprites%s" % (
                    a, len(at.rects), "" if at.image_path else " (image missing)")))
            else:
                self.log.append(("warn", "atlas %s not found" % a))
        self._sprite_atlas = {}
        for key in ("terrain", "mountain", "rivers"):
            at = self.atlases.get(key)
            if at:
                for n in at.rects:
                    self._sprite_atlas.setdefault(n, key)

    # ------------------------------------------------------------------ loading
    def _load_strings(self):
        self.strings = {}
        for lang in dict.fromkeys((self.lang, "en", "cn")):
            path = os.path.join(self.assets, "stringtable_%s.ini" % lang)
            if not os.path.exists(path):
                continue
            n = 0
            for line in open(path, encoding="utf-8-sig", errors="replace"):
                m = re.match(r"([A-Za-z0-9_]+)=(.*)", line.rstrip("\r\n"))
                if m and m.group(1) not in self.strings:
                    self.strings[m.group(1)] = m.group(2)
                    n += 1
            self.log.append(("ok", "stringtable_%s.ini: %d strings" % (lang, n)))

    def _load_terrain(self):
        path = os.path.join(self.assets, "config", "def_mapterrain.xml")
        try:
            text = open(path, "rb").read().decode("utf-8-sig", "replace")
        except OSError as e:
            self.log.append(("error", "%s: %s" % (path, e)))
            return
        for m in re.finditer(r'<terrain\s+name="([^"]*)"\s+terrain="(\d+)"\s+type="(\d+)"([^>]*)>(.*?)</terrain>', text, re.S):
            attrs = m.group(4)
            plants = re.search(r'plants="(\d+)"', attrs)
            tiles = {int(i): img for i, img in re.findall(r'<tile\s+idx="(\d+)"(?:\s+image="([^"]*)")?', m.group(5)) if img}
            self.terrains[int(m.group(2))] = {"name": m.group(1), "type": int(m.group(3)),
                                              "plants": int(plants.group(1)) if plants else 0, "tiles": tiles}
        self.log.append(("ok", "def_mapterrain.xml: %d terrains" % len(self.terrains)))
        path = os.path.join(self.assets, "config", "def_terraintype.xml")
        if os.path.exists(path):
            text = open(path, "rb").read().decode("utf-8-sig", "replace")
            for m in re.finditer(r'<terraintype\s+name="([^"]*)"\s+type="(\d+)"\s+movementcost="(-?\d+)"(?:\s+defense="(-?\d+)")?', text):
                self.terrain_types[int(m.group(2))] = (m.group(1), int(m.group(3)), int(m.group(4) or 0))

    # ------------------------------------------------------------------ lookups
    def text(self, key, default=""):
        return self.strings.get(key, default)

    def stage_files(self):
        stage = os.path.join(self.assets, "stage") if self.assets else None
        if not stage or not os.path.isdir(stage):
            return []
        return sorted(fn for fn in os.listdir(stage) if fn.lower().endswith(".btl"))

    def stage_title(self, fn):
        base = fn[:-4]
        num = base[5:] if base.startswith("stage") else ""
        if num.isdigit():
            sid = int(num)
            name = self.text("stage_%d" % sid)
            if not name and sid in self.tables.get("UnitedStage", {}):
                camp = self.tables["UnitedStage"][sid].get("Campaign")
                name = self.text("unitedcampaign_%s" % camp)
                if name:
                    name += " %d" % (sid % 100)
            return name
        m = re.match(r"conquest(\d+)", base)
        if m:
            return self.text("conquest_%s" % m.group(1))
        return ""

    def army(self, aid):
        return self.tables.get("Army", {}).get(aid)

    def army_name(self, aid):
        return self.text("army_%d" % aid) or (self.army(aid) or {}).get("Name") or "army %d" % aid

    def army_short(self, aid):
        return ARMY_SHORT.get(aid, "?")

    def army_hp(self, aid):
        return (self.army(aid) or {}).get("HP", 0)

    def army_mobility(self, aid):
        return (self.army(aid) or {}).get("Mobility", 0)

    def general(self, gid):
        return self.tables.get("General", {}).get(gid)

    def general_name(self, gid):
        return self.text("general_%d" % gid) or (self.general(gid) or {}).get("Name") or "general %d" % gid

    def exarmy_name(self, xid):
        return self.text("exarmy_%d" % xid) or (self.tables.get("ExArmy", {}).get(xid) or {}).get("Name") or "exarmy %d" % xid

    def country_name(self, cid):
        return self.text("country_%d" % cid) or (self.tables.get("Country", {}).get(cid) or {}).get("Name") or "country %d" % cid

    def city_name(self, n):
        return self.text("battle_cityname_%03d" % n) if n else ""

    def building_name(self, bid):
        if self._english() and bid in BUILDING_EN:
            return BUILDING_EN[bid]
        return (self.tables.get("Building", {}).get(bid) or {}).get("Name") or "building %d" % bid

    def fortification_name(self, fid):
        return self.text("fortification_%d" % fid) or "fortification %d" % fid

    def objective_text(self, t):
        return self.text("objective_%d" % t, "objective %d" % t)

    def _english(self):
        return self.lang not in ("cn", "tw")

    def terrain_name(self, tid):
        if self._english() and tid in TERRAIN_EN:
            return TERRAIN_EN[tid]
        return (self.terrains.get(tid) or {}).get("name", "terrain %d" % tid)

    def terrain_type_name(self, t):
        if self._english() and t in TERRAIN_TYPE_EN:
            return TERRAIN_TYPE_EN[t]
        return (self.terrain_types.get(t) or ("type %d" % t,))[0]

    def sprite(self, tid, tile):
        """(atlas key, image name) for an overlay, or None."""
        name = (self.terrains.get(tid) or {}).get("tiles", {}).get(tile)
        if not name:
            return None
        atlas = self._sprite_atlas.get(name)
        return (atlas, name) if atlas else None

    def head_name(self, gid):
        g = self.general(gid)
        return (g.get("Photo") or g.get("Ename")) + ".png" if g else None

    # ------------------------------------------------------------------ choice lists for the UI
    def choices(self, kind):
        t = self.tables
        if kind == "army":
            return [(i, "%d  %s" % (i, self.army_name(i))) for i in sorted(t.get("Army", {}))]
        if kind == "exarmy":
            return [(i, "%d  %s" % (i, self.exarmy_name(i))) for i in sorted(t.get("ExArmy", {}))]
        if kind == "general":
            return [(i, "%d  %s" % (i, self.general_name(i))) for i in sorted(t.get("General", {}))]
        if kind == "country":
            return [(i, "%d  %s" % (i, self.country_name(i))) for i in sorted(t.get("Country", {}))]
        if kind == "building":
            return [(i, "%d  %s" % (i, self.building_name(i))) for i in sorted(t.get("Building", {}))]
        if kind == "fortification":
            return [(i, "%d  %s" % (i, self.fortification_name(i))) for i in range(1, 6)]
        if kind == "objective":
            return [(i, "%d  %s" % (i, self.objective_text(i))) for i in range(13)]
        if kind == "terrain":
            return [(i, "%d  %s" % (i, self.terrain_name(i))) for i in sorted(self.terrains)]
        return []
