"""City Lab's tests: the city, the step, the world, the jobs, the computer's drivers, the prediction, the server with
two windows, and the window offline and online (CHANGE 194).

    ..\\shared-world-demo\\.venv\\Scripts\\python city_test.py          everything
    ... city_test.py quick                                              the city, the step, the world, the jobs, the drivers
    ... city_test.py window                                             ...and the window offline
    ... city_test.py server                                             ...and the server, not the windows
    ... city_test.py online                                             ...and the server with two windows over
                                                                        pretend school Wi-Fi (step 5)

Exit code 0 when every check passed.
"""
import copy
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
TMP = tempfile.mkdtemp(prefix="citylab_test_")
os.environ["CITYLAB_DATA"] = TMP
sys.path.insert(0, HERE)

import city_version  # noqa: E402,F401
import city_map  # noqa: E402
import city_sim as sim  # noqa: E402
import city_jobs  # noqa: E402
import cpu_brains  # noqa: E402
from engine import predict, wire  # noqa: E402

PY = sys.executable
SCHEMA = wire.Schema("city", sim.SCHEMA_FIELDS)
results = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, ""))
        print(f"PASS  {name} ({time.time() - t0:.1f} s)", flush=True)
    except Exception as e:  # noqa: BLE001
        results.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"FAIL  {name}: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()


# ---------- the city ----------
def the_city():
    for key in city_map.CITIES:
        a, b = city_map.generate(key), city_map.generate(key)
        assert a.to_data() == b.to_data(), f"{key}: generated twice, different"
        c = city_map.City.from_data(json.loads(json.dumps(a.to_data())))
        assert c.to_data() == a.to_data(), f"{key}: the JSON round trip changed it"
        assert len(c.blocks) == c.cols * c.rows
        kinds = [b_["kind"] for b_ in c.blocks]
        for place in city_map.PLACES:
            assert kinds.count(place) == 1, f"{key}: {kinds.count(place)} {place} blocks"
            assert place in c.places and place in c.zones
        for bld in c.buildings:
            blk = c.blocks[bld["b"]]
            pad = city_map.PAVE + city_map.INSET - 0.01
            assert blk["x0"] + pad <= bld["x0"] < bld["x1"] <= blk["x1"] - pad + 0.02, (key, bld, blk)
            assert blk["y0"] + pad <= bld["y0"] < bld["y1"] <= blk["y1"] - pad + 0.02, (key, bld, blk)
            assert bld["h"] >= 3.0
        by_block = {}
        for bld in c.buildings:
            by_block.setdefault(bld["b"], []).append(bld)
        for bi, blds in by_block.items():
            for i in range(len(blds)):
                for j in range(i + 1, len(blds)):
                    p, q = blds[i], blds[j]
                    overlap = p["x0"] < q["x1"] - 0.05 and q["x0"] < p["x1"] - 0.05 and p["y0"] < q["y1"] - 0.05 and q["y0"] < p["y1"] - 0.05
                    inside = any(a["x0"] <= b["x0"] and a["x1"] >= b["x1"] and a["y0"] <= b["y0"] and a["y1"] >= b["y1"]
                                 for a, b in ((p, q), (q, p)))  # (a tower standing on its podium)
                    assert not overlap or inside, (key, bi, p, q)
        for x, y, yaw, name in c.addresses:
            assert c.surface(x, y) == "pave", (key, name, c.surface(x, y))
            assert c.collide(x, y, sim.PERSON_R)[2] is None, (key, name, "an address inside something")
        for x, y, yaw in c.spawns:
            assert c.surface(x, y) == "lot", (key, (x, y), c.surface(x, y))
            assert c.collide(x, y, sim.PERSON_R)[2] is None
        for x, y, yaw in c.parking:
            assert c.surface(x, y) in ("road", "lot"), (key, (x, y), c.surface(x, y))
            assert c.collide(x, y, sim.CAR_R)[2] is None, (key, (x, y))
        for x, y in c.chips:
            assert c.surface(x, y) == "pave" and c.collide(x, y, sim.PERSON_R)[2] is None, (key, (x, y))
        assert c.surface(c.road_x(0), c.road_y(1) + 20.0) == "road"
        assert c.surface(c.xmax + 2.0, 0.0) in ("grass", "quay")
        assert c.surface(c.xmax + city_map.VERGE + 5.0, 0.0) == "out"
        kind, n, lat = c.locate_road(c.road_x(1) + 1.0, c.road_y(1) + 20.0)
        assert kind == "v" and n == 1 and abs(lat - 1.0) < 1e-9
        assert c.locate_road(*c.junction(1, 1))[0] == "x"
        assert c.lane("h", 1, 1) == c.road_y(1) + city_map.LANE and c.lane("v", 1, 1) == c.road_x(1) - city_map.LANE
        # a car in a building is pushed out through the nearest wall
        bld = c.buildings[0]
        x, y, hit = c.collide(bld["x0"] + 0.3, (bld["y0"] + bld["y1"]) / 2, sim.CAR_R)
        assert hit == "building" and abs(x - (bld["x0"] - sim.CAR_R)) < 1e-6, (x, y, hit)
        x, y, hit = c.collide(c.edge[0] - 5.0, 0.0, 1.0)
        assert hit == "edge" and x == c.edge[0] + 1.0
        # the ramps
        rp = c.ramps[0]
        assert c.ramp_height(rp["x"], rp["y"]) > 0.5 and c.ramp_height(rp["x"], rp["y"] + 10.0) == 0.0
        assert len(json.dumps(c.to_data())) < 80000, key
    print("    the three cities: sizes", {k: f"{city_map.generate(k).width:.0f}x{city_map.generate(k).height:.0f}" for k in city_map.CITIES})


# ---------- the step ----------
def open_city():
    return city_map.load("village")


def road_spot(c):
    """A spot on a long straight road: the ring road's west side, facing north."""
    return c.road_x(0) - city_map.LANE, c.ymin + city_map.ROAD + 5.0, 90.0


