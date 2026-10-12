"""Form generator for Glory of Generals 3 tables: one editor per schema field, with game-aware widgets."""
import re

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from wc4btl.ui.dialogs import SearchTable
from ..format import SCALARS, STRUCTS, TABLES, struct_codes

ENUMS = {
    "alliance": {0: "N (none)", 1: "A", 2: "B", 3: "C"},
    "ai": {0: "Normal", 1: "Radical", 2: "Conservative", 3: "Guard", 4: "Escape"},
    "areakey": {0: "Normal", 1: "Primary", 2: "Secondary", 3: "Primary + secondary", 4: "Hidden", 5: "Victory"},
    "bool": {0: "No", 1: "Yes"},
    "style": {1: "Normal", 2: "Snow"},
}
# (table or struct kind, key) -> hint
HINTS = {
    ("s20", "army"): "army", ("s20", "faction"): "faction", ("s20", "hex"): "hex",
    ("s36", "country"): "country", ("s36", "alliance"): "alliance", ("s36", "ai_controlled"): "bool",
    ("s36", "ai?"): "ai", ("s36", "id"): "ro",
    ("s8", "owner"): "faction", ("s8", "building"): "building", ("s8", "style"): "style",
    ("General", "id"): "general", ("ExArmy", "id"): "exarmy", ("Fortification", "type"): "fortification",
    ("Objective", "type"): "objective", ("KeyArea", "key"): "areakey", ("KeyArea", "hex"): "hex",
    ("Area", "hex"): "hex", ("Area", "name"): "cityname", ("Relation", "faction?"): "faction",
    ("AreaOwner", "hex"): "hex", ("AreaOwner", "faction?"): "faction", ("Stack", "hex"): "hex",
    ("ExArmyStock", "exarmy"): "exarmy", ("AIOrder", "target_hex?"): "hex",
    ("s12", "width"): "ro", ("s12", "height"): "ro",
}
LABELS = {"hp": "HP", "max_hp": "Max HP", "ai_controlled": "AI controlled", "ai?": "AI attitude (?)",
          "f16": "f16 (100)", "b10": "b10 (0/1)", "level?": "Level (?)", "next_serial": "Next serial",
          "ai": "AI order", "exarmy": "Elite unit (ExArmy)", "exarmy_pool?": "Elite unit pool (?)",
          "tech?": "Tech levels (?)", "round_limit?": "Round limit (?)"}
UNKNOWN_RE = re.compile(r"^(f\d+|b\d+)$")
RANGE = {"u8": (0, 255), "u16": (0, 65535), "u32": (0, 2 ** 32 - 1), "u64": (0, 2 ** 63 - 1)}


def label_for(key):
    if key in LABELS:
        return LABELS[key]
    q = key.endswith("?")
    k = key.rstrip("?").replace("_", " ")
    return k[:1].upper() + k[1:] + (" (?)" if q else "")


def is_unknown(key):
    return bool(UNKNOWN_RE.match(key.rstrip("?")))


def pick(parent, title, choices, current=None):
    rows = [(k, [k, text.split("  ", 1)[-1]], None) for k, text in choices]
    dlg = SearchTable(parent, title, ["Id", "Name"], rows, current)
    return dlg.result if dlg.exec() else None


