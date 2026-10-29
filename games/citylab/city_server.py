"""The City Lab class server: the city everyone's window is a view of, and the lessons around it (CHANGE 194).

    python city_server.py                       a laptop test server (codes CLUB42 and TEACH99)
    python city_server.py --class-server        the real one (JOIN_CODE and TEACHER_CODE set, behind Caddy)

Kart Lab's server, for a city: 60 times a second it takes each window's latest numbered input
(engine.predict.ServerInputQueue), asks the computer's drivers (cpu_brains: the traffic, the robots, the racers)
and the learners' brains (city_brain, in their own processes), steps the world (city_sim.World: a person on foot,
a car and a robot every window can step identically), and 30 times a second sends each window a binary snapshot of
everything (engine.wire, one record kind) stamped with the server's time and that window's last input applied, so
the window can check its own prediction against it. Everything else (who is here, the jobs in words, the chips,
designs, brains, lessons, missions, AI request cards) is JSON: the teaching layer is the engine's
(engine/teaching.py) with City Lab's own checks in city_teaching.py.

A window's keys reach its person, or the car it drives, with no wait: the window predicts and the server corrects.
Getting in and out, bumps, hits and the jobs happen here only.
"""
import argparse
import asyncio
import copy
import hmac
import ipaddress
import json
import math
import os
import re
import sys
import time

import websockets

import city_version
sys.path.insert(0, city_version.ENGINE_HOME)
from engine import club_ticket, gfx_tiers, predict, rw_sound, schema, wire  # noqa: E402
from engine.outbox import Outboxes  # noqa: E402
from engine.seats import Seats, dropped  # noqa: E402
from engine import lifecycle, tick_stats  # noqa: E402

import ai_pipeline  # noqa: E402
import cpu_brains  # noqa: E402
import city_brain  # noqa: E402
import city_jobs  # noqa: E402
import city_map  # noqa: E402
import city_missions as cm  # noqa: E402
import city_mods  # noqa: E402
import city_profiles  # noqa: E402
import city_sim as sim  # noqa: E402
import city_teaching  # noqa: E402

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
GAME_ID = "citylab"
TICKET_KEY = os.environ.get("CLUBCODERS_TICKET_KEY")
LIVE_FILE = os.environ.get("CLUBCODERS_LIVE_FILE", "")
DESK_INBOX = os.environ.get("CLUBCODERS_DESK_INBOX")
DATA = city_teaching.DATA
CLASS_SERVER = False
OPEN_SIGNUP = False
BAD_LOGINS = city_profiles.RateLimit(10)
BRAIN_UPLOAD_GAP = 3.0
MAX_LEARNERS = 4
MAX_PEOPLE = 8
SEND_RATE = 1 / 30
JOBS_RATE = 0.5          # the JSON jobs message at least this often
BRAIN_EVERY = 3
T0 = time.perf_counter()
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230), (240, 120, 40),
           (60, 200, 200), (230, 90, 160)]
TRAFFIC_COLOURS = sim.TRAFFIC_COLOURS
TEACHER_COLOUR = (180, 90, 230)
SCHEMA = wire.Schema("city", sim.SCHEMA_FIELDS)
IDLE = (0.0, 0.0, 0)
HERE = os.path.dirname(os.path.abspath(__file__))
CARD_NOTE_FILE = os.path.join(DATA, "card_note_saved.json")
GFX_MAX_FILE = os.path.join(DATA, "gfx_max_saved.json")
LIMITS_FILE = os.path.join(DATA, "limits_saved.json")
MISSIONS_FILE = os.path.join(DATA, "mission_settings.json")
MISSION_KEYS = ("mode", "city", "traffic", "robots", "parked", "racers", "cpu_level", "teacher_player", "designs_locked",
                "damage", "time", "jobs", "user_mods", "mods_in_vote", "arena_in_vote", "hazards", "tools", "limits")
HAZARD_WORDS = {"traffic": "Traffic", "robots": "Robots"}
TIMES = ("day", "dusk", "night")
STAGE_ITEMS = tuple(HAZARD_WORDS)
JOB_KINDS = ("delivery", "taxi", "race", "roundup")
PHASE_FREE, PHASE_COUNTDOWN, PHASE_RACING = 0, 1, 2

WEEK1_LESSON = {
    "lesson_number": 1,
    "mode": "practice",            # practice: the city is open and the jobs run; race: the teacher's street race
    "city": city_map.DEFAULT_CITY, # which city (city_map.CITIES)
    "traffic": 6,                  # the computer's cars about (with the hazard "traffic")
    "robots": 6,                   # the robots about (with the hazard "robots")
    "parked": 10,                  # cars parked for anyone to take
    "racers": 2,                   # computer racers in the teacher's street race
    "cpu_level": "medium",         # how they race: easy, medium, expert
    "teacher_player": True,        # the teacher is in the city too
    "designs_locked": False,
    "damage": True,                # cars take damage (mended at the garage); off: nothing is ever dented
    "time": "day",                 # day, dusk or night
    "jobs": {k: True for k in JOB_KINDS},
    "hazards": dict(cm.NO_HAZARDS),
    "ai_card_note": "",
    "gfx_max": None,
    "limits": sim.default_limits(),
    "user_mods": {},
    "sound": dict(rw_sound.DEFAULT_SOUND),
    "tools": copy.deepcopy(cm.LESSONS[1]["tools"]),
    "brains": False,
}


def server_ms():
    return int((time.perf_counter() - T0) * 1000) & 0xFFFFFFFF


def step_ms(due):
    return round((due - T0) * 1000) & 0xFFFFFFFF


class CityUnit:
    """A player's person as the teaching layer sees it: its id, its brain while autopilot is on, its hits."""

    def __init__(self, server, pid):
        self.server, self.pid, self.brain = server, pid, None

    @property
    def hits(self):
        return self.server.world.hits.get(self.pid, 0)


def keep_presses(late, nxt):
    return (nxt[0], nxt[1], nxt[2] | late[2])


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = sim.default_design(name if role == "learner" else "Teacher", colour)
        self.start_colour = list(colour)
        self.person = None                                # its person's id
        self.unit = None
        self.inputs = predict.ServerInputQueue(idle=IDLE, merge=keep_presses)
        self.last_brain = IDLE
        self.profile = None
        self.perf = None
        self.ctrl_seq = None
        self.seen_snap = None
        self.seen_at = None
        self.brain_at = -BRAIN_UPLOAD_GAP


