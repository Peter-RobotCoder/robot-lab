// City Lab's person and car steps (city/city_sim.py, ported line for line), and the city's questions they ask
// (city/city_map.py's City: what is under a point, what a thing bumps into, the kerb, the ramps, the yards): what the
// browser needs to predict its own person on foot, or the car it drives, as the window does (CHANGE 201).
//
// Kart Lab's rule, kept (kart_sim.js): the server, the window and the page step what they control with the same few
// lines of arithmetic and round the result to the wire's precision each tick (centimetres, a tenth of a degree), so
// all three start every tick from the same numbers. step_person and step_car are pure functions of the record (one
// record kind for people, cars and robots: SCHEMA_FIELDS), the input and the city; the city is built from the JSON
// the server sends in its welcome (City below, city_map.City's constructor), so there is one generator and nothing
// to port but its questions. Python's arithmetic is kept where JavaScript's differs (pymath.js: floored %, round half
// to even, math.hypot, radians and degrees, and kart_math's sin, cos and atan2), and Python's max and min are kept
// too (pyMax, pyMin: the first of equals, so a negative zero stays one), so the result is Python's to the last bit;
// city_sim_test.py checks it.
//
// Everything between things (bumps, hits, getting in and out of cars, the jobs) is the server's (city_sim.World); the
// page learns of it from the snapshots. The robots' step isn't here: nobody on the page drives a robot.

import {pyMod, copysign, hypot, radians, degrees, sin, cos, exp, atan2} from "./pymath.js";
import {wireInts as kartWireInts, quantise as kartQuantise} from "./kart_sim.js";

export const STEP = 1 / 60;
export const SIM_VERSION = 1;  // (city_sim.SIM_VERSION: city_sim_test.py's fingerprint is recorded for it)
export const POINTS_TOTAL = 100, STAT_MIN = 10, STAT_MAX = 60;
export const STATS = ["speed", "acceleration", "grip"];
export const BODIES = ["coupe", "supercar", "rally", "muscle"];
export const LOOKS = ["woman", "man", "robin", "human", "robot"];

// ids: what a thing is (people 0 to 31, cars 32 to 127, robots 128 to 191)
export function kindOf(tid) {
    return tid < 32 ? "person" : tid < 128 ? "car" : "robot";
}

// the input's buttons (engine.wire's byte): a car's as Kart Lab's; on foot DRIFT is run and HANDBRAKE is block
export const DRIFT = 1, ACTION = 2, RESPAWN = 4, LAUNCH = 8, HANDBRAKE = 16;
export const PUNCH = 32, KICK = 64, JUMP = 128;
export const RUN = DRIFT, BLOCK = HANDBRAKE;

// the record's flags byte, by kind: a person, a car (Kart Lab's where they are the same), a robot
export const FLAG_RUN = 1, FLAG_AIR = 2, FLAG_BLOCK = 4, FLAG_DOWN = 8, FLAG_PARCEL = 16, FLAG_HURT = 32;
export const FLAG_DRIFT_L = 1, FLAG_DRIFT_R = 2, FLAG_WRECKED = 4, FLAG_CAR_AIR = 8, FLAG_BOOSTING = 16, FLAG_BRAKING = 32,
             FLAG_WHEELSPIN = 64, FLAG_HANDBRAKE = 128;
export const FLAG_CROSS = 1, FLAG_ROGUE = 2, FLAG_OFF = 4, FLAG_ZAP = 8;

// the moves (a person's "move" field) and how long each lasts (ticks)
export const MOVE_NONE = 0, MOVE_PUNCH = 1, MOVE_KICK = 2, MOVE_BLOCK = 3, MOVE_DOWN = 4, MOVE_GETUP = 5, MOVE_HURT = 6;
export const MOVE_TICKS = {[MOVE_PUNCH]: 18, [MOVE_KICK]: 26, [MOVE_DOWN]: 150, [MOVE_GETUP]: 40, [MOVE_HURT]: 14};
export const HEALTH = 100, DOWN_HEALTH = 50, POWER = 100;
export const REGEN_TICKS = 120;

