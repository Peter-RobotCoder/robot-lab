"""Kart Lab graphics: an outdoor circuit in the sun, karts built from boxes and cylinders, a chase camera and the
racing screen (lap, place, speed, countdown, boost meter, minimap, results).

Call init(base, tier) once, then build a TrackVisual for the track and a KartVisual for every kart. The same
classes work in the offline preview (kart_preview.py) and in the class window (kart_client.py). The track and
the kart's state are kart_track.Track and kart_sim's dict: x, y, yaw in degrees (0 = +x, anticlockwise), v
forward and u sideways in m/s. Karts are built with their nose along +x so the kart's yaw is the node's H.

tier: a graphics tier from engine.gfx_tiers; Kart Lab draws all seven (CHANGE 144):
    mesh    every triangle's edges in one colour on black (hidden lines: the faces are black and hide what is
            behind them), no lights, textures, sky or smoke
    lines   the same, but only the shapes' outlines (their edges, folds over CREASE degrees and where a colour
            changes) and a ground grid every GRID metres, fading into the dark: the old vector arcade look
    basic, low, medium, high   as before (the reflection map turned down on medium and high: see init)
    ultra   high with a 4096 shadow map over a wider area, 8x MSAA, a sky with clouds and a haze, skid marks, the
            smooth kart of kart_models.py and the circuit of kart_scenery.py: asphalt with a rubbered racing line,
            kerbs, gravel traps, armco and tyre walls, mown grass, trees, a grandstand with a crowd, the pits, a
            start gantry, and fields, woods and hills out to the horizon (both drawn the same on the page)
The lights and materials follow the tier the driver could run, as rw_gfx does. Everything static is flattened per
material so the whole circuit is a dozen draw calls, and the HUD only sets text that has changed (per-frame
setText is the classic Python-side frame killer: reports/Kart engine netcode and graphics tiers.md). Nothing
here changes the race: the sim never reads a picture.
"""
import math
import os
import random
import sys
import time

import kart_version  # (puts the engine package on the path)
sys.path.insert(0, kart_version.ENGINE_HOME)

from direct.gui.DirectGui import DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from panda3d.core import (AmbientLight, AntialiasAttrib, BitMask32, CardMaker, ColorBlendAttrib, DirectionalLight,  # noqa: E402
                          Filename, Fog, Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, LineSegs, LRotationf, Material, NodePath, OmniBoundingVolume,
                          PNMImage, PTA_uchar, SamplerState, Shader, TextNode, Texture, TextureStage, TransparencyAttrib,
                          Vec3)

from engine import gfx_tiers, line_look, rw_textures  # noqa: E402
from engine.rw_mesh import FORMAT, FORMAT_COLOUR, Mesh, bevel_box, cylinder  # noqa: E402
import kart_models  # noqa: E402  (the ultra kart: numbers only, shared with the page)
import kart_scenery  # noqa: E402  (the ultra circuit: numbers only, shared with the page)

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "assets", "tex")
TEX_VERSION = "2"  # bump to regenerate the circuit's textures after changing a generator

_state = {}

# ---------- colours ----------
SKY = (0.3, 0.5, 0.9)  # (tonemapped with the scene, so a little deeper than it ends up)
SUN_OFFSET = Vec3(30, -45, 45)  # from a kart to the sun: 40 degrees up, so a kart's shadow falls clear of it
KERB_RED, KERB_WHITE = (0.85, 0.12, 0.08, 1), (0.95, 0.95, 0.92, 1)
TARMAC_TINT = (0.9, 0.9, 0.92)
GRASS_TINT = (0.95, 1.0, 0.9)
# the reflection map's light (CHANGE 144). The sky's pictures are screen colours, near white at the horizon, and
# simplepbr took them as light at full strength on top of the fill light: as much light again as the sun, from
# everywhere, so medium and high came out grey and pale beside low. Now the pictures are read as the colours they
# are (sRGB), the sky's light is ENV_STRENGTH of that, and the plain fill keeps ENV_FILL of its own beside it.
ENV_STRENGTH = 0.4
ENV_FILL = 0.4
# mesh and lines (CHANGE 144; the code is engine/line_look.py since CHANGE 145): the line colour (a learner's
# choice: settings.json and their profile, line_colour)
LINE_COLOURS, LINE_COLOUR, CREASE = line_look.LINE_COLOURS, line_look.LINE_COLOUR, line_look.CREASE
GRID = 10.0    # metres between the ground grid's lines on lines


# ---------- textures (generated once into kart/assets/tex) ----------
def _textures():
    """Tarmac, grass and a daytime sky cube map, made with rw_textures' helpers. A few seconds, once."""
    os.makedirs(TEX, exist_ok=True)
    marker = os.path.join(TEX, f"version_{TEX_VERSION}.txt")
    if os.path.exists(marker):
        return
    import numpy as np
    from PIL import Image

    def save(name, rgb):
        Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).save(os.path.join(TEX, name))

    def save_set(name, albedo, height, strength, rough, metal, ao=None):
        save(f"{name}_albedo.png", albedo)
        save(f"{name}_normal.png", rw_textures.normal_from_height(height, strength))
        save(f"{name}_mr.png", np.dstack([np.ones_like(rough) if ao is None else ao, rough, metal]))

    size = 512
    # tarmac: fine grey grit with a few darker patches and tyre-polished streaks along u
    grit = rw_textures.noise(size, 64, 3)
    patches = rw_textures.noise(size, 4, 2)
    streak = rw_textures.brushed(size, 0.3)
    shade = 0.26 + 0.10 * grit - 0.06 * patches - 0.04 * streak
    save_set("tarmac", np.dstack([shade, shade, shade * 1.03]), grit * 0.6 + patches * 0.2, 2.5,
             0.75 + 0.15 * grit - 0.1 * streak, np.zeros_like(grit))
    # grass: green value noise with lighter blades and the odd worn patch
    blades = rw_textures.noise(size, 48, 4)
    worn = rw_textures.noise(size, 3, 2)
    g = 0.42 + 0.22 * blades - 0.1 * worn
    albedo = np.dstack([0.22 + 0.25 * blades + 0.12 * worn, g, 0.08 + 0.1 * blades])
    save_set("grass", albedo, blades, 2.0, 0.9 + 0.05 * blades, np.zeros_like(blades))
    # the sky cube map (a clear day: blue above, a pale horizon, green below): what the paint reflects
    n = 64
    u, v = np.meshgrid(np.linspace(-1, 1, n), np.linspace(-1, 1, n))
    for i, name in enumerate(("px", "nx", "py", "ny", "pz", "nz")):
        if name == "pz":
            h = 1.0 - 0.35 * np.sqrt(u * u + v * v) / math.sqrt(2)
        elif name == "nz":
            h = -0.6 * np.ones_like(u)
        else:
            h = -v / np.sqrt(1 + u * u + v * v)  # the face's height above the horizon
        above = np.clip(h, 0, 1)
        one = np.ones_like(u)
        sky = np.dstack([0.95 - 0.5 * above, 0.95 - 0.25 * above, one])
        ground = np.dstack([0.3 + 0.1 * (-h), 0.45 * one, 0.2 * one])
        save(f"sky_{i}.png", np.where((h >= 0)[..., None], sky, ground))
    _ultra_textures(save, save_set)  # (after the others: rw_textures' random numbers make those the same as ever)
    for f in os.listdir(TEX):
        if f.startswith("version_"):
            os.remove(os.path.join(TEX, f))
    open(marker, "w").close()


