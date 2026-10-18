"""The browser's kart step and prediction (kart_sim.js, predict.js, pymath.js) against Kart Lab's own Python.

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\kart_sim_test.py      (from the ClubCodersAI folder)

Runs the same karts through kart/kart_sim.py and, with node, through kart_sim.js, and checks:
  - the tracks: track.js builds every track in kart_track.TRACKS to the last bit (points, lengths, tangents);
  - the step: thousands of random drives (600 ticks each, every track, random designs, starting places, speeds
    and inputs: full throttle, braking, reversing, drifts long enough for both turbos, dash pads, oil, barriers,
    respawns, the wrong way round) give the same wire numbers and track segment tick for tick, as the server
    applies them (respawn, step, quantise); and how far apart the two are before the rounding (the system's cos,
    sin and exp may differ in the last bit between any two machines: printed, with the closest a value came to
    rounding the other way);
  - the input frame: packInput's 18 bytes are pack_input's, and quantiseInput is quantise_input (halves rounded
    to even, buttons cut to a byte);
  - the prediction: a Predictor stepping the kart with snapshots arriving late, jittered, some skipped, with
    bumps and respawns only the server knew of and the sequence numbers wrapping, makes the same corrections
    with the same errors as engine.predict's, and ends on the server's state; the ErrorSmoother's offsets and the
    LeadController's multipliers are engine.predict's.
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
# the kart game: games/kartlab beside web/ in the public repository, kart/ two folders up in the working folder
KART = next((p for p in (os.path.join(os.path.dirname(HERE), "games", "kartlab"),
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "kart"))
             if os.path.isdir(p)), None)
sys.path.insert(0, KART)
import kart_version  # noqa: E402,F401  (puts the engine on the path)
import kart_sim  # noqa: E402
import kart_track  # noqa: E402
from engine import predict, wire  # noqa: E402

SCHEMA = wire.Schema("kart", kart_sim.SCHEMA_FIELDS)
JS_FILES = ["pymath.js", "track.js", "kart_sim.js", "predict.js", "wire.js"]
RUNS = {"club": 2000, "oval": 600, "straight": 400}
TICKS = 600
RAW_RUNS = 300            # runs whose numbers before the rounding are compared too
PREDICT_RUNS = 40
SEED = 20261014

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


# ---------- the drives (Python) ----------
def wire_line(k):
    return ",".join(map(str, SCHEMA.ints(k)))


def md5(parts):
    return hashlib.md5(";".join(parts).encode()).hexdigest()


def random_inputs(rng, ticks):
    """Held inputs as wire integers: [throttle x100, steer x100, buttons] per tick, RESPAWN on one tick only."""
    out = []
    while len(out) < ticks:
        hold = rng.randint(1, 45)
        r = rng.random()
        th = 1.0 if r < 0.6 else 0.0 if r < 0.68 else -1.0 if r < 0.8 else rng.uniform(-1, 1)
        r = rng.random()
        st = rng.choice((-1.0, 1.0)) if r < 0.3 else 0.0 if r < 0.5 else rng.uniform(-1, 1)
        bt = (kart_sim.DRIFT if rng.random() < 0.35 else 0) | (kart_sim.USE if rng.random() < 0.05 else 0)
        t, s, b = wire.quantise_input(th, st, bt)
        for j in range(hold):
            extra = kart_sim.RESPAWN if j == 0 and rng.random() < 0.012 else 0
            out.append([round(t * 100), round(s * 100), b | extra])
    return out[:ticks]


def random_start(rng, track):
    design = kart_sim.fit_design({k: rng.randint(10, 60) for k in kart_sim.STATS})
    k = kart_sim.new_kart(1, design, 0.0, 0.0, 0.0)
    k["cp"], k["lap"] = rng.randint(0, kart_track.GATES), rng.randint(0, 3)
    kart_sim.place(track, k, rng.uniform(0, track.length), rng.uniform(-track.half, track.half) * 0.9)
    k["flags"] = rng.choice((0, 0, 0, kart_sim.FLAG_WRONG_WAY, kart_sim.FLAG_FINISHED))  # (after place: it clears them)
    if rng.random() < 0.5:  # (a running start: some speed, a heading off the track's, a slide, a boost or oil)
        k["v"] = rng.uniform(-5, 30)
        k["u"] = rng.uniform(-3, 3)
        k["yaw"] = (k["yaw"] + rng.uniform(-60, 60) + (180 if rng.random() < 0.15 else 0) + 180) % 360 - 180
        k["boost"] = rng.choice((0, 0, rng.randint(1, 100)))
        k["slip"] = rng.choice((0, 0, rng.randint(1, 75)))
        k["charge"] = rng.choice((0, rng.randint(0, 700)))
        k["flags"] |= rng.choice((0, kart_sim.FLAG_DRIFT_L, kart_sim.FLAG_DRIFT_R))
    if rng.random() < 0.12 and track.pit:  # (CHANGE 158) some start slowly in the PIT box...
        s0, s1, side = track.pit
        kart_sim.place(track, k, rng.uniform(s0, s1 - 4), side * (track.half - 1.6))
        k["v"] = rng.uniform(0, 6)
    if rng.random() < 0.4:  # ...and some damaged
        for part in kart_sim.DAMAGE_PARTS:
            k[part] = rng.choice((0, rng.randint(0, kart_sim.DAMAGE_MAX)))
    k.update(SCHEMA.quantise(k))
    return design, k


def server_tick(race, k, inp, st):
    """One kart's tick as kart_sim.Race.step_all does it (no other karts): respawn, step, quantise.
    Returns (state, the step's raw result before the rounding)."""
    th, sr, bt = inp
    inp = (th / 100, sr / 100, bt)
    if bt & kart_sim.RESPAWN:
        k = dict(k)
        race.respawn(k)
        inp = (0.0, 0.0, 0)
    n = kart_sim.step(k, inp, kart_sim.STEP, race.track, st, True)  # (real damage on: CHANGE 158)
    raw = [n["x"], n["y"], n["yaw"], n["v"], n["u"], n["s"], n["lat"]]
    n.update(SCHEMA.quantise(n))
    return n, raw


def make_drives(rng, tracks):
    drives, raws, cover = [], {}, dict.fromkeys(
        ("drift boost (super)", "drift boost (mini)", "dash pad", "oil", "barrier", "respawn", "reversing",
         "boosting", "drifting", "wrong-way flag", "damaged", "mended in the PIT box"), 0)
    for name, count in RUNS.items():
        track = tracks[name]
        race = kart_sim.Race(track, SCHEMA)
        limit = track.half - kart_sim.KART_HALF
        for _ in range(count):
            design, k = random_start(rng, track)
            st = kart_sim.stats_of(design)
            inputs = random_inputs(rng, TICKS)
            start = dict(k)
            lines, segs, where, raw = [], [], [], []
            for inp in inputs:
                was = k
                k, r = server_tick(race, k, inp, st)
                lines.append(wire_line(k))
                segs.append(str(k["seg"]))
                where.append((k["s"], k["lat"]))
                if len(drives) < RAW_RUNS:
                    raw.append(r)
                # (what happened, so the printout shows the drives went everywhere they should)
                if inp[2] & kart_sim.RESPAWN:
                    cover["respawn"] += 1
                elif k["boost"] == kart_sim.SUPER_BOOST - 1 and was["charge"] >= kart_sim.SUPER_TURBO:
                    cover["drift boost (super)"] += 1
                elif k["boost"] == kart_sim.MINI_BOOST - 1 and was["charge"] >= kart_sim.MINI_TURBO:
                    cover["drift boost (mini)"] += 1
                if k["boost"] == kart_sim.PAD_BOOST - 1:
                    cover["dash pad"] += 1
                if k["slip"] == kart_sim.OIL_TICKS - 1:
                    cover["oil"] += 1
                if abs(k["lat"]) == limit:
                    cover["barrier"] += 1
                cover["reversing"] += k["v"] < 0
                cover["boosting"] += bool(k["flags"] & kart_sim.FLAG_BOOSTING)
                cover["drifting"] += bool(k["flags"] & (kart_sim.FLAG_DRIFT_L | kart_sim.FLAG_DRIFT_R))
                cover["wrong-way flag"] += bool(k["flags"] & kart_sim.FLAG_WRONG_WAY)
                cover["damaged"] += any(k[p] > was.get(p, 0) for p in kart_sim.DAMAGE_PARTS)  # (CHANGE 158)
                cover["mended in the PIT box"] += any(was.get(p, 0) - k[p] == kart_sim.REPAIR_PIT for p in kart_sim.DAMAGE_PARTS)
            if raw:
                raws[len(drives)] = raw
            drives.append({"track": name, "design": design, "start": start, "inputs": inputs,
                           "md5": md5(lines), "md5_seg": md5(segs), "raw": len(drives) < RAW_RUNS,
                           "_lines": lines, "_segs": segs, "_where": where})
    return drives, raws, cover


# ---------- the input frames (Python) ----------
def make_packs(rng):
    cases = []
    halves = [x / 1000 for x in range(-1300, 1301, 5)]  # (every half a hundredth: round half to even)
    for i in range(3000):
        def val():
            r = rng.random()
            return rng.choice(halves) if r < 0.4 else rng.uniform(-1.6, 1.6) if r < 0.9 else rng.choice((-1.0, 0.0, 1.0))

        def btn():
            return rng.choice((rng.randint(0, 7), rng.randint(-5, 300), rng.uniform(-3, 300)))
        prev = [[val(), val(), btn()] for _ in range(rng.randint(0, 3))]
        args = [rng.randint(-70000, 140000), rng.randint(-70000, 140000), rng.randint(0, 2 ** 44), val(), val(), btn()]
        cases.append({"args": args, "prev": prev,
                      "hex": wire.pack_input(*args, previous=[tuple(p) for p in prev]).hex(),
                      "q": list(wire.quantise_input(args[3], args[4], args[5]))})
    return cases


def make_bumps(rng):  # (CHANGE 155) two karts touching or nearly, bumped and carried on a tick, as the prediction does
    cases = []
    for i in range(2000):
        def kart():
            return {"x": rng.uniform(-3, 3), "y": rng.uniform(-3, 3), "yaw": rng.uniform(-180, 180),
                    "v": rng.uniform(-6, 30), "u": rng.uniform(-3, 3)}
        a, b = kart(), kart()
        reach, slow = rng.choice(((kart_sim.BUMP_DISTANCE, 0.3), (2.5, 0.6)))
        damage = rng.random() < 0.6  # (CHANGE 158, 159: the damage a bump does, and the grace after one)
        for k in (a, b):
            for part in kart_sim.DAMAGE_PARTS:
                k[part] = rng.choice((0, rng.randint(0, kart_sim.DAMAGE_MAX)))
            k["bg"] = rng.choice((0, 0, rng.randint(1, kart_sim.BUMP_GRACE)))
        b["steer"], b["rate"], b["top"] = rng.choice((0.0, rng.uniform(-1, 1))), rng.uniform(100, 160), rng.uniform(19, 31)
        case = {"a": dict(a), "b": dict(b), "reach": reach, "slow": slow, "damage": damage}
        touched = kart_sim.bump(a, b, reach, slow, damage)
        kart_sim.coast(b, kart_sim.STEP)
        case["out"] = [a, b, touched]
        cases.append(case)
    return cases


# ---------- the prediction (Python) ----------
def make_predicts(rng, track):
    race = kart_sim.Race(track, SCHEMA)
    cases = []
    for c in range(PREDICT_RUNS):
        design, k = random_start(rng, track)
        k["flags"] &= ~kart_sim.FLAG_FINISHED
        k.update(SCHEMA.quantise(k))
        start = {n: k[n] for n in SCHEMA.names}  # (the window starts from the server's word: a snapshot record)
        st = kart_sim.stats_of(design)
        inputs = random_inputs(rng, TICKS)
        bumps = {rng.randint(50, TICKS - 60): (rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8)) for _ in range(3)}
        first_seq = rng.choice((0, 65400 + rng.randint(0, 135), rng.randint(1, 65535)))
        # the server: the same inputs in order, a bump now and then from a kart the window doesn't predict
        server = []
        for t, inp in enumerate(inputs):
            k, _ = server_tick(race, k, inp, st)
            if t in bumps:
                dx, dy = bumps[t]
                k["x"] += dx
                k["y"] += dy
                k["v"] *= 0.97
                k.update(SCHEMA.quantise(k))
            server.append({n: k[n] for n in SCHEMA.names})
        # the snapshots: a few ticks late, jittered, some never sent (the server skips a tick now and then), in
        # order as a WebSocket keeps them (several arriving in one tick after a hold-up), the last after the end
        deliver = [[] for _ in range(TICKS + 1)]
        delay, at = rng.randint(2, 10), 0
        for t in range(TICKS - 1):
            if rng.random() < 0.08:
                continue
            at = min(TICKS, max(at, t + delay + rng.choice((0, 0, 0, 1, 2, 5))))
            deliver[at].append(t)
        deliver[TICKS].append(TICKS - 1)
        depths = [rng.choice((0, 0, 1, 1, 2, 2, 3, 5)) for _ in range(200)]
        surprises = len(bumps) + sum(1 for i in inputs if i[2] & kart_sim.RESPAWN)
        cases.append({"design": design, "start": start, "inputs": inputs, "server": server, "deliver": deliver,
                      "first_seq": first_seq, "depths": depths, "surprises": surprises})
    return cases


