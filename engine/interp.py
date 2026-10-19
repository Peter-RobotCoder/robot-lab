"""Smooth movement between the class server's snapshots.

The class server sends the state of the game 30 times a second. Drawing each one as it arrives makes everything
step, and a Wi-Fi stall (a lost packet behind which the next ones queue) makes it freeze and jump. Instead the
window keeps a short queue of snapshots and draws the picture a little in the past (the render delay, about two
snapshots), blending between the snapshot before and the one after that moment. A stall is then invisible as long
as it is shorter than the delay; a longer one makes the delay grow a little (and shrink again slowly afterwards).

(CHANGE 175) The delay follows the network: two snapshots plus how late the snapshots have been arriving (the 97th
percentile over the last three seconds, measured against the quickest), between 67 and 250 ms, as Mirror, Unity's
netcode and Photon Fusion set theirs; it only moves when the target is more than half a snapshot away (a dead
band, so it doesn't hunt around the jitter's edge), up at once and down at 20 ms a second. Past the newest snapshot
the picture carries on for up to 100 ms, headings too (positions and headings are near enough straight over that;
rotations as quaternions are held).

    snaps = Snapshots(LAB_SPEC)            # or FIGHT_SPEC, or a spec of your own (see blend)
    snaps.push(message)                    # every state message, as it arrives (it carries "sm", server ms)
    state = snaps.sample(now)              # every frame: a state message blended for this moment, or None

A spec says which numbers to blend and how; everything else is taken from the later snapshot. The window's own
robot is blended like the others (Robot Lab and Fight Lab don't predict their own movement; the kart game does, with
engine.predict, and draws its own kart from that instead).
"""
import math
import time
from collections import deque

SERVER_MS = "sm"      # the server's time stamp on a state message (milliseconds, its own clock)
RECEIVED = "_rx"      # engine.net stamps each message with time.perf_counter() when it arrived


class ServerClock:
    """What time it is on the server, estimated from the stamp on every message.

    Each message gives one sample of (server time - our time). A message delayed on the way makes that sample
    smaller, never bigger, so the biggest sample in the last few seconds is the one nearest the truth. The estimate
    follows a bigger sample at once (a quicker packet has shown the truth) and a smaller one slowly (slewed), so a
    short burst of slow packets doesn't move the picture."""

    def __init__(self, window=4.0, slew=0.02):
        self.window, self.slew = window, slew  # slew: seconds per second the estimate may fall by
        self.samples = deque()                 # (our time, server time - our time)
        self.offset = None
        self.last_local = None

    def note(self, server_t, local_t):
        off = server_t - local_t
        self.samples.append((local_t, off))
        while self.samples and local_t - self.samples[0][0] > self.window:
            self.samples.popleft()
        best = max(o for _, o in self.samples)
        if self.offset is None or best > self.offset:
            self.offset = best
        else:
            dt = local_t - (self.last_local if self.last_local is not None else local_t)
            self.offset = max(best, self.offset - self.slew * max(0.0, dt))
        self.last_local = local_t

    def server_time(self, local_t):
        return None if self.offset is None else local_t + self.offset


