"""Robot Lab's ultra arena (CHANGE 145): the floor plates, the cage, the lighting rig, the towers, the stands and their
crowd, the big screen and the battle scars, built from numbers alone, so the window (rw_gfx.py) and the page
(club-coders/web/make_models.py writes it to models/arena_ultra.json) draw the same arena. robot_models.py is its
robots; Kart Lab's kart_scenery.py did the same for its circuit.

Pure Python, no Panda3D (engine.model_kit is pure Python too). arena() returns what the page reads:

    {"version": 1,
     "materials": {name: material, ...}   how each material looks (see MATERIALS)
     "groups":    {name: [part, ...]}     the arena's parts, grouped by when they are drawn (see GROUPS)
     "shapes":    {name: [part, ...]}     things placed many times (fans, seats), each in its own frame: x forward,
                                          y left, z up, its feet at the origin
     "instances": {shape: [[x, y, z, h, s, r, g, b], ...]}
     "notes":     {...}}

    part: engine.model_kit.Part.packed() (model_kit says how to read the arrays), with "tint" (an instance's colour
          multiplies its colours) and "far" (outside the arena: no shadow) where they apply
    instance: the shape turned h degrees about z (anticlockwise, from +x), scaled by s, moved to (x, y, z); r, g, b
              multiplies its "tint" parts' colours (screen colours)

ultra draws the arena of the lower tiers (rw_gfx.ArenaVisual: the markings, every hazard and the user mods' items,
which move and change) with these in place of its floor, walls, towers, rig, stands, crowd and screen. Which groups
(GROUPS, WHEN): the floor matching the holes the user mods cut (floor_group), the cage and its hall floor or the open
edge's (No cage), the rig and the roof under the node the full arena camera hides, and the rest always. Everything is
decided here (fixed seeds, hash01), so the page places nothing itself. Nothing here is solid (the sim never reads a
picture), nothing stands inside the arena above its floor's markings, and nothing outside rises into the cameras'
views of it (rw_camera: the TV rail at 5.4 m, the centre camera 6.5 m up 13.5 m out): between the walls and the
stands only the posts (as the lower tiers'), the stands and their fans under 4.8 m (as the lower tiers' crowd), the
hall's walls 40 m out (past the farthest a camera goes) and its roof at 18.5 m (gfx_test.py checks these).

The frame is the game's: x, y on the floor, z up, metres; the arena's floor is z = 0 from -10 to 10.
"""
import math
import random

from engine import model_kit as mk
from engine.model_kit import Frame, Parts, hash01

VERSION = 1
ARENA = 20.0
H = ARENA / 2
# the holes in the floor (lab_sim.floor_holes: the drop zone and the floor flipper always, the spike and flame pits
# when those user mods are on; arena_test checks these are lab_sim's)
PIT = (3.2, 3.2, 3.0)
FLOOR_FLIPPER = (-3.5, -3.5)
SPIKE_PIT = (-3.5, 7.0, 2.4)
FLAME_PIT = (0.0, 0.0, 2.4)
SPIKES = (-H, -2.5, 2.5)  # the wall spikes' opening (west wall, from y to y): no signs there
GUTTER = 3.0              # No cage: the drop round the edge
PLATE = 2.0               # the floor plates' size

# each material: colour (a screen colour, times the vertex colours and the texture; None: the arena's wall colour,
# look["wall_colour"]), rough, metal, texture set (engine/assets/tex or shared-world-demo/assets/tex, the page's tex/),
# "emission" (linear light), "two_sided", "decal" (lying on the floor: drawn after it, a depth offset), "alpha"
# (see-through by its vertices' alpha: drawn after everything solid, no depth write), "flat" (casts no shadow)
MATERIALS = {
    "floor": {"colour": [1.0, 1.0, 1.0], "rough": 1.0, "metal": 1.0, "texture": "lab_floor", "flat": True},
    "wall": {"colour": None, "rough": 0.55, "metal": 0.25, "texture": "paint"},
    "steel": {"colour": [0.6, 0.61, 0.64], "rough": 0.45, "metal": 1.0, "texture": "steel"},
    "dark_steel": {"colour": [0.16, 0.16, 0.18], "rough": 0.5, "metal": 1.0, "texture": "steel"},
    "chrome": {"colour": [0.9, 0.9, 0.92], "rough": 0.12, "metal": 1.0, "texture": None},
    "rubber": {"colour": [0.06, 0.06, 0.065], "rough": 0.85, "metal": 0.0, "texture": None},
    "black": {"colour": [0.02, 0.02, 0.022], "rough": 0.9, "metal": 0.0, "texture": None},
    "concrete": {"colour": [0.62, 0.63, 0.67], "rough": 1.0, "metal": 0.0, "texture": "concrete"},
    "venue_floor": {"colour": [0.42, 0.43, 0.46], "rough": 0.7, "metal": 0.0, "texture": "concrete", "flat": True},
    "seat": {"colour": [1.0, 1.0, 1.0], "rough": 0.45, "metal": 0.0, "texture": None},
    "cloth": {"colour": [0.6, 0.6, 0.6], "rough": 0.9, "metal": 0.0, "texture": None},  # (dim: the hall is dark)
    "skin": {"colour": [0.62, 0.62, 0.62], "rough": 0.65, "metal": 0.0, "texture": None},
    "signs": {"colour": [1.0, 1.0, 1.0], "rough": 0.55, "metal": 0.0, "texture": "lab_signs"},
    "lamp": {"colour": [1.0, 1.0, 1.0], "rough": 0.3, "metal": 0.0, "texture": None, "emission": [6.0, 5.6, 5.0]},
    "led": {"colour": [0.0, 0.0, 0.0], "rough": 0.3, "metal": 0.0, "texture": None, "emission": [0.35, 0.9, 3.2]},
    "screen": {"colour": [0.02, 0.025, 0.03], "rough": 0.08, "metal": 0.0, "texture": None},
    "hazard": {"colour": [1.0, 1.0, 1.0], "rough": 0.5, "metal": 0.0, "texture": "hazard"},
    "scorch": {"colour": [0.035, 0.03, 0.028], "rough": 0.85, "metal": 0.0, "texture": None, "decal": True, "alpha": True,
               "flat": True},
}

