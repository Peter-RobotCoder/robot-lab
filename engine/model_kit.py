"""Pure-Python model building for the games' ultra tier (CHANGE 145): shapes made of numbers alone, so a game's window
(Panda3D) and the page (club-coders/web/make_models.py writes them to models/*.json) draw the same thing. No Panda3D
here, no numpy: lists of floats.

A Part is one material's triangles: positions, normals, texture coordinates (repeats of the material's texture), a
colour per vertex (screen colours, multiplied by the material's: make them linear to light them) and, where a part
fades out, an alpha per vertex. The builders add to a Part, placed by a Frame (an origin and three axes): rounded
boxes with true round edges (rounded_box), shapes turned about an axis (lathe), tubes along a path (tube), straight
round bars (rod), flat-sided extrusions of a 2D outline (extrude), rounded blobs (superellipsoid), hex bolt heads
(bolt) and flat discs (disc).

Part.packed() is the files' form (kart/kart_scenery.py made it for the circuit; the same here): each array packed
little-endian and written in base64. positions: uint16 per coordinate, from "box" (min x, y, z, max x, y, z) in 65535
steps; uvs: uint16 the same way in "uv_box" (min u, v, max u, v); normals: int8 (times 127); colours: uint8 (times 255),
only when not all white; alpha: uint8, only when not all opaque; indices: uint16, or uint32 when "count" is 65536 or
more. Triangles are anticlockwise seen from outside.
"""
import base64
import math
import sys
from array import array


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


def lerp(a, b, t):
    return a + (b - a) * t


def mix(a, b, t):
    return tuple(lerp(x, y, t) for x, y in zip(a, b))


def shade(c, k):
    """A colour times k (each channel, kept under 1)."""
    return tuple(min(1.0, v * k) for v in c)


def hash01(*ints):
    """A number from 0 to 1 that depends only on the integers given (the same in any language)."""
    h = 0x811C9DC5
    for i in ints:
        h = ((h ^ (int(i) & 0xFFFFFFFF)) * 0x01000193) & 0xFFFFFFFF
        h ^= h >> 15
        h = (h * 0x2C1B3C6D) & 0xFFFFFFFF
        h ^= h >> 12
    return (h & 0xFFFFFF) / 16777216.0


class Frame:
    """Where a shape goes: an origin and three axes (x, y, z: unit vectors at right angles, a right-handed set)."""

    def __init__(self, origin=(0.0, 0.0, 0.0), x=(1.0, 0.0, 0.0), y=(0.0, 1.0, 0.0), z=(0.0, 0.0, 1.0)):
        self.o, self.x, self.y, self.z = tuple(origin), tuple(x), tuple(y), tuple(z)

    def p(self, x, y, z):
        """A point given in the frame, in the world."""
        o, a, b, c = self.o, self.x, self.y, self.z
        return (o[0] + a[0] * x + b[0] * y + c[0] * z, o[1] + a[1] * x + b[1] * y + c[1] * z,
                o[2] + a[2] * x + b[2] * y + c[2] * z)

    def v(self, x, y, z):
        """A direction given in the frame, in the world."""
        a, b, c = self.x, self.y, self.z
        return (a[0] * x + b[0] * y + c[0] * z, a[1] * x + b[1] * y + c[1] * z, a[2] * x + b[2] * y + c[2] * z)

    def at(self, x, y, z):
        """This frame moved to a point given in it."""
        return Frame(self.p(x, y, z), self.x, self.y, self.z)

    def turned(self, axis, deg):
        """This frame turned deg degrees about one of its own axes ("x", "y" or "z"), anticlockwise looking down it."""
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        x, y, z = self.x, self.y, self.z
        if axis == "z":
            return Frame(self.o, add(mul(x, c), mul(y, s)), add(mul(y, c), mul(x, -s)), z)
        if axis == "x":
            return Frame(self.o, x, add(mul(y, c), mul(z, s)), add(mul(z, c), mul(y, -s)))
        return Frame(self.o, add(mul(x, c), mul(z, -s)), y, add(mul(z, c), mul(x, s)))


