"""Robot Lab window for learners and the teacher. The fight runs on lab_server.py.

Learner:  python lab_client.py                (log in with a username and password in the window)
Teacher:  python lab_client.py --name "Mr P" --teacher
Class server: add --host wss://play.<club domain> (the downloaded game has it built in). Learners type the class
code once (it is remembered on that computer); the teacher's code comes from --code, ROBOTLAB_TEACHER_CODE or
teacher_settings.json next to this file (never in GitHub).

Logging in: a new username makes a new profile. Everything is saved to it (robot, missions, brain,
camera view), so after a dropped connection the window reconnects by itself, and next lesson the
learner logs in with the same username and password to carry on.

Driving:   Arrow keys drive   Space fire (wedge / hammer)   F weapon on/off
Panels:    M missions   G garage   I AI request card   C your robot as code (edit it, then Apply)
           T teacher panels (the teacher's Learner view shows and changes what a learner sees)   H help
Brain:     U upload brains/my_brain.py   P autopilot on/off (your brain drives)
Camera:    V change view (third person, first person, zoomed arena follow, full arena)   O full arena
           mouse wheel or + / - zoom in and out (every view)
Typing:    while you type in a text box, keys go into the box (not the game). Click away or press Esc to stop.
           In the code panel, Enter applies your code and the up / down arrows move between lines.
"""
import argparse
import ast
import copy
import json
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser

from panda3d.core import loadPrcFileData

import lab_version  # (first: this records the code this window is running, before anything can change it)

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
ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
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
# learners edit brains/my_brain.py: next to Robot Lab.exe in the download, next to this file otherwise
BRAINS = os.path.join(os.path.dirname(sys.executable), "brains", "robotlab") if lab_version.FROZEN else os.path.join(HERE, "brains")  # (Club Coders: each game has its own brains folder)


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def remember(key, value):
    """Keep a setting (the class code) on this computer, so it's only typed once."""
    path = os.path.join(SETTINGS_DIR, "settings.json")
    data = load_json(path) | {key: value}
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


if args.host == "class":  # the class server's address, from the teacher's settings
    args.host = load_json(TEACHER_SETTINGS).get("server") or lab_version.ONLINE_SERVER
elif args.host is None:  # a learner's last choice on the login screen, or this computer / the built-in server
    where = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("where")
    args.host = {"local": lab_version.LOCAL_SERVER, "online": lab_version.ONLINE_SERVER}.get(
        where if not TEACHER else None, lab_version.SERVER)
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))  # a laptop test server
import club_ticket  # noqa: E402
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
x = args.x if args.x is not None else (40 if TEACHER else 1360)
loadPrcFileData("", f"win-size 1280 720\nwindow-title {title}\nframebuffer-multisample 1\nmultisamples 4\n"
                    f"win-origin {x} 80\n")
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import (DGG, DirectButton, DirectCheckButton, DirectEntry, DirectFrame,  # noqa: E402
                                  DirectSlider)
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, Point3, TextNode, WindowProperties  # noqa: E402

import cpu_brains  # noqa: E402
import lab_missions as lm  # noqa: E402
import lab_sim as sim  # noqa: E402
import rw_fx  # noqa: E402
import rw_gfx  # noqa: E402
import rw_sound  # noqa: E402
from net import Net  # noqa: E402
from rw_camera import GameCamera  # noqa: E402
from rw_gfx import ArenaVisual, RobotVisual  # noqa: E402

YELLOW, WHITE, GREY, RED, GREEN = (1, .9, .35, 1), (1, 1, 1, 1), (.75, .8, .9, 1), (1, .45, .4, 1), (.5, .95, .55, 1)
BLUE, ORANGE = (.55, .85, 1, 1), (1, .7, .3, 1)
PANEL = (0.04, 0.05, 0.08, 0.88)
ON, OFF = (0.85, 0.65, 0.1, 1), (0.2, 0.25, 0.35, 1)
SWATCHES = [(220, 60, 50), (240, 140, 30), (240, 200, 40), (60, 190, 90), (60, 130, 230), (180, 90, 230),
            (230, 90, 170), (230, 230, 230)]
PRETTY = {"forward_speed": "Forward speed", "reverse_speed": "Reverse speed", "turn_speed": "Turn speed",
          "acceleration": "Acceleration", "size": "Size", "points_table": "Points table",
          "choose_weapon": "Choose weapon", "name_and_colour": "Name and colour", "code_view": "Code view",
          "stats_readout": "Stats readout", "weapon_toggle": "Weapon on/off", "house_robots": "House robots"}
HAZARD_NAMES = {"pit": "Drop zone open", "floor_flipper": "Floor flipper", "saws": "Floor saws",
                "spikes": "Wall spikes", "house_robots": "House robots"}
LEARNER_TABS = [("missions", "Missions (M)"), ("garage", "Garage (G)"), ("ai", "AI card (I)"), ("card", "My card (K)")]
TEACHER_TABS = [("teacher", "Controls"), ("learners", "Learners"), ("accounts", "Accounts"), ("outcomes", "Outcomes"),
                ("cards", "AI cards"), ("changes", "Changes"), ("garage", "My robot")]
STOP_CODES = (4001, 4004, 4006, 4007, 4008, 4009, 4010, 4011)  # the server said no: wrong code or password,
# old version, deleted, the session ended, the group hasn't started, a ticket that ran out
TARGETS = {"robot": "Their robot", "arena": "The arena", "rules": "The rules", "game": "The whole game"}
APP = None  # the window (so any button click can end typing in a text box)
AI_RULES = ("Only the teacher uses the AI.  Never put personal information in a request.\n"
            "AI can be wrong: you test the code and must be able to explain it.\n"
            "Say where AI helped (the tool and the date).")
CARD_FIELDS = ("goal", "variables", "test", "predict")


def label(parent, text, x, y, scale=0.036, fg=WHITE, align=TextNode.ALeft, wrap=None):
    return OnscreenText(text, pos=(x, y), scale=scale, fg=fg, align=align, parent=parent, mayChange=True,
                        wordwrap=wrap)


def button(parent, text, x, y, command, args_=None, scale=0.036, colour=OFF):
    def clicked(*a):  # pressing a button ends typing, so the panel can redraw with the result
        if APP is not None:
            APP.stop_typing()
        command(*a)
    return DirectButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), command=clicked, extraArgs=args_ or [],
                        frameColor=colour, text_fg=WHITE, relief=DGG.FLAT, pad=(0.3, 0.15))


def check(parent, text, x, y, value, command, scale=0.032):
    return DirectCheckButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), indicatorValue=1 if value else 0,
                             command=command, text_align=TextNode.ALeft, text_fg=WHITE, frameColor=(0, 0, 0, 0),
                             boxPlacement="left")


