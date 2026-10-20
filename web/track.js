// A race track as data (kart/kart_track.py, ported line for line): a smooth closed centre line through a few
// points, a width, dash pads and oil placed by distance along (s) and across (lateral, positive to the left).
// The browser asks it the same questions the window does: where is s, where on the track is (x, y), how high.
// Its numbers are Python's to the last bit (math.hypot, % and degrees done as Python does them: pymath.js), because
// the browser's prediction (kart_sim.js) steps a kart on it and must land where the server's step does.
// (CHANGE 177) Beside the road a kerb KERB wide a kart may drive over, then the barrier, pushed out by a gravel trap
// on the outside of the sharp bends (gravelWidths). (CHANGE 179) A pit lane beside the start straight, with a bay
// for each kart (its id's), open (setPits("lane")) or walled off ("box": the PIT box on the road mends instead).

import {hypot, pyMod, degrees, atan2} from "./pymath.js";  // (atan2: CHANGE 162)

export const GATES = 8;

// the same tracks the server has, for a page that opens before any server has spoken
export const TRACKS = {
    club: {
        name: "Club Circuit", width: 12.0, laps: 3,
        points: [[0, 0, 0], [45, 0, 0], [80, 6, 0.8], [98, 32, 2.4], [92, 62, 3.0], [66, 82, 1.6], [34, 86, 0.4],
                 [6, 74, 0], [-24, 66, -0.6], [-42, 42, -0.4], [-36, 14, 0], [-18, 2, 0]],
        boosts: [[120.0, 0.0], [235.0, 2.5], [300.0, -2.5]],
        oil: [[170.0, -2.0], [268.0, 1.5]],
        pit: [12.0, 30.0, -1],  // (CHANGE 158) the PIT box: from s to s along one side (-1 right, 1 left)
        boxes: [90.0, 205.0],  // (CHANGE 159) where a row of item boxes crosses the road (s)
        pit_lane: [-22.0, 58.0, -1],  // (CHANGE 179) the pit lane: from s to s (s before the line negative), its side
    },
    oval: {
        name: "Test Oval", width: 14.0, laps: 2,
        points: [[0, 0, 0], [40, 0, 0], [70, 10, 0], [80, 35, 0], [70, 60, 0], [40, 70, 0], [0, 70, 0],
                 [-30, 60, 0], [-40, 35, 0], [-30, 10, 0]],
        boosts: [[60.0, 0.0]], oil: [], pit: [10.0, 28.0, -1], boxes: [110.0, 235.0], pit_lane: [-30.0, 46.0, -1],
    },
    straight: {
        name: "Straight Road", width: 12.0, laps: 1,
        points: [[0, 0, 0], [60, 0, 0], [120, 0, 0], [140, 10, 0], [120, 20, 0], [60, 20, 0], [0, 20, 0], [-20, 10, 0]],
        boosts: [], oil: [], pit: [14.0, 32.0, -1], boxes: [80.0, 250.0], pit_lane: [8.0, 104.0, -1],
    },
    // (CHANGE 180) a circuit the shape of Silverstone's Grand Prix loop at one sixth of its size (kart_track.py)
    airfield: {
        name: "Airfield GP", width: 12.0, laps: 2,
        points: [[0.0, 0.0, 0], [66.5, -0.5, 0], [91.4, -31.4, 0], [130.2, -43.2, 0], [120.6, -64.6, 0],
                 [127.2, -67.6, 0], [142.0, -62.2, 0], [151.5, -54.4, 0], [160.7, 54.3, 0], [157.8, 62.0, 0],
                 [151.8, 66.0, 0], [135.5, 58.2, 0], [128.2, 58.9, 0], [124.2, 64.9, 0], [126.5, 72.7, 0],
                 [155.1, 80.2, 0], [174.0, 78.1, 0], [184.2, 71.0, 0], [220.6, 32.0, 0], [230.0, 21.3, 0],
                 [233.2, 13.7, 0], [233.6, 4.6, 0], [230.0, -1.9, 0], [211.5, -24.4, 0], [180.2, -51.8, 0],
                 [170.8, -68.4, 0], [147.2, -78.5, 0], [138.6, -96.1, 0], [130.9, -100.5, 0],
                 [105.3, -94.2, 0], [4.1, -110.1, 0], [-20.9, -111.6, 0], [-29.4, -108.9, 0],
                 [-34.8, -102.6, 0], [-35.6, -94.4, 0], [-25.7, -70.7, 0], [-18.3, -33.9, 0],
                 [-29.7, -27.1, 0], [-29.6, -17.5, 0], [-25.6, -8.3, 0], [-19.0, -0.9, 0]],
        boosts: [[40.0, 0.0], [300.0, 0.0], [520.0, 0.0], [740.0, 0.0]],
        oil: [[205.0, -2.0], [470.0, 2.0], [690.0, -1.5]],
        pit: [10.0, 28.0, -1],
        boxes: [130.0, 420.0, 640.0, 860.0],
        pit_lane: [-16.0, 60.0, -1],
    },
};

