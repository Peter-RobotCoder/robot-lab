"""schema.js against the app's own Python: the code panel must write and read the code exactly as the windows do.

For each game (Robot Lab, Fight Lab, Kart Lab) this makes many designs (the standard ones, random ones, edge values)
and many code texts (as written, with values edited, out of range, broken in every way a learner's typing can break
them), asks the app's Python what it makes of each (engine.schema, each game's simulation, and the windows' own
code_ctx, outside_limits and apply_code, read out of the window files and run without a window), asks schema.js the
same in Node, and compares: the code's text byte for byte, the values read (or the error, its line and its words),
what APPLY CODE says and does to the design, the design checks, the garage's tables and the Warnings tab's changes.

    shared-world-demo/.venv/Scripts/python club-coders/web/schema_test.py [--seed N] [--count N]

Prints "N of N passed" (and the first failures). Skipped, with a note, when Node isn't installed.
"""
import ast
import copy
import importlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import textwrap
import warnings
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_schemas  # noqa: E402

warnings.simplefilter("ignore")  # (Python warns about "\q" and 1if: the code panel's reading doesn't)

GAMES = {"robotlab": ("lab_sim", "shared-world-demo", "lab_client.py", "lab_server.py"),
         "fightlab": ("fight_sim", "BeatEmUp", "fight_client.py", "fight_server.py"),
         "kartlab": ("kart_sim", "kart", "kart_client.py", "kart_server.py")}


def methods(path, names, namespace):
    """The named methods of a window's (or server's) class, read from its file and made plain functions that take a
    stand-in for self: the test runs the app's own lines, not a copy of them."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in names and item.name not in found:
                    found[item.name] = item
    missing = set(names) - set(found)
    if missing:
        raise SystemExit(f"{path}: no {', '.join(sorted(missing))}")
    module = ast.Module(body=[found[n] for n in names], type_ignores=[])
    exec(compile(module, path, "exec"), namespace)
    return {n: namespace[n] for n in names}


def load_game(game):
    module, _, client, server = GAMES[game]
    sim = make_schemas.load(game)
    folder = make_schemas.game_folder(game)  # (the working folder's game, or the public repository's games/<game>)
    from engine import schema
    try:
        from engine import hud
        swatches = hud.SWATCHES
    except Exception:  # (no Panda3D GUI here: the colour blocks only decide the garage's custom block)
        swatches = []
    ns = {"schema": schema, "sim": sim, "TEACHER": False, "SWATCHES": swatches, "RED": "red", "ORANGE": "orange",
          "GREEN": "green", "GREY": "grey",
          "kh": SimpleNamespace(check_design=lambda d, limits=None: list(sim.check_design(d, limits)))}
    if game == "kartlab":  # (the kart window's stats readout is kart_hud's)
        import kart_hud
        ns["kh"].stats_text = kart_hud.stats_text
    names = ["code_ctx", "outside_limits", "apply_code", "update_stats_text"] + \
        (["code_weapons"] if game == "robotlab" else [])
    fns = methods(os.path.join(folder, client), names, ns)
    sns = {"sim": sim, "cpu_brains": SimpleNamespace(LEVELS={}), "MAX_KARTS": 8,
           "kart_track": SimpleNamespace(TRACKS={})}
    rules = methods(os.path.join(folder, server), ["rules"], sns)["rules"]

    class Window:  # a window with nothing on screen: what apply_code and code_ctx read and set
        def __init__(self, design, rules, tools, limits, who=None, lines=(), makers=None):
            self._design, self.rules, self._tools, self._limits, self._who = design, rules, tools, limits, who
            self.schema = sim.schema()
            self.mod_info = {"makers": makers} if makers is not None else None
            self.code_state = {"lines": list(lines), "cursor": [0, 0], "scroll": 0}
            self.entry_text, self.entries, self.custom_colour = {}, {}, None
            self.code_msg, self.code_shown, self.code_changed, self.code_hack = None, None, False, False

        def cur(self): return self._design
        def tools(self): return self._tools
        def limits(self): return self._limits
        def viewing(self): return self._who
        def code_rows(self): return 19
        def refresh_code_panel(self): pass
        def rebuild_panels(self): pass
        def name_key(self): return "name"
        def set_entry(self, key, value): pass

    for name, f in fns.items():
        setattr(Window, name, f)
    the_rules = json.loads(json.dumps(rules(None)))  # (as the window gets them: through JSON)
    return SimpleNamespace(game=game, sim=sim, schema=schema, ns=ns, Window=Window, rules=the_rules)


# ---------- Python's values, written so that JavaScript's can be compared with them ----------
def enc(v):
    if v is None:
        return ["None"]
    if v is Ellipsis:
        return ["Ellipsis"]
    if isinstance(v, bool):
        return ["bool", v]
    if isinstance(v, int):
        return ["int", str(v)]
    if isinstance(v, float):
        return ["float", repr(v)]
    if isinstance(v, complex):
        return ["complex", repr(v.real), repr(v.imag)]
    if isinstance(v, str):  # (a lone surrogate, "\ud83e" in the code, as its code points: JSON would join a pair)
        return ["strcp", [ord(c) for c in v]] if any(0xD800 <= ord(c) <= 0xDFFF for c in v) else ["str", v]
    if isinstance(v, bytes):
        return ["bytes", list(v)]
    if isinstance(v, list):
        return ["list", [enc(x) for x in v]]
    if isinstance(v, tuple):
        return ["tuple", [enc(x) for x in v]]
    if isinstance(v, (set, frozenset)):
        return ["set", [enc(x) for x in v]]
    if isinstance(v, dict):
        return ["dict", [[enc(k), enc(x)] for k, x in v.items()]]
    return ["other", repr(v)]


def same(a, b):
    """Equal, with a set's items in any order."""
    if isinstance(a, list) and isinstance(b, list) and len(a) == 2 and len(b) == 2 and a[0] == b[0] == "set":
        return len(a[1]) == len(b[1]) and all(any(same(x, y) for y in b[1]) for x in a[1])
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, float) or isinstance(b, float):
        return a == b
    return a == b and type(a) is type(b) or (isinstance(a, (int, float)) and isinstance(b, (int, float))
                                              and not isinstance(a, bool) and not isinstance(b, bool) and a == b)


