// Fight Lab's fighters as the page builds and poses them (moved out of fight.js in CHANGE 201, unchanged, so City
// Lab's people are Fight Lab's fighters, as the City Lab window borrows fight_model and fight_gfx): the poses
// (fight_gfx.py's stance, walks, attacks, blocks, falls, ported line for line), the line tiers' rim lines
// (line_look.silhouette), and FighterParts, a set of a scene's methods put on FightScene (fight.js) and CityScene
// (city.js) alike: addFighter builds a fighter from its design on the game's 13-joint skeleton (the primitive human
// or robot in its colours, with its weapon, its number plate; the woman, the man and Robin as the app's own skinned
// models, fightmodels.js, on the lit tiers and the line tiers; ultra's smooth fighter), poseFighter draws one at its
// state each frame. A scene with them has this.fighters (id -> what addFighter made), this.ultraFighters (ultra's
// models are here and in use) and lineFade().
// Panda joint angles (h, p, r) are Babylon rotation (-p, -h, -r); positions game (x, y, z) -> Babylon (x, z, y).

/* global BABYLON */

import {v3, rgb255} from "./base3d.js";
import {FighterModel, withBox} from "./fightmodels.js";
import {fighterLayout, fighterJointMesh, fighterAtlas, FIGHTER_GLOW, loadPandaFont, wordsSize, drawWords} from "./fightfx.js";

const D2R = Math.PI / 180;
export const MOVES = new Set(["punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam", "cartwheel"]);
export const FLASH = [3.0, 2.6, 2.4];  // (the hit flash's colour scale: the window's body's)

// ---------- the poses (fight_gfx.py, verbatim in meaning) ----------
const THIGH = 0.42, SHIN = 0.42, ANKLE = 0.08, HIP_H = THIGH + SHIN + ANKLE, UPPER = 0.29, FORE = 0.26;
export const JOINTS = ["hips", "waist", "neck", "ls", "le", "rs", "re", "lh", "lk", "la", "rh", "rk", "ra"];
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

