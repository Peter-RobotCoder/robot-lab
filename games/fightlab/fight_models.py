"""Fight Lab's ultra fighters (CHANGE 147): the built robot and martial artist (and the bosses made from them) as smooth,
detailed parts built from numbers alone, so the window (fight_gfx.py) and the page (club-coders/web/make_models.py
writes them to models/fight_ultra.json) draw the same fighters. Robot Lab's robot_models.py did the same for its
robots. (The detailed 3D bodies, woman, man and Robin, are already models: fight_model.py draws them on every tier.)

Pure Python, no Panda3D (engine.model_kit is pure Python too). A fighter is put together from pieces, one or more on
each joint of fight_gfx.FighterVisual's skeleton, each built once at the standard size in its joint's own frame (x to
the fighter's right, y forward, z up, metres; a limb hangs down its -z from the joint). fighter() returns what the
page reads:

    {"version": 1,
     "roles":  {role: look}            how each role looks (see ROLES)
     "pieces": {name: [part, ...]}     each piece's parts, one per role, in its joint's frame
     "notes":  {...}}

    part: engine.model_kit.Part.packed() (model_kit says how to read the arrays)

Where each piece goes is layout(body, model): [(joint, piece, pos, hpr, scale)], the joint one of FighterVisual's
(hips, waist, neck, ls, le, rs, re, lh, lk, la, rh, rk, ra: the fists are on le and re, as the lower tiers join them)
and pos, hpr (degrees, Panda's heading, pitch, roll) and scale in its frame. The poses, the hit flash, the energy in
the hands and the number on the back are the lower tiers' (FighterVisual): only the shapes are new. Nothing here is
solid (the sim never reads a picture) and every piece stays where the lower tiers' parts are, give or take a couple
of centimetres (gfx_test.py checks it).
"""
import math

from engine import model_kit as mk
from engine.model_kit import Frame, Parts

VERSION = 1

# each role's look: colour (screen colours; None: the design's colour, "trim": the style's trim, "skin": the style's
# skin, "hair": the fighter's hair colour (fight_gfx.FighterVisual.hair_colour), "pants": the design's colour times
# 0.55 (as the lower tiers' trousers), "shade": the design's colour times 0.78, "lips": the skin a little redder),
# roughness, metalness and emission (linear light; "lights": the style's lights colour times 5, as the lower tiers'
# glowing parts). The window draws each joint's pieces as one Geom: the roles' colours in its vertices, their
# roughness, metal and glow from a tiny picture with a texel a role (fight_gfx.FighterVisual.ultra).
ROLES = {
    "paint": {"colour": None, "rough": 0.32, "metal": 0.55},
    "trim": {"colour": "trim", "rough": 0.38, "metal": 0.6},
    "dark": {"colour": [0.13, 0.13, 0.15], "rough": 0.45, "metal": 0.75},
    "steel": {"colour": [0.56, 0.57, 0.6], "rough": 0.3, "metal": 1.0},
    "chrome": {"colour": [0.93, 0.93, 0.95], "rough": 0.08, "metal": 1.0},
    "rubber": {"colour": [0.07, 0.07, 0.075], "rough": 0.85, "metal": 0.0},
    "black": {"colour": [0.015, 0.015, 0.017], "rough": 0.6, "metal": 0.0},
    "lights": {"colour": [0.0, 0.0, 0.0], "rough": 0.2, "metal": 0.0, "emission": "lights"},
    "gi": {"colour": None, "rough": 0.85, "metal": 0.0},
    "shade": {"colour": "shade", "rough": 0.85, "metal": 0.0},
    "pants": {"colour": "pants", "rough": 0.85, "metal": 0.0},
    "belt": {"colour": "trim", "rough": 0.7, "metal": 0.0},
    "glove": {"colour": "trim", "rough": 0.42, "metal": 0.0},
    "wrap": {"colour": [0.92, 0.92, 0.9], "rough": 0.8, "metal": 0.0},
    "skin": {"colour": "skin", "rough": 0.62, "metal": 0.0},
    "lips": {"colour": "lips", "rough": 0.5, "metal": 0.0},
    "hair": {"colour": "hair", "rough": 0.7, "metal": 0.0},
    "eye": {"colour": [0.95, 0.95, 0.93], "rough": 0.15, "metal": 0.0},
    "iris": {"colour": [0.2, 0.12, 0.06], "rough": 0.1, "metal": 0.0},
}

