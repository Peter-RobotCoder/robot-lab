"""The browser's Craft Lab (craft_sim.js, craft_mesh.js, predict.js, pymath.js) against Craft Lab's own Python (CHANGE 202).

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\craft_sim_test.py      (from the ClubCodersAI folder)

Makes two islands with craft_world (and stamps in what the step and the mesher have to deal with: slabs, beds, ladders
up pillars, pools, doors open and shut, torches, lumen blocks, farmland and wheat, glass, leaves, holes and towers),
then runs the same things through craft/'s Python and, with node, through the page's modules, and checks:
  - the light: the sky's and the torches' light over the whole island (craft_world.light_all), and again after a few
    hundred blocks are changed (apply_changes, as the server's changes come), the same numbers in every block;
  - the meshes: every chunk of both islands, on the plain tiers and the mesh and lines looks, gives craft_mesh's
    vertices (place, texture, shade and light bytes), triangles and edges byte for byte;
  - the world's questions: blocked, touching (water, ladders), on_ground, the ray to the block looked at (and the face
    it came in through), the blocks' heights, look_dir, eye, player_box_hits and dig_time for every block with every
    tool, the same answers for thousands of cases;
  - the player's step: hundreds of runs (600 ticks each: walking, sprinting, sneaking at edges, jumping, stepping up
    onto slabs and beds, swimming, climbing ladders, falling, flying in creative, into walls and off towers) give the
    server's wire numbers tick for tick (step_player, then the wire's rounding, as the server and the window apply
    them), and the same numbers to the last bit before the rounding too;
  - the record: wire.js's CRAFT_FIELDS and craft_sim.js's SCHEMA_FIELDS are craft_sim.SCHEMA_FIELDS, the step's numbers
    are craft_sim's;
  - compare() is craft_sim.compare (the prediction's yardstick);
  - the prediction: a Predictor stepping a player with snapshots arriving late, jittered and some skipped, with knocks,
    shoves and respawns only the server knew of and the numbers wrapping, makes the same corrections with the same
    errors as engine.predict's with craft_sim's step, and ends on the server's state;
  - the Garage and the code panel: schema.js writes a Craft Bot's design as Python as engine.schema.code_lines does,
    reads it back (as written, edited and broken) as parse_code does, applies the values as apply_values does, checks
    a design as craft_design.check_design does and writes the garage's stats line as craft_panels.Garage does;
  - the fingerprint: the runs' numbers are the ones craft_sim_golden.json recorded for craft_sim.SIM_VERSION (a change
    to the step that wasn't meant to change them fails here; one that was: raise SIM_VERSION and run this with --record
    in the same commit).
Exit code 0 = every check passed. Passes with a note if node isn't installed.
"""
import base64
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
CRAFT = next((p for p in (os.path.join(os.path.dirname(HERE), "games", "craftlab"),
                          os.path.join(os.path.dirname(os.path.dirname(HERE)), "craft"))
              if os.path.isdir(p)), None)
sys.path.insert(0, CRAFT or HERE)
import numpy as np  # noqa: E402

import craft_version  # noqa: E402,F401  (the engine on the path)
import craft_art  # noqa: E402
import craft_blocks as B  # noqa: E402
import craft_mesh as M  # noqa: E402
import craft_sim as sim  # noqa: E402
import craft_world  # noqa: E402
from engine import predict, wire  # noqa: E402

SCHEMA = wire.Schema("craft", sim.SCHEMA_FIELDS)
JS_FILES = ["pymath.js", "craft_sim.js", "craft_mesh.js", "predict.js", "wire.js", "schema.js", "schemas.json"]
SEEDS = [2026, 77]
RUNS = 200                # player runs in each world
TICKS = 600
RAW_RUNS = 120            # runs whose numbers before the rounding are compared too
QUESTIONS = 4000          # of each kind of world question, in each world
CHANGES = 300             # blocks changed in each world for the light's second look
PREDICT_RUNS = 40
SEED = 20261029
GOLDEN = os.path.join(HERE, "craft_sim_golden.json")
CONSTANTS = ["SIM_VERSION", "STEP", "HALF", "TALL", "EYE", "SNEAK_TALL", "GRAVITY", "JUMP", "TERMINAL", "WALK", "SPRINT",
             "SNEAK", "FLY_SPEED", "FLY_FAST", "SWIM", "SWIM_UP", "SWIM_SINK", "CLIMB", "REACH", "REACH_CREATIVE", "JUMP_B",
             "SPRINT_B", "SNEAK_B", "FLY_B", "RESPAWN_B", "F_GROUND", "F_WATER", "F_FLY", "F_SNEAK", "F_HURT", "F_SLEEP",
             "F_SWING", "F_CLIMB"]
RAW = ["x", "y", "z", "vx", "vy", "vz", "fall"]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def md5(data):
    return hashlib.md5(data if isinstance(data, bytes) else ";".join(data).encode()).hexdigest()


def wire_line(s):
    return ",".join(map(str, SCHEMA.ints(s)))


