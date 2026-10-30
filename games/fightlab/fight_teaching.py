"""Fight Lab's teaching: what is Fight Lab's own on top of the engine's framework (engine/teaching.py): which
builds, fights and brains complete which objectives, and the fighter files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
fight_missions.py, so the teacher can see (and export) who has shown what.
"""
import math
import os

import fight_version  # noqa: F401  (puts the engine on the path)
import fight_brain
import fight_missions as fm
import fight_mods
import fight_profiles
import fight_sim as sim
from ai_pipeline import fighter_file_text, slug
from engine import teaching

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("FIGHTLAB_DATA", HERE)  # (tests point this somewhere else)
EVIDENCE_DIR = os.path.join(DATA, "evidence")
CARDS_DIR = os.path.join(DATA, "ai_requests")
FIGHTERS_DIR = os.path.join(DATA, "mods", "fighters")  # learners' fighters: with the rest of their data
now_text = teaching.now_text


class Record(teaching.Record):
    def __init__(self, name):
        super().__init__(name)
        self.finishers_at_build = 0
        self.combo_changed = False  # built a combo list of their own (3+ moves)
        self.hits_at_autopilot = None


def apply_mods(t, files):
    """Check and save changed mod files (the stage, the rules, learners' fighters), then use them straight away."""
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
    t.server.reload_mods(written)
    return "Applied: " + ", ".join(written) if written else "Nothing to apply"


GAME = teaching.Game(slug_word="fightlab", missions=fm, profiles=fight_profiles, brain=fight_brain, sim=sim, data=DATA, designs=FIGHTERS_DIR,
                     design_text=fighter_file_text, load_design=fight_mods.load_fighter, mod_error=fight_mods.ModError,
                     apply_mods=apply_mods, slug=slug, unit=lambda p: p.fighter, world=lambda server: server.stage,
                     units=lambda stage: stage.fighters(), rebuild=lambda server: server.rebuild_stage())


