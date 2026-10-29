"""Robot Lab Mission 1, Wake-Up Call, in 3D: the checks.

    python wake_up_call_test.py

1. the prototype's tests, on the Python port (mission_pseudo.py, mission_wake_up.py): phrases, near misses and their
   did-you-mean hints, structure, the mission as five runs and as one program, a flat battery, the wrong tool,
   bumps, the step cap, the stars, the Solar Panel saved for Mission 2
2. the prototype's own JavaScript (missions/wake_up_call/prototype/) runs its own tests (tests.js) in V8
3. the port gives exactly what the prototype gives: the same Python, rows, errors and hints for hundreds of lines
   (the tests' own and made-up ones with slips), and the same events, states and stars for many programs
4. the copies here match the prototype's folder, when it is in the working folder (prototypes/wake-up-call)
5. the 3D window played through offscreen (wake_up_call.py --selftest): TITAN chosen, C opens the Pseudo code
   and Code tabs, a near miss shows its hint and isn't corrected, the solution runs to the end, three stars, the
   Solar Panel saved; a reset (Ctrl+R, the buttons) puts the mission back and keeps the code, mid-run too; zoom,
   pan and the Graphics panel (Solid or Wireframe; Auto and the engine's seven tiers, each chosen and kept in
   settings.json; the line colour for mesh and lines) change nothing in the mission; at the furthest zoom the
   whole map is inside the view and lit; and pictures of the valley drawn
6. the window opens solid: a Robot Lab settings.json that says mesh (the tier Robot Lab's Settings tab saved) is
   not the mission's look; and the mesh look (--gfx mesh) at the furthest zoom still shows the valley (its fade
   moved out past the camera: the valley went black as it zoomed out) (CHANGE 188)
7. every level the Graphics panel offers (mesh, lines, basic, low, medium, high, ultra: gfx_tiers.TIERS, the
   same ladder as Robot Lab's Settings tab), saved as the panel saves it, opens the window at that tier and
   draws the valley; the first build's "quality" low or high is read as the low or high tier (CHANGE 188)
8. the Club Coders app's first screen opens Missions (CHANGE 189): the launcher run offscreen with its MISSIONS
   button pressed (--test-missions --wait) opens the mission window, with the app's --window choice passed on
   and kept on this computer, waits for it and takes its result; skipped, and says so, where the launcher isn't
   beside the game (the public repository's games/robotlab has it at ../../launcher)
2 and 3 need V8 for Python (pip install mini-racer: a test-only package, not in the game); without it they are
skipped and say so. Exit code 0 = all fine.
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import mission_pseudo as P  # noqa: E402
import mission_wake_up as G  # noqa: E402

FOLDER = os.path.join(HERE, "missions", "wake_up_call")
DICT_PATH = os.path.join(FOLDER, "dictionary.json")
PROTOTYPE = os.path.join(HERE, "..", "prototypes", "wake-up-call")
TMP = tempfile.mkdtemp(prefix="wake_up_call_test_")
PY = sys.executable
results = []

# The whole mission in one program, written the messy way a learner might (capitals, punctuation, synonyms).
SOLUTION = "\n".join([
    "# 1 Battery", "Move forward 3.", "turn right", "go ahead one step", "Pick up the power cell!",
    "# 2 Tool", "turn left", "move forward 2", "turn right", "repeat 3 times", "  move forward 1", "end",
    "grab the front spinner",
    "# 3 Blockage", "turn right", "move forward 3", "turn left", "move forward 2", "use spinner",
    "# 4 Village", "move forward 6",
    "# 5 Repair", "turn right", "repair",
])
# The same route as five separate runs, one per objective.
STEPS = [
    ("Battery", "move forward 3\nturn right\nmove forward 1\npick up power cell"),
    ("Tool", "turn left\nmove forward 2\nturn right\nmove forward 3\npick up spinner"),
    ("Blockage", "turn right\nmove forward 3\nturn left\nmove forward 2\nuse spinner"),
    ("Village", "move forward 6"),
    ("Repair", "turn right\nrepair"),
]
PHRASES = [  # phrase -> the Python it must become
    ("Move forward 3.", "robot.move_forward(3)"),
    ("please turn LEFT!", "robot.turn_left()"),
    ("Go ahead three steps", "robot.move_forward(3)"),
    ("Grab the battery", 'robot.pick_up("power cell")'),
    ("pick up the power cell", 'robot.pick_up("power cell")'),
    ("Use the front spinner.", 'robot.use("spinner")'),
    ("use the wedge", 'robot.use("flipper")'),
    ("Fix the generator", "robot.repair()"),
    ("repair the village power supply", "robot.repair()"),
    ("move back 1", "robot.move_back(1)"),
    ("rotate right", "robot.turn_right()"),
    ("Repeat twice", "for i in range(2):"),
    ("loop 4 times", "for i in range(4):"),
]
NEAR_MISSES = [  # phrase, the hint it must give (None: no hint), words the message must contain
    ("mvoe forward 3", "move forward 3", "don't know"),
    ("move 3 forward", "move forward 3", "wrong order"),
    ("turn lfet", "turn left", "don't know"),
    ("use spiner", "use spinner", "don't know"),
    ("pick up the powr cell", "pick up power cell", "don't know"),
    ("repeat 3", "repeat 3 times", "missing"),
    ("forward 2", "move forward 2", "missing"),
    ("move forward 3 quickly", "move forward 3", "quickly"),
    ("move forward", None, "needs a number"),
    ("move forward 50", None, "from 1 to 20"),
    ("turn up", None, "left or right"),
    ("jump over the rocks", None, "don't recognise"),
    ("please", None, "only filler"),
]


def check(name, fn):
    t0 = time.time()
    try:
        note = fn()
        results.append((name, True, note or f"{time.time() - t0:.1f} s"))
    except Exception as e:  # report and carry on, so every problem is listed
        results.append((name, False, f"{type(e).__name__}: {e}"[-1500:]))


def expect(ok, what):
    if not ok:
        raise AssertionError(what)


C = P.load(DICT_PATH)


def run_text(m, text):
    p = P.parse_program(text, C)
    if p["program"] is None:
        raise AssertionError("did not parse: " + text + " " + json.dumps([r["message"] for r in p["errors"]]))
    return m.run(p["program"], p["code_lines"])


# ---------- 1. the prototype's tests, on the Python port ----------
def interpreter():
    for text, py in PHRASES:
        r = P.parse_program(text + "\nturn left\nend" if py.startswith("for ") else text, C)
        expect(r["program"] is not None and r["rows"][0]["python"] == py, f'phrase "{text}": {r["rows"][0]}')
    for text, hint, words in NEAR_MISSES:
        r = P.parse_program(text, C)
        row = r["rows"][0]
        expect(row["kind"] == "error" and r["program"] is None and row["hint"] == hint
               and words.lower() in row["message"].lower(),
               f'near miss "{text}": {row["kind"]} {row.get("message")} hint {row.get("hint")}')
    a, b = P.parse_program("mvoe 3 forwrd", C), P.parse_program("mvoe 3 forwrd", C)
    expect(repr(a["rows"]) == repr(b["rows"]), "the same line twice gave different results")
    expect(P.parse_program("MOVE, forward: 3!!!", C)["rows"][0]["python"] == "robot.move_forward(3)", "case and punctuation")
    return f"{len(PHRASES)} phrases, {len(NEAR_MISSES)} near misses"


def structure():
    st = lambda t: P.parse_program(t, C)  # noqa: E731
    expect("no repeat" in st("end")["rows"][0]["message"], "an end with no repeat")
    expect("needs an end" in st("repeat 2 times\nmove forward 1")["rows"][0]["message"], "a repeat with no end")
    expect("nothing inside" in st("repeat 2 times\nend")["rows"][1]["message"], "an empty repeat")
    expect(st("move forward 1\nmvoe forward 2\nturn left")["program"] is None, "one bad line stops the program")
    nested = st("repeat 2 times\nrepeat 3 times\nmove forward 1\nend\nturn left\nend")
    expect(nested["python"] == "for i in range(2):\n    for j in range(3):\n        robot.move_forward(1)\n"
                               "    # end of repeat\n    robot.turn_left()\n# end of repeat", nested["python"])
    expect(st("# hi\n\nturn left")["code_lines"] == 1, "comments and blank lines count as code")
    deep = st("repeat 2 times\nrepeat 2 times\nrepeat 2 times\nrepeat 2 times\nturn left\nend\nend\nend\nend")
    expect(deep["program"] is None and "3 deep" in deep["rows"][3]["message"], "a fourth repeat inside is refused")


def mission():
    m = G.new_mission("TITAN")
    expect(m.s["energy"] == G.RULES["energyStart"] < 10, "the robot starts with a low battery")
    for i, (title, text) in enumerate(STEPS):
        res = run_text(m, text)
        obj = m.objectives()
        expect(all(o["done"] for o in obj[:i + 1]) and not any(o["done"] for o in obj[i + 1:]),
               f"step {i + 1} ({title}) didn't complete with its run: {res['status']} {m.s}")
    expect(m.s["complete"], "five runs didn't complete the mission")
    expect(m.s["energy"] == G.RULES["energyStart"] - 4 + G.RULES["cellCharge"] - 5 - 5 - 2 - 6 - 3, m.s["energy"])
    expect(m.stars()["count"] == 3, m.stars())
    one = G.new_mission("RAZORBACK")
    p1 = P.parse_program(SOLUTION, C)
    expect(p1["program"] is not None, [r["message"] for r in p1["errors"]])
    r1 = one.run(p1["program"], p1["code_lines"])
    expect(r1["status"] == "complete" and one.s["complete"], one.s)
    expect(len(r1["events"]) > 20 and r1["events"][-1]["type"] == "complete", len(r1["events"]))
    expect(one.s["energy"] == 8 and one.s["linesUsed"] == 19 and one.stars()["count"] == 3,
           f"the solution should end with 8 energy, 19 lines and three stars: {one.s}")
    best = G.new_mission("TITAN")  # (the README's route: the five steps as one run)
    rb = run_text(best, "\n".join(t for _, t in STEPS))
    expect(rb["status"] == "complete" and best.s["linesUsed"] == 17 and best.stars()["count"] == 3, best.s)
    flat = G.new_mission("TITAN")
    rf = run_text(flat, "move forward 5\nturn right\nmove forward 4")
    expect(rf["status"] == "flat" and flat.s["failed"] and flat.s["energy"] == 0, flat.s)
    expect(flat.run([{"action": "turn", "values": {"dir": "left"}, "line": 1}], 1)["status"] == "flat",
           "a flat battery ends the mission")
    tool = G.new_mission("TITAN")
    run_text(tool, STEPS[0][1])
    run_text(tool, STEPS[1][1].replace("spinner", "flipper"))
    run_text(tool, STEPS[2][1].replace("use spinner", "use flipper"))
    expect(not tool.s["rockCleared"] and tool.s["toolPicked"], tool.s)
    bump = run_text(tool, "move forward 1")
    expect(bump["status"] == "stopped" and tool.s["x"] == 7, tool.s)
    nope = run_text(tool, "use spinner")
    expect(nope["status"] == "stopped" and not tool.s["rockCleared"], [e["msg"] for e in nope["events"]])
    wall = G.new_mission("TITAN")
    rw = run_text(wall, "turn left\nmove forward 3\nturn right")
    expect(rw["status"] == "stopped" and (wall.s["x"], wall.s["y"], wall.s["dir"]) == (1, 6, 3), wall.s)
    early = G.new_mission("TITAN")
    expect(run_text(early, "repair")["status"] == "stopped" and not early.s["complete"], "repair away from it")
    lots = G.new_mission("TITAN")
    big = run_text(lots, "repeat 20 times\nrepeat 20 times\nrepeat 20 times\nturn left\nend\nend\nend")
    expect(big["status"] == "stopped", "a run is capped at %d steps" % G.RULES["maxActions"])


def stars_and_unlock():
    slow = G.new_mission("TITAN")  # the long way: every line on its own, so more than 20 lines
    for _, text in STEPS[:3]:
        run_text(slow, text)
    run_text(slow, "\n".join(["move forward 1"] * 6))
    run_text(slow, "turn right\nrepair")
    st = slow.stars()
    expect(slow.s["complete"] and st["count"] == 2 and not st["lines"] and st["energy"], (slow.s, st))
    path = os.path.join(TMP, "progress", "missions_progress.json")
    expect(not G.has_part(path, "solar_panel"), "the Solar Panel before the mission")
    p = G.record_finish(path, slow, "TITAN")
    expect(G.has_part(path, "solar_panel") and p["missions"]["wake_up_call"]["bestStars"] == 2, p)
    best = G.new_mission("RAZORBACK")
    run_text(best, SOLUTION)
    G.record_finish(path, best, "RAZORBACK")
    G.record_finish(path, slow, "TITAN")  # a worse run later keeps the best stars
    saved = G.load_progress(path)
    expect(saved["parts"] == ["solar_panel"] and saved["missions"]["wake_up_call"]["bestStars"] == 3, saved)
    expect(G.load_progress(os.path.join(TMP, "nothing.json")) == {"parts": [], "missions": {}}, "no file yet")
    import lab_missions
    story = lab_missions.STORY_MISSIONS[G.MISSION_ID]
    expect(story["unlocks"] == G.UNLOCK["id"] and os.path.isfile(os.path.join(HERE, story["window"]))
           and all(o in lab_missions.OUTCOMES for o in story["outcomes"]), story)


def quick():
    """The window reads the program again at every key: a line it can't read, the slowest kind (six words, slips in
    every one, so every order is tried for every spelling), must still be read in good time."""
    worst = 0.0
    for text in ("mvoe frward thre stpes quikly plese", "trun lfet rihgt bakc frwd agn", "zzz yyy xxx www vvv uuu",
                 "repaet tiems thre mvoe forwrd endd", "pcik up teh powr cel nwo"):
        c = P.load(DICT_PATH)  # (a fresh dictionary: nothing remembered)
        t0 = time.perf_counter()
        P.parse_program(text, c)
        worst = max(worst, time.perf_counter() - t0)
    expect(worst < 1.0, f"the slowest line took {worst:.2f} s")
    return f"the slowest line {worst * 1000:.0f} ms"


# ---------- 2 and 3: the prototype's JavaScript in V8 ----------
JS_HELPERS = r"""
var C = CCPseudo.compile(DICT);
function rowsOf(r) {
  return { python: r.python, codeLines: r.codeLines, ok: r.program !== null, program: r.program,
    rows: r.rows.map(function (w) { return { n: w.n, kind: w.kind, canonical: w.canonical === undefined ? null : w.canonical,
      message: w.message === undefined ? null : w.message, hint: w.hint === undefined ? null : w.hint,
      after: w.after === undefined ? null : w.after, indent: w.indent, pythonLine: w.pythonLine }; }) };
}
function parseAll(texts) { return JSON.stringify(texts.map(function (t) { return rowsOf(CCPseudo.parseProgram(t, C)); })); }
function play(robot, programs) {
  var m = CCGame.newMission(robot), out = [];
  programs.forEach(function (t) {
    var p = CCPseudo.parseProgram(t, C);
    if (!p.program) { out.push({ error: true }); return; }
    var r = m.run(p.program, p.codeLines);
    out.push({ status: r.status, events: r.events.map(function (e) { return { type: e.type, line: e.line,
      msg: e.msg === undefined ? null : e.msg, tone: e.tone === undefined ? null : e.tone, state: e.state }; }) });
  });
  out.push({ final: m.s, stars: m.stars(), objectives: m.objectives() });
  return JSON.stringify(out);
}
"""


def py_rows(r):
    return {"python": r["python"], "codeLines": r["code_lines"], "ok": r["program"] is not None, "program": r["program"],
            "rows": [{"n": w["n"], "kind": w["kind"], "canonical": w.get("canonical"), "message": w.get("message"),
                      "hint": w.get("hint"), "after": w.get("after"), "indent": w["indent"], "pythonLine": w["python_line"]}
                     for w in r["rows"]]}


def py_play(robot, programs):
    m, out = G.new_mission(robot), []
    for t in programs:
        p = P.parse_program(t, C)
        if p["program"] is None:
            out.append({"error": True})
            continue
        r = m.run(p["program"], p["code_lines"])
        out.append({"status": r["status"], "events": [{k: e[k] for k in ("type", "line", "msg", "tone", "state")}
                                                      for e in r["events"]]})
    out.append({"final": m.s, "stars": m.stars(), "objectives": m.objectives()})
    return out


_v8 = []


def v8():
    """The prototype's interpreter and mission in V8, or None without mini-racer."""
    if not _v8:
        try:
            from py_mini_racer import MiniRacer
        except ImportError:
            _v8.append(None)
            return None
        ctx = MiniRacer()
        with open(DICT_PATH, encoding="utf-8") as f:
            ctx.eval("var DICT = " + f.read() + ";")
        for name in ("cc_pseudo.js", "cc_game.js", "tests.js"):
            with open(os.path.join(FOLDER, "prototype", name), encoding="utf-8") as f:
                ctx.eval(f.read())
        ctx.eval(JS_HELPERS)
        _v8.append(ctx)
    return _v8[0]


