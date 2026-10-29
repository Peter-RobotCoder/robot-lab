"""Load a learner's City Lab brain safely and move their person (or drive their car) with it.

The same arrangement as Kart Lab's kart_brain.py: the file is checked (brain_rules.py: only functions and import
math/random, no files, no hidden __ names, a small set of built-ins), then runs in its own small process
(brain_worker.py) with a memory limit and a limit on how long each tick may take. A brain that crashes just
stops; the error and line number go back to the learner. The city carries on for everyone else.

What a brain sees is plain numbers (view_data, city_data, other_data), sent as JSON each tick; the worker turns
them back into me.speed, city.depot, others[0].distance and so on. Headings and every angle are degrees
anticlockwise from east (+x), as city_sim's yaw is; a positive angle means "turn left".

The brain answers brain(me, city, others) with (throttle, steer) or (throttle, steer, action). In a car they are
the pedals and the wheel. On foot throttle is forward (back if below 0) and steer turns the way you walk (1 is a
right angle to the left). action is one word or a list of them: "run" (in a car: "drift"), "punch", "kick",
"jump", "block" (in a car: "handbrake"), "door" (get in the car beside you, or out of it).
"""
import ast
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time

import brain_rules as rules
import city_sim as sim

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "brain_worker.py")
LOAD_SECONDS = 5.0    # starting the process and loading the brain
TICK_SECONDS = 0.2    # the worker stops a slow brain after 20 ms itself; this is for one line that never ends
TOO_LONG = "brain took too long (is there a loop that never ends?)"
SEE = 60.0            # others within this many metres are in the brain's list (the nearest first)
SEE_MAX = 12
ACTIONS = {"run": sim.RUN, "drift": sim.DRIFT, "punch": sim.PUNCH, "kick": sim.KICK, "jump": sim.JUMP,
           "block": sim.BLOCK, "handbrake": sim.HANDBRAKE, "door": sim.ACTION}


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

    IDLE = (0.0, 0.0, "")

    def tick(self, me, city, others):
        """One tick: the brain's answer (throttle, steer, action), or raises BrainError.

        Asynchronous: the question is sent and the brain's answer to the *previous* question is returned at once, so
        a slow brain never holds up the physics step for everyone (it sees the city a tick, 17 ms, late). A brain
        that hasn't answered within TICK_SECONDS is stopped; until its first answer it stands still."""
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
            question = json.dumps({"me": me, "city": city, "others": others}, separators=(",", ":")).encode("utf-8")
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


def angle_from(x, y, heading, tx, ty):
    return round(wrap(math.degrees(math.atan2(ty - y, tx - x)) - heading), 1)


def view_data(person, world):
    """What a brain can see about itself, as plain numbers (brain_worker.View turns this back into me.x ...). In a
    car, where it is, its heading and speed are the car's."""
    pid = person["id"]
    car = world.cars.get(person["link"] - 1) if person["link"] else None
    at = car or person
    job = world.jobs.mine.get(pid) if getattr(world, "jobs", None) else None
    target = job.get("target") if job else None
    me = {"name": world.designs[pid]["name"], "x": round(at["x"], 2), "y": round(at["y"], 2),
          "heading": round(at["yaw"], 1), "speed": round(abs(at["v"]) * 3.6, 1), "in_car": car is not None,
          "health": person["hp"], "cash": person["cash"], "chips": person["aux"] >> 8,
          "knocked_down": person["move"] == sim.MOVE_DOWN, "damage": car["dmg"] if car else 0,
          "job": (job and {1: "delivery", 2: "taxi", 3: "race", 4: "roundup"}.get(job["kind"])) or "",
          "time": round(world.tick * sim.STEP, 2),
          # the job's target (zeros with none, so a brain can always read them)
          "target_x": 0.0, "target_y": 0.0, "target_name": "", "target_distance": 0.0, "angle_to_target": 0.0,
          "time_left": 0.0}
    if target:
        me.update(target_x=round(target[0], 2), target_y=round(target[1], 2), target_name=job.get("name", ""),
                  target_distance=round(math.hypot(target[0] - at["x"], target[1] - at["y"]), 1),
                  angle_to_target=angle_from(at["x"], at["y"], at["yaw"], target[0], target[1]))
        if "deadline" in job:
            me["time_left"] = round(max(0.0, (job["deadline"] - world.tick) * sim.STEP), 1)
    return me


