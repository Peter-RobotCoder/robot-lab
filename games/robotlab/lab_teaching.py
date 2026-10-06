"""Robot Lab teaching layer: lessons, missions, evidence, learners' brains and AI request cards.

The server calls into this. Everything a learner achieves is saved as evidence against the
learning outcomes in lab_missions.py, so the teacher can see (and export) who has shown what.
"""
import csv
import datetime
import json
import os
import re

import lab_brain
import lab_missions as lm
import lab_profiles
import lab_sim as sim
import rw_mods
from ai_pipeline import robot_file_text, slug

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ROBOTLAB_DATA", HERE)  # (tests point this somewhere else)
EVIDENCE_DIR = os.path.join(DATA, "evidence")
CARDS_DIR = os.path.join(DATA, "ai_requests")
ROBOTS_DIR = os.path.join(DATA, "mods", "robots")  # learners' robots: with the rest of their data (one set per class)


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def design_changes(old, new):
    """What a build changed, by variable name as the code editor shows them: ['turn_speed 80 -> 100', ...]."""
    out = []
    for key, var in (("name", "robot_name"), ("colour", "colour"), ("weapon", "weapon"), ("model", "model")):
        if old.get(key) != new.get(key):
            out.append(f"{var} {old.get(key)!r} -> {new.get(key)!r}")
    for k, v in new.get("points", {}).items():
        if old.get("points", {}).get(k) != v:
            out.append(f"{k}_points {old.get('points', {}).get(k)} -> {v}")
    for k, v in new.get("settings", {}).items():
        if old.get("settings", {}).get(k) != v:
            out.append(f"{k} {old.get('settings', {}).get(k)} -> {v:g}")
    return out


class Record:
    """Everything the teaching layer remembers about one learner (kept if they reconnect)."""

    def __init__(self, name):
        self.name = name
        self.done = {}             # mission id -> {"time", "detail"}
        self.text = {}             # mission id -> reflection text
        self.prediction = None     # predicted top speed, km/h
        self.top_speed = 0.0       # fastest forward speed since the last build, km/h
        self.hits_at_build = 0
        self.built = False         # has built at least one design
        self.code_viewed = False
        self.brain = None          # lab_brain.Autopilot
        self.brain_features = set()
        self.autopilot = False


