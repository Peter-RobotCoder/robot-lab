"""Quick check that Kart Lab works (run after every change).

    python kart_test.py

1. every Python file compiles
2. the track answers consistently (a point put at s, lateral is found there again; the grid is on the track)
3. the kart: deterministic, held by the barriers, drift pays out a boost, oil slides, the wire rounding is stable
4. prediction without a network: a window and a server stepping the same kart agree exactly through 90 ms of
   delay, and a bump from the server is corrected once and absorbed
5. the server: two windows log in, drive with binary inputs at 60 Hz, get 30 snapshots a second with their acks
6. the window draws (offline, offscreen) and takes a screenshot; and logs in to the test server and draws
Exit code 0 = all fine.
"""
import json
import math
import os
import py_compile
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import kart_version  # noqa: E402
sys.path.insert(0, kart_version.ENGINE_HOME)
from engine import predict, wire  # noqa: E402
import kart_sim as sim  # noqa: E402
import kart_track  # noqa: E402

PY = sys.executable
TMP = tempfile.mkdtemp(prefix="kartlab_test_")
os.environ["KARTLAB_DATA"] = TMP  # (the teaching layer, profiles and evidence: here, never in the real data folder)
results = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, f"{time.time() - t0:.0f} s"))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {str(e)[-400:]}"))


def compile_all():
    for name in os.listdir(HERE):
        if name.endswith(".py"):
            py_compile.compile(os.path.join(HERE, name), doraise=True)
    for name in os.listdir(os.path.join(HERE, "brains")):
        if name.endswith(".py"):
            py_compile.compile(os.path.join(HERE, "brains", name), doraise=True)


def track_answers():
    for name in kart_track.TRACKS:
        t = kart_track.load(name)
        assert t.length > 100 and t.n > 50, (name, t.length)
        for s in [x * t.length / 37 for x in range(37)]:
            for lat in (-t.half + 1, 0.0, 2.5, t.half - 1):
                x, y, _ = t.point(s, lat)
                seg, s2, lat2 = t.locate(x, y, None)
                ds = (s2 - s + t.length / 2) % t.length - t.length / 2
                # the place found is where the point is (inside a hairpin the nearest bit of centre line can be a
                # different one from the one the point was made from, so near the edges that is all we ask)
                xx, yy, _ = t.point(s2, lat2)
                assert math.hypot(xx - x, yy - y) < 0.5, (name, s, lat, s2, lat2)
                if abs(lat) <= 2.5:
                    assert abs(ds) < 1.5 and abs(lat2 - lat) < 0.35, (name, s, lat, s2, lat2)
                seg3, s3, lat3 = t.locate(x, y, seg)  # with the hint: the same answer (s = 0 is also s = length)
                ds = (s3 - s2 + t.length / 2) % t.length - t.length / 2
                assert abs(ds) < 1e-6 and abs(lat3 - lat2) < 0.05, (name, s, s2, s3, lat2, lat3)
        for place in range(8):  # the grid is on the track, behind the line, two abreast
            s, lat = t.grid(place)
            assert t.length - 40 < s < t.length and abs(lat) < t.half - 1
        gates = [t.gate_zone(g + 0.5) for g in t.gate_s]
        assert gates == list(range(kart_track.GATES)), gates
        # progress orders a lap: a kart just over the line is ahead of one just behind it
        assert t.progress(0, 1, 1.0) > t.progress(0, 0, t.length - 1.0)
        assert t.progress(1, 1, 1.0) > t.progress(0, 7, t.length - 1.0)
    t = kart_track.load("club")
    assert t.curvature(t.length * 0.1, 15) != 0  # (there is a bend somewhere)


def follow(track, k):
    look = 6 + 0.45 * k["v"]
    tx, ty, _ = track.point(k["s"] + look)
    want = math.degrees(math.atan2(ty - k["y"], tx - k["x"]))
    err = (want - k["yaw"] + 180) % 360 - 180
    curve = abs(track.curvature(k["s"], 18))
    return (1.0 if curve < 25 or k["v"] < 12 else 0.2, max(-1.0, min(1.0, err / 25.0)), 0)


def kart_physics():
    schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
    t = kart_track.load("club")
    # deterministic: two races with the same inputs end identical
    r1, r2 = sim.Race(t, schema), sim.Race(t, schema)
    for r in (r1, r2):
        for i in range(3):
            r.add(i, sim.default_design(f"K{i}"))
        r.start()
        for _ in range(60 * 20):
            r.step_all({i: follow(t, r.karts[i]) for i in r.karts})
    assert r1.karts == r2.karts
    assert all(k["lap"] >= 0 and k["cp"] > 0 for k in r1.karts.values()), r1.karts  # (they got going)
    # the barriers: a kart driven hard into the wall stays on the track
    r = sim.Race(t, schema)
    r.add(0, sim.default_design("Wall"))
    r.start()
    for _ in range(sim.COUNTDOWN_TICKS + 1):
        r.step_all({0: (0.0, 0.0, 0)})
    for _ in range(300):
        r.step_all({0: (1.0, 1.0, 0)})  # full throttle, full lock
        k = r.karts[0]  # (CHANGE 177: held at the barrier, past the kerb and the gravel, never beyond it)
        assert abs(k["lat"]) <= t.barrier(k["seg"], 1 if k["lat"] > 0 else -1) - sim.KART_HALF + 1e-6, k["lat"]
    # drift: hold DRIFT round a long turn and a boost pays out when it ends
    st = sim.stats_of(sim.default_design("D"))
    k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
    sim.place(t, k, 10.0, 0.0)
    k["v"] = 15.0
    for _ in range(80):
        k = sim.step(k, (1.0, 1.0, sim.DRIFT), sim.STEP, t, st)
        k["lat"] = 0.0  # (keep it off the wall: it's the charge we're testing)
        k["x"], k["y"], _ = t.point(k["s"], 0.0)
    assert k["charge"] >= sim.MINI_TURBO and k["flags"] & sim.FLAG_DRIFT_L, (k["charge"], k["flags"])
    k = sim.step(k, (1.0, 0.0, 0), sim.STEP, t, st)
    assert k["boost"] >= sim.MINI_BOOST - 1 and k["charge"] == 0, k["boost"]
    # oil: over a patch the slide begins
    s_oil, lat_oil = t.oil[0]
    k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
    sim.place(t, k, s_oil - 1.0, lat_oil)
    k = sim.step(k, (1.0, 0.0, 0), sim.STEP, t, st)
    assert k["slip"] > 0
    # (CHANGE 156) let go, a kart rolls to a stop and stays there (the rounding to the wire once held it at 0.81 m/s)
    k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
    sim.place(t, k, 10.0, 0.0)
    for _ in range(120):
        k = sim.step(k, (1.0, 0.0, 0), sim.STEP, t, st)
        k.update(schema.quantise(k))
    for _ in range(60 * 10):
        k = sim.step(k, (0.0, 0.0, 0), sim.STEP, t, st)
        k.update(schema.quantise(k))
    still = (k["x"], k["y"])
    for _ in range(60):
        k = sim.step(k, (0.0, 0.0, 0), sim.STEP, t, st)
        k.update(schema.quantise(k))
    assert k["v"] == 0 and (k["x"], k["y"]) == still, (k["v"], still, k["x"], k["y"])
    # (CHANGE 157) the state carries the driver's steering, for every window's front wheels
    k = sim.step(k, (0.0, -0.75, 0), sim.STEP, t, st)
    assert schema.quantise(k)["steer"] == -0.75, k["steer"]
    # the wire rounding is stable: rounding a rounded state changes nothing (both ends can agree)
    q = schema.quantise(r1.karts[0])
    assert schema.quantise(q) == q
    assert schema.unpack(schema.pack(q)) == q


