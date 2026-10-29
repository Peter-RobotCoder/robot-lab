"""The Story Missions' recorded missions replayed, kart/replay_test.py's idea for the missions.

    python replay_mission.py --mission lights_out
                                        replay missions/lights_out/replay_mission.json through the mission's own
                                        Python (mission_pseudo.py, mission_lights_out.py): exit code 0 = every event,
                                        state, star and objective the same as when it was recorded
    python replay_mission.py --mission lights_out --window
                                        ...and the fixed missions through the real window, offscreen, by their
                                        recorded key presses (wake_up_call.py --replay): F2 for Mission 2 on the first
                                        screen, the robot chosen with its key, C for the code panel, the program typed
                                        letter by letter, Ctrl+Enter
    ... --window all                    every recorded mission through the window (minutes on a software renderer)
    ... --record                        record again: after a change MEANT to change the rules, with the mission's
                                        MISSION_VERSION raised, in the same commit
    python replay_mission.py            Mission 1 (Wake-Up Call), as on jarvis/game-tests (3b3b293), where this file
                                        comes from: it needs that branch's recording (missions/wake_up_call/
                                        replay_mission.json), which isn't on this branch

The recording: the fixed missions and 120 made-up ones (seeded), each as its own mission with its robot (and, for
Mission 2, whether the Solar Panel from Mission 1 is fitted); for each, the key presses that play it (readable, with
how each run ended) and what it gives: every run's status and events (type, line, message, tone and the state after
it), the end state, the stars and the objectives (zipped into one field, as kart's replay_race.json keeps its
inputs); and one md5 of the lot. Mission 1's cases are wake_up_call_test's; Mission 2's lights_out_test's (the
solution both ways, a fixed route, a hard-coded report, no if, a variable never set, the step cap, a mistake then a
fix; made-up programs with ifs, elses and variables, and the solution changed one way or another).
A replay that differs names the first mission, run, event and field that differ. The window replay checks the
window's keys, editor and RUN give the mission exactly what its Python gives (the window plays the same events).
Exit code 0 = all fine.
"""
import base64
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

ARGV = sys.argv[1:]
MISSION = ARGV[ARGV.index("--mission") + 1] if "--mission" in ARGV[:-1] else "wake_up_call"
if MISSION == "lights_out":
    import lights_out_test as T  # noqa: E402  (SOLUTION, the fixed cases, programs() and py_play(): one set of cases)
    import mission_lights_out as G  # noqa: E402
elif MISSION == "wake_up_call":
    import mission_wake_up as G  # noqa: E402
    import wake_up_call_test as T  # noqa: E402  (SOLUTION, STEPS, programs() and py_play(): the one set of cases)
else:
    sys.exit(f"replay_mission: no mission called {MISSION} (wake_up_call or lights_out)")

MISSION_VERSION = getattr(G, "MISSION_VERSION", 1)
FILE = os.path.join(HERE, "missions", MISSION, "replay_mission.json")
PY = sys.executable
SEED, RANDOM = 1022, 120


def cases():
    """[{"robot", "runs": [program text, ...]} (Mission 2: and "solar"), ...]: the fixed missions, then the seeded
    made-up ones."""
    rnd = random.Random(SEED)
    if MISSION == "lights_out":
        return T.replay_cases() + [{"robot": rnd.choice(["TITAN", "RAZORBACK"]), "solar": rnd.random() < 0.5,
                                    "runs": runs} for runs in T.programs(rnd, RANDOM)]
    S = T.STEPS
    fixed = [("TITAN", [T.SOLUTION]), ("RAZORBACK", [t for _, t in S]),
             ("TITAN", ["move forward 5\nturn right\nmove forward 4", "turn left"]),
             ("TITAN", [S[0][1], S[1][1].replace("spinner", "flipper"), S[2][1].replace("use spinner", "use flipper"),
                        "move forward 1", "use spinner", "pick up spinner",
                        "turn right\nmove back 2\nturn right\nmove forward 1\nturn left\nmove forward 1"]),
             ("TITAN", ["repeat 20 times\nrepeat 20 times\nrepeat 20 times\nturn left\nend\nend\nend"])]
    return [{"robot": r, "runs": runs} for r, runs in fixed + [(rnd.choice(["TITAN", "RAZORBACK"]), runs)
                                                                for runs in T.programs(rnd, RANDOM)]]


