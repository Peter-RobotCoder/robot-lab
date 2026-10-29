"""Craft Lab's inventories and crafting (CHANGE 200).

An inventory is a list of slots; a slot is None or [item id, count, wear] (wear: uses a tool has left). A player has
36 (0 to 8 the hotbar along the bottom of the screen), a chest 27, a smelter 3 (what to smelt, the fuel, what it
made), the crafting grid 4 (in your inventory) or 9 (at a workbench).

A recipe is a pattern of letters and what each letter means, as a learner would write one in mods/recipes.py:
    {"makes": "workbench", "count": 1, "pattern": ["PP", "PP"], "key": {"P": "planks"}}
or no pattern, just the things that go in, in any places:
    {"makes": "planks", "count": 4, "takes": ["log"]}
A pattern matches anywhere in the grid, and mirrored. A letter's key can be one item or a list of items that will
all do (any planks).

Clicking slots works as the inventory screens of block games do: a left click picks a whole stack up (or puts the one
you hold down, or swaps them, or adds to a stack of the same thing), a right click picks half up or puts one down,
shift and a click moves a stack across (hotbar <-> the rest, or into or out of a chest).
"""
import copy

import craft_blocks as B

I = B.ITEM_ID
PLANKS = ["planks", "pine_planks"]
LOGS = ["log", "pine_log", "pale_log"]

