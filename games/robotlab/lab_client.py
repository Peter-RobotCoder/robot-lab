"""Robot Lab window for learners and the teacher. The fight runs on lab_server.py.

Learner:  python lab_client.py                (log in with a username and password in the window)
Teacher:  python lab_client.py --name "Mr P" --teacher
Class server: add --host wss://play.<club domain> (the downloaded game has it built in). Learners type the class
code once (it is remembered on that computer); the teacher's code comes from --code, ROBOTLAB_TEACHER_CODE or
teacher_settings.json next to this file (never in GitHub).

Logging in: a new username makes a new profile. Everything is saved to it (robot, missions, brain,
camera view), so after a dropped connection the window reconnects by itself, and next lesson the
learner logs in with the same username and password to carry on.

Driving:   Arrow keys drive   Space is the weapon key: it fires a wedge or hammer, and switches a spinner or
           drum on and off (every robot starts with its weapon off)
Panels:    M missions   G garage   I AI request card   C your robot as code (edit it, then Apply)
           J user mods (learners' ideas in the game: tick the ones you'd like, the teacher switches them on)
           T teacher panels (the teacher's Learner view shows and changes what a learner sees)   H help
Brain:     U upload brains/my_brain.py   P autopilot on/off (your brain drives)
Camera:    V change view (third person, first person, zoomed arena follow, full arena, centre camera)
           O full arena   mouse wheel or + / - zoom in and out (every view)
           drag with the right mouse button (or Q / E) to swing the view round and tilt it   Home resets the view
Typing:    while you type in a text box, keys go into the box (not the game). Click away or press Esc to stop.
           Tab goes on to the next text box, and Shift+Tab back to the one before.
           In the code panel, click where you want to type, or drag to select. APPLY CODE applies your code,
           and the mouse wheel scrolls code that is too long for the panel.
"""
import argparse
import ast
import copy
import json
import math
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time
import webbrowser

from panda3d.core import TransparencyAttrib
from panda3d.core import loadPrcFileData

import lab_version  # (first: this records the code this window is running, before anything can change it)
sys.path.insert(0, lab_version.ENGINE_HOME)  # (the engine package, shared by every game: engine/ beside the games)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="", help="username (learners are asked in the window if it's left out)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--host", default=None,
                help="server address (default: this computer, or the class server in the downloaded game); "
                     "'class' = the one in teacher_settings.json")
ap.add_argument("--code", help="class code (the demo codes on a laptop test server)")
ap.add_argument("--gfx", choices=["low", "medium", "high"], default="medium", help="use low on old laptops")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--x", type=int, help="window position (left edge)")
ap.add_argument("--tab", help=argparse.SUPPRESS)
ap.add_argument("--show-code", action="store_true", help=argparse.SUPPRESS)  # (tests: open the code panel)
ap.add_argument("--card", help=argparse.SUPPRESS)
ap.add_argument("--view-tab", help=argparse.SUPPRESS)  # (tests: the Learner view opens on this tab)  # (tests: the teacher's AI cards tab opens on "edit" or a card's id)
ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
ap.add_argument("--scroll", type=float, help=argparse.SUPPRESS)  # (tests: slide the side panel this far after 3 s)
ap.add_argument("--ticket", help=argparse.SUPPRESS)  # (from the club desk: the app has logged this person in)
args = ap.parse_args()
if os.environ.get("ROBOTLAB_LOGIN") and not args.name:  # reopened by itself (to load code changes): same login
    try:
        args.name, args.password, *rest = json.loads(os.environ.pop("ROBOTLAB_LOGIN"))
        args.ticket = rest[0] if rest and rest[0] else args.ticket
    except ValueError:
        pass
TEACHER = args.teacher
HERE = os.path.dirname(os.path.abspath(__file__))
TEACHER_SETTINGS = os.path.join(HERE, "teacher_settings.json")  # the teacher's laptop only: never in git
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RobotLab")
from engine import editor as lab_editor  # noqa: E402  (the engine: shared by every game)
from engine import hud  # noqa: E402
from engine import garage, schema  # noqa: E402
from engine.hud import (DARK, SWATCHES, TEXT_SIZES, TIPS, button, check, label, load_json, remember, text_button,  # noqa: E402,F401
                        word)
from engine.hud import YELLOW, WHITE, GREY, RED, GREEN, BLUE, ORANGE, PANEL, ON, OFF, BOX, HANDLE  # noqa: E402,F401
SETTINGS = hud.setup(SETTINGS_DIR, sys.modules[__name__])  # this computer's settings; this module's colours follow the look
# learners edit brains/my_brain.py: next to Robot Lab.exe in the download, next to this file otherwise
BRAINS = os.path.join(os.path.dirname(sys.executable), "brains", "robotlab") if lab_version.FROZEN else os.path.join(HERE, "brains")  # (Club Coders: each game has its own brains folder)




if args.host == "class":  # the class server's address, from the teacher's settings
    args.host = load_json(TEACHER_SETTINGS).get("server") or lab_version.ONLINE_SERVER
elif args.host is None:  # a learner's last choice on the login screen, or this computer / the built-in server
    where = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("where")
    args.host = {"local": lab_version.LOCAL_SERVER, "online": lab_version.ONLINE_SERVER}.get(
        where if not TEACHER else None, lab_version.SERVER)
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))  # a laptop test server
from engine import try_local  # noqa: E402
# Try it on this laptop (see try_local): the teacher's window, opened on a test server here to look at this
# laptop's game before it is made live for the class. It knows how to go back to the class.
TRY = try_local.unpack(os.environ.pop("ROBOTLAB_TRY", "")) if args.teacher and LOCAL else None
from engine import club_ticket  # noqa: E402
if args.ticket:  # the club desk has logged this person in: their name is in the ticket (the server checks it)
    args.name = (club_ticket.peek(args.ticket) or {}).get("name") or args.name
if args.code or args.ticket:
    code = args.code or ""
elif TEACHER:  # (a laptop test server takes the demo code: the real one only ever goes to the class server)
    code = "TEACH99" if LOCAL else (os.environ.get("ROBOTLAB_TEACHER_CODE")
                                    or load_json(TEACHER_SETTINGS).get("teacher_code"))
    if not code:
        raise SystemExit("The teacher code is needed: put it in teacher_settings.json next to lab_client.py "
                         '(for example {"teacher_code": "..."}) or use --code.')
else:  # (the remembered code is the online class server's; a laptop test server has the demo code)
    code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
name = args.name or ("Teacher" if TEACHER else "")
net = None  # the connection to the server, made when you log in

title = f"Robot Lab - {'TEACHER' if TEACHER else 'LEARNER'}" + (f" ({name})" if name else "")
if TRY:
    title += " - TRYING ON THIS LAPTOP"
x = args.x if args.x is not None else (40 if TEACHER else 1360)
loadPrcFileData("", f"win-size 1280 720\nwindow-title {title}\nframebuffer-multisample 1\nmultisamples 4\n"
                    f"win-origin {x} 80\n")
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame, DirectSlider  # noqa: E402
from direct.gui.OnscreenImage import OnscreenImage
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import (Filename, KeyboardButton, MouseButton, Point3, TextNode,  # noqa: E402
                          WindowProperties)

import cpu_brains  # noqa: E402
import lab_missions as lm  # noqa: E402
import lab_sim as sim  # noqa: E402
import rw_fx  # noqa: E402
import rw_gfx  # noqa: E402
from engine import rw_sound  # noqa: E402
from engine.net import Net  # noqa: E402
from rw_camera import GameCamera  # noqa: E402
from rw_gfx import ArenaVisual, RobotVisual  # noqa: E402

PRETTY = {"forward_speed": "Forward speed", "reverse_speed": "Reverse speed", "turn_speed": "Turn speed",
          "acceleration": "Acceleration", "size": "Size", "points_table": "Points table",
          "choose_weapon": "Choose weapon", "name_and_colour": "Name and colour", "code_view": "Code view",
          "stats_readout": "Stats readout", "weapon_toggle": "Weapon on/off", "house_robots": "Resident Robots",
          "brains": "Autopilot (U and P)"}
HAZARD_NAMES = {"pit": "Drop zone open", "floor_flipper": "Floor flipper", "saws": "Floor saws",
                "spikes": "Wall spikes", "house_robots": "Resident Robots"}
LEARNER_TABS = [("missions", "Mission"), ("garage", "Garage"), ("ai", "AI card"), ("card", "My card"),
                ("mods", "Mods"), ("settings", "Settings")]  # (one key, I, opens and closes the HUD: CHANGE 103)
TEACHER_TABS = [("teacher", "Controls"), ("mods", "User mods"), ("learners", "Learners"), ("accounts", "Accounts"),
                ("outcomes", "Outcomes"), ("cards", "AI cards"), ("changes", "Changes"), ("limits", "Limits"),
                ("warnings", "Warnings"), ("garage", "My robot"), ("settings", "Settings")]  # (drawn in two rows)
CODE_ROWS = 19     # lines of code the code panel shows at once (longer code scrolls)
CODE_PANEL = (-0.86, 0.12, -0.85, 0.36)  # the code panel in its first place: left, right, bottom, top
IDEA_ROWS = 6      # lines in the "My idea" box of the AI request card (CHANGE 93: room to write)
CARD_ROWS = 4      # ...and in each of its other boxes (every box wraps; 2,000 letters each)
INTRO = (2.5, 5.0, 8.0)  # the countdown before a battle: the arena's name until 2.5 s, who is fighting until 5 s,
#                          then 3, 2, 1 (the server ends it at 8 s: ACTIVATE!)
STOP_CODES = (4001, 4004, 4006, 4007, 4008, 4009, 4010, 4011)  # the server said no: wrong code or password,
# old version, deleted, the session ended, the group hasn't started, a ticket that ran out
TARGETS = {"robot": "Their robot", "arena": "The arena", "rules": "The rules", "game": "The whole game"}
APP = None  # the window (so any button click can end typing in a text box)
AI_RULES = ("Only the teacher uses the AI.  Never put personal information in a request.\n"
            "AI can be wrong: you test the code and must be able to explain it.\n"
            "Say where AI helped (the tool and the date).")
CARD_FIELDS = ("goal", "variables", "test", "predict")




def send(msg):
    if net is not None:
        net.send(msg)


