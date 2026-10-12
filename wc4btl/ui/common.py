"""Shared UI helpers: hex geometry, atlas image cache, colours."""
import math
import os

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap, QPolygonF, QIcon

# Flat-top hexes, odd columns shifted down by half a row (verified against province connectivity of all maps).
HEX_R = 74.0                  # centre to corner
HEX_W = 2 * HEX_R             # 148
HEX_H = 129.0                 # row pitch (EModule TileHeight)
COL_STEP = 1.5 * HEX_R        # 111
HALF_H = HEX_H / 2.0


def hex_center(c, r):
    return QPointF(COL_STEP * c + HEX_R, HEX_H * r + HALF_H + (HALF_H if c & 1 else 0.0))


def hex_polygon(cx, cy, scale=1.0):
    rx, hy = HEX_R * scale, HALF_H * scale
    return QPolygonF([QPointF(cx + rx, cy), QPointF(cx + rx / 2, cy + hy), QPointF(cx - rx / 2, cy + hy),
                      QPointF(cx - rx, cy), QPointF(cx - rx / 2, cy - hy), QPointF(cx + rx / 2, cy - hy)])


# polygon corner order above: 0 E, 1 SE, 2 SW, 3 W, 4 NW, 5 NE.  Edge k joins corner k and k+1.
# Neighbour across each edge for odd-q layout:
def neighbours(c, r):
    if c & 1:   # shifted down
        return [(c + 1, r + 1), (c, r + 1), (c - 1, r + 1), (c - 1, r), (c, r - 1), (c + 1, r)]
    return [(c + 1, r), (c, r + 1), (c - 1, r), (c - 1, r - 1), (c, r - 1), (c + 1, r - 1)]


def pick_hex(x, y, W, H):
    c0 = int(x // COL_STEP)
    best, bd = None, 1e18
    for c in (c0 - 1, c0, c0 + 1):
        if c < 0 or c >= W:
            continue
        r0 = int((y - (HALF_H if c & 1 else 0)) // HEX_H)
        for r in (r0 - 1, r0, r0 + 1):
            if 0 <= r < H:
                p = hex_center(c, r)
                d = (p.x() - x) ** 2 + (p.y() - y) ** 2
                if d < bd:
                    best, bd = (c, r), d
    if best is None or bd > HEX_R * HEX_R * 1.2:
        return None
    return best


def map_size(W, H):
    return QRectF(0, 0, COL_STEP * (W - 1) + HEX_W, HEX_H * H + HALF_H)


TERRAIN_COLORS = {0: "#a7c47a", 1: "#3f78b5", 2: "#dcc58c", 3: "#b3b377", 4: "#968f78", 5: "#d6d6d6", 6: "#86ad5d",
                  7: "#6b9650", 8: "#bccf73", 9: "#5f95c9", 10: "#a7c47a"}


def faction_color(f, alpha=None):
    if f is None:
        return QColor(255, 255, 255, alpha if alpha is not None else 255)
    return QColor(f["r"], f["g"], f["b"], alpha if alpha is not None else 255)


class ImageCache:
    """Loads game atlases once and cuts sub-images on demand."""

    def __init__(self, game):
        self.game = game
        self._sheets = {}
        self._parts = {}
        self._files = {}

    def sheet(self, atlas):
        if atlas not in self._sheets:
            a = self.game.atlases.get(atlas) if self.game else None
            self._sheets[atlas] = QImage(a.image_path) if a else QImage()
        return self._sheets[atlas]

    def part(self, atlas, name):
        """(QPixmap, refx, refy) or None."""
        key = (atlas, name)
        if key in self._parts:
            return self._parts[key]
        res = None
        a = self.game.atlases.get(atlas) if self.game else None
        if a is not None and name:
            rect = a.get(name)
            img = self.sheet(atlas)
            if rect and not img.isNull():
                x, y, w, h, rx, ry = rect
                sub = img.copy(int(x), int(y), max(1, int(w)), max(1, int(h)))
                res = (QPixmap.fromImage(sub), rx, ry)
        self._parts[key] = res
        return res

    def file(self, path):
        if not path:
            return None
        if path not in self._files:
            img = QImage(path)
            self._files[path] = QPixmap.fromImage(img) if not img.isNull() else None
        return self._files[path]

    def icon(self, atlas, name, size=32):
        p = self.part(atlas, name)
        if not p:
            return QIcon()
        return QIcon(p[0].scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def flag(self, country):
        return self.part("tacticalmap", "f_%02d.png" % country) or self.part("image_flags_hd", "flag_%d.png" % country)

    def head(self, general_row):
        if not general_row:
            return None
        p = self.part("tacticalmap", "head_%s.png" % general_row.get("EName"))
        if p:
            return p[0]
        path = None
        if self.game and self.game.assets:
            for ext in (".webp", ".png"):
                cand = os.path.join(self.game.assets, "image", "heads",
                                    "general_circle_%s%s" % (general_row.get("Photo") or general_row.get("EName"), ext))
                if os.path.exists(cand):
                    path = cand
                    break
        return self.file(path)

    def city(self, rec):
        """Building sprite for a city record, following EModule's choice of image."""
        if rec is None:
            return None
        w = rec["wonder"]
        if w:
            p = self.part("buildings_hd", "capital_%02d.png" % w)
            if p:
                return p
        b = rec["building"]
        names = []
        if 31 <= b <= 34:
            names.append("building_31_%d.png" % max(1, min(4, rec["look"] or (b - 30))))
        if 15 <= b <= 19:
            names.append("building_15.png")
        names += ["building_%d.png" % b, "building_11.png"]
        for n in names:
            p = self.part("buildings_hd", n)
            if p:
                return p
        return None


def settings():
    return QSettings("WC4Modding", "BtlEditorPC")


def letter_icon(text, color="#4a6", size=20):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, size, size, 4, 4)
    p.setPen(QColor("white"))
    f = p.font(); f.setBold(True); f.setPixelSize(int(size * 0.6)); p.setFont(f)
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, text)
    p.end()
    return QIcon(pm)
