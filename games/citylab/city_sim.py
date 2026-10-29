"""City Lab's step: a person on foot, a car and a robot, the same on the server and in every window (CHANGE 194).

Kart Lab's rule, kept: the step is a few lines of arithmetic on a small dict, pure and deterministic (kart_math's
sin, cos, exp, hypot and atan2), and both ends round the result to the wire's precision each tick, so a window
predicts the thing it controls (its person, or the car it drives) and the server's corrections are only ever real.
Everything between things (bumps, hits, getting in and out of cars, the jobs) is in World, on the server only.

One record kind on the wire (SCHEMA_FIELDS) for all three; what a thing is comes from its id: people 0 to 31, cars
32 to 127, robots 128 to 191. The input is engine.wire's (throttle, steer, buttons). On foot throttle and steer are
the way to move in the world's frame (x east, y north; the window works it out from the keys and the camera, so
the server never knows the camera) and the person faces the way they go; in a car they are the pedals and the wheel.

The design (the engine's nested shape, as Fight Lab's): name, colour (the car's paint, the built fighter's colour),
body (the car: coupe, supercar, rally or muscle), look (the person: woman, man, robin, human or robot: Fight Lab's
bodies), points speed / acceleration / grip for the car (100 between them, 10 to 60 each), no settings.
"""
import math

import city_version  # noqa: F401  (the engine and the other games' folders on the path)
import kart_math as kmath
import city_map

STEP = 1 / 60
SIM_VERSION = 1  # raise with any change meant to change the step's numbers (city_sim_test.py's golden file)
POINTS_TOTAL, STAT_MIN, STAT_MAX = 100, 10, 60
STATS = ("speed", "acceleration", "grip")
SETTINGS = {}  # (no sliders: the engine's limits and garage expect the name)
FULL_STAT, FULL_POINTS_TOTAL = (STAT_MIN, STAT_MAX), POINTS_TOTAL
STAT_NOTES = {"speed": "points for your car's top speed", "acceleration": "points for your car's acceleration",
              "grip": "points for your car's grip: how fast a slide dies, and how sharply it steers"}
LIMITS = None

BODIES = ("coupe", "supercar", "rally", "muscle")        # the cars (car_models.py, Kart Lab's)
LOOKS = ("woman", "man", "robin", "human", "robot")      # the person (Fight Lab's bodies)
NAME_MAX = 12

# ids: what a thing is
PEOPLE, CARS, ROBOTS = range(0, 32), range(32, 128), range(128, 192)
MAX_PEOPLE, MAX_CARS, MAX_ROBOTS = 32, 96, 64


def kind_of(tid):
    return "person" if tid < 32 else "car" if tid < 128 else "robot"


# the input's buttons (engine.wire's byte)
DRIFT, ACTION, RESPAWN, LAUNCH, HANDBRAKE = 1, 2, 4, 8, 16   # (a car: as Kart Lab's; on foot DRIFT is run, HANDBRAKE is block)
PUNCH, KICK, JUMP = 32, 64, 128
RUN, BLOCK = DRIFT, HANDBRAKE

# the record's flags byte, by kind
# a person
FLAG_RUN, FLAG_AIR, FLAG_BLOCK, FLAG_DOWN, FLAG_PARCEL, FLAG_HURT = 1, 2, 4, 8, 16, 32
# a car (Kart Lab's where they are the same, so the car pictures are shared)
FLAG_DRIFT_L, FLAG_DRIFT_R, FLAG_WRECKED, FLAG_CAR_AIR, FLAG_BOOSTING, FLAG_BRAKING, FLAG_WHEELSPIN, FLAG_HANDBRAKE = 1, 2, 4, 8, 16, 32, 64, 128
# a robot
FLAG_CROSS, FLAG_ROGUE, FLAG_OFF, FLAG_ZAP = 1, 2, 4, 8

# the moves (a person's "move" field)
MOVE_NONE, MOVE_PUNCH, MOVE_KICK, MOVE_BLOCK, MOVE_DOWN, MOVE_GETUP, MOVE_HURT = 0, 1, 2, 3, 4, 5, 6
MOVE_TICKS = {MOVE_PUNCH: 18, MOVE_KICK: 26, MOVE_DOWN: 150, MOVE_GETUP: 40, MOVE_HURT: 14}
HIT_TICK = {MOVE_PUNCH: 6, MOVE_KICK: 10}          # the tick of the move that lands
REACH = {MOVE_PUNCH: 1.4, MOVE_KICK: 1.8}
HIT = {MOVE_PUNCH: 8, MOVE_KICK: 14}               # off a robot's power, or a person's health
HIT_ANGLE = 60.0                                   # degrees either side of the facing
BLOCK_SHARE = 0.5                                  # a block halves what lands
HEALTH, DOWN_HEALTH = 100, 50
REGEN_TICKS = 120                                  # a point of health back every 2 s
ZAP, ZAP_PUSH, ZAP_GRACE = 6, 4.0, 45              # a robot's zap: health off, the shove (m/s), ticks before the next

# a person
WALK, RUN_SPEED, TURN_RATE = 3.2, 6.5, 540.0
PERSON_R = 0.35
JUMP_V, GRAVITY = 5.6, 20.0                        # a hop of 0.8 m (arcade gravity)
KNOCK_SPEED = 4.0                                  # a car this fast knocks a person down
PUSH_PERSON = 0.7                                  # people pushed apart closer than this

# a car (Kart Lab's numbers, kart_sim.py)
CAR_R = 1.0
CAR_HALF_LEN = 2.2
ROLL = 0.6
HB_GRIP, HB_BRAKE, HB_TURN, HB_SCRUB = 0.25, 1.2, 1.5, 0.2
LAUNCH_SPEED, LAUNCH_ACCEL, LAUNCH_GRIP, LAUNCH_SPIN = 6.0, 0.35, 0.3, 150.0
PAVE_DRAG, PAVE_GRIP = 0.25, 0.75                  # the pavement: a kerb's rumble
GRASS_DRAG, GRASS_ACCEL, GRASS_GRIP = 1.0, 0.5, 0.6
KERB_BUMP = 0.9                                    # the speed a car keeps crossing a kerb
DAMAGE_MAX = 10000
HIT_SPEED, HIT_WALL, HIT_CAR = 2.0, 900, 1100
BUMP_GRACE = 60
WRECK_SPEED = 4.0                                  # a wrecked car crawls
REPAIR_TICK, REPAIR_GARAGE = 1, 200                # mended a little by itself, fast on the garage's forecourt under 2 m/s
GARAGE_STOP = 2.0
STUNT_LEAST = 6.0                                  # a jump this long pays (metres)
ENTER_REACH = 2.5                                  # how close to a car to get in
EXIT_SPEED = 3.0
SEAT = (0.0, 0.0)                                  # the driver's seat, in the car's frame (x forward, y left)

