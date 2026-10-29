// Fight Lab in Club Coders Live (CHANGE 130): the hall and its rings (fight_sim.py's constants, drawn after
// fight_gfx.StageVisual), the hazards from each snapshot (fire jets, spikes, ice, ropes or an open edge), the
// fighters built from their designs on a 13-joint skeleton and posed by the game's own pose code (fight_gfx.py's
// stance, attacks, falls, ported line for line: fighters.js), the 30-a-second JSON states blended two behind, and the
// teacher's Fight Lab controls. The skinned models (woman, man, Robin) are the app's own (fightmodels.js, on the lit
// tiers); until a fighter's model is loaded, and on blocks, it is drawn as the primitive human or robot in its
// colours, with its weapon. The effects and the camera are the window's (fightfx.js: fight_fx.py, the stage's jets,
// blasts and glowing ropes and edges from fight_gfx.StageVisual, and fight_camera.py's five views).
// Panda joint angles (h, p, r) are Babylon rotation (-p, -h, -r); positions game (x, y, z) -> Babylon (x, z, y).
// (CHANGE 147) Every tier, as the window's since its CHANGE 147: mesh and lines draw the meshes black with their edges
// as lines (base3d.js), each moving part's own (each joint of a fighter, a skinned model's bending with it), a grid on
// the rings' canvas and the hall's floor on lines, the glowing parts' lines pulsing; ultra draws the window's smooth
// fighters and hall (fightfx.js, from models/fight_ultra.json and stage_ultra.json) once loaded.

/* global BABYLON */

import {BaseScene, TIERS, v3, rgb255, lerp, lerpDeg, mulberry} from "./base3d.js";
import {toneMap} from "./pbr.js";
import {AfterFx} from "./kartfx.js";
import {FightFX, FightCamera, CAM_MODES, CAM_NAMES, loadFightModels, fightModelsData, loadStageModels, stageModelsData,
        makeUltraRing, makeUltraHall, loadPandaFont} from "./fightfx.js";
import {FighterParts} from "./fighters.js";  // (the fighters, built and posed: CHANGE 201)
import {FightHud} from "./hud.js";
import {Sound} from "./sound.js";
import {FighterAhead} from "./ahead.js";

const $ = id => document.getElementById(id);
loadPandaFont();  // (the window's letters, asked for as the page opens: CHANGE 150)
const D2R = Math.PI / 180;
const RING_CENTRES = [[0, 0], [16, 0], [-16, 0], [0, 16], [16, 16], [-16, 16]];
const MAT_COLOURS = [[0.12, 0.13, 0.2], [0.35, 0.06, 0.06], [0.06, 0.2, 0.12], [0.2, 0.08, 0.3], [0.3, 0.2, 0.05], [0.05, 0.18, 0.3]];
const PAD_COLOURS = [[0.85, 0.1, 0.1], [0.95, 0.95, 0.95], [0.1, 0.25, 0.85]];
const JET_ANGLES = [45, 135, 225, 315];
const EDGE_GLOW = [4.0, 1.2, 0.2];  // (fight_gfx.py)
// (CHANGE 147) mesh and lines: where the lines fade into the dark (fight_gfx.LOOK_FADE) and the grids on lines (every
// GRID m on the hall's floor, every MAT_GRID m on a ring's canvas); ultra: the hall's air the stands and walls fade
// into (fight_gfx.HAZE, linear) and how thick (per metre). (The hit flash's colour scale is fighters.js's FLASH)
const LOOK_FADE = {all: [18, 75], outline: [25, 110]}, GRID = 2.0, MAT_GRID = 1.0;
const HAZE = [0.01, 0.01, 0.018], HAZE_DENSITY = 0.01, EXPOSURE = 0.8;

// ---------- the scene ----------
export class FightScene extends BaseScene {
    static TIERS = TIERS;  // (every tier, the line tiers and ultra too, as the window: CHANGE 147)
    // (ultra's after-effects, kartfx.js's AfterFx, as Robot Lab's: a gentle glow on the lamps, visors, cores and
    // ropes and a little sharpening, 4x MSAA on that picture as the window's ultra; no SSAO, no reflection probe)
    static ULTRA_FX = {ssao: false, sharpen: true, samples: 4, bloomWeight: 0.25};
    // (the Graphics tab: what this game's lines and ultra draw)
    static TIER_TEXT = {lines: "lines: black, the outlines in one colour (the round fighters' too) and a grid on the rings and the hall's floor (an old vector arcade game).",
                        ultra: "ultra: for a strong graphics card: the window's smooth fighters (armour, visors and lights, a gi, a face and hair) and hall (padded rings with the club's boards, posts and ropes, the stands and their crowd, the screens, the lighting rig, walls and roof), soft 4096 shadows, glow, sharper textures at a slant."};

    constructor(canvas, tier, engine) {
        // fight_gfx.init's lights: a key light high over the hall, a dim blue fill, the arena's reflections, and a
        // spotlight over each ring in use (setSetup); on ultra a haze over the hall's far parts alone (fog.picked, as
        // the window's), given as the colour the tone curve makes of its light
        super(canvas, tier, engine, {sky: [0.02, 0.02, 0.04], radius: 9, target: [0, 0, 1], ground: [0.1, 0.1, 0.14], hemi: 0.45, sun: 1.5,
                                     sunDir: [-0.25, -0.9, 0.45],
                                     pbr: {background: [0.01, 0.01, 0.02], exposure: EXPOSURE, ambient: [0.07, 0.07, 0.1], sky: "env",
                                           fog: {colour: toneMap(HAZE, Math.pow(2, EXPOSURE)), density: HAZE_DENSITY, picked: true},
                                           sun: {colour: [1.1, 1.05, 1.0], offset: [6, -12, 26], film: 16, near: 5, far: 60, bias: 0.005},
                                           spots: FightScene.spots([0])}});
        this.setup = {rings: [0], rs: 4.5, hazards: {}, look: {}};
        this.fighters = new Map();
        this.list = [];
        this.cam = new FightCamera("fight");  // (fight_camera.FightCamera: the five views, each with its zoom)
        this.myId = null;                     // (your fighter: the one the camera's own views follow)
        this.focusId = null;                  // (CHANGE 183: a fighter picked with L is followed instead)
        this.ringMeshes = new Map();
        this.stageT = 0;                      // (the stage's clock: the jets' puffs, the ropes' and edges' pulses)
        this.zapUntil = {};
        this.build();
    }

    get mode() { return this.cam.mode; }

    static spots(rings) {  // fight_gfx.build_lights: one over each ring in use (at most 6)
        return (rings || [0]).slice(0, 6).map(i => {
            const [cx, cy] = RING_CENTRES[i] || [0, 0];
            return {pos: [cx - 2.5, cy - 5.5, 9.5], at: [cx, cy, 0], colour: [5.5, 5.2, 4.8], fov: 52, att: [1, 0, 0.012]};
        });
    }

    build() {  // (ultra's after-effects let go before the scene they were made for: CHANGE 147)
        if (this.after) { this.after.dispose(); this.after = null; }
        super.build();
    }

    populate() {
        // (ultra, CHANGE 147) the window's fighters and hall once both files are here (asked for on ultra alone): high's
        // until then, or if they don't come; then everything is made again with them
        this.ultra = !!(this.settings.ultra && this.lighting);
        this.ultraFighters = this.ultra && !!fightModelsData();
        this.ultraStage = false;
        this.lineCount = 0;
        this.lineStats = null;
        this.glowLines = {};  // (the line tiers: the glowing parts' line materials, pulsed in frame())
        if (this.ultra) {
            const scene = this.scene;
            Promise.all([loadFightModels(), loadStageModels()]).then(([f, s]) => {
                if (this.scene === scene && ((f && !this.ultraFighters) || (s && !this.ultraStage))) this.build();
            });
        }
        this.buildStage();
        this.shadowCulling();
        this.drawOrder();
        this.after = this.ultra && FightScene.ULTRA_FX ? new AfterFx(this, FightScene.ULTRA_FX) : null;
        if (this.after) {  // (CHANGE 150: the glow made from a quarter-size picture, blurred as far across: the same glow, cheaper)
            this.after.pipeline.bloomScale = 0.25;
            this.after.pipeline.bloomKernel = 24;
        }
        this.fx = new FightFX(this);
        // the camera is placed by the window's views every frame (drags, the wheel and keys are FightGame's), so it
        // takes no input of its own and may go anywhere they put it
        const cam = this.camera;
        cam.detachControl();
        cam.lowerRadiusLimit = 0.01;
        cam.upperRadiusLimit = 1000;
        cam.lowerBetaLimit = 0.001;
        cam.upperBetaLimit = Math.PI - 0.001;
        cam.maxZ = 300;
        this.cam.pos = null;
        const list = this.list;
        this.fighters.clear();
        for (const f of list) this.addFighter(f);
    }

