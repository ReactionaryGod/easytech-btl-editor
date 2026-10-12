"""Select / multi-select tools for Glory of Generals 3 maps."""
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QLabel, QPushButton,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from wc4btl.ui.mapview import MODE_MULTI
from ..format import HEX_DISABLED, HEX_SEA, STRUCTS, struct_codes
from ..gamedata import GROUND_NAMES

ARMY_FIELDS = [("faction", "Faction"), ("army", "Army type"), ("number", "Number of sub-units"), ("level?", "Level (?)"),
               ("mobility", "Mobility"), ("hp", "HP"), ("max_hp", "Max HP"), ("morale", "Morale")]


class Gog3ToolPanel(QStackedWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setMinimumWidth(180)
        p0 = QWidget(); l0 = QVBoxLayout(p0)
        l0.addWidget(QLabel("<b>Select mode</b> (Glory of Generals 3)<br>Left click: select a hex (Hex panel).<br>"
                            "Left drag an army: move it to an empty hex.<br>Right / middle drag or Alt+drag: pan.<br>"
                            "Wheel: zoom.<br><br>Multi-select (2) edits many hexes at once. Province painting and "
                            "cropping are World Conqueror 4 tools."))
        l0.addStretch()
        self.addWidget(p0)
        p1 = QWidget(); l1 = QVBoxLayout(p1)
        l1.addWidget(QLabel("<b>Multi-select</b>: left drag adds hexes, right drag removes them."))
        self.multi_label = QLabel()
        l1.addWidget(self.multi_label)
        grid = QGridLayout()
        specs = [("Select all", self.select_all), ("Clear selection", self.clear),
                 ("Add armies…", self.add_armies), ("Delete armies", self.delete_armies),
                 ("Set army field…", self.set_army_field), ("Delete areas", self.delete_areas),
                 ("Set ground…", self.set_ground), ("Sea on", lambda: self.flag(HEX_SEA, True)),
                 ("Sea off", lambda: self.flag(HEX_SEA, False)), ("Disable hexes", lambda: self.flag(HEX_DISABLED, True)),
                 ("Enable hexes", lambda: self.flag(HEX_DISABLED, False))]
        for k, (text, fn) in enumerate(specs):
            b = QPushButton(text); b.clicked.connect(fn)
            grid.addWidget(b, k // 2, k % 2)
        l1.addLayout(grid)
        l1.addStretch()
        self.addWidget(p1)
        for lab in self.findChildren(QLabel):
            lab.setWordWrap(True)

    @property
    def view(self):
        return self.main.view

    @property
    def doc(self):
        return self.main.doc

    def set_mode(self, mode):
        self.setCurrentIndex(1 if mode == MODE_MULTI else 0)
        self.update_labels()

    def update_labels(self):
        self.multi_label.setText("%d hexes selected" % len(self.view.multi))

    def _bulk(self, label, fn):
        d = self.doc
        if not d or not self.view.multi:
            return
        d.begin()
        for i in sorted(self.view.multi):
            fn(i)
        d.reindex()
        self.main.on_doc_changed(label)

    def select_all(self):
        if self.doc:
            self.view.multi = set(range(self.doc.n)); self.view.viewport().update(); self.update_labels()

    def clear(self):
        self.view.multi.clear(); self.view.viewport().update(); self.update_labels()

    def _ask(self, title, rows):
        dlg = QDialog(self); dlg.setWindowTitle(title)
        fl = QFormLayout(dlg)
        for label, w in rows:
            fl.addRow(label, w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject); fl.addRow(bb)
        return dlg.exec()

    def _faction_combo(self):
        cb = QComboBox()
        for f in self.doc.faction_ids():
            cb.addItem(self.doc.faction_label(f), f)
        return cb

    def add_armies(self):
        d, g = self.doc, self.main.game
        if not d:
            return
        fac = self._faction_combo()
        army = QComboBox()
        for k, text in g.choices("army"):
            army.addItem(text, k)
        if not self._ask("Add an army on every selected empty land/sea hex", [("Faction", fac), ("Army", army)]):
            return
        self._bulk("Add armies", lambda i: None if i in d.army_at or d.is_disabled(i)
                   else d.new_army(i, fac.currentData(), army.currentData()))

    def delete_armies(self):
        self._bulk("Delete armies", self.doc.delete_army)

    def delete_areas(self):
        self._bulk("Delete areas", self.doc.delete_area)

    def set_army_field(self):
        d, g = self.doc, self.main.game
        if not d:
            return
        field = QComboBox()
        for k, text in ARMY_FIELDS:
            field.addItem(text, k)
        value = QSpinBox(); value.setRange(0, 65535)
        fac = self._faction_combo()
        army = QComboBox()
        for k, text in g.choices("army"):
            army.addItem(text, k)
        if not self._ask("Set a field on every selected army", [("Field", field), ("Number value", value),
                                                                ("Faction (for Faction)", fac),
                                                                ("Army (for Army type)", army)]):
            return
        key = field.currentData()
        v = fac.currentData() if key == "faction" else army.currentData() if key == "army" else value.value()

        def apply(i):
            a = d.army_at.get(i)
            if a is None:
                return
            if key == "morale":
                a["morale"] = min(255, v)
            else:
                code = struct_codes("s20")[STRUCTS["s20"][1].index(key)]
                a["info"][key] = min(v, 255 if code == "B" else 65535)
        self._bulk("Set army %s" % key, apply)

    def set_ground(self):
        d = self.doc
        if not d:
            return
        cb = QComboBox()
        for k, name in GROUND_NAMES.items():
            cb.addItem("%d  %s" % (k, name), k)
        if not self._ask("Ground for every selected hex", [("Ground", cb)]):
            return
        g = cb.currentData()
        self._bulk("Set ground", lambda i: d.set_hexval(i, (d.hexval(i) & ~7) | g))

    def flag(self, bit, on):
        d = self.doc
        if d:
            self._bulk("Hex flag", lambda i: d.set_hexval(i, (d.hexval(i) | bit) if on else (d.hexval(i) & ~bit)))
