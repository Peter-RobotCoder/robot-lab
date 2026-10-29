"""City Lab's window (CHANGE 194), for learners and the teacher. The city runs on city_server.py. Built in steps
(docs/plans/city-lab.md): this is step 5, the city online and offline.

Learner:  python city_client.py                       (log in with a username and password in the window)
Teacher:  python city_client.py --teacher --name "Mr P"
Offline:  python city_client.py --offline              the city on this laptop, no server
Class server: add --host wss://... Learners come through the Club Coders app (a ticket from the club desk); the
teacher's code comes from --code or CITYLAB_TEACHER_CODE; on a laptop test server it is the demo code.

On foot:  WASD or the arrows walk (W is away from the camera), Shift runs, Space jumps, J punches, K kicks, B blocks,
          E gets into the car beside you. Robots patrol the pavements: come close and they get cross, wind up their
          weapons and zap you; punch and kick one until it powers down (it reboots a few seconds later). Knocked
          down, you get up again with half your health; it comes back by itself.
Driving:  W or up goes, S or down brakes (then reverses), A and D steer, Shift drifts, B is the handbrake, the
          throttle let go and pressed again from a standstill drops the clutch, E gets out (under 10 km/h)
Always:   R goes back to the depot, V changes the view (on foot: behind, over the shoulder, from above; in a car:
          chase, bonnet), the mouse wheel zooms, N cycles day, dusk and night (offline; online the teacher's lesson
          says), H the key list, F11 full screen (Esc leaves it). A game pad works too.
Teacher:  Enter starts a street race for everyone (a car each, on the line), G sends everyone back to the depot,
          F mends your own car, P pauses the city

Jobs:     walk into the DEPOT's ring for a parcel (deliver it to the address under the beam of light: the arrow over
          your head points the way, the sooner the better paid); drive into the TAXI RANK's ring for a passenger
          (pick them up, take them to their stop; every bump costs you the tip); stop on the STREET RACE line in a car
          to open a race (the computer's racers line up, round the checkpoints and back); the chips (green discs on
          the pavements) are paid for at the ARCADE, and walking into its ring with none starts a ROUND-UP (the robots
          go rogue: power them down). The cash and the job are top middle, the minimap top right.

The window steps the world itself offline (city_sim.World, the server's own code), 60 times a second from the keys,
with the computer's traffic driving (cpu_brains), and draws everything between the last two steps, so it moves
smoothly at any frame rate.

Online your own person, or the car you drive, answers the keys at once: the window steps it itself with every key
press (city_sim.step_person or step_car, the server's arithmetic) and sends the numbered inputs; each snapshot from
the server says which input it had applied, the window compares the server's record with what it predicted for that
moment and, when they differ, puts the server's in and replays the inputs since (engine.predict). Everything else is
drawn a little in the past, blended between two snapshots (engine.interp). Getting in and out, bumps, punches, the
jobs and the pay are the server's: they show when its snapshot says so.
"""
import argparse
import json
import math
import os
import queue
import random
import subprocess
import sys
import threading
import time

from panda3d.core import loadPrcFileData

import city_version
sys.path.insert(0, city_version.ENGINE_HOME)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="", help="username (learners are asked in the window if it's left out; offline: "
                                             "the name on your person)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--host", default=None, help="server address (default: this computer); 'class' = the one in "
                                             "teacher_settings.json")
ap.add_argument("--code", help="class code (the demo codes on a laptop test server)")
ap.add_argument("--ticket", help=argparse.SUPPRESS)  # (from the club desk: the app has logged this person in)
ap.add_argument("--offline", action="store_true", help="the city on this laptop, no server")
ap.add_argument("--no-predict", action="store_true", help="draw your own person or car from the server's snapshots only")
ap.add_argument("--no-interp", action="store_true", help="draw each snapshot as it arrives")
ap.add_argument("--city", default=None, help="harbour, village or metro (offline)")
ap.add_argument("--look", default="woman", help="who you are: woman, man, robin, human or robot")
ap.add_argument("--car", default="coupe", help="your car's body when you get in a car of your own (offline: the parked "
                                                "cars are the city's)")
ap.add_argument("--traffic", type=int, default=6, help="the computer's cars about")
ap.add_argument("--parked", type=int, default=12, help="cars parked for anyone to take")
ap.add_argument("--robots", type=int, default=6, help="robots on the pavements")
ap.add_argument("--time", choices=["day", "dusk", "night"], default="day")
ap.add_argument("--window", help="the window: 1280x720 ... or full")
ap.add_argument("--gfx", choices=["auto", "mesh", "lines", "basic", "low", "medium", "high", "ultra"], default="auto")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--demo", action="store_true", help="(tests and pictures) the person runs round the block by themselves")
ap.add_argument("--demo-drive", action="store_true", help="(tests and pictures) start in a car, driving by itself")
ap.add_argument("--demo-fight", action="store_true", help="(tests and pictures) start beside a robot, kicking it")
ap.add_argument("--demo-job", choices=["delivery", "race"], help="(tests and pictures) start on a delivery in a car, or on "
                                                                  "the race line")
ap.add_argument("--racers", type=int, default=2, help="the computer's racers in a street race")
ap.add_argument("--fps", action="store_true", help="print the frame rate every second")
ap.add_argument("--freeze-at", type=float, help=argparse.SUPPRESS)  # (tests: the window stops for 3 s once, this long in)
ap.add_argument("--view", help="start in this view (behind, shoulder, above; chase, hood)")
ap.add_argument("--mute", action="store_true")
ap.add_argument("--tab", help="(tests and pictures) open the side panel on this tab: missions, garage, ai, card, "
                              "settings; the teacher's teacher, mods, warnings, limits")
ap.add_argument("--show-code", action="store_true", help="(tests and pictures) open the code panel (C)")
ap.add_argument("--x", type=int, help="window position (left edge)")
args = ap.parse_args()
if os.environ.get("CITYLAB_LOGIN") and not args.name:  # reopened by itself (to load code changes): the same login
    try:
        args.name, args.password, *rest = json.loads(os.environ.pop("CITYLAB_LOGIN"))
        args.ticket = rest[0] if rest and rest[0] else args.ticket
    except (ValueError, TypeError):
        pass
OFFLINE = bool(args.offline)

HERE = os.path.dirname(os.path.abspath(__file__))
TEACHER_SETTINGS = os.path.join(HERE, "teacher_settings.json")  # the teacher's laptop only: never in git
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "CityLab")
BRAINS = (os.path.join(os.path.dirname(sys.executable), "brains", "citylab") if city_version.FROZEN  # (the built
          else os.path.join(HERE, "brains"))  # app keeps each game's brains folder beside the exe: brains\citylab)
from engine import hud  # noqa: E402
from engine.hud import load_json, remember  # noqa: E402,F401
SETTINGS = hud.setup(SETTINGS_DIR, sys.modules[__name__])
from engine import club_ticket  # noqa: E402
if args.ticket:  # the club desk has logged this person in: their name and role are in the ticket (the server checks it)
    peek = club_ticket.peek(args.ticket) or {}
    args.name = peek.get("name") or args.name
    args.teacher = args.teacher or peek.get("role") == "teacher"
TEACHER = args.teacher
if args.host == "class":  # the class server's address, from the teacher's settings
    args.host = load_json(TEACHER_SETTINGS).get("server") or city_version.ONLINE_SERVER
elif args.host is None:  # a learner's last choice on the login screen, or this computer
    where = load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("where")
    args.host = {"local": city_version.LOCAL_SERVER, "online": city_version.ONLINE_SERVER}.get(
        where if not TEACHER else None) or city_version.SERVER
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))  # a laptop test server
if args.code or args.ticket:
    code = args.code or ""
elif TEACHER:
    code = (os.environ.get("CITYLAB_TEACHER_CODE") or ("TEACH99" if LOCAL else "")
            or load_json(TEACHER_SETTINGS).get("teacher_code"))
    if not code and not OFFLINE:
        raise SystemExit("The teacher code is needed: put it in teacher_settings.json next to city_client.py "
                         '(for example {"teacher_code": "..."}) or use --code.')
else:
    code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
