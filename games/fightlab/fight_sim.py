"""Fight Lab physics: fighters built from a learner's design, moves, blocking, combos, specials, rings and rounds.

A 3D ring fighter (like Soul Calibur and Tekken): the two fighters always face each other, forward and back
close the gap, and SIDESTEP circles round the other fighter. Straight attacks are aimed when they start, so a
well-timed sidestep makes them miss. Spinning attacks hit all the way round, so they catch a sidestep.

A design is plain data a learner can read and change:
    body     - "robot" (a fighting robot) or "human" (a martial artist): how the fighter looks
    points   - 100 points shared between power, speed, defence and stamina
    settings - percentages that tune how the fighter uses what the points bought
    special  - blast (a shot), uppercut, spin_kick or slam: the special move (it uses energy)
    combo    - a list of 2 to 5 moves ("punch", "kick", "low", "high"): pressing punch again after a hit
               lands does the next move in your list

Heights matter: "high" attacks miss a crouching fighter, "low" attacks miss a jumping one and are blocked only
by a low block, "mid" attacks are blocked only standing (they hit a crouching fighter), jump attacks ("overhead")
are blocked only standing, and throws can't be blocked at all. So: block standing, and watch for the low sweep.

Rounds: practice (no damage, like a game's training mode) or battle (rounds, a timer, knockouts and ring-outs).
No graphics here: this runs on the teacher's server.
"""
import math
import random
from collections import namedtuple

STEP = 1 / 60

# Game rules. mods/rules.py can change any of these (the teacher approves every change).
DEFAULT_RULES = {
    "round_seconds": 60,        # length of a round in a battle
    "damage_multiplier": 1.0,   # all attack damage is multiplied by this
    "chip_damage": 0.1,         # share of an attack's damage that still gets through a block
    "combo_scaling": 0.85,      # each extra hit in a combo does this share of the one before
    "knockback": 1.0,           # how far hits push fighters back
    "gravity": 9.81,            # m/s squared: lower is floatier jumps and longer juggles
    "special_cost": 50,         # energy a special move uses (the meter holds 100)
    "energy_gain": 1.0,         # how quickly the energy meter fills
    "ring_size": 4.5,           # the ring's radius in metres
    "hazard_damage": 1.0,       # electric ropes and fire jets damage multiplier
    "fire_jet_every": 5.0,      # seconds between fire jet bursts
}
RULES = dict(DEFAULT_RULES)

# ---------- the design sheet ----------

STATS = ("power", "speed", "defence", "stamina")
POINTS_TOTAL, STAT_MIN, STAT_MAX = 100, 5, 50
SETTINGS = {  # name: (lowest, highest, default, what it means)
    "walk_speed": (10, 100, 80, "% of your top walking speed"),
    "sidestep_speed": (10, 100, 70, "% of your fastest sidestep"),
    "jump_height": (10, 100, 70, "% of your highest jump"),
    "attack_speed": (10, 100, 70, "% attack speed: faster attacks come out sooner but hit softer"),
    "size": (80, 120, 100, "% of standard size: bigger reaches further and has more health, but is slower"),
}
BODIES = {"robot": "a fighting robot: metal armour and glowing eyes",
          "human": "a martial artist: quick hands and a headband",
          "woman": "a detailed 3D woman (Penthesilea's model): choose her outfit, hair, shape and height",
          "man": "a detailed 3D man (Achilles' model): choose his outfit, hair, shape and height",
          "robin": "Robin, a detailed 3D robot: metal plating in your colour, with trim and light colours"}
# how the detailed 3D bodies look (it changes nothing about how they fight): the design's "look" dictionary
MODEL_BODIES = ("woman", "man", "robin")
HUMAN_BODIES = ("woman", "man")  # (the detailed bodies with outfits and hair; Robin has plating)
ROBIN_STYLE = {"trim": [140, 145, 155], "lights": [255, 90, 25]}  # Robin's trim and lights unless the design says
OUTFITS = {
    "hoplite": "Greek hoplite: bronze armour over a tunic, with leather strips and sandals",
    "greek": "light Greek warrior: a short tunic, bracers and sandals",
    "commando": "army commando: camouflage, a tactical vest and boots",
    "training": "training kit: a fitted lycra top and leggings, trainers",
    "civilian": "everyday clothes: T-shirt, jeans and trainers",
    "warrior": "warrior armour (fantasy style): an armoured top, bare midriff, plated shorts, spiked pauldrons and boots",
}
HAIR_STYLES = {"woman": ["ponytail", "braid", "long", "bob", "short", "afro"],
               "man": ["short", "classic", "spiky", "crop", "afro", "long"]}
SHAPES = {"athletic": "athletic", "muscly": "muscly", "full": "full-bodied"}
WINS = {"victory": "a victory celebration", "dance": "a hip hop dance", "bow": "a formal bow",
        "power_up": "a power-up roar"}  # what they do when they win
HEIGHT_MIN, HEIGHT_MAX = 90, 110  # percent: taller or shorter to look at (the size setting changes the fight)


def default_look(body):
    if body not in HUMAN_BODIES:  # Robin: a frame and a height, no clothes or hair
        return {"shape": "athletic", "height": 100, "win": "victory"}
    return {"outfit": "hoplite", "hair": HAIR_STYLES.get(body, ["short"])[0], "hair_colour": [70, 40, 25],
            "shape": "athletic", "height": 100, "win": "victory"}


def check_look(body, look):
    """Problems with a detailed body's look (empty = fine)."""
    if not isinstance(look, dict):
        return ["look must be a dictionary"]
    problems = []
    if body in HUMAN_BODIES:
        if look.get("outfit") not in OUTFITS:
            problems.append(f"look outfit must be one of {', '.join(OUTFITS)}")
        if look.get("hair") not in HAIR_STYLES.get(body, []):
            problems.append(f"look hair must be one of {', '.join(HAIR_STYLES.get(body, []))}")
        c = look.get("hair_colour")
        if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and not isinstance(v, bool)
                                                            and 0 <= v <= 255 for v in c)):
            problems.append("look hair_colour must be three whole numbers from 0 to 255")
    if look.get("shape") not in SHAPES:
        problems.append(f"look shape must be one of {', '.join(SHAPES)}")
    h = look.get("height")
    if not isinstance(h, (int, float)) or isinstance(h, bool) or not HEIGHT_MIN <= h <= HEIGHT_MAX:
        problems.append(f"look height must be from {HEIGHT_MIN} to {HEIGHT_MAX}")
    if look.get("win", "victory") not in WINS:
        problems.append(f"look win must be one of {', '.join(WINS)}")
    return problems
SPECIALS = {
    "blast": "energy blast: a shot that flies across the ring (sidestep or jump it!)",
    "uppercut": "rising uppercut: launches them into the air, and can't be hit as it starts",
    "spin_kick": "spinning kick: hits all the way round, so a sidestep won't escape it",
    "slam": "power slam: a grab that goes through blocks, but only at close range",
}
COMBO_MOVES = {"punch": "a quick jab (high)", "kick": "a front kick (mid)",
               "low": "a sweep (low: block it crouching)", "high": "a high kick that launches (high)"}
COMBO_MIN, COMBO_MAX = 2, 5

