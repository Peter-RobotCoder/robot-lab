"""Fight Lab window for learners and the teacher. The fights run on fight_server.py.

Learner:  python fight_client.py                (log in with a username and password in the window)
Teacher:  python fight_client.py --name "Mr P" --teacher
Class server: add --host wss://... Learners type the class code once (it is remembered on that computer); the
teacher's code comes from --code or FIGHTLAB_TEACHER_CODE; on a laptop test server it is the demo code, and on the
class server it comes from teacher_settings.json next to this file (never in git).

Logging in: a new username makes a new profile. Everything is saved to it (fighter, missions, brain,
camera view), so after a dropped connection the window reconnects by itself, and next lesson the
learner logs in with the same username and password to carry on.

Fighting:  Arrow keys move (towards / away from the other fighter, and up / down to SIDESTEP round them)
           A punch (your combo: press again each time a hit lands)   S kick (forward + S: high kick)
           D special (uses 50 energy)   W throw   Space jump   Shift block (hold)   X crouch (hold)
           crouch + kick = low sweep   crouch + Shift = low block   jump + A or S = jump kick
Panels:    M missions   G garage   I AI request card   C your fighter as code (edit it, then Apply)
           T teacher panels   H help
Brain:     U upload brains/my_brain.py   P autopilot on/off (your brain fights)
Camera:    V change view (fight camera, my fighter, over the shoulder, ring, all rings)   O all rings
           drag with the right mouse button (or Q / E) to swing round the ring and tilt   Home resets the view
           [ and ] watch another ring   mouse wheel or + / - zoom   B the rings list
           L watch the next fighter (round everyone in the ring you are watching, then the next ring's, and back to
           your own: pick a learner with L, then change the view of them with V)
Teacher:   Shift+F fixes your own fighter (full health, on their feet, out of a knockout; F alone is the cartwheel)
Typing:    while you type in a text box, keys go into the box (not the game). Click away or press Esc to stop.
           In the code panel, click or drag to select; APPLY CODE applies your code, Return makes a new line.
"""
import argparse
import ast
import copy
import json
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

import fight_version  # (first: this records the code this window is running, before anything can change it)
sys.path.insert(0, fight_version.ENGINE_HOME)  # (the engine package, shared by every game: engine/ beside the games)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="", help="username (learners are asked in the window if it's left out)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--host", default=None,
                help="server address (default: this computer); 'class' = the one in teacher_settings.json")
ap.add_argument("--code", help="class code (the demo codes on a laptop test server)")
ap.add_argument("--experience", type=int, help="play this experience on your own: Fight Lab's own server starts on "
                                               "this laptop (engine/experience.py; the app's EXPERIENCES button)")
ap.add_argument("--window", help="the window: 1280x720, 1600x900 ... 3840x2160 or full "
                                 "(else this computer's last choice; CHANGE 126)")
ap.add_argument("--gfx", choices=["auto", "mesh", "lines", "basic", "low", "medium", "high", "ultra"], default="auto",
                help="graphics: auto picks for this computer (and remembers); low or basic on old laptops")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--no-interp", action="store_true", help="draw each snapshot as it arrives (no blending between them)")
ap.add_argument("--no-ahead", action="store_true", help="draw your fighter as sent, not ahead (engine/ahead.py: CHANGE 167)")
ap.add_argument("--x", type=int, help="window position (left edge)")
ap.add_argument("--tab", help=argparse.SUPPRESS)
ap.add_argument("--show-code", action="store_true", help=argparse.SUPPRESS)  # (tests: open the code panel)
ap.add_argument("--card", help=argparse.SUPPRESS)
ap.add_argument("--view-tab", help=argparse.SUPPRESS)  # (tests: the Learner view opens on this tab)  # (tests: the teacher's AI cards tab opens on "edit" or a card's id)
ap.add_argument("--scroll", type=float, help=argparse.SUPPRESS)  # (tests: slide the side panel this far after 3 s)
ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
ap.add_argument("--ticket", help=argparse.SUPPRESS)  # (from the club desk: the app has logged this person in)
args = ap.parse_args()
if os.environ.get("FIGHTLAB_LOGIN") and not args.name:  # reopened by itself (to load code changes): same login
    try:
        args.name, args.password, *rest = json.loads(os.environ.pop("FIGHTLAB_LOGIN"))
        args.ticket = rest[0] if rest and rest[0] else args.ticket
    except ValueError:
        pass
TEACHER = args.teacher
HERE = os.path.dirname(os.path.abspath(__file__))
TEACHER_SETTINGS = os.path.join(HERE, "teacher_settings.json")  # the teacher's laptop only: never in git
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "FightLab")
from engine import editor as code_editor  # noqa: E402  (the engine: shared by every game)
from engine import hud, reopen  # noqa: E402
from engine import garage, schema  # noqa: E402
from engine.hud import DARK, button, check, label, load_json, remember, text_button, word  # noqa: E402,F401
from engine.hud import YELLOW, WHITE, GREY, RED, GREEN, BLUE, ORANGE, PANEL, ON, OFF, BOX, HANDLE  # noqa: E402,F401
SETTINGS = hud.setup(SETTINGS_DIR, sys.modules[__name__])  # this computer's settings; this module's colours follow the look
BRAINS = (os.path.join(os.path.dirname(sys.executable), "brains", "fightlab") if fight_version.FROZEN  # (the built
          else os.path.join(HERE, "brains"))  # app keeps each game's brains folder beside the exe: brains\fightlab)




from engine import experience  # noqa: E402
SOLO = None  # (CHANGE 210) an experience on your own: Fight Lab's server on this laptop, started by this window
if args.experience and not args.teacher:
    SOLO = experience.solo_start(HERE, "fight_server.py", "fightlab", args.experience, "FIGHTLAB_DATA",
                                 fight_version.FROZEN)
    # (the window never stops it: the server saves and stops by itself 30 s after the window has gone, and a window
    # that reopens itself, a Graphics choice, finds it still there with the run kept: engine/experience.py)
    if not experience.solo_ready(SOLO):
        raise SystemExit("Fight Lab's server on this laptop didn't start: " + experience.solo_last_words(SOLO))
    args.host, args.code = SOLO["host"], None
    args.name, args.password = args.name or experience.SOLO_NAME, experience.SOLO_PASSWORD
if args.host == "class":  # the class server's address, from the teacher's settings
    args.host = load_json(TEACHER_SETTINGS).get("server") or fight_version.ONLINE_SERVER or fight_version.LOCAL_SERVER
elif args.host is None:  # a learner's last choice on the login screen, or this computer
    where = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("where")
    args.host = {"local": fight_version.LOCAL_SERVER, "online": fight_version.ONLINE_SERVER}.get(
        where if not TEACHER else None) or fight_version.SERVER
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))  # a laptop test server
from engine import try_local  # noqa: E402
# Try it on this laptop (see try_local): the teacher's window, opened on a test server here to look at this
# laptop's game before it is made live for the class. It knows how to go back to the class.
TRY = try_local.unpack(os.environ.pop("FIGHTLAB_TRY", "")) if args.teacher and LOCAL else None
from engine import club_ticket  # noqa: E402
if args.ticket:  # the club desk has logged this person in: their name is in the ticket (the server checks it)
    args.name = (club_ticket.peek(args.ticket) or {}).get("name") or args.name
if args.code or args.ticket:
    code = args.code or ""
elif TEACHER:
    # the saved code is the class server's (saved with its address): a laptop test server has the demo code
    code = (os.environ.get("FIGHTLAB_TEACHER_CODE") or ("TEACH99" if LOCAL else "")
            or load_json(TEACHER_SETTINGS).get("teacher_code"))
    if not code:
        raise SystemExit("The teacher code is needed: put it in teacher_settings.json next to fight_client.py "
                         '(for example {"teacher_code": "..."}) or use --code.')
else:
    # (the remembered code is the online class server's; a laptop test server has the demo code)
    code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
name = args.name or ("Teacher" if TEACHER else "")
net = None  # the connection to the server, made when you log in

title = f"Fight Lab - {'TEACHER' if TEACHER else 'LEARNER'}" + (f" ({name})" if name else "")
if SOLO:
    title = f"Fight Lab - EXPERIENCE {args.experience}"
if TRY:
    title += " - TRYING ON THIS LAPTOP"
x = args.x if args.x is not None else (40 if TEACHER else 1360)
from engine import gfx_tiers  # noqa: E402
GFX = gfx_tiers.resolve(SETTINGS_DIR, args.gfx, gfx_tiers.TIERS)  # (auto: this computer's saved tier, else what its
# driver suggested; Fight Lab draws all seven tiers, mesh to ultra, as Kart Lab and Robot Lab do: CHANGE 147)
loadPrcFileData("", hud.window_arg(args.window, x) + f"window-title {title}\n"  # (the size: CHANGE 126)
                    + gfx_tiers.prc_for(GFX))  # (texture size, mipmaps, multisamples: read as the window opens)
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame, DirectSlider  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, Point3, TextNode, Vec3, WindowProperties  # noqa: E402

import cpu_brains  # noqa: E402
import fight_fx  # noqa: E402
import fight_gfx  # noqa: E402
import fight_missions as fm  # noqa: E402
import fight_sim as sim  # noqa: E402
import fight_sound  # noqa: E402
from engine import rw_sound  # noqa: E402
from fight_camera import FightCamera  # noqa: E402
import fight_model  # noqa: E402
from fight_gfx import StageVisual  # noqa: E402
from fight_hud import FightHUD  # noqa: E402
from engine.net import Net  # noqa: E402
from engine import interp  # noqa: E402
from engine import ahead  # noqa: E402  (CHANGE 167: your fighter's footwork drawn at once)
from engine import gamepad  # noqa: E402  (CHANGE 170: a controller fights)
from engine.experience_hud import ExperienceHud  # noqa: E402  (CHANGE 210)

CODE_ROWS = 19     # lines of code the code panel shows at once (longer code scrolls)
CODE_PANEL = (-0.86, 0.12, -0.85, 0.36)  # the code panel in its first place: left, right, bottom, top
SWATCHES = [(220, 60, 50), (240, 140, 30), (240, 200, 40), (60, 190, 90), (60, 130, 230), (180, 90, 230),
            (230, 90, 170), (230, 230, 230)]
HAIR_SWATCHES = [(20, 16, 14), (60, 36, 22), (110, 62, 32), (140, 50, 25), (190, 95, 40), (215, 180, 110),
                 (230, 225, 210), (60, 110, 200)]  # black, dark brown, chestnut, auburn, ginger, blonde, platinum, blue
TRIM_SWATCHES = [(30, 30, 36), (140, 145, 155), (220, 220, 225), (200, 160, 60), (160, 90, 40), (60, 60, 140),
                 (120, 30, 30), (40, 100, 60)]   # Robin's trim: gunmetal, steel, chrome, brass, copper, blue, red, green
LIGHT_SWATCHES = [(255, 90, 25), (255, 40, 40), (90, 230, 255), (60, 255, 120), (255, 230, 80), (200, 120, 255),
                  (255, 255, 255), (255, 0, 160)]
PRETTY = {"walk_speed": "Walk speed", "sidestep_speed": "Sidestep speed", "jump_height": "Jump height",
          "attack_speed": "Attack speed", "size": "Size", "points_table": "Points table",
          "choose_special": "Choose special", "combo_editor": "Combo editor", "name_and_colour": "Name and colour",
          "body_choice": "Robot or human", "code_view": "Code view", "stats_readout": "Stats readout",
          "bosses": "Play as a boss", "fighting_style": "Fighting style", "brains": "Autopilot (U and P)"}
HAZARD_NAMES = {"ring_out": "Ring-outs (no ropes)", "electric_ropes": "Electric ropes", "fire_jets": "Fire jets",
                "slippery": "Slippery ice", "spikes": "Spikes"}
LEARNER_TABS = [("missions", "Mission"), ("garage", "Garage"), ("ai", "AI card"), ("card", "My card"),
                ("mods", "Mods"), ("settings", "Settings")]  # (one key, I, opens and closes the HUD: CHANGE 103)
TEACHER_TABS = [("teacher", "Controls"), ("mods", "User mods"), ("matches", "Matches"), ("learners", "Learners"),
                ("accounts", "Accounts"), ("outcomes", "Outcomes"), ("cards", "AI cards"), ("changes", "Changes"),
                ("limits", "Limits"), ("warnings", "Warnings"), ("garage", "My fighter"), ("settings", "Settings")]  # (two rows)
STOP_CODES = (4001, 4004, 4006, 4007, 4008, 4009, 4010, 4011)  # the server said no: wrong code or password,
# old version, deleted, the session ended, the group hasn't started, a ticket that ran out
TARGETS = {"fighter": "Their fighter", "stage": "The stage", "rules": "The rules", "game": "The whole game"}
APP = None  # the window (so any button click can end typing in a text box)
AI_RULES = ("Only the teacher uses the AI.  Never put personal information in a request.\n"
            "AI can be wrong: you test the code and must be able to explain it.\n"
            "Say where AI helped (the tool and the date).")
CARD_FIELDS = ("goal", "variables", "test", "predict")
PRESS_KEYS = {"a": "punch", "s": "kick", "d": "special", "w": "throw", "space": "jump",
              "f": "cartwheel"}  # (F: the cartwheel kick user mod; it does nothing while the mod is off)
# (CHANGE 170) a controller's buttons, by where they are: left punch, bottom kick, right special, top jump, right
# shoulder throw, right trigger the cartwheel kick (the user mod)
PAD_PRESS = {"west": "punch", "south": "kick", "east": "special", "north": "jump", "rb": "throw", "rt": "cartwheel"}
PAD_ORDER = ("west", "south", "east", "north", "rb", "rt")
# (CHANGE 210) where an experience is drawn (engine/experience_hud.py), clear of Fight Lab's own HUD. The box with the
# objective and the XP: under the names and health bars (which come down to 0.78), between the rings box (which ends
# at x -0.62) and the side panel (from x 0.78), a little smaller to fit there. The coach's words: above the training
# readout (-0.77), the energy meters and the key list, and beside the side panel when it is open (as the fight HUD
# moves beside it), clear of the events at the bottom left; the toasts and the result card go with them.
XHUD_TOP, XHUD_BOTTOM, XHUD_X, XHUD_SCALE = -0.25, 0.27, 0.08, 0.94
XHUD_X_PANEL = -0.19  # (the coach's words with the side panel open: their box's right edge at 0.76)
ATTACK_ANIMS = {"punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam",
                "cartwheel"}


def send(msg):
    if net is not None:
        net.send(msg)


