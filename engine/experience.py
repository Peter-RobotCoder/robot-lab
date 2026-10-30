"""Experiences (CHANGE 210): a game-style first session in any Club Coders game, played in the game itself.

An Experience is the classic opening mission of a first-person game, Club Coders flavour: a coach talks the learner
through objectives one at a time, each worth XP, with ranks, a progress line and a result card. It is not a game of
its own and draws nothing of its own in the world: the learner plays the real game (its window or the browser page,
its garage, code panel, brains, computer players and fights) on the game's own server, and the experience is a layer
of the teaching framework over it (ExperienceMixin, which engine.teaching.Teaching inherits).

Where it runs:
- In a class: the teacher starts it from the experience box on their window or page; every learner has their own
  run; the teacher's box shows each learner's objective, XP and rank, and who has finished (the best result is kept
  in the learner's profile; the evidence file, its CSV and the desk's session report say so too).
- On your own: the app's EXPERIENCES button opens the game's own window with --experience N. The window starts the
  game's own server on this laptop, out of sight (solo_start), with that experience on, and logs in to it. The
  server stops by itself when the window has gone (solo_watch).

A game's missions module has EXPERIENCES = {1: {...}} (the keys: see check_definition) and its Teaching answers the
hooks at the end of ExperienceMixin (what each objective measures). The windows draw it with engine/experience_hud.py,
the page with web/experience.js. The messages: "experience" (a learner's run, every second while one is on, and
{"on": False} once when it ends) and "experience_class" (the teacher's view); a learner sends {"type": "experience",
"do": "skip" | "again" | "action", "action": ...}, the teacher {"type": "experience", "do": "start", "n": 1} or "stop".
"""
import asyncio
import copy
import json
import os
import socket
import subprocess
import sys
import time

# Ranks, by the share of the experience's XP earned (its objectives' XP, the bonus not counted)
RANKS = [(0.0, "Rookie"), (0.2, "Cadet"), (0.45, "Engineer"), (0.7, "Coder"), (0.95, "Club Coder")]
SOLO_NAME = "Player"                       # who you are on your own (the robot's name until the garage changes it)
SOLO_PASSWORD = "experience-on-this-laptop"  # (a profile on this laptop's own server only: nothing to protect)
SOLO_CODE_ENV = ("JOIN_CODE", "TEACHER_CODE", "CLUBCODERS_TICKET_KEY", "CLUBCODERS_LIVE_FILE", "CLUBCODERS_DESK_INBOX")
OBJECTIVE_KEYS = ("id", "title", "say", "hint", "xp")


def check_definition(d):
    """An experience as a game's missions module defines it: problems, or [] when it is fine.
    title, coach (the coach's name), intro (the coach's first words), lesson (the lesson settings it is played in:
    the keys of the server's lesson to set, as a lesson preset's), objectives (each: id, title, say (the coach's
    words when it starts), hint (the line under it), xp, and optionally goal and unit (a measured objective: the
    progress shows as "2.5 of 4 m"; without them the game says when it is done), outcomes (learning outcome codes)
    and solo (the coach's words instead of say when playing on your own)), bonus (optional: id (an objective's),
    title, xp), finish (the coach's last words)."""
    problems = []
    for k in ("title", "coach", "intro", "lesson", "objectives", "finish"):
        if k not in d:
            problems.append(f"no {k}")
    ids = [o.get("id") for o in d.get("objectives", [])]
    if len(set(ids)) != len(ids):
        problems.append("two objectives with one id")
    for o in d.get("objectives", []):
        problems += [f"objective {o.get('id')}: no {k}" for k in OBJECTIVE_KEYS if k not in o]
    if d.get("bonus") and d["bonus"].get("id") not in ids:
        problems.append("the bonus is for an objective it hasn't got")
    return problems


def max_xp(d):
    return sum(o["xp"] for o in d["objectives"])


def rank_of(xp, d):
    top = max_xp(d) or 1
    return [name for share, name in RANKS if xp >= share * top - 1e-9][-1]


def next_rank(xp, d):
    """(the XP needed, the rank's name) of the next rank up, or None at the top."""
    top = max_xp(d) or 1
    return next(([round(share * top + 0.4999), name] for share, name in RANKS if xp < share * top - 1e-9), None)


def stars(result, d):
    """One for finishing, one for every objective done (none skipped), one for the bonus."""
    return 1 + (not result["skipped"]) + bool(result.get("bonus"))