# the boards round the arena and on the stands: one row each of the "lab_signs" texture, top row first (rw_gfx draws
# the picture; never a real brand). (text, background, lettering), screen colours
SIGNS = [("ROBOT LAB", (0.84, 0.14, 0.12), (1.0, 1.0, 1.0)),
         ("CLUB CODERS", (0.1, 0.36, 0.86), (1.0, 1.0, 1.0)),
         ("KART LAB", (0.98, 0.78, 0.1), (0.08, 0.08, 0.1)),
         ("FIGHT LAB", (0.42, 0.18, 0.68), (1.0, 1.0, 1.0)),
         ('print("ACTIVATE!")', (0.07, 0.09, 0.11), (0.35, 0.95, 0.45)),
         ("BUILD  CODE  BATTLE", (0.08, 0.56, 0.3), (1.0, 1.0, 1.0)),
         ("if flipped: self_right()", (0.17, 0.17, 0.19), (1.0, 0.62, 0.15)),
         ("STAY BEHIND THE SCREENS", (0.95, 0.75, 0.08), (0.06, 0.06, 0.07))]


def sign_v(row):
    """The texture's v from and to for a row of SIGNS (v 1 is the picture's top)."""
    n = len(SIGNS)
    return 1.0 - (row + 1) / n + 0.004, 1.0 - row / n - 0.004


def shirt(k):
    """A fan's shirt colour (screen colours): the clubs' colours and a few others."""
    return [(0.84, 0.14, 0.12), (0.1, 0.36, 0.86), (0.98, 0.78, 0.1), (0.42, 0.18, 0.68), (0.9, 0.9, 0.9),
            (0.15, 0.15, 0.18), (0.95, 0.5, 0.1), (0.2, 0.6, 0.3)][k % 8]


# ---------- the holes and the floor ----------
def floor_holes(spike_pit=False, flame_pit=False):
    """lab_sim.floor_holes for the user mods that cut the floor: (x0, y0, x1, y1)."""
    px, py, ps = PIT
    fx, fy = FLOOR_FLIPPER
    holes = [(px - ps / 2, py - ps / 2, px + ps / 2, py + ps / 2), (fx - 1.5, fy - 1.0, fx + 1.5, fy + 1.0)]
    for on, (kx, ky, ks) in ((spike_pit, SPIKE_PIT), (flame_pit, FLAME_PIT)):
        if on:
            holes.append((kx - ks / 2, ky - ks / 2, kx + ks / 2, ky + ks / 2))
    return holes


def floor_rects(holes):
    """lab_sim.floor_rects: the floor as rectangles with the holes cut out."""
    rects = [(-H, -H, H, H)]
    for hx0, hy0, hx1, hy1 in holes:
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


def floor_group(spike_pit=False, flame_pit=False):
    """The name of the floor group for the user mods that cut the floor."""
    return "floor" + ("_spike_pit" if spike_pit else "") + ("_flame_pit" if flame_pit else "")


def floor(spike_pit=False, flame_pit=False):
    """The steel floor: a plate every PLATE metres, each cut where a hole is, its top edges chamfered (so every seam
    shows), its texture the plate's own (u, v 0 to 1 across a whole plate, turned and flipped plate by plate so no two
    neighbours match), with a bolt in each corner a whole plate has."""
    p = Parts()
    plate, bolts = p.get("floor"), p.get("chrome")
    n = int(ARENA / PLATE)
    for x0, y0, x1, y1 in floor_rects(floor_holes(spike_pit, flame_pit)):
        for i in range(n):
            for j in range(n):
                cx0, cy0 = -H + i * PLATE, -H + j * PLATE
                a0, b0, a1, b1 = max(x0, cx0), max(y0, cy0), min(x1, cx0 + PLATE), min(y1, cy0 + PLATE)
                if a1 - a0 < 1e-6 or b1 - b0 < 1e-6:
                    continue
                turn = int(hash01(i, j, 7) * 8)
                start = len(plate.p)
                mk.rounded_box(plate, Frame(((a0 + a1) / 2, (b0 + b1) / 2, -0.25)), ((a1 - a0) / 2, (b1 - b0) / 2, 0.25),
                               0.006, steps=1, skip=("-z",))
                for k in range(start, len(plate.p)):  # the plate's own texture: its corner (cx0, cy0) at u, v 0
                    x, y = plate.p[k][0], plate.p[k][1]
                    u, v = (x - cx0) / PLATE, (y - cy0) / PLATE
                    if turn & 1:
                        u, v = v, u
                    if turn & 2:
                        u = 1 - u
                    if turn & 4:
                        v = 1 - v
                    plate.uv[k] = (u, v)
                for bx, by in ((cx0 + 0.09, cy0 + 0.09), (cx0 + PLATE - 0.09, cy0 + 0.09), (cx0 + 0.09, cy0 + PLATE - 0.09),
                               (cx0 + PLATE - 0.09, cy0 + PLATE - 0.09)):
                    if a0 + 0.03 < bx < a1 - 0.03 and b0 + 0.03 < by < b1 - 0.03:
                        mk.lathe(bolts, Frame((bx, by, 0.0)), [(0.0, 0.004), (0.014, 0.003), (0.019, 0.0)], seg=8)
    return p.all()