# the skeleton (fight_gfx: THIGH, SHIN, ANKLE, UPPER, FORE): a limb's next joint is this far down its -z
THIGH, SHIN, ANKLE, UPPER, FORE = 0.42, 0.42, 0.08, 0.29, 0.26
BIG = 1.15  # a boss's body is this much wider (fight_gfx's big): the layout scales its pieces


def at(x, y, z):
    return Frame((x, y, z))


def blob(part, x, y, z, radii, e=2.6, seg=20, rings=12):
    """A rounded shape (model_kit.superellipsoid) centred at x, y, z."""
    return mk.superellipsoid(part, at(x, y, z), radii, e=e, seg=seg, rings=rings)


def facing_y(x, y, z):
    """A frame at x, y, z whose z axis points forward (+y): discs and lenses on a fighter's front."""
    return Frame((x, y, z), (1, 0, 0), (0, 0, -1), (0, 1, 0))


def facing_x(x, y, z, s=1):
    """A frame at x, y, z whose z axis points to the side (s 1: right, -1: left)."""
    return Frame((x, y, z), (0, s, 0), (0, 0, 1), (s, 0, 0))


def oval_band(part, cx, cy, rx, ry, profile, seg=28):
    """A band round an oval (a belt, a headband, a cuff): profile [(k, z), ...] from the top down, the oval's radii
    rx, ry times k at height z, centred on cx, cy."""
    rows = []
    for k, z in profile:
        rows.append([(cx + rx * k * math.cos(2 * math.pi * j / seg), cy + ry * k * math.sin(2 * math.pi * j / seg), z)
                     for j in range(seg + 1)])
    zs = [z for _, z in profile]
    mid = (max(zs) + min(zs)) / 2
    part.surface(rows, lambda p: (cx, cy, mid if len(profile) > 1 else p[2]), uv_scale=4.0)
    return part


def mirrored(parts):
    """The left side's piece from the right side's: x the other way (the triangles wound back, so they still face out)."""
    out = []
    for p in parts:
        q = mk.Part(p.name, p.material, p.tint, p.far)
        q.p = [(-x, y, z) for x, y, z in p.p]
        q.n = [(-x, y, z) for x, y, z in p.n]
        q.uv, q.c, q.a = list(p.uv), list(p.c), list(p.a)
        for i in range(0, len(p.idx), 3):
            q.idx += [p.idx[i], p.idx[i + 2], p.idx[i + 1]]
        out.append(q)
    return out


# ---------- the robot ----------
def robot_hips():
    """The pelvis: a dark core, a painted hip plate with chrome bolts, a trim belt and a guard in front."""
    p = Parts()
    blob(p.get("dark"), 0, 0, 0.03, (0.185, 0.118, 0.092), e=3.0)
    mk.rounded_box(p.get("paint"), at(0, 0.004, 0.1), (0.214, 0.144, 0.044), 0.034, steps=3)
    mk.rounded_box(p.get("trim"), at(0, 0, 0.05), (0.204, 0.136, 0.016), 0.012, steps=2)
    mk.rounded_box(p.get("trim"), at(0, 0.118, 0.0), (0.068, 0.024, 0.058), 0.02, steps=2)
    front = facing_y(0, 0.148, 0.1)
    for x in (-0.17, -0.09, 0.09, 0.17):
        mk.bolt(p.get("chrome"), front.at(x, 0.0, 0.0), 0.01, 0.006)
    return p.all()


def robot_thigh():
    """A thigh: the hip's ball joint, a dark actuator, a painted shell with a trim stripe, a chrome piston behind and
    the knee's hinge at the bottom."""
    p = Parts()
    blob(p.get("trim"), 0, 0, 0, (0.08, 0.08, 0.08), e=2.0, seg=18, rings=10)
    mk.lathe(p.get("chrome"), Frame(), [(0.083, 0.012), (0.086, 0.0), (0.083, -0.012)], seg=18)
    mk.cylinder(p.get("dark"), Frame(), 0.052, -THIGH + 0.02, -0.04, seg=14)
    blob(p.get("paint"), 0, 0.012, -0.19, (0.09, 0.098, 0.148), e=2.8)
    mk.rounded_box(p.get("trim"), at(0, 0.104, -0.19), (0.026, 0.008, 0.095), 0.006, steps=2)
    mk.rod(p.get("dark"), (0, -0.07, -0.07), (0, -0.07, -0.2), 0.02, seg=10, caps=True)
    mk.rod(p.get("chrome"), (0, -0.07, -0.2), (0, -0.07, -0.36), 0.012, seg=10, caps=True)
    mk.cylinder(p.get("dark"), facing_x(-0.064, 0, -THIGH + 0.03), 0.045, 0.0, 0.128, seg=16, bevel=0.008)
    return p.all()


