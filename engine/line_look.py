"""The mesh and lines looks (engine.gfx_tiers LOOKS), shared by the games that draw them (CHANGE 145: lifted out of
Kart Lab's kart_gfx.py, CHANGE 144, so Robot Lab draws them with the same code).

    mesh    every triangle's edges in one colour on black (hidden lines: the faces are black and hide what is behind
            them), no lights, textures, sky or smoke
    lines   the same, but only the shapes' outlines (their edges, folds over CREASE degrees and where a colour
            changes), and the game's ground grid (grid() for flat floors), fading into the dark

A game's gfx.init calls init(base, mode, line_colour, fade) instead of making lights and simplepbr (Panda's fixed
pipeline: the cheapest drawing there is), then gives each static or moving piece its look with outline(np_) once it
is built (or blacken() and wire() with a line node from line_node(*edges(...)) worked out once and shared). The
line colour is a learner's choice (settings.json and their profile prefs, line_colour "#rrggbb"): set_line_colour
changes it at once on everything drawn. Nothing here changes a game: the sims never read a picture.

CHANGE 147 (Fight Lab): skinned() gives a model that bends with a skeleton (an Actor) lines that share its vertex
tables, so they bend with it; silhouette() draws the outline of round shapes (bodies, heads, limbs), which have
too few folds for lines to show them.
"""
import math

from panda3d.core import (AntialiasAttrib, CullFaceAttrib, Fog, Geom, GeomLines, GeomNode, GeomVertexData,
                          GeomVertexFormat, InternalName, TransparencyAttrib)

from engine import gfx_tiers

LINE_COLOURS = (("Green", "#33ff66"), ("Amber", "#ffb000"), ("Cyan", "#33e0ff"), ("White", "#f0f0f0"),
                ("Magenta", "#ff4dd2"))
LINE_COLOUR = "#33ff66"  # phosphor green
CREASE = 30.0  # degrees: lines draws an edge where its two faces meet at more than this

_state = {}


def init(base, mode, line_colour=None, fade=(15, 140), far=1000.0):
    """mesh and lines: black, no lights or shaders, and a black fog so the far lines fade into the dark (fade: from
    and to, metres from the camera). line_colour: "#rrggbb" (else phosphor green)."""
    base.setBackgroundColor(0, 0, 0, 1)
    fog = Fog("dark")
    fog.setColor(0, 0, 0)
    fog.setLinearRange(*fade)
    base.render.setFog(fog)
    base.camLens.setFar(far)
    if gfx_tiers.SETTINGS[mode]["msaa"]:
        base.render.setAntialias(AntialiasAttrib.MMultisample)
    try:
        height = base.win.getYSize()
    except Exception:
        height = 720
    _state.clear()
    _state.update(look=mode, lines=[], line_px=max(1.0, round(height / 720 * 1.2, 1)),
                  line_colour=parse_colour(line_colour))


def reset():
    """No look (a game's gfx.init for any other tier)."""
    _state.clear()


def look():
    """"mesh" or "lines" when the tier in use is one of those looks, else None."""
    return _state.get("look")


def colour():
    """The line colour in use, (r, g, b) from 0 to 1."""
    return _state.get("line_colour", parse_colour(None))


def keep(np_):
    """A node the game coloured with colour() by hand (lettering, a lamp's glow): set_line_colour recolours it too."""
    _state.setdefault("lines", []).append(np_)


