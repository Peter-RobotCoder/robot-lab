"""The computer karts' drivers, Easy to Expert. Each is a function of its kart's state and the race that returns
(throttle, steer, buttons) 60 times a second, as a learner's brain does through kart_brain.Autopilot.

All three follow the track by pure pursuit: aim at a point on the track a little way ahead (further the faster
they go), and steer by how hard the kart must turn to get there. They differ in how far they look, how much
throttle they allow themselves, how much they slow for a bend, and what they know about the track:

    easy     looks 5 m + 0.4 s ahead, never above 70% throttle, slows for any bend over 18 degrees, drives
             straight through oil
    medium   6 m + 0.45 s, 88% throttle, slows for bends over 28 degrees, steers round oil
    expert   7 m + 0.5 s, full throttle, slows only for bends over 40 degrees (none on the Club Circuit), steers
             round oil and over dash pads, and holds DRIFT through corners sharper than 30 degrees so it
             collects mini-turbos on the way out

Each has a small wobble from its kart's id and the tick, so two karts of a level never drive the same line, and
each steers 0.3 away from a kart directly ahead within 4 m rather than driving into it.
"""
import math

import kart_sim
import kart_track

LEVELS = ("easy", "medium", "expert")
NAMES = {"easy": "Rookie", "medium": "Racer", "expert": "Ace"}

# per level: lookahead (m, plus seconds of travel), the throttle cap, the 15 m bend (degrees) it starts slowing
# for, how many degrees beyond that take it down to CORNER_MIN, the wobble on the steer, and what it knows
TUNING = {
    "easy":   {"look": (5.0, 0.40), "cap": 0.70, "slow_at": 18.0, "slow_over": 40.0, "wobble": 0.12,
               "oil": False, "pads": False, "drift": False},
    "medium": {"look": (6.0, 0.45), "cap": 0.88, "slow_at": 28.0, "slow_over": 40.0, "wobble": 0.06,
               "oil": True, "pads": False, "drift": False},
    "expert": {"look": (7.0, 0.50), "cap": 1.00, "slow_at": 40.0, "slow_over": 40.0, "wobble": 0.02,
               "oil": True, "pads": True, "drift": True},
}
CORNER_MIN = 9.0          # m/s: the slowest a driver goes for the sharpest bend
DRIFT_CORNER = 30.0       # expert drifts through a corner sharper than this (degrees over the next 20 m)...
DRIFT_KEEP = 18.0         # ...and keeps the drift going while the bend is still over this, so the charge pays out
DRIFT_MIN_SPEED = 14.0    # m/s: slower than this a drift only scrubs speed and over-turns (kart_sim needs > 7)
AVOID_AHEAD, AVOID_SIDE = 4.0, 1.6  # a kart this close in front, this near our line: steer round it
PASS_OFFSET = 2.6         # how far beside a kart in the way to aim (karts bump within 1.7 m)
PASS_TICKS = 90           # how long a driver keeps to its passing side after the kart ahead leaves its nose (1.5 s)
PASSING = {}              # kart id -> (the kart it is passing, the side it chose, the tick it gives up)
FEATURE_MARGIN = 1.8      # how far outside an oil patch's radius to aim
FEATURE_REACH = 25.0      # metres beyond the lookahead a driver starts moving across for a patch or a pad
LATERAL_GAIN = 0.1        # steer per metre the kart is off the line it wants (pursuit alone drifts across slowly)


def name_for(level, n):
    """The display name of the n-th computer kart at this level: Rookie 1, Racer 2, Ace 3..."""
    return f"{NAMES.get(level, str(level).title())} {n}"


def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


def seed_of(kid):
    return kid if isinstance(kid, int) else sum(ord(c) for c in str(kid))


def max_turn_rate(st, v):
    """Degrees a second the kart can turn at this speed with full steer (kart_sim.step's formula)."""
    return st["steer"] * min(1.0, abs(v) / 6.0) * (1.0 - 0.4 * min(1.0, abs(v) / st["top"]))


def target_lateral(tune, track, s, look):
    """Where across the track to aim: the middle, unless an oil patch is coming (go round it, on the side nearer
    the middle) or a dash pad is (go over it). A feature counts from reach metres ahead until 5 m behind, so
    the kart doesn't cut back across the patch the moment its middle is level with it."""
    lat, reach = 0.0, look + FEATURE_REACH
    limit = track.half - kart_sim.KART_HALF - 0.8
    if tune["oil"]:
        for fs, fl in track.oil:
            d = (fs - s + 5.0) % track.length - 5.0
            if -5.0 < d < reach:
                clear = kart_track.OIL_RADIUS + FEATURE_MARGIN
                lat = fl - clear if fl > 0 else fl + clear
    if tune["pads"]:
        for fs, fl in track.boosts:
            d = (fs - s + 5.0) % track.length - 5.0
            if -5.0 < d < reach:
                lat = fl
    return max(-limit, min(limit, lat))


def pursue(track, k, st, look, lateral):
    """Pure pursuit: the steer that carries the kart onto the line (lateral metres left of the middle) look metres
    ahead. The kart must turn through the angle to that point before it gets there, so the yaw rate wanted is
    v * 2 sin(angle) / look; steer is that as a share of what the kart can do."""
    tx, ty, _ = track.point(k["s"] + look, lateral)
    angle = wrap(math.degrees(math.atan2(ty - k["y"], tx - k["x"])) - k["yaw"])
    v = max(k["v"], 3.0)  # (standing still it still points itself at the line)
    wanted = math.degrees(v * 2.0 * math.sin(math.radians(angle)) / look)
    rate = max(max_turn_rate(st, v), 20.0)
    steer = wanted / rate * 1.3  # (×1.3: a touch of extra bite, the slide eats some)
    steer += max(-0.35, min(0.35, (lateral - k["lat"]) * LATERAL_GAIN))  # (and pull across to the line itself)
    return max(-1.0, min(1.0, steer)), angle


