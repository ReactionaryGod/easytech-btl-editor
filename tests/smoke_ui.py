"""Headless UI smoke test: opens maps, exercises panels/modes, writes screenshots to OUT."""
import os, sys, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
app = QApplication(sys.argv)
if os.environ["QT_QPA_PLATFORM"] == "offscreen":
    from PySide6.QtGui import QFont
    app.setFont(QFont("Segoe UI", 9))  # the offscreen platform otherwise picks the first font file it finds
QSettings("WC4Modding", "BtlEditorPC").clear()
from wc4btl.ui.mainwindow import MainWindow
from wc4btl.ui.mapview import MODE_MULTI, MODE_CROP, MODE_SELECT
OUT = sys.argv[1]
WORK = os.path.join(os.path.dirname(__file__), "..", "..", "World Conqueror 4_1.30.0_learning")
errors = []
sys.excepthook = lambda *a: errors.append("".join(traceback.format_exception(*a)))
w = MainWindow(); w.resize(1600, 1000); w.show(); app.processEvents(); w.default_dock_sizes(); app.processEvents()
w.load_work(os.path.normpath(WORK))
app.processEvents()
print("tree top-level:", [w.tree.topLevelItem(k).text(0) for k in range(w.tree.topLevelItemCount())])
for fn in ("stage10101.btl", "conquest1.btl", "event10201.btl", "warzone101.btl"):
    w.open_map(os.path.join(w.game.assets, "stage", fn)); app.processEvents()
    d = w.doc
    w.grab().save(os.path.join(OUT, "win_%s.png" % fn[:-4]))
    # zoom in on a troop
    i = next(iter(d.troop_at))
    w.view.resetTransform(); w.view.scale(0.6, 0.6); w.view.center_on_hex(i); app.processEvents()
    w.on_hex_clicked(i); w.view.selected = i
    for tab in range(w.hexpanel.count()):
        w.hexpanel.setCurrentIndex(tab); app.processEvents()
    w.hexpanel.setCurrentIndex(3); app.processEvents()
    w.grab().save(os.path.join(OUT, "zoom_%s.png" % fn[:-4]))
    for tab in range(w.datapanel.count()):
        w.datapanel.setCurrentIndex(tab); app.processEvents()
    w.data_dock.raise_(); w.datapanel.setCurrentIndex(1); app.processEvents()
    w.grab().save(os.path.join(OUT, "data_%s.png" % fn[:-4]))
    w.hex_dock.raise_()
    # modes
    w.set_mode(MODE_MULTI); w.view.multi = set(list(range(d.n))[:30]); w.tools.create_troops(); w.tools.set_owner if False else None
    w.tools.delete_troops(); w.set_mode(MODE_CROP); w.view.crop_rect = (0, 0, 5, 5); w.tools.update_labels()
    w.start_province_mode(next(iter(d.city_at))); w.tools.apply_province(); app.processEvents()
    while d.undo(): pass
    w.doc.dirty = False
print("errors:", len(errors))
for e in errors[:5]: print(e)
