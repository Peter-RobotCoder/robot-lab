"""Craft Lab's creatures (CHANGE 200; reworked in CHANGE 207), all Club Coders' own:

    FLUFF        a round, floating puff of fluff on two tiny feet that bobs about the turf by day. Brush one with an
                 empty hand (right click) for Fluff; it grows back in three minutes. Harming one gives nothing, and a
                 Zapper won't fire at it.
    BLEEP        a friendly little helper bot that rolls about by day and beeps; it follows anyone holding Scrap.
                 Give it 3 Scrap and it gives back a part (Coal, a Copper ingot or a Battery), once a day.
    GLITCH       a bug that leaked out of the code: a flickering cluster of pixels from a Glitch rift (they open at
                 dusk). It blinks a few blocks towards you every two seconds and zaps from up to 3 blocks away. At
                 dawn the rifts pull their Glitches back in. It drops Glitch shards.
    RUST WALKER  an old broken bot on tracks with a long magnet arm. It lives round a scrap heap in the caves, comes
                 up to the surface only at night, and rolls back home by day. Its magnet grabs (and one grab in four
                 pulls a thing off your Toolbelt, which it drops when it is beaten). It drops Rust and Scrap.

They move as players do (craft_sim.step_player: they bump into blocks, fall, swim) with inputs from their own little
brains, which think ten times a second: wander, follow, chase, flee, go home. Hostile ones only come from the rifts
and the scrap heaps, only while the lesson has creatures on, and none near anyone in the first 30 seconds.
"""
import math

import craft_blocks as B
import craft_items as items
import craft_sim as sim

I, ID = B.ITEM_ID, B.ID
KINDS = {
    #              hp  speed  hostile  height  drops                                     harm
    "fluff": dict(hp=30, speed=1.5, hostile=False, tall=1.0, drops=[], damage=0),
    "bleep": dict(hp=25, speed=2.0, hostile=False, tall=0.9, drops=[("scrap", 1, 2)], damage=0),
    "glitch": dict(hp=40, speed=1.1, hostile=True, tall=1.0, drops=[("glitch_shard", 1, 2)], damage=10),
    "rust": dict(hp=70, speed=2.2, hostile=True, tall=1.6, drops=[("rust", 0, 2), ("scrap", 0, 1)], damage=14),
}
MAX_PASSIVE = 14
PER_HEAP = 2        # Rust Walkers round each scrap heap at once
HEAP_NEAR = 64.0    # a heap's Rust Walkers come out when someone is this near it
HOME_DAY, HOME_NIGHT = 24.0, 48.0   # how far a Rust Walker goes from its heap (it chases you further at night)
THINK = 6           # steps between thoughts (10 a second)
SPAWN_EVERY = 1.0   # seconds between spawning tries
FAR = 80.0          # metres from everyone: it goes
SAFE_START = 30.0   # seconds after the game starts with no hostile ones near anyone
BLINK_EVERY, BLINK_FAR, ZAP_FAR, ZAP_COOL = 2.0, 3.0, 3.0, 1.5
GRAB_FAR, GRAB_COOL, STEAL = 1.7, 1.2, 0.25
REGROW = 180.0      # seconds a brushed Fluff takes to fluff up again
FIRST_ID, LAST_ID = 128, 191  # (their ids on the wire)
SOUNDS = {"fluff": "fluff_chirp", "bleep": "beep", "glitch": "zap", "rust": "clank"}