export function blend(a, b, f) {
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

export function stance(bob = 0) {
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

export function cartwheelTurn(k) {
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

export function animPose(a, k) {
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

// ---------- (CHANGE 150) the rim lines: line_look.silhouette's thick back-face wireframe, on the page ----------
// Each edge of a shape twice (its ends), with the normals of its two faces (rimA, rimB: the same where it has one) and
// its other end (rimOther); shown where either face looks away from the camera at its middle (each end tests it with
// its own bones: where the two disagree, a short edge is half shown), a hidden edge's ends both put at its middle (so
// it draws nothing: the most of them, the shape's side towards the camera), drawn as two thin instances moved apart
// across the line in the picture (rimOffset times screen.z pixels, at right angles to the line between its ends'
// places in the picture, turned the same way at both ends), so a 1-pixel line is the window's 2 pixels thick. Bones too (a skinned model's rim bends
// with it); the fade into the dark as the other lines'
const RIM_VERT = `
precision highp float;
attribute vec3 position;
attribute vec3 rimA;
attribute vec3 rimB;
attribute vec3 rimOther;
attribute vec2 rimOffset;
#include<instancesDeclaration>
#include<bonesDeclaration>
uniform mat4 viewProjection;
uniform vec3 cameraPosition;
uniform vec3 screen;
varying float vDist;
varying float vShow;
void main(void) {
#include<instancesVertex>
#include<bonesVertex>
    vec4 wp = finalWorld * vec4(position, 1.0);
    vec3 mid = 0.5 * (wp.xyz + (finalWorld * vec4(rimOther, 1.0)).xyz), v = mid - cameraPosition;
    vec3 a = (finalWorld * vec4(rimA, 0.0)).xyz, b = (finalWorld * vec4(rimB, 0.0)).xyz;
    vShow = dot(a, v) > 0.0 || dot(b, v) > 0.0 ? 1.0 : 0.0;
    if (vShow < 0.5) wp.xyz = mid;
    vDist = length(wp.xyz - cameraPosition);
    gl_Position = viewProjection * wp;
    vec4 other = viewProjection * finalWorld * vec4(rimOther, 1.0);
    vec2 d = (other.xy / other.w - gl_Position.xy / gl_Position.w) * screen.xy;
    if (d.x < 0.0 || (d.x == 0.0 && d.y < 0.0)) d = -d;
    float l = length(d);
    vec2 across = l > 1e-5 ? vec2(-d.y, d.x) / l : vec2(0.0, 1.0);
    gl_Position.xy += across * rimOffset.x * screen.z * 2.0 / screen.xy * gl_Position.w;
}`;
const RIM_FRAG = `
precision highp float;
uniform vec4 color;
uniform vec2 fade;
varying float vDist;
varying float vShow;
void main(void) {
    if (vShow < 0.5) discard;
    gl_FragColor = vec4(color.rgb * (1.0 - smoothstep(fade.x, fade.y, vDist)), 1.0);
}`;
const RIM_MATRICES = new Float32Array(32);
for (let i = 0; i < 2; i++) RIM_MATRICES[i * 16] = RIM_MATRICES[i * 16 + 5] = RIM_MATRICES[i * 16 + 10] = RIM_MATRICES[i * 16 + 15] = 1;
const RIM_OFFSETS = new Float32Array([1, 0, -1, 0]);  // (times screen.z pixels, across the line)

// a shape's edges for rimLines, in its own frame (the rest pose): the corners within a millimetre merged (line_look's
// rule), each face's normal from its corners (turned to agree with the shape's own normals there), each edge once with
// its first two faces' normals, drawn with one of its own vertices at each end (so with that vertex's bones). Null if
// it has no faces
function rimEdges(mesh) {
    const p = mesh.getVerticesData(BABYLON.VertexBuffer.PositionKind), ix = mesh.getIndices();
    if (!p || !ix || ix.length < 3) return null;
    const nor = mesh.getVerticesData(BABYLON.VertexBuffer.NormalKind);
    const weld = new Map(), ids = new Int32Array(p.length / 3), first = [];
    for (let i = 0, j = 0; i < p.length; i += 3, j++) {
        const k = `${Math.round(p[i] * 1000)},${Math.round(p[i + 1] * 1000)},${Math.round(p[i + 2] * 1000)}`;
        let id = weld.get(k);
        if (id === undefined) { id = first.length; weld.set(k, id); first.push(j); }
        ids[j] = id;
    }
    const edges = new Map(), list = [];
    for (let t = 0; t < ix.length; t += 3) {
        const r0 = ix[t], r1 = ix[t + 1], r2 = ix[t + 2], a = ids[r0], b = ids[r1], c = ids[r2];
        if (a === b || b === c || a === c) continue;
        const ux = p[r1 * 3] - p[r0 * 3], uy = p[r1 * 3 + 1] - p[r0 * 3 + 1], uz = p[r1 * 3 + 2] - p[r0 * 3 + 2];
        const vx = p[r2 * 3] - p[r0 * 3], vy = p[r2 * 3 + 1] - p[r0 * 3 + 1], vz = p[r2 * 3 + 2] - p[r0 * 3 + 2];
        let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
        const l = Math.hypot(nx, ny, nz) || 1;
        nx /= l; ny /= l; nz /= l;
        if (nor) {  // (the winding's normal turned to the side the shape's normals say is out)
            const sx = nor[r0 * 3] + nor[r1 * 3] + nor[r2 * 3], sy = nor[r0 * 3 + 1] + nor[r1 * 3 + 1] + nor[r2 * 3 + 1];
            const sz = nor[r0 * 3 + 2] + nor[r1 * 3 + 2] + nor[r2 * 3 + 2];
            if (sx * nx + sy * ny + sz * nz < 0) { nx = -nx; ny = -ny; nz = -nz; }
        }
        for (const [e0, e1] of [[a, b], [b, c], [c, a]]) {
            const ek = e0 < e1 ? e0 * 4194304 + e1 : e1 * 4194304 + e0;
            const e = edges.get(ek);
            if (!e) { const n = {r0: first[e0], r1: first[e1], a: [nx, ny, nz], b: null}; edges.set(ek, n); list.push(n); }
            else if (!e.b) e.b = [nx, ny, nz];
        }
    }
    const n = list.length, pos = new Float32Array(n * 6), A = new Float32Array(n * 6), B = new Float32Array(n * 6), O = new Float32Array(n * 6);
    const idx = n * 2 >= 65536 ? new Uint32Array(n * 2) : new Uint16Array(n * 2);
    const kinds = [BABYLON.VertexBuffer.MatricesIndicesKind, BABYLON.VertexBuffer.MatricesWeightsKind,
                   BABYLON.VertexBuffer.MatricesIndicesExtraKind, BABYLON.VertexBuffer.MatricesWeightsExtraKind];
    const src = mesh.skeleton ? kinds.map(k => [k, mesh.getVerticesData(k)]).filter(([, d]) => d) : [];
    const bones = src.map(([k]) => [k, new Float32Array(n * 8)]);
    list.forEach((e, i) => {
        const b = e.b || e.a;
        [e.r0, e.r1].forEach((r, k) => {
            const o = (i * 2 + k) * 3;
            pos[o] = p[r * 3]; pos[o + 1] = p[r * 3 + 1]; pos[o + 2] = p[r * 3 + 2];
            A[o] = e.a[0]; A[o + 1] = e.a[1]; A[o + 2] = e.a[2];
            B[o] = b[0]; B[o + 1] = b[1]; B[o + 2] = b[2];
            src.forEach(([, d], s) => bones[s][1].set(d.subarray(r * 4, r * 4 + 4), (i * 2 + k) * 4));
            idx[i * 2 + k] = i * 2 + k;
        });
    });
    for (let i = 0; i < n * 6; i += 6) for (let k = 0; k < 3; k++) { O[i + k] = pos[i + 3 + k]; O[i + 3 + k] = pos[i + k]; }  // (each end's other end)
    return {pos, a: A, b: B, o: O, idx, bones: bones.length ? bones : null};
}


// ---------- the fighters (fight_gfx.FighterVisual, fight_model.ModelFighterVisual) ----------
export const FighterParts = {
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
        // fight_gfx.FighterVisual's looks: a robot's parts in the paint texture set (rough 0.55, metal 0.75), a
        // person's plain (rough 0.75), the lights glowing at five times their colour
        const F = (name, rgb) => robot ? this.material(name, rgb, 0.55, 0.75, 0, {tex: this.tier === "blocks" ? "" : "paint"}) : this.material(name, rgb, 0.75, 0);
        const M = {main: F("main", main), trim: F("trim", trim), dark: F("fdark", [0.16, 0.16, 0.18]), skin: F("skin", skin),
                   hair: F("hair", hair), pants: F("pants", main.map(c => c * 0.55)), white: F("fwhite", [0.92, 0.92, 0.9]),
                   glow: this.material("fglow", [0, 0, 0], 1, 0, 0, {emission: lights.map(v => v * 5)})};
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
        const G = (m, key) => { if (key === "glow") m.ccGlow = true; parts.push(m); };  // (the line tiers: a glowing part's lines apart)
        const B = (j, hx, hy, hz, key, x, y, z) => G(this.box(n[j], hx, hy, hz, M[key], x, y, z), key);
        const C = (j, r, h, key, x, y, z, rTop = null, axis = "z") => G(this.cyl(n[j], r, h, axis, M[key], x, y, z, rTop, 10), key);
        const S = (j, r, key, x, y, z, sx = 1, sy = 1, sz = 1) => G(this.sphere(n[j], r, M[key], x, y, z, sx, sy, sz, 10), key);
        const P = (j, r, len, key, x = 0, y = 0, z = 0) => {  // a capsule hanging down from (x, y, z)
            const c = BABYLON.MeshBuilder.CreateCapsule("capsule", {radius: r, height: len + 2 * r, tessellation: 10, subdivisions: 2}, scene);
            c.material = M[key];
            c.position = v3(x, y, z - len / 2);
            c.parent = n[j];
            parts.push(c);
        };
        const big = boss ? 1.15 : 1;
        let ultra = null;  // (ultra, CHANGE 147: the fighter's material and its hit flash's)
        if (this.ultraFighters) {
            ultra = this.ultraFighter(n, d, robot, boss, parts, {main, trim, skin, hair, lights});
        } else if (robot) {
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
        const plate = this.numberPlate(n.waist, d, robot, this.wire ? [1, 1, 1] : robot ? lights : trim);
        if (plate && this.wire) this.lettering(plate);  // (the line colour on the line tiers: CHANGE 147)
        // the weapon (the window's skinned models carry one; here a plain shape in the right fist, a shield on the left arm)
        const w = d.weapon;
        if (w) {
            const blade = this.material("blade", [0.8, 0.82, 0.86], 0.25, 0.9, 0, {tex: "steel"}), wood = this.material("wood", [0.45, 0.3, 0.16], 0.8);
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
        // the energy in the hands while a blast charges (the line tiers: a ball of lines, no black faces: CHANGE 147)
        const glows = ["l", "r"].map(s => {
            const g = this.wire ? this.linesMesh("handglow", this.lineSphere(0.13), this.lineMaterial("handglow", 1, ...this.lineFade()), n[s + "fist"])
                : this.sphere(n[s + "fist"], 0.13, this.material(robot ? "blastblue" : "blastorange", robot ? [0.3, 0.8, 1] : [1, 0.6, 0.15], 0.5, 0, 2));
            g.isVisible = false;
            return g;
        });
        this.shadowCast(parts);
        const lines = this.wire ? this.fighterLines(n, parts) : null;
        const computer = info.owner === "Computer";
        const label = this.makeLabel(`${d.name || ""}\n${computer && boss ? "Boss" : info.owner || ""}`, computer ? "#ffbf4d" : "#ffffff", 0.9);
        const f = {root, body, n, size, design: d, label, glows, plate, cur: stance(), pos: null, h: 0, wheel: null, owner: info.owner, ring: info.ring, robot,
                   main: ultra ? ultra.base : M.main, flashMat: ultra ? ultra.flash : undefined, lines, ultra: !!ultra};
        this.applyPose(f, f.cur);
        if (FighterModel.wanted(this, d)) f.model = new FighterModel(this, f, d, info.id);  // (the app's own model, once loaded)
        this.fighters.set(info.id, f);
        return f;
    },

    // (CHANGE 143) fight_gfx.FighterVisual.number_plate: the fighter's number (or its name), 8 letters at most, on the
    // waist joint where the window puts it, (0, -0.18) on a robot and (0, -0.14) on a person, 0.34 up: the back of the
    // torso, read from behind (a robot's in its light colour, glowing as Robin's does; a person's in the trim colour)
    numberPlate(joint, d, robot, rgb) {
        const text = String((d.style || {}).number || d.name || "").slice(0, 8);
        if (!text) return null;
        // (CHANGE 150: the window's TextNode, 0.07 a unit, its baseline there, read from behind)
        const css = `rgb(${rgb.map(c => Math.round(255 * Math.max(0, Math.min(1, c)))).join(",")})`;
        const plane = this.fightWords(text, 0.07, css, robot ? 1 : 0.6, [0, robot ? -0.18 : -0.14, 0.34], [0, 0, 0], joint);
        if (!this.lighting) plane.material.emissiveColor = new BABYLON.Color3(0.4, 0.4, 0.4);
        return plane;
    },

    // (CHANGE 150) words as the window's TextNode writes them (centred, in Panda's own letters: fightfx.js's drawWords):
    // a flat card in its own x and y (as a TextNode's x and z: read from in front, its -y), its middle on the baseline,
    // scale metres a unit, at pos turned by hpr (the window's, degrees) under parent; colour a CSS colour, paint how
    // bright it is unlit on the lit tiers (as floorText). Until the letters are loaded, the browser's sans, and the scene
    // made again once they are
    fightWords(text, scale, colour, paint, pos, hpr, parent = null) {
        const size = wordsSize(text) || {width: 0.6 * String(text).length, lo: -0.2, hi: 0.75};
        const ppu = 96, pad = 0.1, w = size.width + 2 * pad, lo = size.lo - pad, hi = size.hi + pad;
        const cw = Math.max(8, Math.ceil(w * ppu)), ch = Math.max(8, Math.ceil((hi - lo) * ppu));
        const plane = BABYLON.MeshBuilder.CreatePlane("words", {width: w * scale, height: (hi - lo) * scale}, this.scene);
        plane.bakeTransformIntoVertices(BABYLON.Matrix.Translation(0, (hi + lo) / 2 * scale, 0));  // (its middle on the baseline)
        const tex = new BABYLON.DynamicTexture("wordstex", {width: cw, height: ch}, this.scene, true);
        tex.hasAlpha = true;
        const ctx = tex.getContext();
        ctx.clearRect(0, 0, cw, ch);
        if (!drawWords(ctx, text, cw / 2, hi * ppu, ppu, colour)) {
            ctx.fillStyle = colour;
            ctx.textAlign = "center";
            ctx.font = `${Math.round(0.7 * ppu)}px sans-serif`;
            ctx.fillText(String(text), cw / 2, hi * ppu);
            if (!this.fontWait) this.fontWait = loadPandaFont().then(f => { if (f && this.scene) this.build(); });
        }
        tex.update();
        const m = new BABYLON.StandardMaterial("wordsmat", this.scene);
        m.diffuseTexture = tex;
        m.useAlphaFromDiffuseTexture = true;
        m.emissiveColor = new BABYLON.Color3(0.4, 0.4, 0.4);
        if (this.lighting) {
            m.disableLighting = true;
            m.emissiveColor = new BABYLON.Color3(paint, paint, paint);
        }
        m.backFaceCulling = true;  // (a TextNode is one-sided)
        plane.material = m;
        plane.isPickable = false;
        if (parent) plane.parent = parent;
        plane.position = v3(...pos);
        plane.rotation.set(-hpr[1] * D2R, -hpr[0] * D2R, -hpr[2] * D2R);
        return plane;
    },

    // (ultra, CHANGE 147: fight_gfx.FighterVisual.ultra) the window's smooth fighter from models/fight_ultra.json: its
    // pieces placed by fighterLayout (fight_models.layout) on the joints the other tiers pose (the fists in the
    // forearms' pieces), each joint's pieces ONE mesh in the fighter's colours (a texel a role for roughness, metal and
    // glow, as the window's atlas: 13 meshes a fighter, its shadow's too). Returns its material and its hit flash's
    ultraFighter(n, d, robot, boss, parts, c) {
        const colours = {main: c.main, trim: c.trim, skin: c.skin, hair: c.hair, pants: c.main.map(v => v * 0.55),
                         shade: c.main.map(v => v * 0.78), lips: [c.skin[0] * 0.85, c.skin[1] * 0.62, c.skin[2] * 0.6]};
        const glow = c.lights.map(v => v * 5);  // (the lower tiers' glow)
        const byJoint = {};
        for (const [j, piece, pos, hpr, scale] of fighterLayout(robot ? "robot" : "human", boss ? d.model : null)) {
            (byJoint[j] = byJoint[j] || []).push([piece, pos, hpr, scale]);
        }
        const base = this.ultraFighterMaterial(glow, [1, 1, 1]);
        for (const [j, items] of Object.entries(byJoint)) {
            const mesh = n[j] ? fighterJointMesh(this, "fighter " + j, items, colours) : null;
            if (!mesh) continue;
            mesh.parent = n[j];
            mesh.material = base;
            parts.push(mesh);
        }
        return {base, flash: this.ultraFighterMaterial(glow, FLASH)};
    },

    // (ultra) a fighter's material: white times its colour scale q (linear: the window's colour scales), the vertices'
    // colours, the roles' roughness, metal and glow from the atlas (fightfx.js's fighterAtlas, its lights colour's), the
    // backs of its faces culled as the window's
    ultraFighterMaterial(lights, q) {
        const key = `fultra:${lights.map(v => v.toFixed(3)).join(",")}:${q.join(",")}`;
        if (this.materials[key]) return this.materials[key];
        const atlas = fighterAtlas(this, lights);
        const m = this.lighting.material(key, {rgb: q.map(v => Math.pow(v, 1 / 2.2)), rough: 1, metal: 1,
                                               emission: [FIGHTER_GLOW, FIGHTER_GLOW, FIGHTER_GLOW], mrMap: atlas.mr, glowMap: atlas.glow});
        m.backFaceCulling = true;
        m.sideOrientation = BABYLON.Material.ClockWiseSideOrientation;  // (the front as the file's, turned round by unpackPart)
        this.materials[key] = m;
        return m;
    },

    // (the line tiers, CHANGE 147: fight_gfx.FighterVisual.finish) a built fighter's lines: each joint's parts (a fist's
    // with its forearm's, as the window joins them; a weapon with its hand's) one black mesh with its edges as lines
    // under the joint, so they move with it; a glowing part's lines apart; on lines each joint's outline too (the round
    // limbs and head have few folds: rimLines). Returns [[mesh, its material, its hit flash's]]
    fighterLines(n, parts) {
        const fade = this.lineFade(), mode = this.wire, out = [];
        const mat = this.lineMaterial("fighter", 1, ...fade), flash = this.tintedLines("fighterflash", FLASH, ...fade);
        const rim = mode === "outline" ? this.rimMaterial("fighter", fade) : null;
        const rimFlash = rim ? this.rimMaterial("fighterflash", fade, FLASH) : null;
        const groups = new Map();
        for (const m of parts) {
            if (!m.parent || m.isDisposed()) continue;
            const joint = m.parent === n.lfist ? n.le : m.parent === n.rfist ? n.re : m.parent, key = joint.uniqueId + (m.ccGlow ? "g" : "");
            if (!groups.has(key)) groups.set(key, [joint, !!m.ccGlow, []]);
            groups.get(key)[2].push(m);
        }
        for (const [joint, glow, list] of groups.values()) {
            const merged = this.mergeParts(list, joint);
            const lines = this.linesMesh("fighterlines", this.edgeLines(merged, mode, joint), mat, joint);
            if (lines) out.push([lines, mat, flash]);
            if (rim && !glow) for (const m of merged) {
                const r = this.rimLines(m, rim);
                if (r) out.push([r, rim, rimFlash]);
            }
        }
        return out;
    },

    // (the line tiers, CHANGE 147: fight_model.ModelFighterVisual.looks) a detailed model's lines (its pieces already
    // black): each piece's edges on a copy of its skinned vertices (base3d's skinnedLines), so they bend with every
    // move; on lines its outline too, bending with it (rimLines). box: the body's posed box (CHANGE 150). Returns
    // [[mesh, its material, its hit flash's]]
    modelLines(meshes, box = null) {
        const fade = this.lineFade(), mode = this.wire, out = [];
        const mat = this.lineMaterial("model", 1, ...fade), flash = this.tintedLines("modelflash", FLASH, ...fade);
        const rim = mode === "outline" ? this.rimMaterial("model", fade) : null;
        const rimFlash = rim ? this.rimMaterial("modelflash", fade, FLASH) : null;
        for (const m of meshes) {
            const lines = this.skinnedLines(m, mode, mat);
            if (lines) out.push([withBox(lines, box), mat, flash]);
            const r = rim ? this.rimLines(m, rim) : null;
            if (r) out.push([withBox(r, box), rim, rimFlash]);
        }
        return out;
    },

    // (CHANGE 150: line_look.silhouette as the window draws it) lines: a round shape's outline is its back faces drawn
    // as a wireframe 1.7 times as thick as the lines (about 2 pixels at 720 high), behind its own black front faces,
    // which are pushed back twice as far as the other black faces (fighterFill: the window's depth offset of 2), so
    // the back faces' edges show at the outline and, where a round shape turns away steeply, a little inside it. WebGL
    // draws lines a pixel wide: here each edge of the shape is a line with its two faces' normals, shown where either
    // face looks away (the shader's test, so the skin can move it), drawn twice a pixel apart (thin instances,
    // offset in the picture). The edges are worked out once a shape (kept by its geometry: every fighter's copy of a
    // model shares it). Returns the lines mesh (under mesh, sharing its bones), or null
    rimLines(mesh, mat) {
        const geo = mesh.geometry;
        if (!geo) return null;
        const cache = this.scene.ccRims || (this.scene.ccRims = new Map());
        if (!cache.has(geo.uniqueId)) cache.set(geo.uniqueId, rimEdges(mesh));
        const made = cache.get(geo.uniqueId);
        if (!made) return null;
        const r = new BABYLON.Mesh(mesh.name + " rim", this.scene);
        const vd = new BABYLON.VertexData();
        vd.positions = made.pos;
        vd.indices = made.idx;
        vd.applyToMesh(r);
        r.setVerticesData("rimA", made.a, false, 3);
        r.setVerticesData("rimB", made.b, false, 3);
        r.setVerticesData("rimOther", made.o, false, 3);
        if (made.bones && mesh.skeleton) {
            for (const [kind, data] of made.bones) r.setVerticesData(kind, data, false, 4);
            r.skeleton = mesh.skeleton;
            r.numBoneInfluencers = mesh.numBoneInfluencers;
        }
        r.parent = mesh;
        r.material = mat;
        r.isPickable = false;
        r.thinInstanceSetBuffer("matrix", RIM_MATRICES, 16, true);
        r.thinInstanceSetBuffer("rimOffset", RIM_OFFSETS, 2, true);
        const b = mesh.getBoundingInfo();  // (the shape's own box: the offsets are in the picture)
        r.setBoundingInfo(new BABYLON.BoundingInfo(b.minimum.clone(), b.maximum.clone()));
        if (mesh.material === this.wireFill()) mesh.material = this.fighterFill();
        this.lineCount = (this.lineCount || 0) + made.idx.length / 2;
        return r;
    },

    // (CHANGE 150) the rim lines' material: the line colour (times tint: the hit flash), fading as the lines do
    rimMaterial(name, fade, tint = null) {
        const key = "lines:rim" + name;
        if (this.materials[key]) return this.materials[key];
        const m = this.materials[key] = new BABYLON.ShaderMaterial("cclinesrim" + name, this.scene, {vertexSource: RIM_VERT, fragmentSource: RIM_FRAG}, {
            attributes: ["position", "rimA", "rimB", "rimOther", "rimOffset"], uniforms: ["world", "viewProjection", "cameraPosition", "color", "fade", "screen"]});
        m.fillMode = BABYLON.Material.LineListDrawMode;
        m.backFaceCulling = false;
        m.ccLine = true;
        m.setVector2("fade", new BABYLON.Vector2(fade[0], fade[1]));
        m.ccDim = 1;
        m.ccPulse = 1;
        if (tint) m.ccTint = tint;
        this.lineMats.push(m);
        this.paintLine(m);
        // (the window's thickness: 1.7 times its lines' 1.2 pixels at 720 high, more on a taller picture)
        const spread = () => {
            const e = this.engine, h = e.getRenderHeight(), w = e.getRenderWidth();
            const half = Math.max(0.25, (1.7 * Math.max(1, Math.round(h / 720 * 12) / 10) - 1) / 2);
            m.setVector3("screen", new BABYLON.Vector3(Math.max(1, w), Math.max(1, h), half));  // (each copy moved half that)
        };
        spread();
        this.scene.onBeforeRenderObservable.add(spread);
        return m;
    },

    // (CHANGE 150) the black faces of a shape drawn with rim lines: pushed back as the window's are (its depth offset
    // of 2, twice the page's other black faces')
    fighterFill() {
        if (this.materials.fighterfill) return this.materials.fighterfill;
        const m = this.materials.fighterfill = this.wireFill().clone("fighterfill");
        m.zOffset = 2;
        m.zOffsetUnits = 2;
        m.ccTile = 1;
        return m;
    },

    applyPose(f, p) {
        f.n.hips.position.y = p.hz;
        for (const j of JOINTS) {
            const [h, pt, r] = p[j];
            const node = f.n[j];
            node.rotation.set(-pt * D2R, -h * D2R, -r * D2R);
        }
    },

    // (moved here from FightScene.frame, CHANGE 201) a fighter drawn at its state s (pos, h, a, k, hu...): the place
    // and heading eased as the window eases them, the detailed model's frame, the built fighter's pose blended to
    // the move's, the cartwheel, the blast's glow, the hit flash and the name over it
    poseFighter(f, s, dt) {
        const target = s.pos;
        if (!f.pos || Math.hypot(target[0] - f.pos[0], target[1] - f.pos[1], target[2] - f.pos[2]) > 2.5) f.pos = [...target];
        else f.pos = f.pos.map((v, i) => v + (target[i] - v) * Math.min(1, dt * 20));
        const dh = ((s.h - f.h + 180) % 360 + 360) % 360 - 180;
        f.h += Math.abs(dh) > 60 ? dh : dh * Math.min(1, dt * 22);
        if (f.model) f.model.frame(s, dt);
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
            // (the line tiers: the lines whitened, as the window's colour scale on the body does: CHANGE 147; ultra:
            // the whole fighter's colours scaled, as the window's)
            if (f.lines) for (const [m, base, white] of f.lines) m.material = flash ? white : base;
            else f.root.getChildMeshes(false).forEach(m => { if (m.material === f.main || m.material === f.flashMat) m.material = flash ? (f.flashMat = f.flashMat || this.material("flash", [1, 0.95, 0.9], 0.5, 0, 0.8)) : f.main; });
        }
        f.label.position = v3(f.pos[0], f.pos[1], f.pos[2] + 2.05 * f.size + (f.labelLift ?? 0.1));
    },

    // (the line tiers, CHANGE 147) a ball's edges, in its own frame (a blast, the energy in a hand): every edge on both
    // looks (the window's ball of 10 sides turns 36 degrees an edge, past the crease that lines draws)
    lineSphere(r) {
        const s = BABYLON.MeshBuilder.CreateSphere("ball", {diameter: r * 2, segments: 5}, this.scene);
        const lists = this.edgeLines([s], "all");
        s.dispose();
        return lists;
    },
};
