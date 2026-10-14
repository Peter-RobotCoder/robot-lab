// Fight Lab in Club Coders Live (CHANGE 130): the hall and its rings (fight_sim.py's constants, drawn after
// fight_gfx.StageVisual), the hazards from each snapshot (fire jets, spikes, ice, ropes or an open edge), the
// fighters built from their designs on a 13-joint skeleton and posed by the game's own pose code (fight_gfx.py's
// stance, attacks, falls, ported line for line below), the 30-a-second JSON states blended two behind, and the
// teacher's Fight Lab controls. The skinned models (woman, man, Robin) are drawn as the primitive human or robot in
// their colours, with their weapon, until the page loads the models themselves.
// Panda joint angles (h, p, r) are Babylon rotation (-p, -h, -r); positions game (x, y, z) -> Babylon (x, z, y).

/* global BABYLON */

import {BaseScene, v3, rgb255, lerp, lerpDeg} from "./base3d.js";

const $ = id => document.getElementById(id);
const D2R = Math.PI / 180;
const RING_CENTRES = [[0, 0], [16, 0], [-16, 0], [0, 16], [16, 16], [-16, 16]];
const MAT_COLOURS = [[0.12, 0.13, 0.2], [0.35, 0.06, 0.06], [0.06, 0.2, 0.12], [0.2, 0.08, 0.3], [0.3, 0.2, 0.05], [0.05, 0.18, 0.3]];
const PAD_COLOURS = [[0.85, 0.1, 0.1], [0.95, 0.95, 0.95], [0.1, 0.25, 0.85]];
const JET_ANGLES = [45, 135, 225, 315];
const MOVES = new Set(["punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam", "cartwheel"]);

// ---------- the poses (fight_gfx.py, verbatim in meaning) ----------
const THIGH = 0.42, SHIN = 0.42, ANKLE = 0.08, HIP_H = THIGH + SHIN + ANKLE, UPPER = 0.29, FORE = 0.26;
const JOINTS = ["hips", "waist", "neck", "ls", "le", "rs", "re", "lh", "lk", "la", "rh", "rk", "ra"];
const deg = r => r * 180 / Math.PI;

function leg(forward, hipH) {
    const down = Math.max(0.2, hipH - ANKLE);
    const d = Math.min(THIGH + SHIN - 1e-4, Math.hypot(forward, down));
    const bend = Math.PI - Math.acos(Math.max(-1, Math.min(1, (THIGH ** 2 + SHIN ** 2 - d ** 2) / (2 * THIGH * SHIN))));
    const alpha = Math.acos(Math.max(-1, Math.min(1, (THIGH ** 2 + d ** 2 - SHIN ** 2) / (2 * THIGH * d))));
    const thigh = Math.atan2(forward, down) + alpha;
    const knee = -bend;
    return [deg(thigh), deg(knee), -deg(thigh + knee)];
}

function pose(hz = 0.84, lift = 0, joints = {}) {
    const p = {hz, lift};
    for (const j of JOINTS) p[j] = joints[j] ? [...joints[j]] : [0, 0, 0];
    return p;
}

function legs(p0, lead, rear, hz = null, spread = 7, liftL = 0, liftR = 0) {
    const p = {...p0};
    const h = hz === null ? p.hz : hz;
    for (const [name, fwd, lift, roll] of [["l", lead, liftL, -spread], ["r", rear, liftR, spread]]) {
        const [t, k, a] = leg(fwd, h - lift);
        p[name + "h"] = [0, t, roll];
        p[name + "k"] = [0, k, 0];
        p[name + "a"] = [0, a, -roll];
    }
    return p;
}

function blend(a, b, f) {
    f = Math.max(0, Math.min(1, f));
    const out = {};
    for (const [k, va] of Object.entries(a)) {
        const vb = b[k];
        out[k] = Array.isArray(va) ? va.map((x, i) => x + (vb[i] - x) * f) : va + (vb - va) * f;
    }
    return out;
}

const ease = f => { f = Math.max(0, Math.min(1, f)); return f * f * (3 - 2 * f); };
const set = (p, o) => ({...p, ...o});

function stance(bob = 0) {
    const p = pose(0.82 + bob, 0, {hips: [-28, 0, 0], waist: [-4, 6, 0], neck: [30, -4, 0], ls: [10, 55, -18], le: [0, 105, 0],
                                   rs: [20, 32, -10], re: [0, 128, 0]});
    return legs(p, 0.26, -0.2);
}

function guard(p) {
    return set(p, {ls: [25, 78, -30], le: [0, 118, 0], rs: [-5, 72, -8], re: [0, 122, 0]});
}

function crouchPose() {
    const p = set(stance(), {hz: 0.5, waist: [-4, 22, 0], neck: [30, -18, 0]});
    return legs(p, 0.32, -0.12, null, 16);
}