name = args.name or ("Teacher" if TEACHER else "")
net = None  # the connection to the server, made when you log in
from engine import gfx_tiers  # noqa: E402
GFX = gfx_tiers.resolve(SETTINGS_DIR, args.gfx, gfx_tiers.TIERS)
title = f"City Lab - {'OFFLINE' if OFFLINE else 'TEACHER' if TEACHER else 'LEARNER'}" + (f" ({name})" if name else "")
loadPrcFileData("", hud.window_arg(args.window, args.x if args.x is not None else (40 if TEACHER or OFFLINE else 1360))
                + f"window-title {title}\n" + gfx_tiers.prc_for(GFX))
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import DirectEntry, DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import ClockObject, Filename, KeyboardButton, TextNode, WindowProperties  # noqa: E402

import city_gfx  # noqa: E402
import city_jobs  # noqa: E402
import city_map  # noqa: E402
import city_panels  # noqa: E402
import city_sim as sim  # noqa: E402
import city_sound  # noqa: E402
import cpu_brains  # noqa: E402
import kart_gfx  # noqa: E402
from engine import gamepad, interp, predict, wire  # noqa: E402
from engine import net as net_module  # noqa: E402
from engine.net import Net  # noqa: E402

SCHEMA = wire.Schema("city", sim.SCHEMA_FIELDS)
SNAP_SPEC = {"entities": ["id", {"x": "lerp", "y": "lerp", "z": "lerp", "yaw": "angle", "v": "lerp", "u": "lerp"}]}
STOP_CODES = (4001, 4004, 4006, 4007, 4008, 4009, 4010, 4011)  # the server said no: retrying won't help
TEACHER_KEYS = "Teacher: Enter street race   G everyone to the depot   F mend your car   P pause"
PREDICT_LOG = os.environ.get("CITYLAB_PREDICT_LOG") == "1"
net_module.OPTIONS["compression"] = None  # (binary snapshots are small already; deflate would make them bigger)


def send(msg):
    if net is not None:
        net.send(msg)
FOOT_KEYS = ("WASD walk   Shift run   Space jump   J punch   K kick   B block   E get in   R depot   "
             "V view" + ("   N day/night" if OFFLINE else "") + "   I panel   C code" + ("" if OFFLINE or TEACHER else
                                                                                  "   U brain   P autopilot") + "   H keys")
CAR_KEYS = ("W go   S brake   A D steer   Shift drift   B handbrake   E get out   R depot   V view"
            + ("   N day/night" if OFFLINE else "") + "   I panel   C code   H keys")
TIMES = ("day", "dusk", "night")
DRAW_PEOPLE, DRAW_CARS, DRAW_ROBOTS = 110.0, 160.0, 90.0  # (metres from the camera each kind is drawn within)
GET_IN_REACH = sim.ENTER_REACH + sim.CAR_R


def between(a, b, f):
    """A thing's record a fraction f of the way from a to b (position, height, heading, speed; the rest b's)."""
    if a is None or f >= 1.0:
        return dict(b)
    dy = (b["yaw"] - a["yaw"] + 180.0) % 360.0 - 180.0
    return dict(b, x=a["x"] + (b["x"] - a["x"]) * f, y=a["y"] + (b["y"] - a["y"]) * f, z=a["z"] + (b["z"] - a["z"]) * f,
                yaw=a["yaw"] + dy * f, v=a["v"] + (b["v"] - a["v"]) * f, u=a["u"] + (b["u"] - a["u"]) * f)


def text(parent, x, y, scale, align=TextNode.ALeft, fg=(1, 1, 1, 1)):
    t = OnscreenText(text="", pos=(0, 0), scale=scale, fg=fg, shadow=(0, 0, 0, 0.85), align=align, mayChange=True)
    t.reparentTo(parent)
    t.setPos(x, y)
    return t


