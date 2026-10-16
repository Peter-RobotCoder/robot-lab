// What every game's scene shares (CHANGE 130): one Babylon engine for the page, the graphics tiers, cached
// materials, name labels, the camera, and the game-to-Babylon coordinate rules.
//
// Coordinates: the games are z-up and right-handed (Panda3D); Babylon is y-up and left-handed. Swapping y and z
// maps one onto the other without a mirror image: game (x, y, z) -> Babylon (x, z, y); a game heading of t degrees
// (anticlockwise seen from above) is a Babylon rotation.y of -t; a game quaternion [w, x, y, z] is Babylon
// (-x, -z, -y, w).
//
// Tiers (the ladder every game shares, CHANGE 131: the app's own, engine/gfx_tiers.py, with "blocks" for its "basic"):
//   mesh    (CHANGE 144) black, and every triangle's edges in one line colour, the lines behind hidden
//   lines   (CHANGE 144) black, only the outlines and sharp creases in the line colour, a ground grid every 10 m
//   blocks  unlit flat colours, no shadows: the floor every machine can draw
//   low     the app's lighting (pbr.js: simplepbr's sums), the textures' colours, no shadows, no reflections
//   medium  + normal maps, the sky's reflections, a 1024 shadow map
//   high    + the occlusion maps, a 2048 shadow map, sharper textures at a slant
//   ultra   (CHANGE 144) + a 4096 soft shadow reaching further, and what each game adds for a strong graphics card
// Each tier also has a budget of pixels: the page draws at most that many, however fine the screen (a 4K laptop
// at 300% has 7.7 million at full sharpness; the app's 1280 x 720 window draws 0.9 million). The canvas's own
// multisampling smooths the edges on every tier.
// Each game says which tiers it draws (its scene's TIERS: Kart Lab all seven, Robot Lab and Fight Lab blocks to
// high); a tier it doesn't have is drawn as its nearest (gameTier: mesh and lines as blocks, ultra as high), so the
// page's choice can stay "lines" while Robot Lab draws blocks. mesh and lines are a look chosen by hand (or by the
// teacher), not a fallback: they need no WebGL 2 and Auto never steps into them or out of them.

/* global BABYLON */

import {Lighting} from "./pbr.js";

export const TIERS = ["mesh", "lines", "blocks", "low", "medium", "high", "ultra"];
export const GAME_TIERS = ["blocks", "low", "medium", "high"];  // (a game that doesn't say: Robot Lab, Fight Lab)
export const LINE_TIERS = ["mesh", "lines"];
export const TIER_SETTINGS = {
    mesh: {pbr: false, shadow: 0, normal: false, ibl: false, occlusion: false, aniso: 1, pixels: 1.0e6, wire: "all"},
    lines: {pbr: false, shadow: 0, normal: false, ibl: false, occlusion: false, aniso: 1, pixels: 1.0e6, wire: "outline"},
    blocks: {pbr: false, shadow: 0, normal: false, ibl: false, occlusion: false, aniso: 1, pixels: 1.0e6},
    low: {pbr: true, shadow: 0, normal: false, ibl: false, occlusion: false, aniso: 1, pixels: 1.1e6},
    medium: {pbr: true, shadow: 1024, normal: true, ibl: true, occlusion: false, aniso: 4, pixels: 1.6e6},
    high: {pbr: true, shadow: 2048, normal: true, ibl: true, occlusion: true, aniso: 8, pixels: 2.4e6},
    ultra: {pbr: true, shadow: 4096, normal: true, ibl: true, occlusion: true, aniso: 16, pixels: 3.7e6, ultra: true},
};

// the tier a game draws for the page's choice: the choice if the game has it, else the nearest it has below it
// (above the game's best: its best; below its floor: its floor)
export function gameTier(tier, tiers = GAME_TIERS) {
    if (tiers.includes(tier)) return tier;
    const i = TIERS.indexOf(tier);
    let best = tiers[0];
    for (const t of tiers) if (TIERS.indexOf(t) <= i) best = t;
    return best;
}

// the line tiers' colour (CHANGE 144): "#rrggbb", the phosphor green unless chosen (app.js keeps it on this computer
// and in a learner's profile as line_colour, the window's key). Changed while drawn: the lines recoloured at once
export const LINE_COLOURS = [["green", "#33ff66"], ["amber", "#ffb000"], ["cyan", "#33e0ff"], ["white", "#f0f0f0"], ["magenta", "#ff4dd2"]];
let lineColour = "#33ff66";
export function cleanColour(c) {
    return typeof c === "string" && /^#[0-9a-fA-F]{6}$/.test(c) ? c.toLowerCase() : null;
}
export function getLineColour() { return lineColour; }
export function setLineColour(c, scene = null) {
    lineColour = cleanColour(c) || lineColour;
    if (scene && scene.recolourLines) scene.recolourLines();
    return lineColour;
}

// the sky's numbers (tex/manifest.json: the spherical harmonics make_textures.py worked out); app.js loads it
let skyData = null;
export function setSkyData(manifest) {
    skyData = manifest && manifest.sh ? manifest : null;
}

