"""Craft Lab's pictures and tables for Club Coders Live (CHANGE 202): the page draws Craft Lab as its window does.

- tex/craft_atlas.png: every block face, item icon, crop stage, tool, suit piece and creature face, 16 x 16 pixels a
  tile, 16 x 16 tiles: the atlas craft_art.py draws by code (its own numpy, seeded by each tile's name, so it is the
  window's atlas pixel for pixel). The page samples it nearest (big pixels close to), mipmapped far off on medium and
  up, as the window does (craft_gfx.atlas_texture).
- tex/craft_clouds.png: craft_gfx.cloud_image's four soft puff clouds (256 x 128 each, one under another).
- craft.json: where each tile is in the atlas (craft_art.build_atlas's where), every block (craft_blocks: its key,
  name, faces' tiles, shape, solid, opaque, see-through, light, hardness, tool and level, climbable, use), every item
  (its key, name, icon, the block it puts down, stack, tool, level, speed, uses, damage, food, fuel, the suit
  slot it goes in and its Shield), the suit's slots, the Refinery's table, the light scale, the tiles whose frames
  play (animated), the
  mesher's numbers (craft_mesh's face shading and corner shading) and the sky's random things (craft_gfx's stars,
  where the clouds start, the dig mask's order: make_craft.sky), so craft.js and craft_sim.js need no copy of the
  game's Python. A learner's own blocks (mods/blocks.py) come from the server in the welcome: the page adds them and
  paints their tiles itself, as the window does.

    python make_craft.py            write tex/craft_atlas.png and craft.json (run after craft_art.py, craft_blocks.py
                                    or craft_mesh.py changes: web_test.py checks it)
    python make_craft.py --check    exit 1 if they aren't what craft/ makes

Run it with the games' Python (shared-world-demo/.venv: numpy and Pillow). The atlas is made with no mods loaded
(the page adds the server's).
"""
import hashlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "tex", "craft_atlas.png")
CLOUDS = os.path.join(HERE, "tex", "craft_clouds.png")
OUT = os.path.join(HERE, "craft.json")
MAKER = "3"  # (this file's own version: change it when what it writes changes shape. 2: the suit, the Refinery;
#              3: the sky's stars, clouds and dig order)


def craft_folder():
    """Craft Lab's folder: games/craftlab beside web/ in the public repository, craft/ in the working folder."""
    for folder in (os.path.join(os.path.dirname(HERE), "games", "craftlab"),
                   os.path.join(os.path.dirname(os.path.dirname(HERE)), "craft")):
        if os.path.exists(os.path.join(folder, "craft_art.py")):
            return folder
    return None


def build():
    folder = craft_folder()
    if folder is None:
        sys.exit("make_craft.py: Craft Lab's folder (craft/) isn't beside this one")
    sys.path.insert(0, folder)
    import craft_art
    import craft_blocks as B
    import craft_mesh as M
    atlas, where = craft_art.build_atlas()
    blocks = []
    for b in B.BLOCKS:
        if b.get("mod"):
            continue
        blocks.append({"id": b["id"], "key": b["key"], "name": b["name"], "tiles": list(b["tiles"]) if b["tiles"] else None,
                       "shape": b["shape"], "solid": b["solid"], "opaque": b["opaque"], "see": b["see"], "light": b["light"],
                       "hard": b["hard"], "tool": b["tool"], "level": b["level"], "climb": b["climb"], "use": b["use"],
                       "falls": b["falls"], "hurts": b["hurts"]})
    item_keys = ("id", "key", "name", "icon", "block", "stack", "tool", "level", "speed", "uses", "damage", "food",
                 "fuel", "places", "plants", "suit", "shield", "glow")
    items = [{k: it[k] for k in item_keys if k in it} for _, it in sorted(B.ITEMS.items())
             if not (it.get("block") is not None and B.BLOCKS[it["block"]].get("mod"))]
    data = {
        "maker": MAKER, "art_version": craft_art.ART_VERSION,
        "atlas": {"file": "tex/craft_atlas.png", "tile": B.TILE, "tiles": B.ATLAS, "used": len(where),
                  "md5": hashlib.md5(atlas.tobytes()).hexdigest(), "where": {k: list(v) for k, v in where.items()}},
        "blocks": blocks, "items": items, "item_base": B.ITEM_BASE, "n_built_in": B.N_BUILT_IN,
        "hand": B.HAND, "suit_parts": [list(p) for p in B.SUIT_PARTS], "stack": B.STACK, "light_max": B.LIGHT_MAX,
        "animated": dict(B.ANIMATED), "fuel": {str(k): v for k, v in sorted(B.FUEL.items())},
        "refines": {str(k): v for k, v in sorted(B.REFINES.items())},
        "refine_takes": {str(k): v for k, v in sorted(B.REFINE_TAKES.items())},
        "mesh": {"face_shade": [float(v) for v in M.FACE_SHADE], "ao": [float(v) for v in M.AO],
                 "wavy": sorted(M.WAVY)},
    }
    data["sky"], clouds = sky()
    return atlas, data, clouds