def outcome(f):
    """What a call gives: its value, the code panel's error (line, words), or a crash (an exception the app doesn't
    catch: only that it crashed is compared)."""
    try:
        return {"ok": f()}
    except Exception as e:
        if type(e).__name__ == "ParseError":
            return {"error": [e.lineno, e.message]}
        return {"crash": f"{type(e).__name__}: {e}"}


# ---------- what the cases are made from ----------
# names with characters beyond the first 65536 (emoji): the code writes each as one \UXXXXXXXX escape and must read
# it back as one character (it used to be json's two surrogates: the name always looked changed, and counted double)
EMOJI = ["🤖", "🤖 Bot", "😀 smile 🚀", "🤖" * 8, "🤖" * 17, "a🤖b🤖c🤖d🤖e🤖f🤖", "𝔘𝔫𝔦𝔠𝔬𝔡𝔢", "\\🤖", "é🤖\t🦀"]
NAMES = ["Robot", "Fighter", "Kart", "Bob", "Zoë", "Sam's bot", 'Say "hi"', "back\\slash", "tab\there", "🤖 Emoji",
         "a-very-long-hyphenated-name-for-a-robot", "x" * 30, "", " spaced ", "日本語", "line\nbreak", "ünïcödé-ẞ",
         "a—dash", "well-made", "--", "ﬁne", "café\u0301", "\u00a0nbsp", "C:\\path", "{name}", "%d", "None"] + EMOJI