def person_step():
    c = open_city()
    x0, y0 = c.junction(1, 1)
    p = sim.new_person(0, x0, y0, 0.0)
    for _ in range(180):
        p = sim.step_person(p, (1.0, 0.0, 0), sim.STEP, c)
        p.update(SCHEMA.quantise(p))
    walked = p["x"] - x0
    assert 8.5 < walked < 9.8, ("walking 3 s", walked)
    assert abs(p["v"] - sim.WALK) < 0.1 and abs(p["yaw"]) < 1e-6
    q = sim.new_person(0, x0, y0, 0.0)
    for _ in range(180):
        q = sim.step_person(q, (1.0, 0.0, sim.RUN), sim.STEP, c)
    assert q["x"] - x0 > walked * 1.7, ("running", q["x"] - x0)
    assert q["flags"] & sim.FLAG_RUN
    # turning to the move: the yaw follows, the person moves the way the input says at once
    r = sim.new_person(0, x0, y0, 0.0)
    for _ in range(30):
        r = sim.step_person(r, (0.0, 1.0, 0), sim.STEP, c)
    assert abs(r["yaw"] - 90.0) < 1e-6 and r["y"] > y0 + 1.0 and abs(r["x"] - x0) < 1e-6, r
    # a jump: up and back down within a second, flagged in the air
    j = sim.new_person(0, x0, y0, 0.0)
    j = sim.step_person(j, (0.0, 0.0, sim.JUMP), sim.STEP, c)
    assert j["vz"] > 0 and j["z"] > 0
    top, air = 0.0, 0
    for _ in range(60):
        j = sim.step_person(j, (0.0, 0.0, 0), sim.STEP, c)
        top = max(top, j["z"])
        air += bool(j["flags"] & sim.FLAG_AIR)
    assert j["z"] == 0.0 and 0.6 < top < 1.0 and 20 < air < 60, (top, air, j)
    # a punch runs its ticks and ends; a block holds while held
    k = sim.new_person(0, x0, y0, 0.0)
    k = sim.step_person(k, (0.0, 0.0, sim.PUNCH), sim.STEP, c)
    assert k["move"] == sim.MOVE_PUNCH and k["mp"] == 0
    for _ in range(sim.MOVE_TICKS[sim.MOVE_PUNCH]):
        k = sim.step_person(k, (1.0, 0.0, 0), sim.STEP, c)
    assert k["move"] == 0 and k["x"] - x0 < 0.5, ("stood still through the punch", k)
    b = sim.new_person(0, x0, y0, 0.0)
    for _ in range(10):
        b = sim.step_person(b, (0.0, 0.0, sim.BLOCK), sim.STEP, c)
    assert b["move"] == sim.MOVE_BLOCK and b["flags"] & sim.FLAG_BLOCK
    b = sim.step_person(b, (0.0, 0.0, 0), sim.STEP, c)
    assert b["move"] == 0
    # a wall: walking into a building is stopped at it
    bld = c.buildings[0]
    w = sim.new_person(0, bld["x0"] - 3.0, (bld["y0"] + bld["y1"]) / 2, 0.0)
    for _ in range(240):
        w = sim.step_person(w, (1.0, 0.0, sim.RUN), sim.STEP, c)
    assert abs(w["x"] - (bld["x0"] - sim.PERSON_R)) < 1e-6, (w["x"], bld["x0"])
    # knocked down, then up with half health
    d = sim.new_person(0, x0, y0, 0.0)
    d["hp"] = 0
    sim.knock_down(d)
    for _ in range(sim.MOVE_TICKS[sim.MOVE_DOWN] + sim.MOVE_TICKS[sim.MOVE_GETUP] + 2):
        d = sim.step_person(d, (1.0, 0.0, 0), sim.STEP, c)
    assert d["move"] == 0 and d["hp"] == sim.DOWN_HEALTH, d
    # in a car nothing moves
    s = sim.new_person(0, x0, y0, 0.0)
    s["link"] = 33
    s2 = sim.step_person(s, (1.0, 1.0, sim.JUMP | sim.PUNCH), sim.STEP, c)
    assert (s2["x"], s2["y"], s2["move"]) == (x0, y0, 0)


