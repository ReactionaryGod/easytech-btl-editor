"""Load and re-save every .btl in the game's stage folder; the bytes must be identical."""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from wc4btl.btlfile import BtlFile, ALL_TYPES

STAGE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..",
                                                           "World Conqueror 4_1.30.0_learning", "assets", "stage")
sizes = {t.name + str(t.size): t.size for t in ALL_TYPES}
print("record sizes:", sizes)
t0 = time.time(); bad = 0; n = 0
for fn in sorted(os.listdir(STAGE)):
    if not fn.endswith(".btl"):
        continue
    data = open(os.path.join(STAGE, fn), "rb").read()
    try:
        out = BtlFile.parse(data).serialize()
    except Exception as e:
        bad += 1; print("ERROR", fn, e); continue
    n += 1
    if out != data:
        bad += 1; print("DIFF", fn, len(out), len(data))
print("files %d, failures %d, %.1fs" % (n, bad, time.time() - t0))
sys.exit(1 if bad else 0)
