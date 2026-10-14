// Kart Lab drawn in the browser with Babylon.js, after the app's kart_gfx.py (CHANGE 131: part for part, with its
// colours, textures, roughness and lights): the road as a ribbon following the hills, kerbs, the barrier, the
// chequered start, cones at the sharp bends, the dash pads' glowing chevrons, oil, grass that follows the track and
// rolls away from it, trees, the grandstand and its roof, the start gantry, and the karts (a tub, a cowl, pods,
// bumpers, a driver in a helmet holding the wheel, a wing, an engine, tyres with hubs).
// The engine, tiers, materials and coordinate rules are base3d.js's (shared with Robot Lab and Fight Lab).

/* global BABYLON */

import {BaseScene, TIERS, v3, lerpAngle, mulberry, upwardNormals} from "./base3d.js";

export {TIERS};

const WHEEL_R = 0.2, WHEEL_W = 0.09;
const WHEELS = [[0.5, 0.6], [0.5, -0.6], [-0.52, 0.62], [-0.52, -0.62]];  // x, y: FL, FR, RL, RR
const KERB_RED = [0.85, 0.12, 0.08, 1], KERB_WHITE = [0.95, 0.95, 0.92, 1];
const TARMAC_TINT = [0.9, 0.9, 0.92], GRASS_TINT = [0.95, 1.0, 0.9], STEEL = [0.6, 0.6, 0.62];
const FLAG_DRIFT_L = 1, FLAG_DRIFT_R = 2, FLAG_BOOSTING = 16;
// kart_gfx.init: the sky, the sun 40 degrees up behind the kart, a blue fill, the daytime sky's reflections
const LOOK = {sky: [0.3, 0.5, 0.9], radius: 60, target: [30, 40, 0],
              pbr: {background: [0.3, 0.5, 0.9], exposure: 0.55, ambient: [0.22, 0.25, 0.32], sky: "sky",
                    sun: {colour: [2.6, 2.45, 2.2], offset: [30, -45, 45], film: 40, near: 50.4, far: 90.4, bias: 0.0015}}};

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = a => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

// a mesh built from quads in game coordinates (engine/rw_mesh.py's Mesh, for the track's pieces)
class Geo {
    constructor(coloured = false) {
        this.pos = []; this.nor = []; this.idx = []; this.col = coloured ? [] : null;
        this.colour = [1, 1, 1, 1];
    }

    quad(p, n = null) {  // four corners; n: the normal (else the corners' own, turned up)
        if (!n) {
            n = unit(cross(sub(p[1], p[0]), sub(p[3], p[0])));
            if (n[2] < 0) n = n.map(v => -v);
        }
        const b = this.pos.length / 3;
        for (const q of p) {
            this.pos.push(q[0], q[2], q[1]);
            this.nor.push(n[0], n[2], n[1]);
            if (this.col) this.col.push(...this.colour);
        }
        this.idx.push(b, b + 1, b + 2, b, b + 2, b + 3);
    }

    poly(p, n) {  // a flat fan
        const b = this.pos.length / 3;
        for (const q of p) {
            this.pos.push(q[0], q[2], q[1]);
            this.nor.push(n[0], n[2], n[1]);
            if (this.col) this.col.push(...this.colour);
        }
        for (let i = 1; i < p.length - 1; i++) this.idx.push(b, b + i, b + i + 1);
    }

    mesh(name, scene) {
        const m = new BABYLON.Mesh(name, scene);
        const vd = new BABYLON.VertexData();
        vd.positions = this.pos;
        vd.indices = this.idx;
        vd.normals = this.nor;
        if (this.col) vd.colors = this.col;
        vd.applyToMesh(m);
        return m;
    }
}

export class KartScene extends BaseScene {
    constructor(canvas, tier = "low", engine = null) {
        super(canvas, tier, engine, LOOK);
        this.karts = new Map();     // id -> visual
        this.hints = new Map();     // id -> last track segment (locate's hint)
        this.track = null;
        this.trackMeshes = [];
        this.follow = null;         // kart id the camera chases, or null for the TV camera
        this.mode = "tv";           // tv | chase | overview
        this.build();
    }

