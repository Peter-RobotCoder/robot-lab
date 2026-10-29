// Craft Lab's movement and world for the page (CHANGE 202): craft/craft_sim.py's player step ported line for line
// (walking, running, Careful mode at an edge, jumping, stepping up onto a step or a Recharge Pod, swimming, climbing,
// flying),
// the world's questions it asks (craft_world.World's get, the blocks' solid, liquid and climbable tables and their
// heights), the ray from your eyes to the block you look at, the digging time (craft_blocks.dig_time), and the wire
// record (craft_sim.SCHEMA_FIELDS) with engine.wire's rounding: what the page needs to predict its own player as the
// window does.
//
// The rule every game's prediction keeps: the server, the window and the page step a player with the same lines of
// arithmetic and round the result to the wire's precision each tick (a millimetre, a hundredth of a metre a second),
// so all three start each tick from the same numbers. Python's arithmetic is kept where JavaScript's differs
// (pymath.js: round half to even, math.hypot, radians, sin, cos and exp; pyMax and pyMin: the first of equals), so the
// numbers are Python's to the last bit; craft_sim_test.py checks it against the game's own Python.
//
// The world (World below) is craft_world.World's arrays, x east, y north, z up, one byte a block: the blocks and their
// meta from the server's packed world (inflated by the page), the sky light and the block light worked out here as
// craft_world.light_region works them out (the same numbers: the test checks those too), changed block by block as the
// server's changes come. Which chunks need drawing again is kept as the window keeps it (dirty, mark).

import {pyRound, hypot, radians, sin, cos, exp} from "./pymath.js";

export const SIM_VERSION = 2;  // (craft_sim.SIM_VERSION: craft_sim_test.py's fingerprint is recorded for it)
export const STEP = 1 / 60;
export const HALF = 0.35;           // half the box's width
export const TALL = 1.7;
export const EYE = 1.55;
export const CAREFUL_TALL = 1.4;
export const CAREFUL_EYE = 1.3;
export const GRAVITY = 30.0;
export const JUMP = 9.17;           // (a jump lifts the feet 1.4 blocks)
export const TERMINAL = 60.0;
export const WALK = 4.5, SPRINT = 6.4, CAREFUL = 1.6, FLY_SPEED = 10.0, FLY_FAST = 18.0;
export const SWIM = 2.2, SWIM_UP = 4.0, SWIM_SINK = 1.6;
export const CLIMB = 2.4;
export const REACH = 5.0, REACH_CREATIVE = 6.5;
export const JUMP_B = 1, SPRINT_B = 2, CAREFUL_B = 4, FLY_B = 8, RESPAWN_B = 16;   // (flying, CAREFUL_B is down)

// the wire record: players and creatures alike (kind 0 player, 1 fluff, 2 bleep, 3 glitch, 4 rust, 5 bot; 6 a thing
// dropped, which the server sends with kind, place and held only); hp, energy and shield are the server's own (0 to
// 100), never predicted
export const SCHEMA_FIELDS = [["kind", "B", 1], ["x", "i", 1000], ["y", "i", 1000], ["z", "i", 1000], ["vx", "h", 100],
                              ["vy", "h", 100], ["vz", "h", 100], ["yaw", "H", 100], ["pitch", "h", 100], ["flags", "B", 1],
                              ["hp", "B", 1], ["energy", "B", 1], ["shield", "B", 1], ["held", "H", 1],
                              ["fall", "H", 100]];
export const F_GROUND = 1, F_WATER = 2, F_FLY = 4, F_CAREFUL = 8, F_HURT = 16, F_SLEEP = 32, F_SWING = 64, F_CLIMB = 128;
export const KINDS = {player: 0, fluff: 1, bleep: 2, glitch: 3, rust: 4, bot: 5};
export const KIND_NAMES = Object.fromEntries(Object.entries(KINDS).map(([k, v]) => [v, k]));

export const pyMax = (a, b) => (b > a ? b : a);   // (Python's max(a, b): the first of equals)
export const pyMin = (a, b) => (b < a ? b : a);

