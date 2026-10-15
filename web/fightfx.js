// Fight Lab's effects and camera in Club Coders Live, ported from the app's fight_fx.py, fight_gfx.StageVisual and
// fight_camera.py.
//
// The effects (fight_fx.Effects): sparks (tiny glowing streaks that fly the way they move, with gravity, a bounce off
// the floor and a colour that cools, in each kind of hit's colours), a hit flash (a soft bright blob) and a shock ring
// (a thin ring that grows) facing the camera and drawn over everything, dust when a fighter lands or is thrown, flames
// for fire hits, bits of armour in the victim's colour flying off robots on big hits, and the camera shake. And the
// stage's moving parts (fight_gfx.StageVisual.update): the fire jets' rising puffs and the blasts' glowing balls with
// their flickering halos.
//
// Kept cheap, as the app keeps them: a fixed pool per kind (the app's sizes, the smaller ones on low and blocks), each
// pool one mesh drawn with thin instances (one draw call, robotfx.js's way). The app draws them unlit, added on (or
// added by their soft dot's alpha) or mixed (dust), into simplepbr's buffer before its tone curve. The page's tone
// curve is in each material (pbr.js), so here each effect's own light goes through the same curve (as if over black)
// and is laid on with a screen blend: exact over the dark hall, and over a lit fighter it adds less, as the curve's
// shoulder does in the app. Drawn after the scene without writing depth; the flashes and rings with no depth test.
//
// The camera (fight_camera.FightCamera): the five views, each with its own zoom, swung round and tilted by dragging,
// the moves eased as the app eases them. Plain numbers here (game coordinates, z up), so it can be checked against
// the Python in node; fight.js puts the Babylon camera where it says.

/* global BABYLON */

import {gameQuat} from "./base3d.js";
import {hprQuat} from "./robotfx.js";

const U = (a, b) => a + Math.random() * (b - a);

// spark colours: (start colour, end colour) for each kind of hit
export const SPARKS = {hot: [[1.0, 0.95, 0.6], [1.0, 0.35, 0.05]], blue: [[0.8, 0.95, 1.0], [0.2, 0.45, 1.0]],
                       white: [[1.0, 1.0, 1.0], [0.7, 0.7, 0.8]], gold: [[1.0, 1.0, 0.6], [1.0, 0.6, 0.0]]};
// kind: [sparks, spark colour, flash colour, flash size, ring?]
export const KINDS = {
    punch: [10, "hot", [1.0, 0.95, 0.85], 0.5, false],
    kick: [14, "hot", [1.0, 0.9, 0.75], 0.65, true],
    low: [12, "hot", [1.0, 0.9, 0.75], 0.55, false],
    high: [18, "hot", [1.0, 0.9, 0.7], 0.8, true],
    special: [30, "blue", [0.6, 0.85, 1.0], 1.1, true],
    counter: [36, "gold", [1.0, 0.85, 0.2], 1.3, true],
    block: [8, "blue", [0.6, 0.8, 1.0], 0.55, false],
    throw: [6, "white", [1.0, 1.0, 1.0], 0.6, true],
    zap: [30, "blue", [0.4, 0.7, 1.0], 0.9, false],
    fire: [8, "hot", [1.0, 0.5, 0.1], 0.8, false],
    wall: [10, "white", [1.0, 1.0, 1.0], 0.6, false],
    spikes: [16, "white", [1.0, 0.4, 0.3], 0.8, true],
    land: [0, "white", null, 0.0, false],
    ringout: [0, "white", [1.0, 0.6, 0.2], 1.0, true],
};

// how many of each the pools hold (fight_fx.Effects: 360 sparks, 40 flashes (half of them rings), 80 puffs, 140 flames
// and at most 30 bits of debris; 120, 24, 30 and 50 on the low tiers, which the app also uses on basic)
const POOLS = {low: {sparks: 120, flashes: 24, puffs: 30, flames: 50}, full: {sparks: 360, flashes: 40, puffs: 80, flames: 140}};
const DEBRIS = 30;
const JET_PUFFS = 14, SHOTS = 12;  // (fight_gfx.StageVisual: 14 puffs up each jet, 12 blasts at once)