def corner_speed(tune, st, bend):
    """The speed this driver is happy with for a bend of this many degrees over 15 m."""
    top = tune["cap"] * st["top"]
    if bend <= tune["slow_at"]:
        return top
    share = min(1.0, (bend - tune["slow_at"]) / tune["slow_over"])
    return max(CORNER_MIN, top - (top - CORNER_MIN) * share)


def blocked(k, race):
    """The nearest kart just ahead of our nose: (its state, +1 if it's to our left or -1 to our right, metres
    ahead), or None if the road is clear."""
    yr = math.radians(k["yaw"])
    fx, fy = math.cos(yr), math.sin(yr)
    best = None
    for oid, o in race.karts.items():
        if oid == k["id"]:
            continue
        dx, dy = o["x"] - k["x"], o["y"] - k["y"]
        ahead = dx * fx + dy * fy
        side = fx * dy - fy * dx  # (positive = to our left)
        if 0.0 < ahead < AVOID_AHEAD and abs(side) < AVOID_SIDE and (best is None or ahead < best[2]):
            best = (o, 1 if side >= 0 else -1, ahead)
    return best


def passing(k, race, block):
    """The kart this one is getting past and the side it chose (+1: it's on our left, so we pass on the right),
    or None. A kart on our nose (block) starts a pass; the side is kept until we're clear ahead of it or
    PASS_TICKS have gone, so the driver doesn't swing back in behind it the moment its nose is free."""
    kid, tick = k["id"], race.tick
    if block:
        PASSING[kid] = (block[0]["id"], block[1], tick + PASS_TICKS)
    p = PASSING.get(kid)
    if p is None:
        return None
    oid, side, until = p
    other = race.karts.get(oid)
    if other is None or tick > until or until - tick > PASS_TICKS:  # (the last: a new race, ticks from 0 again)
        PASSING.pop(kid, None)
        return None
    yr = math.radians(k["yaw"])
    ahead = (other["x"] - k["x"]) * math.cos(yr) + (other["y"] - k["y"]) * math.sin(yr)
    if ahead < -2.0 or ahead > AVOID_AHEAD + 4.0:  # past it, or it has gone: done
        PASSING.pop(kid, None)
        return None
    return other, side


def drive(level, k, race):
    """What a computer kart at this level does this tick: (throttle, steer, buttons) for kart_sim.Race.step_all."""
    tune = TUNING.get(level, TUNING["medium"])
    track, st = race.track, race.stats[k["id"]]
    v, s = k["v"], k["s"]
    base, per_second = tune["look"]
    look = base + per_second * max(0.0, v)
    line = target_lateral(tune, track, s, look)
    block = blocked(k, race)
    pas = passing(k, race, block)
    if pas:  # a kart in the way: aim at the line beside it (touching costs both karts speed every tick)
        limit = track.half - kart_sim.KART_HALF - 0.5
        line = max(-limit, min(limit, pas[0]["lat"] - pas[1] * PASS_OFFSET))
    steer, angle = pursue(track, k, st, look, line)
    # the bend ahead sets the speed: the one we're in, and the next one a little discounted (there's time to slow)
    bend = max(abs(track.curvature(s, 15.0)), 0.7 * abs(track.curvature(s + 15.0, 15.0)))
    want = corner_speed(tune, st, bend)
    if v > want + 2.0:
        throttle = -1.0  # (kart_sim's brake is all or nothing: any negative throttle bites the same)
    elif v > want:
        throttle = 0.0
    else:
        throttle = tune["cap"]
    if abs(angle) > 50 and v > 6.0:  # pointing well off the line: ease off and get it back first
        throttle = min(throttle, 0.2)
    buttons = 0
    if tune["drift"] and v > DRIFT_MIN_SPEED and not k["slip"]:
        # a drift adds its own 25 degrees a second and lets the back slide out, so only start one when fast, on
        # the line it wants and already steering into a real corner (never on oil); keep it going while the bend
        # lasts so the charge reaches a mini-turbo. The pursuit above still steers: the slide makes it ask for more
        corner = track.curvature(s, 20.0)
        into = 1.0 if corner > 0 else -1.0
        drifting = k["flags"] & (kart_sim.FLAG_DRIFT_L | kart_sim.FLAG_DRIFT_R)
        settled = abs(line - k["lat"]) < 1.0
        if (abs(corner) > DRIFT_CORNER and steer * into > 0.3 and settled) or (drifting and abs(corner) > DRIFT_KEEP):
            buttons |= kart_sim.DRIFT
            throttle = max(throttle, 0.6)
    # keep it human: a small sway that is the same every run for this kart
    steer += math.sin(race.tick * 0.07 + seed_of(k["id"]) * 1.7) * tune["wobble"]
    if block:
        steer -= 0.3 * block[1]
        if block[2] < 2.2 and v > block[0]["v"] - 0.5:  # right on its bumper: ease off until we're beside it
            throttle = min(throttle, 0.3)
    return max(-1.0, min(1.0, throttle)), max(-1.0, min(1.0, steer)), buttons
