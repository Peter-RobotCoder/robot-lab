"""Procedural PBR textures for Robot Wars graphics, generated once and cached in assets/tex.

Each material has three maps, matching simplepbr (the glTF layout):
    albedo  - colour (sRGB)
    normal  - surface bumps (tangent space)
    mr      - R: ambient occlusion, G: roughness, B: metalness
Plus an environment cube map (the arena's lights) for reflections on metal.
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "assets", "tex")
VERSION = "4"  # bump to regenerate after changing a generator

rng = np.random.default_rng(7)


# ---------- helpers ----------
def blur(a, r=2):
    """Cheap box blur that wraps around (so textures tile)."""
    out = a.copy()
    for axis in (0, 1):
        acc = np.zeros_like(out)
        for s in range(-r, r + 1):
            acc += np.roll(out, s, axis=axis)
        out = acc / (2 * r + 1)
    return out


def noise(size, scale, octaves=4):
    """Tileable value noise, 0..1."""
    out = np.zeros((size, size))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        cells = max(2, int(scale * 2 ** o))
        grid = rng.random((cells, cells))
        img = Image.fromarray((grid * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
        layer = np.asarray(img, dtype=np.float64) / 255
        out += layer * amp
        total += amp
        amp *= 0.5
    return out / total


def normal_from_height(h, strength):
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * strength
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * strength
    n = np.dstack([-dx, dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def save(name, rgb):
    arr = np.clip(rgb * 255, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(os.path.join(TEX, name))


def save_set(name, albedo, height, strength, rough, metal, ao=None):
    save(f"{name}_albedo.png", albedo)
    save(f"{name}_normal.png", normal_from_height(height, strength))
    ao = np.ones_like(rough) if ao is None else ao
    save(f"{name}_mr.png", np.dstack([ao, rough, metal]))


def grey(v):
    return np.dstack([v, v, v])


# ---------- materials ----------
def diamond_plate(size=1024):
    y, x = np.mgrid[0:size, 0:size] / size
    cells = 8
    h = np.zeros((size, size))
    for off, angle in ((0.0, 0.785), (0.5, -0.785)):  # two staggered rows of diamonds, alternate angles
        cx = (x * cells + off) % 1.0 - 0.5
        cy = (y * cells + off) % 1.0 - 0.5
        c, s = np.cos(angle), np.sin(angle)
        u, v = cx * c - cy * s, cx * s + cy * c
        d = (u / 0.33) ** 2 + (v / 0.07) ** 2
        h = np.maximum(h, np.clip(1 - d, 0, 1) ** 0.5)
    grime = noise(size, 4)
    scratches = brushed(size, 0.25)
    albedo = grey(0.42 + 0.12 * h + 0.08 * scratches - 0.12 * grime * (1 - h))
    rough = 0.32 + 0.25 * grime * (1 - h) - 0.08 * h + 0.05 * scratches
    ao = 0.75 + 0.25 * np.clip(h + 0.4, 0, 1)
    save_set("diamond", albedo, h + 0.05 * scratches, 6.0, rough, np.ones_like(h), ao)


def brushed(size, strength=1.0):
    streak = rng.random((size, 1)).repeat(size, axis=1)
    streak = blur(streak, 1) * 0.6 + noise(size, 32, 2) * 0.4
    return streak * strength


def brushed_steel(size=512):
    s = brushed(size)
    albedo = grey(0.62 + 0.1 * s)
    save_set("steel", albedo, s * 0.5, 1.5, 0.22 + 0.1 * s, np.ones_like(s))


def painted_metal(size=1024):
    """White paint over steel: tint with the robot's colour. Scratches show bare metal; panel seams and rivets."""
    y, x = np.mgrid[0:size, 0:size] / size
    wear = noise(size, 12, 5)
    chips = (wear > 0.74).astype(float)
    scratches = np.zeros((size, size))
    for _ in range(110):
        x0, y0 = rng.integers(0, size, 2)
        length, ang = rng.integers(20, 140), rng.random() * np.pi
        for t in range(length):
            xi = int(x0 + np.cos(ang) * t) % size
            yi = int(y0 + np.sin(ang) * t) % size
            scratches[yi, xi] = 1
    scratches = np.clip(blur(scratches, 1) * 3, 0, 1)
    bare = np.clip(chips + scratches, 0, 1)
    # panel seams every half texture, rivets along them
    seam = ((np.abs((x * 2) % 1 - 0.5) > 0.49) | (np.abs((y * 2) % 1 - 0.5) > 0.49)).astype(float)
    rv = np.zeros((size, size))
    for i in range(16):
        for j in (0.04, 0.46, 0.54, 0.96):
            for cx, cy in ((i / 16 + 1 / 32, j), (j, i / 16 + 1 / 32)):
                d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
                rv = np.maximum(rv, np.clip(1 - d / 0.009, 0, 1))
    orange_peel = noise(size, 64, 2) * 0.15
    height = orange_peel - seam * 0.8 + rv * 1.2 - scratches * 0.3
    paint = 0.92 - 0.1 * wear
    albedo = grey(paint * (1 - bare) + 0.55 * bare - seam * 0.3)
    rough = 0.45 + 0.15 * wear - 0.2 * bare
    metal = np.clip(bare + rv * 0.8, 0, 1)
    ao = 1 - seam * 0.5
    save_set("paint", albedo, height, 3.0, rough, metal, ao)


