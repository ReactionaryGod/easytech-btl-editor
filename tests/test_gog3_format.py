"""Glory of Generals 3 format tests that need no game files.
Run with:  python -m unittest discover -s tests -p "test_*format.py" """
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gog3btl import FormatError, overlays_by_hex, pack_overlay, read, write
from gog3btl.format import HEX_LAYER_B, HEX_LAYER_C, HEX_SEA


def make():
    w, h = 6, 4
    hexes = [0x0001] * (w * h)
    hexes[5] |= HEX_SEA
    hexes[7] |= HEX_LAYER_B | HEX_LAYER_C            # forest with canopy: two overlays
    hexes[9] |= HEX_LAYER_B                          # hill: one overlay
    return {
        "version": 1,
        "map": {"size": {"width": w, "height": h, "view_x": 1, "view_y": 1, "view_w": 4, "view_h": 2},
                "hexes": hexes,
                "overlays": [pack_overlay(21, 2), pack_overlay(21, 5, -12, 30), pack_overlay(34, 1)]},
        "objectives": {"list": [{"type": 8, "target": 1001, "rounds?": 10}], "round_limit?": 20},
        "key_areas": {"list": [{"hex": 9, "f1": 1, "key": 1}]},
        "countries": {"list": [
            {"info": {"id": 1, "country": 3, "alliance": 1, "ai_controlled": 0, "ai?": 0, "money": 100, "f12": 0,
                      "rate_a": 1.0, "rate_b": 1.0, "rate_c": 1.0, "r": 128, "g": 128, "b": 128, "a": 128, "f32": 0},
             "tech?": [1, 0, 2, 0, 0], "f7": 1, "f8": 1},
            {"info": {"id": 2, "country": 1, "alliance": 2, "ai_controlled": 1, "ai?": 2, "money": 0, "f12": 0,
                      "rate_a": 0.5, "rate_b": 1.0, "rate_c": 1.25, "r": 255, "g": 0, "b": 0, "a": 255, "f32": 0},
             "tech?": [0, 0, 0, 0, 0], "relations?": [{"faction?": 1, "value?": 50}]},
        ]},
        "areas": {"list": [
            {"hex": 9, "name": 52, "f2": 1,
             "building": {"info": {"owner": 1, "building": 101, "style": 1, "variant": 2, "f6": 0}}},
            {"hex": 3, "fortification": {"type": 2}},
        ]},
        "armies": {"list": [
            {"info": {"hex": 8, "faction": 1, "serial": 1, "army": 101, "level?": 0, "number": 2, "b10": 1,
                      "mobility": 6, "hp": 160, "max_hp": 160, "f16": 100},
             "morale": 80, "flags?": 1, "general": {"id": 1001, "level?": 2}},
            {"info": {"hex": 0xFFFF, "faction": 2, "serial": 2, "army": 104, "level?": 1, "number": 1, "b10": 0,
                      "mobility": 8, "hp": 160, "max_hp": 160, "f16": 100},
             "morale": 80, "flags?": 1, "exarmy": {"id": 430, "level": 3, "f2": 125, "f3": 125, "f4": 100}},
        ], "groups": [{"id": 1, "serials": [1, 2]}], "next_serial": 3},
        "triggers": {"name": "", "list": [], "f2": [0x01280000, 0, 0, 0x000A0000], "data": [0, 0, 40, 1]},
        "reinforcements": {},
        "weather": {"list": [{"type": 1, "round": 3, "duration": 2}]},
        "ai_tree": [0, 0, 40, 1],
    }


class Gog3FormatTest(unittest.TestCase):
    def test_roundtrip(self):
        b = make()
        data = write(b)
        self.assertEqual(read(data), read(write(read(data))))
        again = read(data)
        self.assertEqual(again["armies"]["list"][0]["general"]["id"], 1001)
        self.assertEqual(again["countries"]["list"][1]["info"]["rate_c"], 1.25)
        self.assertEqual(again["map"]["hexes"], b["map"]["hexes"])
        self.assertEqual(again["ai_tree"], [0, 0, 40, 1])

    def test_offsets_point_forward_and_align(self):
        data = write(make())
        root = struct.unpack_from("<I", data, 0)[0]
        self.assertEqual(root % 4, 0)
        self.assertEqual(len(data) % 4, 0)

    def test_overlays_follow_layer_bits(self):
        ov = overlays_by_hex(make())
        self.assertEqual(sorted(ov), [7, 9])
        self.assertEqual(ov[7]["B"]["terrain"], 21)
        self.assertEqual((ov[7]["C"]["dx"], ov[7]["C"]["dy"]), (-12, 30))
        self.assertEqual(ov[9]["B"]["terrain"], 34)

    def test_overlay_count_mismatch_is_reported(self):
        b = make()
        b["map"]["overlays"] = b["map"]["overlays"][:2]
        with self.assertRaises(FormatError):
            overlays_by_hex(b)

    def test_unknown_key_is_rejected(self):
        b = make()
        b["armies"]["list"][0]["bogus"] = 1
        with self.assertRaises(FormatError):
            write(b)

    def test_absent_fields_stay_absent(self):
        again = read(write(make()))
        self.assertNotIn("exarmy", again["armies"]["list"][0])
        self.assertNotIn("general", again["armies"]["list"][1])


if __name__ == "__main__":
    unittest.main()