def prediction_no_network():
    """A pretend window and server with 90 ms each way, the same step both sides."""
    schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
    t = kart_track.load("straight")
    design = sim.default_design("Me")
    st = sim.stats_of(design)
    server = sim.Race(t, schema)
    server.add(0, design)
    server.start()
    server.go_tick = server.tick  # (no countdown)
    queue = predict.ServerInputQueue(idle=(0.0, 0.0, 0))

    def step(state, inp, dt):
        n = sim.step(state, inp, dt, t, st)
        n.update(schema.quantise(n))
        return n
    client = predict.Predictor(step, dict(server.karts[0]), ignore=0.05)
    DELAY = 5  # ticks each way (83 ms)
    to_server, to_client = [], []  # (deliver at tick, payload)
    errors, worst_after = [], 0.0
    for tick in range(600):
        inp = (1.0, 0.3 * math.sin(tick / 40), sim.DRIFT if 200 < tick < 260 else 0)
        inp = wire.quantise_input(*inp)
        seq = client.apply(inp, sim.STEP)
        to_server.append((tick + DELAY, (seq, inp, client.log.previous(2))))
        while to_server and to_server[0][0] <= tick:
            _, (s, i, prev) = to_server.pop(0)
            queue.push(s, i, prev)
        applied = queue.pop_for_tick()
        server.step_all({0: applied})
        if tick == 400:  # the server knows something the window doesn't: a bump
            server.karts[0]["x"] += 0.8
            server.karts[0]["v"] -= 2.0
            server.karts[0].update(schema.quantise(server.karts[0]))
        if tick % 2 == 0 and queue.applied is not None:
            to_client.append((tick + DELAY, (dict(server.karts[0]), queue.applied)))
        while to_client and to_client[0][0] <= tick:
            _, (state, ack) = to_client.pop(0)
            err = client.correct(state, ack, sim.STEP, sim.compare)
            errors.append((tick, err))
            if tick > 420:
                worst_after = max(worst_after, err)
    before = [e for tk, e in errors if tk < 400 + DELAY]
    assert before and max(before) < 0.05, f"the window and server disagreed with no reason: {max(before):.3f}"
    assert client.corrections >= 1, "the bump was never corrected"
    assert client.corrections <= 3, f"corrected {client.corrections} times for one bump"
    assert worst_after < 0.05, f"after the bump the window kept disagreeing: {worst_after:.3f}"


