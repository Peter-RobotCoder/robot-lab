"""Craft Lab's creatures (CHANGE 200), all Club Coders' own:

    FLUFF        a woolly, friendly thing that wanders the grass by day; hit, it runs off; it drops wool
    BLEEP        a little robot that rolls about by day and beeps; it follows anyone holding scrap; it drops scrap
    GLITCH       a hopping purple cube that comes out in the dark (at night, and in caves); it hops at you and
                 zaps; it fizzles away in the morning sun; it drops glitch shards (four make a lumen block)
    RUST WALKER  a rusty old robot that walks out at night and in deep caves; it swings at you; it drops rust and
                 scrap

They move as players do (craft_sim.step_player: they bump into blocks, fall, swim) with inputs from their own little
brains, which think ten times a second: wander, follow, chase, flee, hop. Hostile ones only come where it is dark
and only while the lesson has creatures on; none come within 20 blocks of where someone joined in the first 30 s.
"""
import math

import craft_blocks as B
import craft_sim as sim

I, ID = B.ITEM_ID, B.ID
KINDS = {
    #             hp  speed  hostile  height  drops                                          damage
    "fluff": dict(hp=8, speed=1.6, hostile=False, tall=1.2, drops=[("wool", 1, 2)], damage=0),
    "bleep": dict(hp=6, speed=2.0, hostile=False, tall=0.9, drops=[("scrap", 1, 2)], damage=0),
    "glitch": dict(hp=10, speed=3.4, hostile=True, tall=1.0, drops=[("glitch_shard", 1, 2)], damage=2),
    "rust": dict(hp=16, speed=2.4, hostile=True, tall=1.9, drops=[("rust", 0, 2), ("scrap", 0, 1)], damage=3),
}
MAX_PASSIVE, MAX_HOSTILE = 14, 16
THINK = 6           # steps between thoughts (10 a second)
SPAWN_EVERY = 1.0   # seconds between spawning tries
FAR = 80.0          # metres from everyone: it goes
SAFE_START = 30.0   # seconds after the game starts with no hostile ones near anyone
FIRST_ID, LAST_ID = 128, 191  # (their ids on the wire)


