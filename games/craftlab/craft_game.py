"""Craft Lab's rules (CHANGE 200): everything that happens in the world besides walking. The class server runs one
Game for everyone; a window played offline runs its own, so both play by the same rules.

    players     each one's movement (craft_sim), health and food, breath, inventory and the stack held on the
                cursor, the crafting grid, what screen is open, where they wake up
    actions     dig (checked: in reach, long enough for that block and tool), place (blocks, torches, doors,
                ladders, beds, seeds, water), use (a workbench, smelter or chest opens; a door opens and shuts; a
                bed skips the night; berries picked; a blast block lit), attack, eat, clicks in the screens,
                crafting, dropping, the hotbar, a creative player's pick of anything
    the world   the time of day, smelters smelting, crops and saplings growing, grass spreading, sand and grit
                falling, water flowing from a source, things dropped lying until picked up, blast blocks going off
    creatures   craft_mobs (Fluffs and Bleeps by day, Glitches and Rust Walkers at night)

Survival is kind to a club: hunger never takes the last heart, and by default you keep your things when you're
knocked out (the teacher can change that). Creative: fly, any block, nothing hurts, digging is instant.

What happened is kept in self.events for the window or the server to show and send: sounds, bursts of bits, words
for one player, a player's inventory or an open screen changed, a block changed (the world's own list).
"""
import math
import random

import craft_blocks as B
import craft_bot
import craft_items as items
import craft_sim as sim

I, ID = B.ITEM_ID, B.ID
DAY_SECONDS = 1200.0
WORLD_TICK = 0.25        # the world's slower things, four times a second
RANDOM_TICKS = 3         # blocks looked at a chunk, each world tick (crops, saplings, grass)
ITEM_LIFE = 300.0        # seconds a dropped thing lies before it goes
PICKUP = 1.6             # metres: walk this close to a dropped thing to pick it up
MAX_ITEMS = 60           # things lying about at once (each needs one of the snapshot's ids, 192 to 254)
BREATH = 10.0
DIG_SLACK = 0.7          # a dig may come this much sooner than the block's time (the window's clock)
# the ids everything has on the wire (one byte): players 0 to 63, their Craft Bots 64 to 127 (craft_bot), creatures
# 128 to 191 (craft_mobs), things dropped 192 to 254
ITEM_BASE, ITEM_LAST = 192, 254
ARMOUR_STOPS = ("hit", "zap", "blast", "spiky")   # what armour keeps off (not falls, magma, breath or hunger)
DEFAULT_RULES = {"mode": "survival", "mobs": True, "pvp": False, "keep_items": True, "blasts": False,
                 "day_length": DAY_SECONDS, "time_runs": True, "hunger": True, "falls_hurt": True}


class Player:
    def __init__(self, pid, name, spawn, creative=False):
        self.pid, self.name = pid, name
        self.state = sim.new_player(*spawn)
        self.inv = [None] * items.SLOTS
        self.armour = [None] * items.ARMOUR    # what's worn: head, chest, legs, feet
        self.cursor = None
        self.grid = [None] * 4
        self.grid_w = 2
        self.open = None            # ("workbench" | "chest" | "smelter", (x, y, z)) or None
        self.selected = 0
        self.spawn = tuple(spawn)
        self.creative = creative
        self.look = (0.0, 0.0)      # yaw, pitch (from the window, for the others to see and for reaching)
        self.input = (0.0, 0.0, 0)
        self.breath = BREATH
        self.tired = 0.0            # exhaustion: food goes down one each 4
        self.regen = 0.0
        self.hurt_at = -10.0
        self.hurt_left = 0.0        # the part of a point of damage that armour kept off, carried to the next hit
        self.dig = None             # (x, y, z, when it started)
        self.asleep = False
        self.stats = {"mined": {}, "placed": {}, "crafted": {}, "smelted": {}, "killed": {}, "eaten": 0, "deaths": 0,
                      "nights": 0, "slept": 0, "bot": {}}
        self.swing = 0.0

    @property
    def hits(self):
        """(The teaching layer's word for a unit's hits: here, the creatures this player has defeated.)"""
        return sum(self.stats.get("killed", {}).values())

    def held(self):
        s = self.inv[self.selected]
        return (B.ITEMS.get(s[0]), s) if s else (None, None)

    def to_save(self):
        return {"name": self.name, "inv": self.inv, "armour": self.armour, "selected": self.selected, "spawn": list(self.spawn),
                "pos": [self.state["x"], self.state["y"], self.state["z"]], "hp": self.state["hp"],
                "food": self.state["food"], "stats": self.stats}

    def load(self, saved):
        try:
            inv = saved.get("inv")
            if isinstance(inv, list) and len(inv) == items.SLOTS:
                self.inv = [s if (isinstance(s, list) and len(s) == 3 and s[0] in B.ITEMS) else None for s in inv]
            worn = saved.get("armour")
            if isinstance(worn, list) and len(worn) == items.ARMOUR:
                self.armour = [s if (isinstance(s, list) and len(s) == 3 and items.armour_part(s[0]) == k) else None
                               for k, s in enumerate(worn)]
            self.selected = int(saved.get("selected", 0)) % items.HOTBAR
            if saved.get("spawn"):
                self.spawn = tuple(float(v) for v in saved["spawn"][:3])
            if saved.get("pos"):
                x, y, z = (float(v) for v in saved["pos"][:3])
                self.state.update(x=x, y=y, z=z)
            self.state["hp"] = max(1, min(20, int(saved.get("hp", 20))))
            self.state["food"] = max(0, min(20, int(saved.get("food", 20))))
            if isinstance(saved.get("stats"), dict):
                self.stats.update(saved["stats"])
        except (TypeError, ValueError):
            pass