    // (CHANGE 150) the shadow map draws only the casters inside the key light's view (its 16 m round what the camera
    // looks at, as the window's shadow camera culls): Babylon's draws its whole list every frame, every ring's and
    // every fighter's, the far rings' 3D bodies too
    shadowCulling() {
        const L = this.lighting, rtt = L && L.rtt;
        if (!rtt || !L.sunCam) return;
        const out = [];
        rtt.getCustomRenderList = (layer, list, n) => {
            const planes = BABYLON.Frustum.GetPlanes(L.sunCam.getTransformationMatrix(true));
            out.length = 0;
            for (let i = 0; i < n; i++) {
                const m = list[i];
                if (!m || !m.isEnabled() || !m.isVisible) continue;
                m.computeWorldMatrix();
                if (m.alwaysSelectAsActiveMesh || m.isInFrustum(planes)) out.push(m);
            }
            return out;
        };
    }

    // (CHANGE 150) the lit tiers draw the fighters first, then the rings and the rest, the crowd, the stands and the
    // hall, and the floor last (a mesh's ccRank, else what its material is), each group by material as Babylon would:
    // what is hidden behind them isn't lit and then painted over (Babylon's own order is the materials' age, the
    // hall's first). The line tiers keep base3d's (every black face, then every line)
    drawOrder() {
        if (this.wire || this.tier === "blocks") return;
        const BY_MATERIAL = {hall: 4, walk: 4, stands: 3, crowd: 2, screen: 3, screenglow: 3, truss: 3, lamp: 3};
        const rank = sub => {  // (worked out once a mesh)
            const m = sub.getMesh();
            if (m.ccRank === undefined) m.ccRank = BY_MATERIAL[String((m.material || {}).name).split(":")[0]] ?? 1;
            return m.ccRank;
        };
        this.scene.setRenderingOrder(0, (a, b) => (rank(a) - rank(b)) || BABYLON.RenderingGroup.PainterSortCompare(a, b));
    }

    setSetup(setup) {
        const key = JSON.stringify(setup);
        if (key === this.setupKey) return;
        this.setupKey = key;
        this.setup = setup;
        this.look.pbr.spots = FightScene.spots(setup.rings);
        this.build();
    }

    // (CHANGE 147) mesh and lines: the rings' still parts' edges as lines (with a grid on each canvas on lines), the
    // hall's (with a grid on its floor on lines), the rig's, and each part that glows or moves its own (stageLines);
    // ultra: the window's rings (fightfx.js's makeUltraRing) in place of the platform, base, mat, posts, pads and ropes,
    // and its hall (makeUltraHall); the markings, logo, open edge's glow, jets, spikes and ice kept
    buildStage() {
        const {rings, rs: R, hazards: hz, look} = this.setup;
        const roped = !hz.ring_out, blocks = this.tier === "blocks";
        const file = this.ultra ? stageModelsData() : null, ultra = !!file;
        this.ultraStage = ultra;
        const M = (name, rgb, rough, metal, tex, tile, emission) => this.material(name, rgb, rough, metal, 0, {tex, tile, emission});
        const statics = [], hall = [];
        const S = m => { statics.push(m); return m; };
        this.buildHall(hall, look, file);
        const marks = M("marks", [0.9, 0.9, 0.95], 0.6, 0);
        const hazard = blocks ? M("hazard", [0.95, 0.75, 0.08], 1, 0) : M("hazard", [1, 1, 1], 1, 0, "hazard", 0.8);
        this.jets = new Map();
        this.ropes = [];
        this.glows = new Map();  // ring -> {ropes, edge}: the materials that pulse (fight_gfx.StageVisual.update)
        this.ultraRings = [];
        const moving = [];  // (the line tiers: [meshes, glow]: the ropes' and an open edge's lines, pulsing as they glow)
        for (const i of rings || [0]) {
            const [cx, cy] = RING_CENTRES[i] || [0, 0];
            const platR = roped ? R + 0.7 : R + 0.1;
            if (!ultra) {
                S(this.cyl(null, platR, 0.4, "z", M("platform", [0.2, 0.2, 0.23], 1, 1, "steel", 0.6), cx, cy, -0.42, null, 48));
                S(this.cyl(null, platR + 0.08, 0.06, "z", M("platrim", [0.08, 0.08, 0.1], 0.6, 0.5, "paint"), cx, cy, -0.8 + 0.06, null, 48));
                S(this.cyl(null, platR - 0.02, 0.012, "z", M("mat" + i, MAT_COLOURS[i % 6], 0.95, 0, "concrete", 0.4), cx, cy, -0.01, null, 48));
            }
            // (each dash along x, as the window's: CHANGE 150, they were turned along the circle)
            if (!hz.slippery) for (let k = 0; k < 40; k++) {
                const a = k / 40 * Math.PI * 2;
                S(this.box(null, 0.14, 0.04, 0.003, marks, cx + Math.cos(a) * 0.45 * R, cy + Math.sin(a) * 0.45 * R, 0.004));
            }
            for (const sx of [-1.6, 1.6]) S(this.box(null, 0.05, 0.45, 0.003, marks, cx + sx, cy, 0.004));
            // (the line colour on the line tiers: CHANGE 147)
            // (the window's TextNode: its letters, 0.75 a unit, the baseline 0.25 m below the middle: CHANGE 150)
            const logo = this.words(i === 0 ? (look.name || "FIGHT LAB") : `RING ${i + 1}`, 0.75, this.wire ? "#ffffff" : "#e8d49a", 0.8, [cx, cy - 0.25, 0.008], [0, -90, 0]);
            if (this.wire) this.lettering(logo);
            const ropeMat = !roped ? null : hz.electric_ropes ? M("eropes" + i, [0.5, 0.8, 1.0], 0.5, 0, null, null, [0.4, 1.2, 3.0]) : M("ropes", [0.85, 0.12, 0.1], 0.5, 0);
            if (roped && hz.electric_ropes) this.glows.set(i, {ropes: ropeMat});
            if (ultra) {  // (the window's ring for this size: the ropes their own mesh, glowing as the lower tiers' do)
                const u = makeUltraRing(this, file, i, R, roped, [cx, cy], MAT_COLOURS[i % 6], PAD_COLOURS[i % 3], ropeMat);
                this.ultraRings.push(u);
                if (u.ropes) this.ropes.push(u.ropes);
                this.shadowCast(u.casters);
            } else if (roped) {
                const postR = (R + 0.08) / Math.cos(22.5 * D2R);
                const posts = [];
                for (let k = 0; k < 8; k++) {
                    const a = (22.5 + 45 * k) * D2R, px = cx + Math.cos(a) * postR, py = cy + Math.sin(a) * postR;
                    posts.push([px, py]);
                    S(this.cyl(null, 0.08, 0.7, "z", M("post", [0.75, 0.75, 0.8], 1, 1, "steel", 0.8), px, py, 0.7, null, 12));
                    S(this.box(null, 0.12, 0.12, 0.45, M("pad" + (i % 3), PAD_COLOURS[i % 3], 0.6, 0.2, "paint"), px, py, 0.85));
                }
                for (const z of [0.45, 0.85, 1.25]) for (let k = 0; k < 8; k++) {
                    const [ax, ay] = posts[k], [bx, by] = posts[(k + 1) % 8];
                    const rope = BABYLON.MeshBuilder.CreateTube("rope", {path: [v3(ax, ay, z), v3(bx, by, z)], radius: 0.035, tessellation: 8}, this.scene);
                    rope.material = ropeMat;
                    this.ropes.push(rope);
                }
            }
            if (roped) moving.push([this.ropes.slice(-(ultra ? 1 : 24)), "ropes" + i]);
            else {
                const band = this.edgeBand(R, cx, cy);
                band.material = M("edge" + i, [0, 0, 0], 1, 0, null, null, EDGE_GLOW);
                this.glows.set(i, {edge: band.material});
                moving.push([[band], "edge" + i]);
            }
            if (hz.fire_jets) {  // the striped plates and nozzles; the flames are soft puffs rising up each jet (fightfx.js)
                // (the line tiers: a flame of lines on each, flickering and growing with the jet, no puffs: CHANGE 147)
                const jets = JET_ANGLES.map(a => {
                    const x = cx + Math.cos(a * D2R) * 0.55 * R, y = cy + Math.sin(a * D2R) * 0.55 * R;
                    S(this.cyl(null, 0.32, 0.01, "z", hazard, x, y, 0.005, null, 20));
                    S(this.cyl(null, 0.16, 0.02, "z", M("nozzle", [0.15, 0.15, 0.16], 1, 1, "steel"), x, y, 0.01, null, 16));
                    return [x, y, this.wire ? this.flameLines(x, y, "jet" + i) : null];
                });
                this.jets.set(i, jets);
            }
            if (hz.spikes) for (const a of [0, 90, 180, 270]) {
                const x = cx + Math.cos(a * D2R) * 0.78 * R, y = cy + Math.sin(a * D2R) * 0.78 * R;
                S(this.cyl(null, 0.45, 0.01, "z", hazard, x, y, 0.005, null, 24));
                for (let k = 0; k < 7; k++) {
                    const r = k ? 0.27 : 0, b = k * Math.PI / 3;
                    S(this.cyl(null, 0.06, 0.12, "z", M("spike", [0.8, 0.8, 0.85], 0.4, 1, "steel"), x + Math.cos(b) * r, y + Math.sin(b) * r, 0.14, 0, 8));
                }
            }
            if (hz.slippery) {
                S(this.cyl(null, 0.45 * R, 0.006, "z", M("ice", [0.55, 0.75, 0.92], 0.06, 0.3), cx, cy, 0.002, null, 48));
                S(this.cyl(null, 0.45 * R + 0.05, 0.004, "z", M("iceedge", [0.85, 0.95, 1.0], 0.3, 0), cx, cy, 0, null, 48));
                const shine = M("iceshine", [1, 1, 1], 0.02, 0, null, null, [0.6, 0.8, 1.0]);  // (glowing streaks across the ice)
                for (let k = 0; k < 6; k++) S(this.box(null, 0.3 * R, 0.012, 0.002, shine, cx + Math.cos(k * 1.05) * 0.12 * R, cy + Math.sin(k * 1.05) * 0.15 * R, 0.01));
            }
        }
        const still = this.mergeStatic(statics), hallStill = this.mergeStatic(hall);
        if (this.wire) this.stageLines(still, hallStill, moving);
    }

