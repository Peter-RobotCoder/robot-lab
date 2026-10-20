"""A race track as data: a loop of points, a width, and what sits on it.

The track is a closed centre line (a smooth curve through the points in TRACKS, resampled every metre or so),
a constant width, and features placed by their distance along the line (s, in metres from the start line) and
their offset across it (lateral, in metres, positive to the left). Everything the game needs is a question about
s and lateral: where is this kart along the track, how far from the middle, what is the track doing ahead, where
is the next gate. The server, the window, the brains and the CPU drivers all ask the same Track object.

Gates: the lap is split into GATES equal lengths; a kart must pass them in order (so no cutting back across the
start line), and the start line is gate 0.

(CHANGE 177) Beside the road: a kerb and verge KERB metres wide that a kart may drive over (a rumble strip: it
slows a little), then the barrier, pushed out by a gravel trap on the outside of the sharp bends (gravel()), which
slows a kart hard and holds one that has lost its momentum. (CHANGE 179) A pit lane beside the start straight
("pit_lane": from s to s on one side), behind the pit wall, with a bay for each kart (its id's): the teacher opens
it (set_pits("lane")) in place of the PIT box painted on the road ("box"). The lane is always there to see; closed,
its entry and exit are walled off.
"""
import bisect
import math

import kart_math as kmath  # (atan2 and hypot the same on every computer: CHANGE 162)

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
        "boxes": [90.0, 205.0],   # (CHANGE 159) where a row of item boxes crosses the road (s)
        "pit_lane": (-22.0, 58.0, -1),  # (CHANGE 179) the pit lane: from s to s (s before the line negative), its side
    },
    "oval": {
        "name": "Test Oval", "width": 14.0, "laps": 2,
        "points": [(0, 0, 0), (40, 0, 0), (70, 10, 0), (80, 35, 0), (70, 60, 0), (40, 70, 0), (0, 70, 0),
                   (-30, 60, 0), (-40, 35, 0), (-30, 10, 0)],
        "boosts": [(60.0, 0.0)],
        "oil": [],
        "pit": (10.0, 28.0, -1),
        "boxes": [110.0, 235.0],
        "pit_lane": (-30.0, 46.0, -1),
    },
    "straight": {  # for netcode tests: a long straight and a hairpin back, the simplest loop there is
        "name": "Straight Road", "width": 12.0, "laps": 1,
        "points": [(0, 0, 0), (60, 0, 0), (120, 0, 0), (140, 10, 0), (120, 20, 0), (60, 20, 0), (0, 20, 0),
                   (-20, 10, 0)],
        "boosts": [], "oil": [],
        "pit": (14.0, 32.0, -1),
        "boxes": [80.0, 250.0],
        "pit_lane": (8.0, 104.0, -1),
    },
    # (CHANGE 180) a circuit the shape of Silverstone's Grand Prix loop, one sixth of its size (a 970 m lap), with its
    # features in order: the start straight into a fast right, a left, a tight right and a hairpin, the long
    # straight, a left and a long right onto the old pit straight, the fast right into the esses, the back straight
    # down to a right, a left and the long right home. The shape is the real road's (from the TUM racetrack database's
    # centre line, Douglas-Peucker simplified) and flat, as the airfield is; the name is ours, the circuit's being a trade mark.
    "airfield": {
        "name": "Airfield GP", "width": 12.0, "laps": 2,
        "points": [(0.0, 0.0, 0), (66.5, -0.5, 0), (91.4, -31.4, 0), (130.2, -43.2, 0), (120.6, -64.6, 0),
                   (127.2, -67.6, 0), (142.0, -62.2, 0), (151.5, -54.4, 0), (160.7, 54.3, 0), (157.8, 62.0, 0),
                   (151.8, 66.0, 0), (135.5, 58.2, 0), (128.2, 58.9, 0), (124.2, 64.9, 0), (126.5, 72.7, 0),
                   (155.1, 80.2, 0), (174.0, 78.1, 0), (184.2, 71.0, 0), (220.6, 32.0, 0), (230.0, 21.3, 0),
                   (233.2, 13.7, 0), (233.6, 4.6, 0), (230.0, -1.9, 0), (211.5, -24.4, 0), (180.2, -51.8, 0),
                   (170.8, -68.4, 0), (147.2, -78.5, 0), (138.6, -96.1, 0), (130.9, -100.5, 0),
                   (105.3, -94.2, 0), (4.1, -110.1, 0), (-20.9, -111.6, 0), (-29.4, -108.9, 0),
                   (-34.8, -102.6, 0), (-35.6, -94.4, 0), (-25.7, -70.7, 0), (-18.3, -33.9, 0),
                   (-29.7, -27.1, 0), (-29.6, -17.5, 0), (-25.6, -8.3, 0), (-19.0, -0.9, 0)],
        "boosts": [(40.0, 0.0), (300.0, 0.0), (520.0, 0.0), (740.0, 0.0)],
        "oil": [(205.0, -2.0), (470.0, 2.0), (690.0, -1.5)],
        "pit": (10.0, 28.0, -1),
        "boxes": [130.0, 420.0, 640.0, 860.0],
        "pit_lane": (-16.0, 60.0, -1),
    },
}

