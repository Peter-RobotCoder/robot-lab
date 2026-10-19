"""The Kart Lab class server: the race everyone's window is a view of, and the lessons around it.

    python kart_server.py                       a laptop test server (codes CLUB42 and TEACH99)
    python kart_server.py --class-server        the real one (JOIN_CODE and TEACHER_CODE set, behind Caddy)

What it does 60 times a second: takes each window's latest numbered input (engine.predict.ServerInputQueue), asks
the computer drivers and the learners' brains (kart_brain, in their own processes), steps the race (kart_sim.Race:
a hand-written kart every window can step identically), and 30 times a second sends each window a binary snapshot
of every kart (engine.wire) stamped with the server's time and that window's last input applied, so the window can
check its own prediction against it. Everything else (who is here, the race's phase, the countdown, results,
designs, brains, lessons, missions, AI request cards) is JSON, as in the other games: the teaching layer is the
engine's (engine/teaching.py) with Kart Lab's own checks in kart_teaching.py.

The window's keys reach its kart with no wait: the window predicts its own kart and the server only corrects it.
Bumps between karts and the race itself happen here only; nothing a window does can move another kart.

In practice (lessons 1 to 3) the track is open: everyone drives as soon as they are on it, laps are timed and
nothing finishes. In race mode (lessons 4 and 5) the teacher starts each race (Enter) and a tournament is a
league of races: points for places, a champion at the end.
"""
import argparse
import asyncio
import copy
import hmac
import ipaddress
import json
import math
import os
import random
import re
import sys
import time

import websockets

import kart_version
sys.path.insert(0, kart_version.ENGINE_HOME)
from engine import club_ticket, gfx_tiers, predict, rw_sound, schema, wire  # noqa: E402
from engine.outbox import Outboxes  # noqa: E402
from engine.seats import Seats, dropped  # noqa: E402
from engine import lifecycle, tick_stats  # noqa: E402

import ai_pipeline  # noqa: E402
import cpu_brains  # noqa: E402
import kart_brain  # noqa: E402
import kart_missions as km  # noqa: E402
import kart_mods  # noqa: E402
import kart_profiles  # noqa: E402
import kart_sim as sim  # noqa: E402
import kart_teaching  # noqa: E402
import kart_track  # noqa: E402
import kart_items  # noqa: E402  (CHANGE 159: the power-ups)

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
GAME_ID = "kartlab"  # (the club desk's name for this game)
TICKET_KEY = os.environ.get("CLUBCODERS_TICKET_KEY")
LIVE_FILE = os.environ.get("CLUBCODERS_LIVE_FILE", "")   # the club desk: which group is launched, in which game
DESK_INBOX = os.environ.get("CLUBCODERS_DESK_INBOX")
DATA = kart_teaching.DATA
CLASS_SERVER = False
OPEN_SIGNUP = False    # a new username makes a profile (laptop test servers only, unless KARTLAB_OPEN_SIGNUP=1)
BAD_LOGINS = kart_profiles.RateLimit(10)  # wrong codes or passwords: 10 a minute per computer
BRAIN_UPLOAD_GAP = 3.0                     # seconds between one learner's brain uploads
MAX_LEARNERS = 4
MAX_KARTS = 8
SEND_RATE = 1 / 30
RACE_RATE = 0.5          # the JSON race message (phase, places, countdown, events)
BRAIN_EVERY = 3          # brains are asked every third tick (20 a second): plenty for driving, kind to the server
NEXT_RACE_AFTER = 8.0    # seconds between a league's races
T0 = time.perf_counter()
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230), (240, 120, 40),
           (60, 200, 200), (230, 90, 160)]
TEACHER_COLOUR = (180, 90, 230)
SCHEMA = wire.Schema("kart", sim.SCHEMA_FIELDS)
IDLE = (0.0, 0.0, 0)
HERE = os.path.dirname(os.path.abspath(__file__))
CARD_NOTE_FILE = os.path.join(DATA, "card_note_saved.json")  # the teacher's words on the AI card
GFX_MAX_FILE = os.path.join(DATA, "gfx_max_saved.json")  # ...and the class's graphics maximum
LIMITS_FILE = os.path.join(DATA, "limits_saved.json")        # the learners' ranges, kept between sessions
MISSIONS_FILE = os.path.join(DATA, "mission_settings.json")  # the teacher's settings for each mission, kept by
# Save settings and used whenever that mission is chosen: these keys
MISSION_KEYS = ("mode", "track", "laps", "cpu_karts", "cpu_level", "teacher_kart", "designs_locked", "damage", "items", "time",
                "user_mods",
                "mods_in_vote", "arena_in_vote", "hazards", "tools", "limits")
HAZARD_WORDS = {"bumping": "Bumping", "cpu_karts": "Computer karts"}
TIMES = ("day", "dusk", "night")  # (CHANGE 172) the race's time of day
STAGE_ITEMS = tuple(HAZARD_WORDS)  # what learners can vote for on the Mods tab (the track's switches)

# What learners can see and change. The teacher edits this live from the teacher screen.
WEEK1_LESSON = {
    "lesson_number": 1,            # which of the 5 lessons: sets missions, tools and the track's switches
    "mode": "practice",            # practice = the track is open, laps are timed; race = the teacher starts races
    "track": "club",               # which track (kart_track.TRACKS)
    "laps": 3,                     # laps in a race
    "cpu_karts": 3,                # computer karts on the grid (when the hazard "cpu_karts" is on)
    "cpu_level": "medium",         # how they drive: easy, medium, expert
    "teacher_kart": True,          # the teacher's own kart is on the grid too
    "designs_locked": False,       # stop design changes (e.g. during a tournament)
    "damage": True,                # (CHANGE 158) real damage: hits slow a kart; it mends, quickly in the PIT box
    "items": {n: True for n in kart_items.ITEMS},  # (CHANGE 159) the power-ups the item boxes give (each on or off)
    "time": "day",                 # (CHANGE 172) the race's time of day: day, dusk or night (the headlights come on)
    "hazards": dict(km.NO_HAZARDS),
    "ai_card_note": "",            # the teacher's own instructions, shown on every learner's AI request card
    "gfx_max": None,               # the best graphics a learner may draw (engine.gfx_tiers.class_max; CHANGE 139)
    "limits": sim.default_limits(),  # the learners' ranges for every point (the teacher's Limits tab)
    "user_mods": {},               # features learners asked for (kart_sim.USER_MODS): the teacher switches them on
    "sound": dict(rw_sound.DEFAULT_SOUND),  # what everyone hears
    "tools": copy.deepcopy(km.LESSONS[1]["tools"]),
    "brains": False,               # (the same switch as tools["brains"]: kept for windows that read it here)
}


def server_ms():
    return int((time.perf_counter() - T0) * 1000) & 0xFFFFFFFF


def step_ms(due):
    """(CHANGE 155) The stamp for the state a physics step left: when that step was due on the same clock. Stamped
    when it was sent, a snapshot after one step and the next after three looked the same time apart, and the pages
    and windows, blending by the stamps, drew everything moving in jerks."""
    return round((due - T0) * 1000) & 0xFFFFFFFF


