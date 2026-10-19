"""Kart Lab's sports cars (CHANGE 173; photo-real on ultra, CHANGE 174): four car bodies a learner can race in place
of the kart, built from numbers alone, so the window (kart_gfx.py) and the page (club-coders/web/make_models.py
writes them to models/) draw the same ones.

A car is only its look: it drives as the design's points say (kart_sim.stats_of), exactly as a kart does, so a
race stays fair whatever everyone picks. Each is a real car's shape and proportions (its length, width, height,
wheelbase, track and wheels as a real one's) made SCALE times its size, so it sits among the karts: about 2.5 to
2.9 m long.

One builder makes each car at two levels of detail:

- car(name), "low" (models/cars.json, about 15,000 triangles): every tier draws it, and ultra draws it when the
  car is far from the camera. The body with its wheel arches, the glasshouse (dark glass), lamps, grille, wings,
  scoops and plates, a plain alloy wheel.
- car_ultra(name), "high" (models/cars_ultra_<name>.json, about 100,000): ultra draws it near the camera. The same
  body at three times the detail with shut lines; see-through glass with the cabin behind it (door cards, roof
  lining, dashboard, seats, a steering wheel and a driver in a helmet); headlamps with clear covers, reflectors and
  running lights; tail lamps behind red lenses; mesh grilles, mirrors, door handles, wipers, an aerial, exhausts, a
  diffuser, number plates; wheels with real tyres (sidewalls and grooves), spoked rims, wheel nuts, brake discs, and
  calipers that turn with the steering but not with the wheel ("brake").

Both return {"version", "name", "body": [part], "nose": [part], "wheel": [part], "wheels": [...], "notes": {...}},
car_ultra also "brake": {"left": [part], "right": [part]}:

    "body":   the car's own parts, in the car's frame (kart_models' part: positions, normals, indices, uvs, a role)
    "nose":   the front splitter (and the front plate on it), which hangs from its left end as the front wing is
              damaged (notes["nose"]["pivot"])
    "wheel":  ONE wheel centred at the origin, its axle along +y, its outer face at +y
    "wheels": [{"x", "y", "z", "front", "side"}, ...] as kart_models' (side -1: turned 180 degrees about z)
    "brake":  a brake caliper for each side, in the wheel's frame (the left one's outer face at +y; the right's
              already the mirror image, not turned): it goes on the wheel's steering pivot, not its spinner
    "notes":  {"nose": {"pivot"}, "lamps": {"head", "tail", "size"}, "smoke", "glow", "hood", "height",
               "wheel_radius", "title", "roles", "triangles", "lod"}

The frame is the game's: x forward, y left, z up, metres, the ground at z = 0 under the car's middle. Roles as
kart_models' (paint is the design's colour) and more: "light" the lamps' housings, "window" see-through glass,
"lens" a lamp's clear cover, "lens_red" a tail lamp's red one over "lamp_red", "drl" a running light, "interior"
the cabin's trim, "gap" a shut line or an opening's dark inside, "carbon" gloss black trim, "liner" the arches'
insides, "disc" a brake disc, "caliper", "rim2" a coloured rim, "plate" and "plate_rear" the number plates,
"stripe" racing stripes.
A role's "alpha" (under 1) is drawn see-through and two-sided; "emission" glows.
"""
import bisect
import math

import kart_models as km
from kart_models import Part, add, sub, mul, dot, cross, norm, spow

VERSION = 2  # (2: real cars' shapes and proportions, and the ultra cars: CHANGE 174)
SCALE = 0.6  # a real car made this much of its size
BODIES = ("kart", "coupe", "supercar", "rally", "muscle")  # (kart: the kart itself, as before)
TITLES = {"kart": "Kart", "coupe": "GT coupe", "supercar": "Supercar", "rally": "Rally hatch", "muscle": "Muscle car"}
ROLES = dict(km.ROLES,
             light={"colour": [0.85, 0.85, 0.86], "rough": 0.1, "metal": 0.6},
             window={"colour": [0.015, 0.02, 0.025], "rough": 0.02, "metal": 0.0, "alpha": 0.3},
             lens={"colour": [0.03, 0.03, 0.035], "rough": 0.02, "metal": 0.0, "alpha": 0.12},
             lens_red={"colour": [0.5, 0.012, 0.01], "rough": 0.04, "metal": 0.0, "alpha": 0.5},
             lamp_red={"colour": [0.32, 0.012, 0.01], "rough": 0.25, "metal": 0.3},
             drl={"colour": [1.0, 1.0, 1.0], "rough": 0.3, "metal": 0.0, "emission": [3.0, 3.0, 3.2]},
             interior={"colour": [0.045, 0.045, 0.05], "rough": 0.85, "metal": 0.0},
             gap={"colour": [0.008, 0.008, 0.009], "rough": 0.9, "metal": 0.0},
             carbon={"colour": [0.035, 0.035, 0.04], "rough": 0.18, "metal": 0.25},
             liner={"colour": [0.03, 0.03, 0.032], "rough": 0.95, "metal": 0.0},
             disc={"colour": [0.55, 0.55, 0.57], "rough": 0.38, "metal": 1.0},
             caliper={"colour": [0.8, 0.06, 0.04], "rough": 0.28, "metal": 0.1},
             rim2={"colour": [0.92, 0.92, 0.93], "rough": 0.3, "metal": 0.3},
             plate={"colour": [0.93, 0.93, 0.91], "rough": 0.35, "metal": 0.0},
             plate_rear={"colour": [0.97, 0.78, 0.08], "rough": 0.35, "metal": 0.0},
             stripe={"colour": [0.92, 0.92, 0.9], "rough": 0.32, "metal": 0.15})


# ---------- curves ----------
def smooth(points):
    """A smooth function of x through (x, value) points, never overshooting them (monotone cubic: Fritsch and
    Carlson), level beyond the ends."""
    pts = sorted(points)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    n = len(pts)
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
        else:
            a, b = m[i] / d[i], m[i + 1] / d[i]
            s = a * a + b * b
            if s > 9:
                t = 3 / math.sqrt(s)
                m[i], m[i + 1] = t * a * d[i], t * b * d[i]

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        i = min(n - 2, max(0, bisect.bisect_right(xs, x) - 1))
        h = xs[i + 1] - xs[i]
        t = (x - xs[i]) / h
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1]
                + (t3 - t2) * h * m[i + 1])
    return f


def spline(points, counts):
    """A smooth curve through points (2D or 3D tuples), counts[i] pieces between point i and point i + 1
    (centripetal Catmull-Rom: no loops or overshoot where the points are unevenly spaced)."""
    n = len(points)
    out = []
    for i in range(n - 1):
        p1, p2 = points[i], points[i + 1]
        p0 = points[i - 1] if i > 0 else tuple(2 * a - b for a, b in zip(p1, p2))
        p3 = points[i + 2] if i + 2 < n else tuple(2 * b - a for a, b in zip(p1, p2))
        t0 = 0.0
        t1 = t0 + max(1e-6, math.dist(p0, p1)) ** 0.5
        t2 = t1 + max(1e-6, math.dist(p1, p2)) ** 0.5
        t3 = t2 + max(1e-6, math.dist(p2, p3)) ** 0.5
        for k in range(counts[i]):
            t = t1 + (t2 - t1) * k / counts[i]

            def lerp(a, b, ta, tb):
                w = (t - ta) / (tb - ta)
                return tuple(x + (y - x) * w for x, y in zip(a, b))
            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            b1, b2 = lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3)
            out.append(lerp(b1, b2, t1, t2))
    out.append(tuple(points[-1]))
    return out


def lerp(a, b, t):
    return a + (b - a) * t


# ---------- surfaces handed out to parts ----------
class Parts:
    """A car's parts by name: each role's triangles in one part (or more, by name)."""

    def __init__(self):
        self.all = {}

    def get(self, name, role=None):
        if name not in self.all:
            self.all[name] = Part(name, role or name.split()[-1])
        return self.all[name]

    def list(self):
        return [p for p in self.all.values() if p.idx]


def normals_of(rows, inside, wrap, poles=None):
    """Each point's normal from its neighbours (as kart_models.Part.surface), turned away from inside(point)."""
    R, C = len(rows), len(rows[0])
    out = []
    for r in range(R):
        nrow = []
        for j in range(C):
            if poles and r in poles:
                nrow.append(poles[r])
                continue
            if wrap:
                jl, jr = (j - 1) % (C - 1), (j + 1) % (C - 1)
            else:
                jl, jr = max(0, j - 1), min(C - 1, j + 1)
            ru, rd = min(R - 1, r + 1), max(0, r - 1)
            n = norm(cross(sub(rows[r][jr], rows[r][jl]), sub(rows[ru][j], rows[rd][j])))
            if n == (0.0, 0.0, 0.0):
                n = norm(sub(rows[r][j], inside(rows[r][j])))
            if dot(n, sub(rows[r][j], inside(rows[r][j]))) < 0:
                n = mul(n, -1)
            nrow.append(n)
        out.append(nrow)
    return out


def uvs_of(rows, scale):
    R, C = len(rows), len(rows[0])
    us = []
    for r in range(R):
        u, row = 0.0, []
        for j in range(C):
            if j:
                u += math.dist(rows[r][j], rows[r][j - 1])
            row.append(u)
        us.append(row)
    out, vcol = [], [0.0] * C
    for r in range(R):
        if r:
            vcol = [v + math.dist(rows[r][j], rows[r - 1][j]) for j, v in enumerate(vcol)]
        out.append([(us[r][j] * scale, vcol[j] * scale) for j in range(C)])
    return out


