// Robot Lab in Club Coders Live (CHANGE 130): the arena (lab_sim.py's constants, drawn after rw_gfx.ArenaVisual),
// its hazards from each snapshot (the drop zone, floor flipper, saws, wall spikes, Resident Robots, the user mods),
// the robots built from their designs with their weapons, the 30-a-second JSON states blended two behind, and the
// teacher's Robot Lab controls. Positions are game (x, y, z) -> Babylon (x, z, y); quaternions via gameQuat.

/* global BABYLON */

import {BaseScene, v3, col, rgb255, gameQuat, slerpQ, lerp} from "./base3d.js";

const $ = id => document.getElementById(id);
const ARENA = 20;
const PIT = [3.2, 3.2, 3.0], FF = [-3.5, -3.5], SAWS = [[4.5, -3.5], [-5.0, 3.5]];
const SPIKE_PIT = [-3.5, 7.0, 2.4], FLAME_PIT = [0, 0, 2.4], BOOST_PAD = [9.0, -3.0, 1.6], REPAIR_BAY = [-9.0, -4.0, 1.6];
const RAMPS = [[6.7, -2.1, -1], [-6.7, -2.1, 1]];
const STARTS = [[-7.5, 0], [7.5, 0], [-3.5, -7.5], [0, -7.5], [3.5, 7.5], [0, 7.5]];
const START_COLOURS = [[0.9, 0.25, 0.2], [0.25, 0.55, 1], [0.3, 0.85, 0.4], [1, 0.8, 0.2], [0.8, 0.4, 1], [1, 0.5, 0.2]];
const HOUSE_WEAPONS = {BLAZE: "flame", CRUSHER: "hammer", RIPSAW: "chainsaw", VORTEX: "vdisc"};
const SPINNERS = new Set(["spinner", "drum", "vdisc"]);
const STEEL = [0.6, 0.62, 0.66], DARK = [0.12, 0.12, 0.13], YELLOW = [0.95, 0.75, 0.08];
const LEVELS = [["none", "No brain"], ["empty", "Empty"], ["easy", "Easy"], ["medium", "Medium"], ["expert", "Expert"]];

function designSize(d) {
    if (d.house) return 1.6;
    const s = ((d.settings || {}).size || 100) / 100;
    return d.model ? 1.6 * s : s;
}

export class RobotScene extends BaseScene {
    constructor(canvas, tier, engine) {
        super(canvas, tier, engine, {sky: [0.1, 0.11, 0.14], fog: [0.1, 0.11, 0.14], fogDensity: 0.006, radius: 26,
                                     target: [0, 0, 0], shadowSize: 34, ground: [0.25, 0.25, 0.28], sunDir: [-0.3, -0.85, 0.4]});
        this.setup = {hazards: {}, user_mods: {}, look: {}};
        this.robots = new Map();
        this.designs = [];
        this.mode = "overview";
        this.follow = null;
        this.sparks = [];
        this.build();
    }