    // (CHANGE 150: fight_gfx.build_ring's open edge) a flat glowing band round the ring from R - 0.05 to R + 0.04 m,
    // 6 mm up, as 64 quads of two triangles each (the window's: so mesh draws the same edges; it was a torus with many
    // more)
    edgeBand(R, cx, cy) {
        const pos = [], idx = [], nor = [], r0 = R - 0.05, r1 = R + 0.04, z = 0.006;
        for (let k = 0; k < 64; k++) {
            const a0 = 2 * Math.PI * k / 64, a1 = 2 * Math.PI * (k + 1) / 64, o = pos.length / 3;
            for (const [a, r] of [[a0, r0], [a1, r0], [a1, r1], [a0, r1]]) { pos.push(cx + Math.cos(a) * r, z, cy + Math.sin(a) * r); nor.push(0, 1, 0); }
            idx.push(o, o + 2, o + 1, o, o + 3, o + 2);  // (the window's fan from the first corner, wound for Babylon)
        }
        const mesh = new BABYLON.Mesh("edge", this.scene), vd = new BABYLON.VertexData();
        vd.positions = pos; vd.normals = nor; vd.indices = idx;
        vd.applyToMesh(mesh);
        return mesh;
    }

    lineFade() {  // (where the lines fade out, as the window's dark fog: fight_gfx.LOOK_FADE, CHANGE 147)
        return LOOK_FADE[this.wire] || LOOK_FADE.outline;
    }

    // (the line tiers, CHANGE 147: fight_gfx.StageVisual.looks) the rings' still parts' edges as lines in tiles (with
    // on lines a grid every MAT_GRID m on each canvas, cut at the ring's edge: fight_gfx.ring_grid), the hall's (with on
    // lines a grid every GRID m on its floor, hidden where the platforms and walkways stand), the rig's (hidden with
    // it), and the ropes' and an open edge's own, their material pulsed in frame() as they glow
    stageLines(still, hallStill, moving) {
        const t0 = performance.now(), before = this.lineCount || 0, fade = this.lineFade(), fill = this.wireFill();
        const mat = this.lineMaterial("stage", 1, ...fade), outline = this.wire === "outline";
        const seg = (L, a, b) => { const k = L.pos.length / 3; L.pos.push(a[0], a[2], a[1], b[0], b[2], b[1]); L.idx.push(k, k + 1); };
        const lists = this.edgeLines(still.filter(m => m.material === fill), this.wire);
        let grid = lists.idx.length / 2;
        if (outline) {
            const r = (this.setup.rs || 4.5) - 0.05, z = 0.006;
            for (const i of this.setup.rings || [0]) {
                const [cx, cy] = RING_CENTRES[i] || [0, 0];
                for (let c = -Math.floor(r / MAT_GRID) * MAT_GRID; c <= r + 1e-9; c += MAT_GRID) {
                    const half = Math.sqrt(Math.max(0, r * r - c * c));
                    if (half < 0.05) continue;
                    seg(lists, [cx + c, cy - half, z], [cx + c, cy + half, z]);
                    seg(lists, [cx - half, cy + c, z], [cx + half, cy + c, z]);
                }
            }
        }
        grid = lists.idx.length / 2 - grid;
        this.staticLines("stagelines", lists, mat);
        const hl = this.edgeLines(hallStill.filter(m => m.material === fill), this.wire), edges = hl.idx.length / 2;
        if (outline) {  // (line_look.grid: each line cut at the rectangle's edges, not along them)
            const [x0, y0, x1, y1] = [-32, -16, 32, 32], z = -0.8 + 0.002;
            for (let x = Math.ceil(x0 / GRID) * GRID; x < x1 - 1e-6; x += GRID) if (x > x0 + 1e-6) seg(hl, [x, y0, z], [x, y1, z]);
            for (let y = Math.ceil(y0 / GRID) * GRID; y < y1 - 1e-6; y += GRID) if (y > y0 + 1e-6) seg(hl, [x0, y, z], [x1, y, z]);
        }
        grid += hl.idx.length / 2 - edges;
        this.staticLines("halllines", hl, mat);
        const rigLines = this.rig.length ? this.linesMesh("riglines", this.edgeLines(this.rig, this.wire), mat) : null;
        if (rigLines) this.rig.push(rigLines);
        for (const [meshes, glow] of moving) {
            const m = this.glowLines[glow] = this.glowLines[glow] || this.lineMaterial(glow, 1, ...fade);
            this.linesMesh(glow.startsWith("edge") ? "edgelines" : "ropelines", this.edgeLines(meshes, this.wire), m);
        }
        this.lineStats = {segments: (this.lineCount || 0) - before, grid, ms: Math.round(performance.now() - t0)};
    }

    // (the line tiers, CHANGE 147) a fire jet's flame of lines (fight_gfx: a cone 0.2 m across its foot, 1 m high, its
    // edges alone: no black faces, a glow is see-through), on a node at the nozzle that frame() grows and shows
    flameLines(x, y, glow) {
        const node = new BABYLON.TransformNode("jetlines", this.scene);
        node.position = v3(x, y, 0.03);
        const cone = this.cyl(node, 0.2, 0.5, "z", this.wireFill(), 0, 0, 0.5, 0.03, 8);
        const m = this.glowLines[glow] = this.glowLines[glow] || this.lineMaterial(glow, 1, ...this.lineFade());
        this.linesMesh("jetlines", this.edgeLines([cone], this.wire, node), m, node);
        cone.dispose();
        node.setEnabled(false);
        return node;
    }

