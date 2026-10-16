"""Kart Lab's ultra kart (CHANGE 144): a smooth, curved kart built from numbers alone, so the window (kart_gfx.py)
and the page (club-coders/web/make_models.py writes it to models/kart_ultra.json) draw the same one.

Pure Python, no Panda3D: everything is lists of floats. kart() returns the model as the page reads it:

    {"version": 1,
     "body":     [part, ...]     the kart's own parts, in the kart's frame
     "wheel":    [part, ...]     ONE wheel centred at the origin, its axle along +y, its outer face at +y
     "wheels":   [{"x", "y", "z", "front", "side"}, ...]  where the four wheels go (side 1: the left, +y; side -1:
                                 the right, whose wheel is turned 180 degrees about z so its outer face is at -y)
     "steering": [part, ...]     the steering wheel, which turns about notes["steering"]
     "notes":    {...}}          the pivot, how far the steering wheel turns, each role's look, the size

    part: {"name": str, "role": str, "positions": [x, y, z, ...], "normals": [x, y, z, ...], "indices": [i, ...],
           "uvs": [u, v, ...]}

The kart's frame is the game's: x forward (the nose along +x), y to the left, z up, in metres, the ground at z = 0
under the kart's middle. Triangles are anticlockwise seen from outside. It has the box kart's footprint
(kart_gfx.KartVisual): the same wheels in the same places, about 1.8 m long and 1.4 m wide over the wheels.

roles: paint (the design's colour), paint2 (its second colour: the designs have one colour so far, so paint),
dark (chassis black), metal, chrome, glass (the visor), tyre, rim, seat, skin, helmet (the design's colour).
"""
import math

VERSION = 1
WHEEL_R, WHEEL_W = 0.2, 0.09  # the wheels' radius and half width (kart_gfx draws the box kart's with these too)
WHEELS = [(0.5, 0.6), (0.5, -0.6), (-0.52, 0.62), (-0.52, -0.62)]  # (x, y): front left, front right, rear left, rear right
STEER_RATIO = 3.0  # the steering wheel turns this many times as far as the front wheels (a picture, not the physics)

# each role's look (linear colours are worked out by the drawer: these are screen colours, as the designs' are)
ROLES = {
    "paint": {"colour": None, "rough": 0.32, "metal": 0.15},   # None: the design's colour
    "paint2": {"colour": None, "rough": 0.32, "metal": 0.15},
    "dark": {"colour": [0.07, 0.07, 0.08], "rough": 0.55, "metal": 0.0},
    "metal": {"colour": [0.62, 0.63, 0.66], "rough": 0.35, "metal": 1.0},
    "chrome": {"colour": [0.92, 0.92, 0.94], "rough": 0.08, "metal": 1.0},
    "glass": {"colour": [0.03, 0.035, 0.05], "rough": 0.04, "metal": 0.0},
    "tyre": {"colour": [0.11, 0.11, 0.12], "rough": 0.8, "metal": 0.0},  # (slicks, as karts race on)
    "rim": {"colour": [0.78, 0.79, 0.82], "rough": 0.28, "metal": 1.0},
    "seat": {"colour": [0.09, 0.09, 0.11], "rough": 0.4, "metal": 0.0},
    "skin": {"colour": [0.86, 0.66, 0.53], "rough": 0.6, "metal": 0.0},
    "helmet": {"colour": None, "rough": 0.18, "metal": 0.05},
}


# ---------- small vector sums ----------
def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a):
    d = math.sqrt(dot(a, a))
    return (a[0] / d, a[1] / d, a[2] / d) if d > 1e-12 else (0.0, 0.0, 0.0)


def rot_y(p, deg):
    """p turned about the y axis (a positive angle tips +x up towards +z... the nose up)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[2] * s, p[1], p[0] * s + p[2] * c)


def rot_axis(p, axis, deg):
    """p turned about a unit axis through the origin (Rodrigues)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return add(add(mul(p, c), mul(cross(axis, p), s)), mul(axis, dot(axis, p) * (1 - c)))


