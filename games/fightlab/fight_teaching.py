"""Fight Lab's teaching: what is Fight Lab's own on top of the engine's framework (engine/teaching.py): which
builds, fights and brains complete which objectives, and the fighter files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
fight_missions.py, so the teacher can see (and export) who has shown what.
"""
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


GAME = teaching.Game(missions=fm, profiles=fight_profiles, brain=fight_brain, sim=sim, data=DATA, designs=FIGHTERS_DIR,
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

