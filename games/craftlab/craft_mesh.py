"""Craft Lab's chunk meshes (CHANGE 200): a chunk of the world (16 x 16 blocks, the whole height) turned into the
vertex arrays the window draws, in numpy, no Panda here (so the tests can measure it).

Only the faces between a block and an open neighbour are made (a hill is its skin, not its insides). Each corner of
a face gets corner shading (darker where two blocks meet in a corner, so edges and holes read at a glance) and the
light there (the sky's and the glowsticks', averaged over the four open blocks it touches, 0 to 12): the shader
multiplies the texture by them, so day and night are one number. Cubes are done all at once with array masks; the
few other shapes (plants, glowsticks, doors, ladders, steps, Recharge Pods, Grow beds, crops, water's lowered top)
one by one.

A vertex is 24 bytes: position (3 floats), texture (2 floats), and four bytes: shade (face direction and corner
shading), sky light, block light (each 0 to 255 for 0 to 12), and the face's direction (x 32, + 16 where leaves
and plants wave on ultra, + 8 on a tile whose frames play one after another: craft_blocks.ANIMATED, the Server
Rack's blinking LEDs).

edges() gives the lines for the mesh and lines looks: every face's edges (mesh), or only where the surface folds or
the block changes (lines).
"""
import numpy as np

import craft_blocks as B

CHUNK = 16
PAD = 2
# the six directions: +x, -x, +y, -y, +z (up), -z (down)
DIRS = np.array([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)])
# each face's corners (in the block, 0..1), counter-clockwise from outside; and its u and v axes
CORNERS = np.array([
    [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
    [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)],
    [(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)],
    [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    [(0, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0)],
], np.float32)
U_AXIS = np.array([(0, 1, 0), (0, -1, 0), (-1, 0, 0), (1, 0, 0), (1, 0, 0), (1, 0, 0)])
V_AXIS = np.array([(0, 0, 1), (0, 0, 1), (0, 0, 1), (0, 0, 1), (0, 1, 0), (0, -1, 0)])
SIGNS = np.array([(-1, -1), (1, -1), (1, 1), (-1, 1)])  # each corner's side along u and v
FACE_SHADE = np.array([0.8, 0.8, 0.66, 0.66, 1.0, 0.5], np.float32)  # (sides a little darker than the top)
AO = np.array([0.42, 0.62, 0.8, 1.0], np.float32)  # corner shading by how open the corner is (0 to 3)
UV = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], np.float32)
WAVY = {"leaves", "pine_leaves", "pale_leaves", "glowfruit_leaves"}
L = B.LIGHT_MAX
LIGHT_SCALE = 255.0 / L   # (a light level to the vertex's byte)
VERTEX = np.dtype([("pos", np.float32, 3), ("uv", np.float32, 2), ("c", np.uint8, 4)])


class Tables:
    """What the mesher reads for each block id (rebuilt when mods add blocks)."""

    def __init__(self, where):
        n = 256
        self.where = where
        self.cube = np.zeros(n, bool)       # drawn by the cube pass
        self.opaque = np.zeros(n, bool)     # hides its neighbours' faces
        self.pass_ = np.zeros(n, np.uint8)  # 0 solid, 1 cutout, 2 blend
        self.tile_uv = np.zeros((n, 6, 2), np.float32)  # each face's tile corner in the atlas (u0, v0)
        self.wave = np.zeros(n, bool)
        self.anim = np.zeros(n, bool)      # a tile whose frames play (the Server Rack's LEDs)
        size = 1.0 / B.ATLAS
        self.size = size
        for b in B.BLOCKS:
            i = b["id"]
            self.cube[i] = b["shape"] == "cube"
            self.opaque[i] = b["opaque"] and b["shape"] == "cube"
            self.pass_[i] = {"cutout": 1, "blend": 2}.get(b["see"], 0)
            self.wave[i] = b["key"] in WAVY
            self.anim[i] = any(tile in B.ANIMATED for tile in (b["tiles"] or ()))
            if b["tiles"]:
                top, side, bottom = b["tiles"]
                for d, t in enumerate((side, side, side, side, top, bottom)):
                    self.tile_uv[i, d] = self.uv0(t)

    def uv0(self, name):
        col, row = self.where.get(name, (0, 0))
        return (col * self.size, 1.0 - (row + 1) * self.size)


