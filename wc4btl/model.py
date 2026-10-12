"""Editable map document: a BtlFile plus per-hex indexes, editing operations, undo/redo, crop and save.

Hexes are addressed by *local* index i = y * width + x.  Records store *file* hex ids, which equal the local
index on maps with their own terrain and are world-grid ids (world width, usually 148) on maps cut from the
world map (master.map_index != 0).  Record order in each section is preserved; new records are appended.
"""
import hashlib
import os
import random
import shutil
import struct

from .btlfile import (BtlFile, CITY, MINE, CAPITAL, AIRRAID, FACTION, EVENT, WEATHER, SCHEME, GENERAL,
                      AIRSUPPORT, DEPLOY, S27, convert)

CITY_HP_ARMY = 39
NO_HEX = 0xFFFF
NO_OWNER = 255

LIST_SECTIONS = {  # section attribute -> (record type or callable, label)
    "factions": (FACTION, "Factions"),
    "events": (EVENT, "Events"),
    "weather": (WEATHER, "Weather"),
    "schemes": (SCHEME, "Schemes"),
    "generals": (GENERAL, "Faction generals"),
    "airsupport": (AIRSUPPORT, "Air support"),
    "deploy_a": (DEPLOY, "Deploy slots A"),
    "deploy_b": (DEPLOY, "Deploy slots B"),
    "s27": (S27, "Unknown 8-byte records"),
}


class DocError(Exception):
    pass


