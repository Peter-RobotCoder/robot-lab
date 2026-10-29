// The karts and the sports cars as Kart Lab draws them in the browser (moved out of scene.js in CHANGE 201, unchanged,
// so City Lab's cars are Kart Lab's: kart_gfx.KartVisual, which the City Lab window borrows too). CarParts is a set of
// a scene's methods, put on KartScene (scene.js) and CityScene (city.js) alike: addKart builds a kart (the box kart,
// the curved ultra kart) or a sports car (models/cars.json; on ultra the detailed one near the camera), with its
// wheels on their steering pivots and rolling spinners, its lamps, the boost's glow and the line tiers' lines;
// carFrame poses one each frame from its record (the body's pitch and lean, the wheels rolling and steering, damage,
// the lamps, the drift smoke, skid marks and sparks on ultra); headlightFrame gives the beams to the nearest at dusk
// and night. A scene with them has this.karts (id -> what addKart made), this.follow, this.timeLook (TIME_LOOKS'),
// this.smoke (a Smoke, or null), this.skids and this.sparks (ultra's, or null), lineFade() and refreshLists().

/* global BABYLON */

import {v3} from "./base3d.js";
import {ultraKartData, partMesh, loadCars, carData, loadCarUltra, carUltraData, HAZE} from "./kartfx.js";
import {DAMAGE_PARTS, DAMAGE_MAX} from "./kart_sim.js";  // (CHANGE 158: each part's damage, drawn on the kart)

const WHEEL_R = 0.2, WHEEL_W = 0.09;
// (CHANGE 157, kart_gfx's) the front wheels at full lock (radians), the steering wheel's turn to theirs, how fast the
// drawn steering follows the driver's (per second)
const MAX_STEER = 26 * Math.PI / 180, STEER_RATIO = 3.0, STEER_EASE = 10.0;
const WHEELS = [[0.5, 0.6], [0.5, -0.6], [-0.52, 0.62], [-0.52, -0.62]];  // x, y: FL, FR, RL, RR
export const STEEL = [0.6, 0.6, 0.62];
const FLAG_DRIFT_L = 1, FLAG_DRIFT_R = 2, FLAG_BOOSTING = 16, FLAG_BRAKING = 32;  // (FLAG_BRAKING: CHANGE 171)
const FLAG_WHEELSPIN = 64, FLAG_HANDBRAKE = 128;  // (CHANGE 181: the back wheels spinning or locked: tyre smoke)
export const PUFFS = 8;  // (kart_gfx.KartVisual.PUFFS: a kart's drift smoke; the scene's pool holds 12 karts' worth)
const PUFF_LIFE = 0.7;
const DEG = Math.PI / 180;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// (CHANGE 172) the race's time of day (the lesson's "time"), as the window's (kart_gfx.TIME_LOOKS): the sky behind
// (and blocks' plain light), the lighting's ambient, sun, exposure and fill (the sky's light and reflections fall with
// the daylight), the haze and ultra's sky dome (screen colours, after the tone curve: the horizon, below it, the sun's
// or moon's glow, the clouds' light, the stars), whether the lamps are lit and the beams' strength
export const TIME_LOOKS = {
    day: {sky: [0.3, 0.5, 0.9], ambient: [0.22, 0.25, 0.32], sun: [2.6, 2.45, 2.2], exposure: 0.55, env: 1.0, blocks: 1.0,
          horizon: HAZE, below: [0.55, 0.62, 0.6], sunCol: [1.0, 0.92, 0.75], clouds: 1.0, stars: 0.0, lamps: false, beam: 0},
    dusk: {sky: [0.5, 0.33, 0.36], ambient: [0.12, 0.1, 0.15], sun: [1.8, 0.95, 0.5], exposure: 0.62, env: 0.4, blocks: 0.7,
           horizon: [0.8, 0.62, 0.58], below: [0.32, 0.28, 0.3], sunCol: [1.0, 0.5, 0.25], clouds: 0.6, stars: 0.0, lamps: true, beam: 0.45},
    night: {sky: [0.01, 0.014, 0.035], ambient: [0.018, 0.022, 0.04], sun: [0.14, 0.18, 0.3], exposure: 0.75, env: 0.06, blocks: 0.35,
            horizon: [0.06, 0.07, 0.11], below: [0.03, 0.035, 0.05], sunCol: [0.5, 0.55, 0.7], clouds: 0.07, stars: 1.0, lamps: true, beam: 1},
};
export const HEADLIGHT = [9.0, 8.6, 7.6], HEADLIGHTS = 4;  // (kart_gfx.HEADLIGHT, HEADLIGHTS: your kart's beams and the nearest)
// (CHANGE 171, 172) where a body's lamps are (kart_gfx.LAMPS: x forward, y left, z up; each one and its mirror)
const LAMPS = {kart: {head: [0.66, 0.24, 0.31], tail: [-0.83, 0.26, 0.27], size: [0.1, 0.06]}};
// (CHANGE 173) where a kart's lamps are, its rear tyres' skids and drift smoke (x back, y out to each side), its
// damaged engine's smoke and its exhaust's sparks (x, y, z: forward, left, up), its beam (x) and the Hood camera
// (x, z): a sports car's from its notes (addCar)
const KART_FIT = {lamps: LAMPS.kart, skid: [-0.52, 0.62], puff: [-0.55, 0.6], smoke: [-0.45, 0.28, 0.5],
                  sparks: [-0.75, 0.28, 0.38], beamX: 0.6, hood: [0.95, 0.62]};