def padded(arr, x0, y0, x1, y1, fill):
    """arr's box [x0:x1, y0:y1, :] with PAD more blocks all round (fill outside the world)."""
    X, Y, Z = arr.shape
    out = np.full((x1 - x0 + 2 * PAD, y1 - y0 + 2 * PAD, Z + 2 * PAD), fill, arr.dtype)
    sx0, sy0 = max(0, x0 - PAD), max(0, y0 - PAD)
    sx1, sy1 = min(X, x1 + PAD), min(Y, y1 + PAD)
    out[sx0 - (x0 - PAD):sx1 - (x0 - PAD), sy0 - (y0 - PAD):sy1 - (y0 - PAD), PAD:PAD + Z] = arr[sx0:sx1, sy0:sy1]
    return out


class Builder:
    """Vertices and triangles for one pass of one chunk."""

    def __init__(self):
        self.parts = []
        self.lines = []

    def add(self, pos, uv, c):
        """pos (n, 4, 3), uv (n, 4, 2), c (n, 4, 4) uint8: n quads."""
        self.parts.append((pos, uv, c))

    def quad(self, corners, uv, shade, sky, glow, d, wave=False):
        """One quad by hand (the shapes that aren't cubes)."""
        c = np.empty((1, 4, 4), np.uint8)  # (sky and glow here are 0 to 1: the light level over 12)
        c[0, :, 0] = int(min(1.0, shade) * 255)
        c[0, :, 1] = int(min(1.0, sky) * 255)
        c[0, :, 2] = int(min(1.0, glow) * 255)
        c[0, :, 3] = d * 32 + (16 if wave else 0)
        self.add(np.asarray(corners, np.float32)[None], np.asarray(uv, np.float32)[None], c)

    def arrays(self):
        """(vertices as bytes, triangle indices as uint32, how many quads)"""
        if not self.parts:
            return None
        pos = np.concatenate([p[0] for p in self.parts]).reshape(-1, 3)
        uv = np.concatenate([p[1] for p in self.parts]).reshape(-1, 2)
        c = np.concatenate([p[2] for p in self.parts]).reshape(-1, 4)
        n = len(pos) // 4
        v = np.empty(len(pos), VERTEX)
        v["pos"], v["uv"], v["c"] = pos, uv, c
        base = (np.arange(n, dtype=np.uint32) * 4)[:, None]
        # the diagonal goes the way that keeps the corner shading even (else a dark corner bleeds over the quad)
        shade = c[:, 0].astype(np.int16).reshape(n, 4)
        flip = (shade[:, 0] + shade[:, 2]) < (shade[:, 1] + shade[:, 3])
        a = np.array([0, 1, 2, 0, 2, 3], np.uint32)
        b = np.array([1, 2, 3, 1, 3, 0], np.uint32)
        idx = np.where(flip[:, None], b[None], a[None]) + base
        return v.tobytes(), idx.astype(np.uint32).ravel(), n


