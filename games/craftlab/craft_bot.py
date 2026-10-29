"""Craft Bots (CHANGE 200): each learner's own little robot helper, driven by their Python (brains/my_bot.py).

Put a BOT DOCK down (a Fabricator blueprint: copper, rubble and a Battery, or given by the teacher) and right-click
it: your Bot rolls out on top, and the Backpack's Bot tab shows what it carries (give it blocks to build with; take
what it dug). Upload your brain (U)
and switch autopilot on (P): from then on the Bot asks your brain(bot, world) what to do next, does it, and asks
again. A Bot hovers (it never falls), moves one block at a time, turns, digs the block in front, above or below
(what it digs goes in its own 9 slots) and puts blocks down from them. How fast it digs, builds and moves is your
design's points (craft_design.py: dig, build, speed).

    brain(bot, world) returns one of:
        "forward"  "back"  "up"  "down"             move one block (not into a solid block)
        "left"  "right"                             turn a quarter
        "dig"  "dig_up"  "dig_down"                 dig the block in front, above or below
        ("place", "boards")  ("place_up", ...)  ("place_down", ...)     put a block it carries there
        ("use", "overload_cell")                   arm the Overload Cell in front of it (when the lesson allows them)
        "wait"                                      do nothing for half a second
        ("say", "Hello!")                           a speech bubble over the Bot

A Bot can't dig the Lab floor, a Glitch rift or a Bot's dock, can't put a block where someone stands, and does nothing at all
while its brain has an error (the error and the line go back to its owner).
"""
import math

import craft_blocks as B
import craft_design as design
import craft_items as items
import craft_sim as sim

I, ID = B.ITEM_ID, B.ID
BOT_BASE = 64     # a player's Bot's id: 64 + the player's (on the wire, one byte)
SLOTS = 9
FACING = ("east", "north", "west", "south")
DXY = ((1, 0), (0, 1), (-1, 0), (0, -1))
TURN_TIME, WAIT_TIME, BUMP_TIME = 0.25, 0.5, 0.3
SEE = 4


