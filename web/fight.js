// Fight Lab in Club Coders Live (CHANGE 130): the hall and its rings (fight_sim.py's constants, drawn after
// fight_gfx.StageVisual), the hazards from each snapshot (fire jets, spikes, ice, ropes or an open edge), the
// fighters built from their designs on a 13-joint skeleton and posed by the game's own pose code (fight_gfx.py's
// stance, attacks, falls, ported line for line below), the 30-a-second JSON states blended two behind, and the
// teacher's Fight Lab controls. The skinned models (woman, man, Robin) are the app's own (fightmodels.js, on the lit
// tiers); until a fighter's model is loaded, and on blocks, it is drawn as the primitive human or robot in its
// colours, with its weapon. The effects and the camera are the window's (fightfx.js: fight_fx.py, the stage's jets,
// blasts and glowing ropes and edges from fight_gfx.StageVisual, and fight_camera.py's five views).
// Panda joint angles (h, p, r) are Babylon rotation (-p, -h, -r); positions game (x, y, z) -> Babylon (x, z, y).
// (CHANGE 147) Every tier, as the window's since its CHANGE 147: mesh and lines draw the meshes black with their edges
// as lines (base3d.js), each moving part's own (each joint of a fighter, a skinned model's bending with it), a grid on
// the rings' canvas and the hall's floor on lines, the glowing parts' lines pulsing; ultra draws the window's smooth
// fighters and hall (fightfx.js, from models/fight_ultra.json and stage_ultra.json) once loaded.

/* global BABYLON */

import {BaseScene, TIERS, v3, rgb255, lerp, lerpDeg, mulberry} from "./base3d.js";
import {toneMap} from "./pbr.js";
import {FighterModel, withBox} from "./fightmodels.js";
import {AfterFx} from "./kartfx.js";
import {FightFX, FightCamera, CAM_MODES, CAM_NAMES, loadFightModels, fightModelsData, loadStageModels, stageModelsData,
        fighterLayout, fighterJointMesh, fighterAtlas, FIGHTER_GLOW, makeUltraRing, makeUltraHall, loadPandaFont, wordsSize,
        drawWords} from "./fightfx.js";
import {FightHud} from "./hud.js";
import {Sound} from "./sound.js";
import {FighterAhead} from "./ahead.js";

const $ = id => document.getElementById(id);
loadPandaFont();  // (the window's letters, asked for as the page opens: CHANGE 150)
const D2R = Math.PI / 180;
const RING_CENTRES = [[0, 0], [16, 0], [-16, 0], [0, 16], [16, 16], [-16, 16]];
const MAT_COLOURS = [[0.12, 0.13, 0.2], [0.35, 0.06, 0.06], [0.06, 0.2, 0.12], [0.2, 0.08, 0.3], [0.3, 0.2, 0.05], [0.05, 0.18, 0.3]];
const PAD_COLOURS = [[0.85, 0.1, 0.1], [0.95, 0.95, 0.95], [0.1, 0.25, 0.85]];
const JET_ANGLES = [45, 135, 225, 315];
const EDGE_GLOW = [4.0, 1.2, 0.2];  // (fight_gfx.py)
const MOVES = new Set(["punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam", "cartwheel"]);
// (CHANGE 147) mesh and lines: where the lines fade into the dark (fight_gfx.LOOK_FADE) and the grids on lines (every
// GRID m on the hall's floor, every MAT_GRID m on a ring's canvas); ultra: the hall's air the stands and walls fade
// into (fight_gfx.HAZE, linear) and how thick (per metre); the hit flash's colour scale (the window's body's)
const LOOK_FADE = {all: [18, 75], outline: [25, 110]}, GRID = 2.0, MAT_GRID = 1.0;
const HAZE = [0.01, 0.01, 0.018], HAZE_DENSITY = 0.01, EXPOSURE = 0.8, FLASH = [3.0, 2.6, 2.4];

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

// ---------- the scene ----------
export class FightScene extends BaseScene {
    static TIERS = TIERS;  // (every tier, the line tiers and ultra too, as the window: CHANGE 147)
    // (ultra's after-effects, kartfx.js's AfterFx, as Robot Lab's: a gentle glow on the lamps, visors, cores and
    // ropes and a little sharpening, 4x MSAA on that picture as the window's ultra; no SSAO, no reflection probe)
    static ULTRA_FX = {ssao: false, sharpen: true, samples: 4, bloomWeight: 0.25};
    // (the Graphics tab: what this game's lines and ultra draw)
    static TIER_TEXT = {lines: "lines: black, the outlines in one colour (the round fighters' too) and a grid on the rings and the hall's floor (an old vector arcade game).",
                        ultra: "ultra: for a strong graphics card: the window's smooth fighters (armour, visors and lights, a gi, a face and hair) and hall (padded rings with the club's boards, posts and ropes, the stands and their crowd, the screens, the lighting rig, walls and roof), soft 4096 shadows, glow, sharper textures at a slant."};

    constructor(canvas, tier, engine) {
        // fight_gfx.init's lights: a key light high over the hall, a dim blue fill, the arena's reflections, and a
        // spotlight over each ring in use (setSetup); on ultra a haze over the hall's far parts alone (fog.picked, as
        // the window's), given as the colour the tone curve makes of its light
        super(canvas, tier, engine, {sky: [0.02, 0.02, 0.04], radius: 9, target: [0, 0, 1], ground: [0.1, 0.1, 0.14], hemi: 0.45, sun: 1.5,
                                     sunDir: [-0.25, -0.9, 0.45],
                                     pbr: {background: [0.01, 0.01, 0.02], exposure: EXPOSURE, ambient: [0.07, 0.07, 0.1], sky: "env",
                                           fog: {colour: toneMap(HAZE, Math.pow(2, EXPOSURE)), density: HAZE_DENSITY, picked: true},
                                           sun: {colour: [1.1, 1.05, 1.0], offset: [6, -12, 26], film: 16, near: 5, far: 60, bias: 0.005},
                                           spots: FightScene.spots([0])}});
        this.setup = {rings: [0], rs: 4.5, hazards: {}, look: {}};
        this.fighters = new Map();
        this.list = [];
        this.cam = new FightCamera("fight");  // (fight_camera.FightCamera: the five views, each with its zoom)
        this.myId = null;                     // (your fighter: the one the camera's own views follow)
        this.ringMeshes = new Map();
        this.stageT = 0;                      // (the stage's clock: the jets' puffs, the ropes' and edges' pulses)
        this.zapUntil = {};
        this.build();
    }

    get mode() { return this.cam.mode; }

    static spots(rings) {  // fight_gfx.build_lights: one over each ring in use (at most 6)
        return (rings || [0]).slice(0, 6).map(i => {
            const [cx, cy] = RING_CENTRES[i] || [0, 0];
            return {pos: [cx - 2.5, cy - 5.5, 9.5], at: [cx, cy, 0], colour: [5.5, 5.2, 4.8], fov: 52, att: [1, 0, 0.012]};
        });
    }

    build() {  // (ultra's after-effects let go before the scene they were made for: CHANGE 147)
        if (this.after) { this.after.dispose(); this.after = null; }
        super.build();
    }

    populate() {
        // (ultra, CHANGE 147) the window's fighters and hall once both files are here (asked for on ultra alone): high's
        // until then, or if they don't come; then everything is made again with them
        this.ultra = !!(this.settings.ultra && this.lighting);
        this.ultraFighters = this.ultra && !!fightModelsData();
        this.ultraStage = false;
        this.lineCount = 0;
        this.lineStats = null;
        this.glowLines = {};  // (the line tiers: the glowing parts' line materials, pulsed in frame())
        if (this.ultra) {
            const scene = this.scene;
            Promise.all([loadFightModels(), loadStageModels()]).then(([f, s]) => {
                if (this.scene === scene && ((f && !this.ultraFighters) || (s && !this.ultraStage))) this.build();
            });
        }
        this.buildStage();
        this.shadowCulling();
        this.drawOrder();
        this.after = this.ultra && FightScene.ULTRA_FX ? new AfterFx(this, FightScene.ULTRA_FX) : null;
        if (this.after) {  // (CHANGE 150: the glow made from a quarter-size picture, blurred as far across: the same glow, cheaper)
            this.after.pipeline.bloomScale = 0.25;
            this.after.pipeline.bloomKernel = 24;
        }
        this.fx = new FightFX(this);
        // the camera is placed by the window's views every frame (drags, the wheel and keys are FightGame's), so it
        // takes no input of its own and may go anywhere they put it
        const cam = this.camera;
        cam.detachControl();
        cam.lowerRadiusLimit = 0.01;
        cam.upperRadiusLimit = 1000;
        cam.lowerBetaLimit = 0.001;
        cam.upperBetaLimit = Math.PI - 0.001;
        cam.maxZ = 300;
        this.cam.pos = null;
        const list = this.list;
        this.fighters.clear();
        for (const f of list) this.addFighter(f);
    }