    // after build() (and again after a tier change): the track and the karts back in
    populate(rebuild) {
        if (!rebuild) return;
        const track = this.trackData, karts = [...this.karts.values()].map(k => k.design);
        this.karts.clear();
        this.trackMeshes = [];
        if (track) this.setTrack(track);
        for (const d of karts) this.addKart(d);
    }

    // ---------- the track (kart_gfx.TrackVisual) ----------
    setTrack(data) {
        for (const m of this.trackMeshes) m.dispose();
        this.trackMeshes = [];
        this.trackData = data;
        const track = this.track = data;  // (a Track instance from track.js)
        const half = track.half, L = track.length, scene = this.scene;
        const blocks = this.tier === "blocks";
        const statics = [];
        const put = (mesh, mat, cast = false) => {
            mesh.material = mat;
            statics.push(mesh);
            if (cast) this.shadowCast([mesh]);
            return mesh;
        };
        // the road: edge to edge, tarmac tiled every 8 m
        const road = new Geo();
        this.ribbon(road, 0, L, half + 0.3, -half - 0.3, 0.0);
        put(road.mesh("road", scene), this.material("tarmac", blocks ? [0.42, 0.42, 0.45] : TARMAC_TINT, 1.0, 0, 0, {tex: "tarmac", tile: 0.125}));
        // the centre line: white dashes, 2.5 m every 6 m
        const dashes = new Geo();
        for (let s = 3; s < L - 3; s += 6) this.ribbon(dashes, s, s + 2.5, 0.1, -0.1, 0.012, 2.5);
        put(dashes.mesh("dashes", scene), this.material("dashes", [0.85, 0.85, 0.8], 0.7));
        // kerbs (red and white, 2 m blocks), the barrier a metre outside (4 m blocks, every third red), the start's
        // chequers: vertex colours, one mesh
        const paint = new Geo(true);
        for (let s = 0, block = 0; s < L; block++) {
            const e = Math.min(L, s + 2);
            paint.colour = block % 2 ? KERB_RED : KERB_WHITE;
            for (const side of [1, -1]) this.ribbon(paint, s, e, side * (half - 0.55), side * (half + 0.2), 0.03, 2.0);
            s = e;
        }
        const wallIn = half + 1.0, wallOut = half + 1.5, wallH = 0.55;
        for (let s = 0, block = 0; s < L; block++) {
            const e = Math.min(L, s + 4);
            paint.colour = block % 3 === 2 ? [0.8, 0.1, 0.08, 1] : [0.92, 0.92, 0.9, 1];
            const left = this.leftOf((s + e) / 2);
            for (const side of [1, -1]) {
                const lower = p => [p[0], p[1], p[2] - 0.3];
                const a0 = lower(track.point(s, side * wallIn)), a1 = lower(track.point(e, side * wallIn));
                const b0 = lower(track.point(s, side * wallOut)), b1 = lower(track.point(e, side * wallOut));
                const up = [0, 0, wallH], n = left.map(v => v * side);
                paint.quad([a0, a1, add3(a1, up), add3(a0, up)], n.map(v => -v));
                paint.quad([b1, b0, add3(b0, up), add3(b1, up)], n);
                paint.quad([add3(a0, up), add3(a1, up), add3(b1, up), add3(b0, up)], [0, 0, 1]);
            }
            s = e;
        }
        const sq = 0.5, cols = Math.round(2 * half / sq);
        for (let i = 0; i < cols; i++) {
            for (let j = 0; j < 3; j++) {
                paint.colour = (i + j) % 2 ? [0.05, 0.05, 0.05, 1] : [0.95, 0.95, 0.92, 1];
                const lat = -half + i * sq;
                this.ribbon(paint, j * sq - 1.5 * sq, (j + 1) * sq - 1.5 * sq, lat + sq, lat, 0.015, sq);
            }
        }
        put(paint.mesh("paint", scene), this.material("paint", [1, 1, 1], 0.75), true);
        // cones at the apex of each sharp bend
        const cones = [];
        for (let s = 0; s < L; s += 3) {
            const c = this.curvature(s, 18);
            if (Math.abs(c) >= 30) {
                const side = c > 0 ? 1 : -1;
                for (let k = 0; k < 3; k++) {
                    const p = track.point(s + k * 4, side * (half + 0.6));
                    cones.push(this.cyl(null, 0.16, 0.3, "z", this.material("cone", [1.0, 0.45, 0.08], 0.6), p[0], p[1], p[2] + 0.25, 0.03, 10));
                }
                s += 24;
            }
        }
        statics.push(...cones);
        this.shadowCast(cones);
        // dash pads: three glowing chevrons each (their glow pulses in frame())
        const pads = new Geo();
        for (const [ps, plat] of track.boosts) {
            for (let k = 0; k < 3; k++) {
                const a = ps - 1.6 + k * 1.3;
                for (const side of [1, -1]) {
                    const li = plat + side * 0.15, lo = plat + side * 1.3;
                    const p = [track.point(a + 0.9, li), track.point(a + 0.4, li), track.point(a - 0.9, lo), track.point(a - 0.4, lo)];
                    pads.quad(p.map(q => [q[0], q[1], q[2] + 0.02]));
                }
            }
        }
        this.padMat = null;
        if (pads.pos.length) {
            this.padMat = this.material("pads", [0.1, 0.06, 0.0], 0.4, 0, 0, {emission: [3.0, 1.6, 0.2]});
            const m = pads.mesh("pads", scene);
            m.material = this.padMat;
            this.trackMeshes.push(m);
        }
        // oil: dark shiny patches
        const oil = new Geo();
        for (const [os, olat] of track.oil) {
            const pts = [];
            for (let k = 0; k < 14; k++) {
                const a = 2 * Math.PI * k / 14, p = track.point(os + Math.cos(a) * 2.6, olat + Math.sin(a) * 1.9);
                pts.push([p[0], p[1], p[2] + 0.018]);
            }
            oil.poly(pts, [0, 0, 1]);
        }
        if (oil.pos.length) put(oil.mesh("oil", scene), this.material("oil", [0.16, 0.15, 0.2], 0.3, 0.4));
        this.grass(statics);
        this.scenery(statics);
        this.trackMeshes.push(...this.mergeStatic(statics));
        this.setMode(this.mode, this.follow);
    }