def beside_the_road():
    """(CHANGE 176 to 182) The kerb slows a kart a little and the gravel a lot (and holds one without the momentum
    to get out), the barrier is past the gravel; a kart hit from behind is pushed on; the handbrake slides the back
    round, the clutch dropped spins the back wheels (a burnout, a donut with the wheel turned); the tyres wear with
    the laps and a pit stop puts new ones on; the pit lane (open) takes a kart in down its entry, holds it to the
    pit speed and mends it stopped in its own bay, and (closed) lets nobody in; the outer item boxes are taken by a
    kart along the barrier; the teacher's fix mends a kart at once; and the browser's track has the same traps."""
    import kart_items
    schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
    t = kart_track.load("club")
    st = sim.stats_of(sim.default_design("D"))

    def run(k, inp, n, wear=0.0, damage=True):
        for _ in range(n):
            k = sim.step(k, inp, sim.STEP, t, st, damage, wear)
            k.update(schema.quantise(k))
        return k

    def start(s, lat, v, yaw_off=0.0):
        k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
        sim.place(t, k, s, lat)
        k["yaw"], k["v"] = t.heading(s) + yaw_off, v
        return k
    # a straight bit of the club track with gravel on the right: the start straight's end before the first bend
    seg = max(range(t.n), key=lambda i: t.gravel[-1][i])
    s_g = t.s[seg]
    assert t.gravel[-1][seg] > 3.0 and t.barrier(seg, -1) > t.half + kart_track.KERB + 3.0, (seg, t.gravel[-1][seg])
    # the kerb: a kart straight along the road's edge, its outer wheels over it, loses a little speed; one on the road none
    on = run(start(20.0, 0.0, 20.0), (0.0, 0.0, 0), 60)
    kerb = run(start(20.0, -(t.half - 0.2), 20.0), (0.0, 0.0, 0), 60)
    assert kerb["v"] < on["v"] - 0.3 and kerb["v"] > on["v"] - 4.5, (on["v"], kerb["v"])  # (a quarter a second: a rumble)
    assert sim.surface(t, kerb["seg"], kerb["s"], kerb["lat"]) == "kerb"
    # the gravel: a kart steered into it from the road stops well short of the barrier, then crawls; a kart along
    # the old barrier line goes on over the kerb (nothing holds it there now)
    k = start(s_g - 25.0, 0.0, 22.0)
    for i in range(240):
        k = run(k, (1.0, -1.0 if i < 50 else 0.0, 0), 1)
    assert sim.surface(t, k["seg"], k["s"], k["lat"]) == "gravel" and abs(k["v"]) < 2.0, (k["lat"], k["v"])
    assert abs(k["lat"]) > t.half + kart_track.KERB + 1.0, k["lat"]  # (well into the trap)
    held = run(dict(k), (1.0, 0.0, 0), 120)
    assert abs(held["v"]) < 1.5, held["v"]  # (full throttle: a crawl)
    # the barrier is where the gravel ends: a kart heading across the trap is held there and damaged
    k = start(s_g, 0.0, 16.0, -70)
    k = run(k, (1.0, 0.0, 0), 120)
    assert abs(abs(k["lat"]) - (t.barrier(k["seg"], -1) - sim.KART_HALF)) < 0.6 and k["dw"] > 0, (k["lat"], k["dw"])
    # a bump from behind pushes the kart in front on and slows the one behind
    r = sim.Race(t, schema)
    r.add(0, sim.default_design("A"))
    r.add(1, sim.default_design("B"))
    r.phase, r.go_tick = sim.FLAGS_RACE, -1
    a, b = r.karts[0], r.karts[1]
    sim.place(t, a, 10.0, 0.0)
    sim.place(t, b, 13.0, 0.0)
    a["v"], b["v"] = 20.0, 10.0
    pushed = False
    for _ in range(30):
        r.step_all({0: (1.0, 0.0, 0), 1: (0.5, 0.0, 0)})
        if r.bumps:
            pushed = True
            assert r.karts[1]["v"] > 13.0 and r.karts[0]["v"] < 18.0, (r.karts[0]["v"], r.karts[1]["v"])
            break
    assert pushed
    # the handbrake: the back steps round, the kart slows; the clutch dropped: wheelspin, slow away, a donut steering
    hb = run(start(10.0, 0.0, 20.0), (1.0, 1.0, sim.HANDBRAKE), 45)
    assert hb["flags"] & sim.FLAG_HANDBRAKE and hb["flags"] & sim.FLAG_BRAKING and hb["v"] < 12 and abs(hb["yaw"] - t.heading(10.0)) > 40, hb
    burn = run(start(10.0, 0.0, 0.0), (1.0, 0.0, sim.LAUNCH), 90)
    plain = run(start(10.0, 0.0, 0.0), (1.0, 0.0, 0), 90)
    assert burn["flags"] & sim.FLAG_WHEELSPIN and burn["v"] < plain["v"] * 0.6, (burn["v"], plain["v"])
    donut = run(start(10.0, 0.0, 0.0), (1.0, 1.0, sim.LAUNCH), 60)
    assert abs((donut["yaw"] - t.heading(10.0) + 180) % 360 - 180) > 90, donut["yaw"]
    gone = run(start(10.0, 0.0, 12.0), (1.0, 0.0, sim.LAUNCH), 30)
    assert not gone["flags"] & sim.FLAG_WHEELSPIN  # (already rolling: the clutch does nothing)
    # tyre wear: a set that lasts 2 laps is half worn after one lap flat out, the kart slower on it; the PIT box renews
    wear = sim.wear_rate(t, 2)
    k = start(5.0, 0.0, st["top"])
    began = k["s"]
    while k["s"] - began < t.length - 5.0 if k["s"] >= began else k["s"] + t.length - began < t.length - 5.0:
        k = run(k, follow(t, k), 1, wear)  # (a lap, driven round the track)
    assert 0.35 < k["tyre"] < 0.65, k["tyre"]
    fresh = run(start(100.0, 0.0, 10.0), (1.0, 1.0, 0), 60)
    worn = start(100.0, 0.0, 10.0)
    worn["tyre"] = 1.0
    worn = run(worn, (1.0, 1.0, 0), 60)
    assert abs(worn["u"]) > abs(fresh["u"]) or worn["v"] < fresh["v"], (fresh, worn)  # (less grip: more slide, less pace)
    s0, s1, side = t.pit_box
    k = start(s0 + 1.0, side * (t.half - 1.6), 4.0)
    k["tyre"] = 0.9
    k = run(k, (0.3, 0.0, 0), 120)
    assert k["tyre"] < 0.3, k["tyre"]
    # the pit lane: open, a kart along the right edge over the entry is taken in, limited to the pit speed, mended
    # and given new tyres stopped in its own bay; closed, the same kart is held on the road
    for mode, expect in (("lane", "lane"), ("box", "kerb")):
        t.set_pits(mode)
        k = start(t.lane[0] - 6.0, -(t.half - 0.6), 14.0)
        for i in range(100):
            k = run(k, (1.0, -0.5 if i < 25 else 0.0, 0), 1)
        assert sim.surface(t, k["seg"], k["s"], k["lat"]) == expect, (mode, k["lat"], sim.surface(t, k["seg"], k["s"], k["lat"]))
        if mode == "lane":
            assert k["v"] <= sim.PIT_SPEED + 0.01, k["v"]
    t.set_pits("lane")
    bs0, bs1, lo, hi = t.bay(0)
    k = start((bs0 + bs1) / 2, -(lo + hi) / 2, 0.0)
    k["id"], k["tyre"], k["dfl"] = 0, 0.8, 6000
    assert t.in_bay(0, k["s"], k["lat"]) and not t.in_bay(1, k["s"], k["lat"])
    k = run(k, (0.0, 0.0, 0), 180)
    assert k["tyre"] == 0.0 and k["dfl"] == 0, (k["tyre"], k["dfl"])
    t.set_pits("box")
    # the outer item boxes: a kart along the barrier line takes one (it got nothing: the box's reach was a circle)
    r = sim.Race(t, schema)
    r.items = kart_items.Items(r, seed=3)
    r.add(0, sim.default_design("K"))
    r.phase, r.go_tick = sim.FLAGS_RACE, -1
    bs, blat = t.box_spots()[3]
    sim.place(t, r.karts[0], bs - 1.0, t.half - sim.KART_HALF)
    r.karts[0]["v"] = 20.0
    r.step_all({0: (1.0, 0.0, 0)})
    assert r.karts[0]["item"], r.items.state()["boxes"]
    # the teacher's fix: every part like new, new tyres
    r.karts[0]["dw"], r.karts[0]["tyre"] = 9000, 0.7
    assert r.fix(0) and r.karts[0]["dw"] == 0 and r.karts[0]["tyre"] == 0.0


