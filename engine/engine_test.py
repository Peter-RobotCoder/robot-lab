"""Tests for the engine's wire format and prediction plumbing, with no server and no game.

    shared-world-demo\\.venv\\Scripts\\python engine\\engine_test.py      (from the ClubCodersAI folder)

Checks: every wire function round-trips, quantises and clamps; an 8-kart snapshot is 179 bytes; u16 sequence
numbers wrap in the InputLog and the ServerInputQueue; holes are filled from the redundant copies; a toy 1-D sim
(position += throttle * dt, a wall at x = 10) shows the Predictor never correcting against a perfect server,
correcting once against a server that applied an unknown impulse and ending exactly on the server's state; the
ErrorSmoother fades a 0.5 m error and snaps a 5 m one; the LeadController settles into the 1-2 tick band from an
empty buffer and from a deep one. Also prints what packing and unpacking an 8-kart snapshot costs.
Exit code 0 = every check passed.
"""
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import predict, wire  # noqa: E402
from engine.predict import ErrorSmoother, InputLog, LeadController, Predictor, ServerInputQueue  # noqa: E402

results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))


KART = wire.Schema("kart", [("x", "i", 100), ("y", "i", 100), ("z", "h", 100), ("yaw", "h", 10000),
                            ("pitch", "b", 100), ("roll", "b", 100), ("speed", "H", 100), ("steer", "b", 100),
                            ("flags", "B", 1), ("lap", "B", 1), ("cp", "B", 1)])


def kart(i):
    return {"id": i, "x": 12.345 * i - 50, "y": -7.891 * i, "z": 0.5 + 0.01 * i, "yaw": 0.4321 * i - 3,
            "pitch": 0.05 * i, "roll": -0.02 * i, "speed": 3.21 * i, "steer": 0.1 * i - 0.5,
            "flags": i * 3, "lap": i % 4, "cp": i * 7}


KARTS = [kart(i) for i in range(8)]

# ---- wire -----------------------------------------------------------------------------------------------------


def schema_round_trip():
    assert KART.size == 20, KART.size
    for k in KARTS:
        q = KART.quantise(k)
        assert KART.unpack(KART.pack(k)) == q, (k, q)
        assert KART.quantise(q) == q, "a second trip changed the numbers"
        assert KART.unpack(KART.pack(q)) == q
    assert isinstance(q["flags"], int) and isinstance(q["x"], float)
    buf = b"\xff" * 5 + KART.pack(KARTS[3])
    assert KART.unpack(buf, 5) == KART.quantise(KARTS[3]), "unpack at an offset"
check("schema: pack/unpack round-trips to what quantise() says, at an offset too", schema_round_trip)


def schema_quantise():
    q = KART.quantise({"x": 1.23456, "yaw": 3.14159, "speed": 12.3449, "lap": 2.0})
    assert q["x"] == 1.23 and q["yaw"] == 3.1416 and q["speed"] == 12.34 and q["lap"] == 2, q
    assert q["y"] == 0.0 and q["flags"] == 0, "a missing field is 0"
check("schema: values are rounded to the wire precision, missing ones are 0", schema_quantise)


def schema_clamp():
    q = KART.quantise({"x": 1e12, "y": -1e12, "z": 400, "pitch": 2.0, "roll": -2.0, "speed": -5, "steer": 9,
                       "flags": 300, "lap": -1, "cp": 256})
    assert q["x"] == 21474836.47 and q["y"] == -21474836.48, q
    assert q["z"] == 327.67 and q["pitch"] == 1.27 and q["roll"] == -1.28, q
    assert q["speed"] == 0 and q["steer"] == 1.27 and q["flags"] == 255 and q["lap"] == 0 and q["cp"] == 255, q
    for bad in ([("x", "f", 1)], [("x", "i", 0)]):
        try:
            wire.Schema("bad", bad)
            raise AssertionError(f"{bad} was accepted")
        except ValueError:
            pass
check("schema: out-of-range values clamp to the field's range (never raise); bad codes are refused", schema_clamp)


def snapshot_size():
    data = wire.pack_snapshot(KART, 123456, 7, KARTS, ack=99, flags=2)
    assert len(data) == 1 + 8 + 2 + 8 * 21 == 179, len(data)
    assert wire.kind_of(data) == wire.KIND_SNAPSHOT == 1
    assert len(wire.pack_snapshot(KART, 0, 0, [])) == 11
check("snapshot: 8 karts are 179 bytes, kind byte 1", snapshot_size)


