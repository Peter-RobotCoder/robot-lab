"""Craft Lab's drawing (CHANGE 200): the world's chunks, the sky (a round sun with a soft glow, a round moon, the
stars and soft puff clouds), the block you look at (a cyan glow outline) and its face dissolving pixel by pixel as
you dig, particles and effects (an Overload Cell armed, its pulse's ring of sparks, a Glitch's streak home), the
creatures and the players, on every graphics tier.

The blocks are drawn by a small shader of Craft Lab's own (GLSL 1.20, so the oldest school laptop runs it): the
atlas's pixels times the corner shading and the light baked into each corner (craft_mesh.py: light 0 to 12,
craft_blocks.LIGHT_MAX), the sky's part of it times the time of day, the glowsticks' part a cool cyan-white and the
same all night, a held Glowfruit's light round the eye (set_held_light); fog into the sky's colour at the edge of the
view. Tiles in craft_blocks.ANIMATED play their frames (4 a second, side by side in the atlas row). The block being
dug loses its pixels to the night-navy (#090c17) in a hashed order as the dig goes 0 to 1 (u_dig: the same pixels
as the texture's own). The day is 15 minutes (craft_game's phases: 9 day, 1 dusk, 4 night, 1 dawn): the sun is up
from the middle of dawn to the middle of dusk, the moon at night, the sky navy with stars.

Every tier draws the same blocks; what changes is how far (VIEW), how smooth (MSAA, from the engine's tier
settings), the sun's shadows (medium and up: a shadow map that follows you, sized as the engine's tiers say),
waving leaves and plants and the water's shimmer (high and ultra), and the clouds (low and up, at two heights; more
of them each tier up). mesh and lines are the engine's looks (engine.line_look): black faces, the blocks' edges in
the line colour, no sky; the outline, the dig (a mask over the block in the line colour) and the effects are drawn
there too. Without the shader (a driver that can't compile it) the dig is the same mask in navy.
"""
import math
import sys

import numpy as np
from panda3d.core import (AntialiasAttrib, CardMaker, ColorBlendAttrib, DirectionalLight, Geom, GeomNode, GeomPoints,
                          GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, InternalName,
                          LineSegs, OrthographicLens, RenderModeAttrib, RenderState, SamplerState, Shader, Texture,
                          TransparencyAttrib, Vec3, Vec4)

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
CLOUDS = {"mesh": 0, "lines": 0, "basic": 0, "low": 9, "medium": 14, "high": 18, "ultra": 26}  # (each of two heights)
PARTICLES = {"mesh": 6, "lines": 6, "basic": 8, "low": 10, "medium": 14, "high": 18, "ultra": 24}
SPARKS = {"mesh": 16, "lines": 16, "basic": 18, "low": 22, "medium": 30, "high": 38, "ultra": 48}
_state = {}

# the brand's colours (the website's tokens)
BG = (0x09 / 255, 0x0c / 255, 0x17 / 255)          # night navy: the sky at night, a dug pixel
CYAN = (0x3e / 255, 0xe9 / 255, 0xff / 255)        # the target's outline, the Overload pulse's sparks
MAGENTA = (0xff / 255, 0x4f / 255, 0xd8 / 255)     # an armed Overload Cell, a Glitch's streak
L = B.LIGHT_MAX
# the light's curve: each level 0.757 of the one above, so 12 (full) is 1 and 0 is as dark as it always was
LIGHT_FALL = 0.8 ** (15.0 / L)
ANIM_FRAMES = 4      # an animated tile's frames, side by side in its atlas row
ANIM_RATE = 4.0      # frames a second

# ---------- the sky through the day ----------
DAY_SECONDS = 900.0     # one day and night (15 minutes), as the server keeps it (craft_game)
DUSK, NIGHT, DAWN = 0.6, 10.0 / 15, 14.0 / 15   # craft_game's phases: day to 0.6, dusk, night, dawn from 0.933
SUNSET = (DUSK + NIGHT) / 2      # the sun goes down in the middle of dusk (0.633)
SUNRISE = (DAWN + 1.0) / 2       # and comes up in the middle of dawn (0.967); noon is 0.3, midnight 0.8
# the sky at the horizon (the fog's colour too) and overhead
SKY_DAY, TOP_DAY = np.array((0.6, 0.78, 0.98)), np.array((0.26, 0.5, 0.94))
SKY_DUSK, TOP_DUSK = np.array((0.98, 0.5, 0.45)), np.array((0.42, 0.24, 0.52))    # coral, magenta-violet above
SKY_DAWN, TOP_DAWN = np.array((0.99, 0.74, 0.47)), np.array((0.42, 0.52, 0.8))    # amber
SKY_NIGHT, TOP_NIGHT = np.array((0.055, 0.075, 0.14)), np.array(BG)               # the site's navy overhead
GLOW_WINDOW = 0.042                        # how long round sunset and sunrise the sky is coloured


def _smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def sun_angle(t):
    """The sun's way round (0 at sunrise, pi at sunset, 1.5 pi at midnight) at the time of day t."""
    up = 1.0 - (SUNRISE - SUNSET)          # (two thirds of the day the sun is up)
    s = (t - SUNRISE) % 1.0
    if s < up:
        return math.pi * s / up
    return math.pi + math.pi * (s - up) / (1.0 - up)


def day_amount(t):
    """1 all day, 0 all night, a smooth step through dusk and dawn."""
    t = t % 1.0
    if t < DUSK:
        return 1.0
    if t < NIGHT:
        return 1.0 - _smooth((t - DUSK) / (NIGHT - DUSK))
    if t < DAWN:
        return 0.0
    return _smooth((t - DAWN) / (1.0 - DAWN))


def sky_look(t):
    """Everything the time of day decides: {daylight 0.14 to 1, day 0 to 1, dusk and dawn (their colours' share),
    sky (r, g, b), sun (its direction)}."""
    t = t % 1.0
    day = day_amount(t)
    dusk = max(0.0, 1.0 - abs(t - SUNSET) / GLOW_WINDOW)
    d_rise = min(abs(t - SUNRISE), abs(t - SUNRISE + 1.0))
    dawn = max(0.0, 1.0 - d_rise / GLOW_WINDOW)
    sky = SKY_NIGHT + (SKY_DAY - SKY_NIGHT) * day
    sky = sky + (SKY_DUSK - sky) * _smooth(dusk) * 0.8
    sky = sky + (SKY_DAWN - sky) * _smooth(dawn) * 0.7
    top = TOP_NIGHT + (TOP_DAY - TOP_NIGHT) * day
    top = top + (TOP_DUSK - top) * _smooth(dusk) * 0.7
    top = top + (TOP_DAWN - top) * _smooth(dawn) * 0.6
    a = sun_angle(t)
    sun_dir = Vec3(math.cos(a) * 0.9, 0.35, math.sin(a))
    sun_dir.normalize()
    return {"daylight": 0.14 + 0.86 * day, "day": day, "dusk": dusk, "dawn": dawn, "sky": tuple(float(c) for c in sky),
            "zenith": tuple(float(c) for c in top), "sun": sun_dir}


