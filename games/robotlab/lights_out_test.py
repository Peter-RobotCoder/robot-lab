"""Robot Lab Mission 2, Lights Out: the checks.

    python lights_out_test.py

1. the dictionary: Mission 2's extends Mission 1's (missions/lights_out/dictionary.json on top of
   missions/wake_up_call/dictionary.json) and adds only if / else, variables and report; Mission 1's own file and
   its reading are unchanged (every pattern's words its say, no symbols, an end closes a repeat)
2. the interpreter: phrases (pseudo code and the Python way of writing them) and the Python each becomes; near
   misses and their did-you-mean hints, never corrected; the structure (else without an if, an if without its end,
   empty ifs and elses, energy read only, three deep at most)
3. the mission: the solution brings the lights on all three nights with three stars, with or without the Solar
   Panel; a fixed route that works on night 1 fails on night 2; a hard-coded report fails; the spinner and repairs
   without an if run the battery flat; a variable used before it is set; the step cap; the same program always
   gives the same events
4. the Solar Panel from Mission 1: read from missions_progress.json; 1 energy back every 5 squares; finishing
   keeps Mission 1's result and the panel
5. the window, offscreen: Mission 2 chosen from the Missions menu, played through by key presses (replay_mission.py
   --mission lights_out --window) and a picture of the hill road at night
Exit code 0 = all fine.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import mission_lights_out as L  # noqa: E402
import mission_pseudo as P  # noqa: E402
import mission_wake_up as M1  # noqa: E402

DICT_PATH = os.path.join(HERE, "missions", "lights_out", "dictionary.json")
M1_DICT = os.path.join(HERE, "missions", "wake_up_call", "dictionary.json")
TMP = tempfile.mkdtemp(prefix="lights_out_test_")
PY = sys.executable
results = []

# The whole mission, the pseudo code way: 15 lines, three stars.
SOLUTION = "\n".join([
    "set lamps to 0",
    "repeat 13 times",
    "  if path blocked",
    "    use spinner",
    "  else",
    "    move forward 1",
    "  end",
    "  if lamp dark",
    "    turn left",
    "    repair",
    "    turn right",
    "    add 1 to lamps",
    "  end",
    "end",
    "report lamps",
])
# The same, written the Python way a learner might (mixed mode): the same program.
SOLUTION_PY = "\n".join([
    "lamps = 0",
    "repeat 13 times",
    "  if robot.path_blocked():",
    "    use spinner",
    "  else:",
    "    move forward 1",
    "  end",
    "  if lamp_dark():",
    "    turn left",
    "    repair",
    "    turn right",
    "    lamps = lamps + 1",
    "  end",
    "end",
    "print(lamps)",
])
# Night 1's route written out with no if: right on night 1, a bump on night 2.
FIXED_ROUTE = "\n".join([
    "move forward 1", "turn left", "repair", "turn right", "use spinner", "move forward 4", "turn left", "repair",
    "turn right", "use spinner", "move forward 3", "use spinner", "move forward 1", "turn left", "repair",
    "turn right", "move forward 1", "set lamps to 3", "report lamps",
])
PHRASES = [  # phrase -> the Python it must become
    ("if path blocked", "if robot.path_blocked():"),
    ("If the path is clear:", "if robot.path_clear():"),
    ("if rocks ahead", "if robot.rockfall_in_front():"),
    ("if the lamp is out", "if robot.lamp_dark():"),
    ("if lamp_dark():", "if robot.lamp_dark():"),
    ("if energy is less than 5", "if robot.energy < 5:"),
    ("if robot.energy < 5:", "if robot.energy < 5:"),
    ("if lamps == 3", "if lamps == 3:"),
    ("if count is more than two", "if count > 2:"),
    ("otherwise", "else:"),
    ("else:", "else:"),
    ("set lamps to 0", "lamps = 0"),
    ("Set the variable count to zero.", "count = 0"),
    ("lamps = 0", "lamps = 0"),
    ("add 1 to lamps", "lamps = lamps + 1"),
    ("lamps = lamps + 1", "lamps = lamps + 1"),
    ("lamps += 1", "lamps += 1"),
    ("count = count - 1", "count = count - 1"),
    ("count-=1", "count -= 1"),
    ("subtract 2 from total", "total = total - 2"),
    ("total = energy - 2", "total = robot.energy - 2"),
    ("report lamps", "robot.report(lamps)"),
    ("print(lamps)", "robot.report(lamps)"),
    ("send the energy", "robot.report(robot.energy)"),
    ("move forward 1", "robot.move_forward(1)"),
    ("use the front spinner", 'robot.use("spinner")'),
    ("turn left", "robot.turn_left()"),
]
NEAR_MISSES = [  # phrase, the hint it must give (None: no hint), words the message must contain
    ("if path blokced", "if path blocked", "don't know"),
    ("if blocked path", "if path blocked", "wrong order"),
    ("set lamps too 0", "set lamps to 0", "don't know"),
    ("set lams to 0", "set lamps to 0", "don't know"),
    ("add lamps 1", "add 1 to lamps", "wrong order"),
    ("increase lamps by 1", "add 1 to lamps", "wrong order"),
    ("report the number of lamps", "report lamps", "number"),
    ("if lamps equal 3", None, "needs an end"),  # (equal is a synonym: the line is right, the if has no end)
    ("if", None, "needs a sensor"),
    ("if the moon is out", None, "sensor"),
    ("energy = energy - 2", None, "can read it"),
    ("set energy to 30", None, "can read it"),
    ("pick up power cell", None, "don't recognise"),
]
STRUCTURE = [  # program, the message the first error must contain
    ("else\nmove forward 1", "has no if above it"),
    ("repeat 2 times\nelse\nend", "has no if above it"),
    ("if path blocked\nuse spinner", "needs an end"),
    ("if path blocked\nend", "nothing inside it"),
    ("if path blocked\nelse\nmove forward 1\nend", "nothing inside it to do before the else"),
    ("if path blocked\nuse spinner\nelse\nend", "else has nothing inside it"),
    ("if path blocked\nuse spinner\nelse\nmove forward 1\nelse\nturn left\nend", "has no if above it"),
    ("end", "no repeat or if to close"),
    ("repeat 2 times\nif path blocked\nrepeat 2 times\nif path clear\nmove forward 1\nend\nend\nend\nend",
     "3 deep at most"),
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


def play(text, solar=False, robot="TITAN"):
    m = L.new_mission(robot, solar)
    p = P.parse_program(text, C)
    if p["program"] is None:
        raise AssertionError("did not parse: " + text + " " + json.dumps([r["message"] for r in p["errors"]]))
    return m, m.run(p["program"], p["code_lines"])


def said(r):
    return " | ".join(e["msg"] for e in r["events"] if e["msg"])


def py_play(robot, programs, solar=False):
    """Runs as the window plays them, through the mission's Python: a run {"status", "events"} or {"error": true};
    last {"final", "stars", "objectives"} (replay_mission.py records and replays this)."""
    m, out = L.new_mission(robot, solar), []
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


def replay_cases():
    """The fixed missions replay_mission.py records first (and plays into the window): the solution without and with
    the Solar Panel, the Python way, a fixed route, a hard-coded report, no if, a variable never set, a mistake
    then a fix (three runs)."""
    return [
        {"robot": "TITAN", "solar": False, "runs": [SOLUTION]},
        {"robot": "RAZORBACK", "solar": True, "runs": [SOLUTION]},
        {"robot": "TITAN", "solar": False, "runs": [SOLUTION_PY]},
        {"robot": "RAZORBACK", "solar": False, "runs": [FIXED_ROUTE]},
        {"robot": "TITAN", "solar": True, "runs": [SOLUTION.replace("report lamps", "set lamps to 3\nreport lamps")]},
        {"robot": "TITAN", "solar": False, "runs": ["repeat 10 times\nuse spinner\nmove forward 1\nend"]},
        {"robot": "RAZORBACK", "solar": False, "runs": [SOLUTION.replace("set lamps to 0\n", "")]},
        {"robot": "TITAN", "solar": True, "runs": ["if path blokced\nuse spinner\nend", FIXED_ROUTE,
                                                   SOLUTION.replace("    repair\n", "    repair\n    repair\n"), SOLUTION]},
        {"robot": "TITAN", "solar": False, "runs": ["set lamps to 0\nrepeat 20 times\nrepeat 20 times\nrepeat 20 times\n"
                                                    "turn left\nend\nend\nend"]},
    ]


def programs(rnd, n):
    """Made-up programs, as lists of runs: half the solution changed one way or another (the repeat's count, the
    sensor, the else, the variable's sums), half random lines with ifs, elses, variables and reports."""
    sensors = ["path blocked", "path clear", "rockfall in front", "lamp dark"]
    moves = ["move forward 1", "move forward 2", "move back 1", "turn left", "turn right", "use spinner", "repair",
             "set lamps to 0", "add 1 to lamps", "lamps = lamps + 1", "subtract 1 from lamps", "count += 2",
             "report lamps", "report energy", "set count to 0"]
    out = []
    for i in range(n):
        if i % 2 == 0:
            t = SOLUTION.replace("repeat 13 times", f"repeat {rnd.randint(9, 16)} times")
            if rnd.random() < 0.4:
                t = t.replace("if path blocked", "if " + rnd.choice(sensors))
            if rnd.random() < 0.3:
                t = t.replace("  else\n    move forward 1\n  end", "  end\n  move forward 1")
            if rnd.random() < 0.3:
                t = t.replace("add 1 to lamps", rnd.choice(["add 2 to lamps", "subtract 1 from lamps", "set lamps to 1"]))
            if rnd.random() < 0.2:
                t = t.replace("report lamps", rnd.choice(["report count", "report energy", "move forward 1\nreport lamps"]))
            out.append([t] if rnd.random() < 0.7 else [rnd.choice(moves), t])
            continue
        runs = []
        for _ in range(rnd.randint(1, 3)):
            lines = []
            for _ in range(rnd.randint(1, 7)):
                r = rnd.random()
                if r < 0.2:
                    lines += [f"if {rnd.choice(sensors)}", rnd.choice(moves)]
                    if rnd.random() < 0.5:
                        lines += ["else", rnd.choice(moves)]
                    lines.append("end")
                elif r < 0.3:
                    lines += [f"if {rnd.choice(['energy', 'lamps'])} {rnd.choice(['less than', 'more than', 'equals'])} "
                              f"{rnd.randint(0, 20)}", rnd.choice(moves), "end"]
                elif r < 0.4:
                    lines += [f"repeat {rnd.randint(1, 13)} times", rnd.choice(moves), rnd.choice(moves), "end"]
                else:
                    lines.append(rnd.choice(moves))
            runs.append("\n".join(lines))
        out.append(runs)
    return out


# ---------- 1. the dictionary ----------
def dictionary():
    with open(DICT_PATH, encoding="utf-8") as f:
        own = json.load(f)
    expect(own["extends"] == "../wake_up_call/dictionary.json", "Mission 2's dictionary extends Mission 1's")
    new = {p["id"] for p in own["patterns"]}
    expect(new == {"if_sensor", "if_compare", "else", "set", "set_eq", "add", "add_eq", "subtract", "subtract_eq",
                   "calc_plus", "calc_minus", "report"}, f"only if / else, variables and report are new: {sorted(new)}")
    base = P.load(M1_DICT)
    with open(M1_DICT, encoding="utf-8") as f:
        raw = json.load(f)
    expect([p["id"] for p in base.patterns] == [p["id"] for p in raw["patterns"]], "Mission 1's patterns as its file has them")
    expect(all(p["words"] == P.split_ws(p["say"]) for p in base.patterns), "Mission 1's patterns match every word of their say")
    expect(not base.symbols and not base.minus and base.blocks == ["repeat"], "Mission 1 reads no symbols and has only repeat")
    expect([p["id"] for p in C.patterns][:7] == ["move_forward", "move_back", "turn", "repeat", "end", "use", "repair"],
           "Mission 1's patterns come first, pick up taken out (nothing to pick up on the hill road)")
    for k in ("move", "forward", "turn", "repeat", "spinner"):
        expect(k in C.vocab_set, f"Mission 1's word {k} is still known")
    m1 = P.parse_program("move forward 3\nrepeat 2 times\nturn left\nend\nuse spinner\nrepair", base)
    m2 = P.parse_program("move forward 3\nrepeat 2 times\nturn left\nend\nuse spinner\nrepair", C)
    expect(m1["python"] == m2["python"], "Mission 1's lines give the same Python in Mission 2")
    expect(P.parse_program("end", base)["errors"][0]["message"] == "This end has no repeat to close.",
           "Mission 1's end message unchanged")
    return f"{len(C.patterns)} patterns ({len(C.patterns) - len(new)} Mission 1's)"


# ---------- 2. the interpreter ----------
def interpreter():
    for text, py in PHRASES:
        opens = py.startswith("if ") or py == "else:"
        prog = ("if path blocked\nturn left\n" + text + "\nturn right\nend") if py == "else:" else \
            (text + "\nturn left\nend") if opens else text
        r = P.parse_program(prog, C)
        row = r["rows"][2 if py == "else:" else 0]
        expect(r["program"] is not None and row["python"] == py, f'phrase "{text}": {row.get("python")} {r["errors"]}')
    for text, hint, words in NEAR_MISSES:
        r = P.parse_program(text, C)
        expect(r["errors"], f'"{text}" should be a mistake')
        e = r["errors"][0]
        expect(e.get("hint") == hint, f'"{text}": hint {e.get("hint")!r}, wanted {hint!r}')
        expect(words.lower() in (e["message"] + " " + (e.get("after") or "")).lower(),
               f'"{text}": message {e["message"]!r} should say {words!r}')
        expect(r["rows"][0]["raw"] == text, "never corrected: the line stays as typed")
    for text, words in STRUCTURE:
        r = P.parse_program(text, C)
        expect(r["program"] is None and words in r["errors"][0]["message"] + " " + (r["errors"][0].get("after") or ""),
               f"{text!r}: {[e['message'] for e in r['errors']]}")
    a, b = P.parse_program(SOLUTION, C), P.parse_program(SOLUTION_PY, C)
    expect(b["program"] is not None, f"the Python way parses: {[e['message'] for e in b['errors']]}")
    expect(a["python"].splitlines()[3:6] == ['        robot.use("spinner")', "    else:", "        robot.move_forward(1)"],
           "else sits level with its if, its lines inside it:\n" + a["python"])
    expect(a["python"].splitlines()[6] == "    # end of if" and a["python"].splitlines()[13] == "# end of repeat",
           "an end says what it closes")
    return f"{len(PHRASES)} phrases, {len(NEAR_MISSES)} near misses, {len(STRUCTURE)} structures"


# ---------- 3. the mission ----------
def mission():
    for solar in (False, True):
        m, r = play(SOLUTION, solar)
        expect(r["status"] == "complete", f"the solution completes (solar {solar}): {said(r)}")
        st = m.stars()
        expect(st["count"] == 3, f"three stars (solar {solar}): {st} {m.s['nightEnergy']}")
        expect(m.s["nightEnergy"] == ([5, 8, 5] if not solar else [7, 10, 7]), f"energy left each night: {m.s['nightEnergy']}")
        expect([e["state"]["night"] for e in r["events"] if e["type"] == "night"] == [1, 2, 3], "three nights in order")
        expect(sum(e["type"] == "solar" for e in r["events"]) == (6 if solar else 0), "the Solar Panel's recharges")
    m, r = play(SOLUTION_PY)
    expect(r["status"] == "complete" and m.stars()["count"] == 3, "the Python way completes too")
    m, r = play(FIXED_ROUTE)
    expect(r["status"] == "stopped" and m.s["nightsDone"] == 1 and "Bump" in said(r),
           f"a fixed route works on night 1 only: {m.s['nightsDone']} {said(r)[-200:]}")
    m, r = play(SOLUTION.replace("report lamps", "set lamps to 3\nreport lamps"))
    expect(r["status"] == "stopped" and m.s["nightsDone"] == 1 and "you repaired 2" in said(r),
           f"a hard-coded count fails on night 2: {said(r)[-200:]}")
    m, r = play("repeat 10 times\nuse spinner\nmove forward 1\nturn left\nrepair\nturn right\nend")
    expect(r["status"] == "stopped" and m.s["nightsDone"] == 0, "no if: stopped on night 1")
    m, r = play(SOLUTION.replace("set lamps to 0\n", ""))
    expect(r["status"] == "stopped" and "lamps has no value yet" in said(r),
           f"a variable used before it's set: {said(r)[-200:]}")
    m, r = play("set lamps to 0\nrepeat 20 times\nrepeat 20 times\nrepeat 20 times\nturn left\nend\nend\nend")
    expect(r["status"] == "stopped" and "too many steps" in said(r), "the step cap")
    m, r = play("repeat 13 times\nuse spinner\nmove forward 1\nend")
    expect(r["status"] == "stopped" and m.s["nightsDone"] == 0 and ("Not enough energy" in said(r) or "Bump" in said(r)),
           f"the spinner used every step: {said(r)[-200:]}")
    m, r = play("set lamps to 0\nrepeat 13 times\nif path blocked\nuse spinner\nelse\nmove forward 1\nend\n"
                "turn left\nrepair\nturn right\nend")
    expect(r["status"] == "stopped" and "nothing in front of you to repair" in said(r), "a repair with no lamp in front")
    m, r = play(SOLUTION.replace("    repair\n", "    repair\n    repair\n"))
    expect(r["status"] == "stopped" and "working already" in said(r) and "Not enough energy" in said(r),
           f"repairing a working lamp costs 3: twice each runs the battery flat {said(r)[-200:]}")
    m, r = play(SOLUTION.replace("report lamps", "move forward 1\nreport lamps"))
    expect(r["status"] == "stopped" and "radio mast" in said(r), "a bump into the mast ends the night")
    m, r = play(SOLUTION.replace("report lamps", "turn left\nreport lamps"))
    expect(r["status"] == "stopped" and "face it" in said(r), "report only facing the mast")
    m, r = play(SOLUTION.replace("report lamps", ""))
    expect(r["status"] == "stopped" and "ended before a report" in said(r), "no report: the night isn't done")
    m, r = play(SOLUTION.replace("set lamps to 0", "set lamps to 0\nif energy less than 31\nset count to 1\nend"))
    expect(r["status"] == "complete" and m.stars()["lines"] is False, "energy read in an if; 18 lines: no lines star")
    a = [json.dumps(play(t)[1], sort_keys=True) for t in (SOLUTION, FIXED_ROUTE)]
    b = [json.dumps(play(t)[1], sort_keys=True) for t in (SOLUTION, FIXED_ROUTE)]
    expect(a == b, "deterministic: the same program, the same events")
    return "solution 3 stars with and without the Solar Panel; fixed route, hard-coded report and no-if all fail"


# ---------- 4. the Solar Panel from Mission 1 ----------
def solar_panel():
    path = os.path.join(TMP, "missions_progress.json")
    expect(not L.has_part(path, L.SOLAR["id"]), "no progress file: no Solar Panel")
    m1 = M1.new_mission("TITAN")
    m1.s["complete"] = True
    M1.record_finish(path, m1, "TITAN")
    expect(L.has_part(path, "solar_panel"), "Mission 1 finished: the Solar Panel is there for Mission 2")
    m, r = play(SOLUTION, solar=L.has_part(path, "solar_panel"))
    L.record_finish(path, m, "TITAN")
    p = L.load_progress(path)
    expect(p["parts"] == ["solar_panel"] and p["missions"]["wake_up_call"]["complete"], f"Mission 1's kept: {p}")
    expect(p["missions"]["lights_out"] == {"complete": True, "bestStars": 3, "robot": "TITAN", "energyLeft": 7,
                                           "linesUsed": 15, "solar": True}, f"Mission 2's result: {p['missions']}")
    return "carried over and kept"


# ---------- 5. the window ----------
def window():
    r = subprocess.run([PY, "replay_mission.py", "--mission", "lights_out", "--window"], cwd=HERE, capture_output=True,
                       text=True, timeout=1200)
    out = (r.stdout + r.stderr).strip()
    expect(r.returncode == 0, out[-1500:])
    return out.splitlines()[-1]


def picture():
    shot = os.path.join(TMP, "lights_out.png")
    r = subprocess.run([PY, "wake_up_call.py", "--offscreen", "--no-sound", "--mission", "lights_out", "--robot", "titan",
                        "--progress", os.path.join(TMP, "pic_progress.json"), "--screenshot", shot, "--after", "3"],
                       cwd=HERE, capture_output=True, text=True, timeout=300)
    expect(r.returncode == 0 and os.path.exists(shot) and os.path.getsize(shot) > 20000,
           f"exit {r.returncode}: {(r.stdout + r.stderr)[-800:]}")
    return shot


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    check("1 dictionary: Mission 2's extends Mission 1's, which is unchanged", dictionary)
    check("2 interpreter: phrases, the Python way, near misses with hints, structure", interpreter)
    check("3 mission: three nights, stars, fixed routes fail", mission)
    check("4 Solar Panel carried over from Mission 1", solar_panel)
    if not quick:
        check("5a window: Mission 2 from the Missions menu by key presses (replay_mission.py --window)", window)
        check("5b window: a picture of the hill road at night", picture)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("  -  " + str(note) if note else ""))
    bad = sum(1 for _, ok, _ in results if not ok)
    print(f"{len(results) - bad} of {len(results)} passed")
    sys.exit(1 if bad else 0)