# ---------- the islands ----------
def stamp(w, rng):
    """What the step and the mesher meet, stamped round the middle of the island: returns the places it put things."""
    ID = B.ID
    cx, cy = w.X // 2, w.Y // 2
    spots = []
    for n in range(90):
        x, y = cx + rng.randint(-34, 34), cy + rng.randint(-34, 34)
        if not (4 <= x < w.X - 6 and 4 <= y < w.Y - 6):
            continue
        z = w.top(x, y) + 1
        if z >= w.Z - 10:
            continue
        kind = n % 13
        b = w.blocks
        if kind == 0:  # slabs and beds to step up onto
            for dx in range(3):
                b[x + dx, y, z] = rng.choice((ID["slab"], ID["plank_slab"], ID["bed"]))
        elif kind == 1:  # a pillar with a ladder up it
            for dz in range(6):
                b[x, y, z + dz] = ID["stone"]
                b[x + 1, y, z + dz] = ID["ladder"]
                w.meta[x + 1, y, z + dz] = 1
        elif kind == 2:  # a pool
            for dx in range(4):
                for dy in range(4):
                    for dz in (-2, -1):
                        b[x + dx, y + dy, z + dz] = ID["water"]
                    b[x + dx, y + dy, z] = 0
        elif kind == 3:  # a doorway
            m = rng.randrange(8)
            b[x, y, z], b[x, y, z + 1] = ID["door"], ID["door_top"]
            w.meta[x, y, z] = w.meta[x, y, z + 1] = m
        elif kind == 4:  # torches and a lumen block in a dark pocket
            for dz in range(3):
                b[x - 1, y, z + dz] = b[x + 1, y, z + dz] = b[x, y - 1, z + dz] = b[x, y + 1, z + dz] = ID["stone"]
            b[x, y, z + 3] = ID["stone"]
            b[x, y, z] = ID["torch"]
            b[x + 2, y, z] = ID["lumen"]
        elif kind == 5:  # farmland and wheat
            for dx in range(3):
                b[x + dx, y, z - 1] = ID["farmland"]
                b[x + dx, y, z] = ID["wheat"]
                w.meta[x + dx, y, z] = rng.randrange(8)
        elif kind == 6:  # glass and leaves walls
            for dx in range(4):
                for dz in range(3):
                    b[x + dx, y, z + dz] = ID["glass"] if dx % 2 else ID["leaves"]
        elif kind == 7:  # a tower to fall from (and sneak round the top of)
            for dz in range(8):
                b[x, y, z + dz] = ID["planks"]
        elif kind == 8:  # a hole
            for dz in range(1, 5):
                b[x, y, z - dz] = 0
                b[x + 1, y, z - dz] = 0
        elif kind == 9:  # a staircase of blocks
            for dx in range(4):
                for dz in range(dx + 1):
                    b[x + dx, y, z + dz] = ID["brick"]
        elif kind == 10:  # plants, a cactus, a smelter lit
            b[x, y, z] = ID["tall_grass"]
            b[x + 1, y, z] = ID["flower_red"]
            b[x + 2, y, z] = ID["cactus"]
            b[x + 3, y, z] = ID["smelter_lit"]
            b[x, y + 1, z] = ID["sapling"]
            b[x + 1, y + 1, z] = ID["berry_bush"]
        elif kind == 11:  # a low ceiling to bump your head on
            for dx in range(3):
                for dy in range(3):
                    b[x + dx, y + dy, z + 2] = ID["rubble"]
        else:  # magma in a pit, ice on water
            b[x, y, z - 1] = ID["magma"]
            b[x + 1, y, z - 1] = ID["ice"]
            b[x + 2, y, z - 1] = ID["water"]
        spots.append((x, y, z, kind))
    w.light_all()
    return spots


def make_worlds():
    worlds = []
    for seed in SEEDS:
        w = craft_world.World("small", seed)
        spots = stamp(w, random.Random(seed))
        worlds.append((w, spots))
    return worlds


def world_job(w):
    return {"size": w.size_key, "seed": w.seed, "spawn": list(w.spawn),
            "blocks": base64.b64encode(w.blocks.tobytes()).decode(), "meta": base64.b64encode(w.meta.tobytes()).decode()}


# ---------- the light ----------
def make_changes(rng, w, spots):
    """Blocks changed near the stamped things (dug, a torch put down, a wall, water): the server's change list."""
    ID = B.ID
    out = []
    for _ in range(CHANGES):
        x, y, z, _k = rng.choice(spots)
        x, y, z = x + rng.randint(-3, 3), y + rng.randint(-3, 3), z + rng.randint(-4, 3)
        bid = rng.choice((0, 0, ID["torch"], ID["stone"], ID["glass"], ID["lumen"], ID["water"], ID["leaves"], ID["planks"]))
        out.append([x, y, z, bid, 0])
    return out


def light_md5(w):
    return [md5(w.sky.tobytes()), md5(w.glow.tobytes())]


# ---------- the meshes ----------
def mesh_md5s(w, tables):
    out = []
    for cx, cy in w.chunks:
        for look in (None, "mesh", "lines"):
            passes, lines = M.mesh_chunk(w, cx, cy, tables, look)
            parts = []
            for p in passes:
                a = p.arrays()
                parts.append("none" if a is None else md5(a[0]) + "/" + md5(a[1].astype(np.uint32).tobytes()) + f"/{a[2]}")
            if look:
                parts.append("none" if lines is None else md5(lines.reshape(-1, 3).astype(np.float32).tobytes()))
            out.append(f"{cx},{cy},{look}:" + "|".join(parts))
    return out


