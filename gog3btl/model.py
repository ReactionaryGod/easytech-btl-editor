"""Editable Glory of Generals 3 battle document: per-hex indexes, edit operations, undo, save."""
import hashlib
import marshal
import os
import shutil
import struct

from .format import (HEX_LAYER_A, HEX_LAYER_B, HEX_LAYER_C, HEX_DISABLED, HEX_SEA, NO_HEX, FormatError, read, save)

LAYERS = (("A", HEX_LAYER_A), ("B", HEX_LAYER_B), ("C", HEX_LAYER_C))
DEFAULT_COLORS = [(214, 64, 52), (52, 110, 214), (60, 170, 80), (230, 170, 30), (150, 80, 200), (40, 180, 190),
                  (220, 110, 170), (120, 120, 60), (240, 120, 40), (90, 90, 160)]


class DocError(Exception):
    pass


def unpack_overlay(x):
    dx, dy = struct.unpack("<bb", struct.pack("<H", x >> 16))
    return {"terrain": x & 0xFF, "tile": (x >> 8) & 0xFF, "dx": dx, "dy": dy}


def pack_overlay(o):
    return (o["terrain"] & 0xFF) | (o["tile"] & 0xFF) << 8 | \
        struct.unpack("<H", struct.pack("<bb", max(-128, min(127, o["dx"])), max(-128, min(127, o["dy"]))))[0] << 16