def robot_shin():
    """A shin: a trim knee cap, a dark core, a painted guard with a strip of light down its front, a calf piston and
    the ankle's hinge."""
    p = Parts()
    blob(p.get("trim"), 0, 0.083, -0.02, (0.064, 0.04, 0.064), e=2.5)
    mk.cylinder(p.get("dark"), Frame(), 0.048, -SHIN + 0.02, 0.0, seg=14)
    blob(p.get("paint"), 0, 0.02, -0.2, (0.086, 0.108, 0.162), e=2.8)
    mk.rounded_box(p.get("lights"), at(0, 0.129, -0.215), (0.015, 0.004, 0.07), 0.003, steps=1)
    mk.rod(p.get("chrome"), (0, -0.08, -0.08), (0, -0.08, -0.3), 0.011, seg=10, caps=True)
    mk.rod(p.get("dark"), (0, -0.075, -0.28), (0, -0.075, -0.37), 0.018, seg=10, caps=True)
    mk.cylinder(p.get("dark"), facing_x(-0.05, 0, -SHIN + 0.03), 0.04, 0.0, 0.1, seg=16, bevel=0.006)
    return p.all()


def robot_foot():
    """A boot: a rubber sole, a trim upper, a painted toe cap and a dark heel."""
    p = Parts()
    blob(p.get("dark"), 0, 0, -0.005, (0.044, 0.044, 0.044), e=2.0, seg=14, rings=8)
    mk.rounded_box(p.get("rubber"), at(0, 0.05, -0.067), (0.087, 0.157, 0.012), 0.01, steps=2)
    blob(p.get("trim"), 0, 0.055, -0.038, (0.084, 0.148, 0.038), e=3.2)
    blob(p.get("paint"), 0, 0.15, -0.042, (0.07, 0.052, 0.032), e=2.6)
    mk.rounded_box(p.get("dark"), at(0, -0.078, -0.03), (0.064, 0.042, 0.038), 0.015, steps=2)
    return p.all()


def robot_torso():
    """The chest: a dark segmented belly, a painted chest shell, a trim plate with a glowing core in a chrome ring,
    side vents, a collar and a back pack (the number is painted just behind it, as on the lower tiers)."""
    p = Parts()
    for k, z in enumerate((0.0, 0.07, 0.14)):
        mk.rounded_box(p.get("dark"), at(0, 0, z), (0.15 - 0.01 * k, 0.104, 0.03), 0.02, steps=2)
    blob(p.get("paint"), 0, 0.01, 0.36, (0.244, 0.164, 0.194), e=3.2, seg=24, rings=14)
    mk.rounded_box(p.get("trim"), at(0, 0.153, 0.372), (0.168, 0.022, 0.108), 0.02, steps=3)
    core = facing_y(0, 0.174, 0.38)
    mk.lathe(p.get("chrome"), core, [(0.04, 0.008), (0.056, 0.008), (0.062, 0.002), (0.062, 0.0)], seg=24)
    mk.disc(p.get("lights"), core, 0.042, 0.0, seg=24, z=0.006)
    for s in (-1, 1):
        for k in range(3):
            mk.rounded_box(p.get("dark"), at(s * 0.205, 0.07, 0.43 - k * 0.035), (0.03, 0.06, 0.008), 0.006, steps=1)
        mk.bolt(p.get("chrome"), core.at(s * 0.14, 0.08, -0.004), 0.009, 0.005)
        mk.bolt(p.get("chrome"), core.at(s * 0.14, -0.07, -0.004), 0.009, 0.005)
    mk.rounded_box(p.get("trim"), at(0, 0, 0.528), (0.248, 0.108, 0.03), 0.024, steps=2)
    mk.rounded_box(p.get("dark"), at(0, -0.148, 0.37), (0.13, 0.02, 0.1), 0.014, steps=2)
    return p.all()


def robot_collar_spikes():
    """A boss's spikes along the collar (as the lower tiers' GOLIATH and VOLTRIX)."""
    p = Parts()
    for x in (-1, 1):
        for k in range(3):
            mk.lathe(p.get("trim"), at(x * (0.12 + k * 0.06), 0.02, 0.54),
                     [(0.0, 0.12), (0.012, 0.09), (0.03, 0.02), (0.034, 0.0)], seg=10)
    return p.all()


