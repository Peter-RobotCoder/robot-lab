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

import fight_version  # (first: this records the code this window is running, before anything can change it)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="", help="username (learners are asked in the window if it's left out)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--host", default=None,
                help="server address (default: this computer); 'class' = the one in teacher_settings.json")
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
BRAINS = os.path.join(os.path.dirname(sys.executable), "brains", "fightlab") if fight_version.FROZEN else os.path.join(HERE, "brains")  # (Club Coders: each game has its own brains folder)


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
    args.host = load_json(TEACHER_SETTINGS).get("server") or fight_version.ONLINE_SERVER or fight_version.LOCAL_SERVER
elif args.host is None:  # a learner's last choice on the login screen, or this computer
    where = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("where")
    args.host = {"local": fight_version.LOCAL_SERVER, "online": fight_version.ONLINE_SERVER}.get(
        where if not TEACHER else None) or fight_version.SERVER
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))  # a laptop test server
import try_local  # noqa: E402
# Try it on this laptop (see try_local): the teacher's window, opened on a test server here to look at this
# laptop's game before it is made live for the class. It knows how to go back to the class.
TRY = try_local.unpack(os.environ.pop("FIGHTLAB_TRY", "")) if args.teacher and LOCAL else None
import club_ticket  # noqa: E402
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
if TRY:
    title += " - TRYING ON THIS LAPTOP"
x = args.x if args.x is not None else (40 if TEACHER else 1360)
loadPrcFileData("", f"win-size 1280 720\nwindow-title {title}\nframebuffer-multisample 1\nmultisamples 4\n"
                    f"win-origin {x} 80\n")
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import (DGG, DirectButton, DirectCheckButton, DirectEntry, DirectFrame,  # noqa: E402
                                  DirectSlider)
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, Point3, TextNode, Vec3, WindowProperties  # noqa: E402

import cpu_brains  # noqa: E402
import fight_fx  # noqa: E402
import fight_gfx  # noqa: E402
import fight_missions as fm  # noqa: E402
import fight_sim as sim  # noqa: E402
import fight_sound  # noqa: E402
import rw_sound  # noqa: E402
from fight_camera import FightCamera  # noqa: E402
import fight_model  # noqa: E402
from fight_gfx import StageVisual  # noqa: E402
from fight_hud import FightHUD  # noqa: E402
from net import Net  # noqa: E402

YELLOW, WHITE, GREY, RED, GREEN = (1, .9, .35, 1), (1, 1, 1, 1), (.75, .8, .9, 1), (1, .45, .4, 1), (.5, .95, .55, 1)
BLUE, ORANGE = (.55, .85, 1, 1), (1, .7, .3, 1)
PANEL = (0.04, 0.05, 0.08, 0.88)
ON, OFF = (0.85, 0.65, 0.1, 1), (0.2, 0.25, 0.35, 1)
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
          "bosses": "Play as a boss", "fighting_style": "Fighting style"}
HAZARD_NAMES = {"ring_out": "Ring-outs (no ropes)", "electric_ropes": "Electric ropes", "fire_jets": "Fire jets",
                "slippery": "Slippery ice", "spikes": "Spikes"}