EMOJI_LITERALS = ['"\\U0001f916 Bot"', '"\\ud83e\\udd16"', '"\\ud83e" "\\udd16"', '"🤖"', '"\\N{NO NAME}🤖"']
SYNTAX_LINES = [
    "x: int = 5 5", "x: int = ", "x = [1, 2, 3", "x = [1, 2 3]", 'x = "abc', "x = 'abc", "x: int = 1OO", "x: int = 007",
    "x: int = 25 +", 'x: str == "a"', "x = (1, 2]", "x = 1, 2]", "x = ]", "x = [1,, 2]", "x: list = [1 2 3]",
    "x int = 5", "x: = 5", "5 = x", '"a" = 1', "x: int = 5:", 'print("hi"', 'x = "a" "b"', "if x:", "x = 1e",
    "x = 0x", "x = 1_", "x = $", "x = [1, 2]]", "x = (", "x = {", "x = weapons[", "x = weapons[]",
    'robot name: str = "a"', "x: int = 5.5.5", "def", "x = a b", "x = not", 'x = """abc', "x = 5 = 6", "x = = 5",
    "x == 5", "x = 0b2", "x = 09", "x = 0o8", "x = 1j2", "x = .", "x = 5.e", "x = \u00a35", "x: int = \u22125",
    ")", "x = 5)", "x = {1: 2", "x = 1 if", "x =- 5", "x = - ", "x = True False", "x: int = 05", "x = 1\\",
    "x = 1 \\ 2", "x: str = 'it's'", "x: int = 5;;", ";", "x: list = [1, 2, 3)", 'x = "a\\"', "f() = 5",
    "x + 1 = 5", "[1] = 5", "True = 5", "None: int = 5", "[x]: int = 5", "x, y: int = 5", "x = [a = 1]",
    "x = [1 = 2]", "x = f(1 = 1)", "x = f(a = 1)", "x = {a = 1}", "x = 1 if 2", 'print "hi"', "print 5",
    "x = 5\x01", "\ufeffx = 5", "x\u00a0= 5", "x = [match 1]", 'x = ["a" b]', "x = f(1 2)", "x = w[1 2]",
    "if x: y = 1", "for x in y:", "while x:", "def f():", "class A:", "try:", "else: x = 1", "x = 1; y = 2",
    "import os", "x = a.5", "x = 5.a", "x = 1e5e5", "x = 5L", "x = 1and 2", "x = 1else", "x = 5\u00e9",
    "x = \u00e95", "x = 00", "x = 0_0", 'x = "a" b"b"', 'x = ur"a"', 'x = f"{1}"', 'x = "\\x"', 'x = "\\u12"',
    'x = "\\N{NO SUCH NAME}"', 'x = "\\N{"', 'x = "\\N"', 'x = "\\N{}"','x = b"\u00e9"', 'x = "\\777"', 'x = "\\q"', "x = ...", "x = *a", "x: int = *a", "del x",
    "x = lambda: 1", "x = yield", "x = await y", "x = {**a}", "x = {1, 2}", "x = set()", "x = (1,)", "x = 1+2j",
    "x = -1-2j", "x = 2 ** 3", "x = -(5)", "x = +-5", "x = --5", "x = ~5", "x = not 5", "x = -True",
    "x = [1, [2, [3]]]", "x = {'a': [1, 2]}", "x = {[1]: 2}", "x = {[1], 2}", "x = b'\\x4'", "x = b'\\x41'",
    "x: list = [255, 0, 0", "weapon: str = weapons[0", "weapon: str = weapons]0]", "weapon: str = weapons(0)",
    "x = [\n1\n2\n]", "x = [1,\n2 3]", 'x = """a\nb"""', "x = (1\\\n2)", "x = 1\\\n\ny = 2", "if x:\ny = 1",
    "try: pass", "with a: pass", "async x", "x = 1 2 3 4", "x = 0x1for", "x: int = 5 = 6", "5: int = 5",
    "(x): int = 5", "f(): int = 5", "x.y = 5", "x[0] = 5", "x += 1", "x, y = 1, 2", "x = y = 1", "(x) = 5",
    "x: int", "x = [1, 2,]", "x = [*a]", "x = f(**a, b)", "x = f(a=1, b)", "x = f(x for x in y, 1)",
    "x = [x for x in y]", "x = [*a for a in b]", "x = {**a for a in b}", "x = [a, b for a in c]", "x = (*a)",
    "x = (**a)", "x = {1: *a}", "x = {1:}", "x = {1 2}", "x = {1: 2 3}", "x = [1 if 2 else 3]", "x = f(True=1)",
    "x = f(a=1 for b in c)", "x = f(a=)", "from . import (a, b,)", "from x import a,", "import a.b as c",
    "global x, y", "nonlocal x", "assert x, y", "raise X from Y", "return", "type X = int", "type: int = 5",
    "match = 5", "match x:", "case = 1", "_ = 5", "x = [i for i in range(3) if i]", "@dec\ndef f(): pass",
    "x = a if b else c", "x = a or b and not c", "x = 1 < 2 <= 3 != 4 is not 5 not in 6", "x = a[1:2, ::3]",
    "x = a.b.c(d)[e]", "x = f(*a, **b)", "x = (yield)", "x = ((((1))))", "x = [[[[[]]]]]", "x = {}", "x = ()",
    "x = []", "x = ''", 'x = r"\\n"', "x = rb'\\x'", "x = 1_000_000", "x = 0o17", "x = 0b101", "x = 0XFF",
    "x = 1e308 * 10", "x = 1e999", "x = -1e999", "x = 0.1", "x = .5", "x = 5.", "x = 1E5", "x = 12345678901234",
    "x = 3.14159265358979", "x = 1/3", "x = 2.5e-7", "x = 100.0", "x = -0.0", "x = -0", "x = 007.5",
    # f-strings (Python 3.12 reads them as tokens of their own)
    'x = f"abc', 'x = f"{1', 'x = f"{1}', 'x = f"{1}"', 'x = f"{"a"}"', 'x = f"{1\n}"', 'x = f"{1 #c}"', 'x = f"}"',
    'x = f"{}"', 'x = f"{$}"', 'x = f"{1!x}"', 'x = f"{1!}"', 'x = f"{1:{2}}"', 'x = f"{1=}"', 'x = f"{1 2}"',
    'x = f"{{"', 'x = f"}}"', 'x = f"""a\nb', 'x = f"{x"', "x = f'{x'", 'x = f"{(}"', 'x = f"{1}" "a"', 'x = f"\\{"',
    'x = f"{lambda: 1}"', 'x = f"{1:\n}"', 'x = f"{1!r:>5}"', 'x = f"{*a}"', 'x = f"{a b}"', 'x = f"{1:{}}"',
    'x = f"{1}}"', 'x = rf"{1}\\d"', 'f"{1"', 'x = f"{1:abc', 'x = f"{x:=1}"', 'x = f"{1}" b"x"', "x f'=] \\x'",
    'x = f"{[1,\n2 3]"', 'x = f"{1:{x=}\ny"', 'x = f"{1! r}"', 'x = f"\\x{1}"', 'x = f"{1:\\x}"', 'x = f"{x!r=}"',
    'robot_name: str = f"Bot {5}"', "robot_name: str = f'{robot_name}'", 'x = f"{{{1}}}"', 'x = f"{1}{{"',
    # parameters, decorators, type parameters
    "x = lambda *: 1", "x = lambda a=1, b: 1", "x = lambda *a=1: 1", "x = lambda **k, a: 1", "x = lambda (a): 1",
    "x = lambda a, /, /: 1", "x = lambda *a, *b: 1", "def f(*): pass", "def f(a=1, b): pass", "def f(a=): pass",
    "def f((a)): pass", "def f(a, *, /): pass", "def f[T](x: T) -> T: pass", "def x [", "class C[T]: pass",
    "type X[T] = list", "type X[*T: int] = 1", "x = f(x for x in y, 1", "x = f(x for x in y, 1)", "x = f(a, b for b in c)",
    # lines a \r splits (Python reads a \r as a line end, and the rest of that line can be indented)
    "x = 1\r  y = 2", "if x:\r  y = 1", "if x:\r  y = 1\r z = 2", "if x:\r\ty = 1\r        z = 2", "match x:\r  case 1: pass",
    "x = 1\ry = 2", "x = [1,\r 2]", "x = 1\r\r\ry",
]
SOUP = ["x", "weapon", "weapons", "print", "match", "ma", "type", "_", "if", "else", "for", "in", "not", "and", "None",
        "True", "lambda", "yield", "await", "0", "25", "007", "1.5", "1e5", "0x1F", "2j", "'a'", '"b"', "b'd'", "f'e'",
        'f"{', "}", "{x=}", "!r", "=", "==", ":", ":=", ",", ";", ".", "...", "+", "-", "*", "**", "/", "@", "(", ")",
        "[", "]", "{", "\n", "#c", "\\", "\r  ", "!", "$", "é", "\u00a0", "def f(", "class", "[T]"]