// The parts of a tier the Graphics tab changes one by one (CHANGE 139), over the tier's own: shadow (0, 512, 1024,
// 2048, 4096), normal, occlusion, ibl (the sky's reflections), aniso (1, 2, 4, 8, 16) and pixels (a budget; SCREEN:
// as fine as the screen). Picking a tier clears them. A class maximum (the teacher's gfx_max, on a learner's page)
// caps every part at that tier's own, whatever was chosen.
export const SCREEN = 1e9;  // (a number, not Infinity: the parts are kept as JSON)
export const PARTS = {shadow: [0, 512, 1024, 2048, 4096], aniso: [1, 2, 4, 8, 16], pixels: [0.6e6, 1.0e6, 1.1e6, 1.6e6, 2.4e6, 3.7e6, SCREEN]};
export function cleanParts(parts) {  // (what was kept on this computer: only the parts there are, of the right kind)
    const out = {};
    for (const [k, v] of Object.entries(parts && typeof parts === "object" ? parts : {})) {
        if (PARTS[k] ? PARTS[k].includes(v) : ["normal", "occlusion", "ibl"].includes(k) && typeof v === "boolean") out[k] = v;
    }
    return out;
}
let tweaks = {}, classMax = null;
export function setGraphics(parts = {}, cap = null) {
    tweaks = Object.assign({}, parts);
    classMax = TIERS.includes(cap) ? cap : null;
}

export function cappedTier(tier, cap = classMax) {
    return cap && TIERS.indexOf(tier) > TIERS.indexOf(cap) ? cap : tier;
}

// what a tier draws with: its own settings, the parts changed by hand, then the class maximum's
export function tierSettings(tier) {
    const s = Object.assign({}, TIER_SETTINGS[tier] || TIER_SETTINGS.medium, tweaks);
    if (classMax) {
        const c = TIER_SETTINGS[classMax];
        for (const k of ["shadow", "aniso", "pixels"]) s[k] = Math.min(s[k], c[k]);
        for (const k of ["pbr", "normal", "ibl", "occlusion"]) s[k] = s[k] && c[k];
        s.ultra = !!(s.ultra && c.ultra);
    }
    return s;
}

// how many pixels the canvas draws for each CSS pixel: the tier's budget over the page's size, never finer than
// the screen, and not much coarser than one for one
let shownTier = "medium";
export function resolutionFor(tier, cssW = window.innerWidth, cssH = window.innerHeight, dpr = window.devicePixelRatio || 1) {
    const budget = tierSettings(tier).pixels;
    return Math.max(Math.min(dpr, 0.75), Math.min(dpr, Math.sqrt(budget / Math.max(1, cssW * cssH))));
}

// Auto (CHANGE 131, 139): fed once a second with the frame rate and the frames that took over MISS_MS. Three
// seconds under 28 frames a second: one tier down, and the tier stepped down from is held off (10 minutes, twice as
// long each time it fails again, up to a day). UP_SECS seconds in a row with headroom (with vsync the frame time
// sits at the screen's rate, so headroom is: no more than one frame missed a second, at 45 a second or more): one
// tier up, never past the class maximum, a tier held off, or one above the best this computer has run cleanly
// (CLEAN_SECS of headroom at it). store is what is kept on this computer: {best, failed: {tier: [until, times]}}.
// (CHANGE 144) Never down past blocks, and never into or out of mesh and lines (chosen by hand, not a fallback); up
// into ultra by the same rules, but never past the best tier the game draws (top).
export class AutoTier {
    static SLOW_FPS = 28; static SLOW_SECS = 3; static MISS_MS = 25; static UP_FPS = 45; static UP_SECS = 25;
    static CLEAN_SECS = 10; static GAP_MS = 8000; static HOLD_MS = 600000; static HOLD_MAX = 86400000;

    constructor(store = {}) {
        this.store = {best: TIERS.includes(store.best) ? store.best : null, failed: Object.assign({}, store.failed || {})};
        this.slow = this.good = 0;
        this.at = -Infinity;  // (the last change: the next waits GAP_MS)
    }

    // fps, missed: this second's; tier: the one drawn; cap: the class maximum; active: a game is drawn and seen;
    // now: performance.now(), wall: Date.now() (the holds are kept on this computer, so in the clock's time); top:
    // the best tier the game draws. Returns {tier, up} when the tier should change, else null
    second({fps, missed = 0, tier, cap = null, active = true, now = performance.now(), wall = Date.now(), top = "ultra"}) {
        if (!active || !fps || LINE_TIERS.includes(tier)) { this.slow = this.good = 0; return null; }
        const C = AutoTier, i = TIERS.indexOf(tier);
        this.slow = fps < C.SLOW_FPS ? this.slow + 1 : 0;
        this.good = fps >= C.UP_FPS && missed <= 1 ? this.good + 1 : 0;
        if (this.good >= C.CLEAN_SECS && TIERS.indexOf(this.store.best) < i) this.store.best = tier;
        if (now - this.at < C.GAP_MS) return null;
        if (this.slow >= C.SLOW_SECS && i > TIERS.indexOf("blocks")) {
            const [, times] = this.store.failed[tier] || [0, 0];
            this.store.failed[tier] = [wall + Math.min(C.HOLD_MAX, C.HOLD_MS * 2 ** times), times + 1];
            return this.change(TIERS[i - 1], false, now);
        }
        const last = TIERS.includes(top) ? TIERS.indexOf(top) : TIERS.length - 1;
        if (this.good >= C.UP_SECS && i < last) {
            const up = TIERS[i + 1], held = this.store.failed[up];
            const ceiling = Math.min(cap ? TIERS.indexOf(cap) : last, last, TIERS.indexOf(this.store.best) + 1);
            if (i + 1 <= ceiling && !(held && held[0] > wall)) return this.change(up, true, now);
            this.good = 0;  // (not now: look again in another UP_SECS)
        }
        return null;
    }