# ---------- fighting styles and weapons ----------
# A style changes what the four attack buttons do: each move's name, and its damage, reach and time compared with
# the kick boxer's (1.0 = the same; a time above 1 is slower). The buttons, combos and brains work the same in
# every style. An armed style also has a choice of weapon, which changes the moves made with it.
STYLES = {
    "kickboxer": "kick boxer: quick punches and strong kicks (no weapon)",
    "boxer": "boxer: the fastest, hardest punches and quick footwork, but short reach and no kicks",
    "capoeira": "capoeira: long sweeping kicks and spins, and quick sidesteps, but weak punches",
    "knives": "knife fighter: very quick stabs and slashes, with a little more reach than a fist",
    "swords": "sword fighter: long reach and heavy cuts, but slower",
    "sticks": "stick fighter: quick strikes with good reach",
}
STYLE_MOVES = {  # style: {button move: (what it is, damage, reach, time)}
    "kickboxer": {"punch": ("jab", 1.0, 1.0, 1.0), "kick": ("front kick", 1.0, 1.0, 1.0),
                  "low": ("low sweep", 1.0, 1.0, 1.0), "high": ("high kick", 1.0, 1.0, 1.0)},
    "boxer": {"punch": ("jab", 1.2, 0.95, 0.85), "kick": ("body hook", 1.05, 0.8, 0.8),
              "low": ("ducking body blow", 1.0, 0.8, 0.85), "high": ("uppercut", 1.1, 0.85, 0.9)},
    "capoeira": {"punch": ("martelo (round kick)", 0.95, 0.85, 0.92), "kick": ("bencao (push kick)", 1.05, 1.05, 1.04),
                 "low": ("rasteira (sweep)", 1.0, 1.06, 1.04), "high": ("meia lua (spinning kick)", 1.05, 1.06, 1.08)},
    "knives": {"punch": ("stab", 0.8, 1.04, 0.92), "kick": ("front kick", 0.95, 1.0, 1.0),
               "low": ("low slash", 0.8, 1.0, 0.95), "high": ("rising slash", 0.85, 1.0, 0.95)},
    "swords": {"punch": ("thrust", 1.0, 1.12, 1.25), "kick": ("kick", 0.95, 1.0, 1.05),
               "low": ("low cut", 0.95, 1.1, 1.25), "high": ("rising cut", 0.95, 1.08, 1.25)},
    "sticks": {"punch": ("strike", 0.9, 1.07, 1.1), "kick": ("kick", 0.95, 1.0, 1.0),
               "low": ("low strike", 0.9, 1.05, 1.1), "high": ("rising strike", 0.9, 1.05, 1.12)},
}
STYLE_MOVEMENT = {"boxer": {"sidestep": 1.1}, "capoeira": {"sidestep": 1.15, "jump": 1.05}}  # (x the usual)
WEAPONS = {  # weapon: (style, what it is, damage, reach, time) for the moves made with it
    "knife": ("knives", "combat knife", 1.0, 1.0, 1.0),
    "dagger": ("knives", "Greek dagger: a longer blade, a little slower", 1.02, 1.04, 1.06),
    "sword_shield": ("swords", "short sword and shield: blocking with the shield lets no damage through", 1.0, 1.0, 1.0),
    "longsword": ("swords", "long sword, in both hands: more reach and damage, but slower", 1.06, 1.05, 1.06),
    "katana": ("swords", "katana, in both hands: quicker cuts, but lighter", 0.92, 1.0, 0.94),
    "stick": ("sticks", "escrima stick: quick", 1.0, 1.0, 1.0),
    "staff": ("sticks", "bo staff, in both hands: the longest reach, but slower", 0.96, 1.05, 1.1),
    "glaive": ("sticks", "glaive, in both hands: a blade on a long pole, heavier and slower", 1.02, 1.05, 1.14),
}
WEAPON_MOVES = ("punch", "low", "high")  # the moves made with the weapon (a kick is still a kick)


def weapons_for(style):
    return [w for w, spec in WEAPONS.items() if spec[0] == style]


def style_of(d):
    """A design's fighting style and weapon (designs from before styles are kick boxers). (A design's "style" is
    something else: how a robot looks.)"""
    style = d.get("fighting_style", "kickboxer")
    if style not in STYLES:
        style = "kickboxer"
    return style, (d.get("weapon") if weapons_for(style) else None)


def move_mods(style, weapon, name):
    """(damage, reach, time) multipliers for a move in this style with this weapon."""
    dmg, reach, time = STYLE_MOVES.get(style, {}).get(name, ("", 1.0, 1.0, 1.0))[1:]
    if weapon in WEAPONS and name in WEAPON_MOVES:
        _, _, wd, wr, wt = WEAPONS[weapon]
        dmg, reach, time = dmg * wd, reach * wr, time * wt
    return dmg, reach, time


def move_name(style, name):
    """What a button's move is called in a style ('jab', 'thrust'...)."""
    return STYLE_MOVES.get(style, {}).get(name, (name.replace("_", " "),))[0]

# Boss fighters: big and strong, with fixed stats. The teacher can make one the computer's fighter,
# and learners can play as one when the teacher allows it.
BOSSES = (  # name, body, special, colour, trim, lights
    ("GOLIATH", "robot", "slam", (70, 74, 82), (235, 180, 30), (255, 60, 30)),
    ("VOLTRIX", "robot", "blast", (30, 90, 200), (220, 225, 235), (90, 230, 255)),
    ("KRAGG", "human", "uppercut", (120, 40, 30), (30, 25, 20), (240, 200, 60)),
    ("SHADE", "human", "spin_kick", (25, 25, 35), (150, 40, 190), (200, 120, 255)),
)
BOSS_BY_NAME = {name: (body, special, colour, trim, lights) for name, body, special, colour, trim, lights in BOSSES}
BOSS_STATS = {"size": 1.3, "health": 260.0, "damage": 1.35, "taken": 0.8, "walk": 1.9, "sidestep": 1.8,
              "jump": 3.3, "attack_time": 1.1, "reach": 1.3, "energy_rate": 5.0, "getup": 0.8}


def default_design(name="Fighter", colour=(200, 120, 40), special="blast", body="robot"):
    d = {"name": name, "body": body, "colour": list(colour), "special": special,
         "points": {k: 25 for k in STATS},
         "settings": {k: v[2] for k, v in SETTINGS.items()},
         "combo": ["punch", "punch", "kick"], "fighting_style": "kickboxer"}
    if body in MODEL_BODIES:
        d["look"] = default_look(body)
    if body == "robin":
        d["style"] = {k: list(v) for k, v in ROBIN_STYLE.items()}
    return d


def boss_design(name):
    body, special, colour, trim, lights = BOSS_BY_NAME[name]
    d = default_design(name, colour, special, body)
    d.update(model=name, boss=True, style={"trim": list(trim), "lights": list(lights), "number": name[:10]})
    return d


