// Robot Lab in Club Coders Live (CHANGE 130): the arena (lab_sim.py's constants, drawn after rw_gfx.ArenaVisual),
// its hazards from each snapshot (the drop zone, floor flipper, saws, wall spikes, Resident Robots, the user mods),
// the robots built from their designs with their weapons, the 30-a-second JSON states blended two behind, and the
// teacher's Robot Lab controls. Positions are game (x, y, z) -> Babylon (x, z, y); quaternions via gameQuat.
// The app's effects (rw_fx.py, in robotfx.js: sparks, saw showers, the flame jet, smoke and fire, debris, the camera
// shake) and rw_gfx.py's real damage (armour panels that bend, rattle and fly off, failing wheels, a shaking weapon,
// darkened and scorched parts, the hit bars), the saws' blur and hot rims, lasers, beacons and the running chain.
// (CHANGE 145) Every tier, as the window's since its CHANGE 145: mesh and lines draw the meshes black with their edges
// as lines (base3d.js), each moving part's own, a floor grid on lines, the glowing parts' lines pulsing; ultra draws
// the window's smooth robots and arena (robotfx.js, from models/robot_ultra.json and arena_ultra.json) once loaded.

/* global BABYLON */

import {BaseScene, TIERS, v3, col, rgb255, gameQuat, slerpQ, lerp, mulberry} from "./base3d.js";
import {toneMap} from "./pbr.js";
import {RobotsAhead} from "./ahead.js";
import {Sound} from "./sound.js";
import {AfterFx} from "./kartfx.js";
import {loadPandaFont, wordsSize, drawWords} from "./fightfx.js";
import {RobotFX, HitBar, RobotCamera, CAM_MODES, CAM_NAMES, qmul, qrot, hprQuat, quatHpr, fromBabylonQuat, loadRobotModels,
        robotModelsData, loadArenaModels, arenaModelsData, robotShapes, robotLayout, robotNodeMesh, robotAtlas, ROBOT_GLOW,
        makeUltraArena} from "./robotfx.js";

const $ = id => document.getElementById(id);
const ARENA = 20;
const PIT = [3.2, 3.2, 3.0], FF = [-3.5, -3.5], SAWS = [[4.5, -3.5], [-5.0, 3.5]];
const SPIKE_PIT = [-3.5, 7.0, 2.4], FLAME_PIT = [0, 0, 2.4], BOOST_PAD = [9.0, -3.0, 1.6], REPAIR_BAY = [-9.0, -4.0, 1.6];
const RAMPS = [[6.7, -2.1, -1], [-6.7, -2.1, 1]], RAMP = [2.6, 1.8, 0.7];  // (lab_sim: RAMP_RUN, RAMP_WIDE, RAMP_HIGH)
const STARTS = [[-7.5, 0], [7.5, 0], [-3.5, -7.5], [0, -7.5], [3.5, 7.5], [0, 7.5]];
const START_COLOURS = [[0.9, 0.25, 0.2], [0.25, 0.55, 1], [0.3, 0.85, 0.4], [1, 0.8, 0.2], [0.8, 0.4, 1], [1, 0.5, 0.2]];
const HOUSE_WEAPONS = {BLAZE: "flame", CRUSHER: "hammer", RIPSAW: "chainsaw", VORTEX: "vdisc"};
const SPINNERS = new Set(["spinner", "drum", "vdisc"]);
const STEEL = [0.6, 0.62, 0.66], DARK = [0.12, 0.12, 0.13], YELLOW = [0.95, 0.75, 0.08];
const PAINT_YELLOW = [0.95, 0.7, 0.05], CPZ = 4.8, GUTTER = 3.0;  // (rw_gfx.py, lab_sim.py)
// the window's five views (rw_camera.py): behind your robot, from its nose, the TV camera on the rail, the whole
// arena, the fixed centre camera (each with its own zoom, swing, tilt and sideways move: robotfx.RobotCamera)
export const RIG_MODES = CAM_MODES;
const RIG_NAMES = CAM_NAMES;
const HALF = 10.0;
const PARTS = ["armour", "weapon", "wheel0", "wheel1", "wheel2", "wheel3"];  // (lab_sim.PARTS: pt is the body's, then these)
const WHEELS = [[0.72, 0.55], [-0.72, 0.55], [0.72, -0.55], [-0.72, -0.55]];
const LEVELS = [["none", "No brain"], ["empty", "Empty"], ["easy", "Easy"], ["medium", "Medium"], ["expert", "Expert"]];

function designSize(d) {
    if (d.house) return 1.6;
    const s = ((d.settings || {}).size || 100) / 100;
    return d.model ? 1.6 * s : s;
}

// what is painted on a robot's deck, as the window paints it (lab_client.painted, CHANGE 152): a class robot's name (a
// saved robot's style may carry an old "number": the window doesn't paint it), a Resident Robot's style number
function deckNumber(d) {
    const style = d.style || {};
    return String((d.house && style.number !== undefined ? style.number : d.name) || "");
}

// lab_sim.floor_rects: the floor as rectangles (x0, y0, x1, y1) with the holes cut out (the drop zone, the floor
// flipper, and the pits the user mods add), as the window's floor and its grid on lines are made (CHANGE 145)
function floorRects(mods) {
    const h = ARENA / 2, holes = [[PIT[0] - PIT[2] / 2, PIT[1] - PIT[2] / 2, PIT[0] + PIT[2] / 2, PIT[1] + PIT[2] / 2], [FF[0] - 1.5, FF[1] - 1.0, FF[0] + 1.5, FF[1] + 1.0]];
    if (mods.spike_pit) holes.push([SPIKE_PIT[0] - SPIKE_PIT[2] / 2, SPIKE_PIT[1] - SPIKE_PIT[2] / 2, SPIKE_PIT[0] + SPIKE_PIT[2] / 2, SPIKE_PIT[1] + SPIKE_PIT[2] / 2]);
    if (mods.flame_pit) holes.push([FLAME_PIT[0] - FLAME_PIT[2] / 2, FLAME_PIT[1] - FLAME_PIT[2] / 2, FLAME_PIT[0] + FLAME_PIT[2] / 2, FLAME_PIT[1] + FLAME_PIT[2] / 2]);
    let rects = [[-h, -h, h, h]];
    for (const [hx0, hy0, hx1, hy1] of holes) {
        const out = [];
        for (const [x0, y0, x1, y1] of rects) {
            if (hx1 <= x0 || hx0 >= x1 || hy1 <= y0 || hy0 >= y1) { out.push([x0, y0, x1, y1]); continue; }
            if (hx0 > x0) out.push([x0, y0, hx0, y1]);
            if (hx1 < x1) out.push([hx1, y0, x1, y1]);
            const mx0 = Math.max(x0, hx0), mx1 = Math.min(x1, hx1);
            if (hy0 > y0) out.push([mx0, y0, mx1, hy0]);
            if (hy1 < y1) out.push([mx0, hy1, mx1, y1]);
        }
        rects = out;
    }
    return rects;
}

// (ultra, CHANGE 145) the hall's air the stands and walls fade into (rw_gfx.HAZE, linear) and how thick (per metre)
const HAZE = [0.012, 0.014, 0.02], HAZE_DENSITY = 0.012, EXPOSURE = 0.7;
// (CHANGE 152) the colours the window's words come out in, measured from its pictures (screen colours, 0 to 255): its
// TextNodes have no normals, so the arena's lights never reach them and each is one even colour on a tier (its
// ambient light, its reflections, its glow): the floor's name a pale grey-beige (its paint is yellow), the score on the
// big screen a pale yellow, a robot's name on its deck a light grey. blocks: as the window's basic; low: no reflections
const NAME_PAINT = {blocks: [137, 127, 115], low: [69, 53, 27], lit: [147, 136, 118]};
const SCORE_GLOW = {blocks: [242, 239, 186], low: [242, 239, 186], lit: [242, 239, 186]};
const DECK_PAINT = {blocks: [207, 207, 208], low: [207, 208, 208], lit: [213, 213, 213]};

export class RobotScene extends BaseScene {
    static TIERS = TIERS;  // (every tier, the line tiers and ultra too, as the window: CHANGE 145)
    // (the Graphics tab: what this game's ultra adds)
    // (ultra's after-effects, kartfx.js's AfterFx: a gentle glow on the lamps, LEDs and glowing parts and a little
    // sharpening, 4x MSAA on that picture as the window's ultra; no SSAO: 5 ms more a frame on an Iris Xe, a third of
    // the whole, where the glow costs half a millisecond; no reflection probe: six more views of a busy arena)
    static ULTRA_FX = {ssao: false, sharpen: true, samples: 4, bloomWeight: 0.25};
    static TIER_TEXT = {lines: "lines: black, the outlines in one colour and a grid on the floor (an old vector arcade game).",
                        ultra: "ultra: for a strong graphics card: the window's smooth robots (round edges, tread, bolts, machined weapons) and arena (steel plates, the cage, towers, the rig, the stands and their crowd), soft 4096 shadows, sharper textures at a slant."};

    constructor(canvas, tier, engine) {
        // rw_gfx.init's lights: a warm key light high over one corner, a spotlight on each corner tower aimed at the
        // middle, a dim blue fill, the arena's reflections; on ultra a haze over the hall alone (fog.picked: the far
        // parts' materials, as the window's), given as the colour the tone curve makes of its light
        super(canvas, tier, engine, {sky: [0.1, 0.11, 0.14], radius: 26, target: [0, 0, 0], ground: [0.25, 0.25, 0.28],
                                     sunDir: [-0.3, -0.85, 0.4],
                                     pbr: {background: [0.02, 0.02, 0.03], exposure: EXPOSURE, ambient: [0.05, 0.055, 0.07], sky: "env",
                                           fog: {colour: toneMap(HAZE, Math.pow(2, EXPOSURE)), density: HAZE_DENSITY, picked: true},
                                           sun: {colour: [1.5, 1.42, 1.3], offset: [8, -14, 30], film: 26, near: 5, far: 60, bias: 0.005, follow: false},
                                           spots: [[-1, -1, [1.0, 0.85, 0.7]], [1, -1, [0.75, 0.85, 1.0]], [-1, 1, [0.75, 0.85, 1.0]], [1, 1, [1.0, 0.85, 0.7]]]
                                               .map(([sx, sy, c]) => ({pos: [sx * 12.5, sy * 12.5, 8.5], at: [sx * 2, sy * 2, 0],
                                                                       colour: c.map(v => v * 3.2), fov: 38, att: [1, 0, 0.004]}))}});
        this.setup = {hazards: {}, user_mods: {}, look: {}};
        this.robots = new Map();
        this.designs = [];
        this.mode = "overview";
        this.follow = null;
        this.fx = null;
        this.cam = new RobotCamera("third");  // (the five views' own settings, kept over a tier change: CHANGE 143)
        this.build();
    }

    build() {  // (ultra's after-effects let go before the scene they were made for: CHANGE 145)
        if (this.after) { this.after.dispose(); this.after = null; }
        super.build();
    }

    populate() {
        // (ultra, CHANGE 145) the window's robots and arena once both files are here (asked for on ultra alone): high's
        // until then, or if they don't come; then everything is made again with them
        this.ultra = !!(this.settings.ultra && this.lighting);
        this.ultraArena = this.ultraRobots = false;
        this.wheelLines = {};
        this.lineCount = 0;
        if (this.ultra) {
            const scene = this.scene;
            Promise.all([loadRobotModels(), loadArenaModels()]).then(([r, a]) => {
                if (this.scene === scene && ((r && !this.ultraRobots) || (a && !this.ultraArena))) this.build();
            });
        }
        this.buildArena();
        this.after = this.ultra && RobotScene.ULTRA_FX ? new AfterFx(this, RobotScene.ULTRA_FX) : null;
        this.fx = new RobotFX(this);  // (rw_fx.Effects: sparks, smoke, fire, debris, the camera shake)
        this.shook = null;
        const designs = this.designs;
        this.robots.clear();
        for (const r of designs) this.addRobot(r);
        this.setMode(this.mode, this.follow);
    }

    setSetup(setup) {
        const key = JSON.stringify(setup);
        if (key === this.setupKey) return;
        this.setupKey = key;
        this.setup = setup;
        this.build();  // (the arena is cheap to build: a new one keeps the robots)
    }

