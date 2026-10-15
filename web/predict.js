// Client-side prediction for the browser (engine/predict.py, ported line for line), and the input frame that goes
// up to the server (engine/wire.py's pack_input and quantise_input).
//
// The page applies its own input the moment it is made and sends it numbered; the server applies the same
// numbered inputs in order and echoes the last one it used with each snapshot. When the server's state for that
// input arrives, the Predictor compares it with what it predicted for that very tick, and only when they differ
// does it take the server's state and replay the inputs the server has not had yet. The ErrorSmoother hides a
// correction in the picture (never the physics) and fades it over a few frames; the LeadController runs the
// page's ticks a little fast or slow so the server holds one or two of our inputs, never none and never many.
//
// Nothing here knows what a state or an input is: the game supplies step(state, input, dt) and
// compare(predicted, server) (kart_sim.js's makeStep and compare for Kart Lab).
//
// Sequence numbers are u16 and wrap (a 60 Hz race wraps in 18 minutes), so every comparison goes through
// seqAfter / seqDiff rather than < and -.
//
// The input frame: kind byte 2, then <HHIbbB> (seq, the last snapshot seq seen, client_ms, throttle and steer in
// hundredths, buttons DRIFT=1 USE=2 RESPAWN=4), then the two previous inputs' throttle, steer and buttons (for
// seq - 1 and seq - 2) so one lost or late message leaves no hole in the server's queue: 18 bytes, little-endian.

import {pyRound, hypot, radians} from "./pymath.js";

export const SEQ_MASK = 0xFFFF;
export const KIND_INPUT = 2;
export const INPUT_SIZE = 18;

// a - b as a signed distance on the u16 circle (positive when a came after b)
export function seqDiff(a, b) {
    const d = (a - b) & SEQ_MASK;
    return d >= 0x8000 ? d - 0x10000 : d;
}

// true when a was numbered after b (and is not b), allowing for the wrap
export function seqAfter(a, b) {
    const d = (a - b) & SEQ_MASK;
    return 0 < d && d < 0x8000;
}

// ---------- the input frame (engine/wire.py) ----------
function i8(v) {
    v = pyRound(v * 100);
    return v < -128 ? -128 : v > 127 ? 127 : v;
}

function u8(v) {
    v = Math.trunc(v);  // (Python's int())
    return v < 0 ? 0 : v > 255 ? 255 : v;
}

// [throttle, steer, buttons] as the server will see them: step with these, not what the keys read, so the
// prediction uses the very numbers the server will
export function quantiseInput(throttle, steer, buttons = 0) {
    return [i8(throttle) / 100, i8(steer) / 100, u8(buttons)];
}

// one input frame as an 18-byte ArrayBuffer. previous holds up to two [throttle, steer, buttons], the most recent
// first (the inputs for seq - 1 and seq - 2); missing ones go as zeros
export function packInput(seq, snapSeq, clientMs, throttle, steer, buttons, previous = []) {
    const prev = previous.slice(0, 2);
    while (prev.length < 2) prev.push([0, 0, 0]);
    const buf = new ArrayBuffer(INPUT_SIZE), dv = new DataView(buf);
    dv.setUint8(0, KIND_INPUT);
    dv.setUint16(1, seq & 0xFFFF, true);
    dv.setUint16(3, snapSeq & 0xFFFF, true);
    dv.setUint32(5, Math.trunc(clientMs) >>> 0, true);
    let off = 9;
    for (const [t, s, b] of [[throttle, steer, buttons], prev[0], prev[1]]) {
        dv.setInt8(off, i8(t));
        dv.setInt8(off + 1, i8(s));
        dv.setUint8(off + 2, u8(b));
        off += 3;
    }
    return buf;
}

// ---------- the prediction ----------
// the page's numbered inputs, oldest first, until the server acknowledges them. keep: how many of the newest
// trim() always leaves (the two that ride along with each input for redundancy, and the newest); maxLen stops
// the log growing while nothing is acknowledged
export class InputLog {
    constructor(firstSeq = 0, keep = 3, maxLen = 1024) {
        this.entries = [];  // [seq, input, localT]
        this.nextSeq = firstSeq & SEQ_MASK;
        this.keep = keep;
        this.maxLen = maxLen;
    }

