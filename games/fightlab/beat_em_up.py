"""BEAT 'EM UP showcase: you fight the computer in the Fight Lab ring, with full graphics and sound. No server needed.

The fighters, stage and rules come from the mods folder (mods/fighters, mods/stage.py, mods/rules.py),
so learners' AI requests can change them.

Choose:  Left / Right your fighter   Up / Down the computer's fighter   Enter FIGHT!
Fight:   Arrow keys move (towards / away, and up / down to SIDESTEP round them)
         A punch (your combo: press again each time a hit lands)   S kick (forward + S: high kick)
         D special (uses 50 energy)   W throw   Space jump   Shift block (hold)   X crouch (hold)
         crouch + kick = low sweep   crouch + Shift = low block   jump + A or S = jump kick
Other:   V change view   mouse wheel or + / - zoom   right-drag or Q / E swing round the ring (Home resets)
         R rematch   Enter choose again   P pause
         M music (8-bit, rock, your own, off)   H hide help   Esc quit
Options: --gfx low|medium|high (use low on old laptops)   --you blaze --cpu kaito   --level expert   --no-sound
"""
import argparse
import math
import os
import time

from panda3d.core import loadPrcFileData

ap = argparse.ArgumentParser()
ap.add_argument("--gfx", choices=["low", "medium", "high"], default="high")
ap.add_argument("--you", default="blaze", help="which fighter file in mods/fighters you play (or a boss's name)")
ap.add_argument("--cpu", default="kaito", help="which fighter the computer plays")
ap.add_argument("--no-sound", action="store_true")
ap.add_argument("--level", choices=["empty", "easy", "medium", "expert"], default="medium",
                help="how well the computer fights")
ap.add_argument("--rounds", type=int, choices=[1, 2, 3], default=2, help="rounds to win the match")
ap.add_argument("--music", choices=["off", "chip", "rock", "yours"], default="rock",
                help="background music (M changes it): 8-bit, rock, or your own files in the music folder")
ap.add_argument("--camera", choices=["fight", "me", "shoulder", "ring"], default="fight")
ap.add_argument("--autoplay", action="store_true", help="the computer fights for you too (demo)")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=12)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--skip-intro", action="store_true")
args = ap.parse_args()

loadPrcFileData("", "win-size 1600 900\nwindow-title BEAT 'EM UP - Fight Lab\nframebuffer-multisample 1\n"
                    "multisamples 4\nsync-video true\n")
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\nwin-size 1280 720\naudio-library-name null\n")

from direct.gui.DirectGui import DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, Point3, TextNode, Vec3  # noqa: E402

import cpu_brains  # noqa: E402
import fight_fx  # noqa: E402
import fight_gfx  # noqa: E402
import fight_model  # noqa: E402
import fight_mods  # noqa: E402
import fight_sim as sim  # noqa: E402
import fight_sound  # noqa: E402
from fight_camera import FightCamera  # noqa: E402
from fight_hud import FightHUD  # noqa: E402

YELLOW, WHITE, GREY, BLUE = (1, .85, .2, 1), (1, 1, 1, 1), (.7, .75, .85, 1), (.55, .85, 1, 1)
PANEL = (0.02, 0.025, 0.04, 0.82)
PRESS_KEYS = {"a": "punch", "s": "kick", "d": "special", "w": "throw", "space": "jump"}
ATTACKS = {"punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam"}


