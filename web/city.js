// City Lab in Club Coders Live (CHANGE 201, docs/plans/city-lab.md steps 8a and 8b): the city, its people, cars and
// robots drawn from the class server's snapshots, and a learner (or the teacher, when the teacher is in the city)
// playing on the page as in the window, their own person on foot or the car they drive predicted as the window
// predicts it (city_sim.js: city_sim.py's steps, ported line for line).
//
// The city comes in the welcome as JSON (city_map.City.to_data): CityScene builds it as the window's city_gfx.CityVisual
// does, one mesh a material (the roads and their markings, the pavements and kerbs, the buildings in their colours with
// rows of windows, shop windows and the depot's doors, flat roofs with a parapet and a plant room, the houses' pitched
// roofs, the parks and gardens, the car parks' bays, the yards' yellow lines, trees, lamp posts, the stunt ramps and
// their chevrons, the railing round the city's edge, the quay and the water, the four places' signs), and the jobs as
// city_gfx.JobsVisual has them (the rings at the depot, the rank and the arcade and the race line, the beam over your
// target, the chips spinning on the pavements, the race's checkpoints). The people are Fight Lab's fighters (fighters.js:
// the woman, the man and Robin as the app's skinned models, the built human and robot), the cars Kart Lab's sports cars
// (cars.js), the robots Robot Lab's (CityScene is a RobotScene, as the Missions' scene is), lit as the window lights the
// city (Kart Lab's sky, sun and time of day: day, dusk, night with the headlights and the street lamps glowing). Every
// tier: mesh and lines (the city's edges in the line colour, a grid on the ground on lines), blocks to high, ultra (the
// sky with clouds, the haze, the glow, skid marks and sparks, the detailed cars near the camera, the smooth fighters and
// robots).
//
// The binary snapshots (wire.js's CITY_FIELDS: one record for people, cars and robots, what each is from its id) are
// blended two behind the newest (interp.js), the jobs message gives the words (the HUD: hud.js's CityHud, the cash, the
// job, the arrow, the minimap), the roster the designs. Your own person, or your car, is stepped on each 1/60 s tick
// with your keys (play.js's city controls: the keyboard, a game pad, a phone's touch controls) and sent as the 18-byte
// input; a snapshot says which input the server applied, the prediction is checked against it and put right if it
// was wrong (predict.js), eased in the picture. Getting in and out, bumps, punches landing, the jobs and the pay are
// the server's: they show when its snapshot says so.

/* global BABYLON */

import {TIERS, v3} from "./base3d.js";
import {RobotScene} from "./robot.js";
import {RobotFX, hprQuat, qrot, robotShapes, loadRobotModels, robotModelsData} from "./robotfx.js";
import {AfterFx, makeSky, Skids, Sparks, loadCars, carData} from "./kartfx.js";
import {loadFightModels, fightModelsData} from "./fightfx.js";
import {LOOK, Geo} from "./scene.js";
import {CarParts, Smoke, TIME_LOOKS, HEADLIGHTS, PUFFS} from "./cars.js";
import {FighterParts} from "./fighters.js";
import {CITY_FIELDS, KIND_SNAPSHOT, kindOf as frameKind, unpackSnapshot} from "./wire.js";
import * as sim from "./city_sim.js";
import {Predictor, InputLog, ErrorSmoother, LeadController, quantiseInput, packInput, seqDiff, SEQ_MASK} from "./predict.js";
import {CityHud} from "./hud.js";
import {LEARNER_TABS} from "./learner.js";
import {TEACHER_TABS} from "./teacher.js";

const $ = id => document.getElementById(id);
const DEG = Math.PI / 180;
const KERB_H = sim.KERB_H;
const FLOOR = 3.2, WIN_EVERY = 2.6, SHOP_GLASS = 2.4, PITCH = 2.4;  // (city_gfx: a storey, a window's spacing, a shop's glass, a roof's rise)
const RIDE = 0.12;  // (lab_sim.RIDE: a robot's body above the ground)
const DRAW = {person: 110, car: 160, robot: 90};  // (city_client: the metres from the camera each kind is drawn within)
export const GET_IN_REACH = sim.ENTER_REACH + sim.CAR_R;
export const PLACE_SIGNS = {depot: "DEPOT", garage: "GARAGE", rank: "TAXI RANK", arcade: "ARCADE"};
const PLACE_COLOURS = {depot: [0.95, 0.7, 0.15], garage: [0.3, 0.8, 1.0], rank: [1.0, 0.85, 0.1], arcade: [1.0, 0.3, 0.9]};
// (city_gfx.JOB_COLOURS and MARKER_WORDS: the jobs' rings, the beam, the arrow, the chips)
export const JOB_COLOURS = {depot: [1.0, 0.72, 0.15], rank: [1.0, 0.9, 0.1], arcade: [1.0, 0.3, 0.9], race: [0.3, 0.9, 1.0],
                            delivery: [1.0, 0.72, 0.15], taxi: [1.0, 0.9, 0.1], roundup: [1.0, 0.3, 0.3], chip: [0.3, 1.0, 0.55]};
const MARKER_WORDS = {depot: "DELIVERIES", rank: "TAXI (in a car)", arcade: "CHIPS PAID  /  ROUND-UP", race: "STREET RACE (stop here)"};
// the city's materials (city_gfx.MATERIALS): texture set, colour, roughness, metal; and how many times a metre each
// texture repeats (the window's tile for that mesh)
const MATERIALS = {
    road: ["tarmac", [0.82, 0.82, 0.86], 0.9, 0.0, 0.125], lot: ["asphalt", [0.78, 0.78, 0.8], 0.9, 0.0, 0.25],
    pave: ["concrete", [0.92, 0.9, 0.86], 0.85, 0.0, 0.25], kerb: ["concrete", [0.75, 0.74, 0.72], 0.8, 0.0, 1.0],
    grass: ["grass", [0.95, 1.0, 0.9], 0.95, 0.0, 0.2], water: ["water", [0.55, 0.7, 0.85], 0.15, 0.0, 0.05],
    walls: ["render", [1.0, 1.0, 1.0], 0.85, 0.0, 0.25], glass: ["", [0.16, 0.2, 0.26], 0.08, 0.6, 1],
    frames: ["", [0.85, 0.85, 0.82], 0.6, 0.0, 1], roof: ["concrete", [0.55, 0.55, 0.57], 0.9, 0.0, 0.25],
    tiles: ["", [0.55, 0.24, 0.18], 0.8, 0.0, 1], paint: ["", [0.95, 0.95, 0.92], 0.6, 0.0, 1],
    yellow: ["", [0.98, 0.78, 0.1], 0.6, 0.0, 1], steel: ["steel", [0.55, 0.57, 0.6], 0.45, 0.8, 1.0],
    lamp: ["", [1.0, 0.95, 0.8], 0.4, 0.0, 1], bark: ["bark", [0.9, 0.85, 0.8], 0.9, 0.0, 1.0],
    leaves: ["foliage", [0.75, 0.95, 0.7], 0.9, 0.0, 1.0], ramp: ["concrete", [0.85, 0.7, 0.3], 0.8, 0.0, 0.25],
    boards: ["", [0.12, 0.12, 0.16], 0.7, 0.0, 1],
};
const COLOURED = new Set(["walls", "lot", "pave", "boards"]);  // (a colour per vertex: every building its own paint)
const LAMP_GLOW = [6.0, 5.4, 4.0];  // (the street lamps' heads at dusk and night: lit pictures, not lights)
const FOOT_VIEWS = ["behind", "shoulder", "above"], CAR_VIEWS = ["chase", "hood"];
const VIEW_NAMES = {behind: "Behind", shoulder: "Over the shoulder", above: "From above", chase: "Chase", hood: "Bonnet",
                    city: "The whole city"};

const wrapDeg = d => ((d + 180) % 360 + 360) % 360 - 180;
const rgb01 = c => (c && c.length >= 3 ? c.slice(0, 3).map(v => Math.max(0, Math.min(1, v / 255))) : [0.7, 0.7, 0.7]);

// how far above the road a thing standing at (x, y) is drawn: on a block, a kerb's height (city_gfx.ground_lift)
function groundLift(city, x, y) {
    return city.blockIndex(x, y) !== null ? KERB_H : 0.0;
}

// a City Lab design as Fight Lab's (city_gfx.fighter_design: the look is its body, the colour its colour)
function fighterDesign(d) {
    const body = sim.LOOKS.includes(d.look) ? d.look : "woman";
    return {name: d.name || "Driver", body, colour: d.colour || [200, 120, 40], fighting_style: "kickboxer", settings: {size: 100}};
}

// a person's move as Fight Lab's animation and its progress (city_gfx.PersonVisual.anim)
function personAnim(p, stride, t) {
    const move = p.move, mp = p.mp;
    if (move === sim.MOVE_PUNCH) return ["punch", 3.0 * mp / sim.MOVE_TICKS[sim.MOVE_PUNCH]];
    if (move === sim.MOVE_KICK) return ["kick", 3.0 * mp / sim.MOVE_TICKS[sim.MOVE_KICK]];
    if (move === sim.MOVE_BLOCK) return ["block", 0.0];
    if (move === sim.MOVE_DOWN) return ["knockdown", Math.min(1.0, mp / 40.0)];
    if (move === sim.MOVE_GETUP) return ["getup", Math.min(1.0, mp / 40.0)];
    if (move === sim.MOVE_HURT) return ["hitstun", Math.min(1.0, mp / sim.MOVE_TICKS[sim.MOVE_HURT])];
    if (p.flags & sim.FLAG_AIR) return ["jump", 0.5];
    if (p.v > 0.3) return ["walk_f", stride];
    return ["idle", t];
}

// the city's look: Kart Lab's lights (city_gfx.init is kart_gfx.init), a fresh copy for each scene
function cityLook() {
    const look = JSON.parse(JSON.stringify(LOOK));
    look.radius = 120;
    look.target = [0, 0, 0];
    return look;
}

// ---------- building the city (city_gfx.CityVisual's helpers, in game co-ordinates) ----------
function quad(g, a, b, c, d, n, colour = null) {
    if (colour && g.col) g.colour = [...colour, 1];
    g.quad([a, b, c, d], n);
}

function wall(g, x0, y0, x1, y1, z0, z1, n, colour = null) {
    quad(g, [x0, y0, z0], [x1, y1, z0], [x1, y1, z1], [x0, y0, z1], n, colour);
}

function flat(g, x0, y0, x1, y1, z, colour = null, n = [0, 0, 1]) {
    quad(g, [x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z], n, colour);
}

const SIDES = (x0, y0, x1, y1) => [[x0, y0, x1, y0, [0, -1, 0]], [x1, y0, x1, y1, [1, 0, 0]], [x1, y1, x0, y1, [0, 1, 0]], [x0, y1, x0, y0, [-1, 0, 0]]];

function box(g, x0, y0, x1, y1, z0, z1, colour = null, top = true) {
    for (const [ax, ay, bx, by, n] of SIDES(x0, y0, x1, y1)) wall(g, ax, ay, bx, by, z0, z1, n, colour);
    if (top) flat(g, x0, y0, x1, y1, z1, colour);
}

function tube(g, x, y, z0, z1, r, seg = 7) {  // (a post or a trunk: an open cylinder up z)
    for (let i = 0; i < seg; i++) {
        const a0 = 2 * Math.PI * i / seg, a1 = 2 * Math.PI * (i + 1) / seg, am = (a0 + a1) / 2;
        const p = [x + Math.cos(a0) * r, y + Math.sin(a0) * r], q = [x + Math.cos(a1) * r, y + Math.sin(a1) * r];
        quad(g, [p[0], p[1], z0], [q[0], q[1], z0], [q[0], q[1], z1], [p[0], p[1], z1], [Math.cos(am), Math.sin(am), 0]);
    }
}