    // ---------- the arena (rw_gfx.ArenaVisual: its colours, textures and roughness) ----------
    // (CHANGE 145) mesh and lines: the still parts' edges as lines (with a floor grid on lines), each moving part's
    // with it, the glowing parts' pulsing (arenaLines); ultra: the window's arena (robotfx.js's makeUltraArena) in
    // place of high's floor, walls, rails, posts, towers, lamps, rig, outside floor, stands, crowd and screen box, the
    // markings, hazards, user mods' items, the cage's screens, the arena's name and the gutter kept
    buildArena() {
        const hz = this.setup.hazards || {}, mods = this.setup.user_mods || {}, look = this.setup.look || {};
        const noCage = !!mods.no_cage, blocks = this.tier === "blocks", h = ARENA / 2;
        const file = this.ultra ? arenaModelsData() : null, ultra = !!file;
        this.ultraArena = ultra;
        const M = (name, rgb, rough, metal, tex, tile, emission) => this.material(name, rgb, rough, metal, 0, {tex, tile, emission});
        const floorM = blocks ? M("floor", [0.58, 0.59, 0.62], 1, 1) : M("floor", [1, 1, 1], 1, 1, "diamond", 0.6);
        const hazard = blocks ? M("hazard", YELLOW, 1, 0) : M("hazard", [1, 1, 1], 1, 0, "hazard", 0.8);
        const darkSteel = M("darksteel", [0.12, 0.12, 0.13], 1, 1, "steel", 0.6);
        const steel = M("steel", [1, 1, 1], 1, 1, "steel");
        const wall = M("wall", rgb255(look.wall_colour, [155, 25, 20]), 1, 1, "paint", 0.5);
        const statics = [];
        const S = m => { statics.push(m); return m; };
        this.glowLines = {};  // (the line tiers: the glowing parts' line materials, pulsed in frame())
        const moving = [];    // (the line tiers: [node, meshes, glow]: each moving part's lines move with it)
        // the floor, with holes for the drop zone and the flipper (and the pits a mod adds): lab_sim.floor_rects'
        // rectangles (CHANGE 145: as the window's, so its grid and edges on the line tiers match)
        const rects = floorRects(mods);
        if (!ultra) for (const [x0, y0, x1, y1] of rects) S(this.box(null, (x1 - x0) / 2, (y1 - y0) / 2, 0.25, floorM, (x0 + x1) / 2, (y0 + y1) / 2, -0.25));
        // markings: the Resident Robots' corner squares, the start squares, the centre circle, the arena's name
        const cz = CPZ / 2;
        for (const sx of [-1, 1]) for (const sy of [-1, 1]) {
            S(this.box(null, cz, cz, 0.004, hazard, sx * (h - cz), sy * (h - cz), 0.004));
            S(this.box(null, cz - 0.25, cz - 0.25, 0.004, M("zone", [0.12, 0.12, 0.13], 0.9, 0.3), sx * (h - cz), sy * (h - cz), 0.006));
        }
        STARTS.forEach(([x, y], i) => {
            const m = M("start" + i, START_COLOURS[i], 0.6, 0);
            for (const [ox, oy, hx, hy] of [[0, 1.1, 1.2, 0.07], [0, -1.1, 1.2, 0.07], [1.1, 0, 0.07, 1.2], [-1.1, 0, 0.07, 1.2]]) {
                S(this.box(null, hx, hy, 0.004, m, x + ox, y + oy, 0.005));
            }
        });
        const yellow = M("yellow", PAINT_YELLOW, 0.6, 0);
        for (let k = 0; k < 48; k++) {
            const a = k / 48 * Math.PI * 2;
            const d = S(this.box(null, 0.17, 0.05, 0.004, yellow, Math.cos(a) * 3, Math.sin(a) * 3, 0.005));
            d.rotation.y = -(a + Math.PI / 2);
        }
        if (!mods.flame_pit) {  // (the window's yellow paint, lit by the arena's lights; the line colour on the line tiers)
            const logo = this.words(String(look.name || "ROBOT LAB"), 1.2, NAME_PAINT, [0, -0.45, 0.012], [0, -90, 0]);
            if (this.wire) this.lettering(logo);
        }
        // the drop zone: a dark shaft, a striped rim, the lights round its edge and the lid that drops
        const [px, py, ps] = PIT;
        for (const [ox, oy, hx, hy] of [[0, ps / 2 + 0.05, ps / 2 + 0.1, 0.05], [0, -ps / 2 - 0.05, ps / 2 + 0.1, 0.05],
                                        [ps / 2 + 0.05, 0, 0.05, ps / 2], [-ps / 2 - 0.05, 0, 0.05, ps / 2]]) {
            S(this.box(null, hx, hy, 1.6, darkSteel, px + ox, py + oy, -1.6));
        }
        for (const [ox, oy, hx, hy] of [[0, ps / 2 + 0.2, ps / 2 + 0.35, 0.15], [0, -ps / 2 - 0.2, ps / 2 + 0.35, 0.15],
                                        [ps / 2 + 0.2, 0, 0.15, ps / 2 + 0.05], [-ps / 2 - 0.2, 0, 0.15, ps / 2 + 0.05]]) {
            S(this.box(null, hx, hy, 0.006, hazard, px + ox, py + oy, 0.006));
        }
        this.pitGlowMat = M("pitlights", [0, 0, 0], 1, 0, null, null, [4, 0.3, 0.1]);
        this.pitGlow = [[0, ps / 2, ps / 2, 0.02], [0, -ps / 2, ps / 2, 0.02], [ps / 2, 0, 0.02, ps / 2], [-ps / 2, 0, 0.02, ps / 2]]
            .map(([ox, oy, hx, hy]) => this.box(null, hx, hy, 0.02, this.pitGlowMat, px + ox, py + oy, -0.15));
        moving.push([null, this.pitGlow, "pit"]);
        this.pitLid = new BABYLON.TransformNode("pitlid", this.scene);
        this.pitLid.position = v3(px, py, 0);
        const lidParts = [this.box(this.pitLid, ps / 2 - 0.03, ps / 2 - 0.03, 0.25,
                                   blocks ? M("lid", [0.75, 0.75, 0.78], 1, 1) : M("lid", [0.75, 0.75, 0.78], 1, 1, "diamond", 0.6), 0, 0, -0.25)];
        const q = ps / 2 - 0.03;
        for (const [ox, oy, hx, hy] of [[0, q - 0.1, q, 0.1], [0, -q + 0.1, q, 0.1], [q - 0.1, 0, 0.1, q - 0.2], [-q + 0.1, 0, 0.1, q - 0.2]]) {
            lidParts.push(this.box(this.pitLid, hx, hy, 0.004, hazard, ox, oy, 0.004));
        }
        moving.push([this.pitLid, lidParts]);
        // the floor flipper: a dark recess, a steel frame, a striped plate hinged on its back edge, a warning lamp
        const [fx, fy] = FF;
        S(this.box(null, 1.5, 1.0, 0.02, M("recess", [0.02, 0.02, 0.02], 0.9, 0), fx, fy, -0.19));
        const frameM = M("frame", [0.15, 0.15, 0.16], 1, 1, "steel");
        for (const [ox, oy, hx, hy] of [[0, 1.03, 1.56, 0.03], [0, -1.03, 1.56, 0.03], [1.53, 0, 0.03, 1.0], [-1.53, 0, 0.03, 1.0]]) {
            S(this.box(null, hx, hy, 0.005, frameM, fx + ox, fy + oy, 0.005));
        }
        this.ffPivot = new BABYLON.TransformNode("ffpivot", this.scene);
        this.ffPivot.position = v3(fx, fy - 1.0, -0.08);
        this.ffPivot.rotationQuaternion = BABYLON.Quaternion.Identity();
        const hinge = M("hinge", [0.3, 0.3, 0.32], 1, 1, "steel");
        const ffParts = [this.box(this.ffPivot, 1.47, 0.97, 0.08, hazard, 0, 1.0, 0),
                         ...[-1, 1].map(s => this.cyl(this.ffPivot, 0.06, 0.25, "x", hinge, s * 0.9, 0.05, 0, null, 14))];
        this.ffLampMat = M("fflamp", [0.05, 0, 0], 0.4, 0, null, null, [0.2, 0, 0]);
        this.ffLamp = this.cyl(null, 0.12, 0.08, "z", this.ffLampMat, fx - 1.9, fy - 1.2, 0.08, null, 16);
        moving.push([this.ffPivot, ffParts], [null, [this.ffLamp], "fflamp"]);
        // the saws: a bolted cover plate with a black slot edged with lights, a blade that rises and spins
        const coverM = M("cover", [0.3, 0.3, 0.32], 1, 1, "steel", 1.2), slotM = M("slot", [0.01, 0.01, 0.01], 1, 0);
        const slotLights = M("slotlights", [0, 0, 0], 1, 0, null, null, [3, 1.2, 0.1]);
        this.saws = SAWS.map(([sx, sy], i) => {
            S(this.box(null, 1.25, 0.34, 0.012, coverM, sx, sy, 0));
            S(this.box(null, 1.12, 0.05, 0.004, slotM, sx, sy, 0.013));
            for (const side of [-1, 1]) S(this.box(null, 1.1, 0.025, 0.006, slotLights, sx, sy + side * 0.14, 0.014));
            const node = new BABYLON.TransformNode("saw" + i, this.scene);
            node.position = v3(sx, sy, -1.1);
            const spin = new BABYLON.TransformNode("sawspin" + i, this.scene);
            spin.parent = node;
            const R = 1.0, sawParts = [];
            sawParts.push(this.cyl(spin, R * 0.93, 0.012, "y", M("blade", [0.78, 0.8, 0.84], 1, 1, "steel", 2), 0, 0, 0, null, 48));
            sawParts.push(this.cyl(spin, R * 0.42, 0.016, "y", M("bladering", [0.45, 0.46, 0.5], 1, 1, "steel"), 0, 0, 0, null, 32));
            sawParts.push(this.cyl(spin, 0.16, 0.04, "y", M("bladehub", [0.2, 0.2, 0.22], 1, 1, "steel"), 0, 0, 0, null, 20));
            const teeth = M("teeth", [0.7, 0.72, 0.76], 1, 1, "steel", 3);
            for (let t = 0; t < 36; t++) {
                const a = t / 36 * Math.PI * 2;
                const tooth = this.box(spin, 0.06, 0.012, 0.05, teeth, Math.cos(a) * 0.98 * R, 0, Math.sin(a) * 0.98 * R);
                tooth.rotation.z = a;
                sawParts.push(tooth);
            }
            moving.push([spin, this.mergeParts(sawParts, spin)]);
            // (rw_gfx.build_saw) a see-through disc as it spins up (not on the line tiers), and the hot rim while it
            // grinds a robot
            const blur = this.cyl(node, R * 1.1, 0.011, "y", this.seeThrough("sawblur", [0.55, 0.57, 0.62], 0.22, 0.3, 1), 0, 0, 0, null, 64);
            const glow = BABYLON.MeshBuilder.CreateCylinder("sawglow", {height: 0.04, diameter: R * 2.08, tessellation: 64, cap: BABYLON.Mesh.NO_CAP}, this.scene);
            glow.material = M("sawglow", [0, 0, 0], 1, 0, null, null, [3.5, 1.2, 0.2]);
            glow.rotation.x = Math.PI / 2;
            glow.parent = node;
            glow.isVisible = false;
            const saw = {node, spin, angle: 0, blur, glow, glowLines: null};
            moving.push([glow, [glow], null, saw]);
            return saw;
        });
        // the wall spikes (west wall), unless there is no cage
        this.spikeBank = null;
        if (!noCage) {
            this.spikeBank = new BABYLON.TransformNode("spikes", this.scene);
            const bank = [this.box(this.spikeBank, 0.3, 2.6, 0.42, M("bank", [0.35, 0.36, 0.38], 1, 1, "steel"))];
            const spikeM = M("spike", [0.85, 0.85, 0.9], 1, 1, "steel");
            for (let y = -2.5; y <= 2.51; y += 0.5) for (const z of [-0.2, 0.2]) {
                const c = this.cyl(this.spikeBank, 0.09, 0.11, "x", spikeM, 0.41, y, z, 0, 12);
                c.rotation.z = -Math.PI / 2;  // (the tip along the game's +x)
                bank.push(c);
            }
            moving.push([this.spikeBank, this.mergeParts(bank, this.spikeBank)]);
            S(this.box(null, 0.02, 2.8, 0.45, hazard, -h + 0.01, 0, 0.55));
        }
        // the cage: kick plates in the wall colour, a rail, posts and glass screens; or, with no cage, a gutter
        // (ultra: the window's cage and posts, the screens as here; the line tiers: the screens' edges alone, black
        // faces would hide the robots from the cameras outside the cage)
        const edge = noCage ? GUTTER : 0.5, screens = [];
        if (!noCage) {
            const glass = this.glass("screen", [0.6, 0.75, 0.9], 0.1);
            for (const [cx, cy, hx, hy] of [[0, h + 0.25, h + 0.5, 0.25], [0, -h - 0.25, h + 0.5, 0.25], [h + 0.25, 0, 0.25, h], [-h - 0.25, 0, 0.25, h]]) {
                if (!ultra) S(this.box(null, hx, hy, 0.6, wall, cx, cy, 0.6));
                if (!ultra) S(this.box(null, hx + 0.03, hy + 0.03, 0.05, steel, cx, cy, 1.25));
                screens.push(this.box(null, hy === 0.25 ? hx : 0.02, hy === 0.25 ? 0.02 : hy, 1.6, glass, cx, cy, 2.9));
            }
            for (let k = -5; k <= 5 && !ultra; k++) {
                for (const [x, y] of [[k * 2, h + 0.25], [k * 2, -h - 0.25], [h + 0.25, k * 2], [-h - 0.25, k * 2]]) {
                    S(this.cyl(null, 0.07, 1.65, "z", steel, x, y, 2.9, null, 12));
                }
            }
        } else {
            const deep = 2.95;
            for (const [cx, cy, hx, hy] of [[0, h + 0.05, h + 0.1, 0.05], [0, -h - 0.05, h + 0.1, 0.05], [h + 0.05, 0, 0.05, h], [-h - 0.05, 0, 0.05, h]]) {
                S(this.box(null, hx, hy, deep / 2, wall, cx, cy, -deep / 2));
            }
            for (const [cx, cy, hx, hy] of [[0, h + GUTTER / 2, h + GUTTER, GUTTER / 2], [0, -h - GUTTER / 2, h + GUTTER, GUTTER / 2],
                                            [h + GUTTER / 2, 0, GUTTER / 2, h], [-h - GUTTER / 2, 0, GUTTER / 2, h]]) {
                S(this.box(null, hx, hy, 0.05, darkSteel, cx, cy, -deep - 0.05));
            }
            if (ultra) {  // (the gutter's outer side, as the window's: the venue's floor stops at the gutter)
                const g = GUTTER, out = M("outside", [1, 1, 1], 1, 0, "concrete", 0.3);
                for (const [cx, cy, hx, hy] of [[0, h + g, h + g, 0.02], [0, -h - g, h + g, 0.02], [h + g, 0, 0.02, h + g], [-h - g, 0, 0.02, h + g]]) {
                    S(this.box(null, hx, hy, deep / 2, out, cx, cy, -deep / 2));
                }
            }
        }
        // the corner towers with their lamps, and the lighting rig overhead
        const towerM = M("tower", [0.25, 0.26, 0.28], 1, 1, "steel"), lampM = M("lamp", [1, 1, 1], 0.3, 0, null, null, [6, 5.6, 5]);
        for (const sx of ultra ? [] : [-1, 1]) for (const sy of [-1, 1]) {
            const x = sx * 12.5, y = sy * 12.5;
            S(this.box(null, 0.25, 0.25, 4.3, towerM, x, y, 4.3));
            S(this.box(null, 0.5, 0.5, 0.35, towerM, x - sx * 0.3, y - sy * 0.3, 8.6));
            S(this.cyl(null, 0.32, 0.05, "z", lampM, x - sx * 0.62, y - sy * 0.62, 8.5, null, 20));
        }
        const rig = [];
        for (const k of ultra ? [] : [-1, 1]) {
            rig.push(this.box(null, 13, 0.15, 0.15, towerM, 0, k * 12.5, 9.2), this.box(null, 0.15, 13, 0.15, towerM, k * 12.5, 0, 9.2));
        }
        for (let i = -3; i <= 3 && !ultra; i++) {
            rig.push(this.box(null, 0.1, 12.5, 0.1, towerM, i * 3.2, 0, 9.3));
            for (const j of [-6, -2, 2, 6]) rig.push(this.box(null, 0.35, 0.2, 0.08, lampM, i * 3.2, j, 9.15));
        }
        this.rig = this.mergeStatic(rig);  // (hidden from the overview camera, which looks down past it)
        // outside: a concrete floor, tiered stands and a crowd
        const far = 30, concrete = M("outside", [1, 1, 1], 1, 0, "concrete", 0.3);
        for (const [cx, cy, hx, hy] of ultra ? [] : [[0, h + edge + far / 2, h + far, far / 2], [0, -h - edge - far / 2, h + far, far / 2],
                                                     [h + edge + far / 2, 0, far / 2, h + edge], [-h - edge - far / 2, 0, far / 2, h + edge]]) {
            S(this.box(null, hx, hy, 0.05, concrete, cx, cy, -0.05));
        }
        const standM = M("stands", [0.5, 0.55, 0.65], 1, 0, "concrete", 0.5);
        const crowdM = M("crowd", [0.45, 0.45, 0.45], 0.9, 0);
        const rnd = mulberry(3);
        const shirts = [[0.8, 0.1, 0.1], [0.1, 0.3, 0.8], [0.9, 0.8, 0.2], [0.2, 0.6, 0.3], [0.9, 0.9, 0.9], [0.15, 0.15, 0.18], [0.9, 0.5, 0.1], [0.5, 0.2, 0.6]];
        const skins = [[0.85, 0.65, 0.5], [0.6, 0.42, 0.3], [0.4, 0.28, 0.2]];
        const people = [];
        for (let side = 0; side < (ultra ? 0 : 4); side++) {
            for (let row = 0; row < 4; row++) {
                const d = h + 3.2 + row * 1.3, z = 0.35 + row * 0.55;
                if (look.crowd !== false && !blocks) {
                    for (let i = -12; i <= 12; i++) {
                        const along = i + (row % 2 ? 0.5 : 0);
                        const [x, y] = [[along, d], [along, -d], [d, along], [-d, along]][side];
                        if (rnd() >= 0.85) continue;
                        const tall = 0.22 + rnd() * 0.08;
                        people.push(this.tinted(this.box(null, 0.19, 0.13, tall, crowdM, x, y, z * 2 + tall), shirts[Math.floor(rnd() * shirts.length)]));
                        people.push(this.tinted(this.box(null, 0.08, 0.08, 0.09, crowdM, x, y, z * 2 + tall * 2 + 0.1), skins[Math.floor(rnd() * skins.length)]));
                    }
                }
                const [cx, cy, hx, hy] = [[0, d, h + 3, 0.65], [0, -d, h + 3, 0.65], [d, 0, 0.65, h + 3], [-d, 0, 0.65, h + 3]][side];
                S(this.box(null, hx, hy, z, standM, cx, cy, z));
            }
        }
        statics.push(...people);
        // the big screen with the arena's name (on ultra the window's screen; the line colour on the line tiers)
        if (!ultra) S(this.box(null, 4, 0.3, 1.4, M("screenbox", [0.1, 0.1, 0.12], 1, 1, "steel"), 0, h + 7.5, 6.5));
        const board = this.words(String(look.name || "ROBOT LAB"), 0.9, SCORE_GLOW, [0, h + 7.15, 6.6], [0, 0, 0]);
        if (this.wire) this.lettering(board);
        // the user mods
        if (mods.spike_pit) {
            const [kx, ky, ks] = SPIKE_PIT;
            S(this.box(null, ks / 2, ks / 2, 0.05, darkSteel, kx, ky, -0.55));
            const spikeM = M("pitspike", [0.85, 0.85, 0.9], 1, 1, "steel");
            for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) {
                S(this.cyl(null, 0.1, 0.15, "z", spikeM, kx - 1.0 + i * 0.4, ky - 1.0 + j * 0.4, -0.35, 0, 10));
            }
        }
        this.flames = [];
        if (mods.flame_pit) {
            S(this.box(null, 1.2, 1.2, 0.05, M("embers", [0, 0, 0], 1, 0, null, null, [1.6, 0.35, 0.04]), 0, 0, -0.55));
            const fire = M("fire", [0, 0, 0], 1, 0, null, null, [5, 1.3, 0.1]);
            for (let i = 0; i < 6; i++) {
                const a = i / 6 * Math.PI * 2;
                const c = BABYLON.MeshBuilder.CreateCylinder("flame", {height: 1, diameterBottom: 0.5, diameterTop: 0, tessellation: 8}, this.scene);
                c.material = fire;
                c.position = v3(Math.cos(a) * 0.6, Math.sin(a) * 0.6, -0.5);
                this.flames.push(c);
                moving.push([c, [c]]);
            }
        }
        this.boostMat = mods.boost_pad ? M("boost", [0.02, 0.05, 0.02], 0.5, 0, null, null, [0.2, 0.9, 0.3]) : null;
        this.boost = mods.boost_pad ? this.box(null, BOOST_PAD[2] / 2, BOOST_PAD[2] / 2, 0.008, this.boostMat, BOOST_PAD[0], BOOST_PAD[1], 0.008) : null;
        this.repairMat = mods.repair_bay ? M("repair", [0.02, 0.04, 0.08], 0.5, 0, null, null, [0.2, 0.5, 1.0]) : null;
        this.repair = mods.repair_bay ? this.box(null, REPAIR_BAY[2] / 2, REPAIR_BAY[2] / 2, 0.008, this.repairMat, REPAIR_BAY[0], REPAIR_BAY[1], 0.008) : null;
        if (this.boost) moving.push([null, [this.boost], "boost"]);
        if (this.repair) moving.push([null, [this.repair], "repair"]);
        if (mods.ramps) {  // (CHANGE 152: rw_gfx's ramps on every tier, ultra's too: the physics' wedge, its deck in
            // diamond plate, hazard stripes down its sides, a lit green speed-burst pad with white arrow bars up its slope)
            const deck = blocks ? M("ramp", [0.75, 0.75, 0.78], 1, 1) : M("ramp", [0.75, 0.75, 0.78], 1, 1, "diamond", 0.6);
            const body = M("rampbody", [0.3, 0.3, 0.32], 1, 1, "steel", 0.5);
            const pad = M("ramppad", [0.02, 0.05, 0.02], 0.5, 0, null, null, [0.2, 0.9, 0.3]);
            const bars = M("rampbars", [0.1, 0.1, 0.1], 0.5, 0, null, null, [1.5, 1.5, 1.6]);
            const [L, W, H] = RAMP;
            for (const [cx, cy, d] of RAMPS) {
                const xb = cx - d * L / 2, xt = cx + d * L / 2, y0 = cy - W / 2, y1 = cy + W / 2;
                const nl = Math.hypot(H, L), n = [-d * H / nl, 0, L / nl];  // (the slope's normal)
                const on = (t, y, lift = 0) => [xb + d * t * L + n[0] * lift, y, t * H + n[2] * lift];  // (t: from the bottom to the top)
                const sl = (t0, t1, ya, yb, lift) => [[on(t0, ya, lift), on(t0, yb, lift), on(t1, yb, lift), on(t1, ya, lift)], n];
                S(this.polyMesh([sl(0, 1, y0, y1, 0)], deck));
                S(this.polyMesh([[[[xt, y0, 0], [xt, y1, 0], [xt, y1, H], [xt, y0, H]], [d, 0, 0]],
                                 [[[xb, y0, 0], [xt, y0, 0], [xt, y0, H]], [0, -1, 0]], [[[xb, y1, 0], [xt, y1, 0], [xt, y1, H]], [0, 1, 0]]], body));
                S(this.polyMesh([sl(0, 1, y0, y0 + 0.15, 0.006), sl(0, 1, y1 - 0.15, y1, 0.006)], hazard));
                const pw = W * 0.3;
                S(this.polyMesh([sl(0.2, 0.8, cy - pw, cy + pw, 0.008)], pad));
                S(this.polyMesh([0.35, 0.5, 0.65].map(t => sl(t - 0.03, t + 0.03, cy - pw * 0.7, cy + pw * 0.7, 0.014)), bars));
            }
        }
        this.lasers = [];
        const still = this.mergeStatic(statics);
        this.shadowCast([...ffParts, ...lidParts]);
        if (this.spikeBank) this.spikeBank.position = v3(-10.5, 0, 0.45);
        this.ultraParts = null;
        if (ultra) {  // (the window's arena: its rig and roof hidden with the rig by the full arena view)
            const u = this.ultraParts = makeUltraArena(this, file, mods, look);
            this.rig.push(...u.rig);
            this.shadowCast(u.casters);
        }
        if (this.wire) this.arenaLines(still, rects, screens, moving);
    }

    lineFade() {  // (where the lines fade out, as the window's dark fog: rw_gfx.LOOK_FADE, CHANGE 145)
        return this.wire === "all" ? [16, 60] : [24, 90];
    }

    // (the line tiers, CHANGE 145: rw_gfx.ArenaVisual.looks) the still parts' edges as lines in tiles, with on lines a
    // grid every 2 m (the floor plates' size) on the floor's own rectangles, none over the holes; the cage's screens as
    // their edges alone; each moving part's lines under it (the pit's lid, the flipper, the spikes, each saw, the
    // flames); the glowing parts' lines their own material, pulsed in frame() as they glow; the rig's hidden with it
    arenaLines(still, rects, screens, moving) {
        const t0 = performance.now(), before = this.lineCount || 0, fade = this.lineFade(), fill = this.wireFill();
        const mat = this.lineMaterial("arena", 1, ...fade);
        const lists = this.edgeLines(still.filter(m => m.material === fill), this.wire), edges = lists.idx.length / 2;
        if (this.wire === "outline") {
            const z = 0.002;  // (line_look.grid: each line cut at the rectangles' edges, not along them)
            for (const [x0, y0, x1, y1] of rects) {
                for (let x = Math.ceil(x0 / 2 - 1e-9) * 2; x < x1 - 1e-6; x += 2) {
                    if (x <= x0 + 1e-6) continue;
                    const b = lists.pos.length / 3;
                    lists.pos.push(x, z, y0, x, z, y1);
                    lists.idx.push(b, b + 1);
                }
                for (let y = Math.ceil(y0 / 2 - 1e-9) * 2; y < y1 - 1e-6; y += 2) {
                    if (y <= y0 + 1e-6) continue;
                    const b = lists.pos.length / 3;
                    lists.pos.push(x0, z, y, x1, z, y);
                    lists.idx.push(b, b + 1);
                }
            }
        }
        const grid = lists.idx.length / 2 - edges;
        this.staticLines("arenalines", lists, mat);
        if (screens.length) {
            this.staticLines("screenlines", this.edgeLines(screens, this.wire), mat);
            for (const m of screens) m.dispose();
        }
        const rigLines = this.rig.length ? this.linesMesh("riglines", this.edgeLines(this.rig, this.wire), mat) : null;
        if (rigLines) this.rig.push(rigLines);
        for (const [node, meshes, glow, saw] of moving) {
            const m = glow ? (this.glowLines[glow] = this.glowLines[glow] || this.lineMaterial(glow, 1, ...fade)) : mat;
            const lines = this.linesMesh(glow ? glow + "lines" : "movinglines", this.edgeLines(meshes, this.wire, node), m, node);
            if (saw) { saw.glowLines = lines; if (lines) lines.isVisible = false; }
        }
        this.lineStats = {segments: (this.lineCount || 0) - before, grid, ms: Math.round(performance.now() - t0)};
    }

    // (CHANGE 152) words as the window's TextNode writes them (centred on its pen's travel, the baseline at pos, in Panda's
    // own letters: fightfx.js's drawWords; scale metres a unit; turned by the window's hpr, degrees) and in the colour
    // the window shows them in on this tier (look: NAME_PAINT and the rest), unlit as the window's are; the line colour
    // on the line tiers. Until the letters are loaded, the browser's sans, and the scene made again once they are
    words(text, scale, look, pos, hpr, parent = null) {
        const size = wordsSize(text) || {width: 0.6 * String(text).length, lo: -0.2, hi: 0.75};
        const ppu = 128, pad = 0.1, w = size.width + 2 * pad, lo = size.lo - pad, hi = size.hi + pad;
        const cw = Math.max(8, Math.ceil(w * ppu)), ch = Math.max(8, Math.ceil((hi - lo) * ppu));
        const plane = BABYLON.MeshBuilder.CreatePlane("words", {width: w * scale, height: (hi - lo) * scale}, this.scene);
        plane.bakeTransformIntoVertices(BABYLON.Matrix.Translation(0, (hi + lo) / 2 * scale, 0));  // (its middle on the baseline)
        plane.ccOwnUV = true;
        const tex = new BABYLON.DynamicTexture("wordstex", {width: cw, height: ch}, this.scene, true);
        tex.hasAlpha = true;
        const ctx = tex.getContext();
        ctx.clearRect(0, 0, cw, ch);
        if (!drawWords(ctx, text, cw / 2, hi * ppu, ppu, "#ffffff")) {
            ctx.fillStyle = "#ffffff";
            ctx.textAlign = "center";
            ctx.font = `${Math.round(0.7 * ppu)}px sans-serif`;
            ctx.fillText(String(text), cw / 2, hi * ppu);
            if (!this.fontWait) { const scene = this.scene; this.fontWait = loadPandaFont().then(f => { if (f && this.scene === scene) this.build(); }); }
        }
        tex.update();
        const m = new BABYLON.StandardMaterial("wordsmat", this.scene);
        m.diffuseTexture = tex;
        m.useAlphaFromDiffuseTexture = true;
        m.specularColor = new BABYLON.Color3(0, 0, 0);
        m.disableLighting = true;
        const c = look[this.tier === "blocks" ? "blocks" : this.tier === "low" ? "low" : "lit"];
        m.emissiveColor = this.wire ? new BABYLON.Color3(1, 1, 1) : new BABYLON.Color3(c[0] / 255, c[1] / 255, c[2] / 255);
        m.backFaceCulling = true;  // (a TextNode is one-sided)
        plane.material = m;
        plane.isPickable = false;
        if (parent) plane.parent = parent;
        plane.position = v3(...pos);
        plane.rotation.set(-hpr[1] * Math.PI / 180, -hpr[0] * Math.PI / 180, -hpr[2] * Math.PI / 180);
        return plane;
    }

    // (CHANGE 152) flat convex polygons as one mesh (engine/rw_mesh.py's Mesh.poly): polys [[points, normal], ...] in
    // game coordinates, each facing along its normal (its texture coordinates are base3d's metres)
    polyMesh(polys, mat, name = "poly") {
        const pos = [], nor = [], uv = [], idx = [];
        for (const [pts, n] of polys) {
            const p = pts.map(q => v3(...q)), nb = v3(...n), b = pos.length / 3;
            // (a front face of Babylon's own boxes turns so that (b - a) x (c - a) points away from its normal)
            const face = BABYLON.Vector3.Cross(p[1].subtract(p[0]), p[2].subtract(p[0]));
            const order = BABYLON.Vector3.Dot(face, nb) > 0 ? p.map((_, i) => i).reverse() : p.map((_, i) => i);
            for (const i of order) { pos.push(p[i].x, p[i].y, p[i].z); nor.push(nb.x, nb.y, nb.z); uv.push(0, 0); }
            for (let k = 1; k < p.length - 1; k++) idx.push(b, b + k, b + k + 1);
        }
        const mesh = new BABYLON.Mesh(name, this.scene);
        const vd = new BABYLON.VertexData();
        vd.positions = pos;
        vd.normals = nor;
        vd.uvs = uv;
        vd.indices = idx;
        vd.applyToMesh(mesh);
        mesh.material = mat;
        return mesh;
    }

    // a box in its own colour (a person in the crowd): vertex colours, so a whole crowd is one mesh
    tinted(mesh, rgb) {
        const n = mesh.getTotalVertices(), c = new Array(n * 4);
        for (let i = 0; i < n; i++) { c[i * 4] = rgb[0]; c[i * 4 + 1] = rgb[1]; c[i * 4 + 2] = rgb[2]; c[i * 4 + 3] = 1; }
        mesh.setVerticesData(BABYLON.VertexBuffer.ColorKind, c);
        return mesh;
    }

    // a see-through material (a spinning blade's blur, a laser's glow), as the app's parts give it: its colour,
    // alpha, roughness, metal and glow; not writing depth
    seeThrough(name, rgb, alpha, rough, metal, emission = null) {
        const key = `see:${name}`;
        if (this.materials[key]) return this.materials[key];
        let m;
        if (this.lighting) {
            m = this.lighting.material(key, {rgb, rough, metal, alpha, emission});
        } else {
            m = new BABYLON.StandardMaterial(key, this.scene);
            m.diffuseColor = col(rgb);
            m.specularColor = new BABYLON.Color3(0, 0, 0);
            if (emission) m.emissiveColor = col(emission.map(c => Math.min(1, c)));
            m.alpha = alpha;
            m.backFaceCulling = false;
        }
        m.disableDepthWrite = true;
        this.materials[key] = m;
        return m;
    }

    // a laser's beam, 1 m long along its node's z (aimed and stretched each frame): a white-hot core inside a red
    // glow (rw_gfx.build_laser)
    // (the line tiers, CHANGE 145: a solid beam in the line colour, no glow)
    buildLaser() {
        const aim = new BABYLON.TransformNode("laser", this.scene);
        this.cyl(aim, 0.02, 0.5, "y", this.wire ? this.lineInk("laser") : this.material("lasercore", [0, 0, 0], 1, 0, 0, {emission: [10, 4, 3]}), 0, 0.5, 0, null, 8);
        if (!this.wire) this.cyl(aim, 0.06, 0.5, "y", this.seeThrough("laserglow", [0, 0, 0], 0.5, 1, 0, [8, 0.3, 0.2]), 0, 0.5, 0, null, 10);
        aim.setEnabled(false);
        return aim;
    }

    // ---------- the robots ----------
    // a material that remembers how it was made, so a part can be darkened or flashed (rw_gfx's colour scales)
    paintOf(name, rgb, rough, metal, opts) {
        const m = this.material(name, rgb, rough, metal, 0, opts);
        if (!m.ccArgs) m.ccArgs = {name, rgb, rough, metal, opts};
        return m;
    }

    // Panda's colour scale k (linear, per channel) on a group of parts: their colours times k (the screen colour
    // times k^(1/2.2)); a glow isn't scaled, as simplepbr doesn't scale it. Steps of 0.05, so few materials are made.
    // (ultra's robots, CHANGE 145: their material's own maker, a.make)
    tint(v, group, k) {
        const q = k.map(c => Math.round(c * 20) / 20), key = q.join(",");
        if (v.tints[group] === key) return;
        v.tints[group] = key;
        const one = q.every(c => c === 1);
        for (const mesh of v.groups[group]) {
            const base = mesh.ccBase, a = base && base.ccArgs;
            if (!a) continue;
            mesh.material = one ? base : a.make ? a.make(q) : this.material(a.name, a.rgb.map((c, i) => c * Math.pow(q[i], 1 / 2.2)), a.rough, a.metal, 0, a.opts);
        }
    }

    setRobots(list) {
        // (ids are given out again on every rebuild of the arena: a robot is made again when its id, design or owner
        // is new. The roster comes again whenever a window's report changes, about once a second: a robot that is
        // the same keeps its model, and what real damage has done to it)
        const keep = new Map();
        for (const r of list) {
            const v = this.robots.get(r.id), key = JSON.stringify([r.design || {}, r.owner || ""]);
            if (v && v.key === key) keep.set(r.id, v);
        }
        for (const [id, v] of this.robots) if (keep.get(id) !== v) this.disposeRobot(v);
        this.robots = keep;
        this.designs = list;
        for (const r of list) if (!keep.has(r.id)) this.addRobot(r);
    }

    disposeRobot(v) {
        for (const f of v.flying) if (!f.node.parent) f.node.dispose();  // (parts that came off lie in the world)
        for (const b of Object.values(v.bars)) b.dispose();
        v.label.dispose(false, true);
        if (v.deckName) v.deckName.dispose(false, true);  // (its own writing)
        v.root.dispose();
        v.weapon.dispose();
        if (v.rear) v.rear.dispose();
    }

    addRobot(info) {
        const d = info.design || {}, scene = this.scene, s = designSize(d);
        const big = !!(d.house || d.model);
        const weaponType = d.weapon || HOUSE_WEAPONS[d.model] || "wedge";
        const colour = rgb255(d.colour, [200, 120, 40]);
        const style = d.style || {};
        const trim = rgb255(style.trim, [30, 30, 34]), lights = rgb255(style.lights, [255, 60, 30]).map(v => v * 6);
        const blocks = this.tier === "blocks";
        if (this.ultra && robotModelsData()) return this.addUltraRobot(info, d, s, big, weaponType, colour, trim, lights, style);
        // rw_gfx.RobotVisual's looks: the paint and steel texture sets (their maps give the shine), tread on the tyres
        const T = (name, rgb, tex, tile = 1, rough = 1, metal = 1) => this.paintOf(name, rgb, rough, metal, {tex, tile});
        const paint = T("hull", colour, "paint", 1.2);
        const trimM = T("trim", trim, "paint", 1.2);
        const steel = T("steel", [1, 1, 1], "steel");
        const bar = T("bar", [0.7, 0.72, 0.76], "steel", 1.5);
        const hazardM = blocks ? this.paintOf("yellow", YELLOW, 0.6, 0, {}) : T("hazard", [1, 1, 1], "hazard", 0.8, 1, 0);
        const glow = this.material("eyes", [0, 0, 0], 0.3, 0, 0, {emission: lights});
        const hx = 0.6 * s, hy = 0.8 * s, hzz = 0.18 * s, z0 = 0.1, top = z0 + hzz;
        const root = new BABYLON.TransformNode("robot" + info.id, scene);
        root.rotationQuaternion = BABYLON.Quaternion.Identity();
        // the parts in their groups (rw_gfx: the chassis, its armour, the weapon, each wheel), each darkened or
        // flashed as a group; real damage bends and throws the armour panels and wheels
        const groups = {chassis: [], armour: [], weapon: [], wheel0: [], wheel1: [], wheel2: [], wheel3: []};
        const all = [];
        const G = (group, mesh) => { mesh.ccBase = mesh.material; groups[group].push(mesh); all.push(mesh); return mesh; };
        G("chassis", this.box(root, hx, hy, hzz, paint, 0, 0, z0));
        // armour: bolted-on panels, each on a hinge edge, so under real damage they bend, rattle and come off
        const armour = new BABYLON.TransformNode("armour", scene);
        armour.parent = root;
        const panels = [];
        const panel = (hinge, bend, lie) => {
            const node = new BABYLON.TransformNode("panel", scene);
            node.parent = armour;
            node.position = v3(...hinge);
            node.rotationQuaternion = BABYLON.Quaternion.Identity();
            panels.push({node, hinge, bend, lie});
            return node;
        };
        const deck = panel([0, -hy * 0.8, top + 0.04], [0, 28, 0], [0, 0]);  // hinged at its back edge: the front lifts
        G("armour", this.box(deck, 0.78 * hx, 0.72 * hy, 0.045, trimM, 0, 0.72 * hy, 0));
        const rivets = [];
        for (let i = 0; i < 8; i++) for (const sd of [-1, 1]) rivets.push(this.cyl(deck, 0.018, 0.008, "z", steel, sd * hx * 0.72, hy * 0.18 + i * hy * 0.16, 0.05, null, 8));
        const skirtM = T("skirt", [0.35, 0.36, 0.38], "steel", 1.5);
        const hingeZ = z0 - 0.02 + hzz * 0.7;
        for (const sd of [-1, 1]) {  // side skirts, hinged at the top
            const skirt = panel([sd * (hx + 0.02), 0, hingeZ], [0, 0, sd * 34], [0, sd * 90]);
            G("armour", this.box(skirt, 0.03, 0.9 * hy, 0.7 * hzz, skirtM, 0, 0, -0.7 * hzz));
            if (big) G("armour", this.box(skirt, 0.02, 0.8 * hy, 0.45 * hzz, hazardM, sd * 0.025, 0, z0 + hzz * 0.2 - hingeZ));  // warning stripes
        }
        const rear = panel([0, -hy - 0.018, top - 0.03], [0, -34, 0], [-90, 0]);  // the back plate, with the rear light bar
        G("armour", this.box(rear, 0.72 * hx, 0.012, 0.55 * hzz, T("back", [0.3, 0.3, 0.33], "steel", 1.5), 0, 0, -0.55 * hzz));
        all.push(this.box(rear, 0.6 * hx, 0.012, 0.02, this.material("taillight", [0, 0, 0], 0.3, 0, 0, {emission: [4, 0.2, 0.1]}), 0, -0.01, z0 + hzz * 0.3 - (top - 0.03)));
        // glowing eyes at the front, an antenna with a tip light
        all.push(this.box(root, 0.5 * hx, 0.012, 0.025, glow, 0, hy + 0.005, z0 + 0.45 * hzz));
        G("chassis", this.cyl(root, 0.008, 0.18, "z", steel, -0.6 * hx, -0.7 * hy, top + 0.24, null, 6));
        all.push(this.cyl(root, 0.022, 0.022, "z", glow, -0.6 * hx, -0.7 * hy, top + 0.43, null, 10));
        let beacon = null;
        if (big) {  // Resident Robots: grab handles, armour plates on the deck, a flashing beacon
            for (const sd of [-1, 1]) G("chassis", this.box(root, 0.03, 0.03, 0.12, T("handle", [0.3, 0.3, 0.32], "steel"), sd * hx * 0.5, -hy - 0.04, top - 0.05));
            for (let i = 0; i < 3; i++) G("armour", this.box(deck, hx * 0.36, hy * 0.2, 0.03, T("plate", [0.4, 0.4, 0.42], "steel"), 0, hy * 0.35 + i * hy * 0.45, 0.06));
            G("chassis", this.cyl(root, 0.1, 0.05, "z", T("beaconbase", [0.2, 0.2, 0.22], "steel"), 0.55 * hx, -0.55 * hy, top + 0.14, null, 16));
            this.beaconMat = this.material("beacon", [0, 0, 0], 0.3, 0, 0, {emission: [6, 3, 0]});
            all.push(beacon = this.cyl(root, 0.08, 0.07, "z", this.beaconMat, 0.55 * hx, -0.55 * hy, top + 0.26, null, 16));
        }
        for (const m of this.mergeParts(rivets, deck)) G("armour", m);
        const wr = big ? 0.32 : 0.2, ww = big ? 0.12 : 0.075;
        const tyreM = blocks ? this.paintOf("tyre", [0.07, 0.07, 0.08], 1, 0, {}) : T("tyre", [1, 1, 1], "tyre", 2.5, 1, 0);
        const wheels = WHEELS.map(([x, y], i) => {
            const lean = new BABYLON.TransformNode("wheel", scene);  // (leans and wobbles when it's failing)
            lean.parent = root;
            lean.position = v3(x * s, y * s, 0.08);
            lean.rotationQuaternion = BABYLON.Quaternion.Identity();
            const spin = new BABYLON.TransformNode("wheelspin", scene);
            spin.parent = lean;
            G("wheel" + i, this.cyl(spin, wr, ww, "x", tyreM, 0, 0, 0, null, 20));
            G("wheel" + i, this.cyl(spin, wr * 0.55, ww + 0.005, "x", T("hub", [0.7, 0.7, 0.72], "steel"), 0, 0, 0, null, 14));
            return {lean, spin, x: x * s, y: y * s};
        });
        // the weapon: a node placed in the world from the snapshot (its origin is the hinge), the shapes around it
        const weapon = new BABYLON.TransformNode("weapon" + info.id, scene);
        weapon.rotationQuaternion = BABYLON.Quaternion.Identity();
        const spin = new BABYLON.TransformNode("wspin", scene);
        spin.parent = weapon;
        const W = m => G("weapon", m);
        let blur = null, chain = null, chainBase = 0;
        if (weaponType === "wedge") {
            this.wedge(weapon, hx, trimM, hazardM, trim).forEach(W);
        } else if (weaponType === "spinner") {
            W(this.box(spin, 0.8 * s, 0.08, 0.05, bar));
            for (const sd of [-1, 1]) W(this.box(spin, 0.09, 0.1, 0.07, steel, sd * (0.8 * s - 0.07), 0, 0));
            W(this.cyl(spin, 0.11, 0.06, "z", trimM));
            blur = this.cyl(weapon, 0.8 * s, 0.004, "z", this.seeThrough("spinblur", [0.8, 0.82, 0.86], 0.28, 0.2, 1), 0, 0, 0, null, 48);
        } else if (weaponType === "drum") {
            W(this.cyl(spin, 0.2 * s, 0.8 * hx, "x", T("drum", [0.6, 0.62, 0.66], "steel", 2), 0, 0, 0, null, 20));
            for (let t = 0; t < 6; t++) {
                const a = t / 6 * Math.PI * 2;
                W(this.box(spin, 0.6 * hx, 0.04, 0.04, steel, 0, Math.cos(a) * 0.22 * s, Math.sin(a) * 0.22 * s));
            }
        } else if (weaponType === "vdisc") {
            const r = 0.42 * s;
            W(this.cyl(spin, r, 0.035 * s, "x", bar, 0, 0, 0, null, 32));
            for (let t = 0; t < 8; t++) {
                const a = t / 8 * Math.PI * 2;
                W(this.box(spin, 0.03 * s, 0.06, 0.06, steel, 0, Math.cos(a) * 1.07 * r, Math.sin(a) * 1.07 * r));
            }
            W(this.cyl(spin, 0.45 * r, 0.05 * s, "x", trimM, 0, 0, 0, null, 12));
            blur = this.cyl(weapon, 1.12 * r, 0.004, "x", this.seeThrough("spinblur", [0.8, 0.82, 0.86], 0.28, 0.2, 1), 0, 0, 0, null, 48);
        } else if (weaponType === "flame") {  // a nozzle with a pilot light, fed by two fuel tanks
            W(this.cyl(weapon, 0.07 * s, 0.22 * s, "y", steel, 0, 0.22 * s, 0, null, 10));
            W(this.cyl(weapon, 0.1 * s, 0.04 * s, "y", trimM, 0, 0.44 * s, 0, null, 10));
            all.push(this.cyl(weapon, 0.025, 0.02, "z", this.material("pilot", [0, 0, 0], 0.3, 0, 0, {emission: [1, 0.5, 2.5]}), 0, 0.44 * s + 0.03, -0.07 * s - 0.02, null, 8));
            for (const sd of [-1, 1]) G("chassis", this.cyl(root, 0.08 * s, 0.25 * s, "y", T("tank", [0.75, 0.1, 0.08], "paint"), sd * 0.45 * hx, -0.2 * hy, top + 0.1));
        } else if (weaponType === "laser") {
            W(this.box(weapon, 0.06 * s, 0.18 * s, 0.05 * s, steel, 0, 0.18 * s, 0));
            all.push(this.sphere(weapon, 0.04 * s, this.material("lens", [0, 0, 0], 0.3, 0, 0, {emission: [8, 1.5, 1]}), 0, 0.36 * s + 0.05, 0));
        } else if (weaponType === "chainsaw") {  // an arm that lowers a chainsaw bar; the chain runs round the bar
            const ay = 0.3 * s, b = [0.025 * s, 0.42 * s, 0.07 * s];
            W(this.box(weapon, 0.06 * s, ay, 0.05 * s, paint, 0, ay, 0));
            W(this.box(weapon, 0.06 * s * 2.2, 0.16, 0.05 * s * 2.2, T("housing", [0.2, 0.2, 0.22], "steel"), 0, ay * 2 - 0.08, -0.02));
            chainBase = ay * 2 + b[1] - 0.05;
            W(this.box(weapon, b[0], b[1], b[2], T("chainbar", [0.75, 0.76, 0.8], "steel"), 0, chainBase, -0.04));
            chain = new BABYLON.TransformNode("chain", scene);
            chain.parent = weapon;
            chain.position = v3(0, chainBase, -0.04);
            const links = [], linkM = T("chain", [0.35, 0.35, 0.37], "steel");
            for (let y = -b[1]; y < b[1] - b[2]; y += 0.06) {
                for (const zz of [-b[2] - 0.012, b[2] + 0.012]) links.push(this.box(chain, b[0] + 0.008, 0.02, 0.014, linkM, 0, y, zz));
            }
            this.mergeParts(links, chain).forEach(W);
        } else {  // hammer
            const m = Math.min(s, 1.3), L = Math.min(0.85 * s, 1.3);
            W(this.box(weapon, 0.05 * m, L, 0.05 * m, T("arm", [0.4, 0.4, 0.42], "steel"), 0, L, 0));
            W(this.box(weapon, 0.22 * s, 0.14 * s, 0.14 * s, T("head", [0.2, 0.2, 0.22], "steel"), 0, 2 * L, 0));
            W(this.cyl(weapon, 0.08, 0.15, "x", steel, 0, 0, 0, null, 10));
        }
        this.shadowCast(all);
        // its name (or number) painted on the deck, as rw_gfx does (not on the line tiers: CHANGE 145)
        const painted = this.wire ? "" : deckNumber(d).slice(0, 10).toUpperCase();
        let deckName = null;
        if (painted) {  // (where the window paints it, its size: a standard robot's, made k times bigger with the robot)
            const kk = robotShapes(weaponType, s, big).k;
            deckName = this.words(painted, Math.min(0.2, 1.2 * hx / kk / Math.max(3, painted.length)) * kk, DECK_PAINT,
                                  [0, 0.68 * hy, 0.048 * kk], [0, -90, 0], deck);
        }
        const owner = info.owner || "";
        const house = owner === "Resident Robot";
        const label = this.makeLabel(house ? `${d.name || ""}\nResident Robot` : owner || d.name || "", house ? "#ffbf4d" : "#ffffff", 1.1, false);
        const vis = {key: JSON.stringify([info.design || {}, owner]), deckName, root, armour, panels, weapon, spin, blur, chain, chainBase, chainPos: 0, wheels, wr, ww, label, design: d, owner, weaponType, s, top,
                     angle: 0, roll: 0, hp: null, flash: 0, groups, tints: {}, trimM, hazardM, trim, hx, rear: null, beacon,
                     health: {}, weak: {}, gone: new Set(), flying: [], bars: {}, barUntil: {}, scorch: 0, fresh: true};
        if (this.wire) this.robotLines(vis);
        this.robots.set(info.id, vis);
        return vis;
    }

    // (the line tiers, CHANGE 145: rw_gfx.RobotVisual.looks) the robot's edges as lines, each part that moves on its
    // own with its own: every armour panel, the beacon (pulsing as it flashes), the body with what is fixed to it, the
    // chainsaw's chain, the weapon (a spinning weapon's turning part apart), each wheel (worked out once a wheel size,
    // for every robot). The see-through blur isn't drawn, nor the name on the deck (the label above says who it is)
    robotLines(v) {
        const mode = this.wire, fade = this.lineFade(), mat = this.lineMaterial("robot", 1, ...fade);
        const own = (node, meshes, m = mat) => this.linesMesh("robotlines", this.edgeLines(meshes, mode, node), m, node);
        for (const pn of v.panels) own(pn.node, pn.node.getChildMeshes(false));
        own(v.root, v.root.getChildMeshes(true).filter(m => m !== v.beacon));
        if (v.beacon) own(v.beacon, [v.beacon], this.glowLines.beacon = this.glowLines.beacon || this.lineMaterial("beacon", 1, ...fade));
        if (v.blur) { v.blur.dispose(); v.blur = null; }
        if (v.chain) own(v.chain, v.chain.getChildMeshes(false));
        own(v.weapon, v.weapon.getChildMeshes(true));
        own(v.spin, v.spin.getChildMeshes(false));
        for (const w of v.wheels) {
            const key = `${mode}:${v.wr}:${v.ww}`;
            if (!this.wheelLines[key]) this.wheelLines[key] = this.edgeLines(w.spin.getChildMeshes(false), mode, w.spin);
            this.linesMesh("wheellines", this.wheelLines[key], mat, w.spin);
        }
    }

    // (ultra, CHANGE 145: rw_gfx.RobotVisual.ultra) the window's smooth robot from models/robot_ultra.json: its pieces
    // placed by robotLayout (robot_models.layout) on the nodes the other tiers use (the body, the armour panels on their
    // hinges, a Resident Robot's beacon, the weapon and its spin, a chainsaw's chain, each wheel), each node's pieces ONE
    // mesh in the robot's colours (a texel a role for roughness, metal and glow, as the window's atlas: about 11 draws a
    // robot, its shadow's too), and the whole robot k times the standard robot it is drawn as (lab_sim.shapes)
    addUltraRobot(info, d, s, big, weaponType, colour, trim, lights, style) {
        const scene = this.scene, sh = robotShapes(weaponType, s, big), k = sh.k, size = sh.size;
        const [hx, hy, hz] = sh.half, z0 = 0.1, top = z0 + hz;
        const node = (name, parent, pos = null, scale = 1) => {
            const n = new BABYLON.TransformNode(name, scene);
            n.parent = parent;
            if (pos) n.position = v3(...pos);
            if (scale !== 1) n.scaling.setAll(scale);
            return n;
        };
        const root = new BABYLON.TransformNode("robot" + info.id, scene);
        root.rotationQuaternion = BABYLON.Quaternion.Identity();
        const body = node("body", root, null, k), armour = node("armour", body), panels = [];
        const panel = (hinge, bend, lie) => {
            const n = node("panel", armour, hinge);
            n.rotationQuaternion = BABYLON.Quaternion.Identity();
            panels.push({node: n, hinge, bend, lie});
            return n;
        };
        const hingeZ = z0 - 0.02 + hz * 0.7;
        const nodes = {chassis: body, deck: panel([0, -hy * 0.8, top + 0.04], [0, 28, 0], [0, 0]),
                       skirt_r: panel([hx + 0.02, 0, hingeZ], [0, 0, 34], [0, 90]), skirt_l: panel([-(hx + 0.02), 0, hingeZ], [0, 0, -34], [0, -90]),
                       rear: panel([0, -hy - 0.018, top - 0.03], [0, -34, 0], [-90, 0])};
        if (big) nodes.beacon = node("beacon", body, [hx * 0.55, -hy * 0.55, top + 0.26]);
        const wr = (big ? 0.32 : 0.2) * k, ww = (big ? 0.12 : 0.075) * k;
        const wheels = WHEELS.map(([x, y], i) => {  // (where the other tiers put them; k times the standard wheel)
            const lean = node("wheel", root, [x * s, y * s, 0.08], k);
            lean.rotationQuaternion = BABYLON.Quaternion.Identity();
            nodes["wheel" + i] = node("wheelspin", lean);
            return {lean, spin: nodes["wheel" + i], x: x * s, y: y * s};
        });
        const weapon = new BABYLON.TransformNode("weapon" + info.id, scene);
        weapon.rotationQuaternion = BABYLON.Quaternion.Identity();
        const spin = node("wspin", weapon);
        nodes.weapon = node("pieces", spin, null, k);
        let chain = null, chainBase = 0, blur = null;
        if (weaponType === "chainsaw") {
            chainBase = sh.arm[1] * 2 + sh.bar[1] - 0.05;
            chain = nodes.chain = node("chain", nodes.weapon, [0, chainBase, -0.04]);
        } else if (weaponType === "spinner" || weaponType === "vdisc") {  // (the see-through disc, as the other tiers')
            const see = this.seeThrough("spinblur", [0.8, 0.82, 0.86], 0.28, 0.2, 1);
            blur = weaponType === "spinner" ? this.cyl(weapon, 0.8 * s, 0.004, "z", see, 0, 0, 0, null, 48)
                : this.cyl(weapon, 1.12 * 0.42 * s, 0.004, "x", see, 0, 0, 0, null, 48);
        }
        const byNode = {};
        for (const [n, piece, pos, hpr, scale] of robotLayout(weaponType, size, big, sh)) (byNode[n] = byNode[n] || []).push([piece, pos, hpr, scale]);
        const groups = {chassis: [], armour: [], weapon: [], wheel0: [], wheel1: [], wheel2: [], wheel3: []}, all = [];
        const groupOf = n => (["deck", "skirt_r", "skirt_l", "rear"].includes(n) ? "armour" : n === "chain" ? "weapon" : n);
        const base = this.ultraRobotMaterial(lights, [1, 1, 1]);
        let beacon = null;
        for (const [n, items] of Object.entries(byNode)) {
            const mesh = nodes[n] ? robotNodeMesh(this, "robot " + n, items, colour, trim) : null;
            if (!mesh) continue;
            mesh.parent = nodes[n];
            all.push(mesh);
            if (n === "beacon") {  // (flashed in frame(): its own material, as the window's)
                mesh.material = this.beaconMat = this.material("beacon", [0, 0, 0], 0.3, 0, 0, {emission: [6, 3, 0]});
                beacon = mesh;
                continue;
            }
            mesh.material = mesh.ccBase = base;
            groups[groupOf(n)].push(mesh);
        }
        // (CHANGE 152, as the window's) the sun's shadow map draws each node's coarser shadow (the file's "shadow": no
        // bolts or lamps, plain tyres), never the robot (layerMask 0: no camera draws them); and while the armour and
        // wheels are whole, the body and its panels are ONE mesh, and their shadow and the tyres' one more (combine)
        const ARMOUR = ["chassis", "deck", "skirt_r", "skirt_l", "rear"], apart = [], shadowsApart = [], casters = [];
        const caster = (mesh, parent) => {
            mesh.parent = parent;
            mesh.material = base;
            mesh.layerMask = 0;
            casters.push(mesh);
            return mesh;
        };
        for (const [n, items] of Object.entries(byNode)) {
            const m = nodes[n] ? robotNodeMesh(this, "robot shadow " + n, items, colour, trim, true) : null;
            if (!m) continue;
            caster(m, nodes[n]);
            if (ARMOUR.includes(n) || n.startsWith("wheel")) shadowsApart.push(m);
        }
        const hingeOf = n => (n === "chassis" ? [0, 0, 0] : panels[["deck", "skirt_r", "skirt_l", "rear"].indexOf(n)].hinge);
        const inBody = ARMOUR.flatMap(n => (byNode[n] || []).map(([piece, pos, hpr, scale]) => [piece, pos.map((c, i) => c + hingeOf(n)[i]), hpr, scale]));
        const tyres = WHEELS.flatMap(([x, y], i) => (byNode["wheel" + i] || []).map(([piece, pos, hpr, scale]) =>
            [piece, [pos[0] + x * s / k, pos[1] + y * s / k, pos[2] + 0.08 / k], hpr, scale]));
        const whole = robotNodeMesh(this, "robot whole", inBody, colour, trim);
        whole.parent = body;
        whole.material = whole.ccBase = base;
        groups.chassis.push(whole);
        for (const n of ARMOUR) apart.push(...all.filter(m => m.parent === nodes[n] && m !== whole));
        const wholeShadow = caster(robotNodeMesh(this, "robot whole shadow", [...inBody, ...tyres], colour, trim, true), body);
        this.shadowCast(casters.filter(m => m !== wholeShadow).concat([wholeShadow]));
        const painted = deckNumber(d).slice(0, 10).toUpperCase();
        let deckName = null;
        if (painted) {  // (across the deck just above its plate, at the window's height and letter size)
            deckName = this.words(painted, Math.min(0.2, 1.2 * hx / Math.max(3, painted.length)), DECK_PAINT,
                                  [0, hy * 0.68, 0.045 * size + 0.002], [0, -90, 0], nodes.deck);
        }
        const owner = info.owner || "", house = owner === "Resident Robot";
        const label = this.makeLabel(house ? `${d.name || ""}\nResident Robot` : owner || d.name || "", house ? "#ffbf4d" : "#ffffff", 1.1, false);
        const vis = {key: JSON.stringify([info.design || {}, owner]), deckName, root, armour, panels, weapon, spin, blur, chain, chainBase,
                     chainPos: 0, chainStep: 0.06 * size, wheels, wr, ww, label, design: d, owner, weaponType, s, top: top * k, k,
                     angle: 0, roll: 0, hp: null, flash: 0, groups, tints: {}, trimM: base, hazardM: base, trim, hx: hx * k, rear: null, beacon,
                     ultraWeapon: groups.weapon.filter(m => m.parent === nodes.weapon), whole, wholeShadow, apart, shadowsApart, combined: null,
                     health: {}, weak: {}, gone: new Set(), flying: [], bars: {}, barUntil: {}, scorch: 0, fresh: true};
        this.ultraRobots = true;
        this.combine(vis, true);
        this.robots.set(info.id, vis);
        return vis;
    }

    // (ultra, CHANGE 152: rw_gfx.RobotVisual.combine) the body, its panels and (in the shadow map) the tyres drawn
    // together (whole), or every part on its own, as soon as one bends, wobbles or comes off
    combine(v, whole) {
        if (!v.whole || v.combined === whole) return;
        v.combined = whole;
        for (const m of v.apart) m.isVisible = !whole;
        for (const m of v.shadowsApart) m.isVisible = !whole;
        v.whole.isVisible = whole;
        if (v.wholeShadow) v.wholeShadow.isVisible = whole;
    }

    // (ultra) a robot's material: white times its colour scale q (linear: rw_gfx's colour scales), the vertices' colours,
    // the roles' roughness and metal and glow from the atlas (robotfx.js's robotAtlas, its lights colour's), the backs
    // of its faces culled as the window's
    ultraRobotMaterial(lights, q) {
        const key = `rultra:${lights.map(v => v.toFixed(3)).join(",")}:${q.join(",")}`;
        if (this.materials[key]) return this.materials[key];
        const atlas = robotAtlas(this, lights);
        const m = this.lighting.material(key, {rgb: q.map(c => Math.pow(c, 1 / 2.2)), rough: 1, metal: 1,
                                               emission: [ROBOT_GLOW, ROBOT_GLOW, ROBOT_GLOW], mrMap: atlas.mr, glowMap: atlas.glow});
        m.backFaceCulling = true;
        m.sideOrientation = BABYLON.Material.ClockWiseSideOrientation;  // (the front as the file's, turned round by unpackPart)
        m.ccArgs = {make: c => this.ultraRobotMaterial(lights, c)};
        this.materials[key] = m;
        return m;
    }

    // a wedge's plate on its hinge, the hazard stripe along its lip (and the Flipper on both ends' back plate)
    wedge(node, hx, trimM, hazardM, trim) {
        return [this.box(node, hx + 0.02, 0.6, 0.02, trimM, 0, 0.6, -0.01),
                this.box(node, hx + 0.02, 0.06, 0.021, hazardM, 0, 1.14, -0.009),
                this.cyl(node, 0.05, hx, "x", this.paintOf("hinge", trim, 1, 1, {tex: "steel", tile: 1}), 0, 0, 0, null, 16)];
    }

    // ---------- real damage (rw_gfx.RobotVisual.damage) ----------
    // pt: the health % of the body, armour, weapon and four wheels (from the server). Weak parts darken, bend,
    // wobble and rattle; a part at zero comes off and flies away (and goes back on for a new round); a part that has
    // just been hit shows its bar for 1.5 seconds.
    damage(v, r, now, dt, real) {
        const pt = r.pt;
        ["body", ...PARTS].forEach((name, i) => {
            const f = i < pt.length ? Math.max(0, pt[i] / 100) : 1;
            if (f < (v.health[name] ?? 1) - 0.004 && !v.fresh) v.barUntil[name] = now + 1.5;
            if (name !== "body") {
                if (f <= 0 && !v.gone.has(name)) this.comeOff(v, name, v.fresh);
                else if (f > 0 && v.gone.has(name)) this.putBack(v, name);
            }
            v.health[name] = f;
            v.weak[name] = f >= 0.6 ? 0 : (0.6 - f) / 0.6;
        });
        v.fresh = false;
        v.scorch = v.weak.body;
        this.combine(v, !v.flying.length && !PARTS.some(n => n !== "weapon" && (v.weak[n] || v.gone.has(n))));
        const rattle = Math.sin(now * 37) * (v.weak.armour > 0.5 ? 1 : 0);
        if (!v.gone.has("armour")) {  // armour panels bend out (and rattle when nearly off)
            const k = v.weak.armour + 0.15 * rattle;
            for (const pn of v.panels) pn.node.rotationQuaternion = gameQuat(hprQuat(pn.bend[0] * k, pn.bend[1] * k, pn.bend[2] * k));
        }
        const wd = v.weak.weapon;
        if (wd > 0.5 && !v.gone.has("weapon")) {  // a weapon about to come off shakes on its mount
            const right = qrot(r.quat, [1, 0, 0]), off = 0.025 * wd * Math.sin(now * 41);
            v.weapon.position = v3(r.wpos[0] + right[0] * off, r.wpos[1] + right[1] * off, r.wpos[2] + right[2] * off);
            const q = SPINNERS.has(v.weaponType) ? r.quat : r.wquat;
            v.weapon.rotationQuaternion = gameQuat(qmul(q, hprQuat(0, 0, 5 * wd * Math.sin(now * 29))));
        }
        this.fly(v, dt);
        for (const name of ["body", ...PARTS]) {  // the bars of the parts hit in the last 1.5 seconds
            if (now < (v.barUntil[name] || 0) && (name === "body" || real)) {
                if (!v.bars[name]) {
                    v.bars[name] = new HitBar(this.scene, {body: real ? "BODY" : "HEALTH", armour: "ARMOUR", weapon: "WEAPON"}[name] || "WHEEL",
                                              name === "body" || name === "armour" ? 0.7 : 0.36);
                }
                v.bars[name].show(this.barPos(v, r, name), v.health[name], now);
            } else if (v.bars[name]) {
                v.bars[name].hide();
            }
        }
    }

    // where a wheel is in the world (game coordinates)
    wheelPos(v, r, i) {
        const w = v.wheels[i];
        if (v.gone.has("wheel" + i)) { const f = v.flying.find(f => f.node === w.lean); if (f) return f.p; }
        const o = qrot(r.quat, [w.x, w.y, 0.08]);
        return [r.pos[0] + o[0], r.pos[1] + o[1], r.pos[2] + o[2]];
    }

    // body and armour bars stack over the robot (above its name); the weapon's is out in front, each wheel's out
    // to its side
    barPos(v, r, name) {
        const p = r.pos;
        if (name === "body") return [p[0], p[1], p[2] + v.top + 1.55];
        if (name === "armour") return [p[0], p[1], p[2] + v.top + 1.34];
        if (name === "weapon") {
            const f = qrot(r.quat, [0, 1, 0]);
            return [r.wpos[0] + f[0] * 0.45, r.wpos[1] + f[1] * 0.45, r.wpos[2] + f[2] * 0.45 + 0.3];
        }
        const i = Number(name.slice(5)), w = this.wheelPos(v, r, i), rt = qrot(r.quat, [1, 0, 0]), k = v.wheels[i].x > 0 ? 0.45 : -0.45;
        return [w[0] + rt[0] * k, w[1] + rt[1] * k, w[2] + rt[2] * k + 0.3];
    }

    // where a part is nearly off (world position, how bad 0..1): the window puffs smoke there
    trouble(v, r) {
        const out = [];
        if ((v.weak.weapon || 0) > 0.5 && !v.gone.has("weapon")) out.push([r.wpos, v.weak.weapon]);
        for (let i = 0; i < 4; i++) {
            if ((v.weak["wheel" + i] || 0) > 0.5 && !v.gone.has("wheel" + i)) out.push([this.wheelPos(v, r, i), v.weak["wheel" + i]]);
        }
        if ((v.weak.armour || 0) > 0.5 && !v.gone.has("armour")) out.push([[r.pos[0], r.pos[1], r.pos[2] + v.top], v.weak.armour]);
        return out;
    }

    // a part at zero: wheels and armour panels fly off (a lost weapon is moved by the server's physics). quiet: a
    // part that was already off when this window first saw it (it joined late, or the tier changed): not shown
    comeOff(v, name, quiet) {
        v.gone.add(name);
        const cx = v.root.position.x, cy = v.root.position.z;
        const away = p => { const x = p[0] - cx, y = p[1] - cy, l = Math.hypot(x, y); return l > 1e-6 ? [x / l, y / l] : [0, 0]; };
        const loosen = node => {  // (into the world, where it is now)
            node.computeWorldMatrix(true);
            node.setParent(null);
            const b = node.position;
            return {p: [b.x, b.z, b.y], q: fromBabylonQuat(node.rotationQuaternion)};
        };
        const U = (a, b) => a + Math.random() * (b - a);
        if (name === "armour") {
            for (const pn of v.panels) {
                if (quiet) { pn.node.setEnabled(false); continue; }
                const {p, q} = loosen(pn.node), o = away(p), k = U(1.5, 3.5);
                v.flying.push({node: pn.node, p, vel: [o[0] * k, o[1] * k, U(3, 5)], spin: [U(-400, 400), U(-400, 400), U(-300, 300)],
                               rest: 0.03, lie: pn.lie, hpr: quatHpr(q)});
            }
            this.tint(v, "armour", [1, 1, 1]);  // (off the robot: its own colour)
        } else if (name.startsWith("wheel")) {
            const w = v.wheels[Number(name.slice(5))].lean;
            if (quiet) { w.setEnabled(false); return; }
            const {p, q} = loosen(w), o = away(p), k = U(2.0, 4.0);
            v.flying.push({node: w, p, vel: [o[0] * k, o[1] * k, U(2.5, 4)], spin: [U(-200, 200), 0, U(200, 500)], rest: v.ww, lie: [0, 90], hpr: quatHpr(q)});
        }
    }

    // a new round: the part is back on the robot
    putBack(v, name) {
        v.gone.delete(name);
        let nodes = [];
        if (name === "armour") {
            for (const pn of v.panels) {
                pn.node.parent = v.armour;
                pn.node.position = v3(...pn.hinge);
                pn.node.rotationQuaternion = BABYLON.Quaternion.Identity();
                pn.node.scaling.setAll(1);  // (loosened, it took the robot's size with it: ultra's k)
                pn.node.setEnabled(true);
                nodes.push(pn.node);
            }
            v.tints.armour = null;
        } else if (name.startsWith("wheel")) {
            const w = v.wheels[Number(name.slice(5))];
            w.lean.parent = v.root;
            w.lean.position = v3(w.x, w.y, 0.08);
            w.lean.rotationQuaternion = BABYLON.Quaternion.Identity();
            w.lean.setEnabled(true);
            nodes = [w.lean];
        }
        v.flying = v.flying.filter(f => !nodes.includes(f.node));
    }

    // parts that came off: thrown clear, they bounce and come to rest lying flat on the floor
    fly(v, dt) {
        const half = ARENA / 2 - 0.2;
        for (const f of v.flying) {
            if (!f.vel) continue;
            f.vel[2] -= 9.81 * dt;
            const p = f.p.map((c, i) => c + f.vel[i] * dt);
            for (const axis of [0, 1]) {  // the arena walls
                if (Math.abs(p[axis]) > half) { p[axis] = Math.sign(p[axis]) * half; f.vel[axis] *= -0.4; }
            }
            let settled = false;
            if (p[2] < f.rest) {
                p[2] = f.rest;
                f.vel = [f.vel[0] * 0.55, f.vel[1] * 0.55, -f.vel[2] * 0.3];
                f.spin = f.spin.map(a => a * 0.5);
                if (Math.hypot(...f.vel) < 0.6) { f.hpr = [f.hpr[0], f.lie[0], f.lie[1]]; settled = true; }  // lying flat
            }
            f.p = p;
            f.node.position = v3(...p);
            if (settled) f.vel = null;
            else f.hpr = f.hpr.map((a, i) => a + f.spin[i] * dt);
            f.node.rotationQuaternion = gameQuat(hprQuat(...f.hpr));
        }
    }

    // ---------- each frame ----------
    // st: the watched arena, blended ({robots: [...], hz, intro, rd}); dt seconds
    frame(st, dt, t) {
        const seen = new Set(), fx = this.fx, real = !!(st && st.rd);
        this.lastRobots = (st && st.robots) || [];
        if (this.beaconMat) {  // a turning amber beacon (its lines pulse on the line tiers)
            const g = Math.floor(t * 3) % 2 === 0 ? 6 : 1;
            this.setGlow(this.beaconMat, [g, g * 0.5, 0]);
            this.pulseLine((this.glowLines || {}).beacon, g > 1 ? 1 : 0.35);
        }
        for (const r of this.lastRobots) {
            const v = this.robots.get(r.id);
            if (!v) continue;
            seen.add(r.id);
            v.root.setEnabled(true);
            v.weapon.setEnabled(true);
            v.label.setEnabled(true);
            for (const f of v.flying) f.node.setEnabled(true);
            v.root.position = v3(r.pos[0], r.pos[1], r.pos[2]);
            v.root.rotationQuaternion = gameQuat(r.quat);
            v.weapon.position = v3(r.wpos[0], r.wpos[1], r.wpos[2]);
            if (SPINNERS.has(v.weaponType)) {
                v.weapon.rotationQuaternion = gameQuat(r.quat);  // (the spin itself is drawn here, from its speed)
                v.angle += (r.rpm || 0) / 60 * 2 * Math.PI * dt * 0.35;
                if (v.weaponType === "spinner") v.spin.rotation.y = v.angle; else v.spin.rotation.x = v.angle;
                if (v.blur) {  // a see-through disc when it spins fast
                    const a = Math.min(0.28, (r.rpm || 0) / 1400);
                    v.blur.isVisible = a > 0.002;
                    v.blur.visibility = a / 0.28;
                }
            } else {
                v.weapon.rotationQuaternion = gameQuat(r.wquat);
            }
            if (r.w2 && v.weaponType === "wedge") {  // the Flipper on both ends user mod: the back plate is a copy of the front one
                if (!v.rear) {
                    v.rear = new BABYLON.TransformNode("rear", this.scene);
                    v.rear.rotationQuaternion = BABYLON.Quaternion.Identity();
                    if (v.ultraWeapon) {  // (ultra: the smooth plate again, k times its size)
                        const kw = new BABYLON.TransformNode("pieces", this.scene);
                        kw.parent = v.rear;
                        kw.scaling.setAll(v.k);
                        for (const m of v.ultraWeapon) { const c = m.clone(m.name, kw); c.ccBase = m.ccBase; v.groups.weapon.push(c); }
                    } else {
                        for (const m of this.wedge(v.rear, v.hx, v.trimM, v.hazardM, v.trim)) { m.ccBase = m.material; v.groups.weapon.push(m); }
                    }
                    this.shadowCast(v.rear.getChildMeshes());
                    v.tints.weapon = null;
                }
                v.rear.setEnabled(true);
                v.rear.position = v3(r.w2[0], r.w2[1], r.w2[2]);
                v.rear.rotationQuaternion = gameQuat(qmul(r.w2.slice(3, 7), hprQuat(180, 0, 0)));  // (the front plate's shape, pointing backwards)
            } else if (v.rear) {
                v.rear.setEnabled(false);
            }
            v.roll += (r.speed || 0) * dt / v.wr;
            const spinDeg = v.roll * 180 / Math.PI;
            v.wheels.forEach((w, i) => {
                if (v.gone.has("wheel" + i)) return;
                const weak = v.weak["wheel" + i] || 0;  // a failing wheel leans out and wobbles as it turns
                w.lean.rotationQuaternion = weak ? gameQuat(hprQuat(0, 0, (w.x > 0 ? 1 : -1) * weak * 9 + weak * 7 * Math.sin(spinDeg * Math.PI / 180)))
                                                 : BABYLON.Quaternion.Identity();
                w.spin.rotation.x = v.roll;
            });
            if (v.chain && (r.on ?? true)) {  // the chain runs round the bar
                v.chainPos = (v.chainPos + dt * 3.0) % (v.chainStep || 0.06);
                v.chain.position.z = v.chainBase + v.chainPos;  // (Babylon's z: the game's y, along the bar)
            }
            if (r.fl && fx) {  // the flame thrower: a jet of fire from its nozzle
                const fwd = qrot(r.quat, [0, 1, 0]), k = 0.44 * v.s + 0.05;
                fx.flame([r.wpos[0] + fwd[0] * k, r.wpos[1] + fwd[1] * k, r.wpos[2] + fwd[2] * k], fwd, dt);
            }
            if (r.pt) {  // parts bending, wobbling and coming off, and the bars of parts just hit
                this.damage(v, r, t, dt, real);
                if (fx) for (const [p, amount] of this.trouble(v, r)) fx.smoke(p, 0.2 + 0.35 * amount, dt);
            }
            if (v.hp !== null && r.hp < v.hp - 0.5) v.flash = 0.15;
            v.hp = r.hp;
            v.flash = Math.max(0, v.flash - dt);
            // the colours: a flash when hit, scorched as the body is hurt, each weak part darker (rw_gfx's colour scales)
            const sc = v.scorch, ch = v.flash > 0 ? [2.2, 2.2, 2.2] : [1 - 0.4 * sc, 1 - 0.45 * sc, 1 - 0.5 * sc];
            this.tint(v, "chassis", ch);
            const a = v.weak.armour || 0;
            this.tint(v, "armour", v.gone.has("armour") ? [1, 1, 1] : [ch[0] * (1 - 0.45 * a), ch[1] * (1 - 0.5 * a), ch[2] * (1 - 0.55 * a)]);
            const wd = v.weak.weapon || 0;
            this.tint(v, "weapon", [1 - 0.45 * wd, 1 - 0.5 * wd, 1 - 0.55 * wd]);
            for (let i = 0; i < 4; i++) { const k = 1 - 0.4 * (v.weak["wheel" + i] || 0); this.tint(v, "wheel" + i, [k, k, k]); }
            const damage = 1 - Math.max(0, r.hp) / Math.max(1, r.max || 1);
            if (fx && damage > 0.55 && r.pos[2] > -1) fx.smoke(r.pos, (damage - 0.55) / 0.45 + (r.ko ? 1 : 0), dt);
            v.label.position = v3(r.pos[0], r.pos[1], r.pos[2] + 1.3 * Math.max(1, v.s));
        }
        for (const [id, v] of this.robots) {
            if (seen.has(id)) continue;
            v.root.setEnabled(false); v.weapon.setEnabled(false); v.label.setEnabled(false);
            if (v.rear) v.rear.setEnabled(false);
            for (const f of v.flying) f.node.setEnabled(false);
            for (const b of Object.values(v.bars)) b.hide();
        }
        const hz = st && st.hz;
        if (hz) {
            const ht = hz.t || 0;  // (the arena's clock: the lights blink and pulse with the app's)
            if (this.pitLid && hz.pit !== undefined) this.pitLid.position.y = hz.pit;
            const G = this.glowLines || {};  // (the line tiers: the glowing parts' lines pulse as they would glow)
            if (hz.pit_open ?? true) { const p = 2.5 + 1.5 * Math.sin(ht * 4); this.setGlow(this.pitGlowMat, [p * 1.6, p * 0.12, p * 0.04]); this.pulseLine(G.pit, p / 4); }
            else { this.setGlow(this.pitGlowMat, [0.05, 0.3, 0.08]); this.pulseLine(G.pit, 0.35); }  // (closed: a calm green)
            if (this.ffPivot && hz.ff) this.ffPivot.rotationQuaternion = gameQuat(hz.ff);
            const warn = (!hz.on || hz.on.floor_flipper !== false) && (ht % 4) > 3.2;  // (blinks just before it fires)
            const lit = warn && Math.floor(ht * 8) % 2 === 0;
            this.setGlow(this.ffLampMat, lit ? [8, 0.3, 0.1] : [0.2, 0, 0]);
            this.pulseLine(G.fflamp, lit ? 1 : 0.45);
            (hz.saws || []).forEach((h, i) => {
                const saw = this.saws[i];
                if (!saw) return;
                saw.node.position.y = -1.1 + 1.35 * h;
                saw.angle -= (400 + 1400 * Math.min(1, 2 * h)) * Math.PI / 180 * dt;
                saw.spin.rotation.z = saw.angle;
                const a = Math.min(0.22, h * 0.3);  // (rw_gfx: the blur as it rises, the hot rim while it grinds)
                saw.blur.isVisible = !this.wire && a > 0.002;  // (no blur on the line tiers)
                saw.blur.visibility = a / 0.22;
                saw.glow.isVisible = !!(hz.saw_hot || [])[i];
                if (saw.glowLines) saw.glowLines.isVisible = saw.glow.isVisible;
            });
            if (this.spikeBank) this.spikeBank.position.x = -10.5 + 0.6 * (hz.spikes || 0);
            for (const [i, f] of this.flames.entries()) {
                const hgt = Math.max(0.2, (0.5 + (hz.flames || 0)) * (0.8 + 0.3 * Math.sin(t * 9 + i * 1.7)));
                f.scaling.y = hgt;
                f.position.y = -0.5 + hgt / 2;
            }
            if (this.boostMat) {
                const g = 0.9 + 0.35 * Math.sin(ht * 5), on = !!(hz.boost ?? 1);
                this.setGlow(this.boostMat, on ? [0.25 * g, g, 0.35 * g] : [0.45, 0.06, 0.04]);
                this.pulseLine(G.boost, on ? g / 1.25 : 0.3);
            }
            if (this.repairMat) {
                const g = hz.repair ? 2.0 + 1.2 * Math.sin(ht * 6) : 0.6;
                this.setGlow(this.repairMat, [0.2 * g, 0.5 * g, g]);
                this.pulseLine(G.repair, Math.min(1, g / 3.2 + 0.2));
            }
            const beams = hz.lasers || [];  // lasers: a beam for each laser firing, from where it starts to its end
            while (this.lasers.length < beams.length) this.lasers.push(this.buildLaser());
            this.lasers.forEach((aim, i) => {
                const b = beams[i], len = b ? Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]) : 0;
                if (len < 0.05) { aim.setEnabled(false); return; }
                aim.position = v3(b[0], b[1], b[2]);
                aim.lookAt(v3(b[3], b[4], b[5]));
                aim.scaling.z = len;
                aim.setEnabled(true);
            });
        }
        if (fx) fx.update(dt);
        this.updateCamera(st, dt, t);
        this.followSun();
    }

    // sparks and debris where something hit (the debris in the colour of the robot nearest the hit, as the window
    // picks it), a shower of sparks from a saw
    impact(pos, dmg, kind) {
        if (!this.fx) return;
        let best = null, bd = Infinity;
        for (const r of this.lastRobots || []) {
            const dd = (r.pos[0] - pos[0]) ** 2 + (r.pos[1] - pos[1]) ** 2 + (r.pos[2] - pos[2]) ** 2;
            if (dd < bd) { bd = dd; best = r; }
        }
        const v = best ? this.robots.get(best.id) : null;
        this.fx.impact(pos, dmg, kind, v ? rgb255(v.design.colour, [200, 120, 40]) : [0.7, 0.7, 0.7]);
    }

    stream(pos, dir, count) {
        if (this.fx) this.fx.stream(pos, dir, count);
    }

    // the window's camera rig (rw_camera.GameCamera.update): where the camera wants to be and what it looks at, in
    // game coordinates, eased there; your robot's node or null, its nose's distance, the robots still fighting.
    // CHANGE 143: every view zooms, swings round, tilts and moves sideways as the window's (this.cam: robotfx.js)
    rigCamera(dt) {
        const cam = this.camera, c = this.cam, mode = this.mode;
        c.setMode(mode);
        const me = this.follow !== null ? this.robots.get(this.follow) : null;
        const live = [];
        for (const v of this.robots.values()) if (v.root.isEnabled() && v.root.position.y > -1) live.push([v.root.position.x, v.root.position.z, v.root.position.y]);
        const centre = live.length ? [live.reduce((a, p) => a + p[0], 0) / live.length, live.reduce((a, p) => a + p[1], 0) / live.length, 0.3] : [0, 0, 0.3];
        let mine = me && me.root.isEnabled() ? [me.root.position.x, me.root.position.z, me.root.position.y] : null;
        if (mine && mine[2] < -1) mine = null;  // (fallen in the pit: watch the arena instead)
        const focus = (mode === "third" || mode === "fpv") && !mine ? "zoom" : mode;
        let want, look, k = 5, fov = 70, near = 0.2;
        const flatOf = () => {
            const f = new BABYLON.Vector3(0, 0, 1).rotateByQuaternionToRef(me.root.rotationQuaternion, new BABYLON.Vector3());
            let x = f.x, y = f.z;
            const l = Math.hypot(x, y);
            if (l < 0.1) { x = 0; y = 1; } else { x /= l; y /= l; }
            return [x, y, f];
        };
        const at = (p, o) => [p[0] + o[0], p[1] + o[1], p[2] + o[2]];
        if (focus === "third") {
            const [fx, fy] = flatOf(), d = c.dist;
            c.lookZ = 0;
            want = at([mine[0], mine[1], 0], c.swing([-fx * d, -fy * d, d * 0.55]));
            if (d < 9) {  // low down: stay inside the arena, in front of the wall posts; squeezed by a wall, go up instead
                const inside = HALF - 0.6, back = Math.hypot(want[0] - mine[0], want[1] - mine[1]);
                want[0] = Math.max(-inside, Math.min(inside, want[0]));
                want[1] = Math.max(-inside, Math.min(inside, want[1]));
                want[2] += Math.max(0, back - Math.hypot(want[0] - mine[0], want[1] - mine[1])) * 1.1;
            }
            const ahead = c.orbit || c.tilt ? 0 : 2;  // (swung round: it looks at the robot itself)
            look = [mine[0] + fx * ahead, mine[1] + fy * ahead, 0.4];
        } else if (focus === "fpv") {
            let [fx, fy] = flatOf();
            const up = new BABYLON.Vector3(0, 1, 0).rotateByQuaternionToRef(me.root.rotationQuaternion, new BABYLON.Vector3());
            if (up.y < 0.3 && this.rigLook) { fx = this.rigLook[0] - this.rigPos[0]; fy = this.rigLook[1] - this.rigPos[1]; const l = Math.hypot(fx, fy) || 1; fx /= l; fy /= l; }
            const front = 0.8 * (me.s || 1);
            want = [mine[0] + fx * (front + 0.15), mine[1] + fy * (front + 0.15), Math.max(0.35, mine[2] + 0.45)];
            c.lookZ = 50;  // (looking round from the robot: up and down are both fine)
            const o = c.swing([-fx * 6, -fy * 6, 0.35]);
            look = [want[0] - o[0], want[1] - o[1], want[2] - o[2]];
            k = 14; fov = 95 * c.fpvScale; near = 0.05;
        } else if (focus === "zoom") {
            let target = mine && mode !== "zoom" ? [mine[0], mine[1], 0.3] : centre;
            if (mode === "zoom" && mine && live.length) target = [(mine[0] + centre[0]) / 2, (mine[1] + centre[1]) / 2, 0.3];
            const rail = [Math.max(-8, Math.min(8, target[0] * 0.7)), -HALF - 1.2, 5.4];  // (a TV camera on the south rail)
            const spread = Math.max(1.5, ...live.map(p => Math.hypot(p[0] - target[0], p[1] - target[1], p[2] - target[2])));
            c.lookZ = target[2];
            const o = c.swing([rail[0] - target[0], rail[1] - target[1], rail[2] - target[2]]);
            want = at(target, o);
            const dist = Math.hypot(...o);
            fov = Math.max(4, Math.min(100, 2 * Math.atan((spread + 1.3) * c.zoomScale / dist) * 180 / Math.PI));
            look = target; k = 2.5;
        } else if (focus === "arena") {  // high and steep: all the floor (zoom moves the camera along its line)
            look = [0, -2, 0]; c.lookZ = 0;
            const s = c.arenaScale;
            want = at(look, c.swing([0, (-HALF + 1 + 2) * s, 17 * s])); fov = 90; k = 3;
        } else {  // centre camera: fixed, lower down, aimed at the middle (it doesn't follow anyone)
            look = [0, 0, 0.3]; c.lookZ = 0.3;
            const s = c.centreScale;
            want = at(look, c.swing([0, (-HALF - 3.5) * s, 6.5 * s])); fov = 62; k = 3;
        }
        if (!this.rigPos || this.snapCamera) { this.rigPos = want.slice(); this.rigLook = look.slice(); this.rigFov = fov; this.snapCamera = false; }
        const a = Math.min(1, dt * k);
        for (let i = 0; i < 3; i++) { this.rigPos[i] += (want[i] - this.rigPos[i]) * a; this.rigLook[i] += (look[i] - this.rigLook[i]) * a; }
        this.rigFov += (fov - this.rigFov) * Math.min(1, dt * 4);
        // moved sideways (the window's CHANGE 112): the camera and what it looks at, across the view
        this.rigShift = [0, 0, 0];
        const p = c.pans[c.mode];
        if (p) {
            const dx = this.rigLook[0] - this.rigPos[0], dy = this.rigLook[1] - this.rigPos[1], l = Math.hypot(dx, dy);
            if (l > 1e-6) this.rigShift = [dy / l * p, -dx / l * p, 0];  // ((look - pos) x up)
        }
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;  // (Panda's lens: the fov is across)
        cam.fov = this.rigFov * Math.PI / 180;
        cam.minZ = near;
        // (the rig places the camera: Babylon's own orbit limits and drift from the mouse are not for it)
        cam.lowerRadiusLimit = 0.01;
        cam.upperBetaLimit = Math.PI - 0.01;
        cam.inertialAlphaOffset = cam.inertialBetaOffset = cam.inertialRadiusOffset = cam.inertialPanningX = cam.inertialPanningY = 0;
        cam.setTarget(v3(...at(this.rigLook, this.rigShift)));
        cam.setPosition(v3(...at(this.rigPos, this.rigShift)));
        return focus;
    }

    // the camera, then the shake from big hits (rw_fx.shake_offset, half of it, as lab_client passes it): the rig's
    // views move the camera only (it still looks where it looked, as rw_camera does); the orbiting views move the
    // camera and what it looks at together, put back before the next frame so the orbit isn't changed
    updateCamera(st, dt, t) {
        const cam = this.camera;
        if (this.shook) { cam.target.subtractInPlace(this.shook); this.shook = null; }
        this.placeCamera(st, dt, t);
        const intro = st && st.intro !== null && st.intro !== undefined;
        const off = this.fx && !intro ? this.fx.shakeOffset() : null;  // (none in the countdown's sweep)
        if (!off) return;
        if (RIG_MODES.includes(this.mode) && this.rigPos) {
            const s = this.rigShift || [0, 0, 0];  // (with the view's sideways move: CHANGE 143)
            cam.setPosition(v3(this.rigPos[0] + s[0] + off[0], this.rigPos[1] + s[1] + off[1], this.rigPos[2] + s[2] + off[2]));
        } else {
            this.shook = v3(off[0], off[1], off[2]);
            cam.target.addInPlace(this.shook);
        }
    }

    placeCamera(st, dt, t) {
        const cam = this.camera;
        if (RIG_MODES.includes(this.mode) && !(st && st.intro !== null && st.intro !== undefined)) {
            const focus = this.rigCamera(dt);
            for (const m of this.rig || []) m.isVisible = focus !== "arena";  // (the full arena view looks down past the rig)
            return;
        }
        cam.fovMode = BABYLON.Camera.FOVMODE_VERTICAL_FIXED;
        cam.fov = 0.8;
        cam.minZ = 0.1;
        cam.lowerRadiusLimit = 2;  // (the orbiting views' own limits again: the rig takes them off)
        cam.upperBetaLimit = 1.5;
        const above = cam.position.y > 9.0;  // (looking down past the lighting rig: hidden, as the app's full-arena camera does)
        for (const m of this.rig || []) m.isVisible = !above;
        if (st && st.intro !== null && st.intro !== undefined) {  // the pre-battle intro: round the arena
            const a = 0.45 * st.intro - 1.2;
            cam.target = BABYLON.Vector3.Lerp(cam.target, v3(0, 0, 0.5), Math.min(1, dt * 3));
            cam.alpha = -Math.PI / 2 + a;
            cam.beta = 1.05;
            cam.radius = 13;
            return;
        }
        if (this.mode === "follow" && this.follow !== null && this.robots.has(this.follow)) {
            const v = this.robots.get(this.follow);
            if (v.root.isEnabled()) {
                const target = v.root.position.add(new BABYLON.Vector3(0, 0.4, 0));
                cam.target = this.snapCamera ? target : BABYLON.Vector3.Lerp(cam.target, target, Math.min(1, dt * 4));
                this.snapCamera = false;
            }
        }
    }

    setMode(mode, follow = null) {
        this.mode = mode;
        this.follow = follow;
        this.snapCamera = true;
        const cam = this.camera;
        if (this.shook) { cam.target.subtractInPlace(this.shook); this.shook = null; }
        if (RIG_MODES.includes(mode)) { this.cam.setMode(mode); return; }  // (the rig places the camera every frame)
        if (mode === "overview") { cam.target = v3(0, 0, 0); cam.radius = 27; cam.alpha = -Math.PI / 2; cam.beta = 0.78; }
        if (mode === "follow") { cam.radius = 8; cam.beta = 0.95; }
    }
}