IDENTITY = Frame()


def heading(h_deg, origin=(0.0, 0.0, 0.0)):
    """A frame turned h degrees about z (anticlockwise from +x), at origin."""
    return Frame(origin).turned("z", h_deg)


# ---------- a part ----------
class Part:
    """One material's triangles. self.colour and self.alpha are given to new vertices unless told otherwise."""

    def __init__(self, name, material, tint=False, far=False):
        self.name, self.material, self.tint, self.far = name, material, tint, far
        self.p, self.n, self.uv, self.c, self.a, self.idx = [], [], [], [], [], []
        self.colour = (1.0, 1.0, 1.0)
        self.alpha = 1.0

    def vertex(self, p, n, uv=(0.0, 0.0), c=None, a=None):
        self.p.append(tuple(p))
        self.n.append(tuple(n))
        self.uv.append(tuple(uv))
        self.c.append(self.colour if c is None else tuple(c))
        self.a.append(self.alpha if a is None else a)
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

    def quad(self, pts, n, uvs=((0, 0), (1, 0), (1, 1), (0, 1)), c=None):
        """A flat quad facing n (its corners in order round it, either way)."""
        v = [self.vertex(p, n, uv, c) for p, uv in zip(pts, uvs)]
        self.tri(v[0], v[1], v[2])
        self.tri(v[0], v[2], v[3])

    def poly(self, pts, n, metres=1.0, c=None):
        """A flat convex polygon facing n, its texture to scale (metres a repeat), projected on its own plane."""
        u_ax = norm(sub(pts[1], pts[0]))
        v_ax = cross(norm(n), u_ax)
        v = [self.vertex(p, n, (dot(sub(p, pts[0]), u_ax) / metres, dot(sub(p, pts[0]), v_ax) / metres), c) for p in pts]
        for i in range(1, len(v) - 1):
            self.tri(v[0], v[i], v[i + 1])

    def grid(self, rows, normals, uvs, colours=None):
        """Quads between rows of points (each row the same length), with the normals given."""
        base = []
        for r, (row, nrow, uvrow) in enumerate(zip(rows, normals, uvs)):
            base.append([self.vertex(p, n, uv, colours[r][j] if colours else None)
                         for j, (p, n, uv) in enumerate(zip(row, nrow, uvrow))])
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
                n = norm(cross(sub(rows[r][jr], rows[r][jl]), sub(rows[ru][j], rows[rd][j])))
                if n == (0.0, 0.0, 0.0):
                    n = norm(sub(rows[r][j], inside(rows[r][j])))
                if dot(n, sub(rows[r][j], inside(rows[r][j]))) < 0:
                    n = mul(n, -1)
                nrow.append(n)
            normals.append(nrow)
        uvs, vcol = [], [0.0] * C
        for r in range(R):
            u, row = 0.0, []
            if r:
                vcol = [v + math.dist(rows[r][j], rows[r - 1][j]) for j, v in enumerate(vcol)]
            for j in range(C):
                if j:
                    u += math.dist(rows[r][j], rows[r][j - 1])
                row.append((u * uv_scale, vcol[j] * uv_scale))
            uvs.append(row)
        self.grid(rows, normals, uvs)

    def tris(self):
        return len(self.idx) // 3

    def merge(self, other):
        """other's triangles added to this part (the same material)."""
        base = len(self.p)
        self.p += other.p
        self.n += other.n
        self.uv += other.uv
        self.c += other.c
        self.a += other.a
        self.idx += [i + base for i in other.idx]

    def packed(self):
        """The part as the models' files keep it (see the module's notes)."""
        n = len(self.p)
        r3 = lambda v: round(v, 3) + 0.0  # noqa: E731  (+ 0.0: never "-0.0")
        box = [r3(min(p[k] for p in self.p) - 0.0005) for k in range(3)] + [r3(max(p[k] for p in self.p) + 0.001) for k in range(3)]
        uv_box = [r3(min(t[k] for t in self.uv) - 0.0005) for k in range(2)] + [r3(max(t[k] for t in self.uv) + 0.001) for k in range(2)]
        positions = array("H", (min(65535, max(0, round((p[k] - box[k]) / (box[k + 3] - box[k]) * 65535)))
                                for p in self.p for k in range(3)))
        uvs = array("H", (min(65535, max(0, round((t[k] - uv_box[k]) / (uv_box[k + 2] - uv_box[k]) * 65535)))
                          for t in self.uv for k in range(2)))
        normals = array("b", (max(-127, min(127, round(c * 127))) for v in self.n for c in v))
        indices = array("H" if n < 65536 else "I", self.idx)
        out = {"name": self.name, "material": self.material, "count": n, "box": box, "uv_box": uv_box,
               "positions": b64(positions), "normals": b64(normals), "uvs": b64(uvs), "indices": b64(indices)}
        if any(c != (1.0, 1.0, 1.0) for c in self.c):
            out["colours"] = b64(array("B", (max(0, min(255, round(v * 255))) for c in self.c for v in c)))
        if any(a != 1.0 for a in self.a):
            out["alpha"] = b64(array("B", (max(0, min(255, round(a * 255))) for a in self.a)))
        if self.tint:
            out["tint"] = True
        if self.far:
            out["far"] = True
        return out