class Bot:
    def __init__(self, game, bid, owner, dock):
        self.game, self.id, self.owner = game, bid, owner
        self.dock = tuple(dock)
        self.cell = [dock[0], dock[1], dock[2] + 1]
        self.facing = 0
        self.inv = [None] * SLOTS
        self.brain = None          # the teaching layer's (or the offline window's) Autopilot, while autopilot is on
        self.action = None         # [kind, seconds left, seconds in all, data]
        self.stats = {"dug": 0, "placed": 0, "moves": 0, "turns": 0, "said": 0, "errors": 0}
        self.bubble = ""
        self.state = sim.new_player(self.cell[0] + 0.5, self.cell[1] + 0.5, float(self.cell[2]), sim.KINDS["bot"])
        self.state["hp"] = 20
        self.from_pos = None
        self.last_error = None

    # ---------- what it sees ----------
    def look_at(self, d):
        x, y, z = self.cell
        fx, fy = DXY[d % 4]
        return x + fx, y + fy, z

    def name_at(self, x, y, z):
        w = self.game.world
        if not w.inside(x, y, z):
            return "edge"
        return B.BLOCKS[w.get(x, y, z)]["key"]

    def bot_data(self):
        x, y, z = self.cell
        p = self.game.players.get(self.owner)
        inv = {}
        for s in self.inv:
            if s:
                key = B.ITEMS[s[0]]["key"]
                inv[key] = inv.get(key, 0) + s[1]
        return {"x": x, "y": y, "z": z, "facing": FACING[self.facing], "front": self.name_at(*self.look_at(self.facing)),
                "behind": self.name_at(*self.look_at(self.facing + 2)),
                "left_side": self.name_at(*self.look_at(self.facing + 1)),
                "right_side": self.name_at(*self.look_at(self.facing + 3)),
                "above": self.name_at(x, y, z + 1), "below": self.name_at(x, y, z - 1), "inventory": inv,
                "carrying": sum(inv.values()), "full": all(self.inv), "dug": self.stats["dug"],
                "placed": self.stats["placed"], "moves": self.stats["moves"],
                "owner_x": round(p.state["x"], 1) if p else x, "owner_y": round(p.state["y"], 1) if p else y,
                "owner_z": round(p.state["z"], 1) if p else z,
                "home_x": self.dock[0], "home_y": self.dock[1], "home_z": self.dock[2] + 1}

    def world_data(self):
        """The 9 x 9 x 9 blocks round the Bot, as one string (a letter a block, its name in the list)."""
        x0, y0, z0 = self.cell
        names, index, chars = [], {}, []
        for dx in range(-SEE, SEE + 1):
            for dy in range(-SEE, SEE + 1):
                for dz in range(-SEE, SEE + 1):
                    key = self.name_at(x0 + dx, y0 + dy, z0 + dz)
                    if key not in index:
                        index[key] = len(names)
                        names.append(key)
                    chars.append(chr(48 + index[key]))
        return {"day": not self.game.is_night(), "time": round(self.game.day_t, 3), "r": SEE, "names": names,
                "grid": "".join(chars)}

    # ---------- the step ----------
    def step(self, dt):
        if self.action is not None:
            self.action[1] -= dt
            self.animate()
            if self.action[1] <= 0:
                self.finish()
            return
        self.settle()
        brain = self.brain
        if brain is None:
            return
        if brain.error:
            if brain.error != self.last_error:
                self.last_error = brain.error
                self.stats["errors"] += 1
                self.game.say(self.owner, f"Your Craft Bot's brain stopped: {brain.error}")
            return
        if not brain.waiting():
            brain.ask(self.bot_data(), self.world_data(), self.game.tick * sim.STEP)
            return
        answer = brain.answer()
        if answer is not None:
            self.start(answer[0], answer[1])

    def stats_now(self):
        p = self.game.designs.get(self.owner) if hasattr(self.game, "designs") else None
        return design.stats_of(p or design.default_design())

    def start(self, kind, extra=""):
        """Begin an action (checked now: a move into a solid block bumps, a dig of nothing or a placement with
        nothing to place waits)."""
        st = self.stats_now()
        w = self.game.world
        x, y, z = self.cell
        solid, _, _ = sim.tables()
        if kind in ("forward", "back", "up", "down"):
            if kind in ("forward", "back"):
                fx, fy = DXY[(self.facing + (0 if kind == "forward" else 2)) % 4]
                to = (x + fx, y + fy, z)
            else:
                to = (x, y, z + (1 if kind == "up" else -1))
            if not w.inside(*to) or solid[w.get(*to)] or self.game.mobs.box_hit(*to):
                self.action = ["bump", BUMP_TIME, BUMP_TIME, None]
                return
            self.from_pos = (x + 0.5, y + 0.5, float(z))
            self.action = [kind, st["move"], st["move"], to]
        elif kind in ("left", "right"):
            self.from_pos = None
            self.action = [kind, TURN_TIME, TURN_TIME, None]
        elif kind in ("dig", "dig_up", "dig_down"):
            to = self.look_at(self.facing) if kind == "dig" else (x, y, z + (1 if kind == "dig_up" else -1))
            bid = w.get(*to)
            b = B.BLOCKS[bid]
            if not bid or bid == ID["water"] or b["hard"] is None or bid == ID["dock"] or not w.inside(*to):
                self.action = ["wait", WAIT_TIME, WAIT_TIME, None]
                return
            secs = max(0.2, st["dig"] * max(0.4, b["hard"]))
            self.action = ["dig", secs, secs, to]
        elif kind in ("place", "place_up", "place_down"):
            to = self.look_at(self.facing) if kind == "place" else (x, y, z + (1 if kind == "place_up" else -1))
            key = B.new_key(str(extra).strip().lower().replace(" ", "_"))
            item = I.get(key)
            slot = next((i for i, s in enumerate(self.inv) if s and s[0] == item), None)
            if item is None or slot is None or B.ITEMS[item].get("block") is None:
                self.game.events.append(("bubble", self.id, f"I have no {key or 'blocks'} to place"))
                self.action = ["wait", WAIT_TIME, WAIT_TIME, None]
                return
            here = w.get(*to)
            if not w.inside(*to) or here not in (0, ID["water"], ID["tall_grass"]) or \
                    any(sim.player_box_hits(q.state, *to) for q in self.game.players.values()):
                self.action = ["bump", BUMP_TIME, BUMP_TIME, None]
                return
            self.action = ["place", st["build"], st["build"], (to, item, slot)]
        elif kind == "use":  # (the block in front: an Overload Cell is armed)
            to = self.look_at(self.facing)
            if w.get(*to) == ID["overload_cell"] and self.game.arm(*to, who=self.owner):
                self.note("bot_armed", "overload_cell")
                self.action = ["wait", 0.8, 0.8, None]
            else:
                self.game.events.append(("bubble", self.id, "Nothing to use there"))
                self.action = ["wait", WAIT_TIME, WAIT_TIME, None]
        elif kind == "say":
            self.bubble = str(extra)[:40]
            self.stats["said"] += 1
            self.game.events.append(("bubble", self.id, self.bubble))
            self.action = ["wait", 0.8, 0.8, None]
        else:
            self.action = ["wait", WAIT_TIME, WAIT_TIME, None]

    def animate(self):
        """Its record (as everyone sees it) part way through a move, a turn, a bump."""
        kind, left, total, data = self.action
        k = 1.0 - max(0.0, left) / total if total else 1.0
        e = k * k * (3 - 2 * k)
        s = self.state
        if kind in ("forward", "back", "up", "down") and self.from_pos:
            fx, fy, fz = self.from_pos
            tx, ty, tz = data[0] + 0.5, data[1] + 0.5, float(data[2])
            s["x"], s["y"], s["z"] = fx + (tx - fx) * e, fy + (ty - fy) * e, fz + (tz - fz) * e
            s["vx"], s["vy"] = (tx - fx) / total, (ty - fy) / total
        elif kind in ("left", "right"):
            turn = 90.0 if kind == "left" else -90.0
            s["yaw"] = (self.facing * 90.0 + turn * e) % 360
        elif kind == "dig":
            s["flags"] |= sim.F_SWING
        elif kind == "bump":
            fx, fy = DXY[self.facing]
            bump = math.sin(math.pi * k) * 0.15
            s["x"], s["y"] = self.cell[0] + 0.5 + fx * bump, self.cell[1] + 0.5 + fy * bump

    def finish(self):
        kind, _, _, data = self.action
        self.action = None
        g = self.game
        w = g.world
        if kind in ("forward", "back", "up", "down"):
            self.cell = list(data)
            self.stats["moves"] += 1
        elif kind in ("left", "right"):
            self.facing = (self.facing + (1 if kind == "left" else 3)) % 4
            self.stats["turns"] += 1
        elif kind == "dig":
            bid = w.get(*data)
            if bid and B.BLOCKS[bid]["hard"] is not None:
                b = B.BLOCKS[bid]
                w.set(*data, 0)
                g.burst(*data, b["tiles"][1] if b["tiles"] else "particle")
                g.sound("dig_" + (b["tool"] or "soft"), data[0] + 0.5, data[1] + 0.5, data[2] + 0.5)
                for item_id, n in g.drops(bid, 0, True):
                    left = items.add(self.inv, item_id, n)
                    if left:
                        g.drop(item_id, left, data[0] + 0.5, data[1] + 0.5, data[2] + 0.5)
                self.stats["dug"] += 1
                g.after_change(*data)
                self.note("bot_dug", b["key"])
                if b["key"].endswith("_ore"):
                    self.note("bot_ore", b["key"])
        elif kind == "place":
            (to, item, slot) = data
            s = self.inv[slot]
            if s and s[0] == item and w.get(*to) in (0, ID["water"], ID["tall_grass"]):
                w.set(*to, B.ITEMS[item]["block"])
                items.use_up(self.inv, slot)
                g.sound("place", to[0] + 0.5, to[1] + 0.5, to[2] + 0.5)
                self.stats["placed"] += 1
                g.after_change(*to)
                self.note("bot_placed", B.ITEMS[item]["key"])
        self.settle()
        g.events.append(("box", ("bot", self.id)))

    def settle(self):
        s = self.state
        s["x"], s["y"], s["z"] = self.cell[0] + 0.5, self.cell[1] + 0.5, float(self.cell[2])
        s["vx"] = s["vy"] = s["vz"] = 0.0
        s["yaw"] = self.facing * 90.0
        s["flags"] &= ~sim.F_SWING

    def note(self, what, detail):
        p = self.game.players.get(self.owner)
        if p is not None:
            p.stats["bot"][what] = p.stats["bot"].get(what, 0) + 1
        self.game.notes.append((self.owner, what, detail))

    def home(self):
        """Back to its dock (the dock used again, or the Bot kit)."""
        self.action = None
        self.cell = [self.dock[0], self.dock[1], self.dock[2] + 1]
        self.settle()

    def to_save(self):
        return {"dock": list(self.dock), "cell": self.cell, "facing": self.facing, "inv": self.inv, "stats": self.stats}

    def load(self, saved):
        try:
            self.cell = [int(v) for v in saved.get("cell", self.cell)][:3]
            self.facing = int(saved.get("facing", 0)) % 4
            inv = saved.get("inv")
            if isinstance(inv, list) and len(inv) == SLOTS:
                self.inv = [s if isinstance(s, list) and len(s) == 3 and s[0] in B.ITEMS else None for s in inv]
            self.stats.update({k: int(v) for k, v in (saved.get("stats") or {}).items() if k in self.stats})
        except (TypeError, ValueError):
            pass
        self.settle()


STARTER = '''"""My Craft Bot's brain. The Bot asks brain(bot, world) what to do next, does it, and asks again.

Press U in the game to upload this file, and P to switch the autopilot on (P again stops it).

What the Bot can see:
    bot.front, bot.above, bot.below, bot.behind, bot.left_side, bot.right_side   the blocks round it ("air", "log"...)
    bot.facing ("east", "north", "west", "south")    bot.x, bot.y, bot.z    bot.inventory   bot.has("boards")
    bot.dug, bot.placed, bot.moves                   how much it has done
    bot.memory                                       a dictionary it keeps between turns
    world.block(dx, dy, dz)    world.find("coal_ore")    world.day
What it can do (return one):
    "forward" "back" "up" "down" "left" "right" "dig" "dig_up" "dig_down" "wait"
    ("place", "boards")  ("place_up", "glowstick")  ("place_down", "rubble")  ("say", "Hello!")
    ("use", "overload_cell")                         arm the Overload Cell in front (if the lesson allows them)
"""


def brain(bot, world):
    # A tunnel: dig the block in front, then move into the gap. Ten blocks, then stop and say so.
    if bot.dug >= 10:
        return ("say", "Tunnel done!")
    if bot.front != "air":
        return "dig"
    return "forward"
'''
