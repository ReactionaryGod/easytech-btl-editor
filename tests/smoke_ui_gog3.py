"""Headless UI smoke test for Glory of Generals 3 maps: opens maps, exercises panels, multi-select tools and undo,
writes screenshots to OUT.  Usage:  python tests/smoke_ui_gog3.py <screenshot dir> [gog3 folder]"""
import os
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    app.setFont(QFont("Segoe UI", 9))
from wc4btl.ui import common
_ini = os.path.join(tempfile.mkdtemp(), "settings.ini")
common.settings = lambda: QSettings(_ini, QSettings.IniFormat)     # never touch the user's real settings
from wc4btl.ui.mainwindow import MainWindow
from wc4btl.ui.mapview import MODE_MULTI, MODE_SELECT

OUT = sys.argv[1]
WORK = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("GOG3_DIR", ".")
errors = []
def _hook(*a):
    errors.append("".join(traceback.format_exception(*a)))
    print(errors[-1], file=sys.stderr)


sys.excepthook = _hook
w = MainWindow(); w.resize(1600, 1000); w.show(); app.processEvents(); w.default_dock_sizes(); app.processEvents()
w.load_work(WORK)
app.processEvents()
assert w.kind == "gog3", w.kind
print("tree:", [w.tree.topLevelItem(k).text(0) for k in range(w.tree.topLevelItemCount())])
print("problems in resource log:", [m for l, m in w.game.log if l != "ok"])
for fn in ("stage10101.btl", "stage10001.btl", "stage20111.btl", "conquest1.btl"):
    w.open_map(os.path.join(w.game.assets, "stage", fn)); app.processEvents()
    d = w.doc
    assert d.KIND == "gog3"
    w.grab().save(os.path.join(OUT, "g3_win_%s.png" % fn[:-4]))
    i = next(iter(d.army_at))
    w.view.resetTransform(); w.view.scale(0.6, 0.6); w.view.center_on_hex(i); app.processEvents()
    w.view.selected = i; w.on_hex_clicked(i); app.processEvents()
    for tab in range(w.hexpanel.count()):
        w.hexpanel.setCurrentIndex(tab); app.processEvents()
    w.hexpanel.setCurrentIndex(2); app.processEvents()
    w.grab().save(os.path.join(OUT, "g3_army_%s.png" % fn[:-4]))
    city = next((h for h, a in d.area_at.items() if "building" in a), None)
    if city is not None:
        w.view.center_on_hex(city); w.view.selected = city; w.on_hex_clicked(city)
        w.hexpanel.setCurrentIndex(1); app.processEvents()
        w.grab().save(os.path.join(OUT, "g3_area_%s.png" % fn[:-4]))
        w.hexpanel.setCurrentIndex(0); app.processEvents()
    w.data_dock.raise_()
    for tab in range(w.datapanel.count()):
        w.datapanel.setCurrentIndex(tab); app.processEvents()
    w.datapanel.setCurrentIndex(2); app.processEvents()
    w.grab().save(os.path.join(OUT, "g3_data_%s.png" % fn[:-4]))
    w.hex_dock.raise_()
    # edits through the UI paths, then undo everything
    before = d.snapshot()
    w.set_mode(MODE_MULTI)
    w.view.multi = set(list(range(d.n))[:40])
    w.tools.delete_armies(); w.tools.flag(0x0200, False); w.tools.delete_areas()
    w.set_mode(MODE_SELECT)
    d.begin(); d.move_troop(i, next(j for j in range(d.n) if j not in d.army_at))
    w.on_doc_changed("test")
    while w.doc.undo():
        pass
    w._after_history("undo all")
    import marshal
    assert marshal.loads(before) == w.doc.b, "undo after UI edits did not restore %s" % fn
    w.doc.dirty = False
# switching games in one session: WC4 folder, then a GoG3 map without its game data, then back to GoG3
wc4 = os.path.join(os.path.dirname(__file__), "..", "..", "World Conqueror 4_1.30.0_learning")
if os.path.isdir(wc4):
    w.load_work(os.path.normpath(wc4)); app.processEvents()
    assert w.kind == "wc4", w.kind
    w.open_map(os.path.join(w.game.assets, "stage", "conquest1.btl")); app.processEvents()
    assert w.kind == "wc4" and w.doc.btl is not None
    w.open_map(os.path.join(WORK, "assets", "stage", "stage10101.btl")); app.processEvents()
    assert w.kind == "gog3" and w.doc.KIND == "gog3", w.kind
    w.grab().save(os.path.join(OUT, "g3_no_gamedata.png"))
    w.load_work(WORK); app.processEvents()
    assert w.kind == "gog3"
print("errors:", len(errors))
for e in errors[:5]:
    print(e)
sys.exit(1 if errors else 0)