def tyre(size=512):
    y, x = np.mgrid[0:size, 0:size] / size
    tread = (np.abs(((x * 12 + np.abs(y - 0.5) * 3) % 1) - 0.5) < 0.18).astype(float)
    h = blur(tread, 2)
    albedo = grey(0.05 + 0.03 * noise(size, 16))
    save_set("tyre", albedo, h, 4.0, 0.85 + 0.1 * noise(size, 8), np.zeros_like(h), 0.7 + 0.3 * h)


def hazard(size=512):
    y, x = np.mgrid[0:size, 0:size] / size
    stripe = (((x + y) * 4) % 1) < 0.5
    wear = noise(size, 8)
    col = np.where(stripe[..., None], np.array([0.95, 0.72, 0.05]), np.array([0.04, 0.04, 0.04]))
    col = col * (1 - 0.3 * (wear[..., None] > 0.7))
    save_set("hazard", col, wear * 0.2, 1.0, 0.5 + 0.2 * wear, np.zeros_like(wear))


def concrete(size=512):
    n = noise(size, 8, 6)
    save_set("concrete", grey(0.3 + 0.15 * n), n, 2.0, 0.85 + 0.1 * n, np.zeros_like(n))


def env_faces(size=256):
    """Arena at night: dark roof with bright light rigs, warm walls, dark floor. Cube faces for reflections."""
    faces = {}
    u, v = np.meshgrid(np.linspace(-1, 1, size), np.linspace(-1, 1, size))
    for name in ("px", "nx", "py", "ny", "pz", "nz"):
        if name == "pz":      # roof: light rigs
            base = 0.05 + 0.03 * noise(size, 4)
            lights = np.zeros((size, size))
            for cx in (-0.6, -0.2, 0.2, 0.6):
                for cy in (-0.5, 0.5):
                    lights += np.exp(-(((u - cx) / 0.08) ** 2 + ((v - cy) / 0.25) ** 2)) * 4
            img = np.dstack([base + lights * 1.0, base + lights * 0.97, base + lights * 0.9])
        elif name == "nz":    # floor
            img = grey(0.06 + 0.02 * noise(size, 8))
        else:                 # sides: dark crowd, a warm glow band, coloured spotlights
            h = (1 - v) / 2   # 0 at bottom, 1 at top of the face
            band = np.exp(-((h - 0.45) / 0.12) ** 2) * 0.6
            spot = np.exp(-((u / 0.15) ** 2 + ((h - 0.8) / 0.08) ** 2)) * 5
            crowd = 0.05 + 0.08 * noise(size, 24) * (h < 0.5)
            img = np.dstack([crowd + band * 1.0 + spot, crowd + band * 0.55 + spot * 0.9, crowd + band * 0.3 + spot])
        faces[name] = np.clip(img, 0, 1)
    order = ("px", "nx", "py", "ny", "pz", "nz")
    for i, name in enumerate(order):
        save(f"env_{i}.png", faces[name])


def ensure():
    """Generate every texture if missing or out of date. Takes a few seconds, once."""
    os.makedirs(TEX, exist_ok=True)
    marker = os.path.join(TEX, f"version_{VERSION}.txt")
    if os.path.exists(marker):
        return TEX
    for gen in (diamond_plate, brushed_steel, painted_metal, tyre, hazard, concrete, env_faces):
        gen()
    for f in os.listdir(TEX):
        if f.startswith("version_"):
            os.remove(os.path.join(TEX, f))
    open(marker, "w").close()
    return TEX


if __name__ == "__main__":
    import time
    t = time.perf_counter()
    ensure()
    print(f"textures ready in {time.perf_counter() - t:.1f} s ->", TEX)