    // quads along the track from s0 to s1 between two lateral offsets, lifted off the road
    ribbon(geo, s0, s1, a, b, lift, step = 1.2) {
        const t = this.track, n = Math.max(1, Math.ceil((s1 - s0) / step));
        let prev = null;
        for (let i = 0; i <= n; i++) {
            const s = s0 + (s1 - s0) * i / n;
            const p = t.point(s, a), q = t.point(s, b);
            const edge = [[p[0], p[1], p[2] + lift], [q[0], q[1], q[2] + lift]];
            if (prev) geo.quad([prev[0], edge[0], edge[1], prev[1]]);
            prev = edge;
        }
    }

    leftOf(s) {  // the unit vector pointing left across the track at s
        const h = this.track.heading(s) * Math.PI / 180;
        return [-Math.sin(h), Math.cos(h), 0];
    }

    curvature(s, ahead = 15) {  // degrees the track turns between s and s + ahead (positive: left)
        const h0 = this.track.heading(s), h1 = this.track.heading(s + ahead);
        return ((h1 - h0 + 180) % 360 + 360) % 360 - 180;
    }

    // the grass: a grid at the height of the nearest bit of track, easing to a base level away from it, with
    // gentle rolling bumps (kart_gfx.TrackVisual.grass)
    grass(statics) {
        const track = this.track, half = track.half;
        const [x0, y0, x1, y1] = track.bounds();
        const margin = 45, cell = 3;
        const xs = [], ys = [];
        for (let x = x0 - margin; x < x1 + margin + cell; x += cell) xs.push(x);
        for (let y = y0 - margin; y < y1 + margin + cell; y += cell) ys.push(y);
        const base = Math.min(...track.pts.map(p => p[2])) - 0.8;
        const pos = [], idx = [], z = [];
        for (let j = 0; j < ys.length; j++) {
            for (let i = 0; i < xs.length; i++) {
                const x = xs[i], y = ys[j], at = track.locate(x, y, null);
                let e = Math.min(1, Math.max(0, (at.dist - half - 2) / 30));
                e = e * e * (3 - 2 * e);
                const bumps = 0.8 * Math.sin(x * 0.07 + 1) * Math.cos(y * 0.05) * e;
                const h = (track.point(at.s)[2] - 0.06) * (1 - e) + base * e + bumps;
                z.push(h);
                pos.push(x, h, y);
            }
        }
        const cols = xs.length;
        for (let j = 0; j < ys.length - 1; j++) {
            for (let i = 0; i < cols - 1; i++) {
                const a = j * cols + i;
                idx.push(a, a + 1, a + cols + 1, a, a + cols + 1, a + cols);
            }
        }
        const mesh = new BABYLON.Mesh("grass", this.scene);
        const vd = new BABYLON.VertexData();
        vd.positions = pos;
        vd.indices = idx;
        vd.normals = upwardNormals(pos, idx);
        vd.applyToMesh(mesh);
        mesh.material = this.material("grass", this.tier === "blocks" ? [0.4, 0.66, 0.32] : GRASS_TINT, 1.0, 0, 0, {tex: "grass", tile: 0.2});
        statics.push(mesh);
        this.ground = {xs, ys, z, cell};
    }

