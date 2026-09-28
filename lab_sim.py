"""Robot Lab physics: the arena, robots built from a learner's design, weapons, hazards and house robots.

A design is plain data a learner can read and change:
    points   - 100 points shared between speed, attack, armour and control
    settings - percentages that tune how the robot uses what the points bought
    weapon   - wedge (with flipper), horizontal spinner, drum (vertical spinner) or hammer

Weapons do "real type" damage: a spinner stores kinetic energy (1/2 x I x w squared) and hands
part of it to whatever it hits, then has to spin up again; a wedge's flipper launches a robot that
is sitting on it; a hammer hits harder the faster its head is moving.

The arena has floor saws (solid spinning blades that throw you the way they turn), a floor flipper that
sits flush with the floor, wall spikes that shoot in and out, a drop zone (pit) the teacher can open and
close, and four heavy house robots that guard the corners.

Real damage (the teacher switches it on): each part of a robot has its own hit points. A hit is shared between
the part it lands on (a wheel, the weapon, the armour) and the body. A part at zero comes off: a lost wheel
stops driving and that corner drags on the floor, a lost weapon falls into the arena, lost armour stops
protecting the body. The body at zero is a knockout, as always.
No graphics here: this runs on the teacher's server.
"""
import math
import random

from panda3d.bullet import (BulletBoxShape, BulletCylinderShape, BulletHingeConstraint, BulletRigidBodyNode,
                            BulletVehicle, BulletWorld, XUp, YUp, ZUp)
from panda3d.core import NodePath, Point3, TransformState, Vec3

STEP, SUBSTEP = 1 / 60, 1 / 180
ARENA = 20.0  # metres square

# Game rules. mods/rules.py can change any of these (the teacher approves every change).
DEFAULT_RULES = {
    "match_seconds": 180,          # length of a battle
    "damage_multiplier": 1.0,      # all weapon damage is multiplied by this
    "spinner_energy_share": 0.6,   # share of a spinner's stored energy handed to the robot it hits
    "max_launch_speed": 7.0,       # m/s: the most any hit can throw a robot (about 2.5 m of air)
    "flip_power": 1.0,             # wedge flipper launch multiplier
    "gravity": 9.81,               # m/s squared
    "hazard_damage": 1.0,          # saw, spike and house robot damage multiplier
    "floor_flipper_every": 4.0,    # seconds between floor flipper shots
    "saw_cycle": 5.0,              # saws rise once every this many seconds...
    "saw_up_seconds": 2.0,         # ...and stay up this long
    "spike_cycle": 4.0,            # wall spikes shoot out once every this many seconds
}
RULES = dict(DEFAULT_RULES)

# ---------- the design sheet ----------

STATS = ("speed", "attack", "armour", "control")
POINTS_TOTAL, STAT_MIN, STAT_MAX = 100, 5, 50
SETTINGS = {  # name: (lowest, highest, default, what it means)
    "forward_speed": (10, 100, 80, "% of your top speed when driving forwards"),
    "reverse_speed": (10, 100, 60, "% of your top speed when reversing"),
    "turn_speed": (10, 100, 70, "% of your fastest turn"),
    "acceleration": (10, 100, 70, "% of your motor's push"),
    "size": (80, 120, 100, "% of standard size: bigger is tougher but slower to turn"),
}
WEAPONS = {
    "wedge": "wedge with a flipper: scoops robots up and launches them",
    "spinner": "horizontal spinner: a bar that stores energy and smashes sideways",
    "drum": "drum (vertical spinner): stores energy and throws robots upwards",
    "hammer": "hammer: an axe that swings down over the top",
}
HOUSE_WEAPONS = ("flame", "hammer", "chainsaw", "vdisc")  # house robots only


def default_design(name="Robot", colour=(200, 120, 40), weapon="wedge"):
    return {"name": name, "colour": list(colour), "weapon": weapon,
            "points": {"speed": 25, "attack": 25, "armour": 25, "control": 25},
            "settings": {k: v[2] for k, v in SETTINGS.items()}}


def check_design(d):
    """Return a list of problems (empty = fine). Used by the server and shown to learners."""
    problems = []
    pts = d.get("points", {})
    if set(pts) != set(STATS):
        problems.append(f"points must have exactly: {', '.join(STATS)}")
    else:
        for k, v in pts.items():
            if not isinstance(v, int) or not STAT_MIN <= v <= STAT_MAX:
                problems.append(f"{k} must be a whole number from {STAT_MIN} to {STAT_MAX}")
        if sum(pts.values()) > POINTS_TOTAL:
            problems.append(f"{sum(pts.values())} points used: the most you can spend is {POINTS_TOTAL}")
    for k, (lo, hi, _, _) in SETTINGS.items():
        v = d.get("settings", {}).get(k)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            problems.append(f"{k} must be from {lo} to {hi}")
    if "model" in d:
        if d["model"] not in HOUSE_BY_NAME:
            problems.append(f"model must be one of {', '.join(HOUSE_BY_NAME)} (or leave it out)")
        elif d.get("weapon") != HOUSE_BY_NAME[d["model"]][0]:
            problems.append(f"{d['model']}'s weapon is {HOUSE_BY_NAME[d['model']][0]}")
    elif d.get("weapon") not in WEAPONS:
        problems.append(f"weapon must be one of {', '.join(WEAPONS)}")
    return problems


def build_stats(d):
    """Turn a design into physics numbers. Kept simple so learners can read the formulas."""
    p, s = d["points"], d["settings"]
    size = s["size"] / 100
    top_speed = 3 + 0.2 * p["speed"]                      # m/s: 4 (5 points) to 13 (50 points)
    return {
        "size": size,
        "forward_max": top_speed * s["forward_speed"] / 100,
        "reverse_max": top_speed * s["reverse_speed"] / 100,
        "accel": (1.5 + 0.12 * p["speed"]) * (0.3 + 0.7 * s["acceleration"] / 100),  # m/s per second
        "turn_rate": math.radians((60 + 4 * p["control"]) * s["turn_speed"] / 100) / size,
        "grip": 1.2 + 0.035 * p["control"],
        "self_right": 4.0 - 0.06 * p["control"],            # seconds upside down before self-righting
        "armour": (50 + 4 * p["armour"]) * size ** 2,       # hit points
        "mass": (22 + 0.3 * p["armour"]) * size ** 2,        # kg
        "power": 0.6 + 0.02 * p["attack"],                  # weapon strength, 1.1 at 25 points
        "flip_strength": p["attack"] / STAT_MAX,             # a flipper at 100% (50 attack points) can flip house robots
    }


# ---------- real damage: every part has its own hit points ----------

PARTS = ("armour", "weapon", "wheel0", "wheel1", "wheel2", "wheel3")  # (the body's hit points are the robot's health)
PART_WORDS = {"body": "Body", "armour": "Armour", "weapon": "Weapon", "wheel0": "Front right wheel",
              "wheel1": "Front left wheel", "wheel2": "Back right wheel", "wheel3": "Back left wheel"}


def part_hit_points(armour):
    """Real damage: each part's hit points, from the robot's armour (its body has the full armour, as always)."""
    return {"armour": 0.5 * armour, "weapon": 0.5 * armour, **{f"wheel{i}": 0.25 * armour for i in range(4)}}


# ---------- house robots: heavy, slow, and they guard the corners ----------