def robot_head():
    """A helmet in the design's colour with a trim visor frame round a glowing visor, a crest, chrome ear discs, a
    chin guard and a little aerial, on a ringed neck."""
    p = Parts()
    for k in range(4):
        z = -0.005 + k * 0.026
        mk.lathe(p.get("dark"), Frame((0, 0, z)), [(0.0, 0.022), (0.04, 0.022), (0.047, 0.011), (0.04, 0.0), (0.0, 0.0)], seg=16)
    blob(p.get("paint"), 0, 0, 0.18, (0.117, 0.127, 0.117), e=2.6, seg=24, rings=14)
    mk.rounded_box(p.get("trim"), at(0, 0.097, 0.214), (0.12, 0.034, 0.031), 0.015, steps=2)
    mk.rounded_box(p.get("lights"), at(0, 0.127, 0.205), (0.095, 0.005, 0.019), 0.005, steps=1)
    mk.rounded_box(p.get("trim"), at(0, -0.02, 0.3), (0.021, 0.094, 0.04), 0.012, steps=2)
    for s in (-1, 1):
        mk.cylinder(p.get("chrome"), facing_x(s * 0.108, 0, 0.18, s), 0.038, 0.0, 0.016, seg=18, bevel=0.004)
    mk.rounded_box(p.get("dark"), at(0, 0.088, 0.1), (0.07, 0.034, 0.03), 0.014, steps=2)
    mk.rod(p.get("dark"), (0.09, -0.04, 0.26), (0.1, -0.06, 0.345), 0.005, seg=6)
    blob(p.get("lights"), 0.1, -0.06, 0.35, (0.009, 0.009, 0.009), e=2.0, seg=8, rings=6)
    return p.all()


def robot_horns():
    """A boss's horns on the helmet."""
    p = Parts()
    for x in (-1, 1):
        mk.lathe(p.get("trim"), at(x * 0.1, 0, 0.27), [(0.0, 0.16), (0.01, 0.12), (0.022, 0.04), (0.026, 0.0)], seg=10)
    return p.all()


def robot_shoulder():
    """The right shoulder and upper arm (the left is its mirror): a painted pauldron with a trim rim, a dark core and a
    trim bicep guard."""
    p = Parts()
    blob(p.get("paint"), 0.03, 0, 0.025, (0.098, 0.116, 0.084), e=2.6)
    mk.rounded_box(p.get("trim"), at(0.03, 0, -0.045), (0.094, 0.108, 0.014), 0.012, steps=2)
    mk.cylinder(p.get("dark"), Frame(), 0.044, -UPPER + 0.01, -0.03, seg=14)
    blob(p.get("trim"), 0, 0, -0.16, (0.07, 0.072, 0.098), e=2.8)
    mk.lathe(p.get("chrome"), Frame((0, 0, -0.07)), [(0.05, 0.008), (0.054, 0.0), (0.05, -0.008)], seg=16)
    return p.all()


def robot_forearm():
    """The right forearm and fist (the left is its mirror): the elbow's ball, a painted guard with a strip of light on
    its outside, the wrist and a trim fist with a steel knuckle plate and a thumb."""
    p = Parts()
    blob(p.get("dark"), 0, 0, 0, (0.057, 0.057, 0.057), e=2.0, seg=16, rings=10)
    blob(p.get("paint"), 0, 0, -0.13, (0.071, 0.077, 0.113), e=2.8)
    mk.rounded_box(p.get("lights"), at(0.072, 0, -0.13), (0.004, 0.02, 0.052), 0.003, steps=1)
    mk.cylinder(p.get("dark"), Frame(), 0.042, -FORE - 0.01, -0.21, seg=14)
    f = -FORE
    mk.rounded_box(p.get("trim"), at(0, 0.01, f - 0.05), (0.066, 0.07, 0.064), 0.026, steps=3)
    mk.rounded_box(p.get("steel"), at(0, 0.012, f - 0.112), (0.058, 0.06, 0.008), 0.006, steps=1)
    for k in range(4):  # the fingers' joints across the front of the fist
        mk.rounded_box(p.get("dark"), at(-0.045 + k * 0.03, 0.078, f - 0.075), (0.012, 0.004, 0.022), 0.004, steps=1)
    blob(p.get("trim"), -0.05, 0.05, f - 0.035, (0.018, 0.024, 0.03), e=2.4, seg=12, rings=8)
    return p.all()


