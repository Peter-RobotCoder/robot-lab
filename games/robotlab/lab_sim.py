"""Robot Lab physics: the arena, robots built from a learner's design, weapons, hazards and Resident Robots.

A design is plain data a learner can read and change:
    points   - 100 points shared between speed, attack, armour and control
    settings - percentages that tune how the robot uses what the points bought
    weapon   - wedge (with flipper), horizontal spinner, drum (vertical spinner) or hammer

Weapons do "real type" damage: a spinner stores kinetic energy (1/2 x I x w squared) and hands
part of it to whatever it hits, then has to spin up again; a wedge's flipper launches a robot that
is sitting on it; a hammer hits harder the faster its head is moving.

The arena has floor saws (solid spinning blades that throw you the way they turn), a floor flipper that
sits flush with the floor, wall spikes that shoot in and out, a drop zone (pit) the teacher can open and
close, and four heavy Resident Robots that guard the corners.

Real damage (the teacher switches it on): each part of a robot has its own hit points. A hit is shared between
the part it lands on (a wheel, the weapon, the armour) and the body. A part at zero comes off: a lost wheel
stops driving and that corner drags on the floor, a lost weapon falls into the arena, lost armour stops
protecting the body. The body at zero is a knockout, as always.
No graphics here: this runs on the teacher's server.
"""
import math

import lab_version  # noqa: F401  (puts the engine, shared by every game, on the path)
import random

from panda3d.bullet import (BulletBoxShape, BulletCylinderShape, BulletHingeConstraint, BulletRigidBodyNode,
                            BulletVehicle, BulletWorld, XUp, YUp, ZUp)
from panda3d.core import NodePath, Point3, TransformState, Vec3

STEP, SUBSTEP = 1 / 60, 1 / 180
MAX_SPEED = 30.0  # m/s: nothing in the arena is ever really this fast (the quickest robot does 23, the hardest hit
#                   throws one at 7), so anything faster is the physics getting two big robots untangled: held to this
ARENA = 20.0  # metres square
MAX_ARENAS = 6  # cages side by side (CHANGE 75): every learner can practise in one of their own

# Game rules. mods/rules.py can change any of these (the teacher approves every change).
DEFAULT_RULES = {
    "match_seconds": 180,          # length of a battle
    "damage_multiplier": 1.0,      # all weapon damage is multiplied by this
    "spinner_energy_share": 0.6,   # share of a spinner's stored energy handed to the robot it hits
    "max_launch_speed": 7.0,       # m/s: the most any hit can throw a robot (about 2.5 m of air)
    "flip_power": 1.0,             # wedge flipper launch multiplier
    "gravity": 9.81,               # m/s squared
    "hazard_damage": 1.0,          # saw, spike and Resident Robot damage multiplier
    "floor_flipper_every": 4.0,    # seconds between floor flipper shots
    "saw_cycle": 5.0,              # saws rise once every this many seconds...
    "saw_up_seconds": 2.0,         # ...and stay up this long
    "spike_cycle": 4.0,            # wall spikes shoot out once every this many seconds
}
RULES = dict(DEFAULT_RULES)

# ---------- the design sheet ----------

STATS = ("speed", "attack", "armour", "control")
# What learners get unless the teacher changes it (the teacher's Limits tab; see default_limits and full_limits):
POINTS_TOTAL, STAT_MIN, STAT_MAX = 100, 5, 50
STANDARD_MASS = 30.0  # kg: the standard robot (25 armour points, size 100%); weight is measured against it
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
HOUSE_WEAPONS = ("flame", "hammer", "chainsaw", "vdisc")  # Resident Robots only
# Every robot starts with its weapon off. Space is the one weapon key: it switches these weapons on and off
# (they spin until switched off), and fires the others (wedge, hammer, flame, chainsaw) while it's pressed.
TOGGLE_WEAPONS = ("spinner", "drum", "vdisc")

# Pushing. A robot's push is its motors' force: its mass x its acceleration (newtons). A robot that another robot
# is driving into keeps only PUSH_GRIP of its grip, so it can be slid along: it moves when the pushes on it (two
# robots' pushes add up) beat its hold, which is PUSH_GRIP x its grip x its weight (its mass x gravity).
# A Resident Robot holds against about 540 N: more than any one standard robot's push, less than two strong ones'.
PUSH_GRIP = 0.12

# The widest anything can go: the teacher's own robot, and the widest range the teacher can give the learners.
FULL_SETTINGS = {"forward_speed": (0, 100), "reverse_speed": (0, 100), "turn_speed": (0, 100),
                 "acceleration": (0, 100), "size": (12.5, 200)}  # size: 1/8 of standard size to 16/8 (double)
FULL_STAT = (0, 100)       # each of the four points
FULL_POINTS_TOTAL = 400    # the most points there can be to share


LIMITS = None  # the engine's limits Spec (made below, once the engine can be imported)


def _limits():
    global LIMITS
    if LIMITS is None:
        from engine.limits import Spec
        LIMITS = Spec(SETTINGS, FULL_SETTINGS, STATS, (STAT_MIN, STAT_MAX), FULL_STAT, POINTS_TOTAL, FULL_POINTS_TOTAL)
    return LIMITS


def default_limits():
    """The learners' ranges as they are until the teacher changes them."""
    return _limits().default()


def full_limits():
    """The widest ranges: the teacher's own robot is checked against these."""
    return _limits().full()


def clean_limits(new, old=None):
    """Limits sent by the teacher's window (or loaded from a file), made safe."""
    return _limits().clean(new, old)


def fit_design(d, limits):
    """A design pulled back inside the limits (the teacher has narrowed them)."""
    return _limits().fit(d, limits)


def default_design(name="Robot", colour=(200, 120, 40), weapon="wedge"):
    return {"name": name, "colour": list(colour), "weapon": weapon,
            "points": {"speed": 25, "attack": 25, "armour": 25, "control": 25},
            "settings": {k: v[2] for k, v in SETTINGS.items()}}


def check_design(d, limits=None):
    """Return a list of problems (empty = fine). Used by the server and shown to learners.
    limits: the ranges to hold it to (the learners' ranges the teacher has set, or full_limits() for the teacher's
    own robot); left out, the ranges are the standard ones (default_limits)."""
    problems = _limits().problems(d, limits)
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
    grip, mass = 1.2 + 0.035 * p["control"], (22 + 0.3 * p["armour"]) * size ** 2
    # weight (CHANGE 114): a heavy robot is slower to get going and a little slower flat out. 1.0 for the standard
    # robot (30 kg); half the mass gives 1.41, double gives 0.71 (the square root, so size doesn't swamp it)
    weight = (STANDARD_MASS / mass) ** 0.5
    top_speed = (3 + 0.2 * p["speed"]) * (0.5 + 0.5 * weight)   # m/s: 4 (5 points) to 13 (50 points), standard weight
    accel = (1.5 + 0.12 * p["speed"]) * (0.3 + 0.7 * s["acceleration"] / 100) * weight
    return {
        "push": mass * accel,                               # newtons: how hard it pushes another robot (see PUSH_GRIP)
        "hold": PUSH_GRIP * grip * mass * 9.81,             # newtons: the push it takes to slide it along
        "size": size,
        "forward_max": top_speed * s["forward_speed"] / 100,
        "reverse_max": top_speed * s["reverse_speed"] / 100,
        "accel": accel,                                     # m/s per second (scaled down by weight: CHANGE 114)
        "weight": weight,                                   # 1.0 standard; lighter > 1, heavier < 1
        "turn_rate": math.radians((60 + 4 * p["control"]) * s["turn_speed"] / 100) / max(size, 0.5),
        "grip": 1.2 + 0.035 * p["control"],
        "self_right": 4.0 - 0.06 * p["control"],            # seconds upside down before self-righting
        "armour": (50 + 4 * p["armour"]) * size ** 2,       # hit points
        "mass": (22 + 0.3 * p["armour"]) * size ** 2,        # kg
        "power": 0.6 + 0.02 * p["attack"],                  # weapon strength, 1.1 at 25 points
        "flip_strength": p["attack"] / STAT_MAX,             # a flipper at 100% (50 attack points) can flip Resident Robots
    }