    populate() {
        this.buildArena();
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

    // ---------- the arena ----------
    buildArena() {
        const hz = this.setup.hazards || {}, mods = this.setup.user_mods || {}, look = this.setup.look || {};
        const noCage = !!mods.no_cage;
        const plate = this.material("plate", this.tier === "blocks" ? [0.58, 0.59, 0.62] : [0.42, 0.43, 0.46], 0.55, 0.6);
        const dark = this.material("dark", DARK, 0.8);
        const steel = this.material("steel", STEEL, 0.4, 0.8);
        const yellow = this.material("yellow", YELLOW, 0.6);
        const wall = this.material("wall", rgb255(look.wall_colour, [155, 25, 20]), 0.7);
        const statics = [];
        // the floor, with holes for the drop zone and the flipper (and the pits a mod adds)
        const holes = [[PIT[0] - 1.5, PIT[1] - 1.5, PIT[0] + 1.5, PIT[1] + 1.5], [-5, -4.5, -2, -2.5]];
        if (mods.spike_pit) holes.push([SPIKE_PIT[0] - 1.2, SPIKE_PIT[1] - 1.2, SPIKE_PIT[0] + 1.2, SPIKE_PIT[1] + 1.2]);
        if (mods.flame_pit) holes.push([-1.2, -1.2, 1.2, 1.2]);
        const xs = [...new Set([-10, 10, ...holes.flatMap(h => [h[0], h[2]])])].sort((a, b) => a - b);
        const ys = [...new Set([-10, 10, ...holes.flatMap(h => [h[1], h[3]])])].sort((a, b) => a - b);
        const tiles = [];
        for (let i = 0; i < xs.length - 1; i++) {
            for (let j = 0; j < ys.length - 1; j++) {
                const cx = (xs[i] + xs[i + 1]) / 2, cy = (ys[j] + ys[j + 1]) / 2;
                if (holes.some(h => cx > h[0] && cx < h[2] && cy > h[1] && cy < h[3])) continue;
                tiles.push(this.box(null, (xs[i + 1] - xs[i]) / 2, (ys[j + 1] - ys[j]) / 2, 0.25, plate, cx, cy, -0.25));
            }
        }
        const floor = BABYLON.Mesh.MergeMeshes(tiles, true);
        floor.receiveShadows = this.lit;
        // markings: the Resident Robots' corner squares, the start squares, the centre circle, the arena's name
        for (const cx of [-1, 1]) for (const cy of [-1, 1]) {
            statics.push(this.box(null, 2.4, 2.4, 0.006, yellow, cx * 7.6, cy * 7.6, 0.006));
            statics.push(this.box(null, 2.15, 2.15, 0.006, dark, cx * 7.6, cy * 7.6, 0.012));
        }
        STARTS.forEach(([x, y], i) => {
            const m = this.material("start" + i, START_COLOURS[i], 0.6);
            for (const [ox, oy, hx, hy] of [[0, 1.1, 1.2, 0.07], [0, -1.1, 1.2, 0.07], [1.1, 0, 0.07, 1.2], [-1.1, 0, 0.07, 1.2]]) {
                statics.push(this.box(null, hx, hy, 0.005, m, x + ox, y + oy, 0.008));
            }
        });
        for (let k = 0; k < 48; k += 2) {
            const a = k / 48 * Math.PI * 2;
            const d = this.box(null, 0.17, 0.05, 0.005, yellow, Math.cos(a) * 3, Math.sin(a) * 3, 0.008);
            d.rotation.y = -(a + Math.PI / 2);
            statics.push(d);
        }
        if (!mods.flame_pit) statics.push(this.floorText(look.name || "ROBOT LAB", 0, -0.45, 0.012, 7));
        // the drop zone: a shaft, a striped rim, a glowing strip and the lid that drops
        const [px, py] = PIT;
        for (const [ox, oy, hx, hy] of [[0, 1.55, 1.6, 0.05], [0, -1.55, 1.6, 0.05], [1.55, 0, 0.05, 1.6], [-1.55, 0, 0.05, 1.6]]) {
            statics.push(this.box(null, hx, hy, 1.6, dark, px + ox, py + oy, -1.6));
            statics.push(this.box(null, hx === 0.05 ? 0.15 : 1.8, hy === 0.05 ? 0.15 : 1.8, 0.004, yellow, px + ox * 1.06, py + oy * 1.06, 0.005));
        }
        this.pitGlow = [[0, 1.45, 1.5, 0.05], [0, -1.45, 1.5, 0.05], [1.45, 0, 0.05, 1.5], [-1.45, 0, 0.05, 1.5]].map(([ox, oy, hx, hy]) =>
            this.box(null, hx, hy, 0.02, this.material("pitglow", [1, 0.15, 0.1], 0.5, 0, 1.5), px + ox, py + oy, -0.15));
        this.pitLid = this.box(null, 1.47, 1.47, 0.25, this.material("lid", [0.75, 0.75, 0.78], 0.5, 0.6), px, py, -0.25);
        // the floor flipper: a recess and a plate hinged on its back edge
        statics.push(this.box(null, 1.5, 1.0, 0.04, dark, FF[0], FF[1], -0.19));
        this.ffPivot = new BABYLON.TransformNode("ffpivot", this.scene);
        this.ffPivot.position = v3(FF[0], FF[1] - 1.0, -0.08);
        this.ffPivot.rotationQuaternion = BABYLON.Quaternion.Identity();
        const ffPlate = this.box(this.ffPivot, 1.47, 0.97, 0.08, yellow, 0, 1.0, 0);
        this.ffLamp = this.sphere(null, 0.12, this.material("lampoff", [0.3, 0.05, 0.05], 0.5), -5.4, -4.7, 0.08);
        // the saws: a slot in a cover plate, a blade that rises and spins
        this.saws = SAWS.map(([sx, sy], i) => {
            statics.push(this.box(null, 1.25, 0.34, 0.01, steel, sx, sy, 0.01));
            statics.push(this.box(null, 1.12, 0.05, 0.012, dark, sx, sy, 0.016));
            const node = new BABYLON.TransformNode("saw" + i, this.scene);
            node.position = v3(sx, sy, -1.1);
            const spin = new BABYLON.TransformNode("sawspin" + i, this.scene);
            spin.parent = node;
            this.cyl(spin, 0.95, 0.03, "y", this.material("blade", [0.75, 0.76, 0.8], 0.3, 0.9), 0, 0, 0, null, 36);
            for (let t = 0; t < 12; t++) {
                const a = t / 12 * Math.PI * 2;
                const tooth = this.box(spin, 0.07, 0.025, 0.07, steel, Math.cos(a) * 1.0, 0, Math.sin(a) * 1.0);
                tooth.rotation.z = a;
            }
            return {node, spin, angle: 0};
        });
        // the wall spikes (west wall), unless there is no cage
        this.spikeBank = null;
        if (!noCage) {
            this.spikeBank = new BABYLON.TransformNode("spikes", this.scene);
            this.box(this.spikeBank, 0.3, 2.6, 0.42, this.material("bank", [0.35, 0.36, 0.38], 0.5, 0.6));
            for (let y = -2.5; y <= 2.51; y += 0.5) for (const z of [-0.2, 0.2]) {
                const c = BABYLON.MeshBuilder.CreateCylinder("spike", {height: 0.22, diameterBottom: 0.18, diameterTop: 0, tessellation: 8}, this.scene);
                c.material = steel;
                c.rotation.z = -Math.PI / 2;  // (the tip along the game's +x)
                c.position = v3(0.41, y, z);
                c.parent = this.spikeBank;
            }
            statics.push(this.box(null, 0.02, 2.8, 0.45, yellow, -9.99, 0, 0.55));
        }
        // the cage: kick plates in the wall colour, a rail, posts and glass screens; or, with no cage, a gutter
        if (!noCage) {
            const glass = this.glass("screen", [0.6, 0.75, 0.9], 0.1);
            for (const s of [-1, 1]) {
                statics.push(this.box(null, 10.5, 0.25, 0.6, wall, 0, s * 10.25, 0.6));
                statics.push(this.box(null, 0.25, 10, 0.6, wall, s * 10.25, 0, 0.6));
                statics.push(this.box(null, 10.53, 0.28, 0.05, steel, 0, s * 10.25, 1.25));
                statics.push(this.box(null, 0.28, 10.53, 0.05, steel, s * 10.25, 0, 1.25));
                statics.push(this.box(null, 10.5, 0.02, 1.6, glass, 0, s * 10.25, 2.9));
                statics.push(this.box(null, 0.02, 10.5, 1.6, glass, s * 10.25, 0, 2.9));
                for (let k = -5; k <= 5; k++) {
                    statics.push(this.cyl(null, 0.07, 1.65, "z", steel, k * 2, s * 10.25, 2.9, null, 8));
                    statics.push(this.cyl(null, 0.07, 1.65, "z", steel, s * 10.25, k * 2, 2.9, null, 8));
                }
            }
        } else {
            statics.push(this.box(null, 13, 13, 0.1, dark, 0, 0, -3.05));
            for (const s of [-1, 1]) {
                statics.push(this.box(null, 10, 0.05, 1.47, wall, 0, s * 10, -1.47));
                statics.push(this.box(null, 0.05, 10, 1.47, wall, s * 10, 0, -1.47));
            }
        }
        // the apron round the arena and a few rows of stands
        const apron = this.material("apron", [0.28, 0.28, 0.3], 1.0);
        for (const s of [-1, 1]) {
            statics.push(this.box(null, 16, 2.75, 0.25, apron, 0, s * 13.25, -0.3));
            statics.push(this.box(null, 2.75, 10.5, 0.25, apron, s * 13.25, 0, -0.3));
        }
        if (look.crowd !== false && this.tier !== "blocks") {
            const seats = this.material("seats", [0.18, 0.2, 0.26], 0.9);
            for (let row = 0; row < 4; row++) {
                const d = 10 + 3.2 + 1.3 * row + 3, h = 0.55 * (row + 1);
                for (const s of [-1, 1]) {
                    statics.push(this.box(null, d + 0.65, 0.65, h / 2, seats, 0, s * d, h / 2 - 0.4));
                    statics.push(this.box(null, 0.65, d - 0.65, h / 2, seats, s * d, 0, h / 2 - 0.4));
                }
            }
        }
        // the user mods
        if (mods.spike_pit) {
            const [kx, ky, ks] = SPIKE_PIT;
            statics.push(this.box(null, ks / 2, ks / 2, 0.05, dark, kx, ky, -0.55));
            for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) {
                statics.push(this.cyl(null, 0.1, 0.15, "z", steel, kx - 1.0 + i * 0.4, ky - 1.0 + j * 0.4, -0.35, 0, 8));
            }
        }
        this.flames = [];
        if (mods.flame_pit) {
            statics.push(this.box(null, 1.2, 1.2, 0.05, this.material("embers", [1, 0.35, 0.05], 0.5, 0, 1.2), 0, 0, -0.55));
            const fire = this.material("fire", [1, 0.55, 0.1], 0.5, 0, 2);
            for (let i = 0; i < 6; i++) {
                const a = i / 6 * Math.PI * 2;
                const c = BABYLON.MeshBuilder.CreateCylinder("flame", {height: 1, diameterBottom: 0.5, diameterTop: 0, tessellation: 8}, this.scene);
                c.material = fire;
                c.position = v3(Math.cos(a) * 0.6, Math.sin(a) * 0.6, -0.5);
                this.flames.push(c);
            }
        }
        this.boost = mods.boost_pad ? this.box(null, BOOST_PAD[2] / 2, BOOST_PAD[2] / 2, 0.01, this.material("boost", [0.2, 1, 0.3], 0.5, 0, 1), BOOST_PAD[0], BOOST_PAD[1], 0.012) : null;
        this.repair = mods.repair_bay ? this.box(null, REPAIR_BAY[2] / 2, REPAIR_BAY[2] / 2, 0.01, this.material("repair", [0.3, 0.6, 1], 0.5, 0, 0.8), REPAIR_BAY[0], REPAIR_BAY[1], 0.012) : null;
        if (mods.ramps) {
            const deck = this.material("ramp", [0.75, 0.75, 0.78], 0.5, 0.6);
            for (const [cx, cy, d] of RAMPS) {
                const ramp = this.box(null, 1.35, 0.9, 0.05, deck, cx, cy, 0.35);
                ramp.rotation.z = d * Math.atan2(0.7, 2.6);  // (rising towards x = cx + d*1.3)
                statics.push(ramp, this.box(null, 0.05, 0.9, 0.35, steel, cx + d * 1.3, cy, 0.35));
            }
        }
        this.lasers = [];
        for (const m of statics) m.receiveShadows = this.lit;
        this.shadowCast([ffPlate, this.pitLid]);
        if (this.spikeBank) this.spikeBank.position = v3(-10.5, 0, 0.45);
    }

