"""Per-hex inspector (EModule's 'single' panels): land, city, city HP, troop, mine, reinforcements, air raids,
capital and deploy slots of the selected hex."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget, QComboBox, QFrame)

from ..model import NO_HEX, NO_OWNER
from . import dialogs
from .forms import RecordForm

TABS = ["Land", "City", "City HP", "Troop", "Mine", "Reinforcements", "Air raids", "Capital / deploy"]


class HexPanel(QTabWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.ctx = main.ctx
        self.hex = None
        self.clip = {}           # copy buffers: troop (record, owner), city, reinforcement, airraid
        self.pages = []
        for t in TABS:
            sa = QScrollArea(); sa.setWidgetResizable(True)
            self.addTab(sa, t)
            self.pages.append(sa)
        self.currentChanged.connect(lambda *_: self.rebuild())

    # ------------------------------------------------------------------ helpers
    @property
    def doc(self):
        return self.main.doc

    def set_hex(self, i):
        self.hex = i
        self.rebuild()

    def rebuild(self):
        k = self.currentIndex()
        for j, page in enumerate(self.pages):
            if j != k:
                old = page.takeWidget()
                if old:
                    old.deleteLater()
                page.setWidget(QWidget())
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignTop)
        if self.doc is None or self.hex is None:
            lay.addWidget(QLabel("Click a hex on the map."))
        else:
            [self.page_land, self.page_city, self.page_cityhp, self.page_troop, self.page_mine,
             self.page_reinf, self.page_airraid, self.page_capital][k](lay)
        old = self.pages[k].takeWidget()
        if old:
            old.deleteLater()
        self.pages[k].setWidget(w)
        self.update_titles()

    def update_titles(self):
        d, i = self.doc, self.hex
        if d is None or i is None:
            for k, t in enumerate(TABS):
                self.setTabText(k, t)
            return
        marks = [True, i in d.city_at, i in d.cityhp_at, i in d.troop_at, i in d.mine_at, bool(d.reinf_at.get(i)),
                 bool(d.airraid_at.get(i)), i in d.capital_at or bool(d.deploy_at.get(i))]
        for k, t in enumerate(TABS):
            self.setTabText(k, ("● " if marks[k] and k else "") + t)

    def buttons(self, lay, specs):
        row = QHBoxLayout()
        for text, fn, enabled in specs:
            b = QPushButton(text)
            b.setEnabled(bool(enabled))
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

    def act(self, label, fn, structural=True):
        self.doc.begin()
        fn()
        self.main.on_doc_changed(label, rebuild_panels=structural)

    # ------------------------------------------------------------------ land
    def page_land(self, lay):
        d, g, i = self.doc, self.main.game, self.hex
        x, y = d.xy(i)
        t = d.terrain(i)
        box = QGroupBox("Hex")
        fl = QFormLayout(box)
        fl.addRow("Position (x, y)", QLabel("%d, %d" % (x, y)))
        fl.addRow("Local index", QLabel(str(i)))
        fl.addRow("File hex id", QLabel(str(d.file_hex(i)) + ("   (world grid)" if d.world else "")))
        tinfo = "%s  (terrain %d, tile %d)" % (g.terrain_name(t["terrain"]), t["terrain"], t["tile"])
        if t["a_terrain"] not in (63, 255):
            tinfo += "  + decor %d/%d" % (t["a_terrain"], t["a_tile"])
        if t["b_terrain"] not in (63, 255):
            tinfo += "  + decor %d/%d" % (t["b_terrain"], t["b_tile"])
        fl.addRow("Terrain", QLabel(tinfo))
        lay.addWidget(box)

        box = QGroupBox("Province (which city this hex belongs to)")
        fl = QFormLayout(box)
        s = QSpinBox(); s.setRange(0, 65535); s.setValue(d.province(i)); s.setKeyboardTracking(False)
        p = d.local(d.province(i))
        plab = QLabel("(none)" if p is None else "hex (%d, %d)%s" % (d.xy(p) + (
            ("  " + g.city_name(d.city_at[p]["name"])) if p in d.city_at else "  (no city there)",)))
        s.valueChanged.connect(lambda v: (d.begin(tag=("prov", i)), d.set_province(i, v),
                                          self.main.on_doc_changed("Set province", rebuild_panels=False)))
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(s); h.addWidget(plab, 1)
        clear = QToolButton(); clear.setText("None")
        clear.clicked.connect(lambda: s.setValue(NO_HEX))
        h.addWidget(clear)
        fl.addRow("Province city hex", row)
        pm = QPushButton("Province painting mode…")
        pm.setToolTip("Paint which hexes belong to the city on this hex's province (or to this hex if it is a city)")
        pm.clicked.connect(lambda: self.main.start_province_mode(i))
        fl.addRow(pm)
        lay.addWidget(box)

        box = QGroupBox("Owner")
        fl = QFormLayout(box)
        cb = QComboBox()
        cb.addItem("(none)", NO_OWNER)
        for k, f in enumerate(d.btl.factions):
            cb.addItem("[%d] %s" % (k, d.faction_label(f)), k)
        idx = cb.findData(d.owner(i))
        if idx < 0:
            cb.addItem("%d (invalid)" % d.owner(i), d.owner(i)); idx = cb.count() - 1
        cb.setCurrentIndex(idx)
        has = i in d.troop_at or i in d.city_at
        cb.setEnabled(has)
        cb.currentIndexChanged.connect(lambda k: self.act("Set owner", lambda: d.set_owner(i, cb.itemData(k))))
        fl.addRow("Owner faction", cb)
        if not has:
            fl.addRow(QLabel("The game only keeps an owner on hexes with a city or a troop."))
        po = d.province_owner(i)
        fl.addRow("Province owner", QLabel("(none)" if po == NO_OWNER or po >= len(d.btl.factions)
                                           else d.faction_label(d.btl.factions[po])))
        lay.addWidget(box)

    # ------------------------------------------------------------------ city
    def page_city(self, lay):
        d, i = self.doc, self.hex
        c = d.city_at.get(i)
        self.buttons(lay, [("Add city", lambda: self.act("Add city", lambda: d.set_city(i)), c is None),
                           ("Copy city", lambda: (self.clip.__setitem__("city", c.clone()), self.rebuild()), c is not None),
                           ("Paste city", lambda: self.act("Paste city", lambda: d.set_city(i, self.clip["city"])),
                            "city" in self.clip),
                           ("Delete city", lambda: self.act("Delete city", lambda: d.delete_city(i)), c is not None)])
        if c is not None:
            lay.addWidget(RecordForm(self.ctx, c))

    def page_cityhp(self, lay):
        d, i = self.doc, self.hex
        t = d.cityhp_at.get(i)
        lay.addWidget(QLabel("City HP is stored as a troop record with army code 39 on the city hex."))
        self.buttons(lay, [("Add city HP", lambda: self.act("Add city HP", lambda: d.add_city_hp(i)),
                            t is None and i in d.city_at),
                           ("Delete city HP", lambda: self.act("Delete city HP", lambda: d.delete_city_hp(i)),
                            t is not None)])
        if t is not None:
            keep = {"hp_bonus", "hp", "hp_max", "level", "exp"}
            lay.addWidget(RecordForm(self.ctx, t, exclude=[k for k in t.rt.keys if k not in keep]))

    # ------------------------------------------------------------------ troop
    def page_troop(self, lay):
        d, i, g = self.doc, self.hex, self.main.game
        t = d.troop_at.get(i)

        def copy():
            self.clip["troop"] = (t.clone(), d.owner(i))
            self.rebuild()

        def paste():
            rec, owner = self.clip["troop"]
            d.set_troop(i, rec.clone())
            if i not in d.city_at and owner != NO_OWNER and owner < len(d.btl.factions):
                d.set_owner(i, owner)

        self.buttons(lay, [("Add troop", lambda: self.act("Add troop", lambda: d.set_troop(i, None)), t is None),
                           ("Copy troop", copy, t is not None),
                           ("Paste troop", lambda: self.act("Paste troop", paste), "troop" in self.clip),
                           ("Delete troop", lambda: self.act("Delete troop", lambda: d.delete_troop(i)), t is not None)])
        if t is None:
            lay.addWidget(QLabel("Tip: drag a troop on the map to move it to an empty hex."))
            return
        lay.addWidget(self.troop_summary(t))
        h = QHBoxLayout()
        b = QPushButton("Recalculate HP from ArmySettings")
        b.setToolTip("Sets current and max HP to base HP x formation HP% + level bonus")
        b.clicked.connect(lambda: self.act("Recalculate HP", lambda: self._recalc_hp(t)))
        h.addWidget(b); h.addStretch()
        lay.addLayout(h)
        lay.addWidget(RecordForm(self.ctx, t, after_set=self._troop_after_set))

    def _recalc_hp(self, t):
        hp = self.main.game.default_hp(t["army"], t["level"], max(1, t["formation"]))
        t["hp"] = t["hp_max"] = hp

    def _troop_after_set(self, rec, key):
        if key in ("army", "level", "general", "formation"):
            self.main.view.viewport().update()

    def troop_summary(self, t):
        g = self.main.game
        r = g.army_row(t["army"], t["level"] or 1)
        lab = QLabel()
        lab.setFrameShape(QFrame.StyledPanel)
        lab.setWordWrap(True)
        if r:
            lab.setText("<b>%s</b> (army %d, settings id %d)<br>Attack %d-%d, range %d-%d, HP %d, defence %d, "
                        "mobility %d, cost %d/%d/%d" % (g.army_name(t["army"], t["level"] or 1), t["army"], r["Id"],
                                                         r["MinAttack"], r["MaxAttack"], r["MinRange"], r["MaxRange"],
                                                         r["HP"], r["Defence"], r["Mobility"], r["CostMoney"],
                                                         r["CostGear"], r["CostAtomic"]))
        else:
            lab.setText("Unknown army code %d" % t["army"])
        if t["general"] > 0:
            lab.setText(lab.text() + "<br>General: <b>%s</b> (id %d)" % (g.general_name(t["general"]), t["general"]))
        return lab

    # ------------------------------------------------------------------ mine / capital
    def page_mine(self, lay):
        d, i = self.doc, self.hex
        m = d.mine_at.get(i)
        self.buttons(lay, [("Add mine", lambda: self.act("Add mine", lambda: d.add_mine(i)), m is None),
                           ("Delete mine", lambda: self.act("Delete mine", lambda: d.delete_mine(i)), m is not None)])
        if m is not None:
            lay.addWidget(QLabel("Level 1-4 normally uses HP 70 / 115 / 160 / 205; army 33 = land mine, 34 = naval mine."))
            lay.addWidget(RecordForm(self.ctx, m))

    def page_capital(self, lay):
        d, i = self.doc, self.hex
        c = d.capital_at.get(i)
        box = QGroupBox("Capital / key area")
        bl = QVBoxLayout(box)
        self.buttons(bl, [("Add capital flag", lambda: self.act("Add capital", lambda: d.add_capital(i)), c is None),
                          ("Delete capital flag", lambda: self.act("Delete capital", lambda: d.delete_capital(i)),
                           c is not None)])
        if c is not None:
            bl.addWidget(RecordForm(self.ctx, c))
        lay.addWidget(box)
        box = QGroupBox("Deploy slots on this hex")
        bl = QVBoxLayout(box)
        slots = d.deploy_at.get(i, [])
        if not slots:
            bl.addWidget(QLabel("None.  Deploy slots are managed in the Data panel (Deploy slots A / B)."))
        for section, rec in slots:
            bl.addWidget(QLabel("<b>%s</b>" % ("Deploy slot A" if section == "deploy_a" else "Deploy slot B")))
            bl.addWidget(RecordForm(self.ctx, rec))
        lay.addWidget(box)

    # ------------------------------------------------------------------ lists
    def page_reinf(self, lay):
        d, i, g = self.doc, self.hex, self.main.game
        rows = list(d.reinf_at.get(i, []))
        self.buttons(lay, [("Add reinforcement", lambda: self.act("Add reinforcement", lambda: d.add_reinforcement(i)), True),
                           ("Paste reinforcement", lambda: self.act("Paste reinforcement",
                                                                    lambda: d.add_reinforcement(i, self.clip["reinf"])),
                            "reinf" in self.clip)])
        for n, r in enumerate(rows):
            box = QGroupBox("#%d  round %d: %s" % (n + 1, r["round"], g.army_name(r["army"], r["level"] or 1)))
            bl = QVBoxLayout(box)
            self.buttons(bl, [("Copy", lambda _=False, r=r: (self.clip.__setitem__("reinf", r.clone()), self.rebuild()), True),
                              ("Delete", lambda _=False, r=r: self.act("Delete reinforcement",
                                                                         lambda: d.delete_reinforcement(i, r)), True)])
            bl.addWidget(RecordForm(self.ctx, r))
            lay.addWidget(box)

    def page_airraid(self, lay):
        d, i, g = self.doc, self.hex, self.main.game
        rows = list(d.airraid_at.get(i, []))
        self.buttons(lay, [("Add air raid", lambda: self.act("Add air raid", lambda: d.add_airraid(i)), True)])
        for n, r in enumerate(rows):
            box = QGroupBox("#%d  round %d: %s" % (n + 1, r["round"], g.army_name(r["army"])))
            bl = QVBoxLayout(box)
            self.buttons(bl, [("Delete", lambda _=False, r=r: self.act("Delete air raid", lambda: d.delete_airraid(i, r)), True)])
            bl.addWidget(RecordForm(self.ctx, r))
            lay.addWidget(box)