// ---------- the blocks (craft_blocks.BLOCKS, from craft.json, and the server's mods) ----------
const DEFAULTS = {shape: "cube", solid: true, opaque: true, hard: 1.0, tool: null, level: 0, light: 0, falls: false, see: null,
                  use: null, climb: false, hurts: 0};
export const B = {blocks: [], id: {}, items: new Map(), itemId: {}, hand: {tool: null, level: 0, speed: 1.0, damage: 4}, nBuiltIn: 0,
                  lightMax: 12, animated: {server_rack_0: 4}, floor: 5};
let solidT = new Uint8Array(256), liquidT = new Uint8Array(256), climbT = new Uint8Array(256), heightT = new Float64Array(256).fill(1.0);

// the game's tables from craft.json (make_craft.py): its blocks and items
export function useTables(data) {
    B.blocks = data.blocks.map(b => Object.assign({}, DEFAULTS, b));
    B.id = Object.fromEntries(B.blocks.map(b => [b.key, b.id]));
    B.items = new Map(data.items.map(it => [it.id, it]));
    B.itemId = Object.fromEntries(data.items.map(it => [it.key, it.id]));
    if (data.hand) B.hand = data.hand;
    B.nBuiltIn = data.n_built_in || B.blocks.length;
    // (craft_blocks.LIGHT_MAX, ANIMATED and FLOOR, from craft.json)
    B.lightMax = data.light_max ?? 12;
    B.animated = data.animated ?? {server_rack_0: 4};
    B.floor = B.id.lab_floor ?? 5;
    remakeTables();
}

// a learner's block from the server (welcome's mods, lesson's blocks): craft_blocks.add_block, as the window's take_mods.
// Returns true when it was new
export function addModBlock(spec) {
    if (!spec || !spec.key || spec.key in B.id || B.blocks.length >= 256) return false;
    const i = B.blocks.length;
    const b = Object.assign({}, DEFAULTS, {id: i, key: spec.key, name: spec.name || spec.key, tiles: [`mod_${spec.key}`, `mod_${spec.key}`, `mod_${spec.key}`],
                                           hard: spec.hard ?? 1.0, light: spec.light || 0, tool: spec.tool || null, mod: true,
                                           colour: spec.colour || null, drops: spec.key});
    B.blocks.push(b);
    B.id[b.key] = i;
    B.items.set(i, {id: i, key: b.key, name: b.name, icon: b.tiles[1], block: i, stack: 50});
    B.itemId[b.key] = i;
    remakeTables();
    return true;
}

function remakeTables() {
    solidT = new Uint8Array(256); liquidT = new Uint8Array(256); climbT = new Uint8Array(256); heightT = new Float64Array(256).fill(1.0);
    for (const b of B.blocks) {
        solidT[b.id] = b.solid ? 1 : 0;
        liquidT[b.id] = b.shape === "liquid" ? 1 : 0;
        climbT[b.id] = b.climb ? 1 : 0;
        heightT[b.id] = {slab: 0.5, bed: 0.6, farmland: 0.875}[b.shape] ?? 1.0;
    }
}

// craft_sim.tables(): (solid, liquid, climb) by block id
export function tables() { return [solidT, liquidT, climbT]; }

// how tall a solid block is (a step and a Recharge Pod are lower: you walk up onto them; a Grow bed too)
export function heights(bid) { return heightT[bid]; }

export function itemOf(id) { return B.items.get(id) || null; }
export function nameOf(id) { const it = B.items.get(id); return it ? it.name : "?"; }

// craft_blocks.dig_time: seconds to dig block bid holding item held (an item or null), and whether it drops anything
export function digTime(bid, held) {
    const b = B.blocks[bid];
    if (!b || b.hard === null || b.hard === undefined) return [null, false];
    const tool = held && held.tool ? held : B.hand;
    const right = b.tool !== null && b.tool !== undefined && tool.tool === b.tool;
    const speed = right ? (tool.speed ?? 1.0) : 1.0;
    const enough = b.level ? (right && (tool.level ?? 0) >= b.level) : true;
    let t = b.hard * 1.5 / speed;
    if (!enough) t *= 3.3;
    return [pyMax(0.05, t), enough];
}

// ---------- the world (craft_world.World's arrays and the questions the step asks) ----------
export const CHUNK = 16;
export const SIZES = {small: [128, 128, 64], medium: [192, 192, 64], large: [256, 256, 80]};