# a robot (Robot Lab's shape and pace)
ROBOT_R = 0.95  # (a robot is 1.6 m long with its weapon out front: a person stands clear of it)
ROBOT_TOP, ROBOT_ACCEL, ROBOT_TURN, ROBOT_GRIP = 6.4, 3.5, 110.0, 8.0
POWER = 100
CROSS_REACH = 6.0                                  # a robot this close to a person on foot gets cross
REBOOT_TICKS = 360                                 # a robot powered down is back in 6 s
SPIN_RATE, SPIN_DECAY = 900.0, 400.0               # degrees a second the weapon winds up, and down

# the wire record for everything (engine.wire): both ends round their numbers to this every tick
SCHEMA_FIELDS = [("x", "i", 100), ("y", "i", 100), ("z", "h", 100), ("vz", "h", 100), ("yaw", "h", 10),
                 ("v", "h", 100), ("u", "h", 100), ("hp", "B", 1), ("flags", "B", 1), ("link", "B", 1),
                 ("move", "B", 1), ("mp", "B", 1), ("steer", "b", 100), ("dmg", "H", 1), ("job", "B", 1),
                 ("jp", "B", 1), ("cash", "H", 1), ("aux", "H", 1), ("lk", "B", 1), ("bg", "B", 1)]

DEFAULT_RULES = {"traffic": 6, "robots": 6, "parked": 10, "delivery_pay": 50, "taxi_fare": 40, "race_pay": 100,
                 "roundup_pay": 15, "chip_pay": 10, "bump_distance": 2.4, "bump_slowdown": 0.3, "bump_transfer": 0.7}
RULES = dict(DEFAULT_RULES)
USER_MODS = {}


# ---------- the design ----------
def default_design(name="Driver", colour=(220, 60, 50), body="coupe", look="woman"):
    return {"name": name, "colour": list(colour), "body": body, "look": look,
            "points": {"speed": 34, "acceleration": 33, "grip": 33}, "settings": {}}


def schema():
    """The design as variables, in the HUD's groups (the garage and the code panel)."""
    from engine.schema import Var
    return ([Var(k, ("points", k), "int", "points", tool=k, note=STAT_NOTES[k]) for k in STATS] +
            [Var("driver_name", ("name",), "str", "strings", tool="name_and_colour",
                 note="a string: text made of chars", max_len=NAME_MAX),
             Var("car", ("body",), "choice", "strings", tool="name_and_colour", options=lambda ctx: list(BODIES),
                 valid=lambda ctx: list(BODIES), note="coupe, supercar, rally or muscle (they all drive as their points say)",
                 per_row=4, step=0.17),
             Var("look", ("look",), "choice", "strings", tool="name_and_colour", options=lambda ctx: list(LOOKS),
                 valid=lambda ctx: list(LOOKS), note="who walks the streets: woman, man, robin, human or robot",
                 per_row=5, step=0.14),
             Var("colour", ("colour",), "rgb", "lists", tool="name_and_colour", note="red, green, blue: 0 to 255")])


design_schema = schema


def _limits():
    global LIMITS
    if LIMITS is None:
        from engine.limits import Spec
        LIMITS = Spec(SETTINGS, {}, STATS, (STAT_MIN, STAT_MAX), FULL_STAT, POINTS_TOTAL, FULL_POINTS_TOTAL)
    return LIMITS


def default_limits():
    return _limits().default()


def code_limits(limits):
    return _limits().code_room(limits)


def full_limits():
    return _limits().full()


def clean_limits(new, old=None):
    return _limits().clean(new, old)


def check_design(d, limits=None):
    """Problems with a design (empty = fine), held to the learners' limits (or full_limits() for the teacher's)."""
    if not isinstance(d, dict):
        return ["the design must be a dictionary"]
    problems = []
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        problems.append("name must be some text")
    elif len(d["name"]) > NAME_MAX:
        problems.append(f"name can be at most {NAME_MAX} characters")
    c = d.get("colour")
    if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                                                         for v in c)):
        problems.append("colour must be three whole numbers from 0 to 255, [red, green, blue]")
    if d.get("body") not in BODIES:
        problems.append(f"body must be one of {', '.join(BODIES)}")
    if d.get("look") not in LOOKS:
        problems.append(f"look must be one of {', '.join(LOOKS)}")
    limits = limits or default_limits()
    pts = d.get("points") if isinstance(d.get("points"), dict) else {}
    for k in STATS:
        lo, hi = limits["points"][k]
        v = pts.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            problems.append(f"{k} must be a whole number from {lo} to {hi}")
    vals = [pts.get(k) for k in STATS]
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals) and sum(vals) > limits["points_total"]:
        problems.append(f"{sum(vals)} points used: the most you can spend is {limits['points_total']}")
    return problems


def fit_design(d, limits=None):
    """A design inside the rules (each point 10 to 60, 100 in all, a real body, look, colour and name)."""
    out = {"name": str(d.get("name", "Driver"))[:NAME_MAX] or "Driver", "settings": {}}
    c = d.get("colour") or [220, 60, 50]
    out["colour"] = [max(0, min(255, int(v))) for v in list(c)[:3]] if len(list(c)) >= 3 else [220, 60, 50]
    out["body"] = d.get("body") if d.get("body") in BODIES else "coupe"
    out["look"] = d.get("look") if d.get("look") in LOOKS else "woman"
    pts = d.get("points") if isinstance(d.get("points"), dict) else {k: d.get(k, 33) for k in STATS}
    if limits is not None:
        fitted = _limits().fit({"points": {k: pts.get(k, 33) for k in STATS}, "settings": {}}, limits)
        out["points"] = {k: int(fitted["points"][k]) for k in STATS}
        return out
    vals = []
    for k in STATS:
        try:
            vals.append(max(STAT_MIN, min(STAT_MAX, int(pts.get(k, 33)))))
        except (TypeError, ValueError):
            vals.append(33)
    over = sum(vals) - POINTS_TOTAL
    i = 0
    while over != 0 and i < 300:
        k = i % 3
        if over > 0 and vals[k] > STAT_MIN:
            vals[k] -= 1
            over -= 1
        elif over < 0 and vals[k] < STAT_MAX:
            vals[k] += 1
            over += 1
        i += 1
    out["points"] = dict(zip(STATS, vals))
    return out