// a person
export const WALK = 3.2, RUN_SPEED = 6.5, TURN_RATE = 540.0;
export const PERSON_R = 0.35;
export const JUMP_V = 5.6, GRAVITY = 20.0;

// a car (Kart Lab's numbers, kart_sim.py)
export const CAR_R = 1.0;
export const ROLL = 0.6;
export const HB_GRIP = 0.25, HB_BRAKE = 1.2, HB_TURN = 1.5, HB_SCRUB = 0.2;
export const LAUNCH_SPEED = 6.0, LAUNCH_ACCEL = 0.35, LAUNCH_GRIP = 0.3, LAUNCH_SPIN = 150.0;
export const PAVE_DRAG = 0.25, PAVE_GRIP = 0.75;
export const GRASS_DRAG = 1.0, GRASS_ACCEL = 0.5, GRASS_GRIP = 0.6;
export const KERB_BUMP = 0.9;
export const DAMAGE_MAX = 10000;
export const HIT_SPEED = 2.0, HIT_WALL = 900;
export const BUMP_GRACE = 60;
export const WRECK_SPEED = 4.0;
export const REPAIR_TICK = 1, REPAIR_GARAGE = 200;
export const GARAGE_STOP = 2.0;
export const ENTER_REACH = 2.5, EXIT_SPEED = 3.0;
export const ROBOT_R = 0.95;

// the wire record for everything (city_sim.SCHEMA_FIELDS): name, struct code, scale
export const SCHEMA_FIELDS = [["x", "i", 100], ["y", "i", 100], ["z", "h", 100], ["vz", "h", 100], ["yaw", "h", 10],
                              ["v", "h", 100], ["u", "h", 100], ["hp", "B", 1], ["flags", "B", 1], ["link", "B", 1],
                              ["move", "B", 1], ["mp", "B", 1], ["steer", "b", 100], ["dmg", "H", 1], ["job", "B", 1],
                              ["jp", "B", 1], ["cash", "H", 1], ["aux", "H", 1], ["lk", "B", 1], ["bg", "B", 1]];

// ---------- the city (city_map.py) ----------
export const ROAD = 12.0, PAVE = 2.5, LANE = 1.75, PARK_LANE = 4.75, KERB_H = 0.12, VERGE = 6.0, INSET = 0.5;
export const RAMP_LEN = 7.0, RAMP_H = 1.4;

// Python's max(a, b) and min(a, b): the first of two equals (Math's give +0 over -0)
export const pyMax = (a, b) => (b > a ? b : a);
export const pyMin = (a, b) => (b < a ? b : a);

export class City {
    // data: the welcome's city (city_map.City.to_data), built as city_map.City builds it
    constructor(data) {
        this.data = data;
        this.key = data.key;
        this.name = data.name;
        this.cols = Math.trunc(data.cols);
        this.rows = Math.trunc(data.rows);
        this.block = Number(data.block);
        this.water = data.water || null;
        this.pitch = this.block + ROAD;
        this.width = this.cols * this.pitch + ROAD;
        this.height = this.rows * this.pitch + ROAD;
        this.xmin = -this.width / 2;
        this.ymin = -this.height / 2;
        this.xmax = this.width / 2;
        this.ymax = this.height / 2;
        this.edge = [this.xmin - VERGE, this.ymin - VERGE, this.xmax + VERGE, this.ymax + VERGE];  // (the barrier)
        this.blocks = data.blocks;          // [{i, j, kind, x0, y0, x1, y1}] (the kerb rectangle)
        this.buildings = data.buildings;    // [{x0, y0, x1, y1, h, kind, c, roof, b}]
        this.trees = data.trees;            // [[x, y, r, h]]
        this.lamps = data.lamps;            // [[x, y]]
        this.ramps = data.ramps;            // [{x, y, yaw}]: the lip is RAMP_LEN / 2 ahead of (x, y)
        this.places = data.places;          // kind -> [x, y, yaw]: the door of the depot, garage, rank, arcade
        this.zones = data.zones;            // kind -> [x0, y0, x1, y1]: the yard that counts as being there
        this.addresses = data.addresses;    // [[x, y, yaw, name]]
        this.spawns = data.spawns;          // [[x, y, yaw]]
        this.parking = data.parking;        // [[x, y, yaw]]
        this.chips = data.chips;            // [[x, y]]
        this.streetNames = data.streets;
        this.roadNames = data.roads;
        // the buildings, lamps and trees by block, for the collision test (in city_map's order: the buildings, then
        // each block's trees, then its lamps)
        this.byBlock = new Map();
        const at = bi => { if (!this.byBlock.has(bi)) this.byBlock.set(bi, [[], []]); return this.byBlock.get(bi); };
        this.buildings.forEach((b, n) => at(b.b)[0].push(n));
        this.trees.forEach(([x, y], n) => { const bi = this.blockIndex(x, y); if (bi !== null) at(bi)[1].push(["t", n]); });
        this.lamps.forEach(([x, y], n) => { const bi = this.blockIndex(x, y); if (bi !== null) at(bi)[1].push(["l", n]); });
    }

