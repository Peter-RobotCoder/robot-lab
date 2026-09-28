"""The computer fighters' drivers, from Empty to Expert. Each is a brain: given its fighter, the other fighter
and the ring, it returns (forward, side, action) 60 times a second, just like a learner's brain.

    empty   stands still, unless the teacher uploads brains/demo_cpu.py (a brain written like a learner's, for
            coding demos in front of the class)
    easy    slow to react (it decides about every 0.7 s), wanders about and mashes buttons when it's close
    medium  reacts in about a third of a second, keeps a sensible distance, blocks some attacks (not always at
            the right height), carries on its combo after a hit, and uses its special when it has the energy
    expert  sees an attack start almost at once (about 0.12 s, like a very good player) and blocks it at the
            right height, punishes attacks that miss, sidesteps shots, throws fighters who only block, jump-kicks
            fighters who crouch, uses its special at the right moment, keeps away from the edge and tries to
            knock you off it, and backs off when it's badly hurt
Reaction time matters most: two equal fighters driven equally well win about half their fights each.
"""
import math
import random

import fight_sim as sim

LEVELS = {"empty": "Empty", "easy": "Easy", "medium": "Medium", "expert": "Expert"}
NOTHING = (0.0, 0.0, "")


def empty_brain(me, enemy, ring):
    return NOTHING


# ---------- things every level needs to know ----------
def memory(me):
    """Each computer fighter's own notes, kept between ticks."""
    return me.__dict__.setdefault("cpu_memory", {"next": -1.0, "last": NOTHING, "plan": "", "plan_until": -1.0,
                                                 "seen": None, "jump_in": False})


def out_of_it(f):
    """Knocked out, fallen off, or not there at all."""
    return f is None or f.knocked_out or f.state == "ringout"


def reach_of(f, move):
    """How far a move reaches from the middle of fighter f (to the middle of an ordinary fighter)."""
    return f.reach(move) + sim.Fighter.RADIUS


def left_towards(me, x, y):
    """Which way to sidestep (+1 left, -1 right) to get closer to the point x, y."""
    lx, ly = -me.fy, me.fx  # my left
    return 1.0 if lx * (x - me.x) + ly * (y - me.y) >= 0 else -1.0


def towards(me, x, y):
    """(forward, side) that walks me straight towards the point x, y (forward is towards the enemy)."""
    dx, dy = x - me.x, y - me.y
    d = math.hypot(dx, dy) or 1.0
    return (me.fx * dx + me.fy * dy) / d, (-me.fy * dx + me.fx * dy) / d


def will_reach(enemy, me, margin=0.25):
    """Will the enemy's attack (aimed when it started) reach me?"""
    m = sim.MOVES[enemy.move]
    s, a, r = enemy.timing(enemy.move)
    still = max(0.0, s + a * 0.5 - enemy.move_t)  # it still steps forward for this long
    reach = enemy.reach(enemy.move) + me.radius + m.lunge * still + margin
    dx, dy = me.x - enemy.x, me.y - enemy.y
    if enemy.move == "spin_kick":
        return math.hypot(dx, dy) <= reach
    along = dx * enemy.aim[0] + dy * enemy.aim[1]
    side = abs(dx * enemy.aim[1] - dy * enemy.aim[0])
    return 0 < along <= reach and side <= m.width + me.radius + margin


def shot_coming(me, ring):
    """A blast flying at me: seconds until it arrives, or None."""
    best = None
    for p in ring.projectiles:
        if p.owner is me:
            continue
        dx, dy = me.x - p.x, me.y - p.y
        along = dx * p.dx + dy * p.dy
        side = abs(dx * p.dy - dy * p.dx)
        if along > -0.2 and side < me.radius + 0.45:
            t = along / sim.BLAST_SPEED
            best = t if best is None else min(best, t)
    return best


def block_for(height):
    """The right block for an attack's height."""
    return "low_block" if height == "low" else "block"


def near_edge(f, ring, how_close):
    return ring.stage.hazards.get("ring_out") and sim.edge_distance(f) < how_close