function ball(g, x, y, z, r, seg = 9, rings = 6) {  // (a tree's crown)
    const pt = (i, j) => {
        const a = 2 * Math.PI * i / seg, b = Math.PI * j / rings - Math.PI / 2;
        return [Math.cos(b) * Math.cos(a), Math.cos(b) * Math.sin(a), Math.sin(b)];
    };
    for (let j = 0; j < rings; j++) {
        for (let i = 0; i < seg; i++) {
            const c = [pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j + 1)];
            const m = c.reduce((s, v) => [s[0] + v[0] / 4, s[1] + v[1] / 4, s[2] + v[2] / 4], [0, 0, 0]);
            const l = Math.hypot(...m) || 1;
            quad(g, ...c.map(v => [x + v[0] * r, y + v[1] * r, z + v[2] * r]), [m[0] / l, m[1] / l, m[2] / l]);
        }
    }
}

function ringGeo(rIn, rOut, seg = 40) {
    const g = new Geo();
    for (let i = 0; i < seg; i++) {
        const a0 = 2 * Math.PI * i / seg, a1 = 2 * Math.PI * (i + 1) / seg;
        const c0 = Math.cos(a0), s0 = Math.sin(a0), c1 = Math.cos(a1), s1 = Math.sin(a1);
        g.quad([[c0 * rIn, s0 * rIn, 0], [c0 * rOut, s0 * rOut, 0], [c1 * rOut, s1 * rOut, 0], [c1 * rIn, s1 * rIn, 0]], [0, 0, 1]);
    }
    return g;
}

function wallGeo(r, h, seg = 32) {
    const g = new Geo();
    for (let i = 0; i < seg; i++) {
        const a0 = 2 * Math.PI * i / seg, a1 = 2 * Math.PI * (i + 1) / seg, am = (a0 + a1) / 2;
        const p0 = [Math.cos(a0) * r, Math.sin(a0) * r], p1 = [Math.cos(a1) * r, Math.sin(a1) * r];
        g.quad([[p0[0], p0[1], 0], [p1[0], p1[1], 0], [p1[0], p1[1], h], [p0[0], p0[1], h]], [Math.cos(am), Math.sin(am), 0]);
    }
    return g;
}

// ---------- the scene ----------
export class CityScene extends RobotScene {
    static TIERS = TIERS;  // (every tier, as the window's: kart_gfx's tiers)
    static ULTRA_FX = {ssao: false, sharpen: true, samples: 4, bloomWeight: 0.25};
    static TIER_TEXT = {lines: "lines: black, the city's outlines in one colour and a grid on the ground (an old vector arcade game).",
                        ultra: "ultra: for a strong graphics card: a sky with clouds and the haze far off, soft shadows, glow, the detailed cars near the camera, the window's smooth fighters and robots, skid marks and sparks."};

    constructor(canvas, tier, engine) {
        super(canvas, tier, engine, cityLook(), true);  // (built when the city comes: setCity)
        this.city = null;
        this.karts = new Map();     // car id -> what cars.js's addKart made
        this.fighters = new Map();  // person id -> what fighters.js's addFighter made
        this.robotKeys = new Map(); // robot id -> its design, as last built
        this.follow = null;         // the car the headlights go to first (yours)
        this.time = "day";
        this.timeLook = TIME_LOOKS.day;
        this.view = {mode: "behind", zoom: 1.0, yaw: 90, pos: null, look: null, carYaw: null, fov: 62, watch: null};
        this.placed = [];
        this.t = 0;
        this.applyTime();
    }

    setCity(city) {
        if (this.city === city && this.scene) return;
        this.city = city;
        this.build();
    }

    // the city at this time of day ("day", "dusk", "night"), as Kart Lab's (kart_gfx.set_time): made again, as the
    // lighting's shaders are made for their number of lights (the headlights' at dusk and night)
    setTime(t) {
        t = TIME_LOOKS[t] ? t : "day";
        if (t === this.time) return;
        this.time = t;
        this.applyTime();
        if (this.city) this.build();
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
        P.spots = T.beam > 0 ? Array.from({length: HEADLIGHTS}, () => ({pos: [0, 0, -100], at: [0, 1, -100], colour: [0, 0, 0], fov: 84, soft: true,
                                                                          att: [1.0, 0.02, 0.008]})) : [];
    }

    render() { if (this.scene) super.render(); }

    drawCalls() { return this.scene ? super.drawCalls() : 0; }

    lineFade() {  // (where the lines fade out into the dark, as the window's black fog: mesh's many lines sooner; far
        // enough that the whole city, seen from above, is still there)
        return this.wire === "all" ? [40, 420] : [80, 520];
    }

    refreshLists() { /* (cars.js asks: Kart Lab's ultra reflection lists; the city has none) */ }

    populate() {
        const scene = this.scene;
        this.ultra = !!(this.settings.ultra && this.lighting);
        // (ultra: the smooth robots and fighters once their files are here, asked for on ultra alone; high's until then)
        this.ultraArena = true;
        this.ultraRobots = false;
        this.ultraFighters = this.ultra && !!fightModelsData();
        if (this.ultra) {
            Promise.all([robotModelsData() ? true : loadRobotModels(), this.ultraFighters ? true : loadFightModels()]).then(([r, f]) => {
                if (this.scene === scene && ((r && r !== true && !this.ultraRobots) || (f && f !== true && !this.ultraFighters))) this.build();
            });
        }
        this.wheelLines = {};
        this.glowLines = {};
        this.lineCount = 0;
        this.lampKit = null;
        this.robots.clear();
        this.robotKeys.clear();
        this.karts.clear();
        this.fighters.clear();
        this.things = new Map();  // id -> {kind, stride, t, hurtAt, wasHurt, tag}
        this.camera.inputs.removeByType("ArcRotateCameraKeyboardMoveInput");  // (the arrows walk: the camera doesn't turn with them)
        if (!this.lit && !this.wire) {  // (blocks: one plain light, dimmed at dusk and night)
            const hemi = scene.getLightByName("sky");
            if (hemi) hemi.intensity = this.timeLook.blocks;
        }
        this.smoke = this.lit ? new Smoke(this, PUFFS * 12) : null;
        this.skids = this.sparks = this.sky = null;
        if (this.ultra) {
            this.sky = makeSky(this);
            this.skids = new Skids(this);
            this.sparks = new Sparks(this);
            this.camera.maxZ = 3000;
        } else this.camera.maxZ = 1600;
        if (!carData("coupe")) loadCars().then(d => {  // (the sports cars: drawn as karts until they are here, then made again)
            if (d && this.scene === scene) for (const id of [...this.karts.keys()]) this.removeKart(id);
        });
        if (!this.city) return;
        const t0 = performance.now();
        this.buildCity();
        this.buildJobs();
        this.lineStats = {segments: this.lineCount, ms: Math.round(performance.now() - t0)};
        this.after = this.ultra ? new AfterFx(this, CityScene.ULTRA_FX) : null;
        this.fx = new RobotFX(this);  // (rw_fx: the sparks where a punch, a kick or a zap lands)
        const cam = this.camera;
        cam.minZ = 0.2;
        cam.lowerRadiusLimit = 0.01;
        cam.upperRadiusLimit = 1200;
        this.view.pos = null;
        if (this.view.mode === "city") this.overview();
    }

    // ---------- the city (city_gfx.CityVisual) ----------
    buildCity() {
        const c = this.city, m = {};
        for (const k of Object.keys(MATERIALS)) m[k] = new Geo(COLOURED.has(k));
        this.ground(m);
        this.blocks(m);
        for (const b of c.buildings) this.building(m, b);
        this.markings(m);
        for (const [x, y, , h] of c.trees) {
            tube(m.bark, x, y, KERB_H, KERB_H + h * 0.5, 0.16);
            ball(m.leaves, x, y, KERB_H + h * 0.62, Math.max(1.2, h * 0.32));
        }
        for (const [x, y] of c.lamps) {
            tube(m.steel, x, y, KERB_H, KERB_H + 5.2, 0.07, 6);
            box(m.steel, x - 0.05, y - 0.05, x + 0.05, y + 0.05, KERB_H + 5.1, KERB_H + 5.25);
            box(m.lamp, x - 0.22, y - 0.22, x + 0.22, y + 0.22, KERB_H + 5.0, KERB_H + 5.12);
        }
        this.ramps(m);
        this.edge(m);
        const meshes = [], casters = [];
        this.cityMeshes = [];
        for (const [key, g] of Object.entries(m)) {
            if (!g.idx.length) continue;
            const [tex, rgb, rough, metal, tile] = MATERIALS[key];
            const mesh = g.mesh("city " + key, this.scene);
            let mat;
            if (key === "lamp") {  // (lit at dusk and night: the lamps glow from their own material)
                mat = this.material("citylamp", rgb, rough, metal, 0, {emission: this.timeLook.lamps ? LAMP_GLOW : [0, 0, 0]});
            } else mat = this.material("city" + key, rgb, rough, metal, 0, {tex: this.wire || this.tier === "blocks" ? "" : tex, tile});
            mat.backFaceCulling = false;
            mesh.material = mat;
            mesh.isPickable = false;
            mesh.freezeWorldMatrix();
            meshes.push(mesh);
            if (["walls", "roof", "tiles", "leaves", "bark", "steel", "ramp", "frames"].includes(key)) casters.push(mesh);
        }
        this.cityMeshes = meshes;
        this.shadowCast(casters);
        const signs = this.signs();
        if (this.wire) this.cityLines(meshes);
        else this.cityMeshes.push(...signs);
    }

    // the ground: the roads' asphalt, the verge, the quay and the water, grass to the horizon
    ground(m) {
        const c = this.city, e = c.edge, water = c.water;
        flat(m.road, c.xmin, c.ymin, c.xmax, c.ymax, 0.0);
        const sides = {south: [e[0], e[1], e[2], c.ymin], north: [e[0], c.ymax, e[2], e[3]], west: [e[0], c.ymin, c.xmin, c.ymax], east: [c.xmax, c.ymin, e[2], c.ymax]};
        for (const [side, [x0, y0, x1, y1]] of Object.entries(sides)) {
            if (side === water) {
                flat(m.pave, x0, y0, x1, y1, 0.02, [0.8, 0.78, 0.74]);
                const far = this.wire ? 60 : 400;  // (the line tiers: the scenery round the city left out, as the window's)
                const w = {south: [x0 - far, y0 - far, x1 + far, y0], north: [x0 - far, y1, x1 + far, y1 + far],
                           west: [x0 - far, y0 - far, x0, y1 + far], east: [x1, y0 - far, x1 + far, y1 + far]}[side];
                flat(m.water, ...w, -1.0);
            } else flat(m.grass, x0, y0, x1, y1, 0.0);
        }
        if (this.wire) return;
        const far = 500;
        for (const [side, r] of [["south", [e[0] - far, e[1] - far, e[2] + far, e[1]]], ["north", [e[0] - far, e[3], e[2] + far, e[3] + far]],
                                 ["west", [e[0] - far, e[1], e[0], e[3]]], ["east", [e[2], e[1], e[2] + far, e[3]]]]) {
            if (side !== water) flat(m.grass, ...r, -0.02);
        }
    }

