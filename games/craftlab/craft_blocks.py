"""Craft Lab's blocks, items, tools and food (CHANGE 200): what each one is called, how it is drawn, how hard it is
to dig and with what, what light it gives and what it drops. Plain data, read by the world, the drawing, the
crafting and the server. mods/blocks.py can add blocks of a learner's own (craft_mods.py checks them first).

A block is a number from 0 to 255 in the world's array (0 is air). An item is a block you hold, or something that is
only ever held (a stick, an ingot, a tool, food): those are numbered from 256 up. Every name is Club Coders' own.

Each block:
    key      the name the code uses ("planks")
    name     the name on screen ("Planks")
    tiles    the texture atlas tiles for its faces: one name for every face, or (top, sides, bottom)
    shape    cube, cross (a plant: two crossed squares), torch, liquid, door, ladder, bed, farmland, crop, slab
    solid    you bump into it         opaque  it hides the faces of the blocks beside it
    hard     seconds to dig by hand (None: can't be dug)   tool  pick, axe, shovel (digs it faster)   level  the tool
             level it needs to drop anything (0 hand, 1 wood, 2 stone, 3 copper, 4 iron)
    drops    the item it gives (its own key unless it says), with how many
    light    the light it gives (0 to 15)
    falls    sand and grit fall when nothing is under them
    see      cutout (leaves, glass: see through the gaps) or blend (water, ice: see through it all)
    use      what pressing it does: workbench, smelter, chest, door, bed, dock
"""

TILE = 16       # pixels a tile
ATLAS = 16      # tiles across the atlas (and down)

