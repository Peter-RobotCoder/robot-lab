"""models/ for Club Coders Live: the models the page draws that the app builds from numbers, so the page's ultra
tier draws the same kart and the same circuit as the app's (CHANGE 144).

- kart_ultra.json: Kart Lab's ultra kart (kart/kart_models.py: pure Python, the window builds it the same way),
  {"version", "body", "wheel", "wheels", "steering", "notes"}: see kart_models.py for every field.
- kart_scenery.json: Kart Lab's ultra circuit for every built-in track (kart/kart_scenery.py, the same way): the
  road, kerbs, gravel, barriers, grass, buildings and country as parts, and the trees, tufts, tyre stacks, fans and
  posts as shapes placed by instances, {"version", "materials", "shapes", "tracks", "notes"}: see kart_scenery.py.

    python make_models.py           write models/ beside this file (run after kart_models.py or kart_scenery.py changes)
    python make_models.py --check   exit 1 if models/ is out of date with them (web_test.py)

It needs nothing but Python: kart_models.py and kart_scenery.py import no Panda3D, and --check builds the models again
and compares.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "models")
FILES = {"kart_ultra.json": "kart_models", "kart_scenery.json": "kart_scenery"}  # file: the module that makes it


def kart_folder():
    """Kart Lab's folder: the public repository's games/kartlab or the working one's kart."""
    for top, kart in ((os.path.dirname(HERE), os.path.join("games", "kartlab")),
                      (os.path.dirname(os.path.dirname(HERE)), "kart")):
        if os.path.exists(os.path.join(top, kart, "kart_models.py")):
            return os.path.join(top, kart)
    return None


def module(name):
    """kart_models or kart_scenery, loaded from Kart Lab's folder (kart_scenery imports kart_models and kart_track
    from beside it)."""
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
    for key in ("body", "wheel", "steering"):
        parts = [json.dumps(p, separators=(",", ":")) for p in m[key]]
        lines.append(f'"{key}": [' + ("\n" + ",\n".join(parts) + "\n" if parts else "") + "],")
    lines.append(f'"wheels": {json.dumps(m["wheels"])},')
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
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
    lines.append(f'"notes": {json.dumps(m["notes"], indent=1)}' + "}")
    return "\n".join(lines) + "\n"


TEXT = {"kart_ultra.json": kart_text, "kart_scenery.json": scenery_text}


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
        else:
            tris = ", ".join(f"{k} {v['total']}" for k, v in data["notes"]["triangles"].items())
            print(f"wrote models/{name} ({len(text) / 1e6:.2f} MB, triangles per track: {tris})")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    build()