# ---------- the martial artist ----------
def front_y(rx, ry, rz, cy, cz, x, z):
    """How far forward an oval body's front is at x, z (an ellipsoid of radii rx, ry, rz centred at 0, cy, cz)."""
    k = 1 - (x / rx) ** 2 - ((z - cz) / rz) ** 2
    return cy + ry * math.sqrt(max(0.0, k))


def human_hips():
    """The trousers' seat and top, in the trousers' colour."""
    p = Parts()
    blob(p.get("pants"), 0, 0, 0.02, (0.184, 0.117, 0.098), e=2.4)
    oval_band(p.get("pants"), 0, 0, 0.19, 0.122, [(0.96, 0.135), (1.0, 0.12), (1.0, 0.085), (0.97, 0.07)])
    return p.all()


def human_thigh():
    """A trouser leg from the hip to the knee, a little baggy."""
    p = Parts()
    mk.lathe(p.get("pants"), Frame(), [(0.0, 0.07), (0.05, 0.062), (0.078, 0.035), (0.086, 0.0), (0.088, -0.1),
                                       (0.085, -0.2), (0.081, -0.3), (0.077, -0.4), (0.07, -0.45), (0.0, -0.47)], seg=20)
    for z in (-0.14, -0.28):  # creases
        mk.lathe(p.get("pants"), Frame((0, 0, z)), [(0.083, 0.012), (0.0886, 0.0), (0.083, -0.012)], seg=20)
    return p.all()


def human_shin():
    """The trousers' lower leg with a turned-up hem, and the bare shin and ankle under it."""
    p = Parts()
    mk.lathe(p.get("pants"), Frame(), [(0.0, 0.028), (0.06, 0.022), (0.075, 0.0), (0.073, -0.15), (0.071, -0.3),
                                       (0.077, -0.33), (0.078, -0.355), (0.06, -0.36), (0.04, -0.36)], seg=20)
    mk.tube(p.get("skin"), [(0, 0, -0.3), (0, 0.004, -0.37), (0, 0, -0.43)], [0.047, 0.044, 0.04], seg=14)
    return p.all()


def human_foot():
    """A bare foot with toes, and a padded foot guard in the trim colour over the instep."""
    p = Parts()
    blob(p.get("skin"), 0, 0.045, -0.047, (0.045, 0.105, 0.033), e=2.3)
    blob(p.get("skin"), 0, 0, -0.03, (0.04, 0.042, 0.05), e=2.0, seg=14, rings=8)
    for k in range(5):
        x = -0.026 + k * 0.013
        blob(p.get("skin"), x, 0.146 - abs(k - 1.5) * 0.007, -0.06, (0.0072, 0.012, 0.0085), e=2.0, seg=8, rings=6)
    blob(p.get("glove"), 0, 0.06, -0.026, (0.05, 0.082, 0.026), e=2.6)
    oval_band(p.get("glove"), 0, 0.005, 0.044, 0.046, [(0.98, -0.005), (1.04, -0.015), (1.04, -0.038), (0.98, -0.048)])
    return p.all()


TORSO = (0.197, 0.121, 0.264, 0.0, 0.3)  # the jacket's radii and centre (rx, ry, rz, y, z)


def human_torso():
    """The gi jacket: a chest and a waist, crossed lapels in a darker shade over a V of skin at the neck, and the belt
    in the trim colour with its knot and tails."""
    p = Parts()
    rx, ry, rz, cy, cz = TORSO
    blob(p.get("gi"), 0, cy, cz, (rx, ry, rz), e=2.4, seg=24, rings=14)
    blob(p.get("gi"), 0, 0, 0.1, (0.167, 0.117, 0.134), e=2.4)
    blob(p.get("skin"), 0, front_y(rx, ry, rz, cy, cz, 0, 0.47) - 0.012, 0.47, (0.058, 0.02, 0.07), e=2.2)
    for s in (-1, 1):  # the lapels, from behind the neck over the shoulder down to the belt, crossing
        path = []
        for t in [k / 8 for k in range(9)]:
            x = s * (0.085 - 0.15 * t)
            z = 0.545 - 0.45 * t
            path.append((x, front_y(rx + 0.004, ry + 0.006, rz + 0.004, cy, cz, x, min(z, 0.53)) + 0.004, z))
        mk.tube(p.get("shade"), path, 0.012, seg=8)
    mk.lathe(p.get("shade"), Frame((0, -0.02, 0.52)), [(0.052, 0.035), (0.062, 0.02), (0.064, 0.0), (0.06, -0.012)], seg=20)
    oval_band(p.get("belt"), 0, 0, 0.176, 0.124, [(0.97, 0.082), (1.0, 0.072), (1.0, 0.028), (0.97, 0.018)])
    blob(p.get("belt"), 0, 0.128, 0.05, (0.03, 0.017, 0.026), e=2.2, seg=12, rings=8)
    for s in (-1, 1):  # the belt's tails
        mk.tube(p.get("belt"), [(s * 0.012, 0.134, 0.04), (s * 0.03, 0.14, -0.02), (s * 0.045, 0.136, -0.1)], 0.011, seg=8)
    return p.all()


