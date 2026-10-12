"""Map rendering and mouse interaction."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal, QObject
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTransform)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from ..gamedata import ARMY_TYPE_SHORT
from ..model import CITY_HP_ARMY, NO_OWNER, NO_HEX
from .common import (COL_STEP, HALF_H, HEX_H, HEX_R, TERRAIN_COLORS, faction_color, hex_center, hex_polygon,
                     map_size, neighbours, pick_hex)

MODE_SELECT, MODE_MULTI, MODE_PROVINCE, MODE_CROP = "select", "multi", "province", "crop"

TYPE_COLORS = {1: "#5b8c3a", 2: "#7a6a3a", 3: "#8a4a3a", 4: "#2f5f8f", 5: "#6a6aa8", 6: "#a05050", 7: "#b03030",
               8: "#707070", 11: "#a0a040", 12: "#606060", 13: "#4f8f8f"}

DEFAULT_LAYERS = {"terrain": True, "owners": True, "borders": True, "grid": False, "cities": True, "names": True,
                  "troops": True, "generals": True, "flags": True, "markers": True, "coords": False}


class MapItem(QGraphicsItem):
    def __init__(self, view):
        super().__init__()
        self.view = view
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)

    def boundingRect(self):
        d = self.view.doc
        return map_size(d.W, d.H).adjusted(-60, -120, 60, 60) if d else QRectF()

    def paint(self, painter, option, widget=None):
        self.view.paint_map(painter, option.exposedRect)


class MapView(QGraphicsView):
    hexClicked = Signal(int)          # select mode
    hexHovered = Signal(int)
    docChanged = Signal(str)          # something on the map was edited (label)
    selectionChanged = Signal()       # multi / province set changed
    cropChanged = Signal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.setBackgroundBrush(QColor("#1d2733"))
        self.doc = None
        self.game = None
        self.images = None
        self.item = None
        self.layers = dict(DEFAULT_LAYERS)
        self.mode = MODE_SELECT
        self.selected = None
        self.hover = None
        self.multi = set()
        self.province_anchor = None
        self.province_set = set()
        self.crop_rect = None             # (x0, y0, x1, y1) hex coords
        self._press = None
        self._pan = None
        self._drag_troop = None           # (src index, current scene pos)
        self._paint_add = True
        self._crop_start = None

    # ------------------------------------------------------------------ setup
    def set_document(self, doc, game, images):
        self.doc, self.game, self.images = doc, game, images
        self.selected = None
        self.multi.clear()
        self.province_set.clear()
        self.crop_rect = None
        self.scene().clear()
        self.item = None
        if doc is None:
            self.viewport().update()
            return
        self.item = MapItem(self)
        self.scene().addItem(self.item)
        self.scene().setSceneRect(self.item.boundingRect().adjusted(-400, -400, 400, 400))
        self.resetTransform()
        self.fit()

    def refresh(self):
        if self.item:
            self.item.prepareGeometryChange()
            self.scene().setSceneRect(self.item.boundingRect().adjusted(-400, -400, 400, 400))
            self.item.update()
        self.viewport().update()

    def fit(self):
        if self.item:
            self.fitInView(self.item.boundingRect(), Qt.KeepAspectRatio)

    def zoom(self, factor):
        s = self.transform().m11() * factor
        if 0.02 < s < 6:
            self.scale(factor, factor)

    def center_on_hex(self, i):
        if self.doc:
            c, r = self.doc.xy(i)
            self.centerOn(hex_center(c, r))

    def set_mode(self, mode):
        self.mode = mode
        self._drag_troop = None
        self.viewport().update()

    # ------------------------------------------------------------------ painting
    def visible_range(self, rect):
        d = self.doc
        c0 = max(0, int((rect.left() - HEX_W_PAD) // COL_STEP) - 1)
        c1 = min(d.W - 1, int((rect.right() + HEX_W_PAD) // COL_STEP) + 1)
        r0 = max(0, int((rect.top() - HEX_H) // HEX_H) - 1)
        r1 = min(d.H - 1, int((rect.bottom() + HEX_H) // HEX_H) + 1)
        return c0, c1, r0, r1

    def paint_map(self, p, rect):
        d = self.doc
        if d is None:
            return
        if getattr(d, "KIND", "wc4") == "gog3":
            from gog3btl.ui.painter import paint
            return paint(self, p, rect)
        lod = p.worldTransform().m11()
        c0, c1, r0, r1 = self.visible_range(rect)
        W = d.W
        game, img = self.game, self.images
        owners, factions = d.btl.owners, d.btl.factions
        cells = [(c, r, r * W + c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
        polys = {}
        for c, r, i in cells:
            ctr = hex_center(c, r)
            polys[i] = (ctr, hex_polygon(ctr.x(), ctr.y()))

        # 1. ground colour
        p.setPen(Qt.NoPen)
        for c, r, i in cells:
            t = d.terrain(i)
            tt = game.terrain_type.get(t["terrain"], 0) if game else 0
            p.setBrush(QColor(TERRAIN_COLORS.get(tt, "#a7c47a")))
            p.drawPolygon(polys[i][1])

        # 2. terrain sprites (mountains, plants ...)
        if self.layers["terrain"] and img and lod > 0.08:
            for c, r, i in cells:
                t = d.terrain(i)
                ctr = polys[i][0]
                for tk, ik, xk, yk in (("terrain", "tile", "tx", "ty"), ("a_terrain", "a_tile", "ax", "ay"),
                                       ("b_terrain", "b_tile", "bx", "by")):
                    tid = t[tk]
                    if tid in (0, 1, 63, 255):
                        continue
                    name = game.terrain_tiles.get(tid, {}).get(t[ik])
                    if not name:
                        continue
                    part = img.part("terrain_hd", name) or img.part("plant_hd", name)
                    if part:
                        pm, rx, ry = part
                        p.drawPixmap(QPointF(ctr.x() + 2 * t[xk] - rx, ctr.y() + 2 * t[yk] - ry), pm)

        # 3. ownership colour (by the owner of the hex's province city, as the game does)
        if self.layers["owners"]:
            for c, r, i in cells:
                o = d.province_owner(i)
                if o == NO_OWNER:
                    o = owners[i]
                if o != NO_OWNER and o < len(factions) and not d.is_sea(i):
                    p.setBrush(faction_color(factions[o], 105))
                    p.drawPolygon(polys[i][1])

        # 4. borders and grid
        if self.layers["grid"]:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 60), 1.0 / max(lod, 0.05)))
            for c, r, i in cells:
                p.drawPolygon(polys[i][1])
        if self.layers["borders"] and lod > 0.04:
            thin = QPen(QColor(40, 40, 40, 110), 2.0)
            for c, r, i in cells:
                if d.is_sea(i):
                    continue
                prov = d.btl.provinces[i]
                own = d.province_owner(i)
                poly = polys[i][1]
                for k, (nc, nr) in enumerate(neighbours(c, r)):
                    if not (0 <= nc < W and 0 <= nr < d.H):
                        continue
                    j = nr * W + nc
                    if d.is_sea(j):
                        continue
                    if d.province_owner(j) != own:
                        f = factions[own] if own < len(factions) else None
                        p.setPen(QPen(faction_color(f).darker(170) if f else QColor(30, 30, 30), 7.0))
                    elif d.btl.provinces[j] != prov:
                        p.setPen(thin)
                    else:
                        continue
                    p.drawLine(poly[k], poly[(k + 1) % 6])

        # 5. province painting / multi selection / crop overlays
        p.setPen(Qt.NoPen)
        if self.mode == MODE_PROVINCE and self.province_anchor is not None:
            p.setBrush(QColor(255, 220, 0, 120))
            for c, r, i in cells:
                if i in self.province_set:
                    p.drawPolygon(polys[i][1])
            a = self.province_anchor
            if a in polys:
                p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor("#ff2"), 8)); p.drawPolygon(polys[a][1]); p.setPen(Qt.NoPen)
        if self.multi:
            p.setBrush(QColor(0, 220, 255, 95))
            for c, r, i in cells:
                if i in self.multi:
                    p.drawPolygon(polys[i][1])

        # 6. objects
        font = QFont("Segoe UI", 18)
        font.setBold(True)
        p.setFont(font)
        for c, r, i in cells:
            ctr = polys[i][0]
            if self.layers["cities"] and i in d.city_at:
                self.draw_city(p, ctr, d.city_at[i], i, lod)
            if self.layers["markers"]:
                self.draw_markers(p, ctr, i, lod)
            if self.layers["troops"] and i in d.troop_at:
                if self._drag_troop and self._drag_troop[0] == i:
                    continue
                self.draw_troop(p, ctr, d.troop_at[i], i, lod)
            if self.layers["coords"] and lod > 0.25:
                p.setPen(QColor(0, 0, 0, 160))
                f2 = QFont(font); f2.setPixelSize(16); f2.setBold(False); p.setFont(f2)
                p.drawText(QRectF(ctr.x() - 60, ctr.y() - 62, 120, 22), Qt.AlignCenter, "%d,%d" % (c, r))
                p.setFont(font)

        if self._drag_troop:
            src, pos = self._drag_troop
            p.setOpacity(0.75)
            self.draw_troop(p, pos, d.troop_at[src], src, lod)
            p.setOpacity(1.0)

        # 7. hover, selection, crop rectangle
        p.setBrush(Qt.NoBrush)
        if self.hover is not None and self.hover in polys:
            p.setPen(QPen(QColor(255, 255, 255, 170), 4))
            p.drawPolygon(polys[self.hover][1])
        if self.selected is not None and self.selected in polys:
            p.setPen(QPen(QColor("#ffd400"), 9))
            p.drawPolygon(polys[self.selected][1])
        if self.crop_rect:
            x0, y0, x1, y1 = self.crop_rect
            a, b = hex_center(min(x0, x1), min(y0, y1)), hex_center(max(x0, x1), max(y0, y1))
            p.setPen(QPen(QColor("#ff3030"), 10, Qt.DashLine))
            p.drawRect(QRectF(a.x() - HEX_R, a.y() - HALF_H - HALF_H, b.x() - a.x() + 2 * HEX_R, b.y() - a.y() + 3 * HALF_H))

    def draw_city(self, p, ctr, rec, i, lod):
        part = self.images.city(rec) if self.images else None
        if part:
            pm, rx, ry = part
            s = 0.75
            w, h = pm.width() * s, pm.height() * s
            p.drawPixmap(QRectF(ctr.x() - w / 2, ctr.y() - h / 2 - 10, w, h), pm, QRectF(pm.rect()))
        else:
            p.setBrush(QColor("#dddddd")); p.setPen(QPen(QColor("#333"), 3))
            p.drawRect(QRectF(ctr.x() - 22, ctr.y() - 22, 44, 44))
        if self.layers["names"] and lod > 0.12:
            name = self.game.city_name(rec["name"]) if self.game else ""
            if i in self.doc.cityhp_at:
                hp = self.doc.cityhp_at[i]
                name = (name + "  " if name else "") + "HP %d" % hp["hp_max"]
            if name:
                rect = QRectF(ctr.x() - 110, ctr.y() + 30, 220, 30)
                path = QPainterPath()
                f = p.font()
                path.addText(QPointF(0, 0), f, name)
                br = path.boundingRect()
                path.translate(rect.center().x() - br.center().x(), rect.center().y() - br.center().y())
                p.setPen(QPen(QColor(0, 0, 0, 200), 5)); p.setBrush(Qt.NoBrush); p.drawPath(path)
                p.setPen(Qt.NoPen); p.setBrush(QColor("white")); p.drawPath(path)

    def draw_markers(self, p, ctr, i, lod):
        d = self.doc
        x, y = ctr.x(), ctr.y()
        if i in d.capital_at:
            p.setPen(QPen(QColor("#202020"), 3)); p.setBrush(QColor("#ffd400"))
            star = QPolygonF([QPointF(x + 44 + 16 * math.cos(math.pi / 2 + k * math.pi / 5) * (1 if k % 2 == 0 else 0.45),
                                      y - 40 - 16 * math.sin(math.pi / 2 + k * math.pi / 5) * (1 if k % 2 == 0 else 0.45))
                              for k in range(10)])
            p.drawPolygon(star)
        if i in d.mine_at:
            m = d.mine_at[i]
            p.setPen(QPen(QColor("#000"), 3)); p.setBrush(QColor("#e04040") if m["army"] != 34 else QColor("#4060e0"))
            p.drawEllipse(QPointF(x - 46, y + 34), 13, 13)
            p.setPen(QColor("white")); p.drawText(QRectF(x - 60, y + 20, 28, 28), Qt.AlignCenter, str(m["level"]))
        if lod > 0.12:
            tags = []
            if d.reinf_at.get(i):
                tags.append(("+%d" % len(d.reinf_at[i]), "#2e8b57"))
            if d.airraid_at.get(i):
                tags.append(("AIR %d" % len(d.airraid_at[i]), "#6a5acd"))
            if d.deploy_at.get(i):
                tags.append(("DEPLOY", "#b8860b"))
            yy = y - 60
            for text, col in tags:
                p.setPen(Qt.NoPen); p.setBrush(QColor(col))
                p.drawRoundedRect(QRectF(x - 70, yy, 64, 24), 6, 6)
                p.setPen(QColor("white"))
                f = p.font(); f2 = QFont(f); f2.setPixelSize(15); p.setFont(f2)
                p.drawText(QRectF(x - 70, yy, 64, 24), Qt.AlignCenter, text)
                p.setFont(f)
                yy += 27

    def draw_troop(self, p, ctr, t, i, lod):
        d, game = self.doc, self.game
        x, y = ctr.x(), ctr.y()
        code = t["army"]
        ttype = game.army_type(code) if game else 0
        elite = game.is_elite(code) if game else False
        f = d.owner_faction(i)
        base = faction_color(f) if f else QColor("#888888")
        box = QRectF(x - 46, y - 24, 92, 50)
        p.setPen(QPen(QColor("#ffcc33") if elite else base.darker(220), 5 if elite else 3))
        p.setBrush(base)
        p.drawRoundedRect(box, 9, 9)
        band = QRectF(box.x() + 3, box.y() + 3, 24, box.height() - 6)
        p.setPen(Qt.NoPen); p.setBrush(QColor(TYPE_COLORS.get(ttype, "#555")))
        p.drawRoundedRect(band, 5, 5)
        light = base.lightness() > 150
        p.setPen(QColor("#111") if light else QColor("white"))
        fnt = p.font()
        f2 = QFont(fnt); f2.setPixelSize(17); p.setFont(f2)
        p.drawText(QRectF(box.x() + 28, box.y() + 2, 62, 24), Qt.AlignCenter, ARMY_TYPE_SHORT.get(ttype, "?"))
        f3 = QFont(fnt); f3.setPixelSize(15); f3.setBold(False); p.setFont(f3)
        p.drawText(QRectF(box.x() + 28, box.y() + 24, 62, 22), Qt.AlignCenter, "#%d" % code)
        p.setFont(fnt)
        # formation pips in the type band
        p.setBrush(QColor("white")); p.setPen(Qt.NoPen)
        for k in range(max(0, min(4, t["formation"]))):
            p.drawRect(QRectF(band.x() + 6, band.bottom() - 9 - k * 10, 12, 6))
        # level / tier badge
        lv = t["level"]
        if lv > 1 or elite:
            r = QRectF(box.right() - 14, box.y() - 16, 30, 26)
            p.setBrush(QColor("#ffcc33") if elite else QColor("#e8e8e8")); p.setPen(QPen(QColor("#222"), 2))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QColor("#111"))
            f4 = QFont(fnt); f4.setPixelSize(17); p.setFont(f4)
            p.drawText(r, Qt.AlignCenter, str(lv))
            p.setFont(fnt)
        # morale
        m = t["morale"]
        if m:
            p.setPen(QPen(QColor("#111"), 2))
            p.setBrush(QColor("#3c3") if m > 0 else QColor("#e33") if m >= -2 else QColor("#a0a"))
            p.drawEllipse(QPointF(box.x() + 2, box.bottom() + 2), 9, 9)
        # HP bar
        if t["hp_max"] > 0:
            frac = max(0.0, min(1.0, t["hp"] / float(t["hp_max"])))
            p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 160)); p.drawRect(QRectF(box.x(), box.bottom() + 4, box.width(), 7))
            p.setBrush(QColor("#4c4") if frac > 0.5 else QColor("#ec4") if frac > 0.25 else QColor("#e44"))
            p.drawRect(QRectF(box.x(), box.bottom() + 4, box.width() * frac, 7))
        if t["shield"] == 9:
            p.setPen(QPen(QColor("#222"), 2)); p.setBrush(QColor("#c0c0c0"))
            p.drawEllipse(QPointF(box.right() + 4, box.bottom() - 2), 9, 9)
        # flag and general head
        if self.layers["flags"] and f is not None and self.images and lod > 0.1:
            fl = self.images.flag(f["country"])
            if fl:
                pm = fl[0]
                s = 34.0 / max(1, pm.height())
                p.drawPixmap(QRectF(box.x() - 12, box.y() - 30, pm.width() * s, 34), pm, QRectF(pm.rect()))
        if self.layers["generals"] and t["general"] > 0 and self.images and lod > 0.1:
            g = game.general(t["general"]) if game else None
            pm = self.images.head(g)
            r = QRectF(x - 6, y - 92, 64, 64)
            if pm:
                p.drawPixmap(r, pm, QRectF(pm.rect()))
            else:
                p.setBrush(QColor("#ddd")); p.setPen(QPen(QColor("#333"), 2)); p.drawEllipse(r)
                p.setPen(QColor("#111")); p.drawText(r, Qt.AlignCenter, "G")

    # ------------------------------------------------------------------ mouse
    def hex_at(self, pos):
        if not self.doc:
            return None
        sp = self.mapToScene(pos)
        h = pick_hex(sp.x(), sp.y(), self.doc.W, self.doc.H)
        return None if h is None else h[1] * self.doc.W + h[0]

    def wheelEvent(self, ev):
        self.zoom(1.18 if ev.angleDelta().y() > 0 else 1 / 1.18)

    def mousePressEvent(self, ev):
        if not self.doc:
            return
        if ev.button() == Qt.MiddleButton or (ev.button() == Qt.LeftButton and ev.modifiers() & Qt.AltModifier):
            self._pan = ev.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        i = self.hex_at(ev.position().toPoint())
        self._press = (ev.button(), ev.position(), i)
        if i is None:
            if ev.button() == Qt.RightButton:
                self._pan = ev.position(); self.setCursor(Qt.ClosedHandCursor)
            return
        if self.mode == MODE_SELECT:
            if ev.button() == Qt.RightButton:
                self._pan = ev.position(); self.setCursor(Qt.ClosedHandCursor)
        elif self.mode == MODE_MULTI:
            self._paint_add = ev.button() == Qt.LeftButton
            self._paint(i, self.multi)
        elif self.mode == MODE_PROVINCE:
            self._paint_add = ev.button() == Qt.LeftButton
            self._paint(i, self.province_set)
        elif self.mode == MODE_CROP and ev.button() == Qt.LeftButton:
            c, r = self.doc.xy(i)
            self._crop_start = (c, r)
            self.crop_rect = (c, r, c, r)
            self.cropChanged.emit(*self.crop_rect)
            self.viewport().update()

    def _paint(self, i, target):
        if self._paint_add:
            target.add(i)
        else:
            target.discard(i)
        self.selectionChanged.emit()
        self.viewport().update()

    def mouseMoveEvent(self, ev):
        if not self.doc:
            return
        if self._pan is not None:
            delta = ev.position() - self._pan
            self._pan = ev.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y()))
            return
        i = self.hex_at(ev.position().toPoint())
        if i != self.hover:
            self.hover = i
            if i is not None:
                self.hexHovered.emit(i)
            self.viewport().update()
        if self._press and ev.buttons():
            btn, start, si = self._press
            if self.mode == MODE_SELECT and btn == Qt.LeftButton and si in self.doc.troop_at:
                if (ev.position() - start).manhattanLength() > 8 or self._drag_troop:
                    self._drag_troop = (si, self.mapToScene(ev.position().toPoint()))
                    self.viewport().update()
            elif self.mode in (MODE_MULTI, MODE_PROVINCE) and i is not None:
                self._paint(i, self.multi if self.mode == MODE_MULTI else self.province_set)
            elif self.mode == MODE_CROP and self._crop_start and i is not None:
                c, r = self.doc.xy(i)
                self.crop_rect = (self._crop_start[0], self._crop_start[1], c, r)
                self.cropChanged.emit(*self.crop_rect)
                self.viewport().update()

    def mouseReleaseEvent(self, ev):
        if self._pan is not None:
            self._pan = None
            self._press = None
            self.setCursor(Qt.ArrowCursor)
            return
        if not self.doc or not self._press:
            return
        btn, start, si = self._press
        self._press = None
        i = self.hex_at(ev.position().toPoint())
        if self._drag_troop:
            src = self._drag_troop[0]
            self._drag_troop = None
            if i is not None and i != src and i not in self.doc.troop_at:
                self.doc.begin()
                self.doc.move_troop(src, i)
                self.selected = i
                self.docChanged.emit("Move troop")
                self.hexClicked.emit(i)
            self.viewport().update()
            return
        if self.mode == MODE_SELECT and btn == Qt.LeftButton and i is not None and i == si:
            self.selected = i
            self.hexClicked.emit(i)
            self.viewport().update()
        self._crop_start = None


HEX_W_PAD = 2 * HEX_R
