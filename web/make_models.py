"""models/ for Club Coders Live: the models the page draws that the app builds from numbers, so the page's ultra
tier draws the same kart and the same circuit as the app's (CHANGE 144).

- kart_ultra.json: Kart Lab's ultra kart (kart/kart_models.py: pure Python, the window builds it the same way),
  {"version", "body", "wheel", "wheels", "steering", "arms", "head", "nose", "notes"}: see kart_models.py for every field.
- kart_scenery.json: Kart Lab's ultra circuit for every built-in track (kart/kart_scenery.py, the same way): the
  road, kerbs, gravel, barriers, grass, buildings and country as parts, and the trees, tufts, tyre stacks, fans and
  posts as shapes placed by instances, {"version", "materials", "shapes", "tracks", "lights", "notes"}: see
  kart_scenery.py.
- cars.json: Kart Lab's sports cars (kart/car_models.py, CHANGE 173), drawn on every tier: {"version", "bodies": {name:
  {"body", "nose", "wheel", "wheels", "notes"}}}: see car_models.py.
- cars_ultra_<name>.json: each sports car in detail, which ultra draws near the camera (CHANGE 174): {"version",
  "name", "body", "nose", "wheel", "wheels", "brake", "notes"}.
- robot_ultra.json: Robot Lab's ultra robots (shared-world-demo/robot_models.py, CHANGE 145): every piece a robot is
  put together from, {"version", "roles", "pieces", "notes"}; where they go is robot_models.layout().
- arena_ultra.json: Robot Lab's ultra arena (shared-world-demo/arena_models.py): the floor for each set of holes, the
  cage, rig, towers, stands, screen, hall and battle scars as groups, and the fans and seats as shapes placed by
  instances, {"version", "materials", "groups", "shapes", "instances", "notes"}.
- fight_ultra.json: Fight Lab's ultra fighters (BeatEmUp/fight_models.py, CHANGE 147): every piece the built robot and
  martial artist (and the bosses) are put together from, {"version", "roles", "pieces", "notes"}; where they go is
  fight_models.layout(), on the joints the lower tiers pose.
- stage_ultra.json: Fight Lab's ultra hall (BeatEmUp/stage_models.py): a ring's pieces (placed for each ring's size by
  stage_models.ring_layout()), the floor, stands, screens, rig, walls and roof as groups, and the fans and seats as
  shapes placed by instances, {"version", "materials", "ring", "groups", "shapes", "instances", "notes"}.

    python make_models.py           write models/ beside this file (run after any of those modules changes)
    python make_models.py --check   exit 1 if models/ is out of date with them (web_test.py)

It needs nothing but Python: those modules (and the engine's model_kit, which Robot Lab's and Fight Lab's use) import
no Panda3D, and --check builds the models again and compares.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "models")
FILES = {"kart_ultra.json": "kart_models", "kart_scenery.json": "kart_scenery",  # file: the module that makes it
         "cars.json": "car_models", **{f"cars_ultra_{n}.json": "car_models" for n in ("coupe", "supercar", "rally", "muscle")},
         "robot_ultra.json": "robot_models", "arena_ultra.json": "arena_models",
         "fight_ultra.json": "fight_models", "stage_ultra.json": "stage_models"}


def kart_folder():
    """Kart Lab's folder: the public repository's games/kartlab or the working one's kart."""
    for top, kart in ((os.path.dirname(HERE), os.path.join("games", "kartlab")),
                      (os.path.dirname(os.path.dirname(HERE)), "kart")):
        if os.path.exists(os.path.join(top, kart, "kart_models.py")):
            return os.path.join(top, kart)
    return None


def lab_folder():
    """Robot Lab's folder: the public repository's games/robotlab or the working one's shared-world-demo, and the
    folder the engine package is in (CHANGE 145)."""
    for top, lab in ((os.path.dirname(HERE), os.path.join("games", "robotlab")),
                     (os.path.dirname(os.path.dirname(HERE)), "shared-world-demo")):
        if os.path.exists(os.path.join(top, lab, "robot_models.py")) and os.path.isdir(os.path.join(top, "engine")):
            return os.path.join(top, lab), top
    return None, None


def fight_folder():
    """Fight Lab's folder: the public repository's games/fightlab or the working one's BeatEmUp, and the folder the
    engine package is in (CHANGE 147)."""
    for top, game in ((os.path.dirname(HERE), os.path.join("games", "fightlab")),
                      (os.path.dirname(os.path.dirname(HERE)), "BeatEmUp")):
        if os.path.exists(os.path.join(top, game, "fight_models.py")) and os.path.isdir(os.path.join(top, "engine")):
            return os.path.join(top, game), top
    return None, None


