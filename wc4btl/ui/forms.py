"""Form generator: builds an editor widget for any btl Record from its field list and hints."""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QToolButton, QVBoxLayout, QWidget, QColorDialog, QSizePolicy)

from ..btlfile import RANGES, TECH_KEYS
from ..enums import hint
from ..model import NO_HEX
from . import dialogs

UNKNOWN_RE = re.compile(r"^(u\d+|x\d+|t15|h29|h30)$")

GROUPS = {
    "Troop": [("Unit", ["army", "level", "skin", "formation", "facing", "hp_bonus", "hp", "hp_max", "exp", "mobility",
                        "build_rounds"]),
              ("General", ["general", "rank", "quality", "skill1", "skill2", "skill3", "skill4", "skill5",
                           "medal1", "medal2", "medal3", "v3_medal1", "v3_medal2", "v3_medal3",
                           "ribbon1", "ribbon2", "ribbon3"]),
              ("Orders and state", ["ai", "stronghold", "transport", "morale", "morale_rounds", "move_target",
                                    "scheme", "change_round", "hatred", "trigger", "shield", "hold_dist"])],
    "Reinforcement": [("Unit", ["army", "level", "formation", "transport", "ai", "country", "round"]),
                      ("General", ["general", "rank", "quality", "skill1", "skill2", "skill3", "skill4", "skill5",
                                   "medal1", "medal2", "medal3", "medal4", "medal5", "medal6",
                                   "ribbon1", "ribbon2", "ribbon3"])],
    "City": [("City", ["name", "building", "look", "landmark", "wonder", "stronghold", "hatred", "trigger",
                       "transport"]),
             ("Facilities", ["factory", "lab", "depot", "airport", "missile", "nuke", "aa", "aa_range"]),
             ("Reward and fire", ["reward_type", "reward_amount", "fire_type", "fire_rounds"])],
    "Faction": [("Faction", ["id", "country", "ai", "alliance", "defeat", "strategy_group", "tech_level"]),
                ("Resources", ["money", "industry", "energy", "unit_bonus", "tax_bonus", "atomic", "hydrogen",
                               "triphase", "antimatter"]),
                ("Colour", ["r", "g", "b", "a"]),
                ("Technology levels", TECH_KEYS)],
}

# hints that apply regardless of record type
FIELD_HINTS = {"City": {"name": "cityname"}}


class FormContext:
    def __init__(self, main):
        self.main = main

    @property
    def doc(self):
        return self.main.doc

    @property
    def game(self):
        return self.main.game

    @property
    def images(self):
        return self.main.images

    @property
    def labels(self):
        return self.main.opts.get("labels", "en")

    @property
    def show_unknown(self):
        return self.main.opts.get("unknown", False)

    def changed(self, label):
        self.main.on_doc_changed(label, rebuild_panels=False)


