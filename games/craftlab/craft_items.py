"""Craft Lab's inventories and blueprints (CHANGE 200; blueprints since CHANGE 207).

An inventory is a list of slots; a slot is None or [item id, count, wear] (wear: uses a tool or suit piece has left).
A player carries 38: the Toolbelt along the bottom of the screen (0 to 7, keys 1 to 8) and the Backpack (8 to 37,
6 across and 5 down). A Locker holds 24, a Refinery 17 (an 8-item queue, the power slot, an 8-slot output tray), and
the suit's three slots are worn (visor, vest, boots).

Building works from blueprints: a list of things you can make, each needing named parts in set amounts, as a learner
would write one in mods/blueprints.py:
    {"makes": "locker", "count": 1, "parts": {"boards": 6, "rod": 2}, "seconds": 2, "station": "fabricator"}
station is "hand" (a Quick Build: anywhere, from the Backpack's Blueprints tab) or "fabricator" (within 4 blocks of
one). A part can be a group (any_log: any log; any_boards; any_coal: coal or charcoal; any_fluff: any colour).
A blueprint shows greyed until you have held at least one of each of its parts; then it is unlocked.

Clicking slots works as the Backpack's: a left click picks a whole stack up (or puts the one you hold down, or swaps
them, or adds to a stack of the same thing), a right click splits a stack in half or puts one down, Shift and a
click sends a stack to the other side (Toolbelt <-> Backpack, or into or out of a Locker).
"""
import copy

import craft_blocks as B

I = B.ITEM_ID
GROUPS = {"any_log": ("log", "pine_log", "pale_log"), "any_boards": ("boards", "pine_boards"),
          "any_coal": ("coal", "charcoal"),
          "any_fluff": ("fluff", "fluff_red", "fluff_yellow", "fluff_green", "fluff_blue", "fluff_purple", "fluff_black")}
GROUP_NAMES = {"any_log": "Log (any)", "any_boards": "Boards (any)", "any_coal": "Coal or charcoal",
               "any_fluff": "Fluff (any)"}
CATEGORIES = ("Build", "Tools", "Suit", "Bot", "Food")
REACH = 4.0         # metres from a Fabricator's middle to build its blueprints


def bp(makes, count, parts, station="fabricator", seconds=2, category="Build"):
    return {"makes": makes, "count": count, "parts": parts, "station": station, "seconds": seconds, "category": category}


BLUEPRINTS = [
    bp("boards", 3, {"any_log": 1}, "hand", 1),
    bp("rod", 3, {"any_boards": 1}, "hand", 1),
    bp("glowstick", 2, {"rod": 1, "any_coal": 1}, "hand", 1),
    bp("fabricator", 1, {"any_boards": 6, "rubble": 2}, "hand", 3),
    bp("pine_boards", 3, {"pine_log": 1}, seconds=1),
    bp("refinery", 1, {"rubble": 6, "clay_ball": 3}, seconds=4),
    bp("locker", 1, {"any_boards": 6, "rod": 2}),
    bp("door", 1, {"any_boards": 4, "rod": 1}),
    bp("ladder", 4, {"rod": 5}),
    bp("pod", 1, {"any_fluff": 3, "any_boards": 4, "copper_ingot": 1}, seconds=4),
    bp("server_rack", 1, {"any_boards": 4, "copper_ingot": 2, "glass": 1}, seconds=3),
    bp("window", 4, {"glass": 3}),
    bp("brick", 1, {"brick_item": 3}),
    bp("stone_tiles", 2, {"stone": 3}),
    bp("sandstone", 2, {"sand": 3, "clay_ball": 1}),
    bp("mossy_rubble", 2, {"rubble": 2, "leaves": 1}, seconds=1),
    bp("rubble_step", 4, {"rubble": 2}, seconds=1),
    bp("board_step", 4, {"any_boards": 2}, seconds=1),
    bp("grow_bed", 1, {"any_boards": 2, "soil": 2}),
    bp("lumen", 1, {"glitch_shard": 3, "glass": 1}, seconds=3),
    bp("overload_cell", 1, {"glitch_shard": 2, "battery": 1, "scrap": 2}, seconds=4),
    bp("canister", 1, {"iron_ingot": 2, "glass": 1}, seconds=3, category="Tools"),
    bp("patch", 1, {"battery": 1, "copper_ingot": 2}, seconds=3, category="Tools"),
    bp("battery", 2, {"copper_ingot": 1, "any_coal": 1, "scrap": 1}, seconds=3, category="Bot"),
    bp("bot_kit", 1, {"iron_ingot": 4, "scrap": 2, "battery": 1}, seconds=5, category="Bot"),
    bp("dock", 1, {"copper_ingot": 4, "rubble": 3, "battery": 1}, seconds=5, category="Bot"),
    bp("grain_bar", 2, {"wheat": 2, "berries": 1}, category="Food"),
]
for _colour, _source in (("red", "flower_red"), ("yellow", "flower_yellow"), ("green", "leaves"), ("purple", "berries"),
                         ("black", "coal"), ("blue", "neon")):
    BLUEPRINTS.append(bp(f"fluff_{_colour}", 4, {"fluff": 4, _source: 1}))