def spow(v, e):
    """A signed power: the superellipse's |v|^e with v's sign."""
    return math.copysign(abs(v) ** e, v)


def catmull(points, steps):
    """A smooth curve through the points (tuples of any length), steps pieces between each pair."""
    out = []
    n = len(points)
    for i in range(n - 1):
        p0, p1, p2 = points[max(0, i - 1)], points[i], points[i + 1]
        p3 = points[min(n - 1, i + 2)]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(tuple(points[-1]))
    return out


# ---------- a part ----------
class Part:
    """One part's triangles: positions, normals and texture coordinates, all in one role."""

    def __init__(self, name, role):
        self.name, self.role = name, role
        self.p, self.n, self.uv, self.idx = [], [], [], []

    def vertex(self, p, n, uv=(0.0, 0.0)):
        self.p.append(p)
        self.n.append(n)
        self.uv.append(uv)
        return len(self.p) - 1

    def tri(self, a, b, c):
        """A triangle, wound so it faces the way its vertices' normals do (anticlockwise seen from there)."""
        pa, pb, pc = self.p[a], self.p[b], self.p[c]
        face = cross(sub(pb, pa), sub(pc, pa))
        if dot(face, face) < 1e-18:
            return  # (a sliver at a pole)
        if dot(face, add(add(self.n[a], self.n[b]), self.n[c])) < 0:
            b, c = c, b
        self.idx += [a, b, c]

    def grid(self, rows, normals, uvs):
        """Quads between rows of points (each row the same length), with the normals given."""
        base = []
        for r, (row, nrow, uvrow) in enumerate(zip(rows, normals, uvs)):
            base.append([self.vertex(p, n, uv) for p, n, uv in zip(row, nrow, uvrow)])
        for r in range(len(rows) - 1):
            for j in range(len(rows[r]) - 1):
                a, b, c, d = base[r][j], base[r][j + 1], base[r + 1][j + 1], base[r + 1][j]
                self.tri(a, b, c)
                self.tri(a, c, d)

    def surface(self, rows, inside, wrap=True, uv_scale=1.0, pole_normals=None):
        """A smooth surface through rows of points: its normals from the neighbouring points, turned to face away
        from inside(point) (a point within the shape). wrap: each row is a closed ring (its last point is its
        first again, for the texture's seam). pole_normals: {row index: normal} for rows shrunk to a point."""
        R, C = len(rows), len(rows[0])
        normals = []
        for r in range(R):
            nrow = []
            for j in range(C):
                if pole_normals and r in pole_normals:
                    nrow.append(pole_normals[r])
                    continue
                if wrap:
                    jl, jr = (j - 1) % (C - 1), (j + 1) % (C - 1)
                else:
                    jl, jr = max(0, j - 1), min(C - 1, j + 1)
                ru, rd = min(R - 1, r + 1), max(0, r - 1)
                du = sub(rows[r][jr], rows[r][jl])
                dv = sub(rows[ru][j], rows[rd][j])
                n = norm(cross(du, dv))
                if n == (0.0, 0.0, 0.0):  # (a row shrunk towards a point: away from the inside)
                    n = norm(sub(rows[r][j], inside(rows[r][j])))
                if dot(n, sub(rows[r][j], inside(rows[r][j]))) < 0:
                    n = mul(n, -1)
                nrow.append(n)
            normals.append(nrow)
        # texture coordinates: u along the rows by distance, v across them by distance
        uvs = []
        for r in range(R):
            u, row = 0.0, []
            for j in range(C):
                if j:
                    u += math.dist(rows[r][j], rows[r][j - 1])
                row.append(u)
            uvs.append(row)
        vcol = [0.0] * C
        out = []
        for r in range(R):
            if r:
                vcol = [v + math.dist(rows[r][j], rows[r - 1][j]) for j, v in enumerate(vcol)]
            out.append([(uvs[r][j] * uv_scale, vcol[j] * uv_scale) for j in range(C)])
        self.grid(rows, normals, out)

    def as_dict(self):
        r4 = lambda v: round(v, 4) + 0.0  # noqa: E731  (a tenth of a millimetre; + 0.0: never "-0.0")
        r3 = lambda v: round(v, 3) + 0.0  # noqa: E731
        return {"name": self.name, "role": self.role,
                "positions": [r4(c) for p in self.p for c in p],
                "normals": [r3(c) for n in self.n for c in n],
                "indices": list(self.idx),
                "uvs": [r3(c) for uv in self.uv for c in uv]}