export const CarParts = {
    addKart(design) {
        const id = design.id;
        if (this.karts.has(id)) this.removeKart(id);
        const scene = this.scene;
        const colour = (design.colour || [220, 60, 50]).map(v => v / 255);
        const root = new BABYLON.TransformNode("kart" + id, scene);
        const body = new BABYLON.TransformNode("body" + id, scene);
        body.parent = root;
        if (design.body && design.body !== "kart") {  // (CHANGE 173) a sports car, once models/cars.json is here
            const car = carData(design.body);
            if (car) {
                // (CHANGE 174, ultra) the detailed car near the camera, once models/cars_ultra_<body>.json is here
                const near = this.ultra ? carUltraData(design.body) : null;
                if (this.ultra && !near) {
                    const scene = this.scene;
                    loadCarUltra(design.body).then(u => {
                        const k = this.karts.get(id);
                        if (u && this.scene === scene && k && k.car === design.body && !k.lod) this.addKart(k.design);
                    });
                }
                return this.addCar(design, root, body, colour, car, near);
            }
            const scene = this.scene;
            loadCars().then(d => {  // (drawn as a kart until it is: then made again)
                const k = this.karts.get(id);
                if (d && this.scene === scene && k && !k.car && k.design.body === design.body) this.addKart(k.design);
            });
        }
        if (this.ultra && ultraKartData()) return this.addCurvedKart(design, root, body, colour);
        // (on ultra the paint and the helmet have a clear coat, and they and the metal reflect the world: CHANGE 144)
        const paint = this.material("kpaint", colour, 0.5, 0.2, 0, {tex: "paint", tile: 1.5, clearcoat: 1, probe: true});
        const dark = this.material("kdark", [0.08, 0.08, 0.09], 0.8);
        const seatM = this.material("kseat", [0.1, 0.1, 0.12], 0.9);
        const suit = this.material("ksuit", colour.map(c => Math.min(1, 0.4 + 0.6 * c)), 0.8);
        const steel = this.material("ksteel", STEEL, 0.5, 1.0, 0, {tex: "steel", probe: true});
        const z0 = 0.16;
        const parts = [];
        const box = (hx, hy, hz, mat, x, y, z, roll = 0) => {
            const m = this.box(body, hx, hy, hz, mat, x, y, z);
            m.rotation.x = roll;  // (a roll about the kart's length: Babylon's x is the game's x)
            parts.push(m);
            return m;
        };
        box(0.72, 0.34, 0.07, paint, 0, 0, z0 + 0.07);                                   // the tub
        box(0.28, 0.2, 0.09, paint, 0.42, 0, z0 + 0.2);                                  // the cowl
        // (CHANGE 158) the front bumper on its own node, hinged at its left end: it hangs as the front wing is damaged
        const nose = new BABYLON.TransformNode("nose", scene);
        nose.parent = body;
        nose.position = v3(0.8, 0.5, z0 + 0.06);
        const noseParts = [this.box(nose, 0.08, 0.55, 0.05, dark, 0, -0.5, 0)];
        box(0.06, 0.6, 0.05, dark, -0.78, 0, z0 + 0.06);
        for (const side of [1, -1]) box(0.36, 0.1, 0.06, paint, 0, side * 0.44, z0 + 0.1);  // side pods
        box(0.02, 0.14, 0.1, this.material("kplate", [0.95, 0.95, 0.9], 0.6), 0.7, 0, z0 + 0.3);
        box(0.16, 0.19, 0.04, seatM, -0.3, 0, z0 + 0.16);                                // seat
        box(0.04, 0.2, 0.2, seatM, -0.46, 0, z0 + 0.36);
        box(0.13, 0.15, 0.17, suit, -0.28, 0, z0 + 0.36);                                // torso
        for (const side of [1, -1]) parts.push(this.cyl(body, 0.035, 0.2, "x", suit, -0.08, side * 0.14, z0 + 0.42, null, 8));
        parts.push(this.sphere(body, 0.14, this.material("khelmet", [0.95, 0.95, 0.95], 0.25, 0, 0, {tex: "paint", tile: 1.5, clearcoat: 0.8, probe: true}), -0.28, 0, z0 + 0.66, 1, 1, 1, 14));
        box(0.03, 0.1, 0.045, this.material("kvisor", [0.05, 0.05, 0.08], 0.1), -0.16, 0, z0 + 0.67);
        // (CHANGE 157) the steering wheel on its own node, turned about its own axis (x) as the driver steers, with a
        // spoke across each face so the turn shows: kept out of the merged body
        const boxWheel = new BABYLON.TransformNode("steering wheel", scene);
        boxWheel.parent = body;
        boxWheel.position = v3(0.1, 0, z0 + 0.45);
        const wheelBits = [this.cyl(boxWheel, 0.12, 0.012, "x", seatM, 0, 0, 0, null, 16)];
        for (const face of [-0.012, 0.012]) wheelBits.push(this.box(boxWheel, 0.006, 0.11, 0.014, steel, face, 0, 0));
        parts.push(this.cyl(body, 0.02, 0.14, "x", steel, 0.22, 0, z0 + 0.4, null, 8));
        for (const side of [1, -1]) box(0.02, 0.02, 0.12, steel, -0.66, side * 0.3, z0 + 0.26);  // wing posts
        const wing = this.box(body, 0.1, 0.42, 0.015, paint, -0.66, 0, z0 + 0.4);
        wing.rotation.z = -8 * Math.PI / 180;  // (tilted: its front edge down)
        parts.push(wing);
        box(0.12, 0.1, 0.09, this.material("kengine", [0.35, 0.35, 0.38], 0.6, 1.0, 0, {tex: "steel", probe: true}), -0.42, 0.28, z0 + 0.22);
        parts.push(this.cyl(body, 0.035, 0.12, "x", this.material("kexhaust", [0.3, 0.3, 0.32], 0.5, 1.0, 0, {tex: "steel", probe: true}), -0.7, 0.28, z0 + 0.22, null, 8));
        const flame = this.kartFlame(root);
        // wheels: a pivot (steering) holding a spinner (rolling) holding the tyre and hub
        const wheels = [];
        const tyreM = this.material("ktyre", [1, 1, 1], 1.0, 0, 0, {tex: "tyre", tile: 2.5});
        const hubM = this.material("khub", [0.75, 0.75, 0.78], 0.5, 1.0, 0, {tex: "steel", probe: true});
        const wheelParts = [];
        WHEELS.forEach(([x, y], i) => {
            const pivot = new BABYLON.TransformNode("pivot", scene);
            pivot.parent = root;
            pivot.position = v3(x, y, WHEEL_R);
            const spin = new BABYLON.TransformNode("spin", scene);
            spin.parent = pivot;
            wheelParts.push(this.cyl(spin, WHEEL_R, WHEEL_W, "y", tyreM, 0, 0, 0, null, 20));
            wheelParts.push(this.cyl(spin, WHEEL_R * 0.55, WHEEL_W + 0.006, "y", hubM, 0, 0, 0, null, 14));
            wheels.push({pivot, spin, front: i < 2});
        });
        const merged = this.mergeParts(parts, body);
        this.shadowCast([...merged, ...wheelParts, ...wheelBits, ...noseParts]);
        let flameLines = null;
        if (this.wire) {  // (the line tiers: the body's edges with the body, each wheel's turning with its wheel)
            const mat = this.lineMaterial("kart", 1, ...this.lineFade());
            this.linesMesh("kartlines", this.edgeLines(merged, this.wire, body), mat, body);
            flameLines = this.linesMesh("flamelines", this.edgeLines([flame], this.wire, flame), mat, flame);
            if (flameLines) flameLines.isVisible = false;
            wheels.forEach((w, i) => this.linesMesh("wheellines", this.edgeLines(wheelParts.slice(i * 2, i * 2 + 2), this.wire, w.spin), mat, w.spin));
            this.linesMesh("steerlines", this.edgeLines(wheelBits, this.wire, boxWheel), mat, boxWheel);
            this.linesMesh("noselines", this.edgeLines(noseParts, this.wire, nose), mat, nose);
        }
        this.finishKart(id, design, root, body, wheels, flame, flameLines, WHEEL_R, false);
        this.karts.get(id).boxWheel = boxWheel;
        this.karts.get(id).nose = nose;
    },

    kartFlame(root) {  // the boost's glow behind the kart (shown while boosting)
        const flame = this.box(root, 0.25, 0.08, 0.06, this.material("flame", [1.0, 0.6, 0.15], 0.3, 0, 0, {emission: [3.0, 1.4, 0.3]}), -1.0, 0, 0.28);
        flame.isVisible = false;
        return flame;
    },

    finishKart(id, design, root, body, wheels, flame, flameLines, wheelR, curved, fit = KART_FIT) {
        const label = this.makeLabel(design.name || "", "#ffffff", 1.3);  // (about the app's size: a kart's width)
        label.parent = root;
        label.position = v3(0, 0, fit.label || 1.15);  // (a car's: over its roof, CHANGE 173)
        this.karts.set(id, {root, body, wheels, flame, flameLines, label, design, lastYaw: 0, spin: 0, wheelR, curved,
                            lastV: null, pitch: 0, roll: 0, glowT: 0, puffTimer: 0, nextPuff: 0, skid: null, fit,
                            lamps: this.wire ? null : this.makeLamps(body, fit.lamps)});  // (CHANGE 171, 172)
        this.refreshLists();
    },

    // (CHANGE 171, 172, kart_gfx.Lamps) the lamps' materials, made once a scene: unlit, so they glow; the halos and the
    // pool of light added on top of what's behind them
    lampMaterials() {
        if (this.lampKit) return this.lampKit;
        const scene = this.scene;
        const dot = new BABYLON.DynamicTexture("lampdot", 64, scene, true);
        const ctx = dot.getContext(), g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
        g.addColorStop(0, "rgba(255,255,255,1)");
        g.addColorStop(0.45, "rgba(255,255,255,0.35)");
        g.addColorStop(1, "rgba(255,255,255,0)");
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, 64, 64);
        dot.update();
        dot.hasAlpha = true;
        const flat = (name, c) => {
            const m = new BABYLON.StandardMaterial(name, scene);
            m.disableLighting = true;
            m.emissiveColor = new BABYLON.Color3(...c);
            m.backFaceCulling = false;
            return m;
        };
        const glow = (name, c, alpha) => {
            const m = flat(name, c);
            m.opacityTexture = dot;
            m.alpha = alpha;
            m.alphaMode = BABYLON.Engine.ALPHA_ADD;
            m.disableDepthWrite = true;
            return m;
        };
        return this.lampKit = {
            headOff: flat("lamp head", [0.62, 0.62, 0.6]), headOn: flat("lamp head lit", [1.0, 0.98, 0.9]),
            tailOff: flat("lamp tail", [0.32, 0.03, 0.03]), tailDim: flat("lamp tail lit", [0.6, 0.04, 0.03]),
            tailOn: flat("lamp tail braking", [1.0, 0.01, 0.005]),
            halo: glow("lamp halo", [1.0, 0.95, 0.82], 1.0), glowDim: glow("lamp glow", [1.0, 0.08, 0.04], 0.5),
            glowOn: glow("lamp glow braking", [1.0, 0.08, 0.04], 0.9), pool: glow("light pool", [0.42, 0.4, 0.34], 1.0),
        };
    },

    makeLamps(parent, spec) {
        const kit = this.lampMaterials(), scene = this.scene, [w, h] = spec.size;
        const [tw, th] = Array.isArray(spec.tail_size) ? spec.tail_size : spec.size;  // (CHANGE 174: a car's own)
        const lamps = {heads: [], tails: [], halos: [], glows: [], state: null};
        for (const side of [1, -1]) {
            for (const [where, list, mat, dx] of [[spec.head, lamps.heads, kit.headOff, 0.005], [spec.tail, lamps.tails, kit.tailOff, -0.005]]) {
                const tail = list === lamps.tails;
                const lens = BABYLON.MeshBuilder.CreatePlane("lamp", {width: tail ? tw : w, height: tail ? th : h}, scene);
                lens.parent = parent;
                lens.position = v3(where[0] + dx, where[1] * side, where[2]);
                lens.rotation.y = Math.PI / 2;  // (a plane faces along z: turned to face along the kart)
                lens.material = mat;
                lens.isPickable = false;
                list.push(lens);
                const g = BABYLON.MeshBuilder.CreatePlane("lamp glow", {size: 1}, scene);
                g.parent = parent;
                g.position = v3(where[0] + dx * 8, where[1] * side, where[2]);
                g.billboardMode = BABYLON.Mesh.BILLBOARDMODE_ALL;
                g.isPickable = false;
                g.setEnabled(false);
                (list === lamps.heads ? lamps.halos : lamps.glows).push(g);
            }
        }
        const pool = lamps.pool = BABYLON.MeshBuilder.CreatePlane("light pool", {size: 1}, scene);
        pool.parent = parent;
        pool.position = v3(5.2, 0, 0.04);
        pool.rotation.x = Math.PI / 2;  // (flat on the road)
        pool.scaling.set(8.5, 4.2, 1);
        pool.material = kit.pool;
        pool.isPickable = false;
        pool.setEnabled(false);
        return lamps;
    },

    // (CHANGE 171, 172) the lamps as they are: headlamps lit at dusk and night with a halo and a pool of light ahead;
    // tail lamps dim when lit and bright when braking (or reversing), day or night
    lampFrame(lamps, lit, braking) {
        const state = (lit ? 1 : 0) + (braking ? 2 : 0);
        if (state === lamps.state) return;
        lamps.state = state;
        const kit = this.lampMaterials();
        for (const m of lamps.heads) m.material = lit ? kit.headOn : kit.headOff;
        for (const m of lamps.tails) m.material = braking ? kit.tailOn : lit ? kit.tailDim : kit.tailOff;
        for (const g of lamps.halos) { g.material = kit.halo; g.scaling.setAll(0.32); g.setEnabled(lit); }
        for (const g of lamps.glows) { g.material = braking ? kit.glowOn : kit.glowDim; g.scaling.setAll(braking ? 0.34 : 0.2); g.setEnabled(lit || braking); }
        lamps.pool.setEnabled(lit);
    },

    // (CHANGE 172) the beams: HEADLIGHTS spotlights to the karts nearest the camera, the one it follows first
    headlightFrame(states) {
        const T = this.timeLook;
        if (!this.lighting || !(T.beam > 0)) return;
        const cam = this.camera.position, ids = [...this.karts.keys()].filter(id => states.has(id));
        const far = id => {
            const r = this.karts.get(id).root.position;
            return id === this.follow ? -1 : (r.x - cam.x) ** 2 + (r.y - cam.y) ** 2 + (r.z - cam.z) ** 2;
        };
        ids.sort((a, b) => far(a) - far(b));
        const spots = [];
        for (let i = 0; i < HEADLIGHTS; i++) {
            const id = ids[i], st = id !== undefined ? states.get(id) : null;
            if (!st) { spots.push({pos: [0, 0, -100], at: [0, 1, -100], colour: [0, 0, 0], fov: 84, soft: true}); continue; }
            const h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h), k = this.karts.get(id), z = k.root.position.y;
            const pos = [st.x + k.fit.beamX * c, st.y + k.fit.beamX * s, z + 1.0];
            spots.push({pos, at: [pos[0] + 10 * c, pos[1] + 10 * s, z + 1.0 - 10 * Math.tan(11 * DEG)], fov: 84, soft: true,
                        colour: HEADLIGHT.map(v => v * T.beam), att: [1.0, 0.02, 0.008]});
        }
        this.lighting.setLights(spots);
    },

    // (ultra, CHANGE 144) the curved kart from models/kart_ultra.json (kartfx.js reads it): each part in the
    // material its role names (the file's notes.roles give each role's colour, roughness and metal: the design's
    // colour where it has none), smooth paint under a clear coat, the wheels on the same steering pivots and
    // rolling spinners as the box kart's (a right-hand wheel is the left's turned half round, as the file says),
    // and the steering wheel turning with the front wheels about the file's axis (notes.steering)
    addCurvedKart(design, root, body, colour) {
        const d = ultraKartData(), scale = Number(d.scale) || 1, notes = d.notes && typeof d.notes === "object" ? d.notes : {};
        const mat = this.roleMaterials(design, colour, notes.roles);
        const parts = [];
        for (const part of d.body) {
            const mesh = partMesh(this, part, scale);
            if (!mesh) continue;
            mesh.material = mat(part.role, "paint");
            mesh.parent = body;
            parts.push(mesh);
        }
        let steerWheel = null;
        const S = notes.steering || {};
        if ((d.steering || []).length) {
            const pivot = Array.isArray(S.pivot) ? S.pivot.map(v => v * scale) : [0.1, 0, 0.47];
            const axis = Array.isArray(S.axis) ? S.axis : [-0.848, 0, 0.53];
            const node = new BABYLON.TransformNode("steering", this.scene);
            node.parent = body;
            node.position = v3(...pivot);
            node.rotationQuaternion = BABYLON.Quaternion.Identity();
            for (const part of d.steering) {
                const mesh = partMesh(this, part, scale);
                if (!mesh) continue;
                mesh.material = mat(part.role, "dark");
                mesh.parent = node;
                mesh.position = v3(...pivot).scale(-1);  // (its vertices are the kart's: about the pivot)
                this.shadowCast([mesh]);
            }
            steerWheel = {node, axis: v3(...axis).normalize(), ratio: Number(S.ratio) || 3, pivot: v3(...pivot), arms: [], head: null};
            // (CHANGE 157) each arm on its shoulder, turned so its hand stays on the rim (the gloves are on it)
            (d.arms || []).forEach((part, i) => {
                const note = (notes.arms || [])[i];
                if (!note) return;
                const shoulder = v3(...note.shoulder.map(v => v * scale)), hand = v3(...note.hand.map(v => v * scale));
                const arm = new BABYLON.TransformNode("arm", this.scene);
                arm.parent = body;
                arm.position = shoulder.clone();
                arm.rotationQuaternion = BABYLON.Quaternion.Identity();
                const mesh = partMesh(this, part, scale);
                if (!mesh) return;
                mesh.material = mat(part.role, "dark");
                mesh.parent = arm;
                mesh.position = shoulder.scale(-1);
                this.shadowCast([mesh]);
                steerWheel.arms.push({arm, shoulder, hand});
            });
            // (CHANGE 157) the head (neck, helmet, visor) on the neck: it looks and leans into a turn
            const H = notes.head || {};
            if ((d.head || []).length && Array.isArray(H.pivot)) {
                const neck = v3(...H.pivot.map(v => v * scale));
                const head = new BABYLON.TransformNode("head", this.scene);
                head.parent = body;
                head.position = neck.clone();
                for (const part of d.head) {
                    const mesh = partMesh(this, part, scale);
                    if (!mesh) continue;
                    mesh.material = mat(part.role, "helmet");
                    mesh.parent = head;
                    mesh.position = neck.scale(-1);
                    this.shadowCast([mesh]);
                }
                steerWheel.head = {node: head, turn: (Number(H.turn) || 16) * Math.PI / 180, lean: (Number(H.lean) || 7) * Math.PI / 180};
            }
        }
        // (CHANGE 158) the front fairing, hinged at its left end (notes.nose): it hangs as the front wing is damaged
        let nose = null;
        const N = notes.nose || {};
        if ((d.nose || []).length && Array.isArray(N.pivot)) {
            const hinge = v3(...N.pivot.map(v => v * scale));
            nose = new BABYLON.TransformNode("nose", this.scene);
            nose.parent = body;
            nose.position = hinge.clone();
            for (const part of d.nose) {
                const mesh = partMesh(this, part, scale);
                if (!mesh) continue;
                mesh.material = mat(part.role, "paint2");
                mesh.parent = nose;
                mesh.position = hinge.scale(-1);
                this.shadowCast([mesh]);
            }
        }
        const wheels = [], wheelParts = [];
        for (const w of d.wheels) {
            const pivot = new BABYLON.TransformNode("pivot", this.scene);
            pivot.parent = root;
            pivot.position = v3(w.x * scale, w.y * scale, w.z * scale);
            const spin = new BABYLON.TransformNode("spin", this.scene);
            spin.parent = pivot;
            const side = new BABYLON.TransformNode("side", this.scene);
            side.parent = spin;
            if (w.side < 0) side.rotation.y = Math.PI;  // (half round about the upright: its outer face to the right)
            for (const part of d.wheel) {
                const mesh = partMesh(this, part, scale);
                if (!mesh) continue;
                mesh.material = mat(part.role, "tyre");
                mesh.parent = side;
                wheelParts.push(mesh);
            }
            wheels.push({pivot, spin, front: !!w.front});
        }
        const merged = this.mergeParts(parts, body);
        this.shadowCast([...merged, ...wheelParts]);
        const wheelR = Math.max(0.1, Number(d.wheels[0].z) * scale || WHEEL_R);
        this.finishKart(design.id, design, root, body, wheels, this.kartFlame(root), null, wheelR, true);
        this.karts.get(design.id).steerWheel = steerWheel;
        this.karts.get(design.id).nose = nose;
    },

    // (CHANGE 144, 173) a role's material (the curved kart's and the sports cars' parts): roles, the file's notes.roles
    // ({colour, rough, metal, alpha, emission}: a colour of null is the design's); a role neither it nor BASE knows is
    // fallback's. The curved kart's visor is see-through; a car's low-detail windows are dark glass, as the window's;
    // (CHANGE 174, ultra) a car's paint has metal flakes under its clear coat, its trim a thinner coat, and its
    // see-through roles (the windows, the lamps' covers) reflect at full strength however see-through they are
    roleMaterials(design, colour, roles, fallback = "paint", car = false) {
        roles = roles && typeof roles === "object" ? roles : {};
        const second = Array.isArray(design.colour2) ? design.colour2.map(v => v / 255) : colour;
        const COAT = car ? {paint: 1, paint2: 1, helmet: 0.8, stripe: 1, carbon: 0.6, chrome: 0.6, rim: 0.6, rim2: 0.6, caliper: 0.6}
            : {paint: 1, paint2: 1, helmet: 0.8};
        const FLAKE = car ? {paint: 1, paint2: 1, helmet: 1} : {};
        const SHINY = ["paint", "paint2", "helmet", "metal", "chrome", "rim", "glass", "light", "window", "lens", "lens_red",
                       "carbon", "disc", "caliper", "rim2", "stripe"];
        const BASE = {paint: [colour, 0.32, 0.15], paint2: [second, 0.32, 0.15], dark: [[0.07, 0.07, 0.08], 0.55, 0],
                      metal: [[0.62, 0.63, 0.66], 0.35, 1], chrome: [[0.92, 0.92, 0.94], 0.08, 1], glass: [[0.03, 0.035, 0.05], 0.04, 0],
                      tyre: [[0.11, 0.11, 0.12], 0.8, 0], rim: [[0.78, 0.79, 0.82], 0.28, 1], seat: [[0.09, 0.09, 0.11], 0.4, 0],
                      skin: [[0.86, 0.66, 0.53], 0.6, 0], helmet: [[0.95, 0.95, 0.95], 0.18, 0.05],
                      light: [[0.85, 0.85, 0.86], 0.1, 0.6]};
        const mats = {};
        return (role, other = fallback) => {
            if (!BASE[role] && !roles[role]) role = other;
            if (mats[role]) return mats[role];
            const [rgb0, rough0, metal0] = BASE[role] || [[0.5, 0.5, 0.5], 0.5, 0], r = roles[role] || {};
            const rgb = Array.isArray(r.colour) && r.colour.length >= 3 ? r.colour.slice(0, 3)
                : r.colour === null && role !== "paint2" ? colour : rgb0;  // (null: the design's colour, the helmet's too)
            const rough = Number.isFinite(r.rough) ? r.rough : rough0, metal = Number.isFinite(r.metal) ? r.metal : metal0;
            const opts = {clearcoat: COAT[role] || 0, probe: SHINY.includes(role), flake: FLAKE[role] || 0};
            if (role === "tyre") Object.assign(opts, {tex: "tyre", tile: 2.5});
            if (car && Number.isFinite(r.alpha) && r.alpha < 1) Object.assign(opts, {alpha: r.alpha, glass: true, clearcoat: 0});
            if (car && Array.isArray(r.emission)) opts.emission = r.emission;
            return (mats[role] = role === "glass" && !car ? this.glass("kvisor", rgb, 0.75)
                : this.material((car ? "car" : "kc") + role, rgb, rough, metal, 0, opts));
        };
    },

    // (CHANGE 173, kart_gfx.KartVisual.car) a sports car from models/cars.json (kartfx.js reads it): its body and front
    // splitter from the file on every tier (hinged at its left end, as the kart's: it hangs as the front wing is
    // damaged); its wheels the file's on ultra and plain tyres and hubs below (a car costs about what a kart does on a
    // school laptop); its lamps, smoke, sparks and boost glow where its notes say. (CHANGE 174) near: on ultra the
    // detailed car (models/cars_ultra_<body>.json: the cabin through see-through glass, the lamps' insides, the brakes)
    // drawn while it is nearer the camera than its notes' lod far, the plain one beyond (frame() switches them)
    addCar(design, root, body, colour, d, near = null) {
        const notes = d.notes && typeof d.notes === "object" ? d.notes : {};
        const mat = this.roleMaterials(design, colour, notes.roles, "paint", true);
        const levels = near ? [["near", near], ["far", d]] : [["far", d]];
        const lod = near ? {far: Number(notes.lod && notes.lod.far) || 22, near: [], farNodes: [], state: null} : null;
        const holder = (parent, level) => {
            const node = new BABYLON.TransformNode(level, this.scene);
            node.parent = parent;
            if (lod) (level === "near" ? lod.near : lod.farNodes).push(node);
            return node;
        };
        let merged = [], nose = null;
        const noseParts = [], N = notes.nose || {};
        if (Array.isArray(N.pivot)) {
            nose = new BABYLON.TransformNode("nose", this.scene);
            nose.parent = body;
            nose.position = v3(...N.pivot);
        }
        for (const [level, m] of levels) {
            const at = holder(body, level), parts = [];
            for (const part of m.body) {
                const mesh = partMesh(this, part);
                if (!mesh) continue;
                mesh.material = mat(part.role);
                mesh.parent = at;
                parts.push(mesh);
            }
            const mine = this.mergeParts(parts, at);
            merged = merged.concat(mine);
            if (nose && (m.nose || []).length) {
                const atNose = holder(nose, level);
                for (const part of m.nose) {
                    const mesh = partMesh(this, part);
                    if (!mesh) continue;
                    mesh.material = mat(part.role, "dark");
                    mesh.parent = atNose;
                    mesh.position = v3(...N.pivot).scale(-1);
                    noseParts.push(mesh);
                }
            }
        }
        const R = Math.max(0.1, Number(notes.wheel_radius) || WHEEL_R), W = R * WHEEL_W / WHEEL_R;
        const tyreM = this.material("ktyre", [1, 1, 1], 1.0, 0, 0, {tex: "tyre", tile: 2.5});
        const hubM = this.material("khub", [0.75, 0.75, 0.78], 0.5, 1.0, 0, {tex: "steel", probe: true});
        const wheels = [], wheelParts = [];
        for (const w of d.wheels) {
            const pivot = new BABYLON.TransformNode("pivot", this.scene);
            pivot.parent = root;
            pivot.position = v3(w.x, w.y, R);
            const spin = new BABYLON.TransformNode("spin", this.scene);
            spin.parent = pivot;
            const side = new BABYLON.TransformNode("side", this.scene);
            side.parent = spin;
            if (w.side < 0) side.rotation.y = Math.PI;  // (half round about the upright: its outer face to the right)
            const mine = [];
            if (this.ultra) {
                for (const [level, m] of levels) {
                    const at = holder(side, level);
                    for (const part of m.wheel) {
                        const mesh = partMesh(this, part);
                        if (!mesh) continue;
                        mesh.material = mat(part.role, "tyre");
                        mesh.parent = at;
                        mine.push(mesh);
                    }
                }
                // (CHANGE 174) the brake caliper: on the steering pivot, so it turns with the steering, not the wheel
                const brake = near && near.brake ? near.brake[w.side > 0 ? "left" : "right"] : null;
                if (brake) {
                    const at = holder(pivot, "near");
                    for (const part of brake) {
                        const mesh = partMesh(this, part);
                        if (!mesh) continue;
                        mesh.material = mat(part.role, "caliper");
                        mesh.parent = at;
                        mine.push(mesh);
                    }
                }
            } else {
                mine.push(this.cyl(side, R, W, "y", tyreM, 0, 0, 0, null, 20));
                mine.push(this.cyl(side, R * 0.6, W + 0.006, "y", hubM, 0, 0, 0, null, 14));
            }
            wheelParts.push(mine);
            wheels.push({pivot, spin, front: !!w.front});
        }
        this.shadowCast([...merged, ...wheelParts.flat(), ...noseParts]);
        const flame = this.kartFlame(root), glow = Array.isArray(notes.glow) ? notes.glow : [-1.3, 0, 0.3];
        flame.position = v3(glow[0] + 0.1, glow[1], glow[2]);
        let flameLines = null;
        if (this.wire) {  // (the line tiers: as the box kart's)
            const lines = this.lineMaterial("kart", 1, ...this.lineFade());
            this.linesMesh("kartlines", this.edgeLines(merged, this.wire, body), lines, body);
            flameLines = this.linesMesh("flamelines", this.edgeLines([flame], this.wire, flame), lines, flame);
            if (flameLines) flameLines.isVisible = false;
            wheels.forEach((w, i) => this.linesMesh("wheellines", this.edgeLines(wheelParts[i], this.wire, w.spin), lines, w.spin));
            if (nose) this.linesMesh("noselines", this.edgeLines(noseParts, this.wire, nose), lines, nose);
        }
        const rear = d.wheels.find(w => !w.front && w.y > 0) || {x: -0.76, y: 0.6}, L = notes.lamps;
        const lamps = L && Array.isArray(L.head) && Array.isArray(L.tail) && Array.isArray(L.size) ? L : LAMPS.kart;
        const smoke = Array.isArray(notes.smoke) ? notes.smoke : [0.75, 0, 0.62];
        const fit = {lamps, skid: [rear.x, rear.y], puff: [rear.x - 0.03, rear.y], smoke,
                     sparks: [glow[0] + 0.1, glow[1], glow[2] + 0.08], beamX: Math.max(0.6, lamps.head[0]),
                     hood: Array.isArray(notes.hood) ? notes.hood : [0.85, 0.75], label: Math.max(1.15, (Number(notes.height) || 1) + 0.3)};
        this.finishKart(design.id, design, root, body, wheels, flame, flameLines, R, this.ultra, fit);
        const k = this.karts.get(design.id);
        k.nose = nose;
        k.car = design.body;
        k.lod = lod;
    },

    rebuildKarts() {  // (every kart made again, as it is now: the curved kart arrived)
        for (const d of [...this.karts.values()].map(k => k.design)) this.addKart(d);
    },

    removeKart(id) {
        const k = this.karts.get(id);
        if (!k) return;
        k.label.dispose(false, true);
        k.root.dispose();  // (the materials are shared: kept)
        this.karts.delete(id);
        if (this.follow === id) this.follow = null;
        this.refreshLists();
    },

    // (moved here from KartScene.frame: a kart's or car's picture each frame, at its place st, z: the ground's
    // height under it) its near or far model, the body's pitch and lean, the boost, skid marks, sparks and smoke,
    // the wheels rolling and steering, damage, the lamps, the steering wheel
    carFrame(k, st, z, dt) {
        if (k.lod) {  // (CHANGE 174) a car's near or far model, by how far it is from the camera
            const nearNow = BABYLON.Vector3.Distance(this.camera.globalPosition, k.root.position) < k.lod.far;
            if (nearNow !== k.lod.state) {
                k.lod.state = nearNow;
                for (const n of k.lod.near) n.setEnabled(nearNow);
                for (const n of k.lod.farNodes) n.setEnabled(!nearNow);
            }
        }
        k.root.rotation.y = -st.yaw * Math.PI / 180;
        const drift = (st.flags & FLAG_DRIFT_L) ? 1 : (st.flags & FLAG_DRIFT_R) ? -1 : 0;
        // (kart_gfx.KartVisual.update, CHANGE 143) the body pitches with the acceleration, nose up as it speeds
        // up and down as it brakes (smoothed: v is quantised each tick), and leans with the slide (u < 0, the back
        // out to the right in a left turn: a lean right); in Babylon's axes a lean is -x, a nose dip -z
        const v = st.v || 0, step = Math.max(1e-4, dt);
        const accel = k.lastV === null ? 0 : (v - k.lastV) / step;
        k.lastV = v;
        const a = Math.min(1, step * 8);
        k.pitch += (clamp(-accel * 0.45, -5, 5) - k.pitch) * a;
        k.roll += (clamp(-(st.u || 0) * 2.2, -7, 7) - k.roll) * a;
        k.body.rotation.x = -k.roll * DEG;
        k.body.rotation.z = -k.pitch * DEG;
        const boosting = !!(st.flags & FLAG_BOOSTING);
        k.flame.isVisible = boosting;
        if (k.flameLines) k.flameLines.isVisible = boosting;
        if (boosting) {  // (the glow flickers: 0.9 to 1.15 times its size)
            k.glowT += dt;
            k.flame.scaling.setAll(0.9 + 0.25 * Math.sin(k.glowT * 31));
        }
        // (ultra, CHANGE 144) skid marks from both rear tyres while drifting above 3 m/s, sparks from the exhaust
        // while boosting
        if (this.skids) this.skidFrom(k, st, z, drift && Math.abs(v) > 3);
        if (this.sparks && boosting) {
            const h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h);
            const [sx, sy, sz] = k.fit.sparks;
            this.sparks.emit([st.x + sx * c - sy * s, st.y + sx * s + sy * c, z + sz], st.yaw, v, dt > 0.02 ? 3 : 2);
        }
        // drift smoke from each rear tyre in turn, every 0.07 s while drifting above 3 m/s (and while the back
        // wheels spin or lock, at any speed, thicker: CHANGE 181)
        const spinning = !!(st.flags & (FLAG_WHEELSPIN | FLAG_HANDBRAKE));
        if (this.smoke && ((drift && Math.abs(v) > 3) || spinning)) {
            k.puffTimer -= dt;
            if (k.puffTimer <= 0) {
                k.puffTimer = spinning ? 0.045 : 0.07;
                const [px, py] = k.fit.puff, side = k.nextPuff % 2 ? py : -py, h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h);
                k.nextPuff = (k.nextPuff + 1) % PUFFS;
                this.smoke.emit([st.x + px * c - side * s, st.y + px * s + side * c, z + 0.15]);
            }
        }
        k.spin += v * dt / (k.wheelR || WHEEL_R);
        // (CHANGE 157, kart_gfx.KartVisual.update) the steering as drawn eases towards the driver's (st.steer, -1
        // right to 1 left: the keys are all or nothing); the front wheels turn by it, up to 26 degrees, the
        // steering wheel three times as far, the hands stay on its rim and the head looks into the turn
        k.steerNow = (k.steerNow || 0) + (Math.max(-1, Math.min(1, st.steer || 0)) - (k.steerNow || 0)) * Math.min(1, dt * STEER_EASE);
        const steer = k.steerNow * MAX_STEER;
        // (CHANGE 158, kart_gfx.KartVisual.update) damage, each part 0 to 1: a damaged wheel leans and wobbles as it
        // turns, the fairing (or bumper) hangs from its left end, the engine smokes grey to black
        const dmg = DAMAGE_PARTS.map(p => Math.min(1, Math.max(0, (st[p] || 0) / DAMAGE_MAX)));
        k.wheels.forEach((w, i) => {
            w.spin.rotation.z = -k.spin;
            if (w.front) w.pivot.rotation.y = -steer;
            const d = dmg[1 + i] || 0;
            w.spin.rotation.x = d > 0.08 ? -(d * 7 + d * 9 * Math.sin(k.spin)) * DEG : 0;
        });
        if ((st.shield || 0) > 0 && !k.bubble) {  // (CHANGE 159) the shield: a pale blue bubble round the kart
            k.bubble = this.sphere(k.root, 1.25, this.glass("kshield", [0.45, 0.75, 1.0], 0.25, 0.4), 0, 0, 0.45, 1, 0.75, 0.6, 16, "shield");
            k.bubble.isPickable = false;
        }
        if (k.bubble) k.bubble.setEnabled((st.shield || 0) > 0);
        if (k.nose) {
            const hang = Math.max(0, Math.min(1, (dmg[0] - 0.2) / 0.6));
            k.nose.rotation.x = -hang * 11 * DEG;  // (its far end down to the road)
            k.nose.rotation.z = -hang * 16 * DEG;
        }
        if (this.smoke && dmg[5] > 0.35) {
            k.smokeTimer = (k.smokeTimer || 0) - dt;
            if (k.smokeTimer <= 0) {
                k.smokeTimer = 0.32 - 0.2 * dmg[5];
                const h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h);
                const [ex, ey, ez] = k.fit.smoke;
                this.smoke.emit([st.x + ex * c - ey * s, st.y + ex * s + ey * c, z + ez], 0.6 - 0.45 * dmg[5]);
            }
        }
        if (k.lamps) this.lampFrame(k.lamps, !!this.timeLook.lamps, !!(st.flags & FLAG_BRAKING));  // (CHANGE 171, 172)
        if (k.boxWheel) k.boxWheel.rotation.x = -steer * STEER_RATIO;
        if (k.steerWheel) {  // (the curved kart's steering wheel, turned as the front wheels times its ratio)
            const sw = k.steerWheel, q = sw.node.rotationQuaternion;
            BABYLON.Quaternion.RotationAxisToRef(sw.axis, -steer * sw.ratio, q);
            for (const a of sw.arms) {  // (each arm turned about its shoulder to point at its hand, carried round)
                const to = a.hand.subtract(sw.pivot).applyRotationQuaternion(q).addInPlace(sw.pivot);
                const from = a.hand.subtract(a.shoulder), want = to.subtract(a.shoulder);
                BABYLON.Quaternion.FromUnitVectorsToRef(from.normalizeToNew(), want.normalizeToNew(), a.arm.rotationQuaternion);
                a.arm.scaling.setAll(want.length() / from.length());
            }
            if (sw.head) {
                sw.head.node.rotation.y = -k.steerNow * sw.head.turn;
                sw.head.node.rotation.x = -k.steerNow * sw.head.lean;
            }
        }
    },

    // a kart's two rear tyres leave a strip on the road each 0.3 m while it drifts (on: drifting fast enough)
    skidFrom(k, st, z, on) {
        if (!on) { k.skid = null; return; }
        const h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h);
        const [rx, ry] = k.fit.skid;
        const at = side => [st.x + rx * c - side * ry * s, st.y + rx * s + side * ry * c, z + 0.035];
        const now = [at(1), at(-1)];
        if (k.skid && Math.hypot(now[0][0] - k.skid[0][0], now[0][1] - k.skid[0][1]) > 2.5) k.skid = null;  // (a respawn)
        if (!k.skid) { k.skid = now; return; }
        if (Math.hypot(now[0][0] - k.skid[0][0], now[0][1] - k.skid[0][1]) < 0.3) return;
        for (let i = 0; i < 2; i++) this.skids.add(k.skid[i], now[i]);
        k.skid = now;
    },
};

