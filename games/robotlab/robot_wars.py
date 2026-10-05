"""ROBOT WARS showcase: you drive TITAN against the computer's RAZORBACK, with full graphics and sound.

The robots, arena and rules come from the mods folder (mods/robots, mods/arena.py, mods/rules.py),
so learners' AI requests can change them.

Drive:   Arrow keys   Space is the weapon key: it fires a flipper or hammer, and switches a spinner or drum on and off
Camera:  C or V change view (third person, first person, zoomed arena follow, full arena)
         mouse wheel or + / - zoom in and out (every view)
Other:   R rematch   P pause   M music (8-bit, rock, your own, off)   H hide help   Esc quit
Options: --gfx low|medium|high (use low on old laptops)   --drive titan --cpu razorback   --no-sound
"""
import argparse
import math
import os
import time

from panda3d.core import loadPrcFileData

ap = argparse.ArgumentParser()
ap.add_argument("--gfx", choices=["low", "medium", "high"], default="high")
ap.add_argument("--drive", default="titan", help="which robot file in mods/robots you drive")
ap.add_argument("--cpu", default="razorback", help="which robot the computer drives")
ap.add_argument("--no-sound", action="store_true")
ap.add_argument("--level", choices=["empty", "easy", "medium", "expert"], default="medium",
                help="how well the computer drives")
ap.add_argument("--music", choices=["off", "chip", "rock", "yours"], default="rock",
                help="background music (M changes it): 8-bit, rock, or your own files in the music folder")
ap.add_argument("--camera", choices=["third", "fpv", "zoom", "arena", "centre"], default="third")
ap.add_argument("--autoplay", action="store_true", help="the computer drives your robot too (demo)")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=12)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--skip-intro", action="store_true")
args = ap.parse_args()

loadPrcFileData("", "win-size 1600 900\nwindow-title ROBOT WARS - Robot Lab\nframebuffer-multisample 1\n"
                    "multisamples 4\nsync-video true\n")
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\nwin-size 1280 720\naudio-library-name null\n")

from direct.gui.DirectGui import DirectFrame  # noqa: E402
from direct.gui.OnscreenText import OnscreenText  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton, Point3, TextNode  # noqa: E402

import cpu_brains  # noqa: E402
import lab_sim as sim  # noqa: E402
import rw_fx  # noqa: E402
import rw_gfx  # noqa: E402
import rw_mods  # noqa: E402
import rw_sound  # noqa: E402
from rw_camera import GameCamera  # noqa: E402

YELLOW, WHITE, GREY, RED, GREEN, ORANGE = (1, .85, .2, 1), (1, 1, 1, 1), (.7, .75, .85, 1), (1, .35, .3, 1), \
    (.4, .95, .5, 1), (1, .55, .15, 1)
PANEL = (0.02, 0.025, 0.04, 0.82)