    // the middle of vertical road k (0 to cols), of horizontal road m (0 to rows)
    roadX(k) { return this.xmin + ROAD / 2 + k * this.pitch; }
    roadY(m) { return this.ymin + ROAD / 2 + m * this.pitch; }

    // the index in blocks of the block (x, y) is on (its kerb rectangle), or null (on a road, or outside)
    blockIndex(x, y) {
        const fx = (x - this.xmin - ROAD) / this.pitch;
        const fy = (y - this.ymin - ROAD) / this.pitch;
        const i = Math.floor(fx), j = Math.floor(fy);
        if (!(0 <= i && i < this.cols && 0 <= j && j < this.rows)) return null;
        if ((fx - i) * this.pitch > this.block || (fy - j) * this.pitch > this.block) return null;
        return j * this.cols + i;
    }

    // what is under (x, y): road, pave, grass, lot, court, quay or out (city_map.City.surface)
    surface(x, y) {
        const e = this.edge;
        if (x < e[0] || x > e[2] || y < e[1] || y > e[3]) return "out";
        if (x < this.xmin || x > this.xmax || y < this.ymin || y > this.ymax) {
            if (this.water && this.waterSide(x, y)) return "quay";
            return "grass";
        }
        const bi = this.blockIndex(x, y);
        if (bi === null) return "road";
        const b = this.blocks[bi];
        if (x < b.x0 + PAVE || x > b.x1 - PAVE || y < b.y0 + PAVE || y > b.y1 - PAVE) return "pave";
        const kind = b.kind;
        if (kind === "park") return "grass";
        if (["carpark", "depot", "garage", "rank", "arcade"].includes(kind)) return "lot";
        return "court";
    }

    waterSide(x, y) {
        return (this.water === "south" && y < this.ymin) || (this.water === "north" && y > this.ymax)
            || (this.water === "east" && x > this.xmax) || (this.water === "west" && x < this.xmin);
    }

    // (x, y) pushed out of anything a thing of radius r can't be in: [x, y, hit], hit null, "building", "post" or
    // "edge" (city_map.City.collide)
    collide(x, y, r) {
        let hit = null;
        const e = this.edge;
        if (x < e[0] + r) { x = e[0] + r; hit = "edge"; }
        else if (x > e[2] - r) { x = e[2] - r; hit = "edge"; }
        if (y < e[1] + r) { y = e[1] + r; hit = "edge"; }
        else if (y > e[3] - r) { y = e[3] - r; hit = "edge"; }
        const bi = this.blockIndex(x, y);
        if (bi === null) return [x, y, hit];
        const [buildings, posts] = this.byBlock.get(bi) || [[], []];
        for (const n of buildings) {
            const b = this.buildings[n];
            if (b.x0 - r < x && x < b.x1 + r && b.y0 - r < y && y < b.y1 + r) {
                // out along the shallowest side
                const left = x - (b.x0 - r), right = (b.x1 + r) - x;
                const down = y - (b.y0 - r), up = (b.y1 + r) - y;
                const least = pyMin(pyMin(pyMin(left, right), down), up);
                if (least === left) x = b.x0 - r;
                else if (least === right) x = b.x1 + r;
                else if (least === down) y = b.y0 - r;
                else y = b.y1 + r;
                hit = "building";
            }
        }
        for (const [kind, n] of posts) {
            const [px, py, pr] = kind === "t" ? [this.trees[n][0], this.trees[n][1], this.trees[n][2]] : [this.lamps[n][0], this.lamps[n][1], 0.2];
            let dx = x - px, dy = y - py;
            const reach = pr + r;
            if (dx * dx + dy * dy >= reach * reach) continue;  // (the cheap test first)
            let d = hypot(dx, dy);
            if (d < reach) {
                if (d < 1e-6) { dx = 1.0; dy = 0.0; d = 1.0; }
                x = px + dx / d * reach;
                y = py + dy / d * reach;
                hit = "post";
            }
        }
        return [x, y, hit];
    }