export const BOOST_RADIUS = 2.6;
export const OIL_RADIUS = 2.2;
export const PIT_WIDTH = 4.0, PIT_KERB = 0.6;  // (CHANGE 158) the PIT box's width in from the barrier; its paint short of the kerb
// (CHANGE 177) beside the road, in metres out from its edge (kart_track.py)
export const KERB = 1.2, GRAVEL_MAX = 4.0, GRAVEL_LEAST = 0.25;
// (CHANGE 179) the pit lane
export const LANE_WALL = 0.5, LANE_WIDTH = 7.0, LANE_RAMP = 12.0, LANE_BAY = 5.5, LANE_BAY_DEPTH = 3.5, LANE_BAYS = 8;
export const PITS = ["box", "lane"];

export function smooth(t) {  // (kart_scenery's: 0 to 1, eased)
    t = t < 0.0 ? 0.0 : t > 1.0 ? 1.0 : t;
    return t * t * (3 - 2 * t);
}

function dist2d(a, b) {  // (math.dist)
    return hypot(a[0] - b[0], a[1] - b[1]);
}

export function catmullRom(points, step = 1.2) {
    const n = points.length, out = [];
    for (let i = 0; i < n; i++) {
        const p0 = points[(i - 1 + n) % n], p1 = points[i], p2 = points[(i + 1) % n], p3 = points[(i + 2) % n];
        const seg = dist2d(p1, p2);
        const count = Math.max(2, Math.floor(seg / step));
        for (let j = 0; j < count; j++) {
            const t = j / count, t2 = t * t, t3 = t2 * t;
            const p = [0, 0, 0];
            for (let c = 0; c < 3; c++) {
                p[c] = 0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                              + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3);
            }
            out.push(p);
        }
    }
    return out;
}

export class Track {
    constructor(data) {
        this.name = data.name;
        this.width = Number(data.width);
        this.laps = Number(data.laps || 3);
        this.half = this.width / 2;
        this.pts = catmullRom(data.points);
        const n = this.n = this.pts.length;
        this.segLen = [];
        this.tan = [];
        this.s = [];
        let total = 0;
        for (let i = 0; i < n; i++) {
            const a = this.pts[i], b = this.pts[(i + 1) % n];
            const dx = b[0] - a[0], dy = b[1] - a[1];
            const length = hypot(dx, dy) || 1e-6;
            this.segLen.push(length);
            this.tan.push([dx / length, dy / length]);
            this.s.push(total);
            total += length;
        }
        this.length = total;
        this.gateS = [];
        for (let g = 0; g < GATES; g++) this.gateS.push(g * total / GATES);
        this.boosts = (data.boosts || []).map(([s, lat]) => [Number(s), Number(lat)]);
        this.oil = (data.oil || []).map(([s, lat]) => [Number(s), Number(lat)]);
        this.boxRows = (data.boxes || []).map(Number);  // (CHANGE 159) the item boxes' rows
        let p = data.pit;  // (CHANGE 158) the PIT box: [from s, to s, side], or null
        this.pitBox = Array.isArray(p) ? [Number(p[0]), Number(p[1]), p[2] > 0 ? 1 : -1] : null;
        p = data.pit_lane;  // (CHANGE 179) the pit lane: [from s, to s, side], or null
        this.lane = Array.isArray(p) ? [Number(p[0]), Number(p[1]), p[2] > 0 ? 1 : -1] : null;
        this.pits = "box";
        this.pit = this.pitBox;  // (the PIT box in use: null with the pit lane open)
        this.gravel = {1: this.gravelWidths(1), "-1": this.gravelWidths(-1)};  // (CHANGE 177) per segment, each side
    }

