"""Robot Wars graphics: PBR materials, arena lighting with reflections, the detailed arena, and robots.

Call init(base, quality) once, then build ArenaVisual and RobotVisual. The same classes work in the
single-player showcase (robot_wars.py) and in Robot Lab (lab_client.py).
quality: "low" (no shadows or surface detail: old laptops), "medium", "high".
"""
import math
import os
import random
import time

from panda3d.core import (AmbientLight, AntialiasAttrib, CardMaker, DirectionalLight, Filename, Material, PerspectiveLens,
                          Point3, Quat, SamplerState, Spotlight, TextNode, Texture, TextureStage,
                          TransparencyAttrib, Vec3)

import lab_sim as sim
import rw_textures
from rw_mesh import Mesh, bevel_box, cylinder, plate_y, prism

_state = {}


# ---------- materials ----------
class Materials:
    def __init__(self, loader, quality):
        rw_textures.ensure()
        self.loader, self.quality = loader, quality
        self.cache = {}
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
        """Give a part a PBR look: a texture set (paint, steel, diamond...) tinted by colour."""
        m = Material()
        m.setBaseColor((*(c ** 2.2 for c in colour), 1))  # screen colours (sRGB) to the linear colours lighting uses
        m.setRoughness(rough)
        m.setMetallic(metal)
        if emission:
            m.setEmission((*emission, 1))
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


# ---------- lighting ----------
def init(base, quality="high"):
    """Lights, reflections and the PBR pipeline. Returns the simplepbr pipeline."""
    import simplepbr
    _state["mats"] = Materials(base.loader, quality)
    base.setBackgroundColor(0.02, 0.02, 0.03)
    render = base.render
    sun = DirectionalLight("key")
    sun.setColor((1.5, 1.42, 1.3, 1))
    if quality != "low":
        size = 4096 if quality == "high" else 2048
        sun.setShadowCaster(True, size, size)
        sun.getLens().setFilmSize(26, 26)
        sun.getLens().setNearFar(5, 60)
    sun_np = render.attachNewNode(sun)
    sun_np.setPos(8, -14, 30)
    sun_np.lookAt(0, 0, 0)
    render.setLight(sun_np)
    # four spotlights on the corner towers, aimed at the middle of the arena
    for sx, sy, col in ((-1, -1, (1.0, 0.85, 0.7)), (1, -1, (0.75, 0.85, 1.0)),
                        (-1, 1, (0.75, 0.85, 1.0)), (1, 1, (1.0, 0.85, 0.7))):
        sp = Spotlight("spot")
        sp.setColor((*(c * 3.2 for c in col), 1))
        lens = PerspectiveLens()
        lens.setFov(38)
        sp.setLens(lens)
        sp.setAttenuation((1, 0, 0.004))
        np_ = render.attachNewNode(sp)
        np_.setPos(sx * 12.5, sy * 12.5, 8.5)
        np_.lookAt(sx * 2, sy * 2, 0)
        render.setLight(np_)
    amb = AmbientLight("fill")
    amb.setColor((0.05, 0.055, 0.07, 1))
    render.setLight(render.attachNewNode(amb))
    env = None
    try:
        cube = base.loader.loadCubeMap(Filename.fromOsSpecific(os.path.join(rw_textures.TEX, "env_#.png")))
        env = simplepbr.EnvMap(cube, prefiltered_size=64, prefiltered_samples=16, blocking_prepare=True)
    except Exception:
        env = None
    pipeline = simplepbr.init(msaa_samples=4 if quality != "low" else 0, max_lights=8,
                              use_normal_maps=quality != "low", use_occlusion_maps=quality != "low",
                              enable_shadows=quality != "low", exposure=0.7, env_map=env)
    render.setAntialias(AntialiasAttrib.MMultisample)
    _state["quality"] = quality
    return pipeline


# ---------- the arena ----------
PAINT_RED, PAINT_YELLOW = (0.6, 0.08, 0.06), (0.95, 0.7, 0.05)


