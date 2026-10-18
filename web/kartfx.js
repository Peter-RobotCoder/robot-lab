// Kart Lab's ultra tier in the browser (CHANGE 144): what the page adds for a strong graphics card, none of it
// touching the race (the karts, the track and the timing are the server's; this is only drawn).
//   the sky      a dome with the sky's colours from the horizon up, the sun's disc and glow, slow clouds
//   the land     hills all round, far off in the haze, the flat country out to them, and woods (thin instances)
//   the look     the camera's pictures after the scene: a glow on what is bright (and shading in the corners, SSAO, if a
//                game asks: since CHANGE 151 none does, Kart Lab's ultra having dropped it for its frame time)
//                (bloom), a little sharpening; the world round the kart watched as a cube (reflected in the paint)
//   the karts    skid marks left on the road while drifting, sparks from the exhaust while boosting, and the
//                curved kart (models/kart_ultra.json, written by make_models.py) when it is there
//   the circuit  the window's ultra circuit (models/kart_scenery.json, make_models.py from kart/kart_scenery.py):
//                asphalt, kerbs, gravel, barriers, grass, trees, the grandstand and its crowd, the pits, the gantry,
//                fields and hills, in place of the land and woods above (and of the road, kerbs and grass of the
//                lower tiers) once it has loaded
// The particles use robotfx.js's shader ("ccfx": a colour per thin instance, the app's tone curve).

/* global BABYLON */

import {v3, mulberry, unpackPart} from "./base3d.js";  // (the packed parts' reader, shared with Robot Lab: CHANGE 145)
import {toneMap} from "./pbr.js";
import "./robotfx.js";

const DEG = Math.PI / 180;

// ---------- the sky ----------
const SKY_VERT = `
precision highp float;
attribute vec3 position;
uniform mat4 world;
uniform mat4 viewProjection;
varying vec3 vDir;
void main(void) {
    vDir = position;
    gl_Position = viewProjection * world * vec4(position, 1.0);
}`;
const SKY_FRAG = `
precision highp float;
uniform vec4 baseColor;
uniform vec3 zenith;
uniform vec3 horizon;
uniform vec3 below;
uniform vec3 sunDir;
uniform vec3 sunCol;
uniform float time;
varying vec3 vDir;
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
    return v;
}
void main(void) {
    vec3 d = normalize(vDir);
    float h = d.y;
    vec3 col = h > 0.0 ? mix(horizon, zenith, pow(h, 0.55)) : mix(horizon, below, clamp(-h * 6.0, 0.0, 1.0));
    float s = max(dot(d, sunDir), 0.0);
    // (clouds: soft heaps drifting on a flat ceiling, thinner towards the horizon, lit on the sun's side)
    if (h > 0.0) {
        vec2 p = d.xz / (h + 0.15) * 2.2 + vec2(time * 0.006, time * 0.002);
        float n = fbm(p);
        float c = smoothstep(0.58, 0.8, n) * smoothstep(0.03, 0.35, h);
        vec3 cloud = mix(vec3(0.72, 0.76, 0.82), vec3(0.96, 0.95, 0.93), clamp(0.4 + 0.5 * s + 2.0 * (n - 0.62), 0.0, 1.0));
        col = mix(col, cloud, c * 0.85);
    }
    col += sunCol * (pow(s, 900.0) * 3.0 + pow(s, 60.0) * 0.22 + pow(s, 6.0) * 0.07);
    gl_FragColor = vec4(col * baseColor.rgb, 1.0);
}`;

// The sky dome: look is the scene's pbr look (its background and sun); the colours after the tone curve, so the
// horizon matches the haze (pbr.js's fog) and the background of the other tiers
export function makeSky(sc) {
    const P = sc.look.pbr, exposure = Math.pow(2, P.exposure || 0);
    const bg = toneMap(P.background, exposure);
    const m = new BABYLON.ShaderMaterial("ccsky", sc.scene, {vertexSource: SKY_VERT, fragmentSource: SKY_FRAG}, {
        attributes: ["position"], uniforms: ["world", "viewProjection", "baseColor", "zenith", "horizon", "below", "sunDir", "sunCol", "time"]});
    m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
    m.setVector3("zenith", new BABYLON.Vector3(bg[0] * 0.55, bg[1] * 0.72, bg[2] * 0.97));
    m.setVector3("horizon", new BABYLON.Vector3(...HAZE));
    m.setVector3("below", new BABYLON.Vector3(0.55, 0.62, 0.6));
    const o = P.sun.offset, n = Math.hypot(...o);
    m.setVector3("sunDir", new BABYLON.Vector3(o[0] / n, o[2] / n, o[1] / n));
    m.setVector3("sunCol", new BABYLON.Vector3(1.0, 0.92, 0.75));
    m.setFloat("time", 0);
    m.backFaceCulling = false;
    m.disableDepthWrite = true;
    const dome = BABYLON.MeshBuilder.CreateSphere("sky", {diameter: 5000, segments: 24}, sc.scene);
    dome.material = m;
    dome.infiniteDistance = true;
    dome.isPickable = false;
    dome.applyFog = false;
    dome.renderingGroupId = 0;
    dome.alphaIndex = -1;
    const t0 = performance.now();
    sc.scene.onBeforeRenderObservable.add(() => m.setFloat("time", (performance.now() - t0) / 1000));
    return dome;
}

