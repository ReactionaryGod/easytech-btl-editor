"""Main window."""
import os
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QSizePolicy, QApplication, QDockWidget, QFileDialog, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QStackedWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from gog3btl.gamedata import Gog3Game, is_gog3_assets
from gog3btl.model import DocError as Gog3DocError, Gog3Doc
from gog3btl.ui.datapanel import Gog3DataPanel
from gog3btl.ui.hexpanel import Gog3HexPanel
from gog3btl.ui.toolpanel import Gog3ToolPanel

from ..gamedata import GameData, find_assets
from ..model import BtlDoc, DocError, NO_OWNER
from . import dialogs
from .common import ImageCache, settings, letter_icon
from .datapanel import DataPanel
from .forms import FormContext
from .hexpanel import HexPanel
from .mapview import DEFAULT_LAYERS, MODE_CROP, MODE_MULTI, MODE_PROVINCE, MODE_SELECT, MapView
from .toolpanel import ToolPanel

CATEGORIES = [("Conquest", "conquest"), ("Campaign", "stage"), ("General stage", "generalstage_"),
              ("Frontier", "frontier"), ("Invade corps", "invadecorps"), ("War zone", "warzone"),
              ("Event", "event"), ("Legend", "legend"), ("Other", "")]

GOG3_CATEGORIES = [("Campaign", "campaign"), ("Challenge", "challenge"), ("United campaigns", "united"),
                   ("Elite battles", "elite"), ("Conquest", "conquest"), ("Corps", "corps"), ("Other", "")]

