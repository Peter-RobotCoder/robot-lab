// Craft Lab's chunk meshes for the page (CHANGE 202): craft/craft_mesh.py ported line for line, so a chunk is drawn
// from the very vertices the window draws it from (craft_sim_test.py compares them byte for byte).
//
// Only the faces between a block and an open neighbour are made (a hill is its skin, not its insides). Each corner of
// a face gets corner shading (darker where two blocks meet in a corner) and the light there (the sky's and the
// torches', averaged over the four open blocks it touches); the shader multiplies the atlas by them, so day and night
// are one number. A vertex is the window's 24 bytes: its place (3 floats), its texture (2 floats) and four bytes: the
// shade (the face's direction and the corner shading), the sky light, the block light, and the face's direction (x 32,
// + 16 where leaves and plants wave). numpy's float32 sums are kept (Math.fround) where the window's are float32.
//
// meshChunk(world, cx, cy, tables, look) gives the chunk's three passes (solid, cutout, blend) and, for the mesh and
// lines looks, its edges: every face's edges (mesh), or only where the surface folds or the block changes (lines).
// Places are the game's (x east, y north, z up): craft.js turns them into Babylon's.

import {B} from "./craft_sim.js";

const f32 = Math.fround;
export const CHUNK = 16;
const PAD = 2;
export const DIRS = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
export const CORNERS = [
    [[1, 0, 0], [1, 1, 0], [1, 1, 1], [1, 0, 1]],
    [[0, 1, 0], [0, 0, 0], [0, 0, 1], [0, 1, 1]],
    [[1, 1, 0], [0, 1, 0], [0, 1, 1], [1, 1, 1]],
    [[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]],
    [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]],
    [[0, 1, 0], [1, 1, 0], [1, 0, 0], [0, 0, 0]],
];
const U_AXIS = [[0, 1, 0], [0, -1, 0], [-1, 0, 0], [1, 0, 0], [1, 0, 0], [1, 0, 0]];
const V_AXIS = [[0, 0, 1], [0, 0, 1], [0, 0, 1], [0, 0, 1], [0, 1, 0], [0, -1, 0]];
const SIGNS = [[-1, -1], [1, -1], [1, 1], [-1, 1]];
export const FACE_SHADE = [0.8, 0.8, 0.66, 0.66, 1.0, 0.5].map(f32);
const AO = [0.42, 0.62, 0.8, 1.0].map(f32);
export const UV = [[0, 0], [1, 0], [1, 1], [0, 1]];
const WAVY = new Set(["leaves", "pine_leaves", "pale_leaves"]);

// what the mesher reads for each block id (craft_mesh.Tables): made again when mods add blocks
export class Tables {
    constructor(where, tiles = 16) {
        this.where = where;
        this.size = 1.0 / tiles;
        this.cube = new Uint8Array(256);
        this.opaque = new Uint8Array(256);
        this.pass = new Uint8Array(256);
        this.wave = new Uint8Array(256);
        this.tileUV = new Float32Array(256 * 12);  // (each face's tile corner: u0, v0 for the six directions)
        for (const b of B.blocks) {
            const i = b.id;
            this.cube[i] = b.shape === "cube" ? 1 : 0;
            this.opaque[i] = b.opaque && b.shape === "cube" ? 1 : 0;
            this.pass[i] = {cutout: 1, blend: 2}[b.see] || 0;
            this.wave[i] = WAVY.has(b.key) ? 1 : 0;
            if (b.tiles) {
                const [top, side, bottom] = b.tiles;
                [side, side, side, side, top, bottom].forEach((t, d) => {
                    const [u0, v0] = this.uv0(t);
                    this.tileUV[i * 12 + d * 2] = u0;
                    this.tileUV[i * 12 + d * 2 + 1] = v0;
                });
            }
        }
        this.n = B.blocks.length;
    }

    uv0(name) {
        const [col, row] = this.where[name] || [0, 0];
        return [col * this.size, 1.0 - (row + 1) * this.size];
    }
}

// vertices and triangles for one pass of one chunk (craft_mesh.Builder)
class Builder {
    constructor() {
        this.pos = [];
        this.uv = [];
        this.c = [];
        this.n = 0;
    }

