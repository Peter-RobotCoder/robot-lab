"""Robot Lab's robots drawn ahead (engine/ahead.py) against the server's Bullet robots (CHANGE 166).

    shared-world-demo\\.venv\\Scripts\\python engine\\ahead_test.py      (from the ClubCodersAI folder)

On one clock: Robot Lab's own arena (lab_sim) stepping 60 times a second with two robots, yours and another, each
driven by a script of keys; its snapshots 30 a second (rounded as the server sends them) reaching a window 40 ms
later, give or take 10 (and its keys reaching the server 40 ms later); the window drawing 60 frames a second, as
blended by engine.interp, then drawn ahead. Checks: the other robot drawn nearer where it really is now (95% of
frames) than blended; your robot moving within a frame or two of your key (blended: a round trip and the blend
later); no jumps (the most it moves between two frames, against its speed); a robot knocked on its side drawn as
blended. Exit code 0 = all fine.
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
sys.path.insert(0, next(p for p in (os.path.join(os.path.dirname(HERE), "games", "robotlab"),  # (the public repository)
                                     os.path.join(os.path.dirname(HERE), "shared-world-demo")) if os.path.isdir(p)))
import lab_sim as sim  # noqa: E402
from engine import ahead, interp  # noqa: E402

LATENCY, JITTER = 0.040, 0.010
results = []


def check(name, ok, note=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"\n      {note}" if note else ""))


def keys(seed, seconds):
    rng, out, t = random.Random(seed), [], 0.0
    while t < seconds:
        hold = rng.uniform(0.3, 1.5)
        out.append((t, rng.choice((1.0, 1.0, 0.0, -1.0)), rng.choice((0.0, 0.0, 1.0, -1.0, 0.5))))
        t += hold
    return out


def key_at(script, t):
    got = (0.0, 0.0)
    for t0, th, st in script:
        if t0 > t:
            break
        got = (th, st)
    return got


class Recorder(ahead.RobotsAhead):
    """RobotsAhead, every call written down (for ahead.js to make the same calls)."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def control(self, local_t, throttle, steer):
        self.calls.append(["c", local_t, throttle, steer])
        super().control(local_t, throttle, steer)

    def snapshot(self, server_t, robots):
        self.calls.append(["s", server_t, json.loads(json.dumps(robots))])
        super().snapshot(server_t, robots)

    def adjust(self, robots, local_now, server_seen, rtt, my_id=None, stats=None, dt=1 / 60):
        out = super().adjust(robots, local_now, server_seen, rtt, my_id, stats, dt)
        self.calls.append(["a", json.loads(json.dumps(robots)), local_now, server_seen, rtt, my_id,
                           [[k, list(v)] for k, v in (stats or {}).items()], dt, json.loads(json.dumps(out))])
        return out


RUNNER = r"""
import fs from "fs";
import {RobotsAhead} from "./ahead.js";
const calls = JSON.parse(fs.readFileSync(process.argv[2], "utf8")), ah = new RobotsAhead();
let worst = 0, n = 0;
for (const c of calls) {
    if (c[0] === "c") ah.control(c[1], c[2], c[3]);
    else if (c[0] === "s") ah.snapshot(c[1], c[2]);
    else {
        const out = ah.adjust(c[1], c[2], c[3], c[4], c[5], new Map(c[6]), c[7]);
        out.forEach((r, i) => { for (const k of ["pos", "quat", "wpos", "wquat"]) if (r[k]) r[k].forEach((v, j) => {
            worst = Math.max(worst, Math.abs(v - c[8][i][k][j])); n++; }); });
    }
}
fs.writeFileSync(process.argv[3], JSON.stringify({worst, n}));
"""