def b64(values):
    """An array's bytes, little-endian, in base64."""
    if sys.byteorder == "big":
        values = array(values.typecode, values)
        values.byteswap()
    return base64.b64encode(values.tobytes()).decode("ascii")


def unpack(packed):
    """A packed part read back: (positions, normals, uvs, colours, alpha, indices) as flat lists (for the tests)."""
    def read(key, code):
        a = array(code)
        a.frombytes(base64.b64decode(packed[key]))
        if sys.byteorder == "big":
            a.byteswap()
        return list(a)
    box, uv_box, n = packed["box"], packed["uv_box"], packed["count"]
    pos = read("positions", "H")
    pos = [box[k % 3] + v / 65535 * (box[k % 3 + 3] - box[k % 3]) for k, v in enumerate(pos)]
    uv = read("uvs", "H")
    uv = [uv_box[k % 2] + v / 65535 * (uv_box[k % 2 + 2] - uv_box[k % 2]) for k, v in enumerate(uv)]
    nrm = [v / 127 for v in read("normals", "b")]
    col = [v / 255 for v in read("colours", "B")] if "colours" in packed else [1.0] * (3 * n)
    alpha = [v / 255 for v in read("alpha", "B")] if "alpha" in packed else [1.0] * n
    idx = read("indices", "H" if n < 65536 else "I")
    return pos, nrm, uv, col, alpha, idx


class Parts:
    """A set of parts, one per material (and tint and far): get() gives the one to add to."""

    def __init__(self, far=False):
        self.by = {}
        self.far = far

    def get(self, material, tint=False, far=None):
        far = self.far if far is None else far
        key = (material, tint, far)
        if key not in self.by:
            self.by[key] = Part(material + (" tinted" if tint else "") + (" far" if far else ""), material, tint, far)
        return self.by[key]

    def all(self):
        return [p for p in self.by.values() if p.idx]


# ---------- shapes ----------
def _band(h, r, steps, inner):
    """The coordinates along one axis of a rounded box's face: the flat middle in `inner` pieces, and `steps` pieces
    over each rounded edge (spaced so each piece turns the same angle)."""
    out = []
    flat = h - r
    for k in range(steps):  # from the edge (-h) to where the flat starts (-flat): angles 45 degrees down to 0
        a = math.radians(45.0 * (steps - k) / steps)
        out.append(-flat - r * math.tan(a))
    for k in range(inner + 1):
        out.append(-flat + 2 * flat * k / inner)
    for k in range(steps - 1, -1, -1):
        a = math.radians(45.0 * (steps - k) / steps)
        out.append(flat + r * math.tan(a))
    return out