def stats_of(design):
    """What the points buy the car (Kart Lab's sums): top speed m/s, acceleration m/s^2, grip, steering deg/s."""
    pts = design.get("points", design)
    sp, ac, gr = (pts.get(k, 33) for k in STATS)
    return {"top": 17.0 + 0.22 * sp, "accel": 5.0 + 0.10 * ac, "grip": 6.0 + 0.10 * gr, "steer": 95.0 + 1.0 * gr}


# the computer's cars' paint: the colours of real cars (silver, black, red, blue, white, grey, green, gold)
TRAFFIC_COLOURS = [(200, 200, 205), (40, 40, 48), (150, 30, 30), (30, 60, 140), (220, 220, 225), (90, 90, 95),
                   (20, 110, 70), (200, 160, 40)]


# ---------- the robots' designs (Robot Lab's shape, so its models draw them) ----------
ROBOT_DESIGNS = [
    {"name": "PATROL", "colour": [90, 140, 220], "weapon": "wedge", "points": {"speed": 30, "attack": 15, "armour": 30, "control": 25},
     "settings": {"forward_speed": 80, "reverse_speed": 60, "turn_speed": 70, "acceleration": 70, "size": 100}},
    {"name": "SWEEPER", "colour": [230, 170, 40], "weapon": "spinner", "points": {"speed": 25, "attack": 30, "armour": 20, "control": 25},
     "settings": {"forward_speed": 70, "reverse_speed": 60, "turn_speed": 80, "acceleration": 60, "size": 100}},
    {"name": "PORTER", "colour": [120, 200, 120], "weapon": "drum", "points": {"speed": 35, "attack": 10, "armour": 35, "control": 20},
     "settings": {"forward_speed": 90, "reverse_speed": 60, "turn_speed": 60, "acceleration": 80, "size": 110}},
    {"name": "WARDEN", "colour": [200, 80, 80], "weapon": "hammer", "points": {"speed": 20, "attack": 35, "armour": 25, "control": 20},
     "settings": {"forward_speed": 70, "reverse_speed": 50, "turn_speed": 70, "acceleration": 60, "size": 100}},
]


def robot_design(n):
    d = dict(ROBOT_DESIGNS[n % len(ROBOT_DESIGNS)])
    d["points"], d["settings"] = dict(d["points"]), dict(d["settings"])
    if n >= len(ROBOT_DESIGNS):
        d["name"] = f"{d['name']} {n // len(ROBOT_DESIGNS) + 1}"
    return d


def robot_stats(design):
    """Robot Lab's pace, roughly (lab_sim.build_stats): top m/s, accel, turn deg/s from the design's settings."""
    s = design.get("settings", {})
    return {"top": ROBOT_TOP * s.get("forward_speed", 80) / 80.0, "accel": ROBOT_ACCEL * s.get("acceleration", 70) / 70.0,
            "turn": ROBOT_TURN * s.get("turn_speed", 70) / 70.0, "grip": ROBOT_GRIP}


# ---------- the states ----------
def new_thing(tid, x=0.0, y=0.0, yaw=0.0):
    return {"id": tid, "x": x, "y": y, "z": 0.0, "vz": 0.0, "yaw": yaw, "v": 0.0, "u": 0.0, "hp": 0, "flags": 0,
            "link": 0, "move": 0, "mp": 0, "steer": 0.0, "dmg": 0, "job": 0, "jp": 0, "cash": 0, "aux": 0, "lk": 0, "bg": 0}


def new_person(pid, x, y, yaw):
    p = new_thing(pid, x, y, yaw)
    p["hp"] = HEALTH
    return p


def new_car(cid, x, y, yaw):
    return new_thing(cid, x, y, yaw)


def new_robot(rid, x, y, yaw):
    r = new_thing(rid, x, y, yaw)
    r["hp"] = POWER
    return r


def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


def facing(yaw):
    """The unit vector a yaw points along (the system's maths: for the server's bookkeeping, not the steps)."""
    yr = math.radians(yaw)
    return math.cos(yr), math.sin(yr)


def facing_exact(yaw):
    """The same with kart_math, for the steps a window predicts."""
    yr = math.radians(yaw)
    return kmath.cos(yr), kmath.sin(yr)


# ---------- a person ----------
def step_person(p, inp, dt, city):
    """One tick of a person on foot. inp: (move x, move y, buttons) in the world's frame. In a car (link) only the
    counters tick: World puts them where the car is."""
    mx, my, bt = inp
    n = dict(p)
    move, mp, flags = p["move"], p["mp"], 0
    hp = p["hp"]
    # the counters
    if n["lk"]:
        n["lk"] -= 1
    if n["bg"]:
        n["bg"] -= 1
    # health creeps back (the aux field counts the ticks; a parcel held is the PARCEL flag, kept in flags by World)
    regen, chips = p["aux"] & 255, p["aux"] & ~255
    if hp < HEALTH and hp > 0 and not p["link"]:
        regen += 1
        if regen >= REGEN_TICKS:
            regen, hp = 0, hp + 1
    n["aux"] = chips | regen
    carried = p["flags"] & FLAG_PARCEL
    if p["link"]:  # in a car: no moving about
        n.update(move=0, mp=0, flags=carried, hp=hp, v=0.0, u=0.0, z=0.0, vz=0.0, steer=0.0)
        return n
    # a move running
    if move:
        mp += 1
        if move == MOVE_BLOCK:
            if not (bt & BLOCK):
                move, mp = MOVE_NONE, 0
        elif mp >= MOVE_TICKS.get(move, 1):
            if move == MOVE_DOWN:
                move, mp = MOVE_GETUP, 0
                hp = max(hp, DOWN_HEALTH)
            else:
                move, mp = MOVE_NONE, 0
    if not move or move == MOVE_BLOCK:
        if (bt & PUNCH) and not move:
            move, mp = MOVE_PUNCH, 0
        elif (bt & KICK) and not move:
            move, mp = MOVE_KICK, 0
        elif (bt & BLOCK) and not move and p["z"] == 0.0:
            move, mp = MOVE_BLOCK, 0
    stuck = move in (MOVE_PUNCH, MOVE_KICK, MOVE_DOWN, MOVE_GETUP, MOVE_HURT)
    blocking = move == MOVE_BLOCK
    if blocking:
        flags |= FLAG_BLOCK
    if move in (MOVE_DOWN,):
        flags |= FLAG_DOWN
    if move == MOVE_HURT:
        flags |= FLAG_HURT
    # moving
    mag = kmath.hypot(mx, my)
    want = 0.0
    if not stuck and mag > 0.1:
        dx, dy = mx / mag, my / mag
        mag = min(1.0, mag)
        want = mag * (RUN_SPEED if (bt & RUN) and not blocking else WALK)
        if blocking:
            want *= 0.5
        if (bt & RUN) and not blocking:
            flags |= FLAG_RUN
        aim = math.degrees(kmath.atan2(my, mx))
        d = wrap(aim - p["yaw"])
        turn = max(-TURN_RATE * dt, min(TURN_RATE * dt, d))
        yaw = wrap(p["yaw"] + turn)
    else:
        yaw = p["yaw"]
        dx, dy = facing_exact(yaw)
    v = p["v"]
    rate = 14.0 if p["z"] == 0.0 else 2.0
    v += (want - v) * min(1.0, rate * dt)
    if stuck and p["z"] == 0.0:
        v *= max(0.0, 1.0 - 12.0 * dt)
    if v < 0.02:
        v = 0.0
    # a jump
    z, vz = p["z"], p["vz"]
    if (bt & JUMP) and z == 0.0 and vz == 0.0 and not stuck and not blocking:
        vz = JUMP_V
    if z > 0.0 or vz > 0.0:
        vz -= GRAVITY * dt
        z += vz * dt
        if z <= 0.0:
            z, vz = 0.0, 0.0
        else:
            flags |= FLAG_AIR
    x = p["x"] + dx * v * dt
    y = p["y"] + dy * v * dt
    x, y, _hit = city.collide(x, y, PERSON_R)
    n.update(x=x, y=y, z=z, vz=vz, yaw=yaw, v=v, u=0.0, hp=hp, move=move, mp=mp, flags=flags | carried, steer=0.0)
    return n


