"""Craft Lab's movement (CHANGE 200): a player (and a creature) walking, running, in Careful mode, jumping,
swimming, climbing and flying among the blocks, 60 steps a second. Pure arithmetic on a few numbers, the same on the server and
in the windows, so a window predicts its own player and the server checks it (engine.predict).

A player is a box 0.7 wide and 1.7 tall standing at (x, y, z) (z its feet), moving by (vx, vy, vz) metres a second.
Each step it moves up or down first, then across and along, stopped by any solid block it would go into. The input is
(mx, my, buttons): where to go in the world's frame (from the keys and the way you look, worked out by the window),
and the buttons held: jump, run, careful (you won't step off an edge), fly.

Also here: the ray from your eyes to the block you look at (dig and place), and the wire record (engine.wire) every
snapshot sends for each player and creature.
"""
import math

import craft_blocks as B

SIM_VERSION = 2   # (the page's craft_sim.js steps a player as this does: club-coders/web/craft_sim_test.py's
#                   fingerprint is recorded for this number; a change that moves a step's numbers raises it)
STEP = 1 / 60
HALF = 0.35          # half the box's width
TALL = 1.7
EYE = 1.55
CAREFUL_TALL = 1.4
CAREFUL_EYE = 1.3
GRAVITY = 30.0
JUMP = 9.17           # (a jump lifts the feet 1.4 blocks)
TERMINAL = 60.0
WALK, SPRINT, CAREFUL, FLY_SPEED, FLY_FAST = 4.5, 6.4, 1.6, 10.0, 18.0
SWIM, SWIM_UP, SWIM_SINK = 2.2, 4.0, 1.6
CLIMB = 2.4
REACH, REACH_CREATIVE = 5.0, 6.5
JUMP_B, SPRINT_B, CAREFUL_B, FLY_B, RESPAWN_B = 1, 2, 4, 8, 16   # (flying, CAREFUL_B is down)

# the wire record: one kind of thing for players and creatures (kind 0 player, 1 fluff, 2 bleep, 3 glitch, 4 rust,
# 5 bot); flags: on the ground, in water, flying, careful, hurt, asleep (in a Recharge Pod; a Fluff: brushed), swinging
# an arm, climbing. hp, energy and shield are the server's own (0 to 100), never predicted
SCHEMA_FIELDS = [("kind", "B", 1), ("x", "i", 1000), ("y", "i", 1000), ("z", "i", 1000), ("vx", "h", 100),
                 ("vy", "h", 100), ("vz", "h", 100), ("yaw", "H", 100), ("pitch", "h", 100), ("flags", "B", 1),
                 ("hp", "B", 1), ("energy", "B", 1), ("shield", "B", 1), ("held", "H", 1), ("fall", "H", 100)]
F_GROUND, F_WATER, F_FLY, F_CAREFUL, F_HURT, F_SLEEP, F_SWING, F_CLIMB = 1, 2, 4, 8, 16, 32, 64, 128
KINDS = {"player": 0, "fluff": 1, "bleep": 2, "glitch": 3, "rust": 4, "bot": 5}

_solid = None
_liquid = None
_climb = None


def tables():
    global _solid, _liquid, _climb
    if _solid is None or len(_solid) < len(B.BLOCKS):
        _solid = [b["solid"] for b in B.BLOCKS] + [False] * (256 - len(B.BLOCKS))
        _liquid = [b["shape"] == "liquid" for b in B.BLOCKS] + [False] * (256 - len(B.BLOCKS))
        _climb = [b["climb"] for b in B.BLOCKS] + [False] * (256 - len(B.BLOCKS))
    return _solid, _liquid, _climb


def heights(bid, meta=0):
    """How tall a solid block is (a step and a Recharge Pod are lower: you walk up onto them; a Grow bed too)."""
    shape = B.BLOCKS[bid]["shape"]
    return {"slab": 0.5, "bed": 0.6, "farmland": 0.875}.get(shape, 1.0)


def new_player(x, y, z, kind=0):
    return {"x": x, "y": y, "z": z, "vx": 0.0, "vy": 0.0, "vz": 0.0, "yaw": 0.0, "pitch": 0.0, "flags": 0, "hp": 100,
            "energy": 100, "shield": 0, "held": 0, "fall": 0.0, "kind": kind}


def blocked(world, x0, y0, z0, x1, y1, z1, solid):
    """Is any solid block inside the box (x0..x1, y0..y1, z0..z1)?"""
    for bx in range(math.floor(x0), math.floor(x1 - 1e-7) + 1):
        for by in range(math.floor(y0), math.floor(y1 - 1e-7) + 1):
            for bz in range(math.floor(z0), math.floor(z1 - 1e-7) + 1):
                bid = world.get(bx, by, bz)
                if solid[bid]:
                    h = heights(bid)
                    if h >= 1.0 or z0 < bz + h:
                        return True
    return False


