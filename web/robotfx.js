// Robot Lab's effects in Club Coders Live, ported from the app's rw_fx.py: sparks (glowing streaks
// with gravity, a bounce off the floor and a colour that cools), the saws' and chainsaws' spark showers, the flame
// thrower's jet of fire with dark smoke at its end, chunks of armour in the victim's colour on big hits, smoke from
// damaged robots (and fire over 70% damage), and the camera shake. Also rw_gfx.HitBar (the bar over a part just
// hit) and the game-quaternion helpers the real damage needs (Panda's HPR, exactly as Panda composes it).
//
// Kept cheap, as the app keeps them: a fixed pool per kind, each pool one mesh drawn with thin instances (one draw
// call), sized per tier. Particles are unlit and blended over the scene as the app blends them (sparks added on,
// fire added by its soft dot's alpha, smoke mixed), with the app's tone curve on the lit tiers (simplepbr's post
// pass, which the app's effects go through), and drawn after everything else without writing depth.

/* global BABYLON */

import {v3, gameQuat} from "./base3d.js";

// ---------- game quaternions [w, x, y, z] (Panda's, z up, right handed) ----------
export function qmul(a, b) {  // a then b in Hamilton's order: rotate by b first, then a
    const [w1, x1, y1, z1] = a, [w2, x2, y2, z2] = b;
    return [w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2];
}

export function qrot(q, v) {  // a vector turned by q
    const [w, x, y, z] = q, [vx, vy, vz] = v;
    const tx = 2 * (y * vz - z * vy), ty = 2 * (z * vx - x * vz), tz = 2 * (x * vy - y * vx);
    return [vx + w * tx + y * tz - z * ty, vy + w * ty + z * tx - x * tz, vz + w * tz + x * ty - y * tx];
}

// Panda's setHpr: heading about z, pitch about x, roll about y (degrees), the roll done first
export function hprQuat(h, p, r) {
    const d = Math.PI / 360;
    return qmul(qmul([Math.cos(h * d), 0, 0, Math.sin(h * d)], [Math.cos(p * d), Math.sin(p * d), 0, 0]),
                [Math.cos(r * d), 0, Math.sin(r * d), 0]);
}

// Panda's getHpr of a quaternion (degrees)
export function quatHpr(q) {
    const f = qrot(q, [0, 1, 0]), rt = qrot(q, [1, 0, 0]);
    const p = Math.asin(Math.max(-1, Math.min(1, f[2])));
    const h = Math.atan2(-f[0], f[1]);
    const ch = Math.cos(h), sh = Math.sin(h);
    const rx = rt[0] * ch + rt[1] * sh;  // (the right vector with the heading taken off)
    const r = Math.atan2(-rt[2] / Math.max(1e-6, Math.cos(p)), rx);
    return [h * 180 / Math.PI, p * 180 / Math.PI, r * 180 / Math.PI];
}

// a Babylon quaternion back to a game one (the inverse of base3d's gameQuat)
export function fromBabylonQuat(q) {
    return [q.w, -q.x, -q.z, -q.y];
}

const U = (a, b) => a + Math.random() * (b - a);

