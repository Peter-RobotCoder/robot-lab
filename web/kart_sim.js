// Kart Lab's kart step (kart/kart_sim.py, ported line for line): what the browser needs to predict its own kart.
//
// The window and the server step every kart with the same few lines of arithmetic and round the result to the
// wire's precision each tick (centimetres, a tenth of a degree), so both start every tick from the same numbers.
// The browser does the same here: step() is kart_sim.step, quantise() is the wire schema's round trip, compare()
// is how far apart two states are. A kart's state is an object (x, y, yaw, v, u, charge, boost, slip, lap, cp,
// flags, tyre, and seg, s, lat: where it is on the track); its input is [throttle, steer, buttons], throttle and
// steer from -1 to 1 in hundredths (predict.js's quantiseInput), buttons DRIFT, USE, RESPAWN, LAUNCH and HANDBRAKE.
//
// Python's arithmetic is kept where JavaScript's differs (pymath.js: floored %, round half to even, math.hypot,
// radians), and sin, cos and exp are pymath.js's own, kart/kart_math.py's twins (CHANGE 162: the system's differ in
// the last bit between Python and each browser, and a value on the edge of the wire's rounding then flipped a whole
// step), so the result is Python's to the last bit by construction, on every computer and in every browser.
//
// Bumping, gates, laps and the countdown are the server's (kart_sim.Race); the browser learns of them from the
// snapshots. respawn() is here because the server applies it before the step (Race.step_all).

import {BOOST_RADIUS, OIL_RADIUS, GATES, KERB, LANE_WALL} from "./track.js";
import {pyMod, pyRound, copysign, hypot, radians, sin, cos, exp} from "./pymath.js";  // (sin, cos, exp: CHANGE 162)

export const STEP = 1 / 60;
export const POINTS_TOTAL = 100, STAT_MIN = 10, STAT_MAX = 60;
export const STATS = ["speed", "acceleration", "grip"];

export const DRIFT = 1, USE = 2, RESPAWN = 4;  // the input's buttons
export const LAUNCH = 8, HANDBRAKE = 16;      // (CHANGE 181) the clutch dropped; the handbrake
export const FLAG_DRIFT_L = 1, FLAG_DRIFT_R = 2, FLAG_FINISHED = 4, FLAG_WRONG_WAY = 8, FLAG_BOOSTING = 16;
export const FLAG_BRAKING = 32;    // (CHANGE 171) the brake (or reverse) pressed: the brake lights
export const FLAG_WHEELSPIN = 64;  // (CHANGE 181) the back wheels spinning (a burnout, a donut)
export const FLAG_HANDBRAKE = 128;  // ...and locked by the handbrake

export const KART_HALF = 0.8;          // half a kart's width: how close to the edge it may go (m)
export const BUMP_DISTANCE = 1.7;      // karts closer than this push each other apart (m)
export const BUMP_TRANSFER = 0.7;      // (CHANGE 176) the share of the closing speed passed from the kart behind to the one in front
export const MINI_TURBO = 270, SUPER_TURBO = 570;   // drift charge needed (Mario Kart's numbers)
export const MINI_BOOST = 37, SUPER_BOOST = 100;    // ...and the boosts they pay out, in ticks
export const PAD_BOOST = 90;                        // a dash pad's boost (1.5 s)
export const OIL_TICKS = 75;                        // how long an oil patch's slide lasts (1.25 s)
export const BOOST_SPEED = 1.25, BOOST_ACCEL = 1.5;
export const ROLL = 0.6;                            // off the throttle the tyres roll to a stop (m/s each second: CHANGE 156)
export const COUNTDOWN_TICKS = 60 * 4;
// (CHANGE 158) real damage: six parts, each 0 (like new) to DAMAGE_MAX (as bad as it gets), never knocked out
export const DAMAGE_PARTS = ["dw", "dfl", "dfr", "drl", "drr", "de"];  // front wing, the wheels, the engine
export const DAMAGE_MAX = 10000;
export const HIT_SPEED = 2.0, HIT_BARRIER = 900, HIT_KART = 1100;
export const HIT_KART_SPEED = 3.0, BUMP_GRACE = 60;  // (CHANGE 159: a bump damages once, then a second's grace)
export const REPAIR_TICK = 1, REPAIR_PIT = 80, PIT_SPEED = 12.0;
// (CHANGE 177) the kerb and the gravel; (CHANGE 181) the handbrake and the clutch dropped; (CHANGE 178) tyre wear
export const KERB_DRAG = 0.25, KERB_GRIP = 0.75;
export const GRAVEL_DRAG = 2.0, GRAVEL_ACCEL = 0.3, GRAVEL_GRIP = 0.5;
export const HB_GRIP = 0.25, HB_BRAKE = 1.2, HB_TURN = 1.5, HB_SCRUB = 0.2;
export const LAUNCH_SPEED = 6.0, LAUNCH_ACCEL = 0.35, LAUNCH_GRIP = 0.3, LAUNCH_SPIN = 150.0;
export const TYRE_GRIP = 0.5, TYRE_TOP = 0.08, TYRE_ACCEL = 0.1, TYRE_FRESH = 2.5, BAY_STOP = 1.5;
export const FLAGS_GRID = 0, FLAGS_RACE = 1, FLAGS_OVER = 2;  // the snapshot's flags byte: the race's phase

