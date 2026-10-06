"""Fight Lab graphics: PBR materials, lights, the fight hall with its rings, and the fighters.

Call init(base, quality) once, then build a StageVisual and a FighterVisual for each fighter.
quality: "low" (no shadows or surface detail: old laptops), "medium", "high".

The fighters are built from simple shapes (boxes and cylinders) joined like a skeleton:
    root (feet, heading) > hips > waist (chest) > neck (head)
                                  waist > shoulders > upper arms > forearms > fists
                           hips > thighs > shins > feet
A pose is a dictionary of joint angles (heading, pitch, roll in degrees). Each animation picks a pose for
its progress k, and the fighter slides smoothly from the pose it is in to that one.
Pitch swings a limb forwards (a hanging arm at pitch 90 points straight ahead); a knee bends with a
negative pitch. Everything faces +y, like the rest of Panda3D.
"""
import math
import os
import random

from panda3d.core import (AmbientLight, AntialiasAttrib, BitMask32, CardMaker, ColorBlendAttrib, DirectionalLight, Filename,
                          Material, PerspectiveLens, Point3, SamplerState, Spotlight, TextNode, Texture,
                          TextureStage, Vec3)

import fight_sim as sim
import rw_textures
from rw_mesh import Mesh, bevel_box, cylinder

_state = {}
SHADOW_MASK = BitMask32.bit(5)  # what the key light's shadow camera draws (the hall and crowd are left out: faster)


# ---------- materials ----------
class Materials:
    def __init__(self, loader, quality):
        rw_textures.ensure()
        self.loader, self.quality = loader, quality
        self.cache = {}
        self.materials = {}
        self.ts_normal = TextureStage("normal")
        self.ts_normal.setMode(TextureStage.M_normal)
        self.ts_mr = TextureStage("metal_rough")
        self.ts_mr.setMode(TextureStage.M_selector)

    def tex(self, name, kind):
        key = (name, kind)
        if key not in self.cache:
            t = self.loader.loadTexture(Filename.fromOsSpecific(os.path.join(rw_textures.TEX, f"{name}_{kind}.png")))
            if kind == "albedo":
                t.setFormat(Texture.F_srgb)
            t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
            t.setMagfilter(SamplerState.FT_linear)
            t.setAnisotropicDegree(8 if self.quality != "low" else 2)
            t.setWrapU(SamplerState.WM_repeat)
            t.setWrapV(SamplerState.WM_repeat)
            self.cache[key] = t
        return self.cache[key]

    def apply(self, np_, name=None, colour=(1, 1, 1), rough=1.0, metal=1.0, emission=None):
        """Give a part a PBR look: a texture set (paint, steel, concrete...) tinted by colour."""
        key = (tuple(colour), rough, metal, tuple(emission) if emission else None)
        m = self.materials.get(key) if not emission else None  # (glowing ones are changed while running)
        if m is None:
            m = Material()
            m.setBaseColor((*(c ** 2.2 for c in colour), 1))  # screen colours (sRGB) to the linear colours lighting uses
            m.setRoughness(rough)
            m.setMetallic(metal)
            if emission:
                m.setEmission((*emission, 1))
            else:
                self.materials[key] = m  # the same material is shared, so parts can be drawn together
        np_.setMaterial(m, 1)
        if name:
            np_.setTexture(TextureStage.getDefault(), self.tex(name, "albedo"), 1)
            np_.setTexture(self.ts_mr, self.tex(name, "mr"), 1)
            np_.setTexture(self.ts_normal, self.tex(name, "normal"), 1)
        return np_


def mats():
    return _state["mats"]


def part(parent, mesh, name=None, colour=(1, 1, 1), rough=1.0, metal=1.0, emission=None, pos=(0, 0, 0), hpr=(0, 0, 0)):
    np_ = parent.attachNewNode(mesh.node() if isinstance(mesh, Mesh) else mesh)
    np_.setPos(*pos)
    np_.setHpr(*hpr)
    mats().apply(np_, name, colour, rough, metal, emission)
    return np_


def glow_node(np_, colour):
    """A bright part that ignores the lights (fire, energy, sparks): added on top of the scene."""
    np_.setLightOff(1)
    np_.setShaderOff(1)
    np_.setColor(*colour, 1)
    np_.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
    np_.setDepthWrite(False)
    np_.setBin("fixed", 22)
    return np_


def soft_dot(size=64):
    """A soft round spot (for fire puffs)."""
    from panda3d.core import PNMImage
    img = PNMImage(size, size, 4)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            img.setXelA(x, y, 1, 1, 1, max(0.0, 1 - math.hypot(x - c, y - c) / c) ** 1.8)
    t = Texture("dot")
    t.load(img)
    return t


def sphere(r, mesh=None, offset=Vec3(0), scale=Vec3(1, 1, 1), seg=16, rings=10, tile=1.0):
    """A smooth sphere (or egg shape, with scale): heads, fists, joints."""
    m = mesh or Mesh(tile)
    o = Vec3(offset)
    angles = [2 * math.pi * i / seg for i in range(seg + 1)]
    for j in range(rings):
        rows = []
        for lat in (j, j + 1):
            t = math.pi * lat / rings
            z, rr = math.cos(t), math.sin(t)
            pts = [o + Vec3(math.cos(a) * rr * r * scale.x, math.sin(a) * rr * r * scale.y, z * r * scale.z)
                   for a in angles]
            nrm = []
            for a in angles:
                n = Vec3(math.cos(a) * rr / scale.x, math.sin(a) * rr / scale.y, z / scale.z)
                n.normalize()
                nrm.append(n)
            rows.append((pts, nrm, t))
        tang = [Vec3(-math.sin(a), math.cos(a), 0) for a in angles]
        u = [a * r for a in angles]
        (p0, n0, t0), (p1, n1, t1) = rows
        m.smooth_strip(p1, p0, n1, n0, tang, u, t1 * r, t0 * r)  # (bottom row first: faces point out)
    return m


def capsule(r, length, mesh=None, offset=Vec3(0), down=True, seg=14):
    """A limb: a rounded cylinder hanging down (or standing up) from offset."""
    m = mesh or Mesh()
    o = Vec3(offset)
    mid = o + Vec3(0, 0, -length / 2 if down else length / 2)
    cylinder(r, length / 2, seg=seg, mesh=m, offset=mid, caps=False)
    sphere(r, mesh=m, offset=mid + Vec3(0, 0, length / 2), seg=seg, rings=6)
    sphere(r, mesh=m, offset=mid - Vec3(0, 0, length / 2), seg=seg, rings=6)
    return m


# ---------- lighting ----------
def init(base, quality="high"):
    """Lights, reflections and the PBR pipeline. Returns the simplepbr pipeline."""
    import simplepbr
    _state["mats"] = Materials(base.loader, quality)
    _state["render"] = base.render
    base.setBackgroundColor(0.01, 0.01, 0.02)
    render = base.render
    sun = DirectionalLight("key")
    sun.setColor((1.1, 1.05, 1.0, 1))
    if quality != "low":
        size = 4096 if quality == "high" else 2048
        sun.setShadowCaster(True, size, size)
        sun.setCameraMask(SHADOW_MASK)
        sun.getLens().setFilmSize(16, 16)
        sun.getLens().setNearFar(5, 60)
    sun_np = render.attachNewNode(sun)
    sun_np.setPos(6, -12, 26)
    sun_np.lookAt(0, 0, 0)
    render.setLight(sun_np)
    _state["sun"] = sun_np
    amb = AmbientLight("fill")
    amb.setColor((0.07, 0.07, 0.1, 1))
    render.setLight(render.attachNewNode(amb))
    env = None
    try:
        cube = base.loader.loadCubeMap(Filename.fromOsSpecific(os.path.join(rw_textures.TEX, "env_#.png")))
        env = simplepbr.EnvMap(cube, prefiltered_size=64, prefiltered_samples=16, blocking_prepare=True)
    except Exception:
        env = None
    pipeline = simplepbr.init(msaa_samples=4 if quality != "low" else 0, max_lights=8,
                              use_normal_maps=quality != "low", use_occlusion_maps=quality != "low",
                              enable_shadows=quality != "low", exposure=0.8, env_map=env)
    render.setAntialias(AntialiasAttrib.MMultisample)
    _state["quality"] = quality
    return pipeline