// ---------- the particles' shader: a colour per instance, a soft round dot for puffs, the app's tone curve ----------
BABYLON.Effect.ShadersStore.ccfxVertexShader = `
precision highp float;
attribute vec3 position;
attribute vec2 uv;
#include<instancesDeclaration>  // (with the thin instances' colours: attribute instanceColor)
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
BABYLON.Effect.ShadersStore.ccfxFragmentShader = `
precision highp float;
uniform vec4 baseColor;
uniform float exposure;
varying vec2 vUV;
varying vec4 vColor;
void main(void) {
    vec4 c = vColor * baseColor;
#ifdef SOFT
    float d = length(vUV - vec2(0.5)) * 2.0;
    c.a *= pow(max(0.0, 1.0 - d), 1.8);  // (rw_fx.soft_dot_texture)
#endif
    vec3 color = c.rgb;
#ifdef ADDED
    // (added on: the app adds them to the scene's light before its tone curve, where the arena's lit floor is on
    // the curve's flat part, so each adds about half its light; added here after the curve, at that slope. Many
    // together still go from orange to yellow-white, as the app's do)
    if (exposure > 0.0) color *= exposure * 0.5;
#else
    if (exposure > 0.0) {  // simplepbr's post pass: exposure, then the Hejl-Burgess filmic curve
        color *= exposure;
        color = max(vec3(0.0), color - vec3(0.004));
        color = (color * (vec3(6.2) * color + vec3(0.5))) / (color * (vec3(6.2) * color + vec3(1.7)) + vec3(0.06));
    }
#endif
    gl_FragColor = vec4(color, c.a);
}`;

// how many of each the pools hold (rw_fx.Effects: 400 sparks, 90 puffs, 160 flames; 120, 30, 50 on the low tiers)
const POOLS = {blocks: {sparks: 80, puffs: 20, flames: 50, debris: 12},
               low: {sparks: 120, puffs: 30, flames: 50, debris: 40},
               medium: {sparks: 400, puffs: 90, flames: 160, debris: 40},
               high: {sparks: 400, puffs: 90, flames: 160, debris: 40}};

// a pool of particles drawn as one mesh's thin instances
class Cloud {
    constructor(scene, name, mesh, cap, blend, soft, order, exposure) {
        const m = new BABYLON.ShaderMaterial("ccfx" + name, scene, {vertex: "ccfx", fragment: "ccfx"}, {
            attributes: ["position", "uv"], uniforms: ["world", "viewProjection", "baseColor", "exposure"],
            defines: [soft ? "SOFT" : "", blend === BABYLON.Constants.ALPHA_COMBINE ? "" : "ADDED"].filter(Boolean), needAlphaBlending: true});
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.setFloat("exposure", exposure);
        m.alphaMode = blend;
        m.disableDepthWrite = true;
        m.backFaceCulling = false;
        mesh.material = m;
        mesh.isPickable = false;
        mesh.alwaysSelectAsActiveMesh = true;  // (the instances move: no bounds kept)
        mesh.doNotSyncBoundingInfo = true;
        mesh.renderingGroupId = 1;  // (after the whole scene, glass and all; the depth kept, so walls still hide them)
        mesh.alphaIndex = order;
        this.mats = new Float32Array(16 * cap);
        this.cols = new Float32Array(4 * cap);
        mesh.thinInstanceSetBuffer("matrix", this.mats, 16, false);
        mesh.thinInstanceSetBuffer("color", this.cols, 4, false);
        mesh.thinInstanceCount = 0;
        mesh.isVisible = false;
        this.mesh = mesh;
        this.items = Array.from({length: cap}, () => ({p: [0, 0, 0], v: [0, 0, 0], life: 0, max: 1, rgb: [1, 1, 1]}));
        this.cursor = 0;
        this.n = 0;
    }

    free() {  // (rw_fx._free: the first that isn't in use, or none)
        const items = this.items, n = items.length;
        for (let k = 0; k < n; k++) {
            const i = (this.cursor + k) % n;
            if (items[i].life <= 0) { this.cursor = (i + 1) % n; return items[i]; }
        }
        return null;
    }

    // one instance: its game position and Babylon axes (each scaled), its colour
    put(p, ax, ay, az, sx, sy, sz, r, g, b, a) {
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

export class RobotFX {
    // sc: the RobotScene (its Babylon scene, tier, materials and camera)
    constructor(sc) {
        this.sc = sc;
        const scene = sc.scene, size = POOLS[sc.tier] || POOLS.low;
        const exposure = sc.lighting ? sc.lighting.exposure : 0;
        scene.setRenderingAutoClearDepthStencil(1, false, false, false);
        const C = BABYLON.Constants;
        // sparks: tiny glowing streaks, 2.4 cm across and 18 long (along Babylon's z: the way they fly), added on
        const streak = BABYLON.MeshBuilder.CreateBox("fxspark", {width: 0.024, height: 0.024, depth: 0.18}, scene);
        this.sparks = new Cloud(scene, "spark", streak, size.sparks, C.ALPHA_ONEONE, false, 30, exposure);
        // smoke: soft grey puffs that rise and fade; fire: soft puffs added by their alpha
        const puff = BABYLON.MeshBuilder.CreatePlane("fxpuff", {size: 1}, scene);
        this.puffs = new Cloud(scene, "smoke", puff, size.puffs, C.ALPHA_COMBINE, true, 20, exposure);
        const flame = BABYLON.MeshBuilder.CreatePlane("fxflame", {size: 1}, scene);
        this.flames = new Cloud(scene, "fire", flame, size.flames, C.ALPHA_ADD, true, 25, exposure);
        // debris: little chunks of armour, lit, in the victim's paint: one mesh of thin instances for each robot's
        // colour (made when first needed), at most the pool's number of chunks in all
        this.debris = [];
        this.debrisCap = size.debris;
        this.debrisMeshes = new Map();
        this.tmpM = new BABYLON.Matrix();
        this.tmpS = new BABYLON.Vector3();
        this.tmpP = new BABYLON.Vector3();
        this.shake = 0;
        this.flameAcc = 0;
    }

    paint(rgb) {
        return this.sc.material("debris", rgb, 1, 1, 0, {tex: this.sc.tier === "blocks" ? "" : "paint", tile: 1.2});
    }

    // sparks (and debris for big hits) where something hit; colour: the victim's
    impact(pos, damage, kind, colour = [0.7, 0.7, 0.7]) {
        const count = {flip: 8, flame: 0, bump: Math.floor(damage / 4), wall: Math.floor(damage / 3)}[kind]
            ?? Math.floor(Math.min(40, 6 + damage * 1.5));
        for (let i = 0; i < count; i++) {
            const s = this.sparks.free();
            if (!s) break;
            s.p[0] = pos[0]; s.p[1] = pos[1]; s.p[2] = pos[2];
            let vx = U(-1, 1), vy = U(-1, 1), vz = U(0.2, 1.4);
            const l = Math.hypot(vx, vy, vz) || 1, sp = U(3, 9) / l;
            s.v[0] = vx * sp; s.v[1] = vy * sp; s.v[2] = vz * sp;
            s.life = s.max = U(0.25, 0.6);
        }
        if (damage > 10 && ["spinner", "drum", "hammer", "saw", "break"].includes(kind)) {
            for (let i = 0; i < Math.floor(Math.min(6, damage / 5)); i++) this.spawnDebris(pos, colour);
        }
        this.shake = Math.max(this.shake, Math.min(0.35, damage / (kind === "bump" || kind === "wall" ? 200 : 60)));
    }

    // a shower of sparks thrown one way: a saw or chainsaw grinding into armour
    stream(pos, d, count = 4) {
        for (let i = 0; i < count; i++) {
            const s = this.sparks.free();
            if (!s) return;
            s.p[0] = pos[0]; s.p[1] = pos[1]; s.p[2] = pos[2];
            const k = U(5, 12);
            s.v[0] = d[0] * k + U(-1.5, 1.5); s.v[1] = d[1] * k + U(-1.5, 1.5); s.v[2] = d[2] * k + U(0.5, 2.5);
            s.life = s.max = U(0.2, 0.55);
        }
    }

    // each frame while a flame thrower fires: a jet of fire from the nozzle (the app's 3 a frame, at 60 a second)
    flame(pos, d, dt) {
        this.flameAcc += 180 * dt;
        const amount = Math.floor(this.flameAcc);
        this.flameAcc -= amount;
        for (let i = 0; i < amount; i++) {
            const f = this.flames.free();
            if (!f) break;
            f.p[0] = pos[0]; f.p[1] = pos[1]; f.p[2] = pos[2];
            const k = U(4.5, 7.0);
            f.v[0] = d[0] * k + U(-0.6, 0.6); f.v[1] = d[1] * k + U(-0.6, 0.6); f.v[2] = d[2] * k + U(0.2, 1.2);
            f.life = f.max = U(0.3, 0.45);
        }
        if (Math.random() < 0.3 * dt * 60) {  // dark smoke at the end of the jet
            const p = this.puffs.free();
            if (p) {
                p.p[0] = pos[0] + d[0] * 2.2; p.p[1] = pos[1] + d[1] * 2.2; p.p[2] = pos[2] + 0.3;
                p.v[0] = d[0]; p.v[1] = d[1]; p.v[2] = 1.2;
                p.life = p.max = U(0.8, 1.4);
                p.rgb = [0.12, 0.1, 0.1];
            }
        }
    }

    debrisMesh(colour) {
        const key = colour.map(c => c.toFixed(3)).join(",");
        let d = this.debrisMeshes.get(key);
        if (!d) {
            const m = BABYLON.MeshBuilder.CreateBox("fxdebris", {size: 1}, this.sc.scene);
            m.material = this.paint(colour);
            m.isPickable = false;
            m.alwaysSelectAsActiveMesh = true;
            m.doNotSyncBoundingInfo = true;
            d = {mesh: m, mats: new Float32Array(16 * this.debrisCap), n: 0};
            m.thinInstanceSetBuffer("matrix", d.mats, 16, false);
            m.thinInstanceCount = 0;
            m.isVisible = false;
            this.debrisMeshes.set(key, d);
        }
        return d;
    }

    spawnDebris(pos, colour) {
        if (this.debris.length >= this.debrisCap) this.debris.shift();  // (the oldest goes, as the app's list of 40 drops its first)
        const hx = U(0.03, 0.08), hy = U(0.03, 0.08);
        this.debris.push({mesh: this.debrisMesh(colour), p: pos.slice(), v: [U(-4, 4), U(-4, 4), U(2, 6)], life: 4.0,
                          hpr: [0, 0, 0], spin: [U(-700, 700), U(-700, 700), 0], size: [hx, hy, 0.012]});
    }

    // each frame for a damaged robot: amount 0..1 and more (a robot knocked out is on fire)
    smoke(pos, amount, dt) {
        if (Math.random() > amount * 0.5 * Math.min(1, dt * 60)) return;
        const p = this.puffs.free();
        if (!p) return;
        p.p[0] = pos[0] + U(-0.2, 0.2); p.p[1] = pos[1] + U(-0.2, 0.2); p.p[2] = pos[2] + 0.3;
        p.v[0] = U(-0.2, 0.2); p.v[1] = U(-0.2, 0.2); p.v[2] = U(0.6, 1.2);
        p.life = p.max = U(1.2, 2.2);
        const shade = U(0.15, 0.35);
        p.rgb = [shade, shade, shade];
        if (amount > 0.7) {
            const f = this.flames.free();
            if (f) {
                f.p[0] = pos[0] + U(-0.15, 0.15); f.p[1] = pos[1] + U(-0.15, 0.15); f.p[2] = pos[2] + 0.25;
                f.v[0] = 0; f.v[1] = 0; f.v[2] = U(1.0, 2.0);
                f.life = f.max = U(0.25, 0.5);
            }
        }
    }

    update(dt) {
        const cam = this.sc.camera;
        const right = cam.getDirection(BABYLON.Axis.X), up = cam.getDirection(BABYLON.Axis.Y), fwd = cam.getDirection(BABYLON.Axis.Z);
        const R = [right.x, right.y, right.z], Up = [up.x, up.y, up.z], F = [fwd.x, fwd.y, fwd.z];
        const g = 9.81 * dt;
        const S = this.sparks;
        for (const s of S.items) {
            if (s.life <= 0) continue;
            s.life -= dt;
            if (s.life <= 0) continue;
            s.v[2] -= g;
            s.p[0] += s.v[0] * dt; s.p[1] += s.v[1] * dt; s.p[2] += s.v[2] * dt;
            const f = s.life / s.max;
            // pointing the way it flies (Babylon axes: the game's y and z swapped)
            const l = Math.hypot(s.v[0], s.v[1], s.v[2]) || 1;
            const az = [s.v[0] / l, s.v[2] / l, s.v[1] / l];
            let ax = Math.abs(az[1]) < 0.95 ? [az[2], 0, -az[0]] : [0, -az[2], az[1]];  // (up x az, or x x az)
            const la = Math.hypot(ax[0], ax[1], ax[2]) || 1;
            ax = [ax[0] / la, ax[1] / la, ax[2] / la];
            const ay = [az[1] * ax[2] - az[2] * ax[1], az[2] * ax[0] - az[0] * ax[2], az[0] * ax[1] - az[1] * ax[0]];
            S.put(s.p, ax, ay, az, 1, 1, 0.5 + f, 1.0, 0.55 + 0.4 * f, 0.15 + 0.5 * f * f, 1);
            if (s.p[2] < 0.01 && s.v[2] < 0) {  // bounce off the floor
                s.v[2] *= -0.35; s.v[0] *= 0.6; s.v[1] *= 0.6;
            }
        }
        S.flush();
        const P = this.puffs;
        for (const p of P.items) {
            if (p.life <= 0) continue;
            p.life -= dt;
            if (p.life <= 0) continue;
            const f = 1 - p.life / p.max;
            p.p[0] += p.v[0] * dt; p.p[1] += p.v[1] * dt; p.p[2] += p.v[2] * dt;
            const sc = 0.35 + f * 1.4;
            P.put(p.p, R, Up, F, sc, sc, sc, p.rgb[0], p.rgb[1], p.rgb[2], 0.55 * (1 - f));
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
            const sc = 0.25 + 0.8 * (1 - f);
            L.put(fl.p, R, Up, F, sc, sc, sc, f + 0.2, (0.35 + 0.4 * f * f) * f, 0.08 * f * f, 1);
        }
        L.flush();
        for (const d of this.debris) {
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
            const p = d.p, fade = Math.min(1, d.life);  // (the last second: it shrinks away, as it fades in the app)
            this.tmpS.set(2 * d.size[0] * fade, 2 * d.size[2] * fade, 2 * d.size[1] * fade);
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
    }

    // where the camera is pushed this frame (game metres; the window uses half of rw_fx's offset)
    shakeOffset() {
        const s = this.shake * 0.5;
        if (s <= 0) return null;
        return [U(-s, s), U(-s, s), U(-s, s) * 0.5];
    }
}

// rw_gfx.HitBar: a small health bar that floats over one part of a robot for a moment after that part is hit,
// always on top, facing the camera
export class HitBar {
    constructor(scene, text, width) {
        this.width = width;
        const W = width + 0.04, H = 0.2, ppm = 420;  // (the bar's frame, the name above it: metres, as the app's)
        this.cw = Math.round(W * ppm);
        this.ch = Math.round(H * ppm);
        this.ppm = ppm;
        this.text = text;
        const plane = BABYLON.MeshBuilder.CreatePlane("hitbar", {width: W, height: H}, scene);
        const tex = new BABYLON.DynamicTexture("hitbartex", {width: this.cw, height: this.ch}, scene, true);
        tex.hasAlpha = true;
        const m = new BABYLON.StandardMaterial("hitbarmat", scene);
        m.diffuseTexture = tex;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.disableLighting = true;
        m.backFaceCulling = false;
        m.useAlphaFromDiffuseTexture = true;
        plane.material = m;
        plane.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        plane.isPickable = false;
        plane.renderingGroupId = 2;  // (the depth cleared first: drawn over everything, as the app's)
        plane.setEnabled(false);
        this.plane = plane;
        this.tex = tex;
        this.key = "";
    }

    // pos: game position of the bar's middle; health 0..1
    show(pos, health, now) {
        let colour;
        if (health > 0.6) colour = "rgb(77,230,89)";
        else if (health > 0.3) colour = "rgb(255,204,38)";
        else colour = Math.floor(now * 8) % 2 ? "rgb(255,51,38)" : "rgb(153,26,20)";  // breaking: red, and it flickers
        const key = `${Math.round(health * 100)}:${colour}`;
        if (key !== this.key) {
            this.key = key;
            const ctx = this.tex.getContext(), k = this.ppm, w = this.width;
            ctx.clearRect(0, 0, this.cw, this.ch);
            const mid = this.ch - 0.05 * k;  // (the bar's middle, 5 cm up from the bottom)
            ctx.fillStyle = "rgb(10,10,15)";
            ctx.fillRect(0, mid - 0.05 * k, this.cw, 0.1 * k);
            ctx.fillStyle = colour;
            ctx.fillRect(0.02 * k, mid - 0.035 * k, Math.max(1, w * Math.max(0, Math.min(1, health)) * k), 0.07 * k);
            ctx.font = `bold ${Math.round(0.075 * k)}px sans-serif`;
            ctx.textBaseline = "alphabetic";
            ctx.fillStyle = "rgba(0,0,0,0.9)";
            ctx.fillText(this.text, 0.006 * k, mid - 0.07 * k + 0.006 * k);
            ctx.fillStyle = "#ffffff";
            ctx.fillText(this.text, 0, mid - 0.07 * k);
            this.tex.update(true);
        }
        this.plane.position = v3(pos[0], pos[1], pos[2] + 0.05);
        this.plane.setEnabled(true);
    }

    hide() {
        this.plane.setEnabled(false);
    }

    dispose() {
        this.plane.dispose(false, true);
    }
}