    // did a move from (x0, y0) to (x1, y1) cross a kerb (the road's edge)? The bump a car feels
    kerbBetween(x0, y0, x1, y1) {
        return (this.blockIndex(x0, y0) === null) !== (this.blockIndex(x1, y1) === null);
    }

    // the height of the ramp under (x, y), or 0: a wedge RAMP_LEN long rising to RAMP_H at its lip, 4 m wide
    rampHeight(x, y) {
        for (const rp of this.ramps) {
            const yr = radians(rp.yaw);
            const c = cos(yr), s = sin(yr);
            const dx = x - rp.x, dy = y - rp.y;
            const along = dx * c + dy * s;
            const across = -dx * s + dy * c;
            if (-RAMP_LEN / 2 <= along && along <= RAMP_LEN / 2 && Math.abs(across) <= 2.0) return RAMP_H * (along + RAMP_LEN / 2) / RAMP_LEN;
        }
        return 0.0;
    }

    inZone(kind, x, y) {
        const z = this.zones[kind];
        return !!z && z[0] <= x && x <= z[2] && z[1] <= y && y <= z[3];
    }
}

// ---------- the design ----------
export function defaultDesign(name = "Driver", colour = [220, 60, 50], body = "coupe", look = "woman") {
    return {name, colour: [...colour], body, look, points: {speed: 34, acceleration: 33, grip: 33}, settings: {}};
}

// what the points buy the car (Kart Lab's sums): top speed m/s, acceleration m/s^2, grip, steering deg/s
export function statsOf(design) {
    const pts = (design && design.points) || design || {};
    const [sp, ac, gr] = STATS.map(k => pts[k] ?? 33);
    return {top: 17.0 + 0.22 * sp, accel: 5.0 + 0.10 * ac, grip: 6.0 + 0.10 * gr, steer: 95.0 + 1.0 * gr};
}

export function wrap(deg) {
    return pyMod(deg + 180.0, 360.0) - 180.0;
}

// the unit vector a yaw points along, with kart_math's cos and sin (for the steps)
export function facingExact(yaw) {
    const yr = radians(yaw);
    return [cos(yr), sin(yr)];
}