    // the blocks: the kerb's face, the pavement round the inside, and what is inside (a park, a lot, gardens, a courtyard)
    blocks(m) {
        const pv = sim.PAVE;
        for (const b of this.city.blocks) {
            const {x0, y0, x1, y1, kind} = b;
            for (const [ax, ay, bx, by, n] of SIDES(x0, y0, x1, y1)) wall(m.kerb, ax, ay, bx, by, 0.0, KERB_H, n);
            const tone = [0.95, 0.93, 0.9];
            flat(m.pave, x0, y0, x1, y0 + pv, KERB_H, tone);
            flat(m.pave, x0, y1 - pv, x1, y1, KERB_H, tone);
            flat(m.pave, x0, y0 + pv, x0 + pv, y1 - pv, KERB_H, tone);
            flat(m.pave, x1 - pv, y0 + pv, x1, y1 - pv, KERB_H, tone);
            const ix0 = x0 + pv, iy0 = y0 + pv, ix1 = x1 - pv, iy1 = y1 - pv;
            if (kind === "park") {
                flat(m.grass, ix0, iy0, ix1, iy1, KERB_H);
                const cx = (ix0 + ix1) / 2, cy = (iy0 + iy1) / 2;  // (a path across it each way)
                flat(m.pave, ix0, cy - 1.0, ix1, cy + 1.0, KERB_H + 0.01, [0.85, 0.8, 0.68]);
                flat(m.pave, cx - 1.0, iy0, cx + 1.0, iy1, KERB_H + 0.012, [0.85, 0.8, 0.68]);
            } else if (["carpark", "depot", "garage", "rank", "arcade"].includes(kind)) {
                flat(m.lot, ix0, iy0, ix1, iy1, KERB_H + 0.002, kind === "carpark" ? [0.75, 0.75, 0.78] : [0.8, 0.79, 0.77]);
            } else if (kind === "houses") flat(m.grass, ix0, iy0, ix1, iy1, KERB_H);
            else flat(m.pave, ix0, iy0, ix1, iy1, KERB_H + 0.001, [0.82, 0.8, 0.76]);
        }
    }

    // a building: its walls in its colour with their windows, a flat roof with a parapet (and a plant room on a tall
    // one) or a house's pitched roof
    building(m, b) {
        const h0 = KERB_H, {x0, y0, x1, y1, h: height, kind} = b, top = h0 + height, colour = rgb01(b.c);
        for (const [ax, ay, bx, by, n] of SIDES(x0, y0, x1, y1)) {
            wall(m.walls, ax, ay, bx, by, h0, top, n, colour);
            this.windows(m, ax, ay, bx, by, h0, top, n, kind);
        }
        if (b.roof === "pitched") this.pitched(m, x0, y0, x1, y1, top, colour);
        else {
            flat(m.roof, x0, y0, x1, y1, top);
            for (const [ax, ay, bx, by, n] of SIDES(x0, y0, x1, y1)) wall(m.walls, ax, ay, bx, by, top, top + 0.6, n, colour.map(v => v * 0.85));
            if (height > 18.0 && x1 - x0 > 8 && y1 - y0 > 8) {
                const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
                box(m.roof, cx - 2.5, cy - 2.0, cx + 2.5, cy + 2.0, top, top + 2.8);
            }
        }
    }

    // rows of windows on a wall (3 cm proud of it), a shop window and the doors of the depot and the garage
    windows(m, ax, ay, bx, by, z0, z1, n, kind) {
        const length = Math.hypot(bx - ax, by - ay);
        if (length < 2.5 || z1 - z0 < 2.5) return;
        const ux = (bx - ax) / length, uy = (by - ay) / length, off = n.map(v => v * 0.03);
        const at = (s, z) => [ax + ux * s + off[0], ay + uy * s + off[1], z + off[2]];
        let rows;
        if (kind === "depot" || kind === "garage") {  // (big doors on the ground floor, a strip of windows above)
            const doorW = Math.min(length * 0.5, 9.0), s0 = (length - doorW) / 2;
            quad(m.frames, at(s0, z0), at(s0 + doorW, z0), at(s0 + doorW, z0 + 4.2), at(s0, z0 + 4.2), n);
            rows = z1 - z0 > 7.0 ? [[z0 + 5.4, z0 + 6.6]] : [];
        } else if (kind === "shop") {
            rows = [[z0 + 0.4, z0 + SHOP_GLASS]];
            for (let k = 1; k < Math.trunc((z1 - z0 - 0.8) / FLOOR); k++) rows.push([z0 + FLOOR * k + 1.0, z0 + FLOOR * k + 2.4]);
        } else if (kind === "arcade") rows = [[z0 + 0.3, z0 + 3.2], [z0 + 6.0, z0 + 9.0]];
        else {
            rows = [];
            for (let k = 0; k < Math.trunc((z1 - z0 - 0.8) / FLOOR); k++) rows.push([z0 + FLOOR * k + 0.9, z0 + FLOOR * k + 2.4]);
            if (kind === "house") rows = rows.slice(0, 2);
        }
        const count = Math.max(1, Math.trunc(length / WIN_EVERY)), gap = length / count;
        rows.forEach(([za, zb], r) => {
            if (zb > z1 - 0.3) return;
            const width = kind === "shop" && r === 0 ? gap * 0.8 : Math.min(1.4, gap * 0.6);
            for (let i = 0; i < count; i++) {
                const mid = gap * (i + 0.5), s0 = mid - width / 2, s1 = mid + width / 2;
                quad(m.glass, at(s0, za), at(s1, za), at(s1, zb), at(s0, zb), n);
                quad(m.frames, at(s0, za - 0.12), at(s1, za - 0.12), at(s1, za), at(s0, za), n);  // (a sill under it)
            }
        });
    }

    // a house's roof: two slopes along the longer side, a gable at each end in the wall's colour
    pitched(m, x0, y0, x1, y1, top, colour) {
        const r = top + PITCH;
        if (x1 - x0 >= y1 - y0) {
            const cy = (y0 + y1) / 2;
            quad(m.tiles, [x0, y0, top], [x1, y0, top], [x1, cy, r], [x0, cy, r], [0, -0.64, 0.77]);
            quad(m.tiles, [x1, y1, top], [x0, y1, top], [x0, cy, r], [x1, cy, r], [0, 0.64, 0.77]);
            for (const [gx, nx] of [[x0, -1], [x1, 1]]) { m.walls.colour = [...colour, 1]; m.walls.poly([[gx, y0, top], [gx, y1, top], [gx, cy, r]], [nx, 0, 0]); }
        } else {
            const cx = (x0 + x1) / 2;
            quad(m.tiles, [x0, y1, top], [x0, y0, top], [cx, y0, r], [cx, y1, r], [-0.64, 0, 0.77]);
            quad(m.tiles, [x1, y0, top], [x1, y1, top], [cx, y1, r], [cx, y0, r], [0.64, 0, 0.77]);
            for (const [gy, ny] of [[y0, -1], [y1, 1]]) { m.walls.colour = [...colour, 1]; m.walls.poly([[x0, gy, top], [x1, gy, top], [cx, gy, r]], [0, ny, 0]); }
        }
    }

    // the roads' paint: the middle's dashes, the lane edges, the zebra crossings, the car parks' bays, the yards'
    // yellow lines (city_gfx.CityVisual.markings)
    markings(m) {
        const c = this.city, z = 0.012, half = sim.ROAD / 2, laneEdge = sim.LANE * 2;
        const dashes = (ax, ay, bx, by, offset, dash = 3.0, gap = 3.0, w = 0.12) => {
            const length = Math.hypot(bx - ax, by - ay), ux = (bx - ax) / length, uy = (by - ay) / length, lx = -uy, ly = ux;
            for (let s = 0; s < length - 0.5; s += dash + gap) {
                const e = Math.min(length, s + dash), o0 = offset - w / 2, o1 = offset + w / 2;
                quad(m.paint, [ax + ux * s + lx * o0, ay + uy * s + ly * o0, z], [ax + ux * e + lx * o0, ay + uy * e + ly * o0, z],
                     [ax + ux * e + lx * o1, ay + uy * e + ly * o1, z], [ax + ux * s + lx * o1, ay + uy * s + ly * o1, z], [0, 0, 1]);
            }
        };
        const zebra = (cx, cy, alongX) => {
            for (let k = -4; k <= 4; k++) {
                const o = k * 1.1;
                if (alongX) flat(m.paint, cx - 1.5, cy + o - 0.27, cx + 1.5, cy + o + 0.27, z);
                else flat(m.paint, cx + o - 0.27, cy - 1.5, cx + o + 0.27, cy + 1.5, z);
            }
        };
        for (let k = 0; k <= c.cols; k++) {
            const x = c.roadX(k);
            for (let mm = 0; mm < c.rows; mm++) {
                const ya = c.roadY(mm) + half + 4.0, yb = c.roadY(mm + 1) - half - 4.0;
                dashes(x, ya, x, yb, 0.0);
                dashes(x, ya, x, yb, laneEdge, 1.0, 0.0, 0.1);
                dashes(x, ya, x, yb, -laneEdge, 1.0, 0.0, 0.1);
                zebra(x, c.roadY(mm) + half + 2.2, false);
                zebra(x, c.roadY(mm + 1) - half - 2.2, false);
            }
        }
        for (let mm = 0; mm <= c.rows; mm++) {
            const y = c.roadY(mm);
            for (let k = 0; k < c.cols; k++) {
                const xa = c.roadX(k) + half + 4.0, xb = c.roadX(k + 1) - half - 4.0;
                dashes(xa, y, xb, y, 0.0);
                dashes(xa, y, xb, y, laneEdge, 1.0, 0.0, 0.1);
                dashes(xa, y, xb, y, -laneEdge, 1.0, 0.0, 0.1);
                zebra(c.roadX(k) + half + 2.2, y, true);
                zebra(c.roadX(k + 1) - half - 2.2, y, true);
            }
        }
        const zz = KERB_H + 0.012;  // (the car parks' bays: a line each side of each bay)
        for (const [x, y] of c.parking) {
            const bi = c.blockIndex(x, y);
            if (bi === null || c.blocks[bi].kind !== "carpark") continue;
            for (const side of [-1.5, 1.5]) flat(m.paint, x + side - 0.06, y - 2.4, x + side + 0.06, y + 2.4, zz);
        }
        for (const [x0, y0, x1, y1] of Object.values(c.zones)) {  // (the yellow lines round the places' yards)
            const zy = KERB_H + 0.014;
            for (const [ax, ay, bx, by] of [[x0, y0, x1, y0], [x1, y0, x1, y1], [x1, y1, x0, y1], [x0, y1, x0, y0]]) {
                const length = Math.hypot(bx - ax, by - ay), lx = -(by - ay) / length * 0.1, ly = (bx - ax) / length * 0.1;
                quad(m.yellow, [ax, ay, zy], [bx, by, zy], [bx + lx, by + ly, zy], [ax + lx, ay + ly, zy], [0, 0, 1]);
            }
        }
    }

    // the stunt ramps: a wedge 7 m long rising to its lip, chevrons on the slope
    ramps(m) {
        const L = sim.RAMP_LEN, H = sim.RAMP_H, w = 2.0;
        for (const rp of this.city.ramps) {
            const yr = rp.yaw * DEG, fx = Math.cos(yr), fy = Math.sin(yr), lx = -fy, ly = fx;
            const at = (a, c, z) => [rp.x + fx * a + lx * c, rp.y + fy * a + ly * c, KERB_H + z];
            const back = -L / 2, front = L / 2, n = [-fx * H / Math.hypot(L, H), -fy * H / Math.hypot(L, H), L / Math.hypot(L, H)];
            quad(m.ramp, at(back, -w, 0), at(front, -w, H), at(front, w, H), at(back, w, 0), n);
            m.ramp.poly([at(back, w, 0), at(front, w, H), at(front, w, 0)], [lx, ly, 0]);
            m.ramp.poly([at(back, -w, 0), at(front, -w, 0), at(front, -w, H)], [-lx, -ly, 0]);
            quad(m.ramp, at(front, -w, 0), at(front, w, 0), at(front, w, H), at(front, -w, H), [fx, fy, 0]);
            for (let k = 0; k < 3; k++) {
                const a0 = back + 1.0 + k * 2.0, a1 = a0 + 0.6;
                const z0 = H * (a0 - back) / L + 0.01, z1 = H * (a1 - back) / L + 0.01;
                quad(m.yellow, at(a0, -w, z0), at(a1, -w, z1), at(a1, w, z1), at(a0, w, z0), n);
            }
        }
    }