def human_chest():
    """A boss's broad chest under the jacket (KRAGG's)."""
    p = Parts()
    blob(p.get("gi"), 0, 0.055, 0.36, (0.2, 0.085, 0.11), e=2.4)
    return p.all()


HEAD = (0.1, 0.108, 0.124, 0.01, 0.17)  # the head's radii and centre (rx, ry, rz, y, z)


def face_y(x, z, lift=0.0):
    rx, ry, rz, cy, cz = HEAD
    return front_y(rx, ry, rz, cy, cz, x, z) + lift


def human_head():
    """The head and neck: skin, ears, and a face: eyes with irises, brows, a nose and a mouth."""
    p = Parts()
    rx, ry, rz, cy, cz = HEAD
    mk.tube(p.get("skin"), [(0, -0.005, -0.01), (0, 0, 0.05), (0, 0.005, 0.1)], 0.048, seg=14, caps=False)
    blob(p.get("skin"), 0, cy, cz, (rx, ry, rz), e=2.0, seg=26, rings=16)
    for s in (-1, 1):
        blob(p.get("skin"), s * 0.098, 0.0, 0.168, (0.012, 0.021, 0.03), e=2.2, seg=10, rings=8)
        x, z = s * 0.037, 0.186
        y = face_y(x, z)
        blob(p.get("eye"), x, y - 0.006, z, (0.017, 0.008, 0.011), e=2.0, seg=12, rings=8)
        mk.disc(p.get("iris"), facing_y(x, y + 0.0015, z), 0.0075, 0.0, seg=12)
        mk.disc(p.get("black"), facing_y(x, y + 0.0018, z), 0.0034, 0.0, seg=10)
        brow = Frame((x, face_y(x, 0.207, 0.002), 0.207)).turned("y", s * 8)
        mk.rounded_box(p.get("hair"), brow, (0.018, 0.004, 0.0035), 0.003, steps=1)
    blob(p.get("skin"), 0, face_y(0, 0.165) - 0.002, 0.165, (0.012, 0.02, 0.021), e=2.2, seg=12, rings=8)
    mk.rounded_box(p.get("lips"), at(0, face_y(0, 0.13) - 0.002, 0.13), (0.019, 0.004, 0.0045), 0.003, steps=1)
    return p.all()


def human_hair():
    """Spiky hair: a cap of it and spikes over the top and front."""
    p = Parts()
    hair = p.get("hair")
    blob(hair, 0, -0.016, 0.215, (0.106, 0.112, 0.085), e=2.2, seg=22, rings=12)
    for k in range(9):
        a = k * 2 * math.pi / 9
        out = (math.cos(a) * 0.5, math.sin(a) * 0.5 - 0.1, 1.0)
        n = mk.norm(out)
        base = (math.cos(a) * 0.045, -0.016 + math.sin(a) * 0.045, 0.28)
        side = mk.norm(mk.cross(n, (0, 1, 0) if abs(n[1]) < 0.9 else (1, 0, 0)))
        mk.lathe(hair, Frame(base, side, mk.cross(n, side), n), [(0.0, 0.085), (0.012, 0.05), (0.026, 0.0)], seg=8)
    for x in (-0.05, -0.02, 0.015, 0.045):  # the fringe, swept forward over the brow
        n = mk.norm((x * 2, 0.8, 0.45))
        side = mk.norm(mk.cross(n, (0, 0, 1)))
        mk.lathe(hair, Frame((x, 0.07, 0.255), side, mk.cross(n, side), n), [(0.0, 0.06), (0.012, 0.03), (0.02, 0.0)], seg=8)
    for s in (-1, 1):  # the headband's tails at the back
        f = Frame((s * 0.022, -0.14, 0.235)).turned("x", 28).turned("y", s * 10)
        mk.rounded_box(p.get("belt"), f, (0.014, 0.062, 0.004), 0.003, steps=1)
    return p.all()


