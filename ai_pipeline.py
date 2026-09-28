"""Teacher-approved AI changes ("vibe coding" through the teacher).

A learner's AI request card, once the teacher approves it, goes to Claude Code on the teacher's computer:
  1. a snapshot of the project's files is taken, so any change can be undone
  2. Claude is given only file tools (no commands) and told what it may change
  3. any change outside that is put back as it was
  4. the change is tested: the mods and a test fight, and for code changes the whole game (smoke_test.py)
  5. the teacher sees what changed and presses Keep or Undo
  6. every kept change becomes a mod in the change history (ai_changes/): it can be looked at, switched off
     and on again (only the mod's own lines change, so later work is kept), and finally merged into the game
     as a permanent update. Nothing is committed to git automatically: commit when you choose to.

What Claude may change:
  "robot"  the learner's file in mods/robots        "arena"  mods/arena.py        "rules"  mods/rules.py
  "game"   anything in the game: every .py file and the mods, including new files. Only the safety parts
           stay locked: this file, the learner-code sandbox, the password code, where updates come from
           (lab_version.py) and the tests.
If a smaller request needs more than it was given, Claude says so and the teacher can send it again as "game".

Try it from a terminal:  python ai_pipeline.py robot Sam "Make my robot blue with yellow lights"
"""
import datetime
import difflib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ROBOTLAB_DATA", HERE)          # where profiles, evidence and the change history live
CHANGES = os.path.join(DATA, "ai_changes")
# the safety parts: logins, the brain sandbox, where updates come from, and the tests (never changed by Claude)
PROTECTED = {"ai_pipeline.py", "lab_profiles.py", "robot_loader.py", "lab_brain.py", "brain_rules.py",
             "brain_worker.py", "lab_version.py", "smoke_test.py", "security_test.py"}
SKIP_DIRS = {".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "brains"}
CLAUDE = shlex.split(os.environ.get("CLAUDE_CMD", "claude"))  # CLAUDE_CMD lets tests use a stand-in
NEEDS_GAME = "NEEDS THE WHOLE GAME"
TARGET_NAMES = {"robot": "the learner's robot file", "arena": "the arena file", "rules": "the rules file",
                "game": "the whole game"}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "learner"


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def in_git_repo():
    r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=HERE, capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "true"


def snapshot_files():
    """Every project file's bytes (paths relative to this folder), so changes can be found and undone."""
    snap = {}
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, HERE).replace("\\", "/")
            try:
                if os.path.getsize(path) <= 2_000_000:
                    with open(path, "rb") as f:
                        snap[rel] = f.read()
            except OSError:
                pass
    return snap


def restore(rel, before):
    """Put one file back as it was in the snapshot (or remove it if it's new)."""
    path = os.path.join(HERE, rel)
    if rel in before:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(before[rel])
    elif os.path.exists(path):
        os.remove(path)


def may_change(target, learner, rel):
    """Is Claude allowed to change this file for this kind of request?"""
    if target == "robot":
        return rel == f"mods/robots/{slug(learner)}.py"
    if target == "arena":
        return rel == "mods/arena.py"
    if target == "rules":
        return rel == "mods/rules.py"
    if target == "game":
        top = rel.split("/")[0]
        return (rel.endswith(".py") or rel.startswith("mods/")) and rel not in PROTECTED and top not in SKIP_DIRS \
            and ".." not in rel
    return False


def allowed_files(target, learner, allow_engine=True):
    """What the prompt tells Claude it may change."""
    if target == "robot":
        return [f"mods/robots/{slug(learner)}.py"]
    if target == "arena":
        return ["mods/arena.py"]
    if target == "rules":
        return ["mods/rules.py"]
    if target == "game":
        return ["any file of the game (the .py files and everything in mods/), and new files if they're needed",
                "except these, which must not be changed: " + ", ".join(sorted(PROTECTED))]
    raise ValueError(f"Unknown target: {target}")


def robot_file_text(design, learner):
    """A mods/robots file for a learner who doesn't have one yet (their current design)."""
    d = dict(design)
    d.setdefault("style", {"trim": [30, 30, 34], "lights": [255, 120, 40], "number": d.get("name", learner)[:8]})
    body = json.dumps(d, indent=4).replace("true", "True").replace("false", "False")
    return (f'"""{learner}\'s robot. Changed by AI requests that the teacher approves."""\n\n'
            f"ROBOT = {body}\n")