HOUSE_SIZE = 1.6
HOUSE_WHEEL_R = 0.32  # bigger wheels, so the big body rides higher off the floor
HOUSE_STATS = {"size": HOUSE_SIZE, "forward_max": 3.0, "reverse_max": 2.2, "accel": 3.0,
               "turn_rate": math.radians(95) / HOUSE_SIZE, "grip": 2.4, "self_right": 2.0,
               "armour": 1000.0, "mass": 190.0, "power": 1.8}
HOUSE_ROBOTS = (  # name, weapon, colour, corner it guards
    ("BLAZE", "flame", (205, 75, 20), (-1, 1)),
    ("CRUSHER", "hammer", (70, 72, 82), (1, 1)),
    ("RIPSAW", "chainsaw", (45, 120, 45), (1, -1)),
    ("VORTEX", "vdisc", (120, 35, 150), (-1, -1)),
)
HOUSE_BY_NAME = {name: (weapon, colour, corner) for name, weapon, colour, corner in HOUSE_ROBOTS}
CPZ = 4.8  # corner patrol zone: how far each house robot's square reaches from its corner (room to drive right in)
# a house robot driven by a player (the teacher can allow it in the garage): heavy, but it can be knocked out
PLAYABLE_HOUSE_STATS = dict(HOUSE_STATS, armour=400.0, forward_max=3.6, reverse_max=2.6, power=1.5)


def house_list(value):
    """The house robots switched on: True = all four, False = none, or a list of names."""
    if value is True:
        return [n for n, *_ in HOUSE_ROBOTS]
    if not value:
        return []
    return [n for n, *_ in HOUSE_ROBOTS if n in value]


def design_size(d):
    """How big a design's robot is (house robot models are always house size)."""
    return HOUSE_SIZE if d.get("house") or d.get("model") in HOUSE_BY_NAME else d["settings"]["size"] / 100


def house_design(name, weapon, colour):
    d = default_design(name, colour, weapon)
    d["settings"]["size"] = int(HOUSE_SIZE * 100)
    d["house"] = True
    d["style"] = {"trim": [25, 25, 28], "lights": [255, 170, 0], "number": name}
    return d


def in_zone(p, corner, margin=0.0):
    """Is point p inside the corner patrol zone of this corner?"""
    h = ARENA / 2
    return corner[0] * p.x >= h - CPZ - margin and corner[1] * p.y >= h - CPZ - margin


# ---------- robot shapes (shared with the viewer) ----------

BASE_HALF = Vec3(0.6, 0.8, 0.18)   # chassis half-size at 100%
CHASSIS_Z = 0.1                    # chassis sits above the body origin: low centre of mass
WHEEL_R = 0.2
WHEELS = ((0.72, 0.55), (-0.72, 0.55), (0.72, -0.55), (-0.72, -0.55))
RIDE = 0.12                        # the body origin rides about this high above the floor


def shapes(weapon, size):
    """Sizes and pivot points for a robot at a given size (so physics and graphics always match)."""
    h = BASE_HALF * size
    top = CHASSIS_Z + h.z
    if weapon == "wedge":      # plate hinged at the top front edge, front lip resting on the floor
        return dict(half=h, top=top, plate=Vec3(h.x + 0.02, 0.6, 0.03), pivot=Point3(0, h.y - 0.05, top),
                    axis=Vec3(1, 0, 0))
    if weapon == "spinner":    # flat bar on a vertical axle in front
        return dict(half=h, top=top, bar=Vec3(0.8 * size, 0.08, 0.05), pivot=Point3(0, h.y + 0.28 * size, CHASSIS_Z),
                    axis=Vec3(0, 0, 1))
    if weapon == "drum":       # heavy drum across the front, spinning upwards into the enemy
        return dict(half=h, top=top, drum=(0.2 * size, h.x * 0.8), pivot=Point3(0, h.y + 0.18, CHASSIS_Z - 0.02),
                    axis=Vec3(1, 0, 0))
    if weapon == "vdisc":      # a big vertical disc in a slot at the front
        r = 0.42 * size
        ride = HOUSE_WHEEL_R - 0.08
        return dict(half=h, top=top, disc=(r, 0.035 * size), pivot=Point3(0, h.y + 0.05, r - ride + 0.04),
                    axis=Vec3(1, 0, 0))
    if weapon == "flame":      # a fixed nozzle on top, pointing forwards
        return dict(half=h, top=top, nozzle=Vec3(0.07 * size, 0.22 * size, 0.07 * size),
                    pivot=Point3(0, h.y - 0.25 * size, top + 0.12 * size), axis=Vec3(1, 0, 0))
    if weapon == "chainsaw":   # an arm on top that lowers a chainsaw bar onto whatever is in front
        return dict(half=h, top=top, arm=Vec3(0.06 * size, 0.3 * size, 0.05 * size),
                    bar=Vec3(0.025 * size, 0.42 * size, 0.07 * size), pivot=Point3(0, h.y * 0.35, top + 0.12),
                    axis=Vec3(1, 0, 0))
    # hammer: arm hinged on top, head at the far end
    return dict(half=h, top=top, arm=Vec3(0.05 * min(size, 1.3), min(0.85 * size, 1.3), 0.05 * min(size, 1.3)),
                head=Vec3(0.22, 0.14, 0.14) * size,
                pivot=Point3(0, -0.2 * size, top + 0.1), axis=Vec3(1, 0, 0))


# ---------- computer drivers ----------

def angle_to(me, point):
    """Degrees to turn to face a point (positive = turn left)."""
    to = Vec3(point.x - me.pos.x, point.y - me.pos.y, 0)
    f = me.forward
    return math.degrees(math.atan2(f.x * to.y - f.y * to.x, f.x * to.x + f.y * to.y)), to.length()


def chase_brain(me, enemies, arena):
    """Computer driver: head for the nearest robot, avoid the pit, attack when close."""
    if not enemies:
        return 0.0, 0.0, False
    target = min(enemies, key=lambda e: (e.pos - me.pos).length())
    angle, dist = angle_to(me, target.pos)
    steer = max(-1.0, min(1.0, angle / 30))
    throttle = 1.0 if abs(angle) < 45 else 0.25
    if arena.hazards["pit"] and arena.pit_open:
        pa, pd = angle_to(me, Point3(arena.PIT[0], arena.PIT[1], 0))
        if pd < arena.PIT[2] + 1.5 and abs(pa) < 70:
            steer, throttle = (-1.0 if pa > 0 else 1.0), 0.3
    return throttle, steer, dist < 2.6 * me.stats["size"] and abs(angle) < 25


