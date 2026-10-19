"""Kart Lab window for learners and the teacher. The races run on kart_server.py.

Learner:  python kart_client.py                (log in with a username and password in the window)
Teacher:  python kart_client.py --name "Mr P" --teacher
Offline:  python kart_client.py --offline --cpu 5        no server: a race on this laptop against computer karts
Class server: add --host wss://... Learners come through the Club Coders app (a ticket from the club desk); the
teacher's code comes from --code or KARTLAB_TEACHER_CODE; on a laptop test server it is the demo code.

Driving:   arrows or WASD drive, Shift (or Space) drifts (hold it through a bend, let go for a boost), R puts you
           back on the track, V changes the camera (chase, hood, TV), the mouse wheel zooms
Panels:    Tab or I opens and closes the HUD (the Mission, Garage, AI card, My card, Mods and Settings tabs; the
           teacher's Controls, Races, Learners, Accounts, Outcomes, AI cards, Changes, Limits, Warnings and more)
           C your kart as code (edit it, then APPLY CODE)   H the key list
Brain:     U uploads brains/my_brain.py (your brain drives the kart)   P autopilot on / off
Typing:    while you type in a text box, keys go into the box (not the kart). Click away or press Esc to stop.

How your own kart feels instant online: the window steps its own kart itself with every key press (kart_sim.step,
the same arithmetic the server runs) and sends the numbered inputs; each snapshot from the server says which
input it had applied, the window compares the server's kart with what it predicted for that moment and, when they
differ by more than 5 cm, puts the server's state in and replays the inputs since (engine.predict). The other karts
are drawn a little in the past, between two snapshots (engine.interp). Bumps between karts are the server's to
decide: a bump shows on your screen when its word arrives, eased in so it never jumps.
"""
import argparse
import copy
import json
import math
import os
import queue
import subprocess
import sys
import textwrap
import threading
import random
import time
import webbrowser

from panda3d.core import loadPrcFileData

import kart_version  # (first: this records the code this window is running, before anything can change it)
sys.path.insert(0, kart_version.ENGINE_HOME)  # (the engine package, shared by every game: engine/ beside the games)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="", help="username (learners are asked in the window if it's left out)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--host", default=None,
                help="server address (default: this computer); 'class' = the one in teacher_settings.json")
ap.add_argument("--code", help="class code (the demo codes on a laptop test server)")
ap.add_argument("--window", help="the window: 1280x720, 1600x900 ... 3840x2160 or full "
                                 "(else this computer's last choice; CHANGE 126)")
ap.add_argument("--gfx", choices=["auto", "mesh", "lines", "basic", "low", "medium", "high", "ultra"], default="auto",
                help="graphics: auto picks for this computer (and remembers); low or basic on old laptops; "
                     "mesh and lines are a look in one colour; ultra for a gaming PC")
ap.add_argument("--offline", action="store_true", help="a race on this laptop, no server")
ap.add_argument("--track", default="club")
ap.add_argument("--cpu", type=int, default=3, help="computer karts (offline)")
ap.add_argument("--level", default="medium", help="their level: easy, medium, expert (offline)")
ap.add_argument("--laps", type=int, default=None)
ap.add_argument("--stats", default=None, help="your design: speed,acceleration,grip points (100 in all)")
ap.add_argument("--brain", default=None, help="a brain file to drive your kart (offline)")
ap.add_argument("--no-predict", action="store_true", help="draw your own kart from the server's snapshots only")
ap.add_argument("--no-interp", action="store_true", help="draw each snapshot as it arrives")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--autostart", action="store_true", help="offline: start the race at once")
ap.add_argument("--mute", action="store_true")
ap.add_argument("--x", type=int, help="window position (left edge)")
ap.add_argument("--panel", action="store_true", help=argparse.SUPPRESS)  # (tests: open the side panel at once)
ap.add_argument("--tab", help=argparse.SUPPRESS)  # (tests: open the side panel on this tab)
ap.add_argument("--show-code", action="store_true", help=argparse.SUPPRESS)  # (tests: open the code panel)
ap.add_argument("--card", help=argparse.SUPPRESS)  # (tests: the teacher's AI cards tab opens on "edit" or a card)
ap.add_argument("--view-tab", help=argparse.SUPPRESS)  # (tests: the Learner view opens on this tab)
ap.add_argument("--scroll", type=float, help=argparse.SUPPRESS)  # (tests: slide the side panel this far after 3 s)
ap.add_argument("--ticket", help=argparse.SUPPRESS)  # (from the club desk: the app has logged this person in)
args = ap.parse_args()
if os.environ.get("KARTLAB_LOGIN") and not args.name:  # reopened by itself (to load code changes): same login
    try:
        args.name, args.password, *rest = json.loads(os.environ.pop("KARTLAB_LOGIN"))
        args.ticket = rest[0] if rest and rest[0] else args.ticket
    except (ValueError, TypeError):
        pass
OFFLINE = bool(args.offline)
HERE = os.path.dirname(os.path.abspath(__file__))
TEACHER_SETTINGS = os.path.join(HERE, "teacher_settings.json")  # the teacher's laptop only: never in git
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "KartLab")
from engine import editor as code_editor  # noqa: E402  (the engine: shared by every game)
from engine import hud  # noqa: E402
from engine import garage, schema  # noqa: E402
from engine.hud import DARK, button, check, label, load_json, remember, text_button, word  # noqa: E402,F401
from engine.hud import YELLOW, WHITE, GREY, RED, GREEN, BLUE, ORANGE, PANEL, ON, OFF, BOX, HANDLE  # noqa: E402,F401
SETTINGS = hud.setup(SETTINGS_DIR, sys.modules[__name__])  # this computer's settings; this module's colours follow the look
from engine import club_ticket  # noqa: E402
if args.ticket:  # the club desk has logged this person in: their name and role are in the ticket (the server checks it)
    peek = club_ticket.peek(args.ticket) or {}
    args.name = peek.get("name") or args.name
    args.teacher = args.teacher or peek.get("role") == "teacher"
TEACHER = args.teacher
BRAINS = (os.path.join(os.path.dirname(sys.executable), "brains", "kartlab") if kart_version.FROZEN  # (the built
          else os.path.join(HERE, "brains"))  # app keeps each game's brains folder beside the exe: brains\kartlab)

if args.host == "class":  # the class server's address, from the teacher's settings
    args.host = load_json(TEACHER_SETTINGS).get("server") or kart_version.ONLINE_SERVER or kart_version.LOCAL_SERVER
elif args.host is None:  # a learner's last choice on the login screen, or this computer
    where = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("where")
    args.host = {"local": kart_version.LOCAL_SERVER, "online": kart_version.ONLINE_SERVER}.get(
        where if not TEACHER else None) or kart_version.SERVER
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))  # a laptop test server
from engine import try_local  # noqa: E402
# Try it on this laptop (see try_local): the teacher's window, opened on a test server here to look at this
# laptop's game before it is made live for the class. It knows how to go back to the class.
TRY = try_local.unpack(os.environ.pop("KARTLAB_TRY", "")) if args.teacher and LOCAL else None
if args.code or args.ticket:
    code = args.code or ""
elif TEACHER:
    code = (os.environ.get("KARTLAB_TEACHER_CODE") or ("TEACH99" if LOCAL else "")
            or load_json(TEACHER_SETTINGS).get("teacher_code"))
    if not code and not OFFLINE:
        raise SystemExit("The teacher code is needed: put it in teacher_settings.json next to kart_client.py "
                         '(for example {"teacher_code": "..."}) or use --code.')
else:
    code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
name = args.name or ("Teacher" if TEACHER else "")
net = None  # the connection to the server, made when you log in

title = f"Kart Lab - {'OFFLINE' if OFFLINE else 'TEACHER' if TEACHER else 'LEARNER'}" + (f" ({name})" if name else "")
if TRY:
    title += " - TRYING ON THIS LAPTOP"
x = args.x if args.x is not None else (40 if TEACHER else 1360)
from engine import gfx_tiers  # noqa: E402
GFX = gfx_tiers.resolve(SETTINGS_DIR, args.gfx, gfx_tiers.TIERS)  # (auto: this computer's saved tier, else what its
# driver suggested; Kart Lab draws all seven tiers: CHANGE 144)
loadPrcFileData("", hud.window_arg(args.window, x) + f"window-title {title}\n"  # (the size: CHANGE 126)
                    + gfx_tiers.prc_for(GFX))  # (texture size, mipmaps, multisamples: read as the window opens)
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, TextNode, WindowProperties  # noqa: E402

import cpu_brains  # noqa: E402
import kart_gfx  # noqa: E402
import kart_hud as kh  # noqa: E402
import kart_sim as sim  # noqa: E402
import kart_items  # noqa: E402  (CHANGE 159: the power-ups, offline)
ITEM_TEXT = [("boost", "Boost"), ("oil", "Oil slick"), ("shot", "Bouncing shot"), ("homing", "Homing shot"),
             ("shield", "Shield")]  # (CHANGE 159: kart_items.ITEMS on the screen)
import kart_sound  # noqa: E402
import kart_track  # noqa: E402
from engine import gamepad, interp, predict, wire  # noqa: E402  (gamepad: a controller, CHANGE 170)
from engine.net import Net  # noqa: E402
from engine import net as net_module  # noqa: E402
try:
    import kart_missions as km  # noqa: E402  (the lessons' words: which objectives are reflections, the AI card's targets)
except ImportError:  # (the teaching layer isn't here yet: the engine's defaults)
    km = None

SCHEMA = wire.Schema("kart", sim.SCHEMA_FIELDS)
SNAP_SPEC = {"entities": ["id", {"x": "lerp", "y": "lerp", "yaw": "angle", "v": "lerp", "u": "lerp"}]}
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230), (240, 120, 40),
           (60, 200, 200), (230, 90, 160)]  # (the server's order too: the computer karts' colours)
AI_TARGETS = dict(getattr(km, "AI_TARGETS", None) or kh.AI_TARGETS)
REFLECTIONS = tuple(getattr(km, "REFLECTIONS", None) or ())
LESSON_NUMBERS = list(getattr(km, "LESSONS", None) or {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})
APP = None  # the window (so any button click can end typing in a text box)
net_module.OPTIONS["compression"] = None  # (binary snapshots are small already; deflate would make them bigger)


def send(msg):
    if net is not None:
        net.send(msg)