    // number and keep an input; returns its seq
    add(input, localT = 0.0) {
        const seq = this.nextSeq;
        this.nextSeq = (seq + 1) & SEQ_MASK;
        this.entries.push([seq, input, localT]);
        if (this.entries.length > this.maxLen) this.entries.shift();  // (a deque's maxlen)
        return seq;
    }

    // [[seq, input]] for every input numbered after ackSeq, in order: what a correction replays
    since(ackSeq) {
        return this.entries.filter(([s]) => seqAfter(s, ackSeq)).map(([s, i]) => [s, i]);
    }

    // the n inputs logged just before the newest one, most recent first (fewer when the log is that short)
    previous(n = 2) {
        const end = this.entries.length - 1;
        return this.entries.slice(Math.max(0, end - n), Math.max(0, end)).reverse().map(e => e[1]);
    }

    // forget inputs the server has applied (at or before ackSeq), keeping the newest few for redundancy
    trim(ackSeq) {
        while (this.entries.length > this.keep && !seqAfter(this.entries[0][0], ackSeq)) this.entries.shift();
    }

    newest() {
        return this.entries.length ? this.entries[this.entries.length - 1][0] : null;
    }

    get length() {
        return this.entries.length;
    }
}

// advances the local state with each input and reconciles it with the server's acknowledged state. A ring of
// the predicted states by seq lets correct() compare the server's state with what was predicted for exactly
// that tick; after a correction that moved the state, movedFrom holds the prediction it replaced (the caller
// works out the visual error from it and hands that to an ErrorSmoother)
export class Predictor {
    constructor(step, state, ignore = 0.05, log = null, ring = 256) {
        this.step = step;
        this.state = state;
        this.ignore = ignore;
        this.log = log !== null ? log : new InputLog();
        this.ring = ring;
        this.predicted = new Map();  // seq -> the state predicted after that input (insertion = seq order)
        this.corrections = 0;        // how many times the state was replaced (a diagnostic: ought to stay small)
        this.movedFrom = null;
    }

    // log the input, step the state with it and remember the result against its seq; returns the seq
    apply(input, dt, localT = 0.0) {
        const seq = this.log.add(input, localT);
        this.state = this.step(this.state, input, dt);
        this.predicted.set(seq, this.state);
        while (this.predicted.size > this.ring) this.predicted.delete(this.predicted.keys().next().value);
        return seq;
    }

    // reconcile with the server's state after it applied input ackSeq; returns the error compare() found. Below
    // ignore nothing happens; otherwise the state becomes the server's and the inputs after ackSeq are replayed.
    // An ack with no prediction behind it (a reconnect, or one older than the ring) is an unbounded error: a snap
    correct(serverState, ackSeq, dt, compare) {
        const was = this.predicted.get(ackSeq);
        const err = was !== undefined ? compare(was, serverState) : Infinity;
        if (err < this.ignore) {
            this.movedFrom = null;
        } else {
            this.movedFrom = this.state;
            this.state = serverState;
            for (const [seq, input] of this.log.since(ackSeq)) {
                this.state = this.step(this.state, input, dt);
                this.predicted.set(seq, this.state);
            }
            this.corrections += 1;
        }
        // (older than the acknowledged tick is of no further use; the tick itself stays, because the same ack
        // comes again while the server has nothing new of ours, and that must not look like a reconnect)
        for (const seq of [...this.predicted.keys()]) {
            if (!seqAfter(ackSeq, seq)) break;
            this.predicted.delete(seq);
        }
        this.log.trim(ackSeq);
        return err;
    }
}

function blend(loAt, lo, hiAt, hi, x) {
    if (x <= loAt) return lo;
    if (x >= hiAt) return hi;
    return lo + (hi - lo) * (x - loAt) / (hiAt - loAt);
}

// a in (-pi, pi], so a correction across the seam is a small turn, not a full one
function wrapAngle(a) {
    return a - 2 * Math.PI * Math.floor((a + Math.PI) / (2 * Math.PI));
}