// the wire record for one kart (kart_sim.SCHEMA_FIELDS): name, struct code, scale
export const SCHEMA_FIELDS = [["x", "i", 100], ["y", "i", 100], ["yaw", "h", 10], ["v", "h", 100], ["u", "h", 100],
                              ["charge", "H", 1], ["boost", "B", 1], ["slip", "B", 1], ["lap", "B", 1],
                              ["cp", "B", 1], ["flags", "B", 1], ["steer", "b", 100],  // (steer: the input's, for the picture: CHANGE 157)
                              ["dw", "H", 1], ["dfl", "H", 1], ["dfr", "H", 1], ["drl", "H", 1], ["drr", "H", 1],
                              ["de", "H", 1],  // (each part's damage, 0 to DAMAGE_MAX: CHANGE 158)
                              ["item", "B", 1], ["shield", "H", 1],  // (the item held; shield ticks left: CHANGE 159)
                              ["bg", "B", 1],  // (a bump's grace: CHANGE 159)
                              ["tyre", "H", 10000]];  // (tyre wear, 0 to 1: CHANGE 178)
const RANGE = {b: [-128, 127], B: [0, 255], h: [-32768, 32767], H: [0, 65535],
               i: [-2147483648, 2147483647], I: [0, 4294967295]};

export function defaultDesign(name = "Kart", colour = [220, 60, 50]) {
    return {name, colour: [...colour], speed: 34, acceleration: 33, grip: 33};
}

// what the points buy: top speed (m/s), acceleration (m/s^2), grip (per second), steering (degrees a second)
export function statsOf(design) {
    const [sp, ac, gr] = STATS.map(k => design[k] ?? 33);
    return {top: 17.0 + 0.22 * sp, accel: 5.0 + 0.10 * ac, grip: 6.0 + 0.10 * gr, steer: 95.0 + 1.0 * gr};
}

export function newKart(id, design, s, lateral, heading) {
    return {id, x: 0.0, y: 0.0, yaw: heading, v: 0.0, u: 0.0, charge: 0, boost: 0, slip: 0, lap: 0, cp: 0,
            flags: 0, steer: 0.0, seg: 0, s, lat: lateral, dw: 0, dfl: 0, dfr: 0, drl: 0, drr: 0, de: 0, item: 0, shield: 0, bg: 0,
            tyre: 0.0};
}

// put a kart at s, lateral on the track (the grid, a respawn): changes k, as Python's does
export function place(track, k, s, lateral) {
    const [x, y] = track.point(s, lateral);
    Object.assign(k, {x, y, yaw: track.heading(s), v: 0.0, u: 0.0, charge: 0, boost: 0, slip: 0,
                      s: pyMod(s, track.length), lat: lateral, seg: track.segmentAt(s),
                      flags: k.flags & FLAG_FINISHED});
    return k;
}

// back onto the track at the last gate passed, facing the right way (Race.respawn): a new state
export function respawn(k, track) {
    const n = {...k};
    const cp = n.cp;
    const gate = cp ? pyMod(cp - 1, GATES) : GATES - 1;
    const s = cp ? track.gateS[gate] + 2.0 : track.grid(0)[0];
    return place(track, n, s, 0.0);
}

// (CHANGE 158) each part's damage as 0 (like new) to 1 (as bad as it gets): wing, fl, fr, rl, rr, engine
export function damageOf(k) {
    return DAMAGE_PARTS.map(p => Math.min(DAMAGE_MAX, Math.max(0, k[p] || 0)) / DAMAGE_MAX);
}