# ---------- blocks ----------
_B = [
    # key, name, tiles, extra
    ("air", "Air", None, dict(shape="air", solid=False, opaque=False, hard=None)),
    ("grass", "Grass", ("grass_top", "grass_side", "soil"), dict(hard=0.9, tool="shovel", drops="soil")),
    ("soil", "Soil", "soil", dict(hard=0.75, tool="shovel")),
    ("stone", "Stone", "stone", dict(hard=2.2, tool="pick", level=1, drops="rubble")),
    ("rubble", "Rubble", "rubble", dict(hard=2.6, tool="pick", level=1)),
    ("corestone", "Corestone", "corestone", dict(hard=None)),
    ("sand", "Sand", "sand", dict(hard=0.75, tool="shovel", falls=True)),
    ("grit", "Grit", "grit", dict(hard=0.9, tool="shovel", falls=True)),
    ("water", "Water", "water", dict(shape="liquid", solid=False, opaque=False, hard=None, see="blend")),
    ("log", "Log", ("log_top", "log_side", "log_top"), dict(hard=2.0, tool="axe")),
    ("leaves", "Leaves", "leaves", dict(hard=0.3, opaque=False, see="cutout", drops=None)),
    ("planks", "Planks", "planks", dict(hard=2.0, tool="axe")),
    ("workbench", "Workbench", ("bench_top", "bench_side", "planks"), dict(hard=2.5, tool="axe", use="workbench")),
    ("smelter", "Smelter", ("smelter_top", "smelter_front", "smelter_top"), dict(hard=3.5, tool="pick", level=1, use="smelter")),
    ("smelter_lit", "Smelter (lit)", ("smelter_top", "smelter_lit", "smelter_top"),
     dict(hard=3.5, tool="pick", level=1, use="smelter", light=13, drops="smelter")),
    ("chest", "Chest", ("chest_top", "chest_side", "chest_top"), dict(hard=2.5, tool="axe", use="chest")),
    ("glass", "Glass", "glass", dict(hard=0.4, opaque=False, see="cutout", drops=None)),
    ("brick", "Brick", "brick", dict(hard=3.0, tool="pick", level=1)),
    ("torch", "Torch", "torch", dict(shape="torch", solid=False, opaque=False, hard=0.05, light=14)),
    ("coal_ore", "Coal ore", "coal_ore", dict(hard=3.0, tool="pick", level=1, drops="coal")),
    ("copper_ore", "Copper ore", "copper_ore", dict(hard=3.2, tool="pick", level=2)),
    ("iron_ore", "Iron ore", "iron_ore", dict(hard=3.6, tool="pick", level=2)),
    ("crystal_ore", "Crystal ore", "crystal_ore", dict(hard=4.5, tool="pick", level=4, drops="crystal")),
    ("lumen", "Lumen block", "lumen", dict(hard=0.6, light=15)),
    ("snow", "Snow", "snow", dict(hard=0.5, tool="shovel")),
    ("ice", "Ice", "ice", dict(hard=0.8, tool="pick", opaque=False, see="blend", drops=None)),
    ("cactus", "Cactus", ("cactus_top", "cactus_side", "cactus_top"), dict(hard=0.6, opaque=False, see="cutout", hurts=1)),
    ("clay", "Clay", "clay", dict(hard=0.9, tool="shovel", drops=("clay_ball", 4))),
    ("sandstone", "Sandstone", ("sandstone_top", "sandstone_side", "sandstone_top"), dict(hard=1.6, tool="pick", level=1)),
    ("wool", "White wool", "wool_white", dict(hard=0.8)),
    ("wool_red", "Red wool", "wool_red", dict(hard=0.8)),
    ("wool_orange", "Orange wool", "wool_orange", dict(hard=0.8)),
    ("wool_yellow", "Yellow wool", "wool_yellow", dict(hard=0.8)),
    ("wool_green", "Green wool", "wool_green", dict(hard=0.8)),
    ("wool_blue", "Blue wool", "wool_blue", dict(hard=0.8)),
    ("wool_purple", "Purple wool", "wool_purple", dict(hard=0.8)),
    ("wool_black", "Black wool", "wool_black", dict(hard=0.8)),
    ("door", "Door", ("door_low", "door_low", "door_low"), dict(shape="door", hard=2.0, tool="axe", opaque=False, use="door")),
    ("door_top", "Door", ("door_high", "door_high", "door_high"), dict(shape="door", hard=2.0, tool="axe", opaque=False,
                                                                      use="door", drops=None)),
    ("ladder", "Ladder", "ladder", dict(shape="ladder", solid=False, opaque=False, hard=0.6, tool="axe", see="cutout",
                                        climb=True)),
    ("bed", "Bed", ("bed_top", "bed_side", "planks"), dict(shape="bed", hard=0.4, opaque=False, use="bed")),
    ("farmland", "Farmland", ("farmland", "soil", "soil"), dict(shape="farmland", hard=0.7, tool="shovel", opaque=False,
                                                              drops="soil")),
    ("wheat", "Wheat", "wheat_7", dict(shape="crop", solid=False, opaque=False, hard=0.05, see="cutout", drops=None)),
    ("sapling", "Sapling", "sapling", dict(shape="cross", solid=False, opaque=False, hard=0.05, see="cutout")),
    ("berry_bush", "Berry bush", "berry_bush", dict(shape="cross", solid=False, opaque=False, hard=0.2, see="cutout",
                                                    drops=None, use="berries")),
    ("tall_grass", "Tall grass", "tall_grass", dict(shape="cross", solid=False, opaque=False, hard=0.05, see="cutout",
                                                    drops=None)),
    ("flower_red", "Red flower", "flower_red", dict(shape="cross", solid=False, opaque=False, hard=0.05, see="cutout")),
    ("flower_yellow", "Yellow flower", "flower_yellow", dict(shape="cross", solid=False, opaque=False, hard=0.05,
                                                             see="cutout")),
    ("bookshelf", "Bookshelf", ("planks", "bookshelf", "planks"), dict(hard=1.6, tool="axe")),
    ("stone_bricks", "Stone bricks", "stone_bricks", dict(hard=2.6, tool="pick", level=1)),
    ("copper_block", "Copper block", "copper_block", dict(hard=4.0, tool="pick", level=2)),
    ("iron_block", "Iron block", "iron_block", dict(hard=4.5, tool="pick", level=2)),
    ("crystal_block", "Crystal block", "crystal_block", dict(hard=5.0, tool="pick", level=4, light=6)),
    ("magma", "Magma", "magma", dict(shape="liquid", solid=False, opaque=True, hard=None, light=14, hurts=3)),
    ("blast", "Blast block", ("blast_top", "blast_side", "blast_top"), dict(hard=0.1, use="blast")),
    ("dock", "Bot dock", ("dock_top", "dock_side", "dock_top"), dict(hard=2.0, tool="pick", use="dock", light=7)),
    ("mossy_rubble", "Mossy rubble", "mossy_rubble", dict(hard=2.6, tool="pick", level=1)),
    ("pine_log", "Pine log", ("pine_top", "pine_side", "pine_top"), dict(hard=2.0, tool="axe")),
    ("pine_leaves", "Pine needles", "pine_leaves", dict(hard=0.3, opaque=False, see="cutout", drops=None)),
    ("pale_log", "Pale log", ("pale_top", "pale_side", "pale_top"), dict(hard=2.0, tool="axe")),
    ("pale_leaves", "Pale leaves", "pale_leaves", dict(hard=0.3, opaque=False, see="cutout", drops=None)),
    ("pine_planks", "Pine planks", "pine_planks", dict(hard=2.0, tool="axe")),
    ("glass_pane", "Window", "window", dict(hard=0.4, opaque=False, see="cutout", drops=None)),
    ("slab", "Rubble slab", "rubble", dict(shape="slab", hard=2.0, tool="pick", level=1, opaque=False)),
    ("plank_slab", "Plank slab", "planks", dict(shape="slab", hard=1.5, tool="axe", opaque=False)),
]

