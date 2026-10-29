// The story missions' places in Club Coders Live (CHANGE 199), built as the mission window builds them
// (shared-world-demo/wake_up_call.py): Mission 1's valley (its Valley: the hills, the grass with its squares, the
// power cell, the supply crate and its tools, the rockfall in the pass, Brookfield's paving, houses, street lamps and
// power supply, the BROOKFIELD sign) and Mission 2's hill road at night (its HillRoad: the road from Brookfield up to
// the radio mast, the lamp posts beside it lit as they are repaired, tonight's rockfalls, the fence and the fields),
// from the map the Missions server sends (mission_wake_up.MAP, mission_lights_out.MAP: 2 m a square, the same
// rocks in the same places from the prototype's tile hash). The robots are Robot Lab's (robot.js's RobotScene: TITAN
// or RAZORBACK holding the tool it picked up, the window's RobotModel; the others' robots dimmed with their names
// over them, its Ghost), in Robot Lab's lights and effects (rw_gfx.init, rw_fx): dusk over the valley, night on the
// hill road (the key light a dim blue moon). Every tier the page has: mesh and lines draw every face black and its
// edges in the line colour, the scenery round the map left out (as the window's), fading out far beyond the
// furthest the camera goes (LOOK_FADE); the lamps' and lights' lines dim and brighten with their glow; ultra adds
// the window's smooth robots (models/robot_ultra.json) and a glow.

/* global BABYLON */

import {TIERS, v3, gameQuat} from "./base3d.js";
import {toneMap} from "./pbr.js";
import {RobotScene, robotLook} from "./robot.js";
import {RobotFX, hprQuat, qmul, qrot, robotShapes, loadRobotModels, robotModelsData} from "./robotfx.js";
import {AfterFx} from "./kartfx.js";

export const SQ = 2.0;  // metres a square
const RIDE = 0.12;      // (lab_sim.RIDE: the body origin above the ground)
const LOOK_FADE = [160, 400];  // (wake_up_call.LOOK_FADE: the lines fade out beyond the camera's furthest)
const EXPOSURE = 0.7;
const SKY = {wake_up_call: [0.16, 0.22, 0.34], lights_out: [0.03, 0.04, 0.09]};  // (light_scene: dusk, night)
const SUN = [1.5, 1.42, 1.3], MOON = [0.38, 0.45, 0.75];
export const GHOST_TINT = [0.55, 0.6, 0.72];  // the others' robots, dimmed
const SIGN_PAINT = {blocks: [255, 235, 179], low: [255, 235, 179], lit: [255, 235, 179]};  // (BROOKFIELD's letters)
const LAMP_ON = [7.0, 5.4, 2.4], LAMP_OFF = [0.02, 0.02, 0.025];  // (HillRoad's lamp heads)