    // (CHANGE 150) the shadow map draws only the casters inside the key light's view (its 16 m round what the camera
    // looks at, as the window's shadow camera culls): Babylon's draws its whole list every frame, every ring's and
    // every fighter's, the far rings' 3D bodies too
    shadowCulling() {
        const L = this.lighting, rtt = L && L.rtt;
        if (!rtt || !L.sunCam) return;
        const out = [];
        rtt.getCustomRenderList = (layer, list, n) => {
            const planes = BABYLON.Frustum.GetPlanes(L.sunCam.getTransformationMatrix(true));
            out.length = 0;
            for (let i = 0; i < n; i++) {
                const m = list[i];
                if (!m || !m.isEnabled() || !m.isVisible) continue;
                m.computeWorldMatrix();
                if (m.alwaysSelectAsActiveMesh || m.isInFrustum(planes)) out.push(m);
            }
            return out;
        };
    }

    // (CHANGE 150) the lit tiers draw the fighters first, then the rings and the rest, the crowd, the stands and the
    // hall, and the floor last (a mesh's ccRank, else what its material is), each group by material as Babylon would:
    // what is hidden behind them isn't lit and then painted over (Babylon's own order is the materials' age, the
    // hall's first). The line tiers keep base3d's (every black face, then every line)
    drawOrder() {
        if (this.wire || this.tier === "blocks") return;
        const BY_MATERIAL = {hall: 4, walk: 4, stands: 3, crowd: 2, screen: 3, screenglow: 3, truss: 3, lamp: 3};
        const rank = sub => {  // (worked out once a mesh)
            const m = sub.getMesh();
            if (m.ccRank === undefined) m.ccRank = BY_MATERIAL[String((m.material || {}).name).split(":")[0]] ?? 1;
            return m.ccRank;
        };
        this.scene.setRenderingOrder(0, (a, b) => (rank(a) - rank(b)) || BABYLON.RenderingGroup.PainterSortCompare(a, b));
    }

    setSetup(setup) {
        const key = JSON.stringify(setup);
        if (key === this.setupKey) return;
        this.setupKey = key;
        this.setup = setup;
        this.look.pbr.spots = FightScene.spots(setup.rings);
        this.build();
    }

    // (CHANGE 147) mesh and lines: the rings' still parts' edges as lines (with a grid on each canvas on lines), the
    // hall's (with a grid on its floor on lines), the rig's, and each part that glows or moves its own (stageLines);
    // ultra: the window's rings (fightfx.js's makeUltraRing) in place of the platform, base, mat, posts, pads and ropes,
    // and its hall (makeUltraHall); the markings, logo, open edge's glow, jets, spikes and ice kept
    buildStage() {
        const {rings, rs: R, hazards: hz, look} = this.setup;
        const roped = !hz.ring_out, blocks = this.tier === "blocks";
        const file = this.ultra ? stageModelsData() : null, ultra = !!file;
        this.ultraStage = ultra;
        const M = (name, rgb, rough, metal, tex, tile, emission) => this.material(name, rgb, rough, metal, 0, {tex, tile, emission});
        const statics = [], hall = [];
        const S = m => { statics.push(m); return m; };
        this.buildHall(hall, look, file);
        const marks = M("marks", [0.9, 0.9, 0.95], 0.6, 0);
        const hazard = blocks ? M("hazard", [0.95, 0.75, 0.08], 1, 0) : M("hazard", [1, 1, 1], 1, 0, "hazard", 0.8);
        this.jets = new Map();
        this.ropes = [];
        this.glows = new Map();  // ring -> {ropes, edge}: the materials that pulse (fight_gfx.StageVisual.update)
        this.ultraRings = [];
        const moving = [];  // (the line tiers: [meshes, glow]: the ropes' and an open edge's lines, pulsing as they glow)
        for (const i of rings || [0]) {
            const [cx, cy] = RING_CENTRES[i] || [0, 0];
            const platR = roped ? R + 0.7 : R + 0.1;
            if (!ultra) {
                S(this.cyl(null, platR, 0.4, "z", M("platform", [0.2, 0.2, 0.23], 1, 1, "steel", 0.6), cx, cy, -0.42, null, 48));
                S(this.cyl(null, platR + 0.08, 0.06, "z", M("platrim", [0.08, 0.08, 0.1], 0.6, 0.5, "paint"), cx, cy, -0.8 + 0.06, null, 48));
                S(this.cyl(null, platR - 0.02, 0.012, "z", M("mat" + i, MAT_COLOURS[i % 6], 0.95, 0, "concrete", 0.4), cx, cy, -0.01, null, 48));
            }
            // (each dash along x, as the window's: CHANGE 150, they were turned along the circle)
            if (!hz.slippery) for (let k = 0; k < 40; k++) {
                const a = k / 40 * Math.PI * 2;
                S(this.box(null, 0.14, 0.04, 0.003, marks, cx + Math.cos(a) * 0.45 * R, cy + Math.sin(a) * 0.45 * R, 0.004));
            }
            for (const sx of [-1.6, 1.6]) S(this.box(null, 0.05, 0.45, 0.003, marks, cx + sx, cy, 0.004));
            // (the line colour on the line tiers: CHANGE 147)
            // (the window's TextNode: its letters, 0.75 a unit, the baseline 0.25 m below the middle: CHANGE 150)
            const logo = this.words(i === 0 ? (look.name || "FIGHT LAB") : `RING ${i + 1}`, 0.75, this.wire ? "#ffffff" : "#e8d49a", 0.8, [cx, cy - 0.25, 0.008], [0, -90, 0]);
            if (this.wire) this.lettering(logo);
            const ropeMat = !roped ? null : hz.electric_ropes ? M("eropes" + i, [0.5, 0.8, 1.0], 0.5, 0, null, null, [0.4, 1.2, 3.0]) : M("ropes", [0.85, 0.12, 0.1], 0.5, 0);
            if (roped && hz.electric_ropes) this.glows.set(i, {ropes: ropeMat});
            if (ultra) {  // (the window's ring for this size: the ropes their own mesh, glowing as the lower tiers' do)
                const u = makeUltraRing(this, file, i, R, roped, [cx, cy], MAT_COLOURS[i % 6], PAD_COLOURS[i % 3], ropeMat);
                this.ultraRings.push(u);
                if (u.ropes) this.ropes.push(u.ropes);
                this.shadowCast(u.casters);
            } else if (roped) {
                const postR = (R + 0.08) / Math.cos(22.5 * D2R);
                const posts = [];
                for (let k = 0; k < 8; k++) {
                    const a = (22.5 + 45 * k) * D2R, px = cx + Math.cos(a) * postR, py = cy + Math.sin(a) * postR;
                    posts.push([px, py]);
                    S(this.cyl(null, 0.08, 0.7, "z", M("post", [0.75, 0.75, 0.8], 1, 1, "steel", 0.8), px, py, 0.7, null, 12));
                    S(this.box(null, 0.12, 0.12, 0.45, M("pad" + (i % 3), PAD_COLOURS[i % 3], 0.6, 0.2, "paint"), px, py, 0.85));
                }
                for (const z of [0.45, 0.85, 1.25]) for (let k = 0; k < 8; k++) {
                    const [ax, ay] = posts[k], [bx, by] = posts[(k + 1) % 8];
                    const rope = BABYLON.MeshBuilder.CreateTube("rope", {path: [v3(ax, ay, z), v3(bx, by, z)], radius: 0.035, tessellation: 8}, this.scene);
                    rope.material = ropeMat;
                    this.ropes.push(rope);
                }
            }
            if (roped) moving.push([this.ropes.slice(-(ultra ? 1 : 24)), "ropes" + i]);
            else {
                const band = this.edgeBand(R, cx, cy);
                band.material = M("edge" + i, [0, 0, 0], 1, 0, null, null, EDGE_GLOW);
                this.glows.set(i, {edge: band.material});
                moving.push([[band], "edge" + i]);
            }
            if (hz.fire_jets) {  // the striped plates and nozzles; the flames are soft puffs rising up each jet (fightfx.js)
                // (the line tiers: a flame of lines on each, flickering and growing with the jet, no puffs: CHANGE 147)
                const jets = JET_ANGLES.map(a => {
                    const x = cx + Math.cos(a * D2R) * 0.55 * R, y = cy + Math.sin(a * D2R) * 0.55 * R;
                    S(this.cyl(null, 0.32, 0.01, "z", hazard, x, y, 0.005, null, 20));
                    S(this.cyl(null, 0.16, 0.02, "z", M("nozzle", [0.15, 0.15, 0.16], 1, 1, "steel"), x, y, 0.01, null, 16));
                    return [x, y, this.wire ? this.flameLines(x, y, "jet" + i) : null];
                });
                this.jets.set(i, jets);
            }
            if (hz.spikes) for (const a of [0, 90, 180, 270]) {
                const x = cx + Math.cos(a * D2R) * 0.78 * R, y = cy + Math.sin(a * D2R) * 0.78 * R;
                S(this.cyl(null, 0.45, 0.01, "z", hazard, x, y, 0.005, null, 24));
                for (let k = 0; k < 7; k++) {
                    const r = k ? 0.27 : 0, b = k * Math.PI / 3;
                    S(this.cyl(null, 0.06, 0.12, "z", M("spike", [0.8, 0.8, 0.85], 0.4, 1, "steel"), x + Math.cos(b) * r, y + Math.sin(b) * r, 0.14, 0, 8));
                }
            }
            if (hz.slippery) {
                S(this.cyl(null, 0.45 * R, 0.006, "z", M("ice", [0.55, 0.75, 0.92], 0.06, 0.3), cx, cy, 0.002, null, 48));
                S(this.cyl(null, 0.45 * R + 0.05, 0.004, "z", M("iceedge", [0.85, 0.95, 1.0], 0.3, 0), cx, cy, 0, null, 48));
                const shine = M("iceshine", [1, 1, 1], 0.02, 0, null, null, [0.6, 0.8, 1.0]);  // (glowing streaks across the ice)
                for (let k = 0; k < 6; k++) S(this.box(null, 0.3 * R, 0.012, 0.002, shine, cx + Math.cos(k * 1.05) * 0.12 * R, cy + Math.sin(k * 1.05) * 0.15 * R, 0.01));
            }
        }
        const still = this.mergeStatic(statics), hallStill = this.mergeStatic(hall);
        if (this.wire) this.stageLines(still, hallStill, moving);
    }