export class World {
    constructor(sizeKey, seed = 1, spawn = null) {
        this.sizeKey = SIZES[sizeKey] ? sizeKey : "medium";
        [this.X, this.Y, this.Z] = SIZES[this.sizeKey];
        this.seed = seed;
        const n = this.X * this.Y * this.Z;
        this.blocks = new Uint8Array(n);
        this.meta = new Uint8Array(n);
        this.sky = new Uint8Array(n);
        this.glow = new Uint8Array(n);
        this.spawn = spawn || [this.X / 2 + 0.5, this.Y / 2 + 0.5, this.Z - 4];
        this.dirty = new Set();       // chunks to draw again: "cx,cy"
        this.floor = B.floor;  // (craft_blocks.FLOOR: the Lab floor, under the world)
    }

    // the blocks and the meta as the server packs them (numpy's C order: x, then y, then z), inflated
    load(blocks, meta) {
        if (blocks.length !== this.blocks.length || meta.length !== this.meta.length) throw new Error("the world's size doesn't add up");
        this.blocks.set(blocks);
        this.meta.set(meta);
        this.lightAll();
    }

    at(x, y, z) { return (x * this.Y + y) * this.Z + z; }

    inside(x, y, z) { return x >= 0 && x < this.X && y >= 0 && y < this.Y && z >= 0 && z < this.Z; }

    get(x, y, z) {
        if (x >= 0 && x < this.X && y >= 0 && y < this.Y && z >= 0 && z < this.Z) return this.blocks[(x * this.Y + y) * this.Z + z];
        return z < 0 ? this.floor : 0;
    }

    getMeta(x, y, z) { return this.inside(x, y, z) ? this.meta[this.at(x, y, z)] : 0; }

    top(x, y) {  // the highest block that isn't air in a column (0 if none)
        for (let z = this.Z - 1; z >= 0; z--) if (this.blocks[this.at(x, y, z)]) return z;
        return 0;
    }

    // a block put in (or air): its light worked out again round it and the chunks it touches drawn again
    // (craft_world.set without the record: the page's own dig shown at once, put right by the server's changes)
    set(x, y, z, bid, meta = 0, light = true) {
        if (!this.inside(x, y, z)) return false;
        const i = this.at(x, y, z);
        this.blocks[i] = bid;
        this.meta[i] = meta;
        const L = B.lightMax;
        if (light) this.lightRegion(Math.max(0, x - L), Math.max(0, y - L), Math.min(this.X, x + L + 1), Math.min(this.Y, y + L + 1));
        this.mark(x, y, light ? L : 1);
        return true;
    }

    mark(x, y, reach = 1) {  // the chunks within reach blocks of (x, y) need drawing again (light reaches 12 blocks)
        const cx0 = Math.max(0, Math.floor((x - reach) / CHUNK)), cx1 = Math.min(this.X / CHUNK - 1, Math.floor((x + reach) / CHUNK));
        const cy0 = Math.max(0, Math.floor((y - reach) / CHUNK)), cy1 = Math.min(this.Y / CHUNK - 1, Math.floor((y + reach) / CHUNK));
        for (let cx = cx0; cx <= cx1; cx++) for (let cy = cy0; cy <= cy1; cy++) this.dirty.add(cx + "," + cy);
    }

    // block changes from the server ([x, y, z, block, meta] each): the light worked out once over the box they cover
    applyChanges(changes) {
        if (!changes || !changes.length) return;
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        const L = B.lightMax;
        for (const [x, y, z, bid, meta] of changes) {
            x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
            if (this.inside(x, y, z)) {
                const i = this.at(x, y, z);
                this.blocks[i] = bid;
                this.meta[i] = meta;
                this.mark(x, y, L);
            }
        }
        this.lightRegion(Math.max(0, x0 - L), Math.max(0, y0 - L), Math.min(this.X, x1 + L + 1), Math.min(this.Y, y1 + L + 1));
    }

    lightAll() {
        this.sky.fill(0);
        this.glow.fill(0);
        this.lightRegion(0, 0, this.X, this.Y);
    }