def house_brain(me, enemies, arena):
    """House robot: wait in your corner; attack anyone who comes into your zone; never chase far."""
    h = ARENA / 2
    home = Point3(me.corner[0] * (h - 1.7), me.corner[1] * (h - 1.7), 0)
    intruders = [e for e in enemies if in_zone(e.pos, me.corner, 0.6)]
    if intruders and in_zone(me.pos, me.corner, 1.5):
        target = min(intruders, key=lambda e: (e.pos - me.pos).length())
        angle, dist = angle_to(me, target.pos)
        steer = max(-1.0, min(1.0, angle / 25))
        # how close to get (centre to centre) before stopping, and how close to use the weapon
        stop, reach = {"flame": (2.6, 3.6), "hammer": (2.7, 3.1), "chainsaw": (2.3, 2.9), "vdisc": (0.0, 2.6)}[me.weapon]
        throttle = 0.0 if dist < stop else (0.9 if abs(angle) < 40 else 0.2)
        return throttle, steer, dist < reach and abs(angle) < 30
    angle, dist = angle_to(me, home)
    if dist > 0.5:  # go home (backwards if home is behind)
        if abs(angle) > 110:
            back = angle - 180 if angle > 0 else angle + 180
            return -0.7, max(-1.0, min(1.0, -back / 25)), False
        return (0.8 if abs(angle) < 40 else 0.15), max(-1.0, min(1.0, angle / 25)), False
    angle, _ = angle_to(me, Point3(0, 0, 0))  # at home: face the middle and wait
    return 0.0, (max(-1.0, min(1.0, angle / 25)) if abs(angle) > 8 else 0.0), False


# ---------- robots ----------