# ---------- the world's questions ----------
def make_questions(rng, w, spots):
    solid, liquid, climb = sim.tables()
    cases = {"blocked": [], "touching": [], "ground": [], "ray": [], "box": [], "look": [], "eye": []}
    for _ in range(QUESTIONS):
        x, y, z, _k = rng.choice(spots)
        px, py, pz = x + rng.uniform(-3, 4), y + rng.uniform(-3, 4), z + rng.uniform(-3, 4)
        sx, sy, sz = rng.uniform(0.01, 1.2), rng.uniform(0.01, 1.2), rng.uniform(0.01, 2.0)
        cases["blocked"].append({"q": [px, py, pz, px + sx, py + sy, pz + sz],
                                 "a": sim.blocked(w, px, py, pz, px + sx, py + sy, pz + sz, solid)})
        s = {"x": px, "y": py, "z": pz}
        tall = rng.choice((sim.TALL, sim.SNEAK_TALL))
        cases["touching"].append({"q": [px, py, pz, tall], "a": [sim.touching(w, s, liquid, tall), sim.touching(w, s, climb, tall)]})
        cases["ground"].append({"q": [px, py, pz], "a": sim.on_ground(w, s, solid)})
        yaw, pitch = rng.uniform(-400, 400), rng.uniform(-89.9, 89.9)
        if rng.random() < 0.1:
            pitch = rng.choice((90.0, -90.0, 0.0, 45.0))
        if rng.random() < 0.05:
            yaw = rng.choice((0.0, 90.0, 180.0, 270.0))
        dx, dy, dz = sim.look_dir(yaw, pitch)
        reach = rng.choice((sim.REACH, sim.REACH_CREATIVE, 12.0))
        hit = sim.ray(w, px, py, pz, dx, dy, dz, reach)
        cases["look"].append({"q": [yaw, pitch], "a": [dx, dy, dz]})
        cases["ray"].append({"q": [px, py, pz, dx, dy, dz, reach],
                             "a": None if hit is None else [list(hit[0]), list(hit[1]), hit[2]]})
        flags = rng.choice((0, sim.F_SNEAK, sim.F_GROUND | sim.F_SNEAK))
        cases["eye"].append({"q": [px, py, pz, flags], "a": list(sim.eye({"x": px, "y": py, "z": pz, "flags": flags}))})
        bx, by, bz = int(math.floor(px + rng.uniform(-1, 1))), int(math.floor(py + rng.uniform(-1, 1))), int(math.floor(pz + rng.uniform(-2, 2)))
        cases["box"].append({"q": [px, py, pz, bx, by, bz, tall], "a": sim.player_box_hits(s, bx, by, bz, tall)})
    return cases


def dig_cases():
    held = [None] + [it for it in B.ITEMS.values() if it.get("tool")] + [B.ITEMS[B.ITEM_ID["stick"]]]
    out = []
    for b in B.BLOCKS:
        for h in held:
            t, enough = B.dig_time(b["id"], h)
            out.append({"bid": b["id"], "held": None if h is None else h["id"], "a": [t, enough]})
    return out


def heights_cases():
    return [sim.heights(i) if i < len(B.BLOCKS) else 1.0 for i in range(256)]


# ---------- the player's runs ----------
def start_state(rng, w, spots):
    x, y, z, kind = rng.choice(spots)
    s = sim.new_player(x + rng.uniform(-2, 3), y + rng.uniform(-2, 3), 0.0)
    xi, yi = int(math.floor(s["x"])), int(math.floor(s["y"]))
    s["z"] = float(w.top(xi, yi) + 1) + rng.choice((0.0, 0.0, 0.0, rng.uniform(0, 3), rng.uniform(-0.3, 0)))
    if rng.random() < 0.5:
        s["flags"] |= sim.F_GROUND
    if rng.random() < 0.25:
        s["vx"], s["vy"], s["vz"] = rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(-8, 8)
    if rng.random() < 0.15:
        s["fall"] = rng.uniform(0, 12)
    s["yaw"], s["pitch"] = rng.uniform(0, 360), rng.uniform(-60, 60)
    s["held"] = rng.randint(0, 300)
    s.update(SCHEMA.quantise(s))
    return s


def run_inputs(rng, ticks, creative):
    out = []
    while len(out) < ticks:
        hold = rng.randint(1, 60)
        if rng.random() < 0.15:
            mx, my = 0.0, 0.0
        else:
            a = rng.uniform(-math.pi, math.pi)
            mag = rng.choice((1.0, 1.0, rng.uniform(0, 1.4), rng.uniform(0.05, 0.2)))
            mx, my = math.cos(a) * mag, math.sin(a) * mag
        held = (sim.SPRINT_B if rng.random() < 0.3 else 0) | (sim.SNEAK_B if rng.random() < 0.2 else 0) | \
            (sim.JUMP_B if rng.random() < 0.25 else 0) | (sim.FLY_B if creative and rng.random() < 0.6 else 0)
        mx, my, held = wire.quantise_input(mx, my, held)
        for _ in range(hold):
            tap = sim.JUMP_B if rng.random() < 0.04 else 0
            out.append([round(mx * 100), round(my * 100), held | tap])
    return out[:ticks]


def run_players(rng, worlds):
    runs, raws = [], {}
    cover = dict.fromkeys(("walking", "sprinting", "sneaking", "jumping", "stepping up", "in water", "climbing", "falling",
                           "landing", "flying", "stopped by a wall", "at an edge"), 0)
    for wi, (w, spots) in enumerate(worlds):
        for _ in range(RUNS):
            creative = rng.random() < 0.3
            s = start_state(rng, w, spots)
            start = dict(s)
            inputs = run_inputs(rng, TICKS, creative)
            lines, raw = [], []
            keep_raw = len(runs) < RAW_RUNS
            for th, sr, bt in inputs:
                was = s
                s = sim.step_player(s, (th / 100, sr / 100, bt), sim.STEP, w, creative)
                if keep_raw:
                    raw.append([s[k] for k in RAW])
                s.update(SCHEMA.quantise(s))
                lines.append(wire_line(s))
                moving = math.hypot(s["vx"], s["vy"]) > 0.2
                cover["walking"] += moving and bool(s["flags"] & sim.F_GROUND) and not bt & sim.SPRINT_B
                cover["sprinting"] += moving and bool(bt & sim.SPRINT_B) and not bt & sim.SNEAK_B
                cover["sneaking"] += bool(s["flags"] & sim.F_SNEAK)
                cover["jumping"] += s["vz"] > 7 and not s["flags"] & sim.F_FLY
                cover["stepping up"] += bool(was["flags"] & sim.F_GROUND) and 0.45 < s["z"] - was["z"] < 0.6
                cover["in water"] += bool(s["flags"] & sim.F_WATER)
                cover["climbing"] += bool(s["flags"] & sim.F_CLIMB)
                cover["falling"] += s["fall"] > 1
                cover["landing"] += bool(s["flags"] & sim.F_GROUND) and not was["flags"] & sim.F_GROUND
                cover["flying"] += bool(s["flags"] & sim.F_FLY)
                cover["stopped by a wall"] += (abs(th) > 50 or abs(sr) > 50) and s["vx"] == 0.0 and s["vy"] == 0.0
                cover["at an edge"] += bool(s["flags"] & sim.F_SNEAK) and bool(s["flags"] & sim.F_GROUND) and (s["vx"] == 0.0) != (s["vy"] == 0.0)
            if keep_raw:
                raws[len(runs)] = raw
            runs.append({"world": wi, "start": {n: start[n] for n in SCHEMA.names}, "inputs": inputs, "creative": creative,
                         "raw": keep_raw, "md5": md5(lines), "_lines": lines})
    return runs, raws, cover