GAME_GUIDE = """HOW THE GAME IS BUILT (Python 3, Panda3D with Bullet physics)
- lab_sim.py: all the physics, run by the server: robots built from designs (points, settings, weapons), weapon
  hits, the arena, hazards (drop zone, floor flipper, saws, wall spikes) and the house robots (BLAZE, CRUSHER,
  RIPSAW, VORTEX). shapes() gives each weapon's sizes, and the graphics use the same numbers.
- lab_server.py: the class server (logins, lessons, the teacher's controls, sending the state 20 times a second).
  lab_teaching.py: missions and evidence. lab_missions.py: lesson presets, missions, curriculum outcomes.
- lab_client.py: the learner and teacher windows (garage, missions, AI card, teacher panels, code panel).
- rw_gfx.py: how the arena and robots look (RobotVisual draws each weapon; ArenaVisual draws the hazards).
  rw_fx.py sparks, smoke and flames; rw_sound.py sounds; rw_camera.py cameras; rw_mesh.py shapes.
- robot_wars.py: the single-player showcase (TITAN v RAZORBACK).
- mods/: plain-data files (robots, arena, rules) checked by rw_mods.py.
A new game feature usually needs the physics in lab_sim.py AND how it looks in rw_gfx.py (and a control in
lab_client.py / lab_server.py if the teacher or learner switches it). A new weapon needs: an entry in WEAPONS,
a shape in shapes(), its body in Robot.__init__, how it moves in Robot.tick, what it does in weapon_contact,
and its model in RobotVisual.

RULES FOR A GAME CHANGE
- Keep everything that already works working. Change as little as the request needs.
- The game must still start. When you have finished, run the game's test with exactly this command (it is the
  only command you may run): .venv/Scripts/python smoke_test.py
  It checks every file compiles, the server runs a full arena, and the showcase and both windows start. If
  anything fails, fix it and run the test again.
- Don't add new packages. Don't touch files outside the game folder."""


def build_prompt(card, learner, target, files):
    import lab_sim as sim
    import rw_mods
    limits = "\n".join(f"  - {k}: {lo} to {hi}" for k, (lo, hi) in rw_mods.RULE_LIMITS.items())
    settings = "\n".join(f"  - {k}: {lo} to {hi}" for k, (lo, hi, _, _) in sim.SETTINGS.items())
    if target == "game":
        scope = f"""The teacher has checked and approved this request, and allows you to change {files[0]},
{files[1]}.

{GAME_GUIDE}"""
    else:
        scope = f"""The teacher has checked and approved this request. Make the change by editing ONLY these files:
{chr(10).join('  - ' + f for f in files)}
If the request needs anything outside these files (for example a new kind of weapon, a second weapon, or new
game mechanics), change nothing and begin your reply with exactly "{NEEDS_GAME}:" followed by one sentence
saying what would need to change. The teacher can then send it again with the whole game allowed."""
    return f"""You are helping a 13-18 year old learner in a coding club change their Robot Wars game.
{scope}

LEARNER'S REQUEST (first name only: {learner})
  Goal: {card.get('goal', '').strip()}
  Variables / values: {card.get('variables', '').strip()}
  How they will test it: {card.get('test', '').strip()}
  Their prediction: {card.get('predict', '').strip()}

HOW THE MOD FILES WORK
- mods/robots/*.py hold ROBOT = {{...}}: name, colour [r, g, b] 0-255, weapon (wedge, spinner, drum, hammer),
  points (speed, attack, armour, control: whole numbers {sim.STAT_MIN}-{sim.STAT_MAX}, total at most {sim.POINTS_TOTAL}),
  settings (percent):
{settings}
  style: trim [r, g, b], lights [r, g, b], number (text on the deck, up to 10 characters), and optionally
  model (one of {', '.join(sim.HOUSE_BY_NAME)}) to drive a house robot.
- mods/arena.py holds ARENA = {{...}}: hazards (pit, floor_flipper, saws, spikes: True/False; house_robots: True,
  False or a list of names) and look (name up to 16 characters, wall_colour [r, g, b], crowd True/False).
- mods/rules.py holds RULES = {{...}} with these numbers and limits:
{limits}
- Mod files must stay plain data: one dictionary, comments allowed, no imports, functions or other code.

RULES FOR YOUR CHANGE
- Keep values inside the limits above (a whole-game change may change the limits themselves in rw_mods.py).
- Don't add anything that wasn't asked for. Keep comments short and clear.
- Finish with 3-5 short bullet points: what you changed (file, what, old -> new) and one thing the learner should
  check when they test it. Don't include any personal information.
"""


def run_tests(changed):
    """Mods and a test fight; if code changed, the whole game (smoke_test.py). Returns (ok, text)."""
    code = any(f.endswith(".py") and not f.startswith("mods/") for f in changed)
    script = "smoke_test.py" if code else "rw_mods.py"
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE, capture_output=True, text=True,
                           timeout=400)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"{script} took too long"


