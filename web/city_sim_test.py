"""The browser's City Lab steps and prediction (city_sim.js, predict.js, pymath.js) against City Lab's own Python.

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\city_sim_test.py      (from the ClubCodersAI folder)

Runs the same people and cars through city/city_sim.py and, with node, through city_sim.js, in all three cities
(Harbour City, Little Lab and Metro Lab, built in the page from the JSON the server sends), and checks (CHANGE 201):
  - the city's questions: collide (buildings, trees, lamp posts, the city's edge, for a person's, a car's and a
    robot's radius), surface, the ramps' height, the kerb crossed, the block under a point and the yards: thousands
    of points give the same answers to the last bit;
  - the person's step: hundreds of random walks (600 ticks each: walking and running every way, turning, jumping,
    punches, kicks and blocks held and let go, knocked down and getting up, hurt, health creeping back, a parcel
    carried, chips held, sitting in a car, into the buildings, the posts and the edge) give the server's wire numbers
    tick for tick, as the server applies them (step, quantise), and the same numbers to the last bit before the
    rounding too;
  - the car's step: hundreds of random drives (the throttle, braking, reversing, drifts, the handbrake, the clutch
    dropped, off the car park's ramps and through the air, over the kerbs, on the pavements, the grass and the quay,
    into the buildings and posts with the damage they do, wrecked, mended on the garage's forecourt, nobody at the
    wheel) the same, tick for tick and before the rounding;
  - the record: wire.js's CITY_FIELDS and city_sim.js's SCHEMA_FIELDS are city_sim.SCHEMA_FIELDS, field for field;
    the steps' numbers (the speeds, the moves' lengths, the car's grips) are city_sim's;
  - compare() is city_sim.compare (the prediction's yardstick);
  - the prediction: a Predictor stepping a person or a car with snapshots arriving late, jittered and some skipped,
    with shoves, knockdowns and bumps only the server knew of and the sequence numbers wrapping, makes the same
    corrections with the same errors as engine.predict's with city_sim's steps, and ends on the server's state;
  - the fingerprint: the runs' numbers are the ones city_sim_golden.json recorded for city_sim.SIM_VERSION (a change
    to the steps that wasn't meant to change them fails here; one that was: raise SIM_VERSION and run this with
    --record in the same commit).
Exit code 0 = every check passed. Passes with a note if node isn't installed.
"""
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# City Lab: games/citylab beside web/ in the public repository, city/ two folders up in the working folder
CITY = next((p for p in (os.path.join(os.path.dirname(HERE), "games", "citylab"),
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "city"))
             if os.path.isdir(p)), None)
sys.path.insert(0, CITY)
import city_version  # noqa: E402,F401  (the engine and the other games' folders on the path)
import city_map  # noqa: E402
import city_sim as sim  # noqa: E402
from engine import predict, wire  # noqa: E402

SCHEMA = wire.Schema("city", sim.SCHEMA_FIELDS)
JS_FILES = ["pymath.js", "track.js", "kart_sim.js", "city_sim.js", "predict.js", "wire.js"]
PEOPLE = {"harbour": 300, "village": 100, "metro": 100}
CARS = {"harbour": 400, "village": 120, "metro": 120}
TICKS = 600
RAW_RUNS = 200            # runs whose numbers before the rounding are compared too (each kind)
POINTS = 6000             # points each city's questions are asked about
PREDICT_RUNS = 30         # of each kind
SEED = 20261029
GOLDEN = os.path.join(HERE, "city_sim_golden.json")
CONSTANTS = ["STEP", "WALK", "RUN_SPEED", "TURN_RATE", "PERSON_R", "JUMP_V", "GRAVITY", "CAR_R", "ROLL", "HB_GRIP",
             "HB_BRAKE", "HB_TURN", "HB_SCRUB", "LAUNCH_SPEED", "LAUNCH_ACCEL", "LAUNCH_GRIP", "LAUNCH_SPIN", "PAVE_DRAG",
             "PAVE_GRIP", "GRASS_DRAG", "GRASS_ACCEL", "GRASS_GRIP", "KERB_BUMP", "DAMAGE_MAX", "HIT_SPEED", "HIT_WALL",
             "BUMP_GRACE", "WRECK_SPEED", "REPAIR_TICK", "REPAIR_GARAGE", "GARAGE_STOP", "HEALTH", "DOWN_HEALTH",
             "REGEN_TICKS", "ENTER_REACH", "EXIT_SPEED", "ROBOT_R", "SIM_VERSION"]