# ---------- shapes ----------
def ring(cy, cz, hw, hh, e, seg, x):
    """A rounded-rectangle ring (a superellipse: e 2 is an ellipse, higher is squarer) across x."""
    pts = []
    for j in range(seg + 1):
        t = 2 * math.pi * j / seg
        pts.append((x, cy + hw * spow(math.cos(t), 2 / e), cz + hh * spow(math.sin(t), 2 / e)))
    return pts


def loft_x(part, stations, seg=32, steps=4, round_front=0.0, round_back=0.0, cy=0.0):
    """A body lofted along x through stations (x, half width, bottom z, top z, squareness), front first, with its
    ends rounded over round_front and round_back metres to a point."""
    smooth = catmull([tuple(s) for s in stations], steps)
    rows, poles = [], {}

    def section(x, hw, zb, zt, e, k=1.0):
        return ring(cy, (zb + zt) / 2, hw * k, (zt - zb) / 2 * k, e, seg, x)
    if round_front:
        x, hw, zb, zt, e = smooth[0]
        for i in range(6, 0, -1):  # a quarter circle from a point to the first section
            a = math.pi / 2 * i / 6
            rows.append(section(x + round_front * math.sin(a), hw, zb, zt, e, max(0.0, math.cos(a))))
        poles[0] = (1.0, 0.0, 0.0)
    rows += [section(*s) for s in smooth]
    if round_back:
        x, hw, zb, zt, e = smooth[-1]
        for i in range(1, 7):
            a = math.pi / 2 * i / 6
            rows.append(section(x - round_back * math.sin(a), hw, zb, zt, e, max(0.0, math.cos(a))))
        poles[len(rows) - 1] = (-1.0, 0.0, 0.0)
    # the inside: the station's centre at that x
    def inside(p):
        best = min(smooth, key=lambda s: abs(s[0] - p[0]))
        return (p[0], cy, (best[2] + best[3]) / 2)
    part.surface(rows, inside, pole_normals=poles, uv_scale=1.5)
    return part


def superellipsoid(part, centre, radii, e=4.0, seg=24, rings=14, tilt=0.0, turn=None):
    """A rounded box or ball (e 2 is an ellipsoid, higher is boxier), tipped tilt degrees about y (the nose up),
    then turned about an (axis, degrees) if given."""
    rows = []
    for i in range(rings + 1):
        lat = -math.pi / 2 + math.pi * i / rings
        row = []
        for j in range(seg + 1):
            lon = 2 * math.pi * j / seg
            cl = spow(math.cos(lat), 2 / e)
            p = (radii[0] * cl * spow(math.cos(lon), 2 / e), radii[1] * cl * spow(math.sin(lon), 2 / e),
                 radii[2] * spow(math.sin(lat), 2 / e))
            p = rot_y(p, tilt)
            if turn:
                p = rot_axis(p, turn[0], turn[1])
            row.append(add(p, centre))
        rows.append(row)
    up = rot_y((0, 0, 1), tilt)
    if turn:
        up = rot_axis(up, turn[0], turn[1])
    part.surface(rows, lambda p: centre, pole_normals={0: mul(up, -1), rings: up}, uv_scale=2.0)
    return part