class RecordForm(QWidget):
    edited = Signal(str)

    def __init__(self, ctx, rec, title=None, exclude=(), after_set=None, collapsed=()):
        super().__init__()
        self.ctx, self.rec = ctx, rec
        self.after_set = after_set
        self.editors = {}
        rt = rec.rt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        groups = GROUPS.get(rt.name)
        shown = [k for k in rt.keys if k not in exclude and (ctx.show_unknown or not UNKNOWN_RE.match(k))]
        if groups:
            used = set()
            for gtitle, keys in groups:
                keys = [k for k in keys if k in shown]
                if not keys:
                    continue
                used.update(keys)
                box = QGroupBox(gtitle)
                box.setCheckable(gtitle in collapsed)
                fl = QFormLayout(box)
                fl.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
                for k in keys:
                    self._add_row(fl, k)
                if gtitle == "Colour":
                    self._add_color_button(fl)
                lay.addWidget(box)
                if gtitle in collapsed:
                    box.setChecked(False)
                    self._toggle_box(box, False)
                    box.toggled.connect(lambda on, b=box: self._toggle_box(b, on))
            rest = [k for k in shown if k not in used]
            if rest:
                box = QGroupBox("Other")
                fl = QFormLayout(box)
                for k in rest:
                    self._add_row(fl, k)
                lay.addWidget(box)
        else:
            fl = QFormLayout()
            fl.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
            for k in shown:
                self._add_row(fl, k)
            lay.addLayout(fl)

    @staticmethod
    def _toggle_box(box, on):
        for ch in box.findChildren(QWidget):
            ch.setVisible(on)

    # ------------------------------------------------------------------ rows
    def _label(self, key):
        f = self.rec.rt.field(key)
        text = f[2] if self.ctx.labels == "cn" else f[3]
        lab = QLabel(text)
        lab.setToolTip("%s  |  %s  |  key: %s  (%s)" % (f[3], f[2], key, f[1]))
        return lab

    def _hint(self, key):
        h = FIELD_HINTS.get(self.rec.rt.name, {}).get(key)
        return h or hint(self.rec.rt.name, key)

    def _add_row(self, fl, key):
        w = self._editor(key)
        fl.addRow(self._label(key), w)

    def _set(self, key, value, label=None):
        if self.rec[key] == value:
            return
        self.ctx.doc.begin(tag=(id(self.rec), key))
        self.rec[key] = value
        if key in ("army", "skin") and "skin" in self.editors:
            self._fill_skins()
        if self.after_set:
            self.after_set(self.rec, key)
        self.edited.emit(key)
        self.ctx.changed(label or "Edit %s" % key)

    def refresh_field(self, key):
        """Re-read a value into its editor (used after programmatic changes)."""
        ed = self.editors.get(key)
        if ed is None:
            return
        w, setter = ed
        w.blockSignals(True)
        setter(self.rec[key])
        w.blockSignals(False)

    def _spin(self, key):
        code = self.rec.rt.field(key)[1]
        if code in "fd":
            s = QDoubleSpinBox(); s.setRange(-1e9, 1e9); s.setDecimals(3); s.setSingleStep(0.05)
        else:
            s = QSpinBox()
            lo, hi = RANGES[code]
            s.setRange(max(lo, -2**31), min(hi, 2**31 - 1))
        s.setValue(self.rec[key])
        s.setKeyboardTracking(False)
        s.valueChanged.connect(lambda v: self._set(key, v))
        s.setMinimumWidth(90)
        self.editors[key] = (s, s.setValue)
        return s

    def _combo(self, key, items):
        cb = QComboBox()
        cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(14)
        for val, text in items:
            cb.addItem("%s" % text, val)

        def setter(v):
            k = cb.findData(v)
            if k < 0:
                cb.addItem("%s (unknown value)" % v, v)
                k = cb.count() - 1
            cb.setCurrentIndex(k)
        setter(self.rec[key])
        cb.currentIndexChanged.connect(lambda k: self._set(key, cb.itemData(k)))
        self.editors[key] = (cb, setter)
        return cb

    def _with_button(self, key, label_fn, pick_fn, extra=None):
        box = QWidget()
        h = QHBoxLayout(box); h.setContentsMargins(0, 0, 0, 0)
        s = self._spin(key)
        lab = QLabel(label_fn(self.rec[key]))
        lab.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lab.setWordWrap(True)
        btn = QToolButton(); btn.setText("…"); btn.setToolTip("Search")
        h.addWidget(s); h.addWidget(lab, 1); h.addWidget(btn)
        if extra:
            h.addWidget(extra)

        def on_change(v):
            lab.setText(label_fn(v))
        s.valueChanged.connect(on_change)

        def on_pick():
            v = pick_fn(self.rec[key])
            if v is not None:
                s.setValue(v)
        btn.clicked.connect(on_pick)
        return box

    def _editor(self, key):
        h = self._hint(key)
        game, doc, images = self.ctx.game, self.ctx.doc, self.ctx.images
        if h == "ro":
            lab = QLabel(self._ro_text(key))
            self.editors[key] = (lab, lambda v, k=key, l=lab: l.setText(self._ro_text(k)))
            return lab
        if isinstance(h, tuple) and h[0] == "enum":
            return self._combo(key, [(v, "%d - %s" % (v, t)) for v, t in h[1].items()])
        if h == "faction_id":
            items = [(0, "0 - (none)")] + [(f["id"], doc.faction_label(f)) for f in doc.btl.factions
                                           if f["id"] != 0]
            if any(f["id"] == 0 for f in doc.btl.factions):
                items = [(f["id"], doc.faction_label(f)) for f in doc.btl.factions]
            return self._combo(key, items)
        if h == "victory":
            items = [(k, "%d - %s" % (k, game.text("objective_desc_%d" % k, "?"))) for k in range(17)]
            return self._combo(key, items)
        if h == "building":
            items = [(0, "0 - (none)")] + [(b, "%d - %s" % (b, game.building_name(b))) for b in sorted(game.buildings)]
            return self._combo(key, items)
        if h == "airdefence":
            kinds = {1: "AA machine gun", 2: "AA artillery", 3: "AA missile"}
            items = [(0, "0 - (none)")] + [(a, "%d - %s Lv%d" % (a, kinds.get(r["Type"], "AA"), r["Level"]))
                                           for a, r in sorted(game.air_defence.items())]
            return self._combo(key, items)
        if h == "army":
            return self._with_button(key, lambda v: game.army_name(v, self.rec.get("level", 1) or 1),
                                     lambda cur: dialogs.pick_army(self, game, images, cur))
        if h == "general":
            return self._with_button(key, lambda v: game.general_name(v) if v > 0 else "(none)",
                                     lambda cur: self._pick_general(cur))
        if h == "country":
            return self._with_button(key, game.country_name, lambda cur: dialogs.pick_country(self, game, images, cur))
        if h == "cityname":
            box = QWidget(); hl = QHBoxLayout(box); hl.setContentsMargins(0, 0, 0, 0)
            s = self._spin(key); lab = QLabel(game.city_name(self.rec[key]) or "(no name)")
            s.valueChanged.connect(lambda v: lab.setText(game.city_name(v) or "(no name)"))
            hl.addWidget(s); hl.addWidget(lab, 1)
            return box
        if h == "hex":
            box = QWidget(); hl = QHBoxLayout(box); hl.setContentsMargins(0, 0, 0, 0)
            s = self._spin(key)
            lab = QLabel(self._hex_text(self.rec[key]))
            s.valueChanged.connect(lambda v: lab.setText(self._hex_text(v)))
            go = QToolButton(); go.setText("Go"); go.setToolTip("Show this hex on the map")
            go.clicked.connect(lambda: self._go(self.rec[key]))
            hl.addWidget(s); hl.addWidget(lab, 1); hl.addWidget(go)
            return box
        if h == "skin":
            box = QWidget(); vl = QVBoxLayout(box); vl.setContentsMargins(0, 0, 0, 0)
            cb = QComboBox()
            cb.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            cb.setMinimumContentsLength(14)
            note = QLabel(); note.setWordWrap(True); note.setStyleSheet("color: #777;")
            self._skin_widgets = (cb, note)
            self.editors[key] = (cb, lambda v: self._fill_skins())
            self._fill_skins()
            cb.currentIndexChanged.connect(lambda k: self._set(key, cb.itemData(k)) if k >= 0 else None)
            vl.addWidget(cb); vl.addWidget(note)
            return box
        if h in ("medal", "ribbon"):
            box = QWidget(); hl = QHBoxLayout(box); hl.setContentsMargins(0, 0, 0, 0)
            s = self._spin(key)
            icon = QLabel(); icon.setFixedSize(34, 34)
            text = QLabel()

            def show(v):
                info = game.medal_image(v) if h == "medal" else game.ribbon_image(v)
                pm = images.part(info[0], info[1]) if (info and info[1] and images) else None
                icon.setPixmap(pm[0].scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation) if pm else QPixmap())
                text.setText(info[2] if info else ("" if not v else "(unknown)"))
            show(self.rec[key])
            s.valueChanged.connect(show)
            hl.addWidget(s); hl.addWidget(icon); hl.addWidget(text, 1)
            return box
        return self._spin(key)

    def _fill_skins(self):
        """Skin choices for the troop's current army (EliteSkinSettings + def_motion.xml skin_<n> entries)."""
        cb, note = self._skin_widgets
        game, rec = self.ctx.game, self.rec
        cur = rec["skin"]
        items = [(0, "0 - Default look")] + (game.skins_for(rec["army"]) if game else [])
        if cur not in [v for v, _ in items]:
            items.append((cur, "%d - %s (not defined for this unit)" % (cur, game.skin_name(rec["army"], cur) if game else cur)))
        cb.blockSignals(True)
        cb.clear()
        for v, text in items:
            cb.addItem(text, v)
        cb.setCurrentIndex(cb.findData(cur))
        cb.blockSignals(False)
        if len(items) == 1:
            note.setText("This unit has no skins.")
        elif cur and game and not game.skin_has_sprite(rec["army"], cur):
            note.setText("No \"skin_%d\" sprite in def_motion.xml for this unit: the game shows the default look." % cur)
        else:
            note.setText("Only troops placed in the map wear a skin; reinforcements and recruits always spawn "
                         "with the default look.")

    def _ro_text(self, key):
        v = self.rec[key]
        if key == "hex":
            return "%d  %s" % (v, self._hex_text(v))
        return str(v)

    def _hex_text(self, v):
        doc = self.ctx.doc
        if v in (-1, NO_HEX):
            return "(none)"
        i = doc.local(v & 0xFFFFFFFF if v >= 0 else v)
        if i is None:
            return "(outside map)"
        x, y = doc.xy(i)
        return "(%d, %d)" % (x, y)

    def _go(self, v):
        i = self.ctx.doc.local(v) if v not in (-1, NO_HEX) else None
        if i is not None:
            self.ctx.main.view.center_on_hex(i)

    def _pick_general(self, cur):
        game = self.ctx.game
        gid = dialogs.pick_general(self, game, self.ctx.images, cur)
        if gid is None:
            return None
        g = game.general(gid)
        if g and self.rec.has("rank"):
            # like EModule: copy rank, quality (Hp) and the levels of the first five skills
            self.ctx.doc.begin()
            self.rec["rank"] = g.get("MilitaryRank", 0)
            self.rec["quality"] = g.get("Hp", 0)
            skills = g.get("Skills") or []
            for k in range(5):
                self.rec["skill%d" % (k + 1)] = game.skill_level(skills[k]) if k < len(skills) else 0
            for k in ("rank", "quality", "skill1", "skill2", "skill3", "skill4", "skill5"):
                self.refresh_field(k)
        return gid

    def _add_color_button(self, fl):
        btn = QPushButton("Pick colour…")

        def paint():
            c = QColor(self.rec["r"], self.rec["g"], self.rec["b"])
            btn.setStyleSheet("background:%s; color:%s" % (c.name(), "#000" if c.lightness() > 140 else "#fff"))
        paint()

        def pick():
            c = QColorDialog.getColor(QColor(self.rec["r"], self.rec["g"], self.rec["b"], self.rec["a"]), self,
                                      "Faction colour", QColorDialog.ShowAlphaChannel)
            if c.isValid():
                self.ctx.doc.begin()
                for k, v in (("r", c.red()), ("g", c.green()), ("b", c.blue()), ("a", c.alpha())):
                    self.rec[k] = v
                    self.refresh_field(k)
                paint()
                self.ctx.changed("Faction colour")
        btn.clicked.connect(pick)
        for k in ("r", "g", "b", "a"):
            ed = self.editors.get(k)
            if ed:
                ed[0].valueChanged.connect(lambda *_: paint())
        fl.addRow("", btn)
