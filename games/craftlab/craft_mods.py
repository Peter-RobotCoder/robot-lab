"""Craft Lab's mods (CHANGE 200): plain-data files a learner (or an approved AI change) writes, checked before use.

    mods/bots/<name>.py   BOT = {...}        a learner's Craft Bot design (name, colour, points)
    mods/blocks.py        BLOCKS = [...]     new blocks: key, name, colour, hard, light, tool
    mods/recipes.py       RECIPES = [...]    new recipes, as craft_items.RECIPES writes them
    mods/world.py         WORLD = {...}      the seed, the size, the mode, the creatures, the length of a day
    mods/rules.py         RULES = {...}      keep your things when knocked out, blasts, hunger, falls hurt

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
RULE_LIMITS = {"keep_items": bool, "blasts": bool, "hunger": bool, "falls_hurt": bool}
WORLD_LIMITS = {"seed": (0, 999_999_999), "size": ("small", "medium", "large"), "mode": ("survival", "creative"),
                "mobs": bool, "day_length": (120, 3600)}
TOOLS = ("pick", "axe", "shovel", None)


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
    if not (isinstance(light, int) and 0 <= light <= 15):
        out.append("light must be a whole number from 0 to 15")
    if b.get("tool") not in TOOLS:
        out.append("tool must be pick, axe, shovel or None")
    return out


def check_recipe(r):
    if not isinstance(r, dict):
        return ["each recipe must be a dictionary"]
    out = []
    if r.get("makes") not in B.ITEM_ID:
        out.append(f"makes must be the name of a block or item (not {r.get('makes')!r})")
    n = r.get("count", 1)
    if not (isinstance(n, int) and 1 <= n <= 64):
        out.append("count must be a whole number from 1 to 64")
    if "pattern" in r:
        p = r["pattern"]
        if not (isinstance(p, list) and 1 <= len(p) <= 3 and all(isinstance(line, str) and 1 <= len(line) <= 3 for line in p)):
            out.append("pattern must be a list of 1 to 3 strings, each 1 to 3 letters (. for an empty place)")
        else:
            key = r.get("key") if isinstance(r.get("key"), dict) else {}
            for ch in set("".join(p)) - {".", " "}:
                what = key.get(ch)
                names = what if isinstance(what, list) else [what]
                if what is None or any(n not in B.ITEM_ID for n in names):
                    out.append(f"key must say what {ch!r} is (the name of a block or item)")
    elif "takes" in r:
        t = r["takes"]
        if not (isinstance(t, list) and 1 <= len(t) <= 9 and all(x in B.ITEM_ID for x in t)):
            out.append("takes must be a list of 1 to 9 names of blocks or items")
    else:
        out.append("a recipe needs a pattern (and a key) or a takes list")
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


def load_recipes():
    path = os.path.join(MODS, "recipes.py")
    if not os.path.exists(path):
        return []
    recipes = read_value(path, "RECIPES")
    if not isinstance(recipes, list):
        raise ModError("recipes.py: RECIPES must be a list")
    for r in recipes:
        problems = check_recipe(r)
        if problems:
            raise ModError(f"recipes.py, {r.get('makes') if isinstance(r, dict) else r!r}: " + "; ".join(problems))
    return recipes


def load_world():
    path = os.path.join(MODS, "world.py")
    out = {"seed": 2026, "size": "medium", "mode": "survival", "mobs": True, "day_length": 1200}
    if not os.path.exists(path):
        return out
    w = read_value(path, "WORLD")
    if not isinstance(w, dict):
        raise ModError("world.py: WORLD must be a dictionary")
    for k, v in w.items():
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
    for k, v in r.items():
        if k not in RULE_LIMITS:
            raise ModError(f"rules.py: {k} isn't a rule ({', '.join(RULE_LIMITS)})")
        if not isinstance(v, bool):
            raise ModError(f"rules.py: {k} must be True or False")
    return r


def use_mods():
    """The learners' blocks and recipes into the game (each block a new id and a plain tile in its colour). Returns
    a list of messages (empty if all went in)."""
    out = []
    try:
        for b in load_blocks():
            if b["key"] not in B.ID:
                B.add_block(b)
    except ModError as e:
        out.append(str(e))
    try:
        items.recipes_changed(items.RECIPES + load_recipes())
    except ModError as e:
        out.append(str(e))
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