// the sky's colour at the horizon, after the tone curve: the haze far off (pbr.js's fog) fades to it. The window's
// (kart_gfx.HAZE, 0.62 0.74 0.92 as light, through the tone curve at its exposure), so the circuit's fields and
// hills are as hazy and as grey as the window's (CHANGE 144)
export const HAZE = [0.83, 0.85, 0.88];

// ---------- the land beyond the track: hills in a ring, the country out to them, and woods ----------
// track: the Track; ground: the scene's grass grid ({xs, ys, z}); base: the grass's level away from the track.
// Returns the meshes (the scene merges and keeps them)
export function makeLand(sc, track, base) {
    const [x0, y0, x1, y1] = track.bounds();
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const inner = Math.min(x1 - x0, y1 - y0) / 2 + 30;  // (inside the grass, under it: no gap at its edge)
    const flat = Math.max(x1 - x0, y1 - y0) / 2 + 160, top = flat + 300;
    const rnd = mulberry(29), phase = [rnd() * 6.3, rnd() * 6.3, rnd() * 6.3, rnd() * 6.3];
    const hill = a => 26 + 18 * Math.sin(a * 3 + phase[0]) + 11 * Math.sin(a * 7 + phase[1]) + 6 * Math.sin(a * 13 + phase[2]) + 3 * Math.sin(a * 29 + phase[3]);
    const radii = [inner, inner + 60, flat - 60, flat, flat + 50, flat + 110, flat + 170, flat + 230, top];
    const SEG = 160, pos = [], idx = [], col = [];
    for (let i = 0; i <= SEG; i++) {
        const a = i / SEG * 2 * Math.PI;
        for (const r of radii) {
            const f = Math.min(1, Math.max(0, (r - flat) / (top - flat - 70)));
            const rise = f * f * (3 - 2 * f) * hill(a) * (r >= top ? 0.85 : 1);
            const z = base - 1.0 + rise;
            pos.push(cx + Math.cos(a) * r, z, cy + Math.sin(a) * r);
            const g = 0.85 + 0.15 * Math.sin(a * 11 + r * 0.05);  // (a little light and dark across the fields)
            col.push(0.55 * g, 0.75 * g, 0.45 * g, 1);
        }
    }
    const R = radii.length;
    for (let i = 0; i < SEG; i++) {
        for (let j = 0; j < R - 1; j++) {
            const a = i * R + j;
            idx.push(a, a + R, a + R + 1, a, a + R + 1, a + 1);
        }
    }
    const land = new BABYLON.Mesh("land", sc.scene);
    const vd = new BABYLON.VertexData();
    vd.positions = pos;
    vd.indices = idx;
    vd.colors = col;
    const nor = [];
    BABYLON.VertexData.ComputeNormals(pos, idx, nor);
    let up = 0;
    for (let i = 1; i < nor.length; i += 3) up += nor[i];
    if (up < 0) for (let i = 0; i < nor.length; i++) nor[i] = -nor[i];
    vd.normals = nor;
    vd.applyToMesh(land);
    land.material = sc.material("land", [0.42, 0.6, 0.3], 1.0, 0, 0, {tex: "grass", tile: 0.05});
    // mountains beyond the hills, out to about 1.6 km, snow on their tops: faint in the haze (as the window's)
    const MR = [top - 20, 1050, 1200, 1320, 1440, 1600], mp = [rnd() * 6.3, rnd() * 6.3, rnd() * 6.3];
    const peak = a => 170 + 80 * Math.sin(a * 4 + mp[0]) + 45 * Math.sin(a * 9 + mp[1]) + 25 * Math.sin(a * 17 + mp[2]);
    const mpos = [], midx = [], mcol = [];
    for (let i = 0; i <= SEG; i++) {
        const a = i / SEG * 2 * Math.PI;
        MR.forEach((r, j) => {
            const f = [0, 0.15, 0.7, 1, 0.75, 0.3][j];
            const z = base - 1.0 + f * peak(a) + (j === 0 ? hill(a) * 0.85 : 0);
            mpos.push(cx + Math.cos(a) * r, z, cy + Math.sin(a) * r);
            const snow = Math.min(1, Math.max(0, (z - base - 175) / 30));
            mcol.push(0.36 + 0.6 * snow, 0.42 + 0.54 * snow, 0.36 + 0.62 * snow, 1);
        });
    }
    const M = MR.length;
    for (let i = 0; i < SEG; i++) for (let j = 0; j < M - 1; j++) { const a = i * M + j; midx.push(a, a + M, a + M + 1, a, a + M + 1, a + 1); }
    const mountains = new BABYLON.Mesh("mountains", sc.scene);
    const md = new BABYLON.VertexData();
    md.positions = mpos;
    md.indices = midx;
    md.colors = mcol;
    const mn = [];
    BABYLON.VertexData.ComputeNormals(mpos, midx, mn);
    let mu = 0;
    for (let i = 1; i < mn.length; i += 3) mu += mn[i];
    if (mu < 0) for (let i = 0; i < mn.length; i++) mn[i] = -mn[i];
    md.normals = mn;
    md.applyToMesh(mountains);
    mountains.material = sc.material("mountains", [1, 1, 1], 1.0);
    return {land, mountains, centre: [cx, cy], inner, flat};
}

