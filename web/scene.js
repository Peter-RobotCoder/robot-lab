// Kart Lab drawn in the browser with Babylon.js, after the app's kart_gfx.py (CHANGE 131: part for part, with its
// colours, textures, roughness and lights): the road as a ribbon following the hills, kerbs, the barrier, the
// chequered start, cones at the sharp bends, the dash pads' glowing chevrons, oil, grass that follows the track and
// rolls away from it, trees, the grandstand and its roof, the start gantry, and the karts (a tub, a cowl, pods,
// bumpers, a driver in a helmet holding the wheel, a wing, an engine, tyres with hubs).
// The engine, tiers, materials and coordinate rules are base3d.js's (shared with Robot Lab and Fight Lab).
// (CHANGE 144) Every tier: mesh and lines draw the same meshes black with their edges as lines (base3d.js), and
// ultra adds kartfx.js's sky, land, after-effects, reflections, skid marks, sparks and the curved kart, and once
// models/kart_scenery.json has loaded draws the window's ultra circuit in place of the road, kerbs, grass and land.

/* global BABYLON */

import {BaseScene, TIERS, v3, mulberry, upwardNormals} from "./base3d.js";
import "./robotfx.js";  // (CHANGE 143: its particle shader, "ccfx", with the app's tone curve, for the drift smoke)
import {makeSky, makeLand, makeForest, AfterFx, Skids, Sparks, HAZE, loadUltraKart, ultraKartData, partMesh,
        loadScenery, sceneryData, makeCircuit, circuitFrame, cullLists} from "./kartfx.js";
import {TRACKS} from "./track.js";

export {TIERS};

const WHEEL_R = 0.2, WHEEL_W = 0.09;
// (CHANGE 157, kart_gfx's) the front wheels at full lock (radians), the steering wheel's turn to theirs, how fast the
// drawn steering follows the driver's (per second)
const MAX_STEER = 26 * Math.PI / 180, STEER_RATIO = 3.0, STEER_EASE = 10.0;
const WHEELS = [[0.5, 0.6], [0.5, -0.6], [-0.52, 0.62], [-0.52, -0.62]];  // x, y: FL, FR, RL, RR
const KERB_RED = [0.85, 0.12, 0.08, 1], KERB_WHITE = [0.95, 0.95, 0.92, 1];
const TARMAC_TINT = [0.9, 0.9, 0.92], GRASS_TINT = [0.95, 1.0, 0.9], STEEL = [0.6, 0.6, 0.62];
const FLAG_DRIFT_L = 1, FLAG_DRIFT_R = 2, FLAG_BOOSTING = 16;
const PUFFS = 8, PUFF_LIFE = 0.7;  // (kart_gfx.KartVisual.PUFFS: a kart's drift smoke; the scene's pool holds 12 karts' worth)
const DEG = Math.PI / 180;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
// kart_gfx.init: the sky, the sun 40 degrees up behind the kart, a blue fill, the daytime sky's reflections.
// (CHANGE 144) The sky's light, as the window has it since CHANGE 144 (kart_gfx.ENV_STRENGTH and ENV_FILL): the sky
// picture's colours read as a screen's (envSrgb; shScale: what that makes of the spherical harmonics make_textures.py
// worked out from the raw picture, measured from sky_reflect.png), the sky's light and reflections at 0.4 of that,
// and the ambient fill at 0.4 beside them (fill). Read raw and at full strength on top of the whole ambient, the sky
// gave about as much light again as the sun from every direction, and its grey-blue reflection over every surface
// turned the red kerbs pink and the karts pastel on medium and high. fog: ultra's haze, to the horizon's colour, as
// thick as the window's (kart_gfx.HAZE_DENSITY); ultraFilm: ultra's shadow, 64 m across (the window's)
const LOOK = {sky: [0.3, 0.5, 0.9], radius: 60, target: [30, 40, 0],
              pbr: {background: [0.3, 0.5, 0.9], exposure: 0.55, ambient: [0.22, 0.25, 0.32], sky: "sky",
                    envSrgb: true, shScale: [0.55, 0.65, 0.86], fill: [0.4, 0.4, 0.4], fog: {colour: HAZE, density: 0.0007},
                    sun: {colour: [2.6, 2.45, 2.2], offset: [30, -45, 45], film: 40, near: 50.4, far: 90.4, bias: 0.0015, ultraFilm: 64}}};

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = a => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

// a mesh built from quads in game coordinates (engine/rw_mesh.py's Mesh, for the track's pieces)
class Geo {
    constructor(coloured = false) {
        this.pos = []; this.nor = []; this.idx = []; this.col = coloured ? [] : null;
        this.colour = [1, 1, 1, 1];
    }

    quad(p, n = null) {  // four corners; n: the normal (else the corners' own, turned up)
        if (!n) {
            n = unit(cross(sub(p[1], p[0]), sub(p[3], p[0])));
            if (n[2] < 0) n = n.map(v => -v);
        }
        const b = this.pos.length / 3;
        for (const q of p) {
            this.pos.push(q[0], q[2], q[1]);
            this.nor.push(n[0], n[2], n[1]);
            if (this.col) this.col.push(...this.colour);
        }
        this.idx.push(b, b + 1, b + 2, b, b + 2, b + 3);
    }

    poly(p, n) {  // a flat fan
        const b = this.pos.length / 3;
        for (const q of p) {
            this.pos.push(q[0], q[2], q[1]);
            this.nor.push(n[0], n[2], n[1]);
            if (this.col) this.col.push(...this.colour);
        }
        for (let i = 1; i < p.length - 1; i++) this.idx.push(b, b + i, b + i + 1);
    }

    mesh(name, scene) {
        const m = new BABYLON.Mesh(name, scene);
        const vd = new BABYLON.VertexData();
        vd.positions = this.pos;
        vd.indices = this.idx;
        vd.normals = this.nor;
        if (this.col) vd.colors = this.col;
        vd.applyToMesh(m);
        return m;
    }
}

export class KartScene extends BaseScene {
    static TIERS = TIERS;  // (every tier, the line tiers and ultra too: CHANGE 144)
    // (CHANGE 151) ultra's pictures after the scene: the glow and a little sharpening on an 8x MSAA picture, as the
    // window's ultra; no SSAO, which the window hasn't either: its passes cost 6 ms a frame on this Iris Xe (22 ms to
    // 16 at 1400 x 850, even at a quarter of the pixels 20), and it darkened the trees more than the window's
    static ULTRA_FX = {ssao: false, sharpen: true, samples: 8, bloomWeight: 0.32};

