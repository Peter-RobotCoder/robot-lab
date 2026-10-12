"""The Kart Lab class server: the race everyone's window is a view of.

    python kart_server.py                       a laptop test server (codes CLUB42 and TEACH99)
    python kart_server.py --class-server        the real one (JOIN_CODE and TEACHER_CODE set, behind Caddy)

What it does 60 times a second: takes each window's latest numbered input (engine.predict.ServerInputQueue), asks
the computer drivers and the learners' brains (kart_brain, in their own processes, asked asynchronously), steps
the race (kart_sim.Race: a hand-written kart every window can step identically), and 30 times a second sends each
window a binary snapshot of every kart (engine.wire) stamped with the server's time and that window's last input
applied, so the window can check its own prediction against it. Everything else (who is here, the race's phase,
the countdown, results, designs, brains) is JSON, as in the other games.

The window's keys reach its kart with no wait: the window predicts its own kart and the server only corrects it.
Bumps between karts and the race itself happen here only; nothing a window does can move another kart.
"""
import argparse
import asyncio
import hmac
import json
import os
import re
import sys
import time

import websockets

import kart_version
sys.path.insert(0, kart_version.ENGINE_HOME)
from engine import club_ticket, predict, wire  # noqa: E402

import cpu_brains  # noqa: E402
import kart_brain  # noqa: E402
import kart_sim as sim  # noqa: E402
import kart_track  # noqa: E402

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
GAME_ID = "kartlab"  # (the club desk's name for this game)
TICKET_KEY = os.environ.get("CLUBCODERS_TICKET_KEY")
LIVE_FILE = os.environ.get("CLUBCODERS_LIVE_FILE", "")   # the club desk: which group is launched, in which game
DATA = os.environ.get("KARTLAB_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CLASS_SERVER = False
MAX_LEARNERS = 4
MAX_KARTS = 8
SEND_RATE = 1 / 30
RACE_RATE = 0.5          # the JSON race message (phase, places, countdown, events)
BRAIN_EVERY = 3          # brains are asked every third tick (20 a second): plenty for driving, kind to the server
T0 = time.perf_counter()
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230), (240, 120, 40),
           (60, 200, 200), (230, 90, 160)]
SCHEMA = wire.Schema("kart", sim.SCHEMA_FIELDS)
IDLE = (0.0, 0.0, 0)

DEFAULT_LESSON = {"track": "club", "laps": 3, "cpu_karts": 3, "cpu_level": "medium", "brains": True}


def server_ms():
    return int((time.perf_counter() - T0) * 1000) & 0xFFFFFFFF


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = sim.default_design(name, colour)
        self.kart = None                                  # its kart's id
        self.inputs = predict.ServerInputQueue(idle=IDLE)  # numbered inputs from the window
        self.brain = None                                 # kart_brain.Autopilot, when uploaded
        self.autopilot = False
        self.last_brain = IDLE
        self.perf = None
        self.ctrl_seq = None