class RobotWars(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        robots, self.arena_mod, self.rules = rw_mods.load_all()
        self.designs = (robots[args.drive], robots[args.cpu])
        rw_gfx.init(self, args.gfx)
        self.fx = rw_fx.Effects(self.render, args.gfx)
        self.snd = rw_sound.Sounds(self, on=not args.no_sound and not args.offscreen)
        self.arena_vis = rw_gfx.ArenaVisual(self.render, self.arena_mod["hazards"], self.arena_mod["look"])
        self.cam = GameCamera(self, args.camera)
        for key, factor in (("wheel_up", 0.88), ("wheel_down", 1 / 0.88), ("=", 0.8), ("+", 0.8), ("-", 1.25),
                            ("=-repeat", 0.9), ("--repeat", 1.11)):
            self.accept(key, self.cam.wheel, [factor])
        self.accept("c", self.cam.cycle)
        self.accept("v", self.cam.cycle)
        self.accept("r", self.rematch)
        self.accept("p", self.toggle_pause)
        self.accept("h", self.toggle_help)
        self.accept("m", self.next_music)
        self.music = args.music
        self.accept("escape", self.userExit)
        self.hud()
        self.new_match()
        self.start = self.last = time.perf_counter()
        self.taskMgr.add(self.update, "update")

    # ---------- a match ----------
    def new_match(self):
        if getattr(self, "arena", None):
            for v in self.vis.values():
                v.destroy()
        self.arena = sim.Arena(hazards=self.arena_mod["hazards"])
        self.player = self.arena.add_robot(self.designs[0], brain=None, owner="YOU", start=3)
        self.cpu = self.arena.add_robot(self.designs[1], brain=None, owner="CPU", start=5)
        self.vis = {}
        for r in self.arena.robots:  # the two fighters and any Resident Robots
            self.vis[r.id] = rw_gfx.RobotVisual(self.render, r.design)
            if r.house:
                self.vis[r.id].set_label(f"{r.name}\nResident Robot", (1, 0.75, 0.3, 1))
        self.visuals = [self.vis[self.player.id], self.vis[self.cpu.id]]
        self.last_hp = [r.health for r in (self.player, self.cpu)]
        self.flash = [0.0, 0.0]
        self.stage = "fight" if args.skip_intro else "intro"
        self.stage_time = 0.0
        self.fight_time = 0.0
        self.accum = 0.0
        self.paused = False
        self.result = ""
        self.slowmo = 0.0
        self.impacts_seen = 0
        self.fire_counts = {}
        self.beeped = set()
        if self.stage == "fight":
            self.activate()

    def activate(self):
        self.cpu.brain = cpu_brains.for_level(args.level)
        self.player.brain = cpu_brains.for_level("expert") if args.autoplay else None
        self.stage, self.stage_time = "fight", 0.0

    def rematch(self):
        self.snd.stop_all()
        self.new_match()

    def toggle_pause(self):
        self.paused = not self.paused

    def next_music(self):
        order = list(rw_sound.MUSIC)
        self.music = order[(order.index(self.music) + 1) % len(order)]

    def toggle_help(self):
        self.help.hide() if not self.help.isHidden() else self.help.show()

    # ---------- the screen ----------
    def hud(self):
        self.cards = []
        for side in (-1, 1):
            x0 = -1.76 if side < 0 else 0.86
            DirectFrame(frameColor=PANEL, frameSize=(x0, x0 + 0.9, 0.7, 0.97))
            name = OnscreenText("", pos=(x0 + 0.04, 0.9), scale=0.055, fg=WHITE, align=TextNode.ALeft, mayChange=True)
            sub = OnscreenText("", pos=(x0 + 0.04, 0.855), scale=0.032, fg=GREY, align=TextNode.ALeft, mayChange=True)
            DirectFrame(frameColor=(0.15, 0.15, 0.17, 1), frameSize=(0, 0.82, 0, 0.035), pos=(x0 + 0.04, 0, 0.8))
            armour = DirectFrame(frameColor=GREEN, frameSize=(0, 0.82, 0, 0.035), pos=(x0 + 0.04, 0, 0.8))
            ticks = [DirectFrame(frameColor=(0.02, 0.02, 0.03, 1), frameSize=(0, 0.004, 0, 0.035),
                                 pos=(x0 + 0.04 + 0.82 * k / 10, 0, 0.8)) for k in range(1, 10)]
            DirectFrame(frameColor=(0.15, 0.15, 0.17, 1), frameSize=(0, 0.82, 0, 0.016), pos=(x0 + 0.04, 0, 0.765))
            weapon = DirectFrame(frameColor=ORANGE, frameSize=(0, 0.82, 0, 0.016), pos=(x0 + 0.04, 0, 0.765))
            info = OnscreenText("", pos=(x0 + 0.04, 0.72), scale=0.03, fg=GREY, align=TextNode.ALeft, mayChange=True)
            self.cards.append((name, sub, armour, weapon, info, ticks))
        DirectFrame(frameColor=PANEL, frameSize=(-0.2, 0.2, 0.84, 0.97))
        self.clock_text = OnscreenText("", pos=(0, 0.88), scale=0.07, fg=WHITE, mayChange=True)
        self.big = OnscreenText("", pos=(0, 0.1), scale=0.16, fg=YELLOW, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.small = OnscreenText("", pos=(0, -0.05), scale=0.06, fg=WHITE, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.ticker = OnscreenText("", pos=(0, -0.86), scale=0.045, fg=YELLOW, shadow=(0, 0, 0, 0.9), mayChange=True)
        self.cam_text = OnscreenText("", pos=(1.74, -0.95), scale=0.03, fg=GREY, align=TextNode.ARight, mayChange=True)
        self.help = OnscreenText("Arrows drive   Space weapon (fire, or on/off)   C view   wheel or +/- zoom   R rematch   "
                                 "P pause   H hide", pos=(-1.74, -0.95), scale=0.03, fg=GREY, align=TextNode.ALeft)

    def update_hud(self, now):
        for i, (r, card) in enumerate(zip((self.player, self.cpu), self.cards)):
            name, sub, armour, weapon, info, _ = card
            name.setText(("YOU  " if i == 0 else "CPU  ") + r.name)
            name.setFg(tuple(c / 255 for c in r.design["colour"]) + (1,))
            sub.setText({"wedge": "Wedge with flipper", "spinner": "Horizontal spinner", "drum": "Drum spinner",
                         "hammer": "Hammer"}[r.weapon] + ("   (weapon OFF: Space)" if r.weapon in sim.TOGGLE_WEAPONS and not r.weapon_on else ""))
            pct = max(0.0, r.health) / r.stats["armour"]
            armour["frameSize"] = (0, 0.82 * pct, 0, 0.035)
            armour["frameColor"] = GREEN if pct > 0.5 else (YELLOW if pct > 0.25 else RED)
            if r.weapon in ("spinner", "drum"):
                charge = min(1.0, r.weapon_energy() / 450)
                label = f"{r.weapon_rpm:.0f} rpm  {r.weapon_energy():.0f} J"
            else:
                ready = self.arena.time >= r.fire_until + 0.9
                charge = 1.0 if ready else min(1.0, (self.arena.time - r.fire_until) / 0.9)
                label = "READY" if ready else "recharging"
            weapon["frameSize"] = (0, 0.82 * max(0.0, charge), 0, 0.016)
            info.setText(("KNOCKED OUT" if r.knocked_out else f"Armour {pct * 100:.0f}%") +
                         f"    {label}    Hits {r.hits}    Damage {r.damage_dealt:.0f}")
        left = max(0.0, self.rules["match_seconds"] - self.fight_time)
        self.clock_text.setText(f"{int(left) // 60}:{int(left) % 60:02d}")
        recent = [e for t, e in self.arena.events if self.arena.time - t < 2.5 and "self-rights" not in e][-2:]
        self.ticker.setText("\n".join(recent) if self.stage == "fight" else "")
        self.cam_text.setText(f"view: {self.cam.name}   {self.clock.getAverageFrameRate():.0f} fps   gfx {args.gfx}")
        self.arena_vis.set_score(f"{self.player.name} {max(0, self.player.health):.0f}   "
                                 f"{int(left) // 60}:{int(left) % 60:02d}   {max(0, self.cpu.health):.0f} {self.cpu.name}")

    # ---------- every frame ----------
    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        if self.stage == "intro":
            self.run_intro(dt)
        elif not self.paused:
            self.read_controls()
            scale = 0.3 if self.slowmo > 0 else 1.0
            self.slowmo = max(0.0, self.slowmo - dt)
            self.accum += dt * scale
            while self.accum >= sim.STEP:
                self.arena.step()
                self.accum -= sim.STEP
                if self.stage == "fight":
                    self.fight_time += sim.STEP
            if self.stage == "fight":
                self.check_end()
        self.draw(dt, now)
        if args.screenshot and now - self.start > args.after:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()
            self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot)))
            self.userExit()
        return task.cont

    def run_intro(self, dt):
        self.stage_time += dt
        t = self.stage_time
        self.accum += dt
        while self.accum >= sim.STEP:  # robots settle during the intro (every weapon starts off)
            self.arena.step()
            self.accum -= sim.STEP
        if t < 2.5:
            self.big.setText(self.arena_mod["look"].get("name", "ROBOT LAB"))
            self.small.setText("")
        elif t < 5.0:
            self.big.setText(f"{self.player.name}  v  {self.cpu.name}")
            self.small.setText("the robot you drive  v  the computer")
        else:
            n = 3 - int(t - 5.0)
            if n >= 1:
                self.big.setText(str(n))
                self.small.setText("")
                if n not in self.beeped:
                    self.beeped.add(n)
                    self.snd.play("beep", 0.6)
            else:
                self.big.setText("ACTIVATE!")
                self.snd.play("go", 0.8)
                self.snd.react("cheer", time.perf_counter())
                self.activate()

    def read_controls(self):
        if args.autoplay or self.mouseWatcherNode is None or self.stage != "fight":
            if self.stage != "fight":
                self.player.control = (0.0, 0.0, False)
            return
        down = self.mouseWatcherNode.is_button_down
        self.player.drive((down(KeyboardButton.up()) - down(KeyboardButton.down())) * 1.0,
                          (down(KeyboardButton.left()) - down(KeyboardButton.right())) * 1.0,
                          bool(down(KeyboardButton.space())))

    def check_end(self):
        if self.stage_time < 1.2:
            self.stage_time += sim.STEP
            if self.stage_time >= 1.0:
                self.big.setText("")
        alive = [r for r in (self.player, self.cpu) if not r.knocked_out]
        if len(alive) < 2 or self.fight_time >= self.rules["match_seconds"]:
            if len(alive) == 1:
                winner, how = alive[0], "KNOCKOUT!"
            elif not alive:
                winner, how = None, "DOUBLE KNOCKOUT!"
            else:
                a, b = (max(0, r.health) / r.stats["armour"] for r in (self.player, self.cpu))
                winner = self.player if a > b else self.cpu if b > a else None
                how = "TIME! The judges decide"
            self.stage = "over"
            self.slowmo = 1.5
            self.snd.play("horn", 0.7)
            self.snd.react("applause", time.perf_counter())
            self.big.setText(how)
            self.small.setText((f"{winner.name} WINS!" if winner else "It's a draw") + "\nPress R for a rematch")
            self.cpu.brain = None
            self.cpu.control = (0.0, 0.0, False)

    def draw(self, dt, now):
        a = self.arena
        for i, (r, v) in enumerate(zip((self.player, self.cpu), self.visuals)):
            v.update({"pos": list(r.pos), "quat": list(r.np.getQuat()), "wpos": list(r.weapon_np.getPos()),
                      "wquat": list(r.weapon_np.getQuat()), "speed": r.speed, "rpm": r.weapon_rpm}, dt)
            if r.health < self.last_hp[i] - 0.5:
                self.flash[i] = now + 0.12
            self.last_hp[i] = r.health
            v.flash(now < self.flash[i])
            damage = 1 - max(0.0, r.health) / r.stats["armour"]
            if damage > 0.55 and not r.pos.z < -1:
                self.fx.smoke(tuple(r.pos), (damage - 0.55) / 0.45 + (1.0 if r.knocked_out else 0))
        for r in a.robots:  # Resident Robots move too
            if r.house:
                self.vis[r.id].update({"pos": list(r.pos), "quat": list(r.np.getQuat()), "wpos": list(r.weapon_np.getPos()),
                                       "wquat": list(r.weapon_np.getQuat()), "speed": r.speed, "rpm": r.weapon_rpm,
                                       "on": r.weapon_on}, dt)
            if r.flaming(a.time):
                tip, fwd = self.vis[r.id].nozzle()
                self.fx.flame(tip, fwd)
        # new hits: sparks, debris and sounds
        impacts, streams = a.take_fx()
        for pos, dmg, kind in impacts:
            victim = min(a.robots, key=lambda r: (r.pos - Point3(*pos)).length())
            self.fx.impact(pos, dmg, kind, tuple(c / 255 for c in victim.design["colour"]))
            far = (Point3(*pos) - self.camera.getPos()).length()
            self.snd.hit(kind, min(1.0, 0.35 + dmg / 25) * max(0.2, 1 - far / 30))
            if kind == "flip":
                self.snd.react("cheer", time.perf_counter())
            elif dmg >= 15 and kind not in ("bump", "wall"):
                self.snd.react("ooh", time.perf_counter())
        for pos, direction, count in streams[-40:]:
            self.fx.stream(pos, direction, count)
        self.fx.update(dt)
        # engine and spinner sounds
        self.snd.layers(self.music, 0.45, self.stage != "intro" or self.stage_time > 5, min(1.0, 0.45 + self.fx.shake))
        if any(a.hazard_state()["saw_hot"]):
            self.snd.loop("grind", "grind", 0.45)
        else:
            self.snd.stop("grind")
        if any(r.flaming(a.time) for r in a.robots):
            self.snd.loop("flame", "flame", 0.5)
        else:
            self.snd.stop("flame")
        for r in a.robots:  # each spinner's motor: the pitch follows its real speed (it bogs down on a hit)
            if r.weapon in ("spinner", "drum", "vdisc"):
                self.snd.spinner(f"spin{r.id}", r.weapon_rpm,
                                 0.0 if r.knocked_out else max(0.15, 1 - (r.pos - self.camera.getPos()).length() / 25))
            if r.fires > self.fire_counts.get(r.id, 0) and r.weapon in ("wedge", "hammer"):
                self.snd.play("pneumatic" if r.weapon == "wedge" else "swing",
                              0.8 * max(0.2, 1 - (r.pos - self.camera.getPos()).length() / 25))
            self.fire_counts[r.id] = r.fires
        if any(r.weapon == "chainsaw" and a.time < r.fire_until for r in a.robots):
            self.snd.loop("chainsaw", "chainsaw", 0.5)
        else:
            self.snd.stop("chainsaw")
        speed = abs(self.player.speed)
        self.snd.loop("motor", "motor", 0.05 + min(0.3, speed / 20), 0.6 + speed / 8)
        self.arena_vis.update(a.hazard_state())
        self.place_camera(dt, now)
        self.update_hud(now)

    def place_camera(self, dt, now):
        if self.stage == "intro":  # a slow sweep round the arena before the fight
            ang = self.stage_time * 0.45 - 1.2
            self.camera.setPos(math.sin(ang) * 11, -math.cos(ang) * 11, 4.5 + self.stage_time * 0.2)
            self.camera.lookAt(0, 0, 0.5)
            self.camLens.setFov(60)
            self.cam.pos = None
            return
        front = self.player.shape["half"].y
        targets = [r.pos for r in (self.player, self.cpu) if not r.knocked_out]
        self.cam.update(dt, self.visuals[0].chassis, front, targets, self.fx.shake_offset())


RobotWars().run()