def emit(parts, rows, inside, classify, wrap=True, poles=None, uv_scale=1.5, inset=0.006):
    """A surface through rows of points, its quads handed out by classify(r, j) (the quad from row r, column j):
    None (left out: a hole), a part's name, or (name, inner name): a second copy facing in, inset metres inside it
    (a door's inside, a roof's lining). A part's role is its name's last word."""
    normals = normals_of(rows, inside, wrap, poles)
    uvs = uvs_of(rows, uv_scale)
    index = {}

    def vert(name, r, j, flip):
        key = (name, flip, r, j)
        if key not in index:
            n = normals[r][j]
            p = rows[r][j]
            if flip:
                p, n = sub(p, mul(n, inset)), mul(n, -1)
            index[key] = parts.get(name, name.split()[-1]).vertex(p, n, uvs[r][j])
        return index[key]
    for r in range(len(rows) - 1):
        for j in range(len(rows[0]) - 1):
            got = classify(r, j)
            if got is None:
                continue
            names = [(got, False)] if isinstance(got, str) else [(got[0], False)] + ([(got[1], True)] if got[1] else [])
            for name, flip in names:
                a, b, c, d = (vert(name, r, j, flip), vert(name, r, j + 1, flip), vert(name, r + 1, j + 1, flip),
                              vert(name, r + 1, j, flip))
                part = parts.get(name, name.split()[-1])
                part.tri(a, b, c)
                part.tri(a, c, d)


# ---------- the cars, as real ones (metres; SCALE makes them the game's size) ----------
# nose and tail: the body's front and back (x); axles: the front and rear axles' x; wheel: the tyre's radius, the
# rim's, the tyre's half width, and how far out each wheel's middle is (half the track). The body's outline as
# smooth curves of x: width (half the body's width), bottom (its underside), belt (the shoulder, where its side
# turns over onto its top) and top (its top along the middle: the bonnet, the boot). rise: how far the top's edge
# stands over the belt; tumble: how far up the side is widest (0 the sill, 1 the belt). glass: the glasshouse (base
# and rear: where the windscreen and the back window meet the body; roof: its top's height along x; roof_w: its
# top's half width; side: the side windows' front edge (x at the belt, x at the roof) and back edge; ws_top and
# roof_rear: where the windscreen and back window meet the roof; b_pillar: a pillar between the side windows).
# seams: the doors' shut lines (x); lamps: (y, z) and (width, height) of the headlamps and tail lamps; grille and
# intake: (half width, z, half height); exhausts: (y, z, radius) each; driver: where the driver sits (x, y: on the
# right, as in Britain).
CARS = {
    "coupe": dict(
        nose=2.24, tail=-2.23, axles=(1.36, -1.26), wheel=(0.345, 0.255, 0.125, 0.8),
        width=[(2.24, 0.62), (2.18, 0.8), (2.04, 0.89), (1.65, 0.93), (1.0, 0.915), (0.2, 0.91), (-0.7, 0.935),
               (-1.25, 0.96), (-1.75, 0.935), (-2.08, 0.86), (-2.23, 0.7)],
        bottom=[(2.24, 0.33), (2.05, 0.21), (1.7, 0.16), (-1.4, 0.16), (-1.95, 0.23), (-2.23, 0.39)],
        belt=[(2.24, 0.54), (2.0, 0.66), (1.36, 0.78), (0.6, 0.835), (-0.4, 0.865), (-1.26, 0.905), (-1.9, 0.89),
              (-2.23, 0.84)],
        top=[(2.24, 0.585), (2.12, 0.69), (1.8, 0.755), (1.2, 0.8), (0.55, 0.855), (0.3, 0.875), (-1.55, 0.93),
             (-1.9, 0.945), (-2.12, 0.93), (-2.23, 0.865)],
        rise=0.035, tumble=0.42,
        glass=dict(base=0.4, rear=-1.66, ws_top=-0.24, roof_rear=-0.86,
                   roof=[(0.05, 1.1), (-0.24, 1.27), (-0.55, 1.3), (-0.86, 1.27), (-1.22, 1.12)],
                   roof_w=[(0.4, 0.72), (-0.24, 0.57), (-0.86, 0.555), (-1.66, 0.7)],
                   side=((0.3, -0.18), (-1.18, -0.8)), b_pillar=None),
        seams=[0.36, -1.02], boot=-1.72,
        lamps=dict(head=(0.6, 0.66, 0.36, 0.085), tail=(0.6, 0.8, 0.44, 0.075)),
        grille=(0.3, 0.44, 0.105), intake=(0.48, 0.27, 0.05), exhausts=[(0.1, 0.31, 0.045), (-0.1, 0.31, 0.045)],
        driver=(-0.62, -0.37), engine="front", roof_role="paint", skirt="paint", rim="split", rim_role="rim",
        extras=["ducktail", "gills", "fin"]),
    "supercar": dict(
        nose=2.3, tail=-2.25, axles=(1.33, -1.34), wheel=(0.35, 0.265, 0.135, 0.84),
        width=[(2.3, 0.55), (2.22, 0.8), (2.0, 0.92), (1.4, 0.955), (0.6, 0.93), (-0.3, 0.965), (-1.0, 0.99),
               (-1.6, 0.98), (-2.05, 0.925), (-2.25, 0.8)],
        bottom=[(2.3, 0.22), (2.02, 0.13), (1.6, 0.11), (-1.5, 0.11), (-2.0, 0.16), (-2.25, 0.3)],
        belt=[(2.3, 0.4), (2.02, 0.62), (1.62, 0.76), (1.33, 0.8), (1.0, 0.77), (0.7, 0.73), (0.0, 0.745), (-0.8, 0.8),
              (-1.34, 0.86), (-2.0, 0.84), (-2.25, 0.765)],
        top=[(2.3, 0.38), (2.15, 0.52), (1.8, 0.63), (1.3, 0.7), (0.98, 0.73), (0.82, 0.745), (-0.5, 0.86),
             (-1.0, 0.9), (-1.7, 0.905), (-2.1, 0.875), (-2.25, 0.8)],
        rise=0.03, tumble=0.38,
        glass=dict(base=0.84, rear=-0.98, ws_top=0.06, roof_rear=-0.6,
                   roof=[(0.45, 0.99), (0.06, 1.14), (-0.3, 1.175), (-0.6, 1.12)],
                   roof_w=[(0.84, 0.7), (0.06, 0.52), (-0.6, 0.5), (-0.98, 0.56)],
                   side=((0.66, 0.1), (-0.58, -0.36)), b_pillar=None),
        seams=[0.72, -0.5], boot=None,
        lamps=dict(head=(0.66, 0.5, 0.32, 0.05), tail=(0.64, 0.7, 0.5, 0.05)),
        grille=(0.24, 0.3, 0.06), intake=(0.62, 0.28, 0.075), exhausts=[(0.13, 0.42, 0.05), (-0.13, 0.42, 0.05)],
        driver=(-0.18, -0.36), engine="middle", roof_role="carbon", skirt="carbon", rim="y", rim_role="carbon",
        extras=["wing", "side_intakes", "louvres", "bonnet_vents", "rear_mesh"]),
    "rally": dict(
        nose=2.02, tail=-1.98, axles=(1.3, -1.26), wheel=(0.33, 0.23, 0.12, 0.8),
        width=[(2.02, 0.7), (1.92, 0.86), (1.7, 0.93), (1.3, 0.955), (0.8, 0.9), (0.0, 0.89), (-0.8, 0.9),
               (-1.26, 0.96), (-1.7, 0.93), (-1.92, 0.86), (-1.98, 0.78)],
        bottom=[(2.02, 0.31), (1.85, 0.23), (1.5, 0.21), (-1.45, 0.21), (-1.85, 0.27), (-1.98, 0.35)],
        belt=[(2.02, 0.7), (1.8, 0.8), (1.3, 0.86), (0.5, 0.915), (-0.5, 0.945), (-1.26, 0.975), (-1.84, 0.975),
              (-1.98, 0.955)],
        top=[(2.02, 0.68), (1.9, 0.82), (1.5, 0.9), (1.0, 0.945), (0.68, 0.965), (0.52, 0.975), (-1.7, 1.0),
             (-1.88, 1.0), (-1.98, 0.975)],
        rise=0.03, tumble=0.4,
        glass=dict(base=0.55, rear=-1.84, ws_top=-0.16, roof_rear=-1.42,
                   roof=[(0.2, 1.2), (-0.16, 1.41), (-0.6, 1.455), (-1.2, 1.435), (-1.5, 1.38), (-1.68, 1.22)],
                   roof_w=[(0.55, 0.72), (-0.16, 0.6), (-1.35, 0.6), (-1.84, 0.66)],
                   side=((0.45, -0.1), (-1.36, -1.18)), b_pillar=(-0.55, 0.09)),
        seams=[0.49, -0.6, -1.3], boot=None,
        lamps=dict(head=(0.6, 0.79, 0.3, 0.11), tail=(0.66, 0.88, 0.3, 0.11)),
        grille=(0.42, 0.5, 0.14), intake=(0.55, 0.32, 0.06), exhausts=[(-0.45, 0.31, 0.06)],
        driver=(-0.5, -0.37), engine="front", roof_role="paint", skirt="carbon", rim="rally", rim_role="rim2",
        extras=["roof_scoop", "roof_wing", "flaps", "spots", "tow"]),
    "muscle": dict(
        nose=2.42, tail=-2.38, axles=(1.42, -1.3), wheel=(0.35, 0.255, 0.135, 0.81),
        width=[(2.42, 0.78), (2.36, 0.89), (2.12, 0.945), (1.4, 0.96), (0.5, 0.95), (-0.6, 0.955), (-1.3, 0.97),
               (-1.9, 0.96), (-2.3, 0.9), (-2.38, 0.84)],
        bottom=[(2.42, 0.3), (2.2, 0.2), (1.9, 0.175), (-1.5, 0.175), (-2.1, 0.22), (-2.38, 0.32)],
        belt=[(2.42, 0.78), (2.2, 0.82), (1.42, 0.84), (0.6, 0.86), (-0.4, 0.88), (-1.3, 0.9), (-2.0, 0.9),
              (-2.38, 0.88)],
        top=[(2.42, 0.8), (2.3, 0.86), (1.9, 0.88), (1.2, 0.9), (0.38, 0.935), (0.18, 0.95), (-1.5, 0.975),
             (-1.9, 0.98), (-2.3, 0.97), (-2.38, 0.93)],
        rise=0.025, tumble=0.5,
        glass=dict(base=0.15, rear=-1.58, ws_top=-0.5, roof_rear=-1.1,
                   roof=[(-0.25, 1.22), (-0.5, 1.34), (-0.8, 1.36), (-1.1, 1.33), (-1.36, 1.15)],
                   roof_w=[(0.15, 0.72), (-0.5, 0.58), (-1.1, 0.57), (-1.58, 0.68)],
                   side=((0.05, -0.46), (-1.18, -1.06)), b_pillar=None),
        seams=[0.12, -1.12], boot=-1.68,
        lamps=dict(head=(0.64, 0.76, 0.26, 0.1), tail=(0.5, 0.8, 0.58, 0.1)),
        grille=(0.62, 0.64, 0.12), intake=(0.5, 0.33, 0.05), exhausts=[(0.58, 0.28, 0.05), (-0.58, 0.28, 0.05)],
        driver=(-0.72, -0.37), engine="front", roof_role="paint", skirt="paint", rim="muscle", rim_role="chrome",
        extras=["hood_scoop", "stripes", "chrome_bumpers", "ducktail"]),
}