// drift smoke (kart_gfx.KartVisual's puffs, CHANGE 143): soft grey puffs left behind in the world, rising at 0.6 m/s,
// growing from 0.35 m to 1.25 m and fading over 0.7 s. One pool for every kart, the oldest reused, drawn as one
// mesh's thin instances facing the camera (robotfx.js's way, with its shader: one draw call, the app's tone curve)
export class Smoke {
    constructor(sc, cap) {
        const scene = sc.scene;
        const m = new BABYLON.ShaderMaterial("ccfxkartsmoke", scene, {vertex: "ccfx", fragment: "ccfx"}, {
            attributes: ["position", "uv"], uniforms: ["world", "viewProjection", "baseColor", "exposure"],
            defines: ["SOFT"], needAlphaBlending: true});
        m.setColor4("baseColor", new BABYLON.Color4(1, 1, 1, 1));
        m.setFloat("exposure", sc.lighting ? sc.lighting.exposure : 0);
        m.alphaMode = BABYLON.Constants.ALPHA_COMBINE;
        m.disableDepthWrite = true;
        m.backFaceCulling = false;
        scene.setRenderingAutoClearDepthStencil(1, false, false, false);
        const mesh = this.mesh = BABYLON.MeshBuilder.CreatePlane("kartpuff", {size: 1}, scene);
        mesh.material = m;
        mesh.isPickable = false;
        mesh.alwaysSelectAsActiveMesh = true;  // (the instances move: no bounds kept)
        mesh.doNotSyncBoundingInfo = true;
        mesh.renderingGroupId = 1;  // (after the whole scene; the depth kept, so the stand and the trees still hide them)
        this.mats = new Float32Array(16 * cap);
        this.cols = new Float32Array(4 * cap);
        mesh.thinInstanceSetBuffer("matrix", this.mats, 16, false);
        mesh.thinInstanceSetBuffer("color", this.cols, 4, false);
        mesh.thinInstanceCount = 0;
        mesh.isVisible = false;
        this.items = Array.from({length: cap}, () => ({p: [0, 0, 0], life: 0}));
        this.cursor = 0;
    }