// woods: firs (crowns of two cones) and round trees, each part one mesh drawn as thin instances, many for one draw.
// spots: [[x, y, z, height, round]]
export function makeForest(sc, spots) {
    if (!spots.length) return [];
    const scene = sc.scene;
    const trunk = BABYLON.MeshBuilder.CreateCylinder("firtrunk", {height: 1, diameter: 0.14, tessellation: 7}, scene);
    trunk.position.y = 0.5;
    trunk.bakeCurrentTransformIntoVertices();
    const c1 = BABYLON.MeshBuilder.CreateCylinder("fircrown", {height: 0.55, diameterBottom: 0.62, diameterTop: 0, tessellation: 9}, scene);
    c1.position.y = 0.55;
    const c2 = BABYLON.MeshBuilder.CreateCylinder("fircrown2", {height: 0.42, diameterBottom: 0.44, diameterTop: 0, tessellation: 9}, scene);
    c2.position.y = 0.82;
    const crown = BABYLON.Mesh.MergeMeshes([c1, c2], true);
    trunk.material = sc.material("trunk", [0.35, 0.22, 0.12], 1.0);
    crown.material = sc.material("fircrown", [0.1, 0.36, 0.15], 1.0);
    const ball = BABYLON.MeshBuilder.CreateIcoSphere("treeball", {radius: 0.3, subdivisions: 2, flat: false}, scene);
    ball.position.y = 0.68;
    ball.scaling.y = 0.9;
    ball.bakeCurrentTransformIntoVertices();
    ball.material = sc.material("treeball", [0.2, 0.46, 0.17], 1.0);
    const all = [], firs = [], rounds = [], m = new BABYLON.Matrix();
    const rnd = mulberry(41);
    for (const [x, y, z, h, round] of spots) {
        const w = h * (0.85 + rnd() * 0.3);
        BABYLON.Matrix.ComposeToRef(new BABYLON.Vector3(w, h, w), BABYLON.Quaternion.RotationAxis(BABYLON.Axis.Y, rnd() * 6.28),
                                    v3(x, y, z - 0.1), m);
        const a = m.toArray().slice();
        all.push(...a);
        (round ? rounds : firs).push(...a);
    }
    const out = [];
    for (const [mesh, list] of [[trunk, all], [crown, firs], [ball, rounds]]) {
        if (!list.length) { mesh.dispose(); continue; }
        mesh.thinInstanceSetBuffer("matrix", new Float32Array(list), 16, true);
        mesh.isPickable = false;
        out.push(mesh);
    }
    return out;
}

// ---------- the camera's pictures after the scene ----------
// SSAO (Babylon's SSAO2, on its own geometry buffer: pbr.js's materials can't write Babylon's pre-pass), then the
// glow on what is brightest (the sun, the dash pads, a boost's flame) and a little sharpening. The scene's own
// shader has already applied the app's tone curve, so Babylon's image processing stays off. The scene says which
// meshes shade each other (gbuffer.renderList: the world's, not the labels, the smoke or the sky). (CHANGE 145) opts:
// which parts (ssao, sharpen) and how many samples the picture has (samples): each game's ultra says its own
// (scene.js, robot.js, fight.js: none has SSAO since CHANGE 151)
export class AfterFx {
    constructor(sc, opts = {}) {
        const scene = sc.scene, cam = sc.camera, o = Object.assign({ssao: true, sharpen: true, samples: 8, bloomWeight: 0.32}, opts);
        this.ssao = this.gbuffer = null;
        if (o.ssao) try {
            const ssao = this.ssao = new BABYLON.SSAO2RenderingPipeline("ccssao", scene, {ssaoRatio: 0.5, blurRatio: 1}, [cam], true);
            ssao.radius = 1.6;
            ssao.totalStrength = 2.2;
            ssao.base = 0.05;
            ssao.samples = 12;
            ssao.maxZ = 140;
            ssao.minZAspect = 0.4;
            ssao.expensiveBlur = false;  // (the bilateral blur: 6 ms more at 3.6 million pixels on an Iris Xe, no difference seen)
            this.gbuffer = scene.enableGeometryBufferRenderer();
        } catch (e) { console.warn("No SSAO:", e); this.ssao = null; }
        const p = this.pipeline = new BABYLON.DefaultRenderingPipeline("ccultra", false, scene, [cam]);
        // (the canvas's multisampling doesn't reach a picture drawn for after-effects: its own, 8 as the window's ultra)
        p.samples = Math.max(1, Math.min(o.samples, scene.getEngine().getCaps().maxMSAASamples || 4));
        p.imageProcessingEnabled = false;
        p.bloomEnabled = true;
        p.bloomThreshold = 0.82;
        p.bloomWeight = o.bloomWeight;
        p.bloomKernel = 48;
        p.bloomScale = 0.5;
        p.sharpenEnabled = !!o.sharpen;
        if (o.sharpen) {
            p.sharpen.edgeAmount = 0.18;
            p.sharpen.colorAmount = 1.0;
        }
    }