class Mobs:
    def __init__(self, game):
        self.game = game
        self.mobs = {}       # id -> {"kind", "s" (craft_sim's record), "hp", "mem"}
        self.spawn_acc = 0.0
        self.age = 0.0

    def ids(self):
        return list(self.mobs)

    def add(self, kind, x, y, z):
        mid = next((i for i in range(FIRST_ID, LAST_ID + 1) if i not in self.mobs), None)
        if mid is None:
            return None
        s = sim.new_player(x, y, z, sim.KINDS[kind])
        s["hp"] = KINDS[kind]["hp"]
        self.mobs[mid] = {"kind": kind, "s": s, "mem": {"t": 0, "goal": None, "flee": 0.0, "hop": 0.0, "cool": 0.0,
                                                         "hurt": 0.0}}
        return mid

    def box_hit(self, x, y, z):
        return any(abs(m["s"]["x"] - (x + 0.5)) < 0.8 and abs(m["s"]["y"] - (y + 0.5)) < 0.8 and
                   m["s"]["z"] - 1 < z < m["s"]["z"] + KINDS[m["kind"]]["tall"] for m in self.mobs.values())

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
            if k["hostile"]:
                self.bite(mid, m, k)
            if m["kind"] == "glitch" and not g.is_night() and self.light_at(s) >= 12 and (tick + mid) % 60 == 0:
                g.burst(s["x"] - 0.5, s["y"] - 0.5, s["z"], "glitch_body", 10)
                del self.mobs[mid]  # (the sun's up: it fizzles away)
                continue
            if not g.players or min(math.dist((s["x"], s["y"]), (p.state["x"], p.state["y"]))
                                    for p in g.players.values()) > FAR:
                del self.mobs[mid]

    def light_at(self, s):
        w = self.game.world
        x, y, z = int(math.floor(s["x"])), int(math.floor(s["y"])), int(math.floor(s["z"] + 0.5))
        if not w.inside(x, y, z):
            return 15
        sky = w.sky[x, y, z] * (1 if not self.game.is_night() else 0.25)
        return max(int(sky), int(w.glow[x, y, z]))

    def nearest(self, s, reach):
        best, bd = None, reach
        for p in self.game.players.values():
            if p.creative or p.asleep:
                continue
            d = math.dist((s["x"], s["y"], s["z"]), (p.state["x"], p.state["y"], p.state["z"]))
            if d < bd:
                best, bd = p, d
        return best, bd

    def think(self, mid, m, k):
        """Ten times a second: where to go (the input for its steps)."""
        g = self.game
        s, mem = m["s"], m["mem"]
        rng = g.rng
        speed = k["speed"] / sim.WALK
        jump = 0
        blocked = abs(s["vx"]) + abs(s["vy"]) < 0.3 and mem.get("going")
        if mem["flee"] > 0:
            mem["flee"] -= THINK * sim.STEP
            p, d = self.nearest(s, 12)
            if p is not None:
                dx, dy = s["x"] - p.state["x"], s["y"] - p.state["y"]
                n = math.hypot(dx, dy) or 1
                return (dx / n * speed * 1.6, dy / n * speed * 1.6, sim.JUMP_B if blocked else 0)
        if k["hostile"]:
            p, d = self.nearest(s, 18)
            if p is not None:
                dx, dy = p.state["x"] - s["x"], p.state["y"] - s["y"]
                n = math.hypot(dx, dy) or 1
                mem["going"] = True
                if m["kind"] == "glitch":  # (it hops)
                    mem["hop"] -= THINK * sim.STEP
                    if mem["hop"] <= 0 and s["flags"] & sim.F_GROUND:
                        mem["hop"] = 0.7 + rng.random() * 0.5
                        jump = sim.JUMP_B
                    return (dx / n * speed, dy / n * speed, jump)
                return (dx / n * speed, dy / n * speed, sim.JUMP_B if blocked or s["flags"] & sim.F_WATER else 0)
        if m["kind"] == "bleep":  # (it follows anyone holding scrap)
            for p in g.players.values():
                held, _ = p.held()
                if held and held["key"] == "scrap":
                    dx, dy = p.state["x"] - s["x"], p.state["y"] - s["y"]
                    n = math.hypot(dx, dy)
                    if 1.8 < n < 10:
                        mem["going"] = True
                        return (dx / n * speed, dy / n * speed, sim.JUMP_B if blocked else 0)
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
        return (gx * speed * 0.6, gy * speed * 0.6, sim.JUMP_B if blocked or s["flags"] & sim.F_WATER else 0)

    def bite(self, mid, m, k):
        """A hostile one close enough hurts (a Glitch's zap, a Rust Walker's swing), with a cool-down."""
        mem, s = m["mem"], m["s"]
        if mem["cool"] > 0:
            return
        for p in self.game.players.values():
            q = p.state
            if abs(q["z"] - s["z"]) < 1.6 and math.hypot(q["x"] - s["x"], q["y"] - s["y"]) < (1.1 if m["kind"] == "glitch" else 1.4):
                mem["cool"] = 1.0
                dx, dy = q["x"] - s["x"], q["y"] - s["y"]
                n = math.hypot(dx, dy) or 1
                self.game.hurt(p, k["damage"], "zap" if m["kind"] == "glitch" else "hit", knock=(dx / n * 6, dy / n * 6))
                self.game.sound("zap" if m["kind"] == "glitch" else "clank", s["x"], s["y"], s["z"])
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
        self.game.sound({"fluff": "baa", "bleep": "beep", "glitch": "zap", "rust": "clank"}[m["kind"]], s["x"], s["y"], s["z"])
        if not KINDS[m["kind"]]["hostile"]:
            m["mem"]["flee"] = 3.0
        if s["hp"] <= 0:
            self.defeated(mid, m, player)
        return True

    def defeated(self, mid, m, player):
        s = m["s"]
        g = self.game
        g.burst(s["x"] - 0.5, s["y"] - 0.5, s["z"], {"fluff": "wool_white", "bleep": "bleep_body", "glitch": "glitch_body",
                                                     "rust": "rust_body"}[m["kind"]], 16)
        for key, lo, hi in KINDS[m["kind"]]["drops"]:
            n = g.rng.randint(lo, hi)
            if n:
                g.drop(I[key], n, s["x"], s["y"], s["z"] + 0.5)
        if player is not None:
            player.stats["killed"][m["kind"]] = player.stats["killed"].get(m["kind"], 0) + 1
            g.notes.append((player.pid, "defeated", m["kind"]))
        del self.mobs[mid]

    def blast(self, x, y, z):
        for mid, m in list(self.mobs.items()):
            s = m["s"]
            d = math.dist((s["x"], s["y"], s["z"]), (x, y, z))
            if d < 6:
                s["hp"] -= int(14 / max(1.0, d))
                s["vz"] = 8.0
                if s["hp"] <= 0:
                    self.defeated(mid, m, None)

    def spawn(self):
        """Now and then: a Fluff or a Bleep on lit grass by day, a Glitch or a Rust Walker somewhere dark, 24 to 40
        blocks from a player."""
        g = self.game
        if not g.players:
            return
        w = g.world
        rng = g.rng
        passive = sum(1 for m in self.mobs.values() if not KINDS[m["kind"]]["hostile"])
        hostile = len(self.mobs) - passive
        p = rng.choice(list(g.players.values()))
        a = rng.random() * math.tau
        r = 24 + rng.random() * 16
        x, y = int(p.state["x"] + math.cos(a) * r), int(p.state["y"] + math.sin(a) * r)
        if not (2 <= x < w.X - 2 and 2 <= y < w.Y - 2):
            return
        solid, liquid, _ = sim.tables()
        if g.is_night() or rng.random() < 0.3:  # (a cave below, or the surface at night)
            if hostile >= MAX_HOSTILE or self.age < SAFE_START:
                return
            zs = [z for z in range(2, w.Z - 2) if solid[w.blocks[x, y, z - 1]] and w.blocks[x, y, z] == 0
                  and w.blocks[x, y, z + 1] == 0 and w.glow[x, y, z] < 6
                  and (w.sky[x, y, z] < 5 or g.is_night())]
            if not zs:
                return
            z = rng.choice(zs)
            self.add("glitch" if rng.random() < 0.55 else "rust", x + 0.5, y + 0.5, float(z))
        else:
            if passive >= MAX_PASSIVE:
                return
            z = w.top(x, y)
            if w.blocks[x, y, z] != ID["grass"] or w.blocks[x, y, z + 1] != 0:
                return
            kind = "fluff" if rng.random() < 0.65 else "bleep"
            for k in range(1 + (kind == "fluff") * rng.randint(0, 2)):
                self.add(kind, x + 0.5 + k * 0.7, y + 0.5, float(z + 1))

    def entities(self):
        return [dict(m["s"], id=mid) for mid, m in self.mobs.items()]
