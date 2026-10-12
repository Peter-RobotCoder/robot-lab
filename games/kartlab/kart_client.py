"""Kart Lab: the window. Drive a kart round the track against the class and the computer.

    python kart_client.py                          join the laptop test server (ws://127.0.0.1:8782) as a learner
    python kart_client.py --teacher                ...as the teacher (Enter starts the race, G puts everyone on the grid)
    python kart_client.py --offline --cpu 5        no server: a race on this laptop against five computer karts
    python kart_client.py --host wss://play.clubcoders.co.uk/class3 --name Violet --code CLUB42

Keys: arrows or WASD drive, Shift (or Space) drifts, R puts you back on the track, V changes the camera,
U uploads brains/my_brain.py to drive your kart, P switches that autopilot on and off.

How your own kart feels instant online: the window steps its own kart itself with every key press (kart_sim.step,
the same arithmetic the server runs) and sends the numbered inputs; each snapshot from the server says which
input it had applied, the window compares the server's kart with what it predicted for that moment and, when they
differ by more than 5 cm, puts the server's state in and replays the inputs since (engine.predict). The other karts
are drawn a little in the past, between two snapshots (engine.interp). Bumps between karts are the server's to
decide: a bump shows on your screen when its word arrives, eased in so it never jumps.
"""
import argparse
import json
import math
import os
import queue
import sys
import time

import kart_version
sys.path.insert(0, kart_version.ENGINE_HOME)

ap = argparse.ArgumentParser()
ap.add_argument("--host", default=None, help="server address (default: this computer)")
ap.add_argument("--name", default=None)
ap.add_argument("--password", default="", help=argparse.SUPPRESS)  # (passed by the Club Coders app; not used yet)
ap.add_argument("--ticket", help=argparse.SUPPRESS)  # (from the club desk: the app has logged this person in)
ap.add_argument("--code", default=None, help="class code (CLUB42 / TEACH99 on a laptop test server)")
ap.add_argument("--teacher", action="store_true")
ap.add_argument("--gfx", default="auto", help="auto, basic, low, medium or high")
ap.add_argument("--offline", action="store_true", help="a race on this laptop, no server")
ap.add_argument("--track", default="club")
ap.add_argument("--cpu", type=int, default=3, help="computer karts (offline)")
ap.add_argument("--level", default="medium", help="their level: easy, medium, expert (offline)")
ap.add_argument("--laps", type=int, default=None)
ap.add_argument("--stats", default=None, help="your design: speed,acceleration,grip points (100 in all)")
ap.add_argument("--brain", default=None, help="a brain file to drive your kart (offline)")
ap.add_argument("--no-predict", action="store_true", help="draw your own kart from the server's snapshots only")
ap.add_argument("--no-interp", action="store_true", help="draw each snapshot as it arrives")
ap.add_argument("--screenshot")
ap.add_argument("--after", type=float, default=6)
ap.add_argument("--offscreen", action="store_true")
ap.add_argument("--autostart", action="store_true", help="offline: start the race at once")
ap.add_argument("--mute", action="store_true")
ap.add_argument("--panel", action="store_true", help=argparse.SUPPRESS)  # (tests: open the Tab panel at once)
args = ap.parse_args()
if os.environ.get("KARTLAB_LOGIN") and not args.name:  # reopened by the app: the same login
    try:
        args.name, args.password, *rest = json.loads(os.environ.pop("KARTLAB_LOGIN"))
        args.ticket = rest[0] if rest and rest[0] else args.ticket
    except (ValueError, TypeError):
        pass

from panda3d.core import loadPrcFileData  # noqa: E402
from engine import club_ticket  # noqa: E402

if args.ticket:  # the club desk has logged this person in: their name is in the ticket (the server checks it)
    args.name = (club_ticket.peek(args.ticket) or {}).get("name") or args.name
    args.teacher = args.teacher or (club_ticket.peek(args.ticket) or {}).get("role") == "teacher"

