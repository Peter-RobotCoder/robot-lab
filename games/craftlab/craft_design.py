"""A learner's design in Craft Lab (CHANGE 200): their Craft Bot, the robot helper their code drives. The engine's
shape (as every game's): a name (a string), a colour (a list, [red, green, blue]: the Bot's paint and your own
shirt) and points (integers) shared between what the Bot is good at:

    dig     how fast it digs (a Bot with 10 digs as slowly as your hand; 60, faster than an iron pick)
    build   how fast it puts blocks down
    speed   how fast it moves from block to block

100 points to share, 10 to 60 each (the teacher can change both: the Limits tab). The garage (press I) and the code
panel (press C) change them, as in every game; a design file in mods/bots/<name>.py keeps an approved AI change.
"""
POINTS_TOTAL, STAT_MIN, STAT_MAX = 100, 10, 60
STATS = ("dig", "build", "speed")
SETTINGS = {}
FULL_STAT, FULL_POINTS_TOTAL = (STAT_MIN, STAT_MAX), POINTS_TOTAL
STAT_NOTES = {"dig": "points for how fast your Craft Bot digs", "build": "points for how fast it puts blocks down",
              "speed": "points for how fast it moves from block to block"}
NAME_MAX = 12
LIMITS = None
USER_MODS = {}  # (AI-made switchable mods for the teacher's Controls: none yet)


def default_design(name="Bot", colour=(60, 130, 230)):
    return {"name": name, "colour": list(colour), "points": {"dig": 34, "build": 33, "speed": 33}, "settings": {}}


def schema():
    """The design as variables, in the HUD's groups (the garage and the code panel)."""
    from engine.schema import Var
    return ([Var(k, ("points", k), "int", "points", tool=k, note=STAT_NOTES[k]) for k in STATS] +
            [Var("bot_name", ("name",), "str", "strings", tool="name_and_colour",
                 note="a string: text made of chars", max_len=NAME_MAX),
             Var("colour", ("colour",), "rgb", "lists", tool="name_and_colour", note="red, green, blue: 0 to 255")])


design_schema = schema


def _limits():
    global LIMITS
    if LIMITS is None:
        from engine.limits import Spec
        LIMITS = Spec(SETTINGS, {}, STATS, (STAT_MIN, STAT_MAX), FULL_STAT, POINTS_TOTAL, FULL_POINTS_TOTAL)
    return LIMITS


def default_limits():
    return _limits().default()


def code_limits(limits):
    return _limits().code_room(limits)


def full_limits():
    return _limits().full()


def clean_limits(new, old=None):
    return _limits().clean(new, old)


def check_design(d, limits=None):
    """Problems with a design (empty = fine), held to the learners' limits (or full_limits() for the teacher's)."""
    if not isinstance(d, dict):
        return ["the design must be a dictionary"]
    problems = []
    if not isinstance(d.get("name"), str) or not d["name"].strip():
        problems.append("name must be some text")
    elif len(d["name"]) > NAME_MAX:
        problems.append(f"name can be at most {NAME_MAX} characters")
    c = d.get("colour")
    if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 255
                                                         for v in c)):
        problems.append("colour must be three whole numbers from 0 to 255, [red, green, blue]")
    limits = limits or default_limits()
    pts = d.get("points") if isinstance(d.get("points"), dict) else {}
    for k in STATS:
        lo, hi = limits["points"][k]
        v = pts.get(k)
        if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
            problems.append(f"{k} must be a whole number from {lo} to {hi}")
    vals = [pts.get(k) for k in STATS]
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vals) and sum(vals) > limits["points_total"]:
        problems.append(f"{sum(vals)} points used: the most you can spend is {limits['points_total']}")
    return problems


def fit_design(d, limits=None):
    """A design inside the rules (each point 10 to 60, 100 in all, a real colour and name)."""
    out = {"name": str(d.get("name", "Bot"))[:NAME_MAX] or "Bot", "settings": {}}
    c = d.get("colour") or [60, 130, 230]
    out["colour"] = [max(0, min(255, int(v))) for v in list(c)[:3]] if len(list(c)) >= 3 else [60, 130, 230]
    pts = d.get("points") if isinstance(d.get("points"), dict) else {k: d.get(k, 33) for k in STATS}
    if limits is not None:
        fitted = _limits().fit({"points": {k: pts.get(k, 33) for k in STATS}, "settings": {}}, limits)
        out["points"] = {k: int(fitted["points"][k]) for k in STATS}
        return out
    vals = []
    for k in STATS:
        try:
            vals.append(max(STAT_MIN, min(STAT_MAX, int(pts.get(k, 33)))))
        except (TypeError, ValueError):
            vals.append(33)
    over = sum(vals) - POINTS_TOTAL
    i = 0
    while over != 0 and i < 300:
        k = i % 3
        if over > 0 and vals[k] > STAT_MIN:
            vals[k] -= 1
            over -= 1
        elif over < 0 and vals[k] < STAT_MAX:
            vals[k] += 1
            over += 1
        i += 1
    out["points"] = dict(zip(STATS, vals))
    return out


def stats_of(design):
    """What the points buy the Bot: seconds a dig takes (times the block's hardness), seconds a placement takes,
    seconds a move takes."""
    pts = design.get("points", design)
    dig, build, speed = (pts.get(k, 33) for k in STATS)
    return {"dig": 1.6 - dig * 0.022, "build": 0.9 - build * 0.012, "move": 0.75 - speed * 0.01}