def aim_sun(centres):
    """Point the key light (and its shadows) at the rings in use."""
    sun = _state.get("sun")
    if sun is None or not centres:
        return
    xs, ys = [c[0] for c in centres], [c[1] for c in centres]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys)) + 2 * sim.RULES["ring_size"] + 4
    sun.setPos(cx + 6, cy - 12, 26)
    sun.lookAt(cx, cy, 0)
    if sun.node().isShadowCaster():
        sun.node().getLens().setFilmSize(span, span)


# ---------- the fight hall ----------
MAT_COLOURS = [(0.12, 0.13, 0.2), (0.35, 0.06, 0.06), (0.06, 0.2, 0.12), (0.2, 0.08, 0.3), (0.3, 0.2, 0.05),
               (0.05, 0.18, 0.3)]
EDGE_GLOW = (4.0, 1.2, 0.2)
ROPE_COLOURS = [(0.85, 0.1, 0.1), (0.95, 0.95, 0.95), (0.1, 0.25, 0.85)]


class StageVisual:
    """The hall: rings on raised platforms, ropes or an open edge, fire jets, ice, stands and a crowd."""

    def __init__(self, parent, ring_indices, hazards, look=None, user_mods=None):
        """user_mods: the teacher's user mods (fight_sim.USER_MODS); a mod draws its part only while it's on."""
        look = look or {}
        self.hazards = dict(hazards or {})
        self.user_mods = sim.user_mods_on(user_mods)
        self.root = parent.attachNewNode("stage_visual")
        self.name = str(look.get("name", "FIGHT LAB"))[:16]
        self.rings = {}
        self.lights = []
        self.zap_until = {}
        self.card = CardMaker("puff")
        self.card.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.dot = soft_dot()
        static = self.root.attachNewNode("static")
        indices = [i for i in ring_indices if 0 <= i < sim.MAX_RINGS] or [0]
        centres = [sim.RING_CENTRES[i] for i in indices]
        hall = self.root.attachNewNode("hall")
        self.build_hall(hall, look)
        hall.flattenStrong()
        hall.hide(SHADOW_MASK)  # the hall gets shadows but doesn't cast any
        for i in indices:
            self.rings[i] = self.build_ring(static, i)
        static.flattenStrong()  # one draw call per material: fast on old laptops
        self.build_lights(parent, centres)
        aim_sun(centres)
        # blasts (energy shots): a small pool of glowing balls
        self.shots = []
        for _ in range(12):
            ball = glow_node(self.root.attachNewNode(sphere(0.2, seg=12, rings=8).node()), (0.4, 0.9, 1.6))
            halo = glow_node(self.root.attachNewNode(sphere(0.34, seg=12, rings=8).node()), (0.08, 0.25, 0.5))
            ball.hide()
            halo.hide()
            self.shots.append((ball, halo))
        self.t = 0.0

    # ---- the hall around the rings: floor, stands, crowd, big screens, a lighting rig ----
    def build_hall(self, static, look):
        xs = [c[0] for c in sim.RING_CENTRES]
        ys = [c[1] for c in sim.RING_CENTRES]
        pad = sim.RULES["ring_size"] + 5
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
        floor_z = -0.8
        part(static, bevel_box(hx + 14, hy + 14, 0.05, 0.0, tile=0.25), "concrete", (0.3, 0.3, 0.34), 1.0, 0.0,
             pos=(cx, cy, floor_z - 0.05))
        # walkways between the rings: dark boards with yellow edge lines
        walk = Mesh(tile=0.5)
        bevel_box(hx, 0.9, 0.02, 0.0, mesh=walk, offset=Vec3(cx, 8, floor_z + 0.02))
        for x in (-8, 8):
            bevel_box(0.9, hy, 0.02, 0.0, mesh=walk, offset=Vec3(x, cy, floor_z + 0.02))
        part(static, walk, "concrete", (0.32, 0.26, 0.2), 1.0, 0.0)
        # tiered stands and a crowd all round (one mesh, a colour per person)
        rnd = random.Random(5)
        stands = Mesh(tile=0.5)
        crowd = Mesh(colours=True)
        shirts = [(0.8, 0.1, 0.1), (0.1, 0.3, 0.8), (0.9, 0.8, 0.2), (0.2, 0.6, 0.3), (0.9, 0.9, 0.9),
                  (0.15, 0.15, 0.18), (0.9, 0.5, 0.1), (0.5, 0.2, 0.6)]
        skins = [(0.85, 0.65, 0.5), (0.6, 0.42, 0.3), (0.4, 0.28, 0.2), (0.92, 0.75, 0.62)]
        for side in range(4):
            for row in range(5):
                d = row * 1.2 + 1.5
                z = floor_z + 0.3 + row * 0.6
                if side < 2:
                    y = y1 + d if side == 0 else y0 - d
                    bevel_box(hx + 6, 0.6, (z - floor_z) / 2, 0.02, mesh=stands, offset=Vec3(cx, y, (z + floor_z) / 2))
                    spots = [(x, y) for x in [x0 - 5 + k * 0.9 + (0.45 if row % 2 else 0)
                                             for k in range(int((hx + 5) * 2 / 0.9))]]
                else:
                    x = x1 + d if side == 2 else x0 - d
                    bevel_box(0.6, hy + 6, (z - floor_z) / 2, 0.02, mesh=stands, offset=Vec3(x, cy, (z + floor_z) / 2))
                    spots = [(x, y) for y in [y0 - 5 + k * 0.9 + (0.45 if row % 2 else 0)
                                             for k in range(int((hy + 5) * 2 / 0.9))]]
                if not look.get("crowd", True):
                    continue
                for x, y in spots:
                    if rnd.random() < 0.8:
                        crowd.colour = (*rnd.choice(shirts), 1)
                        tall = rnd.uniform(0.22, 0.3)
                        bevel_box(0.19, 0.14, tall, 0.06, mesh=crowd, offset=Vec3(x, y, z + tall))
                        crowd.colour = (*rnd.choice(skins), 1)
                        bevel_box(0.09, 0.09, 0.1, 0.04, mesh=crowd, offset=Vec3(x, y, z + tall * 2 + 0.11))
        part(static, stands, "concrete", (0.22, 0.24, 0.3), 1.0, 0.0)
        part(static, crowd, None, (0.5, 0.5, 0.5), 0.9, 0.0)
        # big screens at both ends, with the hall's name
        for y, h in ((y1 + 9.0, 180), (y0 - 9.0, 0)):
            part(static, bevel_box(6.5, 0.3, 2.0, 0.06), "steel", (0.08, 0.08, 0.1), pos=(cx, y, 6.0))
            glowbox = part(static, bevel_box(6.2, 0.05, 1.75, 0.0), None, (0, 0, 0), 1, 0, emission=(0.05, 0.02, 0.12),
                           pos=(cx, y - 0.3 if h == 180 else y + 0.3, 6.0))
            del glowbox
            text = TextNode("screen")
            text.setText(self.name)
            text.setAlign(TextNode.ACenter)
            tn = self.root.attachNewNode(text)
            tn.setPos(cx, y - 0.4 if h == 180 else y + 0.4, 5.55)
            tn.setH(h)
            tn.setScale(1.6)
            mats().apply(tn, None, (0, 0, 0), 1, 0, emission=(4.0, 1.2, 0.3))
        # a lighting truss over the rings
        truss, lamps = Mesh(), Mesh()
        for y in (0, 16):
            bevel_box(hx, 0.15, 0.15, 0.02, mesh=truss, offset=Vec3(cx, y, 8.5))
            for x in (-16, 0, 16):
                for dx in (-2.5, 2.5):
                    bevel_box(0.3, 0.25, 0.12, 0.02, mesh=lamps, offset=Vec3(x + dx, y, 8.3))
        for x in (x0, x1):
            bevel_box(0.2, 0.2, 4.8, 0.02, mesh=truss, offset=Vec3(x, 0, floor_z + 4.8))
            bevel_box(0.2, 0.2, 4.8, 0.02, mesh=truss, offset=Vec3(x, 16, floor_z + 4.8))
        rig = self.root.attachNewNode("lighting_rig")
        rig.hide(SHADOW_MASK)
        part(rig, truss, "steel", (0.2, 0.2, 0.22), 1.0, 1.0)
        part(rig, lamps, None, (1, 1, 1), 0.3, 0.0, emission=(6, 5.5, 5))
        rig.flattenStrong()

    # ---- one ring ----
    def build_ring(self, static, i):
        cx, cy = sim.RING_CENTRES[i]
        R = sim.RULES["ring_size"]
        hz = self.hazards
        roped = not hz.get("ring_out", True)
        plat_r = R + (0.7 if roped else 0.1)
        mat = MAT_COLOURS[i % len(MAT_COLOURS)]
        # the platform (top at z 0) and the mat
        part(static, cylinder(plat_r, 0.4, seg=48, tile=0.6), "steel", (0.2, 0.2, 0.23), 1.0, 1.0,
             pos=(cx, cy, -0.42))
        part(static, cylinder(plat_r + 0.08, 0.06, seg=48), "paint", (0.08, 0.08, 0.1), 0.6, 0.5,
             pos=(cx, cy, -0.8 + 0.06))
        part(static, cylinder(plat_r - 0.02, 0.012, seg=48, tile=0.4), "concrete", mat, 0.95, 0.0,
             pos=(cx, cy, -0.01))
        # markings: a circle, the start lines, and the name painted in the middle
        marks = Mesh()
        for k in range(40 if not self.hazards.get("slippery") else 0):  # (the ice patch has its own edge)
            a = 2 * math.pi * k / 40
            bevel_box(0.14, 0.04, 0.003, 0.0, mesh=marks, offset=Vec3(cx + math.cos(a) * R * 0.45,
                                                                       cy + math.sin(a) * R * 0.45, 0.004))
        for s in (-1, 1):
            bevel_box(0.05, 0.45, 0.003, 0.0, mesh=marks, offset=Vec3(cx + s * 1.6, cy, 0.004))
        part(static, marks, None, (0.9, 0.9, 0.95), 0.6, 0.0)
        logo = TextNode("logo")
        logo.setText(self.name if i == 0 else f"RING {i + 1}")
        logo.setAlign(TextNode.ACenter)
        logo_np = static.attachNewNode(logo)
        logo_np.setPos(cx, cy - 0.25, 0.008)
        logo_np.setHpr(0, -90, 0)
        logo_np.setScale(0.75)
        mats().apply(logo_np, None, (0.95, 0.75, 0.1), 0.5, 0.0)
        ring = {"centre": (cx, cy), "ropes": None, "edge": None, "jets": [], "ice": None}
        if roped:
            posts = Mesh(tile=0.8)
            post_r = (R + 0.08) / math.cos(math.pi / 8)  # the ropes' middles sit just outside the fighting circle
            corners = [(cx + math.cos(math.pi / 8 + k * math.pi / 4) * post_r,
                        cy + math.sin(math.pi / 8 + k * math.pi / 4) * post_r) for k in range(8)]
            for x, y in corners:
                cylinder(0.08, 0.7, seg=12, mesh=posts, offset=Vec3(x, y, 0.7), bevel=0.02)
            # build the ropes as their own nodes so electric ropes can glow
            rope_root = self.root.attachNewNode(f"ropes{i}")
            for z in (0.45, 0.85, 1.25):
                for k in range(8):
                    (xa, ya), (xb, yb) = corners[k], corners[(k + 1) % 8]
                    half = math.hypot(xb - xa, yb - ya) / 2
                    # a rope along x, turned to point from one post to the next
                    tn = rope_root.attachNewNode(cylinder(0.035, half, axis="x", seg=8).node())
                    tn.setPos((xa + xb) / 2, (ya + yb) / 2, z)
                    tn.setH(math.degrees(math.atan2(yb - ya, xb - xa)))
            rope_root.flattenStrong()
            electric = hz.get("electric_ropes")
            colour = (0.5, 0.8, 1.0) if electric else (0.85, 0.12, 0.1)
            mats().apply(rope_root, None, colour, 0.5, 0.0, emission=(0.4, 1.2, 3.0) if electric else None)
            part(static, posts, "steel", (0.75, 0.75, 0.8), 1.0, 1.0)
            pads = Mesh()
            for x, y in corners:
                bevel_box(0.12, 0.12, 0.45, 0.05, mesh=pads, offset=Vec3(x, y, 0.85))
            part(static, pads, "paint", ROPE_COLOURS[i % 3], 0.6, 0.2)
            ring["ropes"] = rope_root
            ring["electric"] = bool(electric)
        else:
            # an open edge: a glowing line, and a drop to the hall floor
            edge = self.root.attachNewNode(f"edge{i}")
            ring_mesh = Mesh()
            for k in range(64):
                a0, a1 = 2 * math.pi * k / 64, 2 * math.pi * (k + 1) / 64
                r0, r1 = R - 0.05, R + 0.04
                pts = [Vec3(cx + math.cos(a0) * r0, cy + math.sin(a0) * r0, 0.006),
                       Vec3(cx + math.cos(a1) * r0, cy + math.sin(a1) * r0, 0.006),
                       Vec3(cx + math.cos(a1) * r1, cy + math.sin(a1) * r1, 0.006),
                       Vec3(cx + math.cos(a0) * r1, cy + math.sin(a0) * r1, 0.006)]
                ring_mesh.poly(pts, Vec3(0, 0, 1))
            part(edge, ring_mesh, None, (0, 0, 0), 1.0, 0.0, emission=EDGE_GLOW)
            ring["edge"] = edge
        if hz.get("fire_jets"):
            for a in sim.JET_ANGLES:
                x = cx + math.cos(math.radians(a)) * R * 0.55
                y = cy + math.sin(math.radians(a)) * R * 0.55
                part(static, cylinder(0.32, 0.01, seg=20), "hazard", (1, 1, 1), 1.0, 0.0, pos=(x, y, 0.005))
                part(static, cylinder(0.16, 0.02, seg=16, bevel=0.01), "steel", (0.15, 0.15, 0.16), 1.0, 1.0,
                     pos=(x, y, 0.01))
                flame = self.root.attachNewNode(f"jet{i}")
                flame.setPos(x, y, 0.03)
                puffs = []
                for k in range(14):  # soft glowing puffs that rise up the jet
                    card = flame.attachNewNode(self.card.generate())
                    card.setTexture(self.dot)
                    card.setBillboardPointEye()
                    puffs.append(card)
                flame.setPythonTag("puffs", puffs)
                flame.setLightOff(1)
                flame.setShaderOff(1)
                flame.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                                      ColorBlendAttrib.O_one))
                flame.setDepthWrite(False)
                flame.setBin("fixed", 24)
                flame.hide()
                ring["jets"].append(flame)
        if hz.get("spikes"):  # a striped plate with steel spikes sticking up
            spikes = Mesh()
            for a in sim.SPIKE_ANGLES:
                x = cx + math.cos(math.radians(a)) * R * 0.78
                y = cy + math.sin(math.radians(a)) * R * 0.78
                part(static, cylinder(sim.SPIKE_RADIUS, 0.01, seg=24), "hazard", (1, 1, 1), 1.0, 0.0, pos=(x, y, 0.005))
                for k in range(7):
                    r = 0.0 if k == 0 else sim.SPIKE_RADIUS * 0.6
                    sx, sy = x + math.cos(k * math.pi / 3) * r, y + math.sin(k * math.pi / 3) * r
                    cylinder(0.06, 0.12, seg=8, r_top=0, mesh=spikes, offset=Vec3(sx, sy, 0.14))
            part(static, spikes, "steel", (0.8, 0.8, 0.85), 0.4, 1.0)
        if hz.get("slippery"):
            part(static, cylinder(R * 0.45, 0.006, seg=48), None, (0.55, 0.75, 0.92), 0.06, 0.3,
                 pos=(cx, cy, 0.002))
            part(static, cylinder(R * 0.45 + 0.05, 0.004, seg=48), None, (0.85, 0.95, 1.0), 0.3, 0.0,
                 pos=(cx, cy, 0.0))
            shine = Mesh()
            for k in range(6):
                a = k * 1.05
                bevel_box(R * 0.3, 0.012, 0.002, 0.0, mesh=shine,
                          offset=Vec3(cx + math.cos(a) * R * 0.12, cy + math.sin(a) * R * 0.15, 0.01))
            part(static, shine, None, (1, 1, 1), 0.02, 0.0, emission=(0.6, 0.8, 1.0))
        return ring

    def build_lights(self, parent, centres):
        """A spotlight over each ring in use (at most 6: simplepbr lights 8 things at once)."""
        render = _state.get("render", parent)
        for cx, cy in centres[:6]:
            sp = Spotlight("ring_spot")
            sp.setColor((5.5, 5.2, 4.8, 1))
            lens = PerspectiveLens()
            lens.setFov(52)
            sp.setLens(lens)
            sp.setAttenuation((1, 0, 0.012))
            np_ = render.attachNewNode(sp)
            np_.setPos(cx - 2.5, cy - 5.5, 9.5)
            np_.lookAt(cx, cy, 0)
            render.setLight(np_)
            self.lights.append(np_)

    # ---- every frame ----
    def zap(self, pos):
        """Electric ropes flash (call it when a "zap" hit happens)."""
        best = min(self.rings, key=lambda i: math.hypot(pos[0] - self.rings[i]["centre"][0],
                                                          pos[1] - self.rings[i]["centre"][1]))
        self.zap_until[best] = self.t + 0.35

    def update(self, rings_state, now, dt):
        self.t += dt
        by_index = {r["i"]: r for r in rings_state or []}
        n_shot = 0
        for i, ring in self.rings.items():
            rs = by_index.get(i)
            jets = (rs or {}).get("hz", {}).get("jets", [0, 0, 0, 0])
            for flame, power in zip(ring["jets"], jets):
                if power > 0.05:
                    flame.show()
                    height = 0.4 + 1.5 * power
                    for k, card in enumerate(flame.getPythonTag("puffs")):
                        f = (k / 14 + self.t * 2.2) % 1.0  # 0 at the nozzle, 1 at the top
                        wob = math.sin(self.t * 23 + k * 2.1) * 0.08
                        card.setPos(wob, math.cos(self.t * 19 + k) * 0.08, f * height)
                        card.setScale((0.8 - 0.45 * f) * (0.6 + 0.6 * power))
                        card.setColor(1.0, 0.8 - 0.6 * f, 0.3 - 0.27 * f, 1 - f * 0.8)
                else:
                    flame.hide()
            if ring["ropes"] is not None and ring.get("electric"):
                m = ring["ropes"].getMaterial()
                if self.zap_until.get(i, -1) > self.t:
                    f = 6 if int(self.t * 30) % 2 else 2
                    m.setEmission((f * 0.6, f * 0.9, f * 1.6, 1))
                else:
                    pulse = 0.8 + 0.4 * math.sin(self.t * 6 + i)
                    m.setEmission((0.3 * pulse, 0.9 * pulse, 2.6 * pulse, 1))
            if ring["edge"] is not None:
                pulse = 0.75 + 0.25 * math.sin(self.t * 3 + i)
                ring["edge"].getChild(0).getMaterial().setEmission(
                    (EDGE_GLOW[0] * pulse, EDGE_GLOW[1] * pulse, EDGE_GLOW[2] * pulse, 1))
            for sh in (rs or {}).get("sh", []):
                if n_shot >= len(self.shots):
                    break
                ball, halo = self.shots[n_shot]
                n_shot += 1
                for node in (ball, halo):
                    node.show()
                    node.setPos(sh[0], sh[1], sh[2])
                halo.setScale(1 + 0.25 * math.sin(self.t * 40))
        for ball, halo in self.shots[n_shot:]:
            ball.hide()
            halo.hide()

    def destroy(self):
        render = _state.get("render")
        for np_ in self.lights:
            if render is not None:
                render.clearLight(np_)
            np_.removeNode()
        self.lights = []
        self.root.removeNode()


