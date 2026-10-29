"""Craft Lab's mods (CHANGE 200): plain-data files a learner (or an approved AI change) writes, checked before use.

    mods/bots/<name>.py   BOT = {...}        a learner's Craft Bot design (name, colour, points)
    mods/blocks.py        BLOCKS = [...]     new blocks: key, name, colour, hard, light, tool
    mods/blueprints.py    BLUEPRINTS = [...] new blueprints, as craft_items.BLUEPRINTS writes them
    mods/world.py         WORLD = {...}      the seed, the size, the mode, the creatures, the length of a day
    mods/rules.py         RULES = {...}      keep your things when knocked out, Overload Cells, Energy, falls hurt

An old mod that uses an old name (planks, pick, survival, hunger, mods/recipes.py...) still loads: the new name is
used and a warning says so (craft_blocks.ALIASES).

They are read with ast.literal_eval, so nothing in them runs as code. Every value is checked against sensible
limits before the game uses it.

    python craft_mods.py          check the mods and run the world for a while (used after every AI change)
"""
import ast
import os
import re

import craft_version  # noqa: F401  (puts the engine on the path)
import craft_blocks as B
import craft_design as design
import craft_items as items

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(HERE, "mods")
RULE_LIMITS = {"keep_items": bool, "blasts": bool, "energy": bool, "falls_hurt": bool}
WORLD_LIMITS = {"seed": (0, 999_999_999), "size": ("small", "medium", "large"), "mode": ("challenge", "sandbox"),
                "mobs": bool, "day_length": (120, 3600)}
TOOLS = ("drill", "cutter", "scoop", None)
STATIONS = ("hand", "fabricator")
WARNINGS = []       # (old names a mod used: said once by whoever loads the mods)


def warn(text):
    if text not in WARNINGS:
        WARNINGS.append(text)


class ModError(Exception):
    pass


def read_value(path, var):
    """The value assigned to `var` in a mod file, read as data only."""
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
    raise ModError(f"{os.path.basename(path)} has no {var} = ...")


read_dict = read_value


def load_bot(path):
    d = read_value(path, "BOT")
    problems = design.check_design(d, design.full_limits()) if isinstance(d, dict) else ["BOT must be a dictionary"]
    if problems:
        raise ModError(f"{os.path.basename(path)}: " + "; ".join(problems))
    d.setdefault("settings", {})
    return d


def check_block(b):
    """Problems with a learner's block (empty = fine)."""
    if not isinstance(b, dict):
        return ["each block must be a dictionary"]
    out = []
    key = b.get("key")
    if not (isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,20}", key)):
        out.append("key must be lower case letters, digits and _ (2 to 21 of them), starting with a letter")
    elif key in B.ID and not B.BLOCKS[B.ID[key]].get("mod"):
        out.append(f"there is already a block called {key}")
    if not (isinstance(b.get("name"), str) and 1 <= len(b["name"]) <= 20):
        out.append("name must be some text (up to 20 letters)")
    c = b.get("colour")
    if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c)):
        out.append("colour must be [red, green, blue], each 0 to 255")
    hard = b.get("hard", 1.0)
    if not (isinstance(hard, (int, float)) and 0.1 <= hard <= 10):
        out.append("hard must be a number of seconds from 0.1 to 10")
    light = b.get("light", 0)
    if not (isinstance(light, int) and 0 <= light <= B.LIGHT_MAX):
        out.append(f"light must be a whole number from 0 to {B.LIGHT_MAX}")
    if b.get("tool") in B.TOOL_ALIASES:
        warn(f"blocks.py: tool {b['tool']!r} is now {B.TOOL_ALIASES[b['tool']]!r}")
    elif b.get("tool") not in TOOLS:
        out.append("tool must be drill, cutter, scoop or None")
    return out


def known(name):
    """Is name a block, an item or a part group? (An old name is warned about and counts.)"""
    if name in B.ITEM_ID or name in items.GROUPS:
        return True
    if B.new_key(name) in B.ITEM_ID:
        warn(f"blueprints.py: {name!r} is now called {B.new_key(name)!r}")
        return True
    return False


def check_blueprint(r):
    """Problems with a learner's blueprint (empty = fine)."""
    if not isinstance(r, dict):
        return ["each blueprint must be a dictionary"]
    out = []
    if not (isinstance(r.get("makes"), str) and known(r["makes"]) and r["makes"] not in items.GROUPS):
        out.append(f"makes must be the name of a block or item (not {r.get('makes')!r})")
    n = r.get("count", 1)
    if not (isinstance(n, int) and 1 <= n <= B.STACK):
        out.append(f"count must be a whole number from 1 to {B.STACK}")
    parts = r.get("parts")
    if not (isinstance(parts, dict) and 1 <= len(parts) <= 6):
        out.append("parts must be a dictionary of 1 to 6 parts, each a name and how many: {\"boards\": 6}")
    else:
        for k, v in parts.items():
            if not (isinstance(k, str) and known(k)):
                out.append(f"part {k!r} isn't a block, an item or a group (any_log, any_boards, any_coal, any_fluff)")
            if not (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= B.STACK):
                out.append(f"how many {k!r} must be a whole number from 1 to {B.STACK}")
    secs = r.get("seconds", 2)
    if not (isinstance(secs, (int, float)) and not isinstance(secs, bool) and 0.5 <= secs <= 30):
        out.append("seconds must be a number from 0.5 to 30")
    if r.get("station", "fabricator") not in STATIONS:
        out.append("station must be \"hand\" or \"fabricator\"")
    return out


