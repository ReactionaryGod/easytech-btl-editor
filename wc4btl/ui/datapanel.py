"""Whole-map data (EModule's data panel): header, factions, events, weather, schemes, faction generals,
air support, deploy slots and the unknown 8-byte section."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QColor, QPixmap
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..btlfile import COUNT_KEYS
from ..enums import EVENT_ACTION, TRIGGER_CONDITION, WEATHER
from ..model import LIST_SECTIONS
from .forms import RecordForm


class ListEditor(QWidget):
    def __init__(self, panel, section):
        super().__init__()
        self.panel, self.section = panel, section
        self.main = panel.main
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Vertical)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_row)
        ll.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Add", self.add), ("Copy", self.copy), ("Delete", self.delete), ("Up", lambda: self.move(-1)),
                         ("Down", lambda: self.move(1))):
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        ll.addLayout(row)
        self.form_area = QScrollArea(); self.form_area.setWidgetResizable(True)
        split.addWidget(left); split.addWidget(self.form_area)
        split.setSizes([220, 600])
        split.setChildrenCollapsible(False)
        lay.addWidget(split)

    @property
    def doc(self):
        return self.main.doc

    def rows(self):
        return getattr(self.doc.btl, self.section) if self.doc else []

    def summary(self, k, r):
        g, d = self.main.game, self.doc
        s = self.section
        if s == "factions":
            return "[%d] %s%s" % (k, d.faction_label(r), "" if r["ai"] else "  (player side)")
        if s == "events":
            return "#%d  %s -> %s  (round %d)" % (r["event_id"], TRIGGER_CONDITION.get(r["condition"], r["condition"]),
                                                  EVENT_ACTION.get(r["action"], r["action"]), r["round"])
        if s == "weather":
            return "%s  rounds %d-%d" % (WEATHER.get(r["type"], r["type"]), r["round"], r["round"] + r["duration"] - 1)
        if s == "schemes":
            return "scheme %d  round %d  target %d" % (r["scheme_id"], r["round"], r["target"])
        if s == "generals":
            f = d.faction_by_id(r["faction"])
            return "%s: %s" % (d.faction_label(f) if f else r["faction"], g.general_name(r["general"]))
        if s == "airsupport":
            f = d.faction_by_id(r["faction"])
            return "%s: %s x%d (round %d)" % (d.faction_label(f) if f else r["faction"], g.army_name(r["army"]),
                                              r["ammo"], r["round"])
        if s in ("deploy_a", "deploy_b"):
            i = d.local(r["hex"])
            return "slot %d  hex %s" % (r["slot"], "(empty)" if i is None else "(%d, %d)" % d.xy(i))
        return "#%d" % k

    def reload(self, keep=None):
        cur = self.list.currentRow() if keep is None else keep
        self.list.blockSignals(True)
        self.list.clear()
        for k, r in enumerate(self.rows()):
            it = QListWidgetItem(self.summary(k, r))
            if self.section == "factions":
                pm = QPixmap(14, 14); pm.fill(QColor(r["r"], r["g"], r["b"]))
                it.setIcon(QIcon(pm))
            self.list.addItem(it)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(max(0, min(cur, self.list.count() - 1)))
        self.show_row(self.list.currentRow())

    def show_row(self, k):
        old = self.form_area.takeWidget()
        if old:
            old.deleteLater()
        rows = self.rows()
        if not (0 <= k < len(rows)):
            self.form_area.setWidget(QLabel("Nothing selected."))
            return
        rec = rows[k]
        collapsed = ("Technology levels",) if self.section == "factions" else ()
        form = RecordForm(self.main.ctx, rec, collapsed=collapsed)
        form.edited.connect(lambda key, k=k: self.list.item(k).setText(self.summary(k, rec)) if self.list.item(k) else None)
        self.form_area.setWidget(form)

    def _act(self, label, fn, keep):
        self.doc.begin()
        fn()
        self.main.on_doc_changed(label, rebuild_panels=False)
        self.reload(keep)
        self.main.hexpanel.rebuild()

    def add(self):
        if self.doc:
            self._act("Add " + self.section, lambda: self.doc.list_new(self.section), len(self.rows()))

    def copy(self):
        k = self.list.currentRow()
        rows = self.rows()
        if not (0 <= k < len(rows)):
            return
        if self.section == "factions":
            self._act("Copy faction", lambda: self.doc.add_faction(rows[k]), len(rows))
        else:
            self._act("Copy " + self.section, lambda: rows.append(rows[k].clone()), len(rows))

    def delete(self):
        k = self.list.currentRow()
        rows = self.rows()
        if not (0 <= k < len(rows)):
            return
        if QMessageBox.question(self, "Delete", "Delete '%s'?" % self.summary(k, rows[k])) != QMessageBox.Yes:
            return
        if self.section == "factions":
            self._act("Delete faction", lambda: self.doc.delete_faction(k), k)
        else:
            self._act("Delete " + self.section, lambda: rows.pop(k), k)

    def move(self, delta):
        k = self.list.currentRow()
        rows = self.rows()
        j = k + delta
        if not (0 <= k < len(rows) and 0 <= j < len(rows)):
            return
        if self.section == "factions":
            self._act("Move faction", lambda: self.doc.move_faction(k, delta), j)
        else:
            def swap():
                rows[k], rows[j] = rows[j], rows[k]
            self._act("Move", swap, j)


class DataPanel(QTabWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.header_area = QScrollArea(); self.header_area.setWidgetResizable(True)
        self.addTab(self.header_area, "Header")
        self.editors = {}
        for section in ("factions", "events", "weather", "schemes", "generals", "airsupport", "deploy_a",
                        "deploy_b", "s27"):
            ed = ListEditor(self, section)
            self.editors[section] = ed
            self.addTab(ed, LIST_SECTIONS[section][1])
        self.currentChanged.connect(lambda *_: self.reload_current())

    def reload(self):
        self.reload_header()
        for ed in self.editors.values():
            ed.reload()

    def reload_current(self):
        w = self.currentWidget()
        if isinstance(w, ListEditor):
            w.reload()
        else:
            self.reload_header()

    def reload_header(self):
        old = self.header_area.takeWidget()
        if old:
            old.deleteLater()
        d = self.main.doc
        if d is None:
            self.header_area.setWidget(QLabel("No map open."))
            return
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Section counts are recomputed when saving and cannot be edited here."))
        lay.addWidget(RecordForm(self.main.ctx, d.btl.master, exclude=sorted(COUNT_KEYS)))
        counts = QLabel("  ".join("%s: %d" % (d.btl.master.rt.field(k)[3], d.btl.master[k])
                                  for k in d.btl.master.rt.keys if k in COUNT_KEYS))
        counts.setWordWrap(True)
        lay.addWidget(counts)
        lay.addStretch()
        self.header_area.setWidget(w)
