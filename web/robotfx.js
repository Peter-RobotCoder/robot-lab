// Robot Lab's effects in Club Coders Live, ported from the app's rw_fx.py: sparks (glowing streaks
// with gravity, a bounce off the floor and a colour that cools), the saws' and chainsaws' spark showers, the flame
// thrower's jet of fire with dark smoke at its end, chunks of armour in the victim's colour on big hits, smoke from
// damaged robots (and fire over 70% damage), and the camera shake. Also rw_gfx.HitBar (the bar over a part just
// hit) and the game-quaternion helpers the real damage needs (Panda's HPR, exactly as Panda composes it).
//
// Kept cheap, as the app keeps them: a fixed pool per kind, each pool one mesh drawn with thin instances (one draw
// call), sized per tier. Particles are unlit and blended over the scene as the app blends them (sparks added on,
// fire added by its soft dot's alpha, smoke mixed), with the app's tone curve on the lit tiers (simplepbr's post
// pass, which the app's effects go through), and drawn after everything else without writing depth. On mesh and
// lines (CHANGE 145, as the window's rw_fx) the sparks are the line colour, debris is its edges, and there is no
// smoke or fire.
//
// (CHANGE 145) Robot Lab's ultra tier too: the window's smooth robots and arena (robot_models.py and arena_models.py,
// written by make_models.py to models/robot_ultra.json and arena_ultra.json, fetched on ultra alone), see the end.

/* global BABYLON */

