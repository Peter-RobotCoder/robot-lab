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
    assert xs[-1] <= 5.0 + 1.6, xs                       # ...carries on at most 50 ms (1.5 units) past the newest
    assert xs[-1] == xs[-2], xs                          # ...then holds
    assert abs(s.delay - (base + 1 / 30)) < 0.002, s.delay  # the delay grew by one snapshot, once
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


check("steady stream blends between snapshots", steady_stream)
check("a stall holds the picture and the delay adapts", stall_then_burst)
check("the server clock follows fast packets", clock_follows_fast_packets)
check("Fight Lab blend", fight_blend)
check("quaternions and angles", quaternions_and_angles)
check("pretend network keeps order and delays", pretend_network)
check("the teacher's report line", perf_line)

ok = True
for name, passed, note in results:
    print(f"{'PASS' if passed else 'FAIL'}  {name}  {note}")
    ok = ok and passed
print("All fine." if ok else "Something failed.")
sys.exit(0 if ok else 1)