MAP_CONSTANTS = ["ROAD", "PAVE", "LANE", "PARK_LANE", "KERB_H", "VERGE", "INSET", "RAMP_LEN", "RAMP_H"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def wire_line(k):
    return ",".join(map(str, SCHEMA.ints(k)))


def md5(parts):
    return hashlib.md5(";".join(parts).encode()).hexdigest()


RAW = ["x", "y", "z", "vz", "yaw", "v", "u"]


# ---------- where things start ----------
def spot(rng, city, kind):
    """A place to start: anywhere in the city and its verge, by a building's wall or corner, by a tree or a lamp post,
    on a road's lane, by the edge, on a car park's run-up to a ramp, on the garage's forecourt. Returns (x, y, yaw)."""
    r = rng.random()
    e = city.edge
    if r < 0.2:
        return rng.uniform(e[0] - 2, e[2] + 2), rng.uniform(e[1] - 2, e[3] + 2), rng.uniform(-180, 180)
    if r < 0.42 and city.buildings:
        b = rng.choice(city.buildings)
        side = rng.randrange(4)
        out = rng.uniform(-0.3, 2.5)
        x = {0: b["x0"] - out, 1: b["x1"] + out}.get(side, rng.uniform(b["x0"] - 1, b["x1"] + 1))
        y = {2: b["y0"] - out, 3: b["y1"] + out}.get(side, rng.uniform(b["y0"] - 1, b["y1"] + 1))
        if side < 2:
            y = rng.uniform(b["y0"] - 1, b["y1"] + 1)
        return x, y, rng.uniform(-180, 180)
    if r < 0.55:
        px, py = rng.choice(city.trees)[:2] if city.trees and rng.random() < 0.5 else rng.choice(city.lamps)
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0.2, 3.0)
        return px + math.cos(a) * d, py + math.sin(a) * d, math.degrees(a) + 180 + rng.uniform(-30, 30)
    if r < 0.7:
        k, m = rng.randint(0, city.cols), rng.randint(0, city.rows)
        x, y = city.junction(k, m)
        if rng.random() < 0.5:
            return x + rng.uniform(-30, 30), y + rng.choice((-1, 1)) * rng.uniform(0, 7), rng.choice((0.0, 180.0)) + rng.uniform(-20, 20)
        return x + rng.choice((-1, 1)) * rng.uniform(0, 7), y + rng.uniform(-30, 30), rng.choice((90.0, -90.0)) + rng.uniform(-20, 20)
    if r < 0.8:  # (by the edge, heading out)
        side = rng.randrange(4)
        x = {0: e[0] + rng.uniform(0, 4), 1: e[2] - rng.uniform(0, 4)}.get(side, rng.uniform(e[0], e[2]))
        y = {2: e[1] + rng.uniform(0, 4), 3: e[3] - rng.uniform(0, 4)}.get(side, rng.uniform(e[1], e[3]))
        return x, y, (180.0, 0.0, -90.0, 90.0)[side] + rng.uniform(-40, 40)
    if r < 0.9 and city.ramps:  # (a ramp's run-up, facing it)
        rp = rng.choice(city.ramps)
        yr = math.radians(rp["yaw"])
        back = rng.uniform(-2, 14)
        return rp["x"] - math.cos(yr) * back, rp["y"] - math.sin(yr) * back, rp["yaw"] + rng.uniform(-8, 8)
    z = city.zones.get("garage") or city.zones.get("depot")
    return rng.uniform(z[0], z[2]), rng.uniform(z[1], z[3]), rng.uniform(-180, 180)


# ---------- the people ----------
def person_start(rng, city):
    x, y, yaw = spot(rng, city, "person")
    p = sim.new_person(rng.randint(0, 31), x, y, yaw)
    r = rng.random()
    if r < 0.25:  # (a move running)
        p["move"] = rng.choice((1, 2, 3, 4, 5, 6))
        p["mp"] = rng.randint(0, sim.MOVE_TICKS.get(p["move"], 30))
    p["hp"] = rng.choice((sim.HEALTH, sim.HEALTH, rng.randint(1, 99), rng.randint(0, 10)))
    p["aux"] = (rng.choice((0, 0, rng.randint(1, 40))) << 8) | rng.randint(0, sim.REGEN_TICKS - 1)
    p["flags"] = rng.choice((0, 0, sim.FLAG_PARCEL, sim.FLAG_RUN | sim.FLAG_PARCEL))
    p["lk"], p["bg"] = rng.choice((0, 0, rng.randint(1, 40))), rng.choice((0, 0, rng.randint(1, 60)))
    p["cash"] = rng.randint(0, 900)
    if rng.random() < 0.2:  # (in the air)
        p["z"], p["vz"] = rng.uniform(0, 0.8), rng.uniform(-3, 5.6)
    if rng.random() < 0.3:
        p["v"] = rng.uniform(0, 6.5)
    if rng.random() < 0.06:  # (sitting in a car)
        p["link"] = rng.randint(33, 60)
    p.update(SCHEMA.quantise(p))
    return p


