"""Glory of Generals 3 (EasyTech, engine libiron.so) battle maps: stage/*.btl.

The files are FlatBuffers 1.9 buffers.  The schema below was recovered from the engine's inlined verifier
functions (root verifier at 0x1e3ab8 in libiron.so, arm64) and checked against all 420 shipped maps: every
non-padding byte is covered except 44 dead bytes in conquest1/conquest2 that no vtable points at.

Field kinds
    u8 u16 u32 u64          little-endian scalars
    sN                      inline struct of N bytes (decoded into named parts by STRUCTS)
    str                     string
    [u8] [u16] [u32] [u64]  vector of scalars
    T / [T]                 table / vector of tables

Names ending in "?" are inferred from data, not from engine code.  Unknown fields keep the name fN.
"""
import re
import struct

# ---------------------------------------------------------------------------------------------- schema
# table name -> [(field index, name, kind)]
TABLES = {
    "Battle": [
        (0, "version", "u16"), (1, "map", "MapInfo"), (2, "objectives", "Objectives"), (3, "key_areas", "KeyAreas"),
        (4, "countries", "Countries"), (5, "areas", "Areas"), (6, "armies", "Armies"), (7, "triggers", "Triggers"),
        (8, "reinforcements", "Reinforcements"), (9, "weather", "WeatherList"), (10, "ai_tree", "[u8]"),
    ],
    "MapInfo": [(0, "size", "s12"), (1, "f1", "u8"), (2, "hexes", "[u16]"), (3, "overlays", "[u32]"), (4, "f4", "u8")],
    "Objectives": [(0, "list", "[Objective]"), (1, "round_limit?", "u16")],
    "Objective": [(0, "type", "u16"), (1, "target", "u16"), (2, "rounds?", "u16"), (3, "f3", "u16"), (4, "f4", "u8")],
    "KeyAreas": [(0, "f0", "u8"), (1, "list", "[KeyArea]")],
    "KeyArea": [(0, "hex", "u16"), (1, "f1", "u8"), (2, "f2", "u8"), (3, "key", "u8")],
    "Countries": [(0, "list", "[Country]")],
    "Country": [
        (0, "info", "s36"), (1, "tech?", "[u8]"), (2, "exarmy_pool?", "[ExArmyStock]"), (3, "f3", "[Pair16]"),
        (4, "f4", "CountryExtra"), (5, "relations?", "[Relation]"), (6, "tag", "Tag"), (7, "f7", "u8"),
        (8, "f8", "u16"), (9, "f9", "u8"),
    ],
    "ExArmyStock": [(0, "exarmy", "u16"), (1, "level?", "u8"), (2, "f2", "u8")],
    "Pair16": [(0, "f0", "u16"), (1, "f1", "u16")],
    "CountryExtra": [
        (0, "f0", "[u16]"), (1, "f1", "u16"), (2, "f2", "[u16]"), (3, "f3", "u16"), (4, "f4", "u16"),
        (5, "f5", "[ByteShort]"), (6, "f6", "u16"), (7, "f7", "u16"), (8, "f8", "u16"), (9, "f9", "u16"),
        (10, "f10", "u16"), (11, "f11", "u16"), (12, "f12", "u8"), (13, "f13", "u8"), (14, "f14", "u8"),
        (15, "f15", "u8"), (16, "f16", "[Triple16]"), (17, "f17", "u16"), (18, "f18", "u8"), (19, "f19", "u16"),
        (20, "f20", "u16"), (21, "f21", "[u32]"), (22, "f22", "u8"), (23, "f23", "u8"), (24, "f24", "u8"),
    ],
    "ByteShort": [(0, "f0", "u8"), (1, "f1", "u16")],
    "Triple16": [(0, "f0", "u16"), (1, "f1", "u16"), (2, "f2", "u16")],
    "Relation": [(0, "faction?", "u16"), (1, "value?", "u16")],
    "Tag": [(0, "id", "u16"), (1, "data", "[u8]")],
    "Areas": [
        (0, "list", "[Area]"), (1, "f1", "[u32]"), (2, "province_of_hex?", "[u16]"), (3, "f3", "[u16]"),
        (4, "f4", "[u64]"), (5, "f5", "u8"), (6, "area_owners?", "[AreaOwner]"), (7, "f7", "u16"),
    ],
    "Area": [
        (0, "hex", "u16"), (1, "name", "u16"), (2, "f2", "u8"), (3, "building", "Building"),
        (4, "fortification", "Fortification"), (5, "f5", "s3"), (6, "f6", "u8"),
    ],
    "Building": [
        (0, "info", "s8"), (1, "f1", "u32"), (2, "ai", "AIOrder"), (3, "f3", "[Triple16]"), (4, "f4", "BuildingExtra"),
        (5, "tag", "Tag"), (6, "f6", "u8"), (7, "f7", "u8"),
    ],
    "AIOrder": [(0, "mode?", "u8"), (1, "f1", "u16"), (2, "target_hex?", "u16"), (3, "f3", "u8"), (4, "f4", "u8"),
                (5, "f5", "u16"), (6, "f6", "u16")],
    "BuildingExtra": [(0, "f0", "u8"), (1, "f1", "u16"), (2, "f2", "u8")],
    "Fortification": [(0, "type", "u8"), (1, "f1", "u8"), (2, "f2", "u8"), (3, "f3", "u8")],
    "AreaOwner": [(0, "hex", "u16"), (1, "faction?", "u16"), (2, "f2", "u8"), (3, "f3", "u8"), (4, "f4", "u8")],
    "Armies": [(0, "list", "[Army]"), (1, "groups", "[Group]"), (2, "next_serial", "u16"), (3, "stacks?", "[Stack]")],
    "Army": [
        (0, "info", "s20"), (1, "f1", "u16"), (2, "f2", "u8"), (3, "ai", "AIOrder"), (4, "f4", "u16"),
        (5, "morale", "u8"), (6, "f6", "u8"), (7, "flags?", "u8"), (8, "f8", "ArmyExtra"), (9, "f9", "s3"),
        (10, "exarmy", "ExArmy"), (11, "general", "General"), (12, "tag", "Tag"), (13, "f13", "u16"), (14, "f14", "u8"),
    ],
    "ArmyExtra": [(0, "f0", "u8"), (1, "f1", "u8"), (2, "f2", "[Triple16]"), (3, "f3", "u8"), (4, "f4", "u8"),
                  (5, "f5", "u32"), (6, "f6", "u8"), (7, "f7", "u16")],
    "ExArmy": [(0, "id", "u16"), (1, "level", "u8"), (2, "f2", "u16"), (3, "f3", "u16"), (4, "f4", "u16"), (5, "f5", "u16")],
    "General": [(0, "id", "u16"), (1, "f1", "u8"), (2, "level?", "u8")],
    "Group": [(0, "id", "u16"), (1, "serials", "[u16]")],
    "Stack": [(0, "hex", "u16"), (1, "serials?", "[u16]")],
    "Triggers": [(0, "name", "str"), (1, "list", "[TriggerEntry]"), (2, "f2", "[u32]"), (3, "data", "[u8]")],
    "TriggerEntry": [(0, "f0", "u16"), (1, "f1", "str"), (2, "f2", "u8")],
    "Reinforcements": [
        (0, "f0", "[ReinfSet]"), (1, "f1", "[ReinfSet]"), (2, "f2", "[ReinfSet2]"), (3, "f3", "[ReinfF3]"),
        (4, "f4", "u16"), (5, "f5", "[ReinfSet4]"), (6, "f6", "[ReinfSet4]"), (7, "f7", "[u16]"),
    ],
    "ReinfSet": [(0, "f0", "u16"), (1, "list", "[Triple16]")],
    "ReinfSet2": [(0, "f0", "u16"), (1, "list", "[Triple16]")],
    "ReinfF3": [(0, "f0", "u16"), (1, "f1", "u8"), (2, "f2", "u8")],
    "ReinfSet4": [(0, "f0", "u16"), (1, "list", "[Quad16]")],
    "Quad16": [(0, "f0", "u16"), (1, "f1", "u16"), (2, "f2", "u16"), (3, "f3", "u16")],
    "WeatherList": [(0, "list", "[Weather]")],
    "Weather": [(0, "type", "u8"), (1, "round", "u16"), (2, "duration", "u16")],
}

