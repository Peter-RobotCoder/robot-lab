"""Kart Lab's ultra circuit (CHANGE 144): the road, kerbs, gravel, barriers, grass, trees, grandstand, pits and the
country round it, built from numbers alone, so the window (kart_gfx.py) and the page (club-coders/web/make_models.py
writes it to models/kart_scenery.json) draw the same circuit. The ultra kart (kart_models.py) is the quality bar.

Pure Python, no Panda3D (kart_track and kart_models are pure Python too). scenery() returns what the page reads:

    {"version": 1,
     "materials": {name: material, ...}    how each material looks (see MATERIALS)
     "shapes":    {name: [part, ...]}      things placed many times (trees, tufts, tyre stacks, fans), each in its own
                                           frame: x forward, y left, z up, the ground at z = 0 under its middle
     "tracks":    {track name: {"parts": [part, ...], "instances": {shape: [[x, y, z, h, s, r, g, b], ...]}}}
     "notes":     {...}}

    part: {"name", "material", "count" (vertices), "box", "uv_box", "positions", "normals", "uvs", "indices", and if
           they're there "colours" (screen colours, as the designs' are: make them linear), "tint": true (an
           instance's colour multiplies this part's colours), "far": true (out in the country: no shadow)}; the
           arrays are packed, five times smaller than lists of numbers would be (Part.packed says how to read them)
    instance: the shape turned h degrees about z (anticlockwise, from +x), scaled by s, moved to (x, y, z); r, g, b
              multiplies the colours of the shape's "tint" parts (screen colours, 1 1 1 is as the shape is)

Placement is exported per built-in track (kart_track.TRACKS: a track mod picks one of them, there are no others), so
the page places nothing itself: it draws each track's parts as they are, and each shape at each of its instances.
Everything is decided by fixed seeds, so the window and the file agree (to a few millimetres: the file's positions
are packed into 65536 steps across each part, the window builds from the numbers themselves). Nothing here is solid:
the sim never reads a picture; and nothing stands within BARRIER of the road's edge, where the karts are held
(kart_sim: |lateral| <= half - KART_HALF), or in the TV cameras' way (tv_cameras: the cameras' one definition).

The frame is the game's: x, y on the ground, z up, metres; triangles anticlockwise seen from outside (from above for
the ground). Texture coordinates are repeats of the material's texture (about MATERIALS' "metres" each).
"""
import base64
import math
import random
import sys
from array import array

import kart_models
import kart_track

VERSION = 1

# the advertising boards and the gantry's banner: one row each of the "signs" texture, top row first (kart_gfx draws
# the picture; never a real brand). (text, background, lettering), screen colours
SIGNS = [("CLUB CODERS", (0.1, 0.36, 0.86), (1.0, 1.0, 1.0)),
         ("KART LAB", (0.98, 0.78, 0.1), (0.08, 0.08, 0.1)),
         ("ROBOT LAB", (0.84, 0.14, 0.12), (1.0, 1.0, 1.0)),
         ("FIGHT LAB", (0.42, 0.18, 0.68), (1.0, 1.0, 1.0)),
         ('print("GO!")', (0.07, 0.09, 0.11), (0.35, 0.95, 0.45)),
         ("BUILD  TEST  RACE", (0.08, 0.56, 0.3), (1.0, 1.0, 1.0)),
         ("if fast: brake()", (0.17, 0.17, 0.19), (1.0, 0.62, 0.15)),
         ("START", (0.06, 0.06, 0.07), (1.0, 1.0, 1.0))]
START_SIGN = 7

# (CHANGE 151) the pond's ripples: its texture's repeat in metres, and how it drifts (metres a second along x and y,
# and a slow sway across that): the window moves the texture, the page the water's texture coordinates, the same way
WATER_METRES = 3.0
WATER_FLOW = {"drift": [0.05, 0.022], "sway": [0.035, -0.06], "sway_period": 9.0}


def water_offset(t):
    """(CHANGE 151) How far the pond's ripples have moved t seconds on, in repeats of its texture (u, v)."""
    f, w = WATER_FLOW["drift"], WATER_FLOW["sway"]
    k = math.sin(2 * math.pi * t / WATER_FLOW["sway_period"])
    return (((f[0] * t + w[0] * k) / WATER_METRES) % 1.0, ((f[1] * t + w[1] * k) / WATER_METRES) % 1.0)  # (it tiles)


# each material: its colour (a screen colour, times the vertex colours and the texture), how rough and metallic,
# its texture set (kart/assets/tex or engine/assets/tex, the page's tex/: <texture>_albedo, _mr (red: shading in the
# cracks, green: roughness, blue: metal), _normal) and how many metres one repeat covers, "emission" (linear light),
# "two_sided" (seen from behind too: blades of grass, flags), "decal" (painted on the road: drawn over it, a depth
# offset so it never flickers with it), "flat" (on the ground or too small to matter: casts no shadow, which
# saves drawing it into the sun's shadow map every frame; it still has shadows cast on it)
MATERIALS = {
    "asphalt": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "asphalt", "metres": 4.0, "flat": True},
    "patch": {"colour": [0.88, 0.88, 0.9], "rough": 0.95, "metal": 0.0, "texture": "asphalt", "metres": 4.0, "decal": True, "flat": True},
    "rubber": {"colour": [0.5, 0.5, 0.52], "rough": 0.8, "metal": 0.0, "texture": "asphalt", "metres": 4.0, "decal": True, "flat": True},
    "tar": {"colour": [0.16, 0.16, 0.17], "rough": 0.3, "metal": 0.0, "texture": None, "metres": 1.0, "decal": True, "flat": True},
    "line_paint": {"colour": [1.0, 1.0, 1.0], "rough": 0.9, "metal": 0.0, "texture": "kerb", "metres": 2.0, "decal": True, "flat": True},
    "kerb": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "kerb", "metres": 2.0, "flat": True},
    "gravel": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "gravel", "metres": 1.5, "flat": True},
    "turf": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "turf", "metres": 2.0, "flat": True},
    "land": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": None, "metres": 1.0, "flat": True},
    "hedge": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "foliage", "metres": 3.0},
    "armco": {"colour": [0.8, 0.82, 0.85], "rough": 0.45, "metal": 1.0, "texture": "steel", "metres": 2.0},
    "steel": {"colour": [0.62, 0.63, 0.66], "rough": 0.55, "metal": 1.0, "texture": "steel", "metres": 2.0},
    "concrete": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "render", "metres": 3.0},
    "paint": {"colour": [1.0, 1.0, 1.0], "rough": 0.6, "metal": 0.0, "texture": None, "metres": 1.0},
    "door": {"colour": [1.0, 1.0, 1.0], "rough": 0.45, "metal": 0.4, "texture": "steel", "metres": 1.0},
    "glass": {"colour": [0.3, 0.38, 0.46], "rough": 0.05, "metal": 0.0, "texture": None, "metres": 1.0},
    "signs": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "signs", "metres": 0.0},
    "lamp": {"colour": [0.16, 0.02, 0.02], "rough": 0.15, "metal": 0.0, "texture": None, "metres": 1.0,
             "emission": [0.04, 0.002, 0.002]},  # (unlit: LAMP_DARK, CHANGE 151)
    "tyre_wall": {"colour": [1.0, 1.0, 1.0], "rough": 0.85, "metal": 0.0, "texture": "kerb", "metres": 1.0},
    "bark": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "bark", "metres": 1.0},
    "needles": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "needles", "metres": 2.0},
    "leaves": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 0.0, "texture": "foliage", "metres": 2.0},
    "blades": {"colour": [1.0, 1.0, 1.0], "rough": 0.85, "metal": 0.0, "texture": None, "metres": 1.0, "two_sided": True, "flat": True},
    "rock": {"colour": [1.0, 1.0, 1.0], "rough": 0.95, "metal": 0.0, "texture": "concrete", "metres": 1.0},
    "skin": {"colour": [1.0, 1.0, 1.0], "rough": 0.7, "metal": 0.0, "texture": None, "metres": 1.0},
    "cloth": {"colour": [1.0, 1.0, 1.0], "rough": 0.9, "metal": 0.0, "texture": None, "metres": 1.0, "two_sided": True},
    "water": {"colour": [0.1, 0.16, 0.17], "rough": 0.06, "metal": 0.0, "texture": "water", "metres": WATER_METRES,
              "flat": True, "flows": WATER_FLOW},
}

# where things go, in metres from the road's edge (lateral half)
BARRIER = 1.2         # the barrier's face (as the lower tiers' wall, half + 1.0 to half + 1.5)
GRAVEL_MAX = 4.0      # how far a gravel trap reaches past BARRIER on the outside of the sharpest bends
GROUND_MARGIN = 45.0  # the mown grass reaches this far past the track's bounds (kart_gfx.TrackVisual.GRASS_MARGIN)
CELL = 3.0            # the grass's grid
STRIPE = 6.0          # the mowing stripes' width (two cells)
CAMERA_CLEAR = 10.0   # nothing taller than a barrier within this of a TV camera


def tv_cameras(track):
    """The TV cameras (kart_gfx.ChaseCamera's): six stands round the track, on the outside of each bend, 6 m off
    the road's edge and 5 m up. [(x, y, z, side, s)]."""
    out = []
    for k in range(6):
        s = (k + 0.5) * track.length / 6
        side = -1 if track.curvature(s, 30) > 0 else 1  # (a left bend: the camera on the right, looking across the apex)
        if track.lane is not None and side == track.lane[2] and track.lane_zone(s) is not None:
            # (CHANGE 179) not in the pit lane: moved along to just past the nearer end of it
            s_in, s_out, _ = track.lane
            ds = (s - s_in) % track.length
            s = (s_in - 12.0 if ds < (s_out - s_in) / 2 else s_out + 12.0) % track.length
            side = -1 if track.curvature(s, 30) > 0 else 1
        x, y, z = track.point(s, side * (track.half + 6.0))
        out.append((x, y, z + 5.0, side, s))
    return out


LIGHTS_FROM, LIGHTS_STEP = 3.0, 0.6  # (CHANGE 151) the start lights: the first pair at 3 s to GO, one more each 0.6 s
LAMP_DARK = (0.04, 0.002, 0.002)      # ...a pair's glow (linear light, as MATERIALS' emission) unlit and lit: unlit
LAMP_LIT = (9.0, 0.015, 0.006)         # nearly dark red glass, lit a red that the tone curve keeps red (not orange)


def start_lights(countdown):
    """(CHANGE 151) How many pairs of the gantry's start lights are lit, seconds before GO (None: the race isn't
    counting down): none, then from the left one pair every LIGHTS_STEP over the countdown's last three seconds (the
    3, 2, 1 on the screen), all five for the last 0.6 s, and all out at GO, as real start lights go."""
    if countdown is None or countdown <= 0.0 or countdown > LIGHTS_FROM:
        return 0
    return min(5, int((LIGHTS_FROM - countdown) / LIGHTS_STEP + 1e-9) + 1)


# ---------- small sums ----------
add, sub, mul, dot, cross, norm = kart_models.add, kart_models.sub, kart_models.mul, kart_models.dot, kart_models.cross, kart_models.norm


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def shade(c, k):
    """A colour times k (each channel, kept under 1)."""
    return tuple(min(1.0, v * k) for v in c)


def mix(a, b, t):
    return tuple(lerp(x, y, t) for x, y in zip(a, b))


def hash01(*ints):
    """A number from 0 to 1 that depends only on the integers given (the same in any language)."""
    h = 0x811C9DC5
    for i in ints:
        h = ((h ^ (int(i) & 0xFFFFFFFF)) * 0x01000193) & 0xFFFFFFFF
        h ^= h >> 15
        h = (h * 0x2C1B3C6D) & 0xFFFFFFFF
        h ^= h >> 12
    return (h & 0xFFFFFF) / 16777216.0


def noise(x, y, seed=0):
    """Smooth value noise from 0 to 1, one feature a unit apart."""
    xi, yi = math.floor(x), math.floor(y)
    fx, fy = smooth(x - xi), smooth(y - yi)
    a, b = hash01(xi, yi, seed), hash01(xi + 1, yi, seed)
    c, d = hash01(xi, yi + 1, seed), hash01(xi + 1, yi + 1, seed)
    return lerp(lerp(a, b, fx), lerp(c, d, fx), fy)


def fbm(x, y, seed=0, octaves=3):
    total, amp, out = 0.0, 1.0, 0.0
    for o in range(octaves):
        out += noise(x, y, seed + o * 17) * amp
        total += amp
        amp *= 0.5
        x, y = x * 2.03 + 1.7, y * 2.03 + 9.2
    return out / total


def frame(heading):
    """The unit vectors forward and left for a heading in radians, and up."""
    c, s = math.cos(heading), math.sin(heading)
    return (c, s, 0.0), (-s, c, 0.0), (0.0, 0.0, 1.0)


def at(origin, axes, x, y, z):
    """origin + x, y, z along the axes (forward, left, up)."""
    a, b, c = axes
    return (origin[0] + a[0] * x + b[0] * y + c[0] * z, origin[1] + a[1] * x + b[1] * y + c[1] * z,
            origin[2] + a[2] * x + b[2] * y + c[2] * z)


def b64(values):
    """An array's bytes, little-endian, in base64."""
    if sys.byteorder == "big":
        values = array(values.typecode, values)
        values.byteswap()
    return base64.b64encode(values.tobytes()).decode("ascii")


# ---------- a part ----------
class Part(kart_models.Part):
    """kart_models' Part in a material (for its role), with a colour per vertex (screen colours; self.colour is the
    colour given to new vertices) and whether an instance's tint colours it."""

    def __init__(self, name, material, tint=False, far=False, group=""):
        super().__init__(name, material)
        self.material, self.tint, self.far, self.group = material, tint, far, group
        self.c = []
        self.colour = (1.0, 1.0, 1.0)

    def vertex(self, p, n, uv=(0.0, 0.0), c=None):
        self.c.append(self.colour if c is None else c)
        return super().vertex(p, n, uv)

    def quad(self, pts, n, uvs=((0, 0), (1, 0), (1, 1), (0, 1)), c=None):
        """A flat quad facing n (its corners in order round it, either way)."""
        v = [self.vertex(p, n, uv, c) for p, uv in zip(pts, uvs)]
        self.tri(v[0], v[1], v[2])
        self.tri(v[0], v[2], v[3])

    def face(self, pts, n, metres=1.0, c=None):
        """A flat quad whose texture is to scale (metres a repeat)."""
        w, h = math.dist(pts[0], pts[1]) / metres, math.dist(pts[0], pts[3]) / metres
        self.quad(pts, n, [(0, 0), (w, 0), (w, h), (0, h)], c)

    def tris(self):
        return len(self.idx) // 3

    def packed(self):
        """The part as models/kart_scenery.json keeps it (a fifth the size of plain lists of numbers): each array
        packed little-endian and written in base64. positions: uint16 per coordinate, from "box" (min x, y, z, max x, y, z)
        in 65535 steps; uvs: uint16 the same way in "uv_box" (min u, v, max u, v); normals: int8 (times 127);
        colours: uint8 (times 255), only if not all white; indices: uint16, or uint32 if "count" is 65536 or more."""
        n = len(self.p)
        r3 = lambda v: round(v, 3) + 0.0  # noqa: E731  (+ 0.0: never "-0.0")
        box_ = [r3(min(p[k] for p in self.p) - 0.0005) for k in range(3)] + [r3(max(p[k] for p in self.p) + 0.001) for k in range(3)]
        uv_box = [r3(min(t[k] for t in self.uv) - 0.0005) for k in range(2)] + [r3(max(t[k] for t in self.uv) + 0.001) for k in range(2)]
        positions = array("H", (min(65535, max(0, round((p[k] - box_[k]) / (box_[k + 3] - box_[k]) * 65535)))
                                for p in self.p for k in range(3)))
        uvs = array("H", (min(65535, max(0, round((t[k] - uv_box[k]) / (uv_box[k + 2] - uv_box[k]) * 65535)))
                          for t in self.uv for k in range(2)))
        normals = array("b", (max(-127, min(127, round(c * 127))) for v in self.n for c in v))
        indices = array("H" if n < 65536 else "I", self.idx)
        out = {"name": self.name, "material": self.material, "count": n, "box": box_, "uv_box": uv_box,
               "positions": b64(positions), "normals": b64(normals), "uvs": b64(uvs), "indices": b64(indices)}
        if any(c != (1.0, 1.0, 1.0) for c in self.c):
            out["colours"] = b64(array("B", (max(0, min(255, round(v * 255))) for c in self.c for v in c)))
        if self.tint:
            out["tint"] = True
        if self.far:
            out["far"] = True
        if self.group:
            out["group"] = self.group
        return out


class Parts:
    """A set of parts, one per material (and tint and far): get() gives the one to add to. group: a part of its own
    in that material, drawn apart because it changes while the race runs (CHANGE 151: each pair of start lights)."""

    def __init__(self, far=False):
        self.by = {}
        self.far = far

    def get(self, material, tint=False, far=None, group=""):
        far = self.far if far is None else far
        key = (material, tint, far, group)
        if key not in self.by:
            self.by[key] = Part(material + (" tinted" if tint else "") + (" far" if far else "") + (f" {group}" if group else ""),
                                material, tint, far, group)
        return self.by[key]

    def all(self):
        return [p for p in self.by.values() if p.idx]


