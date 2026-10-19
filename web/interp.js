// Smooth movement between the class server's snapshots: engine/interp.py's ServerClock and Snapshots, line for
// line (CHANGE 175; engine/interp_test.py runs both on the same arrivals and compares what they draw).
//
// The page draws the game a little in the past (the render delay), blending between the snapshot before and the
// one after that moment, so a Wi-Fi stall shorter than the delay is invisible. The delay follows the network: two
// snapshots plus how late the snapshots have been arriving (the 97th percentile over the last three seconds,
// against the quickest), between 67 and 250 ms; it only moves when the target is more than half a snapshot away
// (a dead band, so it doesn't hunt), up at once and down at 20 ms a second. The moment drawn is a clock of its own
// that eases (75% speed when ahead, 110% when behind) and never jumps back. Past the newest snapshot the picture
// carries on for up to 100 ms (pair() then gives f over 1, with extrapolating true), then holds.
//
//   const snaps = new Snapshots();     // interval 1/30 s
//   snaps.push(snap, now);             // every snapshot (snap.sm: the server's ms), now = performance.now()
//   const p = snaps.pair(now);         // every frame: {a, b, f, extrapolating} or null; b null before the first pair
//   snaps.serverTime(now)              // the server's clock now (ms), or null
//   snaps.renderTime(now)              // the server time being drawn (ms), or null
//
// Times inside are seconds, as the Python's; the page's are milliseconds, converted at the edge.

export class ServerClock {
    constructor(window = 4.0, slew = 0.02) {
        this.window = window;
        this.slew = slew;
        this.samples = [];  // [our time, server time - our time]
        this.offset = null;
        this.lastLocal = null;
    }

    note(serverT, localT) {
        const off = serverT - localT;
        this.samples.push([localT, off]);
        while (this.samples.length && localT - this.samples[0][0] > this.window) this.samples.shift();
        let best = -Infinity;
        for (const [, o] of this.samples) if (o > best) best = o;
        if (this.offset === null || best > this.offset) {
            this.offset = best;
        } else {
            const dt = localT - (this.lastLocal !== null ? this.lastLocal : localT);
            this.offset = Math.max(best, this.offset - this.slew * Math.max(0, dt));
        }
        this.lastLocal = localT;
    }

    serverTime(localT) {
        return this.offset === null ? null : localT + this.offset;
    }
}

export class Snapshots {
    constructor({interval = 1 / 30, delayIntervals = 2.0, minDelay = 0.05, maxDelay = 0.25, maxExtrapolate = 0.1,
                 keep = 1.5, lateWindow = 3.0, latePct = 0.97, fall = 0.02} = {}) {
        this.interval = interval;
        this.baseDelay = Math.max(minDelay, interval * delayIntervals);
        this.delay = this.baseDelay;
        this.minDelay = minDelay;
        this.maxDelay = maxDelay;
        this.maxExtrapolate = maxExtrapolate;
        this.keep = keep;
        this.lateWindow = lateWindow;
        this.latePct = latePct;
        this.fall = fall;
        this.late = [];        // [our time, how late that snapshot was against the quickest]
        this.target = this.baseDelay;
        this.clock = new ServerClock();
        this.snaps = [];       // [server time, snapshot]
        this.lastRx = null;
        this.stalls = 0;       // gaps between arrivals of more than 4.5 intervals (150 ms)
        this.worstGap = 0;
        this.underruns = 0;    // times the picture wanted a snapshot newer than any that had arrived
        this.inUnderrun = false;
        this.lastSampleT = null;
        this.tRender = null;   // the moment (server time) being drawn: a clock of its own, never put back
    }

    get latest() { return this.snaps.length ? this.snaps[this.snaps.length - 1][1] : null; }