SKIPPED = "skipped: no V8 here (pip install mini-racer)"


def prototype_tests():
    ctx = v8()
    if ctx is None:
        return SKIPPED
    out = json.loads(ctx.eval("JSON.stringify(CCTests.run({ Pseudo: CCPseudo, Game: CCGame, dict: DICT }))"))
    bad = [r["name"] + " -- " + r["detail"] for r in out if not r["pass"]]
    expect(not bad, "\n".join(bad))
    return f"{len(out)} of {len(out)}"


def corpus():
    """Lines to read both ways: the tests', every pattern's example, every synonym, and made-up ones with slips."""
    d = C.dict
    lines = [t for t, _ in PHRASES] + [t for t, _, _ in NEAR_MISSES] + [p["example"] for p in d["patterns"]]
    lines += [f"{k} forward 2" for k in d["synonyms"]] + [f"pick up the {k}" for k in d["synonyms"]]
    lines += ["", "   ", "# a note", "// a note", "#", "move forward 0", "move forward 21", "move forward 007",
              "repeat 20 times", "repeat 21 times", "turn", "use", "pick up", "use hammer drum", "turn left right",
              "MOVE  FORWARD\t2", "move-forward-2", "move forward two!", "move forward twenty", "move forward twentyone",
              "go forwards 3 squares please", "end repeat", "end loop", "done", "twice", "once", "repeat once",
              "fix the power supply", "repair village power supply now", "pickup cell", "powercell", "take battery",
              "gte the batery", "trun rihgt", "mvoe bakc 2", "forward move 3", "3 move forward", "times 3 repeat",
              "spinner use", "left turn", "up pick cell power", "move forward 3 4", "move 3", "back 2", "use the laser",
              "pick up the flame thrower", "été move", "move forward ٣", "turn left;", "Turn Left.",
              "please please please", "the robot", "a b c d e f g", "move move move move move move"]
    rnd = random.Random(20261022)
    vocab = C.vocab + [str(n) for n in (0, 1, 2, 3, 6, 20, 25)]

    def slip(w):
        if len(w) < 3:
            return w
        i = rnd.randrange(len(w) - 1)
        kind = rnd.randrange(4)
        if kind == 0:
            return w[:i] + w[i + 1] + w[i] + w[i + 2:]  # two letters swapped
        if kind == 1:
            return w[:i] + w[i + 1:]  # one dropped
        if kind == 2:
            return w[:i] + rnd.choice("aeiourstn") + w[i:]  # one too many
        return w[:i] + rnd.choice("aeiourstn") + w[i + 1:]  # one changed
    for p in d["patterns"]:  # each pattern with values, then with a slip, reordered, cut short, one word more
        for _ in range(12):
            words = []
            for w in p["say"].split():
                if w == "[n]":
                    words.append(str(rnd.randint(1, 20)) if rnd.random() < 0.8 else rnd.choice(list(d["number_words"])))
                elif P.is_slot(w):
                    words.append(rnd.choice(d["slots"][P.slot_name(w)]["values"]))
                else:
                    words.append(w)
            text = " ".join(words)
            lines.append(text)
            ws = text.split()
            k = rnd.randrange(len(ws))
            lines.append(" ".join(ws[:k] + [slip(ws[k])] + ws[k + 1:]))
            if len(ws) > 1:
                lines.append(" ".join(rnd.sample(ws, len(ws))))
                lines.append(" ".join(ws[:-1]))
            lines.append(text + " " + rnd.choice(vocab))
    for _ in range(150):  # words at random
        ws = [rnd.choice(vocab) for _ in range(rnd.randint(1, 6))]
        ws = [slip(w) if rnd.random() < 0.3 else w for w in ws]
        lines.append(" ".join(w.upper() if rnd.random() < 0.1 else w for w in ws) + rnd.choice(["", ".", "!", " ?"]))
    return lines