LITERALS = ["0", "1", "5", "25", "50", "99", "100", "101", "150", "200", "250", "255", "256", "300", "400", "401",
            "-1", "-5", "-0", "+5", "- 5", "5.0", "55.5", "100.0", "12.5", "0.5", "1e2", "1e-5", "1e999", "-1e999",
            "99999999999999999999", "True", "False", "None", '"wedge"', '"drum"', "'spinner'", '"laser"', '"flame"',
            '"BLAZE"', '"VORTEX"', '"Mine"', '"GOLIATH"', '"robot"', '"woman"', '"robin"', '"boxer"', '"swords"',
            '"katana"', '"knife"', '"blast"', '"slam"', '"uppercut"', '"Bob"', '"Zoë"', '"a very long robot name"',
            '"it\'s"', "'say \"hi\"'", '"\\u00e9"', '"\\n"', '"tab\\t"', '"🤖"', '""', "b'x'", '"a" "b"',
            "[255, 0, 0]", "[0, 0, 0]", "[256, 0, 0]", "[-1, 0, 0]", "[255, 0]", "[255, 0, 0, 0]", "[1.0, 2, 3]",
            "[True, 0, 0]", "(255, 0, 0)", "[\"punch\", \"kick\"]", "['punch', 'punch', 'kick']", "['low', 'high']",
            "['punch', 'jump']", "[]", "['punch']", "['punch'] * 3", "[1, 2, 3]", "{'a': 1}", "{1, 2}", "set()",
            "1+2j", "2j", "weapon", "x", "5 + 5", "int(5)", "-(-5)", "abs(-5)", "[i for i in range(3)]",
            "f'{1}'", "...", "(1)", "(1,)", "[[1, 2, 3]]", "weapons[0]", "weapons[1]", "weapons[-1]", "weapons[99]",
            "weapons[-99]", "weapons['a']", "weapons[1.0]", "weapons[True]", "weapons[0:1]", "weapons[0, 1]",
            "weapons[x]", "weapons[0][0]", "specials[0]", "specials[2]", "specials[9]", "specials[-1]", "weapons()",
            "weapons.x"]
CHARS = list("\"'[](){},:=#\\ 0123456789abcdefgxyz.+-*_;\t\n") + ["é", "£", "\u00a0", "\r", "\x00", "🤖", "\u2212"]


def random_name(r):
    return r.choice(NAMES) if r.random() < 0.7 else "".join(r.choice("abcXYZ 09-'\"\\_é") for _ in range(r.randint(0, 20)))


def random_number(r, lo, hi, floats=True):
    p = r.random()
    if p < 0.6:
        return r.randint(int(lo), int(hi))
    if p < 0.75 and floats:  # (never 49.0: JSON brings that to the browser as 49, so schema.js can't know it was a float)
        x = round(r.uniform(lo, hi), r.choice([1, 2, 5]))
        return x + 0.5 if x == int(x) else x
    if p < 0.85:
        return r.choice([lo, hi, int(hi) + 1, int(lo) - 1])
    return r.choice([0, -5, 1000, 12.5, 1e-5, 123456789]) if floats else r.choice([0, 1000, 123456789])


def random_design(g, r):
    sim = g.sim
    if g.game == "kartlab":
        d = sim.default_design(random_name(r), (r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)))
        for k in sim.STATS:
            if r.random() < 0.6:
                d[k] = random_number(r, 0, 100, floats=False)
        if r.random() < 0.05:
            d.pop(r.choice(list(d)))
        return d
    if g.game == "robotlab":
        weapon = r.choice(list(sim.WEAPONS) + list(sim.HOUSE_WEAPONS) + ["nothing"])
        d = sim.default_design(random_name(r), (r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)), weapon)
        if r.random() < 0.25:
            d["model"] = r.choice([n for n, *_ in sim.HOUSE_ROBOTS] + ["NOBODY"])
    else:
        d = sim.default_design(random_name(r), (r.randint(0, 255), r.randint(0, 255), r.randint(0, 255)),
                               r.choice(list(sim.SPECIALS) + ["nothing"]), r.choice(list(sim.BODIES)))
        d["fighting_style"] = r.choice(list(sim.STYLES) + ["dancer"])
        weapons = sim.weapons_for(d["fighting_style"])
        if weapons and r.random() < 0.9:
            d["weapon"] = r.choice(weapons + ["spoon"])
        elif r.random() < 0.2:
            d["weapon"] = "knife"
        d["combo"] = [r.choice(list(sim.COMBO_MOVES) + ["jump"]) for _ in range(r.randint(0, 6))]
        if r.random() < 0.2:
            d["model"] = r.choice(list(sim.BOSS_BY_NAME) + ["NOBODY"])
        if r.random() < 0.1:
            d.pop("look", None)
    for k, v in sim.SETTINGS.items():
        if r.random() < 0.6:
            d["settings"][k] = random_number(r, 0, 200)
    for k in sim.STATS:
        if r.random() < 0.6:
            d["points"][k] = random_number(r, 0, 100, floats=r.random() < 0.3)
    if r.random() < 0.05:
        d["settings"].pop(r.choice(list(d["settings"])))
    return d


def standard_designs(g):
    sim = g.sim
    if g.game == "kartlab":
        return [sim.default_design()]
    if g.game == "robotlab":
        return [sim.default_design()] + [sim.default_design("Robot", (200, 120, 40), w) for w in sim.WEAPONS] + \
            [dict(sim.default_design(), model=n) for n, *_ in sim.HOUSE_ROBOTS]
    return [sim.default_design()] + [sim.default_design("Fighter", (200, 120, 40), s, b)
                                     for s in sim.SPECIALS for b in sim.BODIES]


def random_tools(g, r):
    sim, tools = g.sim, {}
    for v in sim.schema():
        if v.tool and r.random() < 0.6:
            tools[v.tool] = r.random() < 0.7
    for extra in ("code_view", "points_table", "name_and_colour"):
        if r.random() < 0.5:
            tools[extra] = r.random() < 0.8
    if g.game == "robotlab" and r.random() < 0.8:
        tools["weapons"] = r.sample(list(sim.WEAPONS), r.randint(0, len(sim.WEAPONS)))
    if g.game == "fightlab" and r.random() < 0.8:
        tools["specials"] = r.sample(list(sim.SPECIALS), r.randint(0, len(sim.SPECIALS)))
    return tools


def random_limits(g, r):
    sim = g.sim
    p = r.random()
    if p < 0.3:
        return sim.default_limits()
    if p < 0.45:
        return sim.full_limits()
    new = {"settings": {}, "points": {}}
    full = sim.full_limits()
    for k, (lo, hi) in full["settings"].items():
        a, b = r.uniform(lo, hi), r.uniform(lo, hi)
        new["settings"][k] = [round(a) if r.random() < 0.7 else round(a, 1), round(b) if r.random() < 0.7 else round(b, 1)]
    for k, (lo, hi) in full["points"].items():
        new["points"][k] = [r.randint(lo, hi), r.randint(lo, hi)]
    new["points_total"] = r.randint(0, full["points_total"])
    return sim.clean_limits(new)