    // craft_world.light_region: the sky straight down each open column (one less for each leaf or pane of water it
    // passes), then the sky and the block light spread sideways and down, one level less a block (more through
    // leaves and water), over the columns x0..x1, y0..y1 and LIGHT_MAX (12) more round them. The window does it as 11
    // rounds of numpy's neighbour maxima; here a queue from the brightest down (each block's light is the best of
    // every way to it: the same numbers, for light reaches 11 blocks at most)
    lightRegion(x0, y0, x1, y1) {
        const L = B.lightMax, m = L, Z = this.Z, Y = this.Y;
        const ax0 = Math.max(0, x0 - m), ay0 = Math.max(0, y0 - m), ax1 = Math.min(this.X, x1 + m), ay1 = Math.min(this.Y, y1 + m);
        const W = ax1 - ax0, H = ay1 - ay0, n = W * H * Z;
        const dimOf = dimTable(), lightOf = lightTable();
        const dim = new Uint8Array(n), sky = new Int16Array(n), glow = new Int16Array(n);
        for (let i = 0; i < W; i++) {
            for (let j = 0; j < H; j++) {
                const src = ((ax0 + i) * Y + (ay0 + j)) * Z, dst = (i * H + j) * Z;
                let stop = 0, loss = 0;
                for (let z = Z - 1; z >= 0; z--) {
                    const b = this.blocks[src + z], d = dimOf[b];
                    dim[dst + z] = d;
                    if (d >= 15) stop++; else loss += d - 1;
                    sky[dst + z] = stop === 0 ? Math.max(0, Math.min(L, L - loss)) : 0;
                    glow[dst + z] = lightOf[b];
                }
            }
        }
        for (const arr of [sky, glow]) spread(arr, dim, W, H, Z);
        for (let x = x0; x < x1; x++) {
            for (let y = y0; y < y1; y++) {
                const src = ((x - ax0) * H + (y - ay0)) * Z, dst = (x * Y + y) * Z;
                for (let z = 0; z < Z; z++) {
                    this.sky[dst + z] = Math.max(0, Math.min(L, sky[src + z]));
                    this.glow[dst + z] = Math.max(0, Math.min(L, Math.max(glow[src + z], lightOf[this.blocks[dst + z]])));
                }
            }
        }
    }
}

// light passes through air, plants, glowsticks, glass, leaves (a little), water (a little): craft_world.tables()'s
// dim (15 stops it)
let dimCache = null, lightCache = null, dimFor = -1;
function dimTable() {
    if (dimCache && dimFor === B.blocks.length) return dimCache;
    const dim = new Uint8Array(256).fill(15), light = new Uint8Array(256);
    for (const b of B.blocks) {
        if (!b.opaque || b.shape !== "cube") dim[b.id] = 1;
        light[b.id] = b.light || 0;
    }
    for (const k of ["leaves", "pine_leaves", "pale_leaves", "glowfruit_leaves", "water", "ice"]) if (k in B.id) dim[B.id[k]] = 2;
    dimCache = dim; lightCache = light; dimFor = B.blocks.length;
    return dim;
}
function lightTable() { dimTable(); return lightCache; }

// the light spread from the brightest down (a bucket for each level): a block takes its neighbour's level less its
// own dimming where that is more than it has, and a block light can't pass (stone) keeps its own
function spread(arr, dim, W, H, Z) {
    const n = arr.length;
    let top = 0;
    for (let i = 0; i < n; i++) if (arr[i] > top) top = arr[i];
    const buckets = Array.from({length: top + 1}, () => []);
    for (let i = 0; i < n; i++) if (arr[i] >= 2) buckets[arr[i]].push(i);
    const HZ = H * Z;
    for (let v = top; v >= 2; v--) {
        const list = buckets[v];
        for (let k = 0; k < list.length; k++) {
            const c = list[k];
            if (arr[c] !== v) continue;
            const z = c % Z, j = Math.floor(c / Z) % H, i = Math.floor(c / HZ);
            const tryCell = nb => {
                const d = dim[nb];
                if (d >= 15) return;
                const cand = v - d;
                if (cand > arr[nb]) { arr[nb] = cand; if (cand >= 2) buckets[cand].push(nb); }
            };
            if (i > 0) tryCell(c - HZ);
            if (i < W - 1) tryCell(c + HZ);
            if (j > 0) tryCell(c - Z);
            if (j < H - 1) tryCell(c + Z);
            if (z > 0) tryCell(c - 1);
            if (z < Z - 1) tryCell(c + 1);
        }
        buckets[v] = null;
    }
}