    // (CHANGE 150: fight_gfx.build_ring's open edge) a flat glowing band round the ring from R - 0.05 to R + 0.04 m,
    // 6 mm up, as 64 quads of two triangles each (the window's: so mesh draws the same edges; it was a torus with many
    // more)
    edgeBand(R, cx, cy) {
        const pos = [], idx = [], nor = [], r0 = R - 0.05, r1 = R + 0.04, z = 0.006;
        for (let k = 0; k < 64; k++) {
            const a0 = 2 * Math.PI * k / 64, a1 = 2 * Math.PI * (k + 1) / 64, o = pos.length / 3;
            for (const [a, r] of [[a0, r0], [a1, r0], [a1, r1], [a0, r1]]) { pos.push(cx + Math.cos(a) * r, z, cy + Math.sin(a) * r); nor.push(0, 1, 0); }
            idx.push(o, o + 2, o + 1, o, o + 3, o + 2);  // (the window's fan from the first corner, wound for Babylon)
        }
        const mesh = new BABYLON.Mesh("edge", this.scene), vd = new BABYLON.VertexData();
        vd.positions = pos; vd.normals = nor; vd.indices = idx;
        vd.applyToMesh(mesh);
        return mesh;
    }

    lineFade() {  // (where the lines fade out, as the window's dark fog: fight_gfx.LOOK_FADE, CHANGE 147)
        return LOOK_FADE[this.wire] || LOOK_FADE.outline;
    }

    // (the line tiers, CHANGE 147: fight_gfx.StageVisual.looks) the rings' still parts' edges as lines in tiles (with
    // on lines a grid every MAT_GRID m on each canvas, cut at the ring's edge: fight_gfx.ring_grid), the hall's (with on
    // lines a grid every GRID m on its floor, hidden where the platforms and walkways stand), the rig's (hidden with
    // it), and the ropes' and an open edge's own, their material pulsed in frame() as they glow
    stageLines(still, hallStill, moving) {
        const t0 = performance.now(), before = this.lineCount || 0, fade = this.lineFade(), fill = this.wireFill();
        const mat = this.lineMaterial("stage", 1, ...fade), outline = this.wire === "outline";
        const seg = (L, a, b) => { const k = L.pos.length / 3; L.pos.push(a[0], a[2], a[1], b[0], b[2], b[1]); L.idx.push(k, k + 1); };
        const lists = this.edgeLines(still.filter(m => m.material === fill), this.wire);
        let grid = lists.idx.length / 2;
        if (outline) {
            const r = (this.setup.rs || 4.5) - 0.05, z = 0.006;
            for (const i of this.setup.rings || [0]) {
                const [cx, cy] = RING_CENTRES[i] || [0, 0];
                for (let c = -Math.floor(r / MAT_GRID) * MAT_GRID; c <= r + 1e-9; c += MAT_GRID) {
                    const half = Math.sqrt(Math.max(0, r * r - c * c));
                    if (half < 0.05) continue;
                    seg(lists, [cx + c, cy - half, z], [cx + c, cy + half, z]);
                    seg(lists, [cx - half, cy + c, z], [cx + half, cy + c, z]);
                }
            }
        }
        grid = lists.idx.length / 2 - grid;
        this.staticLines("stagelines", lists, mat);
        const hl = this.edgeLines(hallStill.filter(m => m.material === fill), this.wire), edges = hl.idx.length / 2;
        if (outline) {  // (line_look.grid: each line cut at the rectangle's edges, not along them)
            const [x0, y0, x1, y1] = [-32, -16, 32, 32], z = -0.8 + 0.002;
            for (let x = Math.ceil(x0 / GRID) * GRID; x < x1 - 1e-6; x += GRID) if (x > x0 + 1e-6) seg(hl, [x, y0, z], [x, y1, z]);
            for (let y = Math.ceil(y0 / GRID) * GRID; y < y1 - 1e-6; y += GRID) if (y > y0 + 1e-6) seg(hl, [x0, y, z], [x1, y, z]);
        }
        grid += hl.idx.length / 2 - edges;
        this.staticLines("halllines", hl, mat);
        const rigLines = this.rig.length ? this.linesMesh("riglines", this.edgeLines(this.rig, this.wire), mat) : null;
        if (rigLines) this.rig.push(rigLines);
        for (const [meshes, glow] of moving) {
            const m = this.glowLines[glow] = this.glowLines[glow] || this.lineMaterial(glow, 1, ...fade);
            this.linesMesh(glow.startsWith("edge") ? "edgelines" : "ropelines", this.edgeLines(meshes, this.wire), m);
        }
        this.lineStats = {segments: (this.lineCount || 0) - before, grid, ms: Math.round(performance.now() - t0)};
    }

    // (the line tiers, CHANGE 147) a fire jet's flame of lines (fight_gfx: a cone 0.2 m across its foot, 1 m high, its
    // edges alone: no black faces, a glow is see-through), on a node at the nozzle that frame() grows and shows
    flameLines(x, y, glow) {
        const node = new BABYLON.TransformNode("jetlines", this.scene);
        node.position = v3(x, y, 0.03);
        const cone = this.cyl(node, 0.2, 0.5, "z", this.wireFill(), 0, 0, 0.5, 0.03, 8);
        const m = this.glowLines[glow] = this.glowLines[glow] || this.lineMaterial(glow, 1, ...this.lineFade());
        this.linesMesh("jetlines", this.edgeLines([cone], this.wire, node), m, node);
        cone.dispose();
        node.setEnabled(false);
        return node;
    }

    // (the line tiers, CHANGE 147) a ball's edges, in its own frame (a blast, the energy in a hand): every edge on both
    // looks (the window's ball of 10 sides turns 36 degrees an edge, past the crease that lines draws)
    lineSphere(r) {
        const s = BABYLON.MeshBuilder.CreateSphere("ball", {diameter: r * 2, segments: 5}, this.scene);
        const lists = this.edgeLines([s], "all");
        s.dispose();
        return lists;
    }