import {v3, gameQuat, unpackPart, getLineColour} from "./base3d.js";

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
// (CHANGE 145: the line tiers' 400 sparks and no smoke or fire, as the window's; ultra's as high's)
const POOLS = {mesh: {sparks: 400, puffs: 1, flames: 1, debris: 40}, lines: {sparks: 400, puffs: 1, flames: 1, debris: 40},
               blocks: {sparks: 80, puffs: 20, flames: 50, debris: 12},
               low: {sparks: 120, puffs: 30, flames: 50, debris: 40},
               medium: {sparks: 400, puffs: 90, flames: 160, debris: 40},
               high: {sparks: 400, puffs: 90, flames: 160, debris: 40},
               ultra: {sparks: 400, puffs: 90, flames: 160, debris: 40}};

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
        this.look = !!sc.wire;  // (mesh and lines: the sparks in the line colour, read each frame, so a new one at once)
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
        if (this.look) return;  // (the line tiers: no fire)
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
        const key = this.look ? "lines" : colour.map(c => c.toFixed(3)).join(",");
        let d = this.debrisMeshes.get(key);
        if (!d) {
            let m = BABYLON.MeshBuilder.CreateBox("fxdebris", {size: 1}, this.sc.scene);
            if (this.look) {  // (the line tiers: a chunk's edges, every chunk in the line colour)
                const box = m, sc = this.sc;
                m = sc.linesMesh("fxdebris", sc.edgeLines([box], sc.wire), sc.lineMaterial("debris", 1, ...sc.lineFade()));
                box.dispose();
            } else {
                m.material = this.paint(colour);
            }
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
        if (this.look || Math.random() > amount * 0.5 * Math.min(1, dt * 60)) return;  // (the line tiers: no smoke)
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
        const S = this.sparks, ink = this.look ? BABYLON.Color3.FromHexString(getLineColour()) : null;
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
            if (ink) S.put(s.p, ax, ay, az, 1, 1, 0.5 + f, ink.r * (0.4 + 0.6 * f), ink.g * (0.4 + 0.6 * f), ink.b * (0.4 + 0.6 * f), 1);
            else S.put(s.p, ax, ay, az, 1, 1, 0.5 + f, 1.0, 0.55 + 0.4 * f, 0.15 + 0.5 * f * f, 1);
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

// ---------- the window's camera controls (rw_camera.GameCamera, CHANGE 143) ----------
// The five views' own settings: each zooms (the wheel, or + and -), swings round and tilts (the right button
// dragged, Q and E), moves sideways (a sideways scroll) and goes back with Home, each view keeping its own; kept in
// a learner's profile in the window's own format (settings() and restore() are the window's), so a window and a
// page share them. robot.js's rigCamera places the camera from these, as GameCamera.update does.
export const CAM_MODES = ["third", "fpv", "zoom", "arena", "centre"];
export const CAM_NAMES = {third: "Third person", fpv: "First person", zoom: "Zoomed arena follow", arena: "Full arena", centre: "Centre camera"};
const clampTo = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const wrapDeg = v => ((v % 360) + 360) % 360;
const r1 = v => Math.round(v * 10) / 10, r2 = v => Math.round(v * 100) / 100;

export class RobotCamera {
    constructor(mode = "third") {
        this.mode = CAM_MODES.includes(mode) ? mode : "third";
        this.dist = 6.5;          // third person: how far behind (1.5 to 30 m)
        this.fpvScale = 1.0;      // first person: lens zoom (0.3 = telephoto, 1.3 = very wide)
        this.zoomScale = 1.0;     // zoomed follow: tighter or wider framing (0.2 to 4)
        this.arenaScale = 1.0;    // full arena: closer or further away (0.35 to 2)
        this.centreScale = 1.0;   // centre camera: closer or further away (0.35 to 2)
        this.angles = Object.fromEntries(CAM_MODES.map(m => [m, [0.0, 0.0]]));  // each view's swing round and tilt up, degrees
        this.pans = Object.fromEntries(CAM_MODES.map(m => [m, 0.0]));           // ...and how far it was moved sideways, metres
        this.lookZ = 0.0;         // (the height of what the view looks at: a swung camera stays above the floor)
    }

    get name() { return CAM_NAMES[this.mode]; }
    get orbit() { return this.angles[this.mode][0]; }
    set orbit(v) { this.angles[this.mode][0] = v; }
    get tilt() { return this.angles[this.mode][1]; }
    set tilt(v) { this.angles[this.mode][1] = v; }

    turn(degrees) { this.orbit = wrapDeg(this.orbit + degrees); }  // swing the view round (Q and E)

    pan(metres) { this.pans[this.mode] = clampTo(this.pans[this.mode] + metres, -12.0, 12.0); }  // sideways, this view only

    resetView() {  // Home: this view back as it comes (its swing, tilt and sideways move)
        this.angles[this.mode] = [0.0, 0.0];
        this.pans[this.mode] = 0.0;
    }

    // a drag with the right button across the picture: dx, dy as shares of its width and height (right and down
    // positive). (The window: mouse x and y from -1 to 1, y up; 150 degrees round and 60 up for each unit)
    drag(dx, dy) {
        this.orbit = wrapDeg(this.orbit - dx * 2 * 150);
        this.tilt = clampTo(this.tilt + dy * 2 * 60, -12.0, 55.0);
    }

    // an offset from what the camera looks at, swung round by orbit and tilted up by tilt (game coordinates)
    swing(o) {
        if (!(this.orbit || this.tilt)) return o.slice();
        const a = this.orbit * Math.PI / 180, t = this.tilt * Math.PI / 180;
        const x = o[0] * Math.cos(a) - o[1] * Math.sin(a), y = o[0] * Math.sin(a) + o[1] * Math.cos(a);
        const across = Math.hypot(x, y);
        if (across < 1e-6) return o.slice();
        const keep = Math.cos(t);  // tilting up: less across, more height
        return [x * keep, y * keep, Math.max(0.3 - this.lookZ, o[2] + across * Math.sin(t))];
    }

    setMode(mode) { if (CAM_MODES.includes(mode)) this.mode = mode; }

    wheel(factor) {  // zoom the view in use in (factor < 1) or out (factor > 1)
        if (this.mode === "third") this.dist = clampTo(this.dist * factor, 1.5, 30.0);
        else if (this.mode === "fpv") this.fpvScale = clampTo(this.fpvScale * factor, 0.3, 1.3);
        else if (this.mode === "zoom") this.zoomScale = clampTo(this.zoomScale * factor, 0.2, 4.0);
        else if (this.mode === "arena") this.arenaScale = clampTo(this.arenaScale * factor, 0.35, 2.0);
        else this.centreScale = clampTo(this.centreScale * factor, 0.35, 2.0);
    }

    settings() {  // (exactly rw_camera's: the window reads what the page keeps)
        return {mode: this.mode, dist: r2(this.dist), fpv: r2(this.fpvScale), zoom: r2(this.zoomScale), arena: r2(this.arenaScale),
                centre: r2(this.centreScale), orbit: r1(this.orbit), tilt: r1(this.tilt),
                angles: Object.fromEntries(CAM_MODES.map(m => [m, [r1(this.angles[m][0]), r1(this.angles[m][1])]])),
                pans: Object.fromEntries(CAM_MODES.map(m => [m, r2(this.pans[m])]))};
    }

    // put back a view and zoom levels saved earlier (a learner's profile): the window's format, or the page's older
    // {mode, dist}, which is the same with the rest left as they come
    restore(saved) {
        if (!saved || typeof saved !== "object") return;
        const num = (v, now) => (v === undefined || v === null || !Number.isFinite(Number(v)) ? now : Number(v));
        if (CAM_MODES.includes(saved.mode)) this.setMode(saved.mode);
        this.dist = clampTo(num(saved.dist, this.dist), 1.5, 30.0);
        this.fpvScale = clampTo(num(saved.fpv, this.fpvScale), 0.3, 1.3);
        this.zoomScale = clampTo(num(saved.zoom, this.zoomScale), 0.2, 4.0);
        this.arenaScale = clampTo(num(saved.arena, this.arenaScale), 0.35, 2.0);
        this.centreScale = clampTo(num(saved.centre, this.centreScale), 0.35, 2.0);
        if (saved.angles && typeof saved.angles === "object") {  // (each view's own: the window's CHANGE 111)
            for (const [m, ot] of Object.entries(saved.angles)) {
                if (CAM_MODES.includes(m) && Array.isArray(ot)) this.angles[m] = [wrapDeg(num(ot[0], 0)), clampTo(num(ot[1], 0), -12.0, 55.0)];
            }
        } else {  // (saved before each view had its own: the one swing goes to the view in use)
            this.orbit = wrapDeg(num(saved.orbit, 0));
            this.tilt = clampTo(num(saved.tilt, 0), -12.0, 55.0);
        }
        if (saved.pans && typeof saved.pans === "object") {
            for (const [m, p] of Object.entries(saved.pans)) if (CAM_MODES.includes(m)) this.pans[m] = clampTo(num(p, 0), -12.0, 12.0);
        }
    }
}

// ---------- ultra (CHANGE 145): the window's smooth robots and arena ----------
// models/robot_ultra.json (1 MB) and models/arena_ultra.json (4.8 MB), written by make_models.py from the window's
// robot_models.py and arena_models.py. Fetched only on ultra (a school laptop on low never asks for them); null until
// loaded (or when they aren't there or are broken), and the scene draws high's robots and arena till then.
const DEG = Math.PI / 180;
let robotModels = null, robotAsked = null, arenaModels = null, arenaAsked = null;
export function loadRobotModels() {
    if (!robotAsked) {
        robotAsked = fetch("models/robot_ultra.json", {cache: "no-cache"}).then(r => r.ok ? r.json() : null).then(d => {
            robotModels = d && d.version === 1 && d.roles && d.pieces && d.pieces.hull ? d : null;
            return robotModels;
        }).catch(() => null);
    }
    return robotAsked;
}
export function robotModelsData() { return robotModels; }

export function loadArenaModels() {
    if (!arenaAsked) {
        arenaAsked = fetch("models/arena_ultra.json", {cache: "no-cache"}).then(r => r.ok ? r.json() : null).then(d => {
            arenaModels = d && d.version === 1 && d.materials && d.groups && d.groups.floor ? d : null;
            return arenaModels;
        }).catch(() => null);
    }
    return arenaAsked;
}
export function arenaModelsData() { return arenaModels; }

// lab_sim.shapes: a robot's sizes and pivots (the physics' own), the standard robot nearest (80% to 120%) made k
// times bigger or smaller all over; a Resident Robot (big) its own size. Game coordinates
export function robotShapes(weapon, size, big = false) {
    const ref = big ? size : Math.max(0.8, Math.min(1.2, size)), k = size / ref, s = ref;
    const h = [0.6 * s, 0.8 * s, 0.18 * s], top = 0.1 + h[2];
    let sh;
    if (weapon === "wedge") sh = {plate: [h[0] + 0.02, 0.6, 0.03], pivot: [0, h[1] - 0.05, top]};
    else if (weapon === "spinner") sh = {bar: [0.8 * s, 0.08, 0.05], pivot: [0, h[1] + 0.28 * s, 0.1]};
    else if (weapon === "drum") sh = {drum: [0.2 * s, h[0] * 0.8], pivot: [0, h[1] + 0.18, 0.08]};
    else if (weapon === "vdisc") sh = {disc: [0.42 * s, 0.035 * s], pivot: [0, h[1] + 0.05, 0.42 * s - (0.32 - 0.08) + 0.04]};
    else if (weapon === "flame") sh = {nozzle: [0.07 * s, 0.22 * s, 0.07 * s], pivot: [0, h[1] - 0.25 * s, top + 0.12 * s]};
    else if (weapon === "laser") sh = {emitter: [0.06 * s, 0.18 * s, 0.05 * s], pivot: [0, h[1] - 0.3 * s, top + 0.08 * s]};
    else if (weapon === "chainsaw") sh = {arm: [0.06 * s, 0.3 * s, 0.05 * s], bar: [0.025 * s, 0.42 * s, 0.07 * s], pivot: [0, h[1] * 0.35, top + 0.12]};
    else {
        const m = Math.min(s, 1.3);
        sh = {arm: [0.05 * m, Math.min(0.85 * s, 1.3), 0.05 * m], head: [0.22 * s, 0.14 * s, 0.14 * s], pivot: [0, -0.2 * s, top + 0.1]};
    }
    return Object.assign(sh, {half: h, top, k, size: ref});
}

// robot_models.layout: where each piece goes for a robot of this weapon and standard size (house: a Resident
// Robot's styling), [[node, piece, pos, hpr, scale]] in the node's frame (game coordinates, degrees)
export function robotLayout(weapon, size, house, sh) {
    const s = size, hx = 0.6 * s, hy = 0.8 * s, hz = 0.18 * s, z0 = 0.1, top = z0 + hz;
    const one = [1, 1, 1], S = [s, s, s], O = [0, 0, 0];
    const out = [["chassis", "hull", [0, 0, z0], O, S], ["chassis", "eyes", [0, hy + 0.005, z0 + hz * 0.45], O, S],
                 ["chassis", "antenna", [-hx * 0.6, -hy * 0.7, top + 0.04 + 0.045 * s], O, one], ["deck", "deck", O, O, S],
                 ["skirt_r", "skirt", O, O, S], ["skirt_l", "skirt", O, [180, 0, 0], S], ["rear", "rear", O, O, S]];
    [[0.72, 0.55], [-0.72, 0.55], [0.72, -0.55], [-0.72, -0.55]].forEach(([x], i) =>
        out.push([`wheel${i}`, house ? "house_wheel" : "wheel", O, [x < 0 ? 180 : 0, 0, 0], one]));
    if (house) {
        out.push(["deck", "house_plates", O, O, S], ["skirt_r", "skirt_stripes", O, O, S], ["skirt_l", "skirt_stripes", O, [180, 0, 0], S],
                 ["chassis", "house_handles", [0, -hy, top], O, S], ["chassis", "beacon_base", [hx * 0.55, -hy * 0.55, top + 0.14], O, one],
                 ["beacon", "beacon", O, O, one]);
    }
    const pv = sh.pivot;
    if (weapon === "wedge") out.push(["weapon", "wedge", O, O, [sh.plate[0] / 0.62, 1, 1]], ["chassis", "wedge_cheeks", [0, 0, top - 0.05], O, S]);
    else if (weapon === "spinner") out.push(["weapon", "spinner_bar", O, O, [sh.bar[0] / 0.8, 1, 1]], ["weapon", "spinner_hub", O, O, one],
                                            ["chassis", "spinner_forks", [0, hy, z0], O, one]);
    else if (weapon === "drum") out.push(["weapon", "drum", O, O, S], ["chassis", "drum_mounts", [0, hy, z0], O, S]);
    else if (weapon === "vdisc") out.push(["weapon", "vdisc", O, O, S], ["chassis", "vdisc_slot", [pv[0], pv[1], pv[2]], O, S]);
    else if (weapon === "flame") out.push(["weapon", "flame_nozzle", O, O, S], ["chassis", "flame_tanks", [0, -hy * 0.25, top + 0.13 * s / 1.6], O, S],
                                          ["chassis", "flame_base", [pv[0], pv[1], pv[2] - 0.09], O, S]);
    else if (weapon === "laser") out.push(["weapon", "laser", O, O, S], ["chassis", "laser_mount", [pv[0], pv[1], pv[2] - 0.07], O, S]);
    else if (weapon === "chainsaw") out.push(["weapon", "chainsaw_arm", O, O, S], ["chain", "chain", O, O, S],
                                             ["chassis", "chainsaw_mounts", [pv[0], pv[1], pv[2] - 0.05], O, S]);
    else {
        const a = sh.arm, hd = sh.head;
        out.push(["weapon", "hammer_arm", O, O, [a[0] / 0.05, a[1] / 0.85, a[2] / 0.05]],
                 ["weapon", "hammer_head", [0, a[1] * 2, 0], O, [hd[0] / 0.22, hd[1] / 0.14, hd[2] / 0.14]],
                 ["chassis", "hammer_axle", [0, -0.2 * s, top + 0.1], O, S]);
    }
    return out;
}

// each piece's parts unpacked once for the page's life (shared by every robot): [{role, pos, nor, idx}], Babylon axes
// (CHANGE 152) shadow: the piece as the sun's shadow map draws it (the file's "shadow": no bolts or lamps, the wheels
// plain tyres)
const pieceCache = new Map();
function pieceParts(name, shadow = false) {
    const key = (shadow ? "shadow:" : "") + name;
    if (!pieceCache.has(key)) {
        const parts = [], S = shadow ? robotModels.shadow || {skip: [], pieces: {}} : null;
        const list = S && S.pieces && S.pieces[name] ? S.pieces[name] : robotModels.pieces[name] || [];
        for (const p of list) {
            if (S && (S.skip || []).includes(p.material)) continue;
            const a = unpackPart(p);
            if (a && robotModels.roles[p.material]) parts.push({role: p.material, pos: a.pos, nor: a.nor, idx: a.idx});
        }
        pieceCache.set(key, parts);
    }
    return pieceCache.get(key);
}

const lin = c => Math.pow(Math.max(0, c), 2.2);

// One node's pieces as ONE mesh (the window's: a Geom a node), in the robot's colours: each vertex its role's colour
// (null: the design's colour, "trim": the style's, both screen colours; made linear) and its texture coordinates on
// its role's texel of the atlas (robotAtlas: roughness, metal and glow). items: [[piece, pos, hpr, scale]] in the
// node's frame (game coordinates; only headings are used), colour and trim screen colours 0 to 1. Null if empty
// (CHANGE 152) shadow: the pieces as the sun's shadow map draws them (pieceParts)
export function robotNodeMesh(sc, name, items, colour, trim, shadow = false) {
    const roles = Object.keys(robotModels.roles), n = roles.length, parts = [];
    let nv = 0, ni = 0;
    for (const [piece, pos, hpr, scale] of items) {
        for (const p of pieceParts(piece, shadow)) { parts.push([p, pos, hpr, scale]); nv += p.pos.length / 3; ni += p.idx.length; }
    }
    if (!nv) return null;
    const P = new Float32Array(nv * 3), N = new Float32Array(nv * 3), UV = new Float32Array(nv * 2), C = new Float32Array(nv * 4);
    const I = nv >= 65536 ? new Uint32Array(ni) : new Uint16Array(ni);
    let ov = 0, oi = 0;
    for (const [p, at, hpr, scale] of parts) {
        const h = hpr[0] * DEG, c = Math.cos(h), s = Math.sin(h), [sx, sy, sz] = scale;
        const look = robotModels.roles[p.role], ri = roles.indexOf(p.role);
        // (the garage preview's simple materials take screen colours: sc.screenColours)
        const rgb = (look.colour === null ? colour : look.colour === "trim" ? trim : look.colour).map(sc.screenColours ? c => c : lin);
        const u = (ri + 0.5) / n, src = p.pos, nor = p.nor, cnt = src.length / 3;
        for (let i = 0; i < cnt; i++) {
            const o = i * 3, w = (ov + i) * 3;
            // (Babylon's x, y, z are the game's x, z, y: scaled, turned about the game's z, moved)
            const gx = src[o] * sx, gy = src[o + 2] * sy, gz = src[o + 1] * sz;
            P[w] = c * gx - s * gy + at[0]; P[w + 2] = s * gx + c * gy + at[1]; P[w + 1] = gz + at[2];
            const nx = nor[o] / sx, ny = nor[o + 2] / sy, nz = nor[o + 1] / sz, l = Math.hypot(nx, ny, nz) || 1;
            N[w] = (c * nx - s * ny) / l; N[w + 2] = (s * nx + c * ny) / l; N[w + 1] = nz / l;
            const t = (ov + i) * 2, q = (ov + i) * 4;
            UV[t] = u; UV[t + 1] = 0.5;
            C[q] = rgb[0]; C[q + 1] = rgb[1]; C[q + 2] = rgb[2]; C[q + 3] = 1;
        }
        for (let k = 0; k < p.idx.length; k++) I[oi + k] = p.idx[k] + ov;
        ov += cnt;
        oi += p.idx.length;
    }
    const mesh = new BABYLON.Mesh(name, sc.scene);
    const vd = new BABYLON.VertexData();
    vd.positions = P;
    vd.normals = N;
    vd.uvs = UV;
    vd.colors = C;
    vd.indices = I;
    vd.applyToMesh(mesh);
    mesh.ccOwnUV = true;  // (its texture coordinates are the atlas's: not the metres base3d gives a mesh)
    mesh.isPickable = false;
    return mesh;
}

// a robot's two little pictures, a texel a role (the window's rw_gfx.robot_atlas): (1, roughness, metal), and its glow
// over ROBOT_GLOW ("lights": the robot's own lights colour, linear). Made once per scene and lights colour
export const ROBOT_GLOW = 8.0;
export function robotAtlas(sc, lights) {
    if (!sc.ultraAtlas || sc.ultraAtlas.scene !== sc.scene) sc.ultraAtlas = {scene: sc.scene};  // (a scene's own: gone with it)
    const cache = sc.ultraAtlas;
    const roles = Object.keys(robotModels.roles), n = roles.length, key = lights.map(v => v.toFixed(3)).join(",");
    const near = BABYLON.Texture.NEAREST_SAMPLINGMODE;
    const make = data => {
        const t = BABYLON.RawTexture.CreateRGBATexture(data, n, 1, sc.scene, false, false, near);
        t.wrapU = t.wrapV = BABYLON.Texture.CLAMP_ADDRESSMODE;
        return t;
    };
    if (!cache.mr) {
        const mr = new Uint8Array(n * 4);
        roles.forEach((r, i) => { const L = robotModels.roles[r]; mr.set([255, Math.round(L.rough * 255), Math.round(L.metal * 255), 255], i * 4); });
        cache.mr = make(mr);
    }
    if (!cache[key]) {
        const glow = new Uint8Array(n * 4);
        roles.forEach((r, i) => {
            const e = robotModels.roles[r].emission, v = e === "lights" ? lights : Array.isArray(e) ? e : [0, 0, 0];
            glow.set([...v.map(c => Math.round(Math.min(1, c / ROBOT_GLOW) * 255)), 255], i * 4);
        });
        cache[key] = make(glow);
    }
    return {mr: cache.mr, glow: cache[key]};
}

// The window's ultra arena (rw_gfx.ArenaVisual.ultra) from models/arena_ultra.json: the floor for the holes the user
// mods cut, its scars, the cage (not with No cage), the venue's floor, the towers, the stands with their seats and
// crowd (seats alone if the look has no crowd), the big screen, the hall, and the rig and roof (returned apart: the
// full arena view hides them). Each part one mesh (the file has one per material and group), each placed shape's
// part one mesh drawn as thin instances (turned h degrees about the game's z, scaled by s, moved to x, y, z; the
// tinted parts coloured by each instance's r, g, b, made linear). Colour = the material's colour (null: the arena's
// wall colour) x vertex colour x tint x texture; decal: drawn a little nearer than the floor it lies on; alpha: see-
// through by its vertices' alpha, after the solid things, not writing depth; flat and far cast no shadow; far parts
// are in the hall's haze (pbr.js's picked fog). Returns {meshes, rig, casters, parts, instances, triangles}
// (CHANGE 152) a material's part bigger than this is cut into the arena's four sides (rw_gfx.SPLIT_TRIS)
const SPLIT_TRIS = 6000;

// a part's arrays (Babylon axes) cut into the arena's four sides, each triangle by where its middle is (east, west,
// north or south of the arena's diagonals): rw_gfx.sides. The empty ones left out
export function arenaSides(a) {
    const n = a.idx.length / 3, side = new Uint8Array(n), out = [];
    for (let t = 0; t < n; t++) {
        let x = 0, y = 0;
        for (let k = 0; k < 3; k++) { const v = a.idx[t * 3 + k] * 3; x += a.pos[v]; y += a.pos[v + 2]; }
        side[t] = Math.abs(x) >= Math.abs(y) ? (x >= 0 ? 0 : 1) : (y >= 0 ? 2 : 3);
    }
    for (let s = 0; s < 4; s++) {
        const map = new Map(), idx = [];
        for (let t = 0; t < n; t++) {
            if (side[t] !== s) continue;
            for (let k = 0; k < 3; k++) {
                const v = a.idx[t * 3 + k];
                if (!map.has(v)) map.set(v, map.size);
                idx.push(map.get(v));
            }
        }
        if (!idx.length) continue;
        const m = map.size, pos = new Float32Array(m * 3), nor = new Float32Array(m * 3), uv = new Float32Array(m * 2);
        const col = a.col ? new Float32Array(m * 4) : null;
        for (const [v, j] of map) {
            pos.set(a.pos.subarray(v * 3, v * 3 + 3), j * 3);
            nor.set(a.nor.subarray(v * 3, v * 3 + 3), j * 3);
            uv.set(a.uv.subarray(v * 2, v * 2 + 2), j * 2);
            if (col) col.set(a.col.subarray(v * 4, v * 4 + 4), j * 4);
        }
        out.push({pos, nor, uv, col, idx: m >= 65536 ? Uint32Array.from(idx) : Uint16Array.from(idx)});
    }
    return out;
}

export function makeUltraArena(sc, data, mods, look) {
    const scene = sc.scene, out = {meshes: [], rig: [], casters: [], parts: 0, instances: 0, triangles: 0};
    const wall = (Array.isArray(look.wall_colour) && look.wall_colour.length >= 3 ? look.wall_colour : [155, 25, 20]).map(v => v / 255);
    const mats = {};
    // (CHANGE 152) shadowless: out past where any shadow falls (the crowd, the hall, its roof, the big screen): no
    // shadow looked up, the same picture for less (the soft shadow's twelve looks a pixel)
    const material = (name, variant, far, shadowless = false) => {
        const L = data.materials[name] || {colour: [1, 1, 1], rough: 1, metal: 0};
        const key = `arena ${name}${variant}${shadowless ? " lit" : ""}${far ? " far" : ""}`;
        if (mats[key]) return mats[key];
        const m = sc.lighting.material(key, {rgb: L.colour === null ? wall : L.colour || [1, 1, 1], rough: Number(L.rough ?? 1),
            metal: Number(L.metal ?? 0), tex: L.texture || "", emission: Array.isArray(L.emission) ? L.emission : null,
            blend: !!L.alpha, haze: far, shadowless});
        m.backFaceCulling = !L.two_sided;
        m.sideOrientation = BABYLON.Material.ClockWiseSideOrientation;  // (the front as the file's, turned round by unpackPart)
        if (L.decal) { m.zOffset = -1; m.zOffsetUnits = -4; }  // (Panda's setDepthOffset(1))
        if (L.alpha) m.disableDepthWrite = true;
        sc.materials[key] = m;
        return (mats[key] = m);
    };
    // a mesh from arrays (Babylon axes): its own texture coordinates, its colours if it has them
    const make = (a, name, alpha) => {
        const mesh = new BABYLON.Mesh(name, scene);
        const vd = new BABYLON.VertexData();
        vd.positions = a.pos;
        vd.normals = a.nor;
        vd.uvs = a.uv;
        vd.indices = a.idx;
        if (a.col) vd.colors = a.col;
        vd.applyToMesh(mesh);
        if (alpha) { mesh.hasVertexAlpha = true; mesh.alphaIndex = 0; }  // (the scars before the cage's screens)
        mesh.ccOwnUV = true;  // (its texture coordinates are the file's: repeats already)
        mesh.isPickable = false;
        out.triangles += a.idx.length / 3;
        return mesh;
    };
    // (CHANGE 152, as the window's rw_gfx.ultra_parts) a big part that doesn't lie flat is one mesh for each side of the
    // arena, so what is out of view isn't drawn
    const own = (part, into, shadowless = false) => {
        const a = unpackPart(part);
        if (!a) return;
        const L = data.materials[part.material] || {};
        const cut = a.idx.length / 3 > SPLIT_TRIS && !L.flat ? arenaSides(a) : [a];
        for (const piece of cut) {
            const mesh = make(piece, "arena " + part.name, part.alpha);
            mesh.ccCast = false;  // (its shadow: the one caster below)
            mesh.material = material(part.material, `:${!!(part.colours || part.alpha)}`, !!part.far, shadowless && !!part.far);
            mesh.freezeWorldMatrix();
            into.push(mesh);
        }
        if (!part.far && !L.flat) (casting.get(into) || casting.set(into, []).get(into)).push(a);
        out.parts++;
    };
    // (CHANGE 152, as the window's) the sun's shadow map draws every part that casts a shadow as ONE mesh (it sees every
    // side: a draw, not a few dozen), never seen by the camera (layerMask 0); the rig's apart, hidden with it
    const casting = new Map();
    const caster = (list, into) => {
        let nv = 0, ni = 0;
        for (const a of list) { nv += a.pos.length / 3; ni += a.idx.length; }
        const pos = new Float32Array(nv * 3), nor = new Float32Array(nv * 3), I = nv >= 65536 ? new Uint32Array(ni) : new Uint16Array(ni);
        let ov = 0, oi = 0;
        for (const a of list) {
            pos.set(a.pos, ov * 3);
            nor.set(a.nor, ov * 3);
            for (let k = 0; k < a.idx.length; k++) I[oi + k] = a.idx[k] + ov;
            ov += a.pos.length / 3;
            oi += a.idx.length;
        }
        const mesh = new BABYLON.Mesh("arena shadow", scene);
        const vd = new BABYLON.VertexData();
        vd.positions = pos;
        vd.normals = nor;
        vd.uvs = new Float32Array(nv * 2);
        vd.indices = I;
        vd.applyToMesh(mesh);
        mesh.material = material("steel", ":false", false);
        mesh.layerMask = 0;
        mesh.isPickable = false;
        mesh.ccCast = true;
        mesh.ccOwnUV = true;
        mesh.freezeWorldMatrix();
        into.push(mesh);
    };
    const group = n => (Array.isArray(data.groups[n]) ? data.groups[n] : []);
    const floor = "floor" + (mods.spike_pit ? "_spike_pit" : "") + (mods.flame_pit ? "_flame_pit" : "");
    // (made, so drawn, in this order, near to far: the cage and the towers, the crowd, then the stands and the hall
    // behind them, the floors last, so what the nearer parts hide is depth tested, never lit)
    for (const n of [...(mods.no_cage ? [] : ["cage"]), "towers", "screen"]) for (const p of group(n)) own(p, out.meshes, n === "screen");
    for (const p of group("rig")) own(p, out.rig);
    for (const p of group("roof")) own(p, out.rig, true);
    // (CHANGE 152) the seats and fans placed into one mesh for each material and side of the arena, as the window merges
    // them (model_geom.merged): a few draws, and the sides out of view left out (thin instances drew all four always)
    const rows = look.crowd === false ? {seat: (data.instances || {}).seat || []} : data.instances || {};
    const crowd = new Map();
    for (const [shape, list] of Object.entries(rows).sort(([a], [b]) => (a === "seat") - (b === "seat"))) {  // (the fans before the seats they sit in)
        const parts = data.shapes[shape];
        if (!Array.isArray(parts) || !Array.isArray(list) || !list.length) continue;
        for (const part of parts) {
            const a = unpackPart(part);
            if (!a) continue;
            for (const r of list) {
                const side = Math.abs(r[0]) >= Math.abs(r[1]) ? (r[0] >= 0 ? 0 : 1) : (r[1] >= 0 ? 2 : 3);
                const key = `${part.material}:${!!part.far}:${side}`;
                if (!crowd.has(key)) crowd.set(key, {material: part.material, far: !!part.far, items: [], nv: 0, ni: 0});
                const c = crowd.get(key);
                c.items.push([a, r, !!part.tint]);
                c.nv += a.pos.length / 3;
                c.ni += a.idx.length;
            }
        }
        out.instances += list.length;
    }
    for (const c of crowd.values()) {
        const P = new Float32Array(c.nv * 3), N = new Float32Array(c.nv * 3), UV = new Float32Array(c.nv * 2), C = new Float32Array(c.nv * 4);
        const I = c.nv >= 65536 ? new Uint32Array(c.ni) : new Uint16Array(c.ni);
        let ov = 0, oi = 0;
        for (const [a, r, tint] of c.items) {
            // (turned h degrees about the game's z, scaled by s, moved to x, y, z; Babylon's y is the game's z)
            const h = r[3] * DEG, s = r[4], cs = Math.cos(h), sn = Math.sin(h), n = a.pos.length / 3;
            const t = tint ? [lin(r[5]), lin(r[6]), lin(r[7])] : [1, 1, 1];
            for (let i = 0; i < n; i++) {
                const o = i * 3, w = (ov + i) * 3, x = a.pos[o], y = a.pos[o + 1], z = a.pos[o + 2];
                P[w] = (cs * x - sn * z) * s + r[0]; P[w + 1] = y * s + r[2]; P[w + 2] = (sn * x + cs * z) * s + r[1];
                const nx = a.nor[o], nz = a.nor[o + 2];
                N[w] = cs * nx - sn * nz; N[w + 1] = a.nor[o + 1]; N[w + 2] = sn * nx + cs * nz;
                UV[(ov + i) * 2] = a.uv[i * 2]; UV[(ov + i) * 2 + 1] = a.uv[i * 2 + 1];
                const q = (ov + i) * 4;
                for (let k = 0; k < 3; k++) C[q + k] = (a.col ? a.col[i * 4 + k] : 1) * t[k];
                C[q + 3] = a.col ? a.col[i * 4 + 3] : 1;
            }
            for (let k = 0; k < a.idx.length; k++) I[oi + k] = a.idx[k] + ov;
            ov += n;
            oi += a.idx.length;
        }
        const mesh = make({pos: P, nor: N, uv: UV, col: C, idx: I}, `arena crowd ${c.material}`, false);
        mesh.material = material(c.material, ":true", c.far, true);
        mesh.ccCast = false;  // (out in the stands, beyond the shadow's 26 m: drawn into it for nothing)
        mesh.ccCrowd = true;
        mesh.freezeWorldMatrix();
        out.meshes.push(mesh);
    }
    for (const n of ["stands", "hall", "scars", floor, mods.no_cage ? "venue_floor_open" : "venue_floor"]) for (const p of group(n)) own(p, out.meshes, n === "hall");
    for (const [into, list] of casting) caster(list, into);
    for (const m of [...out.meshes, ...out.rig]) if (m.ccCast) out.casters.push(m);
    return out;
}