RECIPES = [
    {"makes": "planks", "count": 4, "takes": ["log"]},
    {"makes": "planks", "count": 4, "takes": ["pale_log"]},
    {"makes": "pine_planks", "count": 4, "takes": ["pine_log"]},
    {"makes": "stick", "count": 4, "pattern": ["P", "P"], "key": {"P": PLANKS}},
    {"makes": "workbench", "count": 1, "pattern": ["PP", "PP"], "key": {"P": PLANKS}},
    {"makes": "smelter", "count": 1, "pattern": ["RRR", "R.R", "RRR"], "key": {"R": "rubble"}},
    {"makes": "chest", "count": 1, "pattern": ["PPP", "P.P", "PPP"], "key": {"P": PLANKS}},
    {"makes": "torch", "count": 4, "pattern": ["C", "S"], "key": {"C": ["coal", "charcoal"], "S": "stick"}},
    {"makes": "glass_pane", "count": 6, "pattern": ["GGG", "GGG"], "key": {"G": "glass"}},
    {"makes": "brick", "count": 1, "pattern": ["BB", "BB"], "key": {"B": "brick_item"}},
    {"makes": "stone_bricks", "count": 4, "pattern": ["SS", "SS"], "key": {"S": "stone"}},
    {"makes": "door", "count": 3, "pattern": ["PP", "PP", "PP"], "key": {"P": PLANKS}},
    {"makes": "ladder", "count": 3, "pattern": ["S.S", "SSS", "S.S"], "key": {"S": "stick"}},
    {"makes": "bed", "count": 1, "pattern": ["WWW", "PPP"],
     "key": {"W": ["wool", "wool_red", "wool_orange", "wool_yellow", "wool_green", "wool_blue", "wool_purple",
                   "wool_black"], "P": PLANKS}},
    {"makes": "bookshelf", "count": 1, "pattern": ["PPP", "WWW", "PPP"], "key": {"P": PLANKS, "W": "wheat_item"}},
    {"makes": "slab", "count": 6, "pattern": ["RRR"], "key": {"R": "rubble"}},
    {"makes": "plank_slab", "count": 6, "pattern": ["PPP"], "key": {"P": PLANKS}},
    {"makes": "bread", "count": 1, "pattern": ["WWW"], "key": {"W": "wheat_item"}},
    {"makes": "bucket", "count": 1, "pattern": ["I.I", ".I."], "key": {"I": "iron_ingot"}},
    {"makes": "lumen", "count": 1, "pattern": ["GG", "GG"], "key": {"G": "glitch_shard"}},
    {"makes": "copper_block", "count": 1, "pattern": ["III", "III", "III"], "key": {"I": "copper_ingot"}},
    {"makes": "iron_block", "count": 1, "pattern": ["III", "III", "III"], "key": {"I": "iron_ingot"}},
    {"makes": "crystal_block", "count": 1, "pattern": ["CCC", "CCC", "CCC"], "key": {"C": "crystal"}},
    {"makes": "copper_ingot", "count": 9, "takes": ["copper_block"]},
    {"makes": "iron_ingot", "count": 9, "takes": ["iron_block"]},
    {"makes": "crystal", "count": 9, "takes": ["crystal_block"]},
    {"makes": "sandstone", "count": 1, "pattern": ["SS", "SS"], "key": {"S": "sand"}},
    {"makes": "mossy_rubble", "count": 1, "takes": ["rubble", "leaves"]},
    {"makes": "wool_red", "count": 1, "takes": ["wool", "flower_red"]},
    {"makes": "wool_yellow", "count": 1, "takes": ["wool", "flower_yellow"]},
    {"makes": "wool_orange", "count": 2, "takes": ["wool", "wool", "flower_red", "flower_yellow"]},
    {"makes": "wool_green", "count": 1, "takes": ["wool", "leaves"]},
    {"makes": "wool_blue", "count": 1, "takes": ["wool", "crystal"]},
    {"makes": "wool_purple", "count": 1, "takes": ["wool", "berries"]},
    {"makes": "wool_black", "count": 1, "takes": ["wool", "coal"]},
    {"makes": "blast", "count": 1, "pattern": ["SGS", "GSG", "SGS"], "key": {"S": "sand", "G": "glitch_shard"}},
    {"makes": "bot_kit", "count": 1, "pattern": ["III", "ISI", "III"], "key": {"I": "iron_ingot", "S": "scrap"}},
    {"makes": "dock", "count": 1, "pattern": ["CCC", "C.C", "RRR"], "key": {"C": "copper_ingot", "R": "rubble"}},
]
for _kind, _pattern in (("pick", ["MMM", ".S.", ".S."]), ("axe", ["MM", "MS", ".S"]), ("shovel", ["M", "S", "S"]),
                        ("sword", ["M", "M", "S"]), ("hoe", ["MM", ".S", ".S"])):
    for _mat, _what in (("wood", PLANKS), ("stone", ["rubble"]), ("copper", ["copper_ingot"]), ("iron", ["iron_ingot"]),
                        ("crystal", ["crystal"])):
        RECIPES.append({"makes": f"{_mat}_{_kind}", "count": 1, "pattern": _pattern, "key": {"M": _what, "S": "stick"}})

WOOLS = ["wool", "wool_red", "wool_orange", "wool_yellow", "wool_green", "wool_blue", "wool_purple", "wool_black"]
for _part, _pattern in (("helmet", ["MMM", "M.M"]), ("chest", ["M.M", "MMM", "MMM"]), ("legs", ["MMM", "M.M", "M.M"]),
                        ("boots", ["M.M", "M.M"])):
    for _mat, _what in (("cloth", WOOLS), ("copper", ["copper_ingot"]), ("iron", ["iron_ingot"]), ("crystal", ["crystal"])):
        RECIPES.append({"makes": f"{_mat}_{_part}", "count": 1, "pattern": _pattern, "key": {"M": _what}})

SLOTS = 36
HOTBAR = 9
CHEST = 27
ARMOUR = 4      # the armour slots: head, chest, legs, feet


def ids(what):
    """A recipe's key entry (an item's key, or a list of them) as a set of item ids."""
    names = what if isinstance(what, list) else [what]
    return {I[n] for n in names if n in I}