// (CHANGE 158) damage k's parts: amount (on DAMAGE_MAX's scale) shared out, shares: {part: fraction}
export function hurt(k, amount, shares) {
    for (const [part, share] of Object.entries(shares)) k[part] = Math.min(DAMAGE_MAX, Math.trunc((k[part] || 0) + amount * share));
}

// (CHANGE 158) who takes a hit, from where it lands in the kart's own frame (front +1 ahead, left +1 left)
export function sideShares(front, left) {
    if (front > 0.5) return left >= 0 ? {dw: 0.55, dfl: 0.3, de: 0.15} : {dw: 0.55, dfr: 0.3, de: 0.15};
    if (front < -0.5) return {drl: 0.35, drr: 0.35, de: 0.3};
    return left > 0 ? {dfl: 0.45, drl: 0.4, de: 0.15} : {dfr: 0.45, drr: 0.4, de: 0.15};
}

// (CHANGE 177, 179) what is under a kart at (seg, s, lat): "road", "kerb", "gravel" or "lane" (kart_sim.surface)
export function surface(track, seg, s, lat) {
    const a = Math.abs(lat);
    if (a <= track.half - KART_HALF) return "road";
    if (track.laneSide(lat)) {
        const zone = track.laneZone(s);
        if (zone !== null && (a > track.half + KERB + LANE_WALL / 2 || (zone === "ramp" && track.pits === "lane"))) return "lane";
    }
    if (a > track.half + KERB - KART_HALF && track.gravelAt(seg, lat > 0 ? 1 : -1) > 0.0) return "gravel";
    return "kerb";
}

// (CHANGE 178) tyre wear for each metre driven when a set lasts laps laps flat out (kart_sim.wear_rate)
export function wearRate(track, laps) {
    return 1.0 / (Math.max(1, Math.trunc(laps)) * track.length);
}