// ---------- the garage's robot preview (lab_client's CHANGE 82; the page's CHANGE 143) ----------
// A turning robot on a round pedestal in a light grey studio, beside the garage's title, built again only when the
// design being edited changes (the draft, before BUILD). Built by RobotScene.addRobot in its own small canvas and
// engine: WebGL 1 and Babylon's simple materials (no textures, so light on memory and quick to make), drawn about 30
// times a second while the garage is on screen, and let go a few seconds after it isn't.
const TEX_TONE = {steel: [0.56, 0.57, 0.6], tyre: [0.07, 0.07, 0.08], hazard: [0.95, 0.75, 0.08], diamond: [0.6, 0.6, 0.62]};  // (each texture set's own colour)
const RIDE = 0.12;  // (lab_sim.RIDE: the body origin above the floor)

// lab_sim.shapes' weapon pivot for a robot of this size: the standard robot nearest (80% to 120%) made bigger or
// smaller all over. Returns [pivot, k]
function weaponPivot(weapon, size) {
    const ref = Math.max(0.8, Math.min(1.2, size)), k = size / ref, hy = 0.8 * ref, top = 0.1 + 0.18 * ref;
    const p = {wedge: [0, hy - 0.05, top], spinner: [0, hy + 0.28 * ref, 0.1], drum: [0, hy + 0.18, 0.08],
               vdisc: [0, hy + 0.05, 0.42 * ref - (0.32 - 0.08) + 0.04], flame: [0, hy - 0.25 * ref, top + 0.12 * ref],
               laser: [0, hy - 0.3 * ref, top + 0.08 * ref], chainsaw: [0, hy * 0.35, top + 0.12]}[weapon] || [0, -0.2 * ref, top + 0.1];
    return [p.map(c => c * k), k];
}

