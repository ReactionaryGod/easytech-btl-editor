"""Glory of Generals 3 document model on every shipped map: open, edit, undo back to the original, save, reload.
Usage:  python tests/test_gog3_model.py <gog3 folder (contains assets/)> [scratch dir]"""
import marshal
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gog3btl import read
from gog3btl.gamedata import Gog3Game
from gog3btl.model import Gog3Doc

work = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GOG3_DIR", ".")
scratch = sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp()
game = Gog3Game(work)
for level, msg in game.log:
    if level != "ok":
        print(level, msg)
stage = os.path.join(game.assets, "stage")
bad = 0
files = game.stage_files()
for fn in files:
    path = os.path.join(stage, fn)
    try:
        d = Gog3Doc(path, game)
        orig = d.snapshot()
        ov = list(d.b["map"].get("overlays", []))
        d._rebuild_overlays()
        assert d.b["map"].get("overlays", []) == ov, "overlay rebuild changed the list"
        types = {d.terrain_type(i) for i in range(d.n)}
        assert types <= set(range(14)), types
        empty = next(i for i in range(d.n) if i not in d.army_at)
        d.begin(); a = d.new_army(empty)
        assert d.army_at[empty] is a
        dst = next(i for i in range(d.n) if i not in d.army_at)
        d.begin(); assert d.move_troop(empty, dst)
        d.begin(); d.set_overlay(dst, "C", {"terrain": 21, "tile": 2, "dx": -5, "dy": 7})
        assert d.overlay(dst, "C") == {"terrain": 21, "tile": 2, "dx": -5, "dy": 7}
        d.begin(); d.set_hexval(dst, d.hexval(dst) ^ 0x0400)
        d.begin(); d.add_area(dst); d.begin(); d.add_key_area(dst)
        out = os.path.join(scratch, fn)
        d.save(out, backup=False, update_checksum=False)
        again = Gog3Doc(out, game)
        assert again.overlay(dst, "C") == {"terrain": 21, "tile": 2, "dx": -5, "dy": 7}
        assert dst in again.army_at and dst in again.area_at and dst in again.key_at
        d.begin(); d.delete_army(dst)
        while d.undo():
            pass
        assert marshal.loads(orig) == d.b, "undo did not restore the original"
        assert read(open(path, "rb").read()) == d.b
        os.remove(out)
    except Exception as e:  # noqa: BLE001
        bad += 1
        print("FAIL", fn, type(e).__name__, e)
print("maps %d, failures %d" % (len(files), bad))
sys.exit(1 if bad else 0)
