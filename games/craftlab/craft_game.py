"""Craft Lab's rules (CHANGE 200; our own world since CHANGE 207): everything that happens in the world besides
walking. The class server runs one Game for everyone; a window played offline runs its own, so both play by the
same rules.

    players     each one's movement (craft_sim), Health, Energy and Shield, air, the Toolbelt and Backpack and the
                stack held on the cursor, the suit worn, what screen is open, the blueprints building, where they
                wake up (their Recharge Pod)
    actions     dig (checked: in reach, long enough for that block and tool), place (blocks, glowsticks, doors,
                ladders, Pods, seed packs, water), use (a Fabricator, Refinery or Locker opens; a door opens and
                shuts; a Pod sets your wake point and recharges you; berries and Glowfruit picked; a Patch closes a
                Glitch rift), use a creature (brush a Fluff, trade with a Bleep), attack, eat, clicks in the screens,
                building a blueprint, dropping, the Toolbelt, a Sandbox player's pick of anything
    the world   the time of day (15 minutes: 9 of day, 1 of dusk, 4 of night, 1 of dawn), Refineries refining, crops
                and saplings growing, turf spreading, sand and grit falling, water flowing from a source (4 blocks),
                things dropped lying until picked up, Overload Cells pulsing, Glitch rifts opening at dusk
    creatures   craft_mobs (Fluffs and Bleeps by day, Glitches from the rifts, Rust Walkers round the scrap heaps)

Challenge is kind to a club: running out of Energy never takes the last 10 Health, and by default you keep your
things when you're knocked out (the teacher can change that). Sandbox: fly, any block, nothing hurts, digging and
building are instant.

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
DAY_SECONDS = 900.0
DUSK, NIGHT, DAWN = 0.6, 9.999 / 15, 14.0 / 15   # (a day: 0 to DUSK day, then dusk, night from NIGHT, dawn from DAWN)
FAST_NIGHT = 20.0        # how much faster the night goes when everyone is resting in a Recharge Pod
WORLD_TICK = 0.25        # the world's slower things, four times a second
RANDOM_TICKS = 3         # blocks looked at a chunk, each world tick (crops, saplings, turf)
ITEM_LIFE = 180.0        # seconds a dropped thing lies before it goes
PICKUP = 1.6             # metres: walk this close to a dropped thing to pick it up
MAX_ITEMS = 60           # things lying about at once (each needs one of the snapshot's ids, 192 to 254)
HEALTH, ENERGY = 100, 100
AIR = 12.0               # seconds under water before you take 5 Health a second
REGEN_EVERY, REGEN_ABOVE = 1.5, 40   # a point of Health back every 1.5 s while Energy is above 40
STARVE_EVERY, STARVE_FLOOR = 3.0, 10  # at no Energy, a point of Health goes every 3 s, never below 10
DRAIN = {"idle": 0.05, "run": 1.0, "swim": 0.6, "dig": 0.4, "jump": 0.2}   # Energy: a second (idle, running,
#                                                                            swimming), or each dig and jump
SHIELD_WAIT, SHIELD_REFILL = 5.0, 0.5   # the Shield refills a point every 0.5 s after 5 s with no harm
SAFE_FALL, FALL_HARM = 4, 8              # a fall of more than 4 blocks: 8 Health for each block more
POD_EVERY, POD_ENERGY = 300.0, 60        # a Pod tops your Energy up to 60, once every 5 minutes
DIG_SLACK = 0.7          # a dig may come this much sooner than the block's time (the window's clock)
PULSE_RADIUS, PULSE_REACH, PULSE_HARM, PULSE_SECONDS = 2.5, 5.0, 6, 3.0   # an Overload Cell's pulse
RIFTS, RIFT_EVERY, RIFT_MOST = (1, 3), 20.0, 3   # rifts opening at dusk; a Glitch from each every 20 s, 3 out at once
SET_BY_HAND = 30.0  # (a jump of the clock larger than this, in game seconds, between world ticks: the time was set)
# the ids everything has on the wire (one byte): players 0 to 63, their Craft Bots 64 to 127 (craft_bot), creatures
# 128 to 191 (craft_mobs), things dropped 192 to 254
ITEM_BASE, ITEM_LAST = 192, 254
SHIELD_STOPS = ("hit", "zap", "grab", "pulse")   # what the Shield soaks (not falls, magma, air or Energy)
SAVE_VERSION = 2         # (a player's saved things: older ones, from before CHANGE 207, start again)
DEFAULT_RULES = {"mode": "challenge", "mobs": True, "pvp": False, "keep_items": True, "blasts": False,
                 "day_length": DAY_SECONDS, "time_runs": True, "energy": True, "falls_hurt": True}
RULE_ALIASES = {"hunger": "energy"}


def clean_rules(rules):
    """Rules with old names (hunger, survival, creative) as they are now."""
    out = {RULE_ALIASES.get(k, k): v for k, v in (rules or {}).items()}
    if "mode" in out:
        out["mode"] = B.mode_of(out["mode"])
    return out


class Player:
    def __init__(self, pid, name, spawn, creative=False):
        self.pid, self.name = pid, name
        self.state = sim.new_player(*spawn)
        self.inv = [None] * items.SLOTS
        self.suit = [None] * items.SUIT      # what's worn: visor, vest, boots
        self.cursor = None
        self.open = None            # ("fabricator" | "locker" | "refinery" | "bot", where) or None
        self.tab = "backpack"       # the Backpack screen's tab: backpack, blueprints or bot
        self.selected = 0
        self.spawn = tuple(spawn)
        self.has_pod = False
        self.creative = creative
        self.look = (0.0, 0.0)      # yaw, pitch (from the window, for the others to see and for reaching)
        self.input = (0.0, 0.0, 0)
        self.air = AIR
        self.energy = float(ENERGY)
        self.shield = 0.0
        self.regen = self.starve = self.refill = self.drown = 0.0
        self.hurt_at = -10.0
        self.harm_at = -10.0        # the last time anything harmed you (the Shield refills 5 s after)
        self.pod_at = -1000.0
        self.dig = None             # (x, y, z, when it started)
        self.asleep = False
        self.seen = set()           # every item id ever held (a blueprint unlocks when all its parts have been)
        self.building = []          # [{"makes", "count", "left", "total"}]: blueprints building, the first one now
        self.warned = False
        self.stats = {"mined": {}, "placed": {}, "built": {}, "refined": {}, "killed": {}, "eaten": 0, "deaths": 0,
                      "nights": 0, "slept": 0, "bot": {}, "rifts": 0, "brushed": 0, "traded": 0}
        self.swing = 0.0

    @property
    def hits(self):
        """(The teaching layer's word for a unit's hits: here, the creatures this player has defeated.)"""
        return sum(self.stats.get("killed", {}).values())

    def held(self):
        s = self.inv[self.selected]
        return (B.ITEMS.get(s[0]), s) if s else (None, None)

    def shield_max(self):
        return items.shield_of(self.suit)

    def to_save(self):
        return {"version": SAVE_VERSION, "name": self.name, "inv": self.inv, "suit": self.suit, "selected": self.selected,
                "spawn": list(self.spawn), "has_pod": self.has_pod,
                "pos": [self.state["x"], self.state["y"], self.state["z"]], "hp": self.state["hp"],
                "energy": round(self.energy, 2), "stats": self.stats,
                "seen": sorted(B.ITEMS[i]["key"] for i in self.seen if i in B.ITEMS),
                "building": [dict(b) for b in self.building]}

    def load(self, saved):
        try:
            if isinstance(saved.get("stats"), dict):
                self.stats.update(saved["stats"])
            if saved.get("version") != SAVE_VERSION:  # (from before CHANGE 207: the old things don't fit the new world)
                return
            inv = saved.get("inv")
            if isinstance(inv, list) and len(inv) == items.SLOTS:
                self.inv = [s if (isinstance(s, list) and len(s) == 3 and s[0] in B.ITEMS) else None for s in inv]
            worn = saved.get("suit")
            if isinstance(worn, list) and len(worn) == items.SUIT:
                self.suit = [s if (isinstance(s, list) and len(s) == 3 and items.suit_part(s[0]) == k) else None
                             for k, s in enumerate(worn)]
            self.selected = int(saved.get("selected", 0)) % items.TOOLBELT
            if saved.get("spawn"):
                self.spawn = tuple(float(v) for v in saved["spawn"][:3])
            self.has_pod = bool(saved.get("has_pod"))
            if saved.get("pos"):
                x, y, z = (float(v) for v in saved["pos"][:3])
                self.state.update(x=x, y=y, z=z)
            self.state["hp"] = max(1, min(HEALTH, int(saved.get("hp", HEALTH))))
            self.energy = max(0.0, min(float(ENERGY), float(saved.get("energy", ENERGY))))
            self.seen = {I[k] for k in saved.get("seen") or [] if k in I}
            self.building = [dict(makes=str(b["makes"]), count=int(b["count"]), left=float(b["left"]),
                                  total=float(b["total"])) for b in saved.get("building") or []
                             if isinstance(b, dict) and b.get("makes") in I][:items.MAX_BUILDS]
        except (TypeError, ValueError, KeyError):
            pass


class Game:
    def __init__(self, world, rules=None, seed=1):
        self.world = world
        self.rules = dict(DEFAULT_RULES, **clean_rules(rules))
        self.time = 0.1 * self.rules["day_length"]  # (the morning)
        self.speed = 1.0            # the time's speed (FAST_NIGHT while everyone rests in a Pod)
        self.tick = 0
        self.players = {}
        self.lockers = {}           # (x, y, z) -> {"slots": [24], "name": "Sam's ores"}
        self.refineries = {}        # (x, y, z) -> {"slots": [17], "power": items it can still refine, "progress"}
        self.items = {}
        self.events = []
        self.rng = random.Random(seed)
        self.world_acc = 0.0
        self.water = set()          # water blocks to look at next world tick (flowing)
        self.watered = {}           # a Grow bed's (x, y, z) -> the day a Water canister was poured on it
        self.overloads = {}         # (x, y, z) -> seconds until an armed Overload Cell pulses
        self.rifts = {}             # number -> {"cells": [(x, y, z), ...], "was": [block, ...], "timer", "glitches"}
        self.rift_n = 0
        self.notes = []             # (pid, what, detail): for the teaching layer (built, refined, survived...)
        self.phase_was = self.phase()
        self.time_was = self.time   # (the clock at the last world tick: was a new phase reached by the clock or set?)
        import craft_mobs
        self.mobs = craft_mobs.Mobs(self)
        self.bots = {}              # Craft Bots: id -> craft_bot.Bot (each learner's own)
        self.bot_brains = {}        # pid -> the brain driving that player's Bot (autopilot on), or None
        self.designs = {}           # pid -> the player's design (craft_design: their Bot's name, colour, points)
        self.fill_ruins()

    # ---------- time ----------
    @property
    def day_t(self):
        return (self.time / self.rules["day_length"]) % 1.0

    @property
    def day(self):
        return int(self.time // self.rules["day_length"])

    def phase(self, t=None):
        t = self.day_t if t is None else t
        return "day" if t < DUSK else "dusk" if t < NIGHT else "night" if t < DAWN else "dawn"

    def is_night(self):
        """Dusk to dawn: Glitch rifts are open, Rust Walkers come up, the Pods speed it by."""
        return DUSK <= self.day_t < DAWN

    def now(self):
        return self.tick * sim.STEP

    # ---------- players ----------
    def add_player(self, pid, name, creative=None, saved=None):
        creative = self.rules["mode"] == "sandbox" if creative is None else creative
        p = Player(pid, name, self.world.spawn, creative)
        if saved:
            p.load(saved)
        if not any(p.inv):
            self.starter_kit(p)
        p.seen |= {s[0] for s in p.inv + p.suit if s}
        self.players[pid] = p
        self.place_safely(p)
        self.say(pid, f"Bot online. Welcome to Craft Lab, {name}!" if not saved else f"Welcome back, {name}.")
        return p

    def starter_kit(self, p):
        """A few things to begin with (Challenge: three apples and the rubble for a Fabricator and a Mk1 Drill;
        Sandbox: a Toolbelt of building blocks)."""
        if p.creative:
            for i, key in enumerate(("boards", "rubble", "glass", "stone_tiles", "glowstick", "door", "lumen", "dock")):
                p.inv[i] = items.new_slot(I[key], items.stack_max(I[key]))
        else:
            p.inv[0] = items.new_slot(I["apple"], 3)
            p.inv[1] = items.new_slot(I["rubble"], 5)

    def fill_ruins(self):
        """The ruined lab buildings' Lockers: starter parts in each (once: a saved world keeps what's left)."""
        for r in getattr(self.world, "ruins", []):
            pos = tuple(r["locker"])
            if pos in self.lockers or self.world.get(*pos) != ID["locker"]:
                continue
            box = [None] * items.LOCKER
            for k, (key, n) in enumerate((("rubble", 8), ("rod", 4), ("battery", 1), ("scrap", 3), ("glowstick", 4),
                                          ("apple", 2))):
                box[k] = items.new_slot(I[key], n)
            self.lockers[pos] = {"slots": box, "name": "Lab stores"}

    def place_safely(self, p):
        """Stand a player on top of the ground where they are (after joining, waking, a world change)."""
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
        p = self.players.get(pid)
        if p is not None:
            self.check_unlocks(p)

    def check_unlocks(self, p):
        """Anything new held: the blueprints it unlocks are said ("Blueprint unlocked: Battery")."""
        now = {s[0] for s in p.inv + p.suit + [p.cursor] if s}
        new = now - p.seen
        if not new:
            return
        before = p.seen
        p.seen = before | new
        if p.creative:
            return
        names = [B.name_of(I[bp["makes"]]) for bp in items.blueprints()
                 if items.unlocked(bp, p.seen) and not items.unlocked(bp, before)]
        if names:
            self.say(p.pid, "Blueprint unlocked: " + ", ".join(dict.fromkeys(names)))

    # ---------- the step ----------
    def step(self, inputs, dt=sim.STEP):
        """60 times a second: everyone's movement (their input, or none), their Health and Energy, the creatures,
        dropped things, blueprints building; four times a second the world's slower things."""
        self.tick += 1
        if self.rules["time_runs"]:
            self.time += dt * self.speed
        for pid, p in self.players.items():
            if pid in inputs:
                p.input = inputs[pid]
            self.step_builds(p, dt)
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
        """Health, Energy, Shield and air: falls, drowning, magma and cacti, Energy draining, getting better."""
        s = p.state
        if p.creative:
            s["hp"], s["energy"], s["shield"] = HEALTH, ENERGY, p.shield_max()
            p.air, p.energy, p.shield = AIR, float(ENERGY), float(p.shield_max())
            return
        landed = (s["flags"] & sim.F_GROUND) and not (before["flags"] & sim.F_GROUND)
        blocks = int(round(before["fall"]))
        if landed and blocks > SAFE_FALL and self.rules["falls_hurt"] and not (s["flags"] & sim.F_WATER):
            self.hurt(p, FALL_HARM * (blocks - SAFE_FALL), "fell")
        if landed:
            s["fall"] = 0.0
        ex, ey, ez = sim.eye(s)
        head = self.world.get(int(math.floor(ex)), int(math.floor(ey)), int(math.floor(ez)))
        if head == ID["water"]:
            p.air = max(0.0, p.air - dt)
            if p.air <= 0:
                p.drown += dt
                if p.drown >= 1.0:
                    p.drown = 0.0
                    self.hurt(p, 5, "drowned")
        else:
            p.air, p.drown = min(AIR, p.air + dt * 4), 0.0
        feet = [self.world.get(int(math.floor(s["x"] + dx)), int(math.floor(s["y"] + dy)), int(math.floor(s["z"] + 0.2)))
                for dx in (-0.36, 0.36) for dy in (-0.36, 0.36)]
        pain = max(B.BLOCKS[b]["hurts"] for b in feet)
        if pain and self.tick % 30 == 0:
            self.hurt(p, pain, "magma" if ID["magma"] in feet else "spiky")
        if self.rules["energy"]:
            moving = math.hypot(s["vx"], s["vy"]) > 0.5
            drain = DRAIN["idle"]
            if s["flags"] & sim.F_WATER and moving:
                drain += DRAIN["swim"]
            elif moving and p.input[2] & sim.SPRINT_B:
                drain += DRAIN["run"]
            self.tire(p, drain * dt)
            if p.input[2] & sim.JUMP_B and before["flags"] & sim.F_GROUND and not s["flags"] & sim.F_GROUND:
                self.tire(p, DRAIN["jump"])
        p.regen += dt
        if p.regen >= REGEN_EVERY:
            p.regen = 0.0
            if p.energy > REGEN_ABOVE and s["hp"] < HEALTH:
                s["hp"] += 1
        if p.energy <= 0:
            p.starve += dt
            if p.starve >= STARVE_EVERY:
                p.starve = 0.0
                if s["hp"] > STARVE_FLOOR:
                    s["hp"] -= 1
        top = p.shield_max()
        if p.shield > top:
            p.shield = float(top)
        if p.shield < top and self.now() - p.harm_at >= SHIELD_WAIT:
            p.refill += dt
            while p.refill >= SHIELD_REFILL and p.shield < top:
                p.refill -= SHIELD_REFILL
                p.shield += 1
        s["energy"], s["shield"] = int(math.ceil(p.energy)), int(p.shield)
        s["flags"] = (s["flags"] | sim.F_HURT) if self.now() - p.hurt_at < 0.35 else (s["flags"] & ~sim.F_HURT)

    def tire(self, p, amount):
        """Energy used (running, swimming, digging, jumping): a warning when it runs low."""
        if p.creative or not self.rules["energy"]:
            return
        p.energy = max(0.0, p.energy - amount)
        if p.energy < 20 and not p.warned:
            p.warned = True
            self.say(p.pid, "Energy low: eat something.")
        elif p.energy >= 30:
            p.warned = False

    def hurt(self, p, amount, why="hit", knock=None):
        """A player is harmed (nothing in Sandbox). The Shield soaks hits, zaps, grabs and pulses first; at no Health
        they are knocked out and reboot at their Recharge Pod."""
        if p.creative or amount <= 0:
            return
        now = self.now()
        if why in ("hit", "zap", "grab") and now - p.hurt_at < 0.5:
            return
        p.harm_at = now
        s = p.state
        if why in SHIELD_STOPS and p.shield > 0:  # (the Shield takes it all, until it is empty; the suit wears)
            soak = min(p.shield, amount)
            p.shield -= soak
            amount -= int(math.ceil(soak))
            broke = [B.name_of(a[0]) for k, a in enumerate(p.suit) if a and items.wear(p.suit, k)]
            for name in broke:
                self.say(p.pid, f"Your {name.lower()} wore out!")
            self.inv_changed(p.pid)
            if broke:
                self.events.append(("wear", p.pid))
            self.sound("shield", s["x"], s["y"], s["z"] + 1, 0.7)
            s["shield"] = int(p.shield)
        if amount > 0:
            p.hurt_at = now
            s["hp"] = max(0, s["hp"] - int(amount))
            self.sound("hurt", s["x"], s["y"], s["z"])
        if knock is not None:
            s["vx"] += knock[0]
            s["vy"] += knock[1]
            s["vz"] = max(s["vz"], knock[2] if len(knock) > 2 else 4.0)
        if s["hp"] <= 0:
            self.knocked_out(p, why)

    def knocked_out(self, p, why):
        s = p.state
        p.stats["deaths"] = p.stats.get("deaths", 0) + 1
        words = {"fell": "fell too far", "drowned": "ran out of air", "magma": "touched magma", "spiky": "hugged a cactus",
                 "hit": "was knocked out", "zap": "was zapped by a Glitch", "grab": "was grabbed by a Rust Walker",
                 "pulse": "was caught in an Overload pulse"}
        self.events.append(("news", f"{p.name} {words.get(why, 'was knocked out')}"))
        if not self.rules["keep_items"]:
            for box in (p.inv, p.suit):
                for i, slot in enumerate(box):
                    if slot:
                        self.drop(slot[0], slot[1], s["x"], s["y"], s["z"] + 1, wear=slot[2])
                        box[i] = None
            self.inv_changed(p.pid)
            self.events.append(("wear", p.pid))
        s.update(x=p.spawn[0], y=p.spawn[1], z=p.spawn[2], vx=0.0, vy=0.0, vz=0.0, hp=HEALTH, fall=0.0)
        p.energy = max(p.energy, float(POD_ENERGY))
        p.air, p.shield = AIR, 0.0
        self.place_safely(p)
        self.say(p.pid, ("Rebooted at your Recharge Pod." if p.has_pod else "Rebooted.") +
                 ("" if self.rules["keep_items"] else " Your things are where you fell."))

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
                p.selected = int(m.get("slot", 0)) % items.TOOLBELT
            elif kind == "dig_start":
                p.dig = (int(m["x"]), int(m["y"]), int(m["z"]), self.now())
                p.swing = 0.3
            elif kind == "dig":
                self.dig(p, int(m["x"]), int(m["y"]), int(m["z"]))
            elif kind == "place":
                self.place(p, int(m["x"]), int(m["y"]), int(m["z"]), tuple(int(v) for v in m.get("face", (0, 0, 1))[:3]))
            elif kind == "right":  # (a right click on a block: what it does, else what you hold is put beside it)
                x, y, z = int(m["x"]), int(m["y"]), int(m["z"])
                face = tuple(int(v) for v in m.get("face", (0, 0, 1))[:3])
                if p.input[2] & sim.CAREFUL_B or not self.use_block(pid, x, y, z):
                    held, _ = p.held()
                    if held and (held.get("food") or held.get("suit") is not None) and held.get("block") is None:
                        self.use_item(p)
                    else:
                        self.place(p, x + face[0], y + face[1], z + face[2], face)
            elif kind == "use_item":
                self.use_item(p)
            elif kind == "attack":
                self.attack(p, int(m.get("target", -1)))
            elif kind == "use_mob":
                self.use_mob(p, int(m.get("target", -1)))
            elif kind == "click":
                self.click(p, str(m.get("area", "")), int(m.get("slot", 0)), bool(m.get("right")), bool(m.get("shift")))
            elif kind == "build":
                self.build(p, int(m.get("bp", -1)))
            elif kind == "sort":
                items.sort(p.inv, items.TOOLBELT)
                self.inv_changed(pid)
            elif kind == "locker_name":
                self.name_locker(p, str(m.get("name", "")))
            elif kind == "tab":
                p.tab = m.get("tab") if m.get("tab") in ("backpack", "blueprints", "bot") else "backpack"
            elif kind == "close":
                self.close(p)
            elif kind == "drop":
                self.drop_held(p, bool(m.get("all")))
            elif kind == "pick" and p.creative:
                item_id = int(m.get("item", 0))
                if item_id in B.ITEMS:
                    p.inv[p.selected] = items.new_slot(item_id, items.stack_max(item_id))
                    self.inv_changed(pid)
            elif kind == "creative_take" and p.creative:  # (the Sandbox palette: any item onto the cursor)
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
            if started is None or self.now() - started < t - DIG_SLACK:
                self.refuse(p, x, y, z)
                return
        p.dig = None
        meta = w.get_meta(x, y, z)
        if b["key"] in ("door", "door_top"):  # (a door comes out whole)
            other = z + 1 if b["key"] == "door" else z - 1
            if w.get(x, y, other) in (ID["door"], ID["door_top"]):
                w.set(x, y, other, 0)
        if b["use"] == "locker":
            for s in (self.lockers.pop((x, y, z), None) or {}).get("slots", []):
                if s:
                    self.drop(s[0], s[1], x + 0.5, y + 0.5, z + 0.5, wear=s[2])
        if b["use"] == "refinery":
            for s in (self.refineries.pop((x, y, z), None) or {}).get("slots", []):
                if s:
                    self.drop(s[0], s[1], x + 0.5, y + 0.5, z + 0.5, wear=s[2])
        self.overloads.pop((x, y, z), None)
        w.set(x, y, z, 0)
        self.burst(x, y, z, b["tiles"][1] if b["tiles"] else "particle")
        self.sound("dig_" + (b["tool"] or "soft"), x + 0.5, y + 0.5, z + 0.5)
        if not p.creative:
            for item_id, n in self.drops(bid, meta, enough):
                self.drop(item_id, n, x + 0.5, y + 0.5, z + 0.5)
            if held and held.get("tool") and items.wear(p.inv, p.selected):
                self.say(p.pid, f"Your {held['name']} wore out!")
                self.sound("break", *sim.eye(p.state))
            self.tire(p, DRAIN["dig"])
            self.inv_changed(p.pid)
        p.stats["mined"][b["key"]] = p.stats["mined"].get(b["key"], 0) + 1
        self.notes.append((p.pid, "mined", b["key"]))
        self.after_change(x, y, z)

    def drops(self, bid, meta, enough):
        key = B.BLOCKS[bid]["key"]
        r = self.rng.random()
        if key in ("leaves", "pale_leaves", "pine_leaves", "glowfruit_leaves"):
            out = []
            if r < 0.08:
                out.append((I["sapling"], 1))
            if key == "leaves" and self.rng.random() < 0.04:
                out.append((I["apple"], 1))
            if key == "glowfruit_leaves":
                out.append((I["glowfruit"], 1))
            return out
        if key == "tall_grass":
            return [(I["root"], 1)] if r < 0.1 else []
        if key == "grain":
            return [(I["wheat"], 2), (I["seed_pack"], 1 + (r < 0.5))] if meta >= 3 else [(I["seed_pack"], 1)]
        if key == "berry_bush":
            return [(I["berries"], 1 + (meta > 0))] + ([(I["sapling"], 1)] if r < 0.15 else [])
        if key == "grit" and r < 0.1:
            return [(I["rubble"], 1)]
        return B.drops_of(bid, enough)

    def refuse(self, p, x, y, z):
        """A change the server won't make: the block as it is sent back to that player (their window had shown it
        changed)."""
        self.events.append(("block", p.pid, x, y, z))

    def place(self, p, x, y, z, face):
        """Something held put into the world at (x, y, z) (the open block beside the face clicked): a block, a
        glowstick, a door, a ladder, a Pod, a seed pack, water."""
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
        if key == "water_canister":
            if replace and here != ID["water"]:
                w.set(x, y, z, ID["water"], 0)
                self.water.add((x, y, z))
                if not p.creative:
                    p.inv[p.selected] = items.new_slot(I["canister"])
                self.sound("splash", x + 0.5, y + 0.5, z + 0.5)
                self.inv_changed(p.pid)
            return
        if key == "seed_pack":
            if here == 0 and below == ID["grow_bed"]:
                self.put(p, x, y, z, ID["grain"], 0, slot)
            else:
                self.refuse(p, x, y, z)
                self.say(p.pid, "Seed packs grow in a Grow bed (a Fabricator blueprint).")
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
        if b["shape"] in ("cross", "crop") and below not in (ID["turf"], ID["soil"], ID["grow_bed"], ID["sand"]):
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
        if b["use"] == "refinery":
            self.refineries[(x, y, z)] = new_refinery()
        if b["use"] == "locker":
            self.lockers[(x, y, z)] = {"slots": [None] * items.LOCKER, "name": ""}
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

    def open_screen(self, p, kind, where, tab="backpack"):
        self.close(p)
        p.open, p.tab = (kind, where), tab
        self.events.append(("open", p.pid, kind, where))
        self.inv_changed(p.pid)

    def use_block(self, pid, x, y, z):
        """Right click on a block: what it does (a screen opens, a door, a Pod, berries, a rift patched). Returns True
        if it did something (else the window places what it holds instead)."""
        p = self.players.get(pid)
        if p is None or not self.reach_ok(p, x, y, z):
            return False
        w = self.world
        bid = w.get(x, y, z)
        b = B.BLOCKS[bid]
        use = b["use"]
        held, slot = p.held()
        if held and held["key"] == "canister" and bid == ID["water"] and w.get_meta(x, y, z) == 0:
            w.set(x, y, z, 0)
            self.after_change(x, y, z)
            if not p.creative:
                items.use_up(p.inv, p.selected)
                items.add(p.inv, I["water_canister"], 1)
                self.inv_changed(pid)
            self.sound("splash", x + 0.5, y + 0.5, z + 0.5)
            return True
        if held and held["key"] == "water_canister" and bid in (ID["grow_bed"], ID["grain"]):
            bed = (x, y, z) if bid == ID["grow_bed"] else (x, y, z - 1)
            for dx in (-1, 0, 1):  # (it waters the beds round it too)
                for dy in (-1, 0, 1):
                    if w.get(bed[0] + dx, bed[1] + dy, bed[2]) == ID["grow_bed"]:
                        self.watered[(bed[0] + dx, bed[1] + dy, bed[2])] = self.day
            if not p.creative:
                p.inv[p.selected] = items.new_slot(I["canister"])
                self.inv_changed(pid)
            self.sound("splash", x + 0.5, y + 0.5, z + 1, 0.6)
            self.say(pid, "Grow bed watered for today.")
            return True
        if use in ("locker", "refinery"):
            if use == "locker":
                self.lockers.setdefault((x, y, z), {"slots": [None] * items.LOCKER, "name": ""})
            else:
                self.refineries.setdefault((x, y, z), new_refinery())
            self.open_screen(p, use, (x, y, z))
            self.sound("open", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "fabricator":
            self.open_screen(p, "fabricator", (x, y, z), "blueprints")
            self.sound("open", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "door":
            lower = z if b["key"] == "door" else z - 1
            meta = w.get_meta(x, y, lower) ^ 4
            w.set(x, y, lower, ID["door"], meta)
            if w.get(x, y, lower + 1) == ID["door_top"]:
                w.set(x, y, lower + 1, ID["door_top"], meta)
            self.sound("door", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "pod":
            return self.use_pod(p, x, y, z)
        if use == "berries" and w.get_meta(x, y, z) > 0:
            w.set(x, y, z, bid, 0)
            items.add(p.inv, I["berries"], 2)
            if self.rng.random() < 0.25:
                items.add(p.inv, I["seed_pack"], 1)
                self.say(pid, "A seed pack was in the bush!")
            self.inv_changed(pid)
            self.sound("pop", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "glowfruit":
            w.set(x, y, z, ID["leaves"])
            items.add(p.inv, I["glowfruit"], 1)
            self.inv_changed(pid)
            self.sound("pop", x + 0.5, y + 0.5, z + 0.5)
            return True
        if use == "overload":
            self.say(pid, "An Overload Cell is armed by a Craft Bot (\"use\") or a Glitch shard thrown at it (X).")
            return True
        if use == "rift":
            rid = self.rift_at(x, y, z)
            if held and held["key"] == "patch" and rid is not None:
                if not p.creative:
                    items.use_up(p.inv, p.selected)
                    self.inv_changed(pid)
                self.close_rift(rid, by=p)
                return True
            self.say(pid, "A Glitch rift: put a Patch on it to close it (a Fabricator blueprint: a Battery and 2 Copper).")
            return True
        if use == "dock":  # (your Craft Bot rolls out on top; the Backpack's Bot tab shows what it carries)
            bot = self.bot_of(pid)
            if bot is None:
                bot = self.add_bot(pid, (x, y, z))
                bot.facing = int(round(p.look[0] / 90.0)) % 4  # (facing the way you look: it digs where you were)
                bot.settle()
                self.say(pid, f"{bot_name(self, pid)} online. Upload its brain (U), then P for the autopilot.")
            elif tuple(bot.dock) != (x, y, z) or bot.brain is None:
                bot.dock = (x, y, z)
                bot.home()
            self.open_screen(p, "bot", bot.id, "bot")
            self.sound("open", x + 0.5, y + 0.5, z + 0.5)
            return True
        return False

    def use_pod(self, p, x, y, z):
        """A Recharge Pod: your wake point, at any time; your Energy topped up to 60 once every five minutes; from
        dusk to dawn you rest in it (and the night speeds by when everyone is resting)."""
        pid = p.pid
        p.spawn = (x + 0.5, y + 0.5, z + 1.0)
        first = not p.has_pod
        p.has_pod = True
        words = ["Wake point set."]
        if self.now() - p.pod_at >= POD_EVERY and p.energy < POD_ENERGY and not p.creative:
            p.energy = float(POD_ENERGY)
            p.pod_at = self.now()
            words.append(f"Recharged: Energy {POD_ENERGY}.")
            self.sound("pod", x + 0.5, y + 0.5, z + 0.5)
        elif first:
            self.sound("pod", x + 0.5, y + 0.5, z + 0.5, 0.6)
        if self.is_night():
            p.asleep = True
            p.state.update(x=x + 0.5, y=y + 0.5, z=z + 0.6, vx=0.0, vy=0.0, vz=0.0)
            p.state["flags"] |= sim.F_SLEEP
            words.append("Resting: the night speeds by when everyone is in a Pod.")
            self.try_sleep()
        self.say(pid, " ".join(words))
        return True

    def try_sleep(self):
        awake = [q for q in self.players.values() if not q.asleep]
        if awake or not self.is_night():
            return
        if self.speed == 1.0:
            self.speed = FAST_NIGHT
            self.events.append(("news", "Everyone is resting: the night speeds by"))

    def wake_all(self):
        self.speed = 1.0
        for q in self.players.values():
            if q.asleep:
                q.asleep = False
                q.state["flags"] &= ~sim.F_SLEEP
                q.stats["slept"] = q.stats.get("slept", 0) + 1
                self.notes.append((q.pid, "slept", "pod"))
                self.say(q.pid, "Good morning! Bot online.")

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

    def use_item(self, p):
        """Right click with nothing to click on: put a suit piece on, eat what you hold (when you need Energy); a Bot
        kit calls your Bot back to its dock."""
        held, slot = p.held()
        if held and held.get("suit") is not None:  # (put on: what was worn there goes in your hand)
            k = held["suit"]
            p.inv[p.selected], p.suit[k] = p.suit[k], p.inv[p.selected]
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
            if p.energy >= ENERGY and not p.creative:
                self.say(p.pid, "Your Energy is full.")
                return
            p.energy = min(float(ENERGY), p.energy + held["food"])
            p.state["energy"] = int(math.ceil(p.energy))
            if not p.creative:
                items.use_up(p.inv, p.selected)
                self.inv_changed(p.pid)
            p.stats["eaten"] = p.stats.get("eaten", 0) + 1
            self.notes.append((p.pid, "ate", held["key"]))
            self.sound("eat", *sim.eye(p.state))

    def attack(self, p, target):
        """A hit on a creature (or, with pvp on, another player) within reach: a Zapper's harm, else a hand's."""
        held, slot = p.held()
        zapper = held is not None and held.get("tool") == "zapper"
        dmg = held["damage"] if zapper else B.HAND["damage"]
        p.swing = 0.3
        ex, ey, ez = sim.eye(p.state)
        if target in self.players and self.rules["pvp"] and target != p.pid:
            q = self.players[target]
            if math.dist((ex, ey, ez), (q.state["x"], q.state["y"], q.state["z"] + 0.9)) < 4.0:
                yaw = math.radians(p.look[0])
                self.hurt(q, dmg, "hit", knock=(math.cos(yaw) * 5, math.sin(yaw) * 5))
            return
        m = self.mobs.mobs.get(target)
        if m is not None and m["kind"] == "fluff" and zapper:
            self.say(p.pid, "The Zapper won't fire at a Fluff.")
            return
        if self.mobs.hit(target, dmg, (ex, ey, ez), p):
            if zapper and items.wear(p.inv, p.selected):
                self.say(p.pid, f"Your {held['name']} wore out!")
            self.inv_changed(p.pid)

    def use_mob(self, p, target):
        """A right click on a creature: brush a Fluff with an empty hand (Fluff for you; it grows back), give a Bleep
        3 Scrap (it gives you a part back, once a day)."""
        m = self.mobs.mobs.get(target)
        if m is None:
            return
        s = m["s"]
        ex, ey, ez = sim.eye(p.state)
        if math.dist((ex, ey, ez), (s["x"], s["y"], s["z"] + 0.6)) > 4.2:
            return
        held, slot = p.held()
        if m["kind"] == "fluff":
            if held is not None:
                self.say(p.pid, "Brush a Fluff with an empty hand.")
                return
            if self.mobs.brushed(m):
                self.say(p.pid, "This Fluff is fluffing up again: try another.")
                return
            n = self.rng.randint(1, 2)
            items.add(p.inv, I["fluff"], n)
            self.mobs.brush(m)
            p.stats["brushed"] = p.stats.get("brushed", 0) + 1
            self.notes.append((p.pid, "brushed", "fluff"))
            self.sound("fluff_chirp", s["x"], s["y"], s["z"])
            self.inv_changed(p.pid)
        elif m["kind"] == "bleep":
            if not (held and held["key"] == "scrap" and slot[1] >= 3):
                self.say(p.pid, "Bleeps trade: give one 3 Scrap (hold it and right-click).")
                return
            if m["mem"].get("traded") == self.day:
                self.say(p.pid, "This Bleep has traded today. Bleep bloop.")
                return
            m["mem"]["traded"] = self.day
            items.take(p.inv, I["scrap"], 3)
            part = self.rng.choice(("coal", "copper_ingot", "battery"))
            items.add(p.inv, I[part], 1)
            if self.rng.random() < 0.5:
                items.add(p.inv, I["seed_pack"], 1)
            p.stats["traded"] = p.stats.get("traded", 0) + 1
            self.notes.append((p.pid, "traded", part))
            self.sound("beep_happy", s["x"], s["y"], s["z"])
            self.say(p.pid, f"The Bleep beeps happily: {B.name_of(I[part])} for you.")
            self.inv_changed(p.pid)

    # ---------- blueprints ----------
    def near_fabricator(self, p):
        """Is a Fabricator within 4 blocks of the player?"""
        s = p.state
        x0, y0, z0 = (int(math.floor(v)) for v in (s["x"], s["y"], s["z"] + 1))
        fab = ID["fabricator"]
        for dx in range(-4, 5):
            for dy in range(-4, 5):
                for dz in range(-4, 5):
                    if self.world.get(x0 + dx, y0 + dy, z0 + dz) == fab and \
                            math.dist((s["x"], s["y"], s["z"] + 1), (x0 + dx + 0.5, y0 + dy + 0.5, z0 + dz + 0.5)) <= \
                            items.REACH + 0.9:
                        return True
        return False

    def build(self, p, index):
        """Build a blueprint: its parts taken now, the thing made when its seconds are up (in the Backpack, even
        if you've walked away)."""
        bps = items.blueprints()
        if not 0 <= index < len(bps):
            return
        bp = bps[index]
        name = B.name_of(I[bp["makes"]])
        if not p.creative:
            if not items.unlocked(bp, p.seen):
                self.say(p.pid, f"{name}: hold one of each part first to unlock it.")
                return
            if bp["station"] != "hand" and not self.near_fabricator(p):
                self.say(p.pid, f"{name} needs a Fabricator within 4 blocks.")
                return
            if len(p.building) >= items.MAX_BUILDS:
                self.say(p.pid, f"The build queue is full ({items.MAX_BUILDS}).")
                return
            if not items.take_parts(p.inv, bp):
                self.say(p.pid, f"{name}: not enough parts yet.")
                return
        secs = 0.05 if p.creative else bp["seconds"]
        p.building.append({"makes": bp["makes"], "count": bp["count"], "left": secs, "total": secs})
        self.sound("open", *sim.eye(p.state), 0.4)
        self.inv_changed(p.pid)

    def step_builds(self, p, dt):
        if not p.building:
            return
        job = p.building[0]
        job["left"] -= dt
        if job["left"] > 0:
            if self.tick % 15 == 0:
                self.events.append(("inv", p.pid))  # (the progress bar moves on)
            return
        p.building.pop(0)
        item_id = I[job["makes"]]
        left = items.add(p.inv, item_id, job["count"])
        if left:
            self.drop(item_id, left, *sim.eye(p.state), wait=1.0)
        p.stats["built"][job["makes"]] = p.stats["built"].get(job["makes"], 0) + job["count"]
        self.notes.append((p.pid, "built", job["makes"]))
        self.sound("build_done", *sim.eye(p.state))
        self.say(p.pid, f"Built: {job['count']} {B.name_of(item_id)}" if job["count"] > 1 else f"Built: {B.name_of(item_id)}")
        self.inv_changed(p.pid)

    # ---------- the screens ----------
    def click(self, p, area, i, right, shift):
        """A click in an open screen: the Backpack and Toolbelt, the suit, a Locker, a Refinery, the Bot's slots."""
        if area == "inv" and 0 <= i < items.SLOTS:
            if shift and p.cursor is None and p.inv[i]:
                self.shift_move(p, i)
            else:
                p.cursor = items.click(p.inv, i, p.cursor, right)
        elif area == "suit" and 0 <= i < items.SUIT:  # (only the piece for that slot goes in)
            if shift and p.cursor is None and p.suit[i]:
                if not items.add(p.inv, p.suit[i][0], wear=p.suit[i][2]):
                    p.suit[i] = None
            elif p.cursor is None or items.suit_part(p.cursor[0]) == i:
                p.cursor, p.suit[i] = p.suit[i], p.cursor
            self.events.append(("wear", p.pid))
        elif area == "locker" and p.open and p.open[0] == "locker":
            box = (self.lockers.get(p.open[1]) or {}).get("slots")
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
        elif area == "refinery" and p.open and p.open[0] == "refinery":
            rf = self.refineries.get(p.open[1])
            if rf is not None and 0 <= i < items.REFINERY:
                slots = rf["slots"]
                tray = i > items.POWER_SLOT
                fits = p.cursor is None or (p.cursor[0] in B.FUEL if i == items.POWER_SLOT else
                                            p.cursor[0] in B.REFINES if i < items.POWER_SLOT else True)
                if shift and slots[i] and p.cursor is None:
                    s = slots[i]
                    left = items.add(p.inv, s[0], s[1], wear=s[2])
                    slots[i] = None if not left else [s[0], left, s[2]]
                    if tray and not left:
                        self.refined(p, s[0], s[1])
                elif fits:
                    before = slots[i]
                    p.cursor = items.click(slots, i, p.cursor, right, takes_only=tray)
                    if tray and before and slots[i] is None:
                        self.refined(p, before[0], before[1])
                self.events.append(("box", p.open[1]))
        self.inv_changed(p.pid)

    def shift_move(self, p, i):
        """Shift-click in the Backpack: into an open Locker or Refinery, a suit piece onto you, else between the
        Toolbelt and the Backpack."""
        s = p.inv[i]
        k = items.suit_part(s[0])
        if k is not None and p.suit[k] is None and not (p.open and p.open[0] in ("locker", "bot", "refinery")):
            p.suit[k], p.inv[i] = s, None
            self.events.append(("wear", p.pid))
            return
        if p.open and p.open[0] == "locker" and p.open[1] in self.lockers:
            left = items.add(self.lockers[p.open[1]]["slots"], s[0], s[1], wear=s[2])
            self.events.append(("box", p.open[1]))
        elif p.open and p.open[0] == "bot" and p.open[1] in self.bots:
            left = items.add(self.bots[p.open[1]].inv, s[0], s[1], wear=s[2])
        elif p.open and p.open[0] == "refinery" and p.open[1] in self.refineries:
            slots = self.refineries[p.open[1]]["slots"]
            if s[0] in B.REFINES:
                left = items.add(slots, s[0], s[1], order=list(range(items.QUEUE)), wear=s[2])
            elif s[0] in B.FUEL:
                left = items.add(slots, s[0], s[1], order=[items.POWER_SLOT], wear=s[2])
            else:
                left = s[1]
            self.events.append(("box", p.open[1]))
        else:
            order = range(items.TOOLBELT, items.SLOTS) if i < items.TOOLBELT else range(items.TOOLBELT)
            left = items.add(p.inv, s[0], s[1], order=list(order), wear=s[2])
            if left == s[1]:
                return
            p.inv[i] = None if not left else [s[0], left, s[2]]
            return
        p.inv[i] = None if not left else [s[0], left, s[2]]

    def name_locker(self, p, name):
        if p.open and p.open[0] == "locker" and p.open[1] in self.lockers:
            clean = "".join(ch for ch in name if ch.isprintable())[:20].strip()
            self.lockers[p.open[1]]["name"] = clean
            self.events.append(("box", p.open[1]))

    def refined(self, p, item_id, n):
        key = B.ITEMS[item_id]["key"]
        p.stats["refined"][key] = p.stats["refined"].get(key, 0) + n
        self.notes.append((p.pid, "refined", key))

    def close(self, p):
        """A screen closed: the cursor's things go back into the Backpack."""
        if p.cursor:
            left = items.add(p.inv, p.cursor[0], p.cursor[1], wear=p.cursor[2])
            if left:
                self.drop(p.cursor[0], left, *sim.eye(p.state), wear=p.cursor[2])
            p.cursor = None
        p.open = None
        self.inv_changed(p.pid)

    def drop_held(self, p, everything=False):
        """X: throw what you hold (one, or the stack with Ctrl) in front of you."""
        held, slot = p.held()
        if not slot:
            return
        n = slot[1] if everything else 1
        yaw, pitch = math.radians(p.look[0]), math.radians(p.look[1])
        ex, ey, ez = sim.eye(p.state)
        self.drop(slot[0], n, ex + math.cos(yaw) * 0.6, ey + math.sin(yaw) * 0.6, ez - 0.2, wear=slot[2], wait=1.5,
                  throw=(math.cos(yaw) * math.cos(pitch) * 7, math.sin(yaw) * math.cos(pitch) * 7,
                         2.5 + math.sin(pitch) * 7), by=p.pid)
        items.use_up(p.inv, p.selected, n)
        self.inv_changed(p.pid)

    # ---------- things dropped ----------
    def drop(self, item_id, n, x, y, z, wear=None, wait=0.4, throw=None, by=None):
        if len(self.items) >= min(MAX_ITEMS, ITEM_LAST - ITEM_BASE + 1):
            oldest = max(self.items, key=lambda k: self.items[k]["age"])
            del self.items[oldest]
        eid = next(i for i in range(ITEM_BASE, ITEM_LAST + 1) if i not in self.items)
        vx, vy, vz = throw or (0.0, 0.0, 2.0)
        self.items[eid] = {"id": eid, "item": item_id, "count": n, "wear": wear, "x": x, "y": y, "z": z, "vx": vx,
                           "vy": vy, "vz": vz, "age": 0.0, "wait": wait, "by": by}

    def step_items(self, dt):
        solid, _, _ = sim.tables()
        w = self.world
        for eid, it in list(self.items.items()):
            it["age"] += dt
            it["wait"] -= dt
            if it["age"] > ITEM_LIFE:
                del self.items[eid]
                continue
            if it.get("vx") or it.get("vy"):  # (thrown: it flies until it hits something)
                for key, v in (("x", it["vx"]), ("y", it["vy"])):
                    n = it[key] + v * dt
                    bx, by_ = (n, it["y"]) if key == "x" else (it["x"], n)
                    if solid[w.get(int(math.floor(bx)), int(math.floor(by_)), int(math.floor(it["z"])))]:
                        it["vx"] = it["vy"] = 0.0
                        break
                    it[key] = n
                it["vx"] *= math.exp(-1.5 * dt)
                it["vy"] *= math.exp(-1.5 * dt)
            below = w.get(int(math.floor(it["x"])), int(math.floor(it["y"])), int(math.floor(it["z"] - 0.15)))
            if solid[below] and it["vz"] <= 0:
                it["vz"] = 0.0
                it["vx"] = it["vy"] = 0.0
                it["z"] = math.floor(it["z"] - 0.15) + 1 + 0.15
            else:
                it["vz"] = max(-20.0, it["vz"] - 20 * dt)
                it["z"] += it["vz"] * dt
            if it["item"] == I["glitch_shard"] and it.get("by") is not None and self.shard_hits(it):
                it["count"] -= 1
                if it["count"] <= 0:
                    del self.items[eid]
                    continue
                it["by"] = None
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

    def shard_hits(self, it):
        """A thrown Glitch shard that reaches an Overload Cell arms it (the shard is used up)."""
        x, y, z = (int(math.floor(it[k])) for k in ("x", "y", "z"))
        cell = ID["overload_cell"]
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    pos = (x + dx, y + dy, z + dz)
                    if self.world.get(*pos) == cell and math.dist((it["x"], it["y"], it["z"]),
                                                                  (pos[0] + 0.5, pos[1] + 0.5, pos[2] + 0.5)) < 1.2:
                        return self.arm(*pos, who=it["by"])
        return False

    # ---------- Overload Cells ----------
    def arm(self, x, y, z, who=None):
        """An Overload Cell armed (a Craft Bot's "use", a thrown Glitch shard): it hums and pulses magenta for 3 s,
        then pulses. Returns True if it armed."""
        if (x, y, z) in self.overloads:
            return True
        if not self.rules["blasts"]:
            if who is not None:
                self.say(who, "Overload Cells are switched off in this lesson.")
            return False
        self.overloads[(x, y, z)] = PULSE_SECONDS
        self.sound("overload_hum", x + 0.5, y + 0.5, z + 0.5)
        self.events.append(("armed", x, y, z, PULSE_SECONDS))
        return True

    def pulse(self, x, y, z):
        """An Overload Cell's pulse: the blocks within 2.5 turn into their drops (no crater of lost blocks), people
        near are knocked back and harmed a little (6 at the middle, none at 5 blocks), creatures too; other Cells
        in it are armed. No fire, no smoke: a ring of cyan sparks."""
        w = self.world
        self.sound("overload_pulse", x + 0.5, y + 0.5, z + 0.5, 1.5)
        if w.get(x, y, z) == ID["overload_cell"]:
            w.set(x, y, z, 0)
        changes = []
        r = PULSE_RADIUS
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                for dz in range(-3, 4):
                    if dx * dx + dy * dy + dz * dz > r * r:
                        continue
                    bx, by, bz = x + dx, y + dy, z + dz
                    bid = w.get(bx, by, bz)
                    if not bid or not w.inside(bx, by, bz) or B.BLOCKS[bid]["hard"] is None or bid == ID["dock"]:
                        continue
                    if bid == ID["overload_cell"]:
                        self.overloads.setdefault((bx, by, bz), 0.4)
                        continue
                    changes.append((bx, by, bz, 0, 0))
                    for item_id, n in self.drops(bid, w.get_meta(bx, by, bz), True):
                        self.drop(item_id, n, bx + 0.5, by + 0.5, bz + 0.5)
                    if B.BLOCKS[bid]["use"] in ("locker", "refinery"):
                        box = (self.lockers.pop((bx, by, bz), None) or self.refineries.pop((bx, by, bz), None) or {})
                        for s in box.get("slots", []):
                            if s:
                                self.drop(s[0], s[1], bx + 0.5, by + 0.5, bz + 0.5, wear=s[2])
        w.apply_changes(changes)
        w.changes.extend(changes)
        self.events.append(("ring", x + 0.5, y + 0.5, z + 0.5, PULSE_REACH))
        for p in self.players.values():
            s = p.state
            d = math.dist((s["x"], s["y"], s["z"] + 0.8), (x + 0.5, y + 0.5, z + 0.5))
            if d < PULSE_REACH:
                dx, dy = s["x"] - (x + 0.5), s["y"] - (y + 0.5)
                n = math.hypot(dx, dy) or 1.0
                self.hurt(p, int(round(PULSE_HARM * (1 - d / PULSE_REACH))), "pulse",
                          knock=(dx / n * 11, dy / n * 11, 6.0))
        self.mobs.pulse(x + 0.5, y + 0.5, z + 0.5, PULSE_REACH)

    # ---------- Glitch rifts ----------
    def open_rifts(self):
        """Dusk: one to three Glitch rifts tear open on the surface near the players (a crack two blocks long)."""
        w = self.world
        rng = self.rng
        want = rng.randint(*RIFTS)
        people = list(self.players.values())
        for _ in range(want * 30):
            if len(self.rifts) >= want:
                break
            if people:
                s = rng.choice(people).state
                cx, cy = s["x"], s["y"]
            else:
                cx, cy = w.spawn[0], w.spawn[1]
            a, d = rng.random() * math.tau, 16 + rng.random() * 32
            x, y = int(cx + math.cos(a) * d), int(cy + math.sin(a) * d)
            dx, dy = (1, 0) if rng.random() < 0.5 else (0, 1)
            if not (2 <= x < w.X - 3 and 2 <= y < w.Y - 3):
                continue
            z = w.top(x, y)
            ground = (ID["turf"], ID["soil"], ID["sand"], ID["snow"], ID["grit"])
            if w.get(x, y, z) not in ground or w.top(x + dx, y + dy) != z or w.get(x + dx, y + dy, z) not in ground:
                continue
            if any(math.dist((x, y), r["cells"][0][:2]) < 10 for r in self.rifts.values()):
                continue
            self.make_rift(x, y, z, dx, dy)
        if self.rifts:
            self.events.append(("news", f"Glitch rifts are opening: {len(self.rifts)} of them. Patch them!"))

    def make_rift(self, x, y, z, dx=1, dy=0):
        """A Glitch rift two blocks long in the ground at (x, y, z) and the block beside it (dx, dy)."""
        w = self.world
        cells = [(x, y, z), (x + dx, y + dy, z)]
        self.rift_n += 1
        self.rifts[self.rift_n] = {"cells": cells, "was": [w.get(*c) for c in cells], "timer": 3.0 + self.rng.random() * 6,
                                   "glitches": []}
        for c in cells:
            if B.BLOCKS[w.get(c[0], c[1], c[2] + 1)]["shape"] in ("cross", "crop"):
                w.set(c[0], c[1], c[2] + 1, 0)
            w.set(*c, ID["glitch_rift"])
        self.sound("rift_open", x + 0.5, y + 0.5, z + 1)
        self.burst(x, y, z + 1, "rift_top", 20)
        return self.rift_n

    def rift_at(self, x, y, z):
        return next((rid for rid, r in self.rifts.items() if (x, y, z) in [tuple(c) for c in r["cells"]]), None)

    def close_rift(self, rid, by=None):
        """A rift seals (a Patch on it, or dawn): the ground back as it was; its Glitches are pulled back in."""
        r = self.rifts.pop(rid, None)
        if r is None:
            return
        w = self.world
        for c, was in zip(r["cells"], r["was"]):
            if w.get(*c) == ID["glitch_rift"]:
                w.set(*c, was)
        x, y, z = r["cells"][0]
        self.sound("rift_close", x + 0.5, y + 0.5, z + 1)
        self.burst(x, y, z + 1, "rift_top", 24)
        for mid in r["glitches"]:
            self.mobs.pull_back(mid, (x + 0.5, y + 0.5, z + 1))
        if by is not None:
            by.stats["rifts"] = by.stats.get("rifts", 0) + 1
            self.notes.append((by.pid, "patched", "rift"))
            self.events.append(("news", f"{by.name} patched a Glitch rift!"))

    def step_rifts(self, dt):
        for rid, r in list(self.rifts.items()):
            r["timer"] -= dt
            if r["timer"] > 0:
                continue
            r["timer"] = RIFT_EVERY
            r["glitches"] = [g for g in r["glitches"] if g in self.mobs.mobs]
            if len(r["glitches"]) < RIFT_MOST and self.rules["mobs"] and self.players:
                x, y, z = r["cells"][self.rng.randrange(len(r["cells"]))]
                mid = self.mobs.add("glitch", x + 0.5, y + 0.5, float(z + 1))
                if mid is not None:
                    self.mobs.mobs[mid]["mem"]["rift"] = rid
                    r["glitches"].append(mid)
                    self.sound("blink", x + 0.5, y + 0.5, z + 1)

    # ---------- the world's slow things ----------
    def world_tick(self):
        dt = WORLD_TICK
        self.refining(dt)
        self.random_ticks()
        self.flow_water()
        for pos in list(self.overloads):
            self.overloads[pos] -= dt
            if self.overloads[pos] <= 0:
                del self.overloads[pos]
                if self.world.get(*pos) == ID["overload_cell"]:
                    self.pulse(*pos)
        self.step_rifts(dt)
        phase = self.phase()
        by_clock = 0 <= self.time - self.time_was <= SET_BY_HAND
        self.time_was = self.time
        if phase != self.phase_was:
            dark, was_dark = phase in ("dusk", "night"), self.phase_was in ("dusk", "night")
            if dark and not was_dark:  # (the time set straight to night, past dusk: dusk's things all the same)
                phase = "dusk"
            elif was_dark and not dark:  # (straight to day, past dawn)
                phase = "dawn"
            if phase == "dusk":
                # The world's first night, come round on the clock, is quiet: no rifts, time to build a Patch.
                # (A dusk the teacher or a lesson sets opens them, so they can be shown any time.)
                quiet = by_clock and self.day == 0
                if self.rules["mobs"] and not quiet:
                    self.open_rifts()
                self.events.append(("news", "Dusk" if not self.rules["mobs"] else
                                    "Dusk: the Rust Walkers stir. The first night is quiet: no rifts tonight" if quiet
                                    else "Dusk: the Rust Walkers stir, and rifts are opening"))
            if phase == "dawn":  # (dawn: the rifts seal, and everyone who was here all night survived it)
                for rid in list(self.rifts):
                    self.close_rift(rid)
                self.mobs.dawn()
                self.wake_all()
                for q in self.players.values():
                    q.stats["nights"] = q.stats.get("nights", 0) + 1
                    self.notes.append((q.pid, "survived", "night"))
                self.events.append(("news", "The sun is up: you survived the night!"))
            self.phase_was = self.phase()
        if self.speed > 1 and (not self.is_night() or any(not q.asleep for q in self.players.values())):
            self.wake_all() if not self.is_night() else setattr(self, "speed", 1.0)

    def refining(self, dt):
        """Each Refinery: the first thing in its queue that it can refine, 6 s an item, one item of power each (a
        Battery's 12, Coal's 6, a Log's 2, Boards' 1, taken from the power slot when the gauge is empty)."""
        w = self.world
        for pos, rf in self.refineries.items():
            slots = rf["slots"]
            job = None
            for k in range(items.QUEUE):
                s = slots[k]
                if s and s[0] in B.REFINES and s[1] >= B.REFINE_TAKES.get(s[0], 1):
                    out = B.REFINES[s[0]]
                    tray = slots[items.POWER_SLOT + 1:]
                    if any(t is None or (t[0] == out and t[1] < items.stack_max(out)) for t in tray):
                        job = (k, out)
                        break
            if job is not None and rf["power"] < 1:
                fuel = slots[items.POWER_SLOT]
                if fuel is not None and fuel[0] in B.FUEL:
                    rf["power"] += B.FUEL[fuel[0]]
                    rf["power_max"] = max(rf.get("power_max", 0), rf["power"])
                    items.use_up(slots, items.POWER_SLOT)
            working = job is not None and rf["power"] >= 1
            if working:
                rf["progress"] += dt
                if rf["progress"] >= B.REFINE_SECONDS:
                    rf["progress"] = 0.0
                    k, out = job
                    items.use_up(slots, k, B.REFINE_TAKES.get(slots[k][0], 1))
                    tray = slots[items.POWER_SLOT + 1:]
                    items.add(tray, out, 1)
                    slots[items.POWER_SLOT + 1:] = tray
                    rf["power"] -= 1
                    self.events.append(("box", pos))
            else:
                rf["progress"] = max(0.0, rf["progress"] - dt * 2)
            want = ID["refinery_on"] if working else ID["refinery"]
            if w.get(*pos) in (ID["refinery"], ID["refinery_on"]) and w.get(*pos) != want:
                w.set(*pos, want, w.get_meta(*pos))
            if self.tick % 15 == 0:
                self.events.append(("box", pos))

    def random_ticks(self):
        """A few blocks a chunk looked at each world tick: grain grows (watered), saplings become trees, turf
        spreads onto soil, berry bushes grow berries again."""
        w = self.world
        for cx, cy in w.chunks:
            for _ in range(RANDOM_TICKS):
                x = cx * 16 + self.rng.randrange(16)
                y = cy * 16 + self.rng.randrange(16)
                z = self.rng.randrange(2, w.Z - 1)
                bid = w.blocks[x, y, z]
                if bid == 0 or bid == ID["stone"]:
                    continue
                if bid == ID["grain"]:
                    m = w.get_meta(x, y, z)
                    lit = max(w.sky[x, y, z] * (0 if self.is_night() else 1), w.glow[x, y, z]) >= 8
                    if m < 3 and lit and self.watered_bed(x, y, z - 1) and self.rng.random() < 0.5:
                        w.set(x, y, z, bid, m + 1, light=False)
                elif bid == ID["sapling"]:
                    if self.rng.random() < 0.3 and w.sky[x, y, z] >= 8:
                        self.grow_tree(x, y, z)
                elif bid == ID["soil"] and w.get(x, y, z + 1) == 0 and w.sky[x, y, z + 1] >= 8:
                    if any(w.get(x + dx, y + dy, z + dz) == ID["turf"] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           for dz in (-1, 0, 1)):
                        w.set(x, y, z, ID["turf"], light=False)
                elif bid == ID["turf"] and B.BLOCKS[w.get(x, y, z + 1)]["opaque"]:
                    w.set(x, y, z, ID["soil"], light=False)
                elif bid == ID["berry_bush"] and w.get_meta(x, y, z) == 0 and self.rng.random() < 0.2:
                    w.set(x, y, z, bid, 1, light=False)

    def watered_bed(self, x, y, z):
        """A Grow bed grows its grain if there is water within 3 blocks of it, or a Water canister was poured on it
        today."""
        w = self.world
        if w.get(x, y, z) != ID["grow_bed"]:
            return False
        if self.watered.get((x, y, z)) == self.day:
            return True
        water = ID["water"]
        return any(w.get(x + dx, y + dy, z + dz) == water for dx in range(-3, 4) for dy in range(-3, 4) for dz in (-1, 0))

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
        it pop off, a glowstick with nothing under it falls."""
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
                self.sound("dig_scoop", x + 0.5, y + 0.5, z + 0.5, 0.6)
            elif ab["shape"] in ("cross", "crop", "torch") or above == ID["door_top"]:
                meta = w.get_meta(x, y, z + 1)
                w.set(x, y, z + 1, 0)
                for item_id, n in self.drops(above, meta, True):
                    self.drop(item_id, n, x + 0.5, y + 0.5, z + 1.5)
        for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, 0)):
            if w.get(x + dx, y + dy, z + dz) == ID["water"]:
                self.water.add((x + dx, y + dy, z + dz))

    def flow_water(self):
        """Water spreads from a source: down first, then sideways up to 4 blocks (meta: 0 a source, 1 to 4 flowing;
        flowing water never makes a new source). Flowing water with nothing feeding it dries up."""
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
            if level >= 4 or w.get(x, y, z - 1) not in (W,) and not B.BLOCKS[w.get(x, y, z - 1)]["solid"]:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = w.get(x + dx, y + dy, z)
                if nb in (0, ID["tall_grass"]) and w.inside(x + dx, y + dy, z):
                    w.set(x + dx, y + dy, z, W, level + 1)
                    self.water.add((x + dx, y + dy, z))

    # ---------- what the window shows ----------
    def inventory_msg(self, pid):
        p = self.players.get(pid)
        if p is None:
            return None
        bps = items.blueprints()
        msg = {"type": "inventory", "inv": p.inv, "cursor": p.cursor, "selected": p.selected,
               "open": p.open[0] if p.open else None, "tab": p.tab, "suit": p.suit, "shield_max": p.shield_max(),
               "creative": p.creative, "building": [dict(b, left=round(b["left"], 2)) for b in p.building],
               "unlocked": [i for i, bp in enumerate(bps) if p.creative or items.unlocked(bp, p.seen)],
               "blueprints_n": len(bps)}
        if p.open and p.open[0] == "locker":
            lk = self.lockers.get(p.open[1]) or {}
            msg["box"], msg["name"] = lk.get("slots"), lk.get("name", "")
        bot = self.bot_of(pid)
        if bot is not None:
            msg["bot"] = {"name": bot_name(self, pid), "error": bot.brain.error if bot.brain else None,
                          "running": bool(bot.brain and not bot.brain.error), "stats": bot.stats,
                          "doing": bot.action[0] if bot.action else "waiting"}
        if p.open and p.open[0] == "bot":
            msg["box"] = bot.inv if bot else [None] * craft_bot.SLOTS
        if p.open and p.open[0] == "refinery":
            rf = self.refineries.get(p.open[1]) or new_refinery()
            msg["box"] = rf["slots"]
            msg["power"] = round(rf["power"], 2)
            msg["power_max"] = max(12, rf.get("power_max", 0))
            msg["progress"] = round(rf["progress"] / B.REFINE_SECONDS, 2)
        return msg

    def save_extra(self):
        """The game's own things kept with the world (Lockers, Refineries, rifts, the time)."""
        return {"time": self.time,
                "lockers": [[list(k), v] for k, v in self.lockers.items()],
                "refineries": [[list(k), v] for k, v in self.refineries.items()],
                "watered": [[list(k), v] for k, v in self.watered.items()],
                "rifts": [dict(r, cells=[list(c) for c in r["cells"]], glitches=[]) for r in self.rifts.values()]}

    def load_extra(self, extra):
        try:
            self.time = float(extra.get("time", self.time))
            self.lockers = {tuple(k): v for k, v in extra.get("lockers", [])}
            self.refineries = {tuple(k): dict(new_refinery(), **v) for k, v in extra.get("refineries", [])}
            self.watered = {tuple(k): int(v) for k, v in extra.get("watered", [])}
            for r in extra.get("rifts", []):
                self.rift_n += 1
                self.rifts[self.rift_n] = dict(r, cells=[tuple(c) for c in r["cells"]], glitches=[])
        except (TypeError, ValueError, KeyError):
            pass
        self.phase_was = self.phase()
        self.fill_ruins()


def new_refinery():
    return {"slots": [None] * items.REFINERY, "power": 0.0, "power_max": 0.0, "progress": 0.0}


def bot_name(game, pid):
    d = game.designs.get(pid)
    name = (d or {}).get("name") or "Craft Bot"
    return "Your Craft Bot" if name in ("You Bot", "Bot") else name
