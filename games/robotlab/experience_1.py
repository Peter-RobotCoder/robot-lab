"""EXPERIENCE 1: ORIENTATION (CHANGE 197). A one-player first session for Club Coders, in Robot Lab's arena: the
classic opening mission of a first-person game, with a coach, objectives one at a time, XP and ranks, but the
skills are a club coder's: drive, use your weapon, change your robot's VARIABLES (a string, an integer, a list),
rebuild it, read it as Python code, hand it to a BRAIN (autopilot), and win your first bout.

    python experience_1.py                      play it (or 20 Experience 1.bat; the Club Coders app's first screen)
    python experience_1.py --robot razorback    start with another robot from mods/robots

No server and no login: anyone can play it, on their own, on any laptop. The best result is kept on this computer
(RobotLab/experience_1.json: the XP, the rank, the stars, the quickest time).

Keys:   arrows or WASD drive   Space weapon   F unstick   G garage (your robot's variables)   C code (your robot as Python)
        P autopilot (brains/my_brain.py drives; the starter brain if yours won't load)   V view   wheel zoom
        N skip this objective (no XP: for a teacher showing the class)   R start again   H help   Esc quit
Tests:  --offscreen --selftest (plays it through by itself and checks every objective; experience_test.py)
        --screenshot X.png --after 8    --objective 6 (start at that objective, for pictures)
"""
import argparse
import json
import math
import os
import sys
import time

from panda3d.core import loadPrcFileData

ap = argparse.ArgumentParser()
ap.add_argument("--robot", default="titan", help="your robot (a file in mods/robots)")
ap.add_argument("--gfx", default="medium", choices=["mesh", "lines", "basic", "low", "medium", "high", "ultra"])
ap.add_argument("--window", default="1600x900", help="the window, as 1920x1080")
ap.add_argument("--no-sound", action="store_true")
ap.add_argument("--progress", help="where the best result is kept (a JSON file)")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=8)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--selftest", action="store_true", help="play it through by itself, check each objective, then quit")
ap.add_argument("--objective", type=int, default=1, help="(tests and pictures) start at this objective")
ap.add_argument("--name", default="", help=argparse.SUPPRESS)  # (the app passes these to every game: not used)
ap.add_argument("--host", default=None, help=argparse.SUPPRESS)
args = ap.parse_args()

try:
    WIN_W, WIN_H = (int(v) for v in args.window.lower().split("x"))
except ValueError:
    WIN_W, WIN_H = 1600, 900
loadPrcFileData("", f"win-size {WIN_W} {WIN_H}\nwindow-title EXPERIENCE 1: ORIENTATION - Club Coders\n"
                    "framebuffer-multisample 1\nmultisamples 4\nsync-video true\n")
import lab_version  # noqa: E402
sys.path.insert(0, lab_version.ENGINE_HOME)  # (the engine package, shared by every game)
from engine import club_fonts, editor, gfx_tiers, schema  # noqa: E402
club_fonts.use_default()  # (the windows' letters: Inter, SIL OFL, not Panda3D's own unlicensed font)
loadPrcFileData("", gfx_tiers.prc_for(args.gfx))
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\nwin-size 1600 900\naudio-library-name null\n")

from direct.gui.DirectGui import DGG, DirectButton, DirectEntry, DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, Point3, TextNode, TransparencyAttrib, Vec3  # noqa: E402

import cpu_brains  # noqa: E402
import lab_sim as sim  # noqa: E402
import rw_fx  # noqa: E402
import rw_gfx  # noqa: E402
import rw_mods  # noqa: E402
from engine import rw_mesh, rw_sound  # noqa: E402
from rw_camera import GameCamera  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RobotLab")
PROGRESS = args.progress or os.path.join(SETTINGS_DIR, "experience_1.json")
BRAINS = (os.path.join(os.path.dirname(sys.executable), "brains", "robotlab") if lab_version.FROZEN
          else os.path.join(HERE, "brains"))
YELLOW, WHITE, GREY, RED, GREEN, ORANGE, BLUE = (1, .85, .2, 1), (1, 1, 1, 1), (.7, .75, .85, 1), (1, .35, .3, 1), \
    (.4, .95, .5, 1), (1, .55, .15, 1), (.45, .75, 1, 1)
PANEL = (0.02, 0.025, 0.04, 0.85)
COACH = "CC-01"  # the coach: Club Coders' own training robot, who talks you through it
# the ranks: the XP you need for each
RANKS = [(0, "Rookie"), (60, "Cadet"), (150, "Engineer"), (240, "Coder"), (320, "Club Coder")]
RINGS = [(-5.0, 5.0), (5.0, 5.0), (5.0, -5.0)]  # the waypoints, in order
RING_R = 1.4
SWATCHES = [(235, 110, 20), (200, 20, 28), (40, 120, 230), (40, 170, 80), (230, 200, 40), (160, 70, 200)]
BOUT_SECONDS = 60
TRAINING_HAZARDS = dict(pit=False, floor_flipper=False, saws=False, spikes=False, house_robots=False)

# The objectives, in order: (id, title, what the coach says, the hint under it, XP)
OBJECTIVES = [
    ("drive", "Wake up", "Systems online. Let's see you move: drive forward with the arrows or W.",
     "Drive 4 metres", 10),
    ("turn", "Steering", "Good. Now turn on the spot: hold left or right until you've spun right round.",
     "Turn through 360 degrees", 10),
    ("rings", "Waypoints", "Three glowing rings on the floor. Drive through them in order: each one lights the next.",
     "Drive through the rings, 1, 2, 3", 30),
    ("weapon", "Weapons check", "Every robot starts with its weapon off. Space fires it (or switches a spinner on).",
     "Fire your weapon 3 times", 15),
    ("dummy", "Target practice", "That's the training dummy. Drive at it and hit it: ram it, flip it, fire at it.",
     "Land 3 hits on the dummy", 30),
    ("garage", "Variables", "Your robot is made of VARIABLES. Press G for the garage: change its name (a STRING), "
                            "its forward speed (an INTEGER) and its colour (a LIST), then press REBUILD.",
     "Change a string, an integer and a list, then REBUILD", 45),
    ("code", "Read the code", "Everything in the garage is Python code. Press C and find the variables you just "
                              "changed: robot_name: str, forward_speed: int, colour: list.",
     "Open the code (C) and read it for 4 seconds", 20),
    ("brain", "Brains", "A BRAIN is a Python function that drives for you. Press P to switch on autopilot and watch it "
                        "drive your robot (brains/my_brain.py; mine if yours won't load).",
     "Autopilot on for 8 seconds", 30),
    ("bout", "First bout", "Ready for a real one? SPARKY, my sparring robot, 60 seconds. Autopilot's off: this one's "
                           "you. Knock it out or have more armour left when the time's up. Stuck? F puts you back on "
                           "your wheels.",
     "Win the bout (a knockout scores a bonus)", 60),
]
BOUT_KO_BONUS = 25