class CityServer:
    def __init__(self, lesson_file=None):
        self.lesson = copy.deepcopy(WEEK1_LESSON)
        try:
            sim.RULES.update(city_mods.load_rules())
            city_mod = city_mods.load_city()
            self.lesson.update(city=city_mod["city"], traffic=city_mod["traffic"], robots=city_mod["robots"],
                               cpu_level=city_mod["cpu_level"])
        except city_mods.ModError as e:
            print("Mods not used:", e, flush=True)
        carried = os.path.join(DATA, "lesson_carried.json")
        if not lesson_file and os.path.exists(carried):
            lesson_file = carried
        if lesson_file and os.path.exists(lesson_file):
            with open(lesson_file) as f:
                saved = json.load(f)
            self.lesson.update({k: v for k, v in saved.items() if k in WEEK1_LESSON or k in MISSION_KEYS})
            if lesson_file == carried:
                os.remove(carried)
        for k, v in cm.NO_HAZARDS.items():
            self.lesson["hazards"].setdefault(k, v)
        try:
            with open(MISSIONS_FILE, encoding="utf-8") as f:
                self.mission_settings = json.load(f)
            if not isinstance(self.mission_settings, dict):
                self.mission_settings = {}
        except (OSError, ValueError):
            self.mission_settings = {}
        self.lesson["saved_missions"] = self.saved_missions()
        try:
            with open(LIMITS_FILE, encoding="utf-8") as f:
                saved_limits = json.load(f)
        except (OSError, ValueError):
            saved_limits = None
        self.lesson["limits"] = sim.clean_limits(saved_limits, sim.clean_limits(self.lesson.get("limits")))
        try:
            with open(CARD_NOTE_FILE, encoding="utf-8") as f:
                self.lesson["ai_card_note"] = str(json.load(f).get("note", ""))[:300]
        except (OSError, ValueError, AttributeError):
            pass
        try:
            with open(GFX_MAX_FILE, encoding="utf-8") as f:
                self.lesson["gfx_max"] = gfx_tiers.class_max(json.load(f).get("gfx_max"))
        except (OSError, ValueError, AttributeError):
            pass
        self.players = {}
        self.outboxes = Outboxes()
        self.seats = Seats()
        self.watchdog = lifecycle.Watchdog()
        self.ticks = tick_stats.TickStats("City Lab")
        self.cpu = None
        self.group = []
        self.mod_votes = {}
        self.arena_votes = {}
        self.mod_makers = ai_pipeline.user_mod_makers()
        self.warnings = []
        self.teacher_design = sim.default_design("Teacher", TEACHER_COLOUR)
        self.design_for_everyone = None
        self.paused = False
        self.roster_version = 0
        self.snap_seq = 0
        self.jobs_version = None
        self.lesson_dirty = False
        self.tournament = None
        self.traffic = {}        # car id -> the driver's memory (the computer's cars about town)
        self.racers = {}         # car id -> (level, memory): the computer's racers
        self.parked = set()      # car ids parked for anyone
        self.robot_mem = {}      # robot id -> the driver's memory
        self.racers_for = None   # the race the computer's racers were lined up for
        self.racers_raced = False  # the computer's racers were in this street race (the teaching's mission 4 d)
        self.race_phase = PHASE_FREE
        self.rng_n = 0
        self.city = city_map.load(self.lesson["city"])
        self.world = self.new_world()
        self.teaching = city_teaching.Teaching(self)
        if not lesson_file:
            self.teaching.apply_lesson(1)
        self.use_mission_settings()
        self.rebuild()

    def new_world(self):
        w = sim.World(self.city, SCHEMA)
        w.jobs = city_jobs.Jobs(self.city, sim.RULES, self.jobs_enabled(), seed=self.rng_n + 1)
        w.units = {}
        w.practice = self.lesson.get("mode", "practice") == "practice"
        return w

    def jobs_enabled(self):
        got = self.lesson.get("jobs") if isinstance(self.lesson.get("jobs"), dict) else {}
        return {k: bool(got.get(k, True)) for k in JOB_KINDS}

    # ---------- the lesson's saved settings ----------
    def use_mission_settings(self):
        saved = self.mission_settings.get(str(self.lesson.get("lesson_number", 1)))
        self.lesson["brains"] = bool(self.lesson.get("tools", {}).get("brains"))
        if not isinstance(saved, dict):
            return False
        for key in MISSION_KEYS:
            if key in saved:
                self.lesson[key] = copy.deepcopy(saved[key])
        self.lesson["limits"] = sim.clean_limits(self.lesson.get("limits"))
        self.lesson["user_mods"] = {k: bool(v) for k, v in self.lesson.get("user_mods", {}).items() if k in sim.USER_MODS}
        for k, v in cm.NO_HAZARDS.items():
            self.lesson["hazards"].setdefault(k, v)
        if self.lesson.get("city") not in city_map.CITIES:
            self.lesson["city"] = city_map.DEFAULT_CITY
        self.lesson["brains"] = bool(self.lesson.get("tools", {}).get("brains"))
        return True

    def saved_missions(self):
        return sorted(int(k) for k in self.mission_settings if str(k).isdigit())

    def save_mission_settings(self):
        n = str(self.lesson.get("lesson_number", 1))
        self.mission_settings[n] = {k: copy.deepcopy(self.lesson[k]) for k in MISSION_KEYS if k in self.lesson}
        self.lesson["saved_missions"] = self.saved_missions()
        try:
            os.makedirs(DATA, exist_ok=True)
            with open(MISSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.mission_settings, f, indent=2)
        except OSError:
            pass

    # ---------- who is in the city ----------
    def learners(self):
        return [p for p in self.players.values() if p.role == "learner"]

    def teacher(self):
        return next((p for p in self.players.values() if p.role == "teacher"), None)

    def people_wanted(self):
        out = [p for p in self.learners()] + self.seats.players()
        t = self.teacher()
        if t is not None and self.lesson.get("teacher_player", True):
            out.append(t)
        return out

    def rebuild(self):
        """The world from the lesson: the city (built again only when it changes), everyone's person, the parked
        cars, the traffic and the robots to the lesson's counts, the jobs' switches."""
        L = self.lesson
        if L["city"] not in city_map.CITIES:
            L["city"] = city_map.DEFAULT_CITY
        if self.city.key != L["city"]:
            self.city = city_map.load(L["city"])
            self.world = self.new_world()
            self.traffic, self.racers, self.parked, self.robot_mem = {}, {}, set(), {}
            self.race_phase = PHASE_FREE
            for p in self.players.values():
                p.person, p.unit = None, None
        w = self.world
        w.practice = L.get("mode", "practice") == "practice"
        w.damage = bool(L.get("damage", True))
        w.set_user_mods(L.get("user_mods"))
        w.jobs.enabled = self.jobs_enabled()
        w.jobs.rules = sim.RULES
        wanted = self.people_wanted()
        for p in self.players.values():
            if p not in wanted and p.person is not None:
                w.remove_person(p.person)
                p.person, p.unit = None, None
        for p in wanted:
            if p.person is None:
                used = {q.person for q in wanted if q.person is not None}
                p.person = next((i for i in range(MAX_PEOPLE) if i not in used), None)
                if p.person is None:
                    continue
            if p.person not in w.people:
                w.add_person(p.person, p.design)
            else:
                w.designs[p.person] = sim.fit_design(p.design)
            p.unit = CityUnit(self, p.person)
            w.units[p.person] = p.unit
        for pid in list(w.units):
            if pid not in w.people:
                del w.units[pid]
        # the parked cars, the traffic and the robots, to the lesson's numbers (city_sim.World's helpers: an offline
        # window fills its city the same way)
        w.park_cars(max(0, min(40, int(L.get("parked", 10)))), self.parked)
        want = max(0, min(30, int(L.get("traffic", 6)))) if L["hazards"].get("traffic") else 0
        while len(self.traffic) < want:
            self.traffic[w.add_traffic(len(self.traffic))["id"]] = {}
        while len(self.traffic) > want:
            cid = max(self.traffic)
            w.remove_car(cid)
            del self.traffic[cid]
        want = max(0, min(20, int(L.get("robots", 6)))) if L["hazards"].get("robots") else 0
        while len(self.robot_mem) < want:
            self.robot_mem[w.add_patrol(len(self.robot_mem))["id"]] = {}
        while len(self.robot_mem) > want:
            rid = max(self.robot_mem)
            w.remove_robot(rid)
            del self.robot_mem[rid]
        for p in wanted:
            if not self.seats.holding(p):
                self.teaching.attach(p)
        self.roster_version += 1
        self.jobs_version = None

    def owner_of(self, pid):
        return next((p.name for p in self.players.values() if p.person == pid), None) or \
            next((p.name + " (away)" for p in self.seats.players() if p.person == pid), None)

    def roster(self):
        w = self.world
        return {"type": "roster", "version": self.roster_version, "city": self.city.key, "city_name": self.city.name,
                "people": [{"id": pid, "name": d["name"], "colour": d["colour"], "design": d, "owner": self.owner_of(pid)}
                           for pid, d in ((pid, w.designs[pid]) for pid in w.people)],
                "cars": [{"id": cid, "design": w.designs[cid], "colour": w.designs[cid]["colour"],
                          "kind": "traffic" if cid in self.traffic else "racer" if cid in self.racers else "parked"}
                         for cid in w.cars],
                "robots": [{"id": rid, "design": w.designs[rid], "name": w.designs[rid]["name"]} for rid in w.robots],
                "mine": {p.name: p.person for p in self.players.values()},
                "user_mods": w.user_mods, "practice": w.practice,
                "perf": {p.name: p.perf for p in self.players.values() if p.perf}}

    def jobs_msg(self):
        w = self.world
        brains = {}
        for p in self.players.values():
            rec = self.teaching.record(p.name)
            brains[p.name] = {"on": rec.autopilot, "error": rec.brain.error if rec.brain else None,
                              "has": rec.brain is not None}
        body = w.jobs.state(w)
        return {"type": "jobs", "sm": server_ms(), "tick": w.tick, "phase": self.race_phase, "paused": self.paused,
                "practice": w.practice, "events": [[t, e] for t, e in w.events if w.tick - t < 300][-4:],
                "cash": {str(pid): p["cash"] for pid, p in w.people.items()},
                "names": {str(pid): w.designs[pid]["name"] for pid in w.people},
                "brains": brains, **body}

    def rules(self):
        return {"stats": sim.STATS, "points_total": sim.POINTS_TOTAL, "stat_min": sim.STAT_MIN,
                "stat_max": sim.STAT_MAX, "settings": sim.SETTINGS, "stat_notes": sim.STAT_NOTES,
                "full": sim.full_limits(), "cpu_levels": list(cpu_brains.LEVELS),
                "cities": {k: v["name"] for k, v in city_map.CITIES.items()}, "bodies": list(sim.BODIES),
                "looks": list(sim.LOOKS), "max_people": MAX_PEOPLE, "jobs": list(JOB_KINDS),
                "bump": {"distance": sim.RULES.get("bump_distance", 2.4), "slowdown": sim.RULES.get("bump_slowdown", 0.3),
                         "transfer": sim.RULES.get("bump_transfer", 0.7)}}

    def limits_for(self, player):
        return sim.full_limits() if player.role == "teacher" else self.lesson["limits"]

    # ---------- connections ----------
    async def handler(self, ws):
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if not isinstance(hello, dict):
                return
        except Exception:
            return
        where = client_address(ws)
        if BAD_LOGINS.blocked(where):
            await ws.close(4008, "Too many wrong tries from this computer. Wait a minute, then try again.")
            return
        if CLASS_SERVER and hello.get("version") != city_version.VERSION:
            page = city_version.DOWNLOAD_PAGE or "your teacher"
            await ws.close(4006, f"Out of date: download Club Coders {city_version.VERSION} from {page}"[:120])
            return
        ticket = None
        if hello.get("ticket") and TICKET_KEY:
            with open(TICKET_KEY, encoding="utf-8") as f:
                ticket = club_ticket.verify(f.read().strip(), hello["ticket"], GAME_ID)
            if ticket is None:
                BAD_LOGINS.failed(where)
                await ws.close(4011, "Your login has run out: open Club Coders and log in again.")
                return
            role = ticket["role"]
            if role == "learner":
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
            BAD_LOGINS.failed(where)
            await ws.close(4001, "wrong class code")
            return
        if role == "teacher" and self.teacher():
            await ws.close(4002, "a teacher is already connected")
            return
        profile, is_new = None, False
        if role == "learner":
            try:
                if ticket:
                    profile, is_new = city_profiles.ticket_profile(ticket["name"]), False
                else:
                    profile, is_new = await asyncio.to_thread(city_profiles.login, hello.get("name", ""),
                                                              hello.get("password", ""), OPEN_SIGNUP)
            except city_profiles.LoginError as e:
                BAD_LOGINS.failed(where)
                await ws.close(4004, str(e)[:120])
                return
            name = profile["name"]
        else:
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(ticket["name"] if ticket else hello.get("name", "")))[:12] or "Teacher"
        old = next((q for q in self.players.values()
                    if q.role == role and city_profiles.slug(q.name) == city_profiles.slug(name)), None)
        if old is not None:
            await self.outboxes.close(old.ws, 4005, "you logged in again somewhere else")
            self.players.pop(old.ws, None)
        if role == "learner" and len(self.learners()) >= MAX_LEARNERS:
            await ws.close(4003, f"the class is full ({MAX_LEARNERS} learners)")
            return
        colour = COLOURS[len(self.learners()) % len(COLOURS)] if role == "learner" else TEACHER_COLOUR
        p = Player(ws, role, name, colour)
        p.profile = profile
        held = self.seats.take(city_profiles.slug(name)) if role == "learner" else None
        if old is not None:
            p.person = old.person
        elif held is not None:
            p.person = held.person
            print(f"  {name} is back: their place was kept", flush=True)
        if role == "teacher":
            p.design = self.teacher_design
        else:
            saved = self.teaching.load_saved_design(name)
            if saved:
                p.design = saved
            self.teaching.login(p)
            if self.design_for_everyone:
                await self.build_for(p, self.design_for_everyone, quiet=True)
        self.players[ws] = p
        self.outboxes.open(ws)
        print(f"+ {name} ({role})", flush=True)
        self.rebuild()
        self.world.events.append((self.world.tick, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "me": p.person, "lesson": self.lesson,
                             "design": p.design, "city": self.city.to_data(), "rules": self.rules(),
                             "prefs": (profile or {}).get("prefs", {}), "new_profile": bool(profile and is_new),
                             "code": city_version.CODE,
                             "live_ready": getattr(self, "live_ready", None) if role == "teacher" else None})
        await self.broadcast_lesson()
        await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
        if role == "teacher":
            await self.warn_teacher()
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    try:
                        self.on_binary(p, raw)
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                try:
                    m = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                if isinstance(m, dict):
                    await lifecycle.handle(self.on_message, p, m)
        except websockets.ConnectionClosed:
            pass
        finally:
            self.outboxes.drop(ws)
            if self.players.get(ws) is p:
                del self.players[ws]
                if role == "teacher":
                    self.teacher_design = p.design
                self.teaching.save()
                if role == "learner" and dropped(ws) and p.person is not None:
                    self.seats.hold(city_profiles.slug(name), p)
                    print(f"- {name} dropped: their place is kept {self.seats.seconds:.0f} s", flush=True)
                    self.roster_version += 1
                else:
                    print(f"- {name} left", flush=True)
                    self.rebuild()
                await self.broadcast_lesson()

    def on_binary(self, p, raw):
        if wire.kind_of(raw) == wire.KIND_INPUT:
            m = wire.unpack_input(raw)
            p.inputs.push(m["seq"], (m["throttle"], m["steer"], m["buttons"]), [tuple(x) for x in m["prev"]])
            p.seen_snap, p.seen_at = m["ack"], time.perf_counter()

    async def deliver(self, replies):
        for ws, msg in replies:
            await self.send(ws, msg)

    async def send(self, ws, msg, key=None):
        await self.outboxes.send(ws, json.dumps(msg, separators=(",", ":")) if isinstance(msg, dict) else msg, key)

    async def notice_teacher(self, text):
        t = self.teacher()
        if t:
            await self.send(t.ws, {"type": "notice", "text": text})

    # ---------- messages ----------
    async def on_message(self, p, m):
        kind = m.get("type")
        if kind == "brain":
            if p.role == "learner" and not self.lesson.get("tools", {}).get("brains", True):
                await self.send(p.ws, {"type": "notice", "text": "Brains aren't switched on for this mission yet."})
                return
            await self.upload_brain(p, str(m.get("source", "")))
            return
        if kind == "autopilot" and "on" in m:
            r = self.teaching.record(p.name)
            if r.brain is None:
                await self.send(p.ws, {"type": "notice", "text": "Upload a brain first (press U)."})
                return
            r.autopilot = bool(m["on"])
            if r.autopilot:
                r.brain.error, r.brain.started, r.brain.memory = None, None, {}
            self.teaching.attach(p)
            self.teaching.save_profile(p.name)
            self.jobs_version = None
            await self.deliver([(p.ws, self.teaching.missions_msg(p))])
            return
        if kind not in ("control", "ping", "perf", "design", "design_for", "cpu_brain", "start", "grid"):
            replies = self.teaching.on_message(p, m)
            if replies is not None:
                if kind == "autopilot":
                    self.jobs_version = None
                broadcast = replies == "broadcast" or "broadcast" in replies
                if replies != "broadcast":
                    await self.deliver([r for r in replies if r != "broadcast"])
                if broadcast:
                    await self.broadcast_lesson()
                    await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
                return
        if kind == "ping":
            await self.send(p.ws, {"type": "pong", "t": m.get("t"), "sm": server_ms()})
        elif kind == "perf":
            p.perf = {k: m.get(k) for k in ("fps", "ping", "tier", "stalls", "delay", "ctrl", "corr") if k in m}
        elif kind in ("mod_vote", "arena_vote") and p.role == "learner":
            votes, key, known = (self.mod_votes, m.get("mod"), sim.USER_MODS) if kind == "mod_vote" else \
                (self.arena_votes, m.get("item"), STAGE_ITEMS)
            in_vote = self.lesson.get("mods_in_vote" if kind == "mod_vote" else "arena_in_vote", {})
            if isinstance(key, str) and key in known and in_vote.get(key, True):
                votes[key] = [n for n in votes.get(key, []) if n != p.name] + ([p.name] if m.get("on") else [])
                await self.broadcast_lesson()
        elif kind == "control":
            try:
                th, st = float(m.get("throttle", 0)), float(m.get("steer", 0))
                if math.isfinite(th) and math.isfinite(st):
                    p.inputs.push(int(m.get("seq", 0)), (max(-1.0, min(1.0, th)), max(-1.0, min(1.0, st)),
                                                         int(m.get("buttons", 0)) & 0xFF))
            except (TypeError, ValueError, OverflowError):
                pass
        elif kind == "design":
            await self.on_design(p, m)
        elif p.role == "teacher":
            await self.teacher_command(m)

    async def on_design(self, p, m):
        if self.lesson["designs_locked"] and p.role == "learner":
            await self.send(p.ws, {"type": "design_result", "ok": False, "design": p.design,
                                   "problems": ["The teacher has locked designs for now."]})
            return
        hack = bool(m.get("code")) and p.role == "learner" and bool(self.lesson["tools"].get("code_view"))
        new = self.clean_design(p, m.get("design", {}), everything=hack or p.role == "teacher")
        limits = self.limits_for(p)
        if hack:
            limits = sim.code_limits(limits)
        problems = sim.check_design(new, limits)
        old = p.design
        outside = self.outside_lesson(old, new) if hack and not problems else []
        if not problems:
            p.design = new
            self.refit(p)
            self.world.events.append((self.world.tick, f"{p.name} rebuilt {new['name']}"))
        self.teaching.on_design(p, new, problems, not problems, old=old, by_code=bool(m.get("code")))
        if not problems and p.role == "learner":
            self.teaching.save_design(p.name, new)
        await self.send(p.ws, {"type": "design_result", "ok": not problems, "problems": problems, "design": p.design})
        await self.deliver(self.teaching.teacher_update() + ([(p.ws, self.teaching.missions_msg(p))]
                                                             if p.role == "learner" else []))
        if not problems:
            await self.broadcast_lesson()
        if outside:
            await self.warn_teacher(p, outside)

    def clean_design(self, p, d, everything=False):
        old, tools = p.design, self.lesson["tools"]
        d = d if isinstance(d, dict) else {}
        new = copy.deepcopy(old)
        new.setdefault("points", {})
        new.setdefault("settings", {})
        if everything or tools.get("name_and_colour"):
            if isinstance(d.get("name"), str):
                new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", d["name"]).strip()[:sim.NAME_MAX] or old["name"]
            if isinstance(d.get("colour"), list):
                new["colour"] = d["colour"]
            if d.get("body") in sim.BODIES:
                new["body"] = d["body"]
            if d.get("look") in sim.LOOKS:
                new["look"] = d["look"]
        pts = d.get("points") if isinstance(d.get("points"), dict) else d
        for k in sim.STATS:
            if (everything or tools.get(k) or tools.get("points_table")) and k in pts:
                new["points"][k] = pts[k]
        if p.role == "learner":
            new["name"] = new["name"] or p.name
        return new

    def refit(self, p):
        """A player's new design goes into the city: the person as they are, the look and the car's paint theirs."""
        if p.person is None or p.person not in self.world.people:
            return
        self.world.designs[p.person] = sim.fit_design(p.design)
        self.teaching.attach(p)
        self.roster_version += 1

    def outside_lesson(self, old, new):
        return schema.outside_lesson(sim.schema(), old, new, self.lesson["tools"])

    async def warn_teacher(self, p=None, changes=None):
        if p is not None:
            self.warnings.append({"who": p.name, "time": time.strftime("%H:%M"), "changes": changes})
            del self.warnings[:-200]
        t = self.teacher()
        if t:
            await self.send(t.ws, {"type": "warnings", "list": self.warnings})

    async def fit_learners(self):
        limits = self.lesson["limits"]
        for p in self.learners():
            new = sim.fit_design(p.design, limits)
            if new["points"] == p.design.get("points"):
                continue
            p.design = new
            self.refit(p)
            self.teaching.save_design(p.name, new)
            await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new, "by_teacher": True})

    async def build_for(self, p, d, quiet=False):
        new = copy.deepcopy(p.design)
        if isinstance(d.get("name"), str):
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", d["name"]).strip()[:sim.NAME_MAX] or new["name"]
        for key in ("colour", "body", "look"):
            if key in d:
                new[key] = d[key]
        pts = d.get("points") if isinstance(d.get("points"), dict) else d
        for key in sim.STATS:
            if key in pts:
                new.setdefault("points", {})[key] = pts[key]
        problems = sim.check_design(new, sim.full_limits())
        if problems:
            if not quiet:
                await self.notice_teacher("Not built: " + "; ".join(problems))
            return problems
        p.design = new
        self.refit(p)
        self.teaching.save_design(p.name, new)
        self.world.events.append((self.world.tick, f"The teacher rebuilt {p.name}'s design"))
        await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new, "by_teacher": True})
        if not quiet:
            await self.notice_teacher(f"Built {new['name']} for {p.name}")
        return []

    async def upload_brain(self, p, source):
        now = time.monotonic()
        if now - p.brain_at < BRAIN_UPLOAD_GAP:
            await self.send(p.ws, {"type": "brain_result", "ok": False, "error": "wait a few seconds before uploading again"})
            return
        p.brain_at = now
        try:
            loaded = await asyncio.to_thread(city_brain.load_brain, source, p.name)
        except city_brain.BrainError as e:
            loaded = e
        if self.players.get(p.ws) is not p:
            if not isinstance(loaded, Exception):
                loaded[0].close()
            return
        reply = self.teaching.upload_brain(p, source, loaded)
        self.jobs_version = None
        await self.deliver([(p.ws, reply), (p.ws, self.teaching.missions_msg(p))] + self.teaching.teacher_update())

    async def teacher_command(self, m):
        kind = m.get("type")
        L = self.lesson
        w = self.world
        if kind == "mod_makers":
            makers = m.get("makers")
            for key, who in (makers.items() if isinstance(makers, dict) else ()):
                who = ai_pipeline.maker_name(who)
                if not (isinstance(key, str) and re.fullmatch(r"[a-z0-9_]{1,40}", key) and who):
                    continue
                if self.mod_makers.get(key) == "" and not m.get("new"):
                    continue
                if key in self.mod_makers or len(self.mod_makers) < 500:
                    self.mod_makers[key] = who
            ai_pipeline.save_user_mod_makers(self.mod_makers)
            await self.broadcast_lesson()
        elif kind == "delete_learner":
            await self.delete_learner(m.get("learner", ""))
        elif kind == "restart_server":
            self.teaching.save()
            self.carry_lesson()
            for ws in list(self.players):
                await self.send(ws, {"type": "notice", "big": True,
                                     "text": "THE SERVER IS RESTARTING to load changes\nyou'll reconnect in a few seconds"})
            if CLASS_SERVER:
                for ws in list(self.players):
                    await self.send(ws, {"type": "notice", "big": True,
                                         "text": "THE GAME IS UPDATING\nback in 10 seconds: your window will reopen"})
                asyncio.get_running_loop().call_later(10, lambda: asyncio.ensure_future(lifecycle.exit_after_closing(
                    self.outboxes, self.players, 3, lambda: (self.teaching.save(), self.carry_lesson()))))
                return
            print("Restarting to load code changes...", flush=True)
            await lifecycle.exit_after_closing(self.outboxes, self.players, 3)
        elif kind == "restart_clients":
            for ws, q in list(self.players.items()):
                if q.role == "learner":
                    await self.send(ws, {"type": "restart_client"})
        elif kind == "cpu_brain":
            await self.notice_teacher("City Lab's traffic, robots and racers drive themselves: there is no demo brain "
                                      "to upload. Set the racers' level in Controls.")
        elif kind == "design_for_all":
            d = m.get("design", {}) if isinstance(m.get("design"), dict) else {}
            built, failed = [], []
            for p in self.learners():
                problems = await self.build_for(p, d, quiet=True)
                (failed if problems else built).append(p.name)
            self.design_for_everyone = d
            L["design_for_everyone"] = str(d.get("name", ""))[:12]
            await self.notice_teacher(f"Built {d.get('name', '?')} for {', '.join(built) or 'nobody yet'}"
                                      + (f"; not for {', '.join(failed)}" if failed else "") +
                                      ". Anyone who joins this session gets it too.")
            await self.broadcast_lesson()
        elif kind == "design_for":
            p = next((q for q in self.learners() if q.name == m.get("learner")), None)
            if p is None:
                await self.notice_teacher("That learner isn't connected.")
                return
            await self.build_for(p, m.get("design", {}) if isinstance(m.get("design"), dict) else {})
            await self.broadcast_lesson()
        elif kind == "tournament":  # (Kart Lab's league: City Lab's grand prix is the street race, see start)
            await self.notice_teacher("City Lab's grand prix is the street race: press Enter to put everyone on the line.")
        elif kind == "lesson":
            await self.update_lesson(m.get("lesson", {}) if isinstance(m.get("lesson"), dict) else {})
        elif kind == "start":
            await self.start_race()
        elif kind in ("grid", "restart"):
            for pid in list(w.people):
                w.respawn(pid)
            w.events.append((w.tick, "Everyone back to the depot"))
            self.jobs_version = None
            await self.broadcast_lesson()
        elif kind == "pause":
            self.paused = not self.paused
            w.events.append((w.tick, "PAUSED" if self.paused else "GO!"))
            self.jobs_version = None
        elif kind == "fix":
            t = self.teacher()
            if t is not None and t.person is not None and w.fix(t.person):
                w.events.append((w.tick, f"{w.designs[t.person]['name']} fixed"))
                self.jobs_version = None
        elif kind == "save_lesson":
            self.save_mission_settings()
            try:
                with open(os.path.join(DATA, "lesson_saved.json"), "w") as f:
                    json.dump(L, f, indent=2)
            except OSError:
                pass
            w.events.append((w.tick, f"Mission {L.get('lesson_number', 1)} settings saved"))
            await self.broadcast_lesson()
        elif kind == "restore_lesson":
            n = L.get("lesson_number", 1)
            self.teaching.apply_lesson(n)
            self.rebuild()
            w.events.append((w.tick, f"Mission {n} settings restored"))
            await self.broadcast_lesson()

    async def start_race(self):
        """(Enter) The teacher's street race: everyone into a car on the line (a car each, parked there), the
        computer's racers too, and the countdown runs."""
        w = self.world
        jobs = w.jobs
        L = self.lesson
        if jobs.race is not None and jobs.race["state"] == "racing":
            await self.notice_teacher("A race is already running.")
            return
        L["mode"] = "race"
        w.practice = False
        lx, ly = jobs.race_line()
        course = jobs.courses[jobs.course_n % len(jobs.courses)]
        nx, ny = course[1]
        yaw = math.degrees(math.atan2(ny - ly, nx - lx))
        fx, fy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        slots = []
        for n in range(MAX_PEOPLE + 4):
            row, side = n // 2, (1 if n % 2 else -1)
            slots.append((lx - fx * (6.0 + row * 5.0) - fy * side * 2.2, ly - fy * (6.0 + row * 5.0) + fx * side * 2.2))
        for cid in list(self.racers):
            w.remove_car(cid)
        self.racers = {}
        jobs.race = {"course": course, "cars": {}, "done": [], "go": w.tick + city_jobs.RACE_COUNTDOWN + 60 * 5,
                     "state": "forming", "pay": {}}
        n = 0
        for pid, p in w.people.items():
            if p["link"]:
                car = w.cars.get(p["link"] - 1)
            else:
                car = None
                owner = next((q for q in self.players.values() if q.person == pid), None)
                d = owner.design if owner else w.designs[pid]
                car = w.add_car(d, 0.0, 0.0, yaw)
                self.parked.add(car["id"])
                car["link"] = pid + 1
                p["link"] = car["id"] + 1
            sx, sy = slots[n % len(slots)]
            car.update(x=sx, y=sy, yaw=yaw, v=0.0, u=0.0, z=0.0, vz=0.0)
            jobs.race["cars"][car["id"]] = 0
            jobs.mine[pid] = {"kind": city_jobs.RACE, "stage": 0, "car": car["id"]}
            n += 1
        level = L.get("cpu_level") if L.get("cpu_level") in cpu_brains.LEVELS else "medium"
        for k in range(max(0, min(6, int(L.get("racers", 2))))):
            d = sim.default_design(cpu_brains.name_for(level, k), TRAFFIC_COLOURS[(k + 2) % len(TRAFFIC_COLOURS)], sim.BODIES[(k + 2) % 4])
            d["points"] = {"speed": 40, "acceleration": 35, "grip": 25}
            sx, sy = slots[n % len(slots)]
            car = w.add_car(d, sx, sy, yaw)
            self.racers[car["id"]] = (level, {})
            jobs.race["cars"][car["id"]] = 0
            n += 1
        self.racers_for, self.racers_raced = jobs.race, bool(self.racers)
        self.roster_version += 1
        jobs.changed = True
        w.events.append((w.tick, "THE STREET RACE: on the line, 3, 2, 1..."))
        self.jobs_version = None
        await self.broadcast_lesson()

    async def update_lesson(self, update):
        L = self.lesson
        w = self.world
        rebuild = False
        if update.get("cpu_level") in cpu_brains.LEVELS:
            L["cpu_level"] = update["cpu_level"]
            for cid in self.racers:
                self.racers[cid] = (update["cpu_level"], self.racers[cid][1])
            w.events.append((w.tick, f"Computer racers: {update['cpu_level']}"))
        if isinstance(update.get("limits"), dict):
            L["limits"] = sim.clean_limits(update["limits"], L["limits"])
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(LIMITS_FILE, "w", encoding="utf-8") as f:
                    json.dump(L["limits"], f)
            except OSError:
                pass
            await self.fit_learners()
        if isinstance(update.get("ai_card_note"), str):
            note = "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in update["ai_card_note"])
            L["ai_card_note"] = " ".join(note.split())[:300]
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(CARD_NOTE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"note": L["ai_card_note"]}, f)
            except OSError:
                pass
        if "gfx_max" in update:
            L["gfx_max"] = gfx_tiers.class_max(update["gfx_max"])
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(GFX_MAX_FILE, "w", encoding="utf-8") as f:
                    json.dump({"gfx_max": L["gfx_max"]}, f)
            except OSError:
                pass
        if isinstance(update.get("mods_in_vote"), dict):
            in_vote = {k: bool(v) for k, v in update["mods_in_vote"].items() if k in sim.USER_MODS}
            L["mods_in_vote"] = {**L.get("mods_in_vote", {}), **in_vote}
            for k, v in in_vote.items():
                if not v:
                    self.mod_votes.pop(k, None)
        if isinstance(update.get("arena_in_vote"), dict):
            in_vote = {k: bool(v) for k, v in update["arena_in_vote"].items() if k in STAGE_ITEMS}
            L["arena_in_vote"] = {**L.get("arena_in_vote", {}), **in_vote}
            for k, v in in_vote.items():
                if not v:
                    self.arena_votes.pop(k, None)
        if isinstance(update.get("user_mods"), dict):
            switched = {k: bool(v) for k, v in update["user_mods"].items() if k in sim.USER_MODS}
            L["user_mods"] = {**L.get("user_mods", {}), **switched}
            w.set_user_mods(L["user_mods"])
            self.roster_version += 1
        if update.get("city") in city_map.CITIES and update["city"] != L["city"]:
            L["city"] = update["city"]
            rebuild = True
        for key, lo, hi in (("traffic", 0, 30), ("robots", 0, 20), ("parked", 0, 40), ("racers", 0, 6)):
            if key in update:
                try:
                    v = max(lo, min(hi, int(update[key])))
                except (TypeError, ValueError, OverflowError):
                    continue
                rebuild |= v != L[key]
                L[key] = v
                if key in ("traffic", "robots") and v > 0 and not L["hazards"].get(key):
                    L["hazards"][key] = True
                    rebuild = True  # (CHANGE 201: switched on here, the hazards' own switch below sees no change)
        for key in ("teacher_player", "designs_locked"):
            if key in update:
                rebuild |= key == "teacher_player" and bool(update[key]) != bool(L.get(key))
                L[key] = bool(update[key])
        if isinstance(update.get("jobs"), dict):
            was = self.jobs_enabled()
            L["jobs"] = {k: bool(update["jobs"].get(k, was[k])) for k in JOB_KINDS}
            if L["jobs"] != was:
                w.jobs.enabled = dict(L["jobs"])
                on = [city_jobs.NAMES[k] for k, name in zip((1, 2, 3, 4), JOB_KINDS) if L["jobs"][name]]
                w.events.append((w.tick, "Jobs: " + (", ".join(on) if on else "none")))
                w.jobs.changed = True
        if update.get("time") in TIMES and update["time"] != L.get("time", "day"):
            L["time"] = update["time"]
            w.events.append((w.tick, {"day": "Daytime", "dusk": "Dusk: the lamps come on",
                                      "night": "Night falls: lights on"}[L["time"]]))
        if "damage" in update and bool(update["damage"]) != bool(L.get("damage", True)):
            L["damage"] = bool(update["damage"])
            w.damage = L["damage"]
            if not w.damage:
                for c in w.cars.values():
                    c["dmg"] = 0
            w.events.append((w.tick, "Damage on" if L["damage"] else "Damage off: every car mended"))
        if update.get("mode") in ("practice", "race", "battle"):
            mode = "race" if update["mode"] == "battle" else update["mode"]
            rebuild |= mode != L["mode"]
            L["mode"] = mode
        if "show_missions" in update:
            L["show_missions"] = self.paused = bool(update["show_missions"])
            w.events.append((w.tick, "PAUSED: look at your Mission tab" if self.paused else "GO!"))
        for key in ("hazards", "tools"):
            for k, v in (update.get(key, {}) if isinstance(update.get(key), dict) else {}).items():
                if key == "hazards" and k not in cm.NO_HAZARDS:
                    continue
                if key == "tools" and k not in L["tools"]:
                    continue
                v = bool(v)
                rebuild |= key == "hazards" and v != L[key].get(k)
                L[key][k] = v
        L["brains"] = bool(L["tools"].get("brains"))
        if "brains" in update:
            L["tools"]["brains"] = L["brains"] = bool(update["brains"])
        if isinstance(update.get("sound"), dict):
            L["sound"] = rw_sound.sound_settings(L.get("sound"), update["sound"])
        was = self.city.key
        if rebuild:
            self.rebuild()
        if self.city.key != was:
            msg = {"type": "city", "city": self.city.to_data(), "me": None}
            for ws, q in list(self.players.items()):
                await self.send(ws, dict(msg, me=q.person))
        self.jobs_version = None
        await self.broadcast_lesson()

    def carry_lesson(self):
        try:
            os.makedirs(DATA, exist_ok=True)
            with open(os.path.join(DATA, "lesson_carried.json"), "w") as f:
                json.dump(self.lesson, f, indent=2)
        except OSError:
            pass

    def reload_mods(self, written):
        try:
            if "mods/rules.py" in written:
                sim.RULES.update(city_mods.load_rules())
            if "mods/city.py" in written:
                t = city_mods.load_city()
                self.lesson.update(city=t["city"], traffic=t["traffic"], robots=t["robots"], cpu_level=t["cpu_level"])
        except city_mods.ModError as e:
            print("Mods not used:", e, flush=True)
        for p in self.learners():
            if f"mods/drivers/{city_teaching.slug(p.name)}.py" in written:
                p.design = self.teaching.load_saved_design(p.name) or p.design
        self.rebuild()
        self.world.events.append((self.world.tick, "An approved AI change is now in the game"))
        self.lesson_dirty = True

    def user_mods_msg(self):
        here = {p.name for p in self.learners()} | set(self.group)
        return {"makers": {k: v for k, v in self.mod_makers.items() if k in sim.USER_MODS},
                "votes": {k: v for k, v in self.mod_votes.items() if v and k in sim.USER_MODS},
                "arena_votes": {k: v for k, v in self.arena_votes.items() if v},
                "here": sorted(here)}

    async def broadcast_lesson(self):
        msg = {"type": "lesson", "lesson": self.lesson, "mods": self.user_mods_msg(), "city": self.city.key,
               "class": [{"name": p.name, "role": p.role, "design": p.design} for p in self.players.values()],
               "tournament": None}
        for ws in list(self.players):
            await self.send(ws, msg)

    async def delete_learner(self, username):
        name = city_profiles.clean_name(username)
        for ws, q in list(self.players.items()):
            if q.role == "learner" and city_profiles.slug(q.name) == city_profiles.slug(name):
                del self.players[ws]
                await self.outboxes.close(ws, 4007, "Your account has been deleted by the teacher.")
        text = self.teaching.delete_learner(name)
        gone = city_profiles.slug(name)
        if any(v and city_profiles.slug(v) == gone for v in self.mod_makers.values()):
            self.mod_makers = {k: "" if city_profiles.slug(v) == gone else v for k, v in self.mod_makers.items()}
            ai_pipeline.save_user_mod_makers(self.mod_makers)
        for votes in (self.mod_votes, self.arena_votes):
            for k in votes:
                votes[k] = [n for n in votes[k] if city_profiles.slug(n) != gone]
        self.rebuild()
        t = self.teacher()
        if t:
            await self.deliver([(t.ws, {"type": "notice", "text": text})] + self.teaching.teacher_update())
        await self.broadcast_lesson()

    # ---------- the loops ----------
    async def physics_loop(self):
        next_step, steps = time.perf_counter(), 0
        while True:
            next_step += sim.STEP
            now = time.perf_counter()
            if next_step < now - 4 * sim.STEP:
                skip = (now - next_step) // sim.STEP
                next_step += skip * sim.STEP
                self.ticks.skip(int(skip))
            await asyncio.sleep(max(0.0, next_step - now))
            start = time.perf_counter()
            if not self.paused:
                self.step()
            else:
                for p in self.players.values():
                    p.inputs.drain()
            self.step_ms = step_ms(next_step)
            steps += 1
            if steps % 30 == 0:
                self.teaching.tick(self.world.tick * sim.STEP)
                for p in self.seats.expired():
                    print(f"- {p.name} didn't come back: their place has gone", flush=True)
                    self.rebuild()
                    await self.broadcast_lesson()
                if self.lesson_dirty:
                    self.lesson_dirty = False
                    await self.broadcast_lesson()
            self.ticks.step(time.perf_counter() - start, max(0.0, start - next_step))
            self.watchdog.ping()
            if self.ticks.due() and self.players:
                line = self.ticks.report(self.outboxes, {ws: p.name for ws, p in self.players.items()})
                inputs = []
                for p in self.players.values():
                    if p.person is not None and (p.inputs.repeats or p.inputs.skipped):
                        inputs.append(f"{p.name} {p.inputs.repeats} dry, {p.inputs.skipped} skipped")
                        p.inputs.repeats = p.inputs.skipped = 0
                print(line + ("; inputs: " + ", ".join(inputs) if inputs else ""), flush=True)

    def step(self):
        w = self.world
        inputs = {}
        ask_brains = w.tick % BRAIN_EVERY == 0
        for p in self.players.values():
            if p.person is None or p.person not in w.people:
                continue
            keys = p.inputs.pop_for_tick()
            p.ctrl_seq = p.inputs.applied
            brain = p.unit.brain if p.unit is not None else None
            if brain is not None:
                if ask_brains:
                    p.last_brain = brain(w.people[p.person], w)
                inputs[p.person] = (p.last_brain[0], p.last_brain[1], p.last_brain[2] | (keys[2] & sim.RESPAWN))
            else:
                inputs[p.person] = keys
        self.rng_n = (self.rng_n + 1) % 1000003
        for cid, mem in self.traffic.items():
            if cid in w.cars and not w.cars[cid]["link"]:
                inputs[cid] = cpu_brains.drive_car(cid, w.cars[cid], w, mem, ((self.rng_n * 7919 + cid * 131) % 1000) / 1000)
        for cid, (level, mem) in self.racers.items():
            if cid in w.cars:
                inputs[cid] = cpu_brains.drive_racer(cid, w.cars[cid], w, mem, level)
        for rid, mem in self.robot_mem.items():
            if rid in w.robots and not w.robots[rid]["link"] and rid not in w.jobs.taxi_stops:
                inputs[rid] = cpu_brains.drive_robot(rid, w.robots[rid], w, mem)
        w.step_all(inputs)
        self.race_racers()
        race = w.jobs.race
        self.race_phase = PHASE_FREE if race is None else PHASE_COUNTDOWN if race["state"] != "racing" else PHASE_RACING
        if race is None and self.racers:  # the race is over: the computer's racers drive off as traffic
            for cid, (level, mem) in list(self.racers.items()):
                if cid in w.cars:
                    self.traffic[cid] = {}
            self.racers = {}
            self.roster_version += 1

    def race_racers(self):
        """A street race opened at the line (a car stopped on it): the computer's racers line up on the grid beside
        it, as an offline window's do."""
        w, L = self.world, self.lesson
        race = w.jobs.race
        if race is None or race["state"] != "forming" or self.racers or self.racers_for is race:
            return
        self.racers_for = race
        n = max(0, min(6, int(L.get("racers", 2))))
        if not n:
            return
        mine = list(race["cars"])
        slots = w.jobs.grid_slots(len(mine) + n)
        for cid, (x, y, yaw) in zip(mine, slots):
            w.cars[cid].update(x=x, y=y, yaw=yaw, v=0.0, u=0.0)
        level = L.get("cpu_level") if L.get("cpu_level") in cpu_brains.LEVELS else "medium"
        for k in range(n):
            x, y, yaw = slots[len(mine) + k]
            d = sim.default_design(cpu_brains.name_for(level, k), TRAFFIC_COLOURS[(k + 2) % len(TRAFFIC_COLOURS)],
                                   sim.BODIES[(k + 2) % 4])
            d["points"] = {"speed": 38, "acceleration": 34, "grip": 28}
            car = w.add_car(d, x, y, yaw)
            race["cars"][car["id"]] = 0
            self.racers[car["id"]] = (level, {})
        self.racers_raced = True
        self.roster_version += 1

    async def send_loop(self):
        sent_version, last_jobs, next_send, ticks = {}, 0.0, time.perf_counter(), 0
        while True:
            next_send += SEND_RATE
            now = time.perf_counter()
            if next_send < now - 4 * SEND_RATE:
                next_send = now
            await asyncio.sleep(max(0.0, next_send - now))
            if not self.players:
                continue
            ticks += 1
            if ticks % 30 == 0:
                await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
            self.snap_seq = (self.snap_seq + 1) & 0xFFFF
            sm = getattr(self, "step_ms", None) or server_ms()
            entities = self.world.things()
            jobs_msg = None
            w = self.world
            version = (self.race_phase, len(w.events), w.jobs.changed, self.paused)
            if version != self.jobs_version or w.jobs.changed or now - last_jobs > JOBS_RATE:
                w.jobs.changed = False
                self.jobs_version, last_jobs = (self.race_phase, len(w.events), False, self.paused), now
                jobs_msg = json.dumps(self.jobs_msg(), separators=(",", ":"))
                perf_version = tuple(sorted((p.name, json.dumps(p.perf, sort_keys=True)) for p in self.players.values() if p.perf))
                if perf_version != getattr(self, "perf_version", None):
                    self.perf_version = perf_version
                    self.roster_version += 1
            roster = None
            now_s = time.perf_counter()
            for ws, p in list(self.players.items()):
                if backed_up(ws):
                    continue
                if p.seen_snap and p.seen_at is not None and now_s - p.seen_at < 1.0:
                    behind = predict.seq_diff(self.snap_seq, p.seen_snap)
                    if (ticks % 3 if behind > 20 else ticks % 2 if behind > 8 else 0):
                        continue
                if sent_version.get(ws) != self.roster_version:
                    roster = roster or json.dumps(self.roster(), separators=(",", ":"))
                    await self.send(ws, roster, "roster")
                    sent_version[ws] = self.roster_version
                if jobs_msg:
                    await self.send(ws, jobs_msg, "jobs")
                flags = self.race_phase | (min(15, p.inputs.depth()) << 4)
                frame = wire.pack_snapshot(SCHEMA, sm, self.snap_seq, entities, ack=p.inputs.ack(), flags=flags)
                await self.send(ws, frame, "state")
            await asyncio.sleep(0)

    async def watch_desk(self):
        if not LIVE_FILE:
            return
        seen, presence = None, {}
        report_file = os.path.join(os.path.dirname(LIVE_FILE), "reports", f"{GAME_ID}.json")
        while True:
            live = read_live()
            mine = live if live and live.get("game") == GAME_ID else None
            key = mine["id"] if mine else None
            if key == seen and mine and sorted(mine.get("learners", [])) != self.group:
                self.group = sorted(mine.get("learners", []))
                for p in self.seats.players():
                    if p.name not in self.group:
                        self.seats.take(city_profiles.slug(p.name))
                        self.rebuild()
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in self.group:
                        self.players.pop(ws, None)
                        await self.outboxes.close(ws, 4009, "Your teacher took you out of this game: back to the lobby.")
                        self.rebuild()
            if key != seen:
                seen, presence = key, {}
                allowed = set(mine.get("learners", [])) if mine else set()
                self.group, self.mod_votes, self.arena_votes = sorted(allowed), {}, {}
                self.seats.clear()
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in allowed:
                        self.players.pop(ws, None)
                        await self.outboxes.close(ws, 4009, "The session has ended." if not mine else "You aren't in this group.")
                if mine:
                    self.teaching.apply_lesson(int(mine.get("lesson", 1)))
                    self.rebuild()
                    self.world.events.append((self.world.tick, f"Session started: {mine.get('group', '')}, lesson {mine.get('lesson', 1)}"))
                else:
                    self.rebuild()
                    self.world.events.append((self.world.tick, "The session has ended"))
                await self.broadcast_lesson()
            if mine:
                stamp = time.strftime("%Y-%m-%d %H:%M")
                for p in self.learners():
                    presence.setdefault(p.name, {"first": stamp})["last"] = stamp
                try:
                    os.makedirs(os.path.dirname(report_file), exist_ok=True)
                    report = {"live_id": mine["id"], "game": GAME_ID,
                              **self.teaching.session_report(str(mine.get("started", "")), presence)}
                    with open(report_file + ".tmp", "w", encoding="utf-8") as f:
                        json.dump(report, f)
                    os.replace(report_file + ".tmp", report_file)
                except OSError:
                    pass
            if DESK_INBOX and os.path.isdir(DESK_INBOX):
                for entry in sorted(os.listdir(DESK_INBOX)):
                    if not entry.endswith(".json"):
                        continue
                    path = os.path.join(DESK_INBOX, entry)
                    try:
                        with open(path, encoding="utf-8") as f:
                            request = json.load(f)
                    except (OSError, ValueError):
                        request = {}
                    try:
                        if request.get("delete_learner"):
                            await self.delete_learner(request["delete_learner"])
                    finally:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
            await asyncio.sleep(2)

    async def watch_live(self):
        pointer = os.environ.get("CLUBCODERS_LIVE_POINTER")
        self.live_ready = None
        failed, told = os.environ.get("CLUBCODERS_LIVE_FAILED") or None, set()
        while pointer:
            try:
                with open(pointer, encoding="utf-8") as f:
                    wanted = f.read().strip() or None
            except OSError:
                wanted = None
            ready = wanted if wanted and wanted != city_version.CODE else None
            if ready and ready == failed:
                ready = None
                for ws, p in list(self.players.items()):
                    if p.role == "teacher" and ws not in told:
                        told.add(ws)
                        await self.send(ws, {"type": "notice", "text": "The live update didn't pass its check as the class server started (engine/canary.py), so the class is running the release's own code. Fix the change and make it live again."})
            if ready != self.live_ready:
                self.live_ready = ready
                for ws, p in list(self.players.items()):
                    if ready and p.role == "teacher":
                        await self.send(ws, {"type": "live_update", "id": ready})
            await asyncio.sleep(10)


