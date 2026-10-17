"""Fight Lab's ultra hall (CHANGE 147): the rings (a padded platform with a canvas top and the club's boards round its
skirt, corner posts with padded covers, ropes, steps), the hall's floor and walkways, the stands with their seats and
fans, the big screens, the lighting rig, the hall's walls and roof, built from numbers alone, so the window
(fight_gfx.py) and the page (club-coders/web/make_models.py writes it to models/stage_ultra.json) draw the same hall.
fight_models.py is its fighters; Robot Lab's arena_models.py did the same for its arena.

Pure Python, no Panda3D (engine.model_kit is pure Python too). stage() returns what the page reads:

    {"version": 1,
     "materials": {name: material, ...}   how each material looks (see MATERIALS)
     "ring":      {name: [part, ...]}     a ring's pieces, made for the standard ring (R0), placed by ring_layout()
     "groups":    {name: [part, ...]}     the hall's parts (see GROUPS and WHEN)
     "shapes":    {name: [part, ...]}     things placed many times (fans, seats), each in its own frame: x forward,
                                          y left, z up, its feet at the origin
     "instances": {shape: [[x, y, z, h, s, r, g, b], ...]}
     "notes":     {...}}

    part: engine.model_kit.Part.packed() (model_kit says how to read the arrays), with "tint" (an instance's colour
          multiplies its colours) and "far" (outside the rings: no shadow) where they apply
    instance: the shape turned h degrees about z (anticlockwise, from +x), scaled by s, moved to (x, y, z); r, g, b
              multiplies its "tint" parts' colours (screen colours)

A ring's size is the teacher's (the rules' ring_size, 3 to 6.5 m), so its pieces are made once for the standard 4.5 m
and ring_layout(R, roped) says how each is placed for a ring of radius R: [(piece, pos, hpr, scale, grow)], the
piece's points first pushed out from its z axis by grow metres (the platform's edge, skirt and boards keep their
shape as the ring grows), then scaled, turned (Panda's heading, pitch, roll, degrees) and moved, in the ring's frame
(its centre at the origin, the canvas at z 0). ultra draws the lower tiers' markings, logo, open edge's glow and
hazards (fight_gfx.StageVisual: they move and change) with these in place of their platform, mat, posts, pads, ropes,
hall floor, walkways, stands, crowd, screens' boxes and lighting truss. The hall is the lower tiers' for the largest
ring (PAD), so it fits every ring size. Nothing here is solid (the sim never reads a picture), nothing stands over a
ring's canvas inside its ring (where fighters move), and between the rings and the stands only the rig's towers rise
from the floor, where the lower tiers' are (gfx_test.py checks these).

The frame is the game's: x, y on the floor, z up, metres; the rings' canvas is z = 0, the hall's floor FLOOR_Z.
"""
import math
import random

from engine import model_kit as mk
from engine.model_kit import Frame, Parts

VERSION = 1
R0 = 4.5                # the standard ring's radius (fight_sim.RULES ring_size): the ring's pieces are made for it
FLOOR_Z = -0.8          # the hall's floor (fight_gfx: the platforms stand 0.8 m high)
RING_CENTRES = [(0.0, 0.0), (16.0, 0.0), (-16.0, 0.0), (0.0, 16.0), (16.0, 16.0), (-16.0, 16.0)]  # (fight_sim's)
PAD = 6.5 + 5.0         # the hall round the rings: fight_gfx.build_hall's for the largest ring (fight_mods: 3 to 6.5 m)
X0, X1, Y0, Y1 = -16.0 - PAD, 16.0 + PAD, 0.0 - PAD, 16.0 + PAD
CX, CY = 0.0, 8.0       # the hall's middle
MAT_COLOURS = [(0.12, 0.13, 0.2), (0.35, 0.06, 0.06), (0.06, 0.2, 0.12), (0.2, 0.08, 0.3), (0.3, 0.2, 0.05),
               (0.05, 0.18, 0.3)]  # each ring's mat (fight_gfx.MAT_COLOURS, ring i: i % 6)
CORNER_COLOURS = [(0.85, 0.1, 0.1), (0.95, 0.95, 0.95), (0.1, 0.25, 0.85)]  # its corner pads (fight_gfx.ROPE_COLOURS, i % 3)
ROPE_HEIGHTS = (0.45, 0.85, 1.25)

