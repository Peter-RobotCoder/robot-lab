// Kart Lab drawn in the browser with Babylon.js: the track as a ribbon with kerbs, barriers, the start line, dash
// pads and oil, grass that follows the hills, trees, and the karts (a tub, pods, wheels, a driver, a wing).
//
// Coordinates: the game is z-up and right-handed (Panda3D); Babylon is y-up and left-handed. Swapping y and z
// maps one onto the other without a mirror image: game (x, y, z) -> Babylon (x, z, y), and a game yaw of t
// (anticlockwise from +x) is a Babylon rotation.y of -t.
//
// Tiers (the start of the ladder every engine will share):
//   blocks  unlit flat colours, no shadows, no textures: the floor every machine can draw
//   low     lit, one 1024 shadow map, fog
//   high    PBR materials, 2048 soft shadows, bloom and FXAA through the default rendering pipeline

/* global BABYLON */

const WHEEL_R = 0.2, WHEEL_W = 0.09;
const WHEELS = [[0.5, 0.6], [0.5, -0.6], [-0.52, 0.62], [-0.52, -0.62]];  // x, y: FL, FR, RL, RR
const KERB_RED = [0.85, 0.12, 0.08], KERB_WHITE = [0.95, 0.95, 0.92];
const FLAG_DRIFT_L = 1, FLAG_DRIFT_R = 2, FLAG_BOOSTING = 16;

export const TIERS = ["blocks", "low", "high"];

function v3(x, y, z) {  // a game point to a Babylon vector
    return new BABYLON.Vector3(x, z, y);
}

function col(rgb) {
    return new BABYLON.Color3(rgb[0], rgb[1], rgb[2]);
}

export class KartScene {
    constructor(canvas, tier = "low") {
        this.canvas = canvas;
        this.tier = TIERS.includes(tier) ? tier : "low";
        this.engine = new BABYLON.Engine(canvas, true, {stencil: true, antialias: true}, true);
        this.karts = new Map();     // id -> visual
        this.hints = new Map();     // id -> last track segment (locate's hint)
        this.track = null;
        this.trackMeshes = [];
        this.follow = null;         // kart id the camera chases, or null for the TV camera
        this.mode = "tv";           // tv | chase | overview
        this.build();
        window.addEventListener("resize", () => this.engine.resize());
    }