class Teaching(teaching.Teaching):
    record_class = Record
    reflections = fm.REFLECTIONS  # mission id -> the words a reflection needs to count

    def __init__(self, server):
        super().__init__(server, GAME)

    def build_rejected(self, p, r, problems, new=None, by_code=False):
        if any("points used" in x or "must be" in x or "combo must" in x for x in problems):
            self.complete(p.name, "2b", f"Rejected: {problems[0]}")

    def build_checks(self, p, r, new, old, by_code):
        """Mission 1's objectives a, b and c (with the GUI), and mission 2's points and combo."""
        self.experience_garage(p, new, old, by_code)  # (Experience 1's garage and code objectives: CHANGE 210)
        f = p.fighter
        r.finishers_at_build = f.finishers if f else 0
        defaults = {k: v[2] for k, v in sim.SETTINGS.items()}
        if not by_code:
            was = old.get("name", p.name)
            if new["name"] != was:
                self.complete(p.name, "1a", f'fighter_name "{was}" became "{new["name"]}" (a string, with the GUI)')
            s = new["settings"]
            if s["walk_speed"] != defaults["walk_speed"] and s["size"] != defaults["size"]:
                self.complete(p.name, "1b", f"walk_speed = {s['walk_speed']:g}, size = {s['size']:g} "
                                            "(integers, with the GUI)")
            if new["colour"] != old.get("colour", p.start_colour):
                self.complete(p.name, "1c", f"colour = {new['colour']} (a list, with the GUI)")
        if sum(new["points"].values()) == sim.POINTS_TOTAL:
            self.complete(p.name, "2a", "Points " + ", ".join(f"{k} {v}" for k, v in new["points"].items()))
        edge = [f"{k} = {v}" for k, v in new["points"].items() if v in (sim.STAT_MIN, sim.STAT_MAX)]
        if len(new["combo"]) in (sim.COMBO_MIN, sim.COMBO_MAX):
            edge.append(f"a combo of exactly {len(new['combo'])} moves")
        if edge:
            self.complete(p.name, "2c", "Boundary value accepted: " + ", ".join(edge))
        r.combo_changed = len(new["combo"]) >= 3 and new["combo"] != sim.default_design()["combo"]

    def tick_checks(self, p, r, f, stage, now):
        enemy = f.ring.enemy_of(f)
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
        if self.lesson_number == 5 and not stage.practice and r.built and r.brain and not r.brain.error:
            self.complete(p.name, "5a", "Entered the final battle with their own design and brain")

    def reflected(self, p, r, mission, text):
        if mission == "5b" and len(text.split()) >= fm.REFLECTIONS["5b"]:
            self.complete(p.name, "5b", text)

    def brain_checks(self, p, r):
        if "if" in r.brain_features:
            self.complete(p.name, "3b", "Brain uses if / elif / else")
        if "own_function" in r.brain_features:
            self.complete(p.name, "3c", "Brain calls its own helper function")
        if "memory" in r.brain_features:
            self.complete(p.name, "3d", "Brain keeps state in me.memory")

    # ---------- Experience 1, Orientation (CHANGE 210): what each objective measures, in the real ring ----------
    # Twice a second (engine/experience.py's experience_tick), from the learner's own fighter as the server has it.
    # The fighting objectives count only what the learner does themselves (not their autopilot), measured from the
    # objective's start, or from a new fighter after a rebuild (a build makes a new Fighter, its counts at nothing).
    FIGHT_OBJECTIVES = ("footwork", "sidestep", "strikes", "combo", "moves", "bout")

    def experience_value(self, p, r, oid, f, stage, now, run):
        b, v = run["base"], run["value"]
        if oid == "brain":
            return r.brain.seconds_running(now) if (r.brain and r.autopilot and not r.brain.error) else None
        if f is None or oid not in self.FIGHT_OBJECTIVES or f not in stage.fighters():
            return None  # (the garage and the code are counted as they are built: build_checks)
        enemy = f.ring.enemy_of(f)
        if b.get("unit") is not f:  # (the objective's start, or a new fighter after a rebuild: measured from here)
            b.update(unit=f, pos=(f.x, f.y), round=self.angle_round(f, enemy), hits=f.hits, finishers=f.finishers,
                     connected=dict(f.connected))
            return None
        mine = not r.autopilot  # (what the learner does, not their brain)
        if oid == "footwork":
            step = math.hypot(f.x - b["pos"][0], f.y - b["pos"][1])
            b["pos"] = (f.x, f.y)
            return v + (step if mine and step < 2.0 else 0.0)  # (a jump back to the start spot isn't walking)
        if oid == "sidestep":  # (how far round the other fighter: the angle from them to you)
            a = self.angle_round(f, enemy)
            step = 0.0 if a is None or b["round"] is None else abs((a - b["round"] + 180) % 360 - 180)
            b["round"] = a
            return v + (step if mine and step < 120 else 0.0)  # (a new round's start spot isn't a sidestep)
        if oid == "strikes":
            got = max(0, f.hits - b["hits"])
            b["hits"] = f.hits
            return v + (got if mine else 0)
        if oid == "combo":  # (whole combos landed: the last move of the combo list, reached by chaining)
            got = max(0, f.finishers - b["finishers"])
            b["finishers"] = f.finishers
            return v + (got if mine else 0)
        if oid == "moves":  # (the kinds landed or blocked: a kick (S, forward + S, X + S), a jump kick, the special)
            kinds = {"kick": ("kick", "high", "low"), "jump kick": ("jump_kick",), "special": (f.special,)}
            have = set(b.get("kinds", []))
            for kind, moves in kinds.items():
                if mine and any(f.connected.get(m, 0) > b["connected"].get(m, 0) for m in moves):
                    have.add(kind)
            b["kinds"], b["connected"] = sorted(have), dict(f.connected)
            return float(len(have))
        if oid == "bout":  # (a match over in the learner's ring, judged once: won, or not this time)
            ring = f.ring
            if not ring.match_over or b.get("judged") is ring:
                return None
            b["judged"] = ring
            if self.bout_winner(ring, stage) is f:
                if enemy is not None and enemy.knocked_out:
                    self.experience_bonus(p.name, "bout")
                return 1.0
            self.experience_say(p.name, "Not this time." + (" Press REMATCH to go again." if self.solo else
                                                            " Win the next one."))
        return None

    @staticmethod
    def angle_round(f, enemy):
        """Where f is, round the other fighter (degrees), or None with nobody to go round."""
        if enemy is None:
            return None
        return math.degrees(math.atan2(f.y - enemy.y, f.x - enemy.x))

    @staticmethod
    def bout_winner(ring, stage):
        """The fighter who won the ring's match (the rounds it takes to win), or None."""
        return next((g for g in ring.fighters if g.wins >= stage.rounds_to_win), None)

    def x_built(self, name, oid, kinds=None):
        """A build counts towards the garage objective (the kinds of variable it changed) or the code one."""
        if self.experience is None:
            return
        run = self.xrun(self.record(name))
        o = self.x_objective(run)
        if o is None or o["id"] != oid:
            return
        self.x_measuring(run)
        if kinds is None:
            run["value"] = 1.0
        else:
            have = set(run["base"].get("kinds", [])) | kinds
            run["base"]["kinds"] = sorted(have)
            run["value"] = float(len(have & {"string", "integer", "list"}))

    def experience_garage(self, p, new, old, by_code):
        """A learner's build, as Mission 1's objectives a to d see it: with the Garage, the kinds of variable it
        changed (the name a string; a setting or a point an integer; the colour or the combo a list); from the code
        panel, any value changed."""
        if by_code:
            if teaching.design_changes(old, new, sim.schema()):
                self.x_built(p.name, "code")
            return
        kinds = set()
        if new.get("name") != old.get("name", p.name):
            kinds.add("string")
        if any(new["settings"].get(k) != (old.get("settings") or {}).get(k) for k in new.get("settings", {})) or \
                any(new["points"].get(k) != (old.get("points") or {}).get(k) for k in new.get("points", {})):
            kinds.add("integer")
        if new.get("colour") != old.get("colour", p.start_colour) or new.get("combo") != old.get("combo"):
            kinds.add("list")
        self.x_built(p.name, "garage", kinds)

    def experience_begin(self, p, r, oid, f, stage, run):
        if oid == "footwork" and r.autopilot:  # (the start: you fight, not your brain from last time)
            self.autopilot_off(p, r)
        if oid == "bout" and self.solo:
            self.solo_bout(p, r, run)

    def experience_actions(self, p, r, oid, run):
        f = p.fighter
        if oid == "bout" and self.solo and f is not None and f.ring.match_over and \
                self.bout_winner(f.ring, self.server.stage) is not f:
            return [["rematch", "REMATCH"]]
        return []

    def experience_action(self, p, r, action, run):
        o = self.x_objective(run)
        if action == "rematch" and self.solo and o is not None and o["id"] == "bout":
            self.solo_bout(p, r, run)

    def experience_ended(self, p, r, oid, run):
        if oid == "bout" and self.solo:
            self.solo_practice(run)

    def experience_reset(self, p, r, run):
        if self.solo:
            self.solo_practice(run)

    def autopilot_off(self, p, r):
        r.autopilot = False
        self.attach(p)
        self.save_profile(p.name)

    def solo_bout(self, p, r, run):
        """On your own: a bout against the computer fighter, its brain on (Easy), with the real countdown (the
        lesson's battle mode, as the teacher's Battle button gives: ROUND 1, 3, 2, 1, GO!)."""
        L = self.server.lesson
        run["base"].setdefault("was", {k: L.get(k) for k in ("mode", "cpu_level")})
        run["base"].pop("judged", None)
        L.update(mode="battle", cpu_level="easy")
        if r.autopilot:  # (this one's you)
            self.autopilot_off(p, r)
        self.server.rebuild_stage()
        self.server.lesson_dirty = True  # (the windows are told, as the teacher's changes are: the physics loop)

    def solo_practice(self, run):
        was = run["base"].pop("was", None)
        if was:
            self.server.lesson.update(was)
            self.server.rebuild_stage()
            self.server.lesson_dirty = True

