"""Fight Lab teaching layer: lessons, missions, evidence, learners' brains and AI request cards.

The server calls into this. Everything a learner achieves is saved as evidence against the
learning outcomes in fight_missions.py, so the teacher can see (and export) who has shown what.
"""
import csv
import datetime
import json
import math
import os
import re

import fight_brain
import fight_missions as fm
import fight_mods
import fight_profiles
import fight_sim as sim
from ai_pipeline import fighter_file_text, slug

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("FIGHTLAB_DATA", HERE)  # (tests point this somewhere else)
EVIDENCE_DIR = os.path.join(DATA, "evidence")
CARDS_DIR = os.path.join(DATA, "ai_requests")
FIGHTERS_DIR = os.path.join(DATA, "mods", "fighters")  # learners' fighters: with the rest of their data


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


class Record:
    """Everything the teaching layer remembers about one learner (kept if they reconnect)."""

    def __init__(self, name):
        self.name = name
        self.done = {}             # mission id -> {"time", "detail"}
        self.text = {}             # mission id -> reflection text
        self.prediction = None     # predicted punches to knock out the sparring partner
        self.measured = None       # what the game measured
        self.hits_at_build = 0
        self.finishers_at_build = 0
        self.combo_changed = False # built a combo list of their own (3+ moves)
        self.built = False         # has built at least one design
        self.code_viewed = False
        self.brain = None          # fight_brain.Autopilot
        self.brain_features = set()
        self.autopilot = False
        self.hits_at_autopilot = None


