"""Load and check the mods: fighters (mods/fighters/*.py), the stage (mods/stage.py) and the rules (mods/rules.py).

Mods are plain data (a dictionary in each file). They are read with ast.literal_eval, so nothing in them
runs as code. Every value is checked against sensible limits before the game uses it.

    python fight_mods.py          check the mods and run a quick test fight (used after every AI change)
"""
import ast
import os

import fight_sim as sim

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(HERE, "mods")

RULE_LIMITS = {
    "round_seconds": (20, 300), "damage_multiplier": (0.1, 5.0), "chip_damage": (0.0, 0.5),
    "combo_scaling": (0.3, 1.0), "knockback": (0.2, 3.0), "gravity": (2.0, 20.0), "special_cost": (10, 100),
    "energy_gain": (0.1, 5.0), "ring_size": (3.0, 6.5), "hazard_damage": (0.0, 5.0), "fire_jet_every": (2.0, 20.0),
}
HAZARDS = ("ring_out", "electric_ropes", "fire_jets", "slippery", "spikes")
STYLE_COLOURS = ("trim", "lights", "skin")


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


def check_fighter(d):
    """Problems with a fighter design, including how it looks (empty = fine)."""
    problems = sim.check_design(d)
    if not isinstance(d, dict):
        return problems
    if not colour_ok(d.get("colour")):
        problems.append("colour must be three whole numbers from 0 to 255")
    if not isinstance(d.get("name"), str) or not d.get("name"):
        problems.append("name must be some text")
    style = d.get("style", {})
    if not isinstance(style, dict):
        problems.append("style must be a dictionary")
    else:
        for key in STYLE_COLOURS:
            if key in style and not colour_ok(style[key]):
                problems.append(f"style {key} must be three whole numbers from 0 to 255")
        if "number" in style and (not isinstance(style["number"], str) or len(style["number"]) > 10):
            problems.append("style number must be text, up to 10 characters")
    return problems


def load_fighter(path):
    d = read_dict(path, "FIGHTER")
    problems = check_fighter(d)
    if problems:
        raise ModError(f"{os.path.basename(path)}: " + "; ".join(problems))
    return d


def load_fighters():
    folder = os.path.join(MODS, "fighters")
    return {os.path.splitext(f)[0]: load_fighter(os.path.join(folder, f))
            for f in sorted(os.listdir(folder)) if f.endswith(".py") and not f.startswith("_")}


def load_stage():
    a = read_dict(os.path.join(MODS, "stage.py"), "STAGE")
    hz = a.get("hazards", {})
    if not isinstance(hz, dict) or not set(hz) <= set(HAZARDS) or not all(isinstance(v, bool) for v in hz.values()):
        raise ModError(f"stage.py: hazards must be True/False for each of {', '.join(HAZARDS)}")
    hz = {k: hz.get(k, False) for k in HAZARDS}  # any left out are switched off
    look = a.get("look", {})
    if not isinstance(look, dict):
        raise ModError("stage.py: look must be a dictionary")
    for key in ("floor_colour", "rope_colour"):
        if key in look and not colour_ok(look[key]):
            raise ModError(f"stage.py: {key} must be three whole numbers from 0 to 255")
    look["name"] = str(look.get("name", "FIGHT LAB"))[:16]
    return {"hazards": hz, "look": look}


def load_rules():
    r = read_dict(os.path.join(MODS, "rules.py"), "RULES")
    rules = dict(sim.DEFAULT_RULES)
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
    return load_fighters(), load_stage(), rules


def test_fight(seconds=30):
    """A quick headless battle with the mods, to show a change works (and doesn't break anything)."""
    import cpu_brains
    fighters, stage_mod, rules = load_all()
    st = sim.Stage(hazards=stage_mod["hazards"], practice=False)
    ring = st.add_ring()
    for d in list(fighters.values())[:2]:
        ring.add_fighter(d, brain=cpu_brains.for_level("medium"))
    for _ in range(int(seconds * 60)):
        st.step()
    kinds = {}
    for _, _, kind in st.impacts:
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"seconds": seconds, "hits": kinds, "rounds": [f.wins for f in ring.fighters],
            "health_left": {f.name: round(max(0, f.health)) for f in ring.fighters}}


if __name__ == "__main__":
    try:
        fighters, stage_mod, rules = load_all()
        print("Mods OK:", ", ".join(fighters), "| hazards:", ", ".join(k for k, v in stage_mod["hazards"].items() if v))
        print("Test fight:", test_fight())
    except ModError as e:
        raise SystemExit(f"MOD PROBLEM: {e}")
