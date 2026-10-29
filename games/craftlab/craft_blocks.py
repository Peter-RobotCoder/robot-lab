"""Craft Lab's blocks, items, tools, suit pieces and food (CHANGE 200, our own world since CHANGE 207): what each
one is called, how it is drawn, how hard it is to dig and with what, what light it gives and what it drops. Plain
data, read by the world, the drawing, the Fabricator and the server. mods/blocks.py can add blocks of a learner's
own (craft_mods.py checks them first).

The island is a Club Coders test lab the robots are rebuilding: its blocks come from the island (turf, stone, logs,
ores) and from salvaged scrap (Batteries, Overload Cells, the Bot dock, Server Racks).

A block is a number from 0 to 255 in the world's array (0 is air). An item is a block you hold, or something that is
only ever held (a rod, an ingot, a tool, food): those are numbered from 256 up.

Each block:
    key      the name the code uses ("boards")
    name     the name on screen ("Boards")
    tiles    the texture atlas tiles for its faces: one name for every face, or (top, sides, bottom)
    shape    cube, cross (a plant: two crossed squares), torch (a glowstick), liquid, door, ladder, bed (a Recharge
             Pod), farmland (a Grow bed), crop, slab (a step)
    solid    you bump into it         opaque  it hides the faces of the blocks beside it
    hard     seconds to dig by hand (None: can't be dug)   tool  drill, cutter, scoop (digs it faster)   level  the
             Drill's Mk it needs to drop anything (0 a hand will do, 1 Mk1, 2 Mk2, 3 Mk3)
    drops    the item it gives (its own key unless it says), with how many
    light    the light it gives (0 to 12, LIGHT_MAX)
    falls    sand and grit fall when nothing is under them
    see      cutout (leaves, glass: see through the gaps) or blend (water, ice: see through it all)
    use      what pressing it does: fabricator, refinery, locker, door, pod, dock, overload, berries, glowfruit, rift

Old names (from before CHANGE 207: planks, workbench, torch...) still load through ALIASES, so an old mod or brain
works, with a warning that says the new name.
"""

TILE = 16       # pixels a tile
ATLAS = 16      # tiles across the atlas (and down)
LIGHT_MAX = 12  # the brightest light: the open sky, a Lumen block
STACK = 50      # things of one kind in a slot (Canisters 10; tools, suit pieces and the Bot kit 1)