    // one quad: 4 corners (game places), 4 texture places, 4 x 4 bytes
    add(pts, uvs, cs) {
        for (let k = 0; k < 4; k++) {
            this.pos.push(f32(pts[k][0]), f32(pts[k][1]), f32(pts[k][2]));
            this.uv.push(f32(uvs[k][0]), f32(uvs[k][1]));
            this.c.push(cs[k][0], cs[k][1], cs[k][2], cs[k][3]);
        }
        this.n++;
    }

    // one quad by hand (the shapes that aren't cubes): shade (f32: a float32 of the window's), sky and glow 0 to 1
    quad(pts, uvs, shade, sky, glow, d, wave = false) {
        const c0 = Math.trunc(f32(Math.min(1.0, shade) * 255)), c1 = Math.trunc((sky < 1.0 ? sky : 1.0) * 255);
        const c2 = Math.trunc((glow < 1.0 ? glow : 1.0) * 255), c3 = d * 32 + (wave ? 16 : 0);
        const cs = [c0, c1, c2, c3];
        this.add(pts, uvs, [cs, cs, cs, cs]);
    }

    // {pos (Float32Array, 3 a vertex), uv (2), c (Uint8Array, 4), idx (Uint32Array), n quads}, or null
    arrays() {
        if (!this.n) return null;
        const n = this.n, idx = new Uint32Array(n * 6), c = Uint8Array.from(this.c);
        for (let q = 0; q < n; q++) {
            const b = q * 4, s = q * 16;
            // (the diagonal goes the way that keeps the corner shading even)
            const flip = (c[s] + c[s + 8]) < (c[s + 4] + c[s + 12]);
            const o = q * 6;
            if (flip) { idx[o] = b + 1; idx[o + 1] = b + 2; idx[o + 2] = b + 3; idx[o + 3] = b + 1; idx[o + 4] = b + 3; idx[o + 5] = b; }
            else { idx[o] = b; idx[o + 1] = b + 1; idx[o + 2] = b + 2; idx[o + 3] = b; idx[o + 4] = b + 2; idx[o + 5] = b + 3; }
        }
        return {pos: Float32Array.from(this.pos), uv: Float32Array.from(this.uv), c, idx, n};
    }
}

// the chunk's blocks, sky and block light with PAD more all round (craft_mesh.padded)
function padded(world, src, x0, y0, fill) {
    const PX = CHUNK + 2 * PAD, PZ = world.Z + 2 * PAD, Z = world.Z, Y = world.Y;
    const out = new Uint8Array(PX * PX * PZ).fill(fill);
    for (let i = 0; i < PX; i++) {
        const x = x0 - PAD + i;
        if (x < 0 || x >= world.X) continue;
        for (let j = 0; j < PX; j++) {
            const y = y0 - PAD + j;
            if (y < 0 || y >= Y) continue;
            out.set(src.subarray((x * Y + y) * Z, (x * Y + y) * Z + Z), (i * PX + j) * PZ + PAD);
        }
    }
    return out;
}