    change(tier, up, now) {
        this.at = now;
        this.slow = this.good = 0;
        return {tier, up};
    }
}

export function applyResolution(engine, tier = shownTier) {
    shownTier = tier;
    engine.setHardwareScalingLevel(1 / resolutionFor(tier));
    engine.resize();
}

export function v3(x, y, z) {  // a game point to a Babylon vector
    return new BABYLON.Vector3(x, z, y);
}

export function col(rgb) {
    return new BABYLON.Color3(rgb[0], rgb[1], rgb[2]);
}

export function rgb255(c, fallback = [200, 200, 200]) {
    const v = Array.isArray(c) && c.length >= 3 ? c : fallback;
    return [v[0] / 255, v[1] / 255, v[2] / 255];
}

export function gameQuat(q) {  // [w, x, y, z] (Panda) -> a Babylon quaternion
    return new BABYLON.Quaternion(-q[1], -q[3], -q[2], q[0]);
}

export function slerpQ(a, b, f) {  // [w, x, y, z] arrays, the short way round
    let dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
    const bb = dot < 0 ? b.map(v => -v) : b;
    dot = Math.abs(dot);
    if (dot > 0.9995) {
        const r = a.map((v, i) => v + (bb[i] - v) * f);
        const n = Math.hypot(...r) || 1;
        return r.map(v => v / n);
    }
    const th = Math.acos(Math.min(1, dot)), s = Math.sin(th);
    const wa = Math.sin((1 - f) * th) / s, wb = Math.sin(f * th) / s;
    return a.map((v, i) => v * wa + bb[i] * wb);
}

export function lerp(a, b, f) {
    return a + (b - a) * f;
}