    // ---------- the scene, rebuilt when the tier changes ----------
    build() {
        const old = this.scene;
        const scene = this.scene = new BABYLON.Scene(this.engine);
        scene.clearColor = new BABYLON.Color4(0.53, 0.72, 0.95, 1);
        scene.ambientColor = new BABYLON.Color3(0.3, 0.3, 0.3);
        this.materials = {};
        this.lit = this.tier !== "blocks";

        // blocks: one even light from everywhere, so every face is its flat colour; the others: sky and sun
        const hemi = new BABYLON.HemisphericLight("sky", new BABYLON.Vector3(0, 1, 0), scene);
        hemi.intensity = this.lit ? 0.55 : 1.0;
        hemi.groundColor = this.lit ? new BABYLON.Color3(0.35, 0.4, 0.3) : new BABYLON.Color3(1, 1, 1);
        const sun = this.sun = new BABYLON.DirectionalLight("sun", new BABYLON.Vector3(-0.45, -0.65, 0.6), scene);
        sun.intensity = this.lit ? 1.4 : 0.0;
        sun.position = new BABYLON.Vector3(60, 90, -80);
        this.shadows = null;
        if (this.lit) {
            const size = this.tier === "high" ? 2048 : 1024;
            const sg = this.shadows = new BABYLON.ShadowGenerator(size, sun);
            sg.usePercentageCloserFiltering = true;
            sg.filteringQuality = this.tier === "high" ? BABYLON.ShadowGenerator.QUALITY_HIGH
                                                       : BABYLON.ShadowGenerator.QUALITY_LOW;
            sg.bias = 0.0015;
            sg.normalBias = 0.02;
            sun.shadowMinZ = 1;
            sun.shadowMaxZ = 400;
            sun.autoUpdateExtends = false;
            sun.shadowFrustumSize = 90;  // (follows the camera's target: see frame())
            scene.fogMode = BABYLON.Scene.FOGMODE_EXP2;
            scene.fogDensity = this.tier === "high" ? 0.0012 : 0.0018;
            scene.fogColor = new BABYLON.Color3(0.7, 0.8, 0.95);
        }
        const cam = this.camera = new BABYLON.ArcRotateCamera("cam", -Math.PI / 2, 1.05, 60,
                                                              new BABYLON.Vector3(30, 0, 40), scene);
        cam.lowerRadiusLimit = 4;
        cam.upperRadiusLimit = 400;
        cam.upperBetaLimit = 1.5;
        cam.minZ = 0.3;
        cam.maxZ = 1200;
        cam.wheelDeltaPercentage = 0.02;
        cam.attachControl(this.canvas, true);
        if (this.tier === "high") {
            const pipe = new BABYLON.DefaultRenderingPipeline("look", true, scene, [cam]);
            pipe.fxaaEnabled = true;
            pipe.bloomEnabled = true;
            pipe.bloomThreshold = 0.85;
            pipe.bloomWeight = 0.25;
            pipe.imageProcessing.toneMappingEnabled = false;  // (ACES greyed the sky and washed the greens)
            pipe.imageProcessing.contrast = 1.05;
        }
        if (old) {
            const track = this.trackData, karts = [...this.karts.values()].map(k => k.design);
            old.dispose();
            this.karts.clear();
            this.trackMeshes = [];
            if (track) this.setTrack(track);
            for (const d of karts) this.addKart(d);
        }
    }

    setTier(tier) {
        if (!TIERS.includes(tier) || tier === this.tier) return;
        this.tier = tier;
        this.build();
    }

    // one material per look, cached: flat and unlit on blocks, PBR on high, Standard between
    material(name, rgb, rough = 0.9, metal = 0.0) {
        const key = `${name}:${rgb.join(",")}:${rough}:${metal}`;
        let m = this.materials[key];
        if (m) return m;
        if (this.tier === "high") {
            m = new BABYLON.PBRMaterial(key, this.scene);
            m.albedoColor = col(rgb);
            m.roughness = rough;
            m.metallic = Math.min(metal, 0.3);  // (no environment map yet: full metal would reflect only black)
            m.environmentIntensity = 0.6;
        } else {
            m = new BABYLON.StandardMaterial(key, this.scene);
            m.diffuseColor = col(rgb);
            m.specularColor = this.lit ? new BABYLON.Color3(0.08, 0.08, 0.08).scale(1 - rough + 0.3)
                                       : new BABYLON.Color3(0, 0, 0);
        }
        m.backFaceCulling = false;
        this.materials[key] = m;
        return m;
    }