def run_predict_py(case, track, start):
    st = kart_sim.stats_of(case["design"])

    def step(state, inp, dt):
        n = kart_sim.step(state, inp, dt, track, st)
        n.update(SCHEMA.quantise(n))
        return n

    def full(rec):
        seg, s, lat = track.locate(rec["x"], rec["y"], None)
        return dict(rec, seg=seg, s=s, lat=lat)

    p = predict.Predictor(step, full(start), ignore=0.05, log=predict.InputLog(first_seq=case["first_seq"]))
    sm = predict.ErrorSmoother(remove_up=True)
    seqs, errs, offs = [], [], []
    for t in range(TICKS + 1):
        if t < TICKS:
            th, sr, bt = case["inputs"][t]
            seqs.append(p.apply((th / 100, sr / 100, bt), kart_sim.STEP))
        for j in case["deliver"][t]:
            ack = seqs[j]
            if ack == 0:
                continue  # (kart_client: the server hasn't applied an input of ours yet)
            err = p.correct(full(case["server"][j]), ack, kart_sim.STEP, kart_sim.compare)
            errs.append(None if err == math.inf else err)
            moved = p.moved_from
            if moved is not None and err != math.inf:
                new = p.state
                dyaw = math.radians((moved["yaw"] - new["yaw"] + 180) % 360 - 180)
                sm.add((moved["x"] - new["x"], moved["y"] - new["y"], 0.0), dyaw)
        dpos, dyaw = sm.offset(kart_sim.STEP)
        offs.append(list(dpos) + [dyaw])
    lead = predict.LeadController()
    mult = [lead.feed(d) for d in case["depths"]]
    return {"errs": errs, "corrections": p.corrections, "final": SCHEMA.ints(p.state), "offs": offs,
            "mult": mult, "log": len(p.log), "snaps": sm.snaps}


