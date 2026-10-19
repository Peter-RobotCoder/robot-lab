"""Checks for engine.interp (blending between snapshots) and engine.net's pretend network.

    python engine/interp_test.py

No window and no server: the snapshots are made up. Exit code 0 = all fine.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import interp, net  # noqa: E402

results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))


def robot_msg(i, t_ms, pos_x, saw=0.0):
    return {"type": "state", "sm": t_ms, "arenas": [{"i": 0, "robots": [
        {"id": 1, "pos": [pos_x, 0, 0], "quat": [1, 0, 0, 0], "wpos": [pos_x, 1, 0], "wquat": [1, 0, 0, 0],
         "speed": pos_x, "hp": 100 - i}], "hz": {"saws": [saw], "ff": [1, 0, 0, 0]}}]}


def steady_stream():
    """Snapshots every 33 ms: the picture is drawn two snapshots back and moves smoothly between them."""
    s = interp.Snapshots(interp.LAB_SPEC)
    t0 = 1000.0
    for i in range(10):
        s.push(robot_msg(i, i * 33, float(i), i * 0.1), local_t=t0 + i * 0.033)
    now = t0 + 9 * 0.033
    m = s.sample(now)
    x = m["arenas"][0]["robots"][0]["pos"][0]
    assert 6.5 < x < 7.5, x                      # 67 ms behind the newest (snapshot 9) is about snapshot 7
    assert abs(m["arenas"][0]["hz"]["saws"][0] - x * 0.1) < 1e-6
    assert m["arenas"][0]["robots"][0]["hp"] == 100 - 7  # (numbers not in the spec come from the later of the pair)
    m2 = s.sample(now + 0.010)
    x2 = m2["arenas"][0]["robots"][0]["pos"][0]
    assert x < x2 < x + 0.5, (x, x2)             # 10 ms later it has moved on by about 10 ms' worth (0.3 m)
    assert s.report()["stalls"] == 0


def stall_then_burst():
    """A 150 ms stall: the picture holds, then carries on without a jump; the delay grows, then shrinks back."""
    s = interp.Snapshots(interp.LAB_SPEC)
    t0 = 1000.0
    for i in range(6):
        s.push(robot_msg(i, i * 33, float(i)), local_t=t0 + i * 0.033)
    base = s.delay
    now = t0 + 5 * 0.033
    xs = []
    for f in range(12):  # 200 ms of frames with nothing arriving
        m = s.sample(now + f / 60)
        xs.append(m["arenas"][0]["robots"][0]["pos"][0])
    assert all(b >= a for a, b in zip(xs, xs[1:])), xs  # never goes backwards
    assert xs[-1] <= 5.0 + 3.1, xs                       # ...carries on at most 100 ms (3 units) past the newest
    assert xs[-1] == xs[-2], xs                          # ...then holds
    # the delay grew by one snapshot, once (and eases back at 20 ms a second while the arrivals say it's not needed)
    assert base + 1 / 30 - 0.006 < s.delay <= base + 1 / 30 + 1e-9, (s.delay, base)
    for i in range(6, 12):  # the held-up snapshots arrive together
        s.push(robot_msg(i, i * 33, float(i)), local_t=now + 0.2)
    assert s.report()["stalls"] == 1
    m = s.sample(now + 0.2 + 1 / 60)
    assert m["arenas"][0]["robots"][0]["pos"][0] >= xs[-1] - 1e-9
    d = s.delay
    for f in range(600):  # ten quiet seconds: the delay creeps back down
        s.push(robot_msg(12 + f, (12 + f) * 33, 12.0 + f), local_t=now + 0.3 + f * 0.033)
        s.sample(now + 0.3 + f * 0.033)
    assert s.delay < d


def clock_follows_fast_packets():
    c = interp.ServerClock()
    c.note(10.0, 0.0)       # offset 10
    c.note(10.033, 0.050)   # a slow one: offset 9.983, ignored (slewed down only very slowly)
    assert abs(c.server_time(0.050) - 10.050) < 0.005
    c.note(10.1, 0.090)     # a fast one: offset 10.01, followed at once
    assert abs(c.offset - 10.01) < 1e-9


def fight_blend():
    s = interp.Snapshots(interp.FIGHT_SPEC)
    msgs = [{"sm": i * 33, "rings": [{"i": 0, "f": [{"id": 3, "pos": [i, 0, 0], "h": 350 + i * 10,
                                                      "a": "punch" if i < 3 else "kick", "k": i * 0.2}]}]}
            for i in range(6)]
    for i, m in enumerate(msgs):
        s.push(m, local_t=i * 0.033)
    delay = s.delay  # (the server clock's offset is 0 here: sm and the local times match)
    f = s.sample(delay + 0.050)["rings"][0]["f"][0]  # between snapshots 1 and 2: the same move
    assert 0.2 < f["k"] < 0.4 and 0 <= (f["h"] - 360) % 360 < 10, f
    f = s.sample(delay + 0.080)["rings"][0]["f"][0]  # between 2 and 3: the move changed
    assert f["k"] == msgs[3]["rings"][0]["f"][0]["k"], f   # (k not blended across two different moves)


def quaternions_and_angles():
    q = interp.slerp([1, 0, 0, 0], [0, 0, 0, 1], 0.5)
    assert abs(q[0] - 0.7071) < 0.001 and abs(q[3] - 0.7071) < 0.001
    q = interp.slerp([1, 0, 0, 0], [-1, 0, 0, 0], 0.5)  # the same rotation written twice: no spin
    assert abs(abs(q[0]) - 1) < 1e-6
    assert interp.angle(350, 10, 0.5) % 360 == 0
    assert interp.posquat([0, 0, 0, 1, 0, 0, 0], [2, 0, 0, 1, 0, 0, 0], 0.5)[0] == 1


def pretend_network():
    assert net.lag_settings("60,15,0.02") == (0.06, 0.015, 0.02)
    assert net.lag_settings("") is None and net.lag_settings("abc") is None
    got = []
    d = net.Delay(0.03, 0.0, 0.0, got.append)
    t0 = time.perf_counter()
    for i in range(5):
        d.put(i)
    time.sleep(0.08)
    assert got == [0, 1, 2, 3, 4], got
    assert time.perf_counter() - t0 >= 0.03


def perf_line():
    line = interp.perf_line("Violet", {"Violet": {"tier": "low", "fps": 48, "ping": 35, "ctrl": 90, "stalls": 2}})
    assert "Low graphics" in line and "48 fps" in line and "key delay 90 ms" in line and "2 network stalls" in line
    assert interp.perf_line("Sam", {}) == "Sam's window: no report yet"



# ---------- (CHANGE 175) interp.js, the page's port, on the same arrivals ----------
import os
import shutil
import subprocess
import tempfile
import json
import random

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = """
import {Snapshots} from "./interp.js";
import fs from "fs";
const calls = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const s = new Snapshots();
const out = [];
for (const c of calls) {
    if (c.push) s.push({sm: c.sm}, c.t * 1000);
    else { const p = s.pair(c.t * 1000); out.push([s.tRender, s.delay, p ? p.f : null, p ? !!p.extrapolating : null, s.underruns, s.stalls]); }
}
fs.writeFileSync(process.argv[3], JSON.stringify(out));
"""


def arrivals(seed=3, seconds=40.0):
    """Snapshots every 1/30 s from a server clock, each arriving after a base lag plus jitter, with a stall and a
    burst (everything behind it) every ten seconds; frames every 1/60 s between them. Returns the calls, in time
    order: {"push", "sm", "t"} and {"t"} for a frame."""
    rng = random.Random(seed)
    calls, t_send, n = [], 0.0, 0
    stall_until = 0.0
    while t_send < seconds:
        lag = 0.04 + abs(rng.gauss(0, 0.012))
        if int(t_send) % 10 == 7 and rng.random() < 0.05 and stall_until < t_send:
            stall_until = t_send + 0.25  # (a Wi-Fi stall: this one and the next few arrive together at its end)
        at = max(t_send + lag, stall_until + 0.001 * (n % 7)) if stall_until > t_send else t_send + lag
        calls.append({"push": True, "sm": round(1000 * (100.0 + t_send)), "t": 1000.0 + at})
        t_send += 1 / 30
        n += 1
    frames = [{"t": 1000.0 + k / 60} for k in range(int(seconds * 60))]
    calls = sorted(calls + frames, key=lambda c: (c["t"], 0 if c.get("push") else 1))
    return calls


def js_parity():
    """interp.js draws the same moments with the same delay as interp.py, to a microsecond, over 40 s of jittery
    arrivals with stalls."""
    node = shutil.which("node")
    if not node:
        results.append(("interp.js matches interp.py", True, "(node isn't here: not checked)"))
        return
    calls = arrivals()
    s = interp.Snapshots()
    mine = []
    for c in calls:
        if c.get("push"):
            s.push({"sm": c["sm"]}, local_t=c["t"])
        else:
            s.sample(c["t"])
            mine.append([s.t_render, s.delay, s.underruns, s.stalls])
    tmp = tempfile.mkdtemp(prefix="interp_js_")
    try:
        web = next(p for p in (os.path.join(os.path.dirname(HERE), "web"), os.path.join(os.path.dirname(HERE), "club-coders", "web"))
                   if os.path.isdir(p))
        shutil.copy(os.path.join(web, "interp.js"), tmp)
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
            theirs = json.load(f)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assert len(theirs) == len(mine), (len(theirs), len(mine))
    worst = 0.0
    for (tr, d, u, st), (tr2, d2, _f, _x, u2, st2) in zip(mine, theirs):
        assert u == u2 and st == st2, ("underruns/stalls differ", u, u2, st, st2)
        if tr is not None and tr2 is not None:
            worst = max(worst, abs(tr - tr2), abs(d - d2))
    assert worst < 1e-6, f"the drawn moment or the delay differ by {worst * 1000:.3f} ms"
    assert s.underruns >= 1 and s.delay > s.base_delay, (s.underruns, s.delay)  # (the stalls were felt and absorbed)
    results.append(("interp.js matches interp.py", True, f"{len(mine)} frames, {s.underruns} underruns, delay {s.delay * 1000:.0f} ms"))


check("steady stream blends between snapshots", steady_stream)
check("a stall holds the picture and the delay adapts", stall_then_burst)
check("the server clock follows fast packets", clock_follows_fast_packets)
check("Fight Lab blend", fight_blend)
check("quaternions and angles", quaternions_and_angles)
check("pretend network keeps order and delays", pretend_network)
check("the teacher's report line", perf_line)
js_parity()  # (CHANGE 175: interp.js, the page's port, line for line)

ok = True
for name, passed, note in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name}  {note}")
    ok = ok and passed
print("All fine." if ok else "Something failed.")
sys.exit(0 if ok else 1)
