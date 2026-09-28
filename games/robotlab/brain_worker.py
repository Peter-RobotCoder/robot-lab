"""Runs one learner's brain in its own small process, so a brain can never freeze or crash the class server.

Started by lab_brain.py. It talks JSON, one line at a time, on stdin/stdout:
  -> {"source": "...", "fname": "..."}            load the brain     <- {"ok": true} or {"error": "..."}
  -> {"me": {...}, "enemies": [{...}, ...]}       run one tick       <- {"r": [throttle, steer, attack]} or {"error": "..."}
  -> {"reset": true}                              forget me.memory   <- {"ok": true}
It stops when stdin closes (the server stopped or dropped the brain).

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
    """What a brain can see: read-only numbers, in metres, degrees and percent (made by lab_brain.view_data)."""

    def __init__(self, data, memory=None):
        for key, value in data.items():
            if key != "pit":
                setattr(self, key, value)
        self.memory = memory
        self.pit, self.centre = Spot(*data["pit"]), Spot(0.0, 0.0)

    def distance_to(self, thing):
        return math.hypot(thing.x - self.x, thing.y - self.y)

    def angle_to(self, thing):
        """Degrees to turn to face thing: positive = turn left, negative = turn right."""
        want = math.degrees(math.atan2(-(thing.x - self.x), thing.y - self.y))
        return (want - self.heading + 180) % 360 - 180


def load(source, fname):
    if len(source) > rules.MAX_SOURCE:
        raise rules.RuleError("the file is too long (max 20,000 characters)")
    try:
        tree = ast.parse(source, filename=fname)
    except SyntaxError as e:
        raise rules.RuleError(f"line {e.lineno}: {e.msg}") from None
    rules.check_code(tree)
    code = ast.Module(body=[n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))],
                      type_ignores=[])
    namespace = {"__builtins__": {**rules.SAFE_BUILTINS, "__import__": rules.safe_import,
                                  "print": lambda *a, **k: None}}
    exec(compile(code, fname, "exec"), namespace)
    if not callable(namespace.get("brain")):
        raise rules.RuleError("the file needs a function called brain(me, enemies)")
    return namespace["brain"]


def run_tick(brain, fname, memory, msg):
    me = View(msg["me"], memory)
    enemies = [View(e) for e in msg["enemies"]]
    lines, start = [0], time.perf_counter()

    def tracer(frame, event, arg):
        if event == "line":
            lines[0] += 1
            if lines[0] > rules.MAX_LINES_PER_TICK or (time.perf_counter() - start) * 1000 > rules.MAX_MS_PER_TICK:
                raise TimeoutError("brain took too long (is there a loop that never ends?)")
        return tracer

    sys.settrace(tracer)
    try:
        result = brain(me, enemies)
    except Exception as e:
        return {"error": rules.describe(e, fname)}
    finally:
        sys.settrace(None)
    try:
        throttle, steer, attack = result
        return {"r": [max(-1.0, min(1.0, float(throttle))), max(-1.0, min(1.0, float(steer))), bool(attack)]}
    except Exception:
        return {"error": "brain must return three things: throttle, steer, attack"}


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
