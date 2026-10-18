"""Tests for the kart brain sandbox and the computer drivers, with no server and no window.

    shared-world-demo\\.venv\\Scripts\\python kart\\brain_test.py      (from the ClubCodersAI folder)

Checks: the worker's views (angle_to, point_ahead); the demo brain loads in the sandbox and laps the Club Circuit
within 60 s of simulated time driving a kart_sim.Race; a brain with `while True: pass` is stopped with "too long"
while step_all keeps taking under 5 ms a tick; a brain returning rubbish, and one that crashes, get a clear
error; each computer level laps, expert faster than medium faster than easy, none of them stuck (never under
2 m/s for 3 s after GO) or into a barrier for long; the three together all finish; view_data's numbers are sane.
Exit code 0 = every check passed. Prints the lap time of every driver.
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import kart_version  # noqa: E402,F401  (puts the engine on the path: one folder up here, two in the public repository)
from engine import wire  # noqa: E402
import brain_worker  # noqa: E402
import cpu_brains  # noqa: E402
import kart_brain  # noqa: E402
import kart_sim  # noqa: E402
import kart_track  # noqa: E402

results = []
laps = []  # (driver, lap time) for the printout


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))


SCHEMA = wire.Schema("kart", kart_sim.SCHEMA_FIELDS)
DEMO = open(os.path.join(HERE, "brains", "demo_brain.py"), encoding="utf-8").read()


def new_race(names=("Kart",), track="club", laps=1):
    race = kart_sim.Race(kart_track.load(track), SCHEMA, laps=laps)
    for i, name in enumerate(names):
        race.add(i, kart_sim.default_design(name))
    race.start()
    return race


def run(race, drivers, seconds, after_tick=None):
    """Step the race with these drivers (id -> fn(kart, race)) until everyone has finished or the time (simulated,
    after GO) is up. Returns a report per kart: worst stretch under 2 m/s (s), ticks at the barrier, max |lat|."""
    report = {i: {"slow": 0, "worst_slow": 0, "wall": 0, "max_lat": 0.0} for i in race.karts}
    limit = race.track.half - kart_sim.KART_HALF
    end = kart_sim.COUNTDOWN_TICKS + int(seconds * 60)
    for _ in range(end):
        inputs = {i: fn(race.karts[i], race) for i, fn in drivers.items()}
        race.step_all(inputs)
        if after_tick:
            after_tick()
        if race.tick > race.go_tick:
            for i, k in race.karts.items():
                if i in race.finish:
                    continue
                r = report[i]
                r["slow"] = r["slow"] + 1 if k["v"] < 2.0 else 0
                r["worst_slow"] = max(r["worst_slow"], r["slow"])
                r["max_lat"] = max(r["max_lat"], abs(k["lat"]))
                if abs(k["lat"]) >= limit - 0.01:
                    r["wall"] += 1
        if race.phase == kart_sim.FLAGS_OVER:
            break
    for r in report.values():
        r["worst_slow"] /= 60
    return report


def lap_time(race, kid):
    return None if kid not in race.finish else (race.finish[kid] - race.go_tick) * kart_sim.STEP


def paced(brain):
    """Wait (a few ms at most) for the brain's answer, so the sandbox keeps pace with a race stepped as fast as the
    computer can rather than at 60 Hz. The real server never waits: tick() is asynchronous."""
    def wait():
        deadline = time.perf_counter() + 0.05
        while brain.pending is not None and brain.replies.empty() and time.perf_counter() < deadline:
            time.sleep(0.0005)
    return wait


# ---------- the worker's views ----------
def test_views():
    me = brain_worker.View({"x": 0.0, "y": 0.0, "heading": 0.0}, {})
    assert abs(me.angle_to(brain_worker.Spot(0, 1)) - 90) < 1e-9, "a point to the left is +90"
    assert abs(me.angle_to(brain_worker.Spot(0, -1)) + 90) < 1e-9, "a point to the right is -90"
    me.heading = 170.0
    assert abs(me.angle_to(brain_worker.Spot(-1, -0.0001)) - 10) < 0.01, "wraps round the back (170 to 180 is +10)"
    assert abs(me.distance_to(brain_worker.Spot(3, 4)) - 5) < 1e-9
    track = brain_worker.TrackView({"name": "t", "length": 100.0, "width": 12.0, "laps": 3,
                                    "ahead": [[i * 5.0, i * 1.0] for i in range(8)]})
    p = track.point_ahead(7.5)
    assert abs(p.x - 7.5) < 1e-9 and abs(p.y - 1.5) < 1e-9, f"interpolates between the 5 m points, got {p.x}, {p.y}"
    assert track.point_ahead(0).x == 0.0 and track.point_ahead(99).x == 35.0, "clamped to the points sent"
    assert track.point_ahead(-3).x == 0.0
    assert track.length == 100.0 and track.laps == 3


check("worker views: angle_to, distance_to, point_ahead", test_views)


# ---------- the sandbox ----------
def test_demo_laps():
    brain, fname = kart_brain.load_brain(DEMO, "demo")
    try:
        auto = kart_brain.Autopilot(brain, fname)
        race = new_race(("Demo",))
        report = run(race, {0: auto}, 60, paced(brain))
        t = lap_time(race, 0)
        assert auto.error is None, f"the demo brain stopped: {auto.error}"
        assert t is not None, f"the demo brain didn't finish a lap in 60 s (lap {race.karts[0]['lap']}, cp {race.karts[0]['cp']})"
        laps.append(("demo brain (sandboxed)", t))
        assert report[0]["worst_slow"] < 3.0, f"the demo brain was stuck for {report[0]['worst_slow']:.1f} s"
        assert auto.ticks > 60 * 10
    finally:
        brain.close()


check("demo brain loads in the sandbox and laps the Club Circuit within 60 s", test_demo_laps)


def stuck(source, killed):
    """Drive a race for 0.6 s of real time with this brain (which never answers): it must be reported as too long,
    and step_all must never wait for it. killed: the host had to kill the process (one line that never ends,
    which the worker's own line counter can't interrupt) rather than the worker stopping the brain itself."""
    brain, fname = kart_brain.load_brain(source, "stuck")
    try:
        auto = kart_brain.Autopilot(brain, fname)
        race = new_race(("Stuck",))
        worst, n = 0.0, 0
        start = time.perf_counter()
        while time.perf_counter() - start < 0.6:  # (real time: the brain is given 0.2 s to answer)
            inp = auto(race.karts[0], race)
            t0 = time.perf_counter()
            race.step_all({0: inp})
            worst = max(worst, time.perf_counter() - t0)
            n += 1
        assert auto.error and "too long" in auto.error, f"expected 'too long', got {auto.error!r}"
        assert worst < 0.005, f"step_all took {1000 * worst:.1f} ms while the brain was stuck"
        assert n > 100, f"only {n} ticks in 0.6 s: the race was held up"
        assert brain.alive() != killed, f"process alive: {brain.alive()} (expected {not killed})"
    finally:
        brain.close()


check("a brain stuck in `while True: pass` is stopped with 'too long' and never stalls the race",
      lambda: stuck("def brain(me, track, rivals):\n    while True:\n        pass\n", killed=False))
check("a brain stuck inside one line is killed with 'too long' and never stalls the race",
      lambda: stuck("import math\n\ndef brain(me, track, rivals):\n    return 1, math.factorial(3000000) % 2\n",
                    killed=True))


def test_rubbish():
    cases = [("def brain(me, track, rivals):\n    return 'zoom'\n", "must return"),
             ("def brain(me, track, rivals):\n    return None\n", "must return"),
             ("def brain(me, track, rivals):\n    return 1, 2, 3, 4\n", "must return"),
             ("def brain(me, track, rivals):\n    return 1, 'left'\n", "must return"),
             ("def brain(me, track, rivals):\n    x = 1\n    return 1, x / 0\n", "line 3: ZeroDivisionError"),
             ("def brain(me, track, rivals):\n    return 1, me.nothing\n", "line 2: AttributeError")]
    for source, expect in cases:
        brain, fname = kart_brain.load_brain(source, "rubbish")
        try:
            auto = kart_brain.Autopilot(brain, fname)
            race = new_race(("Rubbish",))
            for _ in range(60):
                auto(race.karts[0], race)
                paced(brain)()
                if auto.error:
                    break
            assert auto.error and expect in auto.error, f"for {source!r} expected {expect!r}, got {auto.error!r}"
        finally:
            brain.close()
    # and the checks before a process is even started
    for source, expect in [("import os\n", "import math"), ("def think(me):\n    return 0, 0\n", "brain(me, track, rivals)"),
                           ("def brain(me, track, rivals):\n    return open('x')\n", "isn't allowed"),
                           ("def brain(me, track, rivals)\n    return 0, 0\n", "line 1")]:
        try:
            kart_brain.check_source(source, "x.py")
            raise AssertionError(f"{source!r} was accepted")
        except kart_brain.BrainError as e:
            assert expect in str(e), f"for {source!r} expected {expect!r}, got {e}"


check("a brain returning rubbish or crashing gets a clear error with the line", test_rubbish)


def test_clamp_and_drift():
    brain, fname = kart_brain.load_brain("def brain(me, track, rivals):\n    return 5, -7, 'yes'\n", "clamp")
    try:
        auto = kart_brain.Autopilot(brain, fname)
        race = new_race(("Clamp",))
        out = None
        for _ in range(5):
            out = auto(race.karts[0], race)
            paced(brain)()
        assert out == (1.0, -1.0, kart_sim.DRIFT), f"got {out}"
        two = kart_brain.load_brain("def brain(me, track, rivals):\n    return 0.5, 0.25\n", "two")[0]
        try:
            a2 = kart_brain.Autopilot(two, "two")
            for _ in range(5):
                out = a2(race.karts[0], race)
                paced(two)()
            assert out == (0.5, 0.25, 0), f"two values: got {out}"
        finally:
            two.close()
    finally:
        brain.close()


check("throttle and steer are clamped, drift becomes kart_sim.DRIFT, two values are enough", test_clamp_and_drift)


# ---------- the computer drivers ----------
cpu_times = {}


def test_cpu_levels():
    for level in cpu_brains.LEVELS:
        race = new_race((cpu_brains.name_for(level, 1),))
        report = run(race, {0: lambda k, r, lv=level: cpu_brains.drive(lv, k, r)}, 60)
        t = lap_time(race, 0)
        assert t is not None, f"{level} didn't finish a lap in 60 s"
        cpu_times[level] = t
        laps.append((f"cpu {level}", t))
        r = report[0]
        assert r["worst_slow"] < 3.0, f"{level} was under 2 m/s for {r['worst_slow']:.1f} s"
        assert r["wall"] <= 30, f"{level} spent {r['wall']} ticks against the barrier"
    assert cpu_times["expert"] < cpu_times["medium"] < cpu_times["easy"], f"lap times {cpu_times}"


check("each CPU level laps; expert faster than medium faster than easy; none stuck", test_cpu_levels)


def test_cpu_together():
    names = tuple(cpu_brains.name_for(lv, i + 1) for i, lv in enumerate(cpu_brains.LEVELS))
    race = new_race(names)
    drivers = {i: (lambda k, r, lv=lv: cpu_brains.drive(lv, k, r)) for i, lv in enumerate(cpu_brains.LEVELS)}
    report = run(race, drivers, 60)
    for i, lv in enumerate(cpu_brains.LEVELS):
        t = lap_time(race, i)
        assert t is not None, f"{lv} didn't finish the shared race in 60 s"
        laps.append((f"cpu {lv} (3-kart race, grid {i + 1})", t))
        assert report[i]["worst_slow"] < 3.0, f"{lv} was under 2 m/s for {report[i]['worst_slow']:.1f} s"
        assert report[i]["wall"] <= 30, f"{lv} spent {report[i]['wall']} ticks against the barrier"
    assert len(race.finish) == 3


check("the three levels racing together all finish and none is stuck", test_cpu_together)


def test_cpu_oval():
    for level in cpu_brains.LEVELS:
        race = new_race((cpu_brains.name_for(level, 1),), track="oval")
        report = run(race, {0: lambda k, r, lv=level: cpu_brains.drive(lv, k, r)}, 60)
        assert lap_time(race, 0) is not None, f"{level} didn't lap the oval"
        assert report[0]["wall"] <= 30, f"{level} spent {report[0]['wall']} ticks against the oval's barrier"
    assert cpu_brains.name_for("expert", 2) == "Ace 2"


check("the CPU levels lap the Test Oval too", test_cpu_oval)


# ---------- what a brain sees ----------
def test_view_data():
    race = new_race(("A", "B", "C"))
    half = race.track.width / 2
    places = race.places()
    for kid, k in race.karts.items():
        me = kart_brain.view_data(k, race, places.index(kid) + 1)
        assert abs(me["lateral"]) <= half, f"lateral {me['lateral']} outside the track"
        assert abs(me["angle_to_track"]) < 0.5, f"angle_to_track {me['angle_to_track']} on the grid"
        assert me["speed"] == 0.0 and me["lap"] == 0 and me["laps"] == 1 and me["count"] == 3
        assert 1 <= me["place"] <= 3 and me["track_width"] == 12.0 and me["time"] == 0.0
        assert not me["on_oil"] and not me["boosting"] and not me["drifting"] and me["charge"] == 0
        assert 0 < me["next_boost"] <= race.track.length
        assert abs(me["curve_ahead"]) < 10 and me["progress"] < 0, "the grid is a few metres before the line"
        for key in ("name", "x", "y", "heading", "curve_far", "next_boost_lateral"):
            assert key in me, key
        td = kart_brain.track_data(race.track, k["s"], race.laps)
        assert len(td["ahead"]) == 8 and td["name"] == "Club Circuit" and td["laps"] == 1
        x0, y0 = td["ahead"][0]
        assert abs(math.hypot(x0 - k["x"], y0 - k["y"]) - abs(k["lat"])) < 0.05, "the first point is beside me"
        d = math.hypot(td["ahead"][1][0] - x0, td["ahead"][1][1] - y0)
        assert 4.5 < d < 5.5, f"points 5 m apart, got {d}"
    a, b = race.karts[0], race.karts[2]  # grid 0 and grid 2 (two rows, same side, 4 m apart)
    rb = kart_brain.rival_data(b, a, race, 3)
    ra = kart_brain.rival_data(a, b, race, 1)
    assert abs(rb["ahead"] + 4.0) < 0.1 and abs(ra["ahead"] - 4.0) < 0.1, f"ahead {rb['ahead']} / {ra['ahead']}"
    assert rb["name"] == "C" and rb["place"] == 3 and ra["lateral"] == a["lat"]
    # a kart put mid-track, pointing 30 degrees left of the track, on oil
    k = race.karts[1]
    kart_sim.place(race.track, k, 170.0, -2.0)
    k["yaw"] = kart_brain.wrap(race.track.heading(170.0) + 30.0)
    k["slip"], k["boost"], k["v"] = 10, 5, 10.0
    me = kart_brain.view_data(k, race, 2)
    assert abs(me["angle_to_track"] + 30.0) < 0.2, f"angle_to_track {me['angle_to_track']} (expected -30)"
    assert me["on_oil"] and me["boosting"] and me["speed"] == 36.0 and me["lateral"] == -2.0
    assert abs(me["curve_ahead"] - race.track.curvature(170.0, 15)) < 0.1
    assert abs(me["next_boost"] - 65.0) < 0.1 and me["next_boost_lateral"] == 2.5, me["next_boost"]
    # a brain sees those numbers as attributes, and the message is small
    import json
    msg = json.dumps({"me": me, "track": kart_brain.track_data(race.track, 170.0),
                      "rivals": [kart_brain.rival_data(o, k, race, 1) for o in (a, b)]})
    assert len(msg) < 1500, f"tick message is {len(msg)} bytes"


check("view_data, track_data and rival_data numbers are sane", test_view_data)


for name, ok, note in results:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "\n    " + note))
print("lap times (Club Circuit, 1 lap, default kart):")
for who, t in laps:
    print(f"  {who}: {t:.2f} s")
print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
