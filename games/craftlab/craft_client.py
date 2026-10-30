"""Craft Lab's window (CHANGE 200), for learners and the teacher. Online, the world is craft_server.py's; offline
(--offline, or the app's button with no class) this window runs its own (craft_game.Game, the server's own rules)
and keeps it on this computer between goes.

Learner:  python craft_client.py                      (log in with a username and password in the window)
Teacher:  python craft_client.py --teacher --name "Mr P"
Offline:  python craft_client.py --offline             your own island on this laptop (--sandbox to build freely)

Moving:   WASD walk, the mouse looks, Space jumps (in water: swims up), Shift (held) runs, Ctrl switches Careful
          mode on and off (you won't step off an edge: the CAREFUL tag shows); Sandbox: F flies, then Space up and
          Ctrl down
Blocks:   hold the left button to dig what you look at (a tool for the job digs faster), the right button puts
          what you hold beside it, or uses the block (a Fabricator, a Locker, a Refinery, a door, a Recharge Pod, a
          berry bush, the Craft Bot's dock) or a creature (brush a Fluff, trade with a Bleep); 1 to 8 or the mouse
          wheel choose from the Toolbelt; X throws one (Ctrl+X the stack)
Screens:  I your Backpack (its tabs: Backpack, Blueprints, Bot), B the Bot tab (the Garage, the code, the brain),
          Esc closes a screen or opens the menu (the graphics, saving, the credits, quitting)
Always:   V the view (your eyes, behind you, in front), ` (backtick) the dev panel, F11 full screen, H the key list.
          A game pad works too: the right trigger digs, the left places, A jumps, B Careful mode, X the Backpack,
          Y the Bot tab, the bumpers move along the Toolbelt.

The world is drawn by craft_gfx (every tier, mesh and lines too). Online your own player answers the keys at once:
this window steps it with every key press (craft_sim.step_player, the server's arithmetic) and sends the numbered
inputs; each snapshot says which input the server had applied, and a difference is put right (engine.predict).
Everyone else is drawn blended between snapshots (engine.interp). Digging and placing show at once and are the
server's to keep: one it refuses goes back as it was.
"""
import argparse
import json
import math
import os
import queue
import random
import sys
import time

from panda3d.core import loadPrcFileData

import craft_version
sys.path.insert(0, craft_version.ENGINE_HOME)

ap = argparse.ArgumentParser()
ap.add_argument("--name", default="", help="username (learners are asked in the window if it's left out)")
ap.add_argument("--password", default="", help=argparse.SUPPRESS)
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--host", default=None, help="server address (default: this computer)")
ap.add_argument("--code", help="class code (the demo codes on a laptop test server)")
ap.add_argument("--ticket", help=argparse.SUPPRESS)
ap.add_argument("--offline", action="store_true", help="your own world on this laptop, no server")
ap.add_argument("--experience", type=int, help="play this experience on your own: Craft Lab's own server starts on "
                                               "this laptop (engine/experience.py; the app's EXPERIENCES button)")
ap.add_argument("--sandbox", "--creative", dest="creative", action="store_true",
                help="offline: Sandbox mode (fly, every block, nothing hurts; --creative: its old name)")
ap.add_argument("--seed", type=int, default=None, help="offline: a new world from this seed")
ap.add_argument("--size", default="medium", choices=["small", "medium", "large"])
ap.add_argument("--new", action="store_true", help="offline: a new world (the saved one is kept as a backup)")
ap.add_argument("--time", choices=["dawn", "day", "dusk", "night"], help="offline: the time of day at the start")
ap.add_argument("--no-mobs", action="store_true", help="offline: no creatures")
ap.add_argument("--window", help="the window: 1280x720 ... or full")
ap.add_argument("--gfx", choices=["auto", "mesh", "lines", "basic", "low", "medium", "high", "ultra"], default="auto")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--demo", action="store_true", help="(tests and pictures) walk, look about, dig and place by itself")
ap.add_argument("--pose", help="(tests and pictures) x,y,z,yaw,pitch to stand at and look")
ap.add_argument("--view", choices=["eyes", "behind", "front"], default=None)
ap.add_argument("--no-sound", action="store_true")
ap.add_argument("--fps", action="store_true", help="print the frame rate every second")
ap.add_argument("--fixed-step", action="store_true", help="(pictures) a sixtieth of a second a frame, not the clock")
ap.add_argument("--script", help="(the video) a JSON list of moves to play: walk, look, dig, place, wait, screen")
ap.add_argument("--tab", help="(tests and pictures) open the side panel on this tab: missions, ai, card, settings; "
                              "the teacher's teacher, mods, warnings, limits")
ap.add_argument("--clean", action="store_true", help="(the video) no key list, title, log or welcome on the screen")
ap.add_argument("--no-hand", action="store_true", help="(the video) nothing held in view (a camera's flight)")
args = ap.parse_args()
if os.environ.get("CRAFTLAB_LOGIN") and not args.name:  # reopened by itself: the same login
    try:
        args.name, args.password, *rest = json.loads(os.environ.pop("CRAFTLAB_LOGIN"))
        args.ticket = rest[0] if rest and rest[0] else args.ticket
    except (ValueError, TypeError):
        pass
OFFLINE = bool(args.offline)

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "CraftLab")
BRAINS = (os.path.join(os.path.dirname(sys.executable), "brains", "craftlab") if craft_version.FROZEN
          else os.path.join(HERE, "brains"))
from engine import hud  # noqa: E402
from engine.hud import load_json, remember  # noqa: E402
SETTINGS = hud.setup(SETTINGS_DIR, sys.modules[__name__])
from engine import club_ticket  # noqa: E402
if args.ticket:
    peek = club_ticket.peek(args.ticket) or {}
    args.name = peek.get("name") or args.name
    args.teacher = args.teacher or peek.get("role") == "teacher"
TEACHER = args.teacher
from engine import experience  # noqa: E402
SOLO = None  # (CHANGE 210) an experience on your own: Craft Lab's server on this laptop, started by this window
if args.experience and not TEACHER and not OFFLINE:  # (not --offline: that is this window's own world, no server)
    SOLO = experience.solo_start(HERE, "craft_server.py", "craftlab", args.experience, "CRAFTLAB_DATA",
                                 craft_version.FROZEN)
    if not experience.solo_ready(SOLO):
        experience.solo_stop(SOLO)
        raise SystemExit("Craft Lab's server on this laptop didn't start: " + experience.solo_last_words(SOLO))
    # (not stopped when this window closes: the server stops by itself once the window has gone (solo_watch), after
    # it has kept your island and your profile, which a stop from here would lose)
    args.host, args.code, args.ticket = SOLO["host"], None, None
    args.name, args.password = args.name or experience.SOLO_NAME, experience.SOLO_PASSWORD
if args.host is None:
    args.host = craft_version.SERVER
LOCAL = args.host.startswith(("ws://127.0.0.1", "ws://localhost"))
if args.code or args.ticket:
    code = args.code or ""
elif TEACHER:
    code = os.environ.get("CRAFTLAB_TEACHER_CODE") or ("TEACH99" if LOCAL else "")
else:
    code = "CLUB42" if LOCAL else load_json(os.path.join(SETTINGS_DIR, "settings.json")).get("class_code", "")
name = args.name or ("Teacher" if TEACHER else "You" if OFFLINE else "")
net = None
from engine import gfx_tiers  # noqa: E402
GFX = gfx_tiers.resolve(SETTINGS_DIR, None if args.gfx == "auto" else args.gfx, gfx_tiers.TIERS)
title = f"Craft Lab - {'OFFLINE' if OFFLINE else 'TEACHER' if TEACHER else 'LEARNER'}" + (f" ({name})" if name else "")
if SOLO:
    title = f"Craft Lab - EXPERIENCE {args.experience}"
loadPrcFileData("", hud.window_arg(args.window, 40) + f"window-title {title}\n" + gfx_tiers.prc_for(GFX)
                + "exclude-texture-scale *atlas*\n")
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\nwin-size 1600 900\n")

from direct.gui.DirectGui import DirectEntry, DirectFrame  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import (Camera, ClockObject, Filename, KeyboardButton, MouseButton, NodePath,  # noqa: E402
                          PerspectiveLens, TextNode, WindowProperties)

import craft_blocks as B  # noqa: E402
import craft_brain  # noqa: E402
import craft_design as design  # noqa: E402
import craft_game  # noqa: E402
import craft_mods  # noqa: E402
import craft_panels  # noqa: E402
import craft_gfx as gfx  # noqa: E402
import craft_items as items  # noqa: E402
import craft_models  # noqa: E402
import craft_sim as sim  # noqa: E402
import craft_sound  # noqa: E402
import craft_tabs  # noqa: E402
import craft_ui as ui  # noqa: E402
import craft_world  # noqa: E402
from engine import gamepad, interp, predict, wire  # noqa: E402
from engine import net as net_module  # noqa: E402
from engine.net import Net  # noqa: E402
from engine.experience_hud import ExperienceHud  # noqa: E402  (CHANGE 210)

if OFFLINE:  # (this computer's own mods: its blocks drawn in the atlas, its blueprints built)
    for _msg in craft_mods.use_mods():
        print("Mods not used:", _msg, flush=True)
SCHEMA = wire.Schema("craft", sim.SCHEMA_FIELDS)
SNAP_SPEC = {"entities": ["id", {"x": "lerp", "y": "lerp", "z": "lerp", "yaw": "angle", "pitch": "angle",
                                 "vx": "lerp", "vy": "lerp", "vz": "lerp"}]}
STOP_CODES = (4001, 4004, 4006, 4007, 4008, 4009, 4010, 4011)
KIND_WORLD = 9  # (a binary frame of the world, craft_server.KIND_WORLD)
net_module.OPTIONS["compression"] = None
WORLDS = os.path.join(SETTINGS_DIR, "worlds")
VIEWS = ("eyes", "behind", "front")
MOUSE_SPEED = 0.12          # degrees a pixel
KEYS_TEXT = ("WASD walk   mouse look   Space jump   Shift run   Ctrl careful   left: dig   right: place or use   "
             "1-8 Toolbelt   I Backpack   X throw   V view   Tab lessons   H keys\n"
             "Craft Bot: B the Bot tab (Garage, Code, Brain)   U upload the brain   P autopilot")
TEACHER_KEYS = ("Teacher: T time of day   M creatures   G everyone to me   K a Bot kit for everyone   N Sandbox/Challenge "
                "for everyone   F9 pause")