# ---------- easy ----------
def easy_brain(me, enemy, ring):
    """A beginner: wanders about, and presses buttons whenever the other fighter is anywhere near."""
    if out_of_it(enemy):
        return NOTHING
    mem = memory(me)
    now = ring.stage.time
    if now < mem["next"]:
        return mem["last"]
    mem["next"] = now + random.uniform(0.5, 0.9)
    d = sim.distance(me, enemy)
    if d > 2.0:
        out = (random.choice((1.0, 1.0, 0.6, 0.0)), random.choice((0.0, 0.0, 1.0, -1.0)), "")
    elif random.random() < 0.15:
        out = (0.0, 0.0, "block")
    elif random.random() < 0.08:
        out = (0.0, 0.0, "jump")
    else:
        out = (random.choice((0.5, 0.0, -0.3)), random.choice((0.0, 0.0, 0.5)),
               random.choice(("punch", "punch", "kick", "low", "special", "")))
    mem["last"] = out
    return out


# ---------- medium and expert: one brain, with settings for how good it is ----------
MEDIUM = {"reaction": 0.18, "decide": 0.35, "block": 0.45, "right_height": 0.65, "punish": False, "dodge": False,
          "throw_blockers": 0.3, "jump_in": 0.0, "edge": 1.5, "smart_special": False, "retreat": False,
          "combo": True, "wiggle": 0.25, "footsies": False}
EXPERT = {"reaction": 0.12, "decide": 0.22, "block": 0.95, "right_height": 1.0, "punish": True, "dodge": True,
          "throw_blockers": 0.9, "jump_in": 0.35, "edge": 2.0, "smart_special": True, "retreat": True,
          "combo": True, "wiggle": 0.1, "footsies": True}


def defend(me, enemy, ring, how, mem):
    """React to an attack we've seen coming. Returns what to do, or None if there's nothing to worry about."""
    now = ring.stage.time
    arriving = shot_coming(me, ring)
    if arriving is not None and arriving < 0.6:
        if how["dodge"] and arriving > 0.2 and me.free:  # step out of its way
            cx, cy = ring.centre
            return 0.3, left_towards(me, cx, cy), ""
        if mem["plan"] == "shot_block" or random.random() < how["block"]:
            mem["plan"] = "shot_block"
            return 0.0, 0.0, "block"
    if enemy.state != "attack" or enemy.move == "blast":
        return None
    if enemy.move_t < how["reaction"] or enemy.move_phase() == "recovery":
        return None  # we haven't seen it yet, or it's already over
    seen = (enemy.move, round(now - enemy.move_t, 2))  # which attack: what it is and when it started
    if mem["seen"] != seen:  # a new attack: decide once how to deal with it
        mem["seen"] = seen
        mem["defence"] = random.random() < how["block"]
        mem["guess_right"] = random.random() < how["right_height"]
    if not will_reach(enemy, me):
        return None
    m = sim.MOVES[enemy.move]
    if m.height == "throw":  # a throw can't be blocked: jump out of it (throws miss fighters in the air)
        return (0.0, 0.0, "jump") if mem["defence"] and me.free else None
    if not mem["defence"]:
        return None
    # an uppercut can't be hit as it starts: a clever fighter answers an attack with one
    if how["smart_special"] and me.special == "uppercut" and me.energy >= sim.RULES["special_cost"] and me.free:
        if enemy.move_phase() == "startup" and random.random() < 0.5:
            return 0.0, 0.0, "special"
    height = m.height if mem["guess_right"] else random.choice(("low", "high"))
    return 0.0, 0.0, block_for(height)