# ---------- real damage: every part has its own hit points ----------

PARTS = ("armour", "weapon", "wheel0", "wheel1", "wheel2", "wheel3")  # (the body's hit points are the robot's health)
PART_WORDS = {"body": "Body", "armour": "Armour", "weapon": "Weapon", "wheel0": "Front right wheel",
              "wheel1": "Front left wheel", "wheel2": "Back right wheel", "wheel3": "Back left wheel"}


def part_hit_points(armour):
    """Real damage: each part's hit points, from the robot's armour (its body has the full armour, as always)."""
    return {"armour": 0.5 * armour, "weapon": 0.5 * armour, **{f"wheel{i}": 0.25 * armour for i in range(4)}}


# ---------- user mods: features learners asked for, switched on and off by the teacher ----------
# key: (the name in the teacher's Controls, what it does). Every user mod is OFF unless the teacher switches it on,
# and the game works exactly as before while it's off. The physics reads arena.user_mods; the graphics get the same
# switches (ArenaVisual(..., user_mods)). The teacher can switch one mid-round: the arena and windows follow at once.
# A learner's AI request can be made as a new user mod (AI cards: "Make it a switchable User Mod").
# No names here: who made each mod is kept with the class's own data (ai_pipeline.user_mod_makers), never in the
# code, and the windows put it in front of the name ("Sam's Spike pit": see user_mod_title).
USER_MODS = {
    "no_cage": ("No cage", "No walls round the arena: a drop into a gutter all the way round (the wall spikes rest)"),
    "hammer_slam": ("Hammer jump slam", "A hammer robot jumps and slams down: the robot it hits goes flying and takes fall damage"),
    "spike_pit": ("Spike pit", "A square pit of spikes in the floor: a robot pushed in is stuck there and its armour drains away"),
    "flame_pit": ("Flame pit", "A pit of flames in the middle of the arena: the flames rise while a robot is in it, and after 3 seconds in the pit the robot is deactivated"),
    "double_flipper": ("Flipper on both ends", "A flipper robot has a second flipper on its back end: both lift when it fires"),
    "boost_pad": ("3 second boost", "A boost button on the floor by the east wall: the robot that touches it is faster for 3 seconds, then the button rests for 5 seconds"),
    "laser_beam": ("Laser beam", "Fire also shoots a laser beam from the front of a robot: the first robot in the beam is pushed away (power 50)"),
}
LASER_POWER = 50      # laser beam: how hard it pushes, on the same scale as attack points (5 is weak, 50 the most)
LASER_PUSH = 0.1      # ...the speed it gives the robot it hits for each point of power (m/s): 5 m/s at power 50
LASER_RANGE = 12.0    # ...how far the beam reaches (metres)
LASER_EVERY = 1.0     # ...the seconds between shots while fire is held
LASER_SECONDS = 0.25  # ...and how long each shot's beam shows
BOOST_SECONDS = 3.0  # boost button: how long the robot that touches it is boosted...
BOOST_REST = 5.0     # ...how long after a touch the button doesn't work (so a robot chasing it can't boost too)...
BOOST_SPEED = 1.5    # ...and a boosted robot's top speed (forwards and backwards) is this many times its own...
BOOST_ACCEL = 2.0    # ...and its motors' push this many times
SLAM_JUMP = 1.0     # hammer jump slam: how high the hammer robot jumps (metres)
SLAM_DROP = 3.0     # ...how fast it throws itself back down from the top (m/s)
SLAM_LAUNCH = 4.0   # ...the speed the robot it hits flies off at (m/s), before the attack points add more
SLAM_FALL = 2.5     # ...fall damage for each m/s of landing speed (never more than SLAM_FALL_MAX)
SLAM_FALL_MAX = 20.0
SPIKE_PIT_DAMAGE = 8.0  # spike pit: the damage a robot in the pit takes each time the spikes bite...
SPIKE_PIT_EVERY = 1.0   # ...and the seconds between bites
FLAME_PIT_SECONDS = 3.0  # flame pit: a robot that has been in the pit this long is deactivated
FLAME_PIT_RISE = 3.0     # ...by then the flames have climbed to this many times their baseline height
FLAME_PIT_CM = 40        # ...the baseline: how high the flames stand above the floor with nobody in (cm).
FLAME_PIT_CM_MIN, FLAME_PIT_CM_MAX = 10, 100  # The teacher sets it in Controls, between these


def user_mods_on(values):
    """Every user mod's switch (off unless switched on)."""
    values = values or {}
    return {k: bool(values.get(k)) for k in USER_MODS}


def user_mod_title(key, makers=None):
    """A user mod's name as everyone sees it, with its maker's name in front if it's known: "Sam's Spike pit"."""
    maker = (makers or {}).get(key)
    return f"{maker}'s {USER_MODS[key][0]}" if maker else USER_MODS[key][0]


# ---------- Resident Robots: heavy, slow, and they guard the corners ----------

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
CPZ = 4.8  # corner patrol zone: how far each Resident Robot's square reaches from its corner (room to drive right in)
# a Resident Robot driven by a player (the teacher can allow it in the garage): heavy, but it can be knocked out
PLAYABLE_HOUSE_STATS = dict(HOUSE_STATS, armour=400.0, forward_max=3.6, reverse_max=2.6, power=1.5)


# ---------- the robot as variables (the engine's schema: the code panel and the garage's tables) ----------
CODE_NOTES = {  # the comment on each setting's line of the robot's code (CHANGE 49)
    "forward_speed": "% of top speed, forwards", "reverse_speed": "% of top speed, in reverse",
    "turn_speed": "% of the fastest turn", "acceleration": "% of hardest acceleration",
    "size": "% of the standard size"}


def _model_changed(d, ctx):
    """A Resident Robot's weapon is its own; back to a learner's design, the weapon must be a learner's."""
    if d.get("model"):
        d["weapon"] = ctx.house.get(d["model"], d.get("weapon"))
    elif d.get("weapon") not in ctx.all_weapons:
        d["weapon"] = "wedge"


def _weapon_changed(d, ctx):
    if d.get("model"):  # (driving a Resident Robot: its weapon stays)
        d["weapon"] = ctx.house.get(d["model"], d["weapon"])


def _weapon_text(ctx, d):
    """Under the weapon row: what it does (a Resident Robot's, with its fixed stats)."""
    if d.get("model"):
        return (ctx.rules["house_weapons"].get(d["weapon"], d["weapon"]) + "\nResident Robots are heavy (190 kg), "
                "with armour 400 and big wheels. Their stats are fixed, so points and settings aren't used.")
    return ctx.rules["weapons"].get(d["weapon"], "")


def schema():
    """The robot's variables, in the HUD's groups. ctx (from the window): title, points_total, weapons (allowed
    this mission), all_weapons, house (Resident Robot -> its weapon), rules."""
    from engine.schema import Var
    driving = lambda d: bool(d.get("model"))  # noqa: E731  (a Resident Robot: its stats are its own)
    return ([Var(k, ("settings", k), "int", "settings", tool=k, note=CODE_NOTES[k], unless=driving) for k in SETTINGS] +
            [Var(f"{k}_points", ("points", k), "int", "points", tool="points_table", note=f"points for {k}",
                 unless=driving) for k in STATS] +
            [Var("robot_name", ("name",), "str", "strings", tool="name_and_colour", note="a string: text made of chars"),
             Var("weapon", ("weapon",), "choice", "lists", tool="choose_weapon", options=lambda ctx: ctx.weapons,
                 valid=lambda ctx: ctx.all_weapons, list_name="weapons", list_note="the weapons allowed this mission",
                 after=_weapon_changed, fixed=driving, describe=_weapon_text, always=True,
                 allowed_values=lambda tools: tools.get("weapons", [])),
             Var("model", ("model",), "choice", "strings", tool="house_robots", note="driving a Resident Robot",
                 optional=True, options=lambda ctx: list(ctx.house), after=_model_changed, none_text="My design",
                 per_row=5, step=0.13),
             Var("colour", ("colour",), "rgb", "lists", tool="name_and_colour", note="red, green, blue: 0 to 255")])