# inline structs: kind -> (struct format, part names, alignment).  "faction"/"owner" hold faction ids
# (countries.list[].info.id), "country" holds CountrySettings ids.
STRUCTS = {
    "s3": ("<3B", ("b0", "b1", "b2"), 1),
    "s8": ("<HHBBH", ("owner", "building", "style", "variant", "f6"), 8),
    "s12": ("<6H", ("width", "height", "view_x", "view_y", "view_w", "view_h"), 2),
    "s20": ("<HHHHBBBBHHI", ("hex", "faction", "serial", "army", "level?", "number", "b10", "mobility", "hp",
                             "max_hp", "f16"), 4),
    "s36": ("<HHBBHIIfffBBBBI", ("id", "country", "alliance", "ai_controlled", "ai?", "money", "f12", "rate_a", "rate_b",
                                 "rate_c", "r", "g", "b", "a", "f32"), 4),
}
SCALARS = {"u8": "<B", "u16": "<H", "u32": "<I", "u64": "<Q"}


def struct_codes(kind):
    """Per-part struct codes of an inline struct kind, e.g. 's12' -> ['H'] * 6."""
    out = []
    for n, c in re.findall(r"(\d*)([A-Za-z])", STRUCTS[kind][0]):
        out += [c] * int(n or 1)
    return out