    groundZ(x, y) {
        const g = this.ground;
        const i = Math.min(g.xs.length - 1, Math.max(0, Math.round((x - g.xs[0]) / g.cell)));
        const j = Math.min(g.ys.length - 1, Math.max(0, Math.round((y - g.ys[0]) / g.cell)));
        return g.z[j * g.xs.length + i];
    }

    clearOfTrack(x, y, margin) {
        const t = this.track;
        for (let i = 0; i < t.pts.length; i += 3) if (Math.hypot(x - t.pts[i][0], y - t.pts[i][1]) <= t.half + margin) return false;
        return true;
    }

    // trees, the grandstand by the start with its roof, and the start gantry (kart_gfx.TrackVisual.scenery)
    scenery(statics) {
        const t = this.track, half = t.half, L = t.length, scene = this.scene;
        const rnd = mulberry(11);
        const placed = [], casters = [];
        const trunkM = this.material("trunk", [0.35, 0.22, 0.12], 1.0), crownM = this.material("crown", [0.12, 0.42, 0.16], 1.0);
        for (let tries = 0; placed.length < 28 && tries < 400; tries++) {
            const s = rnd() * L, side = rnd() < 0.5 ? 1 : -1;
            const [x, y] = t.point(s, side * (half + 7 + rnd() * 17));
            if (!this.clearOfTrack(x, y, 4) || placed.some(([a, b]) => Math.hypot(x - a, y - b) < 6)) continue;
            if (s < 30 || s > L - 15) continue;  // (the grandstand's spot)
            placed.push([x, y]);
            const z = this.groundZ(x, y), h = 3.5 + rnd() * 2;
            statics.push(this.cyl(null, 0.22, h * 0.25, "z", trunkM, x, y, z + h * 0.25, null, 8));
            const crown = this.cyl(null, h * 0.32, h * 0.38, "z", crownM, x, y, z + h * 0.5 + h * 0.38, 0, 10);
            statics.push(crown);
            casters.push(crown);
        }
        // the grandstand: three tiers facing the track on the left of the start straight
        const stand = new Geo();
        const s0 = -6, s1 = 22, left = this.leftOf((s0 + s1) / 2), along = [left[1], -left[0], 0];
        for (let k = 0; k < 3; k++) {
            const la = half + 5 + k * 1.6, lb = half + 5 + (k + 1) * 1.6, hgt = 0.9 + k * 0.9;
            const a0 = t.point(s0, la), a1 = t.point(s1, la), b0 = t.point(s0, lb), b1 = t.point(s1, lb);
            const baseZ = Math.min(this.groundZ(a0[0], a0[1]), this.groundZ(a1[0], a1[1])) - 0.3;
            for (const p of [a0, a1, b0, b1]) p[2] = baseZ;
            const up = [0, 0, hgt];
            stand.quad([a1, a0, add3(a0, up), add3(a1, up)], left.map(v => -v));
            stand.quad([add3(a0, up), add3(a1, up), add3(b1, up), add3(b0, up)], [0, 0, 1]);
            stand.quad([a0, b0, add3(b0, up), add3(a0, up)], along.map(v => -v));
            stand.quad([b1, a1, add3(a1, up), add3(b1, up)], along);
            if (k === 2) stand.quad([b0, b1, add3(b1, up), add3(b0, up)], left);
        }
        const standMesh = stand.mesh("stand", scene);
        standMesh.material = this.material("stand", [0.55, 0.58, 0.66], 1.0, 0, 0, {tex: "concrete", tile: 0.5});
        statics.push(standMesh);
        casters.push(standMesh);
        const steel = this.material("steel", STEEL, 0.6, 1.0, 0, {tex: "steel"});
        for (const s of [s0 + 1, (s0 + s1) / 2, s1 - 1]) {
            const [x, y] = t.point(s, half + 9.5), z = this.groundZ(x, y);
            const post = this.cyl(null, 0.12, 2.6, "z", steel, x, y, z + 2.6, null, 8);
            statics.push(post);
            casters.push(post);
        }
        const roof = new Geo();
        const r0 = t.point(s0, half + 4.6), r1 = t.point(s1, half + 4.6), q0 = t.point(s0, half + 10.2), q1 = t.point(s1, half + 10.2);
        const zr = this.groundZ(q0[0], q0[1]) + 5.1;
        r0[2] = r1[2] = zr + 0.6;
        q0[2] = q1[2] = zr;
        roof.quad([r0, r1, q1, q0], [0, 0, 1]);
        const roofMesh = roof.mesh("roof", scene);
        roofMesh.material = this.material("roof", [0.85, 0.15, 0.12], 0.7);
        statics.push(roofMesh);
        casters.push(roofMesh);
        // the start gantry: two posts and a beam over the line, with START on both sides
        for (const side of [1, -1]) {
            const [x, y, z] = t.point(0, side * (half + 1.8));
            const post = this.cyl(null, 0.14, 2.6, "z", steel, x, y, z + 2.6, null, 10);
            statics.push(post);
            casters.push(post);
        }
        const a = t.point(0, half + 1.8), b = t.point(0, -half - 1.8), mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
        const beam = this.box(null, 0.2, Math.hypot(a[0] - b[0], a[1] - b[1]) / 2 + 0.2, 0.2, steel, mid[0], mid[1], mid[2] + 5.2);
        beam.rotation.y = -t.heading(0) * Math.PI / 180;
        statics.push(beam);
        casters.push(beam);
        for (const face of [1, -1]) {  // (readable from both sides: each faces its way, a little in front of the beam)
            const h = (t.heading(0) + (face > 0 ? 90 : -90)) * Math.PI / 180;
            const sign = this.signText("START", 2.2);
            sign.position = v3(mid[0] + 0.25 * face * Math.sin(h), mid[1] - 0.25 * face * Math.cos(h), mid[2] + 5.6);
            sign.rotation.y = -h;
            this.trackMeshes.push(sign);
        }
        this.shadowCast(casters);
    }