def tube(part, path, radius, seg=12, steps=6, caps=True):
    """A round tube along a smooth path of points (radius: one number, or one per point)."""
    radii = radius if isinstance(radius, (list, tuple)) else [radius] * len(path)
    pts = catmull([tuple(p) + (r,) for p, r in zip(path, radii)], steps)
    rows, centres = [], []
    prev_side = None
    for i, q in enumerate(pts):
        c, r = q[:3], q[3]
        ahead = norm(sub(pts[min(len(pts) - 1, i + 1)][:3], pts[max(0, i - 1)][:3]))
        ref = (0, 0, 1) if abs(ahead[2]) < 0.9 else (1, 0, 0)
        side = norm(cross(ahead, ref)) if prev_side is None else norm(cross(cross(ahead, prev_side), ahead))
        prev_side = side
        up = cross(side, ahead)
        rows.append([add(c, add(mul(side, r * math.cos(2 * math.pi * j / seg)), mul(up, r * math.sin(2 * math.pi * j / seg))))
                     for j in range(seg + 1)])
        centres.append(c)

    def inside(p):
        return min(centres, key=lambda c: math.dist(c, p))
    part.surface(rows, inside, uv_scale=2.0)
    if caps:
        for end, sign in ((0, -1), (len(pts) - 1, 1)):
            c = centres[end]
            ahead = norm(sub(centres[min(len(centres) - 1, end + 1)], centres[max(0, end - 1)]))
            n = mul(ahead, sign)
            mid = part.vertex(c, n, (0.5, 0.5))
            rim = [part.vertex(p, n, (0.5, 0.5)) for p in rows[end][:-1]]
            for j in range(len(rim)):
                part.tri(mid, rim[j], rim[(j + 1) % len(rim)])
    return part


def lathe(part, profile, seg=40, uv_scale=2.0):
    """A shape turned about the y axis: profile is (radius, y) points, run with the outside on the left (up the
    inner side, over the top, down the outer side; or from the rim in to the axis across a face looking along +y)."""
    rows, normals, uvs = [], [], []
    v = 0.0
    for i, (r, y) in enumerate(profile):
        a, b = profile[max(0, i - 1)], profile[min(len(profile) - 1, i + 1)]
        nr, ny = b[1] - a[1], -(b[0] - a[0])  # (the profile's direction turned a quarter: outwards)
        d = math.hypot(nr, ny) or 1.0
        nr, ny = nr / d, ny / d
        if i:
            v += math.dist(profile[i], profile[i - 1])
        cs = [(math.cos(2 * math.pi * j / seg), math.sin(2 * math.pi * j / seg)) for j in range(seg + 1)]
        rows.append([(r * c, y, r * s_) for c, s_ in cs])
        normals.append([(nr * c, ny, nr * s_) for c, s_ in cs])
        uvs.append([(j / seg * uv_scale * 2, v * uv_scale) for j in range(seg + 1)])
    part.grid(rows, normals, uvs)
    return part


def disc(part, centre_y, r_out, r_in, facing, seg=40, uv_scale=2.0):
    """A flat ring (or disc, r_in 0) across the y axis at centre_y, facing +y (facing 1) or -y (facing -1)."""
    n = (0.0, float(facing), 0.0)
    outer = [part.vertex((r_out * math.cos(2 * math.pi * j / seg), centre_y, r_out * math.sin(2 * math.pi * j / seg)), n,
                         (0.5 + 0.5 * math.cos(2 * math.pi * j / seg), 0.5 + 0.5 * math.sin(2 * math.pi * j / seg)))
             for j in range(seg)]
    if r_in <= 0:
        mid = part.vertex((0.0, centre_y, 0.0), n, (0.5, 0.5))
        for j in range(seg):
            part.tri(mid, outer[j], outer[(j + 1) % seg])
        return part
    k = r_in / r_out
    inner = [part.vertex((r_in * math.cos(2 * math.pi * j / seg), centre_y, r_in * math.sin(2 * math.pi * j / seg)), n,
                         (0.5 + 0.5 * k * math.cos(2 * math.pi * j / seg), 0.5 + 0.5 * k * math.sin(2 * math.pi * j / seg)))
             for j in range(seg)]
    for j in range(seg):
        a, b = outer[j], outer[(j + 1) % seg]
        c, d = inner[(j + 1) % seg], inner[j]
        part.tri(a, b, c)
        part.tri(a, c, d)
    return part