DEFAULTS = dict(shape="cube", solid=True, opaque=True, hard=1.0, tool=None, level=0, light=0, falls=False, see=None,
                use=None, climb=False, hurts=0)
BLOCKS = []        # by id: each block's dict
ID = {}            # key -> id
for _i, (_key, _name, _tiles, _extra) in enumerate(_B):
    b = dict(DEFAULTS, id=_i, key=_key, name=_name, **_extra)
    if _tiles is None:
        b["tiles"] = None
    elif isinstance(_tiles, str):
        b["tiles"] = (_tiles, _tiles, _tiles)
    else:
        b["tiles"] = tuple(_tiles)
    b.setdefault("drops", _key)
    BLOCKS.append(b)
    ID[_key] = _i
AIR, WATER, MAGMA = ID["air"], ID["water"], ID["magma"]
N_BUILT_IN = len(BLOCKS)

# ---------- items that are only ever held ----------
ITEM_BASE = 256
TOOL_KINDS = ("pick", "axe", "shovel", "sword", "hoe")
TOOL_LEVELS = (("wood", "Wooden", 1, 2.0, 60), ("stone", "Stone", 2, 4.0, 130), ("copper", "Copper", 3, 5.0, 200),
               ("iron", "Iron", 4, 6.5, 300), ("crystal", "Crystal", 5, 9.0, 900))  # (key, word, level, speed, uses)
_I = [
    ("stick", "Stick", "stick", {}),
    ("coal", "Coal", "coal", {"fuel": 8}),
    ("copper_ingot", "Copper ingot", "copper_ingot", {}),
    ("iron_ingot", "Iron ingot", "iron_ingot", {}),
    ("crystal", "Crystal", "crystal", {}),
    ("wheat_item", "Wheat", "wheat_item", {}),
    ("seeds", "Seeds", "seeds", {"plants": "wheat"}),
    ("bread", "Bread", "bread", {"food": 5}),
    ("apple", "Apple", "apple", {"food": 4}),
    ("berries", "Berries", "berries", {"food": 2}),
    ("roast_potato", "Baked root", "roast_root", {"food": 6}),
    ("root", "Root", "root", {"food": 1, "smelts": "roast_potato"}),
    ("clay_ball", "Clay", "clay_ball", {"smelts": "brick_item"}),
    ("brick_item", "Brick", "brick_item", {}),
    ("scrap", "Scrap", "scrap", {}),
    ("glitch_shard", "Glitch shard", "glitch_shard", {}),
    ("rust", "Rust", "rust", {}),
    ("bucket", "Bucket", "bucket", {}),
    ("water_bucket", "Water bucket", "water_bucket", {"places": "water"}),
    ("bot_kit", "Bot kit", "bot_kit", {}),
    ("charcoal", "Charcoal", "charcoal", {"fuel": 8}),
]
ITEMS = {}          # id -> the item's dict (blocks included, as items: their block's key, name and first tile)
ITEM_ID = {}        # key -> id
for b in BLOCKS:
    if b["id"]:
        ITEMS[b["id"]] = {"id": b["id"], "key": b["key"], "name": b["name"], "icon": b["tiles"][1] if b["tiles"] else None,
                          "block": b["id"], "stack": 64}
        ITEM_ID[b["key"]] = b["id"]
_n = ITEM_BASE
for _key, _name, _icon, _extra in _I:
    ITEMS[_n] = dict({"id": _n, "key": _key, "name": _name, "icon": _icon, "block": None, "stack": 64}, **_extra)
    ITEM_ID[_key] = _n
    _n += 1
