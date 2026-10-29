"""lessons.json for Club Coders Live: each game's lesson titles, aims, learning outcomes and missions, from the
games' own lesson files (lab_missions.py, fight_missions.py, kart_missions.py, city_missions.py, craft_missions.py), so the page's printed session
records name what the app's PDFs name (records.py reads the same files).

    python make_lessons.py            write lessons.json beside this file (run after a lesson file changes)
    python make_lessons.py --check    exit 1 if lessons.json isn't what the lesson files say (web_test.py checks it)
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lessons.json")
# each game: its lesson file, and its folder in the public repository (games/<game>) or the working folder
GAMES = {"robotlab": ("Robot Lab", "lab_missions", "shared-world-demo"),
         "fightlab": ("Fight Lab", "fight_missions", "BeatEmUp"),
         "kartlab": ("Kart Lab", "kart_missions", "kart"),
         "citylab": ("City Lab", "city_missions", "city"),  # (CHANGE 201: City Lab on the page)
         "craftlab": ("Craft Lab", "craft_missions", "craft")}  # (CHANGE 202: Craft Lab on the page)
SIMS = {"robotlab": "lab_sim", "fightlab": "fight_sim", "kartlab": "kart_sim", "citylab": "city_sim", "craftlab": "craft_design"}  # (each game's USER_MODS: their titles)


def lesson_file(game):
    _, module, dev = GAMES[game]
    for folder in (os.path.join(os.path.dirname(HERE), "games", game), os.path.join(os.path.dirname(os.path.dirname(HERE)), dev)):
        path = os.path.join(folder, module + ".py")
        if os.path.exists(path):
            return path
    return None


def load(path, name):
    spec = importlib.util.spec_from_file_location(f"_lessons_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # (plain data: the lesson files import only ast and re)
    return module


def user_mods(game):
    """The game's user mods' titles and descriptions (USER_MODS in its sim file), read as data without running the
    file (it needs the game's physics): the windows show these, and the class server sends only the switches."""
    path = lesson_file(game)
    if path is None:
        return {}
    path = os.path.join(os.path.dirname(path), SIMS[game] + ".py")
    if not os.path.exists(path):
        return {}
    import ast
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "USER_MODS" for t in node.targets):
            try:
                return {k: list(v) for k, v in ast.literal_eval(node.value).items()}
            except ValueError:
                return {}
    return {}


def build():
    out = {}
    for game, (title, module, _) in GAMES.items():
        path = lesson_file(game)
        if path is None:
            continue
        lm = load(path, module)
        out[game] = {
            "title": title,
            "lessons": {str(n): lesson.get("title", f"Lesson {n}") for n, lesson in sorted(lm.LESSONS.items())},
            "tasks": {str(n): task for n, task in sorted(getattr(lm, "LESSON_TASKS", {}).items())},
            "outcomes": {code: [o[0], o[1]] for code, o in lm.OUTCOMES.items()},
            "missions": {mid: [m[0], m[1], list(m[3])] for mid, m in lm.MISSIONS.items()},
            "user_mods": user_mods(game),
        }
    return out


def text(data):
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main():
    made = text(build())
    if "--check" in sys.argv:
        try:
            with open(OUT, encoding="utf-8") as f:
                same = f.read() == made
        except OSError:
            same = False
        print("lessons.json is up to date" if same else "lessons.json is out of date: run make_lessons.py")
        return 0 if same else 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(made)
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