    // a word standing up, lit from inside (the gantry's sign)
    signText(text, width) {
        const plane = BABYLON.MeshBuilder.CreatePlane("sign", {width, height: width / 4}, this.scene);
        const tex = new BABYLON.DynamicTexture("signtex", {width: 512, height: 128}, this.scene, true);
        tex.hasAlpha = true;
        tex.getContext().clearRect(0, 0, 512, 128);
        tex.drawText(text, null, 100, "bold 100px sans-serif", "#ffffff", null, true, true);
        const m = new BABYLON.StandardMaterial("signmat", this.scene);
        m.diffuseTexture = tex;
        m.useAlphaFromDiffuseTexture = true;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.disableLighting = true;
        m.backFaceCulling = true;
        plane.material = m;
        plane.isPickable = false;
        return plane;
    }

    // ---------- the karts (kart_gfx.KartVisual) ----------
    addKart(design) {
        const id = design.id;
        if (this.karts.has(id)) this.removeKart(id);
        const scene = this.scene;
        const colour = (design.colour || [220, 60, 50]).map(v => v / 255);
        const root = new BABYLON.TransformNode("kart" + id, scene);
        const body = new BABYLON.TransformNode("body" + id, scene);
        body.parent = root;
        const paint = this.material("kpaint", colour, 0.5, 0.2, 0, {tex: "paint", tile: 1.5});
        const dark = this.material("kdark", [0.08, 0.08, 0.09], 0.8);
        const seatM = this.material("kseat", [0.1, 0.1, 0.12], 0.9);
        const suit = this.material("ksuit", colour.map(c => Math.min(1, 0.4 + 0.6 * c)), 0.8);
        const steel = this.material("ksteel", STEEL, 0.5, 1.0, 0, {tex: "steel"});
        const z0 = 0.16;
        const parts = [];
        const box = (hx, hy, hz, mat, x, y, z, roll = 0) => {
            const m = this.box(body, hx, hy, hz, mat, x, y, z);
            m.rotation.x = roll;  // (a roll about the kart's length: Babylon's x is the game's x)
            parts.push(m);
            return m;
        };
        box(0.72, 0.34, 0.07, paint, 0, 0, z0 + 0.07);                                   // the tub
        box(0.28, 0.2, 0.09, paint, 0.42, 0, z0 + 0.2);                                  // the cowl
        box(0.08, 0.55, 0.05, dark, 0.8, 0, z0 + 0.06);                                  // bumpers
        box(0.06, 0.6, 0.05, dark, -0.78, 0, z0 + 0.06);
        for (const side of [1, -1]) box(0.36, 0.1, 0.06, paint, 0, side * 0.44, z0 + 0.1);  // side pods
        box(0.02, 0.14, 0.1, this.material("kplate", [0.95, 0.95, 0.9], 0.6), 0.7, 0, z0 + 0.3);
        box(0.16, 0.19, 0.04, seatM, -0.3, 0, z0 + 0.16);                                // seat
        box(0.04, 0.2, 0.2, seatM, -0.46, 0, z0 + 0.36);
        box(0.13, 0.15, 0.17, suit, -0.28, 0, z0 + 0.36);                                // torso
        for (const side of [1, -1]) parts.push(this.cyl(body, 0.035, 0.2, "x", suit, -0.08, side * 0.14, z0 + 0.42, null, 8));
        parts.push(this.sphere(body, 0.14, this.material("khelmet", [0.95, 0.95, 0.95], 0.25, 0, 0, {tex: "paint", tile: 1.5}), -0.28, 0, z0 + 0.66, 1, 1, 1, 14));
        box(0.03, 0.1, 0.045, this.material("kvisor", [0.05, 0.05, 0.08], 0.1), -0.16, 0, z0 + 0.67);
        parts.push(this.cyl(body, 0.12, 0.012, "x", seatM, 0.1, 0, z0 + 0.45, null, 16));  // the steering wheel
        parts.push(this.cyl(body, 0.02, 0.14, "x", steel, 0.22, 0, z0 + 0.4, null, 8));
        for (const side of [1, -1]) box(0.02, 0.02, 0.12, steel, -0.66, side * 0.3, z0 + 0.26);  // wing posts
        const wing = this.box(body, 0.1, 0.42, 0.015, paint, -0.66, 0, z0 + 0.4);
        wing.rotation.z = -8 * Math.PI / 180;  // (tilted: its front edge down)
        parts.push(wing);
        box(0.12, 0.1, 0.09, this.material("kengine", [0.35, 0.35, 0.38], 0.6, 1.0, 0, {tex: "steel"}), -0.42, 0.28, z0 + 0.22);
        parts.push(this.cyl(body, 0.035, 0.12, "x", this.material("kexhaust", [0.3, 0.3, 0.32], 0.5, 1.0, 0, {tex: "steel"}), -0.7, 0.28, z0 + 0.22, null, 8));
        const flame = this.box(root, 0.25, 0.08, 0.06, this.material("flame", [1.0, 0.6, 0.15], 0.3, 0, 0, {emission: [3.0, 1.4, 0.3]}), -1.0, 0, z0 + 0.12);
        flame.isVisible = false;
        // wheels: a pivot (steering) holding a spinner (rolling) holding the tyre and hub
        const wheels = [];
        const tyreM = this.material("ktyre", [1, 1, 1], 1.0, 0, 0, {tex: "tyre", tile: 2.5});
        const hubM = this.material("khub", [0.75, 0.75, 0.78], 0.5, 1.0, 0, {tex: "steel"});
        const wheelParts = [];
        WHEELS.forEach(([x, y], i) => {
            const pivot = new BABYLON.TransformNode("pivot", scene);
            pivot.parent = root;
            pivot.position = v3(x, y, WHEEL_R);
            const spin = new BABYLON.TransformNode("spin", scene);
            spin.parent = pivot;
            wheelParts.push(this.cyl(spin, WHEEL_R, WHEEL_W, "y", tyreM, 0, 0, 0, null, 20));
            wheelParts.push(this.cyl(spin, WHEEL_R * 0.55, WHEEL_W + 0.006, "y", hubM, 0, 0, 0, null, 14));
            wheels.push({pivot, spin, front: i < 2});
        });
        const merged = this.mergeParts(parts, body);
        this.shadowCast([...merged, ...wheelParts]);
        const label = this.makeLabel(design.name || "", "#ffffff", 1.3);  // (about the app's size: a kart's width)
        label.parent = root;
        label.position = v3(0, 0, 1.15);
        this.karts.set(id, {root, body, wheels, flame, label, design, lastYaw: 0, spin: 0});
    }

