"""Load and check the mods: karts (mods/karts/*.py), the track choice (mods/track.py) and the rules (mods/rules.py).

Mods are plain data (a dictionary in each file). They are read with ast.literal_eval, so nothing in them
runs as code. Every value is checked against sensible limits before the game uses it.

    python kart_mods.py          check the mods and run a quick test race (used after every AI change)
"""
import ast
import os

import kart_sim as sim
import kart_track

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(HERE, "mods")

RULE_LIMITS = {
    "laps": (1, 9), "cpu_karts": (0, 7), "countdown_seconds": (1.0, 10.0), "bump_distance": (1.0, 3.0),
    "bump_slowdown": (0.0, 1.0),
}
HAZARDS = ("bumping", "cpu_karts")  # (the lesson's switches: see kart_missions.NO_HAZARDS)


class ModError(Exception):
    pass


def read_dict(path, var):
    """The dictionary assigned to `var` in a mod file, read as data only."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=os.path.basename(path))
    except SyntaxError as e:
        raise ModError(f"{os.path.basename(path)} line {e.lineno}: {e.msg}") from None
    for node in tree.body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == [var]:
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                raise ModError(f"{os.path.basename(path)}: {var} may only contain plain values") from None
    raise ModError(f"{os.path.basename(path)} has no {var} = {{...}}")


def colour_ok(c):
    return isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                                                        for v in c)


def check_kart(d):
    """Problems with a kart design (empty = fine): the widest ranges, as a mod file is the teacher's business."""
    return sim.check_design(d, sim.full_limits())


def load_kart(path):
    d = read_dict(path, "KART")
    problems = check_kart(d)
    if problems:
        raise ModError(f"{os.path.basename(path)}: " + "; ".join(problems))
    d.setdefault("body", "kart")  # (CHANGE 173: a kart saved before the sports cars)
    return d


def load_karts(folder=None):
    folder = folder or os.path.join(MODS, "karts")
    if not os.path.isdir(folder):
        return {}
    return {os.path.splitext(f)[0]: load_kart(os.path.join(folder, f))
            for f in sorted(os.listdir(folder)) if f.endswith(".py") and not f.startswith("_")}


def load_track():
    """mods/track.py: which track is raced, how many laps, what it is called and how the computer karts drive."""
    path = os.path.join(MODS, "track.py")
    if not os.path.exists(path):
        return {"track": "club", "laps": 3, "name": kart_track.TRACKS["club"]["name"], "cpu_level": "medium"}
    t = read_dict(path, "TRACK")
    if not isinstance(t, dict):
        raise ModError("track.py: TRACK must be a dictionary")
    track = t.get("track", "club")
    if track not in kart_track.TRACKS:
        raise ModError(f"track.py: track must be one of {', '.join(kart_track.TRACKS)}")
    laps = t.get("laps", 3)
    if not isinstance(laps, int) or isinstance(laps, bool) or not 1 <= laps <= 9:
        raise ModError("track.py: laps must be a whole number from 1 to 9")
    level = t.get("cpu_level", "medium")
    if level not in ("easy", "medium", "expert"):
        raise ModError("track.py: cpu_level must be easy, medium or expert")
    name = t.get("name", kart_track.TRACKS[track]["name"])
    if not isinstance(name, str):
        raise ModError("track.py: name must be text")
    return {"track": track, "laps": laps, "name": name[:16], "cpu_level": level}


def load_rules():
    path = os.path.join(MODS, "rules.py")
    rules = dict(sim.DEFAULT_RULES)
    if not os.path.exists(path):
        return rules
    r = read_dict(path, "RULES")
    if not isinstance(r, dict):
        raise ModError("rules.py: RULES must be a dictionary")
    for k, v in r.items():
        if k not in RULE_LIMITS:
            raise ModError(f"rules.py: unknown rule '{k}'")
        lo, hi = RULE_LIMITS[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            raise ModError(f"rules.py: {k} must be a number from {lo} to {hi}")
        rules[k] = v
    return rules


def load_all():
    """Everything, checked. Also switches the game over to the mod rules."""
    rules = load_rules()
    sim.RULES.clear()
    sim.RULES.update(rules)
    return load_karts(), load_track(), rules


def test_race(seconds=30):
    """A quick headless race with the mods, to show a change works (and doesn't break anything)."""
    import cpu_brains
    from engine import wire
    karts, track_mod, rules = load_all()
    track = kart_track.load(track_mod["track"])
    race = sim.Race(track, wire.Schema("kart", sim.SCHEMA_FIELDS), track_mod["laps"])
    designs = list(karts.values())[:4] or [sim.default_design("Test", (200, 60, 60))]
    for i, d in enumerate(designs):
        race.add(i, d)
    race.add(len(designs), sim.default_design("Racer", (60, 130, 230)))
    race.start()
    for _ in range(int(seconds * 60)):
        race.step_all({kid: cpu_brains.drive(track_mod["cpu_level"], k, race) for kid, k in race.karts.items()})
    return {"seconds": seconds, "track": track_mod["track"], "places": [race.designs[k]["name"] for k in race.places()],
            "laps": {race.designs[k]["name"]: race.karts[k]["lap"] for k in race.karts},
            "bumps": sum(race.hits.values()) // 2}


if __name__ == "__main__":
    try:
        karts, track_mod, rules = load_all()
        print("Mods OK:", ", ".join(karts) or "no karts yet", "| track:", track_mod["track"], "| rules:", rules)
        print("Test race:", test_race())
    except ModError as e:
        raise SystemExit(f"MOD PROBLEM: {e}")
