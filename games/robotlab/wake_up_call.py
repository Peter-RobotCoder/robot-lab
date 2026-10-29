"""MISSIONS, the club's fourth game (CHANGE 189): Mission 1, WAKE-UP CALL, in 3D. One learner, no server: TITAN or
RAZORBACK has crash-landed in the hills above Brookfield, and the learner drives it with pseudo code
(docs/plans/wake-up-call-3d.md). The Club Coders app opens it from its Missions button (club-coders/launcher: no
login, no class server, so it is there whether a class is live or not); 18 Mission 1 Wake-Up Call.bat opens it here.
Mission 2, LIGHTS OUT (prototype: mission_lights_out.py, missions/lights_out/), is the second choice on the same
first screen (F1 and F2, or the buttons; 19 Mission 2 Lights Out.bat): the hill road at night, if / else and
variables. The window is the same; the mission, its dictionary, its scene (HillRoad) and its words are its own.

    python wake_up_call.py                      choose a mission and a robot, then press C
    python wake_up_call.py --robot titan        straight in with TITAN (or razorback)
    python wake_up_call.py --mission lights_out Mission 2 chosen at the start
    python wake_up_call.py --host ws://127.0.0.1:8784 --name Sam     in a class (missions_server.py, CHANGE 195):
                                                the lesson's mission, your progress kept on the server, each run
                                                reported; --teacher --name "Mr P" is the teacher's window, with
                                                the class's progress top right

The mission (mission_wake_up.py) and the pseudo code (mission_pseudo.py, missions/wake_up_call/dictionary.json) are
the reviewed 2D prototype's, ported line for line; this window draws them in the 3D Robot Lab: the valley at 2 m a
square, the robot with the tool it holds (Robot Lab's own weapons as tools), the code panel, the HUD. The engine's
code does what every game's window does: the graphics tiers and their settings (engine.gfx_tiers), the window's
size and the Full screen button (engine.hud, engine.full_screen), the code editor (engine.editor), reopening the
window (engine.reopen), the sounds (engine.rw_sound); Robot Lab's own robots, effects and line look (rw_gfx, rw_fx).

Keys:   C  the code panel (Pseudo code and Code tabs)    Ctrl+Enter  run    Esc  close the panel, else quit
        Ctrl+R (or the RESET buttons)  the mission back to its start, your code kept    R  the same, when not typing
        V  the view (the valley, behind the robot, from above)    mouse wheel or + / -  zoom
        right mouse button held and dragged  pan over the map    Home  the camera back as it started
        G  graphics: the Look (Solid or Wireframe, at once), the Quality (Auto or any of the engine's seven tiers,
           mesh, lines, basic, low, medium, high, ultra: the window reopens at it, a few seconds, your robot and code
           kept) and the line colour for mesh and lines (at once); kept for next time in this computer's settings.json
        Full screen  the button top right (Esc comes back out of it), as every game's window
Options: --gfx mesh|lines|basic|low|medium|high|ultra (by hand: otherwise the Graphics panel's choice, else a solid
         tier, never the mesh or lines look Robot Lab may have saved)  --window 1600x900 or full (kept on this
         computer, as the games' Settings tabs keep it)  --no-sound  --progress <file>
Tests:   --offscreen --selftest (plays the mission through and checks it: wake_up_call_test.py runs it), --screenshot X.png
         --zoom 2.2 (the camera's zoom for the picture); --replay keys.json (recorded key presses played into the
         window, each mission's result printed: replay_mission.py). An offscreen picture or replay steps time a
         sixtieth a frame, not by the clock, so every machine draws the same moment (as kart_preview.py does).
Finishing unlocks the Solar Panel for Mission 2: kept in RobotLab/missions_progress.json beside this computer's
settings (as the prototype keeps it in the browser).
"""
import argparse
import json
import math
import os
import re
import sys
import textwrap
import time

from panda3d.core import loadPrcFileData

import lab_version  # noqa: E402
sys.path.insert(0, lab_version.ENGINE_HOME)  # (the engine package, shared by every game)
from engine import editor, full_screen, gfx_tiers, hud, reopen  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--robot", choices=["titan", "razorback"], help="skip the robot choice")
ap.add_argument("--mission", default="wake_up_call", choices=["wake_up_call", "lights_out"],
                help="the mission chosen at the start (the first screen can change it)")
ap.add_argument("--gfx", default="auto", choices=("auto",) + gfx_tiers.TIERS,
                help="the graphics tier (auto: this computer's; the launcher's Graphics button passes its choice)")
ap.add_argument("--window", help="the window, as 1600x900, or full (the launcher's Window button; kept on this computer)")
ap.add_argument("--no-sound", action="store_true")
ap.add_argument("--progress", help="where the Solar Panel and the stars are kept (a JSON file)")
ap.add_argument("--fast", action="store_true", help="no animation: each run's result at once")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--zoom", type=float, help="the camera's zoom for --screenshot (1 as it starts; bigger is further out)")
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--selftest", action="store_true", help="play the mission through and check it, then quit")
ap.add_argument("--replay", help="play recorded key presses (a JSON file replay_mission.py writes) and print each "
                                 "mission's result, then quit")