def city_data(world, x, y, heading):
    """The city for a brain: its name and edges, the places' doors, and the road here (which way it runs)."""
    c = world.city
    places = {k: [round(v[0], 2), round(v[1], 2)] for k, v in c.places.items()
              if k in ("depot", "garage", "rank", "arcade", "carpark")}
    road = c.locate_road(x, y)
    on = "junction" if road and road[0] == "x" else "street" if road else "pavement"
    along = 0.0
    if on == "street":  # the street's direction, the way nearer to where you face
        along = 90.0 if road[0] == "v" else 0.0
        along = along if abs(wrap(along - heading)) <= 90 else wrap(along + 180.0)
    x0, y0, x1, y1 = c.bounds()
    return {"name": c.name, "west": x0, "south": y0, "east": x1, "north": y1, "places": places, "on": on,
            "road_heading": round(along, 1), "angle_to_road": round(wrap(along - heading), 1) if on == "street" else 0.0}


def other_data(tid, t, world, me_x, me_y, heading):
    kind = sim.kind_of(tid)
    d = world.designs.get(tid, {})
    out = {"name": d.get("name", ""), "kind": kind, "x": round(t["x"], 2), "y": round(t["y"], 2),
           "heading": round(t["yaw"], 1), "speed": round(abs(t["v"]) * 3.6, 1),
           "distance": round(math.hypot(t["x"] - me_x, t["y"] - me_y), 1),
           "angle": angle_from(me_x, me_y, heading, t["x"], t["y"])}
    if kind == "robot":
        out["rogue"] = bool(t["flags"] & sim.FLAG_ROGUE)
        out["off"] = bool(t["flags"] & sim.FLAG_OFF)
    elif kind == "car":
        out["empty"] = not t["link"]
    return out


def others_data(person, world, at):
    """The others near, the nearest first: people (not those in a car: their car is the one to see), cars, robots."""
    pid = person["id"]
    mine = person["link"] - 1 if person["link"] else None
    near = []
    for group in (world.people, world.cars, world.robots):
        for tid, t in group.items():
            if tid in (pid, mine) or (sim.kind_of(tid) == "person" and t["link"]):
                continue
            d2 = (t["x"] - at["x"]) ** 2 + (t["y"] - at["y"]) ** 2
            if d2 < SEE * SEE:
                near.append((d2, tid, t))
    near.sort(key=lambda e: (e[0], e[1]))
    return [other_data(tid, t, world, at["x"], at["y"], at["yaw"]) for _, tid, t in near[:SEE_MAX]]


def buttons_of(action, in_car):
    """The answer's action word (or words) as the input's buttons."""
    words = action if isinstance(action, (list, tuple)) else [action]
    b = 0
    for w in words:
        if isinstance(w, str):
            w = w.strip().lower()
            if in_car:
                w = {"run": "drift", "block": "handbrake"}.get(w, w)
            b |= ACTIONS.get(w, 0)
    return b


def to_input(answer, person, car):
    """The brain's (throttle, steer, action) as the person's or car's input: on foot, a walk in the world's frame,
    turned from the way the person faces."""
    throttle, steer, action = answer
    buttons = buttons_of(action, car is not None)
    if car is not None:
        return throttle, steer, buttons
    if abs(throttle) < 0.02 and abs(steer) < 0.02:
        return 0.0, 0.0, buttons
    sign = -1.0 if throttle < 0 else 1.0
    turn = math.radians(person["yaw"] + sign * max(-1.0, min(1.0, steer)) * 90.0)
    size = min(1.0, max(abs(throttle), abs(steer)))
    return sign * math.cos(turn) * size, sign * math.sin(turn) * size, buttons


class Autopilot:
    """Wraps a learner's brain so the world can call it, safely: autopilot(person, world) gives the
    (throttle, steer, buttons) for city_sim.World.step_all."""

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

    def __call__(self, person, world):
        if self._error:
            return 0.0, 0.0, 0
        now = world.tick * sim.STEP
        if self.started is None:
            self.started = now
        car = world.cars.get(person["link"] - 1) if person["link"] else None
        at = car or person
        me = view_data(person, world)
        city = city_data(world, at["x"], at["y"], at["yaw"])
        others = others_data(person, world, at)
        try:
            answer = self.fn.tick(me, city, others)
        except BrainError as e:
            self._error = str(e)
            return 0.0, 0.0, 0
        self.ticks += 1
        return to_input(answer, person, car)

    def close(self):
        self.fn.close()

    def seconds_running(self, now):
        return 0.0 if self.started is None or self._error else now - self.started
