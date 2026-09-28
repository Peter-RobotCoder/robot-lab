"""Load and check the mods: robots (mods/robots/*.py), the arena (mods/arena.py) and the rules (mods/rules.py).

Mods are plain data (a dictionary in each file). They are read with ast.literal_eval, so nothing in them
runs as code. Every value is checked against sensible limits before the game uses it.

    python rw_mods.py          check the mods and run a quick test fight (used after every AI change)
"""
import ast
import os

import lab_sim as sim

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(HERE, "mods")

RULE_LIMITS = {
    "match_seconds": (30, 600), "damage_multiplier": (0.1, 5.0), "spinner_energy_share": (0.1, 0.9),
    "max_launch_speed": (2.0, 12.0), "flip_power": (0.2, 3.0), "gravity": (2.0, 20.0),
    "hazard_damage": (0.0, 5.0), "floor_flipper_every": (1.5, 20.0), "saw_cycle": (2.0, 30.0),
    "saw_up_seconds": (0.5, 10.0), "spike_cycle": (1.5, 20.0),
}
HAZARDS = ("pit", "floor_flipper", "saws", "spikes", "house_robots")


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
    return isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c)


def load_robot(path):
    d = read_dict(path, "ROBOT")
    problems = sim.check_design(d)
    if not colour_ok(d.get("colour")):
        problems.append("colour must be three whole numbers from 0 to 255")
    for key in ("trim", "lights"):
        if key in d.get("style", {}) and not colour_ok(d["style"][key]):
            problems.append(f"style {key} must be three whole numbers from 0 to 255")
    if problems:
        raise ModError(f"{os.path.basename(path)}: " + "; ".join(problems))
    return d


def load_robots():
    folder = os.path.join(MODS, "robots")
    return {os.path.splitext(f)[0]: load_robot(os.path.join(folder, f))
            for f in sorted(os.listdir(folder)) if f.endswith(".py") and not f.startswith("_")}


def load_arena():
    a = read_dict(os.path.join(MODS, "arena.py"), "ARENA")
    hz = a.get("hazards", {})
    houses = hz.get("house_robots", False)
    if isinstance(houses, list) and not all(n in sim.HOUSE_BY_NAME for n in houses):
        raise ModError(f"arena.py: house_robots can be True, False or a list from {', '.join(sim.HOUSE_BY_NAME)}")
    if not set(hz) <= set(HAZARDS) or not all(isinstance(v, bool) for k, v in hz.items() if k != "house_robots"):
        raise ModError(f"arena.py: hazards must be True/False for each of {', '.join(HAZARDS)}")
    hz = {k: hz.get(k, False) for k in HAZARDS}  # any left out are switched off
    look = a.get("look", {})
    if "wall_colour" in look and not colour_ok(look["wall_colour"]):
        raise ModError("arena.py: wall_colour must be three whole numbers from 0 to 255")
    look["name"] = str(look.get("name", "ROBOT LAB"))[:16]
    return {"hazards": hz, "look": look}


def load_rules():
    r = read_dict(os.path.join(MODS, "rules.py"), "RULES")
    rules = dict(sim.DEFAULT_RULES)
    for k, v in r.items():
        if k not in RULE_LIMITS:
            raise ModError(f"rules.py: unknown rule '{k}'")
        lo, hi = RULE_LIMITS[k]
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            raise ModError(f"rules.py: {k} must be a number from {lo} to {hi}")
        rules[k] = v
    if rules["saw_up_seconds"] >= rules["saw_cycle"]:
        raise ModError("rules.py: saw_up_seconds must be less than saw_cycle")
    return rules


def load_all():
    """Everything, checked. Also switches the physics over to the mod rules."""
    rules = load_rules()
    sim.RULES.clear()
    sim.RULES.update(rules)
    return load_robots(), load_arena(), rules


def test_fight(seconds=30):
    """A quick headless fight with the mods, to show a change works (and doesn't break anything)."""
    robots, arena_mod, rules = load_all()
    a = sim.Arena(hazards=arena_mod["hazards"])
    for d in list(robots.values())[:2]:
        a.add_robot(d)
    for _ in range(int(seconds * 60)):
        a.step()
    kinds = {}
    for _, _, kind in a.impacts:
        kinds[kind] = kinds.get(kind, 0) + 1
    fighters = [r for r in a.robots if not r.house]
    return {"seconds": seconds, "hits": kinds, "knocked_out": [r.name for r in fighters if r.knocked_out],
            "armour_left": {r.name: round(max(0, r.health)) for r in fighters}}


if __name__ == "__main__":
    try:
        robots, arena_mod, rules = load_all()
        print("Mods OK:", ", ".join(robots), "| hazards:", ", ".join(k for k, v in arena_mod["hazards"].items() if v))
        print("Test fight:", test_fight())
    except ModError as e:
        raise SystemExit(f"MOD PROBLEM: {e}")