def human_headband():
    """The headband in the trim colour, round the head above the brow."""
    p = Parts()
    oval_band(p.get("belt"), 0, 0.01, 0.0775, 0.0855, [(0.98, 0.271), (1.04, 0.264), (1.04, 0.246), (0.98, 0.239)])
    blob(p.get("belt"), 0, -0.083, 0.255, (0.022, 0.014, 0.016), e=2.2, seg=10, rings=6)
    return p.all()


def kragg_mohawk():
    """KRAGG's mohawk: a crest of fins along the top of his head."""
    p = Parts()
    for k in range(7):
        y = 0.075 - k * 0.03
        z = 0.292 - abs(k - 3) * 0.008
        blob(p.get("hair"), 0, y, z, (0.012, 0.02, 0.045 - abs(k - 3) * 0.004), e=2.4, seg=10, rings=8)
    return p.all()


def shade_mask():
    """SHADE's ninja mask over the whole head, its eye slit glowing."""
    p = Parts()
    rx, ry, rz, cy, cz = HEAD
    blob(p.get("gi"), 0, cy, cz + 0.002, (rx + 0.008, ry + 0.012, rz + 0.008), e=2.1, seg=26, rings=16)
    y = front_y(rx + 0.008, ry + 0.012, rz + 0.008, cy, cz + 0.002, 0, 0.186)
    mk.rounded_box(p.get("black"), at(0, y - 0.004, 0.186), (0.074, 0.006, 0.016), 0.005, steps=1)
    mk.rounded_box(p.get("lights"), at(0, y - 0.0015, 0.186), (0.068, 0.004, 0.0105), 0.004, steps=1)
    blob(p.get("shade"), 0, -0.104, 0.205, (0.026, 0.02, 0.018), e=2.2, seg=12, rings=8)  # (the knot at the back)
    return p.all()


def human_shoulder():
    """A gi sleeve from the shoulder to the elbow, opening a little at its end."""
    p = Parts()
    blob(p.get("gi"), 0, 0, 0, (0.088, 0.088, 0.084), e=2.2)
    mk.lathe(p.get("gi"), Frame(), [(0.0, 0.03), (0.074, 0.0), (0.075, -0.1), (0.078, -0.2), (0.083, -0.28),
                                    (0.084, -0.3), (0.07, -0.305), (0.05, -0.3)], seg=20)
    return p.all()


def human_forearm():
    """The right forearm (the left is its mirror): bare, a white wrap at the wrist, and a padded glove in the trim
    colour with a cuff and a thumb."""
    p = Parts()
    mk.tube(p.get("skin"), [(0, 0, 0.02), (0, 0.004, -0.1), (0, 0, -0.2)], [0.052, 0.05, 0.043], seg=14)
    mk.lathe(p.get("wrap"), Frame(), [(0.044, -0.185), (0.051, -0.19), (0.052, -0.225), (0.046, -0.23)], seg=16)
    f = -FORE
    mk.lathe(p.get("glove"), Frame(), [(0.048, f + 0.04), (0.057, f + 0.032), (0.058, f + 0.005), (0.052, f - 0.005)], seg=18)
    blob(p.get("glove"), 0, 0.012, f - 0.042, (0.057, 0.067, 0.061), e=2.4)
    blob(p.get("glove"), -0.044, 0.046, f - 0.02, (0.019, 0.021, 0.03), e=2.2, seg=12, rings=8)
    mk.rounded_box(p.get("belt"), at(0, 0.074, f - 0.04), (0.04, 0.004, 0.022), 0.004, steps=1)
    return p.all()


PIECES = {
    "robot_hips": robot_hips, "robot_thigh": robot_thigh, "robot_shin": robot_shin, "robot_foot": robot_foot,
    "robot_torso": robot_torso, "robot_collar_spikes": robot_collar_spikes, "robot_head": robot_head,
    "robot_horns": robot_horns, "robot_shoulder_r": robot_shoulder, "robot_shoulder_l": lambda: mirrored(robot_shoulder()),
    "robot_forearm_r": robot_forearm, "robot_forearm_l": lambda: mirrored(robot_forearm()),
    "human_hips": human_hips, "human_thigh": human_thigh, "human_shin": human_shin, "human_foot": human_foot,
    "human_torso": human_torso, "human_chest": human_chest, "human_head": human_head, "human_hair": human_hair,
    "human_headband": human_headband, "kragg_mohawk": kragg_mohawk, "shade_mask": shade_mask,
    "human_shoulder": human_shoulder, "human_forearm_r": human_forearm,
    "human_forearm_l": lambda: mirrored(human_forearm()),
}