// the prototype's tile hash: the same rocks in the same places every time (wake_up_call.hashed, its 32-bit sums)
export function hashed(x, y, k = 0) {
    let h = (Math.imul(x, 374761393) + Math.imul(y, 668265263) + Math.imul(k, 2147483647)) >>> 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

// the map's direction (0 north, 1 east...) as a heading (degrees, anticlockwise from above)
export function heading(d) {
    return -90 * d;
}

// a heading's way forward on the ground: [x, y]
export function forward(h) {
    const a = h * Math.PI / 180;
    return [-Math.sin(a), Math.cos(a)];
}

// rw_mesh.prism: a convex profile [[y, z], ...] (in order) pushed out along x, as flat polygons for polyMesh
function prism(profile, hx, off = [0, 0, 0]) {
    const L = profile.map(([y, z]) => [off[0] - hx, off[1] + y, off[2] + z]);
    const R = profile.map(([y, z]) => [off[0] + hx, off[1] + y, off[2] + z]);
    const polys = [[L, [-1, 0, 0]], [R, [1, 0, 0]]], k = profile.length;
    const cy = profile.reduce((a, p) => a + p[0], 0) / k, cz = profile.reduce((a, p) => a + p[1], 0) / k;
    for (let i = 0; i < k; i++) {
        const j = (i + 1) % k, dy = profile[j][0] - profile[i][0], dz = profile[j][1] - profile[i][1];
        let n = [0, dz, -dy];  // (across the edge, pointing away from the middle)
        if (n[1] * ((profile[i][0] + profile[j][0]) / 2 - cy) + n[2] * ((profile[i][1] + profile[j][1]) / 2 - cz) < 0) n = [0, -dz, dy];
        const l = Math.hypot(n[1], n[2]) || 1;
        polys.push([[L[i], L[j], R[j], R[i]], [0, n[1] / l, n[2] / l]]);
    }
    return polys;
}

export class MissionScene extends RobotScene {
    static TIERS = TIERS;  // (every tier, as the mission window's: CHANGE 188)
    static TIER_TEXT = {lines: "lines: black, the outlines in one colour (an old vector arcade game): the squares, the hills, the houses and the robots.",
                        ultra: "ultra: for a strong graphics card: the window's smooth robots (round edges, tread, bolts, machined tools), soft 4096 shadows, a glow on the lamps."};

    constructor(canvas, tier, engine) {
        super(canvas, tier, engine, robotLook(), true);  // (built when the mission is known: setMission)
        this.mid = null;
        this.about = null;
        this.holders = new Map();  // key -> {key, design, name, ghost, tool, off, v}: each robot drawn
        this.placed = [];          // this frame's robots, as RobotScene.frame takes them
        this.view = {mode: "valley", zoom: 1, pan: [0, 0], at: null, h: 0, panel: 0};
        this.state = null;
        this.t = 0;
        this.flash = 0;
        this.camPos = null;
    }

    // the mission to draw ({map, nights, ...} from the server's welcome): the scene built again, its sky and light
    setMission(mid, about) {
        if (mid === this.mid && this.scene) return;
        this.mid = mid;
        this.about = about;
        this.W = about.map[0].length;
        this.H = about.map.length;
        this.state = null;
        const sky = SKY[mid] || SKY.wake_up_call;
        this.look.sky = toneMap(sky, Math.pow(2, EXPOSURE));  // (blocks: the window's tone curve over its background)
        this.look.pbr.background = sky;
        this.look.pbr.sun.colour = mid === "lights_out" ? MOON : SUN;
        this.build();
    }

    lineFade() { return LOOK_FADE; }

    render() { if (this.scene) super.render(); }

    drawCalls() { return this.scene ? super.drawCalls() : 0; }

    // a square (x across, y down the map) to the world: x east, y north, the map's middle at 0, 0
    world(x, y, z = 0) {
        return [(x - (this.W - 1) / 2) * SQ, ((this.H - 1) / 2 - y) * SQ, z];
    }

    find(ch) {
        for (let y = 0; y < this.H; y++) {
            const x = this.about.map[y].indexOf(ch);
            if (x >= 0) return [x, y];
        }
        return null;
    }

    populate() {
        const scene = this.scene;
        // (ultra: the window's smooth robots once models/robot_ultra.json is here, asked for on ultra alone; high's
        // robots until then, then everything made again with them)
        this.ultra = !!(this.settings.ultra && this.lighting);
        this.ultraArena = true;
        this.ultraRobots = false;
        if (this.ultra && !robotModelsData()) loadRobotModels().then(d => { if (d && this.scene === scene) this.build(); });
        this.wheelLines = {};
        this.glowLines = {};
        this.lineCount = 0;
        this.glows = {};   // name -> {mat, lines}: the parts that light up
        this.lit = [];     // [name, off, on]: what lights up when Brookfield's power comes back
        const t0 = performance.now();
        if (!this.mid) return;
        if (this.mid === "lights_out") this.buildRoad(); else this.buildValley();
        this.lineStats = {segments: this.lineCount, ms: Math.round(performance.now() - t0)};
        this.after = this.ultra ? new AfterFx(this, RobotScene.ULTRA_FX) : null;
        this.fx = new RobotFX(this);  // (rw_fx.Effects: the sparks, the rocks' burst)
        this.robots.clear();
        for (const h of this.holders.values()) h.v = null;  // (each made again when next placed)
        const cam = this.camera;  // (the window's: a horizontal field of view, placed every frame)
        cam.detachControl();
        cam.fovMode = BABYLON.Camera.FOVMODE_HORIZONTAL_FIXED;
        cam.minZ = 0.3;
        cam.maxZ = 600;
        cam.lowerRadiusLimit = 0.5;
        cam.upperRadiusLimit = 600;
        cam.lowerBetaLimit = 0.001;
        cam.upperBetaLimit = Math.PI - 0.001;
        this.camPos = null;
        if (this.state) this.show(this.state);
    }

    // ---------- the parts every mission's place is made of ----------
    // a material as rw_gfx.part gives one: a texture set or none, the colour, rough and metal (its defaults 1 and
    // 1), a glow, the texture's repeats per metre
    paint(name, tex, rgb, rough = 1, metal = 1, emission = null, tile = 1) {
        return this.material(name, rgb, rough, metal, 0, {tex: tex || "", tile, emission});
    }

    // a part that lights up (the window's glow): its own material, so it is lit or dark on its own
    glowPaint(name, rgb, off) {
        const m = this.paint("glow " + name, null, rgb, 0.4, 0, off);
        this.glows[name] = {mat: m, lines: null};
        return m;
    }

    setLit(name, emission) {
        const g = this.glows[name];
        if (!g) return;
        this.setGlow(g.mat, emission);
        if (g.lines) this.pulseLine(g.lines, Math.min(1, 0.3 + Math.max(...emission) / 6));  // (its lines as bright as its glow)
    }

    node(name, pos = [0, 0, 0], hpr = null, parent = null) {
        const n = new BABYLON.TransformNode(name, this.scene);
        if (parent) n.parent = parent;
        n.position = v3(...pos);
        if (hpr) n.rotationQuaternion = gameQuat(hprQuat(...hpr));
        return n;
    }

    turn(mesh, hpr) {
        mesh.rotationQuaternion = gameQuat(hprQuat(...hpr));
        return mesh;
    }

    // a moving part's lines (the line tiers): its meshes' edges (all under it, or those given), under it, in its own
    // material or the place's
    ownLines(node, mat = null, meshes = null) {
        if (!this.wire) return null;
        return this.linesMesh("missionlines", this.edgeLines(meshes || node.getChildMeshes(false), this.wire, node), mat || this.placeLines, node);
    }

    // the parts that never move, drawn together; their lines (the line tiers) in tiles; shadows from what stands up
    finishStill(still, flat, scenery) {
        if (this.wire) for (const m of scenery) m.dispose();  // (the hills round the map and the soil: not on mesh and lines)
        const merged = this.mergeStatic(still), ground = this.mergeStatic(flat);
        if (!this.wire) this.mergeStatic(scenery);
        this.shadowCast(merged);
        if (this.wire) this.staticLines("missionlines", this.edgeLines([...merged, ...ground], this.wire), this.placeLines);
    }

    // a square's ground (a paving slab, grass, the road): its own colour, the soil showing between as the grid
    square(list, x, y) {
        const p = this.world(x, y), g = SQ / 2 - 0.035;
        list.push(this.box(null, g, g, 0.04, null, p[0], p[1], -0.04));
        return list[list.length - 1];
    }

    // a rock wall square: boulders, higher towards the back so the valley can be seen from the south
    hill(list, mat, x, y) {
        const p = this.world(x, y), back = 1 - y / (this.H - 1);
        const inner = x > 0 && x < this.W - 1 && y > 0 && y < this.H - 1;  // (the cliff between the valley and the village)
        let height = 0.45 + (inner ? 1.5 : 0.4 + 2.2 * back) * (0.7 + 0.5 * hashed(x, y, 1));
        if (y === this.H - 1) height = 0.35 + 0.25 * hashed(x, y, 2);  // (the front row stays low: the camera looks over it)
        for (let k = 0; k < 3; k++) {
            const hx = SQ * (0.28 + 0.2 * hashed(x, y, k + 3)), hy = SQ * (0.28 + 0.2 * hashed(x, y, k + 6));
            const hz = height * (0.55 + 0.45 * hashed(x, y, k + 9)) / 2;
            const ox = (hashed(x, y, k + 12) - 0.5) * SQ * 0.45, oy = (hashed(x, y, k + 15) - 0.5) * SQ * 0.45;
            list.push(this.box(null, hx, hy, hz, mat, p[0] + ox, p[1] + oy, hz - 0.05));
        }
    }

    // hills round the valley, so it is a valley (the map's edge isn't the world's), and the soil under everything
    backdrop(scenery, soil) {
        const w = this.W * SQ / 2, h = this.H * SQ / 2;
        scenery.push(this.box(null, w + 30, h + 30, 0.1, this.paint("soil", "concrete", soil, 1, 0, null, 0.25), 0, 0, -0.14));
        const hills = this.paint("hills", "concrete", [0.3, 0.36, 0.24], 1, 0, null, 0.15);
        for (let i = 0; i < 26; i++) {
            const a = i / 26 * 2 * Math.PI, r = 1.15 + 0.25 * hashed(i, 7);
            const x = Math.cos(a) * w * r * 1.25, y = Math.sin(a) * h * r * 1.6;
            if (y < -h) continue;  // (none in front of the camera)
            const size = 3 + 4 * hashed(i, 3);
            scenery.push(this.box(null, size, size * 0.8, size * (0.5 + 0.6 * hashed(i, 5)), hills, x, y, 0));
        }
    }

    house(still, x, y) {
        const p = this.world(x, y);
        still.push(this.box(null, 0.75, 0.68, 0.6, this.paint("wall", "paint", [0.86, 0.8, 0.68], 0.9, 0), p[0], p[1], 0.6));
        const roof = this.polyMesh(prism([[-0.85, 0], [0.85, 0], [0, 0.6]], 0.85), this.paint("roof", "paint", [0.62, 0.22, 0.16], 0.8, 0), "roof");
        roof.position = v3(p[0], p[1], 1.2);
        still.push(this.turn(roof, [90, 0, 0]));
        still.push(this.box(null, 0.16, 0.02, 0.28, this.paint("door", "paint", [0.35, 0.22, 0.14]), p[0], p[1] - 0.69, 0.28));
        const glass = this.glows.windows ? this.glows.windows.mat : this.glowPaint("windows", [0.1, 0.11, 0.14], [0.01, 0.012, 0.02]);
        if (!this.lit.some(([n]) => n === "windows")) this.lit.push(["windows", [0.01, 0.012, 0.02], [5.0, 3.6, 1.4]]);
        for (const wx of [-0.42, 0.42]) still.push(this.box(null, 0.14, 0.015, 0.12, glass, p[0] + wx, p[1] - 0.69, 0.72));
        for (const sx of [-0.76, 0.76]) still.push(this.box(null, 0.015, 0.14, 0.12, glass, p[0] + sx, p[1], 0.72));
    }

    // the rockfall (in the pass, or on the road): a pile of boulders, and the rubble left when it's cleared
    rocks(x, y) {
        const p = this.world(x, y), pile = this.node("rockfall", p), parts = [];
        const colours = [[0.54, 0.42, 0.29], [0.63, 0.49, 0.34], [0.44, 0.34, 0.24]];
        for (let k = 0; k < 11; k++) {
            const s = 0.25 + 0.3 * hashed(x, y, k + 20);
            const pos = [(hashed(x, y, k + 30) - 0.5) * SQ * 0.8, (hashed(x, y, k + 40) - 0.5) * SQ * 0.75, s * 0.8 + (k > 6 ? 0.5 : 0)];
            const r = this.box(pile, s, s * 0.85, s * 0.8, this.paint("rock" + (k % 3), "concrete", colours[k % 3], 1, 0, null, 0.6), ...pos);
            this.turn(r, [hashed(x, y, k) * 90, hashed(x, y, k + 1) * 30 - 15, 0]);
            this.ownLines(r, null, [r]);  // (each boulder flies off on its own)
            parts.push([r, pos]);
        }
        const rubble = this.node("rubble", p), gravel = [], stone = this.paint("gravel", "concrete", [0.6, 0.55, 0.45], 1, 0);
        for (let k = 0; k < 14; k++) {
            const s = 0.05 + 0.06 * hashed(x, y, k + 50);
            gravel.push(this.box(rubble, s, s, s * 0.6, stone, (hashed(x, y, k + 60) - 0.5) * SQ * 0.9, (hashed(x, y, k + 70) - 0.5) * SQ * 0.9, s * 0.5));
        }
        this.mergeParts(gravel, rubble);
        this.ownLines(rubble);
        this.shadowCast([...pile.getChildMeshes(), ...rubble.getChildMeshes()]);
        rubble.setEnabled(false);
        return {pile, rubble, parts};
    }

    // a rockfall flying apart as the spinner grinds through it (k from 0 to 1); side: which way it goes (y)
    clearing(r, k, side) {
        r.pile.setEnabled(true);
        r.parts.forEach(([m, pos], i) => {
            const a = i * 2.4, out = [Math.cos(a) * k * 2.2, (Math.sin(a) * 0.5 + side) * k * 2.2];
            m.position = v3(pos[0] + out[0], pos[1] + out[1], pos[2] + 2.5 * k * (1 - k));
            m.scaling.setAll(Math.max(0.05, 1 - k));
        });
    }

    restRocks(r) {
        for (const [m, pos] of r.parts) { m.position = v3(...pos); m.scaling.setAll(1); }
    }

    // ---------- Mission 1: the valley (Valley) ----------
    buildValley() {
        const map = this.about.map, still = [], flat = [], scenery = [];
        this.placeLines = this.wire ? this.lineMaterial("mission", 1, ...LOOK_FADE) : null;
        const grass = [[0.42, 0.58, 0.26], [0.36, 0.52, 0.22]].map((c, i) => this.paint("grass" + i, "concrete", c, 1, 0, null, 0.5));
        const paving = this.paint("paving", "concrete", [0.78, 0.71, 0.55], 0.9, 0, null, 0.7);
        const rock = this.paint("hillrock", "concrete", [0.46, 0.44, 0.42], 1, 0, null, 0.6);
        map.forEach((row, y) => [...row].forEach((t, x) => {
            if ("VHG".includes(t)) this.square(flat, x, y).material = paving;
            else if (t !== "#") this.square(flat, x, y).material = grass[(x + y) % 2];
            else this.hill(still, rock, x, y);
        }));
        this.backdrop(scenery, [0.25, 0.22, 0.16]);
        // the crash landing's two skid marks behind the start
        const [sx, sy] = this.find("S"), sp = this.world(sx, sy), mark = this.paint("skid", null, [0.12, 0.09, 0.06], 1, 0);
        for (const s of [-1, 1]) flat.push(this.turn(this.box(null, 0.09, 0.75, 0.005, mark, sp[0] + s * 0.42 + 0.3, sp[1] - 0.7, 0.003), [-24, 0, 0]));
        // street lamps round the village square: dark until the power comes back
        const pole = this.paint("pole", "steel", [0.2, 0.21, 0.23]), lamp = this.glowPaint("streetlamps", [0.15, 0.15, 0.15], [0.02, 0.02, 0.02]);
        this.lit.push(["streetlamps", [0.02, 0.02, 0.02], [6, 5, 2.5]]);
        for (const [x, y] of [[9, 2], [14, 2], [9, 6], [14, 6], [12, 4]]) {
            const p = this.world(x, y), ox = p[0] + (x < 12 ? 0.75 : -0.75), oy = p[1] + 0.75;
            still.push(this.cyl(null, 0.045, 1.1, "z", pole, ox, oy, 1.1, null, 10));
            still.push(this.cyl(null, 0.13, 0.08, "z", lamp, ox, oy, 2.25, null, 14));
        }
        map.forEach((row, y) => [...row].forEach((t, x) => { if (t === "H") this.house(still, x, y); }));
        this.sign(still);
        this.finishStill(still, flat, scenery);
        const [gx, gy] = this.find("G"), [cx, cy] = this.find("C"), [tx, ty] = this.find("T"), [rx, ry] = this.find("R");
        this.supply = this.powerSupply(gx, gy);
        this.cell = this.powerCell(cx, cy);
        this.crate = this.supplyCrate(tx, ty);
        this.rockfall = this.rocks(rx, ry);
    }

    // BROOKFIELD on a board on the cliff above the village
    sign(still) {
        const p = this.world(11.5, 1), wood = this.paint("signpost", "paint", [0.4, 0.27, 0.15]);
        for (const s of [-1, 1]) still.push(this.cyl(null, 0.07, 0.9, "z", wood, p[0] + s * 1.9, p[1], 2.4, null, 8));
        still.push(this.box(null, 2.3, 0.06, 0.42, this.paint("signboard", "paint", [0.32, 0.2, 0.1]), p[0], p[1], 3.2));
        const words = this.words("BROOKFIELD", 0.52, SIGN_PAINT, [p[0], p[1] - 0.07, 3.06], [0, 0, 0]);
        if (this.wire) this.lettering(words);
    }

    // the village power supply: a cabinet with a lightning bolt, its warning light blinking until it's mended
    powerSupply(x, y) {
        const root = this.node("power supply", this.world(x, y));
        this.box(root, 0.55, 0.42, 0.75, this.paint("cabinet", "steel", [0.25, 0.33, 0.45], 0.6, 0.8, null, 1.5), 0, 0, 0.75);
        this.box(root, 0.62, 0.5, 0.05, this.paint("cabinettop", "steel", [0.2, 0.22, 0.25]), 0, 0, 1.53);
        const polys = [];  // a lightning bolt on each face, in two convex pieces
        for (const side of [-1, 1]) {
            polys.push(...prism([[-0.12, 0.04], [0, 0.04], [0.1, 0.32], [-0.02, 0.32]], 0.012, [side * 0.435, 0, 0]));
            polys.push(...prism([[-0.06, 0.08], [0.12, 0.08], [-0.02, -0.3]], 0.012, [side * 0.435, 0, 0]));
        }
        const boltNode = this.node("bolt", [0, 0, 0.85], [90, 0, 0], root);
        this.polyMesh(polys, this.glowPaint("bolt", [0.35, 0.36, 0.4], [0.05, 0.05, 0.05]), "bolt").parent = boltNode;
        this.lit.push(["bolt", [0.05, 0.05, 0.05], [8, 6, 0.6]]);
        this.ownLines(root);
        const warning = this.node("warning", [0.4, 0.3, 1.62], null, root);
        this.cyl(warning, 0.06, 0.05, "z", this.glowPaint("warning", [0, 0, 0], [6, 0.4, 0.2]), 0, 0, 0, null, 12);
        if (this.wire) this.glows.warning.lines = this.lineMaterial("warning", 1, ...LOOK_FADE);
        this.ownLines(warning, this.glows.warning.lines);
        this.shadowCast(root.getChildMeshes());
        return root;
    }

    powerCell(x, y) {
        const root = this.node("power cell", this.world(x, y));
        const base = this.cyl(root, 0.5, 0.03, "z", this.paint("cellbase", "steel", [0.3, 0.32, 0.35]), 0, 0, 0.03, null, 28);
        this.ownLines(root, null, [base]);
        const body = this.cellBody = this.node("cell", [0, 0, 0], null, root);  // (it bobs and turns: its lines with it)
        this.cyl(body, 0.2, 0.32, "z", this.paint("cellbody", "paint", [0.16, 0.45, 0.26], 0.5, 0.3), 0, 0, 0.62, null, 20);
        this.cyl(body, 0.08, 0.06, "z", this.paint("cellcap", "steel", [0.7, 0.7, 0.72]), 0, 0, 1.0, null, 12);
        this.cyl(body, 0.205, 0.12, "z", this.paint("cellglow", null, [0, 0, 0], 0.3, 0, [0.6, 3.2, 1.2]), 0, 0, 0.62, null, 20);
        this.ownLines(body);
        this.shadowCast(root.getChildMeshes());
        return root;
    }

    // the supply crate, with the four tools on it (the one the robot holds isn't)
    supplyCrate(x, y) {
        const p = this.world(x, y), root = this.node("supply crate", [p[0], p[1] + 0.35, 0]);
        const steel = [0.75, 0.77, 0.8], S = (n, rgb) => this.paint(n, "steel", rgb);
        this.box(root, 0.85, 0.5, 0.3, this.paint("crate", "paint", [0.62, 0.45, 0.25], 0.9, 0, null, 1.2), 0, 0, 0.3);
        for (const s of [-1, 1]) this.box(root, 0.87, 0.52, 0.03, this.paint("crateband", "paint", [0.4, 0.28, 0.15]), 0, 0, 0.3 + s * 0.2);
        this.ownLines(root);
        const tools = {};
        ["spinner", "flipper", "hammer", "drum"].forEach((name, k) => {
            const t = this.node(name, [-0.6 + k * 0.4, 0, 0.64], null, root);
            if (name === "spinner") {
                this.box(t, 0.17, 0.035, 0.02, S("toolsteel", steel));
                this.cyl(t, 0.035, 0.03, "z", S("toolhub", [0.3, 0.3, 0.32]), 0, 0, 0, null, 12);
            } else if (name === "flipper") {
                this.polyMesh(prism([[-0.15, -0.03], [0.15, -0.03], [0.1, 0.06], [-0.1, 0.06]], 0.13), S("toolsteel", steel), "flipper").parent = t;
            } else if (name === "hammer") {
                this.box(t, 0.02, 0.16, 0.02, S("toolarm", [0.4, 0.4, 0.42]), 0, -0.02, 0);
                this.box(t, 0.07, 0.05, 0.05, S("toolhead", [0.25, 0.25, 0.27]), 0, 0.15, 0.02);
            } else {
                this.cyl(t, 0.06, 0.13, "x", S("toolsteel", steel), 0, 0, 0, null, 16);
            }
            this.ownLines(t);
            tools[name] = t;
        });
        this.tools = tools;
        this.shadowCast(root.getChildMeshes());
        return root;
    }

    // ---------- Mission 2: the hill road at night (HillRoad) ----------
    buildRoad() {
        const A = this.about, map = A.map, still = [], flat = [], scenery = [];
        this.placeLines = this.wire ? this.lineMaterial("mission", 1, ...LOOK_FADE) : null;
        const grass = [[0.2, 0.32, 0.16], [0.17, 0.28, 0.13]].map((c, i) => this.paint("nightgrass" + i, "concrete", c, 1, 0, null, 0.5));
        const road = this.paint("road", "concrete", [0.3, 0.3, 0.32], 0.95, 0, null, 0.7);
        const paving = this.paint("nightpaving", "concrete", [0.62, 0.56, 0.44], 0.9, 0, null, 0.7);
        const field = this.paint("field", "concrete", [0.3, 0.27, 0.15], 1, 0, null, 0.5);
        const rock = this.paint("nightrock", "concrete", [0.36, 0.35, 0.34], 1, 0, null, 0.6);
        map.forEach((row, y) => [...row].forEach((t, x) => {
            if ("VH".includes(t)) this.square(flat, x, y).material = paving;
            else if (".SM".includes(t)) this.square(flat, x, y).material = road;
            else if (t === "~") this.square(flat, x, y).material = field;
            else if ("LF".includes(t)) this.square(flat, x, y).material = grass[(x + y) % 2];
            else this.hill(still, rock, x, y);
        }));
        this.backdrop(scenery, [0.12, 0.13, 0.1]);
        const wood = this.paint("fence", "paint", [0.4, 0.3, 0.2], 0.9, 0);
        map.forEach((row, y) => [...row].forEach((t, x) => {
            if (t === "H") this.house(still, x, y);
            else if (t === "F") {  // a post and two rails on the road's downhill side
                const p = this.world(x, y);
                still.push(this.box(null, 0.06, 0.06, 0.4, wood, p[0] - 0.9, p[1] + 0.6, 0.4));
                for (const z of [0.35, 0.65]) still.push(this.box(null, 1.0, 0.03, 0.04, wood, p[0], p[1] + 0.6, z));
            }
        }));
        this.finishStill(still, flat, scenery);
        this.lamps = {};
        for (const x of A.lamps) this.lamps[x] = this.lampPost(x, A.road_y - 1);
        this.mast = this.radioMast(A.mast.x, A.mast.y);
        this.piles = {};  // each road square a rock falls on some night: its pile and the rubble left when it's cleared
        for (const x of [...new Set(A.nights.flatMap(n => n.rocks))].sort((a, b) => a - b)) this.piles[x] = this.rocks(x, A.road_y);
    }

    // a street lamp on the bank above the road, its head over the road: dark until it's repaired
    lampPost(x, y) {
        const p = this.world(x, y), root = this.node("lamp " + x, [p[0], p[1] - 0.55, 0]), steel = this.paint("lamppost", "steel", [0.2, 0.21, 0.23]);
        this.box(root, 0.25, 0.25, 0.08, this.paint("lampbase", "concrete", [0.35, 0.35, 0.36]), 0, 0, 0.08);
        this.cyl(root, 0.055, 1.4, "z", steel, 0, 0, 1.4, null, 10);
        this.box(root, 0.04, 0.4, 0.04, steel, 0, -0.38, 2.78);
        this.ownLines(root);
        const head = this.node("lamp head", [0, -0.72, 2.72], null, root), name = "lamp" + x;
        this.cyl(head, 0.16, 0.07, "z", this.glowPaint(name, [0.15, 0.15, 0.15], [0.02, 0.02, 0.02]), 0, 0, 0, null, 14);
        if (this.wire) this.glows[name].lines = this.lineMaterial(name, 1, ...LOOK_FADE);
        this.ownLines(head, this.glows[name].lines);
        this.shadowCast(root.getChildMeshes());
        return root;
    }

    // the radio mast at the top of the road: a lattice tower, a dish and a light that blinks red until the night's
    // report arrives
    radioMast(x, y) {
        const root = this.node("radio mast", this.world(x, y)), steel = this.paint("mast", "steel", [0.55, 0.57, 0.6]);
        this.box(root, 0.7, 0.7, 0.12, this.paint("mastbase", "concrete", [0.4, 0.4, 0.42]), 0, 0, 0.12);
        for (const sx of [-1, 1]) for (const sy of [-1, 1]) this.turn(this.box(root, 0.04, 0.04, 2.6, steel, sx * 0.3, sy * 0.3, 2.7), [0, sy * -3, sx * 3]);
        for (const z of [1.0, 2.2, 3.4, 4.5]) { const w = 0.36 - z * 0.035; this.box(root, w, w, 0.025, steel, 0, 0, z); }
        this.cyl(root, 0.32, 0.06, "x", this.paint("dish", "paint", [0.85, 0.86, 0.88]), -0.3, 0, 3.8, null, 18);
        this.box(root, 0.25, 0.2, 0.3, this.paint("mastbox", "paint", [0.85, 0.82, 0.3], 0.6, 0.1), 0, -0.55, 0.42);
        this.ownLines(root);
        const light = this.node("mast light", [0, 0, 5.4], null, root);
        this.cyl(light, 0.08, 0.06, "z", this.glowPaint("mastlight", [0, 0, 0], [6, 0.4, 0.2]), 0, 0, 0, null, 12);
        if (this.wire) this.glows.mastlight.lines = this.lineMaterial("mastlight", 1, ...LOOK_FADE);
        this.ownLines(light, this.glows.mastlight.lines);
        this.shadowCast(root.getChildMeshes());
        return root;
    }

    // ---------- the mission's state shown (each scene's show, as the window asks it) ----------
    show(s) {
        this.state = s;
        if (!this.scene || !s) return;
        if (this.mid === "lights_out") {
            const night = this.about.nights[(s.night || 1) - 1] || this.about.nights[0];
            for (const [xs, r] of Object.entries(this.piles || {})) {
                const x = Number(xs), here = (s.rocks || []).includes(x);
                r.pile.setEnabled(here);
                if (here) this.restRocks(r);
                r.rubble.setEnabled(night.rocks.includes(x) && !here);
            }
            for (const x of Object.keys(this.lamps || {})) this.setLit("lamp" + x, (s.dark || []).includes(Number(x)) ? LAMP_OFF : LAMP_ON);
            for (const [name, , on] of this.lit) this.setLit(name, on);  // (Brookfield's windows: lit since Mission 1)
            return;
        }
        if (this.cell) this.cell.setEnabled(!s.cellTaken);
        for (const [name, t] of Object.entries(this.tools || {})) t.setEnabled(name !== s.tool);
        if (this.rockfall) {
            this.rockfall.pile.setEnabled(!s.rockCleared);
            this.rockfall.rubble.setEnabled(!!s.rockCleared);
            if (!s.rockCleared) this.restRocks(this.rockfall);
        }
        for (const [name, off, on] of this.lit) this.setLit(name, s.repaired ? on : off);
    }

    // the mission back at its start: the power cell as it was before it was picked up
    reset() {
        this.flash = 0;
        if (this.cellBody) { this.cellBody.scaling.setAll(1); this.cellBody.position.y = 0; }
    }

    cleared(ev, before) {  // (Mission 2: the road square a use cleared, or null)
        const gone = (before.rocks || []).filter(x => !(ev.state.rocks || []).includes(x));
        return gone.length && ev.type === "use" ? gone[0] : null;
    }

    // an event k (0 to 1) of the way through: the rocks flying apart, the power cell lifting into the robot, a lamp
    // coming on as it's repaired
    animate(ev, before, k, eventT) {
        const sparks = Math.floor(eventT * 30) % 3 === 0;
        if (this.mid === "lights_out") {
            const x = this.cleared(ev, before);
            if (x !== null && this.piles[x]) {
                this.clearing(this.piles[x], k, -0.6);
                const p = this.world(x, this.about.road_y);
                if (sparks) this.stream([p[0] - 0.8, p[1], 0.4], [-1, 0, 0.6], 3);
            }
            if (ev.type === "repair") {
                const fixed = (before.dark || []).filter(lx => !(ev.state.dark || []).includes(lx));
                if (fixed.length) { const b = k * k; this.setLit("lamp" + fixed[0], [LAMP_ON[0] * b, LAMP_ON[1] * b, LAMP_ON[2] * b]); }
            }
            return;
        }
        if (ev.type === "use" && ev.state.rockCleared && !before.rockCleared && this.rockfall) {
            this.clearing(this.rockfall, k, 0.6);
            const p = this.rockfall.pile.position;
            if (sparks) this.stream([p.x, p.z - 0.8, 0.4], [0, -1, 0.6], 3);
        }
        if (ev.type === "objective" && ev.state.cellTaken && !before.cellTaken && this.cellBody) {
            this.cellBody.position.y = 1.5 * k;  // (Babylon's y: the game's z)
            this.cellBody.scaling.setAll(Math.max(0.05, 1 - k));
        }
    }

    settle(ev) {  // (an event's animation over, before its state is shown)
        if (this.mid !== "lights_out" && ev.state.cellTaken && this.cellBody) this.cellBody.scaling.setAll(1);
    }

    // an event done: the rocks' burst as a rockfall clears, the sparks as the power comes back or a report arrives
    landed(ev, before) {
        const fx = this.fx;
        if (!fx) return;
        if (this.mid === "lights_out") {
            const x = this.cleared(ev, before), top = this.mast ? [this.mast.position.x, this.mast.position.z, 5.4] : [0, 0, 5.4];
            if (x !== null) { const p = this.world(x, this.about.road_y); fx.impact([p[0], p[1], 0.6], 40, "break", [0.5, 0.45, 0.4]); }
            if (ev.type === "report" && ev.tone === "ok") { this.flash = 0.8; fx.impact(top, 18, "spinner", [0.5, 1, 0.6]); }
            if (ev.type === "complete") fx.impact(top, 30, "spinner", [1, 0.9, 0.4]);
            return;
        }
        if (ev.state.rockCleared && !before.rockCleared && this.rockfall) {
            const p = this.rockfall.pile.position;
            fx.impact([p.x, p.z, 0.6], 40, "break", [0.55, 0.43, 0.3]);
        }
        if (ev.type === "complete" && this.supply) fx.impact([this.supply.position.x, this.supply.position.z, 1.6], 25, "spinner", [1, 0.9, 0.4]);
    }

    // the scenery's own movement each frame: the power cell bobbing and turning, the warning light, the mast's light
    updateScenery(dt) {
        this.t += dt;
        this.flash = Math.max(0, this.flash - dt);
        const s = this.state, blink = Math.floor(this.t * 2) % 2 === 0;
        if (this.mid === "lights_out") {
            const done = !!(s && (s.reported || s.complete));
            this.setLit("mastlight", done || this.flash > 0 ? [0.3, 5, 0.6] : blink ? [6, 0.4, 0.2] : [0.3, 0.02, 0.01]);
            return;
        }
        if (s && !s.cellTaken && this.cellBody && this.cellBody.scaling.x === 1) {  // the power cell bobs and turns, to be seen
            this.cellBody.position.y = 0.08 * Math.sin(this.t * 2.2);
            this.cellBody.rotation.y = -this.t * 40 * Math.PI / 180;
        }
        this.setLit("warning", s && s.repaired ? [0.3, 5, 0.6] : blink ? [6, 0.4, 0.2] : [0.3, 0.02, 0.01]);
    }

    // ---------- the robots (the window's RobotModel and Ghost) ----------
    // key: "me" or a classmate's name; design: Robot Lab's; ghost: someone else's (dimmed, their name over it)
    holdRobot(key, design, name, ghost) {
        let h = this.holders.get(key);
        if (!h || JSON.stringify(h.design) !== JSON.stringify(design) || h.ghost !== ghost) {
            if (h && h.v) this.dropModel(h);
            const a = hashed(name.length, [...name].reduce((n, c) => n + c.charCodeAt(0), 0), 3) * 2 * Math.PI;
            h = {key, design, name, ghost, tool: undefined, v: null,
                 off: ghost ? [Math.cos(a) * 0.45, Math.sin(a) * 0.45] : [0, 0]};  // (two on one square both show)
            this.holders.set(key, h);
        }
        return h;
    }

    dropRobot(key) {
        const h = this.holders.get(key);
        if (!h) return;
        if (h.v) this.dropModel(h);
        this.holders.delete(key);
    }

    dropModel(h) {
        if (this.robots.get(h.key) === h.v) this.robots.delete(h.key);
        try { this.disposeRobot(h.v); } catch (e) { /* the scene already gone */ }
        h.v = null;
    }

    // the robot holding a tool (Robot Lab's weapon for it); no tool yet: the robot's own weapon, not fitted
    model(h) {
        const tools = this.about.tools || {}, own = !(h.tool in tools);
        const v = this.addRobot({id: h.key, design: Object.assign({}, h.design, {weapon: own ? h.design.weapon : tools[h.tool].weapon}), owner: ""});
        v.noWeapon = own;
        if (own && v.blur) v.blur.isVisible = false;
        if (h.ghost) {  // (its owner's name on a dark card over it, as the window's Ghost)
            v.label.dispose(false, true);
            v.label = this.makeLabel(h.name, "#ffffff", 3.0, true);
        }
        const sh = robotShapes(v.weaponType, v.s, false);
        h.pivot = sh.pivot.map(c => c * sh.k);
        h.rest = 0;
        if (v.weaponType === "wedge") {  // the flipper's plate rests with its front lip on the ground
            const drop = h.pivot[2] + RIDE - 0.02;
            h.rest = -Math.asin(Math.min(1, drop / (sh.plate[1] * sh.k * 2))) * 180 / Math.PI;
        }
        h.v = v;
        return v;
    }

    // where a robot is this frame (x, y: squares, fractions between; h: its heading) and how far through using its
    // tool (use, 0 to 1); speed turns its wheels, nudge pushes it forward (a bump)
    placeRobot(key, tool, x, y, h, speed = 0, use = 0, nudge = 0) {
        const hd = this.holders.get(key);
        if (!hd || !this.scene) return;
        tool = tool || "none";
        if (hd.tool !== tool && hd.v) this.dropModel(hd);
        hd.tool = tool;
        if (!hd.v) this.model(hd);
        const q = hprQuat(h, 0, 0), f = qrot(q, [0, 1, 0]), p = this.world(x, y);
        const at = [p[0] + hd.off[0] + f[0] * nudge, p[1] + hd.off[1] + f[1] * nudge, RIDE];
        const kind = hd.v.noWeapon ? null : hd.v.weaponType, swing = Math.sin(Math.PI * use);
        let local = hprQuat(0, hd.rest, 0), rpm = 0;
        if (kind === "spinner" || kind === "drum") rpm = 1400 * swing;
        else if (kind === "wedge") local = hprQuat(0, hd.rest + swing * (40 - hd.rest), 0);
        else if (kind === "hammer") local = hprQuat(0, use < 0.45 ? 105 * Math.sin(Math.PI * Math.min(1, use / 0.45)) : -18 * Math.sin(Math.PI * (use - 0.45) / 0.55), 0);
        const w = qrot(q, hd.pivot);
        this.placed.push({id: key, pos: at, quat: q, wpos: [at[0] + w[0], at[1] + w[1], at[2] + w[2]], wquat: qmul(q, local),
                          rpm, speed, hp: 1, max: 1, tint: hd.ghost ? GHOST_TINT : null});
    }

    // ---------- each frame ----------
    // the robots placed this frame drawn (RobotScene.frame: their wheels, weapons, colours and the effects), the
    // labels where the window has them, the scenery's lights, the camera
    frame(dt, t) {
        if (!this.scene) return;
        const placed = this.placed;
        this.placed = [];
        super.frame({robots: placed}, dt, t);
        for (const r of placed) {
            const v = this.robots.get(r.id), h = this.holders.get(r.id);
            if (!v || !h) continue;
            if (v.noWeapon) v.weapon.setEnabled(false);
            if (h.ghost) v.label.position = v3(r.pos[0], r.pos[1], 2.3);
            else v.label.setEnabled(false);
        }
        this.updateScenery(dt);
    }

    // the window's place_camera: the whole valley from the south (zoom 1), following the robot from behind and
    // above, or straight down; the right mouse button's pan; eased there; the shake from a big hit. With the code
    // panel open (view.panel: the share of the screen it covers) the picture moves into the space left of it
    updateCamera(st, dt) {
        const V = this.view, cam = this.camera, z = V.zoom;
        const middle = this.world((this.W - 1) / 2, (this.H - 1) / 2 + 0.6);
        const target = V.at ? this.world(V.at[0], V.at[1]) : this.world((this.W - 1) / 2, (this.H - 1) / 2);
        let want, look, fov;
        if (V.mode === "follow") {
            const f = forward(V.h);
            want = [target[0] - f[0] * 4.5 * z, target[1] - f[1] * 4.5 * z, 6 * z];  // (high: over the roofs)
            look = [target[0] + f[0] * 2.5, target[1] + f[1] * 2.5, 0];
            fov = 60;
        } else if (V.mode === "above") {
            want = [middle[0], middle[1] - 0.01, 30 * z];
            look = middle;
            fov = 62;
        } else {
            want = [middle[0], middle[1] - 22 * z, 23 * z];
            look = [middle[0], middle[1] + 1, 0];
            fov = 58;
        }
        want = [want[0] + V.pan[0], want[1] + V.pan[1], want[2]];
        look = [look[0] + V.pan[0], look[1] + V.pan[1], look[2]];
        if (V.panel > 0) {  // (sideways by half the panel's share of what the camera sees there)
            const d = [look[0] - want[0], look[1] - want[1], look[2] - want[2]], far = Math.hypot(...d), side = Math.hypot(d[0], d[1]) || 1;
            const k = V.panel * far * Math.tan(fov * Math.PI / 360);
            want = [want[0] + d[1] / side * k, want[1] - d[0] / side * k, want[2]];
            look = [look[0] + d[1] / side * k, look[1] - d[0] / side * k, look[2]];
        }
        if (!this.camPos || dt >= 1) { this.camPos = want; this.camLook = look; }
        else {
            const k = Math.min(1, dt * 4);
            this.camPos = this.camPos.map((c, i) => c + (want[i] - c) * k);
            this.camLook = this.camLook.map((c, i) => c + (look[i] - c) * k);
        }
        const s = this.fx ? this.fx.shakeOffset() : null, p = s ? this.camPos.map((c, i) => c + s[i]) : this.camPos;
        cam.fov = fov * Math.PI / 180;
        cam.setTarget(v3(...this.camLook));
        cam.setPosition(v3(...p));
    }
}