def mutate(lines, r, g):
    """A learner's edit of the code: one of the ways the code gets changed (or broken)."""
    lines = list(lines)
    op = r.randrange(17)
    if op == 16:  # a line of anything: the tokens Python's grammar knows, in any order
        lines.insert(r.randint(0, len(lines)), " ".join(r.choice(SOUP) for _ in range(r.randint(1, 10))))
        return "\n".join(lines).split("\n")
    code = [i for i, line in enumerate(lines) if line and not line.startswith("#")]
    if op == 0 or not lines:
        return lines
    if op in (1, 2, 3) and code:  # a value changed
        i = r.choice(code)
        head = lines[i].split("=", 1)[0]
        lines[i] = head + "= " + r.choice(LITERALS)
        return lines
    if op == 4:  # the comments taken out
        return [line for line in lines if not line.startswith("#")]
    if op == 5:  # the types taken out
        return [line.replace(": int =", " =").replace(": str =", " =").replace(": list =", " =").replace(": float =", " =")
                for line in lines]
    if op == 6:  # spaces, tabs, blank lines, Windows line ends
        return [r.choice(["  ", "\t", "", " \r", "\u00a0"]) + line + r.choice(["", "  ", "\r", "\t", "\u3000"])
                for line in lines] + [""] * r.randint(0, 2)
    if op == 7:  # a variable that isn't one
        lines.insert(r.randint(0, len(lines)), r.choice(["speed = 5", "colour_name: str = \"red\"", "x = [1, 2]",
                                                        "weapons: list = [\"drum\", \"wedge\"]", "ROBOT = 5",
                                                        "FIGHTER = {}", "specials = ['slam']", "__proto__ = 1",
                                                        "constructor = 2", "toString = 3"]))
        return lines
    if op in (8, 9):  # a broken line
        line = r.choice(SYNTAX_LINES)
        if op == 8 or not code:
            lines.insert(r.randint(0, len(lines)), line)
        else:
            lines[r.choice(code)] = line
        return "\n".join(lines).split("\n")
    if op in (10, 11, 12):  # typing slips: a character or three deleted, added or changed
        text = "\n".join(lines)
        for _ in range(r.randint(1, 3)):
            if not text:
                break
            at = r.randrange(len(text) + 1)
            kind = r.randrange(3)
            if kind == 0 and at < len(text):
                text = text[:at] + text[at + 1:]
            elif kind == 1:
                text = text[:at] + r.choice(CHARS) + text[at:]
            elif at < len(text):
                text = text[:at] + r.choice(CHARS) + text[at + 1:]
        return text.split("\n")
    if op == 13 and len(code) > 1:  # lines swapped, or one twice
        i, j = r.sample(code, 2)
        if r.random() < 0.5:
            lines[i], lines[j] = lines[j], lines[i]
        else:
            lines.insert(j, lines[i])
        return lines
    if op == 14 and code:  # several on one line
        i = r.choice(code)
        j = min(len(lines), i + r.randint(1, 4))
        return lines[:i] + ["; ".join(lines[i:j])] + lines[j:]
    if op == 15 and code:  # a list over several lines
        i = r.choice(code)
        lines[i] = lines[i].replace(", ", ",\n").replace("[", "[\n", 1)
        return "\n".join(lines).split("\n")
    return lines