def person_inputs(rng, ticks):
    """Held inputs as wire integers: [move x x100, move y x100, buttons] per tick; the taps (punch, kick, jump) on one
    tick now and then."""
    out = []
    while len(out) < ticks:
        hold = rng.randint(1, 50)
        r = rng.random()
        if r < 0.2:
            mx, my = 0.0, 0.0
        else:
            a = rng.uniform(-math.pi, math.pi)
            mag = rng.choice((1.0, 1.0, rng.uniform(0, 1.4), rng.uniform(0.05, 0.15)))
            mx, my = math.cos(a) * mag, math.sin(a) * mag
        held = (sim.RUN if rng.random() < 0.4 else 0) | (sim.BLOCK if rng.random() < 0.12 else 0)
        mx, my, held = wire.quantise_input(mx, my, held)
        for j in range(hold):
            tap = 0
            if rng.random() < 0.05:
                tap = rng.choice((sim.PUNCH, sim.KICK, sim.JUMP, sim.JUMP | sim.RUN, sim.PUNCH | sim.KICK))
            out.append([round(mx * 100), round(my * 100), held | tap])
    return out[:ticks]


def run_people(rng, cities):
    runs, raws, cover = [], {}, dict.fromkeys(
        ("walking", "running", "turning", "in the air", "punching", "kicking", "blocking", "down", "getting up", "hurt",
         "health back", "into a building", "against a post", "at the edge", "in a car", "carrying a parcel"), 0)
    for name, count in PEOPLE.items():
        city = cities[name]
        for _ in range(count):
            p = person_start(rng, city)
            start = dict(p)
            inputs = person_inputs(rng, TICKS)
            lines, raw = [], []
            for th, sr, bt in inputs:
                was = p
                p = sim.step_person(p, (th / 100, sr / 100, bt), sim.STEP, city)
                if len(runs) < RAW_RUNS:
                    raw.append([p[k] for k in RAW])
                p.update(SCHEMA.quantise(p))
                lines.append(wire_line(p))
                cover["walking"] += 0 < p["v"] and not p["flags"] & sim.FLAG_RUN
                cover["running"] += bool(p["flags"] & sim.FLAG_RUN)
                cover["turning"] += p["yaw"] != was["yaw"]
                cover["in the air"] += bool(p["flags"] & sim.FLAG_AIR)
                cover["punching"] += p["move"] == sim.MOVE_PUNCH
                cover["kicking"] += p["move"] == sim.MOVE_KICK
                cover["blocking"] += p["move"] == sim.MOVE_BLOCK
                cover["down"] += p["move"] == sim.MOVE_DOWN
                cover["getting up"] += p["move"] == sim.MOVE_GETUP
                cover["hurt"] += p["move"] == sim.MOVE_HURT
                cover["health back"] += p["hp"] > was["hp"]
                _x, _y, hit = city.collide(was["x"] + (p["x"] - was["x"]) * 1.5, was["y"] + (p["y"] - was["y"]) * 1.5, sim.PERSON_R)
                cover["into a building"] += hit == "building"
                cover["against a post"] += hit == "post"
                cover["at the edge"] += hit == "edge"
                cover["in a car"] += bool(p["link"])
                cover["carrying a parcel"] += bool(p["flags"] & sim.FLAG_PARCEL)
            if raw:
                raws[len(runs)] = raw
            runs.append({"city": name, "start": start, "inputs": inputs, "md5": md5(lines), "raw": len(runs) < RAW_RUNS,
                         "_lines": lines})
    return runs, raws, cover


