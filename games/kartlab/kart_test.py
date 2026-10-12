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
        k = r.karts[0]
        assert abs(k["lat"]) <= t.half - sim.KART_HALF + 1e-6, k["lat"]
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
        amy.send(json.dumps({"type": "hello", "name": "Amy", "code": "CLUB42", "version": kart_version.VERSION}))
        welcome = json.loads(amy.recv(5))
        assert welcome["type"] == "welcome" and welcome["kart"] is not None, welcome
        teacher = connect(url, compression=None, open_timeout=5)
        teacher.send(json.dumps({"type": "hello", "name": "Teacher", "code": "TEACH99", "version": kart_version.VERSION}))
        assert json.loads(teacher.recv(5))["role"] == "teacher"
        amy.send(json.dumps({"type": "design", "design": {"speed": 50, "acceleration": 30, "grip": 20}}))
        amy.send(b"\x07junk")  # (a bad binary frame must not hurt)
        my_id = welcome["kart"]
        seq, snaps, acks, race_msgs, t0 = 0, [], set(), 0, time.time()
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


QUICK = "quick" in sys.argv  # (just the simulation checks, no server and no windows)
check("Every file compiles", compile_all)
check("The track answers consistently", track_answers)
check("The kart is deterministic, held by barriers, drifts and slides", kart_physics)
check("Prediction agrees with the server through 83 ms of delay and absorbs a bump", prediction_no_network)
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