# each level's detail: x spacing (m, as a real car), the points along each piece of half a body section (from the
# underside's middle: the floor, the sill's turn, the lower side, the upper side, the shoulder, the top's edge, the
# top), and of half the glasshouse's (the lower side, the upper side, the roof's edge, the roof), the rings closing
# each end, the wheel's segments round, whether the cabin is drawn
LEVELS = {
    "low": dict(dx=0.055, sec=(2, 1, 4, 4, 1, 2, 2), glass=(3, 3, 2, 2), cap=3, wheel=28, cabin=False),
    "high": dict(dx=0.026, sec=(5, 3, 9, 9, 3, 6, 7), glass=(6, 6, 4, 6), cap=7, wheel=72, cabin=True),
}
SIDE_SEGS = (1, 2, 3, 4)      # the section's pieces on the side (the sill's turn to the shoulder)
TOP_SEGS = (5, 6)             # ...on the top
GAP = 0.004                   # half a shut line's width (m)


def stations(x0, x1, dx, extra):
    """x from x0 to x1 about dx apart, with every x in extra among them (none closer than a third of dx to one)."""
    keep = sorted(set(round(x, 5) for x in extra if x0 < x < x1))
    n = max(1, int(math.ceil((x1 - x0) / dx)))
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    xs = [x for x in xs if all(abs(x - k) > dx / 3 for k in keep)] + keep
    return sorted(set(xs))


def snap_crossings(rows, f, movable, wrap=False):
    """Points moved onto a boundary f(p) = 0 (f < 0 on one side) wherever an edge between two neighbouring points
    crosses it: the nearer end of each such edge, each point once; then, where an edge still crosses (both its ends
    taken), its inside end. Holes and windows cut by it then have smooth edges whatever the grid's spacing."""
    R, C = len(rows), len(rows[0])
    moved = set()

    def crossing(a, b, fa):
        lo, hi = 0.0, 1.0
        for _ in range(18):
            mid = (lo + hi) / 2
            if (f(tuple(u + (v - u) * mid for u, v in zip(a, b))) < 0) == (fa < 0):
                lo = mid
            else:
                hi = mid
        t = (lo + hi) / 2
        return t, tuple(u + (v - u) * t for u, v in zip(a, b))
    for again in (False, True, True):
        for r in range(R):
            for j in range(C):
                if not movable(r, j):
                    continue
                for rr, jj in ((r + 1, j), (r, j + 1)):
                    if rr >= R or jj >= C or not movable(rr, jj):
                        continue
                    a, b = rows[r][j], rows[rr][jj]
                    fa, fb = f(a), f(b)
                    if fa * fb >= 0:
                        continue
                    t, p = crossing(a, b, fa)
                    if t < 0.5 and (r, j) not in moved:
                        rows[r][j] = p
                        moved.add((r, j))
                    elif (rr, jj) not in moved:
                        rows[rr][jj] = p
                        moved.add((rr, jj))
                    elif again:
                        if fa < 0:
                            rows[r][j] = p
                        else:
                            rows[rr][jj] = p
    if wrap:
        for row in rows:
            row[-1] = row[0]


def in_polygon(pts, y, z):
    """Whether (y, z) is inside a closed outline of (y, z) points (crossings)."""
    inside = False
    n = len(pts)
    for i in range(n):
        (y1, z1), (y2, z2) = pts[i], pts[(i + 1) % n]
        if (z1 > z) != (z2 > z) and y < y1 + (y2 - y1) * (z - z1) / (z2 - z1):
            inside = not inside
    return inside