class KartUnit:
    """A player's kart as the teaching layer sees it: its id in the race, its brain while autopilot is on, and how
    many bumps it has had (the engine's Record counts hits)."""

    def __init__(self, server, kid):
        self.server, self.kid, self.brain = server, kid, None

    @property
    def hits(self):
        return self.server.race.hits.get(self.kid, 0)


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = sim.default_design(name if role == "learner" else "Teacher", colour)
        self.start_colour = list(colour)
        self.kart = None                                  # its kart's id
        self.unit = None                                  # KartUnit, while its kart is in the race
        self.inputs = predict.ServerInputQueue(idle=IDLE)  # numbered inputs from the window
        self.last_brain = IDLE
        self.profile = None
        self.perf = None
        self.ctrl_seq = None
        self.brain_at = -BRAIN_UPLOAD_GAP


class Tournament:
    """A league of races: everyone named scores points for their place in each race (10, 7, 5, 3, 2, 1...); after
    the last race the most points is the champion. Computer karts race but don't score."""
    POINTS = (10, 7, 5, 3, 2, 1)
    kind = "league"

    def __init__(self, names, races=3, shuffle=True):
        names = list(names)
        if shuffle:
            random.shuffle(names)
        self.names = names
        self.races = max(1, min(9, int(races)))
        self.points = {n: 0 for n in names}
        self.results = []     # each race: names in finishing order
        self.champion = None

    @property
    def race_number(self):
        return len(self.results) + 1

    def label(self, i=None):
        if self.champion:
            return f"CHAMPION: {self.champion}"
        if self.races == 1:
            return "THE GRAND PRIX"
        return f"RACE {self.race_number} OF {self.races}"

    title = label

    def record(self, order):
        """A race finished: order is every kart's name, first to last. Returns True when the league is over."""
        placed = [n for n in order if n in self.points]
        for i, n in enumerate(placed):
            self.points[n] += self.POINTS[i] if i < len(self.POINTS) else 0
        self.results.append(placed)
        if len(self.results) >= self.races:
            self.champion = max(self.points, key=lambda n: (self.points[n], -self.names.index(n))) if self.points else None
            return True
        return False

    def table(self):
        return sorted(self.points.items(), key=lambda kv: -kv[1])

    def summary(self):
        return {"kind": self.kind, "title": self.label(), "race": min(self.race_number, self.races),
                "races": self.races, "standings": [[n, p] for n, p in self.table()], "champion": self.champion,
                "results": self.results}