// one tick of one kart: the new state. k: the kart, inp: [throttle, steer, buttons], st: statsOf(design)
// damage (CHANGE 158): barrier hits damage the kart; wear (CHANGE 178): tyre wear for each metre driven
export function step(k, inp, dt, track, st, damage = false, wear = 0.0) {
    const [th, steer, bt] = inp;
    const n = {...k};
    let v = k.v, u = k.u, yaw = k.yaw;
    let top = st.top, accel = st.accel, grip = st.grip, steerRate = st.steer;
    // (CHANGE 158) damage: the engine loses top speed and pull, the wing steering and a little grip, the wheels a
    // little speed, and a side's damaged wheels drag the kart towards that side
    const [wing, fl, fr, rl, rr, eng] = damageOf(k);
    const wheels = (fl + fr + rl + rr) / 4;
    top *= (1.0 - 0.25 * eng) * (1.0 - 0.1 * wheels);
    accel *= 1.0 - 0.3 * eng;
    steerRate *= 1.0 - 0.3 * wing;
    grip *= 1.0 - 0.15 * wing;
    const pull = 0.25 * ((fl + rl) - (fr + rr)) / 2;
    // (CHANGE 178) worn tyres: less grip, a little less speed and pull
    let tyre = k.tyre || 0.0;
    grip *= 1.0 - TYRE_GRIP * tyre;
    top *= 1.0 - TYRE_TOP * tyre;
    accel *= 1.0 - TYRE_ACCEL * tyre;
    // (CHANGE 177) what is under the wheels (where the last tick left it)
    const surf = surface(track, k.seg, k.s, k.lat);
    if (surf === "kerb") grip *= KERB_GRIP;
    else if (surf === "gravel") { accel *= GRAVEL_ACCEL; grip *= GRAVEL_GRIP; }
    let boost = k.boost, slip = k.slip, charge = k.charge, flags = 0;
    if (th < 0) flags |= FLAG_BRAKING;  // (CHANGE 171) braking, or reversing: the brake lights
    if (boost) {
        top = top * BOOST_SPEED;
        accel = accel * BOOST_ACCEL;
        flags |= FLAG_BOOSTING;
    }
    if (slip) {  // on oil: the tyres have little to say
        grip *= 0.15;
        steerRate *= 0.5;
    }
    // (CHANGE 181) the handbrake locks the back wheels; the clutch dropped spins them
    const hb = Boolean(bt & HANDBRAKE) && Math.abs(v) > 0.5;
    const launch = Boolean(bt & LAUNCH) && th > 0 && Math.abs(v) < LAUNCH_SPEED && !hb;
    if (hb) { flags |= FLAG_HANDBRAKE | FLAG_BRAKING; grip *= HB_GRIP; }
    if (launch) { flags |= FLAG_WHEELSPIN; accel *= LAUNCH_ACCEL; grip *= LAUNCH_GRIP; }
    // drifting: holding DRIFT while steering above a trot; a charge builds that pays out as a boost when it ends
    let driftDir = k.flags & FLAG_DRIFT_L ? 1 : k.flags & FLAG_DRIFT_R ? -1 : 0;
    const drifting = Boolean(bt & DRIFT) && v > 7.0 && (driftDir !== 0 || steer !== 0) && !hb && surf !== "lane";
    if (drifting) {
        if (driftDir === 0) driftDir = steer > 0 ? 1 : -1;
        flags |= driftDir > 0 ? FLAG_DRIFT_L : FLAG_DRIFT_R;
        charge = Math.min(65535, charge + (steer * driftDir >= 0.5 ? 5 : 2));
        grip *= 0.4;
    } else {
        if (charge >= SUPER_TURBO) boost = Math.max(boost, SUPER_BOOST);
        else if (charge >= MINI_TURBO) boost = Math.max(boost, MINI_BOOST);
        charge = 0;
        driftDir = 0;
    }
    // speed: the motor pushes towards th * top; the brake bites harder; reverse is slow; the handbrake brakes
    if (hb) {
        v = copysign(Math.max(0.0, Math.abs(v) - accel * HB_BRAKE * dt), v);
    } else if (th >= 0 || v <= 0) {
        v += th >= 0 ? (th * accel - accel * v / top) * dt : (th * accel * 0.5 - accel * v / top) * dt;
    } else {
        v -= accel * 1.6 * dt;
    }
    if (th === 0 && !hb) v = copysign(Math.max(0.0, Math.abs(v) - ROLL * dt), v);  // (CHANGE 156: a kart let go crept on for ever)
    if (surf === "kerb") v *= Math.max(0.0, 1.0 - KERB_DRAG * dt);  // (CHANGE 177) the rumble strip, the gravel
    else if (surf === "gravel") v *= Math.max(0.0, 1.0 - GRAVEL_DRAG * dt);
    v = Math.max(-0.3 * top, Math.min(top, v));
    if (surf === "lane") v = Math.max(-PIT_SPEED, Math.min(PIT_SPEED, v));  // (CHANGE 179) the pit lane's limiter
    // steering: a rate that needs some speed to work and eases off at the top, tighter in a drift
    let turn = Math.max(-1.0, Math.min(1.0, steer + pull)) * steerRate * Math.min(1.0, Math.abs(v) / 6.0) * (1.0 - 0.4 * Math.min(1.0, Math.abs(v) / top));
    if (drifting) turn = turn * 1.3 + driftDir * 25.0;
    if (hb) turn *= HB_TURN;
    if (v < 0) turn = -turn;
    if (launch && steer !== 0) turn = Math.max(-1.0, Math.min(1.0, steer)) * LAUNCH_SPIN;  // (CHANGE 181) the donut
    const dyaw = turn * dt;
    yaw = pyMod(yaw + dyaw + 180.0, 360.0) - 180.0;
    // the velocity in the kart's own frame, carried round the turn; the tyres kill the slide, the pace is kept
    // apart from a scrub (bigger in a drift)
    let pace = hypot(v, u);
    const r = radians(dyaw);
    const c = cos(r), s_ = sin(r);
    const v2 = v * c + u * s_;
    u = -v * s_ + u * c;
    v = v2;
    u *= exp(-grip * dt);
    pace *= 1.0 - (hb ? HB_SCRUB : drifting ? 0.12 : 0.03) * dt;
    v = copysign(Math.sqrt(Math.max(0.0, pace * pace - u * u)), v ? v : 1.0);
    const yr = radians(yaw);
    const fx = cos(yr), fy = sin(yr);
    let x = k.x + (fx * v - fy * u) * dt;
    let y = k.y + (fy * v + fx * u) * dt;
    // the track: where we are along it, and the barriers at its edges (CHANGE 177: beyond the kerb and the gravel;
    // CHANGE 179: the pit wall, the lane's walls, and nothing between the road and the lane at its entry and exit)
    const at = track.locate(x, y, k.seg ?? null);
    const seg = at.seg, s = at.s;
    let lat = at.lateral;
    let a = Math.abs(lat);
    const side = lat > 0 ? 1 : -1;
    const zone = track.laneSide(lat) ? track.laneZone(s) : null;
    const inLane = zone !== null && a > track.half + KERB + LANE_WALL / 2;
    let lo, hi;
    if (inLane) {  // (between the pit wall and the outer wall; at its ends the outer wall slants back to the road)
        if (zone === "ramp") { lo = 0.0; hi = track.laneEdge(s) - KART_HALF; }
        else { lo = track.laneInner() + KART_HALF; hi = track.laneOuter() - KART_HALF; }
    } else if (zone === "ramp" && track.pits === "lane") { lo = 0.0; hi = track.laneEdge(s) - KART_HALF; }  // (the lane open)
    else if (zone !== null) { lo = 0.0; hi = track.half + KERB - KART_HALF; }  // (the pit wall, or the closed lane's gate)
    else { lo = 0.0; hi = track.barrier(seg, side) - KART_HALF; }
    if (a > hi || a < lo) {  // into a barrier: held at it, the slide stopped, speed scrubbed off
        // (CHANGE 158) how fast it went into the barrier, only as it arrives: over HIT_SPEED, damage on that side
        const was = Math.abs(k.lat);
        const into = a > hi ? (a - was) / dt : (was - a) / dt;
        const clear = a > hi ? was < hi - 0.005 : was > lo + 0.005;
        if (damage && clear && into > HIT_SPEED) {
            const heading = radians(yaw - track.heading(s));
            const front = Math.abs(sin(heading));  // (square to the barrier: nose first)
            hurt(n, (into - HIT_SPEED) * HIT_BARRIER, sideShares(front > 0.7 ? 1.0 : 0.0, a > hi ? side : -side));
        }
        a = a > hi ? hi : lo;
        lat = side * a;
        [x, y] = track.point(s, lat);
        u = 0.0;
        v *= Math.max(0.0, 1.0 - 3.0 * dt);
        charge = 0;
    }
    // dash pads and oil
    if (track.near(track.boosts, s, lat, BOOST_RADIUS)) boost = Math.max(boost, PAD_BOOST);
    if (track.near(track.oil, s, lat, OIL_RADIUS)) slip = OIL_TICKS;
    // (CHANGE 158) mending: a little every tick, quickly in the PIT box at pit speed; (CHANGE 179) or stopped in your
    // own bay in the pit lane, where (CHANGE 178) new tyres go on too
    const pitting = (Math.abs(v) < PIT_SPEED && track.inPit(s, lat)) || (Math.abs(v) < BAY_STOP && inLane && track.inBay(k.id ?? -1, s, lat));
    const mend = pitting ? REPAIR_PIT : REPAIR_TICK;
    if (n.shield) n.shield -= 1;  // (CHANGE 159) a shield wears off
    if (n.bg) n.bg -= 1;  // ...and a bump's grace
    for (const part of DAMAGE_PARTS) if (n[part]) n[part] = Math.max(0, n[part] - mend);
    // (CHANGE 178) the tyres wear with the metres driven, faster sliding
    if (wear > 0.0) {
        const load = 1.0 + (drifting ? 2.0 : 0.0) + (hb ? 3.0 : 0.0) + (slip ? 1.0 : 0.0) + (launch ? 2.0 : 0.0);
        tyre = Math.min(1.0, tyre + wear * Math.abs(k.v) * dt * load);
    }
    if (pitting) tyre = Math.max(0.0, tyre - dt / TYRE_FRESH);
    n.x = x;
    n.y = y;
    n.yaw = yaw;
    n.v = v;
    n.u = u;
    n.charge = charge;
    n.boost = Math.max(0, boost - 1);
    n.slip = Math.max(0, slip - 1);
    n.flags = flags | (k.flags & (FLAG_FINISHED | FLAG_WRONG_WAY));
    n.seg = seg;
    n.s = s;
    n.lat = lat;
    n.steer = steer;  // (what the driver is doing with the wheel: every window turns the kart's front wheels by it)
    n.tyre = tyre;
    return n;
}