class PreviewScene extends RobotScene {
    populate() {
        const scene = this.scene;
        // (CHANGE 152) ultra's robot on ultra, as the window's preview: the file asked for (on ultra alone), high's robot
        // until it has come, then made again (show)
        this.ultra = !!this.settings.ultra;
        this.screenColours = true;
        if (this.ultra) loadRobotModels().then(d => { if (d && this.scene === scene) this.key = null; });
        this.wheelLines = {};
        this.glowLines = {};
        this.lineCount = 0;
        // (a light grey studio: dark parts stand out against it; black on the line tiers, the pedestal's edges in lines)
        scene.clearColor = this.wire ? new BABYLON.Color4(0, 0, 0, 1) : new BABYLON.Color4(0.46, 0.48, 0.53, 1);
        // light from everywhere (nothing on the robot left black), a key lamp high at the front, a rim lamp behind
        const sky = scene.getLightByName("sky");
        if (sky) { sky.intensity = 0.75; sky.diffuse = new BABYLON.Color3(1, 1, 1); sky.groundColor = new BABYLON.Color3(0.38, 0.38, 0.42); }
        if (this.sun) { this.sun.direction = v3(-2.5, 3.0, -2.6).normalize(); this.sun.intensity = 1.0; }
        const rim = new BABYLON.PointLight("rim", v3(0.5, 3.0, 2.5), scene);
        rim.intensity = 0.5;
        // the pedestal the robot stands on (it turns with it), and the studio's floor
        this.turn = new BABYLON.TransformNode("turntable", scene);
        this.cyl(this.turn, 1.25, 0.06, "z", this.material("pedestal", [0.78, 0.8, 0.84], 0.75, 0.05), 0, 0, -0.06, null, 48);
        this.cyl(this.turn, 1.45, 0.03, "z", this.material("plinth", [0.6, 0.62, 0.66], 0.8, 0.05), 0, 0, -0.15, null, 48);
        const studio = this.cyl(null, 3.5, 0.02, "z", this.material("studio", [0.5, 0.52, 0.57], 1, 0), 0, 0, -0.2, null, 48);
        if (this.wire) {
            const mat = this.lineMaterial("pedestal", 1, ...this.lineFade());
            this.linesMesh("pedestallines", this.edgeLines(this.turn.getChildMeshes(), this.wire, this.turn), mat, this.turn);
            this.linesMesh("studiolines", this.edgeLines([studio], this.wire), mat);
        }
        const cam = this.camera;  // (the window's: 34 degrees, from the front and above)
        cam.detachControl();
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;
        cam.fov = 34 * Math.PI / 180;
        cam.minZ = 0.3;
        cam.maxZ = 40;
        cam.setTarget(v3(0, 0, 0.2));
        cam.setPosition(v3(0, -4.6, 2.0));
        this.key = null;
    }

