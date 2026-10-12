"""Kart Lab's teaching: what is Kart Lab's own on top of the engine's framework (engine/teaching.py): which
builds, laps and brains complete which objectives, and the kart files learners' designs are kept in.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
kart_missions.py, so the teacher can see (and export) who has shown what.
"""
import os

import kart_version  # noqa: F401  (puts the engine on the path)
import kart_brain
import kart_missions as km
import kart_mods
import kart_profiles
import kart_sim as sim
from ai_pipeline import kart_file_text, slug
from engine import teaching

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("KARTLAB_DATA") or os.path.join(HERE, "data")  # (tests point this somewhere else)
EVIDENCE_DIR = os.path.join(DATA, "evidence")
CARDS_DIR = os.path.join(DATA, "ai_requests")
KARTS_DIR = os.path.join(DATA, "mods", "karts")  # learners' karts: with the rest of their data
now_text = teaching.now_text


class Record(teaching.Record):
    def __init__(self, name):
        super().__init__(name)
        self.best_lap = None        # the fastest lap since the last build or prediction, seconds
        self.laps_at_build = 0      # laps the kart had done when the design was last built
        self.laps_at_autopilot = None
        self.lap_times_seen = 0     # how many of the kart's lap times this record has looked at


def apply_mods(t, files):
    """Check and save changed mod files (the track, the rules, learners' karts), then use them straight away."""
    written = []
    if not isinstance(files, dict):
        return "Nothing to apply"
    for rel, text in files.items():
        rel = str(rel).replace("\\", "/")
        name_part = rel[len("mods/karts/"):]
        ok = rel in ("mods/track.py", "mods/rules.py") or (
            rel.startswith("mods/karts/") and rel.endswith(".py") and "/" not in name_part and ".." not in rel)
        if not ok:
            return f"Not applied: {rel} isn't a mod file"
        path = os.path.join(KARTS_DIR, name_part) if rel.startswith("mods/karts/") else os.path.join(HERE, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".check"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(text))
        try:
            if rel == "mods/rules.py":
                kart_mods.read_dict(tmp, "RULES")
            elif rel == "mods/track.py":
                kart_mods.read_dict(tmp, "TRACK")
            else:
                kart_mods.load_kart(tmp)
        except kart_mods.ModError as e:
            os.remove(tmp)
            return f"Not applied: {e}"
        os.replace(tmp, path)
        written.append(rel)
    t.server.reload_mods(written)
    return "Applied: " + ", ".join(written) if written else "Nothing to apply"


GAME = teaching.Game(slug_word="kartlab", missions=km, profiles=kart_profiles, brain=kart_brain, sim=sim, data=DATA,
                     designs=KARTS_DIR, design_text=kart_file_text, load_design=kart_mods.load_kart,
                     mod_error=kart_mods.ModError, apply_mods=apply_mods, slug=slug,
                     unit=lambda p: p.unit, world=lambda server: server.race,
                     units=lambda race: list(getattr(race, "units", {}).values()),
                     rebuild=lambda server: server.rebuild())


