"""Craft Lab's drawing (CHANGE 200): the world's chunks, the sky, the sun, the moon, the stars and the clouds, the
block you look at and the crack as you dig, particles, the creatures and the players, on every graphics tier.

The blocks are drawn by a small shader of Craft Lab's own (GLSL 1.20, so the oldest school laptop runs it): the
atlas's pixels times the corner shading and the light baked into each corner (craft_mesh.py), the sky's part of it
times the time of day, the torches' part warm and the same all night; fog into the sky's colour at the edge of the
view. Every tier draws the same blocks; what changes is how far (VIEW), how smooth (MSAA, from the engine's tier
settings), the sun's shadows (medium and up: a shadow map that follows you, sized as the engine's tiers say),
waving leaves and plants and the water's shimmer (high and ultra), and the clouds (low and up; ultra: two layers).
mesh and lines are the engine's looks (engine.line_look): black faces, the blocks' edges in the line colour.
"""
import math
import sys

import numpy as np
from panda3d.core import (AntialiasAttrib, CardMaker, DirectionalLight, Geom, GeomNode, GeomPoints, GeomTriangles,
                          GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, InternalName, LineSegs,
                          OrthographicLens, SamplerState, Shader, Texture, TransparencyAttrib, Vec3, Vec4)

import craft_art
import craft_blocks as B
import craft_mesh as M
import craft_version
sys.path.insert(0, craft_version.ENGINE_HOME)
from engine import gfx_tiers, line_look  # noqa: E402

TIERS = gfx_tiers.TIERS  # (Craft Lab draws all seven)
VIEW = {"mesh": 72, "lines": 96, "basic": 64, "low": 80, "medium": 112, "high": 144, "ultra": 224}
SHADOW_AREA = {"medium": 64.0, "high": 96.0, "ultra": 128.0}
WAVES = ("high", "ultra")
CLOUDS = {"mesh": 0, "lines": 0, "basic": 0, "low": 1, "medium": 1, "high": 1, "ultra": 2}
PARTICLES = {"mesh": 6, "lines": 6, "basic": 8, "low": 10, "medium": 14, "high": 18, "ultra": 24}
_state = {}

# ---------- the sky through the day ----------
DAY_SECONDS = 1200.0     # one day and night (20 minutes), as the server keeps it
SKY_DAY = np.array((0.48, 0.68, 0.98))
SKY_DUSK = np.array((0.95, 0.55, 0.32))
SKY_NIGHT = np.array((0.015, 0.025, 0.07))


def time_look(t):
    """The time of day t (0 to 1: 0 dawn, 0.25 noon, 0.5 dusk, 0.75 midnight) as (daylight 0.14 to 1, the sky's
    colour, the sun's direction)."""
    a = t * 2 * math.pi
    sun_up = math.sin(a)
    day = max(0.0, min(1.0, sun_up * 3 + 0.35))
    daylight = 0.14 + 0.86 * day
    dusk = max(0.0, 1 - abs(sun_up) * 4) if math.cos(a) != 0 else 0.0
    sky = SKY_NIGHT + (SKY_DAY - SKY_NIGHT) * day
    sky = sky + (SKY_DUSK - sky) * dusk * 0.6
    sun_dir = Vec3(math.cos(a) * 0.9, 0.35, math.sin(a))
    sun_dir.normalize()
    return daylight, tuple(sky), sun_dir