# ---------- the cars ----------
def car_start(rng, city):
    x, y, yaw = spot(rng, city, "car")
    k = sim.new_car(rng.randint(32, 127), x, y, yaw)
    k["v"] = rng.choice((0.0, rng.uniform(-5, 30), rng.uniform(5, 22)))
    k["u"] = rng.choice((0.0, rng.uniform(-3, 3)))
    k["dmg"] = rng.choice((0, 0, rng.randint(0, sim.DAMAGE_MAX), sim.DAMAGE_MAX))
    k["flags"] = rng.choice((0, 0, sim.FLAG_DRIFT_L, sim.FLAG_DRIFT_R))
    k["bg"], k["lk"] = rng.choice((0, 0, rng.randint(1, sim.BUMP_GRACE))), rng.choice((0, rng.randint(0, 20)))
    k["link"] = rng.choice((0, rng.randint(1, 32)))
    if rng.random() < 0.15:  # (in the air, or on a ramp)
        k["z"], k["vz"] = rng.uniform(0, 2.0), rng.uniform(-4, 4)
    if rng.random() < 0.05:
        k["steer"] = rng.uniform(-1, 1)
    k.update(SCHEMA.quantise(k))
    pts = {s: rng.randint(10, 60) for s in sim.STATS}
    design = sim.fit_design({"points": pts})
    return design, k


def car_inputs(rng, ticks):
    out = []
    while len(out) < ticks:
        hold = rng.randint(1, 45)
        r = rng.random()
        th = 1.0 if r < 0.6 else 0.0 if r < 0.7 else -1.0 if r < 0.82 else rng.uniform(-1, 1)
        r = rng.random()
        st = rng.choice((-1.0, 1.0)) if r < 0.3 else 0.0 if r < 0.5 else rng.uniform(-1, 1)
        bt = (sim.DRIFT if rng.random() < 0.35 else 0) | (sim.HANDBRAKE if rng.random() < 0.07 else 0) | \
            (sim.LAUNCH if rng.random() < 0.08 else 0)
        t, s, b = wire.quantise_input(th, st, bt)
        out += [[round(t * 100), round(s * 100), b]] * hold
    return out[:ticks]


def run_cars(rng, cities):
    runs, raws, cover = [], {}, dict.fromkeys(
        ("drifting", "handbrake", "wheelspin", "in the air", "up a ramp", "over a kerb", "on the pavement", "on the grass",
         "on the quay", "into a building", "against a post", "at the edge", "damaged", "wrecked", "mended at the garage",
         "reversing", "nobody driving"), 0)
    for name, count in CARS.items():
        city = cities[name]
        for _ in range(count):
            design, k = car_start(rng, city)
            st = sim.stats_of(design)
            driven = rng.random() < 0.9
            start = dict(k)
            inputs = car_inputs(rng, TICKS)
            lines, raw = [], []
            for th, sr, bt in inputs:
                was = k
                k = sim.step_car(k, (th / 100, sr / 100, bt), sim.STEP, city, st, driven=driven)
                if len(runs) < RAW_RUNS:
                    raw.append([k[f] for f in RAW])
                k.update(SCHEMA.quantise(k))
                lines.append(wire_line(k))
                cover["drifting"] += bool(k["flags"] & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R))
                cover["handbrake"] += bool(k["flags"] & sim.FLAG_HANDBRAKE)
                cover["wheelspin"] += bool(k["flags"] & sim.FLAG_WHEELSPIN)
                cover["in the air"] += bool(k["flags"] & sim.FLAG_CAR_AIR)
                cover["up a ramp"] += city.ramp_height(k["x"], k["y"]) > 0.0 and k["z"] > 0.0
                cover["over a kerb"] += city.kerb_between(was["x"], was["y"], k["x"], k["y"])
                surf = city.surface(k["x"], k["y"])
                cover["on the pavement"] += surf == "pave"
                cover["on the grass"] += surf == "grass"
                cover["on the quay"] += surf == "quay"
                _x, _y, hit = city.collide(k["x"], k["y"], sim.CAR_R + 0.02)
                cover["into a building"] += hit == "building"
                cover["against a post"] += hit == "post"
                cover["at the edge"] += hit == "edge"
                cover["damaged"] += k["dmg"] > was["dmg"]
                cover["wrecked"] += bool(k["flags"] & sim.FLAG_WRECKED)
                cover["mended at the garage"] += was["dmg"] - k["dmg"] == sim.REPAIR_GARAGE
                cover["reversing"] += k["v"] < 0
                cover["nobody driving"] += not driven
            if raw:
                raws[len(runs)] = raw
            runs.append({"city": name, "design": design, "start": start, "inputs": inputs, "driven": driven,
                         "md5": md5(lines), "raw": len(runs) < RAW_RUNS, "_lines": lines})
    return runs, raws, cover