# ---------- a car ----------
def car_velocity(k):
    yr = math.radians(k["yaw"])
    c, s = kmath.cos(yr), kmath.sin(yr)
    return c * k["v"] - s * k["u"], s * k["v"] + c * k["u"]


def step_car(k, inp, dt, city, st, driven=True):
    """One tick of a car: Kart Lab's arcade step with the city for a track. inp: (throttle, steer, buttons); st:
    stats_of(design). driven False: nobody at the wheel (it rolls to a stop)."""
    th, steer, bt = inp if driven else (0.0, 0.0, 0)
    n = dict(k)
    v, u, yaw = k["v"], k["u"], k["yaw"]
    top, accel, grip, steer_rate = st["top"], st["accel"], st["grip"], st["steer"]
    flags = 0
    if n["bg"]:
        n["bg"] -= 1
    if n["lk"]:
        n["lk"] -= 1
    # damage: the engine loses speed and pull, the steering goes heavy; a wreck crawls
    d = min(DAMAGE_MAX, k["dmg"]) / DAMAGE_MAX
    wrecked = k["dmg"] >= DAMAGE_MAX
    top *= 1.0 - 0.3 * d
    accel *= 1.0 - 0.35 * d
    steer_rate *= 1.0 - 0.25 * d
    if wrecked:
        top, flags = min(top, WRECK_SPEED), flags | FLAG_WRECKED
    # what is under the wheels (where the last tick left it)
    surf = city.surface(k["x"], k["y"])
    ground = city.ramp_height(k["x"], k["y"]) if k["z"] > 0.0 else 0.0  # (climbing a ramp is on the ground)
    airborne = k["vz"] != 0.0 or k["z"] > ground + 0.01
    if surf == "pave" or surf == "court":
        grip *= PAVE_GRIP
    elif surf == "grass" or surf == "quay":
        grip *= GRASS_GRIP
        accel *= GRASS_ACCEL
    if airborne:
        accel, grip = 0.0, grip * 0.2
        flags |= FLAG_CAR_AIR
    if th < 0:
        flags |= FLAG_BRAKING
    hb = bool(bt & HANDBRAKE) and abs(v) > 0.5 and not airborne
    launch = bool(bt & LAUNCH) and th > 0 and abs(v) < LAUNCH_SPEED and not hb and not airborne
    if hb:
        flags |= FLAG_HANDBRAKE | FLAG_BRAKING
        grip *= HB_GRIP
    if launch:
        flags |= FLAG_WHEELSPIN
        accel *= LAUNCH_ACCEL
        grip *= LAUNCH_GRIP
    drift_dir = 1 if k["flags"] & FLAG_DRIFT_L else -1 if k["flags"] & FLAG_DRIFT_R else 0
    drifting = bool(bt & DRIFT) and v > 7.0 and (drift_dir != 0 or steer != 0) and not hb and not airborne
    if drifting:
        if drift_dir == 0:
            drift_dir = 1 if steer > 0 else -1
        flags |= FLAG_DRIFT_L if drift_dir > 0 else FLAG_DRIFT_R
        grip *= 0.4
    else:
        drift_dir = 0
    # speed
    if hb:
        v = math.copysign(max(0.0, abs(v) - accel * HB_BRAKE * dt), v)
    elif th >= 0 or v <= 0:
        v += (th * accel - accel * v / top) * dt if th >= 0 else (th * accel * 0.5 - accel * v / top) * dt
    else:
        v -= accel * 1.6 * dt
    if th == 0 and not hb:
        v = math.copysign(max(0.0, abs(v) - ROLL * dt), v)
    if not airborne:
        if surf == "pave" or surf == "court":
            v *= max(0.0, 1.0 - PAVE_DRAG * dt)
        elif surf == "grass" or surf == "quay":
            v *= max(0.0, 1.0 - GRASS_DRAG * dt)
    v = max(-0.3 * top, min(top, v))
    # steering
    turn = max(-1.0, min(1.0, steer)) * steer_rate * min(1.0, abs(v) / 6.0) * (1.0 - 0.4 * min(1.0, abs(v) / top))
    if drifting:
        turn = turn * 1.3 + drift_dir * 25.0
    if hb:
        turn *= HB_TURN
    if v < 0:
        turn = -turn
    if launch and steer != 0:
        turn = max(-1.0, min(1.0, steer)) * LAUNCH_SPIN
    if airborne:
        turn = 0.0
    dyaw = turn * dt
    yaw = wrap(yaw + dyaw)
    pace = kmath.hypot(v, u)
    r = math.radians(dyaw)
    c, s_ = kmath.cos(r), kmath.sin(r)
    v, u = v * c + u * s_, -v * s_ + u * c
    u *= kmath.exp(-grip * dt)
    pace *= 1.0 - (HB_SCRUB if hb else 0.12 if drifting else 0.03) * dt
    v = math.copysign(math.sqrt(max(0.0, pace * pace - u * u)), v if v else 1.0)
    yr = math.radians(yaw)
    fx, fy = kmath.cos(yr), kmath.sin(yr)
    x = k["x"] + (fx * v - fy * u) * dt
    y = k["y"] + (fy * v + fx * u) * dt
    # the kerb: a bump as it is crossed
    if not airborne and city.kerb_between(k["x"], k["y"], x, y):
        v *= KERB_BUMP
        u *= KERB_BUMP
    # the buildings, the posts, the city's edge: held at them, the slide stopped, damage over HIT_SPEED into them
    cx, cy, hit = city.collide(x, y, CAR_R)
    into = 0.0
    if hit:
        px, py = cx - x, cy - y
        pd = kmath.hypot(px, py)
        if pd > 1e-9:
            nx, ny = px / pd, py / pd
            wx, wy = fx * v - fy * u, fy * v + fx * u
            into = -(wx * nx + wy * ny)
            if into > 0.0:
                if into > HIT_SPEED and not n["bg"]:
                    n["dmg"] = min(DAMAGE_MAX, k["dmg"] + int((into - HIT_SPEED) * HIT_WALL))
                    n["bg"] = BUMP_GRACE
                wx += nx * into
                wy += ny * into
                v = wx * fx + wy * fy
                u = -wx * fy + wy * fx
                v *= max(0.0, 1.0 - 3.0 * dt)
        x, y = cx, cy
    # the ramps and the air
    z, vz = k["z"], k["vz"]
    ramp = city.ramp_height(x, y)
    if airborne:
        vz -= GRAVITY * dt
        z += vz * dt
        if z <= ramp:
            z, vz = ramp, 0.0
    else:
        was = ground
        if ramp > 0.0:
            z = ramp
        elif was > 0.3 and v > 2.0:  # off the lip: a hop
            vz = v * city_map.RAMP_H / city_map.RAMP_LEN * 1.6
            z = was + vz * dt
            flags |= FLAG_CAR_AIR
        else:
            z = 0.0
    # mending: a little by itself, fast on the garage's forecourt stopped
    at_garage = abs(v) < GARAGE_STOP and city.in_zone("garage", x, y)
    mend = REPAIR_GARAGE if at_garage else 0 if wrecked else REPAIR_TICK  # (a wreck stays one until the garage mends it)
    if n["dmg"] and into <= HIT_SPEED:
        n["dmg"] = max(0, n["dmg"] - mend)
    n.update(x=x, y=y, z=z, vz=vz, yaw=yaw, v=v, u=u, flags=flags, steer=steer if driven else 0.0)
    return n