    // the hall round the rings: a concrete floor, walkways, tiered stands with a crowd, big screens and a lighting
    // truss (fight_gfx.build_hall); (ultra, CHANGE 147) the window's hall (fightfx.js's makeUltraHall), the screens'
    // lettering kept; (the line tiers) the name on the screens in the line colour
    buildHall(statics, look, file = null) {
        const M = (name, rgb, rough, metal, tex, tile, emission) => this.material(name, rgb, rough, metal, 0, {tex, tile, emission});
        const S = m => { statics.push(m); return m; };
        this.ultraParts = null;
        if (file) {
            const u = this.ultraParts = makeUltraHall(this, file, look);
            this.rig = u.rig;
            this.shadowCast(u.casters);
            // (the hall's name on each screen, facing the hall's middle, as the window's ultra writes it)
            for (const [x, y, z, h] of (file.notes || {}).screens || [[0, 36.5, 6, 0], [0, -20.5, 6, 180]]) {
                const front = h === 0 ? -1 : 1;
                // (the window's glowing orange lettering comes out nearly white through its tone curve)
                this.words(look.name || "FIGHT LAB", 2.2, "#fff0dc", 1.0, [x, y + front * 0.335, z - 0.45], [h, 0, 0]);
            }
            return;
        }
        const xs = RING_CENTRES.map(c => c[0]), ys = RING_CENTRES.map(c => c[1]);
        const pad = (this.setup.rs || 4.5) + 5;
        const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
        const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, hx = (x1 - x0) / 2, hy = (y1 - y0) / 2, floorZ = -0.8;
        S(this.box(null, hx + 14, hy + 14, 0.05, M("hall", [0.3, 0.3, 0.34], 1, 0, "concrete", 0.25), cx, cy, floorZ - 0.05));
        const walk = M("walk", [0.32, 0.26, 0.2], 1, 0, "concrete", 0.5);
        S(this.box(null, hx, 0.9, 0.02, walk, cx, 8, floorZ + 0.02));
        for (const x of [-8, 8]) S(this.box(null, 0.9, hy, 0.02, walk, x, cy, floorZ + 0.02));
        const standM = M("stands", [0.22, 0.24, 0.3], 1, 0, "concrete", 0.5), crowdM = M("crowd", [0.5, 0.5, 0.5], 0.9, 0);
        const shirts = [[0.8, 0.1, 0.1], [0.1, 0.3, 0.8], [0.9, 0.8, 0.2], [0.2, 0.6, 0.3], [0.9, 0.9, 0.9], [0.15, 0.15, 0.18], [0.9, 0.5, 0.1], [0.5, 0.2, 0.6]];
        const skins = [[0.85, 0.65, 0.5], [0.6, 0.42, 0.3], [0.4, 0.28, 0.2], [0.92, 0.75, 0.62]];
        const rnd = mulberry(5), crowd = look.crowd !== false && this.tier !== "blocks";
        for (let side = 0; side < 4; side++) {
            for (let row = 0; row < 5; row++) {
                const d = row * 1.2 + 1.5, z = floorZ + 0.3 + row * 0.6;
                let spots;
                if (side < 2) {
                    const y = side === 0 ? y1 + d : y0 - d;
                    S(this.box(null, hx + 6, 0.6, (z - floorZ) / 2, standM, cx, y, (z + floorZ) / 2));
                    spots = Array.from({length: Math.floor((hx + 5) * 2 / 0.9)}, (_, k) => [x0 - 5 + k * 0.9 + (row % 2 ? 0.45 : 0), y]);
                } else {
                    const x = side === 2 ? x1 + d : x0 - d;
                    S(this.box(null, 0.6, hy + 6, (z - floorZ) / 2, standM, x, cy, (z + floorZ) / 2));
                    spots = Array.from({length: Math.floor((hy + 5) * 2 / 0.9)}, (_, k) => [x, y0 - 5 + k * 0.9 + (row % 2 ? 0.45 : 0)]);
                }
                if (!crowd) continue;
                for (const [x, y] of spots) {
                    if (rnd() >= 0.8) continue;
                    const tall = 0.22 + rnd() * 0.08;
                    S(this.tinted(this.box(null, 0.19, 0.14, tall, crowdM, x, y, z + tall), shirts[Math.floor(rnd() * shirts.length)]));
                    S(this.tinted(this.box(null, 0.09, 0.09, 0.1, crowdM, x, y, z + tall * 2 + 0.11), skins[Math.floor(rnd() * skins.length)]));
                }
            }
        }
        // big screens at both ends with the hall's name
        for (const [y, back] of [[y1 + 9, -1], [y0 - 9, 1]]) {
            S(this.box(null, 6.5, 0.3, 2.0, M("screen", [0.08, 0.08, 0.1], 1, 1, "steel"), cx, y, 6.0));
            S(this.box(null, 6.2, 0.05, 1.75, M("screenglow", [0, 0, 0], 1, 0, null, null, [0.05, 0.02, 0.12]), cx, y + 0.3 * back, 6.0));
            // (each screen's words face the rings: the window's TextNode, 1.6 a unit; its glowing orange comes out of its tone curve
            // nearly white, as the ultra screens')
            const name = this.words(look.name || "FIGHT LAB", 1.6, this.wire ? "#ffffff" : "#f8eabf", 1.0, [cx, y + 0.4 * back, 5.55], [back < 0 ? 0 : 180, 0, 0]);
            if (this.wire) this.lettering(name);
        }
        // the lighting truss over the rings
        const truss = [], trussM = M("truss", [0.2, 0.2, 0.22], 1, 1, "steel"), lampM = M("lamp", [1, 1, 1], 0.3, 0, null, null, [6, 5.5, 5]);
        for (const y of [0, 16]) {
            truss.push(this.box(null, hx, 0.15, 0.15, trussM, cx, y, 8.5));
            for (const x of [-16, 0, 16]) for (const dx of [-2.5, 2.5]) truss.push(this.box(null, 0.3, 0.25, 0.12, lampM, x + dx, y, 8.3));
        }
        for (const x of [x0, x1]) for (const y of [0, 16]) truss.push(this.box(null, 0.2, 0.2, 4.8, trussM, x, y, floorZ + 4.8));
        this.rig = this.mergeStatic(truss);
    }

    // a box in its own colour (a person in the crowd): vertex colours, so a whole crowd is one mesh
    tinted(mesh, rgb) {
        const n = mesh.getTotalVertices(), c = new Array(n * 4);
        for (let i = 0; i < n; i++) { c[i * 4] = rgb[0]; c[i * 4 + 1] = rgb[1]; c[i * 4 + 2] = rgb[2]; c[i * 4 + 3] = 1; }
        mesh.setVerticesData(BABYLON.VertexBuffer.ColorKind, c);
        return mesh;
    }

    // ---------- the fighters ----------
    setFighters(list) {
        for (const f of this.fighters.values()) { f.label.dispose(false, true); if (f.plate) f.plate.dispose(false, true); f.root.dispose(); if (f.model) f.model.dispose(); }
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
    }

    // (CHANGE 143) fight_gfx.FighterVisual.number_plate: the fighter's number (or its name), 8 letters at most, on the
    // waist joint where the window puts it, (0, -0.18) on a robot and (0, -0.14) on a person, 0.34 up: the back of the
    // torso, read from behind (a robot's in its light colour, glowing as Robin's does; a person's in the trim colour)
    numberPlate(joint, d, robot, rgb) {
        const text = String((d.style || {}).number || d.name || "").slice(0, 8);
        if (!text) return null;
        // (CHANGE 150: the window's TextNode, 0.07 a unit, its baseline there, read from behind)
        const css = `rgb(${rgb.map(c => Math.round(255 * Math.max(0, Math.min(1, c)))).join(",")})`;
        const plane = this.words(text, 0.07, css, robot ? 1 : 0.6, [0, robot ? -0.18 : -0.14, 0.34], [0, 0, 0], joint);
        if (!this.lighting) plane.material.emissiveColor = new BABYLON.Color3(0.4, 0.4, 0.4);
        return plane;
    }