FIXED = 5 if MISSION == "wake_up_call" else 9  # (the fixed missions: the ones --window plays)


def play(c):
    """A case through the mission's own Python."""
    if MISSION == "lights_out":
        return T.py_play(c["robot"], c["runs"], c["solar"])
    return T.py_play(c["robot"], c["runs"])


def keys_for(c):
    """The key presses that play a case in the window: (Mission 2: F2 on the first screen) the robot's number, C,
    then for each run Ctrl+A, the program typed, Ctrl+Enter and a wait for the robot (wake_up_call.py's replay()
    says what each step does)."""
    keys = [["key", "f2"]] if MISSION == "lights_out" else []
    keys += [["key", "1" if c["robot"] == "TITAN" else "2"], ["key", "c"]]
    for text in c["runs"]:
        keys += [["key", "control-a"], ["type", text], ["key", "control-enter"], ["wait"]]
    return keys


def fingerprint(results):
    return hashlib.md5(json.dumps(results, sort_keys=True).encode()).hexdigest()


def first_difference(want, got):
    """Where two results first differ: (run, event, field) in words."""
    for r, (a, b) in enumerate(zip(want, got)):
        if a == b:
            continue
        if "final" in a or "final" in b:
            for k in ("final", "stars", "objectives"):
                if a.get(k) != b.get(k):
                    return f"the end: {k} was {json.dumps(a.get(k))[:300]}, now {json.dumps(b.get(k))[:300]}"
        if a.get("status") != b.get("status") or a.get("error") != b.get("error"):
            return f"run {r + 1}: status was {a.get('status', 'error')}, now {b.get('status', 'error')}"
        for e, (x, y) in enumerate(zip(a.get("events", []), b.get("events", []))):
            if x != y:
                field = next((k for k in x if x.get(k) != y.get(k)), "?")
                return f"run {r + 1}, event {e + 1} ({x['type']} at line {x['line']}): {field} was {x.get(field)!r}, now {y.get(field)!r}"
        return f"run {r + 1}: {len(a.get('events', []))} events recorded, now {len(b.get('events', []))}"
    return f"{len(want)} runs recorded, now {len(got)}"