# ---------- the city's questions ----------
def make_points(rng, cities):
    cases = []
    for name, city in cities.items():
        out = []
        for _ in range(POINTS):
            x, y, _yaw = spot(rng, city, "person")
            r = rng.choice((sim.PERSON_R, sim.CAR_R, sim.ROBOT_R, 0.3))
            x2, y2 = x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)
            cx, cy, hit = city.collide(x, y, r)
            out.append({"p": [x, y, r, x2, y2], "collide": [cx, cy, hit], "surface": city.surface(x, y),
                        "ramp": city.ramp_height(x, y), "kerb": city.kerb_between(x, y, x2, y2),
                        "block": city.block_index(x, y),
                        "zones": [city.in_zone(z, x, y) for z in ("depot", "garage", "rank", "arcade")]})
        cases.append({"city": name, "points": out})
    return cases


# ---------- compare() ----------
def make_compares(rng):
    cases = []
    for _ in range(3000):
        a = {"x": rng.uniform(-50, 50), "y": rng.uniform(-50, 50), "yaw": rng.uniform(-180, 180), "v": rng.uniform(-5, 25)}
        b = dict(a)
        if rng.random() < 0.7:
            b.update(x=a["x"] + rng.uniform(-0.2, 0.2), y=a["y"] + rng.uniform(-0.2, 0.2), yaw=(a["yaw"] + rng.uniform(-200, 200) + 180) % 360 - 180,
                     v=a["v"] + rng.uniform(-1, 1))
        for k in ("move", "link", "hp", "cash", "dmg", "aux", "job"):
            a[k] = rng.randint(0, 3)
            b[k] = a[k] if rng.random() < 0.9 else rng.randint(0, 3)
        cases.append({"a": a, "b": b, "out": sim.compare(a, b)})
    return cases


# ---------- the prediction (Python) ----------
def make_predicts(rng, city):
    cases = []
    for c in range(PREDICT_RUNS * 2):
        kind = "person" if c % 2 == 0 else "car"
        if kind == "person":
            s = person_start(rng, city)
            s.update(link=0, move=0, mp=0)
            design = None
            inputs = person_inputs(rng, TICKS)
        else:
            design, s = car_start(rng, city)
            s["dmg"] = min(s["dmg"], sim.DAMAGE_MAX - 1)
            inputs = car_inputs(rng, TICKS)
        s.update(SCHEMA.quantise(s))
        start = {n: s[n] for n in SCHEMA.names}
        st = sim.stats_of(design) if design else None
        surprises = {rng.randint(40, TICKS - 60): rng.choice(("shove", "shove", "knock", "hit")) for _ in range(3)}
        first_seq = rng.choice((0, 65400 + rng.randint(0, 135), rng.randint(1, 65535)))
        server, k = [], dict(start)
        for t, (th, sr, bt) in enumerate(inputs):
            inp = (th / 100, sr / 100, bt)
            k = sim.step_person(k, inp, sim.STEP, city) if kind == "person" else sim.step_car(k, inp, sim.STEP, city, st)
            what = surprises.get(t)
            if what == "shove":  # (a car, a robot or another person pushed it: the server's contacts)
                k["x"] += rng.uniform(-0.6, 0.6)
                k["y"] += rng.uniform(-0.6, 0.6)
            elif what == "knock" and kind == "person":
                k["hp"] = max(0, k["hp"] - 15)
                sim.knock_down(k)
            elif what == "knock" or what == "hit":
                if kind == "person":
                    k["hp"] = max(0, k["hp"] - 8)
                    k["move"], k["mp"] = sim.MOVE_HURT, 0
                else:
                    k["dmg"] = min(sim.DAMAGE_MAX, k["dmg"] + 900)
                    k["v"] *= 0.7
            k.update(SCHEMA.quantise(k))
            server.append({n: k[n] for n in SCHEMA.names})
        deliver = [[] for _ in range(TICKS + 1)]
        delay, at = rng.randint(2, 10), 0
        for t in range(TICKS - 1):
            if rng.random() < 0.08:
                continue
            at = min(TICKS, max(at, t + delay + rng.choice((0, 0, 0, 1, 2, 5))))
            deliver[at].append(t)
        deliver[TICKS].append(TICKS - 1)
        cases.append({"kind": kind, "city": city.key, "design": design, "start": start, "inputs": inputs,
                      "server": server, "deliver": deliver, "first_seq": first_seq, "surprises": len(surprises)})
    return cases