    constructor(canvas, tier = "low", engine = null) {
        super(canvas, tier, engine, LOOK);
        this.karts = new Map();     // id -> visual
        this.hints = new Map();     // id -> last track segment (locate's hint)
        this.track = null;
        this.trackMeshes = [];
        this.follow = null;         // kart id the camera chases, or null for the TV camera
        this.mode = "tv";           // tv | chase | hood | overview
        // the camera as the window's (kart_gfx.ChaseCamera, CHANGE 143): where it is and looks (game coordinates,
        // eased), its field of view (degrees across), the zoom (the wheel, + and -: under 1 closer), the TV stand in use
        this.zoom = 1.0;
        this.camPos = this.camLook = null;
        this.camYaw = null;
        this.camFov = 70;
        this.camKart = undefined;
        this.tvIndex = 0;
        this.build();
    }

    build() {  // (ultra's after-effects let go before the scene they were made for: CHANGE 144)
        if (this.fx) { this.fx.dispose(); this.fx = null; }
        super.build();
    }

    // after build() (and again after a tier change): the track and the karts back in
    populate(rebuild) {
        // (the arrows drive: the camera doesn't turn with them; the drift smoke's pool, none on blocks or the line tiers)
        this.camera.inputs.removeByType("ArcRotateCameraKeyboardMoveInput");
        this.smoke = this.lit ? new Smoke(this, PUFFS * 12) : null;
        this.lineCount = 0;
        // (ultra, CHANGE 144) the sky, the world round the kart watched as a cube for the paint to reflect (made before
        // any material, so theirs can reflect it), skid marks, sparks, the after-effects; the curved kart asked for
        this.ultra = !!(this.settings.ultra && this.lighting);
        this.sky = this.probe = this.skids = this.sparks = this.fx = this.circuit = null;
        this.forest = [];
        this.probeKart = undefined;
        if (this.ultra) {
            this.sky = makeSky(this);
            this.probe = new BABYLON.ReflectionProbe("kartprobe", 256, this.scene, true);
            this.probe.refreshRate = 2;
            this.lighting.setProbe(this.probe.cubeTexture);
            this.skids = new Skids(this);
            this.sparks = new Sparks(this);
            this.fx = new AfterFx(this, KartScene.ULTRA_FX);
            this.camera.maxZ = 3000;  // (the mountains, 1.6 km off)
            const scene = this.scene;
            loadUltraKart().then(d => {  // (it came after the karts were made: made again, curved)
                if (d && this.scene === scene && [...this.karts.values()].some(k => !k.curved)) this.rebuildKarts();
            });
            loadScenery().then(d => {  // (the circuit came after the track was drawn: drawn again with it)
                if (d && this.scene === scene && this.trackData && !this.circuit && this.circuitKey(this.trackData)) this.setTrack(this.trackData);
            });
        }
        this.refreshLists();
        if (!rebuild) return;
        const track = this.trackData, karts = [...this.karts.values()].map(k => k.design);
        this.karts.clear();
        this.trackMeshes = [];
        if (track) this.setTrack(track);
        for (const d of karts) this.addKart(d);
    }

    // ---------- the track (kart_gfx.TrackVisual) ----------
    setTrack(data) {
        for (const m of this.trackMeshes) m.dispose();
        this.trackMeshes = [];
        this.trackData = data;
        const track = this.track = data;  // (a Track instance from track.js)
        const scene = this.scene;
        const statics = [];
        // (ultra, CHANGE 144) the window's ultra circuit (kartfx.js) once models/kart_scenery.json has loaded, in place
        // of the road, kerbs, barrier, start, cones, grass, scenery, land and woods; until then (or for a track the file
        // hasn't) those
        const file = this.ultra ? sceneryData() : null, key = this.circuitKey(track);
        this.circuit = file && key ? makeCircuit(this, file, key) : null;
        if (!this.circuit) this.road(statics);
        // dash pads: three glowing chevrons each (their glow pulses in frame())
        const pads = new Geo();
        for (const [ps, plat] of track.boosts) {
            for (let k = 0; k < 3; k++) {
                const a = ps - 1.6 + k * 1.3;
                for (const side of [1, -1]) {
                    const li = plat + side * 0.15, lo = plat + side * 1.3;
                    const p = [track.point(a + 0.9, li), track.point(a + 0.4, li), track.point(a - 0.9, lo), track.point(a - 0.4, lo)];
                    pads.quad(p.map(q => [q[0], q[1], q[2] + 0.02]));
                }
            }
        }
        this.padMat = null;
        if (pads.pos.length) {
            this.padMat = this.material("pads", [0.1, 0.06, 0.0], 0.4, 0, 0, {emission: [3.0, 1.6, 0.2]});
            const m = pads.mesh("pads", scene);
            m.material = this.padMat;
            this.trackMeshes.push(m);
        }
        // oil: dark shiny patches
        const oil = new Geo();
        for (const [os, olat] of track.oil) {
            const pts = [];
            for (let k = 0; k < 14; k++) {
                const a = 2 * Math.PI * k / 14, p = track.point(os + Math.cos(a) * 2.6, olat + Math.sin(a) * 1.9);
                pts.push([p[0], p[1], p[2] + 0.018]);
            }
            oil.poly(pts, [0, 0, 1]);
        }
        if (oil.pos.length) {
            const m = oil.mesh("oil", scene);
            m.material = this.material("oil", [0.16, 0.15, 0.2], 0.3, 0.4);
            statics.push(m);
        }
        if (this.circuit) {
            this.trackMeshes.push(...this.circuit.meshes);
            this.shadowCast(this.circuit.casters);
            this.forest = this.circuit.trees;
        } else {
            this.grass(statics);
            this.scenery(statics);
            if (this.ultra) this.land(statics);
        }
        this.trackMeshes.push(...this.mergeStatic(statics));
        if (this.wire) this.trackLines();
        this.refreshLists();
        this.setMode(this.mode, this.follow);
    }

    // (ultra, CHANGE 144) which of the file's circuits a track is (club, oval or straight: a track mod picks one of
    // them, so the name is enough), or null
    circuitKey(track) {
        return Object.keys(TRACKS).find(k => TRACKS[k].name === track.name) || null;
    }