    // Babylon's simple materials in each texture set's own colour, with a little shine on metal
    material(name, rgb, rough = 0.9, metal = 0.0, glow = 0, opts = {}) {
        const t = TEX_TONE[opts.tex];
        const m = super.material(name, t ? rgb.map((c, i) => c * t[i]) : rgb, rough, metal, glow, opts);
        if (m.specularColor && !m.ccShine) {
            m.ccShine = true;
            const s = metal ? 0.3 * (1.2 - Math.min(1, rough)) : 0.04;
            m.specularColor = new BABYLON.Color3(s, s, s);
            m.specularPower = 24;
        }
        return m;
    }

    // (ultra, CHANGE 152) the smooth robot in Babylon's simple materials: the vertices' screen colours, a little shine
    // where a role is smooth metal (the preview's own rule, above), its glow from the atlas
    ultraRobotMaterial(lights) {
        const key = `rultra:${lights.map(v => v.toFixed(3)).join(",")}`;
        if (this.materials[key]) return this.materials[key];
        const atlas = robotAtlas(this, lights), roles = robotModelsData().roles, names = Object.keys(roles);
        if (!this.specAtlas) {
            const data = new Uint8Array(names.length * 4);
            names.forEach((r, i) => {
                const L = roles[r], s = L.metal ? 0.3 * (1.2 - Math.min(1, L.rough)) : 0.04;
                data.set([Math.round(s * 255), Math.round(s * 255), Math.round(s * 255), 255], i * 4);
            });
            this.specAtlas = BABYLON.RawTexture.CreateRGBATexture(data, names.length, 1, this.scene, false, false, BABYLON.Texture.NEAREST_SAMPLINGMODE);
        }
        const m = new BABYLON.StandardMaterial(key, this.scene);
        m.diffuseColor = new BABYLON.Color3(1, 1, 1);
        m.specularColor = new BABYLON.Color3(1, 1, 1);
        m.specularTexture = this.specAtlas;
        m.specularPower = 24;
        m.emissiveTexture = atlas.glow;
        m.emissiveTexture.level = ROBOT_GLOW;
        m.backFaceCulling = true;
        m.sideOrientation = BABYLON.Material.ClockWiseSideOrientation;
        this.materials[key] = m;
        return m;
    }