    dispose() {
        if (this.ssao) this.ssao.dispose();
        this.pipeline.dispose();
    }
}

// ---------- skid marks: dark strips left on the road by the back tyres while drifting ----------
const SKID_LIFE = 14, SKID_FADE = 5;
export class Skids {
    constructor(sc, cap = 1200) {
        const scene = sc.scene;
        const m = new BABYLON.ShaderMaterial("ccfxskids", scene, {vertex: "ccfx", fragment: "ccfx"}, {
            attributes: ["position", "uv"], uniforms: ["world", "viewProjection", "baseColor", "exposure"], needAlphaBlending: true});
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.setFloat("exposure", 0);
        m.alphaMode = BABYLON.Constants.ALPHA_COMBINE;
        m.disableDepthWrite = true;
        m.backFaceCulling = false;
        m.zOffset = -2;
        const mesh = this.mesh = BABYLON.MeshBuilder.CreatePlane("skid", {size: 1}, scene);
        mesh.material = m;
        mesh.isPickable = false;
        mesh.alwaysSelectAsActiveMesh = true;
        mesh.doNotSyncBoundingInfo = true;
        this.mats = new Float32Array(16 * cap);
        this.cols = new Float32Array(4 * cap);
        mesh.thinInstanceSetBuffer("matrix", this.mats, 16, false);
        mesh.thinInstanceSetBuffer("color", this.cols, 4, false);
        mesh.thinInstanceCount = 0;
        mesh.isVisible = false;
        this.born = new Float32Array(cap).fill(-1e9);
        this.cap = cap;
        this.cursor = 0;
        this.count = 0;
        this.t = 0;
    }

    // a strip from a to b (game points on the road), 0.1 m wide
    add(a, b) {
        const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
        if (len < 0.05 || len > 3) return;
        const ux = dx / len, uy = dy / len, w = 0.1, i = this.cursor;
        const M = this.mats, o = i * 16, mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, mz = (a[2] + b[2]) / 2;
        // (the plane's x along the strip, its y across it, its z up: Babylon's axes are the game's with y and z swapped)
        M[o] = ux * len; M[o + 1] = 0; M[o + 2] = uy * len; M[o + 3] = 0;
        M[o + 4] = -uy * w; M[o + 5] = 0; M[o + 6] = ux * w; M[o + 7] = 0;
        M[o + 8] = 0; M[o + 9] = 1; M[o + 10] = 0; M[o + 11] = 0;
        M[o + 12] = mx; M[o + 13] = mz; M[o + 14] = my; M[o + 15] = 1;
        this.born[i] = this.t;
        this.cursor = (i + 1) % this.cap;
        this.count = Math.min(this.cap, this.count + 1);
        this.dirty = true;
    }

    update(dt) {
        this.t += dt;
        const C = this.cols;
        let any = false;
        for (let i = 0; i < this.count; i++) {
            const age = this.t - this.born[i];
            const a = age > SKID_LIFE ? 0 : 0.55 * Math.min(1, (SKID_LIFE - age) / SKID_FADE);
            const c = i * 4;
            if (C[c + 3] !== a || this.dirty) { C[c] = C[c + 1] = C[c + 2] = 0.03; C[c + 3] = a; any = true; }
        }
        const mesh = this.mesh;
        mesh.thinInstanceCount = this.count;
        mesh.isVisible = this.count > 0;
        if (this.dirty) mesh.thinInstanceBufferUpdated("matrix");
        if (any) mesh.thinInstanceBufferUpdated("color");
        this.dirty = false;
    }
}