    removeKart(id) {
        const k = this.karts.get(id);
        if (!k) return;
        k.label.dispose(false, true);
        k.root.dispose();  // (the materials are shared: kept)
        this.karts.delete(id);
        if (this.follow === id) this.follow = null;
    }

    setKarts(designs) {  // the roster's karts: add new ones, drop gone ones, recolour changed ones
        const wanted = new Map(designs.map(d => [d.id, d]));
        for (const id of [...this.karts.keys()]) if (!wanted.has(id)) this.removeKart(id);
        for (const [id, d] of wanted) {
            const have = this.karts.get(id);
            if (!have || have.design.name !== d.name || String(have.design.colour) !== String(d.colour)) this.addKart(d);
        }
    }

    // ---------- each frame ----------
    // states: Map id -> {x, y, yaw, v, flags, ...} (interpolated); dt in seconds
    frame(states, dt) {
        const track = this.track;
        for (const [id, k] of this.karts) {
            const st = states.get(id);
            if (!st) { k.root.setEnabled(false); continue; }
            k.root.setEnabled(true);
            let z = 0;
            if (track) {
                const at = track.locate(st.x, st.y, this.hints.get(id) ?? null);
                this.hints.set(id, at.seg);
                z = track.point(at.s)[2];
            }
            k.root.position.set(st.x, z, st.y);
            k.root.rotation.y = -st.yaw * Math.PI / 180;
            const drift = (st.flags & FLAG_DRIFT_L) ? 1 : (st.flags & FLAG_DRIFT_R) ? -1 : 0;
            k.body.rotation.x = BABYLON.Scalar.Lerp(k.body.rotation.x, drift * 0.08, 0.2);  // (roll into a drift)
            k.flame.isVisible = !!(st.flags & FLAG_BOOSTING);
            k.spin += (st.v || 0) * dt / WHEEL_R;
            const steer = Math.max(-0.45, Math.min(0.45, (st.u || 0) * 0.08 + drift * 0.3));
            for (const w of k.wheels) {
                w.spin.rotation.z = -k.spin;
                if (w.front) w.pivot.rotation.y = -steer;
            }
        }
        if (this.padMat && this.lighting) {  // the dash pads pulse (kart_gfx.TrackVisual.update)
            const glow = 2.4 + 1.2 * Math.sin(performance.now() / 1000 * 5);
            this.padMat.setVector3("emission", new BABYLON.Vector3(glow, glow * 0.55, glow * 0.07));
        }
        this.updateCamera(states, dt);
        this.followSun();
    }

