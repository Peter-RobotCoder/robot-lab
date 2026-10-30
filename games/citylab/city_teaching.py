"""City Lab's teaching: what is City Lab's own on top of the engine's framework (engine/teaching.py): which
builds, jobs and brains complete which objectives, and the driver files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
city_missions.py, so the teacher can see (and export) who has shown what.
"""
import asyncio
import math
import os

import city_version  # noqa: F401  (puts the engine on the path)
import city_brain
import city_jobs
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
        self.experience_garage(p, new, old, by_code)  # (Experience 1's garage and code objectives: CHANGE 210)
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

    # ---------- Experience 1, Orientation (CHANGE 210): what each objective measures, in the real city ----------
    # Each one is read from the world as the game has it: the person's record and the car they are in (city_sim),
    # the punches and kicks that landed (World.landed), the surface under the car (city_map), the jobs finished
    # (city_jobs.Jobs.done), the builds (build_checks) and the brain's time on autopilot. run["base"] keeps what an
    # objective measures from; a new world (the teacher chose another city) starts it again from there.
    X_MEASURED = ("walk", "robot", "car", "drive", "delivery", "race")

    def experience_value(self, p, r, oid, unit, world, now, run):
        b, v = run["base"], run["value"]
        if oid == "brain":
            return r.brain.seconds_running(now) if (r.brain and r.autopilot and not r.brain.error) else None
        if unit is None or oid not in self.X_MEASURED:
            return None  # (the garage and the code are counted as they are built: build_checks)
        me = world.people.get(unit.pid)
        if me is None:
            return None
        car = world.cars.get(me["link"] - 1) if me["link"] else None
        if b.get("world") is not world or b.get("pid") != unit.pid:  # (the objective's start, or a new city)
            b.update(world=world, pid=unit.pid, since=world.tick, pos=(me["x"], me["y"]), car=None,
                     landed=world.landed.get(unit.pid, 0))
            return None
        if oid == "walk":  # on foot, by the learner (not the autopilot): a jump back to the depot (R) isn't walking
            step = math.hypot(me["x"] - b["pos"][0], me["y"] - b["pos"][1])
            b["pos"] = (me["x"], me["y"])
            return v + (0.0 if r.autopilot or car is not None or step > 5 else step)
        if oid == "robot":  # the punches and kicks that landed (a robot powered down, then rebooted, still counts)
            landed = world.landed.get(unit.pid, 0)
            got = max(0, landed - b["landed"])
            b["landed"] = landed
            return v + got
        if oid == "car":
            return 1.0 if car is not None and not r.autopilot else None
        if oid == "drive":  # metres driven on the road: the pavement, the grass and the car park don't count
            if car is None or r.autopilot:
                b["car"] = None
                return None
            at = (car["x"], car["y"])
            if b.get("car") != car["id"]:  # (into a car, or another one: measured from here)
                b["car"], b["cpos"] = car["id"], at
                return None
            step = math.hypot(at[0] - b["cpos"][0], at[1] - b["cpos"][1])
            b["cpos"] = at
            return v + (step if step <= 5 and world.city.surface(at[0], at[1]) == "road" else 0.0)
        mine = [d for d in getattr(world.jobs, "done", []) if d["pid"] == unit.pid and d["tick"] >= b["since"]]
        if oid == "delivery":  # (late still counts: the job is done, for less)
            return 1.0 if any(d["kind"] == "delivery" for d in mine) else None
        if oid == "race":
            finished = [d for d in mine if d["kind"] == "race"]
            if finished:
                if any(d["place"] == 1 for d in finished):
                    self.experience_bonus(p.name, "race")
                return 1.0
            job = world.jobs.mine.get(unit.pid)
            if job is not None and job["kind"] == city_jobs.RACE:
                b["racing"] = True
            elif b.pop("racing", False):  # (the race ended before this learner was back at the line)
                self.experience_say(p.name, "Not this time: the race ended before you were back at the line." +
                                    (" Press REMATCH to go again." if self.solo else " Try the next one."))
        return None

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
        """BUILD MY DRIVER: from the code panel with a change in it (the code objective), or from the Garage (the
        garage objective: the kinds of variable it changed, a build at a time)."""
        if by_code:
            if teaching.design_changes(old, new, sim.schema()):
                self.x_built(p.name, "code")
            return
        kinds = set()
        if any(new.get(k) != old.get(k, p.name if k == "name" else None) for k in ("name", "body", "look")):
            kinds.add("string")  # (driver_name, car and look are all STRING VARIABLES in the Garage)
        was_pts = old.get("points") or {}
        if any(new.get("points", {}).get(k) != was_pts.get(k) for k in sim.STATS):
            kinds.add("integer")
        if new.get("colour") != old.get("colour", p.start_colour):
            kinds.add("list")
        self.x_built(p.name, "garage", kinds)

    def experience_begin(self, p, r, oid, unit, world, run):
        if oid == "race" and self.solo:
            self.solo_race(p, r, run)

    def experience_actions(self, p, r, oid, run):
        if oid == "race" and self.solo and self.server.world.jobs.race is None:
            return [["rematch", "REMATCH"]]  # (no race running, and this one not finished: another, on the line)
        return []

    def experience_action(self, p, r, action, run):
        o = self.x_objective(run)
        if action == "rematch" and self.solo and o is not None and o["id"] == "race" \
                and self.server.world.jobs.race is None:
            self.solo_race(p, r, run)

    def experience_ended(self, p, r, oid, run):
        if oid == "race" and self.solo:
            self.solo_practice(run)

    def experience_reset(self, p, r, run):
        if self.solo:
            self.solo_practice(run)

    def solo_race(self, p, r, run):
        """On your own: the street race the teacher's Enter starts (city_server.line_up_race): you in a car on the
        line, the computer's racers (easy) beside you, the real countdown. The lesson's mode goes back after it."""
        L = self.server.lesson
        run["base"].setdefault("was", {"mode": L.get("mode", "practice")})
        run["base"].pop("racing", None)
        if r.autopilot:  # (this one's you)
            r.autopilot = False
            self.attach(p)
        self.server.rebuild()  # (the last race's racers, gone off as traffic, back to the lesson's number)
        self.server.line_up_race()
        self.tell_everyone()

    def solo_practice(self, run):
        was = run["base"].pop("was", None)
        if was:
            self.server.lesson.update(was)
            self.server.rebuild()
            self.tell_everyone()

    def tell_everyone(self):
        """The lesson changed under the windows (a race on your own): they are told as the teacher's changes are."""
        try:
            asyncio.get_running_loop().create_task(self.server.broadcast_lesson())
        except RuntimeError:  # (no loop running: a test calling this directly)
            pass