def programs(rnd, n):
    """Made-up programs, as lists of runs: lines the robot understands, some repeats, some mistakes."""
    moves = ["move forward 1", "move forward 2", "move forward 3", "move back 1", "turn left", "turn right",
             "pick up power cell", "pick up spinner", "pick up flipper", "pick up hammer", "pick up drum",
             "use spinner", "use flipper", "use hammer", "use drum", "repair"]
    out = []
    for _ in range(n):
        runs = []
        for _ in range(rnd.randint(1, 4)):
            lines = []
            for _ in range(rnd.randint(1, 8)):
                if rnd.random() < 0.15:
                    lines += [f"repeat {rnd.randint(1, 4)} times", rnd.choice(moves), rnd.choice(moves), "end"]
                else:
                    lines.append(rnd.choice(moves))
            runs.append("\n".join(lines))
        out.append(runs)
    return out


def parity_lines():
    ctx = v8()
    if ctx is None:
        return SKIPPED
    texts = corpus()
    texts.append("\n".join(texts[:60]))  # and as one program (errors and all)
    texts += [SOLUTION] + [t for _, t in STEPS] + ["repeat 2 times\nrepeat 3 times\nmove forward 1\nend\nturn left\nend",
                                                  "end\nrepeat 2 times", "repeat 2 times\nend",
                                                  "repeat 2 times\nrepeat 2 times\nrepeat 2 times\nrepeat 2 times\nturn left\nend\nend\nend\nend",
                                                  "move forward 1\r\nturn left\r\n\r\n# done"]
    js = json.loads(ctx.eval("parseAll(" + json.dumps(texts) + ")"))
    bad = []
    for t, a in zip(texts, js):
        b = py_rows(P.parse_program(t, C))
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            bad.append(f"{t!r}\n  prototype: {json.dumps(a)[:600]}\n  3D port:   {json.dumps(b)[:600]}")
    expect(not bad, f"{len(bad)} of {len(texts)} differ:\n" + "\n".join(bad[:4]))
    hinted = sum(1 for a in js for r in a["rows"] if r["hint"])
    return f"{len(texts)} texts the same ({hinted} did-you-mean hints among them)"