def use_special(me, enemy, ring, how, d):
    """Is now a good time for our special move?"""
    if me.energy < sim.RULES["special_cost"]:
        return False
    sp = me.special
    if not how["smart_special"]:  # it just throws it out now and then, when it's roughly in range
        return {"blast": d > 2.0, "uppercut": d < 1.3, "spin_kick": d < 1.5, "slam": d < 1.1}[sp] \
            and random.random() < 0.05
    if sp == "blast":
        return d > 2.3 and enemy.state not in ("jump", "knockdown", "getup") and not ring.projectiles
    if sp == "uppercut":  # an anti-air, or a punish when they miss
        return d < 1.4 and (enemy.state == "jump" or enemy.move_phase() == "recovery")
    if sp == "spin_kick":  # it catches a sidestep
        return d < 1.6 and (enemy.state == "side" or enemy.move_phase() == "recovery")
    if sp == "slam":  # a grab that goes through blocks
        return d < 1.2 and not enemy.airborne and enemy.state in ("block", "low_block", "blockstun", "idle", "crouch",
                                                                   "walk", "side")
    return False


def fighter_brain(me, enemy, ring, how):
    """A good fighter's plan, played at the level in `how`."""
    if out_of_it(enemy) or ring.phase != "fight":
        return NOTHING
    mem = memory(me)
    now = ring.stage.time
    d = sim.distance(me, enemy)
    # 1. keep a combo going: punch again straight away after a hit lands
    if me.state == "attack":
        if how["combo"] and me.from_combo and me.chain_open:
            return 0.0, 0.0, "punch"
        return NOTHING
    if me.state == "jump":
        if not me.jumped_attack and d < 1.7 and me.vz < 1.5:
            return 0.0, 0.0, "kick"  # the jump kick: an overhead that beats a crouching block
        return 1.0, 0.0, ""
    # 2. defend against what's coming
    guard = defend(me, enemy, ring, how, mem)
    if guard is not None:
        return guard
    if mem["plan"] == "shot_block":
        mem["plan"] = ""
    # 3. chances that need a quick answer (every tick)
    quick = reflexes(me, enemy, ring, how, d)
    if quick is not None:
        return quick
    # 4. the plan for moving about: decided every so often, and kept in between
    if now < mem["next"]:
        return mem["last"]
    mem["next"] = now + how["decide"] * random.uniform(0.7, 1.3)
    out = plan(me, enemy, ring, how, mem, d)
    fwd, side, action = out
    mem["last"] = (fwd, side, action if action in sim.HOLDS else "")  # (a press happens once, a hold is kept)
    return out


def reflexes(me, enemy, ring, how, d):
    """Quick answers: a special at the right moment, punishing a miss, blocking a jump kick."""
    if not me.free or enemy.state in ("knockdown", "getup"):
        return None
    if use_special(me, enemy, ring, how, d):
        return 0.0, 0.0, "special"
    kick_reach = reach_of(me, "kick")
    if how["punish"] and enemy.move_phase() == "recovery" and d < kick_reach + 0.3:
        s, a, r = enemy.timing(enemy.move)
        left = s + a + r - enemy.move_t
        return 0.4, 0.0, "punch" if left > 0.1 or d < reach_of(me, "punch") else "kick"
    if how["punish"] and enemy.state == "jump" and d < 1.8:
        return 0.0, 0.0, "block"  # a jump kick is an overhead: block it standing
    return None