class KartServer:
    def __init__(self, lesson=None):
        self.lesson = dict(DEFAULT_LESSON, **(lesson or {}))
        self.players = {}       # ws -> Player
        self.cpu = {}           # kart id -> level
        self.track = kart_track.load(self.lesson["track"])
        self.race = sim.Race(self.track, SCHEMA, self.lesson["laps"])
        self.roster_version = 0
        self.snap_seq = 0
        self.race_version = None
        self.rebuild()

    # ---------- who is racing ----------
    def learners(self):
        return [p for p in self.players.values() if p.role == "learner"]

    def teacher(self):
        return next((p for p in self.players.values() if p.role == "teacher"), None)

    def rebuild(self):
        """The karts from the players and the lesson's computer karts, back on the grid."""
        race = sim.Race(self.track, SCHEMA, self.lesson["laps"])
        for p in self.players.values():
            if p.kart is None:
                used = {q.kart for q in self.players.values() if q.kart is not None}
                p.kart = next(i for i in range(MAX_KARTS) if i not in used)
            race.add(p.kart, p.design)
        self.cpu = {}
        used = {p.kart for p in self.players.values()}
        n = 0
        for i in range(MAX_KARTS):
            if n >= int(self.lesson["cpu_karts"]):
                break
            if i in used:
                continue
            level = self.lesson["cpu_level"]
            race.add(i, sim.default_design(cpu_brains.name_for(level, n), COLOURS[i % len(COLOURS)]))
            self.cpu[i] = level
            n += 1
        if self.race.phase == sim.FLAGS_RACE and not self.race.frozen():  # (a kart joining mid-race)
            race.tick, race.phase, race.go_tick = self.race.tick, self.race.phase, self.race.go_tick
            for kid, k in self.race.karts.items():
                if kid in race.karts:
                    race.karts[kid] = k
            race.finish = dict(self.race.finish)
        self.race = race
        self.roster_version += 1

    def roster(self):
        return {"type": "roster", "version": self.roster_version, "track": self.lesson["track"],
                "laps": self.race.laps,
                "karts": [{"id": kid, "name": d["name"], "colour": d["colour"], "cpu": self.cpu.get(kid),
                           "owner": next((p.name for p in self.players.values() if p.kart == kid), None)}
                          for kid, d in self.race.designs.items()],
                "mine": {p.name: p.kart for p in self.players.values()},
                "perf": {p.name: p.perf for p in self.players.values() if p.perf}}

    def race_msg(self):
        r = self.race
        cd = r.countdown()
        return {"type": "race", "phase": r.phase, "tick": r.tick, "sm": server_ms(),
                "go_in_ms": None if cd is None else int(cd * 1000),
                "places": r.places(), "laps": r.laps,
                "events": [e for t, e in r.events if r.tick - t < 240][-4:],
                "results": r.results() if r.phase == sim.FLAGS_OVER else None,
                "brains": {p.name: {"on": p.autopilot, "error": p.brain.error if p.brain else None,
                                    "has": p.brain is not None} for p in self.players.values()}}

    # ---------- connections ----------
    async def handler(self, ws):
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if not isinstance(hello, dict):
                return
        except Exception:
            return
        if CLASS_SERVER and hello.get("version") != kart_version.VERSION:
            await ws.close(4006, f"Out of date: download Club Coders {kart_version.VERSION} from "
                                 f"{kart_version.DOWNLOAD_PAGE}"[:120])
            return
        ticket = None
        if hello.get("ticket") and TICKET_KEY:  # from the club desk, which has checked who this is
            with open(TICKET_KEY, encoding="utf-8") as f:
                ticket = club_ticket.verify(f.read().strip(), hello["ticket"], GAME_ID)
            if ticket is None:
                await ws.close(4011, "Your login has run out: open Club Coders and log in again.")
                return
            role = ticket["role"]
            if role == "learner":  # only the group the teacher has launched, and only into this game
                live = read_live()
                if not live or live.get("game") != GAME_ID or ticket["name"] not in live.get("learners", []):
                    await ws.close(4010, "Your group hasn't started yet: wait for your teacher.")
                    return
        else:
            role = code_role(str(hello.get("code", "")))
            if role == "learner" and TICKET_KEY:
                await ws.close(4010, "Log in through the Club Coders app: your teacher launches your group there.")
                return
        if role is None:
            await ws.close(4001, "wrong class code")
            return
        if role == "teacher" and self.teacher():
            await ws.close(4002, "a teacher is already connected")
            return
        name = re.sub(r"[^A-Za-z0-9 ]", "", str(ticket["name"] if ticket else hello.get("name", "")))[:12] \
            or ("Teacher" if role == "teacher" else "Driver")
        old = next((q for q in self.players.values() if q.name.lower() == name.lower()), None)
        if old is not None:  # logged in again (after a dropped connection): the old connection goes
            await old.ws.close(4005, "you logged in again somewhere else")
            self.players.pop(old.ws, None)
        if role == "learner" and len(self.learners()) >= MAX_LEARNERS:
            await ws.close(4003, f"the class is full ({MAX_LEARNERS} learners)")
            return
        colour = COLOURS[len(self.players) % len(COLOURS)]
        p = Player(ws, role, name, colour)
        if old is not None:
            p.kart, p.design, p.brain, p.autopilot = old.kart, old.design, old.brain, old.autopilot
        self.players[ws] = p
        print(f"+ {name} ({role})", flush=True)
        self.rebuild()
        self.race.events.append((self.race.tick, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "kart": p.kart, "lesson": self.lesson,
                             "design": p.design, "track": kart_track.TRACKS[self.lesson["track"]],
                             "code": kart_version.CODE, "rules": {"stats": sim.STATS, "points_total": sim.POINTS_TOTAL,
                                                                  "stat_min": sim.STAT_MIN, "stat_max": sim.STAT_MAX}})
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    self.on_binary(p, raw)
                else:
                    await self.on_message(p, json.loads(raw))
        except (websockets.ConnectionClosed, json.JSONDecodeError, ValueError):
            pass
        finally:
            if self.players.get(ws) is p:
                del self.players[ws]
                if p.brain:
                    p.brain.close()
                print(f"- {name} left", flush=True)
                self.rebuild()

    def on_binary(self, p, raw):
        if wire.kind_of(raw) == wire.KIND_INPUT:
            m = wire.unpack_input(raw)
            inp = (m["throttle"], m["steer"], m["buttons"])
            p.inputs.push(m["seq"], inp, [tuple(x) for x in m["prev"]])

    async def on_message(self, p, m):
        kind = m.get("type")
        if kind == "ping":
            await self.send(p.ws, {"type": "pong", "t": m.get("t"), "sm": server_ms()})
        elif kind == "perf":
            p.perf = {k: m.get(k) for k in ("fps", "ping", "tier", "stalls", "delay", "ctrl", "corr") if k in m}
        elif kind == "control":  # a JSON control (tests, a brainless window): the same as a binary input
            try:
                p.inputs.push(int(m.get("seq", 0)), (float(m.get("throttle", 0)), float(m.get("steer", 0)),
                                                     int(m.get("buttons", 0))))
            except (TypeError, ValueError):
                pass
        elif kind == "design":
            p.design = sim.fit_design(dict(m.get("design") or {}, name=p.name))
            if p.kart in self.race.designs:
                self.race.designs[p.kart] = p.design
                self.race.stats[p.kart] = sim.stats_of(p.design)
            self.roster_version += 1
            await self.send(p.ws, {"type": "design_result", "ok": True, "design": p.design})
        elif kind == "brain" and p.role == "learner" or kind == "brain" and p.role == "teacher":
            if not self.lesson.get("brains", True):
                await self.send(p.ws, {"type": "notice", "text": "Brains aren't switched on for this race yet."})
                return
            await self.upload_brain(p, str(m.get("source", "")))
        elif kind == "autopilot":
            p.autopilot = bool(m.get("on")) and p.brain is not None
            if p.autopilot and p.brain is not None:
                p.brain.error = None
            self.race_version = None  # (tell everyone)
        elif kind == "start" and p.role == "teacher":
            self.race.start()
            self.race_version = None
        elif kind == "grid" and p.role == "teacher":
            self.rebuild()
            self.race.to_grid()
            self.race_version = None
        elif kind == "lesson" and p.role == "teacher":
            new = {k: v for k, v in (m.get("lesson") or {}).items() if k in DEFAULT_LESSON}
            if new.get("track") not in (None, *kart_track.TRACKS):
                new.pop("track")
            if new.get("cpu_level") not in (None, *cpu_brains.LEVELS):
                new.pop("cpu_level")
            self.lesson.update(new)
            self.lesson["cpu_karts"] = max(0, min(MAX_KARTS - 1, int(self.lesson["cpu_karts"])))
            self.lesson["laps"] = max(1, min(9, int(self.lesson["laps"])))
            self.track = kart_track.load(self.lesson["track"])
            self.rebuild()
            self.race_version = None
            for ws in list(self.players):
                await self.send(ws, {"type": "lesson", "lesson": self.lesson,
                                     "track": kart_track.TRACKS[self.lesson["track"]]})

    async def upload_brain(self, p, source):
        try:
            fn, fname = await asyncio.to_thread(kart_brain.load_brain, source, p.name)
        except kart_brain.BrainError as e:
            await self.send(p.ws, {"type": "brain_result", "ok": False, "error": str(e)})
            return
        if p.brain:
            p.brain.close()
        p.brain = kart_brain.Autopilot(fn, fname)
        p.autopilot = True
        self.race_version = None
        await self.send(p.ws, {"type": "brain_result", "ok": True})

    async def send(self, ws, msg):
        try:
            await ws.send(json.dumps(msg, separators=(",", ":")) if isinstance(msg, dict) else msg)
        except websockets.ConnectionClosed:
            pass

    # ---------- the loops ----------
    async def physics_loop(self):
        next_step = time.perf_counter()
        while True:
            next_step += sim.STEP
            now = time.perf_counter()
            if next_step < now - 4 * sim.STEP:  # (a long stall: don't try to catch up)
                next_step = now
            await asyncio.sleep(max(0.0, next_step - now))
            self.step()

    def step(self):
        race = self.race
        inputs = {}
        ask_brains = race.tick % BRAIN_EVERY == 0
        for p in self.players.values():
            if p.kart is None:
                continue
            keys = p.inputs.pop_for_tick()
            p.ctrl_seq = p.inputs.applied
            if p.autopilot and p.brain is not None and not race.frozen():
                if ask_brains:
                    p.last_brain = p.brain(race.karts[p.kart], race)
                inputs[p.kart] = (p.last_brain[0], p.last_brain[1], p.last_brain[2] | (keys[2] & sim.RESPAWN))
            else:
                inputs[p.kart] = keys
        for kid, level in self.cpu.items():
            if kid in race.karts:
                inputs[kid] = cpu_brains.drive(level, race.karts[kid], race)
        race.step_all(inputs)

    async def send_loop(self):
        sent_version, last_race, next_send = {}, 0.0, time.perf_counter()
        while True:
            next_send += SEND_RATE
            now = time.perf_counter()
            if next_send < now - 4 * SEND_RATE:
                next_send = now
            await asyncio.sleep(max(0.0, next_send - now))
            if not self.players:
                continue
            self.snap_seq = (self.snap_seq + 1) & 0xFFFF
            sm = server_ms()
            entities = list(self.race.karts.values())
            race_msg = None
            version = (self.race.phase, self.race.go_tick, len(self.race.finish), len(self.race.events))
            if version != self.race_version or now - last_race > RACE_RATE:
                self.race_version, last_race = version, now
                race_msg = json.dumps(self.race_msg(), separators=(",", ":"))
                perf_version = tuple(sorted((p.name, json.dumps(p.perf, sort_keys=True)) for p in self.players.values()
                                            if p.perf))
                if perf_version != getattr(self, "perf_version", None):
                    self.perf_version = perf_version
                    self.roster_version += 1
            roster = None
            for ws, p in list(self.players.items()):
                if backed_up(ws):
                    continue
                if sent_version.get(ws) != self.roster_version:
                    roster = roster or json.dumps(self.roster(), separators=(",", ":"))
                    await self.send(ws, roster)
                    sent_version[ws] = self.roster_version
                if race_msg:
                    await self.send(ws, race_msg)
                # that window's own frame: its last input applied, and how many of its inputs wait (for its lead)
                flags = self.race.phase | (min(15, p.inputs.depth()) << 4)
                frame = wire.pack_snapshot(SCHEMA, sm, self.snap_seq, entities, ack=p.ctrl_seq or 0, flags=flags)
                await self.send(ws, frame)
            await asyncio.sleep(0)