for _metal, _ingot in (("copper", "copper_ingot"), ("iron", "iron_ingot"), ("neon", "neon")):
    BLUEPRINTS.append(bp(f"{_metal}_block", 1, {_ingot: 6}))
    BLUEPRINTS.append(bp(_ingot, 6, {f"{_metal}_block": 1}, seconds=1))
for _kind, _parts in (("drill", {"rubble": 3, "rod": 2}), ("cutter", {"rubble": 2, "rod": 2}),
                      ("scoop", {"rubble": 1, "rod": 2}), ("zapper", {"rubble": 1, "rod": 1, "any_coal": 1})):
    BLUEPRINTS.append(bp(f"{_kind}_mk1", 1, _parts, seconds=3, category="Tools"))
    for _was, _mk, _more, _secs in (("mk1", "mk2", {"copper_ingot": 3}, 4), ("mk2", "mk3", {"iron_ingot": 3}, 5),
                                    ("mk3", "mk4", {"neon": 3, "battery": 1}, 6)):  # (upgrades: the old tool and parts)
        BLUEPRINTS.append(bp(f"{_kind}_{_mk}", 1, dict({f"{_kind}_{_was}": 1}, **_more), seconds=_secs, category="Tools"))
for _part, (_pk, _) in enumerate(B.SUIT_PARTS):
    _n = B.SUIT_PARTS_NEEDED[_part]
    BLUEPRINTS.append(bp(f"fluff_{_pk}", 1, {"any_fluff": _n}, seconds=3, category="Suit"))
    for _was, _mat, _with in (("fluff", "copper", "copper_ingot"), ("copper", "iron", "iron_ingot"), ("iron", "neon", "neon")):
        BLUEPRINTS.append(bp(f"{_mat}_{_pk}", 1, {f"{_was}_{_pk}": 1, _with: _n}, seconds=4, category="Suit"))

SLOTS = 38          # the Toolbelt (0 to 7) and the Backpack (8 to 37)
TOOLBELT = 8
BACKPACK_W = 6
LOCKER = 24
SUIT = 3            # the suit's slots: visor, vest, boots
QUEUE, TRAY = 8, 8  # a Refinery's input queue and output tray (its power slot is between them: slot 8)
POWER_SLOT = QUEUE
REFINERY = QUEUE + 1 + TRAY
MAX_BUILDS = 5      # blueprints waiting to build at once


def ids(part):
    """A part's key (an item's key or a group's) as a set of item ids."""
    names = GROUPS.get(part, (B.new_key(part),))
    return {I[n] for n in names if n in I}


def part_name(part):
    return GROUP_NAMES.get(part) or B.name_of(I.get(B.new_key(part)))


def checked(blueprints):
    """Blueprints as the game uses them: only those that make a real thing, from real parts (a mod's checked first)."""
    out = []
    for r in blueprints:
        if not isinstance(r, dict) or B.new_key(r.get("makes")) not in I:
            continue
        parts = {}
        for k, n in (r.get("parts") or {}).items():
            if (k in GROUPS or B.new_key(k) in I) and isinstance(n, int) and n > 0:
                parts[k if k in GROUPS else B.new_key(k)] = n
        if not parts:
            continue
        out.append(dict(r, makes=B.new_key(r["makes"]), parts=parts, count=int(r.get("count", 1)),
                        seconds=float(r.get("seconds", 2)), station=r.get("station", "fabricator"),
                        category=r.get("category", "Build")))
    return out


_ALL = None


def blueprints():
    """Every blueprint in the game now (the built-in ones and the mods'), in order: a blueprint's number is its index."""
    global _ALL
    if _ALL is None:
        _ALL = checked(BLUEPRINTS)
    return _ALL


def blueprints_changed(extra=()):
    """The mods' blueprints added after the built-in ones."""
    global _ALL
    _ALL = checked(BLUEPRINTS) + checked(list(extra))


def have(inv, part):
    want = ids(part)
    return sum(s[1] for s in inv if s and s[0] in want)


def missing(inv, blueprint):
    """The parts a blueprint needs that the inventory hasn't enough of: {part: how many more}."""
    return {k: n - have(inv, k) for k, n in blueprint["parts"].items() if have(inv, k) < n}


def can_build(inv, blueprint):
    return not missing(inv, blueprint)


def take_parts(inv, blueprint):
    """Take a blueprint's parts out of the inventory (all of them, or none). Returns True if it had them."""
    if not can_build(inv, blueprint):
        return False
    for part, n in blueprint["parts"].items():
        want = ids(part)
        for i, s in enumerate(inv):
            if n and s and s[0] in want:
                t = min(n, s[1])
                s[1] -= t
                n -= t
                if s[1] <= 0:
                    inv[i] = None
    return True