    // ---------- the track ----------
    setTrack(data) {
        for (const m of this.trackMeshes) m.dispose();
        this.trackMeshes = [];
        this.trackData = data;
        const track = this.track = data;  // (a Track instance from track.js)
        const half = track.half, L = track.length, scene = this.scene;
        const add = (mesh, mat, shadow = false) => {
            mesh.material = mat;
            mesh.receiveShadows = this.lit;
            if (shadow && this.shadows) this.shadows.addShadowCaster(mesh);
            this.trackMeshes.push(mesh);
            return mesh;
        };
        // the road: a ribbon from edge to edge following the hills
        add(this.ribbon("road", 0, L, half + 0.3, -half - 0.3, 0.0, null, null),
            this.material("tarmac", this.tier === "blocks" ? [0.42, 0.42, 0.45] : [0.3, 0.3, 0.32], 1.0));
        // centre dashes
        const dashes = [];
        for (let s = 3; s < L - 3; s += 6) dashes.push(this.ribbonData(s, s + 2.5, 0.1, -0.1, 0.012, 2.5, [0.85, 0.85, 0.8]));
        add(this.fromParts("dashes", dashes), this.material("paint", [1, 1, 1], 0.7));
        // kerbs: 2 m blocks of red and white along both edges, and barriers a metre outside
        const kerbs = [], walls = [];
        for (let s = 0, block = 0; s < L; s += 2, block++) {
            const c = block % 2 ? KERB_RED : KERB_WHITE, e = Math.min(L, s + 2);
            kerbs.push(this.ribbonData(s, e, half + 0.3, half - 0.3, 0.02, 1.0, c));
            kerbs.push(this.ribbonData(s, e, -half + 0.3, -half - 0.3, 0.02, 1.0, c));
        }
        for (let s = 0, block = 0; s < L; s += 4, block++) {
            const c = block % 2 ? KERB_WHITE : KERB_RED, e = Math.min(L, s + 4);
            for (const side of [1, -1]) {
                const a = side * (half + 1.3), b = side * (half + 1.6);
                walls.push(this.wallData(s, e, a, -0.3, 0.6, c));
                walls.push(this.ribbonData(s, e, a, b, 0.6, 1.0, c));
                walls.push(this.wallData(s, e, b, -0.3, 0.6, c));
            }
        }
        add(this.fromParts("kerbs", kerbs), this.material("paint", [1, 1, 1], 0.8));
        add(this.fromParts("walls", walls), this.material("paint", [1, 1, 1], 0.8), true);
        // the start line: a chequered strip across the road
        const checks = [];
        const cols = 8, rows = 2;
        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const lat0 = half - (c * 2 * half / cols), lat1 = half - ((c + 1) * 2 * half / cols);
                const shade = (r + c) % 2 ? [0.05, 0.05, 0.05] : [0.95, 0.95, 0.95];
                checks.push(this.ribbonData(-r * 1.2 - 1.2, -r * 1.2, lat0, lat1, 0.015, 1.2, shade));
            }
        }
        add(this.fromParts("start", checks), this.material("paint", [1, 1, 1], 0.7));
        // dash pads (orange chevrons) and oil (dark pools)
        const pads = [], oil = [];
        for (const [s, lat] of track.boosts) pads.push(this.ribbonData(s - 1.3, s + 1.3, lat + 1.2, lat - 1.2, 0.02, 1.3, [1.0, 0.55, 0.1]));
        for (const [s, lat] of track.oil) oil.push(this.ribbonData(s - 1.1, s + 1.1, lat + 1.1, lat - 1.1, 0.02, 1.1, [0.08, 0.06, 0.1]));
        if (pads.length) add(this.fromParts("pads", pads), this.material("glow", [1, 1, 1], 0.4));
        if (oil.length) add(this.fromParts("oil", oil), this.material("oil", [1, 1, 1], 0.1));
        // the grass: a grid at the height of the nearest bit of track
        const [x0, y0, x1, y1] = track.bounds();
        const margin = 45, cell = 3;
        const gx0 = x0 - margin, gy0 = y0 - margin, w = (x1 - x0) + 2 * margin, h = (y1 - y0) + 2 * margin;
        const nx = Math.ceil(w / cell), ny = Math.ceil(h / cell);
        const gpos = [], gidx = [];
        for (let j = 0; j <= ny; j++) {
            for (let i = 0; i <= nx; i++) {
                const x = gx0 + i * cell, y = gy0 + j * cell;
                const at = track.locate(x, y, null);
                const z = track.point(at.s)[2] - 0.05 - Math.min(2.5, Math.max(0, at.dist - half) * 0.03);
                gpos.push(x, z, y);
            }
        }
        for (let j = 0; j < ny; j++) {
            for (let i = 0; i < nx; i++) {
                const a = j * (nx + 1) + i, b = a + 1, c = a + nx + 1, d = c + 1;
                gidx.push(a, c, b, b, c, d);
            }
        }
        const grass = new BABYLON.Mesh("grass", scene);
        const gvd = new BABYLON.VertexData();
        gvd.positions = gpos;
        gvd.indices = gidx;
        gvd.normals = upwardNormals(gpos, gidx);
        gvd.applyToMesh(grass);
        add(grass, this.material("grass", this.tier === "blocks" ? [0.4, 0.66, 0.32] : [0.36, 0.62, 0.28], 1.0));
        // trees: cones on trunks, off the track
        const rnd = mulberry(11);
        const trunk = BABYLON.MeshBuilder.CreateCylinder("trunk", {height: 1.6, diameter: 0.5, tessellation: 8}, scene);
        trunk.material = this.material("bark", [0.4, 0.28, 0.18], 1.0);
        const crown = BABYLON.MeshBuilder.CreateCylinder("crown", {height: 5, diameterTop: 0, diameterBottom: 3.6, tessellation: 10}, scene);
        crown.material = this.material("leaf", [0.12, 0.45, 0.2], 1.0);
        trunk.isVisible = crown.isVisible = false;
        this.trackMeshes.push(trunk, crown);
        let placed = 0, tries = 0;
        while (placed < 70 && tries < 2000) {
            tries++;
            const x = gx0 + rnd() * w, y = gy0 + rnd() * h;
            const at = track.locate(x, y, null);
            if (at.dist < half + 11 || at.dist > half + 38) continue;
            const z = track.point(at.s)[2] - 0.05, scale = 0.8 + rnd() * 0.7;
            const t = trunk.createInstance("t" + placed), c = crown.createInstance("c" + placed);
            t.position = v3(x, y, z + 0.8 * scale);
            t.scaling.setAll(scale);
            c.position = v3(x, y, z + (1.6 + 2.5) * scale);
            c.scaling.setAll(scale);
            t.receiveShadows = c.receiveShadows = false;
            if (this.shadows) this.shadows.addShadowCaster(c);
            this.trackMeshes.push(t, c);
            placed++;
        }
        this.setMode(this.mode, this.follow);
    }

    // a strip along the track between s0 and s1, from lateral a to b, lifted: positions/indices/colours
    ribbonData(s0, s1, a, b, lift, step = null, rgb = null) {
        const t = this.track;
        step = step || 1.2;
        const pos = [], idx = [], colr = [];
        const n = Math.max(1, Math.ceil((s1 - s0) / step));
        for (let i = 0; i <= n; i++) {
            const s = s0 + (s1 - s0) * i / n;
            const p = t.point(s, a), q = t.point(s, b);
            pos.push(p[0], p[2] + lift, p[1], q[0], q[2] + lift, q[1]);
            if (rgb) colr.push(rgb[0], rgb[1], rgb[2], 1, rgb[0], rgb[1], rgb[2], 1);
            if (i > 0) {
                const k = 2 * i;
                idx.push(k - 2, k - 1, k, k - 1, k + 1, k);
            }
        }
        return {pos, idx, colr: rgb ? colr : null};
    }

    // a vertical face along the track at lateral a, from height z0 up by height
    wallData(s0, s1, a, z0, height, rgb) {
        const t = this.track, pos = [], idx = [], colr = [];
        const n = Math.max(1, Math.ceil((s1 - s0) / 1.2));
        for (let i = 0; i <= n; i++) {
            const s = s0 + (s1 - s0) * i / n;
            const p = t.point(s, a);
            pos.push(p[0], p[2] + z0, p[1], p[0], p[2] + z0 + height, p[1]);
            colr.push(rgb[0], rgb[1], rgb[2], 1, rgb[0], rgb[1], rgb[2], 1);
            if (i > 0) {
                const k = 2 * i;
                idx.push(k - 2, k - 1, k, k - 1, k + 1, k);
            }
        }
        return {pos, idx, colr};
    }

    ribbon(name, s0, s1, a, b, lift, step, rgb) {
        return this.fromParts(name, [this.ribbonData(s0, s1, a, b, lift, step, rgb)]);
    }

    fromParts(name, parts) {
        const pos = [], idx = [], colr = [];
        let base = 0, coloured = true;
        for (const p of parts) {
            pos.push(...p.pos);
            for (const i of p.idx) idx.push(i + base);
            if (p.colr) colr.push(...p.colr); else coloured = false;
            base += p.pos.length / 3;
        }
        const mesh = new BABYLON.Mesh(name, this.scene);
        const vd = new BABYLON.VertexData();
        vd.positions = pos;
        vd.indices = idx;
        vd.normals = upwardNormals(pos, idx);
        if (coloured && colr.length) vd.colors = colr;
        vd.applyToMesh(mesh);
        return mesh;
    }

    // ---------- the karts ----------
    addKart(design) {
        const id = design.id;
        if (this.karts.has(id)) this.removeKart(id);
        const scene = this.scene;
        const colour = (design.colour || [220, 60, 50]).map(v => v / 255);
        const root = new BABYLON.TransformNode("kart" + id, scene);
        const body = new BABYLON.TransformNode("body" + id, scene);
        body.parent = root;
        const paint = this.material("paint", colour, 0.5, 0.2);
        const dark = this.material("dark", [0.08, 0.08, 0.09], 0.8);
        const steel = this.material("steel", [0.6, 0.6, 0.62], 0.5, 1.0);
        const suit = this.material("suit", colour.map(c => Math.min(1, 0.4 + 0.6 * c)), 0.8);
        const white = this.material("white", [0.95, 0.95, 0.95], 0.25);
        const z0 = 0.16;
        const parts = [];
        const box = (name, w, l, h, mat, x, y, z, tilt = 0) => {  // w along x (game), l along y, h up
            const m = BABYLON.MeshBuilder.CreateBox(name, {width: w, depth: l, height: h}, scene);
            m.material = mat;
            m.position = v3(x, y, z);
            m.rotation.z = tilt;
            m.parent = body;
            parts.push(m);
            return m;
        };
        box("tub", 1.44, 0.68, 0.14, paint, 0, 0, z0 + 0.07);
        box("cowl", 0.56, 0.4, 0.18, paint, 0.42, 0, z0 + 0.2);
        box("bumperF", 0.16, 1.1, 0.1, dark, 0.8, 0, z0 + 0.06);
        box("bumperR", 0.12, 1.2, 0.1, dark, -0.78, 0, z0 + 0.06);
        for (const side of [1, -1]) box("pod", 0.72, 0.2, 0.12, paint, 0, side * 0.44, z0 + 0.1);
        box("plate", 0.04, 0.28, 0.2, white, 0.7, 0, z0 + 0.3);
        box("seat", 0.32, 0.38, 0.08, dark, -0.3, 0, z0 + 0.16);
        box("seatback", 0.08, 0.4, 0.4, dark, -0.46, 0, z0 + 0.36);
        box("torso", 0.26, 0.3, 0.34, suit, -0.28, 0, z0 + 0.36);
        for (const side of [1, -1]) box("arm", 0.4, 0.07, 0.07, suit, -0.08, side * 0.14, z0 + 0.42);
        const helmet = BABYLON.MeshBuilder.CreateSphere("helmet", {diameter: 0.28, segments: 10}, scene);
        helmet.material = white;
        helmet.position = v3(-0.28, 0, z0 + 0.66);
        helmet.parent = body;
        parts.push(helmet);
        box("visor", 0.06, 0.2, 0.09, dark, -0.16, 0, z0 + 0.67);
        box("wing", 0.2, 0.84, 0.03, paint, -0.66, 0, z0 + 0.4, 0.14);
        for (const side of [1, -1]) box("post", 0.04, 0.04, 0.24, steel, -0.66, side * 0.3, z0 + 0.26);
        box("engine", 0.24, 0.2, 0.18, steel, -0.42, 0.28, z0 + 0.22);
        const flame = box("flame", 0.5, 0.16, 0.12, this.material("flame", [1.0, 0.6, 0.15], 0.3), -1.0, 0, z0 + 0.12);
        flame.isVisible = false;
        // wheels: a pivot (steering) holding a spinner (rolling) holding the tyre and hub
        const wheels = [];
        WHEELS.forEach(([x, y], i) => {
            const pivot = new BABYLON.TransformNode("pivot", scene);
            pivot.parent = root;
            pivot.position = v3(x, y, WHEEL_R);
            const spin = new BABYLON.TransformNode("spin", scene);
            spin.parent = pivot;
            const tyre = BABYLON.MeshBuilder.CreateCylinder("tyre", {height: WHEEL_W * 2, diameter: WHEEL_R * 2, tessellation: 18}, scene);
            tyre.material = dark;
            tyre.rotation.x = Math.PI / 2;  // the axle along the game's y (Babylon z)
            tyre.parent = spin;
            const hub = BABYLON.MeshBuilder.CreateCylinder("hub", {height: WHEEL_W * 2 + 0.01, diameter: WHEEL_R * 1.1, tessellation: 12}, scene);
            hub.material = steel;
            hub.rotation.x = Math.PI / 2;
            hub.parent = spin;
            parts.push(tyre, hub);
            wheels.push({pivot, spin, front: i < 2});
        });
        if (this.shadows) for (const p of parts) this.shadows.addShadowCaster(p);
        for (const p of parts) p.receiveShadows = false;
        const label = this.makeLabel(design.name || "", colour);
        label.parent = root;
        label.position = v3(0, 0, 1.25);
        this.karts.set(id, {root, body, wheels, flame, label, design, lastYaw: 0, spin: 0});
    }

    makeLabel(text, colour) {
        const plane = BABYLON.MeshBuilder.CreatePlane("label", {width: 2.4, height: 0.6}, this.scene);
        const tex = new BABYLON.DynamicTexture("labeltex", {width: 384, height: 96}, this.scene, true);
        tex.hasAlpha = true;
        const ctx = tex.getContext();
        ctx.clearRect(0, 0, 384, 96);
        ctx.fillStyle = "rgba(10,12,20,0.7)";
        ctx.fillRect(0, 0, 384, 96);
        tex.drawText(text, null, 68, "bold 52px sans-serif", "#ffffff", null, true, true);
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

    removeKart(id) {
        const k = this.karts.get(id);
        if (!k) return;
        k.root.dispose(false, true);
        this.karts.delete(id);
        if (this.follow === id) this.follow = null;
    }

    setKarts(designs) {  // the roster's karts: add new ones, drop gone ones, recolour changed ones
        const wanted = new Map(designs.map(d => [d.id, d]));
        for (const id of [...this.karts.keys()]) if (!wanted.has(id)) this.removeKart(id);
        for (const [id, d] of wanted) {
            const have = this.karts.get(id);
            if (!have || have.design.name !== d.name || String(have.design.colour) !== String(d.colour)) this.addKart(d);
        }
    }

    // ---------- each frame ----------
    // states: Map id -> {x, y, yaw, v, flags, ...} (interpolated); dt in seconds
    frame(states, dt) {
        const track = this.track;
        for (const [id, k] of this.karts) {
            const st = states.get(id);
            if (!st) { k.root.setEnabled(false); continue; }
            k.root.setEnabled(true);
            let z = 0;
            if (track) {
                const at = track.locate(st.x, st.y, this.hints.get(id) ?? null);
                this.hints.set(id, at.seg);
                z = track.point(at.s)[2];
            }
            k.root.position.set(st.x, z, st.y);
            k.root.rotation.y = -st.yaw * Math.PI / 180;
            const drift = (st.flags & FLAG_DRIFT_L) ? 1 : (st.flags & FLAG_DRIFT_R) ? -1 : 0;
            k.body.rotation.x = BABYLON.Scalar.Lerp(k.body.rotation.x, drift * 0.08, 0.2);  // (roll into a drift)
            k.flame.isVisible = !!(st.flags & FLAG_BOOSTING);
            k.spin += (st.v || 0) * dt / WHEEL_R;
            const steer = Math.max(-0.45, Math.min(0.45, (st.u || 0) * 0.08 + drift * 0.3));
            for (const w of k.wheels) {
                w.spin.rotation.z = -k.spin;
                if (w.front) w.pivot.rotation.y = -steer;
            }
        }
        this.updateCamera(states, dt);
        if (this.sun && this.shadows) {
            const t = this.camera.target;
            this.sun.position.set(t.x + 60, 90, t.z - 80);
        }
    }

    updateCamera(states, dt) {
        const cam = this.camera;
        const snap = this.snapCamera;  // (the first frame after a change of camera jumps straight there)
        if (this.mode === "chase" && this.follow !== null && states.has(this.follow)) {
            const st = states.get(this.follow), k = this.karts.get(this.follow);
            if (!k) return;
            const yaw = st.yaw * Math.PI / 180;
            const p = k.root.position;
            const target = new BABYLON.Vector3(p.x + Math.cos(yaw) * 4, p.y + 0.8, p.z + Math.sin(yaw) * 4);
            cam.target = snap ? target : BABYLON.Vector3.Lerp(cam.target, target, Math.min(1, dt * 8));
            // ArcRotate: alpha measured from +x towards +z; behind the kart is the opposite of its heading
            const wantAlpha = Math.atan2(-Math.sin(yaw), -Math.cos(yaw));
            cam.alpha = snap ? wantAlpha : lerpAngle(cam.alpha, wantAlpha, Math.min(1, dt * 4));
            cam.beta = snap ? 1.25 : BABYLON.Scalar.Lerp(cam.beta, 1.25, Math.min(1, dt * 4));
            cam.radius = snap ? 7.5 : BABYLON.Scalar.Lerp(cam.radius, 7.5, Math.min(1, dt * 4));
            this.snapCamera = false;
        } else if (this.mode === "tv") {
            const lead = this.follow !== null && states.has(this.follow) ? this.follow : this.leader;
            const k = lead !== null && lead !== undefined ? this.karts.get(lead) : null;
            if (k) {
                const target = k.root.position.add(new BABYLON.Vector3(0, 0.5, 0));
                cam.target = snap ? target : BABYLON.Vector3.Lerp(cam.target, target, Math.min(1, dt * 3));
                this.snapCamera = false;
            }
        }
    }

    overview() {
        if (!this.track) return;
        const [x0, y0, x1, y1] = this.track.bounds();
        const cam = this.camera;
        cam.target = new BABYLON.Vector3((x0 + x1) / 2, 0, (y0 + y1) / 2);
        cam.radius = Math.max(x1 - x0, y1 - y0) * 1.1;
        cam.alpha = -Math.PI / 2;
        cam.beta = 0.9;
    }

    setMode(mode, follow = null) {
        this.mode = mode;
        this.follow = follow;
        this.snapCamera = true;
        if (mode === "overview") this.overview();
        if (mode === "tv") { this.camera.radius = 18; this.camera.beta = 0.95; }
    }

    render() {
        this.scene.render();
    }

    gpuInfo() {
        const gl = this.engine._gl;
        let renderer = "";
        try {
            const ext = gl.getExtension("WEBGL_debug_renderer_info");
            renderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
        } catch (e) { renderer = "?"; }
        return {webgl: this.engine.webGLVersion, renderer, webgpu: !!navigator.gpu};
    }
}

// the normals of a mesh whose faces mostly look up (a road, a lawn): computed, then turned over as one if the
// winding left them pointing down, so the sun lights the top
function upwardNormals(pos, idx) {
    const norm = [];
    BABYLON.VertexData.ComputeNormals(pos, idx, norm);
    let up = 0;
    for (let i = 1; i < norm.length; i += 3) up += norm[i];
    if (up < 0) for (let i = 0; i < norm.length; i++) norm[i] = -norm[i];
    return norm;
}

function lerpAngle(a, b, t) {
    let d = ((b - a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    return a + d * t;
}

function mulberry(seed) {  // a small seeded random, so the trees stand where they stood last time
    let a = seed >>> 0;
    return () => {
        a = (a + 0x6D2B79F5) >>> 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
