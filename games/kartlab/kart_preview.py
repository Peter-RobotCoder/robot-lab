"""Kart Lab graphics preview: the Club Circuit with four computer karts racing, no server, for looking at the art.

    python kart_preview.py                         a window, the chase camera on kart 0
    python kart_preview.py --gfx low --track oval
    python kart_preview.py --offscreen --screenshot shot.png --after 8 --camera tv
    python kart_preview.py --offscreen --run 10    ten seconds, then the frame rate
    python kart_preview.py --gfx lines --lines "#ffb000"   the vector look in amber (CHANGE 144)
    python kart_preview.py --offscreen --screenshot s.png --closeup   the followed kart close up

An offscreen screenshot steps the race one tick a frame (not by the clock), so every tier shows the same moment.

Keys:  C next camera   1-4 follow that kart   R restart the race   Esc out of full screen (the button top right)
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
ap.add_argument("--closeup", action="store_true", help="the camera close to the followed kart, from the front")
ap.add_argument("--steer", type=float, default=None, help="draw every kart steering this much (-1 right to 1 left: CHANGE 157)")
ap.add_argument("--shield", action="store_true", help="every kart with a shield up (CHANGE 159)")
ap.add_argument("--damage", default=None, help="draw every kart this damaged: six numbers 0 to 1, wing,fl,fr,rl,rr,engine (CHANGE 158)")
ap.add_argument("--track", choices=["club", "oval", "straight"], default="club")
ap.add_argument("--camera", choices=["chase", "hood", "tv"], default="chase")
ap.add_argument("--laps", type=int, default=None)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=8.0, help="seconds before the screenshot")
ap.add_argument("--run", type=float, default=None, help="run this many seconds, print the frame rate and quit")
args = ap.parse_args()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kart_version  # noqa: E402
sys.path.insert(0, kart_version.ENGINE_HOME)
from engine import full_screen, gfx_tiers, wire  # noqa: E402

loadPrcFileData("", "win-size 1600 900\nwindow-title Kart Lab preview\nsync-video true\n")
loadPrcFileData("", gfx_tiers.prc_for(args.gfx))
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\nwin-size 1280 720\naudio-library-name null\n")

from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename  # noqa: E402

import kart_gfx  # noqa: E402
import kart_sim as sim  # noqa: E402
import kart_items  # noqa: E402  (CHANGE 159)
import kart_track  # noqa: E402

COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40)]
NAMES = ["Violet", "Blue", "Green", "Yellow"]
DESIGNS = [{"name": "Violet", "colour": (180, 90, 230), "speed": 45, "acceleration": 30, "grip": 25},
           {"name": "Blue", "colour": (60, 130, 230), "speed": 30, "acceleration": 40, "grip": 30},
           {"name": "Green", "colour": (60, 190, 90), "speed": 25, "acceleration": 30, "grip": 45},
           {"name": "Yellow", "colour": (240, 190, 40), "speed": 34, "acceleration": 33, "grip": 33}]


def drive(track, k):
    """A simple computer driver: aim at a point ahead on the centre line, ease off for sharp bends, and drift
    through them when fast enough (so the smoke and the boost show)."""
    v = k["v"]
    look = 6.0 + 0.45 * v
    tx, ty, _ = track.point(k["s"] + look)
    want = math.degrees(math.atan2(ty - k["y"], tx - k["x"]))
    err = (want - k["yaw"] + 180.0) % 360.0 - 180.0
    steer = max(-1.0, min(1.0, err / 25.0))
    bend = track.curvature(k["s"], 18)
    throttle = 0.2 if abs(bend) >= 25 and v > 12 else 1.0
    buttons = sim.DRIFT if abs(bend) >= 32 and v > 11 else 0
    return throttle, steer, buttons


class Preview(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.track = kart_track.load(args.track)
        self.pipeline = kart_gfx.init(self, args.gfx, line_colour=args.lines)
        started = time.perf_counter()
        self.track_vis = kart_gfx.TrackVisual(self.render, self.track)
        self.items_vis = kart_gfx.ItemsVisual(self.render, self.track)  # (CHANGE 159) the power-ups
        extra = [f"{k} {getattr(self.track_vis, a):.2f} s" for k, a in (("lines", "lines_secs"), ("circuit", "circuit_secs"))
                 if hasattr(self.track_vis, a)]
        print(f"track built in {time.perf_counter() - started:.2f} s at {kart_gfx.tier()}"
              + (f" ({', '.join(extra)})" if extra else ""), flush=True)
        self.fixed = bool(args.offscreen and args.screenshot)  # (one tick a frame: the same moment on every tier)
        self.sim_time = 0.0
        self.schema = wire.Schema("kart", sim.SCHEMA_FIELDS)
        self.cam = kart_gfx.ChaseCamera(self, args.camera)
        self.hud = kart_gfx.Hud(self, self.track)
        self.follow = 0
        self.karts = {}
        self.new_race()
        self.accept("c", self.cam.cycle)
        self.accept("r", self.new_race)
        if not args.offscreen:  # (CHANGE 146: a full screen button; Esc comes out of full screen, never quits)
            self.full = full_screen.FullScreen(self)
        for i in range(4):
            self.accept(str(i + 1), self.set_follow, [i])
        self.start = self.last = time.perf_counter()
        self.accum = 0.0
        self.prev = None
        self.taskMgr.add(self.update, "update")

    def set_follow(self, i):
        self.follow = i
        self.cam.pos = None

    def new_race(self):
        for v in self.karts.values():
            v.destroy()
        self.race = sim.Race(self.track, self.schema, laps=args.laps)
        self.karts = {}
        for i, d in enumerate(DESIGNS):
            self.race.add(i, d)
            vis = kart_gfx.KartVisual(self.render, d, kart_gfx.mats())
            vis.set_label(d["name"], (*(c / 255 for c in d["colour"]), 1))
            self.karts[i] = vis
        self.race.items = kart_items.Items(self.race)  # (CHANGE 159)
        self.race.start()
        self.prev = None

    def update(self, task):
        now = time.perf_counter()
        dt = min(now - self.last, 0.1)
        self.last = now
        if self.fixed:
            dt = sim.STEP
            self.sim_time += dt
            now = self.start + self.sim_time
        self.accum += dt
        steps = 0
        while self.accum >= sim.STEP and steps < 5:  # (a stall never makes the race run away)
            self.prev = {i: dict(k) for i, k in self.race.karts.items()}
            inputs = {}
            for i, k in self.race.karts.items():  # (and their items, as the computer karts use them: CHANGE 159)
                th, st, bt = drive(self.track, k)
                inputs[i] = (th, st, bt | kart_items.cpu_use(k, self.race))
            self.race.step_all(inputs)
            self.accum -= sim.STEP
            steps += 1
        alpha = max(0.0, min(1.0, self.accum / sim.STEP))
        self.draw(dt, alpha, now)
        if args.screenshot and now - self.start > args.after:
            self.graphicsEngine.renderFrame()
            self.graphicsEngine.renderFrame()
            self.win.saveScreenshot(Filename.fromOsSpecific(os.path.abspath(args.screenshot)))
            print("screenshot:", os.path.abspath(args.screenshot), flush=True)
            if args.run is None:
                self.userExit()
        if args.run is not None and now - self.start > args.run:
            print(f"{self.clock.getAverageFrameRate():.1f} fps over {args.run:.0f} s at {kart_gfx.tier()} "
                  f"({self.render.countNumDescendants()} nodes under render)", flush=True)
            self.userExit()
        return task.cont

    def shown(self, i, alpha):
        """The kart's state between the last tick and this one (what the class window shows too)."""
        k = self.race.karts[i]
        p = (self.prev or {}).get(i)
        if p is None or alpha >= 1.0:
            return dict(k)
        out = dict(k)
        for f in ("x", "y", "v", "u"):
            out[f] = p[f] + (k[f] - p[f]) * alpha
        dyaw = (k["yaw"] - p["yaw"] + 180.0) % 360.0 - 180.0
        out["yaw"] = p["yaw"] + dyaw * alpha
        return out

    def draw(self, dt, alpha, now):
        self.track_vis.update(now - self.start, self.race.countdown())  # (ultra's start lights: CHANGE 151)
        self.items_vis.update(dt, self.race.items.state())  # (CHANGE 159)
        states = {i: self.shown(i, alpha) for i in self.race.karts}
        for i, k in states.items():
            z = self.track.height(k["s"])
            inp = drive(self.track, self.race.karts[i])
            drifting = bool(k["flags"] & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R))
            self.karts[i].update(k["x"], k["y"], z, k["yaw"], inp[1] if args.steer is None else args.steer, k["v"], k["u"], drifting,
                                 bool(k["flags"] & sim.FLAG_BOOSTING), dt,
                                 [float(v) for v in args.damage.split(",")] if args.damage else sim.damage_of(k),
                                 args.shield or k.get("shield", 0) > 0)
        me = states[self.follow]
        self.cam.update(dt, me["x"], me["y"], self.track.height(me["s"]), me["yaw"], me["v"], self.track)
        if args.closeup:  # three quarters from the front, a little above
            yaw = math.radians(me["yaw"])
            fwd, left = (math.cos(yaw), math.sin(yaw)), (-math.sin(yaw), math.cos(yaw))
            z = self.track.height(me["s"])
            self.camera.setPos(me["x"] + fwd[0] * 1.9 + left[0] * 1.3, me["y"] + fwd[1] * 1.9 + left[1] * 1.3, z + 0.95)
            self.camera.lookAt(me["x"] - fwd[0] * 0.1, me["y"] - fwd[1] * 0.1, z + 0.38)
            self.camLens.setFov(48)
        places = self.race.places()
        mine = self.race.karts[self.follow]
        results = self.race.results() if self.race.phase == sim.FLAGS_OVER else None
        dots = [(k["x"], k["y"], DESIGNS[i]["colour"], i == self.follow) for i, k in states.items()]
        self.hud.update(mine["lap"] + 1, self.race.laps, places.index(self.follow) + 1, len(places), me["v"] * 3.6,
                        self.race.countdown(), bool(mine["flags"] & sim.FLAG_WRONG_WAY), mine["charge"], dots, results,
                        [float(v) for v in args.damage.split(",")] if args.damage else None)  # (CHANGE 158)
        self.hud.status(f"{self.clock.getAverageFrameRate():.0f} fps   gfx {kart_gfx.tier()}   camera {self.cam.name}"
                        f"   C camera  1-4 follow  R restart")


Preview().run()