def js_twin(calls):
    """ahead.js making the same calls: the largest difference in what it draws (None: no node here)."""
    node = shutil.which("node")
    if not node:
        return None
    tmp = tempfile.mkdtemp(prefix="ahead_js_")
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
    a = sim.Arenas(1, hazards={"saws": False, "spikes": False, "flipper": False, "pit": False, "house_robots": []})
    mine = a.add_robot(sim.default_design(), brain=None, owner="me", start=0)
    other = a.add_robot(sim.default_design("Other"), brain=None, owner="them", start=3)
    stats = {mine.id: (mine.stats["forward_max"], mine.stats["reverse_max"], mine.stats["accel"], mine.stats["turn_rate"])}
    my_keys = keys(seed, seconds) if step_key_at is None else [(0.0, 0.0, 0.0), (step_key_at, 1.0, 0.0)]
    their_keys = keys(seed + 100, seconds)
    snaps, ah = interp.Snapshots(interp.LAB_SPEC), Recorder()
    in_flight, to_server = [], []  # (arrival time, message) / (arrival time, keys)
    true_poses = {}  # server tick -> {id: (x, y)}
    rows, t, tick = [], 0.0, 0
    last_sent = -1.0
    for _ in range(30):
        a.step()
    while t < seconds:
        # the window: its keys (30 a second), what has arrived, the picture
        if t - last_sent >= 1 / 30 - 1e-9:
            th, st = key_at(my_keys, t)
            to_server.append((t + LATENCY, (th, st)))
            ah.control(t, th, st)
            last_sent = t
        while in_flight and in_flight[0][0] <= t:
            arrived, m = in_flight.pop(0)
            m[interp.RECEIVED] = arrived
            snaps.push(m, arrived)
            ah.snapshot(m["sm"] / 1000, m["arenas"][0]["robots"])
        blended = snaps.sample(t)
        if blended is not None:
            robots = blended["arenas"][0]["robots"]
            drawn = ah.adjust(robots, t, snaps.clock.server_time(t), 2 * LATENCY, mine.id, stats, 1 / 60)
            rows.append((t, {r["id"]: r for r in robots}, {r["id"]: r for r in drawn}))
        # the server: the keys that have arrived, a step, a snapshot every other step
        while to_server and to_server[0][0] <= t:
            mine.control = (*to_server.pop(0)[1], False)
        other.control = (*key_at(their_keys, t), False)
        a.step()
        tick += 1
        true_poses[round(t * 60) + 1] = {r.id: (r.pos.x, r.pos.y, r.pos.z) for r in (mine, other)}  # (after the step)
        if tick % 2 == 0:
            msg = {"type": "state", "sm": round((t + 1 / 60) * 1000), "arenas": [{"i": 0, "robots": [
                {"id": r.id, "pos": [round(v, 2) for v in r.pos], "quat": [round(v, 3) for v in tuple(r.np.getQuat())],
                 "wpos": [round(v, 2) for v in r.weapon_np.getPos()], "wquat": [round(v, 3) for v in tuple(r.weapon_np.getQuat())],
                 "speed": round(r.speed, 2), "ko": False} for r in (mine, other)]}]}
            in_flight.append((t + LATENCY + rng.uniform(-JITTER, JITTER), msg))
            in_flight.sort(key=lambda x: x[0])
        t += 1 / 60
    run.calls = ah.calls
    return rows, true_poses, mine.id, other.id


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def errors(rows, truth, rid, ahead_s):
    """How far each frame's drawn robot is from where it really is ahead_s after the frame (blended, drawn ahead)."""
    eb, ea, jumps, last = [], [], [], None
    for t, blended, drawn in rows[120:]:
        real = truth.get(round((t + ahead_s) * 60))
        if not real or rid not in drawn:
            continue
        rx, ry, _ = real[rid]
        eb.append(math.hypot(blended[rid]["pos"][0] - rx, blended[rid]["pos"][1] - ry))
        ea.append(math.hypot(drawn[rid]["pos"][0] - rx, drawn[rid]["pos"][1] - ry))
        if last is not None:
            jumps.append(math.hypot(drawn[rid]["pos"][0] - last[0], drawn[rid]["pos"][1] - last[1]))
        last = drawn[rid]["pos"]
    return eb, ea, jumps


def main():
    rows, truth, me, them = run()
    # (the moment a key pressed now takes effect on the server: what the picture is drawn for, so a ram looks as it is)
    eb, ea, jumps = errors(rows, truth, them, LATENCY)
    check(f"the other robot drawn where it really is when your key arrives: 95% of frames within {pct(ea, 0.95):.2f} m "
          f"(blended: {pct(eb, 0.95):.2f} m); median {pct(ea, 0.5):.3f} against {pct(eb, 0.5):.3f}",
          pct(ea, 0.95) < 0.5 * pct(eb, 0.95))
    fastest = sim.build_stats(sim.default_design())["forward_max"] / 60
    check(f"no jumps: the other robot moves at most {max(jumps):.3f} m between two frames (its top speed is "
          f"{fastest:.3f} m a frame)", max(jumps) < 2.0 * fastest + 0.02)
    eb, ea, jumps = errors(rows, truth, me, LATENCY)
    check(f"your robot drawn where your keys are taking it: 95% of frames within {pct(ea, 0.95):.2f} m (blended: "
          f"{pct(eb, 0.95):.2f} m); median {pct(ea, 0.5):.3f} against {pct(eb, 0.5):.3f}",
          pct(ea, 0.95) < 0.5 * pct(eb, 0.95))
    check(f"...and no jumps: at most {max(jumps):.3f} m between two frames", max(jumps) < 2.0 * fastest + 0.02)
    got = js_twin(run.calls[:6000])
    if got is None:
        print("(node isn't here: ahead.js not checked)")
    else:
        check(f"ahead.js draws what ahead.py does ({got['n']} numbers, the largest difference {got['worst']:.1e})",
              got["worst"] < 1e-9)
    # your key from standing still: when it's drawn moving (3 cm) against when the server's robot moved 3 cm
    rows, truth, me, them = run(seconds=4.0, step_key_at=2.0)
    start = truth[round(1.9 * 60)][me]
    real = next(k / 60 for k in sorted(truth) if k / 60 >= 2.0 and math.dist(truth[k][me][:2], start[:2]) > 0.03)
    first_a = next((t for t, b, d in rows if t >= 2.0 and math.dist(d[me]["pos"][:2], start[:2]) > 0.03), None)
    first_b = next((t for t, b, d in rows if t >= 2.0 and math.dist(b[me]["pos"][:2], start[:2]) > 0.03), None)
    da, db = (first_a - real) * 1000, (first_b - real) * 1000
    check(f"your key: drawn moving {da:+.0f} ms from when the server's robot moved (blended {db:+.0f} ms; the key "
          f"reaches the server {LATENCY * 1000:.0f} ms after it's pressed)", da < -LATENCY * 1000 * 0.5 and db > 60)
    # on its side: drawn as blended
    rows, truth, me, them = run(seconds=3.0)
    ah = ahead.RobotsAhead()
    side = {"id": 9, "pos": [0.0, 0.0, 0.3], "quat": [0.7071, 0.7071, 0.0, 0.0], "speed": 3.0, "ko": False}
    ah.snapshot(1.0, [side])
    ah.snapshot(1.0333, [dict(side, pos=[0.1, 0.0, 0.3])])
    out = ah.adjust([side], 0.0, 1.05, 0.08, None, None, 1 / 60)
    check("a robot on its side is drawn as blended (Bullet's word: it isn't carried on)", out[0]["pos"] == side["pos"])
    print(f"{sum(results)} of {len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