    // the hall round the rings: a concrete floor, walkways, tiered stands with a crowd, big screens and a lighting
    // truss (fight_gfx.build_hall); (ultra, CHANGE 147) the window's hall (fightfx.js's makeUltraHall), the screens'
    // lettering kept; (the line tiers) the name on the screens in the line colour
    buildHall(statics, look, file = null) {
        const M = (name, rgb, rough, metal, tex, tile, emission) => this.material(name, rgb, rough, metal, 0, {tex, tile, emission});
        const S = m => { statics.push(m); return m; };
        this.ultraParts = null;
        if (file) {
            const u = this.ultraParts = makeUltraHall(this, file, look);
            this.rig = u.rig;
            this.shadowCast(u.casters);
            // (the hall's name on each screen, facing the hall's middle, as the window's ultra writes it)
            for (const [x, y, z, h] of (file.notes || {}).screens || [[0, 36.5, 6, 0], [0, -20.5, 6, 180]]) {
                const front = h === 0 ? -1 : 1;
                // (the window's glowing orange lettering comes out nearly white through its tone curve)
                this.words(look.name || "FIGHT LAB", 2.2, "#fff0dc", 1.0, [x, y + front * 0.335, z - 0.45], [h, 0, 0]);
            }
            return;
        }
        const xs = RING_CENTRES.map(c => c[0]), ys = RING_CENTRES.map(c => c[1]);
        const pad = (this.setup.rs || 4.5) + 5;
        const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
        const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, hx = (x1 - x0) / 2, hy = (y1 - y0) / 2, floorZ = -0.8;
        S(this.box(null, hx + 14, hy + 14, 0.05, M("hall", [0.3, 0.3, 0.34], 1, 0, "concrete", 0.25), cx, cy, floorZ - 0.05));
        const walk = M("walk", [0.32, 0.26, 0.2], 1, 0, "concrete", 0.5);
        S(this.box(null, hx, 0.9, 0.02, walk, cx, 8, floorZ + 0.02));
        for (const x of [-8, 8]) S(this.box(null, 0.9, hy, 0.02, walk, x, cy, floorZ + 0.02));
        const standM = M("stands", [0.22, 0.24, 0.3], 1, 0, "concrete", 0.5), crowdM = M("crowd", [0.5, 0.5, 0.5], 0.9, 0);
        const shirts = [[0.8, 0.1, 0.1], [0.1, 0.3, 0.8], [0.9, 0.8, 0.2], [0.2, 0.6, 0.3], [0.9, 0.9, 0.9], [0.15, 0.15, 0.18], [0.9, 0.5, 0.1], [0.5, 0.2, 0.6]];
        const skins = [[0.85, 0.65, 0.5], [0.6, 0.42, 0.3], [0.4, 0.28, 0.2], [0.92, 0.75, 0.62]];
        const rnd = mulberry(5), crowd = look.crowd !== false && this.tier !== "blocks";
        for (let side = 0; side < 4; side++) {
            for (let row = 0; row < 5; row++) {
                const d = row * 1.2 + 1.5, z = floorZ + 0.3 + row * 0.6;
                let spots;
                if (side < 2) {
                    const y = side === 0 ? y1 + d : y0 - d;
                    S(this.box(null, hx + 6, 0.6, (z - floorZ) / 2, standM, cx, y, (z + floorZ) / 2));
                    spots = Array.from({length: Math.floor((hx + 5) * 2 / 0.9)}, (_, k) => [x0 - 5 + k * 0.9 + (row % 2 ? 0.45 : 0), y]);
                } else {
                    const x = side === 2 ? x1 + d : x0 - d;
                    S(this.box(null, 0.6, hy + 6, (z - floorZ) / 2, standM, x, cy, (z + floorZ) / 2));
                    spots = Array.from({length: Math.floor((hy + 5) * 2 / 0.9)}, (_, k) => [x, y0 - 5 + k * 0.9 + (row % 2 ? 0.45 : 0)]);
                }
                if (!crowd) continue;
                for (const [x, y] of spots) {
                    if (rnd() >= 0.8) continue;
                    const tall = 0.22 + rnd() * 0.08;
                    S(this.tinted(this.box(null, 0.19, 0.14, tall, crowdM, x, y, z + tall), shirts[Math.floor(rnd() * shirts.length)]));
                    S(this.tinted(this.box(null, 0.09, 0.09, 0.1, crowdM, x, y, z + tall * 2 + 0.11), skins[Math.floor(rnd() * skins.length)]));
                }
            }
        }
        // big screens at both ends with the hall's name
        for (const [y, back] of [[y1 + 9, -1], [y0 - 9, 1]]) {
            S(this.box(null, 6.5, 0.3, 2.0, M("screen", [0.08, 0.08, 0.1], 1, 1, "steel"), cx, y, 6.0));
            S(this.box(null, 6.2, 0.05, 1.75, M("screenglow", [0, 0, 0], 1, 0, null, null, [0.05, 0.02, 0.12]), cx, y + 0.3 * back, 6.0));
            // (each screen's words face the rings: the window's TextNode, 1.6 a unit; its glowing orange comes out of its tone curve
            // nearly white, as the ultra screens')
            const name = this.words(look.name || "FIGHT LAB", 1.6, this.wire ? "#ffffff" : "#f8eabf", 1.0, [cx, y + 0.4 * back, 5.55], [back < 0 ? 0 : 180, 0, 0]);
            if (this.wire) this.lettering(name);
        }
        // the lighting truss over the rings
        const truss = [], trussM = M("truss", [0.2, 0.2, 0.22], 1, 1, "steel"), lampM = M("lamp", [1, 1, 1], 0.3, 0, null, null, [6, 5.5, 5]);
        for (const y of [0, 16]) {
            truss.push(this.box(null, hx, 0.15, 0.15, trussM, cx, y, 8.5));
            for (const x of [-16, 0, 16]) for (const dx of [-2.5, 2.5]) truss.push(this.box(null, 0.3, 0.25, 0.12, lampM, x + dx, y, 8.3));
        }
        for (const x of [x0, x1]) for (const y of [0, 16]) truss.push(this.box(null, 0.2, 0.2, 4.8, trussM, x, y, floorZ + 4.8));
        this.rig = this.mergeStatic(truss);
    }

    // a box in its own colour (a person in the crowd): vertex colours, so a whole crowd is one mesh
    tinted(mesh, rgb) {
        const n = mesh.getTotalVertices(), c = new Array(n * 4);
        for (let i = 0; i < n; i++) { c[i * 4] = rgb[0]; c[i * 4 + 1] = rgb[1]; c[i * 4 + 2] = rgb[2]; c[i * 4 + 3] = 1; }
        mesh.setVerticesData(BABYLON.VertexBuffer.ColorKind, c);
        return mesh;
    }

    // ---------- the fighters ----------
    setFighters(list) {
        for (const f of this.fighters.values()) { f.label.dispose(false, true); if (f.plate) f.plate.dispose(false, true); f.root.dispose(); if (f.model) f.model.dispose(); }
        this.fighters.clear();
        this.list = list;
        for (const f of list) this.addFighter(f);
    }

    // (CHANGE 150) words as the window's TextNode writes them: fighters.js's fightWords (the fighters' number plates
    // use it too)
    words(text, scale, colour, paint, pos, hpr, parent = null) {
        return this.fightWords(text, scale, colour, paint, pos, hpr, parent);
    }

    // fs: [{id, pos, h, a, k, hu, ri (its ring), ...}] for the drawn rings; dt seconds
    frame(fs, rings, dt, t) {
        const seen = new Set();
        const closeUp = ["fight", "me", "shoulder"].includes(this.cam.mode), watched = this.watchRing ?? 0;
        for (const s of fs) {
            const f = this.fighters.get(s.id);
            if (!f) continue;
            seen.add(s.id);
            const hide = s.pos[2] < -1.5;
            f.root.setEnabled(!hide);
            f.label.setEnabled(!hide && !(closeUp && s.ri === watched));  // (the fight screen shows their names)
            if (hide) { if (f.model) f.model.show(false); continue; }
            this.poseFighter(f, s, dt);
        }
        for (const [id, f] of this.fighters) if (!seen.has(id)) { f.root.setEnabled(false); f.label.setEnabled(false); if (f.model) f.model.show(false); }
        // the camera first (the effects that face it face it where it is drawn), then the stage's moving parts and
        // the effects (fight_gfx.StageVisual.update, fight_fx.Effects.update)
        this.updateCamera(fs, rings, dt);
        this.stageT += dt;
        const T = this.stageT, fx = this.fx;
        fx.begin();
        const byIndex = new Map(rings.map(r => [r.i, r]));
        const G = this.glowLines || {};  // (the line tiers: the glowing parts' lines pulse as they glow: CHANGE 147)
        for (const [i, jets] of this.jets) {
            const powers = ((byIndex.get(i) || {}).hz || {}).jets || [];
            jets.forEach(([x, y, lines], k) => {
                const p = powers[k] || 0;
                if (lines) {  // (a flame of lines, growing with the jet and flickering)
                    lines.setEnabled(p > 0.05);
                    if (p > 0.05) lines.scaling.set(0.8 + 0.4 * p, 0.4 + 1.5 * p, 0.8 + 0.4 * p);
                } else if (p > 0.05) fx.jet(x, y, p, T);
            });
            this.pulseLine(G["jet" + i], 0.65 + 0.35 * Math.abs(Math.sin(T * 17 + i)));
        }
        for (const [i, g] of this.glows) {
            if (g.ropes) {  // electric ropes: a steady blue pulse, a white-blue flicker for a moment after a zap
                if ((this.zapUntil[i] ?? -1) > T) {
                    const f = Math.floor(T * 30) % 2 ? 6 : 2;
                    this.setGlow(g.ropes, [f * 0.6, f * 0.9, f * 1.6]);
                    this.pulseLine(G["ropes" + i], f === 6 ? 1 : 0.3);
                } else {
                    const pulse = 0.8 + 0.4 * Math.sin(T * 6 + i);
                    this.setGlow(g.ropes, [0.3 * pulse, 0.9 * pulse, 2.6 * pulse]);
                    this.pulseLine(G["ropes" + i], 0.5 + 0.4 * pulse);
                }
            }
            if (g.edge) {  // an open edge's glowing line breathes
                const pulse = 0.75 + 0.25 * Math.sin(T * 3 + i);
                this.setGlow(g.edge, EDGE_GLOW.map(c => c * pulse));
                this.pulseLine(G["edge" + i], pulse);
            }
        }
        let shots = 0;
        for (const r of rings) for (const sh of r.sh || []) if (shots++ < 12) fx.shot(sh, T);
        fx.update(dt);
        this.followSun();
    }

    // the hits (m.fx: [pos, damage, kind]) as the window takes them: the victim is the fighter nearest the hit (its
    // colour for the debris; a robot throws more sparks); a zap flashes that ring's electric ropes
    impacts(list, rings) {
        if (!this.fx || !list || !list.length) return;
        const all = (rings || []).flatMap(r => r.f || []);
        for (const [pos, dmg, kind] of list) {
            let best = null, far = Infinity;
            for (const f of all) {
                const d = (f.pos[0] - pos[0]) ** 2 + (f.pos[1] - pos[1]) ** 2 + (f.pos[2] - pos[2]) ** 2;
                if (d < far) { far = d; best = f; }
            }
            const v = best ? this.fighters.get(best.id) : null, d = v ? v.design || {} : {};
            const colour = v && Array.isArray(d.colour) ? rgb255(d.colour) : [0.8, 0.8, 0.8];
            this.fx.impact(pos, dmg, kind, colour, (d.body || "robot") === "robot");
            if (kind === "zap") this.zap(pos);
        }
    }

