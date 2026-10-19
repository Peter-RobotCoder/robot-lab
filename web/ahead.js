// Robot Lab's robots drawn where they are now, not where they were (CHANGE 166): engine/ahead.py, line for line
// (its docstring says why and how). Every robot carried on from its newest snapshot to the moment a key pressed now
// takes effect on the server; yours by the drive model from the keys sent since, the others at the speed and turn
// rate their snapshots show; a guess that was off drawn away over a few frames; one in the air, on its side or
// knocked out drawn as blended. Times are seconds.

export const STEP = 1 / 60;
export const HORIZON = 0.25;
export const DRIVE = {acc: 0.5, brake: 1.3, stop: 6.0, coast: 2.0, yaw_k: 8.0};
export const EASE = 0.2, SNAP = 2.0, BIG = 0.3, FADE = 0.8, FADE_BIG = 0.7, APART = 3.0;

export function yawOf([w, x, y, z]) { return Math.atan2(1 - 2 * (x * x + z * z), 2 * (x * y - w * z)); }
export function upZ([, x, y]) { return 1 - 2 * (x * x + y * y); }

function qmul([aw, ax, ay, az], [bw, bx, by, bz]) {
    return [aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw];
}

export function turned(q, a) { return qmul([Math.cos(a / 2), 0, 0, Math.sin(a / 2)], q); }

export function wrap(a) {
    const t = (a + Math.PI) % (2 * Math.PI);
    return (t < 0 ? t + 2 * Math.PI : t) - Math.PI;
}

export function driveStep([x, y, yaw, v, w], throttle, steer, [fwd, rev, acc, turn], dt, P = DRIVE) {
    if ((throttle > 0 && v > fwd) || (throttle < 0 && -v > rev)) throttle = 0;
    if (throttle) v += acc * P.acc * throttle * (throttle * v < 0 ? P.brake : 1.0) * dt;
    else v -= Math.sign(v) * Math.min(Math.abs(v), (steer === 0 ? P.stop : P.coast) * dt);
    w += (steer * turn - w) * Math.min(1.0, P.yaw_k * dt);
    yaw += w * dt;
    return [x + Math.cos(yaw) * v * dt, y + Math.sin(yaw) * v * dt, yaw, v, w];
}

export class RobotsAhead {
    constructor() {
        this.tracks = new Map(); this.prev = new Map(); this.fresh = new Set();
        this.off = new Map(); this.weight = new Map();
        this.inputs = [];  // [local time sent (s), throttle, steer]: your own keys
    }

    control(t, throttle, steer) {
        this.inputs.push([t, Number(throttle) || 0, Number(steer) || 0]);
        if (this.inputs.length > 120) this.inputs.shift();
    }

    snapshot(serverT, robots) {
        const seen = new Set();
        for (const r of robots) {
            seen.add(r.id);
            const yaw = yawOf(r.quat), old = this.tracks.get(r.id);
            let w = 0;
            if (old) {
                const gap = serverT - old.t;
                if (gap <= 0) continue;
                w = gap <= 0.2 ? wrap(yaw - old.yaw) / gap : old.w;
            }
            this.prev.set(r.id, old || null);
            this.tracks.set(r.id, {t: serverT, x: r.pos[0], y: r.pos[1], yaw, v: r.speed || 0, w, up: upZ(r.quat)});
            this.fresh.add(r.id);
        }
        for (const id of [...this.tracks.keys()]) {
            if (seen.has(id)) continue;
            for (const m of [this.tracks, this.prev, this.off, this.weight]) m.delete(id);
            this.fresh.delete(id);
        }
    }

    keyAt(t) {
        let got = [0, 0];
        for (const [t0, th, st] of this.inputs) {
            if (t0 > t) break;
            got = [th, st];
        }
        return got;
    }