    // a snapshot with the server's stamp (sm, ms) at our time nowMs (performance.now())
    push(snap, nowMs) {
        const localT = nowMs / 1000;
        if (this.lastRx !== null) {
            const gap = localT - this.lastRx;
            this.worstGap = Math.max(this.worstGap, gap);
            if (gap > 4.5 * this.interval) this.stalls++;
        }
        this.lastRx = localT;
        if (snap.sm === undefined || snap.sm === null) return;
        const serverT = snap.sm / 1000;
        this.clock.note(serverT, localT);
        this.late.push([localT, Math.max(0, this.clock.serverTime(localT) - serverT)]);
        while (this.late.length && localT - this.late[0][0] > this.lateWindow) this.late.shift();
        const lates = this.late.map(x => x[1]).sort((p, q) => p - q);
        const pct = lates.length ? lates[Math.min(lates.length - 1, Math.floor(this.latePct * lates.length))] : 0;
        this.target = Math.max(this.baseDelay, Math.min(this.maxDelay, this.baseDelay + pct));
        if (this.target > this.delay + this.interval / 2) this.delay = this.target;
        const last = this.snaps.length ? this.snaps[this.snaps.length - 1][0] : null;
        if (last !== null && serverT <= last) return;  // (out of order or repeated: keep what we have)
        this.inUnderrun = false;
        this.snaps.push([serverT, snap]);
        while (this.snaps.length > 2 && serverT - this.snaps[0][0] > this.keep) this.snaps.shift();
    }

    serverTime(nowMs) {
        const t = this.clock.serverTime(nowMs / 1000);
        return t === null ? null : t * 1000;
    }

    renderTime(nowMs) {
        if (this.tRender === null) return null;
        return this.tRender * 1000;
    }

    // the two snapshots either side of the moment to draw and how far between them: {a, b, f, extrapolating};
    // b null when there is only one, f over 1 (up to 2.5) while carrying on past the newest
    pair(nowMs) {
        const snaps = this.snaps;
        if (!snaps.length) return null;
        const localT = nowMs / 1000;
        const dt = this.lastSampleT === null ? 0 : Math.max(0, localT - this.lastSampleT);
        this.lastSampleT = localT;
        if (this.delay > this.target + this.interval / 2) this.delay = Math.max(this.target, this.delay - this.fall * dt);
        const want = this.clock.serverTime(localT) - this.delay;
        if (this.tRender === null || Math.abs(want - this.tRender) > 0.5) {
            this.tRender = want;
        } else {
            const gap = want - this.tRender;
            const rate = Math.abs(gap) < 0.002 ? 1.0 : (gap < 0 ? 0.75 : 1.1);
            this.tRender += dt * rate;
            if ((gap < 0 && this.tRender < want) || (gap > 0 && this.tRender > want)) this.tRender = want;
        }
        const t = this.tRender;
        const newest = snaps[snaps.length - 1];
        if (t >= newest[0]) {
            if (!this.inUnderrun) {
                this.inUnderrun = true;
                this.underruns++;
                this.delay = Math.min(this.maxDelay, this.delay + this.interval);
            }
            let over = t - newest[0];
            if (over > this.maxExtrapolate) {
                this.tRender = newest[0] + this.maxExtrapolate;
                over = this.maxExtrapolate;
            }
            if (snaps.length >= 2 && over > 0) {
                const [ta, a] = snaps[snaps.length - 2], [tb, b] = newest;
                const alpha = 1 + over / Math.max(1e-6, tb - ta);
                return {a, b, f: Math.min(alpha, 2.5), extrapolating: true};
            }
            return {a: newest[1], b: null, f: 0, extrapolating: false};
        }
        if (t <= snaps[0][0]) return {a: snaps[0][1], b: null, f: 0, extrapolating: false};
        for (let i = snaps.length - 1; i > 0; i--) {
            const [ta, a] = snaps[i - 1], [tb, b] = snaps[i];
            if (ta <= t && t <= tb) return {a, b, f: (t - ta) / Math.max(1e-6, tb - ta), extrapolating: false};
        }
        return {a: newest[1], b: null, f: 0, extrapolating: false};
    }

    report() {
        return {delay_ms: Math.round(this.delay * 1000), stalls: this.stalls, target_ms: Math.round(this.target * 1000),
                worst_gap_ms: Math.round(this.worstGap * 1000), underruns: this.underruns};
    }
}