def house_list(value):
    """The Resident Robots switched on: True = all four, False = none, or a list of names."""
    if value is True:
        return [n for n, *_ in HOUSE_ROBOTS]
    if not value:
        return []
    return [n for n, *_ in HOUSE_ROBOTS if n in value]


def design_size(d):
    """How big a design's robot is (Resident Robot models are always Resident Robot size)."""
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


def shapes(weapon, size, big=False):
    """Sizes and pivot points for a robot at a given size (so physics and graphics always match).
    The shapes were made for the standard sizes, 80% to 120%. A robot outside them is the nearest standard robot
    made bigger or smaller all over, wheels and weapon too: "k" in the result says how many times (1 for a
    standard size). big: a Resident Robot, which has its own build."""
    ref = size if big else max(STANDARD_SIZES[0], min(STANDARD_SIZES[1], size))
    k = size / ref
    sh = standard_shapes(weapon, ref)
    if k != 1.0:
        for key, v in sh.items():
            if key != "axis":
                sh[key] = tuple(x * k for x in v) if isinstance(v, tuple) else v * k
    sh["k"] = k
    return sh


STANDARD_SIZES = (0.8, 1.2)


def standard_shapes(weapon, size):
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
    """Resident Robot: wait in your corner; attack anyone who comes into your zone; never chase far."""
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
        # (a disc is switched on as soon as someone is in the zone, so it has spun up when it gets there)
        return throttle, steer, me.weapon in TOGGLE_WEAPONS or (dist < reach and abs(angle) < 30)
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
        self.house = house                              # a computer-driven Resident Robot guarding a corner
        self.model = design.get("model") if design.get("model") in HOUSE_BY_NAME else None  # a player's Resident Robot
        self.big = house or self.model is not None
        self.name = str(design["name"])[:20]
        self.colour = tuple(v / 255 for v in design["colour"])
        self.weapon = HOUSE_BY_NAME[self.model][0] if self.model else design["weapon"]
        if stats is None and self.model:
            stats = PLAYABLE_HOUSE_STATS
        self.stats = dict(stats) if stats else build_stats(design)
        self.shape = shapes(self.weapon, self.stats["size"], self.big)
        k = self.k = self.shape["k"]  # (1 for a standard size: see shapes. Everything below is made k times bigger)
        self.motor = k ** 3           # ...and the weapon's motor k^3 times stronger (as its weight on the floor is:
        #                               any stronger and a big hammer's swing would throw its own robot over)
        self.swing_rate = 1 / math.sqrt(k)  # ...and a flipper or hammer swings slower the bigger it is (faster, smaller)
        self.health = self.stats["armour"]
        self.control = (0.0, 0.0, False)
        self.weapon_on = False  # (a weapon that toggles: see TOGGLE_WEAPONS. Every robot starts with it off)
        self.damage_dealt = self.damage_taken = 0.0
        self.hits = 0
        self.knocked_out = False
        self.upside_down_since = None
        self.fire_until = -10.0
        self.throttle = 0.0        # what its driver is asking of the motors now (-1 to 1)
        self.pushed_until = -10.0  # another robot is driving into it until this time (see PUSH_GRIP)
        self.grip_now = None       # the grip its wheels have at the moment
        self.rear_np = self.rear_hinge = None  # the Flipper on both ends user mod: a second plate, on the back end
        self.boost_until = -10.0   # the boost button user mod: boosted until this time
        self.laser_at = -10.0      # the laser beam user mod: when it last fired its laser
        self.launched = set()  # robots already launched by the current flip
        self.start = (pos, heading)
        self.corner = None
        self.swing = 0.0
        self.fires = 0
        self.coast_until = 0.0  # a flipper's plate swings freely for a moment after a flip
        self.jump_at = None     # hammer jump slam (user mod): when the jump started (None = not jumping)
        self.slam_until = -10.0  # ...the hammer is slamming down until this time
        self.drop = 0.0         # ...how fast the robot is falling (m/s)
        self.part_max = part_hit_points(self.stats["armour"])  # real damage: each part's hit points
        self.part_hp = dict(self.part_max)
        self.lost = set()       # parts that have come off
        self.wheel_r = (HOUSE_WHEEL_R if self.big else WHEEL_R) * k
        world, root, sh = arena.world, arena.root, self.shape

        body = BulletRigidBodyNode(f"chassis{rid}")
        body.addShape(BulletBoxShape(sh["half"]), TransformState.makePos(Point3(0, 0, CHASSIS_Z * k)))
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
            w.setMaxSuspensionTravelCm(8 * k)
            w.setSuspensionStiffness(40 / k)  # (so a small robot sinks less on its springs, a big one more)
            w.setWheelsDampingRelaxation(2.3 / math.sqrt(k))
            w.setWheelsDampingCompression(4.4 / math.sqrt(k))
            w.setFrictionSlip(self.stats["grip"])
            w.setRollInfluence(0.02)
            w.setMaxSuspensionForce(20000 * k * k)

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
        self.weapon_mass = wb.getMass() * k * k  # (lighter or heavier with the robot: its mass goes with size squared)
        wb.setMass(self.weapon_mass)
        wb.setDeactivationEnabled(False)
        wb.setCcdMotionThreshold(0.05 * min(1.0, k))
        wb.setCcdSweptSphereRadius(0.06 * min(1.0, k))
        self.weapon_np = root.attachNewNode(wb)
        self.weapon_np.setPos(self.np, sh["pivot"])
        self.weapon_np.setHpr(self.np, 0, 0, 0)
        world.attachRigidBody(wb)
        self.hinge = BulletHingeConstraint(body, wb, sh["pivot"], Point3(0, 0, 0), sh["axis"], sh["axis"], True)
        if self.weapon == "wedge":
            self.hinge.setLimit(self.wedge_rest_angle(), 55)
        elif self.weapon == "hammer":
            self.hinge.setLimit(-5, 115 if self.big or k > 1 else 150)  # (a long hammer doesn't lie as far back)
        elif self.weapon == "chainsaw":
            self.hinge.setLimit(-32, 45)
        elif self.weapon == "flame":
            self.hinge.setLimit(-1, 1)
        world.attachConstraint(self.hinge, True)  # True: a robot can't hit its own weapon
        self.park_weapon()
        self.parts = {body.getName(): "chassis", wb.getName(): "weapon"}
        if arena.user_mods["double_flipper"]:
            self.set_rear_flipper(True)

    def set_rear_flipper(self, on):
        """The Flipper on both ends user mod: a flipper robot gets (or loses) a second plate, hinged on its back
        end. It is the front plate pointing the other way (so its hinge turns the other way to lift), and it
        lifts with the front one. It counts as part of the robot's weapon."""
        world = self.arena.world
        if self.rear_np is not None:
            name = self.rear_np.node().getName()
            world.removeConstraint(self.rear_hinge)
            world.removeRigidBody(self.rear_np.node())
            self.rear_np.removeNode()
            self.rear_np = self.rear_hinge = None
            self.parts.pop(name, None)
            self.arena.owner.pop(name, None)
        if not on or self.weapon != "wedge" or self.big or "weapon" in self.lost:
            return
        sh, k = self.shape, self.k
        wb = BulletRigidBodyNode(f"rear{self.id}")
        wb.addShape(BulletBoxShape(sh["plate"]), TransformState.makePos(Point3(0, -sh["plate"].y, 0)))
        wb.setMass(4 * k * k)
        wb.setFriction(0.1)
        wb.setDeactivationEnabled(False)
        wb.setCcdMotionThreshold(0.05 * min(1.0, k))
        wb.setCcdSweptSphereRadius(0.06 * min(1.0, k))
        pivot = Point3(0, -sh["pivot"].y, sh["pivot"].z)
        self.rear_np = self.arena.root.attachNewNode(wb)
        self.rear_np.setPos(self.np, pivot)
        self.rear_np.setHpr(self.np, 0, 0, 0)
        world.attachRigidBody(wb)
        self.rear_hinge = BulletHingeConstraint(self.np.node(), wb, pivot, Point3(0, 0, 0), sh["axis"], sh["axis"], True)
        self.rear_hinge.setLimit(-55, -self.wedge_rest_angle())
        world.attachConstraint(self.rear_hinge, True)
        self.parts[wb.getName()] = "weapon"
        self.arena.owner[wb.getName()] = self

    def park_weapon(self):
        """The weapon on its mount, as it rests. (A robot bigger than the standard sizes has its hammer laid back
        against its stop: swinging back to it from the front would throw the robot over.)"""
        self.weapon_np.setPos(self.np, self.shape["pivot"])
        self.weapon_np.setHpr(self.np, 0, 115 if self.weapon == "hammer" and self.k > 1 else 0, 0)
        if self.rear_np is not None:
            self.rear_np.node().setLinearVelocity(self.np.node().getLinearVelocity())
            self.rear_np.node().setAngularVelocity(Vec3(0))
            self.rear_np.setPos(self.np, Point3(0, -self.shape["pivot"].y, self.shape["pivot"].z))
            self.rear_np.setHpr(self.np, 0, 0, 0)

    def wedge_rest_angle(self):
        """Angle that puts the wedge's front lip about 2 cm above the floor."""
        drop = self.shape["pivot"].z + (RIDE - 0.02) * self.k  # pivot height above the floor
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
            inertia = self.weapon_mass * ((2 * b.x) ** 2) / 12
        elif self.weapon == "drum":
            inertia = 0.5 * self.weapon_mass * self.shape["drum"][0] ** 2
        elif self.weapon == "vdisc":
            inertia = 0.5 * self.weapon_mass * self.shape["disc"][0] ** 2
        else:
            return 0.0
        return 0.5 * inertia * self.weapon_spin() ** 2

    def flaming(self, now):
        return (self.weapon == "flame" and not self.knocked_out and now < self.fire_until
                and "weapon" not in self.lost)

    def drive(self, throttle, steer, fire, may_switch=True):
        """A player's controls. Fire (Space) is the one weapon key: each press switches a weapon that toggles on
        or off (may_switch: the teacher allows it), and the other weapons fire while it is held (see tick)."""
        if fire and not self.control[2] and may_switch and self.weapon in TOGGLE_WEAPONS and not self.arena.frozen:
            self.weapon_on = not self.weapon_on
        self.control = (throttle, steer, fire)

    def nozzle(self):
        """Where the flame comes out, and which way it points."""
        tip = self.weapon_np.getPos() + self.np.getQuat().getForward() * self.shape["nozzle"].y * 2
        return tip, self.np.getQuat().getForward()

    # ---------- every tick ----------
    def tick(self, enemies, now):
        if self.knocked_out or self.arena.frozen:  # (frozen: the countdown before a battle. Nobody moves or fires)
            throttle, steer, attack = 0.0, 0.0, False
            if self.arena.frozen:
                self.weapon_on = False
        elif self.brain:
            throttle, steer, attack = self.brain(self, enemies, self.arena)
            if self.weapon in TOGGLE_WEAPONS:  # a brain's attack is the switch: on while it says True
                self.weapon_on = bool(attack)
        else:
            throttle, steer, attack = self.control
        st = self.stats
        self.throttle = throttle
        grip = st["grip"] * (PUSH_GRIP if now < self.pushed_until else 1.0)  # being pushed: its tyres slide
        if grip != self.grip_now:
            self.grip_now = grip
            for i in range(4):
                if f"wheel{i}" not in self.lost:
                    self.vehicle.getWheel(i).setFrictionSlip(grip)
        # speed limits from the forward/reverse settings (the boost button user mod raises them for a few seconds)
        v = self.speed
        boost = now < self.boost_until
        faster = BOOST_SPEED if boost else 1.0
        if (throttle > 0 and v > st["forward_max"] * faster) or (throttle < 0 and -v > st["reverse_max"] * faster):
            throttle = 0.0
        # turning: skid steering, capped by the turn speed setting
        yaw_rate = self.np.node().getAngularVelocity().z
        # motors: acceleration sets how hard the wheels push (force = mass x acceleration, over 4 wheels)
        body = self.np.node()
        force = body.getMass() * st["accel"] / 4 * (1.6 if throttle * v < 0 else 1.0)  # braking bites harder
        force *= BOOST_ACCEL if boost else 1.0
        for i, (x, _) in enumerate(WHEELS):
            wheel = self.condition(f"wheel{i}")  # real damage: a damaged wheel pushes less, a lost one not at all
            self.vehicle.applyEngineForce(force * throttle * (0.5 + 0.5 * wheel if wheel > 0 else 0.0), i)
            brake = (3.0 if not self.big else 12.0) * self.k ** 2
            if now < self.pushed_until:  # being pushed: its brakes hold no harder than its sliding tyres (its hold)
                brake = min(brake, grip * body.getMass() * 9.81 / 4 * SUBSTEP)
            self.vehicle.setBrake(brake if throttle == 0 and steer == 0 else 0.0, i)
        # turning: steer asks for a turn rate up to the turn speed setting; the motors push towards it
        if self.np.getQuat().getUp().z > 0.5:
            want = steer * st["turn_rate"]
            inertia = body.getMass() * ((2 * self.shape["half"].x) ** 2 + (2 * self.shape["half"].y) ** 2) / 12
            body.applyTorque(Vec3(0, 0, inertia * 40 * (want - yaw_rate)))

        # laser beam (user mod): fire also shoots the laser, once every LASER_EVERY seconds (see Arena.laser_shots).
        # Resident Robots don't have one
        if attack and self.arena.user_mods["laser_beam"] and not self.house and now >= self.laser_at + LASER_EVERY:
            self.laser_at = now

        if "weapon" in self.lost:  # it has come off: nothing to drive
            return
        on = (self.weapon_on or self.weapon not in TOGGLE_WEAPONS) and not self.knocked_out
        power = st["power"] * (0.7 + 0.3 * self.condition("weapon"))  # a damaged weapon is weaker
        was_firing = now < self.fire_until
        m = self.motor  # (1 on a standard robot)
        if self.weapon == "spinner":
            self.hinge.enableAngularMotor(True, 32 * power if on else 0.0, (5.0 * power if on else 1.5) * m)
        elif self.weapon == "drum":
            self.hinge.enableAngularMotor(True, -45 * power if on else 0.0, (6.0 * power if on else 1.5) * m)
        elif self.weapon == "vdisc":
            self.hinge.enableAngularMotor(True, -38 * power if on else 0.0, (14.0 * power if on else 3.0) * m)
        elif self.weapon == "flame":
            self.hinge.enableAngularMotor(True, 0.0, 200.0 * m)
            if attack and on and now >= self.fire_until + 0.7:
                self.fire_until = now + 1.4  # a burst of flame
        elif self.weapon == "chainsaw":
            if attack and on:
                self.fire_until = now + 0.6  # keeps sawing while there's something to saw
            if now < self.fire_until:
                self.hinge.enableAngularMotor(True, -1.0, 1500.0 * power * m)
            else:
                self.hinge.enableAngularMotor(True, 1.3, 1500.0 * power * m)
        elif self.weapon == "wedge":
            if attack and on and now >= self.fire_until + 0.9:
                self.fire_until = now + 0.3
                self.launched = set()
            if now < self.fire_until:  # the plate lifts itself; a robot on it is launched in weapon_contact
                motor = (True, 14.0 * self.swing_rate, 30.0 * m)   # (gentle, so a robot sitting on it can't lever us over)
            elif now < self.coast_until:
                motor = (False, 0.0, 0.0)
            else:
                motor = (True, -4.0 * self.swing_rate, 80.0 * m)
            self.hinge.enableAngularMotor(*motor)
            if self.rear_hinge is not None:  # (Flipper on both ends: the back plate does as the front one does)
                self.rear_hinge.enableAngularMotor(motor[0], -motor[1], motor[2])
        else:
            if attack and on and now >= self.fire_until + (1.4 if self.big else 0.9) and self.jump_at is None:
                if self.arena.user_mods["hammer_slam"] and not self.big and self.on_floor():
                    self.jump_at = now  # hammer jump slam: jump first, the hammer swings at the top
                    self.lift(math.sqrt(2 * RULES["gravity"] * SLAM_JUMP))
                else:
                    self.fire_until = now + 0.35
            if self.jump_at is not None or now < self.slam_until:
                self.slam_tick(on, now)
            if self.big:  # a big heavy hammer: a slower swing, so it doesn't throw its own robot about
                speed, strength, back = -9.0, 1400.0, (2.5, 500.0)
            else:
                speed, strength, back = -18.0 * min(power, 1.3), 300.0 * power, (6.0, 80.0)
            if now < self.fire_until:
                self.hinge.enableAngularMotor(True, speed * self.swing_rate, strength * m)
            else:
                self.hinge.enableAngularMotor(True, back[0] * self.swing_rate, back[1] * m)
        if now < self.fire_until and not was_firing:
            self.fires += 1  # (the windows play the weapon's firing sound when this goes up)

    # ---------- hammer jump slam (user mod) ----------
    def on_floor(self):
        """Is the robot the right way up on the floor (so it can jump)?"""
        return (self.np.getQuat().getUp().z > 0.8 and self.pos.z < 0.5
                and abs(self.np.node().getLinearVelocity().z) < 1.0)

    def lift(self, speed):
        """Add this much upward speed (m/s) to the robot and its weapon (negative = downwards)."""
        for np_ in (self.np, self.weapon_np) + ((self.rear_np,) if self.rear_np is not None else ()):
            np_.node().setLinearVelocity(np_.node().getLinearVelocity() + Vec3(0, 0, speed))

    def slam_tick(self, on, now):
        """In the air: at the top of the jump the hammer swings and the robot throws itself back down."""
        body = self.np.node()
        if self.jump_at is not None and (body.getLinearVelocity().z < 0.5 or now > self.jump_at + 1.5):
            self.jump_at = None
            if on:
                self.fire_until = self.slam_until = now + 0.45
                self.lift(-SLAM_DROP)
        body.setAngularVelocity(Vec3(0, 0, body.getAngularVelocity().z))  # stay level: the swing can't tip it over
        self.drop = max(0.0, -body.getLinearVelocity().z)

    def reset(self, keep_health=False):
        pos, heading = self.start
        self.jump_at, self.slam_until, self.boost_until = None, -10.0, -10.0
        self.laser_at = -10.0
        for np_ in (self.np, self.weapon_np):
            np_.node().setLinearVelocity(Vec3(0))
            np_.node().setAngularVelocity(Vec3(0))
        self.np.setPos(pos)
        self.np.setHpr(heading, 0, 0)
        if keep_health and "weapon" in self.lost:  # (a weapon that came off stays where it is)
            self.upside_down_since = None
            return
        self.park_weapon()
        self.upside_down_since = None
        if not keep_health:
            self.repair()
            self.health = self.stats["armour"]
            self.knocked_out = False
            self.damage_dealt = self.damage_taken = 0.0
            self.hits = 0
            self.weapon_on = False

    def repair(self):
        """Every part back on and like new (a new round)."""
        lost_weapon = "weapon" in self.lost
        if lost_weapon:  # the weapon goes back on its hinge (reset has put it in place)
            self.arena.world.attachConstraint(self.hinge, True)
            self.parts[self.weapon_np.node().getName()] = "weapon"
        for i in range(4):
            self.wheel_on(i, True)
        self.lost = set()
        self.part_hp = dict(self.part_max)
        if lost_weapon and self.arena.user_mods["double_flipper"]:  # (its back flipper went with its weapon)
            self.set_rear_flipper(True)

    def wheel_on(self, i, on):
        """A wheel on (it holds the robot up and grips) or off (that corner drops and drags on the floor)."""
        w = self.vehicle.getWheel(i)
        w.setMaxSuspensionForce(20000 * self.k ** 2 if on else 0.0)
        w.setFrictionSlip(self.stats["grip"] if on else 0.0)
        self.grip_now = None  # (tick sets the grip again)

    def driving_into(self, other):
        """Is this robot's driver pushing it towards the other robot (forwards at one in front of it, or backwards
        at one behind)? A robot beside it, pushing the same way, doesn't count."""
        to = Vec3(other.pos.x - self.pos.x, other.pos.y - self.pos.y, 0)
        if self.knocked_out or not self.throttle or not to.normalize():
            return False
        return self.forward.dot(to) * (1 if self.throttle > 0 else -1) > 0.5

    def remove(self):
        w = self.arena.world
        self.set_rear_flipper(False)
        if "weapon" not in self.lost:
            w.removeConstraint(self.hinge)
        w.removeVehicle(self.vehicle)  # this also takes the chassis body out of the world
        w.removeRigidBody(self.weapon_np.node())
        self.np.removeNode()
        self.weapon_np.removeNode()


