"""Whole-map data for Glory of Generals 3: objectives, factions, key areas, groups, off-map armies, weather,
map settings, and a JSON editor for any section."""
import json
import marshal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QTabWidget, QVBoxLayout, QWidget)

from ..format import NO_HEX, TABLES, FormatError, write
from .forms import DictForm, default_table


def summary(ctx, kind, r, k):
    doc, game = ctx.doc, ctx.game
    try:
        if kind == "Objective":
            return "%s   target %s   rounds %s" % (game.objective_text(r.get("type", 0)).replace("{0}", "…"),
                                                    r.get("target", 0), r.get("rounds?", "-"))
        if kind == "Country":
            return doc.faction_label(r["info"]["id"])
        if kind == "KeyArea":
            return "(%d, %d)  key %d" % (doc.xy(r.get("hex", 0)) + (r.get("key", 0),))
        if kind == "Group":
            return "group %d: %d unit(s)" % (r.get("id", 0), len(r.get("serials", [])))
        if kind == "Army":
            i = r["info"]
            return "#%d %s  [%s]" % (i["serial"], game.army_name(i["army"]), doc.faction_label(i["faction"]))
        if kind == "Weather":
            return "type %d from round %d for %d" % (r.get("type", 0), r.get("round", 0), r.get("duration", 0))
        if kind == "Area":
            return "(%d, %d) %s" % (doc.xy(r.get("hex", 0)) + (game.city_name(r.get("name", 0)),))
    except (KeyError, TypeError, AttributeError):
        pass
    vals = ["%s=%s" % (key, r[key]) for _, key, kd in TABLES[kind] if key in r and not isinstance(r[key], (dict, list))]
    return "#%d  %s" % (k, "  ".join(vals[:4]))