// the record's fields as the integers that go on the wire (engine.wire.Schema.ints: round half to even, clamped)
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

// how far apart two states of the same kart are (metres, with a little for speed and heading): under 5 cm the
// prediction ignores it
export function compare(a, b) {
    if (a == null || b == null) return Infinity;
    const dyaw = Math.abs(pyMod(a.yaw - b.yaw + 180.0, 360.0) - 180.0);
    return hypot(a.x - b.x, a.y - b.y) + Math.abs(a.v - b.v) * 0.05 + dyaw * 0.01;
}

// a snapshot's kart record as the state step() wants, with where it is along the track (kart_client.full_state)
export function fullState(e, track) {
    const at = track.locate(e.x, e.y, null);
    return {...e, seg: at.seg, s: at.s, lat: at.lateral};
}

// two karts closer than reach pushed apart (one pair of kart_sim.Race.contacts): changes both; true when they
// touched. (CHANGE 176) The speed they close at passes along the line between them from the one coming on to the
// one in front (transfer of it each), the faster one rubbing off up to slow m/s more
export function bump(a, b, reach = BUMP_DISTANCE, slow = 0.3, damage = false, transfer = BUMP_TRANSFER) {
    const dx = b.x - a.x, dy = b.y - a.y, d = hypot(dx, dy);
    if (d >= reach || d < 1e-6) return false;
    const push = (reach - d) / 2, nx = dx / d, ny = dy / d;
    const ya = radians(a.yaw), yb = radians(b.yaw);
    const ca = cos(ya), sa = sin(ya), cb = cos(yb), sb = sin(yb);
    const ua = a.u || 0, ub = b.u || 0;
    const va = [ca * a.v - sa * ua, sa * a.v + ca * ua];
    const vb = [cb * b.v - sb * ub, sb * b.v + cb * ub];
    const closing = (va[0] - vb[0]) * nx + (va[1] - vb[1]) * ny;
    if (damage && closing > HIT_KART_SPEED) {  // (CHANGE 158) closing fast damages each where it was hit
        const amount = (closing - HIT_KART_SPEED) * HIT_KART;
        for (const [k, y, sx, sy] of [[a, ya, nx, ny], [b, yb, -nx, -ny]]) {
            if (k.bg) continue;  // (CHANGE 159: damaged by a bump in the last second)
            hurt(k, amount, sideShares(cos(y) * sx + sin(y) * sy, -sin(y) * sx + cos(y) * sy));
            k.bg = BUMP_GRACE;
        }
    }
    a.x -= nx * push;
    a.y -= ny * push;
    b.x += nx * push;
    b.y += ny * push;
    if (closing > 0.0) {
        const dv = closing * transfer;
        a.v -= dv * (ca * nx + sa * ny);
        a.u = ua - dv * (-sa * nx + ca * ny);
        b.v += dv * (cb * nx + sb * ny);
        b.u = ub + dv * (-sb * nx + cb * ny);
        const rub = slow * Math.min(1.0, closing);
        if (a.v > b.v) a.v -= rub; else b.v -= rub;
    }
    return true;
}