BOOST_RADIUS = 2.6  # how close to a dash pad's middle a kart must pass (m)
OIL_RADIUS = 2.2
PIT_WIDTH = 4.0  # (CHANGE 158) the PIT box's width, in from the barrier on its side (m)
PIT_KERB = 0.6   # (its paint stops short of the kerb along the barrier)
# (CHANGE 177) beside the road, in metres out from its edge (lateral half)
KERB = 1.2          # the kerb and the verge to the barrier's face: a kart may drive on it, slowed a little
GRAVEL_MAX = 4.0    # a gravel trap's reach past that on the outside of the sharpest bends (the barrier moves out with it)
GRAVEL_LEAST = 0.25  # (a trap narrower than this is left out)
# (CHANGE 179) the pit lane
LANE_WALL = 0.5     # the pit wall's thickness (its face at half + KERB, its back at half + KERB + LANE_WALL)
LANE_WIDTH = 7.0    # the lane's asphalt, from the pit wall's back to the outer wall
LANE_RAMP = 12.0    # the entry and the exit: this long, with no wall between the road and the lane
LANE_BAY = 5.5      # each kart's bay along the lane (the first LANE_RAMP + 2 m in)
LANE_BAY_DEPTH = 3.5
LANE_BAYS = 8       # (one a kart: kart_server.MAX_KARTS)
PITS = ("box", "lane")  # the teacher's choice: the PIT box painted on the road, or the pit lane