class Lab(hud.HudKit, ShowBase):
    VERSION, LIVE_ID = lab_version.VERSION, lab_version.live_id()
    UNIT, CPU_VIEW = "robot", "Computer robot"
    FIRST_TAB = "teacher" if TEACHER else "missions"
    teacher = TEACHER
    CODE_PANEL, CODE_ROWS = CODE_PANEL, CODE_ROWS
    reflections = ("2d", "5b")
    user_mods = sim.USER_MODS
    STAGE_WORD = "ARENA"
    LIMITS_TITLE = "ROBOT LIMITS"
    LIMITS_NOTE = "Size: 100 is the standard size, 12.5 is one eighth of it and 200 is double."

    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.07, 0.08, 0.11)
        global APP
        APP = self
        hud.setup_app(self, send)
        self.init_hud()  # (the engine's HUD kit: text boxes, the side panel, settings, the code panel's place)
        self.preview_setup()  # (CHANGE 82)
        self.my_name = name
        rw_gfx.init(self, args.gfx)
        self.fx = rw_fx.Effects(self.render, args.gfx)
        self.snd = rw_sound.Sounds(self, on=not args.offscreen)
        self.muted = False
        self.pending_rebuild = False  # a panel redraw waiting until typing stops
        self.started = False
        self.login_panel = None
        self.delete_armed = None      # teacher: the account whose Delete button says "Sure?"
        self.newer, self.download_button = None, None  # a newer release on GitHub, and its download button
        if lab_version.FROZEN or not LOCAL:
            self.check_for_update()
        self.accept("escape", self.escape)
        self.accept("mouse1", self.stop_typing)  # clicking the arena (not a panel) stops typing
        self.accept("tab", self.tab_key, [1])           # Tab: on to the next text box
        self.accept("shift-tab", self.tab_key, [-1])    # ...and Shift+Tab: back to the one before
        self.start = self.last = time.perf_counter()
        if TEACHER or args.ticket or (args.name and args.password):
            error = self.connect(name, args.password or "")
            if error:
                if TEACHER:
                    raise SystemExit(error)
                self.show_login(error)
        else:
            self.show_login()
        self.taskMgr.add(self.update, "update")

    # ---------- logging in ----------
    def connect(self, username, password):
        """Connect and log in. Returns None if it worked, or a message saying what went wrong."""
        global net, name
        try:
            net = Net(args.host, username, code, password=password, version=lab_version.VERSION,
                      **({"ticket": args.ticket} if args.ticket else {}))
        except OSError:
            net = None
            return f"Can't reach the Robot Lab server ({args.host}). Is it running?"
        except Exception as e:  # e.g. the secure connection couldn't be set up
            net = None
            return f"Can't connect to the Robot Lab server ({args.host}): {e}"
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

    def show_login(self, error=""):
        self.login_panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))  # backdrop
        f = DirectFrame(parent=self.login_panel, frameColor=PANEL, frameSize=(-0.62, 0.62, -0.5, 0.46))
        label(f, "ROBOT LAB", 0, 0.34, 0.08, YELLOW, TextNode.ACenter)
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
        args.host = lab_version.LOCAL_SERVER if local else lab_version.ONLINE_SERVER
        LOCAL = local
        code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
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
        props.setTitle(f"Robot Lab - {'TEACHER' if TEACHER else 'LEARNER'} ({name})")
        if self.win is not None and not args.offscreen:
            self.win.requestProperties(props)
        self.started = True
        self.lesson, self.rules = welcome["lesson"], welcome["rules"]
        self.design = welcome["design"]          # the last design the server accepted
        self.draft = copy.deepcopy(self.design)  # what is being edited in the garage
        self.class_list, self.missions, self.teaching, self.tournament = [], None, None, None
        self.sig = {}                            # what each panel was last drawn from
        self.card_checks = {"privacy": False, "review": False, "credit": False}
        self.card_msg = ("", WHITE)
        self.card_target = "robot"
        self.ai_jobs = {}        # teacher: card id -> {"status", "result", "change"}
        self.card_targets = {}   # teacher: card id -> what Claude may change (can differ from the learner's choice)
        self.card_user_mod = {}  # teacher: card id -> make a whole-game change as a switchable user mod
        self.cards_view = None   # teacher's AI cards tab: None (the requests), "edit" (the learners' card), a card's id
        if args.card:
            self.cards_view = int(args.card) if args.card.isdigit() else args.card
        self.prompt_view, self.prompt_state = None, {}  # ...that card's whole prompt, in a box that scrolls
        self.view_name, self.view_tab = None, "garage"   # teacher's learner view
        if args.view_tab:
            self.view_tab = args.view_tab
        self.change_view, self.change_page, self.change_msg = None, 0, ("", GREY)  # teacher's Changes tab
        self.needs_restart = bool(welcome.get("live_ready"))  # a code change (or a live update) waits for a restart
        self.view_drafts, self.view_missions = {}, {}
        self.code_shown, self.code_msg, self.code_building = None, ("", GREY), False
        self.default = welcome.get("default")  # the lesson's starting robot (RESET CODE in the code panel)
        self.session = {}  # teacher: the club desk's live session and the next one (the Accounts tab)
        self.code_hack = False  # the design holds a value changed in the code that this lesson's garage hides
        self.code_changed = False  # the design holds a value changed in the code (Mission 1: hack the code)
        self.custom_colour = None  # the garage's custom colour block: the colour the code last set (CHANGE 48)
        self.code_state, self.code_editor = {"lines": [""], "cursor": [0, 0], "scroll": 0}, None  # the code panel
        self.schema = sim.schema()  # the robot's variables: the code panel and the garage's tables come from it
        self.intro_beeped, self.intro_was, self.activate_until = set(), False, 0.0  # the countdown before a battle
        self.cam = GameCamera(self, "third")
        self.arena_vis, self.hazards_drawn = None, None
        self.robots, self.roster, self.my_id, self.names = {}, None, None, {}
        self.full_roster, self.my_arena, self.watch = None, None, None  # (CHANGE 75: the arena drawn; watch =
        #                                                                 the one you chose, None = your own)
        self.house = set()       # ids of the Resident Robots
        self.state, self.ping_ms, self.status_msg = None, 0.0, ("", WHITE)
        self.fx_waiting = []
        self.reconnect_thread = None
        self.was_ko, self.last_winner = {}, ""  # (for the crowd's reactions)
        self.fire_counts, self.weapons = {}, {}  # (for weapon sounds: each robot's firings, and its weapon)
        self.last_hp, self.flash = {}, {}
        self.last_send = self.last_ping = 0.0
        self.last_control = None
        self.panel = self.code_panel = None
        self.tab = args.tab or ("teacher" if TEACHER else "missions")
        self.show_code = args.show_code
        self.reconnecting = False
        self.restore_prefs(welcome.get("prefs", {}))
        send({"type": "slot", "do": "list"})  # (my saved designs: CHANGE 83)
        tabs = [t for t, _ in (TEACHER_TABS if TEACHER else LEARNER_TABS)]
        if not args.tab and getattr(self, "last_tab", None) in tabs:  # (CHANGE 103: back on the tab last used)
            self.tab = self.last_tab
            self.rebuild_panels()
        self.key("i", self.toggle_panel)  # (CHANGE 103: the one HUD key)
        self.key("c", self.toggle_code)
        self.key("h", self.toggle_help)
        self.key("u", self.upload_brain)
        self.key("p", self.autopilot_key)
        self.key("v", self.cam.cycle)
        self.key("o", self.cam.set_mode, "arena")
        self.key("wheel_left", self.cam.pan, -0.6)   # sideways scroll moves the view sideways (CHANGE 112)
        self.key("wheel_right", self.cam.pan, 0.6)
        self.key("q", self.cam.turn, 20)   # swing the view round (or drag with the right mouse button)
        self.key("e", self.cam.turn, -20)
        self.key("home", self.cam.reset_view)
        self.key("n", self.toggle_mute)
        self.key("b", self.toggle_hud)
        self.key("[", self.watch_arena, -1)
        self.key("]", self.watch_arena, 1)
        self.key("page_up", self.slide_panel, -1)
        self.key("page_down", self.slide_panel, 1)
        for key, factor in (("=", 0.8), ("+", 0.8), ("-", 1.25), ("=-repeat", 0.9), ("--repeat", 1.11)):
            self.key(key, self.cam.wheel, factor)
        for key, factor, step in (("wheel_up", 0.88, -1), ("wheel_down", 1 / 0.88, 1)):
            self.key(key, self.wheel, factor, step)
        self.hud()
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
        if args.scroll:
            self.taskMgr.doMethodLater(3, lambda t: (setattr(self, "panel_scroll", args.scroll), self.place_panel())
                                       and None, "test scroll")
        if args.selftest:  # press the garage's buttons the way a learner would and build, then hack the code
            def gui(t):  # (Mission 1's objectives a, b and c: a string, two integers and a list, with the GUI)
                self.draft["name"] = "Richy"
                self.draft["settings"]["turn_speed"], self.draft["settings"]["size"] = 90, 80
                self.change_points("speed", 5)
                self.change_points("armour", -5)
                self.set_colour([60, 190, 90])
                self.send_design()

            def hack(t):  # (objective d: a value changed in the code editor)
                self.show_code = True
                self.rebuild_panels()
                lines = self.code_state["lines"]
                lines[:] = [("forward_speed: int = 95" if line.startswith("forward_speed") else line) for line in lines]
                self.rebuild_from_code()

            def resize(t):  # (the code panel made bigger, as the corner grip does)
                self.code_size = self.code_fit(0.5, 0.3)
                self.refresh_code_panel()

            def report(t):
                done = ", ".join(f"{x['id']}={'done' if x['done'] else 'todo'}" for x in (self.missions or {}).get("missions", []))
                print(f"SELFTEST objectives: {done}; code panel rows {self.code_rows()}", flush=True)
            for secs, fn in ((2, gui), (3.5, hack), (4.5, resize), (5.5, report)):
                self.taskMgr.doMethodLater(secs, fn, f"selftest {fn.__name__}")

    def restore_prefs(self, prefs):
        """A learner's camera view and half-typed AI card, from their profile."""
        self.cam.restore(prefs.get("camera", {}))
        self.restore_hud_prefs(prefs)  # (the code panel's place and size, text size, look, the wheel)
        if isinstance(prefs.get("sound"), dict):  # (their own sound settings: CHANGE 107)
            self.sound_prefs = rw_sound.sound_settings(prefs["sound"])
        if prefs.get("hud_at"):  # (the panel is drawn after this: hud_dark reads it)
            self.saved_hud_at = prefs["hud_at"]
            if hasattr(self, "hud_node"):
                self.set_hud_at(prefs["hud_at"])
        for k in CARD_FIELDS:
            if prefs.get("card", {}).get(k):
                self.entry_text[f"card_{k}"] = str(prefs["card"][k])[:2000]
        if prefs.get("card_target") in lm.AI_TARGETS and prefs["card_target"] != "game":
            self.card_target = prefs["card_target"]
        self.prefs_sent = json.dumps(self.gather_prefs(), sort_keys=True)

    def gather_prefs(self):
        card = {}
        for k in CARD_FIELDS:
            e = self.entries.get(f"card_{k}")
            card[k] = e.get() if e is not None else self.entry_text.get(f"card_{k}", "")
        return {"camera": self.cam.settings(), "card": card, "card_target": self.card_target, **self.hud_prefs(),
                "hud_at": [round(v, 3) for v in getattr(self, "hud_at", (0.0, 0.0))],
                **({"sound": self.sound_prefs} if getattr(self, "sound_prefs", None) else {})}

    def key(self, key, fn, *extra):
        """A game shortcut key. It does nothing while you are typing in a text box."""
        self.accept(key, lambda: None if self.typing or not self.started else fn(*extra))

    def escape(self):
        if self.typing:  # Esc while typing just stops typing
            self.stop_typing()
        else:
            self.userExit()

    def tab_key(self, step):
        """Tab moves the typing from one text box to the next (Shift+Tab: to the one before), on the login screen
        and every other screen; from the last box it goes round to the first. Text boxes only, in the order they
        are on the screen (the order they were made): not buttons or tick boxes. In the code panel Tab types four
        spaces instead, as a code editor's does (lab_editor)."""
        keys = list(self.entries)
        if self.typing == "code" or not keys:
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
        hud.set_theme("dark")  # (the HUD over the arena is always the dark look: it is drawn once, over the game)
        self.hud_dark()
        hud.set_theme(was)

    def hud_dark(self):
        # the health bars panel: one node, dragged by its title bar out of the way (CHANGE 79)
        self.hud_node = self.aspect2d.attachNewNode("health bars panel")
        self.hud_back = DirectFrame(parent=self.hud_node, frameColor=PANEL, frameSize=(-1.76, -0.86, 0.36, 0.97),
                                    state=DGG.NORMAL)
        self.hud_back.bind(DGG.B1PRESS, self.hud_drag_press)
        self.hud_back.bind(DGG.B1RELEASE, self.hud_drag_release)
        label(self.hud_node, f"ROBOT LAB  -  {'TEACHER: ' if TEACHER else ''}{name}", -1.72, 0.91, 0.045,
              BLUE if TEACHER else YELLOW)
        settings = load_json(os.path.join(SETTINGS_DIR, "settings.json"))
        self.hud_small = bool(settings.get("hud_small"))
        self.hud_button = button(self.hud_node, "Hide", -0.925, 0.918, self.toggle_hud, None, 0.028)
        self.hud_rows = self.hud_node.attachNewNode("health bars")
        self.hud_drag = None
        self.set_hud_at(getattr(self, "saved_hud_at", None) or settings.get("hud_at"))
        self.hud_used = None
        self.rows = []
        for i in range(10):  # up to 6 robots and 4 Resident Robots
            y = 0.845 - i * 0.068
            rn = self.hud_rows.attachNewNode(f"row{i}")
            t = label(rn, "", -1.72, y, 0.03)
            DirectFrame(parent=rn, frameColor=(0.2, 0.2, 0.22, 1), frameSize=(0, 0.3, 0, 0.018), pos=(-1.2, 0, y - 0.005))
            bar = DirectFrame(parent=rn, frameColor=WHITE, frameSize=(0, 0.3, 0, 0.018), pos=(-1.2, 0, y - 0.005))
            info = label(rn, "", -1.72, y - 0.032, 0.024, GREY)
            parts = self.hud_parts(rn, y - 0.032)
            rn.hide()
            self.rows.append((rn, t, bar, info, parts))
        self.layout_hud(0)
        DirectFrame(frameColor=PANEL, frameSize=(-0.34, 0.34, 0.87, 0.97))
        self.mode_text = label(self.aspect2d, "", 0, 0.905, 0.04, WHITE, TextNode.ACenter)
        self.status_text = label(self.aspect2d, "", 0, 0.83, 0.03, GREY, TextNode.ACenter)
        self.feed = label(self.aspect2d, "", -1.72, -0.7, 0.036, YELLOW)
        self.banner = OnscreenText("", pos=(-0.3, 0.1), scale=0.08, fg=YELLOW, shadow=(0, 0, 0, 1), mayChange=True)
        self.intro_big = OnscreenText("", pos=(-0.3, 0.2), scale=0.16, fg=YELLOW, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.intro_small = OnscreenText("", pos=(-0.3, 0.05), scale=0.06, fg=WHITE, shadow=(0, 0, 0, 0.9),
                                        mayChange=True)
        gap = "    "  # the key list: two lines of big letters (Space fires a weapon, or switches a spinner on/off)
        keys = (gap.join(["Arrows drive", "Space weapon", "I HUD", "C code"] +
                         ([] if TEACHER else ["U upload brain", "P autopilot"])) + "\n" +
                gap.join(["V view", "O full arena", "[ ] arena", "wheel or +/- zoom", "B bars", "N sound", "H hide keys"]))
        self.view_text = label(self.aspect2d, "", 0, 0.795, 0.026, GREY, TextNode.ACenter)
        self.help = OnscreenText(keys, pos=(-0.45, -0.905), scale=0.042 * min(1.15, self.text_scale()), fg=WHITE,
                                 shadow=(0, 0, 0, 0.9), align=TextNode.ACenter, parent=self.aspect2d, mayChange=True)
        self.panel_floor = -0.86  # (the side panel stops above the key list: CHANGE 104)

    def set_hud_at(self, at):
        """Where the health bars panel was dragged to (its offset from the top left corner)."""
        try:
            x, y = float(at[0]), float(at[1])
        except (TypeError, ValueError, IndexError):
            x, y = 0.0, 0.0
        wide = self.getAspectRatio()
        x = max(0.0, min(wide + 1.76 - 0.9, x))   # (never off the screen: its left edge is at -1.76)
        y = max(-1.33, min(0.0, y))
        self.hud_node.setPos(x, 0, y)
        self.hud_at = (x, y)

    def hud_drag_press(self, event=None):
        at = self.mouse_at()
        if at is not None:
            self.hud_drag = (at, self.hud_at)
            self.taskMgr.add(self.hud_drag_task, "hud drag")

    def hud_drag_task(self, task):
        at = self.mouse_at()
        if self.hud_drag is None or at is None:
            return task.cont
        (mx, my), (x0, y0) = self.hud_drag
        self.set_hud_at((x0 + at[0] - mx, y0 + at[1] - my))
        return task.cont

    def hud_drag_release(self, event=None):
        if self.hud_drag is not None:
            self.hud_drag = None
            self.taskMgr.remove("hud drag")
            remember("hud_at", [round(v, 3) for v in self.hud_at])
            self.prefs_at = 0.0  # (sent with the learner's settings)

    def hud_parts(self, row, y):
        """Real damage: small bars for a robot's armour, weapon and four wheels (hidden until it's switched on)."""
        root = row.attachNewNode("parts")
        fills = []
        for text, x in (("Armour", -1.72), ("Weapon", -1.48), ("Wheels", -1.24)):
            label(root, text, x, y, 0.022, GREY)
        for k, (x, width) in enumerate([(-1.63, 0.13), (-1.39, 0.13)] + [(-1.15 + j * 0.066, 0.058) for j in range(4)]):
            DirectFrame(parent=root, frameColor=(0.2, 0.2, 0.22, 1), frameSize=(0, width, 0, 0.014), pos=(x, 0, y - 0.002))
            fills.append((DirectFrame(parent=root, frameColor=WHITE, frameSize=(0, width, 0, 0.014), pos=(x, 0, y - 0.002)),
                          width))
        root.hide()
        return root, fills

    def toggle_hud(self):
        """Make the health bars small (just the title) or full size. B does the same."""
        self.hud_small = not self.hud_small
        remember("hud_small", self.hud_small)
        self.layout_hud(self.hud_used or 0)

    def layout_hud(self, used):
        self.hud_used = used
        if self.hud_small:
            self.hud_rows.hide()
            self.hud_back["frameSize"] = (-1.76, -0.86, 0.875, 0.97)
        else:
            self.hud_rows.show()
            self.hud_back["frameSize"] = (-1.76, -0.86, min(0.8, 0.845 - (max(1, used) - 1) * 0.068 - 0.055), 0.97)
        self.hud_button["text"] = "Show" if self.hud_small else "Hide"

    def hud_row(self, row, s, house, real):
        """One robot's line in the health bars: its health, and with real damage each part's health."""
        rn, t, bar, info, (parts, fills) = row
        rn.show()
        nm, owner, colour = self.names.get(s["id"], ("?", "?", (1, 1, 1)))
        you = "  (YOU)" if s["id"] == self.my_id else ""
        t.setText(f"{nm}  -  {'Resident Robot' if house else owner}{you}")
        t.setFg(DARK["ORANGE"] if house else DARK["YELLOW"] if you else DARK["WHITE"])  # (the HUD is always dark)
        bar["frameColor"] = (*colour, 1)
        bar["frameSize"] = (0, 0.3 * max(0, s["hp"]) / max(1, s["max"]), 0, 0.018)
        if real and not s["ko"] and "pt" in s:
            info.setText("")
            parts.show()
            pt = s["pt"]  # (armour, weapon, then the wheels left to right: front left, front right, back left, back right)
            for (fill, width), v in zip(fills, [pt[1], pt[2], pt[4], pt[3], pt[6], pt[5]]):
                fill["frameSize"] = (0, max(0.001, width * v / 100), 0, 0.014)
                fill["frameColor"] = (0.3, 0.85, 0.35, 1) if v > 60 else (1, 0.8, 0.15, 1) if v > 30 else (1, 0.25, 0.2, 1)
            return
        parts.hide()
        if self.weapons.get(s["id"]) in sim.TOGGLE_WEAPONS:  # switched on and off with Space (it starts off)
            weapon = f"{s['rpm']} rpm, {s['energy']} J" if s["on"] and s["rpm"] else ("on" if s["on"] else "off")
        else:  # fired with Space
            weapon = "firing" if s["on"] else "ready"
        info.setText(("OUT OF ACTION" if house else "KNOCKED OUT") if s["ko"] else
                     f"{'Body' if real else 'Armour'} {s['hp']:.0f}/{s['max']}   weapon {weapon}   hits {s['hits']}")

    def toggle_mute(self):
        self.muted = not self.muted
        self.banner_note("Sound off on this computer (N)" if self.muted else "Sound on (N)", 2)

    def check_code(self, welcome):
        """The server runs the game's current code: if this window's code is different (a mod was switched, or
        the server restarted with changes), reopen with the new code. Returns True if the window is reopening."""
        if not welcome.get("code") or welcome["code"] == lab_version.CODE:
            return False
        if not lab_version.FROZEN and not LOCAL:  # the teacher's own windows on the class server run the teacher's code
            return False
        if os.environ.get("ROBOTLAB_REOPENED") == welcome["code"] or args.offscreen:  # tried already: don't loop
            self.banner_note("This window's game code doesn't match the server's. Restart the server "
                             "(teacher: Controls), then reopen this window.", 3600)
            return False
        self.restart_window(reopen_for=welcome["code"])
        return True

    def restart_window(self, reopen_for=None, argv=None, try_env=None):
        """Reopen this window (to load code changes), logged in as the same person.
        argv: open it with these arguments instead (Try it on this laptop, and Back to the class). try_env: what a
        window on the laptop's test server needs to know (see try_local); left out, a try stays a try."""
        env = dict(os.environ, ROBOTLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        if reopen_for:  # remember which server code this reopen was for, so it only happens once
            env["ROBOTLAB_REOPENED"] = reopen_for
        else:
            env.pop("ROBOTLAB_REOPENED", None)
        if try_env is None and TRY and argv is None:
            try_env = json.dumps(TRY)
        if try_env:
            env["ROBOTLAB_TRY"] = try_env
        else:
            env.pop("ROBOTLAB_TRY", None)
        argv = [a for a in (sys.argv[1:] if argv is None else argv)]
        for flag in ("--name", "--password"):  # the login travels in ROBOTLAB_LOGIN instead
            while flag in argv:
                i = argv.index(flag)
                del argv[i:i + 2]
        if TEACHER:
            argv += ["--name", name]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        program = [sys.executable] if lab_version.FROZEN else [sys.executable, os.path.abspath(__file__)]
        log_dir = SETTINGS_DIR if lab_version.FROZEN else HERE
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "window.log"), "a") as log:
            subprocess.Popen(program + argv, cwd=os.getcwd() if lab_version.FROZEN else HERE, env=env,
                             stdout=log, stderr=log, creationflags=flags)
        os._exit(0)

    def toggle_help(self):
        self.help.hide() if not self.help.isHidden() else self.help.show()
        self.panel_floor = -1.0 if self.help.isHidden() else -0.86  # (CHANGE 104: the panel stops above the keys)
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
        """Redraw the side panels. A redraw caused by the game (a new round, a life lost, new mission results)
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
            f, y0 = self.draw_header(f, tabs, self.open_tab, self.tab, self.tab_text)
            builders = {"garage": self.build_garage, "teacher": self.build_teacher_panel, "missions": self.build_missions,
                        "ai": self.build_ai_card, "outcomes": self.build_outcomes, "cards": self.build_cards,
                        "card": self.build_card, "mods": self.build_mods,
                        "learners": self.build_learner_view, "changes": self.build_changes,
                        "accounts": self.build_accounts, "limits": self.build_limits,
                        "warnings": self.build_warnings, "settings": self.build_settings}
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



    # ---------- settings: text size and the dark or light look (CHANGE 40 and 57) ----------











    def tab_text(self, key, text):
        """A tab's name (some say how much is waiting in them)."""
        if key == "warnings":
            return self.warnings_tab_text(text)
        return text

    # ---------- teacher: warnings (a learner changed, in the code, something the lesson's garage hides) ----------


    # ---------- which robot the garage and code panel are editing ----------
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

    def limits(self):
        """The ranges the design being edited is held to: the learners' (the teacher sets them in the Limits tab),
        or the widest ones for the teacher's own robot."""
        if TEACHER and not self.viewing():
            return self.rules.get("full") or sim.full_limits()
        return self.lesson.get("limits") or sim.default_limits()

    def tools(self):
        if TEACHER:
            return {k: True for k in self.lesson["tools"]} | {"weapons": list(self.rules["weapons"])}
        return self.lesson["tools"]

    # ---------- garage: design your robot ----------
    # ---------- the robot preview (CHANGE 82) ----------
    PREVIEW_Z = -300.0  # the preview robot lives far below the arena, inside the lit scene

    def preview_setup(self):
        """A second camera drawing into a small texture; made once, switched on while the garage shows."""
        self.preview_buffer = self.preview_cam = self.preview_root = self.preview_vis = None
        self.preview_key, self.preview_image = None, None
        try:
            buf = self.win.makeTextureBuffer("robot preview", 256, 256)
            buf.setClearColor((0.07, 0.08, 0.11, 1))
            cam = self.makeCamera(buf)
            cam.reparentTo(self.render)
            cam.node().getLens().setFov(38)
            cam.node().getLens().setNearFar(0.3, 40.0)
            cam.setPos(0, -3.0, self.PREVIEW_Z + 1.5)
            cam.lookAt(0, 0, self.PREVIEW_Z + 0.3)
            root = self.render.attachNewNode("robot preview")
            root.setPos(0, 0, self.PREVIEW_Z)
            buf.setActive(False)
            self.preview_buffer, self.preview_cam, self.preview_root = buf, cam, root
            self.taskMgr.add(self.preview_turn, "robot preview turn")
        except Exception:  # (a window with no offscreen buffers: no preview, the garage is as it was)
            self.preview_buffer = None

    def preview_show(self, f, y, design):
        """The preview beside the garage's title: the robot built again only when the design has changed."""
        if self.preview_buffer is None:
            return
        key = json.dumps(design, sort_keys=True)
        if key != self.preview_key:
            if self.preview_vis is not None:
                self.preview_vis.destroy()
            try:
                self.preview_vis = RobotVisual(self.preview_root, design)
                self.preview_key = key
            except Exception:
                self.preview_vis, self.preview_key = None, None
        self.preview_buffer.setActive(True)
        self.preview_image = OnscreenImage(image=self.preview_buffer.getTexture(), parent=f, pos=(1.64, 0, y - 0.015),
                                           scale=0.1)
        self.preview_image.setTransparency(TransparencyAttrib.MAlpha)

    def preview_turn(self, task):
        """Turns slowly while it shows; the camera rests when the garage is closed."""
        showing = self.preview_image is not None and not self.preview_image.isEmpty() and self.tab in ("garage", "learners")
        if self.preview_buffer is not None:
            self.preview_buffer.setActive(bool(showing))
            if showing:
                self.preview_root.setH((self.preview_root.getH() + 25 * self.clock.getDt()) % 360)
        return task.cont

    def build_garage(self, f, y, view=None):
        """view: the teacher's Learner view of this learner. The teacher sees every control, with a tick box
        on each showing (and setting) whether the learner can see and change it. The tables are the engine's,
        from the robot's schema (CHANGE 46 to 48)."""
        tools, d = self.tools(), self.cur()
        seen = self.lesson["tools"]

        def shown_box(tool, yy):
            if view:
                check(f, " learner sees", 1.52, yy, seen.get(tool), lambda v, t=tool: self.set_lesson({"tools": {t: bool(v)}}),
                      0.022)
        self.preview_show(f, y, d)  # (CHANGE 82: the robot as it is being built, turning, top right)
        label(f, ("EVERY LEARNER'S ROBOT (what they all get)" if view == self.ALL_LEARNERS else
               f"{view.upper()}'S ROBOT (what they see and change)") if view else
              ("MY ROBOT" if TEACHER else "GARAGE  -  your robot as variables"), 0.82, y, 0.034 if view else 0.038,
              YELLOW)
        y -= 0.06
        model = d.get("model")
        limits = self.limits()
        y = garage.draw(self, f, y, d, self.schema, self.code_ctx(), tools, limits, view, shown_box,
                        teacher=TEACHER and not view)

        self.stats_text = None
        if tools.get("stats_readout") and not model:
            self.stats_text = label(f, "", 0.82, y - 0.01, 0.026, GREEN)
            self.update_stats_text()
            shown_box("stats_readout", y)
            y -= 0.205
        if view != self.CPU_VIEW:
            y = self.build_slots(f, y, view)  # (CHANGE 83 to 87)
        self.garage_bottom = y - 0.1  # (where the Learner view puts the computer robot's Reset button)
        if view:
            button(f, f"REBUILD FOR {view.upper()}", 1.27, y, self.send_design_for, [view], 0.036,
                   (0.15, 0.55, 0.25, 1))
        else:
            button(f, "REBUILD MY ROBOT", 1.27, y, self.send_design, None, 0.04, (0.15, 0.55, 0.25, 1))
        self.garage_msg = label(f, self.status_msg[0] if not view else "", 0.82, y - 0.065, 0.026, self.status_msg[1],
                                wrap=36)
        if self.lesson["designs_locked"] and not TEACHER:
            label(f, "Designs are locked by the teacher", 0.82, y - 0.14, 0.028, RED)

    def name_key(self):
        """The robot-name box: one for your robot, one for each learner in the Learner view."""
        return "name_" + (self.viewing() or "me")

    def update_stats_text(self):
        if not getattr(self, "stats_text", None):
            return
        try:
            st = sim.build_stats(self.cur())
        except Exception:
            return
        self.stats_text.setText(
            f"Top speed {st['forward_max'] * 3.6:.0f} km/h forward, {st['reverse_max'] * 3.6:.0f} reverse\n"
            f"0-3 m/s in {3 / st['accel']:.1f} s    Turn {st['turn_rate'] * 57.3:.0f} deg/s\n"
            f"Armour {st['armour']:.0f}    Mass {st['mass']:.0f} kg    Weapon power x{st['power']:.2f}\n"
            f"Self-rights after {st['self_right']:.1f} s    Grip {st['grip']:.2f}\n"
            f"Pushes with {st['push']:.0f} N    Holds against {st['hold']:.0f} N" +
            (f"\nFlipper strength {st['flip_strength'] * 100:.0f}%  (100% flips Resident Robots)"
             if self.cur().get("weapon") == "wedge" else ""))

    def set_colour(self, colour):
        self.cur()["colour"] = colour
        self.code_shown = None
        self.rebuild_panels()

    def set_model(self, model):
        d = self.cur()
        if model:
            d["model"], d["weapon"] = model, self.rules["house"][model]
        else:
            d.pop("model", None)
            if d["weapon"] not in self.rules["weapons"]:
                d["weapon"] = "wedge"
        self.code_shown = None
        self.rebuild_panels()

    def set_weapon(self, w):
        self.cur()["weapon"] = w
        self.code_shown = None
        self.rebuild_panels()

    def change_points(self, stat, delta):
        d = self.cur()
        lo, hi = self.limits()["points"][stat]
        d["points"][stat] = max(lo, min(hi, d["points"][stat] + delta))
        self.code_shown = None
        self.rebuild_panels()

    def slider_moved(self, k):
        s, text = self.sliders[k]
        lo, hi = self.limits()["settings"][k]
        v = max(lo, min(hi, int(round(s["value"]))))  # (whole numbers, but never outside the range: size starts at 12.5)
        self.cur()["settings"][k] = v
        text.setText(f"{v:g}%")
        self.update_stats_text()
        if self.code_panel is not None:  # just the code panel: redrawing the garage would drop the slider
            self.refresh_code_panel()

    def send_design(self, from_code=False):
        if "name_me" in self.entries and self.tools().get("name_and_colour"):
            self.draft["name"] = self.entries["name_me"].get()[:16]
        # (code: the design holds something changed in the code panel, where every value can be changed)
        send({"type": "design", "design": self.draft, "code": bool(from_code or self.code_hack or self.code_changed)})
        self.status_msg = ("Building...", GREY)
        self.code_building = from_code  # (the code panel then says how the build went)
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
        if self.tab == "learners":
            self.garage_msg.setText(f"Building for {learner}...")

    # ---------- code view: your robot as Python code, which you can edit ----------
    def code_weapons(self):
        """The weapons the code may choose from: the lesson's (the teacher: every weapon)."""
        return list(self.tools().get("weapons") or self.rules["weapons"])

    def code_ctx(self):
        """What the schema needs to know from this window: the mission's weapons, the Resident Robots, the limits."""
        from types import SimpleNamespace
        who = self.viewing()
        return SimpleNamespace(title=f"{who.upper()}'S ROBOT" if who else "MY ROBOT",
                               points_total=self.limits()["points_total"], weapons=self.code_weapons(),
                               all_weapons=list(self.rules["weapons"]), house=self.rules.get("house", {}),
                               rules=self.rules)

    def code_lines(self, d):
        """The robot as Python: one variable a line, with its type and a comment, in the garage's groups (the
        engine writes it from the schema: CHANGE 49)."""
        return schema.code_lines(self.schema, d, self.code_ctx())

    def build_code_panel(self):
        """The robot as Python code, in a small editor (lab_editor): click anywhere in it to type there, the words
        are coloured as an IDE colours them, and long code scrolls while the buttons under it stay where they are."""
        who = self.viewing()
        d = self.cur()
        self.code_size = self.code_fit(*self.code_size)
        self.code_at = self.code_place(*self.code_at)
        left, right, bottom, top = rect = self.code_rect()
        f = self.code_panel = DirectFrame(frameColor=PANEL, frameSize=rect, pos=(self.code_at[0], 0, self.code_at[1]))
        # its top is a handle: drag it to move the panel anywhere on the screen (a drag in the code places the cursor)
        handle = DirectFrame(parent=f, frameColor=HANDLE, state=DGG.NORMAL,
                             frameSize=(left, right, 0.285, top))
        handle.bind(DGG.B1PRESS, self.code_drag_start)
        label(f, f"{who.upper()}'S ROBOT AS PYTHON CODE" if who else "YOUR ROBOT AS PYTHON CODE", -0.83, 0.3, 0.032,
              YELLOW)
        label(f, "drag here to move", right - 0.02, 0.337, 0.017, GREY, TextNode.ARight)
        label(f, "Click in the code to type there (drag to select; Ctrl+C, X, V and A work). Change a value,\n"
                 "then press APPLY CODE: the garage changes to match. Return makes a new line.", -0.83, 0.264, 0.021, GREY)
        st, fresh = self.code_state, self.code_lines(d)
        if self.code_shown is None or st["lines"] == self.code_shown:  # not edited: the robot as it is now
            st["lines"][:] = fresh
            self.code_shown = list(fresh)
        self.code_editor = lab_editor.CodeEditor(self, f, st, -0.845, 0.21, right - left - 0.03, self.code_rows(),
                                                 0.024 * self.text_scale(), on_enter=self.apply_code,
                                                 on_focus=self.type_code)
        self.code_more = label(f, "", right - 0.02, 0.243, 0.019, GREY, TextNode.ARight)  # (beside the second line above)
        self.code_editor.on_scroll = self.show_code_more
        self.show_code_more()
        button(f, "APPLY CODE", -0.64, bottom + 0.178, self.apply_code, None, 0.03, (0.15, 0.55, 0.25, 1))  # (always here)
        button(f, "RESET CODE", -0.36, bottom + 0.178, self.reset_code, None, 0.03)
        if TEACHER and not who:  # (CHANGE 90: this code becomes every learner's starting robot for the mission)
            button(f, "SAVE CODE FOR LEARNERS", -0.08, bottom + 0.178, self.save_code_for_learners, None, 0.024,
                   (0.15, 0.45, 0.65, 1))
            if self.lesson.get("start_design"):
                button(f, "standard again", 0.26, bottom + 0.178, self.set_lesson, [{"start_design": None}], 0.019)
        button(f, f"REBUILD FOR {who.upper()}" if who else "REBUILD MY ROBOT", -0.64 if not who else -0.5, bottom + 0.112,
               self.rebuild_from_code, None, 0.03, (0.15, 0.55, 0.25, 1))  # (under APPLY CODE: apply, then build)
        label(f, self.code_msg[0], -0.83, bottom + 0.055, 0.021, self.code_msg[1], wrap=39 + self.code_size[0] / 0.021)
        # its bottom right corner is a grip: drag it to make the panel bigger or smaller (CHANGE 60)
        grip = DirectFrame(parent=f, frameColor=(0.35, 0.4, 0.5, 1), state=DGG.NORMAL,
                           frameSize=(right - 0.045, right, bottom, bottom + 0.045))
        grip.bind(DGG.B1PRESS, self.code_resize_start)
        label(f, "drag to resize", right - 0.055, bottom + 0.012, 0.015, GREY, TextNode.ARight)

    def show_code_more(self):
        """Under the code: how much of it is out of sight (it scrolls with the mouse wheel or the cursor)."""
        above, below = self.code_editor.hidden()
        self.code_more.setText("" if not (above or below) else
                               f"{above} lines above, {below} below")

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

    def default_design(self, who=None):
        """The lesson's starting robot: your own, or (teacher's Learner view) that learner's. The teacher's saved
        starting robot for the mission (CHANGE 90) comes first, with the learner's own name and colour."""
        start = self.lesson.get("start_design")
        if who:
            mine = next((c.get("default") for c in self.class_list if c["name"] == who), None) or self.cur()
        else:
            mine = self.default or self.draft
        if isinstance(start, dict) and not TEACHER or (who and isinstance(start, dict)):
            d = copy.deepcopy(start)
            d["name"], d["colour"] = mine.get("name", name), mine.get("colour", d.get("colour"))
            return d
        return mine

    def save_code_for_learners(self):
        """CHANGE 90: the code on screen is applied, then kept as the mission's starting robot for every learner."""
        if not self.apply_code():
            return
        self.set_lesson({"start_design": self.cur()})
        self.code_msg = ("Saved for learners: this is their starting robot for the mission.", GREEN)
        self.refresh_code_panel()

    def reset_code(self):
        """RESET CODE: the code goes back to the lesson's starting robot. Only the code on screen changes: the
        robot changes when the code is applied or the robot is rebuilt."""
        self.code_state["lines"][:] = self.code_lines(self.default_design(self.viewing()))
        self.code_state["cursor"][:], self.code_state["scroll"] = [0, 0], 0
        self.code_msg = ("The code is back to the starting robot. Press APPLY CODE or REBUILD to use it.", GREY)
        self.refresh_code_panel()

    def rebuild_from_code(self):
        """REBUILD MY ROBOT in the code panel: read the code as APPLY CODE does, then build the robot from it.
        A mistake in the code is shown, and nothing is built."""
        if not self.apply_code():
            return
        who = self.viewing()
        if who:
            self.send_design_for(who)
        else:
            self.code_msg = ("Building...", GREY)
            self.send_design(from_code=True)
            self.refresh_code_panel()

    def outside_limits(self, values):
        """CHANGE 91: the code may set what the garage hides, but every value stays within the teacher's limits
        (the Limits tab). Each one past its range is named; the points total is not checked here (Mission 2 b
        asks learners to try to spend more than it: the server pulls it back)."""
        limits, out = self.limits(), []
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
        Everything in the code can be changed, even what this lesson's garage hides (hidden: those values). The
        class server holds the robot to the limits all the same, and tells the teacher what was changed."""
        text = "\n".join(self.code_state["lines"])
        ctx = self.code_ctx()
        try:
            values = schema.parse_code(text, self.schema, ctx)
        except schema.ParseError as e:
            self.code_msg = (f"Line {e.lineno}: {e.message}", RED)
            if e.lineno:  # the cursor goes to the line with the mistake
                self.code_state["cursor"][:] = [e.lineno - 1, 0]
                self.code_state["scroll"] = max(0, e.lineno - self.code_rows())
            self.refresh_code_panel()
            return
        if "ROBOT" in values:
            self.code_msg = ("The code is now one variable a line: press RESET CODE to see it.", RED)
            self.refresh_code_panel()
            return
        d, tools = self.cur(), self.tools()

        def allowed(var, value):  # (what this mission's garage lets the learner change)
            if var.name == "weapon":
                return bool(tools.get("choose_weapon")) and value in tools.get("weapons", [])
            return bool(tools.get(var.tool, True))
        refused = self.outside_limits(values)  # (CHANGE 91: a value past the teacher's limits is refused outright)
        if refused:
            self.code_msg = ("Unable to compile: " + "; ".join(refused[:2]), RED)
            self.code_shown = None
            self.rebuild_panels()
            return False
        changed, hidden, problems = schema.apply_values(self.schema, d, values, ctx, allowed)
        if "robot_name" in changed:
            self.entry_text.pop(self.name_key(), None)
            if self.name_key() in self.entries:  # (the garage's box is open: it takes the new name, or the redraw
                self.entries[self.name_key()].enterText(d["name"])  # would keep what the box held)
        if "colour" in changed and list(d["colour"]) not in [list(c) for c in SWATCHES]:
            self.custom_colour = list(d["colour"])  # (the garage's custom block takes it)
        if changed and not self.viewing():
            self.code_changed = True  # (the next build is sent as the code's: Mission 1, hack the code)
        if hidden and not self.viewing():
            self.code_hack = True  # (so the next build, from here or the garage, is sent as the code's)
        problems += sim.check_design(d, self.limits())
        if problems:
            self.code_msg = ("Applied, but: " + "; ".join(problems[:3]), ORANGE)
        else:
            self.code_msg = ("Applied: the garage shows your changes. Press REBUILD MY ROBOT to use them.", GREEN)
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

    def banner_note(self, text, secs=3, big=False):
        """Words over the arena for a few seconds. big: the size of a battle's banner (a restart warning)."""
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
        for i, (key, text) in enumerate(lm.AI_TARGETS.items()):
            if key == "game":
                continue
            button(f, text, 1.19 + i * 0.2, y + 0.008, self.set_card_target, [key], 0.025,
                   ON if key == self.card_target else OFF)
        y -= 0.07
        for key, text in (("goal", "My idea"), ("variables", "Variables and values it needs"),
                          ("test", "How I will test it"), ("predict", "What I predict will happen")):
            rows = IDEA_ROWS if key in ("goal", "test") else CARD_ROWS  # (room to explain: CHANGE 93)
            label(f, text, 0.82, y, 0.027)
            if edit:  # (the teacher's copy: the boxes are only drawn)
                DirectFrame(parent=f, frameColor=(0.15, 0.17, 0.22, 1), pos=(0.84, 0, y - 0.045),
                            frameSize=(0, 0.78, -0.009 - (rows - 1) * 0.026, 0.024))
            else:
                self.entry(f, f"card_{key}", 0.84, y - 0.045, 30, rows, scale=0.026)
            y -= 0.1 + (rows - 1) * 0.026
        for key, text in (("privacy", "No personal information (names, school, email, address)"),
                          ("review", "I will review and test the AI's code"),
                          ("credit", "I will say where AI helped")):
            check(f, text, 0.84, y, self.card_checks[key], lambda v, k=key: self.card_checks.__setitem__(k, bool(v)), 0.026)
            y -= 0.045
        if edit:
            return
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

    def send_card_note(self):
        """Teacher: what is typed in "From your teacher" goes on every learner's card (and stays for next time)."""
        note = " ".join(self.entries["card_note"].get().split())[:300] if "card_note" in self.entries else ""
        self.entry_text.pop("card_note", None)
        self.stop_typing()
        self.set_lesson({"ai_card_note": note})
        self.note_text.setText("Sent: it is on the learners' cards." if note else "Sent: nothing from you is on their cards.")

    def show_cards(self, view):
        """Teacher's AI cards tab: the list of requests (None), the learners' card ("edit"), or one card with its
        whole prompt before it is sent (the card's number)."""
        self.cards_view = view
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
        label(f, "Mission", 0.82, y, 0.032, YELLOW)
        for n in range(1, 6):
            button(f, str(n), 1.0 + (n - 1) * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.03,
                   ON if L.get("lesson_number") == n else OFF)
        saved = (L.get("saved_missions") or [])  # (CHANGE 58 and 59: saved per mission, and brought back)
        button(f, "Save settings", 1.5, y + 0.008, send, [{"type": "save_lesson"}], 0.026)
        button(f, "Restore", 1.68, y + 0.008, send, [{"type": "restore_lesson"}], 0.026)
        if saved:  # (Save keeps every control for the mission, used whenever it is chosen; Restore brings it back)
            label(f, "saved settings: mission " + ", ".join(str(n) for n in saved), 1.74, y - 0.037, 0.015, GREY,
                  TextNode.ARight)
        y -= 0.065
        y = self.restart_row(f, y)  # (near the top, so Restart server is always in reach: asked for 6 October)
        y -= 0.065
        label(f, "Match", 0.82, y, 0.03, YELLOW)
        for i, mode in enumerate(("practice", "battle")):
            button(f, mode.title(), 1.04 + i * 0.19, y + 0.008, self.set_lesson, [{"mode": mode}], 0.03,
                   ON if L["mode"] == mode else OFF)
        button(f, "Restart", 1.44, y + 0.008, send, [{"type": "restart"}], 0.03)
        button(f, "Pause", 1.63, y + 0.008, send, [{"type": "pause"}], 0.03,
               ON if (self.state or {}).get("paused") else OFF)  # (CHANGE 102: lit while paused)
        y -= 0.06
        label(f, f"Battle {L['time_limit']} s", 0.82, y, 0.028)
        button(f, "-30", 1.08, y + 0.008, self.set_lesson, [{"time_limit": L["time_limit"] - 30}], 0.026)
        button(f, "+30", 1.18, y + 0.008, self.set_lesson, [{"time_limit": L["time_limit"] + 30}], 0.026)
        label(f, f"Computer robots {L['cpu_robots']}", 1.28, y, 0.028)
        button(f, "-", 1.6, y + 0.008, self.set_lesson, [{"cpu_robots": L["cpu_robots"] - 1}], 0.026)
        button(f, "+", 1.67, y + 0.008, self.set_lesson, [{"cpu_robots": L["cpu_robots"] + 1}], 0.026)
        y -= 0.05
        level = L.get("cpu_level", cpu_brains.START_LEVEL)  # (every game starts at No brain: they sit still)
        label(f, "Computer brains", 0.84, y, 0.026)
        for i, (key, text) in enumerate(cpu_brains.LEVELS.items()):
            button(f, text, 1.11 + i * 0.112, y + 0.008, self.set_lesson, [{"cpu_level": key}], 0.022,
                   ON if level == key else OFF)
        if level == "empty":
            button(f, "Upload demo", 1.685, y + 0.008, self.upload_demo_brain, None, 0.019, (0.15, 0.45, 0.65, 1))
        y -= 0.055
        check(f, "My robot in the arena", 0.84, y, L["teacher_robot"], lambda v: self.set_lesson({"teacher_robot": bool(v)}),
              0.028)
        check(f, "Lock designs", 1.24, y, L["designs_locked"], lambda v: self.set_lesson({"designs_locked": bool(v)}), 0.028)
        check(f, "Real damage", 1.5, y, L.get("real_damage"), lambda v: self.set_lesson({"real_damage": bool(v)}), 0.028)
        y -= 0.07
        y = self.arenas_section(f, y)
        y = self.tournament_section(f, y)
        label(f, "Arena  (on = working, off = resting flush and safe)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        hazards = [h for h in HAZARD_NAMES if h != "house_robots"]
        asked = self.mod_info.get("arena_votes", {})  # learners' votes (who voted is on the User mods tab)
        for i, hz in enumerate(hazards):
            check(f, HAZARD_NAMES[hz] + self.votes_text(asked.get(hz), "  ({})"), 0.84 + (i % 2) * 0.46,
                  y - (i // 2) * 0.046, L["hazards"].get(hz), lambda v, hz=hz: self.set_lesson({"hazards": {hz: bool(v)}}))
        y -= 0.046 * ((len(hazards) + 1) // 2)
        on = sim.house_list(L["hazards"].get("house_robots"))
        label(f, "Resident Robots", 0.84, y, 0.028)
        for i, (hr, w) in enumerate(self.rules.get("house", {}).items()):
            check(f, "  " + hr + (f" ({len(asked[hr])})" if asked.get(hr) else ""), 1.08 + i * 0.17, y + 0.005, hr in on,
                  lambda v, hr=hr: self.toggle_house(hr, bool(v)), 0.024)
        y -= 0.06
        label(f, "User mods  (on or off at any time.  Green: made by this group)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        mods_on, votes = L.get("user_mods", {}), self.mod_info.get("votes", {})
        order = self.mod_order()
        shown = order[:6]  # this group's own mods come first; every mod is on the User mods tab
        for i, (key, lit) in enumerate(shown):
            check(f, " " + self.mod_title(key) + self.votes_text(votes.get(key), "  ({})"), 0.84 + (i % 2) * 0.46,
                  y - (i // 2) * 0.046, mods_on.get(key), lambda v, k=key: self.set_lesson({"user_mods": {k: bool(v)}}),
                  0.024, GREEN if lit else WHITE)
        y -= 0.046 * ((len(shown) + 1) // 2)
        if len(order) > len(shown):
            label(f, f"and {len(order) - len(shown)} more on the User mods tab", 0.84, y, 0.022, GREY)
            y -= 0.036
        if mods_on.get("flame_pit"):  # the Flame pit user mod: how high its flames stand with nobody in
            cm = L.get("flame_pit_cm", sim.FLAME_PIT_CM)
            label(f, f"Flame pit: baseline flame height {cm} cm", 0.84, y, 0.026)
            button(f, "-10", 1.42, y + 0.008, self.set_lesson, [{"flame_pit_cm": cm - 10}], 0.022)
            button(f, "+10", 1.5, y + 0.008, self.set_lesson, [{"flame_pit_cm": cm + 10}], 0.022)
            y -= 0.046
        y -= 0.02
        label(f, "Learners can see and change  (or use the Learners tab)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        keys = ["points_table", "forward_speed", "reverse_speed", "turn_speed", "acceleration", "size",
                "name_and_colour", "choose_weapon", "code_view", "stats_readout", "weapon_toggle", "house_robots",
                "brains"]
        for i, k in enumerate(keys):
            check(f, PRETTY[k], 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.046, L["tools"].get(k, k == "brains"),
                  lambda v, k=k: self.set_lesson({"tools": {k: bool(v)}}))
        y -= 0.046 * ((len(keys) + 1) // 2) + 0.02
        label(f, "Weapons allowed", 0.82, y, 0.028)
        for i, w in enumerate(self.rules["weapons"]):
            button(f, w, 1.1 + i * 0.165, y + 0.008, self.toggle_weapon_allowed, [w], 0.026,
                   ON if w in L["tools"]["weapons"] else OFF)

    def restart_row(self, f, y):
        """Code changes (from Claude, or rolled back) load when the server and windows restart. One row, under the
        Mission row, so it is always in reach; returns the y below it."""
        label(f, "Code changes" + ("!" if self.needs_restart else ""), 0.82, y + 0.008, 0.024,
              ORANGE if self.needs_restart else YELLOW)  # (orange, and an orange button: restart to use them)
        button(f, "Restart server", 1.12, y + 0.008, self.restart_server, None, 0.024,
               (0.6, 0.35, 0.1, 1) if self.needs_restart else OFF)
        button(f, "Reopen learners' windows", 1.4, y + 0.008, send, [{"type": "restart_clients"}], 0.024)
        button(f, "Reopen mine", 1.66, y + 0.008, self.restart_window, None, 0.024)
        y -= 0.05
        if TRY:
            button(f, "Back to the class", 1.0, y + 0.008, self.back_to_class, None, 0.024, (0.15, 0.55, 0.25, 1))
            label(f, "Trying this laptop's game: the class can't see it.", 1.2, y, 0.021, ORANGE)
            y -= 0.05
        elif not lab_version.FROZEN and not LOCAL:
            button(f, "Try on this laptop", 1.0, y + 0.008, self.try_here, None, 0.024, (0.15, 0.45, 0.65, 1))
            label(f, "this window, on a test server here (the class sees nothing)", 1.19, y, 0.02, GREY)
            y -= 0.05
        return y

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
        if TRY or lab_version.FROZEN or self.try_starting is not None:
            return
        if LOCAL:
            return self.banner_note("This window is already on this laptop's test server: it has this laptop's "
                                    "game. Tick the mod in Controls.", 8)
        info, proc = try_local.start(HERE, "lab_server.py", "ROBOTLAB_DATA")
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
        """This window has just opened on the laptop's test server: the class's lesson, the teacher's own robot
        in the arena, and the new user mods switched on. A notice and a way back stay on the screen."""
        if TRY.get("lesson") in (1, 2, 3, 4, 5):
            send({"type": "lesson_number", "n": TRY["lesson"]})
        mods = {k: True for k in TRY.get("mods") or [] if k in sim.USER_MODS}
        self.set_lesson({"teacher_robot": True, **({"user_mods": mods} if mods else {})})
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

    def toggle_house(self, hr, on):
        names = sim.house_list(self.lesson["hazards"].get("house_robots"))
        names = [n for n in names if n != hr] + ([hr] if on else [])
        self.set_lesson({"hazards": {"house_robots": names}})

    def upload_demo_brain(self):
        """Send brains/demo_cpu.py to the server: computer robots set to Empty run it (for coding demos)."""
        path = os.path.join(HERE, "brains", "demo_cpu.py")
        if not os.path.exists(path):
            self.banner_note("No demo brain: make brains/demo_cpu.py first")
            return
        with open(path, encoding="utf-8") as fh:
            send({"type": "cpu_brain", "source": fh.read()})
        self.banner_note("Uploading the demo brain...")

    def volume_row(self, f, y, key, snd):
        """A volume from 0 to 10 with - and + buttons."""
        label(f, f"vol {round(snd[key] * 10)}", 1.58, y, 0.022, GREY)
        button(f, "-", 1.66, y + 0.008, self.set_sound, [{key: round(snd[key] - 0.1, 2)}], 0.022)
        button(f, "+", 1.72, y + 0.008, self.set_sound, [{key: round(snd[key] + 0.1, 2)}], 0.022)

    def my_sound(self):
        """This window's own sound settings (CHANGE 107): the teacher's on this computer, a learner's with their
        profile. (Older servers kept one set for the class in the lesson: it is the start for anyone without one.)"""
        own = getattr(self, "sound_prefs", None)
        if own is None:
            own = SETTINGS.get("sound") if TEACHER else None
        return rw_sound.sound_settings(own if own is not None else self.lesson.get("sound"))

    def set_sound(self, change):
        self.sound_prefs = rw_sound.sound_settings(self.my_sound(), change)
        remember("sound", self.sound_prefs)
        self.prefs_at = 0.0  # (a learner's goes to their profile)
        self.rebuild_panels()

    def build_settings(self, f, y):
        hud.HudKit.build_settings(self, f, y)
        y = self.body_bottom(y) - 0.07
        snd = self.my_sound()
        label(f, "Sound  (yours: each has its own volume, all kept for next time)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        label(f, "Music", 0.84, y, 0.026)
        for i, (key, text) in enumerate(rw_sound.MUSIC.items()):
            button(f, text, 1.0 + i * 0.13, y + 0.008, self.set_sound, [{"music": key}], 0.022,
                   ON if snd["music"] == key else OFF)
        self.volume_row(f, y, "music_volume", snd)
        y -= 0.046
        for key, text in (("crowd", "Crowd"), ("arena", "Arena hum"), ("weapons", "Weapons"),
                          ("motors", "Motors (the robots' drive motors)"), ("effects", "Hit sounds")):
            check(f, " " + text, 0.84, y, snd[key], lambda v, k=key: self.set_sound({k: bool(v)}), 0.026)
            self.volume_row(f, y, {"crowd": "crowd_volume", "arena": "arena_volume", "effects": "volume",
                                   "weapons": "weapons_volume", "motors": "motors_volume"}[key], snd)
            y -= 0.046

    def set_lesson(self, change):
        send({"type": "lesson", "lesson": change})

    # ---------- teacher: the limits (how extreme the learners' robots can go) ----------


    # ---------- user mods: learners' ideas in the game (the teacher switches them on, learners vote) ----------
    def pretty(self, key):
        return PRETTY.get(key, key.title())

    def stage_items(self):
        """The arena's hazards and the Resident Robots, for the Mods tab."""
        L = self.lesson
        house_on = sim.house_list(L["hazards"].get("house_robots"))
        hazards = [(hz, HAZARD_NAMES[hz], bool(L["hazards"].get(hz)),
                    lambda v, k=hz: self.set_lesson({"hazards": {k: bool(v)}}))
                   for hz in HAZARD_NAMES if hz != "house_robots"]
        residents = [(hr, f"Resident Robot {hr}", hr in house_on, lambda v, k=hr: self.toggle_house(k, bool(v)))
                     for hr in self.rules.get("house", {})]
        return hazards + residents

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

    def toggle_weapon_allowed(self, w):
        allowed = list(self.lesson["tools"]["weapons"])
        if w in allowed and len(allowed) > 1:
            allowed.remove(w)
        elif w not in allowed:
            allowed.append(w)
        self.set_lesson({"tools": {"weapons": allowed}})

    # ---------- teacher: the learner view ----------
    def arenas_section(self, f, y):
        """Controls (CHANGE 75): how many arenas (cages side by side, the same hazards and computer robots in
        each), who is in which, and which one this window watches."""
        L = self.lesson
        n = max(1, int(L.get("arenas", 1)))
        label(f, "Arenas", 0.82, y, 0.03, YELLOW)
        for i in range(1, sim.MAX_ARENAS + 1):
            button(f, str(i), 0.98 + (i - 1) * 0.075, y + 0.008, self.set_lesson, [{"arenas": i}], 0.028,
                   ON if n == i else OFF)
        label(f, "the same hazards and\ncomputer robots in each", 1.47, y + 0.012, 0.017, GREY)
        y -= 0.055
        if n > 1:
            where = {r["owner"]: r.get("arena", 0) for r in (self.full_roster or {}).get("robots", [])}
            places = L.get("places", {})
            people = [c["name"] for c in self.class_list if c["role"] == "learner"]
            if L.get("teacher_robot"):
                people.append("Teacher")
            label(f, "Who is where  (the arenas take turns unless you choose)", 0.84, y, 0.024, GREY)
            y -= 0.045
            for who in people:
                shown = "My robot" if who == "Teacher" else who
                label(f, shown, 0.84, y, 0.024)
                at = places.get(who, where.get(name if who == "Teacher" else who))
                for i in range(n):
                    button(f, str(i + 1), 1.2 + i * 0.075, y + 0.008, self.set_lesson, [{"places": {who: i}}], 0.024,
                           ON if at == i and who in places else (0.35, 0.35, 0.3, 1) if at == i else OFF)
                y -= 0.045
            if places:
                button(f, "Take turns again", 0.96, y + 0.008, self.set_lesson,
                       [{"places": {k: None for k in places}}], 0.022)
                y -= 0.045
            label(f, "Watch arena", 0.84, y, 0.024)
            for i in range(n):
                button(f, str(i + 1), 1.2 + i * 0.075, y + 0.008, self.set_watch, [i], 0.024,
                       ON if self.watched_arena() == i else OFF)
            label(f, "([ and ] in the arena)", 1.2 + n * 0.075 + 0.02, y, 0.018, GREY)
            y -= 0.06
        return y

    def tournament_section(self, f, y):
        """Controls (CHANGE 76): winner stays on. Two arenas live; the winner stays, the loser goes to the back
        of the queue and the next challenger comes in; everyone waiting watches ([ and ])."""
        t = self.tournament
        label(f, "Tournament", 0.82, y, 0.03, YELLOW)
        if t is None:
            button(f, "Winner stays on", 1.16, y + 0.008, send,
                   [{"type": "tournament", "start": True, "kind": "stays", "live": 2}], 0.026, (0.15, 0.55, 0.25, 1))
            label(f, "two arenas live; the loser queues, the next challenger\ncomes in, the rest watch. Battle on, designs locked.",
                  1.34, y + 0.012, 0.017, GREY)
            return y - 0.065
        button(f, "Stop: winner stays on", 1.12, y + 0.008, send, [{"type": "tournament", "start": False}], 0.026,
               (0.6, 0.2, 0.15, 1))
        y -= 0.05
        for i, (a, b) in enumerate(t.get("live", [])):
            label(f, f"Arena {i + 1}:  {a or '-'}  v  {b or '-'}", 0.84, y, 0.024, WHITE)
            y -= 0.04
        label(f, "Waiting:  " + (", ".join(t.get("queue", [])) or "nobody"), 0.84, y, 0.022, GREY, wrap=46)
        y -= 0.045
        label(f, f"Battles: {t.get('played', 0)}", 0.84, y, 0.022, GREY)
        y -= 0.04
        for n, w, s in t.get("table", [])[:12]:
            label(f, n, 0.88, y, 0.022, GREEN if w else WHITE)
            label(f, f"{w} win{'s' if w != 1 else ''}" + (f"   {s} in a row" if s > 1 else ""), 1.25, y, 0.022,
                  GREEN if w else GREY)
            y -= 0.036
        return y - 0.03

    def build_learner_view(self, f, y):
        # the learners who are connected, then the first computer robot: the teacher sets it up as a learner
        # sets up theirs (so the game can be tried as a learner without a second login)
        computer = next((c for c in self.class_list if c["role"] == "computer"), None)
        learners = [c["name"] for c in self.class_list if c["role"] == "learner"] + \
            ([computer["name"]] if computer else []) + [self.ALL_LEARNERS]  # (CHANGE 85)
        label(f, "LEARNER VIEW  -  see and change what a learner sees", 0.82, y, 0.03, YELLOW)
        y -= 0.06
        if not learners:
            label(f, "No learners are connected yet.", 0.82, y, 0.028, GREY)
            return
        if self.view_name not in learners:
            self.set_view(learners[0], redraw=False)
        across = max(0.16, min(0.2, 0.86 / len(learners)))
        for i, n in enumerate(learners):
            button(f, n, 0.9 + i * across, y + 0.008, self.set_view, [n], 0.028 if len(learners) < 5 else 0.022,
                   ON if n == self.view_name else OFF)
        y -= 0.065
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
        elif is_computer and self.view_tab == "mods":  # (the rest of CHANGE 23: the Mods tab as a learner sees it)
            label(f, "The Mods tab as a learner sees it (the computer's robot doesn't vote).", 0.82, y, 0.022, GREY)
            self.build_mods(f, y - 0.045, as_learner=True)
        elif self.view_tab == "garage":
            self.build_garage(f, y, view=who)
            if is_computer:
                if not computer.get("in_arena"):
                    label(f, "It isn't in the arena: Computer robots is 0 in Controls.", 0.82, self.garage_bottom + 0.05, 0.022, ORANGE)
                button(f, "RESET: THE COMPUTER'S ROBOT AS IT COMES", 1.27, self.garage_bottom, send,
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
        """Teacher: the first computer robot's own brain, uploaded and switched on as a learner does theirs."""
        label(f, "THE COMPUTER ROBOT'S BRAIN", 0.82, y, 0.03, YELLOW)
        y -= 0.055
        label(f, "A learner writes brains/my_brain.py, uploads it (U) and switches autopilot on (P).\n"
                 "Do the same for the computer's robot here. With its autopilot off it follows\n"
                 "Computer brains in Controls, like the other computer robots.", 0.82, y, 0.022, GREY)
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
        label(f, "The brain is kept for next time. Its autopilot starts off at every session, so the\n"
                 "robot is still until you switch it on. Reset (in its Garage) takes the brain away.", 0.82, y, 0.022, GREY)

    def upload_computer_brain(self):
        path = os.path.join(BRAINS, "my_brain.py")
        if not os.path.exists(path):
            self.banner_note("No brain file: make brains/my_brain.py first")
            return
        with open(path, encoding="utf-8") as fh:
            send({"type": "cpu_robot", "brain": fh.read()})
        self.banner_note("Uploading my_brain.py for the computer's robot...")

    def set_view(self, learner, redraw=True):
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
        # With the club desk (the online class): the names in this session are green and first, the names in the
        # next session (the group whose proposed time comes next) are orange and after them, then everyone else.
        # A tick lets a learner into this session or takes them out of it.
        s = self.session or {}
        here, coming = set(s.get("learners", [])), set(s.get("next", []))
        accounts = sorted(set(accounts) | set(s.get("all", [])), key=lambda n: (
            0 if n in here else 1 if n in coming else 2, n.lower()))
        label(f, f"{len(accounts)} account(s)" if accounts else "No accounts yet.", 0.82, y, 0.026, YELLOW)
        if s.get("live"):
            label(f, "in this\nsession", 1.52, y + 0.02, 0.019, GREY, TextNode.ACenter)
        y -= 0.05
        if s.get("desk"):
            words = (f"Green: in this session ({s['group']})." if s.get("live") else "No session is live.") + \
                (f"  Orange: next, {s['next_group']} ({s['next_time']})." if s.get("next_group") else "")
            label(f, words, 0.82, y, 0.021, GREY)
            y -= 0.045
        for n in accounts[:12]:
            label(f, n, 0.84, y, 0.025, GREEN if n in here else ORANGE if n in coming else WHITE)
            key = "pw_" + n
            self.entry(f, key, 1.04, y, 6, scale=0.024)
            button(f, "Set password", 1.31, y + 0.008, self.set_password, [n, key], 0.022)
            if s.get("live"):  # allowed into the game (the Learners tab shows who is in it now)
                check(f, " ", 1.51, y + 0.006, n in here,
                      lambda v, who=n: send({"type": "session_learner", "learner": who, "in": bool(v)}), 0.03)
            sure = self.delete_armed == n
            button(f, "Sure? Delete" if sure else "Delete", 1.65, y + 0.008, self.delete_account, [n], 0.022,
                   RED if sure else OFF)
            y -= 0.055
        if len(accounts) > 12:
            label(f, f"...and {len(accounts) - 12} more", 0.84, y, 0.022, GREY)
        label(f, "Delete removes their profile, robot, brain, evidence and AI cards from the server.",
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
            self.newer = lab_version.newer_release()
        threading.Thread(target=work, daemon=True).start()

    def offer_download(self):
        if self.download_button is None:
            self.download_button = button(self.aspect2d, "Download the new Club Coders", 1.2, 0.86,
                                          webbrowser.open, [lab_version.DOWNLOAD_PAGE], 0.035, (0.15, 0.55, 0.25, 1))

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
        code = [rel for rel in res["files"] if rel.endswith(".py") and not rel.startswith("mods/")]
        if code:
            self.needs_restart = True
        done = "switched off" if how == "rollback" else "switched on"
        self.change_msg = (f"Mod {n} {done}. " + ("Restart the server (below) to use it." if code else
                                                    "The arena, rules and robots have been updated."), GREEN)
        self.rebuild_panels()

    # ---------- teacher: outcomes and evidence ----------
    def para(self, f, text, x, y, scale=0.022, fg=GREY, width=0.9):
        """Wrapped text; returns the y below it."""
        t = label(f, text, x, y, scale, fg, wrap=width / scale)
        return y - t.textNode.getNumRows() * t.textNode.getLineHeight() * scale - 0.012

    def show_outcome(self, code_, lesson=None):
        """Open (or close, with None) an outcome's lesson piece in the Outcomes tab."""
        self.outcome_view = code_
        if lesson is not None:
            self.guide_lesson = lesson
        self.rebuild_panels()

    # ---------- the missions as learners see them, editable (CHANGE 97) ----------
    def toggle_mission_editor(self):
        self.editing_missions = not getattr(self, "editing_missions", False)
        self.rebuild_panels()

    def build_mission_editor(self, f, y):
        t = self.teaching or {}
        n_ = getattr(self, "guide_lesson", None) or t.get("lesson", 1)
        label(f, "THE MISSIONS AS LEARNERS SEE THEM", 0.82, y, 0.034, YELLOW)
        button(f, "Back to outcomes", 1.5, y + 0.008, self.toggle_mission_editor, None, 0.022)
        y -= 0.05
        label(f, "Change the words, add an objective or take one out: every learner sees it. The automatic checks "
                 "follow\neach objective's id, not its words (an added one has no check: tick it for a learner by hand). "
                 "After editing,\nask Claude separately whether the checks still fit.", 0.82, y, 0.02, GREY)
        y -= 0.085
        label(f, "Mission", 0.82, y, 0.028, YELLOW)
        for n in lm.LESSONS:
            button(f, str(n), 1.0 + (n - 1) * 0.08, y + 0.008, self.show_outcome, [None, n], 0.028,
                   ON if n == n_ else OFF)
        edits = t.get("edits", {})
        if edits.get("changed") or edits.get("removed") or edits.get("added"):
            button(f, "Reset all to standard", 1.46, y + 0.008, send, [{"type": "missions_edit", "do": "reset"}], 0.022,
                   (0.6, 0.2, 0.15, 1))
        y -= 0.06
        objectives = t.get("edited", {}).get(str(n_), {})
        for i, (mid, v) in enumerate(objectives.items()):
            letter = "abcdefgh"[i] if i < 8 else "+"
            label(f, f"{letter}.", 0.82, y, 0.026, WHITE)
            label(f, f"id {mid}   {' '.join(v[3]) or 'no check'}", 1.5, y, 0.019, BLUE)
            self.entry(f, f"mtitle_{mid}", 0.86, y, 24, 1, initial=v[1], scale=0.024)
            y -= 0.05
            self.entry(f, f"mtext_{mid}", 0.86, y, 30, 3, initial=v[2], scale=0.022)
            button(f, "Save", 1.6, y + 0.008, self.save_objective, [mid], 0.022, (0.15, 0.55, 0.25, 1))
            button(f, "Remove", 1.6, y - 0.04, send, [{"type": "missions_edit", "do": "remove", "id": mid}], 0.02,
                   (0.6, 0.2, 0.15, 1))
            y -= 0.1
        y -= 0.02
        label(f, "Add an objective", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        self.entry(f, "mnew_title", 0.86, y, 24, 1, initial="", scale=0.024)
        label(f, "title", 1.5, y, 0.019, GREY)
        y -= 0.05
        self.entry(f, "mnew_text", 0.86, y, 30, 3, initial="", scale=0.022)
        button(f, "Add", 1.6, y + 0.008, self.add_objective, [n_], 0.022, (0.15, 0.55, 0.25, 1))
        y -= 0.1

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
        if getattr(self, "outcome_view", None):
            return self.build_outcome_piece(f, y, self.outcome_view)
        if getattr(self, "editing_missions", False):
            return self.build_mission_editor(f, y)
        label(f, "LEARNING OUTCOMES  -  evidence so far", 0.82, y, 0.034, YELLOW)
        if not t:
            return
        n_ = getattr(self, "guide_lesson", None) or t["lesson"]
        button(f, "Edit the missions", 1.54, y + 0.008, self.toggle_mission_editor, None, 0.022)  # (CHANGE 97)
        y -= 0.06
        label(f, "Mission", 0.82, y, 0.028, YELLOW)
        for n in lm.LESSONS:
            button(f, str(n), 1.0 + (n - 1) * 0.08, y + 0.008, self.show_outcome, [None, n], 0.028,
                   ON if n == n_ else OFF)
        label(f, "(the class is on mission %d)" % t["lesson"], 1.42, y, 0.022, GREY)
        y -= 0.045
        label(f, lm.LESSONS[n_]["title"], 0.82, y, 0.03, WHITE)
        y -= 0.04
        y = self.para(f, "Overall task: " + lm.LESSON_TASKS[n_], 0.82, y, 0.026, BLUE)
        y -= 0.01
        codes = list(t["outcomes"])
        learners = list(t["grid"])
        label(f, "Outcome  (click for the lesson piece)", 0.82, y, 0.022, GREY)
        for j, n in enumerate(learners[:4]):
            label(f, n[:8], 1.28 + j * 0.12, y, 0.024, GREY, TextNode.ACenter)
        y -= 0.04
        for code_ in codes:
            taught = code_ in lm.GUIDE[n_]  # (outcomes this lesson teaches stand out)
            b = button(f, t["outcomes"][code_][0], 0.82, y + 0.007, self.show_outcome, [code_, n_], 0.026,
                       (0.15, 0.45, 0.65, 1) if taught else (0.14, 0.16, 0.22, 1))
            b.setPos(0.82 + b.getWidth() * 0.026 / 2, 0, y + 0.008)  # (left-aligned)
            for j, n in enumerate(learners[:4]):
                c = t["grid"][n]["outcomes"].get(code_, 0)
                label(f, str(c) if c else "-", 1.28 + j * 0.12, y, 0.026, GREEN if c else GREY, TextNode.ACenter)
            y -= 0.047
        y -= 0.02
        label(f, f"Teacher-checked objectives (mission {t['lesson']})", 0.82, y, 0.028, YELLOW)
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

    def build_outcome_piece(self, f, y, code_):
        """One outcome's lesson piece: the overall task, what learners do, what to teach, what success looks
        like, the missions that give evidence, and who has shown it so far."""
        t = self.teaching or {}
        name_, can_do, refs = lm.OUTCOMES[code_]
        taught_in = lm.outcome_lessons(code_)
        n_ = getattr(self, "guide_lesson", None) or t.get("lesson", 1)
        if n_ not in taught_in:
            n_ = taught_in[0]
        button(f, "< All outcomes", 0.9, y + 0.008, self.show_outcome, [None], 0.026)
        label(f, code_, 1.74, y, 0.026, BLUE, TextNode.ARight)
        y -= 0.06
        label(f, name_.upper(), 0.82, y, 0.034, YELLOW)
        y -= 0.04
        y = self.para(f, "Learners can: " + can_do, 0.82, y, 0.029, WHITE)
        label(f, "Taught in mission", 0.82, y - 0.01, 0.028, GREY)
        for i, n in enumerate(taught_in):
            button(f, str(n), 1.12 + i * 0.08, y - 0.002, self.show_outcome, [code_, n], 0.028, ON if n == n_ else OFF)
        y -= 0.065
        label(f, f"MISSION {n_}: {lm.LESSONS[n_]['title']}", 0.82, y, 0.03, YELLOW, wrap=30)
        y -= 0.045
        y = self.para(f, "Overall task: " + lm.LESSON_TASKS[n_], 0.82, y, 0.026, BLUE)
        piece = lm.GUIDE[n_][code_]
        y -= 0.01
        y = self.para(f, "Task: " + piece["task"], 0.82, y - 0.01, 0.033, WHITE) - 0.01
        label(f, "What learners do", 0.82, y, 0.029, YELLOW)
        y -= 0.042
        for i, step in enumerate(piece["do"], 1):
            y = self.para(f, f"{i}.  {step}", 0.84, y, 0.027, WHITE, 0.88)
        y -= 0.01
        label(f, "What to explain or show", 0.82, y, 0.029, YELLOW)
        y -= 0.042
        y = self.para(f, piece["teach"], 0.84, y, 0.027, GREY, 0.88)
        y -= 0.01
        label(f, "Success looks like", 0.82, y, 0.029, YELLOW)
        y -= 0.042
        y = self.para(f, piece["success"], 0.84, y, 0.027, GREEN, 0.88)
        y -= 0.01
        missions = lm.missions_for_outcome(n_, code_)
        label(f, "Objectives that give evidence", 0.82, y, 0.029, YELLOW)
        y -= 0.042
        for mid, (_, title, _, _, check_) in missions.items():
            who = "the teacher ticks it" if check_ == "teacher" else "ticked by the game"
            y = self.para(f, f"{mid}  {title}  ({who})", 0.84, y, 0.027, WHITE, 0.88)
        grid = t.get("grid", {})
        if grid:
            shown = [n for n in grid if grid[n]["outcomes"].get(code_)]
            y -= 0.01
            y = self.para(f, f"Shown so far by {len(shown)} of {len(grid)}: " + (", ".join(shown) or "nobody yet"),
                          0.82, y, 0.026, GREY)
        self.para(f, "Curriculum: " + refs, 0.82, max(y - 0.01, -0.8), 0.022, GREY)

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
                 "anything (new weapons, hazards, rules, graphics). Every change is tested before you Keep it,\n"
                 "and kept changes can be rolled back later in the Changes tab.", 0.82, y, 0.02, GREY)
        y -= 0.1
        cards = [c for c in (self.teaching or {}).get("cards", []) if c["status"] not in ("reviewed", "rejected")][-4:]
        if not cards:
            label(f, "No requests waiting.", 0.82, y, 0.028, GREY)
        for c in cards:
            job = self.ai_jobs.get(c["id"], {})
            target = self.card_targets.get(c["id"], c["card"].get("target", "robot"))
            label(f, f"#{c['id']} {c['learner']}  [{job.get('status', c['status'])}]", 0.82, y, 0.026)
            y -= 0.038
            goal = label(f, c["card"]["goal"], 0.84, y, 0.022, GREY, wrap=41)
            y -= 0.05 + (max(1, goal.textNode.getNumRows()) - 1) * 0.022  # (the whole of a long idea)
            res = job.get("result")
            if job.get("status") == "Claude is working...":
                took = int(time.time() - job.get("started", time.time()))
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
                        button(f, "Allow the whole game: check and send again", 1.25, y, self.ai_retry, [c, "game"],
                               0.028, (0.15, 0.45, 0.65, 1))
                        y -= 0.07
                    label(f, "Nothing was changed. Choose what Claude may change and send again:", 0.84, y, 0.022,
                          ORANGE)
                    y -= 0.05
                    y = self.card_targets_row(f, y, c, target)
                    button(f, "Check and send again", 0.99, y, self.ai_retry, [c], 0.026, (0.15, 0.45, 0.65, 1))
                    button(f, "Reject", 1.27, y, self.card_status, [c["id"], "rejected"], 0.026)
                    y -= 0.07
                elif job.get("status") == "Kept" and res.get("code_changed"):
                    label(f, "Kept on this laptop only. Try it here first; then, for the class: Make my changes\n"
                             "live.bat (then Restart server). A user mod then appears in Controls, to switch on.",
                          0.84, y, 0.022, ORANGE)
                    y -= 0.075
                    if not TRY and not LOCAL and not lab_version.FROZEN:
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
            if y < -0.8:
                break

    def card_prompt(self, c):
        """Exactly the prompt that Send to Claude sends for this card, as the teacher has set it."""
        import ai_pipeline
        target = self.card_targets.get(c["id"], c["card"].get("target", "robot"))
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
            prompt, target = str(e), "robot"
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
        self.prompt_view = lab_editor.CodeEditor(self, f, self.prompt_state, 0.80, y, 0.94, rows, scale, read_only=True)

    @staticmethod
    def job_mods(job):
        """The user mods a kept AI change added (to switch on when it is tried on this laptop)."""
        change = job.get("change")
        if change is None:
            return []
        return sorted(try_local.mod_keys(change.after.get("lab_sim.py"))
                      - try_local.mod_keys(change.before.get("lab_sim.py")))

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

    def ai_retry(self, c, target=None):
        """Send a card again (perhaps with the whole game allowed): its prompt is shown first, as every prompt is."""
        if target:
            self.card_targets[c["id"]] = target
        self.ai_jobs.pop(c["id"], None)
        self.show_cards(c["id"])

    def ai_send(self, c):
        """Run the learner's approved request through Claude in the background."""
        import ai_pipeline
        learner_design = next((p["design"] for p in self.class_list if p["name"] == c["learner"]), None)
        target = self.card_targets.get(c["id"], c["card"].get("target", "robot"))
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
        job["change"].undo()
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

    # ---------- every frame ----------
    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        if args.screenshot and now - self.start > args.after:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()
            self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot)))
            self.userExit()
        if self.panel_bar and self.last_aspect != self.getAspectRatio():
            self.place_panel()
        if not self.started:  # still on the log-in screen
            return task.cont
        self.read_network()
        self.send_controls(now)
        targets = []
        if self.state and self.roster:
            self.draw_state(dt, now)
            targets = [Point3(*s["pos"]) for s in self.state["robots"] if not s["ko"] and s["id"] not in self.house]
        mine = self.robots.get(self.my_id)
        me_alive = mine is not None and any(s["id"] == self.my_id and not s["ko"]
                                            for s in (self.state or {}).get("robots", []))
        intro = self.state.get("intro") if self.state and self.roster else None
        if intro is not None:  # the countdown before a battle: a slow sweep round the arena
            ang = intro * 0.45 - 1.2
            self.camera.setPos(math.sin(ang) * 11, -math.cos(ang) * 11, 4.5 + intro * 0.2)
            self.camera.lookAt(0, 0, 0.5)
            self.camLens.setFov(60)
            self.cam.pos = None  # (afterwards it cuts straight back to your own view)
        else:
            self.cam.update(dt, mine.chassis if me_alive else None, mine.front if mine else 0.8, targets,
                            self.fx.shake_offset() * 0.5)
        snd = self.my_sound()
        if self.muted:
            self.snd.layers("off", 0, False, 0, False, 0)
        else:
            self.snd.layers(snd["music"], snd["music_volume"], snd["crowd"], snd["crowd_volume"], snd["arena"],
                            snd["arena_volume"])
        if self.newer and self.download_button is None:  # a newer release is out on GitHub
            self.banner_note(f"Club Coders {self.newer} is out: press the green button to download it", 8)
            self.offer_download()
        self.limits_released()  # (a limit's slider let go: the class server gets the new limits)
        if self.pending_rebuild and not self.typing:  # typing stopped: now do the redraw that waited
            self.rebuild_panels()
        self.view_text.setText(f"view: {self.cam.name}  (V to change, wheel or +/- to zoom, right-drag or Q/E to turn)" +
                               ("   typing - Esc to stop" if self.typing else ""))
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
                if TEACHER and self.tab == "teacher" and bool(m.get("paused")) != bool((self.state or {}).get("paused")):
                    rebuild = True  # (the Pause button lights up: CHANGE 102)
                self.state = self.arena_view(m)
                self.fx_waiting.append(self.state.get("fx", {}))
            elif kind == "roster":
                self.apply_roster(m)
            elif kind == "welcome":  # back after a dropped connection (or a server restart)
                self.reconnecting = False
                if self.check_code(m):
                    return
                self.lesson, self.rules, self.design = m["lesson"], m["rules"], m["design"]
                self.default = m.get("default")
                self.draft = copy.deepcopy(self.design)
                self.banner_note("Reconnected: carry on!", 3)
                self.code_shown = None
                rebuild = True
                if TEACHER:
                    self.push_mod_makers()
            elif kind == "lesson":
                mods = m.get("mods") or {}
                if m["lesson"] != self.lesson or m.get("tournament") != self.tournament or \
                        (TEACHER and m["class"] != self.class_list):
                    rebuild = rebuild or self.tab in ("garage", "teacher", "learners", "mods", "ai") or \
                        (self.tab == "limits" and not self.limits_moved)  # (not while a limit's slider is held)
                    if m["lesson"].get("limits") != self.lesson.get("limits"):
                        self.code_shown = None  # (the code says how many points there are to share)
                        rebuild = rebuild or self.show_code
                if mods != self.mod_info:  # a new vote, a maker's name, or someone from the group has come in
                    rebuild = rebuild or self.tab in ("teacher", "mods")
                    if TEACHER:
                        self.forget_mod_makers(mods)
                if TEACHER:  # the computer's robot was rebuilt or reset: the Learner view shows it as it is now
                    was = next((c["design"] for c in self.class_list if c["role"] == "computer"), None)
                    for c in m["class"]:
                        if c["role"] == "computer" and was is not None and c["design"] != was:
                            self.view_drafts.pop(c["name"], None)
                            self.entry_text.pop("name_" + c["name"], None)
                            self.code_shown = None
                self.lesson, self.class_list, self.mod_info = m["lesson"], m["class"], mods
                self.tournament = m.get("tournament")
            elif kind == "session":  # teacher: who is in this session and the next (from the club desk)
                if m.get("session") != self.session:
                    self.session = m.get("session") or {}
                    rebuild = rebuild or self.tab == "accounts"
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
                sig = json.dumps({k: v for k, v in m.items() if k != "top_speed"}, sort_keys=True)
                if sig != self.sig.get("missions"):
                    self.sig["missions"] = sig
                    rebuild = rebuild or self.tab in ("missions", "ai", "card")
                elif self.tab == "missions" and getattr(self, "top_speed_text", None):
                    self.top_speed_text.setText(f"fastest so far {m['top_speed']:.1f} km/h")
            elif kind == "teaching":
                self.teaching = m
                sig = json.dumps(m, sort_keys=True)
                if sig != self.sig.get("teaching"):
                    self.sig["teaching"] = sig
                    rebuild = rebuild or self.tab in ("outcomes", "cards", "learners", "accounts")
            elif kind == "design_result":
                self.design = m["design"]
                if m["ok"]:
                    self.draft = copy.deepcopy(self.design)
                    self.code_shown = None
                    self.entry_text.pop("name_me", None)
                    self.status_msg = ("Your teacher changed your robot." if m.get("by_teacher") else
                                       "Built! Your robot is back at its start square.", GREEN)
                    if self.code_building:
                        self.code_msg = ("Built from your code! Your robot is back at its start square.", GREEN)
                    if m.get("by_teacher"):
                        self.banner_note("Your teacher changed your robot", 4)
                else:
                    self.status_msg = ("Not built: " + "; ".join(m["problems"]), RED)
                    if self.code_building:
                        self.code_msg = self.status_msg
                self.code_building = self.code_hack = self.code_changed = False
                rebuild = rebuild or self.tab == "garage" or self.show_code
            elif kind == "ai_card_result":
                if m["ok"]:
                    self.card_msg = ("Sent! The teacher will look at it." + (" Tip: " + " ".join(m["tips"]) if m["tips"] else ""), GREEN)
                    for k in CARD_FIELDS:
                        self.entry_text.pop(f"card_{k}", None)
                        if f"card_{k}" in self.entries:
                            self.entries[f"card_{k}"].enterText("")
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
        self.banner_note("Lost the connection: reconnecting...", 3600)
        self.reconnecting = True
        if self.reconnect_thread is not None and self.reconnect_thread.is_alive():
            return

        def work():  # keep trying every 2 seconds; the server's welcome comes through the inbox
            time.sleep(2)
            while not net.reconnect():
                time.sleep(2)
        self.reconnect_thread = threading.Thread(target=work, daemon=True)
        self.reconnect_thread.start()

    def arenas_count(self):
        return max(1, int((self.full_roster or {}).get("arenas", 1)))

    def watched_arena(self):
        """The arena this window draws: the one you chose, else your own, else the first."""
        n = self.arenas_count()
        if self.watch is not None and 0 <= self.watch < n:
            return self.watch
        return self.my_arena if self.my_arena is not None and self.my_arena < n else 0

    def arena_view(self, m):
        """The state message with the watched arena's robots, hazards, hits and winner at the top level (the
        drawing code sees one arena, as it always did)."""
        arenas = m.get("arenas") or [{}]
        return {**m, **arenas[min(self.watched_arena(), len(arenas) - 1)]}

    def set_watch(self, i):
        self.watch = None if i == self.my_arena else i
        if self.full_roster:
            self.apply_roster(self.full_roster)
        if self.state and "arenas" in self.state:
            self.state = self.arena_view(self.state)
        if self.tab == "teacher":
            self.rebuild_panels()

    def watch_arena(self, delta):
        n = self.arenas_count()
        if n < 2:
            return
        self.set_watch((self.watched_arena() + delta) % n)
        self.banner_note(f"Watching arena {self.watched_arena() + 1}" +
                         ("  (yours)" if self.watched_arena() == self.my_arena else ""), 2)

    def apply_roster(self, m):
        self.full_roster = m
        my_id = m["mine"].get(name)
        self.my_arena = next((r.get("arena", 0) for r in m["robots"] if r["id"] == my_id), None)
        w = self.watched_arena()
        m = {**m, "robots": [r for r in m["robots"] if r.get("arena", 0) == w]}
        self.roster = m
        drawn = json.dumps({"look": m.get("look", {}), "user_mods": m.get("user_mods", {})},  # (every hazard is
                           sort_keys=True)                                                  # always drawn)
        if drawn != self.hazards_drawn:
            if self.arena_vis:
                self.arena_vis.root.removeNode()
            self.arena_vis = ArenaVisual(self.render, m["hazards"], m.get("look"), m.get("user_mods"))
            self.hazards_drawn = drawn
        for rv in self.robots.values():
            rv.destroy()
        self.robots = {}
        self.house = set()
        self.weapons = {r["id"]: sim.HOUSE_BY_NAME[r["design"]["model"]][0] if r["design"].get("model") in
                        sim.HOUSE_BY_NAME else r["design"]["weapon"] for r in m["robots"]}
        for r in m["robots"]:
            rv = RobotVisual(self.render, r["design"])
            if r["design"].get("house"):
                self.house.add(r["id"])
                rv.set_label(f"{r['design']['name']}\nResident Robot", (1, 0.75, 0.3, 1))
            else:
                rv.set_label(r["owner"])  # (the username above; the robot's name is painted on it: CHANGE 78)
            self.robots[r["id"]] = rv
        self.my_id = m["mine"].get(name)
        self.names = {r["id"]: (r["design"]["name"], r["owner"], tuple(v / 255 for v in r["design"]["colour"]))
                      for r in m["robots"]}

    def send_controls(self, now):
        if now - self.last_ping > 1:
            send({"type": "ping", "t": time.time()})
            self.last_ping = now
        if self.mouseWatcherNode is None:
            return
        down = self.mouseWatcherNode.is_button_down
        if self.typing:  # arrows and space move the text cursor, not the robot
            control = (0.0, 0.0, False)
        else:
            throttle = (down(KeyboardButton.up()) - down(KeyboardButton.down())) * 1.0
            steer = (down(KeyboardButton.left()) - down(KeyboardButton.right())) * 1.0
            if throttle < 0:  # reversing: left and right arc the robot the other way, as a car does (CHANGE 113)
                steer = -steer
            control = (throttle, steer, bool(down(KeyboardButton.space())))
        if control != self.last_control or now - self.last_send > 0.25:
            send({"type": "control", "throttle": control[0], "steer": control[1], "fire": control[2]})
            self.last_control, self.last_send = control, now

    def hit_sound(self, pos, dmg, kind, now):
        """The sound of a contact (quieter further from the camera), and the crowd's reaction to it."""
        snd = self.my_sound()
        if self.muted:
            return
        if snd["effects"]:
            far = (Point3(*pos) - self.camera.getPos()).length()
            self.snd.hit(kind, min(1.0, 0.3 + dmg / 25) * max(0.15, 1 - far / 30) * snd["volume"] * 1.4)
        if kind in ("flip", "break"):
            self.snd.react("cheer", now)
        elif dmg >= 15 and kind not in ("bump", "wall"):
            self.snd.react("ooh", now)

    def machine_sounds(self, st, now):
        """Looping and firing sounds. Hit sounds: a floor saw grinding armour. Weapons: each spinner's motor (its
        pitch follows its real speed), flame throwers, chainsaws, flippers firing, hammers swinging. Motors: your
        own drive motor. Each has its own tick and volume in the teacher's Controls."""
        snd = self.my_sound()
        hits = 0.0 if (self.muted or not snd["effects"]) else snd["volume"]
        vol = 0.0 if (self.muted or not snd["weapons"]) else snd["weapons_volume"]
        drive = 0.0 if (self.muted or not snd["motors"]) else snd["motors_volume"]
        cam = self.camera.getPos()
        if hits and any(st["hz"].get("saw_hot") or []):
            self.snd.loop("grind", "grind", 0.5 * hits)
        else:
            self.snd.stop("grind")
        near = lambda s: max(0.1, 1 - (Point3(*s["pos"]) - cam).length() / 25)  # noqa: E731
        live = [s for s in st["robots"] if not s["ko"]]
        spinners = sorted((s for s in live if s["rpm"] > 30), key=near, reverse=True)[:4]
        for s in spinners:  # the four nearest spinners each have their own motor sound
            self.snd.spinner(f"spin{s['id']}", s["rpm"], near(s) * vol)
        self.snd.keep_only("spin", {f"spin{s['id']}" for s in spinners})
        flames = [s for s in live if s.get("fl")]
        if vol and flames:
            self.snd.loop("flame", "flame", 0.6 * vol * max(near(s) for s in flames))
        else:
            self.snd.stop("flame")
        saws = [s for s in live if s.get("act") and self.weapons.get(s["id"]) == "chainsaw"]
        if vol and saws:
            self.snd.loop("chainsaw", "chainsaw", 0.55 * vol * max(near(s) for s in saws))
        else:
            self.snd.stop("chainsaw")
        for s in st["robots"]:  # a flipper firing, a hammer swinging
            fired = s.get("fc", 0) > self.fire_counts.get(s["id"], s.get("fc", 0))
            self.fire_counts[s["id"]] = s.get("fc", 0)
            kind = self.weapons.get(s["id"])
            if fired and vol and kind in ("wedge", "hammer"):
                self.snd.play("pneumatic" if kind == "wedge" else "swing", 0.8 * vol * near(s))
        mine = next((s for s in live if s["id"] == self.my_id), None)
        if drive and mine:  # no idle hum: a robot standing still is silent, and the sound comes in as it moves
            keys = self.last_control or (0.0, 0.0, False)
            driven = (keys[0] or keys[1]) and st.get("intro") is None and not st.get("paused")
            power = max(max(0.0, abs(mine["speed"]) - 0.1) / 20,
                        0.04 if driven else 0.0)  # (driven but not going forward: turning on the spot, pushing)
            self.snd.loop("motor", "motor", min(0.25, power) * drive, 0.6 + abs(mine["speed"]) / 8)
        else:
            self.snd.stop("motor")
        for s in st["robots"]:  # a knockout gets a cheer, the end of a battle gets applause
            if s["ko"] and not self.was_ko.get(s["id"]):
                self.snd.react("cheer", now)
            self.was_ko[s["id"]] = s["ko"]
        if st["winner"] and st["winner"] != self.last_winner:
            self.snd.react("applause", now)
        self.last_winner = st["winner"]

    def show_intro(self, t, now):
        """The countdown before a battle, timed by the server so every window shows it together (t: seconds since
        it began, or None): the arena's name, who is fighting, then 3, 2, 1 with beeps and ACTIVATE! with a cheer.
        Robots can't drive or fire until ACTIVATE!"""
        snd = self.my_sound()
        loud = 0.0 if (self.muted or not snd["effects"]) else min(1.0, snd["volume"] / 0.7)
        big, small = "", ""
        if t is not None:
            if not self.intro_was or t < 1.0:
                self.intro_beeped = {n for n in (3, 2, 1) if t > INTRO[1] + (4 - n)}  # (joined part-way through)
            if t < INTRO[0]:
                big = str((self.roster or {}).get("look", {}).get("name") or "ROBOT LAB")
            elif t < INTRO[1]:
                big = "  v  ".join(nm for rid, (nm, _, _) in self.names.items() if rid not in self.house)
                small = "Get ready: nobody can move or fire until ACTIVATE!"
            else:
                n = max(1, 3 - int(t - INTRO[1]))
                big = str(n)
                if n not in self.intro_beeped:
                    self.intro_beeped.add(n)
                    self.snd.play("beep", 0.6 * loud)
        elif self.intro_was:  # it has just ended
            self.activate_until = now + 1.2
            self.snd.play("go", 0.8 * loud)
            if not self.muted:
                self.snd.react("cheer", now)
        self.intro_was = t is not None
        if t is None and now < self.activate_until:
            big = "ACTIVATE!"
        if big != self.intro_big.getText():
            self.intro_big.setText(big)
            self.intro_big.setScale(min(0.16, 3.6 / max(1, len(big))))
        if small != self.intro_small.getText():
            self.intro_small.setText(small)

    def draw_state(self, dt, now):
        st, me = self.state, None
        if self.arena_vis and st.get("hz"):
            self.arena_vis.update(st["hz"])
        # sparks, flames and debris
        for fx in self.fx_waiting:
            for pos, dmg, kind in fx.get("impacts", []):
                victim = min(st["robots"], key=lambda s: sum((a - b) ** 2 for a, b in zip(s["pos"], pos)), default=None)
                colour = self.names.get(victim["id"], (0, 0, (0.7, 0.7, 0.7)))[2] if victim else (0.7, 0.7, 0.7)
                self.fx.impact(pos, dmg, kind, colour)
                self.hit_sound(pos, dmg, kind, now)
            for pos, direction, count in fx.get("streams", []):
                self.fx.stream(pos, direction, count)
        self.fx_waiting = []
        self.machine_sounds(st, now)
        row, real = 0, bool(st.get("rd"))
        for s in sorted(st["robots"], key=lambda s: s["id"] in self.house):  # (the Resident Robots' bars go last)
            rv = self.robots.get(s["id"])
            if rv is None:
                continue
            rv.update(s, dt)
            if s.get("fl"):
                tip, fwd = rv.nozzle()
                self.fx.flame(tip, fwd)
            if "pt" in s:  # parts bending, wobbling and coming off, and the bars of parts just hit
                rv.damage(s["pt"], now, dt, real)
                for pos, amount in rv.trouble():
                    self.fx.smoke(pos, 0.2 + 0.35 * amount)
            if s["hp"] < self.last_hp.get(s["id"], s["hp"]) - 0.5:
                self.flash[s["id"]] = now + 0.15
            self.last_hp[s["id"]] = s["hp"]
            rv.flash(now < self.flash.get(s["id"], 0))
            damage = 1 - max(0.0, s["hp"]) / max(1, s["max"])
            if damage > 0.55 and s["pos"][2] > -1:
                self.fx.smoke(s["pos"], (damage - 0.55) / 0.45 + (1.0 if s["ko"] else 0))
            if s["id"] == self.my_id and not s["ko"]:
                me = Point3(*s["pos"])
            if row < len(self.rows):
                self.hud_row(self.rows[row], s, s["id"] in self.house, real)
                row += 1
        self.fx.update(dt)
        for i in range(row, len(self.rows)):  # (rows nobody is using)
            self.rows[i][0].hide()
        if row != self.hud_used:
            self.layout_hud(row)
        lesson = f"M{self.lesson.get('lesson_number', 1)}  "
        if self.arenas_count() > 1:
            lesson += f"ARENA {self.watched_arena() + 1} of {self.arenas_count()}  "
        if self.tournament:
            lesson += "WINNER STAYS ON  "
        if st["practice"]:
            self.mode_text.setText(lesson + "PRACTICE (no damage)")
        else:
            left = st["time_left"] or 0
            self.mode_text.setText(lesson + f"BATTLE   {int(left) // 60}:{int(left) % 60:02d}")
        self.status_text.setText(f"{self.clock.getAverageFrameRate():.0f} fps   ping {self.ping_ms:.0f} ms")
        self.feed.setText("\n".join(st["events"]))
        self.show_intro(st.get("intro"), now)
        if now < getattr(self, "note_until", 0):
            self.banner.setText(self.note_text)
            self.banner.setScale(0.075 if getattr(self, "note_big", False) else 0.045)
        elif st["winner"]:
            self.banner.setScale(0.08)
            self.banner.setText(st["winner"] + ("\nPress Restart in Controls" if TEACHER else ""))
        elif st["paused"]:
            self.banner.setScale(0.08)
            self.banner.setText("PAUSED")
        else:
            self.banner.setText("")
        return me


Lab().run()
