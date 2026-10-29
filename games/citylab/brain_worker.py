"""Runs one learner's City Lab brain in its own small process, so a brain can never freeze or crash the class server.

Started by city_brain.py. It talks JSON, one line at a time, on stdin/stdout:
  -> {"source": "...", "fname": "..."}                   load the brain    <- {"ok": true} or {"error": "..."}
  -> {"me": {...}, "city": {...}, "others": [{...}]}     run one tick      <- {"r": [throttle, steer, action]} or {"error": "..."}
  -> {"reset": true}                                     forget me.memory  <- {"ok": true}
It stops when stdin closes (the server stopped or dropped the brain).

The brain returns (throttle, steer) or (throttle, steer, action); the reply has throttle and steer clamped to
-1..1 and action as a word or a list of words (city_brain.ACTIONS says which). The city comes as plain numbers
too (its places' doors as spots: city.depot.x), so this process never needs the City object.

On Linux (the class server) the process gets at most 256 MB of memory and can't write files. The server
also stops it if a tick takes too long, even when one giant sum is stuck inside a single line.
"""
import ast
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_rules as rules  # noqa: E402

MEMORY_LIMIT = 256 * 1024 * 1024


def limit_process():
    try:
        import resource
    except ImportError:  # Windows (a laptop test server): the server's time limit still applies
        return
    for what, value in ((resource.RLIMIT_AS, MEMORY_LIMIT), (resource.RLIMIT_FSIZE, 0), (resource.RLIMIT_CORE, 0)):
        try:
            resource.setrlimit(what, (value, value))
        except (ValueError, OSError):
            pass


class Spot:
    def __init__(self, x, y):
        self.x, self.y = x, y


class View:
    """What a brain can see about itself or another: read-only numbers, in metres, degrees and km/h (made by
    city_brain.view_data and other_data)."""

    def __init__(self, data, memory=None):
        for key, value in data.items():
            setattr(self, key, value)
        self.memory = memory

    def distance_to(self, thing):
        return math.hypot(thing.x - self.x, thing.y - self.y)

    def angle_to(self, thing):
        """Degrees to turn to face thing: positive = turn left, negative = turn right."""
        want = math.degrees(math.atan2(thing.y - self.y, thing.x - self.x))
        return (want - self.heading + 180) % 360 - 180


class CityView:
    """The city as a brain sees it: its name and edges, the places' doors as spots (city.depot, city.garage,
    city.rank, city.arcade, city.carpark) and the road here (city.on, city.road_heading, city.angle_to_road)."""

    def __init__(self, data):
        for key, value in data.items():
            if key != "places":
                setattr(self, key, value)
        for name, p in (data.get("places") or {}).items():
            setattr(self, name, Spot(float(p[0]), float(p[1])))


def load(source, fname):
    if len(source) > rules.MAX_SOURCE:
        raise rules.RuleError("the file is too long (max 20,000 characters)")
    try:
        tree = ast.parse(source, filename=fname)
    except SyntaxError as e:
        raise rules.RuleError(f"line {e.lineno}: {e.msg}") from None
    rules.check_code(tree)
    code = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                                                                   ast.Assign))], type_ignores=[])
    namespace = {"__builtins__": {**rules.SAFE_BUILTINS, "__import__": rules.safe_import,
                                  "print": lambda *a, **k: None}}
    exec(compile(code, fname, "exec"), namespace)
    if not callable(namespace.get("brain")):
        raise rules.RuleError(f"the file needs a function called {rules.REQUIRED}")
    return namespace["brain"]


BAD_RETURN = ("brain must return two or three things: throttle and steer, each a number from -1 to 1, and an "
              "action word such as 'punch'")


def pack(result):
    """The brain's answer as the reply's [throttle, steer, action], or None if it isn't one."""
    if isinstance(result, (int, float)) or not isinstance(result, (tuple, list)) or len(result) not in (2, 3):
        return None
    try:
        throttle, steer = float(result[0]), float(result[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(throttle) and math.isfinite(steer)):
        return None
    action = result[2] if len(result) == 3 else ""
    if isinstance(action, (list, tuple)):
        action = [str(a)[:12] for a in action[:6] if isinstance(a, str)]
    else:
        action = action[:12] if isinstance(action, str) else ""
    return [max(-1.0, min(1.0, throttle)), max(-1.0, min(1.0, steer)), action]


def run_tick(brain, fname, memory, msg):
    me = View(msg["me"], memory)
    city = CityView(msg.get("city", {}))
    others = [View(o) for o in msg.get("others", [])]
    lines, start = [0], time.perf_counter()

    def tracer(frame, event, arg):
        if event == "line":
            lines[0] += 1
            if lines[0] > rules.MAX_LINES_PER_TICK or (time.perf_counter() - start) * 1000 > rules.MAX_MS_PER_TICK:
                raise TimeoutError("brain took too long (is there a loop that never ends?)")
        return tracer

    sys.settrace(tracer)
    try:
        result = brain(me, city, others)
    except Exception as e:
        return {"error": rules.describe(e, fname)}
    finally:
        sys.settrace(None)
    r = pack(result)
    if r is None:
        return {"error": BAD_RETURN}
    return {"r": r}


def main():
    out = sys.stdout.buffer
    sys.stdout = sys.stderr  # nothing but replies may go to the server

    def reply(msg):
        out.write(json.dumps(msg).encode("utf-8") + b"\n")
        out.flush()

    limit_process()
    brain, fname, memory = None, "brain.py", {}
    for raw in sys.stdin.buffer:
        try:
            msg = json.loads(raw)
            if "source" in msg:
                fname = str(msg.get("fname", "brain.py"))
                brain = load(str(msg["source"]), fname)
                reply({"ok": True})
            elif msg.get("reset"):
                memory = {}
                reply({"ok": True})
            elif brain is not None:
                reply(run_tick(brain, fname, memory, msg))
            else:
                reply({"error": "no brain loaded"})
        except rules.RuleError as e:
            reply({"error": str(e)})
        except MemoryError:
            reply({"error": "brain used too much memory"})
            return
        except Exception as e:
            reply({"error": rules.describe(e, fname)})


if __name__ == "__main__":
    main()
