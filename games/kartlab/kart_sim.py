"""The kart race: a hand-written arcade kart that the server and every window step identically.

Why hand-written and not Bullet: a window predicts its own kart (it applies the keys at once and the server
corrects it later), so the same step must give the same answer on the Linux class server and a Windows laptop.
Bullet can't promise that and keeps state a snapshot can't carry; this step is a few lines of arithmetic on a
small dict, costs about 4 microseconds, and both ends round the result to the wire's precision each tick so they
start every tick from the same numbers (engine.wire.Schema.quantise).

A kart's state is a dict (see new_kart). Its input is (throttle, steer, buttons) with throttle and steer from -1
to 1 and the buttons DRIFT, USE and RESPAWN. step() is pure: it reads the track and the kart's stats, touches no
other kart, and returns a new dict. Everything between karts (bumping) and the race itself (gates, laps, places,
the countdown) is in Race, on the server only; a window learns of it from the server's snapshots.

The design sheet: 100 points between speed, acceleration and grip (10 to 60 each), as Robot Lab's robots.
"""
import math

import kart_version  # noqa: F401  (puts the engine, shared by every game, on the path)
import kart_track

STEP = 1 / 60
POINTS_TOTAL, STAT_MIN, STAT_MAX = 100, 10, 60
STATS = ("speed", "acceleration", "grip")
SETTINGS = {}  # (a kart has no settings beyond its points; the engine's limits and garage expect the name)
FULL_STAT, FULL_POINTS_TOTAL = (STAT_MIN, STAT_MAX), POINTS_TOTAL  # the widest ranges the teacher may open
STAT_NOTES = {"speed": "points for top speed", "acceleration": "points for acceleration",
              "grip": "points for grip: how fast a slide dies, and how sharply it steers"}
LIMITS = None  # the engine's limits Spec (made below, once the engine can be imported)

# Rules an approved AI request may change (mods/rules.py): the race's, on the server only. Nothing a window
# predicts with is here, so a rule change can't make a window and the server disagree about a kart.
DEFAULT_RULES = {"laps": 3, "cpu_karts": 3, "countdown_seconds": 4.0, "bump_distance": 1.7, "bump_slowdown": 0.3}
RULES = dict(DEFAULT_RULES)

# Features learners asked for through AI cards that the teacher switches on and off (the engine's user mods):
# key: (name for the teacher's Controls, one sentence). Off by default; Race.user_mods says which are on.
USER_MODS = {}

DRIFT, USE, RESPAWN = 1, 2, 4   # the input's buttons
FLAG_DRIFT_L, FLAG_DRIFT_R, FLAG_FINISHED, FLAG_WRONG_WAY, FLAG_BOOSTING = 1, 2, 4, 8, 16

KART_HALF = 0.8          # half a kart's width: how close to the edge it may go (m)
BUMP_DISTANCE = 1.7      # karts closer than this push each other apart (m)
MINI_TURBO, SUPER_TURBO = 270, 570             # drift charge needed (Mario Kart's numbers)
MINI_BOOST, SUPER_BOOST = 37, 100              # ...and the boosts they pay out, in ticks (0.62 s, 1.67 s)
PAD_BOOST = 90                                 # a dash pad's boost (1.5 s)
OIL_TICKS = 75                                 # how long an oil patch's slide lasts (1.25 s)
BOOST_SPEED, BOOST_ACCEL = 1.25, 1.5
COUNTDOWN_TICKS = 60 * 4                       # 3, 2, 1, GO
FLAGS_GRID, FLAGS_RACE, FLAGS_OVER = 0, 1, 2   # the snapshot's flags byte: the race's phase

# the wire record for one kart (engine.wire): both ends round their numbers to this every tick
SCHEMA_FIELDS = [("x", "i", 100), ("y", "i", 100), ("yaw", "h", 10), ("v", "h", 100), ("u", "h", 100),
                 ("charge", "H", 1), ("boost", "B", 1), ("slip", "B", 1), ("lap", "B", 1), ("cp", "B", 1),
                 ("flags", "B", 1)]