def aerofoil(part, x_le, z, chord, span, angle, thick=0.12, seg=20):
    """A wing lofted along y: a cambered aerofoil section (its leading edge at x_le, the trailing edge behind it),
    tipped angle degrees (positive: the trailing edge up, for downforce), from -span to +span."""
    sec = []
    for j in range(seg + 1):  # round from the trailing edge over the top to the leading edge and back underneath
        t = 2 * math.pi * j / seg
        xc = (1 + math.cos(t)) / 2  # 1 at the trailing edge, 0 at the leading edge
        yt = 5 * thick * (0.2969 * math.sqrt(max(0.0, xc)) - 0.126 * xc - 0.3516 * xc ** 2 + 0.2843 * xc ** 3 - 0.1036 * xc ** 4)
        camber = -0.05 * (1 - (2 * xc - 1) ** 2)  # (cambered downwards: a wing that presses down)
        zz = (camber + (yt if math.sin(t) >= 0 else -yt)) * chord
        p = rot_y((-xc * chord, 0.0, zz), -angle)
        sec.append((x_le + p[0], z + p[2]))
    rows = []
    for k in range(9):
        y = -span + 2 * span * k / 8
        rows.append([(sx, y, sz) for sx, sz in sec])
    rows_t = [list(col) for col in zip(*rows)]  # rows across the span, one per section point (u along the span)
    centre = (x_le - chord / 2, 0.0, z)
    normals = []
    for j in range(len(sec)):
        a, b = sec[max(0, j - 1)], sec[min(len(sec) - 1, j + 1)]
        if j in (0, len(sec) - 1):
            a, b = sec[len(sec) - 2], sec[1]
        tx, tz = b[0] - a[0], b[1] - a[1]
        n = norm((tz, 0.0, -tx))
        if dot(n, sub((sec[j][0], 0.0, sec[j][1]), centre)) < 0:
            n = mul(n, -1)
        normals.append([n] * len(rows))
    uvs = [[(k / 8.0, j / seg) for k in range(len(rows))] for j in range(len(sec))]
    part.grid(rows_t, normals, uvs)
    return part


