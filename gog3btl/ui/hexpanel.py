"""Per-hex editing for Glory of Generals 3: terrain bits and overlays, area (city / building / fortification /
key area) and army."""
import marshal

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ..format import HEX_DISABLED, HEX_FLAG3, HEX_SEA, HEX_SEA_FLAG2
from ..gamedata import GROUND_NAMES
from .forms import DictForm

FLAG_BITS = [(HEX_DISABLED, "Disabled (outside the battlefield)"), (HEX_SEA, "Sea"),
             (HEX_SEA_FLAG2, "Sea flag 0x2000 (unknown)"), (HEX_FLAG3, "Flag 0x4000 (unknown)")]
LAYER_TITLES = {"A": "Layer A: decoration (0x400)", "B": "Layer B: main terrain (0x800)",
                "C": "Layer C: upper sprites (0x1000)"}


class Gog3HexPanel(QTabWidget):
    def __init__(self, main, ctx):
        super().__init__()
        self.main, self.ctx = main, ctx
        self.i = None
        self.clipboard = None
        self.pages = []
        for title, fn in (("Terrain", self.page_terrain), ("Area", self.page_area), ("Army", self.page_army)):
            area = QScrollArea(); area.setWidgetResizable(True)
            self.addTab(area, title)
            self.pages.append((area, fn))
        self.rebuild()

    @property
    def doc(self):
        return self.main.doc

    def set_hex(self, i):
        self.i = i
        self.rebuild()

    def rebuild(self):
        for area, fn in self.pages:
            old = area.takeWidget()
            if old:
                old.deleteLater()
            w = QWidget()
            lay = QVBoxLayout(w)
            if self.doc is None or self.i is None or self.i >= self.doc.n:
                lay.addWidget(QLabel("Click a hex on the map."))
            else:
                fn(lay)
            lay.addStretch()
            area.setWidget(w)
        self.update_titles()

    def update_titles(self):
        d, i = self.doc, self.i
        has = d is not None and i is not None and i < d.n
        self.setTabText(1, "• Area" if has and i in d.area_at else "Area")
        self.setTabText(2, "• Army" if has and i in d.army_at else "Army")

    def act(self, label, fn):
        self.doc.begin()
        fn()
        self.doc.reindex()
        self.main.on_doc_changed(label)

    # ------------------------------------------------------------------ terrain
    def page_terrain(self, lay):
        d, game, i = self.doc, self.main.game, self.i
        x, y = d.xy(i)
        v = d.hexval(i)
        t = d.terrain_type(i)
        info = QLabel("<b>Hex (%d, %d)</b>, index %d, raw value 0x%04x<br>Terrain type: %s" % (
            x, y, i, v, game.terrain_type_name(t) if game else t))
        lay.addWidget(info)
        if d.province is not None:
            p = d.province[i]
            lay.addWidget(QLabel("Province: %s" % ("none" if p == 0xFFFF else "area at (%d, %d)" % d.xy(p))))
        box = QGroupBox("Ground and flags")
        fl = QFormLayout(box)
        ground = QComboBox()
        for k, name in GROUND_NAMES.items():
            ground.addItem("%d  %s" % (k, name), k)
        ground.setCurrentIndex(ground.findData(v & 7) if ground.findData(v & 7) >= 0 else 0)
        ground.currentIndexChanged.connect(lambda _: self.set_bits(0x7, ground.currentData(), "Ground"))
        fl.addRow("Ground", ground)
        tile = QSpinBox(); tile.setRange(0, 31); tile.setValue((v >> 3) & 31)
        tile.valueChanged.connect(lambda n: self.set_bits(0xF8, n << 3, "Ground tile"))
        fl.addRow("Ground tile variant", tile)
        for bit, text in FLAG_BITS:
            cb = QCheckBox(text); cb.setChecked(bool(v & bit))
            cb.toggled.connect(lambda on, b=bit: self.set_bits(b, b if on else 0, "Hex flag"))
            fl.addRow(cb)
        lay.addWidget(box)
        for layer in ("A", "B", "C"):
            lay.addWidget(self.layer_box(layer))

    def set_bits(self, mask, value, label):
        d, i = self.doc, self.i
        d.begin(("hex", i, mask))
        d.set_hexval(i, (d.hexval(i) & ~mask) | value)
        self.main.on_doc_changed(label, rebuild_panels=False)

    def layer_box(self, layer):
        d, game, i = self.doc, self.main.game, self.i
        o = d.overlay(i, layer)
        box = QGroupBox(LAYER_TITLES[layer])
        box.setCheckable(True)
        box.setChecked(o is not None)
        fl = QFormLayout(box)
        o = o or {"terrain": 0, "tile": 0, "dx": 0, "dy": 0}
        terr = QComboBox()
        terr.addItem("0  (none)", 0)
        for tid, text in (game.choices("terrain") if game else []):
            terr.addItem(text, tid)
        if terr.findData(o["terrain"]) < 0:
            terr.addItem("%d  (unknown)" % o["terrain"], o["terrain"])
        terr.setCurrentIndex(terr.findData(o["terrain"]))
        tile = QSpinBox(); tile.setRange(0, 255); tile.setValue(o["tile"])
        dx = QSpinBox(); dx.setRange(-128, 127); dx.setValue(o["dx"])
        dy = QSpinBox(); dy.setRange(-128, 127); dy.setValue(o["dy"])
        name = QLabel()

        def show():
            sp = game.sprite(terr.currentData(), tile.value()) if game else None
            n = len((game.terrains.get(terr.currentData()) or {}).get("tiles", {})) if game else 0
            name.setText("%s  (%d tiles)" % (sp[1] if sp else "no sprite", n))

        def commit(*_):
            if not box.isChecked():
                return
            d.begin(("overlay", i, layer))
            d.set_overlay(i, layer, {"terrain": terr.currentData(), "tile": tile.value(), "dx": dx.value(), "dy": dy.value()})
            show()
            self.main.on_doc_changed("Terrain overlay", rebuild_panels=False)

        def toggled(on):
            d.begin()
            d.set_overlay(i, layer, {"terrain": terr.currentData(), "tile": tile.value(), "dx": dx.value(), "dy": dy.value()}
                          if on else None)
            self.main.on_doc_changed("Terrain layer %s %s" % (layer, "on" if on else "off"), rebuild_panels=False)
        show()
        terr.currentIndexChanged.connect(commit)
        for sp in (tile, dx, dy):
            sp.valueChanged.connect(commit)
        box.toggled.connect(toggled)
        fl.addRow("Terrain", terr)
        fl.addRow("Tile", tile)
        fl.addRow("Sprite", name)
        off = QWidget(); h = QHBoxLayout(off); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("dx")); h.addWidget(dx); h.addWidget(QLabel("dy")); h.addWidget(dy)
        fl.addRow("Offset (px)", off)
        return box

    # ------------------------------------------------------------------ area
    def page_area(self, lay):
        d, i = self.doc, self.i
        k = d.key_at.get(i)
        key = QGroupBox("Key area (objectives)")
        key.setCheckable(True); key.setChecked(k is not None)
        kl = QFormLayout(key)
        if k is not None:
            kl.addRow(DictForm(self.ctx, k, "KeyArea", exclude=("hex",)))
        else:
            kl.addRow(QLabel("Tick to make this hex a key area."))
        key.toggled.connect(lambda on: self.act("Key area", (lambda: d.add_key_area(i)) if on else (lambda: d.delete_key_area(i))))
        lay.addWidget(key)
        a = d.area_at.get(i)
        if a is None:
            lay.addWidget(QLabel("No area on this hex. Areas hold cities, buildings and fortifications; Lua triggers "
                                 "refer to them by hex."))
            b = QPushButton("Add area"); b.clicked.connect(lambda: self.act("Add area", lambda: d.add_area(i)))
            lay.addWidget(b)
            return
        b = QPushButton("Delete area"); b.clicked.connect(lambda: self.act("Delete area", lambda: d.delete_area(i)))
        lay.addWidget(b)
        form = DictForm(self.ctx, a, "Area", exclude=("hex",))
        form.structure.connect(self.rebuild)
        lay.addWidget(form)

    # ------------------------------------------------------------------ army
    def page_army(self, lay):
        d, game, i = self.doc, self.main.game, self.i
        a = d.army_at.get(i)
        row = QHBoxLayout()
        if a is None:
            fac = QComboBox()
            for f in d.faction_ids():
                fac.addItem(d.faction_label(f), f)
            army = QComboBox()
            for k, text in (game.choices("army") if game else [(101, "101")]):
                army.addItem(text, k)
            form = QFormLayout()
            form.addRow("Faction", fac); form.addRow("Army", army)
            lay.addLayout(form)
            b = QPushButton("Add army")
            b.clicked.connect(lambda: self.act("Add army", lambda: d.new_army(i, fac.currentData(), army.currentData())))
            row.addWidget(b)
            p = QPushButton("Paste army")
            p.setEnabled(self.clipboard is not None)
            p.clicked.connect(lambda: self.act("Paste army", lambda: d.new_army(i, template=marshal.loads(self.clipboard))))
            row.addWidget(p)
            lay.addLayout(row)
            return
        c = QPushButton("Copy army"); c.clicked.connect(lambda: self.copy(a)); row.addWidget(c)
        x = QPushButton("Delete army"); x.clicked.connect(lambda: self.act("Delete army", lambda: d.delete_army(i)))
        row.addWidget(x)
        hp = QPushButton("Recalculate HP"); hp.clicked.connect(lambda: self.act("Recalculate HP", lambda: self.recalc(a)))
        hp.setToolTip("HP = ArmySettings HP x number of sub-units (general and elite bonuses not included)")
        row.addWidget(hp)
        lay.addLayout(row)
        groups = [g.get("id") for g in d.b.get("armies", {}).get("groups", []) if a["info"]["serial"] in g.get("serials", [])]
        lay.addWidget(QLabel("Serial %d%s. Lua triggers and ReinforcementSettings refer to units by serial." % (
            a["info"]["serial"], ", in group %s" % ", ".join(map(str, groups)) if groups else "")))
        form = DictForm(self.ctx, a, "Army")
        form.structure.connect(self.rebuild)
        lay.addWidget(form)

    def copy(self, a):
        self.clipboard = marshal.dumps(a)
        self.main.statusBar().showMessage("Army copied", 2000)

    def recalc(self, a):
        g = self.main.game
        info = a["info"]
        hp = g.army_hp(info["army"]) * max(1, info["number"]) if g else info["max_hp"]
        info["hp"] = info["max_hp"] = hp