class Teaching:
    def __init__(self, server):
        self.server = server
        self.records = {}
        self.profiles = {}  # learner name -> their saved profile
        self.cards = []
        self.accounts = lab_profiles.all_names()  # every learner account on this server (for the teacher)
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        os.makedirs(CARDS_DIR, exist_ok=True)
        self.evidence_file = os.path.join(EVIDENCE_DIR, f"evidence_{datetime.date.today()}.json")
        if os.path.exists(self.evidence_file):  # carry on from earlier today
            with open(self.evidence_file) as f:
                saved = json.load(f)
            for name, data in saved.get("learners", {}).items():
                r = self.record(name)
                r.done, r.text = data.get("done", {}), data.get("text", {})
            self.cards = saved.get("cards", [])

    def record(self, name):
        return self.records.setdefault(name, Record(name))

    # ---------- profiles: a learner's work, kept between lessons ----------
    def login(self, p):
        """A learner has logged in: bring back their missions, reflections, prediction, brain and autopilot."""
        prof, r = p.profile, self.record(p.name)
        self.profiles[p.name] = prof
        if p.name not in self.accounts:  # a new profile (laptop-only test servers)
            self.accounts = lab_profiles.all_names()
        saved = prof.get("record", {})
        r.done = {**saved.get("done", {}), **r.done}
        r.text = {**saved.get("text", {}), **r.text}
        if r.prediction is None:
            r.prediction = saved.get("prediction")
        if r.brain is None and prof.get("brain"):
            try:
                fn, fname = lab_brain.load_brain(prof["brain"], p.name)
                r.brain = lab_brain.Autopilot(fn, fname)
                r.brain_features = lm.brain_features(prof["brain"])
                r.autopilot = bool(prof.get("autopilot"))
            except lab_brain.BrainError:
                pass

    def save_profile(self, name):
        prof = self.profiles.get(name)
        if prof is None:
            return
        r = self.record(name)
        prof["record"] = {"done": r.done, "text": r.text, "prediction": r.prediction}
        prof["autopilot"] = r.autopilot
        lab_profiles.save(prof)

    @property
    def lesson_number(self):
        return self.server.lesson.get("lesson_number", 1)

    # ---------- lessons ----------
    def apply_lesson(self, n):
        """Switch on the tools, hazards and mode for lesson n."""
        preset = lm.LESSONS[n]
        L = self.server.lesson
        L["lesson_number"] = n
        L["mode"] = preset["mode"]
        L["hazards"] = dict(preset["hazards"])
        L["tools"] = json.loads(json.dumps(preset["tools"]))

    # ---------- missions ----------
    def complete(self, name, mission, detail, by_teacher=False):
        r = self.record(name)
        if mission in r.done:
            return False
        if not by_teacher and lm.MISSIONS[mission][0] != self.lesson_number:
            return False  # missions count in their own lesson, so evidence matches the plan
        r.done[mission] = {"time": now_text(), "detail": detail}
        title = lm.MISSIONS[mission][1]
        self.server.arena.events.append((self.server.arena.time, f"{name} completed: {title}"))
        self.save()
        return True

    def on_design(self, p, new, problems, accepted, old=None, by_code=False):
        """Called after a learner presses Build: valid or not. old: their design before this build; by_code: the
        build came from the code editor (Mission 1's objective d), not the Garage's buttons (a, b and c)."""
        if p.role != "learner":
            return
        r = self.record(p.name)
        if problems:
            if any("points used" in x or "must be" in x for x in problems):
                self.complete(p.name, "2b", f"Rejected: {problems[0]}")
            return
        r.built = True
        r.top_speed = 0.0
        r.hits_at_build = p.robot.hits if p.robot else 0
        defaults = {k: v[2] for k, v in sim.SETTINGS.items()}
        old = old or {}
        if by_code:
            changed = design_changes(old, new)
            if changed:
                self.complete(p.name, "1d", "Changed in the code: " + ", ".join(changed))
        else:
            was = old.get("name", p.name)
            if new["name"] != was:
                self.complete(p.name, "1a", f'robot_name "{was}" became "{new["name"]}" (a string, with the GUI)')
            s = new["settings"]
            if s["turn_speed"] != defaults["turn_speed"] and s["size"] != defaults["size"]:
                self.complete(p.name, "1b", f"turn_speed = {s['turn_speed']:g}, size = {s['size']:g} "
                                            "(integers, with the GUI)")
            if new["colour"] != old.get("colour", p.start_colour):
                self.complete(p.name, "1c", f"colour = {new['colour']} (a list, with the GUI)")
        limits = self.server.lesson["limits"]  # (the points to share and each point's range are the teacher's)
        if sum(new["points"].values()) == limits["points_total"]:
            self.complete(p.name, "2a", "Points " + ", ".join(f"{k} {v}" for k, v in new["points"].items()))
        edge = [k for k, v in new["points"].items() if v in limits["points"][k]]
        if edge:
            self.complete(p.name, "2c", "Boundary value accepted: " + ", ".join(f"{k} = {new['points'][k]}" for k in edge))

    def tick(self, now):
        """Every half second: checks that need watching over time."""
        for p in self.server.learners():
            r, robot = self.record(p.name), p.robot
            if robot is None or robot not in self.server.arena.robots:
                continue
            r.top_speed = max(r.top_speed, robot.speed * 3.6)
            if r.built and robot.hits - r.hits_at_build >= 3 and len(r.text.get("2d", "").split()) >= 8:
                self.complete(p.name, "2d", f"{robot.hits - r.hits_at_build} hits after rebuilding. Why: {r.text['2d']}")
            if r.brain and r.autopilot and r.brain.seconds_running(now) >= 20:
                self.complete(p.name, "3a", f"Brain ran for {r.brain.seconds_running(now):.0f} s without an error")
            if (self.lesson_number == 5 and not self.server.arena.practice and r.built and r.brain
                    and not r.brain.error):
                self.complete(p.name, "5a", "Entered the final battle with their own design and brain")

    # ---------- messages from learners and the teacher ----------
    def on_message(self, p, m):
        """Returns a list of (websocket, message) replies, or None if the message isn't for us."""
        kind, r = m.get("type"), self.record(p.name)
        if kind == "prediction":
            try:
                r.prediction = max(0.0, min(200.0, float(m["value"])))
            except (TypeError, ValueError):
                return [(p.ws, {"type": "notice", "text": "Type a number for your prediction."})]
            r.top_speed = 0.0
            return [(p.ws, self.missions_msg(p))]
        if kind == "reflection":
            mission = m.get("mission")
            text = re.sub(r"\s+", " ", str(m.get("text", "")))[:600]
            if mission in ("2d", "5b"):
                r.text[mission] = text
                if mission == "5b" and len(text.split()) >= 20:
                    self.complete(p.name, "5b", text)
                self.save()
            return [(p.ws, self.missions_msg(p))]
        if kind == "code_viewed":
            r.code_viewed = True
            return []
        if kind == "prefs":  # camera view, half-typed AI card and so on: kept in the learner's profile
            prof = self.profiles.get(p.name)
            if prof is not None and isinstance(m.get("prefs"), dict) and len(json.dumps(m["prefs"])) < 8000:
                prof["prefs"] = m["prefs"]
                lab_profiles.save(prof)
            return []
        if kind == "brain":
            return [(p.ws, self.upload_brain(p, str(m.get("source", ""))))] + [(p.ws, self.missions_msg(p))]
        if kind == "autopilot":
            if r.brain is None:
                return [(p.ws, {"type": "notice", "text": "Upload a brain first (press U)."})]
            r.autopilot = not r.autopilot
            if r.autopilot:
                r.brain.error, r.brain.started, r.brain.memory = None, None, {}
            self.attach(p)
            self.save_profile(p.name)
            return [(p.ws, self.missions_msg(p))]
        if kind == "ai_card":
            return [(p.ws, self.submit_card(p, m.get("card", {})))] + self.teacher_update()
        if kind == "ai_review":
            return [(p.ws, self.submit_review(p, m))] + self.teacher_update()
        if p.role == "teacher":
            if kind == "lesson_number":
                self.apply_lesson(int(m["n"]))
                self.server.rebuild_arena()
                return "broadcast"
            if kind == "view_learner":  # the teacher's learner view: that learner's missions, as they see them
                q = next((x for x in self.server.learners() if x.name == m.get("name")), None)
                if q is None:
                    return [(p.ws, {"type": "notice", "text": "That learner isn't connected."})]
                return [(p.ws, self.missions_msg(q) | {"for": q.name})]
            if kind == "set_password":
                try:
                    lab_profiles.set_password(m.get("learner", ""), str(m.get("password", "")))
                    text = f"New password set for {m.get('learner')}"
                except lab_profiles.LoginError as e:
                    text = str(e)
                return [(p.ws, {"type": "notice", "text": text})]
            if kind == "add_learner":
                try:
                    prof = lab_profiles.create(m.get("learner", ""), str(m.get("password", "")))
                    self.accounts = lab_profiles.all_names()
                    text = f"Account made for {prof['name']}"
                except lab_profiles.LoginError as e:
                    text = str(e)
                return [(p.ws, {"type": "notice", "text": text})] + self.teacher_update()
            if kind == "tick":
                if m.get("mission") in lm.MISSIONS and m.get("learner"):
                    self.complete(m["learner"], m["mission"], "Checked by the teacher", by_teacher=True)
                return self.teacher_update() + self.learner_updates()
            if kind == "card_status":
                return self.set_card_status(int(m["id"]), m.get("status"), m.get("note", ""))
            if kind == "export":  # saved on the server, and a copy sent to the teacher's own computer
                path = self.export()
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                return [(p.ws, {"type": "evidence_csv", "name": os.path.basename(path), "text": text})]
            if kind == "mods_update":
                msg = self.apply_mods(m.get("files", {}))
                return [(p.ws, {"type": "notice", "text": msg})] + ["broadcast"]
        return None

    # ---------- brains ----------
    def upload_brain(self, p, source, loaded=None):
        """loaded: (brain, fname) or a BrainError, when the server has already loaded it away from the game loop."""
        r = self.record(p.name)
        try:
            if isinstance(loaded, Exception):
                raise loaded
            fn, fname = loaded or lab_brain.load_brain(source, p.name)
        except lab_brain.BrainError as e:
            return {"type": "brain_result", "ok": False, "error": str(e)}
        if r.brain is not None:  # the old brain's process stops
            r.brain.close()
        r.brain = lab_brain.Autopilot(fn, fname)
        r.brain_features = lm.brain_features(source)
        if p.name in self.profiles:  # kept, so it's still there next lesson
            self.profiles[p.name]["brain"] = source
            self.save_profile(p.name)
        if "if" in r.brain_features:
            self.complete(p.name, "3b", "Brain uses if / elif / else")
        if "own_function" in r.brain_features:
            self.complete(p.name, "3c", "Brain calls its own helper function")
        if "memory" in r.brain_features:
            self.complete(p.name, "3d", "Brain keeps state in me.memory")
        self.attach(p)
        return {"type": "brain_result", "ok": True,
                "error": "Uploaded. Press P to switch autopilot " + ("off." if r.autopilot else "on.")}

    def attach(self, p):
        """Give a learner's robot their brain when autopilot is on (also after a rebuild)."""
        r = self.record(p.name) if p.role == "learner" else None
        if p.robot is None:
            return
        p.robot.brain = r.brain if (r and r.brain and r.autopilot) else None

    # ---------- AI request cards ----------
    def submit_card(self, p, card):
        target = card.get("target") if card.get("target") in lm.AI_TARGETS else "robot"
        card = {k: str(card.get(k, ""))[:400] for k in ("goal", "variables", "test", "predict")} | \
               {k: bool(card.get(k)) for k in ("privacy", "review", "credit")} | {"target": target}
        problems, tips = lm.check_ai_card(card)
        if problems:
            return {"type": "ai_card_result", "ok": False, "problems": problems, "tips": tips}
        cid = max([c["id"] for c in self.cards], default=0) + 1
        entry = {"id": cid, "learner": p.name, "time": now_text(), "card": card, "status": "waiting", "note": "",
                 "review": None}
        self.cards.append(entry)
        with open(os.path.join(CARDS_DIR, f"{cid:03d}_{p.name}.md"), "w", encoding="utf-8") as f:
            f.write(lm.ai_prompt(card, p.name))
        mission = lm.AI_CARD_MISSION.get(self.lesson_number)
        if mission:
            self.complete(p.name, mission, f"AI request #{cid} ({lm.AI_TARGETS[target]}): {card['goal']}")
        return {"type": "ai_card_result", "ok": True, "problems": [], "tips": tips}

    def set_card_status(self, cid, status, note):
        card = next((c for c in self.cards if c["id"] == cid), None)
        if card and status in ("waiting", "sent", "working", "ready", "rejected"):
            card["status"], card["note"] = status, note[:200]
            if status == "ready":  # a JCQ-style record of where AI helped: tool and date
                card["acknowledgement"] = f"AI tool: Claude, used by the teacher on {datetime.date.today():%d %B %Y}"
            self.save()
        return self.teacher_update() + self.learner_updates()

    def submit_review(self, p, m):
        card = next((c for c in self.cards if c["id"] == m.get("id") and c["learner"] == p.name), None)
        if card is None or card["status"] != "ready":
            return {"type": "notice", "text": "That request isn't ready for review yet."}
        answers = {k: re.sub(r"\s+", " ", str(m.get("answers", {}).get(k, "")))[:300] for k in lm.REVIEW_QUESTIONS}
        short = [q for q, a in answers.items() if len(a.split()) < 3]
        if short:
            return {"type": "notice", "text": "Answer every review question in a few words."}
        card["review"], card["status"] = answers, "reviewed"
        mission = lm.AI_REVIEW_MISSION.get(self.lesson_number)
        if mission:
            review = f"Reviewed AI change #{card['id']}: " + " | ".join(answers.values())
            if not self.complete(p.name, mission, review):
                r = self.record(p.name)  # (Mission 1: sending the card did the objective; the review is its second
                if mission in r.done:    # half, so it goes on the record too)
                    r.done[mission]["detail"] = (r.done[mission]["detail"] + " || " + review)[:1200]
                    self.save()
        return self.missions_msg(p)

    # ---------- what each screen is sent ----------
    def missions_msg(self, p):
        r = self.record(p.name)
        words = lambda text: lm.points_words(text, self.server.lesson["limits"])  # noqa: E731
        missions = [{"id": k, "title": words(v[1]), "text": words(v[2]), "outcomes": v[3], "check": v[4],
                     "done": k in r.done, "detail": r.done.get(k, {}).get("detail", "")}
                    for k, v in lm.missions_for(self.lesson_number).items()]
        return {"type": "missions", "lesson": self.lesson_number,
                "title": words(lm.LESSONS[self.lesson_number]["title"]),
                "missions": missions, "prediction": r.prediction, "top_speed": round(r.top_speed, 1),
                "text": r.text, "brain": bool(r.brain), "autopilot": r.autopilot,
                "brain_error": r.brain.error if r.brain else None,
                "cards": [c for c in self.cards if c["learner"] == p.name],
                "review_questions": lm.REVIEW_QUESTIONS, "card": self.card_data(p.name)}

    def card_data(self, name):
        """A learner's own card: the outcomes they've shown so far in this game, and what they did each day."""
        done = self.record(name).done
        outcomes = {o: sum(1 for mid in done if o in lm.MISSIONS[mid][3]) for o in lm.OUTCOMES}
        days = {}
        for mid, info in done.items():
            if mid not in lm.MISSIONS:
                continue
            day = str(info.get("time", ""))[:10] or "earlier"
            days.setdefault(day, []).append({"id": mid, "title": lm.MISSIONS[mid][1], "outcomes": lm.MISSIONS[mid][3],
                                             "lesson": lm.MISSIONS[mid][0], "time": info.get("time", "")})
        history = [{"date": day, "missions": sorted(ms, key=lambda m: m["time"])} for day, ms in sorted(days.items(),
                                                                                                        reverse=True)]
        return {"outcomes": outcomes, "outcome_names": {o: v[0] for o, v in lm.OUTCOMES.items()}, "history": history}

    def session_report(self, since, present):
        """What happened in the live session, for the club desk: who was here, what each learner completed
        (missions and their outcomes) since it started, and the AI cards handled."""
        done = {}
        for name, r in self.records.items():
            new = {mid: {"time": info.get("time", ""), "detail": info.get("detail", ""), "title": lm.MISSIONS[mid][1],
                         "outcomes": lm.MISSIONS[mid][3], "check": lm.MISSIONS[mid][4]}
                   for mid, info in r.done.items() if mid in lm.MISSIONS and str(info.get("time", "")) >= since}
            if new:
                done[name] = new
        cards = [{"id": c["id"], "learner": c["learner"], "status": c["status"], "time": c["time"],
                  "goal": str(c["card"].get("goal", ""))[:120]} for c in self.cards if str(c.get("time", "")) >= since]
        totals = {name: self.card_data(name)["outcomes"] for name in self.records}  # (each learner so far, this game)
        return {"since": since, "present": present, "done": done, "cards": cards, "lesson": self.lesson_number,
                "totals": totals}

    def teacher_update(self):
        t = self.server.teacher()
        if not t:
            return []
        names = [p.name for p in self.server.learners()] or list(self.records)
        grid = {}
        for n in names:
            done = self.record(n).done
            grid[n] = {"missions": sorted(done),
                       "outcomes": {o: sum(1 for mid in done if o in lm.MISSIONS[mid][3]) for o in lm.OUTCOMES}}
        return [(t.ws, {"type": "teaching", "lesson": self.lesson_number, "grid": grid, "cards": self.cards,
                        "accounts": self.accounts,
                        "outcomes": {k: v[:2] for k, v in lm.OUTCOMES.items()},
                        "missions": {k: v[:2] + (v[4],) for k, v in lm.MISSIONS.items()}})]

    def learner_updates(self):
        return [(p.ws, self.missions_msg(p)) for p in self.server.learners()]

    # ---------- mods: robots, arena and rules changed by approved AI requests ----------
    def apply_mods(self, files):
        """Check and save changed mod files, then use them straight away."""
        written = []
        for rel, text in files.items():
            rel = rel.replace("\\", "/")
            name_part = rel[len("mods/robots/"):]
            ok = rel in ("mods/arena.py", "mods/rules.py") or (
                rel.startswith("mods/robots/") and rel.endswith(".py") and "/" not in name_part)
            if not ok:
                return f"Not applied: {rel} isn't a mod file"
            path = os.path.join(ROBOTS_DIR, name_part) if rel.startswith("mods/robots/") else os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".check"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                if rel == "mods/rules.py":
                    rw_mods.read_dict(tmp, "RULES")
                elif rel == "mods/arena.py":
                    rw_mods.read_dict(tmp, "ARENA")
                else:
                    rw_mods.load_robot(tmp)
            except rw_mods.ModError as e:
                os.remove(tmp)
                return f"Not applied: {e}"
            os.replace(tmp, path)
            written.append(rel)
        self.server.reload_mods(written)
        return "Applied: " + ", ".join(written) if written else "Nothing to apply"

    # ---------- deleting a learner (end of course, or a parent asks) ----------
    def delete_learner(self, name):
        """Remove everything the server keeps about a learner: profile, robot, brain, evidence and AI cards.
        The server disconnects them first. Returns a message for the teacher."""
        name = lab_profiles.clean_name(name)
        prof = lab_profiles.load(name) if name else None
        if prof is None:
            return "No account with that username."
        name = prof["name"]
        r = self.records.pop(name, None)
        if r is not None and r.brain is not None:
            r.brain.close()
        self.profiles.pop(name, None)
        lab_profiles.delete(name)
        if os.path.exists(self.robot_file(name)):
            os.remove(self.robot_file(name))
        self.cards = [c for c in self.cards if c["learner"] != name]
        for f in os.listdir(CARDS_DIR):
            if f.endswith(f"_{name}.md"):
                os.remove(os.path.join(CARDS_DIR, f))
        for f in os.listdir(EVIDENCE_DIR):  # earlier days' evidence too
            path = os.path.join(EVIDENCE_DIR, f)
            if f.endswith(".json"):
                try:
                    with open(path, encoding="utf-8") as fh:
                        data = json.load(fh)
                except (OSError, ValueError):
                    continue
                data.get("learners", {}).pop(name, None)
                data["cards"] = [c for c in data.get("cards", []) if c.get("learner") != name]
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2)
            elif f.endswith(".csv"):
                with open(path, newline="", encoding="utf-8") as fh:
                    rows = [row for row in csv.reader(fh) if not row or row[0] != name]
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    csv.writer(fh).writerows(rows)
        self.save()
        self.accounts = lab_profiles.all_names()
        return f"Deleted {name}: profile, robot, brain, evidence and AI cards (backups keep them until they expire)"

    def robot_file(self, name):
        return os.path.join(ROBOTS_DIR, f"{slug(name)}.py")

    def load_saved_design(self, name):
        """A learner's robot from last time, if they have one."""
        path = self.robot_file(name)
        if os.path.exists(path):
            try:
                return rw_mods.load_robot(path)
            except rw_mods.ModError:
                return None
        return None

    def save_design(self, name, design):
        """Autosave a learner's robot to their own mod file (keeping its style)."""
        old = self.load_saved_design(name) or {}
        d = dict(design)
        if "style" in old and "style" not in d:
            d["style"] = old["style"]
        os.makedirs(ROBOTS_DIR, exist_ok=True)
        with open(self.robot_file(name), "w", encoding="utf-8") as f:
            f.write(robot_file_text(d, name))

    # ---------- saving ----------
    def save(self):
        data = {"learners": {n: {"done": r.done, "text": r.text} for n, r in self.records.items()},
                "cards": self.cards}
        with open(self.evidence_file + ".tmp", "w") as f:  # (written whole, then swapped in: a server stopped
            json.dump(data, f, indent=2)                    # part-way through can't leave half a file behind)
        os.replace(self.evidence_file + ".tmp", self.evidence_file)
        for name in self.profiles:
            self.save_profile(name)

    def export(self):
        path = os.path.join(EVIDENCE_DIR, f"evidence_{datetime.date.today()}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Learner", "Mission", "Objective", "Title", "Outcomes", "Curriculum", "When", "Evidence"])
            for n, r in sorted(self.records.items()):
                for mid, info in sorted(r.done.items()):
                    lesson, title, _, outcomes, _ = lm.MISSIONS[mid]
                    w.writerow([n, lesson, mid, title, " ".join(outcomes),
                                " || ".join(lm.OUTCOMES[o][2] for o in outcomes), info["time"], info["detail"]])
        return path