# ---------- blocks ----------
_B = [
    # key, name, tiles, extra
    ("air", "Air", None, dict(shape="air", solid=False, opaque=False, hard=None)),
    ("turf", "Turf", ("turf_top", "turf_side", "soil"), dict(hard=0.9, tool="scoop", drops="soil")),
    ("soil", "Soil", "soil", dict(hard=0.75, tool="scoop")),
    ("stone", "Stone", "stone", dict(hard=2.2, tool="drill", level=1, drops="rubble")),
    ("rubble", "Rubble", "rubble", dict(hard=2.6, tool="drill", level=1)),
    ("lab_floor", "Lab floor", "lab_floor", dict(hard=None, light=2)),
    ("sand", "Sand", "sand", dict(hard=0.75, tool="scoop", falls=True)),
    ("grit", "Grit", "grit", dict(hard=0.9, tool="scoop", falls=True)),
    ("water", "Water", "water", dict(shape="liquid", solid=False, opaque=False, hard=None, see="blend")),
    ("log", "Log", ("log_top", "log_side", "log_top"), dict(hard=2.0, tool="cutter")),
    ("leaves", "Leaves", "leaves", dict(hard=0.3, tool="cutter", opaque=False, see="cutout", drops=None)),
    ("boards", "Boards", "boards", dict(hard=2.0, tool="cutter")),
    ("fabricator", "Fabricator", ("fabricator_top", "fabricator_side", "fabricator_bottom"),
     dict(hard=2.5, tool="cutter", use="fabricator")),
    ("refinery", "Refinery", ("refinery_top", "refinery_side", "refinery_bottom"),
     dict(hard=3.5, tool="drill", level=1, use="refinery")),
    ("refinery_on", "Refinery (on)", ("refinery_top", "refinery_on", "refinery_bottom"),
     dict(hard=3.5, tool="drill", level=1, use="refinery", light=8, drops="refinery")),
    ("locker", "Locker", ("locker_top", "locker_side", "locker_top"), dict(hard=2.5, tool="cutter", use="locker")),
    ("glass", "Glass", "glass", dict(hard=0.4, opaque=False, see="cutout", drops=None)),
    ("brick", "Brick block", "brick", dict(hard=3.0, tool="drill", level=1)),
    ("glowstick", "Glowstick", "glowstick", dict(shape="torch", solid=False, opaque=False, hard=0.05, light=10)),
    ("coal_ore", "Coal ore", "coal_ore", dict(hard=3.0, tool="drill", level=1, drops="coal")),
    ("copper_ore", "Copper ore", "copper_ore", dict(hard=3.2, tool="drill", level=1)),
    ("iron_ore", "Iron ore", "iron_ore", dict(hard=3.6, tool="drill", level=1)),
    ("neon_ore", "Neon ore", "neon_ore", dict(hard=4.5, tool="drill", level=2, light=4)),
    ("lumen", "Lumen block", "lumen", dict(hard=0.6, light=12)),
    ("snow", "Snow", "snow", dict(hard=0.5, tool="scoop")),
    ("ice", "Ice", "ice", dict(hard=0.8, tool="drill", opaque=False, see="blend", drops=None)),
    ("cactus", "Cactus", ("cactus_top", "cactus_side", "cactus_top"), dict(hard=0.6, opaque=False, see="cutout", hurts=5)),
    ("clay", "Clay", "clay", dict(hard=0.9, tool="scoop", drops=("clay_ball", 4))),
    ("sandstone", "Sandstone", ("sandstone_top", "sandstone_side", "sandstone_top"), dict(hard=1.6, tool="drill", level=1)),
    ("fluff", "White fluff", "fluff_white", dict(hard=0.8)),
    ("fluff_red", "Red fluff", "fluff_red", dict(hard=0.8)),
    ("fluff_yellow", "Yellow fluff", "fluff_yellow", dict(hard=0.8)),
    ("fluff_green", "Green fluff", "fluff_green", dict(hard=0.8)),
    ("fluff_blue", "Blue fluff", "fluff_blue", dict(hard=0.8)),
    ("fluff_purple", "Purple fluff", "fluff_purple", dict(hard=0.8)),
    ("fluff_black", "Black fluff", "fluff_black", dict(hard=0.8)),
    ("door", "Door", ("door_low", "door_low", "door_low"), dict(shape="door", hard=2.0, tool="cutter", opaque=False, use="door")),
    ("door_top", "Door", ("door_high", "door_high", "door_high"), dict(shape="door", hard=2.0, tool="cutter", opaque=False,
                                                                      use="door", drops=None)),
    ("ladder", "Ladder", "ladder", dict(shape="ladder", solid=False, opaque=False, hard=0.6, tool="cutter", see="cutout",
                                        climb=True)),
    ("pod", "Recharge Pod", ("pod_top", "pod_side", "pod_bottom"), dict(shape="bed", hard=0.8, opaque=False, use="pod",
                                                                        light=3)),
    ("grow_bed", "Grow bed", ("grow_bed_top", "grow_bed_side", "soil"), dict(shape="farmland", hard=0.7, tool="cutter",
                                                                             opaque=False)),
    ("grain", "Grain", "grain_3", dict(shape="crop", solid=False, opaque=False, hard=0.05, see="cutout", drops=None)),
    ("sapling", "Sapling", "sapling", dict(shape="cross", solid=False, opaque=False, hard=0.05, see="cutout")),
    ("berry_bush", "Berry bush", "berry_bush", dict(shape="cross", solid=False, opaque=False, hard=0.2, see="cutout",
                                                    drops=None, use="berries")),
    ("tall_grass", "Tall grass", "tall_grass", dict(shape="cross", solid=False, opaque=False, hard=0.05, see="cutout",
                                                    drops=None)),
    ("flower_red", "Red flower", "flower_red", dict(shape="cross", solid=False, opaque=False, hard=0.05, see="cutout")),
    ("flower_yellow", "Yellow flower", "flower_yellow", dict(shape="cross", solid=False, opaque=False, hard=0.05,
                                                             see="cutout")),
    ("server_rack", "Server Rack", ("rack_top", "server_rack_0", "rack_top"), dict(hard=1.6, tool="cutter", light=2)),
    ("stone_tiles", "Stone tiles", "stone_tiles", dict(hard=2.6, tool="drill", level=1)),
    ("copper_block", "Copper block", "copper_block", dict(hard=4.0, tool="drill", level=2)),
    ("iron_block", "Iron block", "iron_block", dict(hard=4.5, tool="drill", level=2)),
    ("neon_block", "Neon block", "neon_block", dict(hard=5.0, tool="drill", level=3, light=5)),
    ("magma", "Magma", "magma", dict(shape="liquid", solid=False, opaque=True, hard=None, light=11, hurts=15)),
    ("overload_cell", "Overload Cell", ("overload_top", "overload_side", "overload_bottom"),
     dict(hard=0.3, use="overload", light=3)),
    ("dock", "Bot dock", ("dock_top", "dock_side", "dock_top"), dict(hard=2.0, tool="drill", use="dock", light=5)),
    ("mossy_rubble", "Mossy rubble", "mossy_rubble", dict(hard=2.6, tool="drill", level=1)),
    ("pine_log", "Pine log", ("pine_top", "pine_side", "pine_top"), dict(hard=2.0, tool="cutter")),
    ("pine_leaves", "Pine needles", "pine_leaves", dict(hard=0.3, tool="cutter", opaque=False, see="cutout", drops=None)),
    ("pale_log", "Pale log", ("pale_top", "pale_side", "pale_top"), dict(hard=2.0, tool="cutter")),
    ("pale_leaves", "Pale leaves", "pale_leaves", dict(hard=0.3, tool="cutter", opaque=False, see="cutout", drops=None)),
    ("pine_boards", "Pine boards", "pine_boards", dict(hard=2.0, tool="cutter")),
    ("window", "Window", "window", dict(hard=0.4, opaque=False, see="cutout", drops=None)),
    ("rubble_step", "Rubble step", "rubble", dict(shape="slab", hard=2.0, tool="drill", level=1, opaque=False)),
    ("board_step", "Board step", "boards", dict(shape="slab", hard=1.5, tool="cutter", opaque=False)),
    ("glitch_rift", "Glitch rift", ("rift_top", "rift_side", "soil"), dict(hard=None, light=6, use="rift", drops=None)),
    ("scrap_pile", "Scrap heap", "scrap_pile", dict(hard=1.8, tool="drill", drops=("scrap", 2))),
    ("rust_pile", "Rust heap", "rust_pile", dict(hard=1.8, tool="drill", drops=("rust", 2))),
    ("dead_rack", "Dead server rack", ("rack_top", "dead_rack", "rack_top"), dict(hard=1.6, tool="cutter", drops=("scrap", 2))),
    ("glowfruit_leaves", "Glowfruit leaves", "glowfruit_leaves", dict(hard=0.3, tool="cutter", opaque=False, see="cutout",
                                                                      drops=None, light=6, use="glowfruit")),
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
AIR, WATER, MAGMA, FLOOR = ID["air"], ID["water"], ID["magma"], ID["lab_floor"]
N_BUILT_IN = len(BLOCKS)
ANIMATED = {"server_rack_0": 4}     # tiles drawn as frames one after another in the atlas (the rack's blinking LEDs)

# ---------- items that are only ever held ----------
ITEM_BASE = 256
TOOL_KINDS = ("drill", "cutter", "scoop", "zapper")   # (a Zapper harms creatures; it digs nothing faster)
TOOL_LEVELS = (("mk1", "Mk1", 1, 2.5, 80, 12), ("mk2", "Mk2", 2, 4.0, 160, 18), ("mk3", "Mk3", 3, 6.0, 320, 24),
               ("mk4", "Mk4", 4, 10.0, 1000, 32))  # (key, word, level, dig speed, uses, a Zapper's harm)
_I = [
    ("rod", "Rod", "rod", {}),
    ("coal", "Coal", "coal", {"fuel": 6}),
    ("copper_ingot", "Copper ingot", "copper_ingot", {}),
    ("iron_ingot", "Iron ingot", "iron_ingot", {}),
    ("neon", "Neon crystal", "neon", {}),
    ("wheat", "Wheat", "wheat", {}),
    ("seed_pack", "Seed pack", "seed_pack", {"plants": "grain"}),
    ("grain_bar", "Grain bar", "grain_bar", {"food": 25}),
    ("apple", "Apple", "apple", {"food": 15}),
    ("berries", "Berries", "berries", {"food": 8}),
    ("baked_root", "Baked root", "baked_root", {"food": 30}),
    ("root", "Root", "root", {"food": 5}),
    ("clay_ball", "Clay ball", "clay_ball", {}),
    ("brick_item", "Brick", "brick_item", {}),
    ("scrap", "Scrap", "scrap", {}),
    ("glitch_shard", "Glitch shard", "glitch_shard", {}),
    ("rust", "Rust", "rust", {}),
    ("canister", "Canister", "canister", {"stack": 10}),
    ("water_canister", "Water canister", "water_canister", {"places": "water", "stack": 1}),
    ("bot_kit", "Bot kit", "bot_kit", {"stack": 1}),
    ("charcoal", "Charcoal", "charcoal", {"fuel": 6}),
    ("battery", "Battery", "battery", {"fuel": 12}),
    ("patch", "Patch", "patch", {}),
    ("glowfruit", "Glowfruit", "glowfruit", {"food": 10, "glow": 6}),
]
ITEMS = {}          # id -> the item's dict (blocks included, as items: their block's key, name and first tile)
ITEM_ID = {}        # key -> id
for b in BLOCKS:
    if b["id"]:
        ITEMS[b["id"]] = {"id": b["id"], "key": b["key"], "name": b["name"], "icon": b["tiles"][1] if b["tiles"] else None,
                          "block": b["id"], "stack": STACK}
        ITEM_ID[b["key"]] = b["id"]
_n = ITEM_BASE
for _key, _name, _icon, _extra in _I:
    ITEMS[_n] = dict({"id": _n, "key": _key, "name": _name, "icon": _icon, "block": None, "stack": STACK}, **_extra)
    ITEM_ID[_key] = _n
    _n += 1
for _kind in TOOL_KINDS:
    for _lk, _word, _level, _speed, _uses, _zap in TOOL_LEVELS:
        key = f"{_kind}_{_lk}"
        ITEMS[_n] = {"id": _n, "key": key, "name": f"{_word} {_kind.capitalize()}", "icon": key, "block": None,
                     "stack": 1, "tool": _kind, "level": _level, "speed": _speed if _kind != "zapper" else 1.0,
                     "uses": _uses, "damage": _zap if _kind == "zapper" else 4}
        ITEM_ID[key] = _n
        _n += 1
# the suit: three pieces in four materials, worn in the Backpack's three suit slots (visor, vest, boots). Each piece
# adds Shield: it soaks harm completely until it is empty, then Health takes it; it refills when nothing has hurt you
# for a while. A piece wears a little each time its Shield soaks a hit.
SUIT_PARTS = (("visor", "visor"), ("vest", "vest"), ("boots", "boots"))
SUIT_LEVELS = (("fluff", "Fluff", (4, 8, 3), 60), ("copper", "Copper", (6, 12, 5), 140),
               ("iron", "Iron", (8, 16, 6), 260), ("neon", "Neon", (11, 22, 9), 600))  # (key, word, shield, uses)
SUIT_PARTS_NEEDED = (3, 5, 2)   # (how many of a material each piece is made from)
for _part, (_pk, _pword) in enumerate(SUIT_PARTS):
    for _mk, _word, _shield, _uses in SUIT_LEVELS:
        key = f"{_mk}_{_pk}"
        ITEMS[_n] = {"id": _n, "key": key, "name": f"{_word} {_pword}", "icon": key, "block": None, "stack": 1,
                     "suit": _part, "shield": _shield[_part], "uses": _uses}
        ITEM_ID[key] = _n
        _n += 1
ITEMS[ITEM_ID["bot_kit"]]["stack"] = 1
FOOD = {i: it["food"] for i, it in ITEMS.items() if it.get("food")}
FUEL = {i: it["fuel"] for i, it in ITEMS.items() if it.get("fuel")}   # (a Refinery's power: items it refines)
FUEL.update({ID["log"]: 2, ID["pine_log"]: 2, ID["pale_log"]: 2, ID["boards"]: 1, ID["pine_boards"]: 1})
# what a Refinery makes of what (rust takes two for each ingot: REFINE_TAKES)
REFINES = {ID["copper_ore"]: ITEM_ID["copper_ingot"], ID["iron_ore"]: ITEM_ID["iron_ingot"], ID["neon_ore"]: ITEM_ID["neon"],
           ID["sand"]: ID["glass"], ID["rubble"]: ID["stone"], ID["log"]: ITEM_ID["charcoal"],
           ID["pine_log"]: ITEM_ID["charcoal"], ID["pale_log"]: ITEM_ID["charcoal"],
           ITEM_ID["clay_ball"]: ITEM_ID["brick_item"], ITEM_ID["root"]: ITEM_ID["baked_root"],
           ITEM_ID["rust"]: ITEM_ID["iron_ingot"]}
REFINE_TAKES = {ITEM_ID["rust"]: 2}
REFINE_SECONDS = 6.0    # a Refinery's time for one item
HAND = {"tool": None, "level": 0, "speed": 1.0, "damage": 4}

# ---------- the old names ----------
# (before CHANGE 207: an old mod, brain or save that says one of these gets the new one, and a warning)
ALIASES = {
    "grass": "turf", "planks": "boards", "pine_planks": "pine_boards", "stick": "rod", "workbench": "fabricator",
    "smelter": "refinery", "smelter_lit": "refinery_on", "chest": "locker", "torch": "glowstick",
    "crystal_ore": "neon_ore", "crystal": "neon", "crystal_block": "neon_block", "wool": "fluff",
    "wool_white": "fluff", "wool_red": "fluff_red", "wool_orange": "fluff_red", "wool_yellow": "fluff_yellow",
    "wool_green": "fluff_green", "wool_blue": "fluff_blue", "wool_purple": "fluff_purple", "wool_black": "fluff_black",
    "bed": "pod", "bookshelf": "server_rack", "farmland": "grow_bed", "bread": "grain_bar", "bucket": "canister",
    "water_bucket": "water_canister", "slab": "rubble_step", "plank_slab": "board_step", "stone_bricks": "stone_tiles",
    "corestone": "lab_floor", "blast": "overload_cell", "glass_pane": "window", "wheat_item": "wheat",
    "seeds": "seed_pack", "roast_potato": "baked_root",
}
for _old, _new in (("pick", "drill"), ("axe", "cutter"), ("shovel", "scoop"), ("sword", "zapper")):
    for _mat, _mk in (("wood", "mk1"), ("stone", "mk1"), ("copper", "mk2"), ("iron", "mk3"), ("crystal", "mk4")):
        ALIASES[f"{_mat}_{_old}"] = f"{_new}_{_mk}"
for _mat, _new in (("cloth", "fluff"), ("copper", "copper"), ("iron", "iron"), ("crystal", "neon")):
    for _old, _part in (("helmet", "visor"), ("chest", "vest"), ("boots", "boots")):
        ALIASES[f"{_mat}_{_old}"] = f"{_new}_{_part}"
TOOL_ALIASES = {"pick": "drill", "axe": "cutter", "shovel": "scoop"}
MODE_ALIASES = {"survival": "challenge", "creative": "sandbox"}


def new_key(key):
    """A block's or item's key as it is now: an old one (ALIASES) becomes its new one. Unknown keys are kept."""
    return ALIASES.get(key, key) if isinstance(key, str) and key not in ITEM_ID else key


def mode_of(mode):
    """A game mode as it is now (survival: challenge, creative: sandbox)."""
    return MODE_ALIASES.get(mode, mode)


def block(key_or_id):
    return BLOCKS[key_or_id] if isinstance(key_or_id, int) else BLOCKS[ID[new_key(key_or_id)]]


def item(key_or_id):
    return ITEMS.get(key_or_id if isinstance(key_or_id, int) else ITEM_ID.get(new_key(key_or_id)))


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
    enough = (right and tool.get("level", 0) >= b["level"]) if b["level"] else True
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
             light=min(LIGHT_MAX, spec.get("light", 0)), tool=TOOL_ALIASES.get(spec.get("tool"), spec.get("tool")),
             mod=True, colour=spec.get("colour"))
    b["drops"] = spec["key"]
    BLOCKS.append(b)
    ID[b["key"]] = i
    ITEMS[i] = {"id": i, "key": b["key"], "name": b["name"], "icon": b["tiles"][1], "block": i, "stack": STACK}
    ITEM_ID[b["key"]] = i
    return i