def compiled(recipes=None):
    """The recipes as the matcher reads them: (shape (rows of item-id sets or None), result id, count) for patterns,
    (sorted list of item-id sets, result id, count) for the shapeless ones."""
    shaped, shapeless = [], []
    for r in recipes if recipes is not None else RECIPES:
        if r.get("makes") not in I:
            continue
        out = (I[r["makes"]], int(r.get("count", 1)))
        if "pattern" in r:
            rows = [[None if ch in ". " else ids(r["key"][ch]) for ch in line] for line in r["pattern"]]
            shaped.append((rows,) + out)
        else:
            shapeless.append(([ids(t) for t in r["takes"]],) + out)
    return shaped, shapeless


_COMPILED = None


def recipes_changed(recipes=None):
    global _COMPILED
    _COMPILED = compiled(recipes)


def trim(grid, w):
    """The grid's items (a list, w across) cut down to the smallest box round them: rows of item ids (0 = empty)."""
    rows = [[(grid[r * w + c] or [0])[0] for c in range(w)] for r in range(len(grid) // w)]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    cols = [c for c in range(w) if any(r[c] for r in rows)]
    return [r[cols[0]:cols[-1] + 1] for r in rows]


def match(grid, w):
    """What the crafting grid makes: (item id, count) or None."""
    if _COMPILED is None:
        recipes_changed()
    shaped, shapeless = _COMPILED
    t = trim(grid, w)
    if not t:
        return None
    for rows, out, n in shaped:
        if len(rows) != len(t) or len(rows[0]) != len(t[0]) or any(len(r) != len(rows[0]) for r in rows):
            continue
        for mirror in (False, True):
            ok = True
            for pr, gr in zip(rows, t):
                pr = pr[::-1] if mirror else pr
                for want, got in zip(pr, gr):
                    if (want is None) != (got == 0) or (want is not None and got not in want):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                return out, n
    have = sorted(i for r in t for i in r if i)
    for takes, out, n in shapeless:
        if len(takes) != len(have):
            continue
        left = list(have)
        ok = True
        for want in takes:
            hit = next((x for x in left if x in want), None)
            if hit is None:
                ok = False
                break
            left.remove(hit)
        if ok:
            return out, n
    return None


def craft_once(grid, w):
    """Make the grid's recipe once: one of everything in the grid used up. Returns the (item id, count) made."""
    got = match(grid, w)
    if got is None:
        return None
    for i, s in enumerate(grid):
        if s:
            s[1] -= 1
            if s[1] <= 0:
                grid[i] = None
    return got


def stack_max(item_id):
    return B.ITEMS.get(item_id, {}).get("stack", 64)


def new_slot(item_id, count=1):
    it = B.ITEMS.get(item_id, {})
    return [item_id, count, it.get("uses", 0)]


def add(inv, item_id, count=1, order=None, wear=None):
    """Put count of an item in (onto stacks of it first, then empty slots, the hotbar first). Returns how many
    didn't fit. wear: the uses a tool or piece of armour moved from elsewhere has left (else a new one's)."""
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


def armour_part(item_id):
    """Which armour slot an item goes in (0 head, 1 chest, 2 legs, 3 feet), or None if it isn't armour."""
    return B.ITEMS.get(item_id, {}).get("armour") if item_id is not None else None


def armour_points(worn):
    """The points of the armour worn (a list of four slots): 0 to 20."""
    return sum(B.ITEMS.get(s[0], {}).get("points", 0) for s in worn if s)


def wear(inv, i):
    """A tool (or a piece of armour) in slot i used once: it wears out (and breaks when its uses are gone). Returns
    True if it broke."""
    s = inv[i]
    if not s or not (B.ITEMS.get(s[0], {}).get("tool") or armour_part(s[0]) is not None):
        return False
    s[2] -= 1
    if s[2] <= 0:
        inv[i] = None
        return True
    return False


def click(slots, i, cursor, right=False, takes_only=False):
    """A click on slots[i] with cursor (the stack you hold, or None). Returns the new cursor. takes_only: a slot you
    can only take from (a smelter's output)."""
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


def snapshot(slots):
    return copy.deepcopy(slots)