class BtlDoc:
    def __init__(self, path, game, btl=None):
        self.path = path
        self.game = game
        self.btl = btl if btl is not None else BtlFile.load(path)
        self.undo_stack = []
        self.redo_stack = []
        self.dirty = False
        self.backed_up = False
        self._last_tag = None
        self._setup()

    # ------------------------------------------------------------------ geometry
    def _setup(self):
        b = self.btl
        self.W, self.H = b.width, b.height
        self.n = self.W * self.H
        self.world = None
        if not b.own_terrain:
            self.world = self.game.world if self.game else None
            if self.world is None:
                raise DocError("This map uses the world map (map index %d) but world.bin could not be loaded. "
                               "Open the game's assets folder first." % b.master["map_index"])
        self.ww = self.world.width if self.world else self.W
        self.cx = b.master["crop_x"] if self.world else 0
        self.cy = b.master["crop_y"] if self.world else 0
        if len(b.owners) != self.n:
            # maps where the header hex count differs from width*height: keep arrays aligned to the grid
            b.owners = (list(b.owners) + [NO_OWNER] * self.n)[:self.n]
            b.provinces = (list(b.provinces) + [NO_HEX] * self.n)[:self.n]
        self.reindex()

    def file_hex(self, i):
        if self.world is None:
            return i
        return (i // self.W + self.cy) * self.ww + (i % self.W + self.cx)

    def local(self, fh):
        if fh is None or fh < 0 or fh == NO_HEX:
            return None
        if self.world is None:
            return fh if fh < self.n else None
        x, y = fh % self.ww - self.cx, fh // self.ww - self.cy
        if 0 <= x < self.W and 0 <= y < self.H:
            return y * self.W + x
        return None

    def xy(self, i):
        return i % self.W, i // self.W

    def terrain(self, i):
        if self.world is None:
            return self.btl.terrain[i]
        return self.world.terrain[self.file_hex(i)]

    def is_sea(self, i):
        return self.game.is_sea(self.terrain(i)["terrain"]) if self.game else False

    # ------------------------------------------------------------------ indexes
    def reindex(self):
        b = self.btl
        self.city_at, self.troop_at, self.cityhp_at, self.mine_at, self.capital_at = {}, {}, {}, {}, {}
        self.reinf_at, self.airraid_at, self.deploy_at = {}, {}, {}
        for r in b.cities:
            i = self.local(r["hex"])
            if i is not None:
                self.city_at.setdefault(i, r)
        for r in b.troops:
            i = self.local(r["hex"])
            if i is None:
                continue
            (self.cityhp_at if r["army"] == CITY_HP_ARMY else self.troop_at).setdefault(i, r)
        for r in b.mines:
            i = self.local(r["hex"])
            if i is not None:
                self.mine_at.setdefault(i, r)
        for r in b.capitals:
            i = self.local(r["hex"])
            if i is not None:
                self.capital_at.setdefault(i, r)
        for r in b.reinforcements:
            i = self.local(r["hex"])
            if i is not None:
                self.reinf_at.setdefault(i, []).append(r)
        for r in b.airraids:
            i = self.local(r["hex"])
            if i is not None:
                self.airraid_at.setdefault(i, []).append(r)
        for name in ("deploy_a", "deploy_b"):
            for r in getattr(b, name):
                i = self.local(r["hex"])
                if i is not None:
                    self.deploy_at.setdefault(i, []).append((name, r))

    # ------------------------------------------------------------------ factions
    def faction_by_id(self, fid):
        for f in self.btl.factions:
            if f["id"] == fid:
                return f
        return None

    def faction_index(self, fid):
        for k, f in enumerate(self.btl.factions):
            if f["id"] == fid:
                return k
        return None

    def faction_label(self, f):
        if f is None:
            return "(none)"
        name = self.game.country_name(f["country"]) if self.game else "Country %d" % f["country"]
        return "%d: %s" % (f["id"], name)

    def owner(self, i):
        return self.btl.owners[i]

    def owner_faction(self, i):
        o = self.btl.owners[i]
        return self.btl.factions[o] if o < len(self.btl.factions) else None

    def province(self, i):
        return self.btl.provinces[i]

    def province_owner(self, i):
        """Owner index of the city hex this hex belongs to (what colours the hex in game)."""
        p = self.local(self.btl.provinces[i])
        if p is None:
            return NO_OWNER
        return self.btl.owners[p]

    def faction_id_at(self, i):
        o = self.province_owner(i)
        if o == NO_OWNER:
            o = self.btl.owners[i]
        if o < len(self.btl.factions):
            return self.btl.factions[o]["id"]
        return self.btl.factions[0]["id"] if self.btl.factions else 0

    # ------------------------------------------------------------------ undo
    def snapshot(self):
        return self.btl.serialize()

    def begin(self, tag=None):
        """Call before every modification.  Consecutive edits with the same tag (e.g. typing into one field)
        share a single undo step."""
        if tag is not None and tag == self._last_tag:
            self.dirty = True
            return
        self._last_tag = tag
        self.undo_stack.append(self.snapshot())
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.dirty = True

    def _restore(self, data):
        self._last_tag = None
        self.btl = BtlFile.parse(data)
        self._setup()

    def undo(self):
        if not self.undo_stack:
            return False
        self.redo_stack.append(self.snapshot())
        self._restore(self.undo_stack.pop())
        self.dirty = True
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self.undo_stack.append(self.snapshot())
        self._restore(self.redo_stack.pop())
        self.dirty = True
        return True

    # ------------------------------------------------------------------ hex operations
    def _check_owner(self, i):
        if i not in self.troop_at and i not in self.city_at:
            self.btl.owners[i] = NO_OWNER

    def new_troop(self, i, army=1, level=1, formation=1):
        t = self.btl.troop_type().new(hex=self.file_hex(i), army=army, level=level, formation=formation,
                                      facing=0, hp_bonus=100, move_target=-1, shield=1)
        hp = self.game.default_hp(army, level, formation) if self.game else 100
        t["hp"] = t["hp_max"] = hp
        return t

    def set_troop(self, i, rec):
        """Place rec (or a new default troop when rec is None) on hex i, replacing any troop there."""
        old = self.troop_at.get(i)
        rec = convert(rec, self.btl.troop_type()) if rec is not None else self.new_troop(i)
        rec["hex"] = self.file_hex(i)
        if old is not None:
            self.btl.troops[self.btl.troops.index(old)] = rec
        else:
            self.btl.troops.append(rec)
        self.troop_at[i] = rec
        if self.btl.owners[i] == NO_OWNER:
            po = self.province_owner(i)
            self.btl.owners[i] = po if po != NO_OWNER else (0 if self.btl.factions else NO_OWNER)
        return rec

    def delete_troop(self, i):
        t = self.troop_at.pop(i, None)
        if t is not None:
            self.btl.troops.remove(t)
            self._check_owner(i)

    def move_troop(self, src, dst):
        t = self.troop_at.get(src)
        if t is None or src == dst or dst in self.troop_at:
            return False
        owner = self.btl.owners[src]
        del self.troop_at[src]
        t["hex"] = self.file_hex(dst)
        self.troop_at[dst] = t
        if dst not in self.city_at or self.btl.owners[dst] == NO_OWNER:
            self.btl.owners[dst] = owner
        self._check_owner(src)
        return True

    def set_city(self, i, rec=None):
        old = self.city_at.get(i)
        rec = rec.clone() if rec is not None else CITY.new(building=11, look=1)
        rec["hex"] = self.file_hex(i)
        if old is not None:
            self.btl.cities[self.btl.cities.index(old)] = rec
        else:
            self.btl.cities.append(rec)
        self.city_at[i] = rec
        self.btl.provinces[i] = self.file_hex(i)
        if self.btl.owners[i] == NO_OWNER and self.btl.factions:
            self.btl.owners[i] = 0
        return rec

    def delete_city(self, i):
        c = self.city_at.pop(i, None)
        if c is not None:
            self.btl.cities.remove(c)
            self._check_owner(i)

    def add_city_hp(self, i):
        c = self.city_at.get(i)
        hp = self.game.city_hp(c["building"]) if (self.game and c) else 150
        t = self.btl.troop_type().new(hex=self.file_hex(i), army=CITY_HP_ARMY, level=1, formation=1,
                                      hp_bonus=100, hp=hp, hp_max=hp, move_target=-1, shield=1)
        self.btl.troops.append(t)
        self.cityhp_at[i] = t
        return t

    def delete_city_hp(self, i):
        t = self.cityhp_at.pop(i, None)
        if t is not None:
            self.btl.troops.remove(t)

    def add_mine(self, i):
        sea = self.is_sea(i)
        m = MINE.new(hex=self.file_hex(i), owner=self.faction_id_at(i), level=1, hp=70, army=34 if sea else 33)
        self.btl.mines.append(m)
        self.mine_at[i] = m
        return m

    def delete_mine(self, i):
        m = self.mine_at.pop(i, None)
        if m is not None:
            self.btl.mines.remove(m)

    def add_capital(self, i):
        c = CAPITAL.new(hex=self.file_hex(i))
        self.btl.capitals.append(c)
        self.capital_at[i] = c
        return c

    def delete_capital(self, i):
        c = self.capital_at.pop(i, None)
        if c is not None:
            self.btl.capitals.remove(c)

    def add_reinforcement(self, i, rec=None):
        if rec is None:
            rec = self.btl.reinf_type().new(army=1, level=1, formation=1, country=self.faction_id_at(i), round=1)
        else:
            rec = convert(rec.clone(), self.btl.reinf_type())
        rec["hex"] = self.file_hex(i)
        self.btl.reinforcements.append(rec)
        self.reinf_at.setdefault(i, []).append(rec)
        return rec

    def delete_reinforcement(self, i, rec):
        self.btl.reinforcements.remove(rec)
        self.reinf_at.get(i, []).remove(rec)

    def add_airraid(self, i, rec=None):
        rec = rec.clone() if rec is not None else AIRRAID.new(army=21, ammo=1, faction=self.faction_id_at(i), round=1)
        rec["hex"] = self.file_hex(i)
        self.btl.airraids.append(rec)
        self.airraid_at.setdefault(i, []).append(rec)
        return rec

    def delete_airraid(self, i, rec):
        self.btl.airraids.remove(rec)
        self.airraid_at.get(i, []).remove(rec)

    def set_owner(self, i, idx):
        self.btl.owners[i] = idx

    def set_province(self, i, fh):
        self.btl.provinces[i] = fh

    # ------------------------------------------------------------------ faction / list operations
    def add_faction(self, template=None):
        ids = [f["id"] for f in self.btl.factions]
        if template is not None:
            f = template.clone()
        else:
            f = FACTION.new(country=1, money=200, industry=50, energy=10, ai=1, alliance=1, unit_bonus=1.0,
                            tax_bonus=1.0, strategy_group=1, tech_level=1)
            f["r"], f["g"], f["b"], f["a"] = random.randint(60, 250), random.randint(60, 250), random.randint(60, 250), 255
        f["id"] = (max(ids) + 1) if ids else 1
        self.btl.factions.append(f)
        return f

    def delete_faction(self, idx):
        del self.btl.factions[idx]
        own = self.btl.owners
        for i, o in enumerate(own):
            if o == idx:
                own[i] = NO_OWNER
            elif o != NO_OWNER and o > idx:
                own[i] = o - 1

    def move_faction(self, idx, delta):
        j = idx + delta
        fs = self.btl.factions
        if not (0 <= j < len(fs)):
            return idx
        fs[idx], fs[j] = fs[j], fs[idx]
        own = self.btl.owners
        for i, o in enumerate(own):
            if o == idx:
                own[i] = j
            elif o == j:
                own[i] = idx
        return j

    def list_new(self, section):
        rt = LIST_SECTIONS[section][0]
        if section == "factions":
            return self.add_faction()
        defaults = {"weather": dict(type=1, round=1, duration=1), "events": dict(round=1),
                    "deploy_a": dict(hex=NO_HEX), "deploy_b": dict(hex=NO_HEX),
                    "generals": dict(flag=1), "airsupport": dict(army=21, ammo=1, round=1)}
        rec = rt.new(**defaults.get(section, {}))
        if section in ("generals", "airsupport") and self.btl.factions:
            rec["faction"] = self.btl.factions[0]["id"]
        if section == "events":
            ids = [e["event_id"] for e in self.btl.events]
            rec["event_id"] = (max(ids) + 1) if ids else 1
        getattr(self.btl, section).append(rec)
        return rec

    # ------------------------------------------------------------------ crop
    def crop(self, x0, y0, x1, y1):
        """Return a new standalone BtlFile (own terrain) containing the hex rectangle [x0..x1] x [y0..y1]."""
        x0, x1 = sorted((max(0, x0), min(self.W - 1, x1)))
        y0, y1 = sorted((max(0, y0), min(self.H - 1, y1)))
        w, h = x1 - x0 + 1, y1 - y0 + 1
        src = self.btl
        out = BtlFile()
        out.master = src.master.clone()
        m = out.master
        m["map_index"] = 0
        m["crop_x"] = m["crop_y"] = 0
        m["width"], m["height"] = w, h
        m["n_hexes"] = w * h

        def new_local(fh):
            i = self.local(fh)
            if i is None:
                return None
            x, y = self.xy(i)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return (y - y0) * w + (x - x0)
            return None

        old_cells = [(y0 + k // w) * self.W + (x0 + k % w) for k in range(w * h)]
        out.terrain = [self.terrain(i).clone() for i in old_cells]
        out.provinces = []
        for i in old_cells:
            nl = new_local(src.provinces[i])
            out.provinces.append(NO_HEX if nl is None else nl)
        # factions: those owning a hex in the rectangle or referenced by records inside it
        used_idx = {src.owners[i] for i in old_cells if src.owners[i] != NO_OWNER}
        kept = []

        def keep(rec, rt=None):
            nl = new_local(rec["hex"])
            if nl is None:
                return None
            r = rec.clone() if rt is None else convert(rec.clone(), rt)
            r["hex"] = nl
            return r

        out.cities = [r for r in (keep(c) for c in src.cities) if r]
        out.troops = []
        for t in src.troops:
            r = keep(t)
            if r:
                mt = r["move_target"]
                if mt not in (-1, NO_HEX):
                    nl = new_local(mt & 0xFFFF)
                    r["move_target"] = -1 if nl is None else nl
                out.troops.append(r)
        out.mines = [r for r in (keep(c) for c in src.mines) if r]
        out.reinforcements = [r for r in (keep(c) for c in src.reinforcements) if r]
        out.airraids = [r for r in (keep(c) for c in src.airraids) if r]
        out.capitals = [r for r in (keep(c) for c in src.capitals) if r]
        out.deploy_a = [r for r in (keep(c) for c in src.deploy_a) if r]
        out.deploy_b = [r for r in (keep(c) for c in src.deploy_b) if r]
        out.schemes = []
        for s in src.schemes:
            nl = new_local(s["target"])
            if nl is not None:
                r = s.clone(); r["target"] = nl; out.schemes.append(r)
        ref_ids = {r["owner"] for r in out.mines} | {r["country"] for r in out.reinforcements} | \
                  {r["faction"] for r in out.airraids}
        for k, f in enumerate(src.factions):
            if k in used_idx or f["id"] in ref_ids:
                kept.append(k)
        out.factions = [src.factions[k].clone() for k in kept]
        remap = {old: new for new, old in enumerate(kept)}
        out.owners = [remap.get(src.owners[i], NO_OWNER) if src.owners[i] != NO_OWNER else NO_OWNER for i in old_cells]
        kept_ids = {f["id"] for f in out.factions}
        out.weather = [r.clone() for r in src.weather]
        out.events = [r.clone() for r in src.events
                      if r["trigger_faction"] in kept_ids | {0} and r["affect_faction"] in kept_ids | {0}]
        out.generals = [r.clone() for r in src.generals if r["faction"] in kept_ids]
        out.airsupport = [r.clone() for r in src.airsupport if r["faction"] in kept_ids]
        out.s27 = [r.clone() for r in src.s27]
        out.tail = src.tail
        out.update_counts()
        return out

    # ------------------------------------------------------------------ save
    def save(self, path=None, backup=True, update_checksum=True):
        path = path or self.path
        if backup and os.path.exists(path) and not self.backed_up:
            bak = path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
            self.backed_up = True
        size = self.btl.save(path)
        self.path = path
        self.dirty = False
        msg = ""
        if update_checksum and self.game and self.game.assets:
            msg = update_battle_checksum(self.game.assets, path)
        return size, msg


def update_battle_checksum(assets, btl_path):
    """Refresh the MD5 of stageN.btl / conquestN.btl in assets/ch_battle.bin (the game never checks it in 1.30.0,
    but keeping it in sync avoids surprises).  Returns a status message."""
    ch = os.path.join(assets, "ch_battle.bin")
    name = os.path.basename(btl_path).lower()
    if not os.path.exists(ch) or os.path.normcase(os.path.dirname(os.path.abspath(btl_path))) != \
            os.path.normcase(os.path.join(os.path.abspath(assets), "stage")):
        return ""
    if name.startswith("stage") and name[5:-4].isdigit():
        key = (1, int(name[5:-4]))
    elif name.startswith("conquest") and name[8:-4].isdigit():
        key = (2, int(name[8:-4]))
    else:
        return ""
    data = bytearray(open(ch, "rb").read())
    count = struct.unpack_from("<I", data, 0)[0]
    digest = hashlib.md5(open(btl_path, "rb").read()).digest()
    for k in range(count):
        off = 20 + 24 * k
        if struct.unpack_from("<II", data, off) == key:
            if data[off + 8:off + 24] == digest:
                return "ch_battle.bin already up to date"
            if not os.path.exists(ch + ".bak"):
                shutil.copy2(ch, ch + ".bak")
            data[off + 8:off + 24] = digest
            data[4:20] = hashlib.md5(bytes(data[20:]) + b"easytechbattle").digest()
            open(ch, "wb").write(data)
            return "ch_battle.bin checksum updated"
    return ""