// ---------- the particles' shader: a colour per instance, a soft dot or a thin ring, the app's tone curve ----------
BABYLON.Effect.ShadersStore.ccfightfxVertexShader = `
precision highp float;
attribute vec3 position;
attribute vec2 uv;
#include<instancesDeclaration>
uniform mat4 viewProjection;
varying vec2 vUV;
varying vec4 vColor;
void main(void) {
#include<instancesVertex>
    gl_Position = viewProjection * finalWorld * vec4(position, 1.0);
    vUV = uv;
#ifdef INSTANCESCOLOR
    vColor = instanceColor;
#else
    vColor = vec4(1.0);
#endif
}`;
BABYLON.Effect.ShadersStore.ccfightfxFragmentShader = `
precision highp float;
uniform vec4 baseColor;
uniform float exposure;
varying vec2 vUV;
varying vec4 vColor;
vec3 tone(vec3 c) {  // simplepbr's post pass: exposure, then the Hejl-Burgess filmic curve (pbr.js's)
    c = max(vec3(0.0), c * exposure - vec3(0.004));
    return (c * (vec3(6.2) * c + vec3(0.5))) / (c * (vec3(6.2) * c + vec3(1.7)) + vec3(0.06));
}
void main(void) {
    vec4 c = vColor * baseColor;
    float a = c.a;
    float d = length(vUV - vec2(0.5)) * 2.0;
#ifdef SOFT
    a *= pow(max(0.0, 1.0 - d), 1.8);  // (fight_fx.soft_dot_texture)
#endif
#ifdef RING
    a *= pow(max(0.0, 1.0 - abs(d - 0.8) / 0.15), 1.5);  // (fight_fx.ring_texture: the shock wave of a big hit)
#endif
#ifdef ADDED
    // added on (by the alpha, for the soft ones): the light this adds, through the tone curve as if over black,
    // laid on with a screen blend
    vec3 color = c.rgb * a;
    if (exposure > 0.0) color = tone(color);
    gl_FragColor = vec4(color, 1.0);
#else
    // mixed over the scene (dust): the app mixes it before its tone curve, where a dark floor is on the curve's steep
    // part, so a faint puff shows more than its alpha says: as much as its colour times its alpha shows over black
    vec3 color = c.rgb;
    if (exposure > 0.0) {
        color = tone(color);
        float full = dot(color, vec3(1.0));
        if (full > 0.0) a = clamp(dot(tone(c.rgb * a), vec3(1.0)) / full, 0.0, 1.0);
    }
    gl_FragColor = vec4(color, a);
#endif
}`;

// a pool of particles drawn as one mesh's thin instances (robotfx.js's Cloud, with this shader)
class Pool {
    // kind: "add" (added on), "mix" (mixed over); shape: "", "SOFT" or "RING"; group 1 keeps the scene's depth (walls
    // hide them), group 2 has it cleared (always on top)
    constructor(scene, name, mesh, cap, kind, shape, order, exposure, group = 1) {
        const C = BABYLON.Constants;
        const m = new BABYLON.ShaderMaterial("ccfightfx" + name, scene, {vertex: "ccfightfx", fragment: "ccfightfx"}, {
            attributes: ["position", "uv"], uniforms: ["world", "viewProjection", "baseColor", "exposure"],
            defines: [shape, kind === "add" ? "ADDED" : ""].filter(Boolean), needAlphaBlending: true});
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));  // (white, alpha 1: as every material here has one)
        m.setFloat("exposure", exposure);
        m.alphaMode = kind === "add" ? (exposure > 0 ? C.ALPHA_SCREENMODE : C.ALPHA_ONEONE) : C.ALPHA_COMBINE;
        m.disableDepthWrite = true;
        // the solid ones (a spark's box, a blast's ball) show their front faces only, as the app's do: each pixel is
        // added once; the flat puffs always face the camera
        m.backFaceCulling = !shape;
        mesh.material = m;
        mesh.isPickable = false;
        mesh.alwaysSelectAsActiveMesh = true;  // (the instances move: no bounds kept)
        mesh.doNotSyncBoundingInfo = true;
        mesh.renderingGroupId = group;
        mesh.alphaIndex = order;  // (the app's bins: dust 20, blasts 22, jets 24, fire 25, sparks 30, flashes 32)
        this.mats = new Float32Array(16 * cap);
        this.cols = new Float32Array(4 * cap);
        mesh.thinInstanceSetBuffer("matrix", this.mats, 16, false);
        mesh.thinInstanceSetBuffer("color", this.cols, 4, false);
        mesh.thinInstanceCount = 0;
        mesh.isVisible = false;
        this.mesh = mesh;
        this.cap = cap;
        this.items = Array.from({length: cap}, () => ({p: [0, 0, 0], v: [0, 0, 0], life: 0, max: 1, rgb: [1, 1, 1], col: "hot", size: 1}));
        this.n = 0;
    }

    free() {  // (fight_fx._free: the first that isn't in use, or none)
        for (const it of this.items) if (it.life <= 0) return it;
        return null;
    }

    // one instance: its game position and Babylon axes (each scaled), its colour
    put(p, ax, ay, az, sx, sy, sz, r, g, b, a) {
        if (this.n >= this.cap) return;
        const o = this.n * 16, M = this.mats;
        M[o] = ax[0] * sx; M[o + 1] = ax[1] * sx; M[o + 2] = ax[2] * sx; M[o + 3] = 0;
        M[o + 4] = ay[0] * sy; M[o + 5] = ay[1] * sy; M[o + 6] = ay[2] * sy; M[o + 7] = 0;
        M[o + 8] = az[0] * sz; M[o + 9] = az[1] * sz; M[o + 10] = az[2] * sz; M[o + 11] = 0;
        M[o + 12] = p[0]; M[o + 13] = p[2]; M[o + 14] = p[1]; M[o + 15] = 1;
        const c = this.n * 4, C = this.cols;
        C[c] = r; C[c + 1] = g; C[c + 2] = b; C[c + 3] = a;
        this.n++;
    }

    flush() {
        const mesh = this.mesh;
        mesh.thinInstanceCount = this.n;
        mesh.isVisible = this.n > 0;
        if (this.n) {
            mesh.thinInstanceBufferUpdated("matrix");
            mesh.thinInstanceBufferUpdated("color");
        }
        this.n = 0;
    }
}

