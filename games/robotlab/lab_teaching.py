"""Robot Lab's teaching: what is Robot Lab's own on top of the engine's framework (engine/teaching.py): which
builds, drives and brains complete which objectives, and the robot files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
lab_missions.py, so the teacher can see (and export) who has shown what.
"""
import asyncio
import math
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


GAME = teaching.Game(slug_word="robotlab", missions=lm, profiles=lab_profiles, brain=lab_brain, sim=sim, data=DATA, designs=ROBOTS_DIR,
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
        self.experience_garage(p, new, old, by_code)  # (Experience 1's garage and code objectives: CHANGE 210)
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

    # ---------- Experience 1, Orientation (CHANGE 210): what each objective measures, in the real arena ----------
    def experience_value(self, p, r, oid, robot, arena, now, run):
        b, v = run["base"], run["value"]
        if oid == "brain":
            return r.brain.seconds_running(now) if (r.brain and r.autopilot and not r.brain.error) else None
        if robot is None or oid not in ("drive", "turn", "speed", "weapon", "target", "bout"):
            return None  # (the garage and the code are counted as they are built: build_checks)
        if b.get("robot") is not robot:  # (the objective's start, or a new robot after a rebuild: measured from here)
            b.update(robot=robot, pos=(robot.pos.x, robot.pos.y), h=robot.np.getH(), fires=robot.fires,
                     on=robot.weapon_on, hits=robot.hits)
            return None
        if oid == "drive":
            x, y = robot.pos.x, robot.pos.y
            step = math.hypot(x - b["pos"][0], y - b["pos"][1])
            b["pos"] = (x, y)
            return v + (0.0 if r.autopilot or step > 5 else step)  # (a jump back to the start square isn't driving)
        if oid == "turn":
            h = robot.np.getH()
            step = abs((h - b["h"] + 180) % 360 - 180)
            b["h"] = h
            return v + (0.0 if r.autopilot else step)
        if oid == "speed":
            return max(v, abs(robot.speed) * 3.6)
        if oid == "weapon":  # (a wedge or hammer fires; a spinner or drum is switched on or off)
            used = max(0, robot.fires - b["fires"]) + (robot.weapon_on != b["on"])
            b["fires"], b["on"] = robot.fires, robot.weapon_on
            return v + used
        if oid == "target":
            got = max(0, robot.hits - b["hits"])
            b["hits"] = robot.hits
            return v + got
        if oid == "bout":
            winner, _ = self.server.result(robot.arena)
            final = robot.arena.final
            if final is None or b.get("judged") is final:
                return None
            b["judged"] = final
            if winner is robot:
                others = [x for x in robot.arena.robots if x is not robot and not x.house]
                if others and all(x.knocked_out for x in others):
                    self.experience_bonus(p.name, "bout")
                return 1.0
            self.experience_say(p.name, "Not this time." + (" Press REMATCH to go again." if self.solo else
                                                            " Win the next one."))
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
        if new.get("colour") != old.get("colour", p.start_colour):
            kinds.add("list")
        self.x_built(p.name, "garage", kinds)

    def experience_begin(self, p, r, oid, robot, arena, run):
        if oid == "bout" and self.solo:
            self.solo_battle(r, run)

    def experience_actions(self, p, r, oid, run):
        robot = p.robot
        if oid == "bout" and self.solo and robot is not None and robot.arena.final is not None and \
                self.server.result(robot.arena)[0] is not robot:
            return [["rematch", "REMATCH"]]
        return []

    def experience_action(self, p, r, action, run):
        o = self.x_objective(run)
        if action == "rematch" and self.solo and o is not None and o["id"] == "bout":
            self.solo_battle(r, run)

    def experience_ended(self, p, r, oid, run):
        if oid == "bout" and self.solo:
            self.solo_practice(run)

    def experience_reset(self, p, r, run):
        if self.solo:
            self.solo_practice(run)

    def solo_battle(self, r, run):
        """On your own: a battle against the computer robot, its brain on (easy), with the real countdown."""
        L = self.server.lesson
        run["base"].setdefault("was", {k: L.get(k) for k in ("mode", "cpu_level", "time_limit")})
        run["base"].pop("judged", None)
        L.update(mode="battle", cpu_level="easy", time_limit=60)
        if r.autopilot:  # (this one's you)
            r.autopilot = False
        self.server.rebuild_arena(intro=True)
        self.tell_everyone()

    def solo_practice(self, run):
        was = run["base"].pop("was", None)
        if was:
            self.server.lesson.update(was)
            self.server.rebuild_arena()
            self.tell_everyone()

    def tell_everyone(self):
        """The lesson changed under the windows (a battle on your own): they are told as the teacher's changes are."""
        try:
            asyncio.get_running_loop().create_task(self.server.broadcast_lesson())
        except RuntimeError:  # (no loop running: a test calling this directly)
            pass