class Gog3Doc:
    KIND = "gog3"

    def __init__(self, path, game, battle=None):
        self.path = path
        self.game = game
        if battle is None:
            try:
                battle = read(open(path, "rb").read())
            except (FormatError, struct.error) as e:
                raise DocError("not a Glory of Generals 3 battle map: %s" % e)
        self.b = battle
        self.dirty = False
        self.backed_up = False
        self.undo_stack, self.redo_stack = [], []
        self._last_tag = None
        self._setup()

    # ------------------------------------------------------------------ indexes
    def _setup(self):
        m = self.b.setdefault("map", {})
        size = m.get("size") or {"width": 1, "height": 1, "view_x": 0, "view_y": 0, "view_w": 1, "view_h": 1}
        self.W, self.H = size["width"], size["height"]
        self.n = self.W * self.H
        hexes = m.setdefault("hexes", [0] * self.n)
        if len(hexes) != self.n:
            raise DocError("map has %d hex values for %d x %d" % (len(hexes), self.W, self.H))
        self.overlays = {}               # hex -> {"A"|"B"|"C": packed u32}
        ov = m.get("overlays", [])
        cur = 0
        for i, v in enumerate(hexes):
            for layer, bit in LAYERS:
                if v & bit:
                    if cur >= len(ov):
                        raise DocError("terrain overlay list is shorter than the hex layer bits need")
                    self.overlays.setdefault(i, {})[layer] = ov[cur]
                    cur += 1
        if cur != len(ov):
            raise DocError("%d terrain overlays are not used by any hex" % (len(ov) - cur))
        self.reindex()

    def reindex(self):
        b = self.b
        self.army_at, self.offmap, self.stacked = {}, [], []
        for a in b.get("armies", {}).get("list", []):
            h = a["info"]["hex"]
            if h == NO_HEX or h >= self.n:
                self.offmap.append(a)
            elif h in self.army_at:
                self.stacked.append(a)
            else:
                self.army_at[h] = a
        self.area_at = {a["hex"]: a for a in b.get("areas", {}).get("list", []) if "hex" in a}
        self.key_at = {k["hex"]: k for k in b.get("key_areas", {}).get("list", []) if "hex" in k}
        self.factions = {c["info"]["id"]: c for c in b.get("countries", {}).get("list", []) if "info" in c}
        prov = b.get("areas", {}).get("province_of_hex?")
        self.province = prov if prov and len(prov) == self.n else None
        self.area_owner = {o["hex"]: o.get("faction?") for o in b.get("areas", {}).get("area_owners?", []) if "hex" in o}

    @property
    def troop_at(self):            # name used by the shared map view (drag to move)
        return self.army_at

    def xy(self, i):
        return i % self.W, i // self.W

    def file_hex(self, i):
        return i

    def hexval(self, i):
        return self.b["map"]["hexes"][i]

    def is_sea(self, i):
        return bool(self.hexval(i) & HEX_SEA)

    def is_disabled(self, i):
        return bool(self.hexval(i) & HEX_DISABLED)

    def overlay(self, i, layer):
        x = self.overlays.get(i, {}).get(layer)
        return None if x is None else unpack_overlay(x)

    def terrain_type(self, i):
        """The engine's rule (libiron 0x2d1740): sea, else layer-B terrain's type, else from the ground."""
        v = self.hexval(i)
        if v & HEX_SEA:
            return 1
        ground = v & 7
        o = self.overlay(i, "B")
        if o and o["terrain"]:
            t = self.game.terrains.get(o["terrain"]) if self.game else None
            if t:
                if t["type"] == 11:
                    return 3 if ground == 2 else 2 if ground == 3 else 0
                if t["type"] == 6 and o["tile"] < t["plants"]:
                    return 5
                return t["type"]
        return 3 if ground == 2 else 2 if ground == 3 else 0

    # ------------------------------------------------------------------ factions
    def faction(self, fid):
        return self.factions.get(fid)

    def faction_ids(self):
        return list(self.factions)

    def faction_rgb(self, fid):
        c = self.factions.get(fid)
        if c is None:
            return (150, 150, 150)
        i = c["info"]
        if (i["r"], i["g"], i["b"]) != (128, 128, 128) or i["a"] != 128:
            return (i["r"], i["g"], i["b"])
        k = list(self.factions).index(fid)
        return DEFAULT_COLORS[k % len(DEFAULT_COLORS)]

    def faction_label(self, fid):
        c = self.factions.get(fid)
        if c is None:
            return "faction %d (missing)" % fid
        name = self.game.country_name(c["info"]["country"]) if self.game else str(c["info"]["country"])
        return "%d: %s%s" % (fid, name, "" if c["info"].get("ai_controlled") else " (player)")

    def owner_of_hex(self, i):
        """Faction that owns a hex for colouring: the area's building owner, or (conquest maps) the owner of the
        hex's province."""
        a = self.area_at.get(i)
        if a and "building" in a:
            return a["building"].get("info", {}).get("owner")
        if self.province is not None:
            p = self.province[i]
            if p != NO_HEX:
                ar = self.area_at.get(p)
                if ar and "building" in ar:
                    return ar["building"].get("info", {}).get("owner")
                return self.area_owner.get(p)
        return None

    # ------------------------------------------------------------------ undo
    def snapshot(self):
        return marshal.dumps(self.b)

    def begin(self, tag=None):
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
        self.b = marshal.loads(data)
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

    # ------------------------------------------------------------------ terrain edits
    def set_hexval(self, i, value):
        """Change a hex's u16; layer bits that are switched on get an empty overlay, switched off drop theirs."""
        value &= 0xFFFF
        old = self.b["map"]["hexes"][i]
        for layer, bit in LAYERS:
            if value & bit and not old & bit:
                self.overlays.setdefault(i, {})[layer] = pack_overlay({"terrain": 0, "tile": 0, "dx": 0, "dy": 0})
            elif old & bit and not value & bit:
                self.overlays.get(i, {}).pop(layer, None)
        self.b["map"]["hexes"][i] = value
        self._rebuild_overlays()

    def set_overlay(self, i, layer, o):
        """o = {"terrain", "tile", "dx", "dy"} or None to remove the layer."""
        bit = dict(LAYERS)[layer]
        hexes = self.b["map"]["hexes"]
        if o is None:
            hexes[i] &= ~bit & 0xFFFF
            self.overlays.get(i, {}).pop(layer, None)
        else:
            hexes[i] |= bit
            self.overlays.setdefault(i, {})[layer] = pack_overlay(o)
        self._rebuild_overlays()

    def _rebuild_overlays(self):
        hexes = self.b["map"]["hexes"]
        out = []
        for i, v in enumerate(hexes):
            ov = self.overlays.get(i, {})
            for layer, bit in LAYERS:
                if v & bit:
                    out.append(ov[layer])
        self.b["map"]["overlays"] = out

    # ------------------------------------------------------------------ armies
    def _armies(self):
        return self.b.setdefault("armies", {}).setdefault("list", [])

    def next_serial(self):
        used = [a["info"]["serial"] for a in self._armies()]
        n = max([self.b.get("armies", {}).get("next_serial", 1)] + [s + 1 for s in used])
        return n

    def new_army(self, i, faction=None, army=101, template=None):
        if template is not None:
            a = marshal.loads(marshal.dumps(template))
        else:
            if faction is None:
                faction = next(iter(self.factions), 1)
            hp = self.game.army_hp(army) if self.game else 80
            a = {"info": {"hex": i, "faction": faction, "serial": 0, "army": army, "level?": 0, "number": 1, "b10": 1,
                          "mobility": self.game.army_mobility(army) if self.game else 6, "hp": hp, "max_hp": hp,
                          "f16": 100},
                 "morale": 80, "flags?": 1}
        a["info"]["hex"] = i
        a["info"]["serial"] = self.next_serial()
        self._armies().append(a)
        self.b["armies"]["next_serial"] = a["info"]["serial"] + 1
        self.reindex()
        return a

    def delete_army(self, i):
        a = self.army_at.get(i)
        if a is None:
            return None
        self._armies().remove(a)
        serial = a["info"]["serial"]
        for g in self.b.get("armies", {}).get("groups", []):
            if serial in g.get("serials", []):
                g["serials"] = [s for s in g["serials"] if s != serial]
        self.reindex()
        return a

    def move_troop(self, src, dst):
        a = self.army_at.get(src)
        if a is None or dst in self.army_at:
            return False
        a["info"]["hex"] = dst
        self.reindex()
        return True

    # ------------------------------------------------------------------ areas / key areas
    def add_area(self, i):
        if i in self.area_at:
            return self.area_at[i]
        a = {"hex": i}
        self.b.setdefault("areas", {}).setdefault("list", []).append(a)
        self.reindex()
        return a

    def delete_area(self, i):
        a = self.area_at.get(i)
        if a is not None:
            self.b["areas"]["list"].remove(a)
            self.reindex()
        return a

    def add_key_area(self, i, key=1):
        if i not in self.key_at:
            self.b.setdefault("key_areas", {}).setdefault("list", []).append({"hex": i, "f1": 1, "key": key})
            self.reindex()
        return self.key_at[i]

    def delete_key_area(self, i):
        k = self.key_at.get(i)
        if k is not None:
            self.b["key_areas"]["list"].remove(k)
            self.reindex()

    # ------------------------------------------------------------------ save
    def save(self, path=None, backup=True, update_checksum=True):
        path = path or self.path
        if backup and os.path.exists(path) and not self.backed_up:
            bak = path + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(path, bak)
            self.backed_up = True
        size = save(self.b, path)
        self.path = path
        self.dirty = False
        msg = ""
        if update_checksum and self.game and self.game.assets:
            msg = update_battle_checksum(self.game.assets, path)
        return size, msg