# ---------- the cases ----------
def build_cases(seed, count):
    r = random.Random(seed)
    cases, expected = [], []
    games = {g: load_game(g) for g in GAMES}

    def add(case, result):
        cases.append(case)
        expected.append(result)

    for name, g in games.items():
        sim, schema = g.sim, g.schema
        designs = standard_designs(g) + [random_design(g, r) for _ in range(count)]
        for n, d in enumerate(designs):
            tools = random_tools(g, r) if n else {}
            limits = random_limits(g, r) if n else sim.default_limits()
            who = r.choice([None, None, None, "Sam", "zoë"])
            makers = r.choice([None, {}, {"flame": "Sam", "laser": "Ann"}])
            teacher = r.random() < 0.2
            g.ns["TEACHER"] = teacher
            win = g.Window(copy.deepcopy(d), g.rules, tools, limits, who, makers=makers)
            ctx = win.code_ctx()
            spec = {"rules": g.rules, "tools": tools, "limits": limits, "design": d, "who": who,
                    "makers": makers if makers is not None else {}}  # (what codeCtx is given: the window's mod_info)
            # 1. the code as the window writes it
            lines = outcome(lambda: schema.code_lines(win.schema, d, ctx))
            ctx_seen = {k: v for k, v in vars(ctx).items() if k not in ("rules", "design")}
            add({"kind": "lines", "game": name, "design": d, "spec": spec},
                {"lines": lines, "ctx": json.loads(json.dumps(ctx_seen))})
            text_lines = lines.get("ok") or ["x = 1"]
            # 2. the code read back, as written and edited
            for _ in range(6):
                edited = mutate(text_lines, r, g)
                text = "\n".join(edited)
                got = outcome(lambda: [[k, enc(v)] for k, v in schema.parse_code(text, win.schema, ctx).items()])
                add({"kind": "parse", "game": name, "text": text, "spec": spec}, got)
            # 3. APPLY CODE, start to end
            for _ in range(2):
                edited = mutate(text_lines, r, g) if r.random() < 0.8 else text_lines
                cur = copy.deepcopy(d)
                win = g.Window(cur, g.rules, tools, limits, who, lines=edited, makers=makers)
                res = outcome(lambda: win.apply_code())
                result = {"result": res, "msg": list(win.code_msg) if win.code_msg else None, "design": cur,
                          "changed": win.code_changed, "hack": win.code_hack}
                add({"kind": "apply", "game": name, "design": d, "text": "\n".join(edited), "spec": spec,
                     "teacher": teacher}, json.loads(json.dumps(result)))
            # 4. the design checks and the limits' room for the code
            add({"kind": "check", "game": name, "design": d, "limits": limits},
                outcome(lambda: sim.check_design(copy.deepcopy(d), limits)))
            add({"kind": "room", "game": name, "limits": limits},
                outcome(lambda: [sim.code_limits(limits), sim.default_limits(), sim.full_limits()]))
            # 5. the Warnings tab: what changed that the lesson's garage doesn't let them change
            other = random_design(g, r)
            add({"kind": "lesson", "game": name, "old": d, "new": other, "tools": tools},
                outcome(lambda: schema.outside_lesson(sim.schema(), d, other, tools)))
            # 6. the garage's tables, and its stats readout (the window's own update_stats_text)
            win = g.Window(copy.deepcopy(d), g.rules, tools, limits, who)
            win.stats_text = SimpleNamespace(text="")
            win.stats_text.setText = lambda t, box=win.stats_text: setattr(box, "text", t)
            win.update_stats_text()
            if all(not isinstance(v, (int, float)) or v >= 0 for v in d.get("settings", {}).values()):
                # (a negative size: Python's readout shows complex numbers, "Walk 0.0-10.2j m/s"; the page's is blank)
                add({"kind": "stats", "game": name, "design": d}, win.stats_text.text)
            view, teach = r.random() < 0.2, r.random() < 0.2
            add({"kind": "garage", "game": name, "design": d, "spec": spec, "view": view, "teacher": teach},
                outcome(lambda: garage_model(g, d, ctx, tools, limits, view, teach)))
        # 6b. an emoji name: APPLY CODE on the code as written changes nothing (the round trip is exact, in Python
        # itself), and the name is cut to its length as Python counts it
        g.ns["TEACHER"] = False

        def spec_of(design):
            return {"rules": g.rules, "tools": {}, "limits": sim.default_limits(), "design": design, "who": None, "makers": {}}
        for e in EMOJI:
            d = sim.default_design() | {"name": e}
            win = g.Window(copy.deepcopy(d), g.rules, {}, sim.default_limits())
            lines = schema.code_lines(win.schema, d, win.code_ctx())
            cur = copy.deepcopy(d)
            win = g.Window(cur, g.rules, {}, sim.default_limits(), lines=lines)
            res = outcome(lambda: win.apply_code())
            longest = [v.max_len for v in win.schema if v.kind == "str"][0]
            if len(e) <= longest and (win.code_changed or cur != d):  # (a longer one is cut to the longest, as it should be)
                raise SystemExit(f"{name}: APPLY CODE on unchanged code changed {e!r} (the emoji round trip)")
            add({"kind": "apply", "game": name, "design": d, "text": "\n".join(lines), "spec": spec_of(d), "teacher": False},
                json.loads(json.dumps({"result": res, "msg": list(win.code_msg) if win.code_msg else None, "design": cur,
                                       "changed": win.code_changed, "hack": win.code_hack})))
            for lit in EMOJI_LITERALS:  # (typed in the code: one character or two, as Python reads them)
                text = "\n".join(lines + [f"{[v.name for v in win.schema if v.kind == 'str'][0]}: str = {lit}"])
                won = g.Window(sim.default_design(), g.rules, {}, sim.default_limits(), lines=text.split("\n"))
                res = outcome(lambda: won.apply_code())
                add({"kind": "apply", "game": name, "design": sim.default_design(), "text": text,
                     "spec": spec_of(sim.default_design()), "teacher": False},
                    json.loads(json.dumps({"result": res, "msg": list(won.code_msg) if won.code_msg else None,
                                           "design": won.cur(), "changed": won.code_changed, "hack": won.code_hack})))
        # 7. every broken line alone, and each in a robot's code
        ctx = g.Window(sim.default_design(), g.rules, {}, sim.default_limits()).code_ctx()
        spec = {"rules": g.rules, "tools": {}, "limits": sim.default_limits(), "design": sim.default_design(), "who": None,
                "makers": {}}
        base = schema.code_lines(sim.schema(), sim.default_design(), ctx)
        for line in SYNTAX_LINES + [f"weapon: str = {x}" for x in LITERALS] + [f"special: str = {x}" for x in LITERALS]:
            for text in (line, "\n".join(base[:12] + [line] + base[12:]), "\n".join(base + [line])):
                got = outcome(lambda: [[k, enc(v)] for k, v in schema.parse_code(text, sim.schema(), ctx).items()])
                add({"kind": "parse", "game": name, "text": text, "spec": spec}, got)
    # 8. the number and text formats the code is written with
    for _ in range(count * 4):
        x = r.choice([r.uniform(-1000, 1000), r.uniform(0, 1), 10 ** r.uniform(-12, 22), r.randint(-10 ** 6, 10 ** 7),
                      round(r.uniform(0, 300), r.randint(0, 6)), r.choice([0.5, 2.5, 1234565, 12.03125, 1e16, 1e-5,
                                                                           0.0001, 1e21, 123456.5, 999999.5])])
        x = float(x) if r.random() < 0.7 else int(x)
        add({"kind": "format", "x": x, "float": isinstance(x, float)},
            {"g": format(x, "g"), "repr": repr(x), "json": json.dumps([x, str(x)])})
    for _ in range(count * 2):
        words = [r.choice(NAMES + ["the", "a", "well-known", "re-entry", "x" * r.randint(1, 70), "--", "e-mail",
                                   "[255, 0, 0]", "\"text\"", "one—two"]) for _ in range(r.randint(1, 25))]
        text = " ".join(words)
        add({"kind": "wrap", "text": text}, textwrap.wrap(text, 60))
    return cases, expected