def default_design(name="Kart", colour=(220, 60, 50)):
    return {"name": name, "colour": list(colour), "speed": 34, "acceleration": 33, "grip": 33}


# ---------- the kart as variables (the engine's schema: the code panel and the garage's tables) ----------
def schema():
    """The kart's variables, in the HUD's groups: three integer points, a string name and a colour list. The
    design is the flat dictionary default_design() makes."""
    from engine.schema import Var
    return ([Var(k, (k,), "int", "points", tool=k, note=STAT_NOTES[k]) for k in STATS] +  # (each point is its own
            #  garage tool, as Robot Lab's settings are: lesson 1 shows them one by one, lesson 2 adds the
            #  100-point table, tool "points_table")
            [Var("kart_name", ("name",), "str", "strings", tool="name_and_colour",
                 note="a string: text made of chars", max_len=12),
             Var("colour", ("colour",), "rgb", "lists", tool="name_and_colour", note="red, green, blue: 0 to 255")])


design_schema = schema


# ---------- the learners' limits (the engine's Spec works on points and settings groups; a kart's points are
# flat in its design, so the design is shown to it in that shape) ----------
def _limits():
    global LIMITS
    if LIMITS is None:
        from engine.limits import Spec
        LIMITS = Spec(SETTINGS, {}, STATS, (STAT_MIN, STAT_MAX), FULL_STAT, POINTS_TOTAL, FULL_POINTS_TOTAL)
    return LIMITS


def _nested(d):
    return {"points": {k: d.get(k) for k in STATS}, "settings": {}}


def default_limits():
    """The learners' ranges as they are until the teacher changes them (the Limits tab narrows them)."""
    return _limits().default()


def code_limits(limits):
    """What the code may set: up to twice the teacher's limit, or the maximum, whichever is smaller."""
    return _limits().code_room(limits)


def full_limits():
    """The widest ranges: the teacher's own kart is checked against these."""
    return _limits().full()


def clean_limits(new, old=None):
    """Limits sent by the teacher's window (or loaded from a file), made safe."""
    return _limits().clean(new, old)


def check_design(d, limits=None):
    """Return a list of problems (empty = fine). Used by the server and shown to learners. limits: the ranges to
    hold it to (the learners', as the teacher set them, or full_limits() for the teacher's own kart)."""
    if not isinstance(d, dict):
        return ["the design must be a dictionary"]
    problems = []
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        problems.append("name must be some text")
    elif len(d["name"]) > 12:
        problems.append("name can be at most 12 characters")
    c = d.get("colour")
    if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                                                         for v in c)):
        problems.append("colour must be three whole numbers from 0 to 255, [red, green, blue]")
    limits = limits or default_limits()
    for k in STATS:
        lo, hi = limits["points"][k]
        v = d.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            problems.append(f"{k} must be a whole number from {lo} to {hi}")
    vals = [d.get(k) for k in STATS]
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals) and sum(vals) > limits["points_total"]:
        problems.append(f"{sum(vals)} points used: the most you can spend is {limits['points_total']}")
    return problems


def fit_design(d, limits=None):
    """A design inside the rules: each stat 10 to 60 (or the teacher's narrower limits), 100 points in all (the
    extra or the shortfall spread out). With limits, a design already inside them comes back as it is."""
    if limits is not None:
        nested = _limits().fit(_nested(d), limits)
        if nested["points"] == _nested(d)["points"]:
            return d
        return {**d, **nested["points"]}
    out = dict(d)
    vals = [max(STAT_MIN, min(STAT_MAX, int(out.get(k, 33)))) for k in STATS]
    over = sum(vals) - POINTS_TOTAL
    i = 0
    while over != 0 and i < 300:
        k = i % len(STATS)
        if over > 0 and vals[k] > STAT_MIN:
            vals[k] -= 1
            over -= 1
        elif over < 0 and vals[k] < STAT_MAX:
            vals[k] += 1
            over += 1
        i += 1
    for k, v in zip(STATS, vals):
        out[k] = v
    out["name"] = str(out.get("name", "Kart"))[:12] or "Kart"
    c = out.get("colour") or [220, 60, 50]
    out["colour"] = [max(0, min(255, int(v))) for v in list(c)[:3]]
    return out


