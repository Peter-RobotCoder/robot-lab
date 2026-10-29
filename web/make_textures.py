"""tex/ for Club Coders Live: the app's own surfaces and skies, so the page's graphics tiers draw what the app's do
(CHANGE 131).

- the texture sets the games paint their parts with (engine/rw_textures.py: paint, steel, tyre, treadplate, hazard,
  concrete; Kart Lab's kart_gfx.py: tarmac, grass, and for its ultra circuit (CHANGE 144, kart_scenery.MATERIALS)
  asphalt, kerb, gravel, turf, render, bark, foliage, needles, signs, water (CHANGE 151); Robot Lab's lab_textures.py for its ultra arena
  (CHANGE 145, arena_models.MATERIALS): lab_floor, lab_signs; Fight Lab's fight_textures.py for its ultra hall
  (CHANGE 147, stage_models.MATERIALS): fight_canvas, fight_signs): albedo, metal-rough and normal maps, at
  512 x 512 as JPEGs (the app's high tier loads them at 1024: the page draws fewer pixels, and a school laptop has
  less memory), but for FINE (Kart Lab's boards' lettering at 1024: CHANGE 151);
- each sky's reflections as simplepbr makes them (its own functions, so the numbers are the app's): the nine
  spherical-harmonic numbers for the light from everywhere, and the sky blurred four ways for shiny to rough
  surfaces, unwrapped into one latitude-longitude picture per sky (the page reads it without cube-map rules);
  "env" is Robot Lab's and Fight Lab's arena (64 and 16 samples, as rw_gfx and fight_gfx ask), "sky" is Kart Lab's
  daytime sky (32 and 8, as kart_gfx asks);
- simplepbr's BRDF table (the split-sum one its shader reads for reflections).

    python make_textures.py           write tex/ beside this file (run after a texture generator or simplepbr changes)
    python make_textures.py --check   exit 1 if tex/ is out of date with the generators' version numbers (web_test.py)

It needs the games' Python (numpy, Pillow, Panda3D, simplepbr): shared-world-demo/.venv. --check needs none of it.
"""
import ast
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tex")
SETS = {"engine": ["paint", "steel", "tyre", "treadplate", "hazard", "concrete"],
        "kart": ["tarmac", "grass", "asphalt", "kerb", "gravel", "turf", "render", "bark", "foliage", "needles", "signs",
                 "water"],
        "lab": ["lab_floor", "lab_signs"], "fight": ["fight_canvas", "fight_signs"]}
SKIES = {"env": ("engine", "env_#.png", 64, 16), "sky": ("kart", "sky_#.png", 32, 8)}  # name: (folder, files, size, samples)
SIZE = 512
# (CHANGE 151) pictures kept finer, where it shows: Kart Lab's advertising boards' lettering at the window's 1024
# (their albedo alone: the rest of the set is flat; drawn on ultra alone, so only ultra downloads the extra)
FINE = {"signs_albedo": 1024}


def roots():
    """The engine folder and Kart Lab's folder: the public repository (engine/, games/kartlab) or the working one."""
    for top, kart in ((os.path.dirname(HERE), os.path.join("games", "kartlab")),
                      (os.path.dirname(os.path.dirname(HERE)), "kart")):
        if os.path.isdir(os.path.join(top, "engine")) and os.path.isdir(os.path.join(top, kart)):
            return os.path.join(top, "engine"), os.path.join(top, kart)
    return None, None


def lab_root():
    """Robot Lab's folder: the public repository's games/robotlab or the working one's shared-world-demo (CHANGE 145)."""
    for top, lab in ((os.path.dirname(HERE), os.path.join("games", "robotlab")),
                     (os.path.dirname(os.path.dirname(HERE)), "shared-world-demo")):
        if os.path.exists(os.path.join(top, lab, "lab_textures.py")):
            return os.path.join(top, lab)
    return None


def fight_root():
    """Fight Lab's folder: the public repository's games/fightlab or the working one's BeatEmUp (CHANGE 147)."""
    for top, game in ((os.path.dirname(HERE), os.path.join("games", "fightlab")),
                      (os.path.dirname(os.path.dirname(HERE)), "BeatEmUp")):
        if os.path.exists(os.path.join(top, game, "fight_textures.py")):
            return os.path.join(top, game)
    return None


def constant(path, name):
    """A module-level string constant read without importing the file."""
    with open(path, encoding="utf-8") as f:
        for node in ast.parse(f.read()).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
                return node.value.value
    return None


def versions():
    engine, kart = roots()
    return {"engine": constant(os.path.join(engine, "rw_textures.py"), "VERSION"),
            "kart": constant(os.path.join(kart, "kart_gfx.py"), "TEX_VERSION"),
            "lab": constant(os.path.join(lab_root(), "lab_textures.py"), "TEX_VERSION"),
            "fight": constant(os.path.join(fight_root(), "fight_textures.py"), "TEX_VERSION"),
            "size": SIZE, "fine": FINE, "skies": {k: list(v[2:]) for k, v in SKIES.items()}}