# ---------- fighters ----------
THIGH, SHIN, ANKLE = 0.42, 0.42, 0.08
HIP_H = THIGH + SHIN + ANKLE          # hip joint height with straight legs
UPPER, FORE = 0.29, 0.26
JOINTS = ("hips", "waist", "neck", "ls", "le", "rs", "re", "lh", "lk", "la", "rh", "rk", "ra")


def leg(forward, hip_h, side=0.0):
    """Leg angles that put the foot `forward` metres in front of the hip, with the hip hip_h above the floor
    (a two-joint leg, solved with the cosine rule). Returns (thigh, knee, ankle) pitch angles."""
    down = max(0.2, hip_h - ANKLE)
    d = min(THIGH + SHIN - 1e-4, math.hypot(forward, down))
    bend = math.pi - math.acos(max(-1.0, min(1.0, (THIGH ** 2 + SHIN ** 2 - d ** 2) / (2 * THIGH * SHIN))))
    alpha = math.acos(max(-1.0, min(1.0, (THIGH ** 2 + d ** 2 - SHIN ** 2) / (2 * THIGH * d))))
    thigh = math.atan2(forward, down) + alpha
    knee = -bend
    return math.degrees(thigh), math.degrees(knee), -math.degrees(thigh + knee)


def pose(hz=0.84, lift=0.0, **joints):
    """A pose: hip height, an extra lift off the floor, and (heading, pitch, roll) for any joints."""
    p = {"hz": hz, "lift": lift}
    for j in JOINTS:
        p[j] = tuple(joints.get(j, (0, 0, 0)))
    return p