def scars():
    """Battle scars on the floor (decals, see-through at their edges): scorch marks, the skids of tyres turning
    hard, and gouges from weapons. Placed by a fixed seed, never over a hole (any user mod's)."""
    rnd = random.Random(145)
    holes = floor_holes(True, True)
    clear = lambda x, y, m: all(not (hx0 - m < x < hx1 + m and hy0 - m < y < hy1 + m) for hx0, hy0, hx1, hy1 in holes)  # noqa: E731
    p = Parts()
    decal = p.get("scorch")
    z = 0.0015
    placed = 0
    while placed < 14:  # scorch marks: a blotchy disc, dark in the middle, fading out
        x, y = rnd.uniform(-8.5, 8.5), rnd.uniform(-8.5, 8.5)
        r = rnd.uniform(0.35, 0.9)
        if not clear(x, y, r):
            continue
        placed += 1
        seg = 18
        mid = decal.vertex((x, y, z), (0, 0, 1), (0.5, 0.5), a=rnd.uniform(0.55, 0.8))
        ring1 = [decal.vertex((x + r * 0.55 * math.cos(2 * math.pi * k / seg), y + r * 0.55 * math.sin(2 * math.pi * k / seg), z),
                              (0, 0, 1), a=rnd.uniform(0.3, 0.55)) for k in range(seg)]
        ring2 = []
        for k in range(seg):
            rr = r * (0.8 + 0.4 * rnd.random())
            ring2.append(decal.vertex((x + rr * math.cos(2 * math.pi * k / seg), y + rr * math.sin(2 * math.pi * k / seg), z),
                                      (0, 0, 1), a=0.0))
        for k in range(seg):
            q = (k + 1) % seg
            decal.tri(mid, ring1[k], ring1[q])
            decal.tri(ring1[k], ring2[k], ring2[q])
            decal.tri(ring1[k], ring2[q], ring1[q])
    placed = 0
    while placed < 22:  # tyre skids: pairs of curved dark bands
        x, y = rnd.uniform(-8.5, 8.5), rnd.uniform(-8.5, 8.5)
        if not clear(x, y, 2.5):
            continue
        placed += 1
        h0, bend, length = rnd.uniform(0, 2 * math.pi), rnd.uniform(-0.6, 0.6), rnd.uniform(1.5, 3.5)
        alpha = rnd.uniform(0.25, 0.5)
        for side in (-0.55, 0.55):
            rows = []
            steps = 10
            for k in range(steps + 1):
                t = k / steps
                hh = h0 + bend * t
                cx = x + math.cos(h0 + bend * t / 2) * length * t
                cy = y + math.sin(h0 + bend * t / 2) * length * t
                lx, ly = -math.sin(hh), math.cos(hh)
                fade = alpha * math.sin(math.pi * t) ** 0.6
                rows.append([decal.vertex((cx + lx * (side + w), cy + ly * (side + w), z + 0.0002), (0, 0, 1), a=fade * (1 - abs(w) / 0.09))
                             for w in (-0.09, 0.0, 0.09)])
            for k in range(steps):
                for c in range(2):
                    decal.tri(rows[k][c], rows[k + 1][c], rows[k + 1][c + 1])
                    decal.tri(rows[k][c], rows[k + 1][c + 1], rows[k][c + 1])
    placed = 0
    while placed < 16:  # gouges: short thin dark slashes
        x, y = rnd.uniform(-9, 9), rnd.uniform(-9, 9)
        if not clear(x, y, 0.6):
            continue
        placed += 1
        a, L = rnd.uniform(0, math.pi), rnd.uniform(0.25, 0.6)
        dx, dy = math.cos(a) * L / 2, math.sin(a) * L / 2
        nx, ny = -math.sin(a) * 0.012, math.cos(a) * 0.012
        v = [decal.vertex((x - dx, y - dy, z + 0.0004), (0, 0, 1), a=0.0),
             decal.vertex((x + nx, y + ny, z + 0.0004), (0, 0, 1), a=0.85),
             decal.vertex((x + dx, y + dy, z + 0.0004), (0, 0, 1), a=0.0),
             decal.vertex((x - nx, y - ny, z + 0.0004), (0, 0, 1), a=0.85)]
        decal.tri(v[0], v[1], v[2])
        decal.tri(v[0], v[2], v[3])
    return p.all()