    // ---------- the robots ----------
    setRobots(list) {
        // (ids are given out again on every rebuild of the arena: every model is made again, as the window does)
        for (const r of this.robots.values()) { r.root.dispose(false, true); r.weapon.dispose(false, true); r.label.dispose(); }
        this.robots.clear();
        this.designs = list;
        for (const r of list) this.addRobot(r);
    }

    addRobot(info) {
        const d = info.design || {}, scene = this.scene, s = designSize(d);
        const big = !!(d.house || d.model);
        const weaponType = d.weapon || HOUSE_WEAPONS[d.model] || "wedge";
        const colour = rgb255(d.colour, [200, 120, 40]);
        const style = d.style || {};
        const trim = rgb255(style.trim, [30, 30, 34]), lights = rgb255(style.lights, [255, 60, 30]);
        const paint = this.material("paint", colour, 0.45, 0.4);
        const trimM = this.material("trim", trim, 0.6, 0.5);
        const steel = this.material("steel", STEEL, 0.4, 0.8);
        const glow = this.material("glow", lights, 0.5, 0, 2);
        const hx = 0.6 * s, hy = 0.8 * s, hzz = 0.18 * s, z0 = 0.1, top = z0 + hzz;
        const root = new BABYLON.TransformNode("robot" + info.id, scene);
        root.rotationQuaternion = BABYLON.Quaternion.Identity();
        const parts = [];
        parts.push(this.box(root, hx, hy, hzz, paint, 0, 0, z0));
        parts.push(this.box(root, 0.78 * hx, 0.72 * hy, 0.045, trimM, 0, -0.08 * hy, top + 0.04));
        for (const sd of [-1, 1]) parts.push(this.box(root, 0.03, 0.9 * hy, 0.7 * hzz, steel, sd * (hx + 0.02), 0, z0 - 0.02));
        parts.push(this.box(root, 0.5 * hx, 0.012, 0.025, glow, 0, hy + 0.005, z0 + 0.45 * hzz));
        parts.push(this.box(root, 0.72 * hx, 0.012, 0.55 * hzz, this.material("back", [0.3, 0.3, 0.33], 0.6), 0, -hy - 0.005, z0));
        parts.push(this.cyl(root, 0.008, 0.18, "z", steel, -0.6 * hx, -0.7 * hy, top + 0.24, null, 6));
        if (big) parts.push(this.sphere(root, 0.08, this.material("beacon", [1, 0.65, 0], 0.5, 0, 2), 0.55 * hx, -0.55 * hy, top + 0.26));
        const wr = big ? 0.32 : 0.2, ww = big ? 0.12 : 0.075;
        const wheels = [[0.72, 0.55], [-0.72, 0.55], [0.72, -0.55], [-0.72, -0.55]].map(([x, y]) => {
            const spin = new BABYLON.TransformNode("wheel", scene);
            spin.parent = root;
            spin.position = v3(x * s, y * s, 0.08);
            const tyre = this.cyl(spin, wr, ww, "x", this.material("tyre", [0.07, 0.07, 0.08], 0.9), 0, 0, 0, null, 16);
            const hub = this.cyl(spin, wr * 0.55, ww + 0.005, "x", steel, 0, 0, 0, null, 10);
            parts.push(tyre, hub);
            return spin;
        });
        // the weapon: a node placed in the world from the snapshot (its origin is the hinge), the shapes around it
        const weapon = new BABYLON.TransformNode("weapon" + info.id, scene);
        weapon.rotationQuaternion = BABYLON.Quaternion.Identity();
        const spin = new BABYLON.TransformNode("wspin", scene);
        spin.parent = weapon;
        const wparts = [];
        let blur = null, jet = null;
        if (weaponType === "wedge") {
            wparts.push(this.box(weapon, hx + 0.02, 0.6, 0.02, trimM, 0, 0.6, -0.01));
            wparts.push(this.box(weapon, hx + 0.02, 0.06, 0.021, this.material("yellow", YELLOW, 0.6), 0, 1.14, -0.009));
            wparts.push(this.cyl(weapon, 0.05, hx, "x", steel, 0, 0, 0, null, 10));
        } else if (weaponType === "spinner") {
            wparts.push(this.box(spin, 0.8 * s, 0.08, 0.05, this.material("bar", [0.7, 0.72, 0.76], 0.3, 0.9)));
            for (const sd of [-1, 1]) wparts.push(this.box(spin, 0.09, 0.1, 0.07, steel, sd * (0.8 * s - 0.07), 0, 0));
            wparts.push(this.cyl(spin, 0.11, 0.06, "z", trimM));
            blur = this.cyl(weapon, 0.8 * s, 0.01, "z", this.glass("blur", [0.8, 0.82, 0.86], 0.2), 0, 0, 0, null, 32);
        } else if (weaponType === "drum") {
            wparts.push(this.cyl(spin, 0.2 * s, 0.8 * hx, "x", this.material("drum", [0.6, 0.62, 0.66], 0.35, 0.9), 0, 0, 0, null, 16));
            for (let t = 0; t < 6; t++) {
                const a = t / 6 * Math.PI * 2;
                wparts.push(this.box(spin, 0.6 * hx, 0.04, 0.04, steel, 0, Math.cos(a) * 0.22 * s, Math.sin(a) * 0.22 * s));
            }
        } else if (weaponType === "vdisc") {
            const r = 0.42 * s;
            wparts.push(this.cyl(spin, r, 0.035 * s, "x", this.material("bar", [0.7, 0.72, 0.76], 0.3, 0.9), 0, 0, 0, null, 24));
            for (let t = 0; t < 8; t++) {
                const a = t / 8 * Math.PI * 2;
                wparts.push(this.box(spin, 0.03 * s, 0.06, 0.06, steel, 0, Math.cos(a) * 1.07 * r, Math.sin(a) * 1.07 * r));
            }
            wparts.push(this.cyl(spin, 0.45 * r, 0.05 * s, "x", trimM, 0, 0, 0, null, 12));
            blur = this.cyl(weapon, 1.12 * r, 0.02, "x", this.glass("blur", [0.8, 0.82, 0.86], 0.2), 0, 0, 0, null, 32);
        } else if (weaponType === "flame") {
            wparts.push(this.cyl(weapon, 0.07 * s, 0.22 * s, "y", steel, 0, 0.22 * s, 0, null, 10));
            wparts.push(this.cyl(weapon, 0.1 * s, 0.04 * s, "y", trimM, 0, 0.44 * s, 0, null, 10));
            for (const sd of [-1, 1]) parts.push(this.cyl(root, 0.08 * s, 0.25 * s, "y", this.material("tank", [0.75, 0.1, 0.08], 0.5), sd * 0.45 * hx, -0.2 * hy, top + 0.1));
            jet = BABYLON.MeshBuilder.CreateCylinder("jet", {height: 2.6, diameterBottom: 0.06, diameterTop: 1.4, tessellation: 12}, scene);
            jet.material = this.glass("jet", [1, 0.55, 0.1], 0.55);
            jet.material.emissiveColor = new BABYLON.Color3(1, 0.5, 0.1);
            jet.rotation.x = Math.PI / 2;
            jet.position = v3(0, 0.44 * s + 1.35, 0);
            jet.parent = weapon;
            jet.isVisible = false;
        } else if (weaponType === "laser") {
            wparts.push(this.box(weapon, 0.06 * s, 0.18 * s, 0.05 * s, steel, 0, 0.18 * s, 0));
            wparts.push(this.sphere(weapon, 0.04 * s, this.material("lens", [1, 0.1, 0.1], 0.3, 0, 2), 0, 0.36 * s + 0.05, 0));
        } else if (weaponType === "chainsaw") {
            wparts.push(this.box(weapon, 0.06 * s, 0.3 * s, 0.05 * s, paint, 0, 0.3 * s, 0));
            wparts.push(this.box(weapon, 0.025, 0.42 * s, 0.07 * s, this.material("bar", [0.75, 0.76, 0.8], 0.3, 0.9), 0, 0.6 * s + 0.42 * s - 0.05, -0.04));
        } else {  // hammer
            const m = Math.min(s, 1.3), L = Math.min(0.85 * s, 1.3);
            wparts.push(this.box(weapon, 0.05 * m, L, 0.05 * m, this.material("arm", [0.4, 0.4, 0.42], 0.5, 0.7), 0, L, 0));
            wparts.push(this.box(weapon, 0.22 * s, 0.14 * s, 0.14 * s, this.material("head", [0.2, 0.2, 0.22], 0.5, 0.7), 0, 2 * L, 0));
            wparts.push(this.cyl(weapon, 0.08, 0.15, "x", steel, 0, 0, 0, null, 10));
        }
        this.shadowCast([...parts, ...wparts]);
        const owner = info.owner || "";
        const house = owner === "Resident Robot";
        const label = this.makeLabel(house ? `${d.name || ""}\nResident Robot` : owner || d.name || "", house ? "#ffbf4d" : "#ffffff");
        const vis = {root, hull: parts[0], weapon, spin, blur, jet, wheels, wr, label, design: d, owner, weaponType, s, angle: 0, roll: 0, hp: null, flash: 0, look: ""};
        this.robots.set(info.id, vis);
        return vis;
    }

