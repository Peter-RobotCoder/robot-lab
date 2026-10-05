"""The computer robots' drivers, from No brain to Expert. Each is a brain: given its robot, the other robots and the
arena, it returns (throttle, steer, attack) 60 times a second.

    none    no brain: it sits still. Every game starts like this, so nothing attacks until the teacher chooses
            a level
    empty   stands still, unless the teacher uploads brains/demo_cpu.py (a brain written like a learner's, for
            coding demos in front of the class)
    easy    slow to react (it decides about once a second), wobbly aim, fires wildly, knows nothing about hazards
    medium  aims properly, fires when close and facing, steers away from an open drop zone; reacts in half a second
    expert  reacts instantly, avoids every hazard, picks weak targets, uses its own weapon well (spinners wait until
            they have spun up, wedges get underneath, hammers stop and strike), backs off when badly damaged,
            and gets itself unstuck
Reaction time matters most: two equal robots driven equally well win about half their fights each.
"""
import math

import lab_sim as sim

LEVELS = {"none": "No brain", "empty": "Empty", "easy": "Easy", "medium": "Medium", "expert": "Expert"}
START_LEVEL = "none"  # every game starts with the computer robots still: the teacher switches their brains on
FLANK = False  # (tested: circling round made expert wedges and hammers worse, so it's off)
USE = {"spin_wait": True, "retreat": True, "avoid": True, "pit_escape": True, "side_aim": True, "herd": True}


def empty_brain(me, enemies, arena):
    return 0.0, 0.0, False


def slow(brain, every):
    """A driver who decides only every so often (in seconds) and keeps doing the same thing in between."""
    def decide(me, enemies, arena):
        mem = me.__dict__.setdefault("cpu_reaction", {"next": -1.0, "last": (0.0, 0.0, False)})
        if arena.time >= mem["next"]:
            mem["last"] = brain(me, enemies, arena)
            mem["next"] = arena.time + every
        return mem["last"]
    decide.__name__ = brain.__name__
    return decide


def easy_brain(me, enemies, arena):
    """A clumsy driver: slow to turn, always at the same speed, firing whenever anything is vaguely near."""
    if not enemies:
        return 0.0, 0.0, False
    target = min(enemies, key=lambda e: (e.pos - me.pos).length())
    angle, dist = sim.angle_to(me, target.pos)
    wobble = math.sin(arena.time * 1.3 + me.id) * 0.4  # it never quite drives straight
    return 0.7, max(-0.6, min(0.6, angle / 70 + wobble)), dist < 3.5


def medium_brain(me, enemies, arena):
    return sim.chase_brain(me, enemies, arena)


# ---------- expert ----------
def dangers(me, arena):
    """Places to stay away from right now: (x, y, how close is too close)."""
    out = []
    if arena.hazards["pit"] and arena.pit_open:
        px, py, ps = arena.PIT
        out.append((px, py, ps / 2 + 0.7))
    for i, (sx, sy) in enumerate(arena.SAWS):
        if arena.hazards["saws"] and arena.saw_height[i] > 0.3:
            out.append((sx, sy, 1.5))
    if arena.hazards["spikes"]:
        wx, y0, y1 = arena.SPIKES
        out.append((wx, (y0 + y1) / 2, 1.8))
    h = sim.ARENA / 2
    for r in arena.robots:  # the Resident Robots' corners
        if r.house:
            out.append((r.corner[0] * h, r.corner[1] * h, sim.CPZ * 1.3))
    return out


def avoid(me, arena, steer, throttle):
    """Steer away from any danger just ahead."""
    f = me.forward
    for x, y, reach in dangers(me, arena):
        to = sim.Vec3(x - me.pos.x, y - me.pos.y, 0)
        d = to.length()
        if d < reach + 0.8:
            ahead = (f.x * to.x + f.y * to.y) / max(d, 1e-3)
            if ahead > 0.2:  # it's in front: turn away from it, and slow down
                side = f.x * to.y - f.y * to.x
                steer = -1.0 if side > 0 else 1.0
                throttle = min(throttle, 0.4 if d > reach else -0.5)
    return steer, throttle