class AIChange:
    """One learner request going through Claude. Call run(), then keep() or undo()."""

    def __init__(self, card_id, learner, card, target, design=None, allow_engine=True):
        if target not in TARGET_NAMES:
            raise ValueError(f"Unknown target: {target}")
        self.id, self.learner, self.card, self.target = card_id, learner, card, target
        self.design = design
        self.files = allowed_files(target, learner)
        self.before, self.after = {}, {}
        self.changed = []
        self.result = {}

    def run(self, progress=print, timeout=None):
        self.before = snapshot_files()  # before the robot file is made, so Undo removes a new one
        stub = None
        if self.target == "robot":
            rel = f"mods/robots/{slug(self.learner)}.py"
            path = os.path.join(HERE, rel)
            if not os.path.exists(path):
                import lab_sim as sim
                # the learner's current robot, or a starter one if they aren't connected right now
                design = self.design if not sim.check_design(self.design or {}) else sim.default_design(self.learner)
                stub = robot_file_text(design, self.learner).encode("utf-8")
                with open(path, "wb") as f:
                    f.write(stub)
        progress("Claude is working on it...")
        whole = self.target == "game"
        prompt = build_prompt(self.card, self.learner, self.target, self.files)
        tools = "Read,Edit,Write,Glob,Grep" + (",Bash(.venv/Scripts/python smoke_test.py)" if whole else "")
        cmd = CLAUDE + ["-p", prompt, "--allowedTools", tools,
                        "--permission-mode", "acceptEdits", "--max-turns", "60" if whole else "15",
                        "--output-format", "json"]
        try:
            r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout or (1200 if whole else 600),
                               stdin=subprocess.DEVNULL, encoding="utf-8")
            out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"result": r.stdout or r.stderr}
        except subprocess.TimeoutExpired:
            out = {"result": "Claude took too long, so the change was stopped.", "is_error": True}
        except FileNotFoundError:
            out = {"result": "Claude Code isn't installed on this computer.", "is_error": True}
        summary = str(out.get("result", "")).strip()
        # put back anything Claude touched that this request may not change
        after = snapshot_files()
        changed = sorted(f for f in set(self.before) | set(after) if self.before.get(f) != after.get(f))
        outside = [f for f in changed if not may_change(self.target, self.learner, f)]
        for f in outside:
            restore(f, self.before)
        kept = [f for f in changed if f not in outside]
        if stub is not None:  # the starter robot file we made isn't a change unless Claude changed it
            rel = f"mods/robots/{slug(self.learner)}.py"
            if after.get(rel) == stub:
                restore(rel, self.before)
                kept = [f for f in kept if f != rel]
        self.after = {f: after.get(f) for f in kept}
        self.changed = kept
        diff = diff_text(self.before, self.after, kept)
        progress("Testing the change...")
        test_ok, test_text = run_tests(kept) if kept else (True, "nothing to test")
        needs_game = summary.lstrip("*_ `").upper().startswith(NEEDS_GAME)
        self.result = {"id": self.id, "summary": summary[:1500], "files": kept, "blocked": outside,
                       "diff": diff[:6000], "test_ok": test_ok, "test": test_text[-600:],
                       "needs_game": needs_game and not whole, "target": self.target,
                       "code_changed": any(f.endswith(".py") and not f.startswith("mods/") for f in kept),
                       "error": bool(out.get("is_error")), "cost_usd": out.get("total_cost_usd")}
        return self.result

    def contents(self):
        """The changed files' text, so they can be sent to the game server."""
        return {f: open(os.path.join(HERE, f), encoding="utf-8").read() for f in self.changed
                if os.path.exists(os.path.join(HERE, f))}

    def keep(self):
        """Add the change to the mods (so it can be switched off and on later, or merged into the game)."""
        return record_change(self)

    def undo(self):
        """Put the changed files back exactly as they were before Claude ran."""
        for f in self.changed:
            restore(f, self.before)


# ---------- the change history: look at, roll back and put back kept changes ----------

def diff_text(before, after, files):
    out = []
    for f in files:
        a = (before.get(f) or b"").decode("utf-8", "replace").splitlines(True)
        b = (after.get(f) or b"").decode("utf-8", "replace").splitlines(True)
        out.append("".join(difflib.unified_diff(a, b, f"before/{f}", f"after/{f}")))
    return "".join(out)


def _log_path():
    return os.path.join(CHANGES, "log.json")


