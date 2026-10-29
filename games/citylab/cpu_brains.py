"""The computer's drivers in City Lab (server side, so the system's maths will do): the traffic (cars that keep to the left and turn at junctions), the robots
(patrolling their block's pavement, cross with a person who comes close, rogue in a round-up: chasing), and the
racers (computer cars in a street race, from easy to expert). Plain functions of the state, as Kart Lab's.

drive_car(cid, car, world, mem) -> (throttle, steer, buttons); drive_robot(rid, robot, world, mem) -> the same.
mem is a dict the driver keeps between ticks (its route, its waypoint); the server holds one per thing.
"""
import math

import city_version  # noqa: F401
import city_map
import city_sim as sim

LEVELS = ("easy", "medium", "expert")
NAMES = {"easy": "Learner", "medium": "Cabbie", "expert": "Ace"}
TRAFFIC_SPEED = 9.0        # m/s on a straight (32 km/h)
TURN_SPEED = 4.5           # ...into a junction
FOLLOW_GAP = 9.0           # brake for a car this close ahead
PERSON_GAP = 7.0           # stop for a person this close ahead
LOOK = 6.0                 # pure pursuit's reach
RACER = {"easy": (0.55, 0.6), "medium": (0.75, 0.75), "expert": (1.0, 0.95)}  # (share of top speed, corner pace)
DIRS = {0: (1, 0), 1: (0, 1), 2: (-1, 0), 3: (0, -1)}  # east, north, west, south


def name_for(level, n):
    return f"{NAMES.get(level, 'Driver')} {n + 1}"


def wrap(d):
    return (d + 180.0) % 360.0 - 180.0


def steer_to(x, y, yaw, tx, ty):
    """The wheel for a point: -1 to 1 (left positive), from the angle to it."""
    ang = wrap(math.degrees(math.atan2(ty - y, tx - x)) - yaw)
    return max(-1.0, min(1.0, ang / 35.0)), ang


def ahead_of(me, other, gap, width=2.6):
    """Is other within gap in front of me (and roughly in my lane)?"""
    dx, dy = other["x"] - me["x"], other["y"] - me["y"]
    fx, fy = sim.facing(me["yaw"])
    along = dx * fx + dy * fy
    across = -dx * fy + dy * fx
    return 0.5 < along < gap and abs(across) < width


# ---------- the traffic ----------
def nearest_junction(city, x, y):
    k = max(0, min(city.cols, round((x - city.xmin - city_map.ROAD / 2) / city.pitch)))
    m = max(0, min(city.rows, round((y - city.ymin - city_map.ROAD / 2) / city.pitch)))
    return k, m


def leg_points(city, k0, m0, k1, m1):
    """The lane's waypoints from junction (k0, m0) to (k1, m1), on the left as you go: the way out, the way in, the
    junction's middle on your lane."""
    ax, ay = city.junction(k0, m0)
    bx, by = city.junction(k1, m1)
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    lx, ly = -uy * city_map.LANE, ux * city_map.LANE  # left of travel
    pts = []
    s = city_map.ROAD / 2 + 2.0
    while s < d - city_map.ROAD / 2 - 2.0:
        pts.append((ax + ux * s + lx, ay + uy * s + ly))
        s += 12.0
    pts.append((bx - ux * (city_map.ROAD / 2 + 1.0) + lx, by - uy * (city_map.ROAD / 2 + 1.0) + ly))
    pts.append((bx + lx + ux * 1.0, by + ly + uy * 1.0))
    return pts


def next_junction(city, k, m, d, rng_val):
    """From junction (k, m) arriving in direction d: the next direction (not back) and junction."""
    choices = []
    for nd in (d, (d + 1) % 4, (d + 3) % 4):
        ex, ey = DIRS[nd]
        nk, nm = k + ex, m + ey
        if 0 <= nk <= city.cols and 0 <= nm <= city.rows:
            choices.append((nd, nk, nm))
    if not choices:
        nd = (d + 2) % 4
        ex, ey = DIRS[nd]
        return nd, k + ex, m + ey
    # straight on more often than not
    weights = [3 if c[0] == d else 1 for c in choices]
    pick = rng_val * sum(weights)
    for c, w in zip(choices, weights):
        if pick < w:
            return c
        pick -= w
    return choices[-1]


