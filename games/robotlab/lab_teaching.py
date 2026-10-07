"""Robot Lab's teaching: what is Robot Lab's own on top of the engine's framework (engine/teaching.py): which
builds, drives and brains complete which objectives, and the robot files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
lab_missions.py, so the teacher can see (and export) who has shown what.
"""
import os

import lab_version  # noqa: F401  (puts the engine on the path)
import lab_brain
import lab_missions as lm
import lab_profiles
import lab_sim as sim
import rw_mods
from ai_pipeline import robot_file_text, slug
from engine import teaching

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("ROBOTLAB_DATA", HERE)  # (tests point this somewhere else)
EVIDENCE_DIR = os.path.join(DATA, "evidence")
CARDS_DIR = os.path.join(DATA, "ai_requests")
ROBOTS_DIR = os.path.join(DATA, "mods", "robots")  # learners' robots: with the rest of their data (one set per class)
now_text = teaching.now_text


class Record(teaching.Record):
    def __init__(self, name):
        super().__init__(name)
        self.top_speed = 0.0       # fastest forward speed since the last build, km/h


def apply_mods(t, files):
    """Check and save changed mod files (the arena, the rules, learners' robots), then use them straight away."""
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
    t.server.reload_mods(written)
    return "Applied: " + ", ".join(written) if written else "Nothing to apply"


GAME = teaching.Game(missions=lm, profiles=lab_profiles, brain=lab_brain, sim=sim, data=DATA, designs=ROBOTS_DIR,
                     design_text=robot_file_text, load_design=rw_mods.load_robot, mod_error=rw_mods.ModError,
                     apply_mods=apply_mods, slug=slug, unit=lambda p: p.robot, world=lambda server: server.arena,
                     units=lambda arena: arena.robots, rebuild=lambda server: server.rebuild_arena())


class Teaching(teaching.Teaching):
    record_class = Record
    reflections = {"2d": 8, "5b": 20}  # mission id -> the words a reflection needs to count

    def __init__(self, server):
        super().__init__(server, GAME)

    def build_rejected(self, p, r, problems, new=None, by_code=False):
        """Mission 2 b (CHANGE 94): the code editor tried to spend more than the points to share."""
        total = self.server.lesson["limits"]["points_total"]
        pts = (new or {}).get("points", {})
        spent = sum(v for v in pts.values() if isinstance(v, int)) if isinstance(pts, dict) else 0
        if by_code and spent > total:
            self.complete(p.name, "2b", f"Tried to spend {spent} points in the code: refused, the most is {total}")

    def build_checks(self, p, r, new, old, by_code):
        """Mission 1's objectives a, b and c (with the GUI), and mission 2's points."""
        r.top_speed = 0.0
        defaults = {k: v[2] for k, v in sim.SETTINGS.items()}
        if not by_code:
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
        if sum(new["points"].values()) == limits["points_total"] and not by_code:  # (with the GUI: CHANGE 94)
            self.complete(p.name, "2a", "Points " + ", ".join(f"{k} {v}" for k, v in new["points"].items()) +
                          " (all 100 shared, with the GUI)".replace("100", str(limits["points_total"])))
        edge = [k for k, v in new["points"].items() if v in limits["points"][k]]
        if edge:
            self.complete(p.name, "2c", "Boundary value accepted: " + ", ".join(f"{k} = {new['points'][k]}" for k in edge))

    def tick_checks(self, p, r, robot, arena, now):
        r.top_speed = max(r.top_speed, robot.speed * 3.6)
        if r.built and robot.hits - r.hits_at_build >= 3 and len(r.text.get("2d", "").split()) >= 8:
            self.complete(p.name, "2d", f"{robot.hits - r.hits_at_build} hits after rebuilding. Why: {r.text['2d']}")
        if r.brain and r.autopilot and r.brain.seconds_running(now) >= 20:
            self.complete(p.name, "3a", f"Brain ran for {r.brain.seconds_running(now):.0f} s without an error")
        if self.lesson_number == 5 and not arena.practice and r.built and r.brain and not r.brain.error:
            self.complete(p.name, "5a", "Entered the final battle with their own design and brain")

    def predicted(self, p, r):
        r.top_speed = 0.0

    def reflected(self, p, r, mission, text):
        if mission == "5b" and len(text.split()) >= self.reflections["5b"]:
            self.complete(p.name, "5b", text)

    def brain_checks(self, p, r):
        if "if" in r.brain_features:
            self.complete(p.name, "3b", "Brain uses if / elif / else")
        if "own_function" in r.brain_features:
            self.complete(p.name, "3c", "Brain calls its own helper function")
        if "memory" in r.brain_features:
            self.complete(p.name, "3d", "Brain keeps state in me.memory")

    def missions_extra(self, r):
        return {"top_speed": round(r.top_speed, 1)}
