"""Craft Lab's pictures, all drawn by code here (CHANGE 200, our own look since CHANGE 207): every block face, item
icon, crop stage, tool, suit piece and creature face as a 16 x 16 pixel tile, packed into one texture atlas (16 x 16
tiles). Nothing is copied from anywhere: each tile is a few lines of numpy (a base colour, a pattern, a little
noise), seeded by the tile's own name, so the atlas is the same on every computer. The atlas is made the first time
a window needs it and kept in assets/atlas_<version>.png; mods' blocks get a plain tile in their own colour.

The look is Club Coders' own, a neon-on-navy lab island: the natural blocks keep natural colours, a little cleaner
and brighter (turf in the club's lime with a faint hex pattern, stone in layers, ores as veins); the machines and
the lab's blocks are navy with cyan screens, lime and amber lights and magenta glows (the website's colours, PAL).

A tile whose frames play one after another (craft_blocks.ANIMATED: the Server Rack's LEDs) has its frames side by
side in one row of the atlas, frame k k tiles to the right of frame 0, so the shader can step through them.

    python craft_art.py            makes the atlas and a big copy to look at (assets/atlas_big.png)
"""
import math
import os
import zlib

import numpy as np

import craft_blocks as B

ART_VERSION = "3"   # (2: armour; 3: Club Coders' own look, CHANGE 207)
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
T = B.TILE

# the website's colours (ClubCodersWebsite/site/assets/style.css), and a few steps between them
PAL = {"bg": "#090c17", "bg2": "#0f1426", "navy": "#161c33", "navy2": "#232b4a", "navy3": "#343f66",
       "ink": "#f3f6ff", "ink2": "#b9c2e0", "ink3": "#7f8ab0", "cyan": "#3ee9ff", "lime": "#b6ff3b",
       "magenta": "#ff4fd8", "amber": "#ffc638", "coral": "#ff6b5b"}


def rng(name):
    return np.random.default_rng(zlib.crc32(name.encode()))


def rgb(hexcode):
    if not isinstance(hexcode, str):
        return np.array(hexcode, np.float32)
    h = PAL.get(hexcode, hexcode).lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)


def mix(a, b, t):
    return rgb(a) * (1 - t) + rgb(b) * t


def tile(base, noise=18.0, name="", alpha=255):
    """A tile of colour base with per-pixel noise (a float array H x W x 4)."""
    r = rng(name)
    img = np.zeros((T, T, 4), np.float32)
    img[..., :3] = rgb(base)
    img[..., :3] += (r.random((T, T, 1)) - 0.5) * 2 * noise
    img[..., 3] = alpha
    return img


def blank(alpha=0):
    img = np.zeros((T, T, 4), np.float32)
    img[..., 3] = alpha
    return img


def put(img, pts, colour, alpha=255):
    c = rgb(colour)
    for x, y in pts:
        if 0 <= x < T and 0 <= y < T:
            img[y, x, :3] = c
            img[y, x, 3] = alpha
    return img


def wrap(img, pts, colour, alpha=255):
    """put, wrapping round the tile's edges (a pattern that joins up with the next block's)."""
    return put(img, [(x % T, y % T) for x, y in pts], colour, alpha)


def line(x0, y0, x1, y1):
    n = max(abs(x1 - x0), abs(y1 - y0)) + 1
    return [(round(x0 + (x1 - x0) * k / max(1, n - 1)), round(y0 + (y1 - y0) * k / max(1, n - 1))) for k in range(n)]


def rect(x0, y0, x1, y1):
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def disc(cx, cy, r):
    return [(x, y) for x in range(T) for y in range(T) if (x - cx) ** 2 + (y - cy) ** 2 <= r * r]


def border(x0=0, y0=0, x1=T - 1, y1=T - 1):
    return line(x0, y0, x1, y0) + line(x0, y1, x1, y1) + line(x0, y0, x0, y1) + line(x1, y0, x1, y1)


def clip(img):
    return np.clip(img, 0, 255)


GRID = np.mgrid[0:T, 0:T]   # (y, x)


# ---------- patterns ----------
def hex_edges():
    """The faint hex pattern on turf: a honeycomb that repeats every 16 pixels (joins up block to block)."""
    yy, xx = GRID + 0.5
    centres = [(i * 8 + (j % 2) * 4, j * 8) for i in range(-1, 4) for j in range(-1, 4)]
    d = np.stack([np.hypot(xx - cx, yy - cy) for cx, cy in centres], -1)
    s = np.sort(d, -1)
    return (s[..., 1] - s[..., 0]) < 0.9


def strata(base, name, noise=2.0, step=12.0):
    """Rock in layers: gently waving bands of a cool grey, each its own tone, a fine dark line on top of each, a
    lighter one under it, and a few glints of crystal."""
    r = rng(name + "strata")
    yy, xx = GRID
    a, b = r.random(2) * 2 * math.pi
    y2 = (yy + 1.3 * np.sin(xx * 2 * math.pi / T + a) + 0.6 * np.sin(xx * 4 * math.pi / T + b)) % T
    cuts = np.array([0, 3, 6, 10, 13, 16])
    band = np.searchsorted(cuts, y2, side="right") - 1
    band[band == len(cuts) - 1] = 0
    tones = np.array([0.0, 1.0, -0.6, 0.5, -1.0, 0.0]) * step
    img = tile(base, noise, name)
    img[..., :3] += tones[band][..., None]
    above = np.roll(band, 1, axis=0)
    seam = above != band
    img[seam, :3] = rgb(base) * 0.74
    under = np.roll(seam, 1, axis=0)
    img[under & ~seam, :3] *= 1.08
    glint = r.random((T, T)) < 0.025
    img[glint, :3] = rgb(base) * 1.22
    return clip(img)


def cells(base, edge, name, n=7, bevel=True):
    """Broken chunks: angular cells of base (square distance, so their sides are straight), each its own tone, lit
    on the top left and shaded on the bottom right."""
    r = rng(name + "cells")
    pts = r.random((n, 2)) * T
    stretch = 0.6 + r.random((n, 2)) * 0.8
    yy, xx = GRID + 0.5
    d = np.full((T, T, n), 1e9)
    for i, (px, py) in enumerate(pts):
        for ox in (-T, 0, T):
            for oy in (-T, 0, T):
                dd = np.maximum(np.abs(xx - px - ox) * stretch[i, 0], np.abs(yy - py - oy) * stretch[i, 1])
                dd = dd + 0.35 * np.abs((xx - px - ox) + (yy - py - oy)) * 0.3
                d[..., i] = np.minimum(d[..., i], dd)
    s = np.sort(d, axis=2)
    img = tile(base, 4, name)
    shade = (r.random(n) - 0.5) * 34
    img[..., :3] += shade[np.argmin(d, axis=2)][..., None]
    e = (s[..., 1] - s[..., 0]) < 0.7
    if bevel:
        lit = ~e & (np.roll(e, 1, 0) | np.roll(e, 1, 1))
        dark = ~e & (np.roll(e, -1, 0) | np.roll(e, -1, 1))
        img[lit, :3] *= 1.16
        img[dark, :3] *= 0.84
    img[e, :3] = rgb(edge)
    return clip(img)


def vein(img, name, hi, lo, n=2, steps=16, width=1):
    """An ore's veins: lines that wander across the rock, bright on top, a shadow under (they catch the light)."""
    r = rng(name + "vein")
    for _ in range(n):
        x, y = r.random() * T, r.random() * T
        ang = r.random() * math.pi * 2
        for _ in range(steps):
            ang += (r.random() - 0.5) * 0.7
            x += math.cos(ang)
            y += math.sin(ang) * 0.8
            xi, yi = int(x) % T, int(y) % T
            wrap(img, [(xi, yi + 1)] + ([(xi + 1, yi + 1)] if width > 1 else []), lo)
            wrap(img, [(xi, yi)] + ([(xi + 1, yi)] if width > 1 else []), hi)
    return img


def fluffy(colour, name):
    """Soft fluff: round puffs on top of each other, each lit on its top left and edged where it overlaps the one
    under it (cotton, not knitting)."""
    img = tile(colour, 2, name)
    r = rng(name + "puffs")
    base = rgb(colour)
    yy, xx = GRID + 0.5
    top = np.full((T, T), -1)
    for i in range(24):
        cx, cy = r.random(2) * T
        rad = 1.8 + r.random() * 1.6
        for ox in (-T, 0, T):
            for oy in (-T, 0, T):
                dx, dy = xx - cx - ox, yy - cy - oy
                d = np.hypot(dx, dy)
                inside = d < rad
                if not inside.any():
                    continue
                k = 1.12 - 0.12 * (dx + dy)[inside] / rad - 0.08 * (d[inside] / rad) ** 2
                img[inside, :3] = base * k[:, None]
                top[inside] = i
    edge = (top != np.roll(top, -1, 0)) | (top != np.roll(top, -1, 1))
    edge &= r.random((T, T)) < 0.7   # (soft: the edges come and go)
    dark = 0.9 if base.mean() > 80 else 1.4
    img[edge, :3] = img[edge, :3] * dark + (0 if base.mean() > 80 else 10)
    return clip(img)


