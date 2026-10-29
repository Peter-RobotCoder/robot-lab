"""Craft Lab's pictures and tables for Club Coders Live (CHANGE 202): the page draws Craft Lab as its window does.

- tex/craft_atlas.png: every block face, item icon, crop stage, digging crack and creature face, 16 x 16 pixels a
  tile, 16 x 16 tiles: the atlas craft_art.py draws by code (its own numpy, seeded by each tile's name, so it is the
  window's atlas pixel for pixel). The page samples it nearest (big pixels close to), mipmapped far off on medium and
  up, as the window does (craft_gfx.atlas_texture).
- craft.json: where each tile is in the atlas (craft_art.build_atlas's where), every block (craft_blocks: its key,
  name, faces' tiles, shape, solid, opaque, see-through, light, hardness, tool and level, climbable, use), every item
  (its key, name, icon, the block it puts down, stack, tool, level, speed, uses, damage, food, fuel), and the
  mesher's numbers (craft_mesh's face shading and corner shading), so craft.js and craft_sim.js need no copy of the
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
OUT = os.path.join(HERE, "craft.json")
MAKER = "1"  # (this file's own version: change it when what it writes changes shape)


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
                 "fuel", "places", "plants", "smelts", "armour", "points")
    items = [{k: it[k] for k in item_keys if k in it} for _, it in sorted(B.ITEMS.items())
             if not (it.get("block") is not None and B.BLOCKS[it["block"]].get("mod"))]
    data = {
        "maker": MAKER, "art_version": craft_art.ART_VERSION,
        "atlas": {"file": "tex/craft_atlas.png", "tile": B.TILE, "tiles": B.ATLAS, "used": len(where),
                  "md5": hashlib.md5(atlas.tobytes()).hexdigest(), "where": {k: list(v) for k, v in where.items()}},
        "blocks": blocks, "items": items, "item_base": B.ITEM_BASE, "n_built_in": B.N_BUILT_IN,
        "hand": B.HAND, "armour_parts": [list(p) for p in getattr(B, "ARMOUR_PARTS", ())],
        "armour_share": getattr(B, "ARMOUR_SHARE", 0), "fuel": {str(k): v for k, v in sorted(B.FUEL.items())},
        "smelts": {str(k): v for k, v in sorted(B.SMELTS.items())},
        "mesh": {"face_shade": [float(v) for v in M.FACE_SHADE], "ao": [float(v) for v in M.AO],
                 "wavy": sorted(M.WAVY)},
    }
    return atlas, data


def png_bytes(atlas):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(atlas, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def text(data):
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main():
    atlas, data = build()
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
        print("; ".join(problems) + ": run make_craft.py" if problems else
              f"craft.json and tex/craft_atlas.png are up to date ({data['atlas']['used']} tiles, "
              f"{len(data['blocks'])} blocks, {len(data['items'])} items)")
        return 1 if problems else 0
    os.makedirs(os.path.dirname(ATLAS), exist_ok=True)
    with open(ATLAS, "wb") as f:
        f.write(png_bytes(atlas))
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(made)
    print(f"Wrote {ATLAS} ({data['atlas']['used']} tiles) and {OUT} ({len(data['blocks'])} blocks, "
          f"{len(data['items'])} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