const X = [1, 0, 0], Y = [0, 1, 0], Z = [0, 0, 1];  // (Babylon's axes: unturned)

export class FightFX {
    // sc: the FightScene (its Babylon scene, tier, materials and camera)
    constructor(sc) {
        this.sc = sc;
        const scene = sc.scene, size = ["blocks", "low"].includes(sc.tier) ? POOLS.low : POOLS.full;
        // (the app's tone curve at its exposure on every tier: its basic tier has it too, as a pass after the scene)
        const exposure = sc.lighting ? sc.lighting.exposure : Math.pow(2, ((sc.look || {}).pbr || {}).exposure || 0.8);
        scene.setRenderingAutoClearDepthStencil(1, false, false, false);
        // sparks: tiny glowing streaks, 2.4 cm across and 16 long (along Babylon's z: the way they fly), added on
        const streak = BABYLON.MeshBuilder.CreateBox("ffxspark", {width: 0.024, height: 0.024, depth: 0.16}, scene);
        this.sparks = new Pool(scene, "spark", streak, size.sparks, "add", "", 30, exposure);
        // flashes (a bright blob) and shock rings: half the pool each, added by their alpha, always on top
        const half = size.flashes / 2;
        this.dots = new Pool(scene, "flash", BABYLON.MeshBuilder.CreatePlane("ffxflash", {size: 1}, scene), half, "add", "SOFT", 32, exposure, 2);
        this.rings = new Pool(scene, "ring", BABYLON.MeshBuilder.CreatePlane("ffxring", {size: 1}, scene), half, "add", "RING", 33, exposure, 2);
        // dust (and smoke): soft grey puffs mixed over the scene; flames: soft puffs added by their alpha
        this.puffs = new Pool(scene, "dust", BABYLON.MeshBuilder.CreatePlane("ffxpuff", {size: 1}, scene), size.puffs, "mix", "SOFT", 20, exposure);
        this.flames = new Pool(scene, "fire", BABYLON.MeshBuilder.CreatePlane("ffxfire", {size: 1}, scene), size.flames, "add", "SOFT", 25, exposure);
        // the stage's moving parts: the fire jets' puffs (14 for each jet of each ring), the blasts' balls and halos
        this.jetCap = JET_PUFFS * 4 * 6;
        this.jets = new Pool(scene, "jet", BABYLON.MeshBuilder.CreatePlane("ffxjet", {size: 1}, scene), this.jetCap, "add", "SOFT", 24, exposure);
        const ball = BABYLON.MeshBuilder.CreateSphere("ffxshot", {diameter: 2, segments: 8}, scene);
        this.balls = new Pool(scene, "shot", ball, SHOTS, "add", "", 22, exposure);
        const halo = BABYLON.MeshBuilder.CreateSphere("ffxhalo", {diameter: 2, segments: 8}, scene);
        this.halos = new Pool(scene, "halo", halo, SHOTS, "add", "", 22, exposure);
        // debris: little chunks of armour, lit, in the victim's paint: one mesh of thin instances for each colour (made
        // when first needed), at most 30 chunks in all
        this.debris = [];
        this.debrisMeshes = new Map();
        this.tmpM = new BABYLON.Matrix();
        this.tmpS = new BABYLON.Vector3();
        this.tmpP = new BABYLON.Vector3();
        this.shake = 0;
    }