// the chunk's three passes (solid, cutout, blend) as Builders' arrays, and for a look (mesh or lines) its edges as a
// Float32Array of segments (6 numbers each), or null
export function meshChunk(world, cx, cy, t, look = null) {
    const x0 = cx * CHUNK, y0 = cy * CHUNK, Z = world.Z;
    const PX = CHUNK + 2 * PAD, PZ = Z + 2 * PAD;
    const P = (x, y, z) => (x * PX + y) * PZ + z;
    const blk = padded(world, world.blocks, x0, y0, 0);
    const core = B.id.corestone;
    for (let i = 0; i < PX; i++) for (let j = 0; j < PX; j++) for (let z = 0; z < PAD; z++) blk[P(i, j, z)] = core;
    const sky = padded(world, world.sky, x0, y0, 15);
    const glow = padded(world, world.glow, x0, y0, 0);
    for (let i = 0; i < PX; i++) for (let j = 0; j < PX; j++) for (let z = Z + PAD; z < PZ; z++) sky[P(i, j, z)] = 15;
    const opq = new Uint8Array(blk.length);
    for (let i = 0; i < blk.length; i++) opq[i] = t.opaque[blk[i]];
    const out = [new Builder(), new Builder(), new Builder()];
    const segs = [];
    const size = t.size, inset = size / 64.0;
    const ox = x0 - PAD, oy = y0 - PAD, oz = -PAD;
    for (let d = 0; d < 6; d++) {
        const [dx, dy, dz] = DIRS[d], u = U_AXIS[d], v = V_AXIS[d];
        const faces = [];  // [ix, iy, iz, id, pos (4 corners)] in numpy's order
        for (let i = PAD; i < PAD + CHUNK; i++) {
            for (let j = PAD; j < PAD + CHUNK; j++) {
                for (let k = PAD; k < PAD + Z; k++) {
                    const id = blk[P(i, j, k)];
                    if (!t.cube[id]) continue;
                    const nb = blk[P(i + dx, j + dy, k + dz)];
                    if (t.opaque[nb] || nb === id) continue;
                    faces.push([i, j, k, id]);
                }
            }
        }
        if (!faces.length) continue;
        const posAll = [];
        for (const [i, j, k, id] of faces) {
            const ax = i + dx, ay = j + dy, az = k + dz;
            const cs = [];
            for (let q = 0; q < 4; q++) {
                const [su, sv] = SIGNS[q];
                const s1 = P(ax + su * u[0], ay + su * u[1], az + su * u[2]);
                const s2 = P(ax + sv * v[0], ay + sv * v[1], az + sv * v[2]);
                const co = P(ax + su * u[0] + sv * v[0], ay + su * u[1] + sv * v[1], az + su * u[2] + sv * v[2]);
                const o1 = opq[s1], o2 = opq[s2], oc = opq[co], both = o1 && o2;
                const level = both ? 0 : 3 - (o1 + o2 + oc);
                const shade = f32(AO[level] * FACE_SHADE[d]);
                const cnt = 1 + (o1 ? 0 : 1) + (o2 ? 0 : 1) + (!oc && !both ? 1 : 0);
                const a = P(ax, ay, az);
                const ssum = sky[a] + (o1 ? 0 : sky[s1]) + (o2 ? 0 : sky[s2]) + (oc || both ? 0 : sky[co]);
                const gsum = glow[a] + (o1 ? 0 : glow[s1]) + (o2 ? 0 : glow[s2]) + (oc || both ? 0 : glow[co]);
                const ls = f32(ssum / cnt), lg = f32(gsum / cnt);
                cs.push([Math.trunc(Math.min(255, f32(shade * 255))), Math.trunc(Math.min(255, f32(ls * 17))),
                         Math.trunc(Math.min(255, f32(lg * 17))), d * 32 + (t.wave[id] ? 16 : 0)]);
            }
            const pts = CORNERS[d].map(c => [c[0] + i + ox, c[1] + j + oy, c[2] + k + oz]);
            posAll.push(pts);
            const u0 = t.tileUV[id * 12 + d * 2], v0 = t.tileUV[id * 12 + d * 2 + 1];
            const uvs = UV.map(([a, b]) => [f32(u0 + a * size) + (a > 0.5 ? -inset : inset), f32(v0 + b * size) + (b > 0.5 ? -inset : inset)]);
            out[t.pass[id]].add(pts, uvs, cs);
        }
        if (look) segs.push(faceEdges(look, d, posAll, blk, faces, t, P));
    }
    shapes(world, x0, y0, blk, sky, glow, out, t, look ? segs : null, P);
    let lines = null;
    if (look && segs.length) {
        let n = 0;
        for (const s of segs) n += s.length;
        lines = new Float32Array(n);
        let o = 0;
        for (const s of segs) { lines.set(s, o); o += s.length; }
    }
    return {passes: out.map(b => b.arrays()), lines};
}