def module(name):
    """kart_models or kart_scenery, loaded from Kart Lab's folder (kart_scenery imports kart_models and kart_track
    from beside it); robot_models or arena_models from Robot Lab's, fight_models or stage_models from Fight Lab's
    (they import the engine's model_kit)."""
    if name in ("robot_models", "arena_models", "fight_models", "stage_models"):
        folder, top = lab_folder() if name in ("robot_models", "arena_models") else fight_folder()
        if folder is None:
            raise SystemExit(f"{name}.py isn't beside the web folder (shared-world-demo/ or BeatEmUp/, games/robotlab/ "
                             "or games/fightlab/)")
        for path in (top, folder):
            if path not in sys.path:
                sys.path.insert(0, path)
        spec = importlib.util.spec_from_file_location(name, os.path.join(folder, f"{name}.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    folder = kart_folder()
    if folder is None:
        raise SystemExit("kart_models.py isn't beside the web folder (kart/ or games/kartlab/)")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(name, os.path.join(folder, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def kart_text():
    """kart_ultra.json's text as kart_models.py makes it today (one line per part: small to diff, quick to read)."""
    m = module("kart_models").kart()
    lines = ["{" + f'"version": {json.dumps(m["version"])},']
    for key in ("body", "wheel", "steering", "arms", "head", "nose"):  # (arms and head: CHANGE 157; nose: 158)
        parts = [json.dumps(p, separators=(",", ":")) for p in m[key]]
        lines.append(f'"{key}": [' + ("\n" + ",\n".join(parts) + "\n" if parts else "") + "],")
    lines.append(f'"wheels": {json.dumps(m["wheels"])},')
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


def cars_text():
    """cars.json's text as car_models.py makes it today (a line per part)."""
    m = module("car_models").cars()
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    cars = []
    for name, c in m["bodies"].items():
        lines = [f"{json.dumps(name)}: {{"]
        for key in ("body", "nose", "wheel"):
            lines.append(f'"{key}": [\n' + ",\n".join(one(p) for p in c[key]) + "],")
        lines.append(f'"wheels": {one(c["wheels"])},')
        lines.append(f'"notes": {json.dumps(c["notes"], indent=1)}' + "}")
        cars.append("\n".join(lines))
    return "{" + f'"version": {json.dumps(m["version"])},\n"bodies": {{\n' + ",\n".join(cars) + "}}\n"


def car_ultra_text(name):
    """cars_ultra_<name>.json's text as car_models.py makes it today (a line per part)."""
    c = module("car_models").car_ultra(name)
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    lines = ["{" + f'"version": {json.dumps(c["version"])}, "name": {json.dumps(name)},']
    for key in ("body", "nose", "wheel"):
        lines.append(f'"{key}": [\n' + ",\n".join(one(p) for p in c[key]) + "],")
    lines.append('"brake": {' + ", ".join(f'"{k}": [\n' + ",\n".join(one(p) for p in v) + "]" for k, v in c["brake"].items())
                 + "},")
    lines.append(f'"wheels": {one(c["wheels"])},')
    lines.append(f'"notes": {json.dumps(c["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


def scenery_text():
    """kart_scenery.json's text as kart_scenery.py makes it today (a line per material, part and shape)."""
    m = module("kart_scenery").scenery()
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    lines = ["{" + f'"version": {json.dumps(m["version"])},', '"materials": {']
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["materials"].items()))
    lines.append("},")
    lines.append('"shapes": {')
    lines.append(",\n".join(f"{json.dumps(k)}: [\n" + ",\n".join(one(p) for p in v) + "]" for k, v in m["shapes"].items()))
    lines.append("},")
    lines.append('"tracks": {')
    tracks = []
    for name, t in m["tracks"].items():
        inst = ",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in t["instances"].items())
        tracks.append(f'{json.dumps(name)}: {{"parts": [\n' + ",\n".join(one(p) for p in t["parts"]) + '],\n"instances": {\n'
                      + inst + "}}")
    lines.append(",\n".join(tracks))
    lines.append("},")
    if "lights" in m:  # (CHANGE 151: when the start lights come on)
        lines.append(f'"lights": {one(m["lights"])},')
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


def robot_text():
    """robot_ultra.json's text as robot_models.py makes it today (a line per role, piece and part)."""
    m = module("robot_models").robot()
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    lines = ["{" + f'"version": {json.dumps(m["version"])},', '"roles": {']
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["roles"].items()))
    lines.append("},")
    lines.append('"pieces": {')
    lines.append(",\n".join(f"{json.dumps(k)}: [\n" + ",\n".join(one(p) for p in v) + "]" for k, v in m["pieces"].items()))
    lines.append("},")
    if "shadow" in m:  # (CHANGE 152: what the shadow map draws of a robot)
        lines.append('"shadow": {' + f'"skip": {one(m["shadow"]["skip"])}, "pieces": {{')
        lines.append(",\n".join(f"{json.dumps(k)}: [\n" + ",\n".join(one(p) for p in v) + "]" for k, v in m["shadow"]["pieces"].items()))
        lines.append("}},")
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


def arena_text():
    """arena_ultra.json's text as arena_models.py makes it today (a line per material, part and shape)."""
    m = module("arena_models").arena()
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    lines = ["{" + f'"version": {json.dumps(m["version"])},', '"materials": {']
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["materials"].items()))
    lines.append("},")
    for key in ("groups", "shapes"):
        lines.append(f'"{key}": {{')
        lines.append(",\n".join(f"{json.dumps(k)}: [\n" + ",\n".join(one(p) for p in v) + "]" for k, v in m[key].items()))
        lines.append("},")
    lines.append('"instances": {')
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["instances"].items()))
    lines.append("},")
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