def _ultra_textures(save, save_set):
    """(CHANGE 144) ultra's circuit (kart_scenery.MATERIALS): asphalt, worn kerb paint, gravel, mown turf, bark,
    leaves, pine needles and the advertising boards (kart_scenery.SIGNS), from a seeded generator of their own.
    Every one tiles: its random grids wrap round. The metal-rough map's red is the shading in the cracks."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    rng = np.random.default_rng(144)

    def smooth(f):
        return f * f * (3 - 2 * f)

    def vnoise(size, cu, cv=None):
        """Value noise 0..1, cu cells across and cv down."""
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

    def cells(size, n):
        """Cells (Worley noise): the distance to the nearest and the next seed point in cell widths, and a random
        number for the nearest one's cell."""
        off, tone = rng.random((n, n, 2)), rng.random((n, n))
        p = (np.arange(size) + 0.5) * n / size
        px, py = np.meshgrid(p, p)
        cx, cy = px.astype(int), py.astype(int)
        f1, f2, idv = np.full(px.shape, 9.0), np.full(px.shape, 9.0), np.zeros(px.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                gx, gy = (cx + dx) % n, (cy + dy) % n
                d = np.hypot(px - (cx + dx + off[gy, gx, 0]), py - (cy + dy + off[gy, gx, 1]))
                nearer = d < f1
                f2 = np.where(nearer, f1, np.minimum(f2, d))
                idv = np.where(nearer, tone[gy, gx], idv)
                f1 = np.where(nearer, d, f1)
        return f1, f2, idv

    def strokes(size, count, length, dark, light, base, spread=math.pi, lean=0.0):
        """Short lines (blades, needles) in colours between dark and light, drawn again across the edges."""
        img = Image.new("RGB", (size, size), base)
        draw = ImageDraw.Draw(img)
        xy = rng.random((count, 2)) * size
        ang = lean + (rng.random(count) - 0.5) * 2 * spread
        ln = length * (0.5 + rng.random(count))
        t = rng.random(count) ** 1.3
        for (x, y), a, l, k in zip(xy, ang, ln, t):
            x2, y2 = x + math.sin(a) * l, y - math.cos(a) * l
            col = tuple(int(d + (e - d) * k) for d, e in zip(dark, light))
            for ox in ((0, size) if min(x, x2) < 0 else (0, -size) if max(x, x2) >= size else (0,)):
                for oy in ((0, size) if min(y, y2) < 0 else (0, -size) if max(y, y2) >= size else (0,)):
                    draw.line([(x + ox, y + oy), (x2 + ox, y2 + oy)], fill=col, width=1)
        return np.asarray(img, dtype=np.float64) / 255

    # asphalt: 4 m in 1024 px. Small stones (lighter tops, polished smoother) in a dark binder, fine grit, and
    # patches a metre or two across so that no tile repeats plainly
    size = 1024
    f1, f2, tone = cells(size, 230)
    stone = np.clip(1 - f1 * 1.5, 0, 1) ** 0.7 * np.clip((f2 - f1) * 5, 0, 1)
    grit, macro = fbm(size, 160, 3), fbm(size, 3, 4)
    shade = (0.13 + 0.06 * grit + 0.05 * (macro - 0.5)) * (1 + stone * (0.25 + 0.9 * tone ** 3))
    save_set("asphalt", np.dstack([shade, shade, shade * 1.04]), stone * 0.8 + grit * 0.3, 3.0,
             0.92 - 0.3 * stone * tone, np.zeros_like(grit), ao=0.55 + 0.45 * np.clip(stone * 1.4 + 0.35 * grit, 0, 1))
    # kerb paint (u: 2 m along the kerb, v: across it, the road's side at v 0, the bottom of the picture): white
    # with chips worn through to the concrete and the tyres' rubber streaked along its inner half
    size = 512
    wear, fine = fbm(size, 14, 4), fbm(size, 48, 3)
    chips = smooth(np.clip((wear - 0.68) / 0.05, 0, 1))
    across = 1 - (np.arange(size)[:, None] + 0.5) / size
    rubber = np.clip(fbm(size, 2, 4, cv=40) * 1.7 - 0.55, 0, 1) * np.exp(-across / 0.32)
    grey = (0.94 - 0.06 * fine) * (1 - chips) + 0.5 * chips
    grey = grey * (1 - 0.72 * rubber) * (0.94 + 0.06 * fbm(size, 12, 3))
    save_set("kerb", np.dstack([grey, grey, grey]), fine * 0.3 - chips * 0.6, 2.0, 0.5 + 0.35 * rubber + 0.25 * chips,
             np.zeros_like(fine), ao=1 - 0.3 * chips)
    # gravel: 1.5 m. Rounded pebbles in a few stone colours, dark between them
    f1, f2, tone = cells(size, 96)
    pebble = np.clip(1 - f1 * 1.2, 0, 1) ** 0.6 * np.clip((f2 - f1) * 4, 0, 1)
    palette = np.array([[0.66, 0.6, 0.5], [0.52, 0.5, 0.47], [0.74, 0.7, 0.62], [0.47, 0.4, 0.32], [0.6, 0.55, 0.48]])
    col = palette[np.minimum(4, (tone * 5).astype(int))] * (0.85 + 0.3 * fbm(size, 128, 2))[..., None]
    k = smooth(np.clip(pebble * 3, 0, 1))[..., None]
    save_set("gravel", col * k + np.array([0.17, 0.15, 0.13]) * (1 - k), pebble, 5.0, 0.88 - 0.1 * pebble,
             np.zeros_like(pebble), ao=0.4 + 0.6 * np.clip(pebble * 2, 0, 1))
    # turf: 2 m. Blades of grass every way over darker ground, in clumps
    blades = strokes(size, 26000, 7.0, (34, 58, 16), (128, 158, 60), (40, 64, 20))
    clump = 0.88 + 0.24 * fbm(size, 6, 3)
    lum = blades.mean(axis=2)
    save_set("turf", blades * clump[..., None], lum / max(1e-6, lum.max()), 2.5, 0.85 + 0.1 * (1 - lum),
             np.zeros_like(lum), ao=0.6 + 0.4 * lum / max(1e-6, lum.max()))
    # bark (u round the trunk, v up it): furrows running up
    ridge = np.abs(fbm(size, 24, 3, cv=3) - 0.5) * 2
    fine = fbm(size, 64, 3)
    tone = (0.5 + 0.6 * (1 - ridge)) * (0.85 + 0.3 * fine)
    save_set("bark", np.dstack([0.36 * tone, 0.28 * tone, 0.2 * tone]), 1 - ridge, 4.0, 0.9 + 0.05 * ridge,
             np.zeros_like(ridge), ao=0.5 + 0.5 * (1 - ridge))
    # leaves: 2 m. Clusters of leaves, lit on top, dark in the gaps (the trees' and bushes' own colours tint it)
    f1, f2, tone = cells(size, 32)
    leaf = np.sqrt(np.clip(1 - f1 / 0.8, 0, 1)) * np.clip((f2 - f1) * 3, 0, 1)
    light = (0.4 + 0.8 * leaf) * (0.85 + 0.3 * tone)
    save_set("foliage", np.dstack([(0.3 + 0.08 * (tone - 0.5)) * light, 0.48 * light, 0.17 * light]), leaf, 3.0,
             0.75 + 0.1 * (1 - leaf), np.zeros_like(leaf), ao=0.45 + 0.55 * leaf)
    # pine needles: 2 m. Sprays of needles leaning both ways
    needles = strokes(size, 30000, 9.0, (22, 46, 26), (86, 128, 66), (18, 34, 20), spread=0.9)
    lum = needles.mean(axis=2)
    save_set("needles", needles, lum / max(1e-6, lum.max()), 2.5, 0.85 + 0.05 * (1 - lum), np.zeros_like(lum),
             ao=0.55 + 0.45 * lum / max(1e-6, lum.max()))
    # render: pale smooth concrete (walls, the grandstand, the pits), faint stains and streaks run down by the rain
    fine, stains = fbm(size, 64, 3), fbm(size, 5, 4)
    streaks = fbm(size, 40, 3, cv=3)
    tone = 0.8 + 0.05 * (fine - 0.5) - 0.07 * np.clip(stains - 0.5, 0, 1) - 0.05 * np.clip(streaks - 0.55, 0, 1) * 3
    save_set("render", np.dstack([tone, tone * 0.99, tone * 0.97]), fine * 0.5 + stains * 0.2, 1.5, 0.85 + 0.1 * fine,
             np.zeros_like(fine), ao=0.9 + 0.1 * fine)
    # the advertising boards: one row of the picture each, top first (kart_scenery.sign_v gives a row's v)
    rows = len(kart_scenery.SIGNS)
    size, row_h = 1024, 1024 // rows
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=int(row_h * 0.58))

    def rgb(c):
        return tuple(int(v * 255 + 0.5) for v in c)
    for r, (text, bg, fg) in enumerate(kart_scenery.SIGNS):
        top = r * row_h
        draw.rectangle([0, top, size, top + row_h], fill=rgb(bg))
        edge = tuple(int(v * 0.7) for v in rgb(bg))
        draw.rectangle([0, top, size, top + 5], fill=edge)
        draw.rectangle([0, top + row_h - 6, size, top + row_h], fill=edge)
        if text == "START":  # (the gantry's banner: chequered ends)
            sq = row_h // 4
            for i in range(6):
                for j in range(4):
                    if (i + j) % 2:
                        for x0 in (i * sq, size - (i + 1) * sq):
                            draw.rectangle([x0, top + j * sq, x0 + sq - 1, top + (j + 1) * sq - 1], fill=(240, 240, 240))
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0], top + (row_h - (box[3] - box[1])) / 2 - box[1]), text,
                  font=font, fill=rgb(fg))
    flat = np.zeros((size, size))
    save_set("signs", np.asarray(img, dtype=np.float64) / 255, flat, 1.0, flat + 0.45, flat)


class Materials:
    """PBR texture sets for the circuit (kart/assets/tex) and the robots' tyre, steel and paint (engine/assets/tex),
    applied as rw_gfx.Materials does: a Material tinted by colour, plus the albedo, metal-rough and normal maps."""

    def __init__(self, loader, quality):
        rw_textures.ensure()
        _textures()
        self.loader, self.quality = loader, quality
        self.cache = {}
        self.ts_normal = TextureStage("normal")
        self.ts_normal.setMode(TextureStage.M_normal)
        self.ts_mr = TextureStage("metal_rough")
        self.ts_mr.setMode(TextureStage.M_selector)

    def tex(self, name, kind):
        key = (name, kind)
        if key not in self.cache:
            folder = TEX if os.path.exists(os.path.join(TEX, f"{name}_{kind}.png")) else rw_textures.TEX
            t = self.loader.loadTexture(Filename.fromOsSpecific(os.path.join(folder, f"{name}_{kind}.png")))
            if kind == "albedo":
                t.setFormat(Texture.F_srgb)
            t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            t.setMagfilter(SamplerState.FT_linear)
            t.setAnisotropicDegree(gfx_tiers.SETTINGS[self.quality]["aniso"])
            t.setWrapU(SamplerState.WM_repeat)
            t.setWrapV(SamplerState.WM_repeat)
            self.cache[key] = t
        return self.cache[key]

    def apply(self, np_, name=None, colour=(1, 1, 1), rough=1.0, metal=0.0, emission=None):
        if self.quality in gfx_tiers.LOOKS:  # (mesh and lines: black faces and lines, no textures loaded at all)
            return np_
        m = Material()
        m.setBaseColor((*(c ** 2.2 for c in colour), 1))  # screen colours (sRGB) to the linear colours lighting uses
        m.setRoughness(rough)
        m.setMetallic(metal)
        if emission:
            m.setEmission((*emission, 1))
        np_.setMaterial(m, 1)
        if name:
            np_.setTexture(TextureStage.getDefault(), self.tex(name, "albedo"), 1)
            if gfx_tiers.SETTINGS[self.quality]["simplepbr"]:  # (basic: Panda's shaders know nothing of these)
                np_.setTexture(self.ts_mr, self.tex(name, "mr"), 1)
                np_.setTexture(self.ts_normal, self.tex(name, "normal"), 1)
        return np_


def mats():
    return _state["mats"]


def part(parent, mesh, name=None, colour=(1, 1, 1), rough=1.0, metal=0.0, emission=None, pos=(0, 0, 0), hpr=(0, 0, 0),
         materials=None):
    np_ = parent.attachNewNode(mesh.node() if isinstance(mesh, Mesh) else mesh)
    np_.setPos(*pos)
    np_.setHpr(*hpr)
    (materials or mats()).apply(np_, name, colour, rough, metal, emission)
    return np_


# ---------- lighting ----------
SHADOW_AREA = {"ultra": 64.0}  # metres the sun's shadow map covers round the player's kart (40 on the others)
HAZE = (0.62, 0.74, 0.92)       # ultra: the sky at the horizon, which the distance fades into (linear, as lit)
HAZE_DENSITY = 0.0007           # ...how thick the haze is (exponential: a hill 2 km away is a quarter itself)