def touching(world, s, table, tall=TALL):
    """Is the box in any block that table says (water, a ladder)?"""
    x0, y0 = s["x"] - HALF, s["y"] - HALF
    for bx in range(math.floor(x0), math.floor(s["x"] + HALF - 1e-7) + 1):
        for by in range(math.floor(y0), math.floor(s["y"] + HALF - 1e-7) + 1):
            for bz in range(math.floor(s["z"] + 0.1), math.floor(s["z"] + tall * 0.6) + 1):
                if table[world.get(bx, by, bz)]:
                    return True
    return False


def move_axis(world, s, axis, delta, tall, solid, step_up=False):
    """Move the box along one axis by delta, stopped at the first solid block. Returns True if it was stopped.
    Going down, a stopped box stands on the top of what it landed on (a slab's top is half way up). step_up: across
    and along, a box on the ground walks up onto a step or a Recharge Pod (about half a block) without jumping."""
    if delta == 0:
        return False
    x, y, z = s["x"], s["y"], s["z"]
    if axis == 2:
        nz = z + delta
        if not blocked(world, x - HALF, y - HALF, nz, x + HALF, y + HALF, nz + tall, solid):
            s["z"] = nz
            return False
        if delta < 0:
            best = None
            for bx in range(math.floor(x - HALF), math.floor(x + HALF - 1e-7) + 1):
                for by in range(math.floor(y - HALF), math.floor(y + HALF - 1e-7) + 1):
                    for bz in range(math.floor(z + 1e-6), math.floor(nz) - 1, -1):
                        bid = world.get(bx, by, bz)
                        if solid[bid]:
                            top = bz + heights(bid)
                            if top <= z + 1e-6:
                                best = top if best is None else max(best, top)
                            break
            if best is not None and best >= nz - 1e-6:
                s["z"] = best
        return True
    key = "x" if axis == 0 else "y"
    n = s[key] + delta
    bx0, by0 = (n - HALF, y - HALF) if axis == 0 else (x - HALF, n - HALF)
    if not blocked(world, bx0, by0, z + 1e-4, bx0 + 2 * HALF, by0 + 2 * HALF, z + tall, solid):
        s[key] = n
        return False
    if step_up:
        for lift in (0.5, 0.6):
            if not blocked(world, bx0, by0, z + lift, bx0 + 2 * HALF, by0 + 2 * HALF, z + lift + tall, solid) and                     blocked(world, bx0, by0, z + lift - 0.07, bx0 + 2 * HALF, by0 + 2 * HALF, z + lift, solid):
                s[key] = n
                s["z"] = z + lift
                return False
    return True


def on_ground(world, s, solid):
    return blocked(world, s["x"] - HALF, s["y"] - HALF, s["z"] - 0.02, s["x"] + HALF, s["y"] + HALF, s["z"], solid)