def legs(p, lead, rear, hz=None, spread=7, lift_l=0.0, lift_r=0.0):
    """Set both legs in pose p for feet `lead` (left) and `rear` (right) metres forward of the hips."""
    h = p["hz"] if hz is None else hz
    for name, fwd, lift, roll in (("l", lead, lift_l, -spread), ("r", rear, lift_r, spread)):
        t, k, a = leg(fwd, h - lift)
        p[name + "h"] = (0, t, roll)
        p[name + "k"] = (0, k, 0)
        p[name + "a"] = (0, a, -roll)
    return p


def blend(a, b, f):
    f = max(0.0, min(1.0, f))
    out = {}
    for key, va in a.items():
        vb = b[key]
        if isinstance(va, tuple):
            out[key] = tuple(x + (y - x) * f for x, y in zip(va, vb))
        else:
            out[key] = va + (vb - va) * f
    return out


def ease(f):
    f = max(0.0, min(1.0, f))
    return f * f * (3 - 2 * f)


def stance(bob=0.0):
    """The fighting stance: side-on, left foot forward, fists up guarding the chin."""
    p = pose(hz=0.82 + bob, hips=(-28, 0, 0), waist=(-4, 6, 0), neck=(30, -4, 0),
             ls=(10, 55, -18), le=(0, 105, 0), rs=(20, 32, -10), re=(0, 128, 0))
    return legs(p, 0.26, -0.2)


def guard(p):
    """Put the fists up in front of the face (blocking)."""
    p["ls"], p["le"] = (25, 78, -30), (0, 118, 0)
    p["rs"], p["re"] = (-5, 72, -8), (0, 122, 0)
    return p


def crouch_pose():
    p = stance()
    p["hz"] = 0.5
    p["waist"] = (-4, 22, 0)
    p["neck"] = (30, -18, 0)
    return legs(p, 0.32, -0.12, spread=16)