// ---------- a person ----------
// one tick of a person on foot: a new record. inp: [move x, move y, buttons] in the world's frame (x east, y north).
// In a car (link) only the counters tick: the server puts them where the car is
export function stepPerson(p, inp, dt, city) {
    const [mx, my, bt] = inp;
    const n = {...p};
    let move = p.move, mp = p.mp, flags = 0;
    let hp = p.hp;
    // the counters
    if (n.lk) n.lk -= 1;
    if (n.bg) n.bg -= 1;
    // health creeps back (the aux field counts the ticks below its chips)
    let regen = p.aux & 255;
    const chips = p.aux & ~255;
    if (hp < HEALTH && hp > 0 && !p.link) {
        regen += 1;
        if (regen >= REGEN_TICKS) { regen = 0; hp = hp + 1; }
    }
    n.aux = chips | regen;
    const carried = p.flags & FLAG_PARCEL;
    if (p.link) {  // in a car: no moving about
        Object.assign(n, {move: 0, mp: 0, flags: carried, hp, v: 0.0, u: 0.0, z: 0.0, vz: 0.0, steer: 0.0});
        return n;
    }
    // a move running
    if (move) {
        mp += 1;
        if (move === MOVE_BLOCK) {
            if (!(bt & BLOCK)) { move = MOVE_NONE; mp = 0; }
        } else if (mp >= (MOVE_TICKS[move] ?? 1)) {
            if (move === MOVE_DOWN) {
                move = MOVE_GETUP; mp = 0;
                hp = Math.max(hp, DOWN_HEALTH);
            } else { move = MOVE_NONE; mp = 0; }
        }
    }
    if (!move || move === MOVE_BLOCK) {
        if ((bt & PUNCH) && !move) { move = MOVE_PUNCH; mp = 0; }
        else if ((bt & KICK) && !move) { move = MOVE_KICK; mp = 0; }
        else if ((bt & BLOCK) && !move && p.z === 0.0) { move = MOVE_BLOCK; mp = 0; }
    }
    const stuck = [MOVE_PUNCH, MOVE_KICK, MOVE_DOWN, MOVE_GETUP, MOVE_HURT].includes(move);
    const blocking = move === MOVE_BLOCK;
    if (blocking) flags |= FLAG_BLOCK;
    if (move === MOVE_DOWN) flags |= FLAG_DOWN;
    if (move === MOVE_HURT) flags |= FLAG_HURT;
    // moving
    let mag = hypot(mx, my);
    let want = 0.0, dx, dy, yaw;
    if (!stuck && mag > 0.1) {
        dx = mx / mag;
        dy = my / mag;
        mag = pyMin(1.0, mag);
        want = mag * ((bt & RUN) && !blocking ? RUN_SPEED : WALK);
        if (blocking) want *= 0.5;
        if ((bt & RUN) && !blocking) flags |= FLAG_RUN;
        const aim = degrees(atan2(my, mx));
        const d = wrap(aim - p.yaw);
        const turn = pyMax(-TURN_RATE * dt, pyMin(TURN_RATE * dt, d));
        yaw = wrap(p.yaw + turn);
    } else {
        yaw = p.yaw;
        [dx, dy] = facingExact(yaw);
    }
    let v = p.v;
    const rate = p.z === 0.0 ? 14.0 : 2.0;
    v += (want - v) * pyMin(1.0, rate * dt);
    if (stuck && p.z === 0.0) v *= pyMax(0.0, 1.0 - 12.0 * dt);
    if (v < 0.02) v = 0.0;
    // a jump
    let z = p.z, vz = p.vz;
    if ((bt & JUMP) && z === 0.0 && vz === 0.0 && !stuck && !blocking) vz = JUMP_V;
    if (z > 0.0 || vz > 0.0) {
        vz -= GRAVITY * dt;
        z += vz * dt;
        if (z <= 0.0) { z = 0.0; vz = 0.0; }
        else flags |= FLAG_AIR;
    }
    let x = p.x + dx * v * dt;
    let y = p.y + dy * v * dt;
    [x, y] = city.collide(x, y, PERSON_R);
    Object.assign(n, {x, y, z, vz, yaw, v, u: 0.0, hp, move, mp, flags: flags | carried, steer: 0.0});
    return n;
}