def progress_text(o, value):
    """The objective's line, with how far you've got when it is measured: "Drive 4 metres  (2.5 of 4 m)"."""
    if o.get("goal") is None:
        return o["hint"]
    goal, unit = o["goal"], o.get("unit", "")
    shown = f"{min(value, goal):.1f}" if unit in ("m", "s") and goal < 20 else f"{min(value, goal):.0f}"
    return f"{o['hint']}   ({shown} of {goal:g}{(' ' + unit) if unit else ''})"


def new_run(n):
    return {"n": n, "index": 0, "begun": -1, "value": 0.0, "done": {}, "skipped": [], "bonus": False,
            "started": time.time(), "base": {}, "seq": 0, "say": [0, ""], "toasts": [], "result": None}


class ExperienceMixin:
    """The experience layer of the teaching framework (engine.teaching.Teaching inherits it)."""
    experience = None  # the experience on (its number), or None
    solo = False       # played on your own (the server on your laptop, started by your window: solo_start)

    def experiences(self):
        return getattr(self.g.missions, "EXPERIENCES", {}) or {}

    def experience_def(self, n=None):
        return self.experiences().get(n if n is not None else self.experience)

    # ---------- on and off ----------
    def start_experience(self, n, solo=False):
        """The experience on, for everyone here: the lesson settings it is played in (the ones it changes are put
        back when it stops), and a new run for each learner."""
        d = self.experience_def(n)
        if d is None:
            return False
        L = self.server.lesson
        if self.experience is None:
            self.x_saved = {k: copy.deepcopy(L.get(k)) for k in d["lesson"]}
        for k, v in d["lesson"].items():
            L[k] = copy.deepcopy(v)
        self.experience, self.solo = n, bool(solo) or self.solo
        L["experience"] = n
        for r in self.records.values():
            r.xrun = None
        return True

    def stop_experience(self):
        if self.experience is None:
            return False
        L = self.server.lesson
        for k, v in getattr(self, "x_saved", {}).items():
            if v is None:
                L.pop(k, None)
            else:
                L[k] = v
        self.experience = None
        L["experience"] = 0
        return True

    # ---------- a learner's run ----------
    def xrun(self, r):
        if getattr(r, "xrun", None) is None or r.xrun["n"] != self.experience:
            r.xrun = new_run(self.experience)
        return r.xrun

    def x_objective(self, run):
        objectives = self.experience_def(run["n"])["objectives"]
        return objectives[run["index"]] if run["index"] < len(objectives) else None

    def experience_say(self, name, words):
        """The coach says something to this learner (the game's words: a hint, a bout lost)."""
        run = self.xrun(self.record(name))
        run["seq"] += 1
        run["say"] = [run["seq"], words]

    def experience_toast(self, run, words, kind="good"):
        run["seq"] += 1
        run["toasts"] = (run["toasts"] + [[run["seq"], words, kind]])[-4:]

    def experience_count(self, name, oid, amount=1.0):
        """An event that counts towards an objective (a build, an upload): only while it is the one being done."""
        if self.experience is None:
            return
        run = self.xrun(self.record(name))
        o = self.x_objective(run)
        if o is not None and o["id"] == oid:
            self.x_measuring(run)["value"] += amount

    def experience_done(self, name, oid):
        """The game says this objective is done (an objective with no goal), if it is the one being done."""
        o = self.x_objective(self.xrun(self.record(name))) if self.experience is not None else None
        if o is not None:
            self.experience_count(name, oid, o.get("goal") or 1.0)

    def experience_bonus(self, name, oid):
        """The bonus earned (a knockout): XP on top when its objective completes."""
        if self.experience is None:
            return
        run = self.xrun(self.record(name))
        bonus = self.experience_def(run["n"]).get("bonus")
        if bonus and bonus["id"] == oid and not run["bonus"]:
            run["bonus"] = True

    def experience_tick(self, now):
        """Twice a second (from tick): each learner's objective started, measured and completed."""
        if self.experience is None:
            return
        world = self.g.world(self.server)
        for p in self.server.learners():
            r, unit = self.record(p.name), self.g.unit(p)
            run = self.xrun(r)
            if run["result"] is not None:
                continue
            o = self.x_objective(run)
            if o is None:
                self.finish_experience(p, r, run)
                continue
            if run["begun"] != run["index"]:
                run["begun"] = run["index"]
                self.x_measuring(run)
                if run["index"] == 0:
                    d = self.experience_def(run["n"])
                    run["seq"] += 1
                    run["say"] = [run["seq"], d["intro"] + "  " + self.objective_words(o)]
                else:
                    self.experience_say(p.name, self.objective_words(o))
                self.experience_begin(p, r, o["id"], unit, world, run)
            value = self.experience_value(p, r, o["id"], unit, world, now, run)
            if value is not None:
                run["value"] = float(value)
            if run["value"] >= (o.get("goal") or 1.0):
                self.complete_objective(p, r, run, o)

    @staticmethod
    def x_measuring(run):
        """The run, its measurement (value, base) belonging to the objective being done (a build can count a moment
        before the objective's first tick has started it)."""
        if run.get("for") != run["index"]:
            run["for"], run["value"], run["base"] = run["index"], 0.0, {}
        return run

    def objective_words(self, o):
        return o.get("solo") if self.solo and o.get("solo") else o["say"]

    def complete_objective(self, p, r, run, o, skipped=False):
        d = self.experience_def(run["n"])
        if skipped:
            run["skipped"].append(o["id"])
            self.experience_toast(run, f"Skipped: {o['title']} (no XP)", "grey")
        else:
            bonus = d.get("bonus") if run["bonus"] and (d.get("bonus") or {}).get("id") == o["id"] else None
            before = rank_of(self.run_xp(run), d)
            run["done"][o["id"]] = o["xp"] + (bonus["xp"] if bonus else 0)
            self.experience_toast(run, f"+{o['xp']} XP   {o['title'].upper()} COMPLETE", "good")
            if bonus:
                self.experience_toast(run, f"+{bonus['xp']} XP   {bonus['title'].upper()}", "rank")
            after = rank_of(self.run_xp(run), d)
            if after != before:
                self.experience_toast(run, f"RANK UP: {after.upper()}", "rank")
        self.experience_ended(p, r, o["id"], run)
        run["index"] += 1

    @staticmethod
    def run_xp(run):
        return sum(run["done"].values())

    def finish_experience(self, p, r, run):
        d = self.experience_def(run["n"])
        result = {"xp": self.run_xp(run), "rank": rank_of(self.run_xp(run), d), "done": list(run["done"]),
                  "skipped": list(run["skipped"]), "bonus": run["bonus"] and d.get("bonus", {}).get("id") in run["done"],
                  "seconds": round(time.time() - run["started"]), "when": time.strftime("%Y-%m-%d %H:%M")}
        result["stars"] = stars(result, d)
        run["result"] = result
        run["seq"] += 1
        run["say"] = [run["seq"], d["finish"]]
        best = getattr(r, "xbest", None)
        if best is None:
            best = r.xbest = {}
        was = best.get(str(run["n"]), {})
        best[str(run["n"])] = {"best_xp": max(was.get("best_xp", 0), result["xp"]),
                               "best_stars": max(was.get("best_stars", 0), result["stars"]),
                               "rank": rank_of(max(was.get("best_xp", 0), result["xp"]), d),
                               "finished": was.get("finished", 0) + 1,
                               "best_seconds": min(s for s in (was.get("best_seconds"), result["seconds"]) if s is not None),
                               "first": was.get("first") or result["when"], "last": result}
        world = self.g.world(self.server)
        if hasattr(world, "events"):
            world.events.append((world.time, f"{p.name} finished Experience {run['n']}: {d['title']}"))
        self.experience_finished(p, r, run)
        self.save()

    def experience_message(self, p, m):
        """A learner's or the teacher's "experience" message: replies, as on_message's."""
        do = m.get("do")
        if p.role == "teacher":
            if do == "start":
                try:
                    n = int(m.get("n", 1))
                except (TypeError, ValueError, OverflowError):
                    return []
                if self.start_experience(n):
                    self.g.rebuild(self.server)
                    return "broadcast"
                return [(p.ws, {"type": "notice", "text": "This game has no experience with that number."})]
            if do == "stop" and self.stop_experience():
                self.g.rebuild(self.server)
                return [(p.ws, {"type": "experience", "on": False})] + ["broadcast"]
            return []
        if self.experience is None or p.role != "learner":
            return []
        r = self.record(p.name)
        run = self.xrun(r)
        if do == "skip" and run["result"] is None:
            o = self.x_objective(run)
            if o is not None:
                self.complete_objective(p, r, run, o, skipped=True)
        elif do == "again":
            self.experience_reset(p, r, run)
            r.xrun = None
            self.xrun(r)
        elif do == "action" and isinstance(m.get("action"), str):
            self.experience_action(p, r, m["action"][:40], run)
        return [(p.ws, self.experience_msg(p))]

    # ---------- what the windows are told ----------
    def experience_msg(self, p):
        if self.experience is None:
            return {"type": "experience", "on": False}
        d = self.experience_def()
        r = self.record(p.name)
        run = self.xrun(r)
        o = self.x_objective(run)
        xp = self.run_xp(run)
        rows = []
        for i, ob in enumerate(d["objectives"]):
            state = ("done" if ob["id"] in run["done"] else "skipped" if ob["id"] in run["skipped"] else
                     "now" if i == run["index"] else "todo")
            rows.append({"id": ob["id"], "title": ob["title"], "xp": ob["xp"], "state": state})
        return {"type": "experience", "on": True, "n": run["n"], "title": d["title"], "coach": d["coach"],
                "solo": self.solo, "objectives": rows, "index": run["index"],
                "objective": o["title"] if o else "", "hint": progress_text(o, run["value"]) if o else "",
                "actions": self.experience_actions(p, r, o["id"], run) if o else [],
                "xp": xp, "max_xp": max_xp(d), "rank": rank_of(xp, d), "next": next_rank(xp, d),
                "say": run["say"], "toasts": run["toasts"], "result": run["result"],
                "best": (getattr(r, "xbest", None) or {}).get(str(run["n"]))}

    def experience_class_msg(self):
        """The teacher's view: every learner here, their objective, XP and rank, and who has finished."""
        out = {"type": "experience_class", "on": self.experience is not None, "n": self.experience,
               "available": [{"n": n, "title": d["title"]} for n, d in sorted(self.experiences().items())]}
        if self.experience is None:
            return out
        d = self.experience_def()
        rows = []
        for p in self.server.learners():
            r = self.record(p.name)
            run = self.xrun(r)
            o = self.x_objective(run)
            best = (getattr(r, "xbest", None) or {}).get(str(self.experience)) or {}
            rows.append({"name": p.name, "index": run["index"], "of": len(d["objectives"]),
                         "objective": o["title"] if o else "Finished", "xp": self.run_xp(run),
                         "rank": rank_of(self.run_xp(run), d), "finished": run["result"] is not None,
                         "stars": (run["result"] or {}).get("stars", 0), "best_xp": best.get("best_xp"),
                         "best_stars": best.get("best_stars"), "times": best.get("finished", 0)})
        out.update(title=d["title"], learners=rows, solo=self.solo, max_xp=max_xp(d))
        return out

    def experience_missions(self, r):
        """The learner's Mission tab while an experience is on: its objectives (in order, done or not)."""
        d = self.experience_def()
        run = self.xrun(r)
        return [{"id": f"x{self.experience}:{o['id']}", "title": f"{i}. {o['title']}  (+{o['xp']} XP)",
                 "text": o["say"] + "\n\n" + o["hint"], "outcomes": o.get("outcomes", []), "check": "auto",
                 "done": o["id"] in run["done"], "detail": "skipped" if o["id"] in run["skipped"] else ""}
                for i, o in enumerate(d["objectives"], 1)]

    def experience_report(self, since):
        """For the desk's session report: who finished an experience since it started (from their best)."""
        out = {}
        for name, r in self.records.items():
            for n, best in (getattr(r, "xbest", None) or {}).items():
                last = best.get("last") or {}
                if str(last.get("when", "")) >= since:
                    title = (self.experience_def(int(n)) or {}).get("title", "")
                    out.setdefault(name, []).append({"n": int(n), "title": title, "xp": last.get("xp"),
                                                     "rank": last.get("rank"), "stars": last.get("stars")})
        return out

    # ---------- the game's own: what its objectives measure ----------
    def experience_begin(self, p, r, oid, unit, world, run):
        """An objective starts: keep what it measures from (run["base"]), set up what it needs (on your own the
        game may change its world: a bout's countdown)."""

    def experience_value(self, p, r, oid, unit, world, now, run):
        """How far the learner has got with the objective (compared with its goal), or None when the game counts
        it with experience_count or says so with experience_done."""
        return None

    def experience_ended(self, p, r, oid, run):
        """An objective is over (done or skipped): put back what it changed."""

    def experience_actions(self, p, r, oid, run):
        """Buttons the experience box offers for this objective: [[action, words], ...] (a rematch)."""
        return []

    def experience_action(self, p, r, action, run):
        """One of those buttons was pressed."""

    def experience_reset(self, p, r, run):
        """START AGAIN: put the learner's world back as the experience starts."""

    def experience_finished(self, p, r, run):
        """The last objective is over."""


