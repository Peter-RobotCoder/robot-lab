"""Robot Lab graphics preview: the arena with four learners' robots and the Resident Robots fighting, no server, for
looking at the art and timing the graphics tiers (CHANGE 145, as kart/kart_preview.py is Kart Lab's).

    python lab_preview.py                          a window, the zoomed arena follow camera
    python lab_preview.py --gfx ultra --camera third
    python lab_preview.py --offscreen --screenshot shot.png --after 5 --camera centre
    python lab_preview.py --offscreen --run 10     ten seconds, then the frame rate
    python lab_preview.py --run 12 --still 2 --novsync   the drawing alone in a real window, as fast as it goes
    python lab_preview.py --gfx lines --lines "#ffb000"   the vector look in amber
    python lab_preview.py --offscreen --screenshot s.png --closeup 0   robot 0 close up, from the front (the six
                                                   learners' robots are 0 to 5, the Resident Robots 6 to 9)
    python lab_preview.py --mods flame_pit,ramps   with the teacher's user mods on

An offscreen screenshot steps the fight one tick a frame (not by the clock), so every tier shows the same moment.

Keys:  C next camera   1-8 follow that robot   R restart   Esc out of full screen (the button top right)
"""
import argparse
import math
import os
import sys
import time

from panda3d.core import loadPrcFileData

ap = argparse.ArgumentParser()
ap.add_argument("--gfx", choices=["mesh", "lines", "basic", "low", "medium", "high", "ultra"], default="medium")
ap.add_argument("--lines", default=None, help="mesh and lines: their colour, #rrggbb")
ap.add_argument("--camera", choices=["third", "fpv", "zoom", "arena", "centre"], default="zoom")
ap.add_argument("--closeup", type=int, default=None, help="the camera close to this robot, from the front")
ap.add_argument("--view", default=None, help="a fixed camera: x,y,z,look x,look y,look z[,fov]")
ap.add_argument("--mods", default="", help="user mods switched on, comma separated (lab_sim.USER_MODS)")
ap.add_argument("--no-house", action="store_true", help="no Resident Robots")
ap.add_argument("--window", default="1280x720")
ap.add_argument("--novsync", action="store_true", help="a real window that draws as fast as it can")
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--prc", action="append", default=[],
                help="a Panda3D setting to try, e.g. \"threading-model Cull/Draw\" (CHANGE 169: the trials)")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=5.0, help="seconds before the screenshot")
ap.add_argument("--run", type=float, default=None, help="run this many seconds, print the frame rate and quit")
ap.add_argument("--still", type=float, default=None,
                help="stop the fight after this many seconds and only draw (the graphics' own cost: a class window "
                     "runs no physics)")
args = ap.parse_args()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lab_version  # noqa: E402  (puts the engine package on the path)
from engine import full_screen, gfx_tiers  # noqa: E402

w, h = (int(v) for v in args.window.lower().split("x"))
loadPrcFileData("", f"win-size {w} {h}\nwindow-title Robot Lab preview\nsync-video {'false' if args.novsync else 'true'}\n")
loadPrcFileData("", gfx_tiers.prc_for(args.gfx))
for line in args.prc:  # (after the tier's: a trial's setting wins)
    loadPrcFileData("", line)
if args.offscreen:
    loadPrcFileData("", f"window-type offscreen\nwin-size {w} {h}\naudio-library-name null\n")

from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, Point3, Vec3  # noqa: E402

import lab_sim as sim  # noqa: E402
import rw_fx  # noqa: E402
import rw_gfx  # noqa: E402
from rw_camera import GameCamera  # noqa: E402

# four learners' robots, one of each of the four first weapons, and two that learners asked for
DESIGNS = [
    {"name": "TITAN", "colour": [235, 110, 20], "weapon": "wedge", "settings": {"size": 105},
     "style": {"trim": [28, 28, 32], "lights": [255, 170, 40], "number": "TITAN"}},
    {"name": "RAZORBACK", "colour": [200, 20, 28], "weapon": "spinner", "settings": {"size": 100},
     "style": {"trim": [225, 225, 230], "lights": [60, 170, 255], "number": "RAZOR"}},
    {"name": "Drummer", "colour": [40, 120, 220], "weapon": "drum", "settings": {"size": 95},
     "style": {"trim": [30, 30, 34], "lights": [255, 60, 30], "number": "DRUM"}},
    {"name": "Thumper", "colour": [70, 170, 80], "weapon": "hammer", "settings": {"size": 110},
     "style": {"trim": [240, 200, 40], "lights": [255, 255, 255], "number": "THUMP"}},
    {"name": "Scorch", "colour": [250, 200, 40], "weapon": "flame", "settings": {"size": 90},
     "style": {"trim": [40, 40, 44], "lights": [255, 90, 20], "number": "SCORCH"}},
    {"name": "Zap", "colour": [150, 80, 220], "weapon": "laser", "settings": {"size": 85},
     "style": {"trim": [230, 230, 235], "lights": [255, 40, 40], "number": "ZAP"}},
]