def expert_brain(me, enemies, arena):
    mem = me.__dict__.setdefault("cpu_memory", {"stuck": 0.0, "last": (me.pos.x, me.pos.y), "escape_until": -1.0})
    now = arena.time
    if now < mem["escape_until"]:  # getting unstuck: back away and turn
        return -0.8, 1.0, False
    if not enemies:
        return 0.0, 0.0, False
    # pick a target: close, and already damaged
    def score(e):
        return (e.pos - me.pos).length() + 4 * max(0.0, e.health) / e.stats["armour"]
    target = min(enemies, key=score)
    angle, dist = sim.angle_to(me, target.pos)
    # every weapon points forwards: if we're in front of theirs, circle round to their side or back first
    to_me = me.pos - target.pos
    to_me.z = 0
    facing_us = target.forward.dot(to_me.normalized()) > 0.5 if to_me.length() > 0.1 else False
    if FLANK and facing_us and dist > 1.8 and me.weapon not in ("spinner", "drum", "vdisc"):
        flank = target.pos + target.np.getQuat().getRight() * (2.2 if angle > 0 else -2.2) - target.forward * 1.0
        angle, _ = sim.angle_to(me, flank)
    my_armour = max(0.0, me.health) / me.stats["armour"]
    throttle, attack = 1.0, False
    herding = False
    if USE["herd"] and arena.hazards["pit"] and arena.pit_open:
        # the drop zone knocks a robot out at once: get round to the far side of the target, then push it in
        px, py, ps = arena.PIT
        pit = sim.Point3(px, py, 0)
        away = target.pos - pit
        away.z = 0
        if 0.1 < away.length() < 6.0:
            behind = target.pos + away.normalized() * 2.0
            if (me.pos - pit).length() < away.length() + 0.5:  # we're on the pit's side: go round first
                angle, _ = sim.angle_to(me, behind)
            else:  # the target is between us and the pit: charge
                herding = True
    if me.weapon in ("spinner", "drum", "vdisc"):
        # aim a little to the side of the target, to hit it where it isn't pointing its own weapon
        if USE["side_aim"]:
            angle, _ = sim.angle_to(me, target.pos + target.np.getQuat().getRight() * (0.6 if dist > 2.5 else 0.0))
        full = {"spinner": 32, "drum": 45, "vdisc": 38}[me.weapon] * me.stats["power"] * 60 / (2 * math.pi)
        spun_up = me.weapon_rpm > 0.75 * full
        if USE["spin_wait"] and not spun_up and dist < 3:  # a hit slowed the weapon: back off until it's spun up
            throttle = -0.6
        attack = spun_up
    elif me.weapon == "wedge":
        attack = dist < 2.8 * me.stats["size"] and abs(angle) < 20  # drive the wedge underneath, then fire
        throttle = 1.0
    elif me.weapon == "hammer":
        throttle = 0.0 if dist < 2.2 else 0.9  # stop at arm's length, then swing
        attack = dist < 2.7 * me.stats["size"] and abs(angle) < 25
    else:
        attack = dist < 2.8 and abs(angle) < 25
    if USE["retreat"] and my_armour < 0.25 and max(0.0, target.health) / target.stats["armour"] > my_armour:
        throttle = -0.7 if dist < 3 else 0.3  # badly damaged: keep away and wait for a chance
    steer = max(-1.0, min(1.0, angle / 25))
    if abs(angle) > 60 and throttle > 0:
        throttle = 0.3  # turn first, then go
    if USE["avoid"] and not herding:
        steer, throttle = avoid(me, arena, steer, throttle)
    if USE["pit_escape"] and arena.hazards["pit"] and arena.pit_open:  # right by the drop zone: get away from it before anything else
        px, py, ps = arena.PIT
        pit_angle, pit_dist = sim.angle_to(me, sim.Point3(px, py, 0))
        if pit_dist < ps / 2 + 1.3:
            if abs(pit_angle) < 90:  # facing it: reverse away
                throttle, steer = -1.0, (1.0 if pit_angle < 0 else -1.0) * 0.5
            else:  # it's behind us: drive on, away from it
                throttle, steer = 1.0, max(-1.0, min(1.0, -(180 - abs(pit_angle)) * (1 if pit_angle > 0 else -1) / 30))
    # stuck against something? (trying to drive but not moving)
    moved = math.hypot(me.pos.x - mem["last"][0], me.pos.y - mem["last"][1])
    mem["last"] = (me.pos.x, me.pos.y)
    mem["stuck"] = mem["stuck"] + sim.STEP if (abs(throttle) > 0.3 and moved < 0.004) else 0.0
    if mem["stuck"] > 1.2:
        mem["stuck"], mem["escape_until"] = 0.0, now + 0.8
    return throttle, steer, attack


def armed(brain):
    """Every robot starts with its weapon off. A computer robot with a weapon that toggles (a spinner, drum or
    disc) switches it on as soon as it has someone to fight, and off again when it hasn't."""
    def drive(me, enemies, arena):
        throttle, steer, attack = brain(me, enemies, arena)
        return throttle, steer, (bool(enemies) if me.weapon in sim.TOGGLE_WEAPONS else attack)
    drive.__name__ = brain.__name__
    return drive


# reaction times (tested in headless leagues): medium decides every 0.45 s, easy every 0.8 s, expert every tick
BRAINS = {"none": empty_brain, "empty": empty_brain, "easy": armed(slow(easy_brain, 0.8)),
          "medium": armed(slow(medium_brain, 0.45)), "expert": armed(expert_brain)}


def for_level(level, demo=None):
    """The brain for a computer robot at this level (demo: the teacher's uploaded demo brain, for "empty")."""
    if level == "empty":
        return demo or empty_brain
    return BRAINS.get(level, empty_brain)
