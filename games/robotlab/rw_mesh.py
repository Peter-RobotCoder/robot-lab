"""Mesh building for Robot Wars graphics: bevelled boxes, cylinders, cones and wedges, with texture
coordinates and tangents so normal maps (surface detail) and PBR textures work.

Texture coordinates are in metres x tile, so textures stay the same size on every part.
"""
import math

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, InternalName, Vec3)

_arr = GeomVertexArrayFormat()
_arr.addColumn(InternalName.getVertex(), 3, Geom.NT_float32, Geom.C_point)
_arr.addColumn(InternalName.getNormal(), 3, Geom.NT_float32, Geom.C_normal)
_arr.addColumn(InternalName.getTexcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
_arr.addColumn(InternalName.getTangent(), 4, Geom.NT_float32, Geom.C_vector)
FORMAT = GeomVertexFormat.registerFormat(_arr)
_arr_c = GeomVertexArrayFormat(_arr)
_arr_c.addColumn(InternalName.getColor(), 4, Geom.NT_float32, Geom.C_color)
FORMAT_COLOUR = GeomVertexFormat.registerFormat(_arr_c)  # with a colour per vertex (crowds)


class Mesh:
    def __init__(self, tile=1.0, colours=False):
        self.tile = tile  # texture repeats per metre
        self.vd = GeomVertexData("mesh", FORMAT_COLOUR if colours else FORMAT, Geom.UH_static)
        self.c = GeomVertexWriter(self.vd, "color") if colours else None
        self.colour = (1, 1, 1, 1)
        self.v = GeomVertexWriter(self.vd, "vertex")
        self.n = GeomVertexWriter(self.vd, "normal")
        self.t = GeomVertexWriter(self.vd, "texcoord")
        self.tg = GeomVertexWriter(self.vd, "tangent")
        self.tris = GeomTriangles(Geom.UH_static)
        self.count = 0

    @staticmethod
    def _axes(normal):
        """A tangent and bitangent for a face, lined up with the world where possible."""
        ref = Vec3(0, 0, 1) if abs(normal.z) < 0.9 else Vec3(0, 1, 0)
        b = ref - normal * ref.dot(normal)
        b.normalize()
        t = b.cross(normal)
        t.normalize()
        return t, b

    def poly(self, pts, normal=None, uv_origin=Vec3(0)):
        """A flat convex polygon (points in order); flips winding to face along normal."""
        pts = [Vec3(p) for p in pts]
        face_n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
        face_n.normalize()
        if normal is None:
            normal = face_n
        else:
            normal = Vec3(normal)
            normal.normalize()
            if face_n.dot(normal) < 0:
                pts = pts[::-1]
        t, b = self._axes(normal)
        start = self.count
        for p in pts:
            q = p - uv_origin
            self.v.addData3(p)
            self.n.addData3(normal)
            self.t.addData2(q.dot(t) * self.tile, q.dot(b) * self.tile)
            self.tg.addData4(t.x, t.y, t.z, 1.0)
            if self.c:
                self.c.addData4(*self.colour)
        for i in range(1, len(pts) - 1):
            self.tris.addVertices(start, start + i, start + i + 1)
        self.count += len(pts)

    def smooth_strip(self, ring_a, ring_b, normals_a, normals_b, tangents, u_vals, v_a, v_b):
        """Quads between two rings with smooth normals (cylinder sides)."""
        start = self.count
        for ring, normals, v in ((ring_a, normals_a, v_a), (ring_b, normals_b, v_b)):
            for p, nrm, tg, u in zip(ring, normals, tangents, u_vals):
                self.v.addData3(p)
                self.n.addData3(nrm)
                self.t.addData2(u * self.tile, v * self.tile)
                self.tg.addData4(tg.x, tg.y, tg.z, 1.0)
                if self.c:
                    self.c.addData4(*self.colour)
        k = len(ring_a)
        for i in range(k - 1):
            a, b2, c, d = start + i, start + i + 1, start + k + i + 1, start + k + i
            self.tris.addVertices(a, b2, c)
            self.tris.addVertices(a, c, d)
        self.count += 2 * k

    def node(self, name="mesh"):
        g = Geom(self.vd)
        g.addPrimitive(self.tris)
        n = GeomNode(name)
        n.addGeom(g)
        return n


def bevel_box(hx, hy, hz, bevel=0.03, tile=1.0, mesh=None, offset=Vec3(0)):
    """A box with chamfered edges: the chamfers catch the light and look machined."""
    m = mesh or Mesh(tile)
    b = min(bevel, hx * 0.45, hy * 0.45, hz * 0.45)
    h = (hx, hy, hz)
    o = Vec3(offset)

    def P(x, y, z):
        return o + Vec3(x, y, z)
    # 6 faces
    for axis in range(3):
        for s in (-1, 1):
            u, w = [a for a in range(3) if a != axis]
            pts = []
            for cu, cw in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                c = [0, 0, 0]
                c[axis] = s * h[axis]
                c[u] = cu * (h[u] - b)
                c[w] = cw * (h[w] - b)
                pts.append(P(*c))
            nrm = Vec3(0, 0, 0)
            nrm[axis] = s
            m.poly(pts, nrm)
    # 12 edge chamfers
    for a1 in range(3):
        for a2 in range(a1 + 1, 3):
            along = 3 - a1 - a2
            for s1 in (-1, 1):
                for s2 in (-1, 1):
                    pts = []
                    for sa in (-1, 1):
                        for which in (0, 1):
                            c = [0, 0, 0]
                            c[along] = sa * (h[along] - b)
                            c[a1] = s1 * (h[a1] - (b if which else 0))
                            c[a2] = s2 * (h[a2] - (0 if which else b))
                            pts.append(P(*c))
                    quad = [pts[0], pts[1], pts[3], pts[2]]
                    nrm = Vec3(0, 0, 0)
                    nrm[a1], nrm[a2] = s1, s2
                    m.poly(quad, nrm)
    # 8 corners
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                s = (sx, sy, sz)
                pts = []
                for axis in range(3):
                    c = [s[i] * (h[i] - b) for i in range(3)]
                    c[axis] = s[axis] * h[axis]
                    pts.append(P(*c))
                m.poly(pts, Vec3(sx, sy, sz))
    return m


def cylinder(r, half_len, axis="z", seg=28, tile=1.0, mesh=None, offset=Vec3(0), bevel=0.0, r_top=None, caps=True):
    """A cylinder (or cone when r_top is 0) along x, y or z, optionally with bevelled rims."""
    m = mesh or Mesh(tile)
    r_top = r if r_top is None else r_top
    o = Vec3(offset)

    def place(x, y, z):  # x, y around the circle, z along the axis
        if axis == "z":
            return o + Vec3(x, y, z)
        if axis == "x":
            return o + Vec3(z, x, y)
        return o + Vec3(y, z, x)
    angles = [2 * math.pi * i / seg for i in range(seg + 1)]
    b = min(bevel, r * 0.4, half_len * 0.4)
    # side (smooth), trimmed by the bevel
    for (z0, r0), (z1, r1) in (((-half_len + b, r), (half_len - b, r_top)),):
        ring0 = [place(math.cos(a) * r0, math.sin(a) * r0, z0) for a in angles]
        ring1 = [place(math.cos(a) * r1, math.sin(a) * r1, z1) for a in angles]
        slope = (r0 - r1) / max(1e-6, z1 - z0)
        nrm = []
        for a in angles:
            n = place(math.cos(a), math.sin(a), slope) - o
            n.normalize()
            nrm.append(n)
        tang = []
        for a in angles:
            t = place(-math.sin(a), math.cos(a), 0) - o
            t.normalize()
            tang.append(t)
        u = [a * r for a in angles]
        m.smooth_strip(ring0, ring1, nrm, nrm, tang, u, z0, z1)
    if b > 0:  # rim bevels
        for zc, rr, zs in ((half_len, r_top, 1), (-half_len, r, -1)):
            ring_in = [place(math.cos(a) * (rr - b), math.sin(a) * (rr - b), zc) for a in angles]
            ring_out = [place(math.cos(a) * rr, math.sin(a) * rr, zc - zs * b) for a in angles]
            nrm = []
            for a in angles:
                n = place(math.cos(a), math.sin(a), zs) - o
                n.normalize()
                nrm.append(n)
            tang = []
            for a in angles:
                t = place(-math.sin(a), math.cos(a), 0) - o
                t.normalize()
                tang.append(t)
            u = [a * rr for a in angles]
            if zs > 0:
                m.smooth_strip(ring_out, ring_in, nrm, nrm, tang, u, 0, b)
            else:
                m.smooth_strip(ring_in, ring_out, nrm, nrm, tang, u, 0, b)
    if caps:
        for zc, rr, zs in ((half_len, r_top, 1), (-half_len, r, -1)):
            rr_in = rr - b
            if rr_in <= 1e-4:
                continue
            pts = [place(math.cos(a) * rr_in, math.sin(a) * rr_in, zc) for a in angles[:-1]]
            m.poly(pts, place(0, 0, zs) - o)
    return m


def plate_y(profile, half_y, tile=1.0, mesh=None, offset=Vec3(0), angle=0.0):
    """Extrude a convex 2D profile [(x, z), ...] (in order) along y, turned by angle (radians) about y:
    saw teeth, chainsaw bars and other flat parts that sit in the x-z plane."""
    m = mesh or Mesh(tile)
    o = Vec3(offset)
    c, s = math.cos(angle), math.sin(angle)

    def P(x, z, y):
        return o + Vec3(x * c + z * s, y, -x * s + z * c)
    front = [P(x, z, -half_y) for x, z in profile]
    back = [P(x, z, half_y) for x, z in profile]
    m.poly(front, Vec3(0, -1, 0))
    m.poly(back, Vec3(0, 1, 0))
    centre = sum(front, Vec3(0)) / len(front)
    k = len(profile)
    for i in range(k):
        j = (i + 1) % k
        nrm = (front[j] - front[i]).cross(Vec3(0, 1, 0))
        if nrm.length() < 1e-9:
            continue
        nrm.normalize()
        if nrm.dot((front[i] + front[j]) / 2 - centre) < 0:
            nrm = -nrm
        m.poly([front[i], front[j], back[j], back[i]], nrm)
    return m


def prism(profile, half_x, tile=1.0, mesh=None, offset=Vec3(0)):
    """Extrude a convex 2D profile [(y, z), ...] (in order) along x: wedges, ramps and armour."""
    m = mesh or Mesh(tile)
    o = Vec3(offset)
    left = [o + Vec3(-half_x, y, z) for y, z in profile]
    right = [o + Vec3(half_x, y, z) for y, z in profile]
    m.poly(left, Vec3(-1, 0, 0))
    m.poly(right, Vec3(1, 0, 0))
    k = len(profile)
    cy = sum(p[0] for p in profile) / k
    cz = sum(p[1] for p in profile) / k
    for i in range(k):
        j = (i + 1) % k
        dy, dz = profile[j][0] - profile[i][0], profile[j][1] - profile[i][1]
        nrm = Vec3(0, dz, -dy)  # perpendicular to the edge...
        mid_y = (profile[i][0] + profile[j][0]) / 2 - cy
        mid_z = (profile[i][1] + profile[j][1]) / 2 - cz
        if nrm.y * mid_y + nrm.z * mid_z < 0:  # ...pointing away from the middle
            nrm = -nrm
        m.poly([left[i], left[j], right[j], right[i]], nrm)
    return m