    // a railing round the city's edge (the barrier things are held at)
    edge(m) {
        const e = this.city.edge;
        for (const [ax, ay, bx, by] of [[e[0], e[1], e[2], e[1]], [e[2], e[1], e[2], e[3]], [e[2], e[3], e[0], e[3]], [e[0], e[3], e[0], e[1]]]) {
            const length = Math.hypot(bx - ax, by - ay), ux = (bx - ax) / length, uy = (by - ay) / length, n = [-uy, ux, 0];
            for (const zr of [0.55, 0.95]) {
                quad(m.steel, [ax, ay, zr], [bx, by, zr], [bx, by, zr + 0.12], [ax, ay, zr + 0.12], n);
                quad(m.steel, [bx, by, zr], [ax, ay, zr], [ax, ay, zr + 0.12], [bx, by, zr + 0.12], n.map(v => -v));
            }
            for (let s = 0; s <= length; s += 3.0) {
                const px = ax + ux * s, py = ay + uy * s;
                box(m.steel, px - 0.05, py - 0.05, px + 0.05, py + 0.05, 0.0, 1.1);
            }
        }
    }

    // the four places' signs: a dark board on the wall above the door (the doors face south, onto their yards) and
    // the words in the place's colour
    signs() {
        const out = [];
        for (const [kind, [dx, dy]] of Object.entries(this.city.places)) {
            const words = PLACE_SIGNS[kind] || kind.toUpperCase(), colour = PLACE_COLOURS[kind] || [1, 1, 1];
            const wallY = dy + 2.0 - 0.06, w = Math.max(6.0, words.length * 0.95);
            const g = new Geo();
            g.quad([[dx - w / 2, wallY, KERB_H + 4.4], [dx + w / 2, wallY, KERB_H + 4.4], [dx + w / 2, wallY, KERB_H + 6.0], [dx - w / 2, wallY, KERB_H + 6.0]], [0, -1, 0]);
            const board = g.mesh("sign " + kind, this.scene);
            board.material = this.material("signboard", [0.08, 0.08, 0.1], 0.6, 0);
            board.material.backFaceCulling = false;
            board.isPickable = false;
            out.push(board);
            const plane = BABYLON.MeshBuilder.CreatePlane("signwords", {width: w * 0.94, height: 1.4}, this.scene);
            const tex = new BABYLON.DynamicTexture("signtex", {width: 1024, height: 160}, this.scene, true);
            tex.hasAlpha = true;
            tex.getContext().clearRect(0, 0, 1024, 160);
            const css = `rgb(${colour.map(v => Math.round(v * 255)).join(",")})`;
            tex.drawText(words, null, 120, `bold ${Math.min(130, Math.floor(1800 / Math.max(4, words.length)))}px sans-serif`, this.wire ? "#ffffff" : css, null, true, true);
            const mat = new BABYLON.StandardMaterial("signwordsmat", this.scene);
            mat.diffuseTexture = tex;
            mat.useAlphaFromDiffuseTexture = true;
            mat.emissiveColor = new BABYLON.Color3(1, 1, 1);
            mat.disableLighting = true;
            mat.backFaceCulling = false;
            plane.material = mat;
            plane.position = v3(dx, wallY - 0.04, KERB_H + 5.2);
            plane.isPickable = false;
            if (this.wire) this.lettering(plane);
            out.push(plane);
        }
        return out;
    }

    // (the line tiers) the city's edges as lines in tiles (the ones off the screen not drawn), and on lines a grid on
    // the ground every 10 m (kart_gfx.GRID), dimmer
    cityLines(meshes) {
        const fade = this.lineFade();
        this.staticLines("citylines", this.edgeLines(meshes, this.wire), this.lineMaterial("city", 1, ...fade));
        if (this.wire !== "outline") return;
        const c = this.city, pos = [], idx = [], z = 0.004;
        const seg = (ax, ay, bx, by) => { const k = pos.length / 3; pos.push(ax, z, ay, bx, z, by); idx.push(k, k + 1); };
        for (let x = Math.ceil(c.xmin / 10) * 10; x <= c.xmax; x += 10) seg(x, c.ymin, x, c.ymax);
        for (let y = Math.ceil(c.ymin / 10) * 10; y <= c.ymax; y += 10) seg(c.xmin, y, c.xmax, y);
        this.staticLines("grid", {pos, idx}, this.lineMaterial("grid", 0.42, ...fade));
    }

    // ---------- the jobs in the city (city_gfx.JobsVisual) ----------
    glowMat(name, colour, alpha) {  // (drawn as it is, unlit, see-through: the jobs' signs over the city, on every tier)
        const key = `jobglow:${name}:${colour.join(",")}:${alpha}`;
        if (this.materials[key]) return this.materials[key];
        const m = new BABYLON.StandardMaterial(key, this.scene);
        m.diffuseColor = new BABYLON.Color3(0, 0, 0);
        m.specularColor = new BABYLON.Color3(0, 0, 0);
        m.emissiveColor = new BABYLON.Color3(...colour);
        m.disableLighting = true;
        m.backFaceCulling = false;
        m.alpha = alpha;
        if (alpha < 1) m.disableDepthWrite = true;
        this.materials[key] = m;
        return m;
    }

    marker(x, y, z, colour, words, radius) {  // a glowing ring on the ground, a see-through wall round it, its words over it
        const root = new BABYLON.TransformNode("marker", this.scene);
        root.position = v3(x, y, z + 0.03);
        const ring = ringGeo(radius - 0.35, radius).mesh("ring", this.scene);
        ring.material = this.glowMat("ring", colour, 0.95);
        ring.parent = root;
        const wallMesh = wallGeo(radius, 1.4).mesh("ringwall", this.scene);
        wallMesh.material = this.glowMat("wall", colour, 0.22);
        wallMesh.parent = root;
        let label = null;
        if (words) {
            label = this.makeLabel(words, `rgb(${colour.map(v => Math.round(v * 255)).join(",")})`, Math.max(3.0, words.length * 0.24), false);
            label.parent = root;
            label.position = v3(0, 0, 3.0);
        }
        for (const mesh of [ring, wallMesh]) mesh.isPickable = false;
        return {root, ring, wall: wallMesh, label, t: 0};
    }

    buildJobs() {
        const c = this.city;
        this.markers = {};
        for (const kind of ["depot", "rank", "arcade"]) {
            const d = c.places[kind];
            if (d) this.markers[kind] = this.marker(d[0], d[1], KERB_H, JOB_COLOURS[kind], MARKER_WORDS[kind], 3.5);
        }
        this.raceMarker = null;
        this.raceAt = null;
        this.beam = wallGeo(1.3, 45.0, 24).mesh("beam", this.scene);
        this.beam.material = this.glowMat("beam", [1, 0.8, 0.2], 0.32);
        this.beam.isPickable = false;
        this.beam.setEnabled(false);
        this.beamLabel = null;
        this.beamWords = null;
        // the chips: green discs spinning over the pavements, one mesh drawn as thin instances (gone ones at size 0)
        const disc = this.chipMesh = BABYLON.MeshBuilder.CreateCylinder("chip", {height: 0.08, diameter: 0.64, tessellation: 16}, this.scene);
        disc.material = this.glowMat("chip", JOB_COLOURS.chip, 1);
        disc.isPickable = false;
        disc.alwaysSelectAsActiveMesh = true;
        this.chipMats = new Float32Array(16 * Math.max(1, c.chips.length));
        disc.thinInstanceSetBuffer("matrix", this.chipMats, 16, false);
        this.checks = [];
    }

    setRaceLine(x, y) {
        if (this.raceAt && this.raceAt[0] === x && this.raceAt[1] === y) return;
        if (this.raceMarker) this.raceMarker.root.dispose();
        this.raceAt = [x, y];
        this.raceMarker = this.marker(x, y, 0.0, JOB_COLOURS.race, MARKER_WORDS.race, 6.0);
    }

    // jobs: the jobs message (city_jobs.Jobs.state); me: your person as drawn; myCar: your car's id or null
    jobsFrame(dt, jobs, me, myId, myCar) {
        this.t += dt;
        const T = this.t;
        if (!jobs) return;
        const enabled = jobs.enabled || {};
        const pulse = m => { m.t += dt; m.wall.visibility = 0.6 + 0.4 * Math.sin(m.t * 3.0); };
        for (const [kind, m] of Object.entries(this.markers)) {
            const on = (enabled[{depot: "delivery", rank: "taxi", arcade: "roundup"}[kind]] ?? true) || kind === "arcade";
            m.root.setEnabled(on);
            if (on) pulse(m);
        }
        const race = jobs.race;
        if (jobs.line) {
            this.setRaceLine(jobs.line[0], jobs.line[1]);
            const on = (enabled.race ?? true) && (!race || race.state !== "racing");
            this.raceMarker.root.setEnabled(on);
            if (on) pulse(this.raceMarker);
        }
        const gone = new Set(jobs.chips_gone || []), M = this.chipMats;
        this.city.chips.forEach(([x, y], i) => {
            const s = gone.has(i) ? 0 : 1, h = ((T * 120 + i * 40) % 360) * DEG, z = KERB_H + 0.8 + 0.15 * Math.sin(T * 2.5 + i);
            // (a disc standing on edge, turning about the upright: Babylon's cylinder stands along its y)
            const m = BABYLON.Matrix.RotationZ(Math.PI / 2).multiply(BABYLON.Matrix.RotationY(-h)).multiply(BABYLON.Matrix.Scaling(s, s, s))
                .multiply(BABYLON.Matrix.Translation(x, z, y));
            m.copyToArray(M, i * 16);
        });
        if (this.city.chips.length) this.chipMesh.thinInstanceBufferUpdated("matrix");
        const mine = (jobs.mine || {})[String(myId)];
        const target = mine ? mine.target : null;
        if (target) {
            const colour = JOB_COLOURS[mine.kind] || [1, 0.8, 0.2], lift = groundLift(this.city, target[0], target[1]);
            this.beam.material = this.glowMat("beam", colour, 0.32);
            this.beam.position = v3(target[0], target[1], lift);
            this.beam.setEnabled(true);
            const words = mine.name || "";
            if (words !== this.beamWords) {
                if (this.beamLabel) this.beamLabel.dispose(false, true);
                this.beamLabel = words ? this.makeLabel(words, "#ffffff", Math.max(3.0, words.length * 0.28), false) : null;
                this.beamWords = words;
            }
            if (this.beamLabel) { this.beamLabel.position = v3(target[0], target[1], lift + 6.0); this.beamLabel.setEnabled(true); }
        } else {
            this.beam.setEnabled(false);
            if (this.beamLabel) this.beamLabel.setEnabled(false);
        }
        // the checkpoints: the race's course while you are in it, the next one bright
        const inRace = !!(race && myCar !== null && String(myCar) in (race.cars || {}));
        const course = inRace ? race.course : [];
        while (this.checks.length < course.length) this.checks.push(this.marker(0, 0, 0, JOB_COLOURS.race, "", 7.0));
        const next = inRace ? (race.state === "racing" ? (race.cars[String(myCar)] + 1) % course.length : 1) : null;
        this.checks.forEach((m, i) => {
            const on = i < course.length;
            m.root.setEnabled(on);
            if (!on) return;
            m.root.position = v3(course[i][0], course[i][1], 0.03);
            pulse(m);
            m.ring.visibility = i === next ? 1 : 0.25;
            m.wall.visibility *= i === next ? 1 : 0.25;
        });
    }