def sky():
    """The sky's own random things, as craft_gfx makes them (numpy's generators, seeded), so the page's sky is the
    window's: the 500 stars (craft_gfx.Sky.star_node: a direction, its brightness and colour, 440 small then 60
    big), the four cloud pictures (craft_gfx.cloud_image: tex/craft_clouds.png, one under another) and where each
    tier's clouds start (Sky.__init__'s draws after the pictures: width, picture, and the two numbers 0..1 its x and y
    come from across the span), the dig mask's order on the looks (Target: default_rng(7))."""
    import copy

    import numpy as np
    import craft_gfx as gfx
    from panda3d.core import GeomVertexReader
    node = gfx.Sky.star_node(1.0)
    stars = []
    for i in range(node.getNumGeoms()):
        vd = node.getGeom(i).getVertexData()
        pos, col = GeomVertexReader(vd, "vertex"), GeomVertexReader(vd, "color")
        for _ in range(vd.getNumRows()):
            p, c = pos.getData3(), col.getData4()
            stars.append([round(float(v), 5) for v in p] + [round(float(c[k]), 4) for k in range(3)] + [2 if i else 1])
    rng = np.random.default_rng(5)
    pictures = [gfx.cloud_image(rng) for _ in range(4)]
    layouts = {}
    for n in sorted(set(v for v in gfx.CLOUDS.values() if v)):
        r = copy.deepcopy(rng)
        rows = []
        for layer in range(2):
            for _ in range(n):
                w = float(r.uniform(16, 30)) * (1.0 if layer == 0 else 1.3)
                tex = int(r.integers(0, 4))
                dx, dy = r.random(2)   # (the same two doubles as uniform(-span, span, 2))
                rows.append([round(w, 5), tex, round(float(dx), 6), round(float(dy), 6), layer])
        layouts[str(n)] = rows
    order = np.random.default_rng(7).random((16, 16))
    data = {"stars": stars, "clouds": {"file": "tex/craft_clouds.png", "aspect": gfx.CLOUD_ASPECT,
                                       "count": dict(gfx.CLOUDS), "layouts": layouts},
            "dig_order": [round(float(v), 6) for v in order.ravel()]}
    img = (np.clip(np.concatenate(pictures, 0), 0, 1) * 255 + 0.5).astype(np.uint8)
    return data, img


def png_bytes(atlas):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(atlas, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def text(data):
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main():
    atlas, data, clouds = build()
    made = text(data)
    if "--check" in sys.argv:
        problems = []
        try:
            with open(OUT, encoding="utf-8") as f:
                if f.read() != made:
                    problems.append("craft.json isn't what craft/ makes")
        except OSError:
            problems.append("craft.json is missing")
        try:
            import numpy as np
            from PIL import Image
            have = np.asarray(Image.open(ATLAS).convert("RGBA"))
            if have.shape != atlas.shape or not (have == atlas).all():
                problems.append("tex/craft_atlas.png isn't craft_art's atlas")
        except OSError:
            problems.append("tex/craft_atlas.png is missing")
        try:
            have = np.asarray(Image.open(CLOUDS).convert("RGBA"))
            if have.shape != clouds.shape or not (have == clouds).all():
                problems.append("tex/craft_clouds.png isn't craft_gfx's clouds")
        except OSError:
            problems.append("tex/craft_clouds.png is missing")
        print("; ".join(problems) + ": run make_craft.py" if problems else
              f"craft.json and tex/craft_atlas.png are up to date ({data['atlas']['used']} tiles, "
              f"{len(data['blocks'])} blocks, {len(data['items'])} items)")
        return 1 if problems else 0
    os.makedirs(os.path.dirname(ATLAS), exist_ok=True)
    with open(ATLAS, "wb") as f:
        f.write(png_bytes(atlas))
    with open(CLOUDS, "wb") as f:
        f.write(png_bytes(clouds))
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(made)
    print(f"Wrote {ATLAS} ({data['atlas']['used']} tiles) and {OUT} ({len(data['blocks'])} blocks, "
          f"{len(data['items'])} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