def coast_car(k, dt):
    """Another car carried on as it was going (a prediction can't know its keys): Kart Lab's coast."""
    steer, rate = k.get("steer", 0.0), k.get("rate", 0.0)
    if steer and rate:
        v, top = k["v"], k.get("top", 25.0)
        turn = steer * rate * min(1.0, abs(v) / 6.0) * (1.0 - 0.4 * min(1.0, abs(v) / top))
        k["yaw"] += -turn * dt if v < 0 else turn * dt
    yr = math.radians(k["yaw"])
    fx, fy, u = kmath.cos(yr), kmath.sin(yr), k.get("u", 0.0)
    k["x"] += (fx * k["v"] - fy * u) * dt
    k["y"] += (fy * k["v"] + fx * u) * dt


# ---------- a robot ----------
def step_robot(r, inp, dt, city, st):
    """One tick of a robot: a drive step (throttle, steer, buttons: ACTION spins the weapon up)."""
    th, steer, bt = inp
    n = dict(r)
    flags = r["flags"] & (FLAG_ROGUE | FLAG_CROSS)
    if n["bg"]:
        n["bg"] -= 1
    if n["lk"]:
        n["lk"] -= 1
    off = r["hp"] <= 0
    spin = r["aux"]
    if off:  # powered down: still, winding down, rebooting
        flags |= FLAG_OFF
        n["mp"] = min(255, r["mp"] + 1)
        v = r["v"] * max(0.0, 1.0 - 4.0 * dt)
        spin = max(0, int(spin - SPIN_DECAY * dt))
        hp = POWER if n["mp"] >= min(255, REBOOT_TICKS) else 0
        if hp:
            n["mp"], flags = 0, flags & ~FLAG_OFF
        n.update(v=v if abs(v) > 0.02 else 0.0, u=0.0, hp=hp, aux=spin, flags=flags, steer=0.0)
        return n
    top, accel, turn_rate, grip = st["top"], st["accel"], st["turn"], st["grip"]
    want = max(-1.0, min(1.0, th)) * (top if th > 0 else top * 0.75)
    v = r["v"] + max(-accel * dt, min(accel * dt, want - r["v"]))
    if th == 0:
        v = math.copysign(max(0.0, abs(v) - 2.0 * dt), v)
    yaw = wrap(r["yaw"] + max(-1.0, min(1.0, steer)) * turn_rate * dt)
    u = r["u"] * math.exp(-grip * dt)
    fx, fy = facing(yaw)
    x = r["x"] + (fx * v - fy * u) * dt
    y = r["y"] + (fy * v + fx * u) * dt
    x, y, hit = city.collide(x, y, ROBOT_R)
    if hit:
        v *= 0.5
        u = 0.0
    if bt & ACTION:
        spin = min(65535, int(spin + SPIN_RATE * dt))
    else:
        spin = max(0, int(spin - SPIN_DECAY * dt))
    n.update(x=x, y=y, yaw=yaw, v=v if abs(v) > 0.02 else 0.0, u=u, aux=spin, flags=flags, steer=max(-1.0, min(1.0, steer)))
    return n


def compare(a, b):
    """How far apart two states of the same thing are, for the prediction: metres, with a little for the heading.
    What only the server decides (a knockdown, a hit, getting in, the pay, the damage) counts as 1: enough to take
    the server's record (the position hardly moves, so nothing jumps), where it would otherwise never be put right."""
    if a is None or b is None:
        return math.inf
    dyaw = abs(wrap(a["yaw"] - b["yaw"]))
    differ = any(a[k] != b[k] for k in ("move", "link", "hp", "cash", "dmg", "aux", "job"))
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"]) + abs(a["v"] - b["v"]) * 0.05 + dyaw * 0.01 + (1.0 if differ else 0.0)