// ---------- the step (craft_sim.py) ----------
export function newPlayer(x, y, z, kind = 0) {
    return {x, y, z, vx: 0.0, vy: 0.0, vz: 0.0, yaw: 0.0, pitch: 0.0, flags: 0, hp: 100, energy: 100, shield: 0, held: 0,
            fall: 0.0, kind};
}

// is any solid block inside the box (x0..x1, y0..y1, z0..z1)?
export function blocked(world, x0, y0, z0, x1, y1, z1, solid) {
    for (let bx = Math.floor(x0); bx < Math.floor(x1 - 1e-7) + 1; bx++) {
        for (let by = Math.floor(y0); by < Math.floor(y1 - 1e-7) + 1; by++) {
            for (let bz = Math.floor(z0); bz < Math.floor(z1 - 1e-7) + 1; bz++) {
                const bid = world.get(bx, by, bz);
                if (solid[bid]) {
                    const h = heightT[bid];
                    if (h >= 1.0 || z0 < bz + h) return true;
                }
            }
        }
    }
    return false;
}

// is the box in any block that table says (water, a ladder)?
export function touching(world, s, table, tall = TALL) {
    const x0 = s.x - HALF, y0 = s.y - HALF;
    for (let bx = Math.floor(x0); bx < Math.floor(s.x + HALF - 1e-7) + 1; bx++) {
        for (let by = Math.floor(y0); by < Math.floor(s.y + HALF - 1e-7) + 1; by++) {
            for (let bz = Math.floor(s.z + 0.1); bz < Math.floor(s.z + tall * 0.6) + 1; bz++) {
                if (table[world.get(bx, by, bz)]) return true;
            }
        }
    }
    return false;
}

// move the box along one axis by delta, stopped at the first solid block: true if it was stopped (craft_sim.move_axis)
export function moveAxis(world, s, axis, delta, tall, solid, stepUp = false) {
    if (delta === 0) return false;
    const x = s.x, y = s.y, z = s.z;
    if (axis === 2) {
        const nz = z + delta;
        if (!blocked(world, x - HALF, y - HALF, nz, x + HALF, y + HALF, nz + tall, solid)) {
            s.z = nz;
            return false;
        }
        if (delta < 0) {
            let best = null;
            for (let bx = Math.floor(x - HALF); bx < Math.floor(x + HALF - 1e-7) + 1; bx++) {
                for (let by = Math.floor(y - HALF); by < Math.floor(y + HALF - 1e-7) + 1; by++) {
                    for (let bz = Math.floor(z + 1e-6); bz > Math.floor(nz) - 1; bz--) {
                        const bid = world.get(bx, by, bz);
                        if (solid[bid]) {
                            const top = bz + heightT[bid];
                            if (top <= z + 1e-6) best = best === null ? top : pyMax(best, top);
                            break;
                        }
                    }
                }
            }
            if (best !== null && best >= nz - 1e-6) s.z = best;
        }
        return true;
    }
    const key = axis === 0 ? "x" : "y";
    const n = s[key] + delta;
    const [bx0, by0] = axis === 0 ? [n - HALF, y - HALF] : [x - HALF, n - HALF];
    if (!blocked(world, bx0, by0, z + 1e-4, bx0 + 2 * HALF, by0 + 2 * HALF, z + tall, solid)) {
        s[key] = n;
        return false;
    }
    if (stepUp) {
        for (const lift of [0.5, 0.6]) {
            if (!blocked(world, bx0, by0, z + lift, bx0 + 2 * HALF, by0 + 2 * HALF, z + lift + tall, solid) &&
                blocked(world, bx0, by0, z + lift - 0.07, bx0 + 2 * HALF, by0 + 2 * HALF, z + lift, solid)) {
                s[key] = n;
                s.z = z + lift;
                return false;
            }
        }
    }
    return true;
}