def computer_pit_stops():
    """(CHANGE 186) A computer kart on worn tyres pits: with the lane open it drives in, stops in its own bay until
    it has new tyres, and drives on; with the PIT box it crawls through the box and its tyres come back."""
    import cpu_brains
    schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
    for mode in ("lane", "box"):
        t = kart_track.load("club")
        t.set_pits(mode)
        r = sim.Race(t, schema, laps=9)
        r.set_damage(True)
        r.set_tyres(True, 1)  # (a set lasts a lap: the stop comes soon)
        r.add(2, sim.default_design("Ace"))
        r.start()
        r.go_tick = r.tick
        worn, stopped, renewed, laps_after = 0.0, False, False, 0
        for _ in range(60 * 150):
            k = r.karts[2]
            r.step_all({2: cpu_brains.drive("expert", k, r)})
            k = r.karts[2]
            worn = max(worn, k["tyre"])
            if mode == "lane" and t.in_bay(2, k["s"], k["lat"]) and abs(k["v"]) < 0.5:
                stopped = True
            if worn >= cpu_brains.PIT_TYRE and k["tyre"] < (0.05 if mode == "lane" else 0.5):  # (the box is short: a crawl
                renewed = True  # through it renews about half a set)
            if renewed:
                laps_after = max(laps_after, k["lap"])
            if renewed and k["lap"] >= 3:
                break
        assert worn >= cpu_brains.PIT_TYRE, (mode, worn)
        assert renewed, (mode, "the tyres never came back", r.karts[2]["tyre"], r.karts[2]["lat"])
        assert mode == "box" or stopped, "never stopped in its bay"
        assert r.karts[2]["lap"] >= 3, (mode, "stuck after the stop", r.karts[2])


def real_damage():
    """(CHANGE 158) Hits damage the karts (barriers by how fast into them, other karts where they land), damage slows a
    kart, dulls its steering or pulls it to a side but never stops it, it mends by itself and quickly in the PIT box,
    and the lesson's switch turns it off (mending every kart)."""
    schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
    t = kart_track.load("club")
    st = sim.stats_of(sim.default_design("D"))

    def run(k, inp, n, damage=True):
        for _ in range(n):
            k = sim.step(k, inp, sim.STEP, t, st, damage)
            k.update(schema.quantise(k))
        return k

    def crash(damage):
        k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
        sim.place(t, k, 50.0, 0.0)
        k["yaw"], k["v"] = t.heading(50.0) + 60, 15.0  # (15: at 14 it lands within 5 mm of the barrier the tick before
        return run(k, (1.0, 0.0, 0), 90, damage)        # it crosses, which the step reads as already held there: CHANGE 177)
    hit = crash(True)
    assert hit["dw"] > 3000 and hit["dfl"] > 1000 and hit["de"] > 0 and hit["dfr"] == 0, {p: hit[p] for p in sim.DAMAGE_PARTS}
    assert not any(crash(False)[p] for p in sim.DAMAGE_PARTS)  # (damage off: none)
    # pinned against the barrier it isn't hit again (only arriving counts): a second later, a second's mending less
    later = run(dict(hit), (1.0, 0.0, 0), 60)
    assert all(later[p] <= hit[p] for p in sim.DAMAGE_PARTS), "damaged again while held at the barrier"

    def top_speed(level, wheels=None):
        k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
        sim.place(t, k, 0.0, 0.0)
        for p in sim.DAMAGE_PARTS:
            k[p] = level
        best = 0.0
        for _ in range(60 * 6):  # (held in the middle of the track: the top speed, nothing in the way)
            k = sim.step(k, (1.0, 0.0, 0), sim.STEP, t, st, False)
            k.update(schema.quantise(k))
            best = max(best, k["v"])
            k["lat"], (k["x"], k["y"], _) = 0.0, t.point(k["s"], 0.0)
            k["yaw"] = t.heading(k["s"])
            for p in sim.DAMAGE_PARTS:
                k[p] = level  # (no mending while measuring)
        return best
    fine, worst = top_speed(0), top_speed(sim.DAMAGE_MAX)
    assert 0.62 < worst / fine < 0.72, (fine, worst)  # (at worst two thirds of its speed: never stopped)
    # the left wheels damaged: steering straight, the kart turns left
    k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
    sim.place(t, k, 0.0, 0.0)
    k["v"], k["dfl"], k["drl"] = 12.0, sim.DAMAGE_MAX, sim.DAMAGE_MAX
    yaw0 = k["yaw"]
    k = run(k, (1.0, 0.0, 0), 30, False)
    assert (k["yaw"] - yaw0 + 180) % 360 - 180 > 5, (yaw0, k["yaw"])
    # mending: a tick on the road, quickly in the PIT box at pit speed (not too fast through it)
    k = sim.new_kart(0, None, 0.0, 0.0, 0.0)
    sim.place(t, k, 100.0, 0.0)
    k["de"] = 5000
    assert run(dict(k), (0.0, 0.0, 0), 60)["de"] == 5000 - 60 * sim.REPAIR_TICK
    s0, s1, side = t.pit
    sim.place(t, k, s0 + 1.0, side * (t.half - 1.6))
    k["de"], k["v"] = 5000, 3.0
    slow = run(dict(k), (0.0, 0.0, 0), 30)
    assert t.in_pit(slow["s"], slow["lat"]) and slow["de"] == 5000 - 30 * sim.REPAIR_PIT, slow["de"]
    k["v"] = 20.0
    fast = run(dict(k), (0.0, 0.0, 0), 10)
    assert fast["de"] == 5000 - 10 * sim.REPAIR_TICK, fast["de"]
    # karts: a fast one into the back of a slow one: its wing, the other's rear
    r = sim.Race(t, schema)
    r.set_damage(True)
    for i in range(2):
        r.add(i, sim.default_design(f"K{i}"))
    a, b = r.karts[0], r.karts[1]
    sim.place(t, a, 20.0, 0.0)
    sim.place(t, b, 21.5, 0.0)
    a["v"], b["v"] = 15.0, 3.0
    assert sim.bump(a, b, sim.BUMP_DISTANCE, 0.3, True)
    assert a["dw"] > 0 and b["drl"] > 0 and b["drr"] > 0 and b["dw"] == 0, ({p: a[p] for p in sim.DAMAGE_PARTS}, {p: b[p] for p in sim.DAMAGE_PARTS})
    r.set_damage(False)  # (the lesson's switch off: every kart mended)
    assert not any(k[p] for k in r.karts.values() for p in sim.DAMAGE_PARTS)