// ---------- a car ----------
// one tick of a car: Kart Lab's arcade step with the city for a track. inp: [throttle, steer, buttons]; st:
// statsOf(design); driven false: nobody at the wheel (it rolls to a stop)
export function stepCar(k, inp, dt, city, st, driven = true) {
    const [th, steer, bt] = driven ? inp : [0.0, 0.0, 0];
    const n = {...k};
    let v = k.v, u = k.u, yaw = k.yaw;
    let top = st.top, accel = st.accel, grip = st.grip, steerRate = st.steer;
    let flags = 0;
    if (n.bg) n.bg -= 1;
    if (n.lk) n.lk -= 1;
    // damage: the engine loses speed and pull, the steering goes heavy; a wreck crawls
    const d = pyMin(DAMAGE_MAX, k.dmg) / DAMAGE_MAX;
    const wrecked = k.dmg >= DAMAGE_MAX;
    top *= 1.0 - 0.3 * d;
    accel *= 1.0 - 0.35 * d;
    steerRate *= 1.0 - 0.25 * d;
    if (wrecked) { top = pyMin(top, WRECK_SPEED); flags |= FLAG_WRECKED; }
    // what is under the wheels (where the last tick left it)
    const surf = city.surface(k.x, k.y);
    const ground = k.z > 0.0 ? city.rampHeight(k.x, k.y) : 0.0;  // (climbing a ramp is on the ground)
    const airborne = k.vz !== 0.0 || k.z > ground + 0.01;
    if (surf === "pave" || surf === "court") grip *= PAVE_GRIP;
    else if (surf === "grass" || surf === "quay") { grip *= GRASS_GRIP; accel *= GRASS_ACCEL; }
    if (airborne) { accel = 0.0; grip = grip * 0.2; flags |= FLAG_CAR_AIR; }
    if (th < 0) flags |= FLAG_BRAKING;
    const hb = Boolean(bt & HANDBRAKE) && Math.abs(v) > 0.5 && !airborne;
    const launch = Boolean(bt & LAUNCH) && th > 0 && Math.abs(v) < LAUNCH_SPEED && !hb && !airborne;
    if (hb) { flags |= FLAG_HANDBRAKE | FLAG_BRAKING; grip *= HB_GRIP; }
    if (launch) { flags |= FLAG_WHEELSPIN; accel *= LAUNCH_ACCEL; grip *= LAUNCH_GRIP; }
    let driftDir = k.flags & FLAG_DRIFT_L ? 1 : k.flags & FLAG_DRIFT_R ? -1 : 0;
    const drifting = Boolean(bt & DRIFT) && v > 7.0 && (driftDir !== 0 || steer !== 0) && !hb && !airborne;
    if (drifting) {
        if (driftDir === 0) driftDir = steer > 0 ? 1 : -1;
        flags |= driftDir > 0 ? FLAG_DRIFT_L : FLAG_DRIFT_R;
        grip *= 0.4;
    } else driftDir = 0;
    // speed
    if (hb) v = copysign(pyMax(0.0, Math.abs(v) - accel * HB_BRAKE * dt), v);
    else if (th >= 0 || v <= 0) v += th >= 0 ? (th * accel - accel * v / top) * dt : (th * accel * 0.5 - accel * v / top) * dt;
    else v -= accel * 1.6 * dt;
    if (th === 0 && !hb) v = copysign(pyMax(0.0, Math.abs(v) - ROLL * dt), v);
    if (!airborne) {
        if (surf === "pave" || surf === "court") v *= pyMax(0.0, 1.0 - PAVE_DRAG * dt);
        else if (surf === "grass" || surf === "quay") v *= pyMax(0.0, 1.0 - GRASS_DRAG * dt);
    }
    v = pyMax(-0.3 * top, pyMin(top, v));
    // steering
    let turn = pyMax(-1.0, pyMin(1.0, steer)) * steerRate * pyMin(1.0, Math.abs(v) / 6.0) * (1.0 - 0.4 * pyMin(1.0, Math.abs(v) / top));
    if (drifting) turn = turn * 1.3 + driftDir * 25.0;
    if (hb) turn *= HB_TURN;
    if (v < 0) turn = -turn;
    if (launch && steer !== 0) turn = pyMax(-1.0, pyMin(1.0, steer)) * LAUNCH_SPIN;
    if (airborne) turn = 0.0;
    const dyaw = turn * dt;
    yaw = wrap(yaw + dyaw);
    let pace = hypot(v, u);
    const r = radians(dyaw);
    const c = cos(r), s_ = sin(r);
    const v2 = v * c + u * s_;
    u = -v * s_ + u * c;
    v = v2;
    u *= exp(-grip * dt);
    pace *= 1.0 - (hb ? HB_SCRUB : drifting ? 0.12 : 0.03) * dt;
    v = copysign(Math.sqrt(pyMax(0.0, pace * pace - u * u)), v ? v : 1.0);
    const yr = radians(yaw);
    const fx = cos(yr), fy = sin(yr);
    let x = k.x + (fx * v - fy * u) * dt;
    let y = k.y + (fy * v + fx * u) * dt;
    // the kerb: a bump as it is crossed
    if (!airborne && city.kerbBetween(k.x, k.y, x, y)) {
        v *= KERB_BUMP;
        u *= KERB_BUMP;
    }
    // the buildings, the posts, the city's edge: held at them, the slide stopped, damage over HIT_SPEED into them
    const [cx, cy, hit] = city.collide(x, y, CAR_R);
    let into = 0.0;
    if (hit) {
        const px = cx - x, py = cy - y;
        const pd = hypot(px, py);
        if (pd > 1e-9) {
            const nx = px / pd, ny = py / pd;
            let wx = fx * v - fy * u, wy = fy * v + fx * u;
            into = -(wx * nx + wy * ny);
            if (into > 0.0) {
                if (into > HIT_SPEED && !n.bg) {
                    n.dmg = pyMin(DAMAGE_MAX, k.dmg + Math.trunc((into - HIT_SPEED) * HIT_WALL));
                    n.bg = BUMP_GRACE;
                }
                wx += nx * into;
                wy += ny * into;
                v = wx * fx + wy * fy;
                u = -wx * fy + wy * fx;
                v *= pyMax(0.0, 1.0 - 3.0 * dt);
            }
        }
        x = cx;
        y = cy;
    }
    // the ramps and the air
    let z = k.z, vz = k.vz;
    const ramp = city.rampHeight(x, y);
    if (airborne) {
        vz -= GRAVITY * dt;
        z += vz * dt;
        if (z <= ramp) { z = ramp; vz = 0.0; }
    } else {
        const was = ground;
        if (ramp > 0.0) z = ramp;
        else if (was > 0.3 && v > 2.0) {  // off the lip: a hop
            vz = v * RAMP_H / RAMP_LEN * 1.6;
            z = was + vz * dt;
            flags |= FLAG_CAR_AIR;
        } else z = 0.0;
    }
    // mending: a little by itself, fast on the garage's forecourt stopped (a wreck stays one until the garage mends it)
    const atGarage = Math.abs(v) < GARAGE_STOP && city.inZone("garage", x, y);
    const mend = atGarage ? REPAIR_GARAGE : wrecked ? 0 : REPAIR_TICK;
    if (n.dmg && into <= HIT_SPEED) n.dmg = pyMax(0, n.dmg - mend);
    Object.assign(n, {x, y, z, vz, yaw, v, u, flags, steer: driven ? steer : 0.0});
    return n;
}