for _kind in TOOL_KINDS:
    for _lk, _word, _level, _speed, _uses in TOOL_LEVELS:
        key = f"{_lk}_{_kind}"
        ITEMS[_n] = {"id": _n, "key": key, "name": f"{_word} {_kind}", "icon": key, "block": None, "stack": 1,
                     "tool": _kind, "level": _level, "speed": _speed, "uses": _uses,
                     "damage": {"sword": 3 + _level, "axe": 2 + _level}.get(_kind, 1 + _level // 2)}
        ITEM_ID[key] = _n
        _n += 1
# armour: four pieces in four materials, worn in the inventory's four armour slots (head, chest, legs, feet). Each
# piece has points (all twenty, crystal from head to foot, keep off 80% of a hit) and wears out a little each hit.
ARMOUR_PARTS = (("helmet", "helmet"), ("chest", "chest guard"), ("legs", "leg guards"), ("boots", "boots"))
ARMOUR_LEVELS = (("cloth", "Cloth", (1, 3, 2, 1), 55), ("copper", "Copper", (2, 5, 4, 1), 120),
                 ("iron", "Iron", (2, 6, 5, 2), 220), ("crystal", "Crystal", (3, 8, 6, 3), 480))  # (key, word, points, uses)
ARMOUR_SHARE = 0.04     # of a hit kept off for each point worn
for _part, (_pk, _pword) in enumerate(ARMOUR_PARTS):
    for _mk, _word, _points, _uses in ARMOUR_LEVELS:
        key = f"{_mk}_{_pk}"
        ITEMS[_n] = {"id": _n, "key": key, "name": f"{_word} {_pword}", "icon": key, "block": None, "stack": 1,
                     "armour": _part, "points": _points[_part], "uses": _uses}
        ITEM_ID[key] = _n
        _n += 1
ITEMS[ITEM_ID["bucket"]]["stack"] = 16
ITEMS[ITEM_ID["water_bucket"]]["stack"] = 1
ITEMS[ITEM_ID["bot_kit"]]["stack"] = 1
FOOD = {i: it["food"] for i, it in ITEMS.items() if it.get("food")}
FUEL = {i: it["fuel"] for i, it in ITEMS.items() if it.get("fuel")}
FUEL.update({ID["log"]: 4, ID["pine_log"]: 4, ID["pale_log"]: 4, ID["planks"]: 2, ID["pine_planks"]: 2,
             ITEM_ID["stick"]: 1})
SMELTS = {ID["iron_ore"]: ITEM_ID["iron_ingot"], ID["copper_ore"]: ITEM_ID["copper_ingot"], ID["sand"]: ID["glass"],
          ID["rubble"]: ID["stone"], ID["log"]: ITEM_ID["charcoal"], ID["pine_log"]: ITEM_ID["charcoal"],
          ID["pale_log"]: ITEM_ID["charcoal"], ITEM_ID["clay_ball"]: ITEM_ID["brick_item"],
          ITEM_ID["root"]: ITEM_ID["roast_potato"], ID["clay"]: ID["brick"], ITEM_ID["rust"]: ITEM_ID["iron_ingot"]}
SMELT_SECONDS = 4.0     # a smelter's time for one item
HAND = {"tool": None, "level": 0, "speed": 1.0, "damage": 1}


def block(key_or_id):
    return BLOCKS[key_or_id] if isinstance(key_or_id, int) else BLOCKS[ID[key_or_id]]


def item(key_or_id):
    return ITEMS.get(key_or_id if isinstance(key_or_id, int) else ITEM_ID.get(key_or_id))


def name_of(i):
    it = ITEMS.get(i)
    return it["name"] if it else "?"


def dig_time(bid, held):
    """Seconds to dig block bid holding item held (an item dict or None), and whether it drops anything."""
    b = BLOCKS[bid]
    if b["hard"] is None:
        return None, False
    tool = held if held and held.get("tool") else HAND
    right = b["tool"] is not None and tool.get("tool") == b["tool"]
    speed = tool.get("speed", 1.0) if right else 1.0
    enough = tool.get("level", 0) >= b["level"] if b["level"] else True
    t = b["hard"] * 1.5 / speed
    if not enough:
        t *= 3.3
    return max(0.05, t), enough


def drops_of(bid, enough=True):
    """What digging block bid gives: [(item id, count)] (nothing without the right tool, or for leaves and glass)."""
    b = BLOCKS[bid]
    if not enough or b["drops"] is None:
        return []
    d = b["drops"]
    key, n = (d if isinstance(d, tuple) else (d, 1))
    return [(ITEM_ID[key], n)] if key in ITEM_ID else []


# tables the hot loops read: numpy arrays by block id
def tables():
    import numpy as np
    n = 256
    solid = np.zeros(n, bool)
    opaque = np.zeros(n, bool)
    light = np.zeros(n, np.uint8)
    cube = np.zeros(n, bool)
    for b in BLOCKS:
        i = b["id"]
        solid[i] = b["solid"]
        opaque[i] = b["opaque"] and b["shape"] == "cube"
        light[i] = b["light"]
        cube[i] = b["shape"] in ("cube",)
    return {"solid": solid, "opaque": opaque, "light": light, "cube": cube}


def add_block(spec):
    """A learner's block from mods/blocks.py (already checked by craft_mods): its id, or None when the 256 are full."""
    if len(BLOCKS) >= 256:
        return None
    i = len(BLOCKS)
    b = dict(DEFAULTS, id=i, key=spec["key"], name=spec["name"], tiles=(f"mod_{spec['key']}",) * 3, hard=spec.get("hard", 1.0),
             light=spec.get("light", 0), tool=spec.get("tool"), mod=True, colour=spec.get("colour"))
    b["drops"] = spec["key"]
    BLOCKS.append(b)
    ID[b["key"]] = i
    ITEMS[i] = {"id": i, "key": b["key"], "name": b["name"], "icon": b["tiles"][1], "block": i, "stack": 64}
    ITEM_ID[b["key"]] = i
    return i
