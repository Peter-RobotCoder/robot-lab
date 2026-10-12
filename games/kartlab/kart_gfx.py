"""Kart Lab graphics: an outdoor circuit in the sun, karts built from boxes and cylinders, a chase camera and the
racing screen (lap, place, speed, countdown, boost meter, minimap, results).

Call init(base, tier) once, then build a TrackVisual for the track and a KartVisual for every kart. The same
classes work in the offline preview (kart_preview.py) and in the class window (kart_client.py). The track and
the kart's state are kart_track.Track and kart_sim's dict: x, y, yaw in degrees (0 = +x, anticlockwise), v
forward and u sideways in m/s. Karts are built with their nose along +x so the kart's yaw is the node's H.

tier: a graphics tier from engine.gfx_tiers ("basic", "low", "medium", "high"); the lights and materials follow
the tier the driver could run, as rw_gfx does. Everything static is flattened per material so the whole circuit
is a dozen draw calls, and the HUD only sets text that has changed (per-frame setText is the classic Python-side
frame killer: reports/Kart engine netcode and graphics tiers.md).
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
from panda3d.core import (AmbientLight, AntialiasAttrib, CardMaker, ColorBlendAttrib, DirectionalLight,  # noqa: E402
                          Filename, LineSegs, Material, PNMImage, SamplerState, TextNode, Texture, TextureStage,
                          TransparencyAttrib, Vec3)

from engine import gfx_tiers, rw_textures  # noqa: E402
from engine.rw_mesh import Mesh, bevel_box, cylinder  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "assets", "tex")
TEX_VERSION = "1"  # bump to regenerate the circuit's textures after changing a generator

_state = {}

# ---------- colours ----------
SKY = (0.3, 0.5, 0.9)  # (tonemapped with the scene, so a little deeper than it ends up)
SUN_OFFSET = Vec3(30, -45, 45)  # from a kart to the sun: 40 degrees up, so a kart's shadow falls clear of it
KERB_RED, KERB_WHITE = (0.85, 0.12, 0.08, 1), (0.95, 0.95, 0.92, 1)
TARMAC_TINT = (0.9, 0.9, 0.92)
GRASS_TINT = (0.95, 1.0, 0.9)


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

    def save_set(name, albedo, height, strength, rough, metal):
        save(f"{name}_albedo.png", albedo)
        save(f"{name}_normal.png", rw_textures.normal_from_height(height, strength))
        save(f"{name}_mr.png", np.dstack([np.ones_like(rough), rough, metal]))

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
    for f in os.listdir(TEX):
        if f.startswith("version_"):
            os.remove(os.path.join(TEX, f))
    open(marker, "w").close()


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
def init(base, tier="medium"):
    """A sunny day: sky-coloured background, a sun with shadows per tier, a soft blue fill, the sky as the
    reflection map on the tiers that have one. Returns the simplepbr pipeline, or None on "basic"."""
    quality = tier if tier in gfx_tiers.TIERS else gfx_tiers.DEFAULT
    s = gfx_tiers.SETTINGS[quality]
    _state["mats"] = Materials(base.loader, quality)
    base.setBackgroundColor(*SKY, 1.0)  # (alpha 1: simplepbr clears its scene buffer to this, and a screenshot
    # of a buffer cleared to alpha 0 has a see-through sky)
    render = base.render
    sun = DirectionalLight("sun")
    sun.setColor((2.6, 2.45, 2.2, 1))
    if s["shadow"]:
        # the shadow frustum covers 40 m round the player's kart and only 40 m of depth: ChaseCamera.update
        # moves it along. simplepbr's shadow bias is a share of the depth range, so a frustum over the whole
        # circuit would swallow a kart's shadow (a kart is 1 m tall) and blur it to 15 cm texels
        sun.setShadowCaster(True, s["shadow"], s["shadow"])
        sun.getLens().setFilmSize(40, 40)
        far = SUN_OFFSET.length()
        sun.getLens().setNearFar(far - 20, far + 20)
    sun_np = render.attachNewNode(sun)
    sun_np.setPos(SUN_OFFSET)
    sun_np.lookAt(0, 0, 0)
    render.setLight(sun_np)
    amb = AmbientLight("sky fill")
    amb.setColor((0.22, 0.25, 0.32, 1))
    render.setLight(render.attachNewNode(amb))

    def env_map(simplepbr):
        try:
            cube = base.loader.loadCubeMap(Filename.fromOsSpecific(os.path.join(TEX, "sky_#.png")))
            return simplepbr.EnvMap(cube, prefiltered_size=32, prefiltered_samples=8, blocking_prepare=True)
        except Exception:
            return None
    pipeline, used = gfx_tiers.init_pipeline(base, quality, env_map, exposure=0.55)
    if pipeline is not None:
        pipeline.shadow_bias = 0.0015  # (6 cm over the 40 m depth range: a kart's body shadows, flat ground doesn't speckle)
    if used != quality:  # the driver couldn't run the tier asked for: the lights and materials follow the one used
        print(f"gfx: {quality} graphics don't run here, using {used}", flush=True)
        _state["mats"].quality = used
        if not gfx_tiers.SETTINGS[used]["shadow"]:
            sun.setShadowCaster(False)
    if not gfx_tiers.SETTINGS[used]["simplepbr"]:
        _state["tone"] = gfx_tiers.basic_look(base, exposure=0.55)  # (Panda's shaders: the lights come down, the tone curve is a post pass)
    if s["msaa"]:
        render.setAntialias(AntialiasAttrib.MMultisample)
    _state.update(quality=used, pipeline=pipeline, sun=sun_np)
    return pipeline


def tier():
    """The graphics tier in use (the one init was given, or the lower one the driver could run)."""
    return _state.get("quality", gfx_tiers.DEFAULT)


def follow_sun(x, y, z):
    """Keep the sun's shadow frustum over the player's kart (called by ChaseCamera.update)."""
    sun = _state.get("sun")
    if sun is not None:
        sun.setPos(Vec3(x, y, z) + SUN_OFFSET)


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
    line, dash pads, oil, grass and a little trackside scenery. Static, and flattened per material."""
    GRASS_MARGIN = 45.0
    GRASS_CELL = 3.0

    def __init__(self, parent, track):
        self.track = track
        half = track.half
        self.root = parent.attachNewNode("track_visual")
        static = self.root.attachNewNode("static")
        rnd = random.Random(11)
        L = track.length

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
        self.pads_mat = self.pads.getMaterial()
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

        # the grass: a grid over the track's bounds with a margin, each vertex at the height of the nearest bit of
        # track (a little under the road), easing to a base level away from it, so the ground follows the hill
        self.grass(static, rnd)
        self.scenery(static, rnd)
        static.flattenStrong()  # one draw call per material: fast on low-spec laptops

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
        sign = TextNode("start")
        sign.setText("START")
        sign.setAlign(TextNode.ACenter)
        for face in (1, -1):  # readable from both sides
            snp = parent.attachNewNode(sign)
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
        self.pads_mat.setEmission((glow, glow * 0.55, glow * 0.07, 1))

    def destroy(self):
        self.root.removeNode()


