// What every game's scene shares (CHANGE 130): one Babylon engine for the page, the graphics tiers, cached
// materials, name labels, the camera, and the game-to-Babylon coordinate rules.
//
// Coordinates: the games are z-up and right-handed (Panda3D); Babylon is y-up and left-handed. Swapping y and z
// maps one onto the other without a mirror image: game (x, y, z) -> Babylon (x, z, y); a game heading of t degrees
// (anticlockwise seen from above) is a Babylon rotation.y of -t; a game quaternion [w, x, y, z] is Babylon
// (-x, -z, -y, w).
//
// Tiers (the ladder every game shares):
//   blocks  unlit flat colours, no shadows: the floor every machine can draw
//   low     lit, one 1024 shadow map, fog
//   high    PBR materials, 2048 soft shadows, bloom and FXAA

/* global BABYLON */

export const TIERS = ["blocks", "low", "high"];

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
        window.addEventListener("resize", () => sharedEngine.resize());
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
    return {webgl: engine.webGLVersion, renderer, webgpu: !!navigator.gpu};
}

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
    }

    build() {
        const old = this.scene;
        if (old) old.dispose();
        const L = this.look;
        const scene = this.scene = new BABYLON.Scene(this.engine);
        scene.clearColor = new BABYLON.Color4(L.sky[0], L.sky[1], L.sky[2], 1);
        scene.ambientColor = new BABYLON.Color3(0.3, 0.3, 0.3);
        this.materials = {};
        this.lit = this.tier !== "blocks";
        // blocks: one even light from everywhere, so every face is its flat colour; the others: sky and sun
        const hemi = new BABYLON.HemisphericLight("sky", new BABYLON.Vector3(0, 1, 0), scene);
        hemi.intensity = this.lit ? L.hemi : 1.0;
        hemi.groundColor = this.lit ? col(L.ground) : new BABYLON.Color3(1, 1, 1);
        const sun = this.sun = new BABYLON.DirectionalLight("sun", new BABYLON.Vector3(...L.sunDir), scene);
        sun.intensity = this.lit ? L.sun : 0.0;
        sun.position = new BABYLON.Vector3(60, 90, -80);
        this.shadows = null;
        if (this.lit) {
            const sg = this.shadows = new BABYLON.ShadowGenerator(this.tier === "high" ? 2048 : 1024, sun);
            sg.usePercentageCloserFiltering = true;
            sg.filteringQuality = this.tier === "high" ? BABYLON.ShadowGenerator.QUALITY_HIGH : BABYLON.ShadowGenerator.QUALITY_LOW;
            sg.bias = 0.0015;
            sg.normalBias = 0.02;
            sun.shadowMinZ = 1;
            sun.shadowMaxZ = 400;
            sun.autoUpdateExtends = false;
            sun.shadowFrustumSize = L.shadowSize;
            if (L.fogDensity) {
                scene.fogMode = BABYLON.Scene.FOGMODE_EXP2;
                scene.fogDensity = this.tier === "high" ? L.fogDensity * 0.67 : L.fogDensity;
                scene.fogColor = col(L.fog);
            }
        }
        const cam = this.camera = new BABYLON.ArcRotateCamera("cam", -Math.PI / 2, 1.05, L.radius, v3(...L.target), scene);
        cam.lowerRadiusLimit = 2;
        cam.upperRadiusLimit = 400;
        cam.upperBetaLimit = 1.5;
        cam.minZ = 0.1;
        cam.maxZ = 1200;
        cam.wheelDeltaPercentage = 0.02;
        cam.attachControl(this.canvas, true);
        if (this.tier === "high") {
            const pipe = new BABYLON.DefaultRenderingPipeline("look", true, scene, [cam]);
            pipe.fxaaEnabled = true;
            pipe.bloomEnabled = true;
            pipe.bloomThreshold = 0.85;
            pipe.bloomWeight = 0.25;
            pipe.imageProcessing.toneMappingEnabled = false;  // (ACES greyed the sky and washed the colours)
            pipe.imageProcessing.contrast = 1.05;
        }
        this.populate(!!old);
    }

    populate() { /* the subclass's world */ }

    setTier(tier) {
        if (!TIERS.includes(tier) || tier === this.tier) return;
        this.tier = tier;
        this.build();
    }

    // one material per look, cached: flat and unlit on blocks, PBR on high, Standard between
    material(name, rgb, rough = 0.9, metal = 0.0, glow = 0) {
        const key = `${name}:${rgb.join(",")}:${rough}:${metal}:${glow}`;
        let m = this.materials[key];
        if (m) return m;
        if (this.tier === "high") {
            m = new BABYLON.PBRMaterial(key, this.scene);
            m.albedoColor = col(rgb);
            m.roughness = rough;
            m.metallic = Math.min(metal, 0.3);  // (no environment map: full metal would reflect only black)
            m.environmentIntensity = 0.6;
            if (glow) m.emissiveColor = col(rgb).scale(glow);
        } else {
            m = new BABYLON.StandardMaterial(key, this.scene);
            m.diffuseColor = col(rgb);
            m.specularColor = this.lit ? new BABYLON.Color3(0.08, 0.08, 0.08).scale(1 - rough + 0.3) : new BABYLON.Color3(0, 0, 0);
            if (glow) m.emissiveColor = col(rgb).scale(Math.min(1, glow));
        }
        m.backFaceCulling = false;
        this.materials[key] = m;
        return m;
    }

    glass(name, rgb, alpha) {
        const key = `glass:${name}`;
        if (this.materials[key]) return this.materials[key];
        const m = new BABYLON.StandardMaterial(key, this.scene);
        m.diffuseColor = col(rgb);
        m.alpha = alpha;
        m.backFaceCulling = false;
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

    followSun() {
        if (this.sun && this.shadows) {
            const t = this.camera.target;
            this.sun.position.set(t.x + 60, 90, t.z - 80);
        }
    }

    render() {
        this.scene.render();
    }

    gpuInfo() {
        return engineInfo(this.engine);
    }

    dispose() {
        if (this.scene) this.scene.dispose();
        this.scene = null;
    }
}