class Robot:
    def __init__(self, arena, rid, design, pos, heading, brain=chase_brain, owner="cpu", stats=None, house=False):
        self.arena, self.id, self.design, self.brain, self.owner = arena, rid, design, brain, owner
        self.house = house                              # a computer-driven house robot guarding a corner
        self.model = design.get("model") if design.get("model") in HOUSE_BY_NAME else None  # a player's house robot
        self.big = house or self.model is not None
        self.name = str(design["name"])[:20]
        self.colour = tuple(v / 255 for v in design["colour"])
        self.weapon = HOUSE_BY_NAME[self.model][0] if self.model else design["weapon"]
        if stats is None and self.model:
            stats = PLAYABLE_HOUSE_STATS
        self.stats = dict(stats) if stats else build_stats(design)
        self.shape = shapes(self.weapon, self.stats["size"])
        self.health = self.stats["armour"]
        self.control = (0.0, 0.0, False)
        self.weapon_on = True
        self.damage_dealt = self.damage_taken = 0.0
        self.hits = 0
        self.knocked_out = False
        self.upside_down_since = None
        self.fire_until = -10.0
        self.launched = set()  # robots already launched by the current flip
        self.start = (pos, heading)
        self.corner = None
        self.swing = 0.0
        self.fires = 0
        self.coast_until = 0.0  # a flipper's plate swings freely for a moment after a flip
        self.part_max = part_hit_points(self.stats["armour"])  # real damage: each part's hit points
        self.part_hp = dict(self.part_max)
        self.lost = set()       # parts that have come off
        self.wheel_r = HOUSE_WHEEL_R if self.big else WHEEL_R
        world, root, sh = arena.world, arena.root, self.shape

        body = BulletRigidBodyNode(f"chassis{rid}")
        body.addShape(BulletBoxShape(sh["half"]), TransformState.makePos(Point3(0, 0, CHASSIS_Z)))
        body.setMass(self.stats["mass"])
        body.setDeactivationEnabled(False)
        self.np = root.attachNewNode(body)
        self.np.setPos(pos)
        self.np.setH(heading)
        world.attachRigidBody(body)
        self.vehicle = BulletVehicle(world, body)
        self.vehicle.setCoordinateSystem(ZUp)
        world.attachVehicle(self.vehicle)
        s = self.stats["size"]
        for x, y in WHEELS:
            w = self.vehicle.createWheel()
            w.setChassisConnectionPointCs(Point3(x * s, y * s, 0.4))  # suspension rest length is fixed at 0.4 m
            w.setFrontWheel(y > 0)
            w.setWheelDirectionCs(Vec3(0, 0, -1))
            w.setWheelAxleCs(Vec3(1, 0, 0))
            w.setWheelRadius(self.wheel_r)
            w.setMaxSuspensionTravelCm(8)
            w.setSuspensionStiffness(40)
            w.setWheelsDampingRelaxation(2.3)
            w.setWheelsDampingCompression(4.4)
            w.setFrictionSlip(self.stats["grip"])
            w.setRollInfluence(0.02)
            w.setMaxSuspensionForce(20000)

        wb = BulletRigidBodyNode(f"weapon{rid}")
        heavy = 2.4 if self.big else 1.0
        if self.weapon == "wedge":
            wb.addShape(BulletBoxShape(sh["plate"]), TransformState.makePos(Point3(0, sh["plate"].y, 0)))
            wb.setMass(4)
            wb.setFriction(0.1)
        elif self.weapon == "spinner":
            wb.addShape(BulletBoxShape(sh["bar"]))
            wb.setMass(3)
        elif self.weapon == "drum":
            r, half_len = sh["drum"]
            wb.addShape(BulletCylinderShape(r, half_len * 2, XUp))
            wb.setMass(6)
        elif self.weapon == "vdisc":
            r, half_t = sh["disc"]
            wb.addShape(BulletCylinderShape(r, half_t * 2, XUp))
            wb.setMass(14)
        elif self.weapon == "flame":
            wb.addShape(BulletBoxShape(sh["nozzle"]), TransformState.makePos(Point3(0, sh["nozzle"].y, 0)))
            wb.setMass(3)
        elif self.weapon == "chainsaw":
            a, b = sh["arm"], sh["bar"]
            wb.addShape(BulletBoxShape(a), TransformState.makePos(Point3(0, a.y, 0)))
            wb.addShape(BulletBoxShape(b), TransformState.makePos(Point3(0, a.y * 2 + b.y - 0.05, -0.04)))
            wb.setMass(8)
        else:
            wb.addShape(BulletBoxShape(sh["arm"]), TransformState.makePos(Point3(0, sh["arm"].y, 0)))
            wb.addShape(BulletBoxShape(sh["head"]), TransformState.makePos(Point3(0, sh["arm"].y * 2, 0)))
            wb.setMass(5 * heavy)
        wb.setDeactivationEnabled(False)
        wb.setCcdMotionThreshold(0.05)
        wb.setCcdSweptSphereRadius(0.06)
        self.weapon_np = root.attachNewNode(wb)
        self.weapon_np.setPos(self.np, sh["pivot"])
        self.weapon_np.setHpr(self.np, 0, 0, 0)
        world.attachRigidBody(wb)
        self.hinge = BulletHingeConstraint(body, wb, sh["pivot"], Point3(0, 0, 0), sh["axis"], sh["axis"], True)
        if self.weapon == "wedge":
            self.hinge.setLimit(self.wedge_rest_angle(), 55)
        elif self.weapon == "hammer":
            self.hinge.setLimit(-5, 115 if self.big else 150)
        elif self.weapon == "chainsaw":
            self.hinge.setLimit(-32, 45)
        elif self.weapon == "flame":
            self.hinge.setLimit(-1, 1)
        world.attachConstraint(self.hinge, True)  # True: a robot can't hit its own weapon
        self.parts = {body.getName(): "chassis", wb.getName(): "weapon"}

    def wedge_rest_angle(self):
        """Angle that puts the wedge's front lip about 2 cm above the floor."""
        drop = self.shape["pivot"].z + RIDE - 0.02  # pivot height above the floor
        return -math.degrees(math.asin(min(0.95, drop / (self.shape["plate"].y * 2))))

    # ---------- handy readings ----------
    @property
    def pos(self):
        return self.np.getPos()

    @property
    def forward(self):
        return self.np.getQuat().getForward()

    @property
    def speed(self):
        """Forward speed in m/s (negative when reversing)."""
        return self.np.node().getLinearVelocity().dot(self.forward)

    def condition(self, part):
        """How healthy a part is, 0 (gone) to 1 (like new)."""
        return 0.0 if part in self.lost else max(0.0, self.part_hp[part]) / self.part_max[part]

    def weapon_spin(self):
        """Spinner/drum speed relative to the robot, in rad/s."""
        if "weapon" in self.lost:
            return 0.0
        axis = self.np.getQuat().xform(self.shape["axis"])
        rel = self.weapon_np.node().getAngularVelocity() - self.np.node().getAngularVelocity()
        return rel.dot(axis)

    @property
    def weapon_rpm(self):
        return abs(self.weapon_spin()) * 60 / (2 * math.pi) if self.weapon in ("spinner", "drum", "vdisc") else 0

    def weapon_energy(self):
        """Kinetic energy stored in a spinning weapon: E = 1/2 x I x w^2 (joules)."""
        if self.weapon == "spinner":
            b = self.shape["bar"]
            inertia = 3 * ((2 * b.x) ** 2) / 12
        elif self.weapon == "drum":
            inertia = 0.5 * 6 * self.shape["drum"][0] ** 2
        elif self.weapon == "vdisc":
            inertia = 0.5 * 14 * self.shape["disc"][0] ** 2
        else:
            return 0.0
        return 0.5 * inertia * self.weapon_spin() ** 2

    def flaming(self, now):
        return (self.weapon == "flame" and self.weapon_on and not self.knocked_out and now < self.fire_until
                and "weapon" not in self.lost)

    def nozzle(self):
        """Where the flame comes out, and which way it points."""
        tip = self.weapon_np.getPos() + self.np.getQuat().getForward() * self.shape["nozzle"].y * 2
        return tip, self.np.getQuat().getForward()

    # ---------- every tick ----------
    def tick(self, enemies, now):
        if self.knocked_out:
            throttle, steer, attack = 0.0, 0.0, False
        elif self.brain:
            throttle, steer, attack = self.brain(self, enemies, self.arena)
        else:
            throttle, steer, attack = self.control
        st = self.stats
        # speed limits from the forward/reverse settings
        v = self.speed
        if (throttle > 0 and v > st["forward_max"]) or (throttle < 0 and -v > st["reverse_max"]):
            throttle = 0.0
        # turning: skid steering, capped by the turn speed setting
        yaw_rate = self.np.node().getAngularVelocity().z
        # motors: acceleration sets how hard the wheels push (force = mass x acceleration, over 4 wheels)
        body = self.np.node()
        force = body.getMass() * st["accel"] / 4 * (1.6 if throttle * v < 0 else 1.0)  # braking bites harder
        for i, (x, _) in enumerate(WHEELS):
            wheel = self.condition(f"wheel{i}")  # real damage: a damaged wheel pushes less, a lost one not at all
            self.vehicle.applyEngineForce(force * throttle * (0.5 + 0.5 * wheel if wheel > 0 else 0.0), i)
            self.vehicle.setBrake((3.0 if not self.big else 12.0) if throttle == 0 and steer == 0 else 0.0, i)
        # turning: steer asks for a turn rate up to the turn speed setting; the motors push towards it
        if self.np.getQuat().getUp().z > 0.5:
            want = steer * st["turn_rate"]
            inertia = body.getMass() * ((2 * self.shape["half"].x) ** 2 + (2 * self.shape["half"].y) ** 2) / 12
            body.applyTorque(Vec3(0, 0, inertia * 40 * (want - yaw_rate)))

        if "weapon" in self.lost:  # it has come off: nothing to drive
            return
        on = self.weapon_on and not self.knocked_out
        power = st["power"] * (0.7 + 0.3 * self.condition("weapon"))  # a damaged weapon is weaker
        was_firing = now < self.fire_until
        if self.weapon == "spinner":
            self.hinge.enableAngularMotor(True, 32 * power if on else 0.0, 5.0 * power if on else 1.5)
        elif self.weapon == "drum":
            self.hinge.enableAngularMotor(True, -45 * power if on else 0.0, 6.0 * power if on else 1.5)
        elif self.weapon == "vdisc":
            self.hinge.enableAngularMotor(True, -38 * power if on else 0.0, 14.0 * power if on else 3.0)
        elif self.weapon == "flame":
            self.hinge.enableAngularMotor(True, 0.0, 200.0)
            if attack and on and now >= self.fire_until + 0.7:
                self.fire_until = now + 1.4  # a burst of flame
        elif self.weapon == "chainsaw":
            if attack and on:
                self.fire_until = now + 0.6  # keeps sawing while there's something to saw
            if now < self.fire_until:
                self.hinge.enableAngularMotor(True, -1.0, 1500.0 * power)
            else:
                self.hinge.enableAngularMotor(True, 1.3, 1500.0 * power)
        elif self.weapon == "wedge":
            if attack and on and now >= self.fire_until + 0.9:
                self.fire_until = now + 0.3
                self.launched = set()
            if now < self.fire_until:  # the plate lifts itself; a robot on it is launched in weapon_contact
                self.hinge.enableAngularMotor(True, 14.0, 30.0)   # (gentle, so a robot sitting on it can't lever us over)
            elif now < self.coast_until:
                self.hinge.enableAngularMotor(False, 0.0, 0.0)
            else:
                self.hinge.enableAngularMotor(True, -4.0, 80.0)
        else:
            if attack and on and now >= self.fire_until + (1.4 if self.big else 0.9):
                self.fire_until = now + 0.35
            if self.big:  # a big heavy hammer: a slower swing, so it doesn't throw its own robot about
                speed, strength, back = -9.0, 1400.0, (2.5, 500.0)
            else:
                speed, strength, back = -18.0 * min(power, 1.3), 300.0 * power, (6.0, 80.0)
            if now < self.fire_until:
                self.hinge.enableAngularMotor(True, speed, strength)
            else:
                self.hinge.enableAngularMotor(True, *back)
        if now < self.fire_until and not was_firing:
            self.fires += 1  # (the windows play the weapon's firing sound when this goes up)

    def reset(self, keep_health=False):
        pos, heading = self.start
        for np_ in (self.np, self.weapon_np):
            np_.node().setLinearVelocity(Vec3(0))
            np_.node().setAngularVelocity(Vec3(0))
        self.np.setPos(pos)
        self.np.setHpr(heading, 0, 0)
        if keep_health and "weapon" in self.lost:  # (a weapon that came off stays where it is)
            self.upside_down_since = None
            return
        self.weapon_np.setPos(self.np, self.shape["pivot"])
        self.weapon_np.setHpr(self.np, 0, 0, 0)
        self.upside_down_since = None
        if not keep_health:
            self.repair()
            self.health = self.stats["armour"]
            self.knocked_out = False
            self.damage_dealt = self.damage_taken = 0.0
            self.hits = 0
            self.weapon_on = True

    def repair(self):
        """Every part back on and like new (a new round)."""
        if "weapon" in self.lost:  # the weapon goes back on its hinge (reset has put it in place)
            self.arena.world.attachConstraint(self.hinge, True)
            self.parts[self.weapon_np.node().getName()] = "weapon"
        for i in range(4):
            self.wheel_on(i, True)
        self.lost = set()
        self.part_hp = dict(self.part_max)

    def wheel_on(self, i, on):
        """A wheel on (it holds the robot up and grips) or off (that corner drops and drags on the floor)."""
        w = self.vehicle.getWheel(i)
        w.setMaxSuspensionForce(20000 if on else 0.0)
        w.setFrictionSlip(self.stats["grip"] if on else 0.0)

    def remove(self):
        w = self.arena.world
        if "weapon" not in self.lost:
            w.removeConstraint(self.hinge)
        w.removeVehicle(self.vehicle)  # this also takes the chassis body out of the world
        w.removeRigidBody(self.weapon_np.node())
        self.np.removeNode()
        self.weapon_np.removeNode()