// the visual offset that hides a correction: added to the drawn pose, never to the physics state. add() the
// move (old pose minus new pose) and the picture stays where it was; offset(dt) shrinks it each frame (0.95 a
// frame when small, 0.85 when large, blended between; yaw 0.92). Under 5 cm is not worth hiding and over 4 m
// (or 45 degrees) the kart was teleported: both show the truth at once. removeUp drops the vertical part (index
// upAxis: 2, as Panda's z is up). Positions are 3-element arrays; yaw is in radians
export class ErrorSmoother {
    constructor({ignore = 0.05, snap = 4.0, snapYaw = radians(45), decay = 0.9, decaySmall = [0.25, 0.95],
                 decayLarge = [1.0, 0.85], yawDecay = 0.92, ignoreYaw = radians(0.5), removeUp = false,
                 adaptive = true, upAxis = 2} = {}) {
        Object.assign(this, {ignore, snap, snapYaw, decay, decaySmall, decayLarge, adaptive, yawDecay, ignoreYaw,
                             removeUp, upAxis});
        this.dpos = [0.0, 0.0, 0.0];
        this.dyaw = 0.0;
        this.snaps = 0;
    }

    // a correction moved the pose by dpos (old minus new) and dyaw: carry it so the picture does not jump. A new
    // error during a fade adds to what is left of the old one
    add(dpos, dyaw = 0.0) {
        const n = Math.min(this.dpos.length, dpos.length);
        const d = [];
        for (let i = 0; i < n; i++) d.push(this.dpos[i] + dpos[i]);
        if (this.removeUp && d.length > this.upAxis) d[this.upAxis] = 0.0;
        const yaw = wrapAngle(this.dyaw + dyaw);
        if (hypot(...d) > this.snap || Math.abs(yaw) > this.snapYaw) {
            this.dpos = d.map(() => 0.0);
            this.dyaw = 0.0;
            this.snaps += 1;
            return;
        }
        this.dpos = hypot(...d) >= this.ignore ? d : d.map(() => 0.0);
        this.dyaw = Math.abs(yaw) >= this.ignoreYaw ? yaw : 0.0;
    }

    // fade by one frame of dt seconds and return [dpos, dyaw] to add to the drawn pose
    offset(dt) {
        const length = hypot(...this.dpos);
        if (length) {
            let f = this.adaptive ? blend(this.decaySmall[0], this.decaySmall[1], this.decayLarge[0],
                                          this.decayLarge[1], length) : this.decay;
            f **= dt * 60;
            const d = this.dpos.map(a => a * f);
            this.dpos = length * f >= this.ignore ? d : d.map(() => 0.0);
        }
        if (this.dyaw) {
            const yaw = this.dyaw * this.yawDecay ** (dt * 60);
            this.dyaw = Math.abs(yaw) >= this.ignoreYaw ? yaw : 0.0;
        }
        return [this.dpos, this.dyaw];
    }

    clear() {
        this.dpos = this.dpos.map(() => 0.0);
        this.dyaw = 0.0;
    }
}

// keeps the server's input buffer for this page between one and two ticks deep. feed() the depth the server
// echoes each snapshot (Kart Lab: the snapshot's flags >> 4) and stretch the time between ticks by multiplier():
//     acc += frameDt; while (acc >= STEP * lead.multiplier()) { acc -= STEP * lead.multiplier(); tick(); }
// Under 1 the page ticks more often and fills the buffer, over 1 less often and drains it (0.9 to 1.1); inside
// the band it is exactly 1, so a healthy connection is never nudged
export class LeadController {
    constructor(low = 1.0, high = 2.0, gain = 0.1, limit = 0.1, alpha = 0.2) {
        Object.assign(this, {low, high, gain, limit, alpha});
        this.depth = null;  // the smoothed depth (null until the first reading)
    }

    // take the depth the server echoed; returns the multiplier for the next tick
    feed(bufferDepth) {
        if (this.depth === null) this.depth = Number(bufferDepth);
        else this.depth += this.alpha * (bufferDepth - this.depth);
        return this.multiplier();
    }

    multiplier() {
        const d = this.depth;
        if (d === null || (this.low <= d && d <= this.high)) return 1.0;
        const m = d < this.low ? 1.0 - this.gain * (this.low - d) : 1.0 + this.gain * (d - this.high);
        return Math.min(1.0 + this.limit, Math.max(1.0 - this.limit, m));
    }

    reset() {
        this.depth = null;
    }
}