    // the design on the pedestal, built again only when it has changed (lab_client.preview_show, preview_pose)
    show(design) {
        const key = JSON.stringify(design || {});
        if (key === this.key) return;
        this.key = key;
        for (const v of this.robots.values()) this.disposeRobot(v);
        this.robots.clear();
        let v;
        try { v = this.addRobot({id: 0, design: JSON.parse(key), owner: ""}); } catch (e) { return; }  // (half-typed in the code: no picture)
        v.label.setEnabled(false);
        if (v.blur) v.blur.isVisible = false;
        v.root.parent = v.weapon.parent = this.turn;
        // as it rests: the body at ride height, the weapon on its mount (the sim's pivot; a big hammer stands up)
        const [pivot, k] = weaponPivot(v.weaponType, v.s);
        v.root.position = v3(0, 0, RIDE);
        v.weapon.position = v3(pivot[0], pivot[1], pivot[2] + RIDE);
        v.weapon.rotationQuaternion = gameQuat(v.weaponType === "hammer" && k > 1 ? hprQuat(0, 115, 0) : [1, 0, 0, 0]);
    }
}

export class RobotPreview {
    constructor(tier) {
        this.canvas = document.createElement("canvas");
        this.canvas.className = "gpreview";
        this.engine = new BABYLON.Engine(this.canvas, true, {disableWebGL2Support: true, alpha: false, stencil: false}, false);  // (false: CHANGE 161)
        try { this.scene = new PreviewScene(this.canvas, tier, this.engine); } catch (e) { this.engine.dispose(); throw e; }
        this.design = null;
        this.seen = this.drawn = this.checked = performance.now();
        this.gone = false;
        this.engine.runRenderLoop(() => this.tick());
    }

    attach(slot, design) {  // (the garage is drawn again often: the same canvas goes into its new place)
        if (this.canvas.parentNode !== slot) slot.append(this.canvas);
        this.design = design;
        this.engine.resize();
        this.scene.show(design);
        this.seen = performance.now();
    }