def check_design(d):
    """Return a list of problems (empty = fine). Used by the server and shown to learners."""
    problems = []
    if not isinstance(d, dict):
        return ["the design must be a dictionary"]
    pts = d.get("points", {})
    if not isinstance(pts, dict) or set(pts) != set(STATS):
        problems.append(f"points must have exactly: {', '.join(STATS)}")
    else:
        for k, v in pts.items():
            if not isinstance(v, int) or isinstance(v, bool) or not STAT_MIN <= v <= STAT_MAX:
                problems.append(f"{k} must be a whole number from {STAT_MIN} to {STAT_MAX}")
        if all(isinstance(v, int) for v in pts.values()) and sum(pts.values()) > POINTS_TOTAL:
            problems.append(f"{sum(pts.values())} points used: the most you can spend is {POINTS_TOTAL}")
    settings = d.get("settings", {})
    for k, (lo, hi, _, _) in SETTINGS.items():
        v = settings.get(k) if isinstance(settings, dict) else None
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
            problems.append(f"{k} must be from {lo} to {hi}")
    if d.get("body") not in BODIES:
        problems.append(f"body must be one of {', '.join(BODIES)}")
    elif d.get("body") in MODEL_BODIES and "look" in d:
        problems += check_look(d["body"], d["look"])
    combo = d.get("combo")
    if not isinstance(combo, list):
        problems.append("combo must be a list, for example [\"punch\", \"punch\", \"kick\"]")
    elif not COMBO_MIN <= len(combo) <= COMBO_MAX:
        problems.append(f"combo must have {COMBO_MIN} to {COMBO_MAX} moves (it has {len(combo)})")
    elif any(m not in COMBO_MOVES for m in combo):
        problems.append(f"each combo move must be one of {', '.join(COMBO_MOVES)}")
    style = d.get("fighting_style", "kickboxer")
    if style not in STYLES:
        problems.append(f"fighting_style must be one of {', '.join(STYLES)}")
    elif weapons_for(style):
        if d.get("weapon") not in weapons_for(style):
            problems.append(f"a {style} fighter's weapon must be one of {', '.join(weapons_for(style))}")
    elif d.get("weapon") is not None:
        problems.append(f"a {style} fighter has no weapon (leave weapon out)")
    if "model" in d:
        if d["model"] not in BOSS_BY_NAME:
            problems.append(f"model must be one of {', '.join(BOSS_BY_NAME)} (or leave it out)")
        elif d.get("special") != BOSS_BY_NAME[d["model"]][1]:
            problems.append(f"{d['model']}'s special is {BOSS_BY_NAME[d['model']][1]}")
    elif d.get("special") not in SPECIALS:
        problems.append(f"special must be one of {', '.join(SPECIALS)}")
    return problems


def build_stats(d):
    """Turn a design into fighting numbers. Kept simple so learners can read the formulas."""
    if d.get("model") in BOSS_BY_NAME:
        return dict(BOSS_STATS)
    p, s = d["points"], d["settings"]
    size = s["size"] / 100
    perk = STYLE_MOVEMENT.get(style_of(d)[0], {})
    quick = 1.15 - 0.006 * p["speed"]                                   # 1.0 with 25 speed points
    return {
        "size": size,
        "health": (80 + 3 * p["stamina"]) * size ** 2,                  # hit points: 155 with 25 points
        "damage": (0.6 + 0.02 * p["power"]) * (1.3 - 0.43 * s["attack_speed"] / 100),  # x1.1 with 25 points
        "taken": 1.25 - 0.01 * p["defence"],                           # share of damage you take: 1.0 with 25
        "walk": (1.6 + 0.05 * p["speed"]) * s["walk_speed"] / 100 / size ** 0.5,          # m/s
        "sidestep": (2.0 + 0.05 * p["speed"]) * s["sidestep_speed"] / 100 / size ** 0.5 * perk.get("sidestep", 1),
        "jump": (3.0 + 0.03 * p["speed"]) * math.sqrt(s["jump_height"] / 100) * perk.get("jump", 1),  # m/s up
        "attack_time": quick * (1.35 - 0.5 * s["attack_speed"] / 100) * size ** 0.5,       # 1.0 = normal
        "reach": size,
        "energy_rate": 2 + 0.08 * p["stamina"],                         # energy per second, all by itself
        "getup": 1.0 - 0.008 * p["stamina"],                            # seconds on the floor after a knockdown
    }


def stats_text(d):
    """The stats readout in the garage (and the showcase)."""
    st = build_stats(d)
    jump_h = st["jump"] ** 2 / (2 * RULES["gravity"])
    return (f"Health {st['health']:.0f}    Damage x{st['damage']:.2f}    Takes x{st['taken']:.2f} damage\n"
            f"Walk {st['walk']:.1f} m/s    Sidestep {st['sidestep']:.1f} m/s    Jump {jump_h:.2f} m high\n"
            f"{move_name(style_of(d)[0], 'punch').capitalize()} comes out in "
            f"{MOVES['punch'].startup * st['attack_time'] * move_mods(*style_of(d), 'punch')[2]:.2f} s    "
            f"Energy +{st['energy_rate']:.1f} a second    Up after {st['getup']:.1f} s")


# ---------- moves ----------
# startup, active, recovery: seconds at normal speed (the fighter's attack_time multiplies them)
# damage, reach (m from the fighter's middle), width (how far to the side it still hits)
# height: high, mid, low, overhead (jump attacks), throw (can't be blocked)
# stun: seconds the other fighter is stuck after a hit (60% of it after a block), push: knockback m/s
# lunge: m/s the attacker steps forward while it starts, effect: what a clean hit does
Move = namedtuple("Move", "startup active recovery damage reach width height stun push lunge effect")
MOVES = {
    "punch": Move(0.10, 0.06, 0.16, 5, 0.95, 0.22, "high", 0.32, 1.2, 0.8, None),
    "kick": Move(0.15, 0.08, 0.24, 9, 1.25, 0.25, "mid", 0.38, 2.0, 0.9, None),
    "low": Move(0.14, 0.08, 0.28, 7, 1.15, 0.30, "low", 0.36, 1.2, 0.5, "trip"),
    "high": Move(0.19, 0.08, 0.30, 11, 1.20, 0.25, "high", 0.42, 1.8, 0.6, "launch"),
    "jump_kick": Move(0.07, 0.22, 0.08, 10, 1.10, 0.30, "overhead", 0.40, 2.0, 0.0, None),
    "throw": Move(0.10, 0.06, 0.40, 12, 0.90, 0.30, "throw", 0.0, 3.0, 0.6, "down"),
    "blast": Move(0.22, 0.08, 0.34, 10, 0.0, 0.30, "mid", 0.40, 2.2, 0.0, None),       # the shot does the hitting
    "uppercut": Move(0.06, 0.14, 0.50, 14, 1.00, 0.30, "mid", 0.50, 1.0, 1.6, "launch"),
    "spin_kick": Move(0.14, 0.36, 0.30, 5, 1.30, 0.0, "mid", 0.30, 2.4, 1.2, "down"),   # hits all round, 3 times
    "slam": Move(0.12, 0.06, 0.45, 18, 1.00, 0.30, "throw", 0.0, 3.5, 1.0, "down"),
    # user mod "cartwheel_kick": slow to start; its damage is a share of their health (CARTWHEEL_SHARE), not this 12
    "cartwheel": Move(0.36, 0.18, 0.42, 12, 1.30, 0.30, "overhead", 0.45, 2.4, 1.4, "down"),
}
CARTWHEEL_SHARE = 0.5  # a clean cartwheel kick takes this share of the other fighter's full health (0.5 = 50%)
ATTACKS = ("punch", "kick", "low", "high")      # what a brain or a key can ask for directly
PRESSES = ATTACKS + ("special", "throw", "jump", "cartwheel")  # one-off actions (cartwheel: a user mod)
HOLDS = ("block", "low_block", "crouch")          # actions that last as long as they are asked for
BLAST_SPEED, BLAST_LIFE = 7.0, 1.4
INTRO_SECONDS = 1.6  # "ROUND 1" before "FIGHT!"

# where the rings are in the stage (the rings are 16 m apart: room for the walkways and lights)
RING_CENTRES = [(0.0, 0.0), (16.0, 0.0), (-16.0, 0.0), (0.0, 16.0), (16.0, 16.0), (-16.0, 16.0)]
MAX_RINGS = len(RING_CENTRES)
JET_ANGLES = (45, 135, 225, 315)
SPIKE_ANGLES = (0, 90, 180, 270)  # spike patches near the edge, between the fire jets
SPIKE_RADIUS = 0.45               # how big each spike patch is (m)


def length(x, y):
    return math.hypot(x, y)


def heading_of(fx, fy):
    """Facing (x, y) to a heading in degrees (0 = facing +y, turning left is positive)."""
    return math.degrees(math.atan2(-fx, fy))