    wrap(s) {  // (Python's s % length)
        return pyMod(s, this.length);
    }

    segmentAt(s) {
        s = this.wrap(s);
        let lo = 0, hi = this.s.length;  // bisect_right
        while (lo < hi) {
            const mid = (lo + hi) >> 1;
            if (this.s[mid] <= s) lo = mid + 1; else hi = mid;
        }
        return Math.max(0, lo - 1);
    }

    point(s, lateral = 0) {
        s = this.wrap(s);
        const i = this.segmentAt(s);
        const t = (s - this.s[i]) / this.segLen[i];
        const a = this.pts[i], b = this.pts[(i + 1) % this.n];
        const [tx, ty] = this.tan[i];
        return [a[0] + (b[0] - a[0]) * t - ty * lateral, a[1] + (b[1] - a[1]) * t + tx * lateral,
                a[2] + (b[2] - a[2]) * t];
    }

    heading(s) {
        const [tx, ty] = this.tan[this.segmentAt(s)];
        return degrees(atan2(ty, tx));
    }

    height(s) {
        return this.point(s)[2];
    }

    curvature(s, ahead = 15.0) {  // degrees the track turns between s and s + ahead (positive: left), as Python's
        const h0 = this.heading(s), h1 = this.heading(s + ahead);
        return pyMod(h1 - h0 + 180, 360) - 180;
    }

    locate(x, y, hint = null) {
        const n = this.n;
        let candidates;
        if (hint === null || hint === undefined) {
            candidates = Array.from({length: n}, (_, i) => i);
        } else {
            candidates = [];
            for (let k = -10; k <= 10; k++) candidates.push(((hint + k) % n + n) % n);
        }
        let best = null;
        for (const i of candidates) {
            const a = this.pts[i];
            const [tx, ty] = this.tan[i];
            const px = x - a[0], py = y - a[1];
            const t = Math.max(0, Math.min(this.segLen[i], px * tx + py * ty));
            const cx = px - tx * t, cy = py - ty * t;
            const d2 = cx * cx + cy * cy;
            if (best === null || d2 < best[0]) best = [d2, i, t, cx, cy];
        }
        const [d2, i, t, cx, cy] = best;
        if (hint !== null && hint !== undefined && d2 > 400) return this.locate(x, y, null);
        const [tx, ty] = this.tan[i];
        return {seg: i, s: this.s[i] + t, lateral: tx * cy - ty * cx, dist: Math.sqrt(d2)};
    }

    // ---------- beside the road (CHANGE 177, kart_track.py) ----------
    clear(x, y, r) {  // is (x, y) at least r from every point of the centre line?
        const rr = r * r;
        for (const p of this.pts) {
            const dx = p[0] - x, dy = p[1] - y;
            if (dx * dx + dy * dy < rr) return false;
        }
        return true;
    }