# attack key poses: (wind-up, strike)
def attack_poses(name):
    s = stance()
    if name == "punch":
        wind = dict(s, rs=(10, 25, -12), re=(0, 140, 0), waist=(-12, 8, 0))
        hit = dict(s, rs=(-5, 88, -4), re=(0, 4, 0), waist=(22, 10, 0), neck=(8, -6, 0), hips=(-12, 0, 0),
                   ls=(10, 45, -22), le=(0, 120, 0))
        return wind, legs(hit, 0.3, -0.26, hz=0.8)
    if name == "kick":
        wind = dict(s, waist=(-8, -6, 0), rh=(0, 85, 6), rk=(0, -110, 0), ra=(0, 20, 0), hz=0.84)
        wind = legs(dict(wind), 0.05, -0.2, hz=0.84)
        wind["rh"], wind["rk"], wind["ra"] = (0, 85, 6), (0, -115, 0), (0, 30, 0)
        hit = dict(s, waist=(-10, -18, 0), neck=(20, 12, 0), hips=(-10, 0, 0))
        hit = legs(dict(hit), 0.02, -0.2, hz=0.86)
        hit["rh"], hit["rk"], hit["ra"] = (0, 92, 4), (0, -4, 0), (0, 40, 0)
        return wind, hit
    if name == "low":
        wind = crouch_pose()
        wind["hz"] = 0.45
        wind = legs(wind, 0.15, -0.1, hz=0.45, spread=20)
        hit = dict(wind, waist=(10, 38, 0), neck=(0, -35, 0), hips=(-50, 0, 0),
                   ls=(0, 70, -30), le=(0, 20, 0), rs=(0, 60, 25), re=(0, 20, 0))
        hit = legs(hit, 0.1, 0.0, hz=0.42, spread=20)
        hit["rh"], hit["rk"], hit["ra"] = (-20, 62, 55), (0, -4, 0), (0, 25, 0)
        return wind, hit
    if name == "high":
        wind = legs(dict(s, waist=(-20, -5, 0)), 0.1, -0.15, hz=0.86)
        wind["rh"], wind["rk"], wind["ra"] = (0, 80, 25), (0, -110, 0), (0, 30, 0)
        hit = dict(s, waist=(-30, -26, -12), neck=(35, 18, 8), hips=(-45, 0, -10),
                   ls=(0, 50, -45), le=(0, 70, 0), rs=(0, 20, 35), re=(0, 60, 0))
        hit = legs(hit, 0.0, -0.1, hz=0.9)
        hit["rh"], hit["rk"], hit["ra"] = (0, 118, 22), (0, -5, 0), (0, 30, 0)
        return wind, hit
    if name == "jump_kick":
        wind = dict(s, lh=(0, 80, -6), lk=(0, -120, 0), rh=(0, 60, 6), rk=(0, -110, 0), waist=(0, 10, 0), hz=0.9)
        hit = dict(s, lh=(0, 60, -6), lk=(0, -115, 0), rh=(0, 95, 4), rk=(0, -2, 0), ra=(0, 30, 0),
                   waist=(-10, -20, 0), hips=(-20, 0, 0), ls=(0, 40, -40), le=(0, 90, 0), rs=(0, -20, 30),
                   re=(0, 30, 0), hz=0.95)
        return wind, hit
    if name == "throw":
        wind = dict(s, ls=(-10, 82, -8), le=(0, 25, 0), rs=(10, 82, 8), re=(0, 25, 0), waist=(0, 18, 0), hips=(0, 0, 0))
        wind = legs(wind, 0.3, -0.25, hz=0.78)
        hit = dict(wind, ls=(-10, 150, -20), le=(0, 40, 0), rs=(10, 150, 20), re=(0, 40, 0), waist=(60, -25, 0),
                   neck=(-20, 10, 0), hips=(40, 0, 0))
        return wind, hit
    if name == "blast":
        wind = dict(s, ls=(20, -20, -10), le=(0, 100, 0), rs=(-20, -20, 10), re=(0, 100, 0), waist=(-30, 5, 0),
                    hips=(-40, 0, 0), neck=(40, 0, 0))
        wind = legs(wind, 0.3, -0.25, hz=0.72, spread=14)
        hit = dict(wind, ls=(-12, 88, -6), le=(0, 8, 0), rs=(12, 88, 6), re=(0, 8, 0), waist=(0, 6, 0),
                   hips=(0, 0, 0), neck=(0, -4, 0))
        hit = legs(hit, 0.35, -0.3, hz=0.72, spread=14)
        return wind, hit
    if name == "uppercut":
        wind = crouch_pose()
        wind["rs"], wind["re"], wind["waist"] = (0, -15, 5), (0, 100, 0), (-25, 30, 0)
        hit = dict(s, rs=(-10, 172, 10), re=(0, 12, 0), waist=(20, -14, 0), neck=(-10, 10, 0), hips=(0, 0, 0),
                   ls=(0, 20, -30), le=(0, 90, 0), lift=0.35)
        hit = legs(hit, 0.1, -0.05, hz=0.92)
        hit["lh"], hit["lk"] = (0, 55, -6), (0, -80, 0)
        return wind, hit
    if name == "spin_kick":
        wind = legs(dict(s, waist=(-30, 0, 0), ls=(0, 30, -70), le=(0, 40, 0), rs=(0, 30, 70), re=(0, 40, 0)),
                    0.05, -0.1, hz=0.86)
        hit = dict(wind, waist=(0, -6, -18), hips=(0, 0, -15), ls=(0, 10, -85), le=(0, 10, 0), rs=(0, 10, 70),
                   re=(0, 10, 0), lift=0.15)
        hit["rh"], hit["rk"], hit["ra"] = (0, 15, 88), (0, -4, 0), (0, 0, 0)
        return wind, hit
    if name == "slam":
        wind = dict(s, ls=(-10, 85, -8), le=(0, 30, 0), rs=(10, 85, 8), re=(0, 30, 0), waist=(0, 20, 0))
        wind = legs(wind, 0.3, -0.25, hz=0.76)
        lift = dict(wind, ls=(-10, 175, -12), le=(0, 20, 0), rs=(10, 175, 12), re=(0, 20, 0), waist=(0, -20, 0),
                    neck=(0, 15, 0))
        return wind, lift
    if name == "cartwheel":  # (user mod) a star, arms up and legs apart: FighterVisual.update turns it right over
        wind = pose(hz=0.86, ls=(0, 172, -15), le=(0, 8, 0), rs=(0, 172, 15), re=(0, 8, 0),
                    lh=(0, 0, -35), lk=(0, -5, 0), rh=(0, 0, 35), rk=(0, -5, 0))
        hit = dict(wind, lh=(0, 0, -55), rh=(0, 0, 55))  # the legs whip over, wide apart
        return wind, hit
    return s, s


def cartwheel_turn(k):
    """How far over (degrees) the cartwheel kick is at progress k: onto the hands as it starts (k 0-1), the feet
    come over the top and down as it hits (1-2), then back onto the feet early in the recovery."""
    if k < 1:
        return 180.0 * max(0.0, k)
    if k < 2:
        return 180.0 + 120.0 * (k - 1)
    return 300.0 + 60.0 * min(1.0, (k - 2) / 0.4)


def slam_down():
    p = stance()
    p = dict(p, ls=(-10, 110, -8), le=(0, 10, 0), rs=(10, 110, 8), re=(0, 10, 0), waist=(0, 45, 0), neck=(0, -30, 0))
    return legs(p, 0.35, -0.3, hz=0.62, spread=18)


def lying(face_up=True, spread=0.0):
    """Flat on the floor (knocked down): the hips tip over and drop."""
    p = pose(hz=0.16, hips=(0, 88 if face_up else -88, 0), neck=(0, -8, 0),
             ls=(0, 10 + 60 * spread, -30 - 40 * spread), le=(0, 20, 0),
             rs=(0, 10 + 40 * spread, 30 + 50 * spread), re=(0, 30, 0),
             lh=(0, 8, -10), lk=(0, -10, 0), rh=(0, 25, 12), rk=(0, -40, 0))
    return p


