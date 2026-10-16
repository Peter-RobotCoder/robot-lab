"""engine.model_kit's parts as Panda3D Geoms (CHANGE 145): the window's side of the ultra models (the page reads the
same parts from models/*.json). geom(parts) makes one Geom in rw_mesh's vertex format (with tangents, so the normal
maps work), with a colour per vertex when asked (the parts' colours made linear, their alpha kept)."""
import numpy as np
from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData

from engine.rw_mesh import FORMAT, FORMAT_COLOUR


def uv_tangents(pos, nrm, uv, idx):
    """Each vertex's tangent (along u, square to the normal) and its handedness, from its triangles' texture
    coordinates (where they have none, any direction square to the normal)."""
    tri = idx.reshape(-1, 3)
    e1, e2 = pos[tri[:, 1]] - pos[tri[:, 0]], pos[tri[:, 2]] - pos[tri[:, 0]]
    d1, d2 = uv[tri[:, 1]] - uv[tri[:, 0]], uv[tri[:, 2]] - uv[tri[:, 0]]
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    inv = np.where(np.abs(det) > 1e-12, 1.0 / np.where(np.abs(det) > 1e-12, det, 1.0), 0.0)[:, None]
    sdir = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * inv
    tdir = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * inv
    tan, bit = np.zeros_like(pos), np.zeros_like(pos)
    for k in range(3):
        np.add.at(tan, tri[:, k], sdir)
        np.add.at(bit, tri[:, k], tdir)
    tan -= nrm * (nrm * tan).sum(axis=1, keepdims=True)
    length = np.linalg.norm(tan, axis=1, keepdims=True)
    up = np.where(np.abs(nrm[:, 2:3]) < 0.9, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
    spare = np.cross(up, nrm)
    spare /= np.maximum(np.linalg.norm(spare, axis=1, keepdims=True), 1e-12)
    tan = np.where(length > 1e-9, tan / np.maximum(length, 1e-12), spare)
    w = np.where((np.cross(nrm, tan) * bit).sum(axis=1) < 0, -1.0, 1.0)
    return tan, w


def arrays(parts):
    """The parts' vertices and triangles as numpy arrays: positions, normals, uvs, colours (screen), alpha, indices."""
    base, idx, cols = 0, [], []
    for p in parts:
        idx.append(np.array(p.idx, dtype=np.int64) + base)
        base += len(p.p)
    pos = np.array([v for p in parts for v in p.p], dtype=np.float64).reshape(-1, 3)
    nrm = np.array([v for p in parts for v in p.n], dtype=np.float64).reshape(-1, 3)
    uv = np.array([v for p in parts for v in p.uv], dtype=np.float64).reshape(-1, 2)
    col = np.array([v for p in parts for v in p.c], dtype=np.float64).reshape(-1, 3)
    alpha = np.array([v for p in parts for v in p.a], dtype=np.float64)
    del cols
    return pos, nrm, uv, col, alpha, np.concatenate(idx) if idx else np.zeros(0, dtype=np.int64)


def geom(parts, colours=False, name="model"):
    """One Geom for the parts (all drawn with one material)."""
    pos, nrm, uv, col, alpha, idx = arrays(parts)
    return geom_of(pos, nrm, uv, idx, col if colours else None, alpha, name)


def geom_of(pos, nrm, uv, idx, col=None, alpha=None, name="model", tangents=True):
    """One Geom from numpy arrays (col: screen colours, made linear here; None: no colour column). tangents=False:
    any direction square to the normal (for a part with no normal map: quicker)."""
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    if tangents:
        tan, w = uv_tangents(pos, nrm, uv, idx)
    else:
        up = np.where(np.abs(nrm[:, 2:3]) < 0.9, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
        tan = np.cross(up, nrm)
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-12)
        w = np.ones(len(pos))
    cols = [pos, nrm, uv, tan, w[:, None]]
    if col is not None:
        cols += [np.clip(col, 0.0, None) ** 2.2, (alpha if alpha is not None else np.ones(len(pos)))[:, None]]
    rows = np.hstack(cols).astype(np.float32)
    vdata = GeomVertexData(name, FORMAT_COLOUR if col is not None else FORMAT, Geom.UH_static)
    vdata.uncleanSetNumRows(len(pos))
    vdata.modifyArray(0).modifyHandle().setData(rows.tobytes())
    tris = GeomTriangles(Geom.UH_static)
    tris.setIndexType(Geom.NT_uint32)
    tris.modifyVertices().modifyHandle().setData(idx.astype(np.uint32).tobytes())
    g = Geom(vdata)
    g.addPrimitive(tris)
    return g


def merged(parts, shapes=None, instances=None):
    """Parts and placed shapes merged per material (and far or near), for a few draw calls in all: {(material, far):
    (positions, normals, uvs, colours, alpha, indices)}. instances: {shape: [[x, y, z, h, s, r, g, b], ...]}, each the
    shape turned h degrees about z, scaled by s and moved to x, y, z, its "tint" parts' colours times r, g, b."""
    groups = {}
    for p in parts:
        groups.setdefault((p.material, p.far), []).append(arrays([p]))
    for shape, rows in (instances or {}).items():
        inst = np.array(rows, dtype=np.float64)
        h = np.radians(inst[:, 3])[:, None]
        c, s, k = np.cos(h), np.sin(h), inst[:, 4:5]
        for p in shapes[shape]:
            pos, nrm, uv, col, alpha, idx = arrays([p])
            n, v = len(inst), len(pos)
            P = np.stack([(c * pos[:, 0] - s * pos[:, 1]) * k + inst[:, 0:1], (s * pos[:, 0] + c * pos[:, 1]) * k + inst[:, 1:2],
                          pos[:, 2] * k + inst[:, 2:3]], axis=2).reshape(-1, 3)
            N = np.stack([c * nrm[:, 0] - s * nrm[:, 1], s * nrm[:, 0] + c * nrm[:, 1], np.broadcast_to(nrm[:, 2], (n, v))],
                         axis=2).reshape(-1, 3)
            C = (col[None] * inst[:, None, 5:8] if p.tint else np.broadcast_to(col, (n, v, 3))).reshape(-1, 3)
            I = (idx[None, :] + (np.arange(n) * v)[:, None]).reshape(-1)
            groups.setdefault((p.material, p.far), []).append((P, N, np.tile(uv, (n, 1)), C, np.tile(alpha, n), I))
    out = {}
    for key, items in groups.items():
        base, idx = 0, []
        for item in items:
            idx.append(item[5] + base)
            base += len(item[0])
        out[key] = tuple(np.concatenate([i[j] for i in items]) for j in range(5)) + (np.concatenate(idx),)
    return out


def node(parts, colours=False, name="model"):
    n = GeomNode(name)
    n.addGeom(geom(parts, colours, name))
    return n