class ArenaVisual:
    def __init__(self, parent, hazards, look=None, user_mods=None):
        """user_mods: the teacher's user mods (lab_sim.USER_MODS), e.g. no_cage."""
        look = look or {}
        no_cage = sim.user_mods_on(user_mods)["no_cage"]
        wall_colour = tuple(v / 255 for v in look.get("wall_colour", (155, 25, 20)))
        arena_name = str(look.get("name", "ROBOT LAB"))
        self.root = parent.attachNewNode("arena_visual")
        static = self.root.attachNewNode("static")
        A, h = sim.Arena, sim.ARENA / 2
        px, py, ps = A.PIT
        rnd = random.Random(3)

        # floor: diamond plate, with holes for the pit and the floor flipper (the same rectangles as the physics)
        floor = Mesh(tile=0.6)
        for x0, y0, x1, y1 in sim.floor_rects(hazards):
            bevel_box((x1 - x0) / 2, (y1 - y0) / 2, 0.25, 0.01, mesh=floor, offset=Vec3((x0 + x1) / 2, (y0 + y1) / 2, -0.25))
        part(static, floor, "diamond", rough=1.0, metal=1.0)
        # painted markings: the corner patrol zones (house robots), start squares, centre circle
        cz = sim.CPZ / 2
        for sx in (-1, 1):
            for sy in (-1, 1):
                part(static, bevel_box(cz, cz, 0.004, 0.0, tile=0.8), "hazard", rough=1, metal=0,
                     pos=(sx * (h - cz), sy * (h - cz), 0.004))
                part(static, bevel_box(cz - 0.25, cz - 0.25, 0.004, 0.0), None, colour=(0.12, 0.12, 0.13), rough=0.9,
                     metal=0.3, pos=(sx * (h - cz), sy * (h - cz), 0.006))
        start_cols = [(0.9, 0.25, 0.2), (0.25, 0.55, 1.0), (0.3, 0.85, 0.4), (1.0, 0.8, 0.2), (0.8, 0.4, 1.0), (1, 0.5, 0.2)]
        for (sx, sy, _), col in zip(A.STARTS, start_cols):
            for dx, dy, hx, hy in ((0, 1.1, 1.2, 0.07), (0, -1.1, 1.2, 0.07), (1.1, 0, 0.07, 1.2), (-1.1, 0, 0.07, 1.2)):
                part(static, bevel_box(hx, hy, 0.004, 0.0), None, colour=col, rough=0.6, metal=0,
                     pos=(sx + dx, sy + dy, 0.005))
        for i in range(48):
            a = 2 * math.pi * i / 48
            part(static, bevel_box(0.17, 0.05, 0.004, 0.0), None, colour=PAINT_YELLOW, rough=0.6, metal=0,
                 pos=(math.cos(a) * 3, math.sin(a) * 3, 0.005), hpr=(math.degrees(a) + 90, 0, 0))
        logo = TextNode("logo")
        logo.setText(arena_name)
        logo.setAlign(TextNode.ACenter)
        logo_np = static.attachNewNode(logo)
        logo_np.setPos(0, -0.45, 0.012)
        logo_np.setHpr(0, -90, 0)
        logo_np.setScale(1.2)
        mats().apply(logo_np, None, PAINT_YELLOW, 0.5, 0)

        gw, deep = A.GUTTER, -A.PIT_OPEN_Z
        edge = gw if no_cage else 0.5  # (how far the arena's edge reaches beyond the floor)
        if no_cage:  # the No cage user mod: a drop all around the edge (painted sides, a dark gutter floor)
            sides, gutter = Mesh(tile=0.5), Mesh(tile=0.6)
            for cx, cy, hx, hy in ((0, h + 0.05, h + 0.1, 0.05), (0, -h - 0.05, h + 0.1, 0.05),
                                   (h + 0.05, 0, 0.05, h), (-h - 0.05, 0, 0.05, h)):
                bevel_box(hx, hy, deep / 2, 0.0, mesh=sides, offset=Vec3(cx, cy, -deep / 2))
            for cx, cy, hx, hy in ((0, h + gw / 2, h + gw, gw / 2), (0, -h - gw / 2, h + gw, gw / 2),
                                   (h + gw / 2, 0, gw / 2, h), (-h - gw / 2, 0, gw / 2, h)):
                bevel_box(hx, hy, 0.05, 0.0, mesh=gutter, offset=Vec3(cx, cy, -deep - 0.05))
            part(static, sides, "paint", colour=wall_colour, rough=1.0, metal=1.0)
            part(static, gutter, "steel", colour=(0.12, 0.12, 0.13), rough=1.0, metal=1.0)
        else:  # walls: red kick-plates, steel rail and posts, clear screens
            wall = Mesh(tile=0.5)
            rail = Mesh(tile=1.0)
            for cx, cy, hx, hy in ((0, h + 0.25, h + 0.5, 0.25), (0, -h - 0.25, h + 0.5, 0.25),
                                   (h + 0.25, 0, 0.25, h), (-h - 0.25, 0, 0.25, h)):
                bevel_box(hx, hy, 0.6, 0.04, mesh=wall, offset=Vec3(cx, cy, 0.6))
                bevel_box(hx + 0.03, hy + 0.03, 0.05, 0.02, mesh=rail, offset=Vec3(cx, cy, 1.25))
            for k in range(-5, 6):
                for x, y in ((k * 2, h + 0.25), (k * 2, -h - 0.25), (h + 0.25, k * 2), (-h - 0.25, k * 2)):
                    cylinder(0.07, 1.65, mesh=rail, offset=Vec3(x, y, 2.9), seg=12)
            part(static, wall, "paint", colour=wall_colour, rough=1.0, metal=1.0)
            part(static, rail, "steel", rough=1.0, metal=1.0)
            screens = self.root.attachNewNode("screens")
            glass = Mesh()
            for cx, cy, hx, hy in ((0, h + 0.25, h + 0.5, 0.02), (0, -h - 0.25, h + 0.5, 0.02),
                                   (h + 0.25, 0, 0.02, h), (-h - 0.25, 0, 0.02, h)):
                bevel_box(hx, hy, 1.6, 0.0, mesh=glass, offset=Vec3(cx, cy, 2.9))
            g = part(screens, glass, None, colour=(0.6, 0.75, 0.9), rough=0.05, metal=0.0)
            g.setTransparency(TransparencyAttrib.MAlpha)
            g.setAlphaScale(0.1)
            screens.setBin("transparent", 10)
            screens.setDepthWrite(False)

        # corner towers with lamps, and an overhead lighting rig
        towers, lamps = Mesh(), Mesh()
        for sx in (-1, 1):
            for sy in (-1, 1):
                x, y = sx * 12.5, sy * 12.5
                bevel_box(0.25, 0.25, 4.3, 0.03, mesh=towers, offset=Vec3(x, y, 4.3))
                bevel_box(0.5, 0.5, 0.35, 0.05, mesh=towers, offset=Vec3(x - sx * 0.3, y - sy * 0.3, 8.6))
                cylinder(0.32, 0.05, mesh=lamps, offset=Vec3(x - sx * 0.62, y - sy * 0.62, 8.5), seg=20)
        truss, rig_lamps = Mesh(), Mesh()
        for k in (-1, 1):  # truss beams
            bevel_box(13, 0.15, 0.15, 0.02, mesh=truss, offset=Vec3(0, k * 12.5, 9.2))
            bevel_box(0.15, 13, 0.15, 0.02, mesh=truss, offset=Vec3(k * 12.5, 0, 9.2))
        for i in range(-3, 4):
            bevel_box(0.1, 12.5, 0.1, 0.02, mesh=truss, offset=Vec3(i * 3.2, 0, 9.3))
            for j in (-6, -2, 2, 6):
                bevel_box(0.35, 0.2, 0.08, 0.02, mesh=rig_lamps, offset=Vec3(i * 3.2, j, 9.15))
        part(static, towers, "steel", colour=(0.25, 0.26, 0.28), rough=1.0, metal=1.0)
        part(static, lamps, None, colour=(1, 1, 1), rough=0.3, metal=0, emission=(6, 5.6, 5))
        # the overhead rig is its own node: the full arena camera looks down past it, so it hides it
        self.rig = self.root.attachNewNode("lighting_rig")
        part(self.rig, truss, "steel", colour=(0.25, 0.26, 0.28), rough=1.0, metal=1.0)
        part(self.rig, rig_lamps, None, colour=(1, 1, 1), rough=0.3, metal=0, emission=(6, 5.6, 5))
        self.rig.flattenStrong()

        # outside: concrete floor, tiered stands and a crowd (one mesh, coloured per person)
        outside = Mesh(tile=0.3)
        far = 30
        for cx, cy, hx, hy in ((0, h + edge + far / 2, h + far, far / 2), (0, -h - edge - far / 2, h + far, far / 2),
                               (h + edge + far / 2, 0, far / 2, h + edge), (-h - edge - far / 2, 0, far / 2, h + edge)):
            bevel_box(hx, hy, 0.05, 0.0, mesh=outside, offset=Vec3(cx, cy, -0.05))
        if no_cage:
            for cx, cy, hx, hy in ((0, h + gw, h + gw, 0.02), (0, -h - gw, h + gw, 0.02),
                                   (h + gw, 0, 0.02, h + gw), (-h - gw, 0, 0.02, h + gw)):  # the gutter's outer side
                bevel_box(hx, hy, deep / 2, 0.0, mesh=outside, offset=Vec3(cx, cy, -deep / 2))
        stands = Mesh(tile=0.5)
        crowd = Mesh(colours=True)
        shirt = [(0.8, 0.1, 0.1), (0.1, 0.3, 0.8), (0.9, 0.8, 0.2), (0.2, 0.6, 0.3), (0.9, 0.9, 0.9),
                 (0.15, 0.15, 0.18), (0.9, 0.5, 0.1), (0.5, 0.2, 0.6)]
        for side in range(4):
            for row in range(4):
                d = h + 3.2 + row * 1.3
                z = 0.35 + row * 0.55
                for i in range(-12, 13):
                    along = i * 1.0 + (0.5 if row % 2 else 0)
                    x, y = [(along, d), (along, -d), (d, along), (-d, along)][side]
                    if look.get("crowd", True) and rnd.random() < 0.85:
                        crowd.colour = (*rnd.choice(shirt), 1)
                        tall = rnd.uniform(0.22, 0.3)
                        bevel_box(0.19, 0.13, tall, 0.06, mesh=crowd, offset=Vec3(x, y, z * 2 + tall))
                        crowd.colour = (*rnd.choice([(0.85, 0.65, 0.5), (0.6, 0.42, 0.3), (0.4, 0.28, 0.2)]), 1)
                        bevel_box(0.08, 0.08, 0.09, 0.04, mesh=crowd, offset=Vec3(x, y, z * 2 + tall * 2 + 0.1))
                cx, cy, hx, hy = [(0, d, h + 3, 0.65), (0, -d, h + 3, 0.65), (d, 0, 0.65, h + 3), (-d, 0, 0.65, h + 3)][side]
                bevel_box(hx, hy, z, 0.02, mesh=stands, offset=Vec3(cx, cy, z))
        part(static, outside, "concrete", rough=1.0, metal=0.0)
        part(static, stands, "concrete", colour=(0.5, 0.55, 0.65), rough=1.0, metal=0.0)
        part(static, crowd, None, colour=(0.45, 0.45, 0.45), rough=0.9, metal=0.0)  # dim: the stands are in shadow

        # a big screen for the score
        screen = Mesh()
        bevel_box(4, 0.3, 1.4, 0.05, mesh=screen)
        scr = part(static, screen, "steel", colour=(0.1, 0.1, 0.12), pos=(0, h + 7.5, 6.5))
        self.scoreboard = TextNode("score")
        self.scoreboard.setAlign(TextNode.ACenter)
        self.scoreboard.setText(arena_name)
        sb = self.root.attachNewNode(self.scoreboard)
        sb.setPos(0, h + 7.15, 6.6)
        sb.setScale(0.9)
        mats().apply(sb, None, (0, 0, 0), 1, 0, emission=(3, 2.4, 0.4))
        del scr

        # hazards
        self.pit_lights = self.pit_lid = None
        # the drop zone: a shaft with a floor that lowers when it's switched on (open)
        shaft = Mesh(tile=0.6)
        for dx, dy, hx, hy in ((0, ps / 2 + 0.05, ps / 2 + 0.1, 0.05), (0, -ps / 2 - 0.05, ps / 2 + 0.1, 0.05),
                               (ps / 2 + 0.05, 0, 0.05, ps / 2), (-ps / 2 - 0.05, 0, 0.05, ps / 2)):
            bevel_box(hx, hy, 1.6, 0.0, mesh=shaft, offset=Vec3(px + dx, py + dy, -1.6))
        part(static, shaft, "steel", colour=(0.12, 0.12, 0.13), rough=1.0, metal=1.0)
        rim = Mesh(tile=0.8)
        for dx, dy, hx, hy in ((0, ps / 2 + 0.2, ps / 2 + 0.35, 0.15), (0, -ps / 2 - 0.2, ps / 2 + 0.35, 0.15),
                               (ps / 2 + 0.2, 0, 0.15, ps / 2 + 0.05), (-ps / 2 - 0.2, 0, 0.15, ps / 2 + 0.05)):
            bevel_box(hx, hy, 0.006, 0.0, mesh=rim, offset=Vec3(px + dx, py + dy, 0.006))
        part(static, rim, "hazard", rough=1.0, metal=0.0)
        glow = Mesh()
        for dx, dy, hx, hy in ((0, ps / 2, ps / 2, 0.02), (0, -ps / 2, ps / 2, 0.02),
                               (ps / 2, 0, 0.02, ps / 2), (-ps / 2, 0, 0.02, ps / 2)):
            bevel_box(hx, hy, 0.02, 0.0, mesh=glow, offset=Vec3(px + dx, py + dy, -0.15))
        self.pit_lights = part(self.root, glow, None, (0, 0, 0), 1, 0, emission=(4, 0.3, 0.1))
        self.pit_lid = self.root.attachNewNode("pit_lid")
        part(self.pit_lid, bevel_box(ps / 2 - 0.03, ps / 2 - 0.03, 0.25, 0.01, tile=0.6), "diamond",
             colour=(0.75, 0.75, 0.78), rough=1.0, metal=1.0, pos=(0, 0, -0.25))
        border = Mesh(tile=0.8)
        q = ps / 2 - 0.03
        for dx, dy, hx, hy in ((0, q - 0.1, q, 0.1), (0, -q + 0.1, q, 0.1), (q - 0.1, 0, 0.1, q - 0.2),
                               (-q + 0.1, 0, 0.1, q - 0.2)):
            bevel_box(hx, hy, 0.004, 0.0, mesh=border, offset=Vec3(dx, dy, 0.004))
        part(self.pit_lid, border, "hazard", rough=1.0, metal=0.0)
        self.pit_lid.flattenStrong()
        self.pit_lid.setPos(px, py, 0)
        self.spikes = None
        # a bank of spikes that shoots out of the wall and back in (rests inside the wall when off; with the
        # No cage user mod there's no wall, so no spikes)
        wx, y0, y1 = A.SPIKES
        self.spikes = self.root.attachNewNode("spikes")
        if no_cage:
            self.spikes.hide()
        part(self.spikes, bevel_box(0.3, (y1 - y0) / 2 + 0.1, 0.42, 0.03, tile=1.0), "steel",
             (0.35, 0.36, 0.38), rough=1.0, metal=1.0)
        spikes = Mesh()
        y = y0
        while y <= y1 + 1e-6:
            for z in (-0.2, 0.2):
                cylinder(0.09, 0.11, axis="x", mesh=spikes, offset=Vec3(0.41, y - (y0 + y1) / 2, z), seg=12,
                         r_top=0.0)
            y += 0.5
        part(self.spikes, spikes, "steel", (0.85, 0.85, 0.9), rough=1.0, metal=1.0)
        self.spikes.flattenStrong()  # (flattening bakes in the node's position, so it is placed after)
        self.spikes.setPos(A.spike_x(0.0), (y0 + y1) / 2, 0.45)
        if not no_cage:
            part(static, bevel_box(0.02, (y1 - y0) / 2 + 0.3, 0.45, 0.0, tile=0.8), "hazard", rough=1, metal=0,
                 pos=(wx + 0.01, (y0 + y1) / 2, 0.55))
        self.saws = []
        # floor saws (rest down in their slots when off)
        for sx, sy in A.SAWS:
            self.saws.append(self.build_saw(static, sx, sy))
        self.floor_flipper = None
        # a plate that sits flush in the floor, in a dark recess (lies flat when off)
        fx, fy = A.FLOOR_FLIPPER
        ff = A.FF_HALF
        part(static, bevel_box(1.5, 1.0, 0.02, 0.0), None, (0.02, 0.02, 0.02), 0.9, 0, pos=(fx, fy, -0.19))
        frame = Mesh()
        for dx, dy, hx, hy in ((0, 1.03, 1.56, 0.03), (0, -1.03, 1.56, 0.03), (1.53, 0, 0.03, 1.0),
                               (-1.53, 0, 0.03, 1.0)):
            bevel_box(hx, hy, 0.005, 0.0, mesh=frame, offset=Vec3(fx + dx, fy + dy, 0.005))
        part(static, frame, "steel", (0.15, 0.15, 0.16), rough=1.0, metal=1.0)
        self.floor_flipper = self.root.attachNewNode("floor_flipper_visual")
        self.floor_flipper.setPos(fx, fy - 1.0, -ff.z)
        part(self.floor_flipper, bevel_box(ff.x, ff.y, ff.z, 0.015, tile=0.8), "hazard", rough=1.0, metal=0.0,
             pos=(0, 1.0, 0))
        for s in (-1, 1):  # hinge knuckles along the back edge
            part(self.floor_flipper, cylinder(0.06, 0.25, axis="x", seg=14), "steel", (0.3, 0.3, 0.32),
                 pos=(s * 0.9, 0.05, 0.0))
        self.ff_light = part(self.root, cylinder(0.12, 0.08, seg=16), None, (0.05, 0, 0), 0.4, 0,
                             emission=(0.2, 0, 0), pos=(fx - 1.9, fy - 1.2, 0.08))
        static.flattenStrong()  # one draw call per material: fast on low-spec laptops

    def build_saw(self, static, sx, sy):
        """A floor saw: a slotted steel housing, and a blade with hooked carbide-tipped teeth, expansion
        slots and a bolted hub. A see-through blur disc shows when it spins; the rim glows when it grinds."""
        R = sim.Arena.SAW_R
        # the slot: a black gap in a bolted steel cover plate, edged with warning lights
        part(static, bevel_box(1.25, 0.34, 0.012, 0.004, tile=1.2), "steel", (0.3, 0.3, 0.32), rough=1.0, metal=1.0,
             pos=(sx, sy, 0.0))
        part(static, bevel_box(1.12, 0.05, 0.004, 0.0), None, (0.01, 0.01, 0.01), 1.0, 0, pos=(sx, sy, 0.013))
        bolts = Mesh()
        for bx in (-1.15, -0.4, 0.4, 1.15):
            for by in (-0.26, 0.26):
                cylinder(0.022, 0.006, seg=8, mesh=bolts, offset=Vec3(sx + bx, sy + by, 0.016))
        part(static, bolts, "steel", (0.6, 0.6, 0.62), rough=1.0, metal=1.0)
        for side in (-1, 1):
            part(static, bevel_box(1.1, 0.025, 0.006, 0.0), None, (0, 0, 0), 1, 0, emission=(3, 1.2, 0.1),
                 pos=(sx, sy + side * 0.14, 0.014))
        saw = self.root.attachNewNode("saw")
        saw.setPos(sx, sy, sim.Arena.saw_z(0.0))
        spin = saw.attachNewNode("spin")
        # the blade body with a darker, ground inner ring and a bolted hub
        part(spin, cylinder(R * 0.93, 0.012, axis="y", seg=64, tile=2.0), "steel", (0.78, 0.8, 0.84), rough=1.0,
             metal=1.0)
        part(spin, cylinder(R * 0.42, 0.016, axis="y", seg=40), "steel", (0.45, 0.46, 0.5), rough=1.0, metal=1.0)
        part(spin, cylinder(0.16, 0.04, axis="y", seg=24, bevel=0.01), "steel", (0.2, 0.2, 0.22), rough=1.0, metal=1.0)
        bolts = Mesh()
        for k in range(6):
            a = 2 * math.pi * k / 6
            cylinder(0.018, 0.05, axis="y", seg=8, mesh=bolts, offset=Vec3(math.cos(a) * 0.1, 0, math.sin(a) * 0.1))
        part(spin, bolts, "steel", (0.7, 0.7, 0.72), rough=1.0, metal=1.0)
        # laser-cut expansion slots (dark lines from the rim towards the middle)
        slots = Mesh()
        for k in range(6):
            a = 2 * math.pi * (k + 0.5) / 6
            plate_y([(-0.012, R * 0.62), (0.012, R * 0.62), (0.012, R * 0.9), (-0.012, R * 0.9)], 0.0135, mesh=slots,
                    angle=a)
        part(spin, slots, None, (0.03, 0.03, 0.03), 0.8, 0.2)
        # 36 hooked teeth, each with a darker carbide tip
        teeth, tips = Mesh(tile=3.0), Mesh()
        n = 36
        for k in range(n):
            a = 2 * math.pi * k / n
            plate_y([(-0.075, R * 0.9), (0.06, R * 0.9), (0.075, R * 1.02), (0.035, R * 1.09), (-0.02, R * 0.97)],
                    0.012, mesh=teeth, angle=a)
            plate_y([(0.035, R * 1.0), (0.075, R * 1.02), (0.042, R * 1.1), (0.03, R * 1.07)], 0.018, mesh=tips,
                    angle=a)
        part(spin, teeth, "steel", (0.7, 0.72, 0.76), rough=1.0, metal=1.0)
        part(spin, tips, "steel", (0.18, 0.18, 0.2), rough=1.0, metal=1.0)
        spin.flattenStrong()
        blur = part(saw, cylinder(R * 1.1, 0.022, axis="y", seg=64), None, (0.55, 0.57, 0.62), 0.3, 1.0)
        blur.setTransparency(TransparencyAttrib.MAlpha)
        blur.setDepthWrite(False)
        blur.setBin("transparent", 5)
        glow = part(saw, cylinder(R * 1.04, 0.02, axis="y", seg=64, caps=False), None, (0, 0, 0), 1, 0,
                    emission=(3.5, 1.2, 0.2))  # hot rim when grinding
        glow.hide()
        return saw, spin, blur, glow

    def update(self, hz):
        """hz: the arena's hazard_state(): saw heights, flipper angle, pit floor, spikes, time."""
        t = hz["t"]
        hot = hz.get("saw_hot") or [0] * len(self.saws)
        for (saw, spin, blur, glow), height, grinding in zip(self.saws, hz["saws"], hot):
            saw.setZ(sim.Arena.saw_z(height))
            speed = 400 + 1400 * min(1.0, height * 2)  # spins up as it rises (degrees per second)
            spin.setR(-((t * speed) % 360) * sim.Arena.SAW_SPIN)
            blur.setAlphaScale(min(0.22, height * 0.3))
            glow.show() if grinding else glow.hide()
        if self.floor_flipper is not None and hz.get("ff") is not None:
            self.floor_flipper.setQuat(Quat(*hz["ff"]))
            warn = hz.get("on", {}).get("floor_flipper", True) and (t % 4.0) > 3.2  # blinks just before it fires
            m = self.ff_light.getMaterial()
            m.setEmission((8, 0.3, 0.1, 1) if warn and int(t * 8) % 2 == 0 else (0.2, 0, 0, 1))
        if self.spikes is not None:
            self.spikes.setX(sim.Arena.spike_x(hz.get("spikes", 0.0)))
        if self.pit_lid is not None and hz.get("pit") is not None:
            self.pit_lid.setZ(hz["pit"])
            m = self.pit_lights.getMaterial()
            if hz.get("pit_open", True):
                pulse = 2.5 + 1.5 * math.sin(t * 4)
                m.setEmission((pulse * 1.6, pulse * 0.12, pulse * 0.04, 1))
            else:
                m.setEmission((0.05, 0.3, 0.08, 1))  # closed: a calm green

    def set_score(self, text):
        self.scoreboard.setText(text)


