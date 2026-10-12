"""Load a learner's kart brain safely and drive their kart with it.

The same arrangement as Robot Lab's lab_brain.py: the file is checked (brain_rules.py: only functions and import
math/random, no files, no hidden __ names, a small set of built-ins), then runs in its own small process
(brain_worker.py) with a memory limit and a limit on how long each tick may take. A brain that crashes just
stops; the error and line number go back to the learner. The race carries on for everyone else.

What a brain sees is plain numbers (view_data, track_data, rival_data), sent as JSON each tick; the worker turns
them back into me.speed, track.point_ahead(...), rivals[0].ahead and so on. The kart's heading and every angle
here are degrees anticlockwise from +x, as kart_sim's yaw and kart_track's heading are; a positive angle means
"turn left".
"""
import ast
import json
import os
import queue
import subprocess
import sys
import threading
import time

import brain_rules as rules
import kart_sim

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "brain_worker.py")
LOAD_SECONDS = 5.0    # starting the process and loading the brain
TICK_SECONDS = 0.2    # the worker stops a slow brain after 20 ms itself; this is for one line that never ends
TOO_LONG = "brain took too long (is there a loop that never ends?)"
AHEAD_POINTS, AHEAD_SPACING = 8, 5.0  # the centre line sent each tick: 0, 5, ... 35 m ahead


class BrainError(Exception):
    pass