def rank_of(xp):
    name = RANKS[0][1]
    for need, title in RANKS:
        if xp >= need:
            name = title
    return name


def next_rank(xp):
    return next(((need, title) for need, title in RANKS if need > xp), None)


def load_progress(path=PROGRESS):
    try:
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        return p if isinstance(p, dict) else {}
    except (OSError, ValueError):
        return {}


def save_progress(result, path=PROGRESS):
    """The best result kept: the most XP, the most stars, the quickest finish, and how many times it was finished."""
    p = load_progress(path)
    best = {"best_xp": max(p.get("best_xp", 0), result["xp"]), "best_stars": max(p.get("best_stars", 0), result["stars"]),
            "rank": rank_of(max(p.get("best_xp", 0), result["xp"])), "finished": p.get("finished", 0) + 1,
            "best_time": min([t for t in (p.get("best_time"), result["seconds"]) if t]), "last": result}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(best, f, indent=1)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
    return best


def ring_mesh(colour):
    """A ring lying on the floor, and a soft beam of light standing in it."""
    m = rw_mesh.Mesh(colours=True)
    m.colour = colour
    n = 40
    r0, r1 = RING_R - 0.18, RING_R
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        m.poly([Vec3(math.cos(a0) * r0, math.sin(a0) * r0, 0), Vec3(math.cos(a1) * r0, math.sin(a1) * r0, 0),
                Vec3(math.cos(a1) * r1, math.sin(a1) * r1, 0), Vec3(math.cos(a0) * r1, math.sin(a0) * r1, 0)],
               normal=Vec3(0, 0, 1))
    beam = rw_mesh.Mesh(colours=True)
    beam.colour = colour[:3] + (0.18,)
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        r = RING_R - 0.1
        beam.poly([Vec3(math.cos(a0) * r, math.sin(a0) * r, 0), Vec3(math.cos(a1) * r, math.sin(a1) * r, 0),
                   Vec3(math.cos(a1) * r, math.sin(a1) * r, 2.2), Vec3(math.cos(a0) * r, math.sin(a0) * r, 2.2)],
                  normal=Vec3(math.cos(a0), math.sin(a0), 0))
    return m, beam