class Car:
    """One car at one level of detail, built into parts (real size: scaled() makes it the game's)."""

    def __init__(self, name, level="high"):
        self.name, self.c, self.L = name, CARS[name], LEVELS[level]
        self.high = level == "high"
        c = self.c
        self.width, self.bottom = smooth(c["width"]), smooth(c["bottom"])
        self.belt, self.top = smooth(c["belt"]), smooth(c["top"])
        self.R, self.rim_r, self.tw, self.track = c["wheel"]
        self.arch_r = self.R + 0.045
        self.bulge_f, self.bulge_r = 0.045, 0.035
        g = c["glass"]
        self.gbase, self.grear = g["base"], g["rear"]
        self.roof_w = smooth(g["roof_w"])
        self.roof = smooth([(self.gbase, self.belt(self.gbase) + 0.004)] + list(g["roof"])
                           + [(self.grear, self.belt(self.grear) + 0.004)])
        self.parts = Parts()
        self._half = {}
        self.bounds = [0]
        for n in self.L["sec"]:
            self.bounds.append(self.bounds[-1] + n)
        self.gbounds = [0]
        for n in self.L["glass"]:
            self.gbounds.append(self.gbounds[-1] + n)

    # ---------- the body's sections ----------
    def keys(self, x):
        c = self.c
        w, zb, zs, zt = self.width(x), self.bottom(x), self.belt(x), self.top(x)
        rise, tum = c["rise"], c["tumble"]
        return [(0.0, zb), (0.8 * w, zb), (0.965 * w, zb + 0.045), (w, zb + tum * (zs - zb)), (0.968 * w, zs),
                (0.92 * w, zs + rise), (0.5 * w, zt + (zs + rise - zt) * 0.3), (0.0, zt)]

    def half(self, x):
        """Half the section at x, (y, z) from the underside's middle round the left side to the top's middle."""
        key = round(x, 3)  # (to the millimetre: the faces' searches ask at many x)
        if key not in self._half:
            self._half[key] = spline(self.keys(key), self.L["sec"])
        return self._half[key]

    def outline(self, x):
        h = self.half(x)
        return h + [(-y, z) for y, z in reversed(h[1:-1])]

    def seg(self, j):
        """Which piece of the section the quad from column j is on (0 to 6), either side."""
        n = self.bounds[-1]
        jj = j if j < n else 2 * n - j - 1
        return bisect.bisect_right(self.bounds, jj) - 1

    def centre(self, x):
        return (x, 0.0, (self.bottom(x) + self.top(x)) / 2)

    def inside(self, x, y, z):
        """Whether a point is inside the body (its ends' caps too)."""
        c = self.c
        for end, bulge, past in ((c["nose"], self.bulge_f, x - c["nose"]), (c["tail"], self.bulge_r, c["tail"] - x)):
            if past > 0:
                t = past / bulge
                if t >= 1:
                    return False
                s = math.sqrt(1 - t)
                cz = (self.bottom(end) + self.top(end)) / 2
                return in_polygon(self.outline(end), y / s, cz + (z - cz) / s)
        return in_polygon(self.outline(x), y, z)

    def front_x(self, y, z, behind=0.7):
        """The body's front at (y, z): the furthest x forward still inside it (None if it isn't there)."""
        lo, hi = self.c["nose"] - behind, self.c["nose"] + self.bulge_f
        if not self.inside(lo, y, z):
            return None
        for _ in range(26):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if self.inside(mid, y, z) else (lo, mid)
        return lo

    def rear_x(self, y, z, ahead=0.7):
        lo, hi = self.c["tail"] - self.bulge_r, self.c["tail"] + ahead
        if not self.inside(hi, y, z):
            return None
        for _ in range(26):
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if self.inside(mid, y, z) else (mid, hi)
        return hi

    def side_y(self, x, z):
        """The body's left side at (x, z): its y (the furthest out, between the sill and the shoulder)."""
        h = self.half(x)
        b = self.bounds
        best = None
        for i in range(b[1], b[5]):
            (y1, z1), (y2, z2) = h[i], h[i + 1]
            if min(z1, z2) <= z <= max(z1, z2) and z1 != z2:
                y = y1 + (y2 - y1) * (z - z1) / (z2 - z1)
                best = y if best is None else max(best, y)
        return best

    def top_z(self, x, y):
        """The body's top at (x, y) (the shoulder in to the middle)."""
        h = self.half(x)
        y = abs(y)
        for i in range(self.bounds[4], len(h) - 1):
            (y1, z1), (y2, z2) = h[i], h[i + 1]
            if min(y1, y2) <= y <= max(y1, y2) and y1 != y2:
                return z1 + (z2 - z1) * (y - y1) / (y2 - y1)
        return None

    # ---------- the body ----------
    def wheel_spots(self):
        fx, rx = self.c["axles"]
        return [(fx, self.track), (fx, -self.track), (rx, self.track), (rx, -self.track)]

    def body(self):
        c, L = self.c, self.L
        dx = L["dx"]
        extra = [self.gbase, self.grear]
        for s in c["seams"] + ([c["boot"]] if c["boot"] else []):
            extra += [s - GAP, s + GAP]
        for ax in c["axles"]:
            extra += [ax + self.arch_r * math.cos(math.pi * k / 12) for k in range(13)]
        xs = stations(c["tail"], c["nose"], dx, extra)
        rows, row_x, kind = [], [], []
        M = L["cap"]
        tail, nose = c["tail"], c["nose"]
        # the tail's cap: rings from a point out to the tail's section, standing out bulge_r behind it
        ring_t = self.outline(tail)
        czt = (self.bottom(tail) + self.top(tail)) / 2
        for k in range(M):
            s = k / M
            rows.append([(tail - self.bulge_r * (1 - s * s), y * s, czt + (z - czt) * s) for y, z in ring_t + ring_t[:1]])
            row_x.append(tail)
            kind.append("cap")
        for x in xs:
            o = self.outline(x)
            rows.append([(x, y, z) for y, z in o + o[:1]])
            row_x.append(x)
            kind.append("body")
        ring_n = self.outline(nose)
        czn = (self.bottom(nose) + self.top(nose)) / 2
        for k in range(M - 1, -1, -1):
            s = k / M
            rows.append([(nose + self.bulge_f * (1 - s * s), y * s, czn + (z - czn) * s) for y, z in ring_n + ring_n[:1]])
            row_x.append(nose)
            kind.append("cap")
        # the wheel arches: the side's points moved onto each arch's edge where the grid crosses it, the points
        # inside it left out
        cut_y = self.track - self.tw - 0.05

        def arch(p):
            return min(math.hypot(p[0] - ax, p[2] - self.R) for ax in c["axles"]) - self.arch_r
        snap_crossings(rows, arch, lambda r, j: kind[r] == "body" and abs(rows[r][j][1]) > cut_y, wrap=True)
        inside = [[kind[r] == "body" and abs(p[1]) > cut_y and arch(p) < -1e-6 for p in row] for r, row in enumerate(rows)]
        skirt, cabin = c["skirt"], self.L["cabin"]
        lo_x, hi_x = self.grear, self.gbase

        def classify(r, j):
            if any(inside[rr][jj] for rr in (r, r + 1) for jj in (j, j + 1)):
                return None
            s = self.seg(j)
            x0, x1 = row_x[r], row_x[r + 1]
            body_row = kind[r] == "body" and kind[r + 1] == "body"
            if body_row and s in TOP_SEGS and lo_x <= x0 and x1 <= hi_x:
                return None  # (under the glasshouse: the cabin shows through the glass)
            if s == 0:
                return "underbody dark"
            if s == 1:
                return "sills " + skirt
            if body_row:
                for seam in c["seams"]:
                    if seam - GAP - 1e-6 <= x0 and x1 <= seam + GAP + 1e-6 and s in (2, 3):
                        return "shut lines gap"
                if c["boot"] and c["boot"] - GAP - 1e-6 <= x0 and x1 <= c["boot"] + GAP + 1e-6 and s in (4, 5, 6):
                    return "shut lines gap"
                if cabin and s in (2, 3, 4) and lo_x - 0.02 <= x0 and x1 <= hi_x + 0.02:
                    return ("body paint", "door cards interior")
            return "body paint"
        emit(self.parts, rows, lambda p: self.centre(max(tail + 0.2, min(nose - 0.2, p[0]))), classify,
             poles={0: (-1.0, 0.0, 0.0), len(rows) - 1: (1.0, 0.0, 0.0)})
        self.arches()

    def arches(self):
        """Inside each wheel arch: a liner round the top of the tyre, closed at its inner end, and the arch's edge
        rolled over (a lip)."""
        seg = self.L["wheel"] // 2
        cut_y = self.track - self.tw - 0.05
        liner = self.parts.get("arch liners liner")
        lip = self.parts.get("arch lips paint")
        for ax, wy in self.wheel_spots():
            side = 1 if wy > 0 else -1
            zb = self.bottom(ax)
            a0 = math.asin(max(-1.0, min(1.0, (zb - self.R) / self.arch_r)))  # (where the arch meets the sill)
            angs = [math.pi - a0 - (math.pi - 2 * a0) * k / seg for k in range(seg + 1)]  # (back, over the top, front)
            ring = [(ax + (self.arch_r + 0.004) * math.cos(a), self.R + (self.arch_r + 0.004) * math.sin(a)) for a in angs]
            rows = [[(x, side * (cut_y - 0.005), z) for x, z in ring],
                    [(x, side * ((self.side_y(x, z) or self.track + self.tw) - 0.008), z) for x, z in ring]]
            emit(self.parts, rows, lambda p, ax=ax: (ax, p[1], self.R), lambda r, j: "arch liners liner", wrap=False)
            face = [(ax + self.arch_r * math.cos(a), side * (cut_y - 0.005), self.R + self.arch_r * math.sin(a))
                    for a in angs]
            n = (0.0, float(side), 0.0)
            mid = liner.vertex((ax, side * (cut_y - 0.005), zb + 0.02), n)
            vs = [liner.vertex(p, n) for p in face]
            for i in range(len(vs) - 1):
                liner.tri(mid, vs[i], vs[i + 1])
            path = []
            for a in angs[1:-1]:
                x, z = ax + self.arch_r * math.cos(a), self.R + self.arch_r * math.sin(a)
                y = self.side_y(x, z)
                if y is not None:
                    path.append((x, side * (y - 0.004), z))
            if len(path) > 2:
                km.tube(lip, path, 0.012, seg=8 if self.high else 5, steps=1, caps=True)

    # ---------- the glasshouse ----------
    def gkeys(self, x):
        zg = self.belt(x) + 0.004
        bw = 0.885 * self.width(x)
        rw = min(self.roof_w(x), bw - 0.02)
        h = max(0.003, self.roof(x) - zg)
        edge = min(0.035, h * 0.4)
        return [(bw, zg), (lerp(bw, rw, 0.45) + 0.012 * min(1.0, h / 0.2), zg + 0.45 * (h - edge)), (rw, zg + h - edge),
                (0.55 * rw, zg + h - min(0.006, h * 0.1)), (0.0, zg + h)]

    def ghalf(self, x):
        key = ("g", round(x, 4))
        if key not in self._half:
            self._half[key] = spline(self.gkeys(x), self.L["glass"])
        return self._half[key]

    def gring(self, x):
        h = self.ghalf(x)
        return h + [(-y, z) for y, z in reversed(h[:-1])]

    def gseg(self, j):
        m = self.gbounds[-1]
        jj = j if j < m else 2 * m - j - 1
        return bisect.bisect_right(self.gbounds, jj) - 1, jj

    def glass_z(self, x, y):
        """The glasshouse's top at (x, y) (from its roof's edge in), or None."""
        h = self.ghalf(x)
        y = abs(y)
        for i in range(self.gbounds[1], len(h) - 1):
            (y1, z1), (y2, z2) = h[i], h[i + 1]
            if min(y1, y2) <= y <= max(y1, y2) and y1 != y2:
                return z1 + (z2 - z1) * (y - y1) / (y2 - y1)
        return None

    def window_edges(self, x, z):
        """The side window's front and back edges (x) at height z, and how far up the window z is (0 to 1)."""
        g = self.c["glass"]
        (a0, a1), (c0, c1) = g["side"]
        k = self.gkeys(x)
        t = max(0.0, min(1.0, (z - k[0][1]) / max(1e-6, k[2][1] - k[0][1])))
        return lerp(a0, a1, t), lerp(c0, c1, t), t

    def greenhouse(self):
        c, L = self.c, self.L
        g = c["glass"]
        dx = L["dx"]
        (a0, a1), (c0, c1) = g["side"]
        bp = g["b_pillar"]
        extra = [g["ws_top"], g["roof_rear"], a0, a1, c0, c1] + ([bp[0] - bp[1] / 2, bp[0] + bp[1] / 2] if bp else [])
        xs = stations(self.grear, self.gbase, dx, extra)
        rows = [[(x, y, z) for y, z in self.gring(x)] for x in xs]

        # the side windows' slanting edges (and a B pillar's): the points moved onto them where the grid crosses
        def window(p):
            xa, xc, _ = self.window_edges(p[0], p[2])
            f = max(p[0] - xa, xc - p[0])
            return max(f, bp[1] / 2 - abs(p[0] - bp[0])) if bp else f

        def side(r, j):
            s_, jj_ = self.gseg(min(j, len(rows[r]) - 2))
            return s_ <= 1 and 0 < j < len(rows[r]) - 1
        snap_crossings(rows, window, side)
        glass = "windows window" if self.high else "windows glass"
        roof = "roof " + c["roof_role"]
        lining = "roof lining interior" if L["cabin"] else None

        def classify(r, j):
            s, jj = self.gseg(j)
            quad = [rows[r][j], rows[r][j + 1], rows[r + 1][j + 1], rows[r + 1][j]]
            cx = sum(p[0] for p in quad) / 4
            cz = sum(p[2] for p in quad) / 4
            if s <= 1:  # the side: a window between its edges (and either side of a B pillar), a seal under and over
                if window((cx, 0.0, cz)) < 0:
                    return glass if jj not in (0, self.gbounds[2] - 1) else ("window trim carbon", lining)
                return ("pillars " + ("carbon" if bp and abs(cx - bp[0]) < bp[1] / 2 else "paint"), lining)
            ws, rear = cx > g["ws_top"], cx < g["roof_rear"]
            if ws or rear:  # the windscreen or the back window, a pillar and trim at each side
                if jj == self.gbounds[2]:
                    return (roof if ws else "pillars paint", lining)
                if jj == self.gbounds[2] + 1:
                    return ("window trim carbon", lining)
                return glass
            return (roof, lining)
        emit(self.parts, rows, lambda p: (max(self.grear + 0.1, min(self.gbase - 0.1, p[0])), 0.0,
                                          self.belt(p[0]) - 0.1), classify, wrap=False)



    # ---------- shapes on the body's faces ----------
    def face_point(self, face, u, v, off):
        """A point off the body's face: front (u = y, v = z), rear (the same), side (u = x, v = z, the left side),
        top (u = x, v = y) or glass (the glasshouse's top: u = x, v = y); off metres out from it. None if the face
        isn't there."""
        if face == "front":
            x = self.front_x(u, v)
            return None if x is None else (x + off, u, v)
        if face == "rear":
            x = self.rear_x(u, v)
            return None if x is None else (x - off, u, v)
        if face == "side":
            y = self.side_y(u, v)
            return None if y is None else (u, y + off, v)
        if face == "top":
            z = self.top_z(u, v)
            return None if z is None else (u, v, z + off)
        z = self.glass_z(u, v)
        return None if z is None else (u, v, z + off)

    OUT = {"front": (1.0, 0.0, 0.0), "rear": (-1.0, 0.0, 0.0), "side": (0.0, 1.0, 0.0), "top": (0.0, 0.0, 1.0),
           "glass": (0.0, 0.0, 1.0)}

    def patch(self, name, face, uc, vc, uh, vh, off=0.003, e=6.0, n=(8, 4), mirror=False):
        """A rounded rectangle lying on a face (centre (uc, vc), half sizes uh and vh, squareness e), off metres
        out from it: a grille's opening, a plate, a vent. mirror: its twin on the right too."""
        nu, nv = n if self.high else (max(2, n[0] // 3), max(1, n[1] // 2))
        for side in ((1, -1) if mirror else (1,)):
            rows = []
            for i in range(nv + 1):
                t = -1 + 2 * i / nv
                row = []
                for k in range(nu + 1):
                    s = -1 + 2 * k / nu
                    m, r = max(abs(s), abs(t)), (abs(s) ** e + abs(t) ** e) ** (1 / e)
                    ss, tt = (s * m / r, t * m / r) if r > 0 else (0.0, 0.0)
                    p = self.face_point(face, uc + ss * uh, vc + tt * vh, off)
                    if p is not None and side < 0:
                        p = (p[0], -p[1], p[2])
                    row.append(p)
                rows.append(row)
            if any(p is None for row in rows for p in row):
                continue  # (off the body: left out)
            out = self.OUT[face]
            if side < 0:
                out = (out[0], -out[1], out[2])
            emit(self.parts, rows, lambda p, out=out: sub(p, mul(out, 0.2)), lambda r, j: name, wrap=False)

    def bars(self, name, face, uc, vc, uh, vh, count, radius, off=0.004, across=True, n=10):
        """Bars across (or up) an opening on a face, following its curve: a grille's slats."""
        part = self.parts.get(name)
        for i in range(count):
            f = -1 + 2 * (i + 0.5) / count
            path = []
            for k in range(n + 1):
                g = -1 + 2 * k / n
                u, v = (uc + g * uh, vc + f * vh) if across else (uc + f * uh, vc + g * vh)
                p = self.face_point(face, u, v, off)
                if p is not None:
                    path.append(p)
            if len(path) > 1:
                km.tube(part, path, radius, seg=6 if self.high else 4, steps=1)

    # ---------- the wheel and its brake ----------
    def spoke(self, part, a, r0, r1, w0, w1, thick, ydish, branch=0.0):
        """One spoke across the wheel's face (the wheel's plane: x and z; its axle y), from radius r0 to r1 at angle
        a (radians from +x towards +z), widening from w0 to w1, sunk into the dish by ydish(r)."""
        steps = 7 if self.high else 3
        seg = 8 if self.high else 4
        rows, centres = [], []
        for k in range(steps + 1):
            f = k / steps
            r = lerp(r0, r1, f)
            aa = a + branch * f
            c = (r * math.cos(aa), ydish(r), r * math.sin(aa))
            t = (-math.sin(aa), 0.0, math.cos(aa))
            hw = lerp(w0, w1, f)
            row = []
            for j in range(seg + 1):
                th = 2 * math.pi * j / seg
                p = add(c, add(mul(t, hw * spow(math.cos(th), 0.5)), (0.0, thick * spow(math.sin(th), 0.5), 0.0)))
                row.append(p)
            rows.append(row)
            centres.append(c)
        emit(self.parts_wheel, rows, lambda p: min(centres, key=lambda q: math.dist(p, q)), lambda r, j: part)

    def wheel(self):
        """One wheel at the origin, its axle along +y, its outer face at +y."""
        c = self.c
        self.parts_wheel = pw = Parts()
        n = self.L["wheel"]
        R, Rr, W = self.R, self.rim_r, self.tw
        tyre = pw.get("tyre tyre")
        prof = [(Rr + 0.004, -W + 0.024), (Rr + 0.02, -W - 0.002), (lerp(Rr, R, 0.55), -W - 0.008),
                (R - 0.03, -W - 0.002), (R - 0.01, -W + 0.012)]
        tread = [(R, -W + 0.03)]
        if self.high:  # four grooves round the tread
            for gy in (-0.55, -0.18, 0.18, 0.55):
                y = gy * W
                tread += [(R, y - 0.009), (R - 0.008, y - 0.006), (R - 0.008, y + 0.006), (R, y + 0.009)]
        tread.append((R, W - 0.03))
        prof += tread + [(R - 0.01, W - 0.012), (R - 0.03, W + 0.002), (lerp(Rr, R, 0.55), W + 0.008),
                         (Rr + 0.02, W + 0.002), (Rr + 0.004, W - 0.024)]
        km.lathe(tyre, prof, seg=n)
        role = c["rim_role"]
        rim = pw.get("rim " + role, role)
        km.lathe(rim, [(Rr + 0.004, W - 0.024), (Rr + 0.012, W - 0.012), (Rr + 0.006, W - 0.003),
                       (Rr - 0.012, W - 0.006), (Rr - 0.02, W - 0.018)], seg=n)
        barrel = pw.get("barrel metal", "metal")
        km.lathe(barrel, [(Rr - 0.02, W - 0.018), (Rr - 0.02, -W + 0.03)], seg=n)
        km.disc(pw.get("wheel back liner", "liner"), -W + 0.03, Rr - 0.02, 0.0, 1, seg=n // 2)
        # the spokes: sunk into a dish between the hub and the lip
        r0, r1 = 0.07, Rr - 0.016

        def dish(r):
            return W - 0.014 - 0.03 * math.sin(math.pi * (r - r0) / (r1 - r0))
        style = c["rim"]
        if style == "split":
            for i in range(5):
                for d in (-1, 1):
                    self.spoke(rim.name, 2 * math.pi * i / 5 + d * 0.11, r0, r1, 0.011, 0.014, 0.011, dish,
                               branch=d * 0.05)
        elif style == "y":
            for i in range(5):
                a = 2 * math.pi * i / 5
                self.spoke(rim.name, a, r0, lerp(r0, r1, 0.5), 0.02, 0.018, 0.013, dish)
                for d in (-1, 1):
                    self.spoke(rim.name, a, lerp(r0, r1, 0.45), r1, 0.011, 0.012, 0.011, dish, branch=d * 0.2)
        elif style == "rally":
            for i in range(6):
                self.spoke(rim.name, 2 * math.pi * i / 6, r0, r1, 0.02, 0.03, 0.014, dish)
        else:
            for i in range(5):
                self.spoke(rim.name, 2 * math.pi * i / 5, r0, r1, 0.02, 0.028, 0.016, dish)
        km.lathe(rim, [(r0 + 0.012, W - 0.03), (r0 + 0.008, W - 0.014), (0.05, W - 0.006), (0.0, W - 0.004)],
                 seg=max(16, n // 3))
        if self.high:  # the wheel nuts and the centre badge, then the brake disc behind the spokes and its hat
            nuts = pw.get("wheel nuts chrome")
            for i in range(5):
                a = 2 * math.pi * i / 5 + math.pi / 5
                p = (0.045 * math.cos(a), W - 0.006, 0.045 * math.sin(a))
                km.superellipsoid(nuts, p, (0.009, 0.006, 0.009), e=2.6, seg=8, rings=4)
            km.disc(pw.get("badge chrome"), W - 0.002, 0.022, 0.0, 1, seg=16)
            disc = pw.get("brake disc")
            dy = W - 0.095
            ro, ri = Rr - 0.035, 0.105
            km.disc(disc, dy + 0.014, ro, ri, 1, seg=n // 2)
            km.disc(disc, dy - 0.014, ro, ri, -1, seg=n // 2)
            km.lathe(disc, [(ro, dy - 0.014), (ro, dy + 0.014)], seg=n // 2)
            hat = pw.get("disc hat metal", "metal")
            km.lathe(hat, [(ri, dy + 0.014), (ri - 0.01, dy + 0.03), (0.07, W - 0.03), (0.0, W - 0.03)], seg=24)
        return pw.list()

    def brake(self):
        """A brake caliper at the back of each disc, as the left and right wheels' (the right the mirror image)."""
        out = {}
        Rr, W = self.rim_r, self.tw
        dy = W - 0.095
        for side, key in ((1, "left"), (-1, "right")):
            parts = Parts()
            cal = parts.get("caliper caliper")
            rc = Rr - 0.05
            rows, centres = [], []
            for k in range(9):
                a = math.radians(125 + 50 * k / 8)
                cc = (rc * math.cos(a), side * dy, rc * math.sin(a))
                out_ = (math.cos(a), 0.0, math.sin(a))
                row = []
                for j in range(13):
                    th = 2 * math.pi * j / 12
                    p = add(cc, add(mul(out_, 0.032 * spow(math.cos(th), 0.4)), (0.0, side * (0.006 + 0.03 * spow(math.sin(th), 0.4)), 0.0)))
                    row.append(p)
                rows.append(row)
                centres.append(cc)
            emit(parts, rows, lambda p: min(centres, key=lambda q: math.dist(p, q)), lambda r, j: "caliper caliper")
            out[key] = scaled(parts.list())
        return out

    # ---------- lamps, grilles, plates ----------
    def lamp_spot(self, which):
        """Where a lamp is on the body's skin: (x, y, z), its width and height, the way it faces round z (degrees)."""
        y, z, w, h = self.c["lamps"][which]
        f = self.front_x if which == "head" else self.rear_x
        x = f(y, z)
        x1, x2 = f(y + 0.02, z), f(y - 0.02, z)
        slope = (x1 - x2) / 0.04 if x1 is not None and x2 is not None else 0.0
        turn = math.degrees(math.atan2(-slope, 1.0)) if which == "head" else math.degrees(math.atan2(slope, 1.0))
        return (x, y, z), w, h, turn

    def lamps(self):
        """The lamps lying on the body's face: a dark housing; on high a chrome reflector for each lamp, a running
        light along its bottom, and a clear cover over them (the tail lamps a red one over a silver reflector)."""
        for which, face in (("head", "front"), ("tail", "rear")):
            y, z, w, h = self.c["lamps"][which]
            self.patch("lamp housings carbon", face, y, z, w / 2 + 0.012, h / 2 + 0.01, off=0.004, e=5.0, n=(12, 4),
                       mirror=True)
            if not self.high:
                continue
            if which == "head":
                for d in (-0.24, 0.2):
                    self.patch("reflectors chrome", face, y + d * w, z + h * 0.06, h * 0.36, h * 0.36, off=0.008, e=2.2,
                               n=(8, 8), mirror=True)
                self.patch("running lights drl", face, y, z - h * 0.4, w * 0.46, 0.0055, off=0.009, e=8.0, n=(10, 1),
                           mirror=True)
                self.patch("lamp covers lens", face, y, z, w / 2 + 0.006, h / 2 + 0.005, off=0.015, e=5.0, n=(14, 5),
                           mirror=True)
            else:
                self.patch("tail reflectors lamp_red", face, y, z, w * 0.47, h * 0.38, off=0.007, e=6.0, n=(10, 3),
                           mirror=True)
                self.patch("tail lenses lens_red", face, y, z, w / 2 + 0.006, h / 2 + 0.005, off=0.014, e=6.0,
                           n=(14, 4), mirror=True)

    def grille(self):
        c = self.c
        gw, gz, gh = c["grille"]
        iw, iz, ih = c["intake"]
        self.patch("grille gap", "front", 0.0, gz, gw, gh, off=0.006, e=4.0, n=(16, 6))
        self.patch("intake gap", "front", 0.0, iz, iw, ih, off=0.006, e=5.0, n=(16, 4))
        if self.high:
            self.bars("grille bars carbon", "front", 0.0, gz, gw * 0.92, gh * 0.8, 5 if gh > 0.08 else 3, 0.005, off=0.01)
            self.bars("grille bars carbon", "front", 0.0, gz, gw * 0.92, gh * 0.8, 11, 0.004, off=0.009, across=False, n=4)
            self.bars("intake mesh carbon", "front", 0.0, iz, iw * 0.94, ih * 0.75, 3, 0.004, off=0.009)
            self.patch("grille surround chrome" if c["rim"] == "muscle" else "grille surround carbon", "front", 0.0,
                       gz - gh - 0.008, gw, 0.006, off=0.004, e=8.0, n=(12, 1))
        # the number plates: white on the front, yellow at the back (as in Britain), with dark letters
        pz = (gz - gh + iz + ih) / 2 if gz - gh - (iz + ih) > 0.13 else iz
        rz = self.c["lamps"]["tail"][1] - 0.24
        for face, z, role in (("front", pz, "plate"), ("rear", rz, "plate_rear")):
            self.patch(f"{face} plate {role}", face, 0.0, z, 0.26, 0.056, off=0.012, e=10.0, n=(6, 2))
            if self.high:
                for i in range(7):
                    if i == 4:
                        continue
                    self.patch(f"{face} plate letters gap", face, -0.2 + i * 0.064, z, 0.017, 0.03, off=0.0135,
                               e=8.0, n=(2, 2))

    # ---------- what the car's notes give the drawers ----------
    def notes(self, parts_all):
        c, S = self.c, SCALE
        (hx, hy, hz), hw, hh, _ = self.lamp_spot("head")
        (tx, ty, tz), tw_, th, _ = self.lamp_spot("tail")
        fx, rx = c["axles"]
        if c["engine"] == "middle":
            smoke = (rx + 0.6, 0.0, self.top(rx + 0.6) + 0.02)
        else:
            smoke = (fx - 0.35, 0.0, self.top(fx - 0.35) + 0.02)
        ez = c["exhausts"][0][1]
        hood_x = self.gbase + 0.32
        top = max(max(p["positions"][2::3]) for p in parts_all)
        sx = (self.c["nose"] - 0.12) * S
        return {"nose": {"pivot": [round(sx, 4), round(0.86 * self.width(c["nose"] - 0.12) * S, 4),
                                   round((self.bottom(c["nose"] - 0.12) - 0.01) * S, 4)],
                         "about": "the front splitter hangs from its left end as the front wing is damaged"},
                "lamps": {"head": [round((hx - 0.006) * S, 4), round(hy * S, 4), round(hz * S, 4)],
                          "tail": [round((tx + 0.006) * S, 4), round(ty * S, 4), round(tz * S, 4)],
                          "size": [round(hw * S * 0.8, 4), round(hh * S * 0.7, 4)],
                          "tail_size": [round(tw_ * S * 0.8, 4), round(th * S * 0.7, 4)]},
                "smoke": [round(v * S, 4) for v in smoke],
                "glow": [round((c["tail"] - 0.18) * S, 4), 0.0, round(ez * S, 4)],
                "hood": [round(hood_x * S, 4), round((self.top(hood_x) + 0.16) * S, 4)],
                "height": round(top, 3),
                "wheel_radius": round(self.R * S, 4),
                "title": TITLES[self.name], "roles": ROLES,
                "lod": {"far": 22.0, "about": "ultra draws car_ultra's model while the car is nearer the camera "
                                              "than this (metres), car's beyond it"}}

    # ---------- the details ----------
    def details(self):
        c, P, hi = self.c, self.parts, self.high
        ex = c["extras"]
        seg = 16 if hi else 8
        g = c["glass"]
        # the exhausts: polished tips, dark inside, out of a diffuser under the tail
        for y, z, r in c["exhausts"]:
            x = self.rear_x(y, z)
            if x is None:
                continue
            km.tube(P.get("exhausts chrome"), [(x + 0.06, y, z), (x - 0.035, y, z)], r, seg=seg, steps=1, caps=False)
            km.superellipsoid(P.get("exhaust insides gap"), (x - 0.03, y, z), (0.004, r * 0.88, r * 0.88), e=2.0,
                              seg=seg, rings=4)
        zb = self.bottom(c["tail"] + 0.15)
        self.patch("diffuser carbon", "rear", 0.0, zb + 0.06, 0.62 * self.width(c["tail"]), 0.055, off=0.003, e=6.0,
                   n=(14, 3))
        if hi:
            for k in range(-3, 4):
                y = k * 0.12
                if any(abs(y - ey) < er + 0.03 for ey, _, er in c["exhausts"]):
                    continue
                x = self.rear_x(y, zb + 0.06)
                if x is not None:
                    km.superellipsoid(P.get("diffuser fins carbon"), (x + 0.1, y, zb + 0.03), (0.13, 0.006, 0.05),
                                      e=6, seg=8, rings=4)
        # the door mirrors: on a stalk at the side window's front corner
        a0 = g["side"][0][0]
        zm = self.belt(a0) + 0.1
        ym = self.side_y(a0 - 0.05, self.belt(a0) - 0.02) or self.width(a0)
        for side in (1, -1):
            hx, hy = a0 - 0.08, side * (ym + 0.075)
            km.superellipsoid(P.get("mirrors " + ("paint" if c["roof_role"] == "paint" else "carbon")),
                              (hx, hy, zm), (0.06, 0.04, 0.04), e=3.2, seg=seg, rings=8 if hi else 4)
            if hi:
                km.superellipsoid(P.get("mirror glass chrome"), (hx - 0.058, hy, zm), (0.004, 0.033, 0.033), e=4,
                                  seg=12, rings=4)
                km.tube(P.get("mirror stalks carbon"), [(a0 - 0.03, side * (ym - 0.02), zm - 0.03), (hx + 0.02, hy * 0.97, zm - 0.02)],
                        0.012, seg=8, steps=1)
        if hi:
            # the door handles, the wipers, the aerial
            for seam in c["seams"][1:2]:
                for side in (1, -1):
                    hz = self.belt(seam) - 0.07
                    y = self.side_y(seam + 0.16, hz)
                    if y is not None:
                        km.superellipsoid(P.get("door handles chrome"), (seam + 0.16, side * (y + 0.002), hz),
                                          (0.065, 0.006, 0.011), e=5, seg=12, rings=4)
            wx = self.gbase - 0.08
            for y0, y1 in ((-0.62, 0.05), (0.02, 0.6)):
                path = []
                for k in range(9):
                    y = lerp(y0, y1, k / 8)
                    xx = wx - 0.06 * k / 8
                    z = self.glass_z(xx, y)
                    if z is not None:
                        path.append((xx, y, z + 0.012))
                if len(path) > 2:
                    km.tube(P.get("wipers carbon"), path, 0.007, seg=6, steps=1)
            if "fin" in ex:
                xr = g["roof_rear"] + 0.1
                zr = self.glass_z(xr, 0.0)
                if zr:
                    km.superellipsoid(P.get("aerial carbon"), (xr, 0.0, zr + 0.022), (0.075, 0.02, 0.03), e=2.4,
                                      seg=12, rings=6, tilt=-8)
        # each car's own
        if "ducktail" in ex:
            x = c["tail"] + 0.14
            km.superellipsoid(P.get("ducktail paint"), (x, 0.0, self.top(x) - 0.006), (0.12, 0.8 * self.width(x), 0.026),
                              e=4.5, seg=seg * 2, rings=6 if hi else 3, tilt=8)
        if "gills" in ex:
            fx = c["axles"][0] - self.arch_r - 0.12
            for k in range(3):
                self.patch("gills gap", "side", fx - k * 0.06, self.belt(fx) - 0.12, 0.012, 0.07, off=0.002, e=4,
                           n=(2, 6), mirror=True)
        if "wing" in ex:
            x0 = c["tail"] + 0.45
            zt = self.top(x0)
            wing = P.get("rear wing carbon")
            km.aerofoil(wing, x0, zt + 0.24, 0.34, 0.82, 9.0, thick=0.1, seg=20 if hi else 10)
            for side in (1, -1):
                km.tube(P.get("wing posts carbon"), [(x0 - 0.12, side * 0.42, zt - 0.02), (x0 - 0.16, side * 0.42, zt + 0.22)],
                        0.018, seg=8, steps=1)
                km.superellipsoid(P.get("wing plates carbon"), (x0 - 0.17, side * 0.83, zt + 0.25), (0.2, 0.006, 0.09),
                                  e=6, seg=12, rings=4)
        if "side_intakes" in ex:
            x, z = c["axles"][1] + self.arch_r + 0.26, self.belt(c["axles"][1]) - 0.2
            self.patch("side intakes gap", "side", x, z, 0.24, 0.13, off=0.002, e=3.5, n=(10, 6), mirror=True)
            if hi:
                for k in range(3):
                    self.patch("intake strakes paint", "side", x, z - 0.08 + k * 0.08, 0.22, 0.008, off=0.012,
                               e=6, n=(8, 1), mirror=True)
        if "rear_mesh" in ex:  # (a mesh grille across the back between the tail lamps)
            z = c["lamps"]["tail"][1] - 0.14
            self.patch("rear grille gap", "rear", 0.0, z, 0.62, 0.08, off=0.005, e=5.0, n=(16, 4))
            if hi:
                self.bars("rear grille mesh carbon", "rear", 0.0, z, 0.58, 0.065, 4, 0.004, off=0.008)
                self.bars("rear grille mesh carbon", "rear", 0.0, z, 0.58, 0.065, 14, 0.004, off=0.007, across=False, n=4)
        if "louvres" in ex:
            for k in range(5):
                x = c["tail"] + 0.45 + k * 0.1
                self.patch("louvres gap", "top", x, 0.0, 0.025, 0.42, off=0.002, e=6, n=(2, 8))
        if "bonnet_vents" in ex:
            for side in (1, -1):
                self.patch("bonnet vents gap", "top", c["axles"][0] + 0.05, side * 0.36, 0.18, 0.11, off=0.002, e=3,
                           n=(6, 4))
        if "roof_scoop" in ex:
            x = g["ws_top"] - 0.12
            z = self.glass_z(x, 0.0)
            km.superellipsoid(P.get("roof scoop carbon"), (x, 0.0, z + 0.03), (0.14, 0.12, 0.045), e=3.5, seg=seg,
                              rings=6, tilt=-4)
            km.superellipsoid(P.get("scoop mouth gap"), (x + 0.12, 0.0, z + 0.035), (0.03, 0.095, 0.025), e=4, seg=12,
                              rings=4)
        if "roof_wing" in ex:
            x0 = g["roof_rear"] + 0.08
            z = self.glass_z(x0 - 0.05, 0.0) or self.roof(x0)
            km.aerofoil(P.get("roof wing carbon"), x0, z + 0.03, 0.34, 0.66, 4.0, thick=0.09, seg=20 if hi else 10)
            for side in (1, -1):
                km.superellipsoid(P.get("roof wing plates carbon"), (x0 - 0.18, side * 0.67, z + 0.02),
                                  (0.2, 0.006, 0.06), e=6, seg=12, rings=4)
        if "flaps" in ex:
            for x, y in self.wheel_spots():
                side = 1 if y > 0 else -1
                km.superellipsoid(P.get("mud flaps liner"), (x - self.arch_r - 0.02, y, self.bottom(x) - 0.03),
                                  (0.006, self.tw + 0.02, 0.12), e=6, seg=8, rings=4)
        if "spots" in ex:
            gw, gz, gh = c["grille"]
            for k in (-1.5, -0.5, 0.5, 1.5):
                y = k * 0.17
                x = self.front_x(y, gz) or c["nose"]
                p = (x + 0.06, y, gz + 0.02)
                km.superellipsoid(P.get("spot lamps carbon"), p, (0.04, 0.075, 0.075), e=2.2, seg=seg, rings=8)
                km.superellipsoid(P.get("spot lenses " + ("lens" if hi else "light")), add(p, (0.035, 0.0, 0.0)),
                                  (0.012, 0.064, 0.064), e=2.0, seg=seg, rings=6)
            if hi:
                km.tube(P.get("spot bar chrome"), [(c["nose"] + 0.02, -0.34, gz - 0.06), (c["nose"] + 0.02, 0.34, gz - 0.06)],
                        0.012, seg=8, steps=1)
        if "tow" in ex and hi:
            for face, y in (("front", -0.4), ("rear", 0.4)):
                z = c["intake"][1] - 0.04
                f = self.front_x if face == "front" else self.rear_x
                x = f(y, z)
                if x is not None:
                    d = 1 if face == "front" else -1
                    km.tube(P.get("tow straps caliper"), [(x - d * 0.01, y, z), (x + d * 0.05, y, z + 0.02), (x + d * 0.03, y, z + 0.07)],
                            0.012, seg=6, steps=2)
        if "hood_scoop" in ex:
            x = c["axles"][0] - 0.25
            z = self.top(x)
            km.superellipsoid(P.get("bonnet scoop paint"), (x, 0.0, z), (0.32, 0.2, 0.06), e=3.5, seg=seg, rings=8,
                              tilt=-3)
            km.superellipsoid(P.get("scoop mouth gap"), (x + 0.28, 0.0, z + 0.025), (0.04, 0.16, 0.025), e=4, seg=12,
                              rings=4)
        if "stripes" in ex:
            for side in (1, -1):
                y = side * 0.14
                for face, x0, x1 in (("top", c["tail"] + 0.04, self.grear - 0.02), ("top", self.gbase + 0.02, c["nose"] - 0.05),
                                     ("glass", g["roof_rear"] + 0.02, g["ws_top"] - 0.02)):
                    self.patch("stripes stripe", face, (x0 + x1) / 2, y, (x1 - x0) / 2, 0.055, off=0.0025, e=12,
                               n=(30, 2))
        if "chrome_bumpers" in ex:
            iz = c["intake"][1]
            self.bars("bumpers chrome", "front", 0.0, iz + c["intake"][2] + 0.03, 0.9 * self.width(c["nose"]), 0.0, 1,
                      0.018, off=0.01, n=14)
            self.bars("bumpers chrome", "rear", 0.0, self.bottom(c["tail"]) + 0.1, 0.92 * self.width(c["tail"]), 0.0, 1,
                      0.02, off=0.01, n=14)

    # ---------- the cabin: seen through the glass ----------
    def cabin(self):
        c, P = self.c, self.parts
        g = c["glass"]
        x0, x1 = self.grear + 0.06, self.gbase - 0.04
        dx_, dy_ = c["driver"]
        fz = max(self.bottom(dx_) + 0.12, 0.2)
        # the floor, the dashboard under the windscreen, a wall behind the seats, a shelf over it
        rows = []
        for k in range(9):
            x = lerp(x0, x1, k / 8)
            w = (self.side_y(x, fz + 0.05) or self.width(x)) - 0.03
            rows.append([(x, -w + 2 * w * j / 6, fz) for j in range(7)])
        emit(P, rows, lambda p: (p[0], p[1], fz - 1.0), lambda r, j: "cabin floor interior", wrap=False)
        xd = self.gbase - 0.24
        zbelt = self.belt(xd)
        km.superellipsoid(P.get("dashboard interior"), (xd, 0.0, zbelt - 0.06), (0.26, 0.86 * self.width(xd), 0.11), e=4,
                          seg=28, rings=10)
        km.superellipsoid(P.get("dashboard interior"), (xd - 0.15, dy_, zbelt + 0.03), (0.09, 0.17, 0.05), e=3, seg=16,
                          rings=6)  # (the instruments' hood)
        km.superellipsoid(P.get("screens drl"), (xd - 0.08, 0.0, zbelt + 0.02), (0.004, 0.09, 0.05), e=8, seg=8, rings=4,
                          tilt=-20)
        xb = max(x0 + 0.05, dx_ - 0.42)
        km.superellipsoid(P.get("cabin back interior"), (xb, 0.0, (fz + self.belt(xb)) / 2),
                          (0.06, 0.88 * self.width(xb), (self.belt(xb) - fz) / 2 + 0.02), e=6, seg=24, rings=8)
        if x0 < xb - 0.1:
            rows = []
            for k in range(6):
                x = lerp(x0, xb, k / 5)
                w = 0.86 * self.width(x)
                rows.append([(x, -w + 2 * w * j / 6, self.belt(x) - 0.03) for j in range(7)])
            emit(P, rows, lambda p: (p[0], p[1], p[2] - 1.0), lambda r, j: "parcel shelf interior", wrap=False)
        km.superellipsoid(P.get("console interior"), (dx_ + 0.3, 0.0, fz + 0.12), (0.35, 0.08, 0.12), e=4, seg=16, rings=6)
        # the seats, the steering wheel, the driver in a helmet
        for y in (dy_, -dy_):
            km.superellipsoid(P.get("seats seat"), (dx_ + 0.04, y, fz + 0.12), (0.24, 0.22, 0.06), e=3.5, seg=16, rings=8)
            km.superellipsoid(P.get("seats seat"), (dx_ - 0.2, y, fz + 0.45), (0.07, 0.22, 0.33), e=3.5, seg=16, rings=8,
                              tilt=14)
            for d in (-1, 1):
                km.superellipsoid(P.get("seat bolsters seat"), (dx_ - 0.15, y + d * 0.2, fz + 0.36), (0.1, 0.045, 0.22),
                                  e=2.8, seg=12, rings=6, tilt=14)
        sw = (dx_ + 0.52, dy_, self.belt(dx_ + 0.52) - 0.02)
        axis = norm((-math.cos(math.radians(28)), 0.0, math.sin(math.radians(28))))
        up = norm(cross(axis, (0.0, 1.0, 0.0)))
        rim, rr, r = P.get("steering wheel carbon"), 0.17, 0.016
        rows = []
        for i in range(29):
            t = 2 * math.pi * i / 28
            cc = add(sw, add(mul((0.0, 1.0, 0.0), rr * math.cos(t)), mul(up, rr * math.sin(t))))
            out = norm(sub(cc, sw))
            rows.append([add(cc, add(mul(out, r * math.cos(2 * math.pi * j / 8)), mul(axis, r * math.sin(2 * math.pi * j / 8))))
                         for j in range(9)])
        emit(P, rows, lambda p: add(sw, mul(norm(sub(sub(p, sw), mul(axis, dot(sub(p, sw), axis)))), rr)),
             lambda r_, j: "steering wheel carbon")
        km.tube(P.get("steering wheel carbon"), [add(sw, mul(axis, -0.02)), add(sw, mul(axis, -0.25))], 0.025, seg=8, steps=1)
        km.superellipsoid(P.get("driver dark"), (dx_ - 0.12, dy_, fz + 0.44), (0.14, 0.19, 0.27), e=2.6, seg=16, rings=10,
                          tilt=12)
        helmet = (dx_ - 0.13, dy_, fz + 0.84)
        roof = self.glass_z(helmet[0], helmet[1])
        if roof is not None and helmet[2] + 0.15 > roof - 0.02:
            helmet = (helmet[0], helmet[1], roof - 0.17)
        km.superellipsoid(P.get("helmet helmet"), helmet, (0.15, 0.135, 0.14), e=2.0, seg=20, rings=12)
        km.superellipsoid(P.get("visor glass"), add(helmet, (0.075, 0.0, 0.0)), (0.08, 0.115, 0.05), e=2.6, seg=14, rings=6)
        km.tube(P.get("neck skin"), [(helmet[0], dy_, fz + 0.62), (helmet[0], dy_, helmet[2] - 0.08)], 0.05, seg=10, steps=1)
        for d in (-1, 1):
            hand = add(sw, mul((0.0, 1.0, 0.0), d * rr * 0.98))
            km.tube(P.get("arms dark"), [(dx_ - 0.1, dy_ + d * 0.17, fz + 0.62), (dx_ + 0.12, dy_ + d * 0.22, fz + 0.48), hand],
                    [0.045, 0.04, 0.035], seg=10, steps=4)
            km.superellipsoid(P.get("gloves dark"), hand, (0.04, 0.035, 0.045), e=2.2, seg=10, rings=6)

    def nose(self):
        """The front splitter under the nose (its own parts: it hangs as the front wing is damaged)."""
        parts = Parts()
        c = self.c
        x = c["nose"] - 0.12
        w = 0.86 * self.width(x)
        km.superellipsoid(parts.get("splitter carbon"), (x, 0.0, self.bottom(x) - 0.012), (0.13, w, 0.011), e=6,
                          seg=24 if self.high else 10, rings=6 if self.high else 3)
        return parts.list()


# ---------- putting a car together ----------
def scaled(parts, k=SCALE):
    """Parts as dicts, k times their size (the normals stay: the shape is only larger)."""
    out = []
    for p in parts:
        d = p if isinstance(p, dict) else p.as_dict()
        q = dict(d)
        q["positions"] = [round(v * k, 4) + 0.0 for v in d["positions"]]
        out.append(q)
    return out


def merged(parts):
    """Parts with the same role as one part each (fewer for the drawers to handle)."""
    by = {}
    for p in parts:
        by.setdefault(p["role"], []).append(p)
    out = []
    for role, ps in by.items():
        q = {"name": role, "role": role, "positions": [], "normals": [], "indices": [], "uvs": []}
        for p in ps:
            base = len(q["positions"]) // 3
            q["positions"] += p["positions"]
            q["normals"] += p["normals"]
            q["uvs"] += p["uvs"]
            q["indices"] += [i + base for i in p["indices"]]
        out.append(q)
    return out


def build(name, level):
    """The car at this level of detail: its model as the drawers read it (see the top of this file)."""
    car = Car(name, level)
    car.body()
    car.greenhouse()
    car.lamps()
    car.grille()
    car.details()
    if car.high:
        car.cabin()
    body = merged(scaled(car.parts.list()))
    nose = merged(scaled(car.nose()))
    wheel = merged(scaled(car.wheel()))
    wheels = [{"x": round(x * SCALE, 4), "y": round(y * SCALE, 4), "z": round(car.R * SCALE, 4), "front": x > 0,
               "side": 1 if y > 0 else -1} for x, y in car.wheel_spots()]
    out = {"version": VERSION, "name": name, "body": body, "nose": nose, "wheel": wheel, "wheels": wheels}
    extra = []
    if car.high:
        out["brake"] = {k: merged(v) for k, v in car.brake().items()}
        extra = out["brake"]["left"]
    tris = (sum(len(p["indices"]) // 3 for p in body + nose) + 4 * sum(len(p["indices"]) // 3 for p in wheel + extra))
    out["notes"] = car.notes(body)
    out["notes"]["triangles"] = tris
    return out


_CACHE = {}


def car(name):
    """The car as every tier draws it (and ultra beyond notes["lod"]["far"])."""
    if ("low", name) not in _CACHE:
        _CACHE[("low", name)] = build(name, "low")
    return _CACHE[("low", name)]


def car_ultra(name):
    """The car as ultra draws it near the camera."""
    if ("high", name) not in _CACHE:
        _CACHE[("high", name)] = build(name, "high")
    return _CACHE[("high", name)]


def cars():
    """Every car, as models/cars.json holds them."""
    return {"version": VERSION, "bodies": {name: car(name) for name in CARS}}


if __name__ == "__main__":
    import time
    for name in CARS:
        for level in ("low", "high"):
            t = time.perf_counter()
            m = build(name, level)
            print(f"{name:9s} {level:5s} {m['notes']['triangles']:7d} triangles  {time.perf_counter() - t:.2f} s  "
                  f"{len(m['body'])} roles")