// a face's four edges as segments: all of them for mesh; for lines only the edges where the surface doesn't carry on
// flat into the same kind of block (craft_mesh.face_edges: edge 0 of every face, then edge 1...)
function faceEdges(look, d, posAll, blk, faces, t, P) {
    const pairs = [[0, 1], [1, 2], [2, 3], [3, 0]];
    const [dx, dy, dz] = DIRS[d], u = U_AXIS[d], v = V_AXIS[d];
    const sides = [v.map(x => -x), u, v, u.map(x => -x)];
    const out = [];
    pairs.forEach(([a, b], e) => {
        const s = sides[e];
        faces.forEach(([i, j, k, id], f) => {
            if (look === "lines") {
                const nx = i + s[0], ny = j + s[1], nz = k + s[2];
                const same = blk[P(nx, ny, nz)] === id, open = !t.opaque[blk[P(nx + dx, ny + dy, nz + dz)]];
                if (same && open) return;
            }
            const pa = posAll[f][a], pb = posAll[f][b];
            out.push(pa[0], pa[1], pa[2], pb[0], pb[1], pb[2]);
        });
    });
    return out;
}

// a box from lo to hi (in the block), its faces cut from the tiles to fit (craft_mesh._box)
function box(bld, x, y, z, lo, hi, t, id, s, g, segs, wave = false, stretch = false) {
    const size = t.size;
    for (let d = 0; d < 6; d++) {
        const corners = CORNERS[d].map(c => [c[0] * (hi[0] - lo[0]) + lo[0], c[1] * (hi[1] - lo[1]) + lo[1], c[2] * (hi[2] - lo[2]) + lo[2]]);
        const u0 = t.tileUV[id * 12 + d * 2], v0 = t.tileUV[id * 12 + d * 2 + 1];
        let uvs;
        if (d < 4) {
            const ax = d < 2 ? 1 : 0;
            uvs = corners.map(c => [d === 0 || d === 3 ? c[ax] : 1 - c[ax], c[2]]);
        } else uvs = corners.map(c => [c[0], c[1]]);
        if (stretch && d < 4) uvs.forEach((w, q) => { w[1] = (corners[q][2] - lo[2]) / Math.max(1e-6, hi[2] - lo[2]); });
        else if (stretch && d === 4) uvs = [[0.44, 0.75], [0.56, 0.75], [0.56, 0.8], [0.44, 0.8]];
        const clip = w => Math.max(0, Math.min(1, w));
        const uv = uvs.map(([a, b]) => [u0 + clip(a) * size, v0 + clip(b) * size]);
        const pts = corners.map(c => [c[0] + x, c[1] + y, c[2] + z]);
        bld.quad(pts, uv, FACE_SHADE[d], s, g, d, wave);
        if (segs) segs.push(loop(pts));
    }
}

function loop(pts) {  // (a quad's edges: each corner to the next, as np.stack([pts, np.roll(pts, -1, 0)], 1))
    const out = [];
    for (let q = 0; q < 4; q++) { const a = pts[q], b = pts[(q + 1) % 4]; out.push(a[0], a[1], a[2], b[0], b[1], b[2]); }
    return out;
}

const LADDER = [[[0.92, 0, 0], [0.97, 1, 1]], [[0, 0, 0], [0.08, 1, 1]], [[0, 0.92, 0], [1, 0.97, 1]], [[0, 0, 0], [1, 0.08, 1]]];
const DOOR = [[[0, 0, 0], [0.19, 1, 1]], [[0, 0.81, 0], [1, 1, 1]], [[0.81, 0, 0], [1, 1, 1]], [[0, 0, 0], [1, 0.19, 1]]];
const CROSS = [[[0.15, 0.15, 0], [0.85, 0.85, 0], [0.85, 0.85, 0.95], [0.15, 0.15, 0.95]],
               [[0.85, 0.15, 0], [0.15, 0.85, 0], [0.15, 0.85, 0.95], [0.85, 0.15, 0.95]]];
const CROP = [[[0.25, 0, 0], [0.25, 1, 0], [0.25, 1, 0.9], [0.25, 0, 0.9]], [[0.75, 1, 0], [0.75, 0, 0], [0.75, 0, 0.9], [0.75, 1, 0.9]],
              [[0, 0.25, 0], [1, 0.25, 0], [1, 0.25, 0.9], [0, 0.25, 0.9]], [[1, 0.75, 0], [0, 0.75, 0], [0, 0.75, 0.9], [1, 0.75, 0.9]]];