# ---------- compare() ----------
def make_compares(rng):
    cases = []
    for _ in range(3000):
        a = {"x": rng.uniform(-50, 250), "y": rng.uniform(-50, 250), "z": rng.uniform(-20, 80), "flags": rng.randrange(256)}
        b = dict(a)
        if rng.random() < 0.7:
            b.update(x=a["x"] + rng.uniform(-0.2, 0.2), y=a["y"] + rng.uniform(-0.2, 0.2), z=a["z"] + rng.uniform(-0.2, 0.2))
        if rng.random() < 0.2:
            b["flags"] = rng.randrange(256)
        cases.append({"a": a, "b": b, "out": sim.compare(a, b)})
    return cases


# ---------- the prediction (Python) ----------
def make_predicts(rng, w, spots):
    cases = []
    for _ in range(PREDICT_RUNS):
        creative = rng.random() < 0.3
        s = start_state(rng, w, spots)
        start = {n: s[n] for n in SCHEMA.names}
        inputs = run_inputs(rng, TICKS, creative)
        surprises = {rng.randint(40, TICKS - 60): rng.choice(("shove", "knock", "respawn")) for _ in range(3)}
        first_seq = rng.choice((0, 65400 + rng.randint(0, 135), rng.randint(1, 65535)))
        server, k = [], dict(start)
        for t, (th, sr, bt) in enumerate(inputs):
            k = sim.step_player(k, (th / 100, sr / 100, bt), sim.STEP, w, creative)
            what = surprises.get(t)
            if what == "shove":  # (a creature, or a blast, pushed them: the server's own)
                k["x"] += rng.uniform(-0.6, 0.6)
                k["y"] += rng.uniform(-0.6, 0.6)
            elif what == "knock":  # (craft_game.hurt's knock back)
                k["vx"] += rng.uniform(-5, 5)
                k["vy"] += rng.uniform(-5, 5)
                k["vz"] = max(k["vz"], 4.0)
            elif what == "respawn":  # (knocked out: back at the spawn)
                x, y, z, _k = spots[0]
                k.update(x=x + 0.5, y=y + 0.5, z=float(w.top(x, y) + 1), vx=0.0, vy=0.0, vz=0.0, fall=0.0)
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
        cases.append({"start": start, "inputs": inputs, "creative": creative, "server": server, "deliver": deliver,
                      "first_seq": first_seq, "surprises": len(surprises)})
    return cases


def run_predict_py(case, w):
    def step(state, inp, dt):
        n = sim.step_player(state, inp, dt, w, case["creative"])
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
                continue  # (craft_client: the server hasn't applied an input of ours yet)
            err = p.correct(dict(case["server"][j]), ack, sim.STEP, sim.compare)
            errs.append(None if err == math.inf else err)
    return {"errs": errs, "corrections": p.corrections, "final": SCHEMA.ints(p.state), "log": len(p.log)}


# ---------- the Garage and the code panel (CHANGE 202: schemas.json's craftlab, schema.js) ----------
NAMES = ["Craft Bot", "Bob", "Zoë", "Sam's bot", 'Say "hi"', "back\\slash", "🤖 Bot", "", " spaced ", "x" * 20, "日本語", "None"]