    target(tr, until, own, stats, localNow) {
        const h = Math.max(0, Math.min(HORIZON, until - tr.t));
        let s = [tr.x, tr.y, tr.yaw, tr.v, tr.w];
        const n = Math.floor(h / STEP), rest = h - n * STEP;
        for (let k = 0; k < n + (rest > 1e-9 ? 1 : 0); k++) {
            const dt = k < n ? STEP : rest;
            if (own && stats) {
                const [th, st] = this.keyAt(localNow - (until - (tr.t + k * STEP)));
                s = driveStep(s, th, st, stats, dt);
            } else {
                const yaw = s[2] + s[4] * dt;
                s = [s[0] + Math.cos(yaw) * s[3] * dt, s[1] + Math.sin(yaw) * s[3] * dt, yaw, s[3], s[4]];
            }
        }
        return [s[0], s[1], s[2]];
    }

    // robots: as blended; localNow and serverSeen in seconds; stats: Map id -> [forward_max, reverse_max, accel, turn_rate]
    adjust(robots, localNow, serverSeen, rtt, myId = null, stats = null, dt = 1 / 60) {
        if (serverSeen === null || serverSeen === undefined) return robots;
        const until = serverSeen + Math.max(0, Math.min(0.3, rtt));
        return robots.map(r => {
            const tr = this.tracks.get(r.id), q = r.quat;
            const ok = !!tr && !r.ko && upZ(q) > 0.9 && tr.up > 0.9 &&  // (a respawn: as blended until the blend gets there)
                Math.hypot(tr.x - r.pos[0], tr.y - r.pos[1]) < APART;
            const wt = Math.max(0, Math.min(1, (this.weight.get(r.id) || 0) + (ok ? dt : -dt) / EASE));
            this.weight.set(r.id, wt);
            if (!tr || wt <= 0) { this.off.delete(r.id); return r; }
            const own = r.id === myId, st = own && stats ? stats.get(r.id) || null : null;
            const [x, y, yaw] = this.target(tr, until, own, st, localNow);
            let off = this.off.get(r.id) || [0, 0, 0];
            if (this.fresh.has(r.id)) {
                this.fresh.delete(r.id);
                const old = this.prev.get(r.id);
                if (old && this.off.has(r.id)) {
                    const [ox, oy, oyaw] = this.target(old, until, own, st, localNow);
                    off = [off[0] + ox - x, off[1] + oy - y, wrap(off[2] + oyaw - yaw)];
                }
            }
            const size = Math.hypot(off[0], off[1]);
            if (size > SNAP) off = [0, 0, 0];
            const k = (size > BIG ? FADE_BIG : FADE) ** (dt * 60);
            off = [off[0] * k, off[1] * k, off[2] * k];
            this.off.set(r.id, off);
            const [ix, iy, iz] = r.pos, iyaw = yawOf(q);
            const fx = ix + wt * (x + off[0] - ix), fy = iy + wt * (y + off[1] - iy);
            const dyaw = wt * wrap(yaw + off[2] - iyaw);
            const n = {...r, pos: [fx, fy, iz], quat: turned(q, dyaw)};
            if (r.wpos && r.wquat) {  // (its weapon turns about it and moves with it)
                const c = Math.cos(dyaw), s = Math.sin(dyaw), wx = r.wpos[0] - ix, wy = r.wpos[1] - iy;
                n.wpos = [fx + c * wx - s * wy, fy + s * wx + c * wy, r.wpos[2]];
                n.wquat = turned(r.wquat, dyaw);
            }
            return n;
        });
    }
}

// ---------- Fight Lab: your own fighter's footwork (CHANGE 167): engine/ahead.py's FighterAhead, line for line ----------
export const FREE = new Set(["idle", "walk_f", "walk_b", "side_l", "side_r", "block", "low_block", "crouch"]);
export const HOLDS = new Set(["block", "low_block", "crouch"]);
export const GRIP = 18.0, BACK = 0.7, APART_FIGHTER = 1.0;

export class FighterAhead {
    constructor() {
        this.track = this.prev = null;
        this.fresh = false;
        this.off = [0, 0]; this.weight = 0;
        this.inputs = [];  // [local time sent (s), forward, side, hold]
    }

