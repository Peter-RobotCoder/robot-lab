"""Robot Lab's robots drawn where they are now, not where they were (CHANGE 166).

The window and the page draw the arena about 67 ms in the past (engine.interp: blended between the snapshots
either side), and the server's word on a robot is the network's half of a round trip older again: a robot doing
6 m/s is drawn half a metre behind where it is, and your own robot answers your keys a round trip and 67 ms late.
Rocket League (Bullet too) draws the others carried on from their last known speed and your own car predicted from
your keys; Bullet can't be run the same on every computer, so here, as there, nothing is re-simulated:

- every robot is carried on from its newest snapshot to the moment a key pressed now takes effect on the server
  (the server's time as seen plus a round trip), at most HORIZON;
- your own robot by a small drive model (DRIVE, fitted to the server's Bullet robot: 5 to 12 cm off after 100 ms
  for 95% of drives) from the keys sent since, so it answers them at once;
- the others at the speed and turn rate their snapshots show (9 cm off after 100 ms for 95%, where drawn late
  they were 50 cm off);
- when a new snapshot shows the guess was off, the difference is drawn away over a few frames (FADE: 0.8 of it left
  after a frame, 0.7 for a bigger one; Gaffer's 0.95 suits corrections that come now and then, and with one every
  other frame they piled up to ten times the size), never snapped (but for a jump of over 2 m: a respawn);
- a robot in the air, on its side, upside down or knocked out is drawn as it was (the blend), easing between the
  two over 0.2 s; its weapon moves with it. Collisions, flips and hits stay the server's.

club-coders/web/ahead.js is the page's copy, line for line.
"""
import math
from collections import deque

STEP = 1 / 60
HORIZON = 0.25          # the most a robot is carried on past its newest snapshot (s)
DRIVE = {"acc": 0.5, "brake": 1.3, "stop": 6.0, "coast": 2.0, "yaw_k": 8.0}  # (fitted: see the module's docstring)
EASE = 0.2              # seconds to ease between drawn ahead and drawn as it was
SNAP = 2.0              # metres: a difference this big is a respawn, not a guess that was off
BIG = 0.3               # metres: a difference bigger than this is drawn away faster
FADE, FADE_BIG = 0.8, 0.7  # what's left of a difference after a frame (a sixtieth of a second)
APART = 3.0             # metres between the newest snapshot and the blend: more is a respawn, drawn as blended


def yaw_of(q):
    """The heading of a robot's (w, x, y, z) quaternion: the direction its forward (+y) points, radians from +x."""
    w, x, y, z = q
    return math.atan2(1 - 2 * (x * x + z * z), 2 * (x * y - w * z))


def up_z(q):
    w, x, y, z = q
    return 1 - 2 * (x * x + y * y)


def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw)


def turned(q, a):
    """q turned by a radians about the world's up."""
    return qmul((math.cos(a / 2), 0.0, 0.0, math.sin(a / 2)), q)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def drive_step(s, throttle, steer, stats, dt, P=DRIVE):
    """One step of the drive model: s = (x, y, yaw, v, w); stats: forward_max, reverse_max, accel, turn_rate."""
    x, y, yaw, v, w = s
    fwd, rev, acc, turn = stats
    if (throttle > 0 and v > fwd) or (throttle < 0 and -v > rev):
        throttle = 0.0
    if throttle:
        v += acc * P["acc"] * throttle * (P["brake"] if throttle * v < 0 else 1.0) * dt
    else:
        v -= math.copysign(min(abs(v), (P["stop"] if steer == 0 else P["coast"]) * dt), v)
    w += (steer * turn - w) * min(1.0, P["yaw_k"] * dt)
    yaw += w * dt
    return (x + math.cos(yaw) * v * dt, y + math.sin(yaw) * v * dt, yaw, v, w)