# ---------- robots ----------
class HitBar:
    """A small health bar that floats over one part of a robot for a moment after that part is hit."""

    def __init__(self, parent, text, width):
        self.np = parent.attachNewNode("hitbar")
        self.np.setBillboardPointEye()
        self.np.setLightOff(1)
        self.np.setShaderOff(1)
        self.np.setDepthTest(False)
        self.np.setDepthWrite(False)
        cm = CardMaker("bar")
        cm.setFrame(-width / 2 - 0.02, width / 2 + 0.02, -0.05, 0.05)
        back = self.np.attachNewNode(cm.generate())
        back.setColor(0.04, 0.04, 0.06, 1)
        back.setBin("fixed", 61)
        cm.setFrame(0, width, -0.035, 0.035)
        self.fill = self.np.attachNewNode(cm.generate())
        self.fill.setX(-width / 2)
        self.fill.setBin("fixed", 62)
        label = TextNode("part")
        label.setText(text)
        label.setAlign(TextNode.ALeft)
        label.setTextColor(1, 1, 1, 1)
        label.setShadow(0.06, 0.06)
        tnp = self.np.attachNewNode(label)
        tnp.setScale(0.085)
        tnp.setPos(-width / 2 - 0.02, 0, 0.07)
        tnp.setBin("fixed", 63)
        self.np.hide()

    def show(self, pos, health, now):
        self.np.show()
        self.np.setPos(pos)
        self.fill.setSx(max(0.001, health))
        if health > 0.6:
            colour = (0.3, 0.9, 0.35, 1)
        elif health > 0.3:
            colour = (1.0, 0.8, 0.15, 1)
        else:  # breaking: red, and it flickers
            colour = (1.0, 0.2, 0.15, 1) if int(now * 8) % 2 else (0.6, 0.1, 0.08, 1)
        self.fill.setColor(*colour)

    def hide(self):
        self.np.hide()