def read_live():
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


def client_address(ws):
    host = (ws.remote_address or ("?",))[0]
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    forwarded = ws.request.headers.get("X-Forwarded-For") if local and ws.request is not None else None
    return forwarded.split(",")[-1].strip() if forwarded else host


def code_role(code):
    for role, real in (("teacher", TEACHER_CODE), ("learner", LEARNER_CODE)):
        if hmac.compare_digest(code.encode("utf-8"), real.encode("utf-8")):
            return role
    return None


def check_class_server_codes():
    if "JOIN_CODE" not in os.environ or "TEACHER_CODE" not in os.environ:
        return "JOIN_CODE and TEACHER_CODE must be set."
    if LEARNER_CODE in DEMO_CODES.values() or TEACHER_CODE in DEMO_CODES.values():
        return "the demo codes CLUB42 and TEACH99 can't be used on the class server."
    if len(LEARNER_CODE) < 6 or len(TEACHER_CODE) < 16:
        return "the class code needs at least 6 characters and the teacher code at least 16."
    if LEARNER_CODE == TEACHER_CODE:
        return "the class code and teacher code must be different."
    return None


def fine_timer():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.winmm.timeBeginPeriod(1)
        except Exception:
            pass


async def main():
    global CLASS_SERVER, OPEN_SIGNUP
    fine_timer()
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8783)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--class-server", action="store_true", help="the real class server: real codes required")
    ap.add_argument("--lesson", help="start from saved lesson settings (JSON)")
    ap.add_argument("--city", default=None, choices=list(city_map.CITIES))
    ap.add_argument("--traffic", type=int, default=None, help="the computer's cars about")
    ap.add_argument("--robots", type=int, default=None, help="robots about")
    ap.add_argument("--level", default=None, choices=list(cpu_brains.LEVELS))
    ap.add_argument("--autostart", type=float, default=None, help="seconds after the first window joins, start a street race")
    args = ap.parse_args()
    CLASS_SERVER = args.class_server
    local_only = args.bind in ("127.0.0.1", "localhost", "::1")
    if CLASS_SERVER or not local_only:
        problem = check_class_server_codes()
        if problem:
            raise SystemExit("City Lab server not started: " + problem)
    OPEN_SIGNUP = os.environ.get("CITYLAB_OPEN_SIGNUP") == "1" or not CLASS_SERVER
    server = CityServer(args.lesson)
    overrides = {k: v for k, v in (("city", args.city), ("traffic", args.traffic), ("robots", args.robots),
                                   ("cpu_level", args.level)) if v is not None}
    if overrides:
        if overrides.get("traffic"):
            server.lesson["hazards"]["traffic"] = True
        if overrides.get("robots"):
            server.lesson["hazards"]["robots"] = True
        server.lesson.update(overrides)
        server.rebuild()
    if CLASS_SERVER:
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(city_version.CODE)

    async def autostart():
        while not server.players:
            await asyncio.sleep(0.2)
        await asyncio.sleep(args.autostart)
        await server.start_race()

    tasks = [server.physics_loop(), server.send_loop(), server.watch_live(), server.watch_desk()] + \
        ([autostart()] if args.autostart is not None else [])
    async with websockets.serve(server.handler, args.bind, args.port, compression=None, ping_interval=5,
                                ping_timeout=10, max_queue=8):
        tick_stats.start_up()
        print(f"City Lab {'class' if CLASS_SERVER else 'laptop test'} server {city_version.VERSION} on "
              f"{args.bind}:{args.port}, city {server.lesson['city']}."
              + ("" if CLASS_SERVER else f" Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}. A new username "
                                         f"makes a profile."), flush=True)
        await lifecycle.run(tasks, server.outboxes, server.players, server.teaching.save)


if __name__ == "__main__":
    asyncio.run(main())