    // ---------- things that happen ----------
    // where a hit (or a block, a zap, a fall...) happened; colour: the victim's; robot: whether the victim is a robot
    impact(pos, damage, kind, colour = [0.7, 0.7, 0.7], robot = true) {
        const [sparks, sparkCol, flashCol, flashSize, shock] = KINDS[kind] || KINDS.punch;
        const n = robot || ["zap", "counter", "special", "fire"].includes(kind)
            ? Math.floor(sparks * (0.6 + Math.min(1.5, damage / 12))) : Math.floor(sparks * 0.3);
        for (let i = 0; i < n; i++) {
            const s = this.sparks.free();
            if (!s) break;
            s.p[0] = pos[0]; s.p[1] = pos[1]; s.p[2] = pos[2];
            const vx = U(-1, 1), vy = U(-1, 1), vz = U(-0.3, 1.2);
            const sp = U(2.5, kind !== "zap" ? 8 : 5) / (Math.hypot(vx, vy, vz) || 1);
            s.v[0] = vx * sp; s.v[1] = vy * sp; s.v[2] = vz * sp;
            s.life = s.max = U(0.15, 0.45);
            s.col = sparkCol;
        }
        if (flashCol) {
            const size = flashSize * (0.8 + Math.min(1.0, damage / 15) * 0.6);
            this.flash(pos, flashCol, size, false, 0.12);
            if (shock || damage >= 12) this.flash(pos, flashCol, size * 1.3, true, 0.22);
        }
        if (kind === "fire") for (let i = 0; i < 10; i++) this.flame(pos, [0, 0, 1], 1);
        if (kind === "land" || kind === "ringout" || kind === "throw") this.dust(pos, kind === "land" ? 6 : 10);
        if (robot && damage > 12 && ["kick", "high", "special", "counter"].includes(kind)) {
            for (let i = 0; i < Math.floor(Math.min(4, damage / 6)); i++) this.spawnDebris(pos, colour);
        }
        this.shake = Math.max(this.shake, Math.min(0.3, damage / (kind !== "block" && kind !== "land" ? 90 : 250)));
    }

    flash(pos, colour, size, ring = false, life = 0.12) {
        const f = (ring ? this.rings : this.dots).free();
        if (!f) return;
        f.p[0] = pos[0]; f.p[1] = pos[1]; f.p[2] = pos[2];
        f.life = f.max = life;
        f.size = size;
        f.rgb = colour;
    }

    dust(pos, amount = 6) {
        for (let i = 0; i < amount; i++) {
            const p = this.puffs.free();
            if (!p) return;
            p.p[0] = pos[0] + U(-0.3, 0.3); p.p[1] = pos[1] + U(-0.3, 0.3); p.p[2] = Math.max(0.05, pos[2]);
            p.v[0] = U(-1.2, 1.2); p.v[1] = U(-1.2, 1.2); p.v[2] = U(0.2, 0.6);
            p.life = p.max = U(0.5, 0.9);
            const shade = U(0.5, 0.7);
            p.rgb = [shade, shade, shade * 1.05];
        }
    }

    flame(pos, d, amount = 3) {
        for (let i = 0; i < amount; i++) {
            const f = this.flames.free();
            if (!f) return;
            f.p[0] = pos[0] + U(-0.2, 0.2); f.p[1] = pos[1] + U(-0.2, 0.2); f.p[2] = pos[2];
            const k = U(2.0, 4.0);
            f.v[0] = d[0] * k + U(-0.6, 0.6); f.v[1] = d[1] * k + U(-0.6, 0.6); f.v[2] = d[2] * k + 0.5;
            f.life = f.max = U(0.3, 0.5);
        }
    }

    // (fight_fx.smoke: for a knocked-out robot, amount 0..1, each frame; the window doesn't call it at present)
    smoke(pos, amount) {
        if (Math.random() > amount * 0.4) return;
        const p = this.puffs.free();
        if (!p) return;
        p.p[0] = pos[0] + U(-0.2, 0.2); p.p[1] = pos[1] + U(-0.2, 0.2); p.p[2] = pos[2] + 0.2;
        p.v[0] = U(-0.2, 0.2); p.v[1] = U(-0.2, 0.2); p.v[2] = U(0.6, 1.2);
        p.life = p.max = U(1.2, 2.0);
        const shade = U(0.15, 0.3);
        p.rgb = [shade, shade, shade];
    }