    // the road, the centre line's dashes, the kerbs, the barrier, the chequered start and the cones at the sharp bends
    road(statics) {
        const track = this.track, half = track.half, L = track.length, scene = this.scene;
        const blocks = this.tier === "blocks";
        const put = (mesh, mat, cast = false) => {
            mesh.material = mat;
            statics.push(mesh);
            if (cast) this.shadowCast([mesh]);
            return mesh;
        };
        // the road: edge to edge, tarmac tiled every 8 m
        const road = new Geo();
        this.ribbon(road, 0, L, half + 0.3, -half - 0.3, 0.0);
        put(road.mesh("road", scene), this.material("tarmac", blocks ? [0.42, 0.42, 0.45] : TARMAC_TINT, 1.0, 0, 0, {tex: "tarmac", tile: 0.125}));
        // the centre line: white dashes, 2.5 m every 6 m
        const dashes = new Geo();
        for (let s = 3; s < L - 3; s += 6) this.ribbon(dashes, s, s + 2.5, 0.1, -0.1, 0.012, 2.5);
        put(dashes.mesh("dashes", scene), this.material("dashes", [0.85, 0.85, 0.8], 0.7));
        // kerbs (red and white, 2 m blocks), the barrier a metre outside (4 m blocks, every third red), the start's
        // chequers: vertex colours, one mesh
        const paint = new Geo(true);
        for (let s = 0, block = 0; s < L; block++) {
            const e = Math.min(L, s + 2);
            paint.colour = block % 2 ? KERB_RED : KERB_WHITE;
            for (const side of [1, -1]) this.ribbon(paint, s, e, side * (half - 0.55), side * (half + 0.2), 0.03, 2.0);
            s = e;
        }
        const wallIn = half + 1.0, wallOut = half + 1.5, wallH = 0.55;
        for (let s = 0, block = 0; s < L; block++) {
            const e = Math.min(L, s + 4);
            paint.colour = block % 3 === 2 ? [0.8, 0.1, 0.08, 1] : [0.92, 0.92, 0.9, 1];
            const left = this.leftOf((s + e) / 2);
            for (const side of [1, -1]) {
                const lower = p => [p[0], p[1], p[2] - 0.3];
                const a0 = lower(track.point(s, side * wallIn)), a1 = lower(track.point(e, side * wallIn));
                const b0 = lower(track.point(s, side * wallOut)), b1 = lower(track.point(e, side * wallOut));
                const up = [0, 0, wallH], n = left.map(v => v * side);
                paint.quad([a0, a1, add3(a1, up), add3(a0, up)], n.map(v => -v));
                paint.quad([b1, b0, add3(b0, up), add3(b1, up)], n);
                paint.quad([add3(a0, up), add3(a1, up), add3(b1, up), add3(b0, up)], [0, 0, 1]);
            }
            s = e;
        }
        const sq = 0.5, cols = Math.round(2 * half / sq);
        for (let i = 0; i < cols; i++) {
            for (let j = 0; j < 3; j++) {
                paint.colour = (i + j) % 2 ? [0.05, 0.05, 0.05, 1] : [0.95, 0.95, 0.92, 1];
                const lat = -half + i * sq;
                this.ribbon(paint, j * sq - 1.5 * sq, (j + 1) * sq - 1.5 * sq, lat + sq, lat, 0.015, sq);
            }
        }
        put(paint.mesh("paint", scene), this.material("paint", [1, 1, 1], 0.75), true);
        // cones at the apex of each sharp bend
        const cones = [];
        for (let s = 0; s < L; s += 3) {
            const c = this.curvature(s, 18);
            if (Math.abs(c) >= 30) {
                const side = c > 0 ? 1 : -1;
                for (let k = 0; k < 3; k++) {
                    const p = track.point(s + k * 4, side * (half + 0.6));
                    cones.push(this.cyl(null, 0.16, 0.3, "z", this.material("cone", [1.0, 0.45, 0.08], 0.6), p[0], p[1], p[2] + 0.25, 0.03, 10));
                }
                s += 24;
            }
        }
        statics.push(...cones);
        this.shadowCast(cones);
    }

    // (ultra, CHANGE 144) hills all round in the haze with the country out to them, and woods: firs in the grass,
    // clear of the track and the grandstand, and in clumps out on the country (kartfx.js)
    land(statics) {
        const t = this.track, half = t.half, L = t.length;
        const base = Math.min(...t.pts.map(p => p[2])) - 0.8;  // (the grass's level away from the track: grass()'s)
        const {land, mountains, centre, inner, flat} = makeLand(this, t, base);
        statics.push(land, mountains);
        const g = this.ground, gx0 = g.xs[0], gx1 = g.xs[g.xs.length - 1], gy0 = g.ys[0], gy1 = g.ys[g.ys.length - 1];
        const onGrass = (x, y) => x > gx0 + 2 && x < gx1 - 2 && y > gy0 + 2 && y < gy1 - 2;
        const rnd = mulberry(37), spots = [];
        const free = (x, y, gap) => !spots.some(q => Math.abs(q[0] - x) < gap && Math.abs(q[1] - y) < gap);
        for (let tries = 0; spots.length < 70 && tries < 1500; tries++) {
            const x = gx0 + rnd() * (gx1 - gx0), y = gy0 + rnd() * (gy1 - gy0);
            if (!this.clearOfTrack(x, y, 8) || !free(x, y, 4)) continue;
            const at = t.locate(x, y, null);
            if (at.dist < half + 24 && (at.s < 34 || at.s > L - 20)) continue;  // (the grandstand's spot)
            spots.push([x, y, this.groundAt(x, y), 4 + rnd() * 3, rnd() < 0.3]);
        }
        for (let clump = 0; clump < 30; clump++) {
            const a = rnd() * 2 * Math.PI, r = inner + 40 + rnd() * (flat - inner - 60);
            const cx = centre[0] + Math.cos(a) * r, cy = centre[1] + Math.sin(a) * r, round = rnd() < 0.35;
            for (let k = 0, n = 6 + Math.floor(rnd() * 10); k < n; k++) {
                const x = cx + (rnd() - 0.5) * 30, y = cy + (rnd() - 0.5) * 30;
                if (!this.clearOfTrack(x, y, 10) || !free(x, y, 3.5)) continue;
                spots.push([x, y, onGrass(x, y) ? this.groundAt(x, y) : base - 1.0, (round ? 4 : 5) + rnd() * 4, round]);
            }
        }
        this.forest = makeForest(this, spots);
        this.trackMeshes.push(...this.forest);
        this.shadowCast(this.forest);
    }