// ---------- sparks: hot specks thrown back from the exhaust while boosting, falling and fading ----------
export class Sparks {
    constructor(sc, cap = 240) {
        const scene = sc.scene;
        const m = new BABYLON.ShaderMaterial("ccfxsparks", scene, {vertex: "ccfx", fragment: "ccfx"}, {
            attributes: ["position", "uv"], uniforms: ["world", "viewProjection", "baseColor", "exposure"],
            defines: ["SOFT", "ADDED"], needAlphaBlending: true});
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.setFloat("exposure", 0);
        m.alphaMode = BABYLON.Constants.ALPHA_ADD;
        m.disableDepthWrite = true;
        m.backFaceCulling = false;
        const mesh = this.mesh = BABYLON.MeshBuilder.CreatePlane("spark", {size: 1}, scene);
        mesh.material = m;
        mesh.isPickable = false;
        mesh.alwaysSelectAsActiveMesh = true;
        mesh.doNotSyncBoundingInfo = true;
        mesh.renderingGroupId = 1;
        this.mats = new Float32Array(16 * cap);
        this.cols = new Float32Array(4 * cap);
        mesh.thinInstanceSetBuffer("matrix", this.mats, 16, false);
        mesh.thinInstanceSetBuffer("color", this.cols, 4, false);
        mesh.thinInstanceCount = 0;
        mesh.isVisible = false;
        this.items = Array.from({length: cap}, () => ({p: [0, 0, 0], v: [0, 0, 0], life: 0, max: 1}));
        this.cursor = 0;
    }

    // n sparks from p (game point), the kart heading yaw (degrees) and going at speed
    emit(p, yaw, speed, n = 2) {
        const h = yaw * DEG, fx = Math.cos(h), fy = Math.sin(h);
        for (let k = 0; k < n; k++) {
            const it = this.items[this.cursor];
            this.cursor = (this.cursor + 1) % this.items.length;
            const back = 1.5 + Math.random() * 3, side = (Math.random() - 0.5) * 2.4;
            it.p = p.slice();
            it.v = [fx * (speed * 0.85 - back) - fy * side, fy * (speed * 0.85 - back) + fx * side, 0.8 + Math.random() * 2.2];
            it.max = it.life = 0.25 + Math.random() * 0.3;
        }
    }

    update(dt, cam) {
        const r = cam.getDirection(BABYLON.Axis.X), u = cam.getDirection(BABYLON.Axis.Y), f = cam.getDirection(BABYLON.Axis.Z);
        const M = this.mats, C = this.cols;
        let n = 0;
        for (const it of this.items) {
            if (it.life <= 0) continue;
            it.life -= dt;
            if (it.life <= 0) continue;
            it.v[2] -= 9.8 * dt;
            for (let i = 0; i < 3; i++) it.p[i] += it.v[i] * dt;
            const left = it.life / it.max, s = 0.05 + 0.05 * left, o = n * 16, p = it.p;
            M[o] = r.x * s; M[o + 1] = r.y * s; M[o + 2] = r.z * s; M[o + 3] = 0;
            M[o + 4] = u.x * s; M[o + 5] = u.y * s; M[o + 6] = u.z * s; M[o + 7] = 0;
            M[o + 8] = f.x * s; M[o + 9] = f.y * s; M[o + 10] = f.z * s; M[o + 11] = 0;
            M[o + 12] = p[0]; M[o + 13] = p[2]; M[o + 14] = p[1]; M[o + 15] = 1;
            const c = n * 4;
            C[c] = 1.0; C[c + 1] = 0.55 + 0.35 * left; C[c + 2] = 0.15 + 0.3 * left * left; C[c + 3] = 1;
            n++;
        }
        const mesh = this.mesh;
        mesh.thinInstanceCount = n;
        mesh.isVisible = n > 0;
        if (n) {
            mesh.thinInstanceBufferUpdated("matrix");
            mesh.thinInstanceBufferUpdated("color");
        }
    }
}

// ---------- the curved kart (models/kart_ultra.json: make_models.py, CHANGE 144) ----------
// {version, scale?, body: [part], wheel: [part, one wheel at the origin, its axle along +y], wheels: [{x, y, z,
// front, side}], steering: [part]}; a part: {name, role, positions, normals, indices, uvs?} in the game's frame
// (z up, metres, the nose along +x). Loaded once; null until it has (or when it isn't there or is broken)
let ultraKart = null, ultraAsked = null;
export function loadUltraKart() {
    if (!ultraAsked) {
        ultraAsked = fetch("models/kart_ultra.json").then(r => r.ok ? r.json() : null).then(d => {
            ultraKart = d && Array.isArray(d.body) && Array.isArray(d.wheel) && Array.isArray(d.wheels) && d.wheels.length ? d : null;
            return ultraKart;
        }).catch(() => null);
    }
    return ultraAsked;
}
export function ultraKartData() { return ultraKart; }