    // ---------- the things: people (Fight Lab's fighters), cars (Kart Lab's), robots (Robot Lab's) ----------
    // roster: the server's roster (each one's design); drawn: id -> the record to draw (blended or predicted)
    syncThings(roster, drawn) {
        const designs = new Map();
        for (const group of ["people", "cars", "robots"]) for (const e of (roster && roster[group]) || []) designs.set(e.id, e);
        // gone, or a new design: away (made again below)
        for (const [id, f] of this.fighters) {
            const e = designs.get(id);
            if (!drawn.has(id) || !e || JSON.stringify(e.design) !== f.cityKey) this.dropFighter(id);
        }
        for (const [id, k] of this.karts) {
            const e = designs.get(id);
            if (!drawn.has(id) || !e || JSON.stringify(e.design) !== k.cityKey) this.removeKart(id);
        }
        for (const [id, v] of this.robots) {
            const e = designs.get(id);
            if (!drawn.has(id) || !e || JSON.stringify(e.design) !== this.robotKeys.get(id)) this.dropRobot(id, v);
        }
        for (const id of drawn.keys()) {
            const e = designs.get(id);
            if (!e) continue;  // (before the roster has said: drawn once it has)
            const kind = sim.kindOf(id);
            if (kind === "person" && !this.fighters.has(id)) {
                const owner = e.owner && e.owner !== e.name ? e.owner : "";
                const f = this.addFighter({id, design: fighterDesign(e.design || {}), owner});
                f.cityKey = JSON.stringify(e.design);
            } else if (kind === "car" && !this.karts.has(id)) {
                const d = e.design || {};
                this.addKart({id, name: d.name || "", colour: d.colour || e.colour, body: sim.BODIES.includes(d.body) ? d.body : "coupe"});
                const k = this.karts.get(id);
                k.cityKey = JSON.stringify(e.design);
                k.label.setEnabled(false);  // (the window draws no names over the cars)
                k.label.isVisible = false;
            } else if (kind === "robot" && !this.robots.has(id)) {
                const v = this.addRobot({id, design: e.design || {}, owner: ""});
                this.robotKeys.set(id, JSON.stringify(e.design));
                const sh = robotShapes(v.weaponType, v.s, false);
                v.cityPivot = sh.pivot.map(c => c * sh.k);
                v.tag = null;
                v.label.dispose(false, true);
                v.label = this.makeLabel(" ", "#ffffff", 2.2, false);
            }
            if (!this.things.has(id)) this.things.set(id, {stride: 0, t: 0, hurtAt: -10, wasHurt: false});
        }
        for (const id of [...this.things.keys()]) if (!drawn.has(id)) this.things.delete(id);
    }

    dropFighter(id) {
        const f = this.fighters.get(id);
        if (!f) return;
        f.label.dispose(false, true);
        if (f.plate) f.plate.dispose(false, true);
        f.root.dispose();
        if (f.model) f.model.dispose();
        this.fighters.delete(id);
    }

    dropRobot(id, v) {
        try { this.disposeRobot(v); } catch (e) { /* the scene already gone */ }
        this.robots.delete(id);
        this.robotKeys.delete(id);
    }

    // view: {drawn: Map id -> record, roster, jobs, me (my person id), myCar, camera: {x, y, z, yaw, moving} or null}
    frame(view, dt, t) {
        if (!this.scene || !this.city) return;
        const {drawn, roster} = view;
        this.syncThings(roster, drawn);
        const cam = this.camera.globalPosition, overview = this.view.mode === "city", city = this.city;
        const near = (st, kind, id) => overview || id === view.me || id === view.myCar || (st.x - cam.x) ** 2 + (st.y - cam.z) ** 2 < DRAW[kind] ** 2;
        // the people
        for (const [id, f] of this.fighters) {
            const p = drawn.get(id), th = this.things.get(id);
            const show = !!p && !p.link && near(p, "person", id);
            f.root.setEnabled(show);
            f.label.setEnabled(show && id !== view.me);
            if (!show) { if (f.model) f.model.show(false); continue; }
            th.t += dt;
            const hurt = !!(p.flags & sim.FLAG_HURT) || p.move === sim.MOVE_HURT;
            if (hurt && !th.wasHurt) th.hurtAt = th.t;
            th.wasHurt = hurt;
            if (p.v > 0.3 && !p.move && !(p.flags & sim.FLAG_AIR)) th.stride += dt * (p.v * 0.9 + 0.3);
            const [a, k] = personAnim(p, th.stride, th.t);
            // (running: the walk played faster, the models have no run of their own)
            const speedUp = 1.0 + (p.flags & sim.FLAG_RUN && a === "walk_f" ? 0.9 : 0.0);
            const lift = groundLift(city, p.x, p.y);
            this.poseFighter(f, {id, pos: [p.x, p.y, p.z + lift], h: p.yaw - 90.0, a, k, hp: p.hp, max: sim.HEALTH, en: 0, w: 0,
                                 hu: Math.min(9.0, th.t - th.hurtAt), hits: 0, ap: 0}, dt * speedUp);
        }
        // the cars (their damage drawn on every part, as the window's: the wing a little less)
        const carStates = new Map();
        for (const [id, k] of this.karts) {
            const c = drawn.get(id);
            const show = !!c && near(c, "car", id);
            k.root.setEnabled(show);
            if (!show) { k.lastV = null; continue; }
            const d = Math.min(sim.DAMAGE_MAX, c.dmg || 0);
            const st = {...c, dw: d * 0.6, dfl: d, dfr: d, drl: d, drr: d, de: d, shield: 0};
            const z = c.z + groundLift(city, c.x, c.y);
            k.root.position.set(c.x, z, c.y);
            this.carFrame(k, st, z, dt);
            carStates.set(id, st);
        }
        this.follow = view.myCar;
        // the robots, through Robot Lab's frame: their place and heading, the weapon on its pivot (a spinner or drum
        // spun as the robot winds it up), dark when powered down, red when rogue, a tag when hurt
        const placed = [];
        for (const [id, v] of this.robots) {
            const r = drawn.get(id);
            if (!r || !near(r, "robot", id)) continue;
            const q = hprQuat(r.yaw - 90.0, 0, 0), lift = groundLift(city, r.x, r.y), at = [r.x, r.y, lift + RIDE];
            const w = qrot(q, v.cityPivot), off = r.hp <= 0, rogue = !!(r.flags & sim.FLAG_ROGUE);
            const rate = Math.min(2400.0, (r.aux || 0) * 1.6);  // (degrees a second: the weapon winds up as the robot gets cross)
            placed.push({id, pos: at, quat: q, wpos: [at[0] + w[0], at[1] + w[1], at[2] + w[2]], wquat: q, rpm: rate / 6 / 0.35,
                         speed: r.v, hp: Math.max(0, r.hp), max: sim.POWER, tint: off ? [0.35, 0.35, 0.4] : rogue ? [1.4, 0.55, 0.5] : null});
        }
        this.cameraView = view.camera;
        super.frame({robots: placed}, dt, t);  // (the robots, the effects, the camera, the sun's shadow)
        for (const r of placed) {  // (a robot's tag: its power when it is hurt, REBOOTING when it is down)
            const v = this.robots.get(r.id), rec = drawn.get(r.id);
            const tag = rec.hp > 0 && rec.hp < sim.POWER ? `${v.design.name || "ROBOT"}  ${rec.hp}%` : rec.hp <= 0 ? `${v.design.name || "ROBOT"}  REBOOTING` : "";
            if (tag !== v.tag) {
                v.tag = tag;
                v.label.dispose(false, true);
                v.label = this.makeLabel(tag || " ", rec.flags & sim.FLAG_ROGUE ? "#ff7359" : "#ffffff", 2.2, false);
            }
            v.label.setEnabled(!!tag);
            v.label.position = v3(r.pos[0], r.pos[1], r.pos[2] + 1.3);
        }
        for (const [id, v] of this.robots) if (!placed.some(r => r.id === id)) v.label.setEnabled(false);
        this.headlightFrame(carStates);
        if (this.smoke) this.smoke.update(dt, this.camera);
        if (this.skids) this.skids.update(dt);
        if (this.sparks) this.sparks.update(dt, this.camera);
        this.jobsFrame(dt, view.jobs, drawn.get(view.me), view.me, view.myCar);
    }

    // sparks where a punch, a kick or a zap landed (city_client.hits_seen): a robot's power, or a person's health, down
    hit(x, y, z, damage, robot) {
        if (this.fx) this.fx.impact([x, y, z], damage, robot ? "bump" : "flip", robot ? [0.7, 0.7, 0.72] : [0.9, 0.8, 0.7]);
    }

    // ---------- the cameras (city_gfx.FootCamera and CarCamera: Kart Lab's chase camera) ----------
    // on foot: behind and above the person, swinging round behind them as they go (slowly, so steering by the camera
    // is steady), over the shoulder, or from 60 m up; in a car: chase or bonnet; the whole city (the teacher's, or
    // anyone with nobody to follow: Babylon's own orbit)
    overview() {
        const c = this.city, cam = this.camera;
        if (!c) return;
        cam.fovMode = BABYLON.Camera.FOVMODE_VERTICAL_FIXED;
        cam.fov = 0.8;
        cam.minZ = 0.5;
        cam.lowerRadiusLimit = 20;
        cam.upperBetaLimit = 1.45;
        cam.target = new BABYLON.Vector3(0, 0, 0);
        cam.radius = Math.max(c.width, c.height) * 0.95;
        cam.alpha = -Math.PI / 2;
        cam.beta = 0.85;
    }

    setView(mode) {
        this.view.mode = mode;
        this.view.pos = null;
        this.view.carYaw = null;
        if (mode === "city") this.overview();
    }

    // the keys' forward and right (-1 to 1 each) as a move in the world (x east, y north), magnitude up to 1
    // (city_gfx.FootCamera.move_from_keys: W is away from the camera)
    moveFromKeys(forward, right) {
        const yr = this.view.yaw * DEG, fx = Math.cos(yr), fy = Math.sin(yr), rx = fy, ry = -fx;
        let mx = fx * forward + rx * right, my = fy * forward + ry * right;
        const mag = Math.hypot(mx, my);
        if (mag > 1.0) { mx /= mag; my /= mag; }
        return [mx, my];
    }

    // the camera pulled in where a building is between it and the person (so you never look at a wall)
    clearDist(x, y, dx, dy, dist) {
        for (let i = 1; i <= 10; i++) {
            const d = dist * i / 10;
            if (this.city.collide(x + dx * d, y + dy * d, 0.3)[2] === "building") return Math.max(1.2, dist * (i - 1) / 10);
        }
        return dist;
    }

