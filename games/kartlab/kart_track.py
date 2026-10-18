"""A race track as data: a loop of points, a width, and what sits on it.

The track is a closed centre line (a smooth curve through the points in TRACKS, resampled every metre or so),
a constant width, and features placed by their distance along the line (s, in metres from the start line) and
their offset across it (lateral, in metres, positive to the left). Everything the game needs is a question about
s and lateral: where is this kart along the track, how far from the middle, what is the track doing ahead, where
is the next gate. The server, the window, the brains and the CPU drivers all ask the same Track object.

Gates: the lap is split into GATES equal lengths; a kart must pass them in order (so no cutting back across the
start line), and the start line is gate 0.
"""
import bisect
import math

GATES = 8

TRACKS = {
    "club": {
        "name": "Club Circuit", "width": 12.0, "laps": 3,
        # the centre line's control points (x, y, height), going anticlockwise; the start line is at the first
        "points": [(0, 0, 0), (45, 0, 0), (80, 6, 0.8), (98, 32, 2.4), (92, 62, 3.0), (66, 82, 1.6), (34, 86, 0.4),
                   (6, 74, 0), (-24, 66, -0.6), (-42, 42, -0.4), (-36, 14, 0), (-18, 2, 0)],
        "boosts": [(120.0, 0.0), (235.0, 2.5), (300.0, -2.5)],   # dash pads: (s, lateral)
        "oil": [(170.0, -2.0), (268.0, 1.5)],                     # slippery patches: (s, lateral)
        "pit": (12.0, 30.0, -1),  # (CHANGE 158) the PIT box: from s to s along one side (-1 right, 1 left) of the road
    },
    "oval": {
        "name": "Test Oval", "width": 14.0, "laps": 2,
        "points": [(0, 0, 0), (40, 0, 0), (70, 10, 0), (80, 35, 0), (70, 60, 0), (40, 70, 0), (0, 70, 0),
                   (-30, 60, 0), (-40, 35, 0), (-30, 10, 0)],
        "boosts": [(60.0, 0.0)],
        "oil": [],
        "pit": (10.0, 28.0, -1),
    },
    "straight": {  # for netcode tests: a long straight and a hairpin back, the simplest loop there is
        "name": "Straight Road", "width": 12.0, "laps": 1,
        "points": [(0, 0, 0), (60, 0, 0), (120, 0, 0), (140, 10, 0), (120, 20, 0), (60, 20, 0), (0, 20, 0),
                   (-20, 10, 0)],
        "boosts": [], "oil": [],
        "pit": (14.0, 32.0, -1),
    },
}

BOOST_RADIUS = 2.6  # how close to a dash pad's middle a kart must pass (m)
OIL_RADIUS = 2.2
PIT_WIDTH = 4.0  # (CHANGE 158) the PIT box's width, in from the barrier on its side (m)
PIT_KERB = 0.6   # (its paint stops short of the kerb along the barrier)


def catmull_rom(points, step=1.2):
    """A smooth closed curve through the points, as a list of (x, y, z) about step metres apart."""
    n = len(points)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = (points[(i + k - 1) % n] for k in range(4))
        seg = math.dist(p1[:2], p2[:2])
        count = max(2, int(seg / step))
        for j in range(count):
            t = j / count
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t2
                                    + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t3) for c in range(3)))
    return out