def record():
    out = [dict(c, keys=keys_for(c), result=play(c)) for c in cases()]
    # The file: each mission's robot, programs and key presses readable, with its result's status line; the results
    # themselves (every event with its state) zipped into one field, as kart's replay_race.json keeps its inputs.
    results = [c["result"] for c in out]
    packed = base64.b64encode(zlib.compress(json.dumps(results, sort_keys=True, separators=(",", ":")).encode(), 9)).decode()
    data = {"mission_version": MISSION_VERSION, "md5": fingerprint(results),
            "cases": [dict({k: c[k] for k in c if k not in ("keys", "result")}, keys=c["keys"],
                           ends=" ".join(r.get("status", "error") for r in c["result"][:-1])
                           + f" -> {c['result'][-1]['stars']['count']} stars") for c in out],
            "results": packed}
    text = json.dumps(data, indent=0)  # (one line per value; a key step back on one line, to be read)
    text = re.sub(r'\[\n("(?:key|type|frames|shot)"),\n("(?:[^"\\]|\\.)*"|\d+)\n\]', r"[\1, \2]", text)
    text = text.replace('[\n"wait"\n]', '["wait"]')
    with open(FILE, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    done = sum(1 for r in results if r[-1]["final"]["complete"])
    print(f"Recorded {len(out)} missions ({done} completed, md5 {data['md5'][:8]}, {os.path.getsize(FILE) // 1024} KB): {FILE}")
    return load()


def load():
    """The recording with each case's result unpacked, or None (said) if it isn't there or isn't this
    MISSION_VERSION's."""
    if not os.path.exists(FILE):
        print(f"FAIL no recording for {MISSION} here ({FILE}): record it (python replay_mission.py --mission {MISSION} "
              "--record)" + (" or bring it from jarvis/game-tests" if MISSION == "wake_up_call" else ""))
        return None
    with open(FILE, encoding="utf-8") as f:
        data = json.load(f)
    if data["mission_version"] != MISSION_VERSION:
        print(f"FAIL the recording is of MISSION_VERSION {data['mission_version']}, the mission is {MISSION_VERSION}: "
              f"record it again (python replay_mission.py --mission {MISSION} --record) in the same commit as the change")
        return None
    results = json.loads(zlib.decompress(base64.b64decode(data["results"])))
    for c, r in zip(data["cases"], results):
        c["result"] = r
    return data


def replay(data):
    """Every recorded mission through the mission's Python."""
    for i, c in enumerate(data["cases"]):
        got = play(c)
        if json.dumps(got, sort_keys=True) != json.dumps(c["result"], sort_keys=True):
            print(f"FAIL mission {i + 1} of {len(data['cases'])} ({c['robot']}) differs from its recording: "
                  f"{first_difference(c['result'], got)}\n    the programs: {c['runs']!r}\n"
                  "    (if the rules were meant to change: raise the mission's MISSION_VERSION and record again)")
            return 1
    md5 = fingerprint([c["result"] for c in data["cases"]])
    if md5 != data["md5"]:
        print(f"FAIL the recording's md5 {data['md5'][:8]} isn't its own results' {md5[:8]}: the file was edited by hand")
        return 1
    done = sum(1 for c in data["cases"] if c["result"][-1]["final"]["complete"])
    print(f"PASS {len(data['cases'])} recorded {MISSION} missions ({done} completed) replay the same through the "
          f"mission's Python (md5 {md5[:8]})")
    return 0


def window_run(picked, solar):
    """Some cases' key presses played into the window in one go: {case index: what the window printed}, or a
    failure's words. Mission 2's progress file has the Solar Panel or not, as the cases recorded."""
    tmp = tempfile.mkdtemp(prefix="replay_mission_")
    keys = os.path.join(tmp, "keys.json")
    progress = os.path.join(tmp, "missions_progress.json")
    with open(keys, "w", encoding="utf-8") as f:
        json.dump([{"robot": c["robot"], "keys": c["keys"]} for _, c in picked], f)
    if solar:
        with open(progress, "w", encoding="utf-8") as f:
            json.dump({"parts": ["solar_panel"], "missions": {}}, f)
    r = subprocess.run([PY, "wake_up_call.py", "--offscreen", "--no-sound", "--fast", "--progress", progress,
                        "--replay", keys], cwd=HERE, capture_output=True, text=True, timeout=600 + 20 * len(picked))
    out = r.stdout + r.stderr
    played = {}
    for line in out.splitlines():
        if line.startswith("REPLAY {"):
            d = json.loads(line[7:])
            played[picked[d["case"]][0]] = d
    if r.returncode != 0 or len(played) != len(picked) or "REPLAY DONE" not in out:
        return (f"the window played {len(played)} of {len(picked)} missions (exit {r.returncode}):\n    "
                + "\n    ".join(l for l in out.splitlines()[-12:] if not l.startswith("REPLAY {")))
    return played


def replay_window(data, how_many):
    """The recorded key presses played into the real window (offscreen, no animation), its results against the
    recording's."""
    picked = list(enumerate(data["cases"][:how_many]))
    played = {}
    for solar in (False, True):
        group = [(i, c) for i, c in picked if bool(c.get("solar")) == solar]
        if group:
            got = window_run(group, solar)
            if isinstance(got, str):
                print("FAIL " + got)
                return 1
            played.update(got)
    for i, c in picked:
        got = played[i]
        if got["robot"] != c["robot"] or got.get("mission", "wake_up_call") != MISSION \
                or json.dumps(got["result"], sort_keys=True) != json.dumps(c["result"], sort_keys=True):
            print(f"FAIL the window's mission {i + 1} ({c['robot']}) differs from its recording: "
                  f"{first_difference(c['result'], got['result'])}\n    the programs: {c['runs']!r}")
            return 1
    done = sum(1 for _, c in picked if c["result"][-1]["final"]["complete"])
    runs = sum(len(c["runs"]) for _, c in picked)
    print(f"PASS {len(picked)} recorded {MISSION} missions ({runs} runs, {done} completed) played into the window by "
          f"their key presses give the recorded events")
    return 0


if __name__ == "__main__":
    if "--record" in ARGV:
        data = record()
        sys.exit(replay_window(data, FIXED))  # (the recording proven in the window before it is committed)
    data = load()
    if data is None:
        sys.exit(1)
    code = replay(data)
    if code == 0 and "--window" in ARGV:
        n = len(data["cases"]) if "all" in ARGV else FIXED
        code = replay_window(data, n)
    sys.exit(code)