    debrisMesh(colour) {
        const key = colour.map(c => c.toFixed(3)).join(",");
        let d = this.debrisMeshes.get(key);
        if (!d) {
            const m = BABYLON.MeshBuilder.CreateBox("ffxdebris", {size: 1}, this.sc.scene);
            // (fight_gfx.part's defaults: the paint texture set, rough 1, metal 1)
            m.material = this.sc.material("debris", colour, 1, 1, 0, {tex: this.sc.tier === "blocks" ? "" : "paint"});
            m.isPickable = false;
            m.alwaysSelectAsActiveMesh = true;
            m.doNotSyncBoundingInfo = true;
            d = {mesh: m, mats: new Float32Array(16 * DEBRIS), n: 0};
            m.thinInstanceSetBuffer("matrix", d.mats, 16, false);
            m.thinInstanceCount = 0;
            m.isVisible = false;
            this.debrisMeshes.set(key, d);
        }
        return d;
    }

    spawnDebris(pos, colour) {
        const hx = U(0.02, 0.05), hy = U(0.02, 0.05);
        this.debris.push({mesh: this.debrisMesh(colour), p: pos.slice(), v: [U(-3, 3), U(-3, 3), U(2, 5)], life: 3.0,
                          hpr: [0, 0, 0], spin: [U(-700, 700), U(-700, 700), 0], size: [hx, hy, 0.01]});
        if (this.debris.length > DEBRIS) this.debris.shift();  // (the oldest goes)
    }

    // ---------- the stage's moving parts, each frame (fight_gfx.StageVisual.update) ----------
    // a fire jet's puffs rising from its nozzle at (x, y): power 0..1, t the stage's clock
    jet(x, y, power, t) {
        const height = 0.4 + 1.5 * power, big = 0.6 + 0.6 * power;
        for (let k = 0; k < JET_PUFFS; k++) {
            const f = ((k / JET_PUFFS + t * 2.2) % 1 + 1) % 1;  // 0 at the nozzle, 1 at the top
            const wob = Math.sin(t * 23 + k * 2.1) * 0.08;
            this.jetAt[0] = x + wob; this.jetAt[1] = y + Math.cos(t * 19 + k) * 0.08; this.jetAt[2] = 0.03 + f * height;
            const s = (0.8 - 0.45 * f) * big;
            this.jets.put(this.jetAt, this.R, this.Up, this.F, s, s, s, 1.0, 0.8 - 0.6 * f, 0.3 - 0.27 * f, 1 - f * 0.8);
        }
    }

    // a blast in flight: a glowing ball and its flickering halo
    shot(pos, t) {
        this.balls.put(pos, X, Y, Z, 0.2, 0.2, 0.2, 0.4, 0.9, 1.6, 1);
        const h = 0.34 * (1 + 0.25 * Math.sin(t * 40));
        this.halos.put(pos, X, Y, Z, h, h, h, 0.08, 0.25, 0.5, 1);
    }

    // call before jet() and shot() each frame: the camera's axes for the puffs that face it
    begin() {
        const cam = this.sc.camera;
        const right = cam.getDirection(BABYLON.Axis.X), up = cam.getDirection(BABYLON.Axis.Y), fwd = cam.getDirection(BABYLON.Axis.Z);
        this.R = [right.x, right.y, right.z]; this.Up = [up.x, up.y, up.z]; this.F = [fwd.x, fwd.y, fwd.z];
        this.jetAt = [0, 0, 0];
    }