def mesh_chunk(world, cx, cy, tables, look=None):
    """The chunk's three passes (solid, cutout, blend) as Builders, and its lines for a look (mesh or lines): a list
    of (pos (m, 2, 3)) segments, or None."""
    x0, y0 = cx * CHUNK, cy * CHUNK
    x1, y1 = x0 + CHUNK, y0 + CHUNK
    Z = world.Z
    blk = padded(world.blocks, x0, y0, x1, y1, 0)
    blk[:, :, :PAD] = B.FLOOR  # (under the world: solid, so its bottom is never drawn)
    sky = padded(world.sky, x0, y0, x1, y1, L)
    glow = padded(world.glow, x0, y0, x1, y1, 0)
    sky[:, :, Z + PAD:] = L
    t = tables
    opq = t.opaque[blk]
    out = [Builder(), Builder(), Builder()]
    segs = []
    inner = (slice(PAD, PAD + CHUNK), slice(PAD, PAD + CHUNK), slice(PAD, PAD + Z))
    centre = blk[inner]
    is_cube = t.cube[centre]
    origin = np.array([x0 - PAD, y0 - PAD, -PAD], np.float32)
    for d in range(6):
        dx, dy, dz = DIRS[d]
        nb = blk[PAD + dx:PAD + dx + CHUNK, PAD + dy:PAD + dy + CHUNK, PAD + dz:PAD + dz + Z]
        show = is_cube & ~t.opaque[nb] & (nb != centre)
        if not show.any():
            continue
        ix, iy, iz = np.nonzero(show)
        ix, iy, iz = ix + PAD, iy + PAD, iz + PAD  # (in the padded arrays)
        ids = blk[ix, iy, iz]
        ax, ay, az = ix + dx, iy + dy, iz + dz  # the open block the face looks into
        u, v = U_AXIS[d], V_AXIS[d]
        n = len(ix)
        shade = np.empty((n, 4), np.float32)
        light_s = np.empty((n, 4), np.float32)
        light_g = np.empty((n, 4), np.float32)
        for k, (su, sv) in enumerate(SIGNS):
            s1 = (ax + su * u[0], ay + su * u[1], az + su * u[2])
            s2 = (ax + sv * v[0], ay + sv * v[1], az + sv * v[2])
            co = (ax + su * u[0] + sv * v[0], ay + su * u[1] + sv * v[1], az + su * u[2] + sv * v[2])
            o1, o2, oc = opq[s1], opq[s2], opq[co]
            level = np.where(o1 & o2, 0, 3 - (o1.astype(int) + o2 + oc))
            shade[:, k] = AO[level] * FACE_SHADE[d]
            # the light: the four open blocks round the corner, averaged (the face's own always counts)
            cnt = 1 + (~o1).astype(np.float32) + (~o2) + (~oc & ~(o1 & o2))
            ssum = sky[ax, ay, az] + np.where(o1, 0, sky[s1]) + np.where(o2, 0, sky[s2]) + \
                np.where(oc | (o1 & o2), 0, sky[co])
            gsum = glow[ax, ay, az].astype(np.float32) + np.where(o1, 0, glow[s1]) + np.where(o2, 0, glow[s2]) + \
                np.where(oc | (o1 & o2), 0, glow[co])
            light_s[:, k] = ssum / cnt
            light_g[:, k] = gsum / cnt
        pos = CORNERS[d][None] + np.stack([ix, iy, iz], 1)[:, None].astype(np.float32) + origin
        uv = t.tile_uv[ids, d][:, None, :] + UV[None] * t.size
        inset = t.size / 64.0  # (a hair inside the tile: no colour from the next tile at a distance)
        uv = uv + np.where(UV[None] > 0.5, -inset, inset)
        c = np.empty((n, 4, 4), np.uint8)
        c[..., 0] = np.clip(shade * 255, 0, 255)
        c[..., 1] = np.clip(light_s * LIGHT_SCALE, 0, 255)
        c[..., 2] = np.clip(light_g * LIGHT_SCALE, 0, 255)
        c[..., 3] = (d * 32 + np.where(t.wave[ids], 16, 0) + np.where(t.anim[ids], 8, 0))[:, None]
        passes = t.pass_[ids]
        for p in (0, 1, 2):
            sel = passes == p
            if sel.any():
                out[p].add(pos[sel], uv[sel], c[sel])
        if look:
            segs.append(face_edges(look, d, pos, blk, ix, iy, iz, ids, t))
    shapes(world, x0, y0, x1, y1, blk, sky, glow, out, t, segs if look else None)
    lines = np.concatenate(segs) if look and segs else None
    return out, lines