NO_HEX = 0xFFFF

# objectives.list[].type -> stringtable "objective_N" and what "target" means
OBJECTIVE_TARGET = {0: None, 1: "hex", 2: "count", 3: "count", 4: "count", 5: "count", 6: "count", 7: "count",
                    8: "general", 9: "area hex", 10: "general", 11: "area hex", 12: "general"}

# per-hex u16 (map.hexes), decoded by libiron 0x2d1740
HEX_GROUND_MASK = 0x0007        # 0 earth, 1 grass, 2 desert, 3 snow, 4 ?
HEX_TILE_SHIFT = 3              # bits 3-7: ground tile variant
HEX_DISABLED = 0x0100           # outside the battlefield
HEX_SEA = 0x0200
HEX_LAYER_A = 0x0400            # takes the next overlay: decoration (terrain ids 49-57)
HEX_LAYER_B = 0x0800            # takes the next overlay: main terrain, sets the hex's terrain type
HEX_LAYER_C = 0x1000            # takes the next overlay: upper layer (canopy, peaks)
HEX_SEA_FLAG2 = 0x2000          # only meaningful together with HEX_SEA
HEX_FLAG3 = 0x4000


class FormatError(ValueError):
    pass


# ---------------------------------------------------------------------------------------------- reading
class Reader:
    def __init__(self, data):
        self.d = bytes(data)

    def u32(self, p):
        if p + 4 > len(self.d):
            raise FormatError("offset 0x%x out of range" % p)
        return struct.unpack_from("<I", self.d, p)[0]

    def table(self, t, name):
        d = self.d
        vt = t - struct.unpack_from("<i", d, t)[0]
        if not (0 <= vt < len(d) - 4):
            raise FormatError("bad vtable for %s at 0x%x" % (name, t))
        vs, ts = struct.unpack_from("<HH", d, vt)
        nf = (vs - 4) // 2
        fields = TABLES[name]
        if nf > len(fields):
            raise FormatError("%s at 0x%x has %d fields; schema knows %d" % (name, t, nf, len(fields)))
        out = {}
        for i, key, kind in fields:
            if i >= nf:
                continue
            fo = struct.unpack_from("<H", d, vt + 4 + 2 * i)[0]
            if fo:
                out[key] = self.value(t + fo, kind)
        return out

    def value(self, p, kind):
        d = self.d
        if kind in SCALARS:
            return struct.unpack_from(SCALARS[kind], d, p)[0]
        if kind in STRUCTS:
            fmt, names, _ = STRUCTS[kind]
            vals = struct.unpack_from(fmt, d, p)
            return dict(zip(names, vals))
        q = p + self.u32(p)
        n = self.u32(q)
        if kind == "str":
            return d[q + 4:q + 4 + n].decode("utf-8")
        if kind.startswith("[") and kind[1:-1] in SCALARS:
            fmt = SCALARS[kind[1:-1]]
            size = struct.calcsize(fmt)
            if q + 4 + n * size > len(d):
                raise FormatError("vector out of range at 0x%x" % q)
            return list(struct.unpack_from("<%d%s" % (n, fmt[1]), d, q + 4))
        if kind.startswith("["):
            sub = kind[1:-1]
            return [self.table(q + 4 + 4 * j + self.u32(q + 4 + 4 * j), sub) for j in range(n)]
        return self.table(q, kind)


def read(data):
    """Parse a .btl buffer into nested dicts / lists (plain types only, so marshal/json work)."""
    data = bytes(data)
    if len(data) < 8:
        raise FormatError("file too small")
    return Reader(data).table(struct.unpack_from("<I", data, 0)[0], "Battle")


def load(path):
    with open(path, "rb") as fh:
        return read(fh.read())