def power_ups():
    """(CHANGE 159) The item boxes give items (only those switched on), and each does what it should: a boost, a
    shield that takes one hit, an oil slick another kart slides on, a shot that reaches the kart ahead, a homing shot
    that finds the kart one place ahead round a bend; with every item off there are no boxes. And a pack of karts
    no longer wrecks itself: a bump damages a kart once, then a second's grace. (Each tick makes each kart's state
    anew: r.karts[i] is read again after every step.)"""
    import kart_items
    schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
    t = kart_track.load("club")

    def race(n=2, allowed=None, damage=True):
        r = sim.Race(t, schema)
        r.set_damage(damage)
        r.items = kart_items.Items(r, allowed, seed=7)
        for i in range(n):
            r.add(i, sim.default_design(f"K{i}"))
        r.phase, r.go_tick = sim.FLAGS_RACE, -1  # (racing, no countdown)
        return r

    def put(r, i, s, lat=0.0, v=0.0, item=None):
        k = r.karts[i]
        sim.place(t, k, s, lat)
        k["v"] = v
        if item:
            k["item"] = kart_items.CODE[item]

    # a box: driven through, an item (one of those allowed)
    r = race(1, {"shield": True})
    s, lat = t.box_spots()[0]
    put(r, 0, s - 0.5, lat)
    r.step_all({0: (0.0, 0.0, 0)})
    assert r.karts[0]["item"] == kart_items.CODE["shield"] and r.items.state()["boxes"][0] == "0", r.karts[0]["item"]
    # the shield: on with USE, it takes a hit
    r.step_all({0: (0.0, 0.0, sim.USE)})
    assert r.karts[0]["item"] == 0 and r.karts[0]["shield"] > 500, r.karts[0]["shield"]
    r.items.hit(0, "shot", r.karts[0]["x"] + 1, r.karts[0]["y"])
    assert r.karts[0]["shield"] == 0 and r.items.hits[-1][3] is True
    # a boost
    r = race(1)
    put(r, 0, 50.0, 0.0, 10.0, "boost")
    r.step_all({0: (1.0, 0.0, sim.USE)})
    assert r.karts[0]["boost"] >= kart_items.ITEM_BOOST - 2 and r.karts[0]["item"] == 0, r.karts[0]["boost"]
    # an oil slick dropped behind: the kart behind slides on it
    r = race(2)
    put(r, 0, 60.0, 0.0, 8.0, "oil")
    put(r, 1, 48.0, 0.0, 8.0)
    r.step_all({0: (1.0, 0.0, sim.USE), 1: (1.0, 0.0, 0)})
    assert len(r.items.slicks) == 1
    for _ in range(120):
        r.step_all({0: (1.0, 0.0, 0), 1: (1.0, 0.0, 0)})
        if r.karts[1]["slip"]:
            break
    assert r.karts[1]["slip"] > 0 and not r.items.slicks, (r.karts[1]["slip"], r.items.slicks)
    # a shot at the kart ahead on a straight: it spins out, damaged
    r = race(2)
    put(r, 0, 2.0, 0.0, 10.0, "shot")
    put(r, 1, 20.0, 0.0, 4.0)
    r.step_all({0: (1.0, 0.0, sim.USE), 1: (0.5, 0.0, 0)})
    hit = False
    for _ in range(90):
        r.step_all({0: (0.0, 0.0, 0), 1: (0.5, 0.0, 0)})
        if any(h[1] == 1 and h[2] == "shot" for h in r.items.hits):
            hit = True
            break
    b = r.karts[1]
    assert hit and b["slip"] > 0 and b["drl"] + b["drr"] > 0, ({p: b[p] for p in sim.DAMAGE_PARTS}, b["slip"])
    # a homing shot finds the kart one place ahead, out of sight round the first bend
    r = race(2)
    put(r, 0, 30.0, 0.0, 6.0, "homing")
    put(r, 1, 85.0, 0.0, 6.0)
    r.step_all({0: (0.0, 0.0, sim.USE), 1: (0.0, 0.0, 0)})
    assert r.items.shots and r.items.shots[0]["target"] == 1
    hit = False
    for _ in range(kart_items.HOMING_LIFE):
        r.step_all({0: (0.0, 0.0, 0), 1: (0.0, 0.0, 0)})
        if any(h[1] == 1 and h[2] == "homing" for h in r.items.hits):
            hit = True
            break
    assert hit, "the homing shot never found the kart ahead"
    # ...the kart in front on the road, not the leader: here the leader is further round, a lap ahead (Pete's
    # laptop test: it went for the leader)
    r = race(3)
    put(r, 0, 30.0, 0.0, 6.0, "homing")
    put(r, 1, 300.0, 0.0, 6.0)
    r.karts[1]["lap"] = 3
    put(r, 2, 70.0, 0.0, 6.0)
    r.step_all({0: (0.0, 0.0, sim.USE), 1: (0.0, 0.0, 0), 2: (0.0, 0.0, 0)})
    assert r.items.shots[0]["target"] == 2, r.items.shots[0]["target"]
    # every item off: no boxes, nobody holding one
    r = race(1)
    r.karts[0]["item"] = kart_items.CODE["shot"]
    r.items.set_allowed({})
    assert r.items.state()["boxes"] == "" and r.karts[0]["item"] == 0
    # a pack: four computer karts for 90 s barely scratch each other now (they wrecked themselves in a lap)
    import cpu_brains
    r = sim.Race(t, schema)
    r.set_damage(True)
    for i in range(4):
        r.add(i, sim.default_design(f"K{i}"))
    r.start()
    worst = 0
    for _ in range(60 * 90):
        r.step_all({kid: cpu_brains.drive("medium", k, r) for kid, k in r.karts.items()})
        worst = max(worst, max(k[p] for k in r.karts.values() for p in sim.DAMAGE_PARTS))
    # (CHANGE 176: a push from behind passes speed on down the bunch off the grid, so the worst scratch is a little
    # bigger; it is mended within a minute)
    assert worst < 0.5 * sim.DAMAGE_MAX and all(k["lap"] >= 2 for k in r.karts.values()), (worst, [k["lap"] for k in r.karts.values()])