export function onGround(world, s, solid) {
    return blocked(world, s.x - HALF, s.y - HALF, s.z - 0.02, s.x + HALF, s.y + HALF, s.z, solid);
}

// one step of a player: s isn't changed, the next state is returned (craft_sim.step_player)
export function stepPlayer(s, inp, dt, world, creative = false) {
    const [solid, liquid, climb] = tables();
    let [mx, my, buttons] = inp;
    const n = {...s};
    let flags = n.flags;
    const flying = creative && !!(buttons & FLY_B);
    const careful = !!(buttons & CAREFUL_B) && !flying;
    const sprint = !!(buttons & SPRINT_B) && !careful;
    const tall = careful ? CAREFUL_TALL : TALL;
    const inWater = touching(world, n, liquid, tall);
    const onLadder = touching(world, n, climb, tall);
    const length = hypot(mx, my);
    if (length > 1) { mx = mx / length; my = my / length; }
    let speed;
    if (flying) speed = sprint ? FLY_FAST : FLY_SPEED;
    else if (inWater) speed = SWIM;
    else speed = sprint ? SPRINT : careful ? CAREFUL : WALK;
    const ground = !!(flags & F_GROUND);
    const k = (ground || flying) ? 22.0 : !inWater ? 5.0 : 8.0;
    const f = 1 - exp(-k * dt);
    n.vx += (mx * speed - n.vx) * f;
    n.vy += (my * speed - n.vy) * f;
    if (flying) {
        const want = (buttons & JUMP_B ? FLY_SPEED : 0.0) - (buttons & CAREFUL_B ? FLY_SPEED : 0.0);
        n.vz += (want - n.vz) * (1 - exp(-12 * dt));
    } else if (inWater) {
        n.vz = buttons & JUMP_B ? SWIM_UP : pyMax(n.vz - GRAVITY * 0.2 * dt, -SWIM_SINK);
    } else if (onLadder) {
        n.vz = (buttons & JUMP_B || length > 0.1) ? CLIMB : pyMax(n.vz - GRAVITY * dt, -CLIMB);
        if (careful) n.vz = pyMax(0.0, n.vz);
    } else {
        if (ground && buttons & JUMP_B) n.vz = JUMP;
        n.vz = pyMax(-TERMINAL, n.vz - GRAVITY * dt);
    }
    // move: up or down first, then across and along (Careful mode keeps you on the edge you are on)
    const zBefore = n.z;
    const stoppedZ = moveAxis(world, n, 2, n.vz * dt, tall, solid);
    if (stoppedZ) n.vz = 0.0;
    for (const [axis, key] of [[0, "vx"], [1, "vy"]]) {
        const delta = n[key] * dt;
        if (careful && ground && delta) {
            const test = {...n};
            test[axis === 0 ? "x" : "y"] += delta;
            if (!onGround(world, test, solid)) {
                n[key] = 0.0;
                continue;
            }
        }
        if (moveAxis(world, n, axis, delta, tall, solid, ground && !flying)) n[key] = 0.0;
    }
    const nowGround = onGround(world, n, solid) && n.vz <= 0.01;
    // falling: how far since last standing (the server's damage is worked out from it on landing)
    if (nowGround || inWater || onLadder || flying) n.fall = nowGround && !ground ? n.fall : 0.0;
    else n.fall = n.fall + pyMax(0.0, zBefore - n.z);
    flags &= ~(F_GROUND | F_WATER | F_FLY | F_CAREFUL | F_CLIMB);
    flags |= (nowGround ? F_GROUND : 0) | (inWater ? F_WATER : 0) | (flying ? F_FLY : 0) | (careful ? F_CAREFUL : 0) |
        (onLadder ? F_CLIMB : 0);
    n.flags = flags;
    if (n.z < -20) {  // (fallen out of the world: back on top)
        n.z = world.Z;
        n.vz = 0.0;
    }
    return n;
}

// how far apart two records are, for the prediction: metres (1.0 for any flag the step owns that differs)
export function compare(a, b) {
    if (a == null || b == null) return Infinity;
    const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
    let d = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if ((a.flags ^ b.flags) & (F_GROUND | F_WATER | F_FLY | F_CAREFUL)) d = pyMax(d, 1.0);
    return d;
}

