"""Kart Lab's power-ups (CHANGE 159): item boxes on the track, the five items, and what they do. The server's alone.

Two rows of item boxes cross each track (kart_track's "boxes"). A kart driving through one, holding nothing, gets a
random item, the better ones further back (Mario Kart's way); the box comes back three seconds later. USE (the E key,
or a computer kart's brain) uses it:

    boost   a speed burst, as a dash pad's
    oil     a slick dropped behind: whoever drives over it slides (the dropper too, after a moment)
    shot    fired ahead, bouncing off the barriers, for four seconds
    homing  fired at the kart in front on the road (whatever lap it's on), following the road, for six seconds
    shield  ten seconds of a bubble that takes one hit

A shot or a slick that reaches a kart spins it out (slowed hard, its tyres sliding) and, with real damage on, damages
it where it was hit, unless its shield takes the hit. The teacher switches each item on or off (the lesson's
"items"); with all off there are no boxes.

The kart's own record carries what it holds ("item") and its shield ("shield", ticks left): the windows draw them.
The shots and slicks go to the windows in an "items" message (state()), with the snapshot's time stamp.
Items doesn't touch the kart's physics step: a boost or a hit is the server's word, and a predicting window is put
right by its next snapshot, as for a bump.
"""
import math
import random

import kart_sim as sim

ITEMS = ("boost", "oil", "shot", "homing", "shield")  # item code: its index + 1 (0: holding nothing)
CODE = {name: i + 1 for i, name in enumerate(ITEMS)}
BOX_RADIUS = 1.5         # how close to a box's middle a kart takes it (m)
BOX_BACK = 180           # ticks before a taken box is there again (3 s)
ITEM_BOOST = 75          # a boost item's boost (1.25 s)
SLICK_LIFE = 60 * 20     # an oil slick lasts 20 s, or until someone drives over it
SLICK_RADIUS = 1.6
SLICK_SAFE = 45          # ...the dropper can't slide on it for this long (it's behind them anyway)
SHOT_SPEED, SHOT_LIFE, SHOT_RADIUS = 32.0, 240, 1.25    # m/s, ticks, m
HOMING_SPEED, HOMING_LIFE, HOMING_TURN = 30.0, 360, 220.0  # m/s, ticks, degrees a second it can turn
HOMING_REACH = 150.0     # how far ahead on the road a homing shot looks for a kart (m)
HOMING_CLOSE = 25.0      # ...it follows the road until this close, then goes straight for it
SHOT_SAFE = 20           # a shot can't hit the kart that fired it for this long
SHIELD_TICKS = 600       # 10 s
SPIN_TICKS = 45          # a hit kart's tyres slide this long (0.75 s)
HIT_DAMAGE = 3500        # with real damage: what a hit costs (shared out where it landed)

# how likely each item is, for the kart in front (first) and the one at the back (last), the field between them
# blended: in front oil, shots and shields to defend, at the back boosts and homing shots to catch up
ODDS_FRONT = {"boost": 1, "oil": 4, "shot": 3, "homing": 0, "shield": 3}
ODDS_BACK = {"boost": 4, "oil": 1, "shot": 2, "homing": 4, "shield": 1}


def odds(place, count, allowed):
    """Each allowed item's weight for a kart in this place (1-based) of count."""
    f = 0.5 if count <= 1 else (place - 1) / (count - 1)
    return {name: ODDS_FRONT[name] * (1 - f) + ODDS_BACK[name] * f for name in ITEMS if allowed.get(name)}