    updateCamera(st, dt) {
        const V = this.view, c = this.cameraView, cam = this.camera;
        if (V.mode === "city" || !c) return;  // (the whole city: Babylon's own orbit; nobody to follow yet: where it was)
        let want, look, fov, rate = 10, lookRate = 14, near = 0.2;
        if (c.car) {  // (Kart Lab's chase camera: chase or bonnet)
            const yr = c.yaw * DEG, fx = Math.cos(yr), fy = Math.sin(yr), z = c.z + 0.5;
            if (V.mode === "hood") {
                want = [c.x + fx * c.hood[0], c.y + fy * c.hood[0], z + c.hood[1] - 0.5];
                look = [c.x + fx * 25, c.y + fy * 25, z - 0.2];
                fov = 82; rate = lookRate = 60; near = 0.08;
            } else {
                if (V.carYaw === null) V.carYaw = c.yaw;
                V.carYaw += wrapDeg(c.yaw - V.carYaw) * Math.min(1, dt * 4.5);
                const cr = V.carYaw * DEG, speed = Math.max(0, c.v || 0);
                const dist = (5.2 + 0.07 * speed) * V.zoom, height = (2.0 + 0.025 * speed) * (0.6 + 0.4 * V.zoom);
                want = [c.x - Math.cos(cr) * dist, c.y - Math.sin(cr) * dist, z + height];
                look = [c.x + fx * 5, c.y + fy * 5, z + 0.1];
                fov = 72 + 0.25 * speed; rate = lookRate = 14;
            }
            V.yaw = c.yaw;  // (out of the car: the foot camera faces the way the car faced)
        } else if (V.mode === "above") {
            look = [c.x, c.y, c.z];
            want = [c.x, c.y - 25.0 * V.zoom, c.z + 60.0 * V.zoom];
            fov = 55;
        } else {
            if (c.moving) V.yaw += wrapDeg(c.yaw - V.yaw) * Math.min(1.0, dt * 1.6);
            const shoulder = V.mode === "shoulder";
            let [dist, height] = shoulder ? [2.6, 1.75] : [5.0, 2.3];
            fov = shoulder ? 56 : 62;
            dist *= V.zoom;
            const yr = V.yaw * DEG, fx = Math.cos(yr), fy = Math.sin(yr);
            look = [c.x + fx * 1.5, c.y + fy * 1.5, c.z + 1.4];
            if (shoulder) look = [look[0] - fy * 0.6, look[1] + fx * 0.6, look[2] + 0.15];
            dist = this.clearDist(c.x, c.y, -fx, -fy, dist);
            want = [c.x - fx * dist, c.y - fy * dist, c.z + height * (0.6 + 0.4 * V.zoom)];
            if (shoulder) want = [want[0] - fy * 0.7, want[1] + fx * 0.7, want[2]];
        }
        if (!V.pos || dt >= 1) { V.pos = want.slice(); V.look = look.slice(); V.fov = fov; }
        else {
            const a = Math.min(1, dt * rate), b = Math.min(1, dt * lookRate);
            for (let i = 0; i < 3; i++) { V.pos[i] += (want[i] - V.pos[i]) * a; V.look[i] += (look[i] - V.look[i]) * b; }
            V.fov += (fov - V.fov) * Math.min(1, dt * 4);
        }
        const s = this.fx ? this.fx.shakeOffset() : null;
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;  // (Panda's lens: the fov is across)
        cam.fov = Math.max(20, Math.min(110, V.fov)) * DEG;
        cam.minZ = near;
        cam.lowerRadiusLimit = 0.01;
        cam.upperBetaLimit = Math.PI - 0.01;
        cam.inertialAlphaOffset = cam.inertialBetaOffset = cam.inertialRadiusOffset = cam.inertialPanningX = cam.inertialPanningY = 0;
        cam.setTarget(v3(...V.look));
        cam.setPosition(v3(V.pos[0] + (s ? s[0] : 0), V.pos[1] + (s ? s[1] : 0), V.pos[2] + (s ? s[2] : 0)));
    }

    followSun() {  // (the key light's shadow round what the camera looks at)
        if (this.lighting) {
            const t = this.camera.target;
            this.lighting.follow([t.x, t.y, t.z]);
        }
    }

    dispose() {
        if (this.after) { this.after.dispose(); this.after = null; }
        super.dispose();
    }
}

// (CHANGE 201) the cars' and the fighters' own methods (cars.js, fighters.js), as Kart Lab and Fight Lab draw them
Object.assign(CityScene.prototype, CarParts, FighterParts);

// a record a fraction f of the way from a to b (the position, height, heading and speeds; the rest b's)
function between(a, b, f) {
    if (!a || !(f > 0)) return {...(a || b)};
    if (f >= 1) return {...b};
    const dy = wrapDeg(b.yaw - a.yaw);
    return {...b, x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, z: a.z + (b.z - a.z) * f, yaw: a.yaw + dy * f,
            v: a.v + (b.v - a.v) * f, u: (a.u || 0) + ((b.u || 0) - (a.u || 0)) * f};
}

// ---------- the game ----------
export class CityGame {
    static detect(m) { return !!(m.city && m.city.blocks && m.rules && m.rules.looks); }

    constructor(app) {
        this.app = app;
        this.id = "citylab";
        this.title = "City Lab";
        this.word = "driver";
        this.mods = ["mods/city.py", "mods/rules.py", "mods/drivers/<username>.py"];
        this.scene = new CityScene(app.canvas, app.tier, app.engine);
        this.controlKind = "city";  // (play.js: on foot WASD walks, in a car it drives: the window's keys)
        this.hud = new CityHud();
        this.city = null;
        this.me = null;           // my person's id (null: the teacher, out of the city)
        this.jobs = null;
        this.paused = false;
        // what I control, predicted as the window predicts it (city_client: my person on foot, or the car I drive)
        this.predictor = null;
        this.predId = null;
        this.predFirst = 0;
        this.smoother = new ErrorSmoother({removeUp: true});
        this.lead = new LeadController();
        this.nextSeq = 1;         // (one numbering for every input sent, whether or not a predictor is running)
        this.snapSeq = 0;
        this.accum = 0;
        this.sentAt = new Map();
        this.drawFrom = null;
        this.latest = new Map();  // id -> the newest snapshot's record
        this.prevHp = new Map();  // (the sparks where a hit landed)
        this.demo = app.params.get("demo") || null;  // (the tests: "getin" walks to the nearest car and gets in, as the window's --demo-drive)
        this.demoAt = 0;
        this.wheel = e => {
            if (this.scene.view.mode === "city" || !this.app.state.connected) return;
            e.preventDefault();
            this.zoomBy(this.app.wheelZoom(e));
        };
        app.canvas.addEventListener("wheel", this.wheel, {passive: false});
        document.body.classList.add("cityscreen");
    }

    welcome(m) {
        this.setCity(m.city);
        this.me = m.me ?? null;
        this.design = m.design || null;
        this.predictor = null;
        this.scene.setTime(((m.lesson || {}).time) || "day");
        const kept = (m.prefs || {}).camera, V = this.scene.view;
        if (kept && typeof kept === "object") {
            if (FOOT_VIEWS.includes(kept.mode)) V.mode = kept.mode;
            const z = Number(kept.zoom);
            if (Number.isFinite(z)) V.zoom = Math.max(0.45, Math.min(2.5, z));
        }
        const cam = this.app.params.get("cam");
        if (cam && (FOOT_VIEWS.includes(cam) || cam === "city")) this.scene.setView(cam);
        else if (this.me === null) this.scene.setView("city");
        if (m.role !== "learner") this.app.toast("Teacher: Enter starts a street race for everyone, G sends everyone to the depot, F mends your car, P pauses", false, 8000);
    }

    setCity(data) {
        if (!data || (this.city && this.city.data === data)) return;
        if (this.city && JSON.stringify(this.city.data) === JSON.stringify(data)) return;
        this.city = new sim.City(data);
        this.scene.setCity(this.city);
        this.hud.setCity(this.city);
        this.predictor = null;  // (its step knows the old city: predicted afresh, as the window's change_city)
        this.latest = new Map();
    }

    myId() {
        const r = this.app.state.roster;
        if (r && r.mine && r.mine[this.app.state.name] !== undefined) this.me = r.mine[this.app.state.name];
        return this.me;
    }

    // the car I'm in (its id), from what is drawn of me: null on foot
    myCar() {
        const id = this.myId(), me = id !== null ? this.latest.get(id) : null;
        return me && me.link ? me.link - 1 : null;
    }

    driving() { return this.myCar() !== null; }

    mySpeed() {  // (the clutch drop's arming: play.js)
        return this.predictor ? this.predictor.state.v || 0 : 0;
    }

    // ---------- messages ----------
    message(m) {
        switch (m.type) {
            case "lesson":
                this.scene.setTime(((m.lesson || this.app.state.lesson || {}).time) || "day");
                return false;
            case "roster":
                if (m.mine && m.mine[this.app.state.name] !== undefined && m.mine[this.app.state.name] !== this.me) {
                    this.me = m.mine[this.app.state.name];
                    this.predictor = null;
                    // (the teacher out of the city, watching: the whole city; back in it: behind them again)
                    if (this.me === null && this.scene.view.watch === null) this.scene.setView("city");
                    else if (this.me !== null && this.scene.view.mode === "city") this.scene.setView("behind");
                }
                return true;
            case "jobs":
                this.jobs = m;
                this.paused = !!m.paused;
                for (const [, words] of m.events || []) this.app.addEvent(words);
                if (this.app.state.tab === "learners") this.app.renderPanel();
                return true;
            case "city":  // (the teacher chose another city)
                this.setCity(m.city);
                if (m.me !== undefined) this.me = m.me;
                this.app.toast(`Welcome to ${this.city.name}`, false, 4000);
                return true;
            default:
                return false;
        }
    }

    binary(data, now) {
        if (frameKind(data) !== KIND_SNAPSHOT) return;
        const snap = unpackSnapshot(data, CITY_FIELDS);
        this.app.pushSnap(snap, now);
        this.onSnapshot(snap, now);
    }

    // ---------- prediction (city_client.on_snapshot, client_tick) ----------
    predicting() {
        const S = this.app.state;
        return this.myId() !== null && this.app.params.get("predict") !== "0" && !((S.myMissions || {}).autopilot);
    }

    stepFor(target) {  // (city_client.step_fn: my person on foot, or my car driven as my points say)
        if (sim.kindOf(target) === "person") return sim.makeStep(this.city, "person");
        const people = ((this.app.state.roster || {}).people || []), mine = people.find(p => p.id === this.me);
        return sim.makeStep(this.city, "car", sim.statsOf((mine && mine.design) || this.design || sim.defaultDesign()));
    }