    control(t, fwd, side, hold = "") {
        this.inputs.push([t, Number(fwd) || 0, Number(side) || 0, hold || ""]);
        if (this.inputs.length > 120) this.inputs.shift();
    }

    snapshot(serverT, fighters, myId) {
        const me = fighters.find(f => f.id === myId);
        if (!me) { this.track = this.prev = null; return; }
        const foe = fighters.find(f => f.id !== myId), old = this.track;
        if (old && serverT <= old.t) return;
        let vx = 0, vy = 0;
        if (old && serverT - old.t <= 0.2) { vx = (me.pos[0] - old.x) / (serverT - old.t); vy = (me.pos[1] - old.y) / (serverT - old.t); }
        let fx = 1, fy = 0;
        if (foe) {
            const dx = foe.pos[0] - me.pos[0], dy = foe.pos[1] - me.pos[1], d = Math.hypot(dx, dy);
            if (d > 0.05) { fx = dx / d; fy = dy / d; }
        }
        this.prev = old;
        this.track = {t: serverT, x: me.pos[0], y: me.pos[1], vx, vy, fx, fy, free: FREE.has(me.a) && me.pos[2] < 0.01};
        this.fresh = true;
    }

    keyAt(t) {
        let got = [0, 0, ""];
        for (const [t0, f, s, h] of this.inputs) {
            if (t0 > t) break;
            got = [f, s, h];
        }
        return got;
    }

    target(tr, until, [walk, sidestep], localNow) {
        const h = Math.max(0, Math.min(HORIZON, until - tr.t));
        let x = tr.x, y = tr.y, vx = tr.vx, vy = tr.vy;
        const n = Math.floor(h / STEP), rest = h - n * STEP;
        for (let k = 0; k < n + (rest > 1e-9 ? 1 : 0); k++) {
            const dt = k < n ? STEP : rest;
            const [fwd, side, hold] = this.keyAt(localNow - (until - (tr.t + k * STEP)));
            let tx = 0, ty = 0;
            if (!HOLDS.has(hold) && (Math.abs(fwd) > 0.1 || Math.abs(side) > 0.1)) {
                const back = fwd < 0 ? BACK : 1.0, px = -tr.fy, py = tr.fx;
                tx = tr.fx * fwd * walk * back + px * side * sidestep;
                ty = tr.fy * fwd * walk * back + py * side * sidestep;
            }
            const a = Math.min(1.0, GRIP * dt);
            vx += (tx - vx) * a;
            vy += (ty - vy) * a;
            x += vx * dt;
            y += vy * dt;
        }
        return [x, y];
    }

    adjust(fighters, localNow, serverSeen, rtt, myId, stats, dt = 1 / 60) {
        const tr = this.track, me = fighters.find(f => f.id === myId);
        if (serverSeen === null || serverSeen === undefined || !me || !tr || !stats) return fighters;
        const ok = tr.free && FREE.has(me.a) && me.pos[2] < 0.01 && Math.hypot(tr.x - me.pos[0], tr.y - me.pos[1]) < APART_FIGHTER;
        this.weight = Math.max(0, Math.min(1, this.weight + (ok ? dt : -dt) / EASE));
        if (this.weight <= 0) { this.off = [0, 0]; return fighters; }
        const until = serverSeen + Math.max(0, Math.min(0.3, rtt));
        const [x, y] = this.target(tr, until, stats, localNow);
        let off = this.off;
        if (this.fresh) {
            this.fresh = false;
            if (this.prev) {
                const [ox, oy] = this.target(this.prev, until, stats, localNow);
                off = [off[0] + ox - x, off[1] + oy - y];
            }
        }
        const size = Math.hypot(off[0], off[1]);
        if (size > SNAP) off = [0, 0];
        const k = (size > BIG ? FADE_BIG : FADE) ** (dt * 60);
        this.off = off = [off[0] * k, off[1] * k];
        const wt = this.weight, [ix, iy, iz] = me.pos;
        const drawn = {...me, pos: [ix + wt * (x + off[0] - ix), iy + wt * (y + off[1] - iy), iz]};
        return fighters.map(f => f === me ? drawn : f);
    }
}