class RobotVisual:
    """A detailed robot built from a design: painted armour, rivets, tyres, lights and its weapon."""

    def __init__(self, parent, design):
        size = sim.design_size(design)
        model = design.get("model") if design.get("model") in sim.HOUSE_BY_NAME else None
        weapon = sim.HOUSE_BY_NAME[model][0] if model else design["weapon"]
        sh = sim.shapes(weapon, size)
        style = design.get("style", {})
        colour = tuple(v / 255 for v in design["colour"])
        trim = tuple(v / 255 for v in style.get("trim", (30, 30, 34)))
        lights = tuple(v / 255 * 6 for v in style.get("lights", (255, 60, 30)))
        self.root = parent.attachNewNode("robot")
        self.chassis = self.root.attachNewNode("chassis")
        self.house = bool(design.get("house")) or model is not None  # house robot styling and big wheels
        self.weapon_kind = weapon
        self.shape = sh
        self.wheel_r = sim.HOUSE_WHEEL_R if self.house else sim.WHEEL_R
        h = sh["half"]
        self.front = h.y  # how far the nose is from the middle (for the first person camera)
        z0, top = sim.CHASSIS_Z, sim.CHASSIS_Z + h.z
        # body: a chunky bevelled hull, a raised armour deck and side skirts
        part(self.chassis, bevel_box(h.x, h.y, h.z, 0.06, tile=1.2), "paint", colour, pos=(0, 0, z0))
        # armour: bolted-on panels, each on a hinge edge, so under real damage they bend, rattle and come off
        self.armour = self.chassis.attachNewNode("armour")
        self.panels = []
        deck = self.panel((0, -h.y * 0.8, top + 0.04), (0, 28, 0), (0, 0))  # hinged at its back edge: the front lifts
        part(deck, bevel_box(h.x * 0.78, h.y * 0.72, 0.045, 0.03, tile=1.2), "paint", trim, pos=(0, h.y * 0.72, 0))
        rivets = Mesh()  # rivets round the deck
        for i in range(8):
            for s in (-1, 1):
                cylinder(0.018, 0.008, mesh=rivets, seg=8,
                         offset=Vec3(s * h.x * 0.72, h.y * 0.18 + i * h.y * 0.16, 0.05))
        part(deck, rivets, "steel", rough=1.0, metal=1.0)
        self.deck = deck
        hinge_z = z0 - 0.02 + h.z * 0.7
        for s in (-1, 1):  # side skirts, hinged at the top: the bottom swings out
            skirt = self.panel((s * (h.x + 0.02), 0, hinge_z), (0, 0, s * 34), (0, s * 90))
            part(skirt, bevel_box(0.03, h.y * 0.9, h.z * 0.7, 0.012, tile=1.5), "steel", (0.35, 0.36, 0.38),
                 pos=(0, 0, -h.z * 0.7))
            if self.house:  # warning stripes on the skirts
                part(skirt, bevel_box(0.02, h.y * 0.8, h.z * 0.45, 0.01, tile=0.8), "hazard", rough=1, metal=0,
                     pos=(s * 0.025, 0, z0 + h.z * 0.2 - hinge_z))
        rear = self.panel((0, -h.y - 0.018, top - 0.03), (0, -34, 0), (-90, 0))  # the back plate, with the rear light bar
        part(rear, bevel_box(h.x * 0.72, 0.012, h.z * 0.55, 0.008, tile=1.5), "steel", (0.3, 0.3, 0.33),
             pos=(0, 0, -h.z * 0.55))
        part(rear, bevel_box(h.x * 0.6, 0.012, 0.02, 0.006), None, (0, 0, 0), 0.3, 0,
             emission=(4, 0.2, 0.1), pos=(0, -0.01, z0 + h.z * 0.3 - (top - 0.03)))
        # glowing eyes at the front
        self.eyes = part(self.chassis, bevel_box(h.x * 0.5, 0.012, 0.025, 0.006), None, (0, 0, 0), 0.3, 0,
                         emission=lights, pos=(0, h.y + 0.005, z0 + h.z * 0.45))
        # antenna with a tip light
        part(self.chassis, cylinder(0.008, 0.18, seg=6), "steel", pos=(-h.x * 0.6, -h.y * 0.7, top + 0.24))
        part(self.chassis, cylinder(0.022, 0.022, seg=10), None, (0, 0, 0), 0.3, 0, emission=lights,
             pos=(-h.x * 0.6, -h.y * 0.7, top + 0.43))
        self.beacon = None
        if self.house:  # house robots: armour plates, warning stripes, grab handles and a flashing beacon
            for sx_ in (-1, 1):
                part(self.chassis, bevel_box(0.03, 0.03, 0.12, 0.01), "steel", (0.3, 0.3, 0.32),
                     pos=(sx_ * h.x * 0.5, -h.y - 0.04, top - 0.05))
            plates = Mesh(tile=1.0)  # (bolted to the deck: they come off with it)
            for i in range(3):
                bevel_box(h.x * 0.36, h.y * 0.2, 0.03, 0.012, mesh=plates,
                          offset=Vec3(0, h.y * 0.35 + i * h.y * 0.45, 0.06))
            part(self.deck, plates, "steel", (0.4, 0.4, 0.42), rough=1.0, metal=1.0)
            part(self.chassis, cylinder(0.1, 0.05, seg=16), "steel", (0.2, 0.2, 0.22), pos=(h.x * 0.55, -h.y * 0.55, top + 0.14))
            self.beacon = part(self.chassis, cylinder(0.08, 0.07, seg=16, bevel=0.02), None, (0, 0, 0), 0.3, 0,
                               emission=(6, 3, 0), pos=(h.x * 0.55, -h.y * 0.55, top + 0.26))
        # name on the deck
        tn = TextNode("name")
        tn.setText(str(style.get("number", design["name"]))[:10].upper())
        tn.setAlign(TextNode.ACenter)
        tnp = self.deck.attachNewNode(tn)  # (painted on the deck)
        tnp.setPos(0, h.y * 0.68, 0.048)
        tnp.setHpr(0, -90, 0)
        tnp.setScale(min(0.2, 1.2 * h.x / max(3, len(tn.getText()))))
        mats().apply(tnp, None, (1, 1, 1), 0.5, 0, emission=(0.6, 0.6, 0.6))
        # wheels: tyres with tread and steel hubs
        self.wheels = []
        for x, y in sim.WHEELS:
            w = self.root.attachNewNode("wheel")
            spin = w.attachNewNode("spin")
            wr, ww = self.wheel_r, 0.075 * (1.6 if self.house else 1.0)
            part(spin, cylinder(wr, ww, axis="x", seg=28, bevel=0.03, tile=2.5), "tyre", rough=1.0, metal=0.0)
            hub = Mesh()
            cylinder(wr * 0.55, ww + 0.005, axis="x", seg=18, bevel=0.01, mesh=hub)
            for k in range(5):
                a = 2 * math.pi * k / 5
                cylinder(0.014, ww + 0.01, axis="x", seg=6, mesh=hub,
                         offset=Vec3(0, math.cos(a) * wr * 0.3, math.sin(a) * wr * 0.3))
            part(spin, hub, "steel", (0.7, 0.7, 0.72), rough=1.0, metal=1.0)
            self.wheels.append((w, spin, x * size, y * size))
            w.setPythonTag("width", ww)
        # weapon
        self.weapon = self.root.attachNewNode("weapon")
        self.blur = None
        if weapon == "wedge":
            p = sh["plate"]
            L = p.y * 2
            part(self.weapon, prism([(0, -0.03), (L, -0.03), (L, 0.0), (0.05, 0.05)], p.x, tile=1.2), "paint",
                 trim, rough=1.0, metal=1.0)
            part(self.weapon, prism([(L - 0.12, -0.03), (L, -0.03), (L, 0.0), (L - 0.12, 0.012)], p.x - 0.01, tile=1.5),
                 "hazard", rough=1.0, metal=0.0)
            part(self.weapon, cylinder(0.05, p.x * 0.95, axis="x", seg=16), "steel", trim, rough=1.0, metal=1.0)
            for s in (-1, 1):
                part(self.chassis, prism([(0, 0), (h.y * 0.9, 0), (h.y * 0.9, 0.05), (0.1, 0.16)], 0.025), "paint",
                     colour, pos=(s * (h.x - 0.03), 0, top - 0.05))
        elif weapon == "spinner":
            b = sh["bar"]
            part(self.weapon, bevel_box(b.x, b.y, b.z, 0.02, tile=1.5), "steel", (0.7, 0.72, 0.76), rough=1.0, metal=1.0)
            for s in (-1, 1):
                part(self.weapon, bevel_box(0.09, 0.1, 0.07, 0.015), "steel", (0.25, 0.25, 0.27), rough=1.0, metal=1.0,
                     pos=(s * (b.x - 0.07), s * 0.03, 0))
            part(self.weapon, cylinder(0.11, 0.075, seg=20, bevel=0.01), "steel", trim, rough=1.0, metal=1.0)
            for s in (-1, 1):  # support forks from the body
                part(self.chassis, bevel_box(0.06, 0.22, 0.05, 0.015), "steel", (0.3, 0.3, 0.32),
                     pos=(s * 0.15, h.y + 0.12, z0 + 0.1))
            blur = Mesh()
            cylinder(b.x, 0.004, seg=48, mesh=blur)
            self.blur = part(self.weapon.getParent(), blur, None, (0.8, 0.82, 0.86), 0.2, 1.0)
            self.blur.setTransparency(TransparencyAttrib.MAlpha)
            self.blur.setDepthWrite(False)
            self.blur.setBin("transparent", 5)
            self.blur_axis = "z"
        elif weapon == "drum":
            r, half_len = sh["drum"]
            part(self.weapon, cylinder(r, half_len, axis="x", seg=24, bevel=0.02, tile=2.0), "steel", (0.6, 0.62, 0.66),
                 rough=1.0, metal=1.0)
            for t in range(6):
                a = 360 * t / 6
                tooth = part(self.weapon, bevel_box(0.05, 0.035, 0.06, 0.01), "steel", (0.25, 0.25, 0.27),
                             rough=1.0, metal=1.0)
                tooth.setP(a)
                tooth.setPos(tooth, 0, 0, r + 0.02)
            for s in (-1, 1):
                part(self.chassis, bevel_box(0.04, 0.22, 0.09, 0.015), "paint", colour,
                     pos=(s * (half_len + 0.06), h.y + 0.08, z0))
        elif weapon == "vdisc":  # a big vertical disc with teeth, in a slot at the front
            r, half_t = sh["disc"]
            part(self.weapon, cylinder(r, half_t, axis="x", seg=48, bevel=0.01, tile=2.0), "steel", (0.7, 0.72, 0.76),
                 rough=1.0, metal=1.0)
            part(self.weapon, cylinder(r * 0.45, half_t + 0.01, axis="x", seg=32), "steel", trim, rough=1.0, metal=1.0)
            teeth = Mesh()
            for t in range(8):
                a = 2 * math.pi * t / 8
                c, s_ = math.cos(a), math.sin(a)
                pts = [(-0.07, r * 0.92), (0.07, r * 0.92), (0.05, r * 1.14), (-0.03, r * 1.08)]
                prism([(y * c - z * s_, y * s_ + z * c) for y, z in pts], half_t + 0.012, mesh=teeth)
            part(self.weapon, teeth, "steel", (0.22, 0.22, 0.24), rough=1.0, metal=1.0)
            for s_ in (-1, 1):  # the slot's side plates
                part(self.chassis, bevel_box(0.03, r * 0.75, r * 0.55, 0.01), "paint", colour,
                     pos=(s_ * (half_t + 0.07), sh["pivot"].y - 0.05, sh["pivot"].z - r * 0.25))
            part(self.chassis, cylinder(0.07, half_t + 0.12, axis="x", seg=16), "steel", (0.3, 0.3, 0.32),
                 pos=(0, sh["pivot"].y, sh["pivot"].z))
            blur = Mesh()
            cylinder(r * 1.12, 0.004, axis="x", seg=48, mesh=blur)
            self.blur = part(self.weapon.getParent(), blur, None, (0.8, 0.82, 0.86), 0.2, 1.0)
            self.blur.setTransparency(TransparencyAttrib.MAlpha)
            self.blur.setDepthWrite(False)
            self.blur.setBin("transparent", 5)
            self.blur_axis = "x"
        elif weapon == "flame":  # a nozzle with a pilot light, fed by two fuel tanks
            n = sh["nozzle"]
            part(self.weapon, cylinder(n.x, n.y, axis="y", seg=16, bevel=0.01), "steel", (0.3, 0.3, 0.32),
                 rough=1.0, metal=1.0, pos=(0, n.y, 0))
            part(self.weapon, cylinder(n.x * 1.35, 0.05, axis="y", seg=16), "steel", (0.15, 0.15, 0.16),
                 pos=(0, n.y * 2, 0))
            self.pilot = part(self.weapon, cylinder(0.025, 0.02, seg=8), None, (0, 0, 0), 0.3, 0, emission=(1, 0.5, 2.5),
                              pos=(0, n.y * 2 + 0.03, -n.z - 0.02))
            for s_ in (-1, 1):
                part(self.chassis, cylinder(0.12 * size / 1.6, h.y * 0.45, axis="y", seg=20, bevel=0.03), "paint",
                     (0.75, 0.1, 0.08), pos=(s_ * h.x * 0.45, -h.y * 0.25, top + 0.13 * size / 1.6))
            part(self.chassis, bevel_box(n.x * 1.8, n.x * 1.8, 0.08, 0.02), "steel", (0.25, 0.25, 0.27),
                 pos=(sh["pivot"].x, sh["pivot"].y, sh["pivot"].z - 0.09))
        elif weapon == "chainsaw":  # an arm that lowers a chainsaw bar; the chain runs round the bar
            a, b = sh["arm"], sh["bar"]
            part(self.weapon, bevel_box(a.x, a.y, a.z, 0.015), "paint", colour, rough=1.0, metal=1.0, pos=(0, a.y, 0))
            part(self.weapon, bevel_box(a.x * 2.2, 0.16, a.z * 2.2, 0.02), "steel", (0.2, 0.2, 0.22),
                 pos=(0, a.y * 2 - 0.08, -0.02))  # motor housing
            by = a.y * 2 + b.y - 0.05
            part(self.weapon, plate_y([(-b.y, -b.z), (b.y - b.z, -b.z), (b.y, 0), (b.y - b.z, b.z), (-b.y, b.z)], b.x),
                 "steel", (0.75, 0.76, 0.8), rough=1.0, metal=1.0, pos=(0, by, -0.04), hpr=(90, 0, 0))
            self.chain = self.weapon.attachNewNode("chain")
            self.chain.setPos(0, by, -0.04)
            links = Mesh()
            k, step_ = 0, 0.06
            y = -b.y
            while y < b.y - b.z:
                for zz in (-b.z - 0.012, b.z + 0.012):
                    bevel_box(b.x + 0.008, 0.02, 0.014, 0.004, mesh=links, offset=Vec3(0, y, zz))
                y += step_
                k += 1
            part(self.chain, links, "steel", (0.35, 0.35, 0.37), rough=1.0, metal=1.0)
            self.chain_step = step_
            for s_ in (-1, 1):
                part(self.chassis, bevel_box(0.05, 0.12, 0.1, 0.015), "steel", (0.3, 0.3, 0.32),
                     pos=(s_ * 0.12, sh["pivot"].y, sh["pivot"].z - 0.05))
        else:  # hammer
            a, hd = sh["arm"], sh["head"]
            part(self.weapon, bevel_box(a.x, a.y, a.z, 0.015), "steel", (0.4, 0.4, 0.42), rough=1.0, metal=1.0,
                 pos=(0, a.y, 0))
            part(self.weapon, bevel_box(hd.x, hd.y, hd.z, 0.02), "steel", (0.2, 0.2, 0.22), rough=1.0, metal=1.0,
                 pos=(0, a.y * 2, 0))
            part(self.weapon, prism([(-hd.y, 0), (hd.y, 0), (0, -hd.z * 2.2)], hd.x * 0.9), "steel",
                 (0.8, 0.8, 0.84), rough=1.0, metal=1.0, pos=(0, a.y * 2, -hd.z * 0.6))
            part(self.chassis, cylinder(0.08, h.x * 0.5, axis="x", seg=16), "steel", trim,
                 pos=(0, -0.2 * size, top + 0.1))
        self.tag = None
        self.spin_angle = 0.0
        self.chain_pos = 0.0
        self.top = top
        # real damage: how healthy each part is (0..1), parts that have come off, bits flying off, the hit bars
        self.health = {}
        self.gone = set()
        self.flying = []
        self.bars, self.bar_until = {}, {}
        self.scorch = 0.0
        self.weak = {}  # how far each part is from breaking off (0 = fine, 1 = about to come off)

    def panel(self, hinge, bend, lie):
        """An armour panel: a node on its hinge edge. bend is how it turns (h, p, r) when nearly off, and lie is
        its pitch and roll when it has come off and lies flat on the floor."""
        np_ = self.armour.attachNewNode("panel")
        np_.setPos(*hinge)
        np_.setPythonTag("lie", lie)
        self.panels.append((np_, Vec3(*hinge), Vec3(*bend)))
        return np_

    def set_label(self, text, colour=(1, 1, 1, 1)):
        if self.tag is None:
            node = TextNode("tag")
            node.setAlign(TextNode.ACenter)
            node.setCardColor(0.03, 0.04, 0.06, 0.7)
            node.setCardAsMargin(0.35, 0.35, 0.18, 0.12)
            self.tag = self.root.attachNewNode(node)
            self.tag.setBillboardPointEye()
            self.tag.setScale(0.17)
            self.tag.setLightOff(1)
            self.tag.setShaderOff(1)
            self.tag.setDepthTest(False)
            self.tag.setDepthWrite(False)
            self.tag.setBin("fixed", 60)
        self.tag.node().setText(text)
        self.tag.node().setTextColor(*colour)

    def update(self, s, dt):
        """s: this robot's state (pos, quat, wpos, wquat, speed; rpm is optional)."""
        self.chassis.setPos(*s["pos"])
        self.chassis.setQuat(Quat(*s["quat"]))
        self.weapon.setPos(*s["wpos"])
        self.weapon.setQuat(Quat(*s["wquat"]))
        self.spin_angle += s["speed"] / self.wheel_r * dt * 57.3
        for i, (w, spin, x, y) in enumerate(self.wheels):
            if f"wheel{i}" in self.gone:
                continue
            w.setPos(self.chassis, x, y, 0.08)
            weak = self.weak.get(f"wheel{i}", 0.0)  # a failing wheel leans out and wobbles as it turns
            side = 1 if x > 0 else -1
            w.setHpr(self.chassis, 0, 0, side * weak * 9 + weak * 7 * math.sin(math.radians(self.spin_angle)))
            spin.setP(-self.spin_angle)
        if self.blur is not None:  # a see-through disc when the bar spins fast
            rpm = s.get("rpm", 0)
            self.blur.setPos(self.weapon.getPos())
            self.blur.setQuat(self.chassis.getQuat())
            self.blur.setAlphaScale(min(0.28, rpm / 1400))
        if getattr(self, "chain", None) is not None and s.get("on", True):  # the chain runs round the bar
            self.chain_pos = (self.chain_pos + dt * 3.0) % self.chain_step
            self.chain.setY(self.weapon, self.shape["arm"].y * 2 + self.shape["bar"].y - 0.05 + self.chain_pos)
        if self.beacon is not None:  # a turning amber beacon: flashes
            glow = 6 if int(time.perf_counter() * 3) % 2 == 0 else 1
            self.beacon.getMaterial().setEmission((glow, glow * 0.5, 0, 1))
        if self.tag is not None:
            self.tag.setPos(self.chassis.getPos() + Vec3(0, 0, 1.3))

    def nozzle(self):
        """Where a flame thrower's flame comes out, and which way it points (world space)."""
        n = self.shape["nozzle"]
        fwd = self.chassis.getQuat().getForward()
        return self.weapon.getPos() + fwd * (n.y * 2 + 0.05), fwd

    def flash(self, on):
        d = self.scorch
        self.chassis.setColorScale((2.2, 2.2, 2.2, 1) if on else (1 - 0.4 * d, 1 - 0.45 * d, 1 - 0.5 * d, 1))

    # ---------- real damage ----------
    def damage(self, pt, now, dt, real=True):
        """pt: the health % of the body, armour, weapon and four wheels (from the server). Weak parts darken, bend,
        wobble and rattle; a part at zero comes off and flies away (and goes back on for a new round); a part
        that has just been hit shows its bar for 1.5 seconds."""
        for i, name in enumerate(("body",) + sim.PARTS):
            f = max(0.0, pt[i] / 100) if i < len(pt) else 1.0
            if f < self.health.get(name, 1.0) - 0.004:
                self.bar_until[name] = now + 1.5
            if name != "body":
                if f <= 0 and name not in self.gone:
                    self.come_off(name)
                elif f > 0 and name in self.gone:
                    self.put_back(name)
            self.health[name] = f
            self.weak[name] = 0.0 if f >= 0.6 else (0.6 - f) / 0.6
        self.scorch = self.weak["body"]
        rattle = math.sin(now * 37) * (1 if self.weak["armour"] > 0.5 else 0)
        for np_, hinge, bend in self.panels:  # armour panels bend out (and rattle when nearly off)
            if np_.getParent() == self.armour:
                np_.setHpr(bend * (self.weak["armour"] + 0.15 * rattle))
        d = self.weak["armour"]
        self.armour.setColorScale(1 - 0.45 * d, 1 - 0.5 * d, 1 - 0.55 * d, 1)
        d = self.weak["weapon"]
        self.weapon.setColorScale(1 - 0.45 * d, 1 - 0.5 * d, 1 - 0.55 * d, 1)
        if d > 0.5 and "weapon" not in self.gone:  # a weapon about to come off shakes on its mount
            q = self.chassis.getQuat()
            self.weapon.setPos(self.weapon.getPos() + q.getRight() * 0.025 * d * math.sin(now * 41))
            self.weapon.setR(self.weapon, 5 * d * math.sin(now * 29))
        for i, (w, *_) in enumerate(self.wheels):
            d = self.weak[f"wheel{i}"]
            w.setColorScale(1 - 0.4 * d, 1 - 0.4 * d, 1 - 0.4 * d, 1)
        self.fly(dt)
        for name in ("body",) + sim.PARTS:  # the bars of the parts hit in the last 1.5 seconds
            if now < self.bar_until.get(name, 0) and (name == "body" or real):
                self.bar(name, real).show(self.bar_pos(name), self.health[name], now)
            elif name in self.bars:
                self.bars[name].hide()

    def bar(self, name, real):
        if name not in self.bars:
            text = {"body": "BODY" if real else "HEALTH", "armour": "ARMOUR", "weapon": "WEAPON"}.get(name, "WHEEL")
            self.bars[name] = HitBar(self.root, text, 0.7 if name in ("body", "armour") else 0.36)
        return self.bars[name]

    def bar_pos(self, name):
        """Body and armour bars stack over the robot (above its name); the weapon's is out in front, each wheel's
        out to its side."""
        c, q = self.chassis.getPos(), self.chassis.getQuat()
        if name == "body":
            return c + Vec3(0, 0, self.top + 1.55)
        if name == "armour":
            return c + Vec3(0, 0, self.top + 1.34)
        if name == "weapon":
            return self.weapon.getPos() + q.getForward() * 0.45 + Vec3(0, 0, 0.3)
        w, spin, x, y = self.wheels[int(name[5:])]
        return w.getPos() + q.getRight() * (0.45 if x > 0 else -0.45) + Vec3(0, 0, 0.3)

    def trouble(self):
        """Where a part is nearly off (world position, how bad 0..1): the window puffs smoke there."""
        out = []
        if self.weak.get("weapon", 0) > 0.5 and "weapon" not in self.gone:
            out.append((self.weapon.getPos(), self.weak["weapon"]))
        for i, (w, *_) in enumerate(self.wheels):
            if self.weak.get(f"wheel{i}", 0) > 0.5 and f"wheel{i}" not in self.gone:
                out.append((w.getPos(), self.weak[f"wheel{i}"]))
        if self.weak.get("armour", 0) > 0.5 and "armour" not in self.gone:
            out.append((self.chassis.getPos() + Vec3(0, 0, self.top), self.weak["armour"]))
        return out

    def come_off(self, name):
        """A part at zero: wheels and armour panels fly off (a lost weapon is moved by the server's physics)."""
        self.gone.add(name)
        rnd = random.Random(hash((id(self), name)))
        away = lambda p: Vec3(p.x - self.chassis.getX(), p.y - self.chassis.getY(), 0)  # noqa: E731
        if name == "armour":
            for np_, hinge, bend in self.panels:
                np_.wrtReparentTo(self.root)
                out = away(np_.getPos())
                out.normalize()
                self.flying.append([np_, out * rnd.uniform(1.5, 3.5) + Vec3(0, 0, rnd.uniform(3, 5)),
                                    Vec3(rnd.uniform(-400, 400), rnd.uniform(-400, 400), rnd.uniform(-300, 300)), 0.03,
                                    np_.getPythonTag("lie")])
        elif name.startswith("wheel"):
            w = self.wheels[int(name[5:])][0]
            out = away(w.getPos())
            out.normalize()
            self.flying.append([w, out * rnd.uniform(2.0, 4.0) + Vec3(0, 0, rnd.uniform(2.5, 4)),
                                Vec3(rnd.uniform(-200, 200), 0, rnd.uniform(200, 500)), w.getPythonTag("width"), (0, 90)])

    def put_back(self, name):
        """A new round: the part is back on the robot."""
        self.gone.discard(name)
        if name == "armour":
            for np_, hinge, bend in self.panels:
                np_.reparentTo(self.armour)
                np_.setPos(hinge)
                np_.setHpr(0, 0, 0)
            nodes = {id(np_) for np_, *_ in self.panels}
        elif name.startswith("wheel"):
            nodes = {id(self.wheels[int(name[5:])][0])}
        else:
            return
        self.flying = [f for f in self.flying if id(f[0]) not in nodes]

    def fly(self, dt):
        """Parts that came off: thrown clear, they bounce and come to rest lying flat on the floor."""
        half = sim.ARENA / 2 - 0.2
        for f in self.flying:
            np_, vel, spin, rest_z, lie = f
            if vel is None:
                continue
            vel.z -= 9.81 * dt
            p = np_.getPos() + vel * dt
            for axis in (0, 1):  # the arena walls
                if abs(p[axis]) > half:
                    p[axis] = math.copysign(half, p[axis])
                    vel[axis] *= -0.4
            if p.z < rest_z:
                p.z = rest_z
                vel.x, vel.y, vel.z = vel.x * 0.55, vel.y * 0.55, -vel.z * 0.3
                spin *= 0.5
                if vel.length() < 0.6:  # settled: lying flat
                    np_.setHpr(np_.getH(), *lie)
                    f[1] = None
            np_.setPos(p)
            if f[1] is not None:
                np_.setHpr(np_.getHpr() + spin * dt)

    def destroy(self):
        self.root.removeNode()