def run_predict_py(case, city):
    st = sim.stats_of(case["design"]) if case["design"] else None

    def step(state, inp, dt):
        n = sim.step_person(state, inp, dt, city) if case["kind"] == "person" else sim.step_car(state, inp, dt, city, st)
        n.update(SCHEMA.quantise(n))
        return n

    p = predict.Predictor(step, dict(case["start"]), ignore=0.05, log=predict.InputLog(first_seq=case["first_seq"]))
    seqs, errs = [], []
    for t in range(TICKS + 1):
        if t < TICKS:
            th, sr, bt = case["inputs"][t]
            seqs.append(p.apply((th / 100, sr / 100, bt), sim.STEP))
        for j in case["deliver"][t]:
            ack = seqs[j]
            if ack == 0:
                continue  # (city_client: the server hasn't applied an input of ours yet)
            err = p.correct(dict(case["server"][j]), ack, sim.STEP, sim.compare)
            errs.append(None if err == math.inf else err)
    return {"errs": errs, "corrections": p.corrections, "final": SCHEMA.ints(p.state), "log": len(p.log)}


# ---------- the JavaScript side ----------
RUNNER = r"""
import fs from "fs";
import crypto from "crypto";
import * as sim from "./city_sim.js";
import {Predictor, InputLog} from "./predict.js";

const job = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = {people: [], cars: [], points: [], compares: [], predicts: []};
{
    const w = await import("./wire.js");
    out.cityFields = w.CITY_FIELDS || null;
    out.simFields = sim.SCHEMA_FIELDS;
    out.constants = Object.fromEntries(job.constants.map(k => [k, sim[k]]));
}
const cities = {};
for (const [name, data] of Object.entries(job.cities)) cities[name] = new sim.City(data);
const RAW = ["x", "y", "z", "vz", "yaw", "v", "u"];
const t0 = performance.now();
let steps = 0;
for (const r of job.people) {
    const city = cities[r.city];
    let p = r.start;
    const lines = [], raw = [];
    for (const [th, sr, bt] of r.inputs) {
        const n = sim.stepPerson(p, [th / 100, sr / 100, bt], sim.STEP, city);
        steps++;
        if (r.raw) raw.push(RAW.map(k => n[k]));
        Object.assign(n, sim.quantise(n));
        lines.push(sim.wireInts(n).join(","));
        p = n;
    }
    const md5 = crypto.createHash("md5").update(lines.join(";")).digest("hex");
    out.people.push({md5, lines: md5 === r.md5 ? null : lines, raw: r.raw ? raw : null});
}
for (const r of job.cars) {
    const city = cities[r.city], st = sim.statsOf(r.design);
    let k = r.start;
    const lines = [], raw = [];
    for (const [th, sr, bt] of r.inputs) {
        const n = sim.stepCar(k, [th / 100, sr / 100, bt], sim.STEP, city, st, r.driven);
        steps++;
        if (r.raw) raw.push(RAW.map(f => n[f]));
        Object.assign(n, sim.quantise(n));
        lines.push(sim.wireInts(n).join(","));
        k = n;
    }
    const md5 = crypto.createHash("md5").update(lines.join(";")).digest("hex");
    out.cars.push({md5, lines: md5 === r.md5 ? null : lines, raw: r.raw ? raw : null});
}
out.us_per_step = (performance.now() - t0) * 1000 / steps;
for (const c of job.points) {
    const city = cities[c.city];
    out.points.push(c.points.map(({p: [x, y, r, x2, y2]}) => ({collide: city.collide(x, y, r), surface: city.surface(x, y),
        ramp: city.rampHeight(x, y), kerb: city.kerbBetween(x, y, x2, y2), block: city.blockIndex(x, y),
        zones: ["depot", "garage", "rank", "arcade"].map(z => city.inZone(z, x, y))})));
}
out.compares = job.compares.map(c => sim.compare(c.a, c.b));
for (const c of job.predicts) {
    const city = cities[c.city];
    const step = c.kind === "person" ? sim.makeStep(city, "person") : sim.makeStep(city, "car", sim.statsOf(c.design));
    const p = new Predictor(step, {...c.start}, 0.05, new InputLog(c.first_seq));
    const seqs = [], errs = [];
    for (let t = 0; t <= c.inputs.length; t++) {
        if (t < c.inputs.length) {
            const [th, sr, bt] = c.inputs[t];
            seqs.push(p.apply([th / 100, sr / 100, bt], sim.STEP));
        }
        for (const j of c.deliver[t]) {
            const ack = seqs[j];
            if (ack === 0) continue;
            const err = p.correct({...c.server[j]}, ack, sim.STEP, sim.compare);
            errs.push(err === Infinity ? null : err);
        }
    }
    out.predicts.push({errs, corrections: p.corrections, final: sim.wireInts(p.state), log: p.log.length});
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
"""


def first_difference(py_lines, js_lines):
    return next((n for n, (a, b) in enumerate(zip(py_lines, js_lines)) if a != b), None)


