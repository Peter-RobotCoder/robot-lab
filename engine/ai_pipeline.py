"""Teacher-approved AI changes ("vibe coding" through the teacher): the engine's, for every game.

A game describes what is its own in a Game (see the class below: its folders, its files, its words for the
prompt) and calls setup(); its own ai_pipeline.py then offers these names.

A learner's AI request card, once the teacher approves it, goes to Claude Code on the teacher's computer:
  1. a snapshot of the project's files is taken, so any change can be undone
  2. Claude is given only file tools (no commands) and told what it may change
  3. any change outside that is put back as it was
  4. the change is tested: the mods and a test fight, and for code changes the whole game (smoke_test.py)
  5. the teacher sees what changed and presses Keep or Undo
  6. every kept change becomes a mod in the change history (ai_changes/): it can be looked at, switched off
     and on again (only the mod's own lines change, so later work is kept), and finally merged into the game
     as a permanent update. Nothing is committed to git automatically: commit when you choose to.
  7. a change that adds a user mod (USER_MODS in the game's sim) is named after the learner who asked for it, when it is
     kept and again when it is merged: "Sam's Spike pit". The name is kept in ai_changes/user_mod_makers.json
     (with the class's data, never in the code) and the teacher's window passes it on to the class server.

What Claude may change:
  the learner's design file (mods/robots or mods/fighters), the world's file (mods/arena.py, mods/stage.py),
  mods/rules.py, or "game": anything in the game: every .py file and the mods, including new files. Only the
  safety parts stay locked: this file, the learner-code sandbox, the password code, where updates come from
  (the game's version file) and the tests.
If a smaller request needs more than it was given, Claude says so and the teacher can send it again as "game".
Try it from a game's folder:  python ai_pipeline.py robot Sam "Make my robot blue with yellow lights"
"""
import ast
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

class Game:
    """What a game tells the pipeline. home: the game's folder. data: its data folder (the change history goes
    in data/ai_changes). protected: files Claude never changes; skip_dirs: folders left out of snapshots. The
    targets: design_target ("robot") with its folder (design_dir, "mods/robots") and variable (design_var,
    "ROBOT"); world_target ("arena") with its file (world_file). design_text(design, learner): a design file's
    text; sim(): the sim module; sim_file ("lab_sim.py": where USER_MODS lives); rules_limits(): {name: (lo, hi)}
    from the mods module; mods_test ("rw_mods.py"); showcase ("robot_wars.py"); the prompt's words: intro ("their
    Robot Wars game"), needs_game_examples, mod_files_text(sim, settings_text), game_guide, user_mod_guide."""

    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.target_names = {self.design_target: f"the learner's {self.design_target} file",
                             self.world_target: f"the {self.world_target} file", "rules": "the rules file",
                             "game": "the whole game"}


G = None  # the game, from setup()
HERE = DATA = CHANGES = MAKERS = None
PROTECTED, SKIP_DIRS, TARGET_NAMES = set(), set(), {}
CLAUDE = shlex.split(os.environ.get("CLAUDE_CMD", "claude"))  # CLAUDE_CMD lets tests use a stand-in
NEEDS_GAME = "NEEDS THE WHOLE GAME"


def setup(game):
    """Called once by a game's ai_pipeline.py."""
    global G, HERE, DATA, CHANGES, MAKERS, PROTECTED, SKIP_DIRS, TARGET_NAMES
    G = game
    HERE, DATA = game.home, game.data
    CHANGES = os.path.join(DATA, "ai_changes")
    MAKERS = os.path.join(CHANGES, "user_mod_makers.json")  # who made each user mod: {"spike_pit": "Sam"}
    PROTECTED, SKIP_DIRS, TARGET_NAMES = set(game.protected), set(game.skip_dirs), dict(game.target_names)


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
    if target == G.design_target:
        return rel == f"{G.design_dir}/{slug(learner)}.py"
    if target == G.world_target:
        return rel == G.world_file
    if target == "rules":
        return rel == "mods/rules.py"
    if target == "game":
        top = rel.split("/")[0]
        return (rel.endswith(".py") or rel.startswith("mods/")) and rel not in PROTECTED and top not in SKIP_DIRS \
            and ".." not in rel
    return False


