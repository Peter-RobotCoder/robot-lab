"""City Lab's teaching: what is City Lab's own on top of the engine's framework (engine/teaching.py): which
builds, jobs and brains complete which objectives, and the driver files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
city_missions.py, so the teacher can see (and export) who has shown what.
"""
import os

import city_version  # noqa: F401  (puts the engine on the path)
import city_brain
import city_missions as cm
import city_mods
import city_profiles
import city_sim as sim
from ai_pipeline import driver_file_text, slug
from engine import teaching

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("CITYLAB_DATA") or os.path.join(HERE, "data")  # (tests point this somewhere else)
EVIDENCE_DIR = os.path.join(DATA, "evidence")
CARDS_DIR = os.path.join(DATA, "ai_requests")
DRIVERS_DIR = os.path.join(DATA, "mods", "drivers")  # learners' designs: with the rest of their data
now_text = teaching.now_text


class Record(teaching.Record):
    def __init__(self, name):
        super().__init__(name)
        self.jobs_seen = 0          # how many of the world's finished jobs this record has looked at
        self.built_at = None        # the world's tick when the design was last built
        self.best_delivery = None   # the quickest delivery since the last build or prediction, seconds


def apply_mods(t, files):
    """Check and save changed mod files (the city, the rules, learners' drivers), then use them straight away."""
    written = []
    if not isinstance(files, dict):
        return "Nothing to apply"
    for rel, text in files.items():
        rel = str(rel).replace("\\", "/")
        name_part = rel[len("mods/drivers/"):]
        ok = rel in ("mods/city.py", "mods/rules.py") or (
            rel.startswith("mods/drivers/") and rel.endswith(".py") and "/" not in name_part and ".." not in rel)
        if not ok:
            return f"Not applied: {rel} isn't a mod file"
        path = os.path.join(DRIVERS_DIR, name_part) if rel.startswith("mods/drivers/") else os.path.join(HERE, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".check"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(text))
        try:
            if rel == "mods/rules.py":
                city_mods.read_dict(tmp, "RULES")
            elif rel == "mods/city.py":
                city_mods.read_dict(tmp, "CITY")
            else:
                city_mods.load_driver(tmp)
        except city_mods.ModError as e:
            os.remove(tmp)
            return f"Not applied: {e}"
        os.replace(tmp, path)
        written.append(rel)
    t.server.reload_mods(written)
    return "Applied: " + ", ".join(written) if written else "Nothing to apply"


GAME = teaching.Game(slug_word="citylab", missions=cm, profiles=city_profiles, brain=city_brain, sim=sim, data=DATA,
                     designs=DRIVERS_DIR, design_text=driver_file_text, load_design=city_mods.load_driver,
                     mod_error=city_mods.ModError, apply_mods=apply_mods, slug=slug,
                     unit=lambda p: p.unit, world=lambda server: server.world,
                     units=lambda world: list(getattr(world, "units", {}).values()),
                     rebuild=lambda server: server.rebuild())