    // (ultra) what the geometry buffer (the shading in corners) and the reflection cube draw: the world and the karts,
    // not the labels, the smoke or the sky; the cube not the kart it sits on (the one watched). The circuit's meshes
    // say (CHANGE 144): the shading in corners leaves out the far country and the grass's blades (ccAO), the cube
    // the shapes placed by the thousand (ccProbe: the trees, the crowd, the tyres, every tuft; six views every other
    // frame of those would cost more than the whole picture)
    refreshLists() {
        if (!this.ultra) return;
        const world = this.trackMeshes.filter(m => m.name !== "sign" && !m.isDisposed());
        const karts = [];
        for (const [id, k] of this.karts) karts.push(...k.root.getChildMeshes(false).filter(m => m !== k.label && m !== k.flame).map(m => [id, m]));
        if (this.fx && this.fx.gbuffer) this.fx.gbuffer.renderList = [...world.filter(m => m.ccAO !== false), ...karts.map(([, m]) => m)];
        if (this.probe) this.probe.renderList.splice(0, this.probe.renderList.length, this.sky, ...world.filter(m => m.ccProbe !== false),
                                                     ...karts.filter(([id]) => id !== this.probeKart).map(([, m]) => m));
        if (this.circuit && this.circuit.cells) cullLists(this);  // (CHANGE 151: the circuit's copies by cell, where wanted)
    }

    // (the line tiers, CHANGE 144) the track's, the ground's and the scenery's edges as one lines mesh; on lines a
    // grid on the ground every 10 m, dimmer, following its hills (the road and the scenery hide it where they stand)
    trackLines() {
        const t0 = performance.now(), fill = this.wireFill(), before = this.lineCount || 0;
        const solid = this.trackMeshes.filter(m => m.material === fill);
        this.trackMeshes.push(...this.staticLines("tracklines", this.edgeLines(solid, this.wire), this.lineMaterial("track", 1, ...this.lineFade())));
        if (this.wire === "outline") {
            const g = this.ground, pos = [], idx = [], step = 1.5;
            const x0 = g.xs[0], x1 = g.xs[g.xs.length - 1], y0 = g.ys[0], y1 = g.ys[g.ys.length - 1];
            const run = (ax, ay, bx, by) => {  // (a straight line on the ground, a point every 1.5 m)
                const n = Math.max(1, Math.ceil(Math.hypot(bx - ax, by - ay) / step)), b = pos.length / 3;
                for (let i = 0; i <= n; i++) {
                    const x = ax + (bx - ax) * i / n, y = ay + (by - ay) * i / n;
                    pos.push(x, this.groundAt(x, y) + 0.05, y);
                    if (i) idx.push(b + i - 1, b + i);
                }
            };
            for (let x = Math.ceil(x0 / 10) * 10; x <= x1; x += 10) run(x, y0, x, y1);
            for (let y = Math.ceil(y0 / 10) * 10; y <= y1; y += 10) run(x0, y, x1, y);
            this.trackMeshes.push(...this.staticLines("grid", {pos, idx}, this.lineMaterial("grid", 0.42, 60, 380)));
        }
        this.lineStats = {segments: (this.lineCount || 0) - before, ms: Math.round(performance.now() - t0)};
    }

    lineFade() {  // (where the lines fade out, as the window's black fog: mesh's many lines sooner)
        return this.wire === "all" ? [15, 140] : [60, 380];
    }

    // the ground's height at (x, y) on its own triangles (each 3 m cell cut corner to corner as grass() cuts it)
    groundAt(x, y) {
        const g = this.ground, cols = g.xs.length;
        const fx0 = (x - g.xs[0]) / g.cell, fy0 = (y - g.ys[0]) / g.cell;
        const i = Math.min(cols - 2, Math.max(0, Math.floor(fx0))), j = Math.min(g.ys.length - 2, Math.max(0, Math.floor(fy0)));
        const fx = Math.min(1, Math.max(0, fx0 - i)), fy = Math.min(1, Math.max(0, fy0 - j));
        const h00 = g.z[j * cols + i], h10 = g.z[j * cols + i + 1], h01 = g.z[(j + 1) * cols + i], h11 = g.z[(j + 1) * cols + i + 1];
        return fx >= fy ? h00 + fx * (h10 - h00) + fy * (h11 - h10) : h00 + fy * (h01 - h00) + fx * (h11 - h01);
    }

    // quads along the track from s0 to s1 between two lateral offsets, lifted off the road
    ribbon(geo, s0, s1, a, b, lift, step = 1.2) {
        const t = this.track, n = Math.max(1, Math.ceil((s1 - s0) / step));
        let prev = null;
        for (let i = 0; i <= n; i++) {
            const s = s0 + (s1 - s0) * i / n;
            const p = t.point(s, a), q = t.point(s, b);
            const edge = [[p[0], p[1], p[2] + lift], [q[0], q[1], q[2] + lift]];
            if (prev) geo.quad([prev[0], edge[0], edge[1], prev[1]]);
            prev = edge;
        }
    }

    leftOf(s) {  // the unit vector pointing left across the track at s
        const h = this.track.heading(s) * Math.PI / 180;
        return [-Math.sin(h), Math.cos(h), 0];
    }

    curvature(s, ahead = 15) {  // degrees the track turns between s and s + ahead (positive: left)
        const h0 = this.track.heading(s), h1 = this.track.heading(s + ahead);
        return ((h1 - h0 + 180) % 360 + 360) % 360 - 180;
    }