class Fighter:
    RADIUS = 0.35  # at 100% size

    def __init__(self, ring, fid, design, slot, brain=None, owner="Computer"):
        self.ring, self.id, self.design, self.slot = ring, fid, design, slot
        self.name = design["name"]
        self.owner = owner
        self.brain = brain
        self.boss = bool(design.get("boss") or design.get("model"))
        self.stats = build_stats(design)
        self.combo_list = list(design.get("combo") or ["punch", "punch", "kick"])
        self.special = design.get("special", "blast")
        self.style, self.weapon = style_of(design)
        self.control = (0.0, 0.0, "")  # forward, side, held action (block, low_block, crouch or "")
        self.buffer = ("", -9.0)        # a pressed action and when: kept briefly, so a press isn't missed
        self.energy = 0.0
        self.hits = self.damage_dealt = 0
        self.landed = {}               # clean hits landed with each move (for missions and the training readout)
        self.connected = {}            # hits or blocks with each move (it reached them)
        self.last_damage = {}          # the damage each move did last time it landed
        self.finishers = 0             # whole combos landed
        self.wins = 0
        self.reset()

    # ---------- where and what ----------
    def reset(self):
        """Back to the start of a round: full health, at the start spot, facing the middle."""
        cx, cy = self.ring.centre
        side = -1 if self.slot == 0 else 1
        self.x, self.y, self.z = cx + side * 1.6, cy, 0.0
        self.vx = self.vy = self.vz = 0.0
        self.fx, self.fy = -side * 1.0, 0.0
        self.health = self.stats["health"]
        self.state, self.state_t, self.state_len = "idle", 0.0, 0.0
        self.move, self.move_t, self.aim = None, 0.0, (self.fx, self.fy)
        self.hit_done = set()
        self.combo_step, self.chain_open, self.chained = 0, False, False
        self.juggles = 0
        self.combo_taken = 0            # hits taken in the combo happening to us now
        self.jumped_attack = False
        self.invincible_until = -1.0
        self.last_hurt = -9.0
        self.last_zap = self.last_burn = self.last_spiked = -9.0
        self.knocked_out = False
        self.ko_reason = ""
        self.stride, self.walk_dir = 0.0, 0.0
        self.from_combo = False         # this attack came from the combo list (the punch button)
        self.throw_anim = False         # flying from a throw (the windows show it differently)
        self.low_guard = False          # was crouching when a hit or block stunned it (it stays down)
        self.hurt_how = "head"          # how the last clean hit landed: head, body, low, launch or trip

    @property
    def radius(self):
        return self.RADIUS * self.stats["size"]

    @property
    def airborne(self):
        return self.z > 0.02 or self.state in ("jump", "launched")

    @property
    def crouching(self):
        return self.state in ("crouch", "low_block") or self.move == "low" or             (self.state in ("hitstun", "blockstun") and self.low_guard)

    @property
    def free(self):
        """Able to start something new (walk, block, attack)."""
        return self.state in ("idle", "walk", "side", "crouch", "block", "low_block")

    @property
    def heading(self):
        return heading_of(self.fx, self.fy)

    def mods(self, name):
        """(damage, reach, time) multipliers for a move, from this fighter's style and weapon."""
        return move_mods(self.style, self.weapon, name)

    def reach(self, name):
        """How far a move reaches from this fighter's middle (to the other fighter's edge)."""
        return MOVES[name].reach * self.stats["reach"] * self.mods(name)[1]

    def timing(self, name):
        m = MOVES[name]
        k = self.stats["attack_time"] * self.mods(name)[2]
        return m.startup * k, m.active * k, m.recovery * k

    def move_phase(self):
        """'startup', 'active', 'recovery' during an attack, else ''."""
        if self.state != "attack":
            return ""
        s, a, r = self.timing(self.move)
        return "startup" if self.move_t < s else "active" if self.move_t < s + a else "recovery"

    def anim(self):
        """What the windows animate: (name, progress). Attacks: 0-1 startup, 1-2 active, 2-3 recovery."""
        st = self.state
        if st == "attack":
            s, a, r = self.timing(self.move)
            t = self.move_t
            k = t / s if t < s else 1 + (t - s) / a if t < s + a else 2 + min(1.0, (t - s - a) / max(r, 1e-3))
            return self.move, k
        if st == "launched" and self.throw_anim:
            return "thrown", self.state_t
        if st in ("launched", "knockdown") and self.hurt_how == "trip" and not self.knocked_out:
            return "swept", self.state_t  # (swept off their feet: one fall, from the air to the floor)
        if st == "knockdown" and self.knocked_out:
            return "ko", self.state_t
        if st in ("hitstun", "blockstun", "knockdown", "getup"):
            if st == "hitstun":
                st = "hit_low" if self.crouching else "hit_body" if self.hurt_how == "body" else "hitstun"
            return st, min(1.0, self.state_t / max(self.state_len, 1e-3))
        if st == "walk":
            return ("walk_f" if self.walk_dir >= 0 else "walk_b"), self.stride
        if st == "side":
            return ("side_l" if self.walk_dir >= 0 else "side_r"), self.stride
        if st == "jump":
            j = max(self.stats["jump"], 0.1)
            return "jump", max(0.0, min(1.0, 0.5 - self.vz / (2 * j)))
        return st, self.state_t

    def set_state(self, state, secs=0.0):
        self.state, self.state_t, self.state_len = state, 0.0, secs
        if state != "attack":
            self.move = None

    def press(self, action, now):
        if action == "cartwheel" and not self.ring.stage.user_mods["cartwheel_kick"]:
            return  # (a user mod: nothing happens until the teacher switches it on)
        if action in PRESSES:
            self.buffer = (action, now)

    def energy_add(self, amount):
        self.energy = max(0.0, min(100.0, self.energy + amount * RULES["energy_gain"]))


class Projectile:
    def __init__(self, owner, x, y, z, dx, dy, damage):
        self.owner, self.x, self.y, self.z, self.dx, self.dy = owner, x, y, z, dx, dy
        self.damage, self.life = damage, BLAST_LIFE