// the window's step for its own player (craft_client.step_fn): the step, then rounded to the wire as the server does
export function makeStep(world, creative) {
    return (s, inp, dt) => {
        const n = stepPlayer(s, inp, dt, world, typeof creative === "function" ? creative() : creative);
        Object.assign(n, quantise(n));
        return n;
    };
}

// ---------- looking at a block ----------
// the way you look: yaw degrees from +x towards +y (0 east, 90 north), pitch up from level
export function lookDir(yaw, pitch) {
    const cy = cos(radians(yaw)), sy = sin(radians(yaw)), cp = cos(radians(pitch)), sp = sin(radians(pitch));
    return [cy * cp, sy * cp, sp];
}

// the first block (not air, not water) along the ray within reach: [[x, y, z], [nx, ny, nz] the face it came in
// through, the distance], or null: the grid's own walk
export function ray(world, ox, oy, oz, dx, dy, dz, reach) {
    let x = Math.floor(ox), y = Math.floor(oy), z = Math.floor(oz);
    const step = [dx, dy, dz].map(d => (d > 0 ? 1 : -1));
    const tMax = [], tDelta = [];
    for (const [o, d, c] of [[ox, dx, x], [oy, dy, y], [oz, dz, z]]) {
        if (Math.abs(d) < 1e-9) {
            tMax.push(Infinity);
            tDelta.push(Infinity);
        } else {
            const nxt = c + (d > 0 ? 1 : 0);
            tMax.push((nxt - o) / d);
            tDelta.push(Math.abs(1 / d));
        }
    }
    let normal = [0, 0, 0], t = 0.0;
    const water = B.id.water, floor = B.floor, rift = B.id.glitch_rift;
    const LOW = new Set(["cross", "crop", "torch", "ladder"]);
    while (t <= reach) {
        const bid = world.get(x, y, z);
        const b = B.blocks[bid];
        if ((bid && bid !== water && b && b.hard !== null && b.hard !== undefined) || bid === floor || bid === rift) return [[x, y, z], normal, t];
        if (bid && bid !== water && b && LOW.has(b.shape)) return [[x, y, z], normal, t];
        let axis = 0;  // (min(range(3), key=t_max): the first of equals)
        if (tMax[1] < tMax[axis]) axis = 1;
        if (tMax[2] < tMax[axis]) axis = 2;
        t = tMax[axis];
        tMax[axis] += tDelta[axis];
        if (axis === 0) { x += step[0]; normal = [-step[0], 0, 0]; }
        else if (axis === 1) { y += step[1]; normal = [0, -step[1], 0]; }
        else { z += step[2]; normal = [0, 0, -step[2]]; }
    }
    return null;
}

// would a block at (bx, by, bz) be inside the player? (You can't place a block where you stand.)
export function playerBoxHits(s, bx, by, bz, tall = TALL) {
    return bx < s.x + HALF && bx + 1 > s.x - HALF && by < s.y + HALF && by + 1 > s.y - HALF && bz < s.z + tall && bz + 1 > s.z;
}

export function eye(s) {
    return [s.x, s.y, s.z + (s.flags & F_CAREFUL ? CAREFUL_EYE : EYE)];
}

// ---------- the wire (engine.wire.Schema: the record rounded as it goes over the wire) ----------
const RANGE = {b: [-128, 127], B: [0, 255], h: [-32768, 32767], H: [0, 65535], i: [-2147483648, 2147483647], I: [0, 4294967295]};

export function wireInts(values, fields = SCHEMA_FIELDS) {
    const out = [];
    for (const [name, code, scale] of fields) {
        const [lo, hi] = RANGE[code];
        const v = pyRound((values[name] ?? 0) * scale);
        out.push(v < lo ? lo : v > hi ? hi : v);
    }
    return out;
}

// the values as they will be after a trip over the wire (engine.wire.Schema.quantise): only the schema's fields
export function quantise(values, fields = SCHEMA_FIELDS) {
    const ints = wireInts(values, fields), d = {};
    fields.forEach(([name, , scale], i) => { d[name] = scale === 1 ? ints[i] : ints[i] / scale; });
    return d;
}