class BeatEmUp(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        fighters, self.stage_mod, self.rules = fight_mods.load_all()
        # everyone you can pick: the fighters in mods/fighters, then the bosses
        self.roster = [d for d in fighters.values()] + [sim.boss_design(n) for n in sim.BOSS_BY_NAME]
        names = [d["name"].lower() for d in self.roster]
        self.pick = [names.index(args.you.lower()) if args.you.lower() in names else 0,
                     names.index(args.cpu.lower()) if args.cpu.lower() in names else min(1, len(names) - 1)]
        fight_gfx.init(self, args.gfx)
        self.fx = fight_fx.Effects(self.render, args.gfx)
        self.snd = fight_sound.FightSounds(self, on=not args.no_sound and not args.offscreen)
        self.stage_vis = fight_gfx.StageVisual(self.render, [0], self.stage_mod["hazards"], self.stage_mod["look"])
        self.cam = FightCamera(self, args.camera)
        for key, factor in (("wheel_up", 0.88), ("wheel_down", 1 / 0.88), ("=", 0.8), ("+", 0.8), ("-", 1.25),
                            ("=-repeat", 0.9), ("--repeat", 1.11)):
            self.accept(key, self.cam.wheel, [factor])
        self.accept("v", self.cam.cycle)
        for key, deg in (("q", 20), ("e", -20), ("q-repeat", 6), ("e-repeat", -6)):  # swing the view round
            self.accept(key, self.cam.turn, [deg])
        self.accept("home", self.cam.reset_view)
        self.accept("r", self.rematch)
        self.accept("p", self.toggle_pause)
        self.accept("h", self.toggle_help)
        self.accept("m", self.next_music)
        self.accept("enter", self.enter)
        for key, action in PRESS_KEYS.items():
            self.accept(key, self.press, [action])
        for key, delta in (("arrow_left", (0, -1)), ("arrow_right", (0, 1)), ("arrow_up", (1, -1)),
                           ("arrow_down", (1, 1))):
            self.accept(key, self.choose, list(delta))
        self.music = args.music
        self.accept("escape", self.userExit)
        self.visuals = {}
        self.hud()
        self.mode = "select"
        if args.skip_intro:
            self.new_match(intro=False)
        elif args.autoplay:  # (a demo: straight to the fight intro)
            self.new_match()
        else:
            self.show_select()
        self.start = self.last = time.perf_counter()
        self.taskMgr.add(self.update, "update")

    # ---------- choosing fighters ----------
    def show_select(self):
        self.mode = "select"
        self.clear_fighters()
        self.stage = sim.Stage(hazards={}, practice=True)
        ring = self.stage.add_ring()
        for i in (0, 1):
            ring.add_fighter(self.roster[self.pick[i]], brain=None, owner="YOU" if i == 0 else "Computer")
        self.ring = ring
        self.player, self.cpu = ring.fighters
        self.names = {f.id: (f.name, f.owner) for f in ring.fighters}
        self.mode_time, self.accum, self.paused, self.slowmo = 0.0, 0.0, False, 0.0
        self.last_anim, self.last_phase = {}, None
        self.make_visuals(labels=True)
        self.fight_hud.show(False)
        self.select_text()

    def choose(self, who, delta):
        if self.mode != "select":
            return
        self.pick[who] = (self.pick[who] + delta) % len(self.roster)
        self.snd.play("beep", 0.4)
        self.show_select()

    def select_text(self):
        lines = []
        for i, who in enumerate(("YOU", "COMPUTER")):
            d = self.roster[self.pick[i]]
            kind = "BOSS" if d.get("model") else d.get("body", "robot").upper()
            lines.append(f"{who}:  {d['name']}  ({kind}, special: {d['special'].replace('_', ' ')})")
        self.big.setText("CHOOSE YOUR FIGHTER")
        self.small.setText("\n".join(lines) + "\n\nLeft / Right: you     Up / Down: the computer     Enter: FIGHT!")

    def enter(self):
        if self.mode == "select":
            self.snd.play("go", 0.7)
            self.new_match()
        elif self.mode == "over":
            self.show_select()

    # ---------- a match ----------
    def clear_fighters(self):
        for v in self.visuals.values():
            v.destroy()
        self.visuals = {}

    def make_visuals(self, labels=False):
        for f, owner in zip(self.ring.fighters, ("YOU", "COMPUTER")):
            v = fight_model.make(self.render, f.design)
            if labels:  # (in a fight the names are on the health bars instead)
                v.set_label(f"{f.name}\n{owner}", YELLOW if owner == "YOU" else (1, 0.75, 0.3, 1))
            self.visuals[f.id] = v

    def new_match(self, intro=True):
        self.clear_fighters()
        self.snd.stop_all()
        self.stage = sim.Stage(hazards=self.stage_mod["hazards"], practice=False, rounds_to_win=args.rounds)
        self.ring = self.stage.add_ring()
        self.player = self.ring.add_fighter(self.roster[self.pick[0]], brain=None, owner="YOU")
        self.cpu = self.ring.add_fighter(self.roster[self.pick[1]], brain=None, owner="Computer")
        self.make_visuals()
        self.names = {self.player.id: (self.player.name, "YOU"), self.cpu.id: (self.cpu.name, "COMPUTER")}
        self.mode = "intro" if intro else "fight"
        self.mode_time = 0.0
        self.accum = 0.0
        self.paused = False
        self.slowmo = 0.0
        self.pressed = None
        self.last_anim, self.last_phase = {}, None
        self.fight_hud.show(True)
        self.big.setText("")
        self.small.setText("")
        if self.mode == "fight":
            self.activate()

    def activate(self):
        self.cpu.brain = cpu_brains.for_level(args.level)
        self.player.brain = cpu_brains.for_level("expert") if args.autoplay else None
        self.mode, self.mode_time = "fight", 0.0
        self.ring.start_round()

    def rematch(self):
        if self.mode in ("fight", "over"):
            self.new_match()

    def toggle_pause(self):
        self.paused = not self.paused
        self.big.setText("PAUSED" if self.paused else "")

    def next_music(self):
        order = list(fight_sound.rw_sound.MUSIC)
        self.music = order[(order.index(self.music) + 1) % len(order)]

    def toggle_help(self):
        self.help.hide() if not self.help.isHidden() else self.help.show()

    # ---------- the screen ----------
    def hud(self):
        self.fight_hud = FightHUD(self.aspect2d)
        self.big = OnscreenText("", pos=(0, 0.35), scale=0.12, fg=YELLOW, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.small = OnscreenText("", pos=(0, 0.2), scale=0.05, fg=WHITE, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.ticker = OnscreenText("", pos=(0, -0.7), scale=0.045, fg=YELLOW, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.cam_text = OnscreenText("", pos=(1.74, -0.99), scale=0.028, fg=GREY, align=TextNode.ARight, mayChange=True)
        self.help = OnscreenText("Arrows move (up/down sidestep)   A punch/combo   S kick   D special   W throw   "
                                 "Space jump   Shift block   X crouch   V view   Q/E or right-drag turn   R rematch   Enter choose   P pause   "
                                 "H hide", pos=(-1.74, -0.99), scale=0.026, fg=GREY, align=TextNode.ALeft)

    # ---------- your controls ----------
    def press(self, action):
        if self.mode == "fight" and not args.autoplay and not self.paused:
            self.player.press(action, self.stage.time)

    def read_controls(self):
        if args.autoplay or self.mouseWatcherNode is None or self.mode != "fight":
            return
        down = self.mouseWatcherNode.is_button_down
        sx = down(KeyboardButton.right()) - down(KeyboardButton.left())
        sy = down(KeyboardButton.up()) - down(KeyboardButton.down())
        fwd = side = 0.0
        if sx or sy:  # the arrows move you across the screen: work out which way that is for your fighter
            q = self.camera.getQuat(self.render)
            right, ahead = q.getRight(), q.getForward()
            right.z = ahead.z = 0
            right.normalize()
            ahead.normalize()
            want = right * sx + ahead * sy
            face = Vec3(self.cpu.x - self.player.x, self.cpu.y - self.player.y, 0)
            if face.length() > 1e-3:
                face.normalize()
                left = Vec3(-face.y, face.x, 0)
                fwd = max(-1.0, min(1.0, want.dot(face) * 1.4))
                side = max(-1.0, min(1.0, want.dot(left) * 1.4))
        block, crouch = down(KeyboardButton.shift()), down(KeyboardButton.asciiKey("x"))
        hold = "low_block" if block and crouch else "block" if block else "crouch" if crouch else ""
        self.player.control = (fwd, side, hold)

    # ---------- every frame ----------
    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        self.mode_time += dt
        if self.mode == "intro":
            self.run_intro()
        if not self.paused:
            self.read_controls()
            scale = 0.3 if self.slowmo > 0 else 1.0
            self.slowmo = max(0.0, self.slowmo - dt)
            self.accum += dt * scale
            while self.accum >= sim.STEP:
                if self.mode in ("fight", "over", "intro"):
                    self.stage.step()
                elif self.mode == "select":
                    for f in self.ring.fighters:  # showing off: a little fighting stance
                        f.state_t += sim.STEP
                self.accum -= sim.STEP
            if self.mode == "fight":
                self.check_end()
        self.draw(dt, now)
        if args.screenshot and now - self.start > args.after:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()
            self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot)))
            self.userExit()
        return task.cont

    def run_intro(self):
        t = self.mode_time
        self.player.control = self.cpu.control = (0.0, 0.0, "")
        if t < 2.0:
            self.big.setText(self.stage_mod["look"].get("name", "FIGHT LAB"))
            self.small.setText("")
        elif t < 4.2:
            self.big.setText(f"{self.player.name}  v  {self.cpu.name}")
            self.small.setText("you  v  the computer")
        else:
            self.big.setText("")
            self.small.setText("")
            self.activate()

    def check_end(self):
        r = self.ring
        if r.phase == "ko" and self.last_phase == "fight":
            self.slowmo = 1.0
        if r.phase == "over" and self.mode == "fight":
            self.mode = "over"
            winner = self.player if self.player.wins >= self.stage.rounds_to_win else self.cpu
            self.small.setText(("YOU WIN!" if winner is self.player else "THE COMPUTER WINS!") +
                               "\nR rematch     Enter choose fighters")
            self.cpu.brain = None

    def draw(self, dt, now):
        st_now = self.stage.time
        rs = sim.ring_state(self.ring, st_now)
        self.stage_vis.update([rs], st_now, dt)
        for f in rs["f"]:
            v = self.visuals.get(f["id"])
            if v is not None:
                if self.mode == "select":  # stand still in a fighting stance, facing each other
                    f = dict(f, a="idle", k=f["k"] + now)
                v.update(f, dt)
        # new hits: sparks, flashes and sounds
        for pos, dmg, kind in self.stage.take_fx():
            victim = min(self.ring.fighters, key=lambda g: (g.x - pos[0]) ** 2 + (g.y - pos[1]) ** 2)
            robot = victim.design.get("body", "robot") == "robot"
            self.fx.impact(pos, dmg, kind, tuple(c / 255 for c in victim.design["colour"]), robot)
            if kind == "zap":
                self.stage_vis.zap(pos)
            far = (Point3(*pos) - self.camera.getPos()).length()
            self.snd.hit(kind, min(1.0, 0.35 + dmg / 20) * max(0.2, 1 - far / 30), robot)
            if kind == "counter" or dmg >= 14:
                self.snd.react("ooh", now)
        self.fx.update(dt)
        self.sounds(rs, now)
        self.snd.layers(self.music, 0.45, self.mode != "select", min(1.0, 0.45 + self.fx.shake))
        self.place_camera(dt, rs)
        if self.mode != "select":
            self.fight_hud.update(rs, self.names, self.player.id, st_now, dt, self.stage.rounds_to_win)
        recent = [e for t, e in self.stage.events if st_now - t < 2.0 and ("COMBO" in e or "COUNTER" in e or
                                                                             "!" in e and ":" in e)][-2:]
        self.ticker.setText("\n".join(recent) if self.mode == "fight" else "")
        self.cam_text.setText(f"view: {self.cam.name}   {self.clock.getAverageFrameRate():.0f} fps   gfx {args.gfx}")

    def sounds(self, rs, now):
        """A whoosh as each move starts, the bell at FIGHT!, a boom at K.O., and the crowd."""
        if rs["ph"] == "fight" and self.last_phase == "intro":
            self.snd.bell()
        if rs["ph"] == "ko" and self.last_phase == "fight":
            self.snd.ko()
            self.snd.react("cheer", now)
        if rs["ph"] == "over" and self.last_phase != "over":
            self.snd.react("applause", now)
        self.last_phase = rs["ph"]
        for f in rs["f"]:
            a, last = f["a"], self.last_anim.get(f["id"])
            if a in ATTACKS and (last is None or last[0] != a or f["k"] < last[1] - 0.5) and f["k"] < 1.5:
                self.snd.swing(a, 0.7)
            elif a == "jump" and (last is None or last[0] != "jump"):
                self.snd.play("jump", 0.4)
            self.last_anim[f["id"]] = (a, f["k"])

    def place_camera(self, dt, rs):
        cx, cy = rs["c"]
        if self.mode == "intro":  # a slow sweep round the ring before the fight
            ang = self.mode_time * 0.5 - 1.0
            self.camera.setPos(cx + math.sin(ang) * 9, cy - math.cos(ang) * 9, 3.2 + self.mode_time * 0.25)
            self.camera.lookAt(cx, cy, 1.0)
            self.camLens.setFov(55)
            self.cam.pos = None
            return
        fs = [f for f in rs["f"] if f["a"] != "ringout" or f["pos"][2] > -1.5]
        me = next((Point3(*f["pos"]) for f in fs if f["id"] == self.player.id), None)
        other = next((Point3(*f["pos"]) for f in fs if f["id"] != self.player.id), None)
        self.cam.update(dt, me, other, (cx, cy), [(cx, cy)], self.fx.shake_offset())


BeatEmUp().run()
