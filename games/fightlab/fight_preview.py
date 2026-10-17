"""Fight Lab graphics preview: the hall with fighters of every body fighting in three rings, no server, for looking at
the art and timing the graphics tiers (CHANGE 147, as shared-world-demo/lab_preview.py is Robot Lab's).

    python fight_preview.py                          a window, the fight camera on ring 1
    python fight_preview.py --gfx ultra --camera ring
    python fight_preview.py --offscreen --screenshot shot.png --after 5 --camera all
    python fight_preview.py --offscreen --run 10     ten seconds, then the frame rate
    python fight_preview.py --run 12 --still 2 --novsync   the drawing alone in a real window, as fast as it goes
    python fight_preview.py --gfx lines --lines "#ffb000"   the vector look in amber
    python fight_preview.py --offscreen --screenshot s.png --closeup 0   fighter 0 close up, from the front (two to
                                                   a ring: 0 and 1 in ring 1, 2 and 3 in ring 2...)
    python fight_preview.py --hazards ropes,electric_ropes,fire_jets   with ropes and hazards (else ring-outs)

The rings: 1 a built robot and a martial artist (BLAZE, KAITO), 2 the detailed 3D woman and man (Penthesilea,
Achilles), 3 two bosses (GOLIATH, SHADE), then Robin and KRAGG, VOLTRIX and Kaito (--rings up to 5). Practice
fights: they never end. An offscreen screenshot steps the fight one tick a frame (not by the clock) with the dice
seeded, so every tier shows the same moment.

Keys:  V next camera   1-6 watch that ring   R restart   Esc out of full screen (the button top right)
"""
import argparse
import os
import random
import sys
import time

from panda3d.core import loadPrcFileData

ap = argparse.ArgumentParser()
ap.add_argument("--gfx", choices=["mesh", "lines", "basic", "low", "medium", "high", "ultra"], default="medium")
ap.add_argument("--lines", default=None, help="mesh and lines: their colour, #rrggbb")
ap.add_argument("--camera", choices=["fight", "me", "shoulder", "ring", "all"], default="fight")
ap.add_argument("--ring", type=int, default=1, help="the ring the camera watches (1 to --rings)")
ap.add_argument("--rings", type=int, default=3, choices=[1, 2, 3, 4, 5])
ap.add_argument("--closeup", type=int, default=None, help="the camera close to this fighter, from the front")
ap.add_argument("--view", default=None, help="a fixed camera: x,y,z,look x,look y,look z[,fov]")
ap.add_argument("--hazards", default="", help="ropes (no ring-outs), electric_ropes, fire_jets, slippery, spikes")
ap.add_argument("--window", default="1280x720")
ap.add_argument("--novsync", action="store_true", help="a real window that draws as fast as it can")
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=5.0, help="seconds before the screenshot")
ap.add_argument("--run", type=float, default=None, help="run this many seconds, print the frame rate and quit")
ap.add_argument("--still", type=float, default=None,
                help="stop the fight after this many seconds and only draw (the graphics' own cost)")
args = ap.parse_args()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fight_version  # noqa: E402
sys.path.insert(0, fight_version.ENGINE_HOME)  # (the engine package, shared by every game)
from engine import full_screen, gfx_tiers  # noqa: E402

w, h = (int(v) for v in args.window.lower().split("x"))
loadPrcFileData("", f"win-size {w} {h}\nwindow-title Fight Lab preview\nsync-video {'false' if args.novsync else 'true'}\n")
loadPrcFileData("", gfx_tiers.prc_for(args.gfx))
if args.offscreen:
    loadPrcFileData("", f"window-type offscreen\nwin-size {w} {h}\naudio-library-name null\n")

from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, Point3, Vec3  # noqa: E402

import cpu_brains  # noqa: E402
import fight_fx  # noqa: E402
import fight_gfx  # noqa: E402
import fight_model  # noqa: E402
import fight_mods  # noqa: E402
import fight_sim as sim  # noqa: E402
from fight_camera import FightCamera  # noqa: E402

# who fights in each ring: the example fighters' files (mods/fighters) or a boss's name
PAIRS = [("blaze", "kaito"), ("penthesilea", "achilles"), ("GOLIATH", "SHADE"), ("robin", "KRAGG"), ("VOLTRIX", "kaito")]