# ---------- shapes ----------
def box(part, origin, axes, x0, x1, y0, y1, z0, z1, metres=1.0, skip=(), c=None):
    """A box from x0 to x1, y0 to y1, z0 to z1 along the axes from origin. skip: faces left out ("-z", "+x", ...)."""
    corner = lambda x, y, z: at(origin, axes, x, y, z)  # noqa: E731
    a, b, u = axes
    faces = {"+x": (a, [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (y1 - y0, z1 - z0)),
             "-x": (mul(a, -1), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], (y1 - y0, z1 - z0)),
             "+y": (b, [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], (x1 - x0, z1 - z0)),
             "-y": (mul(b, -1), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (x1 - x0, z1 - z0)),
             "+z": (u, [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (x1 - x0, y1 - y0)),
             "-z": (mul(u, -1), [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], (x1 - x0, y1 - y0))}
    for key, (n, pts, (w, h)) in faces.items():
        if key in skip:
            continue
        w, h = w / metres if metres else 1.0, h / metres if metres else 1.0
        part.quad([corner(*p) for p in pts], n, [(0, 0), (w, 0), (w, h), (0, h)], c)


def rod(part, a, b, r, seg=6, c=None, metres=1.0):
    """A straight round bar from a to b (posts, rails, cables), open at the ends."""
    ahead = norm(sub(b, a))
    side = norm(cross(ahead, (0, 0, 1) if abs(ahead[2]) < 0.9 else (1, 0, 0)))
    up = cross(side, ahead)
    length = math.dist(a, b)
    first = None
    for j in range(seg + 1):
        t = 2 * math.pi * j / seg
        n = add(mul(side, math.cos(t)), mul(up, math.sin(t)))
        i0 = part.vertex(add(a, mul(n, r)), n, (j / seg, 0.0), c)
        part.vertex(add(b, mul(n, r)), n, (j / seg, length / metres), c)
        if first is not None:
            part.tri(first, first + 1, i0 + 1)
            part.tri(first, i0 + 1, i0)
        first = i0


def column(part, base, r0, r1, h, seg=8, c=None, top=True, metres=1.0):
    """An upright tapering round column (a trunk, a pole) from base up h, r0 at the foot and r1 at the top."""
    rows, normals, uvs = [], [], []
    slope = (r0 - r1) / h if h else 0.0
    for z, r in ((0.0, r0), (h, r1)):
        rows.append([(base[0] + r * math.cos(2 * math.pi * j / seg), base[1] + r * math.sin(2 * math.pi * j / seg),
                      base[2] + z) for j in range(seg + 1)])
        normals.append([norm((math.cos(2 * math.pi * j / seg), math.sin(2 * math.pi * j / seg), slope)) for j in range(seg + 1)])
        uvs.append([(j / seg * 2 * math.pi * r0 / metres, z / metres) for j in range(seg + 1)])
    start = len(part.p)
    for row, nrow, uvrow in zip(rows, normals, uvs):
        for p, n, uv in zip(row, nrow, uvrow):
            part.vertex(p, n, uv, c)
    for j in range(seg):
        a, b = start + j, start + j + 1
        part.tri(a, b, b + seg + 1)
        part.tri(a, b + seg + 1, a + seg + 1)
    if top and r1 > 0:
        mid = part.vertex((base[0], base[1], base[2] + h), (0, 0, 1), (0.5, 0.5), c)
        rim = [part.vertex(p, (0, 0, 1), (0.5, 0.5), c) for p in rows[1][:-1]]
        for j in range(seg):
            part.tri(mid, rim[j], rim[(j + 1) % seg])


def lathe_z(part, base, profile, seg=10, colours=None, metres=1.0):
    """A shape turned about an upright axis through base: profile is (radius, height) points from the top down the
    outside. colours: one per profile point (or None)."""
    rows, normals, uvs = [], [], []
    v = 0.0
    for i, (r, z) in enumerate(profile):
        a, b = profile[max(0, i - 1)], profile[min(len(profile) - 1, i + 1)]
        dr, dz = b[0] - a[0], b[1] - a[1]
        nr, nz = -dz, dr  # (the profile turned a quarter: outwards for a profile running down the outside)
        d = math.hypot(nr, nz) or 1.0
        nr, nz = nr / d, nz / d
        if i:
            v += math.dist(profile[i], profile[i - 1])
        cs = [(math.cos(2 * math.pi * j / seg), math.sin(2 * math.pi * j / seg)) for j in range(seg + 1)]
        rows.append([(base[0] + r * c, base[1] + r * s, base[2] + z) for c, s in cs])
        normals.append([(nr * c, nr * s, nz) for c, s in cs])
        uvs.append([(j / seg * 2 * math.pi * max(r, 0.05) / metres, v / metres) for j in range(seg + 1)])
    start = len(part.p)
    for i, (row, nrow, uvrow) in enumerate(zip(rows, normals, uvs)):
        for p, n, uv in zip(row, nrow, uvrow):
            part.vertex(p, n, uv, colours[i] if colours else None)
    w = seg + 1
    for i in range(len(rows) - 1):
        for j in range(seg):
            a = start + i * w + j
            part.tri(a, a + 1, a + w + 1)
            part.tri(a, a + w + 1, a + w)


def blob(part, centre, radii, seg=8, rings=5, seed=0, bump=0.25, colour_fn=None, metres=1.0):
    """A lumpy ball (a clump of leaves, a bush, a rock): an ellipsoid pushed in and out by noise. colour_fn(p, n)
    gives each vertex's colour."""
    rows = []
    for i in range(rings + 1):
        lat = -math.pi / 2 + math.pi * i / rings
        row = []
        for j in range(seg + 1):
            lon = 2 * math.pi * (j % seg) / seg
            d = (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))
            k = 1.0 + bump * (noise(d[0] * 1.7 + seed * 3.1, d[1] * 1.7 + d[2] * 1.3, seed) - 0.5) * 2
            row.append(add(centre, (d[0] * radii[0] * k, d[1] * radii[1] * k, d[2] * radii[2] * k)))
        rows.append(row)
    start = len(part.p)
    part.surface(rows, lambda p: centre, pole_normals={0: (0, 0, -1), rings: (0, 0, 1)}, uv_scale=1.0 / metres)
    if colour_fn:
        for i in range(start, len(part.p)):
            part.c[i] = colour_fn(part.p[i], part.n[i])


# ---------- the shapes placed many times (each in its own frame, the ground at z = 0) ----------
def pine(height, layers, spikes, seed, far=False):
    """A pine: a tapering trunk and layers of drooping branches, each a star of spikes (long and short) that rises
    to the trunk and droops at its tips, lighter on top and at the tips, dark underneath. far: fewer layers and
    spikes, for the woods out in the country."""
    rnd = random.Random(seed)
    trunk, needles = Part("trunk", "bark", far=far), Part("needles", "needles", tint=True, far=far)
    column(trunk, (0, 0, -0.3), 0.05 + 0.022 * height, 0.03, height * 0.92 + 0.3, seg=4 if far else 7, metres=1.0,
           c=(0.85, 0.85, 0.85), top=False)
    for i in range(layers):
        t = i / (layers - 1)
        z = height * (0.2 + 0.7 * (1 - (1 - t) ** 1.5))  # (the layers closer together towards the top)
        big = height * 0.3 * (1 - 0.8 * t) + 0.25
        rise, droop = big * 0.55, big * 0.42
        turn = rnd.random() * 2 * math.pi
        n = spikes * 2
        tips, mids = [], []
        for j in range(n):
            a = turn + 2 * math.pi * j / n
            r = big * (1.0 if j % 2 == 0 else 0.68) * (0.88 + 0.24 * rnd.random())
            out = (math.cos(a), math.sin(a), 0.0)
            tips.append(((out[0] * r, out[1] * r, z - droop * (r / big) ** 1.4), out))
            mids.append(((out[0] * r * 0.5, out[1] * r * 0.5, z + rise * 0.42), out))
        top = 1.0 - 0.25 * (1 - t)  # (the lower layers a little darker: the upper ones shade them)
        apex = needles.vertex((0, 0, z + rise), (0, 0, 1), (0, 0), shade((0.95, 1.0, 0.92), top))
        under = needles.vertex((0, 0, z - droop * 0.35), (0, 0, -1), (0, 0), (0.32, 0.36, 0.3))
        ring_t = [needles.vertex(p, norm(add(mul(o, 0.85), (0, 0, 0.5))), (p[0] / 2, p[1] / 2),
                                 shade((1.05, 1.08, 0.88), top)) for p, o in tips]
        ring_u = [needles.vertex(p, norm(add(mul(o, 0.4), (0, 0, -1))), (p[0] / 2, p[1] / 2), (0.4, 0.44, 0.36))
                  for p, o in tips]
        if far:
            for j in range(n):
                needles.tri(apex, ring_t[j], ring_t[(j + 1) % n])
        else:
            ring_m = [needles.vertex(p, norm(add(mul(o, 0.45), (0, 0, 0.9))), (p[0] / 2, p[1] / 2),
                                     shade((0.9, 0.95, 0.85), top)) for p, o in mids]
            for j in range(n):
                k = (j + 1) % n
                needles.tri(apex, ring_m[j], ring_m[k])
                needles.tri(ring_m[j], ring_t[j], ring_t[k])
                needles.tri(ring_m[j], ring_t[k], ring_m[k])
        for j in range(n):
            needles.tri(under, ring_u[(j + 1) % n], ring_u[j])
    tip = needles.vertex((0, 0, height * 1.04), (0, 0, 1), (0, 0), (0.95, 1.0, 0.9))  # (a spire above the top layer)
    base_z = height * 0.9
    spire = [needles.vertex((math.cos(2 * math.pi * j / 5) * 0.18, math.sin(2 * math.pi * j / 5) * 0.18, base_z),
                            norm((math.cos(2 * math.pi * j / 5), math.sin(2 * math.pi * j / 5), 0.4)), (0, 0), (0.85, 0.9, 0.8))
             for j in range(5)]
    for j in range(5):
        needles.tri(tip, spire[j], spire[(j + 1) % 5])
    return [trunk, needles]


def broadleaf(height, lobes, seed, far=False):
    """A broadleaf tree: a trunk forking into branches under a clumpy crown of leafy lobes, darker underneath and
    inside, lighter where the sun falls. far: three lobes and no branches."""
    rnd = random.Random(seed)
    trunk, leaves = Part("trunk", "bark", far=far), Part("leaves", "leaves", tint=True, far=far)
    fork = height * 0.34
    column(trunk, (0, 0, -0.3), 0.07 + 0.025 * height, 0.06 + 0.012 * height, fork + 0.3, seg=4 if far else 8,
           c=(0.85, 0.85, 0.85), top=False)
    crown_z, crown_r = height * 0.6, height * 0.34
    if not far:
        for k in range(3):
            a = 2 * math.pi * k / 3 + rnd.random()
            end = (math.cos(a) * crown_r * 0.6, math.sin(a) * crown_r * 0.6, crown_z + rnd.uniform(-0.3, 0.6))
            kart_models.tube(trunk, [(0, 0, fork - 0.2), (end[0] * 0.4, end[1] * 0.4, fork + (end[2] - fork) * 0.55), end],
                             [0.07 + 0.012 * height, 0.06, 0.035], seg=5, steps=2, caps=False)
    spots = [(0.0, 0.0, crown_z + crown_r * 0.25, 0.8)]
    for k in range(lobes - 1):  # (clumps round a squashed ball: more round the middle, smaller towards the top)
        a = 2 * math.pi * k / (lobes - 1) + rnd.uniform(-0.4, 0.4)
        up_ = rnd.uniform(-0.55, 0.75)
        d = crown_r * math.sqrt(max(0.0, 1 - up_ * up_)) * rnd.uniform(0.65, 0.95)
        spots.append((math.cos(a) * d, math.sin(a) * d, crown_z + up_ * crown_r * 0.75, rnd.uniform(0.45, 0.62) * (1 - 0.25 * max(0.0, up_))))
    zlo, zhi = crown_z - crown_r, crown_z + crown_r * 1.2

    def colour(p, n):
        k = 0.5 + 0.28 * (n[2] * 0.5 + 0.5) + 0.32 * clamp((p[2] - zlo) / (zhi - zlo))
        return (k * 0.96, k, k * 0.86)
    for i, (x, y, z, k) in enumerate(spots):
        r = crown_r * k * (1.15 if far else 0.82)
        blob(leaves, (x, y, z), (r, r, r * 0.8), seg=6 if far else 8, rings=4 if far else 5, seed=seed * 7 + i,
             bump=0.22, colour_fn=colour, metres=2.0)
    return [trunk, leaves]


def bush(seed):
    """A bush: a few leafy lobes on the ground."""
    rnd = random.Random(seed)
    leaves = Part("leaves", "leaves", tint=True)

    def colour(p, n):
        k = 0.45 + 0.3 * (n[2] * 0.5 + 0.5) + 0.35 * clamp(p[2] / 1.1)
        return (k * 0.95, k, k * 0.85)
    for i in range(4):
        a = 2 * math.pi * i / 4 + rnd.random()
        d = 0.0 if i == 0 else rnd.uniform(0.35, 0.55)
        r = rnd.uniform(0.45, 0.7)
        blob(leaves, (math.cos(a) * d, math.sin(a) * d, r * 0.55), (r, r, r * 0.8), seg=7, rings=5, seed=seed + i,
             bump=0.3, colour_fn=colour, metres=2.0)
    return [leaves]


def rock(seed):
    """A rock half sunk in the grass."""
    stone = Part("rock", "rock", tint=True)
    blob(stone, (0, 0, 0.08), (0.55, 0.42, 0.32), seg=7, rings=5, seed=seed, bump=0.4,
         colour_fn=lambda p, n: shade((0.92, 0.9, 0.86), 0.55 + 0.45 * (n[2] * 0.5 + 0.5)), metres=1.0)
    return [stone]


def tuft(seed, blades=7, flowers=0):
    """A tuft of grass: blades leaning out from the middle, dark at the root and light at the tip. flowers: that
    many little five-petalled heads on stalks (tinted: the instance's colour is the petals')."""
    rnd = random.Random(seed)
    grass = Part("blades", "blades", tint=not flowers)
    for j in range(blades):
        a = 2 * math.pi * j / blades + rnd.uniform(-0.35, 0.35)
        out = (math.cos(a), math.sin(a), 0.0)
        side = (-out[1], out[0], 0.0)
        h = rnd.uniform(0.16, 0.3)
        lean = rnd.uniform(0.05, 0.13)
        root = mul(out, 0.025)
        w = rnd.uniform(0.012, 0.018)
        n = norm(add(mul(out, 0.35), (0, 0, 1)))
        tip = add(add(root, mul(out, lean)), (0, 0, h))
        a0 = grass.vertex(add(root, mul(side, w)), n, (0, 0), (0.17, 0.28, 0.08))
        a1 = grass.vertex(add(root, mul(side, -w)), n, (1, 0), (0.17, 0.28, 0.08))
        a2 = grass.vertex(tip, n, (0.5, 1), (0.5, 0.64, 0.26))
        grass.tri(a0, a1, a2)
    parts = [grass]
    if flowers:
        petals = Part("petals", "blades", tint=True)
        for j in range(flowers):
            a = 2 * math.pi * j / flowers + rnd.random()
            c = (math.cos(a) * 0.07, math.sin(a) * 0.07, rnd.uniform(0.2, 0.3))
            kart_models.tube(grass, [(c[0] * 0.3, c[1] * 0.3, 0.0), c], 0.004, seg=3, steps=1, caps=False)
            mid = petals.vertex(add(c, (0, 0, 0.004)), (0, 0, 1), (0.5, 0.5), (1.0, 0.9, 0.35))
            rim = []
            for k in range(10):
                t = 2 * math.pi * k / 10
                r = 0.028 if k % 2 == 0 else 0.012
                rim.append(petals.vertex(add(c, (math.cos(t) * r, math.sin(t) * r, 0.0)), (0, 0, 1), (0, 0), (1.0, 1.0, 1.0)))
            for k in range(10):
                petals.tri(mid, rim[k], rim[(k + 1) % 10])
        parts.append(petals)
    return parts


