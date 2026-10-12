"""Load a learner's robot brain safely and run it for their Robot Lab robot.

Uses the same checks as the Robot League (brain_rules.py): only functions and import math/random,
no files, no hidden __ names, a small set of built-ins, and a limit on how long each tick may take.
A brain that crashes just stops; the error and line number go back to the learner.

Each brain runs in its own small process (brain_worker.py) with a memory limit, and the server stops that
process if a tick takes too long. So even a brain that tries a gigantic sum, or fills memory, only stops
itself: the arena carries on for everyone else.
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
import lab_sim as sim

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "brain_worker.py")
LOAD_SECONDS = 5.0    # starting the process and loading the brain
TICK_SECONDS = 0.2    # the worker stops a slow brain after 20 ms itself; this is for one line that never ends
TOO_LONG = "brain took too long (is there a loop that never ends?)"


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

    IDLE = (0.0, 0.0, False)

    def tick(self, me, enemies):
        """One tick: the brain's answer, or raises BrainError.

        Asynchronous: the question is sent and the brain's answer to the *previous* question is returned at once, so
        a slow brain never holds up the physics step for everyone (it sees the game one tick, 17 ms, late). A brain
        that hasn't answered within TICK_SECONDS is stopped; until its first answer the brain does nothing."""
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
            question = json.dumps({"me": me, "enemies": enemies}, separators=(",", ":")).encode("utf-8")
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
        raise BrainError("the file needs a function called brain(me, enemies)")


def load_brain(source, learner):
    """Returns (the learner's brain, its file name), or raises BrainError with a message they can act on."""
    fname = f"{learner}_brain.py"
    check_source(source, fname)
    return SandboxedBrain(source, fname), fname


def view_data(robot, now):
    """What a brain can see about one robot, as plain numbers (brain_worker.View turns this back into me.x ...)."""
    p = robot.pos
    half = sim.ARENA / 2
    return {"name": robot.name, "weapon": robot.weapon, "x": round(p.x, 3), "y": round(p.y, 3),
            "heading": round(robot.np.getH() % 360, 1), "speed": round(robot.speed * 3.6, 1),
            "armour": round(100 * max(0.0, robot.health) / robot.stats["armour"], 1),
            "upside_down": bool(robot.np.getQuat().getUp().z < 0.3),
            "weapon_ready": bool(now >= robot.fire_until + 0.9), "weapon_rpm": round(robot.weapon_rpm),
            "time": round(now, 2), "pit": list(sim.Arena.PIT[:2]),
            "distance_to_wall": round(min(half - abs(p.x), half - abs(p.y)), 2),
            # (CHANGE 98) half the robot's width, and the arena's size: the brain measures from each side's wheels
            "half_width": round(float(robot.shape["half"].x), 2), "arena": sim.ARENA}


class Autopilot:
    """Wraps a learner's brain so lab_sim can call it every tick, safely."""

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

    def __call__(self, robot, enemies, arena):
        if self._error:
            return 0.0, 0.0, False
        now = arena.time
        if self.started is None:
            self.started = now
        try:
            result = self.fn.tick(view_data(robot, now), [view_data(e, now) for e in enemies])
        except BrainError as e:
            self._error = str(e)
            return 0.0, 0.0, False
        self.ticks += 1
        return result

    def close(self):
        self.fn.close()

    def seconds_running(self, now):
        return 0.0 if self.started is None or self._error else now - self.started