def unlocked(blueprint, seen):
    """Has the player held at least one of each part (seen: the item ids they have ever held)?"""
    return all(ids(part) & seen for part in blueprint["parts"])


def stack_max(item_id):
    return B.ITEMS.get(item_id, {}).get("stack", B.STACK)


def new_slot(item_id, count=1):
    it = B.ITEMS.get(item_id, {})
    return [item_id, count, it.get("uses", 0)]


def add(inv, item_id, count=1, order=None, wear=None):
    """Put count of an item in (onto stacks of it first, then empty slots, the Toolbelt first). Returns how many
    didn't fit. wear: the uses a tool or suit piece moved from elsewhere has left (else a new one's)."""
    order = order or range(len(inv))
    mx = stack_max(item_id)
    for i in order:
        s = inv[i]
        if s and s[0] == item_id and s[1] < mx and mx > 1:
            put = min(count, mx - s[1])
            s[1] += put
            count -= put
            if not count:
                return 0
    for i in order:
        if inv[i] is None:
            put = min(count, mx)
            inv[i] = new_slot(item_id, put)
            if wear is not None and inv[i][2]:
                inv[i][2] = wear
            count -= put
            if not count:
                return 0
    return count


def count_of(inv, item_id):
    return sum(s[1] for s in inv if s and s[0] == item_id)


def take(inv, item_id, count=1):
    """Take count of an item out (from anywhere). Returns True if there were enough."""
    if count_of(inv, item_id) < count:
        return False
    for i, s in enumerate(inv):
        if s and s[0] == item_id:
            t = min(count, s[1])
            s[1] -= t
            count -= t
            if s[1] <= 0:
                inv[i] = None
            if not count:
                return True
    return True


def use_up(inv, i, n=1):
    """n of the stack in slot i used (placed, eaten)."""
    s = inv[i]
    if s:
        s[1] -= n
        if s[1] <= 0:
            inv[i] = None


def suit_part(item_id):
    """Which suit slot an item goes in (0 visor, 1 vest, 2 boots), or None if it isn't a suit piece."""
    return B.ITEMS.get(item_id, {}).get("suit") if item_id is not None else None


def shield_of(worn):
    """The Shield the suit worn gives (a list of three slots): 0 to 42."""
    return sum(B.ITEMS.get(s[0], {}).get("shield", 0) for s in worn if s)


def wear(inv, i):
    """A tool (or a suit piece) in slot i used once: it wears out (and breaks when its uses are gone). Returns True if
    it broke."""
    s = inv[i]
    if not s or not (B.ITEMS.get(s[0], {}).get("tool") or suit_part(s[0]) is not None):
        return False
    s[2] -= 1
    if s[2] <= 0:
        inv[i] = None
        return True
    return False


def click(slots, i, cursor, right=False, takes_only=False):
    """A click on slots[i] with cursor (the stack you hold, or None). Returns the new cursor. takes_only: a slot you
    can only take from (a Refinery's tray)."""
    s = slots[i]
    if cursor is None:
        if s is None:
            return None
        if right and s[1] > 1:
            half = (s[1] + 1) // 2
            s[1] -= half
            return [s[0], half, s[2]]
        slots[i] = None
        return s
    if takes_only:
        if s and s[0] == cursor[0] and cursor[1] + s[1] <= stack_max(s[0]):
            cursor[1] += s[1]
            slots[i] = None
        return cursor
    if s is None:
        if right:
            slots[i] = [cursor[0], 1, cursor[2]]
            cursor[1] -= 1
            return cursor if cursor[1] > 0 else None
        slots[i] = cursor
        return None
    if s[0] == cursor[0] and stack_max(s[0]) > 1:
        room = stack_max(s[0]) - s[1]
        put = min(room, 1 if right else cursor[1])
        s[1] += put
        cursor[1] -= put
        return cursor if cursor[1] > 0 else None
    slots[i] = cursor
    return s


def sort(slots, start=0):
    """The slots from start on tidied: stacks of a kind joined, in the order of their ids, the gaps at the end."""
    stuff = [s for s in slots[start:] if s]
    out = []
    for s in sorted(stuff, key=lambda s: (s[0], -s[2])):
        mx = stack_max(s[0])
        last = out[-1] if out else None
        if last and last[0] == s[0] and mx > 1 and last[1] < mx:
            put = min(mx - last[1], s[1])
            last[1] += put
            s = [s[0], s[1] - put, s[2]]
            if s[1] <= 0:
                continue
        out.append(list(s))
    slots[start:] = out + [None] * (len(slots) - start - len(out))


def snapshot(slots):
    return copy.deepcopy(slots)