def rounded_box(part, f, half, r, steps=3, inner=1, metres=1.0, skip=(), c=None):
    """A box of half sizes half (along f's axes) with every edge and corner rounded to radius r: a true round edge
    (each face's grid pushed out onto the box shrunk by r, plus r along its own normal), so it catches the light like
    machined or moulded metal. skip: faces left out ("-z", "+x", ...). Its texture runs flat over each face."""
    hx, hy, hz = half
    r = max(1e-4, min(r, hx * 0.999, hy * 0.999, hz * 0.999))
    inner_h = (hx - r, hy - r, hz - r)
    cols = [_band(hx, r, steps, inner), _band(hy, r, steps, inner), _band(hz, r, steps, inner)]
    for axis in range(3):
        for s in (-1, 1):
            key = ("+" if s > 0 else "-") + "xyz"[axis]
            if key in skip:
                continue
            u, w = [a for a in range(3) if a != axis]
            rows, normals, uvs = [], [], []
            for cw in cols[w]:
                row, nrow, uvrow = [], [], []
                for cu in cols[u]:
                    q = [0.0, 0.0, 0.0]
                    q[axis], q[u], q[w] = s * half[axis], cu, cw
                    core = [max(-inner_h[i], min(inner_h[i], q[i])) for i in range(3)]
                    core[axis] = s * inner_h[axis]
                    d = norm(sub(q, core))
                    p = add(core, mul(d, r))
                    row.append(f.p(*p))
                    nrow.append(f.v(*d))
                    uvrow.append(((cu * s if axis != 1 else -cu * s) / metres, cw / metres))
                rows.append(row)
                normals.append(nrow)
                uvs.append(uvrow)
            start = len(part.p)
            part.grid(rows, normals, uvs, [[c] * len(rows[0])] * len(rows) if c else None)
            del start
    return part


def box(part, f, x0, x1, y0, y1, z0, z1, metres=1.0, skip=(), c=None):
    """A sharp-edged box from x0 to x1, y0 to y1, z0 to z1 along f's axes. skip: faces left out ("-z", "+x", ...)."""
    faces = {"+x": ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (y1 - y0, z1 - z0)),
             "-x": ((-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], (y1 - y0, z1 - z0)),
             "+y": ((0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], (x1 - x0, z1 - z0)),
             "-y": ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (x1 - x0, z1 - z0)),
             "+z": ((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (x1 - x0, y1 - y0)),
             "-z": ((0, 0, -1), [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], (x1 - x0, y1 - y0))}
    for key, (n, pts, (w, h)) in faces.items():
        if key in skip:
            continue
        w, h = (w / metres, h / metres) if metres else (1.0, 1.0)
        part.quad([f.p(*p) for p in pts], f.v(*n), [(0, 0), (w, 0), (w, h), (0, h)], c)
    return part


def lathe(part, f, profile, seg=24, metres=1.0, c=None, start=0.0, sweep=360.0):
    """A shape turned about f's z axis: profile is (radius, height) points running down the outside (from the top
    down, so its normals point out; reverse it for an inside). start/sweep: part of a turn, in degrees."""
    rows, normals, uvs = [], [], []
    v = 0.0
    full = abs(sweep - 360.0) < 1e-9
    angles = [math.radians(start + sweep * j / seg) for j in range(seg + 1)]
    for i, (r, z) in enumerate(profile):
        a, b = profile[max(0, i - 1)], profile[min(len(profile) - 1, i + 1)]
        nr, nz = -(b[1] - a[1]), b[0] - a[0]
        d = math.hypot(nr, nz) or 1.0
        nr, nz = nr / d, nz / d
        if i:
            v += math.dist(profile[i], profile[i - 1])
        rows.append([f.p(r * math.cos(t), r * math.sin(t), z) for t in angles])
        normals.append([f.v(nr * math.cos(t), nr * math.sin(t), nz) for t in angles])
        uvs.append([((t - angles[0]) * max(r, 0.02) / metres, v / metres) for t in angles])
    part.grid(rows, normals, uvs, [[c] * (seg + 1)] * len(rows) if c else None)
    del full
    return part