def start_route(city, car, mem, rng_val):
    """Where this car is going first: along the nearest road in the direction it faces."""
    k, m = nearest_junction(city, car["x"], car["y"])
    d = int(round(((car["yaw"] % 360.0) / 90.0))) % 4
    ex, ey = DIRS[d]
    if not (0 <= k + ex <= city.cols and 0 <= m + ey <= city.rows):
        d = (d + 2) % 4
        ex, ey = DIRS[d]
    mem["junction"], mem["dir"] = (k, m), d
    mem["route"] = leg_points(city, k, m, k + ex, m + ey)
    mem["next"] = (k + ex, m + ey)


def drive_car(cid, car, world, mem, rng_val=0.5):
    """A traffic car's input this tick."""
    city = world.city
    if "route" not in mem or not mem["route"]:
        start_route(city, car, mem, rng_val)
    if mem.get("stuck", 0) > 240:  # a long while going nowhere: a fresh route
        mem.clear()
        start_route(city, car, mem, rng_val)
    route = mem["route"]
    tx, ty = route[0]
    if math.hypot(tx - car["x"], ty - car["y"]) < 4.5:
        route.pop(0)
        if not route:
            k, m = mem["next"]
            nd, nk, nm = next_junction(city, k, m, mem["dir"], rng_val)
            mem["junction"], mem["dir"], mem["next"] = (k, m), nd, (nk, nm)
            mem["route"] = route = leg_points(city, k, m, nk, nm)
        tx, ty = route[0]
    steer, ang = steer_to(car["x"], car["y"], car["yaw"], tx, ty)
    want = TRAFFIC_SPEED if len(route) > 2 and abs(ang) < 25 else TURN_SPEED
    if abs(ang) > 70 and car["v"] > 1.0:
        want = 1.5
    for oid, other in world.cars.items():
        if oid != cid and ahead_of(car, other, FOLLOW_GAP):
            want = min(want, max(0.0, abs(other["v"]) - 1.0))
    for p in world.people.values():
        if not p["link"] and ahead_of(car, p, PERSON_GAP, 3.2):
            want = 0.0
    for r in world.robots.values():
        if not r["link"] and ahead_of(car, r, PERSON_GAP, 3.2):
            want = 0.0
    v = car["v"]
    if want <= 0.3:
        th = -1.0 if v > 0.5 else 0.0
    elif v < want - 0.5:
        th = 1.0
    elif v > want + 0.5:
        th = -0.6
    else:
        th = 0.35
    mem["stuck"] = mem.get("stuck", 0) + 1 if abs(v) < 0.3 and want > 0.5 else 0
    if abs(ang) > 120 and abs(v) < 1.0:  # facing away from the route: reverse round
        return -0.7, -steer, 0
    return th, steer, 0


# ---------- the racers ----------
def drive_racer(cid, car, world, mem, level="medium"):
    """A computer car in the street race: round the course's checkpoints, braking for the turns."""
    jobs = world.jobs
    race = jobs.race if jobs else None
    if race is None or cid not in race["cars"] or race["state"] != "racing":
        if race is not None and cid in race["cars"]:
            return (0.0, 0.0, 0)  # on the grid
        return drive_car(cid, car, world, mem)
    course = race["course"]
    cp = race["cars"][cid]
    if cid in race["done"]:
        return (-0.5 if car["v"] > 1 else 0.0, 0.0, 0)
    tx, ty = course[(cp + 1) % len(course)]
    nx, ny = course[(cp + 2) % len(course)]
    steer, ang = steer_to(car["x"], car["y"], car["yaw"], tx, ty)
    share, corner = RACER.get(level, RACER["medium"])
    top = world.stats[cid]["top"] * share
    d = math.hypot(tx - car["x"], ty - car["y"])
    turn_ahead = abs(wrap(math.degrees(math.atan2(ny - ty, nx - tx)) - math.degrees(math.atan2(ty - car["y"], tx - car["x"]))))
    want = top
    if d < 25.0 and turn_ahead > 45:
        want = max(6.0, top * corner * (0.45 + 0.55 * d / 25.0))
    if abs(ang) > 40:
        want = min(want, 7.0)
    for oid, other in world.cars.items():
        if oid != cid and ahead_of(car, other, 6.0, 2.2):
            want = min(want, abs(other["v"]))
    v = car["v"]
    th = 1.0 if v < want - 1.0 else -0.8 if v > want + 1.5 else 0.5
    bt = sim.DRIFT if level == "expert" and abs(ang) > 30 and v > 9.0 else 0
    return th, steer, bt