def snapshot_round_trip():
    data = wire.pack_snapshot(KART, 4294967295, 65535, KARTS, ack=65534, flags=255)
    s = wire.unpack_snapshot(KART, data)
    assert (s["sm"], s["seq"], s["ack"], s["flags"]) == (4294967295, 65535, 65534, 255), s
    assert s["entities"] == [{"id": k["id"], **KART.quantise(k)} for k in KARTS]
    assert list(s["entities"][0]) == ["id"] + KART.names
    data = wire.pack_snapshot(KART, 2 ** 32 + 5, 2 ** 16 + 3, KARTS[:2])
    s = wire.unpack_snapshot(KART, data)
    assert (s["sm"], s["seq"], s["ack"], s["flags"], len(s["entities"])) == (5, 3, 0, 0, 2), "counters wrap"
    for bad in (data[:-1], data + b"\0", b"\x02" + data[1:], b""):
        try:
            wire.unpack_snapshot(KART, bad)
            raise AssertionError("a malformed frame was accepted")
        except ValueError:
            pass
check("snapshot: header, ack and every entity round-trip; counters wrap; malformed frames raise ValueError",
      snapshot_round_trip)


def input_round_trip():
    prev = [(0.5, -0.25, 1), (1.0, 0.0, 0)]
    data = wire.pack_input(65535, 65534, 4294967295, 0.834, -0.336, 5, prev)
    assert len(data) == wire.INPUT_SIZE == 1 + 11 + 6 == 18, len(data)
    assert wire.kind_of(data) == wire.KIND_INPUT == 2
    m = wire.unpack_input(data)
    assert (m["seq"], m["ack"], m["cms"]) == (65535, 65534, 4294967295), m
    assert (m["throttle"], m["steer"], m["buttons"]) == (0.83, -0.34, 5), m
    assert m["prev"] == prev, m["prev"]
    assert wire.quantise_input(0.834, -0.336, 5) == (0.83, -0.34, 5)
    m = wire.unpack_input(wire.pack_input(2 ** 16 + 1, 2 ** 16 + 2, 2 ** 32 + 3, 5.0, -5.0, 999, [(2, -2, -1)]))
    assert (m["seq"], m["ack"], m["cms"]) == (1, 2, 3), "counters wrap"
    assert (m["throttle"], m["steer"], m["buttons"]) == (1.27, -1.28, 255), "clamped"
    assert m["prev"] == [(1.27, -1.28, 0), (0, 0, 0)], "one previous clamps, the missing one is zeros"
    for bad in (data[:-1], b"\x01" + data[1:]):
        try:
            wire.unpack_input(bad)
            raise AssertionError("a malformed frame was accepted")
        except ValueError:
            pass
check("input: 18 bytes, kind byte 2, fields and the two previous inputs round-trip, clamp and pad",
      input_round_trip)


def kinds():
    assert wire.KIND_EVENT == 3 and wire.kind_of(b"") == 0 and wire.kind_of(b"\x03rest") == 3
check("kind_of routes by the first byte", kinds)

# ---- InputLog / ServerInputQueue ------------------------------------------------------------------------------


def log_wrap():
    log = InputLog(first_seq=65533)
    seqs = [log.add(f"in{i}") for i in range(5)]
    assert seqs == [65533, 65534, 65535, 0, 1], seqs
    assert log.since(65534) == [(65535, "in2"), (0, "in3"), (1, "in4")], log.since(65534)
    assert log.since(1) == [] and log.since(65532) == [(s, f"in{i}") for i, s in enumerate(seqs)]
    assert log.previous() == ["in3", "in2"] and log.previous(4) == ["in3", "in2", "in1", "in0"]
    log.trim(65535)
    assert [s for s, _, _ in log.entries] == [65535, 0, 1], "trim keeps the newest three for redundancy"
    log.trim(1)
    assert len(log) == 3
    assert InputLog().previous() == []
    small = InputLog(max_len=4)
    for i in range(10):
        small.add(i)
    assert len(small) == 4 and small.newest() == 9
check("InputLog: seqs wrap at 65535; since/previous/trim honour the wrap; the log is capped", log_wrap)