# ---------- the arena floor: holes for the pit and the floor flipper ----------

def floor_holes(hazards=None, user_mods=None):
    """Rectangles (x0, y0, x1, y1) cut out of the floor: the drop zone and the floor flipper are always there
    (switched off, the drop zone's floor is up and the flipper lies flat, both flush with the floor). The Spike pit
    and Flame pit user mods each cut one more."""
    px, py, ps = Arena.PIT
    fx, fy = Arena.FLOOR_FLIPPER
    holes = [(px - ps / 2, py - ps / 2, px + ps / 2, py + ps / 2), (fx - 1.5, fy - 1.0, fx + 1.5, fy + 1.0)]
    mods = user_mods_on(user_mods)
    for key, (kx, ky, ks) in (("spike_pit", Arena.SPIKE_PIT), ("flame_pit", Arena.FLAME_PIT)):
        if mods[key]:
            holes.append((kx - ks / 2, ky - ks / 2, kx + ks / 2, ky + ks / 2))
    return holes


def floor_rects(hazards=None, user_mods=None):
    """The floor as rectangles (x0, y0, x1, y1), with the holes cut out. Physics and graphics share this."""
    h = ARENA / 2
    rects = [(-h, -h, h, h)]
    for hx0, hy0, hx1, hy1 in floor_holes(hazards, user_mods):
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
    GUTTER = 3.0                                 # width of the drop all around the arena edge
    SPIKE_PIT = (-3.5, 7.0, 2.4)                # the spike pit (user mod): centre x, y and size
    SPIKE_PIT_DEPTH = 0.5                        # ...and how deep it is (as deep as the floor is thick)
    FLAME_PIT = (0.0, 0.0, 2.4)                 # the flame pit (user mod): centre x, y and size
    FLAME_PIT_DEPTH = 0.5                        # ...and how deep it is
    BOOST_PAD = (9.0, -3.0, 1.6)                # the boost button (user mod): centre x, y and size (on the floor by
    #                                             the east wall, so it is still there with the No cage user mod)
    STARTS = ((-7.5, 0, -90), (7.5, 0, 90), (-3.5, -7.5, 0), (0, -7.5, 0), (3.5, 7.5, 180), (0, 7.5, 180))

    def __init__(self, root=None, hazards=None, seed=1, user_mods=None):
        self.world = BulletWorld()
        self.user_mods = user_mods_on(user_mods)  # the teacher's user mods (see USER_MODS)
        self.edge, self.spikes_in = [], True
        self.floor = []
        self.world.setGravity(Vec3(0, 0, -RULES["gravity"]))
        self.root = root if root is not None else NodePath("arena")
        self.rnd = random.Random(seed)
        self.hazards = {**dict(pit=True, floor_flipper=True, saws=True, spikes=True, house_robots=False),
                        **(hazards or {})}
        self.frozen = False    # the countdown before a battle: robots can't drive or fire until it ends
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
        self.flying = {}    # hammer jump slam (user mod): robot sent flying -> [who slammed it, when, fastest fall]
        self.flame_pit_cm = FLAME_PIT_CM  # flame pit (user mod): the baseline flame height the teacher set (cm)
        self.flame_height = 0.0           # ...how high the flames stand above the floor right now (metres)
        self.flame_pit_since = {}         # ...robot in the pit -> when it went in
        self.boost_ready_at = 0.0         # boost button (user mod): it works again from this time
        self.lasers = []                  # laser beam (user mod): the beams showing now, each (start, end)
        self.saw_height = [0.0 for _ in self.SAWS]
        self.saw_hot_until = [0.0 for _ in self.SAWS]
        self.spike_out = 0.0
        self.pit_z = self.PIT_OPEN_Z if self.pit_open else self.PIT_CLOSED_Z
        self.bodies, self.constraints = [], []  # everything build() made
        self.index = 0         # which arena this is, when there are several (Arenas)
        self.id_source = None  # where a new robot's id comes from when there are several arenas (unique across them)
        self.build()
        self.set_house_robots(self.hazards.get("house_robots"))

    def new_id(self):
        if self.id_source is not None:
            return self.id_source()
        return max([r.id for r in self.robots], default=-1) + 1

    def set_hazards(self, hazards):
        """Switch hazards on or off mid-round. Nothing disappears: a hazard that is off just rests (saws down,
        spikes in, flipper flat, drop zone floor up and flush), and the robots carry on where they are."""
        self.hazards = {**self.hazards, **hazards}
        self.pit_open = bool(self.hazards["pit"])
        self.set_house_robots(self.hazards.get("house_robots"))

    def set_user_mods(self, values):
        """Switch user mods on or off mid-round (the robots carry on where they are)."""
        before = dict(self.user_mods)
        in_pit = {"spike_pit": [r for r in self.robots if self.in_spike_pit(r)],
                  "flame_pit": [r for r in self.robots if self.in_flame_pit(r)]}
        self.user_mods = user_mods_on({**self.user_mods, **(values or {})})
        if self.user_mods["no_cage"] != before["no_cage"]:
            self.build_edge()
        if self.user_mods["double_flipper"] != before["double_flipper"]:
            for r in self.robots:
                r.set_rear_flipper(self.user_mods["double_flipper"])
        if self.user_mods["boost_pad"] != before["boost_pad"]:
            self.boost_ready_at = 0.0
            for r in self.robots:
                r.boost_until = -10.0
        if self.user_mods["laser_beam"] != before["laser_beam"]:
            self.lasers = []
            for r in self.robots:
                r.laser_at = -10.0
        switched = [k for k in in_pit if self.user_mods[k] != before[k]]
        if "flame_pit" in switched:  # (switched on, the flames start from nothing and rise to their baseline)
            self.flame_height = 0.0
            self.flame_pit_since.clear()
        if switched:
            for r in (r for k in switched for r in in_pit[k]):  # the floor is about to close over the pit:
                lift = 0.6 - r.pos.z                            # lift anyone in it clear
                r.np.setZ(r.np.getZ() + lift)
                if "weapon" not in r.lost:
                    r.weapon_np.setZ(r.weapon_np.getZ() + lift)
            self.build_floor()

    def set_house_robots(self, value):
        """Add or remove Resident Robots one by one (True = all, False = none, or a list of names)."""
        wanted = house_list(value)
        for r in [r for r in self.robots if r.house and r.name not in wanted]:
            self.remove_robot(r)
        have = {r.name for r in self.robots if r.house}
        self.add_house_robots([n for n in wanted if n not in have])

    def build(self):
        h = ARENA / 2
        self.build_floor()

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
        self.build_edge()

    def build_floor(self):
        """The floor, with its holes. Built again when the Spike pit user mod is switched: the mod cuts a square
        hole with a bed of spikes at the bottom (the floor around it makes the pit's sides). The Flame pit user mod
        does the same in the middle of the arena."""
        for np_ in self.floor:
            self.world.removeRigidBody(np_.node())
            self.bodies.remove(np_)
            np_.removeNode()
        first = len(self.bodies)
        for i, (x0, y0, x1, y1) in enumerate(floor_rects(self.hazards, self.user_mods)):
            self.add_static(f"floor{i}", Vec3((x1 - x0) / 2, (y1 - y0) / 2, 0.25), Point3((x0 + x1) / 2, (y0 + y1) / 2, -0.25))
        if self.user_mods["spike_pit"]:
            kx, ky, ks = self.SPIKE_PIT
            self.add_static("spike_pit_floor", Vec3(ks / 2, ks / 2, 0.25), Point3(kx, ky, -self.SPIKE_PIT_DEPTH - 0.25))
        if self.user_mods["flame_pit"]:
            kx, ky, ks = self.FLAME_PIT
            self.add_static("flame_pit_floor", Vec3(ks / 2, ks / 2, 0.25), Point3(kx, ky, -self.FLAME_PIT_DEPTH - 0.25))
        self.floor = self.bodies[first:]

    def in_spike_pit(self, r):
        """Spike pit (user mod): is this robot down in the pit?"""
        kx, ky, ks = self.SPIKE_PIT
        p = r.pos
        return self.user_mods["spike_pit"] and abs(p.x - kx) < ks / 2 and abs(p.y - ky) < ks / 2 and p.z < -0.1

    def in_flame_pit(self, r):
        """Flame pit (user mod): is this robot down in the pit?"""
        kx, ky, ks = self.FLAME_PIT
        p = r.pos
        return self.user_mods["flame_pit"] and abs(p.x - kx) < ks / 2 and abs(p.y - ky) < ks / 2 and p.z < -0.1

    def build_edge(self):
        """The arena's edge: walls with clear screens above them or, with the No cage user mod, a drop all round
        into a gutter as deep as the pit. Built again when the mod is switched, so it can change mid-round."""
        for np_ in self.edge:
            self.world.removeRigidBody(np_.node())
            self.bodies.remove(np_)
            np_.removeNode()
        h, g = ARENA / 2, self.GUTTER
        first = len(self.bodies)
        if self.user_mods["no_cage"]:
            for i, (cx, cy, hx, hy) in enumerate(((0, h + g / 2, h + g, g / 2), (0, -h - g / 2, h + g, g / 2),
                                                  (h + g / 2, 0, g / 2, h), (-h - g / 2, 0, g / 2, h))):
                self.add_static(f"gutter{i}", Vec3(hx, hy, 0.25), Point3(cx, cy, self.PIT_OPEN_Z - 0.25))
            for i, (cx, cy, hx, hy) in enumerate(((0, h + g + 0.25, h + g + 0.5, 0.25), (0, -h - g - 0.25, h + g + 0.5, 0.25),
                                                  (h + g + 0.25, 0, 0.25, h + g), (-h - g - 0.25, 0, 0.25, h + g))):
                self.add_static(f"outer{i}", Vec3(hx, hy, 1.6), Point3(cx, cy, -1.5))  # the gutter's outer side
            for i, (cx, cy, hx, hy) in enumerate(((0, h + g + 5, h + g + 10, 5), (0, -h - g - 5, h + g + 10, 5),
                                                  (h + g + 5, 0, 5, h + g), (-h - g - 5, 0, 5, h + g))):
                self.add_static(f"outside{i}", Vec3(hx, hy, 0.25), Point3(cx, cy, -0.25))  # the floor beyond it
        else:
            for i, (cx, cy, hx, hy) in enumerate(((0, h + 0.25, h + 0.5, 0.25), (0, -h - 0.25, h + 0.5, 0.25),
                                                  (h + 0.25, 0, 0.25, h), (-h - 0.25, 0, 0.25, h))):
                self.add_static(f"wall{i}", Vec3(hx, hy, 0.6), Point3(cx, cy, 0.6))
                self.add_static(f"screen{i}", Vec3(hx, hy, 3.0), Point3(cx, cy, 4.2))  # clear screens above the walls
        self.edge = self.bodies[first:]
        cage = not self.user_mods["no_cage"]  # the wall spikes live in the wall: with no cage they're taken out
        if cage != self.spikes_in:
            (self.world.attachRigidBody if cage else self.world.removeRigidBody)(self.spikes.node())
            self.spikes_in = cage

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
        r = Robot(self, self.new_id(), design, Point3(x, y, 0.5), heading, brain, owner)
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
            r = Robot(self, self.new_id(), house_design(name, weapon, colour), Point3(x, y, 0.6), heading, house_brain,
                      "Resident Robot", stats=HOUSE_STATS, house=True)
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
        self.flying.clear()
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
        for r in self.robots:  # (see MAX_SPEED)
            for body in (r.np.node(), r.weapon_np.node()) + ((r.rear_np.node(),) if r.rear_np is not None else ()):
                v = body.getLinearVelocity()
                if v.lengthSquared() > MAX_SPEED ** 2:
                    body.setLinearVelocity(v * (MAX_SPEED / v.length()))
        self.contacts(now)
        if self.flying:
            self.fall_damage(now)
        self.flame_hits(now)
        if self.user_mods["spike_pit"]:
            self.spike_pit_hits(now)
        if self.user_mods["flame_pit"]:
            self.flame_pit_burn(now)
        if self.user_mods["boost_pad"]:
            self.boost_pad_touch(now)
        if self.user_mods["laser_beam"]:
            self.laser_shots(now)
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
            target = 1.0 if on["spikes"] and self.spikes_in and now % RULES["spike_cycle"] < 1.2 else 0.0
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
            r.set_rear_flipper(False)  # (a back flipper goes with it)
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
        """Robots banging into each other or into the walls: a sound and a few sparks, no damage.
        And pushing: a robot touched by one that is driving into it is being pushed (see PUSH_GRIP)."""
        a0, a1 = self.owner.get(n0), self.owner.get(n1)
        if a0 is not None and a1 is not None and a0 is not a1 and "loose" not in (a0.parts.get(n0), a1.parts.get(n1)):
            for pusher, pushed in ((a0, a1), (a1, a0)):
                if pusher.driving_into(pushed):
                    pushed.pushed_until = now + 0.15
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
                # (Flipper on both ends: a robot on the back plate is thrown backwards)
                way = -1.0 if a.rear_np is not None and a.np.getRelativePoint(self.root, point).y < 0 else 1.0
                fwd = a.forward * way
                vb.applyImpulse(up * lift + fwd * lift * 0.35, point - v.pos)
                vb.setAngularVelocity(vb.getAngularVelocity() + a.np.getQuat().getRight() * 5.0 * way)
                self.hit(a, v, 3 + 4 * a.stats["power"], now, f"{a.name} FLIPS {v.name}", point, "flip", where)
                self.cooldown[key] = now + 0.5
        elif a.weapon == "hammer":
            if now < a.fire_until:
                head_speed = max(a.swing, a.weapon_np.node().getAngularVelocity().length()) * a.shape["arm"].y * 2
                slam = now < a.slam_until  # hammer jump slam (user mod): the fall adds to the swing
                if slam:
                    head_speed += a.drop
                if head_speed > 4:
                    if slam and not v.big:  # the robot it hits goes flying (and is hurt again when it lands)
                        away = Vec3(v.pos.x - a.pos.x, v.pos.y - a.pos.y, 0)
                        away.normalize()
                        speed = min(RULES["max_launch_speed"], SLAM_LAUNCH + 2.0 * a.stats["power"])
                        vb.applyCentralImpulse((away * 0.6 + up * 0.8) * speed * vb.getMass())
                        self.flying[v] = [a, now, 0.0]
                        a.fire_until = a.slam_until = now  # the hammer lifts out of the way
                    else:
                        vb.applyImpulse(-up * vb.getMass() * 2.0, point - v.pos)
                    damage = min(35.0, head_speed * 2.2 * a.stats["power"])
                    if a.big:
                        damage = min(30.0, damage) * (RULES["hazard_damage"] if a.house else 1.0)
                    self.hit(a, v, damage, now, f"{a.name} HAMMERS {v.name}", point, "hammer", where)
                    self.cooldown[key] = now + 0.6
        elif a.weapon == "chainsaw":
            if now < a.fire_until:  # the chain drags the victim forwards and down
                fwd = a.forward
                vb.applyImpulse((fwd * 1.6 - up * 0.8) * vb.getMass(), point - v.pos)
                self.hit(a, v, 4.0 * RULES["hazard_damage"], now, f"{a.name} SAWS INTO {v.name}", point, "saw", where)
                self.streams.append(((point.x, point.y, point.z), tuple(fwd * 0.6 + up * 0.8), 10))
                self.cooldown[key] = now + 0.25

    def fall_damage(self, now):
        """Hammer jump slam (user mod): a robot sent flying by a slam is hurt when it lands. The faster it was
        falling, the more damage."""
        for v, (a, since, fall) in list(self.flying.items()):
            if v not in self.robots or v.knocked_out or now > since + 4.0:
                del self.flying[v]
                continue
            down = -v.np.node().getLinearVelocity().z
            if fall > 2.0 and down < 0.5 * fall:  # it was falling fast and now it isn't: it has landed
                del self.flying[v]
                self.hit(a if a in self.robots else None, v, min(SLAM_FALL_MAX, SLAM_FALL * fall), now,
                         f"{v.name} CRASHES DOWN", None, "hammer")
            else:
                self.flying[v][2] = max(fall, down)

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

    def spike_pit_hits(self, now):
        """Spike pit (user mod): the spikes drain the armour of any robot down in the pit, bite after bite."""
        for r in self.robots:
            key = ("spike_pit", r.id)
            if r.knocked_out or now < self.cooldown.get(key, 0) or not self.in_spike_pit(r):
                continue
            self.hit(None, r, SPIKE_PIT_DAMAGE * RULES["hazard_damage"], now, f"{r.name} is in the spike pit",
                     r.pos, "spikes")
            self.cooldown[key] = now + SPIKE_PIT_EVERY
            if self.practice and not r.house:  # no damage in practice: it comes back, as it does from the drop zone
                self.knock_out(r, now, f"{r.name} is stuck in the spike pit!")

    def boost_pad_touch(self, now):
        """Boost button (user mod): the first robot to drive onto it is boosted for BOOST_SECONDS (faster and with
        more push: see Robot.tick). The button then rests for BOOST_REST seconds, so a robot chasing it can't boost
        too. Resident Robots don't use it."""
        if now < self.boost_ready_at or self.frozen:
            return
        kx, ky, ks = self.BOOST_PAD
        for r in self.robots:
            p = r.pos
            if r.house or r.knocked_out or abs(p.x - kx) > ks / 2 or abs(p.y - ky) > ks / 2 or not -0.2 < p.z < 0.8:
                continue
            r.boost_until, self.boost_ready_at = now + BOOST_SECONDS, now + BOOST_REST
            self.events.append((now, f"{r.name} {BOOST_SECONDS:.0f} Second Boost"))
            return

    def laser(self, a):
        """Laser beam (user mod): where a robot's beam starts and ends, and the robot it hits (None if it hits
        nobody). The beam goes level from the top of the robot's front, the way the robot faces, to the first
        robot in its way: with none in its way, to the end of its range or the arena's edge."""
        flat = Vec3(a.forward.x, a.forward.y, 0)
        if flat.length() < 0.5:  # (pointing up or down: no beam)
            return None
        flat.normalize()
        nose = a.shape["half"].y
        start = a.pos + flat * nose + Vec3(0, 0, a.shape["top"] + 0.05)
        reach, hit = LASER_RANGE, None
        for v in self.robots:
            if v is a or v.knocked_out or abs(v.pos.z - a.pos.z) > 1.0:  # (a robot down in a pit is under the beam)
                continue
            to = v.pos - a.pos
            along = to.x * flat.x + to.y * flat.y - nose  # how far down the beam the robot is...
            side = abs(to.x * flat.y - to.y * flat.x)     # ...and how far to one side of it
            r = (v.shape["half"].x + v.shape["half"].y) / 2
            if along <= 0 or side >= r:
                continue
            touch = max(0.0, along - math.sqrt(r * r - side * side))  # where the beam meets the robot
            if touch < reach:
                reach, hit = touch, v
        if hit is None:
            h = ARENA / 2
            for p, d in ((start.x, flat.x), (start.y, flat.y)):
                if abs(d) > 1e-6:
                    reach = min(reach, ((h if d > 0 else -h) - p) / d)
        return start, start + flat * max(0.0, reach), hit

    def laser_shots(self, now):
        """Laser beam (user mod): the robot in the beam of a laser that has just fired is pushed away, along the
        beam. The push is a speed (LASER_POWER x LASER_PUSH m/s, never more than max_launch_speed), so a heavy
        robot is pushed as fast as a light one: a Resident Robot much less. A laser does no damage."""
        self.lasers = []
        for a in self.robots:
            if a.knocked_out or now >= a.laser_at + LASER_SECONDS:
                continue
            beam = self.laser(a)
            if beam is None:
                continue
            start, end, v = beam
            self.lasers.append((start, end))
            if v is None or a.laser_at != now:  # (it pushes once, as it fires)
                continue
            way = end - start
            way.z = 0
            if not way.normalize():
                way = Vec3(a.forward.x, a.forward.y, 0)
                way.normalize()
            body = v.np.node()
            speed = min(RULES["max_launch_speed"], LASER_POWER * LASER_PUSH)
            body.applyCentralImpulse(way * speed * body.getMass() * (0.35 if v.big else 1.0))
            v.pushed_until = now + 0.3  # (its tyres slide while it's pushed: see PUSH_GRIP)
            self.impacts.append(((end.x, end.y, max(0.1, end.z)), 4.0, "laser"))
            self.events.append((now, f"{a.name}'s laser pushes {v.name}"))

    def flame_pit_burn(self, now):
        """Flame pit (user mod): the flames climb while a robot is down in the pit, and a robot that has been in
        for FLAME_PIT_SECONDS is deactivated. With nobody in, they sink back to the baseline the teacher set."""
        inside = [r for r in self.robots if not r.knocked_out and self.in_flame_pit(r)]
        self.flame_pit_since = {r: t for r, t in self.flame_pit_since.items() if r in inside}
        longest = 0.0
        for r in inside:
            if r not in self.flame_pit_since:
                self.flame_pit_since[r] = now
                self.events.append((now, f"{r.name} is in the flame pit!"))
            longest = max(longest, now - self.flame_pit_since[r])
            if now - self.flame_pit_since[r] >= FLAME_PIT_SECONDS and not r.house:  # (Resident Robots are put back)
                self.knock_out(r, now, f"{r.name} is deactivated by the flame pit!")
        want = self.flame_pit_cm / 100 * (1 + (FLAME_PIT_RISE - 1) * min(1.0, longest / FLAME_PIT_SECONDS))
        self.flame_height += (want - self.flame_height) * 0.1

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
            if r.house:  # Resident Robots: out of action at zero (until the next round); if stuck, they are put back
                if r.knocked_out:
                    continue
                if r.health <= 0:
                    self.knock_out(r, now, f"{r.name} is out of action!")
                    continue
                stuck = p.z < -1 or abs(p.x) > h + 1 or abs(p.y) > h + 1 or r.np.getQuat().getUp().z < 0.3
                stuck = stuck or self.in_spike_pit(r) or self.in_flame_pit(r)
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
                    room = h - r.shape["half"].y - 0.2 if r.k > 1 else h  # (a robot bigger than standard is put
                    r.np.setPos(max(-room, min(room, p.x)), max(-room, min(room, p.y)), 0.8)  # down clear of the walls)
                    r.np.setHpr(r.np.getH(), 0, 0)
                    if "weapon" not in r.lost:
                        r.park_weapon()
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
                "saw_hot": [1 if self.time < t else 0 for t in self.saw_hot_until],
                # flame pit (user mod): how high its flames stand above the floor (only sent while it's on)
                **({"flames": round(self.flame_height, 2)} if self.user_mods["flame_pit"] else {}),
                # boost button (user mod): 1 while it will work, 0 while it rests (only sent while it's on)
                **({"boost": 1 if self.time >= self.boost_ready_at else 0} if self.user_mods["boost_pad"] else {}),
                # laser beam (user mod): each beam showing now, start x, y, z then end x, y, z (only sent while it's on)
                **({"lasers": [[round(c, 2) for c in (*s, *e)] for s, e in self.lasers]}
                   if self.user_mods["laser_beam"] else {})}

    def take_fx(self):
        """New hits and spark showers since the last call (then forgets them)."""
        impacts, streams = self.impacts, self.streams
        self.impacts, self.streams = [], []
        return impacts, streams