# ---------- the robots ----------
def patrol_points(city, r):
    """The pavement round the robot's block: its four lamps, a metre in."""
    bi = city.block_index(r["x"], r["y"])
    if bi is None:
        bi = min(range(len(city.blocks)), key=lambda i: math.hypot((city.blocks[i]["x0"] + city.blocks[i]["x1"]) / 2 - r["x"],
                                                                     (city.blocks[i]["y0"] + city.blocks[i]["y1"]) / 2 - r["y"]))
    b = city.blocks[bi]
    pad = city_map.PAVE / 2
    return [(b["x0"] + pad, b["y0"] + pad), (b["x1"] - pad, b["y0"] + pad), (b["x1"] - pad, b["y1"] - pad), (b["x0"] + pad, b["y1"] - pad)]


def drive_robot(rid, robot, world, mem):
    """A robot's input: patrolling, or chasing a person when cross or rogue."""
    if robot["hp"] <= 0 or robot["link"]:
        return (0.0, 0.0, 0)
    city = world.city
    rogue = bool(robot["flags"] & sim.FLAG_ROGUE)
    # the nearest person on foot
    best, bd = None, math.inf
    for pid, p in world.people.items():
        if p["link"] or p["move"] in (sim.MOVE_DOWN,):
            continue
        d = math.hypot(p["x"] - robot["x"], p["y"] - robot["y"])
        if d < bd:
            best, bd = p, d
    cross = best is not None and (bd < sim.CROSS_REACH or rogue) and bd < (400.0 if rogue else sim.CROSS_REACH * 2.5)
    if cross or (robot["flags"] & sim.FLAG_CROSS and best is not None and bd < sim.CROSS_REACH * 2.5):
        robot["flags"] |= sim.FLAG_CROSS
        mem["calm"] = 0
        steer, ang = steer_to(robot["x"], robot["y"], robot["yaw"], best["x"], best["y"])
        th = 1.0 if abs(ang) < 60 else 0.3
        if bd < 1.6:
            th = 0.2
        return th, steer, sim.ACTION
    if robot["flags"] & sim.FLAG_CROSS:
        mem["calm"] = mem.get("calm", 0) + 1
        if mem["calm"] > 90:
            robot["flags"] &= ~sim.FLAG_CROSS
        return (0.0, 0.0, 0)
    pts = mem.get("patrol")
    if not pts:
        pts = mem["patrol"] = patrol_points(city, robot)
        mem["at"] = min(range(4), key=lambda i: math.hypot(pts[i][0] - robot["x"], pts[i][1] - robot["y"]))
    tx, ty = pts[mem["at"]]
    if math.hypot(tx - robot["x"], ty - robot["y"]) < 1.2:
        mem["at"] = (mem["at"] + 1) % 4
        mem["wait"] = 90
        tx, ty = pts[mem["at"]]
    if mem.get("wait", 0) > 0:
        mem["wait"] -= 1
        return (0.0, 0.0, 0)
    steer, ang = steer_to(robot["x"], robot["y"], robot["yaw"], tx, ty)
    th = 0.45 if abs(ang) < 40 else 0.1
    if mem.get("stuck", 0) > 120:
        mem["stuck"] = 0
        mem["patrol"] = None
        return (-0.5, 1.0, 0)
    mem["stuck"] = mem.get("stuck", 0) + 1 if abs(robot["v"]) < 0.1 else 0
    return th, steer, 0