    tick() {
        if (this.gone) return;
        const now = performance.now(), c = this.canvas, r = c.isConnected ? c.getBoundingClientRect() : null;
        const shown = r && r.width > 0 && r.right > 0 && r.bottom > 0 && r.left < window.innerWidth && r.top < window.innerHeight;
        if (!shown) {  // (the garage closed, or the panel slid away: rests, then let go)
            if (now - this.seen > 4000) setTimeout(() => this.dispose(), 0);
            return;
        }
        this.seen = now;
        if (now - this.drawn < 33) return;
        const dt = Math.min(0.1, (now - this.drawn) / 1000);
        this.drawn = now;
        if (now - this.checked > 300) { this.checked = now; this.scene.show(this.design); }  // (a slider moved, a name typed)
        this.scene.turn.rotation.y -= 25 * Math.PI / 180 * dt;  // (25 degrees a second, anticlockwise from above)
        this.scene.render();
    }

    dispose() {
        if (this.gone) return;
        this.gone = true;
        this.engine.stopRenderLoop();
        try { this.scene.dispose(); this.engine.dispose(); } catch (e) { /* already gone */ }
        this.canvas.remove();
    }
}

export class RobotGame {
    static detect(m) { return !!(m.rules && m.rules.weapons && m.default); }

    constructor(app) {
        this.app = app;
        this.id = "robotlab";
        this.title = "Robot Lab";
        this.word = "robot";
        this.scene = new RobotScene(app.canvas, app.tier, app.engine);
        this.watch = null;  // the arena drawn (null: the teacher's robot's, else the first)
        this.mods = ["mods/arena.py", "mods/rules.py", "mods/robots/<username>.py"];
        this.last = null;
        this.events = new Set();
        this.controlKind = "robot";  // (play.js: the arrows drive, Space fires)
        // (CHANGE 166) the robots drawn where they are now (ahead.js); each robot's drive, from the roster
        this.ahead = new RobotsAhead();
        this.drive = new Map();
        this.aheadNote = "the robots drawn where they are now, and yours answers your keys at once";  // (app.js: Movement)
        // B: the health bars small (just the title) or full, kept on this computer as the window keeps hud_small
        try { this.boardSmall = localStorage.getItem("hud_small") === "1"; } catch (e) { this.boardSmall = false; }
        // the health bars dragged by their title bar, as the window's (lab_client's hud_at), kept on this computer;
        // a double click on the title puts them back (drag.js, CHANGE 143)
        this.boardDrag = app.makeDraggable ? app.makeDraggable($("places"), "robotboard", {handle: ".bhead"}) : null;
    }

    welcome(m) {
        const p = this.app.params;
        this.followMine = this.app.state.role === "learner";  // (a learner's camera starts behind their own robot)
        // the views kept in their profile, in the window's own format (rw_camera.settings: each view's zoom, swing,
        // tilt and sideways move), or the page's older {mode, dist} (CHANGE 143)
        const saved = (m.prefs || {}).camera || {};
        this.scene.cam.restore(saved);
        if (RIG_MODES.includes(saved.mode)) this.rigMode = saved.mode;
        this.hookCamera();
        if (p.get("cam")) { this.followMine = false; this.scene.setMode(p.get("cam") === "chase" ? "follow" : "overview", p.get("follow") !== null ? Number(p.get("follow")) : null); }
    }

    // our own robot's id (the roster's mine), or null: no robot of ours to drive
    myId() {
        const S = this.app.state, roster = S.roster;
        const id = roster && roster.mine ? roster.mine[S.name] : null;
        return id === undefined ? null : id;
    }

    // V: the camera views (behind your robot, the whole arena)
    cycleCamera() {
        const i = RIG_MODES.indexOf(this.scene.mode);
        this.rigMode = RIG_MODES[(i + 1) % RIG_MODES.length];
        this.scene.setMode(this.rigMode, this.myId());
        this.keepCamera();
    }