class Items:
    """The power-ups of one race: its boxes, the shots and slicks out on the track, and the rules for using them.
    allowed: {item: on} (the lesson's "items")."""

    def __init__(self, race, allowed=None, seed=1):
        self.race, self.track = race, race.track
        self.allowed = {name: True for name in ITEMS} if allowed is None else {n: bool(allowed.get(n)) for n in ITEMS}
        self.rng = random.Random(seed)
        self.boxes = []  # [x, y, z, ticks until it's back (0: there)]
        for s, lat in self.track.box_spots():
            x, y, z = self.track.point(s, lat)
            self.boxes.append([x, y, z, 0])
        self.shots = []   # {"id", "kind" (shot/homing), "x", "y", "h" (heading, degrees), "s" (track s), "owner", "age", "target"}
        self.slicks = []  # {"id", "x", "y", "owner", "age"}
        self.next_id = 1
        self.hits = []    # (tick, kart id, what hit it, blocked) this tick, for the windows' sounds and sparks
        self.unsent = []  # ...and since the last items message (state() hands them on)
        self.changed = True

    def on(self):
        """Any item switched on (with none, no boxes)."""
        return any(self.allowed.values())

    def set_allowed(self, allowed):
        self.allowed = {n: bool((allowed or {}).get(n)) for n in ITEMS}
        if not self.on():
            for k in self.race.karts.values():
                k["item"] = 0
        else:  # (an item switched off is taken back from whoever holds it)
            for k in self.race.karts.values():
                if k.get("item") and not self.allowed[ITEMS[k["item"] - 1]]:
                    k["item"] = 0
        self.changed = True

    # ---------- every tick ----------
    def tick(self, inputs, frozen):
        """After the karts' step and their bumps: boxes taken and back, items used, shots and slicks moved, hits."""
        race = self.race
        self.hits = []
        if not self.on():
            if self.shots or self.slicks:
                self.shots, self.slicks, self.changed = [], [], True
            return
        for b in self.boxes:
            if b[3] > 0:
                b[3] -= 1
                if b[3] == 0:
                    self.changed = True
        if frozen:
            return
        places = race.places()
        for kid, k in race.karts.items():
            # a box: taken by a kart driving through it (holding nothing gets an item; holding one just breaks it)
            for b in self.boxes:
                if b[3] == 0 and math.hypot(k["x"] - b[0], k["y"] - b[1]) < BOX_RADIUS:
                    b[3] = BOX_BACK
                    self.changed = True
                    if not k.get("item"):
                        k["item"] = self.roll(places.index(kid) + 1, len(places))
            # USE: the item used
            inp = inputs.get(kid)
            if inp and inp[2] & sim.USE and k.get("item") and kid not in race.finish:
                self.use(kid, k, ITEMS[k["item"] - 1], places)
                k["item"] = 0
        self.move_shots()
        self.check_slicks()

    def roll(self, place, count):
        weights = odds(place, count, self.allowed)
        total = sum(weights.values())
        if total <= 0:
            return 0
        r = self.rng.random() * total
        for name, w in weights.items():
            r -= w
            if r <= 0:
                return CODE[name]
        return CODE[name]

    def use(self, kid, k, item, places):
        h = math.radians(k["yaw"])
        fx, fy = math.cos(h), math.sin(h)
        if item == "boost":
            k["boost"] = max(k["boost"], ITEM_BOOST)
        elif item == "shield":
            k["shield"] = SHIELD_TICKS
        elif item == "oil":
            self.slicks.append({"id": self.new_id(), "x": k["x"] - fx * 1.8, "y": k["y"] - fy * 1.8, "owner": kid, "age": 0})
        else:  # a shot or a homing shot, from just in front
            target = self.kart_in_front(kid, k) if item == "homing" else None
            self.shots.append({"id": self.new_id(), "kind": item, "x": k["x"] + fx * 1.6, "y": k["y"] + fy * 1.6,
                               "h": k["yaw"], "owner": kid, "age": 0, "target": target, "seg": k.get("seg")})
        self.changed = True

    def kart_in_front(self, kid, k):
        """The nearest kart ahead of k along the road within HOMING_REACH (whatever lap each is on), or None."""
        best, best_d = None, HOMING_REACH
        for oid, o in self.race.karts.items():
            if oid == kid or oid in self.race.finish:
                continue
            d = (o["s"] - k["s"]) % self.track.length
            if 1.0 < d < best_d:
                best, best_d = oid, d
        return best

    def new_id(self):
        self.next_id = self.next_id % 60000 + 1
        return self.next_id

    def move_shots(self):
        race, track = self.race, self.track
        dt = sim.STEP
        keep = []
        for sh in self.shots:
            sh["age"] += 1
            homing = sh["kind"] == "homing"
            speed = HOMING_SPEED if homing else SHOT_SPEED
            if homing:  # (turns towards where it wants to go, a little at a time)
                t = race.karts.get(sh["target"]) if sh["target"] is not None else None
                seg, s, lat = track.locate(sh["x"], sh["y"], sh.get("seg"))
                if t is not None and math.hypot(t["x"] - sh["x"], t["y"] - sh["y"]) < HOMING_CLOSE:
                    want = math.degrees(math.atan2(t["y"] - sh["y"], t["x"] - sh["x"]))  # (close: straight at it)
                else:  # (it follows the road, drifting across towards its target's side of it)
                    aim = t["lat"] if t is not None else lat
                    ax, ay, _ = track.point(s + 8.0, aim)
                    want = math.degrees(math.atan2(ay - sh["y"], ax - sh["x"]))
                turn = (want - sh["h"] + 180) % 360 - 180
                limit = HOMING_TURN * dt
                sh["h"] += max(-limit, min(limit, turn))
            h = math.radians(sh["h"])
            x, y = sh["x"] + math.cos(h) * speed * dt, sh["y"] + math.sin(h) * speed * dt
            seg, s, lat = track.locate(x, y, sh.get("seg"))
            sh["seg"] = seg
            limit = track.half - 0.3
            if abs(lat) > limit:  # a barrier: a shot bounces off it, a homing shot slides along it
                tang = track.heading(s)
                rel = (sh["h"] - tang + 180) % 360 - 180
                sh["h"] = tang - rel if not homing else tang + max(-20.0, min(20.0, rel)) * 0.3
                lat = limit if lat > 0 else -limit
                x, y, _ = track.point(s, lat)
            sh["x"], sh["y"] = x, y
            hit = None
            for kid, k in race.karts.items():
                if kid == sh["owner"] and sh["age"] < SHOT_SAFE:
                    continue
                if math.hypot(k["x"] - x, k["y"] - y) < SHOT_RADIUS:
                    hit = kid
                    break
            if hit is not None:
                self.hit(hit, sh["kind"], sh["x"], sh["y"])
                self.changed = True
                continue
            if sh["age"] < (HOMING_LIFE if homing else SHOT_LIFE):
                keep.append(sh)
            else:
                self.changed = True
        self.shots = keep

    def check_slicks(self):
        keep = []
        for sl in self.slicks:
            sl["age"] += 1
            hit = None
            for kid, k in self.race.karts.items():
                if kid == sl["owner"] and sl["age"] < SLICK_SAFE:
                    continue
                if math.hypot(k["x"] - sl["x"], k["y"] - sl["y"]) < SLICK_RADIUS:
                    hit = kid
                    break
            if hit is not None:
                self.hit(hit, "oil", sl["x"], sl["y"])
                self.changed = True
            elif sl["age"] < SLICK_LIFE:
                keep.append(sl)
            else:
                self.changed = True
        self.slicks = keep

    def hit(self, kid, what, x, y):
        """A shot or a slick reached kart kid (from x, y): its shield takes it, or it spins out (damaged too, with
        real damage on, where it was hit)."""
        race = self.race
        k = race.karts[kid]
        if k.get("shield"):
            k["shield"] = 0
            self.hits.append((race.tick, kid, what, True))
            self.unsent.append((race.tick, kid, what, True))
            return
        if what == "oil":
            k["slip"] = max(k["slip"], sim.OIL_TICKS)
            k["v"] *= 0.8
        else:
            k["slip"] = max(k["slip"], SPIN_TICKS)
            k["v"] *= 0.35
            k["u"] = 0.0
        if race.damage and what != "oil":
            h = math.radians(k["yaw"])
            dx, dy = x - k["x"], y - k["y"]
            d = math.hypot(dx, dy) or 1.0
            front, left = (math.cos(h) * dx + math.sin(h) * dy) / d, (-math.sin(h) * dx + math.cos(h) * dy) / d
            sim.hurt(k, HIT_DAMAGE, sim.side_shares(front, left))
        self.hits.append((race.tick, kid, what, False))
        self.unsent.append((race.tick, kid, what, False))
        race.events.append((race.tick, f"{race.designs[kid]['name']} was hit by " +
                            {"shot": "a shot", "homing": "a homing shot", "oil": "an oil slick"}[what]))

    # ---------- for the windows ----------
    def state(self):
        """The items message's body: which boxes are there ("1" there, "0" taken, in box_spots' order), the shots
        ([id, kind, x, y, heading]) and slicks ([id, x, y]), and the hits since the last ([kart id, what, blocked])."""
        hits, self.unsent, self.changed = self.unsent, [], False
        return {"boxes": "".join("1" if b[3] == 0 else "0" for b in self.boxes) if self.on() else "",
                "shots": [[sh["id"], sh["kind"], round(sh["x"], 2), round(sh["y"], 2), round(sh["h"], 1)] for sh in self.shots],
                "slicks": [[sl["id"], round(sl["x"], 2), round(sl["y"], 2)] for sl in self.slicks],
                "hits": [[kid, what, blocked] for _, kid, what, blocked in hits]}