def disc(part, f, r_out, r_in=0.0, seg=24, metres=1.0, c=None, z=0.0, down=False):
    """A flat ring (or disc, r_in 0) across f's z axis at height z, facing +z (or -z if down)."""
    n = f.v(0, 0, -1 if down else 1)
    pts = lambda r: [f.p(r * math.cos(2 * math.pi * j / seg), r * math.sin(2 * math.pi * j / seg), z) for j in range(seg)]  # noqa: E731
    uv = lambda p: (dot(sub(p, f.o), f.x) / metres, dot(sub(p, f.o), f.y) / metres)  # noqa: E731
    outer = [part.vertex(p, n, uv(p), c) for p in pts(r_out)]
    if r_in <= 0:
        mid = part.vertex(f.p(0, 0, z), n, uv(f.p(0, 0, z)), c)
        for j in range(seg):
            part.tri(mid, outer[j], outer[(j + 1) % seg])
        return part
    inner = [part.vertex(p, n, uv(p), c) for p in pts(r_in)]
    for j in range(seg):
        a, b, cc, d = outer[j], outer[(j + 1) % seg], inner[(j + 1) % seg], inner[j]
        part.tri(a, b, cc)
        part.tri(a, cc, d)
    return part


def cylinder(part, f, r, z0, z1, seg=16, caps=True, metres=1.0, c=None, bevel=0.0):
    """A round bar along f's z axis from z0 to z1, its ends closed (caps) and optionally chamfered (bevel)."""
    b = min(bevel, r * 0.4, abs(z1 - z0) * 0.4)
    profile = [(max(1e-4, r - b), z1), (r, z1 - b), (r, z0 + b), (max(1e-4, r - b), z0)] if b else [(r, z1), (r, z0)]
    if b:
        lathe(part, f, profile[:2], seg, metres, c)
        lathe(part, f, profile[1:3], seg, metres, c)
        lathe(part, f, profile[2:], seg, metres, c)
    else:
        lathe(part, f, profile, seg, metres, c)
    if caps:
        disc(part, f, r - b, 0.0, seg, metres, c, z=z1)
        disc(part, f, r - b, 0.0, seg, metres, c, z=z0, down=True)
    return part


def rod(part, a, b, r, seg=8, caps=False, metres=1.0, c=None):
    """A straight round bar from point a to point b (posts, rails, pipes)."""
    ahead = norm(sub(b, a))
    side = norm(cross(ahead, (0, 0, 1) if abs(ahead[2]) < 0.9 else (1, 0, 0)))
    f = Frame(a, side, cross(ahead, side), ahead)
    return cylinder(part, f, r, 0.0, math.dist(a, b), seg, caps, metres, c)


def tube(part, path, radius, seg=12, caps=True, metres=1.0, c=None):
    """A round tube along a path of points (radius: one number, or one per point), bent smoothly at each point."""
    radii = radius if isinstance(radius, (list, tuple)) else [radius] * len(path)
    rows, centres, prev = [], [], None
    for i, (q, r) in enumerate(zip(path, radii)):
        ahead = norm(sub(path[min(len(path) - 1, i + 1)], path[max(0, i - 1)]))
        side = norm(cross(ahead, (0, 0, 1) if abs(ahead[2]) < 0.9 else (1, 0, 0))) if prev is None else \
            norm(cross(cross(ahead, prev), ahead))
        prev = side
        up = cross(side, ahead)
        rows.append([add(q, add(mul(side, r * math.cos(2 * math.pi * j / seg)), mul(up, r * math.sin(2 * math.pi * j / seg))))
                     for j in range(seg + 1)])
        centres.append(tuple(q))
    part.surface(rows, lambda p: min(centres, key=lambda cc: math.dist(cc, p)), uv_scale=1.0 / metres)
    if caps:
        for end, sign in ((0, -1), (len(path) - 1, 1)):
            cc = centres[end]
            n = mul(norm(sub(centres[min(len(centres) - 1, end + 1)], centres[max(0, end - 1)])), sign)
            mid = part.vertex(cc, n, (0.5, 0.5), c)
            rim = [part.vertex(p, n, (0.5, 0.5), c) for p in rows[end][:-1]]
            for j in range(len(rim)):
                part.tri(mid, rim[j], rim[(j + 1) % len(rim)])
    return part