class RobotsAhead:
    def __init__(self):
        self.tracks, self.prev, self.fresh = {}, {}, set()
        self.off, self.weight = {}, {}
        self.inputs = deque(maxlen=120)  # (local time sent, throttle, steer): your own keys

    def control(self, local_t, throttle, steer):
        """A control sent to the server (as sent: steer already turned round when reversing)."""
        self.inputs.append((local_t, float(throttle), float(steer)))

    def snapshot(self, server_t, robots):
        """A new snapshot's robots (the watched arena's: id, pos, quat, speed, ko), stamped server_t (s)."""
        seen = set()
        for r in robots:
            rid = r["id"]
            seen.add(rid)
            yaw = yaw_of(r["quat"])
            old = self.tracks.get(rid)
            w = 0.0
            if old is not None:
                gap = server_t - old["t"]
                if gap <= 0:
                    continue
                w = wrap(yaw - old["yaw"]) / gap if gap <= 0.2 else old["w"]
            self.prev[rid] = old
            self.tracks[rid] = {"t": server_t, "x": r["pos"][0], "y": r["pos"][1], "yaw": yaw,
                                "v": r.get("speed", 0.0) or 0.0, "w": w, "up": up_z(r["quat"])}
            self.fresh.add(rid)
        for rid in list(self.tracks):
            if rid not in seen:  # (gone from the arena: forget it)
                for d in (self.tracks, self.prev, self.off, self.weight):
                    d.pop(rid, None)
                self.fresh.discard(rid)

    def key_at(self, local_t):
        """The control that was being sent at local_t (none before the first)."""
        got = (0.0, 0.0)
        for t, th, st in self.inputs:
            if t > local_t:
                break
            got = (th, st)
        return got

    def target(self, tr, until, own, stats, local_now):
        """Where a track's robot is at server time `until`: (x, y, yaw)."""
        h = max(0.0, min(HORIZON, until - tr["t"]))
        s = (tr["x"], tr["y"], tr["yaw"], tr["v"], tr["w"])
        n = int(h / STEP)
        rest = h - n * STEP
        for k in range(n + (1 if rest > 1e-9 else 0)):
            dt = STEP if k < n else rest
            if own and stats:
                t_k = tr["t"] + k * STEP
                th, st = self.key_at(local_now - (until - t_k))
                s = drive_step(s, th, st, stats, dt)
            else:
                x, y, yaw, v, w = s
                yaw += w * dt
                s = (x + math.cos(yaw) * v * dt, y + math.sin(yaw) * v * dt, yaw, v, w)
        return s[0], s[1], s[2]

    def adjust(self, robots, local_now, server_seen, rtt, my_id=None, stats=None, dt=1 / 60):
        """The robots as blended (engine.interp), drawn ahead: new dicts, the others' fields as they were.
        stats: id -> (forward_max, reverse_max, accel, turn_rate), from the roster (your own robot's at least)."""
        if server_seen is None:
            return robots
        until = server_seen + max(0.0, min(0.3, rtt))
        out = []
        for r in robots:
            rid = r["id"]
            tr = self.tracks.get(rid)
            q = r["quat"]
            ok = (tr is not None and not r.get("ko") and up_z(q) > 0.9 and tr["up"] > 0.9  # (a respawn: as blended
                  and math.hypot(tr["x"] - r["pos"][0], tr["y"] - r["pos"][1]) < APART)    # until the blend gets there)
            wt = max(0.0, min(1.0, self.weight.get(rid, 0.0) + (dt if ok else -dt) / EASE))
            self.weight[rid] = wt
            if tr is None or wt <= 0.0:
                self.off.pop(rid, None)
                out.append(r)
                continue
            own = rid == my_id
            st = (stats or {}).get(rid) if own else None
            x, y, yaw = self.target(tr, until, own, st, local_now)
            off = self.off.get(rid, (0.0, 0.0, 0.0))
            if rid in self.fresh:  # a new snapshot: the old guess's difference from the new is drawn away
                self.fresh.discard(rid)
                old = self.prev.get(rid)
                if old is not None and rid in self.off:
                    ox, oy, oyaw = self.target(old, until, own, st, local_now)
                    off = (off[0] + ox - x, off[1] + oy - y, wrap(off[2] + oyaw - yaw))
            size = math.hypot(off[0], off[1])
            if size > SNAP:
                off = (0.0, 0.0, 0.0)
            k = (FADE_BIG if size > BIG else FADE) ** (dt * 60)
            off = (off[0] * k, off[1] * k, off[2] * k)
            self.off[rid] = off
            ix, iy, iz = r["pos"]
            iyaw = yaw_of(q)
            fx = ix + wt * (x + off[0] - ix)
            fy = iy + wt * (y + off[1] - iy)
            dyaw = wt * wrap(yaw + off[2] - iyaw)
            n = dict(r)
            n["pos"] = [fx, fy, iz]
            n["quat"] = list(turned(q, dyaw))
            if "wpos" in r and "wquat" in r:  # (its weapon turns about it and moves with it)
                c, s_ = math.cos(dyaw), math.sin(dyaw)
                wx, wy = r["wpos"][0] - ix, r["wpos"][1] - iy
                n["wpos"] = [fx + c * wx - s_ * wy, fy + s_ * wx + c * wy, r["wpos"][2]]
                n["wquat"] = list(turned(r["wquat"], dyaw))
            out.append(n)
        return out