class Ring:
    """One ring: up to two fighters, their rounds, and the hazards."""

    def __init__(self, stage, index):
        self.stage, self.index = stage, index
        self.centre = RING_CENTRES[index]
        self.fighters = []
        self.projectiles = []
        self.round, self.phase, self.phase_t = 1, "intro", 0.0
        self.banner, self.result = "", ""
        self.round_started = 0.0
        self.hitstop_until = -1.0
        self.last_hit = None         # the training readout: who hit (fighter id), with what, how much, when
        self.label = ""              # e.g. "Semi-final 1" (set by the server for tournaments)
        self.match_over = False
        self.round_winner = None
        self.time_at_end = 0.0
        self.pending = []            # attacks reaching this tick, landed together in resolve_hits

    # ---------- setting up ----------
    def add_fighter(self, design, brain=None, owner="Computer"):
        slot = len(self.fighters)
        f = Fighter(self, self.stage.new_id(), design, slot, brain, owner)
        self.fighters.append(f)
        self.new_match()
        return f

    def remove_fighter(self, f):
        if f in self.fighters:
            self.fighters.remove(f)
            for i, g in enumerate(self.fighters):
                g.slot = i
            self.new_match()

    def new_match(self):
        self.round = 1
        self.match_over = False
        self.result = ""
        for f in self.fighters:
            f.wins = 0
            f.energy = 0.0
        self.start_round()

    def start_round(self):
        for f in self.fighters:
            f.reset()
        self.projectiles = []
        self.last_hit = None
        if self.practice or len(self.fighters) < 2:
            self.phase, self.banner = "fight", ""
        else:
            self.phase, self.phase_t = "intro", 0.0
            self.banner = f"ROUND {self.round}"

    @property
    def practice(self):
        return self.stage.practice

    @property
    def size(self):
        return RULES["ring_size"]

    def time_left(self):
        """Seconds left in this round (None in practice, or with nobody to fight)."""
        if self.practice or len(self.fighters) < 2:
            return None
        if self.phase == "intro":
            return float(self.stage.round_seconds)
        if self.phase == "fight":
            return max(0.0, self.stage.round_seconds - (self.stage.time - self.round_started))
        return self.time_at_end

    def enemy_of(self, f):
        return next((g for g in self.fighters if g is not f), None)

    def jets(self):
        cx, cy = self.centre
        return [(cx + math.cos(math.radians(a)) * self.size * 0.55, cy + math.sin(math.radians(a)) * self.size * 0.55)
                for a in JET_ANGLES]

    def jet_power(self, i, now):
        """0 (off) to 1 (full): the jets fire in two pairs, one after the other."""
        if not self.stage.hazards.get("fire_jets"):
            return 0.0
        every = RULES["fire_jet_every"]
        t = (now + (i % 2) * every / 2) % every
        return max(0.0, 1 - abs(t - 0.5) / 0.5) if t < 1.0 else 0.0

    def spikes(self):
        """Where the spike patches are (none if spikes are off)."""
        if not self.stage.hazards.get("spikes"):
            return []
        cx, cy = self.centre
        return [(cx + math.cos(math.radians(a)) * self.size * 0.78, cy + math.sin(math.radians(a)) * self.size * 0.78)
                for a in SPIKE_ANGLES]

    def on_ice(self, f):
        if not self.stage.hazards.get("slippery"):
            return False
        return length(f.x - self.centre[0], f.y - self.centre[1]) < self.size * 0.45

    def event(self, text):
        prefix = f"Ring {self.index + 1}: " if len(self.stage.rings) > 1 else ""
        self.stage.events.append((self.stage.time, prefix + text))

    # ---------- every tick ----------
    def step(self, dt, now):
        self.phase_t += dt
        if self.phase == "intro":
            if self.phase_t > INTRO_SECONDS:
                self.phase, self.banner = "fight", "FIGHT!"
                self.round_started = now
                self.banner_until = now + 0.8
        elif self.phase == "fight" and self.banner == "FIGHT!" and now > getattr(self, "banner_until", 0):
            self.banner = ""
        frozen = now < self.hitstop_until
        for f in self.fighters:
            enemy = self.enemy_of(f)
            if self.phase in ("fight",) and not frozen:
                self.think(f, enemy, now)
            elif self.phase != "fight":
                f.control, f.buffer = (0.0, 0.0, ""), ("", -9.0)
            if not frozen:
                self.tick_fighter(f, enemy, dt, now)
        if not frozen:
            self.resolve_hits(now)
            self.move_projectiles(dt, now)
            self.push_apart()
            for f in self.fighters:
                self.edges(f, now)
                self.hazards(f, now)
        self.check_round(now)

    def think(self, f, enemy, now):
        """A brain (the computer's, or a learner's autopilot) decides what to do."""
        if f.brain is None or f.knocked_out:
            return
        try:
            out = f.brain(f, enemy, self)
            fwd, side, action = out
            fwd, side = max(-1.0, min(1.0, float(fwd))), max(-1.0, min(1.0, float(side)))
        except Exception:
            fwd, side, action = 0.0, 0.0, ""
        action = action if isinstance(action, str) else ""
        f.control = (fwd, side, action if action in HOLDS else "")
        if action in PRESSES:
            f.press(action, now)

    def tick_fighter(self, f, enemy, dt, now):
        f.state_t += dt
        st = f.stats
        # energy fills by itself
        if self.phase == "fight" and not f.knocked_out:
            f.energy_add(st["energy_rate"] * dt)
        # face the other fighter (not while an attack is on its way: that is what a sidestep beats)
        if enemy is not None and f.state not in ("attack", "knockdown", "getup", "ringout", "launched"):
            dx, dy = enemy.x - f.x, enemy.y - f.y
            d = length(dx, dy)
            if d > 0.05:
                f.fx, f.fy = dx / d, dy / d
        fwd, side, hold = f.control
        # ---- timed states ----
        if f.state in ("hitstun", "blockstun") and f.state_t >= f.state_len:
            f.set_state("idle")
            f.combo_taken = 0
        elif f.state == "knockdown" and f.state_t >= f.state_len and not f.knocked_out:
            f.set_state("getup", 0.45)
            f.invincible_until = now + 0.5
        elif f.state == "getup" and f.state_t >= f.state_len:
            f.set_state("idle")
            f.combo_taken = 0
        # ---- an attack in progress ----
        if f.state == "attack":
            self.attack_tick(f, enemy, dt, now)
        # ---- start something new ----
        action, pressed_at = f.buffer
        if action and now - pressed_at > 0.15:
            f.buffer = action, pressed_at = ("", -9.0)
        can_chain = f.state == "attack" and f.chain_open and f.move_phase() != "startup"
        if action and (f.free or can_chain or (f.state == "jump" and not f.jumped_attack)) \
                and self.phase == "fight" and not f.knocked_out:
            if self.start_action(f, action, now, can_chain):
                f.buffer = ("", -9.0)
        # ---- holding block or crouch, and walking ----
        if f.free and self.phase == "fight":
            if hold == "block":
                f.state = "block" if f.state != "block" else f.state
            elif hold == "low_block":
                f.state = "low_block"
            elif hold == "crouch":
                f.state = "crouch"
            elif abs(fwd) > 0.1 or abs(side) > 0.1:
                f.state = "walk" if abs(fwd) >= abs(side) else "side"
            else:
                f.state = "idle"
        # target speed on the floor
        tx = ty = 0.0
        if f.state in ("walk", "side") and self.phase == "fight":
            back = 0.7 if fwd < 0 else 1.0
            px, py = -f.fy, f.fx  # to the left
            tx = f.fx * fwd * st["walk"] * back + px * side * st["sidestep"]
            ty = f.fy * fwd * st["walk"] * back + py * side * st["sidestep"]
            f.walk_dir = fwd if f.state == "walk" else side
            f.stride += dt * (length(tx, ty) + 0.3)
        # physics: gravity, floor, sliding
        if f.airborne:
            f.vz -= RULES["gravity"] * dt
            f.z += f.vz * dt
            if f.z <= 0 and f.vz < 0:
                self.land(f, now)
        else:
            grip = 2.5 if self.on_ice(f) else 18.0
            if f.state in ("hitstun", "blockstun", "knockdown"):
                grip = 1.2 if self.on_ice(f) else 6.0   # slide from a hit
                tx = ty = 0.0
            elif f.state == "attack":
                tx = ty = 0.0
                grip = 3.0 if self.on_ice(f) else 12.0
            a = min(1.0, grip * dt)
            f.vx += (tx - f.vx) * a
            f.vy += (ty - f.vy) * a
        f.x += f.vx * dt
        f.y += f.vy * dt

    def land(self, f, now):
        f.z, f.vz = 0.0, 0.0
        f.juggles = 0
        f.throw_anim = False
        if f.state == "ringout":
            return
        if f.state == "launched" or f.knocked_out:
            f.set_state("knockdown", f.stats["getup"] if not f.knocked_out else 99.0)
            self.stage.impacts.append(((f.x, f.y, 0.1), 6, "land"))
        elif f.state == "attack":  # a jump attack ends when you land
            f.set_state("idle")
        else:
            f.set_state("idle")
        f.jumped_attack = False
        f.vx *= 0.5
        f.vy *= 0.5

    # ---------- attacks ----------
    def start_action(self, f, action, now, chaining=False):
        """Start what was pressed. Returns True if it started."""
        if action == "jump":
            if f.airborne or f.state == "attack":
                return False
            f.vz = f.stats["jump"]
            fwd, side, _ = f.control
            px, py = -f.fy, f.fx
            f.vx = f.fx * fwd * f.stats["walk"] * 0.8 + px * side * f.stats["sidestep"] * 0.6
            f.vy = f.fy * fwd * f.stats["walk"] * 0.8 + py * side * f.stats["sidestep"] * 0.6
            f.z = 0.03
            f.set_state("jump")
            f.jumped_attack = False
            return True
        if f.state == "jump":  # in the air: any attack is a jump kick (one a jump)
            if action in ATTACKS:
                f.jumped_attack = True
                self.begin(f, "jump_kick", now)
                return True
            return False
        if action == "special":
            if f.energy < RULES["special_cost"]:
                return False
            f.energy -= RULES["special_cost"]
            self.begin(f, f.special, now)
            if f.special == "uppercut":
                s, a, r = f.timing("uppercut")
                f.invincible_until = now + s + a * 0.5
            self.event(f"{f.name}: {f.special.replace('_', ' ').upper()}!")
            return True
        if action == "throw":
            self.begin(f, "throw", now)
            return True
        if action == "cartwheel":  # user mod: a cartwheel into a kick (not in the middle of a combo)
            if chaining or not self.stage.user_mods["cartwheel_kick"]:
                return False
            self.begin(f, "cartwheel", now)
            return True
        if action not in ATTACKS:
            return False
        crouched = f.control[2] in ("crouch", "low_block") or f.state in ("crouch", "low_block")
        if action == "punch" and not crouched:
            # the punch button follows your combo list: after a hit lands, the next move in the list
            if chaining and f.combo_step + 1 < len(f.combo_list):
                f.combo_step += 1
                f.chained = True
            else:
                if chaining:
                    return False  # the combo is finished
                f.combo_step, f.chained = 0, False
            self.begin(f, f.combo_list[f.combo_step], now, keep_chain=True)
            return True
        if chaining:
            return False
        if action == "kick" and f.control[0] > 0.5:  # forward + kick: the high kick that launches
            action = "high"
        self.begin(f, "low" if crouched else action, now)
        return True

    def begin(self, f, name, now, keep_chain=False):
        f.set_state("attack")
        f.move, f.move_t = name, 0.0
        f.aim = (f.fx, f.fy)
        f.hit_done = set()
        f.chain_open = False
        f.from_combo = keep_chain
        if not keep_chain:
            f.combo_step, f.chained = 0, False
        f.blast_fired = False
        f.last_multi = -1

    def attack_tick(self, f, enemy, dt, now):
        m = MOVES[f.move]
        s, a, r = f.timing(f.move)
        f.move_t += dt
        t = f.move_t
        if t < s + a * 0.5 and m.lunge and not f.airborne:  # step in as it starts
            f.vx, f.vy = f.aim[0] * m.lunge, f.aim[1] * m.lunge
        if s <= t < s + a and enemy is not None:
            if f.move == "blast":
                if not f.blast_fired:
                    f.blast_fired = True
                    dmg = m.damage * f.stats["damage"]
                    self.projectiles.append(Projectile(f, f.x + f.aim[0] * 0.6, f.y + f.aim[1] * 0.6, 1.1 * f.stats["size"],
                                                       f.aim[0], f.aim[1], dmg))
            else:
                key = int((t - s) / 0.12) if f.move == "spin_kick" else 0  # the spin kick hits up to 3 times
                if key not in f.hit_done:
                    self.pending.append((f, enemy, f.move, key))  # (checked with everyone else's: resolve_hits)
        if t >= s + a + r:
            f.set_state("jump" if f.airborne else "idle")
            f.chain_open = False

    def reaches(self, f, v, m):
        """Does move m from f reach v? (straight moves along where they were aimed; spins all round)"""
        dx, dy = v.x - f.x, v.y - f.y
        reach = f.reach(f.move) + v.radius
        if f.move == "spin_kick":
            return length(dx, dy) <= reach
        along = dx * f.aim[0] + dy * f.aim[1]
        side = abs(dx * f.aim[1] - dy * f.aim[0])
        return 0 < along <= reach and side <= m.width + v.radius

    def hit_check(self, f, v, name, now):
        """Would this active attack connect? None (a miss), or True / False (blocked or not)."""
        m = MOVES[name]
        if v.knocked_out or v.state in ("knockdown", "getup", "ringout") or now < v.invincible_until:
            return None
        if not self.reaches(f, v, m):
            return None
        # heights: what can't hit what
        if m.height == "throw":
            if v.airborne or v.state == "hitstun":
                return None
        elif m.height == "low" and v.airborne:
            return None
        elif m.height == "high" and v.crouching and not v.airborne:
            return None  # it goes over their head
        return self.blocks(v, m.height)

    def resolve_hits(self, now):
        """Every attack this tick is checked against where everyone was at the start of the tick, and only then
        do they land. So when both fighters strike at the same moment, both hits land (a trade), instead of the
        one checked first always winning."""
        checks = [(f, v, name, key, self.hit_check(f, v, name, now)) for f, v, name, key in self.pending]
        self.pending = []
        for f, v, name, key, blocked in checks:
            if blocked is not None:
                f.hit_done.add(key)
                self.connect(f, v, name, MOVES[name], blocked, now)

    @staticmethod
    def blocks(v, height):
        if height == "throw":
            return False
        if v.state == "block" or (v.state == "blockstun" and not v.crouching):
            return height in ("high", "mid", "overhead")
        if v.state == "low_block" or (v.state == "blockstun" and v.crouching):
            return height == "low"  # a low block stops sweeps (and high attacks miss anyway), but mids hit it
        return False

    def connect(self, f, v, name, m, blocked, now, point=None, from_shot=False):
        """Apply a hit or a block."""
        dirx, diry = (f.aim if not from_shot else (point[3], point[4]))
        if name == "spin_kick":
            dx, dy = v.x - f.x, v.y - f.y
            d = max(length(dx, dy), 1e-3)
            dirx, diry = dx / d, dy / d
        hx = point[0] if point else (f.x + v.x) / 2
        hy = point[1] if point else (f.y + v.y) / 2
        hz = point[2] if point else {"low": 0.3, "mid": 0.9, "high": 1.35, "overhead": 1.3, "throw": 1.0}[m.height] * v.stats["size"]
        base = (point[5] if from_shot else m.damage * f.stats["damage"] * f.mods(name)[0]) *             RULES["damage_multiplier"] * v.stats["taken"]
        if name == "cartwheel":  # user mod: a share of their full health, whoever the fighters are
            base = v.stats["health"] * CARTWHEEL_SHARE
        # moves from the combo list only knock down or launch on the last move of the list (the finisher)
        in_combo = f.from_combo and not from_shot
        finisher = in_combo and f.chained and f.combo_step == len(f.combo_list) - 1
        mid_combo = in_combo and not finisher
        if in_combo:
            f.chain_open = True  # the next punch press carries on the combo
        f.connected[name] = f.connected.get(name, 0) + 1
        push = m.push * RULES["knockback"] / v.stats["size"]
        was_low = v.crouching and not v.airborne
        self.hitstop_until = now + (0.045 if blocked else 0.07 if m.damage < 12 else 0.1)
        if blocked:
            chip = 0.0 if v.weapon == "sword_shield" else base * RULES["chip_damage"]  # (a shield stops it all)
            if not self.practice:
                v.health = max(1.0, v.health - chip)  # a block never knocks you out
            v.set_state("blockstun", m.stun * 0.6)
            v.low_guard = was_low
            v.vx, v.vy = dirx * push * 0.8, diry * push * 0.8
            f.energy_add(3)
            v.energy_add(4)
            self.stage.impacts.append(((hx, hy, hz), chip, "block"))
            self.last_hit = {"by": f.id, "move": name, "dmg": round(chip, 1), "blocked": True, "combo": 0,
                             "height": m.height, "t": round(now, 2)}
            return
        counter = v.state == "attack" and v.move_phase() == "startup"
        dmg = base * (RULES["combo_scaling"] ** v.combo_taken) * (1.25 if counter else 1.0) * (1.3 if finisher else 1.0)
        if name == "cartwheel":
            dmg = base  # (always the same share: no extra for a counter, no less in a combo)
        v.combo_taken += 1
        v.last_hurt = now
        f.hits += 1
        f.damage_dealt += dmg
        f.landed[name] = f.landed.get(name, 0) + 1
        f.last_damage[name] = dmg
        f.finishers += 1 if finisher else 0
        f.energy_add(8)
        v.energy_add(5)
        if not self.practice:
            v.health -= dmg
        effect = None if mid_combo else ("down" if finisher and m.effect is None else m.effect)
        v.hurt_how = effect if effect in ("trip", "launch") else {"mid": "body", "low": "low"}.get(m.height, "head")
        v.move = None
        v.vx, v.vy = dirx * push, diry * push
        if v.health <= 0 and not self.practice:
            v.knocked_out, v.ko_reason = True, "ko"
            v.set_state("launched")
            v.vz, v.z = max(v.vz, 3.5), max(v.z, 0.03)
            v.vx, v.vy = dirx * 3.0, diry * 3.0
        elif m.height == "throw":
            v.set_state("launched")
            v.throw_anim = True
            v.z, v.vz = 0.03, 3.2
            v.vx, v.vy = dirx * 1.6, diry * 1.6
        elif v.airborne and v.juggles < 3:  # a juggle: keep them up in the air
            v.juggles += 1
            v.set_state("launched")
            v.vz = max(v.vz, 3.2)
        elif effect == "launch":
            v.set_state("launched")
            v.z, v.vz = 0.03, 5.0
            v.vx, v.vy = dirx * 1.2, diry * 1.2
        elif effect in ("down", "trip"):
            v.set_state("launched")
            v.z, v.vz = 0.03, 2.4 if effect == "down" else 1.8
        elif v.airborne:
            v.set_state("launched")
        else:
            v.set_state("hitstun", m.stun)
            v.low_guard = was_low
        kind = "counter" if counter else ("special" if name in SPECIALS else
                                          name if name not in ("jump_kick", "cartwheel") else "kick")
        self.stage.impacts.append(((hx, hy, hz), dmg, kind))
        self.last_hit = {"by": f.id, "move": name, "dmg": round(dmg, 1), "blocked": False, "combo": v.combo_taken,
                         "height": m.height, "counter": counter, "t": round(now, 2)}
        if counter:
            self.event(f"COUNTER HIT by {f.name}!")
        if finisher:
            self.event(f"{f.name}: {len(f.combo_list)}-HIT COMBO!")

    def move_projectiles(self, dt, now):
        for p in list(self.projectiles):
            p.x += p.dx * BLAST_SPEED * dt
            p.y += p.dy * BLAST_SPEED * dt
            p.life -= dt
            gone = p.life <= 0 or length(p.x - self.centre[0], p.y - self.centre[1]) > self.size + 2
            for v in self.fighters:
                if v is p.owner or gone:
                    continue
                if length(v.x - p.x, v.y - p.y) < v.radius + 0.3 and v.z < p.z + 0.2 and v.z + 1.7 * v.stats["size"] > p.z:
                    if now >= v.invincible_until and v.state not in ("knockdown", "getup", "ringout") \
                            and not v.knocked_out:
                        self.connect(p.owner, v, "blast", MOVES["blast"], self.blocks(v, "mid"), now,
                                     point=(p.x, p.y, p.z, p.dx, p.dy, p.damage), from_shot=True)
                        gone = True
            if gone:
                self.projectiles.remove(p)

    def push_apart(self):
        if len(self.fighters) < 2:
            return
        a, b = self.fighters
        if a.knocked_out and a.state == "ringout" or b.state == "ringout":
            return
        dx, dy = b.x - a.x, b.y - a.y
        d = length(dx, dy)
        need = a.radius + b.radius
        overlap_z = abs(a.z - b.z) < 1.0
        if d < need and overlap_z:
            if d < 1e-4:
                dx, dy, d = 1.0, 0.0, 1.0
            push = (need - d) / 2
            a.x -= dx / d * push
            a.y -= dy / d * push
            b.x += dx / d * push
            b.y += dy / d * push

    def edges(self, f, now):
        """The ring's edge: open (fall off = ring out) or roped (you bounce off; electric ropes zap)."""
        cx, cy = self.centre
        dx, dy = f.x - cx, f.y - cy
        d = length(dx, dy)
        if f.state == "ringout":
            return
        if self.stage.hazards.get("ring_out"):
            if d > self.size + 0.1 and f.z <= 0.02:
                f.set_state("ringout")
                f.z, f.vz = -0.01, -1.0
                f.vx, f.vy = dx / d * 1.5, dy / d * 1.5
                if not self.practice and self.phase == "fight":
                    f.knocked_out, f.ko_reason = True, "ringout"
                self.event(f"RING OUT! {f.name} fell off")
                self.stage.impacts.append(((f.x, f.y, 0.2), 10, "ringout"))
            return
        limit = self.size - f.radius
        if d > limit:
            nx, ny = dx / d, dy / d
            f.x, f.y = cx + nx * limit, cy + ny * limit
            out = f.vx * nx + f.vy * ny
            if out > 0:
                if out > 2.5 and f.state in ("hitstun", "launched"):
                    self.stage.impacts.append(((f.x, f.y, 0.9), out * 2, "wall"))
                f.vx -= 1.6 * out * nx  # bounce off the ropes
                f.vy -= 1.6 * out * ny
            if self.stage.hazards.get("electric_ropes") and now - f.last_zap > 0.8 and not f.knocked_out \
                    and self.phase == "fight":
                f.last_zap = now
                dmg = 6 * RULES["hazard_damage"] * f.stats["taken"]
                if not self.practice:
                    f.health -= dmg
                f.vx, f.vy = -nx * 3.0, -ny * 3.0
                if f.state not in ("launched", "knockdown", "getup", "ko"):
                    f.set_state("hitstun", 0.35)
                self.stage.impacts.append(((f.x, f.y, 1.0), dmg, "zap"))
                self.check_hazard_ko(f, "zapped")

    def hazards(self, f, now):
        if f.state in ("ringout",) or f.knocked_out or self.phase != "fight":
            return
        for i, (jx, jy) in enumerate(self.jets()):
            power = self.jet_power(i, now)
            if power > 0.3 and length(f.x - jx, f.y - jy) < 0.6 and f.z < 1.2 and now - f.last_burn > 0.4:
                f.last_burn = now
                dmg = 5 * RULES["hazard_damage"] * f.stats["taken"]
                if not self.practice:
                    f.health -= dmg
                f.set_state("launched")
                f.z, f.vz = max(f.z, 0.03), 3.0
                self.stage.impacts.append(((jx, jy, 0.5), dmg, "fire"))
                self.check_hazard_ko(f, "burned")
        for sx, sy in self.spikes():  # standing on spikes hurts and throws you back towards the middle
            if length(f.x - sx, f.y - sy) < SPIKE_RADIUS and f.z < 0.2 and now - f.last_spiked > 0.8:
                f.last_spiked = now
                dmg = 5 * RULES["hazard_damage"] * f.stats["taken"]
                if not self.practice:
                    f.health -= dmg
                cx, cy = self.centre
                d = max(length(cx - f.x, cy - f.y), 1e-4)
                f.set_state("launched")
                f.z, f.vz = max(f.z, 0.03), 3.0
                f.vx, f.vy = (cx - f.x) / d * 2.5, (cy - f.y) / d * 2.5
                self.stage.impacts.append(((f.x, f.y, 0.3), dmg, "spikes"))
                self.check_hazard_ko(f, "spiked")

    def check_hazard_ko(self, f, how):
        if f.health <= 0 and not self.practice:
            f.knocked_out, f.ko_reason = True, "ko"
            if f.state != "launched":
                f.set_state("launched")
                f.z, f.vz = 0.03, 3.0
            self.event(f"{f.name} was {how}!")

    # ---------- rounds ----------
    def check_round(self, now):
        if self.practice:
            for f in self.fighters:  # training: a ring out puts everyone back after a moment
                if f.state == "ringout":
                    f.z -= 3 * STEP
                    if f.state_t > 1.2:
                        self.start_round()
                        return
            return
        if len(self.fighters) < 2:
            for f in self.fighters:
                if f.state == "ringout" and f.state_t > 1.2:
                    f.reset()
            return
        if self.phase == "fight":
            out = [f for f in self.fighters if f.knocked_out]
            time_up = self.time_left() == 0
            if out or time_up:
                a, b = self.fighters
                if len(out) == 2:
                    winner = None
                elif out:
                    winner = a if out[0] is b else b
                else:
                    ha, hb = a.health / a.stats["health"], b.health / b.stats["health"]
                    winner = a if ha > hb else b if hb > ha else None
                reason = "RING OUT!" if any(f.ko_reason == "ringout" for f in out) else "K.O.!" if out else "TIME!"
                if winner is not None and winner.health >= winner.stats["health"] - 0.01 and out:
                    reason = "PERFECT!"
                self.banner = reason
                self.time_at_end = self.time_left()
                self.round_winner = winner
                self.phase, self.phase_t = "ko", 0.0
                if winner:
                    winner.wins += 1
                self.event(f"{reason} " + (f"{winner.name} wins round {self.round}" if winner else "A draw"))
        elif self.phase == "ko":
            for f in self.fighters:
                if f.state == "ringout":
                    f.z -= 3 * STEP
            if self.phase_t > 1.2 and self.round_winner and self.round_winner.state in ("idle", "walk", "side", "block",
                                                                                          "crouch", "low_block"):
                self.round_winner.set_state("win")
            if self.phase_t > 3.0:
                champ = next((f for f in self.fighters if f.wins >= self.stage.rounds_to_win), None)
                if champ:
                    self.phase, self.match_over = "over", True
                    self.banner = f"{champ.name} WINS!"
                    self.result = champ.name
                    champ.set_state("win")
                    self.event(f"{champ.name} WINS THE MATCH!")
                else:
                    self.round += 1
                    self.start_round()

    def winner(self):
        return self.result

    def hazard_state(self, now):
        return {"jets": [round(self.jet_power(i, now), 2) for i in range(4)]}