// another kart carried on one tick as it was going (the prediction can't know its keys)
// (CHANGE 159) turning as its driver is steering: its steer from the wire, k.rate and k.top its design's steering
// rate and top speed when the prediction knows them (kart_sim.coast)
export function coast(k, dt) {
    const steer = k.steer || 0, rate = k.rate || 0;
    if (steer && rate) {
        const v = k.v, top = k.top || 25.0;
        const turn = steer * rate * Math.min(1.0, Math.abs(v) / 6.0) * (1.0 - 0.4 * Math.min(1.0, Math.abs(v) / top));
        k.yaw += v < 0 ? -turn * dt : turn * dt;
    }
    const yr = radians(k.yaw), fx = cos(yr), fy = sin(yr), u = k.u || 0;
    k.x += (fx * k.v - fy * u) * dt;
    k.y += (fy * k.v + fx * u) * dt;
}

// the window's step for its own kart (kart_client.step_fn): step, then round to the wire as the server does.
// world (CHANGE 155): {others, reach, slow, transfer, damage, wear}, the other karts as the last snapshot had them,
// carried on a tick each step and bumped as the server bumps them, so your kart against another isn't put right
// every tick
export function makeStep(track, stats, world = null) {
    return (state, inp, dt) => {
        const n = step(state, inp, dt, track, stats, !!(world && world.damage), world ? world.wear || 0.0 : 0.0);
        if (world) {
            for (const o of world.others) {
                coast(o, dt);
                bump(n, o, world.reach, world.slow, !!world.damage, world.transfer ?? BUMP_TRANSFER);
            }
        }
        return Object.assign(n, quantise(n));
    };
}