def fmt_lap(t):
    """A lap time as the page writes it (kart.js fmtTime): 41.37s, or 1:02.50 past a minute (CHANGE 143)."""
    m = int(t // 60)
    return f"{m}:{t - m * 60:05.2f}" if m else f"{t:05.2f}s"


def between(a, b, f):
    """(CHANGE 155) A kart's state a fraction f of the way from a to b: the position, speed and heading; the rest b's."""
    if a is None or not f > 0:
        return dict(a if a is not None else b)
    if f >= 1:
        return dict(b)
    dy = (b["yaw"] - a["yaw"] + 180) % 360 - 180
    return dict(b, x=a["x"] + (b["x"] - a["x"]) * f, y=a["y"] + (b["y"] - a["y"]) * f, yaw=a["yaw"] + dy * f,
                v=a["v"] + (b["v"] - a["v"]) * f, u=a.get("u", 0.0) + (b.get("u", 0.0) - a.get("u", 0.0)) * f)


def parse_stats(text, design):
    """--stats: the kart's points (offline, and a window's first design before the server's is known)."""
    d = dict(design)
    if text:
        try:
            sp, ac, gr = (int(v) for v in text.split(","))
            d.update(speed=sp, acceleration=ac, grip=gr)
        except ValueError:
            print("--stats wants three numbers, e.g. 40,30,30", flush=True)
    return sim.fit_design(d)


class Lab(hud.HudKit, ShowBase):
    UNIT, CPU_VIEW = "kart", "Computer kart"
    VERSION, LIVE_ID = kart_version.VERSION, kart_version.live_id()
    FIRST_TAB = "teacher" if TEACHER else "garage" if OFFLINE else "missions"
    teacher = TEACHER
    CODE_PANEL, CODE_ROWS = kh.CODE_PANEL, kh.CODE_ROWS
    reflections = REFLECTIONS
    user_mods = getattr(sim, "USER_MODS", {})
    STAGE_WORD = "TRACK"
    GFX_TIERS = gfx_tiers.TIERS          # (CHANGE 144: the Settings tab's Graphics row and the class maximum's)
    LINE_COLOURS = kart_gfx.LINE_COLOURS
    LIMITS_TITLE = "KART LIMITS"
    LIMITS_NOTE = "The points: each stat from 10 to 60, 100 points in all (the standard design sheet)."
    gp_races = 3  # the teacher's grand prix: how many races the next one has (2 to 5: CHANGE 143)

    def __init__(self):
        super().__init__()
        self.disableMouse()
        global APP
        APP = self
        hud.setup_app(self, send)
        self.init_hud()  # (the engine's HUD kit: text boxes, the side panel, settings, the code panel's place)
        self.my_name = name
        self.code_state = {"lines": [], "cursor": [0, 0], "scroll": 0}  # the code panel's text, kept while it is closed
        self.schema = kh.design_schema()  # the kart's variables: the code panel and the garage's tables come from it
        self.code_changed = False  # the design holds a value changed in the code (Mission 1: hack the code)
        self.code_hack = False     # the design holds a value changed in the code that this mission's garage hides
        gfx_tiers.detect(self, SETTINGS_DIR)  # (the window is open: what the driver says, for the next run's tier)
        self.pipeline = kart_gfx.init(self, GFX, line_colour=self.line_colour)
        self.gfx_tier = kart_gfx.tier()  # (the tier in use: lower than GFX when the driver couldn't run that one)
        try:
            self.snd = kart_sound.KartSounds(self, on=not args.mute and not args.offscreen)
        except Exception as e:  # (no sound card, or the sound kit unhappy: the game is quiet)
            print(f"No sound: {e!r}", flush=True)
            self.snd = kart_sound.KartSounds.__new__(kart_sound.KartSounds)
            self.snd.on = False
        self.muted = bool(args.mute)
        self.pending_rebuild = False  # a panel redraw waiting until typing stops
        self.started = False
        self.login_panel = None
        self.delete_armed = None      # teacher: the account whose Delete button says "Sure?"
        self.newer, self.download_button = None, None
        self.gfx_monitor = None
        self.panel = self.code_panel = None
        self.tab = None
        if (kart_version.FROZEN or not LOCAL) and not OFFLINE:
            self.check_for_update()
        self.accept("escape", self.escape)
        self.accept("mouse1", self.stop_typing)  # clicking the track (not a panel) stops typing
        self.accept("tab", self.tab_or_panel)          # Tab: the side panel; while typing, the next text box
        self.accept("shift-tab", self.tab_key, [-1])   # ...and Shift+Tab: back to the one before
        self.start = self.last = time.perf_counter()
        if OFFLINE:
            self.start_offline()
        elif TEACHER or args.ticket or (args.name and args.password):
            error = self.connect(name, args.password or "")
            if error:
                if TEACHER:
                    self.show_refusal(error)  # (on screen: the .bat shows no console)
                    self.taskMgr.add(self.update, "update")
                    return
                self.show_login(error)
        else:
            self.show_login()
        self.taskMgr.add(self.update, "update")

    # ---------- logging in ----------
    def connect(self, username, password):
        """Connect and log in. Returns None if it worked, or a message saying what went wrong."""
        global net, name
        try:
            net = Net(args.host, username, code, password=password, version=kart_version.VERSION,
                      **({"ticket": args.ticket} if args.ticket else {}))
        except OSError:
            net = None
            return f"Can't reach the Kart Lab server ({args.host}). Is it running?"
        except Exception as e:  # e.g. the secure connection couldn't be set up
            net = None
            return f"Can't connect to the Kart Lab server ({args.host}): {e}"
        welcome, problem = self.wait_for("welcome")
        if welcome is None:
            net = None
            if "Out of date" in problem:
                self.offer_download()
            return problem
        name = welcome.get("name") or username
        self.password = password
        if not TEACHER and not LOCAL and code:
            remember("class_code", code)
        self.start_game(welcome)
        return None

    def wait_for(self, kind):
        deadline = time.time() + 8
        while True:
            try:
                m = net.inbox.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                return None, "No answer from the server."
            if m["type"] == kind:
                return m, ""
            if m["type"] == "closed":
                return None, m.get("reason") or "The server closed the connection (wrong class code, the class " \
                                                "is full, or a teacher is already on)."

    def show_refusal(self, error):
        """The teacher's window couldn't start: say why, with Try again and Close."""
        print(error, flush=True)
        self.login_panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))
        f = DirectFrame(parent=self.login_panel, frameColor=PANEL, frameSize=(-0.72, 0.72, -0.3, 0.36))
        label(f, "KART LAB  -  TEACHER", 0, 0.24, 0.06, YELLOW, TextNode.ACenter)
        label(f, error, 0, 0.1, 0.034, RED, TextNode.ACenter, wrap=36)
        hint = ("Another teacher window is open (on this computer or another): close it, then try again. If none is, "
                "restart the game server (on the server: sudo systemctl restart robotlab@class3)."
                if "already connected" in error else "")
        label(f, hint, 0, -0.06, 0.026, GREY, TextNode.ACenter, wrap=48)
        button(f, "Try again", -0.16, -0.22, self.try_again, (), 0.04, (0.15, 0.55, 0.25, 1))
        button(f, "Close", 0.2, -0.22, self.userExit, (), 0.04)

    def try_again(self):
        if getattr(self, "login_panel", None) is not None:
            self.login_panel.destroy()
            self.login_panel = None
        error = self.connect(name, args.password or "")
        if error:
            self.show_refusal(error)

    def show_login(self, error=""):
        self.login_panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))  # backdrop
        f = DirectFrame(parent=self.login_panel, frameColor=PANEL, frameSize=(-0.62, 0.62, -0.5, 0.46))
        label(f, "KART LAB", 0, 0.34, 0.08, YELLOW, TextNode.ACenter)
        online = bool(kart_version.ONLINE_SERVER)
        if online:  # (only when the club has a Kart Lab class server)
            label(f, "Play on", -0.54, 0.23, 0.035, GREY)
            for i, (local, text) in enumerate(((True, "This computer (test)"), (False, "Online class"))):
                button(f, text, -0.12 + i * 0.4, 0.235, self.set_where, [local], 0.035, ON if LOCAL == local else OFF)
        label(f, "Username", -0.54, 0.12, 0.04)
        self.entry(f, "login_user", -0.16, 0.12, 12, initial=args.name, scale=0.045,
                   command=lambda t: self.focus_entry("login_pass"))
        label(f, "Password", -0.54, 0.0, 0.04)
        self.entry(f, "login_pass", -0.16, 0.0, 12, scale=0.045, obscured=True, command=lambda t: self.submit_login())
        low = 0 if LOCAL else -0.1  # the class server asks for the class code too
        if not LOCAL:  # from the welcome letter: typed once, then remembered on this computer
            label(f, "Class code", -0.54, -0.12, 0.04)
            self.entry(f, "login_code", -0.16, -0.12, 12, initial=code, scale=0.045,
                       command=lambda t: self.submit_login())
        button(f, "LOG IN", 0, -0.14 + low, self.submit_login, None, 0.05, (0.15, 0.55, 0.25, 1))
        help_text = ("New here? Choose a username and a password: that makes your profile.\n"
                     "Next lesson, use the same ones to carry on where you left off." if LOCAL else
                     "Use the username, password and class code your teacher gave you.\n"
                     "Forgotten your password? Ask your teacher to set a new one.")
        label(f, help_text, 0, -0.26 + low * 0.7, 0.028, GREY, TextNode.ACenter)
        self.login_msg = label(f, error, 0, -0.38 + low * 0.5, 0.03, RED, TextNode.ACenter, wrap=38)
        self.focus_entry("login_user" if not args.name else "login_pass")

    def set_where(self, local):
        """Log in to the laptop test server or to the club's online class server (remembered on this computer)."""
        global LOCAL, code
        if local == LOCAL:
            return
        args.host = kart_version.LOCAL_SERVER if local else kart_version.ONLINE_SERVER
        LOCAL = local
        code = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code") or ("CLUB42" if LOCAL else "")
        remember("where", "local" if local else "online")
        self.keep_typing()  # (keeps the username and password typed so far)
        self.login_panel.destroy()
        self.show_login()

    def focus_entry(self, key):
        e = self.entries.get(key)
        if e is not None:
            e["focus"] = 1

    def submit_login(self):
        global code
        user, password = self.entries["login_user"].get().strip(), self.entries["login_pass"].get()
        if not user:
            self.login_msg.setText("Type your username first.")
            return
        if "login_code" in self.entries:
            code = self.entries["login_code"].get().strip()
            if not code:
                self.login_msg.setText("Type the class code from your welcome letter.")
                return
        self.login_msg.setText("Logging in...")
        self.login_msg.setFg(GREY)
        self.graphicsEngine.renderFrame()
        error = self.connect(user, password)
        if error and self.login_panel is not None:
            self.login_msg.setText(error)
            self.login_msg.setFg(RED)

    # ---------- the game screen ----------
    def common_start(self):
        """What the online and the offline game have in common: the track, the kart models, the camera, the
        racing screen, the race's state and the keys."""
        self.track_name = None
        self.track = None
        self.track_vis = None
        self.cam_rig = kart_gfx.ChaseCamera(self)
        self.cam = self.cam_rig  # (the HUD kit's mouse wheel zooms through self.cam)
        self.screen = None       # the racing screen (kart_gfx.Hud): made with the track
        self.karts = {}          # id -> KartVisual
        self.designs = {}        # id -> design
        self.colours = {}        # id -> (r, g, b)
        self.my_id = None
        self.race = {"phase": sim.FLAGS_GRID, "go_local": None, "places": [], "laps": 3, "events": [], "results": None,
                     "brains": {}, "paused": False}
        self.cd_last, self.was_boosting, self.was_finished = None, False, False
        self.lap_seen, self.lap_started, self.best_lap = None, None, None  # lap timing (see laps)
        self.accum = 0.0
        self.keys_down = {"drift": False, "respawn": False, "use": False}  # (use: E, your item: CHANGE 159)
        self.pad = gamepad.Pad(self)  # (CHANGE 170) a USB or Bluetooth controller
        self.note_text, self.note_big, self.note_until = "", False, 0.0
        self.finished = False
        self.autopilot = False
        self.ping_ms = 0.0
        self.ctrl_ms = None
        self.last_ping = self.perf_at = 0.0
        self.local = None
        self.predictor = None
        self.draw_from = None  # the predicted state before the newest tick: drawn between the two (CHANGE 155)
        self.others = []  # the other karts as the prediction sees them (set_others)
        self.smoother = predict.ErrorSmoother(remove_up=True)
        self.lead = predict.LeadController()
        self.snaps = interp.Snapshots(SNAP_SPEC)
        self.snap_seq = 0
        self.next_seq = 1  # one numbering for every input we send, whether or not a predictor is running
        self.sent_at = {}
        self.sig = {}      # what each panel was last drawn from
        self.class_list, self.missions, self.teaching, self.tournament, self.roster = [], None, None, None, None
        self.card_checks = {"privacy": False, "review": False, "credit": False}
        self.card_msg = ("", WHITE)
        self.card_target = next(iter(AI_TARGETS))
        self.ai_jobs = {}        # teacher: card id -> {"status", "result", "change"}
        self.cards_view = None   # teacher's AI cards tab: None (the requests), "edit" (the learners' card), a card's id
        if args.card:
            self.cards_view = int(args.card) if args.card.isdigit() else args.card
        self.prompt_view, self.prompt_state = None, {}  # ...that card's whole prompt, in a box that scrolls
        self.card_targets = {}   # teacher: card id -> what Claude may change (can differ from the learner's choice)
        self.card_user_mod = {}  # teacher: card id -> make a whole-game change as a switchable user mod
        self.view_name, self.view_tab = None, "garage"   # teacher's learner view
        if args.view_tab:
            self.view_tab = args.view_tab
        self.change_view, self.change_page, self.change_msg = None, 0, ("", GREY)  # teacher's Changes tab
        self.view_drafts, self.view_missions = {}, {}
        self.code_shown, self.code_msg = None, ("", GREY)
        self.status_msg = ("", WHITE)
        self.needs_restart = False
        self.reconnect_thread = None
        self.reconnecting = False
        self.try_starting = None
        self.perf_label = None
        self.prefs_sent, self.prefs_at = "", 0.0
        self.key("v", self.cam_rig.cycle)
        self.key("shift", self.key_down, "drift", True)
        self.accept("shift-up", self.key_down, ["drift", False])
        self.key("space", self.key_down, "drift", True)
        self.accept("space-up", self.key_down, ["drift", False])
        self.key("r", self.key_down, "respawn", True)
        self.key("e", self.key_down, "use", True)  # (CHANGE 159) your item
        self.key("i", self.toggle_panel)
        self.key("c", self.toggle_code)
        self.key("h", self.toggle_help)
        self.key("n", self.toggle_mute)
        self.key("u", self.upload_brain)
        self.key("p", self.autopilot_key)
        for key, factor in (("=", 0.8), ("+", 0.8), ("-", 1.25), ("=-repeat", 0.9), ("--repeat", 1.11)):
            self.key(key, self.cam_rig.wheel, factor)
        for key, factor, step in (("wheel_up", 0.88, -1), ("wheel_down", 1 / 0.88, 1)):
            self.key(key, self.wheel, factor, step)  # (the wheel slides a tall side panel, or zooms)
        self.key("page_up", self.slide_panel, -1)
        self.key("page_down", self.slide_panel, 1)

    def start_game(self, welcome):
        if self.check_code(welcome):
            return
        if self.login_panel is not None:
            self.login_panel.destroy()
            self.login_panel = None
        self.entries, self.typing = {}, None
        props = WindowProperties()
        props.setTitle(f"Kart Lab - {'TEACHER' if TEACHER else 'LEARNER'} ({name})")
        if self.win is not None and not args.offscreen:
            self.win.requestProperties(props)
        self.common_start()
        self.started = True
        self.my_name = name
        self.lesson = self.fill_lesson(welcome.get("lesson") or {})
        self.obey_gfx_max()
        self.rules = kh.default_rules() | dict(welcome.get("rules") or {})
        self.design = sim.fit_design(dict(welcome.get("design") or sim.default_design(name)))
        if args.stats:
            self.design = parse_stats(args.stats, self.design)
        self.draft = copy.deepcopy(self.design)  # what is being edited in the garage
        self.my_id = welcome.get("kart")
        self.set_track(self.lesson.get("track", args.track), self.lesson.get("laps", 3))
        self.hud()
        self.start_monitor()
        self.restore_prefs(welcome.get("prefs") or {})
        self.needs_restart = bool(welcome.get("live_ready"))
        self.tab = args.tab or (None if not args.panel and not args.tab else self.FIRST_TAB)
        if args.tab == "outcomes_edit":  # (tests: the Outcomes tab on its missions editor)
            self.tab, self.editing_missions = "outcomes", True
        self.show_code = bool(args.show_code)
        if args.scroll:
            self.taskMgr.doMethodLater(3, lambda t: (setattr(self, "panel_scroll", args.scroll), self.place_panel())
                                       and None, "test scroll")
        tabs = [t for t, _ in (kh.TEACHER_TABS if TEACHER else kh.LEARNER_TABS)]
        if not args.tab and not args.panel and getattr(self, "last_tab", None) in tabs:
            self.tab = None  # (CHANGE 103: I opens the HUD on the tab last used; the race starts with it closed)
        if args.stats:  # (a design chosen on the command line goes to the server at once)
            send({"type": "design", "design": self.design, "code": False})
        send({"type": "slot", "do": "list"})  # (my saved designs: CHANGE 83)
        if TEACHER:
            self.key("enter", send, {"type": "start"})
            self.key("g", send, {"type": "grid"})
            self.key("t", self.next_track)
            self.banner_note("Teacher: Enter starts the race, G puts everyone on the grid, T changes the track", 8)
            self.push_mod_makers()
        if TRY:
            self.begin_try()
        if TEACHER and os.environ.get("CLUBCODERS_TRY_TEST"):  # (tests: there and back by itself, noting each step)
            self.taskMgr.doMethodLater(4, self.try_test, "try test")
        self.rebuild_panels()
        self.start = self.last = time.perf_counter()
        self.prefs_at = self.start
        if welcome.get("new_profile"):
            self.banner_note(f"Welcome, {name}! Your profile is made: next time log in with the same username "
                             "and password.", 7)

    def fill_lesson(self, lesson):
        """The lesson as the window needs it, whatever the server sent: the kart's race settings and the teaching
        layer's (the tools, the limits, the hazards), with defaults for anything missing."""
        L = {"lesson_number": 1, "track": args.track, "laps": 3, "cpu_karts": 3, "cpu_level": "medium", "brains": True,
             "tools": {}, "limits": None, "hazards": {}, "user_mods": {}, "mods_in_vote": {}, "arena_in_vote": {},
             "designs_locked": False, "damage": True, "time": "day", "show_missions": False, "ai_card_note": "",
             "saved_missions": []}
        L.update(lesson or {})
        tools = {k: True for k in kh.TOOL_ORDER}
        tools.update(L.get("tools") or {})
        if "brains" in L and "brains" not in (lesson or {}).get("tools", {}):
            tools["brains"] = bool(L["brains"])
        L["tools"] = tools
        return L

    def start_monitor(self):
        """The graphics monitor (engine.gfx_tiers): turns the graphics down if frames are missed. A window with the
        server on this same computer (a laptop test) shares the GPU with it: its missed frames say nothing worth saving."""
        if self.gfx_monitor is not None:
            return
        try:
            sun = kart_gfx._state.get("sun")
            self.gfx_monitor = gfx_tiers.Monitor(SETTINGS_DIR, self.gfx_tier, override=None if args.gfx == "auto" else args.gfx,
                                                 pipeline=self.pipeline, lights=[sun] if sun is not None else [],
                                                 render=self.render, on_note=self.banner_note,
                                                 judge=OFFLINE or not LOCAL, tiers=gfx_tiers.TIERS).start(self)
        except Exception as e:
            print(f"No graphics monitor: {e!r}", flush=True)

    # ---------- offline: the race on this laptop ----------
    def start_offline(self):
        """No server: this laptop runs the race, with the garage and settings on the side panel."""
        self.common_start()
        self.started = True
        self.my_name = name or "Driver"
        self.lesson = self.fill_lesson({"track": args.track, "laps": args.laps or 3, "cpu_karts": args.cpu,
                                        "cpu_level": args.level})
        self.rules = kh.default_rules()
        self.design = sim.default_design(self.my_name)
        saved = SETTINGS.get("kart_design")
        if isinstance(saved, dict):
            self.design.update({k: saved[k] for k in list(sim.STATS) + ["colour"] if k in saved})
        self.design = parse_stats(args.stats, self.design)
        self.draft = copy.deepcopy(self.design)
        self.set_track(args.track, args.laps)
        self.my_id = 0
        self.local = sim.Race(self.track, SCHEMA, args.laps)
        self.local.set_damage(self.lesson.get("damage", True))  # (CHANGE 158: real damage offline too)
        self.local.items = kart_items.Items(self.local)  # (CHANGE 159: power-ups offline too, every one on)
        self.local.add(0, self.design)
        self.local_cpu = {}
        for n in range(max(0, min(7, args.cpu))):
            kid = n + 1
            self.local.add(kid, sim.default_design(cpu_brains.name_for(args.level, n), COLOURS[kid % len(COLOURS)]))
            self.local_cpu[kid] = args.level
        self.local_brain = None
        if args.brain:
            import kart_brain
            with open(args.brain, encoding="utf-8") as f:
                fn, fname = kart_brain.load_brain(f.read(), "me")
            self.local_brain = kart_brain.Autopilot(fn, fname)
        self.key("enter", self.local_start)
        self.key("g", self.local.to_grid)
        self.sync_designs(self.local.designs)
        self.hud()
        self.start_monitor()
        self.tab = args.tab or ("garage" if args.panel else None)
        self.show_code = bool(args.show_code)
        self.rebuild_panels()
        if args.autostart:
            self.local_start()
        else:
            self.banner_note("Press Enter to start the race", 8)

    def local_start(self):
        self.local.start()

    # ---------- the learner's settings, kept with their profile ----------
    def restore_prefs(self, prefs):
        """A learner's camera view and half-typed AI card, from their profile."""
        self.cam_rig.restore(prefs.get("camera", {}))
        self.restore_hud_prefs(prefs)  # (the code panel's place and size, text size, look, the wheel)
        for k in kh.CARD_FIELDS:
            if prefs.get("card", {}).get(k):
                self.entry_text[f"card_{k}"] = str(prefs["card"][k])[:2000]
        if prefs.get("card_target") in AI_TARGETS and prefs["card_target"] != "game":
            self.card_target = prefs["card_target"]
        self.prefs_sent = json.dumps(self.gather_prefs(), sort_keys=True)

    def gather_prefs(self):
        card = {}
        for k in kh.CARD_FIELDS:
            e = self.entries.get(f"card_{k}")
            card[k] = e.get() if e is not None else self.entry_text.get(f"card_{k}", "")
        return {"camera": self.cam_rig.settings(), "card": card, "card_target": self.card_target, **self.hud_prefs()}

    # ---------- keys ----------
    def key(self, key, fn, *extra):
        """A game shortcut key. It does nothing while you are typing in a text box."""
        self.accept(key, lambda: None if self.typing or not self.started else fn(*extra))

    def key_down(self, which, down):
        self.keys_down[which] = down

    def tab_or_panel(self):
        """Tab: while typing, on to the next text box; otherwise the side panel opens or closes (I does too)."""
        if self.typing or not self.started:
            self.tab_key(1)
        else:
            self.toggle_panel()

    def tab_key(self, step):
        """Tab moves the typing from one text box to the next (Shift+Tab: to the one before), on the login screen
        and every other screen; from the last box it goes round to the first."""
        keys = [k for k in self.entries if not k.startswith("code_")]
        if not keys or str(self.typing or "").startswith("code_"):
            return
        if self.typing in keys:
            to = keys[(keys.index(self.typing) + step) % len(keys)]
        elif self.started:
            return
        else:
            to = keys[0 if step > 0 else -1]  # the login screen, with no box chosen yet
        was = self.entries.get(self.typing)
        if was is not None:
            was["focus"] = 0
        e = self.entries[to]
        e["focus"] = 1
        e.setCursorPosition(len(e.get()))
        self.typing = to

    # ---------- fixed parts of the screen ----------
    def hud(self):
        """The text over the track that stays put: the title, the key list and the banner (always the dark look)."""
        self.overlay = kh.Overlay(self, TEACHER, self.my_name, kh.keys_text(TEACHER))
        self.panel_floor = -0.94  # (the side panel stops above the key list: CHANGE 104)
        self.help = self.overlay.help

    def toggle_help(self):
        hidden = self.overlay.toggle_help()
        self.panel_floor = -1.0 if hidden else -0.94  # (CHANGE 104)
        self.place_panel()

    def toggle_mute(self):
        self.muted = not self.muted
        self.snd.on = not self.muted and not args.offscreen
        self.banner_note("Sound off on this computer (N)" if self.muted else "Sound on (N)", 2)

    def obey_gfx_max(self):
        """The teacher's class maximum for the graphics (CHANGE 139, engine.gfx_tiers): a learner's window only."""
        cap = (self.lesson or {}).get("gfx_max")
        if TEACHER or getattr(self, "gfx_max_seen", "?") == cap:
            return
        self.gfx_max_seen = cap
        note = gfx_tiers.obey_class_max(SETTINGS_DIR, cap, getattr(self, "gfx_monitor", None),
                                        getattr(self, "gfx_tier", None), gfx_tiers.TIERS)
        if note:
            self.banner_note(note, 6)

    def on_line_colour(self, colour):
        """Mesh and lines: the learner's line colour, at once (CHANGE 144)."""
        kart_gfx.set_line_colour(colour)

    def banner_note(self, text, secs=3, big=False):
        """Words over the track for a few seconds. big: a restart warning's size."""
        self.note_until = time.perf_counter() + secs
        self.note_text, self.note_big = text, big

    show_note = banner_note

    def check_code(self, welcome):
        """The server runs the game's current code: if this window's code is different (a mod was switched, or
        the server restarted with changes), reopen with the new code. Returns True if the window is reopening."""
        if not welcome.get("code") or welcome["code"] == kart_version.CODE:
            return False
        if not kart_version.FROZEN and not LOCAL:  # the teacher's own windows on the class server run the teacher's code
            return False
        if os.environ.get("KARTLAB_REOPENED") == welcome["code"] or args.offscreen:  # tried already: don't loop
            self.taskMgr.doMethodLater(1, lambda t: self.banner_note(
                "This window's game code doesn't match the server's. Restart the server (teacher: Controls), then "
                "reopen this window.", 3600), "code note")
            return False
        self.restart_window(reopen_for=welcome["code"])
        return True

    def restart_window(self, reopen_for=None, argv=None, try_env=None):
        """Reopen this window (to load code changes), logged in as the same person."""
        env = dict(os.environ, KARTLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        if reopen_for:  # remember which server code this reopen was for, so it only happens once
            env["KARTLAB_REOPENED"] = reopen_for
        else:
            env.pop("KARTLAB_REOPENED", None)
        if try_env is None and TRY and argv is None:
            try_env = json.dumps(TRY)
        if try_env:
            env["KARTLAB_TRY"] = try_env
        else:
            env.pop("KARTLAB_TRY", None)
        argv = [a for a in (sys.argv[1:] if argv is None else argv)]
        for flag in ("--name", "--password"):  # the login travels in KARTLAB_LOGIN instead
            while flag in argv:
                i = argv.index(flag)
                del argv[i:i + 2]
        if TEACHER:
            argv += ["--name", name]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        program = [sys.executable] if kart_version.FROZEN else [sys.executable, os.path.abspath(__file__)]
        log_dir = SETTINGS_DIR if kart_version.FROZEN else HERE
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "window.log"), "a") as log:
            child = subprocess.Popen(program + argv, cwd=os.getcwd() if kart_version.FROZEN else HERE, env=env,
                                     stdout=log, stderr=log, creationflags=flags)
        if os.environ.get("CLUBCODERS_WINDOW_PID_FILE"):  # (the app that opened this window follows the new one:
            try:                                          # CHANGE 154)
                with open(os.environ["CLUBCODERS_WINDOW_PID_FILE"], "w", encoding="utf-8") as f:
                    f.write(str(child.pid))
            except OSError:
                pass
        os._exit(0)

    def toggle_code(self):
        self.show_code = not self.show_code
        if self.show_code and not TEACHER and not OFFLINE:
            send({"type": "code_viewed"})
        self.rebuild_panels()

    def open_tab(self, tab):
        self.tab = None if self.tab == tab else tab
        self.code_shown = None
        self.rebuild_panels()

    def my_tabs(self):
        return kh.OFFLINE_TABS if OFFLINE else kh.TEACHER_TABS if TEACHER else kh.LEARNER_TABS

    def rebuild_panels(self, from_game=False):
        """Redraw the side panels. A redraw caused by the game (a new lap, new mission results) waits while you're
        typing, so the text box keeps the keyboard."""
        if not self.started:
            return
        if from_game and self.typing:
            self.pending_rebuild = True
            return
        self.pending_rebuild = False
        self.keep_typing()
        self.close_code_editor()
        self.hide_tip()
        if self.prompt_view is not None:
            self.prompt_view.destroy()
            self.prompt_view = None
        for p in (self.panel, self.code_panel):
            if p is not None:
                p.destroy()
        self.panel = self.code_panel = self.panel_body = None
        self.panel_bar = []
        if self.tab:
            f = self.panel = DirectFrame(frameColor=PANEL, frameSize=(0.78, 1.76, -0.93, 0.97))
            tabs = self.my_tabs() + ([] if OFFLINE else hud.extra_tabs(TEACHER))  # (+ a mod's own tabs)
            f, y0 = self.draw_header(f, tabs, self.open_tab, self.tab,
                                     lambda key, text: self.warnings_tab_text(text) if key == "warnings" else text)
            builders = {"garage": self.build_garage, "teacher": self.build_teacher_panel, "missions": self.build_missions,
                        "ai": self.build_ai_card, "outcomes": self.build_outcomes, "cards": self.build_cards,
                        "card": self.build_card, "learners": self.build_learner_view, "changes": self.build_changes,
                        "accounts": self.build_accounts, "races": self.build_races, "settings": self.build_settings,
                        "mods": self.build_mods, "warnings": self.build_warnings, "limits": self.build_limits}
            if self.tab in builders:
                builders[self.tab](f, y0)
            elif hud.extra_builder(self.tab) is not None:
                hud.extra_builder(self.tab)(self, f, y0)
            self.place_panel()
        if self.show_code and (TEACHER or OFFLINE or self.lesson["tools"].get("code_view", True)):
            self.build_code_panel()
        if self.typing == "code" and self.code_editor is not None:  # redrawn while typing in the code: carry on
            self.code_editor.focused = True
            self.code_editor.refresh()
        elif self.typing and self.typing not in self.entries:  # the box being typed in has gone
            self.typing = None
        if self.screen is not None:  # (the racing screen's right-hand readouts move in from under the panel)
            self.screen.set_inset(0.98 * self.text_scale() + 0.02 if self.tab else 0.0)

    # ---------- which kart the garage and code panel are editing ----------
    def viewing(self):
        """The learner the teacher is looking at in the Learner view (or None)."""
        return self.view_name if TEACHER and self.tab == "learners" and self.view_tab == "garage" else None

    def cur(self):
        """The design being edited: your own, or (teacher's Learner view) the learner's."""
        who = self.viewing()
        if who:
            if who not in self.view_drafts:
                d = next((c["design"] for c in self.class_list if c["name"] == who), self.draft)
                self.view_drafts[who] = copy.deepcopy(d)  # ("All learners" starts from the teacher's own: CHANGE 85)
            return self.view_drafts[who]
        return self.draft

    def tools(self):
        if TEACHER or OFFLINE:
            return {k: True for k in self.lesson["tools"]}
        return self.lesson["tools"]

    def limits(self):
        """The ranges the design being edited is held to: the learners' (the teacher sets them in the Limits tab),
        or the widest ones for the teacher's own kart."""
        if (TEACHER and not self.viewing()) or OFFLINE:
            return self.full_limits()
        return self.lesson.get("limits") or self.default_limits()

    def pretty(self, key):
        return kh.PRETTY.get(key, key.replace("_", " ").capitalize())

    # ---------- garage: design your kart ----------
    def build_garage(self, f, y, view=None):
        """view: the teacher's Learner view of this learner. The teacher sees every control, with a tick box on
        each showing (and setting) whether the learner can see and change it. The tables are the engine's, from the
        kart's schema."""
        tools, d = self.tools(), self.cur()
        seen = self.lesson["tools"]

        def shown_box(tool, yy):
            if view:
                check(f, " learner sees", 1.52, yy, seen.get(tool), lambda v, t=tool: self.set_lesson({"tools": {t: bool(v)}}),
                      0.022)
        label(f, ("EVERY LEARNER'S KART" if view == self.ALL_LEARNERS else f"{view.upper()}'S KART") if view else
              ("MY KART" if TEACHER else "GARAGE  -  your kart as variables"), 0.82, y, 0.034 if view else 0.038, YELLOW)
        y -= 0.05
        label(f, f"{self.limits()['points_total']} points between top speed, acceleration and grip: every choice "
                 "is a trade-off.", 0.82, y, 0.021, GREY)
        y -= 0.05
        limits = self.limits()
        y = garage.draw(self, f, y, d, self.schema, self.code_ctx(d), tools, limits, view, shown_box,
                        teacher=TEACHER and not view)
        self.stats_text = None
        if tools.get("stats_readout", True):
            self.stats_text = label(f, "", 0.82, y - 0.005, 0.022, GREEN)
            self.update_stats_text()
            shown_box("stats_readout", y)
            y -= 0.1
        if view != self.CPU_VIEW and not OFFLINE:
            y = self.build_slots(f, y, view)  # (CHANGE 83 to 87)
        self.garage_bottom = y - 0.1
        if view:
            button(f, f"BUILD FOR {view.upper()}", 1.27, y, self.send_design_for, [view], 0.034, (0.15, 0.55, 0.25, 1))
        else:
            button(f, "BUILD MY KART", 1.27, y, self.send_design, None, 0.038, (0.15, 0.55, 0.25, 1))
        self.garage_msg = label(f, self.status_msg[0] if not view else "", 0.82, y - 0.06, 0.024, self.status_msg[1],
                                wrap=40)
        if self.lesson.get("designs_locked") and not TEACHER:
            label(f, "Designs are locked by the teacher", 0.82, y - 0.12, 0.026, RED)

    def name_key(self):
        """The kart-name box: one for your kart, one for each learner in the Learner view."""
        return "name_" + (self.viewing() or "me")

    def update_stats_text(self):
        if not getattr(self, "stats_text", None):
            return
        try:
            self.stats_text.setText(kh.stats_text(self.cur()))
        except Exception:
            return

    def set_colour(self, colour):
        self.cur()["colour"] = list(colour)
        self.code_shown = None
        self.rebuild_panels()

    def change_points(self, stat, delta):
        d = self.cur()
        lo, hi = self.limits()["points"].get(stat, [self.rules["stat_min"], self.rules["stat_max"]])
        d[stat] = max(lo, min(hi, int(d.get(stat, lo)) + delta))
        self.code_shown = None
        self.rebuild_panels()

    def slider_moved(self, k):  # (the kart has no percentage settings; the engine's garage may still ask)
        s, text = self.sliders[k]
        self.cur()[k] = int(round(s["value"]))
        text.setText(f"{self.cur()[k]:g}%")

    def send_design(self):
        """BUILD MY KART: the design goes to the server (which checks it, tells the teaching layer and sends the
        result); offline it is used at once."""
        if self.name_key() in self.entries and self.tools().get("name_and_colour", True):
            self.draft["name"] = self.entries[self.name_key()].get()[:12]
        if OFFLINE:
            problems = kh.check_design(self.draft, self.limits())
            if problems:
                self.status_msg = ("Not built: " + "; ".join(problems[:3]), RED)
            else:
                self.design = sim.fit_design(copy.deepcopy(self.draft))
                self.draft = copy.deepcopy(self.design)
                remember("kart_design", {k: self.design[k] for k in list(sim.STATS) + ["colour"]})
                self.local.designs[0] = self.design
                self.local.stats[0] = sim.stats_of(self.design)
                self.sync_designs(self.local.designs)
                self.status_msg = ("Built!", GREEN)
                self.code_shown = None
            self.rebuild_panels()
            return
        send({"type": "design", "design": self.draft, "code": bool(self.code_changed or self.code_hack)})
        self.status_msg = ("Building...", GREY)
        if self.tab == "garage" and getattr(self, "garage_msg", None) is not None:
            self.garage_msg.setText("Building...")

    def send_design_for(self, learner):
        d = self.cur()
        if self.name_key() in self.entries:
            d["name"] = self.entries[self.name_key()].get()[:12]
        if learner == self.ALL_LEARNERS:  # (CHANGE 85)
            send({"type": "design_for_all", "design": d})
            return
        send({"type": "design_for", "learner": learner, "design": d})
        self.garage_msg.setText(f"Building for {learner}...")

    # ---------- code view: your kart as Python code, which you can edit ----------
    def code_ctx(self, d=None):
        """What the schema needs to know from this window: the title, the points total, the rules and the design."""
        from types import SimpleNamespace
        who = self.viewing()
        return SimpleNamespace(title=f"{who.upper()}'S KART" if who else "MY KART",
                               points_total=self.limits()["points_total"], design=d if d is not None else self.cur(),
                               rules=self.rules)

    def code_lines(self, d):
        """The kart as Python: one variable a line, with its type and a comment, in the garage's groups."""
        return schema.code_lines(self.schema, d, self.code_ctx(d))

    def build_code_panel(self):
        """The kart as Python code, in a small editor (the engine's): click anywhere in it to type there, the
        words are coloured as an IDE colours them, long code scrolls, and the panel can be moved and resized."""
        who = self.viewing()
        d = self.cur()
        self.code_size = self.code_fit(*self.code_size)
        self.code_at = self.code_place(*self.code_at)
        f, (left, right, bottom, top) = self.code_panel_top("kart", who)  # (CHANGE 143: as the browser's)
        st, fresh = self.code_state, self.code_lines(d)
        if self.code_shown is None or st["lines"] == self.code_shown:  # not edited: the kart as it is now
            st["lines"][:] = fresh
            self.code_shown = list(fresh)
        self.code_editor = code_editor.CodeEditor(self, f, st, -0.845, 0.21, right - left - 0.03, self.code_rows(),
                                                  0.024 * self.text_scale(), on_enter=self.apply_code,
                                                  on_focus=self.type_code)
        self.code_more = label(f, "", right - 0.02, 0.243, 0.019, code_editor.DIM, TextNode.ARight)
        self.code_editor.on_scroll = self.show_code_more
        self.show_code_more()
        button(f, "APPLY CODE", -0.64, bottom + 0.178, self.apply_code, None, 0.03, (0.15, 0.55, 0.25, 1))
        button(f, "RESET CODE", -0.36, bottom + 0.178, self.reset_code, None, 0.03)
        button(f, f"BUILD FOR {who.upper()}" if who else "BUILD MY KART", -0.64 if not who else -0.5, bottom + 0.112,
               self.build_from_code, None, 0.03, (0.15, 0.55, 0.25, 1))  # (under APPLY CODE: apply, then build)
        label(f, self.code_msg[0], -0.83, bottom + 0.055, 0.021, self.code_msg[1], wrap=39 + self.code_size[0] / 0.021)
        grip = DirectFrame(parent=f, frameColor=(0.35, 0.4, 0.5, 1), state=DGG.NORMAL,
                           frameSize=(right - 0.045, right, bottom, bottom + 0.045))
        grip.bind(DGG.B1PRESS, self.code_resize_start)  # (its corner is a grip: drag it to resize)
        label(f, "drag to resize", right - 0.055, bottom + 0.012, 0.015, GREY, TextNode.ARight)

    def show_code_more(self):
        """Under the code: how much of it is out of sight (it scrolls with the mouse wheel or the cursor)."""
        above, below = self.code_editor.hidden()
        self.code_more.setText("" if not (above or below) else f"{above} lines above, {below} below")

    def close_code_editor(self):
        if self.code_editor is not None:
            self.code_editor.destroy()
            self.code_editor = None

    def refresh_code_panel(self):
        self.close_code_editor()
        if self.code_panel is not None:
            self.code_panel.destroy()
        self.build_code_panel()
        if self.typing == "code":
            self.code_editor.focused = True
            self.code_editor.refresh()

    def reset_code(self):
        """RESET CODE: the code goes back to the kart as it is now. Only the code on screen changes."""
        self.code_state["lines"][:] = self.code_lines(self.cur())
        self.code_state["cursor"][:], self.code_state["scroll"] = [0, 0], 0
        self.code_shown = list(self.code_state["lines"])
        self.code_msg = ("The code is back to your kart as it is. Press APPLY CODE or BUILD to use it.", GREY)
        self.refresh_code_panel()

    def build_from_code(self):
        """BUILD MY KART in the code panel: read the code as APPLY CODE does, then build the kart from it."""
        if not self.apply_code():
            return
        who = self.viewing()
        if who:
            self.send_design_for(who)
        else:
            self.send_design()

    def outside_limits(self, values):
        """CHANGE 91: each value in the code stays within the teacher's limits; the points total is not checked here."""
        limits, out = self.limits(), []
        for var in self.schema:
            if var.name not in values or var.group not in ("points", "settings"):
                continue
            rng = limits.get(var.group, {}).get(var.path[-1])
            v = values[var.name]
            if not rng or not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if v > rng[1]:
                out.append(f"value too high for {var.name} (most allowed: {rng[1]:g})")
            elif v < rng[0]:
                out.append(f"value too low for {var.name} (least allowed: {rng[0]:g})")
        return out

    def apply_code(self):
        """Read the edited code as data (never run it), and change the design to match. True if all of it was used.
        Everything in the code can be changed, even what this mission's garage hides (hidden: those values). The
        class server holds the kart to the rules all the same, and tells the teacher what was changed."""
        text = "\n".join(self.code_state["lines"])
        d = self.cur()
        ctx = self.code_ctx(d)
        try:
            values = schema.parse_code(text, self.schema, ctx)
        except schema.ParseError as e:
            self.code_msg = (f"Line {e.lineno}: {e.message}", RED)
            if e.lineno:  # the cursor goes to the line with the mistake
                self.code_state["cursor"][:] = [e.lineno - 1, 0]
                self.code_state["scroll"] = max(0, e.lineno - self.code_rows())
            self.refresh_code_panel()
            return
        tools = self.tools()

        def allowed(var, value):  # (what this mission's garage lets the learner change)
            return bool(tools.get(var.tool, True))
        refused = self.outside_limits(values)  # (CHANGE 91: a value past the teacher's limits is refused outright)
        if refused:
            self.code_msg = ("Unable to compile: " + "; ".join(refused[:2]), RED)
            self.code_shown = None
            self.rebuild_panels()
            return False
        changed, hidden, problems = schema.apply_values(self.schema, d, values, ctx, allowed)
        if changed and not self.viewing():
            self.code_changed = True  # (the next build is sent as the code's: Mission 1, hack the code)
        if hidden and not self.viewing():
            self.code_hack = True
        if "kart_name" in changed:
            self.entry_text.pop(self.name_key(), None)
            if self.name_key() in self.entries:
                self.entries[self.name_key()].enterText(d["name"])
        problems += kh.check_design(d, self.limits())
        if problems:
            self.code_msg = ("Applied, but: " + "; ".join(problems[:3]), ORANGE)
        else:
            self.code_msg = ("Applied: the garage shows your changes. Press BUILD to use them.", GREEN)
        self.code_shown = None
        self.rebuild_panels()
        return not problems

    # ---------- missions (learner) ----------
    def build_missions(self, f, y, m=None, preview=False):
        """The engine's Mission tab, with the kart's own row under it: the lap time a learner predicts before a
        race (Mission 2: predict, test, compare)."""
        hud.HudKit.build_missions(self, f, y, m, preview)
        m = m or self.missions
        if not m or preview:
            return
        if m.get("lesson") == 2 or m.get("prediction") is not None:
            y = self.body_bottom(y) - 0.07
            label(f, "My predicted lap time", 0.82, y, 0.028, YELLOW)
            y -= 0.045
            have = m.get("prediction")
            label(f, "Look at your kart's stats, then predict one lap in seconds. Race, then compare.", 0.82, y,
                  0.021, GREY, wrap=46)
            y -= 0.055
            self.entry(f, "predict_lap", 0.84, y, 6, initial="" if have is None else f"{have:g}", scale=0.03)
            label(f, "seconds", 1.1, y, 0.024, GREY)
            button(f, "Save", 1.3, y + 0.008, self.send_prediction, None, 0.026, (0.15, 0.55, 0.25, 1))
            if have is not None:
                best = f"   your best lap so far: {self.best_lap:.1f} s" if self.best_lap else ""
                label(f, f"Predicted: {have:g} s{best}", 0.84, y - 0.05, 0.023, GREEN)

    def send_prediction(self):
        text = self.entries["predict_lap"].get().strip() if "predict_lap" in self.entries else ""
        try:
            value = float(text)
        except ValueError:
            self.banner_note("Type the lap time you predict, in seconds (for example 42)", 4)
            return
        send({"type": "prediction", "value": value})

    def build_card(self, f, y):
        """The learner's own card: the outcomes they've shown so far, and what they did each session."""
        card = (self.missions or {}).get("card")
        label(f, f"MY CARD  -  {name}", 0.82, y, 0.036, YELLOW)
        if not card:
            label(f, "Waiting for your card...", 0.82, y - 0.06, 0.028, GREY)
            return
        y -= 0.06
        label(f, "Outcomes I've shown so far", 0.82, y, 0.03, YELLOW)
        y -= 0.045
        shown = [(card["outcome_names"].get(o, o), n) for o, n in card["outcomes"].items() if n]
        if not shown:
            label(f, "None yet: complete a mission to start your card.", 0.84, y, 0.026, GREY)
            y -= 0.04
        for i, (title_, n) in enumerate(shown):
            label(f, f"{title_}: {n}", 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.038, 0.026, GREEN)
        y -= 0.038 * ((len(shown) + 1) // 2) + 0.02
        label(f, "What I did", 0.82, y, 0.03, YELLOW)
        y -= 0.045
        for day in card["history"]:
            label(f, day["date"], 0.84, y, 0.028, WHITE)
            y -= 0.038
            for mm in day["missions"]:
                label(f, f"Mission {mm['lesson']}: {mm['title']}", 0.88, y, 0.025, GREY)
                label(f, " ".join(mm["outcomes"]), 1.74, y, 0.022, BLUE, TextNode.ARight)
                y -= 0.034
                if mm.get("detail"):  # (CHANGE 96: the change itself, as the objective's check recorded it)
                    t = label(f, mm["detail"], 0.92, y, 0.022, GREEN, wrap=44)
                    y -= 0.028 * t.textNode.getNumRows() + 0.008
            y -= 0.012
        if not card["history"]:
            label(f, "Nothing yet.", 0.84, y, 0.026, GREY)

    def brains_on(self):
        """CHANGE 99: the teacher's Autopilot tick in Controls. Off, U and P do nothing for learners."""
        if TEACHER or OFFLINE or self.lesson.get("tools", {}).get("brains", True):
            return True
        self.banner_note("Brains aren't switched on for this mission yet.", 3)
        return False

    def autopilot_key(self):
        if OFFLINE:
            return self.banner_note("Offline: start the window with --brain brains/my_brain.py to drive with a brain", 5)
        if not self.brains_on():
            return
        if not self.has_brain():
            return self.banner_note("Upload a brain first (U)", 3)
        send({"type": "autopilot", "on": not self.autopilot})

    def has_brain(self):
        mine = self.race["brains"].get(self.my_name) if self.race.get("brains") else None
        if mine is not None:
            return bool(mine.get("has"))
        return bool((self.missions or {}).get("brain"))

    def upload_brain(self):
        if OFFLINE:
            return self.banner_note("Offline: start the window with --brain brains/my_brain.py", 5)
        if not self.brains_on():
            return
        for path in (os.path.join(BRAINS, f"{name}.py"), os.path.join(BRAINS, "my_brain.py")):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    send({"type": "brain", "source": fh.read()})
                self.banner_note(f"Uploading {os.path.basename(path)}...")
                return
        self.banner_note(f"No brain file: make {os.path.join(BRAINS, 'my_brain.py')} first", 5)

    # ---------- AI request card (learner) ----------
    def build_ai_card(self, f, y, edit=False):
        """edit: the teacher's copy (AI cards tab, "The learners' card"). It is the card as the learners see it,
        with a box for the teacher's own instructions: what is typed there is shown on every learner's card."""
        label(f, "AI REQUEST CARD" + ("  as the learners see it" if edit else ""), 0.82, y, 0.036 if edit else 0.04,
              YELLOW)
        if edit:
            button(f, "Back to the requests", 1.62, y + 0.008, self.show_cards, [None], 0.022)
        y -= 0.055
        label(f, kh.AI_RULES, 0.82, y, 0.023, BLUE, wrap=42)
        y -= 0.12
        note = str(self.lesson.get("ai_card_note") or "").strip()
        if edit:
            label(f, "From your teacher:   (type what the learners should read here)", 0.82, y, 0.024, ORANGE)
            self.entry(f, "card_note", 0.84, y - 0.042, 30, 4, initial=note, scale=0.026)
            y -= 0.165
            button(f, "SHOW THIS ON THE LEARNERS' CARDS", 1.27, y, self.send_card_note, None, 0.028, (0.15, 0.45, 0.65, 1))
            self.card_note_text = label(f, "On their cards now." if note else "Nothing from you is on their cards yet.",
                                        0.82, y - 0.055, 0.022, GREY)
            y -= 0.1
        elif note:
            words = label(f, "From your teacher:  " + note, 0.82, y, 0.025, ORANGE, wrap=36)
            y -= 0.03 * max(1, words.textNode.getNumRows()) + 0.025
        label(f, "What should change?", 0.82, y, 0.027)
        shown = [(k, t) for k, t in AI_TARGETS.items() if k != "game"]
        for i, (key, text) in enumerate(shown):
            button(f, text, 1.19 + i * 0.2, y + 0.008, self.set_card_target, [key], 0.025,
                   ON if key == self.card_target else OFF)
        y -= 0.07
        for key, text in (("goal", "My idea"), ("variables", "Variables and values it needs"),
                          ("test", "How I will test it"), ("predict", "What I predict will happen")):
            rows = 6 if key in ("goal", "test") else 4  # (room to explain, every box wrapping: CHANGE 93)
            label(f, text, 0.82, y, 0.027)
            if edit:  # (the teacher's copy: the boxes are only drawn)
                DirectFrame(parent=f, frameColor=(0.15, 0.17, 0.22, 1), pos=(0.84, 0, y - 0.045),
                            frameSize=(0, 0.78, -0.009 - (rows - 1) * 0.026, 0.024))
            else:
                self.textbox(f, f"card_{key}", 0.84, y - 0.02, 0.8, rows, scale=0.024)  # (wraps and scrolls)
            y -= 0.075 + rows * 0.036  # (the box's height)
        for key, text in (("privacy", "No personal information (names, school, email, address)"),
                          ("review", "I will review and test the AI's code"),
                          ("credit", "I will say where AI helped")):
            check(f, text, 0.84, y, self.card_checks[key], lambda v, k=key: self.card_checks.__setitem__(k, bool(v)), 0.026)
            y -= 0.045
        if not edit:
            button(f, "SEND TO THE TEACHER", 1.27, y - 0.01, self.send_card, None, 0.036, (0.15, 0.45, 0.65, 1))
        y -= 0.07
        self.card_text = label(f, self.card_msg[0], 0.82, y, 0.024, self.card_msg[1], wrap=40)
        y -= 0.1
        self.card_list(f, y, (self.missions or {}).get("cards", []), review=True)

    def card_list(self, f, y, cards, review=False):
        if cards:
            label(f, "Requests", 0.82, y, 0.028, YELLOW)
            y -= 0.045
        for c in cards[-3:]:
            label(f, f"#{c['id']} {c['status'].upper()}: {c['card']['goal'][:40]}", 0.84, y, 0.024,
                  GREEN if c["status"] in ("ready", "reviewed") else GREY)
            y -= 0.04
            if c.get("note"):
                label(f, f"Teacher: {c['note']}", 0.86, y, 0.022, BLUE, wrap=40)
                y -= 0.04
            if review and c["status"] == "ready":
                self.build_review(f, y, c)
                return

    def set_card_target(self, key):
        self.card_target = key
        self.rebuild_panels()

    def send_card(self):
        card = {k: self.entries[f"card_{k}"].get() for k in kh.CARD_FIELDS}
        self.stop_typing()
        self.card_msg = ("Sending...", GREY)
        if getattr(self, "card_text", None) is not None:
            self.card_text.setText("Sending...")
        send({"type": "ai_card", "card": card | self.card_checks | {"target": self.card_target}})

    def build_review(self, f, y, c):
        label(f, c.get("acknowledgement", ""), 0.84, y, 0.022, BLUE)
        y -= 0.04
        for key, q in self.missions["review_questions"].items():
            label(f, q, 0.84, y, 0.022, WHITE, wrap=44)
            self.entry(f, f"review_{key}", 0.84, y - 0.04, 30, 1, scale=0.024)
            y -= 0.085
        button(f, "SUBMIT MY REVIEW", 1.27, max(y, -0.88), self.send_review, [c["id"]], 0.032, (0.15, 0.55, 0.25, 1))

    def send_review(self, cid):
        answers = {k: self.entries[f"review_{k}"].get() for k in self.missions["review_questions"]}
        send({"type": "ai_review", "id": cid, "answers": answers})

    # ---------- teacher: controls ----------
    def build_teacher_panel(self, f, y):
        L = self.lesson
        label(f, "Mission", 0.82, y, 0.03, YELLOW)
        for i, n in enumerate(LESSON_NUMBERS[:5]):
            button(f, str(n), 1.0 + i * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.028,
                   ON if L.get("lesson_number") == n else OFF)
        saved = (L.get("saved_missions") or [])  # (CHANGE 58 and 59: saved per mission, and brought back)
        button(f, "Save settings", 1.5, y + 0.008, send, [{"type": "save_lesson"}], 0.024)
        button(f, "Restore", 1.68, y + 0.008, send, [{"type": "restore_lesson"}], 0.024)
        if saved:
            label(f, "saved settings: mission " + ", ".join(str(n) for n in saved), 1.74, y - 0.037, 0.015, GREY,
                  TextNode.ARight)
        y -= 0.06
        y = self.race_controls(f, y)
        check(f, "Lock designs", 0.84, y, L.get("designs_locked"), lambda v: self.set_lesson({"designs_locked": bool(v)}),
              0.026)
        if "teacher_kart" in L:
            check(f, "My kart in the race", 1.3, y, L.get("teacher_kart"),
                  lambda v: self.set_lesson({"teacher_kart": bool(v)}), 0.026)
        y -= 0.05
        # (CHANGE 158) real damage: hits slow a kart till it's mended (off mends every kart)
        check(f, "Damage (hits slow a kart till it's mended)", 0.84, y, L.get("damage", True),
              lambda v: self.set_lesson({"damage": bool(v)}), 0.026)
        y -= 0.05
        # (CHANGE 172) the race's time of day: everyone's window and page relights; headlights at dusk and night
        label(f, "Time of day", 0.82, y, 0.028, YELLOW)
        for i, (key, text) in enumerate((("day", "Day"), ("dusk", "Dusk"), ("night", "Night"))):
            button(f, text, 1.08 + i * 0.16, y + 0.008, lambda k=key: self.set_lesson({"time": k}), (), 0.024,
                   ON if L.get("time", "day") == key else OFF)
        y -= 0.05
        # (CHANGE 159) the power-ups the item boxes give, each on or off
        label(f, "Power-ups", 0.82, y, 0.028, YELLOW)
        items = L.get("items") if isinstance(L.get("items"), dict) else {}
        for i, (name, text) in enumerate(ITEM_TEXT):
            check(f, text, 1.02 + (i % 3) * 0.26, y - (i // 3) * 0.043, items.get(name, True),
                  lambda v, n=name: self.set_lesson({"items": {**self.items_now(), n: bool(v)}}),
                  0.024)
        y -= 0.1
        items = self.stage_items()
        if items:
            label(f, "Track items", 0.82, y, 0.028, YELLOW)
            y -= 0.045
            for i, (key, text, on, switch) in enumerate(items):
                check(f, text, 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.043, on, switch, 0.026)
            y -= 0.043 * ((len(items) + 1) // 2) + 0.01
        label(f, "User mods  (learners' ideas: on or off at any time)", 0.82, y, 0.028, YELLOW)
        y -= 0.043
        mods_on = L.get("user_mods", {})
        if not self.user_mods:
            label(f, "None yet. An AI card sent as 'The whole game' can be made a switchable User Mod.", 0.84, y + 0.01,
                  0.019, GREY)
        for i, (key, (mod_name, _)) in enumerate(self.user_mods.items()):
            check(f, " " + mod_name, 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.043, mods_on.get(key),
                  lambda v, k=key: self.set_lesson({"user_mods": {k: bool(v)}}), 0.026)
        y -= 0.043 * max(1, (len(self.user_mods) + 1) // 2)
        label(f, "Learners can see and change  (or use the Learners tab)", 0.82, y, 0.026, YELLOW)
        y -= 0.045
        keys = [k for k in kh.TOOL_ORDER if k in L["tools"]] + \
            sorted(k for k, v in L["tools"].items() if k not in kh.TOOL_ORDER and isinstance(v, bool))
        for i, k in enumerate(keys):
            check(f, self.pretty(k), 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.041, L["tools"].get(k, k == "brains"),
                  lambda v, k=k: self.set_lesson({"tools": {k: bool(v)}}), 0.024)
        y -= 0.041 * ((len(keys) + 1) // 2) + 0.02
        self.restart_row(f, y)

    def race_controls(self, f, y):
        """The race: start it, back to the grid, pause; the track, the laps, the computer karts and their level."""
        L = self.lesson
        practice = L.get("mode", "practice") != "race"
        racing = self.race.get("phase") == sim.FLAGS_RACE
        label(f, "Race", 0.82, y, 0.028, YELLOW)
        button(f, "START A RACE" if practice else "RESTART" if racing else "START RACE", 1.0, y + 0.008, send,
               [{"type": "start"}], 0.026, (0.15, 0.55, 0.25, 1))
        button(f, "TO THE GRID", 1.24, y + 0.008, send, [{"type": "grid"}], 0.026)
        button(f, "Pause", 1.48, y + 0.008, send, [{"type": "pause"}], 0.026, ON if self.race.get("paused") else OFF)
        y -= 0.055
        # CHANGE 143 (as the page's Controls): practice (the track open, laps timed) or race (the teacher starts each)
        label(f, "Mode", 0.84, y, 0.024)
        for i, (mode, text) in enumerate((("practice", "Practice"), ("race", "Race"))):
            button(f, text, 1.0 + i * 0.16, y + 0.008, self.set_lesson, [{"mode": mode}], 0.024,
                   ON if (mode == "practice") == practice else OFF)
        label(f, "Practice: the track is open and laps are timed; START A RACE closes it until GO." if practice else
              "Race: START begins the countdown; TO THE GRID lines everyone up again.", 1.3, y + 0.004, 0.016, GREY,
              wrap=27)
        y -= 0.055
        # ...and a grand prix of 2 to 5 races: points for every race's places, the most at the end is the champion
        t = self.tournament
        label(f, "Grand prix", 0.84, y, 0.024)
        if t is None:
            for i, n in enumerate(range(2, 6)):
                button(f, str(n), 1.03 + i * 0.065, y + 0.008, self.set_gp_races, [n], 0.024,
                       ON if n == self.gp_races else OFF)
            label(f, "races", 1.3, y, 0.021, GREY)
            button(f, "START THE GRAND PRIX", 1.55, y + 0.008, send,
                   [{"type": "tournament", "start": True, "races": self.gp_races}], 0.022, (0.15, 0.55, 0.25, 1))
        else:
            label(f, str(t.get("title") or "running"), 1.03, y, 0.024, BLUE)
            button(f, "END IT", 1.6, y + 0.008, send, [{"type": "tournament", "start": False}], 0.024,
                   (0.6, 0.2, 0.15, 1))
        y -= 0.055
        label(f, "Track", 0.82, y, 0.026)
        for i, t in enumerate(kart_track.TRACKS):
            button(f, kart_track.TRACKS[t]["name"], 1.0 + i * 0.25, y + 0.008, self.set_lesson, [{"track": t}], 0.024,
                   ON if t == L.get("track") else OFF)
        y -= 0.05
        laps = int(L.get("laps", 3))
        label(f, f"Laps {laps}", 0.82, y, 0.026)
        button(f, "-", 1.0, y + 0.008, self.set_lesson, [{"laps": laps - 1}], 0.024)
        button(f, "+", 1.08, y + 0.008, self.set_lesson, [{"laps": laps + 1}], 0.024)
        cpu = int(L.get("cpu_karts", 3))
        label(f, f"Computer karts {cpu}", 1.2, y, 0.026)
        button(f, "-", 1.56, y + 0.008, self.set_lesson, [{"cpu_karts": cpu - 1}], 0.024)
        button(f, "+", 1.64, y + 0.008, self.set_lesson, [{"cpu_karts": cpu + 1}], 0.024)
        y -= 0.05
        level = L.get("cpu_level", "medium")
        label(f, "Their level", 0.84, y, 0.024)
        levels = list(cpu_brains.LEVELS) + (["empty"] if "empty" in str(level) or L.get("cpu_brain_allowed") else [])
        for i, key in enumerate(levels):
            button(f, key.title(), 1.06 + i * 0.16, y + 0.008, self.set_lesson, [{"cpu_level": key}], 0.021,
                   ON if level == key else OFF)
        if level == "empty":
            button(f, "Upload demo brain", 1.64, y + 0.008, self.upload_demo_brain, None, 0.019, (0.15, 0.45, 0.65, 1))
        y -= 0.05
        check(f, "Autopilot (U and P) for learners", 0.84, y, L["tools"].get("brains", True),
              lambda v: self.set_lesson({"tools": {"brains": bool(v)}}), 0.026)
        y -= 0.05
        return y

    def stage_items(self):
        """The track's items, for the Mods tab and Controls: whatever hazards the lesson lists."""
        L = self.lesson
        return [(hz, kh.HAZARD_NAMES.get(hz, hz.replace("_", " ").capitalize()), bool(on),
                 lambda v, k=hz: self.set_lesson({"hazards": {k: bool(v)}}))
                for hz, on in (L.get("hazards") or {}).items()]

    def restart_row(self, f, y):
        """Code changes (from Claude, or rolled back) load when the server and windows restart."""
        label(f, "Code changes" + ("  (waiting: restart to use them)" if self.needs_restart else ""), 0.82, y, 0.026,
              ORANGE if self.needs_restart else YELLOW)
        y -= 0.05
        button(f, "Restart server", 0.95, y, self.restart_server, None, 0.024,
               (0.6, 0.35, 0.1, 1) if self.needs_restart else OFF)
        button(f, "Reopen learners' windows", 1.25, y, send, [{"type": "restart_clients"}], 0.024)
        button(f, "Reopen mine", 1.6, y, self.restart_window, None, 0.024)
        y -= 0.05
        if TRY:
            button(f, "Back to the class", 1.0, y, self.back_to_class, None, 0.024, (0.15, 0.55, 0.25, 1))
            label(f, "Trying this laptop's game: the class can't see it.", 1.2, y - 0.008, 0.021, ORANGE)
        elif not kart_version.FROZEN and not LOCAL:
            button(f, "Try on this laptop", 1.0, y, self.try_here, None, 0.024, (0.15, 0.45, 0.65, 1))
            label(f, "this window, on a test server here (the class sees nothing)", 1.19, y - 0.008, 0.02, GREY)

    def set_gp_races(self, n):
        self.gp_races = max(2, min(5, int(n)))
        self.rebuild_panels()

    def restart_server(self):
        if TRY:  # (nothing would start the test server again: a new try loads new code)
            return self.banner_note("You are trying this on the laptop: go Back to the class, then Try again, to "
                                    "load new code.", 8)
        self.needs_restart = False
        send({"type": "restart_server"})

    def items_now(self):
        """(CHANGE 159) The lesson's power-ups as they are now (a click before the panel is drawn again sees these)."""
        items = self.lesson.get("items") if isinstance(self.lesson.get("items"), dict) else {}
        return {k: items.get(k, True) for k, _ in ITEM_TEXT}

    def set_lesson(self, change):
        send({"type": "lesson", "lesson": change})

    def next_track(self):
        names = list(kart_track.TRACKS)
        cur = self.lesson.get("track", names[0])
        nxt = names[(names.index(cur) + 1) % len(names)] if cur in names else names[0]
        self.set_lesson({"track": nxt})

    def upload_demo_brain(self):
        """Send brains/demo_cpu.py (or the demo brain) to the server: computer karts set to Empty run it."""
        for path in (os.path.join(HERE, "brains", "demo_cpu.py"), os.path.join(HERE, "brains", "demo_brain.py")):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    send({"type": "cpu_brain", "source": fh.read()})
                self.banner_note(f"Uploading {os.path.basename(path)} for the computer karts...")
                return
        self.banner_note("No demo brain: make brains/demo_cpu.py first")

    # ---------- try it on this laptop (teacher): a look at this laptop's game before it is made live ----------
    def try_here(self, mods=()):
        if TRY or kart_version.FROZEN or self.try_starting is not None:
            return
        if LOCAL:
            return self.banner_note("This window is already on this laptop's test server: it has this laptop's "
                                    "game. Tick the mod in Controls.", 8)
        info, proc = try_local.start(HERE, "kart_server.py", "KARTLAB_DATA")
        self.try_starting = (info, proc, time.perf_counter(), list(mods))
        self.banner_note("Starting a test server on this laptop: this window will reopen on it in a few seconds...", 60)
        self.taskMgr.doMethodLater(0.5, self.try_wait, "try on this laptop")

    def try_wait(self, task):
        info, proc, began, mods = self.try_starting
        if try_local.ready(info):
            login = [name, getattr(self, "password", ""), args.ticket or ""]
            self.restart_window(argv=["--host", f"ws://127.0.0.1:{info['port']}", "--teacher", "--code", "TEACH99",
                                      "--gfx", args.gfx] + (["--offscreen"] if args.offscreen else []),
                                try_env=try_local.pack(info, sys.argv[1:], login, mods, self.lesson.get("lesson_number")))
        if proc.poll() is not None or time.perf_counter() - began > 45:  # it stopped, or never answered
            words = try_local.last_words(info)
            try_local.stop(info, HERE)
            self.try_starting = None
            self.banner_note("The test server didn't start on this laptop, so the game as it is here doesn't run"
                             + (f": {words}" if words else "."), 30)
            return task.done
        return task.again

    def begin_try(self):
        if TRY.get("lesson") in LESSON_NUMBERS:
            send({"type": "lesson_number", "n": TRY["lesson"]})
        mods = {k: True for k in TRY.get("mods") or [] if k in self.user_mods}
        if mods:
            self.set_lesson({"user_mods": mods})
        self.exitFunc = self.stop_try  # (closing the window stops the test server too)
        OnscreenText("TRYING ON THIS LAPTOP: the class can't see this", pos=(-0.04, 0.715), scale=0.045, fg=ORANGE,
                     shadow=(0, 0, 0, 0.9), parent=self.aspect2d)
        DirectButton(parent=self.aspect2d, text="Back to the class", scale=0.042, pos=(-0.04, 0, 0.635),
                     command=self.back_to_class, frameColor=(0.15, 0.55, 0.25, 1), text_fg=WHITE, relief=DGG.FLAT,
                     pad=(0.4, 0.2))
        on = ", ".join(self.user_mods[k][0] for k in mods)
        self.banner_note((f"Switched on here: {on}. " if on else "Tick a user mod in Controls to try it. ")
                         + "When you have seen enough, press Back to the class.", 12)

    def stop_try(self):
        if TRY:
            try_local.stop(TRY["server"], HERE)

    def try_test(self, task):
        path = os.environ["CLUBCODERS_TRY_TEST"]
        seen = open(path).read() if os.path.exists(path) else ""
        with open(path, "a") as f:
            f.write(json.dumps({"where": "laptop" if TRY else "class", "host": args.host, "lesson": self.lesson.get(
                "lesson_number"), "user_mods": self.lesson.get("user_mods"), "mine": self.my_id is not None}) + "\n")
        if TRY:
            self.back_to_class()
        elif "laptop" not in seen:
            self.try_here([k for k in os.environ.get("CLUBCODERS_TRY_TEST_MODS", "").split(",") if k])
        return task.done

    def back_to_class(self):
        self.stop_try()
        global name
        login = TRY.get("login") or [name, "", ""]
        name, self.password, args.ticket = login[0] or name, login[1], login[2] or None
        self.restart_window(argv=TRY.get("argv") or [], try_env="")

    def push_mod_makers(self, only=None):
        """(Teacher) Tell the server who made each user mod: this laptop's change history knows (ai_changes/)."""
        try:
            import ai_pipeline
            makers = {k: who for k, who in ai_pipeline.user_mod_makers().items() if who and (only is None or k in only)}
        except Exception:
            return
        if makers:
            send({"type": "mod_makers", "makers": makers, "new": only is not None})

    def forget_mod_makers(self, mods):
        gone = [k for k, who in mods.get("makers", {}).items() if who == ""]
        if gone:
            try:
                import ai_pipeline
                ai_pipeline.forget_user_mod_makers(gone)
            except Exception:
                pass

    # ---------- settings ----------
    def build_settings(self, f, y):
        hud.HudKit.build_settings(self, f, y)
        y = self.body_bottom(y) - 0.07
        label(f, "Sound  (this computer)", 0.82, y, 0.028, YELLOW)
        y -= 0.05
        check(f, " Engine, tyres, the countdown and the finish", 0.84, y, not self.muted,
              lambda v: self.set_sound_on(bool(v)), 0.024)
        y -= 0.05
        label(f, "N switches the sound off and on while you drive.", 0.84, y, 0.021, GREY)

    def set_sound_on(self, on):
        self.muted = not on
        self.snd.on = on and not args.offscreen

    # ---------- teacher: races and the grand prix ----------
    def build_races(self, f, y):
        label(f, "RACES  -  the grid, the results and the grand prix", 0.82, y, 0.034, YELLOW)
        y -= 0.06
        y = self.race_controls(f, y)
        label(f, "On the grid", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        karts = (self.roster or {}).get("karts", [])
        if not karts:
            label(f, "Nobody yet.", 0.84, y, 0.024, GREY)
            y -= 0.04
        for k in karts[:10]:
            who = k.get("owner") or (f"computer ({k.get('cpu')})" if k.get("cpu") else "")
            label(f, f"{k['name']}", 0.84, y, 0.024, WHITE)
            label(f, who, 1.2, y, 0.022, GREY)
            y -= 0.036
        y -= 0.02
        results = self.race.get("results")
        if results:
            label(f, "Last race", 0.82, y, 0.028, YELLOW)
            y -= 0.045
            for i, (nm, laps_done, t) in enumerate(results[:10]):
                when = f"{int(t // 60)}:{t % 60:04.1f}" if t is not None else f"lap {laps_done + 1}"
                label(f, f"{i + 1}.  {nm}", 0.84, y, 0.024, GREEN if i == 0 else WHITE)
                label(f, when, 1.5, y, 0.024, GREY, TextNode.ARight)
                y -= 0.036
            y -= 0.02
        y = self.lap_times_table(f, y)
        # the grand prix (CHANGE 143: the server's summary, as the page shows it): the standings and the champion;
        # it is started and ended under Race above (designs are locked while it runs)
        t = self.tournament
        label(f, "GRAND PRIX  (designs locked while it runs)", 0.82, y, 0.028, YELLOW)
        y -= 0.05
        if t is None:
            label(f, "Not running: choose 2 to 5 races under Race above, then START THE GRAND PRIX. Every race's\n"
                     "places score points (10, 7, 5, 3, 2, 1); the most at the end is the champion.", 0.84, y, 0.019, GREY)
            y -= 0.07
        else:
            label(f, str(t.get("title") or ""), 0.84, y, 0.026, BLUE)
            y -= 0.045
            if t.get("champion"):
                label(f, f"CHAMPION: {t['champion']}", 0.84, y, 0.036, YELLOW)
                y -= 0.06
            for i, row in enumerate((t.get("standings") or [])[:12]):
                nm, pts = (list(row) + ["", 0])[:2]
                label(f, f"{i + 1}.  {nm}", 0.88, y, 0.023, GREEN if i == 0 else WHITE)
                label(f, f"{pts} pts", 1.5, y, 0.023, GREY, TextNode.ARight)
                y -= 0.034
        return y

    def lap_times_table(self, f, y):
        """CHANGE 143 (the page's Camera tab): every kart's laps this race, its best first (the race message's
        lap_times: kart id -> seconds for each lap done)."""
        times = self.race.get("lap_times") or {}
        names = {str(k["id"]): k["name"] for k in (self.roster or {}).get("karts", [])}
        label(f, "Lap times", 0.82, y, 0.028, YELLOW)
        label(f, "best", 1.2, y, 0.02, GREY, TextNode.ARight)
        y -= 0.042
        rows = [(names.get(str(kid), str(kid)), [t for t in laps if isinstance(t, (int, float))])
                for kid, laps in times.items()]
        rows.sort(key=lambda r: min(r[1]) if r[1] else 1e9)
        if not rows:
            label(f, "No laps yet.", 0.84, y, 0.022, GREY)
            y -= 0.036
        for nm, laps in rows[:12]:
            label(f, nm[:16], 0.84, y, 0.022, WHITE)
            label(f, fmt_lap(min(laps)) if laps else "", 1.2, y, 0.022, GREEN, TextNode.ARight)
            label(f, ", ".join(fmt_lap(t) for t in laps[-6:]), 1.24, y, 0.019, GREY)
            y -= 0.032
        return y - 0.03

    # ---------- teacher: the learner view ----------
    def build_learner_view(self, f, y):
        computer = next((c for c in self.class_list if c.get("role") == "computer"), None)
        learners = [c["name"] for c in self.class_list if c.get("role") == "learner"] + \
            ([computer["name"]] if computer else []) + [self.ALL_LEARNERS]  # (CHANGE 85)
        label(f, "LEARNER VIEW  -  see and change what a learner sees", 0.82, y, 0.03, YELLOW)
        y -= 0.06
        # every window's frame rate, ping, key delay, stalls and graphics, one table (CHANGE 143: the page's "Who is here")
        people = [(c["name"], c["role"]) for c in self.class_list if c.get("role") in ("teacher", "learner")]
        y = self.perf_table(f, y, people, (self.roster or {}).get("perf", {}))
        if self.view_name not in learners or (self.view_name == self.ALL_LEARNERS and len(learners) > 1
                                                and not getattr(self, "view_picked", False)):
            self.set_view(learners[0], redraw=False)  # (never All learners by default)
        across = max(0.16, min(0.2, 0.86 / len(learners)))
        for i, n in enumerate(learners):
            button(f, n, 0.9 + i * across, y + 0.008, self.set_view, [n], 0.028 if len(learners) < 5 else 0.022,
                   ON if n == self.view_name else OFF)
        y -= 0.065
        # how their window is doing (frame rate, ping, graphics tier, network stalls): kept fresh by show_perf
        self.perf_label, self.perf_frame = label(f, "", 0.82, y + 0.022, 0.021, GREY), f
        y -= 0.034
        who = self.view_name
        is_computer = computer is not None and who == computer["name"]
        tabs = (("garage", "Garage"), ("missions", "Mission"), ("ai", "AI card"), ("mods", "Mods"), ("brain", "Brain")) \
            if is_computer else (("garage", "Garage"),) if who == self.ALL_LEARNERS else \
            (("garage", "Garage"), ("missions", "Mission"), ("ai", "AI card"), ("login", "Login"))
        if self.view_tab not in [t for t, _ in tabs]:
            self.view_tab = "garage"
        for i, (t, text) in enumerate(tabs):
            button(f, text, 0.9 + i * 0.18, y + 0.008, self.set_view_tab, [t], 0.026, ON if t == self.view_tab else OFF)
        y -= 0.07
        if is_computer and self.view_tab == "brain":
            self.build_computer_brain(f, y, computer)
        elif is_computer and self.view_tab == "mods":
            label(f, "The Mods tab as a learner sees it (the computer kart doesn't vote).", 0.82, y, 0.022, GREY)
            self.build_mods(f, y - 0.045, as_learner=True)
        elif self.view_tab == "garage":
            self.build_garage(f, y, view=who)
            if is_computer:
                button(f, "RESET: THE COMPUTER KART AS IT COMES", 1.27, self.garage_bottom, send,
                       [{"type": "cpu_robot", "reset": True}], 0.026, (0.6, 0.2, 0.15, 1))
        elif self.view_tab == "missions":
            self.build_missions(f, y, m=self.view_missions.get(who), preview=True)
        elif self.view_tab == "ai":
            label(f, f"{who}'s AI request card", 0.82, y, 0.03, YELLOW)
            y -= 0.05
            label(f, kh.AI_RULES, 0.82, y, 0.023, BLUE, wrap=42)
            y -= 0.14
            self.card_list(f, y, [c for c in (self.teaching or {}).get("cards", []) if c["learner"] == who])
            label(f, "Send their requests to Claude from the AI cards tab.", 0.82, -0.86, 0.024, GREY)
        else:
            label(f, f"{who}'s login", 0.82, y, 0.03, YELLOW)
            y -= 0.06
            label(f, "Forgotten password? Type a new one and press Set.", 0.82, y, 0.025, GREY)
            y -= 0.06
            self.entry(f, "new_password", 0.84, y, 12, scale=0.03)
            button(f, "Set", 1.3, y + 0.008, self.set_password, [who], 0.03)

    def build_computer_brain(self, f, y, computer):
        label(f, "THE COMPUTER KART'S BRAIN", 0.82, y, 0.03, YELLOW)
        y -= 0.055
        label(f, "A learner writes brains/my_brain.py, uploads it (U) and switches autopilot on (P).\n"
                 "Do the same for the computer karts here. With its autopilot off, they follow\n"
                 "Their level in Controls.", 0.82, y, 0.022, GREY)
        y -= 0.13
        has, on = bool(computer.get("brain")), bool(computer.get("autopilot"))
        label(f, "Its brain: " + (("autopilot ON" if on else "uploaded, autopilot off") if has else "not uploaded yet"),
              0.82, y, 0.028, GREEN if has else GREY)
        y -= 0.075
        button(f, "Upload brains/my_brain.py for it", 1.08, y, self.upload_computer_brain, None, 0.028)
        if has:
            button(f, "Autopilot off" if on else "Autopilot on", 1.5, y, send,
                   [{"type": "cpu_robot", "autopilot": not on}], 0.028, ON if on else OFF)

    def upload_computer_brain(self):
        path = os.path.join(BRAINS, "my_brain.py")
        if not os.path.exists(path):
            self.banner_note("No brain file: make brains/my_brain.py first")
            return
        with open(path, encoding="utf-8") as fh:
            send({"type": "cpu_robot", "brain": fh.read()})
        self.banner_note("Uploading my_brain.py for the computer karts...")

    def set_view(self, learner, redraw=True):
        self.view_picked = redraw  # (the teacher chose it, rather than the first in the list)
        self.view_name = learner
        d = next((c["design"] for c in self.class_list if c["name"] == learner), None)
        if d is not None:
            self.view_drafts[learner] = copy.deepcopy(d)
        self.entry_text.pop("name_" + learner, None)
        self.code_shown = None
        send({"type": "view_learner", "name": learner})
        if redraw:
            self.rebuild_panels()

    def set_view_tab(self, tab):
        self.view_tab = tab
        self.code_shown = None
        if tab == "missions" and self.view_name:
            send({"type": "view_learner", "name": self.view_name})
        self.rebuild_panels()

    def set_password(self, learner, key="new_password"):
        pw = self.entries[key].get()
        if len(pw) < 6:
            self.banner_note("Passwords need at least 6 characters")
            return
        send({"type": "set_password", "learner": learner, "password": pw})
        self.entry_text[key] = ""
        self.rebuild_panels()

    # ---------- teacher: learners' accounts ----------
    def build_accounts(self, f, y):
        accounts = (self.teaching or {}).get("accounts", [])
        label(f, "ACCOUNTS  -  make each learner's login", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        label(f, "Use a nickname or first name only. Give the learner their username, password and class code.",
              0.82, y, 0.022, GREY, wrap=44)
        y -= 0.07
        label(f, "Username", 0.82, y, 0.025)
        self.entry(f, "acct_name", 0.97, y, 9, scale=0.028)
        y -= 0.06
        label(f, "Password", 0.82, y, 0.025)
        self.entry(f, "acct_pass", 0.97, y, 9, scale=0.028)
        button(f, "Make account", 1.45, y + 0.03, self.add_account, None, 0.028, (0.15, 0.55, 0.25, 1))
        y -= 0.08
        label(f, f"{len(accounts)} account(s)" if accounts else "No accounts yet.", 0.82, y, 0.026, YELLOW)
        y -= 0.05
        for n in accounts[:12]:
            label(f, n, 0.84, y, 0.025)
            key = "pw_" + n
            self.entry(f, key, 1.07, y, 7, scale=0.024)
            button(f, "Set password", 1.37, y + 0.008, self.set_password, [n, key], 0.022)
            sure = self.delete_armed == n
            button(f, "Sure? Delete" if sure else "Delete", 1.6, y + 0.008, self.delete_account, [n], 0.022,
                   RED if sure else OFF)
            y -= 0.055
        if len(accounts) > 12:
            label(f, f"...and {len(accounts) - 12} more", 0.84, y, 0.022, GREY)
        label(f, "Delete removes their profile, kart, brain, evidence and AI cards from the server.",
              0.82, -0.86, 0.022, GREY, wrap=44)

    def add_account(self):
        n, pw = self.entries["acct_name"].get().strip(), self.entries["acct_pass"].get()
        if not n or len(pw) < 6:
            self.banner_note("Type a username and a password of at least 6 characters")
            return
        send({"type": "add_learner", "learner": n, "password": pw})
        self.entry_text["acct_name"] = self.entry_text["acct_pass"] = ""
        self.rebuild_panels()

    def delete_account(self, learner):
        if self.delete_armed != learner:  # the first click asks "Sure?"
            self.delete_armed = learner
        else:
            self.delete_armed = None
            send({"type": "delete_learner", "learner": learner})
        self.rebuild_panels()

    # ---------- a newer version of the game ----------
    def check_for_update(self):
        def work():
            self.newer = kart_version.newer_release()
        threading.Thread(target=work, daemon=True).start()

    def offer_download(self):
        if self.download_button is None and kart_version.DOWNLOAD_PAGE:
            self.download_button = button(self.aspect2d, "Download the new Club Coders", 1.2, 0.86,
                                          webbrowser.open, [kart_version.DOWNLOAD_PAGE], 0.035, (0.15, 0.55, 0.25, 1))

    # ---------- teacher: mods (changes made with Claude): switch on and off, then merge into the game ----------
    def pipeline_module(self):
        try:
            import ai_pipeline
            return ai_pipeline
        except ImportError:
            return None

    def build_changes(self, f, y):
        ai_pipeline = self.pipeline_module()
        label(f, "MODS", 0.82, y, 0.036, YELLOW)
        y -= 0.05
        if ai_pipeline is None:
            label(f, "The AI pipeline isn't set up for Kart Lab on this computer yet.", 0.82, y, 0.026, GREY)
            return
        log = list(reversed(ai_pipeline.history()))
        mods = [e for e in log if e["status"] != "merged"]
        merged = [e for e in log if e["status"] == "merged"]
        label(f, "Changes made with Claude, newest first. Switch a mod off if it causes problems, and on again to\n"
                 "bring it back. Merge into game makes it a permanent part of the game.", 0.82, y, 0.02, GREY)
        y -= 0.08
        if not mods:
            label(f, "No mods waiting: kept AI changes appear here.", 0.82, y, 0.026, GREY)
            y -= 0.06
        per = 3 if self.change_view else 4
        pages = max(1, (len(mods) + per - 1) // per)
        self.change_page = min(self.change_page, pages - 1)
        for e in mods[self.change_page * per:(self.change_page + 1) * per]:
            on = e["status"] == "kept"
            button(f, " ON " if on else "OFF", 0.855, y + 0.006, self.switch_change, [e["n"], "rollback" if on else "reapply"],
                   0.026, (0.15, 0.55, 0.25, 1) if on else (0.45, 0.3, 0.15, 1))  # the mod's on/off switch
            label(f, f"{e['n']}.  {e['goal'][:46]}", 0.9, y, 0.026, WHITE if on else GREY)
            y -= 0.036
            label(f, f"Designed by {e['learner']}  ({kh.TARGETS.get(e['target'], e['target'])}, {e['time'][5:]})", 0.9, y,
                  0.021, BLUE)
            y -= 0.03
            label(f, "Files: " + ", ".join(e["files"])[:78], 0.9, y, 0.019, GREY)
            y -= 0.045
            button(f, "Hide" if self.change_view == e["n"] else "Show changes", 0.97, y, self.show_change, [e["n"]], 0.023)
            button(f, "Open in editor", 1.19, y, ai_pipeline.open_in_editor, [e["n"]], 0.023)
            if on:
                button(f, "Merge into game", 1.47, y, self.merge_change, [e["n"]], 0.023, (0.15, 0.5, 0.25, 1))
            else:
                label(f, "switch on to merge", 1.47, y - 0.006, 0.02, GREY, TextNode.ACenter)
            y -= 0.06
            if self.change_view == e["n"]:
                y = self.diff_preview(f, y, ai_pipeline.change_diff(e["n"]))
        if pages > 1:
            button(f, "Newer", 1.0, y, self.page_changes, [-1], 0.023)
            label(f, f"page {self.change_page + 1} of {pages}", 1.27, y - 0.005, 0.021, GREY, TextNode.ACenter)
            button(f, "Older", 1.52, y, self.page_changes, [1], 0.023)
            y -= 0.06
        if merged:
            label(f, f"MERGED INTO THE GAME ({len(merged)})", 0.82, y, 0.026, YELLOW)
            y -= 0.04
            for e in merged[:3]:
                label(f, f"{e['n']}.  {e['goal'][:40]}  -  designed by {e['learner']}, merged {e.get('merged', '')[5:]}",
                      0.84, y, 0.02, GREY)
                y -= 0.032
            if len(merged) > 3:
                label(f, f"and {len(merged) - 3} earlier", 0.84, y, 0.02, GREY)
        label(f, self.change_msg[0], 0.82, -0.72, 0.022, self.change_msg[1], wrap=46)
        self.restart_row(f, -0.8)

    def merge_change(self, n):
        ai_pipeline = self.pipeline_module()
        res = ai_pipeline.merge(n)
        self.change_msg = (f"Mod {n} is now a permanent part of the game." if res["ok"] else res["message"],
                           GREEN if res["ok"] else RED)
        if res["ok"]:  # the learner's name goes in front of any user mod it added
            self.push_mod_makers(res["user_mods"])
        if self.change_view == n:
            self.change_view = None
        self.rebuild_panels()

    def diff_preview(self, f, y, diff):
        """The first lines of a change: added lines green, removed lines red."""
        lines = [ln for ln in diff.splitlines() if not ln.startswith(("---", "+++"))][:14]
        for ln in lines:
            colour = GREEN if ln.startswith("+") else RED if ln.startswith("-") else BLUE if ln.startswith("@@") else GREY
            label(f, ln[:78], 0.84, y, 0.019, colour)
            y -= 0.028
        if len(diff.splitlines()) > len(lines) + 2:
            label(f, "... more: press Open in editor", 0.84, y, 0.019, GREY)
            y -= 0.03
        return y - 0.02

    def show_change(self, n):
        self.change_view = None if self.change_view == n else n
        self.rebuild_panels()

    def page_changes(self, delta):
        self.change_page = max(0, self.change_page + delta)
        self.change_view = None
        self.rebuild_panels()

    def switch_change(self, n, how):
        ai_pipeline = self.pipeline_module()
        res = (ai_pipeline.rollback if how == "rollback" else ai_pipeline.reapply)(n)
        if not res["ok"]:
            self.change_msg = (res["message"], ORANGE if res.get("clashes") else RED)
            self.rebuild_panels()
            return
        mods = {}
        for rel in res["files"]:
            path = os.path.join(HERE, rel)
            if rel.startswith("mods/") and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    mods[rel] = fh.read()
        if mods:
            send({"type": "mods_update", "files": mods})
        code_files = [rel for rel in res["files"] if rel.endswith(".py") and not rel.startswith("mods/")]
        if code_files:
            self.needs_restart = True
        done = "switched off" if how == "rollback" else "switched on"
        self.change_msg = (f"Mod {n} {done}. " + ("Restart the server (below) to use it." if code_files else
                                                    "The track, rules and karts have been updated."), GREEN)
        self.rebuild_panels()

    # ---------- teacher: outcomes and evidence; the missions as learners see them, editable (CHANGE 97) ----------
    def toggle_outcome_obj(self, mid):
        self.open_outcome_obj = None if getattr(self, "open_outcome_obj", None) == mid else mid
        self.rebuild_panels()

    def automate_objective(self, mid, n, title_, text, check_="teacher"):
        """AUTOMATE: an AI request card (target: the game) asking Claude to write this objective's automatic check."""
        asked = ("Automate the check for" if check_ == "teacher" else
                 "Check that the automatic check still fits the wording of, and fix it if not,")
        card = {"goal": f"{asked} Mission {n} objective {mid}, '{title_}'. The game should tick it for a "
                        f"learner by itself, as the other objectives are checked by their id in the teaching module "
                        f"(build_checks when they build, tick_checks every half second, brain_checks for brains), when "
                        f"they do this: {text} If it can't be checked automatically, say why and suggest wording that "
                        f"could be.",
                "variables": f"The objective's id is {mid}. self.complete(p.name, '{mid}', detail) marks it done with a "
                             f"detail saying what the learner did (their kart's values before and after).",
                "test": f"Log in as a learner on a laptop test server, do objective {mid} as the text says, and watch the "
                        f"Mission tab: it should show DONE with the detail within a few seconds. Also check it does not "
                        f"tick when the learner has not done it.",
                "predict": f"Objective {mid} ticks itself a moment after a learner does it, with no click from the teacher.",
                "privacy": True, "review": True, "credit": True, "target": "game"}
        send({"type": "ai_card", "card": card})
        self.banner_note(f"Automate {mid}: an AI request card is waiting in the AI cards tab. Check and send it to Claude.", 8)

    def toggle_mission_editor(self):
        self.editing_missions = not getattr(self, "editing_missions", False)
        self.rebuild_panels()

    def build_mission_editor(self, f, y):
        t = self.teaching or {}
        n_ = getattr(self, "guide_lesson", None) or t.get("lesson", 1)
        label(f, "MISSIONS AS LEARNERS SEE THEM", 0.82, y, 0.032, YELLOW)
        button(f, "Back to outcomes", 1.58, y + 0.008, self.toggle_mission_editor, None, 0.02)
        y -= 0.05
        label(f, "Change the words, add an objective or take one out: every learner sees it. The checks follow an "
                 "objective's id, not its words (an added one has no check: tick it for a learner by hand). After "
                 "editing, ask Claude separately whether the checks still fit.", 0.82, y, 0.02, GREY, wrap=72)
        y -= 0.085
        label(f, "Mission", 0.82, y, 0.028, YELLOW)
        lessons = [int(k) for k in t.get("edited", {})] or LESSON_NUMBERS
        for i, n in enumerate(sorted(lessons)):
            button(f, str(n), 1.0 + i * 0.08, y + 0.008, self.pick_edit_lesson, [n], 0.028, ON if n == n_ else OFF)
        edits = t.get("edits", {})
        if edits.get("changed") or edits.get("removed") or edits.get("added"):
            button(f, "Reset all to standard", 1.46, y + 0.008, send, [{"type": "missions_edit", "do": "reset"}], 0.022,
                   (0.6, 0.2, 0.15, 1))
        y -= 0.06
        L = self.lesson
        check(f, " Show learners: pause every race and open every learner's Mission tab", 0.84, y,
              L.get("show_missions"), lambda v: self.set_lesson({"show_missions": bool(v)}), 0.024,
              GREEN if L.get("show_missions") else None)
        y -= 0.05
        objectives = t.get("edited", {}).get(str(n_), {})
        hidden = set(t.get("edits", {}).get("hidden", []))
        grid = t.get("grid", {})
        for i, (mid, v) in enumerate(objectives.items()):
            letter = "abcdefgh"[i] if i < 8 else "+"
            label(f, f"{letter}.", 0.82, y, 0.026, WHITE)
            check(f, " learners see it", 1.3, y, mid not in hidden,
                  lambda on, k=mid: send({"type": "missions_edit", "do": "show" if on else "hide", "id": k}), 0.02)
            label(f, f"id {mid}  {' '.join(v[3]) or 'no check'}", 1.74, y, 0.017, BLUE, TextNode.ARight)
            self.entry(f, f"mtitle_{mid}", 0.86, y - 0.04, 28, 1, initial=v[1], scale=0.024)
            y -= 0.09
            self.textbox(f, f"mtext_{mid}", 0.86, y + 0.03, 0.72, 7, initial=v[2], scale=0.022)  # (the whole text)
            button(f, "Save", 1.62, y + 0.008, self.save_objective, [mid], 0.022, (0.15, 0.55, 0.25, 1))
            button(f, "Remove", 1.62, y - 0.04, send, [{"type": "missions_edit", "do": "remove", "id": mid}], 0.02,
                   (0.6, 0.2, 0.15, 1))
            button(f, "Automate", 1.62, y - 0.088, self.automate_objective, [mid, n_, v[1], v[2], v[4]], 0.019,
                   (0.15, 0.45, 0.65, 1))
            y -= 0.235
            names = [n for n in grid if n != name]  # (every learner the server knows: green has done it, red not yet)
            if names:
                for j, name_ in enumerate(names):
                    done = mid in grid[name_].get("missions", [])
                    label(f, name_[:10], 0.86 + (j % 6) * 0.148, y - (j // 6) * 0.03, 0.02, GREEN if done else RED)
                y -= 0.03 * ((len(names) + 5) // 6) + 0.012
        y -= 0.02
        label(f, "Add an objective", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        self.entry(f, "mnew_title", 0.86, y, 24, 1, initial="", scale=0.024)
        label(f, "title", 1.5, y, 0.019, GREY)
        y -= 0.05
        self.textbox(f, "mnew_text", 0.86, y + 0.03, 0.72, 5, initial="", scale=0.022)
        button(f, "Add", 1.62, y + 0.008, self.add_objective, [n_], 0.022, (0.15, 0.55, 0.25, 1))
        y -= 0.19
        label(f, "As a file", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        button(f, "EXPORT", 0.9, y + 0.008, send, [{"type": "missions_export"}], 0.022)
        button(f, "IMPORT", 1.06, y + 0.008, self.import_missions_file, None, 0.022, (0.15, 0.45, 0.65, 1))
        label(f, "missions_kartlab.json in this folder's evidence folder: export, edit it in any editor, import.",
              0.84, y - 0.04, 0.019, GREY, wrap=46)
        y -= 0.1

    def import_missions_file(self):
        path = os.path.join(HERE, "evidence", "missions_kartlab.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.banner_note("No missions_kartlab.json yet: press EXPORT first", 4)
            return
        except ValueError as e:
            self.banner_note(f"The file isn't valid JSON: {e}", 6)
            return
        send({"type": "missions_import", "data": data})

    def pick_edit_lesson(self, n):
        self.guide_lesson = n
        self.rebuild_panels()

    def save_objective(self, mid):
        title_ = self.entries[f"mtitle_{mid}"].get() if f"mtitle_{mid}" in self.entries else ""
        text = self.entries[f"mtext_{mid}"].get() if f"mtext_{mid}" in self.entries else ""
        send({"type": "missions_edit", "do": "change", "id": mid, "title": title_, "text": text})
        self.banner_note("Saved: every learner sees it", 2)

    def add_objective(self, n):
        title_ = self.entries["mnew_title"].get() if "mnew_title" in self.entries else ""
        text = self.entries["mnew_text"].get() if "mnew_text" in self.entries else ""
        if not title_.strip():
            self.banner_note("Give the objective a title first", 2)
            return
        self.entry_text.pop("mnew_title", None)
        self.entry_text.pop("mnew_text", None)
        send({"type": "missions_edit", "do": "add", "lesson": n, "title": title_, "text": text})

    def build_outcomes(self, f, y):
        t = self.teaching
        if getattr(self, "editing_missions", False):
            return self.build_mission_editor(f, y)
        label(f, "LEARNING OUTCOMES", 0.82, y, 0.034, YELLOW)
        if not t:
            label(f, "Waiting for the server's teaching data...", 0.82, y - 0.06, 0.026, GREY)
            return
        button(f, "Edit the missions", 1.58, y + 0.008, self.toggle_mission_editor, None, 0.022)  # (CHANGE 97)
        y -= 0.06
        codes = list(t["outcomes"])
        learners = list(t["grid"])
        label(f, "Outcome", 0.82, y, 0.024, GREY)
        for j, n in enumerate(learners[:4]):
            label(f, n[:8], 1.28 + j * 0.12, y, 0.024, GREY, TextNode.ACenter)
        y -= 0.04
        n_ = t["lesson"]
        this = t.get("edited", {}).get(str(n_), {})
        for code_ in codes:
            taught = any(code_ in v[3] for v in this.values())  # (outcomes this mission teaches stand out)
            label(f, t["outcomes"][code_][0], 0.82, y, 0.024, BLUE if taught else WHITE)
            for j, n in enumerate(learners[:4]):
                c = t["grid"][n]["outcomes"].get(code_, 0)
                label(f, str(c) if c else "-", 1.28 + j * 0.12, y, 0.026, GREEN if c else GREY, TextNode.ACenter)
            y -= 0.036
            if taught:  # this mission's objectives that give the outcome: click one for its description
                for i, (mid, v) in enumerate(this.items()):
                    if code_ not in v[3]:
                        continue
                    letter = "abcdefgh"[i] if i < 8 else "+"
                    opened = getattr(self, "open_outcome_obj", None) == mid
                    text_button(f, f"{letter}. {v[1]}", 0.9, y, self.toggle_outcome_obj, [mid], 0.023,
                                YELLOW if opened else WHITE)
                    y -= 0.036
                    if opened:
                        tt = label(f, v[2], 0.92, y, 0.021, GREY, wrap=40)
                        y -= 0.027 * tt.textNode.getNumRows() + 0.012
        y -= 0.02
        label(f, f"Teacher-checked missions (lesson {t['lesson']})", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        for mid, (lesson, title_, check_) in t["missions"].items():
            if check_ != "teacher" or lesson != t["lesson"]:
                continue
            label(f, f"{mid} {title_}", 0.84, y, 0.024)
            for j, n in enumerate(learners[:4]):
                done = mid in t["grid"][n]["missions"]
                button(f, n[:6] + (" ok" if done else ""), 1.28 + j * 0.12, y + 0.006, send,
                       [{"type": "tick", "learner": n, "mission": mid}], 0.022, GREEN if done else OFF)
            y -= 0.05
        button(f, "Export evidence (CSV)", 1.27, -0.86, send, [{"type": "export"}], 0.03, (0.15, 0.45, 0.65, 1))

    # ---------- teacher: AI request cards ----------
    def build_cards(self, f, y):
        if self.cards_view == "edit":
            return self.build_ai_card(f, y, edit=True)
        checking = next((c for c in (self.teaching or {}).get("cards", []) if c["id"] == self.cards_view), None)
        if checking is not None:
            return self.build_card_check(f, y, checking)
        if self.teaching is not None:  # (that card has gone: back to the list)
            self.cards_view = None
        label(f, "AI REQUEST CARDS", 0.82, y, 0.036, YELLOW)
        button(f, "The learners' card", 1.62, y + 0.008, self.show_cards, ["edit"], 0.022)
        y -= 0.05
        label(f, "Choose what Claude may change, then Send to Claude. The whole game lets Claude change\n"
                 "anything (new tracks, items, rules, graphics). Every change is tested before you Keep it,\n"
                 "and kept changes can be rolled back later in the Changes tab.", 0.82, y, 0.02, GREY)
        y -= 0.1
        # every card or only the open ones (CHANGE 143: the page's "Showing open cards" button)
        cards = self.cards_filter(f, 1.33, y + 0.158, (self.teaching or {}).get("cards", []))
        if not cards:
            label(f, "No cards." if self.all_cards else "No requests waiting.", 0.82, y, 0.028, GREY)
        for c in cards:
            job = self.ai_jobs.get(c["id"], {})
            target = self.card_targets.get(c["id"], c["card"].get("target", "kart"))
            label(f, f"#{c['id']} {c['learner']}  [{job.get('status', c['status'])}]", 0.82, y, 0.026)
            y -= 0.038
            label(f, c["card"]["goal"], 0.84, y, 0.022, GREY, wrap=44)
            y -= 0.05
            res = job.get("result")
            if job.get("status") == "Claude is working..." and getattr(job.get("change"), "waiting", False):
                label(f, "Waiting: Claude is finishing another card first (one at a time, so neither undoes the "
                         "other)", 0.84, y, 0.022, BLUE, wrap=46)
                y -= 0.05
            elif job.get("status") == "Claude is working...":
                took = int(time.time() - (getattr(job.get("change"), "started", None) or job.get("started", time.time())))
                label(f, f"Claude is working on it ({kh.TARGETS.get(target, target)}), {took} s so far: usually under a "
                         "minute, a few minutes for whole-game changes, then it is tested...", 0.84, y, 0.022, BLUE, wrap=46)
                y -= 0.05
            elif res:
                colour = GREEN if res["test_ok"] and res["files"] else RED
                text = res["summary"][:420] + ("\nTest: passed" if res["test_ok"] else "\nTest: FAILED - " + res["test"][-140:])
                if res["blocked"]:
                    text += "\nThrown away (outside the allowed files): " + ", ".join(res["blocked"])
                label(f, text, 0.84, y, 0.02, colour, wrap=46)
                y -= 0.03 * (text.count("\n") + len(text) // 70 + 2)
                if res.get("files"):
                    label(f, "Changed: " + ", ".join(res["files"])[:90], 0.84, y + 0.02, 0.02, BLUE)
                if job.get("status") == "Check it" and res["files"]:
                    button(f, "Keep", 1.0, y - 0.02, self.ai_keep, [c], 0.028, (0.15, 0.55, 0.25, 1))
                    button(f, "Undo", 1.25, y - 0.02, self.ai_undo, [c], 0.028, (0.6, 0.2, 0.15, 1))
                    y -= 0.09
                elif job.get("status") in ("Check it", "Failed"):  # nothing changed: try again, maybe as a game change
                    if res.get("needs_game"):
                        button(f, "Allow the whole game and send again", 1.25, y, self.ai_retry, [c, "game"], 0.028,
                               (0.15, 0.45, 0.65, 1))
                        y -= 0.07
                    label(f, "Nothing was changed. Choose what Claude may change and send again:", 0.84, y, 0.022,
                          ORANGE)
                    y -= 0.05
                    y = self.card_targets_row(f, y, c, target)
                    button(f, "Send again", 0.95, y, self.ai_retry, [c], 0.026, (0.15, 0.45, 0.65, 1))
                    button(f, "Reject", 1.2, y, self.card_status, [c["id"], "rejected"], 0.026)
                    y -= 0.07
                elif job.get("status") == "Kept" and res.get("code_changed"):
                    label(f, "Kept on this laptop only. Try it here first; then, for the class: Make my changes\n"
                             "live.bat (then Restart server). A user mod then appears in Controls, to switch on.",
                          0.84, y, 0.022, ORANGE)
                    y -= 0.075
                    if not TRY and not LOCAL and not kart_version.FROZEN:
                        button(f, "Try it on this laptop", 1.02, y, self.try_here, [self.job_mods(job)], 0.026,
                               (0.15, 0.45, 0.65, 1))
                        y -= 0.06
            elif c["status"] in ("waiting", "sent", "working"):
                y = self.card_targets_row(f, y, c, target)
                button(f, "Check and send", 0.95, y, self.show_cards, [c["id"]], 0.026, (0.15, 0.45, 0.65, 1))
                button(f, "Copy prompt", 1.2, y, self.copy_prompt, [c], 0.026)
                button(f, "Reject", 1.42, y, self.card_status, [c["id"], "rejected"], 0.026)
                y -= 0.07
            y -= 0.02
            if y < -0.8 and not self.all_cards:  # (every card: the panel slides to show them all)
                break

    @staticmethod
    def job_mods(job):
        """The user mods a kept AI change added (to switch on when it is tried on this laptop)."""
        change = job.get("change")
        if change is None:
            return []
        return sorted(try_local.mod_keys(change.after.get("kart_sim.py"))
                      - try_local.mod_keys(change.before.get("kart_sim.py")))

    def card_targets_row(self, f, y, c, target):
        for i, (key, text) in enumerate(kh.TARGETS.items()):
            button(f, text, 0.93 + i * 0.2, y, self.set_card_target_for, [c["id"], key],
                   0.022, ON if key == target else OFF)
        if target == "game":  # (a user mod is off until the teacher switches it on in Controls)
            y -= 0.05
            check(f, " Make it a switchable User Mod (off until you switch it on in Controls)", 0.86, y + 0.008,
                  self.card_user_mod.get(c["id"], True), lambda v, cid=c["id"]: self.card_user_mod.__setitem__(
                      cid, bool(v)), 0.024)
        return y - 0.06

    def set_card_target_for(self, cid, key):
        self.card_targets[cid] = key
        self.rebuild_panels()

    def card_prompt(self, c):
        """Exactly the prompt that Send to Claude sends for this card, as the teacher has set it."""
        ai_pipeline = self.pipeline_module()
        if ai_pipeline is None:
            raise ValueError("The AI pipeline isn't set up for Kart Lab on this computer yet.")
        target = self.card_targets.get(c["id"], c["card"].get("target", "kart"))
        return ai_pipeline.build_prompt(c["card"], c["learner"], target, ai_pipeline.allowed_files(target, c["learner"]),
                                        target == "game" and self.card_user_mod.get(c["id"], True)), target

    def build_card_check(self, f, y, c):
        """Before anything goes to Claude: the whole card and the whole prompt, on screen."""
        label(f, f"CHECK BEFORE SENDING   #{c['id']} {c['learner']}", 0.82, y, 0.034, YELLOW)
        y -= 0.05
        for key, text in (("goal", "Idea"), ("variables", "Variables and values"), ("test", "How they will test it"),
                          ("predict", "Their prediction")):
            words = label(f, f"{text}:  {c['card'].get(key, '')}", 0.82, y, 0.022, WHITE, wrap=42)
            y -= 0.026 * max(1, words.textNode.getNumRows()) + 0.008
        ticks = [text for key, text in (("privacy", "no personal information"), ("review", "will review and test the code"),
                                        ("credit", "will say where AI helped")) if c["card"].get(key)]
        label(f, "Ticked: " + (", ".join(ticks) or "nothing"), 0.82, y, 0.02, GREY)
        y -= 0.045
        try:
            prompt, target = self.card_prompt(c)
        except ValueError as e:
            prompt, target = str(e), "kart"
        button(f, "Send to Claude", 0.95, y - 0.01, self.ai_send, [c], 0.028, (0.15, 0.45, 0.65, 1))
        button(f, "Copy prompt", 1.22, y - 0.01, self.copy_prompt, [c], 0.026)
        button(f, "Back", 1.42, y - 0.01, self.show_cards, [None], 0.026)
        y -= 0.065
        label(f, f"THE WHOLE PROMPT   ({kh.TARGETS.get(target, target)})", 0.82, y, 0.026, YELLOW)
        label(f, "scroll with the mouse wheel", 1.74, y, 0.02, GREY, TextNode.ARight)
        y -= 0.03
        key = (c["id"], prompt)
        if self.prompt_state.get("key") != key:  # a different card (or what Claude may change has changed)
            lines = [part for line in prompt.splitlines() for part in (textwrap.wrap(line, 80) or [""])]
            self.prompt_state = {"key": key, "lines": lines, "cursor": [0, 0], "scroll": 0}
        scale = 0.018
        rows = max(4, int((y + 0.90) / (scale * 1.8)))
        self.prompt_view = code_editor.CodeEditor(self, f, self.prompt_state, 0.80, y, 0.94, rows, scale, read_only=True)

    def show_cards(self, view):
        self.cards_view = view
        self.rebuild_panels()

    def send_card_note(self):
        """Teacher: what is typed in "From your teacher" goes on every learner's card (and stays for next time)."""
        note = " ".join(self.entries["card_note"].get().split())[:300] if "card_note" in self.entries else ""
        self.entry_text.pop("card_note", None)
        self.stop_typing()
        self.set_lesson({"ai_card_note": note})
        self.card_note_text.setText("Sent: it is on the learners' cards." if note else "Sent: nothing from you is on their cards.")

    def ai_retry(self, c, target=None):
        if target:
            self.card_targets[c["id"]] = target
        self.ai_jobs.pop(c["id"], None)
        self.ai_send(c)

    def ai_send(self, c):
        """Run the learner's approved request through Claude in the background."""
        ai_pipeline = self.pipeline_module()
        if ai_pipeline is None:
            return self.banner_note("The AI pipeline isn't set up for Kart Lab on this computer yet.", 6)
        learner_design = next((p["design"] for p in self.class_list if p["name"] == c["learner"]), None)
        target = self.card_targets.get(c["id"], c["card"].get("target", "kart"))
        try:
            change = ai_pipeline.AIChange(c["id"], c["learner"], c["card"], target, design=learner_design,
                                          as_user_mod=target == "game" and self.card_user_mod.get(c["id"], True))
        except ValueError as e:
            self.banner_note(str(e), 5)
            return
        self.cards_view = None  # (back to the list of requests, where its progress shows)
        job = self.ai_jobs[c["id"]] = {"status": "Claude is working...", "change": change, "started": time.time()}
        send({"type": "card_status", "id": c["id"], "status": "working", "note": "The teacher sent this to Claude"})

        def work():
            try:
                job["result"] = change.run(progress=lambda m: None)
                job["status"] = "Check it"
            except Exception as e:  # show the problem instead of crashing the window
                job["result"] = {"summary": f"Something went wrong: {e}", "test_ok": False, "test": "", "files": [],
                                 "blocked": []}
                job["status"] = "Failed"
            job["dirty"] = True
        threading.Thread(target=work, daemon=True).start()
        self.rebuild_panels()

    def ai_keep(self, c):
        job = self.ai_jobs[c["id"]]
        change = job["change"]
        change.keep()
        self.push_mod_makers(change.user_mods)  # a new user mod gets the learner's name in front
        mods = {k: v for k, v in change.contents().items() if k.startswith("mods/")}
        if mods:
            send({"type": "mods_update", "files": mods})
        engine = [f for f in job["result"]["files"] if not f.startswith("mods/")]
        if engine:
            self.needs_restart = True
        note = "Kept. " + ("It is in the game after the restart. " if engine else "") + \
               "Try it, then answer the review questions. AI tool: Claude, used by the teacher."
        send({"type": "card_status", "id": c["id"], "status": "ready", "note": note})
        job["status"] = "Kept"
        self.rebuild_panels()

    def ai_undo(self, c):
        job = self.ai_jobs[c["id"]]
        try:
            job["change"].undo()
        except RuntimeError as e:  # (Claude is at work on another card: the files mustn't change under it)
            self.banner_note(str(e), 5)
            return
        send({"type": "card_status", "id": c["id"], "status": "rejected",
              "note": "The teacher undid this change. Try making your request clearer."})
        job["status"] = "Undone"
        self.rebuild_panels()

    def card_status(self, cid, status):
        note = {"ready": "Ready: try it, then answer the review questions",
                "rejected": "Please make the goal and test clearer, then send it again",
                "sent": "Sent to the AI by the teacher"}[status]
        send({"type": "card_status", "id": cid, "status": status, "note": note})

    def copy_prompt(self, c):
        ai_pipeline = self.pipeline_module()
        try:
            text, target = self.card_prompt(c)  # the same prompt Send uses
        except ValueError as e:
            self.banner_note(str(e), 5)
            return
        path = os.path.join(ai_pipeline.DATA, "ai_requests", ai_pipeline.save_prompt(c["id"], c["learner"], target, text))
        try:
            subprocess.run("clip", input=text.encode("utf-16"), check=True, shell=True)  # Windows clipboard
            self.banner_note(f"Prompt #{c['id']} copied: paste it into Claude")
        except Exception:
            self.banner_note(f"Prompt saved to {path}")

    # ---------- the track and the race ----------
    def set_track(self, track_name, laps):
        if track_name not in kart_track.TRACKS:
            track_name = next(iter(kart_track.TRACKS))
        if track_name != self.track_name:
            self.track_name = track_name
            self.track = kart_track.load(track_name)
            if self.track_vis is not None:
                self.track_vis.destroy()
            self.track_vis = kart_gfx.TrackVisual(self.render, self.track)
            if getattr(self, "items_vis", None) is not None:
                self.items_vis.destroy()
            self.items_vis = kart_gfx.ItemsVisual(self.render, self.track)  # (CHANGE 159) the power-ups
            if self.screen is not None:
                self.screen.destroy()
            self.screen = kart_gfx.Hud(self, self.track)
            self.predictor = None
            self.snaps = interp.Snapshots(SNAP_SPEC)
        if laps:
            self.race["laps"] = laps

    def read_network(self):
        rebuild = False
        for job in self.ai_jobs.values():
            if job.pop("dirty", False):
                rebuild = rebuild or self.tab == "cards"
        while True:
            try:
                m = net.inbox.get_nowait()
            except queue.Empty:
                break
            kind = m["type"]
            if kind == "binary":
                if wire.kind_of(m["data"]) == wire.KIND_SNAPSHOT:
                    self.on_snapshot(wire.unpack_snapshot(SCHEMA, m["data"]), m.get(interp.RECEIVED))
            elif kind == "race":
                rebuild = self.on_race(m) or rebuild
            elif kind == "items":  # (CHANGE 159) the power-ups out on the track, and who was hit
                if getattr(self, "items_vis", None) is not None:
                    self.items_vis.push(m)
                self.item_hits(m.get("hits") or [])
            elif kind == "roster":
                self.roster = m
                self.sync_designs({k["id"]: {"name": k["name"], "colour": k["colour"],  # (and the body: a kart or a
                                              "body": (k.get("design") or {}).get("body", "kart")}  # sports car, CHANGE 173)
                                   for k in m["karts"]})
                if m.get("laps"):
                    self.race["laps"] = m["laps"]
                mine = (m.get("mine") or {}).get(self.my_name)
                if mine is not None:
                    self.my_id = mine
                rebuild = rebuild or self.tab == "races"
            elif kind == "welcome":  # back after a dropped connection (or a server restart)
                self.reconnecting = False
                if self.check_code(m):
                    return
                self.lesson = self.fill_lesson(m.get("lesson") or self.lesson)
                self.obey_gfx_max()
                self.rules = kh.default_rules() | dict(m.get("rules") or {})
                self.design = sim.fit_design(dict(m.get("design") or self.design))
                self.draft = copy.deepcopy(self.design)
                self.my_id = m.get("kart", self.my_id)
                self.set_track(self.lesson.get("track", self.track_name), self.lesson.get("laps"))
                self.banner_note("Reconnected: carry on!", 3)
                self.code_shown = None
                rebuild = True
            elif kind == "lesson":
                new = self.fill_lesson(m.get("lesson") or {})
                if new != self.lesson or m.get("tournament") != self.tournament or \
                        (TEACHER and m.get("class", self.class_list) != self.class_list):
                    rebuild = rebuild or self.tab in ("garage", "teacher", "learners", "races", "missions") or \
                        (self.tab == "settings" and new.get("gfx_max") != self.lesson.get("gfx_max"))
                mods = m.get("mods") or {}
                if mods != self.mod_info:  # a new vote, a maker's name, or someone from the group has come in
                    rebuild = rebuild or self.tab in ("teacher", "mods")
                    if TEACHER:
                        self.forget_mod_makers(mods)
                if TEACHER:  # the computer kart was rebuilt or reset: the Learner view shows it as it is now
                    was = next((c["design"] for c in self.class_list if c.get("role") == "computer"), None)
                    for c in m.get("class", []):
                        if c.get("role") == "computer" and was is not None and c["design"] != was:
                            self.view_drafts.pop(c["name"], None)
                            self.entry_text.pop("name_" + c["name"], None)
                            self.code_shown = None
                self.show_missions_changed(self.lesson, new)  # (CHANGE 122)
                self.lesson, self.class_list, self.tournament, self.mod_info = \
                    new, m.get("class", self.class_list), m.get("tournament"), mods
                self.obey_gfx_max()
                self.set_track(new.get("track", self.track_name), new.get("laps"))
                kart_gfx.set_time(new.get("time", "day"))  # (CHANGE 172: day, dusk or night, as the teacher has it)
            elif kind in ("slots", "history"):  # saved designs (CHANGE 83 to 86)
                rebuild = self.took_slots(m) or rebuild
            elif kind == "warnings":  # teacher: a learner changed, in the code, something outside the lesson
                self.took_warnings(m)
                rebuild = True  # (the tab's name counts the ones not seen yet)
            elif kind == "missions":
                if m.get("for"):  # the teacher's learner view
                    self.view_missions[m["for"]] = m
                    rebuild = rebuild or self.tab == "learners"
                    continue
                self.missions = m
                if not self.race.get("brains"):
                    self.autopilot = bool(m.get("autopilot"))
                sig = json.dumps(m, sort_keys=True)
                if sig != self.sig.get("missions"):
                    self.sig["missions"] = sig
                    rebuild = rebuild or self.tab in ("missions", "ai", "card")
            elif kind == "teaching":
                self.teaching = m
                sig = json.dumps(m, sort_keys=True)
                if sig != self.sig.get("teaching"):
                    self.sig["teaching"] = sig
                    rebuild = rebuild or self.tab in ("outcomes", "cards", "learners", "accounts")
            elif kind == "design_result":
                if m.get("design"):
                    self.design = sim.fit_design(dict(m["design"]))
                self.code_changed = self.code_hack = False
                if m.get("ok", True):
                    self.draft = copy.deepcopy(self.design)
                    self.code_shown = None
                    self.entry_text.pop("name_me", None)
                    self.predictor = None  # (the stats changed: predict afresh from the server's next snapshot)
                    self.status_msg = ("Your teacher changed your kart." if m.get("by_teacher") else
                                       "Built! Your kart has its new design.", GREEN)
                    if m.get("by_teacher"):
                        self.banner_note("Your teacher changed your kart", 4)
                    remember("kart_design", {k: self.design[k] for k in list(sim.STATS) + ["colour"] if k in self.design})
                else:
                    self.status_msg = ("Not built: " + "; ".join(m.get("problems", [])), RED)
                rebuild = rebuild or self.tab == "garage" or self.show_code
            elif kind == "ai_card_result":
                if m["ok"]:
                    self.card_msg = ("Sent! The teacher will look at it." + (" Tip: " + " ".join(m["tips"]) if m.get("tips") else ""), GREEN)
                    for k in kh.CARD_FIELDS:
                        self.entry_text.pop(f"card_{k}", None)
                        if f"card_{k}" in self.entries:
                            self.set_entry(f"card_{k}", "")
                else:
                    self.card_msg = ("Not sent: " + " ".join(m.get("problems", [])), RED)
                try:  # show it straight away, even before the panel redraws
                    self.card_text.setText(self.card_msg[0])
                    self.card_text.setFg(self.card_msg[1])
                except Exception:
                    pass
                rebuild = rebuild or self.tab == "ai"
            elif kind == "brain_result":
                text = m.get("error") or ("Brain running: P switches it off" if m.get("ok") else "Brain problem")
                self.banner_note(("Brain: " + text) if m.get("ok") else "Brain problem: " + text, 5)
            elif kind == "restart_client":
                self.restart_window()
            elif kind == "missions_file":  # the missions as a file the teacher can edit (CHANGE 97)
                folder = os.path.join(HERE, "evidence")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, os.path.basename(str(m["name"])))
                with open(path, "w", encoding="utf-8") as f:
                    f.write(m["text"])
                self.banner_note(f"Missions saved on this computer: {path}", 6)
            elif kind == "evidence_csv":  # the teacher's copy of the evidence export
                folder = os.path.join(HERE, "evidence")
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, os.path.basename(str(m["name"])))
                with open(path, "w", encoding="utf-8", newline="") as f:
                    f.write(m["text"])
                self.banner_note(f"Evidence saved on this computer: {path}", 6)
            elif kind == "live_update":  # (teacher) a live code update is waiting on the class server
                self.needs_restart = True
                self.banner_note("A live update is ready on the class server. Warn the class, then press "
                                 "Restart server (Controls).", 12)
                rebuild = True
            elif kind == "notice":
                self.banner_note(m["text"], 12 if m.get("big") else 5, big=bool(m.get("big")))
                if self.tab in ("learners", "accounts"):
                    rebuild = True
            elif kind == "pong":
                self.ping_ms = (time.time() - m["t"]) * 1000
            elif kind == "closed":
                self.connection_lost(m)
        if rebuild:
            self.rebuild_panels(from_game=True)

    def on_race(self, m):
        """The race message: the phase, the places, the results, who has a brain running. Returns whether a
        panel that shows these should redraw."""
        r = self.race
        before = (r["phase"], r["results"], r.get("paused"), r.get("lap_times"))
        r.update(phase=m["phase"], places=m["places"], laps=m["laps"], events=m["events"], results=m["results"],
                 brains=m.get("brains", {}), paused=bool(m.get("paused")),
                 lap_times=m.get("lap_times") or {})  # (the Races tab's lap times: CHANGE 143)
        if m["go_in_ms"] is None:
            r["go_local"] = None if m["phase"] != sim.FLAGS_RACE else r.get("go_local") or 0.0
        else:  # the server's GO moment in our own clock: its time stamp is in our clock through the snapshots
            now = time.perf_counter()
            server_now = self.snaps.clock.server_time(now)
            go_server = m["sm"] / 1000 + m["go_in_ms"] / 1000
            r["go_local"] = now + (go_server - server_now) if server_now is not None else now + m["go_in_ms"] / 1000
        if r["brains"]:
            mine = r["brains"].get(self.my_name, {})
            was, self.autopilot = self.autopilot, bool(mine.get("on"))
            if was != self.autopilot:
                self.predictor = None  # (the server drives: nothing to predict; back on the keys we start afresh)
        changed = (r["phase"], r["results"], r.get("paused")) != before[:3]
        return (changed and self.tab in ("races", "teacher")) or (r["lap_times"] != before[3] and self.tab == "races")

    def frozen(self, now):
        r = self.race
        return r["phase"] != sim.FLAGS_RACE or (r["go_local"] is not None and now < r["go_local"])

    def on_snapshot(self, snap, rx):
        self.snap_seq = snap["seq"]
        self.snaps.push(snap, rx)
        self.race["phase"] = snap["flags"] & 3
        self.lead.feed(snap["flags"] >> 4)
        me = next((e for e in snap["entities"] if e["id"] == self.my_id), None)
        if me is None:
            return
        self.finished = finished = bool(me["flags"] & sim.FLAG_FINISHED)
        if args.no_predict or self.autopilot or finished:
            self.predictor = None
            return
        state = self.full_state(me)
        if self.predictor is None:  # (its numbering carries on from ours: the server ignores a number going back)
            self.set_others(snap)
            self.predictor = predict.Predictor(self.step_fn(), state, ignore=0.05,
                                               log=predict.InputLog(first_seq=self.next_seq))
            self.draw_from = state
            self.smoother.clear()
            self.accum = 0.0  # (no burst of catch-up ticks from the time spent waiting for this)
            return
        if snap["ack"] == 0:
            return  # (the server hasn't applied any input of ours yet: nothing to compare with)
        # (the others as at the acknowledged tick: a replay carries them on; with none, carried on to now)
        ahead = len(self.predictor.log.since(snap["ack"]))
        self.set_others(snap)
        err = self.predictor.correct(state, snap["ack"], sim.STEP, sim.compare)
        moved = self.predictor.moved_from
        if moved is None:
            for _ in range(ahead):
                for o in self.others:
                    sim.coast(o, sim.STEP)
        if moved is not None:  # (the state before the newest tick moves with the correction: the picture between them holds)
            new, f = self.predictor.state, self.draw_from
            self.draw_from = new if err == math.inf or f is None else dict(
                f, x=f["x"] + new["x"] - moved["x"], y=f["y"] + new["y"] - moved["y"], yaw=f["yaw"] + new["yaw"] - moved["yaw"])
        if moved is not None and err != math.inf:
            new = self.predictor.state
            dyaw = math.radians((moved["yaw"] - new["yaw"] + 180) % 360 - 180)
            self.smoother.add((moved["x"] - new["x"], moved["y"] - new["y"], 0.0), dyaw)
            if err > 0.3 and not self.frozen(time.perf_counter()):  # (a bump the server knew of: we hear it)
                self.snd.bump(min(1.0, 0.4 + err * 0.3))
        sent = self.sent_at.get(snap["ack"])
        if sent is not None:
            ms = (rx - sent) * 1000 if rx else None
            if ms is not None:
                self.ctrl_ms = ms if self.ctrl_ms is None else self.ctrl_ms * 0.8 + ms * 0.2

    def full_state(self, e):
        """A snapshot's kart record as the state kart_sim.step wants (with where it is along the track)."""
        seg, s, lat = self.track.locate(e["x"], e["y"], None)
        return dict(e, seg=seg, s=s, lat=lat)

    def step_fn(self):
        track, st, others = self.track, sim.stats_of(self.design), self.others
        reach = self.rules.get("bump", {}).get("distance", sim.BUMP_DISTANCE)
        slow = self.rules.get("bump", {}).get("slowdown", 0.3)

        def step(state, inp, dt):
            damage = bool(self.lesson.get("damage", True))  # (CHANGE 158: real damage, as the lesson has it now)
            n = sim.step(state, inp, dt, track, st, damage)
            for o in others:  # (CHANGE 155: the other karts carried on a tick, and bumped as the race bumps them)
                sim.coast(o, dt)
                sim.bump(n, o, reach, slow, damage)
            n.update(SCHEMA.quantise(n))  # (as the server does: the same numbers next tick)
            return n
        return step

    def set_others(self, snap):
        """(CHANGE 155) The other karts in a snapshot, as copies the prediction moves (in place: step_fn holds the
        list), so our kart against another isn't put right every tick."""
        others = []
        designs = {k["id"]: k.get("design") for k in (getattr(self, "roster", None) or {}).get("karts", [])}
        for e in snap["entities"]:
            if e["id"] != self.my_id:  # (their steering and stats, from the roster's designs: CHANGE 159)
                st = sim.stats_of(designs.get(e["id"]) or sim.default_design())
                others.append({"x": e["x"], "y": e["y"], "yaw": e["yaw"], "v": e["v"], "u": e.get("u", 0.0),
                               "steer": e.get("steer", 0.0), "rate": st["steer"], "top": st["top"], "bg": e.get("bg", 0)})
        self.others[:] = others

    def read_keys(self):
        """The arrows or WASD, Shift and R, as the input the simulation wants. While you type in a text box (or the
        window is behind another) the kart gets nothing: the letters go in the box."""
        if self.mouseWatcherNode is None or self.typing:
            return (0.0, 0.0, 0)
        behind = getattr(self.win, "getProperties", None) and not self.win.getProperties().getForeground()
        if behind and not args.offscreen:
            self.keys_down["drift"] = False
            return (0.0, 0.0, 0)
        down = self.mouseWatcherNode.is_button_down
        k = KeyboardButton
        th = (down(k.up()) or down(k.asciiKey("w"))) - (down(k.down()) or down(k.asciiKey("s")))
        steer = (down(k.left()) or down(k.asciiKey("a"))) - (down(k.right()) or down(k.asciiKey("d")))
        bt = (sim.DRIFT if self.keys_down["drift"] else 0) | (sim.RESPAWN if self.keys_down["respawn"] else 0) | \
            (sim.USE if self.keys_down["use"] else 0)
        self.keys_down["respawn"] = self.keys_down["use"] = False
        pad = self.pad.read()  # (CHANGE 170) a controller: the bottom face button or the right trigger goes, the right
        if pad:                # one or the left trigger brakes, the stick steers, the right shoulder drifts, the left
            if not th:         # shoulder or the left face button uses your item, Back (Minus) respawns
                th = max(pad.rt, float("south" in pad.held)) - max(pad.lt, float("east" in pad.held))
            if not steer:
                steer = -pad.x
            bt |= (sim.DRIFT if "rb" in pad.held else 0) | (sim.RESPAWN if "back" in pad.pressed else 0) | \
                (sim.USE if pad.pressed & {"lb", "west"} else 0)
            if "start" in pad.pressed:
                self.toggle_panel()
        return wire.quantise_input(float(th), float(steer), bt)

    def client_tick(self, now):
        """One predicted tick of our own kart, and its input to the server."""
        if self.predictor is None and not (args.no_predict or self.autopilot or self.finished):
            return  # (nothing to predict from until the first snapshot: inputs sent now would only be unlogged)
        if self.race.get("paused"):
            return  # (CHANGE 175: nothing moves and nothing is sent; the server drains what it has)
        inp = self.read_keys()
        if self.frozen(now):
            inp = (0.0, 0.0, 0)
        if self.predictor is not None:
            self.draw_from = self.predictor.state
            seq = self.predictor.apply(inp, sim.STEP, now)
            prev = self.predictor.log.previous(2)
            self.next_seq = self.predictor.log.next_seq
        else:
            seq, prev = self.next_seq, ()
            self.next_seq = (seq + 1) & 0xFFFF
        self.sent_at[seq] = now
        if len(self.sent_at) > 128:
            for s in sorted(self.sent_at)[:64]:
                del self.sent_at[s]
        net.send(wire.pack_input(seq, self.snap_seq, int(now * 1000) & 0xFFFFFFFF, inp[0], inp[1], inp[2], previous=prev))

    # ---------- every frame ----------
    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        # (a few frames first: simplepbr sets camera_world_position in its own task, later in each frame than this one,
        # so a picture taken in the first frame of a slow start asserted: CHANGE 156)
        if args.screenshot and now - self.start > args.after and task.frame > 2:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()
            self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot)))
            self.userExit()
        if not self.started:  # still on the log-in screen
            return task.cont
        states = {}
        if self.local is not None:
            self.accum = min(0.25, self.accum + dt)
            while self.accum >= sim.STEP:
                self.accum -= sim.STEP
                inputs = {}
                if self.local_brain is not None and not self.local.frozen():
                    inputs[0] = self.local_brain(self.local.karts[0], self.local)
                else:
                    inputs[0] = self.read_keys()
                for kid, level in self.local_cpu.items():
                    th, st_, bt = cpu_brains.drive(level, self.local.karts[kid], self.local)
                    inputs[kid] = (th, st_, bt | kart_items.cpu_use(self.local.karts[kid], self.local))
                self.local.step_all(inputs)
            r = self.local
            cd = r.countdown()
            self.race.update(phase=r.phase, places=r.places(), laps=r.laps,
                             results=r.results() if r.phase == sim.FLAGS_OVER else None,
                             go_local=None if cd is None else now + cd)
            states = r.karts
        elif net is not None:
            self.read_network()
            # (a hitch of up to 15 ticks is caught up (the server would otherwise repeat our last input for every
            # tick we missed: CHANGE 175); a longer freeze is skipped, as a burst of inputs would only queue at the
            # server and make every key press late until the lead controller drained it)
            # (the lead multiplier stretches the time between our ticks: over 1 when the server has too many of our
            # inputs waiting, under 1 when it is running dry, so a key press is applied within a tick or two)
            self.accum = min(15 * sim.STEP, self.accum + dt / self.lead.multiplier())
            while self.accum >= sim.STEP:
                self.accum -= sim.STEP
                self.client_tick(now)
            if now - self.last_ping > 1:
                self.last_ping = now
                send({"type": "ping", "t": time.time()})
            self.send_perf(now)
            blended = self.snaps.latest if args.no_interp else self.snaps.sample(now)
            if blended:
                states = {e["id"]: e for e in blended["entities"]}
            if self.predictor is not None and self.my_id in states:
                # (CHANGE 155) between the last two ticks by the time since the newest: frames don't keep time with
                # the 1/60 s ticks, and whole ticks drew our kart stopping one frame and jumping the next
                mine = between(self.draw_from, self.predictor.state, self.accum / sim.STEP)
                (ox, oy, _), oyaw = self.smoother.offset(dt)
                mine["x"], mine["y"], mine["yaw"] = mine["x"] + ox, mine["y"] + oy, mine["yaw"] + math.degrees(oyaw)
                states[self.my_id] = mine
            if self.newer and self.download_button is None:  # a newer release is out
                self.banner_note(f"Club Coders {self.newer} is out: press the green button to download it", 8)
                self.offer_download()
            if TEACHER:
                self.limits_released()  # (a limit's slider let go: the class server gets the new limits)
            if not TEACHER and now - self.prefs_at > 3:  # keep the learner's settings in their profile
                self.prefs_at = now
                prefs = self.gather_prefs()
                text = json.dumps(prefs, sort_keys=True)
                if text != self.prefs_sent:
                    send({"type": "prefs", "prefs": prefs})
                    self.prefs_sent = text
        self.draw(states, dt, now)
        if self.pending_rebuild and not self.typing:  # typing stopped: now do the redraw that waited
            self.rebuild_panels()
        if self.panel_bar and self.last_aspect != self.getAspectRatio():  # (the window resized: the body's cut-off moves)
            self.place_panel()
        return task.cont

    def item_hits(self, hits):
        """(CHANGE 159) A shot or a slick reached our kart: a note, and the bump's sound (a shield: a lighter one)."""
        for kid, what, blocked in hits:
            if kid != self.my_id:
                continue
            words = {"shot": "a shot", "homing": "a homing shot", "oil": "an oil slick"}.get(what, what)
            self.banner_note(f"Your shield stopped {words}!" if blocked else f"Hit by {words}!", 2)
            self.snd.bump(0.5 if blocked else 1.0)

    def damage_readout(self, me):
        """(CHANGE 158) Your kart's damage for the panel (None with damage off) and whether the PIT box is mending it."""
        if me is None or not self.lesson.get("damage", True):
            return None, False
        damage = sim.damage_of(me)
        seg, s, lat = self.track.locate(me["x"], me["y"], me.get("seg"))
        return damage, any(damage) and abs(me["v"]) < sim.PIT_SPEED and self.track.in_pit(s, lat)

    def sync_designs(self, designs):
        for kid, d in designs.items():
            if kid not in self.karts or self.designs.get(kid) != d:
                if kid in self.karts:
                    self.karts[kid].destroy()
                self.karts[kid] = kart_gfx.KartVisual(self.render, d)
                self.karts[kid].set_label(d["name"], tuple(c / 255 for c in d["colour"]) + (1.0,))
                self.designs[kid] = dict(d)
                self.colours[kid] = tuple(c / 255 for c in d["colour"])
        for kid in list(self.karts):
            if kid not in designs:
                self.karts.pop(kid).destroy()
                self.designs.pop(kid, None)

    def draw(self, states, dt, now):
        me = states.get(self.my_id)
        go = self.race["go_local"] if self.race["phase"] == sim.FLAGS_RACE else None
        # (the dash pads pulse; on ultra the pond's ripples move and the start lights follow the countdown: CHANGE 151)
        self.track_vis.update(now - self.start, None if go is None else go - now)
        if getattr(self, "items_vis", None) is not None:  # (CHANGE 159) the power-ups, as late as the karts
            if self.local is not None:
                if self.local.items is not None:
                    state = self.local.items.state()
                    self.item_hits(state["hits"])
                    self.items_vis.update(dt, state)
            else:
                t = self.snaps.clock.server_time(now)
                self.items_vis.update(dt, None if t is None else self.items_vis.at((t - self.snaps.delay) * 1000.0))
        for kid, k in states.items():
            vis = self.karts.get(kid)
            if vis is None:
                continue
            seg, s, lat = self.track.locate(k["x"], k["y"], k.get("seg"))
            z = self.track.height(s)
            flags = k.get("flags", 0)
            vis.update(k["x"], k["y"], z, k["yaw"], k.get("steer", 0.0), k["v"], k["u"],  # (steer: CHANGE 157)
                       bool(flags & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R)), bool(flags & sim.FLAG_BOOSTING), dt,
                       sim.damage_of(k), k.get("shield", 0) > 0, bool(flags & sim.FLAG_BRAKING))  # (CHANGE 158, 159, 171)
        # (CHANGE 172) the headlight beams: your kart's, then the nearest to the camera
        cam = self.camera.getPos(self.render)
        near = sorted((v for kid, v in self.karts.items() if kid in states and kid != self.my_id),
                      key=lambda v: (v.root.getPos(self.render) - cam).lengthSquared())
        kart_gfx.headlights(([self.karts[self.my_id]] if self.my_id in self.karts and self.my_id in states else []) + near)
        if me is not None:
            seg, s, lat = self.track.locate(me["x"], me["y"], me.get("seg"))
            if self.my_id in self.karts:
                self.cam_rig.hood = self.karts[self.my_id].hood  # (CHANGE 173: over a car's bonnet)
            self.cam_rig.update(dt, me["x"], me["y"], self.track.height(s), me["yaw"], me["v"], self.track)
        r = self.race
        places = r["places"] or sorted(states)
        place = places.index(self.my_id) + 1 if self.my_id in places else 0
        cd = None if r["go_local"] is None else max(0.0, r["go_local"] - now)
        if cd is not None and cd <= 0 and now - r["go_local"] > 1.5:
            cd = None
        self.sounds(me, cd if r["phase"] == sim.FLAGS_RACE else None, place, now)
        self.laps(me, now)
        minimap = [(k["x"], k["y"], self.colours.get(kid, (1, 1, 1)), kid == self.my_id) for kid, k in states.items()]
        self.screen.update(min(r["laps"], (me["lap"] if me else 0) + 1), r["laps"], place, len(states),
                           abs(me["v"]) * 3.6 if me else 0.0, cd if r["phase"] == sim.FLAGS_RACE else None,
                           bool(me and me.get("flags", 0) & sim.FLAG_WRONG_WAY), me["charge"] if me else 0,
                           minimap, r["results"], *self.damage_readout(me),
                           kart_items.ITEMS[me["item"] - 1] if me and me.get("item") else None)  # (CHANGE 159)
        text = f"{self.clock.getAverageFrameRate():.0f} fps   gfx {self.gfx_tier}"
        if net is not None:
            rep = self.snaps.report()
            text += f"   ping {self.ping_ms:.0f} ms" + (f"   keys {self.ctrl_ms:.0f} ms" if self.ctrl_ms else "")
            text += f"   blend {rep['delay_ms']} ms" + (f"   stalls {rep['stalls']}" if rep["stalls"] else "")
            if self.predictor is not None:
                text += f"   corrections {self.predictor.corrections}"
            if self.autopilot:
                text += "   AUTOPILOT (P)"
            if r.get("paused"):
                text = "PAUSED     " + text
        self.screen.status(text)
        self.overlay.layout()
        waiting = (r["phase"] == sim.FLAGS_GRID and self.local is None and now > self.note_until)
        self.overlay.note("Waiting for the teacher to start the race" if waiting else
                          self.note_text if now < self.note_until else "", self.note_big and now < self.note_until)
        self.overlay.set_view(f"view: {self.cam_rig.name}  (V to change)" + ("   typing - Esc to stop" if self.typing else ""))

    def laps(self, me, now):
        """Your lap times: told as you cross the line; offline, the best on each track is kept on this computer."""
        r = self.race
        if me is None or r["phase"] != sim.FLAGS_RACE or r["go_local"] is None:
            self.lap_seen, self.lap_started = None, None
            return
        lap = me.get("lap", 0)
        if self.lap_seen is None:  # the race is on: the clock starts at GO
            self.lap_seen, self.lap_started = lap, r["go_local"]
            saved = SETTINGS.get(f"kart_best_{self.track_name}")
            self.best_lap = float(saved) if isinstance(saved, (int, float)) else None
            return
        if lap > self.lap_seen and now > self.lap_started + 5:
            took = now - self.lap_started
            self.lap_seen, self.lap_started = lap, now
            best = self.best_lap is None or took < self.best_lap
            if best:
                self.best_lap = took
                if self.local is not None:  # (offline practice: the record stays; online the teacher's league will)
                    remember(f"kart_best_{self.track_name}", round(took, 2))
            self.banner_note(f"Lap {lap}: {took:.1f} s" + ("   NEW BEST" if best else f"   (best {self.best_lap:.1f} s)"), 4)

    def sounds(self, me, cd, place, now):
        """What you hear: your engine, your tyres, the countdown, a boost starting, the finish."""
        racing = self.race["phase"] == sim.FLAGS_RACE and not self.frozen(now)
        if me is not None:
            flags = me.get("flags", 0)
            top = sim.stats_of(self.design)["top"]
            boosting = bool(flags & sim.FLAG_BOOSTING)
            self.snd.update(now, me.get("v", 0.0), top, bool(flags & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R)), boosting,
                            racing)
            if boosting and not self.was_boosting:
                self.snd.boost()
            self.was_boosting = boosting
            finished = bool(flags & sim.FLAG_FINISHED)
            if finished and not self.was_finished:
                self.snd.finish(now, first=place == 1)
            self.was_finished = finished
        n = None if cd is None else int(math.ceil(cd - 1e-6))
        if n != self.cd_last and n is not None and 0 <= n <= 3:
            self.snd.countdown(n)
        self.cd_last = n

    def show_perf(self, now):
        """Teacher: the line under the Learner view's names saying how that learner's window is doing."""
        lab = getattr(self, "perf_label", None)
        if lab is None or now - getattr(self, "perf_shown", 0.0) < 1:
            return
        self.perf_table_update((self.roster or {}).get("perf", {}))  # (the Who is here table: CHANGE 143)
        if self.perf_frame.isEmpty():  # (the panel has been redrawn: the label went with it)
            self.perf_label = None
            return
        self.perf_shown = now
        lab.setText(interp.perf_line(self.view_name, (self.roster or {}).get("perf", {})))

    def send_perf(self, now):
        """Every few seconds: how this window is doing, for the teacher's grid (frame rate, ping, graphics tier,
        network stalls, the blending delay, the key delay and the prediction's corrections)."""
        if TEACHER:
            self.show_perf(now)
        if now - self.perf_at < 3:
            return
        self.perf_at = now
        rep = self.snaps.report()
        perf = {"type": "perf", "fps": round(self.clock.getAverageFrameRate()), "ping": round(self.ping_ms),
                "tier": self.gfx_tier, "stalls": rep["stalls"], "delay": rep["delay_ms"], "underruns": rep["underruns"],
                "ctrl": None if self.ctrl_ms is None else round(self.ctrl_ms),
                "corr": self.predictor.corrections if self.predictor else None}
        send(perf)
        if args.offscreen:  # (tests read it from the console)
            print("perf", json.dumps(perf), f"lead {self.lead.multiplier():.2f}", flush=True)

    def connection_lost(self, m):
        if m.get("code") == 4005:
            self.banner_note("You logged in again in another window, so this one has stopped.", 3600)
            return
        if m.get("code") in kh.STOP_CODES:  # wrong code or password, deleted, or an old version: retrying won't help
            self.banner_note(m.get("reason") or "The server closed the connection.", 3600)
            if m.get("code") == 4006:
                self.offer_download()
            if m.get("code") == 4009:  # the teacher pressed Stop: this window closes in a few seconds
                self.banner_note("The session has ended. This window will close.", 3600)
                self.taskMgr.doMethodLater(5, lambda t: self.userExit(), "session_over")
            return
        self.banner_note("The class server is restarting: reconnecting..." if m.get("code") == 1012 else
                         "Lost the connection: reconnecting...", 3600)  # (1012: CHANGE 160)
        self.reconnecting = True
        if self.reconnect_thread is not None and self.reconnect_thread.is_alive():
            return

        def work():  # keep trying every 2 seconds; the server's welcome comes through the inbox
            time.sleep(1.0 + random.random() * 2.0)  # (not the whole class at the same moment: CHANGE 160)
            while not net.reconnect():
                time.sleep(1.5 + random.random())
        self.reconnect_thread = threading.Thread(target=work, daemon=True)
        self.reconnect_thread.start()


if __name__ == "__main__":
    Lab().run()
