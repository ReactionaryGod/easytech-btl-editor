"""Glory of Generals 3: read every .btl, rebuild it, read the rebuild; the content must be identical.
Usage:  python tests/test_gog3_roundtrip.py <gog3>/assets/stage"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from gog3btl import overlays_by_hex, read, write

stage = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("GOG3_DIR", "."), "assets", "stage")
t0 = time.time()
n = bad = 0
orig_total = new_total = 0
for fn in sorted(os.listdir(stage)):
    if not fn.endswith(".btl"):
        continue
    n += 1
    data = open(os.path.join(stage, fn), "rb").read()
    try:
        b = read(data)
        out = write(b)
        again = read(out)
        overlays_by_hex(b)
        if again != b:
            bad += 1
            print("DIFF", fn)
        orig_total += len(data)
        new_total += len(out)
    except Exception as e:  # noqa: BLE001 - report and continue
        bad += 1
        print("ERROR", fn, type(e).__name__, e)
print("maps %d, failures %d, original %d bytes, rebuilt %d bytes, %.1fs" % (n, bad, orig_total, new_total, time.time() - t0))
sys.exit(1 if bad else 0)