class Game:
    def __init__(self, world, rules=None, seed=1):
        self.world = world
        self.rules = dict(DEFAULT_RULES, **(rules or {}))
        self.time = 0.3 * self.rules["day_length"]  # (the morning)
        self.tick = 0
        self.players = {}
        self.chests = {}
        self.smelters = {}
        self.items = {}
        self.events = []
        self.rng = random.Random(seed)
        self.world_acc = 0.0
        self.water = set()          # water blocks to look at next world tick (flowing)
        self.blasts = {}            # (x, y, z) -> seconds left
        self.notes = []             # (pid, what, detail): for the teaching layer (crafted, smelted, survived...)
        self.night_was = False
        import craft_mobs
        self.mobs = craft_mobs.Mobs(self)
        self.bots = {}              # Craft Bots: id -> craft_bot.Bot (each learner's own)
        self.bot_brains = {}        # pid -> the brain driving that player's Bot (autopilot on), or None
        self.designs = {}           # pid -> the player's design (craft_design: their Bot's name, colour, points)

    # ---------- time ----------
    @property
    def day_t(self):
        return (self.time / self.rules["day_length"]) % 1.0

    def is_night(self):
        t = self.day_t
        return 0.53 < t < 0.97

    # ---------- players ----------
    def add_player(self, pid, name, creative=None, saved=None):
        creative = self.rules["mode"] == "creative" if creative is None else creative
        p = Player(pid, name, self.world.spawn, creative)
        if saved:
            p.load(saved)
        if not saved or not saved.get("inv"):
            self.starter_kit(p)
        self.players[pid] = p
        self.place_safely(p)
        self.say(pid, f"Welcome to Craft Lab, {name}!" if not saved else f"Welcome back, {name}.")
        return p

    def starter_kit(self, p):
        """A few things to begin with (survival: nothing much; creative: a hotbar of building blocks)."""
        if p.creative:
            for i, key in enumerate(("planks", "rubble", "glass", "brick", "torch", "door", "wool_red", "lumen", "dock")):
                p.inv[i] = items.new_slot(I[key], 64 if B.ITEMS[I[key]]["stack"] > 1 else 1)
        else:
            p.inv[0] = items.new_slot(I["apple"], 3)

    def place_safely(self, p):
        """Stand a player on top of the ground where they are (after joining, respawning, a world change)."""
        s = p.state
        x, y = int(math.floor(s["x"])), int(math.floor(s["y"]))
        x, y = max(0, min(self.world.X - 1, x)), max(0, min(self.world.Y - 1, y))
        z = int(math.floor(s["z"]))
        solid, liquid, _ = sim.tables()

        def free(zz):
            return not solid[self.world.get(x, y, zz)] and not solid[self.world.get(x, y, zz + 1)]
        if not free(z):
            z = self.world.top(x, y) + 1
        s.update(z=float(z), vx=0.0, vy=0.0, vz=0.0, fall=0.0)

    def remove_player(self, pid):
        p = self.players.pop(pid, None)
        if p is not None and p.cursor:
            items.add(p.inv, p.cursor[0], p.cursor[1], wear=p.cursor[2])
        return p

    def say(self, pid, text):
        self.events.append(("say", pid, text))

    def sound(self, name, x, y, z, volume=1.0):
        self.events.append(("sound", name, x, y, z, volume))

    def burst(self, x, y, z, tile, n=None):
        self.events.append(("burst", x, y, z, tile, n))

    def inv_changed(self, pid):
        self.events.append(("inv", pid))

    # ---------- the step ----------
    def step(self, inputs, dt=sim.STEP):
        """60 times a second: everyone's movement (their input, or none), their health and food, the creatures,
        dropped things; four times a second the world's slower things."""
        self.tick += 1
        if self.rules["time_runs"]:
            self.time += dt
        for pid, p in self.players.items():
            if pid in inputs:
                p.input = inputs[pid]
            if p.asleep:
                continue
            before = p.state
            p.state = sim.step_player(before, p.input, dt, self.world, p.creative)
            p.state["yaw"], p.state["pitch"] = p.look
            self.life(p, before, dt)
            p.swing = max(0.0, p.swing - dt)
        self.mobs.step(dt)
        for bot in list(self.bots.values()):
            bot.brain = self.bot_brains.get(bot.owner)
            bot.step(dt)
        self.step_items(dt)
        self.world_acc += dt
        if self.world_acc >= WORLD_TICK:
            self.world_acc -= WORLD_TICK
            self.world_tick()

    def life(self, p, before, dt):
        """Health, food and breath: falls, drowning, magma and cacti, hunger, getting better."""
        s = p.state
        if p.creative:
            s["hp"], s["food"] = 20, 20
            p.breath = BREATH
            return
        landed = (s["flags"] & sim.F_GROUND) and not (before["flags"] & sim.F_GROUND)
        if landed and before["fall"] > 3.4 and self.rules["falls_hurt"] and not (s["flags"] & sim.F_WATER):
            self.hurt(p, int(before["fall"] - 3), "fell")
        if landed:
            s["fall"] = 0.0
        ex, ey, ez = sim.eye(s)
        head = self.world.get(int(math.floor(ex)), int(math.floor(ey)), int(math.floor(ez)))
        if head == ID["water"]:
            p.breath -= dt
            if p.breath < 0:
                p.breath += 1.0
                self.hurt(p, 1, "drowned")
        else:
            p.breath = min(BREATH, p.breath + dt * 4)
        feet = [self.world.get(int(math.floor(s["x"] + dx)), int(math.floor(s["y"] + dy)), int(math.floor(s["z"] + 0.2)))
                for dx in (-0.31, 0.31) for dy in (-0.31, 0.31)]
        pain = max(B.BLOCKS[b]["hurts"] for b in feet)
        if pain and self.tick % 30 == 0:
            self.hurt(p, pain, "magma" if ID["magma"] in feet else "spiky")
        if self.rules["hunger"]:
            moving = math.hypot(s["vx"], s["vy"])
            p.tired += dt * (0.02 + moving * (0.03 if p.input[2] & sim.SPRINT_B else 0.01))
            if p.input[2] & sim.JUMP_B and s["flags"] & sim.F_GROUND:
                p.tired += 0.02
            if p.tired >= 4.0:
                p.tired -= 4.0
                s["food"] = max(0, s["food"] - 1)
        p.regen += dt
        if p.regen >= 4.0:
            p.regen = 0.0
            if s["food"] >= 16 and s["hp"] < 20:
                s["hp"] += 1
                p.tired += 1.5
            elif s["food"] == 0 and s["hp"] > 2:
                s["hp"] -= 1
                self.say(p.pid, "You're starving: eat something!")
        s["flags"] = (s["flags"] | sim.F_HURT) if self.tick * sim.STEP - p.hurt_at < 0.35 else (s["flags"] & ~sim.F_HURT)

    def hurt(self, p, amount, why="hit", knock=None):
        """A player loses health (nothing in creative). At none they are knocked out and wake at their spawn."""
        if p.creative or amount <= 0:
            return
        now = self.tick * sim.STEP
        if why in ("hit", "zap") and now - p.hurt_at < 0.5:
            return
        p.hurt_at = now
        s = p.state
        if why in ARMOUR_STOPS and any(p.armour):  # (armour keeps off part of a hit, and wears a little)
            kept = amount * min(0.8, items.armour_points(p.armour) * B.ARMOUR_SHARE)
            p.hurt_left += amount - kept
            amount = int(p.hurt_left)
            p.hurt_left -= amount
            broke = [B.name_of(a[0]) for k, a in enumerate(p.armour) if a and items.wear(p.armour, k)]
            for name in broke:
                self.say(p.pid, f"Your {name.lower()} broke!")
            self.inv_changed(p.pid)
            if broke:
                self.events.append(("wear", p.pid))
        s["hp"] = max(0, s["hp"] - amount)
        if knock is not None:
            s["vx"] += knock[0]
            s["vy"] += knock[1]
            s["vz"] = max(s["vz"], 4.0)
        self.sound("hurt", s["x"], s["y"], s["z"])
        if s["hp"] <= 0:
            self.knocked_out(p, why)

    def knocked_out(self, p, why):
        s = p.state
        p.stats["deaths"] = p.stats.get("deaths", 0) + 1
        words = {"fell": "fell too far", "drowned": "ran out of breath", "magma": "touched magma", "spiky": "hugged a cactus",
                 "hit": "was knocked out", "zap": "was zapped by a Glitch", "blast": "was caught in a blast"}
        self.events.append(("news", f"{p.name} {words.get(why, 'was knocked out')}"))
        if not self.rules["keep_items"]:
            for box in (p.inv, p.armour):
                for i, slot in enumerate(box):
                    if slot:
                        self.drop(slot[0], slot[1], s["x"], s["y"], s["z"] + 1, wear=slot[2])
                        box[i] = None
            self.inv_changed(p.pid)
            self.events.append(("wear", p.pid))
        s.update(x=p.spawn[0], y=p.spawn[1], z=p.spawn[2], vx=0.0, vy=0.0, vz=0.0, hp=20, food=max(s["food"], 12), fall=0.0)
        p.breath = BREATH
        self.place_safely(p)
        self.say(p.pid, "Knocked out! You wake up at your spawn point." + ("" if self.rules["keep_items"] else
                                                                           " Your things are where you fell."))

    # ---------- actions ----------
    def action(self, pid, m):
        """A player's action (a dict, as the window sends it). Returns nothing: what changed is in the events."""
        p = self.players.get(pid)
        if p is None or not isinstance(m, dict):
            return
        kind = m.get("type")
        try:
            if kind == "look":
                yaw, pitch = float(m.get("yaw", 0)), float(m.get("pitch", 0))
                if math.isfinite(yaw) and math.isfinite(pitch):
                    p.look = (yaw % 360.0, max(-90.0, min(90.0, pitch)))
            elif kind == "select":
                p.selected = int(m.get("slot", 0)) % items.HOTBAR
            elif kind == "dig_start":
                p.dig = (int(m["x"]), int(m["y"]), int(m["z"]), self.tick * sim.STEP)
                p.swing = 0.3
            elif kind == "dig":
                self.dig(p, int(m["x"]), int(m["y"]), int(m["z"]))
            elif kind == "place":
                self.place(p, int(m["x"]), int(m["y"]), int(m["z"]), tuple(int(v) for v in m.get("face", (0, 0, 1))[:3]))
            elif kind == "right":  # (a right click on a block: what it does, else what you hold is put beside it)
                x, y, z = int(m["x"]), int(m["y"]), int(m["z"])
                face = tuple(int(v) for v in m.get("face", (0, 0, 1))[:3])
                if p.input[2] & sim.SNEAK_B or not self.use_block(pid, x, y, z):
                    held, _ = p.held()
                    if held and (held.get("food") or held.get("armour") is not None) and held.get("block") is None:
                        self.use_item(p)
                    else:
                        self.place(p, x + face[0], y + face[1], z + face[2], face)
            elif kind == "use_item":
                self.use_item(p)
            elif kind == "attack":
                self.attack(p, int(m.get("target", -1)))
            elif kind == "click":
                self.click(p, str(m.get("area", "")), int(m.get("slot", 0)), bool(m.get("right")), bool(m.get("shift")))
            elif kind == "close":
                self.close(p)
            elif kind == "drop":
                self.drop_held(p, bool(m.get("all")))
            elif kind == "pick" and p.creative:
                item_id = int(m.get("item", 0))
                if item_id in B.ITEMS:
                    p.inv[p.selected] = items.new_slot(item_id, items.stack_max(item_id))
                    self.inv_changed(pid)
            elif kind == "creative_take" and p.creative:  # (the creative screen: any item onto the cursor)
                item_id = int(m.get("item", 0))
                if item_id in B.ITEMS:
                    p.cursor = items.new_slot(item_id, items.stack_max(item_id) if not m.get("right") else 1)
                    self.inv_changed(pid)
            elif kind == "respawn":
                self.place_safely(p)
        except (KeyError, TypeError, ValueError, IndexError):
            pass

    def reach_ok(self, p, x, y, z):
        ex, ey, ez = sim.eye(p.state)
        reach = sim.REACH_CREATIVE if p.creative else sim.REACH
        return math.dist((ex, ey, ez), (x + 0.5, y + 0.5, z + 0.5)) <= reach + 1.0

    def dig(self, p, x, y, z):
        """A block dug: checked (in reach, there is something to dig, long enough), taken out, its drops given."""
        w = self.world
        bid = w.get(x, y, z)
        if not bid or not w.inside(x, y, z) or not self.reach_ok(p, x, y, z):
            self.refuse(p, x, y, z)
            return
        b = B.BLOCKS[bid]
        held, slot = p.held()
        t, enough = B.dig_time(bid, held)
        if t is None:
            self.refuse(p, x, y, z)
            return
        if not p.creative:
            started = p.dig[3] if p.dig and p.dig[:3] == (x, y, z) else None
            if started is None or self.tick * sim.STEP - started < t - DIG_SLACK:
                self.refuse(p, x, y, z)
                return
        p.dig = None
        meta = w.get_meta(x, y, z)
        if b["key"] in ("door", "door_top"):  # (a door comes out whole)
            other = z + 1 if b["key"] == "door" else z - 1
            if w.get(x, y, other) in (ID["door"], ID["door_top"]):
                w.set(x, y, other, 0)
        if b["use"] == "chest":
            for s in self.chests.pop((x, y, z), []):
                if s:
                    self.drop(s[0], s[1], x + 0.5, y + 0.5, z + 0.5, wear=s[2])
        if b["use"] == "smelter":
            for s in (self.smelters.pop((x, y, z), {}) or {}).get("slots", []):
                if s:
                    self.drop(s[0], s[1], x + 0.5, y + 0.5, z + 0.5, wear=s[2])
        w.set(x, y, z, 0)
        self.burst(x, y, z, b["tiles"][1] if b["tiles"] else "particle")
        self.sound("dig_" + (b["tool"] or "soft"), x + 0.5, y + 0.5, z + 0.5)
        if not p.creative:
            for item_id, n in self.drops(bid, meta, enough):
                self.drop(item_id, n, x + 0.5, y + 0.5, z + 0.5)
            if held and held.get("tool") and items.wear(p.inv, p.selected):
                self.say(p.pid, f"Your {held['name'].lower()} broke!")
                self.sound("break", *sim.eye(p.state))
            self.inv_changed(p.pid)
        p.stats["mined"][b["key"]] = p.stats["mined"].get(b["key"], 0) + 1
        self.notes.append((p.pid, "mined", b["key"]))
        self.after_change(x, y, z)

    def drops(self, bid, meta, enough):
        key = B.BLOCKS[bid]["key"]
        r = self.rng.random()
        if key in ("leaves", "pale_leaves", "pine_leaves"):
            out = []
            if r < 0.08:
                out.append((I["sapling"], 1))
            if key == "leaves" and self.rng.random() < 0.04:
                out.append((I["apple"], 1))
            return out
        if key == "tall_grass":
            return [(I["seeds"], 1)] if r < 0.35 else [(I["root"], 1)] if r < 0.42 else []
        if key == "wheat":
            return [(I["wheat_item"], 1), (I["seeds"], 1 + (r < 0.5))] if meta >= 7 else [(I["seeds"], 1)]
        if key == "berry_bush":
            return [(I["berries"], 1 + (meta > 0))] + ([(I["sapling"], 1)] if r < 0.15 else [])
        if key == "grit" and r < 0.1:
            return [(I["rubble"], 1)]
        if key == "copper_ore":
            return [(ID["copper_ore"], 1)]
        return B.drops_of(bid, enough)

    def refuse(self, p, x, y, z):
        """A change the server won't make: the block as it is sent back to that player (their window had shown it
        changed)."""
        self.events.append(("block", p.pid, x, y, z))

    def place(self, p, x, y, z, face):
        """Something held put into the world at (x, y, z) (the open block beside the face clicked): a block, a torch,
        a door, a ladder, a bed, seeds, water."""
        w = self.world
        held, slot = p.held()
        if held is None or not w.inside(x, y, z) or not self.reach_ok(p, x, y, z):
            self.refuse(p, x, y, z)
            return
        here = w.get(x, y, z)
        replace = here in (0, ID["water"], ID["tall_grass"])
        key = held["key"]
        below = w.get(x, y, z - 1)
        solid, _, _ = sim.tables()
        if key == "water_bucket":
            if replace and here != ID["water"]:
                w.set(x, y, z, ID["water"], 0)
                self.water.add((x, y, z))
                if not p.creative:
                    p.inv[p.selected] = items.new_slot(I["bucket"])
                self.sound("splash", x + 0.5, y + 0.5, z + 0.5)
                self.inv_changed(p.pid)
            return
        if key == "seeds":
            if here == 0 and below == ID["farmland"]:
                self.put(p, x, y, z, ID["wheat"], 0, slot)
            else:
                self.refuse(p, x, y, z)
            return
        if held.get("block") is None:
            self.refuse(p, x, y, z)
            return
        bid = held["block"]
        b = B.BLOCKS[bid]
        if not replace:
            self.refuse(p, x, y, z)
            return
        if b["solid"] and any(sim.player_box_hits(q.state, x, y, z) for q in self.players.values()):
            self.refuse(p, x, y, z)
            return
        if b["solid"] and self.mobs.box_hit(x, y, z):
            self.refuse(p, x, y, z)
            return
        meta = 0
        if b["shape"] in ("cross", "crop") and below not in (ID["grass"], ID["soil"], ID["farmland"], ID["sand"]):
            self.refuse(p, x, y, z)
            return
        if b["shape"] == "torch" and not solid[below]:
            self.refuse(p, x, y, z)
            return
        if b["shape"] == "ladder":
            wall = (-face[0], -face[1], 0)
            if face[2] != 0 or not solid[w.get(x + wall[0], y + wall[1], z)]:
                self.refuse(p, x, y, z)
                return
            meta = {(1, 0): 0, (-1, 0): 1, (0, 1): 2, (0, -1): 3}[(wall[0], wall[1])]
        if b["shape"] == "door":
            if w.get(x, y, z + 1) not in (0, ID["tall_grass"]) or not solid[below]:
                self.refuse(p, x, y, z)
                return
            yaw = p.look[0] % 360
            meta = int(((yaw + 45) % 360) // 90)  # (the way you face: the door's frame is on the far side)
            meta = {0: 2, 1: 1, 2: 3, 3: 0}.get(meta, 0)
            w.set(x, y, z + 1, ID["door_top"], meta)
        if b["use"] == "smelter":
            self.smelters[(x, y, z)] = {"slots": [None, None, None], "burn": 0.0, "burn_max": 0.0, "progress": 0.0}
        if b["use"] == "chest":
            self.chests[(x, y, z)] = [None] * items.CHEST
        self.put(p, x, y, z, bid, meta, slot)

    def put(self, p, x, y, z, bid, meta, slot):
        self.world.set(x, y, z, bid, meta)
        b = B.BLOCKS[bid]
        self.sound("place", x + 0.5, y + 0.5, z + 0.5)
        if not p.creative:
            items.use_up(p.inv, p.selected)
            self.inv_changed(p.pid)
        p.stats["placed"][b["key"]] = p.stats["placed"].get(b["key"], 0) + 1
        self.notes.append((p.pid, "placed", b["key"]))
        p.swing = 0.25
        if bid == ID["water"]:
            self.water.add((x, y, z))
        self.after_change(x, y, z)

    def use_block(self, pid, x, y, z):
        """Right click on a block: what it does (a screen opens, a door, a bed, berries, a blast block). Returns True
        if it did something (else the window places what it holds instead)."""
        p = self.players.get(pid)
        if p is None or not self.reach_ok(p, x, y, z):
            return False
        w = self.world
        bid = w.get(x, y, z)
        b = B.BLOCKS[bid]
        use = b["use"]
        held, slot = p.held()
        if held and held.get("tool") == "hoe" and bid in (ID["grass"], ID["soil"]) and w.get(x, y, z + 1) == 0:
            w.set(x, y, z, ID["farmland"])
            self.sound("dig_shovel", x + 0.5, y + 0.5, z + 1)
            if not p.creative:
                items.wear(p.inv, p.selected)
                self.inv_changed(pid)
            self.notes.append((pid, "hoed", "farmland"))
            return True
        if held and held["key"] == "bucket" and bid == ID["water"] and w.get_meta(x, y, z) == 0:
            w.set(x, y, z, 0)
            self.after_change(x, y, z)
            if not p.creative:
                items.use_up(p.inv, p.selected)
                items.add(p.inv, I["water_bucket"], 1)
                self.inv_changed(pid)
            self.sound("splash", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use in ("workbench", "chest", "smelter"):
            self.close(p)
            if use == "chest":
                self.chests.setdefault((x, y, z), [None] * items.CHEST)
            if use == "smelter":
                self.smelters.setdefault((x, y, z), {"slots": [None, None, None], "burn": 0.0, "burn_max": 0.0,
                                                     "progress": 0.0})
            p.open = (use, (x, y, z))
            if use == "workbench":
                p.grid, p.grid_w = [None] * 9, 3
            self.sound("open", x + 0.5, y + 0.5, z + 0.5)
            self.events.append(("open", pid, use, (x, y, z)))
            self.inv_changed(pid)
            return True
        if use == "door":
            lower = z if b["key"] == "door" else z - 1
            meta = w.get_meta(x, y, lower) ^ 4
            w.set(x, y, lower, ID["door"], meta)
            if w.get(x, y, lower + 1) == ID["door_top"]:
                w.set(x, y, lower + 1, ID["door_top"], meta)
            self.sound("door", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "bed":
            if not self.is_night():
                p.spawn = (x + 0.5, y + 0.5, z + 1.0)
                self.say(pid, "You can only sleep at night. Your spawn point is set here.")
                return True
            p.spawn = (x + 0.5, y + 0.5, z + 1.0)
            p.asleep = True
            p.state.update(x=x + 0.5, y=y + 0.5, z=z + 0.6, vx=0.0, vy=0.0, vz=0.0)
            p.state["flags"] |= sim.F_SLEEP
            self.say(pid, "Sleeping... the night passes when everyone is in bed.")
            self.try_sleep()
            return True
        if use == "berries" and w.get_meta(x, y, z) > 0:
            w.set(x, y, z, bid, 0)
            items.add(p.inv, I["berries"], 2)
            self.inv_changed(pid)
            self.sound("pick", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "blast":
            if not self.rules["blasts"]:
                self.say(pid, "Blasts are switched off in this lesson.")
                return True
            self.blasts[(x, y, z)] = 3.0
            self.sound("fuse", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "dock":  # (your Craft Bot rolls out on top; the dock shows what it carries)
            bot = self.bot_of(pid)
            if bot is None:
                bot = self.add_bot(pid, (x, y, z))
                bot.facing = int(round(p.look[0] / 90.0)) % 4  # (facing the way you look: it digs where you were)
                bot.settle()
                self.say(pid, f"{bot_name(self, pid)} is ready. Upload its brain (U), then P for the autopilot.")
            elif tuple(bot.dock) != (x, y, z) or bot.brain is None:
                bot.dock = (x, y, z)
                bot.home()
            self.close(p)
            p.open = ("bot", bot.id)
            self.sound("open", x + 0.5, y + 0.5, z + 0.5)
            self.events.append(("open", pid, "bot", (x, y, z)))
            self.inv_changed(pid)
            return True
        return False

    # ---------- Craft Bots ----------
    def bot_of(self, pid):
        return self.bots.get(craft_bot.BOT_BASE + pid)

    def add_bot(self, pid, dock, saved=None):
        bot = craft_bot.Bot(self, craft_bot.BOT_BASE + pid, pid, dock)
        if saved:
            bot.load(saved)
        self.bots[bot.id] = bot
        self.notes.append((pid, "bot", "made"))
        return bot

    def try_sleep(self):
        awake = [q for q in self.players.values() if not q.asleep]
        if awake:
            return
        L = self.rules["day_length"]
        self.time = (math.floor(self.time / L) + 1) * L + 0.02 * L  # (the next morning)
        for q in self.players.values():
            q.asleep = False
            q.state["flags"] &= ~sim.F_SLEEP
            q.stats["slept"] = q.stats.get("slept", 0) + 1
            self.notes.append((q.pid, "slept", "bed"))
            self.say(q.pid, "Good morning!")
        self.events.append(("news", "Everyone slept: it's morning"))

    def use_item(self, p):
        """Right click with nothing to click on: eat what you hold (when you're hungry); a Bot kit calls your Bot
        back to its dock."""
        held, slot = p.held()
        if held and held.get("armour") is not None:  # (put on: what was worn there goes in your hand)
            k = held["armour"]
            p.inv[p.selected], p.armour[k] = p.armour[k], p.inv[p.selected]
            self.inv_changed(p.pid)
            self.events.append(("wear", p.pid))
            self.sound("clank", *sim.eye(p.state), 0.5)
            return
        if held and held["key"] == "bot_kit":
            bot = self.bot_of(p.pid)
            if bot is not None:
                bot.home()
                self.say(p.pid, "Your Craft Bot is back at its dock.")
            return
        if held and held.get("food"):
            if p.state["food"] >= 20 and not p.creative:
                self.say(p.pid, "You're not hungry.")
                return
            p.state["food"] = min(20, p.state["food"] + held["food"])
            p.state["hp"] = min(20, p.state["hp"] + (1 if held["food"] >= 4 else 0))
            if not p.creative:
                items.use_up(p.inv, p.selected)
                self.inv_changed(p.pid)
            p.stats["eaten"] = p.stats.get("eaten", 0) + 1
            self.notes.append((p.pid, "ate", held["key"]))
            self.sound("eat", *sim.eye(p.state))

    def attack(self, p, target):
        """A hit on a creature (or, with pvp on, another player) within reach."""
        held, slot = p.held()
        dmg = (held or B.HAND).get("damage", 1) if held and held.get("tool") else 1
        p.swing = 0.3
        ex, ey, ez = sim.eye(p.state)
        if target in self.players and self.rules["pvp"] and target != p.pid:
            q = self.players[target]
            if math.dist((ex, ey, ez), (q.state["x"], q.state["y"], q.state["z"] + 0.9)) < 4.0:
                yaw = math.radians(p.look[0])
                self.hurt(q, dmg, "hit", knock=(math.cos(yaw) * 5, math.sin(yaw) * 5))
            return
        if self.mobs.hit(target, dmg, (ex, ey, ez), p):
            if held and held.get("tool") and items.wear(p.inv, p.selected):
                self.say(p.pid, f"Your {held['name'].lower()} broke!")
            self.inv_changed(p.pid)

    # ---------- the screens ----------
    def click(self, p, area, i, right, shift):
        """A click in an open screen: the inventory, the crafting grid and its result, a chest, a smelter."""
        if area == "inv" and 0 <= i < items.SLOTS:
            if shift and p.cursor is None and p.inv[i]:
                self.shift_move(p, i)
            else:
                p.cursor = items.click(p.inv, i, p.cursor, right)
        elif area == "grid" and 0 <= i < len(p.grid):
            p.cursor = items.click(p.grid, i, p.cursor, right)
        elif area == "armour" and 0 <= i < items.ARMOUR:  # (only the piece for that slot goes in)
            if shift and p.cursor is None and p.armour[i]:
                if not items.add(p.inv, p.armour[i][0], wear=p.armour[i][2]):
                    p.armour[i] = None
            elif p.cursor is None or items.armour_part(p.cursor[0]) == i:
                p.cursor, p.armour[i] = p.armour[i], p.cursor
            self.events.append(("wear", p.pid))
        elif area == "result":
            got = items.match(p.grid, p.grid_w)
            if got is None:
                return
            item_id, n = got
            if shift:  # (as many as the grid makes, into the inventory)
                made = 0
                while items.match(p.grid, p.grid_w) == got and made < 64:
                    if items.add(p.inv, item_id, n):
                        break
                    items.craft_once(p.grid, p.grid_w)
                    made += n
                self.crafted(p, item_id, made)
            elif p.cursor is None or (p.cursor[0] == item_id and p.cursor[1] + n <= items.stack_max(item_id)):
                items.craft_once(p.grid, p.grid_w)
                if p.cursor is None:
                    p.cursor = items.new_slot(item_id, n)
                else:
                    p.cursor[1] += n
                self.crafted(p, item_id, n)
        elif area == "chest" and p.open and p.open[0] == "chest":
            box = self.chests.get(p.open[1])
            if box is not None and 0 <= i < len(box):
                if shift and box[i] and p.cursor is None:
                    left = items.add(p.inv, box[i][0], box[i][1], wear=box[i][2])
                    box[i] = None if not left else [box[i][0], left, box[i][2]]
                else:
                    p.cursor = items.click(box, i, p.cursor, right)
                self.events.append(("box", p.open[1]))
        elif area == "bot" and p.open and p.open[0] == "bot":
            bot = self.bots.get(p.open[1])
            if bot is not None and 0 <= i < len(bot.inv):
                if shift and bot.inv[i] and p.cursor is None:
                    s = bot.inv[i]
                    left = items.add(p.inv, s[0], s[1], wear=s[2])
                    bot.inv[i] = None if not left else [s[0], left, s[2]]
                else:
                    p.cursor = items.click(bot.inv, i, p.cursor, right)
        elif area == "smelter" and p.open and p.open[0] == "smelter":
            sm = self.smelters.get(p.open[1])
            if sm is not None and 0 <= i < 3:
                if shift and sm["slots"][i] and p.cursor is None:
                    s = sm["slots"][i]
                    left = items.add(p.inv, s[0], s[1], wear=s[2])
                    sm["slots"][i] = None if not left else [s[0], left, s[2]]
                    if i == 2 and not left:
                        self.smelted(p, s[0], s[1])
                else:
                    before = sm["slots"][2]
                    p.cursor = items.click(sm["slots"], i, p.cursor, right, takes_only=i == 2)
                    if i == 2 and before and sm["slots"][2] is None:
                        self.smelted(p, before[0], before[1])
                self.events.append(("box", p.open[1]))
        self.inv_changed(p.pid)

    def shift_move(self, p, i):
        """Shift-click in the inventory: into an open chest or smelter, armour onto you, else between the hotbar and
        the rest."""
        s = p.inv[i]
        k = items.armour_part(s[0])
        if k is not None and p.armour[k] is None and not (p.open and p.open[0] in ("chest", "bot", "smelter")):
            p.armour[k], p.inv[i] = s, None
            self.events.append(("wear", p.pid))
            return
        if p.open and p.open[0] == "chest" and p.open[1] in self.chests:
            left = items.add(self.chests[p.open[1]], s[0], s[1], wear=s[2])
            self.events.append(("box", p.open[1]))
        elif p.open and p.open[0] == "bot" and p.open[1] in self.bots:
            left = items.add(self.bots[p.open[1]].inv, s[0], s[1], wear=s[2])
        elif p.open and p.open[0] == "smelter" and p.open[1] in self.smelters:
            sm = self.smelters[p.open[1]]["slots"]
            k = 1 if s[0] in B.FUEL and s[0] not in B.SMELTS else 0
            if sm[k] is None:
                sm[k], left = s, 0
            elif sm[k][0] == s[0]:
                room = items.stack_max(s[0]) - sm[k][1]
                put = min(room, s[1])
                sm[k][1] += put
                left = s[1] - put
            else:
                left = s[1]
            self.events.append(("box", p.open[1]))
        else:
            order = range(items.HOTBAR, items.SLOTS) if i < items.HOTBAR else range(items.HOTBAR)
            left = items.add(p.inv, s[0], s[1], order=list(order), wear=s[2])
            if left == s[1]:
                return
            p.inv[i] = None if not left else [s[0], left, s[2]]
            return
        p.inv[i] = None if not left else [s[0], left, s[2]]

    def crafted(self, p, item_id, n):
        if n <= 0:
            return
        key = B.ITEMS[item_id]["key"]
        p.stats["crafted"][key] = p.stats["crafted"].get(key, 0) + n
        self.notes.append((p.pid, "crafted", key))
        self.sound("craft", *sim.eye(p.state))

    def smelted(self, p, item_id, n):
        key = B.ITEMS[item_id]["key"]
        p.stats["smelted"][key] = p.stats["smelted"].get(key, 0) + n
        self.notes.append((p.pid, "smelted", key))

    def close(self, p):
        """A screen closed: the crafting grid's things and the cursor's go back into the inventory."""
        for i, s in enumerate(p.grid):
            if s:
                left = items.add(p.inv, s[0], s[1], wear=s[2])
                if left:
                    self.drop(s[0], left, *sim.eye(p.state), wear=s[2])
                p.grid[i] = None
        if p.cursor:
            left = items.add(p.inv, p.cursor[0], p.cursor[1], wear=p.cursor[2])
            if left:
                self.drop(p.cursor[0], left, *sim.eye(p.state), wear=p.cursor[2])
            p.cursor = None
        p.grid, p.grid_w = [None] * 4, 2
        p.open = None
        self.inv_changed(p.pid)

    def drop_held(self, p, everything=False):
        """Q: throw what you hold (one, or the stack) in front of you."""
        held, slot = p.held()
        if not slot:
            return
        n = slot[1] if everything else 1
        yaw = math.radians(p.look[0])
        ex, ey, ez = sim.eye(p.state)
        self.drop(slot[0], n, ex + math.cos(yaw) * 1.2, ey + math.sin(yaw) * 1.2, ez - 0.3, wear=slot[2], wait=1.5)
        items.use_up(p.inv, p.selected, n)
        self.inv_changed(p.pid)

    # ---------- things dropped ----------
    def drop(self, item_id, n, x, y, z, wear=None, wait=0.4):
        if len(self.items) >= min(MAX_ITEMS, ITEM_LAST - ITEM_BASE + 1):
            oldest = max(self.items, key=lambda k: self.items[k]["age"])
            del self.items[oldest]
        eid = next(i for i in range(ITEM_BASE, ITEM_LAST + 1) if i not in self.items)
        self.items[eid] = {"id": eid, "item": item_id, "count": n, "wear": wear, "x": x, "y": y, "z": z, "vz": 2.0,
                           "age": 0.0, "wait": wait}

    def step_items(self, dt):
        solid, _, _ = sim.tables()
        for eid, it in list(self.items.items()):
            it["age"] += dt
            it["wait"] -= dt
            if it["age"] > ITEM_LIFE:
                del self.items[eid]
                continue
            below = self.world.get(int(math.floor(it["x"])), int(math.floor(it["y"])), int(math.floor(it["z"] - 0.15)))
            if solid[below] and it["vz"] <= 0:
                it["vz"] = 0.0
                it["z"] = math.floor(it["z"] - 0.15) + 1 + 0.15
            else:
                it["vz"] = max(-20.0, it["vz"] - 20 * dt)
                it["z"] += it["vz"] * dt
            if it["wait"] > 0:
                continue
            for p in self.players.values():
                s = p.state
                if math.dist((s["x"], s["y"], s["z"] + 0.6), (it["x"], it["y"], it["z"])) < PICKUP:
                    left = items.add(p.inv, it["item"], it["count"], wear=it.get("wear"))
                    if left < it["count"]:
                        self.sound("pop", s["x"], s["y"], s["z"], 0.5)
                        self.inv_changed(p.pid)
                    if left:
                        it["count"] = left
                    else:
                        del self.items[eid]
                    break

    # ---------- the world's slow things ----------
    def world_tick(self):
        dt = WORLD_TICK
        self.smelting(dt)
        self.random_ticks()
        self.flow_water()
        for pos in list(self.blasts):
            self.blasts[pos] -= dt
            if self.blasts[pos] <= 0:
                del self.blasts[pos]
                self.blast(*pos)
        night = self.is_night()
        if self.night_was and not night:  # (dawn: everyone who was here all night survived it)
            for q in self.players.values():
                q.stats["nights"] = q.stats.get("nights", 0) + 1
                self.notes.append((q.pid, "survived", "night"))
            self.events.append(("news", "The sun is up: you survived the night!"))
        self.night_was = night

    def smelting(self, dt):
        w = self.world
        for pos, sm in self.smelters.items():
            src, fuel, out = sm["slots"]
            can = src is not None and src[0] in B.SMELTS
            target = B.SMELTS.get(src[0]) if can else None
            room = target is not None and (out is None or (out[0] == target and out[1] < items.stack_max(target)))
            if sm["burn"] <= 0 and can and room and fuel is not None and fuel[0] in B.FUEL:
                sm["burn"] = sm["burn_max"] = B.FUEL[fuel[0]] * B.SMELT_SECONDS
                items.use_up(sm["slots"], 1)
            lit = sm["burn"] > 0
            if lit:
                sm["burn"] -= dt
                if can and room:
                    sm["progress"] += dt
                    if sm["progress"] >= B.SMELT_SECONDS:
                        sm["progress"] = 0.0
                        items.use_up(sm["slots"], 0)
                        if sm["slots"][2] is None:
                            sm["slots"][2] = items.new_slot(target, 1)
                        else:
                            sm["slots"][2][1] += 1
                        self.events.append(("box", pos))
                else:
                    sm["progress"] = 0.0
            else:
                sm["progress"] = max(0.0, sm["progress"] - dt * 2)
            want = ID["smelter_lit"] if sm["burn"] > 0 else ID["smelter"]
            if w.get(*pos) in (ID["smelter"], ID["smelter_lit"]) and w.get(*pos) != want:
                w.set(*pos, want, w.get_meta(*pos))
            if self.tick % 15 == 0:
                self.events.append(("box", pos))

    def random_ticks(self):
        """A few blocks a chunk looked at each world tick: crops grow, saplings become trees, grass spreads onto soil,
        berry bushes grow berries again."""
        w = self.world
        for cx, cy in w.chunks:
            for _ in range(RANDOM_TICKS):
                x = cx * 16 + self.rng.randrange(16)
                y = cy * 16 + self.rng.randrange(16)
                z = self.rng.randrange(2, w.Z - 1)
                bid = w.blocks[x, y, z]
                if bid == 0 or bid == ID["stone"]:
                    continue
                if bid == ID["wheat"]:
                    m = w.get_meta(x, y, z)
                    if m < 7 and max(w.sky[x, y, z] * (1 if not self.is_night() else 0), w.glow[x, y, z]) >= 9:
                        w.set(x, y, z, bid, m + 1, light=False)
                elif bid == ID["sapling"]:
                    if self.rng.random() < 0.3 and w.sky[x, y, z] >= 9:
                        self.grow_tree(x, y, z)
                elif bid == ID["soil"] and w.get(x, y, z + 1) == 0 and w.sky[x, y, z + 1] >= 9:
                    if any(w.get(x + dx, y + dy, z + dz) == ID["grass"] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           for dz in (-1, 0, 1)):
                        w.set(x, y, z, ID["grass"], light=False)
                elif bid == ID["grass"] and B.BLOCKS[w.get(x, y, z + 1)]["opaque"]:
                    w.set(x, y, z, ID["soil"], light=False)
                elif bid == ID["berry_bush"] and w.get_meta(x, y, z) == 0 and self.rng.random() < 0.2:
                    w.set(x, y, z, bid, 1, light=False)

    def grow_tree(self, x, y, z):
        w = self.world
        if any(w.get(x, y, z + k) not in (0, ID["sapling"]) for k in range(6)):
            return
        before = w.blocks.copy()
        w.blocks[x, y, z] = 0
        w.tree(x, y, z, "oak", self.rng.random())
        changed = (w.blocks != before).nonzero()
        for cx, cy, cz in zip(*changed):
            w.set(int(cx), int(cy), int(cz), int(w.blocks[cx, cy, cz]), light=False)
        w.light_region(max(0, x - 4), max(0, y - 4), min(w.X, x + 5), min(w.Y, y + 5))
        self.sound("grow", x + 0.5, y + 0.5, z + 1)

    def after_change(self, x, y, z):
        """A block changed: sand and grit above fall into the gap, water beside or above flows in, plants on top of
        it pop off, a torch with nothing under it falls."""
        w = self.world
        above = w.get(x, y, z + 1)
        ab = B.BLOCKS[above]
        if w.get(x, y, z) == 0:
            if ab["falls"]:
                top = z + 1
                while B.BLOCKS[w.get(x, y, top)]["falls"]:
                    top += 1
                for k in range(z + 1, top):
                    w.set(x, y, k - 1, w.get(x, y, k))
                w.set(x, y, top - 1, 0)
                self.sound("dig_shovel", x + 0.5, y + 0.5, z + 0.5, 0.6)
            elif ab["shape"] in ("cross", "crop", "torch") or above == ID["door_top"]:
                meta = w.get_meta(x, y, z + 1)
                w.set(x, y, z + 1, 0)
                for item_id, n in self.drops(above, meta, True):
                    self.drop(item_id, n, x + 0.5, y + 0.5, z + 1.5)
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, 0)):
            if w.get(x + dx, y + dy, z + dz) == ID["water"]:
                self.water.add((x + dx, y + dy, z + dz))

    def flow_water(self):
        """Water spreads from a source: down first, then sideways up to 7 blocks (meta: 0 a source, 1 to 7 flowing).
        Flowing water with nothing feeding it dries up."""
        w = self.world
        if not self.water:
            return
        todo, self.water = list(self.water)[:400], set(list(self.water)[400:])
        W = ID["water"]
        for x, y, z in todo:
            if w.get(x, y, z) != W:
                continue
            level = w.get_meta(x, y, z)
            if level > 0:  # (flowing: is anything still feeding it?)
                fed = w.get(x, y, z + 1) == W or any(
                    w.get(x + dx, y + dy, z) == W and w.get_meta(x + dx, y + dy, z) < level
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                if not fed:
                    w.set(x, y, z, 0)
                    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, -1)):
                        if w.get(x + dx, y + dy, z + dz) == W:
                            self.water.add((x + dx, y + dy, z + dz))
                    continue
            if w.get(x, y, z - 1) == 0 or (w.get(x, y, z - 1) == W and w.get_meta(x, y, z - 1) > 1):
                if w.get(x, y, z - 1) == 0:
                    w.set(x, y, z - 1, W, 1)
                self.water.add((x, y, z - 1))
                continue
            if level >= 7 or w.get(x, y, z - 1) not in (W,) and not B.BLOCKS[w.get(x, y, z - 1)]["solid"]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = w.get(x + dx, y + dy, z)
                if nb in (0, ID["tall_grass"]) and w.inside(x + dx, y + dy, z):
                    w.set(x + dx, y + dy, z, W, level + 1)
                    self.water.add((x + dx, y + dy, z))

    def blast(self, x, y, z):
        """A blast block going off: blocks within 3 taken out (not corestone; some drop), creatures and players
        near it hurt and thrown."""
        w = self.world
        self.sound("blast", x + 0.5, y + 0.5, z + 0.5, 1.5)
        changes = []
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                for dz in range(-3, 4):
                    if dx * dx + dy * dy + dz * dz > 10:
                        continue
                    bx, by, bz = x + dx, y + dy, z + dz
                    bid = w.get(bx, by, bz)
                    if not bid or bid == ID["corestone"] or not w.inside(bx, by, bz):
                        continue
                    if bid == ID["blast"] and (bx, by, bz) != (x, y, z):
                        self.blasts[(bx, by, bz)] = 0.4
                        continue
                    changes.append((bx, by, bz, 0, 0))
                    if self.rng.random() < 0.25:
                        for item_id, n in self.drops(bid, 0, True):
                            self.drop(item_id, n, bx + 0.5, by + 0.5, bz + 0.5)
        w.apply_changes(changes)
        w.changes.extend(changes)
        self.burst(x, y, z, "magma", 40)
        for p in self.players.values():
            d = math.dist((p.state["x"], p.state["y"], p.state["z"]), (x + 0.5, y + 0.5, z + 0.5))
            if d < 6:
                self.hurt(p, int(12 / max(1.0, d)), "blast", knock=((p.state["x"] - x) * 2, (p.state["y"] - y) * 2))
        self.mobs.blast(x + 0.5, y + 0.5, z + 0.5)

    # ---------- what the window shows ----------
    def inventory_msg(self, pid):
        p = self.players.get(pid)
        if p is None:
            return None
        msg = {"type": "inventory", "inv": p.inv, "cursor": p.cursor, "grid": p.grid, "grid_w": p.grid_w,
               "selected": p.selected, "open": p.open[0] if p.open else None, "armour": p.armour,
               "armour_points": items.armour_points(p.armour),
               "result": list(items.match(p.grid, p.grid_w) or []) or None, "creative": p.creative}
        if p.open and p.open[0] == "chest":
            msg["box"] = self.chests.get(p.open[1])
        if p.open and p.open[0] == "bot":
            bot = self.bots.get(p.open[1])
            msg["box"] = bot.inv if bot else [None] * craft_bot.SLOTS
            msg["bot"] = {"name": bot_name(self, pid), "error": bot.brain.error if bot and bot.brain else None,
                          "running": bool(bot and bot.brain and not bot.brain.error), "stats": bot.stats if bot else {}}
        if p.open and p.open[0] == "smelter":
            sm = self.smelters.get(p.open[1]) or {}
            msg["box"] = sm.get("slots")
            msg["burn"] = round(sm.get("burn", 0) / max(0.01, sm.get("burn_max", 1)), 2) if sm.get("burn", 0) > 0 else 0
            msg["progress"] = round(sm.get("progress", 0) / B.SMELT_SECONDS, 2)
        return msg

    def save_extra(self):
        """The game's own things kept with the world (chests, smelters, the time)."""
        return {"time": self.time,
                "chests": [[list(k), v] for k, v in self.chests.items()],
                "smelters": [[list(k), v] for k, v in self.smelters.items()]}

    def load_extra(self, extra):
        try:
            self.time = float(extra.get("time", self.time))
            self.chests = {tuple(k): v for k, v in extra.get("chests", [])}
            self.smelters = {tuple(k): v for k, v in extra.get("smelters", [])}
        except (TypeError, ValueError):
            pass


def bot_name(game, pid):
    d = game.designs.get(pid)
    name = (d or {}).get("name") or "Craft Bot"
    return "Your Craft Bot" if name in ("You Bot", "Bot") else name