class DictForm(QWidget):
    """Editor for one table dict.  Optional sub-tables get a checkbox that adds or removes them."""
    edited = Signal(str)
    structure = Signal()          # a sub-table was added/removed: the owner should rebuild

    def __init__(self, ctx, obj, table, exclude=(), title=None, nested=True):
        super().__init__()
        self.ctx, self.obj, self.table = ctx, obj, table
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        main = QGroupBox(title) if title else QWidget()
        fl = QFormLayout(main)
        other = QGroupBox("Unidentified fields (meaning unknown, type exact)")
        ofl = QFormLayout(other)
        subs = []
        for i, key, kind in TABLES[table]:
            if key in exclude:
                continue
            target = ofl if is_unknown(key) else fl
            if kind in SCALARS:
                target.addRow(label_for(key), self.scalar(obj, key, kind, HINTS.get((table, key))))
            elif kind in STRUCTS:
                self.struct_rows(fl, ofl, obj, key, kind)
            elif kind == "str":
                e = QLineEdit(obj.get(key, ""))
                e.textEdited.connect(lambda t, k=key: self.set(obj, k, t, "Edit %s" % k))
                target.addRow(label_for(key), e)
            elif kind.startswith("[") and kind[1:-1] in SCALARS:
                target.addRow(label_for(key), self.vector(obj, key, kind))
            elif kind.startswith("["):
                target.addRow(label_for(key), self.table_list(obj, key, kind[1:-1]))
            elif nested:
                subs.append((key, kind))
        lay.addWidget(main)
        for key, kind in subs:
            lay.addWidget(self.subtable(obj, key, kind))
        if ofl.rowCount() and ctx.show_unknown:
            lay.addWidget(other)
        else:
            other.deleteLater()
        lay.addStretch()

    # ------------------------------------------------------------------ editing
    def set(self, obj, key, value, label):
        doc = self.ctx.doc
        if doc is None:
            return
        doc.begin(("form", id(obj), key))
        obj[key] = value
        doc.reindex()
        self.edited.emit(key)
        self.ctx.changed(label)

    # ------------------------------------------------------------------ widgets
    def scalar(self, obj, key, kind, hint, part_of=None):
        """Editor for obj[key] (a table field, or a struct part when part_of is the struct kind)."""
        cur = obj.get(key, 0)
        game, doc = self.ctx.game, self.ctx.doc
        if hint == "ro":
            return QLabel(str(cur))
        if hint in ENUMS:
            return self.combo(obj, key, list(ENUMS[hint].items()), cur)
        if hint == "faction" and doc is not None:
            return self.combo(obj, key, [(f, doc.faction_label(f)) for f in doc.faction_ids()], cur)
        if hint in ("army", "exarmy", "general", "country", "building", "fortification", "objective") and game:
            return self.combo(obj, key, game.choices(hint), cur, searchable=hint in ("general", "exarmy", "country"))
        if hint == "cityname" and game:
            names = sorted((int(k[16:]), v) for k, v in game.strings.items()
                           if k.startswith("battle_cityname_") and k[16:].isdigit())
            return self.combo(obj, key, [(0, "(none)")] + [(n, "%d  %s" % (n, t)) for n, t in names], cur, searchable=True)
        lo, hi = RANGE[kind]
        if kind in ("u32", "u64") or hi > 2 ** 31 - 1:
            sp = QDoubleSpinBox(); sp.setDecimals(0); sp.setRange(lo, min(hi, 2 ** 53))
        else:
            sp = QSpinBox(); sp.setRange(lo, hi)
        sp.setValue(cur)
        sp.valueChanged.connect(lambda v, k=key: self.set(obj, k, int(v), "Edit %s" % k))
        if hint == "hex" and doc is not None:
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
            h.addWidget(sp)
            note = QLabel()

            def show(v):
                v = int(v)
                note.setText("(none)" if v == 0xFFFF else "(%d, %d)" % doc.xy(v) if v < doc.n else "(outside map)")
            show(cur)
            sp.valueChanged.connect(show)
            h.addWidget(note)
            return w
        return sp

    def combo(self, obj, key, items, cur, searchable=False):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        cb = QComboBox()
        keys = [k for k, _ in items]
        if cur not in keys:
            items = list(items) + [(cur, "%s  (not in game data)" % cur)]
        for k, text in items:
            cb.addItem(text, k)
        cb.setCurrentIndex(cb.findData(cur))
        cb.setMaxVisibleItems(25)
        cb.currentIndexChanged.connect(lambda _i, k=key: self.set(obj, k, cb.currentData(), "Edit %s" % k))
        h.addWidget(cb, 1)
        if searchable:
            b = QPushButton("…"); b.setFixedWidth(28)

            def do_pick():
                r = pick(self, "Choose", items, cb.currentData())
                if r is not None:
                    cb.setCurrentIndex(cb.findData(r))
            b.clicked.connect(do_pick)
            h.addWidget(b)
        return w

    def struct_rows(self, fl, ofl, obj, key, kind):
        names = STRUCTS[kind][1]
        st = obj.get(key)
        if st is None:
            return
        for name, code in zip(names, struct_codes(kind)):
            target = ofl if is_unknown(name) else fl
            if code == "f":
                sp = QDoubleSpinBox(); sp.setDecimals(4); sp.setRange(-1e6, 1e6); sp.setSingleStep(0.05)
                sp.setValue(st[name])
                sp.valueChanged.connect(lambda v, n=name: self.set(st, n, float(v), "Edit %s" % n))
                target.addRow(label_for(name), sp)
            else:
                sk = {"B": "u8", "H": "u16", "I": "u32"}[code]
                target.addRow(label_for(name), self.scalar(st, name, sk, HINTS.get((kind, name))))
        if kind == "s36":
            fl.addRow("Colour", self.color_button(st))

    def color_button(self, st):
        b = QPushButton()

        def paint():
            pm = QPixmap(40, 14); pm.fill(QColor(st["r"], st["g"], st["b"]))
            b.setIcon(QIcon(pm)); b.setText(" %d, %d, %d, %d" % (st["r"], st["g"], st["b"], st["a"]))

        def choose():
            c = QColorDialog.getColor(QColor(st["r"], st["g"], st["b"], st["a"]), self, "Faction colour",
                                      QColorDialog.ShowAlphaChannel)
            if c.isValid():
                self.ctx.doc.begin()
                st.update(r=c.red(), g=c.green(), b=c.blue(), a=c.alpha())
                paint()
                self.structure.emit()
                self.ctx.changed("Faction colour")
        paint()
        b.clicked.connect(choose)
        return b

    def vector(self, obj, key, kind):
        vals = obj.get(key)
        if vals is not None and len(vals) > 64:
            return QLabel("%d values (edit through Data > JSON)" % len(vals))
        e = QLineEdit(", ".join(str(v) for v in (vals or [])))
        e.setPlaceholderText("comma-separated numbers")
        lo, hi = RANGE[kind[1:-1]]

        def commit():
            try:
                new = [int(x) for x in re.split(r"[,\s]+", e.text().strip()) if x]
            except ValueError:
                e.setStyleSheet("background:#fcc"); return
            if any(not lo <= v <= hi for v in new):
                e.setStyleSheet("background:#fcc"); return
            e.setStyleSheet("")
            if new != obj.get(key):
                self.set(obj, key, new, "Edit %s" % key)
        e.editingFinished.connect(commit)
        return e

    def table_list(self, obj, key, sub):
        vals = obj.get(key)
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0)
        lab = QLabel("%d item(s)" % len(vals or []))
        h.addWidget(lab)
        b = QPushButton("Edit…")

        def open_editor():
            from .datapanel import ListEditor
            dlg = QDialog(self); dlg.setWindowTitle(label_for(key)); dlg.resize(560, 620)
            v = QVBoxLayout(dlg)
            ed = ListEditor(self.ctx, lambda create: obj.setdefault(key, []) if create else obj.get(key), sub)
            v.addWidget(ed)
            bb = QDialogButtonBox(QDialogButtonBox.Close); bb.rejected.connect(dlg.accept); v.addWidget(bb)
            dlg.exec()
            lab.setText("%d item(s)" % len(obj.get(key) or []))
            self.structure.emit()
        b.clicked.connect(open_editor)
        h.addWidget(b)
        h.addStretch()
        return w

    def subtable(self, obj, key, kind):
        box = QGroupBox(label_for(key))
        box.setCheckable(True)
        present = isinstance(obj.get(key), dict)
        box.setChecked(present)
        v = QVBoxLayout(box)
        if present:
            f = DictForm(self.ctx, obj[key], kind)
            f.edited.connect(self.edited.emit)
            f.structure.connect(self.structure.emit)
            v.addWidget(f)
        else:
            v.addWidget(QLabel("Not set. Tick the box to add it."))

        def toggled(on):
            doc = self.ctx.doc
            doc.begin()
            if on:
                obj[key] = default_table(kind, self.ctx)
            else:
                obj.pop(key, None)
            doc.reindex()
            self.ctx.changed(("Add " if on else "Remove ") + label_for(key))
            self.structure.emit()
        box.toggled.connect(toggled)
        return box


def default_table(kind, ctx=None):
    """A new table with sensible starting values."""
    if kind == "General":
        return {"id": 1001, "level?": 1}
    if kind == "ExArmy":
        return {"id": 401, "level": 1, "f4": 100}
    if kind == "Building":
        owner = next(iter(ctx.doc.factions), 1) if ctx and ctx.doc else 1
        return {"info": {"owner": owner, "building": 101, "style": 1, "variant": 0, "f6": 0}}
    if kind == "Fortification":
        return {"type": 2}
    if kind == "AIOrder":
        return {"mode?": 3}
    out = {}
    for _, key, k in TABLES[kind]:
        if k in STRUCTS:
            names = STRUCTS[k][1]
            out[key] = {n: (0.0 if c == "f" else 0) for n, c in zip(names, struct_codes(k))}
    return out