    gravelWidths(side) {  // the gravel trap's reach past the barrier line at each segment on one side
        const n = this.n;
        let want = [];
        for (let i = 0; i < n; i++) want.push(GRAVEL_MAX * smooth((-side * this.curvature(this.s[i] - 9.0, 18.0) - 17.0) / 9.0));
        for (let pass = 0; pass < 2; pass++) {
            const next = [];
            for (let i = 0; i < n; i++) {
                const win = want.slice(Math.max(0, i - 6), i + 7);
                let total = 0;  // (Python's sum: left to right from 0)
                for (const v of win) total += v;
                next.push(total / win.length);
            }
            want = next;
        }
        const out = [];
        for (let i = 0; i < n; i++) {
            let w = want[i];
            while (w > GRAVEL_LEAST) {
                const d = KERB + w + 1.0;
                const [x, y] = this.point(this.s[i], side * (this.half + d));
                if (this.clear(x, y, this.half + d - 0.3)) break;
                w -= 0.5;
            }
            out.push(w > GRAVEL_LEAST ? w : 0.0);
        }
        return out;
    }

    gravelAt(seg, side) {
        return this.gravel[side > 0 ? 1 : "-1"][seg];
    }

    barrier(seg, side) {  // how far from the middle the barrier's face is beside segment seg on that side
        return this.half + KERB + this.gravelAt(seg, side);
    }

    // ---------- the pit lane (CHANGE 179) ----------
    setPits(mode) {
        this.pits = PITS.includes(mode) ? mode : "box";
        this.pit = this.pits === "box" ? this.pitBox : null;
    }

    laneZone(s) {  // null (no lane here), "ramp" (the lane's entry or exit, its end wall on a slant) or "wall" (the pit wall)
        if (this.lane === null) return null;
        const [s0, s1] = this.lane;
        const ds = pyMod(s - s0, this.length);
        if (ds > s1 - s0) return null;
        return ds < LANE_RAMP || ds > s1 - s0 - LANE_RAMP ? "ramp" : "wall";
    }

    laneEdge(s) {  // the lane's outer wall at s: slanting out over the entry and back in over the exit (kart_track.lane_edge)
        const [s0, s1] = this.lane;
        const ds = pyMod(s - s0, this.length);
        const span = s1 - s0, inner = this.half + KERB, outer = this.laneOuter();
        if (ds < LANE_RAMP) return inner + (outer - inner) * (ds / LANE_RAMP);
        if (ds > span - LANE_RAMP) return inner + (outer - inner) * ((span - ds) / LANE_RAMP);
        return outer;
    }

    laneSide(lateral) {  // the lane's side if this lateral is on it, else 0
        return this.lane !== null && lateral * this.lane[2] > 0 ? this.lane[2] : 0;
    }

    laneInner() { return this.half + KERB + LANE_WALL; }

    laneOuter() { return this.half + KERB + LANE_WALL + LANE_WIDTH; }

    bay(kid) {  // kart kid's pit bay: [s0, s1, lateral in, lateral out] (laterals positive, the lane's side), or null
        if (this.lane === null || !(kid >= 0 && kid < LANE_BAYS)) return null;
        const s0 = this.lane[0] + LANE_RAMP + 2.0 + kid * LANE_BAY;
        return [s0, s0 + LANE_BAY - 0.5, this.laneOuter() - LANE_BAY_DEPTH, this.laneOuter()];
    }

    inBay(kid, s, lateral) {
        const b = this.bay(kid);
        if (b === null) return false;
        const [s0, s1, lo, hi] = b;
        const ds = pyMod(s - s0, this.length);
        return ds <= s1 - s0 && lo <= lateral * this.lane[2] && lateral * this.lane[2] <= hi;
    }

    laneMarks() {  // the bays' white outlines as quads of four [s, lateral] corners (kart_track.lane_marks)
        if (this.lane === null) return [];
        const side = this.lane[2], w = 0.12, quads = [];
        for (let kid = 0; kid < LANE_BAYS; kid++) {
            let [s0, s1, lo, hi] = this.bay(kid);
            lo *= side; hi *= side;
            const a = Math.min(lo, hi), b = Math.max(lo, hi);
            quads.push([[s0, a], [s1, a], [s1, a + w], [s0, a + w]], [[s0, a], [s0 + w, a], [s0 + w, b], [s0, b]],
                       [[s1 - w, a], [s1, a], [s1, b], [s1 - w, b]]);
        }
        return quads;
    }