# ---------------------------------------------------------------------------------------------- writing
class Writer:
    """Front-to-back FlatBuffers writer: every table is followed by its children, so all uoffsets point
    forward as the format requires.  Only fields present in the dict are written (absent = default), which
    preserves the original files' choice of stored fields.  Identical vtables are shared."""

    def __init__(self):
        self.buf = bytearray()
        self.vtables = {}

    def align(self, n):
        while len(self.buf) % n:
            self.buf.append(0)

    def table(self, obj, name):
        fields = TABLES[name]
        known = {key for _, key, _ in fields}
        extra = set(obj) - known
        if extra:
            raise FormatError("%s: unknown keys %s" % (name, sorted(extra)))
        present = [(i, key, kind) for i, key, kind in fields if key in obj and obj[key] is not None]
        nf = max((i for i, _, _ in present), default=-1) + 1
        # inline layout: biggest alignment first
        def inline(kind):
            if kind in SCALARS:
                s = struct.calcsize(SCALARS[kind]); return s, s
            if kind in STRUCTS:
                return struct.calcsize(STRUCTS[kind][0]), STRUCTS[kind][2]
            return 4, 4
        order = sorted(present, key=lambda f: -inline(f[2])[1])
        rel, pos = {}, 4
        for i, key, kind in order:
            size, al = inline(kind)
            pos = (pos + al - 1) // al * al
            rel[i] = pos
            pos += size
        tsize = (pos + 3) // 4 * 4
        vt = struct.pack("<HH", 4 + 2 * nf, tsize) + b"".join(struct.pack("<H", rel.get(i, 0)) for i in range(nf))
        if vt not in self.vtables:
            self.align(2)
            self.vtables[vt] = len(self.buf)
            self.buf += vt
        maxal = max([4] + [inline(k)[1] for _, _, k in present])
        self.align(maxal)
        t = len(self.buf)
        self.buf += bytes(tsize)
        struct.pack_into("<i", self.buf, t, t - self.vtables[vt])
        children = []
        for i, key, kind in present:
            p = t + rel[i]
            v = obj[key]
            if kind in SCALARS:
                struct.pack_into(SCALARS[kind], self.buf, p, v)
            elif kind in STRUCTS:
                fmt, names, _ = STRUCTS[kind]
                struct.pack_into(fmt, self.buf, p, *[v[n] for n in names])
            else:
                children.append((p, kind, v))
        for p, kind, v in children:
            target = self.child(kind, v)
            struct.pack_into("<I", self.buf, p, target - p)
        return t

    def child(self, kind, v):
        if kind == "str":
            b = v.encode("utf-8")
            self.align(4)
            q = len(self.buf)
            self.buf += struct.pack("<I", len(b)) + b + b"\0"
            return q
        if kind.startswith("[") and kind[1:-1] in SCALARS:
            fmt = SCALARS[kind[1:-1]]
            size = struct.calcsize(fmt)
            # element data aligned to its size (and byte blobs to 8, for FlexBuffers)
            al = 8 if size in (1, 8) else max(4, size)
            while (len(self.buf) + 4) % al:
                self.buf.append(0)
            q = len(self.buf)
            self.buf += struct.pack("<I", len(v)) + struct.pack("<%d%s" % (len(v), fmt[1]), *v)
            return q
        if kind.startswith("["):
            sub = kind[1:-1]
            self.align(4)
            q = len(self.buf)
            self.buf += struct.pack("<I", len(v)) + bytes(4 * len(v))
            for j, e in enumerate(v):
                t = self.table(e, sub)
                slot = q + 4 + 4 * j
                struct.pack_into("<I", self.buf, slot, t - slot)
            return q
        return self.table(v, kind)


def write(battle):
    """Serialize a dict produced by read() (possibly edited) back into .btl bytes."""
    w = Writer()
    w.buf += bytes(4)
    root = w.table(battle, "Battle")
    struct.pack_into("<I", w.buf, 0, root)
    w.align(4)
    return bytes(w.buf)


def save(battle, path):
    data = write(battle)
    read(data)  # never write something we cannot read back
    with open(path, "wb") as fh:
        fh.write(data)
    return len(data)


# ---------------------------------------------------------------------------------------------- helpers
def overlays_by_hex(battle):
    """Assign map.overlays to hexes the way the engine does: walk hexes in index order, each layer bit
    (A 0x400, B 0x800, C 0x1000) takes the next overlay.  Returns {hex: {"A"|"B"|"C": overlay dict}}."""
    m = battle["map"]
    hexes, ov = m.get("hexes", []), m.get("overlays", [])
    out, cur = {}, 0
    for i, v in enumerate(hexes):
        for layer, bit in (("A", HEX_LAYER_A), ("B", HEX_LAYER_B), ("C", HEX_LAYER_C)):
            if v & bit:
                if cur >= len(ov):
                    raise FormatError("hex %d needs overlay %d but only %d exist" % (i, cur, len(ov)))
                x = ov[cur]; cur += 1
                dx, dy = struct.unpack("<bb", struct.pack("<H", x >> 16))
                out.setdefault(i, {})[layer] = {"terrain": x & 0xFF, "tile": (x >> 8) & 0xFF, "dx": dx, "dy": dy}
    if cur != len(ov):
        raise FormatError("%d overlays left over" % (len(ov) - cur))
    return out


def pack_overlay(terrain, tile, dx=0, dy=0):
    return terrain | tile << 8 | struct.unpack("<H", struct.pack("<bb", dx, dy))[0] << 16