class SandboxedBrain:
    """One learner's brain, running in its own process."""

    def __init__(self, source, fname):
        self.source, self.fname = source, fname
        self.proc = None
        self._start()

    def _start(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.proc = subprocess.Popen([sys.executable, "-I", WORKER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=HERE, creationflags=flags)
        self.replies = queue.Queue()
        threading.Thread(target=self._read, args=(self.proc, self.replies), daemon=True).start()
        self.pending, self.last = None, None  # the question not answered yet (when it was asked), and the last answer
        reply = self._ask({"source": self.source, "fname": self.fname}, LOAD_SECONDS, "brain took too long to load")
        if "error" in reply:
            self.close()
            raise BrainError(reply["error"])

    @staticmethod
    def _read(proc, replies):
        for raw in proc.stdout:
            try:
                replies.put(json.loads(raw))
            except ValueError:
                pass
        replies.put({"error": "brain stopped (it may have used too much memory)", "dead": True})

    def _ask(self, msg, seconds, too_long=TOO_LONG):
        self._settle(seconds)
        if not self.alive():
            return {"error": "brain stopped (it may have used too much memory)"}
        try:
            self.proc.stdin.write(json.dumps(msg, separators=(",", ":")).encode("utf-8") + b"\n")
            self.proc.stdin.flush()
            reply = self.replies.get(timeout=seconds)
        except queue.Empty:
            self.close()
            return {"error": too_long}
        except OSError:
            self.close()
            return {"error": "brain stopped (it may have used too much memory)"}
        if reply.get("dead"):
            self.close()
        return reply

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    IDLE = (0.0, 0.0, 0)

    def tick(self, me, track, rivals):
        """One tick: the brain's answer (throttle, steer, drift 0/1), or raises BrainError.

        Asynchronous: the question is sent and the brain's answer to the *previous* question is returned at once, so
        a slow brain never holds up the physics step for everyone (it sees the race one tick, 17 ms, late). A brain
        that hasn't answered within TICK_SECONDS is stopped; until its first answer the kart coasts."""
        now = time.perf_counter()
        if self.pending is not None:
            try:
                reply = self.replies.get_nowait()
            except queue.Empty:
                if now - self.pending > TICK_SECONDS:
                    self.close()
                    raise BrainError(TOO_LONG)
                return self.last if self.last is not None else self.IDLE  # (not answered yet: as before)
            self.pending = None
            if reply.get("dead"):
                self.close()
            if "error" in reply:
                raise BrainError(reply["error"])
            self.last = tuple(reply["r"])
        if not self.alive():
            raise BrainError("brain stopped (it may have used too much memory)")
        try:
            question = json.dumps({"me": me, "track": track, "rivals": rivals}, separators=(",", ":")).encode("utf-8")
            self.proc.stdin.write(question + b"\n")
            self.proc.stdin.flush()
        except OSError:
            self.close()
            raise BrainError("brain stopped (it may have used too much memory)")
        self.pending = now
        return self.last if self.last is not None else self.IDLE

    def _settle(self, seconds):
        """Wait for the answer to a question still pending (before asking something else on the same pipe)."""
        if self.pending is None:
            return
        try:
            reply = self.replies.get(timeout=max(0.05, seconds))
            if reply.get("dead"):
                self.close()
        except queue.Empty:
            self.close()
        self.pending = None

    def reset(self):
        """Forget me.memory (and start again if the brain had stopped)."""
        self.last = None
        if self.alive():
            self._ask({"reset": True}, LOAD_SECONDS)
        else:
            try:
                self._start()
            except BrainError:
                pass

    def close(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.wait(timeout=2)
            except Exception:
                pass
            self.proc = None

    def __del__(self):
        self.close()


def check_source(source, fname):
    """The quick checks, done here before starting a process (so mistakes come back straight away)."""
    if len(source) > rules.MAX_SOURCE:
        raise BrainError("the file is too long (max 20,000 characters)")
    try:
        tree = ast.parse(source, filename=fname)
    except SyntaxError as e:
        raise BrainError(f"line {e.lineno}: {e.msg}") from None
    try:
        rules.check_code(tree)
    except rules.RuleError as e:
        raise BrainError(str(e)) from None
    if not any(isinstance(n, ast.FunctionDef) and n.name == "brain" for n in tree.body):
        raise BrainError(f"the file needs a function called {rules.REQUIRED}")


def load_brain(source, learner):
    """Returns (the learner's brain, its file name), or raises BrainError with a message they can act on."""
    fname = f"{learner}_brain.py"
    check_source(source, fname)
    return SandboxedBrain(source, fname), fname


# ---------- what a brain sees ----------
def wrap(deg):
    return (deg + 180.0) % 360.0 - 180.0


def along(track, s_from, s_to):
    """Metres along the track from s_from to s_to, the short way round: positive = s_to is ahead."""
    return (s_to - s_from + track.length / 2) % track.length - track.length / 2


def next_feature(track, features, s):
    """(metres along the track to the nearest of these (s, lateral) features ahead, its lateral); a track without
    any gives a whole lap, so "me.next_boost < 30" is simply never true."""
    best = None
    for fs, fl in features:
        d = (fs - s) % track.length
        if best is None or d < best[0]:
            best = (d, fl)
    return best or (track.length, 0.0)


def view_data(kart, race, place):
    """What a brain can see about its own kart, as plain numbers (brain_worker.View turns this back into me.x ...).
    place is 1 for the leader."""
    t = race.track
    s, lat, yaw = kart["s"], kart["lat"], kart["yaw"]
    boost_d, boost_lat = next_feature(t, t.boosts, s)
    now = 0.0 if race.go_tick is None else max(0.0, (race.tick - race.go_tick) * kart_sim.STEP)
    return {"name": race.designs[kart["id"]]["name"], "x": round(kart["x"], 3), "y": round(kart["y"], 3),
            "heading": round(yaw, 1), "speed": round(kart["v"] * 3.6, 1), "lateral": round(lat, 2),
            "track_width": t.width, "progress": round(t.progress(kart["lap"], kart["cp"], s), 1),
            "lap": kart["lap"], "laps": race.laps, "place": place, "count": len(race.karts),
            "angle_to_track": round(wrap(t.heading(s) - yaw), 1),
            "curve_ahead": round(t.curvature(s, 15.0), 1), "curve_far": round(t.curvature(s, 35.0), 1),
            "next_boost": round(boost_d, 1), "next_boost_lateral": round(boost_lat, 1),
            "on_oil": bool(kart["slip"]), "boosting": bool(kart["boost"]),
            "drifting": bool(kart["flags"] & (kart_sim.FLAG_DRIFT_L | kart_sim.FLAG_DRIFT_R)),
            "charge": int(kart["charge"]), "time": round(now, 2)}


def track_data(track, s, laps=None):
    """The track for a brain: its numbers and the centre line from s onwards, AHEAD_POINTS points AHEAD_SPACING
    apart (brain_worker.TrackView.point_ahead interpolates between them)."""
    ahead = []
    for i in range(AHEAD_POINTS):
        x, y, _ = track.point(s + i * AHEAD_SPACING)
        ahead.append([round(x, 2), round(y, 2)])
    return {"name": track.name, "length": round(track.length, 1), "width": track.width,
            "laps": track.laps if laps is None else laps, "ahead": ahead}


def rival_data(other, me, race, place):
    """What a brain can see about another kart: where it is, and how far ahead of me along the track (signed,
    the short way round, so a kart just behind the start line when I'm just past it is a few metres behind)."""
    t = race.track
    return {"name": race.designs[other["id"]]["name"], "x": round(other["x"], 3), "y": round(other["y"], 3),
            "heading": round(other["yaw"], 1), "speed": round(other["v"] * 3.6, 1), "lateral": round(other["lat"], 2),
            "progress": round(t.progress(other["lap"], other["cp"], other["s"]), 1), "place": place,
            "ahead": round(along(t, me["s"], other["s"]), 1)}


class Autopilot:
    """Wraps a learner's brain so the race can call it every tick, safely: autopilot(kart_state, race) gives the
    (throttle, steer, buttons) for kart_sim.Race.step_all."""

    def __init__(self, fn, fname):
        self.fn, self.fname = fn, fname
        self._error, self.started, self.ticks = None, None, 0

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, value):  # clearing the error (autopilot switched on again) restarts a stopped brain
        if value is None and self._error is not None:
            self.fn.reset()
        self._error = value

    @property
    def memory(self):
        return {}  # kept inside the brain's own process

    @memory.setter
    def memory(self, value):
        self.fn.reset()

    def __call__(self, kart, race):
        if self._error:
            return 0.0, 0.0, 0
        now = race.tick * kart_sim.STEP
        if self.started is None:
            self.started = now
        places = race.places()
        kid = kart["id"]
        me = view_data(kart, race, places.index(kid) + 1)
        track = track_data(race.track, kart["s"], race.laps)
        rivals = [rival_data(o, kart, race, places.index(oid) + 1) for oid, o in race.karts.items() if oid != kid]
        try:
            throttle, steer, drift = self.fn.tick(me, track, rivals)
        except BrainError as e:
            self._error = str(e)
            return 0.0, 0.0, 0
        self.ticks += 1
        return throttle, steer, kart_sim.DRIFT if drift else 0

    def close(self):
        self.fn.close()

    def seconds_running(self, now):
        return 0.0 if self.started is None or self._error else now - self.started