# ---------- the kart ----------
def body_parts():
    parts = []
    # the main body: a nose, the dashboard cowl, the cockpit's sides, the engine cover and the tail (paint)
    body = Part("body", "paint")
    loft_x(body, [(0.86, 0.12, 0.17, 0.25, 3.0), (0.76, 0.2, 0.14, 0.31, 3.2), (0.6, 0.25, 0.13, 0.39, 3.4),
                  (0.44, 0.27, 0.13, 0.45, 3.6), (0.27, 0.3, 0.13, 0.39, 3.8), (0.08, 0.33, 0.13, 0.31, 4.0),
                  (-0.32, 0.34, 0.13, 0.31, 4.0), (-0.52, 0.32, 0.13, 0.4, 3.8), (-0.68, 0.27, 0.14, 0.38, 3.4),
                  (-0.78, 0.2, 0.16, 0.31, 3.0)], seg=36, steps=3, round_front=0.05, round_back=0.05)
    parts.append(body)
    # the front fairing across the nose, in front of the front wheels (paint2), lofted along y
    fair = Part("front fairing", "paint2")
    span = catmull([(-0.56, 0.35), (-0.5, 0.8), (-0.4, 1.0), (0.4, 1.0), (0.5, 0.8), (0.56, 0.35)], 3)
    rows = [[(0.84, -0.575, 0.19)] * 25]  # (a point at each end: the fairing's rounded tips)
    for y, k in span:
        rows.append([(0.84 + 0.075 * k * spow(math.cos(t), 0.6), y, 0.19 + 0.065 * k * spow(math.sin(t), 0.6))
                     for t in (2 * math.pi * j / 24 for j in range(25))])
    rows.append([(0.84, 0.575, 0.19)] * 25)
    fair.surface(rows, lambda p: (0.84, max(-0.5, min(0.5, p[1])), 0.19),
                 pole_normals={0: (0, -1, 0), len(rows) - 1: (0, 1, 0)})
    parts.append(fair)
    # the side pods between the wheels (paint2)
    pods = Part("side pods", "paint2")
    for side in (1, -1):
        loft_x(pods, [(0.27, 0.05, 0.17, 0.25, 3.0), (0.18, 0.085, 0.15, 0.31, 3.4), (-0.12, 0.09, 0.15, 0.32, 3.6),
                      (-0.28, 0.075, 0.16, 0.29, 3.2)], seg=20, steps=2, round_front=0.04, round_back=0.04, cy=side * 0.43)
    parts.append(pods)
    # the floor pan under it all, and the bumper rails at the back (dark)
    dark = Part("chassis", "dark")
    loft_x(dark, [(0.7, 0.24, 0.1, 0.13, 6.0), (0.4, 0.34, 0.1, 0.13, 6.0), (-0.72, 0.36, 0.1, 0.13, 6.0)],
           seg=24, steps=2, round_front=0.02, round_back=0.02)
    tube(dark, [(-0.7, -0.6, 0.2), (-0.84, -0.48, 0.21), (-0.88, 0.0, 0.22), (-0.84, 0.48, 0.21), (-0.7, 0.6, 0.2)],
         0.024, seg=10, steps=6)
    for y in (-0.36, 0.36):
        tube(dark, [(-0.7, y, 0.14), (-0.86, y, 0.21)], 0.018, seg=8, steps=1)
    parts.append(dark)
    # the axles and the steering column (metal)
    metal = Part("axles", "metal")
    tube(metal, [(0.5, -0.53, 0.2), (0.5, 0.53, 0.2)], 0.017, seg=10, steps=1)
    tube(metal, [(-0.52, -0.55, 0.2), (-0.52, 0.55, 0.2)], 0.022, seg=10, steps=1)
    tube(metal, [STEER_CENTRE, (0.4, 0.0, 0.33)], 0.014, seg=8, steps=1)
    for y in (-0.25, 0.25):  # the rear wing's posts
        tube(metal, [(-0.64, y, 0.36), (-0.67, y, 0.57)], 0.012, seg=8, steps=1)
    # the engine beside the seat: the block (metal) under its finned head (dark)
    superellipsoid(metal, (-0.46, 0.22, 0.4), (0.1, 0.075, 0.07), e=5, seg=16, rings=10)
    parts.append(metal)
    head = Part("engine head", "dark")
    for k in range(4):  # cooling fins
        superellipsoid(head, (-0.46, 0.22, 0.47 + 0.017 * k), (0.085 - 0.006 * k, 0.065 - 0.004 * k, 0.006), e=6, seg=16, rings=6)
    superellipsoid(head, (-0.34, 0.22, 0.43), (0.05, 0.045, 0.045), e=3, seg=14, rings=8)  # the air box
    parts.append(head)
    # the exhaust out to the right and back, and its silencer (chrome)
    chrome = Part("exhaust", "chrome")
    tube(chrome, [(-0.5, 0.29, 0.38), (-0.58, 0.36, 0.34), (-0.66, 0.37, 0.33)], 0.018, seg=10, steps=5)
    superellipsoid(chrome, (-0.74, 0.37, 0.34), (0.1, 0.045, 0.045), e=2.6, seg=20, rings=10)
    parts.append(chrome)
    # the rear wing (paint) and its end plates (paint2)
    wing = Part("rear wing", "paint")
    aerofoil(wing, -0.57, 0.6, 0.22, 0.4, 9.0)
    parts.append(wing)
    plates = Part("wing end plates", "paint2")
    for side in (1, -1):
        superellipsoid(plates, (-0.68, side * 0.405, 0.6), (0.13, 0.007, 0.075), e=6, seg=16, rings=8)
    parts.append(plates)
    # the seat's back (seat)
    seat = Part("seat", "seat")
    superellipsoid(seat, (-0.45, 0.0, 0.43), (0.035, 0.18, 0.16), e=4, seg=20, rings=12, tilt=14)
    parts.append(seat)
    # the driver: a dark suit (dark: it stands out against the paint), neck (skin), helmet (helmet), visor (glass),
    # gloves (dark)
    suit = Part("driver", "dark")
    superellipsoid(suit, (-0.31, 0.0, 0.47), (0.11, 0.16, 0.16), e=2.8, seg=24, rings=14, tilt=12)
    for side in (1, -1):
        hand = (STEER_CENTRE[0] - 0.01, side * 0.105, STEER_CENTRE[2] + 0.005)
        tube(suit, [(-0.27, side * 0.15, 0.58), (-0.13, side * 0.205, 0.49), (-0.01, side * 0.15, 0.49), hand],
             [0.04, 0.035, 0.032, 0.03], seg=12, steps=5)
    parts.append(suit)
    skin = Part("neck", "skin")
    tube(skin, [(-0.3, 0.0, 0.6), (-0.29, 0.0, 0.7)], 0.045, seg=14, steps=1)
    parts.append(skin)
    helmet = Part("helmet", "helmet")
    superellipsoid(helmet, HELMET, (0.145, 0.135, 0.135), e=2.0, seg=28, rings=16)
    parts.append(helmet)
    parts.append(visor())
    gloves = Part("gloves", "dark")
    for side in (1, -1):
        superellipsoid(gloves, (STEER_CENTRE[0] - 0.01, side * 0.105, STEER_CENTRE[2] + 0.005), (0.032, 0.03, 0.035),
                       e=2.2, seg=10, rings=6)
    parts.append(gloves)
    return parts