def ultra_scenery():
    """(CHANGE 144) The ultra circuit (kart_scenery) on every track: nothing solid within the barrier's line but what
    is flat (kerbs, the pit lane) or overhead (the gantry), nothing taller than a barrier in front of a TV camera, and
    the file's packed arrays read back to the window's numbers."""
    import base64
    from array import array
    import kart_scenery as ks
    low = {"tuft", "tuft_long", "flowers"}  # (grass: not solid)
    flat = {"asphalt", "patch", "rubber", "tar", "line_paint", "gravel", "turf", "land", "water"}
    shapes = ks.shapes_once()
    # (CHANGE 151) the start lights: dark until 3 s to GO, one more pair each 0.6 s, all five at the end, out at GO
    assert [ks.start_lights(c) for c in (None, 4.0, 3.01, 3.0, 2.41, 2.39, 1.5, 0.61, 0.59, 0.01, 0.0, -1.0)] == \
        [0, 0, 0, 1, 1, 2, 3, 4, 5, 5, 0, 0]
    for name in kart_track.TRACKS:
        t = kart_track.load(name)
        c = ks.circuit(t)
        inner = t.half + ks.BARRIER - 0.05
        assert c.footbridge, (name, "no footbridge")  # (CHANGE 151: one on every track, checked with the rest below)
        assert sorted(p.name for p in c.near.all() if p.material == "lamp") == [f"lamp {k}" for k in range(1, 6)], name
        for shape, rows in c.inst.items():
            if shape in low:
                continue
            for x, y, z, *_ in rows:
                assert c.dist(x, y, inner + 1) >= inner, (name, shape, x, y, c.dist(x, y, inner + 1) - t.half)
        for p in c.near.all():
            if p.material in flat:
                continue
            for x, y, z in p.p:
                if c.dist(x, y, inner + 1) < inner:
                    _, s, _ = t.locate(x, y)
                    above = z - t.height(s)
                    assert above < 0.1 or above > 4.5, (name, p.material, x, y, above)  # (kerbs, the pit lane; the gantry)
        for cx, cy, cz, side, s in c.cams:
            out = c.out_of(s, side)
            for shape, rows in c.inst.items():
                tall = max(q[2] for part in shapes[shape] for q in part.p)
                for x, y, z, h, k, *_ in rows:
                    if tall * k > 1.3 and math.hypot(x - cx, y - cy) < ks.CAMERA_CLEAR:
                        raise AssertionError((name, "camera", shape, x, y))
            for p in c.near.all():
                for x, y, z in p.p:  # (the camera's own tower stands behind it)
                    if (math.hypot(x - cx, y - cy) < ks.CAMERA_CLEAR and (x - cx) * out[0] + (y - cy) * out[1] < 0.2
                            and z - c.ground_z(x, y) > 1.3 and z > cz - 4.0 and p.material not in flat):
                        raise AssertionError((name, "camera", p.material, x, y, z))
    part = ks.circuit(kart_track.load("club")).near.get("asphalt")
    packed = part.packed()
    q = array("H")
    q.frombytes(base64.b64decode(packed["positions"]))
    box = packed["box"]
    for i in range(0, len(part.p), 97):
        got = [box[k] + q[i * 3 + k] / 65535 * (box[k + 3] - box[k]) for k in range(3)]
        assert all(abs(a - b) < 0.005 for a, b in zip(got, part.p[i])), (got, part.p[i])
    assert len(json.dumps(packed)) < 0.4 * len(json.dumps({"p": part.p, "n": part.n, "uv": part.uv, "c": part.c, "i": part.idx}))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc):
    """Stop the server and anything it started: on Windows a venv's python.exe can be a launcher whose child is the
    real interpreter, and proc.kill() alone leaves that child (and its port) behind."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.kill()


def start_server(port, extra=()):
    env = dict(os.environ, KARTLAB_DATA=TMP)
    proc = subprocess.Popen([PY, "kart_server.py", "--port", str(port), "--cpu", "2", "--autostart", "1", *extra],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return proc
        except OSError:
            time.sleep(0.1)
    stop(proc)
    raise RuntimeError("the server did not start: " + proc.stdout.read().decode(errors="replace")[-400:])


def server_end_to_end():
    from websockets.sync.client import connect
    port = free_port()
    proc = start_server(port)
    try:
        schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
        url = f"ws://127.0.0.1:{port}"
        amy = connect(url, compression=None, open_timeout=5)
        amy.send(json.dumps({"type": "hello", "name": "Amy", "password": "amy12345", "code": "CLUB42",
                             "version": kart_version.VERSION}))  # (a laptop test server: a new username makes a profile)
        welcome = json.loads(amy.recv(5))
        assert welcome["type"] == "welcome" and welcome["kart"] is not None, welcome
        assert welcome["lesson"]["lesson_number"] == 1 and "tools" in welcome["lesson"], welcome["lesson"]
        assert welcome["rules"]["points_total"] == 100 and "full" in welcome["rules"], welcome["rules"]
        teacher = connect(url, compression=None, open_timeout=5)
        teacher.send(json.dumps({"type": "hello", "name": "Teacher", "code": "TEACH99", "version": kart_version.VERSION}))
        assert json.loads(teacher.recv(5))["role"] == "teacher"
        amy.send(json.dumps({"type": "design", "design": {"name": "Comet", "colour": [0, 200, 255],
                                                          "speed": 50, "acceleration": 30, "grip": 20}}))
        teacher.send(json.dumps({"type": "lesson_number", "n": 2}))    # the teaching framework's messages
        amy.send(json.dumps({"type": "prediction", "value": 40}))
        amy.send(json.dumps({"type": "reflection", "mission": "2e", "text": "grip keeps me on the track in the hairpin"}))
        amy.send(b"\x07junk")  # (a bad binary frame must not hurt)
        my_id = welcome["kart"]
        seq, snaps, acks, race_msgs, t0 = 0, [], set(), 0, time.time()
        design_ok, missions, lesson_msgs = None, None, 0
        last_send = 0.0
        while time.time() - t0 < 7.5:  # (the race starts after 1 s, the countdown takes 4)
            now = time.time()
            if now - last_send >= 1 / 60:
                last_send = now
                seq = (seq + 1) & 0xFFFF
                amy.send(wire.pack_input(seq, 0, int(now * 1000) & 0xFFFFFFFF, 1.0, 0.0, 0))
            try:
                raw = amy.recv(0.005)
            except TimeoutError:
                continue
            except Exception:
                continue
            if isinstance(raw, bytes):
                s = wire.unpack_snapshot(schema, raw)
                snaps.append((now, s))
                acks.add(s["ack"])
            else:
                m = json.loads(raw)
                if m["type"] == "race":
                    race_msgs += 1
                elif m["type"] == "design_result":
                    design_ok = (m["ok"], m["design"])
                elif m["type"] == "missions":
                    missions = m
                elif m["type"] == "lesson":
                    lesson_msgs += 1
        assert design_ok and design_ok[0] and design_ok[1]["name"] == "Comet" and design_ok[1]["speed"] == 50, design_ok
        assert missions and missions["lesson"] == 2 and missions["prediction"] == 40, missions and missions["lesson"]
        assert "2e" in missions["text"] and any(x["id"] == "2a" for x in missions["missions"]), missions["missions"]
        assert lesson_msgs >= 1
        assert len(snaps) > 120, f"only {len(snaps)} snapshots in 7.5 s"
        gaps = [b[0] - a[0] for a, b in zip(snaps[-60:], snaps[-59:])]
        rate = 1 / (sum(gaps) / len(gaps))
        assert 24 < rate < 36, f"snapshots at {rate:.0f} a second"
        assert len(acks) > 20, f"the acks never moved: {sorted(acks)[:5]}"
        assert race_msgs >= 3, race_msgs
        last = snaps[-1][1]
        me = next(e for e in last["entities"] if e["id"] == my_id)
        assert me["v"] > 5.0, f"full throttle for seconds but v = {me['v']}"
        assert len(last["entities"]) == 4, [e["id"] for e in last["entities"]]  # Amy, teacher, 2 computers
        amy.close()
        teacher.close()
    except Exception as e:
        stop(proc)
        out = proc.stdout.read().decode(errors="replace")[-700:]
        raise AssertionError(f"{type(e).__name__}: {e}\nserver said: {out}") from None
    finally:
        stop(proc)


def windows():
    shot = os.path.join(TMP, "offline.png")
    r = subprocess.run([PY, "kart_client.py", "--offline", "--offscreen", "--autostart", "--cpu", "3",
                        "--screenshot", shot, "--after", "5"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
    assert os.path.exists(shot) and os.path.getsize(shot) > 10000, "no offline screenshot"
    # (CHANGE 171 to 173) the sports cars, at night with their beams, braking, on the tiers that draw them differently
    for gfx in ("lines", "low", "ultra"):
        cars = os.path.join(TMP, f"cars_{gfx}.png")
        r = subprocess.run([PY, "kart_preview.py", "--gfx", gfx, "--bodies", "coupe,supercar,rally,muscle", "--time",
                            "night", "--brake", "--offscreen", "--screenshot", cars, "--after", "3"],
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
        assert os.path.exists(cars) and os.path.getsize(cars) > 10000, f"no picture of the cars on {gfx}"
    port = free_port()
    proc = start_server(port)
    try:
        shot2 = os.path.join(TMP, "online.png")
        r = subprocess.run([PY, "kart_client.py", "--host", f"ws://127.0.0.1:{port}", "--name", "Vi", "--offscreen",
                            "--screenshot", shot2, "--after", "5"], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
        assert os.path.exists(shot2) and os.path.getsize(shot2) > 10000, "no online screenshot"
    finally:
        stop(proc)


def designs_and_limits():
    """The design as variables: the schema, the checks (normal, boundary and invalid data) and the teacher's limits."""
    names = [v.name for v in sim.schema()]
    assert names == ["speed", "acceleration", "grip", "kart_name", "body", "colour"], names
    d = sim.default_design("Test")
    assert sim.check_design(d) == [], sim.check_design(d)
    assert sim.check_design(dict(d, speed=60, acceleration=30, grip=10)) == []           # boundary values
    assert any("61" not in p and "60" in p for p in sim.check_design(dict(d, speed=61)))  # invalid: too high
    assert any("points used" in p for p in sim.check_design(dict(d, speed=50, acceleration=40, grip=20)))
    assert any("whole number" in p for p in sim.check_design(dict(d, speed="fast")))
    assert sim.check_design(dict(d, colour=[0, 300, 0])) and sim.check_design(dict(d, name=""))
    # (CHANGE 173) the body: a kart or a sports car, only its look; anything else refused, or made a kart
    assert all(sim.check_design(dict(d, body=b)) == [] for b in sim.BODIES)
    assert any("body" in p for p in sim.check_design(dict(d, body="tank")))
    assert sim.fit_design(dict(d, body="tank"))["body"] == "kart" and sim.fit_design(dict(d, body="rally"))["body"] == "rally"
    assert sim.stats_of(dict(d, body="supercar")) == sim.stats_of(d), "a car drives as its points say"
    narrow = sim.clean_limits({"points": {"speed": [10, 40]}, "points_total": 90}, sim.default_limits())
    assert narrow["points"]["speed"] == [10, 40] and narrow["points_total"] == 90, narrow
    fitted = sim.fit_design(dict(d, speed=55, acceleration=25, grip=20), narrow)
    assert fitted["speed"] == 40 and sum(fitted[k] for k in sim.STATS) <= 90, fitted
    assert sim.fit_design(d, sim.default_limits()) is d, "a design inside the limits comes back as it is"
    assert sim.code_limits(narrow)["points"]["speed"] == [10, 60], sim.code_limits(narrow)
    assert sim.full_limits()["points_total"] == 100
    import kart_missions as km
    assert set(km.LESSONS) == {1, 2, 3, 4, 5} and all(k in km.OUTCOMES for k in ("VAR", "AISAFE", "EVAL"))
    for mid, (lesson, title, text, outcomes, how) in km.MISSIONS.items():
        assert lesson in km.LESSONS and all(o in km.OUTCOMES for o in outcomes) and how in ("auto", "teacher"), mid
    assert "60" in km.points_words("exactly 10 or exactly 60", sim.default_limits())
    assert km.points_words("Spend exactly 100 points", narrow) == "Spend exactly 90 points"
    assert {"if", "own_function", "memory"} <= km.brain_features(
        "def near(t):\n    return t.bend_ahead > 20\ndef brain(me, track, rivals):\n    me.memory['x'] = 1\n"
        "    if near(track):\n        return 0.5, 0\n    return 1, 0\n")


