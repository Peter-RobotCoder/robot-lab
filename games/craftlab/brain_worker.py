"""Runs one learner's Craft Bot brain in its own small process, so a brain can never freeze or crash the class server
(CHANGE 200). Started by craft_brain.py. It talks JSON, one line at a time, on stdin/stdout:
  -> {"source": "...", "fname": "..."}       load the brain    <- {"ok": true} or {"error": "..."}
  -> {"bot": {...}, "world": {...}}          one turn          <- {"r": [action, extra]} or {"error": "..."}
  -> {"reset": true}                         forget bot.memory <- {"ok": true}
It stops when stdin closes (the server stopped or dropped the brain).

The brain is brain(bot, world) and answers with what the Bot does next: one word ("forward", "back", "up",
"down", "left", "right", "dig", "dig_up", "dig_down", "wait") or a word and what with (("place", "planks"),
("place_up", "torch"), ("place_down", "rubble"), ("say", "hello")). Everything it sees is plain numbers and words.

On Linux (the class server) the process gets at most 256 MB of memory and can't write files. The server also stops
it if a turn takes too long, even when one giant sum is stuck inside a single line.
"""
import ast
import json
import math  # noqa: F401  (a brain may import it, as its own module)
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brain_rules as rules  # noqa: E402

MEMORY_LIMIT = 256 * 1024 * 1024
ACTIONS = ("forward", "back", "up", "down", "left", "right", "dig", "dig_up", "dig_down", "place", "place_up",
           "place_down", "wait", "say")


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


class BotView:
    """The Bot as its brain sees it: where it is (bot.x, bot.y, bot.z), which way it faces (bot.facing: "east",
    "north", "west" or "south"), the blocks round it by name (bot.front, bot.above, bot.below, bot.left_side,
    bot.right_side, bot.behind: "air", "stone", "log"...), what it carries (bot.inventory, a dictionary of name ->
    how many; bot.has("planks")), what it has done (bot.dug, bot.placed, bot.moves), where its owner is (bot.owner_x,
    bot.owner_y, bot.owner_z) and its dock (bot.home_x...), and bot.memory, a dictionary kept between turns."""

    def __init__(self, data, memory):
        for key, value in data.items():
            setattr(self, key, value)
        self.memory = memory

    def has(self, name, count=1):
        return self.inventory.get(name, 0) >= count


class WorldView:
    """The world near the Bot: world.day (True by day), world.time (0 to 1 through a day), world.block(dx, dy, dz)
    (the block that far from the Bot: dx east, dy north, dz up, each from -4 to 4), world.find(name) (the nearest
    block of that name within 4, as (dx, dy, dz), or None)."""

    def __init__(self, data):
        self.day = bool(data.get("day", True))
        self.time = float(data.get("time", 0.0))
        self._r = int(data.get("r", 4))
        self._names = data.get("names", [])
        self._grid = data.get("grid", "")

    def block(self, dx, dy, dz):
        r = self._r
        if not all(isinstance(v, int) and -r <= v <= r for v in (dx, dy, dz)):
            return "unknown"
        n = 2 * r + 1
        i = ((dx + r) * n + (dy + r)) * n + (dz + r)
        k = ord(self._grid[i]) - 48 if i < len(self._grid) else 0
        return self._names[k] if 0 <= k < len(self._names) else "unknown"

    def find(self, name):
        r = self._r
        best = None
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                for dz in range(-r, r + 1):
                    if (dx, dy, dz) != (0, 0, 0) and self.block(dx, dy, dz) == name:
                        d = abs(dx) + abs(dy) + abs(dz)
                        if best is None or d < best[0]:
                            best = (d, (dx, dy, dz))
        return best[1] if best else None


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


BAD_RETURN = ('brain must return what the Bot does next: a word such as "forward" or "dig", or a word and a block '
              'such as ("place", "planks")')


def pack(result):
    """The brain's answer as [action, extra] (extra: a block's name, or words to say), or None if it isn't one."""
    if result is None:
        return ["wait", ""]
    if isinstance(result, str):
        result = (result, "")
    if not isinstance(result, (tuple, list)) or not 1 <= len(result) <= 2:
        return None
    action = str(result[0]).strip().lower()
    if action not in ACTIONS:
        return None
    extra = str(result[1])[:40] if len(result) > 1 and result[1] is not None else ""
    return [action, extra]


def run_turn(brain, fname, memory, msg):
    bot = BotView(msg["bot"], memory)
    world = WorldView(msg.get("world", {}))
    lines, start = [0], time.perf_counter()

    def tracer(frame, event, arg):
        if event == "line":
            lines[0] += 1
            if lines[0] > rules.MAX_LINES_PER_TICK or (time.perf_counter() - start) * 1000 > rules.MAX_MS_PER_TICK * 3:
                raise TimeoutError("brain took too long (is there a loop that never ends?)")
        return tracer

    sys.settrace(tracer)
    try:
        result = brain(bot, world)
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
                reply(run_turn(brain, fname, memory, msg))
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