HELMET = (-0.27, 0.0, 0.79)
STEER_CENTRE = (0.1, 0.0, 0.47)                    # the steering wheel's middle...
STEER_AXIS = norm((-math.cos(math.radians(32)), 0.0, math.sin(math.radians(32))))  # ...and its column, towards the driver


def visor():
    """The visor: a band of a sphere just outside the helmet, across its front."""
    part = Part("visor", "glass")
    r = 0.147
    rows = []
    for i in range(7):
        lat = math.radians(-6 + 34 * i / 6)
        row = []
        for j in range(17):
            lon = math.radians(-62 + 124 * j / 16)
            row.append(add(HELMET, (r * 1.04 * math.cos(lat) * math.cos(lon), r * math.cos(lat) * math.sin(lon),
                                    r * math.sin(lat))))
        rows.append(row)
    part.surface(rows, lambda p: HELMET, wrap=False)
    return part


def steering_parts():
    """The steering wheel: a rim (dark) on three spokes round a hub (metal), across the column."""
    a = STEER_AXIS
    side = (0.0, 1.0, 0.0)
    up = norm(cross(a, side))  # (in the wheel's plane, towards its top)
    c = STEER_CENTRE
    rim = Part("steering wheel", "dark")
    R, r = 0.11, 0.013
    rows = []
    for i in range(33):  # a torus: round the rim...
        t = 2 * math.pi * i / 32
        centre = add(c, add(mul(side, R * math.cos(t)), mul(up, R * math.sin(t))))
        out = norm(sub(centre, c))
        rows.append([add(centre, add(mul(out, r * math.cos(2 * math.pi * j / 10)), mul(a, r * math.sin(2 * math.pi * j / 10))))
                     for j in range(11)])
    rim.surface(rows, lambda p: add(c, mul(norm(sub(sub(p, c), mul(a, dot(sub(p, c), a)))), R)))
    for t in (0.0, math.pi, -math.pi / 2):  # spokes: left, right and down
        end = add(c, add(mul(side, (R - 0.01) * math.cos(t)), mul(up, (R - 0.01) * math.sin(t))))
        tube(rim, [add(c, mul(sub(end, c), 0.25)), end], 0.009, seg=8, steps=1)
    hub = Part("steering hub", "metal")
    tube(hub, [add(c, mul(a, -0.02)), add(c, mul(a, 0.015))], 0.03, seg=16, steps=1)
    return [rim, hub]


