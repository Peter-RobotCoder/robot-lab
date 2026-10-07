"""The teaching framework (the engine's, layer C): lessons, missions, evidence, learners' brains and AI request
cards, for every game.

A game's server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes
in the game's missions module, so the teacher can see (and export) who has shown what. A game gives Teaching a
Game (the modules and names that are its own: see the Game class) and subclasses it for what is its content: which
builds, fights and brains complete which objectives (the hooks at the end).
"""
import csv
import datetime
import json
import os
import time
import re



class Game:
    """What a game tells the framework: its modules and where its files are.
    missions: the missions module (LESSONS, MISSIONS, OUTCOMES, brain_features, AI_CARD_MISSION, AI_REVIEW_MISSION,
    AI_TARGETS, REVIEW_QUESTIONS, check_ai_card, ai_prompt, points_words). profiles: the profiles module (all_names,
    save, load, delete, create, set_password, clean_name, LoginError). brain: the brain module (load_brain,
    Autopilot, BrainError). data: the game's data folder. designs: the folder learners' designs are saved in, as
    mod files. design_text(design, name) and load_design(path) write and read one (load raises mod_error).
    apply_mods(teaching, files) -> message: an approved AI request's changed mod files. unit(player): the player's
    robot or fighter; world(server): the arena or stage (events, time, practice); units(world): the units in it;
    rebuild(server): make the world again. slug(name): a learner's name as a file name."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def now_text():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def design_changes(old, new, schema):
    """What a build changed, by variable name as the code editor shows them: ['turn_speed 80 -> 100', ...]."""
    out = []
    for var in schema:
        a, b = var.get(old), var.get(new)
        if a != b:
            out.append(f"{var.name} {a!r} -> {b!r}")
    return out


class Record:
    """Everything the teaching layer remembers about one learner (kept if they reconnect). A game's Record adds
    what its own checks watch."""

    def __init__(self, name):
        self.name = name
        self.done = {}             # mission id -> {"time", "detail"}
        self.text = {}             # mission id -> reflection text
        self.prediction = None     # a predict-then-test mission's prediction
        self.hits_at_build = 0
        self.built = False         # has built at least one design
        self.code_viewed = False
        self.brain = None          # the game's Autopilot
        self.brain_features = set()
        self.autopilot = False


class Teaching:
    record_class = Record
    reflections = {}  # mission id -> the words a reflection needs to count (the game's)

    def __init__(self, server, game):
        self.server, self.g = server, game
        self.evidence_dir = os.path.join(game.data, "evidence")
        self.cards_dir = os.path.join(game.data, "ai_requests")
        self.records = {}
        self.profiles = {}  # learner name -> their saved profile
        self.cards = []
        self.accounts = game.profiles.all_names()  # every learner account on this server (for the teacher)
        os.makedirs(self.evidence_dir, exist_ok=True)
        os.makedirs(self.cards_dir, exist_ok=True)
        self.evidence_file = os.path.join(self.evidence_dir, f"evidence_{datetime.date.today()}.json")
        if os.path.exists(self.evidence_file):  # carry on from earlier today
            with open(self.evidence_file) as f:
                saved = json.load(f)
            for name, data in saved.get("learners", {}).items():
                r = self.record(name)
                r.done, r.text = data.get("done", {}), data.get("text", {})
            self.cards = saved.get("cards", [])

    def record(self, name):
        return self.records.setdefault(name, self.record_class(name))

    # ---------- profiles: a learner's work, kept between lessons ----------
    def login(self, p):
        """A learner has logged in: bring back their missions, reflections, prediction, brain and autopilot."""
        prof, r = p.profile, self.record(p.name)
        self.profiles[p.name] = prof
        if p.name not in self.accounts:  # a new profile (laptop-only test servers)
            self.accounts = self.g.profiles.all_names()
        saved = prof.get("record", {})
        r.done = {**saved.get("done", {}), **r.done}
        r.text = {**saved.get("text", {}), **r.text}
        if r.prediction is None:
            r.prediction = saved.get("prediction")
        self.restore_record(r, saved)
        if r.brain is None and prof.get("brain"):
            try:
                fn, fname = self.g.brain.load_brain(prof["brain"], p.name)
                r.brain = self.g.brain.Autopilot(fn, fname)
                r.brain_features = self.g.missions.brain_features(prof["brain"])
                r.autopilot = bool(prof.get("autopilot"))
            except self.g.brain.BrainError:
                pass

    def save_profile(self, name):
        prof = self.profiles.get(name)
        if prof is None:
            return
        r = self.record(name)
        prof["record"] = {"done": r.done, "text": r.text, "prediction": r.prediction, **self.record_extra(r)}
        prof["autopilot"] = r.autopilot
        self.g.profiles.save(prof)

    @property
    def lesson_number(self):
        return self.server.lesson.get("lesson_number", 1)

    # ---------- lessons ----------
    def apply_lesson(self, n):
        """Switch on the tools, hazards and mode for lesson n."""
        preset = self.g.missions.LESSONS[n]
        L = self.server.lesson
        L["lesson_number"] = n
        L["mode"] = preset["mode"]
        L["hazards"] = dict(preset["hazards"])
        L["tools"] = json.loads(json.dumps(preset["tools"]))
        self.server.use_mission_settings()  # (then what the teacher saved for this mission, if anything)

    # ---------- missions ----------
    def complete(self, name, mission, detail, by_teacher=False):
        r = self.record(name)
        if mission in r.done:
            return False
        if not by_teacher and self.g.missions.MISSIONS[mission][0] != self.lesson_number:
            return False  # missions count in their own lesson, so evidence matches the plan
        r.done[mission] = {"time": now_text(), "detail": detail}
        title = self.g.missions.MISSIONS[mission][1]
        world = self.g.world(self.server)
        world.events.append((world.time, f"{name} completed: {title}"))
        self.save()
        return True

    def on_design(self, p, new, problems, accepted, old=None, by_code=False):
        """Called after a learner presses Build: valid or not. old: their design before this build; by_code: the
        build came from the code editor (Mission 1's objective d), not the Garage's buttons (a, b and c)."""
        if p.role != "learner":
            return
        r = self.record(p.name)
        if problems:
            self.build_rejected(p, r, problems, new=new, by_code=by_code)
            return
        r.built = True
        unit = self.g.unit(p)
        r.hits_at_build = unit.hits if unit else 0
        old = old or {}
        if by_code:
            changed = design_changes(old, new, self.g.sim.schema())
            if changed:
                self.complete(p.name, "1d", "Changed in the code: " + ", ".join(changed))
        self.build_checks(p, r, new, old, by_code)

    def tick(self, now):
        """Every half second: checks that need watching over time."""
        world = self.g.world(self.server)
        for p in self.server.learners():
            r, unit = self.record(p.name), self.g.unit(p)
            if unit is None or unit not in self.g.units(world):
                continue
            self.tick_checks(p, r, unit, world, now)


    # ---------- messages from learners and the teacher ----------
    def on_message(self, p, m):
        """Returns a list of (websocket, message) replies, or None if the message isn't for us."""
        kind, r = m.get("type"), self.record(p.name)
        if kind == "prediction":
            try:
                r.prediction = max(0.0, min(500.0, float(m["value"])))
            except (TypeError, ValueError, KeyError):
                return [(p.ws, {"type": "notice", "text": "Type a number for your prediction."})]
            self.predicted(p, r)
            self.save_profile(p.name)
            return [(p.ws, self.missions_msg(p))]
        if kind == "reflection":
            mission = m.get("mission")
            text = re.sub(r"\s+", " ", str(m.get("text", "")))[:600]
            if mission in self.reflections:
                r.text[mission] = text
                self.reflected(p, r, mission, text)
                self.save()
            return [(p.ws, self.missions_msg(p))]
        if kind == "code_viewed":
            r.code_viewed = True
            return []
        if kind == "slot":  # CHANGE 83: save into, or empty, one of five slots (a learner's, or the teacher's own)
            if m.get("do") == "list":
                return [(p.ws, self.slots_msg(p.name, self.slots_of(p)))]
            try:
                n = int(m.get("n"))
            except (TypeError, ValueError):
                return []
            if not 1 <= n <= self.MAX_SLOTS:
                return []
            slots = self.slots_of(p)
            if m.get("do") == "save" and isinstance(m.get("design"), dict) and len(json.dumps(m["design"])) < 8000:
                slots[str(n)] = m["design"]
                self.history_add(p.name, n, m["design"])
            elif m.get("do") == "delete":
                slots.pop(str(n), None)
            else:
                return []
            self.keep_slots(p)
            out = [(p.ws, self.slots_msg(p.name, slots))]
            t = self.server.teacher()
            if t and t is not p:  # (the Learner view shows them)
                out.append((t.ws, self.slots_msg(p.name, slots)))
            return out
        if kind == "prefs":  # camera view, half-typed AI card and so on: kept in the learner's profile
            prof = self.profiles.get(p.name)
            if prof is not None and isinstance(m.get("prefs"), dict) and len(json.dumps(m["prefs"])) < 20000:
                prof["prefs"] = m["prefs"]
                self.g.profiles.save(prof)
            return []
        if kind in ("brain", "autopilot") and p.role == "learner" and \
                not self.server.lesson.get("tools", {}).get("brains", True):  # (CHANGE 99: switched off in Controls)
            return [(p.ws, {"type": "notice", "text": "Brains aren't switched on for this mission yet."})]
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
                try:
                    n = int(m["n"])
                except (TypeError, ValueError, KeyError):
                    return []
                if n in self.g.missions.LESSONS:
                    self.apply_lesson(n)
                    self.g.rebuild(self.server)
                return "broadcast"
            if kind == "view_learner":  # the teacher's learner view: that learner's missions, as they see them
                q = next((x for x in self.server.learners() if x.name == m.get("name")), None)
                cpu = getattr(self.server, "cpu", None)  # (the computer's robot or fighter: the Mission tab as a
                if q is None and cpu is not None and m.get("name") == cpu.name:  # learner sees it, CHANGE 23)
                    q = cpu
                if q is None:
                    return [(p.ws, {"type": "notice", "text": "That learner isn't connected."})]
                return [(p.ws, self.missions_msg(q) | {"for": q.name})]
            if kind == "missions_edit":  # CHANGE 97: the teacher's wording of the missions
                self.edit_missions(m)
                return "broadcast"
            if kind == "slots_of":  # CHANGE 86: the teacher reads a learner's saved designs (or their own)
                who = m.get("name")
                if who == p.name or not who:
                    return [(p.ws, self.slots_msg(p.name, self.slots_of(p)))]
                prof = self.profiles.get(who) or (self.g.profiles.load(who) if isinstance(who, str) else None)
                if prof is None:
                    return [(p.ws, {"type": "notice", "text": "No account with that username."})]
                return [(p.ws, self.slots_msg(prof["name"], prof.get("slots", {})))]
            if kind == "history":  # CHANGE 84: every design ever saved, newest first
                return [(p.ws, self.history_msg())]
            if kind == "set_password":
                try:
                    self.g.profiles.set_password(m.get("learner", ""), str(m.get("password", "")))
                    text = f"New password set for {m.get('learner')}"
                except self.g.profiles.LoginError as e:
                    text = str(e)
                return [(p.ws, {"type": "notice", "text": text})]
            if kind == "add_learner":
                try:
                    prof = self.g.profiles.create(m.get("learner", ""), str(m.get("password", "")))
                    self.accounts = self.g.profiles.all_names()
                    text = f"Account made for {prof['name']}"
                except self.g.profiles.LoginError as e:
                    text = str(e)
                return [(p.ws, {"type": "notice", "text": text})] + self.teacher_update()
            if kind == "tick":
                if m.get("mission") in self.g.missions.MISSIONS and m.get("learner"):
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
            fn, fname = loaded or self.g.brain.load_brain(source, p.name)
        except self.g.brain.BrainError as e:
            return {"type": "brain_result", "ok": False, "error": str(e)}
        if r.brain is not None:  # the old brain's process stops
            r.brain.close()
        r.brain = self.g.brain.Autopilot(fn, fname)
        r.brain_features = self.g.missions.brain_features(source)
        if p.name in self.profiles:  # kept, so it's still there next lesson
            self.profiles[p.name]["brain"] = source
            self.save_profile(p.name)
        self.brain_checks(p, r)
        self.attach(p)
        return {"type": "brain_result", "ok": True,
                "error": "Uploaded. Press P to switch autopilot " + ("off." if r.autopilot else "on.")}

    def attach(self, p):
        """Give a learner's robot or fighter their brain when autopilot is on (also after a rebuild)."""
        r = self.record(p.name) if p.role == "learner" else None
        unit = self.g.unit(p)
        if unit is None:
            return
        unit.brain = r.brain if (r and r.brain and r.autopilot) else None

    # ---------- AI request cards ----------
    def submit_card(self, p, card):
        target = card.get("target") if card.get("target") in self.g.missions.AI_TARGETS else "robot"
        card = {k: str(card.get(k, ""))[:2000] for k in ("goal", "variables", "test", "predict")} | \
               {k: bool(card.get(k)) for k in ("privacy", "review", "credit")} | {"target": target}
        problems, tips = self.g.missions.check_ai_card(card)
        if problems:
            return {"type": "ai_card_result", "ok": False, "problems": problems, "tips": tips}
        cid = max([c["id"] for c in self.cards], default=0) + 1
        entry = {"id": cid, "learner": p.name, "time": now_text(), "card": card, "status": "waiting", "note": "",
                 "review": None}
        self.cards.append(entry)
        with open(os.path.join(self.cards_dir, f"{cid:03d}_{p.name}.md"), "w", encoding="utf-8") as f:
            f.write(self.g.missions.ai_prompt(card, p.name))
        mission = self.g.missions.AI_CARD_MISSION.get(self.lesson_number)
        if mission:
            self.complete(p.name, mission, f"AI request #{cid} ({self.g.missions.AI_TARGETS[target]}): {card['goal']}")
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
        answers = {k: re.sub(r"\s+", " ", str(m.get("answers", {}).get(k, "")))[:300] for k in self.g.missions.REVIEW_QUESTIONS}
        short = [q for q, a in answers.items() if len(a.split()) < 3]
        if short:
            return {"type": "notice", "text": "Answer every review question in a few words."}
        card["review"], card["status"] = answers, "reviewed"
        mission = self.g.missions.AI_REVIEW_MISSION.get(self.lesson_number)
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
        limits = self.server.lesson.get("limits")  # (the missions' words with the teacher's own numbers, where a
        points_words = getattr(self.g.missions, "points_words", None)  # game has limits and the words for them)
        words = (lambda text: points_words(text, limits)) if points_words and limits else (lambda text: text)
        missions = [{"id": k, "title": words(v[1]), "text": words(v[2]), "outcomes": v[3], "check": v[4],
                     "done": k in r.done, "detail": r.done.get(k, {}).get("detail", "")}
                    for k, v in self.objectives(self.lesson_number).items()]
        return {"type": "missions", "lesson": self.lesson_number,
                "title": words(self.g.missions.LESSONS[self.lesson_number]["title"]),
                "missions": missions, "prediction": r.prediction, **self.missions_extra(r),
                "text": r.text, "brain": bool(r.brain), "autopilot": r.autopilot,
                "brain_error": r.brain.error if r.brain else None,
                "cards": [c for c in self.cards if c["learner"] == p.name],
                "review_questions": self.g.missions.REVIEW_QUESTIONS, "card": self.card_data(p.name)}

    def card_data(self, name):
        """A learner's own card: the outcomes they've shown so far in this game, and what they did each day."""
        done = self.record(name).done
        outcomes = {o: sum(1 for mid in done if o in self.g.missions.MISSIONS[mid][3]) for o in self.g.missions.OUTCOMES}
        days = {}
        for mid, info in done.items():
            if mid not in self.g.missions.MISSIONS:
                continue
            day = str(info.get("time", ""))[:10] or "earlier"
            days.setdefault(day, []).append({"id": mid, "title": self.g.missions.MISSIONS[mid][1], "outcomes": self.g.missions.MISSIONS[mid][3],
                                             "lesson": self.g.missions.MISSIONS[mid][0], "time": info.get("time", ""),
                                             "detail": str(info.get("detail", ""))[:160]})  # (what exactly: CHANGE 96)
        history = [{"date": day, "missions": sorted(ms, key=lambda m: m["time"])} for day, ms in sorted(days.items(),
                                                                                                        reverse=True)]
        return {"outcomes": outcomes, "outcome_names": {o: v[0] for o, v in self.g.missions.OUTCOMES.items()}, "history": history}

    def session_report(self, since, present):
        """What happened in the live session, for the club desk: who was here, what each learner completed
        (missions and their outcomes) since it started, and the AI cards handled."""
        done = {}
        for name, r in self.records.items():
            new = {mid: {"time": info.get("time", ""), "detail": info.get("detail", ""), "title": self.g.missions.MISSIONS[mid][1],
                         "outcomes": self.g.missions.MISSIONS[mid][3], "check": self.g.missions.MISSIONS[mid][4]}
                   for mid, info in r.done.items() if mid in self.g.missions.MISSIONS and str(info.get("time", "")) >= since}
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
                       "outcomes": {o: sum(1 for mid in done if o in self.g.missions.MISSIONS[mid][3]) for o in self.g.missions.OUTCOMES}}
        return [(t.ws, {"type": "teaching", "lesson": self.lesson_number, "grid": grid, "cards": self.cards,
                        "accounts": self.accounts,
                        "outcomes": {k: v[:2] for k, v in self.g.missions.OUTCOMES.items()},
                        "missions": {k: v[:2] + (v[4],) for k, v in self.g.missions.MISSIONS.items()},
                        # (CHANGE 97) every lesson's objectives as learners see them, with the teacher's edits
                        "edited": {str(n): {k: list(v) for k, v in self.objectives(n).items()}
                                   for n in self.g.missions.LESSONS},
                        "edits": self.mission_edits()})]

    def learner_updates(self):
        return [(p.ws, self.missions_msg(p)) for p in self.server.learners()]

    # ---------- mods: designs, the world and rules changed by approved AI requests ----------
    def apply_mods(self, files):
        """Check and save changed mod files, then use them straight away (the game's own rules)."""
        return self.g.apply_mods(self, files)

    # ---------- deleting a learner (end of course, or a parent asks) ----------
    def delete_learner(self, name):
        """Remove everything the server keeps about a learner: profile, robot, brain, evidence and AI cards.
        The server disconnects them first. Returns a message for the teacher."""
        name = self.g.profiles.clean_name(name)
        prof = self.g.profiles.load(name) if name else None
        if prof is None:
            return "No account with that username."
        name = prof["name"]
        r = self.records.pop(name, None)
        if r is not None and r.brain is not None:
            r.brain.close()
        self.profiles.pop(name, None)
        self.g.profiles.delete(name)
        if os.path.exists(self.design_file(name)):
            os.remove(self.design_file(name))
        self.cards = [c for c in self.cards if c["learner"] != name]
        self.forget_history(name)
        for f in os.listdir(self.cards_dir):
            if f.endswith(f"_{name}.md"):
                os.remove(os.path.join(self.cards_dir, f))
        for f in os.listdir(self.evidence_dir):  # earlier days' evidence too
            path = os.path.join(self.evidence_dir, f)
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
        self.accounts = self.g.profiles.all_names()
        return f"Deleted {name}: profile, design, brain, evidence and AI cards (backups keep them until they expire)"

    def design_file(self, name):
        return os.path.join(self.g.designs, f"{self.g.slug(name)}.py")

    def load_saved_design(self, name):
        """A learner's design from last time, if they have one."""
        path = self.design_file(name)
        if os.path.exists(path):
            try:
                return self.g.load_design(path)
            except self.g.mod_error:
                return None
        return None

    # ---------- the missions' words, as the teacher edited them (CHANGE 97) ----------
    def edits_file(self):
        return os.path.join(self.g.data, "missions_edits.json")

    def mission_edits(self):
        """{"changed": {id: {"title", "text"}}, "removed": [id], "added": {id: [lesson, title, text]}}."""
        if not hasattr(self, "_edits"):
            try:
                with open(self.edits_file(), encoding="utf-8") as f:
                    e = json.load(f)
                self._edits = e if isinstance(e, dict) else {}
            except (OSError, ValueError):
                self._edits = {}
            self._edits.setdefault("changed", {})
            self._edits.setdefault("removed", [])
            self._edits.setdefault("added", {})
        return self._edits

    def keep_edits(self):
        try:
            with open(self.edits_file(), "w", encoding="utf-8") as f:
                json.dump(self.mission_edits(), f, indent=1)
        except OSError:
            pass

    def objectives(self, lesson):
        """The lesson's objectives as the learners see them: the built-in ones with the teacher's wording, less the
        ones taken out, plus the ones added (id -> (lesson, title, text, outcomes, check))."""
        e = self.mission_edits()
        out = {}
        for k, v in self.g.missions.missions_for(lesson).items():
            if k in e["removed"]:
                continue
            c = e["changed"].get(k, {})
            out[k] = (v[0], c.get("title") or v[1], c.get("text") or v[2], v[3], v[4])
        for k, (n, title, text) in e["added"].items():
            if n == lesson:
                out[k] = (lesson, title, text, [], "teacher")
        return out

    def edit_missions(self, m):
        """The teacher's edits: change an objective's words, add one, take one out, or reset to the built-in text."""
        e = self.mission_edits()
        do = m.get("do")
        if do == "change" and isinstance(m.get("id"), str):
            words = {k: " ".join(str(m.get(k, "")).split())[:600] for k in ("title", "text")}
            if m["id"] in e["added"]:
                n = e["added"][m["id"]][0]
                e["added"][m["id"]] = [n, words["title"] or "Objective", words["text"]]
            elif m["id"] in self.g.missions.MISSIONS:
                e["changed"][m["id"]] = words
        elif do == "add":
            try:
                n = int(m.get("lesson"))
            except (TypeError, ValueError):
                return
            k = f"{n}t{1 + sum(1 for i in e['added'] if e['added'][i][0] == n) + len(e['removed'])}"
            while k in e["added"] or k in self.g.missions.MISSIONS:
                k += "x"
            e["added"][k] = [n, " ".join(str(m.get("title", "")).split())[:120] or "New objective",
                             " ".join(str(m.get("text", "")).split())[:600]]
        elif do == "remove" and isinstance(m.get("id"), str):
            if m["id"] in e["added"]:
                e["added"].pop(m["id"])
            elif m["id"] in self.g.missions.MISSIONS and m["id"] not in e["removed"]:
                e["removed"].append(m["id"])
        elif do == "reset":
            self._edits = {"changed": {}, "removed": [], "added": {}}
        else:
            return
        self.keep_edits()

    # ---------- saved designs (CHANGE 83 to 87): five slots each, and a history of every save ----------
    MAX_SLOTS = 5

    def slots_of(self, p):
        """The player's slots: a learner's live in their profile, the teacher's in a file with the class's data."""
        if p.role == "teacher":
            if not hasattr(self, "teacher_slots"):
                try:
                    with open(os.path.join(self.g.data, "teacher_slots.json"), encoding="utf-8") as f:
                        self.teacher_slots = json.load(f)
                except (OSError, ValueError):
                    self.teacher_slots = {}
            return self.teacher_slots
        prof = self.profiles.get(p.name)
        if prof is None:
            return {}
        return prof.setdefault("slots", {})

    def keep_slots(self, p):
        if p.role == "teacher":
            try:
                with open(os.path.join(self.g.data, "teacher_slots.json"), "w", encoding="utf-8") as f:
                    json.dump(self.teacher_slots, f)
            except OSError:
                pass
        else:
            self.save_profile(p.name)

    def slots_msg(self, who, slots):
        return {"type": "slots", "who": who,
                "slots": {n: {"name": str(d.get("name", "?"))[:20], "design": d} for n, d in slots.items()
                          if isinstance(d, dict)}}

    def history_file(self):
        return os.path.join(self.g.data, "design_history.json")

    def history_add(self, who, n, design):
        """Every save goes in the history too (deleting or overwriting a slot never touches it)."""
        items = self.history_items()
        items.append({"who": who, "when": time.strftime("%Y-%m-%d %H:%M"), "slot": n,
                      "name": str(design.get("name", "?"))[:20], "design": design})
        try:
            with open(self.history_file(), "w", encoding="utf-8") as f:
                json.dump(items[-2000:], f)
        except OSError:
            pass

    def history_items(self):
        try:
            with open(self.history_file(), encoding="utf-8") as f:
                items = json.load(f)
            return items if isinstance(items, list) else []
        except (OSError, ValueError):
            return []

    def history_msg(self):
        items = self.history_items()
        return {"type": "history", "items": list(reversed(items))[:300]}

    def forget_history(self, name):
        """A deleted learner's saves come out of the history (as their name comes off their mods)."""
        items = [it for it in self.history_items() if it.get("who") != name]
        try:
            with open(self.history_file(), "w", encoding="utf-8") as f:
                json.dump(items, f)
        except OSError:
            pass

    def save_design(self, name, design):
        """Autosave a learner's design to their own mod file (keeping its style)."""
        old = self.load_saved_design(name) or {}
        d = dict(design)
        if "style" in old and "style" not in d:
            d["style"] = old["style"]
        os.makedirs(self.g.designs, exist_ok=True)
        with open(self.design_file(name), "w", encoding="utf-8") as f:
            f.write(self.g.design_text(d, name))

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
        path = os.path.join(self.evidence_dir, f"evidence_{datetime.date.today()}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Learner", "Mission", "Objective", "Title", "Outcomes", "Curriculum", "When", "Evidence"])
            for n, r in sorted(self.records.items()):
                for mid, info in sorted(r.done.items()):
                    lesson, title, _, outcomes, _ = self.g.missions.MISSIONS[mid]
                    w.writerow([n, lesson, mid, title, " ".join(outcomes),
                                " || ".join(self.g.missions.OUTCOMES[o][2] for o in outcomes), info["time"], info["detail"]])
        return path

    # ---------- the game's own: what completes which objective ----------
    def build_rejected(self, p, r, problems, new=None, by_code=False):
        """A build the server refused (a mission may be about trying invalid data). new: the design as sent;
        by_code: it came from the code editor."""

    def build_checks(self, p, r, new, old, by_code):
        """A build was accepted: which objectives it completes."""

    def tick_checks(self, p, r, unit, world, now):
        """Every half second, for a learner whose robot or fighter is in the world."""

    def predicted(self, p, r):
        """A prediction was typed (a predict-then-test mission): start measuring."""

    def reflected(self, p, r, mission, text):
        """A reflection was saved: complete it if it is enough."""

    def brain_checks(self, p, r):
        """A brain was uploaded: which objectives its features complete."""

    def missions_extra(self, r):
        """Extra fields for the learner's missions message (a measurement to show)."""
        return {}

    def record_extra(self, r):
        """Extra fields kept in the learner's profile record."""
        return {}

    def restore_record(self, r, saved):
        """Those fields back from the profile."""