def car_step():
    c = city_map.load("harbour")  # (a long enough straight for ten seconds flat out)
    x, y, yaw = road_spot(c)
    st = sim.stats_of(sim.default_design())
    k = sim.new_car(32, x, y, yaw)
    speeds = []
    for _ in range(60 * 10):
        k = sim.step_car(k, (1.0, 0.0, 0), sim.STEP, c, st)
        k.update(SCHEMA.quantise(k))
        speeds.append(k["v"])
    assert speeds[-1] > 0.85 * st["top"], ("full throttle 10 s", speeds[-1], st["top"])  # (Kart Lab's karts settle at
    # 0.89 of their top speed too: the last hundredths of a m/s a tick are rounded away on the wire)
    assert all(b >= a - 1e-9 for a, b in zip(speeds, speeds[1:])), "the speed never falls on a straight"
    assert c.surface(k["x"], k["y"]) == "road", ("still on the road", k["x"], k["y"], c.surface(k["x"], k["y"]))
    for t in range(60 * 4):  # (held, the brake becomes reverse once stopped, as Kart Lab's)
        k = sim.step_car(k, (-1.0, 0.0, 0), sim.STEP, c, st)
        assert k["flags"] & sim.FLAG_BRAKING
        if k["v"] <= 0.0:
            break
    assert t < 60 * 3, ("braked to a stop from flat out in under 3 s", t / 60)
    # steering turns it
    t = sim.new_car(32, x, y, yaw)
    for _ in range(60):
        t = sim.step_car(t, (1.0, 1.0, 0), sim.STEP, c, st)
    assert 10 < sim.wrap(t["yaw"] - yaw) < 170, ("turned left", t["yaw"])
    # no driver: rolls to a stop
    r = dict(k)
    r["v"] = 10.0
    for _ in range(60 * 30):
        r = sim.step_car(r, (0.0, 0.0, 0), sim.STEP, c, st, driven=False)
    assert r["v"] == 0.0, r["v"]
    # the pavement drags, the grass more
    pave = next(a for a in c.addresses)
    pv = sim.new_car(32, pave[0], pave[1], 0.0)
    pv["v"] = 10.0
    rd = sim.new_car(32, x, y, yaw)
    rd["v"] = 10.0
    for _ in range(30):
        pv = sim.step_car(pv, (0.0, 0.0, 0), sim.STEP, c, st)
        rd = sim.step_car(rd, (0.0, 0.0, 0), sim.STEP, c, st)
    assert pv["v"] < rd["v"] - 0.5, ("the pavement slows", pv["v"], rd["v"])
    # a wall: damage over HIT_SPEED, held at it, then it mends a little
    bld = c.buildings[0]
    w = sim.new_car(32, bld["x0"] - 12.0, (bld["y0"] + bld["y1"]) / 2, 0.0)
    w["v"] = 14.0
    for _ in range(90):
        w = sim.step_car(w, (1.0, 0.0, 0), sim.STEP, c, st)
    assert w["dmg"] > 1000, ("a 14 m/s crash damages", w["dmg"])
    assert w["x"] <= bld["x0"] - sim.CAR_R + 1e-6 and abs(w["v"]) < 2.0, (w["x"], w["v"])
    # a wreck crawls; the garage mends it
    wreck = sim.new_car(32, x, y, yaw)
    wreck["dmg"] = sim.DAMAGE_MAX
    for _ in range(60 * 5):
        wreck = sim.step_car(wreck, (1.0, 0.0, 0), sim.STEP, c, st)
    assert wreck["v"] <= sim.WRECK_SPEED + 0.01 and wreck["flags"] & sim.FLAG_WRECKED, wreck["v"]
    gz = c.zones["garage"]
    g = sim.new_car(32, (gz[0] + gz[2]) / 2, (gz[1] + gz[3]) / 2, 0.0)
    g["dmg"] = 5000
    for _ in range(60):
        g = sim.step_car(g, (0.0, 0.0, 0), sim.STEP, c, st)
    assert g["dmg"] == 0, ("mended on the forecourt", g["dmg"])
    # the ramp: airborne, then down
    rp = c.ramps[0]
    yr = rp["yaw"]
    import math
    a = sim.new_car(32, rp["x"] - 14.0 * math.cos(math.radians(yr)), rp["y"] - 14.0 * math.sin(math.radians(yr)), yr)
    a["v"] = 16.0
    air, top = 0, 0.0
    for _ in range(180):
        a = sim.step_car(a, (1.0, 0.0, 0), sim.STEP, c, st)
        air += bool(a["flags"] & sim.FLAG_CAR_AIR)
        top = max(top, a["z"])
    assert air > 10 and top > city_map.RAMP_H + 0.3 and a["z"] == 0.0, (air, top, a["z"])
    # quantised and still, a step changes nothing
    still = sim.new_car(32, x, y, yaw)
    still.update(SCHEMA.quantise(still))
    again = sim.step_car(still, (0.0, 0.0, 0), sim.STEP, c, st, driven=False)
    again.update(SCHEMA.quantise(again))
    assert {k_: v for k_, v in again.items() if k_ != "flags"} == {k_: v for k_, v in still.items() if k_ != "flags"}


def make_world(city="village"):
    c = city_map.load(city)
    w = sim.World(c, SCHEMA)
    w.jobs = city_jobs.Jobs(c, sim.RULES)
    return c, w


def the_world():
    c, w = make_world()
    p = w.add_person(0, sim.default_design("Amy"))
    x, y, yaw = road_spot(c)
    car = w.add_car(sim.default_design("Car"), x, y, yaw)
    # too far: ACTION does nothing; beside it: in; drive; out again
    p.update(x=x + 10.0, y=y)
    w.step_all({0: (0.0, 0.0, sim.ACTION)})
    assert w.people[0]["link"] == 0
    w.people[0].update(x=x + 1.5, y=y, lk=0)
    w.step_all({0: (0.0, 0.0, sim.ACTION)})
    assert w.people[0]["link"] == car["id"] + 1 and w.cars[car["id"]]["link"] == 1, (w.people[0]["link"], w.cars[car["id"]]["link"])
    for _ in range(120):
        w.step_all({0: (1.0, 0.0, 0)})
    cs = w.cars[car["id"]]
    assert cs["v"] > 5.0 and abs(w.people[0]["x"] - cs["x"]) < 0.01, ("the driver moves with the car", cs["v"])
    for _ in range(60):
        w.step_all({0: (0.0, 0.0, sim.ACTION)})
    assert w.people[0]["link"] == car["id"] + 1, "no getting out at speed"
    for _ in range(240):
        w.step_all({0: (-1.0 if w.cars[car["id"]]["v"] > 0.3 else 0.0, 0.0, 0)})
    w.people[0]["lk"] = 0
    w.step_all({0: (0.0, 0.0, sim.ACTION)})
    assert w.people[0]["link"] == 0 and w.cars[car["id"]]["link"] == 0
    # two cars: the one behind pushes the one in front on
    a = w.add_car(sim.default_design("A"), x, y + 40.0, 90.0)
    b = w.add_car(sim.default_design("B"), x, y + 44.0, 90.0)
    a["v"] = 12.0
    bumped = False
    for _ in range(30):
        w.step_all({})
        bumped |= bool(w.bumps)
    assert w.cars[b["id"]]["v"] > 3.0 and w.cars[a["id"]]["v"] < 12.0, (w.cars[a["id"]]["v"], w.cars[b["id"]]["v"])
    assert bumped, "the bump was counted"
    # a car at speed knocks a person down
    q = w.add_person(1, sim.default_design("Ben"))
    q.update(x=x, y=y + 80.0, yaw=0.0)
    f = w.add_car(sim.default_design("F"), x, y + 70.0, 90.0)
    f["v"] = 12.0
    for _ in range(60):
        w.step_all({})
    assert w.people[1]["move"] in (sim.MOVE_DOWN, sim.MOVE_GETUP) and w.people[1]["hp"] < 100, w.people[1]
    # a robot: punched until it powers down, then reboots; cross, it zaps
    r = w.add_robot(sim.robot_design(0), x, y + 21.5, 90.0)  # (on the ring road, the person just south of it)
    w.people[0].update(x=x, y=y + 20.0, yaw=90.0, move=0, mp=0, hp=100)
    hits = 0
    for _ in range(60 * 20):
        inp = (0.0, 0.0, sim.KICK)
        w.step_all({0: inp, r["id"]: (0.0, 0.0, 0)})
        if w.robots[r["id"]]["hp"] <= 0:
            hits += 1
            break
    assert w.robots[r["id"]]["hp"] <= 0, ("kicked down", w.robots[r["id"]]["hp"])
    assert w.landed[0] >= 6, w.landed[0]
    for _ in range(sim.REBOOT_TICKS + 5):
        w.step_all({r["id"]: (0.0, 0.0, 0)})
    assert w.robots[r["id"]]["hp"] == sim.POWER
    rob = w.robots[r["id"]]
    rob["flags"] |= sim.FLAG_CROSS
    rob["aux"] = 500
    w.people[0].update(x=rob["x"] - sim.ROBOT_R - sim.PERSON_R + 0.1, y=rob["y"], hp=100, bg=0, move=0)
    w.step_all({})
    assert w.people[0]["hp"] < 100 and w.hits[0] >= 1, "zapped"
    # respawn: back to the depot on foot
    w.step_all({0: (0.0, 0.0, sim.RESPAWN)})
    s = c.spawns[0]
    assert abs(w.people[0]["x"] - s[0]) < 0.01 and w.people[0]["link"] == 0
    # the snapshot carries everyone
    frame = wire.pack_snapshot(SCHEMA, 0, 1, w.things())
    back = wire.unpack_snapshot(SCHEMA, frame)
    assert len(back["entities"]) == len(w.people) + len(w.cars) + len(w.robots)
    print(f"    a snapshot of {len(back['entities'])} things: {len(frame)} bytes")