# ---------- where the pieces go ----------
def layout(body, model=None):
    """Where each piece goes for a fighter of this body ("robot", or anything else built as a human: fight_gfx's
    rule) and model (a boss's name, or None): [(joint, piece, pos, hpr, scale)], in each joint's frame. A boss is
    wider (BIG), as the lower tiers make it, and has its own extras (spikes, horns, KRAGG's mohawk and chest,
    SHADE's mask)."""
    big = BIG if model else 1.0
    one, wide = (1.0, 1.0, 1.0), (big, 1.0, 1.0)
    origin, flat = (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    out = []
    if body == "robot":
        out += [("hips", "robot_hips", origin, flat, wide), ("waist", "robot_torso", origin, flat, wide),
                ("neck", "robot_head", origin, flat, one)]
        for s in ("l", "r"):
            out += [(s + "s", f"robot_shoulder_{s}", origin, flat, wide), (s + "e", f"robot_forearm_{s}", origin, flat, wide),
                    (s + "h", "robot_thigh", origin, flat, wide), (s + "k", "robot_shin", origin, flat, wide),
                    (s + "a", "robot_foot", origin, flat, wide)]
        if model:
            out += [("waist", "robot_collar_spikes", origin, flat, one), ("neck", "robot_horns", origin, flat, one)]
        return out
    limb = (big, big, 1.0)
    out += [("hips", "human_hips", origin, flat, wide), ("waist", "human_torso", origin, flat, wide),
            ("neck", "human_head", origin, flat, one), ("neck", "human_headband", origin, flat, one)]
    for s in ("l", "r"):
        out += [(s + "s", "human_shoulder", origin, flat, limb), (s + "e", f"human_forearm_{s}", origin, flat, limb),
                (s + "h", "human_thigh", origin, flat, limb), (s + "k", "human_shin", origin, flat, limb),
                (s + "a", "human_foot", origin, flat, one)]
    if model == "SHADE":
        out.append(("neck", "shade_mask", origin, flat, one))
    elif model == "KRAGG":
        out.append(("neck", "kragg_mohawk", origin, flat, one))
    else:
        out.append(("neck", "human_hair", origin, flat, one))
    if model:
        out.append(("waist", "human_chest", origin, flat, wide))
    return out


def fighter():
    """Every piece, as models/fight_ultra.json holds it."""
    pieces = {name: [p.packed() for p in parts] for name, parts in kit().items()}
    tris = {name: sum(p.tris() for p in parts) for name, parts in kit().items()}
    return {"version": VERSION, "roles": ROLES, "pieces": pieces,
            "notes": {"frame": "each piece in its joint's frame: x to the fighter's right, y forward, z up, metres, at "
                               "the standard size (the body node's scale, the design's size, makes the whole fighter "
                               "bigger or smaller); triangles anticlockwise seen from outside",
                      "layout": "where each piece goes: fight_models.layout(body, model) in the window's code "
                                "(BeatEmUp/fight_models.py), mirrored by the page: body is the design's body (\"robot\", "
                                "or anything else is built as a human, as the lower tiers do), model a boss's name or "
                                "null",
                      "joints": "fight_gfx.FighterVisual's skeleton (the page's fight.js JOINTS): hips at HIP_H 0.92 "
                                "over the feet (turned by the poses), waist 0.1 over the hips, neck 0.5 over the waist, "
                                "shoulders (ls, rs) at x -/+ (0.25 robot, 0.2 human; 0.04 more for a boss), y 0, z 0.44 "
                                "on the waist, elbows (le, re) 0.29 down the shoulders' -z, hips' joints (lh, rh) at x "
                                "-/+ 0.11 on the hips, knees (lk, rk) 0.42 down, ankles (la, ra) 0.42 down; the fists "
                                "are part of the forearms' pieces (0.26 down le and re)",
                      "roles": "colour null: the design's colour; \"trim\", \"skin\": the style's; \"hair\": the "
                               "fighter's hair colour (from its name, fight_gfx.FighterVisual.hair_colour); \"pants\": "
                               "the design's colour times 0.55; \"shade\": times 0.78; \"lips\": the skin times (0.85, "
                               "0.62, 0.6); emission \"lights\": the style's lights colour (screen colour) times 5",
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
        print(f"{name:20s} {sum(p.tris() for p in parts):6d} triangles  ({', '.join(p.material for p in parts)})")
    print(f"built in {time.perf_counter() - t:.2f} s")