    // ---------- the window's camera controls (rw_camera, lab_client's keys: CHANGE 143) ----------
    // The canvas's own: the wheel zooms the view in use (the other way round with the profile's invert_zoom, as the
    // window's Settings), a sideways scroll moves it sideways, the right button dragged swings it round and tilts
    // it. The keys are app.js's, calling zoom, turnCamera, resetCamera, fullArena and watchArena below.
    hookCamera() {
        if (this.listeners) return;
        const canvas = this.app.canvas;
        this.listeners = [
            [canvas, "wheel", e => {
                if (!RIG_MODES.includes(this.scene.mode)) return;  // (the orbiting views zoom as Babylon's)
                if (Math.abs(e.deltaX) > Math.abs(e.deltaY)) {  // (a sideways scroll: wheel_left and wheel_right, 0.6 m a notch)
                    this.panCamera(e.deltaX * (e.deltaMode === 1 ? 0.2 : e.deltaMode === 2 ? 6 : 0.006));
                } else if (e.deltaY) {
                    const f = e.deltaY > 0 ? 1 / 0.88 : 0.88;
                    this.zoomBy(this.zoomInverted() ? 1 / f : f);
                }
            }, {passive: true}],
            [canvas, "pointerdown", e => {
                if (e.button !== 2 || !RIG_MODES.includes(this.scene.mode)) return;  // (the orbiting views drag as Babylon's)
                this.dragFrom = [e.clientX, e.clientY];
                try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* gone */ }
            }],
            [canvas, "pointermove", e => {
                if (!this.dragFrom) return;
                this.scene.cam.drag((e.clientX - this.dragFrom[0]) / Math.max(1, canvas.clientWidth), (e.clientY - this.dragFrom[1]) / Math.max(1, canvas.clientHeight));
                this.dragFrom = [e.clientX, e.clientY];
            }],
            [canvas, "pointerup", () => { if (this.dragFrom) { this.dragFrom = null; this.keepCamera(); } }],
            [canvas, "pointercancel", () => { this.dragFrom = null; }],
            [canvas, "contextmenu", e => e.preventDefault()],  // (the window drags with the right button)
        ];
        for (const [el, ev, fn, opts] of this.listeners) el.addEventListener(ev, fn, opts);
    }

    // the profile's "the camera's zoom the other way round" (the window's invert_zoom, kept in prefs as the window
    // keeps it; a page's own switch may keep it as zoom_invert or wheel_invert)
    zoomInverted() {
        const P = this.app.state.prefs || {};
        for (const k of ["invert_zoom", "zoom_invert", "wheel_invert"]) if (k in P) return !!P[k];
        return !!this.app.state.invertZoom;
    }

    // a learner's camera kept in their profile, in the window's format (rw_camera.GameCamera.settings)
    keepCamera() {
        if (this.app.keepPrefs) this.app.keepPrefs({camera: this.scene.cam.settings()});
    }

    // zoom the view in use by a factor (under 1: in); the orbiting views (the whole arena, following a robot) move
    // Babylon's camera in and out
    zoomBy(factor) {
        const sc = this.scene;
        if (RIG_MODES.includes(sc.mode)) { sc.cam.wheel(factor); this.keepCamera(); }
        else if (sc.camera) sc.camera.radius = Math.max(2, Math.min(400, sc.camera.radius * factor));
    }

    // + and - (dir -1 zooms in, 1 out; repeat: the key held down), as the window's keys: 0.8 and 1.25 a press, 0.9
    // and 1.11 a repeat. (The keys aren't turned round by invert_zoom: only the wheel is, as in the window)
    zoom(dir, repeat = false) {
        this.zoomBy(dir < 0 ? (repeat ? 0.9 : 0.8) : (repeat ? 1.11 : 1.25));
    }

    // Q and E: swing the view round (the window: 20 degrees a press, Q +20, E -20)
    turnCamera(degrees) {
        const sc = this.scene;
        if (RIG_MODES.includes(sc.mode)) { sc.cam.turn(degrees); this.keepCamera(); }
        else if (sc.camera) sc.camera.alpha += degrees * Math.PI / 180;
    }

    // a sideways scroll: the view moved sideways (metres, right positive), this view only
    panCamera(metres) {
        if (!RIG_MODES.includes(this.scene.mode) || !metres) return;
        this.scene.cam.pan(metres);
        this.keepCamera();
    }

    // Home: this view back as it comes (its swing, tilt and sideways move; its zoom stays); the whole arena's view
    // back over the arena
    resetCamera() {
        const sc = this.scene;
        if (RIG_MODES.includes(sc.mode)) { sc.cam.resetView(); this.keepCamera(); }
        else sc.setMode(sc.mode, sc.follow);
    }

    // O: the full arena view (the window's cam.set_mode("arena"))
    fullArena() {
        this.rigMode = "arena";
        this.scene.setMode("arena", this.myId());
        this.keepCamera();
        this.app.updatePills();
    }

    // [ and ]: watch the next arena (lab_client.watch_arena), as the Camera tab's buttons do; back on your own arena
    // the view follows yours again (Mine)
    watchArena(delta) {
        const n = (this.app.state.roster || {}).arenas || 1;
        if (n < 2) return;
        const next = (((this.watched() + delta) % n) + n) % n, mine = this.myArena();
        this.watch = next === mine ? null : next;
        this.renderBoard();
        this.app.renderPanel();
        this.app.toast(`Watching arena ${next + 1}${next === mine ? "  (yours)" : ""}`, false, 2000);
    }

    myArena() {  // the arena our own robot is in, or null
        const id = this.myId(), r = id !== null ? ((this.app.state.roster || {}).robots || []).find(x => x.id === id) : null;
        return r ? r.arena : null;
    }

    // B, or the board's Hide/Show button (lab_client.toggle_hud)
    toggleBoard() {
        this.boardSmall = !this.boardSmall;
        try { localStorage.setItem("hud_small", this.boardSmall ? "1" : "0"); } catch (e) { /* private window */ }
        this.renderBoard();
    }

    // garage.js's hook (CHANGE 143): the robot being built, turning on its pedestal in slot (the window's preview).
    // A computer that can't make a second drawing has no preview, and the garage is as it was
    garagePreview(slot, design) {
        if (!slot || !design || typeof BABYLON === "undefined") return;
        if (!this.preview || this.preview.gone) {
            try { this.preview = new RobotPreview(this.app.tier); } catch (e) { console.warn("No robot preview:", e); this.preview = null; return; }
        }
        this.preview.attach(slot, design);
    }

    learnerTabs() { return [["camera", "Camera"]]; }

    controlSent(msg, now) { this.ahead.control(now / 1000, msg.throttle, msg.steer); }  // (play.js: CHANGE 166)

    message(m) {
        if (m.type === "roster") {
            this.scene.setSetup({hazards: m.hazards || {}, user_mods: m.user_mods || {}, look: m.look || {}});
            this.scene.setRobots(m.robots || []);
            this.drive = new Map((m.robots || []).filter(r => r.drive).map(r => [r.id, r.drive]));
            const id = this.myId();
            if (this.followMine && id !== null) this.scene.setMode(this.rigMode || "third", id);
            this.renderBoard();
            return true;
        }
        if (m.type === "state") {
            m.sm = m.sm >>> 0;
            this.app.pushSnap(m, performance.now());
            this.ahead.snapshot(m.sm / 1000, ((this.arenaOf(m) || {}).robots) || []);  // (CHANGE 166)
            const id = this.myId();  // (the server's acks: how long our key presses take to show)
            if (id !== null && m.acks && m.acks[id] !== undefined && this.app.ctrl) this.app.ctrl.ack(m.acks[id], performance.now());
            this.last = m;
            const arena = this.arenaOf(m);
            if (arena && arena.fx) {  // sparks, debris and the camera shake (rw_fx), and saws' and chainsaws' spark showers
                for (const [p, dmg, kind] of arena.fx.impacts || []) this.scene.impact(p, dmg, kind);
                for (const [p, dir, n] of arena.fx.streams || []) this.scene.stream(p, dir, n);
            }
            if (arena && arena.fx) this.impacts = (this.impacts || []).concat(arena.fx.impacts || []);  // (heard next frame)
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
        const S = this.app.state, roster = S.roster;
        const mine = roster && roster.mine ? roster.mine[S.name] : null;
        const r = mine !== null && mine !== undefined && roster ? (roster.robots || []).find(x => x.id === mine) : null;
        return r ? r.arena : 0;
    }

    arenaOf(snap) {
        const i = this.watched();
        return (snap.arenas || []).find(a => a.i === i) || (snap.arenas || [])[0] || null;
    }

    frame(now, dt) {
        const pair = this.app.samplePair(now);
        if (!pair) { this.scene.frame(null, dt, now / 1000); return; }
        const A = this.arenaOf(pair.a), B = pair.b ? this.arenaOf(pair.b) : null, f = pair.f;
        if (!A) { this.scene.frame(null, dt, now / 1000); return; }
        const byId = B ? new Map(B.robots.map(r => [r.id, r])) : new Map();
        let robots = A.robots.map(r => {
            const n = byId.get(r.id);
            if (!n) return r;
            return {...n, pos: r.pos.map((v, i) => lerp(v, n.pos[i], f)), quat: slerpQ(r.quat, n.quat, f),
                    wpos: r.wpos.map((v, i) => lerp(v, n.wpos[i], f)), wquat: slerpQ(r.wquat, n.wquat, f),
                    speed: lerp(r.speed || 0, n.speed || 0, f)};
        });
        const S = this.app.state;
        if (S.gfx && S.gfx.ahead && S.offset !== null) {  // (CHANGE 166: drawn where they are now)
            robots = this.ahead.adjust(robots, now / 1000, (now - S.offset) / 1000, (S.pingMs || 0) / 1000, this.myId(),
                                       this.drive, dt);
        }
        let hz = A.hz;
        if (B && B.hz && A.hz) {
            hz = {...B.hz, pit: lerp(A.hz.pit ?? 0, B.hz.pit ?? 0, f), spikes: lerp(A.hz.spikes || 0, B.hz.spikes || 0, f),
                  flames: lerp(A.hz.flames || 0, B.hz.flames || 0, f),
                  saws: (A.hz.saws || []).map((v, i) => lerp(v, (B.hz.saws || [])[i] ?? v, f)),
                  ff: A.hz.ff && B.hz.ff ? slerpQ(A.hz.ff, B.hz.ff, f) : B.hz.ff};
        }
        const top = pair.b || pair.a;
        this.scene.frame({robots, hz, intro: top.intro, rd: top.rd}, dt, now / 1000);
        if (this.app.sound && this.last) {  // hits, spinners, saws, the motor, the countdown (sound.js, lab_client's sounds)
            const keys = this.app.keys;
            this.app.sound.robotFrame(this.arenaOf(this.last), {intro: this.last.intro, paused: this.last.paused}, this.impacts || [], this.myId(),
                {listener: Sound.listenerFrom(this.scene.camera), weapons: Sound.robotWeapons(((this.app.state.roster || {}).robots)),
                 driving: !!keys && keys.is("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"), now: now / 1000});
            this.impacts = [];
        }
    }

    renderBoard() {
        const S = this.app.state, m = this.last, esc = this.app.esc;
        if (!m) return;
        const arena = this.arenaOf(m);
        const roster = S.roster || {};
        const byId = new Map((roster.robots || []).map(r => [r.id, r]));
        const n = roster.arenas || 1;
        const myId = this.myId();
        // (the window's health bars: the robot's name and owner, YOU, the bar in its colour, the weapon and hits;
        // Resident Robots last)
        const list = [...((arena && arena.robots) || [])].sort((a, b) => ((byId.get(a.id) || {}).owner === "Resident Robot") - ((byId.get(b.id) || {}).owner === "Resident Robot"));
        const rows = list.map(r => {
            const info = byId.get(r.id) || {design: {}};
            const house = info.owner === "Resident Robot";
            const c = (info.design.colour || [128, 128, 128]).map(v => Math.round(v));
            const pc = Math.max(0, Math.min(100, Math.round(100 * r.hp / (r.max || 1))));
            const weapon = info.design.weapon || HOUSE_WEAPONS[info.design.model] || "wedge";
            const wstate = ["spinner", "drum", "vdisc"].includes(weapon)
                ? (r.on && r.rpm ? `${Math.round(r.rpm)} rpm${r.energy !== undefined ? `, ${Math.round(r.energy)} J` : ""}` : r.on ? "on" : "off")  // (its energy: CHANGE 143)
                : (r.on || r.act ? "firing" : "ready");
            let status = r.ko ? (house ? "OUT OF ACTION" : "KNOCKED OUT") : `weapon ${wstate}${r.hits ? ` · ${r.hits} hits` : ""}`;
            if (m.rd && !r.ko && r.pt) {  // real damage: armour, weapon and the four wheels' own bars (lab_client.hud_parts)
                const pt = r.pt, bar = (v, w) => `<span style="display:inline-block;width:${w}px;height:6px;background:#333336;margin-right:3px;vertical-align:middle">` +
                    `<i style="display:block;height:100%;width:${Math.max(0, Math.min(100, v))}%;background:${v > 60 ? "#4dd959" : v > 30 ? "#ffcc26" : "#ff4033"}"></i></span>`;
                status = `<small>Armour</small> ${bar(pt[1], 34)}<small>Weapon</small> ${bar(pt[2], 34)}<small>Wheels</small> ${[pt[4], pt[3], pt[6], pt[5]].map(v => bar(v, 15)).join("")}`;
            }
            return `<div data-id="${r.id}" class="${r.id === myId ? "watched" : ""}"><span class="sw" style="background:rgb(${c.join(",")})"></span><span>${esc(info.design.name || "?")}<small> ${esc(info.owner || "")}${r.id === myId ? " (YOU)" : ""}</small></span>` +
                   `<span class="hpbar"><i style="width:${pc}%;background:rgb(${c.join(",")})"></i></span>` +
                   `<span class="lap">${status}</span></div>`;
        });
        // (the window's title bar: ROBOT LAB, TEACHER: and the name, and Hide or Show; small is just the title)
        const teacher = S.role !== "learner";
        const head = `<div class="bhead"><b class="${teacher ? "teacher" : ""}">ROBOT LAB · ${teacher ? "TEACHER: " : ""}${esc(S.name || "")}</b>` +
                     `<button id="rb-small" title="B does the same">${this.boardSmall ? "Show" : "Hide"}</button></div>`;
        $("places").innerHTML = head + (this.boardSmall ? "" : (n > 1 ? `<div><small>ARENA ${this.watched() + 1} of ${n}</small></div>` : "") + (rows.join("") || "<div><small>No robots yet</small></div>"));
        $("rb-small").onpointerdown = () => this.toggleBoard();  // (not onclick: the board is redrawn 30 times a second)
        $("places").querySelectorAll("div[data-id]").forEach(el => el.onclick = () => {
            const id = Number(el.dataset.id);
            this.scene.setMode(this.scene.mode === "follow" && this.scene.follow === id ? "overview" : "follow", id);
            this.app.updatePills();
        });
        let big = "";
        if (m.intro !== null && m.intro !== undefined) {
            const t = m.intro;
            // (the window's intro: the arena's name, who is fighting, then 3, 2, 1; nobody moves until ACTIVATE!)
            const fighting = ((arena && arena.robots) || []).map(r => byId.get(r.id)).filter(x => x && x.owner !== "Resident Robot").map(x => x.design.name || "?");
            big = t < 2.5 ? esc((roster.look || {}).name || "ROBOT LAB") : t < 5 ? `${fighting.map(esc).join("  v  ")}<div class="sub">Get ready: nobody can move or fire until ACTIVATE!</div>`
                : String(Math.max(1, 3 - Math.floor(t - 5)));
            this.activateAt = performance.now();
        } else if (this.activateAt && performance.now() - this.activateAt < 1200) {
            big = "ACTIVATE!";
        } else if (arena && arena.winner) {  // (the window's banner: the teacher is told how to go again, CHANGE 143)
            big = esc(arena.winner) + (teacher ? `<div class="sub">Press Restart in Controls</div>` : "");
        } else if (m.paused) {
            big = "PAUSED";
        }
        $("countdown").innerHTML = big;
        const tl = arena && arena.time_left !== null && arena.time_left !== undefined ? arena.time_left : m.time_left;
        const clock = tl !== null && tl !== undefined ? `${Math.floor(tl / 60)}:${String(Math.floor(tl % 60)).padStart(2, "0")}` : "";
        const T = S.tournament;  // (the window's top line: the tournament's title, CHANGE 143)
        $("phase").textContent = (m.paused ? "PAUSED · " : "") + (T ? `${T.title || "TOURNAMENT"} · ` : "") +
                                 (m.practice ? "PRACTICE (no damage)" : `BATTLE ${clock}`) + (m.rd ? " · real damage" : "");
    }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${L.mode === "battle" ? "battle" : "practice"} · ${L.arenas || 1} arena${(L.arenas || 1) > 1 ? "s" : ""}` : "";
    }

    cameraPill() {
        const sc = this.scene;
        if (RIG_NAMES[sc.mode]) return `Camera: ${RIG_NAMES[sc.mode]} (V to change, wheel or +/- to zoom, right-drag or Q/E to turn, Home back)`;
        return sc.mode === "follow" ? "Camera: following a robot (drag to orbit)" : "Camera: the whole arena (drag to orbit, wheel to zoom)";
    }

    tabs() { return [["controls", "Controls"], ["camera", "Camera"]]; }

    // the knockout's first round as picked so far (lab_client.knockout_lineups): one pair an arena, empty places
    // filled in order from the robots not yet in a line-up
    knockoutLineups(entrants) {
        const rows = Math.min(6, Math.floor(entrants.length / 2));
        const picked = ((this.lineups || []).map(row => row.map(n => entrants.includes(n) ? n : null)).concat(Array.from({length: rows}, () => [null, null]))).slice(0, rows);
        const used = new Set(picked.flat().filter(Boolean));
        const spare = entrants.filter(n => !used.has(n));
        for (const row of picked) for (const k of [0, 1]) if (row[k] === null && spare.length) row[k] = spare.shift();
        this.lineups = picked;
        return picked;
    }

    learnerHead() { return ["Robot", "Arena"]; }
    learnerCells(p) {
        const S = this.app.state, roster = S.roster || {};
        const id = roster.mine ? roster.mine[p.name] : null;
        const r = (roster.robots || []).find(x => x.id === id);
        if (p.role === "computer")  // (CHANGE 140: the arena it is in, or every arena)
            return [this.app.esc((p.design && p.design.name) || ""), !p.in_arena ? "" : p.in === null || p.in === undefined ? "every" : p.in + 1];
        return [this.app.esc((p.design && p.design.name) || ""), r ? r.arena + 1 : ""];
    }

    // CHANGE 142: every robot in the class for the Controls tab's Arenas rows: the teacher's own (while it is in the
    // arena; its place is "Teacher", as the window's), each learner's, each computer robot in use. k: the rows' ids
    arenaRows() {
        const S = this.app.state, L = S.lesson || {}, roster = S.roster || {}, cls = S.classList || [];
        const now = name => { const id = roster.mine ? roster.mine[name] : null, r = (roster.robots || []).find(x => x.id === id); return r ? r.arena : null; };
        const key = s => String(s).replace(/[^A-Za-z0-9]/g, ch => "_" + ch.charCodeAt(0).toString(16));
        const me = cls.find(p => p.role === "teacher");
        return [...(L.teacher_robot ? [{k: "me", who: "Teacher", place: "Teacher", design: (me && me.design) || S.myDesign || {}, now: now(S.name)}] : []),
                ...cls.filter(p => p.role === "learner").map(p => ({k: "l-" + key(p.name), who: p.name, place: p.name, design: p.design || {}, now: now(p.name)})),
                ...cls.filter(p => p.role === "computer" && p.n <= (L.cpu_robots || 0)).map(c => ({k: "c" + c.n, who: `Computer ${c.n}`, cpu: c, design: c.design || {},
                                                                                              now: c.in_arena ? c.in : null}))];
    }

    // a name typed in an Arenas row (Enter or leaving the box): the teacher's own robot as their garage builds it,
    // a learner's as the Learner view's REBUILD FOR, a computer robot's as its own garage; the rest of the design
    // as it is. Held to what the server takes (letters, numbers and spaces, 16 at most)
    rename(r, el) {
        const app = this.app;
        if (!r) return;
        const name = Array.from(el.value.replace(/[^A-Za-z0-9 ]/g, "")).slice(0, 16).join("").trim();
        if (name === (r.design.name || "")) { el.value = name; return; }
        if (!name) { el.value = el.dataset.v; app.toast("A robot's name needs letters or numbers."); return; }
        el.value = el.dataset.v = name;
        this.renames = Object.assign({}, this.renames, {[r.k]: [name, Date.now() + 3000]});  // (shown until the server's answer)
        const d = Object.assign({}, r.design, {name});
        if (r.cpu) app.send({type: "cpu_robot", n: r.cpu.n, design: d});
        else if (r.k === "me") app.send({type: "design", design: d, code: false});
        else app.send({type: "design_for", learner: r.who, design: d});
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, send = app.send, esc = app.esc;
        const lessonSend = patch => send({type: "lesson", lesson: patch});
        if (tab === "controls") {
            if (!L) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return true; }
            const T = S.tournament;
            const people = (S.classList || []).filter(p => p.role === "learner").map(p => p.name).concat(L.teacher_robot ? [S.name] : []);
            const arenas = L.arenas || 1;
            const rows = this.knockoutLineups(people);
            // (CHANGE 142: each robot's row: its name, renamed here, and its arena; ids that stay the same, so the
            // panel's redraw keeps a box being typed in)
            const robots = this.arenaRows(), pend = this.renames || {};
            const nameOf = r => {  // (a name just sent, until the server has it or has said no)
                const p = pend[r.k], now = r.design.name || "";
                if (p && (p[0] === now || p[1] < Date.now())) delete pend[r.k];
                return pend[r.k] ? p[0] : now;
            };
            const arenaHtml = robots.map(r => {
                const v = r.cpu ? r.cpu.arena : (L.places || {})[r.place], set = Number.isInteger(v) ? v : null;
                const pick = arenas > 1 ? `<select id="rb-at-${r.k}" data-robot="${r.k}" data-v="${set ?? ""}"><option value="">${r.cpu ? "every arena" : "any"}</option>${
                    Array.from({length: Math.max(arenas, (set ?? -1) + 1)}, (_, k) => `<option value="${k}" ${set === k ? "selected" : ""}>arena ${k + 1}</option>`).join("")}</select>` +
                    (Number.isInteger(r.now) && r.now !== set ? `<small class="note">in arena ${r.now + 1}</small>` : "") : "";
                return `<div class="row"><label>${esc(r.who)}</label><input id="rb-nm-${r.k}" data-robot="${r.k}" data-v="${esc(nameOf(r))}" value="${esc(nameOf(r))}"
                          maxlength="16" style="width:9em" title="Its name: type a new one, then Enter">${pick}</div>`;
            }).join("");
            const html = `
              ${app.missionRow()}
              <h2>The match</h2>
              <div class="row"><button data-mode="practice" class="${L.mode !== "battle" ? "on" : ""}">Practice</button>
                <button data-mode="battle" class="${L.mode === "battle" ? "on" : ""}">Battle</button>
                <button id="rb-restart" class="go">RESTART</button>
                <button id="rb-pause" class="${this.last && this.last.paused ? "on" : ""}">${this.last && this.last.paused ? "RESUME" : "PAUSE"}</button></div>
              <div class="note">Practice: no damage, knocked-out robots come back. Battle: RESTART counts down 8 seconds, then ACTIVATE!</div>
              <div class="row"><label>Battle time</label><select id="rb-time">${[30, 60, 90, 120, 150, 180, 210, 240, 270, 300].map(t => `<option value="${t}" ${t === L.time_limit ? "selected" : ""}>${t} s</option>`).join("")}</select></div>
              <div class="row"><label>Computer robots</label><select id="rb-cpu">${[0, 1, 2, 3, 4].map(k => `<option ${k === L.cpu_robots ? "selected" : ""}>${k}</option>`).join("")}</select>
                <select id="rb-level">${LEVELS.map(([k, n]) => `<option value="${k}" ${k === L.cpu_level ? "selected" : ""}>${n}</option>`).join("")}</select></div>
              <div class="note">Each one is yours to set up in Learners (Computer 1 to ${(S.classList || []).filter(p => p.role === "computer").length || 4}): its robot, its brain and its arena (its name and arena are under Arenas too).</div>
              ${L.cpu_level === "empty" ? `<div class="row"><label class="filebtn">Upload the demo brain (.py)<input id="rb-demo" type="file" accept=".py,text/plain" hidden></label></div>` : ""}
              <div class="row"><label>My robot</label><button id="rb-mine" class="${L.teacher_robot ? "on" : ""}">${L.teacher_robot ? "In the arena" : "Not in"}</button></div>
              <div class="row"><label>Designs</label><button id="rb-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              <div class="row"><label>Damage</label><button id="rb-real" class="${L.real_damage ? "on" : ""}">${L.real_damage ? "Real damage: parts come off" : "Simple health"}</button></div>
              <div class="row"><label>Drop zone</label><button id="rb-pit-open">Open it now</button><button id="rb-pit-close">Close it now</button></div>
              ${(L.user_mods || {}).flame_pit ? `<div class="row"><label>Flame pit</label><select id="rb-flame">${[10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map(c => `<option value="${c}" ${c === L.flame_pit_cm ? "selected" : ""}>${c} cm</option>`).join("")}</select></div>` : ""}
              <h2>Arenas</h2>
              <div class="row"><label>How many</label><select id="rb-arenas">${[1, 2, 3, 4, 5, 6].map(k => `<option ${k === arenas ? "selected" : ""}>${k}</option>`).join("")}</select>
                <button id="rb-turns">Take turns again</button></div>
              ${arenaHtml}
              ${robots.length ? `<div class="note">${arenas > 1 ? "Any: the arenas take turns. A computer robot in every arena is the same opponent for everyone. Save settings keeps who is where for this mission."
                  : "One arena: everyone is in arena 1."} A name: type it, then Enter.</div>` : ""}
              <h2>Tournament</h2>
              ${T ? `<div class="row"><button id="rb-tstop" class="stop">${T.kind === "knockout" ? "Stop: knockout" : "Stop: winner stays on"}</button></div>
                ${T.kind === "knockout" ? `<p><b class="${T.champion ? "ok" : ""}">${esc(T.title || "")}</b></p>
                    ${(T.rounds || []).map((rd, n) => rd.map(([a, b, w], i) => `<div class="${n === T.rounds.length - 1 ? "" : "note"} ${w ? "ok" : ""}">Round ${n + 1}${rd.length > 1 ? ` arena ${i + 1}` : ""}: ${esc(a)} v ${esc(b)}${w ? ` - ${esc(w)} through` : ""}</div>`).join("")).join("")}
                    ${(T.queue || []).length ? `<div class="note">Waiting for the next round: ${T.queue.map(esc).join(", ")}</div>` : ""}`
                  : `${(T.live || []).map(([a, b], i) => `<div>Arena ${i + 1}: ${esc(a || "-")} v ${esc(b || "-")}</div>`).join("")}
                    <div class="note">Waiting: ${(T.queue || []).map(esc).join(", ") || "nobody"}</div>`}
                <div class="note">Battles: ${T.played || 0}</div>
                ${(T.table || []).length ? `<table>${T.table.slice(0, 12).map(([n, w, st]) => `<tr><td class="${w ? "ok" : ""}">${esc(n)}</td><td>${w} win${w !== 1 ? "s" : ""}${st > 1 ? ` · ${st} in a row` : ""}</td></tr>`).join("")}</table>` : ""}`
                : `<div class="row"><button id="rb-stays" class="go">Winner stays on</button></div>
                   <div class="note">Two arenas live; the loser queues, the next challenger comes in, the rest watch. Battle on, designs locked.</div>
                   <h3>Knockout: pick round 1 (click a name to change it); the winners meet next round</h3>
                   ${rows.length ? rows.map(([a, b], i) => `<div class="row"><label>Arena ${i + 1}</label><button data-lineup="${i},0">${esc(a || "-")}</button> v <button data-lineup="${i},1">${esc(b || "-")}</button></div>`).join("") +
                       `<div class="row"><button id="rb-knock" class="go">START KNOCKOUT</button></div>
                        <div class="note">${(() => { const w = people.filter(n => !rows.some(r => r.includes(n))); return w.length ? `Waiting for round 2: ${w.map(esc).join(", ")}` : "Battle on, designs locked."; })()}</div>`
                     : `<div class="note">Needs at least 2 robots: learners, or your own robot.</div>`}`}
              ${app.restartRow()}`;
            this.drawing = true;  // (a box taken away by the redraw isn't a box left: no rename)
            body.innerHTML = html;
            this.drawing = false;
            app.wireMissionRow(body);
            body.querySelectorAll("button[data-mode]").forEach(b => b.onclick = () => lessonSend({mode: b.dataset.mode}));
            $("rb-restart").onclick = () => send({type: "restart"});
            $("rb-pause").onclick = () => send({type: "pause"});
            $("rb-time").onchange = e => lessonSend({time_limit: Number(e.target.value)});
            $("rb-cpu").onchange = e => lessonSend({cpu_robots: Number(e.target.value)});
            $("rb-level").onchange = e => lessonSend({cpu_level: e.target.value});
            if ($("rb-demo")) $("rb-demo").onchange = async e => { const f = e.target.files[0]; if (f) send({type: "cpu_brain", source: await f.text()}); };
            $("rb-mine").onclick = () => lessonSend({teacher_robot: !L.teacher_robot});
            $("rb-lock").onclick = () => lessonSend({designs_locked: !L.designs_locked});
            $("rb-real").onclick = () => lessonSend({real_damage: !L.real_damage});
            $("rb-pit-open").onclick = () => send({type: "pit", open: true});
            $("rb-pit-close").onclick = () => send({type: "pit", open: false});
            if ($("rb-flame")) $("rb-flame").onchange = e => lessonSend({flame_pit_cm: Number(e.target.value)});
            $("rb-arenas").onchange = e => lessonSend({arenas: Number(e.target.value)});
            $("rb-turns").onclick = () => lessonSend({places: Object.fromEntries(Object.keys(L.places || {}).map(n => [n, null]))});
            const robotOf = el => robots.find(r => r.k === el.dataset.robot);
            body.querySelectorAll("input[data-robot]").forEach(el => {
                el.onkeydown = e => { if (e.key === "Enter") el.blur(); };
                el.onblur = () => { if (!this.drawing) this.rename(robotOf(el), el); };
            });
            body.querySelectorAll("select[data-robot]").forEach(sel => sel.onchange = () => {
                const r = robotOf(sel), v = sel.value === "" ? null : Number(sel.value);
                if (!r) return;
                sel.dataset.v = sel.value;
                if (r.cpu) send({type: "cpu_robot", n: r.cpu.n, arena: v});  // (as its Learners tab sends it)
                else lessonSend({places: {[r.place]: v}});
            });
            // the panel's redraw puts back what each box held; a box or list not in use shows the server's own
            // (a name changed elsewhere, an arena set in Learners) once that is done
            queueMicrotask(() => body.querySelectorAll("[data-robot]").forEach(el => { if (el.isConnected && el !== document.activeElement) el.value = el.dataset.v; }));
            if ($("rb-stays")) $("rb-stays").onclick = () => send({type: "tournament", start: true, kind: "stays", live: 2});
            if ($("rb-knock")) $("rb-knock").onclick = () => send({type: "tournament", start: true, kind: "knockout", lineups: rows});
            body.querySelectorAll("button[data-lineup]").forEach(b => b.onclick = () => {  // (the next robot not in a line-up)
                const [i, k] = b.dataset.lineup.split(",").map(Number);
                const used = new Set(rows.flatMap((row, r) => row.filter((n, j) => n && !(r === i && j === k))));
                const free = people.filter(n => !used.has(n));
                if (free.length) { const here = rows[i][k]; rows[i][k] = free.includes(here) ? free[(free.indexOf(here) + 1) % free.length] : free[0]; }
                app.renderPanel();
            });
            if ($("rb-tstop")) $("rb-tstop").onclick = () => send({type: "tournament", start: false});
            app.wireRestartRow(body);
            return true;
        }
        if (tab === "camera") {
            const sc = this.scene, roster = S.roster || {};
            const n = roster.arenas || 1;
            const here = (roster.robots || []).filter(r => r.arena === this.watched());
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row"><button id="rc-over" class="${sc.mode === "overview" ? "on" : ""}">Whole arena</button></div>
              <h2>Follow a robot</h2>
              <div class="row">${here.map(r => `<button data-follow="${r.id}" class="${sc.mode === "follow" && sc.follow === r.id ? "on" : ""}">${esc(r.design.name || "?")}</button>`).join("") || "<span class='note'>No robots</span>"}</div>
              ${n > 1 ? `<h2>Watch an arena</h2><div class="row">${Array.from({length: n}, (_, k) => `<button data-arena="${k}" class="${this.watched() === k ? "on" : ""}">Arena ${k + 1}</button>`).join("")}
                <button id="rc-auto" class="${this.watch === null ? "on" : ""}">Mine</button></div>` : ""}`;
            $("rc-over").onclick = () => { sc.setMode("overview"); app.updatePills(); app.renderPanel(); };
            body.querySelectorAll("button[data-follow]").forEach(b => b.onclick = () => { sc.setMode("follow", Number(b.dataset.follow)); app.updatePills(); app.renderPanel(); });
            body.querySelectorAll("button[data-arena]").forEach(b => b.onclick = () => { this.watch = Number(b.dataset.arena); this.renderBoard(); app.renderPanel(); });
            if ($("rc-auto")) $("rc-auto").onclick = () => { this.watch = null; this.renderBoard(); app.renderPanel(); };
            return true;
        }
        return false;
    }

    dispose() {
        for (const [el, ev, fn, opts] of this.listeners || []) el.removeEventListener(ev, fn, opts);
        this.listeners = null;
        if (this.boardDrag) { this.boardDrag.release(); this.boardDrag = null; }
        if (this.preview) { this.preview.dispose(); this.preview = null; }
        this.scene.dispose();
        $("places").innerHTML = "";
        $("countdown").textContent = $("phase").textContent = "";
    }
}