def smooth(t):
    """0 to 1, eased (kart_scenery's)."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    return t * t * (3 - 2 * t)


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
            length = kmath.hypot(dx, dy) or 1e-6
            self.seg_len.append(length)
            self.tan.append((dx / length, dy / length))
            self.s.append(total)
            total += length
        self.length = total
        self.gate_s = [g * total / GATES for g in range(GATES)]
        self.boosts = [(float(s), float(lat)) for s, lat in data.get("boosts", [])]
        self.oil = [(float(s), float(lat)) for s, lat in data.get("oil", [])]
        self.box_rows = [float(s) for s in data.get("boxes", [])]  # (CHANGE 159) the item boxes' rows
        p = data.get("pit")  # (CHANGE 158) the PIT box: (from s, to s, side), or None
        self.pit_box = (float(p[0]), float(p[1]), 1 if p[2] > 0 else -1) if p else None
        p = data.get("pit_lane")  # (CHANGE 179) the pit lane: (from s, to s, side), or None
        self.lane = (float(p[0]), float(p[1]), 1 if p[2] > 0 else -1) if p else None
        self.pits = "box"
        self.pit = self.pit_box  # (the PIT box in use: None with the pit lane open)
        self.gravel = {1: self.gravel_widths(1), -1: self.gravel_widths(-1)}  # (CHANGE 177) per segment, each side

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
        return math.degrees(kmath.atan2(ty, tx))

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

    # ---------- beside the road (CHANGE 177) ----------
    def clear(self, x, y, r):
        """Is (x, y) at least r from every point of the centre line (so not on another part of the road)?"""
        rr = r * r
        for p in self.pts:
            dx, dy = p[0] - x, p[1] - y
            if dx * dx + dy * dy < rr:
                return False
        return True

    def gravel_widths(self, side):
        """How far a gravel trap reaches past the barrier line at each segment on one side (1 left, -1 right): on
        the outside of the sharp bends (over 17 degrees in 18 m), up to GRAVEL_MAX, eased in and out, and narrower
        where the road comes back round close by (kart_scenery.Circuit.edge does the same; the page's track.js too,
        so every computer agrees where the barrier is)."""
        n = self.n
        want = [GRAVEL_MAX * smooth((-side * self.curvature(self.s[i] - 9.0, 18.0) - 17.0) / 9.0) for i in range(n)]
        for _ in range(2):
            smoothed = []
            for i in range(n):
                window = want[max(0, i - 6):i + 7]
                total = 0.0  # (added left to right, as track.js does: Python 3.12's sum() compensates its rounding)
                for v in window:
                    total += v
                smoothed.append(total / len(window))
            want = smoothed
        out = []
        for i in range(n):
            w = want[i]
            while w > GRAVEL_LEAST:
                d = KERB + w + 1.0
                x, y, _ = self.point(self.s[i], side * (self.half + d))
                if self.clear(x, y, self.half + d - 0.3):
                    break
                w -= 0.5
            out.append(w if w > GRAVEL_LEAST else 0.0)
        return out

    def gravel_at(self, seg, side):
        """The gravel trap's width beside segment seg on that side (0: none, the barrier at the kerb's edge)."""
        return self.gravel[1 if side > 0 else -1][seg]

    def barrier(self, seg, side):
        """How far from the middle the barrier's face is beside segment seg on that side (a positive lateral)."""
        return self.half + KERB + self.gravel_at(seg, side)

    # ---------- the pit lane (CHANGE 179) ----------
    def set_pits(self, mode):
        """"box": the PIT box painted on the road mends (the pit lane, if there is one, is walled off); "lane": the
        pit lane is open and the PIT box is just paint."""
        self.pits = mode if mode in PITS else "box"
        self.pit = self.pit_box if self.pits == "box" else None

    def lane_zone(self, s):
        """How the pit lane sits beside s: None (no lane here), "ramp" (its entry or its exit: the lane's end wall
        runs on a slant from the barrier line out to the lane's outer wall, lane_edge; open, there is nothing between
        the road and the lane here) or "wall" (the pit wall)."""
        if self.lane is None:
            return None
        s0, s1, _ = self.lane
        ds = (s - s0) % self.length
        if ds > s1 - s0:
            return None
        return "ramp" if ds < LANE_RAMP or ds > s1 - s0 - LANE_RAMP else "wall"

    def lane_edge(self, s):
        """How far from the middle the lane's outer wall is at s (a positive lateral): slanting out from the barrier
        line over the entry and back in over the exit, so a kart leaving the lane is eased back onto the road."""
        s0, s1, _ = self.lane
        ds = (s - s0) % self.length
        span, inner, outer = s1 - s0, self.half + KERB, self.lane_outer()
        if ds < LANE_RAMP:
            return inner + (outer - inner) * (ds / LANE_RAMP)
        if ds > span - LANE_RAMP:
            return inner + (outer - inner) * ((span - ds) / LANE_RAMP)
        return outer

    def lane_side(self, lateral):
        """Is this lateral on the pit lane's side of the road (the lane's side, or 0 for no lane)?"""
        return self.lane[2] if self.lane is not None and lateral * self.lane[2] > 0 else 0

    def lane_inner(self):
        """The lane's asphalt starts here (a positive lateral): the pit wall's back."""
        return self.half + KERB + LANE_WALL

    def lane_outer(self):
        """...and ends here, at the outer wall's face."""
        return self.half + KERB + LANE_WALL + LANE_WIDTH

    def bay(self, kid):
        """Kart kid's pit bay: (s0, s1, lateral in, lateral out), the laterals positive (the lane's side), or None."""
        if self.lane is None or not 0 <= kid < LANE_BAYS:
            return None
        s0 = self.lane[0] + LANE_RAMP + 2.0 + kid * LANE_BAY
        return (s0, s0 + LANE_BAY - 0.5, self.lane_outer() - LANE_BAY_DEPTH, self.lane_outer())

    def in_bay(self, kid, s, lateral):
        """Is (s, lateral) in kart kid's pit bay (where it is mended and given new tyres when it stops)?"""
        b = self.bay(kid)
        if b is None:
            return False
        s0, s1, lo, hi = b
        ds = (s - s0) % self.length
        return ds <= s1 - s0 and lo <= lateral * self.lane[2] <= hi

    def lane_marks(self):
        """The lane's paint as quads of four (s, lateral) corners: each bay's outline (a white box) and the line
        along the lane (kart_gfx.TrackVisual and track.js draw them; the bays' name boards are theirs)."""
        if self.lane is None:
            return []
        side, w = self.lane[2], 0.12
        quads = []
        for kid in range(LANE_BAYS):
            s0, s1, lo, hi = self.bay(kid)
            lo, hi = side * lo, side * hi
            a, b = min(lo, hi), max(lo, hi)
            quads += [((s0, a), (s1, a), (s1, a + w), (s0, a + w)), ((s0, a), (s0 + w, a), (s0 + w, b), (s0, b)),
                      ((s1 - w, a), (s1, a), (s1, b), (s1 - w, b))]
        return quads

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

    def box_spots(self):
        """(CHANGE 159) Each item box's (s, lateral): four across the road in each row (track.js's boxSpots too).
        (CHANGE 178) The outer pair nearer the kerbs, so a kart along the barrier takes one too."""
        across = [-0.7, -0.2, 0.2, 0.7]  # (as a share of the half width)
        return [(s, f * self.half) for s in self.box_rows for f in across]

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
        if self.pit_box is None:
            return []
        s0, s1, side = self.pit_box
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