# ---------- user mods: features learners asked for, switched on and off by the teacher ----------
# key: (the name in the teacher's Controls, what it does). Every user mod is OFF unless the teacher switches it on,
# and the game works exactly as before while it's off. The fighting reads stage.user_mods (a ring: self.stage.user_mods);
# the graphics get the same switches (StageVisual(..., user_mods)). The teacher can switch one mid-match: the rings
# and windows follow at once. A learner's AI request can be made as a new user mod (AI cards: "Make it a switchable
# User Mod").
USER_MODS = {
    "cartwheel_kick": ("Cartwheel kick (F)", "Pressing F does a cartwheel into a kick that takes half of the other "
                                             "fighter's full health if it lands clean."),
}


def user_mods_on(values):
    """Every user mod's switch (off unless switched on)."""
    values = values or {}
    return {k: bool(values.get(k)) for k in USER_MODS}


class Stage:
    """All the rings, stepped together."""

    def __init__(self, hazards=None, practice=True, rounds_to_win=2, round_seconds=None, user_mods=None):
        self.hazards = {"ring_out": True, "electric_ropes": False, "fire_jets": False, "slippery": False,
                        "spikes": False}
        self.hazards.update(hazards or {})
        self.user_mods = user_mods_on(user_mods)  # the teacher's user mods (see USER_MODS)
        self.practice = practice
        self.rounds_to_win = rounds_to_win
        self.round_seconds = round_seconds or RULES["round_seconds"]
        self.rings = []
        self.time = 0.0
        self.events = []
        self.impacts = []
        self._next = 1

    def new_id(self):
        self._next += 1
        return self._next - 1

    def add_ring(self):
        if len(self.rings) >= MAX_RINGS:
            return None
        r = Ring(self, len(self.rings))
        self.rings.append(r)
        return r

    def fighters(self):
        return [f for r in self.rings for f in r.fighters]

    def set_hazards(self, hz):
        self.hazards.update({k: bool(v) for k, v in hz.items() if k in self.hazards})

    def set_user_mods(self, values):
        """Switch user mods on or off mid-match. A mod that changes something already built (a ring's shape, say)
        rebuilds it here when its switch changes."""
        self.user_mods = user_mods_on({**self.user_mods, **(values or {})})

    def step(self):
        self.time += STEP
        for r in self.rings:
            r.step(STEP, self.time)
        if len(self.events) > 200:
            self.events = self.events[-50:]

    def take_fx(self):
        fx, self.impacts = self.impacts, []
        return fx