    // (CHANGE 150) words as the window's TextNode writes them (centred, in Panda's own letters: fightfx.js's drawWords):
    // a flat card in its own x and y (as a TextNode's x and z: read from in front, its -y), its middle on the baseline,
    // scale metres a unit, at pos turned by hpr (the window's, degrees) under parent; colour a CSS colour, paint how
    // bright it is unlit on the lit tiers (as floorText). Until the letters are loaded, the browser's sans, and the scene
    // made again once they are
    words(text, scale, colour, paint, pos, hpr, parent = null) {
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
    }

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
    }

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
    }

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
    }

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
    }

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
    }

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
    }

    // (CHANGE 150) the black faces of a shape drawn with rim lines: pushed back as the window's are (its depth offset
    // of 2, twice the page's other black faces')
    fighterFill() {
        if (this.materials.fighterfill) return this.materials.fighterfill;
        const m = this.materials.fighterfill = this.wireFill().clone("fighterfill");
        m.zOffset = 2;
        m.zOffsetUnits = 2;
        m.ccTile = 1;
        return m;
    }

    applyPose(f, p) {
        f.n.hips.position.y = p.hz;
        for (const j of JOINTS) {
            const [h, pt, r] = p[j];
            const node = f.n[j];
            node.rotation.set(-pt * D2R, -h * D2R, -r * D2R);
        }
    }

    // fs: [{id, pos, h, a, k, hu, ri (its ring), ...}] for the drawn rings; dt seconds
    frame(fs, rings, dt, t) {
        const seen = new Set();
        const closeUp = ["fight", "me", "shoulder"].includes(this.cam.mode), watched = this.watchRing ?? 0;
        for (const s of fs) {
            const f = this.fighters.get(s.id);
            if (!f) continue;
            seen.add(s.id);
            const hide = s.pos[2] < -1.5;
            f.root.setEnabled(!hide);
            f.label.setEnabled(!hide && !(closeUp && s.ri === watched));  // (the fight screen shows their names)
            if (hide) { if (f.model) f.model.show(false); continue; }
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
        }
        for (const [id, f] of this.fighters) if (!seen.has(id)) { f.root.setEnabled(false); f.label.setEnabled(false); if (f.model) f.model.show(false); }
        // the camera first (the effects that face it face it where it is drawn), then the stage's moving parts and
        // the effects (fight_gfx.StageVisual.update, fight_fx.Effects.update)
        this.updateCamera(fs, rings, dt);
        this.stageT += dt;
        const T = this.stageT, fx = this.fx;
        fx.begin();
        const byIndex = new Map(rings.map(r => [r.i, r]));
        const G = this.glowLines || {};  // (the line tiers: the glowing parts' lines pulse as they glow: CHANGE 147)
        for (const [i, jets] of this.jets) {
            const powers = ((byIndex.get(i) || {}).hz || {}).jets || [];
            jets.forEach(([x, y, lines], k) => {
                const p = powers[k] || 0;
                if (lines) {  // (a flame of lines, growing with the jet and flickering)
                    lines.setEnabled(p > 0.05);
                    if (p > 0.05) lines.scaling.set(0.8 + 0.4 * p, 0.4 + 1.5 * p, 0.8 + 0.4 * p);
                } else if (p > 0.05) fx.jet(x, y, p, T);
            });
            this.pulseLine(G["jet" + i], 0.65 + 0.35 * Math.abs(Math.sin(T * 17 + i)));
        }
        for (const [i, g] of this.glows) {
            if (g.ropes) {  // electric ropes: a steady blue pulse, a white-blue flicker for a moment after a zap
                if ((this.zapUntil[i] ?? -1) > T) {
                    const f = Math.floor(T * 30) % 2 ? 6 : 2;
                    this.setGlow(g.ropes, [f * 0.6, f * 0.9, f * 1.6]);
                    this.pulseLine(G["ropes" + i], f === 6 ? 1 : 0.3);
                } else {
                    const pulse = 0.8 + 0.4 * Math.sin(T * 6 + i);
                    this.setGlow(g.ropes, [0.3 * pulse, 0.9 * pulse, 2.6 * pulse]);
                    this.pulseLine(G["ropes" + i], 0.5 + 0.4 * pulse);
                }
            }
            if (g.edge) {  // an open edge's glowing line breathes
                const pulse = 0.75 + 0.25 * Math.sin(T * 3 + i);
                this.setGlow(g.edge, EDGE_GLOW.map(c => c * pulse));
                this.pulseLine(G["edge" + i], pulse);
            }
        }
        let shots = 0;
        for (const r of rings) for (const sh of r.sh || []) if (shots++ < 12) fx.shot(sh, T);
        fx.update(dt);
        this.followSun();
    }

    // the hits (m.fx: [pos, damage, kind]) as the window takes them: the victim is the fighter nearest the hit (its
    // colour for the debris; a robot throws more sparks); a zap flashes that ring's electric ropes
    impacts(list, rings) {
        if (!this.fx || !list || !list.length) return;
        const all = (rings || []).flatMap(r => r.f || []);
        for (const [pos, dmg, kind] of list) {
            let best = null, far = Infinity;
            for (const f of all) {
                const d = (f.pos[0] - pos[0]) ** 2 + (f.pos[1] - pos[1]) ** 2 + (f.pos[2] - pos[2]) ** 2;
                if (d < far) { far = d; best = f; }
            }
            const v = best ? this.fighters.get(best.id) : null, d = v ? v.design || {} : {};
            const colour = v && Array.isArray(d.colour) ? rgb255(d.colour) : [0.8, 0.8, 0.8];
            this.fx.impact(pos, dmg, kind, colour, (d.body || "robot") === "robot");
            if (kind === "zap") this.zap(pos);
        }
    }

    zap(pos) {  // (fight_gfx.StageVisual.zap: the nearest ring's electric ropes flash)
        let best = null, far = Infinity;
        for (const i of this.setup.rings || [0]) {
            const [cx, cy] = RING_CENTRES[i] || [0, 0], d = Math.hypot(pos[0] - cx, pos[1] - cy);
            if (d < far) { far = d; best = i; }
        }
        if (best !== null) this.zapUntil[best] = this.stageT + 0.35;
    }

    // the window's camera (fight_camera.FightCamera.update, fightfx.js), on the watched ring: your fighter (or the
    // first in the ring) and the other one, then the shake from big hits (half of fight_fx's, as fight_client passes
    // it): the camera moves, what it looks at doesn't
    updateCamera(fs, rings, dt) {
        const cam = this.camera, watched = this.watchRing ?? 0;
        if (this.snapCamera) { this.cam.pos = null; this.snapCamera = false; }
        const ring = rings.find(r => r.i === watched) || null;
        const here = fs.filter(s => s.ri === watched && (s.a !== "ringout" || s.pos[2] > -1.5));
        const first = here.find(s => s.id === this.myId) || here[0] || null, other = here.find(s => s !== first) || null;
        const centreOf = r => r.c || RING_CENTRES[r.i] || [0, 0];
        const v = this.cam.update(dt, first ? first.pos.slice() : null, other ? other.pos.slice() : null,
                                  ring ? centreOf(ring) : [0, 0], rings.map(centreOf));
        const rig = ["fight", "me", "shoulder"].includes(v.mode);  // (the high views look down past the lighting rig: hidden)
        for (const m of this.rig || []) m.isVisible = rig;
        const off = this.fx ? this.fx.shakeOffset() : null;
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;  // (Panda's lens: the fov is across)
        cam.fov = v.fov * D2R;
        cam.minZ = 0.1;
        cam.setTarget(v3(...v.look));
        cam.setPosition(v3(v.pos[0] + (off ? off[0] : 0), v.pos[1] + (off ? off[1] : 0), v.pos[2] + (off ? off[2] : 0)));
    }

    setMode(mode) {
        this.cam.setMode(mode);
        this.snapCamera = true;
    }
}

export class FightGame {
    static detect(m) { return !!(m.rules && m.rules.styles && m.rules.bosses); }

    constructor(app) {
        this.app = app;
        this.id = "fightlab";
        // (CHANGE 167) your fighter's footwork drawn at once (ahead.js); each fighter's from the roster
        this.ahead = new FighterAhead();
        this.move = new Map();
        this.aheadNote = "your fighter's steps drawn as you press the keys";  // (app.js: the Graphics tab's Movement row)
        this.title = "Fight Lab";
        this.word = "fighter";
        this.scene = new FightScene(app.canvas, app.tier, app.engine);
        this.watch = null;
        this.mods = ["mods/stage.py", "mods/rules.py", "mods/fighters/<username>.py"];
        this.last = null;
        this.events = new Set();
        this.pickA = this.pickB = "";
        this.controlKind = "fight";  // (play.js: the arrows move, A S D W Space F the moves, Shift blocks, X crouches)
        this.hud = new FightHud();
        // (CHANGE 143) B: the rings box small (the title and the mode line) or full, kept on this computer as the
        // window keeps rings_small
        try { this.boardSmall = localStorage.getItem("rings_small") === "1"; } catch (e) { this.boardSmall = false; }
        this.hookCamera();
    }

    // B, or the rings box's Hide/Show button (fight_client.toggle_rings)
    toggleBoard() {
        this.boardSmall = !this.boardSmall;
        try { localStorage.setItem("rings_small", this.boardSmall ? "1" : "0"); } catch (e) { /* private window */ }
        this.renderBoard();
    }