def init(base, tier="medium", line_colour=None):
    """A sunny day: sky-coloured background, a sun with shadows per tier, a soft blue fill, the sky as the
    reflection map on the tiers that have one. Returns the simplepbr pipeline, or None on basic, mesh and lines.
    line_colour: "#rrggbb" for mesh and lines (else this computer's, else phosphor green)."""
    quality = tier if tier in gfx_tiers.TIERS else gfx_tiers.DEFAULT
    s = gfx_tiers.SETTINGS[quality]
    _state.clear()
    line_look.reset()
    _state["mats"] = Materials(base.loader, quality)
    _state["base"] = base
    if quality in gfx_tiers.LOOKS:
        return init_look(base, quality, line_colour)
    base.setBackgroundColor(*SKY, 1.0)  # (alpha 1: simplepbr clears its scene buffer to this, and a screenshot
    # of a buffer cleared to alpha 0 has a see-through sky)
    render = base.render
    sun = DirectionalLight("sun")
    sun.setColor((2.6, 2.45, 2.2, 1))
    area = SHADOW_AREA.get(quality, 40.0)
    if s["shadow"]:
        # the shadow frustum covers 40 m round the player's kart and only 40 m of depth: ChaseCamera.update
        # moves it along. simplepbr's shadow bias is a share of the depth range, so a frustum over the whole
        # circuit would swallow a kart's shadow (a kart is 1 m tall) and blur it to 15 cm texels (ultra: 64 m
        # at 4096, finer still and further out)
        sun.setShadowCaster(True, s["shadow"], s["shadow"])
        sun.getLens().setFilmSize(area, area)
        far = SUN_OFFSET.length()
        sun.getLens().setNearFar(far - area / 2, far + area / 2)
    sun_np = render.attachNewNode(sun)
    sun_np.setPos(SUN_OFFSET)
    sun_np.lookAt(0, 0, 0)
    render.setLight(sun_np)
    amb = AmbientLight("sky fill")
    amb.setColor((0.22, 0.25, 0.32, 1))
    amb_np = render.attachNewNode(amb)
    render.setLight(amb_np)

    def env_map(simplepbr):
        try:
            cube = base.loader.loadCubeMap(Filename.fromOsSpecific(os.path.join(TEX, "sky_#.png")))
            cube.setFormat(Texture.F_srgb)  # (screen colours: the light they give is their linear colour)
            env = simplepbr.EnvMap(cube, prefiltered_size=32, prefiltered_samples=8, blocking_prepare=True)
            scale_env(env, ENV_STRENGTH)
            return env
        except Exception as e:
            print(f"gfx: no reflection map ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
            return None

    def extra(t):  # ultra: the haze is compiled into simplepbr's shader
        return {"enable_fog": True} if t == "ultra" else {}
    pipeline, used = gfx_tiers.init_pipeline(base, quality, env_map, exposure=0.55, extra=extra)
    if pipeline is not None:
        # 6 cm over the shadow's depth range: a kart's body shadows, flat ground doesn't speckle
        pipeline.shadow_bias = 0.06 / SHADOW_AREA.get(used, 40.0)
    if used != quality:  # the driver couldn't run the tier asked for: the lights and materials follow the one used
        print(f"gfx: {quality} graphics don't run here, using {used}", flush=True)
        _state["mats"].quality = used
        if not gfx_tiers.SETTINGS[used]["shadow"]:
            sun.setShadowCaster(False)
        elif SHADOW_AREA.get(used, 40.0) != area:
            sun.setShadowCaster(True, gfx_tiers.SETTINGS[used]["shadow"], gfx_tiers.SETTINGS[used]["shadow"])
            sun.getLens().setFilmSize(40, 40)
            sun.getLens().setNearFar(SUN_OFFSET.length() - 20, SUN_OFFSET.length() + 20)
    if gfx_tiers.SETTINGS[used]["env_map"]:  # (the sky's light is the fill now: the plain fill steps back)
        amb.setColor((0.22 * ENV_FILL, 0.25 * ENV_FILL, 0.32 * ENV_FILL, 1))
    if not gfx_tiers.SETTINGS[used]["simplepbr"]:
        _state["tone"] = gfx_tiers.basic_look(base, exposure=0.55)  # (Panda's shaders: the lights come down, the tone curve is a post pass)
    if s["msaa"]:
        render.setAntialias(AntialiasAttrib.MMultisample)
    if used == "ultra":
        sun.setCameraMask(SHADOW_MASK)  # (the far country hides from it: ultra_circuit)
        fog = Fog("haze")
        fog.setColor(*HAZE)
        fog.setExpDensity(HAZE_DENSITY)
        render.setFog(fog)
        base.camLens.setFar(4000)  # (the hills are out to 1.3 km)
    _state.update(quality=used, pipeline=pipeline, sun=sun_np)
    return pipeline


def scale_env(env, k):
    """The reflection map's light times k: its nine light-from-everywhere numbers and its blurred sky pictures."""
    import numpy as np
    for i in range(len(env.sh_coefficients)):
        env.sh_coefficients[i] = env.sh_coefficients[i] * k
    tex = env.filtered_env_map
    kind = np.float32 if tex.getComponentWidth() == 4 else np.float16
    for level in range(tex.getNumRamMipmapImages()):
        if tex.hasRamMipmapImage(level):
            data = np.frombuffer(bytes(tex.getRamMipmapImage(level)), dtype=kind) * k
            image = PTA_uchar.emptyArray(0)
            image.setData(data.astype(kind).tobytes())
            tex.setRamMipmapImage(level, image)


def init_look(base, quality, line_colour=None):
    """mesh and lines (engine.line_look): black, no lights or shaders, and a black fog so the far lines fade into
    the dark. Returns None (no pipeline)."""
    fade = (15, 140) if quality == "mesh" else (60, 380)  # (mesh's ground is dense: it fades sooner)
    line_look.init(base, quality, line_colour, fade=fade)
    _state.update(quality=quality, pipeline=None, sun=None)
    return None


def tier():
    """The graphics tier in use (the one init was given, or the lower one the driver could run)."""
    return _state.get("quality", gfx_tiers.DEFAULT)


def follow_sun(x, y, z):
    """Keep the sun's shadow frustum over the player's kart (called by ChaseCamera.update)."""
    sun = _state.get("sun")
    if sun is not None:
        sun.setPos(Vec3(x, y, z) + SUN_OFFSET)


# ---------- mesh and lines (CHANGE 144: the engine's line_look since CHANGE 145) ----------
look, parse_colour, set_line_colour = line_look.look, line_look.parse_colour, line_look.set_line_colour
edges, line_node, wire, blacken, outline = line_look.edges, line_look.line_node, line_look.wire, line_look.blacken, line_look.outline


# ---------- mesh helpers ----------
def quad(mesh, pts, uvs, normal=(0, 0, 1)):
    """One quad with the texture coordinates given (Mesh.poly projects them from the world, which is right for
    tarmac but not for stripes that must run along the track). The winding is flipped if need be so the quad
    faces along normal (up, unless told otherwise)."""
    pts = [Vec3(p) for p in pts]
    face = (pts[1] - pts[0]).cross(pts[2] - pts[0])
    n = Vec3(*normal)
    if face.dot(n) < 0:
        pts, uvs = pts[::-1], list(uvs)[::-1]
    if n.length() < 1e-9:
        n = Vec3(0, 0, 1)
    n.normalize()
    t = pts[1] - pts[0]
    t.normalize()
    start = mesh.count
    for p, (u, v) in zip(pts, uvs):
        mesh.v.addData3(Vec3(p))
        mesh.n.addData3(n)
        mesh.t.addData2(u, v)
        mesh.tg.addData4(t.x, t.y, t.z, 1.0)
        if mesh.c:
            mesh.c.addData4(*mesh.colour)
    mesh.tris.addVertices(start, start + 1, start + 2)
    mesh.tris.addVertices(start, start + 2, start + 3)
    mesh.count += 4


def ribbon(mesh, track, s0, s1, lat_a, lat_b, lift, step=None, u_per_m=1.0, v_scale=1.0):
    """Quads along the track from s0 to s1 between two lateral offsets, lifted off the road. The texture's u runs
    along the track (u_per_m repeats a metre) and v across it."""
    pts_s = [track.s[i] for i in range(track.n) if s0 < track.s[i] < s1] if step is None else []
    if step is not None:
        k = max(1, int(math.ceil((s1 - s0) / step)))
        pts_s = [s0 + (s1 - s0) * j / k for j in range(1, k)]
    edges = []
    for s in [s0] + pts_s + [s1]:
        edges.append((Vec3(*track.point(s, lat_a)) + Vec3(0, 0, lift), Vec3(*track.point(s, lat_b)) + Vec3(0, 0, lift), s))
    for (a0, b0, sa), (a1, b1, sb) in zip(edges, edges[1:]):
        quad(mesh, [a0, a1, b1, b0], [(sa * u_per_m, lat_a * v_scale), (sb * u_per_m, lat_a * v_scale),
                                      (sb * u_per_m, lat_b * v_scale), (sa * u_per_m, lat_b * v_scale)])


def ball(r, seg=12, rings=8, mesh=None, offset=Vec3(0)):
    """A sphere from rings of quads (a driver's helmet, a tree's crown)."""
    m = mesh or Mesh()
    o = Vec3(offset)
    angles = [2 * math.pi * i / seg for i in range(seg + 1)]
    lats = [math.pi * (-0.5 + j / rings) for j in range(rings + 1)]

    def ring(lat):
        pts, nrm = [], []
        for a in angles:
            n = Vec3(math.cos(lat) * math.cos(a), math.cos(lat) * math.sin(a), math.sin(lat))
            pts.append(o + n * r)
            nrm.append(n)
        return pts, nrm
    tang = [Vec3(-math.sin(a), math.cos(a), 0) for a in angles]
    u = [a * r for a in angles]
    for la, lb in zip(lats, lats[1:]):
        pa, na = ring(la)
        pb, nb = ring(lb)
        m.smooth_strip(pa, pb, na, nb, tang, u, la * r, lb * r)
    return m


def soft_dot_texture(size=64):
    img = PNMImage(size, size, 4)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            img.setXelA(x, y, 1, 1, 1, max(0.0, 1 - d) ** 1.8)
    t = Texture("dot")
    t.load(img)
    return t


def dot_texture():
    if "dot" not in _state:
        _state["dot"] = soft_dot_texture()
    return _state["dot"]


# ---------- the circuit ----------
class TrackVisual:
    """The road as a ribbon along the track's centre line, following its hills, with kerbs, a barrier, the start
    line, dash pads, oil, grass and a little trackside scenery. Static, and flattened per material. On ultra the
    road, grass and scenery are kart_scenery's circuit instead (ultra_circuit), with the same dash pads and oil."""
    GRASS_MARGIN = 45.0
    GRASS_CELL = 3.0

    def __init__(self, parent, track):
        self.track = track
        half = track.half
        self.root = parent.attachNewNode("track_visual")
        static = self.root.attachNewNode("static")
        rnd = random.Random(11)
        L = track.length

        ultra = tier() == "ultra"  # (CHANGE 144: kart_scenery's circuit instead of this road, its grass and scenery)
        if not ultra:
            # the road: one quad per centre-line segment, from edge to edge, tarmac tiled in metres
            road = Mesh()
            ribbon(road, track, 0.0, L, half + 0.3, -half - 0.3, 0.0, u_per_m=0.125, v_scale=0.125)
            part(static, road, "tarmac", TARMAC_TINT, rough=1.0, metal=0.0)
            # the centre line: white dashes, 2.5 m every 6 m
            dashes = Mesh()
            s = 3.0
            while s < L - 3.0:
                ribbon(dashes, track, s, s + 2.5, 0.1, -0.1, 0.012, step=2.5)
                s += 6.0
            part(static, dashes, None, (0.85, 0.85, 0.8), rough=0.7, metal=0.0)
            # kerbs along both edges (red and white, 2 m blocks) and the barrier a metre outside them (white and red
            # 4 m blocks, with an inner face, a top and an outer face): vertex colours, one mesh, one draw call
            paint = Mesh(colours=True)
            s = 0.0
            block = 0
            while s < L:
                e = min(L, s + 2.0)
                paint.colour = KERB_RED if block % 2 else KERB_WHITE
                for side in (1, -1):
                    ribbon(paint, track, s, e, side * (half - 0.55), side * (half + 0.2), 0.03, step=2.0)
                s = e
                block += 1
            s = 0.0
            block = 0
            wall_in, wall_out, wall_h = half + 1.0, half + 1.5, 0.55
            while s < L:
                e = min(L, s + 4.0)
                paint.colour = (0.8, 0.1, 0.08, 1) if block % 3 == 2 else (0.92, 0.92, 0.9, 1)
                left = self.left_of((s + e) / 2)
                for side in (1, -1):
                    a0, a1 = Vec3(*track.point(s, side * wall_in)), Vec3(*track.point(e, side * wall_in))
                    b0, b1 = Vec3(*track.point(s, side * wall_out)), Vec3(*track.point(e, side * wall_out))
                    up = Vec3(0, 0, wall_h)
                    # the wall stands on the grass, a little below the road, and its faces reach down into it
                    for p in (a0, a1, b0, b1):
                        p.z -= 0.3
                    uv = [(s, 0), (e, 0), (e, wall_h), (s, wall_h)]
                    quad(paint, [a0, a1, a1 + up, a0 + up], uv, -left * side)          # inner face: towards the road
                    quad(paint, [b1, b0, b0 + up, b1 + up], uv, left * side)           # outer face
                    quad(paint, [a0 + up, a1 + up, b1 + up, b0 + up], uv)             # top
                s = e
                block += 1
            # the start line: a chequered band across the track at s = 0
            sq = 0.5
            cols = int(2 * half / sq)
            for i in range(cols):
                for j in range(3):
                    paint.colour = (0.05, 0.05, 0.05, 1) if (i + j) % 2 else (0.95, 0.95, 0.92, 1)
                    lat = -half + i * sq
                    ribbon(paint, track, j * sq - 1.5 * sq, (j + 1) * sq - 1.5 * sq, lat + sq, lat, 0.015, step=sq)
            # cones at the apex of each sharp bend, and on the grid
            cones = Mesh()
            s = 0.0
            while s < L:
                if abs(track.curvature(s, 18)) >= 30:
                    side = 1 if track.curvature(s, 18) > 0 else -1  # (the inside of the bend)
                    for k in range(3):
                        p = track.point(s + k * 4.0, side * (half + 0.6))
                        cylinder(0.16, 0.3, seg=10, mesh=cones, r_top=0.03, offset=Vec3(p[0], p[1], p[2] + 0.25))
                    s += 24.0
                s += 3.0
            part(static, cones, None, (1.0, 0.45, 0.08), rough=0.6, metal=0.0)
            part(static, paint, None, (1, 1, 1), rough=0.75, metal=0.0)  # (the vertex colours are the paint)

        # dash pads: three glowing chevrons each, pointing along the track (one mesh; its glow pulses in update)
        pads = Mesh()
        for ps, plat in track.boosts:
            for k in range(3):
                a = ps - 1.6 + k * 1.3
                for side in (1, -1):  # each chevron is two arms: the tip ahead in the middle, the tails behind
                    lat_in, lat_out = plat + side * 0.15, plat + side * 1.3
                    p = [track.point(a + 0.9, lat_in), track.point(a + 0.4, lat_in),
                         track.point(a - 0.9, lat_out), track.point(a - 0.4, lat_out)]
                    quad(pads, [Vec3(*q) + Vec3(0, 0, 0.02) for q in p], [(0, 0), (1, 0), (1, 1), (0, 1)])
        # (their own node, not flattened into the static mesh: update() changes their material)
        self.pads = part(self.root, pads, None, (0.1, 0.06, 0.0), rough=0.4, metal=0.0, emission=(3.0, 1.6, 0.2))
        self.pads_mat = self.pads.getMaterial()  # (None on mesh and lines: their outline pulses instead)
        self.pads_lines = None
        # oil: dark shiny patches
        oil = Mesh()  # (a little bigger than the sim's radius: the slick reads before the slide comes)
        for os_, olat in track.oil:
            pts = []
            for k in range(14):
                a = 2 * math.pi * k / 14
                p = track.point(os_ + math.cos(a) * 2.6, olat + math.sin(a) * 1.9)
                pts.append(Vec3(p[0], p[1], p[2] + 0.018))
            oil.poly(pts, Vec3(0, 0, 1))
        part(static, oil, None, (0.16, 0.15, 0.2), rough=0.3, metal=0.4)

        if ultra:  # the circuit of kart_scenery.py, as the page draws it (models/kart_scenery.json), and the sky
            started = time.perf_counter()
            self.circuit = kart_scenery.circuit(track)
            self.ultra_root = ultra_circuit(self.root, self.circuit)
            import numpy as np
            self._ground = (np.array(self.circuit.xs), np.array(self.circuit.ys), np.array(self.circuit.z))
            self.signs = self.root.attachNewNode("signs")
            _state["sky"] = Sky(_state["base"])
            self.circuit_secs = time.perf_counter() - started
        else:
            # the grass: a grid over the track's bounds with a margin, each vertex at the height of the nearest bit
            # of track (a little under the road), easing to a base level away from it, so the ground follows the hill
            self.grass(static, rnd)
            self.scenery(static, rnd)
        self.signs.flattenStrong()
        static.flattenStrong()  # one draw call per material: fast on low-spec laptops
        if look():  # mesh and lines: the circuit's edges, worked out once (the karts' are their own)
            started = time.perf_counter()
            outline(static, extra=self.grid_lines() if look() == "lines" else None)
            self.pads_lines = outline(self.pads)
            for n in self.signs.getChildren():  # (the START sign is written in the line colour)
                n.setColor(*line_look.colour(), 1, 2)
                line_look.keep(n)
            self.lines_secs = time.perf_counter() - started

    def grass(self, parent, rnd):
        import numpy as np
        track = self.track
        x0, y0, x1, y1 = track.bounds()
        m, cell = self.GRASS_MARGIN, self.GRASS_CELL
        xs = np.arange(x0 - m, x1 + m + cell, cell)
        ys = np.arange(y0 - m, y1 + m + cell, cell)
        px = np.array([p[0] for p in track.pts])
        py = np.array([p[1] for p in track.pts])
        pz = np.array([p[2] for p in track.pts])
        gx, gy = np.meshgrid(xs, ys)
        d2 = (gx[..., None] - px) ** 2 + (gy[..., None] - py) ** 2
        near = d2.argmin(axis=2)
        dist = np.sqrt(d2.min(axis=2))
        base = min(pz) - 0.8
        ease = np.clip((dist - track.half - 2.0) / 30.0, 0, 1)
        ease = ease * ease * (3 - 2 * ease)
        # gentle rolling ground away from the track (a value-noise bump), never under the road itself
        bumps = 0.8 * np.sin(gx * 0.07 + 1.0) * np.cos(gy * 0.05) * ease
        z = (pz[near] - 0.06) * (1 - ease) + base * ease + bumps
        mesh = Mesh()
        rows, cols = z.shape
        for j in range(rows):
            for i in range(cols):
                mesh.v.addData3(xs[i], ys[j], float(z[j, i]))
                mesh.n.addData3(0, 0, 1)
                mesh.t.addData2(xs[i] * 0.2, ys[j] * 0.2)
                mesh.tg.addData4(1, 0, 0, 1)
        for j in range(rows - 1):
            for i in range(cols - 1):
                a = j * cols + i
                mesh.tris.addVertices(a, a + 1, a + cols + 1)
                mesh.tris.addVertices(a, a + cols + 1, a + cols)
        mesh.count = rows * cols
        part(parent, mesh, "grass", GRASS_TINT, rough=1.0, metal=0.0)
        self._ground = (xs, ys, z)

    def grid_lines(self):
        """lines: the ground grid, a line every GRID metres each way over the grass, lying exactly on its triangles
        (each line is cut where it crosses their edges) and lifted 2 cm. Returns (m, 2, 3) segment ends."""
        import numpy as np
        xs, ys, z = self._ground
        cell = self.GRASS_CELL

        def height(x, y):  # the grass's own surface: each cell is two triangles split along its rising diagonal
            i = np.clip(((x - xs[0]) // cell).astype(int), 0, len(xs) - 2)
            j = np.clip(((y - ys[0]) // cell).astype(int), 0, len(ys) - 2)
            fx, fy = (x - xs[i]) / cell, (y - ys[j]) / cell
            z00, z10, z01, z11 = z[j, i], z[j, i + 1], z[j + 1, i], z[j + 1, i + 1]
            low = z00 + fx * (z10 - z00) + fy * (z11 - z10)    # (the triangle under the diagonal)
            high = z00 + fy * (z01 - z00) + fx * (z11 - z01)   # (the one over it)
            return np.where(fx >= fy, low, high) + 0.02

        segs = []
        for axis in (0, 1):
            along, across = (ys, xs) if axis == 0 else (xs, ys)
            first = math.ceil(across[0] / GRID) * GRID
            for c in np.arange(first, across[-1], GRID):
                # the cuts: every cell edge, and where the line crosses each cell's diagonal
                k = np.clip(int((c - across[0]) // cell), 0, len(across) - 2)
                offset = c - across[k]
                cuts = np.unique(np.concatenate([along, along[:-1] + offset]))
                cuts = cuts[(cuts >= along[0]) & (cuts <= along[-1])]
                x, y = (np.full_like(cuts, c), cuts) if axis == 0 else (cuts, np.full_like(cuts, c))
                p = np.stack([x, y, height(x, y)], axis=1)
                segs.append(np.stack([p[:-1], p[1:]], axis=1))
        if not segs:
            return np.zeros((0, 2, 3))
        segs = np.concatenate(segs)
        # none under the road: the road's black is pushed back to let its own edges win, and a grid line a few
        # centimetres under it would show through far away
        mid = segs.mean(axis=1)[:, :2]
        road = np.array([p[:2] for p in self.track.pts])
        near = np.full(len(mid), np.inf)
        for k in range(0, len(mid), 4096):
            d = ((mid[k:k + 4096, None, :] - road[None, :, :]) ** 2).sum(axis=2)
            near[k:k + 4096] = np.sqrt(d.min(axis=1))
        return segs[near > self.track.half + 1.6]

    def left_of(self, s):
        """The unit vector pointing left across the track at s."""
        h = math.radians(self.track.heading(s))
        return Vec3(-math.sin(h), math.cos(h), 0)

    def ground_z(self, x, y):
        """The grass height at (x, y), for placing scenery."""
        xs, ys, z = self._ground
        i = min(len(xs) - 1, max(0, int((x - xs[0]) / self.GRASS_CELL + 0.5)))
        j = min(len(ys) - 1, max(0, int((y - ys[0]) / self.GRASS_CELL + 0.5)))
        return float(z[j, i])

    def clear_of_track(self, x, y, margin):
        """Is (x, y) at least margin metres from the road (every part of it)?"""
        t = self.track
        return all(math.hypot(x - p[0], y - p[1]) > t.half + margin for p in t.pts[::3])

    def scenery(self, parent, rnd):
        """Trees (a cone on a trunk), a grandstand by the start, and a start gantry over the line."""
        t = self.track
        half, L = t.half, t.length
        trunks, crowns = Mesh(), Mesh()
        placed = []
        tries = 0
        while len(placed) < 28 and tries < 400:
            tries += 1
            s = rnd.uniform(0, L)
            side = rnd.choice((1, -1))
            lat = side * (half + rnd.uniform(7.0, 24.0))
            x, y, _ = t.point(s, lat)
            if not self.clear_of_track(x, y, 4.0) or any(math.hypot(x - a, y - b) < 6.0 for a, b in placed):
                continue
            if s < 30 or s > L - 15:  # (the grandstand's spot)
                continue
            placed.append((x, y))
            z = self.ground_z(x, y)
            h = rnd.uniform(3.5, 5.5)
            cylinder(0.22, h * 0.25, seg=8, mesh=trunks, offset=Vec3(x, y, z + h * 0.25))
            cylinder(h * 0.32, h * 0.38, seg=10, mesh=crowns, r_top=0.0, offset=Vec3(x, y, z + h * 0.5 + h * 0.38))
        part(parent, trunks, None, (0.35, 0.22, 0.12), rough=1.0, metal=0.0)
        part(parent, crowns, None, (0.12, 0.42, 0.16), rough=1.0, metal=0.0)
        # the grandstand: three tiers and a roof on the left of the start straight, facing the track
        stand = Mesh(tile=0.5)
        s0, s1 = -6.0, 22.0
        left = self.left_of((s0 + s1) / 2)
        along = Vec3(left.y, -left.x, 0)  # (the track's direction there)
        for tier_ in range(3):
            lat_a, lat_b = half + 5.0 + tier_ * 1.6, half + 5.0 + (tier_ + 1) * 1.6
            hgt = 0.9 + tier_ * 0.9
            a0, a1 = Vec3(*t.point(s0, lat_a)), Vec3(*t.point(s1, lat_a))
            b0, b1 = Vec3(*t.point(s0, lat_b)), Vec3(*t.point(s1, lat_b))
            base = min(self.ground_z(a0.x, a0.y), self.ground_z(a1.x, a1.y)) - 0.3
            for p in (a0, a1, b0, b1):
                p.z = base
            up = Vec3(0, 0, hgt)
            uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
            quad(stand, [a1, a0, a0 + up, a1 + up], uv, -left)           # the step's riser, facing the track
            quad(stand, [a0 + up, a1 + up, b1 + up, b0 + up], uv)        # its tread
            quad(stand, [a0, b0, b0 + up, a0 + up], uv, -along)          # the ends
            quad(stand, [b1, a1, a1 + up, b1 + up], uv, along)
            if tier_ == 2:
                quad(stand, [b0, b1, b1 + up, b0 + up], uv, left)        # the back
        part(parent, stand, "concrete", (0.55, 0.58, 0.66), rough=1.0, metal=0.0)
        posts, roof = Mesh(), Mesh()
        for s in (s0 + 1.0, (s0 + s1) / 2, s1 - 1.0):
            x, y, _ = t.point(s, half + 9.5)
            z = self.ground_z(x, y)
            cylinder(0.12, 2.6, seg=8, mesh=posts, offset=Vec3(x, y, z + 2.6))
        a0, a1 = Vec3(*t.point(s0, half + 4.6)), Vec3(*t.point(s1, half + 4.6))
        b0, b1 = Vec3(*t.point(s0, half + 10.2)), Vec3(*t.point(s1, half + 10.2))
        zr = self.ground_z(b0.x, b0.y) + 5.1
        for p in (a0, a1):
            p.z = zr + 0.6
        for p in (b0, b1):
            p.z = zr
        uv = [(0, 0), (1, 0), (1, 1), (0, 1)]
        quad(roof, [a0, a1, b1, b0], uv, (0, 0, 1))
        quad(roof, [b0, b1, a1, a0], uv, (0, 0, -1))
        part(parent, posts, "steel", (0.6, 0.6, 0.62), rough=0.6, metal=1.0)
        part(parent, roof, None, (0.85, 0.15, 0.12), rough=0.7, metal=0.0)
        # the start gantry: two posts and a beam over the line, with a sign
        gantry = Mesh()
        for side in (1, -1):
            x, y, z = t.point(0.0, side * (half + 1.8))
            cylinder(0.14, 2.6, seg=10, mesh=gantry, offset=Vec3(x, y, z + 2.6))
        a, b = Vec3(*t.point(0.0, half + 1.8)), Vec3(*t.point(0.0, -half - 1.8))
        mid = (a + b) / 2
        beam = part(parent, bevel_box(0.2, (a - b).length() / 2 + 0.2, 0.2, 0.03), "steel", (0.6, 0.6, 0.62),
                    rough=0.6, metal=1.0, pos=(mid.x, mid.y, mid.z + 5.2), hpr=(t.heading(0.0), 0, 0))
        part(parent, gantry, "steel", (0.6, 0.6, 0.62), rough=0.6, metal=1.0)
        self.signs = self.root.attachNewNode("signs")  # (apart from the rest: on mesh and lines it is lettering)
        sign = TextNode("start")
        sign.setText("START")
        sign.setAlign(TextNode.ACenter)
        for face in (1, -1):  # readable from both sides
            snp = self.signs.attachNewNode(sign)
            snp.setPos(mid.x, mid.y, mid.z + 5.6)
            snp.setHpr(t.heading(0.0) + (90 if face > 0 else -90), 0, 0)
            snp.setPos(snp, 0, face * -0.25, 0)
            snp.setScale(1.1)
            mats().apply(snp, None, (1, 1, 1), 0.5, 0, emission=(1.2, 1.2, 1.2))
        del beam

    def height_at(self, s):
        return self.track.height(s)

    def update(self, t):
        """t: a clock in seconds, for the dash pads' pulse."""
        glow = 2.4 + 1.2 * math.sin(t * 5)
        if self.pads_mat is not None:
            self.pads_mat.setEmission((glow, glow * 0.55, glow * 0.07, 1))
        elif self.pads_lines is not None:
            k = 1.0 if int(t * 4) % 2 else 0.45
            self.pads_lines.setColorScale(k, k, k, 1)

    def destroy(self):
        for key in ("sky", "skids"):  # (ultra: the dome rides on the camera, the marks are on render)
            old = _state.pop(key, None)
            if old is not None:
                (old.dome if key == "sky" else old.np).removeNode()
        self.root.removeNode()



# ---------- ultra (CHANGE 144) ----------
_SKY_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
varying vec3 v_dir;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_dir = p3d_Vertex.xyz;
}
"""
# the sky's colour is light (simplepbr's tone curve comes after, as for the scene): blue overhead, the haze at the
# horizon, a sun with a glow, and clouds from a few octaves of value noise drifting slowly
_SKY_FRAG = """#version 120
uniform vec3 zenith;
uniform vec3 horizon;
uniform vec3 sun_dir;
uniform float osg_FrameTime;
varying vec3 v_dir;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
    float s = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; ++i) {
        s += a * noise(p);
        p = p * 2.03 + vec2(1.7, 9.2);
        a *= 0.5;
    }
    return s;
}
void main() {
    vec3 d = normalize(v_dir);
    float h = d.z;
    vec3 col = mix(horizon, zenith, pow(clamp(h, 0.0, 1.0), 0.45));
    float s = max(dot(d, sun_dir), 0.0);
    if (h > 0.0) {
        vec2 p = d.xy / (h + 0.12) * 1.3 + vec2(osg_FrameTime * 0.006, osg_FrameTime * 0.002);
        float c = fbm(p);
        float cover = smoothstep(0.52, 0.78, c) * smoothstep(0.0, 0.18, h);
        vec3 cloud = mix(vec3(1.25, 1.25, 1.3), vec3(0.62, 0.66, 0.76), smoothstep(0.62, 1.0, c));
        col = mix(col, cloud * (0.85 + 0.5 * pow(s, 6.0)), cover * 0.92);
    } else {
        col = horizon * (1.0 + h * 1.5);
    }
    col += vec3(1.0, 0.92, 0.75) * (pow(s, 900.0) * 40.0 + pow(s, 24.0) * 0.35);
    gl_FragColor = vec4(col, 1.0);
}
"""
SKY_ZENITH = (0.11, 0.26, 0.78)


class Sky:
    """ultra: a dome round the camera (it follows the camera, never turns with it) drawn behind everything with its
    own small shader."""

    def __init__(self, base):
        self.dome = base.camera.attachNewNode(ball(1500.0, 32, 16).node())
        self.dome.setCompass(base.render)  # (the camera's place, the world's directions)
        self.dome.setBin("background", 0)
        self.dome.setDepthWrite(False)
        self.dome.setDepthTest(False)
        self.dome.setTwoSided(True)
        self.dome.setLightOff(5)
        self.dome.setFogOff(5)
        self.dome.setShader(Shader.make(Shader.SL_GLSL, _SKY_VERT, _SKY_FRAG), 50)  # (over simplepbr's, on render)
        sun = Vec3(SUN_OFFSET)
        sun.normalize()
        self.dome.setShaderInput("sun_dir", sun)
        self.dome.setShaderInput("zenith", Vec3(*SKY_ZENITH))
        self.dome.setShaderInput("horizon", Vec3(*HAZE))
        self.dome.node().setBounds(OmniBoundingVolume())  # (never culled: it is always round the camera)
        self.dome.node().setFinal(True)


SHADOW_MASK = BitMask32.bit(5)  # ultra: the sun's shadow camera sees what doesn't hide from this (the far and the flat do)


def _part_arrays(part):
    """A kart_scenery Part as numpy arrays: positions, normals, uvs, colours (screen colours), indices."""
    import numpy as np
    return (np.array(part.p, dtype=np.float64).reshape(-1, 3), np.array(part.n, dtype=np.float64).reshape(-1, 3),
            np.array(part.uv, dtype=np.float64).reshape(-1, 2), np.array(part.c, dtype=np.float64).reshape(-1, 3),
            np.array(part.idx, dtype=np.int64))


def uv_tangents(pos, nrm, uv, idx):
    """Each vertex's tangent (along u, square to the normal) and its handedness, from its triangles' texture
    coordinates (where they have none, any direction square to the normal)."""
    import numpy as np
    tri = idx.reshape(-1, 3)
    e1, e2 = pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]]
    d1, d2 = uv[tri[:, 1]] - uv[tri[:, 0]], uv[tri[:, 2]] - uv[tri[:, 0]]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    inv = np.where(np.abs(det) > 1e-12, 1.0 / np.where(np.abs(det) > 1e-12, det, 1.0), 0.0)[:, None]
    sdir = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * inv
    tdir = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * inv
    tan, bit = np.zeros_like(pos), np.zeros_like(pos)
    for k in range(3):
        np.add.at(tan, tri[:, k], sdir)
        np.add.at(bit, tri[:, k], tdir)
    tan -= nrm * (nrm * tan).sum(axis=1, keepdims=True)
    length = np.linalg.norm(tan, axis=1, keepdims=True)
    up = np.where(np.abs(nrm[:, 2:3]) < 0.9, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
    spare = np.cross(up, nrm)
    tan = np.where(length > 1e-9, tan / np.maximum(length, 1e-12), spare / np.maximum(np.linalg.norm(spare, axis=1, keepdims=True), 1e-12))
    w = np.where((np.cross(nrm, tan) * bit).sum(axis=1) < 0, -1.0, 1.0)
    return tan, w


def ultra_circuit(parent, circuit):
    """ultra (CHANGE 144): kart_scenery's circuit, as models/kart_scenery.json has it for the page: one Geom per
    material (and far or near), holding the circuit's own parts and every instance of every shape in that
    material, so the whole circuit is a couple of dozen draw calls. The far country and everything flat (the road,
    grass, kerbs, tufts) hide from the sun's shadow camera: the shadows only reach round the karts, and the ground
    only has shadows cast on it. Returns the node."""
    import numpy as np
    shapes = kart_scenery.shapes_once()
    groups = {}
    for p in circuit.near.all() + circuit.far.all():
        groups.setdefault((p.material, p.far), []).append(_part_arrays(p))
    for shape, rows in circuit.inst.items():
        inst = np.array(rows, dtype=np.float64)
        h = np.radians(inst[:, 3])[:, None]
        c, s, k = np.cos(h), np.sin(h), inst[:, 4:5]
        for p in shapes[shape]:
            pos, nrm, uv, col, idx = _part_arrays(p)
            n, v = len(inst), len(pos)
            P = np.stack([(c * pos[:, 0] - s * pos[:, 1]) * k + inst[:, 0:1], (s * pos[:, 0] + c * pos[:, 1]) * k + inst[:, 1:2],
                          pos[:, 2] * k + inst[:, 2:3]], axis=2).reshape(-1, 3)
            N = np.stack([c * nrm[:, 0] - s * nrm[:, 1], s * nrm[:, 0] + c * nrm[:, 1], np.broadcast_to(nrm[:, 2], (n, v))],
                         axis=2).reshape(-1, 3)
            C = (col[None] * inst[:, None, 5:8] if p.tint else np.broadcast_to(col, (n, v, 3))).reshape(-1, 3)
            I = (idx[None, :] + (np.arange(n) * v)[:, None]).reshape(-1)
            groups.setdefault((p.material, p.far), []).append((P, N, np.tile(uv, (n, 1)), C, I))
    root = parent.attachNewNode("ultra circuit")
    m = mats()
    for (material, far), items in sorted(groups.items()):
        base, idx = 0, []
        for item in items:
            idx.append(item[4] + base)
            base += len(item[0])
        pos = np.concatenate([i[0] for i in items])
        nrm = np.concatenate([i[1] for i in items])
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
        uv = np.concatenate([i[2] for i in items])
        col = np.clip(np.concatenate([i[3] for i in items]), 0.0, None) ** 2.2  # (screen colours to linear)
        idx = np.concatenate(idx)
        tan, w = uv_tangents(pos, nrm, uv, idx)
        rows = np.hstack([pos, nrm, uv, tan, w[:, None], col, np.ones((len(pos), 1))]).astype(np.float32)
        vdata = GeomVertexData(material, FORMAT_COLOUR, Geom.UH_static)
        vdata.uncleanSetNumRows(len(pos))
        vdata.modifyArray(0).modifyHandle().setData(rows.tobytes())
        tris = GeomTriangles(Geom.UH_static)
        tris.setIndexType(Geom.NT_uint32)
        tris.modifyVertices().modifyHandle().setData(idx.astype(np.uint32).tobytes())
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode(f"{material}{' far' if far else ''}")
        node.addGeom(geom)
        np_ = root.attachNewNode(node)
        look_ = kart_scenery.MATERIALS[material]
        m.apply(np_, look_["texture"], tuple(look_["colour"]), look_["rough"], look_["metal"],
                tuple(look_["emission"]) if look_.get("emission") else None)
        if look_.get("two_sided"):
            np_.setTwoSided(True)
        if look_.get("decal"):
            np_.setDepthOffset(1)
        if far or look_.get("flat"):  # (the ground needn't fill the shadow map: it only has shadows cast on it)
            np_.hide(SHADOW_MASK)
    return root


class SkidMarks:
    """ultra: dark marks left on the road by drifting tyres: a ring of COUNT quads in one mesh (one draw call), the
    oldest written over first."""
    COUNT = 1600

    def __init__(self, parent):
        self.vdata = GeomVertexData("skid marks", GeomVertexFormat.getV3n3c4(), Geom.UH_dynamic)
        self.vdata.setNumRows(self.COUNT * 4)  # (all at the origin: nothing to see until a mark is written)
        tris = GeomTriangles(Geom.UH_static)
        tris.setIndexType(Geom.NT_uint32)
        for q in range(self.COUNT):
            tris.addVertices(q * 4, q * 4 + 1, q * 4 + 2)
            tris.addVertices(q * 4, q * 4 + 2, q * 4 + 3)
        geom = Geom(self.vdata)
        geom.addPrimitive(tris)
        node = GeomNode("skid marks")
        node.addGeom(geom)
        node.setBounds(OmniBoundingVolume())
        node.setFinal(True)
        self.np = parent.attachNewNode(node)
        mats().apply(self.np, None, (0.04, 0.04, 0.045), rough=0.9, metal=0.0)
        self.np.setTransparency(TransparencyAttrib.M_alpha)
        self.np.setDepthWrite(False)
        self.np.setDepthOffset(1)
        self.np.setBin("transparent", 5)
        self.next = 0

    def add(self, a, b, width, alpha=0.6):
        """A mark from point a to point b (Vec3s on the road), width metres wide."""
        along = b - a
        along.z = 0
        if along.length() < 1e-4:
            return
        along.normalize()
        side = Vec3(-along.y, along.x, 0) * (width / 2)
        row = self.next * 4
        self.next = (self.next + 1) % self.COUNT
        v = GeomVertexWriter(self.vdata, "vertex")
        n = GeomVertexWriter(self.vdata, "normal")
        c = GeomVertexWriter(self.vdata, "color")
        for w in (v, n, c):
            w.setRow(row)
        for p in (a - side, b - side, b + side, a + side):
            v.setData3(p)
            n.setData3(0, 0, 1)
            c.setData4(1, 1, 1, alpha)


def skid_marks():
    """The circuit's one set of skid marks (made when first needed), or None below ultra."""
    if tier() != "ultra" or "base" not in _state:
        return None
    if "skids" not in _state:
        _state["skids"] = SkidMarks(_state["base"].render)
    return _state["skids"]


def geom_of(parts):
    """One Geom from kart_models parts (dicts of flat lists), in rw_mesh's format (with tangents for the maps)."""
    import numpy as np
    pos = np.concatenate([np.array(p["positions"], dtype=np.float32).reshape(-1, 3) for p in parts])
    nrm = np.concatenate([np.array(p["normals"], dtype=np.float32).reshape(-1, 3) for p in parts])
    uvs = np.concatenate([np.array(p["uvs"], dtype=np.float32).reshape(-1, 2) for p in parts])
    idx, base = [], 0
    for p in parts:
        idx.append(np.array(p["indices"], dtype=np.uint32) + base)
        base += len(p["positions"]) // 3
    up = np.where(np.abs(nrm[:, 2:3]) < 0.9, np.array([[0, 0, 1]]), np.array([[1, 0, 0]])).astype(np.float32)
    tan = np.cross(up, nrm)
    tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
    rows = np.hstack([pos, nrm, uvs, tan, np.ones((len(pos), 1), dtype=np.float32)]).astype(np.float32)
    vdata = GeomVertexData("ultra kart", FORMAT, Geom.UH_static)
    vdata.uncleanSetNumRows(len(pos))
    vdata.modifyArray(0).modifyHandle().setData(rows.tobytes())
    tris = GeomTriangles(Geom.UH_static)
    tris.setIndexType(Geom.NT_uint32)
    tris.modifyVertices().modifyHandle().setData(np.concatenate(idx).astype(np.uint32).tobytes())
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    return geom


def ultra_model():
    """The ultra kart's Geoms, one per role, made once: {"body": {role: Geom}, "wheel": {...}, "steering": {...},
    "notes": ...}."""
    if "ultra_model" not in _state:
        model = kart_models.kart()
        out = {"notes": model["notes"]}
        for key in ("body", "wheel", "steering"):
            roles = {}
            for p in model[key]:
                roles.setdefault(p["role"], []).append(p)
            out[key] = {role: geom_of(ps) for role, ps in roles.items()}
        _state["ultra_model"] = out
    return _state["ultra_model"]


def role_look(role, colour):
    """(colour, rough, metal, texture set) for a role of the ultra kart; colour: the design's."""
    look_ = kart_models.ROLES[role]
    c = tuple(look_["colour"]) if look_["colour"] else colour
    name = "steel" if role == "metal" else None  # (smooth paint and slick tyres: the robots' textures are blotchy on curves)
    return c, look_["rough"], look_["metal"], name


# ---------- karts ----------
WHEEL_R, WHEEL_W = kart_models.WHEEL_R, kart_models.WHEEL_W
WHEELS = kart_models.WHEELS  # (x, y): front left, front right, rear left, rear right
MAX_STEER = 26.0  # degrees the front wheels turn at full lock (a picture, not the physics)


class KartVisual:
    """A kart from procedural shapes: a bevelled body in the design's colour, side pods, four tyres with hubs, a
    seat, a round-headed driver in a helmet holding the wheel, a rear wing, a boost glow and drift smoke."""
    PUFFS = 8

    def __init__(self, parent, design, mats_=None):
        self.m = mats_ or mats()
        colour = tuple(v / 255 for v in design.get("colour", (220, 60, 50)))
        self.parent = parent
        self.root = parent.attachNewNode("kart")
        self.body = self.root.attachNewNode("body")  # (pitch and roll go on this; the wheels stay on the road)
        self.steering = None             # ultra: the steering wheel, turned with the front wheels
        self.skid_last = [None, None]    # ultra: where each rear tyre's skid mark last ended
        if tier() == "ultra":
            self.ultra(colour)
        else:
            self.boxes(colour)
        # the boost glow: a soft orange disc at the back (a billboard, so it reads from any angle)
        cm = CardMaker("glow")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.glow = self.root.attachNewNode(cm.generate())
        self.glow.setTexture(dot_texture())
        self.glow.setPos(-0.9, 0, 0.3)
        self.glow.setBillboardPointEye()
        self.glow.setLightOff(1)
        self.glow.setShaderOff(1)
        self.glow.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                                  ColorBlendAttrib.O_one))
        self.glow.setDepthWrite(False)
        self.glow.setBin("fixed", 25)
        self.glow.setColor(1.0, 0.6, 0.15, 1)
        self.glow.hide()
        # drift smoke: a few grey puffs, recycled, left behind in the world
        self.smoke_root = parent.attachNewNode("kart_smoke")
        self.smoke_root.setLightOff(1)
        self.smoke_root.setShaderOff(1)
        self.smoke_root.setTransparency(TransparencyAttrib.M_alpha)
        self.smoke_root.setDepthWrite(False)
        self.smoke_root.setBin("fixed", 20)
        self.puffs = []
        for _ in range(self.PUFFS):
            p = self.smoke_root.attachNewNode(cm.generate())
            p.setTexture(dot_texture())
            p.setBillboardPointEye()
            p.hide()
            self.puffs.append([p, Vec3(0), 0.0])  # node, velocity, life left
        self.next_puff = 0
        self.puff_timer = 0.0
        self.tag = None
        self.cam = None  # (the window's camera, found when first needed: a tag under the camera is hidden)
        self.spin_angle = 0.0
        self.last_v = None
        self.pitch = 0.0
        self.roll = 0.0
        self.glow_t = 0.0

    def boxes(self, colour):
        """The kart from boxes and cylinders (every tier but ultra; on mesh and lines its faces are black and its
        edges are lines)."""
        b = self.body
        m = self.m
        z0 = 0.16  # the floor's height
        # the tub, with a raised cowl behind the nose and a rear bumper
        part(b, bevel_box(0.72, 0.34, 0.07, 0.03, tile=1.5), "paint", colour, rough=0.5, metal=0.2, pos=(0, 0, z0 + 0.07),
             materials=m)
        part(b, bevel_box(0.28, 0.2, 0.09, 0.04, tile=1.5), "paint", colour, rough=0.5, metal=0.2,
             pos=(0.42, 0, z0 + 0.2), materials=m)
        part(b, bevel_box(0.08, 0.55, 0.05, 0.02), None, (0.08, 0.08, 0.09), rough=0.8, pos=(0.8, 0, z0 + 0.06),
             materials=m)  # front bumper
        part(b, bevel_box(0.06, 0.6, 0.05, 0.02), None, (0.08, 0.08, 0.09), rough=0.8, pos=(-0.78, 0, z0 + 0.06),
             materials=m)  # rear bumper
        pods = Mesh(tile=1.5)
        for side in (1, -1):  # side pods between the wheels
            bevel_box(0.36, 0.1, 0.06, 0.025, mesh=pods, offset=Vec3(0, side * 0.44, z0 + 0.1))
        part(b, pods, "paint", colour, rough=0.5, metal=0.2, materials=m)
        # a number plate on the nose
        part(b, bevel_box(0.02, 0.14, 0.1, 0.005), None, (0.95, 0.95, 0.9), rough=0.6, pos=(0.7, 0, z0 + 0.3), materials=m)
        # seat and driver
        part(b, bevel_box(0.16, 0.19, 0.04, 0.02), None, (0.1, 0.1, 0.12), rough=0.9, pos=(-0.3, 0, z0 + 0.16), materials=m)
        part(b, bevel_box(0.04, 0.2, 0.2, 0.02), None, (0.1, 0.1, 0.12), rough=0.9, pos=(-0.46, 0, z0 + 0.36), materials=m)
        suit = tuple(min(1.0, 0.4 + 0.6 * c) for c in colour)
        part(b, bevel_box(0.13, 0.15, 0.17, 0.05), None, suit, rough=0.8, pos=(-0.28, 0, z0 + 0.36), materials=m)  # torso
        arms = Mesh()
        for side in (1, -1):  # arms reaching forward to the wheel
            cylinder(0.035, 0.2, axis="x", seg=8, mesh=arms, offset=Vec3(-0.08, side * 0.14, z0 + 0.42))
        part(b, arms, None, suit, rough=0.8, materials=m)
        helmet = ball(0.14, 14, 9)
        part(b, helmet, "paint", (0.95, 0.95, 0.95), rough=0.25, metal=0.0, pos=(-0.28, 0, z0 + 0.66), materials=m)
        part(b, bevel_box(0.03, 0.1, 0.045, 0.01), None, (0.05, 0.05, 0.08), rough=0.1, pos=(-0.16, 0, z0 + 0.67),
             materials=m)  # visor
        # the steering wheel (a flat ring: a short cylinder with a hub) and column
        part(b, cylinder(0.12, 0.012, axis="x", seg=16, bevel=0.01), None, (0.1, 0.1, 0.12), rough=0.7,
             pos=(0.1, 0, z0 + 0.45), hpr=(0, 0, -25), materials=m)
        part(b, cylinder(0.02, 0.14, axis="x", seg=8), "steel", (0.6, 0.6, 0.62), rough=0.5, metal=1.0,
             pos=(0.22, 0, z0 + 0.4), hpr=(0, 0, -25), materials=m)
        # the rear wing on two posts, and a little engine block beside the seat
        posts = Mesh()
        for side in (1, -1):
            bevel_box(0.02, 0.02, 0.12, 0.005, mesh=posts, offset=Vec3(-0.66, side * 0.3, z0 + 0.26))
        part(b, posts, "steel", (0.6, 0.6, 0.62), rough=0.5, metal=1.0, materials=m)
        part(b, bevel_box(0.1, 0.42, 0.015, 0.006, tile=1.5), "paint", colour, rough=0.5, metal=0.2,
             pos=(-0.66, 0, z0 + 0.4), hpr=(0, 0, 8), materials=m)
        part(b, bevel_box(0.12, 0.1, 0.09, 0.02), "steel", (0.35, 0.35, 0.38), rough=0.6, metal=1.0,
             pos=(-0.42, 0.28, z0 + 0.22), materials=m)
        part(b, cylinder(0.035, 0.12, axis="x", seg=8), "steel", (0.3, 0.3, 0.32), rough=0.5, metal=1.0,
             pos=(-0.7, 0.28, z0 + 0.22), materials=m)  # exhaust
        self.body.flattenStrong()
        if look():  # mesh and lines: black faces, the edges as lines
            outline(self.body)
        # the wheels: the front pair on steering pivots, each with a spin node
        self.wheels, self.steer_nodes = [], []
        tyre = cylinder(WHEEL_R, WHEEL_W, axis="y", seg=20, bevel=0.03, tile=2.5)
        hub = Mesh()
        cylinder(WHEEL_R * 0.55, WHEEL_W + 0.006, axis="y", seg=14, bevel=0.01, mesh=hub)
        for k in range(5):
            a = 2 * math.pi * k / 5
            cylinder(0.012, WHEEL_W + 0.012, axis="y", seg=6, mesh=hub,
                     offset=Vec3(math.cos(a) * WHEEL_R * 0.3, 0, math.sin(a) * WHEEL_R * 0.3))
        wheel_lines = None
        if look():  # (the wheel's edges, worked out once for every kart)
            key = f"wheel {look()}"
            if key not in _state:
                template = NodePath("wheel")
                template.attachNewNode(tyre.node())
                template.attachNewNode(hub.node())
                _state[key] = line_node("wheel lines", *edges(template, look()))
            wheel_lines = _state[key]
        for x, y in WHEELS:
            pivot = self.root.attachNewNode("pivot")
            pivot.setPos(x, y, WHEEL_R)
            spin = pivot.attachNewNode("spin")
            part(spin, tyre.node(), "tyre", (1, 1, 1), rough=1.0, metal=0.0, materials=m)  # (the one Geom, shared)
            part(spin, hub.node(), "steel", (0.75, 0.75, 0.78), rough=0.5, metal=1.0, materials=m)
            if wheel_lines is not None:
                blacken(spin)
                wire(spin, spin.attachNewNode(wheel_lines))
            self.wheels.append(spin)
            if x > 0:
                self.steer_nodes.append(pivot)

    def ultra(self, colour):
        """ultra: the smooth kart of kart_models.py. Its Geoms are made once and shared by every kart; each kart has
        its own paint."""
        model = ultra_model()
        m = self.m

        def parts(parent, geoms):
            for role, geom in geoms.items():
                node = GeomNode(role)
                node.addGeom(geom)
                c, rough, metal, name = role_look(role, colour)
                part(parent, node, name, c, rough=rough, metal=metal, materials=m)
        parts(self.body, model["body"])
        steer = model["notes"]["steering"]
        self.steering = self.body.attachNewNode("steering")  # (turns about the column through the wheel's middle)
        self.steering.setPos(*steer["pivot"])
        self.steer_axis, self.steer_ratio = Vec3(*steer["axis"]), steer["ratio"]
        held = self.steering.attachNewNode("steering wheel")
        held.setPos(-Vec3(*steer["pivot"]))
        parts(held, model["steering"])
        wheel = self.root.attachNewNode("wheel")  # (one wheel, instanced at the four corners)
        parts(wheel, model["wheel"])
        wheel.detachNode()
        self.wheels, self.steer_nodes = [], []
        for x, y in WHEELS:
            pivot = self.root.attachNewNode("pivot")
            pivot.setPos(x, y, WHEEL_R)
            spin = pivot.attachNewNode("spin")
            face = spin.attachNewNode("face")
            if y < 0:
                face.setH(180)  # (the right-hand wheels: their outer face to the right)
            wheel.instanceTo(face)
            self.wheels.append(spin)
            if x > 0:
                self.steer_nodes.append(pivot)

    def set_label(self, text, colour=(1, 1, 1, 1)):
        """A name tag floating above the kart, as RobotVisual's."""
        if self.tag is None:
            node = TextNode("tag")
            node.setAlign(TextNode.ACenter)
            node.setCardColor(0.03, 0.04, 0.06, 0.7)
            node.setCardAsMargin(0.35, 0.35, 0.18, 0.12)
            self.tag = self.root.attachNewNode(node)
            self.tag.setPos(0, 0, 1.35)
            self.tag.setBillboardPointEye()
            self.tag.setScale(0.17)
            self.tag.setLightOff(1)
            self.tag.setShaderOff(1)
            self.tag.setFogOff(1)  # (the haze on ultra and the dark on mesh and lines never dim a name)
            self.tag.setDepthTest(False)
            self.tag.setDepthWrite(False)
            self.tag.setBin("fixed", 60)
        self.tag.node().setText(text)
        self.tag.node().setTextColor(*colour)

    def update(self, x, y, z, yaw_deg, steer, v, u, drifting, boosting, dt):
        """Place the kart; its body pitches with acceleration and rolls with the slide, the front wheels turn
        with steer, all four spin with v; the glow shows while boosting and smoke puffs while drifting."""
        self.root.setPos(x, y, z)
        self.root.setH(yaw_deg)
        dt = max(1e-4, dt)
        # pitch: nose up under acceleration, down under braking (smoothed: the sim's v is quantised each tick)
        accel = 0.0 if self.last_v is None else (v - self.last_v) / dt
        self.last_v = v
        want_pitch = max(-5.0, min(5.0, -accel * 0.45))
        want_roll = max(-7.0, min(7.0, -u * 2.2))  # (a left turn slides the back out right, u < 0: lean right)
        a = min(1.0, dt * 8.0)
        self.pitch += (want_pitch - self.pitch) * a
        self.roll += (want_roll - self.roll) * a
        self.body.setHpr(0, self.roll, self.pitch)  # (nose along +x: a lean is Panda's P, a nose dip its R)
        angle = max(-1.0, min(1.0, steer)) * MAX_STEER
        for pivot in self.steer_nodes:
            pivot.setH(angle)
        if self.steering is not None:
            self.steering.setQuat(LRotationf(self.steer_axis, angle * self.steer_ratio))
            self.skids(x, y, z, yaw_deg, drifting and abs(v) > 3.0)
        self.spin_angle = (self.spin_angle + math.degrees(v / WHEEL_R) * dt) % 360.0
        for spin in self.wheels:
            spin.setR(self.spin_angle)
        if self.tag is not None:
            if self.cam is None:
                import builtins
                self.cam = getattr(builtins, "base", None) and builtins.base.camera
            if self.cam is not None:
                near = (self.cam.getPos(self.parent) - self.root.getPos()).length() < 4.0
                if near != self.tag.isHidden():
                    self.tag.hide() if near else self.tag.show()
        if boosting and not look():
            self.glow_t += dt
            self.glow.show()
            self.glow.setScale(0.9 + 0.25 * math.sin(self.glow_t * 31))
        elif not self.glow.isHidden():
            self.glow.hide()
        # drift smoke from the rear tyres
        if drifting and abs(v) > 3.0 and not look():
            self.puff_timer -= dt
            if self.puff_timer <= 0:
                self.puff_timer = 0.07
                p = self.puffs[self.next_puff]
                side = 0.6 if self.next_puff % 2 else -0.6  # (each rear tyre in turn)
                self.next_puff = (self.next_puff + 1) % self.PUFFS
                p[0].setPos(self.root, -0.55, side, 0.15)
                p[0].setScale(0.35)
                p[0].setColor(0.75, 0.75, 0.78, 0.55)
                p[0].show()
                p[1] = Vec3(0, 0, 0.6)
                p[2] = 0.7
        for p in self.puffs:
            if p[2] <= 0:
                continue
            p[2] -= dt
            node = p[0]
            if p[2] <= 0:
                node.hide()
                continue
            node.setPos(node.getPos() + p[1] * dt)
            f = p[2] / 0.7
            node.setScale(0.35 + (1 - f) * 0.9)
            node.setColor(0.75, 0.75, 0.78, 0.55 * f)

    def skids(self, x, y, z, yaw_deg, on):
        """ultra: while drifting, each rear tyre leaves a mark on the road (a piece every 35 cm)."""
        marks = skid_marks()
        if marks is None or not on:
            self.skid_last = [None, None]
            return
        c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
        for k, (wx, wy) in enumerate(WHEELS[2:]):
            p = Vec3(x + wx * c - wy * s, y + wx * s + wy * c, z + 0.012)
            last = self.skid_last[k]
            if last is None or (p - last).length() > 3.0:  # (a new drift, or the kart put back on the grid)
                self.skid_last[k] = p
            elif (p - last).length() > 0.35:
                marks.add(last, p, 0.15)
                self.skid_last[k] = p

    def destroy(self):
        self.smoke_root.removeNode()
        self.root.removeNode()


# ---------- cameras ----------
class ChaseCamera:
    """Three views, cycled with cycle():
        chase - behind and above the kart, lagging its yaw a little so turns read, further back at speed
        hood  - from the nose, looking down the road
        tv    - fixed trackside cameras (six round the circuit), the nearest one watching the kart
    update() every frame with the kart's (interpolated) position; the camera's own smoothing is a steady
    exponential approach, so it never jitters when the position is smooth."""
    MODES = ("chase", "hood", "tv")
    NAMES = {"chase": "Chase", "hood": "Hood", "tv": "TV"}

    def __init__(self, base, mode="chase"):
        self.base = base
        self.mode = mode if mode in self.MODES else "chase"
        self.cam_yaw = None
        self.pos = self.look = None
        self.fov = 70.0
        self.zoom = 1.0  # the mouse wheel: under 1 is closer (a narrower view), over 1 wider
        self.tv_points = None
        self.tv_track = None
        self.tv_index = 0

    @property
    def name(self):
        return self.NAMES[self.mode]

    def cycle(self):
        self.set_mode(self.MODES[(self.MODES.index(self.mode) + 1) % len(self.MODES)])

    def wheel(self, factor):
        """The mouse wheel (the HUD kit's: when it isn't sliding a side panel): zoom the view a little."""
        self.zoom = max(0.6, min(1.5, self.zoom * (factor ** 0.5)))

    def settings(self):
        """What a learner's profile keeps of the camera."""
        return {"mode": self.mode, "zoom": round(self.zoom, 2)}

    def restore(self, saved):
        if isinstance(saved, dict):
            self.set_mode(saved.get("mode", self.mode))
            try:
                self.zoom = max(0.6, min(1.5, float(saved.get("zoom", 1.0))))
            except (TypeError, ValueError):
                pass

    def set_mode(self, mode):
        if mode in self.MODES:
            self.mode = mode
            self.pos = None  # (cut straight to the new view)

    def tv_cameras(self, track):
        """Six camera stands round the track, on the outside of each bend, 5 m up."""
        if self.tv_track is track:
            return self.tv_points
        pts = [Vec3(x, y, z) for x, y, z, side, s in kart_scenery.tv_cameras(track)]  # (the scenery keeps clear of them)
        self.tv_points, self.tv_track = pts, track
        return pts

    def update(self, dt, x, y, z, yaw_deg, v, track):
        target = Vec3(x, y, z)
        yr = math.radians(yaw_deg)
        fwd = Vec3(math.cos(yr), math.sin(yr), 0)
        near = 0.2
        if self.mode == "chase":
            if self.cam_yaw is None:
                self.cam_yaw = yaw_deg
            diff = (yaw_deg - self.cam_yaw + 180.0) % 360.0 - 180.0
            self.cam_yaw += diff * min(1.0, dt * 4.5)  # lagging the kart's yaw: the kart turns in the frame
            cr = math.radians(self.cam_yaw)
            back = Vec3(math.cos(cr), math.sin(cr), 0)
            speed = max(0.0, v)
            dist, height = 5.2 + 0.07 * speed, 2.0 + 0.025 * speed
            want = target - back * dist + Vec3(0, 0, height)
            look = target + fwd * 5.0 + Vec3(0, 0, 0.6)
            fov, k = 72.0 + 0.25 * speed, 14.0
        elif self.mode == "hood":
            want = target + fwd * 0.95 + Vec3(0, 0, 0.62)  # (just over the nose plate)
            look = target + fwd * 25.0 + Vec3(0, 0, 0.3)
            fov, k, near = 82.0, 60.0, 0.08
        else:
            pts = self.tv_cameras(track)
            d = [(p - target).length() for p in pts]
            best = min(range(len(pts)), key=lambda i: d[i])
            if d[best] < d[self.tv_index] * 0.85 or self.pos is None:  # (a little hysteresis: no flicking about)
                self.tv_index = best
            want = pts[self.tv_index]
            look = target + Vec3(0, 0, 0.4)
            dist = (want - look).length()
            fov = max(14.0, min(70.0, math.degrees(2 * math.atan(7.0 / max(1.0, dist)))))
            k = 60.0
        if self.pos is None:
            self.pos, self.look, self.fov = Vec3(want), Vec3(look), fov
        a = min(1.0, dt * k)
        self.pos += (want - self.pos) * a
        self.look += (look - self.look) * a
        self.fov += (fov - self.fov) * min(1.0, dt * 4)
        cam = self.base.camera
        cam.setPos(self.pos)
        cam.lookAt(self.look)
        self.base.camLens.setFov(max(20.0, min(110.0, self.fov * self.zoom)))
        self.base.camLens.setNear(near)
        follow_sun(x, y, z)


# ---------- the screen ----------
WHITE, GREY, YELLOW, RED = (1, 1, 1, 1), (0.75, 0.8, 0.9, 1), (1, 0.85, 0.2, 1), (1, 0.3, 0.25, 1)
BLUE, ORANGE = (0.45, 0.75, 1, 1), (1, 0.6, 0.2, 1)
MINI_TURBO, SUPER_TURBO = 270, 570


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


class _Text:
    """An OnscreenText that only takes a setText when the text changes."""

    def __init__(self, parent, x, y, scale, fg=WHITE, align=TextNode.ACenter, shadow=(0, 0, 0, 0.9)):
        self.np = OnscreenText("", pos=(x, y), scale=scale, fg=fg, align=align, parent=parent, mayChange=True,
                               shadow=shadow)
        self.text = ""
        self.fg = fg

    def set(self, text, fg=None):
        if text != self.text:
            self.text = text
            self.np.setText(text)
        if fg is not None and fg != self.fg:
            self.fg = fg
            self.np.setFg(fg)

    def alpha(self, a):
        """Fade without regenerating the text (a colour scale on the node, not a new text colour)."""
        self.np.setAlphaScale(max(0.0, min(1.0, a)))

    def pos(self, x, y):
        self.np.setPos(x, y)


class Hud:
    """The racing screen on aspect2d. update() once a frame; only what changed is redrawn."""
    BAR_W, BAR_H = 0.5, 0.04
    MINI = 0.46  # the minimap's box (half-size 0.23)

    def __init__(self, base, track=None):
        self.base = base
        self.root = base.aspect2d.attachNewNode("kart hud")
        self.aspect = None
        self.inset = 0.0  # how far in from the right edge the right-hand readouts sit (a side panel is open)
        r = self.root
        self.lap = _Text(r, 0, 0, 0.075, WHITE, TextNode.ALeft)
        self.place = _Text(r, 0, 0, 0.075, WHITE, TextNode.ARight)
        self.speed = _Text(r, 0, 0, 0.085, WHITE, TextNode.ARight)
        self.count = _Text(r, 0, 0.3, 0.3, YELLOW)
        self.count.np.setTransparency(TransparencyAttrib.M_alpha)
        self.count_t = None            # the countdown seen last frame
        self.go_until = 0.0            # GO! shows until then
        self.wrong = _Text(r, 0, 0.62, 0.11, RED)
        self.wrong.set("WRONG WAY")
        self.wrong.np.hide()
        self.wrong_shown = False
        self.status_text = _Text(r, 0, 0, 0.028, GREY, TextNode.ARight)
        # the boost meter: a dark bar, a fill, and marks at the mini and super turbos
        self.bar_back = DirectFrame(parent=r, frameColor=(0.05, 0.05, 0.07, 0.85),
                                    frameSize=(-0.008, self.BAR_W + 0.008, -0.008, self.BAR_H + 0.008))
        self.bar_fill = DirectFrame(parent=self.bar_back, frameColor=BLUE, frameSize=(0, 0.001, 0, self.BAR_H))
        for mark in (MINI_TURBO, SUPER_TURBO):
            DirectFrame(parent=self.bar_back, frameColor=(1, 1, 1, 0.9),
                        frameSize=(-0.003, 0.003, -0.012, self.BAR_H + 0.012),
                        pos=(self.BAR_W * min(1.0, mark / SUPER_TURBO), 0, 0))
        self.bar_label = _Text(self.bar_back, 0, self.BAR_H + 0.03, 0.035, GREY, TextNode.ALeft)
        self.bar_label.set("DRIFT")
        self.charge_shown = -1
        # the minimap: built once from the track's points (see minimap()); dots per kart
        self.mini = r.attachNewNode("minimap")
        self.mini_track = None
        self.mini_scale, self.mini_centre = 1.0, (0.0, 0.0)
        self.dots = []
        # results
        self.results_back = DirectFrame(parent=r, frameColor=(0.03, 0.035, 0.06, 0.88), frameSize=(-0.6, 0.6, -0.5, 0.5))
        self.results_title = _Text(self.results_back, 0, 0.36, 0.08, YELLOW)
        self.results_title.set("RESULTS")
        self.results_text = _Text(self.results_back, -0.5, 0.22, 0.055, WHITE, TextNode.ALeft)
        self.results_times = _Text(self.results_back, 0.5, 0.22, 0.055, WHITE, TextNode.ARight)
        self.results_shown = None
        self.results_back.hide()
        self.layout()
        if track is not None:
            self.minimap(track)

    def set_inset(self, inset):
        """A side panel is open on the right (inset: how wide, in screen units): the right-hand readouts move in."""
        if inset != self.inset:
            self.inset, self.aspect = inset, None

    def layout(self):
        """Pin everything to the corners for the window's shape (checked each frame: it changes on a resize)."""
        a = self.base.getAspectRatio()
        if a == self.aspect:
            return
        self.aspect = a
        right = a - self.inset
        self.lap.pos(-a + 0.05, 0.9)
        self.place.pos(right - 0.05, 0.9)
        self.speed.pos(right - 0.05, -0.9)
        self.status_text.pos(a - 0.05, -0.975)
        self.bar_back.setPos(right - 0.05 - self.BAR_W, 0, -0.82)
        self.mini.setPos(-a + 0.05 + self.MINI / 2, 0, -0.95 + self.MINI / 2)

    def minimap(self, track):
        """Draw the track's outline once: a 2D line loop scaled into the corner box."""
        self.mini_track = track
        dots = {d for d, _ in self.dots}
        for c in self.mini.getChildren():
            if c not in dots:
                c.removeNode()
        x0, y0, x1, y1 = track.bounds()
        span = max(x1 - x0, y1 - y0)
        self.mini_scale = self.MINI * 0.9 / span
        self.mini_centre = ((x0 + x1) / 2, (y0 + y1) / 2)
        back = CardMaker("mini back")
        back.setFrame(-self.MINI / 2, self.MINI / 2, -self.MINI / 2, self.MINI / 2)
        b = self.mini.attachNewNode(back.generate())
        b.setColor(0.03, 0.035, 0.06, 0.6)
        b.setTransparency(TransparencyAttrib.M_alpha)
        for width, colour in ((9.0, (0.1, 0.1, 0.12, 1)), (5.0, (0.8, 0.82, 0.86, 1))):  # a dark edge, a light road
            seg = LineSegs("track")
            seg.setThickness(width)
            seg.setColor(*colour)
            pts = [self.mini_xy(p[0], p[1]) for p in track.pts]
            seg.moveTo(pts[0][0], 0, pts[0][1])
            for mx, my in pts[1:] + pts[:1]:
                seg.drawTo(mx, 0, my)
            self.mini.attachNewNode(seg.create())
        sx, sy = self.mini_xy(*track.point(0.0, 0.0)[:2])
        line = LineSegs("start")
        line.setThickness(3.0)
        line.setColor(1, 1, 1, 1)
        h = math.radians(track.heading(0.0) + 90)
        line.moveTo(sx + math.cos(h) * 0.02, 0, sy + math.sin(h) * 0.02)
        line.drawTo(sx - math.cos(h) * 0.02, 0, sy - math.sin(h) * 0.02)
        self.mini.attachNewNode(line.create())
        for d, _ in self.dots:
            d.reparentTo(self.mini)  # (2D draws in scene graph order: the dots go back to the end, on top)

    def mini_xy(self, x, y):
        cx, cy = self.mini_centre
        return (x - cx) * self.mini_scale, (y - cy) * self.mini_scale

    def dot(self, i):
        while len(self.dots) <= i:
            cm = CardMaker("dot")
            cm.setFrame(-0.012, 0.012, -0.012, 0.012)
            d = self.mini.attachNewNode(cm.generate())
            self.dots.append([d, None])
        return self.dots[i]

    def status(self, text):
        """Small grey text at the bottom (fps, ping)."""
        self.status_text.set(text)

    def update(self, lap, laps, place, count, kmh, countdown, wrong_way, charge, karts, results):
        """lap/laps: the lap being driven (1-based) and how many; place/count: your place and the field; kmh: speed;
        countdown: seconds to GO or None; wrong_way: flag; charge: the drift charge (0..570+);
        karts: for the minimap, (x, y, colour) tuples or (x, y, colour, big) with big for your own kart; results: None,
        or (name, laps, seconds or None) in finishing order as kart_sim.Race.results() gives."""
        self.layout()
        now = time.perf_counter()
        self.lap.set(f"LAP {max(1, min(lap, laps))}/{laps}" if laps else "")
        self.place.set(f"{_ordinal(place)} of {count}" if place else "")
        self.speed.set(f"{int(round(kmh))} km/h")
        # the countdown: 3, 2, 1 each fading out, then GO! for a second
        if countdown is not None:
            n = int(math.ceil(countdown - 1e-6))
            frac = countdown - math.floor(countdown)
            if 1 <= n <= 3:
                self.count.set(str(n), YELLOW)
                self.count.alpha(frac + 0.15)
                self.count.np.setScale(0.3 + 0.12 * (1 - frac))
            else:
                self.count.set("")
            self.count_t = countdown
        elif self.count_t is not None:  # the countdown has just ended: GO!
            self.count_t = None
            self.go_until = now + 1.0
        if countdown is None and now < self.go_until:
            self.count.set("GO!", (0.4, 1.0, 0.45, 1))
            self.count.alpha((self.go_until - now) * 2)
            self.count.np.setScale(0.32)
        elif countdown is None and self.count.text:
            self.count.set("")
        # the wrong way warning flashes
        show = bool(wrong_way) and int(now * 4) % 2 == 0
        if show != self.wrong_shown:
            self.wrong_shown = show
            self.wrong.np.show() if show else self.wrong.np.hide()
        # the boost meter
        c = int(max(0, charge))
        if c != self.charge_shown:
            self.charge_shown = c
            w = self.BAR_W * min(1.0, c / SUPER_TURBO)
            self.bar_fill["frameSize"] = (0, max(0.001, w), 0, self.BAR_H)
            if c >= SUPER_TURBO:
                colour = (1, 0.95, 0.6, 1) if int(now * 10) % 2 else ORANGE
            else:
                colour = ORANGE if c >= MINI_TURBO else BLUE
            self.bar_fill["frameColor"] = colour
            self.bar_label.set("SUPER TURBO" if c >= SUPER_TURBO else "MINI TURBO" if c >= MINI_TURBO else "DRIFT")
        # the minimap's dots (none until minimap(track) has drawn the outline)
        karts = list(karts or ()) if self.mini_track is not None else []
        for i, k in enumerate(karts):
            d, shown = self.dot(i)
            if isinstance(k, dict):
                x, y, colour, big = k["x"], k["y"], k.get("colour", (1, 1, 1)), k.get("big", False)
            else:
                x, y, colour = k[0], k[1], k[2]
                big = k[3] if len(k) > 3 else False
            mx, my = self.mini_xy(x, y)
            d.setPos(mx, 0, my)
            key = (tuple(colour), big)
            if key != shown:
                self.dots[i][1] = key
                col = tuple(v / 255 if v > 1 else v for v in colour[:3])
                d.setColor(*col, 1)
                d.setScale(1.5 if big else 1.0)
            if d.isHidden():
                d.show()
        for d, _ in self.dots[len(karts):]:
            if not d.isHidden():
                d.hide()
        # results
        if results:
            key = tuple((n, l, None if t is None else round(t, 1)) for n, l, t in results)
            if key != self.results_shown:
                self.results_shown = key
                names, times = [], []
                for i, (name, laps_done, t) in enumerate(results):
                    names.append(f"{_ordinal(i + 1)}  {name}")
                    times.append(f"{int(t // 60)}:{t % 60:04.1f}" if t is not None else f"lap {laps_done + 1}")
                self.results_text.set("\n".join(names))
                self.results_times.set("\n".join(times))
                self.results_back.show()
        elif self.results_shown is not None:
            self.results_shown = None
            self.results_back.hide()

    def show(self, on=True):
        self.root.show() if on else self.root.hide()

    def destroy(self):
        self.root.removeNode()