LAYER_NAMES = [("terrain", "Terrain sprites"), ("owners", "Ownership colours"), ("borders", "Borders"),
               ("grid", "Hex grid"), ("cities", "Cities"), ("names", "City names / HP"), ("troops", "Troops"),
               ("generals", "General portraits"), ("flags", "Flags"), ("markers", "Mines, capitals, reinforcements"),
               ("coords", "Hex coordinates")]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.st = settings()
        self.opts = {"lang": self.st.value("lang", "en"), "labels": self.st.value("labels", "en"),
                     "unknown": self.st.value("unknown", False, type=bool),
                     "backup": self.st.value("backup", True, type=bool),
                     "checksum": self.st.value("checksum", True, type=bool)}
        self.doc = None
        self.game = GameData(None)
        self.images = ImageCache(self.game)
        self.ctx = FormContext(self)
        self.resize(1500, 920)

        self.view = MapView()
        self.setCentralWidget(self.view)
        for k, v in DEFAULT_LAYERS.items():
            self.view.layers[k] = self.st.value("layer_" + k, v, type=bool)
        self.view.hexClicked.connect(self.on_hex_clicked)
        self.view.hexHovered.connect(self.on_hex_hovered)
        self.view.docChanged.connect(lambda label: self.on_doc_changed(label))
        self.view.selectionChanged.connect(lambda: self.tools.update_labels())
        self.view.cropChanged.connect(lambda *a: self.tools.update_labels())

        # docks
        self.tree_filter = QLineEdit(); self.tree_filter.setPlaceholderText("Filter maps…")
        self.tree_filter.textChanged.connect(self.filter_tree)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        self.tree.itemActivated.connect(self.on_tree_activated)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(2, 2, 2, 2)
        ll.addWidget(self.tree_filter); ll.addWidget(self.tree)
        self.maps_dock = self._dock("Maps", left, Qt.LeftDockWidgetArea)
        # every dock holds the World Conqueror 4 panel and the Glory of Generals 3 panel; set_kind() switches
        self.kind = "wc4"
        self.panels = {"wc4": (ToolPanel(self), HexPanel(self), DataPanel(self)),
                       "gog3": (Gog3ToolPanel(self), Gog3HexPanel(self, self.ctx), Gog3DataPanel(self, self.ctx))}
        self.stacks = [QStackedWidget() for _ in range(3)]
        for kind in ("wc4", "gog3"):
            for stack, panel in zip(self.stacks, self.panels[kind]):
                stack.addWidget(panel)
        self.tools, self.hexpanel, self.datapanel = self.panels["wc4"]
        self.tools_dock = self._dock("Tools", self.stacks[0], Qt.LeftDockWidgetArea)
        self.hex_dock = self._dock("Hex", self.stacks[1], Qt.RightDockWidgetArea)
        self.data_dock = self._dock("Data", self.stacks[2], Qt.RightDockWidgetArea)
        self.tabifyDockWidget(self.hex_dock, self.data_dock)
        self.hex_dock.raise_()

        self.status = QLabel()
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.statusBar().addPermanentWidget(self.status, 1)
        self._build_actions()
        self.restoreGeometry(self.st.value("geometry", b""))
        if not self.restoreState(self.st.value("state", b"")):
            QTimer.singleShot(0, self.default_dock_sizes)
        self.update_title()
        work = self.st.value("work", "")
        QTimer.singleShot(0, lambda: self.load_work(work, quiet=True) if work else self.first_run())

    # ------------------------------------------------------------------ construction
    def _dock(self, title, widget, area):
        d = QDockWidget(title, self)
        d.setObjectName(title + "Dock")
        d.setWidget(widget)
        self.addDockWidget(area, d)
        return d

    def _act(self, text, fn, shortcut=None, icon=None, tip=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        if icon:
            a.setIcon(icon)
        if tip:
            a.setToolTip(tip)
        a.triggered.connect(fn)
        return a

    def _build_actions(self):
        mb = self.menuBar()
        fm = mb.addMenu("&File")
        self.a_work = self._act("Set game folder…", self.choose_work, icon=letter_icon("G", "#557"),
                                tip="Folder of the unpacked APK (the one containing assets/) or assets/ itself")
        self.a_open = self._act("Open map…", self.choose_map, "Ctrl+O", letter_icon("O", "#575"))
        self.a_save = self._act("Save", self.save, "Ctrl+S", letter_icon("S", "#2a6"))
        self.a_saveas = self._act("Save as…", self.save_as, "Ctrl+Shift+S")
        self.a_reload = self._act("Reload from disk", self.reload_map)
        fm.addActions([self.a_work, self.a_open])
        fm.addSeparator()
        fm.addActions([self.a_save, self.a_saveas, self.a_reload])
        fm.addSeparator()
        fm.addAction(self._act("Exit", self.close, "Ctrl+Q"))

        em = mb.addMenu("&Edit")
        self.a_undo = self._act("Undo", self.undo, "Ctrl+Z", letter_icon("↶", "#666"))
        self.a_redo = self._act("Redo", self.redo, "Ctrl+Y", letter_icon("↷", "#666"))
        em.addActions([self.a_undo, self.a_redo])

        vm = mb.addMenu("&View")
        lm = QMenu("Layers", self)
        for key, name in LAYER_NAMES:
            a = QAction(name, self, checkable=True)
            a.setChecked(self.view.layers[key])
            a.toggled.connect(lambda on, k=key: self.set_layer(k, on))
            lm.addAction(a)
        vm.addMenu(lm)
        vm.addSeparator()
        vm.addAction(self._act("Zoom in", lambda: self.view.zoom(1.25), "Ctrl+="))
        vm.addAction(self._act("Zoom out", lambda: self.view.zoom(0.8), "Ctrl+-"))
        vm.addAction(self._act("Fit map", self.view.fit, "Ctrl+0"))
        vm.addSeparator()
        for d in (self.maps_dock, self.tools_dock, self.hex_dock, self.data_dock):
            vm.addAction(d.toggleViewAction())

        tm = mb.addMenu("&Tools")
        self.mode_group = QActionGroup(self)
        self.mode_actions = {}
        for mode, text, key, col in ((MODE_SELECT, "Select", "1", "#2a6"), (MODE_MULTI, "Multi-select", "2", "#29c"),
                                     (MODE_PROVINCE, "Province paint", "3", "#c92"), (MODE_CROP, "Crop to new map", "4", "#c33")):
            a = QAction(text, self, checkable=True)
            a.setShortcut(QKeySequence(key))
            a.setIcon(letter_icon(text[0], col))
            a.triggered.connect(lambda _=False, m=mode: self.set_mode(m))
            self.mode_group.addAction(a)
            self.mode_actions[mode] = a
            tm.addAction(a)
        self.mode_actions[MODE_SELECT].setChecked(True)
        tm.addSeparator()
        tm.addAction(self._act("Resource import log", self.show_log))
        tm.addAction(self._act("Settings…", self.show_settings))
        hm = mb.addMenu("&Help")
        hm.addAction(self._act("About", self.about))

        tb = self.addToolBar("Main")
        tb.setObjectName("MainToolbar")
        tb.addActions([self.a_work, self.a_open, self.a_save])
        tb.addSeparator()
        tb.addActions([self.a_undo, self.a_redo])
        tb.addSeparator()
        for m in (MODE_SELECT, MODE_MULTI, MODE_PROVINCE, MODE_CROP):
            tb.addAction(self.mode_actions[m])
        tb.addSeparator()
        lb = QToolButton(); lb.setText("Layers"); lb.setMenu(lm); lb.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(lb)
        tb.addAction(self._act("Fit", self.view.fit))

    def default_dock_sizes(self):
        w = max(1200, self.width())
        self.resizeDocks([self.maps_dock, self.hex_dock], [int(w * 0.17), int(w * 0.30)], Qt.Horizontal)
        self.resizeDocks([self.maps_dock, self.tools_dock], [int(self.height() * 0.62), int(self.height() * 0.38)],
                         Qt.Vertical)

    # ------------------------------------------------------------------ work folder / tree
    def first_run(self):
        guess = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                             "World Conqueror 4_1.30.0_learning")
        if find_assets(guess):
            self.load_work(os.path.normpath(guess), quiet=True)
        else:
            self.status.setText("Use File > Set game folder… to point at the unpacked game (folder with assets/).")

    def choose_work(self):
        d = QFileDialog.getExistingDirectory(self, "Game folder (contains assets/) or the assets folder",
                                             self.st.value("work", ""))
        if d:
            self.load_work(d)

    def load_work(self, path, quiet=False):
        assets = find_assets(path)
        if not assets:
            if not quiet:
                QMessageBox.warning(self, "Not a game folder", "No assets/stage or assets/json folder found in\n" + path)
            return
        if not self.maybe_save():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if is_gog3_assets(assets):
                self.game = Gog3Game(path, self.opts["lang"])
            else:
                self.game = GameData(path, self.opts["lang"])
            self.images = ImageCache(self.game)
        finally:
            QApplication.restoreOverrideCursor()
        self.set_kind(getattr(self.game, "KIND", "wc4"))
        self.st.setValue("work", path)
        self.doc = None
        self.view.set_document(None, self.game, self.images)
        self.hexpanel.set_hex(None)
        self.datapanel.reload()
        self.update_title()
        self.fill_tree()
        bad = [m for l, m in self.game.log if l != "ok"]
        self.status.setText("Game folder: %s   (%d resources loaded%s)" % (
            self.game.assets, sum(1 for l, _ in self.game.log if l == "ok"),
            ", %d problems - see Tools > Resource import log" % len(bad) if bad else ""))
        last = self.st.value("last_map", "")
        if last and os.path.exists(last) and os.path.normcase(last).startswith(os.path.normcase(self.game.assets)):
            self.open_map(last)

    def fill_tree(self):
        if self.kind == "gog3":
            return self.fill_tree_gog3()
        self.tree.clear()
        groups = {}
        for title, prefix in CATEGORIES:
            it = QTreeWidgetItem([title])
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(it)
            groups[prefix] = it
        stage = os.path.join(self.game.assets, "stage") if self.game.assets else None
        for fn in self.game.stage_files():
            low = fn.lower()
            prefix = ""
            for _, p in CATEGORIES:
                if p and low.startswith(p) and not (p == "stage" and low.startswith("generalstage")):
                    prefix = p
                    break
            label = fn
            num = "".join(ch for ch in fn[:-4] if ch.isdigit())
            if prefix == "stage" and num:
                name = self.game.text("stage_name_%s" % num)
                if name:
                    label = "%s  -  %s" % (fn, name)
            child = QTreeWidgetItem([label])
            child.setData(0, Qt.UserRole, os.path.join(stage, fn))
            groups[prefix].addChild(child)
        for it in groups.values():
            it.setText(0, "%s (%d)" % (it.text(0).split(" (")[0], it.childCount()))

    def fill_tree_gog3(self):
        self.tree.clear()
        groups = {}
        for title, key in GOG3_CATEGORIES:
            it = QTreeWidgetItem([title])
            it.setFlags(it.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(it)
            groups[key] = it
        stage = os.path.join(self.game.assets, "stage") if self.game.assets else None
        for fn in self.game.stage_files():
            low = fn.lower()
            num = low[5:-4] if low.startswith("stage") else ""
            if num.isdigit():
                n = int(num)
                if n < 20000:
                    key = "challenge" if 11300 <= n < 11500 else "campaign"
                else:
                    key = "united" if n < 30000 else "elite"
            elif low.startswith("conquest"):
                key = "conquest"
            elif low.startswith("corps") or "\u519b\u56e2" in fn:
                key = "corps"
            else:
                key = ""
            title = self.game.stage_title(fn)
            child = QTreeWidgetItem(["%s  -  %s" % (fn, title) if title else fn])
            child.setData(0, Qt.UserRole, os.path.join(stage, fn))
            groups[key].addChild(child)
        for it in groups.values():
            it.setText(0, "%s (%d)" % (it.text(0).split(" (")[0], it.childCount()))

    def set_kind(self, kind):
        """Switch panels and tools between World Conqueror 4 ("wc4") and Glory of Generals 3 ("gog3")."""
        if kind == self.kind:
            return
        if self.view.mode != MODE_SELECT:
            self.set_mode(MODE_SELECT)
        self.kind = kind
        self.tools, self.hexpanel, self.datapanel = self.panels[kind]
        for stack, panel in zip(self.stacks, self.panels[kind]):
            stack.setCurrentWidget(panel)
        for m in (MODE_PROVINCE, MODE_CROP):
            self.mode_actions[m].setEnabled(kind == "wc4")

    def filter_tree(self, text):
        words = text.lower().split()
        for k in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(k)
            shown = 0
            for j in range(top.childCount()):
                ch = top.child(j)
                hide = not all(w in ch.text(0).lower() for w in words)
                ch.setHidden(hide)
                shown += not hide
            top.setExpanded(bool(words) and shown > 0)

    def on_tree_activated(self, item, col):
        path = item.data(0, Qt.UserRole)
        if path:
            self.open_map(path)

    # ------------------------------------------------------------------ open / save
    def choose_map(self):
        start = os.path.join(self.game.assets, "stage") if self.game.assets else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open battle map", start, "Battle maps (*.btl);;All files (*)")
        if path:
            self.open_map(path)

    def open_map(self, path):
        if not self.maybe_save():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with open(path, "rb") as fh:
                head = fh.read(4)
            kind = "wc4" if len(head) == 4 and int.from_bytes(head, "little") in (1, 2, 3) else "gog3"
            game = self.game if getattr(self.game, "KIND", "wc4") == kind else (
                Gog3Game(None) if kind == "gog3" else GameData(None))
            doc = Gog3Doc(path, game) if kind == "gog3" else BtlDoc(path, game)
        except (DocError, Gog3DocError, ValueError, OSError) as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Cannot open map", "%s\n\n%s" % (path, e))
            return
        except Exception:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Cannot open map", traceback.format_exc())
            return
        if game is not self.game:
            self.game = game
            self.images = ImageCache(game)
        self.set_kind(kind)
        self.doc = doc
        self.view.set_document(doc, self.game, self.images)
        QApplication.restoreOverrideCursor()
        self.set_mode(MODE_SELECT)
        self.hexpanel.set_hex(None)
        self.datapanel.reload()
        self.st.setValue("last_map", path)
        self.update_title()
        if kind == "gog3":
            self.statusBar().showMessage(
                "Opened %s (Glory of Generals 3): %d x %d hexes, %d factions, %d areas, %d armies%s" % (
                    os.path.basename(path), doc.W, doc.H, len(doc.factions), len(doc.area_at),
                    len(doc.b.get("armies", {}).get("list", [])),
                    "" if game.assets else "  - set the GoG3 game folder for names and art"), 8000)
            return
        b = doc.btl
        self.statusBar().showMessage("Opened %s: v%d, %d x %d hexes, %s, %d factions, %d cities, %d troops" % (
            os.path.basename(path), b.version, doc.W, doc.H, "world-map terrain" if doc.world else "own terrain",
            len(b.factions), len(b.cities), len(b.troops)), 8000)

    def reload_map(self):
        if self.doc:
            path = self.doc.path
            self.doc.dirty = False
            self.open_map(path)

    def save(self):
        if not self.doc:
            return False
        try:
            size, msg = self.doc.save(backup=self.opts["backup"], update_checksum=self.opts["checksum"])
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False
        self.update_title()
        self.statusBar().showMessage("Saved %s (%d bytes)%s" % (os.path.basename(self.doc.path), size,
                                                                  ("; " + msg) if msg else ""), 8000)
        return True

    def save_as(self):
        if not self.doc:
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Save battle map as", self.doc.path, "Battle maps (*.btl)")
        if not path:
            return False
        try:
            size, msg = self.doc.save(path, backup=self.opts["backup"], update_checksum=self.opts["checksum"])
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False
        self.st.setValue("last_map", path)
        self.fill_tree()
        self.update_title()
        self.statusBar().showMessage("Saved %s (%d bytes)" % (path, size), 8000)
        return True

    def maybe_save(self):
        if not self.doc or not self.doc.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes to %s?" % os.path.basename(self.doc.path),
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def closeEvent(self, ev):
        if not self.maybe_save():
            ev.ignore()
            return
        self.st.setValue("geometry", self.saveGeometry())
        self.st.setValue("state", self.saveState())
        ev.accept()

    def update_title(self):
        if self.doc:
            self.setWindowTitle("%s%s - EasyTech BTL Editor" % (os.path.basename(self.doc.path),
                                                                   " *" if self.doc.dirty else ""))
        else:
            self.setWindowTitle("EasyTech BTL Editor")
        has = self.doc is not None
        for a in (self.a_save, self.a_saveas, self.a_reload):
            a.setEnabled(has)
        self.a_undo.setEnabled(has and bool(self.doc.undo_stack))
        self.a_redo.setEnabled(has and bool(self.doc.redo_stack))

    # ------------------------------------------------------------------ edits
    def on_doc_changed(self, label, rebuild_panels=True):
        self.view.viewport().update()
        if rebuild_panels:
            self.hexpanel.rebuild()
            if self.data_dock.isVisible():
                self.datapanel.reload_current()
        else:
            self.hexpanel.update_titles()
        self.tools.update_labels()
        self.update_title()
        self.statusBar().showMessage(label, 3000)

    def undo(self):
        if self.doc and self.doc.undo():
            self._after_history("Undo")

    def redo(self):
        if self.doc and self.doc.redo():
            self._after_history("Redo")

    def _after_history(self, label):
        self.view.refresh()
        self.hexpanel.rebuild()
        self.datapanel.reload()
        self.update_title()
        self.statusBar().showMessage(label, 2000)

    def on_hex_clicked(self, i):
        self.hexpanel.set_hex(i)
        self.hex_dock.raise_()
        self.on_hex_hovered(i)

    def on_hex_hovered(self, i):
        d = self.doc
        if not d:
            return
        if self.kind == "gog3":
            return self.hover_gog3(i)
        x, y = d.xy(i)
        t = d.terrain(i)
        parts = ["(%d, %d)" % (x, y), "hex id %d" % d.file_hex(i), self.game.terrain_name(t["terrain"])]
        o = d.owner(i)
        if o != NO_OWNER and o < len(d.btl.factions):
            parts.append("owner " + d.faction_label(d.btl.factions[o]))
        p = d.local(d.province(i))
        if p is not None:
            parts.append("province of (%d, %d)" % d.xy(p))
        if i in d.city_at:
            c = d.city_at[i]
            parts.append("city %s [%s]" % (self.game.city_name(c["name"]) or c["name"], self.game.building_name(c["building"])))
        if i in d.troop_at:
            t = d.troop_at[i]
            s = "troop %s lv%d x%d" % (self.game.army_name(t["army"], t["level"] or 1), t["level"], t["formation"])
            if t["general"] > 0:
                s += " with " + self.game.general_name(t["general"])
            if t["skin"]:
                s += ", skin " + self.game.skin_name(t["army"], t["skin"])
            parts.append(s)
        self.status.setText("   |   ".join(parts))

    def hover_gog3(self, i):
        d, g = self.doc, self.game
        x, y = d.xy(i)
        parts = ["(%d, %d)" % (x, y), "hex %d" % i, g.terrain_type_name(d.terrain_type(i))]
        if d.is_disabled(i):
            parts.append("disabled")
        a = d.area_at.get(i)
        if a:
            s = "area"
            if a.get("name"):
                s += " " + g.city_name(a["name"])
            if "building" in a:
                info = a["building"].get("info", {})
                s += " [%s, %s]" % (g.building_name(info.get("building", 0)), d.faction_label(info.get("owner", 0)))
            if "fortification" in a:
                s += " " + g.fortification_name(a["fortification"].get("type", 0))
            parts.append(s)
        if i in d.key_at:
            parts.append("key area")
        u = d.army_at.get(i)
        if u:
            info = u["info"]
            s = "army #%d %s x%d, %s" % (info["serial"], g.army_name(info["army"]), info["number"],
                                         d.faction_label(info["faction"]))
            if "general" in u:
                s += " with " + g.general_name(u["general"].get("id", 0))
            parts.append(s)
        self.status.setText("   |   ".join(parts))

    def set_layer(self, key, on):
        self.view.layers[key] = on
        self.st.setValue("layer_" + key, on)
        self.view.viewport().update()

    def set_mode(self, mode):
        if self.kind == "gog3" and mode in (MODE_PROVINCE, MODE_CROP):
            self.mode_actions[self.view.mode].setChecked(True)
            return
        if mode == MODE_PROVINCE and self.view.province_anchor is None:
            i = self.view.selected
            if i is None or not self.doc:
                QMessageBox.information(self, "Province painting",
                                        "Select a city hex (or a hex of the province) first, then start province painting.")
                self.mode_actions[self.view.mode].setChecked(True)
                return
            self.start_province_mode(i)
            return
        if mode != MODE_PROVINCE:
            self.view.province_anchor = None
            self.view.province_set.clear()
        self.view.set_mode(mode)
        self.tools.set_mode(mode)
        self.mode_actions[mode].setChecked(True)
        self.tools_dock.raise_()
        self.tools_dock.show()

    def start_province_mode(self, i):
        d = self.doc
        if not d:
            return
        anchor = i
        if i not in d.city_at:
            p = d.local(d.province(i))
            if p is not None:
                anchor = p
        fh = d.file_hex(anchor)
        self.view.province_anchor = anchor
        self.view.province_set = {j for j in range(d.n) if d.province(j) == fh}
        self.view.province_set.add(anchor)
        self.view.set_mode(MODE_PROVINCE)
        self.tools.set_mode(MODE_PROVINCE)
        self.mode_actions[MODE_PROVINCE].setChecked(True)
        self.tools_dock.show(); self.tools_dock.raise_()

    def crop_save(self):
        d = self.doc
        if not d:
            return
        if not self.view.crop_rect:
            QMessageBox.information(self, "Crop", "Drag a rectangle on the map first (Crop mode).")
            return
        base = os.path.splitext(os.path.basename(d.path))[0]
        dlg = dialogs.CropDialog(self, d, self.view.crop_rect, base + "_crop")
        if not dlg.exec():
            return
        rect, name = dlg.values()
        if not name:
            return
        if not name.lower().endswith(".btl"):
            name += ".btl"
        folder = os.path.join(self.game.assets, "stage") if self.game.assets else os.path.dirname(d.path)
        path = os.path.join(folder, name)
        if os.path.exists(path) and QMessageBox.question(self, "Overwrite?", "%s exists. Overwrite it?" % name) != QMessageBox.Yes:
            return
        try:
            out = d.crop(*rect)
            size = out.save(path)
        except Exception as e:
            QMessageBox.critical(self, "Crop failed", str(e))
            return
        self.fill_tree()
        self.statusBar().showMessage("Saved cropped map %s (%d x %d hexes, %d bytes)" % (name, out.width, out.height, size), 8000)
        if dlg.open_after.isChecked():
            self.open_map(path)

    # ------------------------------------------------------------------ misc
    def show_log(self):
        dialogs.LogDialog(self, self.game.log).exec()

    def show_settings(self):
        dlg = dialogs.SettingsDialog(self, self.opts)
        if not dlg.exec():
            return
        new = dlg.values()
        lang_changed = new["lang"] != self.opts["lang"]
        self.opts.update(new)
        for k, v in new.items():
            self.st.setValue(k, v)
        if lang_changed and self.game.assets:
            self.game.lang = new["lang"]
            self.game._load_strings()
            self.fill_tree()
        self.view.viewport().update()
        self.hexpanel.rebuild()
        self.datapanel.reload()

    def about(self):
        QMessageBox.about(self, "About", "<b>EasyTech BTL Editor</b> 0.2.1<br>Visual editor for EasyTech .btl "
                          "battle maps: World Conqueror 4 (v1.30.0, modelled on EModule's BtlEditor) and Glory of "
                          "Generals 3 (FlatBuffers maps).<br>"
                          "<a href='https://github.com/ReactionaryGod/easytech-btl-editor'>"
                          "github.com/ReactionaryGod/easytech-btl-editor</a> (MIT licence)<br><br>"
                          "WC4: every shipped map loads and saves byte-for-byte. GoG3: every shipped map rebuilds "
                          "and passes the game's own verifier.")
