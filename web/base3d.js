// What every game's scene shares (CHANGE 130): one Babylon engine for the page, the graphics tiers, cached
// materials, name labels, the camera, and the game-to-Babylon coordinate rules.
//
// Coordinates: the games are z-up and right-handed (Panda3D); Babylon is y-up and left-handed. Swapping y and z
// maps one onto the other without a mirror image: game (x, y, z) -> Babylon (x, z, y); a game heading of t degrees
// (anticlockwise seen from above) is a Babylon rotation.y of -t; a game quaternion [w, x, y, z] is Babylon
// (-x, -z, -y, w).
//
// Tiers (the ladder every game shares, CHANGE 131: the app's own, engine/gfx_tiers.py, with "blocks" for its "basic"):
//   blocks  unlit flat colours, no shadows: the floor every machine can draw
//   low     the app's lighting (pbr.js: simplepbr's sums), the textures' colours, no shadows, no reflections
//   medium  + normal maps, the sky's reflections, a 1024 shadow map
//   high    + the occlusion maps, a 2048 shadow map, sharper textures at a slant
// Each tier also has a budget of pixels: the page draws at most that many, however fine the screen (a 4K laptop
// at 300% has 7.7 million at full sharpness; the app's 1280 x 720 window draws 0.9 million). The canvas's own
// multisampling smooths the edges on every tier.

/* global BABYLON */

import {Lighting} from "./pbr.js";

export const TIERS = ["blocks", "low", "medium", "high"];
export const TIER_SETTINGS = {
    blocks: {pbr: false, shadow: 0, normal: false, ibl: false, occlusion: false, aniso: 1, pixels: 1.0e6},
    low: {pbr: true, shadow: 0, normal: false, ibl: false, occlusion: false, aniso: 1, pixels: 1.1e6},
    medium: {pbr: true, shadow: 1024, normal: true, ibl: true, occlusion: false, aniso: 4, pixels: 1.6e6},
    high: {pbr: true, shadow: 2048, normal: true, ibl: true, occlusion: true, aniso: 8, pixels: 2.4e6},
};

// the sky's numbers (tex/manifest.json: the spherical harmonics make_textures.py worked out); app.js loads it
let skyData = null;
export function setSkyData(manifest) {
    skyData = manifest && manifest.sh ? manifest : null;
}

// how many pixels the canvas draws for each CSS pixel: the tier's budget over the page's size, never finer than
// the screen, and not much coarser than one for one
let shownTier = "medium";
export function resolutionFor(tier, cssW = window.innerWidth, cssH = window.innerHeight, dpr = window.devicePixelRatio || 1) {
    const budget = (TIER_SETTINGS[tier] || TIER_SETTINGS.medium).pixels;
    return Math.max(Math.min(dpr, 0.75), Math.min(dpr, Math.sqrt(budget / Math.max(1, cssW * cssH))));
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
export function pageEngine(canvas) {
    if (!sharedEngine) {
        sharedEngine = new BABYLON.Engine(canvas, true, {stencil: true, antialias: true}, true);
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

// A game's scene. Subclasses set this.look in their constructor before calling build(), and implement populate()
// (put the world and the players in: called again after a tier change rebuilds everything).
export class BaseScene {
    constructor(canvas, tier = "low", engine = null, look = {}) {
        this.canvas = canvas;
        this.tier = TIERS.includes(tier) ? tier : "low";
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
        const settings = this.settings = Object.assign({}, TIER_SETTINGS[this.tier]);
        if (!this.engine.webGLVersion || this.engine.webGLVersion < 2) settings.pbr = false;  // (the app's lighting needs WebGL 2)
        applyResolution(this.engine, this.tier);
        const scene = this.scene = new BABYLON.Scene(this.engine);
        scene.clearColor = new BABYLON.Color4(L.sky[0], L.sky[1], L.sky[2], 1);
        scene.ambientColor = new BABYLON.Color3(0.3, 0.3, 0.3);
        scene.skipPointerMovePicking = true;
        this.materials = {};
        this.lit = this.tier !== "blocks";
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
            if (!m.material || m.material.ccTile === undefined) continue;  // (labels and writing keep their own)
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

    // parts that never move, drawn together: one mesh per material (a few draws instead of hundreds)
    mergeStatic(meshes) {
        const groups = new Map();
        for (const m of meshes) {
            if (!m || m.isDisposed() || m.parent || !m.material || m.getClassName() !== "Mesh" || m.hasInstances) continue;
            const key = `${m.material.uniqueId}:${m.isVerticesDataPresent(BABYLON.VertexBuffer.ColorKind)}`;
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
            const key = `${m.material.uniqueId}:${m.isVerticesDataPresent(BABYLON.VertexBuffer.ColorKind)}`;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(m);
        }
        const out = [];
        for (const group of groups.values()) {
            for (const m of group) m.computeWorldMatrix(true);
            const merged = group.length > 1 ? BABYLON.Mesh.MergeMeshes(group, true, true) : group[0];
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

    setTier(tier) {
        if (!TIERS.includes(tier) || tier === this.tier) return;
        this.tier = tier;
        this.build();
    }

    // one material per look, cached: flat and unlit on blocks, the app's lighting (pbr.js) on the others.
    // rgb is the screen colour, rough and metal as the app's parts give them; opts.tex names the app's texture set
    // (paint, steel, tyre, diamond, hazard, concrete, tarmac, grass), opts.tile its repeats per metre and
    // opts.emission a glow given as the app gives it (linear, may be over 1)
    material(name, rgb, rough = 0.9, metal = 0.0, glow = 0, opts = {}) {
        const tex = opts.tex || "", tile = opts.tile || 1, emission = opts.emission || null;
        const key = `${name}:${rgb.join(",")}:${rough}:${metal}:${glow}:${tex}:${tile}:${emission}`;
        let m = this.materials[key];
        if (m) return m;
        if (this.lighting) {
            m = this.lighting.material(key, {rgb, rough, metal, glow, tex, emission});
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

    makeLabel(text, colour = "#ffffff", width = 2.4) {
        const lines = String(text).split("\n");
        const h = (lines.length > 1 ? 0.95 : 0.6) * width / 2.4;
        const plane = BABYLON.MeshBuilder.CreatePlane("label", {width, height: h}, this.scene);
        const th = lines.length > 1 ? 152 : 96;
        const tex = new BABYLON.DynamicTexture("labeltex", {width: 384, height: th}, this.scene, true);
        tex.hasAlpha = true;
        const ctx = tex.getContext();
        ctx.clearRect(0, 0, 384, th);
        ctx.fillStyle = "rgba(10,12,20,0.7)";
        ctx.fillRect(0, 0, 384, th);
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
    floorText(text, x, y, z, width, colour = "#f2c40d") {
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
            m.emissiveColor = new BABYLON.Color3(0.6, 0.6, 0.6);
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