    // the grass: a grid at the height of the nearest bit of track, easing to a base level away from it, with
    // gentle rolling bumps (kart_gfx.TrackVisual.grass)
    grass(statics) {
        const track = this.track, half = track.half;
        const [x0, y0, x1, y1] = track.bounds();
        const margin = 45, cell = 3;
        const xs = [], ys = [];
        for (let x = x0 - margin; x < x1 + margin + cell; x += cell) xs.push(x);
        for (let y = y0 - margin; y < y1 + margin + cell; y += cell) ys.push(y);
        const base = Math.min(...track.pts.map(p => p[2])) - 0.8;
        const pos = [], idx = [], z = [];
        for (let j = 0; j < ys.length; j++) {
            for (let i = 0; i < xs.length; i++) {
                const x = xs[i], y = ys[j], at = track.locate(x, y, null);
                let e = Math.min(1, Math.max(0, (at.dist - half - 2) / 30));
                e = e * e * (3 - 2 * e);
                const bumps = 0.8 * Math.sin(x * 0.07 + 1) * Math.cos(y * 0.05) * e;
                const h = (track.point(at.s)[2] - 0.06) * (1 - e) + base * e + bumps;
                z.push(h);
                pos.push(x, h, y);
            }
        }
        const cols = xs.length;
        for (let j = 0; j < ys.length - 1; j++) {
            for (let i = 0; i < cols - 1; i++) {
                const a = j * cols + i;
                idx.push(a, a + 1, a + cols + 1, a, a + cols + 1, a + cols);
            }
        }
        const mesh = new BABYLON.Mesh("grass", this.scene);
        const vd = new BABYLON.VertexData();
        vd.positions = pos;
        vd.indices = idx;
        vd.normals = upwardNormals(pos, idx);
        vd.applyToMesh(mesh);
        mesh.material = this.material("grass", this.tier === "blocks" ? [0.4, 0.66, 0.32] : GRASS_TINT, 1.0, 0, 0, {tex: "grass", tile: 0.2});
        statics.push(mesh);
        this.ground = {xs, ys, z, cell};
    }

    groundZ(x, y) {
        const g = this.ground;
        const i = Math.min(g.xs.length - 1, Math.max(0, Math.round((x - g.xs[0]) / g.cell)));
        const j = Math.min(g.ys.length - 1, Math.max(0, Math.round((y - g.ys[0]) / g.cell)));
        return g.z[j * g.xs.length + i];
    }

    clearOfTrack(x, y, margin) {
        const t = this.track;
        for (let i = 0; i < t.pts.length; i += 3) if (Math.hypot(x - t.pts[i][0], y - t.pts[i][1]) <= t.half + margin) return false;
        return true;
    }