def superellipsoid(part, f, radii, e=4.0, seg=20, rings=12, metres=0.5, c=None):
    """A rounded box or ball about f's origin (e 2 is an ellipsoid, higher is boxier)."""
    def spow(v, k):
        return math.copysign(abs(v) ** k, v)
    rows = []
    for i in range(rings + 1):
        lat = -math.pi / 2 + math.pi * i / rings
        cl = spow(math.cos(lat), 2 / e)
        rows.append([f.p(radii[0] * cl * spow(math.cos(2 * math.pi * j / seg), 2 / e),
                         radii[1] * cl * spow(math.sin(2 * math.pi * j / seg), 2 / e),
                         radii[2] * spow(math.sin(lat), 2 / e)) for j in range(seg + 1)])
    start = len(part.p)
    part.surface(rows, lambda p: f.o, pole_normals={0: f.v(0, 0, -1), rings: f.v(0, 0, 1)}, uv_scale=1.0 / metres)
    if c:
        for i in range(start, len(part.p)):
            part.c[i] = c
    return part


def extrude(part, f, outline, z0, z1, metres=1.0, c=None, caps=True):
    """A flat-sided solid: the 2D outline [(x, y), ...] (convex, anticlockwise seen from +z) in f's x-y plane, from
    height z0 to z1 along f's z (teeth, plates, brackets)."""
    k = len(outline)
    for i in range(k):
        (x0, y0), (x1, y1) = outline[i], outline[(i + 1) % k]
        n = norm((y1 - y0, -(x1 - x0), 0.0))
        L = math.hypot(x1 - x0, y1 - y0)
        part.quad([f.p(x0, y0, z0), f.p(x1, y1, z0), f.p(x1, y1, z1), f.p(x0, y0, z1)], f.v(*n),
                  [(0, z0 / metres), (L / metres, z0 / metres), (L / metres, z1 / metres), (0, z1 / metres)], c)
    if caps:
        part.poly([f.p(x, y, z1) for x, y in outline], f.v(0, 0, 1), metres, c)
        part.poly([f.p(x, y, z0) for x, y in reversed(outline)], f.v(0, 0, -1), metres, c)
    return part


def bolt(part, f, r=0.012, h=0.008, seg=6, c=None):
    """A hex bolt head on f's x-y plane, standing up its z: six flat sides and a chamfered top."""
    top = [(r * 0.8 * math.cos(2 * math.pi * (j + 0.5) / seg), r * 0.8 * math.sin(2 * math.pi * (j + 0.5) / seg)) for j in range(seg)]
    side = [(r * math.cos(2 * math.pi * (j + 0.5) / seg), r * math.sin(2 * math.pi * (j + 0.5) / seg)) for j in range(seg)]
    extrude(part, f, side, 0.0, h * 0.7, 0.05, c, caps=False)
    for j in range(seg):  # the chamfer from the sides to the top
        a, b = side[j], side[(j + 1) % seg]
        ta, tb = top[j], top[(j + 1) % seg]
        pts = [f.p(a[0], a[1], h * 0.7), f.p(b[0], b[1], h * 0.7), f.p(tb[0], tb[1], h), f.p(ta[0], ta[1], h)]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        n = norm(f.v(mid[0] * 0.3 / max(1e-6, math.hypot(*mid)) * 3, mid[1] * 0.3 / max(1e-6, math.hypot(*mid)) * 3, 1.0))
        part.quad(pts, n, c=c)
    part.poly([f.p(x, y, h) for x, y in top], f.v(0, 0, 1), 0.05, c)
    return part


def ring_of(n, r, z=0.0, start=0.0):
    """n points evenly round a circle of radius r (in a frame's x-y plane), at height z."""
    return [(r * math.cos(start + 2 * math.pi * k / n), r * math.sin(start + 2 * math.pi * k / n), z) for k in range(n)]