function attackPoses(name) {
    const s = stance();
    if (name === "punch") {
        const wind = set(s, {rs: [10, 25, -12], re: [0, 140, 0], waist: [-12, 8, 0]});
        const hit = set(s, {rs: [-5, 88, -4], re: [0, 4, 0], waist: [22, 10, 0], neck: [8, -6, 0], hips: [-12, 0, 0], ls: [10, 45, -22], le: [0, 120, 0]});
        return [wind, legs(hit, 0.3, -0.26, 0.8)];
    }
    if (name === "kick") {
        let wind = legs(set(s, {waist: [-8, -6, 0], hz: 0.84}), 0.05, -0.2, 0.84);
        wind = set(wind, {rh: [0, 85, 6], rk: [0, -115, 0], ra: [0, 30, 0]});
        let hit = legs(set(s, {waist: [-10, -18, 0], neck: [20, 12, 0], hips: [-10, 0, 0]}), 0.02, -0.2, 0.86);
        hit = set(hit, {rh: [0, 92, 4], rk: [0, -4, 0], ra: [0, 40, 0]});
        return [wind, hit];
    }
    if (name === "low") {
        let wind = legs(set(crouchPose(), {hz: 0.45}), 0.15, -0.1, 0.45, 20);
        let hit = set(wind, {waist: [10, 38, 0], neck: [0, -35, 0], hips: [-50, 0, 0], ls: [0, 70, -30], le: [0, 20, 0], rs: [0, 60, 25], re: [0, 20, 0]});
        hit = set(legs(hit, 0.1, 0.0, 0.42, 20), {rh: [-20, 62, 55], rk: [0, -4, 0], ra: [0, 25, 0]});
        return [wind, hit];
    }
    if (name === "high") {
        const wind = set(legs(set(s, {waist: [-20, -5, 0]}), 0.1, -0.15, 0.86), {rh: [0, 80, 25], rk: [0, -110, 0], ra: [0, 30, 0]});
        let hit = set(s, {waist: [-30, -26, -12], neck: [35, 18, 8], hips: [-45, 0, -10], ls: [0, 50, -45], le: [0, 70, 0], rs: [0, 20, 35], re: [0, 60, 0]});
        hit = set(legs(hit, 0.0, -0.1, 0.9), {rh: [0, 118, 22], rk: [0, -5, 0], ra: [0, 30, 0]});
        return [wind, hit];
    }
    if (name === "jump_kick") {
        const wind = set(s, {lh: [0, 80, -6], lk: [0, -120, 0], rh: [0, 60, 6], rk: [0, -110, 0], waist: [0, 10, 0], hz: 0.9});
        const hit = set(s, {lh: [0, 60, -6], lk: [0, -115, 0], rh: [0, 95, 4], rk: [0, -2, 0], ra: [0, 30, 0], waist: [-10, -20, 0], hips: [-20, 0, 0],
                            ls: [0, 40, -40], le: [0, 90, 0], rs: [0, -20, 30], re: [0, 30, 0], hz: 0.95});
        return [wind, hit];
    }
    if (name === "throw") {
        const wind = legs(set(s, {ls: [-10, 82, -8], le: [0, 25, 0], rs: [10, 82, 8], re: [0, 25, 0], waist: [0, 18, 0], hips: [0, 0, 0]}), 0.3, -0.25, 0.78);
        const hit = set(wind, {ls: [-10, 150, -20], le: [0, 40, 0], rs: [10, 150, 20], re: [0, 40, 0], waist: [60, -25, 0], neck: [-20, 10, 0], hips: [40, 0, 0]});
        return [wind, hit];
    }
    if (name === "blast") {
        const wind = legs(set(s, {ls: [20, -20, -10], le: [0, 100, 0], rs: [-20, -20, 10], re: [0, 100, 0], waist: [-30, 5, 0], hips: [-40, 0, 0], neck: [40, 0, 0]}), 0.3, -0.25, 0.72, 14);
        const hit = legs(set(wind, {ls: [-12, 88, -6], le: [0, 8, 0], rs: [12, 88, 6], re: [0, 8, 0], waist: [0, 6, 0], hips: [0, 0, 0], neck: [0, -4, 0]}), 0.35, -0.3, 0.72, 14);
        return [wind, hit];
    }
    if (name === "uppercut") {
        const wind = set(crouchPose(), {rs: [0, -15, 5], re: [0, 100, 0], waist: [-25, 30, 0]});
        let hit = set(s, {rs: [-10, 172, 10], re: [0, 12, 0], waist: [20, -14, 0], neck: [-10, 10, 0], hips: [0, 0, 0], ls: [0, 20, -30], le: [0, 90, 0], lift: 0.35});
        hit = set(legs(hit, 0.1, -0.05, 0.92), {lh: [0, 55, -6], lk: [0, -80, 0]});
        return [wind, hit];
    }
    if (name === "spin_kick") {
        const wind = legs(set(s, {waist: [-30, 0, 0], ls: [0, 30, -70], le: [0, 40, 0], rs: [0, 30, 70], re: [0, 40, 0]}), 0.05, -0.1, 0.86);
        const hit = set(wind, {waist: [0, -6, -18], hips: [0, 0, -15], ls: [0, 10, -85], le: [0, 10, 0], rs: [0, 10, 70], re: [0, 10, 0], lift: 0.15,
                               rh: [0, 15, 88], rk: [0, -4, 0], ra: [0, 0, 0]});
        return [wind, hit];
    }
    if (name === "slam") {
        const wind = legs(set(s, {ls: [-10, 85, -8], le: [0, 30, 0], rs: [10, 85, 8], re: [0, 30, 0], waist: [0, 20, 0]}), 0.3, -0.25, 0.76);
        const lift = set(wind, {ls: [-10, 175, -12], le: [0, 20, 0], rs: [10, 175, 12], re: [0, 20, 0], waist: [0, -20, 0], neck: [0, 15, 0]});
        return [wind, lift];
    }
    if (name === "cartwheel") {
        const wind = pose(0.86, 0, {ls: [0, 172, -15], le: [0, 8, 0], rs: [0, 172, 15], re: [0, 8, 0], lh: [0, 0, -35], lk: [0, -5, 0], rh: [0, 0, 35], rk: [0, -5, 0]});
        return [wind, set(wind, {lh: [0, 0, -55], rh: [0, 0, 55]})];
    }
    return [s, s];
}

function cartwheelTurn(k) {
    if (k < 1) return 180 * Math.max(0, k);
    if (k < 2) return 180 + 120 * (k - 1);
    return 300 + 60 * Math.min(1, (k - 2) / 0.4);
}

function slamDown() {
    const p = set(stance(), {ls: [-10, 110, -8], le: [0, 10, 0], rs: [10, 110, 8], re: [0, 10, 0], waist: [0, 45, 0], neck: [0, -30, 0]});
    return legs(p, 0.35, -0.3, 0.62, 18);
}

function lying(faceUp = true, spread = 0) {
    return pose(0.16, 0, {hips: [0, faceUp ? 88 : -88, 0], neck: [0, -8, 0], ls: [0, 10 + 60 * spread, -30 - 40 * spread], le: [0, 20, 0],
                          rs: [0, 10 + 40 * spread, 30 + 50 * spread], re: [0, 30, 0], lh: [0, 8, -10], lk: [0, -10, 0], rh: [0, 25, 12], rk: [0, -40, 0]});
}