def stats_of(design):
    """What the points buy: top speed in m/s, acceleration in m/s^2, grip (how fast a slide dies, per second) and
    how sharply it steers (degrees a second at low speed)."""
    sp, ac, gr = (design.get(k, 33) for k in STATS)
    return {"top": 17.0 + 0.22 * sp,          # 19 to 30 m/s (70 to 108 km/h)
            "accel": 5.0 + 0.10 * ac,         # 6 to 11 m/s^2
            "grip": 6.0 + 0.10 * gr,          # 7 to 12 per second (a slide of 1 m/s is gone in about a tenth)
            "steer": 95.0 + 1.0 * gr}         # 105 to 155 degrees a second


def new_kart(kid, design, s, lateral, heading):
    track_free = {"id": kid, "x": 0.0, "y": 0.0, "yaw": heading, "v": 0.0, "u": 0.0, "charge": 0, "boost": 0,
                  "slip": 0, "lap": 0, "cp": 0, "flags": 0, "seg": 0, "s": s, "lat": lateral}
    return track_free


def place(track, k, s, lateral):
    """Put a kart at s, lateral on the track (the grid, a respawn)."""
    x, y, _ = track.point(s, lateral)
    k.update(x=x, y=y, yaw=track.heading(s), v=0.0, u=0.0, charge=0, boost=0, slip=0, s=s % track.length,
             lat=lateral, seg=track.segment_at(s), flags=k["flags"] & FLAG_FINISHED)