# ---------- the shaders ----------
_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform float u_day;
uniform vec3 u_tint;
uniform float u_time;
uniform float u_wave;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
attribute vec4 p3d_Color;
varying vec2 v_uv;
varying vec3 v_light;
varying float v_dist;
varying float v_sunny;
#SHADOW_DECL
void main() {
    vec4 p = p3d_Vertex;
    float flags = floor(p3d_Color.a * 255.0 + 0.5);
    float wave = mod(flags, 32.0) >= 16.0 ? 1.0 : 0.0;
    if (u_wave > 0.5 && wave > 0.5) {
        p.x += sin(u_time * 1.7 + p.y * 0.9 + p.z) * 0.04;
        p.y += cos(u_time * 1.3 + p.x * 0.8) * 0.04;
    }
    gl_Position = p3d_ModelViewProjectionMatrix * p;
    v_uv = p3d_MultiTexCoord0;
    float sky = pow(0.8, (1.0 - p3d_Color.g) * 15.0) * u_day;
    float blk = pow(0.8, (1.0 - p3d_Color.b) * 15.0);
    blk = p3d_Color.b > 0.01 ? blk : 0.0;
    vec3 l = max(vec3(sky) * u_tint, vec3(blk, blk * 0.86, blk * 0.62));
    v_light = max(l, vec3(0.045)) * p3d_Color.r;
    v_sunny = p3d_Color.g * u_day;
    vec4 eye = p3d_ModelViewMatrix * p;
    v_dist = length(eye.xyz);
#SHADOW_VERT
}
"""
_FRAG = """#version 120
uniform sampler2D p3d_Texture0;
uniform vec3 u_fog_colour;
uniform vec2 u_fog;
uniform float u_cut;
uniform float u_alpha;
varying vec2 v_uv;
varying vec3 v_light;
varying float v_dist;
varying float v_sunny;
#SHADOW_DECL
void main() {
    vec4 t = texture2D(p3d_Texture0, v_uv);
    if (t.a < u_cut) discard;
    vec3 c = t.rgb * v_light;
#SHADOW_FRAG
    float f = clamp((v_dist - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    gl_FragColor = vec4(mix(c, u_fog_colour, f), t.a * u_alpha);
}
"""
_SHADOW_DECL = """uniform struct { sampler2DShadow shadowMap; mat4 shadowViewMatrix; } p3d_LightSource[1];
varying vec4 v_shadow;"""
_SHADOW_VERT = "    v_shadow = p3d_LightSource[0].shadowViewMatrix * eye;"
_SHADOW_FRAG = """    vec4 sc = v_shadow;
    sc.z -= 0.0035 * sc.w;  // (a little bias: no stripes of a face shadowing itself)
    float lit = shadow2DProj(p3d_LightSource[0].shadowMap, sc).r;
    c *= 1.0 - 0.36 * (1.0 - lit) * clamp(v_sunny * 1.4 - 0.25, 0.0, 1.0);"""

# the creatures, players, the hand and particles: the same look, their light from where they stand (u_here)
_ENT_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform float u_day;
uniform vec3 u_tint;
uniform vec2 u_here;
uniform vec4 u_flash;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
attribute vec4 p3d_Color;
varying vec2 v_uv;
varying vec3 v_light;
varying vec4 v_col;
varying float v_dist;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
    float sky = pow(0.8, (1.0 - u_here.x) * 15.0) * u_day;
    float blk = u_here.y > 0.01 ? pow(0.8, (1.0 - u_here.y) * 15.0) : 0.0;
    v_light = max(max(vec3(sky) * u_tint, vec3(blk, blk * 0.86, blk * 0.62)), vec3(0.06));
    v_col = p3d_Color;
    v_dist = length((p3d_ModelViewMatrix * p3d_Vertex).xyz);
}
"""
_ENT_FRAG = """#version 120
uniform sampler2D p3d_Texture0;
uniform vec3 u_fog_colour;
uniform vec2 u_fog;
uniform vec4 u_flash;
varying vec2 v_uv;
varying vec3 v_light;
varying vec4 v_col;
varying float v_dist;
void main() {
    vec4 t = texture2D(p3d_Texture0, v_uv);
    if (t.a < 0.3) discard;
    vec3 c = t.rgb * v_col.rgb * v_light;
    c = mix(c, u_flash.rgb, u_flash.a);
    float f = clamp((v_dist - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    gl_FragColor = vec4(mix(c, u_fog_colour, f), t.a * v_col.a);
}
"""


def _format():
    arr = GeomVertexArrayFormat()
    arr.addColumn(InternalName.getVertex(), 3, Geom.NT_float32, Geom.C_point)
    arr.addColumn(InternalName.getTexcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
    arr.addColumn(InternalName.getColor(), 4, Geom.NT_uint8, Geom.C_color)
    return GeomVertexFormat.registerFormat(arr)


FORMAT = None


def tier():
    return _state.get("tier", gfx_tiers.DEFAULT)


def look():
    return tier() in gfx_tiers.LOOKS


def view_distance():
    return VIEW.get(tier(), 112)


# ---------- the start ----------
def init(base, tier_wanted="medium", line_colour=None):
    """The tier's drawing: the atlas, the shaders, the sun (and its shadow map on medium and up), the sky, the fog.
    Returns the tier used (a driver that can't compile the shadow shader gets medium's look without shadows)."""
    global FORMAT
    FORMAT = FORMAT or _format()
    quality = tier_wanted if tier_wanted in TIERS else gfx_tiers.DEFAULT
    _state.clear()
    line_look.reset()
    _state.update(tier=quality, base=base, time=0.3, wave_t=0.0)
    atlas, where = craft_art.build_atlas()
    _state["where"] = where
    _state["tables"] = M.Tables(where)
    _state["atlas"] = atlas_texture(atlas, quality)
    base.camLens.setNear(0.05)
    base.camLens.setFar(VIEW[quality] * 1.2 + 40)
    base.camLens.setFov(75)
    if quality in gfx_tiers.LOOKS:
        line_look.init(base, quality, line_colour, fade=(VIEW[quality] * 0.35, VIEW[quality]), far=VIEW[quality] * 1.3)
        _state["shader"] = _state["ent_shader"] = None
        return quality
    s = gfx_tiers.SETTINGS[quality]
    shadow = s["shadow"] if quality in SHADOW_AREA else 0
    sun = DirectionalLight("sun")
    sun.setColor((1, 1, 1, 1))
    sun_np = base.render.attachNewNode(sun)
    _state["sun"] = sun_np
    shader = None
    if shadow:
        sun.setShadowCaster(True, shadow, shadow)
        area = SHADOW_AREA[quality]
        lens = OrthographicLens()
        lens.setFilmSize(area, area)
        lens.setNearFar(1, 240)
        sun.setLens(lens)
        base.render.setLight(sun_np)
        shader = make_shader(True)
        if shader is None:
            print("gfx: the shadow shader didn't compile here: no sun shadows", file=sys.stderr, flush=True)
            sun.setShadowCaster(False)
            base.render.clearLight(sun_np)
    if shader is None:
        shader = make_shader(False)
    _state["shader"] = shader
    _state["shadow"] = bool(shadow) and shader is not None and _state.get("shadow_ok", False)
    _state["ent_shader"] = Shader.make(Shader.SL_GLSL, _ENT_VERT, _ENT_FRAG)
    if s["msaa"]:
        base.render.setAntialias(AntialiasAttrib.MMultisample)
    _state["sky"] = Sky(base, quality)
    set_time(base, 0.3)
    return quality


def make_shader(shadow):
    vert, frag = _VERT, _FRAG
    if shadow:
        vert = vert.replace("#SHADOW_DECL", _SHADOW_DECL).replace("#SHADOW_VERT", _SHADOW_VERT)
        frag = frag.replace("#SHADOW_DECL", _SHADOW_DECL).replace("#SHADOW_FRAG", _SHADOW_FRAG)
    else:
        vert = vert.replace("#SHADOW_DECL", "").replace("#SHADOW_VERT", "")
        frag = frag.replace("#SHADOW_DECL", "").replace("#SHADOW_FRAG", "")
    try:
        sh = Shader.make(Shader.SL_GLSL, vert, frag)
    except Exception:
        sh = None
    if sh is not None and shadow:
        _state["shadow_ok"] = True
    return sh


def atlas_texture(atlas, quality):
    """The atlas as a texture: big pixels close to (nearest), mipmapped far off on medium and up (no shimmer), never
    shrunk by the tier's texture scale (a 16-pixel tile is small already)."""
    tex = Texture("craft atlas")
    tex.setup2dTexture(atlas.shape[1], atlas.shape[0], Texture.T_unsigned_byte, Texture.F_rgba8)
    # (Panda's rows run from the bottom up, and its bytes are blue, green, red, alpha)
    tex.setRamImageAs(np.ascontiguousarray(atlas[::-1]).tobytes(), "RGBA")
    tex.setMagfilter(SamplerState.FT_nearest)
    if quality in ("medium", "high", "ultra"):
        tex.setMinfilter(SamplerState.FT_nearest_mipmap_linear)
        tex.setAnisotropicDegree(1)  # (anisotropic filtering smooths the pixels close up too: the blocks' are big)
        ss = SamplerState(tex.getDefaultSampler())
        ss.setMaxLod(4)  # (a 16-pixel tile is one pixel at level 4: further down it would be its neighbours' too)
        tex.setDefaultSampler(ss)
    else:
        tex.setMinfilter(SamplerState.FT_nearest)
    tex.setWrapU(SamplerState.WM_clamp)
    tex.setWrapV(SamplerState.WM_clamp)
    return tex


def refresh_atlas():
    """Mods' blocks have come (from the server, or mods/blocks.py): the atlas drawn again with their tiles, in the
    same texture (everything already drawn shows them), and the mesher's tables made again."""
    atlas, where_ = craft_art.build_atlas()
    _state["where"] = where_
    _state["tables"] = M.Tables(where_)
    tex = _state.get("atlas")
    if tex is not None:
        tex.setRamImageAs(np.ascontiguousarray(atlas[::-1]).tobytes(), "RGBA")


def where():
    return _state["where"]


def tables():
    if _state["tables"].cube.shape[0] and len(B.BLOCKS) != getattr(_state["tables"], "n", len(B.BLOCKS)):
        _state["tables"] = M.Tables(_state["where"])
    return _state["tables"]


def uv_of(tile_name, inset=True):
    """A tile's corner in the atlas and its size (a hair inside it: a far mipmap or a smoothed edge never reaches the
    next tile's pixels)."""
    col, row = _state["where"].get(tile_name, (0, 0))
    s = 1.0 / B.ATLAS
    e = s / 32 if inset else 0.0
    return col * s + e, 1.0 - (row + 1) * s + e, s - 2 * e


# ---------- the time of day ----------
def set_time(base, t):
    """The time of day (0 to 1): the daylight in the shaders, the sky's colour, the fog, the sun and the moon."""
    _state["time"] = t % 1.0
    daylight, sky, sun_dir = time_look(t)
    _state["daylight"], _state["sky_colour"], _state["sun_dir"] = daylight, sky, sun_dir
    tint = (1.0, 1.0, 1.0) if daylight > 0.6 else (0.75 + 0.25 * daylight, 0.8 + 0.2 * daylight, 1.0)
    _state["tint"] = tint
    if look():
        return
    base.setBackgroundColor(*sky, 1)
    for np_ in _state.get("shaded", []):
        if not np_.isEmpty():
            apply_inputs(np_)
    if _state.get("sky") is not None:
        _state["sky"].update(t, sky, sun_dir)


def apply_inputs(np_, cut=None, alpha=None):
    v = VIEW[tier()]
    np_.setShaderInput("u_day", float(_state.get("daylight", 1.0)))
    np_.setShaderInput("u_tint", Vec3(*_state.get("tint", (1, 1, 1))))
    np_.setShaderInput("u_fog_colour", Vec3(*_state.get("sky_colour", SKY_DAY)))
    np_.setShaderInput("u_fog", (v * 0.62, v * 0.98))
    np_.setShaderInput("u_time", float(_state.get("wave_t", 0.0)))
    np_.setShaderInput("u_wave", 1.0 if tier() in WAVES else 0.0)
    if cut is not None:
        np_.setShaderInput("u_cut", cut)
    if alpha is not None:
        np_.setShaderInput("u_alpha", alpha)


def shade_node(np_, cut=0.5, alpha=1.0):
    """A node drawn with the blocks' shader (the world's root, chunks' passes)."""
    if _state.get("shader") is None:
        return
    np_.setShader(_state["shader"])
    apply_inputs(np_, cut, alpha)
    _state.setdefault("shaded", []).append(np_)


def ent_node(np_):
    """A creature's, a player's or the hand's node: the creatures' shader, lit by where it stands (set_here)."""
    if look():
        return
    if _state.get("ent_shader") is None:
        return
    np_.setShader(_state["ent_shader"])
    apply_inputs(np_)
    np_.setShaderInput("u_here", (1.0, 0.0))
    np_.setShaderInput("u_flash", Vec4(1, 0.2, 0.2, 0))
    np_.setTexture(_state["atlas"])
    _state.setdefault("shaded", []).append(np_)


def set_here(np_, world, x, y, z):
    """A creature's light: the sky's and the torches' at its feet."""
    if look() or np_.isEmpty():
        return
    xi, yi, zi = int(math.floor(x)), int(math.floor(y)), int(math.floor(z + 0.5))
    if world.inside(xi, yi, zi):
        np_.setShaderInput("u_here", (float(world.sky[xi, yi, zi]) / 15.0, float(world.glow[xi, yi, zi]) / 15.0))


def flash(np_, on):
    if not look() and not np_.isEmpty():
        np_.setShaderInput("u_flash", Vec4(1, 0.15, 0.15, 0.55 if on else 0.0))


def tick(base, dt, cam_pos):
    """Every frame: the waving leaves' clock, the sun's shadow over the player, the clouds drifting."""
    _state["wave_t"] = _state.get("wave_t", 0.0) + dt
    if tier() in WAVES:
        for np_ in _state.get("shaded", []):
            if not np_.isEmpty():
                np_.setShaderInput("u_time", float(_state["wave_t"]))
    sun = _state.get("sun")
    if sun is not None and cam_pos is not None:
        d = _state.get("sun_dir", Vec3(0, 0, 1))
        if d.z < 0.05:  # (the sun below the horizon: the moon's light, from above)
            d = Vec3(-d.x, -d.y, -d.z)
        sun.setPos(cam_pos + d * 120)
        sun.lookAt(cam_pos)
    if _state.get("sky") is not None:
        _state["sky"].follow(cam_pos, dt)
    _state["shaded"] = [n for n in _state.get("shaded", []) if not n.isEmpty()]


# ---------- the chunks ----------
def geom_from(arrays, name):
    data, idx, n = arrays
    vdata = GeomVertexData(name, FORMAT, Geom.UH_static)
    vdata.uncleanSetNumRows(n * 4)
    vdata.modifyArray(0).modifyHandle().setData(data)
    tris = GeomTriangles(Geom.UH_static)
    tris.setIndexType(Geom.NT_uint32)
    tris.modifyVertices().modifyHandle().setData(idx.tobytes())
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


class WorldVisual:
    """The world's chunks, each drawn as up to three nodes (solid, cutout, blend) and its lines on a look; built
    nearest the player first, a few a frame, and again when a block in them changes."""

    def __init__(self, render, world):
        self.world = world
        self.root = render.attachNewNode("world")
        self.root.setTexture(_state["atlas"])
        self.solid = self.root.attachNewNode("solid")
        self.cutout = self.root.attachNewNode("cutout")
        self.blend = self.root.attachNewNode("blend")
        self.cutout.setTwoSided(True)
        self.blend.setTransparency(TransparencyAttrib.M_alpha)
        self.blend.setDepthWrite(False)
        self.blend.setBin("transparent", 10)
        self.cutout.setBin("opaque", 5)
        shade_node(self.solid, 0.5, 1.0)
        shade_node(self.cutout, 0.5, 1.0)
        shade_node(self.blend, 0.01, 1.0)
        self.chunks = {}       # (cx, cy) -> [nodes]
        self.todo = set(world.chunks)
        if look():
            self.lines = self.root.attachNewNode("lines")
        self.built = 0

    def rebuild(self, key):
        for np_ in self.chunks.pop(key, []):
            np_.removeNode()
        out, segs = M.mesh_chunk(self.world, key[0], key[1], tables(), tier() if look() else None)
        nodes = []
        for p, parent in zip(out, (self.solid, self.cutout, self.blend)):
            arrays = p.arrays()
            if arrays is None:
                continue
            np_ = parent.attachNewNode(geom_from(arrays, f"chunk {key} {p}"))
            if look():
                line_look.blacken(np_)
            nodes.append(np_)
        if look() and segs is not None and len(segs):
            pts = segs.reshape(-1, 3).astype(np.float32)
            pairs = np.arange(len(pts), dtype=np.int64).reshape(-1, 2)
            ln = self.lines.attachNewNode(line_look.line_node(f"lines {key}", pts, pairs))
            line_look.wire(ln, ln)
            nodes.append(ln)
        self.chunks[key] = nodes
        self.built += 1

    def update(self, cam_x, cam_y, budget=0.012, first=False):
        """Chunks changed since last time, and those not yet drawn, nearest the camera first, for up to budget
        seconds (everything, first time, so the first picture is whole)."""
        import time
        self.todo |= self.world.dirty
        self.world.dirty = set()
        if not self.todo:
            return 0
        reach = VIEW[tier()] + M.CHUNK
        order = sorted(self.todo, key=lambda k: (k[0] * M.CHUNK + 8 - cam_x) ** 2 + (k[1] * M.CHUNK + 8 - cam_y) ** 2)
        t0 = time.perf_counter()
        n = 0
        for key in order:
            far = math.hypot(key[0] * M.CHUNK + 8 - cam_x, key[1] * M.CHUNK + 8 - cam_y) > reach
            if far and key not in self.chunks:
                continue  # (out of view: drawn when you come near)
            self.todo.discard(key)
            self.rebuild(key)
            n += 1
            if not first and time.perf_counter() - t0 > budget:
                break
        self.cull(cam_x, cam_y)
        return n

    def cull(self, cam_x, cam_y):
        """Chunks further than the view hidden (the fog has them anyway)."""
        reach = VIEW[tier()] + M.CHUNK * 1.5
        for key, nodes in self.chunks.items():
            far = math.hypot(key[0] * M.CHUNK + 8 - cam_x, key[1] * M.CHUNK + 8 - cam_y) > reach
            for np_ in nodes:
                if far != np_.isHidden():
                    np_.hide() if far else np_.show()

    def destroy(self):
        self.root.removeNode()


# ---------- the sky ----------
class Sky:
    """The sun and the moon (squares that cross the sky with the time of day), the stars at night, the clouds (a
    flat layer of soft blocks drifting east; two on ultra). Drawn behind everything and following the camera."""

    def __init__(self, base, quality):
        self.base = base
        self.root = base.camera.attachNewNode("sky")
        self.root.setCompass()  # (turns with nothing: only the camera's position)
        self.root.setBin("background", 0)
        self.root.setDepthWrite(False)
        self.root.setLightOff(1)
        self.root.setFogOff(1)
        self.root.setShaderOff(1)
        # (inside the far plane on every tier: at 250 m the sun, moon and stars were clipped away below ultra)
        self.r = min(250.0, base.camLens.getFar() * 0.8)
        k = self.r / 250.0
        cm = CardMaker("sun")
        cm.setFrame(-7 * k, 7 * k, -7 * k, 7 * k)
        self.sun = self.root.attachNewNode(cm.generate())
        self.sun.setColor(1.0, 0.95, 0.6, 1)
        self.sun.setBillboardPointEye()
        cm = CardMaker("moon")
        cm.setFrame(-5 * k, 5 * k, -5 * k, 5 * k)
        self.moon = self.root.attachNewNode(cm.generate())
        self.moon.setColor(0.85, 0.88, 1.0, 1)
        self.moon.setBillboardPointEye()
        self.stars = self.root.attachNewNode(self.star_node(self.r * 1.1))
        self.stars.setTransparency(TransparencyAttrib.M_alpha)
        self.clouds = []
        rng = np.random.default_rng(5)
        for layer in range(CLOUDS.get(quality, 0)):
            np_ = base.render.attachNewNode(self.cloud_node(rng, layer))
            np_.setTransparency(TransparencyAttrib.M_alpha)
            np_.setDepthWrite(False)
            np_.setBin("transparent", 20)
            np_.setLightOff(1)
            np_.setShaderOff(1)
            np_.setTwoSided(True)
            np_.setZ(78 + layer * 14)
            self.clouds.append(np_)
        self.drift = 0.0

    @staticmethod
    def star_node(radius=300.0):
        rng = np.random.default_rng(3)
        vdata = GeomVertexData("stars", GeomVertexFormat.getV3c4(), Geom.UH_static)
        from panda3d.core import GeomVertexWriter
        v, c = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color")
        pts = GeomPoints(Geom.UH_static)
        for i in range(500):
            d = rng.normal(size=3)
            d[2] = abs(d[2]) + 0.05
            d = d / np.linalg.norm(d) * radius
            v.addData3(*d)
            b = 0.5 + rng.random() * 0.5
            c.addData4(b, b, b, 1)
            pts.addVertex(i)
        g = Geom(vdata)
        g.addPrimitive(pts)
        node = GeomNode("stars")
        node.addGeom(g)
        return node

    @staticmethod
    def cloud_node(rng, layer):
        """Clouds: soft white slabs on a 12-block grid where a noise is high."""
        size, cell = 40, 12
        field = rng.random((size, size))
        for _ in range(3):  # (blurred: clouds in clumps, not salt and pepper)
            field = (field + np.roll(field, 1, 0) + np.roll(field, -1, 0) + np.roll(field, 1, 1) + np.roll(field, -1, 1)) / 5
        field = (field - field.min()) / max(1e-6, field.max() - field.min())
        vdata = GeomVertexData("clouds", GeomVertexFormat.getV3c4(), Geom.UH_static)
        from panda3d.core import GeomVertexWriter
        v, c = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color")
        tris = GeomTriangles(Geom.UH_static)
        n = 0
        a = 0.75 if layer == 0 else 0.5
        for i in range(size):
            for j in range(size):
                if field[i, j] < 0.56:
                    continue
                x0, y0 = (i - size / 2) * cell, (j - size / 2) * cell
                for (x, y) in ((x0, y0), (x0 + cell, y0), (x0 + cell, y0 + cell), (x0, y0 + cell)):
                    v.addData3(x, y, 0)
                    c.addData4(1, 1, 1, a)
                tris.addVertices(n, n + 1, n + 2)
                tris.addVertices(n, n + 2, n + 3)
                n += 4
        g = Geom(vdata)
        g.addPrimitive(tris)
        node = GeomNode("clouds")
        node.addGeom(g)
        return node

    def update(self, t, sky, sun_dir):
        self.sun.setPos(sun_dir * self.r)
        self.moon.setPos(-sun_dir * self.r)
        night = max(0.0, min(1.0, -sun_dir.z * 4 + 0.2))
        self.stars.setAlphaScale(night)
        self.stars.show() if night > 0.02 else self.stars.hide()
        day = max(0.0, min(1.0, sun_dir.z * 3 + 0.4))
        for k, cl in enumerate(self.clouds):
            g = 0.1 + 0.9 * day
            cl.setColorScale(g, g, g * 1.02, 1)

    def follow(self, cam_pos, dt):
        if cam_pos is None:
            return
        self.drift = (self.drift + dt * 1.2) % 12.0
        for k, cl in enumerate(self.clouds):
            cl.setX(math.floor(cam_pos.x / 12.0) * 12.0 + self.drift * (1 + k * 0.5))
            cl.setY(math.floor(cam_pos.y / 12.0) * 12.0)


# ---------- the block you look at, and the crack ----------
class Target:
    """A thin outline round the block you look at, and the crack drawn over it as you dig."""

    def __init__(self, render):
        ls = LineSegs("target")
        ls.setThickness(2.0)
        ls.setColor(0.05, 0.05, 0.05, 0.85) if not look() else ls.setColor(1, 1, 1, 1)
        e = 0.002
        lo, hi = -e, 1 + e
        for (a, b) in (((lo, lo, lo), (hi, lo, lo)), ((hi, lo, lo), (hi, hi, lo)), ((hi, hi, lo), (lo, hi, lo)),
                       ((lo, hi, lo), (lo, lo, lo)), ((lo, lo, hi), (hi, lo, hi)), ((hi, lo, hi), (hi, hi, hi)),
                       ((hi, hi, hi), (lo, hi, hi)), ((lo, hi, hi), (lo, lo, hi)), ((lo, lo, lo), (lo, lo, hi)),
                       ((hi, lo, lo), (hi, lo, hi)), ((hi, hi, lo), (hi, hi, hi)), ((lo, hi, lo), (lo, hi, hi))):
            ls.moveTo(*a)
            ls.drawTo(*b)
        self.box = render.attachNewNode(ls.create())
        self.box.setTransparency(TransparencyAttrib.M_alpha)
        self.box.setShaderOff(1)
        self.box.setLightOff(1)
        self.box.hide()
        self.crack = render.attachNewNode(self.crack_node())
        self.crack.setTexture(_state["atlas"])
        self.crack.setTransparency(TransparencyAttrib.M_alpha)
        self.crack.setShaderOff(1)
        self.crack.setLightOff(1)
        self.crack.setDepthOffset(1)
        self.crack.hide()
        self.stage = -1

    @staticmethod
    def crack_node():
        from panda3d.core import GeomVertexWriter
        vdata = GeomVertexData("crack", GeomVertexFormat.getV3t2(), Geom.UH_dynamic)
        v, tw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "texcoord")
        tris = GeomTriangles(Geom.UH_static)
        e = 0.004
        for d in range(6):
            for k, corner in enumerate(M.CORNERS[d]):
                p = (np.array(corner) - 0.5) * (1 + 2 * e) + 0.5
                v.addData3(*p)
                tw.addData2(*M.UV[k])
            b = d * 4
            tris.addVertices(b, b + 1, b + 2)
            tris.addVertices(b, b + 2, b + 3)
        g = Geom(vdata)
        g.addPrimitive(tris)
        node = GeomNode("crack")
        node.addGeom(g)
        return node

    def show(self, block, progress):
        if block is None:
            self.box.hide()
            self.crack.hide()
            return
        self.box.setPos(*block)
        self.box.show()
        if progress <= 0:
            self.crack.hide()
            return
        stage = min(9, int(progress * 10))
        self.crack.setPos(*block)
        self.crack.show()
        if stage != self.stage:
            self.stage = stage
            u0, v0, s = uv_of(f"crack_{stage}")
            from panda3d.core import TextureStage
            self.crack.setTexScale(TextureStage.getDefault(), s, s)
            self.crack.setTexOffset(TextureStage.getDefault(), u0, v0)


# ---------- boxes for creatures, players, the hand and items ----------
def box_geom(parts, name="model"):
    """Boxes [(lo, hi, tiles (one name or six), colour)] as one node, in the entity format (each face's corner
    colour is the face's shade times the box's colour)."""
    from panda3d.core import GeomVertexWriter
    vdata = GeomVertexData(name, GeomVertexFormat.getV3c4t2(), Geom.UH_static)
    v, c, tw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color"), GeomVertexWriter(vdata, "texcoord")
    tris = GeomTriangles(Geom.UH_static)
    n = 0
    for lo, hi, tiles, colour in parts:
        lo, hi = np.array(lo, np.float32), np.array(hi, np.float32)
        names = (tiles,) * 6 if isinstance(tiles, str) else tiles
        for d in range(6):
            u0, v0, s = uv_of(names[d])
            sh = M.FACE_SHADE[d]
            for k, corner in enumerate(M.CORNERS[d]):
                v.addData3(*(lo + (hi - lo) * corner))
                c.addData4(colour[0] * sh, colour[1] * sh, colour[2] * sh, 1)
                tw.addData2(u0 + M.UV[k][0] * s, v0 + M.UV[k][1] * s)
            tris.addVertices(n, n + 1, n + 2)
            tris.addVertices(n, n + 2, n + 3)
            n += 4
    g = Geom(vdata)
    g.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(g)
    return node


def model(parent, parts, name="model"):
    """A box model under parent, drawn as the tier draws creatures (lines: its outline)."""
    np_ = parent.attachNewNode(box_geom(parts, name))
    if look():
        line_look.outline(np_)
    return np_


def item_geom(item_id, size=0.25):
    """An item to hold or to see dropped: a block as a small cube of its own faces, anything else as its icon on a
    thin card (both sides)."""
    it = B.ITEMS.get(item_id)
    if it is None:
        return box_geom([((0, 0, 0), (size, size, size), "particle", (1, 0, 1))])
    if it.get("block") is not None and B.BLOCKS[it["block"]]["shape"] == "cube":
        b = B.BLOCKS[it["block"]]
        top, side, bottom = b["tiles"]
        h = size / 2
        return box_geom([((-h, -h, -h), (h, h, h), (side, side, side, side, top, bottom), (1, 1, 1))], it["key"])
    icon = it.get("icon") or "particle"
    if it.get("block") is not None:
        icon = B.BLOCKS[it["block"]]["tiles"][0 if B.BLOCKS[it["block"]]["shape"] in ("cross", "crop", "torch") else 1]
        if it["key"] == "door":
            icon = "door_high"
    return card_geom(icon, size, it["key"])


def card_geom(tile_name, size, name="card"):
    """A flat square showing one tile, both sides (an item's icon held, or dropped)."""
    from panda3d.core import GeomVertexWriter
    vdata = GeomVertexData(name, GeomVertexFormat.getV3c4t2(), Geom.UH_static)
    v, c, tw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color"), GeomVertexWriter(vdata, "texcoord")
    tris = GeomTriangles(Geom.UH_static)
    u0, v0, s = uv_of(tile_name)
    h = size / 2
    for side, ys in ((0, -0.004), (1, 0.004)):
        corners = [(-h, ys, -h), (h, ys, -h), (h, ys, h), (-h, ys, h)]
        uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
        if side:
            corners, uvs = corners[::-1], uvs[::-1]
        for (x, y, z), (a, b) in zip(corners, uvs):
            v.addData3(x, y, z)
            c.addData4(1, 1, 1, 1)
            tw.addData2(u0 + a * s, v0 + b * s)
        base = side * 4
        tris.addVertices(base, base + 1, base + 2)
        tris.addVertices(base, base + 2, base + 3)
    g = Geom(vdata)
    g.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(g)
    return node


def bit_geom(u0, v0, q, colour):
    """A particle: a small cube showing a q-square of the atlas at (u0, v0)."""
    from panda3d.core import GeomVertexWriter
    vdata = GeomVertexData("bit", GeomVertexFormat.getV3c4t2(), Geom.UH_static)
    v, c, tw = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color"), GeomVertexWriter(vdata, "texcoord")
    tris = GeomTriangles(Geom.UH_static)
    n = 0
    for d in range(6):
        sh = M.FACE_SHADE[d]
        for k, corner in enumerate(M.CORNERS[d]):
            v.addData3(*((np.array(corner) - 0.5) * 0.1))
            c.addData4(colour[0] * sh, colour[1] * sh, colour[2] * sh, 1)
            tw.addData2(u0 + M.UV[k][0] * q, v0 + M.UV[k][1] * q)
        tris.addVertices(n, n + 1, n + 2)
        tris.addVertices(n, n + 2, n + 3)
        n += 4
    g = Geom(vdata)
    g.addPrimitive(tris)
    node = GeomNode("bit")
    node.addGeom(g)
    return node


# ---------- particles ----------
class Particles:
    """Bits flying off a block as it is dug or broken, splashes, sparks from hits: small squares of the block's own
    texture, falling, gone in a second."""

    def __init__(self, render):
        self.root = render.attachNewNode("particles")
        ent_node(self.root)
        self.bits = []
        self.rng = np.random.default_rng(9)

    def burst(self, x, y, z, tile_name, n=None, speed=2.5, colour=(1, 1, 1)):
        n = n or PARTICLES.get(tier(), 12)
        u0, v0, s = uv_of(tile_name)
        for _ in range(n):
            q = s / 4
            cu, cv = u0 + self.rng.random() * (s - q), v0 + self.rng.random() * (s - q)
            np_ = self.root.attachNewNode(bit_geom(cu, cv, q, colour))
            np_.setPos(x + self.rng.random() * 0.6 + 0.2, y + self.rng.random() * 0.6 + 0.2, z + self.rng.random() * 0.6 + 0.2)
            vel = Vec3(*(self.rng.random(3) - 0.5) * speed)
            vel.z = abs(vel.z) + 1.5
            if look():
                np_.setColor(*line_look.colour(), 1)
            self.bits.append([np_, vel, 0.6 + self.rng.random() * 0.5])

    def update(self, dt):
        keep = []
        for b in self.bits:
            np_, vel, life = b
            life -= dt
            if life <= 0:
                np_.removeNode()
                continue
            vel.z -= 18 * dt
            np_.setPos(np_.getPos() + vel * dt)
            b[2] = life
            keep.append(b)
        self.bits = keep