function animPose(a, k) {
    a = {hit_body: "hitstun", swept: "knockdown"}[a] || a;
    if (a === "idle") {
        const p = stance(0.015 * Math.sin(k * 5));
        p.le = [0, 105 + 4 * Math.sin(k * 5 + 1), 0];
        return p;
    }
    if (a === "walk_f" || a === "walk_b") {
        const ph = k * 2 * Math.PI / 0.8 * (a === "walk_f" ? 1 : -1);
        const p = stance(0.015 * Math.cos(2 * ph)), s = Math.sin(ph);
        return legs(p, 0.24 + 0.14 * s, -0.2 - 0.14 * s, null, 7, Math.max(0, Math.cos(ph)) * 0.08, Math.max(0, -Math.cos(ph)) * 0.08);
    }
    if (a === "side_l" || a === "side_r") {
        const ph = k * 2 * Math.PI / 0.7;
        const s = Math.sin(ph) * (a === "side_l" ? 1 : -1);
        const p = legs(stance(0.02 * Math.cos(2 * ph)), 0.24, -0.2, null, 8 + 10 * s, Math.max(0, Math.cos(ph)) * 0.07, Math.max(0, -Math.cos(ph)) * 0.07);
        p.hips = [-28, 0, 4 * s];
        return p;
    }
    if (a === "crouch") return crouchPose();
    if (a === "block") return guard(stance());
    if (a === "low_block") return set(guard(crouchPose()), {ls: [25, 48, -30], le: [0, 120, 0]});
    if (a === "blockstun") return set(guard(stance()), {waist: [-4, -10 * (1 - k), 0]});
    if (a === "hitstun") {
        const f = k > 0.15 ? Math.sin(Math.min(1, k) * Math.PI) : k / 0.15;
        return set(stance(), {waist: [-4, 6 - 32 * f, 6 * f], neck: [30, -4 - 35 * f, 0], ls: [10, 40 - 30 * f, -18 - 35 * f],
                              rs: [20, 30 - 20 * f, -10 + 40 * f], le: [0, 60, 0], re: [0, 70, 0]});
    }
    if (a === "hit_low") {
        const f = k > 0.15 ? Math.sin(Math.min(1, k) * Math.PI) : k / 0.15;
        return set(crouchPose(), {waist: [-4, 22 + 25 * f, 0], neck: [30, -18 + 20 * f, 0], ls: [0, 30, -10], le: [0, 90, 0], rs: [0, 30, 10], re: [0, 90, 0]});
    }
    if (a === "launched" || a === "ringout") {
        const f = Math.min(1, k / 0.35), wob = Math.sin(k * 14);
        const p = pose(0.84, 0, {hips: [0, 55 * f, 10 * wob], waist: [0, -20, 0], neck: [0, -25, 0], ls: [0, 100 + 30 * wob, -60], le: [0, 30, 0],
                                 rs: [0, 100 - 30 * wob, 60], re: [0, 30, 0], lh: [0, 40 + 20 * wob, -12], lk: [0, -60, 0], rh: [0, 20 - 20 * wob, 12], rk: [0, -30, 0]});
        if (a === "ringout") p.hips = [0, 20 * wob, 15 * wob];
        return p;
    }
    if (a === "thrown") return set(animPose("launched", k), {hips: [0, Math.min(1, k / 0.5) * 200, 0]});
    if (a === "knockdown") return k < 0.25 ? blend(animPose("launched", 0.4), lying(), k / 0.25) : lying();
    if (a === "ko") return lying(true, 1);
    if (a === "getup") {
        const kneel = set(legs(pose(0.5, 0, {waist: [0, 35, 0], neck: [0, -20, 0], ls: [0, 20, -20], le: [0, 40, 0], rs: [0, 60, 10], re: [0, 30, 0]}), 0.35, -0.3, null, 12), {rk: [0, -140, 0]});
        return k < 0.5 ? blend(lying(), kneel, ease(k * 2)) : blend(kneel, stance(), ease((k - 0.5) * 2));
    }
    if (a === "jump") {
        const tuck = pose(0.84, 0, {waist: [0, 15, 0], ls: [10, 55, -18], le: [0, 105, 0], rs: [20, 40, -10], re: [0, 120, 0],
                                    lh: [0, 80, -6], lk: [0, -120, 0], la: [0, 30, 0], rh: [0, 55, 6], rk: [0, -110, 0], ra: [0, 40, 0]});
        const crouched = crouchPose();
        if (k < 0.15) return blend(crouched, tuck, k / 0.15);
        if (k > 0.85) return blend(tuck, crouched, (k - 0.85) / 0.15);
        return tuck;
    }
    if (a === "win") {
        const wave = Math.sin(k * 6) * 6;
        return set(legs(stance(), 0.2, -0.2, 0.9, 10), {hips: [-10, 0, 0], waist: [10, -8, 0], neck: [0, 8, 0], rs: [0, 168 + wave, 12], re: [0, 15, 0], ls: [0, 15, -35], le: [0, 95, 0]});
    }
    if (a === "intro") return animPose("idle", k);
    if (MOVES.has(a)) {
        const [wind, hit] = attackPoses(a);
        const s = a !== "jump_kick" ? stance() : animPose("jump", 0.5);
        if (a === "slam") {
            if (k < 1) return blend(s, wind, ease(k));
            if (k < 2) return blend(wind, hit, ease(k - 1));
            return blend(slamDown(), s, ease((k - 2) * 1.2 - 0.2));
        }
        if (k < 1) return blend(s, wind, ease(k));
        if (k < 2) return blend(wind, hit, ease(Math.min(1, (k - 1) * 3)));
        return blend(hit, s, ease(k - 2));
    }
    return stance();
}

// ---------- the scene ----------
export class FightScene extends BaseScene {
    constructor(canvas, tier, engine) {
        super(canvas, tier, engine, {sky: [0.02, 0.02, 0.04], fog: [0.02, 0.02, 0.04], fogDensity: 0.004, radius: 9,
                                     target: [0, 0, 1], shadowSize: 30, ground: [0.1, 0.1, 0.14], hemi: 0.45, sun: 1.5,
                                     sunDir: [-0.25, -0.9, 0.45]});
        this.setup = {rings: [0], rs: 4.5, hazards: {}, look: {}};
        this.fighters = new Map();
        this.list = [];
        this.mode = "fight";
        this.ringMeshes = new Map();
        this.blasts = [];
        this.sparks = [];
        this.build();
    }

    populate() {
        this.buildStage();
        const list = this.list;
        this.fighters.clear();
        for (const f of list) this.addFighter(f);
    }

    setSetup(setup) {
        const key = JSON.stringify(setup);
        if (key === this.setupKey) return;
        this.setupKey = key;
        this.setup = setup;
        this.build();
    }

    buildStage() {
        const {rings, rs: R, hazards: hz, look} = this.setup;
        const roped = !hz.ring_out;
        this.box(null, 30, 22, 0.1, this.material("hall", [0.3, 0.3, 0.34], 1.0), 0, 8, -0.9).receiveShadows = this.lit;
        const steel = this.material("steel", [0.2, 0.2, 0.23], 0.4, 0.8);
        const white = this.material("white", [0.9, 0.9, 0.95], 0.6);
        this.jets = new Map();
        this.ropes = [];
        for (const i of rings || [0]) {
            const [cx, cy] = RING_CENTRES[i] || [0, 0];
            const platR = roped ? R + 0.7 : R + 0.1;
            this.cyl(null, platR, 0.4, "z", steel, cx, cy, -0.42, null, 40);
            const mat = this.cyl(null, platR - 0.02, 0.002, "z", this.material("mat" + i, MAT_COLOURS[i % 6], 0.85), cx, cy, 0, null, 48);
            mat.receiveShadows = this.lit;
            if (!hz.slippery) for (let k = 0; k < 40; k++) {
                const a = k / 40 * Math.PI * 2;
                const d = this.box(null, 0.14, 0.04, 0.002, white, cx + Math.cos(a) * 0.45 * R, cy + Math.sin(a) * 0.45 * R, 0.004);
                d.rotation.y = -(a + Math.PI / 2);
            }
            for (const sx of [-1.6, 1.6]) this.box(null, 0.05, 0.45, 0.002, white, cx + sx, cy, 0.004);
            this.floorText(i === 0 ? (look.name || "FIGHT LAB") : `RING ${i + 1}`, cx, cy - 0.25, 0.008, 3.4, "#f2bf1a");
            if (roped) {
                const postR = (R + 0.08) / Math.cos(22.5 * D2R);
                const posts = [];
                for (let k = 0; k < 8; k++) {
                    const a = (22.5 + 45 * k) * D2R, px = cx + Math.cos(a) * postR, py = cy + Math.sin(a) * postR;
                    posts.push([px, py]);
                    this.cyl(null, 0.08, 0.7, "z", this.material("post", [0.6, 0.62, 0.66], 0.4, 0.8), px, py, 0.7, null, 10);
                    this.box(null, 0.12, 0.12, 0.45, this.material("pad" + (k % 3), PAD_COLOURS[k % 3], 0.8), px, py, 0.85);
                }
                const ropeMat = hz.electric_ropes ? this.material("eropes", [0.5, 0.8, 1.0], 0.4, 0, 1.2) : this.material("ropes", [0.85, 0.12, 0.1], 0.6);
                for (const z of [0.45, 0.85, 1.25]) for (let k = 0; k < 8; k++) {
                    const [ax, ay] = posts[k], [bx, by] = posts[(k + 1) % 8];
                    const rope = BABYLON.MeshBuilder.CreateTube("rope", {path: [v3(ax, ay, z), v3(bx, by, z)], radius: 0.035, tessellation: 6}, this.scene);
                    rope.material = ropeMat;
                    this.ropes.push(rope);
                }
            } else {
                const band = BABYLON.MeshBuilder.CreateTorus("edge", {diameter: R * 2, thickness: 0.09, tessellation: 64}, this.scene);
                band.material = this.material("edge", [1, 0.45, 0.1], 0.5, 0, 1.5);
                band.scaling.y = 0.1;
                band.position = v3(cx, cy, 0.006);
            }
            if (hz.fire_jets) {
                const jets = JET_ANGLES.map(a => {
                    const x = cx + Math.cos(a * D2R) * 0.55 * R, y = cy + Math.sin(a * D2R) * 0.55 * R;
                    this.cyl(null, 0.32, 0.004, "z", this.material("yellow", [0.95, 0.75, 0.08], 0.6), x, y, 0.006, null, 20);
                    this.cyl(null, 0.16, 0.03, "z", steel, x, y, 0.03, null, 12);
                    const flame = BABYLON.MeshBuilder.CreateCylinder("jet", {height: 1, diameterBottom: 0.5, diameterTop: 0.05, tessellation: 10}, this.scene);
                    flame.material = this.glass("fire", [1, 0.55, 0.12], 0.75);
                    flame.material.emissiveColor = new BABYLON.Color3(1, 0.5, 0.1);
                    flame.position = v3(x, y, 0.5);
                    flame.isVisible = false;
                    return flame;
                });
                this.jets.set(i, jets);
            }
            if (hz.spikes) for (const a of [0, 90, 180, 270]) {
                const x = cx + Math.cos(a * D2R) * 0.78 * R, y = cy + Math.sin(a * D2R) * 0.78 * R;
                this.cyl(null, 0.45, 0.004, "z", this.material("yellow", [0.95, 0.75, 0.08], 0.6), x, y, 0.006, null, 20);
                for (let k = 0; k < 7; k++) {
                    const r = k ? 0.27 : 0, b = k * Math.PI / 3;
                    this.cyl(null, 0.06, 0.12, "z", this.material("spike", [0.7, 0.72, 0.76], 0.3, 0.9), x + Math.cos(b) * r, y + Math.sin(b) * r, 0.14, 0, 8);
                }
            }
            if (hz.slippery) this.cyl(null, 0.45 * R, 0.003, "z", this.material("ice", [0.55, 0.75, 0.92], 0.06, 0.2, 0.15), cx, cy, 0.006, null, 40);
        }
    }