export function lerpAngle(a, b, t) {  // radians
    const d = ((b - a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    return a + d * t;
}

export function lerpDeg(a, b, f) {
    const d = ((b - a + 180) % 360 + 360) % 360 - 180;
    return a + d * f;
}

export function mulberry(seed) {  // a small seeded random, so scenery stands where it stood last time
    let a = seed >>> 0;
    return () => {
        a = (a + 0x6D2B79F5) >>> 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

// the normals of a mesh whose faces mostly look up (a road, a lawn): computed, then turned over as one if the
// winding left them pointing down, so the sun lights the top
export function upwardNormals(pos, idx) {
    const norm = [];
    BABYLON.VertexData.ComputeNormals(pos, idx, norm);
    let up = 0;
    for (let i = 1; i < norm.length; i += 3) up += norm[i];
    if (up < 0) for (let i = 0; i < norm.length; i++) norm[i] = -norm[i];
    return norm;
}

let sharedEngine = null;
export function pageEngine(canvas, antialias = true) {
    if (!sharedEngine) {
        // alpha false: the canvas is opaque, so the page behind can never show through the drawing (CHANGE 132: a
        // material that wrote alpha 0 made every lit tier black in a real window, though headless pictures were fine).
        // antialias: the canvas's multisampling, fixed when the page opens (CHANGE 139: the Graphics tab's switch)
        sharedEngine = new BABYLON.Engine(canvas, antialias, {stencil: true, antialias, alpha: false}, true);
        sharedEngine.ccKeep = {scene: new BABYLON.Scene(sharedEngine), textures: {}};  // (pbr.js: pictures kept loaded)
        window.addEventListener("resize", () => applyResolution(sharedEngine));
        applyResolution(sharedEngine);
    }
    return sharedEngine;
}

export function engineInfo(engine) {
    const gl = engine._gl;
    let renderer = "";
    try {
        const ext = gl.getExtension("WEBGL_debug_renderer_info");
        renderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    } catch (e) { renderer = "?"; }
    return {webgl: engine.webGLVersion, renderer, webgpu: !!navigator.gpu,
            width: engine.getRenderWidth(), height: engine.getRenderHeight(), ratio: 1 / engine.getHardwareScalingLevel()};
}

// what the app's scenes are lit by, when a game doesn't say (each game passes its own: its gfx module's lights)
const PBR_LOOK = {background: [0.3, 0.5, 0.9], exposure: 0.55, ambient: [0.22, 0.25, 0.32], sky: "sky",
                  sun: {colour: [2.6, 2.45, 2.2], offset: [30, -45, 45], film: 40, near: 50, far: 90, bias: 0.0015}, spots: []};

// the line tiers' shader (CHANGE 144): one colour, faded to the black behind between two distances (as the window's
// black fog: mesh from 15 m to 140 m, lines and the grid from 60 m to 380 m), as on an old vector screen
const LINES_VERT = `
precision highp float;
attribute vec3 position;
uniform mat4 world;
uniform mat4 viewProjection;
uniform vec3 cameraPosition;
varying float vDist;
void main(void) {
    vec4 wp = world * vec4(position, 1.0);
    vDist = distance(wp.xyz, cameraPosition);
    gl_Position = viewProjection * wp;
}`;
const LINES_FRAG = `
precision highp float;
uniform vec4 color;
uniform vec2 fade;
varying float vDist;
void main(void) {
    gl_FragColor = vec4(color.rgb * (1.0 - smoothstep(fade.x, fade.y, vDist)), 1.0);
}`;
const COS_CREASE = Math.cos(30 * Math.PI / 180);  // (lines: a crease is drawn where two faces meet at more than 30 degrees)

// A game's scene. Subclasses set this.look in their constructor before calling build(), and implement populate()
// (put the world and the players in: called again after a tier change rebuilds everything).
export class BaseScene {
    static TIERS = GAME_TIERS;  // (the tiers this game draws: CHANGE 144)

    constructor(canvas, tier = "low", engine = null, look = {}) {
        this.canvas = canvas;
        this.tier = gameTier(TIERS.includes(tier) ? tier : "low", this.constructor.TIERS);
        this.engine = engine || pageEngine(canvas);
        this.look = Object.assign({sky: [0.53, 0.72, 0.95], fog: [0.7, 0.8, 0.95], fogDensity: 0.0018,
                                   sunDir: [-0.45, -0.65, 0.6], shadowSize: 90, ground: [0.35, 0.4, 0.3],
                                   radius: 60, target: [0, 0, 0], hemi: 0.55, sun: 1.4}, look);
        this.look.pbr = Object.assign({}, PBR_LOOK, look.pbr || {});
        this.look.pbr.sun = Object.assign({}, PBR_LOOK.sun, (look.pbr || {}).sun || {});
    }

    build() {
        const old = this.scene;
        if (old) old.dispose();
        const L = this.look;
        const settings = this.settings = tierSettings(this.tier);  // (with the parts changed by hand: CHANGE 139)
        if (!this.engine.webGLVersion || this.engine.webGLVersion < 2) settings.pbr = false;  // (the app's lighting needs WebGL 2)
        applyResolution(this.engine, this.tier);
        const scene = this.scene = new BABYLON.Scene(this.engine);
        scene.clearColor = new BABYLON.Color4(L.sky[0], L.sky[1], L.sky[2], 1);
        scene.ambientColor = new BABYLON.Color3(0.3, 0.3, 0.3);
        scene.skipPointerMovePicking = true;
        this.materials = {};
        // (CHANGE 144) the line tiers: black behind, every mesh filled black (wireFill) and its edges drawn as lines
        this.wire = settings.wire || null;
        this.lineMats = [];
        if (this.wire) scene.clearColor = new BABYLON.Color4(0, 0, 0, 1);
        this.lit = !this.wire && this.tier !== "blocks";
        this.pbr = settings.pbr;
        // the labels and floor writing (Babylon's own materials): one even light from everywhere on blocks, so every
        // face is its flat colour; a sky and a sun on the others. Everything else on low and up is pbr.js's.
        const hemi = new BABYLON.HemisphericLight("sky", new BABYLON.Vector3(0, 1, 0), scene);
        hemi.intensity = this.lit ? L.hemi : 1.0;
        hemi.groundColor = this.lit ? col(L.ground) : new BABYLON.Color3(1, 1, 1);
        const sun = this.sun = new BABYLON.DirectionalLight("sun", new BABYLON.Vector3(...L.sunDir), scene);
        sun.intensity = this.lit ? L.sun : 0.0;
        sun.position = new BABYLON.Vector3(60, 90, -80);
        this.shadows = null;
        this.lighting = null;
        // meshes get texture coordinates in metres (as engine/rw_mesh.py makes them) before they are first drawn
        this.needUV = [];
        scene.onNewMeshAddedObservable.add(m => this.needUV.push(m));
        scene.onBeforeRenderObservable.add(() => this.worldUVs());
        const cam = this.camera = new BABYLON.ArcRotateCamera("cam", -Math.PI / 2, 1.05, L.radius, v3(...L.target), scene);
        cam.lowerRadiusLimit = 2;
        cam.upperRadiusLimit = 400;
        cam.upperBetaLimit = 1.5;
        cam.minZ = 0.1;
        cam.maxZ = 1200;
        cam.wheelDeltaPercentage = 0.02;
        cam.attachControl(this.canvas, true);
        if (this.pbr) {
            const P = L.pbr;
            const sky = skyData && skyData.sh ? skyData.sh[P.sky] : null;
            this.lighting = new Lighting(scene, P, sky ? settings : Object.assign({}, settings, {ibl: false}), sky);
            const bg = this.lighting.background();
            scene.clearColor = new BABYLON.Color4(bg[0], bg[1], bg[2], 1);
            if (this.lighting.rtt) this.shadows = {addShadowCaster: m => this.lighting.addCaster(m)};
        }
        this.populate(!!old);
    }

    // the spotlights after the key light (Robot Lab's towers, Fight Lab's rings): game positions
    setSpots(spots) {
        this.look.pbr.spots = spots;
        if (this.lighting) {
            const before = this.lighting.lights.count;
            this.lighting.setLights(spots);
            if (this.lighting.lights.count !== before) this.build();  // (the shader is made for a number of lights)
        }
    }

    // texture coordinates in metres x the material's tile on every new mesh: each vertex projected on the plane its
    // normal faces most, so a texture is the same size on every part (engine/rw_mesh.py's rule)
    worldUVs() {
        if (!this.needUV.length) return;
        const list = this.needUV;
        this.needUV = [];
        for (const m of list) {
            if (m.isDisposed() || m.getClassName() === "InstancedMesh" || !m.getTotalVertices || !m.getTotalVertices()) continue;
            if (!m.material || m.material.ccTile === undefined || m.ccOwnUV) continue;  // (labels, writing and a model with its own keep theirs)
            const pos = m.getVerticesData(BABYLON.VertexBuffer.PositionKind), nor = m.getVerticesData(BABYLON.VertexBuffer.NormalKind);
            if (!pos || !nor) continue;
            const tile = (m.material && m.material.ccTile) || 1, uv = new Array(pos.length / 3 * 2);
            for (let i = 0, j = 0; i < pos.length; i += 3, j += 2) {
                const ax = Math.abs(nor[i]), ay = Math.abs(nor[i + 1]), az = Math.abs(nor[i + 2]);
                if (ay >= ax && ay >= az) { uv[j] = pos[i] * tile; uv[j + 1] = pos[i + 2] * tile; }
                else if (ax >= az) { uv[j] = pos[i + 2] * tile; uv[j + 1] = pos[i + 1] * tile; }
                else { uv[j] = pos[i] * tile; uv[j + 1] = pos[i + 1] * tile; }
            }
            m.setVerticesData(BABYLON.VertexBuffer.UVKind, uv, false);
        }
    }

    // parts that never move, drawn together: one mesh per material (a few draws instead of hundreds; meshes with and
    // without texture coordinates apart, as Babylon only merges alike: on the line tiers every mesh has one material)
    mergeStatic(meshes) {
        const groups = new Map();
        for (const m of meshes) {
            if (!m || m.isDisposed() || m.parent || !m.material || m.getClassName() !== "Mesh" || m.hasInstances) continue;
            const key = `${m.material.uniqueId}:${m.isVerticesDataPresent(BABYLON.VertexBuffer.ColorKind)}:${m.isVerticesDataPresent(BABYLON.VertexBuffer.UVKind)}`;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(m);
        }
        const out = [];
        for (const group of groups.values()) {
            if (group.length < 2) { out.push(...group); continue; }
            const merged = BABYLON.Mesh.MergeMeshes(group, true, true);
            if (merged) { merged.freezeWorldMatrix(); out.push(merged); }
        }
        return out;
    }

    // a moving thing's parts (a kart's body, a saw's blade) drawn together: one mesh per material under parent
    mergeParts(parts, parent) {
        parent.computeWorldMatrix(true);
        const toLocal = parent.getWorldMatrix().clone().invert();  // (merged meshes come out in the world's frame)
        const groups = new Map();
        for (const m of parts) {
            if (!m || m.getClassName() !== "Mesh" || !m.material) continue;
            const key = `${m.material.uniqueId}:${m.isVerticesDataPresent(BABYLON.VertexBuffer.ColorKind)}:${m.isVerticesDataPresent(BABYLON.VertexBuffer.UVKind)}`;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(m);
        }
        const out = [];
        for (const group of groups.values()) {
            for (const m of group) m.computeWorldMatrix(true);
            const merged = group.length > 1 ? BABYLON.Mesh.MergeMeshes(group, true, true) : group[0];
            if (merged && group.length > 1 && group.every(g => g.ccOwnUV)) merged.ccOwnUV = true;
            if (!merged) continue;
            if (group.length > 1) {
                merged.bakeTransformIntoVertices(toLocal);
                merged.parent = parent;
            }
            out.push(merged);
        }
        return out;
    }

    populate() { /* the subclass's world */ }

    setTier(tier, again = false) {  // (again: the same tier with other parts, built afresh)
        if (!TIERS.includes(tier)) return;
        tier = gameTier(tier, this.constructor.TIERS);  // (one this game doesn't draw: its nearest, CHANGE 144)
        if (tier === this.tier && !again) return;
        this.tier = tier;
        this.build();
    }

    // ---------- the line tiers (CHANGE 144) ----------
    // every mesh's faces in black, a little behind where they are (the polygon offset), so they hide the lines behind
    // them while the lines on their own edges still win the depth test
    wireFill() {
        if (this.materials.wirefill) return this.materials.wirefill;
        const m = new BABYLON.StandardMaterial("wirefill", this.scene);
        m.diffuseColor = new BABYLON.Color3(0, 0, 0);
        m.specularColor = new BABYLON.Color3(0, 0, 0);
        m.emissiveColor = new BABYLON.Color3(0, 0, 0);
        m.disableLighting = true;
        m.backFaceCulling = false;
        m.zOffset = 1;
        m.zOffsetUnits = 2;
        m.ccTile = 1;
        this.materials.wirefill = m;
        return m;
    }

    // a line material: the line colour times dim (the grid is dimmer), fading out from near to far (metres)
    lineMaterial(name, dim = 1, near = 60, far = 380) {
        if (this.materials["lines:" + name]) return this.materials["lines:" + name];
        const m = this.materials["lines:" + name] = new BABYLON.ShaderMaterial("cclines" + name, this.scene, {vertexSource: LINES_VERT, fragmentSource: LINES_FRAG}, {
            attributes: ["position"], uniforms: ["world", "viewProjection", "cameraPosition", "color", "fade"]});
        m.fillMode = BABYLON.Material.LineListDrawMode;
        m.backFaceCulling = false;
        m.setVector2("fade", new BABYLON.Vector2(near, far));
        m.ccFar = far;
        m.ccDim = dim;
        this.lineMats.push(m);
        this.paintLine(m);
        return m;
    }

    paintLine(m) {
        const c = BABYLON.Color3.FromHexString(lineColour);
        m.setColor4("color", new BABYLON.Color4(c.r * m.ccDim, c.g * m.ccDim, c.b * m.ccDim, 1));
    }

    recolourLines() {  // (the line colour changed: at once, nothing rebuilt)
        for (const m of this.lineMats || []) this.paintLine(m);
    }

    // The edges of some meshes as one list of line pairs, in the frame of `frame` (a node the lines will be parented
    // to) or the world's. mode "all": every triangle's edges; "outline": the edges on one face only (a boundary),
    // where two faces meet at more than 30 degrees, or where the colour changes (a kerb's blocks). Vertices in the
    // same place (to the millimetre) are one, so a box's or a ribbon's separate corners join up. O(n): a Map of edges
    edgeLines(meshes, mode, frame = null) {
        const pos = [], weld = new Map(), edges = new Map(), out = [];
        const toFrame = frame ? (frame.computeWorldMatrix(true), frame.getWorldMatrix().clone().invert()) : null;
        const v = new BABYLON.Vector3();
        for (const m of meshes) {
            if (!m || m.isDisposed() || !m.getTotalVertices || !m.getTotalVertices()) continue;
            const p = m.getVerticesData(BABYLON.VertexBuffer.PositionKind), ix = m.getIndices();
            if (!p || !ix) continue;
            const cols = mode === "outline" ? m.getVerticesData(BABYLON.VertexBuffer.ColorKind) : null;
            m.computeWorldMatrix(true);
            const M = toFrame ? m.getWorldMatrix().multiply(toFrame) : m.getWorldMatrix();
            const ids = new Int32Array(p.length / 3);
            for (let i = 0, j = 0; i < p.length; i += 3, j++) {
                BABYLON.Vector3.TransformCoordinatesFromFloatsToRef(p[i], p[i + 1], p[i + 2], M, v);
                const key = `${Math.round(v.x * 1000)},${Math.round(v.y * 1000)},${Math.round(v.z * 1000)}`;
                let id = weld.get(key);
                if (id === undefined) { id = pos.length / 3; weld.set(key, id); pos.push(v.x, v.y, v.z); }
                ids[j] = id;
            }
            for (let t = 0; t < ix.length; t += 3) {
                const a = ids[ix[t]], b = ids[ix[t + 1]], c = ids[ix[t + 2]];
                if (a === b || b === c || a === c) continue;
                let nx = 0, ny = 0, nz = 0, colour = 0;
                if (mode === "outline") {
                    const ux = pos[b * 3] - pos[a * 3], uy = pos[b * 3 + 1] - pos[a * 3 + 1], uz = pos[b * 3 + 2] - pos[a * 3 + 2];
                    const wx = pos[c * 3] - pos[a * 3], wy = pos[c * 3 + 1] - pos[a * 3 + 1], wz = pos[c * 3 + 2] - pos[a * 3 + 2];
                    nx = uy * wz - uz * wy; ny = uz * wx - ux * wz; nz = ux * wy - uy * wx;
                    const l = Math.hypot(nx, ny, nz) || 1;
                    nx /= l; ny /= l; nz /= l;
                    if (cols) { const k = ix[t] * 4; colour = Math.round(cols[k] * 50) * 2601 + Math.round(cols[k + 1] * 50) * 51 + Math.round(cols[k + 2] * 50); }
                }
                for (const [e0, e1] of [[a, b], [b, c], [c, a]]) {
                    const key = e0 < e1 ? e0 * 4194304 + e1 : e1 * 4194304 + e0;
                    const e = edges.get(key);
                    if (!e) { edges.set(key, mode === "outline" ? {nx, ny, nz, colour, n: 1, sharp: false} : 1); continue; }
                    if (mode !== "outline") continue;
                    e.n++;
                    // (the same face seen from the other side, as a double-sided sheet: not a crease)
                    const d = Math.abs(e.nx * nx + e.ny * ny + e.nz * nz);
                    if (d < COS_CREASE || e.colour !== colour) e.sharp = true;
                }
            }
        }
        for (const [key, e] of edges) {
            if (mode === "outline" && !(e.n === 1 || e.sharp)) continue;
            out.push(Math.floor(key / 4194304), key % 4194304);
        }
        return {pos, idx: out};
    }

    // a lines mesh from edgeLines' lists (or any pairs), under parent, in material mat
    linesMesh(name, lists, mat, parent = null) {
        if (!lists.idx.length) return null;
        const m = new BABYLON.Mesh(name, this.scene);
        const vd = new BABYLON.VertexData();
        vd.positions = lists.pos;
        vd.indices = lists.idx;
        vd.applyToMesh(m);
        m.material = mat;
        m.isPickable = false;
        if (parent) m.parent = parent;
        else m.freezeWorldMatrix();
        this.lineCount = (this.lineCount || 0) + lists.idx.length / 2;
        return m;
    }

    // lines that never move (the track's, the grid) as tiles 40 m across, so those off the screen aren't drawn
    // (Babylon's own culling) nor those past where the material fades them out (a level of detail of nothing)
    staticLines(name, lists, mat) {
        const T = 40, tiles = new Map(), P = lists.pos, out = [];
        for (let i = 0; i < lists.idx.length; i += 2) {
            const a = lists.idx[i] * 3, b = lists.idx[i + 1] * 3;
            const key = Math.floor((P[a] + P[b]) / 2 / T) + "," + Math.floor((P[a + 2] + P[b + 2]) / 2 / T);
            if (!tiles.has(key)) tiles.set(key, {pos: [], idx: [], at: new Map()});
            const t = tiles.get(key);
            for (const v of [a, b]) {
                let j = t.at.get(v);
                if (j === undefined) { j = t.pos.length / 3; t.at.set(v, j); t.pos.push(P[v], P[v + 1], P[v + 2]); }
                t.idx.push(j);
            }
        }
        for (const t of tiles.values()) {
            const m = this.linesMesh(name, t, mat);
            if (!m) continue;
            m.addLODLevel(mat.ccFar + T, null);
            out.push(m);
        }
        return out;
    }

    // one material per look, cached: flat and unlit on blocks, the app's lighting (pbr.js) on the others.
    // rgb is the screen colour, rough and metal as the app's parts give them; opts.tex names the app's texture set
    // (paint, steel, tyre, diamond, hazard, concrete, tarmac, grass), opts.tile its repeats per metre and
    // opts.emission a glow given as the app gives it (linear, may be over 1). On the line tiers: black (wireFill).
    // opts.clearcoat (0 to 1) and opts.probe (CHANGE 144, ultra): a glossy coat over the paint, and the world's
    // reflection (the scene's probe) in it
    material(name, rgb, rough = 0.9, metal = 0.0, glow = 0, opts = {}) {
        if (this.wire) return this.wireFill();
        const tex = opts.tex || "", tile = opts.tile || 1, emission = opts.emission || null;
        const coat = this.lighting && this.lighting.tier.ultra ? `${opts.clearcoat || 0}:${!!opts.probe}` : "";
        const key = `${name}:${rgb.join(",")}:${rough}:${metal}:${glow}:${tex}:${tile}:${emission}${coat}`;
        let m = this.materials[key];
        if (m) return m;
        if (this.lighting) {
            m = this.lighting.material(key, {rgb, rough, metal, glow, tex, emission, clearcoat: opts.clearcoat || 0, probe: !!opts.probe});
        } else {
            m = new BABYLON.StandardMaterial(key, this.scene);
            m.diffuseColor = col(rgb);
            m.specularColor = new BABYLON.Color3(0, 0, 0);
            if (glow) m.emissiveColor = col(rgb).scale(Math.min(1, glow));
            if (emission) m.emissiveColor = col(emission.map(c => Math.min(1, c)));
            m.backFaceCulling = false;
        }
        m.ccTile = tile;
        this.materials[key] = m;
        return m;
    }

    // change a glowing material's glow while running (a pit's lights, a lamp that blinks): linear, as the app's
    setGlow(m, emission) {
        if (!m) return;
        if (this.lighting && m.setVector3) m.setVector3("emission", new BABYLON.Vector3(emission[0], emission[1], emission[2]));
        else if (m.emissiveColor) m.emissiveColor = col(emission.map(c => Math.min(1, c)));
    }

    glass(name, rgb, alpha, glow = 0) {
        if (this.wire) return this.wireFill();
        const key = `glass:${name}`;
        if (this.materials[key]) return this.materials[key];
        let m;
        if (this.lighting) {
            m = this.lighting.material(key, {rgb, rough: 0.1, metal: 0, glow, alpha});
        } else {
            m = new BABYLON.StandardMaterial(key, this.scene);
            m.diffuseColor = col(rgb);
            if (glow) m.emissiveColor = col(rgb).scale(Math.min(1, glow));
            m.alpha = alpha;
            m.backFaceCulling = false;
        }
        this.materials[key] = m;
        return m;
    }

    // simple shapes in game coordinates (centre and half extents, z up), parented and coloured
    box(parent, hx, hy, hz, mat, x = 0, y = 0, z = 0, name = "box") {
        const m = BABYLON.MeshBuilder.CreateBox(name, {width: hx * 2, depth: hy * 2, height: hz * 2}, this.scene);
        m.material = mat;
        m.position = v3(x, y, z);
        if (parent) m.parent = parent;
        return m;
    }

    // a cylinder along the game's axis ("x", "y" or "z"), radius r (rTop for a cone), half length h
    cyl(parent, r, h, axis, mat, x = 0, y = 0, z = 0, rTop = null, tess = 14, name = "cyl") {
        const m = BABYLON.MeshBuilder.CreateCylinder(name, {height: h * 2, diameterBottom: r * 2,
            diameterTop: (rTop === null ? r : rTop) * 2, tessellation: tess}, this.scene);
        m.material = mat;
        // Babylon's cylinder stands along its y (= the game's z); turn it onto the game's x or y
        if (axis === "x") m.rotation.z = Math.PI / 2;
        else if (axis === "y") m.rotation.x = Math.PI / 2;
        m.position = v3(x, y, z);
        if (parent) m.parent = parent;
        return m;
    }

    sphere(parent, r, mat, x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1, seg = 10, name = "ball") {
        const m = BABYLON.MeshBuilder.CreateSphere(name, {diameter: r * 2, segments: seg}, this.scene);
        m.material = mat;
        m.position = v3(x, y, z);
        m.scaling = new BABYLON.Vector3(sx, sz, sy);
        if (parent) m.parent = parent;
        return m;
    }

    // a name over a player, always facing the camera: on a dark plate (Kart Lab and Fight Lab, as their windows draw
    // them) or, with plate false, white words with a shadow (Robot Lab's window)
    makeLabel(text, colour = "#ffffff", width = 2.4, plate = true) {
        const lines = String(text).split("\n");
        const h = (lines.length > 1 ? 0.95 : 0.6) * width / 2.4;
        const plane = BABYLON.MeshBuilder.CreatePlane("label", {width, height: h}, this.scene);
        const th = lines.length > 1 ? 152 : 96;
        const tex = new BABYLON.DynamicTexture("labeltex", {width: 384, height: th}, this.scene, true);
        tex.hasAlpha = true;
        const ctx = tex.getContext();
        ctx.clearRect(0, 0, 384, th);
        if (plate) {
            ctx.fillStyle = "rgba(10,12,20,0.7)";
            ctx.fillRect(0, 0, 384, th);
        } else {
            ctx.shadowColor = "rgba(0,0,0,0.9)";
            ctx.shadowBlur = 8;
        }
        lines.forEach((line, i) => tex.drawText(line, null, lines.length > 1 ? 62 + i * 64 : 68,
                                                 `bold ${i ? 42 : 52}px sans-serif`, colour, null, true, i === lines.length - 1));
        const m = new BABYLON.StandardMaterial("labelmat", this.scene);
        m.diffuseTexture = tex;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.disableLighting = true;
        m.backFaceCulling = false;
        m.useAlphaFromDiffuseTexture = true;
        plane.material = m;
        plane.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
        plane.isPickable = false;
        return plane;
    }

    // a flat text decal lying on the floor (game z up)
    floorText(text, x, y, z, width, colour = "#f2c40d", paint = 0.6) {
        const plane = BABYLON.MeshBuilder.CreatePlane("floortext", {width, height: width / 4}, this.scene);
        const tex = new BABYLON.DynamicTexture("floortex", {width: 1024, height: 256}, this.scene, true);
        tex.hasAlpha = true;
        tex.getContext().clearRect(0, 0, 1024, 256);
        tex.drawText(text, null, 180, "bold 150px sans-serif", colour, null, true, true);
        const m = new BABYLON.StandardMaterial("floortextmat", this.scene);
        m.diffuseTexture = tex;
        m.useAlphaFromDiffuseTexture = true;
        m.emissiveColor = new BABYLON.Color3(0.4, 0.4, 0.4);
        if (this.lighting) {  // (paint in a dim hall, as the app draws it: not lit by Babylon's brighter lights)
            m.disableLighting = true;
            m.emissiveColor = new BABYLON.Color3(paint, paint, paint);
        }
        m.backFaceCulling = false;
        plane.material = m;
        plane.rotation.x = Math.PI / 2;
        plane.position = v3(x, y, z);
        plane.isPickable = false;
        return plane;
    }

    shadowCast(meshes) {
        if (!this.shadows) return;
        for (const m of meshes) if (m && m.getTotalVertices && m.getTotalVertices() > 0) this.shadows.addShadowCaster(m);
    }

    followSun() {  // the key light's shadow covers the ground round what the camera looks at
        if (this.lighting) {
            const t = this.camera.target;
            this.lighting.follow([t.x, t.y, t.z]);
        }
    }

    render() {
        this.scene.render();
    }

    gpuInfo() {
        return engineInfo(this.engine);
    }

    drawCalls() {  // (the Graphics tab: how many meshes were drawn in the last frame)
        return this.scene ? this.scene.getActiveMeshes().length : 0;
    }

    dispose() {
        if (this.scene) this.scene.dispose();
        this.scene = null;
    }
}