def plan(me, enemy, ring, how, mem, d):
    """What to do when nothing is coming at us."""
    cx, cy = ring.centre
    punch_reach, kick_reach = reach_of(me, "punch"), reach_of(me, "kick")
    their_reach = reach_of(enemy, "kick") + 0.25
    hurt = me.health / me.stats["health"]
    they = enemy.health / enemy.stats["health"]
    wiggle = random.uniform(-how["wiggle"], how["wiggle"])
    # knocked down or getting up: they can't be hit, so wait just out of reach
    if enemy.state in ("knockdown", "getup"):
        return (0.6 if d > kick_reach + 0.2 else -0.4 if d < 1.2 else 0.0), 0.0, ""
    # stay away from the edge: circle round (no attacking) until they are the one nearer to it
    # (how["edge"]: how near the edge before it worries; 0 = it never notices)
    if how["edge"] and near_edge(me, ring, how["edge"]) and sim.edge_distance(me) <= sim.edge_distance(enemy) + 0.3:
        fwd, side = towards(me, cx, cy)  # head for the middle of the ring
        if abs(side) < 0.5:  # they're in the way: go round them
            side = 0.8 if side >= 0 else -0.8
        if d < kick_reach + 0.2:
            fwd = min(fwd, 0.1)
        return fwd, side, ""
    # badly hurt and losing: keep away and wait for a chance
    if how["retreat"] and hurt < 0.3 and they > hurt + 0.15:
        if d < 2.2 and not near_edge(me, ring, 2.2):
            return -1.0, random.choice((1.0, -1.0)) * 0.5, ""
        return 0.0, 0.0, "block"
    # they only block: throw them (or jump over a crouching block)
    blocking = enemy.state in ("block", "low_block", "blockstun")
    if blocking and d < reach_of(me, "throw") and random.random() < how["throw_blockers"]:
        return 0.0, 0.0, "throw"
    if enemy.state in ("low_block", "crouch") and 1.1 < d < 2.2 and random.random() < how["jump_in"]:
        return 1.0, 0.0, "jump"
    # the edge is behind them: big pushes to knock them off
    if how["edge"] >= 2 and near_edge(enemy, ring, 1.5) and d < kick_reach + 0.4:
        return 0.6, 0.0, "kick" if d > punch_reach else random.choice(("punch", "kick", "high"))
    if how["footsies"]:
        return footsies(me, enemy, ring, how, d, punch_reach, kick_reach, their_reach, wiggle)
    # too far: walk in
    if d > kick_reach + 0.1:
        return 1.0, wiggle, ""
    # in range: mix it up
    if d > punch_reach:
        return 0.4, 0.0, random.choice(("kick", "kick", "high", ""))  # (forward over 0.5 + kick = the high kick)
    return 0.0, wiggle, random.choice(("punch", "punch", "punch", "kick", "low", "block"))


def footsies(me, enemy, ring, how, d, punch_reach, kick_reach, their_reach, wiggle):
    """The expert's spacing game: stay just outside their reach, let them miss, and strike when it's safe."""
    if enemy.special == "blast" and d > 2.4:  # far away from a blaster: close in, weaving from side to side
        side = 0.7 if int(ring.stage.time / 1.2) % 2 else -0.7
        return 1.0, side, ""
    if d > max(kick_reach, their_reach) + 0.35:
        return 1.0, wiggle, ""  # far: walk in
    r = random.random()
    if near_edge(me, ring, 1.6) and r > 0.45:
        r = random.random() * 0.55  # near the edge: no stepping back or sideways
    if d > kick_reach + 0.05:  # we can't reach yet: edge in, or wait for them to come (and miss)
        if r < 0.45:
            return 0.8, wiggle, ""
        if r < 0.7:
            return 0.0, random.choice((1.0, -1.0)) * 0.6, ""  # a sidestep: their straight attacks miss
        return -0.3, 0.0, ""
    if d > their_reach - 0.1:  # we reach and they don't: poke
        return 0.0, 0.0, "kick" if r < 0.6 else ""
    # both in range: guess
    if r < 0.30:
        return 0.0, 0.0, "punch" if d < punch_reach else "kick"
    if r < 0.42:
        return 0.0, 0.0, random.choice(("low", "high"))
    if r < 0.55:
        return 0.0, 0.0, "throw" if d < reach_of(me, "throw") else "kick"
    if r < 0.75:
        return 0.0, 0.0, random.choice(("block", "block", "low_block"))
    if r < 0.88:
        return -1.0, 0.0, ""  # step back: make them miss
    return 0.0, random.choice((1.0, -1.0)), ""


def medium_brain(me, enemy, ring):
    return fighter_brain(me, enemy, ring, MEDIUM)


def expert_brain(me, enemy, ring):
    return fighter_brain(me, enemy, ring, EXPERT)


BRAINS = {"empty": empty_brain, "easy": easy_brain, "medium": medium_brain, "expert": expert_brain}


def for_level(level, demo=None):
    """The brain for a computer fighter at this level (demo: the teacher's uploaded demo brain, for "empty")."""
    if level == "empty":
        return demo or empty_brain
    return BRAINS.get(level, medium_brain)