    emit(p, shade = 0.75) {  // a new puff at a game position (shade: grey, darker for a damaged engine's: CHANGE 158)
        const it = this.items[this.cursor];
        this.cursor = (this.cursor + 1) % this.items.length;
        it.p = p;
        it.life = PUFF_LIFE;
        it.shade = shade;
    }

    update(dt, cam) {
        const r = cam.getDirection(BABYLON.Axis.X), u = cam.getDirection(BABYLON.Axis.Y), f = cam.getDirection(BABYLON.Axis.Z);
        const M = this.mats, C = this.cols;
        let n = 0;
        for (const it of this.items) {
            if (it.life <= 0) continue;
            it.life -= dt;
            if (it.life <= 0) continue;
            it.p[2] += 0.6 * dt;
            const left = it.life / PUFF_LIFE, s = 0.35 + (1 - left) * 0.9;
            const o = n * 16, p = it.p;
            M[o] = r.x * s; M[o + 1] = r.y * s; M[o + 2] = r.z * s; M[o + 3] = 0;
            M[o + 4] = u.x * s; M[o + 5] = u.y * s; M[o + 6] = u.z * s; M[o + 7] = 0;
            M[o + 8] = f.x * s; M[o + 9] = f.y * s; M[o + 10] = f.z * s; M[o + 11] = 0;
            M[o + 12] = p[0]; M[o + 13] = p[2]; M[o + 14] = p[1]; M[o + 15] = 1;
            const c = n * 4;
            const g = it.shade ?? 0.75;
            C[c] = g; C[c + 1] = g; C[c + 2] = g * 1.04; C[c + 3] = 0.55 * left;
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