# ---------- between things (the server, and a window's guess about the cars it knows) ----------
def bump_cars(a, b, reach, slow, transfer):
    """Two cars closer than reach pushed apart, the speed they close at passed from the one behind to the one in front
    (Kart Lab's bump), damage over HIT_SPEED. Changes both; True when they touched."""
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    d = math.hypot(dx, dy)
    if d >= reach or d < 1e-6:
        return False
    push = (reach - d) / 2
    nx, ny = dx / d, dy / d
    va, vb = car_velocity(a), car_velocity(b)
    closing = (va[0] - vb[0]) * nx + (va[1] - vb[1]) * ny
    if closing > HIT_SPEED + 1.0:
        amount = int((closing - HIT_SPEED - 1.0) * HIT_CAR)
        for k in (a, b):
            if not k.get("bg"):
                k["dmg"] = min(DAMAGE_MAX, k["dmg"] + amount)
                k["bg"] = BUMP_GRACE
    a["x"] -= nx * push
    a["y"] -= ny * push
    b["x"] += nx * push
    b["y"] += ny * push
    if closing > 0.0:
        dv = closing * transfer
        ya, yb = math.radians(a["yaw"]), math.radians(b["yaw"])
        ca, sa, cb, sb = math.cos(ya), math.sin(ya), math.cos(yb), math.sin(yb)
        a["v"] -= dv * (ca * nx + sa * ny)
        a["u"] = a["u"] - dv * (-sa * nx + ca * ny)
        b["v"] += dv * (cb * nx + sb * ny)
        b["u"] = b["u"] + dv * (-sb * nx + cb * ny)
        rub = slow * min(1.0, closing)
        if a["v"] > b["v"]:
            a["v"] -= rub
        else:
            b["v"] -= rub
    return True


def push_apart(a, b, reach):
    """Two things on foot (people, robots) pushed apart, no speed exchanged. True when they touched."""
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
    return True


def in_reach(p, t, reach):
    """Is thing t within reach of person p, ahead of them (HIT_ANGLE either side)?"""
    dx, dy = t["x"] - p["x"], t["y"] - p["y"]
    d = math.hypot(dx, dy)
    if d > reach + 0.5 or d < 1e-6:
        return False
    ang = wrap(math.degrees(math.atan2(dy, dx)) - p["yaw"])
    return abs(ang) <= HIT_ANGLE


def knock_down(p, ticks=None):
    p["move"], p["mp"] = MOVE_DOWN, 0
    p["flags"] = (p["flags"] & FLAG_PARCEL) | FLAG_DOWN
    p["v"] = 0.0
    if ticks is not None:
        p["mp"] = max(0, MOVE_TICKS[MOVE_DOWN] - ticks)