    // (CHANGE 143) the window's keys (fight_client's key list and its camera keys), for a key list or help
    keyList() {
        const learner = this.app.state.role === "learner";
        return [["Arrows", "move (up and down sidestep)"], ["A", "punch (again for a combo)"], ["S", "kick (forward + S: high kick)"], ["D", "special"],
                ["W", "throw"], ["Space", "jump"], ["F", "cartwheel (when it's on)"], ["Shift", "block"], ["X", "crouch (X + Shift: low block)"],
                ...(learner ? [["P", "autopilot"], ["U", "upload a brain"]] : []),
                ["V", "camera view"], ["Q and E, or drag", "swing the view round (drag up and down tilts it)"], ["Wheel, + and -", "zoom"],
                ["Home", "the view back as it was"], ["O", "every ring"], ["[ and ]", "watch another ring"], ["B", "the rings box: small or full"],
                ["N", "sound on or off"]];
    }

    // the window's camera controls: dragging swings the view round and tilts it, the wheel (or + and -) zooms the
    // view in use, Q and E swing it round, Home puts it back, O shows every ring, [ and ] watch another ring
    hookCamera() {
        const canvas = this.app.canvas, cam = () => this.scene.cam;
        this.listeners = [
            [canvas, "wheel", e => { cam().wheel(this.app.wheelZoom ? this.app.wheelZoom(e) : e.deltaY > 0 ? 1 / 0.88 : 0.88); this.keepCamera(); }, {passive: true}],  // (the Settings' Wheel zoom: CHANGE 143)
            [canvas, "pointerdown", e => { this.dragFrom = [e.clientX, e.clientY]; try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* gone */ } }],
            [canvas, "pointermove", e => {
                if (!this.dragFrom) return;
                cam().drag((e.clientX - this.dragFrom[0]) / Math.max(1, canvas.clientWidth), (e.clientY - this.dragFrom[1]) / Math.max(1, canvas.clientHeight));
                this.dragFrom = [e.clientX, e.clientY];
            }],
            [canvas, "pointerup", () => { if (this.dragFrom) { this.dragFrom = null; this.keepCamera(); } }],
            [canvas, "pointercancel", () => { this.dragFrom = null; }],
            [canvas, "contextmenu", e => e.preventDefault()],  // (the window drags with the right button)
            [window, "keydown", e => {
                const a = document.activeElement;
                if (e.ctrlKey || e.metaKey || e.altKey || (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) || !this.app.state.connected) return;
                const k = e.key.length === 1 ? e.key.toLowerCase() : e.key, c = cam();
                if (k === "q") c.turn(e.repeat ? 6 : 20);
                else if (k === "e") c.turn(e.repeat ? -6 : -20);
                else if (k === "Home") c.resetView();
                else if (k === "o") { this.scene.setMode("all"); this.app.updatePills(); }
                else if (k === "=" || k === "+") c.wheel(e.repeat ? 0.9 : 0.8);
                else if (k === "-") c.wheel(e.repeat ? 1.11 : 1.25);
                else if (k === "[" || k === "]") this.watchRing(k === "[" ? -1 : 1);
                else return;
                this.keepCamera();
            }],
        ];
        for (const [el, ev, fn, opts] of this.listeners) el.addEventListener(ev, fn, opts);
    }

    // a learner's camera kept in their profile, as the window keeps it (fight_camera.settings)
    keepCamera() {
        if (this.app.state.role === "learner" && this.app.keepPrefs) this.app.keepPrefs({camera: this.scene.cam.settings()});
    }

    // [ and ]: watch the next ring (fight_client.watch_ring); the view of every ring goes back to the fight
    watchRing(delta) {
        const rings = ((this.last || {}).rings || []).map(r => r.i);
        if (!rings.length) return;
        const cur = rings.indexOf(this.watched()), next = rings[((cur < 0 ? 0 : cur) + delta + rings.length) % rings.length];
        const r = this.roster, id = this.myId(), mine = r && id !== null ? ((r.fighters || []).find(x => x.id === id) || {}).ring : undefined;
        this.watch = next === mine ? null : next;
        this.scene.setMode(this.scene.mode !== "all" ? this.scene.mode : "fight");
        this.renderBoard();
        if (this.app.toast) this.app.toast(`Watching ring ${next + 1}${next === mine ? "  (yours)" : ""}`);
        this.app.updatePills();
    }

    welcome(m) {
        const p = this.app.params;
        if (p.get("cam")) this.scene.setMode({tv: "fight", chase: "fight", overview: "all"}[p.get("cam")] || p.get("cam"));
        else if ((m.prefs || {}).camera) this.scene.cam.restore(m.prefs.camera);  // (the view kept in their profile)
    }

    myId() {
        const S = this.app.state, r = this.roster;
        const id = r && r.mine ? r.mine[S.name] : null;
        return id === undefined ? null : id;
    }

    // (CHANGE 143) your fighter's ring (fight_client.my_ring): the newest snapshot's, else the roster's; null with none
    myRing() {
        const id = this.myId();
        if (id === null) return null;
        const r = ((this.last || {}).rings || []).find(x => (x.f || []).some(f => f.id === id));
        if (r) return r.i;
        const f = ((this.roster || {}).fighters || []).find(x => x.id === id);
        return f && Number.isInteger(f.ring) ? f.ring : null;
    }

    // the arrows as (forward, side) for your fighter, as fight_client.stick does: the camera decides which way is
    // which, so right always moves right on the screen; forward is towards your opponent
    stick(sx, sy) {
        const id = this.myId(), m = this.last;
        const ring = m ? (m.rings || []).find(r => (r.f || []).some(x => x.id === id)) : null;
        const mine = ring ? ring.f.find(x => x.id === id) : null;
        if (!mine) return [0, 0];
        const other = ring.f.find(x => x.id !== id);
        const cam = this.scene.camera;
        const r = cam.getDirection(BABYLON.Axis.X), a = cam.getDirection(BABYLON.Axis.Z);
        let right = [r.x, r.z], ahead = [a.x, a.z];  // (Babylon's x and z are the game's x and y)
        const norm = v => { const l = Math.hypot(v[0], v[1]); return l < 1e-3 ? null : [v[0] / l, v[1] / l]; };
        right = norm(right); ahead = norm(ahead);
        if (!right || !ahead) return [sy, -sx];
        const want = [right[0] * sx + ahead[0] * sy, right[1] * sx + ahead[1] * sy];
        let face = other ? [other.pos[0] - mine.pos[0], other.pos[1] - mine.pos[1]]
                         : [-Math.sin(mine.h * Math.PI / 180), Math.cos(mine.h * Math.PI / 180)];
        face = norm(face);
        if (!face) return [sy, -sx];
        const left = [-face[1], face[0]];
        const clamp = v => Math.max(-1, Math.min(1, v * 1.4));
        return [clamp(want[0] * face[0] + want[1] * face[1]), clamp(want[0] * left[0] + want[1] * left[1])];
    }

    cycleCamera() {  // V: the window's five views (fight camera, my fighter, over the shoulder, ring view, all rings)
        this.scene.setMode(CAM_MODES[(CAM_MODES.indexOf(this.scene.mode) + 1) % CAM_MODES.length]);
        this.keepCamera();
    }

    learnerTabs() { return [["camera", "Camera"]]; }

    controlSent(msg, now) { this.ahead.control(now / 1000, msg.f, msg.s, msg.hold); }  // (play.js: CHANGE 167)

    message(m) {
        if (m.type === "roster") {
            this.roster = m;
            this.move = new Map((m.fighters || []).filter(x => x.move).map(x => [x.id, x.move]));  // (CHANGE 167)
            this.scene.setSetup({rings: m.rings || [0], rs: m.rs || 4.5, hazards: m.hazards || {}, look: m.look || {}});
            this.scene.setFighters(m.fighters || []);
            this.scene.watchRing = this.watched();
            this.renderBoard();
            return true;
        }
        if (m.type === "state") {
            m.sm = m.sm >>> 0;
            const myId = this.myId();  // (the server's acks: how long our key presses take to show)
            if (myId !== null && m.acks && m.acks[myId] !== undefined && this.app.ctrl) this.app.ctrl.ack(m.acks[myId], performance.now());
            this.app.pushSnap(m, performance.now());
            const mine = myId !== null ? (m.rings || []).find(r => (r.f || []).some(x => x.id === myId)) : null;
            this.ahead.snapshot(m.sm / 1000, mine ? mine.f : [], myId);  // (CHANGE 167)
            this.last = m;
            this.scene.impacts(m.fx || [], m.rings || []);  // (sparks, flashes, dust, debris and the shake: fightfx.js)
            this.impacts = (this.impacts || []).concat(m.fx || []);  // (heard on the next frame: sound.js)
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
        let fighters = [];
        for (const ra of a.rings || []) {
            const rb = bRings.get(ra.i);
            const byId = rb ? new Map((rb.f || []).map(x => [x.id, x])) : new Map();
            for (const x of ra.f || []) {
                const y = byId.get(x.id);
                if (!y) { fighters.push({...x, ri: ra.i}); continue; }
                fighters.push({...y, pos: x.pos.map((v, i) => lerp(v, y.pos[i], f)), h: lerpDeg(x.h, y.h, f),
                               k: x.a === y.a ? lerp(x.k, y.k, Math.min(1, f)) : y.k, ri: ra.i});
            }
        }
        const S = this.app.state, my = this.myId();
        if (S.gfx && S.gfx.ahead && S.offset !== null && my !== null) {  // (CHANGE 167: your footwork drawn at once)
            const ri = (fighters.find(x => x.id === my) || {}).ri;
            if (ri !== undefined) {
                const drawn = new Map(this.ahead.adjust(fighters.filter(x => x.ri === ri), now / 1000, (now - S.offset) / 1000,
                                                        S.rttS ?? (S.pingMs || 0) / 1000, my, this.move.get(my) || null, dt).map(x => [x.id, x]));
                fighters = fighters.map(x => drawn.get(x.id) || x);
            }
        }
        this.scene.watchRing = this.watched();
        this.scene.myId = my;
        this.scene.frame(fighters, (b || a).rings || [], dt, now / 1000);
        // the fight screen (hud.js): the watched ring's two fighters, from the newest snapshot
        const watched = this.watched(), ring = this.last ? (this.last.rings || []).find(r => r.i === watched) : null;
        const names = new Map(((this.roster || {}).fighters || []).map(x => [x.id, {name: (x.design || {}).name || "?", owner: x.owner || ""}]));
        // (CHANGE 143) RING n over the timer when the ring watched isn't yours (fight_client: watched != my_ring)
        this.hud.update(ring, names, this.myId(), ((this.app.state.lesson || {}).rounds_to_win) || 2, dt, now,
                        ring && watched !== this.myRing() ? `RING ${watched + 1}` : "");
        if (this.app.sound && this.last) {  // the hits, the bell, the crowd (sound.js, fight_client's sounds)
            this.app.sound.fightFrame(this.last.rings || [], this.impacts || [], this.watched(),
                {robots: Sound.fightRobots((this.roster || {}).fighters), listener: Sound.listenerFrom(this.scene.camera), now: now / 1000});
            this.impacts = [];
        }
        document.body.classList.toggle("fightscreen", !!ring && this.myId() !== null);
    }

    // (CHANGE 143) the window's rings box (fight_client.hud_dark, top left under the health bars), for the teacher and
    // a player alike: the title (FIGHT LAB, TEACHER: or LEARNER: and the name) with Hide or Show (B), the mode line
    // (PRACTICE or BATTLE, PAUSED, the tournament or its champion), and, full, every ring's fight, the watched ring
    // yellow, your fighter starred. #places is .fightboard (and .small when B has made it small); the fight screen's
    // banner is the HUD's (hud.js), so #race is left empty
    renderBoard() {
        const S = this.app.state, m = this.last, esc = this.app.esc, el = $("places");
        if (!m || !this.roster) return;
        const names = new Map((this.roster.fighters || []).map(x => [x.id, x]));
        const w = this.watched(), myId = this.myId();
        const lines = (m.rings || []).map(r => {
            const fs = (r.f || []).map(x => {
                const info = names.get(x.id) || {design: {}};
                const pc = Math.max(0, Math.round(100 * x.hp / Math.max(1, x.max || 0)));
                return `${x.id === myId ? "*" : ""}${esc(info.design.name || "?")} ${pc}%${x.w ? ` (${x.w})` : ""}${x.ap ? " AUTO" : ""}`;
            }).join("  v  ");
            const tail = r.bn ? r.bn : r.tl === null || r.tl === undefined ? "training" : `round ${r.rd}  ${Math.max(0, Math.floor(r.tl || 0))} s`;
            return `<div data-ring="${r.i}" class="fring ${r.i === w ? "watched" : ""}"><span>Ring ${r.i + 1}${r.lb ? ` - ${esc(r.lb)}` : ""}: ${fs || "empty"}</span><span class="lap">${esc(tail)}</span></div>`;
        });
        const T = S.tournament, teacher = S.role !== "learner";
        const mode = (m.practice ? "PRACTICE (no damage)" : "BATTLE") + (m.paused ? " · PAUSED" : "") +
                     (T ? ` · TOURNAMENT: ${T.champion ? `CHAMPION ${T.champion}` : T.title || ""}` : "");
        const head = `<div class="bhead"><b class="${teacher ? "teacher" : ""}">FIGHT LAB · ${teacher ? "TEACHER" : "LEARNER"}: ${esc(S.name || "")}</b>` +
                     `<button id="fb-small" title="B does the same">${this.boardSmall ? "Show" : "Hide"}</button></div>` +
                     `<div id="fb-mode" class="fmode">${esc(mode)}</div>`;
        el.classList.add("fightboard");
        el.classList.toggle("small", !!this.boardSmall);
        el.innerHTML = head + (this.boardSmall ? "" : `<div class="ftitle"><small>RINGS ([ and ] watch another ring, B hides this)</small></div>` +
                                                     (lines.join("") || "<div class='fring'><small>No rings</small></div>"));
        $("fb-small").onpointerdown = () => this.toggleBoard();  // (not onclick: the box is redrawn 30 times a second)
        el.querySelectorAll("div[data-ring]").forEach(d => d.onpointerdown = () => { this.watch = Number(d.dataset.ring); this.renderBoard(); this.app.updatePills(); });
        $("countdown").textContent = $("phase").textContent = "";
    }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${L.mode === "battle" ? "battle" : "practice"} · ${L.rings ? `${L.rings} rings` : "rings: auto"}` : "";
    }

    cameraPill() {
        return `Camera: ${CAM_NAMES[this.scene.mode] || ""} (V to change)`;
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
            // (CHANGE 143) who is where: each fighter's list (ids that stay the same, CHANGE 142), and where they are
            // now, as the window greys their ring or says "sitting out" (fight_client's Rings rows)
            const where = new Map(((this.roster || {}).fighters || []).map(f => [f.owner, f.ring]));
            const key = s => String(s).replace(/[^A-Za-z0-9]/g, ch => "_" + ch.charCodeAt(0).toString(16));
            const placeHtml = people.map((n, i) => {
                const v = (L.places || {})[n], set = Number.isInteger(v) ? v : null, now = where.get(n === "Teacher" ? S.name : n);
                const at = Number.isInteger(now) ? now : null;
                return `<div class="row"><label>${n === "Teacher" ? "My fighter" : esc(n)}</label><select id="fb-at-${key(n)}" data-place="${i}" data-v="${set ?? ""}"><option value="">any</option>${
                    Array.from({length: Math.max(L.rings, (set ?? -1) + 1)}, (_, k) => `<option value="${k}" ${set === k ? "selected" : ""}>ring ${k + 1}</option>`).join("")}</select>` +
                    (at === null ? `<small class="note sitout">sitting out</small>` : at !== set ? `<small class="note">in ring ${at + 1}</small>` : "") + `</div>`;
            }).join("");
            const rt = Number(L.round_time) || 60;
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The fights</h2>
              <div class="row"><button data-mode="practice" class="${L.mode !== "battle" ? "on" : ""}">Practice</button>
                <button data-mode="battle" class="${L.mode === "battle" ? "on" : ""}">Battle</button>
                <button id="fb-restart" class="go">RESTART</button>
                <button id="fb-pause" class="${this.last && this.last.paused ? "on" : ""}">${this.last && this.last.paused ? "RESUME" : "PAUSE"}</button></div>
              <div class="note">Practice: no damage and no timer. Battle: rounds of ${L.round_time} s, first to ${L.rounds_to_win}. RESTART begins new matches.</div>
              <div class="row"><label>Round time</label><button id="fb-time-down" ${rt <= 20 ? "disabled" : ""}>-10</button><b id="fb-time">${rt} s</b>
                <button id="fb-time-up" ${rt >= 300 ? "disabled" : ""}>+10</button><span class="note">20 to 300 s</span></div>
              <div class="row"><label>Rounds to win</label>${[1, 2, 3].map(k => `<button data-rtw="${k}" class="${k === L.rounds_to_win ? "on" : ""}">${k}</button>`).join("")}</div>
              <div class="row"><label>Sparring partners</label><button id="fb-cpu" class="${L.cpu_opponents ? "on" : ""}">${L.cpu_opponents ? "Computer fighters on" : "Off"}</button>
                <select id="fb-level" data-v="${esc(L.cpu_level || "")}">${levels.map(([k, n]) => `<option value="${k}" ${k === L.cpu_level ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
              <div class="row"><label>The computer plays</label><button data-cf="sparring" class="${L.cpu_fighter === "sparring" ? "on" : ""}">Sparring</button>
                ${Object.keys(R.bosses || {}).map(b => `<button data-cf="${esc(b)}" class="${L.cpu_fighter === b ? "on" : ""}">${esc(b)}</button>`).join("")}</div>
              ${L.cpu_level === "empty" ? `<div class="row"><label class="filebtn">Upload the demo brain (.py)<input id="fb-demo" type="file" accept=".py,text/plain" hidden></label></div>` : ""}
              <div class="row"><label>My fighter</label><button id="fb-mine" class="${L.teacher_fighter ? "on" : ""}">${L.teacher_fighter ? "In the class" : "Not in"}</button></div>
              <div class="row"><label>Designs</label><button id="fb-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              <h2>Rings</h2>
              <div class="row"><button data-rings="0" class="${!L.rings ? "on" : ""}">Auto</button>${[1, 2, 3, 4, 5, 6].map(k => `<button data-rings="${k}" class="${L.rings === k ? "on" : ""}">${k}</button>`).join("")}
                <button id="fb-turns">Take turns again</button></div>
              ${L.rings ? placeHtml + (people.length ? `<div class="note">Any: the rings take turns; a third in a ring sits out.</div>` : "") : `<div class="note">Auto: one ring each, matches share.</div>`}
              ${app.restartRow()}`;
            app.wireMissionRow(body);
            body.querySelectorAll("button[data-mode]").forEach(b => b.onclick = () => lessonSend({mode: b.dataset.mode}));
            $("fb-restart").onclick = () => send({type: "restart"});
            $("fb-pause").onclick = () => send({type: "pause"});
            // (CHANGE 143) -10 and +10 as the window's: any round time from 20 to 300 s (the server holds it there too)
            $("fb-time-down").onclick = () => lessonSend({round_time: Math.max(20, Math.min(300, rt - 10))});
            $("fb-time-up").onclick = () => lessonSend({round_time: Math.max(20, Math.min(300, rt + 10))});
            body.querySelectorAll("button[data-rtw]").forEach(b => b.onclick = () => lessonSend({rounds_to_win: Number(b.dataset.rtw)}));
            $("fb-cpu").onclick = () => lessonSend({cpu_opponents: !L.cpu_opponents});
            body.querySelectorAll("button[data-cf]").forEach(b => b.onclick = () => lessonSend({cpu_fighter: b.dataset.cf}));
            if ($("fb-demo")) $("fb-demo").onchange = async e => { const f = e.target.files[0]; if (f) send({type: "cpu_brain", source: await f.text()}); };
            $("fb-mine").onclick = () => lessonSend({teacher_fighter: !L.teacher_fighter});
            $("fb-lock").onclick = () => lessonSend({designs_locked: !L.designs_locked});
            body.querySelectorAll("button[data-rings]").forEach(b => b.onclick = () => lessonSend({rings: Number(b.dataset.rings)}));
            $("fb-turns").onclick = () => lessonSend({places: Object.fromEntries(people.map(n => [n, null]))});
            body.querySelectorAll("select[data-place]").forEach(sel => sel.onchange = () => {
                sel.dataset.v = sel.value;
                lessonSend({places: {[people[Number(sel.dataset.place)]]: sel.value === "" ? null : Number(sel.value)}});
            });
            $("fb-level").onchange = e => { e.target.dataset.v = e.target.value; lessonSend({cpu_level: e.target.value}); };
            // the panel's redraw puts back what each list held; a list not in use shows the server's own (a ring or a
            // level set elsewhere) once that is done (as robot.js's Arenas rows)
            queueMicrotask(() => body.querySelectorAll("select[data-v]").forEach(el => { if (el.isConnected && el !== document.activeElement) el.value = el.dataset.v; }));
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
              <h2>Tournament (battle switched on, designs locked)</h2>
              ${!T ? `<div class="row"><button id="fm-knock" class="go">Knockout</button><span class="note">computer fighters fill the gaps</span></div>
                   <div class="row"><button id="fm-stays" class="go">Winner stays on</button></div>
                   <div class="note">Two rings live; the loser queues, the next challenger comes in; the rest watch ([ and ]).</div>`
                : T.kind === "stays" ? `<div class="row"><button id="fm-stop" class="stop">Stop: winner stays on</button></div>
                   ${(T.live || []).map(([a, b], i) => `<div>Ring ${i + 1}: ${esc(a || "-")} v ${esc(b || "-")}</div>`).join("")}
                   <div class="note">Waiting: ${(T.queue || []).map(esc).join(", ") || "nobody"}</div>
                   <div class="note">Matches played: ${T.played || 0}</div>
                   ${(T.table || []).length ? `<table>${T.table.slice(0, 12).map(([n, w, st]) => `<tr><td class="${w ? "ok" : ""}">${esc(n)}</td><td class="${w ? "ok" : ""}">${w} win${w !== 1 ? "s" : ""}${st > 1 ? ` · ${st} in a row` : ""}</td></tr>`).join("")}</table>` : ""}`
                : `<div class="row"><button id="fm-stop" class="stop">Stop the tournament</button></div>
                   ${T.champion ? `<p><b>CHAMPION: ${esc(T.champion)}</b></p>` : ""}
                   ${(T.rounds || []).map(rd => `<div style="color: var(--blue)">${rd.length === 1 ? "Final" : rd.length === 2 ? "Semi-finals" : rd.length === 4 ? "Quarter-finals" : "Round 1"}</div>` +
                       rd.map(([a, b, w]) => `<div class="${w ? "ok" : ""}">${esc(a)} v ${esc(b)}${w ? ` -&gt; ${esc(w)}` : " (fighting)"}</div>`).join("")).join("")}`}`;
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
            if ($("fm-stays")) $("fm-stays").onclick = () => send({type: "tournament", start: true, kind: "stays", live: 2});  // (two rings, as the window's)
            if ($("fm-stop")) $("fm-stop").onclick = () => send({type: "tournament", start: false});
            return true;
        }
        if (tab === "camera") {
            const sc = this.scene, rings = (this.roster && this.roster.rings) || [0];
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row">${CAM_MODES.map(k => `<button data-view="${k}" class="${sc.mode === k ? "on" : ""}">${CAM_NAMES[k]}</button>`).join("")}</div>
              <div class="row"><button data-zoom="0.8">Closer</button><button data-zoom="1.25">Further</button><button id="fc-reset">Straight on again</button></div>
              <div class="note">V changes the view. The fight camera keeps both fighters in shot, side on; my fighter and over the shoulder follow your own fighter (or the first in the ring). Drag to swing the view round and tilt it (or Q and E), the wheel or + and − zoom, Home puts it back, O shows every ring, [ and ] watch another ring.</div>
              <h2>Watch a ring</h2>
              <div class="row">${rings.map(k => `<button data-ring="${k}" class="${this.watched() === k ? "on" : ""}">Ring ${k + 1}</button>`).join("")}</div>`;
            body.querySelectorAll("button[data-view]").forEach(b => b.onclick = () => { sc.setMode(b.dataset.view); this.keepCamera(); app.updatePills(); app.renderPanel(); });
            body.querySelectorAll("button[data-zoom]").forEach(b => b.onclick = () => { sc.cam.wheel(Number(b.dataset.zoom)); this.keepCamera(); });
            $("fc-reset").onclick = () => { sc.cam.resetView(); this.keepCamera(); };
            body.querySelectorAll("button[data-ring]").forEach(b => b.onclick = () => {
                this.watch = Number(b.dataset.ring);
                sc.setMode(sc.mode !== "all" ? sc.mode : "fight");
                this.renderBoard(); app.updatePills(); app.renderPanel();
            });
            return true;
        }
        return false;
    }

    dispose() {
        for (const [el, ev, fn, opts] of this.listeners || []) el.removeEventListener(ev, fn, opts);
        this.listeners = [];
        this.scene.dispose();
        $("places").innerHTML = "";
        $("places").classList.remove("fightboard", "small");  // (CHANGE 143: the next game's board is its own)
        document.body.classList.remove("fightscreen");
        $("countdown").textContent = $("phase").textContent = "";
    }
}
