"""world.bin (the conquest world map named in config/def_map.xml).

Layout: 16-byte header (magic 'YSAE', u32 version, i32 width, i32 height), then width*height terrain
records (same 16-byte layout as the .btl terrain section), then one u16 province value per hex.
"""
import struct

from .btlfile import TERRAIN


class WorldBin:
    def __init__(self, path):
        with open(path, "rb") as fh:
            data = fh.read()
        self.magic = data[:4]
        self.version, self.width, self.height = struct.unpack_from("<Iii", data, 4)
        n = self.width * self.height
        pos = 16
        self.terrain = [TERRAIN.unpack(data, pos + i * 16) for i in range(n)]
        pos += 16 * n
        if len(data) >= pos + 2 * n:
            self.provinces = list(struct.unpack_from("<%dH" % n, data, pos))
        else:
            self.provinces = [0xFFFF] * n