def the_jobs():
    c, w = make_world()
    jobs = w.jobs
    p = w.add_person(0, sim.default_design("Amy"))
    # a delivery: stand at the depot's door, drive to the address
    door = c.places["depot"]
    p.update(x=door[0], y=door[1], lk=0)
    w.step_all({})
    j = jobs.mine.get(0)
    assert j and j["kind"] == city_jobs.DELIVERY and w.people[0]["flags"] & sim.FLAG_PARCEL, j
    tx, ty = j["target"]
    w.people[0].update(x=tx, y=ty, v=0.0)
    w.step_all({})
    assert 0 not in jobs.mine and w.people[0]["cash"] >= 50, (w.people[0]["cash"], jobs.mine)
    assert w.deliveries.get(0) == 1
    # chips: found on foot, counted at the arcade
    cx, cy = c.chips[0]
    w.people[0].update(x=cx, y=cy, link=0)
    w.step_all({})
    assert (w.people[0]["aux"] >> 8) == 1 and 0 in jobs.chips_gone, w.people[0]["aux"]
    cash = w.people[0]["cash"]
    ax, ay, _ = c.places["arcade"]
    w.people[0].update(x=ax, y=ay)
    w.step_all({})
    assert w.people[0]["cash"] == cash + sim.RULES["chip_pay"] and (w.people[0]["aux"] >> 8) == 0
    # the round-up starts at the arcade with no chips held: the robots go rogue, one powered down pays
    r = w.add_robot(sim.robot_design(0), 0.0, 0.0, 0.0)
    w.people[0].update(x=ax + 100.0, y=ay)  # (away, then back)
    w.step_all({})
    w.people[0].update(x=ax, y=ay)
    w.step_all({})
    assert jobs.roundup is not None and w.robots[r["id"]]["flags"] & sim.FLAG_ROGUE, jobs.roundup
    cash = w.people[0]["cash"]
    w.robots[r["id"]]["hp"] = 1
    w.people[0].update(x=w.robots[r["id"]]["x"] - 1.5, y=w.robots[r["id"]]["y"], yaw=0.0, move=0, mp=0)
    for _ in range(40):
        w.step_all({0: (0.0, 0.0, sim.PUNCH)})
        if w.robots[r["id"]]["hp"] <= 0:
            break
    assert w.robots[r["id"]]["hp"] <= 0 and w.people[0]["cash"] == cash + sim.RULES["roundup_pay"]
    assert jobs.roundup is None, "all down: over"
    # a taxi run: in a car at the rank; the passenger gets in at the pickup and out at the stop
    x, y, yaw = road_spot(c)
    car = w.add_car(sim.default_design("Cab"), x, y, yaw)
    w.people[0].update(x=x + 1.0, y=y, lk=0, move=0)
    w.step_all({0: (0.0, 0.0, sim.ACTION)})
    assert w.people[0]["link"] == car["id"] + 1
    rx, ry, _ = c.places["rank"]
    w.cars[car["id"]].update(x=rx, y=ry, v=0.0)
    for _ in range(sim.REBOOT_TICKS + 2):  # (the robot reboots to be a passenger)
        w.step_all({})
    w.cars[car["id"]].update(x=rx, y=ry, v=0.0)
    w.step_all({})
    j = jobs.mine.get(0)
    assert j and j["kind"] == city_jobs.TAXI and j["stage"] == 1, (j, jobs.roundup)
    rid = j["passenger"]
    w.cars[car["id"]].update(x=j["target"][0], y=j["target"][1], v=0.0, u=0.0)
    w.step_all({})
    assert jobs.mine[0]["stage"] == 2 and w.robots[rid]["link"] == car["id"] + 1
    cash = w.people[0]["cash"]
    w.cars[car["id"]].update(x=j["target"][0], y=j["target"][1], v=0.0, u=0.0)
    w.step_all({})
    assert 0 not in jobs.mine and w.people[0]["cash"] >= cash + sim.RULES["taxi_fare"] and w.robots[rid]["link"] == 0
    # a race: the line opens it, the countdown, GO, round the course, paid
    w.people[0]["lk"] = 0
    lx, ly = jobs.race_line()
    w.cars[car["id"]].update(x=lx, y=ly, v=0.0)
    w.step_all({})
    assert jobs.race is not None and jobs.race["state"] == "forming" and car["id"] in jobs.race["cars"]
    jobs.race["go"] = w.tick + 2
    for _ in range(3):
        w.step_all({})
    assert jobs.race["state"] == "racing", jobs.race["state"]
    course = jobs.race["course"]
    for cp in course[1:] + [course[0]]:
        w.cars[car["id"]].update(x=cp[0], y=cp[1])
        w.step_all({})
    assert jobs.race is None and w.people[0]["cash"] >= cash + sim.RULES["race_pay"], (jobs.race, w.people[0]["cash"])
    assert w.races_won.get(0) == 1
    state = json.dumps(jobs.state(w))
    assert len(state) < 4000, len(state)


