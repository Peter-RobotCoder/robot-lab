"""Robot Lab's ultra robots (CHANGE 145): smooth, detailed robot parts built from numbers alone, so the window (rw_gfx.py)
and the page (club-coders/web/make_models.py writes them to models/robot_ultra.json) draw the same robots. Kart Lab's
kart_models.py is the quality bar.

Pure Python, no Panda3D (engine.model_kit is pure Python too). A robot is put together from pieces, each built once
at the standard size (100%) in its own frame: the hull, the armour panels, the wheels, each weapon and what holds it.
robot() returns what the page reads:

    {"version": 1,
     "roles":  {role: look}            how each role looks (see ROLES)
     "pieces": {name: [part, ...]}     each piece's parts, one per role, in the piece's own frame (x to the robot's
                                       right, y forward, z up, metres, at the standard size)
     "notes":  {...}}

    part: engine.model_kit.Part.packed(): {"name", "material" (the role), "count", "box", "uv_box", "positions",
          "normals", "uvs", "indices"}, the arrays packed (model_kit says how to read them)

Where each piece goes is layout(weapon, size, house): [(node, piece, pos, hpr, scale)], the node being one of
rw_gfx.RobotVisual's (chassis, deck, skirt_r, skirt_l, rear, beacon, weapon, chain, wheel) and pos, hpr (degrees,
Panda's heading, pitch, roll) and scale in that node's frame, worked out from lab_sim.shapes() as RobotVisual places
the lower tiers' parts. The page mirrors layout() (and shapes(), which it has already: robot.js). Nothing here is
solid: the sim never reads a picture, and every piece stays inside the shapes the physics uses (or where the lower
tiers' parts already were).
"""
import math

from engine import model_kit as mk
from engine.model_kit import Frame, Parts

VERSION = 1

# each role's look: colour (screen colours: None is the design's colour, "trim" its style's trim colour), roughness,
# metalness and emission (linear light; "lights": the style's lights). No textures: the warning stripes are shapes in
# yellow and black, and the window draws each of a robot's nodes as one Geom (its roles' colours per vertex, their
# roughness, metal and glow from a tiny picture with a texel a role: rw_gfx.RobotVisual.ultra)
ROLES = {
    "paint": {"colour": None, "rough": 0.3, "metal": 0.2},
    "trim": {"colour": "trim", "rough": 0.38, "metal": 0.35},
    "dark": {"colour": [0.1, 0.1, 0.11], "rough": 0.45, "metal": 0.7},
    "steel": {"colour": [0.56, 0.57, 0.6], "rough": 0.32, "metal": 1.0},
    "blade": {"colour": [0.8, 0.81, 0.84], "rough": 0.16, "metal": 1.0},
    "carbide": {"colour": [0.24, 0.24, 0.26], "rough": 0.3, "metal": 1.0},
    "chrome": {"colour": [0.93, 0.93, 0.95], "rough": 0.07, "metal": 1.0},
    "rubber": {"colour": [0.075, 0.075, 0.08], "rough": 0.82, "metal": 0.0},
    "rim": {"colour": [0.78, 0.79, 0.82], "rough": 0.25, "metal": 1.0},
    "glass": {"colour": [0.04, 0.045, 0.06], "rough": 0.04, "metal": 0.0},
    "black": {"colour": [0.015, 0.015, 0.017], "rough": 0.9, "metal": 0.0},
    "tank": {"colour": [0.75, 0.1, 0.08], "rough": 0.28, "metal": 0.2},
    "yellow": {"colour": [0.95, 0.72, 0.05], "rough": 0.5, "metal": 0.0},
    "lights": {"colour": [0.0, 0.0, 0.0], "rough": 0.2, "metal": 0.0, "emission": "lights"},
    "tail": {"colour": [0.0, 0.0, 0.0], "rough": 0.2, "metal": 0.0, "emission": [4.0, 0.2, 0.1]},
    "beacon": {"colour": [0.0, 0.0, 0.0], "rough": 0.2, "metal": 0.0, "emission": [6.0, 3.0, 0.0]},
    "pilot": {"colour": [0.0, 0.0, 0.0], "rough": 0.3, "metal": 0.0, "emission": [1.0, 0.5, 2.5]},
    "laser": {"colour": [0.0, 0.0, 0.0], "rough": 0.1, "metal": 0.0, "emission": [8.0, 1.5, 1.0]},
}

# the standard robot (lab_sim: BASE_HALF at 100%, CHASSIS_Z, WHEEL_R, HOUSE_WHEEL_R; the wheels' half widths are
# rw_gfx's: 0.075, and 1.6 times that on a Resident Robot)
HALF = (0.6, 0.8, 0.18)
CHASSIS_Z = 0.1
WHEEL = (0.2, 0.075)
HOUSE_WHEEL = (0.32, 0.12)
ALONG_X = Frame((0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))   # z along the robot's x (axles, the drum, the disc)
ALONG_Y = Frame((0, 0, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0))  # z along the robot's y (the flame nozzle, the laser)


def at(x, y, z, base=None):
    return (base or Frame()).at(x, y, z)


def chamfered(part, f, outline, z0, z1, ch, metres=0.5):
    """A flat-sided solid like model_kit.extrude, its top and bottom edges chamfered by ch (machined plate): the
    outline [(x, y), ...] convex and anticlockwise, from z0 to z1 along f's z."""
    cx = sum(p[0] for p in outline) / len(outline)
    cy = sum(p[1] for p in outline) / len(outline)
    inset = []
    for x, y in outline:
        d = math.hypot(x - cx, y - cy) or 1.0
        k = max(0.0, 1.0 - ch / d)
        inset.append((cx + (x - cx) * k, cy + (y - cy) * k))
    mk.extrude(part, f, outline, z0 + ch, z1 - ch, metres, caps=False)
    n = len(outline)
    for i in range(n):  # the two chamfers
        j = (i + 1) % n
        for za, zb, inner_top in ((z1 - ch, z1, True), (z0 + ch, z0, False)):
            pts = [f.p(*outline[i], za), f.p(*outline[j], za), f.p(*inset[j], zb), f.p(*inset[i], zb)]
            ex, ey = outline[j][0] - outline[i][0], outline[j][1] - outline[i][1]
            side = mk.norm((ey, -ex, 0.0))
            nn = mk.norm(f.v(side[0], side[1], 1.0 if inner_top else -1.0))
            part.quad(pts, nn)
    part.poly([f.p(x, y, z1) for x, y in inset], f.v(0, 0, 1), metres)
    part.poly([f.p(x, y, z0) for x, y in reversed(inset)], f.v(0, 0, -1), metres)
    return part