class CityWindow(city_panels.CityPanels, hud.HudKit, ShowBase):
    teacher, offline, brains_dir = TEACHER, OFFLINE, BRAINS  # (the side panel's: city_panels)
    FIRST_TAB = "garage" if OFFLINE else "teacher" if TEACHER else "missions"
    GFX_TIERS = gfx_tiers.TIERS
    VERSION = city_version.VERSION

    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()
        self.started = time.perf_counter()
        self.frames = 0
        self.ready = False        # the city is built and the game running (not the log-in screen)
        self.login_panel = None
        self.entries = {}
        self.note_text, self.note_until = "", 0.0
        gfx_tiers.detect(self, SETTINGS_DIR)
        self.pipeline = city_gfx.init(self, GFX)
        self.time_of_day = args.time
        self.apply_time()
        hud.setup_app(self, send)
        self.init_hud()
        self.gfx_tier = GFX
        self.taskMgr.add(self.update, "update")
        if OFFLINE:
            key = args.city if args.city in city_map.CITIES else city_map.DEFAULT_CITY
            self.start_offline(city_map.load(key))
        elif TEACHER or args.ticket or (args.name and args.password):
            error = self.connect(name, args.password or "")
            if error:
                self.show_login(error, teacher=TEACHER)
        else:
            self.show_login()

    # ---------- logging in ----------
    def connect(self, username, password):
        """Connect and log in. Returns None if it worked, or a message saying what went wrong."""
        global net, name
        try:
            net = Net(args.host, username, code, password=password, version=city_version.VERSION,
                      **({"ticket": args.ticket} if args.ticket else {}))
        except OSError:
            net = None
            return f"Can't reach the City Lab server ({args.host}). Is it running?"
        except Exception as e:  # e.g. the secure connection couldn't be set up
            net = None
            return f"Can't connect to the City Lab server ({args.host}): {e}"
        welcome, problem = self.wait_for("welcome")
        if welcome is None:
            net = None
            return problem
        name = welcome.get("name") or username
        self.password = password
        if not TEACHER and not LOCAL and code:
            remember("class_code", code)
        if self.check_code(welcome):
            return None
        self.start_online(welcome)
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

    def show_login(self, error="", teacher=False):
        """The log-in screen: a username and a password (a new username makes a profile on a laptop test server);
        the teacher's window, which logs in by itself, only says what went wrong, with Try again."""
        if error:
            print(error, flush=True)
        if self.login_panel is not None:
            self.login_panel.destroy()
        self.login_panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))
        f = DirectFrame(parent=self.login_panel, frameColor=hud.PANEL, frameSize=(-0.62, 0.62, -0.5, 0.46))
        hud.label(f, "CITY LAB" + ("  -  TEACHER" if teacher else ""), 0, 0.34, 0.08, hud.YELLOW, TextNode.ACenter)
        self.entries = {}
        if not teacher:
            hud.label(f, "Username", -0.54, 0.12, 0.04)
            self.entries["user"] = DirectEntry(parent=f, scale=0.045, pos=(-0.16, 0, 0.12), width=12, initialText=args.name,
                                               numLines=1, focus=not args.name, frameColor=(0.9, 0.9, 0.9, 1),
                                               command=lambda t: self.entries["pass"].setFocus())
            hud.label(f, "Password", -0.54, 0.0, 0.04)
            self.entries["pass"] = DirectEntry(parent=f, scale=0.045, pos=(-0.16, 0, 0.0), width=12, obscured=True,
                                               numLines=1, focus=bool(args.name), frameColor=(0.9, 0.9, 0.9, 1),
                                               command=lambda t: self.submit_login())
            if not LOCAL:  # (the class server asks for the class code too: from the welcome letter, then remembered)
                hud.label(f, "Class code", -0.54, -0.12, 0.04)
                self.entries["code"] = DirectEntry(parent=f, scale=0.045, pos=(-0.16, 0, -0.12), width=12,
                                                   initialText=code, numLines=1, frameColor=(0.9, 0.9, 0.9, 1),
                                                   command=lambda t: self.submit_login())
            hud.button(f, "LOG IN", 0, -0.24, self.submit_login, None, 0.05, (0.15, 0.55, 0.25, 1))
            hud.label(f, "New here? Choose a username and a password: that makes your profile.\n"
                         "Next lesson, use the same ones to carry on where you left off." if LOCAL else
                      "Use the username, password and class code your teacher gave you.", 0, -0.33, 0.028, hud.GREY,
                      TextNode.ACenter)
        else:
            hud.button(f, "Try again", -0.16, -0.22, self.try_again, (), 0.04, (0.15, 0.55, 0.25, 1))
            hud.button(f, "Close", 0.2, -0.22, self.userExit, (), 0.04)
        self.login_msg = hud.label(f, error, 0, -0.42 if not teacher else 0.08, 0.03, hud.RED, TextNode.ACenter, wrap=38)

    def try_again(self):
        error = self.connect(name, args.password or "")
        if error:
            self.show_login(error, teacher=True)

    def submit_login(self):
        global code
        user, password = self.entries["user"].get().strip(), self.entries["pass"].get()
        if not user:
            self.login_msg.setText("Type your username first.")
            return
        if "code" in self.entries:
            code = self.entries["code"].get().strip()
            if not code:
                self.login_msg.setText("Type the class code from your welcome letter.")
                return
        self.login_msg.setText("Logging in...")
        self.login_msg.setFg(hud.GREY)
        self.graphicsEngine.renderFrame()
        error = self.connect(user, password)
        if error and self.login_panel is not None:
            self.login_msg.setText(error)
            self.login_msg.setFg(hud.RED)

    def check_code(self, welcome):
        """The server runs the game's current code: if this window's is different (the server restarted with
        changes), reopen with the new code. Returns True if the window is reopening."""
        if not welcome.get("code") or welcome["code"] == city_version.CODE:
            return False
        if not city_version.FROZEN and not LOCAL:  # the teacher's own windows on the class server run the teacher's code
            return False
        if os.environ.get("CITYLAB_REOPENED") == welcome["code"] or args.offscreen:  # tried already: don't loop
            self.note("This window's game code doesn't match the server's. Restart the server, then reopen this "
                      "window.", 3600)
            return False
        self.restart_window(reopen_for=welcome["code"])
        return True

    def restart_window(self, reopen_for=None):
        """Reopen this window (to load code changes), logged in as the same person."""
        env = dict(os.environ, CITYLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        if reopen_for:  # remember which server code this reopen was for, so it only happens once
            env["CITYLAB_REOPENED"] = reopen_for
        else:
            env.pop("CITYLAB_REOPENED", None)
        argv = list(sys.argv[1:])
        for flag in ("--name", "--password"):  # the login travels in CITYLAB_LOGIN instead
            while flag in argv:
                i = argv.index(flag)
                del argv[i:i + 2]
        if TEACHER:
            argv += ["--name", name]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        program = [sys.executable] if city_version.FROZEN else [sys.executable, os.path.abspath(__file__)]
        log_dir = SETTINGS_DIR if city_version.FROZEN else HERE
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "window.log"), "a") as log:
            child = subprocess.Popen(program + argv, cwd=os.getcwd() if city_version.FROZEN else HERE, env=env,
                                     stdout=log, stderr=log, creationflags=flags)
        if os.environ.get("CLUBCODERS_WINDOW_PID_FILE"):  # (the app that opened this window follows the new one)
            try:
                with open(os.environ["CLUBCODERS_WINDOW_PID_FILE"], "w", encoding="utf-8") as f:
                    f.write(str(child.pid))
            except OSError:
                pass
        os._exit(0)

    # ---------- the game ----------
    def start_online(self, welcome):
        """The server's welcome: its city, who I am, the lesson. The city is drawn from the server's copy."""
        if self.login_panel is not None:
            self.login_panel.destroy()
            self.login_panel = None
            self.entries = {}
        props = WindowProperties()
        props.setTitle(f"City Lab - {'TEACHER' if TEACHER else 'LEARNER'} ({name})")
        if self.win is not None and not args.offscreen:
            self.win.requestProperties(props)
        self.online_state()
        self.lesson = welcome.get("lesson") or {}
        self.rules = welcome.get("rules") or {}
        self.design = welcome.get("design") or sim.default_design(name)
        self.begin(city_map.City(welcome["city"]), welcome.get("me"))
        self.my_name = name
        self.init_panels(self.design, welcome.get("lesson"), welcome.get("rules"))  # (the side panel: city_panels)
        self.open_from_args()
        self.needs_restart = bool(welcome.get("live_ready"))
        send({"type": "slot", "do": "list"})  # (my saved designs)
        # the first person, car and robot drawn load their models (seconds): done now, before the city runs, so the
        # first snapshots don't wait behind them and the prediction starts in step with the server
        t0 = time.perf_counter()
        for vis in (city_gfx.PersonVisual(self.render, sim.fit_design(self.design)),
                    city_gfx.CarVisual(self.render, sim.default_design()),
                    city_gfx.RobotVisual(self.render, sim.robot_design(0), self)):
            vis.destroy()
        print(f"City Lab: the models loaded in {time.perf_counter() - t0:.1f} s", flush=True)
        self.time_of_day = self.lesson.get("time", "day")
        self.apply_time()
        if TEACHER:
            self.key("enter", send, {"type": "start"})
            self.key("g", send, {"type": "grid"})
            self.key("f", send, {"type": "fix"})
            self.key("p", send, {"type": "pause"})
            self.note("Teacher: Enter starts a street race for everyone, G sends everyone to the depot, F mends "
                      "your car, P pauses", 8)
        if welcome.get("new_profile"):
            self.note(f"Welcome, {name}! Your profile is made: next time log in with the same username and "
                      "password.", 7)

    def online_state(self):
        """What the online game keeps: the snapshots, the prediction of my own person or car, the input numbers."""
        self.snaps = interp.Snapshots(SNAP_SPEC)
        self.predictor = None
        self.pred_id = None       # what the predictor steps: my person, or the car I drive
        self.draw_from = None     # the predicted state before the newest tick: drawn between the two
        self.smoother = predict.ErrorSmoother(remove_up=True)
        self.lead = predict.LeadController()
        self.snap_seq = 0
        self.next_seq = 1         # one numbering for every input sent, whether or not a predictor is running
        self.sent_at = {}
        self.last_ents = {}
        self.roster = None
        self.events_seen = []
        self.paused = False
        self.autopilot = False
        self.ping_ms, self.ctrl_ms = 0.0, None
        self.last_ping = self.perf_at = 0.0
        self.reconnecting, self.reconnect_thread = False, None

    def start_offline(self, city):
        self.begin(city, 0)
        # the world (offline: this window runs it, as the server does online)
        self.world.jobs = city_jobs.Jobs(self.city, sim.RULES)
        design = sim.default_design(args.name or "You", (220, 60, 50), body=args.car if args.car in sim.BODIES else "coupe",
                                    look=args.look if args.look in sim.LOOKS else "woman")
        saved = SETTINGS.get("city_design")  # (the garage's last build on this computer)
        if isinstance(saved, dict) and not sim.check_design(saved, sim.full_limits()):
            design = sim.fit_design(saved)
        self.world.add_person(self.me, design)
        self.my_name = design["name"]
        self.init_panels(design, {}, {})  # (offline: the Garage and Settings tabs)
        self.open_from_args()
        self.parked, self.traffic = set(), {}
        self.world.park_cars(max(0, min(40, args.parked)), self.parked)
        for k in range(max(0, min(30, args.traffic))):
            self.traffic[self.world.add_traffic(k)["id"]] = {}
        self.robot_mem = {}
        for k in range(max(0, min(20, args.robots))):
            self.robot_mem[self.world.add_patrol(k)["id"]] = {}
        if args.demo_fight and self.robot_mem:  # (pictures and tests: beside the first robot, facing it)
            rid = min(self.robot_mem)
            r = self.world.robots[rid]
            fx, fy = sim.facing(r["yaw"])
            p = self.world.people[self.me]
            p.update(x=r["x"] + fx * 1.6, y=r["y"] + fy * 1.6, yaw=sim.wrap(r["yaw"] + 180.0))
        self.ticks = 0
        if args.demo_drive:  # (pictures and tests: straight into the nearest parked car)
            p = self.world.people[self.me]
            cid = min(self.parked, key=lambda c: math.hypot(self.world.cars[c]["x"] - p["x"], self.world.cars[c]["y"] - p["y"]))
            car = self.world.cars[cid]
            x, y, yaw = self.world.traffic_spot(len(self.traffic) + 3)  # (on a road, in a lane: the driver needs one)
            car.update(x=x, y=y, yaw=yaw)
            p.update(x=car["x"] + 1.0, y=car["y"])
            self.world.action(self.me, p)
            self.world.seat_people()
        self.racers = {}  # car id -> (level, the driver's memory): the computer's racers in a street race
        if args.demo_job:
            self.start_demo_job()
        self.prev = self.snapshot()
        self.jobs = self.world.jobs.state(self.world)
        self.events_seen = 0
        self.sync_visuals()
        self.foot_cam.yaw = self.world.people[self.me]["yaw"]
        self.title.setText(f"CITY LAB   {self.city.name}   offline")
        self.ready = True

    def begin(self, city, me):
        """The city drawn, the cameras, the screen and the keys: online and offline alike."""
        self.city = city
        t0 = time.perf_counter()
        self.city_vis = city_gfx.CityVisual(self.render, self.city)
        print(f"City Lab: {self.city.name} built in {time.perf_counter() - t0:.1f} s, graphics {city_gfx.tier()}",
              flush=True)
        self.world = sim.World(self.city, SCHEMA)  # (online: a copy of the server's, filled from its snapshots)
        self.me = me
        self.ticks = 0
        if OFFLINE:
            self.predictor = self.pred_id = None  # (online_state's: offline the world itself is stepped)
        self.people, self.cars, self.robots = {}, {}, {}
        self.sparks = city_gfx.Sparks(self.render, self)
        if getattr(self, "snd", None) is None:  # (the sounds: made once, kept when the city changes)
            self.snd = city_sound.make(self, not args.mute and not args.offscreen)
        self.jobs_vis = city_gfx.JobsVisual(self.render, self.city)
        self.jobs = {}
        self.foot_cam = city_gfx.FootCamera(self, self.city)
        self.car_cam = city_gfx.CarCamera(self)
        saved = load_json(os.path.join(SETTINGS_DIR, "settings.json"))
        self.foot_cam.restore(saved.get("camera"))
        self.car_cam.restore(saved.get("car_camera"))
        if args.view in city_gfx.FootCamera.VIEWS:
            self.foot_cam.mode = args.view
        elif args.view in city_gfx.CarCamera.MODES:
            self.car_cam.set_mode(args.view)
        self.pad = gamepad.Pad(self)
        self.accum = 0.0
        self.taps = 0
        self.demo_t = 0.0
        self.th_was, self.th_released, self.launch_armed = False, -10.0, False
        self.in_car = None
        # the overlay
        self.title = text(self.a2dTopLeft, 0.04, -0.07, 0.05)
        self.title.setText(f"CITY LAB   {self.city.name}   {'TEACHER' if TEACHER else 'online'}: {name}")
        self.note_line = text(self.aspect2d, 0, -0.42, 0.045, TextNode.ACenter, fg=(1, 0.95, 0.6, 1))
        self.view = text(self.a2dTopLeft, 0.04, -0.13, 0.04, fg=(0.85, 0.85, 0.85, 1))
        self.hint = text(self.a2dBottomCenter, 0, 0.2, 0.055, TextNode.ACenter, fg=(1, 0.9, 0.3, 1))
        self.speedo = text(self.a2dBottomRight, -0.06, 0.16, 0.08, TextNode.ARight)
        self.damage = text(self.a2dBottomRight, -0.06, 0.1, 0.045, TextNode.ARight, fg=(0.85, 0.85, 0.85, 1))
        self.help = text(self.a2dBottomCenter, 0, 0.05, 0.035, TextNode.ACenter, fg=(1, 1, 1, 0.9))
        self.banner = text(self.aspect2d, 0, 0.25, 0.11, TextNode.ACenter, fg=(1, 0.35, 0.25, 1))
        self.health = city_gfx.HealthBar(self.a2dBottomLeft)
        self.minimap = city_gfx.Minimap(self.a2dTopRight, self.city)
        self.cash = text(self.a2dTopRight, -0.04, -0.68, 0.06, TextNode.ARight, fg=(0.5, 1, 0.5, 1))
        self.chips_text = text(self.a2dTopRight, -0.04, -0.74, 0.04, TextNode.ARight, fg=(0.5, 1, 0.6, 1))
        self.job = text(self.a2dTopCenter, 0, -0.09, 0.055, TextNode.ACenter, fg=(1, 0.85, 0.3, 1))
        self.job2 = text(self.a2dTopCenter, 0, -0.16, 0.042, TextNode.ACenter, fg=(1, 1, 1, 1))
        self.countdown = text(self.aspect2d, 0, 0.45, 0.2, TextNode.ACenter, fg=(1, 0.9, 0.2, 1))
        self.compass = city_gfx.CompassArrow(self.a2dTopCenter)
        self.log = [text(self.a2dBottomLeft, 0.05, 0.36 - 0.05 * i, 0.038, fg=(0.95, 0.95, 0.95, 1)) for i in range(4)]
        self.log_lines = []
        self.help_on = True
        # the keys
        for k, bit in (("j", sim.PUNCH), ("k", sim.KICK), ("r", sim.RESPAWN), ("e", sim.ACTION)):
            self.key(k, self.tap, bit)
        self.key("v", self.cycle_view)
        if OFFLINE:
            self.key("n", self.cycle_time)
        self.key("h", self.toggle_help)
        self.key("i", self.toggle_panel)  # (the side panel: city_panels)
        self.key("tab", self.toggle_panel)
        self.key("c", self.toggle_code)
        self.key("u", self.upload_brain)
        if not TEACHER:
            self.key("p", self.autopilot_key)
        self.accept("wheel_up", self.panel_wheel, [1 / 1.12, -1])
        self.accept("wheel_down", self.panel_wheel, [1.12, 1])
        self.key("page_up", self.slide_panel, -1)
        self.key("page_down", self.slide_panel, 1)
        self.accept("f11", self.toggle_fullscreen)
        self.accept("escape", self.escape)
        self.fps_at, self.fps_frames = time.perf_counter(), 0
        self.ready = not OFFLINE  # (offline: once the world is filled, start_offline)

    def note(self, words, secs=4):
        """A line of news in the middle of the screen for a few seconds (the server's notices, the teacher's keys)."""
        self.note_text, self.note_until = words, time.perf_counter() + secs
        if args.offscreen:  # (tests read it from the console)
            print("note:", words, flush=True)
        if hasattr(self, "note_line"):
            self.note_line.setText(words)

    # ---------- the world's things and their pictures ----------
    def snapshot(self):
        w = self.world
        return {**{pid: dict(p) for pid, p in w.people.items()}, **{cid: dict(c) for cid, c in w.cars.items()},
                **{rid: dict(r) for rid, r in w.robots.items()}}

    def sync_visuals(self):
        """A picture for each person, car and robot in the world (and none for one that has gone; a new one for one
        whose design has changed)."""
        w = self.world
        for things, have, make in ((w.people, self.people, lambda d: city_gfx.PersonVisual(self.render, d)),
                                   (w.cars, self.cars, lambda d: city_gfx.CarVisual(self.render, d)),
                                   (w.robots, self.robots, lambda d: city_gfx.RobotVisual(self.render, d, self))):
            for tid in list(have):
                if tid not in things or (tid in w.designs and have[tid].design != w.designs[tid]):
                    have.pop(tid).destroy()
            for tid in things:
                if tid not in have:
                    d = w.designs.get(tid)
                    if d is None:  # (online, before the roster has said: drawn as it is, once it has)
                        continue
                    t0 = time.perf_counter()
                    have[tid] = make(d)
                    if PREDICT_LOG and time.perf_counter() - t0 > 0.05:
                        print(f"built {tid} in {time.perf_counter() - t0:.2f} s", flush=True)

    # ---------- keys ----------
    def tap(self, bit):
        self.taps |= bit

    def cycle_view(self):
        if self.in_car is not None:
            self.car_cam.cycle()
            remember("car_camera", self.car_cam.settings())
        else:
            self.foot_cam.cycle()
            remember("camera", self.foot_cam.settings())

    def open_from_args(self):
        if args.tab or args.show_code:
            self.tab, self.show_code = args.tab, bool(args.show_code)
            self.rebuild_panels()

    def panel_shown(self, shown):
        """The side panel covers the top right: the minimap, the cash and the chips hide under it while it's open."""
        for part in (self.minimap.root, self.cash, self.chips_text):
            part.hide() if shown else part.show()

    def built_offline(self, design):
        """Offline, BUILD MY DRIVER: your person and the cars you drive take the new design at once."""
        self.world.designs[self.me] = design
        self.sync_visuals()

    def key(self, key, fn, *extra):
        """A game key: it does nothing while you are typing in a text box or the code."""
        self.accept(key, lambda: None if self.typing else fn(*extra))

    def zoom(self, factor):
        (self.car_cam if self.in_car is not None else self.foot_cam).wheel(factor)

    def apply_time(self):
        """The time of day drawn: the sky and lights (Kart Lab's), the city's lamps and windows at dusk and night."""
        kart_gfx.set_time(self.time_of_day)
        if getattr(self, "city_vis", None) is not None:
            self.city_vis.set_time(self.time_of_day)

    def cycle_time(self):
        self.time_of_day = TIMES[(TIMES.index(self.time_of_day) + 1) % len(TIMES)]
        self.apply_time()

    def toggle_help(self):
        self.help_on = not self.help_on

    def launch_button(self, pressed, speed):
        """The clutch dropped (Kart Lab's): the throttle let go and pressed again within 0.35 s while the car is
        nearly still arms LAUNCH, held until the throttle is let go."""
        now = time.perf_counter()
        if pressed and not self.th_was:
            if now - self.th_released < 0.35 and abs(speed) < 3.0:
                self.launch_armed = True
        elif not pressed and self.th_was:
            self.th_released, self.launch_armed = now, False
        self.th_was = pressed
        return sim.LAUNCH if self.launch_armed and pressed else 0

    def read_keys(self):
        """This tick's input. On foot: the move in the world's frame from the keys and the camera, and the buttons.
        In a car: the pedals and the wheel (Kart Lab's)."""
        me = self.world.people.get(self.me)
        if me is None:
            return (0.0, 0.0, 0)
        driving = bool(me["link"])
        if args.demo:  # (a run round the block, for pictures and tests)
            self.demo_t += sim.STEP
            yr = math.radians(self.foot_cam.yaw + 25.0 * math.sin(self.demo_t * 0.5))
            return (math.cos(yr), math.sin(yr), sim.RUN if self.demo_t % 6 < 4 else 0)
        if args.demo_fight:  # (kick the robot in front, punch, block now and then)
            self.demo_t += sim.STEP
            phase = self.demo_t % 3.0
            return (0.0, 0.0, sim.KICK if phase < 1.6 else sim.PUNCH if phase < 2.4 else sim.BLOCK)
        if args.demo_job:  # (drive to the job's target, or race round the course: the computer's drivers at the wheel)
            car = self.world.cars.get(me["link"] - 1) if driving else None
            if car is None:
                return (0.0, 0.0, 0)
            mem = self.__dict__.setdefault("demo_mem", {})
            if args.demo_job == "race":
                return cpu_brains.drive_racer(car["id"], car, self.world, mem, "expert")
            return cpu_brains.drive_car(car["id"], car, self.world, mem, 0.37)
        if args.demo_drive:  # (a drive round the town: the traffic's own driver at the wheel)
            car = self.world.cars.get(me["link"] - 1) if driving else None
            if car is not None:
                if self.predicting_car():  # (online: the car where the prediction has it)
                    car = self.predictor.state
                return cpu_brains.drive_car(car["id"], car, self.world, self.__dict__.setdefault("demo_mem", {}), 0.37)
            return self.demo_get_in(me) if not OFFLINE else (0.0, 0.0, 0)
        if self.mouseWatcherNode is None:  # (offscreen: no keyboard)
            return (0.0, 0.0, 0)
        if self.typing:  # (typing in the side panel or the code: the keys are the words)
            self.taps = 0
            return (0.0, 0.0, 0)
        behind = not self.win.getProperties().getForeground()
        if behind and not args.offscreen:  # (the window is behind another: the keys aren't for us)
            self.th_was = self.launch_armed = False
            self.taps = 0
            return (0.0, 0.0, 0)
        down = self.mouseWatcherNode.is_button_down
        k = KeyboardButton
        up_key = down(k.up()) or down(k.asciiKey("w"))
        down_key = down(k.down()) or down(k.asciiKey("s"))
        left_key = down(k.left()) or down(k.asciiKey("a"))
        right_key = down(k.right()) or down(k.asciiKey("d"))
        shift, space, b = down(k.shift()), down(k.space()), down(k.asciiKey("b"))
        bt = self.taps
        self.taps = 0
        pad = self.pad.read()
        if driving:
            th = float(up_key) - float(down_key)
            steer = float(left_key) - float(right_key)
            if shift:
                bt |= sim.DRIFT
            if b:
                bt |= sim.HANDBRAKE
            if pad:
                if not th:
                    th = max(pad.rt, float("south" in pad.held)) - max(pad.lt, float("east" in pad.held))
                if not steer:
                    steer = -pad.x
                bt |= (sim.DRIFT if "rb" in pad.held else 0) | (sim.RESPAWN if "back" in pad.pressed else 0) | \
                    (sim.ACTION if "west" in pad.pressed or "lb" in pad.pressed else 0) | \
                    (sim.HANDBRAKE if "north" in pad.held else 0)
            car = self.predictor.state if self.predicting_car() else self.world.cars.get(me["link"] - 1)
            bt |= self.launch_button(th > 0, car["v"] if car else 0.0)
            return wire.quantise_input(th, steer, bt)
        forward = float(up_key) - float(down_key)
        right = float(right_key) - float(left_key)
        if pad and not (forward or right):
            forward, right = pad.y, pad.x
        mx, my = self.foot_cam.move_from_keys(forward, right)
        if shift:
            bt |= sim.RUN
        if space:
            bt |= sim.JUMP
        if b:
            bt |= sim.BLOCK
        if pad:
            bt |= (sim.JUMP if "south" in pad.held else 0) | (sim.PUNCH if "west" in pad.pressed else 0) | \
                (sim.KICK if "east" in pad.pressed else 0) | (sim.BLOCK if "lb" in pad.held else 0) | \
                (sim.ACTION if "north" in pad.pressed else 0) | (sim.RUN if "rb" in pad.held else 0) | \
                (sim.RESPAWN if "back" in pad.pressed else 0)
        return wire.quantise_input(mx, my, bt)

    def demo_get_in(self, me):
        """(tests and pictures, online) Walk to the nearest car nobody is in, and get in (E, once a second)."""
        empty = [(math.hypot(c["x"] - me["x"], c["y"] - me["y"]), cid) for cid, c in self.world.cars.items() if not c["link"]]
        if not empty:
            return (0.0, 0.0, 0)
        d, cid = min(empty)
        c = self.world.cars[cid]
        now = time.perf_counter()
        if d < GET_IN_REACH - 0.3:
            if now - getattr(self, "demo_e_at", 0.0) > 1.0:
                self.demo_e_at = now
                return (0.0, 0.0, sim.ACTION)
            return (0.0, 0.0, 0)
        return wire.quantise_input((c["x"] - me["x"]) / d, (c["y"] - me["y"]) / d, 0)

    # ---------- the world's tick (offline) ----------
    def tick(self):
        w = self.world
        inputs = {self.me: self.read_keys()}
        for cid, mem in self.traffic.items():
            car = w.cars.get(cid)
            if car is not None and not car["link"]:
                inputs[cid] = cpu_brains.drive_car(cid, car, w, mem, ((self.ticks * 7919 + cid * 131) % 1000) / 1000)
        for rid, mem in self.robot_mem.items():
            r = w.robots.get(rid)
            if r is not None and not r["link"]:
                inputs[rid] = cpu_brains.drive_robot(rid, r, w, mem)
        for cid, (level, mem) in list(self.racers.items()):
            car = w.cars.get(cid)
            if car is not None:
                inputs[cid] = cpu_brains.drive_racer(cid, car, w, mem, level)
        self.prev = self.snapshot()
        w.step_all(inputs)
        self.ticks += 1
        self.hits_seen(self.prev, self.snapshot())
        self.race_racers()
        if self.ticks % 6 == 0 or w.jobs.changed:  # (the jobs in words: as the server sends them, ten times a second)
            w.jobs.changed = False
            self.jobs = w.jobs.state(w)
        for t, words in w.events[self.events_seen:]:
            self.add_log(words)
        self.events_seen = len(w.events)

    def race_racers(self):
        """A street race forming: the computer's racers line up on the grid beside you (and drive off as traffic when
        it is over). The server does the same online."""
        w = self.world
        race = w.jobs.race
        if race is not None and race["state"] == "forming" and not self.racers and args.racers > 0:
            mine = [cid for cid in race["cars"]]
            slots = w.jobs.grid_slots(len(mine) + args.racers)
            for cid, (x, y, yaw) in zip(mine, slots):
                w.cars[cid].update(x=x, y=y, yaw=yaw, v=0.0, u=0.0)
            level = "medium"
            for k in range(args.racers):
                x, y, yaw = slots[len(mine) + k]
                d = sim.default_design(cpu_brains.name_for(level, k), sim.TRAFFIC_COLOURS[(k + 2) % 8], sim.BODIES[(k + 2) % 4])
                d["points"] = {"speed": 38, "acceleration": 34, "grip": 28}
                car = w.add_car(d, x, y, yaw)
                race["cars"][car["id"]] = 0
                self.racers[car["id"]] = (level, {})
            self.sync_visuals()
        elif race is None and self.racers:
            for cid in self.racers:
                if cid in w.cars:
                    self.traffic[cid] = {}
            self.racers = {}

    def start_demo_job(self):
        """(tests and pictures) --demo-job delivery: a parcel, in a car, driving towards it; race: on the race line."""
        w = self.world
        p = w.people[self.me]
        cid = min(self.parked)
        car = w.cars[cid]
        if args.demo_job == "delivery":
            w.jobs.start_delivery(w, self.me, p)
            x, y, yaw = w.traffic_spot(len(self.traffic) + 3)
        else:
            (x, y), yaw = w.jobs.race_line(), 0.0
        car.update(x=x, y=y, yaw=yaw, v=0.0)
        p.update(x=x + 1.0, y=y)
        w.action(self.me, p)
        w.seat_people()

    def add_log(self, words):
        self.log_lines = (self.log_lines + [words])[-4:]
        for t, line in zip(self.log, list(reversed(self.log_lines)) + [""] * 4):
            t.setText(line)

    def hits_seen(self, prev, things):
        """Sparks where a punch, a kick or a zap landed (a robot's power, or a person's health, went down since prev)."""
        for tid, now in things.items():
            if sim.kind_of(tid) == "car":
                continue
            before = prev.get(tid)
            if before is None or now["hp"] >= before["hp"] or now.get("link"):
                continue
            lost = before["hp"] - now["hp"]
            lift = city_gfx.ground_lift(self.city, now["x"], now["y"])
            robot = sim.kind_of(tid) == "robot"
            self.sparks.hit(now["x"], now["y"], lift + (0.4 if robot else 1.2), lost * 2, "bump" if robot else "flip")
        me = things.get(self.me)
        if me is not None:
            self.snd.landed(things, prev, (me["x"], me["y"]))

    # ---------- the frame ----------
    def update(self, task):
        now = time.perf_counter()
        dt = min(ClockObject.getGlobalClock().getDt(), 0.1)
        self.frames += 1
        if args.screenshot and not self.ready and now - self.started > args.after + 20:
            self.screenshot(now)  # (a test whose window never got into the city: its picture says why)
        if not self.ready:  # still on the log-in screen
            return task.cont
        if OFFLINE:
            self.accum = min(self.accum + dt, 0.25)
            while self.accum >= sim.STEP:
                self.accum -= sim.STEP
                self.tick()
            f = self.accum / sim.STEP
            w = self.world
            drawn = {}
            for tid, cur in list(w.people.items()) + list(w.cars.items()) + list(w.robots.items()):
                drawn[tid] = between(self.prev.get(tid), cur, f)
        else:
            if args.freeze_at and now - self.started > args.freeze_at:  # (tests: a laptop that stops for a moment)
                args.freeze_at = None
                time.sleep(3.0)
            if PREDICT_LOG and now - getattr(self, "frame_at", now) > 0.1:
                print(f"slow frame {now - self.frame_at:.3f} s", flush=True)
            self.frame_at = now
            drawn = self.online_frame(now, dt)
            if self.me not in drawn:  # (no snapshot of me yet: nothing to draw from)
                self.note_line.setText(self.note_text if now < self.note_until else "")
                return task.cont
        w = self.world
        # each thing drawn and placed only near the camera (the blocks hide the rest anyway: a robot is a hundred
        # pieces, and the far ones were half the frame)
        cam = self.camera.getPos(self.render)
        for things, reach in ((self.people, DRAW_PEOPLE), (self.cars, DRAW_CARS), (self.robots, DRAW_ROBOTS)):
            for tid, vis in things.items():
                t = drawn.get(tid)
                if t is None:
                    continue
                near = (t["x"] - cam.x) ** 2 + (t["y"] - cam.y) ** 2 < reach * reach or tid == self.me
                if near == vis.root.isHidden():
                    (vis.root.show if near else vis.root.hide)()
                if near:
                    vis.update(t, city_gfx.ground_lift(self.city, t["x"], t["y"]), dt)
        self.sparks.update(dt)
        self.note_line.setText(self.note_text if now < self.note_until else "")
        self.jobs_vis.update(dt, self.jobs, drawn[self.me], self.me, drawn[self.me]["link"] - 1 if drawn[self.me]["link"] else None)
        self.minimap.update(drawn, self.me, self.jobs, drawn[self.me]["link"] - 1 if drawn[self.me]["link"] else None)
        me = drawn[self.me]
        car_id = me["link"] - 1 if me["link"] else None
        if car_id != self.in_car:  # (in, or out: the other camera, facing the way the car faced)
            if car_id is None:
                self.foot_cam.yaw = me["yaw"]
                self.foot_cam.pos = None
            else:
                self.car_cam.pos, self.car_cam.cam_yaw = None, None
            self.in_car = car_id
        if car_id is not None and car_id in drawn:
            c = drawn[car_id]
            self.car_cam.follow(dt, c, city_gfx.ground_lift(self.city, c["x"], c["y"]))
            self.view.setText(self.car_cam.name)
        else:
            lift = city_gfx.ground_lift(self.city, me["x"], me["y"])
            self.foot_cam.update(dt, me["x"], me["y"], me["z"] + lift, me["yaw"], me["v"] > 0.5)
            self.view.setText(self.foot_cam.name)
        # the headlights: your car's first, then the nearest (at dusk and night)
        if kart_gfx.lamps_on():
            mx, my = me["x"], me["y"]
            order = sorted((cid for cid in self.cars if cid in drawn), key=lambda cid: (cid != car_id, math.hypot(drawn[cid]["x"] - mx, drawn[cid]["y"] - my)))
            kart_gfx.headlights([self.cars[cid].vis for cid in order[:kart_gfx.HEADLIGHTS]])
        else:
            kart_gfx.headlights([])
        self.overlay(me, drawn, car_id)
        self.snd.frame(now, self.me, drawn, car_id, self.city)
        if me["cash"] > getattr(self, "cash_heard", me["cash"]):  # (paid: a job done, chips cashed, a jump)
            self.snd.done()
        self.cash_heard = me["cash"]
        if args.fps:
            self.fps_frames += 1
            if now - self.fps_at >= 1.0:
                print(f"fps {self.fps_frames / (now - self.fps_at):.0f}", flush=True)
                self.fps_at, self.fps_frames = now, 0
        if args.screenshot and now - self.started > args.after and self.frames > 3:
            self.screenshot(now)
        return task.cont

    def screenshot(self, now):
        if not self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot))):
            print(f"screenshot NOT saved: {args.screenshot}", flush=True)
        print(f"screenshot: {args.screenshot} ({self.frames / (now - self.started):.0f} fps over the run)", flush=True)
        if not OFFLINE and net is not None:
            net.goodbye()
        self.userExit()

    # ---------- online: the network, the prediction ----------
    def online_frame(self, now, dt):
        """Online, every frame: the server's messages, our ticks (each one an input sent), and what to draw: the
        others blended between two snapshots, our own person or car where the prediction has it."""
        if net is not None:
            self.read_network()
        # (a hitch of up to 15 ticks is caught up; a longer freeze is skipped. The lead multiplier stretches the
        # time between our ticks when the server has too many of our inputs waiting, and shrinks it when it runs dry)
        self.accum = min(15 * sim.STEP, self.accum + dt / self.lead.multiplier())
        while self.accum >= sim.STEP:
            self.accum -= sim.STEP
            self.client_tick(now)
        if now - self.last_ping > 1:
            self.last_ping = now
            send({"type": "ping", "t": time.time()})
        self.send_perf(now)
        blended = self.snaps.latest if args.no_interp else self.snaps.sample(now)
        drawn = {e["id"]: e for e in blended["entities"]} if blended else {}
        latest_me = self.world.people.get(self.me)
        if self.predictor is not None and self.pred_id in drawn:
            mine = between(self.draw_from, self.predictor.state, self.accum / sim.STEP)
            (ox, oy, _), oyaw = self.smoother.offset(dt)
            mine["x"], mine["y"], mine["yaw"] = mine["x"] + ox, mine["y"] + oy, mine["yaw"] + math.degrees(oyaw)
            drawn[self.pred_id] = mine
            if self.pred_id != self.me and latest_me is not None:  # (in a car: I sit where my car is drawn)
                drawn[self.me] = dict(latest_me, x=mine["x"], y=mine["y"], z=mine["z"], yaw=mine["yaw"], v=mine["v"])
        elif latest_me is not None and self.me in drawn:
            drawn[self.me] = dict(drawn[self.me], cash=latest_me["cash"], aux=latest_me["aux"], link=latest_me["link"])
        return drawn

    def predicting_car(self):
        return self.predictor is not None and self.pred_id is not None and sim.kind_of(self.pred_id) == "car"

    def step_fn(self, tid):
        """The step the prediction runs for what I control: my person on foot, or my car (driven as my points say,
        as the server drives it)."""
        city = self.city
        if sim.kind_of(tid) == "person":
            def step(s, inp, dt):
                n = sim.step_person(s, inp, dt, city)
                n.update(SCHEMA.quantise(n))  # (as the server does: the same numbers next tick)
                return n
            return step
        st = sim.stats_of(self.world.designs.get(self.me) or self.design)

        def step(s, inp, dt):
            n = sim.step_car(s, inp, dt, city, st, driven=True)
            n.update(SCHEMA.quantise(n))
            return n
        return step

    def on_snapshot(self, snap, rx, newest=True):
        """A snapshot: into the blending queue and the world's copy, and checked against the prediction (only the
        newest of several that arrived together: after a stall the older ones would each put it right in turn)."""
        self.snap_seq = snap["seq"]
        self.snaps.push(snap, rx)
        self.lead.feed(snap["flags"] >> 4)
        ents = {e["id"]: e for e in snap["entities"]}
        self.hits_seen(self.last_ents, ents)
        self.last_ents = ents
        w = self.world
        w.people = {i: e for i, e in ents.items() if sim.kind_of(i) == "person"}
        w.cars = {i: e for i, e in ents.items() if sim.kind_of(i) == "car"}
        w.robots = {i: e for i, e in ents.items() if sim.kind_of(i) == "robot"}
        if set(w.people) != set(self.people) or set(w.cars) != set(self.cars) or set(w.robots) != set(self.robots):
            self.sync_visuals()
        me = ents.get(self.me)
        if me is None or args.no_predict or self.autopilot:
            self.predictor = None
            return
        if not newest:
            return
        target = me["link"] - 1 if me["link"] else self.me
        state = ents.get(target)
        if state is None:
            return
        state = dict(state)
        newest = self.predictor.log.newest() if self.predictor is not None else None
        if newest is not None and predict.seq_diff(snap["ack"], newest) > 3:
            # the server has run past every input we sent (this window froze for a moment and dropped the ticks it
            # missed): our numbering carries on from the server's, a round trip ahead, and the prediction from its
            # record (else every input after it arrives late, and is dropped, for half a second)
            self.next_seq = (snap["ack"] + 3 + int(self.ping_ms / 1000 / sim.STEP)) & predict.SEQ_MASK
            self.predictor = None
        if self.predictor is None or self.pred_id != target:  # (in or out of a car: the new thing is predicted from
            self.pred_id = target                             # the server's record; our numbering carries on)
            self.predictor = predict.Predictor(self.step_fn(target), state, ignore=0.05,
                                               log=predict.InputLog(first_seq=self.next_seq))
            self.pred_first = self.next_seq
            self.draw_from = state
            self.smoother.clear()
            self.accum = 0.0
            return
        if snap["ack"] == 0 or predict.seq_diff(snap["ack"], self.pred_first) < 0:
            return  # (the server hasn't applied any input this prediction made yet: nothing to compare with)
        was = self.predictor.predicted.get(snap["ack"])
        err = self.predictor.correct(state, snap["ack"], sim.STEP, sim.compare)
        moved = self.predictor.moved_from
        if PREDICT_LOG and err >= 0.05:  # (CITYLAB_PREDICT_LOG=1: what each correction was about)
            print("correction", snap["ack"], self.predictor.log.newest(), self.pred_first, round(err, 3), {k: (was.get(k), state[k]) for k in state
                                                             if was and was.get(k) != state[k]}, flush=True)
        if moved is not None:  # (the state before the newest tick moves with the correction: the picture holds)
            new, f = self.predictor.state, self.draw_from
            self.draw_from = new if err == math.inf or f is None else dict(
                f, x=f["x"] + new["x"] - moved["x"], y=f["y"] + new["y"] - moved["y"], yaw=f["yaw"] + new["yaw"] - moved["yaw"])
            if err != math.inf:
                dyaw = math.radians((moved["yaw"] - new["yaw"] + 180) % 360 - 180)
                self.smoother.add((moved["x"] - new["x"], moved["y"] - new["y"], 0.0), dyaw)
        sent = self.sent_at.get(snap["ack"])
        if sent is not None and rx:
            ms = (rx - sent) * 1000
            self.ctrl_ms = ms if self.ctrl_ms is None else self.ctrl_ms * 0.8 + ms * 0.2

    def client_tick(self, now):
        """One predicted tick of my own person or car, and its input to the server."""
        if self.predictor is None and not (args.no_predict or self.autopilot):
            return  # (nothing to predict from until the first snapshot: inputs sent now would only be unlogged)
        if self.paused:
            return  # (nothing moves and nothing is sent; the server drains what it has)
        inp = self.read_keys()
        if self.predictor is not None:
            self.draw_from = self.predictor.state
            seq = self.predictor.apply(inp, sim.STEP, now)
            prev = self.predictor.log.previous(2)
            self.next_seq = self.predictor.log.next_seq
            if self.pred_id == self.me:  # (my person's record as predicted: the keys read it next tick)
                self.world.people[self.me] = dict(self.world.people.get(self.me) or {}, **self.predictor.state)
        else:
            seq, prev = self.next_seq, ()
            self.next_seq = (seq + 1) & 0xFFFF
        self.sent_at[seq] = now
        if len(self.sent_at) > 128:
            for s in sorted(self.sent_at)[:64]:
                del self.sent_at[s]
        send(wire.pack_input(seq, self.snap_seq, int(now * 1000) & 0xFFFFFFFF, inp[0], inp[1], inp[2], previous=prev))

    def read_network(self):
        messages = []
        while True:
            try:
                messages.append(net.inbox.get_nowait())
            except queue.Empty:
                break
        snaps = [i for i, m in enumerate(messages) if m["type"] == "binary" and wire.kind_of(m["data"]) == wire.KIND_SNAPSHOT]
        for i, m in enumerate(messages):
            kind = m["type"]
            if kind == "binary":
                if snaps and i in snaps:
                    self.on_snapshot(wire.unpack_snapshot(SCHEMA, m["data"]), m.get(interp.RECEIVED), newest=i == snaps[-1])
            elif kind == "jobs":
                self.jobs = m
                self.paused = bool(m.get("paused"))
                for t, words in m.get("events") or []:
                    if [t, words] not in self.events_seen:
                        self.events_seen = (self.events_seen + [[t, words]])[-30:]
                        self.add_log(words)
            elif kind == "roster":
                self.roster = m
                w = self.world
                for group in ("people", "cars", "robots"):
                    for e in m.get(group) or []:
                        w.designs[e["id"]] = e["design"]
                mine = (m.get("mine") or {}).get(name)
                if mine is not None and mine != self.me:
                    self.me, self.predictor = mine, None
                self.sync_visuals()
            elif kind == "welcome":  # back after a dropped connection (or a server restart)
                self.reconnecting = False
                if self.check_code(m):
                    return
                self.lesson = m.get("lesson") or self.lesson
                self.design = m.get("design") or self.design
                if m.get("city") and m["city"].get("key") != self.city.key:
                    self.change_city(m["city"])
                self.me, self.predictor = m.get("me", self.me), None
                self.snaps = interp.Snapshots(SNAP_SPEC)
                self.note("Reconnected: carry on!", 3)
            elif kind == "city":  # the teacher chose another city
                self.change_city(m["city"])
                self.me, self.predictor = m.get("me", self.me), None
            elif kind == "lesson":
                self.took_lesson(m)
                if self.lesson.get("time", "day") != self.time_of_day:
                    self.time_of_day = self.lesson.get("time", "day")
                    self.apply_time()
            elif kind == "design_result":
                self.design_result(m)
            elif kind == "missions":
                if not m.get("for"):
                    self.took_missions(m)
            elif kind == "ai_card_result":
                self.card_result(m)
            elif kind == "brain_result":
                self.note("Brain: " + (m.get("error") or "running: P switches the autopilot") if m.get("ok") else
                          "Brain problem: " + (m.get("error") or "it didn't load"), 6)
            elif kind == "warnings":
                self.took_warnings(m)
                self.rebuild_panels(from_game=True)
            elif kind in ("slots", "history"):
                if self.took_slots(m):
                    self.rebuild_panels(from_game=True)
            elif kind == "live_update":
                self.needs_restart = True
                self.note("A live update is ready on the class server: press Restart server (Controls).", 12)
            elif kind == "restart_client":
                self.restart_window()
            elif kind == "notice":
                self.note(m.get("text", ""), 12 if m.get("big") else 5)
            elif kind == "pong":
                self.ping_ms = (time.time() - m["t"]) * 1000
            elif kind == "closed":
                self.connection_lost(m)

    def change_city(self, data):
        """Another city from the server: drawn again, everything in it forgotten until its snapshots come."""
        self.city_vis.destroy()
        self.jobs_vis.root.removeNode()
        self.minimap.root.removeNode()
        for have in (self.people, self.cars, self.robots):
            for vis in have.values():
                vis.destroy()
            have.clear()
        self.city = city_map.City(data)
        self.city_vis = city_gfx.CityVisual(self.render, self.city)
        self.jobs_vis = city_gfx.JobsVisual(self.render, self.city)
        self.minimap = city_gfx.Minimap(self.a2dTopRight, self.city)
        self.foot_cam.city = self.city
        designs = self.world.designs
        self.world = sim.World(self.city, SCHEMA)
        self.world.designs = designs
        self.snaps = interp.Snapshots(SNAP_SPEC)
        self.last_ents, self.jobs = {}, {}
        self.title.setText(f"CITY LAB   {self.city.name}   {'TEACHER' if TEACHER else 'online'}: {name}")
        self.note(f"Welcome to {self.city.name}", 4)

    def send_perf(self, now):
        """Every few seconds: how this window is doing, for the teacher (frame rate, ping, graphics tier, network
        stalls, the blending delay, the key delay and the prediction's corrections)."""
        if now - self.perf_at < 3:
            return
        self.perf_at = now
        rep = self.snaps.report()
        perf = {"type": "perf", "fps": round(self.clock.getAverageFrameRate()), "ping": round(self.ping_ms),
                "tier": city_gfx.tier(), "stalls": rep["stalls"], "delay": rep["delay_ms"],
                "ctrl": None if self.ctrl_ms is None else round(self.ctrl_ms),
                "corr": self.predictor.corrections if self.predictor else None}
        send(perf)
        if args.offscreen:  # (tests read it from the console)
            print("perf", json.dumps(perf), f"lead {self.lead.multiplier():.2f}", flush=True)

    def connection_lost(self, m):
        if m.get("code") == 4005:
            self.note("You logged in again in another window, so this one has stopped.", 3600)
            return
        if m.get("code") in STOP_CODES:  # wrong code or password, deleted, or an old version: retrying won't help
            self.note(m.get("reason") or "The server closed the connection.", 3600)
            if m.get("code") == 4009:  # the teacher pressed Stop: this window closes in a few seconds
                self.note("The session has ended. This window will close.", 3600)
                self.taskMgr.doMethodLater(5, lambda t: self.userExit(), "session_over")
            return
        self.note("The class server is restarting: reconnecting..." if m.get("code") == 1012 else
                  "Lost the connection: reconnecting...", 3600)
        self.reconnecting = True
        self.predictor = None
        if self.reconnect_thread is not None and self.reconnect_thread.is_alive():
            return

        def work():  # keep trying every 2 seconds; the server's welcome comes through the inbox
            time.sleep(1.0 + random.random() * 2.0)  # (not the whole class at the same moment)
            while not net.reconnect():
                time.sleep(1.5 + random.random())
        self.reconnect_thread = threading.Thread(target=work, daemon=True)
        self.reconnect_thread.start()

    def overlay(self, me, drawn, car_id):
        """The hint (get in, get out), the speed and the damage in a car, the key list."""
        hint = ""
        if car_id is not None:
            c = drawn[car_id]
            kmh = abs(c["v"]) * 3.6
            self.speedo.setText(f"{kmh:.0f} km/h")
            dmg = c["dmg"] / sim.DAMAGE_MAX
            self.damage.setText("WRECKED: the GARAGE mends it" if c["flags"] & sim.FLAG_WRECKED else
                                f"damage {dmg * 100:.0f}%" if dmg > 0.005 else "")
            if abs(c["v"]) < sim.EXIT_SPEED:
                hint = "E: get out"
            self.help.setText((CAR_KEYS + ("\n" + TEACHER_KEYS if TEACHER else "")) if self.help_on else "")
        else:
            self.speedo.setText("")
            self.damage.setText("")
            if me["move"] not in (sim.MOVE_DOWN, sim.MOVE_GETUP):
                near = min((math.hypot(c["x"] - me["x"], c["y"] - me["y"]) for cid, c in drawn.items()
                            if sim.kind_of(cid) == "car" and not c["link"]), default=99.0)
                if near < GET_IN_REACH:
                    hint = "E: get in"
            self.help.setText((FOOT_KEYS + ("\n" + TEACHER_KEYS if TEACHER else "")) if self.help_on else "")
        self.hint.setText(hint)
        self.health.set(me["hp"] / sim.HEALTH, hurt=bool(me["flags"] & sim.FLAG_HURT) or me["move"] == sim.MOVE_HURT)
        self.job_words(me, car_id)

    def job_words(self, me, car_id):
        """The cash, the chips held, your job in words, the race's countdown."""
        j = self.jobs or {}
        self.cash.setText(f"CASH {me['cash']}")
        chips = me["aux"] >> 8
        self.chips_text.setText(f"{chips} chip{'s' if chips != 1 else ''}: the ARCADE pays" if chips else "")
        mine = (j.get("mine") or {}).get(self.me) or (j.get("mine") or {}).get(str(self.me))
        line, line2, big = "", "", ""
        target = mine.get("target") if mine else None
        far = f"{math.hypot(target[0] - me['x'], target[1] - me['y']):.0f} m" if target else ""
        race = j.get("race")
        if mine and mine["kind"] == "delivery":
            left = mine.get("left", 0)
            line = f"DELIVERY to {mine.get('name', '')}   {far}"
            line2 = f"{left:.0f} s left: stop at the beam" if left > 0 else "LATE: deliver it anyway (or lose it)"
        elif mine and mine["kind"] == "taxi":
            line = (f"TAXI: pick up your passenger at {mine.get('name', '')}" if mine.get("stage") == 1 else
                    f"TAXI: take your passenger to {mine.get('name', '')}") + f"   {far}"
            line2 = "stop by the beam" + ("" if car_id is not None else ": get back in a car")
        elif mine and mine["kind"] == "roundup":
            ru = j.get("roundup") or {}
            line = f"ROUND-UP: {ru.get('left', 0)} rogue robots left"
            line2 = f"{ru.get('ends_in', 0):.0f} s: punch and kick them down (the magenta ones on the map)"
        elif mine and mine["kind"] == "race" and race:
            n = len(race["course"])
            cp = (race.get("cars") or {}).get(str(car_id), 0) if car_id is not None else 0
            if race["state"] == "racing":
                line = f"STREET RACE   checkpoint {min(cp + 1, n)} of {n}" if cp < n else "STREET RACE   back to the line!"
                line2 = "the bright ring is next"
            else:
                line = "STREET RACE: on the grid"
                go = race.get("go_in", 0)
                line2 = f"GO in {go:.0f} s"
                if go <= 3.0:
                    big = str(int(go) + 1) if go > 0.05 else ""
                    if big != getattr(self, "beeped", None):
                        self.beeped = big
                        self.snd.countdown(int(big) if big else 0)
        elif race and race["state"] == "racing" and j.get("phase") is None:
            line = ""
        self.job.setText(line)
        self.job2.setText(line2)
        if target:
            bearing = math.degrees(math.atan2(target[1] - me["y"], target[0] - me["x"]))
            camera_yaw = self.camera.getH(self.render) + 90.0  # (Panda's heading 0 looks along +y: the game's 90)
            self.compass.point(bearing, camera_yaw, city_gfx.JOB_COLOURS.get(mine["kind"], (1, 0.85, 0.2)))
        else:
            self.compass.hide()
        if race and race["state"] == "racing" and mine and mine["kind"] == "race" and race.get("go_in", 1) <= 0.0:
            self.go_shown = getattr(self, "go_shown", 0) + 1
            big = "GO!" if self.go_shown < 50 else ""
        elif not race:
            self.go_shown = 0
        self.countdown.setText("PAUSED" if not OFFLINE and self.paused else big)
        self.banner.setText("KNOCKED DOWN" if me["move"] == sim.MOVE_DOWN else "")


if __name__ == "__main__":
    CityWindow().run()
