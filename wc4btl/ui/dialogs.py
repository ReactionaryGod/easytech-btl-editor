"""Search / pick dialogs and small utility dialogs."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QCheckBox, QComboBox, QFormLayout,
                               QSpinBox, QTextEdit, QAbstractItemView)

from ..gamedata import ARMY_TYPES


class SearchTable(QDialog):
    """Generic filterable table; subclasses fill rows as (key, [cells], icon)."""

    def __init__(self, parent, title, headers, rows, current=None, icon_size=0):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(820, 600)
        self.rows = rows
        self.result = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Search:"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("name, id or any column text")
        self.edit.textChanged.connect(self.apply_filter)
        top.addWidget(self.edit)
        lay.addLayout(top)
        self.table = QTableWidget(len(rows), len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        if icon_size:
            self.table.setIconSize(QSize(icon_size, icon_size))
            self.table.verticalHeader().setDefaultSectionSize(icon_size + 6)
        self.table.setSortingEnabled(False)
        for r, (key, cells, icon) in enumerate(rows):
            for c, val in enumerate(cells):
                it = QTableWidgetItem()
                if isinstance(val, (int, float)):
                    it.setData(Qt.DisplayRole, val)
                else:
                    it.setText(str(val))
                if c == 0:
                    it.setData(Qt.UserRole, key)
                    if icon is not None:
                        it.setIcon(icon)
                self.table.setItem(r, c, it)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.doubleClicked.connect(self.accept)
        lay.addWidget(self.table)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        if current is not None:
            for r in range(self.table.rowCount()):
                if self.table.item(r, 0).data(Qt.UserRole) == current:
                    self.table.selectRow(r)
                    self.table.scrollToItem(self.table.item(r, 0), QAbstractItemView.PositionAtCenter)
                    break
        self.edit.setFocus()

    def apply_filter(self, text):
        words = text.lower().split()
        for r in range(self.table.rowCount()):
            hay = " ".join(self.table.item(r, c).text().lower() for c in range(self.table.columnCount()))
            self.table.setRowHidden(r, not all(w in hay for w in words))

    def accept(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.result = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        super().accept()


def pick_army(parent, game, images, current=None):
    rows = []
    for code in game.army_codes():
        r = game.army_row(code)
        elite = "elite (%d tiers)" % len(game.army_by_code[code]) if r.get("Elite") else ""
        rows.append((code, [code, game.army_name(code), ARMY_TYPES.get(r["Type"], r["Type"]), elite,
                            "%d-%d" % (r["MinAttack"], r["MaxAttack"]), r["HP"], r["Defence"], r["Mobility"],
                            "%d-%d" % (r["MinRange"], r["MaxRange"]), r["Id"]], None))
    dlg = SearchTable(parent, "Choose army", ["Code", "Name", "Type", "Elite", "Attack", "HP", "Def", "Mob",
                                              "Range", "Settings Id"], rows, current)
    return dlg.result if dlg.exec() else None


def pick_general(parent, game, images, current=None):
    rows = []
    stats = ("Infantry", "Artillery", "Armor", "Navy", "AirForce", "March")
    for g in sorted(game.generals, key=lambda g: g["Id"]):
        icon = None
        if images is not None and g["Id"] < 2000:
            pm = images.head(g)
            icon = QIcon(pm) if pm else None
        rank = game.text("general_rank_%d" % g.get("MilitaryRank", 0), str(g.get("MilitaryRank", "")))
        rows.append((g["Id"], [g["Id"], game.general_name(g["Id"]), g.get("Name") or "", rank,
                               " ".join(str(g.get(s, 0)) for s in stats), len(g.get("Skills") or []),
                               {1: "Player", 3: "AI/scenario"}.get(g.get("Type"), g.get("Type"))], icon))
    dlg = SearchTable(parent, "Choose general", ["Id", "Name", "Original name", "Rank",
                                                 "Inf Art Arm Nav Air March", "Skills", "Kind"], rows, current, 36)
    return dlg.result if dlg.exec() else None


def pick_country(parent, game, images, current=None):
    rows = []
    for cid in sorted(game.countries):
        icon = None
        if images is not None:
            fl = images.flag(cid)
            icon = QIcon(fl[0]) if fl else None
        c = game.countries[cid]
        rows.append((cid, [cid, game.country_name(cid), c.get("Name", ""), game.text("camp_%d" % c.get("Camp", 0), "")], icon))
    dlg = SearchTable(parent, "Choose country", ["Id", "Name", "Original name", "Camp"], rows, current, 28)
    return dlg.result if dlg.exec() else None


def pick_faction(parent, doc, images, current=None, allow_none=True):
    rows = []
    if allow_none:
        rows.append((255, [255, "(no owner)", ""], None))
    for k, f in enumerate(doc.btl.factions):
        icon = None
        if images is not None:
            fl = images.flag(f["country"])
            icon = QIcon(fl[0]) if fl else None
        rows.append((k, [k, doc.faction_label(f), "AI" if f["ai"] else "player side"], icon))
    dlg = SearchTable(parent, "Choose faction", ["Index", "Faction (id: country)", "Control"], rows, current, 28)
    return dlg.result if dlg.exec() else None


class CropDialog(QDialog):
    """Hex rectangle + new file name for the 'crop to new map' tool."""

    def __init__(self, parent, doc, rect, name):
        super().__init__(parent)
        self.setWindowTitle("Crop to a new standalone map")
        lay = QFormLayout(self)
        self.spins = []
        for label, val, mx in (("Start X", rect[0], doc.W - 1), ("Start Y", rect[1], doc.H - 1),
                               ("End X", rect[2], doc.W - 1), ("End Y", rect[3], doc.H - 1)):
            s = QSpinBox(); s.setRange(0, mx); s.setValue(val)
            lay.addRow(label, s)
            self.spins.append(s)
        self.name = QLineEdit(name)
        lay.addRow("New file name (.btl)", self.name)
        self.open_after = QCheckBox("Open the new map after saving")
        self.open_after.setChecked(True)
        lay.addRow(self.open_after)
        lay.addRow(QLabel("The new map gets its own terrain (copied from the source), only the factions present in\n"
                          "the rectangle, and every city, troop, mine, reinforcement, air raid and deploy slot inside it."))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def values(self):
        x0, y0, x1, y1 = (s.value() for s in self.spins)
        return (x0, y0, x1, y1), self.name.text().strip()


class LogDialog(QDialog):
    def __init__(self, parent, entries):
        super().__init__(parent)
        self.setWindowTitle("Resource import log")
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        te = QTextEdit(); te.setReadOnly(True)
        colors = {"ok": "#2a8a2a", "warn": "#b08000", "error": "#c03030"}
        te.setHtml("<br>".join('<span style="color:%s">%s</span>' % (colors.get(l, "#000"), m) for l, m in entries))
        lay.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject); bb.accepted.connect(self.accept)
        lay.addWidget(bb)


class SettingsDialog(QDialog):
    def __init__(self, parent, values):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        lay = QFormLayout(self)
        self.lang = QComboBox()
        for code, name in (("en", "English"), ("cn", "简体中文"), ("tw", "繁體中文"), ("de", "Deutsch"),
                           ("es", "Español"), ("ja", "日本語"), ("ko", "한국어")):
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(values.get("lang", "en"))))
        lay.addRow("Game text language", self.lang)
        self.labels = QComboBox()
        self.labels.addItem("English", "en"); self.labels.addItem("中文 (original field names)", "cn")
        self.labels.setCurrentIndex(max(0, self.labels.findData(values.get("labels", "en"))))
        lay.addRow("Field labels", self.labels)
        self.unknown = QCheckBox("Show unknown / padding fields in editors")
        self.unknown.setChecked(values.get("unknown", False))
        lay.addRow(self.unknown)
        self.backup = QCheckBox("Keep a .bak copy of each map before its first save")
        self.backup.setChecked(values.get("backup", True))
        lay.addRow(self.backup)
        self.checksum = QCheckBox("Update assets/ch_battle.bin when saving stage/conquest maps")
        self.checksum.setChecked(values.get("checksum", True))
        lay.addRow(self.checksum)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addRow(bb)

    def values(self):
        return {"lang": self.lang.currentData(), "labels": self.labels.currentData(),
                "unknown": self.unknown.isChecked(), "backup": self.backup.isChecked(),
                "checksum": self.checksum.isChecked()}