def step_player(s, inp, dt, world, creative=False):
    """One step of a player (or a walking creature): s is changed and returned."""
    solid, liquid, climb = tables()
    mx, my, buttons = inp
    n = dict(s)
    flags = n["flags"]
    flying = creative and bool(buttons & FLY_B)
    careful = bool(buttons & CAREFUL_B) and not flying
    sprint = bool(buttons & SPRINT_B) and not careful
    tall = CAREFUL_TALL if careful else TALL
    in_water = touching(world, n, liquid, tall)
    on_ladder = touching(world, n, climb, tall)
    length = math.hypot(mx, my)
    if length > 1:
        mx, my = mx / length, my / length
    if flying:
        speed = FLY_FAST if sprint else FLY_SPEED
    elif in_water:
        speed = SWIM
    else:
        speed = SPRINT if sprint else CAREFUL if careful else WALK
    ground = bool(flags & F_GROUND)
    k = 22.0 if (ground or flying) else 5.0 if not in_water else 8.0
    f = 1 - math.exp(-k * dt)
    n["vx"] += (mx * speed - n["vx"]) * f
    n["vy"] += (my * speed - n["vy"]) * f
    if flying:
        want = (FLY_SPEED if buttons & JUMP_B else 0.0) - (FLY_SPEED if buttons & CAREFUL_B else 0.0)
        n["vz"] += (want - n["vz"]) * (1 - math.exp(-12 * dt))
    elif in_water:
        n["vz"] = SWIM_UP if buttons & JUMP_B else max(n["vz"] - GRAVITY * 0.2 * dt, -SWIM_SINK)
    elif on_ladder:
        n["vz"] = CLIMB if (buttons & JUMP_B or length > 0.1) else max(n["vz"] - GRAVITY * dt, -CLIMB)
        if careful:
            n["vz"] = max(0.0, n["vz"])
    else:
        if ground and buttons & JUMP_B:
            n["vz"] = JUMP
        n["vz"] = max(-TERMINAL, n["vz"] - GRAVITY * dt)
    # move: up or down first, then across and along (Careful mode keeps you on the edge you are on)
    z_before = n["z"]
    stopped_z = move_axis(world, n, 2, n["vz"] * dt, tall, solid)
    if stopped_z:
        n["vz"] = 0.0
    for axis, key in ((0, "vx"), (1, "vy")):
        delta = n[key] * dt
        if careful and ground and delta:
            test = dict(n)
            test["x" if axis == 0 else "y"] += delta
            if not on_ground(world, test, solid):
                n[key] = 0.0
                continue
        if move_axis(world, n, axis, delta, tall, solid, step_up=ground and not flying):
            n[key] = 0.0
    now_ground = on_ground(world, n, solid) and n["vz"] <= 0.01
    # falling: how far since last standing (the server's damage is worked out from it on landing)
    if now_ground or in_water or on_ladder or flying:
        n["fall"] = n["fall"] if now_ground and not ground else 0.0
    else:
        n["fall"] = n["fall"] + max(0.0, z_before - n["z"])
    flags &= ~(F_GROUND | F_WATER | F_FLY | F_CAREFUL | F_CLIMB)
    flags |= (F_GROUND if now_ground else 0) | (F_WATER if in_water else 0) | (F_FLY if flying else 0) | \
        (F_CAREFUL if careful else 0) | (F_CLIMB if on_ladder else 0)
    n["flags"] = flags
    if n["z"] < -20:  # (fallen out of the world: back on top)
        n["z"] = float(world.Z)
        n["vz"] = 0.0
    return n


def compare(a, b):
    """How far apart two records are, for the prediction: metres (1.0 for any flag the step owns that differs)."""
    d = math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)
    if (a["flags"] ^ b["flags"]) & (F_GROUND | F_WATER | F_FLY | F_CAREFUL):
        d = max(d, 1.0)
    return d


# ---------- looking at a block ----------
def look_dir(yaw, pitch):
    """The way you look: yaw degrees from +x towards +y (0 east, 90 north), pitch up from level."""
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    return cy * cp, sy * cp, sp


def ray(world, ox, oy, oz, dx, dy, dz, reach):
    """The first block (not air, not water) along the ray from (ox, oy, oz) going (dx, dy, dz), within reach:
    ((x, y, z), (nx, ny, nz) the face it came in through, distance) or None. The grid's own walk (each block the
    ray passes through, in order)."""
    x, y, z = math.floor(ox), math.floor(oy), math.floor(oz)
    step = [1 if d > 0 else -1 for d in (dx, dy, dz)]
    t_max, t_delta = [], []
    for o, d, c in ((ox, dx, x), (oy, dy, y), (oz, dz, z)):
        if abs(d) < 1e-9:
            t_max.append(math.inf)
            t_delta.append(math.inf)
        else:
            nxt = c + (1 if d > 0 else 0)
            t_max.append((nxt - o) / d)
            t_delta.append(abs(1 / d))
    normal = (0, 0, 0)
    t = 0.0
    water = B.ID["water"]
    while t <= reach:
        bid = world.get(x, y, z)
        if bid and bid != water and B.BLOCKS[bid]["hard"] is not None or bid in (B.FLOOR, B.ID["glitch_rift"]):
            return (x, y, z), normal, t
        if bid and bid != water and B.BLOCKS[bid]["shape"] in ("cross", "crop", "torch", "ladder"):
            return (x, y, z), normal, t
        axis = min(range(3), key=lambda i: t_max[i])
        t = t_max[axis]
        t_max[axis] += t_delta[axis]
        if axis == 0:
            x += step[0]
            normal = (-step[0], 0, 0)
        elif axis == 1:
            y += step[1]
            normal = (0, -step[1], 0)
        else:
            z += step[2]
            normal = (0, 0, -step[2])
    return None


def player_box_hits(s, bx, by, bz, tall=TALL):
    """Would a block at (bx, by, bz) be inside the player? (You can't place a block where you stand.)"""
    return (bx < s["x"] + HALF and bx + 1 > s["x"] - HALF and by < s["y"] + HALF and by + 1 > s["y"] - HALF and
            bz < s["z"] + tall and bz + 1 > s["z"])


def eye(s):
    return s["x"], s["y"], s["z"] + (CAREFUL_EYE if s["flags"] & F_CAREFUL else EYE)
