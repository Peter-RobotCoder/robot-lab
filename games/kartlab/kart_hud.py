"""Kart Lab's own HUD bits, on top of the engine's HUD kit (engine/hud.py): the tab lists, the words for the
design's variables and the lesson's tools, the AI card's targets, the kart's design schema (the garage's tables
and the code panel come from it), the stats readout, and the fixed text over the track (the title, the key list
and the banner).

The window (kart_client.py) is the engine's HudKit with ShowBase, as Fight Lab's and Robot Lab's windows are.
"""
import kart_version  # noqa: F401  (puts the engine on the path)
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

import kart_sim as sim
from engine import hud
from engine.hud import GREY, YELLOW, BLUE, label
from engine.schema import Var

# the side panel's tabs (the learner's one row; the teacher's two)
LEARNER_TABS = [("missions", "Mission"), ("garage", "Garage"), ("ai", "AI card"), ("card", "My card"),
                ("mods", "Mods"), ("settings", "Settings")]
TEACHER_TABS = [("teacher", "Controls"), ("mods", "User mods"), ("races", "Races"), ("learners", "Learners"),
                ("accounts", "Accounts"), ("outcomes", "Outcomes"), ("cards", "AI cards"), ("changes", "Changes"),
                ("limits", "Limits"), ("warnings", "Warnings"), ("garage", "My kart"), ("settings", "Settings")]
OFFLINE_TABS = [("garage", "Garage"), ("settings", "Settings")]  # (no server: no missions, cards or mods)

# the lesson's tools (what a mission's garage shows), as the Controls tab names them
PRETTY = {"points_table": "Points table", "speed": "Top speed", "acceleration": "Acceleration", "grip": "Grip",
          "top_speed": "Top speed", "name_and_colour": "Name and colour", "code_view": "Code view",
          "stats_readout": "Stats readout", "brains": "Autopilot (U and P)", "drift": "Drifting",
          "boost_pads": "Dash pads", "oil": "Oil patches", "respawn": "Respawn (R)"}
TOOL_ORDER = ["points_table", "speed", "acceleration", "grip", "name_and_colour", "code_view", "stats_readout",
              "brains"]
HAZARD_NAMES = {"pads": "Dash pads", "oil": "Oil patches", "bumps": "Bumping between karts", "walls": "Hard barriers",
                "hill": "The hill"}
STAT_WORDS = {"speed": ("Top speed", "how fast it goes flat out on a straight"),
              "acceleration": ("Acceleration", "how quickly it gets there, and how hard it brakes"),
              "grip": ("Grip", "how sharply it turns and how fast a slide stops")}
TARGETS = {"kart": "Their kart", "track": "The track", "rules": "The rules", "game": "The whole game"}
AI_TARGETS = {"kart": "My kart", "track": "The track", "rules": "The rules", "game": "The game (teacher only)"}
AI_RULES = ("Only the teacher uses the AI.  Never put personal information in a request.\n"
            "AI can be wrong: you test the code and must be able to explain it.\n"
            "Say where AI helped (the tool and the date).")
CARD_FIELDS = ("goal", "variables", "test", "predict")
STOP_CODES = (4001, 4004, 4006, 4007, 4008, 4009, 4010, 4011)  # the server said no: wrong code or password,
# old version, deleted, the session ended, the group hasn't started, a ticket that ran out
CODE_ROWS = 19     # lines of code the code panel shows at once (longer code scrolls)
CODE_PANEL = (-0.86, 0.12, -0.85, 0.36)  # the code panel in its first place: left, right, bottom, top


# ---------- the design as variables ----------
def design_schema():
    """The kart's design schema: the garage's tables and the code panel are drawn from it (engine.schema). The
    simulation's own copy (kart_sim.design_schema) is used when it is there; this is the same list."""
    own = getattr(sim, "design_schema", None)
    if own is not None:
        try:
            return list(own())
        except Exception:
            pass
    return [Var("kart_name", ("name",), "str", "strings", tool="name_and_colour", note="a string: text made of chars",
                max_len=12),
            Var("colour", ("colour",), "rgb", "lists", tool="name_and_colour", note="red, green, blue: 0 to 255"),
            Var("speed_points", ("speed",), "int", "points", tool="points_table",
                note="points for top speed (how fast on a straight)"),
            Var("acceleration_points", ("acceleration",), "int", "points", tool="points_table",
                note="points for acceleration (how quickly it gets there, and brakes)"),
            Var("grip_points", ("grip",), "int", "points", tool="points_table",
                note="points for grip (how sharply it turns, how fast a slide stops)")]