# ---------- the computer karts ----------
def cpu_use(k, race, rng=random):
    """Whether a computer kart uses its item this tick (sim.USE or 0): a shot when a kart is ahead within reach, a
    homing shot at once, oil when one is close behind, a boost on a straight, a shield when one is close."""
    item = k.get("item")
    if not item or race.frozen():
        return 0
    name = ITEMS[item - 1]
    if name in ("homing", "shield") and rng.random() < 0.02:
        return sim.USE
    h = math.radians(k["yaw"])
    fx, fy = math.cos(h), math.sin(h)
    for kid, o in race.karts.items():
        if o is k:
            continue
        dx, dy = o["x"] - k["x"], o["y"] - k["y"]
        d = math.hypot(dx, dy)
        ahead = (fx * dx + fy * dy) / (d or 1.0)
        if name == "shot" and d < 25 and ahead > 0.95:
            return sim.USE
        if name == "oil" and d < 10 and ahead < -0.7:
            return sim.USE
        if name == "shield" and d < 6:
            return sim.USE
    if name == "boost" and rng.random() < 0.03:  # (on a straight: the road 25 m on heads the same way)
        bend = (race.track.heading(k["s"] + 25.0) - race.track.heading(k["s"]) + 180) % 360 - 180
        if abs(bend) < 8:
            return sim.USE
    if name in ("oil", "shot") and rng.random() < 0.003:  # (held too long: used anyway)
        return sim.USE
    return 0