def vboards(base, seam, name, w=4, nails=True):
    """Boards standing up (vertical), each its own tone, with grain and two nail dots."""
    img = tile(base, 4, name)
    r = rng(name + "boards")
    for b in range(T // w):
        x0 = b * w
        img[:, x0:x0 + w, :3] += (r.random() - 0.5) * 22
        for _ in range(2):  # (the grain: a faint streak down the board)
            gx = x0 + int(r.integers(0, w - 1))
            gy = int(r.integers(0, T))
            n = int(r.integers(4, 9))
            for k in range(n):
                img[(gy + k) % T, gx, :3] *= 0.93
        img[:, x0 + w - 1, :3] = rgb(seam)
        img[:, x0, :3] *= 1.08
        if nails:
            for ny in (2, 13):
                img[ny, x0 + 1, :3] = rgb(seam) * 0.7
    return clip(img)


def bark(base, dark, name):
    img = tile(base, 6, name)
    r = rng(name + "bark")
    for x in range(T):
        if r.random() < 0.4:
            y0 = int(r.integers(0, T))
            n = int(r.integers(6, T + 1))
            for k in range(n):
                img[(y0 + k) % T, x, :3] = rgb(dark) + (r.random() - 0.5) * 10
    return img


def rings(outer, inner, name):
    img = tile(inner, 5, name)
    yy, xx = GRID + 0.5
    d = np.hypot(xx - T / 2, yy - T / 2)
    img[(d.astype(int) % 3) == 0, :3] = rgb(inner) * 0.82
    img[d < 1.6, :3] = rgb(inner) * 0.7
    img[d > T / 2 - 1.2, :3] = rgb(outer)
    img[(xx < 1) | (xx > T - 1) | (yy < 1) | (yy > T - 1), :3] = rgb(outer)
    return img


def round_leaves(base, name, holes=0.2):
    """Leaves of the round trees: clumps of round leaves, each lit on its top, the gaps between the clumps open to
    see through (more gaps for a bigger holes)."""
    img = tile(base, 4, name)
    img[..., 3] = 0
    r = rng(name + "leaf")
    yy, xx = GRID + 0.5
    n = int(32 - holes * 40)
    for _ in range(n):
        cx, cy = r.random(2) * T
        rad = 2.0 + r.random() * 1.4
        tone = 0.88 + r.random() * 0.24
        for ox in (-T, 0, T):
            for oy in (-T, 0, T):
                dx, dy = xx - cx - ox, yy - cy - oy
                d = np.hypot(dx, dy)
                inside = d < rad
                k = tone - 0.14 * dy[inside] / rad
                img[inside, :3] = rgb(base) * k[:, None]
                img[inside, 3] = 255
                rim = inside & (d > rad - 0.8) & (dy > 0)
                img[rim, :3] = rgb(base) * 0.7
    return clip(img)


def needles(base, name, holes=0.14):
    img = tile(base, 6, name)
    r = rng(name + "needles")
    for _ in range(26):
        x, y = (int(v) for v in r.integers(0, T, 2))
        d = 1 if r.random() < 0.5 else -1
        wrap(img, [(x, y), (x + d, y + 1), (x + 2 * d, y + 2)], rgb(base) * (1.2 if r.random() < 0.5 else 0.75))
    img[r.random((T, T)) < holes, 3] = 0
    return clip(img)


def plate(base, name, rivet="ink", inset=True):
    """A metal block: a panel with a bevelled edge, an inset middle and four rivets."""
    img = tile(base, 4, name)
    c = rgb(base)
    for p in border():
        img[p[1], p[0], :3] = c * 0.62
    img[1, 1:-1, :3] = img[1:-1, 1, :3] = c * 1.2
    img[-2, 1:-1, :3] = img[1:-1, -2, :3] = c * 0.8
    if inset:
        put(img, border(4, 4, 11, 11), c * 0.82)
        put(img, line(5, 5, 10, 5) + line(5, 5, 5, 10), c * 1.1)
    for x, y in ((2, 2), (13, 2), (2, 13), (13, 13)):
        img[y, x, :3] = rgb(rivet)
    return clip(img)


def panel(base="navy", edge="navy3", name="panel", noise=3):
    """A lab machine's casing: navy, a lighter edge on top and left, darker on the bottom and right."""
    img = tile(base, noise, name)
    put(img, line(0, 0, 15, 0) + line(0, 0, 0, 15), mix(edge, "ink3", 0.25))
    put(img, line(0, 15, 15, 15) + line(15, 0, 15, 15), mix(base, "bg", 0.6))
    put(img, line(1, 1, 14, 1) + line(1, 1, 1, 14), edge)
    return img


# ---------- the ground and the rock ----------
def _turf_top(n):
    img = tile("#94d93a", 6, n)
    r = rng(n)
    img[hex_edges(), :3] = rgb("#7fc22e")
    glint = r.random((T, T)) < 0.06
    img[glint, :3] = rgb("lime")
    return clip(img)


def _turf_side(n):
    img = draw("soil")
    top = draw("turf_top")
    img[:3] = top[:3]
    img[2, :, :3] = rgb("#7fc22e")
    img[3, :, :3] = rgb("#5e4128")  # (a clean edge under the band)
    return img


def _soil(n):
    img = tile("#94673f", 7, n)
    r = rng(n)
    for _ in range(7):  # (a few pebbles)
        x, y = (int(v) for v in r.integers(0, T, 2))
        wrap(img, [(x, y), (x + 1, y)], "#6e4a2c")
        wrap(img, [(x, y - 1)], "#b08458")
    return img


def _lab_floor(n):
    img = tile("navy", 2, n)
    put(img, line(0, 0, 15, 0) + line(0, 0, 0, 15), mix("cyan", "navy", 0.45))
    put(img, rect(7, 7, 8, 8), mix("cyan", "navy", 0.3))
    put(img, line(4, 8, 6, 8) + line(9, 8, 11, 8) + line(8, 4, 8, 6) + line(8, 9, 8, 11), mix("cyan", "navy", 0.75))
    return img


def _sand(n):
    img = tile("#ecd9a0", 5, n)
    r = rng(n)
    yy, xx = GRID
    ripple = ((yy + np.round(1.2 * np.sin(xx * 2 * math.pi / T + r.random() * 6))) % 5) == 0
    img[ripple, :3] *= 0.93
    img[r.random((T, T)) < 0.08, :3] = rgb("#d8c080")
    return clip(img)


def _grit(n):
    img = tile("#8f8a86", 6, n)
    r = rng(n)
    for _ in range(22):
        x, y = (int(v) for v in r.integers(0, T, 2))
        c = r.choice(["#6f6a68", "#a8a29c", "#7d8494", "#9a8c7c"])
        wrap(img, [(x, y), (x + 1, y), (x, y + 1)][:int(r.integers(1, 4))], c)
    return img


def _water(n):
    img = tile("#2a86e8", 4, n, alpha=170)
    yy, xx = GRID
    wave = ((yy * 2 + np.round(1.5 * np.sin(xx * 2 * math.pi / T * 2))) % 8) == 0
    img[wave, :3] = rgb("#7cc8ff")
    img[wave, 3] = 190
    return img


def _ice(n):
    img = tile("#a8dcff", 4, n, alpha=190)
    put(img, line(2, 3, 9, 10) + line(9, 10, 14, 8) + line(9, 10, 8, 15), "#eef8ff", 220)
    put(img, line(3, 12, 6, 14), "#eef8ff", 200)
    return img


def _snow(n):
    img = tile("ink", 3, n)
    r = rng(n)
    img[r.random((T, T)) < 0.08, :3] = rgb("#dbe4f7")
    return img


def _clay(n):
    img = tile("#a3adc2", 3, n)
    for y in (4, 9, 13):
        img[y, :, :3] *= 0.94
    return img


def _sandstone_side(n):
    img = tile("#e0cc8e", 4, n)
    put(img, rect(0, 0, 15, 2), "#d4bc7a")
    for y, c in ((3, "#c6ad6a"), (8, "#cdb574"), (12, "#c6ad6a")):
        put(img, line(0, y, 15, y), c)
    return img


def _sandstone_top(n):
    img = tile("#e4d296", 3, n)
    put(img, border(), "#cdb574")
    put(img, border(3, 3, 12, 12), "#d8c486")
    return img


def _magma(n):
    img = tile("#3a1424", 6, n)
    r = rng(n)
    for _ in range(4):  # (glowing cracks across the crust)
        x, y = r.random() * T, r.random() * T
        ang = r.random() * 6.3
        for _ in range(14):
            ang += (r.random() - 0.5) * 1.2
            x, y = x + math.cos(ang), y + math.sin(ang)
            wrap(img, [(int(x), int(y) + 1)], "coral")
            wrap(img, [(int(x), int(y))], "amber")
    return img


# ---------- trees and plants ----------
def _cactus_side(n):
    img = tile("#4ea84a", 5, n)
    for x in (3, 8, 12):
        img[:, x, :3] = rgb("#36803a")
        img[:, x - 1, :3] = rgb("#62c25a")
    r = rng(n)
    for _ in range(9):
        x, y = (int(v) for v in r.integers(0, T, 2))
        img[y, x, :3] = rgb("#f0f0c8")
    return img


def _cross_plant(colour, extra=None):
    def f(n):
        img = blank()
        r = rng(n)
        for k in range(9):
            x = int(r.integers(1, 15))
            h = int(r.integers(5, 14))
            tip = x + int(r.integers(-2, 3))
            put(img, line(x, 15, tip, 15 - h), colour)
            put(img, [(tip, 15 - h)], mix(colour, "lime", 0.5))
        if extra:
            extra(img, r)
        return img
    return f


def _flower(petal, middle):
    def f(n):
        img = blank()
        put(img, line(8, 15, 8, 8), "#3f9a3c")
        put(img, [(7, 12), (6, 11), (9, 11), (10, 10)], "#55b84a")
        put(img, disc(8, 3, 1.5) + disc(5, 5.5, 1.5) + disc(11, 5.5, 1.5) + disc(6, 8, 1.2) + disc(10, 8, 1.2), petal)
        put(img, disc(8, 6, 1.1), middle)
        return img
    return f


def _bush(n):
    img = round_leaves("#3d8f3a", n, holes=0.3)
    r = rng(n + "berries")
    for _ in range(6):
        x, y = (int(v) for v in r.integers(1, 14, 2))
        put(img, rect(x, y, x + 1, y + 1), "#e83a7a")
        put(img, [(x, y)], "#ff9ac0")
    return img


def _sapling(n):
    img = blank()
    put(img, line(8, 15, 8, 8), "#7a5534")
    put(img, disc(8, 6, 3), "#5cbf48")
    put(img, disc(5.5, 9, 1.8) + disc(10.5, 9, 1.8), "#479c3a")
    put(img, [(7, 4), (8, 4)], "#a6ee6a")
    return img


def _grain(k):
    """The Grain crop's four stages: shoots, leaves, green ears, ripe golden ears."""
    def f(n):
        img = blank()
        h = (3, 6, 10, 12)[k]
        green = "#59b84a" if k < 3 else "#c8a648"
        for x in (2, 5, 8, 11, 14):
            lean = (1 if x % 2 else -1) if k else 0
            put(img, line(x, 15, x + lean, 15 - h), green)
            if k >= 1:
                put(img, [(x - 1, 15 - h // 2), (x + 1, 14 - h // 2)], mix(green, "lime", 0.3))
            if k >= 2:
                ear = "#9fd85a" if k == 2 else "#ffd25a"
                put(img, rect(x + lean, 14 - h - 2, x + lean, 15 - h) + [(x + lean - 1, 14 - h), (x + lean + 1, 13 - h)],
                    ear)
        return img
    return f


# ---------- machines and lab blocks ----------
def _fabricator_side(n):
    img = panel("navy", "navy3", n)
    put(img, rect(2, 2, 13, 10), "#0b2f3c")                    # the screen
    for x in range(3, 13, 2):
        put(img, line(x, 3, x, 9), "#145566")                    # its blueprint grid
    for y in range(4, 10, 2):
        put(img, line(3, y, 12, y), "#145566")
    put(img, border(2, 2, 13, 10), "cyan")
    put(img, line(5, 8, 5, 5) + line(5, 5, 8, 5) + line(8, 5, 8, 7) + line(8, 7, 10, 7), "#b8f8ff")  # a part's plan
    put(img, rect(3, 12, 4, 13), "lime")
    put(img, rect(6, 12, 7, 13), "amber")
    put(img, rect(10, 12, 13, 13), "navy3")
    return img


def _fabricator_top(n):
    img = panel("navy", "navy3", n)
    put(img, rect(3, 3, 5, 5), "navy3")                          # the clamp arm's base
    put(img, line(4, 4, 10, 4) + line(4, 5, 10, 5), "ink3")      # the arm
    put(img, line(10, 4, 10, 10) + line(11, 4, 11, 10), "ink3")
    put(img, line(8, 11, 13, 11), "ink2")                         # the clamp's jaws
    put(img, [(8, 12), (13, 12)], "ink2")
    put(img, [(4, 4), (10, 4)], "cyan")                           # its joints
    put(img, rect(5, 9, 6, 10), "lime")
    return img


def _fabricator_bottom(n):
    img = panel("bg2", "navy2", n)
    put(img, border(3, 3, 12, 12), "navy2")
    return img


def _refinery(n, on):
    img = cells("#8a909e", "#4e5463", "refinery_base", n=6)
    put(img, disc(7.5, 7.5, 5.2), "#5c6274")       # the window's rim
    put(img, disc(7.5, 7.5, 4.3), "#c8cfdc")
    put(img, disc(7.5, 7.5, 3.4), "#141826")
    if on:
        yy, xx = GRID + 0.5
        d = np.hypot(xx - 8, yy - 8)
        glow = d <= 3.4
        k = np.clip(1 - d / 3.6, 0, 1)
        img[glow, :3] = (rgb("magenta") * (0.6 + 0.4 * k[glow, None]) + rgb("#ffe0f8") * (k[glow, None] ** 2) * 0.8)
        put(img, [(6, 6)], "#ffffff")
    else:
        put(img, [(6, 6), (5, 7)], "#3a4058")
    put(img, line(2, 14, 13, 14), "#3a4058")
    return clip(img)


def _refinery_top(n):
    img = cells("#8a909e", "#4e5463", "refinery_base", n=6)
    put(img, rect(4, 4, 11, 11), "#2a2f40")
    for y in (5, 7, 9):
        put(img, line(5, y, 10, y), "#141826")
    return img


def _locker_side(n):
    img = vboards("#c98d52", "#8a5a30", n, nails=False)
    for y0 in (2, 11):
        put(img, rect(0, y0, 15, y0 + 1), "#9aa3b5")
        put(img, line(0, y0, 15, y0), "#cfd5e0")
        put(img, [(2, y0 + 1), (13, y0 + 1)], "#5c6274")
    put(img, rect(9, 5, 13, 9), "navy")                        # the keypad
    for x in (10, 12):
        for y in (6, 8):
            put(img, [(x, y)], "amber")
    put(img, [(11, 7)], "lime")
    return img


def _locker_top(n):
    img = vboards("#c98d52", "#8a5a30", n, nails=False)
    put(img, border(), "#9aa3b5")
    put(img, rect(2, 7, 13, 8), "#9aa3b5")
    return img


def _glass(n):
    img = blank(34)
    img[..., :3] = rgb("#d8f4ff")
    for x, y in border():
        img[y, x, :3] = rgb("#b9e6f5")
        img[y, x, 3] = 220
    put(img, line(3, 5, 6, 2), "#ffffff", 210)
    put(img, line(3, 7, 8, 2), "#ffffff", 120)
    put(img, line(10, 13, 13, 10), "#ffffff", 170)
    return img


def _window(n):
    img = _glass(n)
    put(img, border() + border(1, 1, 14, 14), "navy3")
    put(img, line(0, 0, 15, 0), "ink3")
    put(img, rect(7, 1, 8, 14), "navy2")
    put(img, [(1, 1), (14, 1)], "cyan")
    return img


def _brick(n):
    img = tile("#c0583e", 5, n)
    mortar = rgb("#e6dccc")
    for y in range(T):
        row = y // 4
        if y % 4 == 3:
            img[y, :, :3] = mortar
            continue
        off = 4 * (row % 2)
        for x in range(T):
            if (x + off) % 8 == 7:
                img[y, x, :3] = mortar
            elif y % 4 == 0:
                img[y, x, :3] *= 1.12
    r = rng(n)
    for row in range(4):
        for b in range(2):
            img[row * 4:row * 4 + 3, b * 8:(b + 1) * 8, :3] += (r.random() - 0.5) * 16
    return clip(img)


def _stone_tiles(n):
    """Big square tiles (four to a block) with thin dark grout, each a little different, lit on its top left."""
    img = strata("#9ca2b0", n, noise=3, step=4)
    r = rng(n + "tiles")
    for ty in range(2):
        for tx in range(2):
            x0, y0 = tx * 8, ty * 8
            img[y0:y0 + 8, x0:x0 + 8, :3] += (r.random() - 0.5) * 14
            put(img, line(x0 + 1, y0 + 1, x0 + 6, y0 + 1) + line(x0 + 1, y0 + 1, x0 + 1, y0 + 6), "#b8bdc9")
            put(img, line(x0 + 1, y0 + 6, x0 + 6, y0 + 6) + line(x0 + 6, y0 + 1, x0 + 6, y0 + 6), "#868c9a")
    for v in (0, 7, 8, 15):
        img[v, :, :3] = img[:, v, :3] = rgb("#4a5060") if v in (7, 8) else rgb("#5c6272")
    return clip(img)


def _glowstick(n):
    """A thin rod (columns 7 and 8: craft_mesh draws them) with a glowing cyan-white tip."""
    img = blank()
    put(img, rect(7, 5, 8, 15), "#7f8ab0")
    put(img, rect(8, 5, 8, 15), "#5a6488")
    put(img, rect(7, 14, 8, 15), "navy3")
    put(img, rect(7, 1, 8, 4), "cyan")
    put(img, rect(7, 2, 8, 3), "#e8fdff")
    put(img, [(6, 2), (9, 2), (6, 3), (9, 3), (7, 0), (8, 0)], "cyan", 140)
    return img


def _lumen(n):
    img = tile("#e6fbff", 4, n)
    yy, xx = GRID
    rhombus = ((np.abs(xx - 7.5) + np.abs(yy - 7.5)) % 8) < 1.0
    img[rhombus, :3] = rgb("#9ff4ff")
    put(img, border(), "#7fe8f8")
    put(img, rect(7, 7, 8, 8), "#ffffff")
    return img


def _door(n, high):
    """A lab door: a navy panel in a lighter frame; the top half has a cyan window strip, the bottom a handle and a
    kick plate."""
    img = panel("navy2", "navy3", n)
    put(img, line(0, 0, 0, 15) + line(15, 0, 15, 15), "ink3")
    if high:
        put(img, rect(0, 0, 15, 0), "ink3")
        put(img, rect(6, 2, 9, 14), "#0b2f3c")
        put(img, rect(7, 3, 8, 13), "cyan")
        put(img, line(7, 3, 7, 6), "#e8fdff")
        put(img, [(12, 3)], "lime")
    else:
        put(img, rect(12, 1, 12, 5), "amber")
        put(img, rect(11, 1, 11, 1) + rect(11, 5, 11, 5), "#b08a20")
        put(img, rect(2, 11, 13, 14), "navy3")
        for x in range(2, 14, 3):
            put(img, [(x, 12), (x + 1, 13)], "amber")
        put(img, line(0, 15, 15, 15), "ink3")
    return img


def _ladder(n):
    img = blank()
    put(img, rect(2, 0, 3, 15) + rect(12, 0, 13, 15), "ink3")
    put(img, rect(2, 0, 2, 15) + rect(12, 0, 12, 15), "ink2")
    for y in (2, 6, 10, 14):
        put(img, rect(4, y, 11, y), "ink2")
        put(img, [(3, y), (12, y)], "cyan")
    return img


def _pod_top(n):
    """The Recharge Pod from above: a navy shell round a cyan cushion, a pillow at one end."""
    img = tile("#5cd8f0", 4, n)
    for y in range(3, 13, 3):
        put(img, [(4, y), (8, y), (12, y)], "#3ab8d8")
    put(img, rect(2, 2, 13, 4), "#b8f4ff")
    put(img, border() + border(1, 1, 14, 14), "navy2")
    put(img, line(0, 0, 15, 0), "navy3")
    return img


def _pod_side(n):
    """Its side (rows 6 to 15 show: the pod is 0.6 high): the cushion's edge, a glowing strip, the navy shell."""
    img = panel("navy2", "navy3", n)
    put(img, rect(0, 6, 15, 7), "#5cd8f0")
    put(img, rect(0, 10, 15, 10), "cyan")
    put(img, rect(2, 10, 3, 10) + rect(12, 10, 13, 10), "#e8fdff")
    put(img, rect(0, 14, 15, 15), "bg2")
    put(img, [(7, 12), (8, 12)], "lime")
    return img


def _grow_bed_top(n):
    img = tile("#3a2a1e", 6, n)
    for y in (3, 7, 11):
        put(img, line(2, y, 13, y), "#2a1c12")
        put(img, line(2, y + 1, 13, y + 1), "#4e3a28")
    put(img, border() + border(1, 1, 14, 14), "#c98d52")
    put(img, border(), "#8a5a30")
    return img


def _grow_bed_side(n):
    img = vboards("#c98d52", "#8a5a30", n)
    put(img, rect(0, 2, 15, 3), "#3a2a1e")
    put(img, line(0, 4, 15, 4), "#8a5a30")
    return img


def _rack(k, dead=False):
    """A Server Rack's front: four units, each with LEDs (cyan and lime) that blink; frame k of four."""
    def f(n):
        img = tile("bg2", 2, "server_rack")
        put(img, border(), "navy3")
        r = rng("rack leds")
        on = r.random((4, 4, 3)) < 0.55       # (frame, unit, led)
        on[:, :, 0] = True                     # (each unit's first LED is its power: always on)
        for u in range(4):
            y0 = 1 + u * 4
            put(img, rect(1, y0, 14, y0 + 2), "#141a30")
            put(img, line(1, y0 + 3, 14, y0 + 3), "navy2")
            put(img, line(8, y0 + 1, 13, y0 + 1), "#05070d")
            for j, x in enumerate((2, 4, 6)):
                if dead:
                    c = "#262c3e"
                elif on[k, u, j]:
                    c = "lime" if j == 0 else ("cyan" if (u + j) % 2 else "lime")
                else:
                    c = "#1e2a3a"
                put(img, [(x, y0 + 1)], c)
        if dead:
            img[..., :3] *= 0.7
            put(img, line(3, 0, 6, 5) + line(6, 5, 5, 9) + line(5, 9, 10, 15), "#05070d")
            put(img, line(4, 0, 7, 5) + line(7, 5, 6, 9) + line(6, 9, 11, 15), "#3a4058")
        put(img, line(0, 15, 15, 15) + line(0, 0, 0, 15) + line(15, 0, 15, 15), "navy3")
        return img
    return f


def _rack_top(k):
    def f(n):
        img = panel("bg2", "navy2", "rack_top")
        for y in (4, 7, 10):
            put(img, line(3, y, 12, y), "#05070d")
        put(img, [(13, 13)], "lime" if k % 2 == 0 else "#1e2a3a")
        return img
    return f


def _overload_side(n):
    """The Overload Cell: a dark navy casing, a magenta core glowing through a grille. No lettering."""
    img = panel("navy", "navy3", n)
    yy, xx = GRID + 0.5
    d = np.hypot(xx - 8, yy - 8)
    core = d < 5.0
    k = np.clip(1 - d / 5.2, 0, 1)
    img[core, :3] = rgb("magenta") * (0.55 + 0.45 * k[core, None]) + rgb("#ffd8f6") * (k[core, None] ** 3)
    for y in (4, 6, 8, 10, 12):              # the grille's bars, in front of the core
        put(img, line(3, y, 12, y), "#0f1426")
    put(img, border(2, 2, 13, 13), "navy3")
    put(img, [(2, 2), (13, 2), (2, 13), (13, 13)], "ink3")
    return clip(img)


def _overload_top(n):
    """Its top: amber hazard chevrons on navy round a small magenta vent."""
    img = panel("navy", "navy3", n)
    for x in range(2, 14):
        for y in range(2, 14):
            if int((abs(x - 7.5) + y) // 2) % 2 == 0:   # (chevrons pointing up)
                img[y, x, :3] = rgb("amber")
    put(img, rect(5, 5, 10, 10), "navy")
    put(img, rect(6, 6, 9, 9), "magenta")
    put(img, rect(7, 7, 8, 8), "#ffd8f6")
    return img


def _dock(n, top):
    """The Craft Bot's dock: Club Coders' circuit board (teal), amber lights."""
    img = tile("#1d6f7a", 6, n)
    r = rng(n)
    for _ in range(6):
        x, y = (int(v) for v in r.integers(1, 14, 2))
        put(img, line(x, y, x + int(r.integers(-6, 7)), y), "#2fc4d4")
        put(img, line(x, y, x, y + int(r.integers(-6, 7))), "#2fc4d4")
    put(img, [(3, 3), (12, 4), (6, 12), (11, 11)], "amber")
    if top:
        put(img, rect(5, 5, 10, 10), "#0f3a40")
        put(img, rect(6, 6, 9, 9), "amber")
    return img


def _rift_top(n):
    """A Glitch rift: dark scorched ground split by bright magenta cracks."""
    img = tile("#2a1f34", 6, n)
    r = rng(n)
    for _ in range(3):
        x, y = r.random() * T, r.random() * T
        ang = r.random() * 6.3
        for _ in range(16):
            ang += (r.random() - 0.5) * 1.4
            x, y = x + math.cos(ang), y + math.sin(ang)
            wrap(img, [(int(x) + 1, int(y)), (int(x), int(y) + 1)], "#8a2a7a")
            wrap(img, [(int(x), int(y))], "magenta")
    img[r.random((T, T)) < 0.05, :3] = rgb("#ffd8f6")
    return img


def _rift_side(n):
    img = draw("soil")
    img[:2] = tile("#2a1f34", 6, n)[:2]
    r = rng(n)
    for x0 in (3, 10):
        x = x0
        for y in range(0, 9):
            x += int(r.integers(-1, 2))
            put(img, [(x % T, y)], "magenta")
            put(img, [((x + 1) % T, y)], "#8a2a7a")
    return img


def _scrap_pile(n):
    img = tile("#4a5060", 6, n)
    r = rng(n)
    for _ in range(9):
        x, y = (int(v) for v in r.integers(0, T, 2))
        w, h = (int(v) for v in r.integers(2, 6, 2))
        c = rgb(r.choice(["#9098aa", "#7f8ab0", "#c8cfdc", "#343f66", "#5c6274"]))
        wrap(img, rect(x, y, x + w, y + h), c)
        wrap(img, line(x, y, x + w, y), c * 1.2)
        wrap(img, line(x, y + h, x + w, y + h), c * 0.7)
    put(img, line(2, 11, 6, 9) + line(6, 9, 9, 10), "cyan")
    for _ in range(4):
        x, y = (int(v) for v in r.integers(0, T, 2))
        put(img, [(x, y)], "#2a2f40")
    return clip(img)


def _rust_pile(n):
    img = tile("#8a4424", 8, n)
    r = rng(n)
    for _ in range(26):
        x, y = (int(v) for v in r.integers(0, T, 2))
        c = r.choice(["#c0602e", "#e07a3a", "#6a3018", "#a85428"])
        wrap(img, [(x, y), (x + 1, y)][:int(r.integers(1, 3))], c)
    for _ in range(3):
        x, y = (int(v) for v in r.integers(0, T, 2))
        wrap(img, line(x, y, x + 3, y), "#5c6274")
    return img


def _glowfruit_leaves(n):
    img = round_leaves("#3f9a3c", "leaves", holes=0.2)
    for x, y in ((4, 4), (11, 7), (5, 12)):
        put(img, disc(x, y, 2.0), "#1a8fa8")
        put(img, disc(x - 0.3, y - 0.3, 1.6), "cyan")
        put(img, [(x - 1, y - 1)], "#e8fdff")
        put(img, [(x, y - 3)], "#7a5534")
    return img


# ---------- items ----------
def _icon(pts_colours):
    def f(n):
        img = blank()
        for pts, colour in pts_colours:
            put(img, pts, colour)
        return img
    return f


def _ingot(hi, mid, lo):
    """A cast bar from the front: its top face lighter, its front, a darker foot, and a small stamped mark."""
    return _icon([(rect(3, 7, 12, 11), mid), (rect(4, 5, 11, 6), hi), (line(3, 12, 12, 12), lo),
                  (line(4, 5, 7, 5), "#ffffff"), ([(7, 9), (8, 9)], lo), (line(12, 7, 12, 11), lo)])


def _chunk(face, lit, glint):
    body = [(x, y) for y in range(3, 13) for x in range(T)
            if abs(x - 7.5) + abs(y - 8) * 0.8 < 5.2 - (0.8 if (x + y) % 7 == 0 else 0)]
    edge = [(x, y) for x, y in body if (x - 1, y) not in body or (x, y - 1) not in body]
    return _icon([(body, face), (edge, lit), ([(6, 6), (9, 8), (7, 10)], glint)])


def _neon(n):
    img = blank()
    put(img, rect(6, 3, 10, 12) + [(8, 1), (7, 2), (8, 2), (9, 2), (7, 13), (8, 13), (9, 13), (8, 14)], "cyan")
    put(img, rect(6, 3, 7, 12) + [(7, 2), (7, 13)], "#9ff6ff")
    put(img, rect(10, 3, 10, 12) + [(9, 13)], "#1a8fa8")
    put(img, [(7, 4), (7, 5), (7, 6)], "#ffffff")
    return img


def _canister(full):
    def f(n):
        img = blank()
        put(img, rect(5, 4, 10, 14), "#c8cfdc")
        put(img, rect(5, 4, 5, 14), "#eef2fa")
        put(img, rect(10, 4, 10, 14), "#8790a3")
        put(img, rect(6, 2, 9, 3), "navy3")
        put(img, rect(5, 6, 10, 6), "cyan")
        if full:
            put(img, rect(6, 8, 9, 12), "#2a86e8")
            put(img, [(6, 8), (6, 9)], "#a8dcff")
        return img
    return f


def _battery(n):
    """A Club Coders cell: navy, an amber cap band, lime charge bars, a terminal on top."""
    img = blank()
    put(img, rect(5, 3, 10, 14), "navy")
    put(img, line(5, 3, 5, 14) + line(10, 3, 10, 14) + line(5, 14, 10, 14), "navy3")
    put(img, rect(7, 1, 8, 2), "#c8cfdc")
    put(img, rect(5, 3, 10, 4), "amber")
    for y in (7, 9, 11):
        put(img, line(6, y, 9, y), "lime")
    put(img, line(6, 6, 6, 12), "#2a3352")
    return img


def _patch(n):
    """A Patch: a cyan code-patch plate, braces round a lime dot."""
    img = blank()
    put(img, rect(2, 2, 13, 13), "bg2")
    put(img, border(2, 2, 13, 13), "cyan")
    put(img, [(2, 2), (13, 2), (2, 13), (13, 13)], "#1a8fa8")
    put(img, [(6, 5), (5, 6), (5, 7), (4, 8), (5, 9), (5, 10), (6, 11)], "cyan")
    put(img, [(9, 5), (10, 6), (10, 7), (11, 8), (10, 9), (10, 10), (9, 11)], "cyan")
    put(img, rect(7, 7, 8, 9), "lime")
    return img


def _glowfruit(n):
    img = blank()
    put(img, disc(8, 9.5, 4.4), "cyan")
    put(img, disc(8, 9.5, 2.6), "#b8fbff")
    put(img, [(6, 7), (6, 8), (7, 7)], "#ffffff")
    put(img, [(8, 4), (8, 5)], "#7a5534")
    put(img, [(9, 3), (10, 3), (10, 4)], "lime")
    return img


def _bot_kit(n):
    img = blank()
    put(img, rect(2, 5, 13, 14), "#c98d52")
    put(img, border(2, 5, 13, 14), "#8a5a30")
    put(img, rect(5, 2, 10, 9), "#c8ccd4")
    put(img, rect(6, 4, 7, 5) + rect(8, 4, 9, 5), "#1d6f7a")
    put(img, [(6, 4), (8, 4)], "#7ff0ff")
    put(img, line(6, 7, 9, 7), "#3a3f48")
    put(img, rect(2, 10, 13, 10), "cyan")
    return img


ITEM_ICONS = {
    "rod": _icon([(rect(7, 2, 8, 13), "#c48a52"), (rect(7, 2, 7, 13), "#e0aa70"), ([(7, 1), (8, 1), (7, 14), (8, 14)],
                                                                                  "#8a5a30")]),
    "coal": _chunk("#1b1e27", "#3a3f52", "#5a6078"),
    "charcoal": _chunk("#2e2420", "#5a4436", "#7a604a"),
    "copper_ingot": _ingot("#ffc27a", "#e08a4a", "#9c5428"),
    "iron_ingot": _ingot("#f6f8fc", "#d6dce8", "#8790a3"),
    "neon": _neon,
    "wheat": _icon([(line(8, 14, 5, 4) + line(8, 14, 8, 3) + line(8, 14, 11, 4), "#c8a040"),
                    (rect(4, 2, 5, 4) + rect(7, 1, 8, 3) + rect(11, 2, 12, 4), "#ffd25a"), (line(6, 11, 10, 11), "lime")]),
    "seed_pack": _icon([(rect(4, 3, 11, 13), "#e6ebf5"), ([(x, 3) for x in range(4, 12, 2)], "#b9c2e0"),
                        (line(8, 10, 8, 7), "#3f9a3c"), ([(7, 7), (6, 6), (9, 6), (10, 5)], "#5cbf48"),
                        (rect(4, 11, 11, 12), "lime")]),
    "grain_bar": _icon([(rect(2, 6, 13, 10), "amber"), ([(1, 6), (1, 8), (1, 10), (14, 6), (14, 8), (14, 10)], "#ffe08a"),
                        (rect(5, 7, 10, 9), "navy"), (line(6, 8, 9, 8), "lime"), (line(2, 10, 13, 10), "#c8941c")]),
    "apple": _icon([(disc(8, 9.5, 4.5), "#e8424a"), ([(6, 7), (6, 8), (7, 7)], "#ff9a9a"),
                    (line(8, 5, 9, 3), "#7a5534"), ([(10, 3), (11, 3), (10, 4)], "lime")]),
    "berries": _icon([(disc(6, 10, 2.2) + disc(10.5, 10, 2.2) + disc(8, 6.5, 2.2), "#e83a7a"),
                      ([(5, 9), (10, 9), (7, 5)], "#ff9ac0"), ([(8, 3), (9, 3)], "#3f9a3c")]),
    "root": _icon([(disc(7, 8, 3.4) + disc(10, 10.5, 2.6), "#c9965a"), (line(11, 12, 13, 14), "#a87444"),
                   ([(6, 7), (9, 10), (8, 6)], "#8a6034"), ([(5, 4), (6, 4), (4, 3)], "#5cbf48")]),
    "baked_root": _icon([(disc(7, 8, 3.4) + disc(10, 10.5, 2.6), "#d9852e"), (line(11, 12, 13, 14), "#a85a20"),
                         (line(5, 7, 10, 9), "#ffe0a0"), ([(5, 2), (6, 1), (9, 3), (10, 2)], "#b9c2e0")]),
    "clay_ball": _icon([(disc(8, 8.5, 4.2), "#a3adc2"), ([(6, 6), (6, 7), (7, 6)], "#d0d8e8"),
                        (line(9, 12, 11, 10), "#7f8aa0")]),
    "brick_item": _icon([(rect(2, 7, 13, 11), "#c0583e"), (rect(3, 5, 14, 6), "#d87a5a"), (line(2, 11, 13, 11), "#8a3a26"),
                         (line(14, 6, 14, 10), "#8a3a26")]),
    "glitch_shard": _icon([(line(4, 13, 8, 2) + line(5, 13, 9, 2), "cyan"), (line(5, 13, 9, 2) + line(6, 13, 10, 3) +
                                                                            line(7, 12, 11, 4), "magenta"),
                           ([(8, 5), (7, 8)], "#ffffff")]),
    "rust": _icon([(disc(6, 8, 2.2) + disc(10, 10, 2.2) + disc(9.5, 5, 1.5), "#c0602e"),
                   ([(5, 7), (9, 9), (9, 4)], "#e8904a"), ([(7, 9), (11, 11)], "#6a3018")]),
    "canister": _canister(False), "water_canister": _canister(True),
    "bot_kit": _bot_kit,
    "battery": _battery,
    "patch": _patch,
    "glowfruit": _glowfruit,
}


def _scrap(n):
    """Scrap: a bent plate with two holes, a bolt and a bit of cyan wire."""
    img = blank()
    put(img, [p for p in rect(3, 4, 11, 11) if p not in ((3, 4), (3, 11), (11, 11))], "#9098aa")
    put(img, line(4, 4, 11, 4), "#c8cfdc")
    put(img, line(11, 5, 11, 10), "#5c6274")
    put(img, [(5, 6), (9, 9)], "#2a2f40")
    put(img, rect(11, 11, 13, 13), "#c8cfdc")
    put(img, [(12, 12)], "#5c6274")
    put(img, line(10, 5, 13, 6) + line(13, 6, 14, 9), "cyan")
    return img


ITEM_ICONS["scrap"] = _scrap


# ---------- tools: new shapes (no picks, no swords); the tip's colour is the tier ----------
TIER_TIP = {"mk1": ("#8e95a6", "#5c6274"), "mk2": ("#e08a4a", "#9c5428"), "mk3": ("#eef2fa", "#9098aa"),
            "mk4": ("#3ee9ff", "#1a8fa8")}
BODY, BODY_HI, BODY_LO, GRIP = "#46527a", "#7f8ab0", "#2a3150", "#161c33"


def tool_icon(kind, mk):
    hi, lo = TIER_TIP[mk]
    img = blank()
    if kind == "drill":      # a pistol-grip drill, facing right, its bit the tier's colour
        put(img, rect(2, 4, 9, 8) + [(1, 5), (1, 6), (1, 7)], BODY)
        put(img, line(2, 4, 9, 4), BODY_HI)
        put(img, line(2, 8, 9, 8), BODY_LO)
        put(img, rect(4, 9, 6, 12) + [(3, 12)], GRIP)
        put(img, line(4, 9, 4, 12), "navy2")
        put(img, rect(2, 13, 7, 14), GRIP)
        put(img, line(3, 13, 6, 13), "lime")
        put(img, [(7, 9)], "amber")
        put(img, [(4, 6), (6, 6)], BODY_LO)
        put(img, [(8, 5)], "cyan")
        put(img, rect(10, 5, 11, 7), "#9098aa")
        put(img, line(12, 6, 15, 6), hi)
        put(img, [(12, 5), (14, 7), (13, 7), (15, 5)], lo)
    elif kind == "cutter":   # a disc cutter: a toothed disc on a motor with a side handle
        disc_pts = disc(10, 6, 4.7)
        put(img, disc_pts, hi)
        put(img, [p for p in disc_pts if (p[0] - 10) ** 2 + (p[1] - 6) ** 2 > 13 and (p[0] + p[1]) % 2 == 0], lo)
        put(img, disc(10, 6, 2.2), lo)
        put(img, disc(10, 6, 1.0), GRIP)
        put(img, rect(1, 9, 9, 11) + rect(8, 7, 11, 10), BODY)
        put(img, line(1, 9, 9, 9), BODY_HI)
        put(img, line(1, 11, 11, 11) + line(11, 7, 11, 10), BODY_LO)
        put(img, rect(0, 10, 2, 12), GRIP)
        put(img, rect(4, 12, 5, 14), GRIP)
        put(img, [(6, 10)], "cyan")
    elif kind == "scoop":    # a scoop: a deep bowl with a short handle
        bowl = rect(6, 3, 14, 7) + rect(7, 8, 14, 8) + rect(8, 9, 13, 9)
        put(img, bowl, hi)
        put(img, rect(7, 3, 13, 5), lo)
        put(img, line(6, 3, 14, 3), mix(hi, "#ffffff", 0.4))
        put(img, line(7, 6, 7, 8), mix(hi, "#ffffff", 0.3))
        put(img, line(14, 3, 14, 8), lo)
        put(img, line(6, 8, 2, 12) + line(5, 8, 1, 12) + line(6, 9, 2, 13), BODY)
        put(img, rect(0, 12, 2, 14), GRIP)
        put(img, [(1, 14)], "lime")
    else:                    # a zapper: a blaster with a coil and rings the tier's colour
        put(img, rect(2, 4, 9, 8) + [(1, 5), (1, 6), (1, 7)], "navy2")
        put(img, line(2, 4, 9, 4), BODY)
        put(img, rect(4, 2, 7, 3), BODY)
        put(img, rect(4, 5, 7, 6), "cyan")
        put(img, [(4, 5)], "#e8fdff")
        put(img, rect(10, 5, 13, 6), BODY)
        put(img, rect(10, 4, 10, 7) + rect(12, 4, 12, 7), hi)
        put(img, [(14, 5), (14, 6)], hi)
        put(img, [(15, 5), (15, 6)], "#e8fdff")
        put(img, rect(3, 9, 5, 13) + [(2, 12), (2, 13)], GRIP)
        put(img, [(6, 9), (7, 10), (6, 11)], BODY_LO)
        put(img, line(2, 8, 9, 8), BODY_LO)
    return img


# ---------- the suit: visor, vest and boots in fluff, copper, iron and Neon ----------
SUIT_COLOURS = {"fluff": ("#f3f6ff", "#b9c2e0"), "copper": ("#e08a4a", "#9c5428"), "iron": ("#d6dce8", "#8790a3"),
                "neon": ("#3ee9ff", "#1a8fa8")}


def suit_shape(part):
    """A suit piece's pixels: its body, and its edge drawn darker."""
    if part == "visor":
        body = [p for p in rect(1, 5, 14, 10) if p not in ((1, 5), (14, 5), (1, 10), (14, 10))]
        edge = line(2, 10, 13, 10) + [(1, 9), (14, 9)]
    elif part == "vest":
        body = rect(3, 2, 5, 4) + rect(10, 2, 12, 4) + rect(4, 5, 11, 13) + rect(3, 8, 12, 13) + rect(6, 5, 9, 5)
        body = [p for p in body if p not in ((7, 5), (8, 5))]
        edge = line(3, 13, 12, 13) + line(12, 8, 12, 13) + line(7, 6, 7, 13)
    else:
        body = rect(4, 2, 9, 10) + rect(4, 9, 13, 11)
        edge = line(9, 2, 9, 8) + line(4, 11, 13, 11)
    return body, edge


def suit_icon(material, part):
    hi, lo = SUIT_COLOURS[material]
    body, edge = suit_shape(part)
    img = put(blank(), body, hi)
    put(img, edge, lo)
    if material == "fluff":
        put(img, [q for q in body if (q[0] * 3 + q[1] * 2) % 7 == 0], "#dbe2f2")
    else:
        put(img, [q for q in body if q[0] == min(x for x, _ in body) + 1 and q[1] % 3 == 0], "#ffffff")
    if part == "visor":
        put(img, rect(3, 6, 12, 8), "#0b2f3c" if material == "neon" else "cyan")
        put(img, [(4, 6), (5, 6)], "cyan" if material == "neon" else "#e8fdff")
    elif part == "vest":
        put(img, rect(9, 7, 10, 8), "cyan")
    else:
        put(img, rect(3, 12, 14, 13), "navy")
        put(img, line(3, 12, 14, 12), "lime")
        put(img, [(6, 4), (6, 6)], lo)
    return img


def slot_icon(part):
    """An empty suit slot's faint picture of what goes in it."""
    body, _ = suit_shape(part)
    return put(blank(), body, "ink3", 70)


# ---------- the creatures, the players and the Craft Bots (craft_models) ----------
def _coder_face(n):
    img = tile("#e0b08a", 3, n)
    put(img, rect(0, 0, 15, 1), "#3a2a24")
    put(img, [(0, 2), (15, 2), (1, 2)], "#3a2a24")
    put(img, [(3, 10), (12, 10)], "#f0a090")
    put(img, [(6, 11), (7, 12), (8, 12), (9, 11)], "#9a5a4a")
    return img


def _coder_side(n):
    img = tile("#e0b08a", 3, n)
    put(img, rect(0, 0, 15, 7), "#3a2a24")
    put(img, rect(0, 8, 3, 9), "#3a2a24")
    put(img, rect(8, 9, 9, 11), "#c89070")
    return img


def _hair(n):
    img = tile("#3a2a24", 6, n)
    r = rng(n)
    for _ in range(10):
        x, y = (int(v) for v in r.integers(0, T, 2))
        wrap(img, [(x, y), (x, y + 1), (x, y + 2)], "#4e3a30")
    return img


def _suit(front):
    def f(n):
        img = tile("#e8ecf5", 3, n)
        put(img, line(0, 0, 0, 15) + line(15, 0, 15, 15), "#c8cfdc")
        put(img, line(0, 13, 15, 13), "#c8cfdc")
        if front:
            put(img, line(7, 0, 7, 15), "#9aa3b8")
            put(img, [(8, 3), (8, 4)], "#7f8ab0")
            put(img, border(1, 7, 4, 10), "#b9c2d4")
        return img
    return f


def _backpack(n):
    img = panel("navy2", "navy3", n)
    put(img, rect(3, 3, 12, 4), "cyan")
    put(img, rect(3, 3, 5, 4), "#e8fdff")
    for y in (7, 9):
        put(img, line(4, y, 11, y), "bg2")
    put(img, [(12, 12), (12, 11)], "amber")
    return img


def _glove(n):
    img = tile("navy2", 3, n)
    put(img, line(0, 1, 15, 1), "cyan")
    return img


def _boot(n):
    img = tile("#1d2440", 3, n)
    put(img, rect(0, 13, 15, 15), "bg2")
    put(img, line(0, 12, 15, 12), "lime")
    put(img, [(6, 4), (9, 4), (6, 7), (9, 7)], "amber")
    return img


def _belt(n):
    img = tile("navy", 2, n)
    put(img, rect(6, 3, 9, 12), "amber")
    put(img, rect(7, 5, 8, 10), "navy")
    return img


def _visor_glow(n):
    img = tile("cyan", 4, n)
    put(img, line(0, 4, 15, 4), "#9ff6ff")
    put(img, rect(2, 6, 4, 7), "#e8fdff")
    put(img, line(0, 12, 15, 12), "#22b8d8")
    return img


def _fluff_face(n):
    img = fluffy("#f3f6ff", "fluff_white")
    for x0 in (3, 9):  # (big eyes)
        put(img, rect(x0, 5, x0 + 3, 9) + rect(x0 + 1, 4, x0 + 2, 10), "#141826")
        put(img, [(x0 + 1, 5), (x0 + 1, 6), (x0 + 2, 5)], "#ffffff")
        put(img, [(x0 + 2, 8)], "#5c6a96")
    put(img, rect(1, 10, 2, 11) + rect(13, 10, 14, 11), "#ffb0c4")
    put(img, [(7, 12), (8, 12)], "#e07a90")
    return img


def _glitch_body(colour, dark, light):
    def f(n):
        img = tile(colour, 8, n)
        r = rng(n)
        img[r.random((T, T)) < 0.25, :3] = rgb(dark)
        img[r.random((T, T)) < 0.12, :3] = rgb(light)
        for y in range(T):
            if r.random() < 0.2:
                img[y, :, :3] = np.roll(img[y, :, :3], int(r.integers(-4, 5)), axis=0)
        return img
    return f


def _rust_body(n):
    img = tile("navy2", 4, n)
    r = rng(n)
    for _ in range(5):
        x, y = (int(v) for v in r.integers(0, T, 2))
        rad = 1 + r.random() * 1.8
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx * dx + dy * dy <= rad * rad:
                    wrap(img, [(x + dx, y + dy)], r.choice(["#b8582a", "#d9733a", "#8a4020"]))
    for x, y in ((2, 2), (13, 2), (2, 13), (13, 13)):
        put(img, [(x, y)], "ink3")
    put(img, line(0, 7, 15, 7), "navy")
    return img


def _rust_face(n):
    img = _rust_body(n)
    put(img, rect(3, 4, 6, 6) + rect(9, 4, 12, 6), "coral")
    put(img, rect(4, 10, 11, 12), "bg2")
    for x in range(4, 12, 2):
        put(img, line(x, 10, x, 12), "navy3")
    return img


def _eye(colour, core):
    def f(n):
        img = tile(colour, 2, n)
        put(img, rect(6, 6, 9, 9), core)
        return img
    return f


def _track(n):
    """A Rust Walker's track from the side: the tread round the edge, three wheels."""
    img = tile("#1a1e2c", 3, n)
    for x in range(0, T, 3):
        put(img, [(x, 0), (x, 1), (x, 14), (x, 15)], "navy3")
    for cx in (3, 8, 13):
        put(img, disc(cx - 0.5, 7.5, 2.5), "ink3")
        put(img, disc(cx - 0.5, 7.5, 1.0), "navy3")
    return img


def _tread(n):
    img = tile("#1a1e2c", 3, n)
    for y in range(0, T, 3):
        put(img, line(0, y, 15, y), "navy3")
    return img


def _magnet(n):
    img = tile("coral", 4, n)
    put(img, line(0, 0, 15, 0) + line(0, 0, 0, 15), "#ff9a8a")
    put(img, line(0, 15, 15, 15) + line(15, 0, 15, 15), "#c04a3e")
    return img


def _bleep_face(n):
    img = plate("#c8ccd4", n, "#7a7f88", inset=False)
    put(img, rect(3, 5, 6, 8) + rect(9, 5, 12, 8), "#1d6f7a")
    put(img, rect(4, 6, 5, 7) + rect(10, 6, 11, 7), "#7ff0ff")
    put(img, rect(5, 11, 10, 11), "#3a3f48")
    return img


def _bot_face(n):
    img = plate("#e0b030", n, "#8a6a10", inset=False)
    put(img, rect(3, 5, 6, 8) + rect(9, 5, 12, 8), "#0f3a40")
    put(img, rect(4, 6, 5, 7) + rect(10, 6, 11, 7), "#7ff0ff")
    put(img, [(5, 11), (6, 12), (7, 12), (8, 12), (9, 12), (10, 11)], "#0f3a40")
    return img


def _logo_mark(n):
    """Club Coders' mark (the website's logo.svg) in 16 pixels: a rounded navy square in a lime-to-cyan edge, cyan
    braces round a lime play triangle."""
    img = blank()
    put(img, rect(1, 1, 14, 14), "bg2")
    for x, y in border():
        if (x, y) in ((0, 0), (15, 0), (0, 15), (15, 15)):
            continue
        img[y, x, :3] = mix("lime", "cyan", (x + y) / 30)
        img[y, x, 3] = 255
    put(img, [(1, 1), (14, 1), (1, 14), (14, 14)], mix("lime", "cyan", 0.5))
    put(img, [(6, 4), (5, 4), (4, 5), (4, 6), (3, 7), (3, 8), (4, 9), (4, 10), (5, 11), (6, 11)], "cyan")
    put(img, [(9, 4), (10, 4), (11, 5), (11, 6), (12, 7), (12, 8), (11, 9), (11, 10), (10, 11), (9, 11)], "cyan")
    put(img, rect(6, 5, 6, 10) + rect(7, 6, 7, 9) + rect(8, 7, 8, 8) + [(9, 7), (9, 8)], "lime")
    return img


def _spark(n):
    img = tile("#c8fbff", 20, n)
    r = rng(n)
    img[r.random((T, T)) < 0.3, :3] = rgb("#ffffff")
    img[r.random((T, T)) < 0.2, :3] = rgb("cyan")
    return clip(img)


def _metal_dark(n):
    img = tile("navy3", 4, n)
    put(img, line(0, 0, 15, 0), "ink3")
    put(img, line(0, 15, 15, 15), "navy2")
    put(img, [(3, 3), (12, 3), (3, 12), (12, 12)], "ink3")
    return img


FLUFF = {"white": "#f3f6ff", "red": "#ff6b5b", "yellow": "#ffc638", "green": "#8fe04a", "blue": "#4a7dff",
         "purple": "#a066ff", "black": "#2e3348"}

TILES = {
    # the ground and the rock
    "turf_top": _turf_top, "turf_side": _turf_side, "soil": _soil,
    "stone": lambda n: strata("#8e95a6", n),
    "rubble": lambda n: cells("#858b9a", "#4a5060", n),
    "mossy_rubble": lambda n: _moss(cells("#858b9a", "#4a5060", "rubble"), n),
    "lab_floor": _lab_floor, "sand": _sand, "grit": _grit, "water": _water, "ice": _ice, "snow": _snow,
    "clay": _clay, "sandstone_side": _sandstone_side, "sandstone_top": _sandstone_top, "magma": _magma,
    "coal_ore": lambda n: _coal_ore(n),
    "copper_ore": lambda n: vein(strata("#8e95a6", "stone"), n, "amber", "#9c5c1c", n=2),
    "iron_ore": lambda n: vein(strata("#8e95a6", "stone"), n, "#f2f5fb", "#5c6274", n=2),
    "neon_ore": lambda n: _neon_ore(n),
    # trees and plants
    "log_side": lambda n: bark("#8a5f36", "#5e3e22", n), "log_top": lambda n: rings("#6e4a2a", "#d9a868", n),
    "leaves": lambda n: round_leaves("#3f9e3a", n),
    "pine_side": lambda n: bark("#5e4636", "#3a2a20", n), "pine_top": lambda n: rings("#4a3428", "#a8866a", n),
    "pine_leaves": lambda n: needles("#2f7a55", n),
    "pale_side": lambda n: _pale_side(n), "pale_top": lambda n: rings("#d6d0c0", "#e8d8b0", n),
    "pale_leaves": lambda n: round_leaves("#a6d65a", n),
    "glowfruit_leaves": _glowfruit_leaves,
    "cactus_side": _cactus_side, "cactus_top": lambda n: rings("#36803a", "#62c25a", n),
    "sapling": _sapling, "berry_bush": _bush,
    "tall_grass": _cross_plant("#5cbf48"),
    "flower_red": _flower("coral", "amber"), "flower_yellow": _flower("amber", "#ffffff"),
    # built things
    "boards": lambda n: vboards("#d39a5c", "#9a6634", n),
    "pine_boards": lambda n: vboards("#9a8070", "#5e4a3e", n),
    "fabricator_top": _fabricator_top, "fabricator_side": _fabricator_side, "fabricator_bottom": _fabricator_bottom,
    "refinery_top": _refinery_top, "refinery_side": lambda n: _refinery(n, False),
    "refinery_on": lambda n: _refinery(n, True), "refinery_bottom": lambda n: cells("#8a909e", "#4e5463", "refinery_base"),
    "locker_top": _locker_top, "locker_side": _locker_side,
    "glass": _glass, "window": _window, "brick": _brick, "stone_tiles": _stone_tiles,
    "glowstick": _glowstick, "lumen": _lumen,
    "door_low": lambda n: _door(n, False), "door_high": lambda n: _door(n, True),
    "ladder": _ladder,
    "pod_top": _pod_top, "pod_side": _pod_side, "pod_bottom": lambda n: panel("bg2", "navy2", n),
    "grow_bed_top": _grow_bed_top, "grow_bed_side": _grow_bed_side,
    "dead_rack": _rack(0, dead=True),
    "copper_block": lambda n: plate("#e08a4a", n, "#ffc27a"), "iron_block": lambda n: plate("#d6dce8", n, "#8790a3"),
    "neon_block": lambda n: _neon_block(n),
    "overload_top": _overload_top, "overload_side": _overload_side,
    "overload_bottom": lambda n: panel("bg2", "navy2", n),
    "dock_top": lambda n: _dock(n, True), "dock_side": lambda n: _dock(n, False),
    "rift_top": _rift_top, "rift_side": _rift_side, "scrap_pile": _scrap_pile, "rust_pile": _rust_pile,
    # the people, the creatures and the Craft Bots (craft_models), and effects
    "skin": lambda n: tile("#e0b08a", 3, n),
    "coder_face": _coder_face, "coder_side": _coder_side, "coder_hair": _hair,
    "suit": _suit(False), "suit_front": _suit(True), "backpack": _backpack, "glove": _glove, "boot": _boot,
    "belt": _belt, "visor_glow": _visor_glow,
    "fluff_face": _fluff_face, "fluff_foot": lambda n: tile("#ffb38a", 3, n),
    "glitch_body": _glitch_body("magenta", "#b02a9a", "#ffb0f0"),
    "glitch_cyan": _glitch_body("cyan", "#1a8fa8", "#c8fbff"),
    "glitch_eye": _eye("#f3f6ff", "bg"),
    "rust_body": _rust_body, "rust_face": _rust_face, "eye_coral": _eye("coral", "#ffc0b0"),
    "track": _track, "tread": _tread, "magnet": _magnet, "metal_dark": _metal_dark,
    "bleep_face": _bleep_face, "bleep_body": lambda n: plate("#c8ccd4", n, "#7a7f88", inset=False),
    "bot_face": _bot_face,
    "logo_mark": _logo_mark,
    "particle": lambda n: tile("#ffffff", 0, n),
    "spark": _spark,
    **{f"fluff_{c}": (lambda col: (lambda n: fluffy(col, n)))(v) for c, v in FLUFF.items()},
    **ITEM_ICONS,
}

# the tiles craft_models (and the hand) use that no block or item names
MODEL_TILES = ("skin", "coder_face", "coder_side", "coder_hair", "suit", "suit_front", "backpack", "glove", "boot",
               "belt", "visor_glow", "fluff_face", "fluff_foot", "glitch_body", "glitch_cyan", "glitch_eye",
               "rust_body", "rust_face", "eye_coral", "track", "tread", "magnet", "metal_dark", "bleep_face",
               "bleep_body", "bot_face", "logo_mark")
EFFECT_TILES = ("particle", "spark")
GRAIN_STAGES = 4   # (craft_mesh draws stage grain_{meta})
# a tile drawn as frames side by side: frame 0's name -> every frame's name. craft_blocks.ANIMATED says which; a
# block whose side animates has its top and bottom stepped too (the mesher marks the block), so the rack's top gets
# frames as well (its little LED blinks)
FRAMES = {"server_rack_0": [f"server_rack_{k}" for k in range(B.ANIMATED.get("server_rack_0", 4))],
          "rack_top": ["rack_top"] + [f"rack_top_{k}" for k in range(1, B.ANIMATED.get("server_rack_0", 4))]}


def _moss(img, n):
    r = rng(n + "moss")
    for _ in range(6):
        x, y = (int(v) for v in r.integers(0, T, 2))
        y = y // 2
        wrap(img, rect(x, y, x + int(r.integers(1, 4)), y + int(r.integers(0, 2))), r.choice(["#6cbf3a", "#4f9a30", "#8fd64a"]))
    return img


def _coal_ore(n):
    img = strata("#8e95a6", "stone")
    r = rng(n + "chunks")
    x, y = r.random() * T, r.random() * T
    ang = r.random() * 6.3
    for k in range(6):  # (matte black chunks along a seam)
        ang += (r.random() - 0.5) * 1.2
        x, y = x + math.cos(ang) * 2.6, y + math.sin(ang) * 2.0
        xi, yi = int(x), int(y)
        w, h = int(r.integers(1, 3)), int(r.integers(1, 3))
        wrap(img, rect(xi, yi, xi + w, yi + h), "#1b1e27")
        wrap(img, line(xi, yi, xi + w, yi), "#3a3f52")
    return img


def _neon_ore(n):
    img = strata("#8e95a6", "stone")
    img = vein(img, n, "#1a8fa8", "#1a8fa8", n=2, width=2)
    return vein(img, n, "cyan", "#2a6a80", n=2)


def _neon_block(n):
    img = plate("#2ac8e8", n, "#e8fdff")
    put(img, line(5, 10, 10, 5), "#e8fdff")
    put(img, line(6, 10, 10, 6), "#9ff6ff")
    return img


def _pale_side(n):
    img = tile("#e4e0d4", 4, n)
    r = rng(n)
    for x in range(T):
        if r.random() < 0.3:
            img[:, x, :3] *= 0.95
    for _ in range(5):
        x, y = (int(v) for v in r.integers(0, T, 2))
        wrap(img, [(x, y), (x + 1, y)], "#9aa088")
    for _ in range(3):
        x, y = (int(v) for v in r.integers(0, T, 2))
        wrap(img, [(x, y)], "#a6d65a")
    return img


def draw(name):
    """The tile called name, as an H x W x 4 float array (0..255)."""
    for kind in B.TOOL_KINDS:
        for mk in TIER_TIP:
            if name == f"{kind}_{mk}":
                return tool_icon(kind, mk)
    for part, _ in B.SUIT_PARTS:
        for mat in SUIT_COLOURS:
            if name == f"{mat}_{part}":
                return suit_icon(mat, part)
        if name == f"slot_{part}":
            return slot_icon(part)
    if name.startswith("grain_") and name[6:].isdigit():
        return _grain(min(GRAIN_STAGES - 1, int(name[6:])))(name)
    if name.startswith("server_rack_") and name[12:].isdigit():
        return _rack(int(name[12:]))(name)
    if name == "rack_top" or (name.startswith("rack_top_") and name[9:].isdigit()):
        return _rack_top(int(name[9:]) if name != "rack_top" else 0)(name)
    f = TILES.get(name)
    if f is None:
        return tile("#ff00ff", 0, name)  # (a tile with no drawing: bright pink, so it shows)
    return f(name)


def tile_names():
    """Every tile the game draws, in atlas order: the blocks' faces, the items' icons, the crop's stages, the suit's
    empty slots, the models' and effects' tiles, then mods' blocks. Only tiles something uses. A tile with frames
    (FRAMES) has them side by side in one row: frame k is k columns right of frame 0."""
    names, groups = [], {}

    def add(n):
        if not n or n in names or any(n in g for g in groups.values()):
            return
        if n in FRAMES:
            groups[n] = FRAMES[n]
            names.append(("frames", n))
        else:
            names.append(n)
    mods = [b for b in B.BLOCKS if b.get("mod")]
    for b in B.BLOCKS:
        if not b.get("mod"):
            for t in (b["tiles"] or ()):
                add(t)
    for it in B.ITEMS.values():
        if not (it.get("block") is not None and B.BLOCKS[it["block"]].get("mod")):
            add(it.get("icon"))
    for k in range(GRAIN_STAGES):
        add(f"grain_{k}")
    for part, _ in B.SUIT_PARTS:
        add(f"slot_{part}")
    for n in MODEL_TILES + EFFECT_TILES:
        add(n)
    for b in mods:
        for t in (b["tiles"] or ()):
            add(t)
    # lay them out: a group of frames goes where it fits in one row (the next names fill in before it, no gaps)
    out, waiting = [], []
    for n in names:
        if isinstance(n, tuple):
            waiting.append(groups[n[1]])
        else:
            out.append(n)
        while waiting and len(out) % B.ATLAS + len(waiting[0]) <= B.ATLAS:
            out.extend(waiting.pop(0))
    for g in waiting:  # (nothing left to fill the row: start a fresh row's worth of frames)
        if len(out) % B.ATLAS + len(g) > B.ATLAS:
            raise ValueError("craft_art: a tile's frames don't fit in one row of the atlas")
        out.extend(g)
    return out


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