def anim_pose(a, k):
    """The target pose for animation a at progress k (see the top of the file)."""
    a = {"hit_body": "hitstun", "swept": "knockdown"}.get(a, a)  # (the detailed models have their own for these)
    if a == "idle":
        p = stance(0.015 * math.sin(k * 5.0))
        p["le"] = (0, 105 + 4 * math.sin(k * 5.0 + 1), 0)
        return p
    if a in ("walk_f", "walk_b"):
        ph = k * 2 * math.pi / 0.8 * (1 if a == "walk_f" else -1)
        p = stance(0.015 * math.cos(2 * ph))
        s = math.sin(ph)
        return legs(p, 0.24 + 0.14 * s, -0.2 - 0.14 * s, lift_l=max(0, math.cos(ph)) * 0.08,
                    lift_r=max(0, -math.cos(ph)) * 0.08)
    if a in ("side_l", "side_r"):
        ph = k * 2 * math.pi / 0.7
        p = stance(0.02 * math.cos(2 * ph))
        s = math.sin(ph) * (1 if a == "side_l" else -1)
        p = legs(p, 0.24, -0.2, spread=8 + 10 * s, lift_l=max(0, math.cos(ph)) * 0.07,
                 lift_r=max(0, -math.cos(ph)) * 0.07)
        p["hips"] = (-28, 0, 4 * s)
        return p
    if a == "crouch":
        return crouch_pose()
    if a == "block":
        return guard(stance())
    if a == "low_block":
        p = guard(crouch_pose())
        p["ls"], p["le"] = (25, 48, -30), (0, 120, 0)  # a lower guard
        return p
    if a == "blockstun":
        p = guard(stance())
        p["waist"] = (-4, -10 * (1 - k), 0)
        return p
    if a == "hitstun":
        f = math.sin(min(1.0, k) * math.pi) if k > 0.15 else k / 0.15
        p = stance()
        p["waist"] = (-4, 6 - 32 * f, 6 * f)
        p["neck"] = (30, -4 - 35 * f, 0)
        p["ls"], p["rs"] = (10, 40 - 30 * f, -18 - 35 * f), (20, 30 - 20 * f, -10 + 40 * f)
        p["le"], p["re"] = (0, 60, 0), (0, 70, 0)
        return p
    if a == "hit_low":
        f = math.sin(min(1.0, k) * math.pi) if k > 0.15 else k / 0.15
        p = crouch_pose()
        p["waist"] = (-4, 22 + 25 * f, 0)
        p["neck"] = (30, -18 + 20 * f, 0)
        p["ls"], p["le"], p["rs"], p["re"] = (0, 30, -10), (0, 90, 0), (0, 30, 10), (0, 90, 0)
        return p
    if a in ("launched", "ringout"):
        f = min(1.0, k / 0.35)
        wob = math.sin(k * 14)
        p = pose(hz=0.84, hips=(0, 55 * f, 10 * wob), waist=(0, -20, 0), neck=(0, -25, 0),
                 ls=(0, 100 + 30 * wob, -60), le=(0, 30, 0), rs=(0, 100 - 30 * wob, 60), re=(0, 30, 0),
                 lh=(0, 40 + 20 * wob, -12), lk=(0, -60, 0), rh=(0, 20 - 20 * wob, 12), rk=(0, -30, 0))
        if a == "ringout":
            p["hips"] = (0, 20 * wob, 15 * wob)
        return p
    if a == "thrown":
        p = anim_pose("launched", k)
        p["hips"] = (0, min(1.0, k / 0.5) * 200, 0)  # tumbling head over heels
        return p
    if a == "knockdown":
        if k < 0.25:
            return blend(anim_pose("launched", 0.4), lying(), k / 0.25)
        return lying()
    if a == "ko":
        return lying(spread=1.0)
    if a == "getup":
        kneel = legs(pose(hz=0.5, waist=(0, 35, 0), neck=(0, -20, 0), ls=(0, 20, -20), le=(0, 40, 0),
                          rs=(0, 60, 10), re=(0, 30, 0)), 0.35, -0.3, spread=12)
        kneel["rk"] = (0, -140, 0)
        if k < 0.5:
            return blend(lying(), kneel, ease(k * 2))
        return blend(kneel, stance(), ease((k - 0.5) * 2))
    if a == "jump":
        tuck = pose(hz=0.84, waist=(0, 15, 0), ls=(10, 55, -18), le=(0, 105, 0), rs=(20, 40, -10), re=(0, 120, 0),
                    lh=(0, 80, -6), lk=(0, -120, 0), la=(0, 30, 0), rh=(0, 55, 6), rk=(0, -110, 0), ra=(0, 40, 0))
        crouched = crouch_pose()
        if k < 0.15:
            return blend(crouched, tuck, k / 0.15)
        if k > 0.85:
            return blend(tuck, crouched, (k - 0.85) / 0.15)
        return tuck
    if a == "win":
        p = stance()
        p = legs(p, 0.2, -0.2, hz=0.9, spread=10)
        p["hips"], p["waist"], p["neck"] = (-10, 0, 0), (10, -8, 0), (0, 8, 0)
        wave = math.sin(k * 6) * 6
        p["rs"], p["re"] = (0, 168 + wave, 12), (0, 15, 0)
        p["ls"], p["le"] = (0, 15, -35), (0, 95, 0)
        return p
    if a == "intro":
        return anim_pose("idle", k)
    if a in sim.MOVES:
        wind, hit = attack_poses(a)
        s = stance() if a != "jump_kick" else anim_pose("jump", 0.5)
        if a == "slam":
            if k < 1:
                return blend(s, wind, ease(k))
            if k < 2:
                return blend(wind, hit, ease(k - 1))
            return blend(slam_down(), s, ease((k - 2) * 1.2 - 0.2))
        if k < 1:
            return blend(s, wind, ease(k))
        if k < 2:
            return blend(wind, hit, ease(min(1.0, (k - 1) * 3)))
        return blend(hit, s, ease(k - 2))
    return stance()


def rgb(c, default):
    try:
        return tuple(max(0, min(255, v)) / 255 for v in c)
    except (TypeError, ValueError):
        return default