# each material: colour (a screen colour, times the vertex colours and the texture; None: the ring's mat colour,
# "corner": its corner pads' colour, "rope": the ropes' colour, fight_gfx's: red, or blue and glowing when they are
# electric), rough, metal, texture set (engine/assets/tex or BeatEmUp/assets/tex, the page's tex/), "emission"
# (linear light), "flat" (casts no shadow)
MATERIALS = {
    "canvas": {"colour": None, "rough": 0.9, "metal": 0.0, "texture": "fight_canvas", "flat": True},
    "apron": {"colour": [0.08, 0.09, 0.15], "rough": 0.42, "metal": 0.0, "texture": None},
    "bumper": {"colour": [0.1, 0.11, 0.2], "rough": 0.5, "metal": 0.0, "texture": None},
    "corner": {"colour": "corner", "rough": 0.45, "metal": 0.0, "texture": None},
    "rope": {"colour": "rope", "rough": 0.5, "metal": 0.0, "texture": None},
    "steel": {"colour": [0.6, 0.61, 0.64], "rough": 0.4, "metal": 1.0, "texture": "steel"},
    "dark_steel": {"colour": [0.16, 0.16, 0.18], "rough": 0.5, "metal": 1.0, "texture": "steel"},
    "chrome": {"colour": [0.9, 0.9, 0.92], "rough": 0.1, "metal": 1.0, "texture": None},
    "rubber": {"colour": [0.06, 0.06, 0.065], "rough": 0.85, "metal": 0.0, "texture": None},
    "black": {"colour": [0.02, 0.02, 0.022], "rough": 0.9, "metal": 0.0, "texture": None},
    "signs": {"colour": [1.0, 1.0, 1.0], "rough": 0.5, "metal": 0.0, "texture": "fight_signs"},
    "venue_floor": {"colour": [0.34, 0.35, 0.39], "rough": 0.75, "metal": 0.0, "texture": "concrete", "flat": True},
    "walkway": {"colour": [0.32, 0.26, 0.2], "rough": 0.8, "metal": 0.0, "texture": "concrete", "flat": True},
    "line": {"colour": [0.95, 0.72, 0.1], "rough": 0.6, "metal": 0.0, "texture": None, "flat": True},
    "concrete": {"colour": [0.5, 0.52, 0.58], "rough": 1.0, "metal": 0.0, "texture": "concrete"},
    "seat": {"colour": [1.0, 1.0, 1.0], "rough": 0.45, "metal": 0.0, "texture": None},
    "cloth": {"colour": [0.6, 0.6, 0.6], "rough": 0.9, "metal": 0.0, "texture": None},  # (dim: the hall is dark)
    "skin": {"colour": [0.62, 0.62, 0.62], "rough": 0.65, "metal": 0.0, "texture": None},
    "lamp": {"colour": [1.0, 1.0, 1.0], "rough": 0.3, "metal": 0.0, "texture": None, "emission": [6.0, 5.5, 5.0]},
    "led": {"colour": [0.0, 0.0, 0.0], "rough": 0.3, "metal": 0.0, "texture": None, "emission": [2.4, 0.7, 0.15]},
    "screen": {"colour": [0.02, 0.02, 0.03], "rough": 0.08, "metal": 0.0, "texture": None, "emission": [0.05, 0.02, 0.12]},
}

# the boards round the rings' skirts, on the stands and in the hall: one row each of the "fight_signs" texture, top row
# first (fight_textures draws the picture; never a real brand). (text, background, lettering), screen colours
SIGNS = [("FIGHT LAB", (0.42, 0.18, 0.68), (1.0, 1.0, 1.0)),
         ("CLUB CODERS", (0.1, 0.36, 0.86), (1.0, 1.0, 1.0)),
         ("ROBOT LAB", (0.84, 0.14, 0.12), (1.0, 1.0, 1.0)),
         ("KART LAB", (0.98, 0.78, 0.1), (0.08, 0.08, 0.1)),
         ('print("FIGHT!")', (0.07, 0.09, 0.11), (0.35, 0.95, 0.45)),
         ("BUILD  CODE  FIGHT", (0.08, 0.56, 0.3), (1.0, 1.0, 1.0)),
         ("if blocked: counter()", (0.17, 0.17, 0.19), (1.0, 0.62, 0.15)),
         ("RESPECT YOUR OPPONENT", (0.95, 0.75, 0.08), (0.06, 0.06, 0.07))]


def sign_v(row):
    """The texture's v from and to for a row of SIGNS (v 1 is the picture's top)."""
    n = len(SIGNS)
    return 1.0 - (row + 1) / n + 0.004, 1.0 - row / n - 0.004