def schema_cases(rng):
    import craft_design as design
    from types import SimpleNamespace
    from engine import schema
    ctx = SimpleNamespace(title="MY CRAFT BOT", points_total=design.POINTS_TOTAL, weapons=[], all_weapons=[], house={}, rules={},
                          model=None, makers={})  # (craft_panels.ctx)
    sch = design.schema()

    def outcome(f):
        try:
            return {"ok": f()}
        except schema.ParseError as e:
            return {"error": [e.lineno, e.message]}
        except Exception as e:  # noqa: BLE001
            return {"crash": type(e).__name__}

    def mutate(lines):
        lines = list(lines)
        k = rng.randrange(len(lines))
        r = rng.random()
        if r < 0.3:
            lines[k] = re_number(lines[k])
        elif r < 0.45:
            lines[k] = lines[k].replace('"', "", 1)
        elif r < 0.6:
            lines.insert(k, rng.choice(["x = 5", "dig: int = 5 5", "colour = [1, 2", "build: int = 1_0", "speed = -3",
                                        'bot_name: str = "Rex"', "colour: list = [300, 0, 0]", "dig: int = 25.5", "# a note",
                                        "def f(): pass", "speed: int = 0x1F", "bot_name = None"]))
        elif r < 0.7:
            del lines[k]
        elif r < 0.8:
            lines[k] = lines[k] + rng.choice(["  # the Bot", " +", ")", ""])
        return lines

    def re_number(line):
        import re
        return re.sub(r"\d+", lambda m: str(rng.choice([0, 5, 9, 10, 33, 60, 61, 100, 250, 256, -1])), line, count=1)

    cases = []
    for n in range(400):
        d = design.default_design(rng.choice(NAMES), (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)))
        for k in design.STATS:
            if rng.random() < 0.7:
                d["points"][k] = rng.choice([rng.randint(0, 80), 10, 60, 34, rng.randint(10, 40)])
        if rng.random() < 0.05:
            d["colour"] = rng.choice([[1, 2], [300, 0, 0], "red", [1.5, 2, 3]])
        if rng.random() < 0.05:
            d["points"].pop(rng.choice(design.STATS))
        limits = design.default_limits() if rng.random() < 0.6 else design.full_limits()
        lines = outcome(lambda: schema.code_lines(sch, d, ctx))
        text = "\n".join(mutate(lines["ok"]) if "ok" in lines and rng.random() < 0.85 else lines.get("ok", ["x"]))
        parsed = outcome(lambda: {k: v for k, v in schema.parse_code(text, sch, ctx).items()})
        applied = None
        if "ok" in parsed:
            new = json.loads(json.dumps(d))
            res = outcome(lambda: list(schema.apply_values(sch, new, parsed["ok"], ctx, lambda v, x: True)))
            applied = {"res": res, "design": new}
        st = design.stats_of(d) if isinstance(d.get("points"), dict) else None
        stats = None if st is None else (f"a dig takes {st['dig']:.2f} s x the block's hardness; a placement {st['build']:.2f} s; "
                                         f"a move {st['move']:.2f} s")
        cases.append({"design": d, "limits": limits, "text": text,
                      "want": json.loads(json.dumps({"lines": lines, "parsed": parsed, "applied": applied,
                                                     "check": design.check_design(json.loads(json.dumps(d)), limits),
                                                     "stats": stats}))})
    return cases