# ---------- Fight Lab: your own fighter's footwork (CHANGE 167) ----------
FREE = {"idle", "walk_f", "walk_b", "side_l", "side_r", "block", "low_block", "crouch"}  # (the moves it can walk from)
HOLDS = {"block", "low_block", "crouch"}  # (held: standing still)
GRIP = 18.0             # fight_sim's grip on the floor: how fast a fighter's speed follows its keys (1/s)
BACK = 0.7              # ...walking backwards is this much slower
APART_FIGHTER = 1.0     # (as APART: a fighter walks 2 m/s at most)
# (CHANGE 193) a punch's start-up drawn at once: how long past a round trip it waits for the server's word before
# it's taken back (the snapshots come every 33 ms, and one may be late)
CONFIRM = 0.12
CROUCHED = {"crouch", "low_block"}  # (punch held crouching is the low sweep: not drawn ahead)


class FighterAhead:
    """Fight Lab's own fighter's walking and sidestepping drawn at once (fight_sim's footwork: speed eases to what
    the keys ask, along the line to the opponent and across it), from its newest snapshot to the moment a key pressed
    now takes effect. Attacks, blocks, hits, throws and jumps stay the server's: from any of them it is drawn as
    blended, easing between the two over EASE. The other fighters are drawn as blended (they change direction too
    often to carry on). ahead.js's FighterAhead is the page's copy.

    (CHANGE 193) The punch button pressed from footwork: the move it starts (your combo's first) is drawn starting at
    once, its start-up held at its last frame until a snapshot shows the server started it, then on from when you
    pressed it, so it lands on screen when it lands on the server. Taken back (drawn as blended) if the server's
    word doesn't come within a round trip and CONFIRM, or a snapshot shows you hit, thrown or doing something else."""

    def __init__(self):
        self.track = self.prev = None
        self.fresh = False
        self.off, self.weight = (0.0, 0.0), 0.0
        self.inputs = deque(maxlen=120)  # (local time sent, forward, side, hold)
        self.pressed = None  # (CHANGE 193) a punch pressed, not drawn yet: its local time
        self.punch = None    # ...the punch drawn: {"t": pressed, "move", "s", "a", "r": its timing, "seen": the server's word}

    def control(self, local_t, fwd, side, hold=""):
        self.inputs.append((local_t, float(fwd), float(side), hold or ""))

    def press(self, local_t, action):
        """(CHANGE 193) A button sent: a punch is drawn from the next adjust."""
        if action == "punch":
            self.pressed = local_t

    def snapshot(self, server_t, fighters, my_id, phase=None):
        """A new snapshot's fighters in your ring (id, pos, a), stamped server_t; phase: the ring's ("fight": punches
        start)."""
        me = next((f for f in fighters if f["id"] == my_id), None)
        if me is None:
            self.track = self.prev = None
            self.punch = None
            return
        foe = next((f for f in fighters if f["id"] != my_id), None)
        old = self.track
        if old is not None and server_t <= old["t"]:
            return
        vx = vy = 0.0
        if old is not None and server_t - old["t"] <= 0.2:
            vx, vy = (me["pos"][0] - old["x"]) / (server_t - old["t"]), (me["pos"][1] - old["y"]) / (server_t - old["t"])
        fx, fy = 1.0, 0.0
        if foe is not None:
            dx, dy = foe["pos"][0] - me["pos"][0], foe["pos"][1] - me["pos"][1]
            d = math.hypot(dx, dy)
            if d > 0.05:
                fx, fy = dx / d, dy / d
        self.prev = old
        self.track = {"t": server_t, "x": me["pos"][0], "y": me["pos"][1], "vx": vx, "vy": vy, "fx": fx, "fy": fy,
                      "free": me.get("a") in FREE and me["pos"][2] < 0.01, "fight": phase in (None, "fight")}
        self.fresh = True
        p = self.punch
        if p is not None:
            if me.get("a") == p["move"]:
                p["seen"] = True  # (the server started it)
            elif not self.track["free"]:
                self.punch = None  # (hit, thrown, in the air: the server's word)

    def key_at(self, local_t):
        got = (0.0, 0.0, "")
        for t, f, s, h in self.inputs:
            if t > local_t:
                break
            got = (f, s, h)
        return got

    def target(self, tr, until, stats, local_now):
        walk, sidestep = stats
        h = max(0.0, min(HORIZON, until - tr["t"]))
        x, y, vx, vy = tr["x"], tr["y"], tr["vx"], tr["vy"]
        n = int(h / STEP)
        rest = h - n * STEP
        for k in range(n + (1 if rest > 1e-9 else 0)):
            dt = STEP if k < n else rest
            fwd, side, hold = self.key_at(local_now - (until - (tr["t"] + k * STEP)))
            tx = ty = 0.0
            if hold not in HOLDS and (abs(fwd) > 0.1 or abs(side) > 0.1):
                back = BACK if fwd < 0 else 1.0
                px, py = -tr["fy"], tr["fx"]
                tx = tr["fx"] * fwd * walk * back + px * side * sidestep
                ty = tr["fy"] * fwd * walk * back + py * side * sidestep
            a = min(1.0, GRIP * dt)
            vx += (tx - vx) * a
            vy += (ty - vy) * a
            x += vx * dt
            y += vy * dt
        return x, y

    def adjust(self, fighters, local_now, server_seen, rtt, my_id, stats, dt=1 / 60, punch=None):
        """Your ring's fighters as blended: yours drawn ahead (new dicts); stats: (walk, sidestep) m/s, yours; punch:
        (CHANGE 193) [move, start-up, active, recovery seconds] of the move your punch button starts, yours."""
        return self.startup(self.footwork(fighters, local_now, server_seen, rtt, my_id, stats, dt), local_now, rtt,
                            my_id, punch)

    def startup(self, fighters, local_now, rtt, my_id, punch):
        """(CHANGE 193) Your punch drawn from when you pressed it (see the class's docstring)."""
        me = next((f for f in fighters if f["id"] == my_id), None)
        tr = self.track
        if self.pressed is not None:
            t0, self.pressed = self.pressed, None
            if (punch and self.punch is None and me is not None and tr is not None and tr["free"] and tr["fight"]
                    and me.get("a") in FREE and me["pos"][2] < 0.01 and self.key_at(t0)[2] not in CROUCHED):
                self.punch = {"t": t0, "move": punch[0], "s": max(punch[1], 1e-3), "a": max(punch[2], 1e-3),
                              "r": max(punch[3], 1e-3), "seen": False}
        p = self.punch
        if p is None or me is None:
            return fighters
        el, s, a, r = local_now - p["t"] - STEP, p["s"], p["a"], p["r"]  # (the server begins it on the step after the
        # press arrives: a step later than the key's own time)
        if not p["seen"]:
            if el > max(0.0, min(0.3, rtt)) + CONFIRM:
                self.punch = None  # (the server never started it: taken back)
                return fighters
            k = min(el / s, 0.999)  # (its start-up, held at the last frame till the server's word)
        elif el >= s + a + r and me.get("a") != p["move"]:
            self.punch = None  # (done here, and done in the blend)
            return fighters
        else:
            k = el / s if el < s else 1 + (el - s) / a if el < s + a else 2 + min(1.0, (el - s - a) / r)
        drawn = dict(me, a=p["move"], k=max(0.0, k))
        return [drawn if f is me else f for f in fighters]

    def footwork(self, fighters, local_now, server_seen, rtt, my_id, stats, dt=1 / 60):
        """Your fighter's walking and sidestepping drawn ahead (CHANGE 167)."""
        tr = self.track
        me = next((f for f in fighters if f["id"] == my_id), None)
        if server_seen is None or me is None or tr is None or not stats:
            return fighters
        ok = (tr["free"] and me.get("a") in FREE and me["pos"][2] < 0.01  # (back in the ring after a ring out: as
              and math.hypot(tr["x"] - me["pos"][0], tr["y"] - me["pos"][1]) < APART_FIGHTER)  # blended till it's there)
        self.weight = max(0.0, min(1.0, self.weight + (dt if ok else -dt) / EASE))
        if self.weight <= 0.0:
            self.off = (0.0, 0.0)
            return fighters
        until = server_seen + max(0.0, min(0.3, rtt))
        x, y = self.target(tr, until, stats, local_now)
        off = self.off
        if self.fresh:
            self.fresh = False
            if self.prev is not None:
                ox, oy = self.target(self.prev, until, stats, local_now)
                off = (off[0] + ox - x, off[1] + oy - y)
        size = math.hypot(*off)
        if size > SNAP:
            off = (0.0, 0.0)
        k = (FADE_BIG if size > BIG else FADE) ** (dt * 60)
        self.off = off = (off[0] * k, off[1] * k)
        wt, (ix, iy, iz) = self.weight, me["pos"]
        drawn = dict(me, pos=[ix + wt * (x + off[0] - ix), iy + wt * (y + off[1] - iy), iz])
        return [drawn if f is me else f for f in fighters]