def the_drivers():
    c, w = make_world("harbour")
    mem = {}
    cars = []
    for k in range(6):
        kk, m = (k * 3 + 1) % (c.cols + 1), (k * 2 + 1) % (c.rows + 1)
        x, y = c.junction(kk, m)
        yaw = 0.0 if k % 2 == 0 else 90.0
        x, y = (x + 8.0, y + city_map.LANE) if yaw == 0.0 else (x - city_map.LANE, y + 8.0)
        cars.append(w.add_car(sim.default_design(f"T{k}"), x, y, yaw)["id"])
    robots = [w.add_robot(sim.robot_design(k), *c.addresses[k * 5 + 2][:3])["id"] for k in range(4)]
    stuck = {cid: 0 for cid in cars}
    worst_stuck = 0
    for tick in range(60 * 60):
        inputs = {}
        for cid in cars:
            inputs[cid] = cpu_brains.drive_car(cid, w.cars[cid], w, mem.setdefault(cid, {}), ((tick * 7919 + cid) % 1000) / 1000)
        for rid in robots:
            inputs[rid] = cpu_brains.drive_robot(rid, w.robots[rid], w, mem.setdefault(rid, {}))
        w.step_all(inputs)
        for cid in cars:
            stuck[cid] = stuck[cid] + 1 if abs(w.cars[cid]["v"]) < 0.3 else 0
            worst_stuck = max(worst_stuck, stuck[cid])
    for cid in cars:
        assert w.cars[cid]["dmg"] < 3000, ("a traffic car crashed", cid, w.cars[cid]["dmg"])
        assert c.surface(w.cars[cid]["x"], w.cars[cid]["y"]) in ("road", "pave"), (cid, c.surface(w.cars[cid]["x"], w.cars[cid]["y"]))
    assert worst_stuck < 60 * 12, ("a traffic car stood still too long", worst_stuck / 60)
    for rid in robots:
        r = w.robots[rid]
        assert c.surface(r["x"], r["y"]) in ("pave", "road", "court", "lot", "grass"), (rid, c.surface(r["x"], r["y"]))
    moved = [rid for rid in robots if abs(w.robots[rid]["x"] - c.addresses[robots.index(rid) * 5 + 2][0]) +
             abs(w.robots[rid]["y"] - c.addresses[robots.index(rid) * 5 + 2][1]) > 3.0]
    assert len(moved) >= 3, ("the robots patrol", moved)
    # a racer round a course
    jobs = w.jobs
    lx, ly = jobs.race_line()
    course = jobs.courses[0]
    import math
    yaw = math.degrees(math.atan2(course[1][1] - ly, course[1][0] - lx))
    racer = w.add_car(sim.default_design("Ace"), lx, ly, yaw)
    jobs.race = {"course": course, "cars": {racer["id"]: 0}, "done": [], "go": w.tick, "state": "racing", "pay": {},
                 "ends": w.tick + 60 * 180}
    rm = {}
    for tick in range(60 * 150):
        w.step_all({racer["id"]: cpu_brains.drive_racer(racer["id"], w.cars[racer["id"]], w, rm, "expert")})
        if jobs.race is None:
            break
    assert jobs.race is None, ("the expert racer finished the course", jobs.race and jobs.race["cars"])
    print(f"    the racer's lap: {tick / 60:.0f} s, worst traffic stop {worst_stuck / 60:.1f} s")