class Mobs:
    def __init__(self, game):
        self.game = game
        self.mobs = {}       # id -> {"kind", "s" (craft_sim's record), "mem"}
        self.spawn_acc = 0.0
        self.age = 0.0

    def ids(self):
        return list(self.mobs)

    def add(self, kind, x, y, z, home=None):
        mid = next((i for i in range(FIRST_ID, LAST_ID + 1) if i not in self.mobs), None)
        if mid is None:
            return None
        s = sim.new_player(x, y, z, sim.KINDS[kind])
        s["hp"] = KINDS[kind]["hp"]
        self.mobs[mid] = {"kind": kind, "s": s, "mem": {"t": 0, "goal": None, "flee": 0.0, "cool": 0.0, "hurt": 0.0,
                                                         "blink": BLINK_EVERY, "home": home, "stole": [],
                                                         "brushed": -1.0}}
        return mid

    def box_hit(self, x, y, z):
        return any(abs(m["s"]["x"] - (x + 0.5)) < 0.8 and abs(m["s"]["y"] - (y + 0.5)) < 0.8 and
                   m["s"]["z"] - 1 < z < m["s"]["z"] + KINDS[m["kind"]]["tall"] for m in self.mobs.values())

    def brushed(self, m):
        return self.age < m["mem"].get("brushed", -1.0)

    def brush(self, m):
        m["mem"]["brushed"] = self.age + REGROW
        m["s"]["flags"] |= sim.F_SLEEP

    def step(self, dt):
        g = self.game
        self.age += dt
        if not g.rules["mobs"]:
            if self.mobs:
                self.mobs.clear()
            return
        self.spawn_acc += dt
        if self.spawn_acc >= SPAWN_EVERY:
            self.spawn_acc = 0.0
            self.spawn()
        tick = g.tick
        for mid, m in list(self.mobs.items()):
            k = KINDS[m["kind"]]
            mem = m["mem"]
            if (tick + mid) % THINK == 0:
                m["inp"] = self.think(mid, m, k)
            mem["hurt"] = max(0.0, mem["hurt"] - dt)
            mem["cool"] = max(0.0, mem["cool"] - dt)
            inp = m.get("inp", (0.0, 0.0, 0))
            m["s"] = sim.step_player(m["s"], inp, dt, g.world)
            s = m["s"]
            if inp[0] or inp[1]:
                s["yaw"] = math.degrees(math.atan2(inp[1], inp[0]))
            s["flags"] = (s["flags"] | sim.F_HURT) if mem["hurt"] > 0 else (s["flags"] & ~sim.F_HURT)
            if m["kind"] == "fluff":
                s["flags"] = (s["flags"] | sim.F_SLEEP) if self.brushed(m) else (s["flags"] & ~sim.F_SLEEP)
            if m["kind"] == "glitch":
                self.glitch(mid, m, k, dt)
            elif m["kind"] == "rust":
                self.grab(mid, m, k)
            if mid in self.mobs and (not g.players or min(math.dist((s["x"], s["y"]), (p.state["x"], p.state["y"]))
                                                          for p in g.players.values()) > FAR):
                del self.mobs[mid]

    def nearest(self, s, reach):
        best, bd = None, reach
        for p in self.game.players.values():
            if p.creative or p.asleep:
                continue
            d = math.dist((s["x"], s["y"], s["z"]), (p.state["x"], p.state["y"], p.state["z"]))
            if d < bd:
                best, bd = p, d
        return best, bd

    def towards(self, s, x, y, speed, jump=0):
        dx, dy = x - s["x"], y - s["y"]
        n = math.hypot(dx, dy) or 1
        return (dx / n * speed, dy / n * speed, jump)

    def think(self, mid, m, k):
        """Ten times a second: where to go (the input for its steps)."""
        g = self.game
        s, mem = m["s"], m["mem"]
        rng = g.rng
        speed = k["speed"] / sim.WALK
        blocked = abs(s["vx"]) + abs(s["vy"]) < 0.3 and mem.get("going")
        jump = sim.JUMP_B if blocked or s["flags"] & sim.F_WATER else 0
        if mem["flee"] > 0:
            mem["flee"] -= THINK * sim.STEP
            p, d = self.nearest(s, 12)
            if p is not None:
                dx, dy = s["x"] - p.state["x"], s["y"] - p.state["y"]
                n = math.hypot(dx, dy) or 1
                return (dx / n * speed * 1.6, dy / n * speed * 1.6, jump)
        if m["kind"] == "glitch":
            p, d = self.nearest(s, 18)
            if p is not None:
                mem["going"] = True
                return self.towards(s, p.state["x"], p.state["y"], speed if d > ZAP_FAR * 0.8 else 0.0, jump)
        if m["kind"] == "rust":
            home = mem.get("home")
            hx, hy = (home[0] + 0.5, home[1] + 0.5) if home else (s["x"], s["y"])
            leash = HOME_NIGHT if g.is_night() else HOME_DAY
            p, d = self.nearest(s, 18 if g.is_night() else 10)
            if p is not None and math.dist((p.state["x"], p.state["y"]), (hx, hy)) < leash:
                mem["going"] = True
                return self.towards(s, p.state["x"], p.state["y"], speed, jump)
            if home and math.dist((s["x"], s["y"]), (hx, hy)) > (6 if not g.is_night() else leash * 0.6):
                mem["going"] = True  # (back to its heap: by day it rolls home)
                return self.towards(s, hx, hy, speed * 0.8, jump)
        if m["kind"] == "bleep":  # (it follows anyone holding scrap)
            for p in g.players.values():
                held, _ = p.held()
                if held and held["key"] == "scrap":
                    dx, dy = p.state["x"] - s["x"], p.state["y"] - s["y"]
                    n = math.hypot(dx, dy)
                    if 1.8 < n < 10:
                        mem["going"] = True
                        return (dx / n * speed, dy / n * speed, jump)
                    if n <= 1.8:
                        return (0.0, 0.0, 0)
            if rng.random() < 0.01:
                g.sound("beep", s["x"], s["y"], s["z"], 0.5)
        # wander: a new way to go now and then, a stop now and then
        mem["t"] -= THINK * sim.STEP
        if mem["t"] <= 0:
            mem["t"] = 1.5 + rng.random() * 4
            if rng.random() < 0.4:
                mem["goal"] = None
            else:
                a = rng.random() * math.tau
                mem["goal"] = (math.cos(a), math.sin(a))
        if mem["goal"] is None:
            mem["going"] = False
            return (0.0, 0.0, 0)
        mem["going"] = True
        gx, gy = mem["goal"]
        return (gx * speed * 0.6, gy * speed * 0.6, jump)

    def stand_ok(self, x, y, z):
        """Can a creature stand with its feet in block (x, y, z)?"""
        solid, _, _ = sim.tables()
        w = self.game.world
        return w.inside(x, y, z) and not solid[w.get(x, y, z)] and not solid[w.get(x, y, z + 1)] and solid[w.get(x, y, z - 1)]

    def glitch(self, mid, m, k, dt):
        """A Glitch: every two seconds it blinks up to 3 blocks towards the nearest player; near enough, it zaps."""
        mem, s = m["mem"], m["s"]
        g = self.game
        p, d = self.nearest(s, 18)
        mem["blink"] -= dt
        if p is not None and mem["blink"] <= 0 and d > 1.5:
            mem["blink"] = BLINK_EVERY
            q = p.state
            dx, dy = q["x"] - s["x"], q["y"] - s["y"]
            n = math.hypot(dx, dy) or 1
            step = min(BLINK_FAR, max(0.0, n - 1.2))
            for far in (step, step * 0.66, step * 0.33):
                tx, ty = s["x"] + dx / n * far, s["y"] + dy / n * far
                spot = next((zz for zz in (int(math.floor(s["z"])), int(math.floor(s["z"])) + 1, int(math.floor(s["z"])) - 1)
                             if self.stand_ok(int(math.floor(tx)), int(math.floor(ty)), zz)), None)
                if spot is not None and far > 0.4:
                    g.burst(s["x"] - 0.5, s["y"] - 0.5, s["z"], "glitch_body", 6)
                    s.update(x=tx, y=ty, z=float(spot), vx=0.0, vy=0.0, vz=0.0)
                    g.sound("blink", tx, ty, s["z"] + 0.5, 0.7)
                    break
        if p is not None and mem["cool"] <= 0 and d <= ZAP_FAR:
            mem["cool"] = ZAP_COOL
            q = p.state
            dx, dy = q["x"] - s["x"], q["y"] - s["y"]
            n = math.hypot(dx, dy) or 1
            g.hurt(p, k["damage"], "zap", knock=(dx / n * 4, dy / n * 4))
            g.sound("zap", s["x"], s["y"], s["z"])
            s["flags"] |= sim.F_SWING
        else:
            s["flags"] &= ~sim.F_SWING

    def grab(self, mid, m, k):
        """A Rust Walker's magnet arm: close enough, it grabs (14 harm), and one grab in four pulls a thing off your
        Toolbelt (it drops it again when it is beaten)."""
        mem, s = m["mem"], m["s"]
        g = self.game
        if mem["cool"] > 0:
            return
        for p in g.players.values():
            if p.creative or p.asleep:
                continue
            q = p.state
            if abs(q["z"] - s["z"]) < 1.8 and math.hypot(q["x"] - s["x"], q["y"] - s["y"]) < GRAB_FAR:
                mem["cool"] = GRAB_COOL
                dx, dy = q["x"] - s["x"], q["y"] - s["y"]
                n = math.hypot(dx, dy) or 1
                g.hurt(p, k["damage"], "grab", knock=(-dx / n * 3, -dy / n * 3))
                g.sound("magnet", s["x"], s["y"], s["z"] + 1)
                belt = [i for i in range(items.TOOLBELT) if p.inv[i]]
                if belt and g.rng.random() < STEAL:
                    i = g.rng.choice(belt)
                    took = [p.inv[i][0], 1, p.inv[i][2]]
                    items.use_up(p.inv, i)
                    mem["stole"].append(took)
                    g.inv_changed(p.pid)
                    g.say(p.pid, f"A Rust Walker's magnet pulled your {B.name_of(took[0])} away! Beat it to get it back.")
                s["flags"] |= sim.F_SWING
                return
        s["flags"] &= ~sim.F_SWING

    def hit(self, mid, dmg, eye, player):
        """A player's hit (from eye, within reach): True if it landed."""
        m = self.mobs.get(mid)
        if m is None:
            return False
        s = m["s"]
        if math.dist(eye, (s["x"], s["y"], s["z"] + KINDS[m["kind"]]["tall"] / 2)) > 4.2:
            return False
        s["hp"] -= dmg
        m["mem"]["hurt"] = 0.35
        dx, dy = s["x"] - eye[0], s["y"] - eye[1]
        n = math.hypot(dx, dy) or 1
        s["vx"] += dx / n * 7
        s["vy"] += dy / n * 7
        s["vz"] = 5.0
        self.game.sound(SOUNDS[m["kind"]], s["x"], s["y"], s["z"])
        if not KINDS[m["kind"]]["hostile"]:
            m["mem"]["flee"] = 3.0
        if s["hp"] <= 0:
            self.defeated(mid, m, player)
        return True

    def defeated(self, mid, m, player):
        s = m["s"]
        g = self.game
        g.burst(s["x"] - 0.5, s["y"] - 0.5, s["z"], {"fluff": "fluff_white", "bleep": "bleep_body", "glitch": "glitch_body",
                                                     "rust": "rust_body"}[m["kind"]], 16)
        for key, lo, hi in KINDS[m["kind"]]["drops"]:
            n = g.rng.randint(lo, hi)
            if n:
                g.drop(I[key], n, s["x"], s["y"], s["z"] + 0.5)
        for took in m["mem"].get("stole", []):
            g.drop(took[0], took[1], s["x"], s["y"], s["z"] + 0.5, wear=took[2])
        if player is not None:
            player.stats["killed"][m["kind"]] = player.stats["killed"].get(m["kind"], 0) + 1
            g.notes.append((player.pid, "defeated", m["kind"]))
        del self.mobs[mid]

    def pulse(self, x, y, z, reach):
        """An Overload pulse: creatures near it harmed and thrown."""
        for mid, m in list(self.mobs.items()):
            s = m["s"]
            d = math.dist((s["x"], s["y"], s["z"]), (x, y, z))
            if d < reach:
                s["hp"] -= int(round(20 * (1 - d / reach)))
                dx, dy = s["x"] - x, s["y"] - y
                n = math.hypot(dx, dy) or 1
                s["vx"] += dx / n * 9
                s["vy"] += dy / n * 9
                s["vz"] = 7.0
                if s["hp"] <= 0:
                    self.defeated(mid, m, None)

    def pull_back(self, mid, to):
        """A rift sealing pulls its Glitch back in: a magenta streak from it to the rift."""
        m = self.mobs.pop(mid, None)
        if m is None:
            return
        s = m["s"]
        self.game.events.append(("streak", s["x"], s["y"], s["z"] + 0.5, to[0], to[1], to[2]))

    def dawn(self):
        """Dawn: every Glitch still out goes back where it came from."""
        for mid, m in list(self.mobs.items()):
            if m["kind"] == "glitch":
                s = m["s"]
                self.game.burst(s["x"] - 0.5, s["y"] - 0.5, s["z"], "glitch_body", 10)
                self.pull_back(mid, (s["x"], s["y"], s["z"] - 2))

    def spawn(self):
        """Now and then: a Fluff or a Bleep on lit turf by day, 24 to 40 blocks from a player; a Rust Walker at a scrap
        heap someone is near (Glitches only come from the rifts: craft_game)."""
        g = self.game
        if not g.players:
            return
        w = g.world
        rng = g.rng
        if self.age >= SAFE_START:
            for heap in getattr(w, "heaps", []):
                near = any(math.dist((p.state["x"], p.state["y"]), heap[:2]) < HEAP_NEAR for p in g.players.values())
                mine = sum(1 for m in self.mobs.values() if m["kind"] == "rust" and m["mem"].get("home") == tuple(heap))
                if near and mine < PER_HEAP and rng.random() < 0.2:
                    hx, hy, hz = heap
                    for _ in range(12):
                        x, y = hx + rng.randint(-4, 4), hy + rng.randint(-4, 4)
                        z = next((zz for zz in range(hz, hz + 5) if self.stand_ok(x, y, zz)), None)
                        if z is not None:
                            self.add("rust", x + 0.5, y + 0.5, float(z), home=tuple(heap))
                            break
        passive = sum(1 for m in self.mobs.values() if not KINDS[m["kind"]]["hostile"])
        if g.is_night() or passive >= MAX_PASSIVE:
            return
        p = rng.choice(list(g.players.values()))
        a = rng.random() * math.tau
        r = 24 + rng.random() * 16
        x, y = int(p.state["x"] + math.cos(a) * r), int(p.state["y"] + math.sin(a) * r)
        if not (2 <= x < w.X - 2 and 2 <= y < w.Y - 2):
            return
        z = w.top(x, y)
        if w.blocks[x, y, z] != ID["turf"] or w.blocks[x, y, z + 1] != 0:
            return
        kind = "fluff" if rng.random() < 0.65 else "bleep"
        for k in range(1 + (kind == "fluff") * rng.randint(0, 2)):
            self.add(kind, x + 0.5 + k * 0.7, y + 0.5, float(z + 1))

    def entities(self):
        return [dict(m["s"], id=mid) for mid, m in self.mobs.items()]