class Preview(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.mods = {k: True for k in args.mods.split(",") if k in sim.USER_MODS}
        self.hazards = {"pit": True, "floor_flipper": True, "saws": True, "spikes": True,
                        "house_robots": not args.no_house}
        self.look = {"name": "ROBOT LAB", "wall_colour": [155, 25, 20], "crowd": True}
        self.pipeline = rw_gfx.init(self, args.gfx, line_colour=args.lines)
        started = time.perf_counter()
        self.arena_vis = rw_gfx.ArenaVisual(self.render, self.hazards, self.look, self.mods)
        print(f"arena built in {time.perf_counter() - started:.2f} s at {rw_gfx.tier()}", flush=True)
        self.fx = rw_fx.Effects(self.render, "low" if rw_gfx.tier() in ("basic", "low") else rw_gfx.tier())
        self.cam = GameCamera(self, args.camera)
        self.fixed = bool(args.offscreen and args.screenshot)  # (one tick a frame: the same moment on every tier)
        self.sim_time = 0.0
        self.follow = 0
        self.vis = {}
        self.new_fight()
        self.accept("c", self.cam.cycle)
        self.accept("r", self.new_fight)
        if not args.offscreen:  # (CHANGE 146: a full screen button; Esc comes out of full screen, never quits)
            self.full = full_screen.FullScreen(self)
        for i in range(8):
            self.accept(str(i + 1), self.set_follow, [i])
        self.frame_times = []
        self.start = self.last = time.perf_counter()
        self.accum = 0.0
        self.taskMgr.add(self.update, "update")

    def set_follow(self, i):
        self.follow = min(i, len(self.order) - 1)
        self.cam.pos = None

    def new_fight(self):
        for v in self.vis.values():
            v.destroy()
        self.arena = sim.Arena(hazards=self.hazards, user_mods=self.mods)
        started = time.perf_counter()
        for i, d in enumerate(DESIGNS):
            self.arena.add_robot(dict(d, points={"speed": 25, "attack": 25, "armour": 25, "control": 25},
                                      settings=dict(forward_speed=80, reverse_speed=60, turn_speed=70, acceleration=70,
                                                    **d["settings"])), owner=f"learner {i + 1}")
        self.vis = {}
        for r in self.arena.robots:
            v = rw_gfx.RobotVisual(self.render, r.design)
            v.set_label(f"{r.name}\nResident Robot" if r.house else r.owner, (1, 0.75, 0.3, 1) if r.house else (1, 1, 1, 1))
            self.vis[r.id] = v
        self.order = [r.id for r in self.arena.robots if not r.house] + [r.id for r in self.arena.robots if r.house]
        print(f"{len(self.vis)} robots built in {time.perf_counter() - started:.2f} s", flush=True)
        self.cam.pos = None

    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.frame_times.append(now - self.last)
        self.last = now
        if self.fixed:
            dt = sim.STEP
            self.sim_time += dt
            now = self.start + self.sim_time
        self.accum += dt
        steps = 0
        if args.still is not None and now - self.start > args.still:
            self.accum = 0.0
        while self.accum >= sim.STEP and steps < 5:  # (a stall never makes the fight run away)
            self.arena.step()
            self.accum -= sim.STEP
            steps += 1
        self.draw(dt, now)
        if args.screenshot and now - self.start > args.after:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()
            self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot)))
            print("screenshot:", os.path.abspath(args.screenshot), flush=True)
            if args.run is None:
                self.userExit()
        if args.run is not None and now - self.start > args.run:
            ft = sorted(self.frame_times[60:]) or [0.0]  # (the first second: shaders compiling)
            missed = 100.0 * sum(1 for t in ft if t > 0.022) / len(ft)
            print(f"{self.clock.getAverageFrameRate():.1f} fps over {args.run:.0f} s at {rw_gfx.tier()} "
                  f"({len(ft) / max(1e-6, sum(ft)):.1f} fps by frames, median frame {ft[len(ft) // 2] * 1000:.1f} ms, 99th percentile frame "
                  f"{ft[int(len(ft) * 0.99) - 1] * 1000:.1f} ms, {missed:.1f}% over 22 ms; "
                  f"{self.render.countNumDescendants()} nodes under render)", flush=True)
            self.userExit()
        return task.cont

    def state(self, r):
        return {"pos": list(r.pos), "quat": list(r.np.getQuat()), "wpos": list(r.weapon_np.getPos()),
                "wquat": list(r.weapon_np.getQuat()), "speed": r.speed, "rpm": r.weapon_rpm, "on": r.weapon_on}

    def draw(self, dt, now):
        a = self.arena
        for r in a.robots:
            v = self.vis[r.id]
            v.update(self.state(r), dt)
            if r.flaming(a.time):
                tip, fwd = v.nozzle()
                self.fx.flame(tip, fwd)
        impacts, streams = a.take_fx()
        for pos, dmg, kind in impacts:
            victim = min(a.robots, key=lambda r: (r.pos - Point3(*pos)).length())
            self.fx.impact(pos, dmg, kind, tuple(c / 255 for c in victim.design["colour"]))
        for pos, direction, count in streams[-40:]:
            self.fx.stream(pos, direction, count)
        self.fx.update(dt)
        self.arena_vis.update(a.hazard_state())
        rid = self.order[self.follow]
        me = next(r for r in a.robots if r.id == rid)
        targets = [r.pos for r in a.robots if not r.knocked_out and not r.house]
        self.cam.update(dt, self.vis[rid].chassis, me.shape["half"].y, targets, Vec3(0))
        if args.closeup is not None:  # three quarters from the front, a little above
            rid = self.order[min(args.closeup, len(self.order) - 1)]
            r = next(r for r in a.robots if r.id == rid)
            q = self.vis[r.id].chassis.getQuat(self.render)
            fwd, right = q.getForward(), q.getRight()
            fwd.z = right.z = 0
            fwd.normalize()
            right.normalize()
            k = max(1.0, r.shape["half"].y / 0.8)
            p = r.pos
            self.camera.setPos(p + fwd * 2.3 * k + right * 1.5 * k + Vec3(0, 0, 1.25 * k))
            self.camera.lookAt(p + Vec3(0, 0, 0.25 * k))
            self.camLens.setFov(45)
        elif args.view:
            v = [float(x) for x in args.view.split(",")]
            self.camera.setPos(*v[:3])
            self.camera.lookAt(*v[3:6])
            self.camLens.setFov(v[6] if len(v) > 6 else 60)


Preview().run()