def prediction_no_network():
    """A window predicting its person and its car with the server five ticks away each way: no corrections."""
    c, w = make_world()
    x, y, yaw = road_spot(c)
    for thing in ("person", "car"):
        if thing == "person":
            state = sim.new_person(0, x + 3.0, y, 0.0)
            def step(s, inp, dt):
                n = sim.step_person(s, inp, dt, c)
                n.update(SCHEMA.quantise(n))
                return n
        else:
            st = sim.stats_of(sim.default_design())
            state = sim.new_car(32, x, y, yaw)
            def step(s, inp, dt):
                n = sim.step_car(s, inp, dt, c, st)
                n.update(SCHEMA.quantise(n))
                return n
        state.update(SCHEMA.quantise(state))
        server = dict(state)
        queue = predict.ServerInputQueue(idle=(0.0, 0.0, 0))
        pred = predict.Predictor(step, dict(state), ignore=0.05, log=predict.InputLog(first_seq=1))
        delay = 5
        to_server, to_client = [], []
        corrections = []
        for t in range(600):
            inp = (1.0, 0.3 if (t // 90) % 2 else -0.3, sim.RUN if t % 200 < 100 else 0)
            inp = wire.quantise_input(*inp)
            seq = pred.apply(inp, sim.STEP)
            to_server.append((t + delay, seq, inp, pred.log.previous(2)))
            for due, s_, i_, prev in [m for m in to_server if m[0] == t]:
                queue.push(s_, i_, prev)
            to_server = [m for m in to_server if m[0] > t]
            applied = queue.pop_for_tick()
            server = step(server, applied, sim.STEP)
            to_client.append((t + delay, dict(server), queue.ack()))
            for due, snap, ack in [m for m in to_client if m[0] == t]:
                if ack:
                    err = pred.correct(snap, ack, sim.STEP, sim.compare)
                    if err > 0.05:
                        corrections.append((t, err))
            to_client = [m for m in to_client if m[0] > t]
        assert len(corrections) <= 2, (thing, corrections[:5])


# ---------- the server ----------
def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port, extra=()):
    proc = subprocess.Popen([PY, "city_server.py", "--port", str(port), "--traffic", "2", "--robots", "2", *extra],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={**os.environ, "CITYLAB_DATA": TMP})
    for _ in range(150):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc
        except OSError:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace")
                raise RuntimeError(f"the server stopped: {out[-2000:]}")
            time.sleep(0.1)
    raise RuntimeError("the server didn't start")


def stop(proc):
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        pass


def server_end_to_end():
    from websockets.sync.client import connect
    import city_version
    port = free_port()
    proc = start_server(port)
    try:
        url = f"ws://127.0.0.1:{port}"
        amy = connect(url, compression=None, max_size=None)
        amy.send(json.dumps({"type": "hello", "name": "Amy", "code": "CLUB42", "password": "amy-pass-1",
                             "version": city_version.VERSION}))
        welcome = None
        while welcome is None:
            m = amy.recv(timeout=10)
            if isinstance(m, str) and json.loads(m).get("type") == "welcome":
                welcome = json.loads(m)
        assert welcome["role"] == "learner" and welcome["me"] is not None and "city" in welcome and "cities" in welcome["rules"]
        assert welcome["city"]["blocks"] and welcome["rules"]["bodies"] and welcome["rules"]["looks"]
        assert "tracks" not in welcome["rules"] and "track" not in welcome, "the page tells the games apart by these"
        teacher = connect(url, compression=None, max_size=None)
        teacher.send(json.dumps({"type": "hello", "name": "Teach", "code": "TEACH99", "version": city_version.VERSION}))
        amy.send(json.dumps({"type": "design", "design": {**welcome["design"], "name": "AMY", "body": "rally",
                                                          "points": {"speed": 40, "acceleration": 30, "grip": 30}}}))
        amy.send(json.dumps({"type": "lesson_number", "n": 2}))
        amy.send(json.dumps({"type": "prediction", "value": "60"}))
        amy.send(b"\x07junk")
        snaps, acks, jobs_msgs, rosters, design_ok = 0, set(), 0, 0, None
        t0 = time.time()
        seq = 1
        last_send = 0.0
        me = welcome["me"]
        my_states = []
        while time.time() - t0 < 6.0:
            now = time.time()
            if now - last_send >= 1 / 60:
                last_send = now
                amy.send(wire.pack_input(seq, 0, int(now * 1000) & 0xFFFFFFFF, 1.0, 0.0, sim.RUN))
                seq = (seq + 1) & 0xFFFF
            try:
                m = amy.recv(timeout=0.005)
            except TimeoutError:
                continue
            if isinstance(m, bytes):
                if wire.kind_of(m) == wire.KIND_SNAPSHOT:
                    snap = wire.unpack_snapshot(SCHEMA, m)
                    snaps += 1
                    acks.add(snap["ack"])
                    mine = next((e for e in snap["entities"] if e["id"] == me), None)
                    if mine:
                        my_states.append(mine)
                continue
            d = json.loads(m)
            if d.get("type") == "jobs":
                jobs_msgs += 1
                assert "mine" in d and "cash" in d and "markers" in d, d.keys()
            elif d.get("type") == "roster":
                rosters += 1
                assert any(p["id"] == me for p in d["people"]) and d["cars"] and d["robots"], d
                assert d["mine"]["Amy"] == me
            elif d.get("type") == "design_result":
                design_ok = d["ok"], d.get("problems")
        secs = time.time() - t0
        assert 24 * secs * 0.8 < snaps, ("snapshots", snaps, secs)
        assert len(acks) > 20, ("acks", len(acks))
        assert jobs_msgs >= 3 and rosters >= 1, (jobs_msgs, rosters)
        assert design_ok == (True, []), design_ok
        assert my_states and my_states[-1]["x"] - my_states[0]["x"] > 10.0, ("Amy ran east", my_states[0], my_states[-1])
        kinds = {sim.kind_of(e["id"]) for e in snap["entities"]}
        assert kinds == {"person", "car", "robot"}, kinds
        # the teacher's keys: everyone to the depot, start a race
        teacher.send(json.dumps({"type": "grid"}))
        teacher.send(json.dumps({"type": "start"}))
        t1 = time.time()
        racing = False
        while time.time() - t1 < 4.0:
            try:
                m = teacher.recv(timeout=0.05)
            except TimeoutError:
                continue
            if isinstance(m, str):
                d = json.loads(m)
                if d.get("type") == "jobs" and d.get("race"):
                    racing = True
                    assert d["race"]["state"] in ("forming", "countdown", "racing") and d["race"]["course"]
                    break
        assert racing, "the teacher's Enter opened a street race"
        # F mends the teacher's car; another city goes to every window, with who they are in it
        teacher.send(json.dumps({"type": "fix"}))
        teacher.send(json.dumps({"type": "lesson", "lesson": {"city": "village"}}))
        got = {}
        t2 = time.time()
        while len(got) < 2 and time.time() - t2 < 6.0:
            for who, ws in (("amy", amy), ("teacher", teacher)):
                if who in got:
                    continue
                try:
                    m = ws.recv(timeout=0.02)
                except TimeoutError:
                    continue
                if isinstance(m, str) and json.loads(m).get("type") == "city":
                    got[who] = json.loads(m)
        assert set(got) == {"amy", "teacher"}, ("the new city reached", sorted(got))
        assert got["amy"]["city"]["key"] == "village" and got["amy"]["me"] == me, got["amy"]["me"]
        assert city_map.City(got["teacher"]["city"]).name, "the window can build the new city"
        amy.close()
        teacher.close()
    finally:
        stop(proc)


def the_sounds():
    """(Step 7) What the city sounds like, worked out each frame: the mixer given pretend sounds, so no sound card is
    needed. Driving: the engine note rises with the speed and the tyres squeal with the handbrake; a punch starts its
    whoosh and lands its thump; a robot hit clangs; near the park the crowd murmurs, far from it it is quiet."""
    import city_sound

    class Sfx:
        PLAYING = 2

        def __init__(self):
            self.volume, self.rate, self.on = 0.0, 1.0, False

        def status(self):
            return self.PLAYING if self.on else 1

        def setVolume(self, v):
            self.volume = v

        def setPlayRate(self, r):
            self.rate = r

        def setLoop(self, on):
            pass

        def play(self):
            self.on = True

        def stop(self):
            self.on = False

    class Base:
        class loader:
            @staticmethod
            def loadSfx(path):
                return Sfx()
    snd = city_sound.CitySounds(Base(), on=True)
    played = []
    snd.play = lambda name, volume=1.0, rate=1.0: played.append(name) if volume > 0.02 else None
    c, w = make_world()
    x, y, yaw = road_spot(c)
    me = sim.new_person(0, x, y, yaw)
    car = sim.new_car(32, x, y, yaw)
    things = {0: me, 32: dict(car, v=6.0, flags=0)}
    snd.frame(0.0, 0, things, 32, c)
    slow = (snd.loops["engine"].volume, snd.loops["engine"].rate)
    things[32] = dict(car, v=25.0, flags=sim.FLAG_HANDBRAKE)
    snd.frame(0.1, 0, things, 32, c)
    fast = (snd.loops["engine"].volume, snd.loops["engine"].rate)
    assert fast[0] > slow[0] and fast[1] > slow[1], ("the engine note rises", slow, fast)
    assert "skid" in snd.loops, "the tyres squeal with the handbrake on"
    things[32] = dict(car, v=0.0, flags=0)
    snd.frame(0.2, 0, things, 32, c)
    assert "bump" in played, ("a car stopped dead bumps", played)
    snd.frame(0.3, 0, {0: me}, None, c)
    assert "engine" not in snd.loops, "out of the car the engine stops"
    played.clear()
    snd.frame(0.4, 0, {0: dict(me, move=sim.MOVE_PUNCH)}, None, c)
    rid = 128
    robot = sim.new_robot(rid, x + 1.0, y, yaw)
    snd.landed({0: me, rid: dict(robot, hp=robot["hp"] - sim.HIT[sim.MOVE_KICK])}, {0: me, rid: robot}, (x, y))
    assert "f_whoosh" in played and "f_kick" in played and "f_metal" in played, played
    park = next(b for b in c.blocks if b["kind"] == "park")
    snd.frame(0.5, 0, {0: dict(me, x=(park["x0"] + park["x1"]) / 2, y=(park["y0"] + park["y1"]) / 2)}, None, c)
    near = snd.loops.get("crowd").volume if "crowd" in snd.loops else 0.0
    snd.frame(0.6, 0, {0: dict(me, x=c.xmax + 200, y=c.ymax + 200)}, None, c)
    assert near > 0.1 and "crowd" not in snd.loops, ("the park's crowd near it, quiet far away", near)


def windows():
    """The window offline (step 1): the city drawn and a person running round it, on medium and on lines. (Online
    windows come in step 5.)"""
    assert os.path.exists("city_client.py"), "city_client.py is not written yet"
    env = {**os.environ, "CITYLAB_DATA": TMP}
    for gfx in ("medium", "lines"):
        shot = os.path.join(TMP, f"offline_{gfx}.png")
        r = subprocess.run([PY, "city_client.py", "--offline", "--offscreen", "--demo", "--mute", "--gfx", gfx,
                            "--after", "4", "--screenshot", shot], capture_output=True, text=True, timeout=180, env=env)
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
        assert os.path.exists(shot) and os.path.getsize(shot) > 20000, f"no {gfx} screenshot"
        assert "Traceback" not in r.stderr, r.stderr[-1500:]
    # (step 2) driving at night with the traffic about: the cars drawn, the headlights on
    shot = os.path.join(TMP, "offline_drive.png")
    r = subprocess.run([PY, "city_client.py", "--offline", "--offscreen", "--demo-drive", "--mute", "--gfx", "medium",
                        "--time", "night", "--traffic", "8", "--after", "5", "--screenshot", shot],
                       capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stdout[-1500:] + r.stderr[-1500:]
    assert os.path.exists(shot) and os.path.getsize(shot) > 20000, "no driving screenshot"
    # (step 3) a fight with a robot: the robots drawn, the sparks, the health bar
    shot = os.path.join(TMP, "offline_fight.png")
    r = subprocess.run([PY, "city_client.py", "--offline", "--offscreen", "--demo-fight", "--mute", "--gfx", "medium",
                        "--robots", "4", "--after", "8", "--screenshot", shot],
                       capture_output=True, text=True, timeout=180, env=env)
    assert r.returncode == 0 and "Traceback" not in r.stderr, r.stdout[-1500:] + r.stderr[-1500:]
    assert "not drawn" not in r.stdout, r.stdout[-800:]
    assert os.path.exists(shot) and os.path.getsize(shot) > 20000, "no fighting screenshot"
    # (step 4) the jobs: a delivery's beam and arrow, a street race with the computer's racers
    for job in ("delivery", "race"):
        shot = os.path.join(TMP, f"offline_{job}.png")
        r = subprocess.run([PY, "city_client.py", "--offline", "--offscreen", "--demo-job", job, "--mute", "--gfx", "medium",
                            "--after", "20" if job == "race" else "6", "--screenshot", shot],
                           capture_output=True, text=True, timeout=180, env=env)
        assert r.returncode == 0 and "Traceback" not in r.stderr, r.stdout[-1500:] + r.stderr[-1500:]
        assert os.path.exists(shot) and os.path.getsize(shot) > 20000, f"no {job} screenshot"


def lessons():
    """(Step 6) Mission 1 done as the Garage and the code panel do it, over the wire: a new name (1a), two points
    changed (1b), a colour (1c), then a change in the code (1d); each build answered, each objective ticked in the
    learner's missions message; then the prediction box (mission 2) kept."""
    from websockets.sync.client import connect
    import city_version
    port = free_port()
    proc = start_server(port)
    try:
        ws = connect(f"ws://127.0.0.1:{port}", compression=None, max_size=None)
        ws.send(json.dumps({"type": "hello", "name": "Dev", "code": "CLUB42", "password": "dev-pass-1",
                            "version": city_version.VERSION}))

        def wait(kind, test=lambda m: True, secs=10):
            end = time.time() + secs
            while time.time() < end:
                m = ws.recv(timeout=max(0.1, end - time.time()))
                if isinstance(m, str):
                    d = json.loads(m)
                    if d.get("type") == kind and test(d):
                        return d
            raise AssertionError(f"no {kind} message")
        d = copy.deepcopy(wait("welcome")["design"])
        builds = [({"name": "DEVI"}, False), ({"points": {"speed": 40, "acceleration": 30, "grip": 30}}, False),
                  ({"colour": [60, 130, 230]}, False), ({"body": "muscle"}, True)]
        for change, by_code in builds:
            d.update(change)
            ws.send(json.dumps({"type": "design", "design": d, "code": by_code}))
            r = wait("design_result")
            assert r["ok"], r.get("problems")
        m = wait("missions", lambda m: sum(x["done"] for x in m["missions"]) >= 4)
        done = {x["id"] for x in m["missions"] if x["done"]}
        assert {"1a", "1b", "1c", "1d"} <= done, done
        ws.send(json.dumps({"type": "prediction", "value": 42}))
        m = wait("missions", lambda m: m.get("prediction") == 42)
        ws.close()
    finally:
        stop(proc)


def panels():
    """(Step 6) The side panel: a learner's Mission, Garage (with the code panel) and AI card tabs and the teacher's
    Controls, drawn from a server's messages; offline the Garage. Each window must draw it without a mistake."""
    port = free_port()
    proc = start_server(port)
    env = {**os.environ, "CITYLAB_DATA": TMP}
    url = f"ws://127.0.0.1:{port}"
    try:
        runs = [("teacher", ["--host", url, "--teacher", "--tab", "teacher"]),
                ("missions", ["--host", url, "--name", "Cara", "--password", "cara-pass-1", "--tab", "missions"]),
                ("garage", ["--host", url, "--name", "Cara", "--password", "cara-pass-1", "--tab", "garage",
                            "--show-code"]),
                ("ai", ["--host", url, "--name", "Cara", "--password", "cara-pass-1", "--tab", "ai"]),
                ("offline_garage", ["--offline", "--tab", "garage", "--show-code"])]
        for what, extra in runs:
            shot = os.path.join(TMP, f"panel_{what}.png")
            r = subprocess.run([PY, "city_client.py", *extra, "--offscreen", "--mute", "--gfx", "low", "--after", "6",
                                "--screenshot", shot], capture_output=True, text=True, timeout=180, env=env)
            out = r.stdout + r.stderr
            assert r.returncode == 0 and "Traceback" not in out, (what, out[-2000:])
            assert os.path.exists(shot) and os.path.getsize(shot) > 20000, f"no {what} screenshot"
    finally:
        stop(proc)


def online_windows():
    """(step 5) The server with a teacher's window and a learner's, over pretend school Wi-Fi (60 ms each way, 15 ms
    of jitter): both log in and draw the city; the learner runs, the teacher walks to a car, gets in and drives; the
    prediction is rarely put right; then the learner's window stops for 3 s and picks up again."""
    port = free_port()
    proc = start_server(port)
    env = {**os.environ, "CITYLAB_DATA": TMP, "CLUBCODERS_LAG": "60,15"}
    url = f"ws://127.0.0.1:{port}"
    try:
        shots = {who: os.path.join(TMP, f"online_{who}.png") for who in ("teacher", "learner")}
        teacher = subprocess.Popen([PY, "city_client.py", "--host", url, "--teacher", "--offscreen", "--demo-drive",
                                    "--mute", "--gfx", "low", "--after", "24", "--screenshot", shots["teacher"]],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        learner = subprocess.run([PY, "city_client.py", "--host", url, "--name", "Ben", "--password", "ben-pass-1",
                                  "--offscreen", "--demo", "--mute", "--gfx", "low", "--freeze-at", "14", "--after", "24",
                                  "--screenshot", shots["learner"]], capture_output=True, text=True, timeout=240, env=env)
        t_out, _ = teacher.communicate(timeout=240)
        for who, out, code in (("teacher", t_out, teacher.returncode), ("learner", learner.stdout + learner.stderr,
                                                                       learner.returncode)):
            assert code == 0 and "Traceback" not in out, (who, out[-2000:])
            assert os.path.exists(shots[who]) and os.path.getsize(shots[who]) > 20000, f"no {who} screenshot"
            perfs = [json.loads(line.split(" ", 1)[1].rsplit(" lead", 1)[0]) for line in out.splitlines()
                     if line.startswith("perf {")]
            assert perfs and perfs[-1]["ping"] >= 100, (who, "the pretend Wi-Fi's round trip", perfs[-1:])
            corr = perfs[-1]["corr"]
            print(f"    {who}: {corr} corrections in 20 s, ping {perfs[-1]['ping']} ms, key delay {perfs[-1]['ctrl']} ms")
            assert corr is not None and corr <= 20, (who, "corrections", corr)  # (0 to 5 alone; 17 once on a loaded laptop)
        assert "City Lab: Harbour City built" in t_out, "the teacher's window drew the server's city"
    finally:
        stop(proc)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    check("the three cities: generated the same twice, buildings inside their blocks and apart, addresses on the "
          "pavement, spawns in the yard, bays on the road, the surfaces, the roads, the walls, the edge, the ramps", the_city)
    check("a person: walks, runs, turns to the move, jumps, punches and blocks, is stopped by a wall, gets up", person_step)
    check("a car: Kart Lab's pace on the road, brakes, turns, rolls to a stop with nobody in it, the pavement drags, "
          "a wall damages and holds it, a wreck crawls, the garage mends, the ramp jumps, still is still", car_step)
    check("the world: in and out of a car, the driver carried, a shove from behind, a person knocked down by a car, "
          "a robot kicked down and rebooted, a zap, respawn, the snapshot", the_world)
    check("the jobs: a delivery paid, chips found and cashed, the round-up, a taxi run, a street race won", the_jobs)
    check("the computer's drivers: six traffic cars drive a minute without a crash, the robots patrol, an expert "
          "racer completes a course", the_drivers)
    check("the prediction: a person and a car predicted five ticks ahead of the server with no corrections", prediction_no_network)
    check("the sounds: the engine rises with the speed, the tyres squeal, a bump, a punch's whoosh and a robot's "
          "clang, the park's crowd only near the park", the_sounds)
    if mode in ("server", "online", "all"):
        check("the server with two windows: welcome, roster, jobs, 30 snapshots a second, acks, a design built, "
              "Amy runs, the teacher's Enter opens a street race", server_end_to_end)
    if mode in ("server", "online", "all"):
        check("the lessons: mission 1 a to d built as the Garage and the code panel build them, each ticked; a "
              "prediction kept", lessons)
        check("the side panel: a learner's Mission, Garage and code, AI card; the teacher's Controls; offline the "
              "Garage", panels)
    if mode in ("online", "all"):
        check("two windows online over pretend school Wi-Fi: a teacher driving and a learner running, the prediction "
              "rarely put right, a window that stops for 3 s picks up again", online_windows)
    if mode in ("window", "all"):
        check("the window offline: the city drawn and a person running round it, on medium and on lines; a car "
              "driven through the traffic at night; a robot kicked; a delivery and a street race", windows)
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} passed" + (f"; FAILED: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)