def load_blocks():
    path = os.path.join(MODS, "blocks.py")
    if not os.path.exists(path):
        return []
    blocks = read_value(path, "BLOCKS")
    if not isinstance(blocks, list):
        raise ModError("blocks.py: BLOCKS must be a list")
    for b in blocks:
        problems = check_block(b)
        if problems:
            raise ModError(f"blocks.py, {b.get('key') if isinstance(b, dict) else b!r}: " + "; ".join(problems))
    return blocks


def load_blueprints():
    path = os.path.join(MODS, "blueprints.py")
    if not os.path.exists(path):
        if os.path.exists(os.path.join(MODS, "recipes.py")):
            warn("mods/recipes.py isn't used any more: write blueprints in mods/blueprints.py")
        return []
    bps = read_value(path, "BLUEPRINTS")
    if not isinstance(bps, list):
        raise ModError("blueprints.py: BLUEPRINTS must be a list")
    for r in bps:
        problems = check_blueprint(r)
        if problems:
            raise ModError(f"blueprints.py, {r.get('makes') if isinstance(r, dict) else r!r}: " + "; ".join(problems))
    return bps


def load_world():
    path = os.path.join(MODS, "world.py")
    out = {"seed": 2026, "size": "medium", "mode": "challenge", "mobs": True, "day_length": 900}
    if not os.path.exists(path):
        return out
    w = read_value(path, "WORLD")
    if not isinstance(w, dict):
        raise ModError("world.py: WORLD must be a dictionary")
    for k, v in w.items():
        if k == "mode" and v in B.MODE_ALIASES:
            warn(f"world.py: the mode {v!r} is now {B.mode_of(v)!r}")
            v = B.mode_of(v)
        lim = WORLD_LIMITS.get(k)
        if lim is None:
            raise ModError(f"world.py: {k} isn't a world setting ({', '.join(WORLD_LIMITS)})")
        if lim is bool:
            if not isinstance(v, bool):
                raise ModError(f"world.py: {k} must be True or False")
        elif isinstance(lim[0], str):
            if v not in lim:
                raise ModError(f"world.py: {k} must be one of {', '.join(lim)}")
        elif not (isinstance(v, int) and lim[0] <= v <= lim[1]):
            raise ModError(f"world.py: {k} must be a whole number from {lim[0]} to {lim[1]}")
        out[k] = v
    return out


def load_rules():
    path = os.path.join(MODS, "rules.py")
    if not os.path.exists(path):
        return {}
    r = read_value(path, "RULES")
    if not isinstance(r, dict):
        raise ModError("rules.py: RULES must be a dictionary")
    out = {}
    for k, v in r.items():
        if k == "hunger":
            warn("rules.py: hunger is now called energy")
            k = "energy"
        if k not in RULE_LIMITS:
            raise ModError(f"rules.py: {k} isn't a rule ({', '.join(RULE_LIMITS)})")
        if not isinstance(v, bool):
            raise ModError(f"rules.py: {k} must be True or False")
        out[k] = v
    return out


def use_mods():
    """The learners' blocks and blueprints into the game (each block a new id and a plain tile in its colour).
    Returns a list of messages (empty if all went in; old names it met are said as warnings)."""
    out = []
    try:
        for b in load_blocks():
            if b["key"] not in B.ID:
                B.add_block(b)
    except ModError as e:
        out.append(str(e))
    try:
        items.blueprints_changed(load_blueprints())
    except ModError as e:
        out.append(str(e))
    for w in WARNINGS:  # (old names: the mod still works)
        print("Mods:", w, flush=True)
    return out


if __name__ == "__main__":
    problems = use_mods()
    try:
        load_world()
        load_rules()
    except ModError as e:
        problems.append(str(e))
    folder = os.path.join(MODS, "bots")
    for f in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if f.endswith(".py"):
            try:
                load_bot(os.path.join(folder, f))
            except ModError as e:
                problems.append(str(e))
    if problems:
        print("Mods not right:\n  " + "\n  ".join(problems))
        raise SystemExit(1)
    import craft_game
    import craft_world
    w = craft_world.World("small", 7)
    g = craft_game.Game(w)
    g.add_player(0, "Test")
    for _ in range(600):
        g.step({0: (0.5, 0.0, 0)})
    print("Mods fine: the world ran for 10 seconds.")
