"""Robot Lab's brains in pseudo code (CHANGE 211): the Missions' pseudo code (mission_pseudo) with Robot Lab's own
dictionary (missions/arena_brain/dictionary.json), and Python that can be typed in its place.

A brain's lines are read again 60 times a second, so they say what to do *now*: drive forward, turn towards enemy,
attack, if enemy distance less than 3 ... else ... end. Each pseudo code line is one line of Python inside
brain(me, enemies); the start and the end are always the same (START and END below: the nearest enemy, throttle,
steer and attack, then the return), so the whole brain is a real my_brain.py the Robot Lab server runs as it runs one
from a file.

Both sides can be written:
    read(pseudo)        each line's reading and its Python (mission_pseudo.parse_program), and the whole brain
    to_pseudo(python)   the other way: each line of Python read with the patterns' own Python (a line that isn't one
                        of them is kept as typed, and shown as a line the phrasebook doesn't know)
The window reads both itself; the page asks its class server, which uses the same functions.
"""
import os
import re

import mission_pseudo as P

HERE = os.path.dirname(os.path.abspath(__file__))
DICTIONARY = os.path.join(HERE, "missions", "arena_brain", "dictionary.json")
C = P.load(DICTIONARY)

START = ["def brain(me, enemies):",
         "    if not enemies:",
         "        return 0, 0, False",
         "    enemy = min(enemies, key=me.distance_to)  # the nearest enemy",
         "    throttle, steer, attack = 0, 0, False"]
END = ["    return throttle, steer, attack"]
HEADER = ('"""My robot brain, written in pseudo code in Robot Lab (the Brain panel, K): each line of pseudo code is a '
          'line of Python here."""')
STARTER = ("# Chase the nearest enemy and attack it when it's close.\n"
           "turn towards enemy\n"
           "if enemy distance less than 3\n"
           "  attack\n"
           "  drive slowly\n"
           "else\n"
           "  drive forward\n"
           "end")
MAX_LINES = 60


def read(text):
    """The pseudo code read: mission_pseudo's {"rows", "errors", "program", "code_lines", "python"}, with "source":
    the whole brain as Python (None while a line can't be read), and "body": its lines, as the Python column shows."""
    text = "\n".join(str(text).split("\n")[:MAX_LINES])
    parsed = P.parse_program(text, C)
    body = [r["python_line"] for r in parsed["rows"]]
    parsed["body"] = body
    parsed["source"] = None if parsed["errors"] else source_of(body)
    return parsed


def source_of(body):
    lines = ["    " + line if line.strip() else "" for line in body]
    return "\n".join([HEADER, ""] + START + lines + END) + "\n"


# ---------- Python back to pseudo code ----------
NUMBER = r"(\d+)"


def _squash(text):
    return re.sub(r"\s+", "", text)


def _reverse_patterns():
    """Each pattern's Python as a pattern to match a line of Python against (spaces don't matter): its slots are
    the slot's own Python (dir left: 1) or a number."""
    out = []
    for p in C.patterns:
        if p.get("alias"):
            continue
        if p.get("closes"):  # (end: END_COMMENT)
            continue
        rx, slots, pos, template = "", [], 0, p["python"]
        for m in P.FILL.finditer(template):
            rx += re.escape(_squash(template[pos:m.start()]))
            name = m.group(1) or m.group(2)
            slot = C.dict["slots"][name]
            if slot["kind"] == "number":
                rx += NUMBER
            else:
                py = slot.get("python") or {}
                choices = sorted(((_squash(py.get(v, v)), v) for v in slot["values"]), key=lambda c: -len(c[0]))
                rx += "(" + "|".join(re.escape(c[0]) for c in choices) + ")"
            slots.append((name, slot))
            pos = m.end()
        rx += re.escape(_squash(template[pos:]))
        out.append((re.compile("^" + rx + "$"), p, slots))
    return out


REVERSE = _reverse_patterns()
END_COMMENT = re.compile(r"^#\s*end\b", re.I)


def line_to_pseudo(line):
    """One line of Python as pseudo code, or None if it isn't one the phrasebook knows. A comment stays a comment;
    "# end" (or "# end of if") is end."""
    text = line.strip()
    if not text:
        return ""
    if END_COMMENT.match(text):
        return "end"
    if text.startswith("#"):
        return text
    code = _squash(re.sub(r"\s+#.*$", "", text))  # (a note after the code is dropped)
    for rx, p, slots in REVERSE:
        m = rx.match(code)
        if not m:
            continue
        values = {}
        for (name, slot), got in zip(slots, m.groups()):
            if slot["kind"] == "number":
                n = int(got)
                if not slot["min"] <= n <= slot["max"]:
                    break
                values[name] = n
            else:
                py = slot.get("python") or {}
                values[name] = next(v for v in slot["values"] if _squash(py.get(v, v)) == got)
        else:
            return P.fill(p["say"], values)
    return None


def to_pseudo(python):
    """The Python column read back, line for line: (the pseudo code, [line numbers whose Python isn't known]). A line
    that isn't known is kept as it was typed, so the pseudo code side shows it as a line it can't read."""
    out, unknown = [], []
    for i, line in enumerate(str(python).split("\n")[:MAX_LINES]):
        said = line_to_pseudo(line)
        if said is None:
            unknown.append(i + 1)
            said = line.strip()
        depth = len(line) - len(line.lstrip(" "))
        out.append(" " * min(depth // 2, 8) + said if said else "")
    return "\n".join(out), unknown


def phrasebook():
    """What the panel's phrasebook shows: each instruction, what it does and an example; the values; the brain's start
    and end around the lines (the Python column shows them, greyed, as they can't be changed)."""
    d = C.dict
    return {"patterns": [{"say": p["say"], "meaning": p["meaning"], "example": p["example"]} for p in d["patterns"]
                         if not p.get("alias")],
            "values": {k: s["describe"] for k, s in d["slots"].items()},
            "start": START, "end": END, "starter": STARTER}


ROW_KEYS = ("n", "kind", "raw", "indent", "python_line", "message", "hint", "after", "canonical")


def code_msg(side, text, with_phrasebook=False):
    """The page's question answered (CHANGE 211: it has no Python of its own to read pseudo code with): the pseudo code
    (read back from the Python when the Python column was typed in), each line's reading and Python, the lines of
    Python that aren't known, and whether it can run."""
    text = str(text)[:6000]
    pseudo, unknown = to_pseudo(text) if side == "python" else (text, [])
    parsed = read(pseudo)
    out = {"type": "brain_code", "side": "python" if side == "python" else "pseudo", "pseudo": pseudo,
           "python": "\n".join(parsed["body"]), "unknown": unknown, "errors": len(parsed["errors"]),
           "lines": parsed["code_lines"], "ok": parsed["source"] is not None,
           "rows": [{k: r.get(k) for k in ROW_KEYS if r.get(k) is not None} for r in parsed["rows"]]}
    if with_phrasebook:
        out["phrasebook"] = phrasebook()
    return out


def indent(text):
    """The pseudo code with each line indented by its if or else (two spaces a level), as the panel shows it after a
    RUN (what is typed is never changed while it is being typed)."""
    parsed = P.parse_program(text, C)
    return "\n".join(("  " * r["indent"] + r["raw"].strip()) if r["raw"].strip() else "" for r in parsed["rows"])
