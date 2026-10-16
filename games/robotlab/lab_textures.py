"""Robot Lab's ultra textures (CHANGE 145): the worn steel floor plates and the boards with the club's names, made once
into shared-world-demo/assets/tex beside the engine's (engine/rw_textures.py: paint, steel, tyre, diamond, hazard,
concrete), and copied for the page by club-coders/web/make_textures.py.

Each set has three maps, as the engine's: <name>_albedo (sRGB), <name>_normal, <name>_mr (red: shading in the
cracks, green: roughness, blue: metal). From a seeded generator of their own: the same pictures every time.
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "assets", "tex")
TEX_VERSION = "3"  # bump to regenerate after changing a generator
SETS = ("lab_floor", "lab_signs")


def ensure():
    """Make the textures if they're missing or out of date (a few seconds, once). Returns the folder."""
    os.makedirs(TEX, exist_ok=True)
    marker = os.path.join(TEX, f"version_{TEX_VERSION}.txt")
    if os.path.exists(marker):
        return TEX
    make()
    for f in os.listdir(TEX):
        if f.startswith("version_"):
            os.remove(os.path.join(TEX, f))
    open(marker, "w").close()
    return TEX


def make():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    import arena_models
    from engine import rw_textures
    rng = np.random.default_rng(145)

    def save(name, rgb):
        Image.fromarray(np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(TEX, name))

    def save_set(name, albedo, height, strength, rough, metal, ao):
        save(f"{name}_albedo.png", albedo)
        save(f"{name}_normal.png", rw_textures.normal_from_height(height, strength))
        save(f"{name}_mr.png", np.dstack([ao, rough, metal]))

    def smooth(f):
        return f * f * (3 - 2 * f)

    def vnoise(size, cu, cv=None):
        """Value noise 0..1, cu cells across and cv down (wrapping)."""
        cv = cv or cu
        g = rng.random((cv, cu))
        x, y = np.arange(size) * cu / size, np.arange(size) * cv / size
        xi, yi = x.astype(int), y.astype(int)
        fx, fy = smooth(x - xi)[None, :], smooth(y - yi)[:, None]
        x1, y1 = (xi + 1) % cu, (yi + 1) % cv
        top = g[np.ix_(yi, xi)] * (1 - fx) + g[np.ix_(yi, x1)] * fx
        bottom = g[np.ix_(y1, xi)] * (1 - fx) + g[np.ix_(y1, x1)] * fx
        return top * (1 - fy) + bottom * fy

    def fbm(size, cu, octaves, cv=None):
        out, amp, total = 0.0, 1.0, 0.0
        for o in range(octaves):
            out = out + vnoise(size, min(size, cu * 2 ** o), min(size, (cv or cu) * 2 ** o)) * amp
            total += amp
            amp *= 0.5
        return out / total

    # the floor: one 2 m plate in 1024 px (each plate has its own u, v 0 to 1: arena_models.floor), heavy steel with
    # a mottled mill finish, fine scratches every way, gouges from weapons, tyre rubber, rust and oil in patches,
    # grime in the seams round its edge and round the four bolts
    size = 1024
    mottle, grain = fbm(size, 4, 4), fbm(size, 90, 2, cv=8)
    grain2 = fbm(size, 8, 2, cv=90)
    mix = smooth(np.clip((fbm(size, 3, 3) - 0.35) * 3, 0, 1))
    base = 0.34 + 0.07 * (mottle - 0.5) + 0.035 * (grain * mix + grain2 * (1 - mix) - 0.5)
    img = Image.new("L", (size, size), 0)
    deep = Image.new("L", (size, size), 0)
    draw, draw_deep = ImageDraw.Draw(img), ImageDraw.Draw(deep)
    for _ in range(1900):  # scratches: bright bare metal, short and thin, in drifts of one direction
        x, y = rng.random(2) * size
        a = (math.floor(x / 256) * 1.3 + math.floor(y / 256) * 0.7) % math.pi + rng.normal(0, 0.35)
        L = rng.uniform(8, 70)
        draw.line([(x, y), (x + math.cos(a) * L, y + math.sin(a) * L)], fill=int(rng.uniform(40, 150)), width=1)
    for _ in range(26):  # gouges: deeper, longer, a few curved
        x, y = rng.uniform(60, size - 60, 2)
        a, L, bend = rng.random() * math.pi * 2, rng.uniform(40, 200), rng.normal(0, 0.006)
        pts = []
        for k in range(12):
            t = k / 11 * L
            pts.append((x + math.cos(a + bend * t) * t, y + math.sin(a + bend * t) * t))
        draw_deep.line(pts, fill=200, width=int(rng.integers(1, 4)))
    scratch = np.asarray(img, dtype=np.float64) / 255
    gouge = np.asarray(deep, dtype=np.float64) / 255
    gouge_rim = np.clip(rw_textures.blur(gouge, 2) * 2.2 - gouge * 1.5, 0, 1)
    rubber = np.clip((fbm(size, 3, 4, cv=12) - 0.58) * 4.5, 0, 1) * np.clip((fbm(size, 5, 3) - 0.4) * 3, 0, 1)
    rust = np.clip((fbm(size, 6, 4) - 0.72) * 4, 0, 1) * 0.8
    u = (np.arange(size) + 0.5) / size
    edge_d = np.minimum(np.minimum(u[None, :], 1 - u[None, :]), np.minimum(u[:, None], 1 - u[:, None]))
    seam = np.exp(-edge_d * size / 5.0)
    rust = np.clip(rust + 0.22 * np.exp(-edge_d * size / 40.0) * fbm(size, 24, 3), 0, 1)
    bolt_ring = np.zeros((size, size))
    yy, xx = np.mgrid[0:size, 0:size]
    for cx in (0.045, 0.955):
        for cy in (0.045, 0.955):
            d = np.hypot(xx - cx * size, yy - cy * size)
            bolt_ring = np.maximum(bolt_ring, np.exp(-((d - 13) / 4.0) ** 2) * 0.8 + (d < 11) * 0.3)
    shade = base * (1 + 0.45 * scratch) * (1 - 0.45 * gouge) + 0.1 * gouge_rim
    shade = shade * (1 - 0.65 * rubber) * (1 - 0.5 * seam) * (1 - 0.45 * bolt_ring)
    albedo = np.dstack([shade, shade * 1.005, shade * 1.02])
    rust_col = np.dstack([0.32 + 0.1 * mottle, 0.17 + 0.05 * mottle, 0.08 + 0.02 * mottle])
    albedo = albedo * (1 - rust[..., None] * 0.7) + rust_col * rust[..., None] * 0.7
    height = 0.25 * mottle - 0.35 * scratch - 1.2 * rw_textures.blur(gouge, 1) + 0.4 * gouge_rim - 0.8 * seam - 0.6 * bolt_ring
    rough = np.clip(0.42 + 0.1 * (mottle - 0.5) - 0.18 * scratch + 0.45 * rubber + 0.35 * rust, 0.12, 1.0)
    metal = np.clip(1.0 - 0.9 * rubber - 0.65 * rust, 0, 1)
    ao = np.clip(1.0 - 0.55 * seam - 0.4 * gouge - 0.35 * bolt_ring, 0, 1)
    save_set("lab_floor", albedo, height, 2.5, rough, metal, ao)
    # the boards: one row of the picture each, top first (arena_models.sign_v gives a row's v)
    rows = len(arena_models.SIGNS)
    size, row_h = 1024, 1024 // rows
    sign = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(sign)

    def rgb(c):
        return tuple(int(v * 255 + 0.5) for v in c)
    for r, (text, bg, fg) in enumerate(arena_models.SIGNS):
        top = r * row_h
        draw.rectangle([0, top, size, top + row_h], fill=rgb(bg))
        edge = tuple(int(v * 0.7) for v in rgb(bg))
        draw.rectangle([0, top, size, top + 5], fill=edge)
        draw.rectangle([0, top + row_h - 6, size, top + row_h], fill=edge)
        if text.startswith("STAY"):  # (the warning board: hazard stripes at its ends)
            for i in range(-2, 4):
                for x0 in (i * 26, size - 80 + i * 26):
                    draw.polygon([(x0, top + row_h - 6), (x0 + 13, top + row_h - 6), (x0 + 13 + 60, top + 5), (x0 + 60, top + 5)],
                                 fill=(20, 20, 22))
        room = size - (300 if text.startswith("STAY") else 120)
        font = ImageFont.load_default(size=int(row_h * 0.5))
        while draw.textbbox((0, 0), text, font=font)[2] > room:  # (the longer boards' lettering smaller)
            font = ImageFont.load_default(size=int(font.size * 0.92))
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], top + (row_h - (box[3] - box[1])) / 2 - box[1]), text,
                  font=font, fill=rgb(fg))
    flat = np.zeros((size, size))
    save_set("lab_signs", np.asarray(sign, dtype=np.float64) / 255, flat, 1.0, flat + 0.5, flat, flat + 1.0)


if __name__ == "__main__":
    import sys
    import time
    sys.path.insert(0, HERE)
    import lab_version  # noqa: F401  (the engine package on the path)
    t = time.perf_counter()
    ensure()
    print(f"textures ready in {time.perf_counter() - t:.1f} s ->", TEX)
