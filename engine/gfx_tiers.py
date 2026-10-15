"""Graphics quality tiers: what each game draws on an old school laptop and on a gaming PC, chosen by itself.

The tiers are basic, low, medium and high (TIERS). "basic" has no simplepbr at all: Panda's own generated
shaders (setShaderAuto) and the paint texture only; it is the floor every machine can draw. The other three
are simplepbr with fewer or more of the costly things: shadows, MSAA, the number of lights, normal and
occlusion maps, the reflection map.

A game's window uses this file in four steps:
1. before the window opens: tier = resolve(settings_dir, --gfx) and loadPrcFileData("", prc_for(tier, ...))
   (texture size, mipmaps and the window's multisamples are read as the window opens, so they must be set first)
2. right after the window opens: detect(base, settings_dir) reads the graphics driver's name and GL version and
   saves them, so the NEXT run can pick its tier from them (Panda can't read the card's memory, see the notes)
3. the game's gfx.init(base, tier) calls init_pipeline(), which makes simplepbr with the tier's settings and
   drops to the next tier down if the driver can't compile it (old Intel drivers), down to "basic"
4. when play starts: Monitor watches the frame times. Missed frames turn the shadows and MSAA down in this
   run first; if frames are still missed it saves the next tier down for next time and tells the player.

Settings live in this computer's settings.json (the same file engine.hud keeps the class code and look in):
gfx_tier (the player's or the monitor's choice), gfx_detect (what the driver said) and gfx_benchmarked (the
highest tier that has run cleanly here: the monitor never steps up past it), and gfx_class_max (the teacher's
class maximum, CHANGE 139: a learner's window opens at most at it and never steps up past it).
"""
import ctypes
import json
import math
import os
import re
import sys
import time

TIERS = ("basic", "low", "medium", "high")

# Each tier's knobs. pbr: simplepbr's keyword arguments (enable_shadows is compiled in, so it can't change in a
# run). shadow: the key light's shadow map size (0 = no shadows). aniso: texture anisotropic filtering degree.
# texture_scale: textures are shrunk to this as they load (0.5 = a quarter of the memory and bandwidth).
# lod_scale: Panda's LOD distance scale, when a scene has LOD nodes. env_map: the reflection map (IBL).
SETTINGS = {
    "basic": {"simplepbr": False, "pbr": {}, "shadow": 0, "aniso": 1, "texture_scale": 0.5, "lod_scale": 0.6,
              "env_map": False, "msaa": 0},
    "low": {"simplepbr": True,
            "pbr": {"msaa_samples": 0, "max_lights": 8, "use_normal_maps": False, "use_occlusion_maps": False,
                    "enable_shadows": False},
            "shadow": 0, "aniso": 1, "texture_scale": 0.5, "lod_scale": 0.6, "env_map": False, "msaa": 0},
    "medium": {"simplepbr": True,
               "pbr": {"msaa_samples": 2, "max_lights": 8, "use_normal_maps": True, "use_occlusion_maps": False,
                       "enable_shadows": True},
               "shadow": 1024, "aniso": 4, "texture_scale": 1.0, "lod_scale": 1.0, "env_map": True, "msaa": 2},
    "high": {"simplepbr": True,
             "pbr": {"msaa_samples": 4, "max_lights": 8, "use_normal_maps": True, "use_occlusion_maps": True,
                     "enable_shadows": True},
             "shadow": 2048, "aniso": 8, "texture_scale": 1.0, "lod_scale": 1.5, "env_map": True, "msaa": 4},
}
DEFAULT = "medium"  # the very first run on a machine nobody has seen: the monitor steps it down if it must
DETECTED = None     # what detect() found this run (None until the window is open, or in a tool with no window)


def _index(tier):
    return TIERS.index(tier)


def below(tier):
    """The next tier down, or the tier itself at the floor."""
    return TIERS[max(0, _index(tier) - 1)]


def above(tier):
    return TIERS[min(len(TIERS) - 1, _index(tier) + 1)]