class Preview(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()
        fighters, stage_mod, _ = fight_mods.load_all()  # (the mods' rules: the ring's size)
        self.designs = {d["name"].lower(): d for d in fighters.values()}
        self.designs.update({n.lower(): sim.boss_design(n) for n in sim.BOSS_BY_NAME})
        hz = set(args.hazards.split(","))
        self.hazards = {"ring_out": "ropes" not in hz, "electric_ropes": "electric_ropes" in hz,
                        "fire_jets": "fire_jets" in hz, "slippery": "slippery" in hz, "spikes": "spikes" in hz}
        self.look = dict(stage_mod["look"])
        self.pipeline = fight_gfx.init(self, args.gfx, line_colour=args.lines)
        started = time.perf_counter()
        self.stage_vis = fight_gfx.StageVisual(self.render, list(range(args.rings)), self.hazards, self.look)
        print(f"stage built in {time.perf_counter() - started:.2f} s at {fight_gfx.tier()}", flush=True)
        self.fx = fight_fx.Effects(self.render, "low" if fight_gfx.tier() in ("basic", "low") else fight_gfx.tier())
        self.cam = FightCamera(self, args.camera)
        self.fixed = bool(args.offscreen and args.screenshot)  # (one tick a frame: the same moment on every tier)
        self.watch = max(0, min(args.rings, args.ring) - 1)
        self.vis = {}
        self.new_fight()
        self.accept("v", self.cam.cycle)
        self.accept("r", self.new_fight)
        for i in range(6):
            self.accept(str(i + 1), self.set_watch, [i])
        if not args.offscreen:  # (CHANGE 146: a full screen button; Esc comes out of full screen, never quits)
            self.full = full_screen.FullScreen(self)
        self.frame_times = []
        self.start = self.last = time.perf_counter()
        self.sim_time = 0.0
        self.accum = 0.0
        self.taskMgr.add(self.update, "update")

    def set_watch(self, i):
        self.watch = min(i, len(self.stage.rings) - 1)
        self.cam.pos = None

    def new_fight(self):
        for v in self.vis.values():
            v.destroy()
        if self.fixed:  # (the computer fighters' dice and the sparks the same on every tier)
            random.seed(147)
            self.fx.rnd.seed(147)
        self.stage = sim.Stage(hazards=self.hazards, practice=True)
        started = time.perf_counter()
        self.vis, self.order = {}, []
        for a, b in PAIRS[:args.rings]:
            ring = self.stage.add_ring()
            for who in (a, b):
                f = ring.add_fighter(self.designs[who.lower()], brain=cpu_brains.for_level("expert"))
                v = fight_model.make(self.render, f.design)
                v.set_label(f"{f.name}\n{'Boss' if f.design.get('model') else f.design.get('body', 'robot')}",
                            (1, 0.75, 0.3, 1) if f.design.get("model") else (1, 1, 1, 1))
                self.vis[f.id] = v
                self.order.append(f)
        print(f"{len(self.vis)} fighters built in {time.perf_counter() - started:.2f} s", flush=True)
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
        if args.still is None or now - self.start < args.still:
            self.accum += dt
        steps = 0
        while self.accum >= sim.STEP and steps < 5:  # (a stall never makes the fight run away)
            self.stage.step()
            self.accum -= sim.STEP
            steps += 1
        self.draw(dt)
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
            print(f"{self.clock.getAverageFrameRate():.1f} fps over {args.run:.0f} s at {fight_gfx.tier()} "
                  f"({len(ft) / max(1e-6, sum(ft)):.1f} fps by frames, median frame {ft[len(ft) // 2] * 1000:.1f} ms, "
                  f"99th percentile frame {ft[int(len(ft) * 0.99) - 1] * 1000:.1f} ms, {missed:.1f}% over 22 ms; "
                  f"{self.render.countNumDescendants()} nodes under render)", flush=True)
            self.userExit()
        return task.cont

    def draw(self, dt):
        st = self.stage
        rings = [sim.ring_state(r, st.time) for r in st.rings]
        self.stage_vis.update(rings, st.time, dt)
        for rs in rings:
            for s in rs["f"]:
                self.vis[s["id"]].update(s, dt)
        for pos, dmg, kind in st.take_fx():
            victim = min(self.order, key=lambda f: (f.x - pos[0]) ** 2 + (f.y - pos[1]) ** 2)
            self.fx.impact(pos, dmg, kind, tuple(c / 255 for c in victim.design["colour"]),
                           victim.design.get("body", "robot") == "robot")
            if kind == "zap":
                self.stage_vis.zap(pos)
        self.fx.update(dt)
        ring = rings[self.watch]
        fs = [s for s in ring["f"] if s["a"] != "ringout" or s["pos"][2] > -1.5]
        me = Point3(*fs[0]["pos"]) if fs else None
        other = Point3(*fs[1]["pos"]) if len(fs) > 1 else None
        self.cam.update(dt, me, other, tuple(ring["c"]), [tuple(r["c"]) for r in rings], self.fx.shake_offset() * 0.5)
        if args.closeup is not None:  # from the front and a little to the side, at head height
            f = self.order[min(args.closeup, len(self.order) - 1)]
            v = self.vis[f.id]
            q = v.root.getQuat(self.render)
            fwd, right = q.getForward(), q.getRight()
            fwd.z = right.z = 0
            fwd.normalize()
            right.normalize()
            k = v.size
            p = Point3(f.x, f.y, f.z)
            self.camera.setPos(p + fwd * 2.6 * k + right * 1.2 * k + Vec3(0, 0, 1.45 * k))
            self.camera.lookAt(p + Vec3(0, 0, 0.95 * k))
            self.camLens.setFov(45)
        elif args.view:
            vals = [float(x) for x in args.view.split(",")]
            self.camera.setPos(*vals[:3])
            self.camera.lookAt(*vals[3:6])
            self.camLens.setFov(vals[6] if len(vals) > 6 else 60)


Preview().run()