class Teaching:
    def __init__(self, server):
        self.server = server
        self.records = {}
        self.profiles = {}  # learner name -> their saved profile
        self.cards = []
        self.accounts = fight_profiles.all_names()  # every learner account on this server (for the teacher)
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
            self.accounts = fight_profiles.all_names()
        saved = prof.get("record", {})
        r.done = {**saved.get("done", {}), **r.done}
        r.text = {**saved.get("text", {}), **r.text}
        if r.prediction is None:
            r.prediction = saved.get("prediction")
        if r.brain is None and prof.get("brain"):
            try:
                fn, fname = fight_brain.load_brain(prof["brain"], p.name)
                r.brain = fight_brain.Autopilot(fn, fname)
                r.brain_features = fm.brain_features(prof["brain"])
                r.autopilot = bool(prof.get("autopilot"))
            except fight_brain.BrainError:
                pass

    def save_profile(self, name):
        prof = self.profiles.get(name)
        if prof is None:
            return
        r = self.record(name)
        prof["record"] = {"done": r.done, "text": r.text, "prediction": r.prediction}
        prof["autopilot"] = r.autopilot
        fight_profiles.save(prof)

    @property
    def lesson_number(self):
        return self.server.lesson.get("lesson_number", 1)

    # ---------- lessons ----------
    def apply_lesson(self, n):
        """Switch on the tools, hazards and mode for lesson n."""
        preset = fm.LESSONS[n]
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
        if not by_teacher and fm.MISSIONS[mission][0] != self.lesson_number:
            return False  # missions count in their own lesson, so evidence matches the plan
        r.done[mission] = {"time": now_text(), "detail": detail}
        title = fm.MISSIONS[mission][1]
        self.server.stage.events.append((self.server.stage.time, f"{name} completed: {title}"))
        self.save()
        return True

    def on_design(self, p, new, problems, accepted):
        """Called after a learner presses Build: valid or not."""
        if p.role != "learner":
            return
        r = self.record(p.name)
        if problems:
            if any("points used" in x or "must be" in x or "combo must" in x for x in problems):
                self.complete(p.name, "2b", f"Rejected: {problems[0]}")
            return
        r.built = True
        f = p.fighter
        r.hits_at_build = f.hits if f else 0
        r.finishers_at_build = f.finishers if f else 0
        defaults = {k: v[2] for k, v in sim.SETTINGS.items()}
        changed = [k for k, v in new["settings"].items() if v != defaults[k]]
        if changed:
            self.complete(p.name, "1a", "Changed " + ", ".join(f"{k} to {new['settings'][k]}%" for k in changed))
        if new["name"] != p.name and new["colour"] != p.start_colour and r.code_viewed:
            self.complete(p.name, "1c", f"Name '{new['name']}' (text), colour {new['colour']} (list)")
        if sum(new["points"].values()) == sim.POINTS_TOTAL:
            self.complete(p.name, "2a", "Points " + ", ".join(f"{k} {v}" for k, v in new["points"].items()))
        edge = [f"{k} = {v}" for k, v in new["points"].items() if v in (sim.STAT_MIN, sim.STAT_MAX)]
        if len(new["combo"]) in (sim.COMBO_MIN, sim.COMBO_MAX):
            edge.append(f"a combo of exactly {len(new['combo'])} moves")
        if edge:
            self.complete(p.name, "2c", "Boundary value accepted: " + ", ".join(edge))
        r.combo_changed = len(new["combo"]) >= 3 and new["combo"] != sim.default_design()["combo"]

    def tick(self, now):
        """Every half second: checks that need watching over time."""
        for p in self.server.learners():
            r, f = self.record(p.name), p.fighter
            if f is None or f not in self.server.stage.fighters():
                continue
            enemy = f.ring.enemy_of(f)
            # 1b: predicted punches to knock out the sparring partner, then measured from real punches
            # (3 punches that reach them, hit or blocked; each one's damage comes from the game's own formula)
            if r.prediction is not None and f.connected.get("punch", 0) >= 3 and enemy is not None:
                per = sim.move_damage(f, enemy, "punch")
                if per > 0:
                    r.measured = math.ceil(enemy.stats["health"] / per)
                    self.complete(p.name, "1b", f"Predicted {r.prediction:.0f} punches, measured {r.measured} "
                                                f"(each punch did {per:.1f} damage to {enemy.stats['health']:.0f} health)")
            if r.combo_changed and f.finishers > r.finishers_at_build:
                self.complete(p.name, "2d", f"Landed the whole combo {p.design['combo']}")
            if r.built and f.hits - r.hits_at_build >= 3 and len(r.text.get("2e", "").split()) >= fm.REFLECTIONS["2e"]:
                self.complete(p.name, "2e", f"{f.hits - r.hits_at_build} hits after rebuilding. Why: {r.text['2e']}")
            if r.brain and r.autopilot:
                if r.brain.seconds_running(now) >= 20:
                    self.complete(p.name, "3a", f"Brain ran for {r.brain.seconds_running(now):.0f} s without an error")
                if r.hits_at_autopilot is None:
                    r.hits_at_autopilot = f.hits
                elif f.hits - r.hits_at_autopilot >= 5 and not r.brain.error:
                    self.complete(p.name, "3e", f"Autopilot landed {f.hits - r.hits_at_autopilot} hits")
            else:
                r.hits_at_autopilot = None
            ring = f.ring
            if enemy is not None and enemy.boss and ring.phase in ("ko", "over") and ring.round_winner is f:
                self.complete(p.name, "4d", f"Beat {enemy.name} in round {ring.round}")
            if (self.lesson_number == 5 and not self.server.stage.practice and r.built and r.brain
                    and not r.brain.error):
                self.complete(p.name, "5a", "Entered the final battle with their own design and brain")

    # ---------- messages from learners and the teacher ----------
    def on_message(self, p, m):
        """Returns a list of (websocket, message) replies, or None if the message isn't for us."""
        kind, r = m.get("type"), self.record(p.name)
        if kind == "prediction":
            try:
                r.prediction = max(1.0, min(500.0, float(m["value"])))
            except (TypeError, ValueError, KeyError):
                return [(p.ws, {"type": "notice", "text": "Type a number for your prediction."})]
            if p.fighter is not None:
                p.fighter.connected["punch"] = 0  # measure from now on
            self.save_profile(p.name)
            return [(p.ws, self.missions_msg(p))]
        if kind == "reflection":
            mission = m.get("mission")
            text = re.sub(r"\s+", " ", str(m.get("text", "")))[:600]
            if mission in fm.REFLECTIONS:
                r.text[mission] = text
                if mission == "5b" and len(text.split()) >= fm.REFLECTIONS["5b"]:
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
                fight_profiles.save(prof)
            return []
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
                try:
                    n = int(m["n"])
                except (TypeError, ValueError, KeyError):
                    return []
                if n in fm.LESSONS:
                    self.apply_lesson(n)
                    self.server.rebuild_stage()
                return "broadcast"
            if kind == "view_learner":  # the teacher's learner view: that learner's missions, as they see them
                q = next((x for x in self.server.learners() if x.name == m.get("name")), None)
                if q is None:
                    return [(p.ws, {"type": "notice", "text": "That learner isn't connected."})]
                return [(p.ws, self.missions_msg(q) | {"for": q.name})]
            if kind == "set_password":
                try:
                    fight_profiles.set_password(m.get("learner", ""), str(m.get("password", "")))
                    text = f"New password set for {m.get('learner')}"
                except fight_profiles.LoginError as e:
                    text = str(e)
                return [(p.ws, {"type": "notice", "text": text})]
            if kind == "add_learner":
                try:
                    prof = fight_profiles.create(m.get("learner", ""), str(m.get("password", "")))
                    self.accounts = fight_profiles.all_names()
                    text = f"Account made for {prof['name']}"
                except fight_profiles.LoginError as e:
                    text = str(e)
                return [(p.ws, {"type": "notice", "text": text})] + self.teacher_update()
            if kind == "tick":
                if m.get("mission") in fm.MISSIONS and m.get("learner"):
                    self.complete(m["learner"], m["mission"], "Checked by the teacher", by_teacher=True)
                return self.teacher_update() + self.learner_updates()
            if kind == "card_status":
                try:
                    return self.set_card_status(int(m["id"]), m.get("status"), str(m.get("note", "")))
                except (TypeError, ValueError, KeyError):
                    return []
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
            fn, fname = loaded or fight_brain.load_brain(source, p.name)
        except fight_brain.BrainError as e:
            return {"type": "brain_result", "ok": False, "error": str(e)}
        if r.brain is not None:  # the old brain's process stops
            r.brain.close()
        r.brain = fight_brain.Autopilot(fn, fname)
        r.brain_features = fm.brain_features(source)
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
        """Give a learner's fighter their brain when autopilot is on (also after a rebuild)."""
        r = self.record(p.name) if p.role == "learner" else None
        if p.fighter is None:
            return
        p.fighter.brain = r.brain if (r and r.brain and r.autopilot) else None

    # ---------- AI request cards ----------
    def submit_card(self, p, card):
        if not isinstance(card, dict):
            card = {}
        target = card.get("target") if card.get("target") in fm.AI_TARGETS and card.get("target") != "game" else "fighter"
        card = {k: str(card.get(k, ""))[:400] for k in ("goal", "variables", "test", "predict")} | \
               {k: bool(card.get(k)) for k in ("privacy", "review", "credit")} | {"target": target}
        problems, tips = fm.check_ai_card(card)
        if problems:
            return {"type": "ai_card_result", "ok": False, "problems": problems, "tips": tips}
        cid = max([c["id"] for c in self.cards], default=0) + 1
        entry = {"id": cid, "learner": p.name, "time": now_text(), "card": card, "status": "waiting", "note": "",
                 "review": None}
        self.cards.append(entry)
        with open(os.path.join(CARDS_DIR, f"{cid:03d}_{slug(p.name)}.md"), "w", encoding="utf-8") as f:
            f.write(fm.ai_prompt(card, p.name))
        mission = fm.AI_CARD_MISSION.get(self.lesson_number)
        if mission:
            self.complete(p.name, mission, f"AI request #{cid} ({fm.AI_TARGETS[target]}): {card['goal']}")
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
        answers = m.get("answers", {}) if isinstance(m.get("answers"), dict) else {}
        answers = {k: re.sub(r"\s+", " ", str(answers.get(k, "")))[:300] for k in fm.REVIEW_QUESTIONS}
        short = [q for q, a in answers.items() if len(a.split()) < 3]
        if short:
            return {"type": "notice", "text": "Answer every review question in a few words."}
        card["review"], card["status"] = answers, "reviewed"
        mission = fm.AI_REVIEW_MISSION.get(self.lesson_number)
        if mission:
            self.complete(p.name, mission, f"Reviewed AI change #{card['id']}: " + " | ".join(answers.values()))
        return self.missions_msg(p)

    # ---------- what each screen is sent ----------
    def missions_msg(self, p):
        r = self.record(p.name)
        f = p.fighter
        missions = [{"id": k, "title": v[1], "text": v[2], "outcomes": v[3], "check": v[4],
                     "done": k in r.done, "detail": r.done.get(k, {}).get("detail", "")}
                    for k, v in fm.missions_for(self.lesson_number).items()]
        return {"type": "missions", "lesson": self.lesson_number, "title": fm.LESSONS[self.lesson_number]["title"],
                "missions": missions, "prediction": r.prediction, "measured": r.measured,
                "punches": f.connected.get("punch", 0) if f else 0,
                "text": r.text, "brain": bool(r.brain), "autopilot": r.autopilot,
                "brain_error": r.brain.error if r.brain else None,
                "cards": [c for c in self.cards if c["learner"] == p.name],
                "review_questions": fm.REVIEW_QUESTIONS}

    def teacher_update(self):
        t = self.server.teacher()
        if not t:
            return []
        names = [p.name for p in self.server.learners()] or list(self.records)
        grid = {}
        for n in names:
            done = self.record(n).done
            grid[n] = {"missions": sorted(done),
                       "outcomes": {o: sum(1 for mid in done if o in fm.MISSIONS[mid][3]) for o in fm.OUTCOMES}}
        return [(t.ws, {"type": "teaching", "lesson": self.lesson_number, "grid": grid, "cards": self.cards,
                        "accounts": self.accounts,
                        "outcomes": {k: v[:2] for k, v in fm.OUTCOMES.items()},
                        "missions": {k: v[:2] + (v[4],) for k, v in fm.MISSIONS.items()}})]

    def learner_updates(self):
        return [(p.ws, self.missions_msg(p)) for p in self.server.learners()]

    # ---------- mods: fighters, stage and rules changed by approved AI requests ----------
    def apply_mods(self, files):
        """Check and save changed mod files, then use them straight away."""
        written = []
        if not isinstance(files, dict):
            return "Nothing to apply"
        for rel, text in files.items():
            rel = str(rel).replace("\\", "/")
            name_part = rel[len("mods/fighters/"):]
            ok = rel in ("mods/stage.py", "mods/rules.py") or (
                rel.startswith("mods/fighters/") and rel.endswith(".py") and "/" not in name_part and ".." not in rel)
            if not ok:
                return f"Not applied: {rel} isn't a mod file"
            path = os.path.join(FIGHTERS_DIR, name_part) if rel.startswith("mods/fighters/") else os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".check"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(str(text))
            try:
                if rel == "mods/rules.py":
                    fight_mods.read_dict(tmp, "RULES")
                elif rel == "mods/stage.py":
                    fight_mods.read_dict(tmp, "STAGE")
                else:
                    fight_mods.load_fighter(tmp)
            except fight_mods.ModError as e:
                os.remove(tmp)
                return f"Not applied: {e}"
            os.replace(tmp, path)
            written.append(rel)
        self.server.reload_mods(written)
        return "Applied: " + ", ".join(written) if written else "Nothing to apply"

    # ---------- deleting a learner (end of course, or a parent asks) ----------
    def delete_learner(self, name):
        """Remove everything the server keeps about a learner: profile, fighter, brain, evidence and AI cards.
        The server disconnects them first. Returns a message for the teacher."""
        name = fight_profiles.clean_name(name)
        prof = fight_profiles.load(name) if name else None
        if prof is None:
            return "No account with that username."
        name = prof["name"]
        r = self.records.pop(name, None)
        if r is not None and r.brain is not None:
            r.brain.close()
        self.profiles.pop(name, None)
        fight_profiles.delete(name)
        if os.path.exists(self.fighter_file(name)):
            os.remove(self.fighter_file(name))
        self.cards = [c for c in self.cards if c["learner"] != name]
        for f in os.listdir(CARDS_DIR):
            if f.endswith((f"_{name}.md", f"_{slug(name)}.md")):
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
        self.accounts = fight_profiles.all_names()
        return f"Deleted {name}: profile, fighter, brain, evidence and AI cards (backups keep them until they expire)"

    def fighter_file(self, name):
        return os.path.join(FIGHTERS_DIR, f"{slug(name)}.py")

    def load_saved_design(self, name):
        """A learner's fighter from last time, if they have one."""
        path = self.fighter_file(name)
        if os.path.exists(path):
            try:
                return fight_mods.load_fighter(path)
            except fight_mods.ModError:
                return None
        return None

    def save_design(self, name, design):
        """Autosave a learner's fighter to their own mod file (keeping its style)."""
        old = self.load_saved_design(name) or {}
        d = dict(design)
        if "style" in old and "style" not in d:
            d["style"] = old["style"]
        os.makedirs(FIGHTERS_DIR, exist_ok=True)
        with open(self.fighter_file(name), "w", encoding="utf-8") as f:
            f.write(fighter_file_text(d, name))

    # ---------- saving ----------
    def save(self):
        data = {"learners": {n: {"done": r.done, "text": r.text} for n, r in self.records.items()},
                "cards": self.cards}
        with open(self.evidence_file, "w") as f:
            json.dump(data, f, indent=2)
        for name in self.profiles:
            self.save_profile(name)

    def export(self):
        path = os.path.join(EVIDENCE_DIR, f"evidence_{datetime.date.today()}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Learner", "Lesson", "Mission", "Title", "Outcomes", "Curriculum", "When", "Evidence"])
            for n, r in sorted(self.records.items()):
                for mid, info in sorted(r.done.items()):
                    lesson, title, _, outcomes, _ = fm.MISSIONS[mid]
                    w.writerow([n, lesson, mid, title, " ".join(outcomes),
                                " || ".join(fm.OUTCOMES[o][2] for o in outcomes), info["time"], info["detail"]])
        return path