def profiles_and_missions():
    """Accounts (scrypt, the teacher's rules) and the missions the server completes from what a learner does."""
    import kart_profiles
    import kart_server
    kart_profiles.PROFILES = os.path.join(TMP, "profiles")
    try:
        kart_profiles.create("Vi", "short")
        raise AssertionError("a 5-letter password was accepted")
    except kart_profiles.LoginError as e:
        assert "6 characters" in str(e)
    prof = kart_profiles.create("Vi", "rocket42")
    assert prof["hash"].startswith("scrypt$") and "rocket42" not in json.dumps(prof)
    assert kart_profiles.login("Vi", "rocket42")[0]["name"] == "Vi"
    try:
        kart_profiles.login("Vi", "wrong-one")
        raise AssertionError("a wrong password was accepted")
    except kart_profiles.LoginError:
        pass
    kart_profiles.set_password("Vi", "comet123")
    assert kart_profiles.login("Vi", "comet123")[1] is False and "Vi" in kart_profiles.all_names()

    srv = kart_server.KartServer()
    p = kart_server.Player(None, "learner", "Vi", (220, 60, 50))
    p.profile = kart_profiles.load("Vi")
    srv.players[object()] = p
    srv.teaching.login(p)
    srv.rebuild()
    assert p.kart is not None and p.unit is not None and p.unit in srv.race.units.values()
    t = srv.teaching
    done = lambda: set(t.record("Vi").done)  # noqa: E731
    # lesson 1: a, b and c with the GUI, d from the code
    old = dict(p.design)
    new = dict(old, name="Comet", speed=40, grip=27)
    t.on_design(p, new, [], True, old=old, by_code=False)
    assert {"1a", "1b"} <= done(), done()
    new2 = dict(new, colour=[0, 200, 255])
    t.on_design(p, new2, [], True, old=new, by_code=False)
    assert "1c" in done(), done()
    t.on_design(p, dict(new2, acceleration=35, grip=25), [], True, old=new2, by_code=True)
    assert "1d" in done(), done()
    # lesson 2: the budget, invalid and boundary data, a prediction and a timed lap, a reflection
    t.apply_lesson(2)
    srv.rebuild()
    t.on_design(p, dict(new2, speed=60, acceleration=30, grip=10), [], True, old=new2, by_code=False)
    assert {"2a", "2c"} <= done(), done()
    t.on_design(p, dict(new2, speed=60, acceleration=60, grip=10), ["130 points used"], False, old=new2, by_code=True)
    assert "2b" in done(), done()
    replies = t.on_message(p, {"type": "prediction", "value": 40})
    assert replies and replies[0][1]["prediction"] == 40
    t.on_message(p, {"type": "reflection", "mission": "2e", "text": "grip keeps me on the track in the hairpin bend"})
    srv.race.lap_times[p.kart] = [38.5]          # (as the race records a lap)
    t.tick(10.0)
    assert {"2d", "2e"} <= done(), done()
    assert t.missions_msg(p)["best_lap"] == 38.5
    # lesson 3: a brain with selection, a function and memory
    t.apply_lesson(3)
    srv.rebuild()
    r = t.record("Vi")
    r.brain_features = {"if", "own_function", "memory"}
    t.brain_checks(p, r)
    assert {"3b", "3c", "3d"} <= done(), done()
    # the evidence export and the desk's report carry the outcomes
    assert open(t.export(), encoding="utf-8").read().startswith("Learner")
    report = t.session_report("2000-01-01", {})
    assert report["totals"]["Vi"]["VAR"] >= 2 and "Vi" in report["done"], report["totals"]
    # a learner's kart file, and deleting the learner removes everything
    t.save_design("Vi", p.design)
    assert os.path.exists(t.design_file("Vi"))
    text = t.delete_learner("Vi")
    assert "Deleted" in text and not os.path.exists(t.design_file("Vi")) and kart_profiles.load("Vi") is None