def main():
    if CITY is None:
        print("City Lab's folder isn't beside this one: nothing to test against.")
        return 1
    node = shutil.which("node")
    if not node:
        print("node isn't installed: the browser's City Lab steps can't be checked here (passing with this note)")
        print("1 of 1 passed")
        return 0
    rng = random.Random(SEED)
    cities = {name: city_map.load(name) for name in city_map.CITIES}
    t0 = time.perf_counter()
    people, people_raw, people_cover = run_people(rng, cities)
    cars, cars_raw, cars_cover = run_cars(rng, cities)
    points = make_points(random.Random(SEED + 1), cities)
    compares = make_compares(random.Random(SEED + 2))
    predicts = make_predicts(random.Random(SEED + 3), cities["harbour"])
    py_time = time.perf_counter() - t0

    tmp = tempfile.mkdtemp(prefix="city_sim_test_")
    try:
        for f in JS_FILES:
            shutil.copy(os.path.join(HERE, f), tmp)
        with open(os.path.join(tmp, "package.json"), "w") as f:
            f.write('{"type": "module"}')
        with open(os.path.join(tmp, "runner.js"), "w", encoding="utf-8") as f:
            f.write(RUNNER)
        job = {"cities": {name: c.to_data() for name, c in cities.items()},
               "people": [{k: v for k, v in r.items() if not k.startswith("_")} for r in people],
               "cars": [{k: v for k, v in r.items() if not k.startswith("_")} for r in cars],
               "points": [{"city": c["city"], "points": [{"p": q["p"]} for q in c["points"]]} for c in points],
               "compares": [{"a": c["a"], "b": c["b"]} for c in compares], "predicts": predicts,
               "constants": CONSTANTS + MAP_CONSTANTS}
        with open(os.path.join(tmp, "job.json"), "w") as f:
            json.dump(job, f)
        t1 = time.perf_counter()
        r = subprocess.run([node, os.path.join(tmp, "runner.js"), os.path.join(tmp, "job.json"),
                            os.path.join(tmp, "out.json")], capture_output=True, text=True, cwd=tmp)
        js_time = time.perf_counter() - t1
        if r.returncode != 0:
            print(r.stdout, r.stderr)
            check("node ran the browser's modules", False, r.stderr.strip().splitlines()[-1] if r.stderr else "")
            return report()
        with open(os.path.join(tmp, "out.json")) as f:
            out = json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # the record and the numbers
    want = [list(f) for f in sim.SCHEMA_FIELDS]
    check("wire.js's CITY_FIELDS and city_sim.js's SCHEMA_FIELDS are city_sim.SCHEMA_FIELDS, field for field",
          out["cityFields"] == want and out["simFields"] == want, f"{out['cityFields']} / {out['simFields']}")
    py_consts = {k: getattr(sim, k) for k in CONSTANTS}
    py_consts.update({k: getattr(city_map, k) for k in MAP_CONSTANTS})
    wrong = {k: (v, out["constants"].get(k)) for k, v in py_consts.items() if out["constants"].get(k) != v}
    check(f"city_sim.js's {len(py_consts)} numbers (the speeds, the moves, the car's grips, the city's measurements) are "
          f"city_sim's and city_map's", not wrong, str(wrong))

    # the city's questions
    for c, js in zip(points, out["points"]):
        bad = []
        for i, (q, j) in enumerate(zip(c["points"], js)):
            for key in ("collide", "surface", "ramp", "kerb", "block", "zones"):
                a, b = q[key], j[key]
                if key == "collide":
                    a = list(a)
                if a != b:
                    bad.append(f"point {i} {q['p']}: {key} python {a!r} js {b!r}")
        check(f"'{c['city']}': collide, surface, the ramps, the kerb, the block and the yards are city_map's for "
              f"{len(c['points'])} points", not bad, "; ".join(bad[:3]))

    # the steps
    for kind, runs, js_runs, counts in (("person", people, out["people"], PEOPLE), ("car", cars, out["cars"], CARS)):
        bad = []
        for i, (d, js) in enumerate(zip(runs, js_runs)):
            if js["md5"] != d["md5"]:
                n = first_difference(d["_lines"], js["lines"])
                bad.append(f"{kind} {i} ({d['city']}) first differs at tick {n}: python {d['_lines'][n]} js {js['lines'][n]}")
        for name, count in counts.items():
            mine = [b for b in bad if f"({name})" in b]
            check(f"'{name}': {count} {kind} runs of {TICKS} ticks give the server's wire numbers tick for tick", not mine,
                  "; ".join(mine[:3]))
    print("  what the people did (ticks):", ", ".join(f"{k} {v}" for k, v in people_cover.items()))
    print("  what the cars did (ticks):", ", ".join(f"{k} {v}" for k, v in cars_cover.items()))
    check("the people walked, ran, turned, jumped, punched, kicked, blocked, went down and got up, were hurt, got "
          "health back, met buildings, posts and the edge, sat in cars and carried parcels", all(people_cover.values()),
          str(people_cover))
    check("the cars drifted, handbraked, spun their wheels, flew off ramps, crossed kerbs, ran on pavements, grass and "
          "the quay, met buildings, posts and the edge, were damaged, wrecked and mended, reversed, and rolled with "
          "nobody driving", all(cars_cover.values()), str(cars_cover))
    for kind, raws, js_runs in (("person", people_raw, out["people"]), ("car", cars_raw, out["cars"])):
        diff, total, worst = 0, 0, [0.0] * len(RAW)
        for i, raw in raws.items():
            for a, b in zip(raw, js_runs[i]["raw"]):
                total += 1
                if a != b:
                    diff += 1
                    for f in range(len(RAW)):
                        if a[f] != b[f]:
                            worst[f] = max(worst[f], abs(a[f] - b[f]))
        check(f"before the rounding the {kind}'s numbers are the same to the last bit too ({total} ticks)", diff == 0,
              ", ".join(f"{RAW[f]} {worst[f]:.1e}" for f in range(len(RAW))) + f" ({diff} ticks differ)")

    # compare()
    wrong = [i for i, (c, js) in enumerate(zip(compares, out["compares"])) if c["out"] != js]
    check(f"compare() is city_sim.compare ({len(compares)} pairs)", not wrong,
          str([(compares[i]["out"], out["compares"][i]) for i in wrong[:3]]))

    # the prediction
    same, corr, final_ok, exact = True, 0, True, 0
    bad = []
    for i, (c, js) in enumerate(zip(predicts, out["predicts"])):
        py = run_predict_py(c, cities[c["city"]])
        if not (py["errs"] == js["errs"] and py["corrections"] == js["corrections"] and py["log"] == js["log"]):
            same = False
            bad.append(f"{c['kind']} {i}: python {py['corrections']} corrections, js {js['corrections']}")
        corr += py["corrections"]
        server_final = SCHEMA.ints(c["server"][-1])
        exact += js["final"] == server_final
        final_ok &= js["final"] == py["final"] and sim.compare(SCHEMA.values(js["final"]), SCHEMA.values(server_final)) < 0.05
    surprises = sum(c["surprises"] for c in predicts)
    check(f"the Predictor makes engine.predict's corrections with city_sim's steps ({len(predicts)} runs, a person's and "
          f"a car's, {corr} corrections for {surprises} shoves, knockdowns and hits only the server knew of: late, "
          f"jittered and skipped snapshots, numbers wrapping)", same, "; ".join(bad[:3]))
    check(f"the Predictor ends on the server's state ({exact} of {len(predicts)} to the centimetre, all within the "
          f"5 cm it ignores)", final_ok)

    # the fingerprint
    fingerprint = {"sim_version": sim.SIM_VERSION, "people": md5([r["md5"] for r in people]),
                   "cars": md5([r["md5"] for r in cars])}
    if "--record" in sys.argv:
        with open(GOLDEN, "w", encoding="utf-8") as f:
            json.dump(fingerprint, f, indent=1)
        print(f"  recorded the fingerprint for SIM_VERSION {sim.SIM_VERSION}: {GOLDEN}")
    try:
        with open(GOLDEN, encoding="utf-8") as f:
            golden = json.load(f)
    except OSError:
        golden = {}
    if golden.get("sim_version") != sim.SIM_VERSION:
        check("the runs' numbers are the recorded ones for this SIM_VERSION", False,
              f"city_sim_golden.json is for SIM_VERSION {golden.get('sim_version')}, the steps are "
              f"{sim.SIM_VERSION}: run this with --record in the same commit as the change")
    else:
        check(f"the runs' numbers are the ones recorded for SIM_VERSION {sim.SIM_VERSION} (the same on every computer: "
              f"a change that moves them needs a new SIM_VERSION)", golden == fingerprint,
              f"recorded {golden}, now {fingerprint}")
    print(f"  (Python made the runs in {py_time:.1f} s; node ran them in {js_time:.1f} s, "
          f"{out['us_per_step']:.2f} us a step)")
    return report()


def report():
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {detail}" if detail and not ok else ""))
    passed = sum(ok for _, ok, _ in results)
    print(f"{passed} of {len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