def shirt(k):
    """A fan's shirt colour (screen colours): the clubs' colours and a few others."""
    return [(0.84, 0.14, 0.12), (0.1, 0.36, 0.86), (0.98, 0.78, 0.1), (0.42, 0.18, 0.68), (0.9, 0.9, 0.9),
            (0.15, 0.15, 0.18), (0.95, 0.5, 0.1), (0.2, 0.6, 0.3)][k % 8]


# ---------- a ring ----------
def canvas():
    """The canvas inside the ring (its radius R0: ring_layout scales it to the ring's), its texture to scale."""
    p = Parts()
    mk.disc(p.get("canvas"), Frame(), R0, 0.0, seg=64, metres=2.0)
    return p.all()


def platform(edge):
    """The platform round the canvas, from the ring's edge (R0) out to R0 + edge (0.7 with ropes, 0.1 for ring-outs,
    as the lower tiers' platform): the canvas out to a padded bumper round the top edge, a vinyl skirt down to the
    hall's floor with the club's boards round it, and a steel kick ring at its foot. (ring_layout grows it to the
    ring's radius.)"""
    p = Parts()
    pr = R0 + edge
    c = p.get("canvas")
    start = len(c.p)
    mk.disc(c, Frame(), pr - 0.06, R0, seg=64, metres=2.0)
    for k in range(start, len(c.p)):  # (the canvas outside the fighting circle a shade darker)
        c.c[k] = (0.72, 0.72, 0.72)
    mk.lathe(p.get("bumper"), Frame(), [(pr - 0.06, 0.0), (pr - 0.035, 0.026), (pr, 0.034), (pr + 0.026, 0.012),
                                        (pr + 0.034, -0.03), (pr + 0.024, -0.075)], seg=64)
    mk.lathe(p.get("apron"), Frame(), [(pr + 0.022, -0.07), (pr + 0.022, FLOOR_Z + 0.06)], seg=64, metres=2.0)
    mk.lathe(p.get("dark_steel"), Frame(), [(pr + 0.022, FLOOR_Z + 0.07), (pr + 0.05, FLOOR_Z + 0.06),
                                            (pr + 0.06, FLOOR_Z + 0.03), (pr + 0.06, FLOOR_Z)], seg=64)
    boards = 12
    for k in range(boards):  # boards round the skirt, each curved with it
        row = (k * 3) % len(SIGNS)
        v0, v1 = sign_v(row)
        a0, a1 = 2 * math.pi * (k + 0.12) / boards, 2 * math.pi * (k + 0.88) / boards
        rows, normals, uvs = [], [], []
        for z, v in ((-0.6, v0), (-0.2, v1)):
            row_p, row_n, row_uv = [], [], []
            for j in range(9):
                a = a0 + (a1 - a0) * j / 8
                r = pr + 0.026
                row_p.append((r * math.cos(a), r * math.sin(a), z))
                row_n.append((math.cos(a), math.sin(a), 0.0))
                row_uv.append((0.02 + 0.96 * j / 8, v))
            rows.append(row_p)
            normals.append(row_n)
            uvs.append(row_uv)
        p.get("signs").grid(rows, normals, uvs)
    return p.all()


def post():
    """A corner post (its +x towards the ring's middle): a steel post on a flange with a chrome cap, eyes for the
    three ropes, and a tall padded cover in the corner's colour on its inner side."""
    p = Parts()
    steel = p.get("steel")
    mk.lathe(steel, Frame(), [(0.0, 0.03), (0.13, 0.03), (0.13, 0.012), (0.085, 0.0)], seg=16)
    mk.lathe(steel, Frame(), [(0.07, 1.4), (0.07, 0.03)], seg=16)
    mk.lathe(p.get("chrome"), Frame(), [(0.0, 1.47), (0.05, 1.465), (0.08, 1.44), (0.08, 1.41), (0.07, 1.4)], seg=16)
    for z in ROPE_HEIGHTS:
        mk.lathe(p.get("chrome"), Frame((0, 0, z)), [(0.072, 0.03), (0.082, 0.02), (0.082, -0.02), (0.072, -0.03)], seg=16)
    mk.rounded_box(p.get("corner"), Frame((0.1, 0, 0.86)), (0.06, 0.13, 0.56), 0.05, steps=3, inner=2)
    mk.rounded_box(p.get("black"), Frame((0.162, 0, 0.86)), (0.003, 0.08, 0.42), 0.002, steps=1)
    return p.all()


def rope():
    """A rope a metre long along x (ring_layout stretches it from post to post)."""
    p = Parts()
    mk.rod(p.get("rope"), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), 0.035, seg=12)
    return p.all()