    // trees, the grandstand by the start with its roof, and the start gantry (kart_gfx.TrackVisual.scenery)
    scenery(statics) {
        const t = this.track, half = t.half, L = t.length, scene = this.scene;
        const rnd = mulberry(11);
        const placed = [], casters = [];
        const trunkM = this.material("trunk", [0.35, 0.22, 0.12], 1.0), crownM = this.material("crown", [0.12, 0.42, 0.16], 1.0);
        for (let tries = 0; placed.length < 28 && tries < 400; tries++) {
            const s = rnd() * L, side = rnd() < 0.5 ? 1 : -1;
            const [x, y] = t.point(s, side * (half + 7 + rnd() * 17));
            if (!this.clearOfTrack(x, y, 4) || placed.some(([a, b]) => Math.hypot(x - a, y - b) < 6)) continue;
            if (s < 30 || s > L - 15) continue;  // (the grandstand's spot)
            placed.push([x, y]);
            const z = this.groundZ(x, y), h = 3.5 + rnd() * 2;
            statics.push(this.cyl(null, 0.22, h * 0.25, "z", trunkM, x, y, z + h * 0.25, null, 8));
            const crown = this.cyl(null, h * 0.32, h * 0.38, "z", crownM, x, y, z + h * 0.5 + h * 0.38, 0, 10);
            statics.push(crown);
            casters.push(crown);
        }
        // the grandstand: three tiers facing the track on the left of the start straight
        const stand = new Geo();
        const s0 = -6, s1 = 22, left = this.leftOf((s0 + s1) / 2), along = [left[1], -left[0], 0];
        for (let k = 0; k < 3; k++) {
            const la = half + 5 + k * 1.6, lb = half + 5 + (k + 1) * 1.6, hgt = 0.9 + k * 0.9;
            const a0 = t.point(s0, la), a1 = t.point(s1, la), b0 = t.point(s0, lb), b1 = t.point(s1, lb);
            const baseZ = Math.min(this.groundZ(a0[0], a0[1]), this.groundZ(a1[0], a1[1])) - 0.3;
            for (const p of [a0, a1, b0, b1]) p[2] = baseZ;
            const up = [0, 0, hgt];
            stand.quad([a1, a0, add3(a0, up), add3(a1, up)], left.map(v => -v));
            stand.quad([add3(a0, up), add3(a1, up), add3(b1, up), add3(b0, up)], [0, 0, 1]);
            stand.quad([a0, b0, add3(b0, up), add3(a0, up)], along.map(v => -v));
            stand.quad([b1, a1, add3(a1, up), add3(b1, up)], along);
            if (k === 2) stand.quad([b0, b1, add3(b1, up), add3(b0, up)], left);
        }
        const standMesh = stand.mesh("stand", scene);
        standMesh.material = this.material("stand", [0.55, 0.58, 0.66], 1.0, 0, 0, {tex: "concrete", tile: 0.5});
        statics.push(standMesh);
        casters.push(standMesh);
        const steel = this.material("steel", STEEL, 0.6, 1.0, 0, {tex: "steel"});
        for (const s of [s0 + 1, (s0 + s1) / 2, s1 - 1]) {
            const [x, y] = t.point(s, half + 9.5), z = this.groundZ(x, y);
            const post = this.cyl(null, 0.12, 2.6, "z", steel, x, y, z + 2.6, null, 8);
            statics.push(post);
            casters.push(post);
        }
        const roof = new Geo();
        const r0 = t.point(s0, half + 4.6), r1 = t.point(s1, half + 4.6), q0 = t.point(s0, half + 10.2), q1 = t.point(s1, half + 10.2);
        const zr = this.groundZ(q0[0], q0[1]) + 5.1;
        r0[2] = r1[2] = zr + 0.6;
        q0[2] = q1[2] = zr;
        roof.quad([r0, r1, q1, q0], [0, 0, 1]);
        const roofMesh = roof.mesh("roof", scene);
        roofMesh.material = this.material("roof", [0.85, 0.15, 0.12], 0.7);
        statics.push(roofMesh);
        casters.push(roofMesh);
        // the start gantry: two posts and a beam over the line, with START on both sides
        for (const side of [1, -1]) {
            const [x, y, z] = t.point(0, side * (half + 1.8));
            const post = this.cyl(null, 0.14, 2.6, "z", steel, x, y, z + 2.6, null, 10);
            statics.push(post);
            casters.push(post);
        }
        const a = t.point(0, half + 1.8), b = t.point(0, -half - 1.8), mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2];
        const beam = this.box(null, 0.2, Math.hypot(a[0] - b[0], a[1] - b[1]) / 2 + 0.2, 0.2, steel, mid[0], mid[1], mid[2] + 5.2);
        beam.rotation.y = -t.heading(0) * Math.PI / 180;
        statics.push(beam);
        casters.push(beam);
        for (const face of [1, -1]) {  // (readable from both sides: each faces its way, a little in front of the beam)
            const h = (t.heading(0) + (face > 0 ? 90 : -90)) * Math.PI / 180;
            const sign = this.signText("START", 4.4);
            sign.position = v3(mid[0] + 0.25 * face * Math.sin(h), mid[1] - 0.25 * face * Math.cos(h), mid[2] + 5.6);
            sign.rotation.y = -h;
            this.trackMeshes.push(sign);
        }
        this.shadowCast(casters);
    }

    // a word standing up, lit from inside (the gantry's sign)
    signText(text, width) {
        const plane = BABYLON.MeshBuilder.CreatePlane("sign", {width, height: width / 4}, this.scene);
        const tex = new BABYLON.DynamicTexture("signtex", {width: 512, height: 128}, this.scene, true);
        tex.hasAlpha = true;
        tex.getContext().clearRect(0, 0, 512, 128);
        tex.drawText(text, null, 100, "bold 100px sans-serif", "#ffffff", null, true, true);
        const m = new BABYLON.StandardMaterial("signmat", this.scene);
        m.diffuseTexture = tex;
        m.useAlphaFromDiffuseTexture = true;
        m.emissiveColor = new BABYLON.Color3(1, 1, 1);
        m.disableLighting = true;
        m.backFaceCulling = true;
        plane.material = m;
        plane.isPickable = false;
        return plane;
    }

    // ---------- the karts (kart_gfx.KartVisual) ----------
    addKart(design) {
        const id = design.id;
        if (this.karts.has(id)) this.removeKart(id);
        const scene = this.scene;
        const colour = (design.colour || [220, 60, 50]).map(v => v / 255);
        const root = new BABYLON.TransformNode("kart" + id, scene);
        const body = new BABYLON.TransformNode("body" + id, scene);
        body.parent = root;
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
        box(0.08, 0.55, 0.05, dark, 0.8, 0, z0 + 0.06);                                  // bumpers
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
        this.shadowCast([...merged, ...wheelParts, ...wheelBits]);
        let flameLines = null;
        if (this.wire) {  // (the line tiers: the body's edges with the body, each wheel's turning with its wheel)
            const mat = this.lineMaterial("kart", 1, ...this.lineFade());
            this.linesMesh("kartlines", this.edgeLines(merged, this.wire, body), mat, body);
            flameLines = this.linesMesh("flamelines", this.edgeLines([flame], this.wire, flame), mat, flame);
            if (flameLines) flameLines.isVisible = false;
            wheels.forEach((w, i) => this.linesMesh("wheellines", this.edgeLines(wheelParts.slice(i * 2, i * 2 + 2), this.wire, w.spin), mat, w.spin));
            this.linesMesh("steerlines", this.edgeLines(wheelBits, this.wire, boxWheel), mat, boxWheel);
        }
        this.finishKart(id, design, root, body, wheels, flame, flameLines, WHEEL_R, false);
        this.karts.get(id).boxWheel = boxWheel;
    }

    kartFlame(root) {  // the boost's glow behind the kart (shown while boosting)
        const flame = this.box(root, 0.25, 0.08, 0.06, this.material("flame", [1.0, 0.6, 0.15], 0.3, 0, 0, {emission: [3.0, 1.4, 0.3]}), -1.0, 0, 0.28);
        flame.isVisible = false;
        return flame;
    }

    finishKart(id, design, root, body, wheels, flame, flameLines, wheelR, curved) {
        const label = this.makeLabel(design.name || "", "#ffffff", 1.3);  // (about the app's size: a kart's width)
        label.parent = root;
        label.position = v3(0, 0, 1.15);
        this.karts.set(id, {root, body, wheels, flame, flameLines, label, design, lastYaw: 0, spin: 0, wheelR, curved,
                            lastV: null, pitch: 0, roll: 0, glowT: 0, puffTimer: 0, nextPuff: 0, skid: null});
        this.refreshLists();
    }

    // (ultra, CHANGE 144) the curved kart from models/kart_ultra.json (kartfx.js reads it): each part in the
    // material its role names (the file's notes.roles give each role's colour, roughness and metal: the design's
    // colour where it has none), smooth paint under a clear coat, the wheels on the same steering pivots and
    // rolling spinners as the box kart's (a right-hand wheel is the left's turned half round, as the file says),
    // and the steering wheel turning with the front wheels about the file's axis (notes.steering)
    addCurvedKart(design, root, body, colour) {
        const d = ultraKartData(), scale = Number(d.scale) || 1, notes = d.notes && typeof d.notes === "object" ? d.notes : {};
        const roles = notes.roles && typeof notes.roles === "object" ? notes.roles : {};
        const second = Array.isArray(design.colour2) ? design.colour2.map(v => v / 255) : colour;
        const COAT = {paint: 1, paint2: 1, helmet: 0.8}, SHINY = ["paint", "paint2", "helmet", "metal", "chrome", "rim", "glass"];
        const BASE = {paint: [colour, 0.32, 0.15], paint2: [second, 0.32, 0.15], dark: [[0.07, 0.07, 0.08], 0.55, 0],
                      metal: [[0.62, 0.63, 0.66], 0.35, 1], chrome: [[0.92, 0.92, 0.94], 0.08, 1], glass: [[0.03, 0.035, 0.05], 0.04, 0],
                      tyre: [[0.11, 0.11, 0.12], 0.8, 0], rim: [[0.78, 0.79, 0.82], 0.28, 1], seat: [[0.09, 0.09, 0.11], 0.4, 0],
                      skin: [[0.86, 0.66, 0.53], 0.6, 0], helmet: [[0.95, 0.95, 0.95], 0.18, 0.05]};
        const mats = {};
        const mat = role => {
            if (mats[role]) return mats[role];
            const [rgb0, rough0, metal0] = BASE[role] || BASE.paint, r = roles[role] || {};
            const rgb = Array.isArray(r.colour) && r.colour.length >= 3 ? r.colour.slice(0, 3)
                : r.colour === null && role !== "paint2" ? colour : rgb0;  // (null: the design's colour, the helmet's too)
            const rough = Number.isFinite(r.rough) ? r.rough : rough0, metal = Number.isFinite(r.metal) ? r.metal : metal0;
            const opts = {clearcoat: COAT[role] || 0, probe: SHINY.includes(role)};
            if (role === "tyre") Object.assign(opts, {tex: "tyre", tile: 2.5});
            return (mats[role] = role === "glass" ? this.glass("kvisor", rgb, 0.75) : this.material("kc" + role, rgb, rough, metal, 0, opts));
        };
        const parts = [];
        for (const part of d.body) {
            const mesh = partMesh(this, part, scale);
            if (!mesh) continue;
            mesh.material = mat(BASE[part.role] ? part.role : "paint");
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
                mesh.material = mat(BASE[part.role] ? part.role : "dark");
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
                mesh.material = mat(BASE[part.role] ? part.role : "dark");
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
                    mesh.material = mat(BASE[part.role] ? part.role : "helmet");
                    mesh.parent = head;
                    mesh.position = neck.scale(-1);
                    this.shadowCast([mesh]);
                }
                steerWheel.head = {node: head, turn: (Number(H.turn) || 16) * Math.PI / 180, lean: (Number(H.lean) || 7) * Math.PI / 180};
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
                mesh.material = mat(BASE[part.role] ? part.role : "tyre");
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
    }

    rebuildKarts() {  // (every kart made again, as it is now: the curved kart arrived)
        for (const d of [...this.karts.values()].map(k => k.design)) this.addKart(d);
    }

    removeKart(id) {
        const k = this.karts.get(id);
        if (!k) return;
        k.label.dispose(false, true);
        k.root.dispose();  // (the materials are shared: kept)
        this.karts.delete(id);
        if (this.follow === id) this.follow = null;
        this.refreshLists();
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
            if (!st) { k.root.setEnabled(false); k.lastV = null; continue; }
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
                this.sparks.emit([st.x - 0.75 * c - 0.28 * s, st.y - 0.75 * s + 0.28 * c, z + 0.38], st.yaw, v, dt > 0.02 ? 3 : 2);
            }
            // drift smoke from each rear tyre in turn, every 0.07 s while drifting above 3 m/s
            if (this.smoke && drift && Math.abs(v) > 3) {
                k.puffTimer -= dt;
                if (k.puffTimer <= 0) {
                    k.puffTimer = 0.07;
                    const side = k.nextPuff % 2 ? 0.6 : -0.6, h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h);
                    k.nextPuff = (k.nextPuff + 1) % PUFFS;
                    this.smoke.emit([st.x - 0.55 * c - side * s, st.y - 0.55 * s + side * c, z + 0.15]);
                }
            }
            k.spin += v * dt / (k.wheelR || WHEEL_R);
            // (CHANGE 157, kart_gfx.KartVisual.update) the steering as drawn eases towards the driver's (st.steer, -1
            // right to 1 left: the keys are all or nothing); the front wheels turn by it, up to 26 degrees, the
            // steering wheel three times as far, the hands stay on its rim and the head looks into the turn
            k.steerNow = (k.steerNow || 0) + (Math.max(-1, Math.min(1, st.steer || 0)) - (k.steerNow || 0)) * Math.min(1, dt * STEER_EASE);
            const steer = k.steerNow * MAX_STEER;
            for (const w of k.wheels) {
                w.spin.rotation.z = -k.spin;
                if (w.front) w.pivot.rotation.y = -steer;
            }
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
        }
        if (this.padMat && this.lighting) {  // the dash pads pulse (kart_gfx.TrackVisual.update)
            const glow = 2.4 + 1.2 * Math.sin(performance.now() / 1000 * 5);
            this.padMat.setVector3("emission", new BABYLON.Vector3(glow, glow * 0.55, glow * 0.07));
        }
        this.updateCamera(states, dt);
        if (this.smoke) this.smoke.update(dt, this.camera);
        if (this.ultra) this.ultraFrame(dt);
        this.followSun();
    }

    // (ultra) the skid marks and sparks moved on; the reflection cube with the kart the camera watches (inside it,
    // so left out of what it draws)
    ultraFrame(dt) {
        this.skids.update(dt);
        this.sparks.update(dt, this.camera);
        // (CHANGE 151) the circuit's start lights follow the countdown (kart.js sets it) and its pond's ripples drift
        if (this.circuit) circuitFrame(this.circuit, performance.now() / 1000, this.countdown ?? null);
        const id = this.camKart !== undefined && this.karts.has(this.camKart) ? this.camKart
            : this.follow !== null && this.karts.has(this.follow) ? this.follow : this.leader;
        const k = this.karts.get(id);
        if (id !== this.probeKart) { this.probeKart = id; this.refreshLists(); }
        if (k) this.probe.position.set(k.root.position.x, k.root.position.y + 0.55, k.root.position.z);
        else this.probe.position.copyFrom(this.camera.target);
    }

    // a kart's two rear tyres leave a strip on the road each 0.3 m while it drifts (on: drifting fast enough)
    skidFrom(k, st, z, on) {
        if (!on) { k.skid = null; return; }
        const h = st.yaw * DEG, c = Math.cos(h), s = Math.sin(h);
        const at = side => [st.x - 0.52 * c - side * 0.62 * s, st.y - 0.52 * s + side * 0.62 * c, z + 0.035];
        const now = [at(1), at(-1)];
        if (k.skid && Math.hypot(now[0][0] - k.skid[0][0], now[0][1] - k.skid[0][1]) > 2.5) k.skid = null;  // (a respawn)
        if (!k.skid) { k.skid = now; return; }
        if (Math.hypot(now[0][0] - k.skid[0][0], now[0][1] - k.skid[0][1]) < 0.3) return;
        for (let i = 0; i < 2; i++) this.skids.add(k.skid[i], now[i]);
        k.skid = now;
    }

    // ---------- the cameras (kart_gfx.ChaseCamera, CHANGE 143) ----------
    // chase: behind and above the kart, lagging its yaw a little so turns read, further back, higher and wider at
    // speed; hood: from the nose, looking down the road; tv: six fixed stands round the circuit, the nearest one
    // watching the kart and zoomed to fit it. Each eases to where it wants to be (a steady exponential approach) and
    // is zoomed by the field of view (zoomBy). The kart watched: the one followed, else the leader.
    tvCameras() {  // six camera stands, on the outside of each bend, 5 m up
        const t = this.track;
        if (this.tvTrack === t) return this.tvPoints;
        const pts = [];
        for (let k = 0; k < 6; k++) {
            const s = (k + 0.5) * t.length / 6;
            const side = this.curvature(s, 30) > 0 ? -1 : 1;  // (a left bend: the camera on the right, across the apex)
            const [x, y, z] = t.point(s, side * (t.half + 6.0));
            pts.push([x, y, z + 5.0]);
        }
        this.tvPoints = pts;
        this.tvTrack = t;
        return pts;
    }

    zoomBy(factor) {  // (ChaseCamera.wheel: the wheel's 0.88 a notch, + and - 0.8 and 1.25)
        this.zoom = clamp(this.zoom * Math.sqrt(factor), 0.6, 1.5);
    }

    cameraSettings() {  // what a learner's profile keeps of the camera (ChaseCamera.settings: the window's format)
        return {mode: this.mode, zoom: Math.round(this.zoom * 100) / 100};
    }

    resetCamera() {  // (Home) the zoom back to 1 and the view cut straight to where it belongs
        this.zoom = 1.0;
        this.setMode(this.mode, this.follow);
    }

    updateCamera(states, dt) {
        if (this.mode === "overview" || !this.track) return;  // (the whole track: Babylon's own orbit)
        const id = this.follow !== null && states.has(this.follow) ? this.follow : this.leader;
        const st = id !== null && id !== undefined ? states.get(id) : null, k = st ? this.karts.get(id) : null;
        if (!k) return;
        if (id !== this.camKart) { this.camKart = id; this.camPos = null; this.camYaw = null; }  // (another kart: cut to it)
        const p = k.root.position, tx = p.x, ty = p.z, tz = p.y;
        const yr = st.yaw * DEG, fx = Math.cos(yr), fy = Math.sin(yr);
        let want, look, fov, rate, near = 0.2;
        if (this.mode === "hood") {
            want = [tx + fx * 0.95, ty + fy * 0.95, tz + 0.62];  // (just over the nose plate)
            look = [tx + fx * 25, ty + fy * 25, tz + 0.3];
            fov = 82; rate = 60; near = 0.08;
        } else if (this.mode === "tv") {
            const pts = this.tvCameras(), d = pts.map(q => Math.hypot(q[0] - tx, q[1] - ty, q[2] - tz));
            let best = 0;
            for (let i = 1; i < d.length; i++) if (d[i] < d[best]) best = i;
            if (this.camPos === null || d[best] < d[this.tvIndex] * 0.85) this.tvIndex = best;  // (a little hysteresis)
            want = pts[this.tvIndex];
            look = [tx, ty, tz + 0.4];
            const dist = Math.hypot(want[0] - look[0], want[1] - look[1], want[2] - look[2]);
            fov = clamp(2 * Math.atan(7.0 / Math.max(1, dist)) / DEG, 14, 70);
            rate = 60;
        } else {  // chase
            if (this.camYaw === null) this.camYaw = st.yaw;
            const diff = ((st.yaw - this.camYaw + 180) % 360 + 360) % 360 - 180;
            this.camYaw += diff * Math.min(1, dt * 4.5);  // (lagging the kart's yaw: the kart turns in the frame)
            const cr = this.camYaw * DEG, speed = Math.max(0, st.v || 0);
            const dist = 5.2 + 0.07 * speed, height = 2.0 + 0.025 * speed;
            want = [tx - Math.cos(cr) * dist, ty - Math.sin(cr) * dist, tz + height];
            look = [tx + fx * 5, ty + fy * 5, tz + 0.6];
            fov = 72 + 0.25 * speed; rate = 14;
        }
        if (this.camPos === null) { this.camPos = want.slice(); this.camLook = look.slice(); this.camFov = fov; }
        const a = Math.min(1, dt * rate);
        for (let i = 0; i < 3; i++) {
            this.camPos[i] += (want[i] - this.camPos[i]) * a;
            this.camLook[i] += (look[i] - this.camLook[i]) * a;
        }
        this.camFov += (fov - this.camFov) * Math.min(1, dt * 4);
        const cam = this.camera;
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;  // (Panda's lens: the fov is across)
        cam.fov = clamp(this.camFov * this.zoom, 20, 110) * DEG;
        cam.minZ = near;
        // (the rig places the camera, as robot.js's: Babylon's own orbit limits and drift from the mouse are not for it)
        cam.lowerRadiusLimit = 0.01;
        cam.upperBetaLimit = Math.PI - 0.01;
        cam.inertialAlphaOffset = cam.inertialBetaOffset = cam.inertialRadiusOffset = cam.inertialPanningX = cam.inertialPanningY = 0;
        cam.setTarget(v3(...this.camLook));
        cam.setPosition(v3(...this.camPos));
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
        this.camPos = null;  // (cut straight to the new view)
        this.camYaw = null;
        this.camKart = undefined;
        if (mode === "overview") {  // (Babylon's own orbit again: its limits and lens)
            const cam = this.camera;
            cam.fovMode = BABYLON.Camera.FOVMODE_VERTICAL_FIXED;
            cam.fov = 0.8;
            cam.minZ = 0.1;
            cam.lowerRadiusLimit = 2;
            cam.upperBetaLimit = 1.5;
            this.overview();
        }
    }
}

// drift smoke (kart_gfx.KartVisual's puffs, CHANGE 143): soft grey puffs left behind in the world, rising at 0.6 m/s,
// growing from 0.35 m to 1.25 m and fading over 0.7 s. One pool for every kart, the oldest reused, drawn as one
// mesh's thin instances facing the camera (robotfx.js's way, with its shader: one draw call, the app's tone curve)
class Smoke {
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

    emit(p) {  // a new puff at a game position
        const it = this.items[this.cursor];
        this.cursor = (this.cursor + 1) % this.items.length;
        it.p = p;
        it.life = PUFF_LIFE;
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
            C[c] = 0.75; C[c + 1] = 0.75; C[c + 2] = 0.78; C[c + 3] = 0.55 * left;
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
