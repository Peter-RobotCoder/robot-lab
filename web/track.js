// A race track as data (kart/kart_track.py, ported line for line): a smooth closed centre line through a few
// points, a width, dash pads and oil placed by distance along (s) and across (lateral, positive to the left).
// The browser asks it the same questions the window does: where is s, where on the track is (x, y), how high.
// Its numbers are Python's to the last bit (math.hypot, % and degrees done as Python does them: pymath.js), because
// the browser's prediction (kart_sim.js) steps a kart on it and must land where the server's step does.

import {hypot, pyMod, degrees} from "./pymath.js";

export const GATES = 8;

// the same tracks the server has, for a page that opens before any server has spoken
export const TRACKS = {
    club: {
        name: "Club Circuit", width: 12.0, laps: 3,
        points: [[0, 0, 0], [45, 0, 0], [80, 6, 0.8], [98, 32, 2.4], [92, 62, 3.0], [66, 82, 1.6], [34, 86, 0.4],
                 [6, 74, 0], [-24, 66, -0.6], [-42, 42, -0.4], [-36, 14, 0], [-18, 2, 0]],
        boosts: [[120.0, 0.0], [235.0, 2.5], [300.0, -2.5]],
        oil: [[170.0, -2.0], [268.0, 1.5]],
    },
    oval: {
        name: "Test Oval", width: 14.0, laps: 2,
        points: [[0, 0, 0], [40, 0, 0], [70, 10, 0], [80, 35, 0], [70, 60, 0], [40, 70, 0], [0, 70, 0],
                 [-30, 60, 0], [-40, 35, 0], [-30, 10, 0]],
        boosts: [[60.0, 0.0]], oil: [],
    },
    straight: {
        name: "Straight Road", width: 12.0, laps: 1,
        points: [[0, 0, 0], [60, 0, 0], [120, 0, 0], [140, 10, 0], [120, 20, 0], [60, 20, 0], [0, 20, 0], [-20, 10, 0]],
        boosts: [], oil: [],
    },
};

export const BOOST_RADIUS = 2.6;
export const OIL_RADIUS = 2.2;

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
        return degrees(Math.atan2(ty, tx));
    }

    height(s) {
        return this.point(s)[2];
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

    gateZone(s) {
        return Math.min(GATES - 1, Math.floor(this.wrap(s) / (this.length / GATES)));
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