try:
    from engine import gfx_tiers  # noqa: E402
    from engine import hud as engine_hud  # noqa: E402
    engine_hud.setup(os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders")) \
        if hasattr(engine_hud, "setup") else None
    TIER = gfx_tiers.resolve(engine_hud.SETTINGS_DIR, None if args.gfx == "auto" else args.gfx)
    loadPrcFileData("", gfx_tiers.prc_for(TIER))
except Exception as e:  # (the tiers module missing or unhappy: medium, as the other games' default was)
    gfx_tiers = None
    TIER = args.gfx if args.gfx in ("basic", "low", "medium", "high") else "medium"
    print(f"Graphics tiers not used ({e!r}): {TIER}", flush=True)
loadPrcFileData("", f"win-size 1280 720\nwindow-title Kart Lab\n"
                    + ("framebuffer-multisample 1\nmultisamples 4\n" if TIER in ("medium", "high") else ""))
if args.offscreen:
    loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")

from direct.gui.DirectGui import DirectFrame  # noqa: E402
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from panda3d.core import Filename, KeyboardButton  # noqa: E402
from engine.hud import GREY, OFF, ON, PANEL, WHITE, YELLOW, button, label  # noqa: E402

from engine import interp, predict, wire  # noqa: E402
from engine.net import Net  # noqa: E402
from engine import net as net_module  # noqa: E402

import cpu_brains  # noqa: E402
import kart_gfx  # noqa: E402
import kart_sim as sim  # noqa: E402
import kart_sound  # noqa: E402
import kart_track  # noqa: E402

SCHEMA = wire.Schema("kart", sim.SCHEMA_FIELDS)
SNAP_SPEC = {"entities": ["id", {"x": "lerp", "y": "lerp", "yaw": "angle", "v": "lerp", "u": "lerp"}]}
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230), (240, 120, 40),
           (60, 200, 200), (230, 90, 160)]  # (the server's order too: the computer karts' colours)
HERE = os.path.dirname(os.path.abspath(__file__))
BRAINS = os.path.join(os.path.dirname(sys.executable), "brains", "kartlab") if kart_version.FROZEN else os.path.join(HERE, "brains")  # (Club Coders: each game has its own brains folder)
MY_BRAIN = os.path.join(BRAINS, "my_brain.py")
TEACHER = args.teacher
net_module.OPTIONS["compression"] = None  # (binary snapshots are small already; deflate would make them bigger)


def parse_stats(text):
    """The kart's design: --stats, else the one built last time on this computer, else the default."""
    d = sim.default_design(args.name or "Driver")
    saved = engine_hud.SETTINGS.get("kart_design") if hasattr(engine_hud, "SETTINGS") else None
    if isinstance(saved, dict) and not text:
        d.update({k: saved[k] for k in sim.STATS if k in saved})
    if text:
        try:
            sp, ac, gr = (int(v) for v in text.split(","))
            d.update(speed=sp, acceleration=ac, grip=gr)
        except ValueError:
            print("--stats wants three numbers, e.g. 40,30,30", flush=True)
    return sim.fit_design(d)


STAT_WORDS = {"speed": ("Top speed", "how fast it goes flat out on a straight"),
              "acceleration": ("Acceleration", "how quickly it gets there, and how hard it brakes"),
              "grip": ("Grip", "how sharply it turns and how fast a slide stops")}