class Arenas:
    """Several arenas (cages side by side), stepped together: a Bullet world each, with the same hazards and
    Resident Robots in every one (CHANGE 75). The server talks to this as it talked to one Arena: the clock,
    the events and the settings are shared, and each robot is in one arena (robot.arena, with its index)."""

    def __init__(self, count=1, hazards=None, user_mods=None):
        self.events = []
        self._next_id = 0
        self.arenas = []
        for i in range(max(1, min(MAX_ARENAS, int(count)))):
            a = Arena(hazards=hazards, user_mods=user_mods, seed=i + 1)
            a.index, a.id_source, a.events = i, self.next_id, self.events
            self.arenas.append(a)
        for a in self.arenas:  # (the Resident Robots were built before the id source was set: number them again)
            for r in a.robots:
                r.id = self.next_id()

    def next_id(self):
        self._next_id += 1
        return self._next_id - 1

    def __len__(self):
        return len(self.arenas)

    def __iter__(self):
        return iter(self.arenas)

    def __getitem__(self, i):
        return self.arenas[i]

    # the shared things: read from the first arena, set on every one
    def _get(self, key):
        return getattr(self.arenas[0], key)

    def _set(self, key, value):
        for a in self.arenas:
            setattr(a, key, value)

    time = property(lambda self: self._get("time"))
    hazards = property(lambda self: self._get("hazards"))
    user_mods = property(lambda self: self._get("user_mods"))
    practice = property(lambda self: self._get("practice"), lambda self, v: self._set("practice", v))
    frozen = property(lambda self: self._get("frozen"), lambda self, v: self._set("frozen", v))
    real_damage = property(lambda self: self._get("real_damage"), lambda self, v: self._set("real_damage", v))
    flame_pit_cm = property(lambda self: self._get("flame_pit_cm"), lambda self, v: self._set("flame_pit_cm", v))

    @property
    def robots(self):
        return [r for a in self.arenas for r in a.robots]

    def add_robot(self, design, brain=chase_brain, owner="cpu", start=None, arena=0):
        """arena: its index, or the Arena itself."""
        a = arena if isinstance(arena, Arena) else self.arenas[max(0, min(len(self.arenas) - 1, int(arena)))]
        return a.add_robot(design, brain=brain, owner=owner, start=start)

    def remove_robot(self, r):
        r.arena.remove_robot(r)

    def set_hazards(self, hazards):
        for a in self.arenas:
            a.set_hazards(hazards)

    def set_user_mods(self, values):
        for a in self.arenas:
            a.set_user_mods(values)

    def set_pit(self, open_, instant=False):
        for a in self.arenas:
            a.set_pit(open_, instant)

    def restart(self):
        for a in self.arenas:
            a.restart()

    def step(self):
        for a in self.arenas:
            a.step()
        if len(self.events) > 200:
            del self.events[:-50]