// the blocks that aren't cubes: plants, crops, torches, ladders, doors, slabs, beds, farmland, water and magma, one
// by one (craft_mesh.shapes)
function shapes(world, x0, y0, blk, sky, glow, out, t, segs, P) {
    const Z = world.Z, size = t.size, water = B.id.water, magma = B.id.magma;
    for (let i = 0; i < CHUNK; i++) {
        for (let j = 0; j < CHUNK; j++) {
            for (let k = 0; k < Z; k++) {
                const px = i + PAD, py = j + PAD, pz = k + PAD, p = P(px, py, pz);
                const bid = blk[p];
                if (!bid || t.cube[bid]) continue;
                const b = B.blocks[bid], shape = b.shape;
                const x = x0 + i, y = y0 + j, z = k;
                const s = sky[p] / 15.0, g = glow[p] / 15.0;
                const meta = world.meta[world.at(x, y, z)];
                if (shape === "cross" || shape === "crop") {
                    const [u0, v0] = shape === "crop" ? t.uv0(`wheat_${Math.min(7, meta)}`) : [t.tileUV[bid * 12], t.tileUV[bid * 12 + 1]];
                    const uv = UV.map(([a, c]) => [u0 + a * size, v0 + c * size]);
                    for (const q of shape === "cross" ? CROSS : CROP) {
                        const pts = q.map(c => [f32(c[0]) + x, f32(c[1]) + y, f32(c[2]) + z]);
                        out[1].quad(pts, uv, 0.9, s, g, 4, true);
                        if (segs) segs.push(loop(pts));
                    }
                } else if (shape === "torch") {
                    box(out[1], x, y, z, [0.44, 0.44, 0], [0.56, 0.56, 0.62], t, bid, s < 0.9 ? 0.9 : s, 1.0, segs, false, true);
                } else if (shape === "ladder") {
                    const [lo, hi] = LADDER[meta % 4];
                    box(out[1], x, y, z, lo, hi, t, bid, s, g, segs);
                } else if (shape === "door") {
                    const facing = meta & 3, opened = !!(meta & 4);
                    const [lo, hi] = DOOR[(facing + (opened ? 1 : 0)) % 4];
                    box(out[1], x, y, z, lo, hi, t, bid, s, g, segs);
                } else if (shape === "slab" || shape === "bed" || shape === "farmland") {
                    const top = {slab: 0.5, bed: 0.56, farmland: 0.94}[shape];
                    const sa = sky[P(px, py, pz + 1)] / 15.0, ga = glow[P(px, py, pz + 1)] / 15.0;
                    box(out[0], x, y, z, [0, 0, 0], [1, 1, top], t, bid, sa > s ? sa : s, ga > g ? ga : g, segs);
                } else if (b.key === "cactus") {
                    box(out[1], x, y, z, [0.06, 0.06, 0], [0.94, 0.94, 1], t, bid, s, g, segs);
                } else if (shape === "liquid") {
                    const above = blk[P(px, py, pz + 1)];
                    const top = f32(above === bid ? 1.0 : 0.88);
                    const pass = bid === water ? 2 : 0;
                    for (let d = 0; d < 6; d++) {
                        const [dx, dy, dz] = DIRS[d];
                        const q = P(px + dx, py + dy, pz + dz), nb = blk[q];
                        if (nb === bid || t.opaque[nb] || d === 5) continue;
                        const pts = CORNERS[d].map(c => [c[0] + x, c[1] + y, (c[2] > 0.5 ? top : 0) + z]);
                        const ns = d === 4 ? sky[q] / 15.0 : s, ng = d === 4 ? glow[q] / 15.0 : g;
                        const u0 = t.tileUV[bid * 12 + d * 2], v0 = t.tileUV[bid * 12 + d * 2 + 1];
                        const uv = UV.map(([a, c]) => [u0 + a * size, v0 + c * size]);
                        let gl = g;  // (max(g, ng, 0.9 if magma else 0): the first of equals)
                        if (ng > gl) gl = ng;
                        const extra = bid === magma ? 0.9 : 0;
                        if (extra > gl) gl = extra;
                        out[pass].quad(pts, uv, FACE_SHADE[d], ns > s ? ns : s, gl, d, bid === water && d === 4);
                        if (segs && d === 4) segs.push(loop(pts));
                    }
                }
            }
        }
    }
}