    // ---------- every frame ----------
    update(dt) {
        if (!this.R) this.begin();
        const R = this.R, Up = this.Up, F = this.F;
        const g = 9.81 * dt;
        const S = this.sparks;
        for (const s of S.items) {
            if (s.life <= 0) continue;
            s.life -= dt;
            if (s.life <= 0) continue;
            s.v[2] -= g * 0.6;
            s.p[0] += s.v[0] * dt; s.p[1] += s.v[1] * dt; s.p[2] += s.v[2] * dt;
            const f = s.life / s.max;
            const [a, b] = SPARKS[s.col] || SPARKS.hot;
            // pointing the way it flies (Babylon axes: the game's y and z swapped)
            const l = Math.hypot(s.v[0], s.v[1], s.v[2]) || 1;
            const az = [s.v[0] / l, s.v[2] / l, s.v[1] / l];
            let ax = Math.abs(az[1]) < 0.95 ? [az[2], 0, -az[0]] : [0, -az[2], az[1]];
            const la = Math.hypot(ax[0], ax[1], ax[2]) || 1;
            ax = [ax[0] / la, ax[1] / la, ax[2] / la];
            const ay = [az[1] * ax[2] - az[2] * ax[1], az[2] * ax[0] - az[0] * ax[2], az[0] * ax[1] - az[1] * ax[0]];
            S.put(s.p, ax, ay, az, 1, 1, 0.5 + f, b[0] + (a[0] - b[0]) * f, b[1] + (a[1] - b[1]) * f, b[2] + (a[2] - b[2]) * f, 1);
            if (s.p[2] < 0.01 && s.v[2] < 0) {  // bounce off the floor
                s.v[0] *= 0.6; s.v[1] *= 0.6; s.v[2] *= -0.35;
            }
        }
        S.flush();
        for (const [P, ring] of [[this.dots, false], [this.rings, true]]) {
            for (const fl of P.items) {
                if (fl.life <= 0) continue;
                fl.life -= dt;
                if (fl.life <= 0) continue;
                const t = 1 - fl.life / fl.max;  // 0 at the start, 1 at the end
                const s = fl.size * (ring ? 0.4 + 1.0 * t : 1.0 + 0.5 * t);
                P.put(fl.p, R, Up, F, s, s, s, fl.rgb[0], fl.rgb[1], fl.rgb[2], 1 - t);
            }
            P.flush();
        }
        const P = this.puffs;
        for (const p of P.items) {
            if (p.life <= 0) continue;
            p.life -= dt;
            if (p.life <= 0) continue;
            const f = 1 - p.life / p.max, slow = Math.max(0, 1 - dt * 2);
            p.v[0] *= slow; p.v[1] *= slow; p.v[2] *= slow;
            p.p[0] += p.v[0] * dt; p.p[1] += p.v[1] * dt; p.p[2] += p.v[2] * dt;
            const s = 0.3 + f * 1.2;
            P.put(p.p, R, Up, F, s, s, s, p.rgb[0], p.rgb[1], p.rgb[2], 0.5 * (1 - f));
        }
        P.flush();
        const L = this.flames;
        for (const fl of L.items) {
            if (fl.life <= 0) continue;
            fl.life -= dt;
            if (fl.life <= 0) continue;
            const f = fl.life / fl.max, slow = Math.max(0, 1 - dt * 2.5);  // flames slow down and rise
            fl.v[0] *= slow; fl.v[1] *= slow; fl.v[2] = fl.v[2] * slow + dt * 3.0;
            fl.p[0] += fl.v[0] * dt; fl.p[1] += fl.v[1] * dt; fl.p[2] += fl.v[2] * dt;
            const s = 0.25 + 0.6 * (1 - f);
            L.put(fl.p, R, Up, F, s, s, s, 1.0 * f + 0.2, (0.35 + 0.4 * f * f) * f, 0.08 * f * f, 1);
        }
        L.flush();
        // (the stage's: put this frame by jet() and shot())
        this.jets.flush();
        this.balls.flush();
        this.halos.flush();
        for (const d of this.debris) {
            if (d.life <= 0) continue;
            d.life -= dt;
            d.v[2] -= g;
            const p = d.p;
            p[0] += d.v[0] * dt; p[1] += d.v[1] * dt; p[2] += d.v[2] * dt;
            if (p[2] < 0.02) {
                p[2] = 0.02;
                d.v = [d.v[0] * 0.5, d.v[1] * 0.5, -d.v[2] * 0.3];
                d.spin = d.spin.map(v => v * 0.5);
            }
            for (let i = 0; i < 3; i++) d.hpr[i] += d.spin[i] * dt;
        }
        this.debris = this.debris.filter(d => d.life > 0);
        for (const m of this.debrisMeshes.values()) m.n = 0;
        for (const d of this.debris) {
            const p = d.p;
            this.tmpS.set(2 * d.size[0], 2 * d.size[2], 2 * d.size[1]);
            this.tmpP.set(p[0], p[2], p[1]);
            BABYLON.Matrix.ComposeToRef(this.tmpS, gameQuat(hprQuat(...d.hpr)), this.tmpP, this.tmpM);
            this.tmpM.copyToArray(d.mesh.mats, d.mesh.n * 16);
            d.mesh.n++;
        }
        for (const m of this.debrisMeshes.values()) {
            m.mesh.thinInstanceCount = m.n;
            m.mesh.isVisible = m.n > 0;
            if (m.n) m.mesh.thinInstanceBufferUpdated("matrix");
        }
        this.shake = Math.max(0, this.shake - dt * 1.2);
        this.R = null;
    }