def parity_mission():
    ctx = v8()
    if ctx is None:
        return SKIPPED
    rnd = random.Random(1022)
    cases = [("TITAN", [SOLUTION]), ("RAZORBACK", [t for _, t in STEPS]),
             ("TITAN", ["move forward 5\nturn right\nmove forward 4", "turn left"]),
             ("TITAN", [STEPS[0][1], STEPS[1][1].replace("spinner", "flipper"),
                        STEPS[2][1].replace("use spinner", "use flipper"), "move forward 1", "use spinner",
                        "pick up spinner", "turn right\nmove back 2\nturn right\nmove forward 1\nturn left\nmove forward 1"]),
             ("TITAN", ["repeat 20 times\nrepeat 20 times\nrepeat 20 times\nturn left\nend\nend\nend"])]
    cases += [(rnd.choice(["TITAN", "RAZORBACK"]), runs) for runs in programs(rnd, 120)]
    bad = []
    for robot, runs in cases:
        a = json.loads(ctx.eval(f"play({json.dumps(robot)}, {json.dumps(runs)})"))
        b = py_play(robot, runs)
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            bad.append(f"{robot} {runs!r}\n  prototype: {json.dumps(a)[:500]}\n  3D port:   {json.dumps(b)[:500]}")
    expect(not bad, f"{len(bad)} of {len(cases)} differ:\n" + "\n".join(bad[:3]))
    return f"{len(cases)} missions played the same"