// one part as a Babylon mesh: the game's (x, y, z) as Babylon's (x, z, y), and each triangle turned round (the swap
// is a mirror image, which turns the winding over)
export function partMesh(sc, part, scale = 1) {
    const p = part.positions || [], n = part.normals || [], ix = part.indices || [];
    if (p.length < 9 || ix.length < 3) return null;
    const pos = new Array(p.length), nor = n.length === p.length ? new Array(n.length) : null;
    for (let i = 0; i < p.length; i += 3) {
        pos[i] = p[i] * scale; pos[i + 1] = p[i + 2] * scale; pos[i + 2] = p[i + 1] * scale;
        if (nor) { nor[i] = n[i]; nor[i + 1] = n[i + 2]; nor[i + 2] = n[i + 1]; }
    }
    const idx = new Array(ix.length);
    for (let i = 0; i + 2 < ix.length; i += 3) { idx[i] = ix[i]; idx[i + 1] = ix[i + 2]; idx[i + 2] = ix[i + 1]; }
    const m = new BABYLON.Mesh(part.name || "part", sc.scene);
    const vd = new BABYLON.VertexData();
    vd.positions = pos;
    vd.indices = idx;
    if (nor) vd.normals = nor;
    else { const out = []; BABYLON.VertexData.ComputeNormals(pos, idx, out); vd.normals = out; }
    if (Array.isArray(part.uvs) && part.uvs.length === p.length / 3 * 2) { vd.uvs = part.uvs; m.ccOwnUV = true; }
    vd.applyToMesh(m);
    return m;
}

// ---------- the circuit (models/kart_scenery.json: make_models.py, CHANGE 144) ----------
// {version, materials: {name: {colour, rough, metal, texture, metres, emission?, two_sided?, decal?, flat?}},
// shapes: {name: [part]}, tracks: {club|oval|straight: {parts: [part], instances: {shape: [[x, y, z, h, s, r, g, b]]}}},
// notes}: kart/kart_scenery.py's, the window's ultra circuit (kart_gfx.ultra_circuit). Fetched only on ultra (4.7 MB:
// a school laptop on low never asks for it); null until it has loaded (or when it isn't there or is broken)
let scenery = null, sceneryAsked = null;
export function loadScenery() {
    if (!sceneryAsked) {
        sceneryAsked = fetch("models/kart_scenery.json").then(r => r.ok ? r.json() : null).then(d => {
            scenery = d && d.version === 1 && d.materials && d.shapes && d.tracks ? d : null;
            return scenery;
        }).catch(() => null);
    }
    return sceneryAsked;
}
export function sceneryData() { return scenery; }

// (CHANGE 151) how the circuit is drawn quickly: cells, the placed shapes copied by where they stand for the shadow
// and the geometry buffer (CELL metres square); treesAO, the trees in the shading in corners (off: as the window)
export const CIRCUIT_CULL = {cells: true, treesAO: false};
const CELL = 40;

// (CHANGE 151) The circuit's copies by cell (makeCircuit's) drawn only where they're wanted: into the sun's shadow
// those whose cells reach into its box (the shadow camera's view), into the geometry buffer (SSAO) those in the
// camera's view; each list's other meshes as they are. Set on the two render targets (scene.js refreshLists)
export function cullLists(sc) {
    const L = sc.lighting, planes = BABYLON.Frustum.GetPlanes(BABYLON.Matrix.Identity());
    const pick = (list, count, inside) => {
        const out = [];
        for (let i = 0; i < count; i++) {
            const m = list[i];
            if (!m.ccCell || m.isInFrustum(inside)) out.push(m);
        }
        return out;
    };
    if (L && L.rtt) L.rtt.getCustomRenderList = (layer, list, count) => {
        BABYLON.Frustum.GetPlanesToRef(L.shadowMatrix, planes);  // (Lighting.update has placed it round the target)
        return pick(list, count, planes);
    };
    const gb = sc.fx && sc.fx.gbuffer && sc.fx.gbuffer.getGBuffer && sc.fx.gbuffer.getGBuffer();
    if (gb) gb.getCustomRenderList = (layer, list, count) => pick(list, count, sc.scene.frustumPlanes);
}