class ListEditor(QWidget):
    """List of tables of one kind: add / copy / delete / reorder, and a form for the selected item."""

    def __init__(self, ctx, getter, kind, filt=None, on_change=None):
        super().__init__()
        self.ctx, self.getter, self.kind, self.filt, self.on_change = ctx, getter, kind, filt, on_change
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Vertical)
        top = QWidget(); tl = QVBoxLayout(top); tl.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.show_row)
        tl.addWidget(self.list)
        row = QHBoxLayout()
        for text, fn in (("Add", self.add), ("Copy", self.copy), ("Delete", self.delete), ("Up", lambda: self.move(-1)),
                         ("Down", lambda: self.move(1))):
            b = QPushButton(text); b.clicked.connect(fn); row.addWidget(b)
        tl.addLayout(row)
        self.area = QScrollArea(); self.area.setWidgetResizable(True)
        split.addWidget(top); split.addWidget(self.area)
        split.setSizes([200, 600]); split.setChildrenCollapsible(False)
        lay.addWidget(split)
        self.reload()

    def rows(self):
        rows = self.getter(False)
        if rows is None:
            return []
        return [r for r in rows if self.filt is None or self.filt(r)]

    def reload(self, keep=None):
        cur = self.list.currentRow() if keep is None else keep
        self.list.blockSignals(True)
        self.list.clear()
        for k, r in enumerate(self.rows()):
            it = QListWidgetItem(summary(self.ctx, self.kind, r, k))
            if self.kind == "Country" and self.ctx.doc:
                pm = QPixmap(14, 14); pm.fill(QColor(*self.ctx.doc.faction_rgb(r["info"]["id"])))
                it.setIcon(QIcon(pm))
            self.list.addItem(it)
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(max(0, min(cur, self.list.count() - 1)))
        self.show_row(self.list.currentRow())

    def show_row(self, k):
        old = self.area.takeWidget()
        if old:
            old.deleteLater()
        rows = self.rows()
        if not 0 <= k < len(rows):
            self.area.setWidget(QLabel("Nothing selected."))
            return
        rec = rows[k]
        form = DictForm(self.ctx, rec, self.kind)
        form.edited.connect(lambda _key, k=k: self.list.item(k) and self.list.item(k).setText(summary(self.ctx, self.kind, rec, k)))
        form.structure.connect(lambda k=k: self.reload(k))
        self.area.setWidget(form)

    def _changed(self, label, keep):
        self.ctx.doc.reindex()
        self.ctx.changed(label)
        if self.on_change:
            self.on_change()
        self.reload(keep)

    def _list(self):
        return self.getter(True)

    def add(self):
        doc = self.ctx.doc
        if doc is None or self._list() is None:
            return
        doc.begin()
        if self.kind == "Army":
            doc.new_army(NO_HEX)
        elif self.kind == "Country":
            ids = doc.faction_ids()
            new = default_table("Country")
            new["info"].update(id=max(ids + [0]) + 1, country=1, alliance=1, ai_controlled=1, rate_a=1.0, rate_b=1.0,
                               rate_c=1.0, r=128, g=128, b=128, a=128)
            new["tech?"] = [0, 0, 0, 0, 0]
            self._list().append(new)
        elif self.kind == "Group":
            ids = [g.get("id", 0) for g in self._list()]
            self._list().append({"id": max(ids + [0]) + 1, "serials": []})
        elif self.kind == "Objective":
            self._list().append({"type": 0, "target": 0, "rounds?": 10})
        elif self.kind == "Weather":
            self._list().append({"type": 1, "round": 1, "duration": 1})
        elif self.kind == "KeyArea":
            self._list().append({"hex": 0, "f1": 1, "key": 1})
        else:
            self._list().append(default_table(self.kind, self.ctx))
        self._changed("Add", len(self.rows()) - 1)

    def copy(self):
        rows = self.rows()
        k = self.list.currentRow()
        if not 0 <= k < len(rows):
            return
        doc = self.ctx.doc
        doc.begin()
        if self.kind == "Army":
            doc.new_army(NO_HEX, template=rows[k])
        else:
            c = marshal.loads(marshal.dumps(rows[k]))
            if self.kind == "Country":
                c["info"]["id"] = max(doc.faction_ids() + [0]) + 1
            self._list().append(c)
        self._changed("Copy", len(self.rows()) - 1)

    def delete(self):
        rows = self.rows()
        k = self.list.currentRow()
        if not 0 <= k < len(rows):
            return
        if QMessageBox.question(self, "Delete", "Delete '%s'?" % self.list.item(k).text()) != QMessageBox.Yes:
            return
        self.ctx.doc.begin()
        self._list().remove(rows[k])
        self._changed("Delete", k)

    def move(self, delta):
        rows = self.rows()
        k = self.list.currentRow()
        j = k + delta
        if not (0 <= k < len(rows) and 0 <= j < len(rows)):
            return
        lst = self._list()
        a, b = lst.index(rows[k]), lst.index(rows[j])
        self.ctx.doc.begin()
        lst[a], lst[b] = lst[b], lst[a]
        self._changed("Move", j)


class JsonEditor(QWidget):
    """Edit any top-level section as JSON (covers every field, including unidentified ones)."""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.section = QComboBox()
        for _, key, _ in TABLES["Battle"]:
            self.section.addItem(key)
        self.section.currentIndexChanged.connect(self.load)
        row.addWidget(QLabel("Section")); row.addWidget(self.section, 1)
        b = QPushButton("Apply"); b.clicked.connect(self.apply); row.addWidget(b)
        b = QPushButton("Revert"); b.clicked.connect(self.load); row.addWidget(b)
        lay.addLayout(row)
        self.edit = QPlainTextEdit()
        self.edit.setFont(QFont("Consolas", 9))
        self.edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        lay.addWidget(self.edit)
        note = QLabel("Field names follow docs/gog3-btl-format.md. Large per-hex arrays are on one line each.")
        note.setWordWrap(True)
        lay.addWidget(note)

    def load(self, *_):
        doc = self.ctx.doc
        if doc is None:
            self.edit.setPlainText("")
            return
        key = self.section.currentText()
        val = doc.b.get(key)
        text = json.dumps(val, ensure_ascii=False, indent=1)
        if len(text) > 400000:
            text = json.dumps(val, ensure_ascii=False)
        self.edit.setPlainText(text)

    def apply(self):
        doc = self.ctx.doc
        if doc is None:
            return
        key = self.section.currentText()
        try:
            val = json.loads(self.edit.toPlainText()) if self.edit.toPlainText().strip() else None
            test = dict(doc.b)
            if val is None:
                test.pop(key, None)
            else:
                test[key] = val
            write(test)
        except (ValueError, FormatError, KeyError, TypeError, OverflowError) as e:
            QMessageBox.warning(self, "Not applied", "This JSON cannot be saved as a map:\n%s" % e)
            return
        snap = doc.snapshot()
        doc.begin()
        if val is None:
            doc.b.pop(key, None)
        else:
            doc.b[key] = val
        try:
            doc._setup()
        except Exception as e:  # noqa: BLE001 - restore and report
            doc._restore(snap)
            doc.undo_stack.pop()
            QMessageBox.warning(self, "Not applied", str(e))
            return
        self.ctx.main._after_history("Edit %s (JSON)" % key)


