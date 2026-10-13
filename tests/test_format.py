"""Format tests that need no game files: build .btl files from scratch, save, re-read and compare.
Run with:  python -m unittest discover -s tests -p "test_format.py" """
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from wc4btl.btlfile import (AIRRAID, AIRSUPPORT, CAPITAL, CITY, DEPLOY, EVENT, FACTION, GENERAL, MINE, S27, SCHEME,
                            TERRAIN, WEATHER, BtlFile)


def make(version, own_terrain, w=6, h=4):
    b = BtlFile()
    b.master["version"] = version
    b.master["map_index"] = 0 if own_terrain else 1
    b.master["width"], b.master["height"] = w, h
    n = w * h
    b.factions = [FACTION.new(id=k, r=40 * k, g=100, b=200, ai=k) for k in range(3)]
    if own_terrain:
        b.terrain = [TERRAIN.new() for _ in range(n)]
    b.provinces = [0xFFFF] * n
    b.owners = [255] * n
    b.cities = [CITY.new(hex=1)]
    b.provinces[1] = b.provinces[2] = 1
    b.owners[1] = 0
    b.troops = [b.troop_type().new(hex=1, army=39), b.troop_type().new(hex=5, army=1)]
    b.mines = [MINE.new(hex=7)]
    b.schemes = [SCHEME.new(), SCHEME.new()]
    b.weather = [WEATHER.new()]
    b.events = [EVENT.new()]
    b.reinforcements = [b.reinf_type().new(hex=3)]
    b.airraids = [AIRRAID.new()]
    b.deploy_a = [DEPLOY.new(hex=4)]
    b.deploy_b = [DEPLOY.new(hex=6)]
    b.capitals = [CAPITAL.new(hex=1)]
    b.s27 = [S27.new(a=1, b=2)]
    b.generals = [GENERAL.new()]
    b.airsupport = [AIRSUPPORT.new()]
    if version >= 3:
        b.tail = b"\x01\x02\x03"
    return b


class FormatTest(unittest.TestCase):
    def test_roundtrip_all_versions(self):
        for version in (1, 2, 3):
            for own in (True, False):
                with self.subTest(version=version, own_terrain=own):
                    data = make(version, own).serialize()
                    again = BtlFile.parse(data)
                    self.assertEqual(again.serialize(), data)
                    self.assertEqual(len(again.troops), 2)
                    self.assertEqual(len(again.schemes), 2, "duplicate schemes must be kept")
                    self.assertEqual(again.factions[2]["id"], 2)
                    if version >= 3:
                        self.assertEqual(again.tail, b"\x01\x02\x03")

    def test_counts_follow_lists(self):
        b = make(3, True)
        b.troops.append(b.troop_type().new(hex=9))
        b.weather.clear()
        again = BtlFile.parse(b.serialize())
        self.assertEqual(again.master["n_troops"], 3)
        self.assertEqual(again.master["n_weather"], 0)

    def test_record_sizes(self):
        b1, b3 = make(1, True), make(3, True)
        self.assertEqual(b1.troop_type().size, 48)
        self.assertEqual(b3.troop_type().size, 64)
        self.assertEqual(b1.reinf_type().size, 80)
        self.assertEqual(make(2, True).reinf_type().size, 104)

    def test_troop_skin_is_byte_47(self):
        for version in (1, 3):
            b = make(version, True)
            t = b.troops[1]
            t["hold_dist"], t["skin"] = 3, 1
            data = b.serialize()
            again = BtlFile.parse(data)
            self.assertEqual((again.troops[1]["hold_dist"], again.troops[1]["skin"]), (3, 1))
            rt = b.troop_type()
            raw = rt.pack(again.troops[1])
            self.assertEqual(raw[44:48], bytes([3, 0, 0, 1]))

    def test_values_are_clamped(self):
        r = FACTION.new()
        r["r"] = 999
        self.assertEqual(r["r"], 255)

    def test_truncated_file_is_rejected(self):
        data = make(3, False).serialize()
        with self.assertRaises(ValueError):
            BtlFile.parse(data[:-5])


if __name__ == "__main__":
    unittest.main()