# ---------- the arena floor: holes for the pit and the floor flipper ----------

def floor_holes(hazards=None):
    """Rectangles (x0, y0, x1, y1) cut out of the floor: the drop zone and the floor flipper are always there
    (switched off, the drop zone's floor is up and the flipper lies flat, both flush with the floor)."""
    px, py, ps = Arena.PIT
    fx, fy = Arena.FLOOR_FLIPPER
    return [(px - ps / 2, py - ps / 2, px + ps / 2, py + ps / 2), (fx - 1.5, fy - 1.0, fx + 1.5, fy + 1.0)]


def floor_rects(hazards=None):
    """The floor as rectangles (x0, y0, x1, y1), with the holes cut out. Physics and graphics share this."""
    h = ARENA / 2
    rects = [(-h, -h, h, h)]
    for hx0, hy0, hx1, hy1 in floor_holes(hazards):
        out = []
        for x0, y0, x1, y1 in rects:
            if hx1 <= x0 or hx0 >= x1 or hy1 <= y0 or hy0 >= y1:
                out.append((x0, y0, x1, y1))
                continue
            if hx0 > x0:
                out.append((x0, y0, hx0, y1))
            if hx1 < x1:
                out.append((hx1, y0, x1, y1))
            mx0, mx1 = max(x0, hx0), min(x1, hx1)
            if hy0 > y0:
                out.append((mx0, y0, mx1, hy0))
            if hy1 < y1:
                out.append((mx0, hy1, mx1, y1))
        rects = out
    return rects


# ---------- the arena ----------