def side(x, s, y=0.0, z=0.0):
    """A frame on the robot's right (s 1) or left (s -1) side at x: its x forward (backward on the left), y up and
    z out of the side."""
    return Frame((x, y, z), (0, s, 0), (0, 0, 1), (s, 0, 0))


def bolts_on(part, f, points, r=0.011, h=0.007, seg=6):
    """Hex bolt heads at points [(x, y), ...] on f's x-y plane, standing up its z."""
    for x, y in points:
        mk.bolt(part, f.at(x, y, 0.0), r, h, seg)


# ---------- the body ----------
def hull():
    """The body at the standard size, centred on the origin (rw_gfx places it at CHASSIS_Z): a dark chassis tub, a
    painted shell with true round edges, side armour plates and a front plate in the trim colour, bumpers, a vent
    grille on top in front of the deck, and bolts round the top edge."""
    hx, hy, hz = HALF
    p = Parts()
    mk.rounded_box(p.get("dark"), at(0, 0, -0.06), (hx - 0.03, hy - 0.03, hz - 0.06), 0.05, steps=3)
    mk.rounded_box(p.get("paint"), at(0, 0, 0.02), (hx, hy, hz - 0.02), 0.055, steps=4, inner=2)
    trim = p.get("trim")
    for s in (1, -1):  # side armour plates, bolted on
        mk.rounded_box(trim, at(s * (hx + 0.006), -0.02, -0.005), (0.012, hy * 0.74, 0.085), 0.009, steps=2)
        bolts_on(p.get("chrome"), side(s * (hx + 0.018), s), [(y, z) for y in (-0.52, -0.17, 0.17, 0.52) for z in (-0.06, 0.05)], 0.011)
    mk.rounded_box(trim, at(0, hy + 0.006, -0.035), (hx * 0.86, 0.012, 0.07), 0.01, steps=2)  # front plate
    front = Frame((0, hy + 0.018, 0), (-1, 0, 0), (0, 0, 1), (0, 1, 0))
    bolts_on(p.get("chrome"), front, [(x, -0.035 + dz) for x in (-0.44, -0.15, 0.15, 0.44) for dz in (-0.04, 0.04)], 0.01)
    mk.rounded_box(p.get("rubber"), at(0, hy + 0.02, -0.13), (hx * 0.9, 0.03, 0.035), 0.02, steps=2)  # bumpers
    mk.rounded_box(p.get("rubber"), at(0, -hy - 0.02, -0.12), (hx * 0.8, 0.03, 0.035), 0.02, steps=2)
    # the vent grille in front of the deck: dark slats over a black opening
    grille = p.get("dark")
    mk.box(p.get("black"), Frame(), -0.27, 0.27, 0.56, 0.74, hz + 0.0005, hz + 0.0015, 0.2)
    for k in range(6):
        y = 0.575 + k * 0.03
        mk.rounded_box(grille, at(0, y, hz + 0.006), (0.26, 0.007, 0.006), 0.004, steps=1)
    mk.rounded_box(grille, at(0, 0.65, hz + 0.004), (0.29, 0.1, 0.004), 0.004, steps=1, skip=("-z",))
    top = Frame((0, 0, hz), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    edge = [(x, y) for x in (-0.5, -0.25, 0.0, 0.25, 0.5) for y in (-hy + 0.06, hy - 0.05)]
    edge += [(x, y) for x in (-hx + 0.065, hx - 0.065) for y in (-0.6, -0.3, 0.0, 0.3, 0.6)]
    bolts_on(p.get("chrome"), top, edge, 0.011, 0.006)
    # lifting points at the back corners
    for s in (1, -1):
        mk.tube(p.get("steel"), [(s * 0.42, -hy + 0.02, hz - 0.002), (s * 0.42, -hy - 0.035, hz + 0.03),
                                 (s * 0.3, -hy - 0.035, hz + 0.03), (s * 0.3, -hy + 0.02, hz - 0.002)], 0.012, seg=8)
    return p.all()


def eyes():
    """The light bar on the front (rw_gfx: at the nose, z0 + 45% of the half height): a dark housing, two round
    headlamps and a strip of lamps between them, in the style's lights colour."""
    p = Parts()
    mk.rounded_box(p.get("dark"), at(0, 0, 0), (0.3, 0.022, 0.034), 0.012, steps=2)
    f = Frame((0, 0.022, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    for x in (-0.23, 0.23):
        mk.lathe(p.get("chrome"), f.at(x, 0, 0), [(0.03, 0.006), (0.033, 0.0)], seg=20)
        mk.disc(p.get("lights"), f.at(x, 0, 0), 0.027, 0.0, seg=20, z=0.004)
    for k in range(7):
        mk.rounded_box(p.get("lights"), at(-0.135 + k * 0.045, 0.022, 0), (0.016, 0.004, 0.009), 0.003, steps=1)
    return p.all()


def antenna():
    """The aerial (rw_gfx: on the deck's back left corner): a base, a thin whip and a lit tip."""
    p = Parts()
    mk.lathe(p.get("dark"), Frame(), [(0.0, 0.05), (0.018, 0.045), (0.026, 0.02), (0.03, 0.0)], seg=14)
    mk.cylinder(p.get("steel"), Frame(), 0.006, 0.04, 0.4, seg=8, caps=False)
    mk.superellipsoid(p.get("lights"), at(0, 0, 0.415), (0.02, 0.02, 0.02), e=2, seg=12, rings=8)
    return p.all()


def deck():
    """The top armour panel (in its node's frame: its hinge at the origin, the plate forward of it): a plate in the
    trim colour with rounded edges, raised rims front and back, and two rows of bolts down its sides (the name is
    painted across its middle: rw_gfx writes it at 0.048 up)."""
    hx, hy, hz = HALF
    p = Parts()
    L, W = hy * 0.72, hx * 0.78
    mk.rounded_box(p.get("trim"), at(0, L, 0.005), (W, L, 0.04), 0.028, steps=3, inner=2)
    for y in (0.05, 2 * L - 0.05):
        mk.rounded_box(p.get("trim"), at(0, y, 0.049), (W - 0.03, 0.022, 0.006), 0.005, steps=1, skip=("-z",))
    mk.cylinder(p.get("steel"), Frame((-W + 0.02, 0.0, 0.0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), 0.02, 0.0, 2 * W - 0.04,
                seg=12, bevel=0.004)  # the hinge pin along its back edge
    top = Frame((0, 0, 0.045), (1, 0, 0), (0, 1, 0), (0, 0, 1))
    bolts_on(p.get("chrome"), top, [(s * hx * 0.72, hy * 0.18 + i * hy * 0.16) for i in range(8) for s in (-1, 1)], 0.013)
    return p.all()


def house_plates():
    """A Resident Robot's extra armour on its deck: three bolted steel plates (in the deck's frame)."""
    hx, hy, hz = HALF
    p = Parts()
    for i in range(3):
        y = hy * 0.35 + i * hy * 0.45
        mk.rounded_box(p.get("steel"), at(0, y, 0.06), (hx * 0.36, hy * 0.2, 0.022), 0.012, steps=2)
        top = Frame((0, y, 0.082), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        bolts_on(p.get("chrome"), top, [(sx * hx * 0.3, sy * hy * 0.15) for sx in (-1, 1) for sy in (-1, 1)], 0.012)
    return p.all()


def skirt():
    """The right-hand side skirt (in its node's frame: hinged along its top edge at the origin; the left one is this
    turned half round): a steel plate with a rubber strip along the bottom and bolts along the top."""
    hx, hy, hz = HALF
    p = Parts()
    mk.rounded_box(p.get("steel"), at(0, 0, -hz * 0.7), (0.03, hy * 0.9, hz * 0.7), 0.012, steps=2, inner=2)
    mk.rounded_box(p.get("rubber"), at(0.004, 0, -hz * 1.4 + 0.012), (0.03, hy * 0.88, 0.014), 0.01, steps=2)
    bolts_on(p.get("chrome"), side(0.03, 1, z=-0.03), [(y, 0.0) for y in (-0.6, -0.36, -0.12, 0.12, 0.36, 0.6)], 0.011)
    return p.all()


def stripes(p, f, x0, x1, z0, z1, width=0.07, slant=0.08):
    """Warning stripes on f's x-z plane (facing f's -y... its y out), from x0 to x1 and z0 to z1: slanted bands,
    yellow and black in turn, the band's ends slanted too."""
    n = int(round((x1 - x0) / width))
    for k in range(n):
        a, b = x0 + k * (x1 - x0) / n, x0 + (k + 1) * (x1 - x0) / n
        pts = [f.p(a, 0, z0), f.p(b, 0, z0), f.p(b + slant, 0, z1), f.p(a + slant, 0, z1)]
        p.get("yellow" if k % 2 else "black").quad(pts, f.v(0, 1, 0))


def skirt_stripes():
    """A Resident Robot's warning stripes on each skirt (in the skirt's frame): a band of them on its outer face."""
    hx, hy, hz = HALF
    p = Parts()
    zc = 0.02 - 0.5 * hz
    stripes(p, Frame((0.0305, 0, 0), (0, -1, 0), (1, 0, 0), (0, 0, 1)), -hy * 0.8, hy * 0.8 - 0.08, zc - hz * 0.42, zc + hz * 0.42,
            0.07, 0.08)
    return p.all()


def rear():
    """The back plate (in its node's frame: hinged along its top edge at the origin) with the tail lamps."""
    hx, hy, hz = HALF
    p = Parts()
    mk.rounded_box(p.get("steel"), at(0, 0, -hz * 0.55), (hx * 0.72, 0.012, hz * 0.55), 0.01, steps=2, inner=2)
    mk.rounded_box(p.get("dark"), at(0, -0.016, -0.096), (hx * 0.62, 0.008, 0.022), 0.006, steps=1)
    mk.rounded_box(p.get("tail"), at(0, -0.024, -0.096), (hx * 0.58, 0.004, 0.012), 0.004, steps=1)
    back = Frame((0, -0.012, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))
    bolts_on(p.get("chrome"), back, [(x, -0.03) for x in (-0.36, -0.12, 0.12, 0.36)], 0.01)
    return p.all()


def house_handles():
    """A Resident Robot's grab handles at the back (built about the back of the top: x across, y back)."""
    p = Parts()
    for s in (1, -1):
        x = s * 0.3
        mk.tube(p.get("steel"), [(x - 0.06, 0.0, -0.05), (x - 0.06, -0.06, 0.02), (x + 0.06, -0.06, 0.02), (x + 0.06, 0.0, -0.05)],
                0.016, seg=10)
    return p.all()


def beacon_base():
    p = Parts()
    mk.lathe(p.get("dark"), Frame(), [(0.0, 0.05), (0.09, 0.05), (0.1, 0.035), (0.1, -0.05)], seg=24)
    return p.all()


def beacon():
    """The Resident Robots' flashing beacon: an amber dome (its own node: rw_gfx makes it flash)."""
    p = Parts()
    mk.lathe(p.get("beacon"), Frame(), [(0.0, 0.07), (0.035, 0.064), (0.06, 0.045), (0.075, 0.015), (0.08, -0.07)], seg=24)
    return p.all()


# ---------- the wheels ----------
def wheel(R, W):
    """One wheel at the origin, its axle along x and its outer face at +x (the left-hand wheels are this turned half
    round): a chunky tyre with two staggered rows of chamfered tread blocks, a dished rim with five spokes and a hub
    with five wheel nuts."""
    p = Parts()
    f = ALONG_X
    core = R - 0.022 * R / 0.2  # (the carcass under the tread blocks)
    bead = R * 0.64
    mid = bead + 0.3 * (core - bead)
    profile = [(bead, W - 0.012)]
    for k in range(13):  # up the outer sidewall, over the shoulder, across the crown and down the inner one
        t = math.pi / 2 - math.pi * k / 12
        c, s_ = abs(math.cos(t)) ** 0.4, math.copysign(abs(math.sin(t)) ** 0.7, math.sin(t))
        profile.append((mid + (core - mid) * c, (W - 0.002) * s_))
    profile.append((bead, -W + 0.012))
    mk.lathe(p.get("rubber"), f, profile, seg=36)
    blocks = p.get("rubber")
    n = 12
    for k in range(n):
        for row, side in ((0, 1), (1, -1)):
            a = 2 * math.pi * (k + 0.5 * row) / n
            g = Frame((0, 0, 0), (0, math.cos(a), math.sin(a)), (0, -math.sin(a), math.cos(a)), (1, 0, 0))
            bf = Frame(g.p(core + 0.011 * R / 0.2, 0, side * W * 0.47), g.x, g.y, g.z)  # x: out from the axle
            t, ax, hr = 0.024 * R / 0.2, W * 0.42, 0.011 * R / 0.2  # (a block: chamfered round its outer face)
            chamfered(blocks, Frame(bf.o, bf.y, bf.z, bf.x), [(-t, -ax), (t, -ax), (t, ax), (-t, ax)], -hr, hr, 0.005)
    rim = p.get("rim")
    mk.lathe(rim, f, [(R * 0.22, W - 0.02), (R * 0.25, W - 0.03), (bead - 0.02, W - 0.02), (bead - 0.008, W - 0.001),
                      (bead + 0.004, W - 0.004), (bead, W - 0.012)], seg=36)
    mk.lathe(rim, f, [(bead - 0.002, -W + 0.012), (bead - 0.002, W - 0.012)][::-1], seg=36)  # the barrel, inside
    mk.disc(rim, f, bead, 0.0, seg=36, z=-W + 0.012, down=True)
    for k in range(5):  # five spokes standing proud of the dish
        a = 2 * math.pi * k / 5 + math.pi / 2
        g = Frame(f.p(0, 0, W - 0.026), f.v(math.cos(a), math.sin(a), 0), f.v(-math.sin(a), math.cos(a), 0), f.v(0, 0, 1))
        mk.rounded_box(rim, g.at((R * 0.25 + bead - 0.02) / 2, 0, 0), ((bead - 0.02 - R * 0.25) / 2 + 0.006, 0.012 * R / 0.2, 0.008),
                       0.005, steps=1)
    hub = f.at(0, 0, W - 0.02)
    mk.lathe(p.get("dark"), hub, [(0.0, 0.016), (R * 0.15, 0.012), (R * 0.2, 0.0)], seg=20)
    bolts_on(p.get("chrome"), hub, [(R * 0.11 * math.cos(2 * math.pi * k / 5), R * 0.11 * math.sin(2 * math.pi * k / 5))
                                     for k in range(5)], 0.008 * R / 0.2, 0.018)
    return p.all()


# ---------- the weapons (each in the weapon node's frame: its pivot at the origin, at the standard size) ----------
def wedge():
    """The flipper wedge (lab_sim: a plate 1.24 m wide and 1.2 m long hinged at the front of the top): a thick
    machined plate thinning to a sharp lip with warning stripes, hinge knuckles on a pin, and flush bolts."""
    p = Parts()
    side = Frame((-0.62, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))  # x forward, y up, z across
    out = [(0.0, -0.03), (1.06, -0.03), (1.2, -0.012), (1.2, -0.004), (1.06, 0.006), (0.06, 0.045), (0.0, 0.03)]
    mk.extrude(p.get("trim"), side, out, 0.0, 1.24, 0.6)
    lip = [(1.06, 0.006), (1.2, -0.004), (1.2, -0.0035), (1.06, 0.0075)]
    for k in range(16):  # the lip's warning blocks, yellow and black in turn
        mk.extrude(p.get("yellow" if k % 2 else "black"), side, [(1.06, 0.0062), (1.2, -0.0036), (1.2005, -0.001), (1.06, 0.0085)],
                   0.005 + k * 1.23 / 16, 0.005 + (k + 1) * 1.23 / 16, 0.5)
    del lip
    knuckles = p.get("steel")
    for k in range(5):
        x0 = -0.6 + k * 0.25
        mk.cylinder(knuckles, Frame((x0, 0.0, 0.0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), 0.048, 0.0, 0.2, seg=16, bevel=0.008)
    mk.cylinder(p.get("chrome"), Frame((-0.63, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), 0.022, 0.0, 1.26, seg=12, bevel=0.004)
    slope = math.atan2(0.039, 1.0)
    for y in (0.3, 0.62, 0.92):
        z = 0.045 - 0.039 * (y - 0.06) / 1.0
        top = Frame((0, y, z), (1, 0, 0), (0, math.cos(slope), -math.sin(slope)), (0, math.sin(slope), math.cos(slope)))
        for x in (-0.48, -0.16, 0.16, 0.48):
            mk.disc(p.get("chrome"), top.at(x, 0, 0.0008), 0.014, 0.0, seg=10)
            mk.disc(p.get("black"), top.at(x, 0, 0.0012), 0.006, 0.0, seg=6)
    return p.all()


def wedge_cheeks():
    """The cheeks either side of the wedge's hinge, on the body (built about the top's sides: rw_gfx places it at
    top - 0.05)."""
    hx = HALF[0]
    p = Parts()
    for s in (1, -1):
        f = Frame((s * (hx - 0.03) - 0.022, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0))
        chamfered(p.get("paint"), f, [(0.0, 0.0), (0.72, 0.0), (0.72, 0.05), (0.1, 0.16), (0.0, 0.16)], 0.0, 0.044, 0.008)
        bolts_on(p.get("chrome"), side(s * (hx - 0.03) + s * 0.022, s), [(s * y, z) for y, z in ((0.12, 0.06), (0.4, 0.04), (0.62, 0.03))],
                 0.01)
    return p.all()


def spinner_bar():
    """The horizontal spinner's bar (1.6 m across at the standard size: rw_gfx stretches it along x with the size):
    a tapered, chamfered steel bar with lightening holes and carbide strike blocks at its tips."""
    p = Parts()
    out = [(-0.8, -0.05), (-0.22, -0.08), (0.22, -0.08), (0.8, -0.05), (0.8, 0.05), (0.22, 0.08), (-0.22, 0.08), (-0.8, 0.05)]
    chamfered(p.get("blade"), Frame(), out, -0.05, 0.05, 0.012)
    for s in (-1, 1):
        f = Frame((s * 0.73, s * 0.03, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        chamfered(p.get("carbide"), f, [(-0.09, -0.1), (0.09, -0.1), (0.09, 0.1), (-0.09, 0.1)], -0.07, 0.07, 0.014)
        for x in (0.32, 0.5):
            for z, down in ((0.0505, False), (-0.0505, True)):
                mk.disc(p.get("black"), at(s * x, 0, 0), 0.026, 0.0, seg=14, z=z, down=down)
        bolts_on(p.get("chrome"), Frame((s * 0.73, s * 0.03, 0.07), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
                 [(-0.04, -0.05), (0.04, 0.05)], 0.012)
    return p.all()


def spinner_hub():
    """The spinner's hub on its upright axle: a turned boss with six bolts and a centre nut."""
    p = Parts()
    mk.lathe(p.get("trim"), Frame(), [(0.0, 0.075), (0.085, 0.075), (0.11, 0.055), (0.11, -0.055), (0.085, -0.075), (0.0, -0.075)],
             seg=28)
    top = at(0, 0, 0.075)
    bolts_on(p.get("chrome"), top, [(0.065 * math.cos(2 * math.pi * k / 6), 0.065 * math.sin(2 * math.pi * k / 6)) for k in range(6)],
             0.012, 0.008)
    mk.lathe(p.get("chrome"), top, [(0.0, 0.03), (0.022, 0.03), (0.03, 0.012), (0.03, 0.0)], seg=6)
    return p.all()


def spinner_forks():
    """The two forks that hold the spinner's axle out in front of the body (about the nose at CHASSIS_Z)."""
    p = Parts()
    for s in (1, -1):
        chamfered(p.get("steel"), at(s * 0.15, 0.12, 0.1 - 0.05), [(-0.06, -0.22), (0.06, -0.22), (0.06, 0.18), (0.0, 0.22), (-0.06, 0.18)],
                  0.0, 0.1, 0.012)
        bolts_on(p.get("chrome"), at(s * 0.15, 0.12, 0.15), [(0.0, -0.15), (0.0, -0.02)], 0.012)
    return p.all()


def drum():
    """The drum spinner (0.4 m across and 0.96 m long at the standard size, along x): a turned steel drum with
    grooves, dark end caps with bolt circles and staggered carbide teeth."""
    p = Parts()
    f = ALONG_X
    r, L = 0.2, 0.48
    prof = [(r - 0.02, L), (r, L - 0.02)]
    for k in range(7):  # grooves
        z = L - 0.07 - k * 0.135
        prof += [(r, z + 0.012), (r - 0.008, z + 0.006), (r - 0.008, z - 0.006), (r, z - 0.012)]
    prof += [(r, -L + 0.02), (r - 0.02, -L)]
    mk.lathe(p.get("steel"), f, prof, seg=40)
    for z, down in ((L, False), (-L, True)):
        mk.disc(p.get("dark"), f, r - 0.02, 0.0, seg=40, z=z, down=down)
        g = Frame(f.p(0, 0, z), f.x, f.y, f.z) if not down else Frame(f.p(0, 0, z), mk.mul(f.x, -1), f.y, mk.mul(f.z, -1))
        bolts_on(p.get("chrome"), g, [(0.12 * math.cos(2 * math.pi * k / 8), 0.12 * math.sin(2 * math.pi * k / 8)) for k in range(8)],
                 0.012, 0.008)
        mk.lathe(p.get("chrome"), g, [(0.0, 0.03), (0.04, 0.025), (0.05, 0.0)], seg=16)
    for k in range(6):
        a = 2 * math.pi * k / 6
        z = (-0.24 if k % 2 else 0.24)
        g = Frame(f.p(0, 0, z), f.v(math.cos(a), math.sin(a), 0), f.v(-math.sin(a), math.cos(a), 0), f.z)
        chamfered(p.get("carbide"), Frame(g.p(r - 0.005, 0, 0), g.z, g.x, g.y),
                  [(-0.06, 0.0), (0.06, 0.0), (0.04, 0.07), (-0.04, 0.07)], -0.035, 0.035, 0.008)
    return p.all()


def drum_mounts():
    """The drum's side mounts with bearing housings (about the nose at CHASSIS_Z: the drum's axle at y 0.18)."""
    p = Parts()
    for s in (1, -1):
        x = s * (0.48 + 0.06)
        mk.rounded_box(p.get("paint"), at(x, 0.08, 0.0), (0.04, 0.22, 0.09), 0.015, steps=2)
        g = Frame((x + s * 0.04, 0.18, -0.02), (0, s, 0), (0, 0, 1), (s, 0, 0))
        mk.lathe(p.get("dark"), g, [(0.0, 0.03), (0.04, 0.03), (0.065, 0.0)], seg=20)
        bolts_on(p.get("chrome"), side(x + s * 0.04, s), [(s * -0.08, 0.05), (s * 0.15, -0.05)], 0.011)
    return p.all()


def hammer_arm():
    """The hammer's arm (0.1 m square and 1.7 m long at the standard size, from the pivot forward: rw_gfx stretches
    it as lab_sim does): a steel box section with lightening slots and a collar at the pivot."""
    p = Parts()
    mk.rounded_box(p.get("steel"), at(0, 0.85, 0), (0.05, 0.85, 0.05), 0.015, steps=2, inner=3)
    for k in range(4):
        y = 0.35 + k * 0.33
        for s in (1, -1):
            mk.rounded_box(p.get("black"), at(s * 0.0505, y, 0), (0.001, 0.11, 0.022), 0.0009, steps=1)
    mk.lathe(p.get("dark"), Frame((-0.075, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)),
             [(0.04, 0.15), (0.075, 0.14), (0.075, 0.01), (0.04, 0.0)], seg=20)
    return p.all()


def hammer_head():
    """The hammer's head (about its middle, at the arm's end): a dark block with bolted cheek plates, a striking
    face and a steel spike underneath."""
    p = Parts()
    mk.rounded_box(p.get("carbide"), at(0, 0, 0), (0.22, 0.14, 0.14), 0.03, steps=3)
    for s in (1, -1):
        mk.rounded_box(p.get("dark"), at(s * 0.224, 0, 0), (0.008, 0.11, 0.11), 0.006, steps=1)
        bolts_on(p.get("chrome"), side(s * 0.232, s),
                 [(dy, dz) for dy in (-0.07, 0.07) for dz in (-0.07, 0.07)], 0.012)
    mk.rounded_box(p.get("blade"), at(0, 0.142, 0), (0.18, 0.01, 0.1), 0.008, steps=1)
    mk.lathe(p.get("blade"), Frame((0, 0, -0.084), (1, 0, 0), (0, 1, 0), (0, 0, 1)).turned("z", 45),
             [(0.11, 0.0), (0.11, -0.04), (0.03, -0.24), (0.0, -0.31)], seg=4)
    return p.all()


def hammer_axle():
    """The hammer's axle across the top, in two bearing blocks, with a ram behind (about the axle's middle)."""
    p = Parts()
    mk.cylinder(p.get("steel"), Frame((-0.3, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), 0.06, 0.0, 0.6, seg=20, bevel=0.01)
    for s in (1, -1):
        mk.rounded_box(p.get("trim"), at(s * 0.24, 0, -0.04), (0.05, 0.09, 0.1), 0.02, steps=2)
        mk.lathe(p.get("chrome"), Frame((s * 0.3, 0, 0), (0, s, 0), (0, 0, 1), (s, 0, 0)), [(0.0, 0.02), (0.04, 0.015), (0.045, 0.0)], seg=6)
    mk.tube(p.get("dark"), [(0.0, -0.05, -0.02), (0.0, -0.3, -0.08)], 0.035, seg=12)
    mk.tube(p.get("chrome"), [(0.0, -0.02, 0.0), (0.0, -0.12, -0.03)], 0.018, seg=10)
    return p.all()


def flame_nozzle():
    """The flame thrower's nozzle (along y from the pivot, 0.44 m at the standard size): a turned barrel with
    cooling rings, a flared tip and the pilot light under it."""
    p = Parts()
    f = ALONG_Y
    prof = [(0.07, 0.44)]
    for k in range(5):
        z = 0.38 - k * 0.07
        prof += [(0.07, z + 0.02), (0.082, z + 0.012), (0.082, z - 0.012), (0.07, z - 0.02)]
    prof += [(0.07, 0.02), (0.075, 0.0)]
    mk.lathe(p.get("steel"), f, prof, seg=24)
    mk.lathe(p.get("dark"), f, [(0.05, 0.5), (0.094, 0.49), (0.094, 0.43), (0.07, 0.4)], seg=24)
    mk.disc(p.get("black"), f, 0.05, 0.0, seg=24, z=0.5)
    mk.superellipsoid(p.get("pilot"), at(0, 0.47, -0.09), (0.022, 0.022, 0.02), e=2, seg=10, rings=6)
    mk.tube(p.get("chrome"), [(0, 0.1, -0.07), (0, 0.3, -0.085), (0, 0.45, -0.088)], 0.008, seg=8)
    return p.all()


def flame_tanks():
    """The flame thrower's two fuel tanks with chrome straps and feed hoses (about the top, a quarter of the way
    back: rw_gfx lifts it by the tanks' radius)."""
    hx, hy, hz = HALF
    p = Parts()
    r, L = 0.075, hy * 0.45
    for s in (1, -1):
        x = s * hx * 0.45
        g = Frame((x, 0, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0))
        prof = [(0.0, L + r * 0.8)]
        for k in range(1, 7):
            a = math.pi / 2 * k / 6
            prof.append((r * math.sin(a), L + r * 0.8 * math.cos(a)))
        for k in range(7):
            a = math.pi / 2 * k / 6
            prof.append((r * math.cos(a), -L - r * 0.8 * math.sin(a)))
        mk.lathe(p.get("tank"), g, prof, seg=28)
        for y in (-L * 0.55, L * 0.55):
            mk.lathe(p.get("chrome"), Frame((x, y, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0)),
                     [(r + 0.004, 0.012), (r + 0.006, 0.0), (r + 0.004, -0.012)], seg=28)
        mk.cylinder(p.get("chrome"), Frame((x, L + r * 0.8, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0)), 0.014, 0.0, 0.04, seg=10)
        mk.tube(p.get("rubber"), [(x, L + r * 0.8 + 0.035, 0.0), (x * 0.6, L + 0.2, 0.02), (0.0, L + 0.3, 0.04)], 0.013, seg=8)
    return p.all()


def flame_base():
    p = Parts()
    chamfered(p.get("dark"), Frame(), [(-0.126, -0.126), (0.126, -0.126), (0.126, 0.126), (-0.126, 0.126)], -0.08, 0.08, 0.02)
    bolts_on(p.get("chrome"), at(0, 0, 0.08), [(sx * 0.09, sy * 0.09) for sx in (-1, 1) for sy in (-1, 1)], 0.012)
    return p.all()


def laser():
    """The laser emitter (along y from the pivot, 0.36 m at the standard size): a rounded housing with cooling fins,
    a turned lens barrel and the lens."""
    p = Parts()
    mk.rounded_box(p.get("dark"), at(0, 0.18, 0), (0.06, 0.18, 0.05), 0.015, steps=2, inner=2)
    for k in range(7):
        mk.rounded_box(p.get("steel"), at(0, 0.06 + k * 0.042, 0.062), (0.055, 0.006, 0.014), 0.003, steps=1, skip=("-z",))
    for s in (1, -1):
        mk.rounded_box(p.get("trim"), at(s * 0.062, 0.18, 0), (0.006, 0.15, 0.03), 0.004, steps=1)
    f = Frame((0, 0.36, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0))
    mk.lathe(p.get("steel"), f, [(0.03, 0.08), (0.045, 0.075), (0.045, 0.05), (0.04, 0.045), (0.04, 0.02), (0.05, 0.012), (0.05, 0.0)], seg=24)
    mk.disc(p.get("laser"), f, 0.031, 0.0, seg=20, z=0.078)
    mk.tube(p.get("rubber"), [(0.03, 0.02, -0.03), (0.04, -0.08, -0.06), (0.02, -0.16, -0.07)], 0.01, seg=8)
    return p.all()


def laser_mount():
    p = Parts()
    mk.lathe(p.get("dark"), Frame(), [(0.0, 0.06), (0.08, 0.06), (0.096, 0.03), (0.096, -0.06)], seg=28)
    mk.lathe(p.get("steel"), Frame(), [(0.07, 0.072), (0.085, 0.064), (0.085, 0.058)], seg=28)
    return p.all()


def chainsaw_arm():
    """The chainsaw (lab_sim: an arm forward from the pivot, a motor and a guide bar at its end): the arm in the
    design's colour, a finned motor housing, a guide bar with a rounded nose (the chain is its own piece)."""
    p = Parts()
    a, bar = (0.06, 0.3, 0.05), (0.025, 0.42, 0.07)
    mk.rounded_box(p.get("paint"), at(0, a[1], 0), a, 0.018, steps=2, inner=2)
    mk.rounded_box(p.get("dark"), at(0, a[1] * 2 - 0.08, -0.02), (a[0] * 2.2, 0.16, a[2] * 2.2), 0.03, steps=3)
    for k in range(5):
        mk.rounded_box(p.get("steel"), at(0, a[1] * 2 - 0.2 + k * 0.06, -0.02 + a[2] * 2.2), (a[0] * 2.0, 0.008, 0.012), 0.004,
                       steps=1, skip=("-z",))
    by = a[1] * 2 + bar[1] - 0.05
    side = Frame((-bar[0], by, -0.04), (0, 1, 0), (0, 0, 1), (1, 0, 0))
    out = [(-bar[1], -bar[2]), (bar[1] - bar[2], -bar[2])]
    for k in range(1, 8):
        t = -math.pi / 2 + math.pi * k / 8
        out.append((bar[1] - bar[2] + bar[2] * math.cos(t), bar[2] * math.sin(t)))
    out += [(bar[1] - bar[2], bar[2]), (-bar[1], bar[2])]
    mk.extrude(p.get("blade"), side, out, 0.0, 2 * bar[0], 0.4)
    for s in (1, -1):
        for y in (-0.3, -0.1, 0.1):
            mk.disc(p.get("chrome"), Frame((s * (bar[0] + 0.0005), by + y, -0.04), (0, s, 0), (0, 0, 1), (s, 0, 0)), 0.012, 0.0, seg=10)
    return p.all()


def chain():
    """The chainsaw's chain (its own node: rw_gfx runs it along the bar): links top and bottom, every 6 cm, the top
    ones with carbide cutters."""
    p = Parts()
    bar = (0.025, 0.42, 0.07)
    y = -bar[1]
    k = 0
    while y < bar[1] - bar[2]:
        for z in (-bar[2] - 0.012, bar[2] + 0.012):
            mk.rounded_box(p.get("steel"), at(0, y, z), (bar[0] + 0.008, 0.02, 0.014), 0.005, steps=1)
            if z > 0 and k % 2 == 0:
                chamfered(p.get("carbide"), Frame((0, y, z + 0.012), (1, 0, 0), (0, 1, 0), (0, 0, 1)),
                          [(-0.02, -0.015), (0.02, -0.015), (0.015, 0.02), (-0.015, 0.02)], 0.0, 0.014, 0.004)
        y += 0.06
        k += 1
    return p.all()


def chainsaw_mounts():
    p = Parts()
    for s in (1, -1):
        mk.rounded_box(p.get("steel"), at(s * 0.12, 0, 0), (0.05, 0.12, 0.1), 0.018, steps=2)
        bolts_on(p.get("chrome"), side(s * 0.17, s), [(-0.06, 0.05), (0.06, 0.05), (0.0, -0.05)], 0.011)
    return p.all()


def vdisc():
    """The vertical disc (0.84 m across at the standard size, spinning about x): a steel disc with lightening holes,
    a turned hub with bolts, and eight hooked carbide teeth."""
    p = Parts()
    f = ALONG_X
    r, t = 0.42, 0.035
    mk.lathe(p.get("blade"), f, [(r, t - 0.006), (r - 0.006, t), (r * 0.48, t)][::-1] + [], seg=48)
    mk.lathe(p.get("blade"), f, [(r * 0.48, -t), (r - 0.006, -t), (r, -t + 0.006)][::-1], seg=48)
    mk.lathe(p.get("blade"), f, [(r, t - 0.006), (r, -t + 0.006)], seg=48)
    for z, down in ((t + 0.0006, False), (-t - 0.0006, True)):
        for k in range(6):
            a = 2 * math.pi * (k + 0.5) / 6
            mk.disc(p.get("black"), Frame(f.p(r * 0.68 * math.cos(a), r * 0.68 * math.sin(a), 0), f.x, f.y, f.z), 0.055, 0.0,
                    seg=16, z=z, down=down)
    mk.lathe(p.get("trim"), f, [(0.0, t + 0.04), (r * 0.36, t + 0.03), (r * 0.45, t + 0.0005), (r * 0.48, t - 0.002)], seg=36)
    mk.lathe(p.get("trim"), f, [(r * 0.48, -t + 0.002), (r * 0.45, -t - 0.0005), (r * 0.36, -t - 0.03), (0.0, -t - 0.04)], seg=36)
    bolts_on(p.get("chrome"), f.at(0, 0, t + 0.035), [(0.1 * math.cos(2 * math.pi * k / 6), 0.1 * math.sin(2 * math.pi * k / 6))
                                                       for k in range(6)], 0.013)
    for k in range(8):
        a = 2 * math.pi * k / 8
        g = Frame(f.p(0, 0, -t - 0.012), f.v(math.cos(a), math.sin(a), 0), f.v(-math.sin(a), math.cos(a), 0), f.z)
        mk.extrude(p.get("carbide"), g, [(r * 0.92, -0.07), (r * 1.14, 0.05), (r * 1.08, 0.07), (r * 0.92, 0.07)], 0.0,
                   2 * t + 0.024, 0.2)
    return p.all()


def vdisc_slot():
    """The slot the disc spins in: two side plates in the design's colour and the axle (about the pivot)."""
    p = Parts()
    r, t = 0.42, 0.035
    for s in (1, -1):
        mk.rounded_box(p.get("paint"), at(s * (t + 0.07), -0.05, -r * 0.25), (0.03, r * 0.75, r * 0.55), 0.015, steps=2)
        bolts_on(p.get("chrome"), side(s * (t + 0.1), s), [(s * dy, dz) for dy in (-0.3, 0.2) for dz in (-0.25, 0.05)], 0.013)
    mk.cylinder(p.get("steel"), Frame((-(t + 0.12), 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), 0.07, 0.0, 2 * (t + 0.12), seg=20, bevel=0.01)
    for s in (1, -1):
        mk.lathe(p.get("chrome"), Frame((s * (t + 0.12), 0, 0), (0, s, 0), (0, 0, 1), (s, 0, 0)), [(0.0, 0.03), (0.05, 0.025), (0.055, 0.0)], seg=6)
    return p.all()


PIECES = {
    "hull": hull, "eyes": eyes, "antenna": antenna, "deck": deck, "house_plates": house_plates, "skirt": skirt,
    "skirt_stripes": skirt_stripes, "rear": rear, "house_handles": house_handles, "beacon_base": beacon_base,
    "beacon": beacon, "wheel": lambda: wheel(*WHEEL), "house_wheel": lambda: wheel(*HOUSE_WHEEL),
    "wedge": wedge, "wedge_cheeks": wedge_cheeks, "spinner_bar": spinner_bar, "spinner_hub": spinner_hub,
    "spinner_forks": spinner_forks, "drum": drum, "drum_mounts": drum_mounts, "hammer_arm": hammer_arm,
    "hammer_head": hammer_head, "hammer_axle": hammer_axle, "flame_nozzle": flame_nozzle, "flame_tanks": flame_tanks,
    "flame_base": flame_base, "laser": laser, "laser_mount": laser_mount, "chainsaw_arm": chainsaw_arm, "chain": chain,
    "chainsaw_mounts": chainsaw_mounts, "vdisc": vdisc, "vdisc_slot": vdisc_slot,
}


# ---------- where the pieces go ----------
def layout(weapon, size, house, sh):
    """Where each piece goes for a robot of this weapon and size (the standard size it is drawn at: rw_gfx's size/k)
    and house (Resident Robot styling), from sh = lab_sim.shapes(weapon, size, house). [(node, piece, pos, hpr, scale)]:
    node is one of RobotVisual's; pos, hpr (degrees) and scale (x, y, z) in its frame. The wheels are one entry each
    (node "wheel0" to "wheel3", in lab_sim.WHEELS' order; a wheel on the left, x < 0, turned half round)."""
    s = size
    hx, hy, hz = (v * s for v in HALF)
    z0, top = CHASSIS_Z, CHASSIS_Z + hz
    one, S = (1.0, 1.0, 1.0), (s, s, s)
    out = [("chassis", "hull", (0.0, 0.0, z0), (0, 0, 0), S),
           ("chassis", "eyes", (0.0, hy + 0.005, z0 + hz * 0.45), (0, 0, 0), S),
           ("chassis", "antenna", (-hx * 0.6, -hy * 0.7, top + 0.04 + 0.045 * s), (0, 0, 0), one),
           ("deck", "deck", (0.0, 0.0, 0.0), (0, 0, 0), S),
           ("skirt_r", "skirt", (0.0, 0.0, 0.0), (0, 0, 0), S),
           ("skirt_l", "skirt", (0.0, 0.0, 0.0), (180, 0, 0), S),
           ("rear", "rear", (0.0, 0.0, 0.0), (0, 0, 0), S)]
    wheel_piece = "house_wheel" if house else "wheel"
    from_lab = ((0.72, 0.55), (-0.72, 0.55), (0.72, -0.55), (-0.72, -0.55))  # (lab_sim.WHEELS)
    for i, (x, y) in enumerate(from_lab):
        out.append((f"wheel{i}", wheel_piece, (0.0, 0.0, 0.0), (180 if x < 0 else 0, 0, 0), one))
    if house:
        out += [("deck", "house_plates", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("skirt_r", "skirt_stripes", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("skirt_l", "skirt_stripes", (0.0, 0.0, 0.0), (180, 0, 0), S),
                ("chassis", "house_handles", (0.0, -hy, top), (0, 0, 0), S),
                ("chassis", "beacon_base", (hx * 0.55, -hy * 0.55, top + 0.14), (0, 0, 0), one),
                ("beacon", "beacon", (0.0, 0.0, 0.0), (0, 0, 0), one)]
    if weapon == "wedge":
        p1 = 0.6 + 0.02
        out += [("weapon", "wedge", (0.0, 0.0, 0.0), (0, 0, 0), (sh["plate"][0] / p1, 1.0, 1.0)),
                ("chassis", "wedge_cheeks", (0.0, 0.0, top - 0.05), (0, 0, 0), S)]
    elif weapon == "spinner":
        out += [("weapon", "spinner_bar", (0.0, 0.0, 0.0), (0, 0, 0), (sh["bar"][0] / 0.8, 1.0, 1.0)),
                ("weapon", "spinner_hub", (0.0, 0.0, 0.0), (0, 0, 0), one),
                ("chassis", "spinner_forks", (0.0, hy, z0), (0, 0, 0), one)]
    elif weapon == "drum":
        out += [("weapon", "drum", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("chassis", "drum_mounts", (0.0, hy, z0), (0, 0, 0), S)]
    elif weapon == "vdisc":
        pv = sh["pivot"]
        out += [("weapon", "vdisc", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("chassis", "vdisc_slot", (pv[0], pv[1], pv[2]), (0, 0, 0), S)]
    elif weapon == "flame":
        pv = sh["pivot"]
        out += [("weapon", "flame_nozzle", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("chassis", "flame_tanks", (0.0, -hy * 0.25, top + 0.13 * s / 1.6), (0, 0, 0), S),
                ("chassis", "flame_base", (pv[0], pv[1], pv[2] - 0.09), (0, 0, 0), S)]
    elif weapon == "laser":
        pv = sh["pivot"]
        out += [("weapon", "laser", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("chassis", "laser_mount", (pv[0], pv[1], pv[2] - 0.07), (0, 0, 0), S)]
    elif weapon == "chainsaw":
        pv = sh["pivot"]
        out += [("weapon", "chainsaw_arm", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("chain", "chain", (0.0, 0.0, 0.0), (0, 0, 0), S),
                ("chassis", "chainsaw_mounts", (pv[0], pv[1], pv[2] - 0.05), (0, 0, 0), S)]
    else:  # hammer
        a, hd = sh["arm"], sh["head"]
        out += [("weapon", "hammer_arm", (0.0, 0.0, 0.0), (0, 0, 0), (a[0] / 0.05, a[1] / 0.85, a[2] / 0.05)),
                ("weapon", "hammer_head", (0.0, a[1] * 2, 0.0), (0, 0, 0), (hd[0] / 0.22, hd[1] / 0.14, hd[2] / 0.14)),
                ("chassis", "hammer_axle", (0.0, -0.2 * s, top + 0.1), (0, 0, 0), S)]
    return out


def robot():
    """Every piece, as models/robot_ultra.json holds it."""
    pieces = {name: [p.packed() for p in parts] for name, parts in kit().items()}
    tris = {name: sum(len(mk.unpack(p)[5]) // 3 for p in parts) for name, parts in pieces.items()}
    return {"version": VERSION, "roles": ROLES, "pieces": pieces,
            "notes": {"frame": "x to the robot's right, y forward, z up, metres, at the standard size (100%); "
                               "triangles anticlockwise seen from outside",
                      "layout": "where each piece goes: robot_models.layout(weapon, size, house, shapes) in the robot "
                                "window's code (shared-world-demo/robot_models.py), mirrored by the page; size is the "
                                "standard size the robot is drawn at (lab_sim.shapes' k scales the whole robot after)",
                      "nodes": "chassis: the body (its pose from the server); deck, skirt_r, skirt_l, rear: the armour "
                               "panels on their hinges (rw_gfx.RobotVisual.panel); beacon: a Resident Robot's flashing "
                               "dome; weapon: the weapon (its pose from the server); chain: the chainsaw's chain, run "
                               "along the bar; wheel0-3: the wheels, spinning about x",
                      "roles": "colour None: the design's colour; \"trim\": the style's trim colour; emission "
                               "\"lights\": the style's lights colour (screen colour) times 6",
                      "triangles": tris}}


_kit = {}


def kit():
    """The pieces made once ({name: [model_kit.Part, ...]}), for the window."""
    if not _kit:
        _kit.update({name: make() for name, make in PIECES.items()})
    return _kit


if __name__ == "__main__":
    import time
    t = time.perf_counter()
    for name, parts in kit().items():
        print(f"{name:16s} {sum(p.tris() for p in parts):6d} triangles  ({', '.join(p.material for p in parts)})")
    print(f"built in {time.perf_counter() - t:.2f} s")