def check():
    try:
        with open(os.path.join(OUT, "manifest.json"), encoding="utf-8") as f:
            have = json.load(f)
    except (OSError, ValueError):
        print("tex/manifest.json is missing: run make_textures.py")
        return False
    want = versions()
    if {k: have.get(k) for k in want} != want:
        print(f"tex/ is out of date ({ {k: have.get(k) for k in want} } != {want}): run make_textures.py")
        return False
    missing = [f for f in have.get("files", []) if not os.path.exists(os.path.join(OUT, f))]
    if missing:
        print(f"tex/ is missing {missing}: run make_textures.py")
        return False
    return True


def build():
    import numpy as np
    from PIL import Image
    engine, kart = roots()
    sys.path[:0] = [os.path.dirname(engine), kart, lab_root(), fight_root()]
    from engine import rw_textures
    import fight_textures
    import kart_gfx
    import lab_textures
    import panda3d.core as p3d
    from simplepbr import _ibl_funcs_cpu as ibl
    import simplepbr
    folders = {"engine": rw_textures.ensure(), "kart": kart_gfx.TEX, "lab": lab_textures.ensure(),
               "fight": fight_textures.ensure()}
    kart_gfx._textures()
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if not f.startswith("craft_"):  # (tex/craft_atlas.png is make_craft.py's)
            os.remove(os.path.join(OUT, f))
    files = []
    for where, names in SETS.items():
        for name in names:
            for kind in ("albedo", "mr", "normal"):
                im = Image.open(os.path.join(folders[where], f"{name}_{kind}.png")).convert("RGB")
                size = FINE.get(f"{name}_{kind}", SIZE)
                if im.size[0] > size:
                    im = im.resize((size, size), Image.LANCZOS)
                out = f"{name}_{kind}.jpg"
                im.save(os.path.join(OUT, out), quality=90)
                files.append(out)
    lights = {}
    for sky, (where, pattern, size, samples) in SKIES.items():
        cube = p3d.TexturePool.load_cube_map(p3d.Filename.from_os_specific(os.path.join(folders[where], pattern)))
        sh = ibl.get_sh_coeffs_from_cube_map(cube)
        lights[sky] = [[round(c, 6) for c in v] for v in sh]
        peeker = cube.peek()
        rows = []
        for level in range(4):  # (filter_env_map's four mipmaps: roughness 0, 1/3, 2/3, 1)
            h = max(1, int(size * 0.5 ** level))
            w = 2 * h
            img = np.zeros((h, w, 3), np.float32)
            for j in range(h):
                theta = (j + 0.5) / h * math.pi  # (row 0 looks straight up: game z)
                for i in range(w):
                    phi = (i + 0.5) / w * 2 * math.pi - math.pi
                    d = p3d.LVector3(math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta))
                    c = ibl.filter_sample(d, peeker, level / 3, samples)
                    img[j, i] = (c[0], c[1], c[2])
            rows.append(Image.fromarray(np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)).resize((2 * size, size), Image.BILINEAR))
        atlas = Image.new("RGB", (2 * size, 4 * size))
        for level, im in enumerate(rows):
            atlas.paste(im, (0, level * size))
        out = f"{sky}_reflect.png"
        atlas.save(os.path.join(OUT, out))
        files.append(out)
    # simplepbr's BRDF table: x = n.v, y = perceptual roughness (row 0 of the PNG is roughness 0)
    lut = simplepbr.Pipeline._BRDF_LUT  # (loaded from the package as simplepbr starts)
    lw, lh, comps = lut.get_x_size(), lut.get_y_size(), lut.get_num_components()
    width = lut.get_component_width()
    raw = bytes(lut.get_ram_image())
    dtype = {2: np.float16, 4: np.float32}.get(width, np.uint8)
    arr = np.frombuffer(raw, dtype=dtype).astype(np.float32).reshape(lh, lw, comps)
    if dtype == np.uint8:
        arr = arr / 255.0
    rg = arr[:, :, :2] if comps >= 2 else np.repeat(arr, 2, axis=2)  # (two channels are kept in order: gen_brdf_lut packs x, y)
    out_img = np.dstack([rg[:, :, 0], rg[:, :, 1], np.zeros((lh, lw), np.float32)])
    Image.fromarray(np.clip(out_img * 255 + 0.5, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "brdf_lut.png"))
    files.append("brdf_lut.png")
    manifest = dict(versions(), files=sorted(files), sh=lights, simplepbr=getattr(simplepbr, "__version__", ""))
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in files)
    print(f"wrote {len(files)} files to {OUT} ({total / 1e6:.1f} MB)")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    build()
