"""Craft Lab's pictures, all drawn by code here (CHANGE 200): every block face, item icon, crop stage, digging crack
and creature face as a 16 x 16 pixel tile, packed into one texture atlas (16 x 16 tiles). Nothing is copied from
anywhere: each tile is a few lines of numpy (a base colour, noise, a pattern), seeded by the tile's own name, so
the atlas is the same on every computer. The atlas is made the first time a window needs it and kept in
assets/atlas_<version>.png; mods' blocks get a plain tile in their own colour.

    python craft_art.py            makes the atlas and a big copy to look at (assets/atlas_big.png)
"""
import os
import zlib

import numpy as np

import craft_blocks as B

ART_VERSION = "2"   # (2: armour)
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
T = B.TILE


def rng(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def rgb(hexcode):
    h = hexcode.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def tile(base, noise=18.0, name="", alpha=255):
    """A tile of colour base with per-pixel noise (a float array H x W x 4)."""
    r = rng(name)
    img = np.zeros((T, T, 4), np.float32)
    img[..., :3] = rgb(base) if isinstance(base, str) else np.array(base, np.float32)
    img[..., :3] += (r.random((T, T, 1)) - 0.5) * 2 * noise
    img[..., 3] = alpha
    return img


def blotch(img, colour, n, size, name, alpha=None):
    """n soft blotches of colour (ores' clusters, moss, berries)."""
    r = rng(name + "blotch")
    c = rgb(colour) if isinstance(colour, str) else np.array(colour, np.float32)
    for _ in range(n):
        cx, cy = r.integers(1, T - 1, 2)
        for dx in range(-size, size + 1):
            for dy in range(-size, size + 1):
                if dx * dx + dy * dy <= size * size + r.integers(0, 2):
                    x, y = (cx + dx) % T, (cy + dy) % T
                    img[y, x, :3] = c + (r.random(3) - 0.5) * 30
                    if alpha is not None:
                        img[y, x, 3] = alpha
    return img


def speckle(img, colour, share, name):
    r = rng(name + "speckle")
    mask = r.random((T, T)) < share
    img[mask, :3] = rgb(colour) + (r.random((int(mask.sum()), 3)) - 0.5) * 20
    return img


def cells(base, edge, name, n=7):
    """Cobbles: Voronoi cells of base with dark edges."""
    r = rng(name + "cells")
    pts = r.random((n, 2)) * T
    yy, xx = np.mgrid[0:T, 0:T] + 0.5
    d = np.full((T, T, n), 1e9)
    for i, (px, py) in enumerate(pts):
        for ox in (-T, 0, T):
            for oy in (-T, 0, T):
                d[..., i] = np.minimum(d[..., i], np.hypot(xx - px - ox, yy - py - oy))
    s = np.sort(d, axis=2)
    img = tile(base, 14, name)
    shade = (r.random(n) - 0.5) * 40
    img[..., :3] += shade[np.argmin(d, axis=2)][..., None]
    img[(s[..., 1] - s[..., 0]) < 1.1, :3] = rgb(edge)
    return img


def bricks(base, mortar, name, h=4, w=8):
    img = tile(base, 16, name)
    for y in range(T):
        row = y // h
        if y % h == 0:
            img[y, :, :3] = rgb(mortar)
        off = (w // 2) * (row % 2)
        for x in range(T):
            if (x + off) % w == 0:
                img[y, x, :3] = rgb(mortar)
    return img


def boards(base, seam, name, vertical=False):
    img = tile(base, 10, name)
    r = rng(name + "boards")
    for y in range(T):
        if y % 4 == 3:
            img[y, :, :3] = rgb(seam)
        else:
            img[y, :, :3] += (r.random() - 0.5) * 18
    for row in range(4):
        x = int(r.integers(0, T))
        img[row * 4:row * 4 + 3, x, :3] = rgb(seam)
    return np.transpose(img, (1, 0, 2)).copy() if vertical else img


def bark(base, dark, name):
    img = tile(base, 12, name)
    r = rng(name + "bark")
    for x in range(T):
        if r.random() < 0.35:
            img[:, x, :3] = rgb(dark) + (r.random((T, 1)) - 0.5) * 20
    return img


def rings(outer, inner, name):
    img = tile(inner, 8, name)
    yy, xx = np.mgrid[0:T, 0:T] + 0.5
    d = np.hypot(xx - T / 2, yy - T / 2)
    img[(d.astype(int) % 3) == 0, :3] = rgb(inner) * 0.8
    img[d > T / 2 - 1.5, :3] = rgb(outer)
    return img


def leaves(base, name, holes=0.22):
    img = tile(base, 26, name)
    r = rng(name + "holes")
    img[r.random((T, T)) < holes, 3] = 0
    blotch(img, rgb(base) * 0.75, 5, 1, name)
    return img


def ore(colour, name, base="stone"):
    img = draw(base)
    return blotch(img, colour, 5, 1, name)


def plate(base, name, rivet="#ffffff"):
    img = tile(base, 8, name)
    img[0, :, :3] = img[-1, :, :3] = img[:, 0, :3] = img[:, -1, :3] = rgb(base) * 0.6
    img[1, 1:-1, :3] = rgb(base) * 1.2
    for x, y in ((2, 2), (13, 2), (2, 13), (13, 13)):
        img[y, x, :3] = rgb(rivet)
    return np.clip(img, 0, 255)


def blank(alpha=0):
    img = np.zeros((T, T, 4), np.float32)
    img[..., 3] = alpha
    return img


def put(img, pts, colour, alpha=255):
    c = rgb(colour) if isinstance(colour, str) else np.array(colour, np.float32)
    for x, y in pts:
        if 0 <= x < T and 0 <= y < T:
            img[y, x, :3] = c
            img[y, x, 3] = alpha
    return img


def line(x0, y0, x1, y1):
    n = max(abs(x1 - x0), abs(y1 - y0)) + 1
    return [(round(x0 + (x1 - x0) * k / max(1, n - 1)), round(y0 + (y1 - y0) * k / max(1, n - 1))) for k in range(n)]


def rect(x0, y0, x1, y1):
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def disc(cx, cy, r):
    return [(x, y) for x in range(T) for y in range(T) if (x - cx) ** 2 + (y - cy) ** 2 <= r * r]


WOOL = {"white": "#e8e8e4", "red": "#c43a34", "orange": "#e3852b", "yellow": "#e8cf3c", "green": "#4f9a3a",
        "blue": "#3b5fc4", "purple": "#8a45b8", "black": "#26262c"}
MATERIAL = {"wood": ("#a87c4a", "#6e4f2c"), "stone": ("#8d8d8d", "#5a5a5a"), "copper": ("#d88a52", "#8a4f28"),
            "iron": ("#d9d6cf", "#8f8b82"), "crystal": ("#5fe3f0", "#2a8fa8")}


def tool_icon(kind, material):
    hi, lo = MATERIAL[material]
    img = blank()
    put(img, line(3, 13, 10, 6), "#7a5530")  # (the handle, a stick from bottom left)
    put(img, line(4, 13, 11, 6), "#5c3e22")
    if kind == "pick":
        put(img, line(5, 3, 13, 11), hi)
        put(img, line(6, 3, 13, 10), hi)
        put(img, line(5, 4, 12, 11), lo)
    elif kind == "axe":
        put(img, rect(9, 3, 12, 7), hi)
        put(img, line(9, 8, 12, 8), lo)
        put(img, rect(12, 4, 13, 7), lo)
    elif kind == "shovel":
        put(img, rect(10, 2, 13, 5), hi)
        put(img, [(11, 6), (12, 6)], lo)
    elif kind == "sword":
        img = blank()
        put(img, line(4, 11, 13, 2), hi)
        put(img, line(5, 11, 13, 3), lo)
        put(img, line(2, 10, 6, 14), "#4a3a2a")
        put(img, line(2, 13, 4, 11), "#7a5530")
    elif kind == "hoe":
        put(img, rect(9, 3, 13, 4), hi)
        put(img, [(9, 5), (9, 6)], lo)
    return img


ARMOUR_COLOURS = dict(MATERIAL, cloth=("#c8b48e", "#86724e"))


def armour_shape(part):
    """The pixels of an armour piece's icon: its body, and the edge drawn darker."""
    if part == "helmet":
        body = rect(3, 4, 12, 7) + rect(3, 8, 5, 11) + rect(10, 8, 12, 11)
        edge = line(3, 11, 5, 11) + line(10, 11, 12, 11) + line(12, 4, 12, 11)
    elif part == "chest":
        body = rect(2, 3, 6, 6) + rect(9, 3, 13, 6) + rect(4, 6, 11, 13) + rect(6, 4, 9, 6)
        body = [q for q in body if q not in ((7, 3), (8, 3), (7, 4), (8, 4))]
        edge = line(4, 13, 11, 13) + line(11, 6, 11, 13) + line(2, 6, 3, 6) + line(12, 6, 13, 6)
    elif part == "legs":
        body = rect(3, 3, 12, 5) + rect(3, 6, 6, 13) + rect(9, 6, 12, 13)
        edge = line(3, 13, 6, 13) + line(9, 13, 12, 13) + line(12, 3, 12, 13)
    else:
        body = rect(3, 6, 6, 12) + rect(2, 11, 6, 13) + rect(9, 6, 12, 12) + rect(9, 11, 13, 13)
        edge = line(2, 13, 6, 13) + line(9, 13, 13, 13) + line(6, 6, 6, 13) + line(12, 6, 12, 10)
    return body, edge


def armour_icon(part, material):
    hi, lo = ARMOUR_COLOURS[material]
    body, edge = armour_shape(part)
    img = put(blank(), body, hi)
    put(img, edge, lo)
    if material == "cloth":  # (stitches)
        put(img, [q for q in body if (q[0] + q[1]) % 5 == 0], lo)
    else:  # (a shine)
        put(img, [q for q in body if q[0] == min(x for x, _ in body) + 1 and q[1] % 3 == 0], "#ffffff")
    return img


def slot_icon(part):
    """An empty armour slot's faint picture of what goes in it."""
    body, _ = armour_shape(part)
    return put(blank(), body, "#8a90a0", 70)


def draw(name):
    """The tile called name, as an H x W x 4 float array (0..255)."""
    if name.startswith("wool_"):
        img = tile(WOOL[name[5:]], 12, name)
        r = rng(name + "fibre")
        for _ in range(26):
            x, y = r.integers(0, T, 2)
            img[y, x:x + 2, :3] *= 0.88
        return img
    if name.startswith("crack_") and name[6:].isdigit():
        k = int(name[6:])
        img = blank()
        r = rng("crack")
        pts = []
        for _ in range(3 + k * 2):
            x, y = r.integers(2, T - 2, 2)
            dx, dy = r.integers(-3, 4, 2)
            pts += line(x, y, x + dx, y + dy)
        return put(img, pts[: 6 + k * 9], "#101010", 200)
    if name.startswith("wheat_") and name[6:].isdigit():
        k = int(name[6:])
        img = blank()
        colour = "#5aa83a" if k < 5 else "#b5a83a" if k < 7 else "#d8b84a"
        h = 3 + k
        for x in (3, 6, 9, 12):
            put(img, line(x, 15, x + (1 if x % 2 else 0), 15 - h), colour)
            if k >= 5:
                put(img, [(x, 15 - h), (x + 1, 16 - h), (x - 1, 16 - h)], "#e8c860")
        return img
    for kind in B.TOOL_KINDS:
        for mat in MATERIAL:
            if name == f"{mat}_{kind}":
                return tool_icon(kind, mat)
    for part, _ in B.ARMOUR_PARTS:
        for mat in ARMOUR_COLOURS:
            if name == f"{mat}_{part}":
                return armour_icon(part, mat)
        if name == f"slot_{part}":
            return slot_icon(part)
    f = TILES.get(name)
    if f is None:
        return tile("#ff00ff", 0, name)  # (a tile with no drawing: bright pink, so it shows)
    return f(name)


def _grass_side(n):
    img = draw("soil")
    top = draw("grass_top")
    r = rng(n)
    for x in range(T):
        d = 3 + int(r.integers(0, 3))
        img[:d, x] = top[:d, x]
    return img


def _torch(n):
    img = blank()
    put(img, rect(7, 6, 8, 15), "#7a5530")
    put(img, rect(7, 3, 8, 5), "#ffd34a")
    put(img, [(7, 2), (8, 4)], "#fff3b0")
    put(img, [(6, 4), (9, 4)], "#ff8a2a")
    return img


def _glass(n):
    img = blank(30)
    img[..., :3] = rgb("#cfe8f0")
    img[0, :, 3] = img[-1, :, 3] = img[:, 0, 3] = img[:, -1, 3] = 230
    put(img, line(3, 5, 6, 2), "#ffffff", 200)
    put(img, line(9, 12, 12, 9), "#ffffff", 180)
    return img


def _window(n):
    img = _glass(n)
    put(img, rect(7, 0, 8, 15) + rect(0, 7, 15, 8), "#7a5530")
    put(img, rect(0, 0, 15, 0) + rect(0, 15, 15, 15) + rect(0, 0, 0, 15) + rect(15, 0, 15, 15), "#7a5530")
    return img


def _ladder(n):
    img = blank()
    put(img, rect(2, 0, 3, 15) + rect(12, 0, 13, 15), "#8a6238")
    for y in (2, 6, 10, 14):
        put(img, rect(2, y, 13, y), "#a87c4a")
    return img


def _door(n, high):
    img = boards("#9c7244", "#6e4f2c", n, vertical=True)
    img[:, 0, :3] = img[:, -1, :3] = rgb("#5a3e22")
    if high:
        put(img, rect(4, 3, 11, 9), "#cfe8f0", 255)
        put(img, rect(7, 3, 8, 9) + rect(4, 6, 11, 6), "#6e4f2c")
    else:
        put(img, [(12, 2), (12, 3), (13, 2)], "#d8c060")
        img[0, :, :3] = rgb("#5a3e22")
    return img


def _cross_plant(colour, extra=None):
    def f(n):
        img = blank()
        r = rng(n)
        for k in range(9):
            x = int(r.integers(1, 15))
            h = int(r.integers(5, 14))
            put(img, line(x, 15, x + int(r.integers(-2, 3)), 15 - h), colour)
        if extra:
            extra(img, r)
        return img
    return f


def _flower(petal):
    def f(n):
        img = blank()
        put(img, line(8, 15, 8, 7), "#3f8a2c")
        put(img, [(7, 11), (9, 10)], "#3f8a2c")
        put(img, disc(8, 5, 2), petal)
        put(img, [(8, 5)], "#f0e060")
        return img
    return f


def _bush(n):
    img = leaves("#3d7a2c", n, holes=0.35)
    blotch(img, "#d83a4a", 7, 0, n, alpha=255)
    return img


def _sapling(n):
    img = blank()
    put(img, line(8, 15, 8, 8), "#6e4f2c")
    put(img, disc(8, 6, 3), "#4f9a3a")
    put(img, disc(6, 8, 2) + disc(10, 8, 2), "#3f8a2c")
    return img


def _bench_top(n):
    img = boards("#b08850", "#7a5530", n)
    put(img, rect(0, 0, 15, 0) + rect(0, 15, 15, 15) + rect(0, 0, 0, 15) + rect(15, 0, 15, 15), "#5c3e22")
    put(img, line(3, 3, 12, 12), "#5a5a5a")
    put(img, rect(10, 3, 12, 5), "#8d8d8d")
    return img


def _bench_side(n):
    img = boards("#a07848", "#6e4f2c", n)
    put(img, rect(2, 4, 6, 5) + rect(4, 6, 4, 11), "#5a5a5a")  # a hammer
    put(img, line(9, 11, 13, 5), "#bcbcbc")  # a saw's blade
    put(img, rect(8, 11, 10, 12), "#6e4f2c")
    return img


def _smelter(n, lit):
    img = cells("#7a7a7a", "#4a4a4a", "rubble_s")
    put(img, rect(4, 7, 11, 12), "#181818")
    if lit:
        put(img, rect(5, 9, 10, 12), "#ff8a2a")
        put(img, rect(6, 10, 9, 12), "#ffd34a")
    put(img, rect(4, 6, 11, 6), "#3a3a3a")
    return img


def _chest(n, top):
    img = boards("#a8763c", "#6e4a22", n)
    img[0, :, :3] = img[-1, :, :3] = img[:, 0, :3] = img[:, -1, :3] = rgb("#4a3216")
    if not top:
        put(img, rect(0, 6, 15, 6), "#4a3216")
        put(img, rect(7, 5, 8, 8), "#d8c060")
    return img


def _bed_top(n):
    img = tile("#b83434", 10, n)
    put(img, rect(2, 1, 13, 5), "#ececec")
    put(img, rect(0, 7, 15, 7), "#8a2424")
    return img


def _bed_side(n):
    img = boards("#9c7244", "#6e4f2c", n)
    put(img, rect(0, 0, 15, 6), "#b83434")
    return img


def _farmland(n):
    img = tile("#5a3a20", 14, n)
    for y in (2, 6, 10, 14):
        img[y, :, :3] *= 0.7
    return img


def _cactus_side(n):
    img = tile("#3f8a2c", 12, n)
    for x in (3, 8, 12):
        img[:, x, :3] = rgb("#2c6a1e")
    r = rng(n)
    for _ in range(10):
        x, y = r.integers(0, T, 2)
        img[y, x, :3] = rgb("#e8e8b0")
    return img


def _bookshelf(n):
    img = boards("#9c7244", "#5c3e22", n)
    r = rng(n)
    for row in (1, 9):
        x = 1
        while x < 15:
            w = int(r.integers(1, 3))
            col = r.choice(["#b83434", "#3b5fc4", "#4f9a3a", "#e8cf3c", "#8a45b8"])
            put(img, rect(x, row, min(14, x + w - 1), row + 5), col)
            x += w + 1
    return img


def _magma(n):
    img = tile("#d8521c", 30, n)
    blotch(img, "#5a1e0e", 6, 2, n)
    blotch(img, "#ffd34a", 4, 0, n)
    return img


def _blast_side(n):
    img = tile("#c43a34", 10, n)
    put(img, rect(0, 6, 15, 9), "#ececec")
    put(img, rect(2, 7, 3, 8) + rect(6, 7, 7, 8) + rect(10, 7, 11, 8), "#26262c")
    return img


def _blast_top(n):
    img = tile("#c43a34", 10, n)
    put(img, disc(8, 8, 2), "#26262c")
    put(img, [(8, 5), (9, 4)], "#d8c060")
    return img


def _dock(n, top):
    """The Craft Bot's dock: Club Coders' circuit board (teal), yellow lights."""
    img = tile("#1d6f7a", 8, n)
    r = rng(n)
    for _ in range(6):
        x, y = (int(v) for v in r.integers(1, 14, 2))
        put(img, line(x, y, x + int(r.integers(-6, 7)), y), "#2fb8c4")
        put(img, line(x, y, x, y + int(r.integers(-6, 7))), "#2fb8c4")
    put(img, [(3, 3), (12, 4), (6, 12), (11, 11)], "#ffd34a")
    if top:
        put(img, rect(5, 5, 10, 10), "#0f3a40")
        put(img, rect(6, 6, 9, 9), "#ffd34a")
    return img


def _water(n):
    img = tile("#2f6fd0", 10, n, alpha=170)
    r = rng(n)
    for _ in range(5):
        x, y = r.integers(0, T - 4, 2)
        put(img, line(x, y, x + 3, y), "#7fb4f0", 190)
    return img


def _ice(n):
    img = tile("#9cc8f0", 8, n, alpha=190)
    put(img, line(2, 3, 9, 10) + line(9, 10, 14, 8), "#e8f4ff", 210)
    return img


def _face(colour, eyes, mouth=None):
    def f(n):
        img = tile(colour, 10, n)
        put(img, eyes, "#101418")
        if mouth:
            put(img, mouth, "#101418")
        return img
    return f


def _bleep_face(n):
    img = plate("#c8ccd4", n, "#7a7f88")
    put(img, rect(3, 5, 6, 8) + rect(9, 5, 12, 8), "#1d6f7a")
    put(img, rect(4, 6, 5, 7) + rect(10, 6, 11, 7), "#7ff0ff")
    put(img, rect(5, 11, 10, 11), "#3a3f48")
    return img


def _glitch(n):
    img = tile("#8a45b8", 30, n)
    r = rng(n)
    for y in range(T):
        if r.random() < 0.25:
            img[y, :, :3] = np.roll(img[y, :, :3], int(r.integers(-4, 5)), axis=0) + 40
    return img


def _glitch_face(n):
    img = _glitch(n)
    put(img, rect(3, 5, 5, 7) + rect(10, 5, 12, 7), "#f0f0ff")
    put(img, rect(4, 6, 4, 6) + rect(11, 6, 11, 6), "#ff3a6a")
    put(img, line(4, 11, 11, 12), "#200a30")
    return img


def _player_face(n):
    img = tile("#d8a880", 6, n)
    put(img, rect(0, 0, 15, 3) + rect(0, 4, 1, 6) + rect(14, 4, 15, 6), "#4a3020")
    put(img, rect(3, 7, 5, 8) + rect(10, 7, 12, 8), "#ffffff")
    put(img, rect(4, 7, 5, 8) + rect(10, 7, 11, 8), "#2a4a8a")
    put(img, rect(6, 12, 9, 12), "#9a5a4a")
    return img


def _bot_face(n):
    img = plate("#e0b030", n, "#8a6a10")
    put(img, rect(3, 5, 6, 8) + rect(9, 5, 12, 8), "#0f3a40")
    put(img, rect(4, 6, 5, 7) + rect(10, 6, 11, 7), "#7ff0ff")
    put(img, [(5, 11), (6, 12), (7, 12), (8, 12), (9, 12), (10, 11)], "#0f3a40")
    return img


def _rust_face(n):
    img = tile("#8a5a3a", 24, n)
    blotch(img, "#c46a2a", 5, 1, n)
    put(img, rect(3, 5, 6, 6) + rect(9, 5, 12, 6), "#ff6a2a")
    put(img, rect(4, 10, 11, 11), "#2a1a10")
    return img


def _icon(pts_colours):
    def f(n):
        img = blank()
        for pts, colour in pts_colours:
            put(img, pts, colour)
        return img
    return f


def _ingot(hi, lo):
    return _icon([(rect(3, 7, 12, 11), lo), (rect(4, 6, 11, 9), hi), (rect(5, 6, 9, 6), "#ffffff")])


def _bot_kit(n):
    img = blank()
    put(img, rect(3, 4, 12, 12), "#c8ccd4")
    put(img, rect(5, 6, 6, 7) + rect(9, 6, 10, 7), "#2fb8c4")
    put(img, rect(5, 10, 10, 10), "#3a3f48")
    put(img, line(8, 1, 8, 3), "#7a7f88")
    put(img, [(8, 0)], "#ffd34a")
    return img


def _bucket(full):
    def f(n):
        img = blank()
        put(img, rect(4, 6, 11, 13) + rect(3, 5, 12, 5), "#bcbcbc")
        put(img, rect(5, 12, 10, 13), "#8f8b82")
        put(img, line(3, 5, 8, 1) + line(8, 1, 12, 5), "#8f8b82")
        if full:
            put(img, rect(4, 6, 11, 7), "#2f6fd0")
        return img
    return f


TILES = {
    "grass_top": lambda n: speckle(tile("#5da83f", 22, n), "#4a8a30", 0.2, n),
    "grass_side": _grass_side,
    "soil": lambda n: speckle(tile("#86603a", 16, n), "#5e4024", 0.15, n),
    "stone": lambda n: blotch(tile("#8d8d8d", 14, n), "#7a7a7a", 6, 1, n),
    "rubble": lambda n: cells("#808080", "#4e4e4e", n),
    "mossy_rubble": lambda n: blotch(cells("#808080", "#4e4e4e", n), "#4f8a3a", 6, 1, n),
    "corestone": lambda n: speckle(tile("#3a3a3e", 24, n), "#16161a", 0.25, n),
    "sand": lambda n: speckle(tile("#e3d39a", 12, n), "#cdb878", 0.2, n),
    "grit": lambda n: speckle(tile("#8a8078", 20, n), "#5e5650", 0.3, n),
    "water": _water,
    "log_side": lambda n: bark("#7a5530", "#5a3e22", n),
    "log_top": lambda n: rings("#6a4a2a", "#b08850", n),
    "leaves": lambda n: leaves("#3f8f2c", n),
    "planks": lambda n: boards("#b08850", "#7a5530", n),
    "pine_planks": lambda n: boards("#7a5a3a", "#4e3820", n),
    "bench_top": _bench_top, "bench_side": _bench_side,
    "smelter_top": lambda n: cells("#7a7a7a", "#4a4a4a", n),
    "smelter_front": lambda n: _smelter(n, False), "smelter_lit": lambda n: _smelter(n, True),
    "chest_top": lambda n: _chest(n, True), "chest_side": lambda n: _chest(n, False),
    "glass": _glass, "window": _window,
    "brick": lambda n: bricks("#a84a3a", "#c8c0b0", n),
    "stone_bricks": lambda n: bricks("#8a8a8a", "#5a5a5a", n, h=8, w=16),
    "torch": _torch,
    "coal_ore": lambda n: ore("#1e1e22", n), "copper_ore": lambda n: ore("#d8823e", n),
    "iron_ore": lambda n: ore("#d8b894", n), "crystal_ore": lambda n: ore("#5fe3f0", n),
    "lumen": lambda n: blotch(tile("#f0e070", 30, n), "#fff8c0", 6, 1, n),
    "snow": lambda n: tile("#f2f6fa", 6, n),
    "ice": _ice,
    "cactus_side": _cactus_side, "cactus_top": lambda n: rings("#2c6a1e", "#5aa83a", n),
    "clay": lambda n: tile("#9aa4b4", 8, n),
    "sandstone_side": lambda n: bricks("#d8c48a", "#c4ae70", n, h=5, w=16),
    "sandstone_top": lambda n: tile("#dccc94", 8, n),
    "door_low": lambda n: _door(n, False), "door_high": lambda n: _door(n, True),
    "ladder": _ladder,
    "bed_top": _bed_top, "bed_side": _bed_side,
    "farmland": _farmland,
    "sapling": _sapling, "berry_bush": _bush,
    "tall_grass": _cross_plant("#5aa83a"),
    "flower_red": _flower("#d83a3a"), "flower_yellow": _flower("#f0d040"),
    "bookshelf": _bookshelf,
    "copper_block": lambda n: plate("#d88a52", n), "iron_block": lambda n: plate("#d9d6cf", n, "#8f8b82"),
    "crystal_block": lambda n: plate("#5fe3f0", n, "#e8ffff"),
    "magma": _magma,
    "blast_side": _blast_side, "blast_top": _blast_top,
    "dock_top": lambda n: _dock(n, True), "dock_side": lambda n: _dock(n, False),
    "pine_side": lambda n: bark("#5a3e26", "#3a2816", n), "pine_top": lambda n: rings("#4a3218", "#8a6a44", n),
    "pine_leaves": lambda n: leaves("#2a5e30", n, 0.15),
    "pale_side": lambda n: speckle(tile("#e0dccc", 8, n), "#3a3a36", 0.08, n),
    "pale_top": lambda n: rings("#d0ccbc", "#c8a878", n),
    "pale_leaves": lambda n: leaves("#7ab84a", n),
    # items
    "stick": _icon([(line(4, 13, 11, 3), "#7a5530"), (line(5, 13, 12, 3), "#5c3e22")]),
    "coal": _icon([(disc(8, 8, 4), "#26262c"), ([(6, 6), (9, 7)], "#4a4a52")]),
    "charcoal": _icon([(disc(8, 8, 4), "#3a2e26"), ([(6, 6), (9, 7)], "#5a4a3e")]),
    "copper_ingot": _ingot("#e8a06a", "#a8602e"), "iron_ingot": _ingot("#ececec", "#a8a49c"),
    "crystal": _icon([(disc(8, 8, 4), "#5fe3f0"), (line(6, 5, 10, 11), "#e8ffff")]),
    "wheat_item": _icon([(line(5, 14, 9, 3) + line(8, 14, 9, 3) + line(11, 14, 9, 3), "#d8b84a")]),
    "seeds": _icon([([(5, 9), (8, 7), (10, 10), (7, 11), (11, 7)], "#6a8a2a")]),
    "bread": _icon([(rect(3, 7, 12, 11), "#c4883e"), (rect(4, 6, 11, 7), "#e0a85a")]),
    "apple": _icon([(disc(8, 9, 4), "#c8342c"), (line(8, 5, 9, 3), "#5c3e22"), ([(10, 4)], "#4f9a3a")]),
    "berries": _icon([(disc(6, 9, 2) + disc(10, 9, 2) + disc(8, 6, 2), "#d83a4a")]),
    "root": _icon([(disc(8, 9, 4), "#b0884a"), ([(6, 8), (9, 10)], "#7a5a2a")]),
    "roast_root": _icon([(disc(8, 9, 4), "#c8802e"), ([(6, 8), (9, 10)], "#ffd38a")]),
    "clay_ball": _icon([(disc(8, 8, 4), "#9aa4b4")]),
    "brick_item": _icon([(rect(3, 6, 12, 10), "#a84a3a")]),
    "scrap": _icon([(disc(8, 8, 5), "#8f8b82"), (disc(8, 8, 2), "#3a3f48"), ([(8, 2), (8, 14), (2, 8), (14, 8)], "#8f8b82")]),
    "glitch_shard": _icon([(line(5, 13, 11, 3) + line(6, 13, 11, 4) + line(7, 12, 12, 4), "#a855e0")]),
    "rust": _icon([(disc(6, 8, 2) + disc(10, 10, 2) + disc(9, 5, 1), "#b85a2a")]),
    "bucket": _bucket(False), "water_bucket": _bucket(True),
    "bot_kit": _bot_kit,
    # creatures and the player
    "fluff_wool": lambda n: draw("wool_white"),
    "fluff_face": _face("#e8e8e4", rect(3, 6, 4, 7) + rect(11, 6, 12, 7), rect(7, 10, 8, 11)),
    "bleep_face": _bleep_face, "bleep_body": lambda n: plate("#c8ccd4", n, "#7a7f88"),
    "glitch_face": _glitch_face, "glitch_body": _glitch,
    "rust_face": _rust_face, "rust_body": lambda n: blotch(tile("#7a4a2e", 26, n), "#b85a2a", 6, 1, n),
    "skin": lambda n: tile("#d8a880", 6, n),
    "player_face": _player_face,
    "hair": lambda n: speckle(tile("#4a3020", 14, n), "#2e1c10", 0.2, n),
    "bot_face": _bot_face,
    "shirt": lambda n: tile("#ffffff", 8, n),
    "trousers": lambda n: tile("#3a4a7a", 8, n),
    "bot_body": lambda n: _dock(n, False),
    "particle": lambda n: tile("#ffffff", 0, n),
    "cloth_armour": lambda n: speckle(tile("#c8b48e", 10, n), "#86724e", 0.15, n),
    **{f"slot_{part}": (lambda n: slot_icon(n[5:])) for part, _ in B.ARMOUR_PARTS},
}


def tile_names():
    """Every tile the game draws, in atlas order: the blocks' faces, the items' icons, the crops, the cracks."""
    names = []

    def add(n):
        if n and n not in names:
            names.append(n)
    for b in B.BLOCKS:
        for t in (b["tiles"] or ()):
            add(t)
    for it in B.ITEMS.values():
        add(it.get("icon"))
    for k in range(8):
        add(f"wheat_{k}")
    for k in range(10):
        add(f"crack_{k}")
    for n in TILES:
        add(n)
    return names


def build_atlas():
    """The atlas (a uint8 array, 256 x 256 x 4) and where each tile is: {name: (column, row)}."""
    names = tile_names()
    if len(names) > B.ATLAS * B.ATLAS:
        raise ValueError(f"{len(names)} tiles: the atlas holds {B.ATLAS * B.ATLAS}")
    size = B.ATLAS * T
    atlas = np.zeros((size, size, 4), np.uint8)
    where = {}
    for i, name in enumerate(names):
        cx, cy = i % B.ATLAS, i // B.ATLAS
        b = next((b for b in B.BLOCKS if b.get("mod") and name in (b["tiles"] or ())), None)
        img = tile(b["colour"], 14, name) if b is not None and b.get("colour") else draw(name)
        atlas[cy * T:(cy + 1) * T, cx * T:(cx + 1) * T] = np.clip(img, 0, 255).astype(np.uint8)
        where[name] = (cx, cy)
    return atlas, where


def atlas_path():
    mods = "".join(sorted(b["key"] for b in B.BLOCKS if b.get("mod")))
    tag = ART_VERSION + ("-" + format(zlib.crc32(mods.encode()), "08x") if mods else "")
    return os.path.join(ASSETS, f"atlas_{tag}.png")


def save_png(path, img):
    from PIL import Image
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(img, "RGBA").save(path)


if __name__ == "__main__":
    atlas, where = build_atlas()
    save_png(atlas_path(), atlas)
    from PIL import Image
    Image.fromarray(atlas, "RGBA").resize((1024, 1024), Image.NEAREST).save(os.path.join(ASSETS, "atlas_big.png"))
    print(f"{len(where)} tiles: {atlas_path()}")
