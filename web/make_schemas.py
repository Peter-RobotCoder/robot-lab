"""schemas.json for Club Coders Live: each game's design schema (the variables the code panel writes and reads back,
and the garage's tables draw), its limits (the ranges a design is held to) and the game constants the schema's own
rules, the garage (its colour blocks: engine/hud.py, fight_client.py) and its stats readout use, from the games' own
files (lab_sim.py, fight_sim.py, kart_sim.py), so the page's code panel (schema.js) writes and reads the code
exactly as the app does.

Why a copy: the class servers send the rules (the weapons, specials, bodies...) and the limits, but not the schema
itself. A variable's rules are Python functions (the weapons a robot may choose, what a new body brings with it),
so the copy names each one and schema.js holds the same function under that name. A function this file doesn't
know stops it (a new rule needs its JavaScript too), and each function's source is fingerprinted, so a changed rule
makes --check fail until schema.js has been looked at again.

    python make_schemas.py            write schemas.json beside this file (run after a game's schema changes)
    python make_schemas.py --check    exit 1 if schemas.json isn't what the games' files say (schema_test.py checks it)

Run it with the games' Python (shared-world-demo/.venv): Robot Lab's simulation needs Panda3D's physics.
"""
import hashlib
import importlib
import inspect
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "schemas.json")
# each game: its simulation module, its folder in the working folder, and the word its code's title uses
GAMES = {"robotlab": ("Robot Lab", "lab_sim", "shared-world-demo", "ROBOT"),
         "fightlab": ("Fight Lab", "fight_sim", "BeatEmUp", "FIGHTER"),
         "kartlab": ("Kart Lab", "kart_sim", "kart", "KART")}
# the old code's one-variable name (a design written as one dictionary): the app refuses it with "press RESET CODE"
OLD_NAMES = {"robotlab": "ROBOT", "fightlab": "FIGHTER", "kartlab": None}
# CHANGE 124: the code may set up to twice the teacher's limit (sim.code_limits). Robot Lab's and Fight Lab's
# windows check the code against that room; Kart Lab's window checks it against the teacher's limits as they are
# (kart_client.outside_limits), and its server gives the room.
CLIENT_CODE_ROOM = {"robotlab": True, "fightlab": True, "kartlab": False}

# Every function a variable carries, by game, variable and attribute: the name schema.js knows it by.
FUNCTIONS = {
    ("robotlab", "weapon", "options"): "lab_weapon_options",
    ("robotlab", "weapon", "valid"): "lab_weapon_valid",
    ("robotlab", "weapon", "after"): "nothing",
    ("robotlab", "weapon", "describe"): "lab_weapon_text",
    ("robotlab", "weapon", "allowed_values"): "lab_weapons_allowed",
    ("robotlab", "model", "options"): "house_names",
    ("robotlab", "model", "after"): "lab_model_changed",
    ("fightlab", "body", "options"): "body_names",
    ("fightlab", "body", "after"): "fight_body_changed",
    ("fightlab", "body", "extra"): "look_section",
    ("fightlab", "model", "options"): "boss_names",
    ("fightlab", "model", "after"): "fight_model_changed",
    ("fightlab", "special", "options"): "mission_specials",
    ("fightlab", "special", "valid"): "all_specials",
    ("fightlab", "special", "after"): "fight_special_changed",
    ("fightlab", "special", "fixed"): "has_model",
    ("fightlab", "special", "describe"): "fight_special_text",
    ("fightlab", "special", "allowed_values"): "fight_specials_allowed",
    ("fightlab", "fighting_style", "options"): "style_names",
    ("fightlab", "fighting_style", "after"): "fight_style_changed",
    ("fightlab", "fighting_style", "describe"): "fight_style_text",
    ("fightlab", "weapon", "options"): "style_weapons",
    ("fightlab", "weapon", "after"): "fight_style_changed",
    ("fightlab", "weapon", "unless"): "has_model_or_unarmed",
    ("fightlab", "combo", "options"): "combo_move_names",
    ("fightlab", "combo", "extra"): "combo_section",
}
# unless=: every points row in Robot Lab, and most rows in Fight Lab, hide behind the same rule (a Resident Robot
# or a boss: its own stats)
UNLESS = {"robotlab": "has_model", "fightlab": "has_model"}
FUNCTION_ATTRS = ("options", "valid", "after", "fixed", "describe", "extra", "unless", "allowed_values")
PLAIN_ATTRS = ("name", "kind", "group", "garage", "tool", "note", "list_name", "list_note", "max_len", "optional",
               "none_text", "per_row", "step", "always")


def game_folder(game):
    _, module, dev, _ = GAMES[game]
    for folder in (os.path.join(os.path.dirname(HERE), "games", game),
                   os.path.join(os.path.dirname(os.path.dirname(HERE)), dev)):
        if os.path.exists(os.path.join(folder, module + ".py")):
            return folder
    return None


def load(game):
    folder = game_folder(game)
    if folder is None:
        return None
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return importlib.import_module(GAMES[game][1])