def step(k, inp, dt, track, st):
    """One tick of one kart: the new state. k: the kart, inp: (throttle, steer, buttons), st: stats_of(design)."""
    th, steer, bt = inp
    n = dict(k)
    v, u, yaw = k["v"], k["u"], k["yaw"]
    top, accel, grip, steer_rate = st["top"], st["accel"], st["grip"], st["steer"]
    boost, slip, charge, flags = k["boost"], k["slip"], k["charge"], 0
    if boost:
        top, accel = top * BOOST_SPEED, accel * BOOST_ACCEL
        flags |= FLAG_BOOSTING
    if slip:  # on oil: the tyres have little to say
        grip *= 0.15
        steer_rate *= 0.5
    # drifting: holding DRIFT while steering above a trot. The back steps out (less grip), the kart turns tighter,
    # and a charge builds that pays out as a boost when the drift ends (Mario Kart's mini-turbo)
    drift_dir = 1 if k["flags"] & FLAG_DRIFT_L else -1 if k["flags"] & FLAG_DRIFT_R else 0
    drifting = bool(bt & DRIFT) and v > 7.0 and (drift_dir != 0 or steer != 0)
    if drifting:
        if drift_dir == 0:
            drift_dir = 1 if steer > 0 else -1
        flags |= FLAG_DRIFT_L if drift_dir > 0 else FLAG_DRIFT_R
        charge = min(65535, charge + (5 if steer * drift_dir >= 0.5 else 2))
        grip *= 0.4
    else:
        if charge >= SUPER_TURBO:
            boost = max(boost, SUPER_BOOST)
        elif charge >= MINI_TURBO:
            boost = max(boost, MINI_BOOST)
        charge = 0
        drift_dir = 0
    # speed: the motor pushes towards th * top (the drag term makes full throttle settle at the top speed); the
    # brake bites harder; reverse is slow
    if th >= 0 or v <= 0:
        v += (th * accel - accel * v / top) * dt if th >= 0 else (th * accel * 0.5 - accel * v / top) * dt
    else:
        v -= accel * 1.6 * dt
    v = max(-0.3 * top, min(top, v))
    # steering: a rate that needs some speed to work and eases off at the top, tighter in a drift
    turn = steer * steer_rate * min(1.0, abs(v) / 6.0) * (1.0 - 0.4 * min(1.0, abs(v) / top))
    if drifting:
        turn = turn * 1.3 + drift_dir * 25.0
    if v < 0:
        turn = -turn
    dyaw = turn * dt
    yaw = (yaw + dyaw + 180.0) % 360.0 - 180.0
    # the velocity in the kart's own frame, carried round the turn: part of what was forward is now sideways.
    # The tyres kill the slide, and (arcade, not physics) the pace isn't lost with it: the kart keeps its speed
    # through a turn apart from a scrub, bigger in a drift. Without this a long drift would bleed to a crawl.
    pace = math.hypot(v, u)
    r = math.radians(dyaw)
    c, s_ = math.cos(r), math.sin(r)
    v, u = v * c + u * s_, -v * s_ + u * c
    u *= math.exp(-grip * dt)
    pace *= 1.0 - (0.12 if drifting else 0.03) * dt
    v = math.copysign(math.sqrt(max(0.0, pace * pace - u * u)), v if v else 1.0)
    yr = math.radians(yaw)
    fx, fy = math.cos(yr), math.sin(yr)
    x = k["x"] + (fx * v - fy * u) * dt
    y = k["y"] + (fy * v + fx * u) * dt
    # the track: where we are along it, and the barriers at its edges
    seg, s, lat = track.locate(x, y, k.get("seg"))
    limit = track.half - KART_HALF
    if abs(lat) > limit:  # into the barrier: held at the edge, the slide stopped, speed scrubbed off
        lat = limit if lat > 0 else -limit
        x, y, _ = track.point(s, lat)
        u = 0.0
        v *= max(0.0, 1.0 - 3.0 * dt)
        charge = 0
    # dash pads and oil
    if track.near(track.boosts, s, lat, kart_track.BOOST_RADIUS):
        boost = max(boost, PAD_BOOST)
    if track.near(track.oil, s, lat, kart_track.OIL_RADIUS):
        slip = OIL_TICKS
    n.update(x=x, y=y, yaw=yaw, v=v, u=u, charge=charge, boost=max(0, boost - 1), slip=max(0, slip - 1),
             flags=flags | (k["flags"] & (FLAG_FINISHED | FLAG_WRONG_WAY)), seg=seg, s=s, lat=lat)
    return n


def compare(a, b):
    """How far apart two states of the same kart are, for the window's prediction (metres, with a little for the
    heading): under 5 cm is ignored, see engine.predict.Predictor."""
    if a is None or b is None:
        return math.inf
    dyaw = abs((a["yaw"] - b["yaw"] + 180.0) % 360.0 - 180.0)
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"]) + abs(a["v"] - b["v"]) * 0.05 + dyaw * 0.01


# ---------- the race (server side) ----------

def bump(a, b, reach=BUMP_DISTANCE, slow=0.3):
    """Two karts closer than reach pushed apart, a bounded nudge with no spin, and the faster one losing a little
    speed to the slower (bounded, so nobody is sent flying): one pair of Race.contacts, and what the windows' and the
    pages' prediction does against the other karts (CHANGE 155). Changes both; True when they touched."""
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    d = math.hypot(dx, dy)
    if d >= reach or d < 1e-6:
        return False
    push = (reach - d) / 2
    nx, ny = dx / d, dy / d
    a["x"] -= nx * push
    a["y"] -= ny * push
    b["x"] += nx * push
    b["y"] += ny * push
    a["v"], b["v"] = a["v"] * 0.97 - slow * min(1.0, max(0.0, a["v"] - b["v"])), \
        b["v"] * 0.97 - slow * min(1.0, max(0.0, b["v"] - a["v"]))
    return True