    zap(pos) {  // (fight_gfx.StageVisual.zap: the nearest ring's electric ropes flash)
        let best = null, far = Infinity;
        for (const i of this.setup.rings || [0]) {
            const [cx, cy] = RING_CENTRES[i] || [0, 0], d = Math.hypot(pos[0] - cx, pos[1] - cy);
            if (d < far) { far = d; best = i; }
        }
        if (best !== null) this.zapUntil[best] = this.stageT + 0.35;
    }

    // the window's camera (fight_camera.FightCamera.update, fightfx.js), on the watched ring: your fighter (or the
    // first in the ring) and the other one, then the shake from big hits (half of fight_fx's, as fight_client passes
    // it): the camera moves, what it looks at doesn't
    updateCamera(fs, rings, dt) {
        const cam = this.camera, watched = this.watchRing ?? 0;
        if (this.snapCamera) { this.cam.pos = null; this.snapCamera = false; }
        const ring = rings.find(r => r.i === watched) || null;
        const here = fs.filter(s => s.ri === watched && (s.a !== "ringout" || s.pos[2] > -1.5));
        const first = (this.focusId !== null ? here.find(s => s.id === this.focusId) : null) || here.find(s => s.id === this.myId) || here[0] || null,
              other = here.find(s => s !== first) || null;
        const centreOf = r => r.c || RING_CENTRES[r.i] || [0, 0];
        const v = this.cam.update(dt, first ? first.pos.slice() : null, other ? other.pos.slice() : null,
                                  ring ? centreOf(ring) : [0, 0], rings.map(centreOf));
        const rig = ["fight", "me", "shoulder"].includes(v.mode);  // (the high views look down past the lighting rig: hidden)
        for (const m of this.rig || []) m.isVisible = rig;
        const off = this.fx ? this.fx.shakeOffset() : null;
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;  // (Panda's lens: the fov is across)
        cam.fov = v.fov * D2R;
        cam.minZ = 0.1;
        cam.setTarget(v3(...v.look));
        cam.setPosition(v3(v.pos[0] + (off ? off[0] : 0), v.pos[1] + (off ? off[1] : 0), v.pos[2] + (off ? off[2] : 0)));
    }

    setMode(mode) {
        this.cam.setMode(mode);
        this.snapCamera = true;
    }
}

// (CHANGE 201) the fighters' own methods (fighters.js), shared with City Lab's scene
Object.assign(FightScene.prototype, FighterParts);

export class FightGame {
    static detect(m) { return !!(m.rules && m.rules.styles && m.rules.bosses); }

    constructor(app) {
        this.app = app;
        this.id = "fightlab";
        // (CHANGE 167) your fighter's footwork drawn at once (ahead.js); each fighter's from the roster
        this.ahead = new FighterAhead();
        this.move = new Map();
        this.aheadNote = "your fighter's steps drawn as you press the keys";  // (app.js: the Graphics tab's Movement row)
        this.title = "Fight Lab";
        this.word = "fighter";
        this.scene = new FightScene(app.canvas, app.tier, app.engine);
        this.watch = null;
        this.focus = null;  // (CHANGE 183) the fighter the camera follows (L), null = your own
        this.mods = ["mods/stage.py", "mods/rules.py", "mods/fighters/<username>.py"];
        this.last = null;
        this.events = new Set();
        this.pickA = this.pickB = "";
        this.controlKind = "fight";  // (play.js: the arrows move, A S D W Space F the moves, Shift blocks, X crouches)
        this.hud = new FightHud();
        // (CHANGE 143) B: the rings box small (the title and the mode line) or full, kept on this computer as the
        // window keeps rings_small
        try { this.boardSmall = localStorage.getItem("rings_small") === "1"; } catch (e) { this.boardSmall = false; }
        this.hookCamera();
    }

    // B, or the rings box's Hide/Show button (fight_client.toggle_rings)
    toggleBoard() {
        this.boardSmall = !this.boardSmall;
        try { localStorage.setItem("rings_small", this.boardSmall ? "1" : "0"); } catch (e) { /* private window */ }
        this.renderBoard();
    }

    // (CHANGE 143) the window's keys (fight_client's key list and its camera keys), for a key list or help
    keyList() {
        const learner = this.app.state.role === "learner";
        return [["Arrows", "move (up and down sidestep)"], ["A", "punch (again for a combo)"], ["S", "kick (forward + S: high kick)"], ["D", "special"],
                ["W", "throw"], ["Space", "jump"], ["F", "cartwheel (when it's on)"], ["Shift", "block"], ["X", "crouch (X + Shift: low block)"],
                ...(learner ? [["P", "autopilot"], ["U", "upload a brain"]] : []),
                ["V", "camera view"], ["Q and E, or drag", "swing the view round (drag up and down tilts it)"], ["Wheel, + and -", "zoom"],
                ["Home", "the view back as it was"], ["O", "every ring"], ["L", "watch the next fighter (then V for the view)"],
                ["[ and ]", "watch another ring"], ["B", "the rings box: small or full"],
                ...(learner ? [] : [["Shift+F", "fix your fighter"]]),
                ["N", "sound on or off"]];
    }