def fingerprint(fn):
    """A short fingerprint of a function's source (a lambda's: the lines it is written on)."""
    try:
        text = inspect.getsource(fn)
    except (OSError, TypeError):
        text = fn.__code__.co_code.hex()
    return hashlib.sha1("\n".join(line.strip() for line in text.strip().split("\n")).encode()).hexdigest()[:10]


def variable(game, var):
    out = {k: getattr(var, k) for k in PLAIN_ATTRS}
    out["path"] = list(var.path)
    for attr in FUNCTION_ATTRS:
        fn = getattr(var, attr)
        if fn is None:
            continue
        name = FUNCTIONS.get((game, var.name, attr))
        if name is None and attr == "unless":
            name = UNLESS.get(game)
        if name is None:
            raise SystemExit(f"{game}: {var.name}.{attr} is a function schema.js doesn't know: add it to "
                             f"make_schemas.FUNCTIONS and to schema.js")
        out[attr] = name
        out.setdefault("fingerprints", {})[attr] = fingerprint(fn)
    return out


def limits_spec(sim):
    spec = sim._limits()
    return {"settings": {k: list(v) for k, v in spec.settings.items()},
            "full_settings": {k: list(v) for k, v in spec.full_settings.items()},
            "stats": list(spec.stats), "stat_range": list(spec.stat_range), "full_stat": list(spec.full_stat),
            "points_total": spec.points_total, "full_points_total": spec.full_points_total}


def literals(path, names):
    """Module-level constants read out of a file without running it (a window's file starts a window)."""
    import ast
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in names:
                out[node.targets[0].id] = ast.literal_eval(node.value)
    missing = set(names) - set(out)
    if missing:
        raise SystemExit(f"{path}: no {', '.join(sorted(missing))}")
    return out


def engine_file(name):
    import engine
    return os.path.join(os.path.dirname(engine.__file__), name)


def constants(game, sim):
    """What the schema's functions, the game's design check, the garage (its colour blocks) and the garage's stats
    readout read from the game itself (not the ctx)."""
    swatches = [list(c) for c in literals(engine_file("hud.py"), ["SWATCHES"])["SWATCHES"]]
    if game == "robotlab":
        return {"weapons": list(sim.WEAPONS), "house_weapons": list(sim.HOUSE_WEAPONS),
                "house": {name: w for name, w, _, _ in sim.HOUSE_ROBOTS}, "settings_default": {
                    k: v[2] for k, v in sim.SETTINGS.items()}, "swatches": swatches,
                "standard_mass": sim.STANDARD_MASS, "push_grip": sim.PUSH_GRIP, "stat_max": sim.STAT_MAX}
    if game == "fightlab":
        client = literals(os.path.join(game_folder(game), "fight_client.py"),
                          ["HAIR_SWATCHES", "TRIM_SWATCHES", "LIGHT_SWATCHES"])
        return {"swatches": swatches, **{k.lower(): [list(c) for c in v] for k, v in client.items()},
                "style_moves": {s: {m: list(v) for m, v in moves.items()} for s, moves in sim.STYLE_MOVES.items()},
                "weapon_mods": {w: list(v[2:5]) for w, v in sim.WEAPONS.items()}, "weapon_moves": list(sim.WEAPON_MOVES),
                "style_movement": sim.STYLE_MOVEMENT, "punch_startup": sim.MOVES["punch"].startup,
                "gravity": sim.DEFAULT_RULES["gravity"], "boss_stats": sim.BOSS_STATS,
                "bodies": list(sim.BODIES), "model_bodies": list(sim.MODEL_BODIES),
                "human_bodies": list(sim.HUMAN_BODIES), "robin_style": sim.ROBIN_STYLE,
                "hair_styles": sim.HAIR_STYLES, "outfits": list(sim.OUTFITS), "shapes": list(sim.SHAPES),
                "wins": list(sim.WINS), "height": [sim.HEIGHT_MIN, sim.HEIGHT_MAX],
                "default_look": {b: sim.default_look(b) for b in sim.BODIES},
                "styles": list(sim.STYLES), "weapons": {w: v[0] for w, v in sim.WEAPONS.items()},
                "specials": list(sim.SPECIALS), "combo_moves": list(sim.COMBO_MOVES),
                "combo_min": sim.COMBO_MIN, "combo_max": sim.COMBO_MAX,
                "bosses": {name: v[1] for name, v in sim.BOSS_BY_NAME.items()}}
    return {"name_max": 12, "swatches": swatches}


def build():
    out = {}
    for game, (title, module, _, word) in GAMES.items():
        sim = load(game)
        if sim is None:
            continue
        out[game] = {"title": title, "word": word, "old_name": OLD_NAMES[game],
                     "client_code_room": CLIENT_CODE_ROOM[game],
                     "vars": [variable(game, v) for v in sim.schema()],
                     "limits": limits_spec(sim), "consts": constants(game, sim)}
    return out


def text(data):
    # (not sorted: the order of a game's variables and of each list of choices is the order the app shows them)
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main():
    made = text(build())
    if "--check" in sys.argv:
        try:
            with open(OUT, encoding="utf-8") as f:
                same = f.read() == made
        except OSError:
            same = False
        print("schemas.json is up to date" if same else "schemas.json is out of date: run make_schemas.py "
              "(and check schema.js still does what each changed function does)")
        return 0 if same else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(made)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