class Teaching(teaching.Teaching):
    record_class = Record
    reflections = km.REFLECTIONS  # mission id -> the words a reflection needs to count

    def __init__(self, server):
        super().__init__(server, GAME)

    # ---------- what the server asks ----------
    def attach(self, p):
        """Give a kart its brain when autopilot is on (the teacher's too: they test brains as learners do)."""
        r = self.record(p.name)
        unit = self.g.unit(p)
        if unit is None:
            return
        unit.brain = r.brain if (r.brain and r.autopilot) else None

    def lap_times(self, p):
        race = self.server.race
        return race.lap_times.get(p.kart, []) if p.kart is not None else []

    # ---------- the game's own: what completes which objective ----------
    def build_rejected(self, p, r, problems, new=None, by_code=False):
        """Mission 2 b: the code editor tried to spend more than the points to share."""
        total = self.server.lesson["limits"]["points_total"]
        vals = [(new or {}).get(k) for k in sim.STATS]
        spent = sum(v for v in vals if isinstance(v, int) and not isinstance(v, bool))
        if by_code and spent > total:
            self.complete(p.name, "2b", f"Tried to spend {spent} points in the code: refused, the most is {total}")

    def build_checks(self, p, r, new, old, by_code):
        """Mission 1's objectives a, b and c (with the GUI), and mission 2's points."""
        r.best_lap = None
        r.laps_at_build = len(self.lap_times(p))
        r.lap_times_seen = r.laps_at_build
        if not by_code:
            was = old.get("name", p.name)
            if new["name"] != was:
                self.complete(p.name, "1a", f'kart_name "{was}" became "{new["name"]}" (a string, with the GUI)')
            changed = [k for k in sim.STATS if new.get(k) != old.get(k, sim.default_design()[k])]
            if len(changed) >= 2:
                self.complete(p.name, "1b", ", ".join(f"{k} = {new[k]}" for k in changed) + " (integers, with the GUI)")
            if new["colour"] != old.get("colour", p.start_colour):
                self.complete(p.name, "1c", f"colour = {new['colour']} (a list, with the GUI)")
        limits = self.server.lesson["limits"]  # (the points to share and each point's range are the teacher's)
        if sum(new[k] for k in sim.STATS) == limits["points_total"] and not by_code:
            self.complete(p.name, "2a", "Points " + ", ".join(f"{k} {new[k]}" for k in sim.STATS) +
                          f" (all {limits['points_total']} shared, with the GUI)")
        edge = [k for k in sim.STATS if new[k] in limits["points"][k]]
        if edge:
            self.complete(p.name, "2c", "Boundary value accepted: " + ", ".join(f"{k} = {new[k]}" for k in edge))

    def tick_checks(self, p, r, unit, race, now):
        laps = self.lap_times(p)
        if len(laps) > r.lap_times_seen:  # new lap times since this record last looked
            fresh = laps[r.lap_times_seen:]
            r.lap_times_seen = len(laps)
            best = min(fresh)
            if r.best_lap is None or best < r.best_lap:
                r.best_lap = best
            if r.prediction is not None and self.lesson_number == 2:
                self.complete(p.name, "2d", f"Predicted {r.prediction:g} s, lapped in {best:.2f} s "
                                            f"({abs(best - r.prediction):.2f} s out)")
        if r.built and len(laps) > r.laps_at_build and len(r.text.get("2e", "").split()) >= km.REFLECTIONS["2e"]:
            self.complete(p.name, "2e", f"Lapped in {min(laps[r.laps_at_build:]):.2f} s after rebuilding. "
                                        f"Why: {r.text['2e']}")
        if r.brain and r.autopilot:
            if r.brain.seconds_running(now) >= 20:
                self.complete(p.name, "3a", f"Brain ran for {r.brain.seconds_running(now):.0f} s without an error")
            if r.laps_at_autopilot is None:
                r.laps_at_autopilot = len(laps)
            elif len(laps) > r.laps_at_autopilot and not r.brain.error:
                self.complete(p.name, "3e", f"Autopilot drove a lap in {laps[-1]:.2f} s")
        else:
            r.laps_at_autopilot = None
        if race.phase == sim.FLAGS_OVER and p.kart in race.finish and not race.practice:
            places = race.places()
            aces = [kid for kid, level in self.server.cpu_levels.items() if level == "expert" and kid in race.karts]
            if aces and any(places.index(p.kart) < places.index(a) for a in aces if a in places):
                self.complete(p.name, "4d", f"Finished {race.ordinal(places.index(p.kart) + 1)}, ahead of an "
                                            f"expert computer kart")
        if self.lesson_number == 5 and not race.practice and r.built and r.brain and not r.brain.error:
            self.complete(p.name, "5a", "Entered the grand prix with their own design and brain")

    def predicted(self, p, r):
        r.best_lap = None
        r.lap_times_seen = len(self.lap_times(p))

    def reflected(self, p, r, mission, text):
        if mission == "5b" and len(text.split()) >= km.REFLECTIONS["5b"]:
            self.complete(p.name, "5b", text)

    def brain_checks(self, p, r):
        if "if" in r.brain_features:
            self.complete(p.name, "3b", "Brain uses if / elif / else")
        if "own_function" in r.brain_features:
            self.complete(p.name, "3c", "Brain calls its own helper function")
        if "memory" in r.brain_features:
            self.complete(p.name, "3d", "Brain keeps state in me.memory")

    def missions_extra(self, r):
        return {"best_lap": None if r.best_lap is None else round(r.best_lap, 2)}

    def record_extra(self, r):
        return {"best_lap": r.best_lap}

    def restore_record(self, r, saved):
        if r.best_lap is None and isinstance(saved.get("best_lap"), (int, float)):
            r.best_lap = float(saved["best_lap"])