# ---------- the JavaScript side ----------
RUNNER = r"""
import fs from "fs";
import crypto from "crypto";
import {Track, TRACKS} from "./track.js";
import * as sim from "./kart_sim.js";
import {Predictor, InputLog, ErrorSmoother, LeadController, packInput, quantiseInput} from "./predict.js";
import {radians, pyMod} from "./pymath.js";

const job = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = {tracks: {}, drives: [], packs: [], predicts: [], bumps: []};
{  // (CHANGE 158) the record the page reads snapshots with (wire.js), and kart_sim.js's
    const w = await import("./wire.js");
    out.kartFields = w.KART_FIELDS;
    out.simFields = sim.SCHEMA_FIELDS;
}
const tracks = {};
for (const name of Object.keys(TRACKS)) {
    const t = tracks[name] = new Track(TRACKS[name]);
    out.tracks[name] = {pts: t.pts, seg_len: t.segLen, tan: t.tan, s: t.s, length: t.length, gate_s: t.gateS};
}

// the drives, as the server ticks a kart: respawn, step, quantise
const t0 = performance.now();
let steps = 0;
for (const d of job.drives) {
    const track = tracks[d.track], st = sim.statsOf(d.design);
    let k = d.start;
    const lines = [], segs = [], where = [], raw = [];
    for (const [th, sr, bt] of d.inputs) {
        let inp = [th / 100, sr / 100, bt];
        if (bt & sim.RESPAWN) {
            k = sim.respawn(k, track);
            inp = [0.0, 0.0, 0];
        }
        const n = sim.step(k, inp, sim.STEP, track, st, true);  // (real damage on: CHANGE 158)
        steps++;
        if (d.raw) raw.push([n.x, n.y, n.yaw, n.v, n.u, n.s, n.lat]);
        Object.assign(n, sim.quantise(n));
        lines.push(sim.wireInts(n).join(","));
        segs.push(String(n.seg));
        where.push([n.s, n.lat]);
        k = n;
    }
    const md5 = crypto.createHash("md5").update(lines.join(";")).digest("hex");
    const md5Seg = crypto.createHash("md5").update(segs.join(";")).digest("hex");
    out.drives.push({md5, lines: md5 === d.md5 ? null : lines, raw: d.raw ? raw : null,
                     segs: md5Seg === d.md5_seg ? null : segs, where: md5Seg === d.md5_seg ? null : where});
}
out.us_per_step = (performance.now() - t0) * 1000 / steps;

for (const c of job.packs) {
    const [seq, snap, ms, th, sr, bt] = c.args;
    const hex = Buffer.from(packInput(seq, snap, ms, th, sr, bt, c.prev)).toString("hex");
    out.packs.push({hex, q: quantiseInput(th, sr, bt)});
}

for (const c of job.bumps) {  // (CHANGE 155)
    const a = {...c.a}, b = {...c.b};
    const touched = sim.bump(a, b, c.reach, c.slow, c.damage);
    sim.coast(b, sim.STEP);
    out.bumps.push([a, b, touched]);
}

// the prediction, as kart_client.on_snapshot and client_tick use it
for (const c of job.predicts) {
    const track = tracks.club, st = sim.statsOf(c.design);
    const p = new Predictor(sim.makeStep(track, st), sim.fullState(c.start, track), 0.05, new InputLog(c.first_seq));
    const sm = new ErrorSmoother({removeUp: true});
    const seqs = [], errs = [], offs = [];
    for (let t = 0; t <= c.inputs.length; t++) {
        if (t < c.inputs.length) {
            const [th, sr, bt] = c.inputs[t];
            seqs.push(p.apply([th / 100, sr / 100, bt], sim.STEP));
        }
        for (const j of c.deliver[t]) {
            const ack = seqs[j];
            if (ack === 0) continue;
            const err = p.correct(sim.fullState(c.server[j], track), ack, sim.STEP, sim.compare);
            errs.push(err === Infinity ? null : err);
            const moved = p.movedFrom;
            if (moved !== null && err !== Infinity) {
                const n = p.state;
                const dyaw = radians(pyMod(moved.yaw - n.yaw + 180, 360) - 180);
                sm.add([moved.x - n.x, moved.y - n.y, 0.0], dyaw);
            }
        }
        const [dpos, dyaw] = sm.offset(sim.STEP);
        offs.push([...dpos, dyaw]);
    }
    const lead = new LeadController();
    const mult = c.depths.map(d => lead.feed(d));
    out.predicts.push({errs, corrections: p.corrections, final: sim.wireInts(p.state), offs, mult,
                       log: p.log.length, snaps: sm.snaps});
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
"""