    // ---------- the fighters ----------
    setFighters(list) {
        for (const f of this.fighters.values()) { f.root.dispose(false, true); f.label.dispose(); }
        this.fighters.clear();
        this.list = list;
        for (const f of list) this.addFighter(f);
    }

    addFighter(info) {
        const d = info.design || {}, scene = this.scene, style = d.style || {};
        const boss = !!d.model;
        const robin = d.body === "robin";
        const robot = d.body === "robot" || robin || (boss && ["GOLIATH", "VOLTRIX"].includes(d.model));
        const size = boss ? 1.3 : ((d.settings || {}).size || 100) / 100;
        const main = rgb255(d.colour, [180, 100, 50]);
        const trim = rgb255(style.trim || (robin ? [140, 145, 155] : null), robot ? [31, 31, 36] : [20, 20, 20]);
        const lights = rgb255(style.lights || (robin ? [255, 90, 25] : null), robot ? [255, 90, 25] : [230, 230, 230]);
        const skin = rgb255(style.skin, [217, 161, 120]);
        const hairs = [[0.08, 0.06, 0.05], [0.3, 0.18, 0.08], [0.55, 0.35, 0.15], [0.12, 0.1, 0.1], [0.7, 0.55, 0.3]];
        const hair = d.look && d.look.hair_colour ? rgb255(d.look.hair_colour) : hairs[[...String(d.name || "")].reduce((a, c) => a + c.charCodeAt(0), 0) % 5];
        const M = {main: this.material("main", main, robot ? 0.55 : 0.75, robot ? 0.75 : 0), trim: this.material("trim", trim, 0.6, robot ? 0.6 : 0),
                   dark: this.material("fdark", [0.16, 0.16, 0.18], 0.7), skin: this.material("skin", skin, 0.8),
                   hair: this.material("hair", hair, 0.9), pants: this.material("pants", main.map(c => c * 0.55), 0.85),
                   white: this.material("fwhite", [0.92, 0.92, 0.9], 0.7), glow: this.material("fglow", lights, 0.5, 0, 2)};
        const root = new BABYLON.TransformNode("fighter" + info.id, scene);
        const body = new BABYLON.TransformNode("body", scene);
        body.parent = root;
        body.scaling.setAll(size);
        body.setPivotPoint(v3(0, 0, 0.9));
        const n = {};
        const node = (name, parent, x, y, z) => { const t = new BABYLON.TransformNode(name, scene); t.parent = parent; t.position = v3(x, y, z); n[name] = t; return t; };
        const wide = (robot ? 0.25 : 0.2) + (boss ? 0.04 : 0);
        node("hips", body, 0, 0, HIP_H);
        node("waist", n.hips, 0, 0, 0.1);
        node("neck", n.waist, 0, 0, 0.5);
        for (const [s, x] of [["l", -1], ["r", 1]]) {
            node(s + "s", n.waist, x * wide, 0, 0.44);
            node(s + "e", n[s + "s"], 0, 0, -UPPER);
            node(s + "fist", n[s + "e"], 0, 0, -FORE);
            node(s + "h", n.hips, x * 0.11, 0, 0);
            node(s + "k", n[s + "h"], 0, 0, -THIGH);
            node(s + "a", n[s + "k"], 0, 0, -SHIN);
        }
        const parts = [];
        const B = (j, hx, hy, hz, key, x, y, z) => parts.push(this.box(n[j], hx, hy, hz, M[key], x, y, z));
        const C = (j, r, h, key, x, y, z, rTop = null, axis = "z") => parts.push(this.cyl(n[j], r, h, axis, M[key], x, y, z, rTop, 10));
        const S = (j, r, key, x, y, z, sx = 1, sy = 1, sz = 1) => parts.push(this.sphere(n[j], r, M[key], x, y, z, sx, sy, sz, 10));
        const P = (j, r, len, key, x = 0, y = 0, z = 0) => {  // a capsule hanging down from (x, y, z)
            const c = BABYLON.MeshBuilder.CreateCapsule("capsule", {radius: r, height: len + 2 * r, tessellation: 10, subdivisions: 2}, scene);
            c.material = M[key];
            c.position = v3(x, y, z - len / 2);
            c.parent = n[j];
            parts.push(c);
        };
        const big = boss ? 1.15 : 1;
        if (robot) {
            B("hips", 0.2 * big, 0.13, 0.1, "dark", 0, 0, 0.02); B("hips", 0.22 * big, 0.15, 0.05, "main", 0, 0, 0.1);
            for (const s of ["l", "r"]) {
                C(s + "h", 0.07, THIGH / 2, "dark", 0, 0, -THIGH / 2); B(s + "h", 0.1 * big, 0.11, 0.15, "main", 0, 0.01, -0.18); S(s + "h", 0.085, "trim", 0, 0, 0);
                C(s + "k", 0.06, SHIN / 2, "dark", 0, 0, -SHIN / 2); B(s + "k", 0.095 * big, 0.12, 0.17, "main", 0, 0.02, -0.2);
                B(s + "k", 0.07, 0.05, 0.06, "trim", 0, 0.09, -0.02); B(s + "k", 0.02, 0.005, 0.07, "glow", 0, 0.142, -0.22);
                B(s + "a", 0.09 * big, 0.16, 0.045, "trim", 0, 0.05, -ANKLE + 0.045);
            }
            B("waist", 0.17 * big, 0.12, 0.14, "dark", 0, 0, 0.1); B("waist", 0.25 * big, 0.17, 0.2, "main", 0, 0.01, 0.36);
            B("waist", 0.2 * big, 0.04, 0.12, "trim", 0, 0.17, 0.36); C("waist", 0.055, 0.01, "glow", 0, 0.215, 0.38, null, "y");
            B("waist", 0.27 * big, 0.12, 0.035, "trim", 0, 0, 0.52);
            if (boss) for (const x of [-1, 1]) for (let k = 0; k < 3; k++) C("waist", 0.035, 0.06, "trim", x * (0.12 + k * 0.06), 0.02, 0.6, 0);
            C("neck", 0.05, 0.05, "dark", 0, 0, 0.04); B("neck", 0.12, 0.13, 0.12, "main", 0, 0, 0.18);
            B("neck", 0.125, 0.05, 0.03, "trim", 0, 0.1, 0.22); B("neck", 0.1, 0.012, 0.022, "glow", 0, 0.132, 0.2); B("neck", 0.03, 0.1, 0.05, "trim", 0, -0.02, 0.31);
            if (boss) for (const x of [-1, 1]) C("neck", 0.025, 0.08, "trim", x * 0.1, 0, 0.36, 0);
            for (const [s, x] of [["l", -1], ["r", 1]]) {
                B(s + "s", 0.1 * big, 0.12, 0.09, "main", x * 0.03, 0, 0.02); B(s + "s", 0.075, 0.075, 0.11, "trim", 0, 0, -0.16); C(s + "s", 0.05, UPPER / 2, "dark", 0, 0, -UPPER / 2);
                B(s + "e", 0.075 * big, 0.08, 0.12, "main", 0, 0, -0.13); S(s + "e", 0.06, "dark", 0, 0, 0); B(s + "e", 0.005, 0.03, 0.06, "glow", x * 0.078 * big, 0, -0.13);
                B(s + "fist", 0.07 * big, 0.075, 0.07, "trim", 0, 0.01, -0.05);
            }
        } else {
            B("hips", 0.19 * big, 0.12, 0.1, "pants", 0, 0, 0.02); B("hips", 0.2 * big, 0.13, 0.035, "trim", 0, 0, 0.1);
            for (const s of ["l", "r"]) {
                P(s + "h", 0.085 * big, THIGH, "pants");
                C(s + "k", 0.075 * big, SHIN * 0.42, "pants", 0, 0, -SHIN * 0.42, 0.07 * big); P(s + "k", 0.045, SHIN * 0.5, "skin", 0, 0, -SHIN * 0.5);
                S(s + "a", 0.06, "skin", 0, 0.05, -ANKLE + 0.035, 0.8, 1.9, 0.6);
            }
            S("waist", 0.2 * big, "main", 0, 0, 0.3, 1.0, 0.62, 1.35); S("waist", 0.17 * big, "main", 0, 0, 0.1, 1.0, 0.7, 0.8);
            S("waist", 0.07, "skin", 0, 0.08, 0.47, 1.1, 1, 0.9); C("waist", 0.175 * big, 0.03, "trim", 0, 0, 0.05);
            C("neck", 0.05, 0.05, "skin", 0, 0, 0.04);
            if (d.model === "SHADE") { S("neck", 0.115, "main", 0, 0.01, 0.17, 0.95, 1.02, 1.17); B("neck", 0.07, 0.01, 0.012, "glow", 0, 0.113, 0.185); }
            else S("neck", 0.11, "skin", 0, 0.01, 0.17, 0.92, 1.0, 1.15);
            C("neck", 0.104, 0.016, "trim", 0, 0.01, 0.262);
            if (d.model === "KRAGG") for (let k = 0; k < 6; k++) C("neck", 0.018, 0.06, "hair", 0, 0.08 - k * 0.04, 0.33 - Math.abs(k - 2.5) * 0.01, 0.004);
            else if (d.model !== "SHADE") {
                S("neck", 0.115, "hair", 0, -0.02, 0.22, 0.98, 1.0, 0.8);
                for (let k = 0; k < 5; k++) { const a = k * 1.25; C("neck", 0.03, 0.06, "hair", Math.cos(a) * 0.05, -0.03 + Math.sin(a) * 0.05, 0.33, 0); }
            }
            if (d.model !== "SHADE") { for (const x of [-0.04, 0.04]) S("neck", 0.014, "dark", x, 0.1, 0.19); }
            for (const s of ["l", "r"]) {
                S(s + "s", 0.09 * big, "main", 0, 0, 0); P(s + "s", 0.075 * big, UPPER, "main");
                P(s + "e", 0.055 * big, FORE * 0.9, "skin"); C(s + "e", 0.06 * big, 0.05, "white", 0, 0, -FORE + 0.06);
                S(s + "fist", 0.06 * big, "skin", 0, 0.01, -0.04, 0.9, 1.1, 1.0);
            }
        }
        // the weapon (the window's skinned models carry one; here a plain shape in the right fist, a shield on the left arm)
        const w = d.weapon;
        if (w) {
            const blade = this.material("blade", [0.8, 0.82, 0.86], 0.25, 0.9), wood = this.material("wood", [0.45, 0.3, 0.16], 0.8);
            if (w === "knife" || w === "dagger") B("rfist", 0.012, 0.02, 0.13, "trim", 0, 0.02, -0.16), parts[parts.length - 1].material = blade;
            if (["sword_shield", "longsword", "katana"].includes(w)) {
                const len = w === "sword_shield" ? 0.32 : 0.45;
                parts.push(this.box(n.rfist, 0.012, 0.025, len, blade, 0, 0.02, -0.07 - len));
                if (w === "sword_shield") parts.push(this.cyl(n.le, 0.22, 0.02, "x", this.material("shield", main, 0.5, 0.4), -0.08, 0, -0.14, null, 18));
            }
            if (["stick", "staff", "glaive"].includes(w)) {
                const len = w === "stick" ? 0.32 : 0.8;
                parts.push(this.cyl(n.rfist, 0.02, len, "z", wood, 0, 0.02, -0.04, null, 6));
                if (w === "glaive") parts.push(this.box(n.rfist, 0.01, 0.05, 0.14, blade, 0, 0.02, -0.04 - len - 0.12));
            }
        }
        const glows = ["l", "r"].map(s => { const g = this.sphere(n[s + "fist"], 0.13, this.material(robot ? "blastblue" : "blastorange", robot ? [0.3, 0.8, 1] : [1, 0.6, 0.15], 0.5, 0, 2)); g.isVisible = false; return g; });
        this.shadowCast(parts);
        const computer = info.owner === "Computer";
        const label = this.makeLabel(`${d.name || ""}\n${computer && boss ? "Boss" : info.owner || ""}`, computer ? "#ffbf4d" : "#ffffff", 0.9);
        const f = {root, body, n, size, design: d, label, glows, cur: stance(), pos: null, h: 0, wheel: null, owner: info.owner, ring: info.ring, robot, main: M.main};
        this.applyPose(f, f.cur);
        this.fighters.set(info.id, f);
        return f;
    }