def face_edges(look, d, pos, blk, ix, iy, iz, ids, t):
    """A face's four edges as segments (n*4 or fewer, 2, 3): all of them for mesh; for lines only the edges where the
    surface doesn't carry on flat into the same kind of block."""
    pairs = ((0, 1), (1, 2), (2, 3), (3, 0))
    out = []
    dx, dy, dz = DIRS[d]
    u, v = U_AXIS[d], V_AXIS[d]
    sides = (-v, u, v, -u)  # (the edge's way out from the face's middle)
    for (a, b), e in zip(pairs, sides):
        seg = np.stack([pos[:, a], pos[:, b]], 1)
        if look == "lines":
            nx, ny, nz = ix + e[0], iy + e[1], iz + e[2]
            same = blk[nx, ny, nz] == ids
            open_ = ~t.opaque[blk[nx + dx, ny + dy, nz + dz]]
            keep = ~(same & open_)
            seg = seg[keep]
        out.append(seg)
    return np.concatenate(out) if out else np.zeros((0, 2, 3), np.float32)


def _box(bld, x, y, z, lo, hi, tiles_uv, size, s, g, segs, wave=False, stretch=False):
    """A box from lo to hi (in the block), its faces cut from the tiles (uv0 per direction) to fit (stretch: the
    tile's whole height up each side, as a torch's flame is at the top of its tile)."""
    for d in range(6):
        corners = CORNERS[d] * (np.array(hi) - np.array(lo)) + np.array(lo)
        u0, v0 = tiles_uv[d]
        # the texture cut to the part of the face the box covers (so a slab's side is half a tile)
        if d < 4:
            ax = 1 if d < 2 else 0
            uvs = np.stack([corners[:, ax] if d in (0, 3) else 1 - corners[:, ax], corners[:, 2]], 1)
        else:
            uvs = np.stack([corners[:, 0], corners[:, 1]], 1)
        if stretch and d < 4:
            uvs[:, 1] = (corners[:, 2] - lo[2]) / max(1e-6, hi[2] - lo[2])
        elif stretch and d == 4:  # (the top: the flame's middle)
            uvs = np.array([[0.44, 0.75], [0.56, 0.75], [0.56, 0.8], [0.44, 0.8]])
        uv = np.array([u0, v0]) + np.clip(uvs, 0, 1) * size
        pts = corners + np.array([x, y, z], np.float32)
        bld.quad(pts, uv, FACE_SHADE[d], s, g, d, wave)
        if segs is not None:
            segs.append(np.stack([pts, np.roll(pts, -1, 0)], 1))