def parse_colour(text):
    """"#rrggbb" (a learner's line_colour) as (r, g, b) from 0 to 1; anything else is phosphor green."""
    text = text if isinstance(text, str) and len(text) == 7 and text.startswith("#") else LINE_COLOUR
    try:
        return tuple(int(text[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except ValueError:
        return parse_colour(LINE_COLOUR)


def set_line_colour(text):
    """The lines' colour, changed at once on everything already drawn."""
    _state["line_colour"] = parse_colour(text)
    _state["lines"] = [n for n in _state.get("lines", []) if not n.isEmpty()]
    for n in _state["lines"]:
        n.setColor(*_state["line_colour"], 1, 2)


def _arrays(root):
    """Every triangle under root in root's frame, as numpy arrays: the corners (n, 3), the triangles (t, 3) as
    indices into them, and a key per triangle that differs where the material or the vertex colour does."""
    import numpy as np
    nodes = list(root.findAllMatches("**/+GeomNode"))
    if root.node().isGeomNode():
        nodes.insert(0, root)
    points, tris, keys = [], [], []
    count = 0
    seen = {}  # (CHANGE 145) a flattened node's Geoms share one vertex table: it is read once, not once per Geom
    for k, gnp in enumerate(nodes):
        if gnp.isHidden() or gnp.hasNetTag("no_lines"):
            continue
        mat = gnp.getMat(root)
        m = np.array([[mat.getCell(r, c) for c in range(4)] for r in range(4)])
        gn = gnp.node()
        for gi in range(gn.getNumGeoms()):
            geom = gn.getGeom(gi)
            vdata = geom.getVertexData()
            if (k, vdata) in seen:
                start, shade = seen[(k, vdata)]
                for t in _triangles(geom):
                    tris.append(t + start)
                    keys.append((k * 64 + gi) * 4096 + shade[t[:, 0]])
                continue
            fmt = vdata.getFormat()
            ai = fmt.getArrayWith(InternalName.getVertex())
            col = fmt.getColumn(InternalName.getVertex())
            stride = fmt.getArray(ai).getStride()
            raw = np.frombuffer(vdata.getArray(ai).getHandle().getData(), dtype=np.uint8).reshape(-1, stride)
            pos = raw[:, col.getStart():col.getStart() + 12].copy().view(np.float32).reshape(-1, 3).astype(np.float64)
            pos = pos @ m[:3, :3] + m[3, :3]  # (Panda's matrices act on row vectors)
            shade = np.zeros(len(pos), dtype=np.int64)
            if fmt.hasColumn(InternalName.getColor()):
                cai = fmt.getArrayWith(InternalName.getColor())
                ccol = fmt.getColumn(InternalName.getColor())
                craw = np.frombuffer(vdata.getArray(cai).getHandle().getData(), dtype=np.uint8)
                craw = craw.reshape(-1, fmt.getArray(cai).getStride())
                if ccol.getNumericType() == Geom.NT_float32:
                    c = craw[:, ccol.getStart():ccol.getStart() + 12].copy().view(np.float32).reshape(-1, 3)
                    c = np.clip(c * 15 + 0.5, 0, 15).astype(np.int64)
                else:
                    c = craw[:, ccol.getStart():ccol.getStart() + 3].astype(np.int64) // 16
                shade = c[:, 0] * 256 + c[:, 1] * 16 + c[:, 2]
            for t in _triangles(geom):
                tris.append(t + count)
                keys.append((k * 64 + gi) * 4096 + shade[t[:, 0]])
            seen[(k, vdata)] = (count, shade)
            points.append(pos)
            count += len(pos)
    if not points or not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0, dtype=np.int64)
    return np.concatenate(points), np.concatenate(tris), np.concatenate(keys)


def _triangles(geom):
    """A Geom's triangles, (t, 3) indices into its vertex table, one array per primitive."""
    import numpy as np
    out = []
    for pi in range(geom.getNumPrimitives()):
        prim = geom.getPrimitive(pi)
        if prim.getPrimitiveType() != prim.PT_polygons:
            continue
        prim = prim.decompose()
        if prim.isIndexed():
            kind = {Geom.NT_uint8: np.uint8, Geom.NT_uint16: np.uint16}.get(prim.getIndexType(), np.uint32)
            idx = np.frombuffer(prim.getVertices().getHandle().getData(), dtype=kind).astype(np.int64)
        else:
            idx = np.arange(prim.getFirstVertex(), prim.getFirstVertex() + prim.getNumVertices())
        out.append(idx.reshape(-1, 3))
    return out


def edges(root, mode, crease=CREASE):
    """The edges to draw for root's triangles: (points (n, 3), pairs (m, 2)). mode "mesh": every triangle's edges;
    "lines": the outline only, edges with one face (the boundary), edges whose two faces meet at more than crease
    degrees, and edges where the material or colour changes (the kerbs' blocks, the start line's squares). Corners
    within a millimetre are one point (the meshes give each quad its own corners), and each edge is drawn once:
    the points are sorted once (numpy), then each edge is a key in one pass, so the work grows with the triangles."""
    import numpy as np
    pts, tris, keys = _arrays(root)
    if not len(tris):
        return pts, np.zeros((0, 2), dtype=np.int64)
    uniq, inv = np.unique(np.round(pts * 1000).astype(np.int64), axis=0, return_inverse=True)
    t = inv.reshape(-1)[tris]
    good = (t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])
    t, keys = t[good], keys[good]
    pts = uniq / 1000.0
    return pts, _pick(pts, t, keys, mode, crease)


def _pick(pts, t, keys, mode, crease):
    """edges' choice for triangles t (indices into pts, no slivers) with their keys: the (m, 2) pairs to draw."""
    import numpy as np
    e = np.sort(np.stack([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]], axis=1).reshape(-1, 2), axis=1)
    ekey = e[:, 0] * len(pts) + e[:, 1]
    order = np.argsort(ekey, kind="stable")
    ekey = ekey[order]
    starts = np.flatnonzero(np.r_[True, ekey[1:] != ekey[:-1]])
    counts = np.diff(np.r_[starts, len(ekey)])
    first = e[order[starts]]
    if mode == "mesh":
        return first
    face = order // 3  # (each edge's triangle)
    n = np.cross(pts[t[:, 1]] - pts[t[:, 0]], pts[t[:, 2]] - pts[t[:, 0]])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    keep = counts != 2  # an edge of one face is the boundary; three or more faces meet at a fold
    two = np.flatnonzero(counts == 2)
    f1, f2 = face[starts[two]], face[starts[two] + 1]
    fold = np.einsum("ij,ij->i", n[f1], n[f2]) < math.cos(math.radians(crease))
    keep[two] = fold | (keys[f1] != keys[f2])
    return first[keep]