// One track's circuit (data: the file, key: club, oval or straight), as the window's ultra_circuit draws it: each of
// the track's own parts one mesh (the file has one per material, and far or near), and each part of each shape placed
// many times one mesh drawn as thin instances (turned h degrees about the game's z, scaled by s, moved to x, y, z;
// the parts marked tint coloured by each instance's r, g, b, made linear). Colour = the material's colour x vertex
// colour x tint x texture; two_sided seen from behind (pbr.js draws both sides: the others have their backs culled);
// decal drawn a little nearer than the road it lies on. The far country and everything flat cast no shadow (the window
// hides them from the sun's shadow camera) but have shadows cast on them. Returns {meshes, casters, trees, parts,
// instances, triangles} (null for a track the file hasn't), every mesh frozen where it stands
export function makeCircuit(sc, data, key) {
    const track = data.tracks[key];
    if (!track || !Array.isArray(track.parts)) return null;
    const scene = sc.scene, out = {meshes: [], casters: [], trees: [], parts: 0, instances: 0, triangles: 0,
                                   lamps: [], water: [], lights: data.lights || null, lit: -1, cells: 0};
    const mats = {};
    const material = (name, variant) => {  // (one per kind of mesh: a ShaderMaterial is compiled for the attributes it's given)
        const look = data.materials[name] || {colour: [1, 1, 1], rough: 1, metal: 0};
        const k = name + variant;
        if (mats[k]) return mats[k];
        const m = sc.material("circuit " + k, look.colour || [1, 1, 1], Number(look.rough ?? 1), Number(look.metal ?? 0), 0,
                              {tex: look.texture || "", emission: Array.isArray(look.emission) ? look.emission : null});
        m.backFaceCulling = !look.two_sided;
        m.sideOrientation = BABYLON.Material.ClockWiseSideOrientation;  // (the front as the file's, turned round by unpackPart)
        if (look.decal) { m.zOffset = -1; m.zOffsetUnits = -4; }  // (Panda's setDepthOffset(1))
        return (mats[k] = m);
    };
    const build = (part, name) => {
        const a = unpackPart(part);
        if (!a) return null;
        const mesh = new BABYLON.Mesh(name, scene);
        const vd = new BABYLON.VertexData();
        vd.positions = a.pos;
        vd.normals = a.nor;
        vd.uvs = a.uv;
        vd.indices = a.idx;
        if (a.col) vd.colors = a.col;
        vd.applyToMesh(mesh);
        mesh.ccOwnUV = true;  // (its texture coordinates are the file's: repeats already)
        mesh.isPickable = false;
        const look = data.materials[part.material] || {};
        mesh.ccCast = !part.far && !look.flat;
        mesh.ccFar = !!part.far;
        out.triangles += a.idx.length / 3;
        return mesh;
    };
    const own = part => {  // (one of the track's own parts)
        const mesh = build(part, "circuit " + part.name);
        if (!mesh) return;
        // (CHANGE 151: a part with a group, each pair of start lights, has a material of its own to light it by)
        mesh.material = material(part.material, `:${!!part.colours}${part.group ? ":" + part.group : ""}`);
        if (part.material === "lamp" && part.group) out.lamps[Number(part.group) - 1] = mesh.material;
        if (part.material === "water") {  // (its ripples drift: circuitFrame moves its texture coordinates)
            const uv = Float32Array.from(mesh.getVerticesData(BABYLON.VertexBuffer.UVKind));
            mesh.setVerticesData(BABYLON.VertexBuffer.UVKind, uv, true);
            out.water.push({mesh, uv, now: new Float32Array(uv.length), look: data.materials.water || {}});
        }
        mesh.ccProbe = true;  // (the reflection cube watches the circuit's own parts, not the thousands of shapes)
        mesh.freezeWorldMatrix();
        out.meshes.push(mesh);
        out.parts++;
    };
    // (made, so drawn, in this order: Babylon draws what doesn't blend in the order it was made, and the turf runs on
    // under the road and the far country under the turf, so the road, its paint, the kerbs, the buildings and the
    // shapes come first, then the turf and the pond, the country last: the ground they hide is depth tested, never lit)
    const ground = p => p.far ? 2 : p.material === "turf" || p.material === "water" ? 1 : 0;
    for (const part of track.parts) if (!ground(part)) own(part);
    for (const [shape, rows] of Object.entries(track.instances || {})) {
        const parts = data.shapes[shape];
        if (!Array.isArray(parts) || !Array.isArray(rows) || !rows.length) continue;
        const M = new Float32Array(rows.length * 16), C = new Float32Array(rows.length * 4);
        rows.forEach((r, i) => {
            const h = r[3] * DEG, s = r[4], c = Math.cos(h) * s, n = Math.sin(h) * s, o = i * 16;
            // (rows of Babylon's matrix: where its x, y and z go, then the place; its y is the game's z)
            M[o] = c; M[o + 2] = n; M[o + 5] = s; M[o + 8] = -n; M[o + 10] = c;
            M[o + 12] = r[0]; M[o + 13] = r[2]; M[o + 14] = r[1]; M[o + 15] = 1;
            C[i * 4] = Math.pow(r[5], 2.2); C[i * 4 + 1] = Math.pow(r[6], 2.2); C[i * 4 + 2] = Math.pow(r[7], 2.2); C[i * 4 + 3] = 1;
        });
        // (CHANGE 151) the instances by where they stand, CELL metres square, for the copies below
        const cells = new Map();
        rows.forEach((r, i) => {
            const k = `${Math.floor(r[0] / CELL)},${Math.floor(r[1] / CELL)}`;
            if (!cells.has(k)) cells.set(k, []);
            cells.get(k).push(i);
        });
        for (const part of parts) {
            const mesh = build(part, `circuit ${shape} ${part.name}`);
            if (!mesh) continue;
            out.triangles += (rows.length - 1) * mesh.getTotalIndices() / 3;
            mesh.material = material(part.material, `:${!!part.colours}:i${part.tint ? "t" : ""}`);
            mesh.thinInstanceSetBuffer("matrix", M, 16, true);
            if (part.tint) mesh.thinInstanceSetBuffer("color", C, 4, true);
            mesh.thinInstanceRefreshBoundingInfo(false);
            mesh.ccProbe = false;
            const tree = part.material === "needles" || part.material === "leaves" || part.material === "bark";
            // (the shading in corners: not for thousands of blades of grass; CHANGE 151: nor the trees, which the
            // window shades with their own pictures alone: the page's SSAO had them darker than the window's)
            mesh.ccAO = part.material !== "blades" && !(tree && !CIRCUIT_CULL.treesAO);
            mesh.freezeWorldMatrix();
            mesh.doNotSyncBoundingInfo = true;
            out.meshes.push(mesh);
            if (tree) out.trees.push(mesh);
            // (CHANGE 151) the sun's shadow and the shading in corners draw copies of this, one a cell, never seen by
            // the camera (layerMask 0), and only the cells in the shadow's box or the camera's view (cullLists): one
            // mesh for the whole circuit drew every tree, tyre and fan into the 4096 shadow and the geometry buffer
            // every frame, however far off
            const ao = mesh.ccAO && !!(sc.fx && sc.fx.gbuffer);  // (no copies for a geometry buffer there isn't)
            if (!CIRCUIT_CULL.cells || (!mesh.ccCast && !ao) || mesh.ccFar) continue;
            // (CHANGE 155) each copy its own geometry: Babylon keeps a mesh's thin instances on its geometry, so copies
            // sharing the original's each put their own cell's in its place, and the camera drew only the last cell's
            // tyres, trees and posts of every shape (the tyre walls behind the gravel traps gone)
            const shared = BABYLON.VertexData.ExtractFromMesh(mesh);
            for (const [k, list] of cells) {
                const copy = new BABYLON.Mesh(`${mesh.name} @${k}`, scene), m = new Float32Array(list.length * 16);
                shared.applyToMesh(copy);
                list.forEach((i, j) => m.set(M.subarray(i * 16, i * 16 + 16), j * 16));
                copy.material = mesh.material;
                copy.thinInstanceSetBuffer("matrix", m, 16, true);
                if (part.tint) {
                    const c = new Float32Array(list.length * 4);
                    list.forEach((i, j) => c.set(C.subarray(i * 4, i * 4 + 4), j * 4));
                    copy.thinInstanceSetBuffer("color", c, 4, true);
                }
                copy.thinInstanceRefreshBoundingInfo(false);
                copy.layerMask = 0;
                copy.isPickable = false;
                copy.ccCell = true;
                copy.ccCast = mesh.ccCast;
                copy.ccAO = ao;
                copy.ccProbe = false;
                copy.freezeWorldMatrix();
                copy.doNotSyncBoundingInfo = true;
                out.meshes.push(copy);
                out.cells++;
            }
            mesh.ccCast = mesh.ccAO = false;  // (its copies do both)
        }
        out.instances += rows.length;
    }
    for (const part of track.parts) if (ground(part) === 1) own(part);
    for (const part of track.parts) if (ground(part) === 2) own(part);
    for (const m of out.meshes) {
        if (m.ccFar) m.ccAO = false;  // (out past where the shading in corners reaches)
        if (m.ccCast) out.casters.push(m);
    }
    return out;
}