    gateZone(s) {
        return Math.min(GATES - 1, Math.floor(this.wrap(s) / (this.length / GATES)));
    }

    // (CHANGE 159) each item box's [s, lateral]: four across the road in each row (kart_track.Track.box_spots);
    // (CHANGE 178) the outer pair nearer the kerbs
    boxSpots() {
        const out = [];
        for (const s of this.boxRows) for (const f of [-0.7, -0.2, 0.2, 0.7]) out.push([s, f * this.half]);
        return out;
    }

    // (CHANGE 158) is (s, lateral) in the PIT box (where a kart going slowly is mended)?
    inPit(s, lateral) {
        if (this.pit === null) return false;
        const [s0, s1, side] = this.pit;
        s = pyMod(s, this.length);
        return s0 <= s && s <= s1 && lateral * side >= this.half - PIT_WIDTH;
    }

    // (CHANGE 158) the PIT box's paint as quads, each four [s, lateral] corners (kart_track.Track.pit_marks)
    pitMarks() {
        if (this.pitBox === null) return [];
        const [s0, s1, side] = this.pitBox, inner = side * (this.half - PIT_WIDTH), outer = side * (this.half - PIT_KERB);
        const lo = Math.min(inner, outer), hi = Math.max(inner, outer), w = 0.12;
        const quads = [[[s0, lo], [s1, lo], [s1, lo + w], [s0, lo + w]], [[s0, hi - w], [s1, hi - w], [s1, hi], [s0, hi]],
                       [[s0, lo], [s0 + w, lo], [s0 + w, hi], [s0, hi]], [[s1 - w, lo], [s1, lo], [s1, hi], [s1 - w, hi]]];
        const letters = {P: [[0, 0, 1, 5], [0, 4, 4, 5], [3, 2.5, 4, 5], [0, 2.5, 4, 3.5]],
                         I: [[1.5, 0, 2.5, 5], [0, 4, 4, 5], [0, 0, 4, 1]], T: [[0, 4, 4, 5], [1.5, 0, 2.5, 5]]};
        const left = side < 0 ? hi - 0.25 : hi - 0.25 - (PIT_WIDTH - PIT_KERB - 3.0);  // (the word clear of the kerb)
        [..."PIT"].forEach((ch, i) => {
            for (const [u0, h0, u1, h1] of letters[ch]) {
                const a0 = s0 + 1.5 + h0 * 0.4, a1 = s0 + 1.5 + h1 * 0.4;
                const b0 = left - i * 1.0 - u1 * 0.2, b1 = left - i * 1.0 - u0 * 0.2;
                quads.push([[a0, b0], [a1, b0], [a1, b1], [a0, b1]]);
            }
        });
        return quads;
    }

    // is (s, lateral) within radius of one of these [s, lateral] features (the dash pads, the oil)?
    near(features, s, lateral, radius) {
        for (const [fs, fl] of features) {
            const ds = pyMod(s - fs + this.length / 2, this.length) - this.length / 2;
            if (Math.abs(ds) < radius && Math.abs(lateral - fl) < radius) return true;
        }
        return false;
    }

    grid(place) {
        const row = Math.floor(place / 2), side = place % 2;
        return [this.wrap(-(5.0 + row * 4.0)), side === 0 ? 2.6 : -2.6];
    }

    bounds() {
        const xs = this.pts.map(p => p[0]), ys = this.pts.map(p => p[1]);
        return [Math.min(...xs) - this.half, Math.min(...ys) - this.half,
                Math.max(...xs) + this.half, Math.max(...ys) + this.half];
    }
}

export function load(name = "club") {
    return new Track(TRACKS[name]);
}