# in a class (CHANGE 195): the Missions class server, as the Club Coders app opens every game's window
ap.add_argument("--host", default=None, help="the Missions class server (missions_server.py); none: play alone")
ap.add_argument("--name", default="", help="your name in the class")
ap.add_argument("--teacher", action="store_true", help="the teacher's window: the class's progress top right")
ap.add_argument("--code", help="class code (the demo codes on a laptop test server)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)  # (accepted as every game's window: not used)
ap.add_argument("--ticket", help=argparse.SUPPRESS)  # (from the club desk: the app has logged this person in)
args = ap.parse_args()
# An offscreen picture or replay: time steps a sixtieth a frame, not by the clock (the selftest keeps the clock: it
# waits for real seconds)
FIXED_STEP = bool(args.offscreen and (args.screenshot or args.replay) and not args.selftest)

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RobotLab")  # (as lab_client's)
PROGRESS = args.progress or os.path.join(SETTINGS_DIR, "missions_progress.json")
# The mission's own graphics choice (the Look, the tier, the line colour) lives in settings.json beside the progress
# file: RobotLab/settings.json, the engine's own settings file, unless --progress puts it elsewhere (the tests do).
MISSION_SETTINGS_DIR = os.path.dirname(os.path.abspath(PROGRESS))
GFX_KEY = "wake_up_call_gfx"
SOLID = tuple(t for t in gfx_tiers.TIERS if t not in gfx_tiers.LOOKS)  # basic to ultra: the shaded tiers
# The Graphics panel's Quality row: the engine's whole ladder, as Robot Lab's Settings tab offers it (CHANGE 145), with
# Auto first (the computer's own solid tier, as the engine picks it). None stands for Auto in the saved choice too.
TIER_CHOICES = (None,) + gfx_tiers.TIERS
hud.setup(SETTINGS_DIR)  # (this computer's look and window size; only a --window choice is written, as every game's)


def gfx_choice():
    """What was chosen in the window's Graphics panel, checked: {"look": "solid" | "wireframe", "tier": one of the
    engine's seven (missing: Auto), "line_colour": "#rrggbb"}; each key missing when nothing was chosen. The first
    build's "quality" low or high (a942ff1, Pete's laptop) is read as the low or high tier."""
    saved = gfx_tiers.load_settings(MISSION_SETTINGS_DIR).get(GFX_KEY)
    saved = saved if isinstance(saved, dict) else {}
    out = {}
    if saved.get("look") in ("solid", "wireframe"):
        out["look"] = saved["look"]
    tier = saved.get("tier", saved.get("quality"))
    if tier in gfx_tiers.TIERS:
        out["tier"] = tier
    if hud.HudKit.good_line_colour(saved.get("line_colour")):
        out["line_colour"] = saved["line_colour"].lower()
    return out


def choose_tier(override=args.gfx):
    """The graphics tier this run draws. --gfx wins (any of the seven, by hand). Else the Graphics panel's choice
    (any of the seven; the teacher's class maximum from Robot Lab still caps it). Else, Auto: this computer's tier as
    the engine picks it for the solid tiers alone: Robot Lab's saved mesh or lines look is a look, not a quality, and
    never carries over unless chosen here (the window opened as a wireframe on a laptop whose Robot Lab had been set
    to Mesh: CHANGE 188)."""
    if override in gfx_tiers.TIERS:
        return override
    saved = gfx_tiers.load_settings(SETTINGS_DIR)
    cap = saved.get("gfx_class_max")
    chosen = gfx_choice().get("tier")
    if chosen:
        return gfx_tiers.capped(chosen, cap)
    tier = saved.get("gfx_tier")
    if tier not in gfx_tiers.TIERS or tier in gfx_tiers.LOOKS:
        guess = (saved.get("gfx_detect") or {}).get("heuristic_tier")
        tier = guess if guess in gfx_tiers.TIERS else gfx_tiers.DEFAULT
    return gfx_tiers.nearest(gfx_tiers.capped(tier, cap), SOLID)


GFX = choose_tier()
print(f"wake_up_call: the {GFX} tier" + (" (--gfx)" if args.gfx in gfx_tiers.TIERS else
      f" (Graphics panel: {gfx_choice()['tier']})" if gfx_choice().get("tier") else
      " (this computer's, solid tiers only)"), flush=True)
# A window reopened by the Graphics panel at a new tier carries its robot, code and view over in this (JSON).
REOPEN_ENV = "WAKE_UP_CALL_REOPEN"
# the window's size: --window (the launcher's Window button: a size, or full), else the size kept on this computer,
# kept again as the games' Settings tabs keep it (engine.hud.window_arg, CHANGE 126)
WINDOW_TITLES = {"wake_up_call": "Missions - Mission 1: Wake-Up Call", "lights_out": "Missions - Mission 2: Lights Out"}


class ClassLink:
    """(CHANGE 195) The window's link to the Missions class server: logged in before the window opens (the lesson
    says which mission; the learner's progress comes from the server, so it follows them to any laptop), each run
    reported, the teacher's window sent the class's progress. None of this when playing alone (no --host)."""

    def __init__(self):
        from engine import club_ticket
        from engine.net import Net
        self.net, self.role, self.name, self.lesson, self.progress = None, "learner", args.name, None, None
        self.class_state, self.note = None, ""
        if args.ticket:  # the club desk has logged this person in: their name and role are in the ticket
            peek = club_ticket.peek(args.ticket) or {}
            self.name = peek.get("name") or self.name
            args.teacher = args.teacher or peek.get("role") == "teacher"
        self.role = "teacher" if args.teacher else "learner"
        code = args.code or ("TEACH99" if args.teacher else "CLUB42")
        try:
            self.net = Net(args.host, self.name or ("Teacher" if args.teacher else ""), code, version=lab_version.VERSION,
                           **({"ticket": args.ticket} if args.ticket else {}))
        except Exception as e:  # (no server: the mission is played alone, and the window says so)
            self.note = f"Couldn't reach the Missions class server ({args.host}): playing alone. {e}"
            print(self.note, flush=True)
            return
        welcome, problem = self.wait_for("welcome")
        if welcome is None:
            self.note = f"The Missions class server said no: {problem}"
            print(self.note, flush=True)
            self.net = None
            return
        self.name = welcome.get("name") or self.name
        self.role = welcome.get("role") or self.role
        self.take_lesson(welcome.get("lesson"))
        self.progress = welcome.get("progress") if isinstance(welcome.get("progress"), dict) else None
        # (CHANGE 198) the server runs the missions: the class's robots now, and this person's own mission when
        # they're coming back to it (a reopened window, a dropped connection), sent straight after the welcome
        self.runs_here = bool(welcome.get("runs_here"))
        self.early, self.back = [], None
        if self.runs_here:
            world, _ = self.wait_for("world", 3)
            self.early.append(world or {"type": "world", "robots": []})
            import queue
            try:
                m = self.net.inbox.get(timeout=0.3)
                if m.get("type") == "state" and m.get("back"):
                    self.back = m
                else:
                    self.early.append(m)
            except queue.Empty:
                pass

    def wait_for(self, kind, seconds=8):
        import queue
        deadline = time.time() + seconds
        while True:
            try:
                m = self.net.inbox.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                return None, "no answer from the server"
            if m["type"] == kind:
                return m, ""
            if m["type"] == "closed":
                return None, m.get("reason") or "the server closed the connection"

    def take_lesson(self, lesson):
        if isinstance(lesson, dict) and lesson.get("mission") in ("wake_up_call", "lights_out"):
            self.lesson = lesson
            return lesson["mission"]
        return None

    def send(self, msg):
        if self.net is not None:
            self.net.send(msg)

    def messages(self):
        """What has come from the server since the last frame."""
        import queue
        out, self.early = list(getattr(self, "early", [])), []
        if self.net is None:
            return out
        while True:
            try:
                out.append(self.net.inbox.get_nowait())
            except queue.Empty:
                return out


LINK = ClassLink() if args.host else None
# (CHANGE 198) a class server that runs the missions: the programs go to it and its events are played here
RUNS_ON_SERVER = LINK is not None and LINK.net is not None and getattr(LINK, "runs_here", False)
SERVER_WAIT = 10.0  # seconds a run waits for the server before it is run on this computer instead
GHOST_TINT = (0.55, 0.6, 0.72, 1)  # the others' robots, dimmed
if LINK is not None and LINK.lesson:
    args.mission = LINK.lesson["mission"]  # (the lesson's mission: the first screen can still change it)
if LINK is not None and LINK.net is not None and not args.progress and LINK.role == "learner":
    # the learner's own progress file on this computer, seeded from the server's copy (the server's is the truth:
    # it follows the learner to any laptop)
    PROGRESS = os.path.join(SETTINGS_DIR, f"missions_progress_{re.sub(r'[^a-z0-9]+', '-', LINK.name.lower())}.json")
    if LINK.progress is not None:
        try:
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            with open(PROGRESS, "w", encoding="utf-8") as f:
                json.dump(LINK.progress, f, indent=1)
        except OSError:
            pass
loadPrcFileData("", hud.window_arg(args.window) + f"window-title {WINDOW_TITLES[args.mission]}\n"
                + gfx_tiers.prc_for(GFX))
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\nwin-size 1600 900\naudio-library-name null\n")

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import (Filename, Geom, GeomNode, GeomTrifans, GeomVertexData, GeomVertexFormat,  # noqa: E402
                          GeomVertexWriter, MouseButton, Point2, Point3, Quat, TextNode, Vec3, WindowProperties)

import lab_missions  # noqa: E402
import lab_sim as sim  # noqa: E402
import mission_lights_out  # noqa: E402
import mission_pseudo as P  # noqa: E402
import mission_wake_up  # noqa: E402
import rw_fx  # noqa: E402
import rw_gfx  # noqa: E402
import rw_mods  # noqa: E402
from engine import rw_sound  # noqa: E402
from engine.rw_mesh import Mesh, bevel_box, cylinder, prism  # noqa: E402

# The missions this window plays, in the first screen's order. G is the one chosen (use_mission), as DICTIONARY,
# STORY, TITLE and STARTER are its: each mission's rules are its own module, read through the same names.
MISSIONS = {"wake_up_call": mission_wake_up, "lights_out": mission_lights_out}
G = mission_wake_up
SQ = 2.0  # metres a square
D = hud.DARK  # (the HUD over the 3D is always the dark look, as every game's)
YELLOW, WHITE, GREY, RED, GREEN, BLUE, ORANGE = (D[k] for k in ("YELLOW", "WHITE", "GREY", "RED", "GREEN", "BLUE", "ORANGE"))
PANEL = (0.03, 0.04, 0.07, 0.86)
TONES = {"ok": GREEN, "bad": RED, "info": GREY, None: GREY}
GOLD, DIM_STAR = (1, 0.82, 0.2, 1), (0.3, 0.32, 0.38, 1)
# how long each event is animated (seconds): the prototype's, so a run feels the same
DURATION = {"move": 0.23, "turn": 0.2, "bump": 0.42, "use": 0.65, "objective": 0.7, "complete": 0.9, "flat": 0.6,
            # (Mission 2's: a night begins, an if's question, a variable changes, the panel, a repair, a report)
            "night": 1.1, "check": 0.14, "set": 0.12, "solar": 0.3, "repair": 0.6, "report": 0.8, "stop": 0.5}
STARTERS = {
    "wake_up_call": ["# Wake-Up Call. Write one instruction per line, then press RUN (or Ctrl+Enter).",
                     "# The phrasebook below lists what the robot understands.", "", ""],
    "lights_out": mission_lights_out.STARTER,
}
# Each mission's own words in the window (Mission 1's as they were before Mission 2 came)
TEXTS = {
    "wake_up_call": {
        "story": "Your robot has crash-landed in the hills above Brookfield, and the village's power has failed.\n"
                 "Its battery is nearly flat. Find a power cell, pick up a tool from the supply crate, clear the\n"
                 "rockfall in the pass, reach Brookfield and repair its power supply. You drive it with code.",
        "rules": "The whole valley is in view. Every square you drive costs 1 energy; turning and picking up are free;\n"
                 "using a tool costs 2 and a repair 3. Stars: one for finishing, one for 6 or more energy left, one for\n"
                 "{lines} or fewer lines of code run. Finishing unlocks a robot part for Mission 2.",
        "legend": "Stars: finish   {energy}+ energy left   {lines} or fewer lines run",
        "first": "Press C to open the code panel. First objective: find the power cell.",
        "stopped": "The run stopped there. Your robot stays where it is: write the next lines and run again.",
        "done": "Mission complete: the lights are on all over Brookfield.",
    },
    "lights_out": {
        "story": "Night has fallen over Brookfield. A storm has brought rocks down on the hill road to the radio mast\n"
                 "and put some of its lamps out, in different places every night. One program has to work on three\n"
                 "nights: look with if and else, keep count with a variable, and report the count from the mast.",
        "rules": "Every run starts from the bottom of the road and plays nights 1, 2 and 3. A square costs 1 energy, the\n"
                 "spinner 2, a repair 3; turning, the sensors and variables are free. Stars: one for finishing, one for\n"
                 "{energy} or more energy left every night, one for {lines} or fewer lines of code.",
        "legend": "Stars: finish   {energy}+ energy every night   {lines} or fewer lines",
        "first": "Press C to open the code panel. Your program will run on three nights, from the start each time.",
        "stopped": "That night went wrong, so the run stopped. Change the program and run again: every run starts "
                   "from night 1.",
        "done": "Mission complete: one program lit the hill road on all three nights.",
    },
}


def use_mission(mid):
    """Point the window's mission names at mid's: its rules (G), dictionary, story, title and starter code."""
    global G, DICTIONARY, STORY, TITLE, STARTER, TEXT
    G = MISSIONS[mid]
    DICTIONARY = os.path.join(HERE, "missions", mid, "dictionary.json")
    STORY = lab_missions.STORY_MISSIONS[mid]
    TITLE = f"MISSION {STORY['number']}: {STORY['title'].upper()}"
    STARTER = STARTERS[mid]
    TEXT = {k: v.format(**G.RULES["stars"]) for k, v in TEXTS[mid].items()}


use_mission(args.mission)
# The camera: zoom 1 is the whole valley; ZOOM_MAX keeps the map a good third of the picture (the camera about 70 m
# out in the valley view). PAN_REACH: how far the right mouse button can drag the view past the map's edge, metres.
ZOOM_MIN, ZOOM_MAX = 0.35, 2.2
PAN_REACH = 8.0
# mesh and lines: the engine's black fog fades the lines out between 16 and 60 m (Robot Lab's arena is 20 m
# across), but this camera is 32 m out at zoom 1 and 70 m at ZOOM_MAX, so the valley went dark as it zoomed out
# (CHANGE 188). The mission has no fog of war: its fade starts well beyond the furthest the camera can get.
LOOK_FADE = (160.0, 400.0)


def world(x, y, z=0.0):
    """A square (x across, y down the map) to the world: x east, y north, the map's middle at 0, 0."""
    return Point3((x - (G.W - 1) / 2) * SQ, ((G.H - 1) / 2 - y) * SQ, z)


def unpack_events(before, events):
    """(CHANGE 198) A class server's run: each event's whole state again from what changed ("d", missions_server)."""
    cur, out = dict(before), []
    for e in events:
        cur = dict(cur, **e.get("d", {}))
        out.append(dict({k: v for k, v in e.items() if k != "d"}, state=cur))
    return out


def heading(d):
    """The map's direction (0 north, 1 east...) as Panda3D's heading (degrees, anticlockwise)."""
    return -90.0 * d


def hashed(x, y, k=0):
    """The prototype's tile hash: the same rocks in the same places every time."""
    h = (x * 374761393 + y * 668265263 + k * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFFFF) / 4294967296


def shown(text):
    """Text as the HUD's font can draw it."""
    return str(text).replace("→", "->")


def star(parent, x, y, r, colour):
    """A five-pointed star (the font has none)."""
    data = GeomVertexData("star", GeomVertexFormat.getV3(), Geom.UHStatic)
    w = GeomVertexWriter(data, "vertex")
    w.addData3(0, 0, 0)
    for i in range(11):
        a = math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        w.addData3(rr * math.cos(a), 0, rr * math.sin(a))
    fan = GeomTrifans(Geom.UHStatic)
    fan.addConsecutiveVertices(0, 12)
    fan.closePrimitive()
    geom = Geom(data)
    geom.addPrimitive(fan)
    node = GeomNode("star")
    node.addGeom(geom)
    np_ = parent.attachNewNode(node)
    np_.setPos(x, 0, y)
    np_.setColor(*colour)
    np_.setTwoSided(True)
    return np_


class PseudoEditor(editor.CodeEditor):
    """The engine's code editor (the code panel's), telling the window when the text changes. It never changes what
    is typed: no auto-correct, no autocomplete."""

    def __init__(self, *a, on_change=None, **k):
        self.on_change = on_change
        super().__init__(*a, **k)

    def changed(self):
        super().changed()
        if self.on_change:
            self.on_change()


class Valley:
    """The mission's map in 3D: the hills, the grass with its squares, the power cell, the supply crate and its
    tools, the rockfall, Brookfield (its paving, houses, street lamps and power supply) and the sign."""

    def __init__(self, render):
        self.root = render.attachNewNode("valley")
        part = rw_gfx.part
        static = self.root.attachNewNode("static")
        scenery = self.root.attachNewNode("scenery")  # (round the map: not drawn on mesh and lines, where the
        #                                               big shapes' edges would cut across the picture)
        under = Mesh(tile=0.25)  # the soil under everything: shows between the squares as the grid's lines
        bevel_box(G.W * SQ / 2 + 30, G.H * SQ / 2 + 30, 0.1, 0.02, mesh=under, offset=Vec3(0, 0, -0.14))
        part(scenery, under, "concrete", (0.25, 0.22, 0.16), rough=1.0, metal=0.0)
        grass = [Mesh(tile=0.5), Mesh(tile=0.5)]
        paving, rocks = Mesh(tile=0.7), Mesh(tile=0.6)
        g = SQ / 2 - 0.035  # (a square, less half the grid line)
        for y, row in enumerate(G.MAP):
            for x, t in enumerate(row):
                p = world(x, y)
                if t in "VHG":
                    bevel_box(g, g, 0.04, 0.01, mesh=paving, offset=Vec3(p.x, p.y, -0.04))
                elif t != "#":
                    bevel_box(g, g, 0.04, 0.01, mesh=grass[(x + y) % 2], offset=Vec3(p.x, p.y, -0.04))
                else:
                    self.hill(rocks, x, y)
        part(static, grass[0], "concrete", (0.42, 0.58, 0.26), rough=1.0, metal=0.0)
        part(static, grass[1], "concrete", (0.36, 0.52, 0.22), rough=1.0, metal=0.0)
        part(static, paving, "concrete", (0.78, 0.71, 0.55), rough=0.9, metal=0.0)
        part(static, rocks, "concrete", (0.46, 0.44, 0.42), rough=1.0, metal=0.0)
        self.backdrop(scenery)
        scenery.flattenStrong()
        if rw_gfx.look():
            scenery.hide()
        self.skid_marks(static)
        self.lit = []  # (material, off, on) of everything that lights up when the power comes back
        self.lamps(static)
        for y, row in enumerate(G.MAP):
            for x, t in enumerate(row):
                if t == "H":
                    self.house(static, x, y)
        self.sign(static)
        static.flattenStrong()
        self.supply = self.power_supply(*self.where("G"))
        self.cell = self.power_cell(*self.where("C"))
        self.crate, self.tools = self.supply_crate(*self.where("T"))
        self.rockfall, self.rubble, self.rock_parts = self.rocks(*self.where("R"))
        if rw_gfx.look():  # mesh and lines: every face black, its edges in the line colour
            for np_ in [static, self.supply, self.cell, self.crate, self.rockfall, self.rubble] + list(self.tools.values()):
                rw_gfx.outline(np_)
        self.state = None
        self.t = 0.0

    @staticmethod
    def where(ch):
        f = G.find(ch)
        return f["x"], f["y"]

    def hill(self, mesh, x, y):
        """A rock wall square: boulders, higher towards the back so the valley can be seen from the south."""
        p = world(x, y)
        back = 1.0 - y / (G.H - 1)
        inner = 0 < x < G.W - 1 and 0 < y < G.H - 1  # (the cliff between the valley and the village)
        height = 0.45 + (1.5 if inner else 0.4 + 2.2 * back) * (0.7 + 0.5 * hashed(x, y, 1))
        if y == G.H - 1:
            height = 0.35 + 0.25 * hashed(x, y, 2)  # (the front row stays low: the camera looks over it)
        for k in range(3):
            hx = SQ * (0.28 + 0.2 * hashed(x, y, k + 3))
            hy = SQ * (0.28 + 0.2 * hashed(x, y, k + 6))
            hz = height * (0.55 + 0.45 * hashed(x, y, k + 9)) / 2
            ox = (hashed(x, y, k + 12) - 0.5) * SQ * 0.45
            oy = (hashed(x, y, k + 15) - 0.5) * SQ * 0.45
            bevel_box(hx, hy, hz, 0.12, mesh=mesh, offset=Vec3(p.x + ox, p.y + oy, hz - 0.05))

    def backdrop(self, static):
        """Hills round the valley, so it is a valley (the map's edge isn't the world's)."""
        hills = Mesh(tile=0.15)
        w, h = G.W * SQ / 2, G.H * SQ / 2
        for i in range(26):
            a = i / 26 * 2 * math.pi
            r = 1.15 + 0.25 * hashed(i, 7)
            x, y = math.cos(a) * w * r * 1.25, math.sin(a) * h * r * 1.6
            if y < -h:  # (none in front of the camera)
                continue
            size = 3 + 4 * hashed(i, 3)
            bevel_box(size, size * 0.8, size * (0.5 + 0.6 * hashed(i, 5)), 0.8, mesh=hills, offset=Vec3(x, y, 0))
        rw_gfx.part(static, hills, "concrete", (0.3, 0.36, 0.24), rough=1.0, metal=0.0)

    def skid_marks(self, static):
        """The crash landing's two skid marks behind the start."""
        f = G.find("S")
        p = world(f["x"], f["y"])
        for s in (-1, 1):
            mark = rw_gfx.part(static, bevel_box(0.09, 0.75, 0.005, 0.002), None, (0.12, 0.09, 0.06), rough=1.0, metal=0.0,
                               pos=(p.x + s * 0.42 + 0.3, p.y - 0.7, 0.003), hpr=(-24, 0, 0))
            mark.setTwoSided(True)

    def glow(self, parent, mesh, colour, off, on, pos=(0, 0, 0)):
        """A part that lights up when the power comes back."""
        np_ = rw_gfx.part(parent, mesh, None, colour, 0.4, 0.0, emission=off, pos=pos)
        self.lit.append((rw_gfx.glow_material(np_), off, on))
        return np_

    def house(self, static, x, y):
        p = world(x, y)
        wall, roof = (0.86, 0.8, 0.68), (0.62, 0.22, 0.16)
        rw_gfx.part(static, bevel_box(0.75, 0.68, 0.6, 0.03), "paint", wall, rough=0.9, metal=0.0, pos=(p.x, p.y, 0.6))
        rw_gfx.part(static, prism([(-0.85, 0), (0.85, 0), (0, 0.6)], 0.85), "paint", roof, rough=0.8, metal=0.0,
                    pos=(p.x, p.y, 1.2), hpr=(90, 0, 0))
        rw_gfx.part(static, bevel_box(0.16, 0.02, 0.28, 0.01), "paint", (0.35, 0.22, 0.14), pos=(p.x, p.y - 0.69, 0.28))
        windows = Mesh()
        for wx in (-0.42, 0.42):
            bevel_box(0.14, 0.015, 0.12, 0.005, mesh=windows, offset=Vec3(wx, -0.69, 0.72))
        bevel_box(0.015, 0.14, 0.12, 0.005, mesh=windows, offset=Vec3(-0.76, 0, 0.72))
        bevel_box(0.015, 0.14, 0.12, 0.005, mesh=windows, offset=Vec3(0.76, 0, 0.72))
        self.glow(static, windows, (0.1, 0.11, 0.14), (0.01, 0.012, 0.02), (5.0, 3.6, 1.4), pos=(p.x, p.y, 0))

    def lamps(self, static):
        """Street lamps round the village square: dark until the power comes back."""
        for x, y in ((9, 2), (14, 2), (9, 6), (14, 6), (12, 4)):
            p = world(x, y)
            ox, oy = p.x + (0.75 if x < 12 else -0.75), p.y + 0.75
            rw_gfx.part(static, cylinder(0.045, 1.1, seg=10), "steel", (0.2, 0.21, 0.23), pos=(ox, oy, 1.1))
            self.glow(static, cylinder(0.13, 0.08, seg=14), (0.15, 0.15, 0.15), (0.02, 0.02, 0.02), (6, 5, 2.5),
                      pos=(ox, oy, 2.25))

    def sign(self, static):
        """BROOKFIELD on a board on the cliff above the village."""
        p = world(11.5, 1)
        for s in (-1, 1):
            rw_gfx.part(static, cylinder(0.07, 0.9, seg=8), "paint", (0.4, 0.27, 0.15), pos=(p.x + s * 1.9, p.y, 2.4))
        rw_gfx.part(static, bevel_box(2.3, 0.06, 0.42, 0.03), "paint", (0.32, 0.2, 0.1), pos=(p.x, p.y, 3.2))
        tn = TextNode("brookfield")
        tn.setText("BROOKFIELD")
        tn.setAlign(TextNode.ACenter)
        tn.setTextColor(1, 0.92, 0.7, 1)
        t = static.attachNewNode(tn)
        t.setPos(p.x, p.y - 0.07, 3.06)
        t.setScale(0.52)
        t.setLightOff(1)
        if rw_gfx.look():
            rw_gfx.lettering(t)

    def power_supply(self, x, y):
        """The village power supply: a cabinet with a lightning bolt, its warning light blinking until it's mended."""
        p = world(x, y)
        root = self.root.attachNewNode("power supply")
        root.setPos(p)
        rw_gfx.part(root, bevel_box(0.55, 0.42, 0.75, 0.04, tile=1.5), "steel", (0.25, 0.33, 0.45), rough=0.6, metal=0.8,
                    pos=(0, 0, 0.75))
        rw_gfx.part(root, bevel_box(0.62, 0.5, 0.05, 0.02), "steel", (0.2, 0.22, 0.25), pos=(0, 0, 1.53))
        bolt = Mesh()  # a lightning bolt on each face, in two convex pieces (prism needs convex shapes)
        for side in (-1, 1):
            o = Vec3(side * 0.435, 0, 0)  # (along x before the turn: the faces north and south after it)
            prism([(-0.12, 0.04), (0.0, 0.04), (0.1, 0.32), (-0.02, 0.32)], 0.012, mesh=bolt, offset=o)
            prism([(-0.06, 0.08), (0.12, 0.08), (-0.02, -0.3)], 0.012, mesh=bolt, offset=o)
        self.bolt = self.glow(root, bolt, (0.35, 0.36, 0.4), (0.05, 0.05, 0.05), (8, 6, 0.6), pos=(0, 0, 0.85))
        self.bolt.setH(90)
        self.warning = rw_gfx.part(root, cylinder(0.06, 0.05, seg=12), None, (0, 0, 0), 0.3, 0.0, emission=(6, 0.4, 0.2),
                                   pos=(0.4, 0.3, 1.62))
        return root

    def power_cell(self, x, y):
        p = world(x, y)
        root = self.root.attachNewNode("power cell")
        root.setPos(p)
        rw_gfx.part(root, cylinder(0.5, 0.03, seg=28), "steel", (0.3, 0.32, 0.35), pos=(0, 0, 0.03))
        self.cell_body = root.attachNewNode("cell")
        rw_gfx.part(self.cell_body, cylinder(0.2, 0.32, seg=20, bevel=0.03), "paint", (0.16, 0.45, 0.26), rough=0.5,
                    metal=0.3, pos=(0, 0, 0.62))
        rw_gfx.part(self.cell_body, cylinder(0.08, 0.06, seg=12), "steel", (0.7, 0.7, 0.72), pos=(0, 0, 1.0))
        rw_gfx.part(self.cell_body, cylinder(0.205, 0.12, seg=20), None, (0, 0, 0), 0.3, 0.0, emission=(0.6, 3.2, 1.2),
                    pos=(0, 0, 0.62))
        return root

    def supply_crate(self, x, y):
        """The supply crate, with the four tools on it (the one the robot holds isn't)."""
        p = world(x, y)
        root = self.root.attachNewNode("supply crate")
        root.setPos(p.x, p.y + 0.35, 0)
        wood, steel = (0.62, 0.45, 0.25), (0.75, 0.77, 0.8)
        rw_gfx.part(root, bevel_box(0.85, 0.5, 0.3, 0.03, tile=1.2), "paint", wood, rough=0.9, metal=0.0, pos=(0, 0, 0.3))
        for s in (-1, 1):
            rw_gfx.part(root, bevel_box(0.87, 0.52, 0.03, 0.01), "paint", (0.4, 0.28, 0.15), pos=(0, 0, 0.3 + s * 0.2))
        tools = {}
        for k, name in enumerate(("spinner", "flipper", "hammer", "drum")):
            t = root.attachNewNode(name)
            t.setPos(-0.6 + k * 0.4, 0, 0.64)
            if name == "spinner":
                rw_gfx.part(t, bevel_box(0.17, 0.035, 0.02, 0.008), "steel", steel)
                rw_gfx.part(t, cylinder(0.035, 0.03, seg=12), "steel", (0.3, 0.3, 0.32))
            elif name == "flipper":
                rw_gfx.part(t, prism([(-0.15, -0.03), (0.15, -0.03), (0.1, 0.06), (-0.1, 0.06)], 0.13), "steel", steel)
            elif name == "hammer":
                rw_gfx.part(t, bevel_box(0.02, 0.16, 0.02, 0.006), "steel", (0.4, 0.4, 0.42), pos=(0, -0.02, 0))
                rw_gfx.part(t, bevel_box(0.07, 0.05, 0.05, 0.01), "steel", (0.25, 0.25, 0.27), pos=(0, 0.15, 0.02))
            else:
                rw_gfx.part(t, cylinder(0.06, 0.13, axis="x", seg=16), "steel", steel)
            tools[name] = t
        return root, tools

    def rocks(self, x, y):
        """The rockfall in the pass: a pile of boulders, and the rubble left when it's cleared."""
        p = world(x, y)
        pile = self.root.attachNewNode("rockfall")
        pile.setPos(p)
        parts = []
        colours = ((0.54, 0.42, 0.29), (0.63, 0.49, 0.34), (0.44, 0.34, 0.24))
        for k in range(11):
            s = 0.25 + 0.3 * hashed(x, y, k + 20)
            pos = ((hashed(x, y, k + 30) - 0.5) * SQ * 0.8, (hashed(x, y, k + 40) - 0.5) * SQ * 0.75,
                   s * 0.8 + (0.5 if k > 6 else 0.0))
            r = rw_gfx.part(pile, bevel_box(s, s * 0.85, s * 0.8, s * 0.3), "concrete", colours[k % 3], rough=1.0,
                            metal=0.0, pos=pos, hpr=(hashed(x, y, k) * 90, hashed(x, y, k + 1) * 30 - 15, 0))
            parts.append((r, Point3(*pos)))
        rubble = self.root.attachNewNode("rubble")
        rubble.setPos(p)
        gravel = Mesh(tile=1.0)
        for k in range(14):
            s = 0.05 + 0.06 * hashed(x, y, k + 50)
            bevel_box(s, s, s * 0.6, s * 0.3, mesh=gravel,
                      offset=Vec3((hashed(x, y, k + 60) - 0.5) * SQ * 0.9, (hashed(x, y, k + 70) - 0.5) * SQ * 0.9, s * 0.5))
        rw_gfx.part(rubble, gravel, "concrete", (0.6, 0.55, 0.45), rough=1.0, metal=0.0)
        rubble.hide()
        return pile, rubble, parts

    def show(self, s):
        """Draw the map as it is in the mission's state s."""
        self.state = s
        self.cell.show() if not s["cellTaken"] else self.cell.hide()
        for name, t in self.tools.items():
            t.show() if name != s["tool"] else t.hide()
        if s["rockCleared"]:
            self.rockfall.hide()
            self.rubble.show()
        else:
            self.rockfall.show()
            self.rubble.hide()
            for r, pos in self.rock_parts:
                r.setPos(pos)
                r.setScale(1)
        for mat, off, on in self.lit:
            mat.setEmission((*(on if s["repaired"] else off), 1))

    def clearing(self, k):
        """The rockfall flying apart as the spinner grinds through it (k from 0 to 1)."""
        self.rockfall.show()
        for i, (r, pos) in enumerate(self.rock_parts):
            a = i * 2.4
            out = Vec3(math.cos(a), math.sin(a) * 0.5 + 0.6, 0) * (k * 2.2)
            r.setPos(pos + out + Vec3(0, 0, 2.5 * k * (1 - k)))
            r.setScale(max(0.05, 1 - k))

    def update(self, dt):
        self.t += dt
        if self.state is not None and not self.state["cellTaken"]:  # the power cell bobs and turns, to be seen
            self.cell_body.setZ(0.08 * math.sin(self.t * 2.2))
            self.cell_body.setH(self.t * 40)
        on = self.state is not None and self.state["repaired"]
        blink = int(self.t * 2) % 2 == 0
        rw_gfx.glow_material(self.warning).setEmission((0.3, 5, 0.6, 1) if on else ((6, 0.4, 0.2, 1) if blink else (0.3, 0.02, 0.01, 1)))

    # ---------- what the window asks of a mission's scene (Mission 2's HillRoad answers the same) ----------
    def reset(self):
        """The mission back at its start: the power cell as it was before it was picked up."""
        self.cell_body.setScale(1)
        self.cell_body.setZ(0)

    def animate(self, ev, before, k, w):
        """An event k (0 to 1) of the way through: the rockfall flying apart, the power cell lifting into the robot."""
        if ev["type"] == "use" and ev["state"]["rockCleared"] and not before["rockCleared"]:
            self.clearing(k)
            if int(w.event_t * 30) % 3 == 0:
                w.fx.stream(tuple(self.rockfall.getPos() + Vec3(0, -0.8, 0.4)), Vec3(0, -1, 0.6), 3)
        if ev["type"] == "objective" and ev["state"]["cellTaken"] and not before["cellTaken"]:
            self.cell_body.setZ(1.5 * k)
            self.cell_body.setScale(max(0.05, 1 - k))

    def settle(self, ev):
        """An event's animation over (before the window takes its state)."""
        if ev["state"]["cellTaken"]:
            self.cell_body.setScale(1)

    def landed(self, ev, before, fx):
        """An event done: the rocks' burst as the pass clears, the sparks as the power comes back."""
        if ev["state"]["rockCleared"] and not before["rockCleared"]:
            fx.impact(tuple(self.rockfall.getPos() + Vec3(0, 0, 0.6)), 40, "break", (0.55, 0.43, 0.3))
        if ev["type"] == "complete":
            fx.impact(tuple(self.supply.getPos() + Vec3(0, 0, 1.6)), 25, "spinner", (1, 0.9, 0.4))

    def destroy(self):
        self.root.removeNode()


class HillRoad(Valley):
    """Mission 2's map in 3D, at night: the hill road from Brookfield (its houses lit since Mission 1) up to the
    radio mast, the lamp posts beside it (dark or lit), tonight's rockfalls, the fence and the fields below. Valley's
    hills, houses, rocks and glowing parts, on mission_lights_out.MAP."""

    def __init__(self, render):
        self.root = render.attachNewNode("hill road")
        part = rw_gfx.part
        static = self.root.attachNewNode("static")
        scenery = self.root.attachNewNode("scenery")
        under = Mesh(tile=0.25)
        bevel_box(G.W * SQ / 2 + 30, G.H * SQ / 2 + 30, 0.1, 0.02, mesh=under, offset=Vec3(0, 0, -0.14))
        part(scenery, under, "concrete", (0.12, 0.13, 0.1), rough=1.0, metal=0.0)
        grass = [Mesh(tile=0.5), Mesh(tile=0.5)]
        road, paving, field, rocks = Mesh(tile=0.7), Mesh(tile=0.7), Mesh(tile=0.5), Mesh(tile=0.6)
        g = SQ / 2 - 0.035
        for y, row in enumerate(G.MAP):
            for x, t in enumerate(row):
                p = world(x, y)
                if t in "VH":
                    bevel_box(g, g, 0.04, 0.01, mesh=paving, offset=Vec3(p.x, p.y, -0.04))
                elif t in ".SM":
                    bevel_box(g, g, 0.04, 0.01, mesh=road, offset=Vec3(p.x, p.y, -0.04))
                elif t == "~":
                    bevel_box(g, g, 0.04, 0.01, mesh=field, offset=Vec3(p.x, p.y, -0.04))
                elif t in "LF":
                    bevel_box(g, g, 0.04, 0.01, mesh=grass[(x + y) % 2], offset=Vec3(p.x, p.y, -0.04))
                else:
                    self.hill(rocks, x, y)
        part(static, grass[0], "concrete", (0.2, 0.32, 0.16), rough=1.0, metal=0.0)
        part(static, grass[1], "concrete", (0.17, 0.28, 0.13), rough=1.0, metal=0.0)
        part(static, road, "concrete", (0.3, 0.3, 0.32), rough=0.95, metal=0.0)
        part(static, paving, "concrete", (0.62, 0.56, 0.44), rough=0.9, metal=0.0)
        part(static, field, "concrete", (0.3, 0.27, 0.15), rough=1.0, metal=0.0)
        part(static, rocks, "concrete", (0.36, 0.35, 0.34), rough=1.0, metal=0.0)
        self.backdrop(scenery)
        scenery.flattenStrong()
        if rw_gfx.look():
            scenery.hide()
        self.lit = []
        for y, row in enumerate(G.MAP):
            for x, t in enumerate(row):
                if t == "H":
                    self.house(static, x, y)
                elif t == "F":
                    self.fence(static, x, y)
        static.flattenStrong()
        self.lamps = {x: self.lamp_post(x, G.ROAD_Y - 1) for x in G.LAMPS}
        self.mast, self.mast_light = self.radio_mast(G.MAST["x"], G.MAST["y"])
        road_xs = sorted({x for n in G.NIGHTS for x in n["rocks"]})
        self.piles = {}  # each road square a rocks fall on: its pile and the rubble left when it's cleared
        for x in road_xs:
            self.piles[x] = self.rocks(x, G.ROAD_Y)
        if rw_gfx.look():
            for np_ in [static, self.mast] + [lp for lp, _ in self.lamps.values()] + \
                    [n for pile, rubble, _ in self.piles.values() for n in (pile, rubble)]:
                rw_gfx.outline(np_)
        self.state = None
        self.t = 0.0
        self.flash = 0.0

    def fence(self, static, x, y):
        """A post and two rails on the road's downhill side."""
        p = world(x, y)
        wood = (0.4, 0.3, 0.2)
        rw_gfx.part(static, bevel_box(0.06, 0.06, 0.4, 0.01), "paint", wood, rough=0.9, metal=0.0,
                    pos=(p.x - 0.9, p.y + 0.6, 0.4))
        for z in (0.35, 0.65):
            rw_gfx.part(static, bevel_box(1.0, 0.03, 0.04, 0.01), "paint", wood, rough=0.9, metal=0.0,
                        pos=(p.x, p.y + 0.6, z))

    def lamp_post(self, x, y):
        """A street lamp on the bank above the road, its head over the road: dark until it's repaired."""
        p = world(x, y)
        root = self.root.attachNewNode(f"lamp {x}")
        root.setPos(p.x, p.y - 0.55, 0)
        rw_gfx.part(root, bevel_box(0.25, 0.25, 0.08, 0.02), "concrete", (0.35, 0.35, 0.36), pos=(0, 0, 0.08))
        rw_gfx.part(root, cylinder(0.055, 1.4, seg=10), "steel", (0.2, 0.21, 0.23), pos=(0, 0, 1.4))
        rw_gfx.part(root, bevel_box(0.04, 0.4, 0.04, 0.01), "steel", (0.2, 0.21, 0.23), pos=(0, -0.38, 2.78))
        head = rw_gfx.part(root, cylinder(0.16, 0.07, seg=14), None, (0.15, 0.15, 0.15), 0.4, 0.0,
                           emission=(0.02, 0.02, 0.02), pos=(0, -0.72, 2.72))
        return root, rw_gfx.glow_material(head)

    def radio_mast(self, x, y):
        """The radio mast at the top of the road: a lattice tower, a dish and a light that blinks red until the
        night's report arrives."""
        p = world(x, y)
        root = self.root.attachNewNode("radio mast")
        root.setPos(p)
        steel = (0.55, 0.57, 0.6)
        rw_gfx.part(root, bevel_box(0.7, 0.7, 0.12, 0.03), "concrete", (0.4, 0.4, 0.42), pos=(0, 0, 0.12))
        for sx in (-1, 1):
            for sy in (-1, 1):
                rw_gfx.part(root, bevel_box(0.04, 0.04, 2.6, 0.01), "steel", steel,
                            pos=(sx * 0.3, sy * 0.3, 2.7), hpr=(0, sy * -3, sx * 3))
        for z in (1.0, 2.2, 3.4, 4.5):
            w = 0.36 - z * 0.035
            rw_gfx.part(root, bevel_box(w, w, 0.025, 0.01), "steel", steel, pos=(0, 0, z))
        rw_gfx.part(root, cylinder(0.32, 0.06, axis="x", seg=18), "paint", (0.85, 0.86, 0.88), pos=(-0.3, 0, 3.8),
                    hpr=(0, 0, 0))
        rw_gfx.part(root, bevel_box(0.25, 0.2, 0.3, 0.02), "paint", (0.85, 0.82, 0.3), rough=0.6, metal=0.1,
                    pos=(0, -0.55, 0.42))
        light = rw_gfx.part(root, cylinder(0.08, 0.06, seg=12), None, (0, 0, 0), 0.3, 0.0, emission=(6, 0.4, 0.2),
                            pos=(0, 0, 5.4))
        return root, light

    def show(self, s):
        self.state = s
        night = mission_lights_out.NIGHTS[s["night"] - 1]
        for x, (pile, rubble, parts) in self.piles.items():
            fallen = x in night["rocks"]
            if x in s["rocks"]:
                pile.show()
                for r, pos in parts:
                    r.setPos(pos)
                    r.setScale(1)
            else:
                pile.hide()
            rubble.show() if fallen and x not in s["rocks"] else rubble.hide()
        for x, (lp, mat) in self.lamps.items():
            mat.setEmission((0.02, 0.02, 0.025, 1) if x in s["dark"] else (7.0, 5.4, 2.4, 1))
        for mat, off, on in self.lit:  # (Brookfield's windows: lit since Mission 1)
            mat.setEmission((*on, 1))

    def clearing_at(self, x, k):
        pile, _, parts = self.piles[x]
        pile.show()
        for i, (r, pos) in enumerate(parts):
            a = i * 2.4
            out = Vec3(math.cos(a), math.sin(a) * 0.5 - 0.6, 0) * (k * 2.2)
            r.setPos(pos + out + Vec3(0, 0, 2.5 * k * (1 - k)))
            r.setScale(max(0.05, 1 - k))

    def update(self, dt):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        s = self.state
        done = s is not None and (s["reported"] or s["complete"])
        blink = int(self.t * 2) % 2 == 0
        rw_gfx.glow_material(self.mast_light).setEmission(
            (0.3, 5, 0.6, 1) if done or self.flash > 0 else ((6, 0.4, 0.2, 1) if blink else (0.3, 0.02, 0.01, 1)))

    def reset(self):
        self.flash = 0.0

    @staticmethod
    def cleared(ev, before):
        gone = [x for x in before["rocks"] if x not in ev["state"]["rocks"]]
        return gone[0] if gone and ev["type"] == "use" else None

    def animate(self, ev, before, k, w):
        x = self.cleared(ev, before)
        if x is not None:
            self.clearing_at(x, k)
            if int(w.event_t * 30) % 3 == 0:
                w.fx.stream(tuple(world(x, G.ROAD_Y) + Vec3(-0.8, 0, 0.4)), Vec3(-1, 0, 0.6), 3)
        if ev["type"] == "repair":
            fixed = [lx for lx in before["dark"] if lx not in ev["state"]["dark"]]
            if fixed:
                b = k * k
                self.lamps[fixed[0]][1].setEmission((7.0 * b, 5.4 * b, 2.4 * b, 1))

    def settle(self, ev):
        pass

    def landed(self, ev, before, fx):
        x = self.cleared(ev, before)
        if x is not None:
            fx.impact(tuple(world(x, G.ROAD_Y) + Vec3(0, 0, 0.6)), 40, "break", (0.5, 0.45, 0.4))
        if ev["type"] == "report" and ev["tone"] == "ok":
            self.flash = 0.8
            fx.impact(tuple(self.mast.getPos() + Vec3(0, 0, 5.4)), 18, "spinner", (0.5, 1, 0.6))
        if ev["type"] == "complete":
            fx.impact(tuple(self.mast.getPos() + Vec3(0, 0, 5.4)), 30, "spinner", (1, 0.9, 0.4))


SCENES = {"wake_up_call": Valley, "lights_out": HillRoad}


class RobotModel:
    """The robot, as Robot Lab draws it (rw_gfx.RobotVisual), holding the tool it picked up: one model for each tool
    (Robot Lab's weapon for it), built when first needed, the one held shown."""

    def __init__(self, render, design):
        self.render, self.design = render, design
        self.models = {}
        self.tool = "none"
        self.spin = 0.0

    def model(self, tool):
        if tool not in self.models:
            weapon = G.TOOLS[tool]["weapon"] if tool in G.TOOLS else self.design["weapon"]
            v = rw_gfx.RobotVisual(self.render, dict(self.design, weapon=weapon))
            if tool not in G.TOOLS:  # (no tool yet: the robot's own weapon isn't fitted)
                v.weapon.hide()
                if v.blur is not None:
                    v.blur.hide()
            sh = v.shape
            rest = 0.0
            if v.weapon_kind == "wedge":  # the flipper's plate rests with its front lip on the ground
                drop = sh["pivot"].z + sim.RIDE - 0.02
                rest = -math.degrees(math.asin(min(1.0, drop / (sh["plate"].y * 2))))
            self.models[tool] = (v, rest)
        return self.models[tool]

    def hold(self, tool):
        tool = tool or "none"
        for name, (v, _) in self.models.items():
            v.root.hide() if name != tool else v.root.show()
        self.model(tool)[0].root.show()
        self.tool = tool

    def place(self, pos, h, dt, speed=0.0, use=0.0, nudge=0.0):
        """Where the robot is (pos, a world point; h, its heading), and how far through using its tool (use, 0 to 1)."""
        v, rest = self.model(self.tool)
        q = Quat()
        q.setHpr((h, 0, 0))
        fwd = q.getForward()
        at = Point3(pos.x, pos.y, sim.RIDE) + fwd * nudge
        local = Quat()
        rpm = 0.0
        kind = v.weapon_kind if self.tool in G.TOOLS else None
        swing = math.sin(math.pi * use)
        if kind in ("spinner", "drum"):
            rpm = 1400 * swing
            self.spin += rpm * 6 * dt
            local.setHpr((self.spin, 0, 0) if kind == "spinner" else (0, -self.spin, 0))
        elif kind == "wedge":
            local.setHpr((0, rest + swing * (40 - rest), 0))
        elif kind == "hammer":
            p = 105 * math.sin(math.pi * min(1.0, use / 0.45)) if use < 0.45 else \
                -18 * math.sin(math.pi * (use - 0.45) / 0.55)
            local.setHpr((0, p, 0))
        else:
            local.setHpr((0, rest, 0))
        wq = local * q
        v.update({"pos": list(at), "quat": list(q), "wpos": list(at + q.xform(Vec3(v.shape["pivot"]))),
                  "wquat": list(wq), "speed": speed, "rpm": rpm}, dt)
        return v

    def front(self, pos, h):
        q = Quat()
        q.setHpr((h, 0, 0))
        return Point3(pos.x, pos.y, 0.4) + q.getForward() * SQ * 0.6


class Ghost:
    """(CHANGE 198) Someone else's robot in the valley, in a class whose server runs the missions: dimmed, its owner's
    name over it, a little off the middle of its square (so two robots on one square both show), playing the steps
    the server sends of each of their runs at the window's own pace (faster when it has fallen behind). Only the
    robots on this window's mission are shown; they never bump into anything of this window's."""

    def __init__(self, app, name, robot, mission):
        self.name, self.robot_name, self.mission = name, robot, mission
        self.node = app.render.attachNewNode("ghost " + name)
        self.node.setColorScale(*GHOST_TINT)
        self.model = RobotModel(self.node, app.designs.get(robot) or G.ROBOTS[robot])
        self.tool, self.at, self.anim, self.steps = None, None, None, []
        self.model.hold(None)
        a = hashed(len(name), sum(map(ord, name)), 3) * math.tau
        self.off = Vec3(math.cos(a) * 0.45, math.sin(a) * 0.45, 0)
        tag = TextNode("name " + name)
        tag.setText(name)
        tag.setAlign(TextNode.ACenter)
        tag.setTextColor(1, 1, 1, 1)
        tag.setCardColor(0.02, 0.08, 0.16, 0.9)
        tag.setCardAsMargin(0.3, 0.3, 0.15, 0.1)
        tag.setCardDecal(True)
        self.tag = self.node.attachNewNode(tag)
        self.tag.setBillboardPointEye()
        self.tag.setScale(0.8)
        self.tag.setTransparency(True)
        self.tag.setShaderOff(1)  # (the scene's lit shader and fog would grey it out)
        self.tag.setFogOff(1)
        self.tag.setLightOff()
        self.tag.setColorScaleOff(1)

    def take(self, steps):
        self.steps.extend(s for s in steps if isinstance(s, list) and len(s) == 5)

    def show(self, on):
        self.node.show() if on else self.node.hide()

    def update(self, dt):
        speed, use = 0.0, 0.0
        while self.anim is None and self.steps:
            kind, x, y, d, tool = self.steps.pop(0)
            if tool != self.tool:
                self.tool = tool
                self.model.hold(tool)
            h = heading(d)
            if self.at is not None:
                h = self.at[2] + (h - self.at[2] + 180) % 360 - 180  # (the short way round)
            to = (x, y, h)
            if kind in ("place", "night") or self.at is None:
                self.at = to
                continue
            hurry = 0.3 if len(self.steps) > 30 else 1.0
            self.anim = [self.at, to, 0.0, DURATION.get(kind, 0.45) * hurry, kind]
        x, y, h = self.at or (0, 0, 0)
        if self.anim is not None:
            (x0, y0, h0), (x1, y1, h1), t, dur, kind = self.anim
            t += dt
            self.anim[2] = t
            k = min(1.0, t / dur) if dur > 0 else 1.0
            e = 2 * k * k if k < 0.5 else 1 - (-2 * k + 2) ** 2 / 2
            x, y, h = x0 + (x1 - x0) * e, y0 + (y1 - y0) * e, h0 + (h1 - h0) * e
            if kind == "move":
                speed = SQ / max(0.05, dur) * math.sin(math.pi * k) * 1.6
            elif kind == "use":
                use = k
            if k >= 1.0:
                self.at, self.anim = (x1, y1, h1), None
        if self.at is None:
            return
        p = world(x, y) + self.off
        self.model.place(p, h, dt, speed, use)
        self.tag.setPos(p.x, p.y, 2.3)

    def where(self):
        return self.at[:2] if self.at else None

    def destroy(self):
        for v, _ in self.model.models.values():
            v.destroy()
        self.node.removeNode()


class RememberedFullScreen(full_screen.FullScreen):
    """The engine's Full screen button (top right, Esc comes back out), and the choice kept on this computer as the
    games' Settings tabs keep it ("fullscreen" in settings.json), so the next start and the launcher's Window
    button agree (CHANGE 189). Esc is the window's own key here (key_escape calls leave())."""

    def toggle(self):
        was = self.on
        super().toggle()
        if self.on != was:
            hud.remember("fullscreen", self.on)


class WakeUpCall(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        gfx_tiers.detect(self, None)
        # the Graphics panel's choice; the Look is solid unless Wireframe was chosen here (CHANGE 188)
        self.gfx = {"look": "solid"} | gfx_choice()
        # the line colour for mesh and lines: the panel's, else the one Robot Lab keeps on this computer, else green
        rw_gfx.init(self, GFX, line_colour=self.gfx.get("line_colour") or hud.SETTINGS.get("line_colour"))
        self.tier = rw_gfx.tier()
        self.sun_colour = rw_gfx.sun().node().getColor() if rw_gfx.sun() is not None else None
        if rw_gfx.look():  # (the lines' fade, moved out past the camera's furthest reach: LOOK_FADE above)
            self.render.getFog().setLinearRange(*LOOK_FADE)
        self.fx = rw_fx.Effects(self.render, "low" if self.tier in ("basic", "low") else self.tier)
        self.snd = rw_sound.Sounds(self, on=not args.no_sound and not args.offscreen)
        self.C = P.load(DICTIONARY)
        self.valley = SCENES[G.MISSION_ID](self.render)  # (the mission's scene: Mission 1's valley, Mission 2's road)
        self.light_scene()
        robots = {}
        try:
            robots = rw_mods.load_all()[0]  # (TITAN and RAZORBACK as the mods folder has them now)
        except Exception as e:
            print("the robots' mod files didn't load, so the mission's own copies are used:", e, flush=True)
        self.designs = {name: dict(robots.get(name.lower()) or G.ROBOTS[name]) for name in G.ROBOTS}
        self.robot_name = None
        self.robot = None
        self.mission = None
        self.view = None
        self.queue, self.event, self.event_t, self.playing = [], None, 0.0, False
        self.cam_mode, self.zoom = "valley", 1.0
        self.cam_pos = None
        self.pan = Vec3(0, 0, 0)  # how far the right mouse button has dragged the view over the map, metres
        self.drag_from = None
        self.options = None       # the Graphics panel, while it is open
        self.msaa0 = getattr(rw_gfx.pipeline(), "msaa_samples", 0)  # (this run's own smoothing: the knobs go back to it)
        self.shadow0 = gfx_tiers.SETTINGS[self.tier]["shadow"]       # (and its shadow map)
        self.code_state = {"lines": list(STARTER), "cursor": [3, 0], "scroll": 0}
        self.parsed = None
        self.read_at = None  # (when to read the code again, after typing)
        self.panel = None
        self.tab = "pseudo"
        self.editor = None
        self.run_line = None
        self.log_lines = []
        self.speed = 0.06 if args.selftest else 0.0 if args.fast else 1.0
        # (CHANGE 198) in a class whose server runs the missions: the others' robots, and a run sent and not yet back
        self.ghosts = {}
        self.server_runs = RUNS_ON_SERVER
        self.waiting = None
        self.build_hud()
        self.build_intro()
        # Full screen, top right, as every game's window (engine.full_screen, CHANGE 146): Esc comes back out of it
        # (key_escape, below, takes the key over: the panel, the end card and quitting come after it); --window full
        # or a full screen kept on this computer opens that way
        self.full = RememberedFullScreen(self)
        if hud.SETTINGS.get("fullscreen") and not args.offscreen:
            self.taskMgr.doMethodLater(0.5, lambda t: self.full.toggle() and None, "full screen at the start")
        for key, fn, a in (("c", self.key_code, []), ("v", self.key_view, []), ("r", self.key_restart, []),
                           ("control-r", self.key_reset, []), ("g", self.key_graphics, []), ("home", self.key_home, []),
                           ("escape", self.key_escape, []), ("control-enter", self.run_code, []),
                           ("1", self.key_choose, ["TITAN"]), ("2", self.key_choose, ["RAZORBACK"]),
                           ("f1", self.key_mission, ["wake_up_call"]), ("f2", self.key_mission, ["lights_out"]),
                           ("wheel_up", self.wheel, [0.88]), ("wheel_down", self.wheel, [1 / 0.88]),
                           ("=", self.wheel, [0.85]), ("+", self.wheel, [0.85]), ("-", self.wheel, [1 / 0.85])):
            self.accept(key, fn, a)
        self.valley.show(G.new_mission("TITAN").snapshot())
        self.apply_gfx()
        if args.zoom:
            self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, args.zoom))
        self.place_camera(1.0)
        if args.robot:
            self.choose(args.robot.upper())
        self.resume_reopened()
        self.start = self.last = self.now = time.perf_counter()
        self.frames = 0
        self.checks = None
        if args.selftest:
            self.checks = self.selftest()
        elif args.replay:
            with open(args.replay, encoding="utf-8") as f:
                self.checks = self.replay(json.load(f))
        self.taskMgr.add(self.update, "update")

    # ---------- the missions: the first screen chooses one ----------
    def light_scene(self):
        """The sky and the key light for the mission's time of day: dusk over Mission 1's valley (Brookfield's
        lights are out), night on Mission 2's hill road (the sun turned to a dim blue moon)."""
        night = G.MISSION_ID == "lights_out"
        if not rw_gfx.look():
            self.setBackgroundColor(*((0.03, 0.04, 0.09) if night else (0.16, 0.22, 0.34)))
        if self.sun_colour is not None:
            rw_gfx.sun().node().setColor((0.38, 0.45, 0.75, 1) if night else self.sun_colour)

    def key_mission(self, mid):
        if not self.intro.isHidden():
            self.choose_mission(mid)

    def choose_mission(self, mid):
        """Another mission, from the first screen: its rules, dictionary, scene, words and starter code; the robot
        is chosen again. The camera and the graphics stay as they are."""
        if mid == G.MISSION_ID:
            return
        self.queue, self.event, self.playing, self.run_line = [], None, False, None
        self.close_panel()
        self.close_done()
        use_mission(mid)
        self.C = P.load(DICTIONARY)
        self.valley.destroy()
        self.valley = SCENES[mid](self.render)
        self.apply_gfx()
        self.light_scene()
        self.mission, self.view = None, None
        self.code_state = {"lines": list(STARTER), "cursor": [len(STARTER) - 1, 0], "scroll": 0}
        self.parsed = None
        self.valley.show(G.new_mission("TITAN").snapshot())
        self.t_title.setText(TITLE)
        self.t_legend.setText(TEXT["legend"])
        if self.robot is not None:
            for v, _ in self.robot.models.values():
                v.root.hide()
        self.robot_name = None
        self.update_hud(G.new_mission("TITAN").snapshot())
        self.t_now.setText("")
        self.banner.hide()
        self.log_lines = []
        self.log(f"{STORY['title']} chosen.", "info")
        self.intro.destroy()
        self.build_intro()
        if hasattr(self.win, "requestProperties"):
            props = WindowProperties()
            props.setTitle(WINDOW_TITLES[mid])
            self.win.requestProperties(props)
        if LINK is not None:
            LINK.send({"type": "mission", "mission": mid})

    def new_mission(self):
        """The chosen mission from its start, with the Solar Panel fitted if Mission 1 unlocked it (Mission 2)."""
        solar = getattr(G, "SOLAR", None)
        if solar:
            return G.new_mission(self.robot_name, solar=G.has_part(PROGRESS, solar["id"]))
        return G.new_mission(self.robot_name)

    # ---------- the HUD ----------
    def build_hud(self):
        a = self.getAspectRatio()
        tl = self.a2dTopLeft
        DirectFrame(parent=tl, frameColor=PANEL, frameSize=(0.03, 0.93, -0.79, -0.03))
        self.t_title = OnscreenText(TITLE, pos=(0.06, -0.1), scale=0.042, fg=YELLOW, align=TextNode.ALeft, parent=tl,
                                    mayChange=True)
        self.t_robot = OnscreenText("", pos=(0.06, -0.155), scale=0.032, fg=WHITE, align=TextNode.ALeft, parent=tl,
                                    mayChange=True)
        OnscreenText("ENERGY", pos=(0.06, -0.205), scale=0.028, fg=GREY, align=TextNode.ALeft, parent=tl)
        DirectFrame(parent=tl, frameColor=(0.15, 0.15, 0.17, 1), frameSize=(0, 0.5, 0, 0.032), pos=(0.2, 0, -0.215))
        self.energy_bar = DirectFrame(parent=tl, frameColor=GREEN, frameSize=(0, 0.5, 0, 0.032), pos=(0.2, 0, -0.215))
        self.t_energy = OnscreenText("", pos=(0.72, -0.205), scale=0.03, fg=WHITE, align=TextNode.ALeft, parent=tl,
                                     mayChange=True)
        self.t_tool = OnscreenText("", pos=(0.06, -0.26), scale=0.03, fg=WHITE, align=TextNode.ALeft, parent=tl,
                                   mayChange=True)
        self.t_lines = OnscreenText("", pos=(0.06, -0.305), scale=0.03, fg=WHITE, align=TextNode.ALeft, parent=tl,
                                    mayChange=True)
        self.live_stars = [star(tl, 0.58 + i * 0.075, -0.285, 0.03, DIM_STAR) for i in range(3)]
        OnscreenText("OBJECTIVES", pos=(0.06, -0.36), scale=0.028, fg=GREY, align=TextNode.ALeft, parent=tl)
        self.t_objectives = [OnscreenText("", pos=(0.06, -0.405 - i * 0.05), scale=0.03, fg=WHITE, align=TextNode.ALeft,
                                          parent=tl, mayChange=True) for i in range(5)]
        self.t_vars = OnscreenText("", pos=(0.06, -0.643), scale=0.027, fg=editor.COLOURS["function"],
                                   align=TextNode.ALeft, parent=tl, mayChange=True)
        self.t_legend = OnscreenText(TEXT["legend"], pos=(0.06, -0.68), scale=0.024, fg=GREY, align=TextNode.ALeft,
                                     parent=tl, mayChange=True)
        # RESET (the mission back to its start, the code kept) and GRAPHICS, always in view (CHANGE 188)
        self.reset_button = DirectButton(parent=tl, text="RESET  Ctrl+R", scale=0.028, pos=(0.17, 0, -0.75),
                                         command=self.reset_mission, relief=DGG.FLAT, pad=(0.5, 0.3),
                                         frameColor=(0.75, 0.5, 0.1, 1), text_fg=(0, 0, 0, 1))
        DirectButton(parent=tl, text="GRAPHICS  G", scale=0.028, pos=(0.44, 0, -0.75), command=self.toggle_options,
                     relief=DGG.FLAT, pad=(0.5, 0.3), frameColor=(0.16, 0.3, 0.42, 1), text_fg=(1, 1, 1, 1))
        DirectButton(parent=tl, text="HOME VIEW", scale=0.028, pos=(0.72, 0, -0.75), command=self.home_camera,
                     relief=DGG.FLAT, pad=(0.5, 0.3), frameColor=(0.16, 0.3, 0.42, 1), text_fg=(1, 1, 1, 1))
        # what to do now, over the middle
        self.t_now = OnscreenText("", pos=(0, -0.08), scale=0.04, fg=YELLOW, parent=self.a2dTopCenter, mayChange=True,
                                  shadow=(0, 0, 0, 0.9))
        # in a class (CHANGE 195): who you are, top right under the Full screen button; the teacher's window lists
        # the class's progress there (each learner's mission, runs, stars and the objectives done)
        self.t_class = OnscreenText("", pos=(-0.06, -0.14), scale=0.028, fg=WHITE, align=TextNode.ARight,
                                    parent=self.a2dTopRight, mayChange=True, shadow=(0, 0, 0, 0.9))
        if LINK is not None:
            self.t_class.setText(LINK.note or (f"CLASS: {LINK.name} ({LINK.role})" + (
                "\nwaiting for the class..." if LINK.role == "teacher" else "")))
        # the log, bottom left
        bl = self.a2dBottomLeft
        self.log_back = DirectFrame(parent=bl, frameColor=PANEL, frameSize=(0.03, 1.33, 0.1, 0.5))
        self.t_log = [OnscreenText("", pos=(0.06, 0.45 - i * 0.048), scale=0.028, fg=GREY, align=TextNode.ALeft,
                                   parent=bl, mayChange=True) for i in range(8)]
        self.t_help = OnscreenText("C code panel   Ctrl+Enter run   Ctrl+R reset   V view   wheel zoom   "
                                   "right-drag pan   Home camera   G graphics   Esc quit",
                                   pos=(0.05, 0.04), scale=0.028, fg=GREY, align=TextNode.ALeft, parent=bl, mayChange=True)
        # the flat battery's banner
        self.banner = DirectFrame(parent=self.aspect2d, frameColor=(0.35, 0.05, 0.05, 0.92), frameSize=(-1.1, 1.1, -0.14, 0.14),
                                  pos=(-0.25, 0, 0.45))
        OnscreenText("The battery is flat and the robot can't move.\nReset the mission (your code is kept) and try a shorter route.",
                     pos=(-0.25, 0.04), scale=0.04, fg=WHITE, parent=self.banner)
        DirectButton(parent=self.banner, text="RESET", scale=0.045, pos=(0.82, 0, -0.01), command=self.reset_mission,
                     frameColor=(0.85, 0.65, 0.1, 1), text_fg=(0, 0, 0, 1), relief=DGG.FLAT, pad=(0.3, 0.2))
        self.banner.hide()
        self.done = None
        self.a = a

    def update_hud(self, s):
        self.t_robot.setText(f"Robot: {self.robot_name or '-'}" + ("" if "solar" not in s else
                             "   Solar Panel fitted" if s["solar"] else "   no Solar Panel"))
        frac = s["energy"] / G.RULES["energyMax"]
        self.energy_bar["frameSize"] = (0, 0.5 * max(0.002, frac), 0, 0.032)
        self.energy_bar["frameColor"] = RED if s["energy"] <= 3 else YELLOW if s["energy"] <= 8 else GREEN
        self.t_energy.setText(f"{s['energy']} / {G.RULES['energyMax']}")
        self.t_tool.setText("Tool: " + (G.TOOLS[s["tool"]]["name"] if s["tool"] else "none")
                            + (f"   Night {s['night']} of {len(G.NIGHTS)}" if "night" in s else ""))
        if "vars" in s:  # (Mission 2: the variables as they are now, live while a run plays)
            names = "   ".join(f"{k} = {v}" for k, v in s["vars"].items()) or "none yet"
            self.t_lines.setText(f"Lines: {s['linesUsed']}")
            self.t_vars.setText(f"VARIABLES   {names}")
        else:
            self.t_lines.setText(f"Lines run: {s['linesUsed']}")
            self.t_vars.setText("")
        if self.mission is None:
            return
        objs = self.mission.objectives(s)
        for t, o in zip(self.t_objectives, objs):
            t.setText(("done  " if o["done"] else ">  " if o["now"] else "    ") + o["title"]
                      + ("" if o["done"] else f": {o['text']}" if o["now"] else ""))
            t.setFg(GREEN if o["done"] else YELLOW if o["now"] else GREY)
        now = next((i for i, o in enumerate(objs) if o["now"]), None)
        self.t_now.setText(f"Now {now + 1}/{len(objs)}: {objs[now]['title']}. {objs[now]['text']}" if now is not None
                           else "All five objectives done")
        st = self.mission.stars(s)
        for on, np_ in zip((s["complete"], s["complete"] and st["energy"], s["complete"] and st["lines"]), self.live_stars):
            np_.setColor(*(GOLD if on else DIM_STAR))

    def log(self, msg, tone=None):
        self.log_lines = (self.log_lines + [(shown(msg), TONES.get(tone, GREY))])[-40:]
        rows = [(line, colour) for text, colour in self.log_lines  # each message wrapped to the box, newest last
                for line in textwrap.wrap(text, 78, subsequent_indent="    ")][-len(self.t_log):]
        for i, t in enumerate(self.t_log):
            text, colour = rows[i] if i < len(rows) else ("", GREY)
            t.setText(text)
            t.setFg(colour)

    # ---------- choosing a robot ----------
    def build_intro(self):
        f = self.intro = DirectFrame(parent=self.aspect2d, frameColor=(0.02, 0.03, 0.05, 0.9), frameSize=(-1.3, 1.3, -0.8, 0.92))
        # the missions, side by side: the one chosen lit (F1 and F2 choose too)
        self.mission_buttons = {}
        for i, mid in enumerate(MISSIONS):
            story = lab_missions.STORY_MISSIONS[mid]
            b = DirectButton(parent=f, text=f"F{i + 1}  MISSION {story['number']}: {story['title'].upper()}",
                             scale=0.036, pos=(-0.42 + i * 0.84, 0, 0.82), relief=DGG.FLAT, pad=(0.6, 0.35),
                             command=self.choose_mission, extraArgs=[mid], text_fg=(1, 1, 1, 1),
                             frameColor=(0.2, 0.55, 0.65, 1) if mid == G.MISSION_ID else (0.12, 0.15, 0.22, 1))
            self.mission_buttons[mid] = b
        OnscreenText(TITLE, pos=(0, 0.66), scale=0.075, fg=YELLOW, parent=f)
        OnscreenText(TEXT["story"], pos=(0, 0.55), scale=0.034, fg=WHITE, parent=f)
        OnscreenText("Choose your robot (or press 1 or 2)", pos=(0, 0.33), scale=0.04, fg=GREY, parent=f)
        for i, name in enumerate(G.ROBOTS):
            r = G.ROBOTS[name]
            d = self.designs[name]
            x = -0.62 + i * 1.24
            col = tuple(c / 255 for c in d["colour"]) + (1,)
            card = DirectButton(parent=f, frameColor=(0.1, 0.12, 0.18, 1), frameSize=(-0.55, 0.55, -0.42, 0.22),
                                pos=(x, 0, 0), relief=DGG.FLAT, command=self.choose, extraArgs=[name])
            card.setName("card " + name)
            OnscreenText(f"{i + 1}  {name}", pos=(0, 0.13), scale=0.06, fg=col, parent=card)
            OnscreenText(r["blurb"], pos=(0, 0.06), scale=0.03, fg=GREY, parent=card)
            for k, (stat, v) in enumerate(d.get("points", r["points"]).items()):
                y = -0.03 - k * 0.075
                OnscreenText(stat, pos=(-0.46, y), scale=0.032, fg=WHITE, align=TextNode.ALeft, parent=card)
                DirectFrame(parent=card, frameColor=col, frameSize=(0, v * 0.012, 0, 0.03), pos=(-0.15, 0, y - 0.005))
                OnscreenText(str(v), pos=(0.47, y), scale=0.032, fg=WHITE, align=TextNode.ARight, parent=card)
        OnscreenText(TEXT["rules"], pos=(0, -0.55), scale=0.03, fg=GREY, parent=f)
        self.t_parts = OnscreenText("", pos=(0, -0.72), scale=0.03, fg=GREEN, parent=f, mayChange=True)
        self.update_parts()

    def update_parts(self):
        solar = getattr(G, "SOLAR", None)
        if solar:  # (Mission 2 uses the part Mission 1 unlocks)
            fitted = G.has_part(PROGRESS, solar["id"])
            self.t_parts.setText(f"{solar['name']} fitted (from Mission 1): 1 energy back for every 5 squares you drive."
                                 if fitted else f"No {solar['name']} yet: finish Mission 1 to fit one. Mission 2 can be "
                                 "done without it.")
            self.t_parts.setFg(GREEN if fitted else GREY)
            return
        unlocked = G.has_part(PROGRESS, G.UNLOCK["id"])
        self.t_parts.setText(f"{G.UNLOCK['name']} unlocked: it carries over to Mission 2." if unlocked else "")

    def key_choose(self, name):
        if not self.intro.isHidden():
            self.choose(name)

    def choose(self, name):
        self.robot_name = name
        if self.robot is not None:
            for v, _ in self.robot.models.values():
                v.destroy()
        self.robot = RobotModel(self.render, self.designs[name])
        self.intro.hide()
        back = LINK.back if LINK is not None and self.server_runs else None
        if back and back.get("mission") == G.MISSION_ID and back.get("robot") == name and isinstance(back.get("state"), dict):
            LINK.back = None  # (coming back to the class: the mission carries on where the server has it)
            self.reset_mission(send=False)
            self.adopt(back["state"])
            self.log("Back in the class: your mission carries on where it was.", "info")
            return
        self.reset_mission()

    def reset_mission(self, send=True):
        """The mission back to its start: the robot on its square, the battery, the tools on the crate, the rockfall,
        the objectives and the stars. Your code stays in the editor, to fix and run again. Any time after a robot is
        chosen, even while a run is being played (the playing stops) or after the battery went flat. The camera and
        the graphics are not the mission's: they stay as they are. (Before CHANGE 188 only R did this, and R typed
        an r into the code whenever the code panel was open, and did nothing while a run was playing.) In a class
        whose server runs the missions (CHANGE 198) the server's copy starts again too."""
        if self.robot_name is None:
            return
        if send and self.server_runs:
            LINK.send({"type": "start", "mission": G.MISSION_ID, "robot": self.robot_name})
        self.queue, self.event, self.playing, self.run_line = [], None, False, None
        self.waiting = None
        self.bumped = False
        self.snd.stop("tool")
        self.mission = self.new_mission()
        s = self.mission.snapshot()
        self.view = {"x": s["x"], "y": s["y"], "h": heading(s["dir"]), "state": s}
        self.robot.hold(s["tool"])  # (none in Mission 1; Mission 2's robot has the spinner from the start)
        self.valley.reset()
        self.valley.show(s)
        self.banner.hide()
        if self.done is not None:
            self.done.destroy()
            self.done = None
        self.log_lines = []
        if G is mission_wake_up:
            self.log(f"{self.robot_name} wakes up after the crash landing. Battery: {s['energy']} energy. "
                     f"It's facing {G.DIR_NAMES[s['dir']]}.", "info")
        else:
            self.log(f"{self.robot_name} waits at the bottom of the hill road, facing {G.DIR_NAMES[s['dir']]} up it, "
                     f"with {s['energy']} energy and the front spinner." + (" The Solar Panel is fitted." if s.get("solar")
                                                                             else ""), "info")
        self.log(TEXT["first"], "info")
        self.update_hud(s)
        self.refresh_code()

    def adopt(self, s):
        """(CHANGE 198) The mission as the class server has it (this window's copy of it follows the server's): the
        robot, the valley, the HUD and the code panel shown as that state says."""
        if self.mission is None:
            return
        self.mission.s = dict(s)
        s = self.mission.snapshot()
        self.view = {"x": s["x"], "y": s["y"], "h": heading(s["dir"]), "state": s}
        self.robot.hold(s["tool"])
        self.valley.reset()
        self.valley.show(s)
        if s.get("failed"):
            self.banner.show()
        self.update_hud(s)
        self.refresh_code()

    # ---------- the code panel ----------
    def typing(self):
        return self.editor is not None and self.editor.focused

    def key_code(self):
        if self.typing() or not self.intro.isHidden() or self.done is not None:
            return
        self.toggle_panel()

    def key_view(self):
        if not self.typing():
            order = ["valley", "follow", "above"]
            self.cam_mode = order[(order.index(self.cam_mode) + 1) % len(order)]

    def key_restart(self):
        """R: a reset, when the keyboard isn't the editor's (there it is a letter: Ctrl+R works everywhere)."""
        if not self.typing() and self.intro.isHidden():
            self.reset_mission()

    def key_reset(self):
        if self.intro.isHidden():
            self.reset_mission()

    def key_graphics(self):
        if not self.typing():
            self.toggle_options()

    def key_home(self):
        if not self.typing():
            self.home_camera()

    def key_escape(self):
        if self.full.on:
            self.full.leave()
        elif self.options is not None:
            self.close_options()
        elif self.panel is not None:
            self.close_panel()
        elif self.done is not None:
            self.close_done()
        elif not args.selftest:
            self.userExit()

    def wheel(self, factor):
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * factor))

    def pan_by(self, dx, dy):
        """Drag the view dx across and dy up the map (metres), no further than PAN_REACH past the map's edge."""
        self.pan.x = max(-G.W * SQ / 2 - PAN_REACH, min(G.W * SQ / 2 + PAN_REACH, self.pan.x + dx))
        self.pan.y = max(-G.H * SQ / 2 - PAN_REACH, min(G.H * SQ / 2 + PAN_REACH, self.pan.y + dy))

    def home_camera(self):
        """The camera as it started: the whole valley, zoom 1, no pan."""
        self.cam_mode, self.zoom = "valley", 1.0
        self.pan = Vec3(0, 0, 0)

    def mouse_drag(self):
        """The right mouse button held and dragged pans the view over the map (as Robot Lab's camera swings)."""
        mw = self.mouseWatcherNode
        if mw is None or not mw.hasMouse() or not mw.isButtonDown(MouseButton.three()):
            self.drag_from = None
            return
        x, y = mw.getMouseX(), mw.getMouseY()
        if self.drag_from is not None:  # (the map follows the mouse: a drag to the right shows what is left of it)
            reach = 16.0 * self.zoom  # metres the map moves for the mouse crossing half the window
            self.pan_by(-(x - self.drag_from[0]) * reach * self.a, -(y - self.drag_from[1]) * reach)
        self.drag_from = (x, y)

    # ---------- graphics: the Look, the engine's seven tiers, the line colour (CHANGE 188) ----------
    def next_tier(self):
        """The tier the next start draws from the panel's choice alone (--gfx is dropped when the window reopens)."""
        return choose_tier(None)

    def apply_gfx(self):
        """Draw as self.gfx says, now. Look: Panda's wireframe draws every triangle's edges in its shaded colour, on
        any tier (the mesh and lines tiers are a look of their own and stay as they are). Tier: the shaders are made
        as the window opens, so a chosen tier is drawn by reopening the window (set_gfx); here the knobs that change
        safely in a run (the shadow map and the smoothing, as the engine's Monitor turns them) go to the chosen
        tier's as far as this run's tier has them, so a window that can't reopen (offscreen, the tests) still
        shows the change; Auto keeps this run's own."""
        if not rw_gfx.look():
            if self.gfx["look"] == "wireframe":
                self.render.setRenderModeWireframe(1)
            else:
                self.render.clearRenderMode()
        want = gfx_tiers.SETTINGS[self.gfx.get("tier") or self.tier]
        sun, pipe = rw_gfx.sun(), rw_gfx.pipeline()
        if sun is not None and self.shadow0:
            size = min(want["shadow"], self.shadow0)
            if size:
                sun.node().setShadowCaster(True, size, size)
            else:
                sun.node().setShadowCaster(False)
        if pipe is not None:
            pipe.msaa_samples = min(want["pbr"].get("msaa_samples", 0), self.msaa0)

    def set_gfx(self, key, value):
        """A Graphics panel button: kept in settings.json for the next start, and drawn now as far as a run can.
        The Look and the line colour change at once. A tier (value None: Auto) reopens the window at it when it
        isn't the one drawn, a few seconds, the robot, the code and the view kept (as Robot Lab's Settings tab does:
        the shaders and the window's multisampling are made as a window opens); a window that can't reopen turns
        the knobs it can and draws the tier from the next start."""
        if value is None:
            self.gfx.pop(key, None)
        else:
            self.gfx[key] = value
        gfx_tiers.remember(MISSION_SETTINGS_DIR, **{GFX_KEY: dict(self.gfx)})
        if key == "line_colour":
            rw_gfx.set_line_colour(value)
        if key == "tier" and self.next_tier() != self.tier and self.reopen():
            return
        self.apply_gfx()
        if self.options is not None:
            self.open_options()

    def reopen(self):
        """Open this window again at the tier chosen, carrying the robot, the code and the view over in REOPEN_ENV,
        and close this one (lab_client.restart_window's way). False when it can't: an offscreen window or the
        selftest (nothing to reopen into), or the new window wouldn't start."""
        if args.offscreen or args.selftest:
            return False
        state = {"robot": self.robot_name, "code": list(self.code_state["lines"]), "cam_mode": self.cam_mode,
                 "zoom": self.zoom, "options": self.options is not None, "mission": G.MISSION_ID}
        env = dict(os.environ, **{REOPEN_ENV: json.dumps(state)})
        argv = []
        for a in sys.argv[1:]:  # (--gfx was by hand; the panel's choice comes first now)
            if argv and argv[-1] == "--gfx":
                argv.pop()
            elif not a.startswith("--gfx="):
                argv.append(a)
        # (the new process, window.log, the Club Coders app told the new process id: engine.reopen, shared by every
        # game's window since CHANGE 189; in the app the exe runs this window again by REOPEN_ENV, club_coders.GAMES)
        try:
            reopen.start(__file__, argv, env, frozen=lab_version.FROZEN,
                         log_dir=SETTINGS_DIR if lab_version.FROZEN else HERE)
        except OSError as e:
            print(f"wake_up_call: couldn't reopen the window at the {self.next_tier()} tier: {e}", flush=True)
            return False
        os._exit(0)

    def resume_reopened(self):
        """A window reopened by the Graphics panel: the robot, the code and the view as they were, the panel open
        again so the new tier's name is in view. Nothing without REOPEN_ENV; anything odd in it is left out."""
        raw = os.environ.pop(REOPEN_ENV, None)
        if not raw:
            return
        try:
            state = json.loads(raw)
        except ValueError:
            return
        if not isinstance(state, dict):
            return
        if state.get("mission") in MISSIONS:
            self.choose_mission(state["mission"])
        code = state.get("code")
        if isinstance(code, list) and code and all(isinstance(line, str) for line in code):
            self.code_state["lines"][:] = code
            self.code_state["cursor"] = [len(code) - 1, 0]
            self.code_state["scroll"] = 0
        if self.robot_name is None and state.get("robot") in self.designs:
            self.choose(state["robot"])
        elif self.robot_name is not None:
            self.refresh_code()
        if state.get("cam_mode") in ("valley", "follow", "above"):
            self.cam_mode = state["cam_mode"]
        if isinstance(state.get("zoom"), (int, float)):
            self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, float(state["zoom"])))
        self.place_camera(1.0)
        if state.get("options"):
            self.open_options()

    def gfx_note(self):
        """What is drawn now and what the choice does from here: at once, by reopening, or at the next start."""
        chosen = self.gfx.get("tier")
        drawn = self.tier
        text = f"Drawing {drawn.title()} now"
        if rw_gfx.look():
            text += f" (the Club Coders {rw_gfx.look()} look)"
        elif self.gfx["look"] == "wireframe":
            text += " as a wireframe (every triangle's edges)"
        if args.gfx in gfx_tiers.TIERS:
            text += ", chosen by hand (--gfx)"
        text += ". "
        if chosen is None:
            text += "Auto: this computer's own solid tier, never Robot Lab's Mesh or Lines unless chosen here. "
        elif self.next_tier() != chosen:  # (the teacher's class maximum, from Robot Lab's settings)
            text += f"{chosen.title()} is kept, but the teacher's class maximum holds it at {self.next_tier().title()}. "
        elif self.next_tier() != drawn:
            text += f"{self.next_tier().title()} is kept: this window couldn't reopen, so it is drawn from the next start. "
        text += ("A tier chosen here reopens the window at it (a few seconds) with your robot and code kept. Mesh: "
                 "every triangle's edges. Lines: outlines and a grid, in one colour. Ultra: for a gaming PC.")
        return text

    def toggle_options(self):
        self.close_options() if self.options is not None else self.open_options()

    def close_options(self):
        if self.options is not None:
            self.options.destroy()
            self.options = None

    def open_options(self):
        """The Graphics panel under the HUD: Look (Solid or Wireframe), Quality (Auto and the engine's seven tiers,
        four to a line as Robot Lab's Settings tab lays them), the line colour for mesh and lines (when one is drawn
        or chosen), what they do, CLOSE."""
        self.close_options()
        f = self.options = DirectFrame(parent=self.a2dTopLeft, frameColor=PANEL)
        OnscreenText("GRAPHICS", pos=(0.06, -0.87), scale=0.03, fg=YELLOW, align=TextNode.ALeft, parent=f)
        self.option_buttons = {}
        on, off = (0.2, 0.55, 0.65, 1), (0.12, 0.15, 0.22, 1)
        rows = [("Look", "look", [("solid", "SOLID"), ("wireframe", "WIREFRAME")], 0.3, 2),
                ("Quality", "tier", [(t, (t or "auto").upper()) for t in TIER_CHOICES], 0.15, 4)]
        if rw_gfx.look() or self.gfx.get("tier") in gfx_tiers.LOOKS:
            rows.append(("Line colour", "line_colour", list(rw_gfx.LINE_COLOURS), 0.13, 5))
        y = -0.95
        for label, key, choices, step, per_row in rows:
            OnscreenText(label, pos=(0.06, y - 0.01), scale=0.028, fg=WHITE, align=TextNode.ALeft, parent=f)
            if key == "line_colour":  # (name, "#rrggbb") as the engine lists them: the value is the colour
                choices = [(colour, name) for name, colour in choices]
                chosen = (self.gfx.get("line_colour") or (hud.SETTINGS.get("line_colour") or "").lower()
                          or rw_gfx.LINE_COLOURS[0][1])
            else:
                chosen = self.gfx.get(key)
            for i, (value, text) in enumerate(choices):
                b = DirectButton(parent=f, text=text, scale=0.026 if per_row > 2 else 0.028,
                                 pos=(0.3 + (i % per_row) * step, 0, y - (i // per_row) * 0.05), relief=DGG.FLAT,
                                 pad=(0.5, 0.3), command=self.set_gfx, extraArgs=[key, value], text_fg=(1, 1, 1, 1),
                                 frameColor=on if chosen == value else off)
                if key == "look" and rw_gfx.look():
                    b["state"] = DGG.DISABLED
                self.option_buttons[value if value is not None else "auto"] = b
            y -= 0.05 * ((len(choices) + per_row - 1) // per_row) + 0.03
        OnscreenText(self.gfx_note(), pos=(0.06, y), scale=0.022, fg=GREY, align=TextNode.ALeft, parent=f, wordwrap=38)
        y -= 0.135
        OnscreenText("Kept for next time in settings.json.", pos=(0.06, y), scale=0.022, fg=GREY,
                     align=TextNode.ALeft, parent=f)
        DirectButton(parent=f, text="CLOSE", scale=0.028, pos=(0.82, 0, y + 0.005), command=self.close_options,
                     relief=DGG.FLAT, pad=(0.4, 0.25), frameColor=(0.3, 0.12, 0.12, 1), text_fg=(1, 1, 1, 1))
        f["frameSize"] = (0.03, 0.93, y - 0.04, -0.82)

    def toggle_panel(self):
        self.close_panel() if self.panel is not None else self.open_panel()

    def close_panel(self):
        if self.editor is not None:
            self.editor.destroy()
            self.editor = None
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
        self.camLens.setFilmOffset(0, 0)
        self.t_now.show()
        self.full.button.show()  # (the code panel's title bar had its corner)

    def open_panel(self, tab=None):
        self.close_panel()
        self.full.button.hide()
        self.tab = tab or self.tab
        self.pw = min(1.66, self.a * 0.95)  # the panel's width (the right of the screen)
        pw = self.pw
        fw = self.camLens.getFilmSize()[0]  # (the valley moves into the space left of the panel)
        self.camLens.setFilmOffset(fw * pw / (2 * self.a) / 2, 0)
        self.t_now.hide()  # (no room beside the panel: the objectives list marks what's now)
        p = self.panel = editor.code_window((-pw, -0.02, -1.97, -0.03), (0, 0, 0))
        self.panel.reparentTo(self.a2dTopRight)
        x0 = -pw + 0.03
        editor.title_bar(self, p, x0, -0.075, G.MISSION_ID + (".pseudo" if self.tab == "pseudo" else ".py"),
                         scale=0.026)
        self.tab_buttons = {}
        for i, (key, text) in enumerate((("pseudo", "Pseudo code"), ("code", "Code"))):
            b = DirectButton(parent=p, text=text, scale=0.03, pos=(-pw + 0.72 + i * 0.3, 0, -0.085),
                             command=self.open_panel, extraArgs=[key], relief=DGG.FLAT, pad=(0.4, 0.25),
                             frameColor=(0.2, 0.55, 0.65, 1) if key == self.tab else (0.12, 0.15, 0.22, 1),
                             text_fg=(1, 1, 1, 1))
            self.tab_buttons[key] = b
        DirectButton(parent=p, text="X", scale=0.034, pos=(-0.07, 0, -0.087), command=self.close_panel, relief=DGG.FLAT,
                     pad=(0.35, 0.2), frameColor=(0.3, 0.12, 0.12, 1), text_fg=(1, 1, 1, 1))
        if self.tab == "code":
            self.build_code_tab(p, x0)
        else:
            self.build_pseudo_tab(p, x0)
        self.refresh_code()

    def build_pseudo_tab(self, p, x0):
        pw, scale = self.pw, 0.026
        dim = editor.DIM
        OnscreenText("PSEUDO CODE: type one instruction per line", pos=(x0, -0.16), scale=0.024, fg=dim,
                     align=TextNode.ALeft, parent=p)
        ew = pw * 0.47
        self.py_x = x0 + ew + 0.04
        OnscreenText("THE SAME AS PYTHON", pos=(self.py_x, -0.16), scale=0.024, fg=dim, align=TextNode.ALeft, parent=p)
        self.editor = PseudoEditor(self, p, self.code_state, x0, -0.18, ew, 15, scale=scale, on_change=self.typed)
        self.editor.on_scroll = self.draw_python
        font = editor.code_font(self)
        extra = {"font": font} if font is not None else {}
        self.run_back = DirectFrame(parent=p, frameColor=(1, 0.85, 0.2, 0.22),
                                    frameSize=(0, -0.04 - self.py_x, -scale * 0.35, scale * 1.05))
        self.run_back.hide()
        self.py_rows = [OnscreenText("", pos=(self.py_x, self.editor.row_y(i)), scale=scale, fg=(1, 1, 1, 1),
                                     align=TextNode.ALeft, parent=p, mayChange=True, **extra) for i in range(15)]
        self.t_problems = [OnscreenText("", pos=(x0, -0.95 - i * 0.042), scale=0.026, fg=RED, align=TextNode.ALeft,
                                        parent=p, mayChange=True, wordwrap=(pw - 0.08) / 0.026) for i in range(4)]
        self.run_button = DirectButton(parent=p, text="RUN", scale=0.042, pos=(x0 + 0.1, 0, -1.15), command=self.run_code,
                                       relief=DGG.FLAT, pad=(0.5, 0.2), frameColor=(0.2, 0.6, 0.3, 1), text_fg=(1, 1, 1, 1))
        self.t_runinfo = OnscreenText("", pos=(x0 + 0.24, -1.155), scale=0.028, fg=dim, align=TextNode.ALeft, parent=p,
                                      mayChange=True)
        self.panel_reset = DirectButton(parent=p, text="RESET", scale=0.034, pos=(-0.19, 0, -1.152), command=self.reset_mission,
                                        relief=DGG.FLAT, pad=(0.5, 0.25), frameColor=(0.75, 0.5, 0.1, 1), text_fg=(0, 0, 0, 1))
        self.build_phrasebook(p, x0, -1.23)
        self.editor.focus()

    def build_phrasebook(self, p, x0, top):
        """The phrasebook, for reference only: words, no buttons (nothing is inserted for the learner)."""
        d = self.C.dict
        pw = self.pw
        book = self.phrasebook = p.attachNewNode("phrasebook")
        DirectFrame(parent=book, frameColor=(1, 1, 1, 0.04), frameSize=(x0 - 0.01, -0.04, -1.95, top + 0.02))
        OnscreenText("PHRASEBOOK  (for reference: type the instructions yourself)", pos=(x0, top - 0.035),
                     scale=0.026, fg=YELLOW, align=TextNode.ALeft, parent=book)
        font = editor.code_font(self)
        extra = {"font": font} if font is not None else {}
        colw = (pw - 0.1) / 2
        shown_patterns = [pat for pat in d["patterns"] if not pat.get("alias")]  # (the Python ways: in a note below)
        rows = (len(shown_patterns) + 1) // 2
        step = 0.088 if rows <= 4 else 0.064  # (Mission 2's fifteen: closer, their meanings on one line)
        for i, pat in enumerate(shown_patterns):
            x = x0 + (i % 2) * colw
            y = top - 0.085 - (i // 2) * step
            OnscreenText(pat["say"], pos=(x, y), scale=0.026 if rows <= 4 else 0.024, fg=editor.COLOURS["function"],
                         align=TextNode.ALeft, parent=book, **extra)
            meaning = pat["meaning"] if rows <= 4 else textwrap.shorten(pat["meaning"], int(colw / 0.0105), placeholder="...")
            OnscreenText(meaning, pos=(x, y - (0.035 if rows <= 4 else 0.027)), scale=0.02 if rows <= 4 else 0.018, fg=GREY, align=TextNode.ALeft,
                         parent=book, wordwrap=colw / 0.02 - 1)
        y = top - 0.085 - rows * step - 0.005 + (0 if rows <= 4 else 0.02)
        if rows > 4:  # (Mission 2: the Python way of writing the new lines works too)
            py = "   ".join(pat["example"] for pat in d["patterns"] if pat.get("alias"))
            OnscreenText("The Python way works too:  " + py + "   if robot.energy < 5:   print(lamps)", pos=(x0, y),
                         scale=0.019, fg=editor.COLOURS["function"], align=TextNode.ALeft, parent=book,
                         wordwrap=(pw - 0.08) / 0.019, **extra)
            y -= 0.035
        values = "   ".join(f"[{k}] {s['describe']}" for k, s in d["slots"].items()
                            if any(f"[{k}]" in pat["say"] for pat in shown_patterns))
        OnscreenText("Values:  " + values, pos=(x0, y), scale=0.02 if rows <= 4 else 0.018, fg=WHITE,
                     align=TextNode.ALeft, parent=book, wordwrap=(pw - 0.08) / (0.02 if rows <= 4 else 0.018))
        if rows > 4:
            return  # (no room for the word lists: the did-you-mean hints name the right words)
        others = ", ".join(f"{k} = {v}" for k, v in d["synonyms"].items() if k != v)
        OnscreenText("Other words it knows:  " + others, pos=(x0, y - 0.07), scale=0.019, fg=GREY, align=TextNode.ALeft,
                     parent=book, wordwrap=(pw - 0.08) / 0.019)
        OnscreenText("Ignored: capitals, punctuation and the filler words (" + ", ".join(d["fillers"]) + "). Number words "
                     "(one to twenty) count as numbers. A line starting with # is a note.", pos=(x0, y - 0.16),
                     scale=0.019, fg=GREY, align=TextNode.ALeft, parent=book, wordwrap=(pw - 0.08) / 0.019)

    def build_code_tab(self, p, x0):
        OnscreenText("YOUR PROGRAM AS PYTHON (read only: change it in the Pseudo code tab)", pos=(x0, -0.16),
                     scale=0.024, fg=editor.DIM, align=TextNode.ALeft, parent=p)
        self.code_view_state = {"lines": [""], "cursor": [0, 0], "scroll": 0}
        self.code_view = editor.CodeEditor(self, p, self.code_view_state, x0, -0.18, self.pw - 0.08, 36, scale=0.026,
                                           read_only=True)

    def typed(self):
        """The text changed: read it again when the typing pauses (a line it can't read can take a moment to
        diagnose, and every key would otherwise wait for it)."""
        self.read_at = self.now + 0.12  # (update reads it then; self.now is the frame's clock, fixed for a picture)
        self.run_button["state"] = DGG.DISABLED  # (until it has been read)

    def refresh_code(self):
        self.read_at = None
        self.parsed = P.parse_program("\n".join(self.code_state["lines"]), self.C)
        if self.panel is None:
            return
        if self.tab == "code":
            text = (f"from clubcoders import robot  # Robot Lab Mission {STORY['number']}: {STORY['title']}\n\n"
                    + self.parsed["python"].rstrip("\n"))
            self.code_view_state["lines"][:] = text.split("\n")
            self.code_view.refresh()
            return
        self.draw_python()
        errors = self.parsed["errors"]
        rows = []
        for r in errors:
            rows.append((f"Line {r['n']}: {r['message']}" + (f"  {r['after']}" if r.get("after") else ""), RED))
            if r.get("hint"):
                rows.append((f"      Did you mean: {r['hint']}?", YELLOW))
        if not errors and self.parsed["code_lines"]:
            n = self.parsed["code_lines"]
            rows.append((f"All {n} line{'' if n == 1 else 's'} understood.", GREEN))
        if len(rows) > len(self.t_problems):
            more = len(errors) - sum(1 for _, c in rows[:len(self.t_problems) - 1] if c == RED)
            rows = rows[:len(self.t_problems) - 1] + [(f"... and {more} more", RED)]
        for i, t in enumerate(self.t_problems):
            text, colour = rows[i] if i < len(rows) else ("", RED)
            t.setText(text)
            t.setFg(colour)
        n = self.parsed["code_lines"]
        self.t_runinfo.setText("Fix the lines above to run." if errors else
                               f"{n} line{'' if n == 1 else 's'} of code   (Ctrl+Enter runs)")
        ok = self.can_run()
        self.run_button["state"] = DGG.NORMAL if ok else DGG.DISABLED
        self.run_button["frameColor"] = (0.2, 0.6, 0.3, 1) if ok else (0.22, 0.25, 0.3, 1)

    def draw_python(self):
        """The Python beside each line of pseudo code, scrolled with it."""
        if self.editor is None or self.parsed is None:
            return
        first = self.code_state["scroll"]
        rows = self.parsed["rows"]
        self.run_back.hide()
        for i, t in enumerate(self.py_rows):
            n = first + i
            if n < len(rows):
                r = rows[n]
                text = r["python_line"]
                t.setText(text if r["kind"] == "error" else editor.coloured(text))
                t.setFg(RED if r["kind"] == "error" else (1, 1, 1, 1))
                if self.run_line == r["n"]:
                    self.run_back.setPos(self.py_x - 0.01, 0, self.editor.row_y(i))
                    self.run_back.show()
            else:
                t.setText("")

    def can_run(self):
        m = self.mission
        return (not self.playing and self.parsed is not None and bool(self.parsed["program"]) and m is not None
                and not m.s["complete"] and not m.s["failed"])

    def run_code(self):
        self.parsed = P.parse_program("\n".join(self.code_state["lines"]), self.C)
        if not self.can_run():
            self.refresh_code()
            return
        if self.server_runs:  # (CHANGE 198: the class server runs it; its events come back to read_link's "ran")
            LINK.send({"type": "program", "mission": G.MISSION_ID, "text": "\n".join(self.code_state["lines"])})
            self.waiting = time.perf_counter()
            self.playing = True
            self.refresh_code()
            return
        self.play_result(self.mission.run(self.parsed["program"], self.parsed["code_lines"]))

    def play_result(self, result):
        """A run's events played: here, by the window's own Python, or as the class server sent them (CHANGE 198)."""
        n = self.parsed["code_lines"] if self.parsed else 0
        self.log(f"Run {self.mission.s['runs']}: {n} line{'' if n == 1 else 's'}.", "info")
        self.queue = list(result["events"])
        self.result = result
        self.playing = True
        self.refresh_code()
        if self.speed == 0:
            while self.queue:
                self.next_event()
                self.end_event()
            self.finish()

    # ---------- playing a run ----------
    def next_event(self):
        ev = self.event = self.queue.pop(0)
        self.event_t = 0.0
        self.event_from = (self.view["x"], self.view["y"], self.view["h"])
        to_h = heading(ev["state"]["dir"])
        dh = (to_h - self.view["h"] + 180) % 360 - 180  # (the short way round)
        self.event_to = (ev["state"]["x"], ev["state"]["y"], self.view["h"] + dh)
        if ev.get("msg"):
            self.log(ev["msg"], ev.get("tone"))
        self.run_line = ev["line"]
        self.draw_python()
        before = self.view["state"]
        s = ev["state"]
        if ev["type"] == "night":  # (Mission 2: the robot back at the bottom of the road at once, not driven there)
            self.event_from = self.event_to = (s["x"], s["y"], to_h)
            self.view.update(x=s["x"], y=s["y"], h=to_h, state=s)
            self.valley.reset()
            self.valley.show(s)
            self.update_hud(s)
            before = s
        if s["tool"] != before["tool"]:
            self.robot.hold(s["tool"])
            self.valley.show(dict(before, tool=s["tool"]))
            self.snd.play("clang", 0.5)
        if ev["type"] == "bump":
            self.snd.hit("bump", 0.7)
        elif ev["type"] == "use":
            self.snd.play({"flipper": "pneumatic", "hammer": "swing"}.get(s["tool"], "saw"), 0.7)
        elif ev["type"] == "objective" and s.get("cellTaken") and not before.get("cellTaken"):
            self.snd.play("beep", 0.6)
        elif ev["type"] == "complete":
            self.snd.play("horn", 0.6)
        elif ev["type"] == "flat":
            self.snd.play("beep", 0.4, 0.6)
        elif ev["type"] == "repair":
            self.snd.play("clang", 0.5)
        elif ev["type"] in ("report", "solar"):
            self.snd.play("beep", 0.5 if ev["type"] == "report" else 0.3, 1.0 if ev.get("tone") == "ok" else 0.6)

    def end_event(self):
        ev = self.event
        before, s = self.view["state"], ev["state"]
        self.view.update(x=self.event_to[0], y=self.event_to[1], h=self.event_to[2], state=s)
        self.valley.landed(ev, before, self.fx)
        self.valley.show(s)
        self.update_hud(s)
        self.event = None

    def finish(self):
        self.playing = False
        self.run_line = None
        result = self.result
        s = self.mission.snapshot()
        self.view.update(x=s["x"], y=s["y"], state=s)
        self.valley.show(s)
        self.update_hud(s)
        self.refresh_code()
        if result["status"] == "complete":
            G.record_finish(PROGRESS, self.mission, self.robot_name)
            self.update_parts()
            self.close_panel()
            self.show_done()
        elif result["status"] == "flat":
            if self.mission.s["failed"]:
                self.banner.show()
        elif result["status"] == "stopped":
            self.log(TEXT["stopped"], "info")
        else:
            o = next((o for o in self.mission.objectives() if o["now"]), None)
            if o:
                self.log(f"Next: {o['title']}. {o['text']}", "info")
        if not self.server_runs:  # (CHANGE 198: a server that ran it has marked the objectives itself)
            self.report_run(result)

    # ---------- a class whose server runs the missions (CHANGE 198) ----------
    def server_ran(self, m):
        """The class server's answer to a run: its events played as this window's own would be."""
        if self.waiting is None or m.get("mission") != G.MISSION_ID:
            return
        self.waiting = None
        status = m.get("status")
        if status not in ("done", "complete", "flat", "stopped"):
            self.playing = False
            self.log({"error": "The class server couldn't read a line of that program.",
                      "too soon": "Wait a moment, then run again."}.get(status, f"The class server: {status}."), "bad")
            if status == "no mission":  # (the server has restarted: the mission starts again there and here)
                self.reset_mission()
            self.refresh_code()
            return
        events = unpack_events(m.get("before") or self.mission.snapshot(), m.get("events") or [])
        if isinstance(m.get("state"), dict):
            self.mission.s = dict(m["state"])
        self.play_result({"status": status, "events": events})

    def run_here_instead(self, why):
        """No answer from the class server: the run (and the rest of the mission) played by this window itself, as
        when playing alone, each run reported as before CHANGE 198."""
        self.log(f"{why} Your mission carries on on this computer.", "warn")
        self.server_runs, self.waiting, self.playing = False, None, False
        self.run_code()

    def world_robot(self, m):
        name = str(m.get("name", ""))[:20]
        if not name or name == LINK.name:
            return
        if m.get("gone"):
            g = self.ghosts.pop(name, None)
            if g is not None:
                g.destroy()
            return
        mid, robot = m.get("mission"), m.get("robot")
        if mid not in MISSIONS or robot not in ("TITAN", "RAZORBACK"):
            return
        g = self.ghosts.get(name)
        if g is None or g.robot_name != robot or g.mission != mid:
            if g is not None:
                g.destroy()
            g = self.ghosts[name] = Ghost(self, name, robot, mid)
        g.take(m.get("steps") or [])
        g.show(mid == G.MISSION_ID)

    def update_ghosts(self, dt):
        for g in self.ghosts.values():
            g.show(g.mission == G.MISSION_ID)
            if g.mission == G.MISSION_ID:
                g.update(dt)

    def show_done(self):
        st = self.mission.stars()
        s = self.mission.s
        f = self.done = DirectFrame(parent=self.aspect2d, frameColor=(0.02, 0.03, 0.05, 0.93), frameSize=(-0.95, 0.95, -0.62, 0.62))
        OnscreenText("MISSION COMPLETE", pos=(0, 0.48), scale=0.08, fg=YELLOW, parent=f)
        for i, on in enumerate((True, st["energy"], st["lines"])):
            star(f, -0.17 + i * 0.17, 0.33, 0.07, GOLD if on else DIM_STAR)
        if "nightEnergy" in s:  # (Mission 2: the energy left at the end of each night, the program's lines)
            left = ", ".join(str(e) for e in s["nightEnergy"])
            energy = (f"Energy left each night: {left}  ({'a star' if st['energy'] else 'no star'}: "
                      f"{G.RULES['stars']['energy']} or more every night earns one)")
            lines_text = (f"Lines of code: {s['linesUsed']}  ({'a star' if st['lines'] else 'no star'}: "
                          f"{G.RULES['stars']['lines']} or fewer earns one; if and repeat save lines)")
        else:
            energy = (f"Energy left: {s['energy']}  ({'a star' if st['energy'] else 'no star'}: "
                      f"{G.RULES['stars']['energy']} or more earns one)")
            lines_text = (f"Lines of code run: {s['linesUsed']}  ({'a star' if st['lines'] else 'no star'}: "
                          f"{G.RULES['stars']['lines']} or fewer earns one; repeat saves lines)")
        lines = [(TEXT["done"], WHITE), (energy, GREEN if st["energy"] else GREY),
                 (lines_text, GREEN if st["lines"] else GREY)]
        for i, (text, colour) in enumerate(lines):
            OnscreenText(text, pos=(0, 0.17 - i * 0.06), scale=0.034, fg=colour, parent=f)
        DirectFrame(parent=f, frameColor=(0.16, 0.24, 0.45, 1), frameSize=(-0.8, -0.62, -0.26, -0.1))
        for k in range(1, 4):
            DirectFrame(parent=f, frameColor=(0.55, 0.7, 1, 1), frameSize=(-0.8 + k * 0.045, -0.8 + k * 0.045 + 0.004, -0.26, -0.1))
        if G.UNLOCK:
            OnscreenText(f"Unlocked: {G.UNLOCK['name']}", pos=(-0.56, -0.13), scale=0.04, fg=GREEN, align=TextNode.ALeft,
                         parent=f)
            OnscreenText(G.UNLOCK["text"] + "\nSaved on this computer for Mission 2.", pos=(-0.56, -0.18), scale=0.028,
                         fg=GREY, align=TextNode.ALeft, parent=f, wordwrap=46)
        else:  # (Mission 2: the part it used, and what comes next)
            OnscreenText(f"{G.SOLAR['name']}: {'fitted, from Mission 1' if s['solar'] else 'not fitted'}",
                         pos=(-0.56, -0.13), scale=0.04, fg=GREEN if s["solar"] else GREY, align=TextNode.ALeft, parent=f)
            OnscreenText("Your stars are saved on this computer. Mission 3, Supply Run (while loops), comes next.",
                         pos=(-0.56, -0.18), scale=0.028, fg=GREY, align=TextNode.ALeft, parent=f, wordwrap=46)
        DirectButton(parent=f, text="PLAY AGAIN", scale=0.042, pos=(-0.3, 0, -0.5), command=self.play_again,
                     relief=DGG.FLAT, pad=(0.4, 0.2), frameColor=(0.2, 0.55, 0.65, 1), text_fg=(1, 1, 1, 1))
        DirectButton(parent=f, text="CLOSE", scale=0.042, pos=(0.3, 0, -0.5), command=self.close_done,
                     relief=DGG.FLAT, pad=(0.4, 0.2), frameColor=(0.15, 0.18, 0.25, 1), text_fg=(1, 1, 1, 1))
        self.done_stars = st["count"]

    def close_done(self):
        if self.done is not None:
            self.done.destroy()
            self.done = None

    def play_again(self):
        self.close_done()
        self.intro.show()

    # ---------- every frame ----------
    def read_link(self):
        """(CHANGE 195) The class server's messages: the lesson's mission (the teacher changed it), the class's
        progress (the teacher's window), a notice, the connection lost."""
        for m in LINK.messages():
            kind = m.get("type")
            if kind == "lesson":
                mid = LINK.take_lesson(m.get("lesson"))
                if mid and mid != G.MISSION_ID and not self.playing:
                    self.choose_mission(mid)
                    self.log(f"Your teacher chose {STORY['title']}.", "info")
            elif kind == "class" and LINK.role == "teacher":
                lines = [f"CLASS: lesson {m.get('lesson', '')}, {len(m.get('learners') or [])} here"]
                for L in (m.get("learners") or [])[:12]:
                    last = L.get("last") or {}
                    words = (f"{last.get('objectives', 0)}/{last.get('of', 0)} steps" if last else "not run yet")
                    if last.get("complete"):
                        words = f"done, {last.get('stars', 0)} star{'s' if last.get('stars') != 1 else ''}"
                    lines.append(f"{L['name']}: M{1 if L.get('mission') == 'wake_up_call' else 2}  {L.get('runs', 0)} runs  "
                                 f"{words}  [{' '.join(L.get('done') or []) or '-'}]")
                self.t_class.setText("\n".join(lines))
            elif kind == "ran":
                self.server_ran(m)
            elif kind == "state":  # (the mission started on the server: this window's copy takes the server's state)
                if (m.get("mission") == G.MISSION_ID and m.get("robot") == self.robot_name and not self.playing
                        and isinstance(m.get("state"), dict) and not m.get("back")):
                    self.adopt(m["state"])
            elif kind == "world":
                for r in m.get("robots") or []:
                    if isinstance(r, dict) and isinstance(r.get("at"), list) and len(r["at"]) == 4:
                        self.world_robot({"name": r.get("name"), "mission": r.get("mission"), "robot": r.get("robot"),
                                          "steps": [["place"] + r["at"]]})
            elif kind == "robot":
                self.world_robot(m)
            elif kind == "notice":
                self.log(str(m.get("text", ""))[:120], "info")
            elif kind == "welcome":  # (back after a dropped connection)
                self.log("Back in the class.", "info")
            elif kind == "closed":
                reason = m.get("reason") or "the connection closed"
                self.log(f"The class server: {reason}. Your runs carry on; the class won't see them.", "warn")
                for g in self.ghosts.values():
                    g.destroy()
                self.ghosts = {}
                if self.waiting is not None:
                    self.server_runs = False
                    self.waiting, self.playing = None, False
                    self.run_code()
                self.server_runs = False
                if m.get("code") == 4009:  # (the session ended, or the teacher took you out: the window closes)
                    self.taskMgr.doMethodLater(5, lambda t: self.userExit(), "session over")

    def report_run(self, result):
        """(CHANGE 195) A run's result to the class server: the mission's objectives, whether it finished, the
        stars; after a finish, the progress file too (the server keeps it for the learner)."""
        if LINK is None or LINK.net is None or self.mission is None:
            return
        s = self.mission.s
        st = self.mission.stars()
        LINK.send({"type": "run", "mission": G.MISSION_ID, "status": result.get("status", ""),
                   "objectives": [bool(o["done"]) for o in self.mission.objectives()], "complete": bool(s.get("complete")),
                   "stars": st, "energy_left": s.get("energy"), "lines_used": s.get("linesUsed"),
                   "robot": self.robot_name or ""})
        if s.get("complete"):
            LINK.send({"type": "progress", "progress": G.load_progress(PROGRESS)})

    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        if LINK is not None:
            self.read_link()
        if FIXED_STEP:  # (a sixtieth a frame: the power cell's bob, the lamp's blink and the camera the same every run)
            self.frames += 1
            dt = 1 / 60
            now = self.start + self.frames * dt
        self.now = now
        use, speed, nudge = 0.0, 0.0, 0.0
        if self.read_at is not None and now >= self.read_at:  # (the typing has paused: read the code)
            self.refresh_code()
        if self.waiting is not None and time.perf_counter() - self.waiting > SERVER_WAIT:
            self.run_here_instead("The class server didn't answer.")
        if self.playing and self.speed > 0 and self.waiting is None:
            if self.event is None:
                if self.queue:
                    self.next_event()
                else:
                    self.finish()
            if self.event is not None:
                ev = self.event
                dur = DURATION.get(ev["type"], 0.45) * self.speed
                self.event_t += dt
                k = min(1.0, self.event_t / dur) if dur > 0 else 1.0
                e = 2 * k * k if k < 0.5 else 1 - (-2 * k + 2) ** 2 / 2
                (x0, y0, h0), (x1, y1, h1) = self.event_from, self.event_to
                self.view.update(x=x0 + (x1 - x0) * e, y=y0 + (y1 - y0) * e, h=h0 + (h1 - h0) * e)
                if ev["type"] == "move":  # (the wheels turn as it goes: backwards for move back)
                    speed = SQ / max(0.05, dur) * math.sin(math.pi * k) * 1.6
                    if self.is_backwards(x0, y0, x1, y1, h1):
                        speed = -speed
                elif ev["type"] == "bump":
                    nudge = 0.3 * math.sin(math.pi * k)
                    if k > 0.45 and not getattr(self, "bumped", False):
                        self.bumped = True
                        p = world(self.view["x"], self.view["y"])
                        self.fx.impact(tuple(self.robot.front(p, self.view["h"])), 12, "bump", (0.6, 0.6, 0.6))
                elif ev["type"] == "use":
                    use = k
                self.valley.animate(ev, self.view["state"], k, self)  # (the rocks flying apart, the cell lifted...)
                if k >= 1.0:
                    self.bumped = False
                    self.valley.settle(ev)
                    self.end_event()
        if self.robot is not None and self.view is not None:
            self.robot.place(world(self.view["x"], self.view["y"]), self.view["h"], dt, speed, use, nudge)
            if self.robot.tool in ("spinner", "drum") and use > 0:
                self.snd.spinner("tool", 1400 * math.sin(math.pi * use), 0.6, "drum" if self.robot.tool == "drum" else "spinner")
            else:
                self.snd.stop("tool")
            self.snd.loop("motor", "motor", 0.05 + min(0.3, abs(speed) / 20), 0.6 + abs(speed) / 8)
        self.update_ghosts(dt)
        self.valley.update(dt)
        self.fx.update(dt)
        self.mouse_drag()
        self.place_camera(dt)
        if self.checks is not None:
            try:
                next(self.checks)
            except StopIteration:
                self.checks = None
        elif args.screenshot and not args.selftest and now - self.start > args.after:
            self.save_shot(args.screenshot)
            self.userExit()
        return task.cont

    def is_backwards(self, x0, y0, x1, y1, h):
        q = Quat()
        q.setHpr((h, 0, 0))
        f = q.getForward()
        return (x1 - x0) * f.x * SQ + (y0 - y1) * f.y * SQ < 0

    def place_camera(self, dt):
        if self.view is None:
            target, h = world((G.W - 1) / 2, (G.H - 1) / 2), 0.0
        else:
            target, h = world(self.view["x"], self.view["y"]), self.view["h"]
        middle = world((G.W - 1) / 2, (G.H - 1) / 2 + 0.6)
        if self.cam_mode == "follow":
            q = Quat()
            q.setHpr((h, 0, 0))
            want = target - q.getForward() * 4.5 * self.zoom + Vec3(0, 0, 6 * self.zoom)  # (high: over the roofs)
            look = target + q.getForward() * 2.5
            fov = 60
        elif self.cam_mode == "above":
            want = middle + Vec3(0, -0.01, 30 * self.zoom)
            look = middle
            fov = 62
        else:
            want = middle + Vec3(0, -22 * self.zoom, 23 * self.zoom)
            look = middle + Vec3(0, 1.0, 0)
            fov = 58
        want, look = want + self.pan, look + self.pan  # (the right mouse button's drag)
        if self.cam_pos is None or dt >= 1.0:
            self.cam_pos, self.cam_look = Point3(want), Point3(look)
        else:
            k = min(1.0, dt * 4)
            self.cam_pos += (want - self.cam_pos) * k
            self.cam_look += (look - self.cam_look) * k
        self.camLens.setFov(fov)
        self.camera.setPos(self.cam_pos + Vec3(*self.fx.shake_offset()))
        self.camera.lookAt(self.cam_look)

    def save_shot(self, path):
        self.graphicsEngine.renderFrame()
        self.graphicsEngine.renderFrame()
        self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(path)))

    def view_check(self, edges=True):
        """Is the whole map in the picture, and lit, as the camera is now? The map's corners (edges: its outer edges,
        on the ground and 3 m up, the sign's height; else the corner squares' middles on the ground) projected
        through the lens, against the far clip and the fog (the mesh and lines look's fade: a point past its onset
        starts to go dark). Returns what it measured; the selftest checks it."""
        if edges:
            corners = [world(x, y, z) for x in (-0.5, G.W - 0.5) for y in (-0.5, G.H - 0.5) for z in (0.0, 3.0)]
        else:
            corners = [world(x, y) for x in (0, G.W - 1) for y in (0, G.H - 1)]
        inside, furthest = True, 0.0
        for p in corners:
            q = Point2()
            local = self.cam.getRelativePoint(self.render, p)
            inside = inside and self.camLens.project(local, q) and abs(q.x) <= 1 and abs(q.y) <= 1
            furthest = max(furthest, (p - self.camera.getPos()).length())
        fog = self.render.getFog()
        onset = fog.getLinearOnsetPoint().length() if fog is not None else None
        return {"inside": inside, "furthest": round(furthest, 1), "far": self.camLens.getFar(),
                "fog_onset": onset, "zoom": self.zoom, "mode": self.cam_mode,
                "lit": self.camLens.getFar() > furthest and (onset is None or onset > furthest)}

    # ---------- --replay: recorded key presses played into this window (replay_mission.py) ----------
    def replay(self, cases):
        """Each case {"robot", "keys"}: its key presses sent as the window hears them, one step a frame, and its
        result printed as one line, REPLAY {"case": i, "result": [...]}, in the shape replay_mission.py's play()
        gives (a run: {"status", "events"}, or {"error": true} for a program the editor can't read; last
        {"final", "stars", "objectives"}). The steps: ["key", name] (f1, f2, 1, 2, c, escape, control-a,
        control-enter, enter: a key as the window hears it), ["type", text] (into the code editor, letter by letter,
        Return for a new line), ["wait"] (until the run has been played: the run's result is taken here),
        ["frames", n] (n frames drawn), ["shot", name] (a picture, with --screenshot: X_name.png). After the first
        case the next starts as PLAY AGAIN does: the end card and the panel closed, the first screen shown.
        (From jarvis/game-tests 3b3b293, where it plays Mission 1; here a case's keys choose its mission first.)"""
        keep = ("type", "line", "msg", "tone", "state")
        for _ in range(3):
            yield
        for i, case in enumerate(cases):
            if i:
                self.close_done()
                self.close_panel()
                self.intro.show()
                yield
            results, seen, typed = [], 0, ""
            for step in case["keys"]:
                kind = step[0]
                if kind == "key":
                    self.messenger.send(step[1])
                elif kind == "type":
                    typed = step[1]
                    for ch in typed:
                        if ch == "\n":
                            self.messenger.send("enter")
                        else:
                            self.messenger.send("keystroke", [ch])
                elif kind == "wait":
                    while self.playing:
                        yield
                    s = self.mission.s
                    if s["runs"] > seen:  # (the window ran it)
                        seen = s["runs"]
                        results.append({"status": self.result["status"],
                                        "events": [{k: e[k] for k in keep} for e in self.result["events"]]})
                    elif P.parse_program(typed, self.C)["program"] is None:  # (RUN was disabled: a mistake)
                        results.append({"error": True})
                    else:  # (the mission was over: the editor gone or RUN disabled, as the mission's run() says)
                        results.append({"status": "complete" if s["complete"] else "flat", "events": []})
                elif kind == "frames":
                    for _ in range(int(step[1])):
                        yield
                elif kind == "shot":
                    if args.screenshot:
                        self.save_shot(args.screenshot.replace(".png", f"_{step[1]}.png"))
                else:
                    raise ValueError(f"replay: a step I don't know: {step!r}")
                yield
            m = self.mission
            results.append({"final": m.snapshot(), "stars": m.stars(), "objectives": m.objectives()})
            print("REPLAY " + json.dumps({"case": i, "mission": G.MISSION_ID, "robot": self.robot_name,
                                          "result": results}, sort_keys=True), flush=True)
        if self.ghosts:  # (CHANGE 198: the class's other robots, where this window drew them)
            print("REPLAY GHOSTS " + json.dumps({n: [g.mission, g.robot_name, g.where()] for n, g in self.ghosts.items()}),
                  flush=True)
        print(f"REPLAY DONE: {len(cases)} missions played", flush=True)
        os._exit(0)

    # ---------- --selftest: the mission played through by pretend keys and clicks ----------
    @staticmethod
    def pause(seconds):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            yield

    def selftest(self):
        results = []

        def check(name, ok, detail=""):
            results.append((name, bool(ok), detail))

        for _ in range(3):
            yield
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_choose.png"))
        self.messenger.send("1")
        yield
        check("pressing 1 chooses TITAN and starts the mission", self.intro.isHidden() and self.robot_name == "TITAN"
              and self.mission is not None, self.robot_name)
        check("the robot starts on the start square with 8 energy", (self.mission.s["x"], self.mission.s["y"]) == (1, 6)
              and self.mission.s["energy"] == 8, self.mission.s)
        self.messenger.send("c")
        yield
        check("C opens the code panel on the Pseudo code tab", self.panel is not None and self.editor is not None
              and self.tab == "pseudo", self.tab)
        check("the panel has the Pseudo code and Code tabs", [b["text"] for b in self.tab_buttons.values()] ==
              ["Pseudo code", "Code"], list(self.tab_buttons))
        check("the editor has the typing", self.typing(), "")
        self.messenger.send("c")  # (a c typed in the editor is a letter, not the panel's key)
        yield
        check("c while typing doesn't close the panel", self.panel is not None, "")
        self.code_state["lines"][:] = ["mvoe forward 3"]
        self.code_state["cursor"][:] = [0, 14]
        self.editor.changed()
        check("the code is read when the typing pauses, not at every key", self.read_at is not None, "")
        yield from self.pause(0.3)
        problems = " ".join(t.getText() for t in self.t_problems)
        check("a near miss shows a did-you-mean hint", "Did you mean: move forward 3?" in problems, problems)
        check("a near miss isn't corrected in the editor", self.code_state["lines"] == ["mvoe forward 3"],
              self.code_state["lines"])
        check("a near miss can't run", self.run_button["state"] == DGG.DISABLED and not self.can_run(), "")
        found = self.phrasebook.findAllMatches("**/+PGButton")
        check("the phrasebook has nothing to click or drag", found.getNumPaths() == 0, str(found))
        self.run_code()
        yield
        check("running a program with a mistake does nothing", self.mission.s["runs"] == 0 and not self.playing, "")
        solution = ["# 1 Battery", "Move forward 3.", "turn right", "go ahead one step", "Pick up the power cell!",
                    "# 2 Tool", "turn left", "move forward 2", "turn right", "repeat 3 times", "  move forward 1", "end",
                    "grab the front spinner", "# 3 Blockage", "turn right", "move forward 3", "turn left",
                    "move forward 2", "use spinner", "# 4 Village", "move forward 6", "# 5 Repair", "turn right", "repair"]
        self.code_state["lines"][:] = solution
        self.editor.changed()
        yield from self.pause(0.3)
        check("the solution is understood", not self.parsed["errors"], [r["message"] for r in self.parsed["errors"]])
        beside = " ".join(r["python_line"] for r in self.parsed["rows"])
        check("Python is shown beside the pseudo code", 'robot.use("spinner")' in beside and "for i in range(" in beside
              and any("robot." in re.sub("\x01[^\x01]*\x01|\x02", "", t.getText()) for t in self.py_rows),  # (unstyled)
              beside[:200])
        self.open_panel("code")
        yield
        code = "\n".join(self.code_view_state["lines"])
        check("the Code tab shows the whole program as Python", code.startswith("from clubcoders import robot")
              and "robot.repair()" in code and "    robot.move_forward(1)" in code, code[:120])
        self.open_panel("pseudo")
        yield
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_panel.png"))
        self.run_button["command"]()
        yield
        check("running starts the robot", self.playing or self.mission.s["runs"] == 1, "")
        while self.playing:
            yield
        for _ in range(3):
            yield
        s = self.mission.s
        check("the run completes the mission", s["complete"] and self.done is not None, s)
        check("three stars", self.mission.stars()["count"] == 3 and getattr(self, "done_stars", 0) == 3,
              self.mission.stars())
        check("the robot ends facing the power supply with 8 energy and 19 lines run",
              (s["x"], s["y"], s["dir"], s["energy"], s["linesUsed"]) == (13, 4, 2, 8, 19), s)
        check("the Solar Panel is saved for Mission 2", G.has_part(PROGRESS, "solar_panel")
              and G.load_progress(PROGRESS)["missions"]["wake_up_call"]["bestStars"] == 3, G.load_progress(PROGRESS))
        v = self.robot.models[self.robot.tool][0]
        want = world(s["x"], s["y"])
        check("the robot is drawn where it ended, holding the spinner", self.robot.tool == "spinner"
              and (v.chassis.getPos() - Point3(want.x, want.y, sim.RIDE)).length() < 0.01, v.chassis.getPos())
        check("the rockfall is cleared and the village lit", self.valley.rockfall.isHidden()
              and not self.valley.rubble.isHidden(), "")
        self.messenger.send("escape")  # (closes the end card)
        yield
        self.messenger.send("v")
        for _ in range(40):
            yield
        check("V changes the view", self.cam_mode == "follow", self.cam_mode)
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_follow.png"))
        self.cam_mode = "valley"
        for _ in range(40):
            yield
        if args.screenshot:
            self.save_shot(args.screenshot)
        self.messenger.send("r")
        yield
        check("R restarts the mission", self.mission.s["energy"] == 8 and not self.mission.s["complete"]
              and self.robot.tool == "none", self.mission.s)
        self.code_state["lines"][:] = ["move forward 5", "turn right", "move forward 4"]
        self.run_code()
        while self.playing:
            yield
        check("skipping the power cell flattens the battery: the banner offers a reset",
              self.mission.s["failed"] and not self.banner.isHidden(), self.mission.s)
        # --- reset (CHANGE 188): with the panel open and the keyboard the editor's, Ctrl+R; mid-run, the button ---
        fresh = G.new_mission("TITAN").snapshot()
        self.messenger.send("c")
        yield
        bad_code = ["move forward 5", "turn right", "move forward 4"]
        self.code_state["lines"][:] = bad_code
        self.editor.changed()
        yield
        self.messenger.send("control-r")
        yield
        check("Ctrl+R with the code panel open resets the mission", self.mission.snapshot() == fresh
              and self.banner.isHidden() and self.view["x"] == fresh["x"] and self.view["y"] == fresh["y"]
              and self.robot.tool == "none", self.mission.s)
        check("...and keeps the code in the editor, open and focused", self.code_state["lines"] == bad_code
              and self.panel is not None and self.typing(), self.code_state["lines"])
        self.messenger.send("r")  # (the key, as the window hears it, and the letter, as the editor hears it)
        self.messenger.send("keystroke", ["r"])
        yield
        check("r while typing is a letter in the code, not a reset", "r" in "".join(self.code_state["lines"][0])
              and self.code_state["lines"] != bad_code and self.mission.snapshot() == fresh, list(self.code_state["lines"]))
        self.code_state["lines"][:] = ["move forward 3", "turn right", "move forward 1", "pick up power cell"]
        self.editor.changed()
        yield from self.pause(0.3)
        self.run_button["command"]()
        yield
        yield
        check("a run is playing", self.playing and self.mission.s["runs"] == 1, "")
        self.panel_reset["command"]()  # (the panel's RESET button, mid-run)
        yield
        check("RESET while a run is playing stops it and resets the mission", not self.playing and self.queue == []
              and self.mission.snapshot() == fresh and self.view["x"] == fresh["x"] and self.view["y"] == fresh["y"],
              (self.playing, self.mission.s))
        v = self.robot.models[self.robot.tool][0]
        start_at = world(fresh["x"], fresh["y"])
        check("...and the robot is drawn back on its start square, holding nothing", self.robot.tool == "none"
              and (v.chassis.getPos() - Point3(start_at.x, start_at.y, sim.RIDE)).length() < 0.01, v.chassis.getPos())
        check("the HUD's RESET button and the banner's are the same reset", self.reset_button["command"] == self.reset_mission
              and self.panel_reset["command"] == self.reset_mission, "")
        # --- the camera and the graphics are not the mission's (CHANGE 188) ---
        for _ in range(12):
            self.wheel(1 / 0.88)
        check("the wheel zooms out no further than ZOOM_MAX", self.zoom == ZOOM_MAX, self.zoom)
        self.pan_by(100, -100)
        check("a drag pans no further than PAN_REACH past the map", self.pan.x == G.W * SQ / 2 + PAN_REACH
              and self.pan.y == -(G.H * SQ / 2 + PAN_REACH), self.pan)
        from panda3d.core import RenderModeAttrib
        if not rw_gfx.look():
            self.set_gfx("look", "wireframe")
            check("Wireframe draws the scene in Panda's wireframe mode",
                  self.render.getRenderMode() == RenderModeAttrib.MWireframe, self.render.getRenderMode())
        self.set_gfx("tier", "low")
        sun = rw_gfx.sun()
        check("Low turns the shadows off in this run (an offscreen window doesn't reopen)",
              sun is None or not sun.node().isShadowCaster(), "")
        self.messenger.send("escape")  # (closes the panel: the keyboard is the window's again)
        yield
        self.messenger.send("g")
        yield
        check("G opens the Graphics panel with Look and Quality: Auto and the engine's seven tiers", self.options is not None
              and set(self.option_buttons) == {"solid", "wireframe", "auto"} | set(gfx_tiers.TIERS)
              and TIER_CHOICES == (None,) + gfx_tiers.TIERS, sorted(self.option_buttons, key=str))
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_graphics.png"))
        from engine import line_look
        kept, drawn_before, tier_before = {}, self.tier, rw_gfx.tier()
        for tier in gfx_tiers.TIERS:  # every level, by its button: saved, the window still this one, the tier drawn unchanged
            self.option_buttons[tier]["command"](*self.option_buttons[tier]["extraArgs"])
            kept[tier] = (gfx_tiers.load_settings(MISSION_SETTINGS_DIR).get(GFX_KEY) or {}).get("tier")
            if tier in gfx_tiers.LOOKS:
                check(f"choosing {tier} shows the Line colour row", "#ffb000" in self.option_buttons, sorted(self.option_buttons, key=str))
        check("every tier can be chosen and is kept in settings.json", all(kept[t] == t for t in gfx_tiers.TIERS), kept)
        check("...and a chosen tier is drawn from the next start, not by this offscreen window",
              self.tier == drawn_before and rw_gfx.tier() == tier_before, (self.tier, rw_gfx.tier()))
        self.option_buttons["lines"]["command"](*self.option_buttons["lines"]["extraArgs"])
        self.option_buttons["#ffb000"]["command"](*self.option_buttons["#ffb000"]["extraArgs"])
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_graphics_lines.png"))
        check("a line colour is kept and set in the engine at once", self.gfx.get("line_colour") == "#ffb000"
              and (gfx_tiers.load_settings(MISSION_SETTINGS_DIR).get(GFX_KEY) or {}).get("line_colour") == "#ffb000"
              and tuple(round(c, 2) for c in line_look.colour()) == (1.0, 0.69, 0.0), (self.gfx, line_look.colour()))
        self.option_buttons["auto"]["command"](*self.option_buttons["auto"]["extraArgs"])
        check("Auto drops the tier: the next start picks this computer's solid tier", "tier" not in self.gfx
              and "tier" not in (gfx_tiers.load_settings(MISSION_SETTINGS_DIR).get(GFX_KEY) or {})
              and "#ffb000" not in self.option_buttons and self.next_tier() in SOLID, (self.gfx, self.next_tier()))
        check("the knobs follow Auto back to this run's own", sun is None or not self.shadow0
              or (sun.node().isShadowCaster() and sun.node().getShadowBufferSize().x == self.shadow0), "")
        self.option_buttons["high"]["command"](*self.option_buttons["high"]["extraArgs"])
        check("HIGH keeps the shadows on, as far as this tier has them", self.gfx["tier"] == "high"
              and (sun is None or not self.shadow0 or sun.node().isShadowCaster()), self.gfx)
        if not rw_gfx.look():
            self.option_buttons["solid"]["command"](*self.option_buttons["solid"]["extraArgs"])
            check("SOLID clears the wireframe", self.render.getRenderMode() == RenderModeAttrib.MUnchanged, "")
        saved = gfx_tiers.load_settings(MISSION_SETTINGS_DIR).get(GFX_KEY)
        check("the choice is kept in settings.json beside the progress file", saved == self.gfx
              and os.path.dirname(os.path.abspath(PROGRESS)) == MISSION_SETTINGS_DIR, saved)
        self.messenger.send("escape")
        yield
        check("Esc closes the Graphics panel", self.options is None, "")
        self.messenger.send("c")
        yield
        self.run_button["command"]()
        while self.playing:
            yield
        twin = G.new_mission("TITAN")
        twin.run(self.parsed["program"], self.parsed["code_lines"])
        check("zoom, pan and the graphics change nothing in the mission", self.mission.snapshot() == twin.snapshot()
              and self.mission.s["cellTaken"], self.mission.s)
        self.messenger.send("escape")
        yield
        # --- the whole map in the picture and lit at the furthest zoom (CHANGE 188) ---
        views = {}
        for mode in ("valley", "above"):
            self.cam_mode, self.zoom, self.pan = mode, ZOOM_MAX, Vec3(0, 0, 0)
            self.place_camera(1.0)  # (snaps the camera there)
            views[mode] = self.view_check()
        check("at the furthest zoom the whole map is inside the view, in the valley and above views",
              all(v["inside"] for v in views.values()), views)
        check("...and lit: nearer than the far clip and any fog's onset", all(v["lit"] for v in views.values()), views)
        self.cam_mode, self.zoom = "valley", 1.0
        self.place_camera(1.0)
        check("at zoom 1 every square of the valley is in view", self.view_check(edges=False)["inside"],
              (self.view_check(edges=False), self.view_check()))
        self.zoom = ZOOM_MAX
        for _ in range(30):
            yield
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_zoom.png"))
        self.cam_mode, self.zoom = "above", 0.5
        self.pan_by(5, 5)
        self.messenger.send("home")
        yield
        check("Home puts the camera back as it started", (self.cam_mode, self.zoom, tuple(self.pan)) == ("valley", 1.0, (0, 0, 0)),
              (self.cam_mode, self.zoom, self.pan))
        self.choose("RAZORBACK")
        self.code_state["lines"][:] = ["move forward 3", "turn right", "move forward 1", "pick up power cell",
                                       "turn left", "move forward 2", "turn right", "move forward 3", "pick up flipper",
                                       "turn right", "move forward 3", "turn left", "move forward 2", "use flipper"]
        self.run_code()
        while self.playing:
            yield
        s = self.mission.s
        check("RAZORBACK with the flipper: the rockfall stays, the robot holds the flipper",
              s["tool"] == "flipper" and not s["rockCleared"] and self.robot.tool == "flipper" and
              not self.robot.models["flipper"][0].weapon.isHidden() and not self.valley.rockfall.isHidden()
              and self.banner.isHidden(), s)
        self.cam_mode = "follow"
        for _ in range(40):
            yield
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_flipper.png"))
        failed = [r for r in results if not r[1]]
        for name, ok, detail in results:
            print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -- {detail}"), flush=True)
        print(f"SELFTEST {'FAIL' if failed else 'PASS'}: {len(results) - len(failed)} of {len(results)} passed", flush=True)
        os._exit(1 if failed else 0)


WakeUpCall().run()