def wheel_parts():
    """One wheel at the origin, its axle along +y and its outer face at +y: a tyre with rounded shoulders and
    sidewalls (tyre), a dished rim with five spokes (rim) and a hub nut (chrome)."""
    R, W = WHEEL_R, WHEEL_W
    tyre = Part("tyre", "tyre")
    profile = [(0.128, -W + 0.012)]  # (radius, y): from the inner bead, up the inner sidewall, over the tread...
    for k in range(13):
        t = -math.pi / 2 + math.pi * k / 12
        profile.append((0.158 + (R - 0.158) * spow(math.cos(t), 0.45), W * spow(math.sin(t), 0.6)))
    profile.append((0.128, W - 0.012))  # ...and down the outer sidewall to the outer bead
    lathe(tyre, profile, seg=36)
    rim = Part("rim", "rim")
    # the barrel inside the tyre, the outer lip, the dish down to the hub; the inner face closed
    lathe(rim, [(0.128, W - 0.012), (0.131, W - 0.004), (0.122, W - 0.002), (0.112, W - 0.022), (0.05, W - 0.03),
                (0.042, W - 0.02)], seg=36)
    lathe(rim, [(0.126, W - 0.012), (0.128, -W + 0.012)], seg=36)  # (the barrel, seen from the axle)
    disc(rim, -W + 0.012, 0.128, 0.0, -1, seg=36)
    for k in range(5):  # five spokes standing proud of the dish
        t = 2 * math.pi * k / 5 + math.pi / 2
        p0 = (0.05 * math.cos(t), W - 0.02, 0.05 * math.sin(t))
        p1 = (0.112 * math.cos(t), W - 0.014, 0.112 * math.sin(t))
        mid = mul(add(p0, p1), 0.5)
        superellipsoid(rim, mid, (0.034, 0.008, 0.011), e=4, seg=10, rings=4,
                       turn=((0.0, 1.0, 0.0), -math.degrees(t)))
    nut = Part("hub nut", "chrome")
    lathe(nut, [(0.044, W - 0.024), (0.032, W - 0.01), (0.024, W + 0.006), (0.0, W + 0.006)], seg=24)
    return [tyre, rim, nut]


def kart():
    """The whole model, as models/kart_ultra.json holds it."""
    body = body_parts()
    steering = steering_parts()
    wheel = wheel_parts()
    tris = sum(len(p.idx) // 3 for p in body + steering) + 4 * sum(len(p.idx) // 3 for p in wheel)
    return {"version": VERSION,
            "body": [p.as_dict() for p in body],
            "wheel": [p.as_dict() for p in wheel],
            "wheels": [{"x": x, "y": y, "z": WHEEL_R, "front": x > 0, "side": 1 if y > 0 else -1} for x, y in WHEELS],
            "steering": [p.as_dict() for p in steering],
            "notes": {"steering": {"pivot": [round(v, 4) for v in STEER_CENTRE], "axis": [round(v, 4) for v in STEER_AXIS],
                                   "ratio": STEER_RATIO,
                                   "about": "the steering wheel turns about the axis through the pivot by the front "
                                            "wheels' angle times ratio (a left turn, anticlockwise seen from the driver)"},
                      "wheels": "side -1: the wheel turned 180 degrees about z, so its outer face (+y in 'wheel') is at -y; "
                                "the wheel spins about its own y axis, and a front wheel turns about z with the steering",
                      "roles": ROLES,
                      "size": {"length": 1.78, "width": round(2 * (0.62 + WHEEL_W), 2), "wheel_radius": WHEEL_R},
                      "triangles": tris,
                      "frame": "x forward, y left, z up, metres, the ground at z = 0; triangles anticlockwise seen from outside"}}


def triangles(model=None):
    """How many triangles the whole kart draws (the wheel four times)."""
    return (model or kart())["notes"]["triangles"]


if __name__ == "__main__":
    m = kart()
    for key in ("body", "wheel", "steering"):
        for p in m[key]:
            print(f"{key:9s} {p['name']:18s} {p['role']:7s} {len(p['indices']) // 3:6d} triangles")
    print("whole kart:", triangles(m), "triangles")