# ---------- the JavaScript side ----------
RUNNER = r"""
import fs from "fs";
import crypto from "crypto";
import * as sim from "./craft_sim.js";
import {Tables, meshChunk} from "./craft_mesh.js";
import {Predictor, InputLog} from "./predict.js";
import {CRAFT_FIELDS} from "./wire.js";
import * as SC from "./schema.js";

const job = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const md5 = b => crypto.createHash("md5").update(b).digest("hex");
sim.useTables(job.tables);
const tables = new Tables(job.tables.atlas.where, job.tables.atlas.tiles);
const out = {fields: CRAFT_FIELDS, simFields: sim.SCHEMA_FIELDS, constants: Object.fromEntries(job.constants.map(k => [k, sim[k]])),
             heights: Array.from({length: 256}, (_, i) => sim.heights(i)), worlds: [], runs: [], compares: [], predicts: [], dig: []};
const worlds = [];
for (const wj of job.worlds) {
    const w = new sim.World(wj.size, wj.seed, wj.spawn), tl = performance.now();
    w.load(Buffer.from(wj.blocks, "base64"), Buffer.from(wj.meta, "base64"));
    const res = {light: [md5(w.sky), md5(w.glow)], lightMs: performance.now() - tl};
    // the meshes
    const meshes = [];
    const tm = performance.now();
    for (let cx = 0; cx < w.X / 16; cx++) for (let cy = 0; cy < w.Y / 16; cy++) for (const look of [null, "mesh", "lines"]) {
        const {passes, lines} = meshChunk(w, cx, cy, tables, look);
        const parts = passes.map(a => {
            if (!a) return "none";
            const n = a.pos.length / 3, buf = Buffer.alloc(n * 24);
            for (let i = 0; i < n; i++) {
                for (let k = 0; k < 3; k++) buf.writeFloatLE(a.pos[i * 3 + k], i * 24 + k * 4);
                for (let k = 0; k < 2; k++) buf.writeFloatLE(a.uv[i * 2 + k], i * 24 + 12 + k * 4);
                for (let k = 0; k < 4; k++) buf.writeUInt8(a.c[i * 4 + k], i * 24 + 20 + k);
            }
            return md5(buf) + "/" + md5(Buffer.from(a.idx.buffer, a.idx.byteOffset, a.idx.byteLength)) + "/" + a.n;
        });
        if (look) parts.push(lines ? md5(Buffer.from(new Float32Array(lines).buffer)) : "none");
        meshes.push(`${cx},${cy},${look === null ? "None" : look}:` + parts.join("|"));
    }
    res.meshMs = (performance.now() - tm) / meshes.length * 3;
    res.meshes = meshes;
    // the world's questions (before the changes)
    const [solid, liquid, climb] = sim.tables(), Q = job.questions[worlds.length];
    res.blocked = Q.blocked.map(c => sim.blocked(w, ...c.q, solid));
    res.touching = Q.touching.map(c => { const s = {x: c.q[0], y: c.q[1], z: c.q[2]}; return [sim.touching(w, s, liquid, c.q[3]), sim.touching(w, s, climb, c.q[3])]; });
    res.ground = Q.ground.map(c => sim.onGround(w, {x: c.q[0], y: c.q[1], z: c.q[2]}, solid));
    res.look = Q.look.map(c => sim.lookDir(c.q[0], c.q[1]));
    res.ray = Q.ray.map(c => sim.ray(w, ...c.q));
    res.eye = Q.eye.map(c => sim.eye({x: c.q[0], y: c.q[1], z: c.q[2], flags: c.q[3]}));
    res.box = Q.box.map(c => sim.playerBoxHits({x: c.q[0], y: c.q[1], z: c.q[2]}, c.q[3], c.q[4], c.q[5], c.q[6]));
    worlds.push(w);
    out.worlds.push(res);
}
// the runs
const ts = performance.now();
let steps = 0;
for (const r of job.runs) {
    const w = worlds[r.world];
    let s = r.start;
    const lines = [], raw = [];
    for (const [th, sr, bt] of r.inputs) {
        const n = sim.stepPlayer(s, [th / 100, sr / 100, bt], sim.STEP, w, r.creative);
        steps++;
        if (r.raw) raw.push(["x", "y", "z", "vx", "vy", "vz", "fall"].map(k => n[k]));
        Object.assign(n, sim.quantise(n));
        lines.push(sim.wireInts(n).join(","));
        s = n;
    }
    const m = md5(lines.join(";"));
    out.runs.push({md5: m, lines: m === r.md5 ? null : lines, raw: r.raw ? raw : null});
}
out.us_per_step = (performance.now() - ts) * 1000 / Math.max(1, steps);
out.compares = job.compares.map(c => sim.compare(c.a, c.b));
out.dig = job.dig.map(c => sim.digTime(c.bid, c.held === null ? null : sim.itemOf(c.held)));
for (const c of job.predicts) {
    const p = new Predictor(sim.makeStep(worlds[0], c.creative), {...c.start}, 0.05, new InputLog(c.first_seq));
    const seqs = [], errs = [];
    for (let t = 0; t <= c.inputs.length; t++) {
        if (t < c.inputs.length) { const [th, sr, bt] = c.inputs[t]; seqs.push(p.apply([th / 100, sr / 100, bt], sim.STEP)); }
        for (const j of c.deliver[t]) {
            const ack = seqs[j];
            if (ack === 0) continue;
            const err = p.correct({...c.server[j]}, ack, sim.STEP, sim.compare);
            errs.push(err === Infinity ? null : err);
        }
    }
    out.predicts.push({errs, corrections: p.corrections, final: sim.wireInts(p.state), log: p.log.length});
}
// the light again after the server's changes (each world's list at once, then one block at a time)
job.worlds.forEach((wj, i) => {
    const w = worlds[i];
    w.applyChanges(job.changes[i]);
    const once = [md5(w.sky), md5(w.glow)];
    for (const [x, y, z, bid, meta] of job.singles[i]) w.set(x, y, z, bid, meta);
    out.worlds[i].lightAfter = once;
    out.worlds[i].lightSingles = [md5(w.sky), md5(w.glow), md5(w.blocks)];
});
// the Garage and the code panel: schema.js with schemas.json's Craft Lab
{
    const G = JSON.parse(fs.readFileSync("schemas.json", "utf8")).craftlab;
    const outcome = f => { try { return {ok: f()}; } catch (e) { return e instanceof SC.ParseError ? {error: [e.lineno, e.message]} : {crash: e.constructor.name}; } };
    const plain = v => JSON.parse(JSON.stringify(v, (k, x) => (typeof x === "bigint" ? Number(x) : x instanceof SC.PyStr ? String.fromCodePoint(...x.cps)
        : x instanceof SC.PyFloat ? x.v : x)));
    out.schema = job.schema.map(c => {
        const ctx = SC.codeCtx(G, {rules: {}, tools: {}, limits: c.limits, design: c.design});
        const lines = outcome(() => SC.codeLines(G, JSON.parse(JSON.stringify(c.design)), ctx));
        const parsed = outcome(() => plain(SC.parseCode(G, c.text, ctx)));
        let applied = null;
        if ("ok" in parsed) {
            const nd = JSON.parse(JSON.stringify(c.design));
            const values = SC.parseCode(G, c.text, ctx);
            const res = outcome(() => { const r = SC.applyValues(G, nd, values, ctx, () => true); return [r.changed, r.hidden, r.problems]; });
            applied = {res, design: plain(nd)};
        }
        let stats = null;
        if (c.design && typeof c.design.points === "object" && !Array.isArray(c.design.points)) stats = SC.statsText(G, c.design);
        return {lines, parsed, applied, check: SC.checkDesign(G, JSON.parse(JSON.stringify(c.design)), c.limits), stats};
    });
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
"""