class World:
    """Everyone, every car and every robot in one city; the bumps, the hits, getting in and out; the jobs are
    city_jobs.Jobs, which World steps after the things. Server side."""

    def __init__(self, city, schema):
        self.city, self.schema = city, schema
        self.people, self.cars, self.robots = {}, {}, {}   # id -> state
        self.designs = {}       # id -> design (people: the player's; cars: a kart-shaped design; robots: Robot Lab's)
        self.stats = {}         # car id -> stats_of(design); robot id -> robot_stats
        self.tick = 0
        self.events = []        # (tick, text)
        self.bumps = []         # (tick, id, other) this tick
        self.hits = {}          # person id -> hits taken and given since joining (the teaching layer)
        self.landed = {}        # person id -> punches and kicks that landed
        self.stunts = {}        # car id -> (took off at x, y, tick) while airborne
        self.jobs = None        # city_jobs.Jobs
        self.practice = True
        self.user_mods = {}
        self.damage = True
        self.units = {}
        self.chips_found = {}   # person id -> count found this session (the teaching layer)
        self._next_car = CARS.start
        self._next_robot = ROBOTS.start

    @property
    def time(self):
        return self.tick

    def things(self):
        """Every record, for the snapshot."""
        return list(self.people.values()) + list(self.cars.values()) + list(self.robots.values())

    def find(self, tid):
        return self.people.get(tid) or self.cars.get(tid) or self.robots.get(tid)

    def set_user_mods(self, switches):
        self.user_mods = {k: bool(v) for k, v in (switches or {}).items() if k in USER_MODS}

    # ---------- joining ----------
    def add_person(self, pid, design):
        design = fit_design(design)
        s = self.city.spawns[pid % len(self.city.spawns)]
        p = new_person(pid, s[0], s[1], s[2])
        self.people[pid], self.designs[pid] = p, design
        self.hits.setdefault(pid, 0)
        self.landed.setdefault(pid, 0)
        self.chips_found.setdefault(pid, 0)
        return p

    def remove_person(self, pid):
        p = self.people.pop(pid, None)
        if p and p["link"]:
            car = self.cars.get(p["link"] - 1)
            if car:
                car["link"] = 0
        for d in (self.designs, self.hits, self.landed, self.chips_found):
            d.pop(pid, None)
        if self.jobs:
            self.jobs.left(pid)

    def add_car(self, design, x, y, yaw, cid=None):
        if cid is None:
            cid = self._next_car
            while cid in self.cars and cid < CARS.stop - 1:
                cid += 1
            self._next_car = cid + 1 if cid + 1 < CARS.stop else CARS.start
        design = fit_design(design)
        c = new_car(cid, x, y, yaw)
        self.cars[cid], self.designs[cid], self.stats[cid] = c, design, stats_of(design)
        return c

    def remove_car(self, cid):
        c = self.cars.pop(cid, None)
        if c and c["link"]:
            p = self.people.get(c["link"] - 1)
            if p:
                p["link"] = 0
        self.designs.pop(cid, None)
        self.stats.pop(cid, None)

    def add_robot(self, design, x, y, yaw, rid=None):
        if rid is None:
            rid = self._next_robot
            while rid in self.robots and rid < ROBOTS.stop - 1:
                rid += 1
            self._next_robot = rid + 1 if rid + 1 < ROBOTS.stop else ROBOTS.start
        r = new_robot(rid, x, y, yaw)
        self.robots[rid], self.designs[rid], self.stats[rid] = r, design, robot_stats(design)
        return r

    def remove_robot(self, rid):
        self.robots.pop(rid, None)
        self.designs.pop(rid, None)
        self.stats.pop(rid, None)

    # ---------- the city's cars and robots (the server's and an offline window's) ----------
    def park_cars(self, want, parked):
        """Cars parked for anyone to take, up to want, in the city's bays (a mixed bag of bodies and colours).
        parked: the set of their ids, kept by the caller; changed here."""
        bays = self.city.parking
        yard = [b for b in bays if self.city.in_zone("depot", b[0], b[1])][:3]  # (a few in the depot's yard, where
        order = yard + [bays[(n * 7) % len(bays)] for n in range(len(bays))]  # everyone starts; the rest about town)
        n = 0
        while len(parked) < want and n < len(order):
            spot = order[n]
            n += 1
            if any(math.hypot(c["x"] - spot[0], c["y"] - spot[1]) < 3.0 for c in self.cars.values()):
                continue
            k = len(parked)
            d = default_design(f"Parked {k + 1}", TRAFFIC_COLOURS[(k * 3) % len(TRAFFIC_COLOURS)], BODIES[k % 4])
            d["points"] = {"speed": 30 + (k * 7) % 25, "acceleration": 30 + (k * 11) % 25, "grip": 30}
            parked.add(self.add_car(d, spot[0], spot[1], spot[2])["id"])
        while len(parked) > want:
            cid = max(parked)
            if self.cars.get(cid, {}).get("link"):
                break
            self.remove_car(cid)
            parked.discard(cid)

    def traffic_spot(self, k):
        """Where the k-th traffic car starts: on its lane, 8 m past a junction."""
        c = self.city
        kk, m = (k * 3 + 1) % (c.cols + 1), (k * 2 + 1) % (c.rows + 1)
        x, y = c.junction(kk, m)
        yaw = 0.0 if k % 2 == 0 else 90.0
        return ((x + 8.0, y + city_map.LANE) if yaw == 0.0 else (x - city_map.LANE, y + 8.0)) + (yaw,)

    def add_traffic(self, k):
        x, y, yaw = self.traffic_spot(k)
        d = default_design(f"Traffic {k + 1}", TRAFFIC_COLOURS[k % len(TRAFFIC_COLOURS)], BODIES[(k + 1) % 4])
        d["points"] = {"speed": 30, "acceleration": 35, "grip": 35}
        return self.add_car(d, x, y, yaw)

    def patrol_spot(self, k):
        """Where the k-th robot starts its patrol: on the pavement of the k-th block nearest the depot, where everyone
        starts (they used to start along the city's south edge, 100 to 180 m away, and nobody met one)."""
        c = self.city
        dx, dy = c.places["depot"][0], c.places["depot"][1]
        order = sorted(range(len(c.blocks)), key=lambda i: (math.hypot((c.blocks[i]["x0"] + c.blocks[i]["x1"]) / 2 - dx,
                                                                         (c.blocks[i]["y0"] + c.blocks[i]["y1"]) / 2 - dy), i))
        bi = order[k % len(order)]
        side = (k * 3 + 1 + k // len(order)) % 4
        return c.addresses[bi * 4 + side]

    def add_patrol(self, k):
        a = self.patrol_spot(k)
        return self.add_robot(robot_design(k), a[0], a[1], a[2])

    def respawn(self, pid):
        """A person back to the depot's yard on foot (the car left where it is)."""
        p = self.people.get(pid)
        if p is None:
            return
        if p["link"]:
            car = self.cars.get(p["link"] - 1)
            if car:
                car["link"] = 0
        s = self.city.spawns[pid % len(self.city.spawns)]
        p.update(x=s[0], y=s[1], z=0.0, vz=0.0, yaw=s[2], v=0.0, u=0.0, link=0, move=0, mp=0, lk=30)
        p["flags"] &= FLAG_PARCEL
        if p["hp"] <= 0:
            p["hp"] = DOWN_HEALTH

    def fix(self, pid):
        """(The teacher's F) Mend the person and the car they are in."""
        p = self.people.get(pid)
        if p is None:
            return False
        p["hp"], p["move"], p["mp"] = HEALTH, 0, 0
        if p["link"] and (p["link"] - 1) in self.cars:
            self.cars[p["link"] - 1]["dmg"] = 0
        return True

    # ---------- the tick ----------
    def step_all(self, inputs):
        """One tick. inputs: id -> (a, b, buttons): a person's move vector or a car's pedals go under the PERSON's id
        (the person drives the car they are in); a robot's input under the robot's."""
        self.bumps = []
        city = self.city
        idle = (0.0, 0.0, 0)
        driven = {}
        for pid, p in list(self.people.items()):
            inp = inputs.get(pid, idle)
            if (inp[2] & RESPAWN) and not p["lk"]:
                self.respawn(pid)
                inp = idle
                p = self.people[pid]
            if (inp[2] & ACTION) and not p["lk"]:
                self.action(pid, p)
            if p["link"]:
                driven[p["link"] - 1] = (inp, pid)
            self.people[pid] = step_person(p, inp if not p["link"] else idle, STEP, city)
        for cid, c in list(self.cars.items()):
            inp, driver = driven.get(cid, (None, None))
            if inp is None and not c["link"]:
                inp = inputs.get(cid)  # (the computer's traffic and racers drive under the car's own id)
            st = self.stats[cid] if driver is None else stats_of(self.designs[driver])  # (a person drives as their
            n = step_car(c, inp if inp is not None else idle, STEP, city, st, driven=inp is not None)  # points say)
            self.cars[cid] = n
            self.stunt(cid, c, n)
        for rid, r in list(self.robots.items()):
            self.robots[rid] = step_robot(r, inputs.get(rid, idle), STEP, city, self.stats[rid])
        self.contacts()
        self.seat_people()
        if self.jobs is not None:
            self.jobs.tick(self)
        for things in (self.people, self.cars, self.robots):
            for t in things.values():
                t.update(self.schema.quantise(t))
        self.tick += 1
        return self.things()

    def action(self, pid, p):
        """ACTION on foot: into the nearest car with no driver within reach; in a car, under EXIT_SPEED: out."""
        if p["link"]:
            car = self.cars.get(p["link"] - 1)
            if car is None or abs(car["v"]) < EXIT_SPEED:
                if car is not None:
                    car["link"] = 0
                    fx, fy = facing(car["yaw"])
                    p["x"], p["y"] = car["x"] - fy * 1.6, car["y"] + fx * 1.6
                    p["yaw"] = car["yaw"]
                    p["x"], p["y"], _ = self.city.collide(p["x"], p["y"], PERSON_R)
                p["link"], p["lk"], p["v"], p["z"], p["vz"] = 0, 20, 0.0, 0.0, 0.0
            return
        if p["move"] in (MOVE_DOWN, MOVE_GETUP) or p["z"] > 0.0:
            return
        best, bd = None, ENTER_REACH + CAR_R
        for cid, c in self.cars.items():
            if c["link"]:
                continue
            d = math.hypot(c["x"] - p["x"], c["y"] - p["y"])
            if d < bd:
                best, bd = cid, d
        if best is not None:
            self.cars[best]["link"] = pid + 1
            p["link"], p["lk"], p["move"], p["mp"], p["v"] = best + 1, 20, 0, 0, 0.0
            if self.jobs is not None:
                self.jobs.entered(self, pid, best)

    def seat_people(self):
        for p in self.people.values():
            if p["link"]:
                car = self.cars.get(p["link"] - 1)
                if car is None:
                    p["link"] = 0
                    continue
                fx, fy = facing(car["yaw"])
                p["x"], p["y"], p["z"] = car["x"] + fx * SEAT[0] - fy * SEAT[1], car["y"] + fy * SEAT[0] + fx * SEAT[1], car["z"]
                p["yaw"], p["v"], p["u"] = car["yaw"], car["v"], car["u"]

    def stunt(self, cid, before, after):
        """A jump off a ramp: its length when it lands (the jobs pay for it)."""
        if after["flags"] & FLAG_CAR_AIR and not before["flags"] & FLAG_CAR_AIR:
            self.stunts[cid] = (before["x"], before["y"], self.tick)
        elif before["flags"] & FLAG_CAR_AIR and not after["flags"] & FLAG_CAR_AIR and cid in self.stunts:
            x0, y0, _t = self.stunts.pop(cid)
            length = math.hypot(after["x"] - x0, after["y"] - y0)
            if length >= STUNT_LEAST and after["link"] and self.jobs is not None:
                self.jobs.stunt(self, after["link"] - 1, length)

    def contacts(self):
        """Cars bump cars and shove people; people and robots push each other; a cross robot zaps; punches and
        kicks land."""
        reach, slow, transfer = RULES.get("bump_distance", 2.4), RULES.get("bump_slowdown", 0.3), RULES.get("bump_transfer", 0.7)
        cars = list(self.cars.items())
        for i in range(len(cars)):
            a = cars[i][1]
            for j in range(i + 1, len(cars)):
                b = cars[j][1]
                if bump_cars(a, b, reach, slow, transfer):
                    self.bumps.append((self.tick, cars[i][0], cars[j][0]))
                    for cid in (cars[i][0], cars[j][0]):
                        who = self.cars[cid]["link"]
                        if who:
                            self.hits[who - 1] = self.hits.get(who - 1, 0) + 1
                            if self.jobs is not None:
                                self.jobs.bumped(self, who - 1)
        people = [(pid, p) for pid, p in self.people.items() if not p["link"]]
        for pid, p in people:
            for cid, c in cars:
                dx, dy = p["x"] - c["x"], p["y"] - c["y"]
                d = math.hypot(dx, dy)
                if d < CAR_R + PERSON_R + 0.3:
                    speed = math.hypot(*car_velocity(c))
                    if d > 1e-6:
                        push = CAR_R + PERSON_R + 0.3 - d
                        p["x"] += dx / d * push
                        p["y"] += dy / d * push
                    if speed > KNOCK_SPEED and p["move"] not in (MOVE_DOWN, MOVE_GETUP) and not p["bg"]:
                        p["hp"] = max(0, p["hp"] - 15)
                        knock_down(p)
                        p["bg"] = BUMP_GRACE
                        self.hits[pid] = self.hits.get(pid, 0) + 1
                        who = c["link"]
                        self.events.append((self.tick, f"{self.name(pid)} was knocked down by a car"))
                        if who and self.jobs is not None:
                            self.jobs.bumped(self, who - 1)
            for rid, r in self.robots.items():
                if push_apart(p, r, PERSON_R + ROBOT_R) and (r["flags"] & FLAG_CROSS) and r["hp"] > 0 and not p["bg"] \
                        and p["move"] not in (MOVE_DOWN, MOVE_GETUP) and r["aux"] > 200:
                    p["hp"] = max(0, p["hp"] - (ZAP // 2 if p["move"] == MOVE_BLOCK else ZAP))
                    p["bg"] = ZAP_GRACE
                    p["move"], p["mp"] = (MOVE_HURT, 0) if p["move"] != MOVE_BLOCK else (p["move"], p["mp"])
                    dx, dy = p["x"] - r["x"], p["y"] - r["y"]
                    d = math.hypot(dx, dy) or 1.0
                    p["x"] += dx / d * 0.4
                    p["y"] += dy / d * 0.4
                    r["flags"] |= FLAG_ZAP
                    self.hits[pid] = self.hits.get(pid, 0) + 1
                    if p["hp"] <= 0:
                        knock_down(p)
                        self.events.append((self.tick, f"{self.name(pid)} was zapped down by {self.designs[rid]['name']}"))
                else:
                    r["flags"] &= ~FLAG_ZAP
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                push_apart(people[i][1], people[j][1], PUSH_PERSON)
        robots = list(self.robots.items())
        for i in range(len(robots)):
            for j in range(i + 1, len(robots)):
                push_apart(robots[i][1], robots[j][1], 2 * ROBOT_R)
        for rid, r in robots:
            for cid, c in cars:
                if push_apart(r, c, ROBOT_R + CAR_R):
                    c["v"] *= 0.9
        # punches and kicks: the tick they land, the first thing in reach ahead
        for pid, p in people:
            move = p["move"]
            if move in HIT_TICK and p["mp"] == HIT_TICK[move]:
                for rid, r in robots:
                    if r["hp"] > 0 and in_reach(p, r, REACH[move] + ROBOT_R):
                        r["hp"] = max(0, r["hp"] - HIT[move])
                        r["v"] += 1.5
                        r["flags"] |= FLAG_CROSS
                        self.landed[pid] = self.landed.get(pid, 0) + 1
                        if r["hp"] <= 0:
                            r["mp"] = 0
                            self.events.append((self.tick, f"{self.name(pid)} powered down {self.designs[rid]['name']}"))
                            if self.jobs is not None:
                                self.jobs.powered_down(self, pid, rid)
                        break
                else:
                    for qid, q in people:
                        if qid != pid and q["move"] not in (MOVE_DOWN, MOVE_GETUP) and in_reach(p, q, REACH[move] + PERSON_R):
                            amount = HIT[move] * (BLOCK_SHARE if q["move"] == MOVE_BLOCK else 1.0)
                            q["hp"] = max(0, q["hp"] - int(amount))
                            self.landed[pid] = self.landed.get(pid, 0) + 1
                            self.hits[qid] = self.hits.get(qid, 0) + 1
                            if q["move"] != MOVE_BLOCK:
                                q["move"], q["mp"] = MOVE_HURT, 0
                            if q["hp"] <= 0:
                                knock_down(q)
                                self.events.append((self.tick, f"{self.name(qid)} was knocked down by {self.name(pid)}"))
                            break

    def name(self, pid):
        d = self.designs.get(pid)
        return d["name"] if d else f"#{pid}"


def city_of(name=city_map.DEFAULT_CITY):
    return city_map.load(name)