class Gog3DataPanel(QTabWidget):
    def __init__(self, main, ctx):
        super().__init__()
        self.main, self.ctx = main, ctx
        self.specs = [
            ("Objectives", lambda c: self.sub("objectives", "list", c), "Objective", None),
            ("Factions", lambda c: self.sub("countries", "list", c), "Country", None),
            ("Key areas", lambda c: self.sub("key_areas", "list", c), "KeyArea", None),
            ("Groups", lambda c: self.sub("armies", "groups", c), "Group", None),
            ("Off-map units", lambda c: self.sub("armies", "list", c), "Army", lambda a: a["info"]["hex"] == NO_HEX),
            ("Weather", lambda c: self.sub("weather", "list", c), "Weather", None),
        ]
        self.settings = QScrollArea(); self.settings.setWidgetResizable(True)
        self.addTab(self.settings, "Map")
        self.editors = []
        for title, getter, kind, filt in self.specs:
            holder = QWidget(); QVBoxLayout(holder).setContentsMargins(0, 0, 0, 0)
            self.addTab(holder, title)
            self.editors.append((holder, getter, kind, filt))
        self.json = JsonEditor(ctx)
        self.addTab(self.json, "JSON")
        self.currentChanged.connect(lambda *_: self.reload_current())

    def sub(self, section, key, create=False):
        doc = self.ctx.doc
        if doc is None:
            return None
        if create:
            return doc.b.setdefault(section, {}).setdefault(key, [])
        return doc.b.get(section, {}).get(key)

    def reload(self):
        self.reload_current()

    def reload_current(self):
        w = self.currentWidget()
        if w is self.settings:
            self.reload_settings()
        elif w is self.json:
            self.json.load()
        else:
            for holder, getter, kind, filt in self.editors:
                if holder is w:
                    lay = holder.layout()
                    while lay.count():
                        old = lay.takeAt(0).widget()
                        if old:
                            old.deleteLater()
                    if self.ctx.doc is None:
                        lay.addWidget(QLabel("No map open."))
                    else:
                        lay.addWidget(ListEditor(self.ctx, getter, kind, filt))

    def reload_settings(self):
        old = self.settings.takeWidget()
        if old:
            old.deleteLater()
        doc = self.ctx.doc
        if doc is None:
            self.settings.setWidget(QLabel("No map open."))
            return
        w = QWidget(); lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Width and height are fixed here (the per-hex arrays depend on them)."))
        lay.addWidget(DictForm(self.ctx, doc.b["map"], "MapInfo", title="Map"))
        for key, kind, title in (("objectives", "Objectives", "Objectives"), ("armies", "Armies", "Armies")):
            if isinstance(doc.b.get(key), dict):
                lay.addWidget(DictForm(self.ctx, doc.b[key], kind, title=title, exclude=("list", "groups")))
        info = QLabel("Version %s.  AI behaviour tree: %d bytes (FlexBuffers).  Trigger data: %d bytes.  "
                      "Stage trigger scripts live in assets/luac/trigger/." % (
                          doc.b.get("version"), len(doc.b.get("ai_tree", [])),
                          len(doc.b.get("triggers", {}).get("data", []))))
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addStretch()
        self.settings.setWidget(w)