    // ---------- each frame ----------
    // st: the watched arena, blended ({robots: [...], hz}); dt seconds
    frame(st, dt, t) {
        const seen = new Set();
        for (const r of (st && st.robots) || []) {
            const v = this.robots.get(r.id);
            if (!v) continue;
            seen.add(r.id);
            v.root.setEnabled(true);
            v.weapon.setEnabled(true);
            v.label.setEnabled(true);
            v.root.position = v3(r.pos[0], r.pos[1], r.pos[2]);
            v.root.rotationQuaternion = gameQuat(r.quat);
            v.weapon.position = v3(r.wpos[0], r.wpos[1], r.wpos[2]);
            if (SPINNERS.has(v.weaponType)) {
                v.weapon.rotationQuaternion = gameQuat(r.quat);  // (the spin itself is drawn here, from its speed)
                v.angle += (r.rpm || 0) / 60 * 2 * Math.PI * dt * 0.35;
                if (v.weaponType === "spinner") v.spin.rotation.y = v.angle; else v.spin.rotation.x = v.angle;
                if (v.blur) { v.blur.visibility = Math.min(1, (r.rpm || 0) / 400); v.blur.isVisible = (r.rpm || 0) > 30; }
            } else {
                v.weapon.rotationQuaternion = gameQuat(r.wquat);
            }
            if (v.jet) v.jet.isVisible = !!r.fl;
            v.roll += (r.speed || 0) * dt / v.wr;
            for (const w of v.wheels) w.rotation.x = v.roll;
            v.label.position = v3(r.pos[0], r.pos[1], r.pos[2] + 1.3 * Math.max(1, v.s));
            if (v.hp !== null && r.hp < v.hp - 0.5) v.flash = 0.15;
            v.hp = r.hp;
            v.flash = Math.max(0, v.flash - dt);
            const look = r.ko ? "ko" : v.flash > 0 ? "flash" : "";  // (knocked out: dark; just hit: a flash)
            if (look !== v.look) {
                v.look = look;
                const scale = look === "ko" ? 0.35 : look === "flash" ? 2.2 : 1;
                v.hull.material = this.material("paint", rgb255(v.design.colour, [200, 120, 40]).map(c => Math.min(1, c * scale)), 0.45, 0.4);
            }
        }
        for (const [id, v] of this.robots) {
            if (!seen.has(id)) { v.root.setEnabled(false); v.weapon.setEnabled(false); v.label.setEnabled(false); }
        }
        const hz = st && st.hz;
        if (hz) {
            if (this.pitLid && hz.pit !== undefined) this.pitLid.position.y = hz.pit - 0.25;
            const glow = hz.pit_open ? this.material("pitglow", [1, 0.15, 0.1], 0.5, 0, 1.5) : this.material("pitcalm", [0.2, 0.9, 0.3], 0.5, 0, 0.8);
            for (const g of this.pitGlow || []) g.material = glow;
            if (this.ffPivot && hz.ff) this.ffPivot.rotationQuaternion = gameQuat(hz.ff);
            if (this.ffLamp) this.ffLamp.material = (hz.on && hz.on.floor_flipper && (hz.t % 4) > 3.2 && Math.sin(t * 20) > 0)
                ? this.material("lampon", [1, 0.1, 0.1], 0.5, 0, 2) : this.material("lampoff", [0.3, 0.05, 0.05], 0.5);
            (hz.saws || []).forEach((h, i) => {
                const saw = this.saws[i];
                if (!saw) return;
                saw.node.position.y = -1.1 + 1.35 * h;
                saw.angle -= (400 + 1400 * Math.min(1, 2 * h)) * Math.PI / 180 * dt;
                saw.spin.rotation.z = saw.angle;
            });
            if (this.spikeBank) this.spikeBank.position.x = -10.5 + 0.6 * (hz.spikes || 0);
            for (const [i, f] of this.flames.entries()) {
                const hgt = Math.max(0.2, (0.5 + (hz.flames || 0)) * (0.8 + 0.3 * Math.sin(t * 9 + i * 1.7)));
                f.scaling.y = hgt;
                f.position.y = -0.5 + hgt / 2;
            }
            if (this.boost) this.boost.material = hz.boost ? this.material("boost", [0.2, 1, 0.3], 0.5, 0, 0.6 + 0.4 * Math.sin(t * 6)) : this.material("boostoff", [0.6, 0.1, 0.1], 0.5, 0, 0.3);
            for (const l of this.lasers) l.dispose();
            this.lasers = (hz.lasers || []).map(([sx, sy, sz, ex, ey, ez]) => {
                const a = v3(sx, sy, sz), b = v3(ex, ey, ez);
                const beam = BABYLON.MeshBuilder.CreateTube("laser", {path: [a, b], radius: 0.04, tessellation: 6}, this.scene);
                beam.material = this.material("beam", [1, 0.15, 0.1], 0.5, 0, 2);
                return beam;
            });
        }
        for (const sp of this.sparks) {
            sp.life -= dt;
            sp.mesh.scaling.setAll(1 + (0.3 - sp.life) * 6);
            sp.mesh.visibility = Math.max(0, sp.life / 0.3);
            if (sp.life <= 0) sp.mesh.dispose();
        }
        this.sparks = this.sparks.filter(sp => sp.life > 0);
        this.updateCamera(st, dt, t);
        this.followSun();
    }

