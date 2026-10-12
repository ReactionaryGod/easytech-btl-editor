"""Draws a Glory of Generals 3 map inside the shared MapView.

GoG3 hexes have the same layout as WC4's (flat-top, odd columns shifted down) but are drawn at radius 93 in the
game's art (coast masks are 186 x 162), so every sprite is scaled by HEX_R / 93."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen, QPolygonF

from wc4btl.ui.common import HALF_H, HEX_R, hex_center, hex_polygon, neighbours
from ..format import HEX_DISABLED

S = HEX_R / 93.0
GROUND_COLORS = {0: "#b5a77c", 1: "#9dbb68", 2: "#dfca8f", 3: "#e9eef1", 4: "#9f9f8a"}
SEA_COLOR = "#4f84b8"
KEY_COLORS = {0: "#bbbbbb", 1: "#ffd400", 2: "#ff8a00", 3: "#ff5050", 4: "#9a9a9a", 5: "#40d0ff"}
FORT_LETTER = {1: "R", 2: "T", 3: "B", 4: "F", 5: "C"}


def paint(view, p, rect):
    d, game, img = view.doc, view.game, view.images
    lod = p.worldTransform().m11()
    c0, c1, r0, r1 = view.visible_range(rect)
    W = d.W
    cells = [(c, r, r * W + c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]
    polys = {}
    for c, r, i in cells:
        ctr = hex_center(c, r)
        polys[i] = (ctr, hex_polygon(ctr.x(), ctr.y()))
    hexes = d.b["map"]["hexes"]

    # 1. ground / sea
    p.setPen(Qt.NoPen)
    for c, r, i in cells:
        v = hexes[i]
        p.setBrush(QColor(SEA_COLOR if d.is_sea(i) else GROUND_COLORS.get(v & 7, "#a0a080")))
        p.drawPolygon(polys[i][1])

    # 2. terrain sprites, layer by layer (A decorations, B main terrain, C canopies/peaks)
    if view.layers["terrain"] and img and game and lod > 0.06:
        for layer in ("A", "B", "C"):
            for c, r, i in cells:
                o = d.overlay(i, layer)
                if not o or not o["terrain"]:
                    continue
                sp = game.sprite(o["terrain"], o["tile"])
                part = img.part(*sp) if sp else None
                if not part:
                    continue
                pm, rx, ry = part
                ctr = polys[i][0]
                p.drawPixmap(QRectF(ctr.x() + (o["dx"] - rx) * S, ctr.y() + (o["dy"] - ry) * S, pm.width() * S,
                                    pm.height() * S), pm, QRectF(pm.rect()))

    # 3. ownership tint
    owner = {}
    if view.layers["owners"] or view.layers["borders"]:
        for c, r, i in cells:
            owner[i] = d.owner_of_hex(i)
    if view.layers["owners"]:
        for c, r, i in cells:
            o = owner[i]
            if o is not None and not d.is_sea(i):
                p.setBrush(QColor(*d.faction_rgb(o), 95))
                p.drawPolygon(polys[i][1])

    # 4. outside-the-battlefield shading, grid, borders, view rectangle
    p.setBrush(QColor(0, 0, 0, 105))
    for c, r, i in cells:
        if hexes[i] & HEX_DISABLED:
            p.drawPolygon(polys[i][1])
    if view.layers["grid"]:
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 60), 1.0 / max(lod, 0.05)))
        for c, r, i in cells:
            p.drawPolygon(polys[i][1])
    if view.layers["borders"] and d.province is not None and lod > 0.04:
        thin = QPen(QColor(40, 40, 40, 110), 2.0)
        for c, r, i in cells:
            if d.is_sea(i):
                continue
            poly = polys[i][1]
            for k, (nc, nr) in enumerate(neighbours(c, r)):
                if not (0 <= nc < W and 0 <= nr < d.H):
                    continue
                j = nr * W + nc
                if d.is_sea(j):
                    continue
                oj = owner.get(j, d.owner_of_hex(j))
                if oj != owner[i]:
                    rgb = d.faction_rgb(owner[i]) if owner[i] is not None else (30, 30, 30)
                    p.setPen(QPen(QColor(*rgb).darker(170), 7.0))
                elif d.province[j] != d.province[i]:
                    p.setPen(thin)
                else:
                    continue
                p.drawLine(poly[k], poly[(k + 1) % 6])
    size = d.b["map"].get("size", {})
    if size.get("view_w"):
        a = hex_center(size["view_x"], size["view_y"])
        b = hex_center(size["view_x"] + size["view_w"] - 1, size["view_y"] + size["view_h"] - 1)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 120), 4, Qt.DashLine))
        p.drawRect(QRectF(a.x() - HEX_R, a.y() - HALF_H, b.x() - a.x() + 2 * HEX_R, b.y() - a.y() + 3 * HALF_H))

    # 5. multi selection
    p.setPen(Qt.NoPen)
    if view.multi:
        p.setBrush(QColor(0, 220, 255, 95))
        for c, r, i in cells:
            if i in view.multi:
                p.drawPolygon(polys[i][1])

    # 6. areas, key areas, armies
    font = QFont("Segoe UI", 18)
    font.setBold(True)
    p.setFont(font)
    for c, r, i in cells:
        ctr = polys[i][0]
        if view.layers["cities"] and i in d.area_at:
            draw_area(view, p, ctr, d.area_at[i], lod)
        if view.layers["markers"]:
            draw_markers(view, p, ctr, i, lod)
    for c, r, i in cells:
        if view.layers["troops"] and i in d.army_at:
            if view._drag_troop and view._drag_troop[0] == i:
                continue
            draw_army(view, p, polys[i][0], d.army_at[i], lod)
        if view.layers["coords"] and lod > 0.25:
            p.setPen(QColor(0, 0, 0, 160))
            f2 = QFont(font); f2.setPixelSize(16); f2.setBold(False); p.setFont(f2)
            ctr = polys[i][0]
            p.drawText(QRectF(ctr.x() - 60, ctr.y() - 62, 120, 22), Qt.AlignCenter, "%d,%d" % (c, r))
            p.setFont(font)
    if view._drag_troop:
        src, pos = view._drag_troop
        if src in d.army_at:
            p.setOpacity(0.75)
            draw_army(view, p, pos, d.army_at[src], lod)
            p.setOpacity(1.0)

    # 7. hover and selection
    p.setBrush(Qt.NoBrush)
    if view.hover is not None and view.hover in polys:
        p.setPen(QPen(QColor(255, 255, 255, 170), 4))
        p.drawPolygon(polys[view.hover][1])
    if view.selected is not None and view.selected in polys:
        p.setPen(QPen(QColor("#ffd400"), 9))
        p.drawPolygon(polys[view.selected][1])


def outlined_text(p, rect, text):
    path = QPainterPath()
    path.addText(QPointF(0, 0), p.font(), text)
    br = path.boundingRect()
    path.translate(rect.center().x() - br.center().x(), rect.center().y() - br.center().y())
    p.setPen(QPen(QColor(0, 0, 0, 200), 5)); p.setBrush(Qt.NoBrush); p.drawPath(path)
    p.setPen(Qt.NoPen); p.setBrush(QColor("white")); p.drawPath(path)


def building_sprite(img, info):
    bid = info.get("building", 0)
    base = "b_%d%s" % (bid, "s" if info.get("style") == 2 else "")
    names = [base + "_%d.png" % (info.get("variant", 0) + 1), base + ".png", "b_%d_1.png" % bid, "b_%d.png" % bid]
    for n in names:
        part = img.part("buildings", n)
        if part:
            return part
    return None


def draw_area(view, p, ctr, area, lod):
    d, img, game = view.doc, view.images, view.game
    b = area.get("building")
    if b and "info" in b:
        part = building_sprite(img, b["info"]) if img else None
        if part:
            pm, rx, ry = part
            p.drawPixmap(QRectF(ctr.x() - rx * S, ctr.y() - ry * S, pm.width() * S, pm.height() * S), pm, QRectF(pm.rect()))
        else:
            p.setBrush(QColor("#dddddd")); p.setPen(QPen(QColor("#333"), 3))
            p.drawRect(QRectF(ctr.x() - 22, ctr.y() - 22, 44, 44))
        owner = b["info"].get("owner")
        if owner in d.factions:
            p.setBrush(QColor(*d.faction_rgb(owner))); p.setPen(QPen(QColor("#111"), 2))
            p.drawEllipse(QPointF(ctr.x() + 52, ctr.y() + 30), 11, 11)
    if view.layers["names"] and lod > 0.12 and area.get("name") and game:
        name = game.city_name(area["name"])
        if name:
            outlined_text(p, QRectF(ctr.x() - 110, ctr.y() + 32, 220, 30), name)


def draw_markers(view, p, ctr, i, lod):
    d = view.doc
    x, y = ctr.x(), ctr.y()
    k = d.key_at.get(i)
    if k is not None:
        p.setPen(QPen(QColor("#202020"), 3)); p.setBrush(QColor(KEY_COLORS.get(k.get("key", 0), "#ffd400")))
        star = QPolygonF([QPointF(x - 44 + 18 * math.cos(math.pi / 2 + j * math.pi / 5) * (1 if j % 2 == 0 else 0.45),
                                  y - 40 - 18 * math.sin(math.pi / 2 + j * math.pi / 5) * (1 if j % 2 == 0 else 0.45))
                          for j in range(10)])
        p.drawPolygon(star)
    a = d.area_at.get(i)
    if a and "fortification" in a and lod > 0.1:
        t = a["fortification"].get("type", 0)
        r = QRectF(x - 66, y + 14, 28, 28)
        p.setPen(QPen(QColor("#111"), 2)); p.setBrush(QColor("#8a6d3b"))
        p.drawRoundedRect(r, 5, 5)
        p.setPen(QColor("white"))
        f = p.font(); f2 = QFont(f); f2.setPixelSize(18); p.setFont(f2)
        p.drawText(r, Qt.AlignCenter, FORT_LETTER.get(t, "?"))
        p.setFont(f)


def draw_army(view, p, ctr, a, lod):
    d, game, img = view.doc, view.game, view.images
    x, y = ctr.x(), ctr.y()
    info = a["info"]
    fid = info.get("faction")
    base = QColor(*d.faction_rgb(fid))
    elite = "exarmy" in a
    box = QRectF(x - 46, y - 26, 92, 54)
    p.setPen(QPen(QColor("#ffcc33") if elite else base.darker(220), 5 if elite else 3))
    p.setBrush(base)
    p.drawRoundedRect(box, 9, 9)
    icon = img.part("image_army_icon", "icon_army_%d.png" % info.get("army", 0)) if img else None
    if icon and lod > 0.08:
        pm = icon[0]
        p.drawPixmap(QRectF(box.x() + 3, box.y() + 3, 40, 47), pm, QRectF(pm.rect()))
    light = base.lightness() > 150
    p.setPen(QColor("#111") if light else QColor("white"))
    fnt = p.font()
    f2 = QFont(fnt); f2.setPixelSize(17); p.setFont(f2)
    p.drawText(QRectF(box.x() + 42, box.y() + 2, 48, 26), Qt.AlignCenter, game.army_short(info.get("army", 0)) if game else "?")
    f3 = QFont(fnt); f3.setPixelSize(14); f3.setBold(False); p.setFont(f3)
    p.drawText(QRectF(box.x() + 42, box.y() + 26, 48, 24), Qt.AlignCenter, "#%d" % info.get("serial", 0))
    p.setFont(fnt)
    # sub-unit count pips
    p.setBrush(QColor("white")); p.setPen(QPen(QColor("#222"), 1))
    for k in range(max(0, min(4, info.get("number", 0)))):
        p.drawRect(QRectF(box.right() - 8, box.bottom() - 12 - k * 11, 7, 8))
    # HP bar
    if info.get("max_hp", 0) > 0:
        frac = max(0.0, min(1.0, info.get("hp", 0) / float(info["max_hp"])))
        p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 160)); p.drawRect(QRectF(box.x(), box.bottom() + 4, box.width(), 7))
        p.setBrush(QColor("#4c4") if frac > 0.5 else QColor("#ec4") if frac > 0.25 else QColor("#e44"))
        p.drawRect(QRectF(box.x(), box.bottom() + 4, box.width() * frac, 7))
    # morale dot (game default 80)
    m = a.get("morale")
    if m is not None and m != 80:
        p.setPen(QPen(QColor("#111"), 2))
        p.setBrush(QColor("#3c3") if m > 80 else QColor("#ec4") if m > 50 else QColor("#e33"))
        p.drawEllipse(QPointF(box.x() + 2, box.bottom() + 2), 9, 9)
    # flag
    c = d.factions.get(fid)
    if view.layers["flags"] and c and img and lod > 0.1:
        fl = img.part("image_flag", "country_flag_%d.png" % c["info"].get("country", 0))
        if fl:
            pm = fl[0]
            p.drawPixmap(QRectF(box.x() - 14, box.y() - 30, 34, 34), pm, QRectF(pm.rect()))
    # general portrait
    g = a.get("general")
    if view.layers["generals"] and g and img and game and lod > 0.1:
        name = game.head_name(g.get("id", 0))
        part = img.part("image_generalhead", name) if name else None
        r = QRectF(x - 2, y - 94, 54, 63)
        if part:
            pm = part[0]
            p.drawPixmap(r, pm, QRectF(pm.rect()))
        else:
            p.setBrush(QColor("#ddd")); p.setPen(QPen(QColor("#333"), 2)); p.drawEllipse(r)
            p.setPen(QColor("#111")); p.drawText(r, Qt.AlignCenter, "G")