# ---------- the class maximum (CHANGE 139) ----------
# The teacher's lesson key "gfx_max": the best tier a learner's window or page may draw (None: no limit). The
# browser's "blocks" is the windows' "basic". A learner's window keeps it here (gfx_class_max) so the next start
# opens at most at it: the shaders are made as the window opens, so mid-run only the knobs that change safely in
# a run come down (the monitor's: the shadow map, MSAA, the LOD distance).
def class_max(value):
    """The lesson's gfx_max, checked: one of TIERS, or None."""
    value = "basic" if value == "blocks" else value
    return value if value in TIERS else None


def capped(tier, cap):
    """tier, or the class maximum when it is lower."""
    cap = class_max(cap)
    return cap if cap and tier in TIERS and _index(tier) > _index(cap) else tier


def obey_class_max(settings_dir, cap, monitor=None, tier=None):
    """A learner's window heard the lesson: keep the class maximum for the next start and tell the monitor. Returns
    a note for the player when it has just come down below the tier in use, else None."""
    cap = class_max(cap)
    if settings_dir and load_settings(settings_dir).get("gfx_class_max") != cap:
        if cap:
            remember(settings_dir, gfx_class_max=cap)
        else:
            forget(settings_dir, "gfx_class_max")
    was = monitor.class_max if monitor is not None else None
    if monitor is not None:
        monitor.set_class_max(cap)
    if cap and tier in TIERS and _index(tier) > _index(cap) and was != cap:
        return (f"Your teacher set the graphics to at most {cap.title()}: shadows and smoothing are turned down now, "
                "the rest from the next start")
    return None