def send(msg):
    if net is not None:
        net.send(msg)


class Lab(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.setBackgroundColor(0.07, 0.08, 0.11)
        global APP
        APP = self
        rw_gfx.init(self, args.gfx)
        self.fx = rw_fx.Effects(self.render, args.gfx)
        self.snd = rw_sound.Sounds(self, on=not args.offscreen)
        self.muted = False
        self.entries, self.entry_text = {}, {}   # text boxes, and what was typed in them
        self.typing = None           # the text box being typed in (game keys are ignored while typing)
        self.pending_rebuild = False  # a panel redraw waiting until typing stops
        self.started = False
        self.login_panel = None
        self.delete_armed = None      # teacher: the account whose Delete button says "Sure?"
        self.newer, self.download_button = None, None  # a newer release on GitHub, and its download button
        if lab_version.FROZEN or not LOCAL:
            self.check_for_update()
        self.accept("escape", self.escape)
        self.accept("mouse1", self.stop_typing)  # clicking the arena (not a panel) stops typing
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
        self.class_list, self.missions, self.teaching = [], None, None
        self.sig = {}                            # what each panel was last drawn from
        self.card_checks = {"privacy": False, "review": False, "credit": False}
        self.card_msg = ("", WHITE)
        self.card_target = "robot"
        self.ai_jobs = {}        # teacher: card id -> {"status", "result", "change"}
        self.card_targets = {}   # teacher: card id -> what Claude may change (can differ from the learner's choice)
        self.card_user_mod = {}  # teacher: card id -> make a whole-game change as a switchable user mod
        self.view_name, self.view_tab = None, "garage"   # teacher's learner view
        self.change_view, self.change_page, self.change_msg = None, 0, ("", GREY)  # teacher's Changes tab
        self.needs_restart = bool(welcome.get("live_ready"))  # a code change (or a live update) waits for a restart
        self.view_drafts, self.view_missions = {}, {}
        self.code_shown, self.code_msg = None, ("", GREY)
        self.cam = GameCamera(self, "third")
        self.arena_vis, self.hazards_drawn = None, None
        self.robots, self.roster, self.my_id, self.names = {}, None, None, {}
        self.house = set()       # ids of the house robots
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
        self.show_code = False
        self.reconnecting = False
        self.restore_prefs(welcome.get("prefs", {}))
        self.key("f", send, {"type": "weapon"})
        self.key("g", self.open_tab, "garage")
        self.key("c", self.toggle_code)
        self.key("h", self.toggle_help)
        self.key("u", self.upload_brain)
        self.key("p", send, {"type": "autopilot"})
        self.key("v", self.cam.cycle)
        self.key("o", self.cam.set_mode, "arena")
        self.key("n", self.toggle_mute)
        self.key("b", self.toggle_hud)
        for key, factor in (("wheel_up", 0.88), ("wheel_down", 1 / 0.88), ("=", 0.8), ("+", 0.8), ("-", 1.25),
                            ("=-repeat", 0.9), ("--repeat", 1.11)):
            self.key(key, self.cam.wheel, factor)
        if TEACHER:
            self.key("t", self.cycle_teacher_tabs)
        else:
            self.key("m", self.open_tab, "missions")
            self.key("k", self.open_tab, "card")
            self.key("i", self.open_tab, "ai")
        self.accept("arrow_up", self.code_line_move, [-1])  # only does anything while typing in the code
        self.accept("arrow_down", self.code_line_move, [1])
        self.hud()
        self.rebuild_panels()
        self.start = self.last = time.perf_counter()
        self.prefs_at = self.start
        if welcome.get("new_profile"):
            self.banner_note(f"Welcome, {name}! Your profile is made: next time log in with the same username "
                             "and password.", 7)
        if args.selftest:  # press some garage buttons the way a learner would, then build
            self.taskMgr.doMethodLater(2, lambda t: [self.change_points("speed", 5), self.change_points("armour", -5),
                                                     self.set_colour([60, 190, 90])] and None, "t1")
            self.taskMgr.doMethodLater(2.5, lambda t: self.send_design(), "t2")

    def restore_prefs(self, prefs):
        """A learner's camera view and half-typed AI card, from their profile."""
        self.cam.restore(prefs.get("camera", {}))
        for k in CARD_FIELDS:
            if prefs.get("card", {}).get(k):
                self.entry_text[f"card_{k}"] = str(prefs["card"][k])[:400]
        if prefs.get("card_target") in lm.AI_TARGETS and prefs["card_target"] != "game":
            self.card_target = prefs["card_target"]
        self.prefs_sent = json.dumps(self.gather_prefs(), sort_keys=True)

    def gather_prefs(self):
        card = {}
        for k in CARD_FIELDS:
            e = self.entries.get(f"card_{k}")
            card[k] = e.get() if e is not None else self.entry_text.get(f"card_{k}", "")
        return {"camera": self.cam.settings(), "card": card, "card_target": self.card_target}

    def key(self, key, fn, *extra):
        """A game shortcut key. It does nothing while you are typing in a text box."""
        self.accept(key, lambda: None if self.typing or not self.started else fn(*extra))

    def escape(self):
        if self.typing:  # Esc while typing just stops typing
            self.stop_typing()
        else:
            self.userExit()

    def start_typing(self, key):
        self.typing = key

    def stop_typing(self, key=None):
        if key is not None and key != self.typing:
            return
        e = self.entries.get(self.typing)
        self.typing = None
        if e is not None:
            try:
                e["focus"] = 0
            except Exception:
                pass

    # ---------- fixed parts of the screen ----------
    def hud(self):
        self.hud_back = DirectFrame(frameColor=PANEL, frameSize=(-1.76, -0.86, 0.36, 0.97))
        label(self.aspect2d, f"ROBOT LAB  -  {'TEACHER' if TEACHER else 'LEARNER'}: {name}", -1.72, 0.91, 0.045,
              BLUE if TEACHER else YELLOW)
        self.hud_small = bool(load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("hud_small"))
        self.hud_button = button(self.aspect2d, "Hide", -0.925, 0.918, self.toggle_hud, None, 0.028)
        self.hud_rows = self.aspect2d.attachNewNode("health bars")
        self.hud_used = None
        self.rows = []
        for i in range(10):  # up to 6 robots and 4 house robots
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
        keys = ("Arrows drive  Space fire  F weapon  " + ("T panels  " if TEACHER else "M missions  I AI card  ") +
                "G garage  C code  U upload brain  P autopilot  V view  O full arena  wheel or +/- zoom  B bars  H help")
        self.view_text = label(self.aspect2d, "", 0, 0.795, 0.026, GREY, TextNode.ACenter)
        self.help = label(self.aspect2d, keys, -0.45, -0.96, 0.028, GREY, TextNode.ACenter)

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
        t.setText(f"{nm}  -  {'House robot' if house else owner}{you}")
        t.setFg(ORANGE if house else YELLOW if you else WHITE)
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
        weapon = f"{s['rpm']} rpm, {s['energy']} J" if s["rpm"] else ("on" if s["on"] else "off")
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

    def restart_window(self, reopen_for=None):
        """Reopen this window (to load code changes), logged in as the same person."""
        env = dict(os.environ, ROBOTLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        if reopen_for:  # remember which server code this reopen was for, so it only happens once
            env["ROBOTLAB_REOPENED"] = reopen_for
        else:
            env.pop("ROBOTLAB_REOPENED", None)
        argv = [a for a in sys.argv[1:]]
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

    def keep_typing(self):
        """Remember what is typed in text boxes, so redrawing a panel doesn't lose it."""
        for key, e in self.entries.items():
            try:
                self.entry_text[key] = e.get()
            except Exception:
                pass
        self.entries = {}

    def entry(self, parent, key, x, y, width=18, lines=1, initial="", command=None, scale=0.03, obscured=False):
        e = DirectEntry(parent=parent, initialText=self.entry_text.get(key, initial), scale=scale, width=width,
                        pos=(x, 0, y), numLines=lines, focus=0, frameColor=(0.15, 0.17, 0.22, 1), text_fg=WHITE,
                        obscured=1 if obscured else 0,
                        command=command, focusInCommand=self.start_typing, focusInExtraArgs=[key],
                        focusOutCommand=self.stop_typing, focusOutExtraArgs=[key])
        if key == self.typing:  # redrawn while typing: carry on typing in the new box
            e["focus"] = 1
            e.setCursorPosition(len(e.get()))
        self.entries[key] = e
        return e

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
        for p in (self.panel, self.code_panel):
            if p is not None:
                p.destroy()
        self.panel = self.code_panel = None
        if self.tab:
            f = self.panel = DirectFrame(frameColor=PANEL, frameSize=(0.78, 1.76, -0.93, 0.97))
            tabs = TEACHER_TABS if TEACHER else LEARNER_TABS
            for i, (key, text) in enumerate(tabs):
                button(f, text, 0.84 + (i + 0.5) * (0.9 / len(tabs)), 0.925, self.open_tab, [key],
                       0.026 if TEACHER else 0.03, ON if key == self.tab else OFF)
            {"garage": self.build_garage, "teacher": self.build_teacher_panel, "missions": self.build_missions,
             "ai": self.build_ai_card, "outcomes": self.build_outcomes, "cards": self.build_cards,
             "card": self.build_card,
             "learners": self.build_learner_view, "changes": self.build_changes,
             "accounts": self.build_accounts}[self.tab](f, 0.84)
        if self.show_code and (TEACHER or self.lesson["tools"]["code_view"]):
            self.build_code_panel()
        if self.typing and self.typing not in self.entries:  # the box being typed in has gone
            self.typing = None

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
                self.view_drafts[who] = copy.deepcopy(d)
            return self.view_drafts[who]
        return self.draft

    def tools(self):
        if TEACHER:
            return {k: True for k in self.lesson["tools"]} | {"weapons": list(self.rules["weapons"])}
        return self.lesson["tools"]

    # ---------- garage: design your robot ----------
    def build_garage(self, f, y, view=None):
        """view: the teacher's Learner view of this learner. The teacher sees every control, with a tick box
        on each showing (and setting) whether the learner can see and change it."""
        tools, d = self.tools(), self.cur()
        seen = self.lesson["tools"]

        def shown_box(tool, yy):
            if view:
                check(f, " learner sees", 1.52, yy, seen.get(tool), lambda v, t=tool: self.set_lesson({"tools": {t: bool(v)}}),
                      0.022)
        label(f, f"{view.upper()}'S ROBOT (what they see and change)" if view else
              ("MY ROBOT" if TEACHER else "GARAGE  -  design your robot"), 0.82, y, 0.034 if view else 0.04, YELLOW)
        y -= 0.07
        if tools.get("name_and_colour"):
            label(f, "Name", 0.82, y, 0.03)
            self.entry(f, self.name_key(), 0.98, y, 10, initial=d["name"],
                       command=lambda t: self.cur().__setitem__("name", t[:16]))
            shown_box("name_and_colour", y)
            y -= 0.065
            for i, c in enumerate(SWATCHES):
                big = 0.95 if list(c) == list(d["colour"]) else 0.6
                DirectButton(parent=f, text="", scale=0.034, pos=(0.84 + i * 0.09, 0, y), relief=DGG.FLAT,
                             frameColor=(*(v / 255 for v in c), 1), frameSize=(-0.9, 0.9, -big, big),
                             command=self.set_colour, extraArgs=[list(c)])
            if list(d["colour"]) not in [list(c) for c in SWATCHES]:  # a colour typed in the code
                DirectFrame(parent=f, frameColor=(*(v / 255 for v in d["colour"]), 1), frameSize=(-0.03, 0.03, -0.032, 0.032),
                            pos=(0.84 + len(SWATCHES) * 0.09, 0, y))
            y -= 0.07
        model = d.get("model")
        if tools.get("house_robots") or model:
            label(f, "Robot", 0.82, y, 0.03)
            if tools.get("house_robots"):
                button(f, "My design", 1.0, y + 0.008, self.set_model, [None], 0.024, OFF if model else ON)
                for i, hr in enumerate(self.rules.get("house", {})):
                    button(f, hr, 1.17 + i * 0.13, y + 0.008, self.set_model, [hr], 0.024, ON if hr == model else OFF)
                shown_box("house_robots", y - 0.04)
            else:
                label(f, f"{model} (house robot, set by the teacher)", 1.0, y, 0.026, ORANGE)
            y -= 0.06 if not view else 0.075
        if model:
            label(f, f"Weapon: {self.rules['house_weapons'].get(d['weapon'], d['weapon'])}", 0.82, y, 0.026, ORANGE)
            y -= 0.045
            label(f, "House robots are heavy (190 kg), with armour 400 and big wheels.\n"
                     "Their stats are fixed, so points and settings aren't used.", 0.82, y, 0.024, GREY)
            y -= 0.1
        elif tools.get("choose_weapon"):
            label(f, "Weapon", 0.82, y, 0.03)
            for i, w in enumerate(tools.get("weapons", [])):
                button(f, w, 1.02 + i * 0.13, y + 0.008, self.set_weapon, [w], 0.026, ON if w == d["weapon"] else OFF)
            shown_box("choose_weapon", y - 0.04)
        else:
            label(f, f"Weapon: {d['weapon']}  (chosen by the teacher this lesson)", 0.82, y, 0.028, GREY)
        if not model:
            y -= 0.045
            label(f, self.rules["weapons"].get(d["weapon"], ""), 0.82, y, 0.024, GREY)
            y -= 0.06 if not view else 0.075
        if tools.get("points_table") and not model:
            used = sum(d["points"].values())
            label(f, f"POINTS  ({used} of {self.rules['points_total']} used, {self.rules['points_total'] - used} left)",
                  0.82, y, 0.03, YELLOW if used <= self.rules["points_total"] else RED)
            shown_box("points_table", y)
            y -= 0.055
            for stat in self.rules["stats"]:
                v = d["points"][stat]
                label(f, stat.title(), 0.82, y, 0.03)
                for dx, delta, text in ((1.04, -5, "-5"), (1.12, -1, "-"), (1.26, 1, "+"), (1.34, 5, "+5")):
                    button(f, text, dx, y + 0.008, self.change_points, [stat, delta], 0.026)
                label(f, str(v), 1.19, y, 0.032, WHITE, TextNode.ACenter)
                DirectFrame(parent=f, frameColor=(0.2, 0.2, 0.22, 1), frameSize=(0, 0.3, 0, 0.02), pos=(1.42, 0, y))
                DirectFrame(parent=f, frameColor=(0.9, 0.7, 0.15, 1),
                            frameSize=(0, 0.3 * min(v, self.rules["stat_max"]) / self.rules["stat_max"], 0, 0.02),
                            pos=(1.42, 0, y))
                y -= 0.055
        self.sliders = {}
        shown = [k for k in self.rules["settings"] if tools.get(k)] if not model else []
        if shown:
            label(f, "SETTINGS  (percent)", 0.82, y, 0.03, YELLOW)
            y -= 0.055
        for k in shown:
            lo, hi, _, _ = self.rules["settings"][k]
            label(f, PRETTY[k], 0.82, y, 0.028)
            s = DirectSlider(parent=f, range=(lo, hi), value=d["settings"][k], pageSize=5, scale=0.17 if view else 0.2,
                             pos=(1.24 if view else 1.3, 0, y + 0.008), command=self.slider_moved, extraArgs=[k],
                             thumb_frameSize=(-0.04, 0.04, -0.12, 0.12))
            self.sliders[k] = (s, label(f, f"{d['settings'][k]:.0f}%", 1.44 if view else 1.55, y, 0.028, WHITE))
            shown_box(k, y)
            y -= 0.055
        self.stats_text = None
        if tools.get("stats_readout") and not model:
            self.stats_text = label(f, "", 0.82, y - 0.01, 0.026, GREEN)
            self.update_stats_text()
            shown_box("stats_readout", y)
            y -= 0.18
        if view:
            button(f, f"BUILD FOR {view.upper()}", 1.27, y, self.send_design_for, [view], 0.036, (0.15, 0.55, 0.25, 1))
        else:
            button(f, "BUILD MY ROBOT", 1.27, y, self.send_design, None, 0.04, (0.15, 0.55, 0.25, 1))
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
            f"Self-rights after {st['self_right']:.1f} s    Grip {st['grip']:.2f}" +
            (f"\nFlipper strength {st['flip_strength'] * 100:.0f}%  (100% flips house robots)"
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
        send({"type": "design", "design": self.draft})
        self.status_msg = ("Building...", GREY)
        if self.tab == "garage":
            self.garage_msg.setText("Building...")

    def send_design_for(self, learner):
        d = self.cur()
        if self.name_key() in self.entries:
            d["name"] = self.entries[self.name_key()].get()[:16]
        send({"type": "design_for", "learner": learner, "design": d})
        self.garage_msg.setText(f"Building for {learner}...")

    # ---------- code view: your robot as Python code, which you can edit ----------
    def code_lines(self, d):
        lines = ["ROBOT = {", f'    "name": "{d["name"]}",        # text (a string)',
                 f'    "colour": [{d["colour"][0]}, {d["colour"][1]}, {d["colour"][2]}],  # red, green, blue: 0 to 255',
                 f'    "weapon": "{d["weapon"]}",']
        if d.get("model"):
            lines.append(f'    "model": "{d["model"]}",      # driving a house robot')
        lines += ['    "points": {                 # a dictionary: 100 points to share']
        lines += [f'        "{k}": {v},' for k, v in d["points"].items()]
        lines += ["    },", '    "settings": {               # percentages']
        lines += [f'        "{k}": {v:.0f},' for k, v in d["settings"].items()]
        lines += ["    },", "}", f"# points used: {sum(d['points'].values())} of {self.rules['points_total']}"]
        return lines

    def build_code_panel(self):
        who = self.viewing()
        d = self.cur()
        f = self.code_panel = DirectFrame(frameColor=PANEL, frameSize=(-0.84, -0.02, -0.92, 0.32))
        label(f, f"{who.upper()}'S ROBOT AS PYTHON CODE" if who else "YOUR ROBOT AS PYTHON CODE", -0.8, 0.26, 0.032,
              YELLOW)
        label(f, "Change a value, then press Enter or APPLY: the garage changes to match.", -0.8, 0.215, 0.022, GREY)
        fresh = self.code_lines(d)
        typed = [self.entry_text.get(f"code_{i}") for i in range(len(self.code_shown or []))]
        edited = self.code_shown is not None and any(t is not None and t != s for t, s in zip(typed, self.code_shown))
        lines = [t if t is not None else s for t, s in zip(typed, self.code_shown)] if edited else fresh
        if not edited:
            for i in range(40):
                self.entry_text.pop(f"code_{i}", None)
        for i, line in enumerate(lines):
            self.entry(f, f"code_{i}", -0.81, 0.165 - i * 0.043, 35.5, initial=line, scale=0.022,
                       command=lambda t: self.apply_code())
        self.code_shown = lines
        yb = 0.165 - len(lines) * 0.043 - 0.03
        button(f, "APPLY CODE", -0.62, yb, self.apply_code, None, 0.03, (0.15, 0.55, 0.25, 1))
        button(f, "UNDO MY EDITS", -0.3, yb, self.reset_code, None, 0.03)
        label(f, self.code_msg[0], -0.8, yb - 0.06, 0.022, self.code_msg[1], wrap=36)

    def refresh_code_panel(self):
        for key in [k for k in self.entries if k.startswith("code_")]:
            self.entry_text[key] = self.entries.pop(key).get()
        if self.code_panel is not None:
            self.code_panel.destroy()
        self.build_code_panel()

    def reset_code(self):
        self.code_shown, self.code_msg = None, ("", GREY)
        for i in range(40):
            self.entry_text.pop(f"code_{i}", None)
        self.rebuild_panels()

    def code_line_move(self, delta):
        """Up / down arrows move between lines of code while typing in it."""
        if not self.typing or not self.typing.startswith("code_"):
            return
        e = self.entries.get(f"code_{int(self.typing[5:]) + delta}")
        if e is not None:
            self.entries[self.typing]["focus"] = 0
            e["focus"] = 1

    def apply_code(self):
        """Read the edited code as data (never run it), and change the design to match."""
        n = len(self.code_shown or [])
        text = "\n".join(self.entries[f"code_{i}"].get() if f"code_{i}" in self.entries else "" for i in range(n))
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            msg = e.msg if e.msg.endswith((".", "?", "!")) else e.msg + "."
            self.code_msg = (f"Line {e.lineno}: {msg} Check the brackets, commas and quote marks.", RED)
            self.refresh_code_panel()
            return
        node = next((s.value for s in tree.body if isinstance(s, ast.Assign)
                     and [getattr(t, "id", None) for t in s.targets] == ["ROBOT"]), None)
        if node is None:
            self.code_msg = ("The code needs ROBOT = { ... }", RED)
            self.refresh_code_panel()
            return
        try:
            new = ast.literal_eval(node)
        except ValueError:
            self.code_msg = ("Only plain values are allowed: numbers, \"text\", [lists] and {dictionaries}.", RED)
            self.refresh_code_panel()
            return
        if not isinstance(new, dict):
            self.code_msg = ("ROBOT must be a dictionary: { ... }", RED)
            self.refresh_code_panel()
            return
        d, tools, locked, problems = self.cur(), self.tools(), [], []
        if "name" in new and str(new["name"]) != d["name"]:
            if tools.get("name_and_colour"):
                d["name"] = str(new["name"])[:16]
                self.entry_text.pop(self.name_key(), None)
            else:
                locked.append("name")
        c = new.get("colour", d["colour"])
        if c != d["colour"]:
            if not (isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c)):
                problems.append("colour must be a list of three whole numbers from 0 to 255")
            elif tools.get("name_and_colour"):
                d["colour"] = c
            else:
                locked.append("colour")
        m = new.get("model")
        if m != d.get("model"):
            if m is not None and m not in self.rules.get("house", {}):
                problems.append(f"model must be one of: {', '.join(self.rules.get('house', {}))}")
            elif tools.get("house_robots"):
                if m:
                    d["model"] = m
                    new["weapon"] = d["weapon"] = self.rules["house"][m]
                else:
                    d.pop("model", None)
                    if d["weapon"] not in self.rules["weapons"]:
                        d["weapon"] = new["weapon"] = "wedge"
            else:
                locked.append("model")
        w = new.get("weapon", d["weapon"])
        if w != d["weapon"] and not d.get("model"):
            if w not in self.rules["weapons"]:
                problems.append(f"weapon must be one of: {', '.join(self.rules['weapons'])}")
            elif tools.get("choose_weapon") and w in tools.get("weapons", []):
                d["weapon"] = w
            else:
                locked.append("weapon")
        for group, allowed in (("points", lambda k: tools.get("points_table")), ("settings", lambda k: tools.get(k))):
            values = new.get(group, {})
            if not isinstance(values, dict):
                problems.append(f"{group} must be a dictionary")
                continue
            for k, v in values.items():
                if k not in d[group]:
                    problems.append(f"'{k}' isn't one of the {group}")
                elif not isinstance(v, (int, float)) or isinstance(v, bool):
                    problems.append(f"{k} must be a number")
                elif v != d[group][k]:
                    if allowed(k):
                        d[group][k] = int(v) if group == "points" and v == int(v) else v
                    else:
                        locked.append(k)
        problems += sim.check_design(d)
        if problems:
            self.code_msg = ("Applied, but: " + "; ".join(problems[:3]), ORANGE)
        elif locked:
            self.code_msg = ("Applied. Not changeable this lesson: " + ", ".join(locked), ORANGE)
        else:
            self.code_msg = ("Applied: the garage shows your changes. Press BUILD to use them.", GREEN)
        self.code_shown = None
        for i in range(40):
            self.entry_text.pop(f"code_{i}", None)
        self.rebuild_panels()

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
            if y < -0.75:
                label(f, "...", 0.84, y, 0.026, GREY)
                break
            label(f, day["date"], 0.84, y, 0.028, WHITE)
            y -= 0.038
            for m in day["missions"]:
                if y < -0.75:
                    break
                label(f, f"Lesson {m['lesson']}: {m['title']}", 0.88, y, 0.025, GREY)
                label(f, " ".join(m["outcomes"]), 1.74, y, 0.022, BLUE, TextNode.ARight)
                y -= 0.034
            y -= 0.012
        if not card["history"]:
            label(f, "Nothing yet.", 0.84, y, 0.026, GREY)

    def build_missions(self, f, y, m=None, preview=False):
        m = m or self.missions
        self.top_speed_text = None
        if not m:
            label(f, "Waiting for missions...", 0.82, y, 0.03, GREY)
            return
        label(f, f"LESSON {m['lesson']}: {m['title']}", 0.82, y, 0.034, YELLOW, wrap=26)
        y -= 0.1
        for mm in m["missions"]:
            tick = "DONE" if mm["done"] else ("TEACHER" if mm["check"] == "teacher" else "TO DO")
            label(f, f"[{tick}]  {mm['title']}", 0.82, y, 0.03, GREEN if mm["done"] else WHITE)
            label(f, " ".join(mm["outcomes"]), 1.74, y, 0.022, BLUE, TextNode.ARight)
            y -= 0.04
            text = mm["detail"] if mm["done"] else mm["text"]
            label(f, text, 0.84, y, 0.024, GREY, wrap=36)
            y -= 0.035 * max(1, len(text) // 55 + 1)
            if preview:  # the teacher sees what the learner typed, not boxes to type in
                typed = m["prediction"] if mm["id"] == "1b" else m["text"].get(mm["id"])
                if typed and not mm["done"]:
                    label(f, f"They wrote: {typed}", 0.86, y, 0.022, BLUE, wrap=38)
                    y -= 0.045
                y -= 0.015
                continue
            if mm["id"] == "1b" and not mm["done"]:
                label(f, "Prediction (km/h)", 0.84, y, 0.026)
                self.entry(f, "prediction", 1.12, y, 5, initial=str(m["prediction"] or ""))
                button(f, "Save", 1.36, y + 0.008, self.save_prediction, None, 0.026)
                self.top_speed_text = label(f, f"fastest so far {m['top_speed']:.1f} km/h", 1.45, y, 0.024, GREY)
                y -= 0.06
            if mm["id"] in ("2d", "5b") and not mm["done"]:
                self.entry(f, f"reflect_{mm['id']}", 0.84, y, 30, 2, initial=m["text"].get(mm["id"], ""), scale=0.026)
                button(f, "Save", 1.66, y - 0.02, self.save_reflection, [mm["id"]], 0.026)
                y -= 0.09
            y -= 0.015
        if m["lesson"] >= 3:
            status = ("autopilot ON" if m["autopilot"] else "uploaded (press P for autopilot)") if m["brain"] \
                else "not uploaded yet (edit brains/my_brain.py, then press U)"
            label(f, f"Brain: {status}", 0.82, max(y, -0.8), 0.026, GREEN if m["brain"] else GREY)
            if m.get("brain_error"):
                label(f, f"Brain stopped: {m['brain_error']}", 0.82, max(y, -0.8) - 0.045, 0.024, RED, wrap=38)

    def save_prediction(self):
        send({"type": "prediction", "value": self.entries["prediction"].get()})

    def save_reflection(self, mission):
        send({"type": "reflection", "mission": mission, "text": self.entries[f"reflect_{mission}"].get()})

    def upload_brain(self):
        for path in (os.path.join(BRAINS, f"{name}.py"), os.path.join(BRAINS, "my_brain.py")):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    send({"type": "brain", "source": fh.read()})
                self.banner_note(f"Uploading {os.path.basename(path)}...")
                return
        self.banner_note("No brain file: make brains/my_brain.py first")

    def banner_note(self, text, secs=3):
        self.note_until = time.perf_counter() + secs
        self.note_text = text

    # ---------- AI request card (learner) ----------
    def build_ai_card(self, f, y):
        label(f, "AI REQUEST CARD", 0.82, y, 0.04, YELLOW)
        y -= 0.055
        label(f, AI_RULES, 0.82, y, 0.023, BLUE, wrap=42)
        y -= 0.12
        label(f, "What should change?", 0.82, y, 0.027)
        for i, (key, text) in enumerate(lm.AI_TARGETS.items()):
            if key == "game":
                continue
            button(f, text, 1.12 + i * 0.2, y + 0.008, self.set_card_target, [key], 0.025,
                   ON if key == self.card_target else OFF)
        y -= 0.07
        for key, text in (("goal", "My idea in one sentence"), ("variables", "Variables and values it needs"),
                          ("test", "How I will test it"), ("predict", "What I predict will happen")):
            label(f, text, 0.82, y, 0.027)
            self.entry(f, f"card_{key}", 0.84, y - 0.045, 30, 1, scale=0.026)
            y -= 0.1
        for key, text in (("privacy", "No personal information (names, school, email, address)"),
                          ("review", "I will review and test the AI's code"),
                          ("credit", "I will say where AI helped")):
            check(f, text, 0.84, y, self.card_checks[key], lambda v, k=key: self.card_checks.__setitem__(k, bool(v)), 0.026)
            y -= 0.045
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
        label(f, "Lesson", 0.82, y, 0.032, YELLOW)
        for n in range(1, 6):
            button(f, str(n), 1.0 + (n - 1) * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.03,
                   ON if L.get("lesson_number") == n else OFF)
        button(f, "Save settings", 1.6, y + 0.008, send, [{"type": "save_lesson"}], 0.026)
        y -= 0.065
        label(f, "Match", 0.82, y, 0.03, YELLOW)
        for i, mode in enumerate(("practice", "battle")):
            button(f, mode.title(), 1.04 + i * 0.19, y + 0.008, self.set_lesson, [{"mode": mode}], 0.03,
                   ON if L["mode"] == mode else OFF)
        button(f, "Restart", 1.44, y + 0.008, send, [{"type": "restart"}], 0.03)
        button(f, "Pause", 1.63, y + 0.008, send, [{"type": "pause"}], 0.03)
        y -= 0.06
        label(f, f"Battle {L['time_limit']} s", 0.82, y, 0.028)
        button(f, "-30", 1.08, y + 0.008, self.set_lesson, [{"time_limit": L["time_limit"] - 30}], 0.026)
        button(f, "+30", 1.18, y + 0.008, self.set_lesson, [{"time_limit": L["time_limit"] + 30}], 0.026)
        label(f, f"Computer robots {L['cpu_robots']}", 1.28, y, 0.028)
        button(f, "-", 1.6, y + 0.008, self.set_lesson, [{"cpu_robots": L["cpu_robots"] - 1}], 0.026)
        button(f, "+", 1.67, y + 0.008, self.set_lesson, [{"cpu_robots": L["cpu_robots"] + 1}], 0.026)
        y -= 0.05
        level = L.get("cpu_level", "medium")
        label(f, "Computer level", 0.84, y, 0.026)
        for i, (key, text) in enumerate(cpu_brains.LEVELS.items()):
            button(f, text, 1.1 + i * 0.13, y + 0.008, self.set_lesson, [{"cpu_level": key}], 0.022,
                   ON if level == key else OFF)
        if level == "empty":
            button(f, "Upload demo brain", 1.64, y + 0.008, self.upload_demo_brain, None, 0.02, (0.15, 0.45, 0.65, 1))
        y -= 0.055
        check(f, "My robot in the arena", 0.84, y, L["teacher_robot"], lambda v: self.set_lesson({"teacher_robot": bool(v)}),
              0.028)
        check(f, "Lock designs", 1.24, y, L["designs_locked"], lambda v: self.set_lesson({"designs_locked": bool(v)}), 0.028)
        check(f, "Real damage", 1.5, y, L.get("real_damage"), lambda v: self.set_lesson({"real_damage": bool(v)}), 0.028)
        y -= 0.07
        label(f, "Arena  (on = working, off = resting flush and safe)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        hazards = [h for h in HAZARD_NAMES if h != "house_robots"]
        for i, hz in enumerate(hazards):
            check(f, HAZARD_NAMES[hz], 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.046, L["hazards"].get(hz),
                  lambda v, hz=hz: self.set_lesson({"hazards": {hz: bool(v)}}))
        y -= 0.046 * ((len(hazards) + 1) // 2)
        on = sim.house_list(L["hazards"].get("house_robots"))
        label(f, "House robots", 0.84, y, 0.028)
        for i, (hr, w) in enumerate(self.rules.get("house", {}).items()):
            check(f, "  " + hr, 1.08 + i * 0.17, y + 0.005, hr in on, lambda v, hr=hr: self.toggle_house(hr, bool(v)), 0.024)
        y -= 0.06
        label(f, "User mods  (learners' ideas: on or off at any time)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        mods_on = L.get("user_mods", {})
        for i, (key, (mod_name, _)) in enumerate(sim.USER_MODS.items()):
            check(f, " " + mod_name, 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.046, mods_on.get(key),
                  lambda v, k=key: self.set_lesson({"user_mods": {k: bool(v)}}), 0.026)
        y -= 0.046 * ((len(sim.USER_MODS) + 1) // 2) + 0.02
        snd = rw_sound.sound_settings(L.get("sound"))
        label(f, "Sound  (mix any of these: each has its own volume)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        label(f, "Music", 0.84, y, 0.026)
        for i, (key, text) in enumerate(rw_sound.MUSIC.items()):
            button(f, text, 1.0 + i * 0.13, y + 0.008, self.set_lesson, [{"sound": {"music": key}}], 0.022,
                   ON if snd["music"] == key else OFF)
        self.volume_row(f, y, "music_volume", snd)
        y -= 0.046
        for key, text in (("crowd", "Crowd"), ("arena", "Arena hum"), ("weapons", "Weapons and motors"),
                          ("effects", "Hit sounds")):
            check(f, " " + text, 0.84, y, snd[key], lambda v, k=key: self.set_lesson({"sound": {k: bool(v)}}), 0.026)
            self.volume_row(f, y, {"crowd": "crowd_volume", "arena": "arena_volume", "effects": "volume",
                                   "weapons": "weapons_volume"}[key], snd)
            y -= 0.046
        y -= 0.02
        label(f, "Learners can see and change  (or use the Learners tab)", 0.82, y, 0.03, YELLOW)
        y -= 0.05
        keys = ["points_table", "forward_speed", "reverse_speed", "turn_speed", "acceleration", "size",
                "name_and_colour", "choose_weapon", "code_view", "stats_readout", "weapon_toggle", "house_robots"]
        for i, k in enumerate(keys):
            check(f, PRETTY[k], 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.046, L["tools"][k],
                  lambda v, k=k: self.set_lesson({"tools": {k: bool(v)}}))
        y -= 0.046 * ((len(keys) + 1) // 2) + 0.02
        label(f, "Weapons allowed", 0.82, y, 0.028)
        for i, w in enumerate(self.rules["weapons"]):
            button(f, w, 1.1 + i * 0.165, y + 0.008, self.toggle_weapon_allowed, [w], 0.026,
                   ON if w in L["tools"]["weapons"] else OFF)
        y -= 0.065
        self.restart_row(f, y)

    def restart_row(self, f, y):
        """Code changes (from Claude, or rolled back) load when the server and windows restart."""
        label(f, "Code changes" + ("  (waiting: restart to use them)" if self.needs_restart else ""), 0.82, y, 0.028,
              ORANGE if self.needs_restart else YELLOW)
        y -= 0.055
        button(f, "Restart server", 0.95, y, self.restart_server, None, 0.026,
               (0.6, 0.35, 0.1, 1) if self.needs_restart else OFF)
        button(f, "Reopen learners' windows", 1.25, y, send, [{"type": "restart_clients"}], 0.026)
        button(f, "Reopen mine", 1.6, y, self.restart_window, None, 0.026)

    def restart_server(self):
        self.needs_restart = False
        send({"type": "restart_server"})

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
        button(f, "-", 1.66, y + 0.008, self.set_lesson, [{"sound": {key: round(snd[key] - 0.1, 2)}}], 0.022)
        button(f, "+", 1.72, y + 0.008, self.set_lesson, [{"sound": {key: round(snd[key] + 0.1, 2)}}], 0.022)

    def set_lesson(self, change):
        send({"type": "lesson", "lesson": change})

    def toggle_weapon_allowed(self, w):
        allowed = list(self.lesson["tools"]["weapons"])
        if w in allowed and len(allowed) > 1:
            allowed.remove(w)
        elif w not in allowed:
            allowed.append(w)
        self.set_lesson({"tools": {"weapons": allowed}})

    # ---------- teacher: the learner view ----------
    def build_learner_view(self, f, y):
        learners = [c["name"] for c in self.class_list if c["role"] == "learner"]
        label(f, "LEARNER VIEW  -  see and change what a learner sees", 0.82, y, 0.03, YELLOW)
        y -= 0.06
        if not learners:
            label(f, "No learners are connected yet.", 0.82, y, 0.028, GREY)
            return
        if self.view_name not in learners:
            self.set_view(learners[0], redraw=False)
        for i, n in enumerate(learners):
            button(f, n, 0.9 + i * 0.2, y + 0.008, self.set_view, [n], 0.028, ON if n == self.view_name else OFF)
        y -= 0.065
        for i, (t, text) in enumerate((("garage", "Garage"), ("missions", "Missions"), ("ai", "AI card"),
                                      ("login", "Login"))):
            button(f, text, 0.9 + i * 0.2, y + 0.008, self.set_view_tab, [t], 0.026, ON if t == self.view_tab else OFF)
        y -= 0.07
        who = self.view_name
        if self.view_tab == "garage":
            self.build_garage(f, y, view=who)
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
            self.download_button = button(self.aspect2d, "Download the new Robot Lab", 1.2, 0.86,
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

    def build_outcomes(self, f, y):
        t = self.teaching
        if getattr(self, "outcome_view", None):
            return self.build_outcome_piece(f, y, self.outcome_view)
        label(f, "LEARNING OUTCOMES  -  evidence so far", 0.82, y, 0.034, YELLOW)
        if not t:
            return
        n_ = getattr(self, "guide_lesson", None) or t["lesson"]
        y -= 0.06
        label(f, "Lesson", 0.82, y, 0.028, YELLOW)
        for n in lm.LESSONS:
            button(f, str(n), 1.0 + (n - 1) * 0.08, y + 0.008, self.show_outcome, [None, n], 0.028,
                   ON if n == n_ else OFF)
        label(f, "(the class is on lesson %d)" % t["lesson"], 1.42, y, 0.022, GREY)
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
        label(f, "Taught in lesson", 0.82, y - 0.01, 0.028, GREY)
        for i, n in enumerate(taught_in):
            button(f, str(n), 1.12 + i * 0.08, y - 0.002, self.show_outcome, [code_, n], 0.028, ON if n == n_ else OFF)
        y -= 0.065
        label(f, f"LESSON {n_}: {lm.LESSONS[n_]['title']}", 0.82, y, 0.03, YELLOW, wrap=30)
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
        label(f, "Missions that give evidence", 0.82, y, 0.029, YELLOW)
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
        label(f, "AI REQUEST CARDS", 0.82, y, 0.036, YELLOW)
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
            label(f, c["card"]["goal"], 0.84, y, 0.022, GREY, wrap=44)
            y -= 0.05
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
                    label(f, "Kept on this laptop. For the online class: Make my changes live.bat (then Restart\n"
                             "server). A user mod then appears in Controls, ready to switch on.", 0.84, y, 0.022, ORANGE)
                    y -= 0.05
            elif c["status"] in ("waiting", "sent", "working"):
                y = self.card_targets_row(f, y, c, target)
                button(f, "Send to Claude", 0.95, y, self.ai_send, [c], 0.026, (0.15, 0.45, 0.65, 1))
                button(f, "Copy prompt", 1.2, y, self.copy_prompt, [c], 0.026)
                button(f, "Reject", 1.42, y, self.card_status, [c["id"], "rejected"], 0.026)
                y -= 0.07
            y -= 0.02
            if y < -0.8:
                break

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
        if target:
            self.card_targets[c["id"]] = target
        self.ai_jobs.pop(c["id"], None)
        self.ai_send(c)

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
        target = self.card_targets.get(c["id"], c["card"].get("target", "robot"))
        try:
            files = ai_pipeline.allowed_files(target, c["learner"])
        except ValueError as e:
            self.banner_note(str(e), 5)
            return
        text = ai_pipeline.build_prompt(c["card"], c["learner"], target, files)  # the same prompt Send uses
        os.makedirs(os.path.join(HERE, "ai_requests"), exist_ok=True)
        path = os.path.join(HERE, "ai_requests", f"{c['id']:03d}_{c['learner']}_prompt.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
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
        self.cam.update(dt, mine.chassis if me_alive else None, mine.front if mine else 0.8, targets,
                        self.fx.shake_offset() * 0.5)
        snd = rw_sound.sound_settings(self.lesson.get("sound"))
        if self.muted:
            self.snd.layers("off", 0, False, 0, False, 0)
        else:
            self.snd.layers(snd["music"], snd["music_volume"], snd["crowd"], snd["crowd_volume"], snd["arena"],
                            snd["arena_volume"])
        if self.newer and self.download_button is None:  # a newer release is out on GitHub
            self.banner_note(f"Robot Lab {self.newer} is out: press the green button to download it", 8)
            self.offer_download()
        if self.pending_rebuild and not self.typing:  # typing stopped: now do the redraw that waited
            self.rebuild_panels()
        self.view_text.setText(f"view: {self.cam.name}  (V to change, wheel or +/- to zoom)" +
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
                self.state = m
                self.fx_waiting.append(m.get("fx", {}))
            elif kind == "roster":
                self.apply_roster(m)
            elif kind == "welcome":  # back after a dropped connection (or a server restart)
                self.reconnecting = False
                if self.check_code(m):
                    return
                self.lesson, self.rules, self.design = m["lesson"], m["rules"], m["design"]
                self.draft = copy.deepcopy(self.design)
                self.banner_note("Reconnected: carry on!", 3)
                self.code_shown = None
                rebuild = True
            elif kind == "lesson":
                if m["lesson"] != self.lesson or (TEACHER and m["class"] != self.class_list):
                    rebuild = rebuild or self.tab in ("garage", "teacher", "learners")
                self.lesson, self.class_list = m["lesson"], m["class"]
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
                    if m.get("by_teacher"):
                        self.banner_note("Your teacher changed your robot", 4)
                else:
                    self.status_msg = ("Not built: " + "; ".join(m["problems"]), RED)
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
                self.banner_note(m["text"], 5)
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

    def apply_roster(self, m):
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
                rv.set_label(f"{r['design']['name']}\nHouse robot", (1, 0.75, 0.3, 1))
            else:
                rv.set_label(f"{r['design']['name']}\n{r['owner']}")
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
            control = ((down(KeyboardButton.up()) - down(KeyboardButton.down())) * 1.0,
                       (down(KeyboardButton.left()) - down(KeyboardButton.right())) * 1.0,
                       bool(down(KeyboardButton.space())))
        if control != self.last_control or now - self.last_send > 0.25:
            send({"type": "control", "throttle": control[0], "steer": control[1], "fire": control[2]})
            self.last_control, self.last_send = control, now

    def hit_sound(self, pos, dmg, kind, now):
        """The sound of a contact (quieter further from the camera), and the crowd's reaction to it."""
        snd = rw_sound.sound_settings(self.lesson.get("sound"))
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
        """Looping and firing sounds. Hit sounds: a floor saw grinding armour. Weapons and motors: each spinner's
        motor (its pitch follows its real speed), flame throwers, chainsaws, flippers firing, hammers swinging,
        and your own drive motor."""
        snd = rw_sound.sound_settings(self.lesson.get("sound"))
        hits = 0.0 if (self.muted or not snd["effects"]) else snd["volume"]
        vol = 0.0 if (self.muted or not snd["weapons"]) else snd["weapons_volume"]
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
        if vol and mine:
            self.snd.loop("motor", "motor", (0.04 + min(0.25, abs(mine["speed"]) / 20)) * vol, 0.6 + abs(mine["speed"]) / 8)
        else:
            self.snd.stop("motor")
        for s in st["robots"]:  # a knockout gets a cheer, the end of a battle gets applause
            if s["ko"] and not self.was_ko.get(s["id"]):
                self.snd.react("cheer", now)
            self.was_ko[s["id"]] = s["ko"]
        if st["winner"] and st["winner"] != self.last_winner:
            self.snd.react("applause", now)
        self.last_winner = st["winner"]

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
        for s in sorted(st["robots"], key=lambda s: s["id"] in self.house):  # (the house robots' bars go last)
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
        lesson = f"L{self.lesson.get('lesson_number', 1)}  "
        if st["practice"]:
            self.mode_text.setText(lesson + "PRACTICE (no damage)")
        else:
            left = st["time_left"] or 0
            self.mode_text.setText(lesson + f"BATTLE   {int(left) // 60}:{int(left) % 60:02d}")
        self.status_text.setText(f"{self.clock.getAverageFrameRate():.0f} fps   ping {self.ping_ms:.0f} ms")
        self.feed.setText("\n".join(st["events"]))
        if now < getattr(self, "note_until", 0):
            self.banner.setText(self.note_text)
            self.banner.setScale(0.045)
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
