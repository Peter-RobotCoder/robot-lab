"""Fight Lab's ultra textures (CHANGE 147): the rings' canvas and the boards with the club's names, made once into
BeatEmUp/assets/tex beside the engine's (engine/rw_textures.py: paint, steel, concrete...), and copied for the page by
club-coders/web/make_textures.py. Robot Lab's lab_textures.py does the same for its arena.

Each set has three maps, as the engine's: <name>_albedo (sRGB), <name>_normal, <name>_mr (red: shading in the
cracks, green: roughness, blue: metal). From a seeded generator of their own: the same pictures every time.
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "assets", "tex")
TEX_VERSION = "1"  # bump to regenerate after changing a generator
SETS = ("fight_canvas", "fight_signs")


def ensure():
    """Make the textures if they're missing or out of date (a few seconds, once). Returns the folder."""
    os.makedirs(TEX, exist_ok=True)
    marker = os.path.join(TEX, f"fight_version_{TEX_VERSION}.txt")
    if os.path.exists(marker):
        return TEX
    make()
    for f in os.listdir(TEX):
        if f.startswith("fight_version_"):
            os.remove(os.path.join(TEX, f))
    open(marker, "w").close()
    return TEX


def make():
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    import stage_models
    from engine import rw_textures
    rng = np.random.default_rng(147)

    def save(name, rgb):
        Image.fromarray(np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(TEX, name))

    def save_set(name, albedo, height, strength, rough, metal, ao):
        save(f"{name}_albedo.png", albedo)
        save(f"{name}_normal.png", rw_textures.normal_from_height(height, strength))
        save(f"{name}_mr.png", np.dstack([ao, rough, metal]))

    def smooth(f):
        return f * f * (3 - 2 * f)

    def vnoise(size, cells):
        """Value noise 0..1 that wraps, cells across."""
        g = rng.random((cells, cells))
        x = np.arange(size) * cells / size
        xi = x.astype(int)
        f = smooth(x - xi)
        x1 = (xi + 1) % cells
        fx, fy = f[None, :], f[:, None]
        top = g[np.ix_(xi, xi)] * (1 - fx) + g[np.ix_(xi, x1)] * fx
        bottom = g[np.ix_(x1, xi)] * (1 - fx) + g[np.ix_(x1, x1)] * fx
        return top * (1 - fy) + bottom * fy

    def fbm(size, cells, octaves):
        out, amp, total = 0.0, 1.0, 0.0
        for o in range(octaves):
            out = out + vnoise(size, min(size, cells * 2 ** o)) * amp
            total += amp
            amp *= 0.5
        return out / total

    # the canvas: 2 m in 1024 px (stage_models: a repeat every 2 m), near white so the ring's colour shows through:
    # a tight weave, a mottled wash, scuffs and shoe marks where the fighters move, a few faint stains
    size = 1024
    u = np.arange(size) / size
    weave_u = 0.5 + 0.5 * np.sin(u * 2 * math.pi * 220)
    warp = weave_u[None, :] * 0.5 + weave_u[:, None] * 0.5
    check = ((np.floor(u * 220)[None, :] + np.floor(u * 220)[:, None]) % 2)  # (over and under)
    weave = warp * (0.55 + 0.45 * check)
    mottle = fbm(size, 4, 4)
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)
    for _ in range(420):  # scuffs: short curved smears
        x, y = rng.random(2) * size
        a, L = rng.random() * math.pi * 2, rng.uniform(10, 60)
        pts = [(x + math.cos(a + 0.01 * t) * t, y + math.sin(a + 0.01 * t) * t) for t in range(0, int(L), 4)]
        if len(pts) > 1:
            draw.line(pts, fill=int(rng.uniform(30, 110)), width=int(rng.integers(2, 6)))
    for _ in range(26):  # shoe marks: soft ovals in pairs
        x, y = rng.uniform(40, size - 40, 2)
        a = rng.random() * math.pi
        for s in (-1, 1):
            cx, cy = x + math.cos(a + math.pi / 2) * 14 * s, y + math.sin(a + math.pi / 2) * 14 * s
            draw.ellipse([cx - 9, cy - 20, cx + 9, cy + 20], fill=int(rng.uniform(25, 60)))
    scuff = rw_textures.blur(np.asarray(img, dtype=np.float64) / 255, 2)
    stain = np.clip((fbm(size, 6, 4) - 0.68) * 3.5, 0, 1)
    shade = (0.78 + 0.08 * (mottle - 0.5)) * (0.9 + 0.1 * weave) * (1 - 0.35 * scuff) * (1 - 0.15 * stain)
    albedo = np.dstack([shade, shade * 0.995, shade * 0.985])
    height = 0.6 * weave - 0.3 * scuff + 0.2 * mottle
    rough = np.clip(0.88 + 0.06 * (mottle - 0.5) - 0.18 * scuff, 0.5, 1.0)
    ao = np.clip(0.9 + 0.1 * weave - 0.15 * scuff, 0, 1)
    save_set("fight_canvas", albedo, height, 1.2, rough, np.zeros((size, size)), ao)
    # the boards: one row of the picture each, top first (stage_models.sign_v gives a row's v)
    rows = len(stage_models.SIGNS)
    size, row_h = 1024, 1024 // rows
    sign = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(sign)

    def rgb(c):
        return tuple(int(v * 255 + 0.5) for v in c)
    for r, (text, bg, fg) in enumerate(stage_models.SIGNS):
        top = r * row_h
        draw.rectangle([0, top, size, top + row_h], fill=rgb(bg))
        edge = tuple(int(v * 0.7) for v in rgb(bg))
        draw.rectangle([0, top, size, top + 5], fill=edge)
        draw.rectangle([0, top + row_h - 6, size, top + row_h], fill=edge)
        room = size - 120
        font = ImageFont.load_default(size=int(row_h * 0.5))
        while draw.textbbox((0, 0), text, font=font)[2] > room:  # (the longer boards' lettering smaller)
            font = ImageFont.load_default(size=int(font.size * 0.92))
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], top + (row_h - (box[3] - box[1])) / 2 - box[1]), text,
                  font=font, fill=rgb(fg))
    flat = np.zeros((size, size))
    save_set("fight_signs", np.asarray(sign, dtype=np.float64) / 255, flat, 1.0, flat + 0.5, flat, flat + 1.0)


if __name__ == "__main__":
    import sys
    import time
    sys.path.insert(0, HERE)
    import fight_version
    sys.path.insert(0, fight_version.ENGINE_HOME)
    t = time.perf_counter()
    ensure()
    print(f"textures ready in {time.perf_counter() - t:.1f} s ->", TEX)