LEARNER_TABS = [("missions", "Missions (M)"), ("garage", "Garage (G)"), ("ai", "AI card (I)"), ("card", "My card (K)")]
TEACHER_TABS = [("teacher", "Controls"), ("matches", "Matches"), ("learners", "Learners"), ("accounts", "Accounts"),
                ("outcomes", "Outcomes"), ("cards", "AI cards"), ("changes", "Changes"), ("garage", "My fighter")]
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
ATTACK_ANIMS = {"punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam",
                "cartwheel"}


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
        global APP
        APP = self
        fight_gfx.init(self, args.gfx)
        self.fx = fight_fx.Effects(self.render, args.gfx)
        self.snd = fight_sound.FightSounds(self, on=not args.offscreen)
        self.muted = False
        self.entries, self.entry_text = {}, {}   # text boxes, and what was typed in them
        self.typing = None           # the text box being typed in (game keys are ignored while typing)
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
        props.setTitle(f"Fight Lab - {'TEACHER' if TEACHER else 'LEARNER'} ({name})")
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
        self.card_target = "fighter"
        self.ai_jobs = {}        # teacher: card id -> {"status", "result", "change"}
        self.card_targets = {}   # teacher: card id -> what Claude may change (can differ from the learner's choice)
        self.card_user_mod = {}  # teacher: card id -> make a whole-game change as a switchable user mod
        self.view_name, self.view_tab = None, "garage"   # teacher's learner view
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
        self.state, self.ping_ms, self.status_msg = None, 0.0, ("", WHITE)
        self.fx_waiting = []
        self.reconnect_thread = None
        self.last_anim, self.last_phase, self.last_winner = {}, {}, {}  # (for sounds)
        self.last_send = self.last_ping = 0.0
        self.last_control = None
        self.panel = self.code_panel = None
        self.tab = args.tab or ("teacher" if TEACHER else "missions")
        self.show_code = False
        self.reconnecting = False
        self.restore_prefs(welcome.get("prefs", {}))
        for key, action in PRESS_KEYS.items():  # fighting keys: sent the moment they're pressed
            self.key(key, self.press, action)
        self.key("g", self.open_tab, "garage")
        self.key("c", self.toggle_code)
        self.key("h", self.toggle_help)
        self.key("u", self.upload_brain)
        self.key("p", send, {"type": "autopilot"})
        self.key("v", self.cam.cycle)
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
        self.try_starting = None  # (teacher: a test server on this laptop is starting: see try_here)
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
        if args.selftest:  # press some garage buttons the way a learner would, then build
            self.taskMgr.doMethodLater(2, lambda t: [self.change_points("speed", 5), self.change_points("defence", -5),
                                                     self.set_colour([60, 190, 90])] and None, "t1")
            self.taskMgr.doMethodLater(2.5, lambda t: self.send_design(), "t2")

    def restore_prefs(self, prefs):
        """A learner's camera view and half-typed AI card, from their profile."""
        self.cam.restore(prefs.get("camera", {}))
        for k in CARD_FIELDS:
            if prefs.get("card", {}).get(k):
                self.entry_text[f"card_{k}"] = str(prefs["card"][k])[:400]
        if prefs.get("card_target") in fm.AI_TARGETS and prefs["card_target"] != "game":
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
                "X crouch  " + ("T panels  " if TEACHER else "M missions  I AI card  ") +
                "G garage  C code  U brain  P autopilot  V view  Q/E or right-drag turn  H help")
        self.help = label(self.aspect2d, keys, -1.74, -0.975, 0.021, GREY)
        self.layout_rings()

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
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        program = [sys.executable] if fight_version.FROZEN else [sys.executable, os.path.abspath(__file__)]
        log_dir = SETTINGS_DIR if fight_version.FROZEN else HERE
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "window.log"), "a") as log:
            subprocess.Popen(program + argv, cwd=os.getcwd() if fight_version.FROZEN else HERE, env=env,
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
        """Redraw the side panels. A redraw caused by the game (a new round, new mission results)
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
                       0.022 if TEACHER else 0.03, ON if key == self.tab else OFF)
            {"garage": self.build_garage, "teacher": self.build_teacher_panel, "missions": self.build_missions,
             "ai": self.build_ai_card, "outcomes": self.build_outcomes, "cards": self.build_cards,
             "card": self.build_card,
             "learners": self.build_learner_view, "changes": self.build_changes,
             "accounts": self.build_accounts, "matches": self.build_matches}[self.tab](f, 0.84)
        if self.show_code and (TEACHER or self.lesson["tools"]["code_view"]):
            self.build_code_panel()
        if self.typing and self.typing not in self.entries:  # the box being typed in has gone
            self.typing = None
        self.fight_hud.place(-0.5 if self.tab else 0.0)
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
                self.view_drafts[who] = copy.deepcopy(d)
            return self.view_drafts[who]
        return self.draft

    def tools(self):
        if TEACHER:
            return {k: True for k in self.lesson["tools"]} | {"specials": list(self.rules["specials"])}
        return self.lesson["tools"]

    # ---------- garage: design your fighter ----------
    def build_garage(self, f, y, view=None):
        """view: the teacher's Learner view of this learner. The teacher sees every control, with a tick box
        on each showing (and setting) whether the learner can see and change it."""
        tools, d = self.tools(), self.cur()
        seen = self.lesson["tools"]

        def shown_box(tool, yy):
            if view:
                check(f, " learner sees", 1.52, yy, seen.get(tool), lambda v, t=tool: self.set_lesson({"tools": {t: bool(v)}}),
                      0.022)
        label(f, f"{view.upper()}'S FIGHTER (what they see and change)" if view else
              ("MY FIGHTER" if TEACHER else "GARAGE  -  design your fighter"), 0.82, y, 0.034 if view else 0.04, YELLOW)
        y -= 0.065
        if tools.get("name_and_colour"):
            label(f, "Name", 0.82, y, 0.028)
            self.entry(f, self.name_key(), 0.97, y, 10, initial=d["name"],
                       command=lambda t: self.cur().__setitem__("name", t[:16]))
            shown_box("name_and_colour", y)
            y -= 0.055
            for i, c in enumerate(SWATCHES):
                big = 0.95 if list(c) == list(d["colour"]) else 0.6
                DirectButton(parent=f, text="", scale=0.03, pos=(0.84 + i * 0.085, 0, y), relief=DGG.FLAT,
                             frameColor=(*(v / 255 for v in c), 1), frameSize=(-0.9, 0.9, -big, big),
                             command=self.set_colour, extraArgs=[list(c)])
            if list(d["colour"]) not in [list(c) for c in SWATCHES]:  # a colour typed in the code
                DirectFrame(parent=f, frameColor=(*(v / 255 for v in d["colour"]), 1), frameSize=(-0.027, 0.027, -0.028, 0.028),
                            pos=(0.84 + len(SWATCHES) * 0.085, 0, y))
            y -= 0.06
        model = d.get("model")
        if tools.get("body_choice") and not model:
            label(f, "Body", 0.82, y, 0.028)
            for i, b in enumerate(self.rules["bodies"]):
                button(f, b, 1.02 + i * 0.14, y + 0.008, self.set_body, [b], 0.024, ON if b == d.get("body") else OFF)
            shown_box("body_choice", y)
            y -= 0.055
            if d.get("body") in self.rules.get("model_bodies", []):
                y = self.build_look(f, y, d)
        if tools.get("bosses") or model:
            label(f, "Fighter", 0.82, y, 0.028)
            if tools.get("bosses"):
                button(f, "Mine", 1.0, y + 0.008, self.set_model, [None], 0.022, OFF if model else ON)
                for i, b in enumerate(self.rules.get("bosses", {})):
                    button(f, b, 1.13 + i * 0.145, y + 0.008, self.set_model, [b], 0.022, ON if b == model else OFF)
                shown_box("bosses", y - 0.04)
            else:
                label(f, f"{model} (a boss, set by the teacher)", 1.0, y, 0.024, ORANGE)
            y -= 0.055 if not view else 0.075
        if model:
            label(f, f"Special: {self.rules['specials'].get(d['special'], d['special'])}", 0.82, y, 0.022, ORANGE, wrap=44)
            y -= 0.07
            label(f, "Bosses are big and strong (260 health) but slow.\n"
                     "Their stats are fixed, so points and settings aren't used.", 0.82, y, 0.022, GREY)
            y -= 0.09
        elif tools.get("choose_special"):
            label(f, "Special", 0.82, y, 0.028)
            for i, sp in enumerate(tools.get("specials", [])):
                button(f, sp.replace("_", " "), 1.03 + i * 0.16, y + 0.008, self.set_special, [sp], 0.023,
                       ON if sp == d["special"] else OFF)
            shown_box("choose_special", y - 0.04)
        else:
            label(f, f"Special: {d['special'].replace('_', ' ')}  (chosen by the teacher this lesson)", 0.82, y, 0.026, GREY)
        if not model:
            y -= 0.042
            label(f, self.rules["specials"].get(d["special"], ""), 0.82, y, 0.021, GREY, wrap=46)
            y -= 0.055 if not view else 0.07
        if not model and self.rules.get("styles"):
            y = self.build_style(f, y, d, tools.get("fighting_style"), shown_box)
        if tools.get("points_table") and not model:
            used = sum(d["points"].values())
            label(f, f"POINTS  ({used} of {self.rules['points_total']} used, {self.rules['points_total'] - used} left)",
                  0.82, y, 0.028, YELLOW if used <= self.rules["points_total"] else RED)
            shown_box("points_table", y)
            y -= 0.048
            for stat in self.rules["stats"]:
                v = d["points"][stat]
                label(f, stat.title(), 0.82, y, 0.027)
                for dx, delta, text in ((1.04, -5, "-5"), (1.12, -1, "-"), (1.26, 1, "+"), (1.34, 5, "+5")):
                    button(f, text, dx, y + 0.008, self.change_points, [stat, delta], 0.024)
                label(f, str(v), 1.19, y, 0.03, WHITE, TextNode.ACenter)
                DirectFrame(parent=f, frameColor=(0.2, 0.2, 0.22, 1), frameSize=(0, 0.3, 0, 0.018), pos=(1.42, 0, y))
                DirectFrame(parent=f, frameColor=(0.9, 0.7, 0.15, 1),
                            frameSize=(0, 0.3 * min(v, self.rules["stat_max"]) / self.rules["stat_max"], 0, 0.018),
                            pos=(1.42, 0, y))
                y -= 0.046
        if tools.get("combo_editor") and not model:
            combo = d.get("combo", [])
            label(f, f"COMBO  (a list: {self.rules['combo_min']} to {self.rules['combo_max']} moves, "
                     "press A again after each hit)", 0.82, y, 0.024, YELLOW)
            shown_box("combo_editor", y)
            y -= 0.05
            for i, mv in enumerate(combo):  # click a move to change it
                button(f, f"{i + 1}. {mv}", 0.9 + (i % 4) * 0.2, y + 0.008 - (i // 4) * 0.05, self.cycle_combo, [i], 0.023,
                       (0.3, 0.35, 0.5, 1))
            y -= 0.05 * (1 + (max(0, len(combo) - 1)) // 4)
            button(f, "+ add a move", 0.94, y + 0.008, self.combo_length, [1], 0.022)
            button(f, "- last move", 1.17, y + 0.008, self.combo_length, [-1], 0.022)
            y -= 0.05
        self.sliders = {}
        shown = [k for k in self.rules["settings"] if tools.get(k)] if not model else []
        if shown:
            label(f, "SETTINGS  (percent)", 0.82, y, 0.028, YELLOW)
            y -= 0.048
        for k in shown:
            lo, hi, _, _ = self.rules["settings"][k]
            label(f, PRETTY[k], 0.82, y, 0.026)
            s = DirectSlider(parent=f, range=(lo, hi), value=d["settings"][k], pageSize=5, scale=0.17 if view else 0.2,
                             pos=(1.24 if view else 1.3, 0, y + 0.008), command=self.slider_moved, extraArgs=[k],
                             thumb_frameSize=(-0.04, 0.04, -0.12, 0.12))
            self.sliders[k] = (s, label(f, f"{d['settings'][k]:.0f}%", 1.44 if view else 1.55, y, 0.026, WHITE))
            shown_box(k, y)
            y -= 0.046
        self.stats_text = None
        if tools.get("stats_readout") and not model:
            self.stats_text = label(f, "", 0.82, y - 0.005, 0.022, GREEN)
            self.update_stats_text()
            shown_box("stats_readout", y)
            y -= 0.13
        y = max(y, -0.8)
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

    # ---------- code view: your fighter as Python code, which you can edit ----------
    def code_lines(self, d):
        lines = ["FIGHTER = {", f'    "name": "{d["name"]}",        # text (a string)',
                 f'    "body": "{d.get("body", "robot")}",       # robot or human',
                 f'    "colour": [{d["colour"][0]}, {d["colour"][1]}, {d["colour"][2]}],  # red, green, blue: 0 to 255',
                 f'    "special": "{d["special"]}",']
        if self.rules.get("styles"):
            style, weapon = sim.style_of(d)
            lines.append(f'    "fighting_style": "{style}",  # {", ".join(self.rules["styles"])}')
            if weapon:
                others = [w for w, v in self.rules["weapons"].items() if v[0] == style]
                lines.append(f'    "weapon": "{weapon}",   # {", ".join(others)}')
        if d.get("model"):
            lines.append(f'    "model": "{d["model"]}",      # playing as a boss')
        lines += ['    "points": {                 # a dictionary: 100 points to share']
        lines += [f'        "{k}": {v},' for k, v in d["points"].items()]
        lines += ["    },", '    "settings": {               # percentages']
        lines += [f'        "{k}": {v:.0f},' for k, v in d["settings"].items()]
        lines += ["    },", f'    "combo": {json.dumps(d.get("combo", []))},  # a list of moves']
        if d.get("body") in self.rules.get("model_bodies", []):
            look = d.get("look") or sim.default_look(d["body"])
            lines += ['    "look": {                   # how the detailed body looks']
            lines += [f'        "{k}": {json.dumps(v)},' for k, v in look.items()]
            lines += ["    },"]
        if d.get("body") == "robin" or (d.get("style") and d.get("body") == "robot"):
            style = d.get("style") or {}
            lines += ['    "style": {                  # trim and light colours [red, green, blue], the chest number']
            lines += [f'        "{k}": {json.dumps(style.get(k, v))},' for k, v in
                      (("trim", sim.ROBIN_STYLE["trim"]), ("lights", sim.ROBIN_STYLE["lights"]), ("number", d["name"][:10]))]
            lines += ["    },"]
        lines += ["}",
                  f"# points used: {sum(d['points'].values())} of {self.rules['points_total']}"]
        return lines

    def build_code_panel(self):
        who = self.viewing()
        d = self.cur()
        f = self.code_panel = DirectFrame(frameColor=PANEL, frameSize=(-0.84, -0.02, -0.92, 0.42))
        label(f, f"{who.upper()}'S FIGHTER AS PYTHON CODE" if who else "YOUR FIGHTER AS PYTHON CODE", -0.8, 0.36, 0.03,
              YELLOW)
        label(f, "Change a value, then press Enter or APPLY: the garage changes to match.", -0.8, 0.32, 0.021, GREY)
        fresh = self.code_lines(d)
        typed = [self.entry_text.get(f"code_{i}") for i in range(len(self.code_shown or []))]
        edited = self.code_shown is not None and any(t is not None and t != s for t, s in zip(typed, self.code_shown))
        lines = [t if t is not None else s for t, s in zip(typed, self.code_shown)] if edited else fresh
        if not edited:
            for i in range(40):
                self.entry_text.pop(f"code_{i}", None)
        for i, line in enumerate(lines):
            self.entry(f, f"code_{i}", -0.81, 0.27 - i * 0.041, 35.5, initial=line, scale=0.021,
                       command=lambda t: self.apply_code())
        self.code_shown = lines
        yb = 0.27 - len(lines) * 0.041 - 0.03
        button(f, "APPLY CODE", -0.62, yb, self.apply_code, None, 0.03, (0.15, 0.55, 0.25, 1))
        button(f, "UNDO MY EDITS", -0.3, yb, self.reset_code, None, 0.03)
        label(f, self.code_msg[0], -0.8, yb - 0.06, 0.021, self.code_msg[1], wrap=37)

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
                     and [getattr(t, "id", None) for t in s.targets] == ["FIGHTER"]), None)
        if node is None:
            self.code_msg = ("The code needs FIGHTER = { ... }", RED)
            self.refresh_code_panel()
            return
        try:
            new = ast.literal_eval(node)
        except ValueError:
            self.code_msg = ("Only plain values are allowed: numbers, \"text\", [lists] and {dictionaries}.", RED)
            self.refresh_code_panel()
            return
        if not isinstance(new, dict):
            self.code_msg = ("FIGHTER must be a dictionary: { ... }", RED)
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
        b = new.get("body", d.get("body"))
        if b != d.get("body"):
            if b not in self.rules["bodies"]:
                problems.append(f"body must be one of: {', '.join(self.rules['bodies'])}")
            elif tools.get("body_choice"):
                d["body"] = b
            else:
                locked.append("body")
        m = new.get("model")
        if m != d.get("model"):
            if m is not None and m not in self.rules.get("bosses", {}):
                problems.append(f"model must be one of: {', '.join(self.rules.get('bosses', {}))}")
            elif tools.get("bosses"):
                if m:
                    d["model"] = m
                    new["special"] = d["special"] = self.rules["bosses"][m]
                else:
                    d.pop("model", None)
            else:
                locked.append("model")
        sp = new.get("special", d["special"])
        if sp != d["special"] and not d.get("model"):
            if sp not in self.rules["specials"]:
                problems.append(f"special must be one of: {', '.join(self.rules['specials'])}")
            elif tools.get("choose_special") and sp in tools.get("specials", []):
                d["special"] = sp
            else:
                locked.append("special")
        style, weapon = new.get("fighting_style", sim.style_of(d)[0]), new.get("weapon")
        if (style, weapon) != sim.style_of(d) and self.rules.get("styles"):
            weapons = [w for w, v in self.rules["weapons"].items() if v[0] == style]
            if style not in self.rules["styles"]:
                problems.append(f"fighting_style must be one of: {', '.join(self.rules['styles'])}")
            elif weapons and weapon not in weapons:
                problems.append(f"a {style} fighter's weapon must be one of: {', '.join(weapons)}")
            elif not weapons and weapon is not None:
                problems.append(f"a {style} fighter has no weapon (take the weapon line out)")
            elif tools.get("fighting_style"):
                d["fighting_style"] = style
                if weapon:
                    d["weapon"] = weapon
                else:
                    d.pop("weapon", None)
            else:
                locked.append("fighting_style")
        combo = new.get("combo", d.get("combo"))
        if combo != d.get("combo"):
            if not isinstance(combo, list) or not all(isinstance(mv, str) for mv in combo):
                problems.append("combo must be a list of moves in quotes, like [\"punch\", \"kick\"]")
            elif tools.get("combo_editor"):
                d["combo"] = combo[:12]
            else:
                locked.append("combo")
        if "style" in new and new["style"] != d.get("style"):
            st = new["style"]
            if not isinstance(st, dict):
                problems.append("style must be a dictionary")
            elif any(k in st and not (isinstance(st[k], list) and len(st[k]) == 3 and
                                      all(isinstance(v, int) and 0 <= v <= 255 for v in st[k])) for k in ("trim", "lights")):
                problems.append("style trim and lights must each be three whole numbers from 0 to 255")
            elif "number" in st and (not isinstance(st["number"], str) or len(st["number"]) > 10):
                problems.append("style number must be text, up to 10 characters")
            else:
                d["style"] = {k: v for k, v in st.items() if k in ("trim", "lights", "number")}
        if "look" in new and new["look"] != d.get("look") and d.get("body") in self.rules.get("model_bodies", []):
            if not tools.get("body_choice"):
                locked.append("look")
            elif not isinstance(new["look"], dict):
                problems.append("look must be a dictionary")
            else:
                problems += sim.check_look(d["body"], new["look"])
                d["look"] = new["look"]
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
        self.punch_text = None
        if not m:
            label(f, "Waiting for missions...", 0.82, y, 0.03, GREY)
            return
        label(f, f"LESSON {m['lesson']}: {m['title']}", 0.82, y, 0.032, YELLOW, wrap=28)
        y -= 0.1
        for mm in m["missions"]:
            tick = "DONE" if mm["done"] else ("TEACHER" if mm["check"] == "teacher" else "TO DO")
            label(f, f"[{tick}]  {mm['title']}", 0.82, y, 0.028, GREEN if mm["done"] else WHITE)
            label(f, " ".join(mm["outcomes"]), 1.74, y, 0.02, BLUE, TextNode.ARight)
            y -= 0.038
            text = mm["detail"] if mm["done"] else mm["text"]
            label(f, text, 0.84, y, 0.022, GREY, wrap=40)
            y -= 0.033 * max(1, len(text) // 60 + 1)
            if preview:  # the teacher sees what the learner typed, not boxes to type in
                typed = m["prediction"] if mm["id"] == "1b" else m["text"].get(mm["id"])
                if typed and not mm["done"]:
                    label(f, f"They wrote: {typed}", 0.86, y, 0.021, BLUE, wrap=40)
                    y -= 0.042
                y -= 0.012
                continue
            if mm["id"] == "1b" and not mm["done"]:
                label(f, "Punches to knock out", 0.84, y, 0.024)
                self.entry(f, "prediction", 1.16, y, 4, initial=str(m["prediction"] or ""))
                button(f, "Save", 1.36, y + 0.008, self.save_prediction, None, 0.024)
                self.punch_text = label(f, f"punches landed {m.get('punches', 0)}", 1.44, y, 0.022, GREY)
                y -= 0.055
            if mm["id"] in fm.REFLECTIONS and not mm["done"]:
                self.entry(f, f"reflect_{mm['id']}", 0.84, y, 30, 2, initial=m["text"].get(mm["id"], ""), scale=0.025)
                button(f, "Save", 1.66, y - 0.02, self.save_reflection, [mm["id"]], 0.024)
                y -= 0.085
            y -= 0.012
        if m["lesson"] >= 3:
            status = ("autopilot ON" if m["autopilot"] else "uploaded (press P for autopilot)") if m["brain"] \
                else "not uploaded yet (edit brains/my_brain.py, then press U)"
            label(f, f"Brain: {status}", 0.82, max(y, -0.8), 0.025, GREEN if m["brain"] else GREY)
            if m.get("brain_error"):
                label(f, f"Brain stopped: {m['brain_error']}", 0.82, max(y, -0.8) - 0.045, 0.022, RED, wrap=42)

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
        for i, (key, text) in enumerate(fm.AI_TARGETS.items()):
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
        label(f, "Lesson", 0.82, y, 0.03, YELLOW)
        for n in range(1, 6):
            button(f, str(n), 1.0 + (n - 1) * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.028,
                   ON if L.get("lesson_number") == n else OFF)
        button(f, "Save settings", 1.6, y + 0.008, send, [{"type": "save_lesson"}], 0.024)
        y -= 0.06
        label(f, "Fights", 0.82, y, 0.028, YELLOW)
        for i, mode in enumerate(("practice", "battle")):
            button(f, mode.title(), 1.04 + i * 0.19, y + 0.008, self.set_lesson, [{"mode": mode}], 0.028,
                   ON if L["mode"] == mode else OFF)
        button(f, "Restart", 1.44, y + 0.008, send, [{"type": "restart"}], 0.028)
        button(f, "Pause", 1.63, y + 0.008, send, [{"type": "pause"}], 0.028)
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
        snd = rw_sound.sound_settings(L.get("sound"))
        label(f, "Sound", 0.82, y, 0.028, YELLOW)
        for i, (key, text) in enumerate(rw_sound.MUSIC.items()):
            button(f, text, 1.0 + i * 0.13, y + 0.008, self.set_lesson, [{"sound": {"music": key}}], 0.021,
                   ON if snd["music"] == key else OFF)
        self.volume_row(f, y, "music_volume", snd)
        y -= 0.043
        for key, text in (("crowd", "Crowd"), ("effects", "Hits and moves")):
            check(f, " " + text, 0.84, y, snd[key], lambda v, k=key: self.set_lesson({"sound": {k: bool(v)}}), 0.024)
            self.volume_row(f, y, {"crowd": "crowd_volume", "effects": "volume"}[key], snd)
            y -= 0.043
        y -= 0.01
        label(f, "Learners can see and change  (or use the Learners tab)", 0.82, y, 0.026, YELLOW)
        y -= 0.045
        keys = ["points_table", "walk_speed", "sidestep_speed", "jump_height", "attack_speed", "size",
                "name_and_colour", "body_choice", "choose_special", "combo_editor", "code_view", "stats_readout", "bosses",
                "fighting_style"]
        for i, k in enumerate(keys):
            check(f, PRETTY[k], 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.041, L["tools"].get(k),
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
        button(f, "-", 1.66, y + 0.008, self.set_lesson, [{"sound": {key: round(snd[key] - 0.1, 2)}}], 0.021)
        button(f, "+", 1.72, y + 0.008, self.set_lesson, [{"sound": {key: round(snd[key] + 0.1, 2)}}], 0.021)

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

    def build_matches(self, f, y):
        L = self.lesson
        label(f, "MATCHES  -  who fights who", 0.82, y, 0.034, YELLOW)
        y -= 0.05
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
        label(f, "TOURNAMENT  (knockout: computer fighters fill the gaps)", 0.82, y, 0.028, YELLOW)
        y -= 0.06
        t = self.tournament
        if t is None:
            button(f, "Start a tournament", 1.1, y, send, [{"type": "tournament", "start": True}], 0.03,
                   (0.15, 0.55, 0.25, 1))
            label(f, "(it switches Battle on and locks designs)", 1.36, y - 0.005, 0.019, GREY)
            y -= 0.07
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
    def build_outcomes(self, f, y):
        t = self.teaching
        label(f, "LEARNING OUTCOMES  -  evidence so far", 0.82, y, 0.034, YELLOW)
        if not t:
            return
        y -= 0.06
        codes = list(t["outcomes"])
        learners = list(t["grid"])
        label(f, "Outcome", 0.82, y, 0.024, GREY)
        for j, n in enumerate(learners[:4]):
            label(f, n[:8], 1.28 + j * 0.12, y, 0.024, GREY, TextNode.ACenter)
        y -= 0.04
        for code_ in codes:
            label(f, t["outcomes"][code_][0], 0.82, y, 0.024, WHITE)
            for j, n in enumerate(learners[:4]):
                c = t["grid"][n]["outcomes"].get(code_, 0)
                label(f, str(c) if c else "-", 1.28 + j * 0.12, y, 0.026, GREEN if c else GREY, TextNode.ACenter)
            y -= 0.036
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
        label(f, "AI REQUEST CARDS", 0.82, y, 0.036, YELLOW)
        y -= 0.05
        label(f, "Choose what Claude may change, then Send to Claude. The whole game lets Claude change\n"
                 "anything (new moves, specials, hazards, rules, graphics). Every change is tested before you Keep it,\n"
                 "and kept changes can be rolled back later in the Changes tab.", 0.82, y, 0.02, GREY)
        y -= 0.1
        cards = [c for c in (self.teaching or {}).get("cards", []) if c["status"] not in ("reviewed", "rejected")][-4:]
        if not cards:
            label(f, "No requests waiting.", 0.82, y, 0.028, GREY)
        for c in cards:
            job = self.ai_jobs.get(c["id"], {})
            target = self.card_targets.get(c["id"], c["card"].get("target", "fighter"))
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
                button(f, "Send to Claude", 0.95, y, self.ai_send, [c], 0.026, (0.15, 0.45, 0.65, 1))
                button(f, "Copy prompt", 1.2, y, self.copy_prompt, [c], 0.026)
                button(f, "Reject", 1.42, y, self.card_status, [c["id"], "rejected"], 0.026)
                y -= 0.07
            y -= 0.02
            if y < -0.8:
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
        target = self.card_targets.get(c["id"], c["card"].get("target", "fighter"))
        try:
            files = ai_pipeline.allowed_files(target, c["learner"])
        except ValueError as e:
            self.banner_note(str(e), 5)
            return
        text = ai_pipeline.build_prompt(c["card"], c["learner"], target, files)  # the same prompt Send uses
        os.makedirs(os.path.join(HERE, "ai_requests"), exist_ok=True)
        path = os.path.join(HERE, "ai_requests", f"{c['id']:03d}_{ai_pipeline.slug(c['learner'])}_prompt.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
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
        self.set_watch(rings[(i + delta) % len(rings)])
        self.banner_note(f"Watching ring {self.watched_ring() + 1}" + ("  (yours)" if self.watched_ring() ==
                                                                       self.my_ring() else ""), 2)

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
        watched = self.watched_ring()
        ring = next((r for r in (self.state or {}).get("rings", []) if r["i"] == watched), None)
        if self.state and self.roster:
            self.draw_state(dt, now, ring)
        me = enemy = None
        if ring:
            fs = [f for f in ring["f"] if f["a"] != "ringout" or f["pos"][2] > -1.5]
            mine = next((f for f in fs if f["id"] == self.my_id), None)
            first = mine or (fs[0] if fs else None)
            other = next((f for f in fs if f is not first), None)
            me = Point3(*first["pos"]) if first else None
            enemy = Point3(*other["pos"]) if other else None
        centres = [tuple(r["c"]) for r in (self.state or {}).get("rings", [])]
        self.cam.update(dt, me, enemy, tuple(ring["c"]) if ring else (0.0, 0.0), centres, self.fx.shake_offset() * 0.5)
        self.fight_hud.update(ring, {k: v[:2] for k, v in self.names.items()}, self.my_id,
                              (self.state or {}).get("t", 0.0), dt, self.lesson.get("rounds_to_win", 2),
                              f"RING {watched + 1}" if watched is not None and watched != self.my_ring() else "")
        snd = rw_sound.sound_settings(self.lesson.get("sound"))
        if self.muted:
            self.snd.layers("off", 0, False, 0, False, 0)
        else:
            self.snd.layers(snd["music"], snd["music_volume"], snd["crowd"], snd["crowd_volume"], False, 0)
        if self.newer and self.download_button is None:  # a newer release is out
            self.banner_note(f"Club Coders {self.newer} is out: press the green button to download it", 8)
            self.offer_download()
        if self.pending_rebuild and not self.typing:  # typing stopped: now do the redraw that waited
            self.rebuild_panels()
        self.view_text.setText(f"view: {self.cam.name}  (V to change)" + ("   typing - Esc to stop" if self.typing else ""))
        self.banner.setText(self.note_text if now < getattr(self, "note_until", 0) else "")
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
                self.state = m
                self.fx_waiting.append(m.get("fx", []))
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
                if m["lesson"] != self.lesson or m.get("tournament") != self.tournament or \
                        (TEACHER and m["class"] != self.class_list):
                    rebuild = rebuild or self.tab in ("garage", "teacher", "learners", "matches")
                self.lesson, self.class_list, self.tournament = m["lesson"], m["class"], m.get("tournament")
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
                elif self.tab == "missions" and getattr(self, "punch_text", None):
                    self.punch_text.setText(f"punches landed {m.get('punches', 0)}")
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
        drawn = json.dumps([m.get("look", {}), m.get("rings"), m.get("hazards"), m.get("rs"), m.get("user_mods")],
                           sort_keys=True)
        if drawn != self.stage_drawn:
            if self.stage_vis:
                self.stage_vis.destroy()
            sim.RULES["ring_size"] = m.get("rs", sim.RULES["ring_size"])
            self.stage_vis = StageVisual(self.render, m["rings"], m["hazards"], m.get("look"), m.get("user_mods"))
            self.stage_drawn = drawn
        for fv in self.fighters.values():
            fv.destroy()
        self.fighters = {}
        for f in m["fighters"]:
            fv = fight_model.make(self.render, f["design"])
            boss = f["design"].get("model")
            fv.set_label(f"{f['design']['name']}\n{'Boss' if boss and f['owner'] == 'Computer' else f['owner']}",
                         (1, 0.75, 0.3, 1) if f["owner"] == "Computer" else (1, 1, 1, 1))
            self.fighters[f["id"]] = fv
        self.my_id = m["mine"].get(name)
        self.ring_of = {f["id"]: f["ring"] for f in m["fighters"]}
        self.names = {f["id"]: (f["design"]["name"], f["owner"], tuple(v / 255 for v in f["design"]["colour"]),
                                f["design"].get("body", "robot")) for f in m["fighters"]}

    # ---------- your controls ----------
    def press(self, action):
        """A fighting key was pressed: send it straight away (the server keeps it for a moment, so it isn't missed)."""
        self.pending_press = action
        self.send_controls(time.perf_counter(), force=True)

    def stick(self):
        """The arrow keys as (forward, side) for your fighter: the camera decides which way is which, so right
        always moves right on the screen."""
        down = self.mouseWatcherNode.is_button_down
        sx = down(KeyboardButton.right()) - down(KeyboardButton.left())
        sy = down(KeyboardButton.up()) - down(KeyboardButton.down())
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
        if self.typing:  # arrows and space move the text cursor, not the fighter
            control = (0.0, 0.0, "")
            press = None
        else:
            fwd, side = self.stick()
            block, crouch = down(KeyboardButton.shift()), down(KeyboardButton.asciiKey("x"))
            hold = "low_block" if block and crouch else "block" if block else "crouch" if crouch else ""
            control = (round(fwd, 2), round(side, 2), hold)
        if press or force or control != self.last_control or now - self.last_send > 0.25:
            msg = {"type": "control", "f": control[0], "s": control[1], "hold": control[2]}
            if press:
                msg["press"] = press
            send(msg)
            self.last_control, self.last_send = control, now

    # ---------- sounds and drawing ----------
    def event_sounds(self, st, now):
        """Moves starting (a whoosh), the bell, knockouts and wins, and the crowd's reactions."""
        snd = rw_sound.sound_settings(self.lesson.get("sound"))
        if self.muted or not snd["effects"]:
            return
        vol = snd["volume"]
        watched = self.watched_ring()
        for r in st["rings"]:
            near = 1.0 if r["i"] == watched else 0.25
            phase = self.last_phase.get(r["i"])
            if phase == "intro" and r["ph"] == "fight" and r["i"] == watched:
                self.snd.bell()
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
                    self.snd.play("jump", 0.4 * vol * near)
                self.last_anim[f["id"]] = (a, f["k"])

    def draw_state(self, dt, now, watched_ring):
        st = self.state
        if self.stage_vis:
            self.stage_vis.update(st["rings"], st["t"], dt)
        # sparks, flashes and hit sounds
        watched = watched_ring["i"] if watched_ring else None
        all_f = [(f, r["i"]) for r in st["rings"] for f in r["f"]]
        snd = rw_sound.sound_settings(self.lesson.get("sound"))
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
        self.status_text.setText(f"{self.clock.getAverageFrameRate():.0f} fps   ping {self.ping_ms:.0f} ms")
        self.feed.setText("\n".join(st["events"]))


if __name__ == "__main__":
    Lab().run()