QUICK = "quick" in sys.argv  # (just the simulation checks, no server and no windows)
check("Every file compiles", compile_all)
check("The track answers consistently", track_answers)
check("The kart is deterministic, held by barriers, drifts and slides", kart_physics)
check("Prediction agrees with the server through 83 ms of delay and absorbs a bump", prediction_no_network)
check("Designs are checked as variables, inside the teacher's limits", designs_and_limits)
check("Accounts and missions: what a learner does completes the right objectives", profiles_and_missions)
check("Beside the road: the kerb, the gravel, the barrier past it, a push from behind, the handbrake and the clutch dropped, "
      "tyre wear and the pit stop, the pit lane open and closed, the outer item boxes, the teacher's fix", beside_the_road)
check("A computer kart on worn tyres pits: the lane and its bay, or the PIT box", computer_pit_stops)
check("Real damage: hits damage, damage slows but never stops, it mends (quickly in the PIT box), the switch turns it off",
      real_damage)
check("Power-ups: boxes give the items switched on; a boost, a shield, oil, a shot and a homing shot each work; a "
      "pack of karts doesn't wreck itself", power_ups)
check("The ultra circuit keeps clear of the karts and the TV cameras, and its file reads back", ultra_scenery)
if not QUICK:
    check("The server runs a race for two windows at 30 snapshots a second", server_end_to_end)
if not QUICK and "server" not in sys.argv:  # ("server": everything but the windows)
    check("The window draws offline and online", windows)

ok = True
for name, passed, note in results:
    print(f"{'PASS' if passed else 'FAIL'} {name}  {note}")
    ok = ok and passed
print("Test data:", TMP)
sys.exit(0 if ok else 1)