def ulps(a, b):
    """How many representable doubles apart a and b are."""
    import struct

    def key(x):
        i = struct.unpack("<q", struct.pack("<d", x))[0]
        return i if i >= 0 else -(i & 0x7FFFFFFFFFFFFFFF)
    return abs(key(a) - key(b))


def main():
    node = shutil.which("node")
    if not node:
        print("node isn't installed: the browser's kart step can't be checked here (passing with this note)")
        print("1 of 1 passed")
        return 0
    rng = random.Random(SEED)
    tracks = {name: kart_track.load(name) for name in kart_track.TRACKS}
    t0 = time.perf_counter()
    drives, raws, cover = make_drives(rng, tracks)
    packs = make_packs(rng)
    predicts = make_predicts(rng, tracks["club"])
    bumps = make_bumps(random.Random(SEED + 1))
    py_time = time.perf_counter() - t0

    tmp = tempfile.mkdtemp(prefix="kart_sim_test_")
    try:
        for f in JS_FILES:
            shutil.copy(os.path.join(HERE, f), tmp)
        with open(os.path.join(tmp, "package.json"), "w") as f:
            f.write('{"type": "module"}')
        with open(os.path.join(tmp, "runner.js"), "w", encoding="utf-8") as f:
            f.write(RUNNER)
        job = {"drives": [{k: v for k, v in d.items() if not k.startswith("_")} for d in drives],
               "packs": packs, "predicts": predicts, "bumps": bumps}
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

    # the tracks
    for name, t in tracks.items():
        js = out["tracks"][name]
        same = (js["pts"] == [list(p) for p in t.pts] and js["seg_len"] == t.seg_len and
                js["tan"] == [list(p) for p in t.tan] and js["s"] == t.s and js["length"] == t.length and
                js["gate_s"] == t.gate_s)
        check(f"track.js builds '{name}' to the last bit ({t.n} points, {t.length:.2f} m)", same)

    # the drives
    bad = []
    for i, (d, js) in enumerate(zip(drives, out["drives"])):
        if js["md5"] != d["md5"]:
            first = next((n for n, (a, b) in enumerate(zip(d["_lines"], js["lines"])) if a != b), None)
            bad.append(f"drive {i} ({d['track']}) first differs at tick {first}: python {d['_lines'][first]} "
                       f"js {js['lines'][first]}")
    for name, count in RUNS.items():
        mine = [b for b in bad if f"({name})" in b]
        check(f"'{name}': {count} drives of {TICKS} ticks give the server's wire numbers tick for tick", not mine,
              "; ".join(mine[:3]))
    # the segment (not on the wire: the hint where the next tick's search of the track starts). Where a kart is
    # right on the joint between two segments both are the same distance away, and a last-bit difference picks
    # the other one: harmless when s and lat (the same point, said from either side) agree
    # (the joint's own point, said from either segment: the same s; lat is the distance across each segment's own
    # direction, so beyond the outside of a bend it differs by a hair)
    flips, worst_s, worst_lat = [], 0.0, 0.0
    for i, (d, js) in enumerate(zip(drives, out["drives"])):
        if js["segs"] is None:
            continue
        t = tracks[d["track"]]
        for tick, (a, b, (s1, l1), (s2, l2)) in enumerate(zip(d["_segs"], js["segs"], d["_where"], js["where"])):
            if a != b:
                ds = abs((s1 - s2 + t.length / 2) % t.length - t.length / 2)
                joint = abs(int(a) - int(b)) in (1, t.n - 1)
                worst_s, worst_lat = max(worst_s, ds), max(worst_lat, abs(l1 - l2))
                flips.append(f"drive {i} tick {tick}: segments {a} / {b}{' (neighbours)' if joint else ''}, "
                             f"s {s1!r} / {s2!r}, lat {l1!r} / {l2!r}")
    for f in flips[:5]:
        print("  segment hint differs:", f)
    seg_ticks = sum(RUNS.values()) * TICKS
    check(f"the track segment agrees too, but for {len(flips)} of {seg_ticks} ticks on a joint between two "
          f"(s within {worst_s:.0e} m, lat {worst_lat:.0e} m: the joint seen from either side)",
          len(flips) <= seg_ticks * 1e-4 and worst_s < 1e-9 and worst_lat < 0.01 and
          all("(neighbours)" in f for f in flips), "; ".join(flips[:3]))
    print("  what the drives did (ticks):", ", ".join(f"{k} {v}" for k, v in cover.items()))
    check("the drives covered drift turbos, dash pads, oil, barriers, respawns, reversing, the wrong way, damage and the PIT box",
          all(cover.values()), str(cover))

    # before the rounding: how far apart, and the closest any value came to rounding differently
    fields = ["x", "y", "yaw", "v", "u", "s", "lat"]
    scales = [100, 100, 10, 100, 100, None, None]
    diff_ticks, total, worst, worst_ulp, closest = 0, 0, [0.0] * 7, [0] * 7, math.inf
    for i, raw in raws.items():
        for a, b in zip(raw, out["drives"][i]["raw"]):
            total += 1
            if a != b:
                diff_ticks += 1
                for f in range(7):
                    if a[f] != b[f]:
                        worst[f] = max(worst[f], abs(a[f] - b[f]))
                        worst_ulp[f] = max(worst_ulp[f], ulps(a[f], b[f]))
                        if scales[f]:
                            frac = (a[f] * scales[f]) % 1.0
                            closest = min(closest, abs(frac - 0.5) / scales[f])
    print(f"  before the rounding: {diff_ticks} of {total} ticks not identical to the bit "
          f"({100 * diff_ticks / max(1, total):.2f}%, from the system's cos/sin/exp); worst per field: " +
          ", ".join(f"{fields[f]} {worst[f]:.1e} ({worst_ulp[f]} ulp)" for f in range(7)))
    print(f"  the closest a differing value came to a rounding edge: {closest:.2e} (m, or degrees for yaw); "
          f"the largest difference was {max(worst[:5]):.1e}")
    check(f"before the rounding the two never differ by more than {max(worst):.0e} (a nanometre at most allowed)",
          max(worst) < 1e-9, str(worst))

    # (CHANGE 158) the page reads the server's snapshots with wire.js's KART_FIELDS: it must be the record field for
    # field (a field added to one and not the other reads every kart wrongly: positions thousands of km off)
    want = [list(f) for f in kart_sim.SCHEMA_FIELDS]
    check("wire.js's KART_FIELDS and kart_sim.js's SCHEMA_FIELDS are kart_sim.SCHEMA_FIELDS, field for field",
          out["kartFields"] == want and out["simFields"] == want, f"{out['kartFields']} / {out['simFields']}")

    # the input frames
    wrong = [i for i, (c, js) in enumerate(zip(packs, out["packs"])) if c["hex"] != js["hex"]]
    check(f"packInput's 18 bytes are pack_input's ({len(packs)} frames, half-hundredths, wrapping numbers)",
          not wrong, "; ".join(f"{packs[i]['args']} py {packs[i]['hex']} js {out['packs'][i]['hex']}"
                               for i in wrong[:3]))
    wrong = [i for i, (c, js) in enumerate(zip(packs, out["packs"])) if c["q"] != js["q"]]
    check("quantiseInput is quantise_input", not wrong, str([packs[i]["args"] for i in wrong[:3]]))

    # (CHANGE 155) the bump between two karts and another kart carried on: the bump to the last bit, the carrying on
    # (cos and sin: the system's) to a nanometre
    def far(c, js):
        (pa, pb, pt), (ja, jb, jt) = c["out"], js
        return (pt != jt or any(pa[k] != ja[k] for k in pa) or pb["v"] != jb["v"] or abs(pb["yaw"] - jb["yaw"]) > 1e-9
                or any(abs(pb[k] - jb[k]) > 1e-9 for k in ("x", "y")))
    wrong = [i for i, (c, js) in enumerate(zip(bumps, out["bumps"])) if far(c, js)]
    touched = sum(1 for c in bumps if c["out"][2])
    check(f"bump and coast are kart_sim's ({len(bumps)} pairs, {touched} touching)", not wrong and 300 < touched,
          str([(bumps[i]["out"], out["bumps"][i]) for i in wrong[:2]]))

    # the prediction
    errs_same, corr, final_ok, offs_ok, mult_ok, worst_off, exact = True, 0, True, True, True, 0.0, 0
    surprises = sum(c["surprises"] for c in predicts)
    for c, js in zip(predicts, out["predicts"]):
        py = run_predict_py(c, tracks["club"], c["start"])
        errs_same &= py["errs"] == js["errs"] and py["corrections"] == js["corrections"] and py["log"] == js["log"]
        corr += py["corrections"]
        server_final = SCHEMA.ints(c["server"][-1])
        exact += js["final"] == server_final
        final_ok &= js["final"] == py["final"] and kart_sim.compare(
            SCHEMA.values(js["final"]), SCHEMA.values(server_final)) < 0.05
        for a, b in zip(py["offs"], js["offs"]):
            worst_off = max(worst_off, max(abs(x - y) for x, y in zip(a, b)))
        offs_ok &= py["snaps"] == js["snaps"]
        mult_ok &= py["mult"] == js["mult"]
    check(f"the Predictor makes engine.predict's corrections with the same errors ({PREDICT_RUNS} drives, "
          f"{corr} corrections for {surprises} bumps and respawns only the server knew of: late, jittered and "
          f"skipped snapshots, numbers wrapping)",
          errs_same)
    check(f"the Predictor ends on the server's state ({exact} of {PREDICT_RUNS} to the centimetre, all within "
          f"the 5 cm it ignores)", final_ok)
    check(f"the ErrorSmoother's offsets are engine.predict's (largest difference {worst_off:.1e} m)",
          offs_ok and worst_off < 1e-9)
    check("the LeadController's multipliers are engine.predict's", mult_ok)
    print(f"  (Python made the drives in {py_time:.1f} s; node ran them in {js_time:.1f} s, "
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