    // the window's camera controls: dragging swings the view round and tilts it, the wheel (or + and -) zooms the
    // view in use, Q and E swing it round, Home puts it back, O shows every ring, [ and ] watch another ring
    hookCamera() {
        const canvas = this.app.canvas, cam = () => this.scene.cam;
        this.listeners = [
            [canvas, "wheel", e => { cam().wheel(this.app.wheelZoom ? this.app.wheelZoom(e) : e.deltaY > 0 ? 1 / 0.88 : 0.88); this.keepCamera(); }, {passive: true}],  // (the Settings' Wheel zoom: CHANGE 143)
            [canvas, "pointerdown", e => { this.dragFrom = [e.clientX, e.clientY]; try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* gone */ } }],
            [canvas, "pointermove", e => {
                if (!this.dragFrom) return;
                cam().drag((e.clientX - this.dragFrom[0]) / Math.max(1, canvas.clientWidth), (e.clientY - this.dragFrom[1]) / Math.max(1, canvas.clientHeight));
                this.dragFrom = [e.clientX, e.clientY];
            }],
            [canvas, "pointerup", () => { if (this.dragFrom) { this.dragFrom = null; this.keepCamera(); } }],
            [canvas, "pointercancel", () => { this.dragFrom = null; }],
            [canvas, "contextmenu", e => e.preventDefault()],  // (the window drags with the right button)
            [window, "keydown", e => {
                const a = document.activeElement;
                if (e.ctrlKey || e.metaKey || e.altKey || (a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName)) || !this.app.state.connected) return;
                const k = e.key.length === 1 ? e.key.toLowerCase() : e.key, c = cam();
                if (k === "q") c.turn(e.repeat ? 6 : 20);
                else if (k === "e") c.turn(e.repeat ? -6 : -20);
                else if (k === "Home") c.resetView();
                else if (k === "o") { this.scene.setMode("all"); this.app.updatePills(); }
                else if (k === "=" || k === "+") c.wheel(e.repeat ? 0.9 : 0.8);
                else if (k === "-") c.wheel(e.repeat ? 1.11 : 1.25);
                else if (k === "[" || k === "]") this.watchRing(k === "[" ? -1 : 1);
                else return;
                this.keepCamera();
            }],
        ];
        for (const [el, ev, fn, opts] of this.listeners) el.addEventListener(ev, fn, opts);
    }

    // a learner's camera kept in their profile, as the window keeps it (fight_camera.settings)
    keepCamera() {
        if (this.app.state.role === "learner" && this.app.keepPrefs) this.app.keepPrefs({camera: this.scene.cam.settings()});
    }

    // [ and ]: watch the next ring (fight_client.watch_ring); the view of every ring goes back to the fight
    watchRing(delta) {
        const rings = ((this.last || {}).rings || []).map(r => r.i);
        if (!rings.length) return;
        const cur = rings.indexOf(this.watched()), next = rings[((cur < 0 ? 0 : cur) + delta + rings.length) % rings.length];
        const r = this.roster, id = this.myId(), mine = r && id !== null ? ((r.fighters || []).find(x => x.id === id) || {}).ring : undefined;
        this.watch = next === mine ? null : next;
        this.focus = null;  // (another ring: the camera follows your own fighter, or the ring's first)
        this.scene.setMode(this.scene.mode !== "all" ? this.scene.mode : "fight");
        this.renderBoard();
        if (this.app.toast) this.app.toast(`Watching ring ${next + 1}${next === mine ? "  (yours)" : ""}`);
        this.app.updatePills();
    }

    // (CHANGE 183) L: the camera follows the next fighter: round the ring watched, then the next ring's fighters
    // (watching that ring), and back to your own, as the window's cycle_focus; V then changes the view of them.
    cycleWatch() {
        const rings = (this.last || {}).rings || [], w = this.watched();
        const k = Math.max(0, rings.findIndex(r => r.i === w));
        const order = rings.slice(k).concat(rings.slice(0, k)).flatMap(r => (r.f || []).map(f => [r.i, f.id]));  // (from the watched ring on)
        if (!order.length) return;
        const ids = order.map(x => x[1]), my = this.myId();
        const cur = this.focus !== null && ids.includes(this.focus) ? this.focus : my;
        const [ringI, next] = order[(ids.indexOf(cur) + 1) % order.length];
        if (this.scene.mode === "ring" || this.scene.mode === "all") this.scene.setMode("me");  // (a view that follows nobody: on them instead)
        if (ringI !== w) {
            const mine = this.myRing();
            this.watch = ringI === mine ? null : ringI;
            this.scene.watchRing = this.watched();
            this.renderBoard();
        }
        this.focus = next === my ? null : next;
        this.scene.focusId = this.focus;
        this.scene.snapCamera = true;  // (cut straight to them)
        const info = ((this.roster || {}).fighters || []).find(x => x.id === next) || {};
        if (this.app.toast) this.app.toast(this.focus === null ? (my !== null && ids.includes(my) ? "Camera: your fighter" : "Camera: the ring")
                                           : `Camera: ${(info.design || {}).name || "?"}${info.owner ? ` (${info.owner})` : ""}`);
        this.app.updatePills();
    }

    // (CHANGE 182) Shift+F, the teacher only (app.js checks the role): the server mends the teacher's own fighter
    fixMine() { this.app.send({type: "fix"}); }

    welcome(m) {
        const p = this.app.params;
        if (p.get("cam")) this.scene.setMode({tv: "fight", chase: "fight", overview: "all"}[p.get("cam")] || p.get("cam"));
        else if ((m.prefs || {}).camera) this.scene.cam.restore(m.prefs.camera);  // (the view kept in their profile)
    }

    myId() {
        const S = this.app.state, r = this.roster;
        const id = r && r.mine ? r.mine[S.name] : null;
        return id === undefined ? null : id;
    }

    // (CHANGE 143) your fighter's ring (fight_client.my_ring): the newest snapshot's, else the roster's; null with none
    myRing() {
        const id = this.myId();
        if (id === null) return null;
        const r = ((this.last || {}).rings || []).find(x => (x.f || []).some(f => f.id === id));
        if (r) return r.i;
        const f = ((this.roster || {}).fighters || []).find(x => x.id === id);
        return f && Number.isInteger(f.ring) ? f.ring : null;
    }

    // the arrows as (forward, side) for your fighter, as fight_client.stick does: the camera decides which way is
    // which, so right always moves right on the screen; forward is towards your opponent
    stick(sx, sy) {
        const id = this.myId(), m = this.last;
        const ring = m ? (m.rings || []).find(r => (r.f || []).some(x => x.id === id)) : null;
        const mine = ring ? ring.f.find(x => x.id === id) : null;
        if (!mine) return [0, 0];
        const other = ring.f.find(x => x.id !== id);
        const cam = this.scene.camera;
        const r = cam.getDirection(BABYLON.Axis.X), a = cam.getDirection(BABYLON.Axis.Z);
        let right = [r.x, r.z], ahead = [a.x, a.z];  // (Babylon's x and z are the game's x and y)
        const norm = v => { const l = Math.hypot(v[0], v[1]); return l < 1e-3 ? null : [v[0] / l, v[1] / l]; };
        right = norm(right); ahead = norm(ahead);
        if (!right || !ahead) return [sy, -sx];
        const want = [right[0] * sx + ahead[0] * sy, right[1] * sx + ahead[1] * sy];
        let face = other ? [other.pos[0] - mine.pos[0], other.pos[1] - mine.pos[1]]
                         : [-Math.sin(mine.h * Math.PI / 180), Math.cos(mine.h * Math.PI / 180)];
        face = norm(face);
        if (!face) return [sy, -sx];
        const left = [-face[1], face[0]];
        const clamp = v => Math.max(-1, Math.min(1, v * 1.4));
        return [clamp(want[0] * face[0] + want[1] * face[1]), clamp(want[0] * left[0] + want[1] * left[1])];
    }

    cycleCamera() {  // V: the window's five views (fight camera, my fighter, over the shoulder, ring view, all rings)
        this.scene.setMode(CAM_MODES[(CAM_MODES.indexOf(this.scene.mode) + 1) % CAM_MODES.length]);
        this.keepCamera();
    }

    learnerTabs() { return [["camera", "Camera"]]; }

    controlSent(msg, now) {  // (play.js: CHANGE 167; a punch's start-up drawn at once: CHANGE 193)
        this.ahead.control(now / 1000, msg.f, msg.s, msg.hold);
        if (msg.press) this.ahead.press(now / 1000, msg.press);
    }

    message(m) {
        if (m.type === "roster") {
            this.roster = m;
            this.move = new Map((m.fighters || []).filter(x => x.move).map(x => [x.id, x.move]));  // (CHANGE 167)
            this.punch = new Map((m.fighters || []).filter(x => x.punch).map(x => [x.id, x.punch]));  // (CHANGE 193)
            this.scene.setSetup({rings: m.rings || [0], rs: m.rs || 4.5, hazards: m.hazards || {}, look: m.look || {}});
            this.scene.setFighters(m.fighters || []);
            this.scene.watchRing = this.watched();
            this.renderBoard();
            return true;
        }
        if (m.type === "state") {
            m.sm = m.sm >>> 0;
            const myId = this.myId();  // (the server's acks: how long our key presses take to show)
            if (myId !== null && m.acks && m.acks[myId] !== undefined && this.app.ctrl) this.app.ctrl.ack(m.acks[myId], performance.now());
            this.app.pushSnap(m, performance.now());
            const mine = myId !== null ? (m.rings || []).find(r => (r.f || []).some(x => x.id === myId)) : null;
            this.ahead.snapshot(m.sm / 1000, mine ? mine.f : [], myId, mine ? mine.ph : null);  // (CHANGE 167, 193)
            this.last = m;
            this.scene.impacts(m.fx || [], m.rings || []);  // (sparks, flashes, dust, debris and the shake: fightfx.js)
            this.impacts = (this.impacts || []).concat(m.fx || []);  // (heard on the next frame: sound.js)
            for (const e of m.events || []) if (!this.events.has(e)) { this.events.add(e); this.app.addEvent(e); }
            if (this.events.size > 200) this.events = new Set([...this.events].slice(-60));
            this.renderBoard();
            return true;
        }
        return false;
    }

    binary() {}

    watched() {
        if (this.watch !== null) return this.watch;
        const S = this.app.state, r = this.roster;
        const mine = r && r.mine ? r.mine[S.name] : null;
        const f = mine !== null && mine !== undefined && r ? (r.fighters || []).find(x => x.id === mine) : null;
        return f ? f.ring : ((r && r.rings) || [0])[0] ?? 0;
    }

    frame(now, dt) {
        const pair = this.app.samplePair(now);
        if (!pair) { this.scene.frame([], [], dt, now / 1000); return; }
        const {a, b, f} = pair;
        const bRings = b ? new Map((b.rings || []).map(r => [r.i, r])) : new Map();
        let fighters = [];
        for (const ra of a.rings || []) {
            const rb = bRings.get(ra.i);
            const byId = rb ? new Map((rb.f || []).map(x => [x.id, x])) : new Map();
            for (const x of ra.f || []) {
                const y = byId.get(x.id);
                if (!y) { fighters.push({...x, ri: ra.i}); continue; }
                fighters.push({...y, pos: x.pos.map((v, i) => lerp(v, y.pos[i], f)), h: lerpDeg(x.h, y.h, f),
                               k: x.a === y.a ? lerp(x.k, y.k, Math.min(1, f)) : y.k, ri: ra.i});
            }
        }
        const S = this.app.state, my = this.myId();
        if (S.gfx && S.gfx.ahead && S.offset !== null && my !== null) {  // (CHANGE 167: your footwork drawn at once)
            const ri = (fighters.find(x => x.id === my) || {}).ri;
            if (ri !== undefined) {
                const drawn = new Map(this.ahead.adjust(fighters.filter(x => x.ri === ri), now / 1000, (now - S.offset) / 1000,
                                                        S.rttS ?? (S.pingMs || 0) / 1000, my, this.move.get(my) || null, dt,
                                                        (this.punch && this.punch.get(my)) || null).map(x => [x.id, x]));
                fighters = fighters.map(x => drawn.get(x.id) || x);
            }
        }
        this.scene.watchRing = this.watched();
        this.scene.myId = my;
        this.scene.focusId = this.focus;  // (L: another fighter followed)
        this.scene.frame(fighters, (b || a).rings || [], dt, now / 1000);
        // the fight screen (hud.js): the watched ring's two fighters, from the newest snapshot
        const watched = this.watched(), ring = this.last ? (this.last.rings || []).find(r => r.i === watched) : null;
        const names = new Map(((this.roster || {}).fighters || []).map(x => [x.id, {name: (x.design || {}).name || "?", owner: x.owner || ""}]));
        // (CHANGE 143) RING n over the timer when the ring watched isn't yours (fight_client: watched != my_ring)
        this.hud.update(ring, names, this.myId(), ((this.app.state.lesson || {}).rounds_to_win) || 2, dt, now,
                        ring && watched !== this.myRing() ? `RING ${watched + 1}` : "");
        if (this.app.sound && this.last) {  // the hits, the bell, the crowd (sound.js, fight_client's sounds)
            this.app.sound.fightFrame(this.last.rings || [], this.impacts || [], this.watched(),
                {robots: Sound.fightRobots((this.roster || {}).fighters), listener: Sound.listenerFrom(this.scene.camera), now: now / 1000});
            this.impacts = [];
        }
        document.body.classList.toggle("fightscreen", !!ring && this.myId() !== null);
    }

    // (CHANGE 143) the window's rings box (fight_client.hud_dark, top left under the health bars), for the teacher and
    // a player alike: the title (FIGHT LAB, TEACHER: or LEARNER: and the name) with Hide or Show (B), the mode line
    // (PRACTICE or BATTLE, PAUSED, the tournament or its champion), and, full, every ring's fight, the watched ring
    // yellow, your fighter starred. #places is .fightboard (and .small when B has made it small); the fight screen's
    // banner is the HUD's (hud.js), so #race is left empty
    renderBoard() {
        const S = this.app.state, m = this.last, esc = this.app.esc, el = $("places");
        if (!m || !this.roster) return;
        const names = new Map((this.roster.fighters || []).map(x => [x.id, x]));
        const w = this.watched(), myId = this.myId();
        const lines = (m.rings || []).map(r => {
            const fs = (r.f || []).map(x => {
                const info = names.get(x.id) || {design: {}};
                const pc = Math.max(0, Math.round(100 * x.hp / Math.max(1, x.max || 0)));
                return `${x.id === myId ? "*" : ""}${esc(info.design.name || "?")} ${pc}%${x.w ? ` (${x.w})` : ""}${x.ap ? " AUTO" : ""}`;
            }).join("  v  ");
            const tail = r.bn ? r.bn : r.tl === null || r.tl === undefined ? "training" : `round ${r.rd}  ${Math.max(0, Math.floor(r.tl || 0))} s`;
            return `<div data-ring="${r.i}" class="fring ${r.i === w ? "watched" : ""}"><span>Ring ${r.i + 1}${r.lb ? ` - ${esc(r.lb)}` : ""}: ${fs || "empty"}</span><span class="lap">${esc(tail)}</span></div>`;
        });
        const T = S.tournament, teacher = S.role !== "learner";
        const mode = (m.practice ? "PRACTICE (no damage)" : "BATTLE") + (m.paused ? " · PAUSED" : "") +
                     (T ? ` · TOURNAMENT: ${T.champion ? `CHAMPION ${T.champion}` : T.title || ""}` : "");
        const head = `<div class="bhead"><b class="${teacher ? "teacher" : ""}">FIGHT LAB · ${teacher ? "TEACHER" : "LEARNER"}: ${esc(S.name || "")}</b>` +
                     `<button id="fb-small" title="B does the same">${this.boardSmall ? "Show" : "Hide"}</button></div>` +
                     `<div id="fb-mode" class="fmode">${esc(mode)}</div>`;
        el.classList.add("fightboard");
        el.classList.toggle("small", !!this.boardSmall);
        el.innerHTML = head + (this.boardSmall ? "" : `<div class="ftitle"><small>RINGS ([ and ] watch another ring, B hides this)</small></div>` +
                                                     (lines.join("") || "<div class='fring'><small>No rings</small></div>"));
        $("fb-small").onpointerdown = () => this.toggleBoard();  // (not onclick: the box is redrawn 30 times a second)
        el.querySelectorAll("div[data-ring]").forEach(d => d.onpointerdown = () => { this.watch = Number(d.dataset.ring); this.renderBoard(); this.app.updatePills(); });
        $("countdown").textContent = $("phase").textContent = "";
    }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${L.mode === "battle" ? "battle" : "practice"} · ${L.rings ? `${L.rings} rings` : "rings: auto"}` : "";
    }

    cameraPill() {
        return `Camera: ${CAM_NAMES[this.scene.mode] || ""} (V to change)`;
    }

    tabs() { return [["controls", "Controls"], ["matches", "Matches"], ["camera", "Camera"]]; }

    learnerHead() { return ["Fighter", "Ring"]; }
    learnerCells(p) {
        const r = this.roster || {};
        const id = r.mine ? r.mine[p.name] : null;
        const f = (r.fighters || []).find(x => x.id === id);
        return [this.app.esc((p.design && p.design.name) || ""), f ? f.ring + 1 : ""];
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, R = S.rules || {}, send = app.send, esc = app.esc;
        const lessonSend = patch => send({type: "lesson", lesson: patch});
        if (!L && tab !== "camera") { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return ["controls", "matches"].includes(tab); }
        const people = (S.classList || []).filter(p => p.role === "learner").map(p => p.name).concat(L && L.teacher_fighter ? ["Teacher"] : []);
        if (tab === "controls") {
            const levels = Object.entries(R.cpu_levels || {});
            // (CHANGE 143) who is where: each fighter's list (ids that stay the same, CHANGE 142), and where they are
            // now, as the window greys their ring or says "sitting out" (fight_client's Rings rows)
            const where = new Map(((this.roster || {}).fighters || []).map(f => [f.owner, f.ring]));
            const key = s => String(s).replace(/[^A-Za-z0-9]/g, ch => "_" + ch.charCodeAt(0).toString(16));
            const placeHtml = people.map((n, i) => {
                const v = (L.places || {})[n], set = Number.isInteger(v) ? v : null, now = where.get(n === "Teacher" ? S.name : n);
                const at = Number.isInteger(now) ? now : null;
                return `<div class="row"><label>${n === "Teacher" ? "My fighter" : esc(n)}</label><select id="fb-at-${key(n)}" data-place="${i}" data-v="${set ?? ""}"><option value="">any</option>${
                    Array.from({length: Math.max(L.rings, (set ?? -1) + 1)}, (_, k) => `<option value="${k}" ${set === k ? "selected" : ""}>ring ${k + 1}</option>`).join("")}</select>` +
                    (at === null ? `<small class="note sitout">sitting out</small>` : at !== set ? `<small class="note">in ring ${at + 1}</small>` : "") + `</div>`;
            }).join("");
            const rt = Number(L.round_time) || 60;
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The fights</h2>
              <div class="row"><button data-mode="practice" class="${L.mode !== "battle" ? "on" : ""}">Practice</button>
                <button data-mode="battle" class="${L.mode === "battle" ? "on" : ""}">Battle</button>
                <button id="fb-restart" class="go">RESTART</button>
                <button id="fb-pause" class="${this.last && this.last.paused ? "on" : ""}">${this.last && this.last.paused ? "RESUME" : "PAUSE"}</button></div>
              <div class="note">Practice: no damage and no timer. Battle: rounds of ${L.round_time} s, first to ${L.rounds_to_win}. RESTART begins new matches.</div>
              <div class="row"><label>Round time</label><button id="fb-time-down" ${rt <= 20 ? "disabled" : ""}>-10</button><b id="fb-time">${rt} s</b>
                <button id="fb-time-up" ${rt >= 300 ? "disabled" : ""}>+10</button><span class="note">20 to 300 s</span></div>
              <div class="row"><label>Rounds to win</label>${[1, 2, 3].map(k => `<button data-rtw="${k}" class="${k === L.rounds_to_win ? "on" : ""}">${k}</button>`).join("")}</div>
              <div class="row"><label>Sparring partners</label><button id="fb-cpu" class="${L.cpu_opponents ? "on" : ""}">${L.cpu_opponents ? "Computer fighters on" : "Off"}</button>
                <select id="fb-level" data-v="${esc(L.cpu_level || "")}">${levels.map(([k, n]) => `<option value="${k}" ${k === L.cpu_level ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
              <div class="row"><label>The computer plays</label><button data-cf="sparring" class="${L.cpu_fighter === "sparring" ? "on" : ""}">Sparring</button>
                ${Object.keys(R.bosses || {}).map(b => `<button data-cf="${esc(b)}" class="${L.cpu_fighter === b ? "on" : ""}">${esc(b)}</button>`).join("")}</div>
              ${L.cpu_level === "empty" ? `<div class="row"><label class="filebtn">Upload the demo brain (.py)<input id="fb-demo" type="file" accept=".py,text/plain" hidden></label></div>` : ""}
              <div class="row"><label>My fighter</label><button id="fb-mine" class="${L.teacher_fighter ? "on" : ""}">${L.teacher_fighter ? "In the class" : "Not in"}</button></div>
              <div class="row"><label>Designs</label><button id="fb-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              <h2>Rings</h2>
              <div class="row"><button data-rings="0" class="${!L.rings ? "on" : ""}">Auto</button>${[1, 2, 3, 4, 5, 6].map(k => `<button data-rings="${k}" class="${L.rings === k ? "on" : ""}">${k}</button>`).join("")}
                <button id="fb-turns">Take turns again</button></div>
              ${L.rings ? placeHtml + (people.length ? `<div class="note">Any: the rings take turns; a third in a ring sits out.</div>` : "") : `<div class="note">Auto: one ring each, matches share.</div>`}
              ${app.restartRow()}`;
            app.wireMissionRow(body);
            body.querySelectorAll("button[data-mode]").forEach(b => b.onclick = () => lessonSend({mode: b.dataset.mode}));
            $("fb-restart").onclick = () => send({type: "restart"});
            $("fb-pause").onclick = () => send({type: "pause"});
            // (CHANGE 143) -10 and +10 as the window's: any round time from 20 to 300 s (the server holds it there too)
            $("fb-time-down").onclick = () => lessonSend({round_time: Math.max(20, Math.min(300, rt - 10))});
            $("fb-time-up").onclick = () => lessonSend({round_time: Math.max(20, Math.min(300, rt + 10))});
            body.querySelectorAll("button[data-rtw]").forEach(b => b.onclick = () => lessonSend({rounds_to_win: Number(b.dataset.rtw)}));
            $("fb-cpu").onclick = () => lessonSend({cpu_opponents: !L.cpu_opponents});
            body.querySelectorAll("button[data-cf]").forEach(b => b.onclick = () => lessonSend({cpu_fighter: b.dataset.cf}));
            if ($("fb-demo")) $("fb-demo").onchange = async e => { const f = e.target.files[0]; if (f) send({type: "cpu_brain", source: await f.text()}); };
            $("fb-mine").onclick = () => lessonSend({teacher_fighter: !L.teacher_fighter});
            $("fb-lock").onclick = () => lessonSend({designs_locked: !L.designs_locked});
            body.querySelectorAll("button[data-rings]").forEach(b => b.onclick = () => lessonSend({rings: Number(b.dataset.rings)}));
            $("fb-turns").onclick = () => lessonSend({places: Object.fromEntries(people.map(n => [n, null]))});
            body.querySelectorAll("select[data-place]").forEach(sel => sel.onchange = () => {
                sel.dataset.v = sel.value;
                lessonSend({places: {[people[Number(sel.dataset.place)]]: sel.value === "" ? null : Number(sel.value)}});
            });
            $("fb-level").onchange = e => { e.target.dataset.v = e.target.value; lessonSend({cpu_level: e.target.value}); };
            // the panel's redraw puts back what each list held; a list not in use shows the server's own (a ring or a
            // level set elsewhere) once that is done (as robot.js's Arenas rows)
            queueMicrotask(() => body.querySelectorAll("select[data-v]").forEach(el => { if (el.isConnected && el !== document.activeElement) el.value = el.dataset.v; }));
            app.wireRestartRow(body);
            return true;
        }
        if (tab === "matches") {
            const T = S.tournament;
            const matches = L.matches || [];
            const opts = sel => `<option value="">pick</option>` + people.map(n => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("");
            body.innerHTML = `
              <h2>Matches</h2>
              <div class="row"><select id="fm-a">${opts(this.pickA)}</select> v <select id="fm-b">${opts(this.pickB)}</select><button id="fm-add" class="go">Add match</button></div>
              <table>${matches.map(([a, b], i) => `<tr><td>${esc(a)} v ${esc(b)}</td><td><button data-mrm="${i}">Remove</button></td></tr>`).join("") || "<tr><td class='note'>No matches set: everyone spars.</td></tr>"}</table>
              <div class="row"><button id="fm-clear">Clear all</button></div>
              <h2>Tournament (battle switched on, designs locked)</h2>
              ${!T ? `<div class="row"><button id="fm-knock" class="go">Knockout</button><span class="note">computer fighters fill the gaps</span></div>
                   <div class="row"><button id="fm-stays" class="go">Winner stays on</button></div>
                   <div class="note">Two rings live; the loser queues, the next challenger comes in; the rest watch ([ and ]).</div>`
                : T.kind === "stays" ? `<div class="row"><button id="fm-stop" class="stop">Stop: winner stays on</button></div>
                   ${(T.live || []).map(([a, b], i) => `<div>Ring ${i + 1}: ${esc(a || "-")} v ${esc(b || "-")}</div>`).join("")}
                   <div class="note">Waiting: ${(T.queue || []).map(esc).join(", ") || "nobody"}</div>
                   <div class="note">Matches played: ${T.played || 0}</div>
                   ${(T.table || []).length ? `<table>${T.table.slice(0, 12).map(([n, w, st]) => `<tr><td class="${w ? "ok" : ""}">${esc(n)}</td><td class="${w ? "ok" : ""}">${w} win${w !== 1 ? "s" : ""}${st > 1 ? ` · ${st} in a row` : ""}</td></tr>`).join("")}</table>` : ""}`
                : `<div class="row"><button id="fm-stop" class="stop">Stop the tournament</button></div>
                   ${T.champion ? `<p><b>CHAMPION: ${esc(T.champion)}</b></p>` : ""}
                   ${(T.rounds || []).map(rd => `<div style="color: var(--blue)">${rd.length === 1 ? "Final" : rd.length === 2 ? "Semi-finals" : rd.length === 4 ? "Quarter-finals" : "Round 1"}</div>` +
                       rd.map(([a, b, w]) => `<div class="${w ? "ok" : ""}">${esc(a)} v ${esc(b)}${w ? ` -&gt; ${esc(w)}` : " (fighting)"}</div>`).join("")).join("")}`}`;
            $("fm-a").onchange = e => { this.pickA = e.target.value; };
            $("fm-b").onchange = e => { this.pickB = e.target.value; };
            $("fm-add").onclick = () => {
                const a = $("fm-a").value, b = $("fm-b").value;
                if (!a || !b || a === b) return app.toast("Pick two different fighters.");
                const rest = matches.filter(([x, y]) => ![x, y].includes(a) && ![x, y].includes(b));
                lessonSend({matches: [...rest, [a, b]].slice(0, 6)});
            };
            body.querySelectorAll("button[data-mrm]").forEach(b => b.onclick = () => lessonSend({matches: matches.filter((_, i) => i !== Number(b.dataset.mrm))}));
            $("fm-clear").onclick = () => lessonSend({matches: []});
            if ($("fm-knock")) $("fm-knock").onclick = () => send({type: "tournament", start: true});
            if ($("fm-stays")) $("fm-stays").onclick = () => send({type: "tournament", start: true, kind: "stays", live: 2});  // (two rings, as the window's)
            if ($("fm-stop")) $("fm-stop").onclick = () => send({type: "tournament", start: false});
            return true;
        }
        if (tab === "camera") {
            const sc = this.scene, rings = (this.roster && this.roster.rings) || [0];
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row">${CAM_MODES.map(k => `<button data-view="${k}" class="${sc.mode === k ? "on" : ""}">${CAM_NAMES[k]}</button>`).join("")}</div>
              <div class="row"><button data-zoom="0.8">Closer</button><button data-zoom="1.25">Further</button><button id="fc-reset">Straight on again</button></div>
              <div class="note">V changes the view. The fight camera keeps both fighters in shot, side on; my fighter and over the shoulder follow your own fighter (or the first in the ring). Drag to swing the view round and tilt it (or Q and E), the wheel or + and − zoom, Home puts it back, O shows every ring, [ and ] watch another ring.</div>
              <h2>Watch a ring</h2>
              <div class="row">${rings.map(k => `<button data-ring="${k}" class="${this.watched() === k ? "on" : ""}">Ring ${k + 1}</button>`).join("")}</div>`;
            body.querySelectorAll("button[data-view]").forEach(b => b.onclick = () => { sc.setMode(b.dataset.view); this.keepCamera(); app.updatePills(); app.renderPanel(); });
            body.querySelectorAll("button[data-zoom]").forEach(b => b.onclick = () => { sc.cam.wheel(Number(b.dataset.zoom)); this.keepCamera(); });
            $("fc-reset").onclick = () => { sc.cam.resetView(); this.keepCamera(); };
            body.querySelectorAll("button[data-ring]").forEach(b => b.onclick = () => {
                this.watch = Number(b.dataset.ring);
                sc.setMode(sc.mode !== "all" ? sc.mode : "fight");
                this.renderBoard(); app.updatePills(); app.renderPanel();
            });
            return true;
        }
        return false;
    }

    dispose() {
        for (const [el, ev, fn, opts] of this.listeners || []) el.removeEventListener(ev, fn, opts);
        this.listeners = [];
        this.scene.dispose();
        $("places").innerHTML = "";
        $("places").classList.remove("fightboard", "small");  // (CHANGE 143: the next game's board is its own)
        document.body.classList.remove("fightscreen");
        $("countdown").textContent = $("phase").textContent = "";
    }
}