    updateCamera(states, dt) {
        const cam = this.camera;
        const snap = this.snapCamera;  // (the first frame after a change of camera jumps straight there)
        if (this.mode === "chase" && this.follow !== null && states.has(this.follow)) {
            const st = states.get(this.follow), k = this.karts.get(this.follow);
            if (!k) return;
            const yaw = st.yaw * Math.PI / 180;
            const p = k.root.position;
            const target = new BABYLON.Vector3(p.x + Math.cos(yaw) * 4, p.y + 0.8, p.z + Math.sin(yaw) * 4);
            cam.target = snap ? target : BABYLON.Vector3.Lerp(cam.target, target, Math.min(1, dt * 8));
            // ArcRotate: alpha measured from +x towards +z; behind the kart is the opposite of its heading
            const wantAlpha = Math.atan2(-Math.sin(yaw), -Math.cos(yaw));
            cam.alpha = snap ? wantAlpha : lerpAngle(cam.alpha, wantAlpha, Math.min(1, dt * 4));
            cam.beta = snap ? 1.25 : BABYLON.Scalar.Lerp(cam.beta, 1.25, Math.min(1, dt * 4));
            cam.radius = snap ? 7.5 : BABYLON.Scalar.Lerp(cam.radius, 7.5, Math.min(1, dt * 4));
            this.snapCamera = false;
        } else if (this.mode === "tv") {
            const lead = this.follow !== null && states.has(this.follow) ? this.follow : this.leader;
            const k = lead !== null && lead !== undefined ? this.karts.get(lead) : null;
            if (k) {
                const target = k.root.position.add(new BABYLON.Vector3(0, 0.5, 0));
                cam.target = snap ? target : BABYLON.Vector3.Lerp(cam.target, target, Math.min(1, dt * 3));
                this.snapCamera = false;
            }
        }
    }

    overview() {
        if (!this.track) return;
        const [x0, y0, x1, y1] = this.track.bounds();
        const cam = this.camera;
        cam.target = new BABYLON.Vector3((x0 + x1) / 2, 0, (y0 + y1) / 2);
        cam.radius = Math.max(x1 - x0, y1 - y0) * 1.1;
        cam.alpha = -Math.PI / 2;
        cam.beta = 0.9;
    }

    setMode(mode, follow = null) {
        this.mode = mode;
        this.follow = follow;
        this.snapCamera = true;
        if (mode === "overview") this.overview();
        if (mode === "tv") { this.camera.radius = 18; this.camera.beta = 0.95; }
    }
}