def garage_model(g, d, ctx, tools, limits, view, teacher):
    """engine.garage.draw's decisions, as data: which rows, what they say, which buttons."""
    from engine.schema import shown  # noqa: F401  (the same module the garage uses)
    schema = g.sim.schema()

    def can_change(var, value=None):  # engine.garage.can_change
        if var.tool and not tools.get(var.tool):
            return False
        if var.allowed_values and value is not None:
            return value in var.allowed_values(tools)
        return True

    def visible(var):
        if var.unless and var.unless(d):
            return False
        return bool(view or teacher or var.always or not var.tool or tools.get(var.tool))

    out = {"strings": [], "lists": [], "settings": [], "points": None}
    for v in [v for v in schema if v.garage == "strings" and visible(v)]:
        value = v.get(d)
        row = {"name": v.name, "value": value}
        if v.kind == "str":
            row["text"] = str(value or "")
        else:
            row["text"] = f'"{value}"' if value is not None else f'"{v.none_text}"' if v.none_text else '""'
        if v.kind == "choice":
            allowed = view or teacher or can_change(v)
            if allowed and not (v.fixed and v.fixed(d)):
                options = list(v.options(ctx)) if v.options else []
                if v.optional:
                    options = [None] + options
                row["choose"] = [[o, v.none_text if o is None else str(o).replace("_", " "), o == value] for o in options]
            else:
                row["chosenByTeacher"] = True
        if v.describe:
            row["describe"] = v.describe(ctx, d) or None
        out["strings"].append(row)
    for v in [v for v in schema if v.garage == "lists" and visible(v)]:
        value = v.get(d)
        if v.kind == "rgb":
            c = list(value or [0, 0, 0])
            text = f"{v.name}: list = [{c[0]}, {c[1]}, {c[2]}]"
        elif v.kind == "words":
            text = f"{v.name}: list = {list(value or [])}".replace("'", '"')
        else:
            text = f"{v.name}: list = {value}".replace("'", '"')
        out["lists"].append({"name": v.name, "value": value, "text": text})
    points = [v for v in schema if v.group == "points" and visible(v)]
    if points:
        used = sum(v.get(d) or 0 for v in points)
        out["points"] = {"total": limits["points_total"], "used": used, "over": used > limits["points_total"],
                         "rows": [{"name": v.name, "stat": v.path[-1], "value": v.get(d),
                                   "most": max(1, limits["points"][v.path[-1]][1])} for v in points]}
    for v in [v for v in schema if v.group == "settings" and visible(v)]:
        k, value = v.path[-1], v.get(d)
        lo, hi = limits["settings"][k]
        out["settings"].append({"name": v.name, "key": k, "value": value, "lo": lo, "hi": hi, "fixed": lo >= hi,
                                "text": f"{value:g}%"})
    return json.loads(json.dumps(out))


# ---------- schema.js's side, in Node ----------
RUNNER = r"""
import fs from "fs";
import * as S from "./schema.mjs";
const [schemasPath, casesPath, outPath] = process.argv.slice(2);
const schemas = JSON.parse(fs.readFileSync(schemasPath, "utf8"));
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
function enc(v) {
    if (v === null || v === undefined) return ["None"];
    if (v === S.ELLIPSIS) return ["Ellipsis"];
    if (typeof v === "boolean") return ["bool", v];
    if (typeof v === "number") return ["int", Number.isSafeInteger(v) ? String(v) : BigInt(v).toString()];
    if (typeof v === "bigint") return ["int", v.toString()];
    if (v instanceof S.PyFloat) return ["float", S.floatRepr(v.v)];
    if (v instanceof S.PyComplex) return ["complex", S.floatRepr(v.re), S.floatRepr(v.im)];
    if (typeof v === "string") return ["str", v];
    if (v instanceof S.PyStr) return ["strcp", v.cps];
    if (v instanceof S.PyBytes) return ["bytes", v.bytes];
    if (Array.isArray(v)) return ["list", v.map(enc)];
    if (v instanceof S.PyTuple) return ["tuple", v.items.map(enc)];
    if (v instanceof S.PySet) return ["set", v.items.map(enc)];
    if (v instanceof S.PyDict) return ["dict", [...v.map.values()].map(([k, x]) => [enc(k), enc(x)])];
    return ["other", String(v)];
}
function outcome(f) {
    try { return {ok: f()}; }
    catch (e) {
        if (e instanceof S.ParseError) return {error: [e.lineno, e.message]};
        return {crash: `${e.constructor.name}: ${e.message}`};
    }
}
const clone = x => JSON.parse(JSON.stringify(x));
const colours = {red: "red", orange: "orange", green: "green"};
function run(c) {
    const G = schemas[c.game];
    const ctxOf = spec => S.codeCtx(G, {...spec, design: spec.design});
    switch (c.kind) {
        case "lines": {
            const spec = clone(c.spec), ctx = ctxOf(spec);
            const seen = {};
            for (const [k, v] of Object.entries(ctx)) if (k !== "rules" && k !== "design") seen[k] = v;
            return {lines: outcome(() => S.codeLines(G, clone(c.design), ctx)), ctx: seen};
        }
        case "parse": {
            const spec = clone(c.spec);
            return outcome(() => Object.entries(S.parseCode(G, c.text, ctxOf(spec))).map(([k, v]) => [k, enc(v)]));
        }
        case "apply": {
            const spec = clone(c.spec), cur = clone(c.design);
            spec.design = cur;
            const ctx = S.codeCtx(G, spec);
            let res;
            try {
                res = S.applyCode(G, cur, c.text, {ctx, tools: spec.tools, limits: spec.limits, teacher: c.teacher, viewing: spec.who});
            } catch (e) {
                return {result: {crash: String(e)}, msg: null, design: cur, changed: false, hack: false};
            }
            // (the window: True when all of it was used, False when refused, None when the code couldn't be read)
            let ok;
            if (res.lineno !== undefined || res.message.startsWith("The code is now")) ok = null;
            else ok = res.ok;
            return {result: {ok}, msg: [res.message, colours[res.colour]], design: cur,
                    changed: Boolean(res.codeChanged), hack: Boolean(res.codeHack)};
        }
        case "check": return outcome(() => S.checkDesign(G, clone(c.design), c.limits));
        case "room": return outcome(() => [S.codeRoom(G, c.limits), S.defaultLimits(G), S.fullLimits(G)]);
        case "lesson": return outcome(() => S.outsideLesson(G, c.old, c.new, c.tools));
        case "garage": {
            const spec = clone(c.spec), ctx = ctxOf(spec);
            return outcome(() => {
                const t = S.garageTables(G, clone(c.design), ctx, spec.tools, spec.limits, {view: c.view, teacher: c.teacher});
                const strings = t.strings.map(row => {
                    const out = {name: row.name, value: row.value, text: row.text};
                    if (row.choose) out.choose = row.choose.map(o => [o.value, o.text, o.on]);
                    if (row.chosenByTeacher) out.chosenByTeacher = true;
                    if ("describe" in row) out.describe = row.describe;
                    return out;
                });
                const lists = t.lists.map(row => ({name: row.name, value: row.value, text: row.text}));
                const settings = t.settings.map(s => ({name: s.name, key: s.key, value: s.value, lo: s.lo, hi: s.hi, fixed: s.fixed, text: s.text}));
                const points = t.points && {total: t.points.total, used: t.points.used, over: t.points.over,
                    rows: t.points.rows.map(p => ({name: p.name, stat: p.stat, value: p.value, most: p.most}))};
                return {strings, lists, settings, points};
            });
        }
        case "format": {
            const x = c.float ? new S.PyFloat(c.x) : c.x;
            return {g: S.formatG(x), repr: c.float ? S.floatRepr(c.x) : S.pyStr(c.x), json: S.jsonDumps([x, S.pyStr(x)])};
        }
        case "wrap": return S.wrap(c.text, 60);
        case "stats": return S.statsText(G, clone(c.design));
    }
    throw new Error("unknown case " + c.kind);
}
const out = cases.map(c => { try { return run(c); } catch (e) { return {runnerCrash: String(e && e.stack || e)}; } });
fs.writeFileSync(outPath, JSON.stringify(out));
"""