def read_live():
    """The launched group, from the club desk: {"id", "group", "game", "lesson", "learners"} or None."""
    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            live = json.load(f)
        return live if isinstance(live, dict) and live.get("id") else None
    except (OSError, ValueError, TypeError):
        return None


def backed_up(ws, limit=16 * 1024):
    transport = getattr(ws, "transport", None)
    try:
        return transport is not None and transport.get_write_buffer_size() > limit
    except Exception:
        return False


def code_role(code):
    for role, real in (("teacher", TEACHER_CODE), ("learner", LEARNER_CODE)):
        if hmac.compare_digest(code.encode("utf-8"), real.encode("utf-8")):
            return role
    return None


def fine_timer():
    """Windows wakes a sleeping loop only every 15.6 ms unless asked for a finer clock."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass


async def main():
    global CLASS_SERVER
    fine_timer()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8782)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--class-server", action="store_true", help="the real class server: real codes required")
    ap.add_argument("--track", default=None, choices=list(kart_track.TRACKS))
    ap.add_argument("--cpu", type=int, default=None, help="computer karts")
    ap.add_argument("--level", default=None, choices=list(cpu_brains.LEVELS))
    ap.add_argument("--laps", type=int, default=None)
    ap.add_argument("--autostart", type=float, default=None, help="seconds after the first window joins, start the race")
    args = ap.parse_args()
    CLASS_SERVER = args.class_server
    if CLASS_SERVER and (LEARNER_CODE in DEMO_CODES.values() or TEACHER_CODE in DEMO_CODES.values()
                         or len(TEACHER_CODE) < 16):
        raise SystemExit("Kart Lab server not started: JOIN_CODE and TEACHER_CODE must be set (not the demo codes).")
    lesson = {k: v for k, v in (("track", args.track), ("cpu_karts", args.cpu), ("cpu_level", args.level),
                                ("laps", args.laps)) if v is not None}
    server = KartServer(lesson)
    if CLASS_SERVER:  # (the club desk tells the Club Coders app which code this class runs)
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(kart_version.CODE)

    async def autostart():
        while not server.players:
            await asyncio.sleep(0.2)
        await asyncio.sleep(args.autostart)
        server.race.start()
        server.race_version = None

    tasks = [server.physics_loop(), server.send_loop()] + ([autostart()] if args.autostart is not None else [])
    async with websockets.serve(server.handler, args.bind, args.port, compression=None, ping_interval=5,
                                ping_timeout=10, max_queue=8):
        print(f"Kart Lab {'class' if CLASS_SERVER else 'laptop test'} server {kart_version.VERSION} on "
              f"{args.bind}:{args.port}, track {server.lesson['track']}."
              + ("" if CLASS_SERVER else f" Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}."), flush=True)
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