def coast(k, dt):
    """Another kart carried on one tick as it was going (a prediction can't know its keys): CHANGE 155."""
    yr = math.radians(k["yaw"])
    fx, fy, u = math.cos(yr), math.sin(yr), k.get("u", 0.0)
    k["x"] += (fx * k["v"] - fy * u) * dt
    k["y"] += (fy * k["v"] + fx * u) * dt

class Race:
    """Every kart on one track, the countdown, gates, laps, places and bumps between karts."""

    def __init__(self, track, schema, laps=None):
        self.track, self.schema = track, schema
        self.laps = laps or track.laps
        self.karts = {}         # id -> state
        self.designs = {}       # id -> design
        self.stats = {}         # id -> stats_of(design)
        self.tick = 0
        self.phase = FLAGS_GRID
        self.go_tick = None     # the tick the race starts (after the countdown)
        self.finish = {}        # id -> the tick it finished
        self.events = []        # (tick, text)
        self.bumps = []         # (tick, id, other id) this tick, for the windows' sound and sparks
        self.hits = {}          # id -> bumps with another kart since it joined (the missions watch these)
        self.lap_times = {}     # id -> [seconds for each lap completed this race]
        self.lap_start = {}     # id -> the tick its current lap began
        self.practice = True    # a practice (free driving) or a race that counts (the teaching layer reads it)
        self.user_mods = {}     # the engine's user mods switched on (USER_MODS): nothing uses them yet

    @property
    def time(self):
        """The race's clock, in ticks (the teaching layer stamps its events with it, as the race does its own)."""
        return self.tick

    def set_user_mods(self, switches):
        self.user_mods = {k: bool(v) for k, v in (switches or {}).items() if k in USER_MODS}

    def add(self, kid, design):
        design = fit_design(design)
        k = new_kart(kid, design, 0.0, 0.0, 0.0)
        self.karts[kid], self.designs[kid], self.stats[kid] = k, design, stats_of(design)
        self.hits.setdefault(kid, 0)
        self.to_grid()
        return k

    def remove(self, kid):
        for d in (self.karts, self.designs, self.stats, self.finish, self.hits, self.lap_times, self.lap_start):
            d.pop(kid, None)

    def to_grid(self):
        """Everyone back on the grid, in the order they finished last time (or joined)."""
        order = sorted(self.karts, key=lambda i: (self.finish.get(i, 10 ** 9), i))
        for n, kid in enumerate(order):
            k = self.karts[kid]
            s, lat = self.track.grid(n)
            k.update(lap=0, cp=0, flags=0, charge=0)
            place(self.track, k, s, lat)
        self.finish = {}
        self.lap_times, self.lap_start = {}, {}
        self.phase = FLAGS_GRID
        self.go_tick = None

    def start(self):
        """3, 2, 1, GO: nobody moves until go_tick."""
        self.to_grid()
        self.go_tick = self.tick + max(60, int(RULES.get("countdown_seconds", 4.0) / STEP))
        self.phase = FLAGS_RACE
        self.lap_start = {kid: self.go_tick for kid in self.karts}
        self.events.append((self.tick, "On your marks..."))

    def frozen(self):
        return self.phase != FLAGS_RACE or (self.go_tick is not None and self.tick < self.go_tick)

    def countdown(self):
        """Seconds to GO (a float), or None once the race is running."""
        if self.go_tick is None or self.tick >= self.go_tick:
            return None
        return (self.go_tick - self.tick) * STEP

    def step_all(self, inputs):
        """One tick of the whole race. inputs: id -> (throttle, steer, buttons) for the karts driven this tick
        (a kart with none coasts). Returns the new states (also kept in self.karts)."""
        self.bumps = []
        frozen = self.frozen()
        for kid, k in list(self.karts.items()):
            inp = (0.0, 0.0, 0) if frozen or kid in self.finish else inputs.get(kid, (0.0, 0.0, 0))
            if inp[2] & RESPAWN and not frozen:
                self.respawn(k)
                inp = (0.0, 0.0, 0)
            n = step(k, inp, STEP, self.track, self.stats[kid])
            self.karts[kid] = n
        self.contacts()
        for kid, k in self.karts.items():
            self.gates(kid, k)
            k.update(self.schema.quantise(k))  # (the numbers every window will see: start the next tick from them)
        self.tick += 1
        if self.phase == FLAGS_RACE and self.karts and all(kid in self.finish for kid in self.karts):
            self.phase = FLAGS_OVER
            self.events.append((self.tick, "Race over"))
        return self.karts

    def respawn(self, k):
        """Back onto the track at the last gate passed, facing the right way."""
        gate = (k["cp"] - 1) % kart_track.GATES if k["cp"] else kart_track.GATES - 1
        s = self.track.gate_s[gate] + 2.0 if k["cp"] else self.track.grid(0)[0]
        place(self.track, k, s, 0.0)

    def contacts(self):
        """Karts that overlap push each other apart: a bounded nudge, no spin, so a bump online looks the same on
        every screen once the server's word arrives."""
        ids = list(self.karts)
        for i in range(len(ids)):
            a = self.karts[ids[i]]
            for j in range(i + 1, len(ids)):
                b = self.karts[ids[j]]
                if not bump(a, b, RULES.get("bump_distance", BUMP_DISTANCE), RULES.get("bump_slowdown", 0.3)):
                    continue
                self.bumps.append((self.tick, ids[i], ids[j]))
                self.hits[ids[i]] = self.hits.get(ids[i], 0) + 1
                self.hits[ids[j]] = self.hits.get(ids[j], 0) + 1

    def gates(self, kid, k):
        """Gate, lap and finish bookkeeping from where the kart is along the track."""
        t = self.track
        zone = t.gate_zone(k["s"])
        cp = k["cp"]
        if cp == 0:
            if zone == 0 and not self.frozen():
                k["cp"] = 1
        elif cp < kart_track.GATES:
            if zone == cp:
                k["cp"] = cp + 1
        else:  # all gates passed: the start line again is a lap
            if zone == 0:
                k["lap"] += 1
                k["cp"] = 1
                began = self.lap_start.get(kid, self.go_tick if self.go_tick is not None else self.tick)
                self.lap_times.setdefault(kid, []).append(round((self.tick - began) * STEP, 2))
                self.lap_start[kid] = self.tick
                if k["lap"] >= self.laps and kid not in self.finish:
                    self.finish[kid] = self.tick
                    k["flags"] |= FLAG_FINISHED
                    self.events.append((self.tick, f"{self.designs[kid]['name']} finished "
                                                   f"{self.ordinal(len(self.finish))}"))
        # the wrong way: in the zone before the one just passed
        behind = (k["cp"] - 2) % kart_track.GATES
        if k["cp"] >= 2 and zone == behind and k["v"] > 1.0:
            k["flags"] |= FLAG_WRONG_WAY
        else:
            k["flags"] &= ~FLAG_WRONG_WAY

    @staticmethod
    def ordinal(n):
        return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

    def places(self):
        """Kart ids from first to last: finishers in finishing order, then by progress round the track."""
        def key(kid):
            k = self.karts[kid]
            if kid in self.finish:
                return (0, self.finish[kid], 0.0)
            return (1, 0, -self.track.progress(k["lap"], k["cp"], k["s"]))
        return sorted(self.karts, key=key)

    def results(self):
        """(name, laps, time in seconds or None) in finishing order."""
        out = []
        for kid in self.places():
            k = self.karts[kid]
            t = None if kid not in self.finish or self.go_tick is None else (self.finish[kid] - self.go_tick) * STEP
            out.append((self.designs[kid]["name"], k["lap"], t))
        return out