class KartServer:
    def __init__(self, lesson_file=None):
        self.lesson = copy.deepcopy(WEEK1_LESSON)
        try:  # the mod track choice and rules (an approved AI request may have changed them)
            sim.RULES.update(kart_mods.load_rules())
            track_mod = kart_mods.load_track()
            self.lesson.update(track=track_mod["track"], laps=track_mod["laps"], cpu_level=track_mod["cpu_level"])
            self.track_name = track_mod["name"]
        except kart_mods.ModError as e:
            print("Mods not used:", e, flush=True)
            self.track_name = kart_track.TRACKS[self.lesson["track"]]["name"]
        carried = os.path.join(DATA, "lesson_carried.json")  # (left by a restart for code changes)
        if not lesson_file and os.path.exists(carried):
            lesson_file = carried
        if lesson_file and os.path.exists(lesson_file):
            with open(lesson_file) as f:
                saved = json.load(f)
            self.lesson.update({k: v for k, v in saved.items() if k in WEEK1_LESSON or k in MISSION_KEYS})
            if lesson_file == carried:
                os.remove(carried)
        for k, v in km.NO_HAZARDS.items():
            self.lesson["hazards"].setdefault(k, v)
        try:
            with open(MISSIONS_FILE, encoding="utf-8") as f:
                self.mission_settings = json.load(f)  # mission number (as text) -> the teacher's saved settings
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
        self.players = {}        # websocket -> Player
        self.outboxes = Outboxes()  # each window's messages (CHANGE 160)
        self.seats = Seats()  # learners whose connection dropped: their kart kept a while (CHANGE 164)
        self.watchdog = lifecycle.Watchdog()  # (systemd's, on the VPS: CHANGE 160)
        self.ticks = tick_stats.TickStats("Kart Lab")  # how the physics loop keeps time (CHANGE 160)
        self.cpu = None          # (the engine's Learner view looks for a computer player here: Kart Lab has none)
        self.cpu_levels = {}     # kart id -> level, for the computer karts on the grid
        self.group = []          # the launched group's learners (from the club desk), here yet or not
        self.mod_votes = {}      # user mod -> the learners who'd like it switched on (this session)
        self.arena_votes = {}    # the same for the track's switches (STAGE_ITEMS)
        self.mod_makers = ai_pipeline.user_mod_makers()  # who made each user mod: their name goes in front of it
        self.warnings = []       # for the teacher: learners who changed, in the code, something outside the lesson
        self.teacher_design = sim.default_design("Teacher", TEACHER_COLOUR)
        self.design_for_everyone = None
        self.paused = False
        self.roster_version = 0
        self.snap_seq = 0
        self.race_version = None
        self.lesson_dirty = False
        self.tournament = None
        self.race_recorded = False
        self.next_race_at = None
        self.track = kart_track.load(self.lesson["track"])
        self.race = sim.Race(self.track, SCHEMA, self.lesson["laps"])
        self.race.units = {}
        self.teaching = kart_teaching.Teaching(self)
        if not lesson_file:
            self.teaching.apply_lesson(1)
        self.use_mission_settings()
        self.rebuild()

    # ---------- the lesson's saved settings ----------
    def use_mission_settings(self):
        """The teacher's saved settings for the mission the class is on, over the mission's own defaults (the
        presets in kart_missions): every control they saved, including what learners see in the garage."""
        saved = self.mission_settings.get(str(self.lesson.get("lesson_number", 1)))
        self.lesson["brains"] = bool(self.lesson.get("tools", {}).get("brains"))
        if not isinstance(saved, dict):
            return False
        for key in MISSION_KEYS:
            if key in saved:
                self.lesson[key] = copy.deepcopy(saved[key])
        self.lesson["limits"] = sim.clean_limits(self.lesson.get("limits"))
        self.lesson["user_mods"] = {k: bool(v) for k, v in self.lesson.get("user_mods", {}).items() if k in sim.USER_MODS}
        for k, v in km.NO_HAZARDS.items():
            self.lesson["hazards"].setdefault(k, v)
        if self.lesson.get("track") not in kart_track.TRACKS:
            self.lesson["track"] = "club"
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

    # ---------- who is racing ----------
    def learners(self):
        return [p for p in self.players.values() if p.role == "learner"]

    def teacher(self):
        return next((p for p in self.players.values() if p.role == "teacher"), None)

    def karts_wanted(self):
        """Everyone who gets a kart: the learners, and the teacher if their kart is switched on."""
        out = [p for p in self.learners()] + self.seats.players()  # (a dropped learner's kart races on: CHANGE 164)
        t = self.teacher()
        if t is not None and self.lesson.get("teacher_kart", True):
            out.append(t)
        return out

    def rebuild(self):
        """The karts from the players and the lesson's computer karts, back on the grid (in practice the track
        opens at once; in race mode the teacher starts the race)."""
        L = self.lesson
        owners_before = self.kart_owners()
        if L["track"] not in kart_track.TRACKS:
            L["track"] = "club"
        if self.track.name != kart_track.TRACKS[L["track"]]["name"]:
            self.track = kart_track.load(L["track"])
        practice = L.get("mode", "practice") == "practice"
        laps = 99 if practice else max(1, min(9, int(L.get("laps", 3))))
        race = sim.Race(self.track, SCHEMA, laps)
        race.units = {}
        race.practice = practice
        race.set_user_mods(L.get("user_mods"))
        race.set_damage(L.get("damage", True))
        race.items = kart_items.Items(race, self.items_allowed())  # (CHANGE 159)
        wanted = self.karts_wanted()
        for p in self.players.values():
            p.unit = None
            if p not in wanted:
                p.kart = None
        for p in wanted:
            if p.kart is None:  # (a free id, one no computer kart has if there is one: CHANGE 164)
                used = {q.kart for q in wanted if q.kart is not None}
                cpus = {kid for kid, who in owners_before.items() if who == "cpu"}
                p.kart = next((i for i in range(MAX_KARTS) if i not in used | cpus),
                              next((i for i in range(MAX_KARTS) if i not in used), None))
            if p.kart is None:
                continue
            race.add(p.kart, p.design)
            p.unit = KartUnit(self, p.kart)
            race.units[p.kart] = p.unit
        before_cpu = sorted(self.cpu_levels)
        self.cpu_levels = {}
        used = {p.kart for p in wanted if p.kart is not None}
        n, want = 0, int(L.get("cpu_karts", 0)) if L["hazards"].get("cpu_karts") else 0
        # (CHANGE 164) the computer karts keep the ids they had: a learner leaving used to hand their id, and their
        # place on the track, to a computer kart, and every computer kart after it moved up one
        free = [i for i in range(MAX_KARTS) if i not in used]
        for i in [i for i in before_cpu if i in free] + [i for i in free if i not in before_cpu]:
            if n >= want:
                break
            level = L.get("cpu_level") if L.get("cpu_level") in cpu_brains.LEVELS else "medium"
            race.add(i, sim.default_design(cpu_brains.name_for(level, n), COLOURS[i % len(COLOURS)]))
            self.cpu_levels[i] = level
            n += 1
        if self.race.phase == sim.FLAGS_RACE and not self.race.frozen():  # (a kart joining mid-race)
            race.tick, race.phase, race.go_tick = self.race.tick, self.race.phase, self.race.go_tick
            race.lap_start, race.lap_times = dict(self.race.lap_start), dict(self.race.lap_times)
            race.hits = dict(self.race.hits)
            owners = self.kart_owners(race)
            for kid, k in self.race.karts.items():
                if kid in race.karts and owners.get(kid) == owners_before.get(kid):  # (the same driver: CHANGE 164)
                    race.karts[kid] = k
            old = self.race.items  # (the boxes, shots and slicks out on the track carry on too)
            if old is not None and race.items is not None and self.race.track is race.track:
                race.items.boxes, race.items.shots, race.items.slicks = old.boxes, old.shots, old.slicks
                race.items.next_id = old.next_id
            race.finish = dict(self.race.finish)
            for kid in list(race.karts):
                race.lap_start.setdefault(kid, race.tick)
        self.race = race
        self.race_recorded = False
        for p in wanted:
            if not self.seats.holding(p):
                self.teaching.attach(p)
        if practice and race.phase == sim.FLAGS_GRID:  # the track is open: no countdown, no finish line
            race.start()
            race.go_tick = race.tick
            race.lap_start = {kid: race.tick for kid in race.karts}
            race.events[-1:] = [(race.tick, "Practice: the track is open")]
        self.roster_version += 1
        self.race_version = None

    def kart_owners(self, race=None):
        """(CHANGE 164) Who drives each kart: a player's name, or "cpu"."""
        race = race or self.race
        names = {p.kart: p.name for p in list(self.players.values()) + self.seats.players() if p.kart is not None}
        return {kid: names.get(kid, "cpu" if kid in self.cpu_levels else None) for kid in race.karts}

    def items_allowed(self):
        """(CHANGE 159) The lesson's power-ups, {item: on}, every item there (a lesson from before them: all on)."""
        got = self.lesson.get("items")
        got = got if isinstance(got, dict) else {}
        return {n: bool(got.get(n, True)) for n in kart_items.ITEMS}

    def roster(self):
        return {"type": "roster", "version": self.roster_version, "track": self.lesson["track"],
                "track_name": self.track_name, "laps": self.race.laps,
                "karts": [{"id": kid, "name": d["name"], "colour": d["colour"], "cpu": self.cpu_levels.get(kid),
                           "design": d,
                           "owner": next((p.name for p in self.players.values() if p.kart == kid), None) or
                                    next((p.name + " (away)" for p in self.seats.players() if p.kart == kid), None)}
                          for kid, d in self.race.designs.items()],
                "mine": {p.name: p.kart for p in self.players.values()},
                "user_mods": self.race.user_mods, "practice": self.race.practice,
                "perf": {p.name: p.perf for p in self.players.values() if p.perf}}

    def race_msg(self):
        r = self.race
        cd = r.countdown()
        brains = {}
        for p in self.players.values():
            rec = self.teaching.record(p.name)
            brains[p.name] = {"on": rec.autopilot, "error": rec.brain.error if rec.brain else None,
                              "has": rec.brain is not None}
        return {"type": "race", "phase": r.phase, "tick": r.tick, "sm": server_ms(),
                "go_in_ms": None if cd is None else int(cd * 1000),
                "places": r.places(), "laps": r.laps, "practice": r.practice, "paused": self.paused,
                "lap_times": {str(k): v for k, v in r.lap_times.items()},
                "events": [e for t, e in r.events if r.tick - t < 240][-4:],
                "results": r.results() if r.phase == sim.FLAGS_OVER else None,
                "tournament": self.tournament.summary() if self.tournament else None,
                "brains": brains}

    def rules(self):
        return {"stats": sim.STATS, "points_total": sim.POINTS_TOTAL, "stat_min": sim.STAT_MIN,
                "stat_max": sim.STAT_MAX, "settings": sim.SETTINGS, "stat_notes": sim.STAT_NOTES,
                "full": sim.full_limits(),  # the widest ranges: the teacher's own kart, and the Limits tab's sliders
                "cpu_levels": list(cpu_brains.LEVELS), "tracks": {k: v["name"] for k, v in kart_track.TRACKS.items()},
                "max_karts": MAX_KARTS,
                # (CHANGE 155) the page predicts its kart's bumps as the race makes them (mods/rules.py may change them)
                "bump": {"distance": sim.RULES.get("bump_distance", sim.BUMP_DISTANCE),
                         "slowdown": sim.RULES.get("bump_slowdown", 0.3)}}

    def limits_for(self, player):
        """The ranges a design is held to: the learners' (as the teacher has set them), or the widest ones for the
        teacher's own kart."""
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
        if CLASS_SERVER and hello.get("version") != kart_version.VERSION:
            page = kart_version.DOWNLOAD_PAGE or "your teacher"
            await ws.close(4006, f"Out of date: download Club Coders {kart_version.VERSION} from {page}"[:120])
            return
        ticket = None
        if hello.get("ticket") and TICKET_KEY:  # from the club desk, which has checked who this is
            with open(TICKET_KEY, encoding="utf-8") as f:
                ticket = club_ticket.verify(f.read().strip(), hello["ticket"], GAME_ID)
            if ticket is None:
                BAD_LOGINS.failed(where)
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
            BAD_LOGINS.failed(where)
            await ws.close(4001, "wrong class code")
            return
        if role == "teacher" and self.teacher():
            await ws.close(4002, "a teacher is already connected")
            return
        profile, is_new = None, False
        if role == "learner":  # username and password (slow on purpose, so it's checked away from the game loop)
            try:
                if ticket:
                    profile, is_new = kart_profiles.ticket_profile(ticket["name"]), False
                else:
                    profile, is_new = await asyncio.to_thread(kart_profiles.login, hello.get("name", ""),
                                                              hello.get("password", ""), OPEN_SIGNUP)
            except kart_profiles.LoginError as e:
                BAD_LOGINS.failed(where)
                await ws.close(4004, str(e)[:120])  # (a close reason can be at most 123 bytes)
                return
            name = profile["name"]
        else:
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(ticket["name"] if ticket else hello.get("name", "")))[:12] or "Teacher"
        old = next((q for q in self.players.values()
                    if q.role == role and kart_profiles.slug(q.name) == kart_profiles.slug(name)), None)
        if old is not None:  # logged in again (after a dropped connection): the old connection goes
            await self.outboxes.close(old.ws, 4005, "you logged in again somewhere else")
            self.players.pop(old.ws, None)
        if role == "learner" and len(self.learners()) >= MAX_LEARNERS:
            await ws.close(4003, f"the class is full ({MAX_LEARNERS} learners)")
            return
        colour = COLOURS[len(self.learners()) % len(COLOURS)] if role == "learner" else TEACHER_COLOUR
        p = Player(ws, role, name, colour)
        p.profile = profile
        held = self.seats.take(kart_profiles.slug(name)) if role == "learner" else None
        if old is not None:
            p.kart = old.kart
        elif held is not None:  # (CHANGE 164) back within the time: the same kart, where it is now
            p.kart = held.kart
            print(f"  {name} is back: their kart was kept", flush=True)
        if role == "teacher":
            p.design = self.teacher_design
        else:
            saved = self.teaching.load_saved_design(name)
            if saved:  # their kart from last time
                p.design = saved
            self.teaching.login(p)  # their missions, reflections, brain and settings from last time
            if self.design_for_everyone:
                await self.build_for(p, self.design_for_everyone, quiet=True)
        self.players[ws] = p
        self.outboxes.open(ws)  # (from now on everything to this window goes through its outbox: CHANGE 160)
        print(f"+ {name} ({role})", flush=True)
        self.rebuild()
        self.race.events.append((self.race.tick, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "kart": p.kart, "lesson": self.lesson,
                             "design": p.design, "track": kart_track.TRACKS[self.lesson["track"]],
                             "rules": self.rules(), "prefs": (profile or {}).get("prefs", {}),
                             "new_profile": bool(profile and is_new), "code": kart_version.CODE,
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
                    except Exception:  # noqa: BLE001  (a broken input frame: dropped, CHANGE 165)
                        pass
                    continue
                try:
                    m = json.loads(raw)
                except (ValueError, TypeError):
                    continue  # (not a message: dropped, CHANGE 165)
                if isinstance(m, dict):
                    await lifecycle.handle(self.on_message, p, m)  # (an error over one is logged, not the end: CHANGE 165)
        except websockets.ConnectionClosed:
            pass
        finally:
            self.outboxes.drop(ws)
            if self.players.get(ws) is p:  # (not already replaced by the same person logging in again)
                del self.players[ws]
                if role == "teacher":
                    self.teacher_design = p.design
                self.teaching.save()
                if role == "learner" and dropped(ws) and p.kart is not None:  # (lost, not left: CHANGE 164)
                    self.seats.hold(kart_profiles.slug(name), p)
                    print(f"- {name} dropped: their kart is kept {self.seats.seconds:.0f} s", flush=True)
                    self.roster_version += 1
                else:
                    print(f"- {name} left", flush=True)
                    self.rebuild()
                await self.broadcast_lesson()

    def on_binary(self, p, raw):
        if wire.kind_of(raw) == wire.KIND_INPUT:
            m = wire.unpack_input(raw)
            inp = (m["throttle"], m["steer"], m["buttons"])
            p.inputs.push(m["seq"], inp, [tuple(x) for x in m["prev"]])

    async def deliver(self, replies):
        for ws, msg in replies:
            await self.send(ws, msg)

    async def send(self, ws, msg, key=None):
        """Into the window's outbox (engine.outbox: never waits for a slow window; CHANGE 160). key: a kind of
        message of which only the newest matters (a snapshot), so one not sent yet is dropped for this."""
        await self.outboxes.send(ws, json.dumps(msg, separators=(",", ":")) if isinstance(msg, dict) else msg, key)

    async def notice_teacher(self, text):
        t = self.teacher()
        if t:
            await self.send(t.ws, {"type": "notice", "text": text})

    # ---------- messages ----------
    async def on_message(self, p, m):
        kind = m.get("type")
        if kind == "brain":  # loaded in its own process, away from the game loop
            if p.role == "learner" and not self.lesson.get("tools", {}).get("brains", True):
                await self.send(p.ws, {"type": "notice", "text": "Brains aren't switched on for this mission yet."})
                return
            await self.upload_brain(p, str(m.get("source", "")))
            return
        if kind == "autopilot" and "on" in m:  # (a window that says which way; the engine's message toggles)
            r = self.teaching.record(p.name)
            if r.brain is None:
                await self.send(p.ws, {"type": "notice", "text": "Upload a brain first (press U)."})
                return
            r.autopilot = bool(m["on"])
            if r.autopilot:
                r.brain.error, r.brain.started, r.brain.memory = None, None, {}
            self.teaching.attach(p)
            self.teaching.save_profile(p.name)
            self.race_version = None
            await self.deliver([(p.ws, self.teaching.missions_msg(p))])
            return
        if kind not in ("control", "ping", "perf", "design", "design_for", "cpu_brain", "start", "grid"):
            replies = self.teaching.on_message(p, m)
            if replies is not None:
                if kind == "autopilot":
                    self.race_version = None  # (the race message says whose autopilot is on)
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
        elif kind in ("mod_vote", "arena_vote") and p.role == "learner":  # a tick on the learner's Mods tab (CHANGE 134:
            # the votes were kept and shown but never taken in)
            votes, key, known = (self.mod_votes, m.get("mod"), sim.USER_MODS) if kind == "mod_vote" else \
                (self.arena_votes, m.get("item"), STAGE_ITEMS)
            in_vote = self.lesson.get("mods_in_vote" if kind == "mod_vote" else "arena_in_vote", {})
            if isinstance(key, str) and key in known and in_vote.get(key, True):
                votes[key] = [n for n in votes.get(key, []) if n != p.name] + ([p.name] if m.get("on") else [])
                await self.broadcast_lesson()
        elif kind == "control":  # a JSON control (tests, a brainless window): the same as a binary input
            try:
                th, st = float(m.get("throttle", 0)), float(m.get("steer", 0))
                if math.isfinite(th) and math.isfinite(st):  # (NaN would have spoilt the whole race: CHANGE 165)
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
        # from the code panel a learner can change what the garage hides (while the lesson has the Code view)
        hack = bool(m.get("code")) and p.role == "learner" and bool(self.lesson["tools"].get("code_view"))
        new = self.clean_design(p, m.get("design", {}), everything=hack or p.role == "teacher")
        limits = self.limits_for(p)
        if hack:  # (the code may go to twice the teacher's limit, or the maximum)
            limits = sim.code_limits(limits)
        problems = sim.check_design(new, limits)
        old = p.design  # (the missions compare the two: what the build changed, and how)
        outside = self.outside_lesson(old, new) if hack and not problems else []
        if not problems:
            p.design = new
            self.refit(p)
            self.race.events.append((self.race.tick, f"{p.name} rebuilt {new['name']}"))
        self.teaching.on_design(p, new, problems, not problems, old=old, by_code=bool(m.get("code")))
        if not problems and p.role == "learner":
            self.teaching.save_design(p.name, new)  # autosave: their kart is there next lesson
        await self.send(p.ws, {"type": "design_result", "ok": not problems, "problems": problems, "design": p.design})
        await self.deliver(self.teaching.teacher_update() + ([(p.ws, self.teaching.missions_msg(p))]
                                                             if p.role == "learner" else []))
        if not problems:
            await self.broadcast_lesson()  # the teacher's class list shows the new design
        if outside:
            await self.warn_teacher(p, outside)

    def clean_design(self, p, d, everything=False):
        """A design from a window, with only what this lesson's garage lets a learner change (or everything, from
        the code panel or the teacher)."""
        old, tools = p.design, self.lesson["tools"]
        d = d if isinstance(d, dict) else {}
        new = dict(old)
        if everything or tools.get("name_and_colour"):
            if isinstance(d.get("name"), str):
                new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", d["name"]).strip()[:12] or old["name"]
            if isinstance(d.get("colour"), list):
                new["colour"] = d["colour"]
            if d.get("body") in sim.BODIES:  # (CHANGE 173: a kart or a sports car, with the name and colour)
                new["body"] = d["body"]
        for k in sim.STATS:
            if (everything or tools.get(k) or tools.get("points_table")) and k in d:
                new[k] = d[k]
        if p.role == "learner":
            new["name"] = new["name"] or p.name
        return new

    def refit(self, p):
        """A player's new design goes into the race: the kart stays where it is with its new stats."""
        if p.kart is None or p.kart not in self.race.karts:
            return
        self.race.designs[p.kart] = sim.fit_design(p.design)
        self.race.stats[p.kart] = sim.stats_of(self.race.designs[p.kart])
        self.teaching.attach(p)
        self.roster_version += 1

    def outside_lesson(self, old, new):
        """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
        did it in the code): [[variable, the old value, the new value], ...] for the teacher's Warnings tab."""
        return schema.outside_lesson(sim.schema(), old, new, self.lesson["tools"])

    async def warn_teacher(self, p=None, changes=None):
        """Add a warning (a learner got round the lesson in the code) and send the teacher the list."""
        if p is not None:
            self.warnings.append({"who": p.name, "time": time.strftime("%H:%M"), "changes": changes})
            del self.warnings[:-200]
        t = self.teacher()
        if t:
            await self.send(t.ws, {"type": "warnings", "list": self.warnings})

    async def fit_learners(self):
        """The teacher has changed the limits: a learner's kart outside them is pulled back to the nearest allowed
        values (and rebuilt, and saved), and the learner is told."""
        limits = self.lesson["limits"]
        for p in self.learners():
            new = sim.fit_design(p.design, limits)
            if new is p.design:
                continue
            p.design = new
            self.refit(p)
            self.teaching.save_design(p.name, new)
            await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new,
                                   "by_teacher": True})

    async def build_for(self, p, d, quiet=False):
        """The teacher builds this kart for learner p (the Learner view's BUILD FOR NAME; and for all). Returns the
        problems (none: built)."""
        new = dict(p.design)
        if isinstance(d.get("name"), str):
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", d["name"]).strip()[:12] or new["name"]
        for key in ("colour", "body", *sim.STATS):
            if key in d:
                new[key] = d[key]
        problems = sim.check_design(new, sim.full_limits())
        if problems:
            if not quiet:
                await self.notice_teacher("Not built: " + "; ".join(problems))
            return problems
        p.design = new
        self.refit(p)
        self.teaching.save_design(p.name, new)
        self.race.events.append((self.race.tick, f"The teacher rebuilt {p.name}'s kart"))
        await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new,
                               "by_teacher": True})
        if not quiet:
            await self.notice_teacher(f"Built {new['name']} for {p.name}")
        return []

    async def upload_brain(self, p, source):
        now = time.monotonic()
        if now - p.brain_at < BRAIN_UPLOAD_GAP:
            await self.send(p.ws, {"type": "brain_result", "ok": False,
                                   "error": "wait a few seconds before uploading again"})
            return
        p.brain_at = now
        try:
            loaded = await asyncio.to_thread(kart_brain.load_brain, source, p.name)
        except kart_brain.BrainError as e:
            loaded = e
        if self.players.get(p.ws) is not p:  # they left while it loaded
            if not isinstance(loaded, Exception):
                loaded[0].close()
            return
        reply = self.teaching.upload_brain(p, source, loaded)
        self.race_version = None
        await self.deliver([(p.ws, reply), (p.ws, self.teaching.missions_msg(p))] + self.teaching.teacher_update())

    async def teacher_command(self, m):
        kind = m.get("type")
        L = self.lesson
        if kind == "mod_makers":  # who made each user mod, from the teacher's laptop (its change history knows)
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
        elif kind == "delete_learner":  # everything the server keeps about them goes (they're disconnected first)
            await self.delete_learner(m.get("learner", ""))
        elif kind == "restart_server":  # load code changes (the .bat starts it again)
            self.teaching.save()
            self.carry_lesson()
            for ws in list(self.players):
                await self.send(ws, {"type": "notice", "big": True,
                                     "text": "THE SERVER IS RESTARTING to load changes\nyou'll reconnect in a few seconds"})
            if CLASS_SERVER:  # the class server (a live update): everyone gets a warning, then it restarts
                for ws in list(self.players):
                    await self.send(ws, {"type": "notice", "big": True,
                                         "text": "THE GAME IS UPDATING\nback in 10 seconds: your window will reopen"})
                asyncio.get_running_loop().call_later(10, lambda: asyncio.ensure_future(lifecycle.exit_after_closing(
                    self.outboxes, self.players, 3, lambda: (self.teaching.save(), self.carry_lesson()))))  # (1012: CHANGE 160)
                return
            print("Restarting to load code changes...", flush=True)
            await lifecycle.exit_after_closing(self.outboxes, self.players, 3)
        elif kind == "restart_clients":  # everyone's window reopens itself with the new code
            for ws, q in list(self.players.items()):
                if q.role == "learner":
                    await self.send(ws, {"type": "restart_client"})
        elif kind == "cpu_brain":
            await self.notice_teacher("Kart Lab's computer karts drive themselves (easy, medium, expert): there is "
                                      "no demo brain to upload. Set their level in Controls.")
        elif kind == "design_for_all":  # every learner gets exactly this kart (and anyone who joins later)
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
        elif kind == "design_for":  # the teacher changes a learner's kart for them
            p = next((q for q in self.learners() if q.name == m.get("learner")), None)
            if p is None:
                await self.notice_teacher("That learner isn't connected.")
                return
            await self.build_for(p, m.get("design", {}) if isinstance(m.get("design"), dict) else {})
            await self.broadcast_lesson()
        elif kind == "tournament":  # a league of races for everyone with a kart
            if m.get("start"):
                names = [p.name for p in self.karts_wanted()]
                if len(names) < 2:
                    await self.notice_teacher("A tournament needs at least 2 karts (learners, or your own kart).")
                    return
                try:
                    races = int(m.get("races", m.get("live", 3)))
                except (TypeError, ValueError, OverflowError):
                    races = 3
                self.tournament = Tournament(names, races=races)
                L["mode"] = "race"
                L["designs_locked"] = True
                self.rebuild()
                self.race.events.append((self.race.tick, f"THE GRAND PRIX BEGINS! {self.tournament.label()}: "
                                                         f"press Enter to start it"))
            else:
                self.tournament = None
                self.next_race_at = None
                L["designs_locked"] = False
                self.rebuild()
            await self.broadcast_lesson()
        elif kind == "lesson":  # partial update from the teacher's screen
            await self.update_lesson(m.get("lesson", {}) if isinstance(m.get("lesson"), dict) else {})
        elif kind == "start":
            if L.get("mode", "practice") == "practice":
                L["mode"] = "race"  # (starting a race ends practice: the track closes until GO)
                self.rebuild()
            else:
                self.race.start()
            self.race_recorded = False
            self.race_version = None
            await self.broadcast_lesson()
        elif kind in ("grid", "restart"):
            self.rebuild()
            self.race.to_grid()
            if self.race.practice:
                self.race.start()
                self.race.go_tick = self.race.tick
            self.race_version = None
            await self.broadcast_lesson()
        elif kind == "pause":
            self.paused = not self.paused
            self.race.events.append((self.race.tick, "PAUSED" if self.paused else "GO!"))
            self.race_version = None
        elif kind == "save_lesson":  # every control, for this mission: used whenever the mission is chosen
            self.save_mission_settings()
            try:
                with open(os.path.join(DATA, "lesson_saved.json"), "w") as f:
                    json.dump(L, f, indent=2)
            except OSError:
                pass
            self.race.events.append((self.race.tick, f"Mission {L.get('lesson_number', 1)} settings saved"))
            await self.broadcast_lesson()
        elif kind == "restore_lesson":  # back to what was saved for this mission (or the mission's own defaults)
            n = L.get("lesson_number", 1)
            self.teaching.apply_lesson(n)
            self.rebuild()
            self.race.events.append((self.race.tick, f"Mission {n} settings restored"))
            await self.broadcast_lesson()

    async def update_lesson(self, update):
        L = self.lesson
        rebuild = False
        if update.get("cpu_level") in cpu_brains.LEVELS:  # straight away, no restart
            L["cpu_level"] = update["cpu_level"]
            for kid in self.cpu_levels:
                self.cpu_levels[kid] = update["cpu_level"]
            self.race.events.append((self.race.tick, f"Computer karts: {update['cpu_level']}"))
        if isinstance(update.get("limits"), dict):  # the learners' ranges: kept between sessions
            L["limits"] = sim.clean_limits(update["limits"], L["limits"])
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(LIMITS_FILE, "w", encoding="utf-8") as f:
                    json.dump(L["limits"], f)
            except OSError:
                pass
            await self.fit_learners()
        if isinstance(update.get("ai_card_note"), str):  # the teacher's words on the learners' AI request card
            note = "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in update["ai_card_note"])
            L["ai_card_note"] = " ".join(note.split())[:300]
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(CARD_NOTE_FILE, "w", encoding="utf-8") as f:
                    json.dump({"note": L["ai_card_note"]}, f)
            except OSError:
                pass
        if "gfx_max" in update:  # CHANGE 139: the best graphics a learner may draw, kept between sessions
            L["gfx_max"] = gfx_tiers.class_max(update["gfx_max"])
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(GFX_MAX_FILE, "w", encoding="utf-8") as f:
                    json.dump({"gfx_max": L["gfx_max"]}, f)
            except OSError:
                pass
        if isinstance(update.get("mods_in_vote"), dict):  # which mods learners see and vote on
            in_vote = {k: bool(v) for k, v in update["mods_in_vote"].items() if k in sim.USER_MODS}
            L["mods_in_vote"] = {**L.get("mods_in_vote", {}), **in_vote}
            for k, v in in_vote.items():
                if not v:
                    self.mod_votes.pop(k, None)
        if isinstance(update.get("arena_in_vote"), dict):  # ...and which of the track's switches
            in_vote = {k: bool(v) for k, v in update["arena_in_vote"].items() if k in STAGE_ITEMS}
            L["arena_in_vote"] = {**L.get("arena_in_vote", {}), **in_vote}
            for k, v in in_vote.items():
                if not v:
                    self.arena_votes.pop(k, None)
        if isinstance(update.get("user_mods"), dict):  # straight away: the race reads the switches
            switched = {k: bool(v) for k, v in update["user_mods"].items() if k in sim.USER_MODS}
            L["user_mods"] = {**L.get("user_mods", {}), **switched}
            self.race.set_user_mods(L["user_mods"])
            self.roster_version += 1
            if switched:
                self.race.events.append((self.race.tick, ", ".join(f"{sim.USER_MODS[k][0]} {'on' if v else 'off'}"
                                                                   for k, v in switched.items())))
        if update.get("track") in kart_track.TRACKS and update["track"] != L["track"]:
            L["track"] = update["track"]
            self.track = kart_track.load(L["track"])
            self.track_name = kart_track.TRACKS[L["track"]]["name"]
            rebuild = True
        for key, lo, hi in (("laps", 1, 9), ("cpu_karts", 0, MAX_KARTS - 1)):
            if key in update:
                try:
                    v = max(lo, min(hi, int(update[key])))
                except (TypeError, ValueError, OverflowError):
                    continue
                rebuild |= v != L[key]
                L[key] = v
                if key == "cpu_karts" and v > 0 and not L["hazards"].get("cpu_karts"):
                    L["hazards"]["cpu_karts"] = True  # (asking for computer karts puts them on the grid)
        for key in ("teacher_kart", "designs_locked"):
            if key in update:
                rebuild |= key == "teacher_kart" and bool(update[key]) != bool(L.get(key))
                L[key] = bool(update[key])
        if isinstance(update.get("items"), dict):  # (CHANGE 159) the power-ups switched on and off, live
            was = self.items_allowed()
            L["items"] = {n: bool(update["items"].get(n, was[n])) for n in kart_items.ITEMS}
            if L["items"] != was and self.race.items is not None:
                self.race.items.set_allowed(L["items"])
                on = [n for n in kart_items.ITEMS if L["items"][n]]
                self.race.events.append((self.race.tick, "Power-ups: " + (", ".join(on) if on else "none")))
        if update.get("time") in TIMES and update["time"] != L.get("time", "day"):  # (CHANGE 172) live: every
            L["time"] = update["time"]  # window and page relights the race
            self.race.events.append((self.race.tick, {"day": "Daytime", "dusk": "Dusk: lights on",
                                                      "night": "Night falls: lights on"}[L["time"]]))
        if "damage" in update and bool(update["damage"]) != bool(L.get("damage", True)):  # (CHANGE 158) live
            L["damage"] = bool(update["damage"])
            self.race.set_damage(L["damage"])
            self.race.events.append((self.race.tick, "Damage on" if L["damage"] else "Damage off: every kart mended"))
        if update.get("mode") in ("practice", "race", "battle"):
            mode = "race" if update["mode"] == "battle" else update["mode"]
            rebuild |= mode != L["mode"]
            L["mode"] = mode
        if "show_missions" in update:  # every learner's Mission tab opens and the game pauses
            L["show_missions"] = self.paused = bool(update["show_missions"])
            self.race.events.append((self.race.tick, "PAUSED: look at your Mission tab" if self.paused else "GO!"))
        for key in ("hazards", "tools"):
            for k, v in (update.get(key, {}) if isinstance(update.get(key), dict) else {}).items():
                if key == "hazards" and k not in km.NO_HAZARDS:
                    continue
                if key == "tools" and k not in L["tools"]:
                    continue
                v = bool(v)
                rebuild |= key == "hazards" and k == "cpu_karts" and v != L[key].get(k)
                L[key][k] = v
        L["brains"] = bool(L["tools"].get("brains"))
        if "brains" in update:  # (a window that switches brains here)
            L["tools"]["brains"] = L["brains"] = bool(update["brains"])
        if isinstance(update.get("sound"), dict):
            L["sound"] = rw_sound.sound_settings(L.get("sound"), update["sound"])
        if rebuild:
            if self.tournament and L["mode"] == "practice":
                self.tournament = None  # practice ends a tournament
            self.rebuild()
        self.race_version = None
        await self.broadcast_lesson()  # (the lesson message carries the track: the windows redraw it if it changed)

    def carry_lesson(self):
        """Save the lesson for the server that starts after a restart for code changes."""
        try:
            os.makedirs(DATA, exist_ok=True)
            with open(os.path.join(DATA, "lesson_carried.json"), "w") as f:
                json.dump(self.lesson, f, indent=2)
        except OSError:
            pass

    def reload_mods(self, written):
        """Use mod files that an approved AI change just updated."""
        try:
            if "mods/rules.py" in written:
                sim.RULES.update(kart_mods.load_rules())
            if "mods/track.py" in written:
                t = kart_mods.load_track()
                self.lesson.update(track=t["track"], laps=t["laps"], cpu_level=t["cpu_level"])
                self.track_name = t["name"]
                self.track = kart_track.load(t["track"])
        except kart_mods.ModError as e:
            print("Mods not used:", e, flush=True)
        for p in self.learners():
            if f"mods/karts/{kart_teaching.slug(p.name)}.py" in written:
                p.design = self.teaching.load_saved_design(p.name) or p.design
        self.rebuild()
        self.race.events.append((self.race.tick, "An approved AI change is now in the game"))
        self.lesson_dirty = True

    def user_mods_msg(self):
        """For everyone's Mods tab: who made each mod, who'd like it switched on, and whose group is in."""
        here = {p.name for p in self.learners()} | set(self.group)
        return {"makers": {k: v for k, v in self.mod_makers.items() if k in sim.USER_MODS},
                "votes": {k: v for k, v in self.mod_votes.items() if v and k in sim.USER_MODS},
                "arena_votes": {k: v for k, v in self.arena_votes.items() if v},
                "here": sorted(here)}

    async def broadcast_lesson(self):
        msg = {"type": "lesson", "lesson": self.lesson, "mods": self.user_mods_msg(),
               "track": kart_track.TRACKS[self.lesson["track"]],
               "class": [{"name": p.name, "role": p.role, "design": p.design} for p in self.players.values()],
               "tournament": self.tournament.summary() if self.tournament else None}
        for ws in list(self.players):
            await self.send(ws, msg)

    async def delete_learner(self, username):
        name = kart_profiles.clean_name(username)
        for ws, q in list(self.players.items()):
            if q.role == "learner" and kart_profiles.slug(q.name) == kart_profiles.slug(name):
                del self.players[ws]
                await self.outboxes.close(ws, 4007, "Your account has been deleted by the teacher.")
        text = self.teaching.delete_learner(name)
        gone = kart_profiles.slug(name)
        if any(v and kart_profiles.slug(v) == gone for v in self.mod_makers.values()):  # their mods stay, unnamed
            self.mod_makers = {k: "" if kart_profiles.slug(v) == gone else v for k, v in self.mod_makers.items()}
            ai_pipeline.save_user_mod_makers(self.mod_makers)
        for votes in (self.mod_votes, self.arena_votes):
            for k in votes:
                votes[k] = [n for n in votes[k] if kart_profiles.slug(n) != gone]
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
            if next_step < now - 4 * sim.STEP:  # (a long stall: don't try to catch up; whole steps are skipped, so the
                skip = (now - next_step) // sim.STEP  # steps' stamps stay 1/60 s apart: CHANGE 155)
                next_step += skip * sim.STEP
                self.ticks.skip(int(skip))
            await asyncio.sleep(max(0.0, next_step - now))
            start = time.perf_counter()
            if not self.paused:
                self.step()
            self.step_ms = step_ms(next_step)
            steps += 1
            if steps % 30 == 0:  # twice a second: missions that are checked over time, and the league
                self.teaching.tick(self.race.tick * sim.STEP)  # (seconds: a brain's running time is in seconds)
                for p in self.seats.expired():  # (CHANGE 164) not back in time: their kart goes
                    print(f"- {p.name} didn't come back: their kart has gone", flush=True)
                    self.rebuild()
                    await self.broadcast_lesson()
                if self.check_race():
                    await self.broadcast_lesson()
                if self.lesson_dirty:
                    self.lesson_dirty = False
                    await self.broadcast_lesson()
            if self.next_race_at is not None and time.perf_counter() > self.next_race_at:
                self.next_race_at = None
                self.rebuild()
                self.race.start()
                self.race_version = None
                await self.broadcast_lesson()
            self.ticks.step(time.perf_counter() - start, max(0.0, start - next_step))
            self.watchdog.ping()
            if self.ticks.due() and self.players:  # (the log's line every 10 s: engine.tick_stats, CHANGE 160)
                print(self.ticks.report(self.outboxes, {ws: p.name for ws, p in self.players.items()}), flush=True)

    def step(self):
        race = self.race
        inputs = {}
        ask_brains = race.tick % BRAIN_EVERY == 0
        for p in self.players.values():
            if p.kart is None or p.kart not in race.karts:
                continue
            keys = p.inputs.pop_for_tick()
            p.ctrl_seq = p.inputs.applied
            brain = p.unit.brain if p.unit is not None else None
            if brain is not None:
                if ask_brains:
                    p.last_brain = brain(race.karts[p.kart], race)
                inputs[p.kart] = (p.last_brain[0], p.last_brain[1], p.last_brain[2] | (keys[2] & sim.RESPAWN))
            else:
                inputs[p.kart] = keys
        for p in self.seats.players():  # (CHANGE 164) a dropped learner's kart races on, driven by the computer
            if p.kart in race.karts:
                inputs[p.kart] = cpu_brains.drive("easy", race.karts[p.kart], race)
        for kid, level in self.cpu_levels.items():
            if kid in race.karts:
                th, st, bt = cpu_brains.drive(level, race.karts[kid], race)
                inputs[kid] = (th, st, bt | kart_items.cpu_use(race.karts[kid], race))  # (CHANGE 159: its item)
        race.step_all(inputs)

    def check_race(self):
        """A race in a league has finished: score it and start the next one in a moment (or crown the champion)."""
        if self.race.phase != sim.FLAGS_OVER or self.race_recorded or self.race.practice:
            return False
        self.race_recorded = True
        if not self.tournament or self.tournament.champion:
            return False
        order = [self.race.designs[k]["name"] for k in self.race.places()]
        over = self.tournament.record(order)
        if over:
            self.race.events.append((self.race.tick, f"{self.tournament.champion} IS THE CHAMPION!"))
            self.lesson["designs_locked"] = False
        else:
            self.race.events.append((self.race.tick, f"Next: {self.tournament.label()}"))
            self.next_race_at = time.perf_counter() + NEXT_RACE_AFTER
        self.race_version = None
        return True

    async def send_loop(self):
        sent_version, last_race, next_send, ticks = {}, 0.0, time.perf_counter(), 0
        while True:
            next_send += SEND_RATE
            now = time.perf_counter()
            if next_send < now - 4 * SEND_RATE:
                next_send = now
            await asyncio.sleep(max(0.0, next_send - now))
            if not self.players:
                continue
            ticks += 1
            if ticks % 30 == 0:  # once a second: missions and the teacher's outcome grid
                await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
            self.snap_seq = (self.snap_seq + 1) & 0xFFFF
            sm = getattr(self, "step_ms", None) or server_ms()
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
            # (CHANGE 159) the power-ups: every send while shots or slicks are out, else when the boxes change and
            # once a second (a window just joined)
            items, items_msg = self.race.items, None
            if items is not None and (items.shots or items.slicks or items.changed or items.unsent or ticks % 30 == 0):
                items_msg = json.dumps({"type": "items", "sm": sm, **items.state()}, separators=(",", ":"))
            for ws, p in list(self.players.items()):
                if backed_up(ws):
                    continue
                if sent_version.get(ws) != self.roster_version:
                    roster = roster or json.dumps(self.roster(), separators=(",", ":"))
                    await self.send(ws, roster, "roster")
                    sent_version[ws] = self.roster_version
                if race_msg:
                    await self.send(ws, race_msg, "race")
                # that window's own frame: its last input applied, and how many of its inputs wait (for its lead)
                flags = self.race.phase | (min(15, p.inputs.depth()) << 4)
                frame = wire.pack_snapshot(SCHEMA, sm, self.snap_seq, entities, ack=p.ctrl_seq or 0, flags=flags)
                await self.send(ws, frame, "state")
                if items_msg:
                    await self.send(ws, items_msg, "items")
            await asyncio.sleep(0)

    async def watch_desk(self):
        """On the class server: follow the club desk. When a group is launched for this game, start its lesson and
        let only its learners in; when it's stopped, the learners' windows are closed. Requests in the desk's inbox
        (delete a learner's data) are carried out. Checked every 2 seconds."""
        if not LIVE_FILE:
            return
        seen, presence = None, {}
        report_file = os.path.join(os.path.dirname(LIVE_FILE), "reports", f"{GAME_ID}.json")
        while True:
            live = read_live()
            mine = live if live and live.get("game") == GAME_ID else None
            key = mine["id"] if mine else None
            if key == seen and mine and sorted(mine.get("learners", [])) != self.group:
                # the same session, but the teacher has added someone or taken someone out (the desk's This session, the
                # live group's learners, or the Accounts tab): who was taken out goes back to the lobby (CHANGE 141)
                self.group = sorted(mine.get("learners", []))
                for p in self.seats.players():
                    if p.name not in self.group:
                        self.seats.take(kart_profiles.slug(p.name))
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
                self.seats.clear()  # (CHANGE 164: a new session, or none: nobody's kart is kept)
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in allowed:
                        self.players.pop(ws, None)
                        await self.outboxes.close(ws, 4009, "The session has ended." if not mine else
                                                  "You aren't in this group.")
                if mine:
                    self.teaching.apply_lesson(int(mine.get("lesson", 1)))
                    self.rebuild()
                    self.race.events.append((self.race.tick, f"Session started: {mine.get('group', '')}, "
                                                             f"lesson {mine.get('lesson', 1)}"))
                else:
                    self.rebuild()
                    self.race.events.append((self.race.tick, "The session has ended"))
                await self.broadcast_lesson()
            if mine:  # the session so far, for the desk (who is here, what they've completed, AI cards)
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
        """On the class server: a live code update installed for this game (robotlab-live) is offered to the teacher,
        who restarts the class when they have warned it (see restart_server). Checked every 10 seconds."""
        pointer = os.environ.get("CLUBCODERS_LIVE_POINTER")
        self.live_ready = None
        failed, told = os.environ.get("CLUBCODERS_LIVE_FAILED") or None, set()  # (run-class.sh: CHANGE 168)
        while pointer:
            try:
                with open(pointer, encoding="utf-8") as f:
                    wanted = f.read().strip() or None
            except OSError:
                wanted = None
            ready = wanted if wanted and wanted != kart_version.CODE else None
            if ready and ready == failed:  # (tried as this server started, and not ready: not offered again; the
                ready = None              # teacher is told, once each time they log in)
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