class Lab(hud.HudKit, ShowBase):
    UNIT, CPU_VIEW = "fighter", "Computer fighter"
    VERSION, LIVE_ID = fight_version.VERSION, fight_version.live_id()
    FIRST_TAB = "teacher" if TEACHER else "missions"
    teacher = TEACHER
    CODE_PANEL, CODE_ROWS = CODE_PANEL, CODE_ROWS
    reflections = tuple(fm.REFLECTIONS)
    user_mods = sim.USER_MODS
    STAGE_WORD = "STAGE"
    GFX_TIERS = gfx_tiers.TIERS          # (CHANGE 147: the Settings tab's Graphics row and the class maximum's)
    LINE_COLOURS = fight_gfx.LINE_COLOURS
    AHEAD_ROW = "your fighter's steps are drawn as you press the keys"  # (CHANGE 167: the Settings tab's Movement row)
    LIMITS_TITLE = "FIGHTER LIMITS"
    LIMITS_NOTE = "Size: 100 is the standard size; 80 to 120 is as far as a fighter can go."

    def __init__(self):
        super().__init__()
        self.disableMouse()
        global APP
        APP = self
        hud.setup_app(self, send)
        self.init_hud()  # (the engine's HUD kit: text boxes, the side panel, settings, the code panel's place)
        self.my_name = name
        self.code_state = {"lines": [], "cursor": [0, 0], "scroll": 0}  # the code panel's text, kept while it is closed
        self.schema = sim.schema()  # the fighter's variables: the code panel (and the garage's tables) come from it
        self.code_changed = False  # the design holds a value changed in the code (Mission 1: hack the code)
        self.code_hack = False  # the design holds a value changed in the code that this mission's garage hides
        gfx_tiers.detect(self, SETTINGS_DIR)  # (the window is open: what the driver says, for the next run's tier)
        fight_gfx.init(self, GFX, line_colour=self.line_colour)
        self.gfx_tier = fight_gfx.tier()  # (the tier in use: lower than GFX when the driver couldn't run that one)
        self.fx = fight_fx.Effects(self.render, "low" if self.gfx_tier in ("basic", "low") else self.gfx_tier)
        self.snd = fight_sound.FightSounds(self, on=not args.offscreen)
        self.muted = False
        self.pending_rebuild = False  # a panel redraw waiting until typing stops
        self.started = False
        self.login_panel = None
        self.delete_armed = None      # teacher: the account whose Delete button says "Sure?"
        self.newer, self.download_button = None, None
        if fight_version.FROZEN or not LOCAL:
            self.check_for_update()
        self.accept("escape", self.escape)
        self.accept("mouse1", self.stop_typing)  # clicking the ring (not a panel) stops typing
        self.accept("tab", self.tab_key, [1])           # Tab: on to the next text box
        self.accept("shift-tab", self.tab_key, [-1])    # ...and Shift+Tab: back to the one before
        self.start = self.last = time.perf_counter()
        if TEACHER or args.ticket or (args.name and args.password):
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
            net = Net(args.host, username, code, password=password, version=fight_version.VERSION,
                      **({"ticket": args.ticket} if args.ticket else {}))
        except OSError:
            net = None
            return f"Can't reach the Fight Lab server ({args.host}). Is it running?"
        except Exception as e:  # e.g. the secure connection couldn't be set up
            net = None
            return f"Can't connect to the Fight Lab server ({args.host}): {e}"
        welcome, problem = self.wait_for("welcome")
        if welcome is None:
            net = None
            if "Out of date" in problem:
                self.offer_download()
            return problem
        name = welcome["name"]
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
        label(f, "FIGHT LAB  -  TEACHER", 0, 0.24, 0.06, YELLOW, TextNode.ACenter)
        label(f, error, 0, 0.1, 0.034, RED, TextNode.ACenter, wrap=36)
        hint = ("Another teacher window is open (on this computer or another): close it, then try again. If none is, "
                "restart the game server (on the server: sudo systemctl restart robotlab@class1)."
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
        label(f, "FIGHT LAB", 0, 0.34, 0.08, YELLOW, TextNode.ACenter)
        online = bool(fight_version.ONLINE_SERVER)
        if online:  # (only when the club has a Fight Lab class server)
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
        args.host = fight_version.LOCAL_SERVER if local else fight_version.ONLINE_SERVER
        code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
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
    def start_game(self, welcome):
        if self.check_code(welcome):
            return
        if self.login_panel is not None:
            self.login_panel.destroy()
            self.login_panel = None
        self.entries, self.typing = {}, None
        props = WindowProperties()
        props.setTitle(f"Fight Lab - EXPERIENCE {args.experience}" if SOLO else
                       f"Fight Lab - {'TEACHER' if TEACHER else 'LEARNER'} ({name})")
        if self.win is not None and not args.offscreen:
            self.win.requestProperties(props)
        self.started = True
        self.gfx_monitor = getattr(self, "gfx_monitor", None) or fight_gfx.start_monitor(
            self, SETTINGS_DIR, args.gfx, self.banner_note, judge=not LOCAL)  # (a laptop test shares the GPU)
        self.lesson, self.rules = welcome["lesson"], welcome["rules"]
        self.obey_gfx_max()
        self.design = welcome["design"]          # the last design the server accepted
        self.draft = copy.deepcopy(self.design)  # what is being edited in the garage
        self.class_list, self.missions, self.teaching, self.tournament = [], None, None, None
        self.sig = {}                            # what each panel was last drawn from
        self.card_checks = {"privacy": False, "review": False, "credit": False}
        self.card_msg = ("", WHITE)
        self.card_target = "fighter"
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
        self.match_pick = []     # teacher: the two names being put in a match
        self.needs_restart = bool(welcome.get("live_ready"))  # a code change (or a live update) waits for a restart
        self.view_drafts, self.view_missions = {}, {}
        self.code_shown, self.code_msg = None, ("", GREY)
        self.cam = FightCamera(self, "fight")
        self.stage_vis, self.stage_drawn = None, None
        self.fighters, self.roster, self.my_id, self.names = {}, None, None, {}
        self.ring_of = {}        # fighter id -> ring index
        self.watch = None        # the ring being watched (None = your own)
        self.focus = None        # (CHANGE 183) the fighter the camera follows (L), None = your own
        self.state, self.ping_ms, self.status_msg = None, 0.0, ("", WHITE)
        self.pings, self.rtt = [], None  # (CHANGE 175) the last round trips and the smoothed one drawing ahead uses
        self.fighter_keys = {}           # (CHANGE 175) each drawn fighter's design and owner: rebuilt only on a change
        # the server's snapshots, drawn a little in the past and blended (engine.interp); latest is the newest as sent
        self.snaps, self.latest = interp.Snapshots(interp.FIGHT_SPEC), None
        self.pad = gamepad.Pad(self)  # (CHANGE 170) a USB or Bluetooth controller
        self.ahead, self.move = ahead.FighterAhead(), {}  # (CHANGE 167) your fighter drawn ahead; footwork from the roster
        self.punch = {}  # (CHANGE 193) ...and the move its punch button starts, with its timing
        self.ctrl_seq, self.ctrl_sent, self.ctrl_ms = 0, {}, None  # numbered controls, and the measured control delay
        self.perf_at = 0.0
        self.fx_waiting = []
        self.reconnect_thread = None
        self.last_anim, self.last_phase, self.last_winner, self.last_banner = {}, {}, {}, {}  # (for sounds)
        self.last_send = self.last_ping = 0.0
        self.last_control = None
        self.panel = self.code_panel = None
        self.tab = args.tab or ("teacher" if TEACHER else "missions")
        if args.tab == "outcomes_edit":  # (tests: the Outcomes tab on its missions editor)
            self.tab, self.editing_missions = "outcomes", True
        self.show_code = bool(args.show_code)
        self.reconnecting = False
        if args.scroll:
            self.taskMgr.doMethodLater(3, lambda t: (setattr(self, "panel_scroll", args.scroll), self.place_panel())
                                       and None, "test scroll")
        self.restore_prefs(welcome.get("prefs", {}))
        tabs = [t for t, _ in (TEACHER_TABS if TEACHER else LEARNER_TABS)]
        if not args.tab and getattr(self, "last_tab", None) in tabs:  # (CHANGE 103: back on the tab last used)
            self.tab = self.last_tab
            self.rebuild_panels()
        send({"type": "slot", "do": "list"})  # (my saved designs: CHANGE 83)
        for key, action in PRESS_KEYS.items():  # fighting keys: sent the moment they're pressed
            self.key(key, self.press, action)
        self.key("i", self.toggle_panel)  # (CHANGE 103: the one HUD key)
        self.key("c", self.toggle_code)
        self.key("h", self.toggle_help)
        self.key("u", self.upload_brain)
        self.key("p", self.autopilot_key)
        self.key("v", self.cam.cycle)
        self.key("l", self.cycle_focus)  # (CHANGE 183) the camera follows the next fighter
        if TEACHER:
            self.key("shift-f", self.fix_mine)  # (CHANGE 182) the teacher's own fighter mended (F alone: cartwheel)
        self.key("q", self.cam.turn, 20)       # swing the view round the ring (or drag with the right mouse button)
        self.key("e", self.cam.turn, -20)
        self.key("q-repeat", self.cam.turn, 6)
        self.key("e-repeat", self.cam.turn, -6)
        self.key("home", self.cam.reset_view)
        self.key("o", self.cam.set_mode, "all")
        self.key("n", self.toggle_mute)
        self.key("b", self.toggle_rings)
        self.key("[", self.watch_ring, -1)
        self.key("]", self.watch_ring, 1)
        for key, factor in (("=", 0.8), ("+", 0.8), ("-", 1.25), ("=-repeat", 0.9), ("--repeat", 1.11)):
            self.key(key, self.cam.wheel, factor)
        for key, factor, step in (("wheel_up", 0.88, -1), ("wheel_down", 1 / 0.88, 1)):
            self.key(key, self.wheel, factor, step)  # (the wheel slides a tall side panel, or zooms)
        self.key("page_up", self.slide_panel, -1)
        self.key("page_down", self.slide_panel, 1)
        self.hud()
        if getattr(self, "xhud", None) is None:  # (CHANGE 210) an experience, drawn over the ring when one is on
            self.xhud = ExperienceHud(self, send, TEACHER, top=XHUD_TOP, bottom=XHUD_BOTTOM)
            self.xhud.top_node.setPos(XHUD_X, 0, 0)
            self.xhud.top_node.setScale(XHUD_SCALE)
            self.place_xhud()
        self.try_starting = None  # (teacher: a test server on this laptop is starting: see try_here)
        if TRY:
            self.begin_try()
        if TEACHER and os.environ.get("CLUBCODERS_TRY_TEST"):  # (tests: there and back by itself, noting each step)
            self.taskMgr.doMethodLater(4, self.try_test, "try test")
        self.rebuild_panels()
        if TEACHER:
            self.push_mod_makers()
        self.start = self.last = time.perf_counter()
        self.prefs_at = self.start
        if welcome.get("new_profile"):
            self.banner_note(f"Welcome, {name}! Your profile is made: next time log in with the same username "
                             "and password.", 7)
        if args.selftest:  # press the garage's buttons the way a learner would and build, then hack the code
            def gui(t):  # (Mission 1's objectives a, b and c: a string, two integers and a list, with the GUI)
                self.draft["name"] = "Rocky"
                self.draft["settings"]["walk_speed"], self.draft["settings"]["size"] = 90, 110
                self.set_colour([60, 190, 90])
                self.send_design()

            def hack(t):  # (objective d: a value changed in the code editor)
                self.show_code = True
                self.rebuild_panels()
                lines = self.code_state["lines"]
                lines[:] = [("jump_height: int = 95" if line.startswith("jump_height") else line) for line in lines]
                self.build_from_code()

            def report(t):
                done = ", ".join(f"{x['id']}={'done' if x['done'] else 'todo'}" for x in (self.missions or {}).get("missions", []))
                print(f"SELFTEST objectives: {done}", flush=True)
            for secs, fn in ((2, gui), (3.5, hack), (5.5, report)):
                self.taskMgr.doMethodLater(secs, fn, f"selftest {fn.__name__}")

    def restore_prefs(self, prefs):
        """A learner's camera view and half-typed AI card, from their profile."""
        self.cam.restore(prefs.get("camera", {}))
        self.restore_hud_prefs(prefs)  # (the code panel's place and size, text size, look, the wheel)
        if isinstance(prefs.get("sound"), dict):  # (their own sound settings: CHANGE 107)
            self.sound_prefs = rw_sound.sound_settings(prefs["sound"])
        for k in CARD_FIELDS:
            if prefs.get("card", {}).get(k):
                self.entry_text[f"card_{k}"] = str(prefs["card"][k])[:2000]
        if prefs.get("card_target") in fm.AI_TARGETS and prefs["card_target"] != "game":
            self.card_target = prefs["card_target"]
        self.prefs_sent = json.dumps(self.gather_prefs(), sort_keys=True)

    def gather_prefs(self):
        card = {}
        for k in CARD_FIELDS:
            e = self.entries.get(f"card_{k}")
            card[k] = e.get() if e is not None else self.entry_text.get(f"card_{k}", "")
        return {"camera": self.cam.settings(), "card": card, "card_target": self.card_target, **self.hud_prefs(),
                **({"sound": self.sound_prefs} if getattr(self, "sound_prefs", None) else {})}

    def key(self, key, fn, *extra):
        """A game shortcut key. It does nothing while you are typing in a text box."""
        self.accept(key, lambda: None if self.typing or not self.started else fn(*extra))

    def tab_key(self, step):
        """Tab moves the typing from one text box to the next (Shift+Tab: to the one before), on the login screen
        and every other screen; from the last box it goes round to the first. Text boxes only, in the order they
        are on the screen (the order they were made): not buttons or tick boxes, and not the lines of the code
        view (the up and down arrows move between those)."""
        keys = [k for k in self.entries if not k.startswith("code_")]
        if not keys or str(self.typing or "").startswith("code_"):
            return
        if self.typing in keys:
            to = keys[(keys.index(self.typing) + step) % len(keys)]
        elif self.started:
            return  # (not typing: Tab is not a game key)
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
        was = hud.THEME
        hud.set_theme("dark")  # (the HUD over the ring is always the dark look: it is drawn once, over the game)
        self.hud_dark()
        hud.set_theme(was)

    def hud_dark(self):
        self.fight_hud = FightHUD(self.aspect2d)
        # the rings box (top left, under the health bars): who you are, the mode, and every ring's fight
        self.rings_small = bool(load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("rings_small"))
        self.rings_back = DirectFrame(frameColor=PANEL, frameSize=(-1.76, -0.62, 0.2, 0.72))
        label(self.aspect2d, f"FIGHT LAB  -  {'TEACHER' if TEACHER else 'LEARNER'}: {name}", -1.73, 0.675, 0.03,
              BLUE if TEACHER else YELLOW)
        self.mode_text = label(self.aspect2d, "", -1.73, 0.63, 0.026, WHITE)
        self.view_text = label(self.aspect2d, "", -1.73, 0.59, 0.022, GREY)
        self.rings_title = label(self.aspect2d, "RINGS   ([ and ] watch another ring, B hides this)", -1.73, 0.545,
                                 0.022, YELLOW)
        self.ring_rows = [label(self.aspect2d, "", -1.73, 0.5 - i * 0.05, 0.023) for i in range(6)]
        self.status_text = label(self.aspect2d, "", 1.74, -0.975, 0.022, GREY, TextNode.ARight)
        self.feed = label(self.aspect2d, "", -1.72, -0.55, 0.032, YELLOW)
        self.banner = OnscreenText("", pos=(-0.3, -0.35), scale=0.05, fg=YELLOW, shadow=(0, 0, 0, 1), mayChange=True,
                                   wordwrap=40)
        keys = ("Arrows move (up/down sidestep)  A punch/combo  S kick  D special  W throw  Space jump  Shift block  "
                "X crouch  I HUD  C code  " + ("Shift+F fix  " if TEACHER else "U brain  P autopilot  ") +
                "V view  L fighter  [ ] ring  Q/E or right-drag turn  H help")
        self.help = label(self.aspect2d, keys, -1.74, -0.975, 0.021 * min(1.15, self.text_scale()), GREY)
        self.panel_floor = -0.94  # (the side panel stops above the key list: CHANGE 104)
        self.layout_rings()

    def place_xhud(self):
        """(CHANGE 210) The experience's coach, toasts and result card beside the side panel while it is open."""
        if getattr(self, "xhud", None) is not None:
            for node in (self.xhud.bottom_node, self.xhud.root):
                node.setX(XHUD_X_PANEL if self.tab else 0.0)

    def toggle_rings(self):
        self.rings_small = not self.rings_small
        remember("rings_small", self.rings_small)
        self.layout_rings()

    def layout_rings(self):
        for w in [self.rings_title] + self.ring_rows:
            w.hide() if self.rings_small else w.show()
        self.rings_back["frameSize"] = (-1.76, -0.62, 0.57 if self.rings_small else 0.2, 0.72)

    def toggle_mute(self):
        self.muted = not self.muted
        self.banner_note("Sound off on this computer (N)" if self.muted else "Sound on (N)", 2)

    def check_code(self, welcome):
        """The server runs the game's current code: if this window's code is different (a mod was switched, or
        the server restarted with changes), reopen with the new code. Returns True if the window is reopening."""
        if not welcome.get("code") or welcome["code"] == fight_version.CODE:
            return False
        if not fight_version.FROZEN and not LOCAL:  # the teacher's own windows on the class server run the teacher's code
            return False
        if os.environ.get("FIGHTLAB_REOPENED") == welcome["code"] or args.offscreen:  # tried already: don't loop
            self.banner_note("This window's game code doesn't match the server's. Restart the server "
                             "(teacher: Controls), then reopen this window.", 3600)
            return False
        self.restart_window(reopen_for=welcome["code"])
        return True

    def restart_window(self, reopen_for=None, argv=None, try_env=None):
        """Reopen this window (to load code changes), logged in as the same person.
        argv: open it with these arguments instead (Try it on this laptop, and Back to the class). try_env: what a
        window on the laptop's test server needs to know (see try_local); left out, a try stays a try."""
        env = dict(os.environ, FIGHTLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        if reopen_for:  # remember which server code this reopen was for, so it only happens once
            env["FIGHTLAB_REOPENED"] = reopen_for
        else:
            env.pop("FIGHTLAB_REOPENED", None)
        if try_env is None and TRY and argv is None:
            try_env = json.dumps(TRY)
        if try_env:
            env["FIGHTLAB_TRY"] = try_env
        else:
            env.pop("FIGHTLAB_TRY", None)
        argv = [a for a in (sys.argv[1:] if argv is None else argv)]
        for flag in ("--name", "--password"):  # the login travels in FIGHTLAB_LOGIN instead
            while flag in argv:
                i = argv.index(flag)
                del argv[i:i + 2]
        if TEACHER:
            argv += ["--name", name]
        # (the new process, window.log, the app told the new process id, os._exit: engine.reopen, shared by every
        # game's window since CHANGE 189)
        reopen.reopen(__file__, argv, env, frozen=fight_version.FROZEN,
                      log_dir=SETTINGS_DIR if fight_version.FROZEN else HERE)

    def toggle_help(self):
        self.help.hide() if not self.help.isHidden() else self.help.show()
        self.panel_floor = -1.0 if self.help.isHidden() else -0.94  # (CHANGE 104)
        self.place_panel()

    def toggle_code(self):
        self.show_code = not self.show_code
        if self.show_code and not TEACHER:
            send({"type": "code_viewed"})
        self.rebuild_panels()

    def open_tab(self, tab):
        self.tab = None if self.tab == tab else tab
        self.code_shown = None
        self.rebuild_panels()

    def cycle_teacher_tabs(self):
        order = [t for t, _ in TEACHER_TABS]
        self.tab = order[(order.index(self.tab) + 1) % len(order)] if self.tab in order else order[0]
        self.code_shown = None
        self.rebuild_panels()

    def rebuild_panels(self, from_game=False):
        """Redraw the side panels. A redraw caused by the game (a new round, new mission results)
        waits while you're typing, so the text box keeps the keyboard."""
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
            tabs = (TEACHER_TABS if TEACHER else LEARNER_TABS) + hud.extra_tabs(TEACHER)  # (+ a mod's own tabs)
            f, y0 = self.draw_header(f, tabs, self.open_tab, self.tab,
                                     lambda key, text: self.warnings_tab_text(text) if key == "warnings" else text)
            builders = {"garage": self.build_garage, "teacher": self.build_teacher_panel, "missions": self.build_missions,
                        "ai": self.build_ai_card, "outcomes": self.build_outcomes, "cards": self.build_cards,
                        "card": self.build_card,
                        "learners": self.build_learner_view, "changes": self.build_changes,
                        "accounts": self.build_accounts, "matches": self.build_matches,
                        "settings": self.build_settings, "mods": self.build_mods, "warnings": self.build_warnings,
                        "limits": self.build_limits}
            if self.tab in builders:
                builders[self.tab](f, y0)
            elif hud.extra_builder(self.tab) is not None:
                hud.extra_builder(self.tab)(self, f, y0)
            self.place_panel()
        if self.show_code and (TEACHER or self.lesson["tools"]["code_view"]):
            self.build_code_panel()
        if self.typing == "code" and self.code_editor is not None:  # redrawn while typing in the code: carry on
            self.code_editor.focused = True
            self.code_editor.refresh()
        elif self.typing and self.typing not in self.entries:  # the box being typed in has gone
            self.typing = None
        self.fight_hud.place(-0.5 if self.tab else 0.0)
        self.place_xhud()
        self.cam.set_shift(0.14 if self.tab else 0.0)  # keep the fight clear of the side panel

    # ---------- which fighter the garage and code panel are editing ----------
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
        if TEACHER:
            return {k: True for k in self.lesson["tools"]} | {"specials": list(self.rules["specials"])}
        return self.lesson["tools"]

    # ---------- garage: design your fighter ----------
    def build_garage(self, f, y, view=None):
        """view: the teacher's Learner view of this learner. The teacher sees every control, with a tick box
        on each showing (and setting) whether the learner can see and change it. The tables are the engine's,
        from the fighter's schema."""
        tools, d = self.tools(), self.cur()
        seen = self.lesson["tools"]

        def shown_box(tool, yy):
            if view:
                check(f, " learner sees", 1.52, yy, seen.get(tool), lambda v, t=tool: self.set_lesson({"tools": {t: bool(v)}}),
                      0.022)
        label(f, ("EVERY LEARNER'S FIGHTER" if view == self.ALL_LEARNERS else f"{view.upper()}'S FIGHTER") if view else
              ("MY FIGHTER" if TEACHER else "GARAGE  -  your fighter as variables"), 0.82, y, 0.034 if view else 0.038,
              YELLOW)
        y -= 0.06
        model = d.get("model")
        limits = self.limits()
        y = garage.draw(self, f, y, d, self.schema, self.code_ctx(d), tools, limits, view, shown_box,
                        teacher=TEACHER and not view)

        self.stats_text = None
        if tools.get("stats_readout") and not model:
            self.stats_text = label(f, "", 0.82, y - 0.005, 0.022, GREEN)
            self.update_stats_text()
            shown_box("stats_readout", y)
            y -= 0.13
        if view != self.CPU_VIEW:
            y = self.build_slots(f, y, view)  # (CHANGE 83 to 87)
        self.garage_bottom = y - 0.1  # (where the Learner view puts the computer fighter's Reset button)
        if view:
            button(f, f"BUILD FOR {view.upper()}", 1.27, y, self.send_design_for, [view], 0.034, (0.15, 0.55, 0.25, 1))
        else:
            button(f, "BUILD MY FIGHTER", 1.27, y, self.send_design, None, 0.038, (0.15, 0.55, 0.25, 1))
        self.garage_msg = label(f, self.status_msg[0] if not view else "", 0.82, y - 0.06, 0.024, self.status_msg[1],
                                wrap=40)
        if self.lesson["designs_locked"] and not TEACHER:
            label(f, "Designs are locked by the teacher", 0.82, y - 0.12, 0.026, RED)

    def build_style(self, f, y, d, can_change, shown_box):
        """The fighting style (what the attack buttons do) and, for an armed style, the weapon."""
        style, weapon = sim.style_of(d)
        if can_change:
            label(f, "Style", 0.82, y, 0.028)
            for i, s in enumerate(self.rules["styles"]):
                button(f, s, 1.02 + (i % 3) * 0.2, y + 0.008 - (i // 3) * 0.045, self.set_style, [s], 0.022,
                       ON if s == style else OFF)
            shown_box("fighting_style", y)
            y -= 0.095
            weapons = [w for w, v in self.rules["weapons"].items() if v[0] == style]
            if weapons:
                label(f, "Weapon", 0.84, y, 0.025)
                for i, w in enumerate(weapons):
                    button(f, w.replace("_", " & "), 1.02 + i * 0.2, y + 0.008, self.set_weapon, [w], 0.021,
                           ON if w == weapon else OFF)
                y -= 0.045
        else:
            label(f, f"Style: {style}" + (f" with a {weapon.replace('_', ' & ')}" if weapon else "") +
                  "  (chosen by the teacher this lesson)", 0.82, y, 0.024, GREY)
            y -= 0.045
        moves = self.rules["style_moves"].get(style, {})
        what = self.rules["weapons"][weapon][1] if weapon else self.rules["styles"][style]
        label(f, f"{what}\nA {moves.get('punch')}   S {moves.get('kick')}   X+S {moves.get('low')}   "
                 f"forward+S {moves.get('high')}", 0.84, y, 0.02, GREY, wrap=48)
        return y - 0.09

    def set_style(self, style):
        d = self.cur()
        d["fighting_style"] = style
        weapons = [w for w, v in self.rules["weapons"].items() if v[0] == style]
        if weapons:
            d["weapon"] = d["weapon"] if d.get("weapon") in weapons else weapons[0]
        else:
            d.pop("weapon", None)
        self.code_shown = None
        self.rebuild_panels()

    def set_weapon(self, weapon):
        self.cur()["weapon"] = weapon
        self.code_shown = None
        self.rebuild_panels()

    def look_section(self, f, y, d):
        """After the body row: a detailed 3D body's look."""
        if d.get("body") in self.rules.get("model_bodies", []) and (TEACHER or self.tools().get("body_choice")):
            return self.build_look(f, y, d)
        return y

    def combo_section(self, f, y, d):
        """After the combo row: the editor (click a move to change it)."""
        if not (TEACHER or self.tools().get("combo_editor")):
            return y
        combo = d.get("combo", [])
        label(f, f"{self.rules['combo_min']} to {self.rules['combo_max']} moves; press A again after each hit. "
                 "Click a move to change it.", 0.84, y, 0.021, GREY)
        y -= 0.045
        for i, mv in enumerate(combo):
            button(f, f"{i + 1}. {mv}", 0.9 + (i % 4) * 0.2, y + 0.008 - (i // 4) * 0.05, self.cycle_combo, [i], 0.023,
                   (0.3, 0.35, 0.5, 1))
        y -= 0.05 * (1 + (max(0, len(combo) - 1)) // 4)
        button(f, "+ add a move", 0.94, y + 0.008, self.combo_length, [1], 0.022)
        button(f, "- last move", 1.17, y + 0.008, self.combo_length, [-1], 0.022)
        return y - 0.055

    def build_look(self, f, y, d):
        """A detailed body's look: outfit, hairstyle, hair colour, shape and height (it doesn't change the fight).
        Robin has a frame (shape) and height instead, with trim and light colours."""
        look = d.setdefault("look", sim.default_look(d["body"]))
        human = d["body"] in self.rules.get("human_bodies", ["woman", "man"])
        rows = ((("Outfit", "outfit", list(self.rules["outfits"])),
                 ("Hair", "hair", self.rules["hair_styles"][d["body"]])) if human else ()) + (
                ("Shape" if human else "Frame", "shape", list(self.rules["shapes"])),
                ("Win", "win", list(self.rules.get("wins", {}))))
        for text, key, options in rows:
            label(f, text, 0.84, y, 0.025)
            for i, opt in enumerate(options):
                button(f, opt, 1.02 + (i % 5) * 0.145, y + 0.008 - (i // 5) * 0.045, self.set_look, [key, opt], 0.021,
                       ON if look.get(key) == opt else OFF)
            y -= 0.045 * (1 + (len(options) - 1) // 5) + 0.005
        if human:
            label(f, "Hair colour", 0.84, y, 0.025)
            for i, c in enumerate(HAIR_SWATCHES):
                big = 0.95 if list(c) == list(look.get("hair_colour", [])) else 0.6
                DirectButton(parent=f, text="", scale=0.026, pos=(1.05 + i * 0.075, 0, y + 0.008), relief=DGG.FLAT,
                             frameColor=(*(v / 255 for v in c), 1), frameSize=(-0.9, 0.9, -big, big),
                             command=self.set_look, extraArgs=["hair_colour", list(c)])
            y -= 0.05
        else:  # Robin: trim and light colours (the design's style, as the built robot's)
            style = d.setdefault("style", {})
            for text, key, swatches in (("Trim", "trim", TRIM_SWATCHES), ("Lights", "lights", LIGHT_SWATCHES)):
                label(f, text, 0.84, y, 0.025)
                current = list(style.get(key) or self.rules.get("robin_style", {}).get(key, []))
                for i, c in enumerate(swatches):
                    big = 0.95 if list(c) == current else 0.6
                    DirectButton(parent=f, text="", scale=0.026, pos=(1.05 + i * 0.075, 0, y + 0.008), relief=DGG.FLAT,
                                 frameColor=(*(v / 255 for v in c), 1), frameSize=(-0.9, 0.9, -big, big),
                                 command=self.set_style_colour, extraArgs=[key, list(c)])
                y -= 0.05
        label(f, "Height", 0.84, y, 0.025)
        lo, hi = self.rules["height"]
        s = DirectSlider(parent=f, range=(lo, hi), value=look.get("height", 100), pageSize=2, scale=0.18,
                         pos=(1.28, 0, y + 0.008), command=self.height_moved, thumb_frameSize=(-0.04, 0.04, -0.12, 0.12))
        self.height_slider = (s, label(f, f"{look.get('height', 100):.0f}%", 1.5, y, 0.025, WHITE))
        return y - 0.055

    def limits(self):
        """The ranges the design being edited is held to: the learners' (the teacher sets them in the Limits tab),
        or the widest ones for the teacher's own fighter."""
        if TEACHER and not self.viewing():
            return self.full_limits()
        return self.lesson.get("limits") or self.default_limits()

    def pretty(self, key):
        return PRETTY.get(key, key.title())

    def push_mod_makers(self, only=None):
        """(Teacher) Tell the server who made each user mod: this laptop's change history knows (ai_changes/).
        only: the mods that a change kept or merged just now added."""
        import ai_pipeline
        makers = {k: who for k, who in ai_pipeline.user_mod_makers().items() if who and (only is None or k in only)}
        if makers:
            send({"type": "mod_makers", "makers": makers, "new": only is not None})

    def forget_mod_makers(self, mods):
        """(Teacher) A deleted learner's name has come off their mods on the server: off this laptop's list too."""
        gone = [k for k, who in mods.get("makers", {}).items() if who == ""]
        if gone:
            import ai_pipeline
            try:
                ai_pipeline.forget_user_mod_makers(gone)
            except OSError:
                pass

    def stage_items(self):
        """The stage's hazards, for the Mods tab."""
        L = self.lesson
        return [(hz, HAZARD_NAMES[hz], bool(L["hazards"].get(hz)), lambda v, k=hz: self.set_lesson({"hazards": {k: bool(v)}}))
                for hz in HAZARD_NAMES]

    def set_style_colour(self, key, colour):
        self.cur().setdefault("style", {})[key] = colour
        self.code_shown = None
        self.rebuild_panels()

    def set_look(self, key, value):
        self.cur().setdefault("look", sim.default_look(self.cur()["body"]))[key] = value
        self.code_shown = None
        self.rebuild_panels()

    def height_moved(self):
        s, text = self.height_slider
        v = int(round(s["value"]))
        self.cur().setdefault("look", sim.default_look(self.cur()["body"]))["height"] = v
        text.setText(f"{v}%")

    def name_key(self):
        """The fighter-name box: one for your fighter, one for each learner in the Learner view."""
        return "name_" + (self.viewing() or "me")

    def update_stats_text(self):
        if not getattr(self, "stats_text", None):
            return
        try:
            self.stats_text.setText(sim.stats_text(self.cur()))
        except Exception:
            return

    def set_colour(self, colour):
        self.cur()["colour"] = colour
        self.code_shown = None
        self.rebuild_panels()

    def set_body(self, body):
        d = self.cur()
        d["body"] = body
        if body in self.rules.get("model_bodies", []):  # a complete look for this body (keeping what carries over)
            base = sim.default_look(body)
            look = {k: v for k, v in (d.get("look") if isinstance(d.get("look"), dict) else {}).items() if k in base}
            if look.get("hair") not in self.rules["hair_styles"].get(body, []):
                look.pop("hair", None)
            d["look"] = dict(base, **look)
        self.code_shown = None
        self.rebuild_panels()

    def set_model(self, model):
        d = self.cur()
        if model:
            d["model"], d["special"] = model, self.rules["bosses"][model]
        else:
            d.pop("model", None)
        self.code_shown = None
        self.rebuild_panels()

    def set_special(self, sp):
        self.cur()["special"] = sp
        self.code_shown = None
        self.rebuild_panels()

    def cycle_combo(self, i):
        moves = list(self.rules["combo_moves"])
        combo = self.cur()["combo"]
        combo[i] = moves[(moves.index(combo[i]) + 1) % len(moves)] if combo[i] in moves else moves[0]
        self.code_shown = None
        self.rebuild_panels()

    def combo_length(self, delta):
        """Add or remove a move. (It lets you go one past the limits, so you can see the server say no: mission 2b.)"""
        combo = self.cur()["combo"]
        if delta > 0 and len(combo) < self.rules["combo_max"] + 1:
            combo.append("punch")
        elif delta < 0 and len(combo) > 1:
            combo.pop()
        self.code_shown = None
        self.rebuild_panels()

    def change_points(self, stat, delta):
        d = self.cur()
        d["points"][stat] = max(self.rules["stat_min"], min(self.rules["stat_max"], d["points"][stat] + delta))
        self.code_shown = None
        self.rebuild_panels()

    def slider_moved(self, k):
        s, text = self.sliders[k]
        v = int(round(s["value"]))
        self.cur()["settings"][k] = v
        text.setText(f"{v}%")
        self.update_stats_text()
        if self.code_panel is not None:  # just the code panel: redrawing the garage would drop the slider
            self.refresh_code_panel()

    def send_design(self):
        if "name_me" in self.entries and self.tools().get("name_and_colour"):
            self.draft["name"] = self.entries["name_me"].get()[:16]
        send({"type": "design", "design": self.draft, "code": bool(self.code_changed or self.code_hack)})
        self.status_msg = ("Building...", GREY)
        if self.tab == "garage":
            self.garage_msg.setText("Building...")

    def send_design_for(self, learner):
        if learner == self.ALL_LEARNERS:  # (CHANGE 85)
            d = self.cur()
            if self.name_key() in self.entries:
                d["name"] = self.entries[self.name_key()].get()[:16]
            send({"type": "design_for_all", "design": d})
            return
        d = self.cur()
        if self.name_key() in self.entries:
            d["name"] = self.entries[self.name_key()].get()[:16]
        send({"type": "design_for", "learner": learner, "design": d})
        self.garage_msg.setText(f"Building for {learner}...")

    # ---------- code view: your fighter as Python code, which you can edit ----------
    def code_ctx(self, d=None):
        """What the schema needs to know from this window: the mission's specials, the bodies, the bosses, the
        styles, the combo moves, the limits, and the design itself (the weapons offered depend on its style)."""
        from types import SimpleNamespace
        who = self.viewing()
        tools = self.tools()
        return SimpleNamespace(title=f"{who.upper()}'S FIGHTER" if who else "MY FIGHTER", points_total=self.limits()["points_total"],
                               design=d if d is not None else self.cur(), bodies=self.rules["bodies"],
                               bosses=self.rules.get("bosses", {}), specials=list(tools.get("specials") or self.rules["specials"]),
                               all_specials=list(self.rules["specials"]), styles=self.rules.get("styles", {}),
                               combo_moves=self.rules.get("combo_moves", {}), rules=self.rules)

    def code_lines(self, d):
        """The fighter as Python: one variable a line, with its type and a comment, in the garage's groups (the
        engine writes it from the schema)."""
        return schema.code_lines(self.schema, d, self.code_ctx(d))

    def build_code_panel(self):
        """The fighter as Python code, in a small editor (the engine's): click anywhere in it to type there, the
        words are coloured as an IDE colours them, long code scrolls, and the panel can be moved and resized."""
        who = self.viewing()
        d = self.cur()
        self.code_size = self.code_fit(*self.code_size)
        self.code_at = self.code_place(*self.code_at)
        f, (left, right, bottom, top) = self.code_panel_top("fighter", who)  # (CHANGE 143: as the browser's)
        st, fresh = self.code_state, self.code_lines(d)
        if self.code_shown is None or st["lines"] == self.code_shown:  # not edited: the fighter as it is now
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
        button(f, f"BUILD FOR {who.upper()}" if who else "BUILD MY FIGHTER", -0.64 if not who else -0.5, bottom + 0.112,
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
        """RESET CODE: the code goes back to the fighter as it is now. Only the code on screen changes."""
        self.code_state["lines"][:] = self.code_lines(self.cur())
        self.code_state["cursor"][:], self.code_state["scroll"] = [0, 0], 0
        self.code_shown = list(self.code_state["lines"])
        self.code_msg = ("The code is back to your fighter as it is. Press APPLY CODE or BUILD to use it.", GREY)
        self.refresh_code_panel()

    def build_from_code(self):
        """BUILD MY FIGHTER in the code panel: read the code as APPLY CODE does, then build the fighter from it."""
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
        if not TEACHER:  # (CHANGE 124: the code has room to twice the teacher's limit, or the maximum)
            limits = sim.code_limits(limits)
        for var in self.schema:
            if var.name not in values or var.group not in ("points", "settings"):
                continue
            path = var.path if isinstance(var.path, (tuple, list)) else (var.path,)
            rng = limits.get(var.group, {}).get(path[-1])
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
        class server holds the fighter to the rules all the same, and tells the teacher what was changed."""
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
        if "FIGHTER" in values:
            self.code_msg = ("The code is now one variable a line: press RESET CODE to see it.", RED)
            self.refresh_code_panel()
            return
        tools = self.tools()

        def allowed(var, value):  # (what this mission's garage lets the learner change)
            if var.name == "special":
                return bool(tools.get("choose_special")) and value in tools.get("specials", [])
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
            self.code_hack = True  # (so the next build, from here or the garage, is sent as the code's)
        if "fighter_name" in changed:
            self.entry_text.pop(self.name_key(), None)
            if self.name_key() in self.entries:
                self.entries[self.name_key()].enterText(d["name"])
        problems += sim.check_design(d, self.limits())
        if problems:
            self.code_msg = ("Applied, but: " + "; ".join(problems[:3]), ORANGE)
        else:
            self.code_msg = ("Applied: the garage shows your changes. Press BUILD to use them.", GREEN)
        self.code_shown = None
        self.rebuild_panels()
        return not problems

    # ---------- missions (learner) ----------
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
        for i, (title, n) in enumerate(shown):
            label(f, f"{title}: {n}", 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.038, 0.026, GREEN)
        y -= 0.038 * ((len(shown) + 1) // 2) + 0.02
        label(f, "What I did", 0.82, y, 0.03, YELLOW)
        y -= 0.045
        for day in card["history"]:
            label(f, day["date"], 0.84, y, 0.028, WHITE)
            y -= 0.038
            for m in day["missions"]:
                label(f, f"Mission {m['lesson']}: {m['title']}", 0.88, y, 0.025, GREY)
                label(f, " ".join(m["outcomes"]), 1.74, y, 0.022, BLUE, TextNode.ARight)
                y -= 0.034
                if m.get("detail"):  # (CHANGE 96: the change itself, as the objective's check recorded it)
                    t = label(f, m["detail"], 0.92, y, 0.022, GREEN, wrap=44)
                    y -= 0.028 * t.textNode.getNumRows() + 0.008
            y -= 0.012
        if not card["history"]:
            label(f, "Nothing yet.", 0.84, y, 0.026, GREY)



    def save_reflection(self, mission):
        send({"type": "reflection", "mission": mission, "text": self.entries[f"reflect_{mission}"].get()})

    def brains_on(self):
        """CHANGE 99: the teacher's Autopilot tick in Controls. Off, U and P do nothing for learners."""
        if TEACHER or self.lesson.get("tools", {}).get("brains", True):
            return True
        self.banner_note("Brains aren't switched on for this mission yet.", 3)
        return False

    def autopilot_key(self):
        if self.brains_on():
            send({"type": "autopilot"})

    def upload_brain(self):
        if not self.brains_on():
            return
        for path in (os.path.join(BRAINS, f"{name}.py"), os.path.join(BRAINS, "my_brain.py")):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    send({"type": "brain", "source": fh.read()})
                self.banner_note(f"Uploading {os.path.basename(path)}...")
                return
        self.banner_note("No brain file: make brains/my_brain.py first")

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
        """mesh and lines: the learner's line colour, at once (CHANGE 147; the HUD keeps it in their profile)."""
        fight_gfx.set_line_colour(colour)

    def banner_note(self, text, secs=3, big=False):
        """Words over the ring for a few seconds. big: the size of a round's banner (a restart warning)."""
        self.note_until = time.perf_counter() + secs
        self.note_text, self.note_big = text, big

    # ---------- AI request card (learner) ----------
    def build_ai_card(self, f, y, edit=False):
        """edit: the teacher's copy (AI cards tab, "The learners' card"). It is the card as the learners see it,
        with a box for the teacher's own instructions: what is typed there is shown on every learner's card."""
        label(f, "AI REQUEST CARD" + ("  as the learners see it" if edit else ""), 0.82, y, 0.036 if edit else 0.04,
              YELLOW)
        if edit:
            button(f, "Back to the requests", 1.62, y + 0.008, self.show_cards, [None], 0.022)
        y -= 0.055
        label(f, AI_RULES, 0.82, y, 0.023, BLUE, wrap=42)
        y -= 0.12
        note = str(self.lesson.get("ai_card_note") or "").strip()
        if edit:
            label(f, "From your teacher:   (type what the learners should read here)", 0.82, y, 0.024, ORANGE)
            self.entry(f, "card_note", 0.84, y - 0.042, 30, 4, initial=note, scale=0.026)
            y -= 0.165
            button(f, "SHOW THIS ON THE LEARNERS' CARDS", 1.27, y, self.send_card_note, None, 0.028, (0.15, 0.45, 0.65, 1))
            self.note_text = label(f, "On their cards now." if note else "Nothing from you is on their cards yet.",
                                   0.82, y - 0.055, 0.022, GREY)
            y -= 0.1
        elif note:
            words = label(f, "From your teacher:  " + note, 0.82, y, 0.025, ORANGE, wrap=36)
            y -= 0.03 * max(1, words.textNode.getNumRows()) + 0.025
        label(f, "What should change?", 0.82, y, 0.027)
        for i, (key, text) in enumerate(fm.AI_TARGETS.items()):
            if key == "game":
                continue
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
        card = {k: self.entries[f"card_{k}"].get() for k in CARD_FIELDS}
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
        for n in range(1, 6):
            button(f, str(n), 1.0 + (n - 1) * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.028,
                   ON if L.get("lesson_number") == n else OFF)
        saved = (L.get("saved_missions") or [])  # (CHANGE 58 and 59: saved per mission, and brought back)
        button(f, "Save settings", 1.5, y + 0.008, send, [{"type": "save_lesson"}], 0.024)
        button(f, "Restore", 1.68, y + 0.008, send, [{"type": "restore_lesson"}], 0.024)
        if saved:
            label(f, "saved settings: mission " + ", ".join(str(n) for n in saved), 1.74, y - 0.037, 0.015, GREY,
                  TextNode.ARight)
        y -= 0.06
        y = self.xhud.controls_row(f, 0.82, y)  # (CHANGE 210: Experience 1 for the class, or its end)
        label(f, "Fights", 0.82, y, 0.028, YELLOW)
        for i, mode in enumerate(("practice", "battle")):
            button(f, mode.title(), 1.04 + i * 0.19, y + 0.008, self.set_lesson, [{"mode": mode}], 0.028,
                   ON if L["mode"] == mode else OFF)
        button(f, "Restart", 1.44, y + 0.008, send, [{"type": "restart"}], 0.028)
        button(f, "Pause", 1.63, y + 0.008, send, [{"type": "pause"}], 0.028,
               ON if (self.state or {}).get("paused") else OFF)  # (CHANGE 102: lit while paused)
        y -= 0.055
        label(f, f"Rounds {L['round_time']} s", 0.82, y, 0.026)
        button(f, "-10", 1.06, y + 0.008, self.set_lesson, [{"round_time": L["round_time"] - 10}], 0.024)
        button(f, "+10", 1.15, y + 0.008, self.set_lesson, [{"round_time": L["round_time"] + 10}], 0.024)
        label(f, "Rounds to win", 1.25, y, 0.026)
        for n in (1, 2, 3):
            button(f, str(n), 1.5 + (n - 1) * 0.07, y + 0.008, self.set_lesson, [{"rounds_to_win": n}], 0.024,
                   ON if L["rounds_to_win"] == n else OFF)
        y -= 0.05
        check(f, "Computer sparring partners", 0.84, y, L["cpu_opponents"],
              lambda v: self.set_lesson({"cpu_opponents": bool(v)}), 0.026)
        y -= 0.045
        level = L.get("cpu_level", "medium")
        label(f, "Computer level", 0.84, y, 0.024)
        for i, (key, text) in enumerate(cpu_brains.LEVELS.items()):
            button(f, text, 1.1 + i * 0.13, y + 0.008, self.set_lesson, [{"cpu_level": key}], 0.021,
                   ON if level == key else OFF)
        if level == "empty":
            button(f, "Upload demo brain", 1.64, y + 0.008, self.upload_demo_brain, None, 0.019, (0.15, 0.45, 0.65, 1))
        y -= 0.045
        label(f, "Computer plays", 0.84, y, 0.024)
        for i, who in enumerate(["sparring"] + list(self.rules["bosses"])):
            button(f, who.title() if who == "sparring" else who, 1.1 + i * 0.13, y + 0.008, self.set_lesson,
                   [{"cpu_fighter": who}], 0.019, ON if L.get("cpu_fighter") == who else OFF)
        y -= 0.05
        check(f, "My fighter in the class", 0.84, y, L["teacher_fighter"],
              lambda v: self.set_lesson({"teacher_fighter": bool(v)}), 0.026)
        check(f, "Lock designs", 1.34, y, L["designs_locked"], lambda v: self.set_lesson({"designs_locked": bool(v)}),
              0.026)
        y -= 0.06
        y = self.rings_section(f, y)
        label(f, "Stage hazards", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        for i, hz in enumerate(HAZARD_NAMES):
            check(f, HAZARD_NAMES[hz], 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.043, L["hazards"].get(hz),
                  lambda v, hz=hz: self.set_lesson({"hazards": {hz: bool(v)}}), 0.026)
        y -= 0.043 * 3
        label(f, "(electric ropes only work with ring-outs off: then the ring has ropes)", 0.84, y + 0.01, 0.019, GREY)
        y -= 0.04
        label(f, "User mods  (learners' ideas: on or off at any time)", 0.82, y, 0.028, YELLOW)
        y -= 0.043
        mods_on = L.get("user_mods", {})
        if not sim.USER_MODS:
            label(f, "None yet. An AI card sent as 'The whole game' can be made a switchable User Mod.", 0.84, y + 0.01,
                  0.019, GREY)
        for i, (key, (mod_name, _)) in enumerate(sim.USER_MODS.items()):
            check(f, " " + mod_name, 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.043, mods_on.get(key),
                  lambda v, k=key: self.set_lesson({"user_mods": {k: bool(v)}}), 0.026)
        y -= 0.043 * max(1, (len(sim.USER_MODS) + 1) // 2)
        label(f, "Learners can see and change  (or use the Learners tab)", 0.82, y, 0.026, YELLOW)
        y -= 0.045
        keys = ["points_table", "walk_speed", "sidestep_speed", "jump_height", "attack_speed", "size",
                "name_and_colour", "body_choice", "choose_special", "combo_editor", "code_view", "stats_readout", "bosses",
                "fighting_style", "brains"]
        for i, k in enumerate(keys):
            check(f, PRETTY[k], 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.041, L["tools"].get(k, k == "brains"),
                  lambda v, k=k: self.set_lesson({"tools": {k: bool(v)}}), 0.024)
        y -= 0.041 * ((len(keys) + 1) // 2) + 0.01
        label(f, "Specials allowed", 0.82, y, 0.024)
        for i, sp in enumerate(self.rules["specials"]):
            button(f, sp.replace("_", " "), 1.1 + i * 0.16, y + 0.008, self.toggle_special_allowed, [sp], 0.021,
                   ON if sp in L["tools"]["specials"] else OFF)
        y -= 0.055
        self.restart_row(f, y)

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
        elif not fight_version.FROZEN and not LOCAL:
            button(f, "Try on this laptop", 1.0, y, self.try_here, None, 0.024, (0.15, 0.45, 0.65, 1))
            label(f, "this window, on a test server here (the class sees nothing)", 1.19, y - 0.008, 0.02, GREY)

    def restart_server(self):
        if TRY:  # (nothing would start the test server again: a new try loads new code)
            return self.banner_note("You are trying this on the laptop: go Back to the class, then Try again, to "
                                    "load new code.", 8)
        self.needs_restart = False
        send({"type": "restart_server"})

    # ---------- try it on this laptop (teacher): a look at this laptop's game before it is made live ----------
    def try_here(self, mods=()):
        """Leave the class for a moment: a test server starts on this laptop, out of sight, and this one window
        reopens on it (see try_local). mods: the user mods to switch on there. Back to the class comes back."""
        if TRY or fight_version.FROZEN or self.try_starting is not None:
            return
        if LOCAL:
            return self.banner_note("This window is already on this laptop's test server: it has this laptop's "
                                    "game. Tick the mod in Controls.", 8)
        info, proc = try_local.start(HERE, "fight_server.py", "FIGHTLAB_DATA")
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
        """This window has just opened on the laptop's test server: the class's lesson, the teacher's own fighter
        in a ring, and the new user mods switched on. A notice and a way back stay on the screen."""
        if TRY.get("lesson") in (1, 2, 3, 4, 5):
            send({"type": "lesson_number", "n": TRY["lesson"]})
        mods = {k: True for k in TRY.get("mods") or [] if k in sim.USER_MODS}
        self.set_lesson({"teacher_fighter": True, **({"user_mods": mods} if mods else {})})
        self.exitFunc = self.stop_try  # (closing the window stops the test server too)
        OnscreenText("TRYING ON THIS LAPTOP: the class can't see this", pos=(-0.04, 0.715), scale=0.045, fg=ORANGE,
                     shadow=(0, 0, 0, 0.9), parent=self.aspect2d)
        DirectButton(parent=self.aspect2d, text="Back to the class", scale=0.042, pos=(-0.04, 0, 0.635),
                     command=self.back_to_class, frameColor=(0.15, 0.55, 0.25, 1), text_fg=WHITE, relief=DGG.FLAT,
                     pad=(0.4, 0.2))
        on = ", ".join(sim.USER_MODS[k][0] for k in mods)
        self.banner_note((f"Switched on here: {on}. " if on else "Tick a user mod in Controls to try it. ")
                         + "When you have seen enough, press Back to the class.", 12)

    def stop_try(self):
        if TRY:
            try_local.stop(TRY["server"], HERE)

    def try_test(self, task):
        """Tests only (CLUBCODERS_TRY_TEST names a file): on the class, note it and try the laptop; on the laptop,
        note what is switched on and go back; back on the class, note it and stay."""
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
        """Stop the test server and reopen this window on the class, the way it was opened before."""
        self.stop_try()
        global name
        login = TRY.get("login") or [name, "", ""]
        name, self.password, args.ticket = login[0] or name, login[1], login[2] or None
        self.restart_window(argv=TRY.get("argv") or [], try_env="")

    def upload_demo_brain(self):
        """Send brains/demo_cpu.py to the server: computer fighters set to Empty run it (for coding demos)."""
        path = os.path.join(HERE, "brains", "demo_cpu.py")
        if not os.path.exists(path):
            self.banner_note("No demo brain: make brains/demo_cpu.py first")
            return
        with open(path, encoding="utf-8") as fh:
            send({"type": "cpu_brain", "source": fh.read()})
        self.banner_note("Uploading the demo brain...")

    def volume_row(self, f, y, key, snd):
        """A volume from 0 to 10 with - and + buttons."""
        label(f, f"vol {round(snd[key] * 10)}", 1.58, y, 0.021, GREY)
        button(f, "-", 1.66, y + 0.008, self.set_sound, [{key: round(snd[key] - 0.1, 2)}], 0.021)
        button(f, "+", 1.72, y + 0.008, self.set_sound, [{key: round(snd[key] + 0.1, 2)}], 0.021)

    def my_sound(self):
        """This window's own sound settings (CHANGE 107): the teacher's on this computer, a learner's with their profile."""
        own = getattr(self, "sound_prefs", None)
        if own is None:
            own = SETTINGS.get("sound") if TEACHER else None
        return rw_sound.sound_settings(own if own is not None else self.lesson.get("sound"))

    def set_sound(self, change):
        self.sound_prefs = rw_sound.sound_settings(self.my_sound(), change)
        remember("sound", self.sound_prefs)
        self.prefs_at = 0.0
        self.rebuild_panels()

    def build_settings(self, f, y):
        hud.HudKit.build_settings(self, f, y)
        y = self.body_bottom(y) - 0.07
        snd = self.my_sound()
        label(f, "Sound  (yours: each has its own volume, all kept for next time)", 0.82, y, 0.028, YELLOW)
        y -= 0.05
        label(f, "Music", 0.84, y, 0.024)
        for i, (key, text) in enumerate(rw_sound.MUSIC.items()):
            button(f, text, 1.0 + i * 0.13, y + 0.008, self.set_sound, [{"music": key}], 0.021,
                   ON if snd["music"] == key else OFF)
        self.volume_row(f, y, "music_volume", snd)
        y -= 0.043
        for key, text in (("crowd", "Crowd"), ("effects", "Hits and moves")):
            check(f, " " + text, 0.84, y, snd[key], lambda v, k=key: self.set_sound({k: bool(v)}), 0.024)
            self.volume_row(f, y, {"crowd": "crowd_volume", "effects": "volume"}[key], snd)
            y -= 0.043

    def set_lesson(self, change):
        send({"type": "lesson", "lesson": change})

    def toggle_special_allowed(self, sp):
        allowed = list(self.lesson["tools"]["specials"])
        if sp in allowed and len(allowed) > 1:
            allowed.remove(sp)
        elif sp not in allowed:
            allowed.append(sp)
        self.set_lesson({"tools": {"specials": allowed}})

    # ---------- teacher: matches and the tournament ----------
    def fighters_in_class(self):
        people = [c["name"] for c in self.class_list if c["role"] == "learner"]
        if self.lesson.get("teacher_fighter"):
            people.append(name)
        return people

    def rings_section(self, f, y):
        """Controls (CHANGE 75): how many rings (Auto: one each, and matches share a ring), who is in which (two
        to a ring), and which ring this window watches."""
        L = self.lesson
        n = max(0, int(L.get("rings", 0)))
        label(f, "Rings", 0.82, y, 0.028, YELLOW)
        button(f, "Auto", 0.98, y + 0.008, self.set_lesson, [{"rings": 0}], 0.024, ON if n == 0 else OFF)
        for i in range(1, sim.MAX_RINGS + 1):
            button(f, str(i), 1.08 + (i - 1) * 0.07, y + 0.008, self.set_lesson, [{"rings": i}], 0.024,
                   ON if n == i else OFF)
        label(f, "Auto: one each, matches\nshare (Matches tab)" if n == 0 else "two to a ring", 1.51, y + 0.012,
              0.017, GREY)
        y -= 0.05
        if n:
            where = {f_["owner"]: f_["ring"] for f_ in (self.roster or {}).get("fighters", [])}
            places = L.get("places", {})
            people = [c["name"] for c in self.class_list if c["role"] == "learner"]
            if L.get("teacher_fighter"):
                people.append("Teacher")
            label(f, "Who is where  (the rings take turns unless you choose; a third sits out)", 0.84, y, 0.022,
                  GREY)
            y -= 0.045
            for who in people:
                shown = "My fighter" if who == "Teacher" else who
                label(f, shown, 0.84, y, 0.024)
                at = places.get(who, where.get(name if who == "Teacher" else who))
                for i in range(n):
                    button(f, str(i + 1), 1.2 + i * 0.075, y + 0.008, self.set_lesson, [{"places": {who: i}}], 0.024,
                           ON if at == i and who in places else (0.35, 0.35, 0.3, 1) if at == i else OFF)
                if at is None:
                    label(f, "sitting out", 1.2 + n * 0.075, y, 0.018, ORANGE)
                y -= 0.045
            if places:
                button(f, "Take turns again", 0.96, y + 0.008, self.set_lesson,
                       [{"places": {k: None for k in places}}], 0.022)
                y -= 0.045
            label(f, "Watch ring", 0.84, y, 0.024)
            for i in range(n):
                button(f, str(i + 1), 1.2 + i * 0.075, y + 0.008, self.set_watch, [i], 0.024,
                       ON if self.watched_ring() == i else OFF)
            label(f, "([ and ] in the ring)", 1.2 + n * 0.075 + 0.02, y, 0.018, GREY)
            y -= 0.06
        return y

    def build_matches(self, f, y):
        L = self.lesson
        label(f, "MATCHES  -  who fights who", 0.82, y, 0.034, YELLOW)
        y -= 0.05
        if L.get("rings"):
            label(f, f"Rings is set to {L['rings']} in Controls: Who is where there says who shares a ring.\n"
                     "Set Rings to Auto for the matches below to make the rings.", 0.82, y, 0.02, ORANGE)
            y -= 0.07
        label(f, "Pick two fighters, then Add match: they share a ring. Everyone else trains in a ring of their own.\n"
                 "Switch Battle on (Controls) for rounds, knockouts and ring-outs.", 0.82, y, 0.02, GREY)
        y -= 0.07
        check(f, "My fighter in the class (so I can fight learners myself)", 0.84, y, L["teacher_fighter"],
              lambda v: self.set_lesson({"teacher_fighter": bool(v)}), 0.024)
        y -= 0.06
        people = self.fighters_in_class()
        if len(people) < 2:
            label(f, "Matches need two fighters: wait for learners, or tick 'My fighter in the class'.", 0.82, y, 0.024,
                  GREY, wrap=44)
            y -= 0.08
        else:
            for i, n in enumerate(people):
                picked = n in self.match_pick
                button(f, n, 0.9 + (i % 4) * 0.21, y + 0.008 - (i // 4) * 0.055, self.pick_for_match, [n], 0.026,
                       ON if picked else OFF)
            y -= 0.055 * ((len(people) + 3) // 4) + 0.01
            pick = " v ".join(self.match_pick) or "nobody picked yet"
            label(f, f"Next match: {pick}", 0.84, y, 0.024, WHITE)
            button(f, "Add match", 1.55, y + 0.008, self.add_match, None, 0.026, (0.15, 0.55, 0.25, 1))
            y -= 0.06
        label(f, "Matches now", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        if not L.get("matches"):
            label(f, "No matches: everyone trains.", 0.84, y, 0.024, GREY)
            y -= 0.045
        for i, (a, b) in enumerate(L.get("matches", [])):
            label(f, f"{a}  v  {b}", 0.84, y, 0.026)
            button(f, "Remove", 1.55, y + 0.008, self.remove_match, [i], 0.022)
            y -= 0.048
        if L.get("matches"):
            button(f, "Clear all", 1.0, y, self.set_lesson, [{"matches": []}], 0.024)
            y -= 0.06
        y -= 0.02
        label(f, "TOURNAMENT  (Battle switched on, designs locked)", 0.82, y, 0.028, YELLOW)
        y -= 0.06
        t = self.tournament
        if t is None:
            button(f, "Knockout", 0.96, y, send, [{"type": "tournament", "start": True}], 0.028, (0.15, 0.55, 0.25, 1))
            label(f, "computer fighters fill the gaps", 1.1, y - 0.005, 0.019, GREY)
            y -= 0.06
            button(f, "Winner stays on", 1.0, y, send, [{"type": "tournament", "start": True, "kind": "stays", "live": 2}],
                   0.028, (0.15, 0.55, 0.25, 1))
            label(f, "two rings live; the loser queues, the next\nchallenger comes in; the rest watch ([ and ])",
                  1.18, y + 0.006, 0.019, GREY)
            y -= 0.07
        elif t.get("kind") == "stays":  # CHANGE 76
            button(f, "Stop: winner stays on", 1.1, y, send, [{"type": "tournament", "start": False}], 0.028,
                   (0.6, 0.2, 0.15, 1))
            y -= 0.055
            for i, (a, b) in enumerate(t.get("live", [])):
                label(f, f"Ring {i + 1}:  {a or '-'}  v  {b or '-'}", 0.84, y, 0.024, WHITE)
                y -= 0.04
            label(f, "Waiting:  " + (", ".join(t.get("queue", [])) or "nobody"), 0.84, y, 0.022, GREY, wrap=46)
            y -= 0.045
            label(f, f"Matches played: {t.get('played', 0)}", 0.84, y, 0.022, GREY)
            y -= 0.04
            for n, w, s in t.get("table", [])[:12]:
                label(f, f"{n}", 0.88, y, 0.022, GREEN if w else WHITE)
                label(f, f"{w} win{'s' if w != 1 else ''}" + (f"   {s} in a row" if s > 1 else ""), 1.25, y, 0.022,
                      GREEN if w else GREY)
                y -= 0.036
            y -= 0.01
        else:
            button(f, "Stop the tournament", 1.1, y, send, [{"type": "tournament", "start": False}], 0.028,
                   (0.6, 0.2, 0.15, 1))
            y -= 0.06
            if t.get("champion"):
                label(f, f"CHAMPION: {t['champion']}", 0.84, y, 0.036, YELLOW)
                y -= 0.06
            for r_i, rnd in enumerate(t["rounds"]):
                left = len(rnd)
                title = "Final" if left == 1 else "Semi-finals" if left == 2 else "Quarter-finals" if left == 4 else "Round 1"
                label(f, title, 0.84, y, 0.024, BLUE)
                y -= 0.04
                for a, b, w in rnd:
                    text = f"{a}  v  {b}" + (f"   ->  {w}" if w else "   (fighting)")
                    label(f, text, 0.88, y, 0.023, GREEN if w else WHITE)
                    y -= 0.036
                y -= 0.01
        y = min(y, -0.62)
        label(f, "Watch a ring", 0.82, y, 0.026, YELLOW)
        for i, r in enumerate((self.state or {}).get("rings", [])):
            button(f, f"Ring {r['i'] + 1}", 1.08 + i * 0.12, y + 0.008, self.set_watch, [r["i"]], 0.022,
                   ON if self.watched_ring() == r["i"] else OFF)

    def pick_for_match(self, n):
        if n in self.match_pick:
            self.match_pick.remove(n)
        else:
            self.match_pick = (self.match_pick + [n])[-2:]
        self.rebuild_panels()

    def add_match(self):
        if len(self.match_pick) != 2:
            self.banner_note("Pick two fighters first")
            return
        a, b = self.match_pick
        keep = [m for m in self.lesson.get("matches", []) if a not in m and b not in m]
        self.set_lesson({"matches": keep + [[a, b]]})
        self.match_pick = []

    def remove_match(self, i):
        ms = list(self.lesson.get("matches", []))
        if 0 <= i < len(ms):
            ms.pop(i)
        self.set_lesson({"matches": ms})

    # ---------- teacher: the learner view ----------
    def build_learner_view(self, f, y):
        # the learners who are connected, then the computer fighter: the teacher sets it up as a learner sets up
        # theirs, and every ring's sparring partner is built from it (CHANGE 77)
        computer = next((c for c in self.class_list if c["role"] == "computer"), None)
        learners = [c["name"] for c in self.class_list if c["role"] == "learner"] + \
            ([computer["name"]] if computer else []) + [self.ALL_LEARNERS]  # (CHANGE 85)
        label(f, "LEARNER VIEW  -  see and change what a learner sees", 0.82, y, 0.03, YELLOW)
        y -= 0.06
        # every window's frame rate, ping, key delay, stalls and graphics, one table (CHANGE 143: the page's "Who is here")
        people = [(c["name"], c["role"]) for c in self.class_list if c.get("role") in ("teacher", "learner")]
        y = self.perf_table(f, y, people, (self.roster or {}).get("perf", {}))
        if not learners:
            label(f, "No learners are connected yet.", 0.82, y, 0.028, GREY)
            return
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
        elif is_computer and self.view_tab == "mods":  # (as Robot Lab's CHANGE 23: the Mods tab as a learner sees it)
            label(f, "The Mods tab as a learner sees it (the computer fighter doesn't vote).", 0.82, y, 0.022, GREY)
            self.build_mods(f, y - 0.045, as_learner=True)
        elif self.view_tab == "garage":
            self.build_garage(f, y, view=who)
            if is_computer:
                if not computer.get("in_arena"):
                    label(f, "It isn't in a ring: Computer sparring partners is off in Controls.", 0.82, self.garage_bottom + 0.05, 0.022, ORANGE)
                button(f, "RESET: THE COMPUTER FIGHTER AS IT COMES", 1.27, self.garage_bottom, send,
                       [{"type": "cpu_robot", "reset": True}], 0.026, (0.6, 0.2, 0.15, 1))
        elif self.view_tab == "missions":
            self.build_missions(f, y, m=self.view_missions.get(who), preview=True)
        elif self.view_tab == "ai":
            label(f, f"{who}'s AI request card", 0.82, y, 0.03, YELLOW)
            y -= 0.05
            label(f, AI_RULES, 0.82, y, 0.023, BLUE, wrap=42)
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
        """Teacher: the computer fighter's own brain, uploaded and switched on as a learner does theirs."""
        label(f, "THE COMPUTER FIGHTER'S BRAIN", 0.82, y, 0.03, YELLOW)
        y -= 0.055
        label(f, "A learner writes brains/my_brain.py, uploads it (U) and switches autopilot on (P).\n"
                 "Do the same for the computer fighter here. With its autopilot off, every ring's\n"
                 "sparring partner follows Computer level in Controls.", 0.82, y, 0.022, GREY)
        y -= 0.13
        has, on = bool(computer.get("brain")), bool(computer.get("autopilot"))
        label(f, "Its brain: " + (("autopilot ON" if on else "uploaded, autopilot off") if has else "not uploaded yet"),
              0.82, y, 0.028, GREEN if has else GREY)
        y -= 0.075
        button(f, "Upload brains/my_brain.py for it", 1.08, y, self.upload_computer_brain, None, 0.028)
        if has:
            button(f, "Autopilot off" if on else "Autopilot on", 1.5, y, send,
                   [{"type": "cpu_robot", "autopilot": not on}], 0.028, ON if on else OFF)
        y -= 0.07
        label(f, "The brain is kept for next time. Its autopilot starts off at every session. Reset (in its\n"
                 "Garage) takes the brain away.", 0.82, y, 0.022, GREY)

    def upload_computer_brain(self):
        path = os.path.join(BRAINS, "my_brain.py")
        if not os.path.exists(path):
            self.banner_note("No brain file: make brains/my_brain.py first")
            return
        with open(path, encoding="utf-8") as fh:
            send({"type": "cpu_robot", "brain": fh.read()})
        self.banner_note("Uploading my_brain.py for the computer fighter...")

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

    # ---------- teacher: learners' accounts (the teacher makes them; learners can't) ----------
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
        label(f, "Delete removes their profile, fighter, brain, evidence and AI cards from the server.",
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
            self.newer = fight_version.newer_release()
        threading.Thread(target=work, daemon=True).start()

    def offer_download(self):
        if self.download_button is None and fight_version.DOWNLOAD_PAGE:
            self.download_button = button(self.aspect2d, "Download the new Club Coders", 1.2, 0.86,
                                          webbrowser.open, [fight_version.DOWNLOAD_PAGE], 0.035, (0.15, 0.55, 0.25, 1))

    # ---------- teacher: mods (changes made with Claude): switch on and off, then merge into the game ----------
    def build_changes(self, f, y):
        import ai_pipeline
        log = list(reversed(ai_pipeline.history()))
        mods = [e for e in log if e["status"] != "merged"]
        merged = [e for e in log if e["status"] == "merged"]
        label(f, "MODS", 0.82, y, 0.036, YELLOW)
        y -= 0.05
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
            label(f, f"Designed by {e['learner']}  ({TARGETS.get(e['target'], e['target'])}, {e['time'][5:]})", 0.9, y,
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
        import ai_pipeline
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
        import ai_pipeline
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
                                                    "The stage, rules and fighters have been updated."), GREEN)
        self.rebuild_panels()

    # ---------- teacher: outcomes and evidence ----------
    # ---------- the missions as learners see them, editable (CHANGE 97) ----------
    def toggle_outcome_obj(self, mid):
        self.open_outcome_obj = None if getattr(self, "open_outcome_obj", None) == mid else mid
        self.rebuild_panels()

    def automate_objective(self, mid, n, title, text, check="teacher"):
        """AUTOMATE: an AI request card (target: the game) asking Claude to write this objective's automatic check,
        so learners' windows tick it by themselves. The teacher sends it from the AI cards tab."""
        unit = self.UNIT
        asked = ("Automate the check for" if check == "teacher" else
                 "Check that the automatic check still fits the wording of, and fix it if not,")
        card = {"goal": f"{asked} Mission {n} objective {mid}, '{title}'. The game should tick it for a "
                        f"learner by itself, as the other objectives are checked by their id in the teaching module "
                        f"(build_checks when they build, tick_checks every half second, brain_checks for brains), when "
                        f"they do this: {text} If it can't be checked automatically, say why and suggest wording that "
                        f"could be.",
                "variables": f"The objective's id is {mid}. self.complete(p.name, '{mid}', detail) marks it done with a "
                             f"detail saying what the learner did (their {unit}'s values before and after).",
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
        for n in fm.LESSONS:
            button(f, str(n), 1.0 + (n - 1) * 0.08, y + 0.008, self.pick_edit_lesson, [n], 0.028,
                   ON if n == n_ else OFF)
        edits = t.get("edits", {})
        if edits.get("changed") or edits.get("removed") or edits.get("added"):
            button(f, "Reset all to standard", 1.46, y + 0.008, send, [{"type": "missions_edit", "do": "reset"}], 0.022,
                   (0.6, 0.2, 0.15, 1))
        y -= 0.06
        L = self.lesson
        check(f, " Show learners: pause every game and open every learner's Mission tab", 0.84, y,
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
                   (0.15, 0.45, 0.65, 1))  # (ask Claude for the automatic check, or to check the one there fits)
            y -= 0.235
            names = [n for n in grid if n != name]  # (every learner the server knows: green has done it, red not yet)
            if names:
                for j, name_ in enumerate(names):
                    done = mid in grid[name_].get("missions", [])
                    label(f, name_[:10], 0.86 + (j % 6) * 0.148, y - (j // 6) * 0.03, 0.02,
                          GREEN if done else RED)
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
        label(f, f"missions_fightlab.json in this folder's evidence folder: export, edit it in any editor, import.",
              0.84, y - 0.04, 0.019, GREY, wrap=46)
        y -= 0.1

    def import_missions_file(self):
        path = os.path.join(HERE, "evidence", "missions_fightlab.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.banner_note("No missions_fightlab.json yet: press EXPORT first", 4)
            return
        except ValueError as e:
            self.banner_note(f"The file isn't valid JSON: {e}", 6)
            return
        send({"type": "missions_import", "data": data})

    def pick_edit_lesson(self, n):
        self.guide_lesson = n
        self.rebuild_panels()

    def save_objective(self, mid):
        title = self.entries[f"mtitle_{mid}"].get() if f"mtitle_{mid}" in self.entries else ""
        text = self.entries[f"mtext_{mid}"].get() if f"mtext_{mid}" in self.entries else ""
        send({"type": "missions_edit", "do": "change", "id": mid, "title": title, "text": text})
        self.banner_note("Saved: every learner sees it", 2)

    def add_objective(self, n):
        title = self.entries["mnew_title"].get() if "mnew_title" in self.entries else ""
        text = self.entries["mnew_text"].get() if "mnew_text" in self.entries else ""
        if not title.strip():
            self.banner_note("Give the objective a title first", 2)
            return
        self.entry_text.pop("mnew_title", None)
        self.entry_text.pop("mnew_text", None)
        send({"type": "missions_edit", "do": "add", "lesson": n, "title": title, "text": text})

    def build_outcomes(self, f, y):
        t = self.teaching
        if getattr(self, "editing_missions", False):
            return self.build_mission_editor(f, y)
        label(f, "LEARNING OUTCOMES", 0.82, y, 0.034, YELLOW)
        if not t:
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
        for mid, (lesson, title, check_) in t["missions"].items():
            if check_ != "teacher" or lesson != t["lesson"]:
                continue
            label(f, f"{mid} {title}", 0.84, y, 0.024)
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
                 "anything (new moves, specials, hazards, rules, graphics). Every change is tested before you Keep it,\n"
                 "and kept changes can be rolled back later in the Changes tab.", 0.82, y, 0.02, GREY)
        y -= 0.1
        # every card or only the open ones (CHANGE 143: the page's "Showing open cards" button)
        cards = self.cards_filter(f, 1.33, y + 0.158, (self.teaching or {}).get("cards", []))
        if not cards:
            label(f, "No cards." if self.all_cards else "No requests waiting.", 0.82, y, 0.028, GREY)
        for c in cards:
            job = self.ai_jobs.get(c["id"], {})
            target = self.card_targets.get(c["id"], c["card"].get("target", "fighter"))
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
                label(f, f"Claude is working on it ({TARGETS[target]}), {took} s so far: usually under a minute, "
                         "a few minutes for whole-game changes, then it is tested...", 0.84, y, 0.022, BLUE, wrap=46)
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
                    if not TRY and not LOCAL and not fight_version.FROZEN:
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
        return sorted(try_local.mod_keys(change.after.get("fight_sim.py"))
                      - try_local.mod_keys(change.before.get("fight_sim.py")))

    def card_targets_row(self, f, y, c, target):
        for i, (key, text) in enumerate(TARGETS.items()):
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
        import ai_pipeline
        target = self.card_targets.get(c["id"], c["card"].get("target", "fighter"))
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
            prompt, target = str(e), "fighter"
        button(f, "Send to Claude", 0.95, y - 0.01, self.ai_send, [c], 0.028, (0.15, 0.45, 0.65, 1))
        button(f, "Copy prompt", 1.22, y - 0.01, self.copy_prompt, [c], 0.026)
        button(f, "Back", 1.42, y - 0.01, self.show_cards, [None], 0.026)
        y -= 0.065
        label(f, f"THE WHOLE PROMPT   ({TARGETS.get(target, target)})", 0.82, y, 0.026, YELLOW)
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
        """Teacher's AI cards tab: the list of requests (None), the learners' card ("edit"), or one card with its
        whole prompt before it is sent (the card's number)."""
        self.cards_view = view
        self.rebuild_panels()

    def send_card_note(self):
        """Teacher: what is typed in "From your teacher" goes on every learner's card (and stays for next time)."""
        note = " ".join(self.entries["card_note"].get().split())[:300] if "card_note" in self.entries else ""
        self.entry_text.pop("card_note", None)
        self.stop_typing()
        self.set_lesson({"ai_card_note": note})
        self.note_text.setText("Sent: it is on the learners' cards." if note else "Sent: nothing from you is on their cards.")

    def ai_retry(self, c, target=None):
        if target:
            self.card_targets[c["id"]] = target
        self.ai_jobs.pop(c["id"], None)
        self.ai_send(c)

    def ai_send(self, c):
        """Run the learner's approved request through Claude in the background."""
        import ai_pipeline
        learner_design = next((p["design"] for p in self.class_list if p["name"] == c["learner"]), None)
        target = self.card_targets.get(c["id"], c["card"].get("target", "fighter"))
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
        import ai_pipeline
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

    # ---------- the rings ----------
    def my_ring(self):
        return self.ring_of.get(self.my_id)

    def watched_ring(self):
        """The ring the camera and the fight screen follow: the one you chose, else your own, else the first."""
        rings = [r["i"] for r in (self.state or {}).get("rings", [])]
        if self.watch in rings:
            return self.watch
        mine = self.my_ring()
        return mine if mine in rings else (rings[0] if rings else None)

    def set_watch(self, i):
        self.watch = None if i == self.my_ring() else i
        self.cam.set_mode(self.cam.mode if self.cam.mode != "all" else "fight")
        if self.tab == "matches":
            self.rebuild_panels()

    def watch_ring(self, delta):
        rings = [r["i"] for r in (self.state or {}).get("rings", [])]
        if not rings:
            return
        cur = self.watched_ring()
        i = rings.index(cur) if cur in rings else 0
        self.focus = None  # (another ring: the camera follows your own fighter, or the ring's first)
        self.set_watch(rings[(i + delta) % len(rings)])
        self.banner_note(f"Watching ring {self.watched_ring() + 1}" + ("  (yours)" if self.watched_ring() ==
                                                                       self.my_ring() else ""), 2)

    def cycle_focus(self):
        """L (CHANGE 183): the camera follows the next fighter: round the ring you are watching, then the next
        ring's fighters (watching that ring), and back to your own. V then changes the view of that fighter. The
        teacher watches a learner this way."""
        rings = (self.state or {}).get("rings", [])
        w = self.watched_ring()
        k = next((n for n, r in enumerate(rings) if r["i"] == w), 0)
        order = [(r["i"], f["id"]) for r in rings[k:] + rings[:k] for f in r["f"]]  # (from the watched ring on)
        if not order:
            return
        ids = [fid for _, fid in order]
        cur = self.focus if self.focus in ids else self.my_id
        i = ids.index(cur) if cur in ids else -1
        ring_i, nxt = order[(i + 1) % len(order)]
        if self.cam.mode in ("ring", "all"):  # (a view that follows nobody: on them instead)
            self.cam.set_mode("me")
        if ring_i != w:
            self.set_watch(ring_i)
        self.focus = None if nxt == self.my_id else nxt
        self.cam.pos = None  # (cut straight to them)
        if self.focus is None:
            self.banner_note("Camera: your fighter" if self.my_id in ids else "Camera: the ring", 2)
        else:
            fighter_name, owner = self.names.get(nxt, ("?", ""))[:2]
            self.banner_note(f"Camera: {fighter_name} ({owner})" if owner else f"Camera: {fighter_name}", 2)

    def fix_mine(self):
        """Shift+F, the teacher only (CHANGE 182): the server mends the teacher's fighter (fight_server's "fix")."""
        send({"type": "fix"})

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
        self.read_network()
        if not args.no_interp:  # the picture for this moment: between two of the server's snapshots
            blended = self.snaps.sample(now)
            if blended is not None:
                self.state = blended
                if self.ahead_on and not args.no_ahead:  # (CHANGE 167)
                    self.state = self.fighter_ahead(blended, now, dt)
        self.send_controls(now)
        self.send_perf(now)
        watched = self.watched_ring()
        ring = next((r for r in (self.state or {}).get("rings", []) if r["i"] == watched), None)
        if self.state and self.roster:
            self.draw_state(dt, now, ring)
        me = enemy = None
        if ring:
            fs = [f for f in ring["f"] if f["a"] != "ringout" or f["pos"][2] > -1.5]
            picked = next((f for f in fs if f["id"] == self.focus), None) if self.focus is not None else None  # (L)
            mine = next((f for f in fs if f["id"] == self.my_id), None)
            first = picked or mine or (fs[0] if fs else None)
            other = next((f for f in fs if f is not first), None)
            me = Point3(*first["pos"]) if first else None
            enemy = Point3(*other["pos"]) if other else None
        centres = [tuple(r["c"]) for r in (self.state or {}).get("rings", [])]
        self.cam.update(dt, me, enemy, tuple(ring["c"]) if ring else (0.0, 0.0), centres, self.fx.shake_offset() * 0.5)
        self.fight_hud.update(ring, {k: v[:2] for k, v in self.names.items()}, self.my_id,
                              (self.state or {}).get("t", 0.0), dt, self.lesson.get("rounds_to_win", 2),
                              f"RING {watched + 1}" if watched is not None and watched != self.my_ring() else "")
        snd = self.my_sound()
        if self.muted:
            self.snd.layers("off", 0, False, 0, False, 0)
        else:
            self.snd.layers(snd["music"], snd["music_volume"], snd["crowd"], snd["crowd_volume"], False, 0)
        if self.newer and self.download_button is None:  # a newer release is out
            self.banner_note(f"Club Coders {self.newer} is out: press the green button to download it", 8)
            self.offer_download()
        self.limits_released()  # (a limit's slider let go: the class server gets the new limits)
        if self.pending_rebuild and not self.typing:  # typing stopped: now do the redraw that waited
            self.rebuild_panels()
        self.view_text.setText(f"view: {self.cam.name}  (V to change)" + ("   typing - Esc to stop" if self.typing else ""))
        self.banner.setText(self.note_text if now < getattr(self, "note_until", 0) else "")
        self.banner.setScale(0.075 if getattr(self, "note_big", False) else 0.05)
        if self.panel_bar and self.last_aspect != self.getAspectRatio():  # (the window resized: the body's cut-off moves)
            self.place_panel()
        if not TEACHER and now - self.prefs_at > 3:  # keep the learner's settings in their profile
            self.prefs_at = now
            prefs = self.gather_prefs()
            text = json.dumps(prefs, sort_keys=True)
            if text != self.prefs_sent:
                send({"type": "prefs", "prefs": prefs})
                self.prefs_sent = text
        return task.cont

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
            if kind == "state":
                ring_list = [r["i"] for r in m.get("rings", [])]
                if self.tab == "matches" and ring_list != [r["i"] for r in (self.state or {}).get("rings", [])]:
                    rebuild = True
                if TEACHER and self.tab == "teacher" and bool(m.get("paused")) != bool((self.latest or {}).get("paused")):
                    rebuild = True  # (the Pause button lights up: CHANGE 102)
                self.latest = m
                self.snaps.push(m)
                my = getattr(self, "my_id", None)
                mine = next((r for r in m.get("rings", []) if any(f["id"] == my for f in r.get("f", []))), None)
                if m.get("sm") is not None:  # (CHANGE 167: what your fighter is drawn ahead from)
                    self.ahead.snapshot(m["sm"] / 1000, mine["f"] if mine else [], my, mine.get("ph") if mine else None)
                if args.no_interp:
                    self.state = m
                self.fx_waiting.append(m.get("fx", []))
                self.note_ack(m)
            elif kind == "roster":
                self.apply_roster(m)
            elif kind == "welcome":  # back after a dropped connection (or a server restart)
                self.reconnecting = False
                if self.check_code(m):
                    return
                self.lesson, self.rules, self.design = m["lesson"], m["rules"], m["design"]
                self.obey_gfx_max()
                self.draft = copy.deepcopy(self.design)
                self.banner_note("Reconnected: carry on!", 3)
                self.code_shown = None
                rebuild = True
            elif kind == "lesson":
                if m["lesson"] != self.lesson or m.get("tournament") != self.tournament or \
                        (TEACHER and m["class"] != self.class_list):
                    rebuild = rebuild or self.tab in ("garage", "teacher", "learners", "matches") or \
                        (self.tab == "settings" and m["lesson"].get("gfx_max") != self.lesson.get("gfx_max"))
                mods = m.get("mods") or {}
                if mods != self.mod_info:  # a new vote, a maker's name, or someone from the group has come in
                    rebuild = rebuild or self.tab in ("teacher", "mods")
                    if TEACHER:
                        self.forget_mod_makers(mods)
                if TEACHER:  # the computer fighter was rebuilt or reset: the Learner view shows it as it is now
                    was = next((c["design"] for c in self.class_list if c["role"] == "computer"), None)
                    for c in m["class"]:
                        if c["role"] == "computer" and was is not None and c["design"] != was:
                            self.view_drafts.pop(c["name"], None)
                            self.entry_text.pop("name_" + c["name"], None)
                            self.code_shown = None
                self.show_missions_changed(self.lesson, m["lesson"])  # (CHANGE 122)
                self.lesson, self.class_list, self.tournament, self.mod_info = m["lesson"], m["class"], m.get("tournament"), mods
                self.obey_gfx_max()
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
                sig = json.dumps({k: v for k, v in m.items() if k != "punches"}, sort_keys=True)
                if sig != self.sig.get("missions"):
                    self.sig["missions"] = sig
                    rebuild = rebuild or self.tab in ("missions", "ai", "card")
            elif kind in ("experience", "experience_class"):  # (CHANGE 210)
                was = getattr(self.xhud, "m", None) is not None
                self.xhud.took(m)
                rebuild = rebuild or (TEACHER and self.tab == "teacher" and was != (self.xhud.m is not None))
            elif kind == "teaching":
                self.teaching = m
                sig = json.dumps(m, sort_keys=True)
                if sig != self.sig.get("teaching"):
                    self.sig["teaching"] = sig
                    rebuild = rebuild or self.tab in ("outcomes", "cards", "learners", "accounts")
            elif kind == "design_result":
                self.design = m["design"]
                self.code_changed = self.code_hack = False
                if m["ok"]:
                    self.draft = copy.deepcopy(self.design)
                    self.code_shown = None
                    self.entry_text.pop("name_me", None)
                    self.status_msg = ("Your teacher changed your fighter." if m.get("by_teacher") else
                                       "Built! Your fighter is back at the start of the round.", GREEN)
                    if m.get("by_teacher"):
                        self.banner_note("Your teacher changed your fighter", 4)
                else:
                    self.status_msg = ("Not built: " + "; ".join(m["problems"]), RED)
                rebuild = rebuild or self.tab == "garage" or self.show_code
            elif kind == "ai_card_result":
                if m["ok"]:
                    self.card_msg = ("Sent! The teacher will look at it." + (" Tip: " + " ".join(m["tips"]) if m["tips"] else ""), GREEN)
                    for k in CARD_FIELDS:
                        self.entry_text.pop(f"card_{k}", None)
                        if f"card_{k}" in self.entries:
                            self.set_entry(f"card_{k}", "")  # (a modern text box: set, not DirectEntry's enterText)
                else:
                    self.card_msg = ("Not sent: " + " ".join(m["problems"]), RED)
                try:  # show it straight away, even before the panel redraws
                    self.card_text.setText(self.card_msg[0])
                    self.card_text.setFg(self.card_msg[1])
                except Exception:
                    pass
                rebuild = rebuild or self.tab == "ai"
            elif kind == "brain_result":
                self.banner_note(("Brain: " + m["error"]) if m["ok"] else "Brain problem: " + m["error"], 5)
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
                self.note_ping((time.time() - m["t"]) * 1000)
            elif kind == "closed":
                self.connection_lost(m)
        if rebuild:
            self.rebuild_panels(from_game=True)

    def connection_lost(self, m):
        if m.get("code") == 4005:
            self.banner_note("You logged in again in another window, so this one has stopped.", 3600)
            return
        if m.get("code") in STOP_CODES:  # wrong code or password, deleted, or an old version: retrying won't help
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

    def fighter_ahead(self, state, now, dt):
        """(CHANGE 167) The blended state with your fighter's footwork drawn ahead (engine.ahead.FighterAhead)."""
        my = getattr(self, "my_id", None)
        rings = []
        for r in state.get("rings", []):
            if any(f["id"] == my for f in r.get("f", [])):
                r = dict(r, f=self.ahead.adjust(r["f"], now, self.snaps.clock.server_time(now), self.rtt or getattr(self, "ping_ms", 0.0) / 1000, my,
                                                self.move.get(my), dt, self.punch.get(my)))
            rings.append(r)
        return dict(state, rings=rings)

    def apply_roster(self, m):
        self.roster = m
        self.move = {f["id"]: tuple(f["move"]) for f in m.get("fighters", []) if f.get("move")}  # (CHANGE 167)
        self.punch = {f["id"]: f["punch"] for f in m.get("fighters", []) if f.get("punch")}  # (CHANGE 193)
        drawn = json.dumps([m.get("look", {}), m.get("rings"), m.get("hazards"), m.get("rs"), m.get("user_mods")],
                           sort_keys=True)
        if drawn != self.stage_drawn:
            if self.stage_vis:
                self.stage_vis.destroy()
            sim.RULES["ring_size"] = m.get("rs", sim.RULES["ring_size"])
            self.stage_vis = StageVisual(self.render, m["rings"], m["hazards"], m.get("look"), m.get("user_mods"))
            self.stage_drawn = drawn
        # (CHANGE 175) only a fighter whose design or owner changed is built again (a roster comes every second with
        # the windows' reports in it: building every fighter in every ring each time froze the window for seconds)
        wanted = {f["id"]: f for f in m["fighters"]}
        keyed = {fid: json.dumps([f["design"], f["owner"]], sort_keys=True, default=str) for fid, f in wanted.items()}
        for fid in list(self.fighters):
            if fid not in wanted or self.fighter_keys.get(fid) != keyed[fid]:
                self.fighters.pop(fid).destroy()
                self.fighter_keys.pop(fid, None)
        for fid, f in wanted.items():
            if fid in self.fighters:
                continue
            fv = fight_model.make(self.render, f["design"])
            boss = f["design"].get("model")
            fv.set_label(f"{f['design']['name']}\n{'Boss' if boss and f['owner'] == 'Computer' else f['owner']}",
                         (1, 0.75, 0.3, 1) if f["owner"] == "Computer" else (1, 1, 1, 1))
            self.fighters[fid] = fv
            self.fighter_keys[fid] = keyed[fid]
        self.my_id = m["mine"].get(name)
        self.ring_of = {f["id"]: f["ring"] for f in m["fighters"]}
        self.names = {f["id"]: (f["design"]["name"], f["owner"], tuple(v / 255 for v in f["design"]["colour"]),
                                f["design"].get("body", "robot")) for f in m["fighters"]}


    def note_ping(self, ms):
        """(CHANGE 175) The round trip: ping_ms as measured (the status line), rtt the one drawing ahead uses: the
        quickest of the last six, rising by at most 10 ms a second, so a spike in one sample doesn't move every
        robot drawn ahead at once and back a second later."""
        self.ping_ms = ms
        self.pings.append(ms)
        del self.pings[:-6]
        target = min(self.pings) / 1000
        self.rtt = target if self.rtt is None or target < self.rtt else min(target, self.rtt + 0.01)

    # ---------- your controls ----------
    def press(self, action):
        """A fighting key was pressed: send it straight away (the server keeps it for a moment, so it isn't missed)."""
        self.pending_press = action
        self.send_controls(time.perf_counter(), force=True)

    def stick(self, pad=None):
        """The arrow keys (or a controller's stick: CHANGE 170) as (forward, side) for your fighter: the camera
        decides which way is which, so right always moves right on the screen."""
        down = self.mouseWatcherNode.is_button_down
        sx = down(KeyboardButton.right()) - down(KeyboardButton.left())
        sy = down(KeyboardButton.up()) - down(KeyboardButton.down())
        if pad and not sx and not sy:
            sx, sy = round(pad.x, 2), round(pad.y, 2)  # (analogue: a little push is a slow walk)
        if not sx and not sy:
            return 0.0, 0.0
        ring = next((r for r in (self.state or {}).get("rings", []) if r["i"] == self.my_ring()), None)
        mine = next((f for f in (ring or {}).get("f", []) if f["id"] == self.my_id), None)
        other = next((f for f in (ring or {}).get("f", []) if f["id"] != self.my_id), None)
        if mine is None:
            return 0.0, 0.0
        q = self.camera.getQuat(self.render)
        right, ahead = q.getRight(), q.getForward()
        right.z = ahead.z = 0
        if right.length() < 1e-3 or ahead.length() < 1e-3:
            return float(sy), float(-sx)
        right.normalize()
        ahead.normalize()
        want = right * sx + ahead * sy  # where on the floor the arrows point
        if other is not None:
            face = Vec3(other["pos"][0] - mine["pos"][0], other["pos"][1] - mine["pos"][1], 0)
        else:
            import math
            face = Vec3(-math.sin(math.radians(mine["h"])), math.cos(math.radians(mine["h"])), 0)
        if face.length() < 1e-3:
            return float(sy), float(-sx)
        face.normalize()
        left = Vec3(-face.y, face.x, 0)
        fwd, side = want.dot(face), want.dot(left)
        return max(-1.0, min(1.0, fwd * 1.4)), max(-1.0, min(1.0, side * 1.4))

    def send_controls(self, now, force=False):
        if now - self.last_ping > 1:
            send({"type": "ping", "t": time.time()})
            self.last_ping = now
        if self.mouseWatcherNode is None:
            return
        down = self.mouseWatcherNode.is_button_down
        press = getattr(self, "pending_press", None)
        self.pending_press = None
        pad = self.pad.read()  # (CHANGE 170: read every frame, so a button tapped between two isn't lost)
        if pad and not press and not (self.typing or not self.started):
            press = next((PAD_PRESS[b] for b in PAD_ORDER if b in pad.pressed), None)
            if "start" in pad.pressed:
                self.toggle_panel()
        behind = getattr(self.win, "getProperties", None) and not self.win.getProperties().getForeground()
        if self.typing or behind:  # arrows and space move the text cursor, not the fighter; and a key held
            # as the window loses focus would never let go (its key-up never arrives): no input while behind
            control = (0.0, 0.0, "")
            press = None
        else:
            fwd, side = self.stick(pad)
            block, crouch = down(KeyboardButton.shift()), down(KeyboardButton.asciiKey("x"))
            if pad:  # (CHANGE 170) left shoulder: block; left trigger: crouch (both held)
                block, crouch = block or "lb" in pad.held, crouch or "lt" in pad.held
            hold = "low_block" if block and crouch else "block" if block else "crouch" if crouch else ""
            control = (round(fwd, 2), round(side, 2), hold)
        # a change or a press goes at once; otherwise the control is repeated 30 times a second, numbered, so a message
        # lost or held up on the way is made good by the next one (the server ignores one that arrives out of order)
        if press or force or control != self.last_control or now - self.last_send > 1 / 30:
            self.ctrl_seq = (self.ctrl_seq + 1) % 65536
            msg = {"type": "control", "seq": self.ctrl_seq, "f": control[0], "s": control[1], "hold": control[2]}
            if press:
                msg["press"] = press
            send(msg)
            self.ahead.control(now, control[0], control[1], control[2])  # (CHANGE 167)
            if press:
                self.ahead.press(now, press)  # (CHANGE 193: a punch's start-up drawn at once)
            self.ctrl_sent[self.ctrl_seq] = now
            if len(self.ctrl_sent) > 90:
                for k in sorted(self.ctrl_sent)[:30]:
                    del self.ctrl_sent[k]
            self.last_control, self.last_send = control, now

    def note_ack(self, m):
        """A snapshot says which of our controls the server had applied: how long a key press takes to show."""
        my_id = getattr(self, "my_id", None)
        seq = (m.get("acks") or {}).get(str(my_id)) if my_id is not None else None
        sent = self.ctrl_sent.get(seq)
        if sent is not None:
            ms = (m.get(interp.RECEIVED, time.perf_counter()) - sent) * 1000
            self.ctrl_ms = ms if self.ctrl_ms is None else self.ctrl_ms * 0.8 + ms * 0.2

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
        network stalls and the blending delay)."""
        if TEACHER:
            self.show_perf(now)
        if now - self.perf_at < 3:
            return
        self.perf_at = now
        rep = self.snaps.report()
        send({"type": "perf", "fps": round(self.clock.getAverageFrameRate()), "ping": round(self.ping_ms),
              "tier": getattr(self, "gfx_tier", None) or args.gfx, "stalls": rep["stalls"], "delay": rep["delay_ms"],
              "ctrl": None if self.ctrl_ms is None else round(self.ctrl_ms)})

    # ---------- sounds and drawing ----------
    def event_sounds(self, st, now):
        """Moves starting (a whoosh), the bell, knockouts and wins, and the crowd's reactions."""
        snd = self.my_sound()
        if self.muted or not snd["effects"]:
            return
        vol = snd["volume"]
        watched = self.watched_ring()
        for r in st["rings"]:
            near = 1.0 if r["i"] == watched else 0.25
            phase = self.last_phase.get(r["i"])
            if phase == "intro" and r["ph"] == "fight" and r["i"] == watched:
                self.snd.bell()
                self.snd.say("go", 0.9 * min(1.0, vol / 0.7))
            elif r["ph"] == "intro" and r["bn"] in ("3", "2", "1") and r["i"] == watched and \
                    self.last_banner.get(r["i"]) != r["bn"]:  # a robot's voice says the count (CHANGE 153)
                self.snd.say(int(r["bn"]), 0.9 * min(1.0, vol / 0.7))
            self.last_banner[r["i"]] = r["bn"]
            if phase == "fight" and r["ph"] == "ko":
                if r["i"] == watched:
                    self.snd.ko()
                self.snd.react("cheer", now)
            if r["ph"] == "over" and self.last_winner.get(r["i"]) != r["bn"]:
                self.snd.react("applause", now)
            self.last_winner[r["i"]] = r["bn"] if r["ph"] == "over" else ""
            self.last_phase[r["i"]] = r["ph"]
            for f in r["f"]:
                a, last = f["a"], self.last_anim.get(f["id"])
                if a in ATTACK_ANIMS and (last is None or last[0] != a or f["k"] < last[1] - 0.5) and f["k"] < 1.5:
                    self.snd.swing(a, 0.7 * vol * near)
                elif a == "jump" and (last is None or last[0] != "jump"):
                    self.snd.play("f_jump", 0.4 * vol * near)  # (CHANGE 134: the pool has f_jump; "jump" was silent)
                self.last_anim[f["id"]] = (a, f["k"])

    def draw_state(self, dt, now, watched_ring):
        st = self.state
        if self.stage_vis:
            self.stage_vis.update(st["rings"], st["t"], dt)
        # sparks, flashes and hit sounds
        watched = watched_ring["i"] if watched_ring else None
        all_f = [(f, r["i"]) for r in st["rings"] for f in r["f"]]
        snd = self.my_sound()
        for fx in self.fx_waiting:
            for pos, dmg, kind in fx:
                victim = min(all_f, key=lambda fr: sum((a - b) ** 2 for a, b in zip(fr[0]["pos"], pos)), default=None)
                vid = victim[0]["id"] if victim else None
                colour = self.names.get(vid, (0, 0, (0.8, 0.8, 0.8)))[2]
                robot = self.names.get(vid, (0, 0, 0, "robot"))[3] == "robot"
                self.fx.impact(pos, dmg, kind, colour, robot)
                if kind == "zap" and self.stage_vis:
                    self.stage_vis.zap(pos)
                if not self.muted and snd["effects"]:
                    far = (Point3(*pos) - self.camera.getPos()).length()
                    self.snd.hit(kind, min(1.0, 0.35 + dmg / 20) * max(0.15, 1 - far / 30) * snd["volume"] * 1.3, robot)
                    if kind == "counter" or dmg >= 14:
                        self.snd.react("ooh", now)
        self.fx_waiting = []
        self.fx.update(dt)
        self.event_sounds(st, now)
        close_up = self.cam.mode in ("fight", "me", "shoulder")
        for r in st["rings"]:
            for s in r["f"]:
                fv = self.fighters.get(s["id"])
                if fv is not None:
                    fv.update(s, dt)
                    fv.show_label(not (close_up and r["i"] == watched))  # (the fight screen shows their names)
        # the rings list (top left): who is fighting who in every ring
        rows = []
        for r in st["rings"]:
            parts = []
            for f in r["f"]:
                nm = self.names.get(f["id"], ("?",))[0]
                you = "*" if f["id"] == self.my_id else ""
                parts.append(f"{you}{nm} {round(100 * f['hp'] / max(1, f['max']))}%" + (f" ({f['w']})" if f["w"] else ""))
            what = r["bn"] if r["bn"] else ("training" if r.get("tl") is None else f"round {r['rd']}  {int(r['tl'] or 0)} s")
            rows.append((r["i"], f"Ring {r['i'] + 1}{' - ' + r['lb'] if r['lb'] else ''}:  " + "  v  ".join(parts) +
                         f"   [{what}]"))
        for i, row in enumerate(self.ring_rows):
            if i < len(rows):
                row.setText(rows[i][1])
                row.setFg(YELLOW if rows[i][0] == watched else WHITE)
            else:
                row.setText("")
        if not self.rings_small:
            self.rings_back["frameSize"] = (-1.76, -0.62, 0.5 - max(1, len(rows)) * 0.05, 0.72)
        mode = "PRACTICE (no damage)" if st["practice"] else "BATTLE"
        if st.get("paused"):
            mode += "  -  PAUSED"
        t = self.tournament
        if t:
            mode += f"   TOURNAMENT: {'CHAMPION ' + t['champion'] if t.get('champion') else t['title']}"
        self.mode_text.setText(mode)
        self.status_text.setText(f"{self.clock.getAverageFrameRate():.0f} fps   ping {self.ping_ms:.0f} ms"
                                 f"  gfx {self.gfx_tier}")
        self.feed.setText("\n".join(st["events"]))


if __name__ == "__main__":
    Lab().run()