def queue_wrap_and_gaps():
    q = ServerInputQueue(idle="idle")
    assert q.pop_for_tick() == "idle" and q.repeats == 0 and q.applied is None, "nothing from the window yet: no number used"
    for s in (65534, 65535, 0, 1):
        assert q.push(s, f"in{s}", prev=[f"p{s}-1", f"p{s}-2"])
    assert q.depth() == 4, "the first message's prev entries are not queued before it"
    got = [q.pop_for_tick() for _ in range(4)]
    assert got == ["in65534", "in65535", "in0", "in1"], got
    assert q.applied == 1 and q.depth() == 0
    assert not q.push(65535, "old") and not q.push(1, "dup") and q.depth() == 0, "stale seqs are ignored"
    assert q.pop_for_tick() == "in1" and q.repeats == 1 and q.applied == 2, "dry: the last input again, as number 2 (CHANGE 175)"
    assert not q.push(2, "in2") and q.dropped == 3, "number 2 coming after its tick was run is dropped..."
    assert q.push(4, "in4", prev=["in3", "in2"]) and q.depth() == 2, "...and prev fills only what is still to come"
    assert q.pop_for_tick() == "in3"
    assert q.pop_for_tick() == "in4"
    assert q.push(9, "in9", prev=["in8", "in7"])
    assert q.push(10, "in10", prev=["in9", "in8"]) and q.depth() == 4, "prev never overwrites what arrived"
    assert q.pop_for_tick() == "in7" and q.skipped == 2 and q.applied == 7, "a wider hole (5, 6) is skipped"
    assert [q.pop_for_tick() for _ in range(3)] == ["in8", "in9", "in10"]
    q2 = ServerInputQueue(max_gap=1)
    q2.push(0, "a")
    q2.pop_for_tick()
    q2.push(3, "d", prev=["c", "b"])
    assert q2.depth() == 2 and q2.pop_for_tick() == "c", "max_gap limits how far back prev is used"
    q3 = ServerInputQueue(idle="idle", max_depth=4, idle_after=3, behind_after=5)  # (CHANGE 175) the cap, idling, a slow window
    for s in range(1, 9):
        q3.push(s, f"in{s}")
    assert q3.depth() == 4 and q3.skipped == 4 and q3.pop_for_tick() == "in5", "over max_depth the oldest go"
    for _ in range(3):
        q3.pop_for_tick()
    assert [q3.pop_for_tick() for _ in range(5)] == ["in8", "in8", "in8", "idle", "idle"], "dry: the last input, then idle"
    assert q3.applied == 13
    for s in range(3, 9):  # a window far behind (its numbers stale, nothing fresh): picked up where it is after 5
        q3.push(s, f"late{s}")
    assert q3.depth() == 1 and q3.pop_for_tick() == "late8" and q3.applied == 8, "...and its next input applied"
    q3.drain()
    assert q3.depth() == 0 and q3.applied == 8
    q4 = ServerInputQueue(idle="idle", merge=lambda late, nxt: nxt + "+" + late)  # a late input's presses kept
    q4.push(1, "in1")
    q4.push(2, "in2")
    assert [q4.pop_for_tick() for _ in range(3)] == ["in1", "in2", "in2"] and q4.applied == 3
    assert not q4.push(3, "in3") and q4.push(4, "in4")
    assert q4.pop_for_tick() == "in4+in3", "number 3 came late: dropped, its presses in number 4"
check("ServerInputQueue: wraps, drops stale seqs, a dry tick uses the next number, fills holes <= 2 from prev, skips wider, caps, idles",
      queue_wrap_and_gaps)

# ---- the toy sim ----------------------------------------------------------------------------------------------

DT = 1 / 60
WALL = 10.0


def step(state, throttle, dt):
    """position += throttle * dt, with a wall at x = 10 (the state is a 1-tuple)."""
    return (min(WALL, state[0] + throttle * dt),)


def compare(a, b):
    return abs(a[0] - b[0])


class ToyServer:
    """Applies the client's inputs in order and reports its state and the last seq applied, a few ticks late."""

    def __init__(self, impulse_at=None):
        self.state, self.queue, self.applied, self.impulse_at, self.tick = (0.0,), ServerInputQueue(), None, impulse_at, 0

    def receive(self, seq, throttle, prev):
        self.queue.push(seq, throttle, prev)

    def run_tick(self):
        inp = self.queue.pop_for_tick()
        if inp is not None:
            self.state = step(self.state, inp, DT)
            self.applied = self.queue.applied
        if self.tick == self.impulse_at:
            self.state = (self.state[0] + 0.5,)  # the thing the client could not know about
        self.tick += 1
        return self.state, self.applied