def client_address(ws):
    """The computer connecting. Behind Caddy (on this same machine) that is in X-Forwarded-For."""
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
    """The class server won't start with missing, demo or short codes. Returns a problem, or None."""
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
    """Windows wakes a sleeping loop only every 15.6 ms unless asked for a finer clock."""
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
    ap.add_argument("--port", type=int, default=8782)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--class-server", action="store_true", help="the real class server: real codes required")
    ap.add_argument("--lesson", help="start from saved lesson settings (JSON)")
    ap.add_argument("--track", default=None, choices=list(kart_track.TRACKS))
    ap.add_argument("--cpu", type=int, default=None, help="computer karts")
    ap.add_argument("--level", default=None, choices=list(cpu_brains.LEVELS))
    ap.add_argument("--laps", type=int, default=None)
    ap.add_argument("--autostart", type=float, default=None, help="seconds after the first window joins, start a race")
    args = ap.parse_args()
    CLASS_SERVER = args.class_server
    local_only = args.bind in ("127.0.0.1", "localhost", "::1")
    if CLASS_SERVER or not local_only:
        problem = check_class_server_codes()
        if problem:
            raise SystemExit("Kart Lab server not started: " + problem)
    OPEN_SIGNUP = os.environ.get("KARTLAB_OPEN_SIGNUP") == "1" or not CLASS_SERVER
    server = KartServer(args.lesson)
    overrides = {k: v for k, v in (("track", args.track), ("cpu_karts", args.cpu), ("cpu_level", args.level),
                                   ("laps", args.laps)) if v is not None}
    if overrides:
        if overrides.get("cpu_karts"):
            server.lesson["hazards"]["cpu_karts"] = True
        server.lesson.update(overrides)
        server.rebuild()
    if CLASS_SERVER:  # (the club desk tells the Club Coders app which code this class runs)
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(kart_version.CODE)

    async def autostart():
        while not server.players:
            await asyncio.sleep(0.2)
        await asyncio.sleep(args.autostart)
        server.lesson["mode"] = "race"
        server.rebuild()
        server.race.start()
        server.race_version = None
        await server.broadcast_lesson()

    tasks = [server.physics_loop(), server.send_loop(), server.watch_live(), server.watch_desk()] + \
        ([autostart()] if args.autostart is not None else [])
    async with websockets.serve(server.handler, args.bind, args.port, compression=None, ping_interval=5,
                                ping_timeout=10, max_queue=8):
        tick_stats.start_up()  # (CHANGE 160)
        print(f"Kart Lab {'class' if CLASS_SERVER else 'laptop test'} server {kart_version.VERSION} on "
              f"{args.bind}:{args.port}, track {server.lesson['track']}."
              + ("" if CLASS_SERVER else f" Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}. A new username "
                                         f"makes a profile."), flush=True)
        await lifecycle.run(tasks, server.outboxes, server.players, server.teaching.save)  # (1012 at the end)


if __name__ == "__main__":
    asyncio.run(main())