# ---------- 4. the copies here and the prototype ----------
def copies():
    if not os.path.isfile(os.path.join(PROTOTYPE, "index.html")):
        return "skipped: no prototypes/wake-up-call in the working folder (git switch prototype/wake-up-call to see it)"
    r = subprocess.run([PY, os.path.join(FOLDER, "sync_prototype.py"), PROTOTYPE, "--check"], capture_output=True,
                       text=True, timeout=60)
    expect(r.returncode == 0, (r.stdout + r.stderr).strip())


# ---------- 5. the 3D window ----------
def window():
    shot = os.path.join(TMP, "wake_up_call.png")
    progress = os.path.join(TMP, "window", "missions_progress.json")
    r = subprocess.run([PY, "wake_up_call.py", "--offscreen", "--selftest", "--no-sound", "--progress", progress,
                        "--screenshot", shot], cwd=HERE, capture_output=True, text=True, timeout=300)
    # (300 s: about 250 s on LT5, a worker drawing in software, when it's busy; 240 s ran out there)
    out = r.stdout + r.stderr
    expect(r.returncode == 0 and "SELFTEST PASS" in out, out[-1500:])
    expect(os.path.exists(shot), "no picture drawn")
    expect(G.has_part(progress, "solar_panel"), "the window didn't save the Solar Panel")
    px = pixels(shot)
    expect(px.std() > 12, f"the picture is nearly one colour (std {px.std():.1f})")
    zoomed = shot.replace(".png", "_zoom.png")
    expect(os.path.exists(zoomed), "no picture at the furthest zoom")
    middle = brightness(zoomed)
    expect(middle > 25, f"the valley is dark at the furthest zoom (the middle of the picture averages {middle:.0f} of 255)")
    with open(os.path.join(os.path.dirname(progress), "settings.json"), encoding="utf-8") as f:
        saved = json.load(f)
    expect(saved.get("wake_up_call_gfx") == {"look": "solid", "tier": "high", "line_colour": "#ffb000"},
           f"the Graphics choice beside the progress file: {saved.get('wake_up_call_gfx')}")
    return [line for line in out.splitlines() if line.startswith("SELFTEST")][-1] + f", the zoomed-out valley {middle:.0f}/255"


