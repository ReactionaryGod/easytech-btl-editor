"""Game resources read from the unpacked APK: settings tables, stringtables, terrain/map config, atlases.

The work folder may be either the folder that contains `assets/` or the `assets/` folder itself.
Everything is optional: a missing file only disables the feature that needs it (names, icons, terrain...).
"""
import json
import os
import re

from .worldbin import WorldBin

LANGS = ["en", "cn", "tw", "de", "es", "ja", "ko"]

ARMY_TYPES = {1: "Infantry", 2: "Armor", 3: "Artillery", 4: "Navy", 5: "Air force", 6: "Missile", 7: "Nuke",
              8: "Defense", 9: "City", 10: "Satellite", 11: "Mine", 12: "Fortress", 13: "Helicopter"}
ARMY_TYPE_SHORT = {1: "INF", 2: "ARM", 3: "ART", 4: "NAV", 5: "AIR", 6: "MSL", 7: "NUK", 8: "DEF", 9: "CTY",
                   10: "SAT", 11: "MIN", 12: "FRT", 13: "HEL"}

# terrain type (def_terraintype) -> name
TERRAIN_TYPES = {0: "Plain", 1: "Sea", 2: "Desert", 3: "Hills", 4: "Mountain", 5: "High mountain", 6: "Woods",
                 7: "Forest", 8: "Farmland", 9: "River", 10: "Decoration"}


def find_assets(path):
    if not path:
        return None
    for cand in (os.path.join(path, "assets"), path):
        if os.path.isdir(os.path.join(cand, "stage")) or os.path.isdir(os.path.join(cand, "json")):
            return os.path.normpath(cand)
    return None