def compare(case, want, got):
    kind = case["kind"]
    if isinstance(got, dict) and "runnerCrash" in got:
        return False
    if kind in ("parse", "check", "room", "lesson", "garage"):
        if "crash" in want or "crash" in got:
            return "crash" in want and "crash" in got
        return same(json.loads(json.dumps(want)), got)
    if kind == "lines":
        lw, lg = want["lines"], got["lines"]
        if "crash" in lw or "crash" in lg:
            return "crash" in lw and "crash" in lg
        return lw == lg and same(want["ctx"], got["ctx"])
    if kind == "apply":
        rw, rg = want["result"], got["result"]
        if "crash" in rw or "crash" in rg:
            return "crash" in rw and "crash" in rg
        return (rw.get("ok") == rg.get("ok") and want["msg"] == got["msg"] and same(want["design"], got["design"])
                and want["changed"] == got["changed"] and want["hack"] == got["hack"])
    return want == got


def main():
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 2026
    count = int(sys.argv[sys.argv.index("--count") + 1]) if "--count" in sys.argv else 60
    passed = total = 0
    failures = []
    # schemas.json is what the games' files say
    total += 1
    with open(make_schemas.OUT, encoding="utf-8") as f:
        if f.read() == make_schemas.text(make_schemas.build()):
            passed += 1
        else:
            failures.append("schemas.json is out of date: run make_schemas.py")
    node = shutil.which("node")
    if not node:
        print("schema_test: skipped the comparisons (Node isn't installed); schemas.json",
              "is up to date" if passed else "is OUT OF DATE")
        return 0 if passed == total else 1
    cases, expected = build_cases(seed, count)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(os.path.join(HERE, "schema.js"), os.path.join(tmp, "schema.mjs"))
        with open(os.path.join(tmp, "run.mjs"), "w", encoding="utf-8") as f:
            f.write(RUNNER)
        with open(os.path.join(tmp, "cases.json"), "w", encoding="utf-8") as f:
            json.dump(cases, f)
        done = subprocess.run([node, os.path.join(tmp, "run.mjs"), make_schemas.OUT, os.path.join(tmp, "cases.json"),
                               os.path.join(tmp, "out.json")], capture_output=True, text=True, encoding="utf-8")
        if done.returncode:
            print(done.stdout, done.stderr)
            print(f"{passed} of {total + len(cases)} passed (Node stopped)")
            return 1
        with open(os.path.join(tmp, "out.json"), encoding="utf-8") as f:
            results = json.load(f)
    by_kind = {}
    for case, want, got in zip(cases, expected, results):
        total += 1
        ok = compare(case, want, got)
        k = by_kind.setdefault(case["kind"], [0, 0])
        k[1] += 1
        if ok:
            passed += 1
            k[0] += 1
        elif len(failures) < 30 and k[1] - k[0] <= 4:  # (the first few of each kind)
            show = {key: case[key] for key in ("kind", "game", "text", "x") if key in case}
            if case["kind"] == "lines" and "ok" in want["lines"] and "ok" in got.get("lines", {}):
                a, b = want["lines"]["ok"], got["lines"]["ok"]
                at = next((i for i in range(max(len(a), len(b))) if a[i:i + 1] != b[i:i + 1]), None)
                if at is not None:  # (the first line that differs)
                    want, got = {"line": at, "text": a[at:at + 3]}, {"line": at, "text": b[at:at + 3]}
                else:
                    want, got = want["ctx"], got["ctx"]
            failures.append(f"{json.dumps(show, ensure_ascii=False)[:600]}\n    Python: "
                            f"{json.dumps(want, ensure_ascii=False)[:700]}\n    schema.js: {json.dumps(got, ensure_ascii=False)[:700]}")
    for f in failures:
        print("FAILED:", f)
    print("  " + ", ".join(f"{k} {a}/{b}" for k, (a, b) in by_kind.items()))
    print(f"{passed} of {total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