# ---------- this computer's settings (the same settings.json engine.hud keeps the class code in) ----------
def load_settings(settings_dir):
    try:
        with open(os.path.join(settings_dir, "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def forget(settings_dir, *keys):
    """Drop gfx settings (a new driver or machine: judge afresh)."""
    path = os.path.join(settings_dir, "settings.json")
    data = {k: v for k, v in load_settings(settings_dir).items() if k not in keys}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def remember(settings_dir, **keys):
    """Keep gfx settings on this computer, next to the class code and the look (never losing those)."""
    path = os.path.join(settings_dir, "settings.json")
    data = load_settings(settings_dir) | keys
    try:
        os.makedirs(settings_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------- before the window opens ----------
def prc_for(tier):
    """The prc text to load before the window opens.

    No gl-version line, on purpose: asking Panda for "gl-version 3 2" made the Intel Iris Xe driver hand back a
    context capped at GL 3.2 / GLSL 1.50 instead of its 4.6 / 4.60, which is the opposite of what it was meant
    to buy (GLSL 3.30 shaders). simplepbr's shader version is set from the detected GLSL instead (init_pipeline)."""
    s = SETTINGS[tier]
    lines = [f"texture-scale {s['texture_scale']}",
             "texture-minfilter linear-mipmap-linear",  # Panda ships with mipmaps off: shimmering, and slower
             f"texture-anisotropic-degree {s['aniso']}",
             "textures-power-2 down",
             # the panels' pictures and any font or icon textures stay full size on every tier
             "exclude-texture-scale *gui*", "exclude-texture-scale *font*", "exclude-texture-scale *icon*",
             "exclude-texture-scale *logo*",
             f"framebuffer-multisample {1 if s['msaa'] else 0}", f"multisamples {s['msaa']}"]
    return "\n".join(lines) + "\n"


def resolve(settings_dir, override=None):
    """The tier this run uses: --gfx wins; then the tier saved here (the player's or the monitor's choice);
    then the heuristic from a previous run's detection; then medium on a machine nobody has seen. Never above the
    class maximum a learner's window kept here (CHANGE 139)."""
    saved = load_settings(settings_dir)
    if override in TIERS:
        return capped(override, saved.get("gfx_class_max"))
    if saved.get("gfx_tier") in TIERS:
        return capped(saved["gfx_tier"], saved.get("gfx_class_max"))
    guess = (saved.get("gfx_detect") or {}).get("heuristic_tier")
    return capped(guess if guess in TIERS else DEFAULT, saved.get("gfx_class_max"))


# ---------- after the window opens ----------
# word-boundary patterns (a plain "ati" would match "NVIDIA Corporation"); the first match wins, so the more
# particular lines come first
_SOFTWARE = re.compile(r"\b(llvmpipe|softpipe|swiftshader|gdi generic|microsoft basic render|mesa|virtualbox|"
                       r"vmware|svga3d)\b", re.I)
_HEURISTIC = (
    (re.compile(r"\b(rtx|geforce gtx 16\d\d|radeon rx|radeon pro|arc(\(tm\))? a\d+|quadro rtx|apple m\d)\b", re.I),
     "high"),
    (re.compile(r"\b(geforce gtx (7|9|10)\d\d|geforce mx\d{3}|quadro|tesla|arc)\b", re.I), "medium"),
    (re.compile(r"\b(uhd graphics 6[23]\d|iris)\b", re.I), "medium"),             # UHD 620/630, Iris Xe/Plus/Pro
    (re.compile(r"\b(uhd graphics 6[01]\d|hd graphics|uhd graphics 6\d\d)\b", re.I), "low"),  # UHD 600/605, HD 4000-620
    (re.compile(r"\buhd graphics\b", re.I), "medium"),                              # Tiger Lake and later, no number
    (re.compile(r"\bradeon.*\b(vega|graphics|7\d0m|6\d0m)\b", re.I), "medium"),    # the Ryzen laptop iGPUs
    (re.compile(r"\bradeon\b", re.I), "low"),                                       # old HD 4000-7000, R5/R7 M
    (re.compile(r"\bgeforce\b", re.I), "low"),                                      # GT 7xx, GTX 4xx-6xx and older
)


def classify(renderer, gl=(0, 0), ram_gb=0):
    """The tier a driver's renderer string suggests (the heuristic the first run can't have)."""
    renderer = renderer or ""
    gl = tuple(gl or (0, 0))
    if gl[0] and gl < (3, 0):
        return "basic"  # GLSL 1.20 at best: simplepbr's shaders are a gamble, Panda's own are not
    if _SOFTWARE.search(renderer):
        tier = "low"
    else:
        tier = "low"
        for pattern, t in _HEURISTIC:
            if pattern.search(renderer):
                tier = t
                break
    if ram_gb and ram_gb < 4 and _index(tier) > _index("low"):
        tier = "low"  # an iGPU shares this memory: a 4 GB laptop has little to spare for 1024 textures
    return tier


def physical_ram_gb():
    """This computer's memory in GB (Windows: GlobalMemoryStatusEx), or 0 when it can't be read."""
    try:
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / 2 ** 30, 1)
    except (AttributeError, OSError):
        pass
    return 0


def detect(base, settings_dir=None):
    """What the graphics driver says about itself (only meaningful once the window is open), with the tier it
    suggests. Saved for the next run when settings_dir is given, and kept in DETECTED for this one."""
    global DETECTED
    info = {"vendor": "", "renderer": "", "version": "", "gl": [0, 0], "glsl": [0, 0], "max_texture": 0,
            "ram_gb": physical_ram_gb(), "when": time.strftime("%Y-%m-%d %H:%M")}
    try:
        gsg = base.win.getGsg()
        info.update(vendor=gsg.getDriverVendor(), renderer=gsg.getDriverRenderer(), version=gsg.getDriverVersion(),
                    gl=[gsg.getDriverVersionMajor(), gsg.getDriverVersionMinor()],
                    glsl=[gsg.getDriverShaderVersionMajor(), gsg.getDriverShaderVersionMinor()],
                    max_texture=gsg.getMaxTextureDimension())
    except Exception as e:  # (no window, or a pipe without a GSG): the heuristic falls back to low
        info["error"] = str(e)
    info["heuristic_tier"] = classify(info["renderer"], info["gl"], info["ram_gb"])
    DETECTED = info
    if settings_dir:
        old = load_settings(settings_dir).get("gfx_detect") or {}
        if old and (old.get("renderer"), old.get("version")) != (info["renderer"], info["version"]):
            forget(settings_dir, "gfx_tier", "gfx_benchmarked", "gfx_failed")  # (another driver: judge afresh)
        remember(settings_dir, gfx_detect=info)
    print(f"gfx: {info['renderer']} (GL {info['gl'][0]}.{info['gl'][1]}, GLSL {info['glsl'][0]}.{info['glsl'][1]}, "
          f"{info['ram_gb']} GB): looks {info['heuristic_tier']}", flush=True)
    return info


def _use_330():
    """Whether the driver seen this run takes GLSL 3.30 shaders (None = let simplepbr guess from the prc)."""
    if not DETECTED or not DETECTED["glsl"][0]:
        return None
    return tuple(DETECTED["glsl"]) >= (3, 30)


def _undo_pipeline(base, pipeline):
    """Best effort to take a half-made simplepbr out again before the next tier is tried."""
    try:
        base.taskMgr.remove("simplepbr update")
        pipeline._filtermgr.cleanup()
        base.render.clearShader()
        base.render.clearMaterial()
    except Exception:
        pass


def init_pipeline(base, tier, env_loader=None, exposure=0.0):
    """Make simplepbr for the tier (the shared part of the games' gfx.init). env_loader(simplepbr) returns the
    reflection map, asked for on the tiers that use one. Returns (pipeline or None, tier actually used): a tier
    whose shaders the driver won't compile is swapped for the next one down, ending at "basic" (Panda's own
    shaders, no simplepbr)."""
    tier = tier if tier in TIERS else DEFAULT
    while SETTINGS[tier]["simplepbr"]:
        pipeline = None
        try:
            import simplepbr
            env = env_loader(simplepbr) if env_loader and SETTINGS[tier]["env_map"] else None
            kwargs = dict(SETTINGS[tier]["pbr"], exposure=exposure, env_map=env)
            if _use_330() is not None:
                kwargs["use_330"] = _use_330()
            pipeline = simplepbr.init(**kwargs)
            pipeline.verify_shaders()  # (compiles them now: a driver that can't say so here, not as a black screen)
            return pipeline, tier
        except Exception as e:
            print(f"gfx: simplepbr {tier} didn't start here ({type(e).__name__}: {e}): trying {below(tier)}",
                  file=sys.stderr, flush=True)
            if pipeline is not None:
                _undo_pipeline(base, pipeline)
            tier = below(tier)
    base.render.setShaderAuto()
    return None, "basic"


def dim_lights(render):
    """For "basic": the games' key and spot lights are set for simplepbr, whose diffuse is the colour over pi;
    Panda's own shaders use the colour as it is, so they come down by pi (the ambient light is the same in both)."""
    from panda3d.core import AmbientLight, LightAttrib
    attrib = render.getAttrib(LightAttrib)
    if attrib is None:
        return
    for light in attrib.getOnLights():
        node = light.node()
        if isinstance(node, AmbientLight):
            continue
        c = node.getColor()
        node.setColor((c[0] / math.pi, c[1] / math.pi, c[2] / math.pi, 1))


# simplepbr's tone curve (tonemap.frag: exposure, then the Hejl-Burgess filmic curve, which has the sRGB gamma
# built in), as a GLSL 1.20 post pass for "basic", so that the games' linear material colours and PBR-strength
# lights come out at the brightness the other tiers draw them, instead of dark mid-tones and clipped lights
_TONE_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
varying vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_uv = p3d_MultiTexCoord0;
}
"""
_TONE_FRAG = """#version 120
uniform sampler2D tex;
uniform float exposure;
varying vec2 v_uv;
void main() {
    vec4 c = texture2D(tex, v_uv);
    vec3 x = max(vec3(0.0), c.rgb * exposure - vec3(0.004));
    vec3 t = (x * (vec3(6.2) * x + vec3(0.5))) / (x * (vec3(6.2) * x + vec3(1.7)) + vec3(0.06));
    gl_FragColor = vec4(t, 1.0);  // (opaque: the games clear to alpha 0, which a screenshot would show as white)
}
"""


def tone_pass(base, exposure=0.0):
    """Draw the 3D scene through simplepbr's tone curve on "basic" (Panda's own shaders have none). Returns the
    FilterManager, or None where offscreen buffers or the shader aren't available (the picture is then drawn
    straight, dimmer in the mid-tones)."""
    try:
        from direct.filter.FilterManager import FilterManager
        from panda3d.core import ATSNone, Shader, Texture
        Texture.setTexturesPower2(ATSNone)  # (as simplepbr does: a scene texture padded to a power of two would
        # show in the corner of the quad; every GL 2 card draws any size)
        manager = FilterManager(base.win, base.cam)
        colour = Texture("basic scene")
        quad = manager.renderSceneInto(colortex=colour)
        if quad is None:
            return None
        shader = Shader.make(Shader.SL_GLSL, _TONE_VERT, _TONE_FRAG)
        if shader is None:
            manager.cleanup()
            return None
        quad.setShader(shader)
        quad.setShaderInput("tex", colour)
        quad.setShaderInput("exposure", float(2 ** exposure))
        return manager
    except Exception as e:
        print(f"gfx: no tone curve on basic ({type(e).__name__}: {e})", file=sys.stderr, flush=True)
        return None


def basic_look(base, exposure=0.0):
    """Everything "basic" does after the lights are placed: the key lights come down by pi (simplepbr's diffuse
    is the colour over pi, Panda's is the colour) and the scene is drawn through simplepbr's tone curve at the
    game's exposure. Returns the FilterManager (keep it) or None."""
    dim_lights(base.render)
    return tone_pass(base, exposure)




# ---------- while playing ----------
class Monitor:
    """Watches the frame times once play has started and turns the graphics down when frames are missed.

    After a warm-up (shaders compile in the first seconds) it keeps a running average of the frame time and
    counts the frames over MISS seconds in the last WINDOW seconds (with vsync on, a missed 60 Hz frame shows as
    a 33 ms one). Over MISS_PCT per cent missed: first the knobs that change safely in a run, one per window
    (the shadow map size, then MSAA, then the LOD distance); when those are spent, the next tier down is saved
    for next time (one tier a run; never below "low" or the player's --gfx, since missed frames at low are the
    Python side, not the GPU: "basic" is only for drivers that can't run simplepbr, or the player's own choice)
    and on_note is told; the tier stepped down from is remembered as failed here, and never stepped back up
    into (the player's Graphics button or --gfx can still choose it; a new driver forgets it). It steps back up
    only after UP_SECS seconds with headroom: frame times under UP_RATIO of the budget, or (with vsync, which
    pins frame times to the budget) a whole window with no missed frame. judge=False (a window whose server is
    on this same computer, as when the teacher tests alone: the frames it misses say nothing about the GPU) and
    an offscreen buffer (the tests, screenshots) watch and turn the knobs, but remember nothing. It steps back up only after UP_SECS seconds under UP_RATIO of the budget, and never past the tier that
    has run cleanly here (gfx_benchmarked).

    frame(dt) is the whole of it, so tests can feed frame times with their own clock; start(base) runs it as a
    Panda task."""
    BUDGET = 1 / 60
    MISS = 0.022       # a frame longer than this missed its vsync slot
    WARMUP = 5.0
    WINDOW = 3.0
    MISS_PCT = 8.0
    UP_SECS = 10.0
    UP_RATIO = 0.7
    MIN_FRAMES = 30    # a window with fewer frames than this says nothing (a stall, a panel rebuild)

    def __init__(self, settings_dir, tier, override=None, pipeline=None, lights=(), render=None, on_note=None,
                 clock=None, heuristic=None, judge=True):
        self.settings_dir, self.tier, self.pipeline, self.render = settings_dir, tier, pipeline, render
        if not judge:
            self.settings_dir = None  # (reads what is saved, below; never writes)
        self.override = override if override in TIERS else None
        self.on_note = on_note or (lambda text: None)
        self.clock = clock or time.perf_counter
        saved = load_settings(settings_dir) if settings_dir else {}
        self.heuristic = heuristic or (saved.get("gfx_detect") or {}).get("heuristic_tier")
        self.benchmarked = saved.get("gfx_benchmarked") if saved.get("gfx_benchmarked") in TIERS else None
        self.saved_tier = saved.get("gfx_tier") if saved.get("gfx_tier") in TIERS else None
        self.failed = [t for t in (saved.get("gfx_failed") or []) if t in TIERS]  # tiers stepped down from here
        self.class_max = class_max(saved.get("gfx_class_max"))  # the teacher's (CHANGE 139): never stepped up past
        self.capped_knobs = []           # the knobs the class maximum turned down in this run
        self.lights = [l for l in lights if self._shadow_size(l)]
        self.has_lod = bool(render is not None and not render.find("**/+LODNode").isEmpty())
        self.steps = self._plan_steps()  # the in-run step-downs still to take, in order
        self.taken = []                  # those taken (undone in reverse when stepping up)
        self.started = None
        self.ewma = None
        self.frames = []                 # (time, missed) for the last WINDOW seconds
        self.hold_until = 0              # no decisions until then (a fresh window after each change)
        self.good_since = None
        self.clean = False               # this run has had a clean window at its tier (then benchmarked = tier)
        self.changed = False             # a step was taken this run (so it never counts as a clean run)
        self.stepped_tier = False        # a tier was saved this run (one a run: the next run judges again)
        self.task = None
        if self.class_max:  # (heard before the monitor started: the knobs come down now)
            self.set_class_max(self.class_max)

    # --- the knobs that are safe in a run ---
    @staticmethod
    def _shadow_size(light):
        try:
            node = light.node()
            return node.getShadowBufferSize().x if node.isShadowCaster() else 0
        except Exception:
            return 0

    def _plan_steps(self):
        steps = []
        size = max([self._shadow_size(l) for l in self.lights] or [0])
        msaa = getattr(self.pipeline, "msaa_samples", 0) if self.pipeline is not None else 0
        while size > 512:
            size //= 2
            steps.append(("shadow", size))
            if msaa and len(steps) == 1:
                steps.append(("msaa", 0))
                msaa = 0
        if msaa:
            steps.append(("msaa", 0))
        if self.has_lod:
            steps.append(("lod", round(SETTINGS[self.tier]["lod_scale"] * 0.7, 2)))
        return steps

    def _apply(self, step):
        kind, value = step
        try:
            if kind == "shadow":
                for l in self.lights:
                    l.node().setShadowCaster(True, value, value)
            elif kind == "msaa":
                self.pipeline.msaa_samples = value  # (rebuilds the post pass only, not the PBR shader)
            elif kind == "lod":
                self.render.setLodScale(value)
        except Exception as e:
            print(f"gfx: couldn't set {kind} {value}: {e}", file=sys.stderr, flush=True)

    def _undo(self, step):
        kind, _ = step
        s = SETTINGS[self.tier]
        before = [v for k, v in self.taken if k == kind]
        value = before[-1] if before else {"shadow": s["shadow"], "msaa": s["pbr"].get("msaa_samples", 0),
                                           "lod": s["lod_scale"]}[kind]
        self._apply((kind, value))

    # --- the decisions ---
    def frame(self, dt, now=None):
        """Called once a frame with its length in seconds."""
        now = self.clock() if now is None else now
        if self.started is None:
            self.started = now
            return
        if now - self.started < self.WARMUP:
            return
        self.ewma = dt if self.ewma is None else 0.8 * self.ewma + 0.2 * dt
        self.frames.append((now, dt > self.MISS))
        while self.frames and self.frames[0][0] < now - self.WINDOW:
            self.frames.pop(0)
        if now < self.hold_until or len(self.frames) < self.MIN_FRAMES or self.frames[0][0] > now - self.WINDOW + 0.1:
            return
        missed = 100.0 * sum(1 for _, m in self.frames if m) / len(self.frames)
        if missed > self.MISS_PCT:
            self.good_since = None
            self.step_down(now)
            return
        if not self.clean and not self.changed:
            self.clean = True  # a full clean window at this tier: the highest clean tier is remembered
            if self.benchmarked is None or _index(self.tier) > _index(self.benchmarked):
                self.benchmarked = self.tier
                if self.settings_dir:
                    remember(self.settings_dir, gfx_benchmarked=self.tier)
        if self.ewma < self.UP_RATIO * self.BUDGET or missed == 0.0:  # (vsync pins frame times to the budget:
            self.good_since = self.good_since or now                     # then a window with no miss is headroom)
            if now - self.good_since >= self.UP_SECS:
                self.step_up(now)
        else:
            self.good_since = None

    def _changed(self, now):
        self.changed = True
        self.frames = []
        self.hold_until = now + self.WINDOW
        self.good_since = None

    def step_down(self, now):
        if self.steps:
            step = self.steps.pop(0)
            self._apply(step)
            self.taken.append(step)
            self._changed(now)
            return
        current = capped(self.saved_tier or self.tier, self.class_max)
        floor = self.override or "low"
        if self.stepped_tier or _index(current) <= _index(floor):
            self.hold_until = now + self.WINDOW  # nothing left to turn down (a Python-bound client, or low)
            return
        if current not in self.failed:
            self.failed = sorted(set(self.failed) | {current}, key=_index)
            if self.settings_dir:
                remember(self.settings_dir, gfx_failed=self.failed)
        self.save_tier(below(current), now)
        self.stepped_tier = True
        self.on_note(f"Graphics set to {self.saved_tier.title()} for next time (frames were being missed)")

    def step_up(self, now):
        if self.capped_knobs:  # (the class maximum holds the knobs down: nothing goes back up past it)
            self.good_since = now
            return
        if self.taken:
            self._undo(self.taken.pop())
            self._changed(now)
            return
        current = capped(self.saved_tier or self.tier, self.class_max)
        # the driver's own tier (the heuristic's, or medium) is always worth trying again, however a bad session
        # (a server and two windows on one laptop) left things; a clean run above it buys at most one tier more
        own = self.heuristic if self.heuristic in TIERS else DEFAULT
        ceiling = own
        if self.benchmarked and _index(self.benchmarked) > _index(own):
            ceiling = TIERS[min(_index(self.benchmarked), _index(own) + 1)]
        ceiling = capped(ceiling, self.class_max)
        if self.override or _index(current) >= _index(ceiling) or above(current) in self.failed:
            self.good_since = now  # (wait another UP_SECS before looking again)
            return
        self.save_tier(above(current), now)
        self.on_note(f"Graphics set to {self.saved_tier.title()} for next time")

    def save_tier(self, tier, now):
        """Save the tier for next time."""
        self.saved_tier = tier
        if self.settings_dir:
            remember(self.settings_dir, gfx_tier=tier)
        self._changed(now)

    def set_class_max(self, cap):
        """The teacher's class maximum (CHANGE 139) heard mid-run. Below the tier in use: the knobs that change
        safely in a run come down to the maximum's (the shadow map no smaller than 512: the shadows are compiled in);
        lifted: they go back to this run's own."""
        cap = class_max(cap)
        self.class_max = cap
        if cap and _index(self.tier) > _index(cap):
            s = SETTINGS[cap]
            knobs = []
            if self.lights:
                knobs.append(("shadow", max(512, s["shadow"])))
            if self.pipeline is not None and (SETTINGS[self.tier]["msaa"] or "msaa" in self.capped_knobs):
                knobs.append(("msaa", s["msaa"]))
            if self.has_lod:
                knobs.append(("lod", s["lod_scale"]))
            for step in knobs:
                kind, value = step
                own = [v for k, v in self.taken if k == kind]  # (the monitor's own turn-downs stay if lower)
                if not own or own[-1] > value:
                    self._apply(step)
            held = dict(knobs)  # (a step-down still to take only if it goes lower than the maximum's)
            self.steps = [(k, v) for k, v in self.steps if k not in held or v < held[k]]
            self.capped_knobs = list(held)
        elif self.capped_knobs:
            for kind in self.capped_knobs:
                self._undo((kind, None))
            self.capped_knobs = []
            self.steps = self._plan_steps()

    def report(self):
        """For the status line and the teacher's grid."""
        missed = 100.0 * sum(1 for _, m in self.frames if m) / len(self.frames) if self.frames else 0.0
        return {"tier": self.tier, "fps": round(1 / self.ewma) if self.ewma else 0, "missed_pct": round(missed, 1),
                "next_time": self.saved_tier}

    # --- as a Panda task ---
    def start(self, base):
        from panda3d.core import ClockObject, GraphicsWindow
        clock = ClockObject.getGlobalClock()
        if not isinstance(getattr(base, "win", None), GraphicsWindow):
            self.settings_dir = None  # an offscreen buffer: its frame times say nothing about the screen

        def tick(task):
            self.frame(clock.getDt())
            return task.cont
        self.task = base.taskMgr.add(tick, "gfx monitor", sort=60)
        return self

    def stop(self):
        if self.task is not None:
            self.task.remove()
            self.task = None