// ---------- the wire and the prediction ----------
// the record's fields as the integers on the wire, and the values as they will be after a trip over it (engine.wire's
// Schema.ints and quantise, as kart_sim.js has them, with City Lab's record)
export function wireInts(values) {
    return kartWireInts(values, SCHEMA_FIELDS);
}

export function quantise(values) {
    return kartQuantise(values, SCHEMA_FIELDS);
}

// how far apart two states of the same thing are (city_sim.compare): metres, with a little for the speed and the
// heading; what only the server decides (a knockdown, a hit, getting in, the pay, the damage) counts as 1, enough to
// take the server's record
const SERVERS_OWN = ["move", "link", "hp", "cash", "dmg", "aux", "job"];
export function compare(a, b) {
    if (a == null || b == null) return Infinity;
    const dyaw = Math.abs(wrap(a.yaw - b.yaw));
    const differ = SERVERS_OWN.some(k => a[k] !== b[k]);
    return hypot(a.x - b.x, a.y - b.y) + Math.abs(a.v - b.v) * 0.05 + dyaw * 0.01 + (differ ? 1.0 : 0.0);
}

// the window's step for what it controls (city_client.step_fn): a person on foot, or a car driven as the driver's
// points say (stats: statsOf the driver's design); then rounded to the wire as the server does, so the next tick
// starts from the same numbers
export function makeStep(city, kind, stats = null) {
    if (kind === "person") {
        return (s, inp, dt) => {
            const n = stepPerson(s, inp, dt, city);
            return Object.assign(n, quantise(n));
        };
    }
    return (s, inp, dt) => {
        const n = stepCar(s, inp, dt, city, stats, true);
        return Object.assign(n, quantise(n));
    };
}