def drive(server, ticks, throttle=5.0, lag=3):
    """Client and server in lockstep: the client's input reaches the server lag ticks later, and the server's
    state for a tick reaches the client lag ticks after that. Returns the predictor and the server's final state."""
    p = Predictor(step, (0.0,))
    in_flight, back = [], []
    for t in range(ticks):
        th = throttle if t < ticks - 10 else 0.0  # (ease off near the end so the last inputs differ)
        seq = p.apply(th, DT)
        in_flight.append((t + lag, seq, th, p.log.previous()))
        while in_flight and in_flight[0][0] <= t:
            _, s, th2, prev = in_flight.pop(0)
            server.receive(s, th2, prev)
        state, ack = server.run_tick()
        if ack is not None:
            back.append((t + lag, state, ack))
        while back and back[0][0] <= t:
            _, st, a = back.pop(0)
            p.correct(st, a, DT, compare)
    for _ in range(2 * lag + 1):  # let the last inputs land and the last state come back
        while in_flight and in_flight[0][0] <= ticks + 2 * lag:
            _, s, th2, prev = in_flight.pop(0)
            server.receive(s, th2, prev)
        state, ack = server.run_tick()
        back.append((0, state, ack))
    while back:
        _, st, a = back.pop(0)
        p.correct(st, a, DT, compare)
    return p, server.state


def perfect_server():
    p, final = drive(ToyServer(), 200)
    assert p.corrections == 0, f"corrected {p.corrections} times against a perfect server"
    assert p.state == final, (p.state, final)
    assert final[0] > 5, final
check("toy sim (a): a perfect server never causes a correction, states agree exactly", perfect_server)


def impulse_server():
    p, final = drive(ToyServer(impulse_at=40), 200)
    assert p.corrections == 1, f"corrected {p.corrections} times, wanted exactly 1"
    assert p.state == final, f"predicted {p.state} but the server re-simulated to {final}"
    assert p.moved_from is None, "the last correction should have been a no-op"
    p, final = drive(ToyServer(impulse_at=100), 700)  # long enough to meet the wall
    assert p.corrections == 1 and p.state == final == (WALL,), (p.corrections, p.state, final)
check("toy sim (b): one unknown impulse -> one correction, the replay lands exactly on the server's state",
      impulse_server)


def predictor_edges():
    p = Predictor(step, (0.0,))
    for _ in range(5):
        p.apply(1.0, DT)
    before = p.state
    err = p.correct((p.predicted[2][0] + 0.01,), 2, DT, compare)
    assert abs(err - 0.01) < 1e-9 and p.state == before and p.corrections == 0, "below ignore: untouched"
    assert p.moved_from is None and 1 not in p.predicted and 2 in p.predicted, "older ticks are forgotten"
    assert p.correct(p.predicted[2], 2, DT, compare) == 0.0, "the same ack again (a dry server) is not a snap"
    err = p.correct((7.0,), 1000, DT, compare)  # an ack we never logged (reconnect): snap; nothing is newer
    assert err == math.inf and p.corrections == 1 and p.moved_from == before and p.state == (7.0,), (err, p.state)
    p = Predictor(step, (0.0,), ring=4)
    for _ in range(10):
        p.apply(1.0, DT)
    assert list(p.predicted) == [6, 7, 8, 9], "the ring keeps the newest predictions only"
check("Predictor: errors under ignore leave the state alone; an unknown ack snaps; the ring is bounded",
      predictor_edges)


def smoother():
    s = ErrorSmoother()
    s.add((0.5, 0.0, 0.0), 0.0)
    assert s.dpos == (0.5, 0.0, 0.0)
    frames = 0
    while s.offset(DT)[0][0] >= 0.05 and frames < 200:
        frames += 1
    assert frames < 90, f"0.5 m took {frames} frames (> 1.5 s) to fade below 0.05 m"
    assert s.dpos == (0.0, 0.0, 0.0), "below ignore the offset is dropped to zero"
    s.add((5.0, 0.0, 0.0), 0.0)
    assert s.dpos == (0.0, 0.0, 0.0) and s.snaps == 1, "5 m snaps at once"
    s.add((0.0, 0.0, 0.0), math.radians(50))
    assert s.dyaw == 0.0 and s.snaps == 2, "50 degrees of yaw snaps"
    s.add((0.0, 0.0, 0.0), math.radians(20))
    d1, y1 = s.offset(DT)
    assert abs(y1 - math.radians(20) * 0.92) < 1e-9, "yaw decays 0.92 per frame"
    s.add((0.02, 0.0, 0.0))
    assert s.dpos == (0.0, 0.0, 0.0), "an error under 0.05 m is ignored"
    s.add((0.0, 0.0, 0.3))
    s.add((0.0, 0.0, 0.3))
    assert s.dpos == (0.0, 0.0, 0.6), "a second error during a fade adds to what is left"
    big = ErrorSmoother(adaptive=False)
    big.add((2.0, 0.0, 0.0))
    d, _ = big.offset(DT * 2)  # a 30 fps frame fades twice as much
    assert abs(d[0] - 2.0 * 0.9 ** 2) < 1e-9, d
    up = ErrorSmoother(remove_up=True)
    up.add((0.3, 0.0, 0.3))
    assert up.dpos == (0.3, 0.0, 0.0), "remove_up zeroes the vertical part"