def update_battle_checksum(assets, btl_path):
    """Refresh a map's MD5 in assets/ch_battle.bin if that file exists.  Same layout as World Conqueror 4
    (count u32, salted MD5 of the records, 24-byte records type/id/md5); GoG3's loader (libiron 0x1d61d4) uses
    type 3 for conquestN, 4 for corpsN and anything else for stageN."""
    ch = os.path.join(assets, "ch_battle.bin")
    if not os.path.exists(ch):
        return "no ch_battle.bin in this game"
    if os.path.normcase(os.path.dirname(os.path.abspath(btl_path))) != os.path.normcase(os.path.join(os.path.abspath(assets), "stage")):
        return ""
    name = os.path.basename(btl_path).lower()[:-4]
    for prefix, kinds in (("conquest", (3,)), ("corps", (4,)), ("stage", (1, 2, 0))):
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            num = int(name[len(prefix):])
            break
    else:
        return ""
    data = bytearray(open(ch, "rb").read())
    count = struct.unpack_from("<I", data, 0)[0]
    digest = hashlib.md5(open(btl_path, "rb").read()).digest()
    for k in range(count):
        off = 20 + 24 * k
        typ, rid = struct.unpack_from("<II", data, off)
        if rid == num and typ in kinds:
            if data[off + 8:off + 24] == digest:
                return "ch_battle.bin already up to date"
            if not os.path.exists(ch + ".bak"):
                shutil.copy2(ch, ch + ".bak")
            data[off + 8:off + 24] = digest
            data[4:20] = hashlib.md5(bytes(data[20:]) + b"easytechbattle").digest()
            open(ch, "wb").write(data)
            return "ch_battle.bin checksum updated"
    return "map not listed in ch_battle.bin"