    onSnapshot(snap, rx) {
        this.snapSeq = snap.seq;
        this.lead.feed(snap.flags >> 4);
        const ents = new Map(snap.entities.map(e => [e.id, e]));
        this.hitsSeen(this.latest, ents);
        this.latest = ents;
        const id = this.myId(), me = id !== null ? ents.get(id) : null;
        if (!me || !this.city || !this.predicting()) { this.predictor = null; return; }
        const target = me.link ? me.link - 1 : id, state = ents.get(target);
        if (!state) return;
        const newest = this.predictor ? this.predictor.log.newest() : null;
        if (newest !== null && newest !== undefined && seqDiff(snap.ack, newest) > 3) {
            // the server has run past every input we sent (the page froze for a moment): our numbering carries on
            // from the server's, a round trip ahead, and the prediction from its record (city_client.on_snapshot)
            this.nextSeq = (snap.ack + 3 + Math.floor(this.app.state.pingMs / 1000 / sim.STEP)) & SEQ_MASK;
            this.predictor = null;
        }
        if (!this.predictor || this.predId !== target) {  // (in or out of a car: the new thing predicted from the server's record)
            if (!this.facedYet && target === id) { this.facedYet = true; this.scene.view.yaw = state.yaw; }  // (the camera behind you, as you start)
            this.predId = target;
            this.predictor = new Predictor(this.stepFor(target), {...state}, 0.05, new InputLog(this.nextSeq));
            this.predFirst = this.nextSeq;
            this.drawFrom = {...state};
            this.smoother.clear();
            this.accum = 0;
            return;
        }
        if (snap.ack === 0 || seqDiff(snap.ack, this.predFirst) < 0) return;  // (none of this prediction's inputs applied yet)
        const err = this.predictor.correct({...state}, snap.ack, sim.STEP, sim.compare);
        const moved = this.predictor.movedFrom;
        if (moved) {  // (the state before the newest tick moves with the correction: the picture holds)
            const n = this.predictor.state, f = this.drawFrom;
            this.drawFrom = err === Infinity || !f ? n : {...f, x: f.x + n.x - moved.x, y: f.y + n.y - moved.y, yaw: f.yaw + n.yaw - moved.yaw};
            if (err !== Infinity) this.smoother.add([moved.x - n.x, moved.y - n.y, 0], wrapDeg(moved.yaw - n.yaw) * DEG);
        }
        const sent = this.sentAt.get(snap.ack);
        if (sent !== undefined && this.app.ctrl) {
            const ms = rx - sent;
            this.app.ctrl.ctrlMs = this.app.ctrl.ctrlMs === null ? ms : this.app.ctrl.ctrlMs * 0.8 + ms * 0.2;
        }
    }

    // sparks and a sound where a punch, a kick or a zap landed: a robot's power or a person's health went down
    hitsSeen(prev, now) {
        if (!this.city) return;
        for (const [id, e] of now) {
            const kind = sim.kindOf(id), was = prev.get(id);
            if (kind === "car" || !was || e.hp >= was.hp || e.link) continue;
            const lost = was.hp - e.hp, lift = groundLift(this.city, e.x, e.y), robot = kind === "robot";
            this.scene.hit(e.x, e.y, lift + (robot ? 0.4 : 1.2), lost * 2, robot);
            if (this.app.sound) this.app.sound.cityHit(robot ? "punch" : e.move === sim.MOVE_DOWN ? "high" : "kick", [e.x, e.y], robot);
        }
    }

    sendNeutral() {  // (the tab hidden: one input with nothing pressed, numbered on from ours)
        const seq = this.nextSeq;
        this.nextSeq = (seq + 1) & SEQ_MASK;
        this.app.sendBinary(packInput(seq, this.snapSeq, Math.floor(performance.now()) >>> 0, 0, 0, 0, []));
    }

    // the keys' forward and right as a move in the world, by the camera (play.js asks)
    footMove(forward, right) {
        return this.scene.moveFromKeys(forward, right);
    }

    // (the tests, as the window's --demo-drive online: demo_get_in) walk to the nearest car nobody is in, and get in (E,
    // once a second); null once in a car, or with no demo asked for
    demoKeys() {
        if (this.demo !== "getin" || this.driving()) return null;
        const id = this.myId(), me = this.predictor && this.predId === id ? this.predictor.state : this.latest.get(id);
        if (!me) return null;
        let best = null, bd = Infinity;
        const parked = new Set((((this.app.state.roster || {}).cars) || []).filter(c => c.kind === "parked").map(c => c.id));
        for (const [cid, c] of this.latest) {
            if (sim.kindOf(cid) !== "car" || c.link || (parked.size && !parked.has(cid))) continue;  // (a parked one: the traffic drives off)
            const d = Math.hypot(c.x - me.x, c.y - me.y);
            if (d < bd) { bd = d; best = c; }
        }
        if (!best) return {throttle: 0, steer: 0, buttons: 0};
        if (bd < GET_IN_REACH - 0.3) {
            const now = performance.now();
            if (now - this.demoAt > 1000) { this.demoAt = now; return {throttle: 0, steer: 0, buttons: sim.ACTION}; }
            return {throttle: 0, steer: 0, buttons: 0};
        }
        return {throttle: (best.x - me.x) / bd, steer: (best.y - me.y) / bd, buttons: 0};
    }

    // play.js calls this every frame with a function reading the keys: whole 1/60 s ticks, each one input
    controlFrame(now, readKeys, dt) {
        if (this.predictor === null && this.predicting()) return;  // (nothing to predict from until the first snapshot)
        if (this.paused) return;  // (nothing moves and nothing is sent while the teacher has paused the city)
        this.accum = Math.min(15 * sim.STEP, this.accum + dt / this.lead.multiplier());
        while (this.accum >= sim.STEP) {
            this.accum -= sim.STEP;
            const k = this.demoKeys() || readKeys();
            const inp = quantiseInput(k.throttle, k.steer, k.buttons);
            let seq, prev;
            if (this.predictor) {
                this.drawFrom = this.predictor.state;
                seq = this.predictor.apply(inp, sim.STEP, now);
                prev = this.predictor.log.previous(2);
                this.nextSeq = this.predictor.log.nextSeq;
            } else {
                seq = this.nextSeq;
                prev = [];
                this.nextSeq = (seq + 1) & SEQ_MASK;
            }
            this.sentAt.set(seq, now);
            if (this.sentAt.size > 128) for (const s of [...this.sentAt.keys()].slice(0, 64)) this.sentAt.delete(s);
            this.app.sendBinary(packInput(seq, this.snapSeq, Math.floor(now) >>> 0, inp[0], inp[1], inp[2], prev));
        }
    }

    // ---------- each frame ----------
    frame(now, dt) {
        if (!this.city) return;
        const pair = this.app.samplePair(now), drawn = new Map();
        if (pair) {
            const {a, b, f} = pair, byId = b ? new Map(b.entities.map(e => [e.id, e])) : new Map();
            for (const e of a.entities) drawn.set(e.id, byId.has(e.id) ? between(e, byId.get(e.id), f) : e);
        }
        const id = this.myId();
        if (this.predictor && this.predId !== null && drawn.has(this.predId)) {
            const mine = between(this.drawFrom, this.predictor.state, this.accum / sim.STEP);
            const [[ox, oy], oyaw] = this.smoother.offset(dt);
            mine.x += ox; mine.y += oy; mine.yaw += oyaw / DEG;
            drawn.set(this.predId, mine);
            const latestMe = this.latest.get(id);
            if (this.predId !== id && latestMe) drawn.set(id, {...latestMe, x: mine.x, y: mine.y, z: mine.z, yaw: mine.yaw, v: mine.v});  // (in a car: I sit where it is)
        } else if (id !== null && drawn.has(id) && this.latest.has(id)) {
            const l = this.latest.get(id);
            drawn.set(id, {...drawn.get(id), cash: l.cash, aux: l.aux, link: l.link});
        }
        const S = this.app.state, sc = this.scene, V = sc.view;
        const me = id !== null ? drawn.get(id) : null, car = me && me.link ? me.link - 1 : null;
        const watched = V.watch !== null && drawn.has(V.watch) ? drawn.get(V.watch) : me;
        let camera = null;
        if (watched) {
            const wcar = watched.link ? drawn.get(watched.link - 1) : null, t = wcar || watched;
            const lift = groundLift(this.city, t.x, t.y);
            const k = wcar ? sc.karts.get(watched.link - 1) : null;
            camera = {x: t.x, y: t.y, z: t.z + lift, yaw: t.yaw, v: t.v, moving: t.v > 0.5, car: !!wcar,
                      hood: k ? k.fit.hood : [0.95, 0.62]};
            if (wcar && !CAR_VIEWS.includes(V.mode) && V.mode !== "city") { V.footMode = V.mode; sc.setView("chase"); }
            if (!wcar && CAR_VIEWS.includes(V.mode)) { sc.setView(V.footMode || "behind"); V.yaw = t.yaw; }
        }
        sc.frame({drawn, roster: S.roster, jobs: this.jobs, me: id, myCar: car, camera}, dt, now / 1000);
        const shown = `${car !== null}:${V.mode}:${V.watch}`;
        if (shown !== this.shownKeys) {  // (in or out of a car, another view: the key list and the camera's pill again)
            this.shownKeys = shown;
            if (this.app.keyHelp) this.app.keyHelp();
            this.app.updatePills();
        }
        // the HUD (hud.js): the cash, the job and its arrow, the minimap, health, speed and damage, the hint, the keys
        let hint = "";
        if (me && car !== null && drawn.get(car) && Math.abs(drawn.get(car).v) < sim.EXIT_SPEED) hint = "E: get out";
        else if (me && car === null && ![sim.MOVE_DOWN, sim.MOVE_GETUP].includes(me.move)) {
            let nearest = 99;
            for (const [cid, c] of drawn) if (sim.kindOf(cid) === "car" && !c.link) nearest = Math.min(nearest, Math.hypot(c.x - me.x, c.y - me.y));
            if (nearest < GET_IN_REACH) hint = "E: get in";
        }
        const camYaw = V.mode === "city" ? 90 : V.pos && V.look ? Math.atan2(V.look[1] - V.pos[1], V.look[0] - V.pos[0]) / DEG : V.yaw;
        this.hud.update({me, car: car !== null ? drawn.get(car) : null, myId: id, myCar: car, jobs: this.jobs, drawn, camYaw, hint,
                         paused: this.paused, view: VIEW_NAMES[V.mode] || V.mode, watching: V.watch !== null ? this.nameOf(V.watch) : null});
        if (this.app.touch && this.app.touch.shown) this.app.touch.setLayout(car !== null ? "car" : "foot");
        if (this.app.sound) {
            const heard = car !== null ? drawn.get(car) : null;
            const people = (S.roster || {}).people || [], mine = people.find(p => p.id === id);
            this.app.sound.cityFrame(heard, me, {top: sim.statsOf((mine && mine.design) || {}).top, race: this.jobs ? this.jobs.race : null,
                                                 mine: this.jobs && id !== null ? (this.jobs.mine || {})[String(id)] : null, now: Date.now()});
        }
    }

    nameOf(id) {
        const p = (((this.app.state.roster || {}).people) || []).find(x => x.id === id);
        return p ? p.name : `#${id}`;
    }

    // ---------- the keys app.js passes on ----------
    cycleCamera() {  // V: behind, over the shoulder, from above (and the whole city for the teacher); in a car chase, bonnet
        const sc = this.scene, V = sc.view, teacher = this.app.state.role !== "learner" || this.myId() === null;
        const order = this.driving() ? CAR_VIEWS : teacher ? [...FOOT_VIEWS, "city"] : FOOT_VIEWS;
        sc.setView(order[(order.indexOf(V.mode) + 1) % order.length]);
        if (FOOT_VIEWS.includes(V.mode)) V.footMode = V.mode;
        this.keepCamera();
    }

    // L: the camera follows the next person in the city (round them all, then your own again)
    cycleWatch() {
        const people = ((this.app.state.roster || {}).people || []).map(p => p.id).filter(i => this.latest.has(i));
        if (!people.length) return;
        const V = this.scene.view, mine = this.myId();
        const ids = mine !== null && people.includes(mine) ? people.slice(people.indexOf(mine)).concat(people.slice(0, people.indexOf(mine))) : people;
        const cur = V.watch !== null && ids.includes(V.watch) ? V.watch : mine !== null ? mine : null;
        const next = cur === null ? ids[0] : ids[(ids.indexOf(cur) + 1) % ids.length];
        V.watch = next === mine ? null : next;
        if (V.mode === "city") this.scene.setView("behind");
        V.pos = null;
        this.app.toast(V.watch === null ? "Camera: you" : `Camera: ${this.nameOf(V.watch)}  (L next, V view)`);
    }