def allowed_files(target, learner, allow_engine=True):
    """What the prompt tells Claude it may change."""
    if target == G.design_target:
        return [f"{G.design_dir}/{slug(learner)}.py"]
    if target == G.world_target:
        return [G.world_file]
    if target == "rules":
        return ["mods/rules.py"]
    if target == "game":
        return ["any file of the game (the .py files and everything in mods/), and new files if they're needed",
                "except these, which must not be changed: " + ", ".join(sorted(PROTECTED))]
    raise ValueError(f"Unknown target: {target}")


def build_prompt(card, learner, target, files, as_user_mod=False):
    sim = G.sim()
    limits = "\n".join(f"  - {k}: {lo} to {hi}" for k, (lo, hi) in G.rules_limits().items())
    settings = "\n".join(f"  - {k}: {lo} to {hi}" for k, (lo, hi, _, _) in sim.SETTINGS.items())
    if target == "game":
        scope = f"""The teacher has checked and approved this request, and allows you to change {files[0]},
{files[1]}.

{G.game_guide}""" + (f"\n\n{G.user_mod_guide}" if as_user_mod else "")
    else:
        scope = f"""The teacher has checked and approved this request. Make the change by editing ONLY these files:
{chr(10).join('  - ' + f for f in files)}
If the request needs anything outside these files (for example {G.needs_game_examples}), change nothing and begin your reply with exactly "{NEEDS_GAME}:" followed by one sentence
saying what would need to change. The teacher can then send it again with the whole game allowed."""
    return f"""You are helping a 13-18 year old learner in a coding club change {G.intro}.
{scope}

LEARNER'S REQUEST (first name only: {learner})
  Goal: {card.get('goal', '').strip()}
  Variables / values: {card.get('variables', '').strip()}
  How they will test it: {card.get('test', '').strip()}
  Their prediction: {card.get('predict', '').strip()}

HOW THE MOD FILES WORK
{G.mod_files_text(sim, settings)}
- mods/rules.py holds RULES = {{...}} with these numbers and limits:
{limits}
- Mod files must stay plain data: one dictionary, comments allowed, no imports, functions or other code.

RULES FOR YOUR CHANGE
- Keep values inside the limits above (a whole-game change may change the limits themselves in {G.mods_module}).
- Don't add anything that wasn't asked for. Keep comments short and clear.
- Finish with 3-5 short bullet points: what you changed (file, what, old -> new) and one thing the learner should
  check when they test it. Don't include any personal information.
"""


def save_prompt(card_id, learner, target, prompt):
    """Keep a prompt that goes to Claude, whole, with the card's number: ai_requests/003_sam_game_<when>_prompt.md
    (on the teacher's laptop, with the class's other data). Returns the file's name."""
    folder = os.path.join(DATA, "ai_requests")
    os.makedirs(folder, exist_ok=True)
    when = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    name = f"{int(card_id):03d}_{slug(learner)}_{target}_{when}_prompt.md"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(prompt)
    return name


def run_tests(changed):
    """Mods and a test fight; if code changed, the whole game (smoke_test.py). Returns (ok, text)."""
    code = any(f.endswith(".py") and not f.startswith("mods/") for f in changed)
    script = "smoke_test.py" if code else G.mods_test
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, script)], cwd=HERE, capture_output=True, text=True,
                           timeout=400)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return False, f"{script} took too long"


