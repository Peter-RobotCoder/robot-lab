"""Fight Lab's own fighter's footwork drawn ahead (engine/ahead.py's FighterAhead) against fight_sim (CHANGE 167).

    shared-world-demo\\.venv\\Scripts\\python engine\\fighter_ahead_test.py      (from the ClubCodersAI folder)

On one clock: a practice ring (fight_sim) stepping 60 times a second, your fighter driven by a script of keys
(walking, sidestepping, blocking, now and then a punch), a computer sparring partner; snapshots 30 a second (as the
server rounds them) reaching a window 40 ms later, give or take 10, and its keys reaching the server 40 ms later;
the window drawing 60 frames a second, blended by engine.interp, then drawn ahead. Checks: your fighter drawn where
your keys are taking it (95% of frames, against blended); moving within a frame or two of your key; no jumps; drawn
as blended while it attacks or is hit. Exit code 0 = all fine.
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, next(p for p in (os.path.join(os.path.dirname(HERE), "games", "fightlab"),  # (the public repository)
                                     os.path.join(os.path.dirname(HERE), "BeatEmUp")) if os.path.isdir(p)))
import fight_sim as sim  # noqa: E402
import cpu_brains  # noqa: E402
from engine import ahead, interp  # noqa: E402

LATENCY, JITTER = 0.040, 0.010
results = []


def check(name, ok, note=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {note}" if note else ""))


def keys(seed, seconds):
    rng, out, t = random.Random(seed), [], 0.0
    while t < seconds:
        f, s = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (1, 1), (0.7, -0.7)))
        hold = rng.choice(("", "", "", "", "block"))
        press = rng.choice((None,) * 9 + ("punch",))
        out.append((t, float(f), float(s), hold, press))
        t += rng.uniform(0.2, 0.9)
    return out


def key_at(script, t):
    got = (0.0, 0.0, "", None)
    for t0, f, s, h, p in script:
        if t0 > t:
            break
        got = (f, s, h, p)
    return got


class Recorder(ahead.FighterAhead):
    """FighterAhead, every call written down (for ahead.js to make the same calls)."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def control(self, local_t, fwd, side, hold=""):
        self.calls.append(["c", local_t, fwd, side, hold])
        super().control(local_t, fwd, side, hold)

    def snapshot(self, server_t, fighters, my_id):
        self.calls.append(["s", server_t, json.loads(json.dumps(fighters)), my_id])
        super().snapshot(server_t, fighters, my_id)

    def adjust(self, fighters, local_now, server_seen, rtt, my_id, stats, dt=1 / 60):
        out = super().adjust(fighters, local_now, server_seen, rtt, my_id, stats, dt)
        self.calls.append(["a", json.loads(json.dumps(fighters)), local_now, server_seen, rtt, my_id, list(stats), dt,
                           json.loads(json.dumps(out))])
        return out


RUNNER = r"""
import fs from "fs";
import {FighterAhead} from "./ahead.js";
const calls = JSON.parse(fs.readFileSync(process.argv[2], "utf8")), fa = new FighterAhead();
let worst = 0, n = 0;
for (const c of calls) {
    if (c[0] === "c") fa.control(c[1], c[2], c[3], c[4]);
    else if (c[0] === "s") fa.snapshot(c[1], c[2], c[3]);
    else fa.adjust(c[1], c[2], c[3], c[4], c[5], c[6], c[7]).forEach((f, i) => f.pos.forEach((v, j) => {
        worst = Math.max(worst, Math.abs(v - c[8][i].pos[j])); n++; }));
}
fs.writeFileSync(process.argv[3], JSON.stringify({worst, n}));
"""