class Experience(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        robots, self.arena_mod, self.rules = rw_mods.load_all()
        self.robots_mods = robots
        self.design = dict(robots.get(args.robot) or robots["titan"])
        self.design["points"] = dict(self.design["points"])
        self.design["settings"] = dict(self.design["settings"])
        self.start_design = json.loads(json.dumps(self.design))
        rw_gfx.init(self, args.gfx)
        self.fx = rw_fx.Effects(self.render, "low" if args.gfx in ("basic", "low") else args.gfx)
        self.snd = rw_sound.Sounds(self, on=not args.no_sound and not args.offscreen)
        look = dict(self.arena_mod["look"], name="CLUB CODERS TRAINING", crowd=False)
        self.arena_vis = rw_gfx.ArenaVisual(self.render, TRAINING_HAZARDS, look)
        self.cam = GameCamera(self, "third")
        for key, factor in (("wheel_up", 0.88), ("wheel_down", 1 / 0.88), ("=", 0.8), ("+", 0.8), ("-", 1.25)):
            self.accept(key, self.cam.wheel, [factor])
        for key, fn in (("v", self.cam.cycle), ("g", self.toggle_garage), ("c", self.toggle_code),
                        ("p", self.toggle_autopilot), ("n", self.skip), ("r", self.restart_run), ("h", self.toggle_help),
                        ("escape", self.escape), ("space", self.fire_pressed), ("f", self.unstick)):
            self.accept(key, fn)
        self.typing = False
        self.garage = self.code_panel = None
        self.code_state = {"lines": [], "cursor": [0, 0], "scroll": 0}
        self.build_hud()
        self.start = self.last = time.perf_counter()
        self.frames = 0
        self.new_run()
        self.checks = self.selftest() if args.selftest else None
        self.taskMgr.add(self.update, "update")

    # ---------- a run through the experience ----------
    def new_run(self):
        if getattr(self, "arena", None):
            for v in self.vis.values():
                v.destroy()
            self.close_brain()
        for ring in getattr(self, "rings", []):
            ring.removeNode()
        self.design = json.loads(json.dumps(self.start_design))
        self.arena = sim.Arena(hazards=TRAINING_HAZARDS)
        self.arena.practice = False
        self.player = self.arena.add_robot(self.design, brain=None, owner="YOU", start=3)
        self.place(self.player, (0.0, -3.0), 0.0)  # (out from the wall, so the camera behind you has room)
        self.dummy = None
        self.cpu = None
        self.vis = {self.player.id: rw_gfx.RobotVisual(self.render, self.player.design)}
        self.vis[self.player.id].set_label("YOU", (1, 1, 1, 1))
        self.rings, self.ring_n = [], 0
        self.xp, self.done = 0, []
        self.objective = 0
        self.obj_start = 0.0
        self.run_start = time.perf_counter()
        self.accum = 0.0
        self.travelled, self.turned, self.last_xy, self.last_h = 0.0, 0.0, None, None
        self.fires, self.fire_counts = 0, {}
        self.garage_changes = set()
        self.rebuilt = False
        self.code_open_for = 0.0
        self.autopilot, self.brain, self.brain_note, self.autopilot_for = False, None, "", 0.0
        self.bout_time, self.bout_result = 0.0, None
        self.finished = None
        self.toasts = []
        self.last_hp = {}
        self.flash = {}
        self.close_panels()
        self.result_card.hide()
        while self.objective + 1 < args.objective:  # (tests and pictures: straight to a later objective)
            self.complete(skipped=True)
        self.begin_objective()

    @staticmethod
    def place(robot, xy, heading):
        """A robot put somewhere other than its start spot (and that is where it starts again from)."""
        robot.start = (Point3(xy[0], xy[1], 0.5), heading)
        robot.reset()

    def restart_run(self):  # (not restart: ShowBase has one of its own, which it calls as it starts)
        if self.typing:
            return
        self.snd.stop_all()
        self.new_run()

    @property
    def obj(self):
        return OBJECTIVES[self.objective] if self.objective < len(OBJECTIVES) else None

    def begin_objective(self):
        o = self.obj
        self.obj_start = self.arena.time
        if o is None:
            return self.finish()
        oid = o[0]
        if oid == "rings":
            self.show_rings()
        if oid in ("dummy", "garage", "code", "brain") and self.dummy is None:
            d = sim.default_design("DUMMY", (190, 190, 200), "wedge")
            d["points"] = {"speed": 5, "attack": 5, "armour": 50, "control": 40}
            self.dummy = self.arena.add_robot(d, brain=None, owner="DUMMY", start=4)
            self.place(self.dummy, (0.0, 3.5), 180.0)
            self.vis[self.dummy.id] = rw_gfx.RobotVisual(self.render, d)
            self.vis[self.dummy.id].set_label("TRAINING DUMMY", (0.8, 0.85, 0.95, 1))
            self.dummy_start = self.dummy.health
        if oid == "dummy":
            self.hits_start = self.player.hits
        if oid == "bout":
            self.start_bout()
        self.say(o[2])
        self.update_checklist()

    def complete(self, skipped=False):
        o = self.obj
        if o is None:
            return
        self.done.append((o[0], not skipped))
        if not skipped:
            before = rank_of(self.xp)
            gain = o[4] + (BOUT_KO_BONUS if o[0] == "bout" and self.bout_result == "ko" else 0)
            self.xp += gain
            self.toast(f"+{gain} XP   {o[1].upper()} COMPLETE", GREEN)
            self.snd.play("horn" if o[0] == "bout" else "beep", 0.5)
            if rank_of(self.xp) != before:
                self.toast(f"RANK UP: {rank_of(self.xp).upper()}", YELLOW, big=True)
                self.snd.react("cheer", time.perf_counter())
        self.objective += 1
        if o[0] == "rings":
            for ring in self.rings:
                ring.removeNode()
            self.rings = []

    def skip(self):
        if self.typing or self.obj is None:
            return
        self.toast(f"Skipped: {self.obj[1]} (no XP)", GREY)
        self.complete(skipped=True)
        self.begin_objective()

    # ---------- the objectives' checks, every tick ----------
    def check_objective(self):
        o = self.obj
        if o is None:
            return
        oid, p = o[0], self.player
        done = False
        if oid == "drive":
            done = self.travelled >= 4.0
        elif oid == "turn":
            done = self.turned >= 360.0
        elif oid == "rings":
            if self.ring_n < len(RINGS):
                x, y = RINGS[self.ring_n]
                if math.hypot(p.pos.x - x, p.pos.y - y) < RING_R:
                    self.ring_n += 1
                    self.snd.play("beep", 0.6, 1.0 + 0.2 * self.ring_n)
                    self.light_rings()
            done = self.ring_n >= len(RINGS)
        elif oid == "weapon":
            done = self.fires >= 3
        elif oid == "dummy":
            done = self.dummy is not None and self.player.hits - self.hits_start >= 3
        elif oid == "garage":
            done = self.rebuilt and {"string", "integer", "list"} <= self.garage_changes
        elif oid == "code":
            done = self.code_open_for >= 4.0
        elif oid == "brain":
            done = self.autopilot_for >= 8.0
        elif oid == "bout":
            done = self.bout_result in ("ko", "win")
            if self.bout_result == "lost":
                self.say("Not this time: SPARKY came out on top. Have another go: press B for a rematch.")
                self.bout_result = "waiting"
        if done:
            self.complete()
            self.begin_objective()

    def track_moves(self):
        p = self.player
        xy = (p.pos.x, p.pos.y)
        h = p.np.getH()
        if self.last_xy is not None and not self.autopilot:
            self.travelled += math.hypot(xy[0] - self.last_xy[0], xy[1] - self.last_xy[1])
            self.turned += abs((h - self.last_h + 180) % 360 - 180)
        self.last_xy, self.last_h = xy, h
        if p.fires > self.fire_counts.get("me", 0):
            self.fires += p.fires - self.fire_counts.get("me", 0)
        self.fire_counts["me"] = p.fires
        if self.code_panel is not None and self.obj and self.obj[0] == "code":
            self.code_open_for += sim.STEP
        if self.autopilot and self.brain is not None and not getattr(self.brain, "error", None):
            self.autopilot_for += sim.STEP

    def unstick(self):
        """F: back on your wheels (or back at your start if you've gone over the edge)."""
        if not self.typing and self.finished is None:
            self.player.fix()
            self.toast("Back on your wheels", GREY)

    def fire_pressed(self):
        if self.typing or self.autopilot:
            return
        if self.player.weapon in sim.TOGGLE_WEAPONS:  # (a spinner is switched on and off: that counts as using it)
            self.fires += 1

    # ---------- the rings ----------
    def show_rings(self):
        self.rings = []
        for i, (x, y) in enumerate(RINGS):
            m, beam = ring_mesh((0.3, 0.9, 1.0, 1.0))
            root = self.render.attachNewNode(f"ring {i + 1}")
            root.attachNewNode(m.node(f"ring {i + 1}"))
            b = root.attachNewNode(beam.node(f"beam {i + 1}"))
            b.setTransparency(TransparencyAttrib.MAlpha)
            b.setDepthWrite(False)
            b.setTwoSided(True)
            root.setPos(x, y, 0.03)
            root.setLightOff(1)
            root.setShaderOff(1)
            t = TextNode(f"ring label {i + 1}")
            t.setText(str(i + 1))
            t.setAlign(TextNode.ACenter)
            t.setTextColor(1, 1, 1, 1)
            lab = root.attachNewNode(t)
            lab.setPos(0, 0, 2.6)
            lab.setScale(0.9)
            lab.setBillboardPointEye()
            self.rings.append(root)
        self.light_rings()

    def light_rings(self):
        for i, ring in enumerate(self.rings):
            if i < self.ring_n:
                ring.setColorScale(0.3, 1.0, 0.4, 0.35)
            elif i == self.ring_n:
                ring.setColorScale(1, 1, 1, 1)
            else:
                ring.setColorScale(0.4, 0.4, 0.5, 0.5)

    # ---------- the garage: the robot's variables ----------
    def toggle_garage(self):
        if self.typing:
            return
        if self.garage is not None:
            return self.close_garage()
        self.close_code()
        f = self.garage = DirectFrame(parent=self.a2dTopRight, frameColor=PANEL, frameSize=(-1.02, -0.04, -1.2, -0.08))
        OnscreenText("GARAGE: your robot as variables", pos=(-0.98, -0.15), scale=0.042, fg=YELLOW,
                     align=TextNode.ALeft, parent=f)
        d = self.design
        OnscreenText("STRING   robot_name: str", pos=(-0.98, -0.25), scale=0.032, fg=BLUE, align=TextNode.ALeft, parent=f)
        self.name_box = DirectEntry(parent=f, scale=0.045, pos=(-0.98, 0, -0.33), width=12, initialText=d["name"],
                                    numLines=1, frameColor=(0.9, 0.9, 0.9, 1), command=self.name_typed,
                                    focusInCommand=self.start_typing, focusOutCommand=self.end_typing)
        OnscreenText("(type a new name, then Enter)", pos=(-0.42, -0.33), scale=0.024, fg=GREY, align=TextNode.ALeft,
                     parent=f)
        OnscreenText("INTEGER   forward_speed: int", pos=(-0.98, -0.43), scale=0.032, fg=BLUE, align=TextNode.ALeft,
                     parent=f)
        self.speed_text = OnscreenText("", pos=(-0.62, -0.51), scale=0.045, fg=WHITE, parent=f, mayChange=True)
        for i, delta in enumerate((-10, -1, 1, 10)):
            DirectButton(parent=f, text=f"{delta:+d}", scale=0.04, pos=(-0.92 + i * 0.12 + (0.2 if i > 1 else 0), 0, -0.52),
                         command=self.change_speed, extraArgs=[delta], relief=DGG.FLAT, pad=(0.3, 0.2),
                         frameColor=(0.16, 0.3, 0.42, 1), text_fg=WHITE)
        OnscreenText("LIST   colour: list = [red, green, blue]", pos=(-0.98, -0.62), scale=0.032, fg=BLUE,
                     align=TextNode.ALeft, parent=f)
        for i, c in enumerate(SWATCHES):
            DirectButton(parent=f, text="", frameSize=(-0.05, 0.05, -0.05, 0.05), pos=(-0.92 + i * 0.13, 0, -0.71),
                         frameColor=tuple(v / 255 for v in c) + (1,), relief=DGG.FLAT, command=self.set_colour,
                         extraArgs=[list(c)])
        self.colour_text = OnscreenText("", pos=(-0.98, -0.81), scale=0.03, fg=WHITE, align=TextNode.ALeft, parent=f,
                                        mayChange=True)
        DirectButton(parent=f, text="REBUILD MY ROBOT", scale=0.05, pos=(-0.53, 0, -0.95), command=self.rebuild,
                     relief=DGG.FLAT, pad=(0.4, 0.25), frameColor=(0.15, 0.55, 0.25, 1), text_fg=WHITE)
        self.garage_note = OnscreenText("", pos=(-0.53, -1.07), scale=0.028, fg=GREY, parent=f, mayChange=True,
                                        wordwrap=34)
        OnscreenText("G closes the garage", pos=(-0.53, -1.15), scale=0.024, fg=GREY, parent=f)
        self.update_garage()

    def update_garage(self):
        if self.garage is None:
            return
        d = self.design
        self.speed_text.setText(str(d["settings"]["forward_speed"]))
        c = d["colour"]
        self.colour_text.setText(f"colour = [{c[0]}, {c[1]}, {c[2]}]")
        have = self.garage_changes
        self.garage_note.setText("Changed: " + (", ".join(sorted(have)) if have else "nothing yet") +
                                 ("" if {"string", "integer", "list"} <= have else
                                  "   (a string, an integer and a list)"))

    def start_typing(self):
        self.typing = True

    def end_typing(self):
        self.typing = False

    def name_typed(self, text):
        text = "".join(ch for ch in text if ch.isalnum() or ch == " ").strip()[:16]
        if text and text != self.design["name"]:
            self.design["name"] = text
            self.garage_changes.add("string")
        if getattr(self, "name_box", None) is not None and self.name_box.get() != self.design["name"]:
            self.name_box.enterText(self.design["name"])
        self.typing = False
        self.update_garage()

    def change_speed(self, delta):
        lo, hi = sim.SETTINGS["forward_speed"][:2]
        v = max(lo, min(hi, self.design["settings"]["forward_speed"] + delta))
        if v != self.design["settings"]["forward_speed"]:
            self.design["settings"]["forward_speed"] = v
            self.garage_changes.add("integer")
        self.update_garage()

    def set_colour(self, colour):
        if colour != self.design["colour"]:
            self.design["colour"] = colour
            self.garage_changes.add("list")
        self.update_garage()

    def rebuild(self):
        """The robot made again from its variables, where it stands (checked as the server checks a design)."""
        if self.garage is not None and self.name_box is not None:
            self.name_typed(self.name_box.get())
        problems = sim.check_design(self.design, sim.full_limits())
        if problems:
            self.say("That design won't build: " + "; ".join(problems))
            return
        p = self.player
        pos, h = Point3(p.pos), p.np.getH()
        self.vis.pop(p.id).destroy()
        self.arena.remove_robot(p)
        hits = self.player.hits
        self.player = self.arena.add_robot(json.loads(json.dumps(self.design)), brain=None, owner="YOU", start=3)
        self.player.hits = hits
        self.player.np.setPos(pos.x, pos.y, 0.5)
        self.player.np.setH(h)
        self.vis[self.player.id] = rw_gfx.RobotVisual(self.render, self.player.design)
        self.vis[self.player.id].set_label("YOU", (1, 1, 1, 1))
        self.last_xy = None
        self.rebuilt = True
        self.fire_counts["me"] = self.player.fires
        self.snd.play("pneumatic", 0.5)
        self.toast(f"REBUILT: {self.design['name']}", BLUE)
        self.update_garage()
        if self.autopilot:
            self.player.brain = self.brain

    def close_garage(self):
        if self.garage is not None:
            self.garage.destroy()
            self.garage = None
            self.name_box = None
        self.typing = False

    # ---------- the code: the robot as Python ----------
    def code_ctx(self):
        from types import SimpleNamespace
        return SimpleNamespace(title="MY ROBOT", points_total=sim.POINTS_TOTAL, weapons=list(sim.WEAPONS),
                               all_weapons=list(sim.WEAPONS), house={}, rules={}, model=None, makers={})

    def toggle_code(self):
        if self.typing:
            return
        if self.code_panel is not None:
            return self.close_code()
        self.close_garage()
        f = self.code_panel = DirectFrame(parent=self.a2dTopRight, frameColor=PANEL, frameSize=(-1.32, -0.04, -1.55, -0.08))
        OnscreenText("CODE: your robot as Python (read only here)", pos=(-1.28, -0.15), scale=0.04, fg=YELLOW,
                     align=TextNode.ALeft, parent=f)
        lines = schema.code_lines(sim.schema(), self.player.design, self.code_ctx())
        self.code_state = {"lines": lines, "cursor": [0, 0], "scroll": 0}
        want = ("robot_name", "forward_speed", "colour")
        first = next((i for i, line in enumerate(lines) if line.startswith(want)), 0)
        self.code_state["scroll"] = max(0, first - 3)
        self.code_editor = editor.CodeEditor(self, f, self.code_state, -1.28, -0.22, 1.2, 28, 0.024, read_only=True)
        OnscreenText("Find robot_name, forward_speed and colour. The mouse wheel scrolls.  C closes the code.",
                     pos=(-0.68, -1.5), scale=0.026, fg=GREY, parent=f)

    def close_code(self):
        if self.code_panel is not None:
            ed = getattr(self, "code_editor", None)
            if ed is not None:
                ed.destroy()
                self.code_editor = None
            self.code_panel.destroy()
            self.code_panel = None

    def close_panels(self):
        self.close_garage()
        self.close_code()

    # ---------- the brain: autopilot ----------
    def toggle_autopilot(self):
        if self.typing:
            return
        if self.autopilot:
            self.autopilot = False
            self.player.brain = None
            self.player.control = (0.0, 0.0, False)
            self.toast("Autopilot OFF: you're driving", GREY)
            return
        if self.brain is None:
            self.brain, self.brain_note = self.load_brain()
        self.autopilot = True
        self.player.brain = self.brain
        self.toast("Autopilot ON: " + self.brain_note, BLUE)

    def load_brain(self):
        """Your brain (brains/my_brain.py), run safely in its own process as Robot Lab runs it; the starter brain
        when yours won't load (the reason is said)."""
        path = os.path.join(BRAINS, "my_brain.py")
        try:
            import lab_brain
            with open(path, encoding="utf-8") as f:
                fn, fname = lab_brain.load_brain(f.read(), "experience")
            return lab_brain.Autopilot(fn, fname), "my_brain.py is driving"
        except Exception as e:  # (no file, a mistake in it: the starter brain drives, and the learner is told why)
            self.say(f"Your brain didn't load ({str(e)[:90]}). My starter brain will drive instead.")
            return cpu_brains.for_level("easy"), "the starter brain is driving"

    def close_brain(self):
        if self.brain is not None and hasattr(self.brain, "close"):
            try:
                self.brain.close()
            except Exception:
                pass
        self.brain = None

    # ---------- the bout ----------
    def start_bout(self):
        if self.autopilot:
            self.toggle_autopilot()
        if self.dummy is not None:
            self.vis.pop(self.dummy.id).destroy()
            self.arena.remove_robot(self.dummy)
            self.dummy = None
        if self.cpu is not None:
            self.vis.pop(self.cpu.id).destroy()
            self.arena.remove_robot(self.cpu)
        self.player.fix()
        self.player.reset()
        # (a first bout should be winnable: SPARKY, Club Coders' sparring robot, a wedge like yours and a little
        # slower; a spinner's hits were too much for a first go)
        rival = sim.default_design("SPARKY", (40, 170, 200), "wedge")
        rival["points"] = {"speed": 20, "attack": 15, "armour": 20, "control": 20}
        rival["settings"] = dict(rival["settings"], forward_speed=65, acceleration=60)
        rival["style"] = {"trim": [20, 30, 40], "lights": [80, 220, 255], "number": "CC-02"}
        self.cpu = self.arena.add_robot(rival, brain=None, owner="CPU", start=5)
        self.vis[self.cpu.id] = rw_gfx.RobotVisual(self.render, self.cpu.design)
        self.vis[self.cpu.id].set_label("SPARKY", (0.5, 0.9, 1, 1))
        self.bout_time, self.bout_result = -3.0, None  # (a 3, 2, 1 first)
        self.beeped = set()
        self.accept("b", self.rematch)

    def rematch(self):
        if self.obj and self.obj[0] == "bout" and self.bout_result in ("waiting", None):
            self.start_bout()

    def bout_tick(self):
        if self.obj is None or self.obj[0] != "bout" or self.cpu is None or self.bout_result is not None:
            return
        self.bout_time += sim.STEP
        if self.bout_time < 0:
            n = int(-self.bout_time) + 1
            if n not in self.beeped:
                self.beeped.add(n)
                self.snd.say(n, 0.9)
            self.player.control = (0.0, 0.0, False)
            self.cpu.brain = None
            return
        if self.cpu.brain is None:
            self.cpu.brain = cpu_brains.for_level("easy")
            self.snd.say("activate", 0.9)
        alive = [r for r in (self.player, self.cpu) if not r.knocked_out]
        if len(alive) < 2 or self.bout_time >= BOUT_SECONDS:
            mine, theirs = (max(0, r.health) / r.stats["armour"] for r in (self.player, self.cpu))
            if self.cpu.knocked_out and not self.player.knocked_out:
                self.bout_result = "ko"
            elif not self.player.knocked_out and mine > theirs:
                self.bout_result = "win"
            else:
                self.bout_result = "lost"
            self.cpu.brain = None
            self.cpu.control = (0.0, 0.0, False)

    # ---------- the end ----------
    def finish(self):
        if self.finished is not None:
            return
        seconds = time.perf_counter() - self.run_start
        all_done = all(ok for _, ok in self.done) and len(self.done) == len(OBJECTIVES)
        stars = 1 + (1 if all_done else 0) + (1 if self.bout_result == "ko" else 0)
        self.finished = {"xp": self.xp, "rank": rank_of(self.xp), "stars": stars, "seconds": round(seconds, 1),
                         "objectives": [oid for oid, ok in self.done if ok], "robot": self.player.name}
        best = save_progress(self.finished)
        self.close_panels()
        self.say("Orientation complete. You drove it, coded it and gave it a brain. Welcome to Club Coders!")
        self.result_title.setText("EXPERIENCE 1 COMPLETE")
        self.result_body.setText(
            f"{self.xp} XP      rank: {rank_of(self.xp).upper()}\n\n"
            + "\n".join(f"{'+' if ok else '-'}  {next(o[1] for o in OBJECTIVES if o[0] == oid)}" for oid, ok in self.done)
            + f"\n\ntime {int(seconds) // 60}:{int(seconds) % 60:02d}      best {best.get('best_xp', 0)} XP, "
              f"finished {best.get('finished', 1)} time{'s' if best.get('finished', 1) != 1 else ''}\n\n"
              "R plays it again      Esc quits")
        for i, s in enumerate(self.result_stars):
            s.setFg(YELLOW if i < stars else (0.3, 0.3, 0.35, 1))
        self.result_card.show()
        self.snd.react("applause", time.perf_counter())

    def escape(self):
        if self.typing:
            return
        if self.garage is not None or self.code_panel is not None:
            return self.close_panels()
        self.close_brain()
        self.userExit()

    # ---------- the screen ----------
    def build_hud(self):
        tl = self.a2dTopLeft
        DirectFrame(parent=tl, frameColor=PANEL, frameSize=(0.03, 0.86, -0.98, -0.03))
        OnscreenText("EXPERIENCE 1: ORIENTATION", pos=(0.06, -0.1), scale=0.042, fg=YELLOW, align=TextNode.ALeft, parent=tl)
        self.rank_text = OnscreenText("", pos=(0.06, -0.16), scale=0.032, fg=WHITE, align=TextNode.ALeft, parent=tl,
                                      mayChange=True)
        DirectFrame(parent=tl, frameColor=(0.15, 0.15, 0.17, 1), frameSize=(0, 0.76, 0, 0.026), pos=(0.06, 0, -0.215))
        self.xp_bar = DirectFrame(parent=tl, frameColor=BLUE, frameSize=(0, 0.01, 0, 0.026), pos=(0.06, 0, -0.215))
        self.xp_text = OnscreenText("", pos=(0.06, -0.255), scale=0.026, fg=GREY, align=TextNode.ALeft, parent=tl,
                                    mayChange=True)
        OnscreenText("OBJECTIVES", pos=(0.06, -0.31), scale=0.028, fg=GREY, align=TextNode.ALeft, parent=tl)
        self.check_rows = [OnscreenText("", pos=(0.06, -0.36 - i * 0.065), scale=0.03, fg=WHITE, align=TextNode.ALeft,
                                        parent=tl, mayChange=True) for i in range(len(OBJECTIVES))]
        # the coach, bottom centre
        bc = self.a2dBottomCenter
        DirectFrame(parent=bc, frameColor=PANEL, frameSize=(-1.0, 1.0, 0.1, 0.36))
        OnscreenText(COACH, pos=(-0.96, 0.31), scale=0.032, fg=BLUE, align=TextNode.ALeft, parent=bc)
        self.coach_text = OnscreenText("", pos=(-0.96, 0.26), scale=0.033, fg=WHITE, align=TextNode.ALeft, parent=bc,
                                       mayChange=True, wordwrap=58)
        self.coach_full, self.coach_shown, self.coach_at = "", 0, 0.0
        # the objective, top centre
        tc = self.a2dTopCenter
        self.obj_title = OnscreenText("", pos=(0, -0.09), scale=0.05, fg=YELLOW, shadow=(0, 0, 0, 0.9), parent=tc,
                                      mayChange=True)
        self.obj_hint = OnscreenText("", pos=(0, -0.15), scale=0.034, fg=WHITE, shadow=(0, 0, 0, 0.9), parent=tc,
                                     mayChange=True)
        self.big = OnscreenText("", pos=(0, 0.2), scale=0.13, fg=YELLOW, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.toast_rows = [OnscreenText("", pos=(0, 0.45 - i * 0.07), scale=0.05, fg=GREEN, shadow=(0, 0, 0, 0.9),
                                        mayChange=True) for i in range(3)]
        self.help = OnscreenText("Arrows/WASD drive   Space weapon   F unstick   G garage   C code   P autopilot   "
                                 "V view   N skip   R restart   H help   Esc quit",
                                 pos=(0, 0.04), scale=0.027, fg=GREY, parent=bc)
        self.armour_text = OnscreenText("", pos=(-0.06, 0.06), scale=0.035, fg=WHITE, align=TextNode.ARight,
                                        parent=self.a2dBottomRight, mayChange=True)
        # the result card
        self.result_card = DirectFrame(frameColor=(0.02, 0.03, 0.06, 0.94), frameSize=(-0.9, 0.9, -0.62, 0.62))
        self.result_title = OnscreenText("", pos=(0, 0.48), scale=0.07, fg=YELLOW, parent=self.result_card, mayChange=True)
        self.result_stars = [OnscreenText("*", pos=(-0.2 + i * 0.2, 0.3), scale=0.2, fg=YELLOW, parent=self.result_card,
                                          mayChange=True) for i in range(3)]
        self.result_body = OnscreenText("", pos=(0, 0.14), scale=0.036, fg=WHITE, parent=self.result_card, mayChange=True)
        self.result_card.hide()

    def toggle_help(self):
        if not self.typing:
            self.help.hide() if not self.help.isHidden() else self.help.show()

    def say(self, words):
        self.coach_full, self.coach_shown, self.coach_at = words, 0, time.perf_counter()
        if args.offscreen:
            print(f"{COACH}: {words}", flush=True)

    def toast(self, words, colour, big=False):
        self.toasts = (self.toasts + [(words, colour, time.perf_counter() + (3.5 if big else 2.5))])[-3:]
        if args.offscreen:
            print("toast:", words, flush=True)

    def update_checklist(self):
        for i, (row, o) in enumerate(zip(self.check_rows, OBJECTIVES)):
            done = next((ok for oid, ok in self.done if oid == o[0]), None)
            if done is True:
                row.setText(f"[x]  {o[1]}   +{o[4]}")
                row.setFg(GREEN)
            elif done is False:
                row.setText(f"[-]  {o[1]}   skipped")
                row.setFg(GREY)
            elif i == self.objective:
                row.setText(f">    {o[1]}")
                row.setFg(YELLOW)
            else:
                row.setText(f"[ ]  {o[1]}")
                row.setFg((0.55, 0.58, 0.65, 1))

    def update_hud(self, now):
        xp, rank = self.xp, rank_of(self.xp)
        nxt = next_rank(xp)
        base = max(need for need, _ in RANKS if need <= xp)
        frac = 1.0 if nxt is None else (xp - base) / (nxt[0] - base)
        self.xp_bar["frameSize"] = (0, 0.76 * max(0.01, frac), 0, 0.026)
        self.rank_text.setText(f"RANK: {rank.upper()}      {xp} XP")
        self.xp_text.setText(f"{nxt[0] - xp} XP to {nxt[1]}" if nxt else "Top rank!")
        self.update_checklist()
        o = self.obj
        if o is not None:
            self.obj_title.setText(f"OBJECTIVE {self.objective + 1} OF {len(OBJECTIVES)}:  {o[1].upper()}")
            hint = o[3]
            if o[0] == "drive":
                hint += f"   ({min(4.0, self.travelled):.1f} m)"
            elif o[0] == "turn":
                hint += f"   ({min(360, self.turned):.0f} degrees)"
            elif o[0] == "rings":
                hint += f"   ({self.ring_n} of {len(RINGS)})"
            elif o[0] == "weapon":
                hint += f"   ({min(3, self.fires)} of 3)"
            elif o[0] == "dummy" and self.dummy is not None:
                hint += f"   ({min(3, self.player.hits - self.hits_start)} of 3)"
            elif o[0] == "code":
                hint += f"   ({min(4.0, self.code_open_for):.0f} s)"
            elif o[0] == "brain":
                hint += f"   ({min(8.0, self.autopilot_for):.0f} s)" + ("   AUTOPILOT ON" if self.autopilot else "   press P")
            elif o[0] == "bout":
                left = max(0.0, BOUT_SECONDS - max(0.0, self.bout_time))
                hint = f"SPARKY  {left:.0f} s left" if self.bout_result is None else hint
            self.obj_hint.setText(hint)
        else:
            self.obj_title.setText("")
            self.obj_hint.setText("")
        big = ""
        if o is not None and o[0] == "bout" and self.bout_result is None and self.bout_time < 0.6:
            big = str(int(-self.bout_time) + 1) if self.bout_time < 0 else "ACTIVATE!"
        self.big.setText(big)
        live = [t for t in self.toasts if t[2] > now]
        self.toasts = live
        for row, t in zip(self.toast_rows, list(reversed(live)) + [None] * 3):
            row.setText(t[0] if t else "")
            if t:
                row.setFg(t[1])
        if self.coach_shown < len(self.coach_full):  # (the coach's words come up a few letters at a time)
            self.coach_shown = min(len(self.coach_full), int((now - self.coach_at) * 70))
            self.coach_text.setText(self.coach_full[:self.coach_shown])
        p = self.player
        self.armour_text.setText(f"{p.name}   armour {100 * max(0, p.health) / p.stats['armour']:.0f}%"
                                 + ("   AUTOPILOT" if self.autopilot else ""))

    # ---------- every frame ----------
    def read_controls(self):
        if self.autopilot or self.typing or self.mouseWatcherNode is None or args.selftest:
            if not self.autopilot and not args.selftest:
                self.player.control = (0.0, 0.0, False)
            return
        down = self.mouseWatcherNode.is_button_down
        k = KeyboardButton
        th = (down(k.up()) or down(k.asciiKey("w"))) - (down(k.down()) or down(k.asciiKey("s")))
        st = (down(k.left()) or down(k.asciiKey("a"))) - (down(k.right()) or down(k.asciiKey("d")))
        self.player.drive(float(th), float(st), bool(down(k.space())))

    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        self.frames += 1
        if self.checks is not None:
            try:
                next(self.checks)
            except StopIteration:
                self.checks = None
        if self.finished is None:
            self.read_controls()
            self.accum += dt * (4.0 if args.selftest else 1.0)
            while self.accum >= sim.STEP:
                self.arena.step()
                self.accum -= sim.STEP
                self.track_moves()
                self.bout_tick()
                self.check_objective()
                if self.finished is not None:
                    break
        self.draw(dt, now)
        self.update_hud(now)
        if args.screenshot and now - self.start > args.after and self.frames > 3 and not args.selftest:
            self.save_shot(args.screenshot)
            self.close_brain()
            self.userExit()
        return task.cont

    def save_shot(self, path):
        self.graphicsEngine.renderFrame()
        self.graphicsEngine.renderFrame()
        self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(path)))

    def draw(self, dt, now):
        a = self.arena
        for r in a.robots:
            v = self.vis.get(r.id)
            if v is None:
                continue
            v.update({"pos": list(r.pos), "quat": list(r.np.getQuat()), "wpos": list(r.weapon_np.getPos()),
                      "wquat": list(r.weapon_np.getQuat()), "speed": r.speed, "rpm": r.weapon_rpm}, dt)
            if r.health < self.last_hp.get(r.id, r.health) - 0.5:
                self.flash[r.id] = now + 0.12
            self.last_hp[r.id] = r.health
            v.flash(now < self.flash.get(r.id, 0))
        impacts, streams = a.take_fx()
        for pos, dmg, kind in impacts:
            victim = min(a.robots, key=lambda r: (r.pos - Point3(*pos)).length())
            self.fx.impact(pos, dmg, kind, tuple(c / 255 for c in victim.design["colour"]))
            self.snd.hit(kind, min(1.0, 0.35 + dmg / 25))
        for pos, direction, count in streams[-40:]:
            self.fx.stream(pos, direction, count)
        self.fx.update(dt)
        for r in a.robots:
            if r.weapon in ("spinner", "drum", "vdisc"):
                self.snd.spinner(f"spin{r.id}", r.weapon_rpm, 0.0 if r.knocked_out else 0.5, r.weapon)
            if r.fires > self.fire_counts.get(r.id, 0) and r.weapon in ("wedge", "hammer"):
                self.snd.play("pneumatic" if r.weapon == "wedge" else "swing", 0.6)
            self.fire_counts[r.id] = r.fires
        speed = abs(self.player.speed)
        self.snd.loop("motor", "motor", 0.05 + min(0.3, speed / 20), 0.6 + speed / 8)
        for ring in self.rings:  # (the rings' beams breathe)
            ring.setZ(0.03)
            ring.getChild(1).setSz(0.85 + 0.15 * math.sin(now * 3))
        self.arena_vis.update(a.hazard_state())
        front = self.player.shape["half"].y
        targets = [r.pos for r in a.robots if not r.knocked_out and r is not self.player][:1] + [self.player.pos]
        self.cam.update(dt, self.vis[self.player.id].chassis, front, targets, self.fx.shake_offset())

    # ---------- --selftest: the experience played through by itself ----------
    def steer_to(self, x, y, speed=1.0):
        p = self.player
        want = math.degrees(math.atan2(y - p.pos.y, x - p.pos.x)) - 90  # (Panda's heading 0 faces +y)
        ang = (want - p.np.getH() + 180) % 360 - 180
        steer = max(-1.0, min(1.0, ang / 30))
        p.drive(speed * (0.3 if abs(ang) > 60 else 1.0), steer, False)
        return math.hypot(x - p.pos.x, y - p.pos.y)

    def selftest(self):
        results = []

        def check(name, ok, detail=""):
            results.append((name, bool(ok), detail))
            print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)

        def until(cond, seconds):
            end = time.perf_counter() + seconds
            while not cond() and time.perf_counter() < end:
                yield
            return cond()

        def objective_is(oid):
            return lambda: self.obj is not None and self.obj[0] == oid

        for _ in range(5):
            yield
        # 1 drive
        while self.obj and self.obj[0] == "drive" and time.perf_counter() - self.start < 60:
            self.player.drive(1.0, 0.0, False)
            yield
        check("1 drive: 4 m driven completes it", objective_is("turn")(), f"{self.travelled:.1f} m")
        # 2 turn
        t0 = time.perf_counter()
        while objective_is("turn")() and time.perf_counter() - t0 < 60:
            self.player.drive(0.0, 1.0, False)
            yield
        check("2 turn: a spin on the spot completes it", objective_is("rings")(), f"{self.turned:.0f} degrees")
        # 3 rings
        t0 = time.perf_counter()
        while objective_is("rings")() and time.perf_counter() - t0 < 120:
            x, y = RINGS[min(self.ring_n, len(RINGS) - 1)]
            self.steer_to(x, y)
            yield
        check("3 rings: driven through in order", objective_is("weapon")(), f"{self.ring_n} rings")
        # 4 weapon
        t0 = time.perf_counter()
        while objective_is("weapon")() and time.perf_counter() - t0 < 30:
            self.player.drive(0.0, 0.0, True)
            yield
            self.player.drive(0.0, 0.0, False)
            for _ in range(20):
                yield
        check("4 weapon: three fires complete it", objective_is("dummy")(), f"{self.fires} fires")
        # 5 dummy
        t0 = time.perf_counter()
        while objective_is("dummy")() and time.perf_counter() - t0 < 120:
            d = self.dummy
            dist = self.steer_to(d.pos.x, d.pos.y)
            if dist < 3.0:  # (close: full speed at it, firing every other moment)
                self.player.drive(1.0, self.player.control[1], int(time.perf_counter() * 3) % 2 == 0)
            yield
        check("5 dummy: three hits complete it", objective_is("garage")(),
              f"{self.player.hits - self.hits_start} hits")
        # 6 garage: the variables changed through the panel's own methods, then REBUILD
        self.player.drive(0.0, 0.0, False)
        self.toggle_garage()
        yield
        self.name_typed("TESTBOT")
        self.change_speed(-10)
        self.set_colour(list(SWATCHES[2]))
        yield
        self.rebuild()
        yield from until(objective_is("code"), 10)
        check("6 garage: a string, an integer and a list changed, then REBUILD", objective_is("code")()
              and self.player.name == "TESTBOT" and self.player.design["colour"] == list(SWATCHES[2]),
              f"{sorted(self.garage_changes)}, the robot is {self.player.name}")
        if args.screenshot:
            self.save_shot(args.screenshot.replace(".png", "_garage.png"))
        # 7 code
        self.toggle_code()
        yield
        text = "\n".join(self.code_state["lines"])
        check("7 code: the code shows the changed variables", 'robot_name: str = "TESTBOT"' in text
              and "forward_speed: int = " in text, "")
        if args.screenshot:
            for _ in range(5):
                yield
            self.save_shot(args.screenshot.replace(".png", "_code.png"))
        yield from until(objective_is("brain"), 10)
        check("7 code: open 4 seconds completes it", objective_is("brain")(), f"{self.code_open_for:.1f} s")
        self.close_code()
        # 8 brain
        self.toggle_autopilot()
        yield from until(objective_is("bout"), 20)
        check("8 brain: autopilot 8 seconds completes it", objective_is("bout")(), self.brain_note)
        # 9 bout: the expert computer driver at the wheel for the test (put there again whenever the bout's start
        # takes the wheel back, as it does for a learner who left autopilot on)
        yield from until(objective_is("bout"), 30)
        driver = cpu_brains.for_level("expert")
        t0 = time.perf_counter()
        while self.obj is not None and time.perf_counter() - t0 < 120:
            if self.bout_result in ("lost", "waiting"):
                break
            if self.player.brain is not driver:
                self.player.brain = driver
            yield
        self.player.brain = None
        if self.obj is not None:  # (lost the bout: the test says so, then skips it so the end is checked too)
            check("9 bout: a bout is fought to a result", self.bout_result is not None, str(self.bout_result))
            self.skip()
        else:
            check("9 bout: won (ko or on armour)", self.bout_result in ("ko", "win"), str(self.bout_result))
        yield from until(lambda: self.finished is not None, 5)
        check("the end: the result card, the XP and the rank", self.finished is not None and self.finished["xp"] > 0,
              json.dumps(self.finished))
        saved = load_progress()
        check("the best result is kept on this computer", saved.get("best_xp", 0) >= (self.finished or {}).get("xp", 1),
              json.dumps(saved)[:160])
        if args.screenshot:
            for _ in range(10):
                yield
            self.save_shot(args.screenshot)
        failed = [n for n, ok, _ in results if not ok]
        print(f"SELFTEST {'PASS' if not failed else 'FAIL'}: {len(results) - len(failed)} of {len(results)} passed",
              flush=True)
        self.close_brain()
        os._exit(0 if not failed else 1)


if __name__ == "__main__":
    Experience().run()