def shapes(world, x0, y0, x1, y1, blk, sky, glow, out, t, segs):
    """The blocks that aren't cubes: plants, crops, torches, ladders, doors, slabs, beds, farmland, cacti, water
    and magma. One by one: there are few of them."""
    Z = world.Z
    inner = blk[PAD:PAD + CHUNK, PAD:PAD + CHUNK, PAD:PAD + Z]
    special = ~t.cube[inner] & (inner != 0)
    if not special.any():
        return
    size = t.size
    water, magma = B.ID["water"], B.ID["magma"]
    for ix, iy, iz in zip(*np.nonzero(special)):
        bid = int(inner[ix, iy, iz])
        b = B.BLOCKS[bid]
        shape = b["shape"]
        x, y, z = x0 + ix, y0 + iy, iz
        px, py, pz = ix + PAD, iy + PAD, iz + PAD
        s = sky[px, py, pz] / L
        g = glow[px, py, pz] / L
        meta = int(world.meta[x, y, z])
        tiles = t.tile_uv[bid]
        if shape in ("cross", "crop"):
            uv0 = t.uv0(f"grain_{min(3, meta)}") if shape == "crop" else tiles[0]
            uv = np.array(uv0) + UV * size
            if shape == "cross":
                planes = [[(0.15, 0.15, 0), (0.85, 0.85, 0), (0.85, 0.85, 0.95), (0.15, 0.15, 0.95)],
                          [(0.85, 0.15, 0), (0.15, 0.85, 0), (0.15, 0.85, 0.95), (0.85, 0.15, 0.95)]]
            else:
                planes = [[(0.25, 0, 0), (0.25, 1, 0), (0.25, 1, 0.9), (0.25, 0, 0.9)],
                          [(0.75, 1, 0), (0.75, 0, 0), (0.75, 0, 0.9), (0.75, 1, 0.9)],
                          [(0, 0.25, 0), (1, 0.25, 0), (1, 0.25, 0.9), (0, 0.25, 0.9)],
                          [(1, 0.75, 0), (0, 0.75, 0), (0, 0.75, 0.9), (1, 0.75, 0.9)]]
            for q in planes:
                pts = np.array(q, np.float32) + (x, y, z)
                out[1].quad(pts, uv, 0.9, s, g, 4, wave=True)
                if segs is not None:
                    segs.append(np.stack([pts, np.roll(pts, -1, 0)], 1))
        elif shape == "torch":
            _box(out[1], x, y, z, (0.44, 0.44, 0), (0.56, 0.56, 0.62), tiles, size, max(s, 0.9), 1.0, segs, stretch=True)
        elif shape == "ladder":
            face = meta % 4  # the wall it is on: 0 +x, 1 -x, 2 +y, 3 -y
            lo, hi = [(0.92, 0, 0), (0, 0, 0), (0, 0.92, 0), (0, 0, 0)][face], \
                [(0.97, 1, 1), (0.08, 1, 1), (1, 0.97, 1), (1, 0.08, 1)][face]
            _box(out[1], x, y, z, lo, hi, tiles, size, s, g, segs)
        elif shape == "door":
            facing, opened = meta & 3, bool(meta & 4)
            side = (facing + (1 if opened else 0)) % 4
            lo, hi = [((0, 0, 0), (0.19, 1, 1)), ((0, 0.81, 0), (1, 1, 1)), ((0.81, 0, 0), (1, 1, 1)),
                      ((0, 0, 0), (1, 0.19, 1))][side]
            _box(out[1], x, y, z, lo, hi, tiles, size, s, g, segs)
        elif shape in ("slab", "bed", "farmland"):
            top = {"slab": 0.5, "bed": 0.6, "farmland": 0.875}[shape]
            _box(out[0], x, y, z, (0, 0, 0), (1, 1, top), tiles, size, max(s, sky[px, py, pz + 1] / L),
                 max(g, glow[px, py, pz + 1] / L), segs)
        elif b["key"] == "cactus":
            _box(out[1], x, y, z, (0.06, 0.06, 0), (0.94, 0.94, 1), tiles, size, s, g, segs)
        elif shape == "liquid":
            above = blk[px, py, pz + 1]
            top = 1.0 if above == bid else 0.88
            p = 2 if bid == water else 0
            for d in range(6):
                dx, dy, dz = DIRS[d]
                nb = blk[px + dx, py + dy, pz + dz]
                if nb == bid or t.opaque[nb] or (d == 5):
                    continue
                corners = CORNERS[d].copy()
                corners[:, 2] = np.where(corners[:, 2] > 0.5, top, 0)
                pts = corners + (x, y, z)
                ns = sky[px + dx, py + dy, pz + dz] / L if d == 4 else s
                ng = glow[px + dx, py + dy, pz + dz] / L if d == 4 else g
                uv = np.array(tiles[d]) + UV * size
                out[p].quad(pts, uv, FACE_SHADE[d], max(s, ns), max(g, ng, 0.9 if bid == magma else 0), d,
                            wave=bid == water and d == 4)
                if segs is not None and d == 4:
                    segs.append(np.stack([pts, np.roll(pts, -1, 0)], 1))