check("ErrorSmoother: 0.5 m fades under 0.05 m within 1.5 s; 5 m and 50 degrees snap; yaw 0.92; time-corrected",
      smoother)


def lead(start_depth):
    """A server ticking at 60 Hz pops one input a tick; the client makes one every multiplier/60 s."""
    lead = LeadController()
    queue, pending, depths, m = start_depth, 0.0, [], 1.0
    for _ in range(600):
        pending += 1.0 / m
        while pending >= 1.0:
            queue += 1
            pending -= 1.0
        if queue:
            queue -= 1
        depths.append(queue)
        m = lead.feed(queue)
        assert 0.9 <= m <= 1.1, m
    tail = depths[-120:]
    assert all(1 <= d <= 2 for d in tail), f"from {start_depth}: the last 2 s of depths were {sorted(set(tail))}"
    assert 0.99 < lead.depth < 2.01 and abs(lead.multiplier() - 1.0) < 1e-9, (lead.depth, lead.multiplier())
    return depths


def lead_from_empty():
    depths = lead(0)
    assert 0 in depths, "it should have started dry"


def lead_from_deep():
    depths = lead(6)
    assert max(depths) == 6 and depths.index(min(d for d in depths if d <= 2)) < 120, "drained within 2 s"


check("LeadController: converges into the 1-2 band from an empty buffer and stays there", lead_from_empty)
check("LeadController: converges into the 1-2 band from a depth of 6 and stays there", lead_from_deep)


def lead_steps():
    lc = LeadController()
    assert lc.multiplier() == 1.0, "no reading yet: no nudge"
    assert lc.feed(0) == 0.9 and lc.feed(0) == 0.9
    for _ in range(100):
        lc.feed(1.5)
    assert lc.multiplier() == 1.0
    assert lc.feed(6) <= 1.05, "one deep reading (a burst after a stall) does not jolt the pace (EWMA)"
    for _ in range(30):
        lc.feed(6)
    assert lc.multiplier() == 1.1, "but a sustained one hits the limit"
check("LeadController: 1.0 inside the band, 0.9/1.1 at the limits, one odd reading is smoothed", lead_steps)

# ---- the cost of an 8-kart snapshot ---------------------------------------------------------------------------


def timing():
    """Mean cost per call over 10,000 calls, and the best of five such rounds (what the code costs when nothing
    else on the laptop is in the way: the mean swings with whatever else is running)."""
    n, rounds = 10000, 5
    data = wire.pack_snapshot(KART, 1234, 5, KARTS, ack=3)
    msg = wire.pack_input(1, 2, 3, 0.5, -0.5, 1)
    jobs = [("8-kart snapshot pack", lambda: wire.pack_snapshot(KART, 1234, 5, KARTS, ack=3)),
            ("8-kart snapshot unpack", lambda: wire.unpack_snapshot(KART, data)),
            ("input pack", lambda: wire.pack_input(1, 2, 3, 0.5, -0.5, 1, [(0.5, -0.5, 1), (0.4, -0.4, 0)])),
            ("input unpack", lambda: wire.unpack_input(msg))]
    print(f"snapshot {len(data)} bytes, input {len(msg)} bytes; per call, {n} calls per round, {rounds} rounds:")
    for name, fn in jobs:
        means = []
        for _ in range(rounds):
            t0 = time.perf_counter()
            for _ in range(n):
                fn()
            means.append((time.perf_counter() - t0) / n)
        print(f"  {name}: first round {1e6 * means[0]:.1f} us, best round {1e6 * min(means):.1f} us")


timing()

for name, ok, note in results:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "\n    " + note))
print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