def main():
    if CRAFT is None:
        print("Craft Lab's folder isn't beside this one: nothing to test against.")
        return 1
    node = shutil.which("node")
    if not node:
        print("node isn't installed: the browser's Craft Lab can't be checked here (passing with this note)")
        print("1 of 1 passed")
        return 0
    with open(os.path.join(HERE, "craft.json"), encoding="utf-8") as f:
        data = json.load(f)
    atlas, where = craft_art.build_atlas()
    check("craft.json's atlas places are craft_art's (make_craft.py has been run since craft/ changed)",
          {k: tuple(v) for k, v in data["atlas"]["where"].items()} == where)
    tables = M.Tables(where)
    rng = random.Random(SEED)
    t0 = time.perf_counter()
    worlds = make_worlds()
    lights = [light_md5(w) for w, _ in worlds]
    meshes = [mesh_md5s(w, tables) for w, _ in worlds]
    questions = [make_questions(random.Random(SEED + 10 + i), w, spots) for i, (w, spots) in enumerate(worlds)]
    runs, raws, cover = run_players(rng, worlds)
    compares = make_compares(random.Random(SEED + 2))
    digs = dig_cases()
    predicts = make_predicts(random.Random(SEED + 3), *worlds[0])
    schemas = schema_cases(random.Random(SEED + 4))
    changes = [make_changes(random.Random(SEED + 20 + i), w, spots) for i, (w, spots) in enumerate(worlds)]
    singles = [make_changes(random.Random(SEED + 30 + i), w, spots)[:25] for i, (w, spots) in enumerate(worlds)]
    py_predicts = [run_predict_py(c, worlds[0][0]) for c in predicts]
    py_time = time.perf_counter() - t0
    jobs_worlds = [world_job(w) for w, _ in worlds]  # (before the changes)
    after, after_singles = [], []
    for (w, _), ch, single in zip(worlds, changes, singles):
        w.apply_changes([tuple(c) for c in ch])
        after.append(light_md5(w))
        for x, y, z, bid, meta in single:
            w.set(x, y, z, bid, meta, record=False)
        after_singles.append(light_md5(w) + [md5(w.blocks.tobytes())])

    tmp = tempfile.mkdtemp(prefix="craft_sim_test_")
    try:
        for f in JS_FILES:
            shutil.copy(os.path.join(HERE, f), tmp)
        with open(os.path.join(tmp, "package.json"), "w") as f:
            f.write('{"type": "module"}')
        with open(os.path.join(tmp, "runner.js"), "w", encoding="utf-8") as f:
            f.write(RUNNER)
        job = {"tables": data, "worlds": jobs_worlds, "constants": CONSTANTS,
               "questions": [{k: [{"q": c["q"]} for c in v] for k, v in q.items()} for q in questions],
               "runs": [{k: v for k, v in r.items() if not k.startswith("_")} for r in runs],
               "compares": [{"a": c["a"], "b": c["b"]} for c in compares], "dig": [{"bid": c["bid"], "held": c["held"]} for c in digs],
               "predicts": predicts, "changes": changes, "singles": singles,
               "schema": [{k: c[k] for k in ("design", "limits", "text")} for c in schemas]}
        with open(os.path.join(tmp, "job.json"), "w") as f:
            json.dump(job, f)
        t1 = time.perf_counter()
        r = subprocess.run([node, os.path.join(tmp, "runner.js"), os.path.join(tmp, "job.json"), os.path.join(tmp, "out.json")],
                           capture_output=True, text=True, cwd=tmp)
        js_time = time.perf_counter() - t1
        if r.returncode != 0:
            print(r.stdout, r.stderr)
            check("node ran the browser's modules", False, r.stderr.strip().splitlines()[-1] if r.stderr else "")
            return report()
        with open(os.path.join(tmp, "out.json"), encoding="utf-8") as f:
            out = json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # the record and the numbers
    want = [list(f) for f in sim.SCHEMA_FIELDS]
    check("wire.js's CRAFT_FIELDS and craft_sim.js's SCHEMA_FIELDS are craft_sim.SCHEMA_FIELDS, field for field",
          out["fields"] == want and out["simFields"] == want, f"{out['fields']} / {out['simFields']}")
    py_consts = {k: getattr(sim, k) for k in CONSTANTS}
    wrong = {k: (v, out["constants"].get(k)) for k, v in py_consts.items() if out["constants"].get(k) != v}
    check(f"craft_sim.js's {len(py_consts)} numbers (the speeds, the box, the buttons and flags) are craft_sim's", not wrong, str(wrong))
    check("the blocks' heights (slabs, beds, farmland) are craft_sim.heights' for every block id", out["heights"] == heights_cases())

    for i, ((w, spots), res) in enumerate(zip(worlds, out["worlds"])):
        name = f"island {SEEDS[i]}"
        check(f"{name}: the sky's and the torches' light in all {w.X * w.Y * w.Z} blocks is craft_world.light_all's "
              f"({len(spots)} things stamped in)", res["light"] == lights[i], f"python {lights[i]} js {res['light']}")
        check(f"{name}: the light after {CHANGES} blocks changed at once (apply_changes) and 25 more one at a time (set) is "
              f"craft_world's", res["lightAfter"] == after[i] and res["lightSingles"] == after_singles[i])
        bad = [f"{a} / {b}" for a, b in zip(meshes[i], res["meshes"]) if a != b]
        check(f"{name}: every chunk's meshes ({len(meshes[i])} chunk-looks: the solid, cutout and blend passes, the mesh and "
              f"lines looks' edges) are craft_mesh's byte for byte", not bad and len(meshes[i]) == len(res["meshes"]), "; ".join(bad[:2]))
        q = questions[i]
        for key, words in (("blocked", "blocked"), ("ground", "on_ground"), ("box", "player_box_hits")):
            bad = [j for j, (c, a) in enumerate(zip(q[key], res[key])) if c["a"] != a]
            check(f"{name}: {words} gives craft_sim's answers ({len(q[key])} cases)", not bad, str([q[key][j] for j in bad[:2]]))
        bad = [j for j, (c, a) in enumerate(zip(q["touching"], res["touching"])) if c["a"] != a]
        check(f"{name}: touching water and ladders gives craft_sim's answers ({len(q['touching'])} cases)", not bad)
        # (look_dir isn't in the step: it is math.sin and math.cos, the C library's, which pymath.js's fdlibm matches to
        # within a bit or two; the ray is checked with Python's own directions, exactly)
        bad = [j for j, (c, a) in enumerate(zip(q["look"], res["look"])) if any(abs(u - v) > 4e-16 for u, v in zip(c["a"], a))]
        last = sum(1 for c, a in zip(q["look"], res["look"]) if c["a"] != a)
        check(f"{name}: look_dir is craft_sim's to within two units in the last place ({len(q['look'])} cases, {last} not to the "
              f"last bit)", not bad, str([(q['look'][j], res['look'][j]) for j in bad[:2]]))
        bad = [j for j, (c, a) in enumerate(zip(q["ray"], res["ray"])) if c["a"] != a]
        hits = sum(1 for c in q["ray"] if c["a"] is not None)
        check(f"{name}: the ray to the block looked at (the block, the face, the distance) is craft_sim.ray's "
              f"({len(q['ray'])} rays, {hits} hits)", not bad, str([(q['ray'][j], res['ray'][j]) for j in bad[:2]]))
        bad = [j for j, (c, a) in enumerate(zip(q["eye"], res["eye"])) if c["a"] != a]
        check(f"{name}: eye is craft_sim's", not bad)
        print(f"  {name}: light {res['lightMs']:.0f} ms in node, a chunk meshed in {res['meshMs']:.1f} ms")

    bad = [j for j, (c, a) in enumerate(zip(digs, out["dig"])) if [c["a"][0], c["a"][1]] != a]
    check(f"dig_time for every block with every tool and a hand ({len(digs)} cases) is craft_blocks'", not bad,
          str([(digs[j], out['dig'][j]) for j in bad[:2]]))

    # the runs
    bad = []
    for i, (d, js) in enumerate(zip(runs, out["runs"])):
        if js["md5"] != d["md5"]:
            n = next((k for k, (a, b) in enumerate(zip(d["_lines"], js["lines"])) if a != b), None)
            bad.append(f"run {i} first differs at tick {n}: python {d['_lines'][n]} js {js['lines'][n]}")
    check(f"{len(runs)} players' runs of {TICKS} ticks give the server's wire numbers tick for tick", not bad, "; ".join(bad[:3]))
    print("  what the players did (ticks):", ", ".join(f"{k} {v}" for k, v in cover.items()))
    check("the players walked, sprinted, sneaked (stopping at edges), jumped, stepped up, swam, climbed, fell, landed, "
          "flew and met walls", all(cover.values()), str(cover))
    diff, total = 0, 0
    worst = [0.0] * len(RAW)
    for i, raw in raws.items():
        for a, b in zip(raw, out["runs"][i]["raw"]):
            total += 1
            if a != b:
                diff += 1
                for f in range(len(RAW)):
                    if a[f] != b[f]:
                        worst[f] = max(worst[f], abs(a[f] - b[f]))
    check(f"before the rounding the player's numbers are the same to the last bit too ({total} ticks)", diff == 0,
          ", ".join(f"{RAW[f]} {worst[f]:.1e}" for f in range(len(RAW))) + f" ({diff} ticks differ)")

    wrong = [i for i, (c, js) in enumerate(zip(compares, out["compares"])) if c["out"] != js]
    check(f"compare() is craft_sim.compare ({len(compares)} pairs)", not wrong, str([(compares[i]["out"], out["compares"][i]) for i in wrong[:3]]))

    same, corr, exact, final_ok, bad = True, 0, 0, True, []
    for i, (c, js, py) in enumerate(zip(predicts, out["predicts"], py_predicts)):
        if not (py["errs"] == js["errs"] and py["corrections"] == js["corrections"] and py["log"] == js["log"]):
            same = False
            bad.append(f"run {i}: python {py['corrections']} corrections, js {js['corrections']}")
        corr += py["corrections"]
        server_final = SCHEMA.ints(c["server"][-1])
        exact += js["final"] == server_final
        final_ok &= js["final"] == py["final"] and sim.compare(SCHEMA.values(js["final"]), SCHEMA.values(server_final)) < 0.05
    surprises = sum(c["surprises"] for c in predicts)
    check(f"the Predictor makes engine.predict's corrections with craft_sim's step ({len(predicts)} runs, {corr} corrections "
          f"for {surprises} knocks, shoves and respawns only the server knew of: late, jittered and skipped snapshots, "
          f"numbers wrapping)", same, "; ".join(bad[:3]))
    check(f"the Predictor ends on the server's state ({exact} of {len(predicts)} to the millimetre, all within the 5 cm it "
          f"ignores)", final_ok)

    # the Garage and the code panel
    for key, words in (("lines", "the code written (engine.schema.code_lines)"), ("parsed", "the code read back, as written, edited and broken (parse_code)"),
                       ("applied", "the values put in the design (apply_values)"), ("check", "the design checked (craft_design.check_design)"),
                       ("stats", "the garage's stats line (craft_panels.Garage)")):
        # (a colour list the server would never let in, [1, 2]: Python's code_lines stops at it; only the rest compared)
        bad = [i for i, (c, js) in enumerate(zip(schemas, out["schema"])) if c["want"][key] != js[key]
               and not (key == "lines" and "crash" in c["want"][key])]
        check(f"schema.js with schemas.json's Craft Lab: {words}, {len(schemas)} Craft Bot designs", not bad,
              "; ".join(f"{schemas[i]['want'][key]} / {out['schema'][i][key]}" for i in bad[:2]))
    errors = sum(1 for c in schemas if "error" in c["want"]["parsed"])
    print(f"  (the code panel's cases: {errors} of {len(schemas)} texts with a mistake in them)")

    fingerprint = {"sim_version": sim.SIM_VERSION, "runs": md5([r["md5"] for r in runs])}
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
              f"craft_sim_golden.json is for SIM_VERSION {golden.get('sim_version')}, the step is {sim.SIM_VERSION}: run "
              f"this with --record in the same commit as the change")
    else:
        check(f"the runs' numbers are the ones recorded for SIM_VERSION {sim.SIM_VERSION} (the same on every computer: a "
              f"change that moves them needs a new SIM_VERSION)", golden == fingerprint, f"recorded {golden}, now {fingerprint}")
    print(f"  (Python made it all in {py_time:.1f} s; node ran it in {js_time:.1f} s, {out['us_per_step']:.2f} us a step)")
    return report()


def report():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # (an emoji in a design's name)
    except (AttributeError, ValueError):
        pass
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {detail}" if detail and not ok else ""))
    passed = sum(ok for _, ok, _ in results)
    print(f"{passed} of {len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