class FighterVisual:
    """A fighter built from a design: a robot (armour, glowing eyes) or a human (a martial artist)."""

    def __init__(self, parent, design):
        self.design = design
        style = design.get("style") or {}
        self.boss = bool(design.get("model"))
        self.robot = design.get("body", "robot") == "robot"  # (other bodies are built as a human)
        size = 1.3 if self.boss else design.get("settings", {}).get("size", 100) / 100
        self.size = size
        colour = rgb(design.get("colour"), (0.7, 0.4, 0.2))
        trim = rgb(style.get("trim"), (0.12, 0.12, 0.14) if self.robot else (0.08, 0.08, 0.08))
        lights = rgb(style.get("lights"), (1.0, 0.35, 0.1) if self.robot else (0.9, 0.9, 0.9))
        skin = rgb(style.get("skin"), (0.85, 0.63, 0.47))
        self.colours = {"main": colour, "trim": trim, "lights": lights, "skin": skin}
        self.root = parent.attachNewNode(f"fighter_{design.get('name', '')}")
        self.body = self.root.attachNewNode("body")
        self.body.setScale(size)
        self.tag = None
        self.nodes = {}
        self.glow_parts = []
        self.build_skeleton()
        self.pending = {}
        if self.robot:
            self.build_robot()
        else:
            self.build_human()
        self.finish()
        self.cur = stance()
        self.apply(self.cur)
        self.pos = None
        self.h = 0.0
        self.flashing = False
        self.spin = 0.0  # extra turn for the spin kick (degrees)
        self.wheel = None  # how far over the cartwheel kick is (degrees), while there is one
        self.hand_glow = []
        for side in ("l", "r"):
            g = glow_node(self.nodes[side + "fist"].attachNewNode(sphere(0.13, seg=10, rings=6).node()),
                          (0.3, 0.8, 1.5) if self.robot else (1.4, 0.8, 0.2))
            g.hide()
            self.hand_glow.append(g)

    # ---- the skeleton: empty joints that the body parts hang from ----
    def build_skeleton(self):
        n = self.nodes
        wide = 0.25 if self.robot else 0.2
        if self.boss:
            wide += 0.04
        n["hips"] = self.body.attachNewNode("hips")
        n["hips"].setZ(HIP_H)
        n["waist"] = n["hips"].attachNewNode("waist")
        n["waist"].setZ(0.1)
        n["neck"] = n["waist"].attachNewNode("neck")
        n["neck"].setZ(0.5)
        for side, x in (("l", -1), ("r", 1)):
            sh = n[side + "s"] = n["waist"].attachNewNode(side + "_shoulder")
            sh.setPos(x * wide, 0, 0.44)
            el = n[side + "e"] = sh.attachNewNode(side + "_elbow")
            el.setZ(-UPPER)
            n[side + "fist"] = el.attachNewNode(side + "_fist")
            n[side + "fist"].setZ(-FORE)
            hip = n[side + "h"] = n["hips"].attachNewNode(side + "_hip")
            hip.setX(x * 0.11)
            kn = n[side + "k"] = hip.attachNewNode(side + "_knee")
            kn.setZ(-THIGH)
            an = n[side + "a"] = kn.attachNewNode(side + "_ankle")
            an.setZ(-SHIN)

    def geo(self, joint, pieces):
        """Add shapes to a joint. pieces: list of (colour key, mesh). They are joined up in finish()."""
        z = 0.0
        if joint.endswith("fist"):  # a fist doesn't move on its own: it joins the forearm (one less part to draw)
            joint, z = joint[0] + "e", -FORE
        self.pending.setdefault(joint, []).extend((key, mesh, z) for key, mesh in pieces)

    def finish(self):
        """Join each joint's shapes into one piece, coloured per shape (fast: about 15 parts to draw a fighter).
        Glowing shapes (eyes, lights) stay separate so they can shine."""
        c = self.colours
        colours = {
            "main": c["main"], "trim": c["trim"], "dark": (0.16, 0.16, 0.18), "skin": c["skin"],
            "hair": self.hair_colour(), "pants": tuple(v * 0.55 for v in c["main"]), "white": (0.92, 0.92, 0.9),
        }
        for joint, pieces in self.pending.items():
            holder = self.nodes[joint].attachNewNode("geo")
            glow = None
            for key, mesh, z in pieces:
                if key == "glow":
                    glow = glow or self.nodes[joint].attachNewNode("glow")
                    glow.attachNewNode(mesh.node()).setZ(z)
                    continue
                piece = holder.attachNewNode(mesh.node())
                piece.setZ(z)
                piece.setColor(*(v ** 2.2 for v in colours[key]), 1)  # (lighting uses linear colours)
            holder.flattenStrong()  # the colours go into the shapes' corners, and the shapes become one
            if self.robot:
                mats().apply(holder, "paint", (1, 1, 1), 0.55, 0.75)
            else:
                mats().apply(holder, None, (1, 1, 1), 0.75, 0.0)
            if glow is not None:
                glow.flattenStrong()
                mats().apply(glow, None, (0, 0, 0), 1.0, 0.0, emission=tuple(v * 5 for v in c["lights"]))
                self.glow_parts.append(glow)
        self.pending = {}

    def hair_colour(self):
        name = str(self.design.get("name", ""))
        choices = [(0.08, 0.06, 0.05), (0.3, 0.18, 0.08), (0.55, 0.35, 0.15), (0.12, 0.1, 0.1), (0.7, 0.55, 0.3)]
        return choices[sum(ord(ch) for ch in name) % len(choices)]

    def build_robot(self):
        V = Vec3
        big = 1.15 if self.boss else 1.0
        # hips and legs
        self.geo("hips", [("dark", bevel_box(0.2 * big, 0.13, 0.1, 0.03, offset=V(0, 0, 0.02))),
                          ("main", bevel_box(0.22 * big, 0.15, 0.05, 0.02, offset=V(0, 0, 0.1)))])
        for s in ("l", "r"):
            x = -1 if s == "l" else 1
            self.geo(s + "h", [("dark", cylinder(0.07, THIGH / 2, seg=10, offset=V(0, 0, -THIGH / 2))),
                               ("main", bevel_box(0.1 * big, 0.11, 0.15, 0.03, offset=V(0, 0.01, -0.18))),
                               ("trim", sphere(0.085, seg=10, rings=6, offset=V(0, 0, 0)))])
            self.geo(s + "k", [("dark", cylinder(0.06, SHIN / 2, seg=10, offset=V(0, 0, -SHIN / 2))),
                               ("main", bevel_box(0.095 * big, 0.12, 0.17, 0.03, offset=V(0, 0.02, -0.2))),
                               ("trim", bevel_box(0.07, 0.05, 0.06, 0.02, offset=V(0, 0.09, -0.02))),
                               ("glow", bevel_box(0.02, 0.005, 0.07, 0.0, offset=V(x * 0.0, 0.142, -0.22)))])
            self.geo(s + "a", [("trim", bevel_box(0.09 * big, 0.16, 0.045, 0.02, offset=V(0, 0.05, -ANKLE + 0.045))),
                               ("dark", bevel_box(0.07, 0.05, 0.04, 0.02, offset=V(0, -0.08, -ANKLE + 0.05)))])
        # chest: a big armoured torso with a glowing core and the fighter's number
        chest = [("dark", bevel_box(0.17 * big, 0.12, 0.14, 0.03, offset=V(0, 0, 0.1))),
                 ("main", bevel_box(0.25 * big, 0.17, 0.2, 0.05, offset=V(0, 0.01, 0.36))),
                 ("trim", bevel_box(0.2 * big, 0.04, 0.12, 0.03, offset=V(0, 0.17, 0.36))),
                 ("glow", cylinder(0.055, 0.01, axis="y", seg=16, offset=V(0, 0.215, 0.38))),
                 ("trim", bevel_box(0.27 * big, 0.12, 0.035, 0.02, offset=V(0, 0, 0.52)))]
        if self.boss:
            for x in (-1, 1):  # spikes on the collar
                for k in range(3):
                    chest.append(("trim", cylinder(0.035, 0.06, seg=8, r_top=0.0,
                                                   offset=V(x * (0.12 + k * 0.06), 0.02, 0.6))))
        self.geo("waist", chest)
        # head: a helmet with a visor that glows
        head = [("dark", cylinder(0.05, 0.05, seg=10, offset=V(0, 0, 0.04))),
                ("main", bevel_box(0.12, 0.13, 0.12, 0.04, offset=V(0, 0, 0.18))),
                ("trim", bevel_box(0.125, 0.05, 0.03, 0.015, offset=V(0, 0.1, 0.22))),
                ("glow", bevel_box(0.1, 0.012, 0.022, 0.0, offset=V(0, 0.132, 0.2))),
                ("trim", bevel_box(0.03, 0.1, 0.05, 0.015, offset=V(0, -0.02, 0.31)))]
        if self.boss:
            head += [("trim", cylinder(0.025, 0.08, seg=8, r_top=0.0, offset=V(x * 0.1, 0, 0.36))) for x in (-1, 1)]
        self.geo("neck", head)
        # arms: shoulder pads, pistons and big fists
        for s in ("l", "r"):
            x = -1 if s == "l" else 1
            self.geo(s + "s", [("main", bevel_box(0.1 * big, 0.12, 0.09, 0.04, offset=V(x * 0.03, 0, 0.02))),
                               ("trim", bevel_box(0.075, 0.075, 0.11, 0.025, offset=V(0, 0, -0.16))),
                               ("dark", cylinder(0.05, UPPER / 2, seg=10, offset=V(0, 0, -UPPER / 2)))])
            self.geo(s + "e", [("main", bevel_box(0.075 * big, 0.08, 0.12, 0.03, offset=V(0, 0, -0.13))),
                               ("dark", sphere(0.06, seg=10, rings=6)),
                               ("glow", bevel_box(0.005, 0.03, 0.06, 0.0, offset=V(x * 0.078 * big, 0, -0.13)))])
            self.geo(s + "fist", [("trim", bevel_box(0.07 * big, 0.075, 0.07, 0.03, offset=V(0, 0.01, -0.05)))])
        self.number_plate()

    def number_plate(self):
        text = str((self.design.get("style") or {}).get("number") or self.design.get("name", ""))[:8]
        if not text:
            return
        t = TextNode("number")
        t.setText(text)
        t.setAlign(TextNode.ACenter)
        tn = self.nodes["waist"].attachNewNode(t)
        tn.setPos(0, -0.18 if self.robot else -0.14, 0.34)
        tn.setH(180)
        tn.setScale(0.07)
        mats().apply(tn, None, self.colours["lights"] if self.robot else self.colours["trim"], 0.5, 0.0)

    def build_human(self):
        V = Vec3
        big = 1.15 if self.boss else 1.0
        # legs: loose trousers (a darker shade of the gi) and bare feet
        self.geo("hips", [("pants", bevel_box(0.19 * big, 0.12, 0.1, 0.06, offset=V(0, 0, 0.02))),
                          ("trim", bevel_box(0.2 * big, 0.13, 0.035, 0.015, offset=V(0, 0, 0.1)))])
        for s in ("l", "r"):
            self.geo(s + "h", [("pants", capsule(0.085 * big, THIGH, seg=12))])
            self.geo(s + "k", [("pants", cylinder(0.075 * big, SHIN * 0.42, seg=12, r_top=0.07 * big,
                                                  offset=V(0, 0, -SHIN * 0.42))),
                               ("skin", capsule(0.045, SHIN * 0.5, seg=10, offset=V(0, 0, -SHIN * 0.5)))])
            self.geo(s + "a", [("skin", sphere(0.06, offset=V(0, 0.05, -ANKLE + 0.035), scale=V(0.8, 1.9, 0.6),
                                               seg=12, rings=6))])
        # chest: the gi top (a V at the neck shows skin) with a belt in the trim colour
        torso = [("main", sphere(0.2 * big, offset=V(0, 0, 0.3), scale=V(1.0, 0.62, 1.35), seg=16, rings=10)),
                 ("main", sphere(0.17 * big, offset=V(0, 0, 0.1), scale=V(1.0, 0.7, 0.8), seg=14, rings=8)),
                 ("skin", sphere(0.07, offset=V(0, 0.08, 0.47), scale=V(1.1, 1, 0.9), seg=10, rings=6)),
                 ("trim", cylinder(0.175 * big, 0.03, seg=18, offset=V(0, 0, 0.05))),
                 ("trim", bevel_box(0.03, 0.02, 0.1, 0.01, offset=V(0.06, 0.12, -0.03)))]
        if self.boss:
            torso.append(("main", sphere(0.1, offset=V(0, 0.08, 0.35), scale=V(2.2, 1.0, 1.1), seg=12, rings=6)))
        self.geo("waist", torso)
        # head: skin, hair and a headband
        name = self.design.get("model") or ""
        head = [("skin", cylinder(0.05, 0.05, seg=10, offset=V(0, 0, 0.04))),
                ("skin", sphere(0.11, offset=V(0, 0.01, 0.17), scale=V(0.92, 1.0, 1.15), seg=16, rings=10)),
                ("skin", sphere(0.03, offset=V(0, 0.115, 0.16), seg=8, rings=5)),
                ("trim", cylinder(0.104, 0.016, seg=18, offset=V(0, 0.01, 0.262)))]
        if name == "SHADE":  # a ninja mask with glowing eyes
            head[1] = ("main", sphere(0.115, offset=V(0, 0.01, 0.17), scale=V(0.95, 1.02, 1.17), seg=16, rings=10))
            head.append(("glow", bevel_box(0.07, 0.01, 0.012, 0.0, offset=V(0, 0.113, 0.185))))
        elif name == "KRAGG":  # a mohawk
            for k in range(6):
                head.append(("hair", cylinder(0.018, 0.06, seg=6, r_top=0.004, offset=V(0, 0.08 - k * 0.04, 0.33 - abs(k - 2.5) * 0.01))))
        else:
            head.append(("hair", sphere(0.115, offset=V(0, -0.02, 0.22), scale=V(0.98, 1.0, 0.8), seg=14, rings=8)))
            for k in range(5):  # spiky hair
                a = k * 1.25
                head.append(("hair", cylinder(0.03, 0.06, seg=6, r_top=0.0,
                                              offset=V(math.cos(a) * 0.05, -0.03 + math.sin(a) * 0.05, 0.33))))
            head.append(("trim", bevel_box(0.015, 0.1, 0.02, 0.005, offset=V(0.02, -0.17, 0.25))))  # headband tails
        if name != "SHADE":
            for x in (-0.04, 0.04):  # eyes
                head.append(("dark", sphere(0.014, offset=V(x, 0.1, 0.19), seg=8, rings=4)))
            head.append(("hair", bevel_box(0.07, 0.006, 0.008, 0.0, offset=V(0, 0.105, 0.215))))  # eyebrows
        self.geo("neck", head)
        # arms: gi sleeves, bare forearms with hand wraps, and fists
        for s in ("l", "r"):
            self.geo(s + "s", [("main", sphere(0.09 * big, offset=V(0, 0, 0.0), seg=12, rings=6)),
                               ("main", capsule(0.075 * big, UPPER, seg=12))])
            self.geo(s + "e", [("skin", capsule(0.055 * big, FORE * 0.9, seg=12)),
                               ("white", cylinder(0.06 * big, 0.05, seg=12, offset=V(0, 0, -FORE + 0.06)))])
            self.geo(s + "fist", [("skin", sphere(0.06 * big, offset=V(0, 0.01, -0.04), scale=V(0.9, 1.1, 1.0),
                                                  seg=12, rings=6)),
                                  ("white", bevel_box(0.055 * big, 0.06, 0.02, 0.015, offset=V(0, 0.01, 0.0)))])
        self.number_plate()

    # ---- posing ----
    def apply(self, p):
        n = self.nodes
        n["hips"].setZ(p["hz"])
        for j in JOINTS:
            n[j].setHpr(*p[j])
        self.lift = p["lift"]

    def show_label(self, on):
        """Hide the name tag (e.g. when the fight screen already shows the name)."""
        if self.tag is not None:
            self.tag.show() if on else self.tag.hide()

    def set_label(self, text, colour=(1, 1, 1, 1)):
        if self.tag is None:
            node = TextNode("tag")
            node.setAlign(TextNode.ACenter)
            node.setCardColor(0.03, 0.04, 0.06, 0.7)
            node.setCardAsMargin(0.35, 0.35, 0.18, 0.12)
            self.tag = self.root.attachNewNode(node)
            self.tag.setBillboardPointEye()
            self.tag.setScale(0.15)
            self.tag.setLightOff(1)
            self.tag.setShaderOff(1)
            self.tag.setDepthTest(False)
            self.tag.setDepthWrite(False)
            self.tag.setBin("fixed", 60)
            self.tag.setZ(2.05 * self.size + 0.2)
        self.tag.node().setText(text)
        self.tag.node().setTextColor(*colour)

    def update(self, s, dt):
        """s: this fighter's state from the server (pos, h, a, k, hu...)."""
        x, y, z = s["pos"]
        target = Point3(x, y, z)
        if self.pos is None or (self.pos - target).length() > 2.5:
            self.pos = Point3(target)
        else:
            self.pos += (target - self.pos) * min(1.0, dt * 20)
        dh = (s["h"] - self.h + 180) % 360 - 180
        self.h += dh if abs(dh) > 60 else dh * min(1.0, dt * 22)
        a, k = s.get("a", "idle"), s.get("k", 0.0)
        # the spin kick turns a full circle while it hits (smoothly here, between the server's updates)
        spin_to = 0.0 if a != "spin_kick" else 360.0 * max(0.0, min(1.0, k - 1.0))
        if spin_to < self.spin - 1:
            self.spin = spin_to if a == "spin_kick" else 0.0
        else:
            self.spin = min(spin_to, self.spin + 1400 * dt)
        want = anim_pose(a, k)
        rate = 40 if a in sim.MOVES else 18
        self.cur = blend(self.cur, want, 1 - math.exp(-dt * rate))
        self.apply(self.cur)
        lift = self.cur["lift"] * self.size
        self.root.setPos(self.pos.x, self.pos.y, self.pos.z + lift)
        self.root.setH(self.h + self.spin)
        # (user mod) the cartwheel kick: the body turns side-on and goes right over, about its middle
        if a == "cartwheel":
            over = cartwheel_turn(k)
            if self.wheel is None or over < self.wheel - 1:
                self.wheel = over
            else:  # (smoothly, between the server's updates)
                self.wheel = min(over, self.wheel + 900 * dt)
            mid = Vec3(0, 0, 0.9 * self.size)
            self.body.setHpr(90 * min(ease(k * 4), ease((3 - k) * 2.5)), 0, self.wheel)
            rise = 1 + 0.22 * math.sin(math.radians(self.wheel / 2)) ** 2  # (higher on the hands: the arms are up)
            self.body.setPos(mid * rise - self.body.getQuat().xform(mid))
        elif self.wheel is not None:
            self.wheel = None
            self.body.setPosHpr(0, 0, 0, 0, 0, 0)
        # energy in the hands while a blast charges
        charging = a == "blast" and k < 2.0
        for g in self.hand_glow:
            if charging:
                g.show()
                g.setScale(0.5 + 0.8 * min(1.0, k))
            else:
                g.hide()
        # a hit flash: bright for a moment
        hurt = s.get("hu", 9) < 0.12
        if hurt != self.flashing:
            self.flashing = hurt
            self.body.setColorScale((3.0, 2.6, 2.4, 1) if hurt else (1, 1, 1, 1))

    def chest_pos(self):
        return self.nodes["waist"].getPos(self.root.getParent()) + Vec3(0, 0, 0.3 * self.size)

    def head_pos(self):
        return self.nodes["neck"].getPos(self.root.getParent()) + Vec3(0, 0, 0.18 * self.size)

    def destroy(self):
        self.root.removeNode()