def geom_pairs(geom, mode, crease=CREASE):
    """edges for one Geom, as pairs of rows of its OWN vertex table (CHANGE 147: Fight Lab's skinned fighters): the
    corners within a millimetre are merged to find the edges, as edges() does, and each merged corner is drawn with
    one of its rows. A GeomLines on these rows, sharing the Geom's vertex table, moves with whatever moves those
    rows (an Actor's joints: Panda animates the table once a frame for the faces and the lines together)."""
    import numpy as np
    vdata = geom.getVertexData()
    fmt = vdata.getFormat()
    ai = fmt.getArrayWith(InternalName.getVertex())
    col = fmt.getColumn(InternalName.getVertex())
    stride = fmt.getArray(ai).getStride()
    raw = np.frombuffer(vdata.getArray(ai).getHandle().getData(), dtype=np.uint8).reshape(-1, stride)
    pos = raw[:, col.getStart():col.getStart() + 12].copy().view(np.float32).reshape(-1, 3).astype(np.float64)
    tris = _triangles(geom)
    if not tris:
        return np.zeros((0, 2), dtype=np.int64)
    tris = np.concatenate(tris)
    used = np.unique(tris)
    uniq, inv = np.unique(np.round(pos[used] * 1000).astype(np.int64), axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    row = np.zeros(len(uniq), dtype=np.int64)
    row[inv[::-1]] = used[::-1]  # (each merged corner's first row)
    merged = np.zeros(len(pos), dtype=np.int64)
    merged[used] = inv
    t = merged[tris]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    if not len(t):
        return np.zeros((0, 2), dtype=np.int64)
    return row[_pick(uniq / 1000.0, t, np.zeros(len(t), dtype=np.int64), mode, crease)]


def skinned(np_, mode=None, cache=None, key=""):
    """mesh and lines for a model whose vertices move with a skeleton (CHANGE 147: Fight Lab's detailed fighters,
    Actors): every GeomNode under np_ that is shown gets a lines node under it whose Geoms share its Geoms' vertex
    tables (geom_pairs), so the lines bend with the skin for nothing more than drawing them; its faces go black; on
    lines it gets its outline too (silhouette: the round body has few folds). cache: a dict that keeps each Geom's
    pairs under (key, the node's name, the Geom's number, mode), for the next fighter with the same model. Returns
    the line nodes."""
    import numpy as np
    mode = mode or look()
    out = []
    for gnp in list(np_.findAllMatches("**/+GeomNode")):
        if gnp.hasNetTag("no_lines"):
            continue
        gn = gnp.node()
        node = GeomNode(f"{gnp.getName()} {mode}")
        for gi in range(gn.getNumGeoms()):
            geom = gn.getGeom(gi)
            pairs = cache.get((key, gnp.getName(), gi, mode)) if cache is not None else None
            if pairs is None:
                pairs = geom_pairs(geom, mode)
                if cache is not None:
                    cache[(key, gnp.getName(), gi, mode)] = pairs
            if not len(pairs):
                continue
            lines = GeomLines(Geom.UH_static)
            lines.setIndexType(Geom.NT_uint32)
            lines.modifyVertices().modifyHandle().setData(pairs.astype(np.uint32).tobytes())
            g = Geom(geom.getVertexData())
            g.addPrimitive(lines)
            node.addGeom(g)
        blacken(gnp)
        if node.getNumGeoms():
            out.append(wire(gnp, gnp.attachNewNode(node)))
        if mode == "lines":
            out += silhouette(gnp)
    return out


def silhouette(np_):
    """lines: the outlines of round shapes (CHANGE 147), which have no folds for edges() to find: each GeomNode under
    np_ (itself included) drawn again from its back faces, as thick lines in the line colour; where they are not
    behind its own black front faces, at its outline, they show. The Geoms are shared (an Actor's skin moves them).
    Returns the outline nodes."""
    nodes = list(np_.findAllMatches("**/+GeomNode"))
    if np_.node().isGeomNode():
        nodes.insert(0, np_)
    out = []
    for gnp in nodes:
        gn = gnp.node()
        node = GeomNode(f"{gnp.getName()} outline")
        for gi in range(gn.getNumGeoms()):
            node.addGeom(gn.getGeom(gi).makeCopy())
        if not node.getNumGeoms():
            continue
        sil = wire(gnp, gnp.attachNewNode(node))
        sil.setRenderModeWireframe()
        sil.setRenderModeThickness(_state.get("line_px", 1.0) * 1.7)
        sil.setAttrib(CullFaceAttrib.makeReverse())
        out.append(sil)
    return out


def line_node(name, pts, pairs, extra=None):
    """A GeomLines node for the edges (pairs of indices into pts), plus extra segments ((m, 2, 3) points)."""
    import numpy as np
    if extra is not None and len(extra):
        base = len(pts)
        pts = np.concatenate([pts, extra.reshape(-1, 3)])
        pairs = np.concatenate([pairs, base + np.arange(len(extra) * 2).reshape(-1, 2)])
    used, compact = np.unique(pairs.reshape(-1), return_inverse=True)  # (only the points the lines use)
    vdata = GeomVertexData(name, GeomVertexFormat.getV3(), Geom.UH_static)
    vdata.uncleanSetNumRows(len(used))
    vdata.modifyArray(0).modifyHandle().setData(pts[used].astype(np.float32).tobytes())
    lines = GeomLines(Geom.UH_static)
    lines.setIndexType(Geom.NT_uint32)
    lines.modifyVertices().modifyHandle().setData(compact.astype(np.uint32).tobytes())
    geom = Geom(vdata)
    geom.addPrimitive(lines)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


def wire(np_, lines_np):
    """Give a line node the look: the line colour, no light or texture. (It wins against its own black faces
    because those are pushed back a little, blacken: a depth offset moves polygons, never lines.)"""
    lines_np.setLightOff(3)
    lines_np.setTextureOff(3)
    lines_np.setMaterialOff(3)
    lines_np.setShaderOff(3)
    lines_np.setColor(*_state.get("line_colour", parse_colour(None)), 1, 2)
    lines_np.setRenderModeThickness(_state.get("line_px", 1.0))
    lines_np.setAntialias(AntialiasAttrib.MLine)  # (smoothed lines: blended, so drawn after the black faces)
    lines_np.setTransparency(TransparencyAttrib.M_alpha)
    _state.setdefault("lines", []).append(lines_np)
    return lines_np


def blacken(np_):
    """The faces: black, solid and writing depth, so they hide the lines behind them, and pushed back a little
    (slope-scaled, so the road seen end-on too) so that their own edges are drawn over them whole."""
    np_.setColor(0, 0, 0, 1, 1)
    np_.setDepthOffset(-2, 1)
    np_.setTextureOff(1)
    np_.setMaterialOff(1)
    np_.setLightOff(1)
    np_.setShaderOff(1)
    return np_


def outline(np_, parent=None, mode=None, extra=None):
    """mesh and lines: np_'s faces go black and its edges are drawn as lines (under parent, np_ by default).
    Returns the line node."""
    mode = mode or look()
    pts, pairs = edges(np_, mode)
    blacken(np_)
    node = line_node(f"{np_.getName()} {mode}", pts, pairs, extra)
    return wire(np_, (parent or np_).attachNewNode(node))


def grid(rects, step, z=0.002):
    """A flat ground grid (CHANGE 145: Robot Lab's floor): a line every step metres each way over the rectangles
    (x0, y0, x1, y1), each line cut at their edges and lifted to z. Returns (m, 2, 3) segment ends, for outline's
    extra (or line_node's)."""
    import numpy as np
    segs = []
    for x0, y0, x1, y1 in rects:
        for axis in (0, 1):
            lo, hi = (x0, x1) if axis == 0 else (y0, y1)
            a0, a1 = (y0, y1) if axis == 0 else (x0, x1)
            for c in np.arange(math.ceil(lo / step - 1e-9) * step, hi + 1e-9, step):
                if c <= lo + 1e-6 or c >= hi - 1e-6:
                    continue  # (the rectangle's own edges are its outline)
                p, q = ((c, a0, z), (c, a1, z)) if axis == 0 else ((a0, c, z), (a1, c, z))
                segs.append((p, q))
    return np.array(segs, dtype=np.float64).reshape(-1, 2, 3)