def history():
    """Every kept change, oldest first."""
    try:
        with open(_log_path(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def _save_history(log):
    os.makedirs(CHANGES, exist_ok=True)
    with open(_log_path(), "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def _store(n, side, files):
    for rel, data in files.items():
        if data is None:
            continue
        path = os.path.join(CHANGES, str(n), side, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)


def _stored(n, side, rel):
    path = os.path.join(CHANGES, str(n), side, rel)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def _current(rel):
    path = os.path.join(HERE, rel)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def _put(rel, data):
    path = os.path.join(HERE, rel)
    if data is None:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def record_change(change):
    log = history()
    n = max([e["n"] for e in log], default=0) + 1
    _store(n, "before", {f: change.before.get(f) for f in change.changed})
    _store(n, "after", {f: change.after.get(f) for f in change.changed})
    log.append({"n": n, "card": change.id, "learner": change.learner, "goal": change.card.get("goal", "")[:200],
                "target": change.target, "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "files": change.changed, "summary": change.result.get("summary", "")[:600], "status": "kept",
                "new_files": [f for f in change.changed if change.before.get(f) is None]})
    _save_history(log)
    return n


def change_diff(n):
    e = next((e for e in history() if e["n"] == n), None)
    if e is None:
        return ""
    return diff_text({f: _stored(n, "before", f) for f in e["files"]}, {f: _stored(n, "after", f) for f in e["files"]},
                     e["files"])


def merge3(current, base, other):
    """Take the file as it is now and apply just the mod's own change (base -> other) to it, keeping every
    other change made since. Returns the new bytes, or None if the same lines were changed again since."""
    if current is None or base is None or other is None:  # made or deleted by the mod
        return other if current == base else (current if current == other else None)
    crlf = b"\r\n" in current  # (Windows line endings or not: compare the words, keep the file's own style)
    current, base, other = (d.replace(b"\r\n", b"\n") for d in (current, base, other))
    merged = other if current in (base, other) else None
    if merged is None:
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, data in (("current", current), ("base", base), ("other", other)):
                path = os.path.join(d, name)
                with open(path, "wb") as f:
                    f.write(data)
                paths.append(path)
            r = subprocess.run(["git", "merge-file", "-p", "--quiet", *paths], capture_output=True)
        if r.returncode != 0:
            return None
        merged = r.stdout
    return merged.replace(b"\n", b"\r\n") if crlf else merged


def _switch(n, to):
    """Switch a mod off (to = "before") or on (to = "after"), changing only the mod's own lines."""
    log = history()
    e = next((e for e in log if e["n"] == n), None)
    if e is None:
        return {"ok": False, "message": f"No mod {n}"}
    if e["status"] == "merged":
        return {"ok": False, "message": f"Mod {n} is merged into the game, so it can't be switched off"}
    frm = "after" if to == "before" else "before"
    new, clashes = {}, []
    for f in e["files"]:
        result = merge3(_current(f), _stored(n, frm, f), _stored(n, to, f))
        if result is None and _stored(n, to, f) is not None:
            clashes.append(f)
        else:
            new[f] = result
    if clashes:
        return {"ok": False, "clashes": clashes,
                "message": f"Mod {n} can't be switched {'off' if to == 'before' else 'on'} cleanly: the same lines of "
                           f"{', '.join(clashes)} have been changed again since. Nothing was changed. Press Open in "
                           "editor to see the mod's lines."}
    for f, data in new.items():
        _put(f, data)
    e["status"] = "rolled back" if to == "before" else "kept"
    e.setdefault("events", []).append(f"{datetime.datetime.now():%Y-%m-%d %H:%M} "
                                      f"{'switched off' if to == 'before' else 'switched on'}")
    _save_history(log)
    return {"ok": True, "files": e["files"], "message": ""}


def rollback(n):
    return _switch(n, "before")


def reapply(n):
    return _switch(n, "after")


def merge(n):
    """Accept a mod as a permanent part of the game: it stays in, and can't be switched off any more."""
    log = history()
    e = next((e for e in log if e["n"] == n), None)
    if e is None:
        return {"ok": False, "message": f"No mod {n}"}
    if e["status"] != "kept":
        return {"ok": False, "message": "Switch the mod on before merging it into the game"}
    e["status"] = "merged"
    e["merged"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    e.setdefault("events", []).append(f"{e['merged']} merged into the game")
    _save_history(log)
    return {"ok": True, "message": ""}


def open_in_editor(n):
    """Save the full changes as a file and open it (Windows: in the default text editor)."""
    path = os.path.join(CHANGES, str(n), "changes.diff")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(change_diff(n) or "(no changes)")
    try:
        os.startfile(path)  # noqa: attribute exists on Windows
    except (AttributeError, OSError):
        pass
    return path


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    target, learner, goal = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
    change = AIChange(0, learner, {"goal": goal, "variables": "", "test": "Run robot_wars.py and look",
                                   "predict": ""}, target, design=None)
    res = change.run()
    print(json.dumps({k: v for k, v in res.items() if k != "diff"}, indent=2))
    print(res["diff"])
    if input("Keep this change? (y/n) ").strip().lower() == "y":
        print("Kept as change", change.keep())
    else:
        change.undo()
        print("Undone.")