# ---------- what the windows are sent (plain data: the server and the showcase both use it) ----------
def fighter_state(f, now, ring=None):
    a, k = f.anim()
    if ring is not None and ring.phase == "intro":  # (they bow as the round is announced)
        a, k = "intro", min(1.0, ring.phase_t / INTRO_SECONDS)
    return {"id": f.id, "pos": [round(f.x, 3), round(f.y, 3), round(f.z, 3)], "h": round(f.heading, 1),
            "a": a, "k": round(k, 3), "hp": round(max(0.0, f.health), 1), "max": round(f.stats["health"]),
            "en": round(f.energy), "w": f.wins, "hu": round(min(9.0, now - f.last_hurt), 2), "hits": f.hits,
            "ap": 1 if f.brain is not None and f.owner not in ("Computer", "Teacher (away)") else 0}


def ring_state(r, now):
    tl = r.time_left()
    return {"i": r.index, "c": list(r.centre), "ph": r.phase, "rd": r.round,
            "tl": None if tl is None else round(tl, 1), "bn": r.banner, "lb": r.label,
            "hz": r.hazard_state(now), "f": [fighter_state(f, now, r) for f in r.fighters],
            "sh": [[round(p.x, 2), round(p.y, 2), round(p.z, 2), round(p.dx, 2), round(p.dy, 2), p.owner.id]
                   for p in r.projectiles],
            "lh": r.last_hit}


# ---------- the simple computer driver (cpu_brains.py has the levels) ----------
def move_damage(f, v, name):
    """How much one clean hit of a move from f does to v (before combo scaling): the game's damage model."""
    return MOVES[name].damage * f.stats["damage"] * f.mods(name)[0] * RULES["damage_multiplier"] * v.stats["taken"]


def distance(a, b):
    return length(a.x - b.x, a.y - b.y)


def edge_distance(f):
    cx, cy = f.ring.centre
    return f.ring.size - length(f.x - cx, f.y - cy)


def simple_brain(me, enemy, ring):
    """Walk up and punch. (The computer's fighters use cpu_brains.py.)"""
    if enemy is None:
        return 0.0, 0.0, ""
    d = distance(me, enemy)
    if d > 1.1:
        return 1.0, 0.0, ""
    return 0.0, 0.0, "punch" if random.random() < 0.3 else ""
