"""Tools for the multi-select, province-painting and crop modes."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QSizePolicy, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QGroupBox, QLabel,
                               QMessageBox, QPushButton, QSpinBox, QStackedWidget, QVBoxLayout, QWidget, QDoubleSpinBox)

from ..btlfile import CITY, RANGES
from ..model import NO_HEX, NO_OWNER
from . import dialogs
from .mapview import MODE_CROP, MODE_MULTI, MODE_PROVINCE, MODE_SELECT


class FieldValueDialog(QDialog):
    def __init__(self, parent, rt, labels="en", show_unknown=False):
        super().__init__(parent)
        self.setWindowTitle("Set a %s field on every selected hex" % rt.name.lower())
        lay = QFormLayout(self)
        self.rt = rt
        self.field = QComboBox()
        for f in rt.fields:
            if f[0] == "hex":
                continue
            self.field.addItem("%s  (%s)" % (f[3] if labels == "en" else f[2], f[0]), f[0])
        lay.addRow("Field", self.field)
        self.value = QDoubleSpinBox(); self.value.setDecimals(3); self.value.setRange(-2**31, 2**31 - 1)
        lay.addRow("Value", self.value)
        self.field.currentIndexChanged.connect(self._update_range)
        self._update_range()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def _update_range(self):
        code = self.rt.field(self.field.currentData())[1]
        if code in "fd":
            self.value.setDecimals(3); self.value.setRange(-1e9, 1e9)
        else:
            lo, hi = RANGES[code]
            self.value.setDecimals(0); self.value.setRange(lo, hi)

    def result_value(self):
        return self.field.currentData(), self.value.value()


class ToolPanel(QStackedWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setMinimumWidth(180)
        # page 0: select mode help
        p0 = QWidget(); l0 = QVBoxLayout(p0)
        l0.addWidget(QLabel("<b>Select mode</b><br>Left click: select a hex (see the Hex panel).<br>"
                            "Left drag a troop: move it to an empty hex.<br>Right / middle drag or Alt+drag: pan.<br>"
                            "Wheel: zoom.<br><br>Switch modes with the toolbar: Multi-select, Province paint, Crop."))
        l0.addStretch()
        self.addWidget(p0)
        # page 1: multi
        p1 = QWidget(); l1 = QVBoxLayout(p1)
        self.multi_label = QLabel()
        l1.addWidget(QLabel("<b>Multi-select</b>: left drag adds hexes, right drag removes them."))
        l1.addWidget(self.multi_label)
        grid = QGridLayout()
        specs = [("Select all", self.select_all), ("Clear selection", self.clear_multi),
                 ("Create troops", self.create_troops), ("Delete troops", self.delete_troops),
                 ("Create cities", self.create_cities), ("Delete cities", self.delete_cities),
                 ("Set owner…", self.set_owner), ("Set province…", self.set_province),
                 ("Set troop field…", lambda: self.set_field("troop")), ("Set city field…", lambda: self.set_field("city")),
                 ("Add mines", self.add_mines), ("Delete mines", self.delete_mines)]
        for k, (text, fn) in enumerate(specs):
            b = QPushButton(text); b.clicked.connect(fn)
            grid.addWidget(b, k // 2, k % 2)
        l1.addLayout(grid)
        l1.addStretch()
        self.addWidget(p1)
        # page 2: province
        p2 = QWidget(); l2 = QVBoxLayout(p2)
        self.prov_label = QLabel()
        self.prov_label.setWordWrap(True)
        l2.addWidget(self.prov_label)
        for text, fn in (("Apply", self.apply_province), ("Clear painted hexes", self.clear_province),
                         ("Cancel", self.cancel_province)):
            b = QPushButton(text); b.clicked.connect(fn); l2.addWidget(b)
        l2.addStretch()
        self.addWidget(p2)
        # page 3: crop
        p3 = QWidget(); l3 = QVBoxLayout(p3)
        l3.addWidget(QLabel("<b>Crop</b>: left drag a rectangle of hexes, then save it as a new standalone map "
                            "in the stage folder (EModule's 截取 tool)."))
        self.crop_label = QLabel("No rectangle yet.")
        l3.addWidget(self.crop_label)
        b = QPushButton("Save rectangle as new map…"); b.clicked.connect(self.main.crop_save)
        l3.addWidget(b)
        b = QPushButton("Whole map"); b.clicked.connect(self.crop_all)
        l3.addWidget(b)
        l3.addStretch()
        self.addWidget(p3)

    def showEvent(self, ev):
        for lab in self.findChildren(QLabel):
            lab.setWordWrap(True)
        super().showEvent(ev)

    @property
    def view(self):
        return self.main.view

    @property
    def doc(self):
        return self.main.doc

    def set_mode(self, mode):
        self.setCurrentIndex({MODE_SELECT: 0, MODE_MULTI: 1, MODE_PROVINCE: 2, MODE_CROP: 3}[mode])
        self.update_labels()

    def update_labels(self):
        v = self.view
        self.multi_label.setText("%d hexes selected" % len(v.multi))
        d = self.doc
        if d and v.province_anchor is not None:
            a = d.file_hex(v.province_anchor)
            x, y = d.xy(v.province_anchor)
            name = self.main.game.city_name(d.city_at[v.province_anchor]["name"]) if v.province_anchor in d.city_at else ""
            self.prov_label.setText("<b>Province painting</b> for the city at (%d, %d) %s (hex id %d).<br>"
                                    "Left drag: add hexes. Right drag: remove.<br>%d hexes painted. "
                                    "Apply makes exactly these hexes belong to this city." % (x, y, name, a, len(v.province_set)))
        if v.crop_rect:
            x0, y0, x1, y1 = v.crop_rect
            self.crop_label.setText("From (%d, %d) to (%d, %d): %d x %d hexes" % (
                min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1), abs(x1 - x0) + 1, abs(y1 - y0) + 1))

    # ------------------------------------------------------------------ multi actions
    def _bulk(self, label, fn):
        d = self.doc
        if not d or not self.view.multi:
            return
        d.begin()
        for i in sorted(self.view.multi):
            fn(i)
        self.main.on_doc_changed(label)

    def select_all(self):
        if self.doc:
            self.view.multi = set(range(self.doc.n)); self.view.viewport().update(); self.update_labels()

    def clear_multi(self):
        self.view.multi.clear(); self.view.viewport().update(); self.update_labels()

    def create_troops(self):
        self._bulk("Create troops", lambda i: None if i in self.doc.troop_at else self.doc.set_troop(i, None))

    def delete_troops(self):
        self._bulk("Delete troops", self.doc.delete_troop)

    def create_cities(self):
        self._bulk("Create cities", lambda i: None if i in self.doc.city_at else self.doc.set_city(i))

    def delete_cities(self):
        self._bulk("Delete cities", self.doc.delete_city)

    def add_mines(self):
        self._bulk("Add mines", lambda i: None if i in self.doc.mine_at else self.doc.add_mine(i))

    def delete_mines(self):
        self._bulk("Delete mines", self.doc.delete_mine)

    def set_owner(self):
        if not self.doc:
            return
        k = dialogs.pick_faction(self, self.doc, self.main.images)
        if k is None:
            return
        d = self.doc
        self._bulk("Set owner", lambda i: d.set_owner(i, k) if (i in d.troop_at or i in d.city_at) else None)

    def set_province(self):
        d = self.doc
        if not d:
            return
        dlg = QDialog(self); dlg.setWindowTitle("Set province")
        fl = QFormLayout(dlg)
        x = QSpinBox(); x.setRange(-1, d.W - 1); y = QSpinBox(); y.setRange(-1, d.H - 1)
        if self.view.selected is not None:
            sx, sy = d.xy(self.view.selected); x.setValue(sx); y.setValue(sy)
        fl.addRow(QLabel("Hex of the city the selected hexes should belong to\n(-1 = no province)"))
        fl.addRow("City X", x); fl.addRow("City Y", y)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); fl.addRow(bb)
        if not dlg.exec():
            return
        fh = NO_HEX if x.value() < 0 or y.value() < 0 else d.file_hex(y.value() * d.W + x.value())
        self._bulk("Set province", lambda i: d.set_province(i, fh))

    def set_field(self, kind):
        d = self.doc
        if not d:
            return
        rt = d.btl.troop_type() if kind == "troop" else CITY
        dlg = FieldValueDialog(self, rt, self.main.opts.get("labels", "en"))
        if not dlg.exec():
            return
        key, val = dlg.result_value()
        table = d.troop_at if kind == "troop" else d.city_at
        hits = [i for i in self.view.multi if i in table]
        if not hits:
            QMessageBox.information(self, "Nothing to change", "No selected hex has a %s." % kind)
            return
        self._bulk("Set %s.%s" % (kind, key), lambda i: table[i].__setitem__(key, val) if i in table else None)

    # ------------------------------------------------------------------ province
    def apply_province(self):
        v, d = self.view, self.doc
        if d is None or v.province_anchor is None:
            return
        anchor = d.file_hex(v.province_anchor)
        d.begin()
        for i in range(d.n):
            if i in v.province_set:
                d.set_province(i, anchor)
            elif d.province(i) == anchor:
                d.set_province(i, NO_HEX)
        self.main.set_mode(MODE_SELECT)
        self.main.on_doc_changed("Paint province")

    def clear_province(self):
        self.view.province_set.clear(); self.view.viewport().update(); self.update_labels()

    def cancel_province(self):
        self.main.set_mode(MODE_SELECT)

    def crop_all(self):
        if self.doc:
            self.view.crop_rect = (0, 0, self.doc.W - 1, self.doc.H - 1)
            self.view.viewport().update(); self.update_labels()