def fight_text():
    """fight_ultra.json's text as fight_models.py makes it today (a line per role, piece and part)."""
    m = module("fight_models").fighter()
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    lines = ["{" + f'"version": {json.dumps(m["version"])},', '"roles": {']
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["roles"].items()))
    lines.append("},")
    lines.append('"pieces": {')
    lines.append(",\n".join(f"{json.dumps(k)}: [\n" + ",\n".join(one(p) for p in v) + "]" for k, v in m["pieces"].items()))
    lines.append("},")
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


def stage_text():
    """stage_ultra.json's text as stage_models.py makes it today (a line per material, part and shape)."""
    m = module("stage_models").stage()
    one = lambda v: json.dumps(v, separators=(",", ":"))  # noqa: E731
    lines = ["{" + f'"version": {json.dumps(m["version"])},', '"materials": {']
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["materials"].items()))
    lines.append("},")
    for key in ("ring", "groups", "shapes"):
        lines.append(f'"{key}": {{')
        lines.append(",\n".join(f"{json.dumps(k)}: [\n" + ",\n".join(one(p) for p in v) + "]" for k, v in m[key].items()))
        lines.append("},")
    lines.append('"instances": {')
    lines.append(",\n".join(f"{json.dumps(k)}: {one(v)}" for k, v in m["instances"].items()))
    lines.append("},")
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


TEXT = {"kart_ultra.json": kart_text, "kart_scenery.json": scenery_text, "cars.json": cars_text,
        **{f"cars_ultra_{n}.json": (lambda n=n: car_ultra_text(n)) for n in ("coupe", "supercar", "rally", "muscle")}, "robot_ultra.json": robot_text,
        "arena_ultra.json": arena_text, "fight_ultra.json": fight_text, "stage_ultra.json": stage_text}


def check():
    ok = True
    for name, source in FILES.items():
        try:
            with open(os.path.join(OUT, name), encoding="utf-8") as f:
                have = f.read()
        except OSError:
            print(f"models/{name} is missing: run make_models.py")
            ok = False
            continue
        if have != TEXT[name]():
            print(f"models/{name} is out of date with {source}.py: run make_models.py")
            ok = False
    return ok


def build():
    os.makedirs(OUT, exist_ok=True)
    for name in FILES:
        text = TEXT[name]()
        data = json.loads(text)  # (it must read back)
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        if name == "kart_ultra.json":
            print(f"wrote models/{name} ({len(text) / 1e6:.2f} MB, {data['notes']['triangles']} triangles for the whole kart)")
        elif name.startswith("cars_ultra_"):
            print(f"wrote models/{name} ({len(text) / 1e6:.2f} MB, {data['notes']['triangles']} triangles)")
        elif name == "cars.json":
            tris = ", ".join(f"{k} {v['notes']['triangles']}" for k, v in data["bodies"].items())
            print(f"wrote models/{name} ({len(text) / 1e6:.2f} MB, triangles per car: {tris})")
        elif name in ("robot_ultra.json", "arena_ultra.json", "fight_ultra.json", "stage_ultra.json"):
            tris = data["notes"]["triangles"]
            print(f"wrote models/{name} ({len(text) / 1e6:.2f} MB, {len(tris)} pieces or groups, {sum(tris.values())} triangles)")
        else:
            tris = ", ".join(f"{k} {v['total']}" for k, v in data["notes"]["triangles"].items())
            print(f"wrote models/{name} ({len(text) / 1e6:.2f} MB, triangles per track: {tris})")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    build()