    spark(pos, dmg, kind) {
        if (this.sparks.length > 30) return;
        const hot = ["flame", "saw", "spinner", "drum"].includes(kind);
        const m = this.sphere(null, Math.min(0.35, 0.08 + dmg * 0.01), this.material(hot ? "sparkhot" : "spark", hot ? [1, 0.6, 0.15] : [1, 0.95, 0.7], 0.5, 0, 2), pos[0], pos[1], pos[2], 1, 1, 1, 6);
        this.sparks.push({mesh: m, life: 0.3});
    }

    updateCamera(st, dt, t) {
        const cam = this.camera;
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
        if (mode === "overview") { cam.target = v3(0, 0, 0); cam.radius = 27; cam.alpha = -Math.PI / 2; cam.beta = 0.78; }
        if (mode === "follow") { cam.radius = 8; cam.beta = 0.95; }
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
    }

    welcome(m) {
        const p = this.app.params;
        if (p.get("cam")) this.scene.setMode(p.get("cam") === "chase" ? "follow" : "overview", p.get("follow") !== null ? Number(p.get("follow")) : null);
    }

    message(m) {
        if (m.type === "roster") {
            this.scene.setSetup({hazards: m.hazards || {}, user_mods: m.user_mods || {}, look: m.look || {}});
            this.scene.setRobots(m.robots || []);
            this.renderBoard();
            return true;
        }
        if (m.type === "state") {
            m.sm = m.sm >>> 0;
            this.app.pushSnap(m, performance.now());
            this.last = m;
            const arena = this.arenaOf(m);
            if (arena && arena.fx) for (const [p, dmg, kind] of arena.fx.impacts || []) this.scene.spark(p, dmg, kind);
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
        const robots = A.robots.map(r => {
            const n = byId.get(r.id);
            if (!n) return r;
            return {...n, pos: r.pos.map((v, i) => lerp(v, n.pos[i], f)), quat: slerpQ(r.quat, n.quat, f),
                    wpos: r.wpos.map((v, i) => lerp(v, n.wpos[i], f)), wquat: slerpQ(r.wquat, n.wquat, f),
                    speed: lerp(r.speed || 0, n.speed || 0, f)};
        });
        let hz = A.hz;
        if (B && B.hz && A.hz) {
            hz = {...B.hz, pit: lerp(A.hz.pit ?? 0, B.hz.pit ?? 0, f), spikes: lerp(A.hz.spikes || 0, B.hz.spikes || 0, f),
                  flames: lerp(A.hz.flames || 0, B.hz.flames || 0, f),
                  saws: (A.hz.saws || []).map((v, i) => lerp(v, (B.hz.saws || [])[i] ?? v, f)),
                  ff: A.hz.ff && B.hz.ff ? slerpQ(A.hz.ff, B.hz.ff, f) : B.hz.ff};
        }
        const top = pair.b || pair.a;
        this.scene.frame({robots, hz, intro: top.intro}, dt, now / 1000);
    }

    renderBoard() {
        const S = this.app.state, m = this.last, esc = this.app.esc;
        if (!m) return;
        const arena = this.arenaOf(m);
        const roster = S.roster || {};
        const byId = new Map((roster.robots || []).map(r => [r.id, r]));
        const n = roster.arenas || 1;
        const rows = ((arena && arena.robots) || []).map(r => {
            const info = byId.get(r.id) || {design: {}};
            const c = (info.design.colour || [128, 128, 128]).map(v => Math.round(v));
            const pc = Math.max(0, Math.min(100, Math.round(100 * r.hp / (r.max || 1))));
            return `<div data-id="${r.id}"><span class="sw" style="background:rgb(${c.join(",")})"></span><span>${esc(info.design.name || "?")}<small> ${esc(info.owner || "")}</small></span>` +
                   `<span class="hpbar"><i style="width:${pc}%;background:${pc > 50 ? "#4ade80" : pc > 25 ? "#facc15" : "#f87171"}"></i></span>` +
                   `<span class="lap">${r.ko ? "KO" : r.hits ? `${r.hits} hits` : ""}</span></div>`;
        });
        $("places").innerHTML = (n > 1 ? `<div><small>ARENA ${this.watched() + 1} of ${n}</small></div>` : "") + (rows.join("") || "<div><small>No robots yet</small></div>");
        $("places").querySelectorAll("div[data-id]").forEach(el => el.onclick = () => {
            const id = Number(el.dataset.id);
            this.scene.setMode(this.scene.mode === "follow" && this.scene.follow === id ? "overview" : "follow", id);
            this.app.updatePills();
        });
        let big = "";
        if (m.intro !== null && m.intro !== undefined) {
            const t = m.intro;
            big = t < 2.5 ? ((roster.look || {}).name || "ROBOT LAB") : t < 5 ? "GET READY" : String(Math.max(1, 3 - Math.floor(t - 5)));
            this.activateAt = performance.now();
        } else if (this.activateAt && performance.now() - this.activateAt < 1200) {
            big = "ACTIVATE!";
        } else if (arena && arena.winner) {
            big = arena.winner;
        }
        $("countdown").textContent = big;
        const tl = arena && arena.time_left !== null && arena.time_left !== undefined ? arena.time_left : m.time_left;
        const clock = tl !== null && tl !== undefined ? `${Math.floor(tl / 60)}:${String(Math.floor(tl % 60)).padStart(2, "0")}` : "";
        $("phase").textContent = (m.paused ? "PAUSED · " : "") + (m.practice ? "PRACTICE (no damage)" : `BATTLE ${clock}`) + (m.rd ? " · real damage" : "");
    }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${L.mode === "battle" ? "battle" : "practice"} · ${L.arenas || 1} arena${(L.arenas || 1) > 1 ? "s" : ""}` : "";
    }

    cameraPill() {
        const sc = this.scene;
        return sc.mode === "follow" ? "Camera: following a robot (drag to orbit)" : "Camera: the whole arena (drag to orbit, wheel to zoom)";
    }

    tabs() { return [["controls", "Controls"], ["camera", "Camera"]]; }

    learnerHead() { return ["Robot", "Arena"]; }
    learnerCells(p) {
        const S = this.app.state, roster = S.roster || {};
        const id = roster.mine ? roster.mine[p.name] : null;
        const r = (roster.robots || []).find(x => x.id === id);
        return [this.app.esc((p.design && p.design.name) || ""), r ? r.arena + 1 : ""];
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, send = app.send, esc = app.esc;
        const lessonSend = patch => send({type: "lesson", lesson: patch});
        if (tab === "controls") {
            if (!L) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return true; }
            const T = S.tournament;
            const people = (S.classList || []).filter(p => p.role === "learner").map(p => p.name).concat(L.teacher_robot ? ["Teacher"] : []);
            const arenas = L.arenas || 1;
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The match</h2>
              <div class="row"><button data-mode="practice" class="${L.mode !== "battle" ? "on" : ""}">Practice</button>
                <button data-mode="battle" class="${L.mode === "battle" ? "on" : ""}">Battle</button>
                <button id="rb-restart" class="go">RESTART</button>
                <button id="rb-pause" class="${this.last && this.last.paused ? "on" : ""}">${this.last && this.last.paused ? "RESUME" : "PAUSE"}</button></div>
              <div class="note">Practice: no damage, knocked-out robots come back. Battle: RESTART counts down 8 seconds, then ACTIVATE!</div>
              <div class="row"><label>Battle time</label><select id="rb-time">${[30, 60, 90, 120, 150, 180, 210, 240, 270, 300].map(t => `<option value="${t}" ${t === L.time_limit ? "selected" : ""}>${t} s</option>`).join("")}</select></div>
              <div class="row"><label>Computer robots</label><select id="rb-cpu">${[0, 1, 2, 3].map(k => `<option ${k === L.cpu_robots ? "selected" : ""}>${k}</option>`).join("")}</select>
                <select id="rb-level">${LEVELS.map(([k, n]) => `<option value="${k}" ${k === L.cpu_level ? "selected" : ""}>${n}</option>`).join("")}</select></div>
              ${L.cpu_level === "empty" ? `<div class="row"><label class="filebtn">Upload the demo brain (.py)<input id="rb-demo" type="file" accept=".py,text/plain" hidden></label></div>` : ""}
              <div class="row"><label>My robot</label><button id="rb-mine" class="${L.teacher_robot ? "on" : ""}">${L.teacher_robot ? "In the arena" : "Not in"}</button></div>
              <div class="row"><label>Designs</label><button id="rb-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              <div class="row"><label>Damage</label><button id="rb-real" class="${L.real_damage ? "on" : ""}">${L.real_damage ? "Real damage: parts come off" : "Simple health"}</button></div>
              <div class="row"><label>Drop zone</label><button id="rb-pit-open">Open it now</button><button id="rb-pit-close">Close it now</button></div>
              ${(L.user_mods || {}).flame_pit ? `<div class="row"><label>Flame pit</label><select id="rb-flame">${[10, 20, 30, 40, 50, 60, 70, 80, 90, 100].map(c => `<option value="${c}" ${c === L.flame_pit_cm ? "selected" : ""}>${c} cm</option>`).join("")}</select></div>` : ""}
              <h2>Arenas</h2>
              <div class="row"><label>How many</label><select id="rb-arenas">${[1, 2, 3, 4, 5, 6].map(k => `<option ${k === arenas ? "selected" : ""}>${k}</option>`).join("")}</select>
                <button id="rb-turns">Take turns again</button></div>
              ${arenas > 1 ? people.map((n, i) => `<div class="row"><label>${esc(n)}</label><select data-place="${i}"><option value="">any</option>${Array.from({length: arenas}, (_, k) =>
                  `<option value="${k}" ${(L.places || {})[n] === k ? "selected" : ""}>arena ${k + 1}</option>`).join("")}</select></div>`).join("") : ""}
              <h2>Tournament</h2>
              ${T ? `<p><b>${esc(T.title || "")}</b>${T.champion ? ` · champion ${esc(T.champion)}` : ""}</p>
                ${(T.table || []).length ? `<table><tr><th>Robot</th><th>wins</th><th>streak</th></tr>${T.table.map(([n, w, s]) => `<tr><td>${esc(n)}</td><td class="num">${w}</td><td class="num">${s}</td></tr>`).join("")}</table>` : ""}
                ${(T.rounds || []).map((rd, i) => `<div class="note">Round ${i + 1}: ${rd.map(([a, b, w]) => `${esc(a)} v ${esc(b)}${w ? ` (${esc(w)})` : ""}`).join(", ")}</div>`).join("")}
                <div class="row"><button id="rb-tstop" class="stop">STOP THE TOURNAMENT</button></div>`
                : `<div class="row"><button id="rb-stays" class="go">Winner stays on</button><button id="rb-knock" class="go">Knockout</button></div>
                   <div class="note">Winner stays on uses ${arenas} arena${arenas > 1 ? "s" : ""}; a knockout pairs everyone in order, one pair per arena.</div>`}
              ${app.restartRow()}`;
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
            $("rb-turns").onclick = () => lessonSend({places: Object.fromEntries(people.map(n => [n, null]))});
            body.querySelectorAll("select[data-place]").forEach(sel => sel.onchange = () =>
                lessonSend({places: {[people[Number(sel.dataset.place)]]: sel.value === "" ? null : Number(sel.value)}}));
            if ($("rb-stays")) $("rb-stays").onclick = () => send({type: "tournament", start: true, kind: "stays", live: arenas});
            if ($("rb-knock")) $("rb-knock").onclick = () => {
                const pairs = [];
                for (let i = 0; i + 1 < people.length && pairs.length < arenas; i += 2) pairs.push([people[i], people[i + 1]]);
                send({type: "tournament", start: true, kind: "knockout", lineups: pairs});
            };
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
        this.scene.dispose();
        $("places").innerHTML = "";
        $("countdown").textContent = $("phase").textContent = "";
    }
}