def steps():
    """Steps up to the platform (their back at the origin, going out along -y): three treads on a dark frame."""
    p = Parts()
    for k in range(3):
        z = FLOOR_Z + 0.2 * (k + 1)
        y0 = -0.3 * (3 - k)
        mk.rounded_box(p.get("rubber"), Frame((0, y0 + 0.15, z - 0.015)), (0.45, 0.15, 0.015), 0.008, steps=1)
        mk.box(p.get("dark_steel"), Frame(), -0.45, 0.45, y0, y0 + 0.3, FLOOR_Z, z - 0.03)
        mk.box(p.get("line"), Frame(), -0.45, 0.45, y0 - 0.002, y0 + 0.03, z - 0.004, z + 0.001)
    return p.all()


RING = {"canvas": canvas, "platform": lambda: platform(0.7), "platform_open": lambda: platform(0.1), "post": post,
        "rope": rope, "steps": steps}


def ring_layout(R, roped):
    """Where a ring's pieces go for a ring of radius R (the rules' ring_size) with ropes (roped) or an open edge:
    [(piece, pos, hpr, scale, grow)] in the ring's frame (see the module's notes). The posts and ropes stand where the
    lower tiers' do: eight posts round the ring, the ropes' middles just outside it."""
    edge = 0.7 if roped else 0.1
    out = [("canvas", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (R / R0, R / R0, 1.0), 0.0),
           ("platform" if roped else "platform_open", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), R - R0),
           ("steps", (0.0, -(R + edge + 0.03), 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0.0)]
    if roped:
        post_r = (R + 0.08) / math.cos(math.pi / 8)  # (fight_gfx: the ropes' middles sit just outside the circle)
        corners = [(math.cos(math.pi / 8 + k * math.pi / 4) * post_r, math.sin(math.pi / 8 + k * math.pi / 4) * post_r)
                   for k in range(8)]
        for x, y in corners:
            out.append(("post", (round(x, 4), round(y, 4), 0.0), (round(math.degrees(math.atan2(-y, -x)), 3), 0.0, 0.0),
                        (1.0, 1.0, 1.0), 0.0))
        for z in ROPE_HEIGHTS:
            for k in range(8):
                (xa, ya), (xb, yb) = corners[k], corners[(k + 1) % 8]
                out.append(("rope", (round(xa, 4), round(ya, 4), z),
                            (round(math.degrees(math.atan2(yb - ya, xb - xa)), 3), 0.0, 0.0),
                            (round(math.hypot(xb - xa, yb - ya), 4), 1.0, 1.0), 0.0))
    return out


# ---------- the hall ----------
def floor():
    """The hall's floor, the walkways between the rings (as the lower tiers': dark boards with yellow edges)."""
    p = Parts(far=True)
    mk.box(p.get("venue_floor"), Frame(), -80.0, 80.0, -60.0, 76.0, FLOOR_Z - 0.05, FLOOR_Z, 4.0, skip=("-z",))
    walk, line = p.get("walkway"), p.get("line")
    z = FLOOR_Z
    for x0, x1, y0, y1 in ((X0, X1, CY - 0.9, CY + 0.9), (-8.9, -7.1, Y0, Y1), (7.1, 8.9, Y0, Y1)):
        mk.box(walk, Frame(), x0, x1, y0, y1, z, z + 0.02, 2.0, skip=("-z",))
        if x1 - x0 > y1 - y0:
            for y in (y0, y1 - 0.08):
                mk.box(line, Frame(), x0, x1, y, y + 0.08, z + 0.02, z + 0.023, skip=("-z",))
        else:
            for x in (x0, x1 - 0.08):
                mk.box(line, Frame(), x, x + 0.08, y0, y1, z + 0.02, z + 0.023, skip=("-z",))
    return p.all()


STAND_ROWS = 5
ROW_DEEP = 1.2   # (the lower tiers': 1.2 m deep, 0.6 m up each, the first 0.9 m outside the hall)
ROW_RISE = 0.6
FRONT = 0.9


def sides():
    """The hall's four sides: (middle on the hall's edge, out of the hall, along it, half length)."""
    return [((CX, Y1), (0, 1), (-1, 0), (X1 - X0) / 2 + FRONT), ((CX, Y0), (0, -1), (1, 0), (X1 - X0) / 2 + FRONT),
            ((X1, CY), (1, 0), (0, 1), (Y1 - Y0) / 2 + FRONT), ((X0, CY), (-1, 0), (0, -1), (Y1 - Y0) / 2 + FRONT)]