class Snapshots:
    """The queue of snapshots and the render delay (see the module's docstring)."""

    def __init__(self, spec=None, interval=1 / 30, delay_intervals=2.0, min_delay=0.05, max_delay=0.25,
                 max_extrapolate=0.1, keep=1.5, late_window=3.0, late_pct=0.97, fall=0.02):
        self.spec = spec or {}
        self.interval = interval
        self.base_delay = max(min_delay, interval * delay_intervals)
        self.delay = self.base_delay
        self.min_delay, self.max_delay, self.max_extrapolate = min_delay, max_delay, max_extrapolate
        self.keep = keep                 # seconds of snapshots kept (for the blend and for the gap statistics)
        self.late_window, self.late_pct, self.fall = late_window, late_pct, fall  # (CHANGE 175: the delay's target)
        self.late = deque()              # (our time, how late that snapshot was against the quickest)
        self.target = self.base_delay
        self.clock = ServerClock()
        self.snaps = deque()             # (server time, message)
        self.last_rx = None
        self.stalls = 0                  # gaps between arrivals of more than 4.5 intervals (150 ms)
        self.worst_gap = 0.0             # the longest gap seen (seconds)
        self.underruns = 0               # times the picture wanted a snapshot newer than any that had arrived
        self.in_underrun = False
        self.last_sample_t = None
        self.t_render = None             # the moment (server time) being drawn: a clock of its own, never put back

    @property
    def latest(self):
        return self.snaps[-1][1] if self.snaps else None

    def push(self, msg, local_t=None):
        """A state message from the server. It needs the server's stamp (sm); without one it is drawn as it is."""
        if local_t is None:
            local_t = msg.get(RECEIVED) or time.perf_counter()
        sm = msg.get(SERVER_MS)
        if self.last_rx is not None:
            gap = local_t - self.last_rx
            self.worst_gap = max(self.worst_gap, gap)
            if gap > 4.5 * self.interval:
                self.stalls += 1
        self.last_rx = local_t
        if sm is None:
            self.snaps.clear()
            self.snaps.append((None, msg))
            return
        server_t = sm / 1000.0
        self.clock.note(server_t, local_t)
        # (CHANGE 175) how late this one was against the quickest path seen: what the delay has to cover
        self.late.append((local_t, max(0.0, self.clock.server_time(local_t) - server_t)))
        while self.late and local_t - self.late[0][0] > self.late_window:
            self.late.popleft()
        lates = sorted(v for _, v in self.late)
        pct = lates[min(len(lates) - 1, int(self.late_pct * len(lates)))] if lates else 0.0
        self.target = max(self.base_delay, min(self.max_delay, self.base_delay + pct))
        if self.target > self.delay + self.interval / 2:  # (a dead band of half a snapshot: up at once)
            self.delay = self.target
        if self.snaps and self.snaps[-1][0] is not None and server_t <= self.snaps[-1][0]:
            return  # (out of order or repeated: keep what we have)
        self.in_underrun = False  # (something new has arrived: a stall is over)
        self.snaps.append((server_t, msg))
        while len(self.snaps) > 2 and server_t - self.snaps[0][0] > self.keep:
            self.snaps.popleft()

    def sample(self, local_t=None):
        """The state to draw now: the two snapshots either side of (server time - delay), blended. None until a
        snapshot has arrived."""
        if not self.snaps:
            return None
        if self.snaps[-1][0] is None:  # (no server stamps: nothing to blend)
            return self.snaps[-1][1]
        if local_t is None:
            local_t = time.perf_counter()
        dt = 0.0 if self.last_sample_t is None else max(0.0, local_t - self.last_sample_t)
        self.last_sample_t = local_t
        # the delay eases back towards its target when the network has been quicker for a while (CHANGE 175: the
        # target measured, not the base; only when it is more than half a snapshot below, so it doesn't hunt)
        if self.delay > self.target + self.interval / 2:
            self.delay = max(self.target, self.delay - self.fall * dt)
        # The moment drawn is a clock of its own: it runs at the server's speed, a little slower while it is ahead
        # of where it should be (after a stall made the delay grow, or a quick packet moved the server clock) and a
        # little faster while behind. So the picture never jumps back and never skips, only eases.
        want = self.clock.server_time(local_t) - self.delay
        if self.t_render is None or abs(want - self.t_render) > 0.5:
            self.t_render = want  # (the first frame, a reconnect, a pause: start again from the right moment)
        else:
            gap = want - self.t_render
            rate = 1.0 if abs(gap) < 0.002 else (0.75 if gap < 0 else 1.1)
            self.t_render += dt * rate
            if (gap < 0 and self.t_render < want) or (gap > 0 and self.t_render > want):
                self.t_render = want  # (eased all the way: don't overshoot)
        t = self.t_render
        snaps = self.snaps
        if t >= snaps[-1][0]:  # nothing new enough has arrived: carry on a little further, then hold the latest
            if not self.in_underrun:  # (once per stall, not once per frame: the delay grows by one snapshot)
                self.in_underrun = True
                self.underruns += 1
                self.delay = min(self.max_delay, self.delay + self.interval)
            over = t - snaps[-1][0]
            if over > self.max_extrapolate:  # held where the carrying-on stopped (the clock waits here too)
                self.t_render = snaps[-1][0] + self.max_extrapolate
                over = self.max_extrapolate
            if len(snaps) >= 2 and over > 0:
                (ta, a), (tb, b) = snaps[-2], snaps[-1]
                alpha = 1.0 + over / max(1e-6, tb - ta)
                return blend(a, b, min(alpha, 2.5), self.spec, extrapolating=True)
            return snaps[-1][1]
        if t <= snaps[0][0]:
            return snaps[0][1]
        # find the pair round t (newest first: it is nearly always the last pair)
        for i in range(len(snaps) - 1, 0, -1):
            ta, a = snaps[i - 1]
            tb, b = snaps[i]
            if ta <= t <= tb:
                alpha = (t - ta) / max(1e-6, tb - ta)
                return blend(a, b, alpha, self.spec)
        return snaps[-1][1]

    def report(self):
        """Numbers for the status line and the teacher's grid."""
        return {"delay_ms": round(self.delay * 1000), "stalls": self.stalls, "target_ms": round(self.target * 1000),
                "worst_gap_ms": round(self.worst_gap * 1000), "underruns": self.underruns}