// ---------- the circuit while racing (CHANGE 151) ----------
// How many pairs of the gantry's start lights are lit, countdown seconds before GO (null: not counting down):
// kart_scenery.start_lights, with the file's "lights" (none, then from the left one pair every step seconds from
// "from" seconds before GO, all out at GO)
export function startLights(countdown, lights) {
    const from = lights ? Number(lights.from) : 3.0, step = lights ? Number(lights.step) : 0.6;
    if (countdown === null || countdown === undefined || !(countdown > 0) || countdown > from) return 0;
    return Math.min(5, Math.floor((from - countdown) / step + 1e-9) + 1);
}

// each frame on ultra: the start lights (each pair's material's glow, the file's dark and lit) and the pond's ripples
// (kart_scenery.water_offset: the water's texture coordinates moved, as the window moves its texture). t: seconds
export function circuitFrame(c, t, countdown) {
    const lit = startLights(countdown, c.lights);
    if (lit !== c.lit && c.lamps.length) {
        c.lit = lit;
        const L = c.lights || {dark: [0.04, 0.002, 0.002], lit: [9.0, 0.015, 0.006]};
        c.lamps.forEach((m, k) => {
            const e = k < lit ? L.lit : L.dark;
            if (m) m.setVector3("emission", new BABYLON.Vector3(e[0], e[1], e[2]));
        });
    }
    for (const w of c.water) {
        const f = w.look.flows, metres = Number(w.look.metres) || 1;
        if (!f) continue;
        const k = Math.sin(2 * Math.PI * t / f.sway_period);
        const du = ((f.drift[0] * t + f.sway[0] * k) / metres) % 1, dv = ((f.drift[1] * t + f.sway[1] * k) / metres) % 1;  // (it tiles)
        for (let i = 0; i < w.uv.length; i += 2) { w.now[i] = w.uv[i] + du; w.now[i + 1] = w.uv[i + 1] + dv; }
        w.mesh.updateVerticesData(BABYLON.VertexBuffer.UVKind, w.now);
    }
}