    applyPose(f, p) {
        f.n.hips.position.y = p.hz;
        for (const j of JOINTS) {
            const [h, pt, r] = p[j];
            const node = f.n[j];
            node.rotation.set(-pt * D2R, -h * D2R, -r * D2R);
        }
    }

    // fs: [{id, pos, h, a, k, hu, ...}] for the drawn rings; dt seconds
    frame(fs, rings, dt, t) {
        const seen = new Set();
        for (const s of fs) {
            const f = this.fighters.get(s.id);
            if (!f) continue;
            seen.add(s.id);
            const hide = s.pos[2] < -1.5;
            f.root.setEnabled(!hide);
            f.label.setEnabled(!hide);
            if (hide) continue;
            const target = s.pos;
            if (!f.pos || Math.hypot(target[0] - f.pos[0], target[1] - f.pos[1], target[2] - f.pos[2]) > 2.5) f.pos = [...target];
            else f.pos = f.pos.map((v, i) => v + (target[i] - v) * Math.min(1, dt * 20));
            const dh = ((s.h - f.h + 180) % 360 + 360) % 360 - 180;
            f.h += Math.abs(dh) > 60 ? dh : dh * Math.min(1, dt * 22);
            const want = animPose(s.a || "idle", s.k || 0);
            f.cur = blend(f.cur, want, 1 - Math.exp(-dt * (MOVES.has(s.a) ? 40 : 18)));
            this.applyPose(f, f.cur);
            let heading = f.h;
            if (s.a === "spin_kick" && s.k > 1 && s.k < 2) heading += 360 * (s.k - 1);
            f.root.position = v3(f.pos[0], f.pos[1], f.pos[2] + f.cur.lift * f.size);
            f.root.rotation.y = -heading * D2R;
            if (s.a === "cartwheel") {
                const over = cartwheelTurn(s.k || 0);
                f.wheel = f.wheel === null || over < f.wheel - 1 ? over : Math.min(over, f.wheel + 900 * dt);
                f.body.rotation.z = -f.wheel * D2R;
            } else if (f.wheel !== null) { f.wheel = null; f.body.rotation.z = 0; }
            for (const g of f.glows) {
                g.isVisible = s.a === "blast" && s.k < 2;
                g.scaling.setAll(0.5 + 0.8 * Math.min(1, s.k || 0));
            }
            const flash = (s.hu ?? 9) < 0.12;
            if (flash !== f.flashing) {
                f.flashing = flash;
                f.root.getChildMeshes(false).forEach(m => { if (m.material === f.main || m.material === f.flashMat) m.material = flash ? (f.flashMat = f.flashMat || this.material("flash", [1, 0.95, 0.9], 0.5, 0, 0.8)) : f.main; });
            }
            f.label.position = v3(f.pos[0], f.pos[1], f.pos[2] + 2.05 * f.size + 0.1);
        }
        for (const [id, f] of this.fighters) if (!seen.has(id)) { f.root.setEnabled(false); f.label.setEnabled(false); }
        for (const r of rings) {
            const jets = this.jets.get(r.i);
            if (jets && r.hz && r.hz.jets) r.hz.jets.forEach((power, k) => {
                const fl = jets[k];
                if (!fl) return;
                fl.isVisible = power > 0.05;
                const hgt = 0.4 + 1.5 * power;
                fl.scaling.set(0.6 + 0.6 * power, hgt * (0.9 + 0.1 * Math.sin(t * 25 + k)), 0.6 + 0.6 * power);
                fl.position.y = 0.03 + hgt / 2;
            });
        }
        for (const b of this.blasts) b.dispose();
        this.blasts = rings.flatMap(r => (r.sh || []).map(([x, y, z]) => this.sphere(null, 0.2, this.material("blast", [0.4, 0.9, 1], 0.5, 0, 2), x, y, z)));
        for (const sp of this.sparks) {
            sp.life -= dt;
            sp.mesh.scaling.setAll(1 + (0.3 - sp.life) * 6);
            sp.mesh.visibility = Math.max(0, sp.life / 0.3);
            if (sp.life <= 0) sp.mesh.dispose();
        }
        this.sparks = this.sparks.filter(sp => sp.life > 0);
        this.updateCamera(fs, dt);
        this.followSun();
    }