# ---------- karts ----------
WHEEL_R, WHEEL_W = 0.2, 0.09
WHEELS = [(0.5, 0.6), (0.5, -0.6), (-0.52, 0.62), (-0.52, -0.62)]  # (x, y): front left, front right, rear left, rear right
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
        # the wheels: the front pair on steering pivots, each with a spin node
        self.wheels, self.steer_nodes = [], []
        tyre = cylinder(WHEEL_R, WHEEL_W, axis="y", seg=20, bevel=0.03, tile=2.5)
        hub = Mesh()
        cylinder(WHEEL_R * 0.55, WHEEL_W + 0.006, axis="y", seg=14, bevel=0.01, mesh=hub)
        for k in range(5):
            a = 2 * math.pi * k / 5
            cylinder(0.012, WHEEL_W + 0.012, axis="y", seg=6, mesh=hub,
                     offset=Vec3(math.cos(a) * WHEEL_R * 0.3, 0, math.sin(a) * WHEEL_R * 0.3))
        for x, y in WHEELS:
            pivot = self.root.attachNewNode("pivot")
            pivot.setPos(x, y, WHEEL_R)
            spin = pivot.attachNewNode("spin")
            part(spin, tyre.node(), "tyre", (1, 1, 1), rough=1.0, metal=0.0, materials=m)  # (the one Geom, shared)
            part(spin, hub.node(), "steel", (0.75, 0.75, 0.78), rough=0.5, metal=1.0, materials=m)
            self.wheels.append(spin)
            if x > 0:
                self.steer_nodes.append(pivot)
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
        if boosting:
            self.glow_t += dt
            self.glow.show()
            self.glow.setScale(0.9 + 0.25 * math.sin(self.glow_t * 31))
        elif not self.glow.isHidden():
            self.glow.hide()
        # drift smoke from the rear tyres
        if drifting and abs(v) > 3.0:
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
        self.tv_points = None
        self.tv_track = None
        self.tv_index = 0

    @property
    def name(self):
        return self.NAMES[self.mode]

    def cycle(self):
        self.set_mode(self.MODES[(self.MODES.index(self.mode) + 1) % len(self.MODES)])

    def set_mode(self, mode):
        if mode in self.MODES:
            self.mode = mode
            self.pos = None  # (cut straight to the new view)

    def tv_cameras(self, track):
        """Six camera stands round the track, on the outside of each bend, 5 m up."""
        if self.tv_track is track:
            return self.tv_points
        pts = []
        for k in range(6):
            s = (k + 0.5) * track.length / 6
            bend = track.curvature(s, 30)
            side = -1 if bend > 0 else 1  # (a left bend: the camera on the right, looking across the apex)
            x, y, z = track.point(s, side * (track.half + 6.0))
            pts.append(Vec3(x, y, z + 5.0))
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
        self.base.camLens.setFov(self.fov)
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
        self.status_text = _Text(r, 0, 0, 0.032, GREY)
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

    def layout(self):
        """Pin everything to the corners for the window's shape (checked each frame: it changes on a resize)."""
        a = self.base.getAspectRatio()
        if a == self.aspect:
            return
        self.aspect = a
        self.lap.pos(-a + 0.05, 0.9)
        self.place.pos(a - 0.05, 0.9)
        self.speed.pos(a - 0.05, -0.93)
        self.status_text.pos(0, -0.97)
        self.bar_back.setPos(a - 0.05 - self.BAR_W, 0, -0.84)
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