def default_rules():
    """What the window needs to know about the design's rules when the server hasn't said (offline, or an older
    server): the stats, the points, and no percentage settings."""
    return {"stats": list(sim.STATS), "points_total": sim.POINTS_TOTAL, "stat_min": sim.STAT_MIN,
            "stat_max": sim.STAT_MAX, "settings": {}, "full": None}


def check_design(d, limits=None):
    """A list of problems with a design (empty: fine). kart_sim's own check is used when it is there."""
    own = getattr(sim, "check_design", None)
    if own is not None:
        try:
            return list(own(d, limits))
        except TypeError:
            return list(own(d))
    problems = []
    if not isinstance(d, dict):
        return ["the design must be a dictionary"]
    lo, hi = sim.STAT_MIN, sim.STAT_MAX
    total = sim.POINTS_TOTAL
    if limits:
        total = limits.get("points_total", total)
    used = 0
    for k in sim.STATS:
        v = d.get(k)
        rng = (limits or {}).get("points", {}).get(k, [lo, hi])
        if not isinstance(v, int) or isinstance(v, bool):
            problems.append(f"{k} must be a whole number")
            continue
        if not rng[0] <= v <= rng[1]:
            problems.append(f"{k} must be from {rng[0]} to {rng[1]} (it is {v})")
        used += v
    if used != total:
        problems.append(f"points used must be exactly {total} (they are {used})")
    name = d.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append("the name must be a word or two")
    c = d.get("colour")
    if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c)):
        problems.append("colour must be a list of three whole numbers, each 0 to 255")
    return problems


def stats_text(design):
    """What the points buy, in words (the garage's stats readout)."""
    st = sim.stats_of(design)
    kmh = st["top"] * 3.6
    to60 = (60 / 3.6) / max(0.1, st["accel"])
    return (f"Top speed {kmh:.0f} km/h    0 to 60 km/h in {to60:.1f} s\n"
            f"Steering {st['steer']:.0f} degrees a second    a slide dies in {1 / max(0.1, st['grip']):.2f} s")


def points_left(design, total=None):
    return (total or sim.POINTS_TOTAL) - sum(int(design.get(k, 0)) for k in sim.STATS)


# ---------- the fixed text over the track ----------
class Overlay:
    """The title (top left, under the lap counter), the key list (bottom left) and the banner (notes for a few
    seconds, big for a restart warning): always the dark look, drawn once over the game."""

    def __init__(self, base, teacher, name, keys_text):
        was = hud.THEME
        hud.set_theme("dark")
        try:
            a = base.getAspectRatio()
            self.base = base
            self.title = label(base.aspect2d, f"KART LAB  -  {'TEACHER' if teacher else 'LEARNER'}: {name}", -a + 0.05,
                               0.8, 0.03, BLUE if teacher else YELLOW)
            self.view_text = label(base.aspect2d, "", -a + 0.05, 0.755, 0.022, GREY)
            self.help = label(base.aspect2d, keys_text, -a + 0.05, -0.975, 0.02, GREY)
            self.banner = OnscreenText("", pos=(-0.3, 0.52), scale=0.05, fg=YELLOW, shadow=(0, 0, 0, 1), mayChange=True,
                                       wordwrap=40, parent=base.aspect2d)  # (left of centre: clear of the side panel)
            self.aspect = a
        finally:
            hud.set_theme(was)

    def layout(self):
        a = self.base.getAspectRatio()
        if a == self.aspect:
            return
        self.aspect = a
        self.title.setPos(-a + 0.05, 0.8)
        self.view_text.setPos(-a + 0.05, 0.755)
        self.help.setPos(-a + 0.05, -0.975)

    def set_title(self, text):
        self.title.setText(text)

    def toggle_help(self):
        self.help.hide() if not self.help.isHidden() else self.help.show()
        return self.help.isHidden()

    def note(self, text, big=False):
        self.banner.setText(text)
        self.banner.setScale(0.075 if big else 0.05)

    def set_view(self, text):
        self.view_text.setText(text)


def keys_text(teacher):
    return ("Arrows/WASD drive  Shift drift  R respawn  V view  Tab/I HUD  C code  " +
            ("Enter start  G grid  T track  " if teacher else "U brain  P autopilot  ") + "N sound  H help")