def stands():
    """The stands on every side (where the lower tiers' are: five rows from 0.9 m outside the hall): concrete tiers
    with nosings, a back wall with boards along its top, a railing and a lit strip along the front with the club's
    boards on its wall. The seats and fans are shapes placed by stand_instances()."""
    p = Parts(far=True)
    concrete, steel = p.get("concrete"), p.get("steel")
    sign = 2
    for (mx, my), (ox, oy), (ax, ay), half in sides():
        f = Frame((mx, my, 0.0), (ax, ay, 0.0), (ox, oy, 0.0), (0, 0, 1))  # x along the side, y out of the hall
        for row in range(STAND_ROWS):
            y0, y1 = FRONT + row * ROW_DEEP, FRONT + (row + 1) * ROW_DEEP
            top = FLOOR_Z + 0.3 + row * ROW_RISE
            mk.box(concrete, f, -half, half, y0, y1, FLOOR_Z, top, 3.0, skip=("-z",))
            mk.box(p.get("dark_steel"), f, -half, half, y0, y0 + 0.05, top, top + 0.02)  # the tread's nosing
        back = FRONT + STAND_ROWS * ROW_DEEP
        wall_top = FLOOR_Z + 0.3 + (STAND_ROWS - 1) * ROW_RISE + 1.7
        mk.box(concrete, f, -half - 0.3, half + 0.3, back, back + 0.3, FLOOR_Z, wall_top, 3.0)
        for k in range(-2, 3):  # boards along the top of the back wall
            row = sign % len(SIGNS)
            sign += 1
            v0, v1 = sign_v(row)
            c = k * half / 2.6
            pts = [f.p(c + 3.0, back - 0.01, wall_top - 0.75), f.p(c - 3.0, back - 0.01, wall_top - 0.75),
                   f.p(c - 3.0, back - 0.01, wall_top - 0.1), f.p(c + 3.0, back - 0.01, wall_top - 0.1)]
            p.get("signs").quad(pts, f.v(0, -1, 0), [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
        n = int(2 * half / 2.9)
        for k in range(n):  # the front wall's boards
            row = (k + sign) % len(SIGNS)
            v0, v1 = sign_v(row)
            c = -half + 1.45 + k * 2.9 + (2 * half - n * 2.9) / 2
            pts = [f.p(c + 1.35, FRONT - 0.01, FLOOR_Z + 0.04), f.p(c - 1.35, FRONT - 0.01, FLOOR_Z + 0.04),
                   f.p(c - 1.35, FRONT - 0.01, FLOOR_Z + 0.27), f.p(c + 1.35, FRONT - 0.01, FLOOR_Z + 0.27)]
            p.get("signs").quad(pts, f.v(0, -1, 0), [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
        mk.box(p.get("led"), f, -half, half, FRONT - 0.03, FRONT, FLOOR_Z + 0.27, FLOOR_Z + 0.3)
        for x in [-half + 0.1 + 1.5 * k for k in range(int(2 * half / 1.5) + 1)]:
            mk.rod(steel, f.p(x, FRONT + 0.08, FLOOR_Z + 0.3), f.p(x, FRONT + 0.08, FLOOR_Z + 1.2), 0.02, seg=6)
        mk.rod(steel, f.p(-half, FRONT + 0.08, FLOOR_Z + 1.2), f.p(half, FRONT + 0.08, FLOOR_Z + 1.2), 0.028, seg=8)
        mk.rod(steel, f.p(-half, FRONT + 0.08, FLOOR_Z + 0.78), f.p(half, FRONT + 0.08, FLOOR_Z + 0.78), 0.015, seg=6)
    rnd = random.Random(147)  # the corners between the stands: flight cases, and the judges' table in one
    for sx, sy in ((X1, Y0), (X0, Y1), (X1, Y1)):
        dx, dy = (1 if sx > 0 else -1), (1 if sy > CY else -1)
        for k in range(3):
            x, y = sx + dx * (1.6 + rnd.uniform(0, 2.0)), sy + dy * (1.4 + k * 1.1)
            w, d, h = rnd.uniform(0.4, 0.6), rnd.uniform(0.3, 0.45), rnd.uniform(0.35, 0.75)
            f = Frame((x, y, FLOOR_Z)).turned("z", rnd.uniform(-20, 20))
            mk.rounded_box(p.get("black"), f.at(0, 0, h), (w, d, h), 0.03, steps=1)
            mk.box(p.get("chrome"), f, -w - 0.005, w + 0.005, -d - 0.005, d + 0.005, h * 1.4, h * 1.4 + 0.03)
    desk = Frame((X0 - 3.4, Y0 - 3.4, FLOOR_Z)).turned("z", -45)
    mk.rounded_box(p.get("dark_steel"), desk.at(0, 0, 0.45), (1.4, 0.4, 0.45), 0.04, steps=2)
    mk.box(p.get("screen"), Frame(desk.p(0, 0.25, 0.93), desk.x, desk.y, desk.z).turned("x", 25), -1.0, 1.0, -0.01, 0.01, 0.0, 0.3)
    return p.all()


SCREENS = ((CX, Y1 + 9.0, 6.0, 0.0), (CX, Y0 - 9.0, 6.0, 180.0))  # the big screens: x, y, z of their middles, heading


def screens():
    """The two big screens at the hall's ends (where the lower tiers' are: the hall's name is written on them), in dark
    housings with a lit edge, on legs behind the stands."""
    p = Parts(far=True)
    for x, y, z, h in SCREENS:
        f = Frame((x, y, z)).turned("z", h)  # (its -y towards the hall's middle)
        mk.rounded_box(p.get("dark_steel"), f, (6.6, 0.3, 2.04), 0.08, steps=2, inner=3)
        mk.box(p.get("screen"), f, -6.25, 6.25, -0.32, -0.29, -1.8, 1.8)
        mk.box(p.get("led"), f, -6.35, 6.35, -0.322, -0.3, -1.95, -1.9)
        for dx in (-4.5, -1.5, 1.5, 4.5):
            mk.rod(p.get("steel"), f.p(dx, 0.2, -2.0), f.p(dx, 0.2, FLOOR_Z - z), 0.08, seg=10)
    return p.all()


RIG_Z = 8.5  # (the lower tiers' truss)


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


def lamp_can(part_body, part_lens, f, r=0.22, depth=0.45):
    """A theatre lamp: a dark can along f's z (its lens at the front, +z)."""
    mk.lathe(part_body, f, [(r * 0.75, depth), (r, depth - 0.04), (r, 0.06), (r * 0.6, 0.0), (0.0, 0.0)], seg=16)
    mk.disc(part_lens, f, r * 0.82, 0.0, seg=16, z=depth + 0.002)
    mk.lathe(part_body, f, [(r * 0.86, depth + 0.06), (r * 1.02, depth + 0.02), (r * 1.02, depth)], seg=16)


def rig():
    """The lighting rig over the rings (under the node the high views hide, "lighting_rig", as the lower tiers'
    truss): box trusses along each row of rings on towers at the hall's edge, cross trusses, and lamps hanging over
    each ring, aimed at its middle."""
    p = Parts()
    steel = p.get("steel")
    for y in (0.0, 16.0):
        truss(steel, (X0, y, RIG_Z), (X1, y, RIG_Z), w=0.4, bay=0.7, r=0.04, lace=0.018)
        for x in (X0, X1):
            truss(steel, (x, y, FLOOR_Z), (x, y, RIG_Z + 0.2), w=0.4, bay=0.7, r=0.04, lace=0.018)
            mk.box(p.get("dark_steel"), Frame((x, y, FLOOR_Z)), -0.45, 0.45, -0.45, 0.45, 0.0, 0.05)
    for x in (-16.0, 0.0, 16.0):
        truss(steel, (x, -0.2, RIG_Z + 0.4), (x, 16.2, RIG_Z + 0.4), w=0.3, bay=0.6, r=0.03, lace=0.014)
    for cx, cy in RING_CENTRES:
        for dx, dy in ((-2.5, 0.0), (2.5, 0.0), (0.0, -1.2), (0.0, 1.2)):
            y = cy if dy == 0 else cy + dy
            x = cx + dx
            if dy:  # (on the cross truss)
                pos = (x, y, RIG_Z + 0.4 - 0.25)
            else:
                pos = (x, y, RIG_Z - 0.25)
            aim = mk.norm(mk.sub((cx, cy, 0.0), pos))
            side = mk.norm(mk.cross(aim, (0, 0, 1)))
            lamp_can(p.get("black"), p.get("lamp"), Frame(pos, side, mk.cross(aim, side), aim), 0.18, 0.32)
            mk.rod(p.get("dark_steel"), pos, (pos[0], pos[1], pos[2] + 0.25), 0.02, seg=6)
    return p.all()


WALL_X, WALL_Y0, WALL_Y1 = 50.0, -34.0, 50.0  # the hall's walls (beyond where the fight cameras go)
ROOF_Z = 18.0


def hall():
    """The hall's walls (under the rig's node: the high views hide them, as the roof), up to the roof: dark concrete
    with tall lit strips and the club's banners high up."""
    p = Parts(far=True)
    sign = 0
    for (x0, y0), (x1, y1) in (((-WALL_X, WALL_Y1), (WALL_X, WALL_Y1)), ((WALL_X, WALL_Y0), (-WALL_X, WALL_Y0)),
                               ((WALL_X, WALL_Y1), (WALL_X, WALL_Y0)), ((-WALL_X, WALL_Y0), (-WALL_X, WALL_Y1))):
        along = mk.norm((x1 - x0, y1 - y0, 0.0))
        inward = (-along[1], along[0], 0.0)
        f = Frame(((x0 + x1) / 2, (y0 + y1) / 2, FLOOR_Z), along, inward, (0, 0, 1))  # x along, y into the hall
        half = math.dist((x0, y0), (x1, y1)) / 2
        mk.box(p.get("concrete"), f, -half, half, -0.5, 0.0, 0.0, ROOF_Z - FLOOR_Z, 4.0, skip=("-z",))
        for k in range(-int(half // 8), int(half // 8) + 1):
            mk.box(p.get("led"), f, k * 8.0 - 0.08, k * 8.0 + 0.08, 0.0, 0.05, 0.5, ROOF_Z - FLOOR_Z - 1.5)
        for c in (-half / 3, half / 3):
            row = sign % len(SIGNS)
            sign += 3
            v0, v1 = sign_v(row)
            pts = [f.p(c + 6.0, 0.06, 7.5), f.p(c - 6.0, 0.06, 7.5), f.p(c - 6.0, 0.06, 9.0), f.p(c + 6.0, 0.06, 9.0)]
            p.get("signs").quad(pts, f.v(0, 1, 0), [(0.02, v0), (0.98, v0), (0.98, v1), (0.02, v1)])
    return p.all()


def roof():
    """The hall's roof (under the rig's node): dark panels, deep trusses every 8 m and a lamp row under each."""
    p = Parts(far=True)
    mk.box(p.get("concrete"), Frame(), -WALL_X, WALL_X, WALL_Y0, WALL_Y1, ROOF_Z, ROOF_Z + 0.3, 6.0, skip=("+z",))
    for k in range(-4, 6):
        y = CY + k * 8.0
        truss(p.get("dark_steel"), (-WALL_X, y, ROOF_Z - 1.2), (WALL_X, y, ROOF_Z - 1.2), w=1.0, bay=2.5, r=0.08, lace=0.04)
        for x in range(-40, 41, 10):
            mk.box(p.get("lamp"), Frame((x, y, ROOF_Z - 1.75)), -0.5, 0.5, -0.2, 0.2, -0.04, 0.0)
    return p.all()


# ---------- the crowd ----------
def fan(skin, hair, pose, seed):
    """A fan sitting or standing (pose 0: arms down, 1: one arm waving, 2: both arms up), facing +x: legs and body in
    their shirt's colour (the instance's tint), arms, a head with hair. About 1.5 m standing (as Robot Lab's)."""
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
    """Every seat and fan: [x, y, z, h, s, r, g, b] per shape. A seat every 0.8 m along each row but the aisles; a fan
    in most seats (standing in the front two rows, mostly sitting further back), in their shirts' colours."""
    inst = {}
    rnd = random.Random(147)
    seat_cols = [(0.42, 0.18, 0.68), (0.1, 0.36, 0.86)]
    for side, ((mx, my), (ox, oy), (ax, ay), half) in enumerate(sides()):
        f = Frame((mx, my, 0.0), (ax, ay, 0.0), (ox, oy, 0.0), (0, 0, 1))
        facing = math.degrees(math.atan2(-oy, -ox))  # (the shapes face +x: turned to face the hall)
        aisles = [k * 7.0 for k in range(-int(half // 7), int(half // 7) + 1)]
        for row in range(STAND_ROWS):
            top = FLOOR_Z + 0.3 + row * ROW_RISE
            y = FRONT + row * ROW_DEEP + 0.7
            x = -half + 0.5
            while x <= half - 0.5:
                if min(abs(x - a) for a in aisles) < 0.6:
                    x += 0.8
                    continue
                px, py, pz = f.p(x, y, top)
                sc = seat_cols[(row + side) % 2]
                inst.setdefault("seat", []).append([round(px, 3), round(py, 3), round(pz, 3), round(facing, 1), 1.0, *sc])
                if rnd.random() < 0.75:
                    k = rnd.randrange(8)
                    standing = row < 2 or (row < STAND_ROWS - 1 and rnd.random() < 0.2)
                    if row == STAND_ROWS - 1:  # (the top row sits, arms down: no higher than the row below)
                        k = (0, 1, 3, 5, 7)[k % 5]
                    fx, fy, fz = f.p(x + rnd.uniform(-0.05, 0.05), y - (0.25 if standing else -0.05),
                                     top + (0.0 if standing else -0.38))
                    inst.setdefault(f"fan{k}", []).append([round(fx, 3), round(fy, 3), round(fz, 3),
                                                           round(facing + rnd.uniform(-15, 15), 1),
                                                           round(rnd.uniform(0.92, 1.04) * (1.0 if standing else 0.97), 3),
                                                           *shirt(rnd.randrange(8))])
                x += 0.8
    return inst


GROUPS = {"floor": floor, "stands": stands, "screens": screens, "rig": rig, "hall": hall, "roof": roof}
WHEN = {"floor": "always", "stands": "always (with the shapes at their instances, the fans only when the look has a "
                  "crowd)", "screens": "always", "rig": "always, under the node the high views hide (lighting_rig)",
        "hall": "always, under the rig's node", "roof": "always, under the rig's node"}


def groups():
    """{group: [model_kit.Part, ...]}"""
    return {name: make() for name, make in GROUPS.items()}


def ring_pieces():
    """{piece: [model_kit.Part, ...]}"""
    return {name: make() for name, make in RING.items()}


_made = {}


def made():
    """ring_pieces(), groups(), shapes() and stand_instances() made once, for the window."""
    if not _made:
        _made.update(ring=ring_pieces(), groups=groups(), shapes=shapes(), instances=stand_instances())
    return _made


def stage():
    """Everything, as models/stage_ultra.json holds it."""
    m = made()
    packed = lambda d: {name: [p.packed() for p in parts] for name, parts in d.items()}  # noqa: E731
    tris = {name: sum(p.tris() for p in parts) for name, parts in list(m["ring"].items()) + list(m["groups"].items())}
    tris["crowd"] = sum(len(rows) * sum(p.tris() for p in m["shapes"][name]) for name, rows in m["instances"].items())
    return {"version": VERSION, "materials": MATERIALS, "ring": packed(m["ring"]), "groups": packed(m["groups"]),
            "shapes": packed(m["shapes"]), "instances": m["instances"],
            "notes": {"when": WHEN, "signs": SIGNS, "frame": "x, y on the floor, z up, metres; the rings' canvas z = 0, "
                                                             f"the hall's floor z = {FLOOR_Z}",
                      "ring": "each ring's pieces, made for a ring of radius R0 = 4.5 m: stage_models.ring_layout(R, "
                              "roped) in the window's code (BeatEmUp/stage_models.py), mirrored by the page, places "
                              "them for a ring of radius R (the roster's rs) with ropes (the hazard ring_out off) or an "
                              "open edge, about the ring's centre (fight_sim.RING_CENTRES): each piece's points pushed "
                              "out from its z axis by grow metres (x, y times (r + grow) / r), then scaled, turned "
                              "(heading about z, degrees) and moved",
                      "ultra": "drawn in place of the lower tiers' platform, base, mat, posts, pads and ropes, the "
                               "hall's floor, walkways, stands, crowd, screens' boxes and lighting truss "
                               "(fight_gfx.StageVisual); the markings, the logo, the open edge's glow, the fire jets, "
                               "spikes and ice, the screens' lettering and the energy shots as the lower tiers draw them",
                      "materials": "colour null: the ring's mat colour, MAT_COLOURS[ring % 6]; \"corner\": "
                                   "CORNER_COLOURS[ring % 3]; \"rope\": the ropes' colour (red 0.85, 0.12, 0.1; electric "
                                   "ropes 0.5, 0.8, 1.0 glowing 0.3, 0.9, 2.6 and pulsing, as the lower tiers'); flat or "
                                   "far: casts no shadow",
                      "mat_colours": MAT_COLOURS, "corner_colours": CORNER_COLOURS, "screens": SCREENS,
                      "triangles": tris}}


if __name__ == "__main__":
    import time
    t = time.perf_counter()
    m = made()
    for name, parts in list(m["ring"].items()) + list(m["groups"].items()):
        print(f"{name:16s} {sum(p.tris() for p in parts):7d} triangles  ({', '.join(p.material for p in parts)})")
    crowd = sum(len(rows) * sum(p.tris() for p in m["shapes"][name]) for name, rows in m["instances"].items())
    print(f"{'crowd and seats':16s} {crowd:7d} triangles  ({sum(len(r) for r in m['instances'].values())} instances)")
    print(f"built in {time.perf_counter() - t:.2f} s")