    keepCamera() {  // (in the window's format: FootCamera.settings)
        const V = this.scene.view;
        if (FOOT_VIEWS.includes(V.mode) && this.app.keepPrefs) this.app.keepPrefs({camera: {mode: V.mode, zoom: Math.round(V.zoom * 100) / 100}});
    }

    zoomBy(factor) {  // (FootCamera.wheel: x 1.12 a notch, held between 0.45 and 2.5)
        const V = this.scene.view;
        V.zoom = Math.max(0.45, Math.min(2.5, V.zoom * factor));
        this.keepCamera();
    }

    zoom(dir, how = "key") {  // (+ and -: closer and wider)
        if (!dir || this.scene.view.mode === "city") return false;
        const f = how === "repeat" ? [0.9, 1.11] : [0.8, 1.25];
        this.zoomBy(dir > 0 ? f[0] : f[1]);
        return true;
    }

    resetCamera() {  // Home: the zoom back to 1, the camera cut back to where it belongs
        const V = this.scene.view;
        V.zoom = 1.0;
        V.watch = null;
        this.scene.setView(V.mode);
        this.keepCamera();
        return true;
    }

    fixMine() { this.app.send({type: "fix"}); }  // (the teacher's F: the server mends the teacher's own car)

    // the teacher's keys (city_client.start_online): Enter a street race for everyone, G everyone to the depot
    teacherKey(key) {
        if (this.app.state.role === "learner") return false;
        const k = String(key || "").toLowerCase();
        if (k === "enter") this.app.send({type: "start"});
        else if (k === "g") this.app.send({type: "grid"});
        else return false;
        return true;
    }

    // a game's own keys before the page's: the teacher's P pauses the city; C (the code panel) waits for the lessons
    onKey(k) {
        if (k === "p" && this.app.state.role !== "learner") { this.app.send({type: "pause"}); return true; }
        if (k === "c") { this.app.toast("City Lab's garage and code panel come with its lessons (not in the game window yet either).", false, 4000); return true; }
        if ((k === "j" || k === "k" || k === "e" || k === "r") && this.myId() !== null) return true;  // (yours: play.js reads them)
        return false;
    }

    // H: the window's key list (city_client's FOOT_KEYS and CAR_KEYS, the teacher's after)
    keyList() {
        const teacher = this.app.state.role !== "learner";
        const rows = this.driving()
            ? [["W", "go"], ["S", "brake (then reverse)"], ["A D", "steer"], ["Shift", "drift"], ["B", "handbrake"], ["E", "get out (slowly)"]]
            : [["WASD", "walk (W is away from the camera)"], ["Shift", "run"], ["Space", "jump"], ["J", "punch"], ["K", "kick"], ["B", "block"], ["E", "get in"]];
        rows.push(["R", "back to the depot"], ["V", "view"], ["Wheel, + and -", "zoom"], ["Home", "the camera back to normal"], ["Tab/I", "HUD"]);
        if (teacher) rows.push(["L", "watch the next person"], ["Enter", "street race for everyone"], ["G", "everyone to the depot"], ["F", "mend your car"], ["P", "pause"]);
        rows.push(["N", "sound"], ["H", "help"]);
        return rows;
    }

    // the side panel's tabs: no Garage yet (City Lab's lessons, docs/plans/city-lab.md step 6, bring it)
    panelTabs(role) {
        if (role === "learner") return [...LEARNER_TABS.filter(([k]) => k !== "garage"), ["camera", "Camera"], ["graphics", "Settings"], ["about", "Keys"]];
        return [["controls", "Controls"], ...TEACHER_TABS, ["camera", "Camera"], ["mission", "My mission"], ["graphics", "Graphics"], ["about", "About"]];
    }

    tabs() { return [["controls", "Controls"], ["camera", "Camera"]]; }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${this.city ? this.city.name : L.city} · ${L.mode === "race" ? "street race" : "practice"}${this.paused ? " · PAUSED" : ""}` : "";
    }

    cameraPill() {
        const V = this.scene.view;
        return V.mode === "city" ? "Camera: the whole city (drag to orbit, wheel to zoom)" : `Camera: ${VIEW_NAMES[V.mode] || V.mode}${V.watch !== null ? `, watching ${this.nameOf(V.watch)}` : ""} (V to change)`;
    }

    // the Learners table's game columns
    learnerHead() { return ["Person", "Cash", "Job"]; }
    learnerCells(p) {
        const r = this.app.state.roster, esc = this.app.esc, pid = r && r.mine ? r.mine[p.name] : null;
        const e = pid !== null && pid !== undefined ? this.latest.get(pid) : null;
        const job = this.jobs && pid !== null && pid !== undefined ? (this.jobs.mine || {})[String(pid)] : null;
        return [e ? esc(e.link ? "driving" : "on foot") : "", e ? e.cash : "", job ? esc(job.kind) : ""];
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, R = S.rules || {}, send = app.send, esc = app.esc;
        if (tab === "controls") {
            if (!L) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return true; }
            const jobs = L.jobs || {}, hz = L.hazards || {};
            const num = (id, label, key, hi) => `<div class="row"><label>${label}</label><select id="${id}">${Array.from({length: hi + 1}, (_, n) =>
                `<option ${n === L[key] ? "selected" : ""}>${n}</option>`).join("")}</select></div>`;
            const racing = this.jobs && this.jobs.race && this.jobs.race.state === "racing";
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The city</h2>
              <div class="row">
                <button id="btn-start" class="go">${racing ? "A RACE IS ON" : "START A STREET RACE"}</button>
                <button id="btn-grid">EVERYONE TO THE DEPOT</button>
                <button id="btn-pause" class="${this.paused ? "on" : ""}">${this.paused ? "RESUME" : "PAUSE"}</button>
                <button id="btn-fix">MEND MY CAR</button>
              </div>
              <div class="note">START A STREET RACE puts everyone in a car on the line with the computer's racers (Enter does it too); EVERYONE TO THE DEPOT sends them back (G); PAUSE stops the city (P); MEND MY CAR mends yours (F).</div>
              <div class="row"><label>City</label><select id="sel-city">${Object.entries(R.cities || {}).map(([k, n]) => `<option value="${k}" ${k === L.city ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
              ${num("sel-traffic", "Traffic", "traffic", 30)}
              <div class="row"><label></label><button data-hz="traffic" class="${hz.traffic ? "on" : ""}">${hz.traffic ? "Traffic on" : "No traffic"}</button></div>
              ${num("sel-robots", "Robots", "robots", 20)}
              <div class="row"><label></label><button data-hz="robots" class="${hz.robots ? "on" : ""}">${hz.robots ? "Robots on" : "No robots"}</button></div>
              ${num("sel-parked", "Parked cars", "parked", 40)}
              ${num("sel-racers", "Racers", "racers", 6)}
              <div class="row"><label>Their level</label><select id="sel-level">${(R.cpu_levels || []).map(l => `<option ${l === L.cpu_level ? "selected" : ""}>${l}</option>`).join("")}</select></div>
              <div class="row"><label>The jobs</label>${(R.jobs || ["delivery", "taxi", "race", "roundup"]).map(k => `<button data-job="${k}" class="${jobs[k] !== false ? "on" : ""}">${{delivery: "Deliveries", taxi: "Taxi runs", race: "Street races", roundup: "Round-ups"}[k] || k}</button>`).join("")}</div>
              <div class="row"><label>Time of day</label>${[["day", "Day"], ["dusk", "Dusk"], ["night", "Night"]].map(([k, t]) => `<button data-time="${k}" class="${(L.time || "day") === k ? "on" : ""}">${t}</button>`).join("")}</div>
              <div class="note">Every window and page draws the city at that time; at dusk and night the headlights and the street lamps come on.</div>
              <div class="row"><label>Damage</label><button id="btn-damage" class="${L.damage !== false ? "on" : ""}">${L.damage !== false ? "On: walls and bumps dent a car (the GARAGE mends it)" : "Off"}</button></div>
              <div class="row"><label>Teacher in the city</label><button id="btn-tplayer" class="${L.teacher_player !== false ? "on" : ""}">${L.teacher_player !== false ? "Yes" : "No: watching"}</button></div>
              <div class="row"><label>Designs</label><button id="btn-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              ${app.restartRow()}`;
            const now = () => this.app.state.lesson || L;
            const lessonSend = patch => send({type: "lesson", lesson: patch});
            app.wireMissionRow(body);
            $("btn-start").onclick = () => send({type: "start"});
            $("btn-grid").onclick = () => send({type: "grid"});
            $("btn-pause").onclick = () => send({type: "pause"});
            $("btn-fix").onclick = () => send({type: "fix"});
            $("sel-city").onchange = e => lessonSend({city: e.target.value});
            for (const [sel, key] of [["sel-traffic", "traffic"], ["sel-robots", "robots"], ["sel-parked", "parked"], ["sel-racers", "racers"]]) {
                $(sel).onchange = e => lessonSend({[key]: Number(e.target.value)});
            }
            $("sel-level").onchange = e => lessonSend({cpu_level: e.target.value});
            body.querySelectorAll("button[data-hz]").forEach(b => b.onclick = () => lessonSend({hazards: {[b.dataset.hz]: !(now().hazards || {})[b.dataset.hz]}}));
            body.querySelectorAll("button[data-job]").forEach(b => b.onclick = () => {
                const on = Object.assign({delivery: true, taxi: true, race: true, roundup: true}, now().jobs || {});
                lessonSend({jobs: {...on, [b.dataset.job]: !on[b.dataset.job]}});
            });
            body.querySelectorAll("button[data-time]").forEach(b => b.onclick = () => lessonSend({time: b.dataset.time}));
            $("btn-damage").onclick = () => lessonSend({damage: now().damage === false});
            $("btn-tplayer").onclick = () => lessonSend({teacher_player: now().teacher_player === false});
            $("btn-lock").onclick = () => lessonSend({designs_locked: !now().designs_locked});
            app.wireRestartRow(body);
            return true;
        }
        if (tab === "camera") {
            const V = this.scene.view, people = ((S.roster || {}).people || []);
            const views = this.driving() ? CAR_VIEWS : [...FOOT_VIEWS, ...(S.role !== "learner" || this.myId() === null ? ["city"] : [])];
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row">${views.map(m => `<button data-view="${m}" class="${V.mode === m ? "on" : ""}">${VIEW_NAMES[m]}</button>`).join("")}</div>
              <div class="note">V changes the view, the wheel or + and - zoom, Home puts the camera back. The whole city: drag to orbit.</div>
              ${S.role !== "learner" ? `<h2>Watch someone</h2><div class="row">${people.map(p => `<button data-watch="${p.id}" class="${V.watch === p.id ? "on" : ""}">${esc(p.name)}</button>`).join("") || "<span class='note'>Nobody in the city yet</span>"}
                <button data-watch="" class="${V.watch === null ? "on" : ""}">${this.myId() !== null ? "Me" : "Nobody"}</button></div>
                <div class="note">L watches the next person.</div>` : ""}`;
            body.querySelectorAll("button[data-view]").forEach(b => b.onclick = () => { this.scene.setView(b.dataset.view); this.keepCamera(); app.updatePills(); app.renderPanel(); });
            body.querySelectorAll("button[data-watch]").forEach(b => b.onclick = () => {
                V.watch = b.dataset.watch === "" ? null : Number(b.dataset.watch);
                if (V.mode === "city" && V.watch !== null) this.scene.setView("behind");
                V.pos = null;
                app.updatePills();
                app.renderPanel();
            });
            return true;
        }
        return false;
    }

    dispose() {
        this.app.canvas.removeEventListener("wheel", this.wheel);
        document.body.classList.remove("cityscreen");
        this.hud.clear();
        this.scene.dispose();
    }
}