PLACE_GAP = 0.22
# (CHANGE 210) The experience's boxes (engine/experience_hud.py) clear of the lab visor: the top one under the news
# pill, the coach's above the Toolbelt and the key list; slid left (top, bottom) while a panel is open on the right
XHUD_TOP, XHUD_BOTTOM, XHUD_SLIDE = -0.25, 0.36, (-0.36, -0.55)
TIMES = {"dawn": 0.95, "day": 0.3, "dusk": 0.62, "night": 0.8}


def send(msg):
    if net is not None:
        net.send(msg)


class CraftWindow(craft_tabs.CraftTabs, hud.HudKit, ShowBase):
    teacher, offline = TEACHER, OFFLINE  # (the side panel of lesson tabs: craft_tabs)
    FIRST_TAB = "teacher" if TEACHER else "settings" if OFFLINE else "missions"
    VERSION = craft_version.VERSION

    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()
        self.started = time.perf_counter()
        self.frames = 0
        self.ready = False
        self.login_panel = None
        gfx_tiers.detect(self, SETTINGS_DIR)
        self.tier = gfx.init(self, GFX, line_colour=SETTINGS.get("line_colour"))
        self.snd = craft_sound.Sounds(self, on=not args.no_sound and not args.offscreen)
        hud.setup_app(self, send)
        self.init_hud()
        self.taskMgr.add(self.update, "update")
        if args.screenshot and args.offscreen:  # (a picture never taken, say no world arrived: stop, don't wait forever)
            self.taskMgr.doMethodLater(args.after + 180, self.no_picture, "no_picture")
        if OFFLINE:
            self.start_offline()
        elif TEACHER or args.ticket or (args.name and args.password):
            error = self.connect(name, args.password or "")
            if error:
                self.show_login(error, teacher=TEACHER)
        else:
            self.show_login()

    # ---------- logging in (online) ----------
    def connect(self, username, password):
        global net, name
        try:
            net = Net(args.host, username, code, password=password, version=craft_version.VERSION,
                      **({"ticket": args.ticket} if args.ticket else {}))
        except OSError:
            net = None
            return f"Can't reach the Craft Lab server ({args.host}). Is it running?"
        except Exception as e:
            net = None
            return f"Can't connect to the Craft Lab server ({args.host}): {e}"
        welcome, problem = self.wait_for("welcome")
        if welcome is None:
            net = None
            return problem
        name = welcome.get("name") or username
        self.password = password
        self.early = []
        end, problem = self.wait_for("world", 60)
        if end is None:
            net = None
            return problem or "The server didn't send the world."
        self.start_online(welcome, end)
        return None

    def wait_for(self, kind, seconds=8):
        deadline = time.time() + seconds
        while True:
            try:
                m = net.inbox.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                return None, "No answer from the server."
            if m["type"] == kind:
                return m, ""
            if m["type"] == "binary" and kind == "world":  # (the world comes in binary parts after its header)
                self.early.append(m)
                continue
            if m["type"] == "closed":
                return None, m.get("reason") or "The server closed the connection."
            if kind == "world":
                self.early.append(m)

    def show_login(self, error="", teacher=False):
        if error:
            print(error, flush=True)
        if self.login_panel is not None:
            self.login_panel.destroy()
        self.login_panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))
        f = DirectFrame(parent=self.login_panel, frameColor=hud.PANEL, frameSize=(-0.62, 0.62, -0.5, 0.46))
        hud.label(f, "CRAFT LAB" + ("  -  TEACHER" if teacher else ""), 0, 0.34, 0.08, hud.YELLOW, TextNode.ACenter)
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
            hud.button(f, "LOG IN", 0, -0.2, self.submit_login, None, 0.05, (0.15, 0.55, 0.25, 1))
            hud.label(f, "New here? Choose a username and a password: that makes your profile." if LOCAL else
                      "Use the username and password your teacher gave you.", 0, -0.33, 0.028, hud.GREY, TextNode.ACenter)
            hud.button(f, "Play offline instead", 0, -0.42, self.go_offline, None, 0.032)
        else:
            hud.button(f, "Try again", -0.16, -0.22, self.try_again, (), 0.04, (0.15, 0.55, 0.25, 1))
            hud.button(f, "Close", 0.2, -0.22, self.userExit, (), 0.04)
        self.login_msg = hud.label(f, error, 0, 0.2 if teacher else -0.28, 0.03, hud.RED, TextNode.ACenter, wrap=38)

    def go_offline(self):
        global OFFLINE
        OFFLINE = True
        if self.login_panel is not None:
            self.login_panel.destroy()
            self.login_panel = None
        self.start_offline()

    def try_again(self):
        error = self.connect(name, args.password or "")
        if error:
            self.show_login(error, teacher=True)

    def submit_login(self):
        user, password = self.entries["user"].get().strip(), self.entries["pass"].get()
        if not user:
            self.login_msg.setText("Type your username first.")
            return
        self.login_msg.setText("Logging in...")
        self.login_msg.setFg(hud.GREY)
        self.graphicsEngine.renderFrame()
        error = self.connect(user, password)
        if error and self.login_panel is not None:
            self.login_msg.setText(error)
            self.login_msg.setFg(hud.RED)

    # ---------- starting ----------
    def start_offline(self):
        """Your own world: the one kept on this computer (or a new one), this window running the game."""
        folder = os.path.join(WORLDS, "offline")
        world, extra = (None, {}) if (args.new or args.seed is not None) else craft_world.World.load(folder)
        if world is None:
            seed = args.seed if args.seed is not None else random.randrange(1, 1_000_000)
            t0 = time.perf_counter()
            world = craft_world.World(args.size, seed)
            print(f"Craft Lab: a new world (seed {seed}) in {time.perf_counter() - t0:.1f} s", flush=True)
            extra = {}
        rules = {"mode": "sandbox" if args.creative else "challenge", "mobs": not args.no_mobs}
        self.game = craft_game.Game(world, rules)
        self.game.load_extra(extra)
        saved = (extra.get("players") or {}).get("you")
        p = self.game.add_player(0, name, creative=args.creative, saved=saved)
        if args.time:
            self.game.time = TIMES[args.time] * self.game.rules["day_length"]
        self.save_folder = folder
        self.begin(world, 0)
        self.game.designs[0] = design.fit_design(self.design)
        bot = (extra.get("bots") or {}).get("you")
        if bot and bot.get("dock"):
            self.game.add_bot(0, tuple(bot["dock"]), bot)
        self.me_state = p.state
        self.inventory = self.game.inventory_msg(0)
        self.saved_at = time.perf_counter()
        self.ready = True

    def begin(self, world, me):
        """The world drawn, the camera, the HUD and the keys: online and offline alike."""
        self.world = world
        self.me = me
        aspect = self.getAspectRatio()
        if aspect < 1:  # (a tall window, a phone's video: 72 degrees up and down, not across)
            self.camLens.setFov(math.degrees(2 * math.atan(math.tan(math.radians(36)) * aspect)))
        t0 = time.perf_counter()
        self.world_vis = gfx.WorldVisual(self.render, world)
        cx, cy = world.spawn[0], world.spawn[1]
        self.world_vis.update(cx, cy, first=True)
        print(f"Craft Lab: {len(self.world_vis.chunks)} chunks drawn in {time.perf_counter() - t0:.1f} s, graphics "
              f"{gfx.tier()}", flush=True)
        self.target = gfx.Target(self.render)
        self.particles = gfx.Particles(self.render)
        self.effects = gfx.Effects(self.render) if hasattr(gfx, "Effects") else None
        self.models = {}         # entity id -> craft_models.Model / ItemModel
        self.hud = ui.Hud(self)
        self.screen = None
        self.menu = None
        self.view = args.view or SETTINGS.get("craft_view", "eyes")
        self.yaw, self.pitch = 90.0, -5.0
        self.accum = 0.0
        self.dig_at, self.dig_progress, self.dig_hit = None, 0.0, 0.0
        self.place_at = 0.0
        self.fly = False
        self.careful = False
        self.ctrl_used = False
        self.debug_on = False
        self.blueprint_list = items.blueprints() if OFFLINE else getattr(self, "blueprint_list", items.blueprints())
        self.help_on = True
        self.hurt_until = 0.0
        self.pad = gamepad.Pad(self)
        self.inventory = None
        self.captured = False
        self.step_at = 0.0
        self.bot_panel, self.panel_kind = None, None
        self.offline_brain, self.autopilot = None, False
        self.lesson = getattr(self, "lesson", {}) or {}
        saved = SETTINGS.get("craft_design") if OFFLINE else None
        self.design = getattr(self, "design", None) or (saved if isinstance(saved, dict) and not design.check_design(
            saved, design.full_limits()) else design.default_design(f"{name[:8]} Bot" if name and name != "You" else "Craft Bot"))
        self.bubbles = {}
        self.hand_setup()
        self.keys()
        self.my_name = name or "You"
        self.init_tabs(self.lesson)  # (the side panel: Tab)
        if args.tab:
            self.tab = args.tab
            self.rebuild_panels()
        if args.pose:
            x, y, z, yaw, pitch = (float(v) for v in args.pose.split(","))
            self.pose = (x, y, z)
            self.yaw, self.pitch = yaw, pitch
        else:
            self.pose = None
        self.script = None
        if args.script:
            with open(args.script, encoding="utf-8") as f:
                self.script = Script(self, json.load(f))
        self.capture(True)
        self.started = time.perf_counter()  # (the pictures' and the frame rate's clock: from here, not the world's making)
        self.frames = 0
        self.hud.title.setText(f"CRAFT LAB   {'offline' if OFFLINE else 'TEACHER' if TEACHER else 'online'}: {name}")
        self.hud.keys.setText(KEYS_TEXT + ("\n" + TEACHER_KEYS if TEACHER else ""))
        if args.clean:
            for t in (self.hud.title, self.hud.keys, self.hud.log, self.hud.news, self.full_button):
                t.hide()
        if args.no_hand:
            self.hand_scene.hide()

    def keys(self):
        def key(name, fn, *a):  # (not while typing in a panel's box or editor: the letters are the code's)
            self.accept(name, lambda *x: None if self.busy() else fn(*(a + x)))
        for i in range(items.TOOLBELT):
            key(str(i + 1), self.select, i)
        key("wheel_up", self.wheel, -1)
        key("wheel_down", self.wheel, 1)
        key("i", self.toggle_inventory)
        self.accept("escape", self.escape)
        key("x", self.drop, False)
        key("control-x", self.drop, True)
        key("v", self.cycle_view)
        key("`", self.toggle_debug)
        key("h", self.toggle_help)
        self.accept("f11", self.toggle_full)
        key("f", self.toggle_fly)
        key("control", self.ctrl_down)       # (Ctrl on its own switches Careful mode: on letting it go, if no other
        self.accept("control-up", self.ctrl_up)  # key was pressed with it, Ctrl+X say)
        self.accept("mouse1", self.mouse_down, [1])
        self.accept("mouse3", self.mouse_down, [3])
        key("tab", self.toggle_panel)  # (the lesson tabs: Mission, AI card, My card, Settings; the teacher's Controls)
        key("page_up", self.slide_panel, -1)
        key("page_down", self.slide_panel, 1)
        key("b", self.toggle_inventory, "bot")
        key("u", self.upload_brain)
        key("p", self.toggle_autopilot)
        if OFFLINE:
            key("t", self.offline_time)
        if TEACHER:
            for k, kind in (("t", "time"), ("m", "mobs"), ("g", "gather"), ("f9", "pause"), ("n", "mode"), ("k", "kit")):
                key(k, send, {"type": kind})

    def busy(self):
        """Typing in a box or an editor (a Bot panel's, the side panel's, the Backpack's search or a Locker's name):
        the keys are the words, not the game's."""
        return bool(self.typing) or (self.bot_panel is not None and self.bot_panel.typing()) or \
            (self.screen is not None and self.screen.typing())

    # ---------- the Craft Bot's panels ----------
    def bot_hub(self, kind):
        """The Bot tab's GARAGE, CODE and BRAIN: the Backpack shuts and the panel opens."""
        if self.screen is not None:
            self.act({"type": "close"})
            self.close_screen()
        self.open_panel(kind)

    def open_panel(self, kind):
        """The garage, the code, the brain (from the Bot tab; the same one again closes it)."""
        was = self.panel_kind
        self.close_panel()
        if was == kind:
            return
        d = self.design
        tools = self.lesson.get("tools") or {k: True for k in design.STATS + ("name_and_colour", "code_view",
                                                                              "stats_readout")}
        limits = self.lesson.get("limits") or design.default_limits()
        if kind == "garage":
            self.bot_panel = craft_panels.Garage(self, d, tools, limits)
        elif kind == "code":
            if not tools.get("code_view", True) and not TEACHER:
                self.hud.say("The code view isn't on for this mission yet.", time.perf_counter())
                return
            self.bot_panel = craft_panels.Code(self, d)
            send({"type": "code_viewed"})
        else:
            self.bot_panel = craft_panels.Brain(self, os.path.join(BRAINS, "my_bot.py"))
            self.bot_panel.say(self.brain_status())
        self.panel_kind = kind
        self.capture(False)
        self.place_xhud()

    def close_panel(self):
        if self.bot_panel is not None:
            self.bot_panel.destroy()
            self.bot_panel = None
            self.panel_kind = None
            self.place_xhud()
            if self.screen is None and self.menu is None:
                self.capture(True)

    def act_design(self, d, by_code):
        """BUILD MY BOT: online the server checks it (and the teaching layer sees it); offline it is checked here."""
        if OFFLINE:
            problems = design.check_design(d, design.full_limits() if by_code else design.default_limits())
            if not problems:
                self.design = d
                self.game.designs[self.me] = design.fit_design(d)
                remember("craft_design", d)
            self.design_result({"ok": not problems, "problems": problems, "design": self.design})
        else:
            send({"type": "design", "design": d, "code": by_code})

    def design_result(self, m):
        self.design = m.get("design") or self.design
        if self.bot_panel is not None and hasattr(self.bot_panel, "result"):
            self.bot_panel.result(bool(m.get("ok")), m.get("problems") or [])
        if m.get("ok"):
            self.hud.say(f"{self.design['name']} rebuilt", time.perf_counter(), 2)

    def upload_brain(self):
        """U: brains/my_bot.py to your Craft Bot (offline: run here, safely, in its own process)."""
        path = os.path.join(BRAINS, "my_bot.py")
        if not os.path.exists(path):
            os.makedirs(BRAINS, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(craft_bot_starter())
        with open(path, encoding="utf-8") as f:
            source = f.read()
        if not OFFLINE:
            send({"type": "brain", "source": source})
            return
        try:
            fn, fname = craft_brain.load_brain(source, "you")
        except craft_brain.BrainError as e:
            self.brain_said(f"Not uploaded: {e}", False)
            return
        if self.offline_brain is not None:
            self.offline_brain.close()
        self.offline_brain = craft_brain.Autopilot(fn, fname)
        self.game.bot_brains[self.me] = self.offline_brain if self.autopilot else None
        self.brain_said("Uploaded. Press P to switch the autopilot " + ("off." if self.autopilot else "on."))

    def toggle_autopilot(self):
        if not OFFLINE:
            send({"type": "autopilot"})
            return
        if self.offline_brain is None:
            self.brain_said("Upload your Bot's brain first (U).", False)
            return
        self.autopilot = not self.autopilot
        if self.autopilot:
            self.offline_brain.error = None
            if self.game.bot_of(self.me) is None:
                self.hud.say("Put a BOT DOCK down and right-click it: your Bot comes out on top.", time.perf_counter(), 5)
        self.game.bot_brains[self.me] = self.offline_brain if self.autopilot else None
        self.brain_said("Autopilot on: your Craft Bot is running your brain." if self.autopilot else "Autopilot off.")

    def brain_said(self, text, ok=True):
        self.hud.say(text, time.perf_counter(), 4)
        self.hud.add_log(text)
        if self.bot_panel is not None and self.panel_kind == "brain":
            self.bot_panel.say(text, ok)

    def brain_status(self):
        if OFFLINE:
            b = self.offline_brain
            if b is None:
                return "Not uploaded yet: press SAVE AND UPLOAD."
            if b.error:
                return f"Stopped: {b.error}"
            return "Running on your Bot." if self.autopilot else "Uploaded. Autopilot is off (P)."
        return getattr(self, "brain_words", "Press SAVE AND UPLOAD to send it to your Bot.")

    # ---------- the mouse ----------
    def capture(self, on):
        """The mouse looks about (hidden, kept in the window) or is free for the screens and the menu."""
        self.captured = on
        if args.offscreen or self.win is None:
            return
        props = WindowProperties()
        props.setCursorHidden(on)
        props.setMouseMode(WindowProperties.M_confined if on else WindowProperties.M_absolute)
        self.win.requestProperties(props)
        if on:
            self.centre_mouse()

    def centre_mouse(self):
        if self.win is not None and not args.offscreen:
            self.win.movePointer(0, self.win.getXSize() // 2, self.win.getYSize() // 2)

    def read_mouse(self):
        if not self.captured or args.offscreen or self.win is None:
            return
        if not self.win.getProperties().getForeground():
            return
        p = self.win.getPointer(0)
        cx, cy = self.win.getXSize() // 2, self.win.getYSize() // 2
        dx, dy = p.getX() - cx, p.getY() - cy
        if dx or dy:
            self.yaw = (self.yaw - dx * MOUSE_SPEED) % 360
            self.pitch = max(-89.0, min(89.0, self.pitch - dy * MOUSE_SPEED))
            self.centre_mouse()

    # ---------- keys ----------
    def select(self, i):
        if self.screen is None:
            self.act({"type": "select", "slot": i})

    def wheel(self, step):
        at = self.mouse_at()
        if self.tab and self.panel_bar and at is not None and at[0] > 1.76 - 0.98 * self.text_scale():
            return self.slide_panel(step)  # (over a tall side panel: it slides)
        if self.screen is not None:
            return self.screen.scroll(step)
        if self.inventory:
            self.act({"type": "select", "slot": (self.inventory["selected"] + step) % items.TOOLBELT})

    def toggle_fly(self):
        """F: Sandbox players fly (Space up, Ctrl down) or walk."""
        if not self.creative():
            return
        self.fly = not self.fly
        self.hud.say("Flying: Space up, Ctrl down" if self.fly else "Walking", time.perf_counter(), 1.5)

    def ctrl_down(self):
        self.ctrl_used = False

    def ctrl_up(self):
        if self.ctrl_used or self.busy() or self.fly:
            return
        self.set_careful(not self.careful)

    def set_careful(self, on):
        self.careful = on
        self.hud.set_careful(on)

    def creative(self):
        return bool(self.inventory and self.inventory.get("creative"))

    def toggle_inventory(self, tab="backpack"):
        """I: the Backpack (on its Backpack tab); B: on its Bot tab. Again: it shuts."""
        if self.screen is not None:
            self.act({"type": "close"})
            self.close_screen()
        elif self.menu is None:
            self.act({"type": "tab", "tab": tab})
            self.open_screen(dict(self.inventory or {}, open=None, tab=tab))

    def open_screen(self, msg):
        if self.screen is not None:
            self.screen.destroy()
        self.close_panel()
        self.screen = ui.Screen(self, msg, self.act, self.blueprint_list, self.near_fabricator)
        self.capture(False)
        self.hand_scene.hide()  # (the hand is drawn over everything: it would cover the Backpack's corner)

    def near_fabricator(self):
        """Is a Fabricator within 4 blocks (the Blueprints tab says which need one: the server checks again)?"""
        s = self.me_now()
        x0, y0, z0 = (int(math.floor(v)) for v in (s["x"], s["y"], s["z"] + 1))
        fab = B.ID["fabricator"]
        return any(self.world.get(x0 + dx, y0 + dy, z0 + dz) == fab and
                   math.dist((s["x"], s["y"], s["z"] + 1), (x0 + dx + .5, y0 + dy + .5, z0 + dz + .5)) <= items.REACH + 0.9
                   for dx in range(-4, 5) for dy in range(-4, 5) for dz in range(-4, 5))

    def close_screen(self):
        if self.screen is not None:
            self.screen.destroy()
            self.screen = None
        if not args.no_hand and not self.tab:
            self.hand_scene.show()
        self.capture(True)

    def escape(self):
        if self.typing:
            self.stop_typing()
            return
        if self.tab:
            self.toggle_panel()
            return
        if self.bot_panel is not None:
            self.close_panel()
            return
        if self.screen is not None:
            self.act({"type": "close"})
            self.close_screen()
            return
        if self.menu is not None:
            self.menu.destroy()
            self.menu = None
            self.capture(True)
            return
        self.open_menu()

    def open_menu(self):
        """Esc: the Club Coders logo, resume, the graphics (the window reopens at the tier chosen, your world kept),
        save, the credits (the third-party notices), quit."""
        self.capture(False)
        self.menu = ui.Menu(self, gfx.tier(), gfx_tiers.TIERS, self.escape, self.choose_tier,
                            (lambda: self.save_offline(True)) if OFFLINE else None, self.quit)

    def choose_tier(self, t):
        gfx_tiers.remember(SETTINGS_DIR, gfx_tier=t, gfx_hand=True)
        if OFFLINE:
            self.save_offline()
        argv = []
        for a in sys.argv[1:]:  # (--gfx and its value left out: the new window gets the one chosen)
            if argv and argv[-1] == "--gfx":
                argv.pop()
            elif not a.startswith("--gfx="):
                argv.append(a)
        if argv and argv[-1] == "--gfx":
            argv.pop()
        from engine import reopen
        env = dict(os.environ, CRAFTLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        try:
            reopen.start(__file__, argv + ["--gfx", t], env, frozen=craft_version.FROZEN,
                         log_dir=SETTINGS_DIR if craft_version.FROZEN else HERE)
        except OSError as e:
            print("couldn't reopen:", e, flush=True)
            return
        os._exit(0)

    def quit(self):
        if OFFLINE:
            self.save_offline()
        self.userExit()

    def drop(self, everything):
        if everything:
            self.ctrl_used = True
        if self.screen is None:
            self.act({"type": "drop", "all": everything})

    def cycle_view(self):
        self.view = VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        remember("craft_view", self.view)

    def toggle_debug(self):
        self.debug_on = not self.debug_on
        if not self.debug_on:
            self.hud.dev(None)

    def toggle_help(self):
        self.help_on = not self.help_on
        self.hud.keys.setText((KEYS_TEXT + ("\n" + TEACHER_KEYS if TEACHER else "")) if self.help_on else "")

    def toggle_full(self):
        props = WindowProperties()
        if not self.win.getProperties().getUndecorated():
            props.setSize(self.pipe.getDisplayWidth(), self.pipe.getDisplayHeight())
            props.setUndecorated(True)
            props.setOrigin(0, 0)
        else:
            props.setUndecorated(False)
            props.setSize(1280, 720)
            props.setOrigin(40, 40)
        self.win.requestProperties(props)

    def panel_note(self, text, secs=4):
        self.hud.say(text, time.perf_counter(), secs)

    def tabs_shown(self, shown):
        """The side panel open: the mouse is let go to click in it; shut, it looks about again."""
        if not args.no_hand:  # (the hand is drawn over everything: it would cover the panel's corner)
            self.hand_scene.hide() if shown else self.hand_scene.show()
        if shown:
            self.capture(False)
        elif self.screen is None and self.menu is None and self.bot_panel is None:
            self.capture(True)
        self.place_xhud()

    def place_xhud(self):
        """(CHANGE 210) The experience's boxes over the island: centred, or slid left out of the way of a panel on the
        right (the side panel of lesson tabs, the Bot's Garage, Code or Brain) so the panel's buttons stay clear."""
        x = getattr(self, "xhud", None)
        if x is None:
            return
        right = bool(getattr(self, "tab", None)) or getattr(self, "bot_panel", None) is not None
        x.top_node.setX(XHUD_SLIDE[0] if right else 0.0)
        x.bottom_node.setX(XHUD_SLIDE[1] if right else 0.0)

    def restart_window(self):
        """Reopen this window (Controls: Reopen mine), logged in as the same person."""
        from engine import reopen
        env = dict(os.environ, CRAFTLAB_LOGIN=json.dumps([name, getattr(self, "password", ""), args.ticket or ""]))
        reopen.reopen(__file__, list(sys.argv[1:]), env, frozen=craft_version.FROZEN,
                      log_dir=SETTINGS_DIR if craft_version.FROZEN else HERE)

    def offline_time(self):
        g = self.game
        L = g.rules["day_length"]
        g.time = (math.floor(g.time / L) + (g.day_t + 0.25)) * L
        self.hud.say("The time of day moves on", time.perf_counter(), 1.5)

    def mouse_down(self, button):
        if self.screen is not None or self.menu is not None or self.bot_panel is not None or self.tab:
            return
        if not self.captured:
            self.capture(True)
            return
        if button == 1:
            target = self.mob_in_sight()
            if target is not None:
                self.act({"type": "attack", "target": target})
                self.dig_hit = 0.0
        elif button == 3:
            target = self.mob_in_sight()
            if target is not None and target >= 128:  # (a creature: brush a Fluff, trade with a Bleep)
                self.act({"type": "use_mob", "target": target})
                self.place_at = 0.6
                return
            self.place_at = 0.0  # (a click places at once; holding repeats)

    # ---------- the hand ----------
    def hand_setup(self):
        """What you hold, drawn over the world at the bottom right in its own view (so it never goes into a wall)."""
        self.hand_scene = NodePath("hand scene")
        dr = self.win.makeDisplayRegion()
        dr.setSort(20)
        dr.setClearDepthActive(True)
        cam = Camera("hand camera")
        lens = PerspectiveLens()
        lens.setFov(70)
        lens.setNear(0.01)
        lens.setAspectRatio(self.getAspectRatio())
        cam.setLens(lens)
        self.hand_cam = self.hand_scene.attachNewNode(cam)
        dr.setCamera(self.hand_cam)
        self.hand = self.hand_scene.attachNewNode("hand")
        self.hand.setPos(0.38, 0.78, -0.26)
        gfx.ent_node(self.hand)
        self.hand_item = None
        self.hand_np = None
        self.hand_t = 0.0

    def hand_update(self, dt, s):
        held = self.inventory["inv"][self.inventory["selected"]] if self.inventory else None
        item = held[0] if held else None
        if item != self.hand_item or self.hand_np is None:
            if self.hand_np is not None:
                self.hand_np.removeNode()
            if item is None:
                self.hand_np = gfx.model(self.hand, [((-0.07, -0.07, -0.25), (0.07, 0.07, 0.1), "skin", (1, 1, 1))])
            else:
                size = 0.22 if B.ITEMS.get(item, {}).get("block") is None else 0.13
                self.hand_np = self.hand.attachNewNode(gfx.item_geom(item, size))
                if gfx.look():
                    gfx.line_look.outline(self.hand_np)
                self.hand_np.setHpr(30, 0, -10)
            self.hand_item = item
        self.hand_t += dt * math.hypot(s["vx"], s["vy"])
        bob = math.sin(self.hand_t * 2.2) * 0.02
        swing = 0.0
        if self.dig_at is not None or self.dig_hit > 0:
            swing = math.sin(time.perf_counter() * 14) * 25
        self.hand.setPos(0.38, 0.78, -0.26 + bob)
        self.hand.setP(-abs(swing))
        self.hand.show() if self.view == "eyes" else self.hand.hide()
        gfx.set_here(self.hand, self.world, s["x"], s["y"], s["z"] + 1)

    # ---------- the player's keys ----------
    def read_keys(self):
        """This tick's input: where to go in the world's frame, and the buttons (jump, sprint, sneak, fly)."""
        if args.demo:
            return self.demo_input()
        if self.script is not None:
            return self.script.input()
        if self.mouseWatcherNode is None or self.screen is not None or self.menu is not None or self.busy():
            return (0.0, 0.0, sim.FLY_B if self.fly else 0)
        if not self.win.getProperties().getForeground() and not args.offscreen:
            return (0.0, 0.0, sim.FLY_B if self.fly else 0)
        down = self.mouseWatcherNode.is_button_down
        k = KeyboardButton
        f = float(down(k.asciiKey("w")) or down(k.up())) - float(down(k.asciiKey("s")) or down(k.down()))
        r = float(down(k.asciiKey("d")) or down(k.right())) - float(down(k.asciiKey("a")) or down(k.left()))
        bt = 0
        if down(k.space()):
            bt |= sim.JUMP_B
        if down(k.shift()):
            bt |= sim.SPRINT_B
        pad = self.pad.read()
        if pad:
            if not (f or r):
                f, r = pad.y, pad.x
                if math.hypot(pad.x, pad.y) > 0.95:  # (the stick pushed all the way: run)
                    bt |= sim.SPRINT_B
            if "south" in pad.held:
                bt |= sim.JUMP_B
            for b, act in (("east", lambda: self.set_careful(not self.careful)), ("west", self.toggle_inventory),
                           ("north", lambda: self.toggle_inventory("bot")), ("lb", lambda: self.wheel(-1)),
                           ("rb", lambda: self.wheel(1))):
                if b in pad.pressed:
                    act()
            self.yaw = (self.yaw - pad.rx * 3.0) % 360 if hasattr(pad, "rx") else self.yaw
        if self.fly and self.creative():
            bt |= sim.FLY_B
            if down(k.control()):
                bt |= sim.CAREFUL_B  # (flying: Ctrl goes down)
        else:
            self.fly = False
            if self.careful:
                bt |= sim.CAREFUL_B
        yr = math.radians(self.yaw)
        fx, fy = math.cos(yr), math.sin(yr)
        rx, ry = math.sin(yr), -math.cos(yr)
        mx, my = f * fx + r * rx, f * fy + r * ry
        n = math.hypot(mx, my)
        if n > 1:
            mx, my = mx / n, my / n
        return wire.quantise_input(mx, my, bt)

    def demo_input(self):
        """(tests and pictures) Walk in a slow circle, looking about, jumping now and then."""
        t = time.perf_counter() - self.started
        self.yaw = (90 + t * 12) % 360
        self.pitch = -12 + math.sin(t * 0.7) * 10
        yr = math.radians(self.yaw)
        jump = sim.JUMP_B if (int(t * 2) % 5 == 0) else 0
        return (math.cos(yr) * 0.6, math.sin(yr) * 0.6, jump)

    # ---------- acting ----------
    def act(self, msg):
        """An action: the game's (offline, at once) or the server's."""
        if OFFLINE:
            self.game.action(self.me, msg)
            self.offline_events()
            if msg.get("type") == "select" and self.inventory:  # (the game sends no inventory for a new slot)
                self.inventory["selected"] = msg["slot"] % items.TOOLBELT
        else:
            send(msg)
            self.predict_action(msg)

    def predict_action(self, msg):
        """Online: a dig shown at once (the server's answer puts it right if it says no), the hotbar at once."""
        kind = msg.get("type")
        if kind == "dig":
            x, y, z = msg["x"], msg["y"], msg["z"]
            b = B.BLOCKS[self.world.get(x, y, z)]
            self.world.set(x, y, z, 0, record=False)
            self.particles.burst(x, y, z, b["tiles"][1] if b["tiles"] else "particle")
            self.snd.play("dig_" + str(b["tool"] or "soft"), (x + .5, y + .5, z + .5), sim.eye(self.me_now()))
        elif kind == "select" and self.inventory:
            self.inventory["selected"] = msg["slot"]

    def look_target(self):
        s = self.me_now()
        ex, ey, ez = sim.eye(s)
        dx, dy, dz = sim.look_dir(self.yaw, self.pitch)
        return sim.ray(self.world, ex, ey, ez, dx, dy, dz, sim.REACH_CREATIVE if self.creative() else sim.REACH)

    def mob_in_sight(self):
        """The creature (or player) in the middle of the screen, within reach, nearer than any block."""
        s = self.me_now()
        ex, ey, ez = sim.eye(s)
        dx, dy, dz = sim.look_dir(self.yaw, self.pitch)
        hit = self.look_target()
        limit = min(3.6, hit[2]) if hit else 3.6
        best, bd = None, limit
        for eid, e in self.entities.items():
            if eid == self.me or e.get("kind") in (6,):
                continue
            cx, cy, cz = e["x"] - ex, e["y"] - ey, e["z"] + 0.8 - ez
            along = cx * dx + cy * dy + cz * dz
            if along <= 0 or along > bd:
                continue
            off = math.sqrt(max(0.0, cx * cx + cy * cy + cz * cz - along * along))
            if off < 0.7:
                best, bd = eid, along
        return best

    def dig_and_place(self, dt):
        """The left button held digs what you look at (its time from the block and what you hold); the right
        button puts what you hold beside it, or uses it."""
        if self.screen is not None or self.menu is not None or self.bot_panel is not None or \
                not self.captured and not args.demo and self.script is None:
            self.dig_at = None
            self.target.show(None, 0)
            return
        hit = self.look_target()
        mw = self.mouseWatcherNode
        left = bool(mw and mw.is_button_down(MouseButton.one())) if self.script is None else self.script.left
        right = bool(mw and mw.is_button_down(MouseButton.three())) if self.script is None else self.script.right
        pad = self.pad.state if hasattr(self.pad, "state") else None
        if pad:
            left = left or pad.rt > 0.5
            right = right or pad.lt > 0.5
        self.dig_hit = max(0.0, self.dig_hit - dt)
        if hit is None:
            self.dig_at = None
            self.target.show(None, 0)
        else:
            pos, face, dist = hit
            if left and self.mob_in_sight() is None:
                if self.dig_at != pos:
                    self.dig_at, self.dig_progress = pos, 0.0
                    self.act({"type": "dig_start", "x": pos[0], "y": pos[1], "z": pos[2]})
                held = self.inventory["inv"][self.inventory["selected"]] if self.inventory else None
                t, _ = B.dig_time(self.world.get(*pos), B.ITEMS.get(held[0]) if held else None)
                if t is None:
                    self.dig_progress = 0
                else:
                    self.dig_progress += dt / (0.12 if self.creative() else t)
                    if self.dig_progress >= 1.0:
                        self.act({"type": "dig", "x": pos[0], "y": pos[1], "z": pos[2]})
                        self.dig_at, self.dig_progress = None, 0.0
                        self.dig_hit = 0.15 if self.creative() else 0.0
                    elif self.step_at <= 0:
                        b = B.BLOCKS[self.world.get(*pos)]
                        self.snd.play("dig_" + str(b["tool"] or "soft"), (pos[0] + .5, pos[1] + .5, pos[2] + .5),
                                      sim.eye(self.me_now()), 0.4)
                        self.particles.burst(pos[0], pos[1], pos[2], b["tiles"][1] if b["tiles"] else "particle", 3, 1.5)
                        self.step_at = 0.25
            else:
                self.dig_at, self.dig_progress = None, 0.0
            self.target.show(pos, self.dig_progress)
            if right:
                self.place_at -= dt
                if self.place_at <= 0:
                    self.place_at = PLACE_GAP
                    self.act({"type": "right", "x": pos[0], "y": pos[1], "z": pos[2], "face": list(face)})
        if hit is None and right:
            self.place_at -= dt
            if self.place_at <= 0:
                self.place_at = PLACE_GAP * 2
                self.act({"type": "use_item"})
        if not right:
            self.place_at = 0.0


    # ---------- online: the world from the server ----------
    def start_online(self, welcome, end):
        """The server's welcome and its world (the parts that came before its end marker): the world built, the
        game begun."""
        if self.login_panel is not None:
            self.login_panel.destroy()
            self.login_panel = None
        props = WindowProperties()
        props.setTitle(f"Craft Lab - EXPERIENCE {args.experience}" if SOLO else
                       f"Craft Lab - {'TEACHER' if TEACHER else 'LEARNER'} ({name})")
        if self.win is not None and not args.offscreen:
            self.win.requestProperties(props)
        self.lesson = welcome.get("lesson") or {}
        self.design = welcome.get("design") or design.default_design()
        self.game_rules = welcome.get("game_rules") or {}
        self.take_mods(welcome.get("mods"))
        early = getattr(self, "early", [])
        self.early = []
        world = self.assemble_world(early)
        self.online_state()
        self.day_t = float(end.get("time", 0.3))
        self.begin(world, welcome.get("me"))
        if getattr(self, "xhud", None) is None:  # (CHANGE 210) an experience, drawn over the island when one is on
            self.xhud = ExperienceHud(self, send, TEACHER, XHUD_TOP, XHUD_BOTTOM)
            self.place_xhud()
        self.me_state = sim.new_player(*world.spawn)
        for m in early:  # (what came in while the world did: the inventory, the state...)
            if m.get("type") not in ("binary", "world_head"):
                self.server_message(m)
        if TEACHER:
            self.hud.say("Teacher: T time of day, M creatures, G everyone to you, K a Bot kit for everyone, "
                         "N Sandbox or Challenge, F9 pause", time.perf_counter(), 8)
        if welcome.get("new_profile"):
            self.hud.say(f"Welcome, {name}! Your profile is made: next time log in with the same username and "
                         "password.", time.perf_counter(), 7)
        self.ready = True

    def take_mods(self, blocks):
        """Mods' blocks from the server (the learners' own): into the block list, and drawn in the atlas."""
        added = False
        for b in blocks or []:
            if isinstance(b, dict) and b.get("key") and b["key"] not in B.ID:
                B.add_block({"key": b["key"], "name": b.get("name", b["key"]), "colour": b.get("colour"),
                             "hard": b.get("hard", 1.0), "light": b.get("light", 0), "tool": b.get("tool")})
                added = True
        if added:
            gfx.refresh_atlas()

    @staticmethod
    def assemble_world(messages):
        head = next((m for m in messages if m.get("type") == "world_head"), None)
        if head is None:
            raise RuntimeError("the server's world had no header")
        parts = {}
        for m in messages:
            if m.get("type") == "binary" and m["data"][:1] == bytes([KIND_WORLD]):
                parts[int.from_bytes(m["data"][1:3], "little")] = m["data"][3:]
        data = b"".join(parts[i] for i in sorted(parts))
        n = head["blocks_len"]
        return craft_world.World.unpack({"size": head["size"], "seed": head["seed"], "spawn": head["spawn"],
                                         "blocks": data[:n], "meta": data[n:]})

    def online_state(self):
        self.snaps = interp.Snapshots(SNAP_SPEC)
        self.predictor = None
        self.draw_from = None
        self.smoother = predict.ErrorSmoother(remove_up=False)
        self.lead = predict.LeadController()
        self.snap_seq = 0
        self.next_seq = 1
        self.sent_at = {}
        self.names = {}
        self.ping_ms, self.ctrl_ms = 0.0, None
        self.last_ping = self.perf_at = self.look_at = 0.0
        self.reconnecting, self.reconnect_thread = False, None
        self.paused = False
        self.entities = {}

    def online_frame(self, now, dt):
        """Online, every frame: the server's messages, our ticks (each one an input sent), what to draw (the others
        blended between snapshots, our own player where the prediction has it), and the time of day."""
        if net is not None:
            self.read_network()
        self.accum = min(15 * sim.STEP, self.accum + dt / self.lead.multiplier())
        while self.accum >= sim.STEP:
            self.accum -= sim.STEP
            self.client_tick(now)
        if now - self.last_ping > 1:
            self.last_ping = now
            send({"type": "ping", "t": time.time()})
        if now - self.look_at > 0.1:
            self.look_at = now
            send({"type": "look", "yaw": round(self.yaw, 1), "pitch": round(self.pitch, 1)})
        self.send_perf(now)
        blended = self.snaps.sample(now)
        drawn = {e["id"]: e for e in blended["entities"]} if blended else {}
        if self.predictor is not None:
            mine = dict(self.predictor.state)
            f = self.accum / sim.STEP
            if self.draw_from is not None:
                for k in ("x", "y", "z"):
                    mine[k] = self.draw_from[k] + (mine[k] - self.draw_from[k]) * f
            (ox, oy, oz), _ = self.smoother.offset(dt)
            mine["x"], mine["y"], mine["z"] = mine["x"] + ox, mine["y"] + oy, mine["z"] + oz
            mine["id"] = self.me
            drawn[self.me] = mine
            self.me_state = mine
        elif self.me in drawn:
            self.me_state = drawn[self.me]
        self.entities = drawn
        length = (self.game_rules or {}).get("day_length", craft_game.DAY_SECONDS)
        if (self.game_rules or {}).get("time_runs", True) and not self.paused:
            self.day_t = (self.day_t + dt * getattr(self, "time_speed", 1.0) / length) % 1.0
        return self.day_t

    def step_fn(self):
        world = self.world

        def step(s, inp, dt):
            n = sim.step_player(s, inp, dt, world, self.creative())
            n.update(SCHEMA.quantise(n))  # (as the server does: the same numbers next tick)
            return n
        return step

    def on_snapshot(self, snap, rx, newest=True):
        self.snap_seq = snap["seq"]
        self.snaps.push(snap, rx)
        self.lead.feed(snap["flags"] >> 4)
        if not newest:
            return
        ents = {e["id"]: e for e in snap["entities"]}
        me = ents.get(self.me)
        if me is None:
            return
        state = {k: me[k] for k in me if k != "id"}
        newest_seq = self.predictor.log.newest() if self.predictor is not None else None
        if newest_seq is not None and predict.seq_diff(snap["ack"], newest_seq) > 3:
            self.next_seq = (snap["ack"] + 3 + int(self.ping_ms / 1000 / sim.STEP)) & predict.SEQ_MASK
            self.predictor = None
        if self.predictor is None:
            self.predictor = predict.Predictor(self.step_fn(), state, ignore=0.05,
                                               log=predict.InputLog(first_seq=self.next_seq))
            self.pred_first = self.next_seq
            self.draw_from = state
            self.smoother.clear()
            self.accum = 0.0
            return
        if snap["ack"] == 0 or predict.seq_diff(snap["ack"], self.pred_first) < 0:
            return
        for k in ("hp", "energy", "shield", "held"):  # (the server's own: Health, Energy and Shield aren't predicted)
            self.predictor.state[k] = state[k]
        err = self.predictor.correct(state, snap["ack"], sim.STEP, sim.compare)
        moved = self.predictor.moved_from
        if moved is not None:
            new, f = self.predictor.state, self.draw_from
            self.draw_from = new if err == math.inf or f is None else dict(
                f, x=f["x"] + new["x"] - moved["x"], y=f["y"] + new["y"] - moved["y"], z=f["z"] + new["z"] - moved["z"])
            if err != math.inf:
                self.smoother.add((moved["x"] - new["x"], moved["y"] - new["y"], moved["z"] - new["z"]), 0.0)
        sent = self.sent_at.get(snap["ack"])
        if sent is not None and rx:
            ms = (rx - sent) * 1000
            self.ctrl_ms = ms if self.ctrl_ms is None else self.ctrl_ms * 0.8 + ms * 0.2

    def client_tick(self, now):
        if self.predictor is None or self.paused:
            return
        inp = self.read_keys()
        self.draw_from = self.predictor.state
        seq = self.predictor.apply(inp, sim.STEP, now)
        prev = self.predictor.log.previous(2)
        self.next_seq = self.predictor.log.next_seq
        self.sent_at[seq] = now
        if len(self.sent_at) > 128:
            for k in sorted(self.sent_at)[:64]:
                del self.sent_at[k]
        send(wire.pack_input(seq, self.snap_seq, int(now * 1000) & 0xFFFFFFFF, inp[0], inp[1], inp[2], previous=prev))

    def read_network(self):
        messages = []
        while True:
            try:
                messages.append(net.inbox.get_nowait())
            except queue.Empty:
                break
        snaps = [i for i, m in enumerate(messages) if m["type"] == "binary" and wire.kind_of(m["data"]) == wire.KIND_SNAPSHOT]
        joining = None
        for i, m in enumerate(messages):
            if joining is not None:  # (a new world arriving: everything until its end marker is part of it)
                joining.append(m)
                if m.get("type") == "world":
                    self.change_world(joining)
                    joining = None
                continue
            if m["type"] == "binary":
                if i in snaps:
                    self.on_snapshot(wire.unpack_snapshot(SCHEMA, m["data"]), m.get(interp.RECEIVED), newest=i == snaps[-1])
            elif m["type"] == "world_head":
                joining = [m]
            else:
                self.server_message(m)
        if joining is not None:
            self.joining = joining

    def change_world(self, messages):
        """A new world from the server (the teacher made one, or after the server restarted): drawn again."""
        self.world_vis.destroy()
        for m in self.models.values():
            m.destroy()
        self.models = {}
        self.world = self.assemble_world(messages)
        self.world_vis = gfx.WorldVisual(self.render, self.world)
        self.world_vis.update(self.world.spawn[0], self.world.spawn[1], first=True)
        self.predictor = None
        self.snaps = interp.Snapshots(SNAP_SPEC)

    def server_message(self, m):
        kind = m.get("type")
        now = time.perf_counter()
        if kind == "inventory":
            self.inventory = m if "inv" in m else None  # (a teacher with no player in the world gets an empty one)
            if m.get("open") and (self.screen is None or self.screen.kind != m["open"]):
                self.open_screen(m)
            elif self.screen is not None:
                self.screen.update(m)
        elif kind == "blocks":
            mine = self.dig_at
            self.world.apply_changes([tuple(c) for c in m.get("list") or []])
            self.dig_at = mine
        elif kind == "say":
            self.hud.say(m.get("text", ""), now)
            self.hud.add_log(m.get("text", ""))
        elif kind == "news":
            self.hud.say(m.get("text", ""), now, 5)
            self.hud.add_log(m.get("text", ""))
        elif kind == "sound":
            at = m.get("at") or [0, 0, 0]
            self.snd.play(m.get("name", ""), tuple(at), sim.eye(self.me_now()), m.get("v", 1.0))
        elif kind == "burst":
            at = m.get("at") or [0, 0, 0]
            self.particles.burst(at[0], at[1], at[2], m.get("tile") or "particle", m.get("n"))
        elif kind == "bubble":
            self.bubbles[m.get("id")] = (str(m.get("text", ""))[:40], now + 4)
        elif kind == "state":
            self.day_t = float(m.get("t", self.day_t))
            self.time_speed = float(m.get("speed", 1.0))
            self.paused = bool(m.get("paused"))
            self.game_rules = m.get("rules") or self.game_rules
        elif kind == "roster":
            for pid, info in (m.get("players") or {}).items():
                self.names[int(pid)] = info.get("name")
                self.names[f"colour {int(pid)}"] = info.get("colour")
                self.names[f"wear {int(pid)}"] = info.get("wear")
            for bid, info in (m.get("bots") or {}).items():
                self.names[int(bid)] = info.get("name")
                self.names[f"colour {int(bid)}"] = info.get("colour")
        elif kind == "lesson":
            self.took_lesson(m)
            self.take_mods(m.get("blocks"))
        elif kind == "design_result":
            self.design_result(m)
        elif kind == "blueprints":
            items.blueprints_changed()  # (the list as the server has it: the mods' ones after the built-in ones)
            self.blueprint_list = [dict(bp) for bp in m.get("list") or []] or items.blueprints()
        elif kind == "bot_status":
            self.bot_status = m
        elif kind in ("armed", "ring", "streak"):
            self.effect(kind, *(list(m.get("at") or [0, 0, 0]) + list(m.get("more") or [])))
        elif kind == "brain_result":
            self.brain_words = ("Uploaded. " if m.get("ok") else "Not uploaded: ") + str(m.get("error") or "")
            self.brain_said(self.brain_words, bool(m.get("ok")))
        elif kind == "missions":
            if not m.get("for"):
                self.took_missions(m)
        elif kind in ("experience", "experience_class") and getattr(self, "xhud", None) is not None:  # (CHANGE 210)
            was = self.xhud.m is not None
            self.xhud.took(m)
            if TEACHER and self.tab == "teacher" and was != (self.xhud.m is not None):
                self.rebuild_panels(from_game=True)  # (the Controls tab's START or END)
        elif kind == "ai_card_result":
            self.card_result(m)
        elif kind == "warnings":
            self.took_warnings(m)
            self.rebuild_panels(from_game=True)
        elif kind == "live_update":
            self.needs_restart = True
            self.hud.say("A live update is ready on the class server: press Restart server (Controls).", now, 12)
        elif kind == "notice":
            self.hud.say(m.get("text", ""), now, 12 if m.get("big") else 5)
            self.hud.add_log(m.get("text", ""))
            if "Autopilot" in m.get("text", ""):
                self.brain_words = m["text"]
        elif kind == "welcome":  # (back after a dropped connection, or a new world on its way)
            self.reconnecting = False
            self.me = m.get("me", self.me)
            self.lesson = m.get("lesson") or self.lesson
            self.predictor = None
            self.snaps = interp.Snapshots(SNAP_SPEC)
            if not m.get("new_world"):
                self.hud.say("Reconnected: carry on!", now, 3)
        elif kind == "restart_client":
            self.hud.say("The teacher reopened the windows.", now, 3)
        elif kind == "pong":
            self.ping_ms = (time.time() - m["t"]) * 1000
        elif kind == "closed":
            self.connection_lost(m)

    def send_perf(self, now):
        if now - self.perf_at < 3:
            return
        self.perf_at = now
        rep = self.snaps.report()
        send({"type": "perf", "fps": round(self.clock.getAverageFrameRate()), "ping": round(self.ping_ms),
              "tier": gfx.tier(), "stalls": rep["stalls"], "delay": rep["delay_ms"],
              "ctrl": None if self.ctrl_ms is None else round(self.ctrl_ms),
              "corr": self.predictor.corrections if self.predictor else None})
        if args.offscreen and self.predictor:
            print("perf corr", self.predictor.corrections, flush=True)

    def connection_lost(self, m):
        if m.get("code") == 4005:
            self.hud.say("You logged in again in another window, so this one has stopped.", time.perf_counter(), 3600)
            return
        if m.get("code") in STOP_CODES:
            self.hud.say(m.get("reason") or "The server closed the connection.", time.perf_counter(), 3600)
            if m.get("code") == 4009:
                self.taskMgr.doMethodLater(5, lambda t: self.userExit(), "session_over")
            return
        self.hud.say("Lost the connection: reconnecting...", time.perf_counter(), 3600)
        self.reconnecting = True
        self.predictor = None
        if self.reconnect_thread is not None and self.reconnect_thread.is_alive():
            return
        import threading

        def work():
            time.sleep(1.0 + random.random() * 2.0)
            while not net.reconnect():
                time.sleep(1.5 + random.random())
        self.reconnect_thread = threading.Thread(target=work, daemon=True)
        self.reconnect_thread.start()

    # ---------- offline: the game here ----------
    def offline_events(self):
        g = self.game
        g.world.take_changes()
        for ev in g.events:
            self.event(ev)
        g.events = []

    def event(self, ev):
        now = time.perf_counter()
        kind = ev[0]
        if kind == "say" and ev[1] == self.me:
            self.hud.say(ev[2], now)
            self.hud.add_log(ev[2])
        elif kind == "news":
            self.hud.say(ev[1], now, 5)
            self.hud.add_log(ev[1])
        elif kind == "sound":
            self.snd.play(ev[1], ev[2:5], sim.eye(self.me_now()), ev[5] if len(ev) > 5 else 1.0)
        elif kind == "burst":
            self.particles.burst(ev[1], ev[2], ev[3], ev[4], ev[5])
        elif kind == "inv" and ev[1] == self.me:
            self.inventory = self.game.inventory_msg(self.me) if OFFLINE else self.inventory
            if self.screen is not None and self.inventory:
                self.screen.update(self.inventory)
        elif kind == "open" and ev[1] == self.me:
            self.inventory = self.game.inventory_msg(self.me) if OFFLINE else self.inventory
            self.open_screen(self.inventory)
        elif kind == "box":
            if self.screen is not None and OFFLINE:
                self.inventory = self.game.inventory_msg(self.me)
                self.screen.update(self.inventory)
        elif kind == "bubble":
            self.bubbles[ev[1]] = (ev[2], time.perf_counter() + 4)
        elif kind in ("armed", "ring", "streak"):
            self.effect(kind, *ev[1:])

    def effect(self, kind, *at):
        """An Overload Cell armed (it pulses magenta), its pulse (a ring of cyan sparks), a Glitch pulled home."""
        if self.effects is not None:
            getattr(self.effects, kind)(*at)
        elif kind == "ring":
            self.particles.burst(at[0] - 0.5, at[1] - 0.5, at[2] - 0.5, "spark", 40)

    def me_now(self):
        return self.me_state

    def offline_tick(self, inp):
        g = self.game
        p = g.players[self.me]
        p.look = (self.yaw, self.pitch)
        if self.pose is not None:
            p.state.update(x=self.pose[0], y=self.pose[1], z=self.pose[2], vx=0.0, vy=0.0, vz=0.0)
        g.step({self.me: inp})
        self.me_state = p.state
        self.offline_events()

    def save_offline(self, say=False):
        g = self.game
        extra = g.save_extra()
        extra["players"] = {"you": g.players[self.me].to_save()}
        bot = g.bot_of(self.me)
        if bot is not None:
            extra["bots"] = {"you": bot.to_save()}
        try:
            g.world.save(self.save_folder, extra)
            if say:
                self.hud.say("Your world is saved on this computer.", time.perf_counter())
        except OSError as e:
            print("couldn't save the world:", e, flush=True)

    # ---------- the frame ----------
    def update(self, task):
        now = time.perf_counter()
        dt = 1 / 60 if args.fixed_step else min(ClockObject.getGlobalClock().getDt(), 0.1)
        self.frames += 1
        if not self.ready:
            return task.cont
        self.read_mouse()
        self.step_at -= dt
        if OFFLINE:
            self.accum = min(self.accum + dt, 0.25)
            while self.accum >= sim.STEP:
                self.accum -= sim.STEP
                self.offline_tick(self.read_keys())
            g = self.game
            self.entities = {pid: dict(q.state, id=pid) for pid, q in g.players.items()}
            self.entities.update({mid: dict(m["s"], id=mid) for mid, m in g.mobs.mobs.items()})
            self.entities.update({eid: {"id": eid, "kind": 6, "x": it["x"], "y": it["y"], "z": it["z"], "held": it["item"],
                                        "vx": 0.0, "vy": 0.0, "vz": 0.0, "yaw": 0.0, "pitch": 0.0, "flags": 0}
                                  for eid, it in g.items.items()})
            for bid, bot in g.bots.items():
                self.entities[bid] = dict(bot.state, id=bid)
            day_t = g.day_t
            self.inventory = self.inventory or g.inventory_msg(self.me)
            if now - self.saved_at > 60:
                self.saved_at = now
                self.save_offline()
        else:
            day_t = self.online_frame(now, dt)
        s = self.me_now()
        self.dig_and_place(dt)
        self.place_camera(s, dt)
        cam = self.camera.getPos(self.render)
        gfx.set_time(self, day_t) if abs(day_t - gfx._state.get("time", 0)) > 0.0005 else None
        gfx.tick(self, dt, cam)
        self.world_vis.update(cam.x, cam.y)
        self.sync_models(dt)
        self.particles.update(dt)
        if self.effects is not None:
            self.effects.update(dt)
        self.hand_update(dt, s)
        self.overlay(s, now)
        if self.screen is not None:
            self.screen.follow_mouse(now)
        self.snd.set_music("music_night" if craft_game.DUSK <= day_t < craft_game.DAWN else "music_day")
        if self.script is not None:
            self.script.tick(dt)
        if args.fps and now - getattr(self, "fps_at", 0) > 1:
            print(f"fps {self.clock.getAverageFrameRate():.0f}", flush=True)
            self.fps_at = now
        if args.screenshot and now - self.started > args.after and self.frames > 5:
            self.shot()
        self.frames_since = getattr(self, "frames_since", 0) + 1
        return task.cont

    def no_picture(self, task):
        print(f"screenshot NOT taken: no world after {args.after + 180:.0f} s", flush=True)
        os._exit(3)

    def shot(self):
        path = os.path.abspath(args.screenshot)
        if not self.win.saveScreenshot(Filename.fromOsSpecific(path)):
            print(f"screenshot NOT saved: {path}", flush=True)
        print(f"screenshot: {path} ({self.frames / (time.perf_counter() - self.started):.0f} fps over the run)",
              flush=True)
        if OFFLINE and not args.offscreen and not args.demo:
            self.save_offline()
        if net is not None:
            net.goodbye()
        self.userExit()

    def place_camera(self, s, dt):
        ex, ey, ez = sim.eye(s)
        if s["flags"] & sim.F_SLEEP:
            ez = s["z"] + 0.4
        self.camera.setHpr(self.yaw - 90.0, self.pitch, 0)
        if self.view == "eyes":
            self.camera.setPos(ex, ey, ez)
            return
        dx, dy, dz = sim.look_dir(self.yaw, self.pitch)
        back = -1 if self.view == "behind" else 1
        dist = 4.5
        # (behind: over your head and a little to the right, looking past you; front: facing you)
        rx, ry = math.sin(math.radians(self.yaw)) * 0.6, -math.cos(math.radians(self.yaw)) * 0.6
        ox, oy, oz = (dx * back + (rx if back < 0 else 0)), (dy * back + (ry if back < 0 else 0)), dz * back + 0.35
        n = math.sqrt(ox * ox + oy * oy + oz * oz)
        ox, oy, oz = ox / n, oy / n, oz / n
        hit = sim.ray(self.world, ex, ey, ez, ox, oy, oz, dist)
        if hit is not None:
            dist = max(0.6, hit[2] - 0.3)
        self.camera.setPos(ex + ox * dist, ey + oy * dist, ez + oz * dist)
        if self.view == "front":
            self.camera.lookAt(ex, ey, ez)
        else:
            self.camera.lookAt(ex + dx * 6, ey + dy * 6, ez + dz * 6)

    def sync_models(self, dt):
        """A model for each player, creature and dropped thing near enough to see (not your own, in your eyes)."""
        cam = self.camera.getPos(self.render)
        reach = gfx.view_distance() * 0.8
        for eid in list(self.models):
            if eid not in self.entities:
                self.models.pop(eid).destroy()
        names = getattr(self, "names", {})
        for eid, e in self.entities.items():
            if eid == self.me and self.view == "eyes":
                if eid in self.models:
                    self.models.pop(eid).destroy()
                continue
            far = (e["x"] - cam.x) ** 2 + (e["y"] - cam.y) ** 2 > reach * reach
            m = self.models.get(eid)
            if far:
                if m is not None:
                    self.models.pop(eid).destroy()
                continue
            kind = e.get("kind", 0)
            if m is None:
                if kind == 6:
                    m = craft_models.ItemModel(self.render, e.get("held", 0))
                else:
                    kname = craft_models.KIND_NAMES.get(kind, "player")
                    if OFFLINE:
                        who = (self.game.players[eid].name if eid in self.game.players else
                               self.design["name"] if kname == "bot" else None)
                        colour = self.design["colour"] if kname == "bot" else (60, 130, 230)
                    else:
                        who, colour = names.get(eid), names.get(f"colour {eid}") or (60, 130, 230)
                    m = craft_models.Model(self.render, kname, colour,
                                           who if kname in ("player", "bot") and eid != self.me else None)
                self.models[eid] = m
            m.update(e, dt, self.world)
            if kind == 0 and hasattr(m, "wear"):
                if OFFLINE:
                    q = self.game.players.get(eid)
                    m.wear([a[0] if a else 0 for a in q.suit] if q is not None else ())
                else:
                    m.wear(names.get(f"wear {eid}") or ())
            said = self.bubbles.get(eid)
            if said is not None and hasattr(m, "say"):
                m.say(said[0] if time.perf_counter() < said[1] else None)

    def overlay(self, s, now):
        """The HUD: the Toolbelt, Health, Energy and Shield, the crosshair's ring (digging, or your air under water),
        Careful mode, the Bot's line, the dev panel."""
        inv = self.inventory
        creative = self.creative()
        if inv:
            self.hud.set_toolbelt(inv["inv"], inv["selected"], now)
        ex, ey, ez = sim.eye(s)
        head = self.world.get(int(math.floor(ex)), int(math.floor(ey)), int(math.floor(ez)))
        wet = head == B.ID["water"]
        if OFFLINE:
            air = self.game.players[self.me].air
        else:  # (the server keeps your air: the window counts it the same way to show it)
            dt = min(0.1, now - getattr(self, "air_at", now))
            self.air = max(0.0, getattr(self, "air", craft_game.AIR) - dt) if wet else \
                min(craft_game.AIR, getattr(self, "air", craft_game.AIR) + dt * 4)
            air = self.air
        self.air_at = now
        self.hud.set_life(s["hp"], s.get("energy", 100), s.get("shield", 0), (inv or {}).get("shield_max", 0), creative,
                          bool(s["flags"] & sim.F_HURT))
        self.hud.set_ring(self.dig_progress if self.dig_at is not None else 0.0, air, craft_game.AIR, wet and not creative)
        self.hud.set_careful(self.careful and not self.fly)
        self.hud.set_bot(self.bot_words())
        if hasattr(gfx, "set_held_light"):
            held = inv["inv"][inv["selected"]] if inv else None
            glow = B.ITEMS.get(held[0], {}).get("glow", 0) if held else 0
            gfx.set_held_light(glow, (ex, ey, ez))
        self.hud.tick(now)
        if self.debug_on and now - getattr(self, "dev_at", 0) > 0.25:
            self.dev_at = now
            t = self.game.day_t if OFFLINE else self.day_t
            phase = ("day" if t < craft_game.DUSK else "dusk" if t < craft_game.NIGHT else "night" if t < craft_game.DAWN
                     else "dawn")
            cx, cy = int(s["x"]) // 16, int(s["y"]) // 16
            xi, yi, zi = int(math.floor(ex)), int(math.floor(ey)), int(math.floor(ez))
            light = (int(self.world.sky[xi, yi, zi]), int(self.world.glow[xi, yi, zi])) if self.world.inside(xi, yi, zi) \
                else (0, 0)
            self.hud.dev(f"POSITION  x {s['x']:.1f}  y {s['y']:.1f}  z {s['z']:.1f}\n"
                         f"          looking {self.yaw:.0f} {self.pitch:.0f}\n"
                         f"CHUNK     {cx}, {cy}   ({len(self.world_vis.chunks)} drawn, {len(self.world_vis.todo)} to draw)\n"
                         f"LIGHT     sky {light[0]}  block {light[1]}  (of {B.LIGHT_MAX})\n"
                         f"FPS       {self.clock.getAverageFrameRate():.0f}\n"
                         f"TIER      {gfx.tier()}\n"
                         f"SERVER    " + ("offline (this computer)" if OFFLINE else
                                          f"ping {self.ping_ms:.0f} ms   things {len(self.entities)}") +
                         f"\nTIME      {t:.3f} ({phase})")

    def bot_words(self):
        """The status card's Bot line: what your Craft Bot is doing ("Bot: digging, 12 placed")."""
        if OFFLINE:
            bot = self.game.bot_of(self.me)
            if bot is None:
                return ""
            doing, st, running = (bot.action[0] if bot.action else "waiting"), bot.stats, \
                bool(bot.brain and not bot.brain.error)
        else:
            m = getattr(self, "bot_status", None)
            if not m:
                return ""
            doing, st, running = m.get("doing", "waiting"), m.get("stats") or {}, m.get("running")
        words = {"dig": "digging", "place": "building", "forward": "moving", "back": "moving", "up": "moving",
                 "down": "moving", "left": "turning", "right": "turning", "bump": "bumped", "wait": "thinking"}
        what = words.get(doing, doing) if running else "parked"
        return f"Bot: {what}, {st.get('dug', 0)} dug, {st.get('placed', 0)} placed"


class Script:
    """(the video) Moves played one after another: ["walk", seconds, forward, right, buttons], ["look", yaw, pitch,
    seconds], ["dig", seconds], ["place", seconds], ["select", slot], ["wait", seconds], ["screen", tab], ["close"],
    ["say", text], ["time", day_t], ["view", eyes|behind|front], ["pose", x, y, z], ["rift", forward, right],
    ["rules", {...}], ["calm"], and spawn, set, act, build, put, attack, call, dock, give (see step)."""

    def __init__(self, app, moves):
        self.app, self.moves = app, list(moves)
        self.left = self.right = False
        self.move = None
        self.t = 0.0
        self.walk = (0.0, 0.0, 0)
        self.look_from = None

    def input(self):
        yr = math.radians(self.app.yaw)
        f, r, b = self.walk
        return (f * math.cos(yr) + r * math.sin(yr), f * math.sin(yr) - r * math.cos(yr), b)

    def tick(self, dt):
        """Moves that take no time (set, give, select...) all happen this frame, up to the next one that does."""
        for _ in range(500):
            self.step(dt)
            if self.move is not None or not self.moves:
                return
            dt = 0.0  # (the frame's time went to the move that just ended)

    def step(self, dt):
        app = self.app
        if self.move is None:
            if not self.moves:
                return
            self.move = self.moves.pop(0)
            self.t = 0.0
            self.look_from = (app.yaw, app.pitch)
            kind = self.move[0]
            if kind == "select":
                app.act({"type": "select", "slot": int(self.move[1])})
                self.move = None
                return
            if kind == "screen":  # (["screen", "backpack" | "blueprints" | "bot"]: the Backpack on that tab)
                tab = self.move[1] if len(self.move) > 1 and self.move[1] in ("backpack", "blueprints", "bot") else "backpack"
                app.toggle_inventory(tab)
                self.move = None
                return
            if kind == "close":
                app.escape() if app.screen is not None else None
                self.move = None
                return
            if kind == "say":
                app.hud.say(self.move[1], time.perf_counter(), 4)
                self.move = None
                return
            if kind == "time" and OFFLINE:
                app.game.time = float(self.move[1]) * app.game.rules["day_length"]
                self.move = None
                return
            if kind == "view":
                app.view = self.move[1]
                self.move = None
                return
            if kind == "pose" and OFFLINE:
                st = app.game.players[app.me].state
                st.update(x=float(self.move[1]), y=float(self.move[2]), z=float(self.move[3]), vx=0.0, vy=0.0, vz=0.0)
                self.move = None
                return
            if kind == "spawn" and OFFLINE:  # (a creature this far ahead of you and to the side)
                st = app.game.players[app.me].state
                yr = math.radians(app.yaw)
                f, r = float(self.move[2]), float(self.move[3])
                x, y = st["x"] + f * math.cos(yr) + r * math.sin(yr), st["y"] + f * math.sin(yr) - r * math.cos(yr)
                z = app.world.top(int(x), int(y)) + 1
                app.game.mobs.add(self.move[1], x, y, float(z))
                self.move = None
                return
            if kind == "set" and OFFLINE:  # (a block this far ahead and to the side, at this height above your feet)
                st = app.game.players[app.me].state
                yr = math.radians(app.yaw)
                f, r, up = float(self.move[2]), float(self.move[3]), int(self.move[4])
                x, y = st["x"] + f * math.cos(yr) + r * math.sin(yr), st["y"] + f * math.sin(yr) - r * math.cos(yr)
                app.world.set(int(math.floor(x)), int(math.floor(y)), int(math.floor(st["z"])) + up, B.ID[self.move[1]])
                self.move = None
                return
            if kind == "rift" and OFFLINE:  # (a Glitch rift this far ahead and to the side: ["rift", f, r])
                st = app.game.players[app.me].state
                yr = math.radians(app.yaw)
                f, r = float(self.move[1]), float(self.move[2])
                x = int(math.floor(st["x"] + f * math.cos(yr) + r * math.sin(yr)))
                y = int(math.floor(st["y"] + f * math.sin(yr) - r * math.cos(yr)))
                app.game.make_rift(x, y, app.world.top(x, y))
                app.offline_events()
                self.move = None
                return
            if kind == "calm" and OFFLINE:  # (the video: every rift closed and every creature gone, for a clean shot)
                for rid in list(app.game.rifts):
                    app.game.close_rift(rid)
                app.game.mobs.mobs.clear()
                app.offline_events()
                self.move = None
                return
            if kind == "rules" and OFFLINE:  # (["rules", {"blasts": true}]: the lesson's rules changed)
                app.game.rules.update(self.move[1])
                self.move = None
                return
            if kind == "act":  # (an action as the window sends it: a click in a screen, a right click...)
                app.act(dict(self.move[1]))
                self.move = None
                return
            if kind == "build" and OFFLINE:  # (blocks put down one after another, from where you stand: [f, r, up])
                st = app.game.players[app.me].state
                yr = math.radians(app.yaw)
                cells = []
                for f, r, up in self.move[2]:
                    x = int(math.floor(st["x"] + f * math.cos(yr) + r * math.sin(yr)))
                    y = int(math.floor(st["y"] + f * math.sin(yr) - r * math.cos(yr)))
                    cells.append((x, y, int(math.floor(st["z"])) + up))
                self.moves[0:0] = [["put", self.move[1], c] for c in cells]
                self.move = None
                return
            if kind == "put" and OFFLINE:
                x, y, z = self.move[2]
                p = app.game.players[app.me]
                slot = next((i for i, sl in enumerate(p.inv) if sl and sl[0] == B.ITEM_ID[self.move[1]]), None)
                if slot is not None:
                    app.act({"type": "select", "slot": slot % items.TOOLBELT}) if slot < items.TOOLBELT else None
                    p.selected = slot if slot < items.TOOLBELT else p.selected
                app.act({"type": "right", "x": x, "y": y, "z": z - 1, "face": [0, 0, 1]})
                self.move = ["wait", 0.09]
                self.t = 0.0
                return
            if kind == "attack":
                target = app.mob_in_sight()
                if target is not None:
                    app.act({"type": "attack", "target": target})
                self.move = None
                return
            if kind == "call":  # (a key's job: upload_brain, toggle_autopilot, open_panel...)
                getattr(app, self.move[1])(*self.move[2:])
                self.move = None
                return
            if kind == "dock" and OFFLINE:  # (a Bot dock this far ahead, used: the Bot comes out)
                st = app.game.players[app.me].state
                yr = math.radians(app.yaw)
                f, r = float(self.move[1]), float(self.move[2])
                x, y = int(math.floor(st["x"] + f * math.cos(yr) + r * math.sin(yr))),                     int(math.floor(st["y"] + f * math.sin(yr) - r * math.cos(yr)))
                z = int(math.floor(st["z"]))
                app.world.set(x, y, z, B.ID["dock"])
                app.game.use_block(app.me, x, y, z)
                app.offline_events()
                self.move = None
                return
            if kind == "give" and OFFLINE:
                items.add(app.game.players[app.me].inv, B.ITEM_ID[self.move[1]], int(self.move[2]))
                app.game.inv_changed(app.me)
                app.offline_events()
                self.move = None
                return
        kind = self.move[0]
        self.t += dt
        if kind == "walk":
            secs, f, r, b = self.move[1], self.move[2], self.move[3], self.move[4] if len(self.move) > 4 else 0
            self.walk = (f, r, b)
            if self.t >= secs:
                self.walk = (0.0, 0.0, 0)
                self.move = None
        elif kind == "look":
            yaw, pitch, secs = self.move[1], self.move[2], max(0.01, self.move[3])
            k = min(1.0, self.t / secs)
            e = k * k * (3 - 2 * k)
            y0, p0 = self.look_from
            dy = (yaw - y0 + 180) % 360 - 180
            app.yaw = (y0 + dy * e) % 360
            app.pitch = p0 + (pitch - p0) * e
            if k >= 1:
                self.move = None
        elif kind in ("dig", "place"):
            self.left, self.right = kind == "dig", kind == "place"
            if self.t >= self.move[1]:
                self.left = self.right = False
                self.move = None
        elif kind == "wait":
            if self.t >= self.move[1]:
                self.move = None


def craft_bot_starter():
    import craft_bot
    return craft_bot.STARTER


if __name__ == "__main__":
    CraftWindow().run()