    spark(pos, dmg, kind) {
        if (this.sparks.length > 30 || kind === "land") return;
        const colour = {special: [0.6, 0.85, 1], counter: [1, 0.85, 0.2], block: [0.6, 0.8, 1], zap: [0.4, 0.7, 1], fire: [1, 0.5, 0.1]}[kind] || [1, 0.92, 0.7];
        const m = this.sphere(null, Math.min(0.3, 0.07 + dmg * 0.015), this.material("fspark" + kind, colour, 0.5, 0, 2), pos[0], pos[1], pos[2], 1, 1, 1, 6);
        this.sparks.push({mesh: m, life: 0.3});
    }

    updateCamera(fs, dt) {
        const cam = this.camera, ring = this.watchRing ?? 0;
        const [cx, cy] = RING_CENTRES[ring] || [0, 0];
        const here = fs.filter(s => this.fighters.has(s.id) && this.fighters.get(s.id).ring === ring && s.pos[2] > -1.5);
        let target, radius, beta;
        if (this.mode === "fight" && here.length >= 1) {
            const xs = here.map(s => s.pos[0]), ys = here.map(s => s.pos[1]);
            const mx = xs.reduce((a, b) => a + b, 0) / xs.length, my = ys.reduce((a, b) => a + b, 0) / ys.length;
            const gap = here.length > 1 ? Math.hypot(xs[1] - xs[0], ys[1] - ys[0]) : 1;
            target = v3(mx, my, 1.0);
            radius = 4.3 + 0.8 * gap;
            beta = 1.25;
            if (here.length > 1) {  // side-on to the line between them, staying on the side the camera is on
                const ax = xs[1] - xs[0], ay = ys[1] - ys[0];
                let want = Math.atan2(ax, -ay);  // (the camera off to the side of the line: Babylon alpha is measured in the game's x-y)
                const alt = want + Math.PI;
                const d1 = Math.abs(((want - cam.alpha + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI);
                const d2 = Math.abs(((alt - cam.alpha + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI);
                if (d2 < d1) want = alt;
                cam.alpha = this.snapCamera ? want : cam.alpha + (((want - cam.alpha + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI) * Math.min(1, dt * 3);
            }
        } else if (this.mode === "ring" || this.mode === "fight") {
            target = v3(cx, cy, 0.5); radius = 12; beta = 0.9;
        } else {
            const used = this.setup.rings || [0];
            const xs = used.map(i => (RING_CENTRES[i] || [0, 0])[0]), ys = used.map(i => (RING_CENTRES[i] || [0, 0])[1]);
            const span = Math.max(...xs) - Math.min(...xs) + Math.max(...ys) - Math.min(...ys) + 10;
            target = v3((Math.max(...xs) + Math.min(...xs)) / 2, (Math.max(...ys) + Math.min(...ys)) / 2, 0);
            radius = span * 1.05; beta = 0.85;
        }
        if (this.snapCamera) { cam.target = target; cam.radius = radius; cam.beta = beta; this.snapCamera = false; return; }
        cam.target = BABYLON.Vector3.Lerp(cam.target, target, Math.min(1, dt * 5));
        if (!this.userZoom) { cam.radius = lerp(cam.radius, radius, Math.min(1, dt * 3)); cam.beta = lerp(cam.beta, beta, Math.min(1, dt * 3)); }
    }

    setMode(mode) {
        this.mode = mode;
        this.snapCamera = true;
    }
}

export class FightGame {
    static detect(m) { return !!(m.rules && m.rules.styles && m.rules.bosses); }

    constructor(app) {
        this.app = app;
        this.id = "fightlab";
        this.title = "Fight Lab";
        this.word = "fighter";
        this.scene = new FightScene(app.canvas, app.tier, app.engine);
        this.watch = null;
        this.mods = ["mods/stage.py", "mods/rules.py", "mods/fighters/<username>.py"];
        this.last = null;
        this.events = new Set();
        this.pickA = this.pickB = "";
    }

    welcome(m) {
        const p = this.app.params;
        if (p.get("cam")) this.scene.setMode({tv: "fight", chase: "fight", overview: "all"}[p.get("cam")] || p.get("cam"));
    }

    message(m) {
        if (m.type === "roster") {
            this.roster = m;
            this.scene.setSetup({rings: m.rings || [0], rs: m.rs || 4.5, hazards: m.hazards || {}, look: m.look || {}});
            this.scene.setFighters(m.fighters || []);
            this.scene.watchRing = this.watched();
            this.renderBoard();
            return true;
        }
        if (m.type === "state") {
            m.sm = m.sm >>> 0;
            this.app.pushSnap(m, performance.now());
            this.last = m;
            for (const [p, dmg, kind] of m.fx || []) this.scene.spark(p, dmg, kind);
            for (const e of m.events || []) if (!this.events.has(e)) { this.events.add(e); this.app.addEvent(e); }
            if (this.events.size > 200) this.events = new Set([...this.events].slice(-60));
            this.renderBoard();
            return true;
        }
        return false;
    }

    binary() {}

    watched() {
        if (this.watch !== null) return this.watch;
        const S = this.app.state, r = this.roster;
        const mine = r && r.mine ? r.mine[S.name] : null;
        const f = mine !== null && mine !== undefined && r ? (r.fighters || []).find(x => x.id === mine) : null;
        return f ? f.ring : ((r && r.rings) || [0])[0] ?? 0;
    }

    frame(now, dt) {
        const pair = this.app.samplePair(now);
        if (!pair) { this.scene.frame([], [], dt, now / 1000); return; }
        const {a, b, f} = pair;
        const bRings = b ? new Map((b.rings || []).map(r => [r.i, r])) : new Map();
        const fighters = [];
        for (const ra of a.rings || []) {
            const rb = bRings.get(ra.i);
            const byId = rb ? new Map((rb.f || []).map(x => [x.id, x])) : new Map();
            for (const x of ra.f || []) {
                const y = byId.get(x.id);
                if (!y) { fighters.push(x); continue; }
                fighters.push({...y, pos: x.pos.map((v, i) => lerp(v, y.pos[i], f)), h: lerpDeg(x.h, y.h, f),
                               k: x.a === y.a ? lerp(x.k, y.k, f) : y.k});
            }
        }
        this.scene.watchRing = this.watched();
        this.scene.frame(fighters, (b || a).rings || [], dt, now / 1000);
    }

    renderBoard() {
        const m = this.last, esc = this.app.esc;
        if (!m || !this.roster) return;
        const names = new Map((this.roster.fighters || []).map(x => [x.id, x]));
        const w = this.watched();
        const lines = (m.rings || []).map(r => {
            const fs = (r.f || []).map(x => {
                const info = names.get(x.id) || {design: {}};
                const pc = Math.max(0, Math.round(100 * x.hp / (x.max || 1)));
                return `${esc(info.design.name || "?")} ${pc}%${x.w ? ` (${x.w})` : ""}${x.ap ? " AUTO" : ""}`;
            }).join("  v  ");
            const tail = r.bn ? r.bn : r.tl === null || r.tl === undefined ? "training" : `round ${r.rd}  ${Math.ceil(r.tl)} s`;
            return `<div data-ring="${r.i}" class="${r.i === w ? "watched" : ""}"><span>Ring ${r.i + 1}${r.lb ? ` · ${esc(r.lb)}` : ""}: ${fs || "empty"}</span><span class="lap">${esc(tail)}</span></div>`;
        });
        $("places").innerHTML = lines.join("") || "<div><small>No rings</small></div>";
        $("places").querySelectorAll("div[data-ring]").forEach(el => el.onclick = () => { this.watch = Number(el.dataset.ring); this.renderBoard(); });
        const ring = (m.rings || []).find(r => r.i === w);
        $("countdown").textContent = ring ? ring.bn || "" : "";
        const T = this.app.state.tournament;
        $("phase").textContent = (m.paused ? "PAUSED · " : "") + (m.practice ? "PRACTICE (no damage)" : "BATTLE") +
                                 (ring && ring.tl !== null && ring.tl !== undefined ? ` · ${Math.ceil(ring.tl)} s` : "") +
                                 (T ? ` · ${T.champion ? `CHAMPION ${T.champion}` : T.title || "tournament"}` : "");
    }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${L.mode === "battle" ? "battle" : "practice"} · ${L.rings ? `${L.rings} rings` : "rings: auto"}` : "";
    }

    cameraPill() {
        return {fight: "Camera: the fight, side on", ring: "Camera: the whole ring", all: "Camera: every ring"}[this.scene.mode] || "";
    }

    tabs() { return [["controls", "Controls"], ["matches", "Matches"], ["camera", "Camera"]]; }

    learnerHead() { return ["Fighter", "Ring"]; }
    learnerCells(p) {
        const r = this.roster || {};
        const id = r.mine ? r.mine[p.name] : null;
        const f = (r.fighters || []).find(x => x.id === id);
        return [this.app.esc((p.design && p.design.name) || ""), f ? f.ring + 1 : ""];
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, R = S.rules || {}, send = app.send, esc = app.esc;
        const lessonSend = patch => send({type: "lesson", lesson: patch});
        if (!L && tab !== "camera") { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return ["controls", "matches"].includes(tab); }
        const people = (S.classList || []).filter(p => p.role === "learner").map(p => p.name).concat(L && L.teacher_fighter ? ["Teacher"] : []);
        if (tab === "controls") {
            const levels = Object.entries(R.cpu_levels || {});
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The fights</h2>
              <div class="row"><button data-mode="practice" class="${L.mode !== "battle" ? "on" : ""}">Practice</button>
                <button data-mode="battle" class="${L.mode === "battle" ? "on" : ""}">Battle</button>
                <button id="fb-restart" class="go">RESTART</button>
                <button id="fb-pause" class="${this.last && this.last.paused ? "on" : ""}">${this.last && this.last.paused ? "RESUME" : "PAUSE"}</button></div>
              <div class="note">Practice: no damage and no timer. Battle: rounds of ${L.round_time} s, first to ${L.rounds_to_win}. RESTART begins new matches.</div>
              <div class="row"><label>Round time</label><select id="fb-time">${[20, 30, 40, 50, 60, 90, 120, 180, 240, 300].map(t => `<option value="${t}" ${t === L.round_time ? "selected" : ""}>${t} s</option>`).join("")}</select></div>
              <div class="row"><label>Rounds to win</label>${[1, 2, 3].map(k => `<button data-rtw="${k}" class="${k === L.rounds_to_win ? "on" : ""}">${k}</button>`).join("")}</div>
              <div class="row"><label>Sparring partners</label><button id="fb-cpu" class="${L.cpu_opponents ? "on" : ""}">${L.cpu_opponents ? "Computer fighters on" : "Off"}</button>
                <select id="fb-level">${levels.map(([k, n]) => `<option value="${k}" ${k === L.cpu_level ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
              <div class="row"><label>The computer plays</label><button data-cf="sparring" class="${L.cpu_fighter === "sparring" ? "on" : ""}">Sparring</button>
                ${Object.keys(R.bosses || {}).map(b => `<button data-cf="${esc(b)}" class="${L.cpu_fighter === b ? "on" : ""}">${esc(b)}</button>`).join("")}</div>
              ${L.cpu_level === "empty" ? `<div class="row"><label class="filebtn">Upload the demo brain (.py)<input id="fb-demo" type="file" accept=".py,text/plain" hidden></label></div>` : ""}
              <div class="row"><label>My fighter</label><button id="fb-mine" class="${L.teacher_fighter ? "on" : ""}">${L.teacher_fighter ? "In the class" : "Not in"}</button></div>
              <div class="row"><label>Designs</label><button id="fb-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              <h2>Rings</h2>
              <div class="row"><button data-rings="0" class="${!L.rings ? "on" : ""}">Auto</button>${[1, 2, 3, 4, 5, 6].map(k => `<button data-rings="${k}" class="${L.rings === k ? "on" : ""}">${k}</button>`).join("")}
                <button id="fb-turns">Take turns again</button></div>
              ${L.rings ? people.map((n, i) => `<div class="row"><label>${esc(n)}</label><select data-place="${i}"><option value="">any</option>${Array.from({length: L.rings}, (_, k) =>
                  `<option value="${k}" ${(L.places || {})[n] === k ? "selected" : ""}>ring ${k + 1}</option>`).join("")}</select></div>`).join("") : `<div class="note">Auto: one ring each, matches share.</div>`}
              ${app.restartRow()}`;
            app.wireMissionRow(body);
            body.querySelectorAll("button[data-mode]").forEach(b => b.onclick = () => lessonSend({mode: b.dataset.mode}));
            $("fb-restart").onclick = () => send({type: "restart"});
            $("fb-pause").onclick = () => send({type: "pause"});
            $("fb-time").onchange = e => lessonSend({round_time: Number(e.target.value)});
            body.querySelectorAll("button[data-rtw]").forEach(b => b.onclick = () => lessonSend({rounds_to_win: Number(b.dataset.rtw)}));
            $("fb-cpu").onclick = () => lessonSend({cpu_opponents: !L.cpu_opponents});
            $("fb-level").onchange = e => lessonSend({cpu_level: e.target.value});
            body.querySelectorAll("button[data-cf]").forEach(b => b.onclick = () => lessonSend({cpu_fighter: b.dataset.cf}));
            if ($("fb-demo")) $("fb-demo").onchange = async e => { const f = e.target.files[0]; if (f) send({type: "cpu_brain", source: await f.text()}); };
            $("fb-mine").onclick = () => lessonSend({teacher_fighter: !L.teacher_fighter});
            $("fb-lock").onclick = () => lessonSend({designs_locked: !L.designs_locked});
            body.querySelectorAll("button[data-rings]").forEach(b => b.onclick = () => lessonSend({rings: Number(b.dataset.rings)}));
            $("fb-turns").onclick = () => lessonSend({places: Object.fromEntries(people.map(n => [n, null]))});
            body.querySelectorAll("select[data-place]").forEach(sel => sel.onchange = () =>
                lessonSend({places: {[people[Number(sel.dataset.place)]]: sel.value === "" ? null : Number(sel.value)}}));
            app.wireRestartRow(body);
            return true;
        }
        if (tab === "matches") {
            const T = S.tournament;
            const matches = L.matches || [];
            const opts = sel => `<option value="">pick</option>` + people.map(n => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("");
            body.innerHTML = `
              <h2>Matches</h2>
              <div class="row"><select id="fm-a">${opts(this.pickA)}</select> v <select id="fm-b">${opts(this.pickB)}</select><button id="fm-add" class="go">Add match</button></div>
              <table>${matches.map(([a, b], i) => `<tr><td>${esc(a)} v ${esc(b)}</td><td><button data-mrm="${i}">Remove</button></td></tr>`).join("") || "<tr><td class='note'>No matches set: everyone spars.</td></tr>"}</table>
              <div class="row"><button id="fm-clear">Clear all</button></div>
              <h2>Tournament</h2>
              ${T ? `<p><b>${esc(T.title || "")}</b>${T.champion ? ` · champion ${esc(T.champion)}` : ""}</p>
                  ${(T.table || []).length ? `<table><tr><th>Fighter</th><th>wins</th><th>streak</th></tr>${T.table.map(([n, w, s]) => `<tr><td>${esc(n)}</td><td class="num">${w}</td><td class="num">${s}</td></tr>`).join("")}</table>` : ""}
                  ${(T.rounds || []).map((rd, i) => `<div class="note">Round ${i + 1}: ${rd.map(([a, b, w]) => `${esc(a)} v ${esc(b)}${w ? ` (${esc(w)})` : ""}`).join(", ")}</div>`).join("")}
                  <div class="row"><button id="fm-stop" class="stop">STOP THE TOURNAMENT</button></div>`
                : `<div class="row"><button id="fm-knock" class="go">Knockout</button><button id="fm-stays" class="go">Winner stays on</button></div>
                   <div class="note">A knockout of everyone with a fighter (computer fighters fill the gaps). Winner stays on uses ${L.rings || 2} rings.</div>`}`;
            $("fm-a").onchange = e => { this.pickA = e.target.value; };
            $("fm-b").onchange = e => { this.pickB = e.target.value; };
            $("fm-add").onclick = () => {
                const a = $("fm-a").value, b = $("fm-b").value;
                if (!a || !b || a === b) return app.toast("Pick two different fighters.");
                const rest = matches.filter(([x, y]) => ![x, y].includes(a) && ![x, y].includes(b));
                lessonSend({matches: [...rest, [a, b]].slice(0, 6)});
            };
            body.querySelectorAll("button[data-mrm]").forEach(b => b.onclick = () => lessonSend({matches: matches.filter((_, i) => i !== Number(b.dataset.mrm))}));
            $("fm-clear").onclick = () => lessonSend({matches: []});
            if ($("fm-knock")) $("fm-knock").onclick = () => send({type: "tournament", start: true});
            if ($("fm-stays")) $("fm-stays").onclick = () => send({type: "tournament", start: true, kind: "stays", live: L.rings || 2});
            if ($("fm-stop")) $("fm-stop").onclick = () => send({type: "tournament", start: false});
            return true;
        }
        if (tab === "camera") {
            const sc = this.scene, rings = (this.roster && this.roster.rings) || [0];
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row">${[["fight", "The fight"], ["ring", "The ring"], ["all", "Every ring"]].map(([k, n]) => `<button data-view="${k}" class="${sc.mode === k ? "on" : ""}">${n}</button>`).join("")}</div>
              <div class="note">The fight follows the watched ring's two fighters, side on. Drag to orbit, wheel to zoom.</div>
              <h2>Watch a ring</h2>
              <div class="row">${rings.map(k => `<button data-ring="${k}" class="${this.watched() === k ? "on" : ""}">Ring ${k + 1}</button>`).join("")}</div>`;
            body.querySelectorAll("button[data-view]").forEach(b => b.onclick = () => { sc.setMode(b.dataset.view); app.updatePills(); app.renderPanel(); });
            body.querySelectorAll("button[data-ring]").forEach(b => b.onclick = () => { this.watch = Number(b.dataset.ring); sc.snapCamera = true; this.renderBoard(); app.renderPanel(); });
            return true;
        }
        return false;
    }

    dispose() {
        this.scene.dispose();
        $("places").innerHTML = "";
        $("countdown").textContent = $("phase").textContent = "";
    }
}