class Track:
    def __init__(self, data):
        self.name, self.width, self.laps = data["name"], float(data["width"]), int(data.get("laps", 3))
        self.half = self.width / 2
        self.pts = catmull_rom(data["points"])
        n = self.n = len(self.pts)
        self.seg_len, self.tan, self.s = [], [], []
        total = 0.0
        for i in range(n):
            a, b = self.pts[i], self.pts[(i + 1) % n]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy) or 1e-6
            self.seg_len.append(length)
            self.tan.append((dx / length, dy / length))
            self.s.append(total)
            total += length
        self.length = total
        self.gate_s = [g * total / GATES for g in range(GATES)]
        self.boosts = [(float(s), float(lat)) for s, lat in data.get("boosts", [])]
        self.oil = [(float(s), float(lat)) for s, lat in data.get("oil", [])]
        p = data.get("pit")  # (CHANGE 158) the PIT box: (from s, to s, side), or None
        self.pit = (float(p[0]), float(p[1]), 1 if p[2] > 0 else -1) if p else None

    # ---------- where things are ----------
    def segment_at(self, s):
        s %= self.length
        return max(0, bisect.bisect_right(self.s, s) - 1)

    def point(self, s, lateral=0.0):
        """The place s metres along the track and lateral metres to the left of its middle: (x, y, z)."""
        s %= self.length
        i = self.segment_at(s)
        t = (s - self.s[i]) / self.seg_len[i]
        a, b = self.pts[i], self.pts[(i + 1) % self.n]
        tx, ty = self.tan[i]
        return (a[0] + (b[0] - a[0]) * t - ty * lateral, a[1] + (b[1] - a[1]) * t + tx * lateral,
                a[2] + (b[2] - a[2]) * t)

    def heading(self, s):
        """The track's direction at s, in degrees (0 = +x, anticlockwise), as a kart's yaw is."""
        tx, ty = self.tan[self.segment_at(s)]
        return math.degrees(math.atan2(ty, tx))

    def height(self, s):
        return self.point(s)[2]

    def curvature(self, s, ahead=15.0):
        """How much the track turns between s and s + ahead, in degrees (positive = left). The number brains and
        the CPU drivers brake for."""
        h0, h1 = self.heading(s), self.heading(s + ahead)
        return (h1 - h0 + 180) % 360 - 180

    def locate(self, x, y, hint=None):
        """Where (x, y) is on the track: (segment, s, lateral). hint is the segment last time (the search then
        starts there, which is nearly always right); without it every segment is tried."""
        n = self.n
        if hint is None:
            candidates = range(n)
        else:
            candidates = [(hint + k) % n for k in range(-10, 11)]
        best = None
        for i in candidates:
            a = self.pts[i]
            tx, ty = self.tan[i]
            px, py = x - a[0], y - a[1]
            t = max(0.0, min(self.seg_len[i], px * tx + py * ty))
            cx, cy = px - tx * t, py - ty * t
            d2 = cx * cx + cy * cy
            if best is None or d2 < best[0]:
                best = (d2, i, t, cx, cy)
        d2, i, t, cx, cy = best
        if hint is not None and d2 > 400.0:  # (more than 20 m off: the hint was wrong, look everywhere)
            return self.locate(x, y, None)
        tx, ty = self.tan[i]
        lateral = tx * cy - ty * cx  # (left of the tangent is positive)
        return i, self.s[i] + t, lateral

    # ---------- the race ----------
    def gate_zone(self, s):
        """Which gate's stretch of track s is in (0 = just past the start line)."""
        return min(GATES - 1, int((s % self.length) / (self.length / GATES)))

    def progress(self, lap, cp, s):
        """How far round the race a kart is, for ordering: laps done, then metres along. A kart that hasn't crossed
        the start line yet (or has slipped back behind it) counts as behind it."""
        s %= self.length
        if cp <= 1 and s > self.length * 0.75:
            return lap * self.length + s - self.length
        return lap * self.length + s

    def grid(self, place):
        """Where a kart starts: two abreast, 4 m apart, behind the start line."""
        row, side = divmod(place, 2)
        return (-(5.0 + row * 4.0)) % self.length, 2.6 if side == 0 else -2.6

    def in_pit(self, s, lateral):
        """(CHANGE 158) Is (s, lateral) in the PIT box (where a kart going slowly is mended)?"""
        if self.pit is None:
            return False
        s0, s1, side = self.pit
        s %= self.length
        inner = self.half - PIT_WIDTH  # (the box runs from the barrier PIT_WIDTH in towards the middle)
        return s0 <= s <= s1 and lateral * side >= inner

    def pit_marks(self):
        """(CHANGE 158) The PIT box's paint as quads, each four (s, lateral) corners: a yellow outline and the word
        PIT across it near its start, reading the right way for a kart coming up to it (track.js's pitMarks too)."""
        if self.pit is None:
            return []
        s0, s1, side = self.pit
        inner, outer = side * (self.half - PIT_WIDTH), side * (self.half - PIT_KERB)
        lo, hi = min(inner, outer), max(inner, outer)
        w = 0.12  # (the lines' width)
        quads = [((s0, lo), (s1, lo), (s1, lo + w), (s0, lo + w)), ((s0, hi - w), (s1, hi - w), (s1, hi), (s0, hi)),
                 ((s0, lo), (s0 + w, lo), (s0 + w, hi), (s0, hi)), ((s1 - w, lo), (s1, lo), (s1, hi), (s1 - w, hi))]
        # the letters on a grid 4 across (0.2 m each, the first column on the driver's left) by 5 along (0.4 m each)
        letters = {"P": [(0, 0, 1, 5), (0, 4, 4, 5), (3, 2.5, 4, 5), (0, 2.5, 4, 3.5)],
                   "I": [(1.5, 0, 2.5, 5), (0, 4, 4, 5), (0, 0, 4, 1)],
                   "T": [(0, 4, 4, 5), (1.5, 0, 2.5, 5)]}
        left = hi - 0.25 if side < 0 else hi - 0.25 - (PIT_WIDTH - PIT_KERB - 3.0)  # (the word clear of the kerb)
        for i, ch in enumerate("PIT"):
            for u0, h0, u1, h1 in letters[ch]:
                a0, a1 = s0 + 1.5 + h0 * 0.4, s0 + 1.5 + h1 * 0.4
                b0, b1 = left - i * 1.0 - u1 * 0.2, left - i * 1.0 - u0 * 0.2
                quads.append(((a0, b0), (a1, b0), (a1, b1), (a0, b1)))
        return quads

    def near(self, features, s, lateral, radius):
        """Is (s, lateral) within radius of one of these (s, lateral) features?"""
        for fs, fl in features:
            ds = (s - fs + self.length / 2) % self.length - self.length / 2
            if abs(ds) < radius and abs(lateral - fl) < radius:
                return True
        return False

    def edges(self, every=1):
        """The left and right edges as polylines of (x, y, z), for drawing."""
        left, right = [], []
        for i in range(0, self.n, every):
            s = self.s[i]
            left.append(self.point(s, self.half))
            right.append(self.point(s, -self.half))
        return left, right

    def bounds(self):
        xs = [p[0] for p in self.pts]
        ys = [p[1] for p in self.pts]
        return min(xs) - self.half, min(ys) - self.half, max(xs) + self.half, max(ys) + self.half


def load(name="club"):
    return Track(TRACKS[name])