def pixels(path):
    from PIL import Image
    import numpy as np
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


def brightness(path):
    """The average brightness (0 to 255) of the middle three fifths of a picture: the valley, not the HUD."""
    px = pixels(path)
    h, w = px.shape[:2]
    return float(px[h // 5: 4 * h // 5, w // 5: 4 * w // 5].mean())


# ---------- 6. solid by default, and the mesh look lit at the furthest zoom (CHANGE 188) ----------
def picture(name, extra, env=None):
    """The window opened straight in with TITAN and photographed after a moment: the picture's path and the output."""
    shot = os.path.join(TMP, name + ".png")
    progress = os.path.join(TMP, name, "missions_progress.json")
    r = subprocess.run([PY, "wake_up_call.py", "--offscreen", "--no-sound", "--robot", "titan", "--progress", progress,
                        "--screenshot", shot, "--after", "0.5"] + extra, cwd=HERE, capture_output=True, text=True,
                       timeout=180, env=env)
    out = r.stdout + r.stderr
    # A software renderer (llvmpipe, a worker without a GPU) can't compile Panda's own Cg shaders, which the basic
    # tier draws with ("The profile is not supported"), and Panda aborts as that window closes, after the picture is
    # saved: the same at a942ff1 and in robot_wars.py --gfx basic, so the level is judged by its picture there.
    cg_abort = r.returncode != 0 and os.path.exists(shot) and "The profile is not supported" in out
    expect((r.returncode == 0 or cg_abort) and os.path.exists(shot), out[-1500:])
    return shot, out + ("\n(the window aborted as it closed: Panda's Cg shaders on this software renderer)" if cg_abort else "")


def solid_by_default():
    # Robot Lab's Settings tab had saved the Mesh look on this computer (gfx_tier mesh, chosen by hand): the mission
    # used to open as a wireframe. Its settings live in APPDATA/RobotLab (HOME/RobotLab elsewhere).
    home = os.path.join(TMP, "home")
    os.makedirs(os.path.join(home, "RobotLab"), exist_ok=True)
    with open(os.path.join(home, "RobotLab", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"gfx_tier": "mesh", "gfx_hand": True, "gfx_detect": {"heuristic_tier": "high"}}, f)
    env = dict(os.environ, APPDATA=home, HOME=home, USERPROFILE=home)
    shot, out = picture("solid", [], env)
    tier = [line for line in out.splitlines() if line.startswith("wake_up_call: the ")]
    expect(tier and "mesh" not in tier[0] and "lines" not in tier[0], f"the tier the window chose: {tier} {out[-600:]}")
    expect("solid tiers only" in tier[0], tier[0])
    solid = brightness(shot)
    expect(solid > 25, f"the solid picture is dark (the middle averages {solid:.0f} of 255)")
    # --gfx mesh by hand, at the furthest zoom: the lines still there (the fade used to start at 16 m and end at 60)
    shot, out = picture("mesh", ["--gfx", "mesh", "--zoom", "9"])
    expect("wake_up_call: the mesh tier (--gfx)" in out, out[-600:])
    px = pixels(shot)
    h, w = px.shape[:2]
    middle = px[h // 5: 4 * h // 5, w // 5: 4 * w // 5]
    lit = float((middle.max(axis=2) > 60).mean() * 100)  # (the share of the middle that isn't black: the lines)
    expect(lit > 1.5, f"the mesh look is black at the furthest zoom ({lit:.1f}% of the middle has lines)")
    return f"solid at {solid:.0f}/255 with Robot Lab's mesh saved; mesh at the furthest zoom {lit:.1f}% lines"


# ---------- 7. every level the Graphics panel offers opens and is drawn (CHANGE 188) ----------
def every_level():
    """The panel's Quality row is the engine's whole ladder (gfx_tiers.TIERS, as Robot Lab's Settings tab). A tier
    chosen there is kept beside the progress file and the next start opens at it: each of the seven, saved as the
    panel saves it, opens the window at that tier and draws the valley (a picture per level, in TMP); the first
    build's "quality" low or high is read as the low or high tier; with no choice the window is solid (test 6)."""
    import lab_version
    sys.path.insert(0, lab_version.ENGINE_HOME)
    from engine import gfx_tiers
    expect(gfx_tiers.TIERS == ("mesh", "lines", "basic", "low", "medium", "high", "ultra"), gfx_tiers.TIERS)
    notes = []
    cases = [({"look": "solid", "tier": t}, t) for t in gfx_tiers.TIERS] + [({"quality": "low"}, "low")]
    for choice, tier in cases:
        name = "level_" + tier + ("_quality" if "quality" in choice else "")
        folder = os.path.join(TMP, name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "settings.json"), "w", encoding="utf-8") as f:
            json.dump({"wake_up_call_gfx": choice}, f)
        shot, out = picture(name, [])
        line = [ln for ln in out.splitlines() if ln.startswith("wake_up_call: the ")]
        expect(line and line[0] == f"wake_up_call: the {tier} tier (Graphics panel: {tier})", f"{choice}: {line} {out[-600:]}")
        px = pixels(shot)
        h, w = px.shape[:2]
        middle = px[h // 5: 4 * h // 5, w // 5: 4 * w // 5]
        if tier in gfx_tiers.LOOKS:
            lit = float((middle.max(axis=2) > 60).mean() * 100)
            expect(lit > 1.5, f"{tier}: black ({lit:.1f}% of the middle has lines)")
            notes.append(f"{tier} {lit:.0f}% lines")
        else:
            # (dusk over the valley: basic, with Panda's own lights, averages about 30 of 255 here; black was under 10)
            expect(middle.mean() > 20 and middle.std() > 12, f"{tier}: dark or flat (mean {middle.mean():.0f}, std {middle.std():.0f})")
            notes.append(f"{tier} {middle.mean():.0f}/255" + (" (drawn; aborted on closing: Cg shaders on a software renderer)"
                                                              if "aborted as it closed" in out else ""))
        with open(os.path.join(folder, "settings.json"), encoding="utf-8") as f:
            expect(json.load(f).get("wake_up_call_gfx") == choice, "opening the window changed the saved choice")
    return "; ".join(notes)


# ---------- 8. the Club Coders app opens Missions from its first screen (CHANGE 189) ----------
def launcher():
    """The app's launcher, offscreen, its MISSIONS button pressed by --test-missions: it opens wake_up_call.py in
    this folder (club_coders.GAMES["missions"], Robot Lab's folder), passes its Graphics and Window choices on, waits
    for the window and exits with its result. Its settings go to a scratch HOME (ClubCoders/settings.json,
    RobotLab/settings.json)."""
    for rel in (("..", "club-coders", "launcher"), ("..", "..", "launcher")):  # (the working folder; the public repo)
        path = os.path.abspath(os.path.join(HERE, *rel, "club_coders.py"))
        if os.path.exists(path):
            break
    else:
        return "skipped: the app's launcher isn't beside this folder"
    home = os.path.join(TMP, "launcher")
    os.makedirs(os.path.join(home, "ClubCoders"), exist_ok=True)
    with open(os.path.join(home, "ClubCoders", "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"where": "online", "window": "1600x900"}, f)  # (the app's Window button: passed on as --window)
    env = dict(os.environ, HOME=home, USERPROFILE=home, APPDATA=home)
    shot = os.path.join(TMP, "from_launcher.png")
    r = subprocess.run([PY, path, "--offscreen", "--test-missions", "--wait", "--screenshot", shot, "--after", "0.5"],
                       cwd=os.path.dirname(path), capture_output=True, text=True, timeout=300, env=env)
    out = r.stdout + r.stderr
    expect(r.returncode == 0, f"exit {r.returncode}: {out[-1500:]}")
    opened = [ln for ln in out.splitlines() if ln.startswith("Opening Missions:")]
    expect(opened and "--window 1600x900" in opened[0], f"the launcher's line: {opened} {out[-800:]}")
    expect("wake_up_call: the " in out, f"the mission window didn't start: {out[-800:]}")
    expect(os.path.exists(shot), "no picture from the window the launcher opened")
    with open(os.path.join(home, "RobotLab", "settings.json"), encoding="utf-8") as f:
        saved = json.load(f)
    expect(saved.get("window") == "1600x900" and saved.get("fullscreen") is False,
           f"the app's --window choice wasn't kept as the games keep it: {saved}")
    return opened[0]


if __name__ == "__main__":
    check("The interpreter: phrases, near misses and their hints", interpreter)
    check("The interpreter: repeats, ends and errors", structure)
    check("The mission: five runs, one program, a flat battery, the wrong tool, bumps", mission)
    check("Stars and the Solar Panel saved for Mission 2", stars_and_unlock)
    check("A line it can't read is read quickly enough to type", quick)
    check("The prototype's own tests pass in V8", prototype_tests)
    check("The port reads every line as the prototype does", parity_lines)
    check("The port plays every mission as the prototype does", parity_mission)
    check("The copies match the prototype", copies)
    check("The 3D window plays the mission through", window)
    check("The window opens solid, and the mesh look is lit at the furthest zoom", solid_by_default)
    check("Every level the Graphics panel offers opens the window at it and draws the valley", every_level)
    check("The Club Coders app's first screen opens Missions and waits for it", launcher)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + (f" ({note})" if ok else ":\n    " + note.replace("\n", "\n    ")))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
