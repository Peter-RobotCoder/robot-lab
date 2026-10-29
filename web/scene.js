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
import {makeSky, makeLand, makeForest, AfterFx, Skids, Sparks, HAZE, loadUltraKart, loadScenery, sceneryData, makeCircuit,
        circuitFrame, cullLists} from "./kartfx.js";
import {TRACKS, KERB, LANE_RAMP, LANE_BAYS} from "./track.js";  // (KERB, the lane: CHANGE 177, 179)
import {CarParts, Smoke, TIME_LOOKS, HEADLIGHTS, PUFFS, STEEL} from "./cars.js";  // (the karts and cars: CHANGE 201)

export {TIERS};

const KERB_RED = [0.85, 0.12, 0.08, 1], KERB_WHITE = [0.95, 0.95, 0.92, 1];
const TARMAC_TINT = [0.9, 0.9, 0.92], GRASS_TINT = [0.95, 1.0, 0.9];
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
// (CHANGE 201: City Lab's city is lit as its window lights it, with these)
export const LOOK = {sky: [0.3, 0.5, 0.9], radius: 60, target: [30, 40, 0],
                     pbr: {background: [0.3, 0.5, 0.9], exposure: 0.55, ambient: [0.22, 0.25, 0.32], sky: "sky",
                           envSrgb: true, shScale: [0.55, 0.65, 0.86], fill: [0.4, 0.4, 0.4], fog: {colour: HAZE, density: 0.0007},
                           sun: {colour: [2.6, 2.45, 2.2], offset: [30, -45, 45], film: 40, near: 50.4, far: 90.4, bias: 0.0015, ultraFilm: 64}}};

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const unit = a => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };

// a mesh built from quads in game coordinates (engine/rw_mesh.py's Mesh, for the track's pieces)
export class Geo {  // (CHANGE 201: City Lab's city is built with it too)
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
        this.time = "day";          // (CHANGE 172) the race's time of day
        this.timeLook = TIME_LOOKS.day;
        this.build();
    }

    // (CHANGE 172) the race drawn at this time of day: "day", "dusk" or "night" (the scene is made again: the lighting's
    // shaders are made for their number of lights, and at dusk and night there are the headlights' too)
    setTime(t) {
        t = TIME_LOOKS[t] ? t : "day";
        if (t === this.time) return;
        this.time = t;
        this.applyTime();
        this.build();
    }

    applyTime() {
        const T = this.timeLook = TIME_LOOKS[this.time], P = this.look.pbr;
        this.look.sky = T.sky;
        P.background = T.sky;
        P.ambient = T.ambient;
        P.sun = Object.assign({}, P.sun, {colour: T.sun});
        P.exposure = T.exposure;
        P.fill = [0.4 * T.env, 0.4 * T.env, 0.4];
        if (P.fog) P.fog = Object.assign({}, P.fog, {colour: T.horizon});
        // (the beams: HEADLIGHTS spotlights, given to the karts each frame; none by day)
        P.spots = T.beam > 0 ? Array.from({length: HEADLIGHTS}, () => ({pos: [0, 0, -100], at: [0, 1, -100], colour: [0, 0, 0], fov: 84, soft: true,
                                                                          att: [1.0, 0.02, 0.008]})) : [];
    }

    build() {  // (ultra's after-effects let go before the scene they were made for: CHANGE 144)
        if (this.fx) { this.fx.dispose(); this.fx = null; }
        super.build();
    }

    // after build() (and again after a tier change): the track and the karts back in
    populate(rebuild) {
        // (the arrows drive: the camera doesn't turn with them; the drift smoke's pool, none on blocks or the line tiers)
        this.camera.inputs.removeByType("ArcRotateCameraKeyboardMoveInput");
        this.lampKit = null;  // (CHANGE 171, 172: the lamps' materials, made again with the scene)
        if (!this.lit && !this.wire) {  // (blocks: one plain light, dimmed at dusk and night)
            const hemi = this.scene.getLightByName("sky");
            if (hemi) hemi.intensity = this.timeLook.blocks;
        }
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
        this.makeItemBoxes(track);  // (CHANGE 159) the power-ups' boxes
        // (CHANGE 158) the PIT box: a yellow outline and PIT on the road (track.js pitMarks, kart_track's)
        const pit = new Geo();
        for (const corners of track.pitMarks()) pit.quad(corners.map(([s, l]) => { const p = track.point(s, l); return [p[0], p[1], p[2] + 0.022]; }));
        if (pit.pos.length) {
            const m = pit.mesh("pit", scene);
            m.material = this.material("pit", [1.0, 0.8, 0.08], 0.7, 0);
            statics.push(m);
        }
        // (CHANGE 179) the pit lane's bays: a white outline each (the road builder's or the circuit's), a strip at the
        // back in its kart's colour and a board with the kart's name (setBayNames), on every tier; and on ultra, where
        // the circuit draws the open lane's walls, the closed lane's gates across the entry and the exit
        this.bays = [];
        if (this.circuit) this.gates = null;
        if (track.lane) {
            const [sIn, sOut, side] = track.lane, half = track.half;
            if (this.circuit) {
                const gate = new Geo(true);
                gate.colour = [0.92, 0.92, 0.9, 1];
                for (const [a, b] of [[sIn, sIn + LANE_RAMP], [sOut - LANE_RAMP, sOut]]) {
                    for (let s = a; s < b - 1e-6;) {
                        const e = Math.min(b, s + 4), lower = p => [p[0], p[1], p[2] - 0.3], up = [0, 0, 0.55];
                        const n = this.leftOf((s + e) / 2).map(v => v * side);
                        const a0 = lower(track.point(s, side * (half + KERB))), a1 = lower(track.point(e, side * (half + KERB)));
                        const b0 = lower(track.point(s, side * (half + KERB + 0.5))), b1 = lower(track.point(e, side * (half + KERB + 0.5)));
                        gate.quad([a0, a1, add3(a1, up), add3(a0, up)], n.map(v => -v));
                        gate.quad([b1, b0, add3(b0, up), add3(b1, up)], n);
                        gate.quad([add3(a0, up), add3(a1, up), add3(b1, up), add3(b0, up)], [0, 0, 1]);
                        s = e;
                    }
                }
                this.gates = gate.mesh("gates", scene);
                this.gates.material = this.material("paint", [1, 1, 1], 0.75);
                this.trackMeshes.push(this.gates);
            }
            const marks = new Geo();
            for (const corners of track.laneMarks()) marks.quad(corners.map(([s, l]) => { const p = track.point(s, l); return [p[0], p[1], p[2] + 0.022]; }));
            const mk = marks.mesh("baymarks", scene);
            mk.material = this.material("baypaint", [0.92, 0.92, 0.9], 0.7, 0);
            statics.push(mk);
            for (let kid = 0; kid < LANE_BAYS; kid++) {
                const [s0, s1, lo, hi] = track.bay(kid);
                const strip = new Geo();
                const q = [track.point(s0 + 0.15, side * (hi - 0.6)), track.point(s1 - 0.15, side * (hi - 0.6)),
                           track.point(s1 - 0.15, side * (hi - 0.15)), track.point(s0 + 0.15, side * (hi - 0.15))];
                strip.quad(q.map(p => [p[0], p[1], p[2] + 0.024]));
                const stripMesh = strip.mesh("baystrip" + kid, scene);
                stripMesh.material = this.material("baystrip" + kid, [0.5, 0.5, 0.5], 0.7, 0);
                stripMesh.isPickable = false;
                this.trackMeshes.push(stripMesh);
                const mid = (s0 + s1) / 2, [x, y, z] = track.point(mid, side * (hi + 0.35));
                const post = this.cyl(null, 0.03, 0.6, "z", this.material("steel", [0.6, 0.6, 0.62], 0.6, 1), x, y, z + 0.6, 0, 6);
                this.trackMeshes.push(post);
                const board = this.signText(String(kid + 1), 2.0);
                board.position.set(x, z + 1.35, y);
                // (facing the lane: the plane's front is its -z in Babylon, turned by the track's heading)
                board.rotation.y = -(track.heading(mid) + (side < 0 ? 90 : -90)) * Math.PI / 180;
                this.trackMeshes.push(board);
                this.bays.push({board, strip: stripMesh});
            }
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

    // (CHANGE 179) the pit lane open ("lane": its entry and exit clear) or closed ("box": walled off)
    setPits(mode) {
        if (this.gates) this.gates.setEnabled(mode !== "lane");
    }

    // (CHANGE 179) the bays' boards and strips: Map(kart id -> [name, [r, g, b]]) from the roster
    setBayNames(names) {
        (this.bays || []).forEach(({board, strip}, kid) => {
            const [name, colour] = names.get(kid) || [null, null];
            const text = name ? String(name).slice(0, 12) : String(kid + 1);
            if (board.ccText !== text) {
                board.ccText = text;
                const tex = board.material.diffuseTexture;
                tex.getContext().clearRect(0, 0, 512, 128);
                tex.drawText(text, null, 100, `bold ${text.length > 6 ? 64 : 100}px sans-serif`, "#ffffff", null, true, true);
            }
            const c = colour ? colour.map(v => v / 255) : [0.5, 0.5, 0.5];
            strip.material.albedoColor = new BABYLON.Color3(c[0], c[1], c[2]);
            if (strip.material.diffuseColor) strip.material.diffuseColor = new BABYLON.Color3(c[0], c[1], c[2]);
        });
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
        const lane = track.lane, laneSide = lane ? lane[2] : 0;  // (CHANGE 179: the pit lane's side; its entry and exit have no kerb paint)
        for (let s = 0, block = 0; s < L; block++) {
            const e = Math.min(L, s + 2);
            paint.colour = block % 2 ? KERB_RED : KERB_WHITE;
            for (const side of [1, -1]) {
                if (side === laneSide && track.laneZone((s + e) / 2) === "ramp") continue;
                this.ribbon(paint, s, e, side * (half - 0.55), side * (half + 0.2), 0.03, 2.0);
            }
            s = e;
        }
        // (CHANGE 177) the gravel traps: sand-coloured, from the barrier line out as far as the trap reaches
        paint.colour = [0.74, 0.68, 0.56, 1];
        for (const side of [1, -1]) {
            const g = track.gravel[side > 0 ? 1 : "-1"];
            for (let i = 0; i < track.n; i++) {
                const j = (i + 1) % track.n;
                if (g[i] <= 0 && g[j] <= 0) continue;
                const s0 = track.s[i], s1 = track.s[i] + track.segLen[i];
                const pts = [track.point(s0, side * (half + KERB)), track.point(s1, side * (half + KERB)),
                             track.point(s1, side * (half + KERB + g[j])), track.point(s0, side * (half + KERB + g[i]))];
                paint.quad(pts.map(p => [p[0], p[1], p[2] + 0.02]), [0, 0, 1]);
            }
        }
        const wallIn = half + KERB, wallOut = half + KERB + 0.5, wallH = 0.55;
        const gate = new Geo(true);  // (CHANGE 179: the wall across the pit lane's entry and exit, shown while it's closed)
        const wallBlock = (geo, a0, a1, b0, b1, n) => {
            const lower = p => [p[0], p[1], p[2] - 0.3], up = [0, 0, wallH];
            a0 = lower(a0); a1 = lower(a1); b0 = lower(b0); b1 = lower(b1);
            geo.quad([a0, a1, add3(a1, up), add3(a0, up)], n.map(v => -v));
            geo.quad([b1, b0, add3(b0, up), add3(b1, up)], n);
            geo.quad([add3(a0, up), add3(a1, up), add3(b1, up), add3(b0, up)], [0, 0, 1]);
        };
        for (let s = 0, block = 0; s < L; block++) {
            const e = Math.min(L, s + 4);
            const colour = block % 3 === 2 ? [0.8, 0.1, 0.08, 1] : [0.92, 0.92, 0.9, 1];
            const left = this.leftOf((s + e) / 2);
            for (const side of [1, -1]) {
                const zone = side === laneSide ? track.laneZone((s + e) / 2) : null;
                const geo = zone === "ramp" ? gate : paint;
                geo.colour = colour;
                const g0 = zone === null ? track.gravelAt(track.segmentAt(s), side) : 0;  // (out past the gravel)
                const g1 = zone === null ? track.gravelAt(track.segmentAt(e), side) : 0;
                wallBlock(geo, track.point(s, side * (wallIn + g0)), track.point(e, side * (wallIn + g1)),
                          track.point(s, side * (wallOut + g0)), track.point(e, side * (wallOut + g1)), left.map(v => v * side));
            }
            s = e;
        }
        if (lane) {  // (CHANGE 179) the pit lane: its asphalt, and the outer wall slanting in at each end
            const [sIn, sOut, side] = lane, laneGeo = new Geo();
            for (const [a, b, inner] of [[sIn, sIn + LANE_RAMP, half + 0.3], [sIn + LANE_RAMP, sOut - LANE_RAMP, track.laneInner()],
                                         [sOut - LANE_RAMP, sOut, half + 0.3]]) {
                const steps = Math.max(1, Math.ceil((b - a) / 1.5));
                let prev = null;
                for (let j = 0; j <= steps; j++) {
                    const ls = a + (b - a) * j / steps;
                    const row = [track.point(ls, side * inner), track.point(ls, side * track.laneEdge(ls))].map(p => [p[0], p[1], p[2] + 0.012]);
                    if (prev) laneGeo.quad([prev[0], row[0], row[1], prev[1]]);
                    prev = row;
                }
            }
            put(laneGeo.mesh("lane", scene), this.material("lanetarmac", blocks ? [0.5, 0.5, 0.52] : [0.5, 0.5, 0.52], 1.0, 0, 0, {tex: "tarmac", tile: 0.125}));
            for (let s = sIn, block = 0; s < sOut; block++) {
                const e = Math.min(sOut, s + 4);
                paint.colour = block % 3 === 2 ? [0.8, 0.1, 0.08, 1] : [0.92, 0.92, 0.9, 1];
                wallBlock(paint, track.point(s, side * track.laneEdge(s)), track.point(e, side * track.laneEdge(e)),
                          track.point(s, side * (track.laneEdge(s) + 0.5)), track.point(e, side * (track.laneEdge(e) + 0.5)),
                          this.leftOf((s + e) / 2).map(v => v * side));
                s = e;
            }
        }
        this.gates = gate.pos.length ? put(gate.mesh("gates", scene), this.material("paint", [1, 1, 1], 0.75), true) : null;
        if (this.gates) { this.trackMeshes.push(this.gates); statics.splice(statics.indexOf(this.gates), 1); }
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

    setKarts(designs) {  // the roster's karts: add new ones, drop gone ones, recolour changed ones
        // (CHANGE 173: the roster's entry carries the whole design, and its body: a kart or a sports car)
        const wanted = new Map(designs.map(d => [d.id, d.body || !(d.design && d.design.body) ? d : {...d, body: d.design.body}]));
        for (const id of [...this.karts.keys()]) if (!wanted.has(id)) this.removeKart(id);
        for (const [id, d] of wanted) {
            const have = this.karts.get(id);
            if (!have || have.design.name !== d.name || String(have.design.colour) !== String(d.colour)
                || (have.design.body || "kart") !== (d.body || "kart")) this.addKart(d);  // (the body: CHANGE 173)
        }
    }

    // ---------- the power-ups (CHANGE 159, kart_gfx.ItemsVisual) ----------
    // the item boxes, a row of four across the road at each of the track's box rows, spinning, their colour going
    // round the rainbow; the shots and slicks come and go with the items messages (drawItems)
    makeItemBoxes(track) {
        for (const m of (this.itemShots || new Map()).values()) m.dispose();
        for (const m of (this.itemSlicks || new Map()).values()) m.dispose();
        this.itemShots = new Map();
        this.itemSlicks = new Map();
        this.itemBoxes = track.boxSpots().map(([s, lat], i) => {
            const [x, y, z] = track.point(s, lat);
            const mat = this.material("itembox" + i, [0.18, 0.18, 0.2], 0.35, 0, 0, {emission: [0.9, 0.8, 0.3]});  // (its glow its colour)
            const box = this.box(null, 0.42, 0.42, 0.42, mat, x, y, z + 0.75, "itembox");
            box.isPickable = false;
            this.trackMeshes.push(box);
            if (this.wire) this.linesMesh("itemboxlines", this.edgeLines([box], this.wire, box), this.lineMaterial("itembox", 1, ...this.lineFade()), box);
            return {box, mat};
        });
        this.itemSpin = 0;
    }

    // view: the items to draw ({boxes: "1101..", shots: [[id, kind, x, y, heading]], slicks: [[id, x, y]]}) or null
    drawItems(view, dt) {
        if (!this.itemBoxes || !this.track) return;
        this.itemSpin = (this.itemSpin + dt * 90) % 360;
        const boxes = (view && view.boxes) || "";
        this.itemBoxes.forEach(({box, mat}, i) => {
            const there = boxes[i] === "1";
            box.setEnabled(there);
            if (!there) return;
            box.rotation.set(20 * DEG, this.itemSpin * DEG, 30 * DEG);
            const [r, g, b] = hueColour((this.itemSpin / 360 + i * 0.13) % 1);
            this.setGlow(mat, [r * 0.8, g * 0.8, b * 0.8]);
        });
        const height = (x, y) => { const at = this.track.locate(x, y, null); return this.track.point(at.s)[2]; };
        this.syncItems(this.itemShots, (view && view.shots) || [], sh => {
            const c = sh[1] === "homing" ? [1.0, 0.3, 0.22] : [0.35, 1.0, 0.45];
            const m = this.sphere(null, 0.28, this.material("itemshot" + sh[1], c, 0.3, 0, 0, {emission: c.map(v => v * 2.5)}), 0, 0, 0, 1, 1, 1, 12, "shot");
            if (this.wire) this.linesMesh("shotlines", this.edgeLines([m], this.wire, m), this.lineMaterial("shot", 1, ...this.lineFade()), m);
            return m;
        }, (m, sh) => m.position.set(sh[2], height(sh[2], sh[3]) + 0.45, sh[3]));
        this.syncItems(this.itemSlicks, (view && view.slicks) || [], () => {
            const g = new Geo(), pts = [];
            for (let k = 0; k < 16; k++) { const a = 2 * Math.PI * k / 16; pts.push([Math.cos(a) * 1.5, Math.sin(a) * 1.2, 0]); }
            g.poly(pts, [0, 0, 1]);
            const m = g.mesh("slick", this.scene);
            m.material = this.material("itemslick", [0.05, 0.05, 0.07], 0.15, 0.5);
            return m;
        }, (m, sl) => m.position.set(sl[1], height(sl[1], sl[2]) + 0.025, sl[2]));
    }

    syncItems(meshes, items, make, place) {
        const seen = new Set();
        for (const it of items) {
            seen.add(it[0]);
            let m = meshes.get(it[0]);
            if (!m) meshes.set(it[0], m = make(it));
            place(m, it);
        }
        for (const [id, m] of meshes) if (!seen.has(id)) { m.dispose(); meshes.delete(id); }
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
            this.carFrame(k, st, z, dt);
        }
        if (this.padMat && this.lighting) {  // the dash pads pulse (kart_gfx.TrackVisual.update)
            const glow = 2.4 + 1.2 * Math.sin(performance.now() / 1000 * 5);
            this.padMat.setVector3("emission", new BABYLON.Vector3(glow, glow * 0.55, glow * 0.07));
        }
        this.updateCamera(states, dt);
        this.headlightFrame(states);  // (CHANGE 172)
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
            const [hx, hz] = k.fit.hood;  // (just over the nose plate, or a car's bonnet: CHANGE 173)
            want = [tx + fx * hx, ty + fy * hx, tz + hz];
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

// (CHANGE 201) the karts' and cars' own methods (cars.js), shared with City Lab's scene
Object.assign(KartScene.prototype, CarParts);

// (CHANGE 159) a bright colour round the rainbow (h 0 to 1: kart_gfx.hue_colour)
function hueColour(h) {
    const i = Math.floor(h * 6) % 6, f = h * 6 - Math.floor(h * 6);
    return [[1, f, 0.05], [1 - f, 1, 0.05], [0.05, 1, f], [0.05, 1 - f, 1], [f, 0.05, 1], [1, 0.05, 1 - f]][i];
}