def load_stringtable(path):
    d = {}
    with open(path, encoding="utf-8-sig", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if not line or line[0] == ";" or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d.setdefault(k.strip(), v)
    return d


class Atlas:
    """<Texture name=...> + <Image name x y w h refx refy> sprite sheet next to a .webp/.png file."""

    IMG_RE = re.compile(r'<Image\s+name="([^"]+)"\s+x="([-\d.]+)"\s+y="([-\d.]+)"\s+w="([-\d.]+)"\s+h="([-\d.]+)"'
                        r'(?:\s+refx="([-\d.]+)")?(?:\s+refy="([-\d.]+)")?')

    def __init__(self, xml_path):
        self.name = os.path.splitext(os.path.basename(xml_path))[0]
        self.rects = {}
        with open(xml_path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
        for m in self.IMG_RE.finditer(text):
            n, x, y, w, h, rx, ry = m.groups()
            self.rects[n] = (float(x), float(y), float(w), float(h), float(rx or 0), float(ry or 0))
        base = os.path.splitext(xml_path)[0]
        self.image_path = None
        for ext in (".webp", ".png"):
            if os.path.exists(base + ext):
                self.image_path = base + ext
                break

    def get(self, name):
        return self.rects.get(name)


class GameData:
    def __init__(self, work_path=None, lang="en"):
        self.assets = find_assets(work_path)
        self.lang = lang
        self.log = []
        self.armies = []            # ArmySettings rows
        self.army_by_id = {}
        self.army_by_code = {}      # code -> rows sorted by Id
        self.generals = []
        self.general_by_id = {}
        self.skills = {}
        self.medals = {}            # GeneralMedalSettings Id -> row
        self.medal_by_type_level = {}
        self.countries = {}         # CountrySettings Id -> row
        self.buildings = {}
        self.air_defence = {}
        self.army_number = {}       # formation count -> ArmyNumberSettings row
        self.army_level = {}        # level -> ArmyLevelSettings row
        self.strings = {}
        self.strings_cn = {}
        self.terrain_tiles = {}     # terrain id -> {tile idx: image name}
        self.terrain_type = {}      # terrain id -> terrain type
        self.maps = {}              # def_map id -> dict
        self.world = None
        self.atlases = {}
        if self.assets:
            self.load()

    # ---------------------------------------------------------------- loading
    def _p(self, *parts):
        return os.path.join(self.assets, *parts)

    def _try(self, label, fn):
        try:
            fn()
            self.log.append(("ok", "Loaded " + label))
        except FileNotFoundError:
            self.log.append(("warn", "Not found: " + label))
        except Exception as e:  # keep going; the editor works with partial data
            self.log.append(("error", "Failed to load %s: %s" % (label, e)))

    def _json(self, name):
        with open(self._p("json", name), encoding="utf-8-sig") as fh:
            return json.load(fh)

    def load(self):
        self._try("ArmySettings.json", self._load_armies)
        self._try("GeneralSettings.json", self._load_generals)
        self._try("SkillSettings.json", lambda: self.skills.update({r["Id"]: r for r in self._json("SkillSettings.json")}))
        self._try("GeneralMedalSettings.json", self._load_medals)
        self._try("CountrySettings.json", lambda: self.countries.update({r["Id"]: r for r in self._json("CountrySettings.json")}))
        self._try("BuildingSettings.json", lambda: self.buildings.update({r["Id"]: r for r in self._json("BuildingSettings.json")}))
        self._try("ArmyNumberSettings.json", lambda: self.army_number.update({r["Id"]: r for r in self._json("ArmyNumberSettings.json")}))
        self._try("ArmyLevelSettings.json", lambda: self.army_level.update({r["Level"]: r for r in self._json("ArmyLevelSettings.json")}))
        self._try("AirDefenceSettings.json", lambda: self.air_defence.update({r["Id"]: r for r in self._json("AirDefenceSettings.json")}))
        self._try("stringtable_%s.ini" % self.lang, self._load_strings)
        self._try("stringtable_cn.ini", lambda: self.strings_cn.update(load_stringtable(self._p("stringtable_cn.ini"))))
        self._try("config/def_mapterrain.xml", self._load_mapterrain)
        self._try("config/def_map.xml", self._load_maps)
        self._try("world map (def_map file)", self._load_world)
        for rel in ("terrain_hd.xml", "plant_hd.xml", "buildings_hd.xml", "tacticalmap.xml",
                    "image/image_general_medal_hd.xml", "image/image_ribbon_hd.xml", "image/image_flags_hd.xml"):
            self._try(rel, lambda rel=rel: self._load_atlas(rel))

    def _load_armies(self):
        self.armies = self._json("ArmySettings.json")
        for r in self.armies:
            self.army_by_id[r["Id"]] = r
            self.army_by_code.setdefault(r["Army"], []).append(r)
        for rows in self.army_by_code.values():
            rows.sort(key=lambda r: r["Id"])

    def _load_generals(self):
        self.generals = [g for g in self._json("GeneralSettings.json") if g.get("Id")]
        self.general_by_id = {g["Id"]: g for g in self.generals}

    def _load_medals(self):
        for r in self._json("GeneralMedalSettings.json"):
            self.medals[r["Id"]] = r
            self.medal_by_type_level[(r["Type"], r["Level"])] = r

    def _load_strings(self):
        p = self._p("stringtable_%s.ini" % self.lang)
        if not os.path.exists(p):
            p = self._p("stringtable_en.ini")
        self.strings = load_stringtable(p)

    def _load_mapterrain(self):
        with open(self._p("config", "def_mapterrain.xml"), "rb") as fh:
            text = fh.read().decode("latin-1")
        for m in re.finditer(r'<terrain\b([^>]*)>(.*?)</terrain>', text, re.S):
            attrs, body = m.groups()
            tid = re.search(r'\bterrain="(\d+)"', attrs)
            ttype = re.search(r'\btype="(\d+)"', attrs)
            if not tid:
                continue
            tid = int(tid.group(1))
            self.terrain_type[tid] = int(ttype.group(1)) if ttype else 0
            tiles = {}
            for t in re.finditer(r'<tile\s+idx="(\d+)"(?:\s+image="([^"]*)")?', body):
                if t.group(2):
                    tiles[int(t.group(1))] = t.group(2)
            self.terrain_tiles[tid] = tiles

    def _load_maps(self):
        with open(self._p("config", "def_map.xml"), encoding="utf-8-sig") as fh:
            text = fh.read()
        for m in re.finditer(r'<map\b([^>]*)/?>', text):
            a = dict(re.findall(r'(\w+)="([^"]*)"', m.group(1)))
            if "id" in a:
                self.maps[int(a["id"])] = a

    def _load_world(self):
        mp = self.maps.get(1)
        name = mp["file"] if mp else "world.bin"
        self.world = WorldBin(self._p(name))

    def _load_atlas(self, rel):
        a = Atlas(self._p(rel))
        if not a.image_path:
            raise FileNotFoundError(rel)
        self.atlases[a.name] = a

    # ---------------------------------------------------------------- lookups
    def text(self, key, default=None):
        v = self.strings.get(key)
        if v is None:
            v = self.strings_cn.get(key)
        return default if v is None else v

    def army_row(self, code, level=1):
        rows = self.army_by_code.get(code)
        if not rows:
            return None
        if rows[0].get("Elite") and 1 <= level <= len(rows):
            return rows[level - 1]
        return rows[0]

    def army_name(self, code, level=1):
        r = self.army_row(code, level)
        if not r:
            return "Army %d" % code
        return self.text("unit_name_%d" % r["Id"], r.get("Name") or "Army %d" % code)

    def army_type(self, code):
        r = self.army_row(code)
        return r["Type"] if r else 0

    def default_hp(self, code, level=1, formation=1):
        """Starting HP estimate: base HP x formation HP% + level bonus (elites use their tier row)."""
        r = self.army_row(code, level)
        if not r:
            return 100
        hp = r["HP"] * self.army_number.get(formation, {}).get("HpPercent", 100) / 100.0
        if not r.get("Elite"):
            hp += self.army_level.get(level, {}).get("AddHP", 0)
        return max(1, int(round(hp)))

    def city_hp(self, building_id):
        b = self.buildings.get(building_id)
        r = self.army_by_id.get(b["ArmyId"]) if b and b.get("ArmyId") else None
        return r["HP"] if r else 150

    def is_elite(self, code):
        r = self.army_row(code)
        return bool(r and r.get("Elite"))

    def army_codes(self):
        return sorted(self.army_by_code)

    def general(self, gid):
        return self.general_by_id.get(gid)

    def general_name(self, gid):
        g = self.general_by_id.get(gid)
        if not g:
            return "General %d" % gid if gid else ""
        return self.text(g.get("EName") or "", None) or g.get("Name") or g.get("EName") or str(gid)

    def country_name(self, cid):
        return self.text("country_%d" % cid, "Country %d" % cid)

    def city_name(self, nid):
        return self.text("battle_cityname_%03d" % nid, None) or self.text("battle_cityname_%d" % nid, "")

    def building_name(self, bid):
        b = self.buildings.get(bid)
        names = {2: "Windmill", 3: "Town", 11: "Small city", 12: "Medium city", 13: "Large city", 14: "Metropolis",
                 15: "Capital 1", 16: "Capital 2", 17: "Capital 3", 18: "Capital 4", 19: "Capital 5",
                 21: "Refinery", 22: "Factory", 23: "Nuclear plant", 31: "Port 1", 32: "Port 2", 33: "Port 3",
                 34: "Port 4"}
        return names.get(bid, b["Name"] if b else "Building %d" % bid)

    def terrain_name(self, tid):
        return TERRAIN_TYPES.get(self.terrain_type.get(tid, -1), "Terrain %d" % tid)

    def is_sea(self, tid):
        return self.terrain_type.get(tid, -1) == 1

    def head_path(self, gid):
        g = self.general_by_id.get(gid)
        if not g or not self.assets:
            return None
        for ext in (".webp", ".png"):
            p = self._p("image", "heads", "general_circle_%s%s" % (g.get("Photo") or g.get("EName"), ext))
            if os.path.exists(p):
                return p
        return None

    def skill_level(self, skill_id):
        """Level stored in troop 'skill N' bytes: last digit of the skill id, 0 meaning level 10."""
        lv = skill_id % 10
        return 10 if lv == 0 and skill_id else lv

    def medal_image(self, value):
        """Troop medal byte -> (atlas name, image name, label).  1-16 single medals, 171-230 levelled medals."""
        if not value:
            return None
        if 1 <= value <= 16:
            mtype, level = value, 1
        elif 171 <= value <= 230:
            mtype, level = (value - 1) // 10, (value - 1) % 10 + 1
        else:
            return None
        label = self.text("general_medal_%d" % mtype, "Medal %d" % mtype)
        if level > 1:
            label += " Lv%d" % level
        return ("image_general_medal_hd", "general_medal_%d.png" % mtype, label)

    def ribbon_image(self, value):
        if not value:
            return None
        rtype, level = value // 10 + 20, value % 10
        row = self.medal_by_type_level.get((rtype, level))
        label = (self.text("general_medal_%d" % rtype, "Ribbon %d" % rtype) or "").replace("%d", str(level))
        if not row:
            return ("image_ribbon_hd", None, label or "Ribbon %d" % value)
        return ("image_ribbon_hd", "ribbon_%d.png" % row["Id"], label)

    def stage_files(self):
        d = self._p("stage") if self.assets else None
        if not d or not os.path.isdir(d):
            return []
        return sorted(f for f in os.listdir(d) if f.lower().endswith(".btl"))
