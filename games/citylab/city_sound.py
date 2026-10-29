"""City Lab's sound (CHANGE 194, step 7): Kart Lab's and Fight Lab's sounds in one set, on the engine's mixer.

    in a car      the engine note rising with the speed, the tyres squealing in a drift, with the handbrake on or the
                  wheels spinning (Kart Lab's), a bump into a wall or a car (Robot Lab's)
    on foot       a punch's or a kick's whoosh as it starts and its thump where it lands, a block's knock, a robot's
                  clang and a zap's buzz (Fight Lab's)
    the city      the other cars' engines going by, the crowd in the park when you are near it, the horn at the end
                  of a job, the street race's 3-2-1-GO beeps

Nothing is recorded: Kart Lab's and Fight Lab's sounds are made from maths the first time either game runs (the
engine's assets/sfx). With no sound card, or in offscreen tests, it is quiet.

    snd = CitySounds(base, on)
    snd.frame(now, me_id, things, car_id, city)    every frame: the loops (the engine, the tyres, the traffic, the park)
    snd.hit(kind, volume, robot)   snd.swing(move, volume)   snd.bump(volume)   snd.countdown(n)   snd.done()
"""
import math

import kart_sound

import city_sim as sim

CAR_TOP = 28.0          # m/s: the engine note's top (a car's top speed is about this with the points)
HEAR = 45.0             # metres: things further from you than this are not heard
PARK_HEAR = 35.0        # the crowd in the park, from this near its edge


def falloff(d, reach=HEAR):
    """How loud something d metres away sounds (1 beside you, nothing at reach)."""
    return max(0.0, 1.0 - d / reach) ** 1.6


class CitySounds(kart_sound.KartSounds):
    """Kart Lab's sounds (the engine, the tyres, the beeps) and Fight Lab's (the hits) in one mixer."""

    def __init__(self, base, on=True):
        super().__init__(base, on)
        import fight_sound  # (Fight Lab's: its folder is on the path, city_version)
        fight_sound.ensure()
        self.fight = fight_sound
        for name in fight_sound.VARIED:
            self.pool["f_" + name] = [self._load(f"f_{name}_{v}") for v in range(fight_sound.VARIANTS) for _ in range(2)]
        for name in fight_sound.SINGLE:
            self.pool["f_" + name] = [self._load("f_" + name) for _ in range(2)]
        self.moves = {}         # each person's move last frame (a new punch or kick starts its whoosh)
        self.speeds = {}        # each car's speed last frame (a sudden stop is a bump)

    # ---------- one-off sounds ----------
    def hit(self, kind, volume, robot=False):
        """A contact (Fight Lab's): punch, kick, block, zap... A robot's hits have a clang of metal on top."""
        if volume <= 0.02:
            return
        for name, loud in self.fight.HIT_SOUNDS.get(kind, [("punch", 1.0)]):
            self.play(name if name == "wall" else "f_" + name, volume * loud)
        if robot and kind in self.fight.METAL:
            self.play("f_metal", volume * self.fight.METAL[kind])

    def swing(self, move, volume):
        name, loud, speed = self.fight.SWINGS.get(move, ("whoosh", 0.5, 1.0))
        if volume > 0.02:
            self.play("f_" + name, volume * loud, speed)

    def done(self):
        """A job done: the horn."""
        self.play("horn", 0.8)

    # ---------- every frame ----------
    def frame(self, now, me_id, things, car_id, city):
        """me_id: your own person; things: every record drawn (id -> record); car_id: the car you drive or None;
        city: city_map.City (the park)."""
        if not self.on or me_id not in things:
            return
        me = things[me_id]
        mine = things.get(car_id) if car_id is not None else None
        if mine is not None:
            f = mine["flags"]
            self.update(now, mine["v"], CAR_TOP, bool(f & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R)),
                        bool(f & sim.FLAG_BOOSTING), False,
                        spinning=bool(f & (sim.FLAG_WHEELSPIN | sim.FLAG_HANDBRAKE)) and abs(mine["v"]) > 1.0)
        else:
            self.stop("engine")
            self.stop("skid")
        x, y = (mine or me)["x"], (mine or me)["y"]
        loudest = 0.0  # the nearest moving car that isn't yours: one loop, as loud as it is near
        for tid, t in things.items():
            kind = sim.kind_of(tid)
            d = math.hypot(t["x"] - x, t["y"] - y)
            if kind == "car":
                v = abs(t["v"])
                before = self.speeds.get(tid)
                self.speeds[tid] = v
                if before is not None and before - v > 5.0 and d < HEAR:  # (stopped dead: it hit something)
                    self.bump(min(1.0, (before - v) / 12.0) * (1.0 if tid == car_id else falloff(d)))
                if tid != car_id and v > 2.0:
                    loudest = max(loudest, falloff(d, 30.0) * min(1.0, v / 15.0))
            elif kind == "person":
                move = t.get("move", 0)
                if move != self.moves.get(tid) and move in (sim.MOVE_PUNCH, sim.MOVE_KICK):
                    self.swing("punch" if move == sim.MOVE_PUNCH else "kick", 0.8 * (1.0 if tid == me_id else falloff(d, 25.0)))
                self.moves[tid] = move
        if loudest > 0.03:
            self.loop("traffic", "motor", 0.25 * loudest, 0.7 + 0.5 * loudest)
        else:
            self.stop("traffic")
        park = 0.0
        for b in city.blocks:
            if b["kind"] == "park":
                dx = max(b["x0"] - x, 0.0, x - b["x1"])
                dy = max(b["y0"] - y, 0.0, y - b["y1"])
                park = max(park, falloff(math.hypot(dx, dy), PARK_HEAR))
        self.layers("off", 0.0, park > 0.03, 0.5 * park, False, 0)

    def landed(self, things, prev, me_xy):
        """Hits that landed since prev (a robot's power or a person's health went down): their sounds, by how far."""
        if not self.on:
            return
        x, y = me_xy
        for tid, now in things.items():
            kind = sim.kind_of(tid)
            before = prev.get(tid)
            if kind == "car" or before is None or now["hp"] >= before["hp"] or now.get("link"):
                continue
            lost = before["hp"] - now["hp"]
            loud = falloff(math.hypot(now["x"] - x, now["y"] - y), 30.0) * min(1.0, 0.5 + lost / 20.0)
            if kind == "robot":
                self.hit("kick" if lost >= sim.HIT[sim.MOVE_KICK] else "punch", loud, robot=True)
            elif now["flags"] & sim.FLAG_BLOCK:
                self.hit("block", loud)
            elif any(sim.kind_of(o) == "robot" and t["flags"] & sim.FLAG_ZAP and
                     math.hypot(t["x"] - now["x"], t["y"] - now["y"]) < 3.0 for o, t in things.items()):
                self.hit("zap", loud)
            else:
                self.hit("kick" if lost >= sim.HIT[sim.MOVE_KICK] else "punch", loud)


class Quiet:
    """No sound at all (offscreen tests, or a computer with no sound card): every call does nothing."""
    on = False

    def __getattr__(self, name):
        return lambda *a, **k: None


def make(base, on):
    if not on:
        return Quiet()
    try:
        return CitySounds(base, on)
    except Exception as e:  # (no sound card, or the sounds couldn't be made: the city is quiet, not broken)
        print(f"City Lab: no sound ({e!r})", flush=True)
        return Quiet()