class Arena:
    PIT = (3.2, 3.2, 3.0)                       # the drop zone: centre x, y and size
    PIT_OPEN_Z, PIT_CLOSED_Z = -2.95, 0.0       # height of the top of the pit floor when open / closed
    FLOOR_FLIPPER = (-3.5, -3.5)
    FF_HALF = Vec3(1.47, 0.97, 0.08)            # the flipper plate (it sits flush with the floor)
    SAWS = ((4.5, -3.5), (-5.0, 3.5))
    SAW_R, SAW_HALF_T = 1.0, 0.03                # blade radius and half thickness
    SAW_SPIN = 1.0                               # blade turns this way round (the top edge moves towards -x)
    SPIKES = (-ARENA / 2, -2.5, 2.5)            # west wall, from y to y
    STARTS = ((-7.5, 0, -90), (7.5, 0, 90), (-3.5, -7.5, 0), (0, -7.5, 0), (3.5, 7.5, 180), (0, 7.5, 180))

    def __init__(self, root=None, hazards=None, seed=1):
        self.world = BulletWorld()
        self.world.setGravity(Vec3(0, 0, -RULES["gravity"]))
        self.root = root if root is not None else NodePath("arena")
        self.rnd = random.Random(seed)
        self.hazards = {**dict(pit=True, floor_flipper=True, saws=True, spikes=True, house_robots=False),
                        **(hazards or {})}
        self.practice = False  # practice: no damage, and knocked-out robots come back after 2 seconds
        self.real_damage = False  # real damage: each part has hit points and comes off at zero
        self.pit_open = bool(self.hazards["pit"])  # switched off, the drop zone's floor rises flush
        self.time = 0.0
        self.events = []
        self.impacts = []  # (where, how hard, what kind): the graphics turn these into sparks and sounds
        self.streams = []  # (where, which way, how many): showers of sparks from saws grinding a robot
        self.robots = []
        self.owner = {}
        self.cooldown = {}  # (attacker id, victim id) -> time a new hit may land
        self.saw_height = [0.0 for _ in self.SAWS]
        self.saw_hot_until = [0.0 for _ in self.SAWS]
        self.spike_out = 0.0
        self.pit_z = self.PIT_OPEN_Z if self.pit_open else self.PIT_CLOSED_Z
        self.bodies, self.constraints = [], []  # everything build() made
        self.build()
        self.set_house_robots(self.hazards.get("house_robots"))

    def set_hazards(self, hazards):
        """Switch hazards on or off mid-round. Nothing disappears: a hazard that is off just rests (saws down,
        spikes in, flipper flat, drop zone floor up and flush), and the robots carry on where they are."""
        self.hazards = {**self.hazards, **hazards}
        self.pit_open = bool(self.hazards["pit"])
        self.set_house_robots(self.hazards.get("house_robots"))

    def set_house_robots(self, value):
        """Add or remove house robots one by one (True = all, False = none, or a list of names)."""
        wanted = house_list(value)
        for r in [r for r in self.robots if r.house and r.name not in wanted]:
            self.remove_robot(r)
        have = {r.name for r in self.robots if r.house}
        self.add_house_robots([n for n in wanted if n not in have])

    def build(self):
        h = ARENA / 2
        for i, (x0, y0, x1, y1) in enumerate(floor_rects(self.hazards)):
            self.add_static(f"floor{i}", Vec3((x1 - x0) / 2, (y1 - y0) / 2, 0.25), Point3((x0 + x1) / 2, (y0 + y1) / 2, -0.25))
        for i, (cx, cy, hx, hy) in enumerate(((0, h + 0.25, h + 0.5, 0.25), (0, -h - 0.25, h + 0.5, 0.25),
                                              (h + 0.25, 0, 0.25, h), (-h - 0.25, 0, 0.25, h))):
            self.add_static(f"wall{i}", Vec3(hx, hy, 0.6), Point3(cx, cy, 0.6))
            self.add_static(f"screen{i}", Vec3(hx, hy, 3.0), Point3(cx, cy, 4.2))  # clear screens above the walls

        # the drop zone: a floor that lowers into the pit (kinematic: it moves, nothing can move it)
        px, py, ps = self.PIT
        self.pit_lid = self.add_kinematic("pitlid", BulletBoxShape(Vec3(ps / 2 - 0.03, ps / 2 - 0.03, 0.25)),
                                          Point3(px, py, self.pit_z - 0.25))

        # floor flipper: a plate that sits flush in a recess, hinged at its back edge
        fx, fy = self.FLOOR_FLIPPER
        ff = self.FF_HALF
        self.add_static("flipper_recess", Vec3(1.5, 1.0, 0.25), Point3(fx, fy, -ff.z * 2 - 0.26))
        plate = BulletRigidBodyNode("floorflipper")
        plate.addShape(BulletBoxShape(ff), TransformState.makePos(Point3(0, 1.0, 0)))
        plate.setMass(40)
        plate.setDeactivationEnabled(False)
        self.floor_flipper = self.root.attachNewNode(plate)
        self.floor_flipper.setPos(fx, fy - 1.0, -ff.z)
        self.world.attachRigidBody(plate)
        anchor = BulletRigidBodyNode("flipper_anchor")
        anchor.addShape(BulletBoxShape(Vec3(0.1, 0.1, 0.1)))
        anchor_np = self.root.attachNewNode(anchor)
        anchor_np.setPos(fx, fy - 1.0, -0.35)
        self.world.attachRigidBody(anchor)
        self.bodies += [self.floor_flipper, anchor_np]
        self.ff_hinge = BulletHingeConstraint(anchor, plate, Point3(0, 0, 0.35 - ff.z), Point3(0, 0, 0),
                                              Vec3(1, 0, 0), Vec3(1, 0, 0), True)
        self.ff_hinge.setLimit(0, 60)
        self.world.attachConstraint(self.ff_hinge, True)
        self.constraints.append(self.ff_hinge)

        # floor saws: solid blades that rise out of slots (robots bounce off them instead of passing through)
        self.saws = []
        for i, (sx, sy) in enumerate(self.SAWS):
            self.saws.append(self.add_kinematic(f"saw{i}", BulletCylinderShape(self.SAW_R, self.SAW_HALF_T * 2, YUp),
                                                Point3(sx, sy, self.saw_z(0.0))))

        # wall spikes: a bank of spikes that shoots out of the west wall
        wx, y0, y1 = self.SPIKES
        self.spikes = self.add_kinematic("spikes", BulletBoxShape(Vec3(0.3, (y1 - y0) / 2 + 0.1, 0.42)),
                                         Point3(self.spike_x(0.0), (y0 + y1) / 2, 0.45))

    def set_pit(self, open_, instant=False):
        """Open or close the drop zone (instant: no lowering or rising, e.g. when the arena is rebuilt)."""
        self.pit_open = bool(open_)
        self.hazards["pit"] = self.pit_open
        if instant:
            self.pit_z = self.PIT_OPEN_Z if self.pit_open else self.PIT_CLOSED_Z
            if self.pit_lid is not None:
                self.pit_lid.setZ(self.pit_z - 0.25)

    def add_static(self, name, half, pos):
        node = BulletRigidBodyNode(name)
        node.addShape(BulletBoxShape(half))
        np_ = self.root.attachNewNode(node)
        np_.setPos(pos)
        self.world.attachRigidBody(node)
        self.bodies.append(np_)
        return np_

    def add_kinematic(self, name, shape, pos):
        node = BulletRigidBodyNode(name)
        node.addShape(shape)
        node.setKinematic(True)
        np_ = self.root.attachNewNode(node)
        np_.setPos(pos)
        self.world.attachRigidBody(node)
        self.bodies.append(np_)
        return np_

    @staticmethod
    def saw_z(height):
        return -1.1 + height * 1.35  # blade centre: fully down it is hidden under the floor

    @classmethod
    def spike_x(cls, out):
        """Centre of the spike bank: hidden in the wall (out = 0), or with its spikes 0.6 m out (out = 1)."""
        return cls.SPIKES[0] - 0.5 + out * 0.6

    # ---------- robots ----------
    def add_robot(self, design, brain=chase_brain, owner="cpu", start=None):
        used = {r.start_index for r in self.robots}
        idx = start if start is not None else next(i for i in range(len(self.STARTS)) if i not in used)
        x, y, heading = self.STARTS[idx]
        rid = max([r.id for r in self.robots], default=-1) + 1
        r = Robot(self, rid, design, Point3(x, y, 0.5), heading, brain, owner)
        r.start_index = idx
        self.robots.append(r)
        self.owner.update({name: r for name in r.parts})
        return r

    def add_house_robots(self, names=None):
        h = ARENA / 2
        for name, weapon, colour, corner in HOUSE_ROBOTS:
            if names is not None and name not in names:
                continue
            x, y = corner[0] * (h - 1.7), corner[1] * (h - 1.7)
            heading = math.degrees(math.atan2(corner[0], -corner[1]))  # facing the middle
            rid = max([r.id for r in self.robots], default=-1) + 1
            r = Robot(self, rid, house_design(name, weapon, colour), Point3(x, y, 0.6), heading, house_brain,
                      "House robot", stats=HOUSE_STATS, house=True)
            r.corner, r.start_index = corner, None
            self.robots.append(r)
            self.owner.update({n: r for n in r.parts})

    def remove_robot(self, r):
        for name in r.parts:
            self.owner.pop(name, None)
        r.remove()
        self.robots.remove(r)

    def restart(self):
        for r in self.robots:
            r.reset()
        self.cooldown.clear()
        self.events.append((self.time, "FIGHT!"))

    # ---------- every tick ----------
    def step(self):
        self.time += STEP
        now = self.time
        self.move_hazards(now)
        live = [r for r in self.robots if not r.knocked_out]
        for r in self.robots:
            r.tick([e for e in live if e is not r and not e.house], now)
            r.swing = r.weapon_np.node().getAngularVelocity().length()  # before the step: a hit stops the swing
        self.world.doPhysics(STEP, 6, SUBSTEP)
        self.contacts(now)
        self.flame_hits(now)
        self.check_knockouts(now)

    def move_hazards(self, now):
        """Hazards that are switched off rest: flipper flat, saws down in their slots, spikes inside the wall."""
        on = self.hazards
        up = on["floor_flipper"] and (now % RULES["floor_flipper_every"]) < 0.6
        self.ff_hinge.enableAngularMotor(True, 4.0 if up else -2.0, 500.0 if up else 400.0)
        cycle = RULES["saw_cycle"]
        for i, saw in enumerate(self.saws):  # saws rise for saw_up_seconds in every saw_cycle
            target = 1.0 if on["saws"] and (now + i * cycle / 2) % cycle < RULES["saw_up_seconds"] else 0.0
            self.saw_height[i] += (target - self.saw_height[i]) * 0.15
            saw.setZ(self.saw_z(self.saw_height[i]))
        if self.spikes is not None:  # out fast, back slowly
            target = 1.0 if on["spikes"] and now % RULES["spike_cycle"] < 1.2 else 0.0
            self.spike_out += (target - self.spike_out) * (0.35 if target > self.spike_out else 0.08)
            self.spikes.setX(self.spike_x(self.spike_out))
        if self.pit_lid is not None:  # the drop zone floor lowers (open) or rises (closed) at 1.2 m/s
            want = self.PIT_OPEN_Z if self.pit_open else self.PIT_CLOSED_Z
            self.pit_z += max(-1.2 * STEP, min(1.2 * STEP, want - self.pit_z))
            self.pit_lid.setZ(self.pit_z - 0.25)

    def hit(self, attacker, victim, damage, now, text, point=None, kind="hit", where="chassis"):
        """where: the part of the victim that was touched ("chassis" or "weapon")."""
        p = point if point is not None else victim.pos
        self.impacts.append(((p.x, p.y, max(0.1, p.z)), damage, kind))
        if attacker:
            damage *= RULES["damage_multiplier"]
            attacker.hits += 1
        if self.practice:  # count it, but nobody loses armour
            self.events.append((now, f"{text} (practice)"))
            return
        victim.health -= self.share_damage(victim, damage, p, where, now) if self.real_damage else damage
        victim.damage_taken += damage
        if attacker:
            attacker.damage_dealt += damage
        self.events.append((now, f"{text} ({damage:.0f} damage)"))

    def share_damage(self, r, damage, point, where, now):
        """Real damage: the part that was hit takes a share, and the body takes the rest (all of it once that part
        has come off). Returns the body's share."""
        if where == "weapon":
            shares = {"weapon": 0.7}
        else:
            local = r.np.getRelativePoint(self.root, point)  # where the hit landed, measured on the robot
            s = r.stats["size"]
            i = min(range(4), key=lambda k: (local.x - WHEELS[k][0] * s) ** 2 + (local.y - WHEELS[k][1] * s) ** 2)
            near = math.hypot(local.x - WHEELS[i][0] * s, local.y - WHEELS[i][1] * s) < 0.4 * s
            shares = {f"wheel{i}": 0.4, "armour": 0.36} if near else {"armour": 0.6}
        body = damage
        for part, share in shares.items():
            if part in r.lost:
                continue
            take = min(damage * share, r.part_hp[part])
            r.part_hp[part] -= take
            body -= take
            if r.part_hp[part] <= 0.01:
                self.detach(r, part, now)
        return body

    def detach(self, r, part, now):
        """A part at zero comes off."""
        r.lost.add(part)
        r.part_hp[part] = 0.0
        p = r.pos
        self.impacts.append(((p.x, p.y, max(0.3, p.z + 0.3)), 30.0, "break"))
        if part == "weapon":  # off its hinge: it falls into the arena (and anyone can push it about)
            self.world.removeConstraint(r.hinge)
            wb = r.weapon_np.node()
            r.parts[wb.getName()] = "loose"
            wb.setLinearVelocity(r.np.node().getLinearVelocity() + r.forward * 1.5 + Vec3(0, 0, 2.5))
            wb.setAngularVelocity(wb.getAngularVelocity() * 0.15)  # (a spinner that comes off tumbles, not flies)
            self.events.append((now, f"{r.name}'s weapon is RIPPED OFF!"))
        elif part == "armour":
            self.events.append((now, f"{r.name}'s armour falls off!"))
        else:
            r.wheel_on(int(part[5:]), False)
            self.events.append((now, f"{r.name} loses a wheel!"))

    def contacts(self, now):
        """Everything touching after the physics step: weapons hitting robots, and robots hitting hazards."""
        for m in self.world.getManifolds():
            if m.getNumManifoldPoints() == 0:
                continue
            n0, n1 = m.getNode0().getName(), m.getNode1().getName()
            mp = m.getManifoldPoints()[0]
            for this, other, point in ((n0, n1, mp.getPositionWorldOnB()), (n1, n0, mp.getPositionWorldOnA())):
                v = self.owner.get(other)
                if not v or v.knocked_out or v.parts.get(other) == "loose":
                    continue
                where = v.parts.get(other)
                if this.startswith("saw"):
                    self.saw_contact(int(this[3:]), v, point, now, where)
                elif this == "spikes":
                    self.spike_contact(v, point, now, where)
                else:
                    a = self.owner.get(this)
                    if not a or a is v or a.parts.get(this) != "weapon":
                        continue
                    key = (a.id, v.id)
                    if now < self.cooldown.get(key, 0):
                        continue
                    self.weapon_contact(a, v, point, now, key, where)
            self.bump(m, n0, n1, mp, now)

    def bump(self, m, n0, n1, mp, now):
        """Robots banging into each other or into the walls: a sound and a few sparks, no damage."""
        a0, a1 = self.owner.get(n0), self.owner.get(n1)
        wall = n0.startswith(("wall", "screen")) or n1.startswith(("wall", "screen"))
        robots = a0 is not None and a1 is not None and a0 is not a1 and \
            a0.parts.get(n0) == "chassis" and a1.parts.get(n1) == "chassis"
        r = a0 or a1
        if not (robots or (wall and r is not None and r.parts.get(n0 if a0 else n1) == "chassis")):
            return
        speed = max(p.getAppliedImpulse() for p in m.getManifoldPoints()) / r.np.node().getMass() * 6
        key = ("bump", n0, n1)
        if speed > 0.7 and now >= self.cooldown.get(key, 0):
            p = mp.getPositionWorldOnA()
            self.impacts.append(((p.x, p.y, max(0.1, p.z)), min(20.0, speed * 4), "wall" if wall else "bump"))
            self.cooldown[key] = now + 0.4

    def weapon_contact(self, a, v, point, now, key, where="chassis"):
        vb = v.np.node()
        up = Vec3(0, 0, 1)
        if a.weapon in ("spinner", "drum", "vdisc"):
            energy = a.weapon_energy()
            if energy < 15:  # barely spinning: just a bump
                return
            transfer = RULES["spinner_energy_share"] * energy
            away = Vec3(v.pos.x - a.pos.x, v.pos.y - a.pos.y, 0)
            away.normalize()
            if a.weapon == "spinner":   # smash sideways and a little up
                direction = away + a.np.getQuat().getRight() * 0.3 + up * 0.25
            else:                       # the drum and the vertical disc throw their victim upwards
                direction = away * 0.55 + up * 0.85
            direction.normalize()
            impulse = min(math.sqrt(2 * vb.getMass() * transfer), RULES["max_launch_speed"] * vb.getMass())
            vb.applyImpulse(direction * impulse, point - v.pos)
            a.np.node().applyCentralImpulse(-away * impulse * 0.3)  # recoil: spinners bounce off too
            # the weapon loses the energy it handed over and has to spin up again
            spin_left = math.sqrt(max(0.0, 1 - RULES["spinner_energy_share"]))
            axis = a.np.getQuat().xform(a.shape["axis"])
            wv = a.weapon_np.node().getAngularVelocity()
            a.weapon_np.node().setAngularVelocity(wv - axis * a.weapon_spin() * (1 - spin_left))
            damage = min(40.0, transfer / 12) * (RULES["hazard_damage"] if a.house else 1.0)
            verb = "SMASHES" if a.weapon == "spinner" else "LAUNCHES"
            self.hit(a, v, damage, now, f"{a.name} {verb} {v.name}", point, "drum" if a.weapon == "vdisc" else a.weapon,
                     where)
            self.cooldown[key] = now + 0.35
        elif a.weapon == "wedge":
            if now < a.fire_until and v.id not in a.launched:  # flipper is firing with the robot on it
                a.launched.add(v.id)
                # the plate stops pushing once it has done its job (and swings freely for a moment), so it can't
                # lever its own robot over
                a.fire_until, a.coast_until = now, now + 0.35
                if (v.big or vb.getMass() > 2.5 * a.np.node().getMass()) and a.stats.get("flip_strength", 1.0) < 0.999:
                    # too heavy to flip unless the flipper is at 100%: it lifts the robot a little instead
                    vb.applyCentralImpulse(up * vb.getMass() * 2.2)
                    self.hit(a, v, 1.0, now, f"{a.name} lifts {v.name}: too heavy to flip", point, "flip", where)
                    self.cooldown[key] = now + 0.5
                    return
                lift = vb.getMass() * min(RULES["max_launch_speed"] * 0.7, (2.5 + 2.0 * a.stats["power"]) * RULES["flip_power"])
                fwd = a.forward
                vb.applyImpulse(up * lift + fwd * lift * 0.35, point - v.pos)
                vb.setAngularVelocity(vb.getAngularVelocity() + a.np.getQuat().getRight() * 5.0)
                self.hit(a, v, 3 + 4 * a.stats["power"], now, f"{a.name} FLIPS {v.name}", point, "flip", where)
                self.cooldown[key] = now + 0.5
        elif a.weapon == "hammer":
            if now < a.fire_until:
                head_speed = max(a.swing, a.weapon_np.node().getAngularVelocity().length()) * a.shape["arm"].y * 2
                if head_speed > 4:
                    vb.applyImpulse(-up * vb.getMass() * 2.0, point - v.pos)
                    damage = min(35.0, head_speed * 2.2 * a.stats["power"])
                    if a.big:
                        damage = min(30.0, damage) * (RULES["hazard_damage"] if a.house else 1.0)
                    self.hit(a, v, damage, now, f"{a.name} HAMMERS {v.name}", point, "hammer", where)
                    self.cooldown[key] = now + 0.6
        elif a.weapon == "chainsaw":
            if now < a.fire_until and a.weapon_on:  # the chain drags the victim forwards and down
                fwd = a.forward
                vb.applyImpulse((fwd * 1.6 - up * 0.8) * vb.getMass(), point - v.pos)
                self.hit(a, v, 4.0 * RULES["hazard_damage"], now, f"{a.name} SAWS INTO {v.name}", point, "saw", where)
                self.streams.append(((point.x, point.y, point.z), tuple(fwd * 0.6 + up * 0.8), 10))
                self.cooldown[key] = now + 0.25

    def saw_contact(self, i, r, point, now, where="chassis"):
        """A floor saw touching a robot: sparks fly, and the robot is thrown the way the blade is turning."""
        if self.saw_height[i] < 0.3:
            return
        sx, sy = self.SAWS[i]
        centre = Point3(sx, sy, self.saw_z(self.saw_height[i]))
        spoke = point - centre
        edge = Vec3(0, -self.SAW_SPIN, 0).cross(spoke)  # the way the blade's surface moves at that point
        if edge.length() < 1e-4:
            return
        edge.normalize()
        self.streams.append(((point.x, point.y, point.z), tuple(edge), 8))  # grinding sparks, every tick
        self.saw_hot_until[i] = now + 0.2
        key = ("saw", i, r.id)
        if now < self.cooldown.get(key, 0):
            return
        side = Vec3(0, 1 if r.pos.y > sy else -1, 0)  # also pushed off the face of the blade
        body = r.np.node()
        push = edge * 4.5 + side * 1.5 + Vec3(0, 0, 1.2)
        body.applyImpulse(push * body.getMass() * (0.35 if r.house else 1.0), point - r.pos)
        self.hit(None, r, 7 * RULES["hazard_damage"], now, f"{r.name} hits the saw", point, "saw", where)
        self.cooldown[key] = now + 0.35

    def spike_contact(self, r, point, now, where="chassis"):
        if self.spike_out < 0.3:
            return
        key = ("spikes", r.id)
        if now < self.cooldown.get(key, 0):
            return
        body = r.np.node()
        body.applyCentralImpulse(Vec3(4, 0, 1) * body.getMass() * (0.3 if r.house else 1.0))
        self.hit(None, r, 5 * RULES["hazard_damage"], now, f"{r.name} hits the wall spikes", point, "spikes", where)
        self.cooldown[key] = now + 0.8

    def flame_hits(self, now):
        """Flame throwers burn anything in a cone in front of the nozzle."""
        for a in self.robots:
            if not a.flaming(now):
                continue
            tip, fwd = a.nozzle()
            for v in self.robots:
                if v is a or v.knocked_out:
                    continue
                to = v.pos - tip
                to.z = 0  # the flame pours down onto robots, so only the direction across the floor matters
                flat = Vec3(fwd.x, fwd.y, 0)
                dist = to.length()
                if dist > 3.0 or dist < 1e-3 or flat.length() < 0.5 or                         flat.normalized().dot(to / dist) < math.cos(math.radians(26)):
                    continue
                key = ("flame", a.id, v.id)
                if now >= self.cooldown.get(key, 0):
                    self.hit(a, v, 3.0 * RULES["hazard_damage"], now, f"{a.name} TORCHES {v.name}",
                             v.pos + Vec3(0, 0, 0.3), "flame")
                    self.cooldown[key] = now + 0.25

    def check_knockouts(self, now):
        h = ARENA / 2
        for r in self.robots:
            p = r.pos
            if r.house:  # house robots: out of action at zero (until the next round); if stuck, they are put back
                if r.knocked_out:
                    continue
                if r.health <= 0:
                    self.knock_out(r, now, f"{r.name} is out of action!")
                    continue
                stuck = p.z < -1 or abs(p.x) > h + 1 or abs(p.y) > h + 1 or r.np.getQuat().getUp().z < 0.3
                if stuck:
                    r.upside_down_since = r.upside_down_since if r.upside_down_since is not None else now
                    if now - r.upside_down_since > 2.0:
                        r.reset(keep_health=True)
                else:
                    r.upside_down_since = None
                continue
            if r.knocked_out:
                if self.practice and now >= getattr(r, "back_at", 0):
                    r.reset()
                    self.events.append((now, f"{r.name} is back"))
                continue
            if p.z < -2:
                self.knock_out(r, now, f"{r.name} fell in the pit!")
            elif abs(p.x) > h + 1 or abs(p.y) > h + 1:
                self.knock_out(r, now, f"{r.name} was thrown out of the arena!")
            elif r.health <= 0:
                self.knock_out(r, now, f"{r.name} is knocked out!")
            elif sum(k.startswith("wheel") for k in r.lost) >= 3:
                self.knock_out(r, now, f"{r.name} is immobilised!")
            elif r.np.getQuat().getUp().z < 0.3:
                if r.upside_down_since is None:
                    r.upside_down_since = now
                elif now - r.upside_down_since > r.stats["self_right"]:
                    self.events.append((now, f"{r.name} self-rights"))
                    r.np.node().setLinearVelocity(Vec3(0))
                    r.np.node().setAngularVelocity(Vec3(0))
                    r.np.setPos(p.x, p.y, 0.8)
                    r.np.setHpr(r.np.getH(), 0, 0)
                    if "weapon" not in r.lost:
                        r.weapon_np.setPos(r.np, r.shape["pivot"])
                        r.weapon_np.setHpr(r.np, 0, 0, 0)
                    r.upside_down_since = None
            else:
                r.upside_down_since = None

    def knock_out(self, r, now, text):
        r.knocked_out = True
        r.back_at = now + 2
        r.health = max(0.0, r.health)
        self.events.append((now, text))

    # ---------- for the graphics ----------
    def hazard_state(self):
        """How the moving parts of the arena are placed right now."""
        return {"t": round(self.time, 2), "saws": [round(h, 2) for h in self.saw_height],
                "ff": [round(v, 4) for v in tuple(self.floor_flipper.getQuat())] if self.floor_flipper else None,
                "pit": round(self.pit_z, 2) if self.pit_lid is not None else None, "pit_open": self.pit_open,
                "on": {k: bool(self.hazards[k]) for k in ("pit", "floor_flipper", "saws", "spikes")},
                "spikes": round(self.spike_out, 2),
                "saw_hot": [1 if self.time < t else 0 for t in self.saw_hot_until]}

    def take_fx(self):
        """New hits and spark showers since the last call (then forgets them)."""
        impacts, streams = self.impacts, self.streams
        self.impacts, self.streams = [], []
        return impacts, streams
