"""Load and check the mods: drivers (mods/drivers/*.py), the city choice (mods/city.py) and the rules (mods/rules.py).

Mods are plain data (a dictionary in each file). They are read with ast.literal_eval, so nothing in them
runs as code. Every value is checked against sensible limits before the game uses it.

    python city_mods.py          check the mods and run the city for a while (used after every AI change)
"""
import ast
import os

import city_version  # noqa: F401  (puts the engine and the other games on the path)
import city_map
import city_sim as sim

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(HERE, "mods")

RULE_LIMITS = {
    "traffic": (0, 30), "robots": (0, 20), "parked": (0, 40), "delivery_pay": (0, 500), "taxi_fare": (0, 500),
    "race_pay": (0, 1000), "roundup_pay": (0, 200), "chip_pay": (0, 100), "bump_distance": (1.0, 3.5),
    "bump_slowdown": (0.0, 1.0), "bump_transfer": (0.0, 1.0),
}
LEVELS = ("easy", "medium", "expert")


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


def check_driver(d):
    """Problems with a design (empty = fine): the widest ranges, as a mod file is the teacher's business."""
    if not isinstance(d, dict):
        return ["DRIVER must be a dictionary"]
    return sim.check_design(d, sim.full_limits())


def load_driver(path):
    d = read_dict(path, "DRIVER")
    problems = check_driver(d)
    if problems:
        raise ModError(f"{os.path.basename(path)}: " + "; ".join(problems))
    d.setdefault("settings", {})
    return d


def load_drivers(folder=None):
    folder = folder or os.path.join(MODS, "drivers")
    if not os.path.isdir(folder):
        return {}
    return {os.path.splitext(f)[0]: load_driver(os.path.join(folder, f))
            for f in sorted(os.listdir(folder)) if f.endswith(".py") and not f.startswith("_")}


def whole(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def load_city():
    """mods/city.py: which city, how many of the computer's cars and robots, and how the street racers drive."""
    path = os.path.join(MODS, "city.py")
    out = {"city": city_map.DEFAULT_CITY, "traffic": sim.DEFAULT_RULES["traffic"],
           "robots": sim.DEFAULT_RULES["robots"], "cpu_level": "medium"}
    if not os.path.exists(path):
        return out
    t = read_dict(path, "CITY")
    if not isinstance(t, dict):
        raise ModError("city.py: CITY must be a dictionary")
    for k in t:
        if k not in out:
            raise ModError(f"city.py: unknown setting '{k}' (city, traffic, robots, cpu_level)")
    city = t.get("city", out["city"])
    if city not in city_map.CITIES:
        raise ModError(f"city.py: city must be one of {', '.join(city_map.CITIES)}")
    for k, hi in (("traffic", 30), ("robots", 20)):
        if not whole(t.get(k, out[k]), 0, hi):
            raise ModError(f"city.py: {k} must be a whole number from 0 to {hi}")
    if t.get("cpu_level", "medium") not in LEVELS:
        raise ModError("city.py: cpu_level must be easy, medium or expert")
    out.update(t)
    return out


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
    return load_drivers(), load_city(), rules


def test_city(seconds=20):
    """A quick headless run of the city with the mods, to show a change works (and doesn't break anything)."""
    import city_jobs
    import cpu_brains
    from engine import wire
    drivers, city_mod, rules = load_all()
    city = city_map.load(city_mod["city"])
    w = sim.World(city, wire.Schema("city", sim.SCHEMA_FIELDS))
    w.jobs = city_jobs.Jobs(city, sim.RULES, {k: True for k in ("delivery", "taxi", "race", "roundup")}, seed=1)
    designs = list(drivers.values())[:4] or [sim.default_design("Test", (200, 60, 60))]
    for i, d in enumerate(designs):
        w.add_person(i, d)
    traffic = {w.add_traffic(k)["id"]: {} for k in range(min(6, city_mod["traffic"]))}
    robots = {w.add_patrol(k)["id"]: {} for k in range(min(6, city_mod["robots"]))}
    for _ in range(int(seconds * 60)):
        inputs = {cid: cpu_brains.drive_car(cid, w.cars[cid], w, mem, 0.5) for cid, mem in traffic.items()}
        inputs.update({rid: cpu_brains.drive_robot(rid, w.robots[rid], w, mem) for rid, mem in robots.items()})
        w.step_all(inputs)
    return {"seconds": seconds, "city": city.key, "people": [w.designs[p]["name"] for p in w.people],
            "traffic": len(traffic), "robots": len(robots), "bumps": sum(w.hits.values())}


if __name__ == "__main__":
    try:
        drivers, city_mod, rules = load_all()
        print("Mods OK:", ", ".join(drivers) or "no drivers yet", "| city:", city_mod, "| rules:", rules)
        print("Test run:", test_city())
    except ModError as e:
        raise SystemExit(f"MOD PROBLEM: {e}")