def time_look(t):
    """The time of day t (0 to 1: noon 0.3, sunset 0.633, midnight 0.8, sunrise 0.967) as (daylight 0.14 to 1, the
    sky's colour, the sun's direction)."""
    k = sky_look(t)
    return k["daylight"], k["sky"], k["sun"]


# ---------- the shaders ----------
_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
uniform float u_day;
uniform vec3 u_tint;
uniform float u_time;
uniform float u_wave;
uniform vec4 u_held;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
attribute vec4 p3d_Color;
varying vec2 v_uv;
varying vec3 v_light;
varying float v_dist;
varying float v_sunny;
varying vec3 v_cell;
varying float v_face;
#SHADOW_DECL
float level(float x) { return pow(LIGHT_FALL, (1.0 - x) * LIGHT_MAX); }
void main() {
    vec4 p = p3d_Vertex;
    float flags = floor(p3d_Color.a * 255.0 + 0.5);
    float face = floor(flags / 32.0);
    float low = mod(flags, 32.0);
    float wave = low >= 16.0 ? 1.0 : 0.0;
    float anim = mod(low, 16.0) >= 8.0 ? 1.0 : 0.0;
    if (u_wave > 0.5 && wave > 0.5) {
        p.x += sin(u_time * 1.7 + p.y * 0.9 + p.z) * 0.04;
        p.y += cos(u_time * 1.3 + p.x * 0.8) * 0.04;
    }
    gl_Position = p3d_ModelViewProjectionMatrix * p;
    vec2 uv = p3d_MultiTexCoord0;
    uv.x += anim * mod(floor(u_time * ANIM_RATE), ANIM_FRAMES) * TILE_U;
    v_uv = uv;
    float sky = level(p3d_Color.g) * u_day;
    float blk = p3d_Color.b > 0.01 ? level(p3d_Color.b) : 0.0;
    vec3 world = (p3d_ModelMatrix * p).xyz;
    float held = u_held.w - distance(world, u_held.xyz);
    blk = held > 0.0 ? max(blk, level(held / LIGHT_MAX)) : blk;
    vec3 l = max(vec3(sky) * u_tint, vec3(blk * 0.84, blk * 0.95, blk));
    v_light = max(l, vec3(0.045)) * p3d_Color.r;
    v_sunny = p3d_Color.g * u_day;
    vec3 n = face < 0.5 ? vec3(1.0, 0.0, 0.0) : face < 1.5 ? vec3(-1.0, 0.0, 0.0) : face < 2.5 ? vec3(0.0, 1.0, 0.0) :
             face < 3.5 ? vec3(0.0, -1.0, 0.0) : face < 4.5 ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 0.0, -1.0);
    v_cell = world - n * 0.02;
    v_face = face;
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
uniform float u_time;
uniform vec4 u_dig;
varying vec2 v_uv;
varying vec3 v_light;
varying float v_dist;
varying float v_sunny;
varying vec3 v_cell;
varying float v_face;
#SHADOW_DECL
float hash(vec2 q) {
    vec3 p3 = fract(vec3(q.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
void main() {
    vec4 t = texture2D(p3d_Texture0, v_uv);
    if (t.a < u_cut) discard;
    vec3 c = t.rgb * v_light;
    float a = t.a * u_alpha;
#SHADOW_FRAG
    if (u_dig.w > 0.0) {
        vec3 d = abs(floor(v_cell) - u_dig.xyz);
        if (d.x + d.y + d.z < 0.5) {
            vec2 px = floor(v_uv * ATLAS_PX);
            float h = hash(px + vec2(v_face * 41.0, v_face * 13.0));
            if (h < u_dig.w) {
                c = vec3(BG_RGB);
                a = 1.0;
            } else if (h < u_dig.w + 0.12 && hash(px + vec2(floor(u_time * 10.0) * 7.0, 3.0)) > 0.55) {
                c = mix(c, vec3(BG_RGB), 0.7);
            }
        }
    }
    float f = clamp((v_dist - u_fog.x) / (u_fog.y - u_fog.x), 0.0, 1.0);
    gl_FragColor = vec4(mix(c, u_fog_colour, f), a);
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
uniform mat4 p3d_ModelMatrix;
uniform float u_day;
uniform vec3 u_tint;
uniform vec2 u_here;
uniform vec4 u_flash;
uniform vec4 u_held;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
attribute vec4 p3d_Color;
varying vec2 v_uv;
varying vec3 v_light;
varying vec4 v_col;
varying float v_dist;
float level(float x) { return pow(LIGHT_FALL, (1.0 - x) * LIGHT_MAX); }
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
    float sky = level(u_here.x) * u_day;
    float blk = u_here.y > 0.01 ? level(u_here.y) : 0.0;
    float held = u_held.w - distance((p3d_ModelMatrix * p3d_Vertex).xyz, u_held.xyz);
    blk = held > 0.0 ? max(blk, level(held / LIGHT_MAX)) : blk;
    v_light = max(max(vec3(sky) * u_tint, vec3(blk * 0.84, blk * 0.95, blk)), vec3(0.06));
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


def _source(text):
    """A shader's text with Craft Lab's numbers filled in."""
    atlas_px = _state.get("atlas_px", B.ATLAS * B.TILE)
    for k, v in (("LIGHT_FALL", f"{LIGHT_FALL:.6f}"), ("LIGHT_MAX", f"{float(L):.1f}"),
                 ("ANIM_RATE", f"{ANIM_RATE:.1f}"), ("ANIM_FRAMES", f"{float(ANIM_FRAMES):.1f}"),
                 ("TILE_U", f"{1.0 / B.ATLAS:.8f}"), ("ATLAS_PX", f"{float(atlas_px):.1f}"),
                 ("BG_RGB", ", ".join(f"{c:.5f}" for c in BG))):
        text = text.replace(k, v)
    return text


def _format():
    arr = GeomVertexArrayFormat()
    arr.addColumn(InternalName.getVertex(), 3, Geom.NT_float32, Geom.C_point)
    arr.addColumn(InternalName.getTexcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
    arr.addColumn(InternalName.getColor(), 4, Geom.NT_uint8, Geom.C_color)
    return GeomVertexFormat.registerFormat(arr)


def _fx_format():
    arr = GeomVertexArrayFormat()
    arr.addColumn(InternalName.getVertex(), 3, Geom.NT_float32, Geom.C_point)
    arr.addColumn(InternalName.getColor(), 4, Geom.NT_float32, Geom.C_color)
    return GeomVertexFormat.registerFormat(arr)


FORMAT = None
FX_FORMAT = None


def tier():
    return _state.get("tier", gfx_tiers.DEFAULT)


def look():
    return tier() in gfx_tiers.LOOKS


def shaded():
    """The blocks drawn by Craft Lab's shader (every tier but the looks, where the driver could compile it)."""
    return not look() and _state.get("shader") is not None


def view_distance():
    return VIEW.get(tier(), 112)


def line_px():
    """A thin line's width in pixels for this window (2 at 720 rows)."""
    try:
        h = _state["base"].win.getYSize()
    except Exception:
        h = 720
    return max(1.0, h / 720.0)


# ---------- the start ----------
def init(base, tier_wanted="medium", line_colour=None):
    """The tier's drawing: the atlas, the shaders, the sun (and its shadow map on medium and up), the sky, the fog.
    Returns the tier used (a driver that can't compile the shadow shader gets medium's look without shadows)."""
    global FORMAT, FX_FORMAT
    FORMAT = FORMAT or _format()
    FX_FORMAT = FX_FORMAT or _fx_format()
    quality = tier_wanted if tier_wanted in TIERS else gfx_tiers.DEFAULT
    _state.clear()
    line_look.reset()
    _state.update(tier=quality, base=base, time=0.3, wave_t=0.0)
    atlas, where = craft_art.build_atlas()
    _state["where"] = where
    _state["atlas_px"] = atlas.shape[1]
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
    try:
        _state["ent_shader"] = Shader.make(Shader.SL_GLSL, _source(_ENT_VERT), _source(_ENT_FRAG))
    except Exception:
        _state["ent_shader"] = None
    # (what changes every frame is set once on render, and every shaded node below it sees it)
    base.render.setShaderInput("u_time", 0.0)
    base.render.setShaderInput("u_held", Vec4(0, 0, -1000, 0))
    base.render.setShaderInput("u_dig", Vec4(0, 0, -1000, 0))
    if s["msaa"]:
        base.render.setAntialias(AntialiasAttrib.MMultisample)
    _state["sky"] = Sky(base, quality)
    set_time(base, 0.3)
    return quality


def make_shader(shadow):
    vert, frag = _source(_VERT), _source(_FRAG)
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


def image_texture(rgba, name, smooth=True):
    """A small picture made here (the sun, the moon, a cloud, a spark) as a texture: rgba (h, w, 4) floats 0..1, the
    top row first."""
    img = (np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8)
    tex = Texture(name)
    tex.setup2dTexture(img.shape[1], img.shape[0], Texture.T_unsigned_byte, Texture.F_rgba8)
    tex.setRamImageAs(np.ascontiguousarray(img[::-1]).tobytes(), "RGBA")
    if smooth:
        tex.setMagfilter(SamplerState.FT_linear)
        tex.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    else:
        tex.setMagfilter(SamplerState.FT_nearest)
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
    """The time of day (0 to 1, craft_game's day_t: noon 0.3, dusk from 0.6, night from 0.667, dawn from 0.933): the
    daylight in the shaders, the sky's colour, the fog, the sun, the moon, the stars and the clouds' colour."""
    _state["time"] = t % 1.0
    k = sky_look(t)
    _state["sky_look"] = k
    daylight, sky, sun_dir = k["daylight"], k["sky"], k["sun"]
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
        _state["sky"].update(k)


def apply_inputs(np_, cut=None, alpha=None):
    v = VIEW[tier()]
    np_.setShaderInput("u_day", float(_state.get("daylight", 1.0)))
    np_.setShaderInput("u_tint", Vec3(*_state.get("tint", (1, 1, 1))))
    np_.setShaderInput("u_fog_colour", Vec3(*_state.get("sky_colour", SKY_DAY)))
    np_.setShaderInput("u_fog", (v * 0.62, v * 0.98))
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
    top = np_.getTop()  # (a scene of its own, the hand's: render's inputs don't reach it, so it gets them too)
    base = _state.get("base")
    if base is not None and top != base.render:
        roots = _state.setdefault("roots", [])
        if not any(r == top for r in roots):
            roots.append(top)
            for name in ("u_time", "u_dig"):
                top.setShaderInput(base.render.getShaderInput(name))
            held = _state.get("held", (0.0, 0.0, -1000.0, 0.0))
            top.setShaderInput("u_held", Vec4(0.0, 0.0, 0.0, held[3]) if held[3] > 0 else Vec4(*held))


def set_here(np_, world, x, y, z):
    """A creature's light: the sky's and the glowsticks' at its feet (0 to 1: the level over LIGHT_MAX)."""
    if look() or np_.isEmpty():
        return
    xi, yi, zi = int(math.floor(x)), int(math.floor(y)), int(math.floor(z + 0.5))
    if world.inside(xi, yi, zi):
        np_.setShaderInput("u_here", (float(world.sky[xi, yi, zi]) / L, float(world.glow[xi, yi, zi]) / L))


def set_held_light(level, pos=None):
    """A light carried (a Glowfruit held: level 6): the blocks, creatures and the hand near pos (the eye, in the
    world; None: the camera) lit as block light falling off a level a block from it. level 0: none. Every frame is
    fine (one input on render); the looks have no light to give."""
    base = _state.get("base")
    if base is None or not shaded():
        return
    level = max(0.0, min(float(L), float(level or 0)))
    if level <= 0:
        value = (0.0, 0.0, -1000.0, 0.0)
    else:
        if pos is None:
            pos = base.camera.getPos(base.render)
        value = (float(pos[0]), float(pos[1]), float(pos[2]), level)
    if _state.get("held") != value:
        _state["held"] = value
        base.render.setShaderInput("u_held", Vec4(*value))
        for top in _state.get("roots", []):  # (the hand's scene has its own frame: the light is at its eye, the origin)
            top.setShaderInput("u_held", Vec4(0.0, 0.0, 0.0, value[3]) if value[3] > 0 else Vec4(*value))


def flash(np_, on):
    if not look() and not np_.isEmpty():
        np_.setShaderInput("u_flash", Vec4(1, 0.15, 0.15, 0.55 if on else 0.0))


def tick(base, dt, cam_pos):
    """Every frame: the shaders' clock (waving leaves, animated tiles, the dig's blinking pixels), the sun's shadow
    over the player, the clouds drifting."""
    _state["wave_t"] = _state.get("wave_t", 0.0) + dt
    if shaded():
        for top in [base.render] + _state.get("roots", []):
            top.setShaderInput("u_time", float(_state["wave_t"] % 3600.0))
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
        _state["world"] = world  # (the target's outline fits the block's shape)
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
        if _state.get("world") is self.world:
            _state.pop("world", None)
        self.root.removeNode()


# ---------- pictures made here ----------
def _grid(n):
    """Each pixel's centre from -1 to 1 across an n x n picture, as (x, y) with y up."""
    c = (np.arange(n) + 0.5) / n * 2 - 1
    x, y = np.meshgrid(c, -c)
    return x, y


def sun_image(n=128):
    """The sun: a round white-gold disc, its edge smooth, in a soft warm glow that fades to nothing."""
    x, y = _grid(n)
    r = np.hypot(x, y)
    disc = np.clip((0.34 - r) / 0.025, 0, 1)
    glow = np.clip(1 - (r - 0.3) / 0.7, 0, 1) ** 2.4 * 0.7
    img = np.zeros((n, n, 4))
    img[..., 0] = 1.0
    img[..., 1] = 0.82 + 0.16 * disc
    img[..., 2] = 0.5 + 0.42 * disc
    img[..., 3] = np.maximum(disc, glow)
    return img


def moon_image(n=128):
    """The moon: a round pale disc with a few soft grey seas, in a faint cool glow."""
    x, y = _grid(n)
    r = np.hypot(x, y)
    disc = np.clip((0.6 - r) / 0.03, 0, 1)
    shade = np.ones_like(r)
    for cx, cy, cr in ((-0.18, 0.16, 0.17), (0.2, -0.1, 0.12), (0.05, 0.3, 0.08), (-0.1, -0.28, 0.1)):
        shade -= 0.16 * np.clip(1 - np.hypot(x - cx, y - cy) / cr, 0, 1) ** 0.6
    shade -= 0.12 * np.clip((x + y) * 0.5 + 0.2, 0, 1) * disc  # (a little darker on one side: it is a ball)
    glow = np.clip(1 - (r - 0.58) / 0.42, 0, 1) ** 2.5 * 0.3
    img = np.zeros((n, n, 4))
    img[..., 0] = np.where(disc > 0, 0.84 * shade, 0.62)
    img[..., 1] = np.where(disc > 0, 0.89 * shade, 0.8)
    img[..., 2] = np.where(disc > 0, 0.98 * shade, 1.0)
    img[..., 3] = np.maximum(disc, glow)
    return img


CLOUD_ASPECT = 3.0   # a cloud card is three times as wide as it is high


def cloud_image(rng, w=256, h=128):
    """A cloud seen from the side: soft round puffs heaped on a flat bottom (a big one in the middle, smaller ones
    either side, joined), white on top, a cool grey below."""
    ys, xs = np.mgrid[0:h, 0:w]
    y = (h - 1 - ys + 0.5) / h      # (0 at the bottom row, 1 at the top)
    x = (xs + 0.5) / w * CLOUD_ASPECT  # (the card's own units: a circle here is a circle on the card)
    field = np.zeros((h, w))
    span = rng.uniform(0.55, 0.7) * CLOUD_ASPECT

    def puff(cx, cy, rad, sharp):   # (blobs that melt into each other where they meet: one soft heap, no seams)
        return np.exp(-(np.hypot(x - cx, y - cy) / rad) ** 2 * sharp)
    # the body: a long low capsule (its bottom is the cloud's flat base)
    half = span * 0.5 - 0.16
    dx = np.maximum(0.0, np.abs(x - CLOUD_ASPECT / 2) - half)
    field += np.exp(-(np.hypot(dx, y - 0.27) / 0.2) ** 2 * 1.3)
    k = int(rng.integers(4, 7))
    for i in range(k):   # the round tops, biggest in the middle
        f = (i + 0.5) / k
        mid = 1 - abs(f - 0.5) * 2
        rad = 0.14 + 0.2 * mid + rng.uniform(-0.02, 0.03)
        cx = CLOUD_ASPECT / 2 + half * (f * 2 - 1) * 0.9 + rng.uniform(-0.03, 0.03)
        field += puff(cx, 0.3 + rad * 0.6, rad, 3.0)
    field *= np.clip((y - 0.12) / 0.05, 0, 1)   # (the flat bottom)
    s = np.clip((field - 0.42) / 0.14, 0, 1)
    a = s * s * (3 - 2 * s) * 0.94
    light = 0.78 + 0.22 * np.clip((y - 0.14) / 0.5, 0, 1)
    img = np.zeros((h, w, 4))
    img[..., 0] = light * 0.97
    img[..., 1] = light * 0.98
    img[..., 2] = np.minimum(1.0, light * 1.02 + 0.02)
    img[..., 3] = a
    return img


def ring_image(n=128):
    """The Overload pulse's ring: a thin bright cyan circle with a soft glow either side."""
    x, y = _grid(n)
    r = np.hypot(x, y)
    band = np.exp(-((r - 0.92) / 0.03) ** 2) + 0.3 * np.exp(-((r - 0.9) / 0.07) ** 2)
    img = np.zeros((n, n, 4))
    img[..., 0] = CYAN[0] + (1 - CYAN[0]) * np.clip(band - 0.6, 0, 1)
    img[..., 1] = CYAN[1]
    img[..., 2] = CYAN[2]
    img[..., 3] = np.clip(band, 0, 1) * (r < 1)
    return img


def dot_image(n=32):
    """A soft round glow (the pulse's flash)."""
    x, y = _grid(n)
    r = np.hypot(x, y)
    img = np.ones((n, n, 4))
    img[..., 3] = np.clip(1 - r, 0, 1) ** 2
    return img


def _add_blend(np_):
    """Light added to what's behind (a glow: it brightens, never darkens)."""
    cb = ColorBlendAttrib
    np_.setAttrib(cb.make(cb.M_add, cb.O_incoming_alpha, cb.O_one))
    np_.setDepthWrite(False)
    return np_


def _card(parent, name, half, tex, w_half=None):
    cm = CardMaker(name)
    w = half if w_half is None else w_half
    cm.setFrame(-w, w, -half, half)
    np_ = parent.attachNewNode(cm.generate())
    np_.setTexture(tex)
    return np_


# ---------- the sky ----------
class Sky:
    """The sun (a round disc in a soft glow) and the moon (round, opposite it) crossing the sky with the time of day,
    the stars at night, the clouds (soft puffs at two heights, drifting east, facing you). The sun, moon and stars
    are behind everything and follow the camera; the clouds sit over the island round you."""

    def __init__(self, base, quality):
        self.base = base
        self.root = base.camera.attachNewNode("sky")
        self.root.setCompass()  # (turns with nothing: only the camera's position)
        self.root.setBin("background", 0)
        self.root.setDepthWrite(False)
        self.root.setDepthTest(False)
        self.root.setLightOff(1)
        self.root.setFogOff(1)
        self.root.setShaderOff(1)
        self.root.setTransparency(TransparencyAttrib.M_alpha)
        # (inside the far plane on every tier: at 250 m the sun, moon and stars were clipped away below ultra)
        self.r = min(250.0, base.camLens.getFar() * 0.8)
        k = self.r / 250.0
        # the sky deepening overhead: a dome whose colour (the zenith's) fades out to the horizon's (the background)
        self.dome = self.root.attachNewNode(self.dome_node(self.r))
        self.dome.setBin("background", 0)
        self.dome.setTwoSided(True)
        self.halo = _card(self.root, "halo", 95 * k, image_texture(dot_image(64), "halo"))
        self.halo.setBillboardPointEye()
        self.halo.setBin("background", 1)
        _add_blend(self.halo)
        self.stars = self.root.attachNewNode(self.star_node(self.r * 0.98))
        self.stars.setBin("background", 1)
        self.moon = _card(self.root, "moon", 11 * k, image_texture(moon_image(), "moon"))
        self.moon.setBillboardPointEye()
        self.moon.setBin("background", 2)
        self.sun = _card(self.root, "sun", 18 * k, image_texture(sun_image(), "sun"))
        self.sun.setBillboardPointEye()
        self.sun.setBin("background", 3)
        _add_blend(self.sun)
        self.clouds = []      # [node, x, y (on the wrap), layer, width]
        self.cloud_root = base.render.attachNewNode("clouds")
        cr = self.cloud_root
        cr.setTransparency(TransparencyAttrib.M_alpha)
        cr.setDepthWrite(False)
        cr.setBin("transparent", 20)
        cr.setLightOff(1)
        cr.setShaderOff(1)
        cr.setFogOff(1)
        cr.setTwoSided(True)
        n = CLOUDS.get(quality, 0)
        # (the clouds reach out as far as the far plane allows, with room above the camera for their height)
        self.span = max(60.0, base.camLens.getFar() * 0.72)
        if n:
            rng = np.random.default_rng(5)
            texes = [image_texture(cloud_image(rng), f"cloud {i}") for i in range(4)]
            for layer in range(2):
                for i in range(n):
                    w = rng.uniform(16, 30) * (1.0 if layer == 0 else 1.3)
                    np_ = _card(cr, "cloud", w / CLOUD_ASPECT, texes[int(rng.integers(0, 4))], w_half=w)
                    np_.setBillboardPointEye()
                    x, y = rng.uniform(-self.span, self.span, 2)
                    self.clouds.append([np_, float(x), float(y), layer, w])
        self.drift = 0.0
        self.cloud_colour = (1.0, 1.0, 1.0)
        self.cam = None

    @staticmethod
    def dome_node(radius):
        """A half sphere, white, see-through at the horizon and solid overhead (its colour is set by the time)."""
        from panda3d.core import GeomVertexWriter
        vdata = GeomVertexData("dome", GeomVertexFormat.getV3c4(), Geom.UH_static)
        v, c = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color")
        rings = (0, 4, 9, 16, 25, 37, 52, 70, 90)
        seg = 24
        for el in rings:
            e = math.radians(el)
            a = _smooth(math.sin(e) / 0.75) ** 0.9
            for i in range(seg + 1):
                az = i / seg * 2 * math.pi
                ce = math.cos(e) * radius
                v.addData3(ce * math.cos(az), ce * math.sin(az), math.sin(e) * radius)
                c.addData4(1, 1, 1, a)
        tris = GeomTriangles(Geom.UH_static)
        for r in range(len(rings) - 1):
            for i in range(seg):
                p, q = r * (seg + 1) + i, (r + 1) * (seg + 1) + i
                tris.addVertices(p, p + 1, q + 1)
                tris.addVertices(p, q + 1, q)
        g = Geom(vdata)
        g.addPrimitive(tris)
        node = GeomNode("dome")
        node.addGeom(g)
        return node

    @staticmethod
    def star_node(radius=300.0):
        """Five hundred stars, a few of them bigger, white with a touch of the club's cyan."""
        from panda3d.core import GeomVertexWriter
        rng = np.random.default_rng(3)
        node = GeomNode("stars")
        for size, count in ((1.0, 440), (2.0, 60)):
            vdata = GeomVertexData("stars", GeomVertexFormat.getV3c4(), Geom.UH_static)
            v, c = GeomVertexWriter(vdata, "vertex"), GeomVertexWriter(vdata, "color")
            pts = GeomPoints(Geom.UH_static)
            for i in range(count):
                d = rng.normal(size=3)
                d[2] = abs(d[2]) + 0.04
                d = d / np.linalg.norm(d) * radius
                v.addData3(*d)
                b = 0.55 + rng.random() * 0.45
                cyan = rng.random() < 0.25
                c.addData4(b * (0.75 if cyan else 1.0), b, b, 1)
                pts.addVertex(i)
            g = Geom(vdata)
            g.addPrimitive(pts)
            node.addGeom(g, RenderState.make(RenderModeAttrib.make(RenderModeAttrib.M_unchanged, size * line_px())))
        return node

    def update(self, k):
        """The time of day's look (sky_look): where the sun and moon are, how bright, the stars, the clouds' colour."""
        sun_dir = k["sun"]
        self.sun.setPos(sun_dir * self.r * 0.9)
        self.moon.setPos(-sun_dir * self.r * 0.9)
        self.dome.setColorScale(*k["zenith"], 1)
        glow = max(_smooth(k["dusk"]), _smooth(k["dawn"]))
        self.halo.setPos(sun_dir * self.r * 0.88)
        hc = SKY_DUSK if k["dusk"] >= k["dawn"] else SKY_DAWN
        self.halo.setColorScale(float(hc[0]), float(hc[1]), float(hc[2]), 0.55 * glow)
        self.halo.show() if glow > 0.01 else self.halo.hide()
        up = max(0.0, min(1.0, (sun_dir.z + 0.06) * 8))
        low = max(0.0, min(1.0, sun_dir.z * 3))   # (low in the sky: warmer)
        self.sun.setColorScale(1.0, 0.72 + 0.28 * low, 0.5 + 0.5 * low, up)
        self.sun.show() if up > 0.01 else self.sun.hide()
        mup = max(0.0, min(1.0, (-sun_dir.z + 0.06) * 8)) * (0.35 + 0.65 * (1 - k["day"]))
        self.moon.setColorScale(1, 1, 1, mup)
        self.moon.show() if mup > 0.01 else self.moon.hide()
        night = max(0.0, 1.0 - k["day"] * 1.6)
        self.stars.setAlphaScale(night)
        self.stars.show() if night > 0.02 else self.stars.hide()
        day = k["day"]
        night_c = np.array((0.16, 0.2, 0.32))
        c = night_c + (np.ones(3) - night_c) * day
        c = c + (np.array((1.0, 0.62, 0.72)) - c) * _smooth(k["dusk"]) * 0.55
        c = c + (np.array((1.0, 0.8, 0.6)) - c) * _smooth(k["dawn"]) * 0.5
        self.cloud_colour = tuple(float(v) for v in c)
        self.cloud_root.setColorScale(*self.cloud_colour, 1)

    def follow(self, cam_pos, dt):
        """The clouds drift east and wrap round the camera, fading out at the edge of the sky they fill."""
        if cam_pos is None or not self.clouds:
            return
        self.drift += dt * 1.2
        span = self.span
        world = _state.get("world")
        base_z = max(78.0, (world.Z + 12.0) if world is not None else 78.0)
        for cl in self.clouds:
            np_, x, y, layer, w = cl
            speed = 1.0 + layer * 0.5
            dx = (x + self.drift * speed - cam_pos.x + span) % (2 * span) - span
            dy = (y - cam_pos.y + span) % (2 * span) - span
            d = math.hypot(dx, dy)
            a = max(0.0, min(1.0, (span - d) / (span * 0.35)))
            if a <= 0.01:
                np_.hide()
                continue
            np_.show()
            np_.setPos(cam_pos.x + dx, cam_pos.y + dy, base_z + layer * 16)
            np_.setAlphaScale(a * (0.95 if layer == 0 else 0.75))


# ---------- the block you look at, and the dig ----------
def block_bounds(block):
    """The box the outline goes round: the block's own shape (a step is half high, a glowstick thin), as (lo, hi)
    in the block."""
    world = _state.get("world")
    full = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    if world is None:
        return full
    x, y, z = (int(v) for v in block)
    try:
        if not world.inside(x, y, z):
            return full
        b = B.BLOCKS[int(world.blocks[x, y, z])]
        meta = int(world.meta[x, y, z])
    except Exception:
        return full
    shape = b.get("shape")
    if shape == "slab":
        return (0, 0, 0), (1, 1, 0.5)
    if shape == "bed":
        return (0, 0, 0), (1, 1, 0.6)
    if shape == "farmland":
        return (0, 0, 0), (1, 1, 0.875)
    if shape == "torch":
        return (0.38, 0.38, 0), (0.62, 0.62, 0.7)
    if shape == "cross":
        return (0.15, 0.15, 0), (0.85, 0.85, 0.95)
    if shape == "crop":
        return (0, 0, 0), (1, 1, 0.9)
    if shape == "ladder":
        face = meta % 4
        return ([(0.9, 0, 0), (0, 0, 0), (0, 0.9, 0), (0, 0, 0)][face],
                [(1, 1, 1), (0.1, 1, 1), (1, 1, 1), (1, 0.1, 1)][face])
    if shape == "door":
        side = ((meta & 3) + (1 if meta & 4 else 0)) % 4
        return [((0, 0, 0), (0.19, 1, 1)), ((0, 0.81, 0), (1, 1, 1)), ((0.81, 0, 0), (1, 1, 1)),
                ((0, 0, 0), (1, 0.19, 1))][side]
    return full


def _box_lines(name, thickness, colour):
    ls = LineSegs(name)
    ls.setThickness(thickness)
    ls.setColor(*colour)
    for (a, b) in (((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 1, 0)), ((1, 1, 0), (0, 1, 0)), ((0, 1, 0), (0, 0, 0)),
                   ((0, 0, 1), (1, 0, 1)), ((1, 0, 1), (1, 1, 1)), ((1, 1, 1), (0, 1, 1)), ((0, 1, 1), (0, 0, 1)),
                   ((0, 0, 0), (0, 0, 1)), ((1, 0, 0), (1, 0, 1)), ((1, 1, 0), (1, 1, 1)), ((0, 1, 0), (0, 1, 1))):
        ls.moveTo(*a)
        ls.drawTo(*b)
    return ls.create()


def _face_box(name, uv=True):
    """A unit cube's six faces (outward), each with the texture's whole square on it."""
    from panda3d.core import GeomVertexWriter
    vdata = GeomVertexData(name, GeomVertexFormat.getV3t2() if uv else GeomVertexFormat.getV3(), Geom.UH_static)
    v = GeomVertexWriter(vdata, "vertex")
    tw = GeomVertexWriter(vdata, "texcoord") if uv else None
    tris = GeomTriangles(Geom.UH_static)
    for d in range(6):
        for k, corner in enumerate(M.CORNERS[d]):
            v.addData3(*corner)
            if tw is not None:
                tw.addData2(*M.UV[k])
        b = d * 4
        tris.addVertices(b, b + 1, b + 2)
        tris.addVertices(b, b + 2, b + 3)
    g = Geom(vdata)
    g.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(g)
    return node


class Target:
    """The block you look at: a cyan glow outline round it (about 2 pixels, pulsing gently), and as you dig its faces
    dissolve, pixel by pixel, to the night navy. With the blocks' shader the dissolve is the block's own texture's
    pixels (u_dig); on the looks, or without the shader, a 16 x 16 mask over the block does it (in the line colour on
    the looks, navy elsewhere)."""

    PULSE = 1.1   # the outline's breaths a second

    def __init__(self, render):
        self.render = render
        self.root = render.attachNewNode("target")
        self.root.setLightOff(1)
        self.root.setShaderOff(1)
        self.root.setTextureOff(1)
        self.root.setTransparency(TransparencyAttrib.M_alpha)
        self.root.setDepthWrite(False)
        self.root.setBin("fixed", 42)  # (after the world, its water and its lines: drawn over, never under)
        px = line_px()
        self.frame = self.root.attachNewNode("frame")
        self.glow = self.frame.attachNewNode(_box_lines("target glow", 6.0 * px, (*CYAN, 1)))
        self.glow.setAntialias(AntialiasAttrib.MLine)
        self.core = self.frame.attachNewNode(_box_lines("target", 2.0 * px, (*CYAN, 1)))
        self.core.setAntialias(AntialiasAttrib.MLine)
        self.root.hide()
        self.mask = None
        if not shaded():
            self.mask = render.attachNewNode(_face_box("dig mask"))
            self.mask_tex = image_texture(np.zeros((16, 16, 4)), "dig mask", smooth=False)
            self.mask.setTexture(self.mask_tex, 1)
            self.mask.setTransparency(TransparencyAttrib.M_alpha)
            self.mask.setShaderOff(1)
            self.mask.setLightOff(1)
            self.mask.setDepthOffset(2)
            self.mask.setDepthWrite(False)
            self.mask.setBin("fixed", 41)
            self.mask.hide()
            self.order = np.random.default_rng(7).random((16, 16))
        self.stage = None
        self.dig = None
        self.block = None

    def _set_dig(self, value):
        if value != self.dig:
            self.dig = value
            for top in [self.render] + _state.get("roots", []):
                top.setShaderInput("u_dig", Vec4(*value))

    def show(self, block, progress):
        """block: (x, y, z) or None; progress: the dig, 0 to 1. Called every frame (the outline breathes)."""
        if block is None:
            self.root.hide()
            self.block = None
            if self.mask is not None:
                self.mask.hide()
            elif shaded():
                self._set_dig((0.0, 0.0, -1000.0, 0.0))
            return
        bx, by, bz = (int(math.floor(v)) for v in block)
        if self.block != (bx, by, bz):
            self.block = (bx, by, bz)
            lo, hi = block_bounds(self.block)
            e = 0.004
            self.lo = Vec3(bx + lo[0] - e, by + lo[1] - e, bz + lo[2] - e)
            self.size = Vec3(hi[0] - lo[0] + 2 * e, hi[1] - lo[1] + 2 * e, hi[2] - lo[2] + 2 * e)
            self.frame.setPos(self.lo)
            self.frame.setScale(self.size)
        self.root.show()
        try:
            from direct.showbase.ShowBaseGlobal import globalClock
            now = globalClock.getFrameTime()
        except Exception:
            now = 0.0
        breath = 0.5 + 0.5 * math.sin(now * self.PULSE * 2 * math.pi)
        self.core.setAlphaScale(0.75 + 0.25 * breath)
        self.glow.setAlphaScale(0.22 + 0.22 * breath)
        progress = max(0.0, min(1.0, float(progress or 0)))
        if self.mask is None:
            if shaded():
                self._set_dig((float(bx), float(by), float(bz), progress * 0.97 if progress > 0 else 0.0))
            return
        if progress <= 0:
            self.mask.hide()
            return
        self.mask.setPos(self.lo)
        self.mask.setScale(self.size)
        self.mask.show()
        stage = (int(progress * 32), int(now * 10))
        if stage != self.stage:
            self.stage = stage
            gone = self.order < progress * 0.97
            blink = (self.order < progress + 0.12) & ~gone & \
                (np.random.default_rng(stage[1]).random((16, 16)) > 0.55)
            colour = line_look.colour() if look() else BG
            img = np.zeros((16, 16, 4))
            img[..., :3] = colour
            img[..., 3] = np.where(gone, 1.0, np.where(blink, 0.5, 0.0))
            self.mask_tex.setRamImageAs(np.ascontiguousarray((img[::-1] * 255).astype(np.uint8)).tobytes(), "RGBA")


# ---------- effects: the Overload Cell, its pulse, a Glitch going home ----------
_CUBE = (M.CORNERS - 0.5).reshape(-1, 3).astype(np.float32)   # (24, 3): a little cube's corners round its middle
_CUBE_IDX = (np.array([0, 1, 2, 0, 2, 3], np.uint32)[None] + (np.arange(6, dtype=np.uint32) * 4)[:, None]).ravel()
_FX_VERTEX = np.dtype([("pos", np.float32, 3), ("c", np.float32, 4)])


class _Sparks:
    """n little glowing cubes in one node, moved every frame from numpy (one draw, however many)."""

    def __init__(self, parent, n, name="sparks"):
        self.n = n
        vdata = GeomVertexData(name, FX_FORMAT or _fx_format(), Geom.UH_dynamic)
        vdata.uncleanSetNumRows(n * 24)
        self.vdata = vdata
        tris = GeomTriangles(Geom.UH_static)
        tris.setIndexType(Geom.NT_uint32)
        idx = (_CUBE_IDX[None] + (np.arange(n, dtype=np.uint32) * 24)[:, None]).ravel()
        tris.modifyVertices().modifyHandle().setData(idx.astype(np.uint32).tobytes())
        g = Geom(vdata)
        g.addPrimitive(tris)
        node = GeomNode(name)
        node.addGeom(g)
        self.np = parent.attachNewNode(node)
        self.buf = np.zeros(n * 24, _FX_VERTEX)

    def set(self, pos, size, colour):
        """pos (n, 3), size (n,) metres, colour (n, 4) 0..1."""
        self.buf["pos"] = (pos[:, None, :] + _CUBE[None] * np.asarray(size, np.float32)[:, None, None]).reshape(-1, 3)
        self.buf["c"] = np.repeat(np.clip(colour, 0, 1).astype(np.float32), 24, axis=0)
        self.vdata.modifyArray(0).modifyHandle().setData(self.buf.tobytes())


class Effects:
    """What the Overload Cell and the Glitches show (called by the client; update(dt) every frame):

        armed(x, y, z, seconds)   the cell at block (x, y, z) armed: a magenta glow round it, pulsing about three
                                  times a second and faster as it nears the pulse
        disarm(x, y, z)           that glow gone at once (the cell dug, or its pulse come)
        ring(x, y, z, radius)     the pulse from block (x, y, z) (or any point in it: it centres on the block's
                                  middle): a cyan ring and sparks out to radius in half a second, the cell's glow gone
        streak(x0, y0, z0, x1, y1, z1)   a magenta streak from a Glitch (a point in the world) to its rift, 0.4 s
        clear()                   everything gone (a new world)

    All of it is glowing colour added over the picture, no lights, textures of the world or shaders: the same on
    every tier (the looks too: lines and sparks in the brand's colours over the black)."""

    RING_TIME = 0.5
    STREAK_TIME = 0.4

    def __init__(self, render):
        self.render = render
        self.root = render.attachNewNode("effects")
        self.root.setLightOff(1)
        self.root.setShaderOff(1)
        self.root.setFogOff(1)
        self.root.setBin("fixed", 40)
        self.root.setTransparency(TransparencyAttrib.M_alpha)
        self.root.setDepthWrite(False)
        self.cells = {}      # (x, y, z) -> [node, seconds left, seconds in all, phase]
        self.rings = []      # [root, sparks, card, flash, t, radius, directions, speeds, rises]
        self.streaks = []    # [root, core LineSegs, glow LineSegs, head sparks, t, a, b]
        self.rng = np.random.default_rng(11)
        self._ring_tex = None
        self._dot_tex = None
        self.box_geom = _face_box("armed", uv=False)

    # -- the armed cell --
    def armed(self, x, y, z, seconds=3.0):
        key = (math.floor(x), math.floor(y), math.floor(z))
        self.disarm(*key)
        np_ = self.root.attachNewNode("armed")
        faces = np_.attachNewNode(self.box_geom.makeCopy())
        faces.setColor(*MAGENTA, 1)
        faces.setTwoSided(True)
        edges = np_.attachNewNode(_box_lines("armed edges", 2.0 * line_px(), (*MAGENTA, 1)))
        edges.setAntialias(AntialiasAttrib.MLine)
        np_.setPos(key[0] + 0.5, key[1] + 0.5, key[2] + 0.5)
        for part in (faces, edges):
            part.setPos(-0.5, -0.5, -0.5)
        self.cells[key] = [np_, float(seconds), max(0.1, float(seconds)), 0.0, faces, edges]

    def disarm(self, x, y, z):
        cell = self.cells.pop((math.floor(x), math.floor(y), math.floor(z)), None)
        if cell is not None:
            cell[0].removeNode()

    # -- the pulse --
    def ring(self, x, y, z, radius=2.5):
        n = SPARKS.get(tier(), 28)
        root = self.root.attachNewNode("pulse")
        root.setPos(math.floor(x) + 0.5, math.floor(y) + 0.5, math.floor(z) + 0.5)
        self.disarm(x, y, z)  # (the cell has gone off: its glow goes with it)
        sparks = _Sparks(root, n)
        if self._ring_tex is None:
            self._ring_tex = image_texture(ring_image(), "pulse ring")
            self._dot_tex = image_texture(dot_image(), "pulse flash")
        card = _card(root, "ring", 1.0, self._ring_tex)
        card.setP(-90)       # (flat: a ring on the ground round the cell)
        card.setTwoSided(True)
        card.setColor(1, 1, 1, 1)
        flash = _card(root, "flash", 1.0, self._dot_tex)
        flash.setBillboardPointEye()
        flash.setColor(0.75, 0.97, 1.0, 1)
        ang = np.arange(n) / n * 2 * np.pi + self.rng.uniform(-0.12, 0.12, n)
        dirs = np.stack([np.cos(ang), np.sin(ang), np.zeros(n)], 1).astype(np.float32)
        speeds = self.rng.uniform(0.82, 1.08, n).astype(np.float32)
        rises = self.rng.uniform(-0.35, 0.9, n).astype(np.float32)
        self.rings.append([root, sparks, card, flash, 0.0, max(0.5, float(radius)), dirs, speeds, rises])
        self._ring_frame(self.rings[-1])

    def _ring_frame(self, r):
        root, sparks, card, flash, t, radius, dirs, speeds, rises = r
        f = min(1.0, t / self.RING_TIME)
        out = 1 - (1 - f) ** 2.2                   # (fast, then slowing: a shock going out)
        fade = 1.0 if f < 0.55 else max(0.0, 1 - (f - 0.55) / 0.45)
        pos = dirs * (radius * out * speeds)[:, None]
        pos[:, 2] = rises * out * 0.6
        size = np.full(len(dirs), 0.085 * (1 - 0.5 * f), np.float32)
        white = max(0.0, 1 - f * 2.5)
        colour = np.empty((len(dirs), 4), np.float32)
        colour[:, 0] = CYAN[0] + (1 - CYAN[0]) * white
        colour[:, 1] = CYAN[1] + (1 - CYAN[1]) * white
        colour[:, 2] = 1.0
        colour[:, 3] = fade
        sparks.set(pos, size, colour)
        card.setScale(max(0.05, radius * out))
        card.setAlphaScale(fade * 0.9)
        flash.setScale(0.4 + 1.6 * f)
        flash.setAlphaScale(max(0.0, 1 - f / 0.35) * 0.9)

    # -- the streak --
    def streak(self, x0, y0, z0, x1, y1, z1):
        a, b = np.array((x0, y0, z0), np.float32), np.array((x1, y1, z1), np.float32)
        root = self.root.attachNewNode("streak")
        px = line_px()
        lines = []
        for name, width, colour in (("glow", 9.0 * px, (*MAGENTA, 0.5)), ("core", 3.5 * px, (1.0, 0.6, 0.93, 1))):
            ls = LineSegs(f"streak {name}")
            ls.setThickness(width)
            ls.setColor(*colour)
            ls.moveTo(*a)
            for _ in range(9):
                ls.drawTo(*a)
            node = root.attachNewNode(ls.create(True))
            node.setAntialias(AntialiasAttrib.MLine)
            lines.append((ls, colour))
        head = _Sparks(root, 3, "streak head")
        self.streaks.append([root, lines, head, 0.0, a, b])
        self._streak_frame(self.streaks[-1])

    def _streak_frame(self, s):
        root, lines, head, t, a, b = s
        f = min(1.0, t / self.STREAK_TIME)
        h = 1 - (1 - f) ** 2                 # the head: quick out of the Glitch, easing into the rift
        tail = max(0.0, h - 0.45) if f < 1 else h
        tail = max(tail, (f - 0.6) / 0.4 * h) if f > 0.6 else tail
        dist = float(np.linalg.norm(b - a))
        up = np.array((0, 0, 1), np.float32) * min(1.5, dist * 0.25)

        def at(u):
            return a + (b - a) * u + up * math.sin(math.pi * u)
        for ls, colour in lines:
            for i in range(10):
                u = tail + (h - tail) * i / 9
                ls.setVertex(i, *at(u))
                ls.setVertexColor(i, colour[0], colour[1], colour[2], colour[3] * (i / 9) ** 1.5)
        pos = np.stack([at(h)] * 3) + self.rng.normal(0, 0.06, (3, 3)).astype(np.float32)
        colour = np.tile(np.array([[*MAGENTA, 1.0]], np.float32), (3, 1))
        colour[0, :3] = (1.0, 0.85, 0.97)
        head.set(pos.astype(np.float32), np.array([0.14, 0.09, 0.07], np.float32), colour)
        root.setAlphaScale(1.0 if f < 0.8 else max(0.0, 1 - (f - 0.8) / 0.2))

    def update(self, dt):
        for key, cell in list(self.cells.items()):
            np_, left, total, phase, faces, edges = cell
            left -= dt
            if left <= 0:
                self.disarm(*key)
                continue
            done = 1 - left / total
            phase += dt * (3.0 + 4.0 * done) * 2 * math.pi   # (about 3 a second, 7 by the end)
            beat = 0.5 + 0.5 * math.sin(phase)
            faces.setAlphaScale(0.12 + 0.3 * beat + 0.15 * done)
            edges.setAlphaScale(0.55 + 0.45 * beat)
            np_.setScale(1.05 + 0.05 * beat + 0.04 * done)
            cell[1], cell[3] = left, phase
        keep = []
        for r in self.rings:
            r[4] += dt
            if r[4] >= self.RING_TIME:
                r[0].removeNode()
                continue
            self._ring_frame(r)
            keep.append(r)
        self.rings = keep
        keep = []
        for s in self.streaks:
            s[3] += dt
            if s[3] >= self.STREAK_TIME:
                s[0].removeNode()
                continue
            self._streak_frame(s)
            keep.append(s)
        self.streaks = keep

    def busy(self):
        return bool(self.cells or self.rings or self.streaks)

    def clear(self):
        for key in list(self.cells):
            self.disarm(*key)
        for r in self.rings:
            r[0].removeNode()
        for s in self.streaks:
            s[0].removeNode()
        self.rings, self.streaks = [], []


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