class Teaching(teaching.Teaching):
    record_class = Record
    reflections = cm.REFLECTIONS  # mission id -> the words a reflection needs to count

    def __init__(self, server):
        super().__init__(server, GAME)

    # ---------- what the server asks ----------
    def attach(self, p):
        """Give a person their brain when autopilot is on (the teacher's too: they test brains as learners do)."""
        r = self.record(p.name)
        unit = self.g.unit(p)
        if unit is None:
            return
        unit.brain = r.brain if (r.brain and r.autopilot) else None

    def jobs_done(self, p, r):
        """The jobs this person finished since the record last looked."""
        done = getattr(self.server.world.jobs, "done", [])
        if r.jobs_seen > len(done):  # (a new world: the city changed)
            r.jobs_seen = 0
        fresh = [d for d in done[r.jobs_seen:] if d["pid"] == p.person]
        r.jobs_seen = len(done)
        return fresh

    # ---------- the game's own: what completes which objective ----------
    def build_rejected(self, p, r, problems, new=None, by_code=False):
        """Mission 2 b: the code editor tried to spend more than the points to share."""
        total = self.server.lesson["limits"]["points_total"]
        pts = (new or {}).get("points") if isinstance((new or {}).get("points"), dict) else {}
        spent = sum(v for v in (pts.get(k) for k in sim.STATS) if isinstance(v, int) and not isinstance(v, bool))
        if by_code and spent > total:
            self.complete(p.name, "2b", f"Tried to spend {spent} points in the code: refused, the most is {total}")

    def build_checks(self, p, r, new, old, by_code):
        """Mission 1's objectives a, b, c and d, and mission 2's points."""
        r.best_delivery = None
        r.built_at = self.server.world.tick
        pts, was_pts = new.get("points", {}), old.get("points", sim.default_design()["points"])
        if by_code:
            changed = [k for k in ("name", "colour", "body", "look") if new.get(k) != old.get(k)] + \
                [k for k in sim.STATS if pts.get(k) != was_pts.get(k)]
            if changed:
                self.complete(p.name, "1d", "Changed in the code: " + ", ".join(changed))
        else:
            was = old.get("name", p.name)
            if new["name"] != was:
                self.complete(p.name, "1a", f'driver_name "{was}" became "{new["name"]}" (a string, with the GUI)')
            changed = [k for k in sim.STATS if pts.get(k) != was_pts.get(k)]
            if len(changed) >= 2:
                self.complete(p.name, "1b", ", ".join(f"{k} = {pts[k]}" for k in changed) + " (integers, with the GUI)")
            if new["colour"] != old.get("colour", p.start_colour):
                self.complete(p.name, "1c", f"colour = {new['colour']} (a list, with the GUI)")
        limits = self.server.lesson["limits"]  # (the points to share and each point's range are the teacher's)
        if sum(pts[k] for k in sim.STATS) == limits["points_total"] and not by_code:
            self.complete(p.name, "2a", "Points " + ", ".join(f"{k} {pts[k]}" for k in sim.STATS) +
                          f" (all {limits['points_total']} shared, with the GUI)")
        edge = [k for k in sim.STATS if pts[k] in limits["points"][k]]
        if edge:
            self.complete(p.name, "2c", "Boundary value accepted: " + ", ".join(f"{k} = {pts[k]}" for k in edge))

    def tick_checks(self, p, r, unit, world, now):
        for d in self.jobs_done(p, r):
            if d["kind"] == "delivery":
                if r.best_delivery is None or d["seconds"] < r.best_delivery:
                    r.best_delivery = d["seconds"]
                if r.prediction is not None and self.lesson_number == 2:
                    self.complete(p.name, "2d", f"Predicted {r.prediction:g} s, delivered in {d['seconds']:.1f} s "
                                                f"({abs(d['seconds'] - r.prediction):.1f} s out)")
                if d["brain"]:
                    self.complete(p.name, "3e", f"Autopilot delivered a parcel in {d['seconds']:.1f} s, "
                                                f"earning {d['pay']}")
            if d["kind"] in ("delivery", "taxi") and r.built and r.built_at is not None and \
                    len(r.text.get("2e", "").split()) >= cm.REFLECTIONS["2e"]:
                self.complete(p.name, "2e", f"A {d['kind']} in {d['seconds']:.1f} s earning {d['pay']} after "
                                            f"rebuilding. Why: {r.text['2e']}")
            if d["kind"] == "race":
                level = self.server.lesson.get("cpu_level")
                if d["place"] == 1 and level == "expert" and getattr(self.server, "racers_raced", False):
                    self.complete(p.name, "4d", f"Won a street race in {d['seconds']:.1f} s against expert racers")
                if self.lesson_number == 5 and r.built and r.brain and not r.brain.error:
                    self.complete(p.name, "5a", f"Raced in the street race with their own design and brain "
                                                f"(finished {d['place']})")
        if r.brain and r.autopilot and r.brain.seconds_running(now) >= 20:
            self.complete(p.name, "3a", f"Brain ran for {r.brain.seconds_running(now):.0f} s without an error")

    def predicted(self, p, r):
        r.best_delivery = None

    def reflected(self, p, r, mission, text):
        if mission == "5b" and len(text.split()) >= cm.REFLECTIONS["5b"]:
            self.complete(p.name, "5b", text)

    def brain_checks(self, p, r):
        if "if" in r.brain_features:
            self.complete(p.name, "3b", "Brain uses if / elif / else")
        if "own_function" in r.brain_features:
            self.complete(p.name, "3c", "Brain calls its own helper function")
        if "memory" in r.brain_features:
            self.complete(p.name, "3d", "Brain keeps state in me.memory")

    def missions_extra(self, r):
        return {"best_delivery": None if r.best_delivery is None else round(r.best_delivery, 1)}

    def record_extra(self, r):
        return {"best_delivery": r.best_delivery}

    def restore_record(self, r, saved):
        if r.best_delivery is None and isinstance(saved.get("best_delivery"), (int, float)):
            r.best_delivery = float(saved["best_delivery"])