def js_twin(calls):
    node = shutil.which("node")
    if not node:
        return None
    tmp = tempfile.mkdtemp(prefix="fighter_js_")
    try:
        web = next(p for p in (os.path.join(os.path.dirname(HERE), "web"), os.path.join(os.path.dirname(HERE), "club-coders", "web"))
                   if os.path.isdir(p))
        shutil.copy(os.path.join(web, "ahead.js"), tmp)
        with open(os.path.join(tmp, "package.json"), "w") as f:
            f.write('{"type": "module"}')
        with open(os.path.join(tmp, "runner.js"), "w") as f:
            f.write(RUNNER)
        with open(os.path.join(tmp, "calls.json"), "w") as f:
            json.dump(calls, f)
        r = subprocess.run([node, "runner.js", "calls.json", "out.json"], cwd=tmp, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr[-500:])
        with open(os.path.join(tmp, "out.json")) as f:
            return json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(seconds=40.0, seed=1, step_key_at=None):
    rng = random.Random(seed)
    random.seed(seed)  # (the computer partner's brain uses the random module: the same fight every run)
    stage = sim.Stage(practice=True)
    ring = stage.add_ring()
    me = ring.add_fighter(sim.default_design("Me"), brain=None, owner="me")
    ring.add_fighter(sim.default_design("Foe", body="robot"), brain=cpu_brains.for_level("easy", None) if step_key_at is None else None,
                     owner="Computer")
    stats = (me.stats["walk"], me.stats["sidestep"])
    script = keys(seed, seconds) if step_key_at is None else [(0.0, 0.0, 0.0, "", None), (step_key_at, 1.0, 0.0, "", None)]
    snaps, ah = interp.Snapshots(interp.FIGHT_SPEC), Recorder()
    in_flight, to_server, truth, rows = [], [], {}, []
    t, tick, last_sent, pressed = 0.0, 0, -1.0, set()
    for _ in range(120):  # (the round's start)
        stage.step()
    while t < seconds:
        if t - last_sent >= 1 / 30 - 1e-9:
            f, s, h, p = key_at(script, t)
            to_server.append((t + LATENCY, (f, s, h, p if p and (t, p) not in pressed else None)))
            ah.control(t, f, s, h)
            last_sent = t
        while in_flight and in_flight[0][0] <= t:
            arrived, m = in_flight.pop(0)
            snaps.push(m, arrived)
            ah.snapshot(m["sm"] / 1000, m["rings"][0]["f"], me.id)
        blended = snaps.sample(t)
        if blended is not None:
            fs = blended["rings"][0]["f"]
            drawn = ah.adjust(fs, t, snaps.clock.server_time(t), 2 * LATENCY, me.id, stats, 1 / 60)
            rows.append((t, {f["id"]: f for f in fs}, {f["id"]: f for f in drawn}))
        while to_server and to_server[0][0] <= t:
            f, s, h, p = to_server.pop(0)[1]
            me.control = (f, s, h)
            if p:
                me.press(p, stage.time)
        stage.step()
        tick += 1
        truth[round(t * 60) + 1] = (me.x, me.y, me.state)
        if tick % 2 == 0:
            msg = {"type": "state", "sm": round((t + 1 / 60) * 1000), "rings": [sim.ring_state(ring, stage.time)]}
            in_flight.append((t + LATENCY + rng.uniform(-JITTER, JITTER), msg))
            in_flight.sort(key=lambda x: x[0])
        t += 1 / 60
    run.calls = ah.calls
    return rows, truth, me.id


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def main():
    rows, truth, me = run()
    eb, ea, jumps, last, walking = [], [], [], None, 0
    for t, blended, drawn in rows[120:]:
        real = truth.get(round((t + LATENCY) * 60))
        if not real:
            continue
        if real[2] in ("walk", "side"):  # (footwork: what's drawn ahead; standing still, both are right)
            walking += 1
            eb.append(math.hypot(blended[me]["pos"][0] - real[0], blended[me]["pos"][1] - real[1]))
            ea.append(math.hypot(drawn[me]["pos"][0] - real[0], drawn[me]["pos"][1] - real[1]))
        if last is not None:  # (what drawing ahead adds to the frame's movement: the blend's own jumps aren't its)
            d = [drawn[me]["pos"][i] - blended[me]["pos"][i] for i in (0, 1)]
            jumps.append(math.hypot(d[0] - last[0], d[1] - last[1]))
        last = [drawn[me]["pos"][i] - blended[me]["pos"][i] for i in (0, 1)]
    check(f"your fighter drawn where your keys are taking it: 95% of frames within {pct(ea, 0.95):.3f} m (blended "
          f"{pct(eb, 0.95):.3f} m), median {pct(ea, 0.5):.3f} against {pct(eb, 0.5):.3f} ({walking} frames walking)",
          pct(ea, 0.95) < 0.75 * pct(eb, 0.95) and pct(ea, 0.5) < 0.5 * pct(eb, 0.5))  # (the 5% furthest: steps into
    # and out of a block or a punch, where the server's word comes first either way)
    walk = sim.build_stats(sim.default_design())["walk"] / 60
    check(f"no jumps: drawing ahead moves it at most {max(jumps):.3f} m more between two frames than the blend "
          f"(walking flat out: {walk:.3f})",
          max(jumps) < 2.5 * walk + 0.01)
    got = js_twin(run.calls[:8000])
    if got is None:
        print("(node isn't here: ahead.js not checked)")
    else:
        check(f"ahead.js draws what ahead.py does ({got['n']} numbers, the largest difference {got['worst']:.1e})",
              got["worst"] < 1e-9 and got["n"] > 1000)
    rows, truth, me = run(seconds=4.0, step_key_at=2.0)
    start = truth[round(1.9 * 60)]
    real = next(k / 60 for k in sorted(truth) if k / 60 >= 2.0 and math.dist(truth[k][:2], start[:2]) > 0.02)
    first_a = next(t for t, b, d in rows if t >= 2.0 and math.dist(d[me]["pos"][:2], start[:2]) > 0.02)
    first_b = next(t for t, b, d in rows if t >= 2.0 and math.dist(b[me]["pos"][:2], start[:2]) > 0.02)
    da, db = (first_a - real) * 1000, (first_b - real) * 1000
    check(f"your key: drawn walking {da:+.0f} ms from when the server's fighter did (blended {db:+.0f} ms)",
          da < -LATENCY * 1000 * 0.5 and db > 60)
    fa = ahead.FighterAhead()
    hit = {"id": 1, "pos": [0.0, 0.0, 0.0], "a": "hit_body"}
    fa.snapshot(1.0, [hit, {"id": 2, "pos": [1.0, 0.0, 0.0], "a": "punch"}], 1)
    fa.control(0.0, 1.0, 0.0, "")
    out = fa.adjust([hit], 0.0, 1.05, 0.08, 1, (2.0, 1.5), 1 / 60)
    check("a fighter being hit is drawn as blended (the server's word)", out[0]["pos"] == hit["pos"])
    print(f"{sum(results)} of {len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