class KartWindow(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()
        self.pipeline = kart_gfx.init(self, TIER)
        self.tier = TIER
        self.track_name = args.track
        self.track = kart_track.load(args.track)
        try:
            self.snd = kart_sound.KartSounds(self, on=not args.mute and not args.offscreen)
        except Exception as e:  # (no sound card, or the sound kit unhappy: the game is quiet)
            print(f"No sound: {e!r}", flush=True)
            self.snd = kart_sound.KartSounds.__new__(kart_sound.KartSounds)
            self.snd.on = False
        self.cd_last, self.was_boosting, self.was_finished = None, False, False
        self.lap_seen, self.lap_started, self.best_lap = None, None, None  # lap timing (see laps)
        self.track_vis = kart_gfx.TrackVisual(self.render, self.track)
        self.cam_rig = kart_gfx.ChaseCamera(self)
        self.hud = kart_gfx.Hud(self, self.track)
        self.karts = {}          # id -> KartVisual
        self.designs = {}        # id -> design
        self.colours = {}        # id -> (r, g, b)
        self.my_id = None
        self.my_design = parse_stats(args.stats)
        self.race = {"phase": sim.FLAGS_GRID, "go_local": None, "places": [], "laps": self.track.laps,
                     "events": [], "results": None, "brains": {}}
        self.last = self.start = time.perf_counter()
        self.accum = 0.0
        self.note, self.note_until = "", 0.0
        self.keys_down = {"drift": False, "respawn": False}
        self.accept("v", self.cam_rig.cycle)
        self.accept("shift", self.key, ["drift", True])
        self.accept("shift-up", self.key, ["drift", False])
        self.accept("space", self.key, ["drift", True])
        self.accept("space-up", self.key, ["drift", False])
        self.accept("r", self.key, ["respawn", True])
        self.accept("escape", self.userExit)
        self.accept("tab", self.toggle_panel)
        self.panel = None
        self.draft = None  # the design being edited in the panel
        # network and prediction (online), or the race itself (offline)
        self.net = None
        self.local = None
        self.predictor = None
        self.smoother = predict.ErrorSmoother(remove_up=True)
        self.lead = predict.LeadController()
        self.snaps = interp.Snapshots(SNAP_SPEC)
        self.snap_seq = 0
        self.next_seq = 1  # one numbering for every input we send, whether or not a predictor is running
        self.sent_at = {}
        self.ctrl_ms = None
        self.ping_ms = 0.0
        self.last_ping = self.perf_at = 0.0
        self.autopilot = False
        self.gfx_monitor = None
        if args.offline:
            self.start_offline()
        else:
            problem = self.connect()
            if problem:
                print(problem, flush=True)
                self.show_note(problem, 999)
        if gfx_tiers is not None and hasattr(gfx_tiers, "Monitor"):  # (turns the graphics down if frames are missed)
            try:
                sun = kart_gfx._state.get("sun") if hasattr(kart_gfx, "_state") else None
                self.gfx_monitor = gfx_tiers.Monitor(
                    engine_hud.SETTINGS_DIR, kart_gfx.tier() if hasattr(kart_gfx, "tier") else self.tier,
                    override=None if args.gfx == "auto" else args.gfx, pipeline=self.pipeline,
                    lights=[sun] if sun is not None else [], render=self.render, on_note=self.show_note,
                    # a window with the server on this same computer (a laptop test) shares the GPU with it:
                    # its missed frames say nothing worth saving
                    judge=args.offline or not (args.host or kart_version.SERVER).startswith(
                        ("ws://127.0.0.1", "ws://localhost"))).start(self)
            except Exception as e:
                print(f"No graphics monitor: {e!r}", flush=True)
        self.taskMgr.add(self.update, "update")
        if args.panel:
            self.toggle_panel()

    def key(self, which, down):
        self.keys_down[which] = down

    # ---------- the panel (Tab): your kart's design sheet, and the teacher's race controls ----------
    def toggle_panel(self):
        if self.panel is not None:
            self.panel.destroy()
            self.panel = None
            return
        self.draft = dict(self.my_design)
        self.build_panel()

    def rebuild_panel(self):
        if self.panel is not None:
            self.panel.destroy()
            self.build_panel()

    def build_panel(self):
        teacher = TEACHER and self.net is not None
        f = DirectFrame(parent=self.aspect2d, frameColor=PANEL, frameSize=(-0.66, 0.66, -0.4 if teacher else 0.04, 0.5),
                        pos=(0, 0, 0.1))
        self.panel = f
        d = self.draft
        y = 0.43
        label(f, "YOUR KART  -  100 points between three stats (Tab closes)", -0.6, y, 0.032, YELLOW)
        y -= 0.07
        for stat in sim.STATS:
            name, what = STAT_WORDS[stat]
            label(f, f"{name}", -0.6, y, 0.03, WHITE)
            label(f, what, -0.6, y - 0.035, 0.021, GREY)
            button(f, "-", 0.02, y + 0.005, self.change_points, [stat, -5], 0.045)
            label(f, f"{d[stat]:>3}", 0.14, y, 0.034, YELLOW)
            button(f, "+", 0.26, y + 0.005, self.change_points, [stat, 5], 0.045)
            bar = DirectFrame(parent=f, frameColor=(0.3, 0.7, 1.0, 0.9), frameSize=(0, 0.26 * d[stat] / sim.STAT_MAX, 0, 0.025),
                              pos=(0.36, 0, y - 0.004))
            bar.setTransparency(True)
            y -= 0.085
        left = sim.POINTS_TOTAL - sum(d[k] for k in sim.STATS)
        label(f, f"Points left: {left}" + ("" if left == 0 else "   (BUILD spreads them out)"), -0.6, y, 0.026,
              WHITE if left == 0 else YELLOW)
        button(f, "BUILD MY KART", 0.42, y + 0.005, self.build_kart, None, 0.032, ON)
        if teacher:
            y -= 0.1
            label(f, "TEACHER", -0.6, y, 0.032, YELLOW)
            button(f, "START RACE", -0.32, y + 0.005, lambda: self.net.send({"type": "start"}), None, 0.03, ON)
            button(f, "TO THE GRID", 0.0, y + 0.005, lambda: self.net.send({"type": "grid"}), None, 0.03)
            y -= 0.08
            label(f, "Track", -0.6, y, 0.028, WHITE)
            for i, name in enumerate(kart_track.TRACKS):
                button(f, kart_track.TRACKS[name]["name"], -0.38 + i * 0.3, y + 0.005, self.set_lesson,
                       [{"track": name}], 0.026, ON if name == self.track_name else OFF)
            y -= 0.07
            les = getattr(self, "lesson", {})
            label(f, f"Computer karts: {les.get('cpu_karts', '?')}", -0.6, y, 0.028, WHITE)
            button(f, "-", -0.12, y + 0.005, self.set_lesson, [{"cpu_karts": int(les.get("cpu_karts", 3)) - 1}], 0.03)
            button(f, "+", -0.02, y + 0.005, self.set_lesson, [{"cpu_karts": int(les.get("cpu_karts", 3)) + 1}], 0.03)
            label(f, f"Laps: {les.get('laps', '?')}", 0.12, y, 0.028, WHITE)
            button(f, "-", 0.36, y + 0.005, self.set_lesson, [{"laps": int(les.get("laps", 3)) - 1}], 0.03)
            button(f, "+", 0.46, y + 0.005, self.set_lesson, [{"laps": int(les.get("laps", 3)) + 1}], 0.03)
            y -= 0.07
            label(f, "Their level", -0.6, y, 0.028, WHITE)
            for i, level in enumerate(cpu_brains.LEVELS):
                button(f, level, -0.3 + i * 0.26, y + 0.005, self.set_lesson, [{"cpu_level": level}], 0.026,
                       ON if les.get("cpu_level") == level else OFF)

    def change_points(self, stat, delta):
        d = self.draft
        new = max(sim.STAT_MIN, min(sim.STAT_MAX, d[stat] + delta))
        if new > d[stat] and sum(d[k] for k in sim.STATS) - d[stat] + new > sim.POINTS_TOTAL:
            self.show_note("No points left: take some from another stat first", 3)
            return
        d[stat] = new
        self.rebuild_panel()

    def build_kart(self):
        self.my_design = sim.fit_design(dict(self.draft, name=self.my_design.get("name", "Kart")))
        self.draft = dict(self.my_design)
        try:
            engine_hud.remember("kart_design", {k: self.my_design[k] for k in sim.STATS})
        except Exception:
            pass
        if self.net is not None:
            self.net.send({"type": "design", "design": self.my_design})
            self.predictor = None  # (the stats changed: predict afresh from the server's next snapshot)
        elif self.local is not None:
            self.local.designs[0] = self.my_design
            self.local.stats[0] = sim.stats_of(self.my_design)
            self.sync_designs(self.local.designs)
        self.show_note("Kart built: " + "  ".join(f"{STAT_WORDS[k][0]} {self.my_design[k]}" for k in sim.STATS), 4)
        self.rebuild_panel()

    def set_lesson(self, change):
        self.net.send({"type": "lesson", "lesson": change})
        self.taskMgr.doMethodLater(0.4, lambda task: self.rebuild_panel(), "panel refresh")

    def show_note(self, text, seconds=4):
        self.note, self.note_until = text, time.perf_counter() + seconds

    # ---------- offline: the race on this laptop ----------
    def start_offline(self):
        self.my_id = 0
        self.local = sim.Race(self.track, SCHEMA, args.laps)
        self.local.add(0, self.my_design)
        self.local_cpu = {}
        for n in range(max(0, min(7, args.cpu))):
            kid = n + 1
            self.local.add(kid, sim.default_design(cpu_brains.name_for(args.level, n), COLOURS[kid % len(COLOURS)]))
            self.local_cpu[kid] = args.level
        self.local_brain = None
        if args.brain:
            import kart_brain
            with open(args.brain, encoding="utf-8") as f:
                fn, fname = kart_brain.load_brain(f.read(), "me")
            self.local_brain = kart_brain.Autopilot(fn, fname)
        self.accept("enter", self.local_start)
        self.accept("g", self.local.to_grid)
        self.sync_designs(self.local.designs)
        self.show_note("Press Enter to start the race" if not args.autostart else "", 8)
        if args.autostart:
            self.local_start()

    def local_start(self):
        self.local.start()

    # ---------- online ----------
    def connect(self):
        host = args.host or kart_version.SERVER
        code = args.code or ("TEACH99" if TEACHER else "CLUB42")
        name = args.name or ("Teacher" if TEACHER else os.environ.get("USERNAME", "Driver"))
        try:
            self.net = Net(host, name, code, version=kart_version.VERSION,
                           **({"ticket": args.ticket} if args.ticket else {}))
        except Exception as e:
            self.net = None
            return f"Can't reach the Kart Lab server ({host}): {e}"
        deadline = time.time() + 8
        while True:
            try:
                m = self.net.inbox.get(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                return "No answer from the server."
            if m["type"] == "welcome":
                break
            if m["type"] == "closed":
                return m.get("reason") or "The server closed the connection."
        self.name = m["name"]
        self.my_id = m["kart"]
        self.lesson = m["lesson"]
        self.set_track(m["lesson"]["track"], m["lesson"]["laps"])
        self.net.send({"type": "design", "design": self.my_design})
        if TEACHER:
            self.accept("enter", lambda: self.net.send({"type": "start"}))
            self.accept("g", lambda: self.net.send({"type": "grid"}))
            self.accept("t", self.next_track)
            self.show_note("Teacher: Enter starts the race, G puts everyone on the grid, T changes the track", 10)
        self.accept("u", self.upload_brain)
        self.accept("p", self.toggle_autopilot)
        return None

    def set_track(self, name, laps):
        if name != getattr(self, "track_name", None):
            self.track_name = name
            self.track = kart_track.load(name)
            self.track_vis.destroy()
            self.track_vis = kart_gfx.TrackVisual(self.render, self.track)
            self.hud.destroy()
            self.hud = kart_gfx.Hud(self, self.track)
            self.predictor = None
            self.snaps = interp.Snapshots(SNAP_SPEC)
        self.race["laps"] = laps

    def next_track(self):
        names = list(kart_track.TRACKS)
        nxt = names[(names.index(self.track_name) + 1) % len(names)]
        self.net.send({"type": "lesson", "lesson": {"track": nxt}})

    def upload_brain(self):
        try:
            with open(MY_BRAIN, encoding="utf-8") as f:
                source = f.read()
        except OSError:
            self.show_note(f"No brain file: write {MY_BRAIN}")
            return
        self.net.send({"type": "brain", "source": source})
        self.show_note("Brain sent...")

    def toggle_autopilot(self):
        mine = self.race["brains"].get(getattr(self, "name", ""), {})
        if not mine.get("has"):
            self.show_note("Upload a brain first (U)")
            return
        self.net.send({"type": "autopilot", "on": not mine.get("on")})

    def read_network(self):
        while True:
            try:
                m = self.net.inbox.get_nowait()
            except queue.Empty:
                return
            kind = m["type"]
            if kind == "binary":
                if wire.kind_of(m["data"]) == wire.KIND_SNAPSHOT:
                    self.on_snapshot(wire.unpack_snapshot(SCHEMA, m["data"]), m.get(interp.RECEIVED))
            elif kind == "race":
                self.on_race(m)
            elif kind == "roster":
                self.sync_designs({k["id"]: {"name": k["name"], "colour": k["colour"]} for k in m["karts"]})
                self.race["laps"] = m["laps"]
            elif kind == "lesson":
                self.lesson = m["lesson"]
                self.set_track(m["lesson"]["track"], m["lesson"]["laps"])
                self.rebuild_panel()
            elif kind == "pong":
                self.ping_ms = (time.time() - m["t"]) * 1000
            elif kind == "brain_result":
                self.show_note("Brain running: P switches it off" if m["ok"] else f"Brain: {m['error']}", 6)
            elif kind == "design_result":
                self.my_design = m["design"]
            elif kind == "notice":
                self.show_note(m["text"], 5)
            elif kind == "closed":
                self.show_note("Connection lost: " + (m.get("reason") or ""), 999)

    def on_race(self, m):
        r = self.race
        r.update(phase=m["phase"], places=m["places"], laps=m["laps"], events=m["events"], results=m["results"],
                 brains=m.get("brains", {}))
        if m["go_in_ms"] is None:
            r["go_local"] = None if m["phase"] != sim.FLAGS_RACE else r.get("go_local") or 0.0
        else:  # the server's GO moment in our own clock: its time stamp is in our clock through the snapshots
            now = time.perf_counter()
            server_now = self.snaps.clock.server_time(now)
            go_server = m["sm"] / 1000 + m["go_in_ms"] / 1000
            r["go_local"] = now + (go_server - server_now) if server_now is not None else now + m["go_in_ms"] / 1000
        mine = r["brains"].get(getattr(self, "name", ""), {})
        was, self.autopilot = self.autopilot, bool(mine.get("on"))
        if was != self.autopilot:
            self.predictor = None  # (the server drives: nothing to predict; back on the keys we start afresh)

    def frozen(self, now):
        r = self.race
        return r["phase"] != sim.FLAGS_RACE or (r["go_local"] is not None and now < r["go_local"])

    def on_snapshot(self, snap, rx):
        self.snap_seq = snap["seq"]
        self.snaps.push(snap, rx)
        self.race["phase"] = snap["flags"] & 3
        self.lead.feed(snap["flags"] >> 4)
        me = next((e for e in snap["entities"] if e["id"] == self.my_id), None)
        if me is None:
            return
        self.finished = finished = bool(me["flags"] & sim.FLAG_FINISHED)
        if args.no_predict or self.autopilot or finished:
            self.predictor = None
            return
        state = self.full_state(me)
        if self.predictor is None:  # (its numbering carries on from ours: the server ignores a number going back)
            self.predictor = predict.Predictor(self.step_fn(), state, ignore=0.05,
                                               log=predict.InputLog(first_seq=self.next_seq))
            self.smoother.clear()
            self.accum = 0.0  # (no burst of catch-up ticks from the time spent waiting for this)
            return
        if snap["ack"] == 0:
            return  # (the server hasn't applied any input of ours yet: nothing to compare with)
        err = self.predictor.correct(state, snap["ack"], sim.STEP, sim.compare)
        moved = self.predictor.moved_from
        if moved is not None and err != math.inf:
            new = self.predictor.state
            dyaw = math.radians((moved["yaw"] - new["yaw"] + 180) % 360 - 180)
            self.smoother.add((moved["x"] - new["x"], moved["y"] - new["y"], 0.0), dyaw)
            if err > 0.3 and not self.frozen(time.perf_counter()):  # (a bump the server knew of: we hear it)
                self.snd.bump(min(1.0, 0.4 + err * 0.3))
        sent = self.sent_at.get(snap["ack"])
        if sent is not None:
            ms = (rx - sent) * 1000 if rx else None
            if ms is not None:
                self.ctrl_ms = ms if self.ctrl_ms is None else self.ctrl_ms * 0.8 + ms * 0.2

    def full_state(self, e):
        """A snapshot's kart record as the state kart_sim.step wants (with where it is along the track)."""
        seg, s, lat = self.track.locate(e["x"], e["y"], None)
        return dict(e, seg=seg, s=s, lat=lat)

    def step_fn(self):
        track, st = self.track, sim.stats_of(self.my_design)

        def step(state, inp, dt):
            n = sim.step(state, inp, dt, track, st)
            n.update(SCHEMA.quantise(n))  # (as the server does: the same numbers next tick)
            return n
        return step

    def read_keys(self):
        if self.mouseWatcherNode is None:
            return (0.0, 0.0, 0)
        down = self.mouseWatcherNode.is_button_down
        k = KeyboardButton
        th = (down(k.up()) or down(k.asciiKey("w"))) - (down(k.down()) or down(k.asciiKey("s")))
        steer = (down(k.left()) or down(k.asciiKey("a"))) - (down(k.right()) or down(k.asciiKey("d")))
        bt = (sim.DRIFT if self.keys_down["drift"] else 0) | (sim.RESPAWN if self.keys_down["respawn"] else 0)
        self.keys_down["respawn"] = False
        return wire.quantise_input(float(th), float(steer), bt)

    def client_tick(self, now):
        """One predicted tick of our own kart, and its input to the server."""
        if self.predictor is None and not (args.no_predict or self.autopilot or getattr(self, "finished", False)):
            return  # (nothing to predict from until the first snapshot: inputs sent now would only be unlogged)
        inp = self.read_keys()
        if self.frozen(now):
            inp = (0.0, 0.0, 0)
        if self.predictor is not None:
            seq = self.predictor.apply(inp, sim.STEP, now)
            prev = self.predictor.log.previous(2)
            self.next_seq = self.predictor.log.next_seq
        else:
            seq, prev = self.next_seq, ()
            self.next_seq = (seq + 1) & 0xFFFF
        self.sent_at[seq] = now
        if len(self.sent_at) > 128:
            for s in sorted(self.sent_at)[:64]:
                del self.sent_at[s]
        self.net.send(wire.pack_input(seq, self.snap_seq, int(now * 1000) & 0xFFFFFFFF, inp[0], inp[1], inp[2],
                                      previous=prev))

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
        states = {}
        if self.local is not None:
            self.accum = min(0.25, self.accum + dt)
            while self.accum >= sim.STEP:
                self.accum -= sim.STEP
                inputs = {}
                if self.local_brain is not None and not self.local.frozen():
                    inputs[0] = self.local_brain(self.local.karts[0], self.local)
                else:
                    inputs[0] = self.read_keys()
                for kid, level in self.local_cpu.items():
                    inputs[kid] = cpu_brains.drive(level, self.local.karts[kid], self.local)
                self.local.step_all(inputs)
            r = self.local
            cd = r.countdown()
            self.race.update(phase=r.phase, places=r.places(), laps=r.laps,
                             results=r.results() if r.phase == sim.FLAGS_OVER else None,
                             go_local=None if cd is None else now + cd)
            states = r.karts
        elif self.net is not None:
            self.read_network()
            # (a hitch of more than four ticks is skipped, not caught up: a burst of inputs would only queue at the
            # server and make every key press late until the lead controller drained it)
            # (the lead multiplier stretches the time between our ticks: over 1 when the server has too many of our
            # inputs waiting, under 1 when it is running dry, so a key press is applied within a tick or two)
            self.accum = min(4 * sim.STEP, self.accum + dt / self.lead.multiplier())
            while self.accum >= sim.STEP:
                self.accum -= sim.STEP
                self.client_tick(now)
            if now - self.last_ping > 1:
                self.last_ping = now
                self.net.send({"type": "ping", "t": time.time()})
            self.send_perf(now)
            blended = self.snaps.latest if args.no_interp else self.snaps.sample(now)
            if blended:
                states = {e["id"]: e for e in blended["entities"]}
            if self.predictor is not None and self.my_id in states:
                mine = dict(self.predictor.state)
                (ox, oy, _), oyaw = self.smoother.offset(dt)
                mine["x"], mine["y"], mine["yaw"] = mine["x"] + ox, mine["y"] + oy, mine["yaw"] + math.degrees(oyaw)
                states[self.my_id] = mine
        self.draw(states, dt, now)
        return task.cont

    def sync_designs(self, designs):
        for kid, d in designs.items():
            if kid not in self.karts or self.designs.get(kid) != d:
                if kid in self.karts:
                    self.karts[kid].destroy()
                self.karts[kid] = kart_gfx.KartVisual(self.render, d)
                self.karts[kid].set_label(d["name"], tuple(c / 255 for c in d["colour"]) + (1.0,))
                self.designs[kid] = dict(d)
                self.colours[kid] = tuple(c / 255 for c in d["colour"])
        for kid in list(self.karts):
            if kid not in designs:
                self.karts.pop(kid).destroy()
                self.designs.pop(kid, None)

    def draw(self, states, dt, now):
        me = states.get(self.my_id)
        self.track_vis.update(now - self.start)  # (the dash pads pulse)
        for kid, k in states.items():
            vis = self.karts.get(kid)
            if vis is None:
                continue
            seg, s, lat = self.track.locate(k["x"], k["y"], k.get("seg"))
            z = self.track.height(s)
            flags = k.get("flags", 0)
            vis.update(k["x"], k["y"], z, k["yaw"], 0.0, k["v"], k["u"],
                       bool(flags & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R)), bool(flags & sim.FLAG_BOOSTING), dt)
        if me is not None:
            seg, s, lat = self.track.locate(me["x"], me["y"], me.get("seg"))
            self.cam_rig.update(dt, me["x"], me["y"], self.track.height(s), me["yaw"], me["v"], self.track)
        r = self.race
        places = r["places"] or sorted(states)
        place = places.index(self.my_id) + 1 if self.my_id in places else 0
        cd = None if r["go_local"] is None else max(0.0, r["go_local"] - now)
        if cd is not None and cd <= 0 and now - r["go_local"] > 1.5:
            cd = None
        self.sounds(me, cd if r["phase"] == sim.FLAGS_RACE else None, place, now)
        self.laps(me, now)
        minimap = [(k["x"], k["y"], self.colours.get(kid, (1, 1, 1)), kid == self.my_id) for kid, k in states.items()]
        self.hud.update(min(r["laps"], (me["lap"] if me else 0) + 1), r["laps"], place, len(states),
                        abs(me["v"]) * 3.6 if me else 0.0, cd if r["phase"] == sim.FLAGS_RACE else None,
                        bool(me and me.get("flags", 0) & sim.FLAG_WRONG_WAY), me["charge"] if me else 0,
                        minimap, r["results"])
        text = f"{self.clock.getAverageFrameRate():.0f} fps   gfx {self.tier}"
        if self.net is not None:
            rep = self.snaps.report()
            text += f"   ping {self.ping_ms:.0f} ms" + (f"   keys {self.ctrl_ms:.0f} ms" if self.ctrl_ms else "")
            text += f"   blend {rep['delay_ms']} ms" + (f"   stalls {rep['stalls']}" if rep["stalls"] else "")
            if self.predictor is not None:
                text += f"   corrections {self.predictor.corrections}"
            if self.autopilot:
                text += "   AUTOPILOT (P)"
        if now < self.note_until:
            text = self.note + "     " + text
        elif r["phase"] == sim.FLAGS_GRID and self.local is None:
            text = "Waiting for the teacher to start the race     " + text
        self.hud.status(text)

    def laps(self, me, now):
        """Your lap times: told as you cross the line; offline, the best on each track is kept on this computer."""
        r = self.race
        if me is None or r["phase"] != sim.FLAGS_RACE or r["go_local"] is None:
            self.lap_seen, self.lap_started = None, None
            return
        lap = me.get("lap", 0)
        if self.lap_seen is None:  # the race is on: the clock starts at GO
            self.lap_seen, self.lap_started = lap, r["go_local"]
            key = f"kart_best_{self.track_name}"
            saved = engine_hud.SETTINGS.get(key) if hasattr(engine_hud, "SETTINGS") else None
            self.best_lap = float(saved) if isinstance(saved, (int, float)) else None
            return
        if lap > self.lap_seen and now > self.lap_started + 5:
            took = now - self.lap_started
            self.lap_seen, self.lap_started = lap, now
            best = self.best_lap is None or took < self.best_lap
            if best:
                self.best_lap = took
                if self.local is not None:  # (offline practice: the record stays; online the teacher's league will)
                    try:
                        engine_hud.remember(f"kart_best_{self.track_name}", round(took, 2))
                    except Exception:
                        pass
            self.show_note(f"Lap {lap}: {took:.1f} s" + ("   NEW BEST" if best else f"   (best {self.best_lap:.1f} s)"), 4)

    def sounds(self, me, cd, place, now):
        """What you hear: your engine, your tyres, the countdown, a boost starting, the finish."""
        racing = self.race["phase"] == sim.FLAGS_RACE and not self.frozen(now)
        if me is not None:
            flags = me.get("flags", 0)
            top = sim.stats_of(self.my_design)["top"]
            boosting = bool(flags & sim.FLAG_BOOSTING)
            self.snd.update(now, me.get("v", 0.0), top, bool(flags & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R)), boosting,
                            racing)
            if boosting and not self.was_boosting:
                self.snd.boost()
            self.was_boosting = boosting
            finished = bool(flags & sim.FLAG_FINISHED)
            if finished and not self.was_finished:
                self.snd.finish(now, first=place == 1)
            self.was_finished = finished
        n = None if cd is None else int(math.ceil(cd - 1e-6))
        if n != self.cd_last and n is not None and 0 <= n <= 3:
            self.snd.countdown(n)
        self.cd_last = n

    def send_perf(self, now):
        if now - self.perf_at < 3:
            return
        self.perf_at = now
        rep = self.snaps.report()
        perf = {"type": "perf", "fps": round(self.clock.getAverageFrameRate()), "ping": round(self.ping_ms),
                "tier": self.tier, "stalls": rep["stalls"], "delay": rep["delay_ms"],
                "ctrl": None if self.ctrl_ms is None else round(self.ctrl_ms),
                "corr": self.predictor.corrections if self.predictor else None}
        self.net.send(perf)
        if args.offscreen:  # (tests read it from the console)
            print("perf", json.dumps(perf), f"lead {self.lead.multiplier():.2f}", flush=True)


if __name__ == "__main__":
    KartWindow().run()