class AIChange:
    """One learner request going through Claude. Call run(), then keep() or undo()."""

    def __init__(self, card_id, learner, card, target, design=None, allow_engine=True, as_user_mod=False):
        if target not in TARGET_NAMES:
            raise ValueError(f"Unknown target: {target}")
        self.id, self.learner, self.card, self.target = card_id, learner, card, target
        self.as_user_mod = as_user_mod and target == "game"  # a feature the teacher switches on and off
        self.design = design
        self.files = allowed_files(target, learner)
        self.before, self.after = {}, {}
        self.changed = []
        self.user_mods = []  # the user mods this change added (known once it's kept)
        self.prompt, self.prompt_file = "", ""  # exactly what was sent to Claude, and the file it is kept in
        self.result = {}

    def run(self, progress=print, timeout=None):
        self.before = snapshot_files()  # before the robot file is made, so Undo removes a new one
        stub = None
        if self.target == G.design_target:
            rel = f"{G.design_dir}/{slug(self.learner)}.py"
            path = os.path.join(HERE, rel)
            if not os.path.exists(path):
                sim = G.sim()
                # the learner's current design, or a starter one if they aren't connected right now
                design = self.design if not sim.check_design(self.design or {}) else sim.default_design(self.learner)
                stub = G.design_text(design, self.learner).encode("utf-8")
                with open(path, "wb") as f:
                    f.write(stub)
        progress("Claude is working on it...")
        whole = self.target == "game"
        prompt = self.prompt = build_prompt(self.card, self.learner, self.target, self.files, self.as_user_mod)
        try:
            self.prompt_file = save_prompt(self.id, self.learner, self.target, prompt)  # every sent prompt is kept
        except OSError:
            pass
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
        if stub is not None:  # the starter design file we made isn't a change unless Claude changed it
            rel = f"{G.design_dir}/{slug(self.learner)}.py"
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
    change.user_mods = sorted(user_mod_keys(change.after.get(G.sim_file)) -
                              user_mod_keys(change.before.get(G.sim_file)))
    log.append({"n": n, "card": change.id, "learner": change.learner, "goal": change.card.get("goal", "")[:200],
                "target": change.target, "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "files": change.changed, "summary": change.result.get("summary", "")[:600], "status": "kept",
                "new_files": [f for f in change.changed if change.before.get(f) is None],
                "user_mods": change.user_mods, "prompt": getattr(change, "prompt_file", "")})
    _save_history(log)
    name_user_mods(change.user_mods, change.learner)
    return n


# ---------- who made each user mod: its maker's name goes in front ("Sam's Spike pit") ----------

def user_mod_keys(source):
    """The user mods in a copy of the game's sim (its bytes, or None): the keys of USER_MODS."""
    try:
        tree = ast.parse(source or b"")
    except (SyntaxError, ValueError):
        return set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) and any(
                isinstance(t, ast.Name) and t.id == "USER_MODS" for t in node.targets):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()


def maker_name(text):
    """A maker's name as it's kept and shown: a learner's username (letters, numbers and spaces)."""
    return re.sub(r"[^A-Za-z0-9 ]", "", str(text)).strip()[:12]


def user_mod_makers():
    """Who made each user mod: {key: name}. ("" = the maker's data was deleted: the mod stays, without a name.)"""
    try:
        with open(MAKERS, encoding="utf-8") as f:
            makers = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(makers, dict):
        return {}
    return {k: maker_name(v) for k, v in makers.items() if isinstance(v, str)}


def save_user_mod_makers(makers):
    os.makedirs(CHANGES, exist_ok=True)
    with open(MAKERS + ".tmp", "w", encoding="utf-8") as f:
        json.dump(makers, f, indent=2, sort_keys=True)
    os.replace(MAKERS + ".tmp", MAKERS)


def name_user_mods(keys, learner):
    """These user mods were made for this learner: remember it, so their name goes in front of each one."""
    who = maker_name(learner)
    if keys and who:
        save_user_mod_makers(user_mod_makers() | {k: who for k in keys})


def forget_user_mod_makers(keys):
    """Take the maker's name off these user mods (their data was deleted on the class server)."""
    makers = user_mod_makers()
    if any(k in makers for k in keys):
        save_user_mod_makers({k: v for k, v in makers.items() if k not in keys})


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
    if "user_mods" not in e:  # (kept before user mods were named after their makers)
        e["user_mods"] = sorted(user_mod_keys(_stored(n, "after", G.sim_file)) -
                                user_mod_keys(_stored(n, "before", G.sim_file)))
    _save_history(log)
    name_user_mods(e["user_mods"], e["learner"])  # the learner's name goes in front of the user mods it added
    return {"ok": True, "message": "", "user_mods": e["user_mods"]}


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


def main():
    """python ai_pipeline.py <target> <learner> <goal>: a request from a terminal (run from a game's folder)."""
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    target, learner, goal = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
    change = AIChange(0, learner, {"goal": goal, "variables": "", "test": f"Run {G.showcase} and look",
                                   "predict": ""}, target, design=None)
    res = change.run()
    print(json.dumps({k: v for k, v in res.items() if k != "diff"}, indent=2))
    print(res["diff"])
    if input("Keep this change? (y/n) ").strip().lower() == "y":
        print("Kept as change", change.keep())
    else:
        change.undo()
        print("Undone.")