# ---------- the cage ----------
def walls():
    """The kick walls (where the lower tiers' walls are: 0.5 m thick outside the floor, 1.2 m high) in the arena's
    wall colour, with a bolted panel between each pair of posts on the inside, boards with the club's names on
    them, a rubber skid strip along the foot, a round steel rail along the top, and posts every 2 m up to the
    screens' top with base flanges, caps and brackets (no bar along the screens' top: the cameras look over it)."""
    p = Parts()
    wall, steel, chrome = p.get("wall"), p.get("steel"), p.get("chrome")
    edge = H + 0.25
    sides = [((0, edge), (1, 0), (0, 1)), ((0, -edge), (-1, 0), (0, -1)), ((edge, 0), (0, -1), (1, 0)),
             ((-edge, 0), (0, 1), (-1, 0))]  # (the wall's middle, along it, out of the arena)
    sign = 0
    for (mx, my), (ax, ay), (ox, oy) in sides:
        f = Frame((mx, my, 0.0), (ax, ay, 0), (ox, oy, 0), (0, 0, 1))  # x along the wall, y out of the arena
        long = H + 0.5 if ay == 0 else H
        # the wall's own face 2.5 cm back from the floor's edge, so its panels, bolts and boards come no further than
        # the edge (where the physics' wall is: a robot against the wall touches them, never sinks into them)
        mk.rounded_box(wall, f.at(0, 0.0125, 0.6), (long, 0.2375, 0.6), 0.03, steps=2, inner=4, metres=2.0)
        inner = Frame(f.p(0, -0.225, 0), mk.mul(f.x, -1), mk.mul(f.y, -1), f.z)  # x along, y into the arena
        for k in range(10):
            c = -9 + 2 * k
            if (ox, oy) == (-1, 0) and abs(c) < 4:  # (the wall spikes come out here: a hazard plate, no panel)
                continue
            mk.rounded_box(wall, inner.at(c, 0.008, 0.62), (0.94, 0.008, 0.5), 0.006, steps=2, metres=2.0,
                           c=(0.82, 0.82, 0.82))
            for bx in (-0.86, -0.43, 0.0, 0.43, 0.86):
                for bz in (0.17, 1.07):
                    mk.bolt(chrome, Frame(inner.p(c + bx, 0.016, bz), inner.x, mk.mul(inner.z, -1), inner.y), 0.012, 0.006)
            if k % 3 == 1 or (k % 3 == 2 and ay != 0):  # boards with the club's names on some panels
                row = sign % len(SIGNS)
                sign += 1
                v0, v1 = sign_v(row)
                pts = [inner.p(c + 0.82, 0.0165, 0.45), inner.p(c - 0.82, 0.0165, 0.45), inner.p(c - 0.82, 0.0165, 0.85),
                       inner.p(c + 0.82, 0.0165, 0.85)]  # (inner.x runs to the left of someone in the arena)
                p.get("signs").quad(pts, inner.y, [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
        mk.rounded_box(p.get("rubber"), inner.at(0, 0.012, 0.05), (long - 0.02, 0.012, 0.05), 0.008, steps=1, inner=4)
        mk.rod(steel, f.p(-long, 0, 1.26), f.p(long, 0, 1.26), 0.065, seg=14)
        for k in range(-5, 6):
            post = f.at(2 * k, 0, 1.2)
            mk.lathe(steel, post, [(0.0, 0.07), (0.12, 0.07), (0.12, 0.04), (0.075, 0.03), (0.075, 0.0)], seg=16)
            mk.lathe(steel, post, [(0.07, 3.38), (0.07, 0.05)], seg=14)
            mk.lathe(chrome, post, [(0.0, 3.41), (0.05, 3.405), (0.075, 3.385), (0.075, 3.37), (0.07, 3.36)], seg=14)
            for bz in (1.0, 2.2):
                mk.box(p.get("dark_steel"), Frame(post.p(0, 0, bz), f.x, f.y, f.z), -0.1, 0.1, -0.035, 0.035, -0.04, 0.04)
    return p.all()


# ---------- the towers and the rig ----------
def lamp_can(part_body, part_lens, f, r=0.22, depth=0.45):
    """A theatre lamp: a dark can along f's z (its lens at the front, +z), with a yoke."""
    mk.lathe(part_body, f, [(r * 0.75, depth), (r, depth - 0.04), (r, 0.06), (r * 0.6, 0.0), (0.0, 0.0)], seg=16)
    mk.disc(part_lens, f, r * 0.82, 0.0, seg=16, z=depth + 0.002)
    mk.lathe(part_body, f, [(r * 0.86, depth + 0.06), (r * 1.02, depth + 0.02), (r * 1.02, depth)], seg=16)


def truss(part, a, b, w=0.3, bay=0.6, r=0.035, lace=0.016):
    """A box truss from a to b (w square): four round chords and zigzag lacing on each side."""
    ahead = mk.norm(mk.sub(b, a))
    side = mk.norm(mk.cross(ahead, (0, 0, 1) if abs(ahead[2]) < 0.9 else (1, 0, 0)))
    up = mk.cross(side, ahead)
    L = math.dist(a, b)
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    at_ = lambda t, cx, cy: mk.add(mk.add(a, mk.mul(ahead, t)), mk.add(mk.mul(side, cx * w / 2), mk.mul(up, cy * w / 2)))  # noqa: E731
    for cx, cy in corners:
        mk.rod(part, at_(0, cx, cy), at_(L, cx, cy), r, seg=8)
    bays = max(1, int(round(L / bay)))
    for k in range(bays):
        t0, t1 = L * k / bays, L * (k + 1) / bays
        for c in range(4):
            (ax_, ay_), (bx_, by_) = corners[c], corners[(c + 1) % 4]
            if k % 2:
                mk.rod(part, at_(t0, ax_, ay_), at_(t1, bx_, by_), lace, seg=5)
            else:
                mk.rod(part, at_(t0, bx_, by_), at_(t1, ax_, ay_), lace, seg=5)


def towers():
    """The four corner towers (where the lower tiers' are: their spotlights hang there): lattice masts on base
    plates, each topped by a head with four lamps aimed at the middle of the arena."""
    p = Parts()
    steel, dark = p.get("dark_steel"), p.get("dark_steel")
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * 12.5, sy * 12.5
            mk.box(steel, Frame((x, y, 0)), -0.5, 0.5, -0.5, 0.5, 0.0, 0.05)
            truss(steel, (x, y, 0.05), (x, y, 8.3), w=0.5, bay=0.7, r=0.045, lace=0.02)
            head = Frame((x, y, 8.6)).turned("z", math.degrees(math.atan2(-y, -x)))
            mk.rounded_box(dark, head, (0.4, 0.55, 0.3), 0.06, steps=2)
            for k, (dy, dz) in enumerate(((-0.27, 0.12), (0.27, 0.12), (-0.27, -0.14), (0.27, -0.14))):
                aim = mk.norm(mk.sub((sx * 2.0, sy * 2.0, 0.0), head.p(0.45, dy, dz)))
                side = mk.norm(mk.cross(aim, (0, 0, 1)))
                f = Frame(head.p(0.42, dy, dz), side, mk.cross(aim, side), aim)
                lamp_can(p.get("black"), p.get("lamp"), f, 0.13, 0.28)
    return p.all()


RIG_Z = 9.2


def rig():
    """The lighting rig over the arena (its own node, "lighting_rig": the full arena camera looks down past it and
    hides it): box trusses round the edge and across, lamps hanging under them and cable runs."""
    p = Parts()
    steel = p.get("steel")
    for k in (-1, 1):
        truss(steel, (-13.0, k * 12.5, RIG_Z), (13.0, k * 12.5, RIG_Z))
        truss(steel, (k * 12.5, -12.35, RIG_Z), (k * 12.5, 12.35, RIG_Z))
    for i in range(-3, 4):
        truss(steel, (i * 3.2, -12.35, RIG_Z + 0.1), (i * 3.2, 12.35, RIG_Z + 0.1), w=0.24, bay=0.5, r=0.028, lace=0.013)
        for j in (-6, -2, 2, 6):
            f = Frame((i * 3.2, j, RIG_Z - 0.12), (1, 0, 0), (0, -1, 0), (0, 0, -1))  # (facing down)
            lamp_can(p.get("black"), p.get("lamp"), f, 0.18, 0.3)
            mk.box(p.get("dark_steel"), Frame((i * 3.2, j, RIG_Z - 0.06)), -0.24, 0.24, -0.03, 0.03, -0.12, 0.0)
        mk.tube(p.get("rubber"), [(i * 3.2 + 0.18, -12.3, RIG_Z + 0.02), (i * 3.2 + 0.18, 0.0, RIG_Z - 0.06),
                                  (i * 3.2 + 0.18, 12.3, RIG_Z + 0.02)], 0.022, seg=6, caps=False)
    return p.all()


# ---------- the venue ----------
def venue_floor(cage=True):
    """The hall's floor round the arena (out to 30 m), from the walls' outside or, with No cage, from the gutter's
    outer edge."""
    p = Parts(far=True)
    e = H + (0.5 if cage else GUTTER)
    far = 30.0
    for x0, y0, x1, y1 in ((-H - far, e, H + far, H + far), (-H - far, -H - far, H + far, -e), (e, -e, H + far, e),
                           (-H - far, -e, -e, e)):
        mk.box(p.get("venue_floor"), Frame(), x0, x1, y0, y1, -0.05, 0.0, 3.0, skip=("-z",))
    return p.all()


STAND_ROWS = 4
ROW_DEEP = 1.3
BACK_WALL = 4.7  # (the stands' back wall: the centre camera, zoomed right out and tilted down, still sees over it)
ROW_RISE = 0.95  # (the top row's fans' heads under 4.8 m, as the lower tiers' crowd)


def stands():
    """The stands on every side (where the lower tiers' are: 13.2 m out, four rows): concrete tiers with treads and
    risers, aisles every 6 m, end walls, a back wall up to 4.5 m with boards above the top row, a railing and
    a lit strip along the front, and the club's boards on the front wall. The seats and fans are shapes placed by
    stand_instances()."""
    p = Parts(far=True)
    concrete, steel = p.get("concrete"), p.get("steel")
    sign = 3
    for side in range(4):
        f = Frame((0, 0, 0)).turned("z", 90 * side)  # (side 0 north: y out of the arena)
        d0 = H + 2.55
        span = H + 3.0
        for row in range(STAND_ROWS):
            y0, y1 = d0 + row * ROW_DEEP, d0 + (row + 1) * ROW_DEEP
            top = 0.7 + row * ROW_RISE
            mk.box(concrete, f, -span, span, y0, y1, 0.0, top, 3.0, skip=("-z",))
            mk.box(p.get("dark_steel"), f, -span, span, y0, y0 + 0.06, top, top + 0.025)  # the tread's nosing
        back = d0 + STAND_ROWS * ROW_DEEP
        mk.box(concrete, f, -span - 0.3, span + 0.3, back, back + 0.35, 0.0, BACK_WALL, 3.0)
        for x in (-span - 0.15, span + 0.15):  # the end walls
            mk.box(concrete, Frame(f.p(x, 0, 0), f.x, f.y, f.z), -0.15, 0.15, d0, back, 0.0, 0.7 + STAND_ROWS * ROW_RISE, 3.0)
        for k in range(-1, 2):  # the boards along the back wall, above the top row
            row = sign % len(SIGNS)
            sign += 1
            v0, v1 = sign_v(row)
            c = k * 7.5
            pts = [f.p(c - 3.2, back - 0.01, BACK_WALL - 0.7), f.p(c + 3.2, back - 0.01, BACK_WALL - 0.7),
                   f.p(c + 3.2, back - 0.01, BACK_WALL - 0.08), f.p(c - 3.2, back - 0.01, BACK_WALL - 0.08)]
            p.get("signs").quad(pts, f.v(0, -1, 0), [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
        # the front: the wall's boards, a lit strip and a railing
        for k in range(-4, 5):
            row = (k + side * 3) % len(SIGNS)
            v0, v1 = sign_v(row)
            c = k * 2.9
            pts = [f.p(c - 1.35, d0 - 0.01, 0.12), f.p(c + 1.35, d0 - 0.01, 0.12), f.p(c + 1.35, d0 - 0.01, 0.52),
                   f.p(c - 1.35, d0 - 0.01, 0.52)]
            p.get("signs").quad(pts, f.v(0, -1, 0), [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
        mk.box(p.get("led"), f, -span, span, d0 - 0.03, d0, 0.6, 0.64)
        for x in [-span + 0.1 + 1.5 * k for k in range(int(2 * span / 1.5) + 1)]:
            mk.rod(steel, f.p(x, d0 + 0.08, 0.7), f.p(x, d0 + 0.08, 1.75), 0.022, seg=6)
        mk.rod(steel, f.p(-span, d0 + 0.08, 1.75), f.p(span, d0 + 0.08, 1.75), 0.03, seg=8)
        mk.rod(steel, f.p(-span, d0 + 0.08, 1.25), f.p(span, d0 + 0.08, 1.25), 0.016, seg=6)
    # the corners: flight cases and the judges' desk
    rnd = random.Random(11)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for k in range(3):
                x, y = sx * (14.6 + rnd.uniform(0, 2.2)), sy * (14.2 + k * 1.1)
                w, dd, hh = rnd.uniform(0.4, 0.6), rnd.uniform(0.3, 0.45), rnd.uniform(0.35, 0.8)
                f = Frame((x, y, 0)).turned("z", rnd.uniform(-20, 20))
                mk.rounded_box(p.get("black"), f.at(0, 0, hh), (w, dd, hh), 0.03, steps=1)
                mk.box(p.get("chrome"), f, -w - 0.005, w + 0.005, -dd - 0.005, dd + 0.005, hh * 1.4, hh * 1.4 + 0.03)
    desk = Frame((-15.5, -15.0, 0)).turned("z", 45)
    mk.rounded_box(p.get("dark_steel"), desk.at(0, 0, 0.45), (1.4, 0.4, 0.45), 0.04, steps=2)
    mk.box(p.get("screen"), Frame(desk.p(0, -0.25, 0.93), desk.x, desk.y, desk.z).turned("x", -25), -1.0, 1.0, -0.01, 0.01, 0.0, 0.3)
    return p.all()


def big_screen():
    """The big screen over the north stand (where the lower tiers' is: the score is written on it), in a dark
    housing with a bezel, standing on struts on the stand's back wall."""
    p = Parts(far=True)
    f = Frame((0, H + 7.5, 6.5))
    mk.rounded_box(p.get("dark_steel"), f, (4.2, 0.3, 1.55), 0.08, steps=2, inner=3)
    mk.box(p.get("screen"), f, -4.0, 4.0, -0.31, -0.29, -1.38, 1.38)
    mk.box(p.get("led"), f, -4.05, 4.05, -0.312, -0.3, -1.45, -1.41)
    back = H + 2.55 + STAND_ROWS * ROW_DEEP
    for x in (-3.0, -1.0, 1.0, 3.0):
        mk.rod(p.get("steel"), (x, back + 0.17, BACK_WALL), (x, H + 7.6, 4.95), 0.06, seg=10)
    return p.all()


def hall():
    """The hall's walls at the floor's edge, 40 m out (beyond where any camera goes: the third person view at its
    farthest is 36 m out), up to the roof: dark concrete with tall lit strips and the club's banners high up."""
    p = Parts(far=True)
    wall_at, high = H + 30.0, ROOF_Z
    sign = 1
    for side in range(4):
        f = Frame((0, 0, 0)).turned("z", 90 * side)
        mk.box(p.get("venue_floor"), f, -wall_at, wall_at, wall_at, wall_at + 0.5, 0.0, high, 4.0, skip=("-z",))
        for k in range(-4, 5):
            x = k * 8.0
            mk.box(p.get("led"), f, x - 0.08, x + 0.08, wall_at - 0.05, wall_at, 0.5, high - 1.5)
        for k in (-1, 1):
            row = sign % len(SIGNS)
            sign += 3
            v0, v1 = sign_v(row)
            c = k * 16.0
            pts = [f.p(c - 6.0, wall_at - 0.06, 7.0), f.p(c + 6.0, wall_at - 0.06, 7.0), f.p(c + 6.0, wall_at - 0.06, 8.5),
                   f.p(c - 6.0, wall_at - 0.06, 8.5)]
            p.get("signs").quad(pts, f.v(0, -1, 0), [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
    return p.all()


ROOF_Z = 18.5  # (over every camera but the full arena's, which hides the rig and the roof with it)


def roof():
    """The hall's roof (under the lighting rig's node: the full arena camera, high over everything, hides it): dark
    panels, deep trusses across every 8 m and a row of lamps under each."""
    p = Parts(far=True)
    span = H + 30.0
    mk.box(p.get("venue_floor"), Frame(), -span, span, -span, span, ROOF_Z, ROOF_Z + 0.3, 6.0, skip=("+z",))
    for k in range(-4, 5):
        y = k * 8.0
        truss(p.get("dark_steel"), (-span, y, ROOF_Z - 1.2), (span, y, ROOF_Z - 1.2), w=1.0, bay=2.5, r=0.08, lace=0.04)
        for x in range(-24, 25, 8):
            mk.box(p.get("lamp"), Frame((x, y, ROOF_Z - 1.75)), -0.5, 0.5, -0.2, 0.2, -0.04, 0.0)
    return p.all()


# ---------- the crowd ----------
def fan(skin, hair, pose, seed):
    """A fan sitting or standing (pose 0: arms down, 1: one arm waving, 2: both arms up), facing +x: legs and body in
    their shirt's colour (the instance's tint), arms, a head with hair. About 1.5 m standing."""
    rnd = random.Random(seed)
    body, skin_p, hair_p = mk.Part("shirt", "cloth", tint=True, far=True), mk.Part("skin", "skin", far=True), \
        mk.Part("hair", "cloth", far=True)
    trousers = (0.25, 0.27, 0.33)
    for y in (0.11, -0.11):
        mk.box(body, Frame((0, y, 0)), -0.08, 0.08, -0.07, 0.07, 0.0, 0.86, c=trousers, skip=("-z",))
    mk.superellipsoid(body, Frame((0, 0, 1.08)), (0.13, 0.22, 0.27), e=3.0, seg=8, rings=6)
    for side in (1, -1):
        up = pose == 2 or (pose == 1 and side == 1)
        shoulder = (0.0, side * 0.22, 1.27)
        hand = (0.08, side * 0.32, 1.9 + rnd.uniform(-0.05, 0.08)) if up else (0.06, side * 0.27, 0.82)
        mk.tube(body, [shoulder, mk.mix(shoulder, hand, 0.45)], 0.055, seg=5, caps=False)
        mk.tube(skin_p, [mk.mix(shoulder, hand, 0.45), hand], 0.045, seg=5)
    mk.superellipsoid(skin_p, Frame((0.01, 0, 1.52)), (0.1, 0.09, 0.12), e=2.2, seg=8, rings=6)
    mk.superellipsoid(hair_p, Frame((-0.015, 0, 1.585)), (0.1, 0.095, 0.075), e=2.4, seg=8, rings=4)
    for part, c in ((skin_p, skin), (hair_p, hair)):
        part.c = [c] * len(part.p)
    return [body, skin_p, hair_p]


def seat():
    """A stadium seat, facing +x: a moulded shell (tinted) on a dark bracket."""
    shell, frame = mk.Part("seat", "seat", tint=True, far=True), mk.Part("seat frame", "dark_steel", far=True)
    mk.box(shell, Frame((0.02, 0, 0.42)), -0.2, 0.2, -0.22, 0.22, -0.03, 0.03)
    mk.box(shell, Frame((-0.18, 0, 0.66)).turned("y", -12), -0.03, 0.03, -0.22, 0.22, -0.22, 0.22)
    mk.box(frame, Frame((0, 0, 0)), -0.04, 0.04, -0.03, 0.03, 0.0, 0.4)
    return [shell, frame]


SKINS = [(0.92, 0.74, 0.62), (0.8, 0.6, 0.45), (0.6, 0.42, 0.3), (0.42, 0.28, 0.2)]
HAIRS = [(0.08, 0.06, 0.05), (0.35, 0.22, 0.12), (0.75, 0.6, 0.35), (0.5, 0.15, 0.08)]


def shapes():
    out = {"seat": seat()}
    for k in range(8):
        out[f"fan{k}"] = fan(SKINS[k % 4], HAIRS[(k * 3 + 1) % 4], (0, 0, 1, 0, 2, 0, 1, 0)[k], 40 + k)
    return out


def stand_instances():
    """Every seat and fan: [x, y, z, h, s, r, g, b] per shape. A seat every 0.62 m along each row but the aisles; a fan in
    most seats (standing in the front rows, mostly sitting further back, sitting with their arms down on the top row),
    in their shirts' colours."""
    inst = {}
    rnd = random.Random(7)
    seat_cols = [(0.1, 0.36, 0.86), (0.84, 0.14, 0.12)]
    for side in range(4):
        f = Frame((0, 0, 0)).turned("z", 90 * side)
        facing = 90 * side - 90  # (the shapes face +x: turned to face the arena)
        d0 = H + 2.55
        for row in range(STAND_ROWS):
            top = 0.7 + row * ROW_RISE
            y = d0 + row * ROW_DEEP + 0.75
            x = -H - 2.7
            while x <= H + 2.7:
                if min(abs(x - a) for a in (-6.0, 0.0, 6.0)) < 0.6:  # (the aisles)
                    x += 0.62
                    continue
                px, py, pz = f.p(x, y, top)
                sc = seat_cols[(row + side) % 2]
                inst.setdefault("seat", []).append([round(px, 3), round(py, 3), round(pz, 3), facing, 1.0, *sc])
                if rnd.random() < 0.82:
                    k = rnd.randrange(8)
                    standing = row < 2 or (row < STAND_ROWS - 1 and rnd.random() < 0.25)
                    if row == STAND_ROWS - 1:  # (the top row sits, arms down: under the lower tiers' crowd's 4.8 m)
                        k = (0, 1, 3, 5, 7)[k % 5]
                    fx, fy, fz = f.p(x + rnd.uniform(-0.05, 0.05), y - (0.25 if standing else -0.05), top + (0.0 if standing else -0.38))
                    inst.setdefault(f"fan{k}", []).append([round(fx, 3), round(fy, 3), round(fz, 3),
                                                           round(facing + rnd.uniform(-15, 15), 1),
                                                           round(min(rnd.uniform(0.92, 1.06), 1.0 if row == STAND_ROWS - 1 else 2.0)
                                                                 * (1.0 if standing else 0.97), 3),
                                                           *shirt(rnd.randrange(8))])
                x += 0.62
    return inst


GROUPS = {
    "floor": lambda: floor(False, False),
    "floor_spike_pit": lambda: floor(True, False),
    "floor_flame_pit": lambda: floor(False, True),
    "floor_spike_pit_flame_pit": lambda: floor(True, True),
    "scars": scars,
    "cage": walls,
    "venue_floor": lambda: venue_floor(True),
    "venue_floor_open": lambda: venue_floor(False),
    "towers": towers,
    "rig": rig,
    "stands": stands,
    "screen": big_screen,
    "hall": hall,
    "roof": roof,
}
WHEN = {"floor": "the floor_group(spike_pit, flame_pit) for the user mods on: one of the four", "scars": "always",
        "cage": "the cage is up (not the No cage user mod)", "venue_floor": "the cage is up",
        "venue_floor_open": "No cage", "towers": "always", "rig": "always, under a node the full arena camera hides",
        "stands": "always (with the shapes at their instances)", "screen": "always", "hall": "always",
        "roof": "always, under the rig's node (the full arena camera hides it)"}


def groups():
    """{group: [model_kit.Part, ...]}"""
    return {name: make() for name, make in GROUPS.items()}


_made = {}


def made():
    """groups(), shapes() and stand_instances() made once, for the window."""
    if not _made:
        _made.update(groups=groups(), shapes=shapes(), instances=stand_instances())
    return _made


def arena():
    """Everything, as models/arena_ultra.json holds it."""
    m = made()
    out_groups = {name: [p.packed() for p in parts] for name, parts in m["groups"].items()}
    out_shapes = {name: [p.packed() for p in parts] for name, parts in m["shapes"].items()}
    tris = {name: sum(p.tris() for p in parts) for name, parts in m["groups"].items()}
    tris["crowd"] = sum(len(rows) * sum(p.tris() for p in m["shapes"][name]) for name, rows in m["instances"].items())
    return {"version": VERSION, "materials": MATERIALS, "groups": out_groups, "shapes": out_shapes,
            "instances": m["instances"],
            "notes": {"when": WHEN, "signs": SIGNS, "frame": "x, y on the floor, z up, metres; the floor z = 0 from -10 to 10",
                      "ultra": "drawn in place of the lower tiers' floor, walls, rails and posts, towers, rig, outside "
                               "floor, stands, crowd and screen box (rw_gfx.ArenaVisual); the markings, hazards, the "
                               "cage's see-through screens, the score's lettering and the user mods' items as the "
                               "lower tiers draw them",
                      "materials": "colour null: the arena's look wall_colour; decal: drawn after the floor with a "
                                   "depth offset; alpha: see-through by the vertices' alpha, drawn after the solid "
                                   "things without writing depth; flat or far: casts no shadow",
                      "triangles": tris}}


if __name__ == "__main__":
    import time
    t = time.perf_counter()
    m = made()
    for name, parts in m["groups"].items():
        print(f"{name:28s} {sum(p.tris() for p in parts):7d} triangles  ({', '.join(p.material for p in parts)})")
    crowd = sum(len(rows) * sum(p.tris() for p in m["shapes"][name]) for name, rows in m["instances"].items())
    print(f"{'crowd and seats':28s} {crowd:7d} triangles  ({sum(len(r) for r in m['instances'].values())} instances)")
    print(f"built in {time.perf_counter() - t:.2f} s")