    // where the camera is pushed this frame (game metres): fight_fx.shake_offset, of which the window uses half
    shakeOffset() {
        const s = this.shake;
        if (s <= 0) return null;
        return [U(-s, s) * 0.5, U(-s, s) * 0.5, U(-s, s) * 0.25];
    }
}

// ---------- the camera (fight_camera.FightCamera) ----------
export const CAM_MODES = ["fight", "me", "shoulder", "ring", "all"];
export const CAM_NAMES = {fight: "Fight camera", me: "My fighter", shoulder: "Over the shoulder", ring: "Ring view", all: "All rings"};

const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const mul = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const len = a => Math.hypot(a[0], a[1], a[2]);
const norm = a => { const l = len(a); return l > 0 ? mul(a, 1 / l) : a; };
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const wrap360 = v => ((v % 360) + 360) % 360;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export class FightCamera {
    constructor(mode = "fight") {
        this.mode = CAM_MODES.includes(mode) ? mode : "fight";
        this.pos = this.look = null;
        this.fov = 50.0;
        this.zoom = Object.fromEntries(CAM_MODES.map(m => [m, 1.0]));  // 0.4 (close) to 2.5 (far) for each view
        this.side = null;                   // the fight camera's side of the fighters: a direction on the floor
        this.orbit = 0.0;                   // your own view: degrees swung round,
        this.tilt = 0.0;                    // and tilted up (or down)
        this.shift = 0.0;                   // (a panel over the right of the screen: the window's; 0 here)
        this.lastMode = this.mode;          // the view actually used last (fight when yours has no fighter to follow)
    }

    get name() { return CAM_NAMES[this.mode]; }

    turn(degrees) { this.orbit = wrap360(this.orbit + degrees); }

    resetView() { this.orbit = 0.0; this.tilt = 0.0; }

    // a drag across the picture: dx, dy as shares of its width and height (right and down positive)
    drag(dx, dy) {
        // (the window: mouse x and y from -1 to 1, y up; 150 degrees round and 60 up for the whole width and height)
        this.orbit = wrap360(this.orbit - dx * 2 * 150);
        this.tilt = clamp(this.tilt + dy * 2 * 60, -12.0, 55.0);
    }

    // an offset from what the camera looks at, swung round by orbit and tilted up by tilt (degrees)
    swing(o) {
        const a = this.orbit * Math.PI / 180, t = this.tilt * Math.PI / 180;
        const x = o[0] * Math.cos(a) - o[1] * Math.sin(a), y = o[0] * Math.sin(a) + o[1] * Math.cos(a);
        const across = Math.hypot(x, y);
        if (across < 1e-6) return o.slice();
        const keep = Math.cos(t);  // tilting up: less across, more height
        return [x * keep, y * keep, o[2] + across * Math.sin(t)];
    }

    cycle() { this.setMode(CAM_MODES[(CAM_MODES.indexOf(this.mode) + 1) % CAM_MODES.length]); }

    setMode(mode) {
        if (CAM_MODES.includes(mode)) {
            this.mode = mode;
            this.pos = null;  // cut straight to the new view
        }
    }

    wheel(factor) { this.zoom[this.mode] = clamp(this.zoom[this.mode] * factor, 0.4, 2.5); }

    settings() {
        return {mode: this.mode, zoom: Object.fromEntries(CAM_MODES.map(m => [m, Math.round(this.zoom[m] * 100) / 100])),
                orbit: Math.round(this.orbit * 10) / 10, tilt: Math.round(this.tilt * 10) / 10};
    }

    // put back a view and zoom levels saved earlier (a learner's profile: the window's own camera settings)
    restore(saved) {
        if (!saved || typeof saved !== "object") return;
        if (CAM_MODES.includes(saved.mode)) this.setMode(saved.mode);
        for (const [m, z] of Object.entries(saved.zoom || {})) if (CAM_MODES.includes(m) && Number.isFinite(Number(z))) this.zoom[m] = clamp(Number(z), 0.4, 2.5);
        if (Number.isFinite(Number(saved.orbit))) this.orbit = wrap360(Number(saved.orbit));
        if (Number.isFinite(Number(saved.tilt))) this.tilt = clamp(Number(saved.tilt), -12.0, 55.0);
    }

    // me, enemy: the feet of your fighter (or the first in the ring) and the other one, [x, y, z] or null; centre: the
    // watched ring's [x, y]; centres: every ring's. Returns {pos, look, fov (degrees across), mode (the one used)}
    update(dt, me = null, enemy = null, centre = [0, 0], centres = []) {
        const C = [centre[0], centre[1], 0];
        let mode = this.mode;
        if ((mode === "shoulder" && (!me || !enemy)) || (mode === "me" && !me)) mode = "fight";
        let want, look, k = 4.0, fov = 45.0;
        if (mode === "fight") {
            let a = me || enemy;
            const b = me && enemy ? enemy : null;
            if (!a) a = C;
            const mid = b ? mul(add(a, b), 0.5) : a.slice();
            let line = b ? sub(b, a) : [1, 0, 0];
            line[2] = 0;
            if (len(line) < 0.05) line = [1, 0, 0];
            line = norm(line);
            let side = [-line[1], line[0], 0];  // at right angles to the line between them
            // first time: stand on the side where you (me) are on the left of the screen
            if (this.side === null) this.side = me && b ? mul(side, -1) : [0, -1, 0];
            if (dot(side, this.side) < 0) side = mul(side, -1);  // stay on the same side as before
            this.side = norm(add(this.side, mul(sub(side, this.side), Math.min(1.0, dt * 6))));
            const gap = b ? len(sub(b, a)) : 0.0;
            const dist = (4.3 + gap * 0.8) * this.zoom.fight * (1 + this.shift * 2);
            want = add([mid[0], mid[1], 0], this.swing(add(mul(this.side, dist), [0, 0, 1.3 + dist * 0.1])));
            want[2] += Math.max(a[2], 0) * 0.5;
            look = [mid[0], mid[1], 1.0 + Math.max(a[2], 0) * 0.5];
            k = 5.0; fov = 50.0;
        } else if (mode === "me") {
            let to = enemy ? sub(enemy, me) : [0, 1, 0];
            to[2] = 0;
            if (len(to) < 0.05) to = [0, 1, 0];
            to = norm(to);
            let right = [to[1], -to[0], 0];
            if (this.side === null) this.side = right.slice();
            if (dot(right, this.side) < 0) right = mul(right, -1);  // (stay on the same side as the fighters circle)
            this.side = norm(add(this.side, mul(sub(right, this.side), Math.min(1.0, dt * 6))));
            const z = this.zoom.me;
            // in front of you and well to the side (so the other fighter doesn't get in the way), a little above
            want = add([me[0], me[1], 0], this.swing(add(mul(add(mul(to, 0.45), mul(this.side, 0.9)), 3.4 * z), [0, 0, 1.5])));
            want[2] += Math.max(me[2], 0);
            look = [me[0], me[1], 1.0 + Math.max(me[2], 0)];
            k = 6.0; fov = 50.0;
        } else if (mode === "shoulder") {
            let to = sub(enemy, me);
            to[2] = 0;
            if (len(to) < 0.05) to = [0, 1, 0];
            to = norm(to);
            const right = [to[1], -to[0], 0];
            const z = this.zoom.shoulder;
            want = add([me[0], me[1], 0], this.swing(add(add(mul(to, -3.2 * z), mul(right, 0.9)), [0, 0, 2.2 + 0.4 * z])));
            look = [enemy[0], enemy[1], 0.8];
            k = 6.0; fov = 60.0;
        } else if (mode === "ring") {
            const z = this.zoom.ring;
            want = add(C, this.swing([0, -9.5 * z, 7.5 * z]));
            look = add(C, [0, 0.5, 0.4]);
            k = 3.0; fov = 50.0;
        } else {
            const pts = centres.length ? centres : [centre];
            const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
            const mid = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2, 0];
            const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) + 10;
            const z = this.zoom.all;
            want = add(mid, this.swing([0, -span * 0.75 * z, span * 0.75 * z]));
            look = add(mid, [0, 1, 0]);
            k = 2.5; fov = 55.0;
        }
        if (this.pos === null) { this.pos = want.slice(); this.look = look.slice(); this.fov = fov; }
        const a = Math.min(1.0, dt * k);
        this.pos = add(this.pos, mul(sub(want, this.pos), a));
        this.look = add(this.look, mul(sub(look, this.look), a));
        this.fov += (fov - this.fov) * Math.min(1.0, dt * 4);
        this.lastMode = mode;
        return {pos: this.pos, look: this.look, fov: this.fov, mode};
    }
}