# ---------- blending two state messages ----------
def lerp(a, b, k):
    if isinstance(a, (list, tuple)):
        if not isinstance(b, (list, tuple)) or len(a) != len(b):
            return b
        return [x + (y - x) * k for x, y in zip(a, b)]
    return a + (b - a) * k


def slerp(a, b, k):
    """Between two quaternions given as [w, x, y, z] (Panda3D's order), the short way round."""
    if not (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == 4 and len(b) == 4):
        return b
    k = max(0.0, min(1.0, k))  # (rotations are not carried on past the latest snapshot)
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = [-y for y in b], -dot
    if dot > 0.9995:  # (so close that a straight blend, re-normalised, is right)
        out = [x + (y - x) * k for x, y in zip(a, b)]
    else:
        th = math.acos(max(-1.0, min(1.0, dot)))
        sa, sb = math.sin((1 - k) * th), math.sin(k * th)
        out = [(x * sa + y * sb) for x, y in zip(a, b)]
    n = math.sqrt(sum(x * x for x in out)) or 1.0
    return [x / n for x in out]


def angle(a, b, k):
    """Between two headings in degrees, the short way round."""
    d = (b - a + 180) % 360 - 180
    return a + d * k


def posquat(a, b, k):
    """A position and a quaternion in one list of seven (Robot Lab's second flipper plate)."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == 7 and len(b) == 7:
        return lerp(a[:3], b[:3], k) + slerp(a[3:], b[3:], k)
    return b


OPS = {"lerp": lerp, "slerp": slerp, "angle": angle, "posquat": posquat}


def blend(a, b, k, spec, extrapolating=False):
    """b with its numbers blended towards a's by (1 - k): k = 0 gives a's numbers, 1 gives b's, more than 1
    carries on past b (only for lerp fields). spec is a dict mirroring the message:
      "field": "lerp" | "slerp" | "angle" | "posquat"       a number, a list of numbers, a quaternion, a heading
      "field": "lerp if a"                                   lerp, but only while the entity's "a" field matches
      "field": {sub spec}                                    a dict inside the message
      "field": ["id", {sub spec}]                            a list of dicts matched up by their "id" field
    Anything not in the spec, missing on either side, or None is taken from b."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return b
    out = dict(b)
    for key, rule in spec.items():
        if key not in a or key not in b or a[key] is None or b[key] is None:
            continue
        va, vb = a[key], b[key]
        if isinstance(rule, dict):
            out[key] = blend(va, vb, k, rule, extrapolating)
        elif isinstance(rule, list):
            id_key, sub = rule
            if not (isinstance(va, list) and isinstance(vb, list)):
                continue
            by_id = {e.get(id_key): e for e in va if isinstance(e, dict)}
            out[key] = [blend(by_id[e.get(id_key)], e, k, sub, extrapolating)
                        if isinstance(e, dict) and e.get(id_key) in by_id else e for e in vb]
        elif isinstance(rule, str):
            if rule.startswith("lerp if "):
                same = rule[8:]
                if a.get(same) != b.get(same):
                    continue
                rule = "lerp"
            op = OPS.get(rule)
            if op is None:
                continue
            if extrapolating and rule not in ("lerp", "angle"):  # (CHANGE 175: headings carried on too)
                continue
            try:
                out[key] = op(va, vb, k)
            except (TypeError, ValueError):
                pass
    return out


# The two shipped games' state messages
LAB_SPEC = {"arenas": ["i", {
    "robots": ["id", {"pos": "lerp", "quat": "slerp", "wpos": "lerp", "wquat": "slerp", "w2": "posquat",
                      "speed": "lerp"}],
    "hz": {"saws": "lerp", "ff": "slerp", "pit": "lerp", "spikes": "lerp", "flames": "lerp"}}]}

FIGHT_SPEC = {"rings": ["i", {
    "f": ["id", {"pos": "lerp", "h": "angle", "k": "lerp if a"}]}]}


def perf_line(name, reports):
    """One line for the teacher about a learner's window, from the report it sends (see the games' send_perf)."""
    r = (reports or {}).get(name)
    if not r:
        return "" if not name else f"{name}'s window: no report yet"
    parts = [f"{str(r.get('tier') or '?').capitalize()} graphics", f"{r.get('fps', '?')} fps",
             f"ping {r.get('ping', '?')} ms"]
    if r.get("ctrl") is not None:
        parts.append(f"key delay {r['ctrl']} ms")
    if r.get("stalls"):
        parts.append(f"{r['stalls']} network stalls")
    return f"{name}'s window:   " + "   ".join(parts)