# ---------- on your own: the game's server on this laptop ----------
def solo_folder(game):
    """Where your own experiences are kept on this laptop (the server's data: your profile, your best results)."""
    return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders", "experiences", game)


def solo_start(here, server_file, game, number, data_env, frozen=False):
    """Start the game's own server on a free port of this laptop, out of sight, with experience `number` on.
    frozen: the downloaded app (its exe runs the server as `Club Coders.exe --serve <game>`). Returns its info.
    A window that reopens itself (a Graphics choice) finds the server it started still there (the environment it
    passes on says where) and carries on with it: the run is kept."""
    key = f"CLUBCODERS_SOLO_{game.upper()}"
    try:
        was = json.loads(os.environ.get(key) or "{}")
    except ValueError:
        was = {}
    if was.get("number") == number and was.get("port"):
        try:
            socket.create_connection(("127.0.0.1", int(was["port"])), timeout=0.5).close()
            return {"pid": was.get("pid"), "port": int(was["port"]), "data": solo_folder(game), "proc": None,
                    "log": os.path.join(solo_folder(game), "server.log"), "host": f"ws://127.0.0.1:{int(was['port'])}"}
        except (OSError, ValueError):
            pass
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    data = solo_folder(game)
    os.makedirs(data, exist_ok=True)
    log = os.path.join(data, "server.log")
    env = dict(os.environ, **{data_env: data}, PYTHONUNBUFFERED="1")
    for key in SOLO_CODE_ENV:
        env.pop(key, None)  # (this laptop's server: the demo codes, no club desk)
    cmd = ([sys.executable, "--serve", game] if frozen else [sys.executable, os.path.join(here, server_file)])
    cmd += ["--port", str(port), "--experience", str(number)]
    with open(log, "w") as out:
        proc = subprocess.Popen(cmd, cwd=here, env=env, stdout=out, stderr=out,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    os.environ[key] = json.dumps({"number": number, "port": port, "pid": proc.pid})  # (for a reopened window)
    return {"pid": proc.pid, "port": port, "data": data, "log": log, "proc": proc,
            "host": f"ws://127.0.0.1:{port}"}


def solo_ready(info, seconds=60):
    """Wait until the server answers (True), or it stops or the time is up (False)."""
    end = time.time() + seconds
    while time.time() < end:
        if info["proc"] is not None and info["proc"].poll() is not None:
            return False
        try:
            socket.create_connection(("127.0.0.1", info["port"]), timeout=0.3).close()
            return True
        except OSError:
            time.sleep(0.15)
    return False


def solo_last_words(info, lines=4):
    try:
        with open(info["log"], encoding="utf-8", errors="replace") as f:
            return " ".join(line.strip() for line in f.read().strip().splitlines()[-lines:])[-400:]
    except OSError:
        return ""


def solo_stop(info):
    if not info or info.get("proc") is None:  # (a server an earlier window started stops by itself: solo_watch)
        return
    try:
        info["proc"].terminate()
    except OSError:
        pass


async def solo_watch(players, first=120.0, after=30.0):
    """On your own, the server stops by itself once your window has gone: nobody connected for `after` seconds
    (or nobody came at all in `first`). players: the server's connected windows."""
    seen, alone_since, start = False, None, time.monotonic()
    while True:
        await asyncio.sleep(1.0)
        now = time.monotonic()
        if players:
            seen, alone_since = True, None
            continue
        if alone_since is None:
            alone_since = now
        if (seen and now - alone_since > after) or (not seen and now - start > first):
            print("Experience: the window has gone, so this laptop's server stops.", flush=True)
            sys.stdout.flush()
            os._exit(0)


def summary(best):
    """A learner's best result in words (the teacher's box, the records)."""
    if not best:
        return ""
    return (f"{best.get('best_xp', 0)} XP, {best.get('rank', '')}, {'*' * int(best.get('best_stars', 0))} "
            f"(finished {best.get('finished', 0)}x)")


if __name__ == "__main__":  # (a quick look at the ranks for an experience worth 260 XP)
    demo = {"objectives": [{"xp": 260}]}
    print(json.dumps([(xp, rank_of(xp, demo), next_rank(xp, demo)) for xp in (0, 52, 117, 182, 247, 260)]))