def tyre_stack():
    """Three old tyres stacked (a tyre wall is a row of them; tinted: painted bands)."""
    tyres = Part("tyres", "tyre_wall", tint=True)
    profile, colours = [(0.17, 0.6)], [(0.55, 0.55, 0.55)]
    for k in (2, 1, 0):
        top, bottom = 0.2 * (k + 1), 0.2 * k
        profile += [(0.27, top), (0.3, top - 0.045), (0.3, bottom + 0.045), (0.27, bottom)]
        colours += [(0.75, 0.75, 0.75), (1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (0.6, 0.6, 0.6)]
    lathe_z(tyres, (0, 0, 0), profile, seg=8, colours=colours)
    lathe_z(tyres, (0, 0, 0), [(0.17, 0.4), (0.17, 0.6)], seg=8, colours=[(0.12, 0.12, 0.12), (0.4, 0.4, 0.4)])
    return [tyres]


def fan(skin, hair, wave=False, cap=None):
    """Someone sitting in the grandstand, facing +x (the seat at z = 0): a shirt (tinted), trousers, arms, a head
    and hair (or a cap)."""
    shirt, clothes = Part("shirt", "paint", tint=True), Part("clothes", "paint")
    head = Part("head", "skin")
    kart_models.superellipsoid(shirt, (-0.03, 0.0, 0.3), (0.11, 0.17, 0.25), e=2.6, seg=6, rings=4)
    for side in (1, -1):
        if wave and side < 0:
            kart_models.tube(shirt, [(0.0, -0.19, 0.48), (0.03, -0.27, 0.72), (0.06, -0.3, 0.95)], 0.042, seg=4, steps=1)
        else:
            kart_models.tube(shirt, [(-0.01, side * 0.19, 0.48), (0.05, side * 0.21, 0.24), (0.2, side * 0.15, 0.17)],
                             0.042, seg=4, steps=1)
    clothes.colour = (0.16, 0.2, 0.3)
    for side in (1, -1):
        kart_models.tube(clothes, [(0.0, side * 0.085, 0.06), (0.36, side * 0.095, 0.07)], 0.07, seg=4, steps=1)
        kart_models.tube(clothes, [(0.36, side * 0.095, 0.07), (0.4, side * 0.095, -0.36)], 0.055, seg=4, steps=1)
    head.colour = skin
    kart_models.superellipsoid(head, (0.0, 0.0, 0.68), (0.095, 0.085, 0.11), e=2.2, seg=7, rings=4)
    clothes.colour = cap or hair
    kart_models.superellipsoid(clothes, (-0.018, 0.0, 0.72 if cap is None else 0.75),
                               (0.096, 0.09, 0.095 if cap is None else 0.07), e=2.4 if cap is None else 3.0, seg=7, rings=3)
    if cap is not None:
        box(clothes, (0.06, 0.0, 0.745), frame(0.0), 0.0, 0.1, -0.07, 0.07, 0.0, 0.015)
    return [shirt, clothes, head]


def marshal_post():
    """A marshals' post facing +x: an orange hut with a window and a white roof, and a flag on a pole (tinted: the
    flag's colour)."""
    hut, glass, steel, flag = Part("hut", "paint"), Part("window", "glass"), Part("pole", "steel"), Part("flag", "cloth", tint=True)
    axes = frame(0.0)
    hut.colour = (0.95, 0.45, 0.1)
    box(hut, (0, 0, 0), axes, -0.7, 0.7, -0.7, 0.7, -0.2, 2.2, skip=("-z",))
    hut.colour = (0.92, 0.92, 0.9)
    box(hut, (0, 0, 0), axes, -0.85, 0.85, -0.85, 0.85, 2.2, 2.32)
    glass.quad([(0.705, -0.5, 1.15), (0.705, 0.5, 1.15), (0.705, 0.5, 1.85), (0.705, -0.5, 1.85)], (1, 0, 0))
    column(steel, (0.5, 0.95, 0.0), 0.03, 0.025, 3.3, seg=6)
    for i in range(7):  # (the flag: rippling in the breeze along -x)
        t = i / 6
        x = 0.5 - 0.06 - t * 0.9
        y = 0.95 + 0.07 * math.sin(t * 5.0) * t
        v = [flag.vertex((x, y, z), norm((0.3 * math.cos(t * 5.0), 1.0, 0.0)), (t, z), (1, 1, 1)) for z in (2.65, 3.25)]
        if i:
            flag.tri(v[0] - 2, v[0], v[1])
            flag.tri(v[0] - 2, v[1], v[1] - 2)
    return [hut, glass, steel, flag]


def flagpole():
    """A tall flagpole with a big flag (tinted) flying along -x."""
    steel, flag = Part("pole", "steel"), Part("flag", "cloth", tint=True)
    column(steel, (0, 0, 0), 0.06, 0.035, 8.5, seg=6)
    for i in range(9):
        t = i / 8
        x = -0.05 - t * 2.1
        y = 0.18 * math.sin(t * 6.0 + 0.5) * t
        v = [flag.vertex((x, y, z), norm((0.4 * math.cos(t * 6.0 + 0.5), 1.0, 0.0)), (t, z), (1, 1, 1)) for z in (7.0, 8.4)]
        if i:
            flag.tri(v[0] - 2, v[0], v[1])
            flag.tri(v[0] - 2, v[1], v[1] - 2)
    return [steel, flag]


def seat():
    """A grandstand seat facing +x, the step it stands on at z = 0 (tinted: the seat's colour)."""
    shell = Part("seat", "paint", tint=True)
    box(shell, (0, 0, 0), frame(0.0), -0.18, 0.18, -0.21, 0.21, 0.38, 0.44, skip=("-z",))
    box(shell, (0, 0, 0), frame(0.0), -0.24, -0.18, -0.21, 0.21, 0.38, 0.8, skip=("-z",))
    box(shell, (0, 0, 0), frame(0.0), -0.05, 0.05, -0.04, 0.04, 0.0, 0.38, skip=("-z", "+z"), c=(0.3, 0.3, 0.32))
    return [shell]


def post():
    """An armco post (its rail on the -x side)."""
    steel = Part("post", "steel")
    box(steel, (0, 0, 0), frame(0.0), -0.05, 0.05, -0.04, 0.04, -0.3, 0.8, metres=2.0, skip=("-z",))
    return [steel]


def pole():
    """A fence post, 1.4 m."""
    steel = Part("pole", "steel")
    rod(steel, (0, 0, 0), (0, 0, 1.4), 0.035, seg=5)
    return [steel]


SKINS = [(0.92, 0.74, 0.62), (0.76, 0.55, 0.4), (0.48, 0.32, 0.22)]
HAIR = [(0.36, 0.24, 0.14), (0.08, 0.06, 0.05), (0.78, 0.62, 0.36)]


def shapes():
    """Every shape, by name."""
    out = {"pine_a": pine(9.0, 7, 9, 1), "pine_b": pine(11.0, 8, 8, 2),
           "broadleaf_a": broadleaf(9.0, 13, 3), "broadleaf_b": broadleaf(7.5, 11, 4),
           "pine_far": pine(10.0, 4, 5, 5, far=True), "broadleaf_far": broadleaf(8.5, 3, 6, far=True),
           "bush_a": bush(7), "bush_b": bush(8), "rock": rock(9),
           "tuft": tuft(10), "tuft_long": tuft(11, blades=9), "flowers": tuft(12, blades=4, flowers=3),
           "tyres": tyre_stack(), "marshal_post": marshal_post(), "flagpole": flagpole(),
           "seat": seat(), "post": post(), "pole": pole(),
           "fan_a": fan(SKINS[0], HAIR[0]), "fan_b": fan(SKINS[1], HAIR[1], wave=True),
           "fan_c": fan(SKINS[2], HAIR[1], cap=(0.85, 0.15, 0.12)), "fan_d": fan(SKINS[0], HAIR[2])}
    return out


# ---------- one track's circuit ----------
KERB = [(-0.5, 0.008), (0.0, 0.012), (0.12, 0.028), (0.26, 0.048), (0.38, 0.056), (0.48, 0.04), (0.56, -0.07)]  # (out from the road's edge, up)
ARMCO = [(0.09, 0.43), (0.0, 0.5), (0.05, 0.6), (0.0, 0.7), (0.09, 0.77)]  # (back from its face, up: two humps)
TYRE_BANDS = [((0.93, 0.93, 0.9), (0.82, 0.12, 0.1)), ((0.93, 0.93, 0.9), (0.12, 0.3, 0.78)),
              ((0.95, 0.8, 0.12), (0.1, 0.1, 0.11)), ((0.93, 0.93, 0.9), (0.1, 0.1, 0.11))]
SHIRTS = [(0.85, 0.15, 0.12), (0.1, 0.36, 0.86), (0.95, 0.8, 0.15), (0.15, 0.6, 0.25), (0.95, 0.95, 0.95),
          (0.12, 0.12, 0.14), (0.95, 0.45, 0.1), (0.55, 0.2, 0.65), (0.1, 0.36, 0.86), (0.3, 0.75, 0.9)]
FIELDS = [((0.36, 0.5, 0.2), 0.2), ((0.42, 0.56, 0.24), 0.18), ((0.3, 0.44, 0.17), 0.12), ((0.5, 0.6, 0.28), 0.08),
          ((0.76, 0.66, 0.34), 0.13), ((0.7, 0.66, 0.42), 0.08), ((0.88, 0.82, 0.24), 0.05), ((0.42, 0.32, 0.22), 0.09),
          ((0.64, 0.57, 0.36), 0.07)]  # (colour, how often): pasture, meadow, wheat, barley, rapeseed, ploughed, stubble
STAND_D0, STAND_DEPTH = 5.0, 8.2  # the grandstand: its front this far from the road's edge, and how deep it is
PIT_D0, PIT_DEPTH = 1.5, 13.0     # the pit lane (behind the pit wall) and the garages behind it
PIT_FRONT = 6.5                   # the garages' front, from the pit building's origin (CHANGE 179: the lane's outer wall)
GANTRY_D = 2.2                    # the start gantry's towers, past the road's edge
BRIDGE_CLEAR = 5.1                # (CHANGE 151) the footbridge's underside over the road's middle
BRIDGE_IN, BRIDGE_OUT = 2.6, 4.4  # ...its stair towers from (and to) this far past the road's edge
BRIDGE_RISE, BRIDGE_TREAD = 0.18, 0.28  # ...its steps


def runs(mask, st, gap, least):
    """The stretches (first, last index) where mask is true, joined over gaps under gap metres, at least least long."""
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            if out and st[i] - st[out[-1][1]] < gap:
                out[-1][1] = j
            else:
                out.append([i, j])
            i = j + 1
        else:
            i += 1
    return [(a, b) for a, b in out if st[b] - st[a] >= least]


def sheet(part, rows, normals, uvs, colours=None):
    """Quads between rows of points (each row the same length), each vertex its own colour."""
    base = []
    for r, (row, nrow, uvrow) in enumerate(zip(rows, normals, uvs)):
        crow = colours[r] if colours else [None] * len(row)
        base.append([part.vertex(p, n, uv, c) for p, n, uv, c in zip(row, nrow, uvrow, crow)])
    for r in range(len(rows) - 1):
        for j in range(len(rows[r]) - 1):
            a, b, c, d = base[r][j], base[r][j + 1], base[r + 1][j + 1], base[r + 1][j]
            part.tri(a, b, c)
            part.tri(a, c, d)


class Circuit:
    """One track's ultra circuit, built as it is made: its parts (one per material) and its instances (by shape)."""

    def __init__(self, track):
        self.t = track
        self.half, self.L = track.half, track.length
        self.near, self.far = Parts(), Parts(far=True)
        self.inst = {}
        self.keep = []  # (x, y, r): ground taken by what's built (nothing else goes there)
        self.cams = tv_cameras(track)
        self.cam_keep = [(x, y, CAMERA_CLEAR) for x, y, z, side, s in self.cams]
        self.bins = {}
        for i, p in enumerate(track.pts):
            self.bins.setdefault((int(p[0] // 10), int(p[1] // 10)), []).append(i)
        self.st = [track.s[i] for i in range(track.n)] + [track.length]  # (the centre line's points, the last the first again)
        self.curv = [track.curvature(s - 9.0, 18.0) for s in self.st]    # (each bend measured round its middle)
        self.verge = {}
        rnd = random.Random(23)  # (the hills' shape: the lower tiers' had it too)
        self.waves = [(rnd.randint(2, 11), rnd.uniform(0, 2 * math.pi), rnd.uniform(0.3, 1.0)) for _ in range(9)]
        self.layout()
        self.place_pond()
        self.ground()
        self.road()
        self.paint()
        for side in (1, -1):
            self.edge(side)
        self.grandstand()
        self.pit_lane()  # (CHANGE 179)
        self.pit_building()
        self.gantry()
        self.bridge()
        self.boards()
        self.marshals()
        self.camera_towers()
        self.plants()
        self.country()

    # ---------- questions ----------
    def dist(self, x, y, reach=30.0):
        """How far (x, y) is from the track's centre line (reach, if it's further than that)."""
        best = reach * reach
        r = int(reach // 10) + 1
        bx, by = int(x // 10), int(y // 10)
        pts = self.t.pts
        for i in range(bx - r, bx + r + 1):
            for j in range(by - r, by + r + 1):
                for k in self.bins.get((i, j), ()):
                    p = pts[k]
                    d = (p[0] - x) ** 2 + (p[1] - y) ** 2
                    if d < best:
                        best = d
        return math.sqrt(best)

    def free(self, x, y, r, cameras=True):
        """Is a circle r round (x, y) clear of what's built (and of the TV cameras' ground, if cameras)?"""
        for a, b, rr in self.keep + (self.cam_keep if cameras else []):
            if (x - a) ** 2 + (y - b) ** 2 < (r + rr) ** 2:
                return False
        return True

    def out_of(self, s, side):
        """The unit vector across the track at s, away from it on that side (1: the left)."""
        tx, ty = self.t.tan[self.t.segment_at(s)]
        return (-ty * side, tx * side, 0.0)

    def put(self, shape, x, y, z, h, s=1.0, tint=(1.0, 1.0, 1.0)):
        """An instance of a shape (rounded as the file keeps it, so the window draws exactly the same)."""
        self.inst.setdefault(shape, []).append([round(x, 2) + 0.0, round(y, 2) + 0.0, round(z, 2) + 0.0,
                                                round(h % 360.0, 1) + 0.0, round(s, 3) + 0.0,
                                                *(round(c, 2) + 0.0 for c in tint)])

    def ground_z(self, x, y):
        """The ground's height at (x, y) as its triangles have it (the country's, past the grass)."""
        xs, ys, z = self.xs, self.ys, self.z
        fx, fy = (x - xs[0]) / CELL, (y - ys[0]) / CELL
        if not (0 <= fx <= len(xs) - 1 and 0 <= fy <= len(ys) - 1):
            return self.land_z(x, y)
        i, j = min(len(xs) - 2, int(fx)), min(len(ys) - 2, int(fy))
        fx, fy = fx - i, fy - j
        z00, z10, z01, z11 = z[j][i], z[j][i + 1], z[j + 1][i], z[j + 1][i + 1]
        if fx >= fy:  # (each cell is two triangles split along its rising diagonal)
            return z00 + fx * (z10 - z00) + fy * (z11 - z10)
        return z00 + fy * (z01 - z00) + fx * (z11 - z01)

    def land_height(self, r, a):
        """The country's height over the floor r metres from the middle, a radians round: flat a little past the
        grass, then hills, then mountains round the horizon (the lower tiers' ultra Land, as it was)."""
        rise = (r - self.reach * 1.25) / 360.0
        if rise <= 0:
            return 0.0
        wave = sum(amp * math.sin(n * a + ph) for n, ph, amp in self.waves) / 3.0
        hills = min(1.0, rise) ** 2 * (28 + 16 * wave)
        far = clamp((rise - 1.2) / 2.4)
        mountains = far * far * (3 - 2 * far) * (90 + 60 * wave + 22 * math.sin(17 * a + 2 * wave))
        return max(0.0, hills + mountains)

    def land_z(self, x, y):
        dx, dy = x - self.centre[0], y - self.centre[1]
        return self.floor + self.land_height(math.hypot(dx, dy), math.atan2(dy, dx))

    def pond_q(self, x, y):
        """How far (x, y) is from the pond's middle, its shore at 1."""
        px, py, rx, ry, h = self.pond
        dx, dy = x - px, y - py
        u, v = dx * math.cos(h) + dy * math.sin(h), -dx * math.sin(h) + dy * math.cos(h)
        a = math.atan2(v / ry, u / rx)
        return math.hypot(u / rx, v / ry) / (1.0 + 0.3 * (noise(math.cos(a) * 1.6 + 5, math.sin(a) * 1.6 + 5, 77) - 0.5))

    # ---------- where the buildings go ----------
    def site(self, side, s_mid, length, d0, d1, slack):
        """A straight building's frame beside the road (its middle at s_mid, its front d0 past the road's edge, its
        back d1), if it fits there: clear of every part of the track (the road may bend up to slack metres nearer at
        its ends), the TV cameras and what's built already. (origin, (along, out, up)) or None."""
        t = self.t
        a, b, u = frame(math.radians(t.heading(s_mid)))
        axes = (a, mul(b, side), u)
        o = t.point(s_mid, side * (self.half + d0))
        n = max(2, int(length / 3))
        for i in range(n + 1):
            for y in (0.0, (d1 - d0) / 2, d1 - d0):
                p = at(o, axes, -length / 2 + length * i / n, y, 0.0)
                if self.dist(p[0], p[1], self.half + d0 + 2) < self.half + d0 - slack or not self.free(p[0], p[1], 1.0):
                    return None
        return o, axes

    def claim(self, o, axes, length, depth):
        n = max(1, int(length / 4))
        for i in range(n + 1):
            p = at(o, axes, -length / 2 + length * i / n, depth / 2, 0.0)
            self.keep.append((p[0], p[1], depth / 2 + 1.0))

    def claim_box(self, o, axes, x0, x1, y0, y1, r=1.5):
        """(CHANGE 179) The ground of a box in a building's frame taken, closely (small circles on a grid), so what
        stands just past it (the footbridge's tower past the pit building) still has its room."""
        nx, ny = max(1, int((x1 - x0) / r)), max(1, int((y1 - y0) / r))
        for i in range(nx + 1):
            for j in range(ny + 1):
                p = at(o, axes, x0 + (x1 - x0) * i / nx, y0 + (y1 - y0) * j / ny, 0.0)
                self.keep.append((p[0], p[1], r))

    def layout(self):
        """The grandstand and the pit building beside the start straight, each where it fits, on either side; the
        start gantry's towers."""
        self.stand = self.pits = None
        self.walls = {1: [], -1: []}  # (s0, s1): where the barrier is a wall (in front of the buildings)
        lane = self.t.lane  # (CHANGE 179) the pit lane's ground is taken (along the road: it bends a little): nothing
        if lane:            # else is built on it
            s_in, s_out, side = lane
            depth = self.t.lane_outer() - self.half - BARRIER
            for s in self.lane_ss(s_in, s_out):
                for k in range(int(depth / 1.5) + 1):
                    x, y, _ = self.t.point(s, side * (self.half + BARRIER + min(depth, k * 1.5)))
                    self.keep.append((x, y, 1.5))
        for side, s_mid in ((1, 8.0), (-1, 8.0), (1, 40.0), (-1, 40.0), (1, -30.0), (-1, -30.0)):
            for length in (30.0, 24.0, 18.0):
                got = self.site(side, s_mid, length, STAND_D0, STAND_D0 + STAND_DEPTH, 1.2)
                if got:
                    self.stand = (side, s_mid, length) + got
                    break
            if self.stand:
                break
        first = -1
        if self.stand:
            side, s_mid, length, o, axes = self.stand
            self.claim(o, axes, length + 6, STAND_DEPTH + 1)
            self.walls[side].append((s_mid - length / 2 - 3, s_mid + length / 2 + 3))
            first = -side
        if lane:  # (CHANGE 179) the pit building stands along the pit lane, its garages' front the lane's outer wall
            s_in, s_out, side = lane
            length = kart_track.LANE_BAYS * kart_track.LANE_BAY + 2.0  # (the garages along the bays, a metre over each end)
            s_mid = s_in + kart_track.LANE_RAMP + 2.0 + length / 2 - 1.0
            a, b, u = frame(math.radians(self.t.heading(s_mid)))
            d0 = self.t.lane_outer() - self.half - PIT_FRONT + 0.1  # (the garages' front PIT_FRONT behind the origin)
            self.pits = (side, s_mid, length, self.t.point(s_mid, side * (self.half + d0)), (a, mul(b, side), u))
            self.claim_box(self.pits[3], self.pits[4], -length / 2 - 1.0, length / 2 + 1.0, PIT_FRONT - 0.5, PIT_DEPTH + 0.5)
        else:
            for side, s_mid in ((first, -2.0), (first, -12.0), (first, 10.0), (first, 45.0), (-first, 45.0), (-first, -40.0)):
                for length in (36.0, 30.0, 24.0):
                    got = self.site(side, s_mid, length, PIT_D0, PIT_D0 + PIT_DEPTH, 0.4)
                    if got:
                        self.pits = (side, s_mid, length) + got
                        break
                if self.pits:
                    break
            if self.pits:
                side, s_mid, length, o, axes = self.pits
                self.claim(o, axes, length + 4, PIT_DEPTH + 1)
                self.walls[side].append((s_mid - length / 2 - 2, s_mid + length / 2 + 2))
        for side in (1, -1):
            x, y, z = self.t.point(0.0, side * (self.half + GANTRY_D))
            self.keep.append((x, y, 1.2))

    def place_pond(self):
        """A pond on the grass where there's room: inside the circuit if it's big enough, else beside it."""
        t = self.t
        x0, y0, x1, y1 = t.bounds()
        cx, cy = sum(p[0] for p in t.pts) / t.n, sum(p[1] for p in t.pts) / t.n
        rx, ry = 15.0, 9.5
        m = GROUND_MARGIN * 0.5
        self.pond = None
        for px, py in ((cx, cy), (cx, y0 - m), (cx, y1 + m), (x0 - m, cy), (x1 + m, cy)):
            if self.dist(px, py, self.half + 30 + rx) >= self.half + 12 + rx and self.free(px, py, rx + 3):
                self.pond = (px, py, rx, ry, math.radians(20.0))
                self.keep.append((px, py, rx + 2))
                return

    # ---------- the ground ----------
    def ground(self):
        """The mown grass: a grid over the track's bounds and GROUND_MARGIN, each point at the height of the nearest
        bit of track (6 cm under the road), easing away from it into gentle rolls, down to the country at its edges
        and dug out under the pond. Mown in stripes STRIPE wide (each stripe its own vertices: sharp edges), its
        green changing slowly across the field."""
        t = self.t
        x0, y0, x1, y1 = t.bounds()
        m = GROUND_MARGIN
        per = int(round(STRIPE / CELL))
        cols = int(math.ceil((x1 - x0 + 2 * m) / CELL / per)) * per + 1  # (whole stripes)
        rows = int(math.ceil((y1 - y0 + 2 * m) / CELL)) + 1
        xs = [x0 - m + i * CELL for i in range(cols)]
        ys = [y0 - m + j * CELL for j in range(rows)]
        reach = t.half + 34.0
        d2 = [[reach * reach] * cols for _ in range(rows)]
        zn = [[0.0] * cols for _ in range(rows)]
        for p in t.pts:  # (each centre-line point marks the grid round it: quicker than every point searching)
            i0, i1 = max(0, int((p[0] - reach - xs[0]) / CELL)), min(cols - 1, int((p[0] + reach - xs[0]) / CELL) + 1)
            j0, j1 = max(0, int((p[1] - reach - ys[0]) / CELL)), min(rows - 1, int((p[1] + reach - ys[0]) / CELL) + 1)
            for j in range(j0, j1 + 1):
                dy2 = (ys[j] - p[1]) ** 2
                rd, rz = d2[j], zn[j]
                for i in range(i0, i1 + 1):
                    d = (xs[i] - p[0]) ** 2 + dy2
                    if d < rd[i]:
                        rd[i] = d
                        rz[i] = p[2]
        base = min(p[2] for p in t.pts) - 0.8
        z = []
        for j in range(rows):
            row = []
            for i in range(cols):
                ease = smooth((math.sqrt(d2[j][i]) - t.half - 2.0) / 30.0)
                bumps = 0.8 * math.sin(xs[i] * 0.07 + 1.0) * math.cos(ys[j] * 0.05) * ease
                row.append((zn[j][i] - 0.06) * (1 - ease) + base * ease + bumps)
            z.append(row)
        self.floor = min(min(r) for r in z) - 0.35  # (the country's flat: under the grass everywhere)
        edge = self.floor + 0.15
        for j in range(rows):
            for i in range(cols):
                e = smooth(min(i, cols - 1 - i, j, rows - 1 - j) * CELL / 15.0)
                z[j][i] = edge + (z[j][i] - edge) * e
        if self.pond:  # the pond: water a little under its shore, the ground dug out under it and sloping up to it
            px, py, rx, ry, h = self.pond
            near = [(j, i) for j in range(rows) for i in range(cols)
                    if abs(xs[i] - px) < rx * 1.7 and abs(ys[j] - py) < rx * 1.7]
            q = {(j, i): self.pond_q(xs[i], ys[j]) for j, i in near}
            self.water = min(z[j][i] for j, i in near if q[(j, i)] < 1.5) - 0.12
            for (j, i), k in q.items():
                if k < 1.0:
                    z[j][i] = self.water - 0.06 - 0.55 * (1 - k * k)
                elif k < 1.5:
                    z[j][i] = self.water - 0.06 + (z[j][i] - self.water + 0.06) * smooth((k - 1.0) / 0.5)
        self.xs, self.ys, self.z = xs, ys, z
        self.centre = ((x0 + x1) / 2, (y0 + y1) / 2)  # (the country round it: the lower tiers' Land's middle and reach)
        self.reach = math.hypot(x1 - x0, y1 - y0) / 2 + m
        part = self.near.get("turf")
        normal, colour = {}, {}
        for j in range(rows):
            for i in range(cols):
                gx = (z[j][min(cols - 1, i + 1)] - z[j][max(0, i - 1)]) / (2 * CELL)
                gy = (z[min(rows - 1, j + 1)][i] - z[max(0, j - 1)][i]) / (2 * CELL)
                normal[(j, i)] = norm((-gx, -gy, 1.0))
                x, y = xs[i], ys[j]
                k = 0.9 + 0.14 * fbm(x / 26.0, y / 26.0, 5)
                hue = fbm(x / 45.0 + 3.0, y / 45.0, 9) - 0.5
                c = (k * (0.94 + 0.2 * hue), k, k * (0.9 - 0.16 * hue))
                if self.pond and self.pond_q(x, y) < 1.15:
                    c = mix(c, (0.5, 0.45, 0.3), 0.6)  # (mud at the water's edge)
                colour[(j, i)] = c
        for k in range(0, cols - 1, per):  # a stripe: its own vertices
            tone = 1.0 if (k // per) % 2 == 0 else 0.8
            band = range(k, k + per + 1)
            sheet(part, [[(xs[i], ys[j], z[j][i]) for i in band] for j in range(rows)],
                  [[normal[(j, i)] for i in band] for j in range(rows)],
                  [[(xs[i] / 2.0, ys[j] / 2.0) for i in band] for j in range(rows)],
                  [[shade(colour[(j, i)], tone) for i in band] for j in range(rows)])
        if self.pond:
            px, py, rx, ry, h = self.pond
            water = self.near.get("water")
            uv = lambda x, y: (x / WATER_METRES, y / WATER_METRES)  # noqa: E731  (the ripples to scale: CHANGE 151)
            mid = water.vertex((px, py, self.water), (0, 0, 1), uv(px, py))
            rim = []
            for k in range(40):
                a = 2 * math.pi * k / 40
                d = (math.cos(a) * math.cos(h) * rx - math.sin(a) * math.sin(h) * ry,
                     math.cos(a) * math.sin(h) * rx + math.sin(a) * math.cos(h) * ry)
                lo, hi = 0.5, 2.0  # (out to where pond_q is 1.12: the water meets the bank)
                for _ in range(20):
                    f = (lo + hi) / 2
                    if self.pond_q(px + d[0] * f, py + d[1] * f) < 1.12:
                        lo = f
                    else:
                        hi = f
                rim.append(water.vertex((px + d[0] * lo, py + d[1] * lo, self.water), (0, 0, 1), uv(px + d[0] * lo, py + d[1] * lo)))
            for k in range(40):
                water.tri(mid, rim[k], rim[(k + 1) % 40])

    # ---------- the road ----------
    def racing_line(self, s):
        """Where the karts' tyres have rubbered the road: the middle on a straight, the inside of a bend."""
        return clamp(self.t.curvature(s - 10.0, 20.0) / 26.0, -1.0, 1.0) * (self.half - 1.7)

    def asphalt_colour(self, s, lat, line):
        """The road's own shading (the texture's times this): broad patches of older and newer asphalt, the racing
        line darker with rubber, the edges paler where no tyres go."""
        k = 0.84 + 0.18 * fbm(s / 11.0, lat / 6.0, 3) - 0.06 * noise(s / 2.3, lat / 1.9, 4)
        g = lambda d, w: math.exp(-d * d / (2 * w * w))  # noqa: E731
        k *= 1 - 0.26 * (g(lat - line - 0.6, 0.38) + g(lat - line + 0.6, 0.38)) - 0.12 * g(lat - line, 1.4)
        k *= 1 + 0.1 * smooth((abs(lat) - (self.half - 1.2)) / 0.7)
        k = min(1.0, k)
        return (k, k, k)

    def road(self):
        """The road: rows across it at every centre-line point, a column every half metre, its edges bevelled down
        into the grass; then repairs (patches of newer asphalt) and sealed cracks."""
        t, H = self.t, self.half
        part = self.near.get("asphalt")
        K = 20
        lats = [H + 0.45] + [H + 0.3 - (2 * H + 0.6) * k / K for k in range(K + 1)] + [-H - 0.45]
        drops = [-0.07] + [0.0] * (K + 1) + [-0.07]
        rows, normals, uvs, colours = [], [], [], []
        for s in self.st:
            g = (t.height(s + 1.0) - t.height(s - 1.0)) / 2.0
            tx, ty = t.tan[t.segment_at(s)]
            n = norm((-tx * g, -ty * g, 1.0))
            line = self.racing_line(s)
            rows.append([add(t.point(s, lat), (0, 0, dz)) for lat, dz in zip(lats, drops)])
            normals.append([n] * len(lats))
            uvs.append([(s / 4.0, lat / 4.0) for lat in lats])
            colours.append([self.asphalt_colour(s, lat, line) for lat in lats])
        sheet(part, rows, normals, uvs, colours)
        rnd = random.Random(31)
        avoid = [ps for ps, _ in t.boosts] + [os_ for os_, _ in t.oil] + [0.0, self.L]
        patch, made, tries = self.near.get("patch"), 0, 0
        while made < 7 and tries < 80:
            tries += 1
            s0, length = rnd.uniform(12.0, self.L - 20.0), rnd.uniform(2.5, 6.5)
            w = rnd.uniform(1.6, 3.6)
            l0 = rnd.uniform(-H + 0.7, H - 0.7 - w)
            if any(abs(s0 + length / 2 - a) < length / 2 + 5.0 for a in avoid):
                continue
            made += 1
            ss = [s0] + [s for s in self.st if s0 < s < s0 + length] + [s0 + length]
            sheet(patch, [[add(t.point(s, l0), (0, 0, 0.004)), add(t.point(s, l0 + w), (0, 0, 0.004))] for s in ss],
                  [[(0, 0, 1)] * 2 for _ in ss], [[(s / 4 + 0.37, l0 / 4 + 0.21), (s / 4 + 0.37, (l0 + w) / 4 + 0.21)] for s in ss])
        tar = self.near.get("tar")
        for k in range(10):  # sealed cracks: thin black wandering lines
            s, lat, a = rnd.uniform(5.0, self.L - 5.0), rnd.uniform(-H + 0.6, H - 0.6), rnd.uniform(0, math.pi)
            pts = []
            for _ in range(12):
                pts.append(add(t.point(s, lat), (0, 0, 0.005)))
                a += rnd.uniform(-0.7, 0.7)
                s, lat = s + math.cos(a) * 0.45, clamp(lat + math.sin(a) * 0.45, -H + 0.3, H - 0.3)
            rows = []
            for i, p in enumerate(pts):
                d = norm(sub(pts[min(len(pts) - 1, i + 1)], pts[max(0, i - 1)]))
                side = (-d[1] * 0.025, d[0] * 0.025, 0.0)
                rows.append([sub(p, side), add(p, side)])
            sheet(tar, rows, [[(0, 0, 1)] * 2 for _ in rows], [[(0, 0), (0, 0)] for _ in rows])
        # rubber laid down into each sharp bend: pairs of dark tyre marks along the racing line to the apex
        rubber, apexes = self.near.get("rubber"), []
        for i, c in enumerate(self.curv[:-1]):
            if abs(c) >= 22 and abs(c) >= max(abs(v) for v in self.curv[max(0, i - 8):i + 9]):
                if not apexes or self.st[i] - apexes[-1] > 30.0:
                    apexes.append(self.st[i])
        for a in apexes:
            for k in range(rnd.randint(2, 4)):
                s0, length, off = a - rnd.uniform(6.0, 16.0), rnd.uniform(9.0, 22.0), rnd.uniform(-0.6, 0.6)
                wave, phase = rnd.uniform(0.05, 0.2), rnd.uniform(0, 6.3)
                for wheel in (-0.6, 0.6):
                    rows, uvs = [], []
                    steps = max(2, int(length / 0.8))
                    for j in range(steps + 1):
                        s = s0 + length * j / steps
                        lat = clamp(self.racing_line(s) + off + wheel + wave * math.sin(s * 0.4 + phase), -H + 0.3, H - 0.3)
                        w = 0.07 * smooth(min(j, steps - j) / 3.0)
                        rows.append([add(t.point(s, lat - w), (0, 0, 0.0045)), add(t.point(s, lat + w), (0, 0, 0.0045))])
                        uvs.append([(s / 4.0, (lat - w) / 4.0), (s / 4.0, (lat + w) / 4.0)])
                    sheet(rubber, rows, [[(0, 0, 1)] * 2 for _ in rows], uvs)

    def paint(self):
        """White lines along both edges, the chequered start line and the grid's boxes."""
        t, H = self.t, self.half
        part = self.near.get("line_paint")
        white, black = (0.95, 0.95, 0.92), (0.06, 0.06, 0.06)
        for side in (1, -1):
            lats = (side * (H - 0.62), side * (H - 0.5))
            sheet(part, [[add(t.point(s, lat), (0, 0, 0.006)) for lat in lats] for s in self.st],
                  [[(0, 0, 1)] * 2 for _ in self.st], [[(s / 2.0, 0.55), (s / 2.0, 0.6)] for s in self.st],
                  [[shade(white, 0.9 + 0.1 * noise(s / 3.0, side, 6))] * 2 for s in self.st])

        def mark(s0, s1, l0, l1, colour, lift=0.007):
            pts = [add(t.point(s, lat), (0, 0, lift)) for s, lat in ((s0, l0), (s1, l0), (s1, l1), (s0, l1))]
            part.quad(pts, (0, 0, 1), [(s0 / 2, 0.6), (s1 / 2, 0.6), (s1 / 2, 0.7), (s0 / 2, 0.7)], colour)
        sq = 0.5
        for i in range(int(round(2 * H / sq))):
            for j in range(3):
                mark(-0.75 + j * sq, -0.75 + (j + 1) * sq, -H + i * sq, -H + (i + 1) * sq, white if (i + j) % 2 == 0 else black)
        for place in range(8):  # the grid: a bar in front of each kart's place and a line down each side
            s, lat = t.grid(place)
            mark(s + 1.05, s + 1.17, lat - 0.8, lat + 0.8, white)
            for k in (-1, 1):
                mark(s - 0.4, s + 1.05, lat + k * 0.8 - 0.05, lat + k * 0.8 + 0.05, white)

    # ---------- beside the road ----------
    def edge(self, side):
        """One side of the road: kerbs round the bends (inside and out), gravel on the outside of the sharp ones,
        and the barrier: armco on posts, tyre walls behind the gravel, a wall in front of the buildings."""
        t, H, n = self.t, self.half, len(self.st)
        bend = [side * c for c in self.curv]  # (positive: bending towards this side, the inside of the bend)
        self.kerbs(side, runs([b >= 12 or b <= -16 for b in bend], self.st, 10.0, 8.0))
        walls = self.walls[side]
        in_wall = [any(a <= s <= b or a <= s - self.L <= b for a, b in walls) for s in self.st]
        # (CHANGE 179) the pit lane's stretch: its own walls (pit_lane), no barrier and no gravel here
        in_lane = [t.lane is not None and side == t.lane[2] and t.lane_zone(s) is not None for s in self.st]
        # (CHANGE 177) the gravel traps are the track's own (kart_track.Track.gravel_widths: the karts are held at the
        # barrier where this draws it), none in front of a building or along the pit lane
        W = [0.0 if in_wall[i] or in_lane[i] else t.gravel[side][i % t.n] for i in range(n)]
        self.verge[side] = (W, in_wall)
        in_wall = [in_wall[i] or in_lane[i] for i in range(n)]
        self.gravel(side, W)
        near = []  # (the inside of a hairpin: the barrier's line would come too near the road coming back round)
        for i, s in enumerate(self.st):
            near.append(any(self.dist(x, y, H + BARRIER + 1) < H + BARRIER - 0.05 for x, y, _ in
                            (t.point(s, side * (H + d)) for d in (BARRIER, BARRIER + 0.4))))
        cramped = [any(near[max(0, i - 1):i + 2]) for i in range(n)]
        kinds = ["none" if in_lane[i] else "wall" if in_wall[i] else "none" if cramped[i] else "tyres" if W[i] >= 0.6
                 else "armco" for i in range(n)]
        i, which = 0, 0
        while i < n:
            j = i
            while j + 1 < n and kinds[j + 1] == kinds[i]:
                j += 1
            if kinds[i] == "armco":
                self.armco(side, i, min(n - 1, j + 1), W)
            elif kinds[i] == "tyres":
                self.tyre_wall(side, i, j, W, which)
                which += 1
            elif kinds[i] == "wall":
                self.wall(side, i, min(n - 1, j + 1))
            i = j + 1

    def kerbs(self, side, stretches):
        """Kerbs in metre blocks of red and white (each a little worn), a flat painted strip rising to a rounded
        lip on the outside; each stretch's ends sloped down to the road."""
        t, H = self.t, self.half
        part = self.near.get("kerb")
        for i0, i1 in stretches:
            s0, s1 = self.st[i0], self.st[i1]
            blocks = max(1, round(s1 - s0))
            bl = (s1 - s0) / blocks
            for b in range(blocks):
                x, y, _ = t.point(s0 + bl * (b + 0.5), side * (H + 0.56))
                if self.dist(x, y, H + 1.6) < H + 0.5:
                    continue  # (the tip of a hairpin's inside: the road coming back round is here)
                part.colour = shade((0.82, 0.1, 0.07) if b % 2 else (0.95, 0.95, 0.92), 0.88 + 0.12 * hash01(b, i0, side + 5))
                rows, normals, uvs = [], [], []
                for k in range(2):
                    s = s0 + bl * (b + k)
                    taper = smooth(min(s - s0, s1 - s) / 1.5)
                    prof = [(d, 0.008 + (dz - 0.008) * taper if dz > 0.008 else dz) for d, dz in KERB]
                    out, zc = self.out_of(s, side), t.height(s)
                    rows.append([(*t.point(s, side * (H + d))[:2], zc + dz) for d, dz in prof])
                    nrow = []
                    for m in range(len(prof)):
                        a, c = prof[max(0, m - 1)], prof[min(len(prof) - 1, m + 1)]
                        nrow.append(norm(sub((0, 0, 1), mul(out, (c[1] - a[1]) / (c[0] - a[0])))))
                    normals.append(nrow)
                    uvs.append([(s / 2.0, (d + 0.5) / 1.06) for d, _ in prof])
                part.grid(rows, normals, uvs)

    def gravel(self, side, W):
        """Gravel traps: from the kerb out under the tyre wall, tapering to nothing at each end."""
        t, H, n = self.t, self.half, len(self.st)
        part = self.near.get("gravel")
        i = 0
        while i < n:
            if W[i] <= 0:
                i += 1
                continue
            j = i
            while j + 1 < n and W[j + 1] > 0:
                j += 1
            rows, normals, uvs, colours = [], [], [], []
            for k in range(max(0, i - 1), min(n - 1, j + 1) + 1):
                s, w = self.st[k], W[k]
                reach = 0.42 + (w + BARRIER + 0.7 - 0.42) * smooth(w / 0.8)
                row, crow = [], []
                for m in range(5):
                    x, y, _ = t.point(s, side * (H + 0.42 + (reach - 0.42) * m / 4))
                    row.append((x, y, self.ground_z(x, y) + 0.035))
                    c = shade((1.0, 0.98, 0.95), 0.86 + 0.14 * noise(x / 3.1, y / 3.1, 21))
                    crow.append(mix(c, (0.75, 0.86, 0.62), 0.45) if m == 4 else c)  # (grass growing in at the back)
                rows.append(row)
                normals.append([(0, 0, 1)] * 5)
                uvs.append([(p[0] / 1.5, p[1] / 1.5) for p in row])
                colours.append(crow)
            sheet(part, rows, normals, uvs, colours)
            i = j + 1

    def armco(self, side, i0, i1, W):
        """Armco: a double-humped steel rail (front and back) on posts every 2 m."""
        t, H = self.t, self.half
        rail = self.near.get("armco")
        front, back, nf, nb, uvs = [], [], [], [], []
        for k in range(i0, i1 + 1):
            s = self.st[k]
            out = self.out_of(s, side)
            x, y, _ = t.point(s, side * (H + BARRIER + W[k]))
            zg = self.ground_z(x, y)
            fr, br, fn, bn = [], [], [], []
            for m, (e, h) in enumerate(ARMCO):
                a, c = ARMCO[max(0, m - 1)], ARMCO[min(len(ARMCO) - 1, m + 1)]
                ne, nh = -(c[1] - a[1]), c[0] - a[0]
                if ne > 0:
                    ne, nh = -ne, -nh  # (the face's normal towards the road)
                ln = math.hypot(ne, nh)
                ne, nh = ne / ln, nh / ln
                p = (x + out[0] * e, y + out[1] * e, zg + h)
                fr.append(p)
                br.append(add(p, mul(out, 0.006)))
                fn.append(norm((out[0] * ne, out[1] * ne, nh)))
                bn.append(norm((-out[0] * ne, -out[1] * ne, -nh)))
            front.append(fr)
            back.append(br)
            nf.append(fn)
            nb.append(bn)
            uvs.append([(s / 2.0, h / 2.0) for e, h in ARMCO])
        sheet(rail, front, nf, uvs)
        sheet(rail, back, nb, uvs)
        s = self.st[i0] + 1.0
        while s < self.st[i1] - 0.5:
            k = min(i1, max(i0, t.segment_at(s)))
            out = self.out_of(s, side)
            x, y, _ = t.point(s, side * (H + BARRIER + W[k] + 0.15))
            self.put("post", x, y, self.ground_z(x, y), math.degrees(math.atan2(out[1], out[0])))
            s += 2.0

    def tyre_wall(self, side, i0, i1, W, which):
        """A tyre wall: stacks of three tyres every 62 cm along the back of the gravel, painted in bands."""
        t, H = self.t, self.half
        bands = TYRE_BANDS[int(hash01(which, side + 3, int(self.L)) * len(TYRE_BANDS))]
        pts = [t.point(self.st[k], side * (H + BARRIER + W[k] + 0.31)) for k in range(i0, i1 + 1)]
        gap, count = 0.31, 0
        for a, b in zip(pts, pts[1:]):
            seg = math.dist(a[:2], b[:2])
            while gap <= seg:
                f = gap / seg
                x, y = lerp(a[0], b[0], f), lerp(a[1], b[1], f)
                self.put("tyres", x, y, self.ground_z(x, y) - 0.02, hash01(count, which, 7) * 360.0, 1.0,
                         bands[(count // 3) % 2])
                count += 1
                gap += 0.62
            gap -= seg

    def wall(self, side, i0, i1):
        """A concrete wall in front of the buildings: white, a red band along the top, a debris fence above it."""
        self.wall_along(side, [self.st[k] for k in range(i0, i1 + 1)], lambda s: self.half + BARRIER)

    def wall_along(self, side, ss, lateral, fence=True, height=1.0):
        """(CHANGE 179) The concrete wall along these s values at lateral(s) out from the middle (a positive lateral:
        the wall's face), with or without the debris fence: the barrier walls, and the pit lane's."""
        t = self.t
        concrete, steel = self.near.get("concrete"), self.near.get("steel")
        white, red = (0.92, 0.92, 0.9), (0.78, 0.1, 0.08)
        faces = [((0.0, -0.3), (0.0, height - 0.18), white, -1), ((0.0, height - 0.18), (0.0, height), red, -1),
                 ((0.0, height), (0.3, height), red, 0), ((0.3, height), (0.3, -0.3), white, 1)]
        for (e0, h0), (e1, h1), colour, facing in faces:
            rows, normals, uvs = [], [], []
            for s in ss:
                out = self.out_of(s, side)
                x, y, z = t.point(s, side * lateral(s))
                rows.append([(x + out[0] * e, y + out[1] * e, z + h) for e, h in ((e0, h0), (e1, h1))])
                n = (0.0, 0.0, 1.0) if facing == 0 else mul(out, facing)
                normals.append([n, n])
                uvs.append([(s / 2.0, h0 / 2.0 + e0), (s / 2.0, h1 / 2.0 + e1)])
            sheet(concrete, rows, normals, uvs, [[colour, colour] for _ in rows])
        if not fence:
            return
        line = []
        for s in ss:
            out = self.out_of(s, side)
            x, y, z = t.point(s, side * lateral(s))
            line.append((x + out[0] * 0.22, y + out[1] * 0.22, z))
        for h in (1.35, 1.7, 2.05, 2.3):
            kart_models.tube(steel, [add(p, (0, 0, h)) for p in line], 0.008, seg=4, steps=1, caps=False)
        acc = 0.0
        for a, b in zip(line, line[1:]):
            seg = math.dist(a, b)
            while acc <= seg:
                p = add(a, mul(sub(b, a), acc / seg))
                self.put("pole", p[0], p[1], p[2] + 0.95, 0.0)
                acc += 3.0
            acc -= seg

    def lane_ss(self, a, b, step=1.5):
        """s values from a to b (a may be before the start line: negative), about step apart, the ends exact."""
        n = max(1, int(math.ceil((b - a) / step)))
        return [a + (b - a) * k / n for k in range(n + 1)]

    def pit_lane(self):
        """(CHANGE 179) The pit lane beside the start straight (kart_track's "pit_lane"): its asphalt from the pit
        wall's back to the outer wall (and from the road's edge over the entry and the exit, where the outer wall
        slants out from the barrier line and back), the pit wall, the outer wall (the garages' front where the pit
        building stands), each kart's bay outlined in white. The teacher opens and closes it: the gates across the
        entry and the exit are the window's and the page's own (kart_gfx.TrackVisual.set_pits), as are the bays'
        name boards."""
        t, H, lane = self.t, self.half, self.t.lane
        if not lane:
            return
        s_in, s_out, side = lane
        asphalt, paint = self.near.get("asphalt"), self.near.get("line_paint")
        ramp = kart_track.LANE_RAMP
        for a, b, inner in ((s_in, s_in + ramp, H + 0.3), (s_in + ramp, s_out - ramp, t.lane_inner()),
                            (s_out - ramp, s_out, H + 0.3)):
            ss = self.lane_ss(a, b)
            rows = [[add(t.point(s, side * inner), (0, 0, 0.012)), add(t.point(s, side * t.lane_edge(s)), (0, 0, 0.012))]
                    for s in ss]
            sheet(asphalt, rows, [[(0, 0, 1)] * 2 for _ in ss],
                  [[(s / 4.0, inner / 4.0), (s / 4.0, t.lane_edge(s) / 4.0)] for s in ss],
                  [[shade((0.86, 0.86, 0.88), 0.9 + 0.1 * noise(s / 5.0, side, 44))] * 2 for s in ss])
        self.wall_along(side, self.lane_ss(s_in + ramp, s_out - ramp), lambda s: H + BARRIER, fence=False, height=0.9)
        # the outer wall: slanting in over the entry and the exit, straight between, except behind the pit building
        # (its front is the wall there)
        gaps = []
        if self.pits and self.pits[0] == side:
            _, s_mid, length = self.pits[:3]
            gaps.append((s_mid - length / 2, s_mid + length / 2))
        s = s_in
        runs_ = []
        for g0, g1 in sorted(gaps):
            if g0 > s:
                runs_.append((s, g0))
            s = max(s, g1)
        if s < s_out:
            runs_.append((s, s_out))
        for a, b in runs_:
            self.wall_along(side, self.lane_ss(a, b), lambda s: t.lane_edge(s), fence=False, height=1.2)
        white = (0.95, 0.95, 0.92)
        for corners in t.lane_marks():
            pts = [add(t.point(ps, lat), (0, 0, 0.02)) for ps, lat in corners]
            paint.quad(pts, (0, 0, 1), [(0, 0.6), (1, 0.6), (1, 0.7), (0, 0.7)], white)

    # ---------- the buildings ----------
    def sign(self, part, left, right, bottom, top, n, row):
        """A board of the signs texture: one row of it, read from the front (left and right as a viewer there sees
        them: points on its bottom edge's line, bottom and top heights over them)."""
        v0, v1 = sign_v(row)
        part.quad([add(left, (0, 0, bottom)), add(right, (0, 0, bottom)), add(right, (0, 0, top)), add(left, (0, 0, top))],
                  n, [(0, v0), (1, v0), (1, v1), (0, v1)])

    def grandstand(self):
        """The grandstand: seven rows of seats rising from a front wall, people in most of them, aisles of steps,
        a roof on masts with tie rods and the boards along its front, flags at its ends."""
        if not self.stand:
            return
        side, s_mid, length, o, axes = self.stand
        a, out, up = axes
        back = mul(out, -1)  # (towards the road)
        x0, x1 = -length / 2, length / 2
        zb = min(self.ground_z(*at(o, axes, x, y, 0.0)[:2]) for x in (x0, 0.0, x1) for y in (0.0, STAND_DEPTH)) - 0.1
        o = (o[0], o[1], zb)
        P = lambda x, y, z: at(o, axes, x, y, z)  # noqa: E731
        concrete, paint, steel, signs = (self.near.get(m) for m in ("concrete", "paint", "steel", "signs"))
        rows, rise, run, h0 = 7, 0.42, 0.85, 1.4
        Y = [0.0] + [0.6 + r * run for r in range(1, rows + 1)]  # (each row's front; the first starts at the front wall)
        Z = [h0 + r * rise for r in range(rows)]
        concrete.colour = (0.8, 0.79, 0.77)
        concrete.face([P(x0, 0, -0.5), P(x1, 0, -0.5), P(x1, 0, h0), P(x0, 0, h0)], back, 2.0)
        for r in range(rows):
            concrete.face([P(x0, Y[r], Z[r]), P(x1, Y[r], Z[r]), P(x1, Y[r + 1], Z[r]), P(x0, Y[r + 1], Z[r])], up, 2.0)
            if r + 1 < rows:
                concrete.face([P(x0, Y[r + 1], Z[r]), P(x1, Y[r + 1], Z[r]), P(x1, Y[r + 1], Z[r + 1]), P(x0, Y[r + 1], Z[r + 1])],
                              back, 2.0)
            for x, n in ((x0, mul(a, -1)), (x1, a)):
                concrete.face([P(x, Y[r], -0.5), P(x, Y[r + 1], -0.5), P(x, Y[r + 1], Z[r]), P(x, Y[r], Z[r])], n, 2.0)
        yb, ztop = Y[-1], Z[-1] + 1.0
        concrete.face([P(x0, yb, -0.5), P(x1, yb, -0.5), P(x1, yb, ztop), P(x0, yb, ztop)], out, 2.0)
        box(concrete, o, axes, x0, x1, yb - 0.2, yb, Z[-1], ztop, metres=2.0, skip=("-z", "+y"))
        aisles = [x0 + 0.8 + k * 8.0 for k in range(int((length - 1.6) / 8.0) + 1)] + [x1 - 0.8]
        rnd = random.Random(int(s_mid * 10) + 7)
        heading = math.degrees(math.atan2(back[1], back[0]))
        for r in range(rows):
            mid_y = (Y[r] + Y[r + 1]) / 2
            for xa in aisles:  # steps up the aisles: half a row high
                box(concrete, o, axes, xa - 0.6, xa + 0.6, mid_y, Y[r + 1], Z[r], Z[r] + rise / 2, metres=2.0, skip=("-z",))
            x = x0 + 0.5
            while x < x1 - 0.45:
                if min(abs(x - xa) for xa in aisles) > 0.85:
                    pick = rnd.random()
                    colour = (0.95, 0.95, 0.95) if pick < 0.08 else (0.95, 0.78, 0.1) if pick < 0.13 else (0.1, 0.32, 0.78)
                    yf = Y[r] + (0.75 if r == 0 else 0.15)
                    self.put("seat", *P(x, yf + 0.18, Z[r]), heading, 1.0, colour)
                    if rnd.random() < 0.74:
                        who = rnd.random()
                        shape = "fan_a" if who < 0.3 else "fan_b" if who < 0.5 else "fan_c" if who < 0.75 else "fan_d"
                        self.put(shape, *P(x, yf + 0.18, Z[r] + 0.44), heading + rnd.uniform(-12, 12), rnd.uniform(0.92, 1.06),
                                 SHIRTS[int(rnd.random() * len(SHIRTS))])
                x += 0.5
        # the roof: masts behind the top row, the roof sloping down to the back, tie rods from the masts to its front
        zf = Z[-1] + 3.6
        zr, yf, yr = zf - 0.45, -0.7, yb + 0.7
        masts = max(2, round(length / 7.5) + 1)
        for k in range(masts):
            x = x0 + 0.3 + (length - 0.6) * k / (masts - 1)
            column(steel, P(x, yb + 0.25, -0.5), 0.13, 0.11, zf + 2.4, seg=8)
            rod(steel, P(x, yb + 0.25, zf + 1.8), P(x, yf + 0.4, zf + 0.02), 0.03, seg=4)
        paint.colour = (0.4, 0.42, 0.46)
        paint.quad([P(x0, yf, zf), P(x1, yf, zf), P(x1, yr, zr), P(x0, yr, zr)], norm(add(up, mul(out, 0.08))))
        paint.colour = (0.9, 0.9, 0.88)
        paint.quad([P(x0, yf, zf - 0.22), P(x1, yf, zf - 0.22), P(x1, yr, zr - 0.22), P(x0, yr, zr - 0.22)], mul(up, -1))
        paint.quad([P(x0, yr, zr - 0.22), P(x1, yr, zr - 0.22), P(x1, yr, zr), P(x0, yr, zr)], out)
        for x, n in ((x0, mul(a, -1)), (x1, a)):
            paint.quad([P(x, yf, zf - 0.75), P(x, yr, zr - 0.22), P(x, yr, zr), P(x, yf, zf)], n)
        panels = max(1, round(length / 5.6))
        for k in range(panels):  # the boards along the roof's front (read from the road: left is where the viewer's is)
            xa, xb = x0 + length * k / panels, x0 + length * (k + 1) / panels
            left, right = (P(xa, yf, 0.0), P(xb, yf, 0.0)) if side > 0 else (P(xb, yf, 0.0), P(xa, yf, 0.0))
            self.sign(signs, left, right, zf - 0.75, zf, back, (0, 1, 0, 5, 0, 4)[k % 6])
        for k, x in enumerate((x0 - 2.0, x1 + 2.0)):
            p = P(x, yb - 1.0, 0.0)
            self.put("flagpole", p[0], p[1], self.ground_z(p[0], p[1]) - 0.1, 200.0, 1.0, ((0.1, 0.36, 0.86), (0.95, 0.8, 0.15))[k])

    def pit_building(self):
        """The pits: the pit lane behind its wall, a row of garages (some open, the doors in the teams' colours), the
        glazed floor above them with its boards, and the race control tower at the end nearer the start line."""
        if not self.pits:
            return
        t = self.t
        side, s_mid, length, o, axes = self.pits
        a, out, up = axes
        back = mul(out, -1)
        z0 = t.height(s_mid)
        o = (o[0], o[1], z0)
        P = lambda x, y, z: at(o, axes, x, y, z)  # noqa: E731
        concrete, paint, door, glass, steel, signs, lines = (self.near.get(m) for m in
                                                             ("concrete", "paint", "door", "glass", "steel", "signs", "line_paint"))
        x0, x1 = -length / 2, length / 2
        if not t.lane:  # (CHANGE 179: with a pit lane the asphalt is pit_lane's; this is the old apron behind a wall)
            # the pit lane: concrete from under the wall back to the garages, rising and falling with the road
            xs = [x0 - 2.0 + (length + 4.0) * k / max(1, round((length + 4.0) / 3.0)) for k in range(round((length + 4.0) / 3.0) + 1)]
            ys = (-0.35, 3.0, 6.6)
            rows = [[P(x, y, t.height(s_mid + x) - z0 + 0.01) for y in ys] for x in xs]
            sheet(concrete, rows, [[up] * 3 for _ in rows], [[(p[0] / 2, p[1] / 2) for p in row] for row in rows],
                  [[shade((0.86, 0.86, 0.84), 0.92 + 0.08 * noise(p[0] / 4, p[1] / 4, 33)) for p in row] for row in rows])
            rows = [[P(x, y, t.height(s_mid + x) - z0 + 0.016) for y in (0.8, 0.92)] for x in xs]
            sheet(lines, rows, [[up] * 2 for _ in rows], [[(x / 2, 0.6), (x / 2, 0.65)] for x in xs], [[(0.95, 0.95, 0.92)] * 2 for _ in rows])
        yg0, yg1, zg, zu = PIT_FRONT, PIT_DEPTH, 4.2, 7.4
        tower_x = (x0, x0 + 5.5) if s_mid > 0 else (x1 - 5.5, x1)  # (the tower at the end nearer the start line)
        gx0, gx1 = (tower_x[1], x1) if s_mid > 0 else (x0, tower_x[0])
        white, dark = (0.92, 0.92, 0.9), (0.07, 0.07, 0.08)
        teams = [(0.85, 0.15, 0.12), (0.1, 0.36, 0.86), (0.95, 0.8, 0.15), (0.15, 0.6, 0.25), (0.55, 0.2, 0.65), (0.82, 0.82, 0.84)]
        bays = max(1, int((gx1 - gx0) / 4.5))
        bay = (gx1 - gx0) / bays
        paint.colour = white
        for k in range(bays):
            bx0, bx1 = gx0 + k * bay, gx0 + (k + 1) * bay
            dx0, dx1 = bx0 + 0.45, bx1 - 0.45
            concrete.face([P(bx0, yg0, 0), P(dx0, yg0, 0), P(dx0, yg0, zg), P(bx0, yg0, zg)], back, 3.0, white)
            concrete.face([P(dx1, yg0, 0), P(bx1, yg0, 0), P(bx1, yg0, zg), P(dx1, yg0, zg)], back, 3.0, white)
            concrete.face([P(dx0, yg0, 3.2), P(dx1, yg0, 3.2), P(dx1, yg0, zg), P(dx0, yg0, zg)], back, 3.0, white)
            for x, n in ((dx0, a), (dx1, mul(a, -1))):  # (the opening's sides)
                paint.quad([P(x, yg0, 0), P(x, yg0 + 0.15, 0), P(x, yg0 + 0.15, 3.2), P(x, yg0, 3.2)], n)
            paint.quad([P(dx0, yg0, 3.2), P(dx1, yg0, 3.2), P(dx1, yg0 + 0.15, 3.2), P(dx0, yg0 + 0.15, 3.2)], mul(up, -1))
            if k % 4 == 1:  # an open garage: a dark room, the door rolled up at the top
                paint.colour = dark
                paint.quad([P(dx0, yg1 - 0.3, 0), P(dx1, yg1 - 0.3, 0), P(dx1, yg1 - 0.3, 3.2), P(dx0, yg1 - 0.3, 3.2)], back)
                for x, n in ((dx0, a), (dx1, mul(a, -1))):
                    paint.quad([P(x, yg0 + 0.15, 0), P(x, yg1 - 0.3, 0), P(x, yg1 - 0.3, 3.2), P(x, yg0 + 0.15, 3.2)], n)
                paint.quad([P(dx0, yg0 + 0.15, 3.2), P(dx1, yg0 + 0.15, 3.2), P(dx1, yg1 - 0.3, 3.2), P(dx0, yg1 - 0.3, 3.2)], mul(up, -1))
                concrete.colour = (0.42, 0.42, 0.42)
                concrete.face([P(dx0, yg0 + 0.15, 0.01), P(dx1, yg0 + 0.15, 0.01), P(dx1, yg1 - 0.3, 0.01), P(dx0, yg1 - 0.3, 0.01)], up, 2.0)
                paint.colour = white
                door.colour = teams[k % len(teams)]
                box(door, o, axes, dx0, dx1, yg0 + 0.15, yg0 + 0.45, 2.9, 3.2, skip=("+y",))
            else:
                door.colour = shade(teams[k % len(teams)], 0.9 + 0.1 * hash01(k, 3))
                rows = [[P(x, yg0 + 0.15, z) for x in (dx0, dx1)] for z in [3.2 * i / 16 for i in range(17)]]
                ribs = [[shade(door.colour, 0.9 if i % 2 else 1.0)] * 2 for i in range(17)]  # (the roller door's slats)
                sheet(door, rows, [[back] * 2 for _ in rows], [[(0, z), (dx1 - dx0, z)] for z in [3.2 * i / 16 for i in range(17)]], ribs)
        for x, n in ((gx0, mul(a, -1)), (gx1, a)):
            concrete.face([P(x, yg0, 0), P(x, yg1, 0), P(x, yg1, zu), P(x, yg0, zu)], n, 3.0, white)
        concrete.face([P(x0, yg1, -0.3), P(x1, yg1, -0.3), P(x1, yg1, zu), P(x0, yg1, zu)], out, 3.0, white)
        concrete.colour = (0.7, 0.7, 0.68)
        concrete.face([P(gx0, yg0, zg), P(gx1, yg0, zg), P(gx1, yg0 + 1.7, zg), P(gx0, yg0 + 1.7, zg)], up, 2.0)
        # the floor above: glass between a white sill and the boards, mullions, a railed terrace in front, a roof
        yu = yg0 + 1.7
        concrete.face([P(gx0, yu, zg), P(gx1, yu, zg), P(gx1, yu, zg + 0.25), P(gx0, yu, zg + 0.25)], back, 3.0, white)
        glass.quad([P(gx0, yu, zg + 0.25), P(gx1, yu, zg + 0.25), P(gx1, yu, zu - 0.45), P(gx0, yu, zu - 0.45)], back)
        panels = max(1, round((gx1 - gx0) / 3.6))
        for k in range(panels):
            xa, xb = gx0 + (gx1 - gx0) * k / panels, gx0 + (gx1 - gx0) * (k + 1) / panels
            left, right = (P(xa, yu - 0.01, 0.0), P(xb, yu - 0.01, 0.0)) if side > 0 else (P(xb, yu - 0.01, 0.0), P(xa, yu - 0.01, 0.0))
            self.sign(signs, left, right, zu - 0.45, zu, back, (1, 0, 6, 0, 2, 0, 3, 0, 4)[k % 9])
        x = gx0 + 1.5
        while x < gx1 - 0.5:
            box(steel, o, axes, x - 0.03, x + 0.03, yu - 0.06, yu, zg + 0.25, zu - 0.45, skip=("+y", "-z", "+z"))
            x += 1.5
        rail = [P(gx0 + 0.1, yg0 + 0.1, 0), P(gx1 - 0.1, yg0 + 0.1, 0)]
        for h in (zg + 0.55, zg + 1.05):
            rod(steel, add(rail[0], (0, 0, h)), add(rail[1], (0, 0, h)), 0.025, seg=5)
        x = gx0 + 0.1
        while x <= gx1 - 0.05:
            rod(steel, P(x, yg0 + 0.1, zg), P(x, yg0 + 0.1, zg + 1.05), 0.02, seg=4)
            x += 1.5
        paint.colour = (0.4, 0.42, 0.46)
        box(paint, o, axes, gx0 - 0.3, gx1 + 0.3, yu - 0.6, yg1 + 0.3, zu, zu + 0.25, skip=())
        # race control: a tower with a glass room on top
        tx0, tx1 = tower_x
        zt = 11.0
        paint.colour = white
        for (xa, ya), (xb, yb), n in (((tx0, yg0), (tx1, yg0), back), ((tx1, yg1), (tx0, yg1), out),
                                      ((tx0, yg1), (tx0, yg0), mul(a, -1)), ((tx1, yg0), (tx1, yg1), a)):
            concrete.face([P(xa, ya, -0.3), P(xb, yb, -0.3), P(xb, yb, 8.2), P(xa, ya, 8.2)], n, 3.0, white)
            glass.quad([P(xa, ya, 8.2), P(xb, yb, 8.2), P(xb, yb, 10.3), P(xa, ya, 10.3)], n)
            concrete.face([P(xa, ya, 10.3), P(xb, yb, 10.3), P(xb, yb, zt), P(xa, ya, zt)], n, 3.0, white)
        left, right = (P(tx0, yg0 - 0.01, 0), P(tx1, yg0 - 0.01, 0)) if side > 0 else (P(tx1, yg0 - 0.01, 0), P(tx0, yg0 - 0.01, 0))
        self.sign(signs, left, right, 10.3, zt, back, 0)
        for x, y in ((tx0, yg0), (tx1, yg0), (tx0, yg1), (tx1, yg1)):
            box(steel, o, axes, x - 0.06, x + 0.06, y - 0.06, y + 0.06, 8.2, 10.3, skip=("-z", "+z"))
        paint.colour = (0.4, 0.42, 0.46)
        box(paint, o, axes, tx0 - 0.5, tx1 + 0.5, yg0 - 0.5, yg1 + 0.5, zt, zt + 0.28)
        rod(steel, P((tx0 + tx1) / 2, (yg0 + yg1) / 2, zt + 0.28), P((tx0 + tx1) / 2, (yg0 + yg1) / 2, zt + 3.5), 0.04, seg=5)

    def gantry(self):
        """The start gantry: two lattice towers past the barriers, a truss across the road with START boards on both
        sides, and the start lights facing the grid: five pairs, each its own part ("lamp 1" to "lamp 5", from the
        left as the grid sees them), dark until the window or the page lights them (start_lights: CHANGE 151)."""
        t, H = self.t, self.half
        steel, paint, signs = (self.near.get(m) for m in ("steel", "paint", "signs"))
        a, b, u = frame(math.radians(t.heading(0.0)))
        z0 = t.height(0.0)
        for side in (1, -1):
            x, y, _ = t.point(0.0, side * (H + GANTRY_D))
            c = (x, y, self.ground_z(x, y))
            corners = [(-0.35, -0.35), (0.35, -0.35), (0.35, 0.35), (-0.35, 0.35)]
            top = z0 + 6.6 - c[2]
            for da, db in corners:
                box(steel, c, (a, b, u), da - 0.05, da + 0.05, db - 0.05, db + 0.05, -0.3, top, metres=2.0, skip=("-z",))
            levels = [0.4 + (top - 0.6) * k / 6 for k in range(7)]
            for k, h in enumerate(levels):
                for i in range(4):
                    (pa, pb), (qa, qb) = corners[i], corners[(i + 1) % 4]
                    rod(steel, at(c, (a, b, u), pa, pb, h), at(c, (a, b, u), qa, qb, h), 0.022, seg=4)
                    if k + 1 < len(levels):
                        rod(steel, at(c, (a, b, u), pa, pb, h), at(c, (a, b, u), qa, qb, levels[k + 1]), 0.018, seg=4)
        span = H + GANTRY_D
        o = t.point(0.0, 0.0)
        G = lambda lat, da, z: add(add(o, mul(b, lat)), add(mul(a, da), (0, 0, z)))  # noqa: E731
        for da in (-0.3, 0.3):
            for z in (5.6, 6.4):
                rod(steel, G(-span, da, z), G(span, da, z), 0.045, seg=6)
            n = int(2 * span)
            for k in range(n + 1):
                lat = -span + 2 * span * k / n
                rod(steel, G(lat, da, 5.6), G(lat, da, 6.4), 0.02, seg=4)
                if k < n:
                    rod(steel, G(lat, da, 5.6 if k % 2 else 6.4), G(lat + 2 * span / n, da, 6.4 if k % 2 else 5.6), 0.018, seg=4)
        for face, da in ((-1, -0.36), (1, 0.36)):  # START boards: facing the grid (-1) and the other way
            n = mul(a, face)
            for lo, hi in ((-H - 0.6, 0.0), (0.0, H + 0.6)):
                pl, pr = (G(hi, da, 0.0), G(lo, da, 0.0)) if face < 0 else (G(lo, da, 0.0), G(hi, da, 0.0))
                self.sign(signs, pl, pr, 5.65, 6.35, n, START_SIGN)
        paint.colour = (0.05, 0.05, 0.06)
        box(paint, o, (a, b, u), -0.2, 0.1, -1.3, 1.3, 4.85, 5.45)
        for lat in (-0.9, 0.9):
            rod(steel, G(lat, -0.05, 5.45), G(lat, -0.05, 5.62), 0.02, seg=4)
        for col in range(5):
            lamp = self.near.get("lamp", group=str(5 - col))  # (col 0 is on the right as the grid looks: lat -1.0)
            for z in (5.0, 5.3):
                c = G(-1.0 + 0.5 * col, -0.205, z)
                mid = lamp.vertex(c, mul(a, -1), (0.5, 0.5))
                rim = [lamp.vertex(add(c, add(mul(b, 0.09 * math.cos(2 * math.pi * k / 10)), (0, 0, 0.09 * math.sin(2 * math.pi * k / 10)))),
                                   mul(a, -1), (0, 0)) for k in range(10)]
                for k in range(10):
                    lamp.tri(mid, rim[k], rim[(k + 1) % 10])

    def bridge_site(self):
        """(CHANGE 151) Where the footbridge goes: the straightest stretch (scanned every 2 m, never near the start)
        where a stair tower fits past the barriers on both sides, each with its steps running along the road one way
        or the other, clear of what's built, the gravel, the walls and the road coming back round, and the whole of it
        CAMERA_CLEAR from every TV camera. (s, run, {side: the way its steps run along the road}) or None."""
        t, H = self.t, self.half
        run = (BRIDGE_CLEAR + 0.75) / BRIDGE_RISE * BRIDGE_TREAD  # (the steps' length, a little over: the ground falls)
        best = None
        for step in range(int(self.L / 2)):
            s = 30.0 + 2.0 * step
            if s > self.L - 30.0:
                break
            bend = max(abs(t.curvature(s + d - 9.0, 18.0)) for d in (-12.0, 0.0, 12.0))
            if bend > 14.0 or (best and bend >= best[0]):
                continue
            a, b, u = frame(math.radians(t.heading(s)))
            o = t.point(s, 0.0)
            span = [at(o, (a, b, u), along, lat, 0.0) for along in (-1.4, 1.4)
                    for lat in [(H + BRIDGE_OUT) * (j / 4.0 - 1.0) for j in range(9)]]
            if any(math.hypot(p[0] - cx, p[1] - cy) < CAMERA_CLEAR + 1.5 for p in span for cx, cy, *_ in self.cams):
                continue
            ways, extra = {}, {}
            for side in (1, -1):
                W, in_wall = self.verge[side]
                # (CHANGE 179) the tower stands past the gravel trap, if there is one, or past the pit lane's outer
                # wall: extra, how much further out than the road's edge the span reaches on this side
                lane_side = t.lane is not None and side == t.lane[2]
                for way in (side, -side):
                    lo, hi = (-2.0, run + 3.0) if way > 0 else (-run - 3.0, 2.0)
                    ds = range(int(lo), int(hi) + 1)
                    if any(in_wall[t.segment_at(s + d)] for d in ds):
                        continue
                    out = max(t.lane_edge(s + d) - H if lane_side and t.lane_zone(s + d) is not None
                              else W[t.segment_at(s + d)] for d in ds)
                    pts = [at(o, (a, b, u), along, side * (H + out + lat), 0.0) for lat in (BRIDGE_IN, BRIDGE_OUT)
                           for along in [x * 0.5 for x in range(-3, 4)] + [way * (1.3 + run * f) for f in (0.25, 0.5, 0.75, 1.0)]]
                    if all(self.dist(p[0], p[1], H + out + BRIDGE_IN + 2) >= H + out + BRIDGE_IN - 0.3 and self.free(p[0], p[1], 0.8)
                           for p in pts):
                        ways[side], extra[side] = way, out
                        break
            if len(ways) == 2:
                best = (bend, s, run, ways, extra)
        return best[1:] if best else None

    def bridge(self):
        """(CHANGE 151) A footbridge over the road (bridge_site): a covered walkway on two steel girders BRIDGE_CLEAR
        over the road, glazed, with the club's boards along both sides facing the karts coming each way; a stair tower
        past the barriers on each side, and from each a flight of steps down along the road, the two flights running
        opposite ways. Nothing of it is within the barrier's line under 4.5 m, nor near a TV camera (kart_test.py)."""
        site = self.bridge_site()
        self.footbridge = None
        if not site:
            return
        s, run, ways, extra = site
        t, H = self.t, self.half
        steel, concrete, paint, glass, signs = (self.near.get(m) for m in ("steel", "concrete", "paint", "glass", "signs"))
        a, b, u = frame(math.radians(t.heading(s)))
        axes = (a, b, u)
        o = t.point(s, 0.0)
        P = lambda along, lat, z: at(o, axes, along, lat, z)  # noqa: E731  (z from the road's middle)
        C, D = BRIDGE_CLEAR, 1.3  # (the underside, half the walkway's width along the road)
        # (CHANGE 179) the walkway's ends each side (past the gravel or the pit lane there: extra), as laterals
        E = {1: H + extra[1], -1: -(H + extra[-1])}  # (the road's edge, or the trap's or the lane's outer edge)
        Lp, Ln = E[1] + BRIDGE_OUT, E[-1] - BRIDGE_OUT
        deck = C + 0.45
        self.footbridge = (s, run, ways)
        white, grey = (0.93, 0.93, 0.91), (0.38, 0.4, 0.44)
        # the girders, the floor, the roof
        for y0, y1 in ((-D, -D + 0.28), (D - 0.28, D)):
            box(steel, o, axes, y0, y1, Ln, Lp, C, C + 0.3, metres=2.0)
        concrete.colour = (0.8, 0.8, 0.78)
        box(concrete, o, axes, -D, D, Ln, Lp, C + 0.3, deck, metres=3.0, skip=("-z",))
        paint.colour = grey
        box(paint, o, axes, -D - 0.15, D + 0.15, Ln - 0.15, Lp + 0.15, C + 2.45, C + 2.65)
        # each side: the club's board over the road (one row of the signs texture, read from the karts coming that way),
        # white panels past it, glazing above on mullions
        for face in (-1, 1):
            n = mul(a, face)
            x = face * (D + 0.004)
            left, right = (P(x, H + 0.8, 0.0), P(x, -H - 0.8, 0.0)) if face < 0 else (P(x, -H - 0.8, 0.0), P(x, H + 0.8, 0.0))
            self.sign(signs, left, right, deck, C + 1.5, n, 0 if face < 0 else 1)
            paint.colour = white
            for lo, hi in ((Ln, -H - 0.8), (H + 0.8, Lp)):
                paint.quad([P(x, lo, deck), P(x, hi, deck), P(x, hi, C + 1.5), P(x, lo, C + 1.5)], n)
            paint.quad([P(x * 0.99, Ln, deck), P(x * 0.99, Lp, deck), P(x * 0.99, Lp, C + 1.5), P(x * 0.99, Ln, C + 1.5)],
                       mul(n, -1))  # (its back, seen from the walkway)
            box(steel, o, axes, face * D - 0.05, face * D + 0.05, Ln, Lp, C + 1.5, C + 1.58)
            glass.quad([P(face * D, Ln, C + 1.58), P(face * D, Lp, C + 1.58), P(face * D, Lp, C + 2.45), P(face * D, Ln, C + 2.45)], n)
            lat = Ln
            while lat <= Lp + 0.01:
                box(steel, o, axes, face * D - 0.05, face * D + 0.05, lat - 0.04, lat + 0.04, C + 1.58, C + 2.45, skip=("-z", "+z"))
                lat += 1.5
        # the stair towers and the steps
        for side in (1, -1):
            l0, l1 = E[side] + side * BRIDGE_IN, E[side] + side * BRIDGE_OUT
            lo, hi = min(l0, l1), max(l0, l1)
            for along in (-D + 0.1, D - 0.1):
                for lat in (lo + 0.1, hi - 0.1):
                    foot = P(along, lat, 0.0)
                    zg = self.ground_z(foot[0], foot[1]) - o[2]
                    box(steel, o, axes, along - 0.08, along + 0.08, lat - 0.08, lat + 0.08, zg - 0.3, C + 0.3, metres=2.0, skip=("-z", "+z"))
            for k, h in enumerate((1.2, 2.4, 3.6)):  # (cross braces between the columns)
                for lat in (lo + 0.1, hi - 0.1):
                    rod(steel, P(-D + 0.1, lat, h), P(D - 0.1, lat, h + 1.1), 0.03, seg=4)
            # the steps: treads between two stringers, from the walkway's end down to the ground, along the road
            way = ways[side]
            w0, w1 = lo + 0.15, hi - 0.15
            top, k = deck, 0
            treads = []
            while k < 60:
                along0 = way * (D + BRIDGE_TREAD * k)
                along1 = way * (D + BRIDGE_TREAD * (k + 1))
                z = deck - BRIDGE_RISE * (k + 1)
                mid = P((along0 + along1) / 2, (w0 + w1) / 2, 0.0)
                if z <= self.ground_z(mid[0], mid[1]) - o[2] + 0.05:
                    break
                treads.append((along0, along1, z))
                k += 1
            concrete.colour = (0.72, 0.72, 0.7)
            for along0, along1, z in treads:
                x0, x1 = min(along0, along1), max(along0, along1)
                box(concrete, o, axes, x0, x1 + 0.02, w0, w1, z - 0.06, z, metres=1.0, skip=("-z",))
            if not treads:
                continue
            end = treads[-1]
            last = P(end[1], (w0 + w1) / 2, 0.0)
            zg = self.ground_z(last[0], last[1]) - o[2]
            for lat in (w0 - 0.04, w1 + 0.04):
                rod(steel, P(way * D, lat, deck - 0.12), P(end[1], lat, zg), 0.07, seg=6)  # (the stringer)
                rod(steel, P(way * D, lat, deck + 0.95), P(end[1], lat, zg + 0.95), 0.025, seg=5)  # (the handrail)
                for along0, along1, z in treads[::4]:
                    rod(steel, P(along0, lat, z), P(along0, lat, z + 0.95), 0.018, seg=4)
            # the landing's rail on the outside, and the tower's sides to the deck
            rod(steel, P(-D, l1, deck + 1.0), P(D, l1, deck + 1.0), 0.025, seg=5)
            for along in (-D + 0.1, D - 0.1):
                rod(steel, P(along, l1, deck), P(along, l1, deck + 1.0), 0.02, seg=4)
            # (claimed: no board, tree or post goes under the steps or by the tower)
            for f in [i / 6.0 for i in range(7)]:
                p = P(way * (D + (abs(end[1]) - D) * f), (w0 + w1) / 2, 0.0)
                self.keep.append((p[0], p[1], 1.6))
            p = P(0.0, (lo + hi) / 2, 0.0)
            self.keep.append((p[0], p[1], 2.2))

    # ---------- round the track ----------
    def boards(self):
        """Advertising boards behind the armco: pairs of 4 m boards on legs facing the road, every 26 m or so where
        there's room (not in front of the buildings, nor behind the gravel)."""
        t, H = self.t, self.half
        signs, paint, steel = self.near.get("signs"), self.near.get("paint"), self.near.get("steel")
        for side in (1, -1):
            W, in_wall = self.verge[side]
            s, k = 6.0 + (12.0 if side < 0 else 0.0), 0
            while s < self.L - 12.0:
                ends, ok = [], True
                for j in range(2):
                    sa, sb = s + j * 4.4, s + j * 4.4 + 4.0
                    ia, ib = t.segment_at(sa), t.segment_at(sb)
                    if any(in_wall[i] or W[i] > 0.0 for i in range(ia, min(len(W), ib + 2))):
                        ok = False
                        break
                    d = H + BARRIER + 0.9
                    pa, pb = t.point(sa, side * d), t.point(sb, side * d)
                    for p in (pa, pb):
                        if self.dist(p[0], p[1], d + 2) < d - 0.4 or not self.free(p[0], p[1], 0.6, cameras=False):
                            ok = False
                    ends.append((pa, pb))
                if not ok:
                    s += 5.0
                    continue
                for j, (pa, pb) in enumerate(ends):
                    pa = (pa[0], pa[1], self.ground_z(pa[0], pa[1]))
                    pb = (pb[0], pb[1], self.ground_z(pb[0], pb[1]))
                    n = norm(cross(sub(pb, pa), (0, 0, side)))  # (towards the road)
                    left, right = (pa, pb) if side > 0 else (pb, pa)
                    self.sign(signs, left, right, 0.3, 0.85, n, int(hash01(k, j, side + 9, int(self.L)) * 7))
                    off = mul(n, -0.03)
                    paint.colour = (0.3, 0.3, 0.32)
                    paint.quad([add(add(right, off), (0, 0, 0.3)), add(add(left, off), (0, 0, 0.3)),
                                add(add(left, off), (0, 0, 0.85)), add(add(right, off), (0, 0, 0.85))], mul(n, -1))
                    for p, q in ((pa, pb), (pb, pa)):
                        foot = add(add(p, mul(sub(q, p), 0.06)), mul(n, -0.08))
                        rod(steel, add(foot, (0, 0, -0.2)), add(foot, (0, 0, 0.85)), 0.03, seg=4)
                k += 1
                s += 26.0

    def marshals(self):
        """Marshals' posts on the outside of the bends, behind the barrier, every 80 m or so, each with a flag."""
        t, H = self.t, self.half
        s, k = 35.0, 0
        flags = [(0.1, 0.65, 0.2), (0.95, 0.85, 0.1), (0.15, 0.4, 0.9)]
        while s < self.L - 20.0:
            side = -1 if t.curvature(s - 9.0, 18.0) > 0 else 1
            W, in_wall = self.verge[side]
            i = t.segment_at(s)
            d = H + BARRIER + W[i] + (2.7 if W[i] >= 0.6 else 2.2)
            x, y, _ = t.point(s, side * d)
            if not in_wall[i] and self.dist(x, y, d + 2) >= d - 0.5 and self.free(x, y, 1.5):
                out = self.out_of(s, side)
                self.put("marshal_post", x, y, self.ground_z(x, y), math.degrees(math.atan2(-out[1], -out[0])), 1.0, flags[k % 3])
                self.keep.append((x, y, 1.4))
                k += 1
                s += 80.0
            else:
                s += 6.0

    def camera_towers(self):
        """A scaffold tower under each TV camera, its platform just behind and below the camera's eye (so the camera
        never sees it), with railings and a parasol."""
        t, H = self.t, self.half
        steel, paint = self.near.get("steel"), self.near.get("paint")
        for cx, cy, cz, side, s in self.cams:
            out = self.out_of(s, side)
            tx, ty = t.tan[t.segment_at(s)]
            axes = ((tx, ty, 0.0), out, (0.0, 0.0, 1.0))
            c = (cx + out[0] * 0.95, cy + out[1] * 0.95, 0.0)
            legs = [(da, do) for da in (-0.55, 0.55) for do in (-0.55, 0.55)]
            feet = [at(c, axes, da, do, 0.0) for da, do in legs]
            if any(self.dist(p[0], p[1], H + 8) < H + 6.0 or not self.free(p[0], p[1], 0.3, cameras=False) for p in feet):
                continue
            zg = min(self.ground_z(p[0], p[1]) for p in feet)
            c = (c[0], c[1], zg)
            deck = cz - 1.0 - zg
            for da, do in legs:
                box(steel, c, axes, da - 0.04, da + 0.04, do - 0.04, do + 0.04, -0.3, deck, metres=2.0, skip=("-z",))
            h = 1.2
            while h < deck:
                for (pa, pb), (qa, qb) in ((legs[0], legs[1]), (legs[1], legs[3]), (legs[3], legs[2]), (legs[2], legs[0])):
                    rod(steel, at(c, axes, pa, pb, h), at(c, axes, qa, qb, h), 0.02, seg=4)
                h += 1.2
            paint.colour = (0.35, 0.35, 0.37)
            box(paint, c, axes, -0.65, 0.65, -0.6, 0.65, deck - 0.08, deck)
            for (pa, pb), (qa, qb), hh in (((-0.6, 0.6), (0.6, 0.6), 0.95), ((-0.6, -0.55), (-0.6, 0.6), 0.95),
                                           ((0.6, -0.55), (0.6, 0.6), 0.95), ((-0.6, -0.55), (0.6, -0.55), 0.5)):
                rod(steel, at(c, axes, pa, pb, deck + hh), at(c, axes, qa, qb, deck + hh), 0.022, seg=4)
            pole = at(c, axes, 0.4, 0.45, deck)
            rod(steel, pole, add(pole, (0, 0, 2.45)), 0.02, seg=4)
            for k in range(8):  # the parasol: red and white
                a0, a1 = 2 * math.pi * k / 8, 2 * math.pi * (k + 1) / 8
                paint.colour = (0.85, 0.12, 0.1) if k % 2 else (0.95, 0.95, 0.93)
                apex = add(pole, (0, 0, 2.45))
                p0 = add(pole, (math.cos(a0) * 1.05, math.sin(a0) * 1.05, 2.0))
                p1 = add(pole, (math.cos(a1) * 1.05, math.sin(a1) * 1.05, 2.0))
                n = norm(cross(sub(p0, apex), sub(p1, apex)))
                if n[2] < 0:
                    n = mul(n, -1)
                v = [paint.vertex(p, n, (0, 0)) for p in (apex, p0, p1)]
                paint.tri(*v)
                v = [paint.vertex(p, mul(n, -1), (0, 0), shade(paint.colour, 0.7)) for p in (apex, p1, p0)]
                paint.tri(*v)

    # ---------- plants ----------
    def tuft(self, x, y, rnd, long=False):
        if self.pond and self.pond_q(x, y) < 1.05:
            return
        k = rnd.uniform(0.85, 1.1)
        if long:
            self.put("tuft_long", x, y, self.ground_z(x, y) - 0.01, rnd.uniform(0, 360), rnd.uniform(1.2, 1.9), (k * 1.02, k * 0.95, k * 0.8))
        else:
            self.put("tuft", x, y, self.ground_z(x, y) - 0.01, rnd.uniform(0, 360), rnd.uniform(0.8, 1.25),
                     (k * rnd.uniform(0.92, 1.05), k, k * rnd.uniform(0.85, 1.0)))

    def plants(self):
        """Copses of pines and broadleaf trees on the grass and a few on their own, bushes, rocks; grass tufts along
        the verges, long grass at the barriers' feet, wild flowers out on the grass and reeds round the pond."""
        t, H = self.t, self.half
        rnd = random.Random(41)
        lo_x, hi_x, lo_y, hi_y = self.xs[0] + 8, self.xs[-1] - 8, self.ys[0] + 8, self.ys[-1] - 8
        trees = []

        def room(x, y, clear):
            return (lo_x < x < hi_x and lo_y < y < hi_y and self.dist(x, y, H + clear + 2) >= H + clear
                    and self.free(x, y, 2.5) and all((x - a) ** 2 + (y - b) ** 2 > 13.0 for a, b in trees)
                    and not (self.pond and self.pond_q(x, y) < 1.6))
        centres = []
        for _ in range(300):
            x, y = rnd.uniform(lo_x, hi_x), rnd.uniform(lo_y, hi_y)
            if (len(centres) < 18 and self.dist(x, y, H + 16) >= H + 14 and self.free(x, y, 6)
                    and all(math.hypot(x - a, y - b) > 24 for a, b in centres)):
                centres.append((x, y))
        for cx, cy in centres:
            for _ in range(rnd.randint(5, 10)):
                x, y = cx + rnd.gauss(0, 6.0), cy + rnd.gauss(0, 6.0)
                if room(x, y, 9.0):
                    trees.append((x, y))
        lone = 0
        for _ in range(200):
            x, y = rnd.uniform(lo_x, hi_x), rnd.uniform(lo_y, hi_y)
            if lone < 24 and room(x, y, 11.0):
                trees.append((x, y))
                lone += 1
        for x, y in trees:
            pine_ = rnd.random() < 0.55
            shape = (("pine_a", "pine_b") if pine_ else ("broadleaf_a", "broadleaf_b"))[rnd.random() < 0.5]
            k = rnd.uniform(0.82, 1.08)
            tint = ((k * rnd.uniform(0.92, 1.06), k, k * rnd.uniform(0.9, 1.05)) if pine_
                    else (k * rnd.uniform(0.9, 1.18), k, k * rnd.uniform(0.8, 1.0)))
            self.put(shape, x, y, self.ground_z(x, y), rnd.uniform(0, 360), rnd.uniform(0.8, 1.25), tint)
            for _ in range(rnd.randint(2, 4)):
                a, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.6, 2.4)
                self.tuft(x + math.cos(a) * r, y + math.sin(a) * r, rnd, long=True)
        made = 0
        for i in range(500):
            if made >= 44:
                break
            if made < 24 and centres:
                cx, cy = centres[made % len(centres)]
                a, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(7.0, 13.0)
                x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
            else:
                x, y = rnd.uniform(lo_x, hi_x), rnd.uniform(lo_y, hi_y)
            if (lo_x < x < hi_x and lo_y < y < hi_y and self.dist(x, y, H + 10) >= H + 7.5
                    and self.free(x, y, 1.2, cameras=False) and not (self.pond and self.pond_q(x, y) < 1.4)):
                k = rnd.uniform(0.8, 1.08)
                self.put(("bush_a", "bush_b")[made % 2], x, y, self.ground_z(x, y) - 0.05, rnd.uniform(0, 360),
                         rnd.uniform(0.75, 1.3), (k * rnd.uniform(0.9, 1.12), k, k * rnd.uniform(0.82, 1.0)))
                made += 1
        made = 0
        for i in range(300):
            x, y = rnd.uniform(lo_x, hi_x), rnd.uniform(lo_y, hi_y)
            if made < 18 and self.dist(x, y, H + 10) >= H + 8.0 and self.free(x, y, 0.8, cameras=False) and not (
                    self.pond and self.pond_q(x, y) < 1.3):
                k = rnd.uniform(0.75, 1.05)
                self.put("rock", x, y, self.ground_z(x, y), rnd.uniform(0, 360), rnd.uniform(0.5, 1.4), (k, k * 0.98, k * 0.95))
                made += 1
        for side in (1, -1):
            W, in_wall = self.verge[side]
            for i in range(len(self.st) - 1):
                if in_wall[i]:
                    continue
                s0, s1 = self.st[i], self.st[i + 1]
                d_b = BARRIER + W[i]
                if W[i] <= 0.0:
                    for _ in range(2):  # the verge between the road and the barrier
                        d = H + rnd.uniform(0.62, d_b - 0.12)
                        x, y, _ = t.point(rnd.uniform(s0, s1), side * d)
                        if self.dist(x, y, d + 1) >= d - 0.3:
                            self.tuft(x, y, rnd)
                for _ in range(2):  # long grass at the barrier's foot, behind it
                    d = H + d_b + (0.62 if W[i] >= 0.6 else 0.15) + rnd.uniform(0.05, 1.2)
                    x, y, _ = t.point(rnd.uniform(s0, s1), side * d)
                    if self.dist(x, y, d + 1) >= d - 0.5:
                        self.tuft(x, y, rnd, long=True)
        for i in range(1100):  # out on the grass: tufts and wild flowers
            x, y = rnd.uniform(lo_x, hi_x), rnd.uniform(lo_y, hi_y)
            if self.dist(x, y, H + 12) < H + 10 or not self.free(x, y, 0.3, cameras=False):
                continue
            if rnd.random() < 0.3:
                if not (self.pond and self.pond_q(x, y) < 1.1):
                    colour = ((1.0, 1.0, 1.0), (1.0, 0.85, 0.2), (0.72, 0.45, 0.95), (1.0, 0.55, 0.7))[int(rnd.random() * 4)]
                    self.put("flowers", x, y, self.ground_z(x, y) - 0.01, rnd.uniform(0, 360), rnd.uniform(0.85, 1.3), colour)
            else:
                self.tuft(x, y, rnd)
        if self.pond:  # reeds round the water
            px, py, rx, ry, h = self.pond
            for i in range(60):
                a = rnd.uniform(0, 2 * math.pi)
                f = rnd.uniform(0.9, 1.15)
                d = (math.cos(a) * math.cos(h) * rx - math.sin(a) * math.sin(h) * ry,
                     math.cos(a) * math.sin(h) * rx + math.sin(a) * math.cos(h) * ry)
                x, y = px + d[0] * f, py + d[1] * f
                k = rnd.uniform(0.8, 1.0)
                self.put("tuft_long", x, y, max(self.water - 0.05, self.ground_z(x, y)) - 0.02, rnd.uniform(0, 360),
                         rnd.uniform(2.4, 3.6), (k * 0.85, k, k * 0.6))

    # ---------- the country ----------
    def hedge(self, part, p0, p1, z_of, rnd_key):
        """A hedgerow from p0 to p1 (ground points): a rounded ridge of leaves 1.5 m wide, up to 2 m tall."""
        length = math.dist(p0[:2], p1[:2])
        pieces = max(1, int(length / 25.0) + 1)
        d = norm((p1[0] - p0[0], p1[1] - p0[1], 0.0))
        side = (-d[1], d[0], 0.0)
        rows, normals, uvs, colours = [], [], [], []
        for k in range(pieces + 1):
            f = k / pieces
            x, y = lerp(p0[0], p1[0], f), lerp(p0[1], p1[1], f)
            z = z_of(x, y)
            hgt = 1.4 + 0.6 * noise(x / 7.0, y / 7.0, 57)
            rows.append([(x + side[0] * 0.8, y + side[1] * 0.8, z - 0.3), (x, y, z + hgt), (x - side[0] * 0.8, y - side[1] * 0.8, z - 0.3)])
            normals.append([norm(add(mul(side, 0.8), (0, 0, 0.6))), (0, 0, 1), norm(add(mul(side, -0.8), (0, 0, 0.6)))])
            u = (f * length) / 3.0
            uvs.append([(u, 0.0), (u, 0.6), (u, 1.2)])
            k_ = 0.78 + 0.3 * hash01(rnd_key, k, 59)
            colours.append([shade((0.55, 0.62, 0.45), k_ * 0.75), shade((0.9, 0.95, 0.75), k_), shade((0.55, 0.62, 0.45), k_ * 0.75)])
        sheet(part, rows, normals, uvs, colours)

    def land_vertex(self, r, a):
        x, y = self.centre[0] + r * math.cos(a), self.centre[1] + r * math.sin(a)
        z = self.land_z(x, y)
        gx, gy = (self.land_z(x + 2, y) - self.land_z(x - 2, y)) / 4, (self.land_z(x, y + 2) - self.land_z(x, y - 2)) / 4
        return (x, y, z), norm((-gx, -gy, 1.0))

    def country(self):
        """The country: fields in a patchwork (each its own colour, hedgerows between, trees in them) rising into the
        hills, the mountains round the horizon; woods; three farms; a hedge round the mown grass. All far: no
        shadows (the sun's shadows only reach round the karts)."""
        C, R = self.centre, self.reach
        land, hedges = self.far.get("land"), self.far.get("hedge")
        flat = R * 1.25
        inner = 0.55 * min(self.xs[-1] - C[0], self.ys[-1] - C[1])
        radii = [inner, R * 0.85, R, R * 1.12, flat] + [flat + d for d in (35, 75, 120, 170, 230, 300, 380, 470, 600, 780, 1000, 1300, 1650)]
        fields_to = flat + 380
        SEG = 128
        ang = [2 * math.pi * j / SEG for j in range(SEG + 1)]
        ring = [[self.land_vertex(r, a) for a in ang] for r in radii]
        weights = sum(w for _, w in FIELDS)

        def field(k, g):
            pick, acc = hash01(k, g, 71) * weights, 0.0
            for colour, w in FIELDS:
                acc += w
                if pick <= acc:
                    return colour
            return FIELDS[0][0]

        def hill_colour(p, n):
            h = p[2] - self.floor
            c = mix((0.3, 0.42, 0.18), (0.45, 0.43, 0.4), max(smooth((h - 45) / 40), smooth((0.86 - n[2]) / 0.14)))
            return mix(c, (0.92, 0.93, 0.96), smooth((h - 125) / 30))
        rnd = random.Random(53)
        for k in range(len(radii) - 1):
            r0, r1 = radii[k], radii[k + 1]
            if r1 <= R or r0 >= fields_to:
                groups = [(0, SEG)]
            else:
                groups, j, g = [], 0, max(1, round(80.0 / (2 * math.pi * (r0 + r1) / 2 / SEG)))
                while j < SEG:
                    size = max(1, g + int(hash01(k, j, 67) * 3) - 1)
                    groups.append((j, min(SEG, j + size)))
                    j += size
            for gi, (j0, j1) in enumerate(groups):
                rows = [[ring[k][j][0] for j in range(j0, j1 + 1)], [ring[k + 1][j][0] for j in range(j0, j1 + 1)]]
                normals = [[ring[k][j][1] for j in range(j0, j1 + 1)], [ring[k + 1][j][1] for j in range(j0, j1 + 1)]]
                if r1 <= R:
                    colours = [[(0.38, 0.52, 0.22)] * len(rows[0])] * 2
                elif r0 >= fields_to:
                    colours = [[hill_colour(p, n) for p, n in zip(rows[i], normals[i])] for i in (0, 1)]
                else:
                    c = field(k, gi)
                    colours = [[shade(c, 0.93 + 0.12 * noise(p[0] / 30.0, p[1] / 30.0, 73)) for p in rows[i]] for i in (0, 1)]
                sheet(land, rows, normals, [[(0.0, 0.0)] * len(rows[0])] * 2, colours)
                if R * 1.02 < r0 and r1 <= fields_to:  # hedgerows: along the field's edge out from the middle...
                    if hash01(k, j0, 61) < 0.8:
                        p0, p1 = ring[k][j0][0], ring[k + 1][j0][0]
                        self.hedge(hedges, p0, p1, self.land_z, k * 1000 + j0)
                        if hash01(k, j0, 63) < 0.5:
                            m = mul(add(p0, p1), 0.5)
                            self.put("broadleaf_far", m[0], m[1], self.land_z(m[0], m[1]) - 0.3, hash01(k, j0) * 360,
                                     0.8 + 0.5 * hash01(k, j0, 5), (0.95, 1.0, 0.86))
                    for j in range(j0, j1):  # ...and round its inner edge
                        if hash01(k, j // 3, 65) < 0.55:
                            self.hedge(hedges, ring[k][j][0], ring[k][j + 1][0], self.land_z, k * 1000 + j + 500)
        # a hedge round the mown grass (with gaps), where it meets the country
        x0, x1, y0, y1 = self.xs[0] - 1.5, self.xs[-1] + 1.5, self.ys[0] - 1.5, self.ys[-1] + 1.5
        border = self.near.get("hedge")
        for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            pieces = max(1, int(math.hypot(bx - ax, by - ay) / 12.0))
            for k in range(pieces):
                if hash01(int(ax), int(ay), k, 69) < 0.15:
                    continue
                f0, f1 = k / pieces, (k + 1) / pieces
                self.hedge(border, (lerp(ax, bx, f0), lerp(ay, by, f0)), (lerp(ax, bx, f1), lerp(ay, by, f1)), self.land_z,
                           int(ax) * 7 + k)
        # three farms out in the fields: a barn, a farmhouse and a silo each
        paint = self.far.get("paint")
        corner = math.hypot(self.xs[-1] - C[0], self.ys[-1] - C[1])
        farms = []
        for f in range(3):
            a = 2 * math.pi * (f / 3 + 0.12 + 0.12 * rnd.random())
            r = flat + 70 + f * 60
            p = (C[0] + r * math.cos(a), C[1] + r * math.sin(a))
            farms.append(p)
            axes = frame(rnd.uniform(0, math.pi))
            for (dx, dy), (hx, hy, hz, ridge), walls, roof in (((0, 0), (8, 4.5, 5, 3), (0.55, 0.22, 0.15), (0.35, 0.36, 0.38)),
                                                                ((-4, 14), (4.5, 3.5, 6, 2.5), (0.86, 0.8, 0.68), (0.3, 0.22, 0.2))):
                o = at((p[0], p[1], 0.0), axes, dx, dy, 0.0)
                o = (o[0], o[1], min(self.land_z(*at(o, axes, sx * hx, sy * hy, 0)[:2]) for sx in (-1, 1) for sy in (-1, 1)) - 0.3)
                paint.colour = walls
                box(paint, o, axes, -hx, hx, -hy, hy, 0.0, hz + 0.3, skip=("-z", "+z"))
                for sx in (-1, 1):  # the gables
                    n = mul(axes[0], sx)
                    paint.tri(paint.vertex(at(o, axes, sx * hx, -hy, hz + 0.3), n), paint.vertex(at(o, axes, sx * hx, hy, hz + 0.3), n),
                              paint.vertex(at(o, axes, sx * hx, 0, hz + 0.3 + ridge), n))
                paint.colour = roof
                for sy in (-1, 1):
                    n = norm(add(mul(axes[1], sy * ridge), mul(axes[2], hy)))
                    paint.quad([at(o, axes, -hx - 0.4, sy * (hy + 0.4), hz + 0.3 - 0.4 * ridge / hy), at(o, axes, hx + 0.4, sy * (hy + 0.4), hz + 0.3 - 0.4 * ridge / hy),
                                at(o, axes, hx + 0.4, 0, hz + 0.3 + ridge), at(o, axes, -hx - 0.4, 0, hz + 0.3 + ridge)], n)
            s = at((p[0], p[1], 0.0), axes, 12.0, -2.0, 0.0)
            zs = self.land_z(s[0], s[1]) - 0.3
            paint.colour = (0.74, 0.75, 0.77)
            column(paint, (s[0], s[1], zs), 2.4, 2.4, 11.0, seg=12, top=False)
            lathe_z(paint, (s[0], s[1], zs + 11.0), [(0.0, 1.6), (1.4, 1.2), (2.45, 0.0)], seg=12)
        # woods: copses of pines and broadleaf trees out in the fields
        for k in range(10):
            a = 2 * math.pi * (k + rnd.random() * 0.7) / 10
            r = rnd.uniform(corner + 25.0, flat + 380.0)
            cx, cy = C[0] + r * math.cos(a), C[1] + r * math.sin(a)
            spread = rnd.uniform(16.0, 36.0)
            for _ in range(rnd.randint(16, 36)):
                x, y = cx + rnd.gauss(0, spread / 2), cy + rnd.gauss(0, spread / 2)
                if (self.xs[0] - 6 < x < self.xs[-1] + 6 and self.ys[0] - 6 < y < self.ys[-1] + 6) or any(
                        math.hypot(x - fx, y - fy) < 32 for fx, fy in farms):
                    continue
                pine_ = rnd.random() < 0.6
                q = rnd.uniform(0.78, 1.05)
                self.put("pine_far" if pine_ else "broadleaf_far", x, y, self.land_z(x, y) - 0.3, rnd.uniform(0, 360),
                         rnd.uniform(0.8, 1.45), (q * 0.95, q, q * 0.95) if pine_ else (q * rnd.uniform(0.92, 1.15), q, q * 0.85))

    def as_dict(self):
        return {"parts": [p.packed() for p in self.near.all() + self.far.all()], "instances": self.inst}


def sign_v(row):
    """The v range (bottom, top) of one row of the signs texture (row 0 at the top of the picture), a little in
    from its edges so a blurred mipmap never bleeds in the next row."""
    rows = len(SIGNS)
    return 1 - (row + 1) / rows + 0.004, 1 - row / rows - 0.004


_cache = {}


def circuit(track):
    """The circuit for a kart_track.Track (built once per track: about a second)."""
    key = (track.name, round(track.length, 3), track.half)
    if key not in _cache:
        _cache[key] = Circuit(track)
    return _cache[key]


def shapes_once():
    if "shapes" not in _cache:
        _cache["shapes"] = shapes()
    return _cache["shapes"]


def scenery():
    """The whole thing, as models/kart_scenery.json holds it."""
    sh = shapes_once()
    tracks = {}
    tris = {}
    for name in kart_track.TRACKS:
        c = circuit(kart_track.load(name))
        tracks[name] = c.as_dict()
        own = sum(p.tris() for p in c.near.all() + c.far.all())
        placed = sum(len(rows) * sum(p.tris() for p in sh[shape]) for shape, rows in c.inst.items())
        tris[name] = {"parts": own, "instances": placed, "total": own + placed}
    return {"version": VERSION, "materials": MATERIALS,
            "shapes": {k: [p.packed() for p in v] for k, v in sh.items()},
            "tracks": tracks,
            "lights": {"from": LIGHTS_FROM, "step": LIGHTS_STEP, "dark": list(LAMP_DARK), "lit": list(LAMP_LIT)},
            "notes": {"frame": "the game's: x, y on the ground, z up, metres; triangles anticlockwise seen from outside",
                      "placement": "per track, exported here (kart_track.TRACKS are the only tracks): draw each track's "
                                   "parts as they are, and each shape at each of its instances: [x, y, z, h, s, r, g, b] = "
                                   "turn the shape h degrees anticlockwise about z, scale it by s, move it to (x, y, z); "
                                   "multiply the colours of its parts marked tint by (r, g, b)",
                      "colours": "vertex colours and tints are screen colours (sRGB): make them linear (c ** 2.2) as a "
                                 "material's colour is; the drawn colour is material colour x vertex colour x tint x texture",
                      "materials": "texture sets are kart_gfx.py's (and the engine's steel, concrete) as make_textures.py "
                                   "writes them to tex/: <texture>_albedo (sRGB), _mr (red: occlusion, green: roughness, "
                                   "blue: metal; times the material's rough and metal), _normal; uvs are in repeats already",
                      "decal": "drawn over the road: a small depth offset (the window: Panda's setDepthOffset(1))",
                      "two_sided": "seen from behind too (no back-face culling)",
                      "far": "out in the country: no shadow (the window hides it from the sun's shadow camera)",
                      "signs": "the signs texture is one row per SIGNS entry, top first: " + ", ".join(t for t, _, _ in SIGNS),
                      "lamp": "the start lights: five pairs on the gantry, parts lamp 1 to lamp 5 (group 1 to 5) from the left "
                              "as the grid sees them, dark red glass; \"lights\" says when each is lit "
                              "(kart_scenery.start_lights: from \"from\" seconds before GO one more pair each \"step\" "
                              "seconds, all out at GO) and their glow unlit and lit (linear light, as emission)",
                      "water": "the pond's texture coordinates are metres / its material's metres; \"flows\" says how "
                               "they move (kart_scenery.water_offset): drift metres a second, plus sway times "
                               "sin(2 pi t / sway_period), divided by metres",
                      "group": "a part drawn apart from the others of its material, because it changes while racing",
                      "bridge": "a footbridge over the road (kart_scenery.Circuit.bridge) is in the track's parts",
                      "tv_cameras": "kart_scenery.tv_cameras(track) = kart_gfx.ChaseCamera's six TV cameras: nothing "
                                    "taller than a barrier within 10 m of one",
                      "triangles": tris}}


if __name__ == "__main__":
    import time
    started = time.perf_counter()
    data = scenery()
    print(f"built in {time.perf_counter() - started:.2f} s")
    for name, n in data["notes"]["triangles"].items():
        inst = {k: len(v) for k, v in data["tracks"][name]["instances"].items()}
        print(f"{name:9s} {n['parts']:7d} triangles in parts, {n['instances']:7d} placed  {inst}")
