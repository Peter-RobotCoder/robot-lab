"""Robot Lab server: one arena for up to 4 learners and the teacher.

The teacher decides what learners can see and change (the "lesson"), switches hazards on and off,
and runs practice (no damage) or battles. Learners design their robot in their own window;
the server checks every design and rebuilds their robot.

Learners log in with a username and password, so if they disconnect they can log back in to the same robot,
missions and settings.

Two ways to run it:
  python lab_server.py                  laptop test server: only this computer can join (ws://127.0.0.1:8780),
                                        demo codes CLUB42 / TEACH99, and a new username makes a new profile.
  python lab_server.py --class-server   the real class server (on the VPS, behind Caddy's wss://). It won't start
                                        without real codes in JOIN_CODE and TEACHER_CODE (from /etc/robotlab.env),
                                        the teacher makes every learner's account, and windows must run this
                                        server's version of the game.
"""
import argparse
import asyncio
import copy
import datetime
import hmac
import ipaddress
import json
import os
import re
import time

import websockets

import ai_pipeline
import cpu_brains
import lab_brain
import club_ticket
import lab_profiles
import lab_sim as sim
import lab_version
import lab_teaching
import rw_mods
import rw_sound

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
CLASS_SERVER = False   # set by --class-server in main()
OPEN_SIGNUP = False    # a new username makes a profile (laptop test servers only, unless ROBOTLAB_OPEN_SIGNUP=1)
BAD_LOGINS = lab_profiles.RateLimit(10)  # wrong codes or passwords: 10 a minute per computer
GAME_ID = "robotlab"  # (the club desk's name for this game)
# the club desk (club-coders/desk): run-class.sh sets these on the class server
TICKET_KEY = os.environ.get("CLUBCODERS_TICKET_KEY")
LIVE_FILE = os.environ.get("CLUBCODERS_LIVE_FILE")
DESK_INBOX = os.environ.get("CLUBCODERS_DESK_INBOX")


def read_live():
    """The launched group, from the club desk: {"id", "group", "game", "lesson", "learners"} or None."""
    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            live = json.load(f)
        return live if isinstance(live, dict) and live.get("id") else None
    except (OSError, ValueError, TypeError):
        return None


DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def desk_json(name, default):
    """One of the club desk's own files (next to its live session's file): its groups, its learners."""
    try:
        with open(os.path.join(os.path.dirname(LIVE_FILE), name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return default


def next_group(groups, live_group=None, now=None):
    """The group whose proposed time (a day and a time each week, "Tuesday 16:00") comes next after now, leaving
    out the one that is live: (its name, its group) or (None, None). Only this game's groups count."""
    now = now or datetime.datetime.now()
    best = (None, None, None)
    for name, g in (groups or {}).items():
        when = str((g or {}).get("time") or "").lower().split()
        if name == live_group or g.get("game") != GAME_ID or len(when) != 2 or when[0] not in DAYS:
            continue
        try:
            hour, minute = (int(v) for v in when[1].split(":"))
        except ValueError:
            continue
        days = (DAYS.index(when[0]) - now.weekday()) % 7
        start = now.replace(hour=hour % 24, minute=minute % 60, second=0, microsecond=0) + datetime.timedelta(days=days)
        if start <= now:
            start += datetime.timedelta(days=7)
        if best[0] is None or start < best[0]:
            best = (start, name, g)
    return best[1], best[2]


BRAIN_UPLOAD_GAP = 3.0                   # seconds between one learner's brain uploads
MAX_LEARNERS = 4
INTRO_SECONDS = 8.0  # the countdown before a battle: the arena's name, who is fighting, then 3, 2, 1, ACTIVATE!
SEND_RATE = 1 / 20
HERE = os.path.dirname(os.path.abspath(__file__))
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230)]

# What learners can see and change. The teacher edits this live from the teacher screen.
WEEK1_LESSON = {
    "lesson_number": 1,            # which of the 5 lessons: sets missions, tools and hazards
    "mode": "practice",            # practice = no damage, robots come back; battle = real fight
    "time_limit": 120,             # seconds per battle
    "cpu_robots": 1,               # computer-driven sparring robots
    "cpu_level": cpu_brains.START_LEVEL,  # their brains: none (still, as every game starts), empty (the teacher's
                                   # demo brain), easy, medium, expert
    "teacher_robot": True,
    "designs_locked": False,       # stop design changes (e.g. during a battle)
    "real_damage": False,          # each part (wheels, weapon, armour, body) has hit points and comes off at zero
    "user_mods": {},               # features learners asked for (lab_sim.USER_MODS): the teacher switches them on
    "flame_pit_cm": sim.FLAME_PIT_CM,  # the Flame pit user mod: how high its flames stand with nobody in (cm)
    "hazards": {"pit": True, "floor_flipper": False, "saws": False, "spikes": False, "house_robots": []},
    "sound": dict(rw_sound.DEFAULT_SOUND),  # what everyone hears: music, crowd, arena hum and hit sounds
    "limits": sim.default_limits(),  # the learners' ranges for every setting and point (the teacher's Limits tab)
    "ai_card_note": "",            # the teacher's own instructions, shown on every learner's AI request card
    "tools": {                     # the learner's garage: what is shown and changeable
        "points_table": True,
        "forward_speed": True, "reverse_speed": True, "turn_speed": True, "acceleration": True, "size": True,
        "choose_weapon": False, "weapons": ["wedge", "spinner", "drum", "hammer"],
        "name_and_colour": True, "code_view": True, "stats_readout": True, "weapon_toggle": True,
        "house_robots": False,     # learners may drive a Resident Robot
    },
}


HAZARD_WORDS = {"pit": "Drop zone", "floor_flipper": "Floor flipper", "saws": "Floor saws", "spikes": "Wall spikes"}
ARENA_ITEMS = tuple(HAZARD_WORDS) + tuple(sim.HOUSE_BY_NAME)  # what learners can vote for: hazards, Resident Robots
SOUND_FILE = os.path.join(lab_teaching.DATA, "sound_saved.json")  # the teacher's sound settings, kept between sessions


LIMITS_FILE = os.path.join(lab_teaching.DATA, "limits_saved.json")  # ...and the learners' ranges, kept the same way
CARD_NOTE_FILE = os.path.join(lab_teaching.DATA, "card_note_saved.json")  # ...and the teacher's words on the AI card
CPU_FILE = os.path.join(lab_teaching.DATA, "computer_robot.json")  # ...and the first computer robot, as the teacher set it up
CPU_NAME = "Computer robot"  # the first computer robot's name in the teacher's Learner view (its robot is Sparky 1)


def load_saved(path):
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def load_sound():
    return load_saved(SOUND_FILE)


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = sim.default_design(name if role == "learner" else "Teacher Bot", colour,
                                         "wedge" if role == "learner" else "spinner")
        self.robot = None
        self.start_colour = list(colour)
        self.default = copy.deepcopy(self.design)  # the starting robot (the code panel's RESET CODE goes back to it)
        self.profile = None


class LabServer:
    def __init__(self, lesson_file=None):
        self.lesson = copy.deepcopy(WEEK1_LESSON)
        if lesson_file and os.path.exists(lesson_file):
            with open(lesson_file) as f:
                self.lesson.update(json.load(f))
        self.lesson["cpu_level"] = cpu_brains.START_LEVEL  # (every start: nothing attacks until the teacher says)
        self.lesson["sound"] = rw_sound.sound_settings(self.lesson.get("sound"), load_sound())  # as last set
        self.lesson["limits"] = sim.clean_limits(load_saved(LIMITS_FILE), sim.clean_limits(self.lesson.get("limits")))
        self.lesson["ai_card_note"] = str(load_saved(CARD_NOTE_FILE).get("note", ""))[:300]
        self.intro_started = None  # the countdown before a battle is running since this moment (time.monotonic)
        self.players = {}        # websocket -> Player
        self.teacher_design = sim.default_design("Teacher Bot", (180, 90, 230), "spinner")
        self.paused, self.fight_started = False, 0.0
        self.roster_version = 0
        self.mod_makers = ai_pipeline.user_mod_makers()  # who made each user mod: their name goes in front of it
        self.mod_votes = {}      # user mod -> the learners who'd like it switched on (this session)
        self.arena_votes = {}    # the same for the arena's hazards and Resident Robots (see ARENA_ITEMS)
        self.group = []          # the launched group's learners (from the club desk), here yet or not
        self.warnings = []       # for the teacher: learners who changed, in the code, something outside the lesson
        self.session = {"desk": bool(LIVE_FILE)}  # for the teacher's Accounts tab: who is in this session, and the next
        # The first computer robot is the teacher's to set up, as a learner sets up theirs (the Learner view): its
        # design and its own brain are kept between sessions. Its autopilot is off at every start: until the teacher
        # switches it on, the robot follows Computer brains in Controls like the others (so it starts still).
        self.cpu = Player(None, "computer", CPU_NAME, (150, 150, 160))
        self.cpu.design = sim.default_design("Sparky 1", (150, 150, 160), "wedge")  # (the computer robot as it comes)
        self.cpu.default = copy.deepcopy(self.cpu.design)
        self.cpu_source, self.cpu_own_brain, self.cpu_autopilot = "", None, False
        saved = load_saved(CPU_FILE)
        if isinstance(saved.get("design"), dict) and not sim.check_design(saved["design"], sim.full_limits()) \
                and rw_mods.colour_ok(saved["design"].get("colour")):
            self.cpu.design = saved["design"]
        if saved.get("brain"):
            self.cpu_source = str(saved["brain"])[:20000]
            self.cpu_own_brain = self.make_demo_brain(self.cpu_source)[0]
        self.arena = None
        self.look = {}
        try:  # the mod rules and arena look (hazards come from the lesson)
            sim.RULES.update(rw_mods.load_rules())
            self.look = rw_mods.load_arena()["look"]
        except rw_mods.ModError as e:
            print("Mods not used:", e)
        self.teaching = lab_teaching.Teaching(self)
        self.demo_brain = None  # the teacher's demo brain for "empty" computer robots (brains/demo_cpu.py)
        demo = os.path.join(HERE, "brains", "demo_cpu.py")
        if os.path.exists(demo):
            with open(demo, encoding="utf-8") as f:
                self.load_demo_brain(f.read())
        if not lesson_file:
            self.teaching.apply_lesson(1)
        self.rebuild_arena()

    # ---------- the arena and who is in it ----------
    def rebuild_arena(self, intro=False):
        """New arena (hazards may have changed), then put everyone's robot back in.
        intro: a new battle is starting, so it opens with the countdown (robots can't move or fire until it ends)."""
        self.arena = sim.Arena(hazards=self.lesson["hazards"], user_mods=self.lesson.get("user_mods"))
        self.arena.practice = self.lesson["mode"] == "practice"
        if self.arena.practice:
            self.intro_started = None
        elif intro:
            self.intro_started = time.monotonic()
        self.arena.frozen = self.intro_started is not None
        self.arena.real_damage = bool(self.lesson.get("real_damage"))
        self.arena.flame_pit_cm = self.lesson.get("flame_pit_cm", sim.FLAME_PIT_CM)
        start = 0
        for p in self.learners():
            p.robot = self.arena.add_robot(p.design, brain=None, owner=p.name, start=start)
            self.teaching.attach(p)  # their uploaded brain drives it if autopilot is on
            start += 1
        t = self.teacher()
        if self.lesson["teacher_robot"]:
            owner = t.name if t else "Teacher (away)"  # (away: the computer drives it, like its own robots)
            r = self.arena.add_robot(t.design if t else self.teacher_design, brain=None if t else self.cpu_brain(),
                                     owner=owner, start=start)
            if t:
                t.robot = r
            start += 1
        elif t:
            t.robot = None
        self.cpu.robot = None
        for i in range(self.lesson["cpu_robots"]):
            if start < len(sim.Arena.STARTS):
                if i == 0:  # (the one the teacher sets up in the Learner view)
                    self.cpu.robot = self.arena.add_robot(self.cpu.design, brain=self.cpu_robot_brain(),
                                                          owner="Computer", start=start)
                else:
                    cpu = sim.default_design(f"Sparky {i + 1}", (150, 150, 160),
                                             ["wedge", "spinner", "drum", "hammer"][i % 4])
                    self.arena.add_robot(cpu, brain=self.cpu_brain(), owner="Computer", start=start)
                start += 1
        self.fight_started = self.arena.time
        self.roster_version += 1
        if not self.arena.frozen:
            self.arena.events.append((self.arena.time, "Practice: no damage" if self.arena.practice else "FIGHT!"))

    def end_intro(self):
        """The countdown is over: ACTIVATE! The robots can move and fire, and the battle's clock starts."""
        self.intro_started, self.arena.frozen = None, False
        self.fight_started = self.arena.time
        self.arena.events.append((self.arena.time, "ACTIVATE!"))

    def cpu_brain(self):
        return cpu_brains.for_level(self.lesson.get("cpu_level", cpu_brains.START_LEVEL), self.demo_brain)

    def cpu_robot_brain(self):
        """What drives the first computer robot: its own brain while its autopilot is on, or the level's brain."""
        return self.cpu_own_brain if (self.cpu_own_brain and self.cpu_autopilot) else self.cpu_brain()

    def attach_cpu(self):
        if self.arena is not None and self.cpu.robot is not None and self.cpu.robot in self.arena.robots:
            self.cpu.robot.brain = self.cpu_robot_brain()

    def save_cpu(self):
        try:
            if self.cpu.design == self.cpu.default and not self.cpu_source:
                if os.path.exists(CPU_FILE):
                    os.remove(CPU_FILE)  # (as it comes: nothing to keep)
                return
            with open(CPU_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"design": self.cpu.design, "brain": self.cpu_source}, f)
            os.replace(CPU_FILE + ".tmp", CPU_FILE)
        except OSError:
            pass

    def rebuild_cpu_robot(self):
        """The first computer robot has a new design: it is built again on its start square."""
        r = self.cpu.robot
        if r is not None and r in self.arena.robots:
            start = r.start_index
            self.arena.remove_robot(r)
            self.cpu.robot = self.arena.add_robot(self.cpu.design, brain=self.cpu_robot_brain(), owner="Computer",
                                                  start=start)
            self.roster_version += 1

    async def cpu_robot_command(self, m):
        """The teacher sets up the first computer robot (the Learner view): its design, its own brain, its
        autopilot, or Reset (back to the computer robot as it comes: Sparky 1, with no brain of its own)."""
        t = self.teacher()
        text = None
        if "design" in m:
            d = m["design"] if isinstance(m["design"], dict) else {}
            new = copy.deepcopy(self.cpu.design)
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", str(d.get("name", new["name"])))[:16] or new["name"]
            for key in ("colour", "weapon", "points", "settings"):
                if key in d:
                    new[key] = d[key]
            if d.get("model") in sim.HOUSE_BY_NAME:
                new["model"], new["weapon"] = d["model"], sim.HOUSE_BY_NAME[d["model"]][0]
            else:
                new.pop("model", None)
            problems = sim.check_design(new, self.lesson["limits"])
            if not rw_mods.colour_ok(new.get("colour")):
                problems.append("colour must be three whole numbers from 0 to 255")
            if problems:
                text = "Not built: " + "; ".join(problems)
            else:
                self.cpu.design = new
                self.rebuild_cpu_robot()
                text = f"Built {new['name']} for the computer"
                self.arena.events.append((self.arena.time, "The teacher rebuilt the computer's robot"))
        elif m.get("reset"):
            old, self.cpu_own_brain = self.cpu_own_brain, None
            if old is not None:
                old.close()
            self.cpu.design, self.cpu_source, self.cpu_autopilot = copy.deepcopy(self.cpu.default), "", False
            self.rebuild_cpu_robot()
            text = "The computer's robot is back as it comes: Sparky 1, with no brain of its own"
        elif "brain" in m:  # (loaded off the game loop: checking a brain can take a moment)
            source = str(m["brain"])[:20000]
            brain, problem = await asyncio.to_thread(self.make_demo_brain, source)
            if brain is None:
                text = f"Brain problem: {problem}"
            else:
                old, self.cpu_own_brain, self.cpu_source = self.cpu_own_brain, brain, source
                if old is not None:
                    old.close()
                text = "Brain uploaded for the computer's robot. Switch its autopilot on to use it."
        elif "autopilot" in m:
            self.cpu_autopilot = bool(m["autopilot"]) and self.cpu_own_brain is not None
        self.attach_cpu()
        self.save_cpu()
        if t and text:
            await self.send(t.ws, {"type": "notice", "text": text})
        await self.broadcast_lesson()

    def cpu_driven(self):
        """The robots the computer drives: its own, and the teacher's while the teacher is away."""
        return [r for r in self.arena.robots if r.owner in ("Computer", "Teacher (away)")]

    @staticmethod
    def make_demo_brain(source):
        """The teacher's demo brain (written like a learner's): (brain, None), or (None, the problem)."""
        try:
            fn, fname = lab_brain.load_brain(source, "demo_cpu")
        except lab_brain.BrainError as e:
            return None, str(e)
        return lab_brain.Autopilot(fn, fname), None

    def use_demo_brain(self, brain):
        """Computer robots set to Empty now run this brain (the old one is closed)."""
        old, self.demo_brain = self.demo_brain, brain
        if old is not None and hasattr(old, "close"):
            old.close()
        if self.arena is not None:
            for r in self.cpu_driven():
                r.brain = self.cpu_brain()
            self.attach_cpu()

    def load_demo_brain(self, source):
        """Load and use a demo brain now. Returns a problem, or None if it loaded."""
        brain, problem = self.make_demo_brain(source)
        if brain is not None:
            self.use_demo_brain(brain)
        return problem

    def teaching_reattach(self):
        """(Robots keep their brains when the arena changes.)"""
        for p in self.learners():
            self.teaching.attach(p)

    def learners(self):
        return [p for p in self.players.values() if p.role == "learner"]

    def teacher(self):
        return next((p for p in self.players.values() if p.role == "teacher"), None)

    def limits_for(self, player):
        """The ranges a design is held to: the learners' (as the teacher has set them), or the widest ones for the
        teacher's own robot."""
        return sim.full_limits() if player.role == "teacher" else self.lesson["limits"]

    async def fit_learners(self):
        """The teacher has changed the limits: a learner's robot outside them is pulled back to the nearest
        allowed values (and rebuilt, and saved), and the learner is told."""
        limits = self.lesson["limits"]
        for p in self.learners():
            p.default = sim.fit_design(p.default, limits)
            new = sim.fit_design(p.design, limits)
            if new is p.design:
                continue
            p.design = new
            if p.robot is not None and p.robot in self.arena.robots:
                start = p.robot.start_index
                self.arena.remove_robot(p.robot)
                p.robot = self.arena.add_robot(new, brain=None, owner=p.name, start=start)
                self.teaching.attach(p)
                self.roster_version += 1
            self.teaching.save_design(p.name, new)
            await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new,
                                   "by_teacher": True})

    def outside_lesson(self, old, new):
        """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
        did it in the code): [[what, the old value, the new value], ...] for the teacher's Warnings tab."""
        tools, found = self.lesson["tools"], []
        if not tools.get("name_and_colour"):
            found += [[k, old[k], new[k]] for k in ("name", "colour") if old[k] != new[k]]
        if not tools.get("points_table"):
            found += [[k, old["points"][k], new["points"][k]] for k in sim.STATS if old["points"][k] != new["points"][k]]
        found += [[k, old["settings"][k], new["settings"][k]] for k in sim.SETTINGS
                  if not tools.get(k) and old["settings"][k] != new["settings"][k]]
        if old.get("model") != new.get("model"):
            if not tools.get("house_robots"):
                found.append(["model", old.get("model") or "none", new.get("model") or "none"])
        elif old["weapon"] != new["weapon"] and not (tools.get("choose_weapon") and new["weapon"] in tools.get("weapons", [])):
            found.append(["weapon", old["weapon"], new["weapon"]])
        return found

    async def warn_teacher(self, p=None, changes=None):
        """Add a warning (a learner got round the lesson in the code) and send the teacher the list. The learner is
        not told. Warnings last for the session."""
        if p is not None:
            self.warnings.append({"who": p.name, "time": time.strftime("%H:%M"), "changes": changes})
            del self.warnings[:-200]
        t = self.teacher()
        if t:
            await self.send(t.ws, {"type": "warnings", "list": self.warnings})

    def clean_design(self, player, d, everything=False):
        """Keep only what this lesson lets learners change; everything else stays as it was.
        everything: the design was sent from the code panel, where a learner can change what the garage hides
        (the limits still hold, and the teacher is told: see outside_lesson)."""
        tools, old = self.lesson["tools"], player.design
        new = copy.deepcopy(old)
        if player.role == "teacher" or everything:
            tools = {k: True for k in tools} | {"weapons": list(sim.WEAPONS)}
        if tools.get("name_and_colour"):
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", str(d.get("name", old["name"])))[:16] or old["name"]
            c = d.get("colour", old["colour"])
            if isinstance(c, list) and len(c) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in c):
                new["colour"] = c
        if tools.get("points_table") and isinstance(d.get("points"), dict):
            new["points"] = {k: d["points"].get(k, old["points"][k]) for k in sim.STATS}
        for k in sim.SETTINGS:
            if tools.get(k) and k in d.get("settings", {}):
                new["settings"][k] = d["settings"][k]
        if tools.get("choose_weapon") and d.get("weapon") in tools.get("weapons", []):
            new["weapon"] = d["weapon"]
        if tools.get("house_robots"):  # drive a Resident Robot instead of your own design
            if d.get("model") in sim.HOUSE_BY_NAME:
                new["model"] = d["model"]
            else:
                new.pop("model", None)
        if new.get("model"):
            new["weapon"] = sim.HOUSE_BY_NAME[new["model"]][0]
        elif new["weapon"] not in sim.WEAPONS:
            new["weapon"] = "wedge"
        return new

    # ---------- messages ----------
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
        if CLASS_SERVER and hello.get("version") != lab_version.VERSION:
            # (the window shows this, with a button to the download page. A close reason can be at most 123 bytes)
            await ws.close(4006, f"Out of date: download Club Coders {lab_version.VERSION} from "
                                 f"{lab_version.DOWNLOAD_PAGE}"[:120])
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
            if role == "learner":
                live = read_live()
                if not live or live.get("game") != GAME_ID or ticket["name"] not in live.get("learners", []):
                    await ws.close(4010, "Your group hasn't started yet: wait for your teacher.")
                    return
        else:
            role = code_role(str(hello.get("code", "")))
            if role == "learner" and TICKET_KEY:  # with the club desk on, learners come in only through it
                await ws.close(4010, "Log in through the Club Coders app: your teacher launches your group there.")
                return
        if role is None:
            BAD_LOGINS.failed(where)
            await ws.close(4001, "wrong class code")
            return
        if role == "teacher" and self.teacher():
            await ws.close(4002, "a teacher is already connected")
            return
        profile = None
        if role == "learner":  # username and password (slow on purpose, so it's checked away from the game loop)
            try:
                if ticket:
                    profile, is_new = lab_profiles.ticket_profile(ticket["name"]), False
                else:
                    profile, is_new = await asyncio.to_thread(lab_profiles.login, hello.get("name", ""),
                                                              hello.get("password", ""), OPEN_SIGNUP)
            except lab_profiles.LoginError as e:
                BAD_LOGINS.failed(where)
                await ws.close(4004, str(e)[:120])  # (a close reason can be at most 123 bytes)
                return
            name = profile["name"]
            old = next((q for q in self.learners() if lab_profiles.slug(q.name) == lab_profiles.slug(name)), None)
            if old is not None:  # logged in again (e.g. after a dropped connection): the old connection goes
                await old.ws.close(4005, "you logged in again somewhere else")
                self.players.pop(old.ws, None)
            if len(self.learners()) >= MAX_LEARNERS:
                await ws.close(4003, "the class is full (4 learners)")
                return
        else:
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(ticket["name"] if ticket else hello.get("name", "")))[:12] or "Teacher"
        colour = COLOURS[len(self.learners()) % len(COLOURS)] if role == "learner" else (180, 90, 230)
        p = Player(ws, role, name, colour)
        p.profile = profile
        if role == "teacher":
            p.design = self.teacher_design
        else:
            saved = self.teaching.load_saved_design(name)
            if saved:  # their robot from last time
                p.design = saved
            p.design = sim.fit_design(p.design, self.lesson["limits"])  # (inside the limits as they are today)
            p.default = sim.fit_design(p.default, self.lesson["limits"])
            self.teaching.login(p)  # their missions, reflections, brain and settings from last time
        self.players[ws] = p
        print(f"+ {name} ({role})")
        self.rebuild_arena()
        self.arena.events.append((self.arena.time, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "lesson": self.lesson,
                             "design": p.design, "default": p.default, "rules": self.rules(),
                             "prefs": (profile or {}).get("prefs", {}), "new_profile": bool(profile and is_new),
                             "code": lab_version.CODE,
                             "live_ready": getattr(self, "live_ready", None) if role == "teacher" else None})  # (see lab_version)
        await self.broadcast_lesson()
        await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
        if role == "teacher":
            await self.warn_teacher()
        try:
            async for raw in ws:
                await self.on_message(p, json.loads(raw))
        except (websockets.ConnectionClosed, json.JSONDecodeError):
            pass
        finally:
            if self.players.get(ws) is p:  # (not already replaced by the same learner logging in again)
                del self.players[ws]
                if role == "teacher":
                    self.teacher_design = p.design
                self.teaching.save()
                print(f"- {name} left")
                self.rebuild_arena()

    def rules(self):
        return {"stats": sim.STATS, "points_total": sim.POINTS_TOTAL, "stat_min": sim.STAT_MIN,
                "stat_max": sim.STAT_MAX, "settings": sim.SETTINGS, "weapons": sim.WEAPONS,
                "full": sim.full_limits(),  # the widest ranges: the teacher's own robot, and the Limits tab's sliders
                "house": {name: w for name, w, _, _ in sim.HOUSE_ROBOTS},
                "house_weapons": {"flame": "flame thrower: burns what's in front", "hammer": "a huge hammer",
                                  "chainsaw": "chainsaw arm: saws into what's in front",
                                  "vdisc": "vertical disc: throws robots into the air"}}

    async def deliver(self, replies):
        for ws, msg in replies:
            await self.send(ws, msg)

    async def on_message(self, p, m):
        kind = m.get("type")
        if kind == "brain" and p.role == "learner":  # loaded in its own process, away from the game loop
            await self.upload_brain(p, str(m.get("source", "")))
            return
        if kind in ("mod_vote", "arena_vote") and p.role == "learner":  # a tick on the learner's Mods tab
            votes, key, known = (self.mod_votes, m.get("mod"), sim.USER_MODS) if kind == "mod_vote" else \
                (self.arena_votes, m.get("item"), ARENA_ITEMS)
            if isinstance(key, str) and key in known:
                votes[key] = [n for n in votes.get(key, []) if n != p.name] + ([p.name] if m.get("on") else [])
                await self.broadcast_lesson()
            return
        if kind not in ("control", "ping", "design", "weapon", "design_for", "pit", "cpu_brain"):
            replies = self.teaching.on_message(p, m)
            if replies is not None:
                broadcast = replies == "broadcast" or "broadcast" in replies
                if replies != "broadcast":
                    await self.deliver([r for r in replies if r != "broadcast"])
                if broadcast:
                    await self.broadcast_lesson()
                    await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
                return
        if kind == "control" and p.robot is not None:  # (fire is Space, the one weapon key: see Robot.drive)
            p.robot.drive(max(-1.0, min(1.0, float(m["throttle"]))), max(-1.0, min(1.0, float(m["steer"]))),
                          bool(m["fire"]), p.role == "teacher" or bool(self.lesson["tools"]["weapon_toggle"]))
        elif kind == "ping":
            await self.send(p.ws, {"type": "pong", "t": m.get("t")})
        elif kind == "design":
            if self.lesson["designs_locked"] and p.role == "learner":
                await self.send(p.ws, {"type": "design_result", "ok": False, "problems": ["The teacher has locked designs for now."],
                                       "design": p.design})
                return
            # from the code panel a learner can change what the garage hides (while the lesson has the Code view)
            hack = bool(m.get("code")) and p.role == "learner" and bool(self.lesson["tools"].get("code_view"))
            new = self.clean_design(p, m.get("design", {}), everything=hack)
            problems = sim.check_design(new, self.limits_for(p))
            outside = self.outside_lesson(p.design, new) if hack and not problems else []
            if not problems:
                p.design = new
                if p.robot is not None and p.robot in self.arena.robots:  # rebuild at the same start square
                    start = p.robot.start_index
                    self.arena.remove_robot(p.robot)
                    p.robot = self.arena.add_robot(new, brain=None, owner=p.name, start=start)
                    self.teaching.attach(p)
                    self.roster_version += 1
                self.arena.events.append((self.arena.time, f"{p.name} rebuilt {new['name']}"))
            self.teaching.on_design(p, new, problems, not problems)
            if not problems and p.role == "learner":
                self.teaching.save_design(p.name, new)  # autosave: their robot is there next lesson
            await self.send(p.ws, {"type": "design_result", "ok": not problems, "problems": problems, "design": p.design})
            await self.deliver(self.teaching.teacher_update() + ([(p.ws, self.teaching.missions_msg(p))]
                                                                 if p.role == "learner" else []))
            if not problems:
                await self.broadcast_lesson()  # the teacher's class list shows the new design
            if outside:
                await self.warn_teacher(p, outside)
        elif p.role == "teacher":
            await self.teacher_command(m)

    async def upload_brain(self, p, source):
        now = time.monotonic()
        if now - getattr(p, "brain_at", -BRAIN_UPLOAD_GAP) < BRAIN_UPLOAD_GAP:
            await self.send(p.ws, {"type": "brain_result", "ok": False,
                                   "error": "wait a few seconds before uploading again"})
            return
        p.brain_at = now
        try:
            loaded = await asyncio.to_thread(lab_brain.load_brain, source, p.name)
        except lab_brain.BrainError as e:
            loaded = e
        if self.players.get(p.ws) is not p:  # they left while it loaded
            if not isinstance(loaded, Exception):
                loaded[0].close()
            return
        reply = self.teaching.upload_brain(p, source, loaded)
        await self.deliver([(p.ws, reply), (p.ws, self.teaching.missions_msg(p))] + self.teaching.teacher_update())

    async def teacher_command(self, m):
        kind = m.get("type")
        if kind == "delete_learner":  # everything the server keeps about them goes (they're disconnected first)
            await self.delete_learner(m.get("learner", ""))
            return
        if kind == "restart_server":  # load code changes (13 Robot Lab server.bat starts it again)
            self.teaching.save()
            for ws in list(self.players):
                await self.send(ws, {"type": "notice", "text": "The server is restarting to load changes: "
                                                               "you'll reconnect in a few seconds."})
            if CLASS_SERVER:  # the class server (a live update): everyone gets a warning, then it restarts
                for ws in list(self.players):
                    await self.send(ws, {"type": "notice", "text": "The game is updating: back in 10 seconds."})
                asyncio.get_running_loop().call_later(10, lambda: (self.teaching.save(), os._exit(3)))
                return
            print("Restarting to load code changes...")
            os._exit(3)
        if kind == "restart_clients":  # everyone's window reopens itself with the new code
            for ws, q in list(self.players.items()):
                if q.role == "learner":
                    await self.send(ws, {"type": "restart_client"})
            return
        if kind == "cpu_brain":  # the teacher's demo brain for "empty" computer robots
            # (loaded off the game loop: checking a brain can take a moment)
            brain, problem = await asyncio.to_thread(self.make_demo_brain, str(m.get("source", ""))[:20000])
            if brain is not None:
                self.use_demo_brain(brain)
            t = self.teacher()
            if t:
                await self.send(t.ws, {"type": "notice", "text": f"Demo brain problem: {problem}" if problem else
                                       "Demo brain uploaded: computer robots set to Empty now run it"})
            return
        if kind == "mod_makers":  # who made each user mod, from the teacher's laptop (its change history knows)
            makers = m.get("makers")
            for key, who in (makers.items() if isinstance(makers, dict) else ()):
                who = ai_pipeline.maker_name(who)
                if not (isinstance(key, str) and re.fullmatch(r"[a-z0-9_]{1,40}", key) and who):
                    continue
                if self.mod_makers.get(key) == "" and not m.get("new"):
                    continue  # that learner's data was deleted: only a newly kept or merged change names it again
                if key in self.mod_makers or len(self.mod_makers) < 500:
                    self.mod_makers[key] = who
            ai_pipeline.save_user_mod_makers(self.mod_makers)
            await self.broadcast_lesson()
            return
        if kind == "session_learner":  # the Accounts tab's "In this session" tick: the club desk lets them in or out
            t, live = self.teacher(), read_live() if LIVE_FILE else None
            name = lab_profiles.clean_name(str(m.get("learner", "")))
            if not live or live.get("game") != GAME_ID:
                text = "No session is live: launch a group from the Club Coders app first."
            elif not await self.ask_desk({"session_learner": name, "in": bool(m.get("in")), "live_id": live["id"],
                                          "game": GAME_ID}):
                text = "The club desk couldn't be asked: nothing was changed."
            else:
                text = f"{name} is {'being let into' if m.get('in') else 'being taken out of'} this session..."
            if t:
                await self.send(t.ws, {"type": "notice", "text": text})
            return
        if kind == "pit":  # open or close the drop zone, straight away (no restart)
            self.lesson["hazards"]["pit"] = bool(m.get("open"))
            self.arena.set_pit(self.lesson["hazards"]["pit"])
            self.arena.events.append((self.arena.time, "The drop zone is OPEN" if self.lesson["hazards"]["pit"]
                                      else "The drop zone is closed"))
            await self.broadcast_lesson()
            return
        if kind == "cpu_robot" or (kind == "design_for" and m.get("learner") == CPU_NAME
                                   and not any(q.name == CPU_NAME for q in self.learners())):
            await self.cpu_robot_command(m)  # the first computer robot, set up from the Learner view
            return
        if kind == "design_for":  # the teacher changes a learner's robot for them
            p = next((q for q in self.learners() if q.name == m.get("learner")), None)
            t = self.teacher()
            if p is None:
                if t:
                    await self.send(t.ws, {"type": "notice", "text": "That learner isn't connected."})
                return
            d = m.get("design", {})
            new = copy.deepcopy(p.design)
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", str(d.get("name", new["name"])))[:16] or new["name"]
            for key in ("colour", "weapon", "points", "settings"):
                if key in d:
                    new[key] = d[key]
            if d.get("model") in sim.HOUSE_BY_NAME:
                new["model"], new["weapon"] = d["model"], sim.HOUSE_BY_NAME[d["model"]][0]
            else:
                new.pop("model", None)
            problems = sim.check_design(new, self.lesson["limits"])
            if not rw_mods.colour_ok(new.get("colour")):
                problems.append("colour must be three whole numbers from 0 to 255")
            if problems:
                if t:
                    await self.send(t.ws, {"type": "notice", "text": "Not built: " + "; ".join(problems)})
                return
            p.design = new
            if p.robot is not None and p.robot in self.arena.robots:
                start = p.robot.start_index
                self.arena.remove_robot(p.robot)
                p.robot = self.arena.add_robot(new, brain=None, owner=p.name, start=start)
                self.teaching.attach(p)
                self.roster_version += 1
            self.teaching.save_design(p.name, new)
            self.arena.events.append((self.arena.time, f"The teacher rebuilt {p.name}'s robot"))
            await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new,
                                   "by_teacher": True})
            if t:
                await self.send(t.ws, {"type": "notice", "text": f"Built {new['name']} for {p.name}"})
            await self.broadcast_lesson()
            return
        if kind == "lesson":  # partial update from the teacher's screen
            update = m.get("lesson", {})
            rebuild, arena_changed = False, False
            if update.get("cpu_level") in cpu_brains.LEVELS:  # straight away, no restart
                self.lesson["cpu_level"] = update["cpu_level"]
                for r in self.cpu_driven():
                    r.brain = self.cpu_brain()
                self.attach_cpu()
                self.arena.events.append((self.arena.time, f"Computer robots: {cpu_brains.LEVELS[update['cpu_level']]}"))
            if isinstance(update.get("user_mods"), dict):  # straight away, no restart: the windows redraw the arena
                switched = {k: bool(v) for k, v in update["user_mods"].items() if k in sim.USER_MODS}
                self.lesson["user_mods"] = {**self.lesson.get("user_mods", {}), **switched}
                self.arena.set_user_mods(self.lesson["user_mods"])
                self.roster_version += 1
                if switched:
                    self.arena.events.append((self.arena.time, ", ".join(
                        f"{sim.user_mod_title(k, self.mod_makers)} {'on' if v else 'off'}" for k, v in switched.items())))
            if "flame_pit_cm" in update:  # the Flame pit user mod's baseline flame height: straight away
                cm = max(sim.FLAME_PIT_CM_MIN, min(sim.FLAME_PIT_CM_MAX, int(update["flame_pit_cm"])))
                self.lesson["flame_pit_cm"] = self.arena.flame_pit_cm = cm
            new_battle = update.get("mode") == "battle" and self.lesson["mode"] != "battle"
            for key in ("mode", "time_limit", "cpu_robots", "teacher_robot", "designs_locked"):
                if key in update:
                    rebuild |= key in ("mode", "cpu_robots", "teacher_robot") and update[key] != self.lesson[key]
                    self.lesson[key] = update[key]
            if "real_damage" in update:  # straight away: parts already lost stay off until the next round
                self.lesson["real_damage"] = self.arena.real_damage = bool(update["real_damage"])
                self.arena.events.append((self.arena.time, "Real damage ON: parts can come off" if
                                          self.arena.real_damage else "Real damage off"))
            self.lesson["cpu_robots"] = max(0, min(3, int(self.lesson["cpu_robots"])))
            self.lesson["time_limit"] = max(30, min(300, int(self.lesson["time_limit"])))
            for key in ("hazards", "tools"):
                for k, v in update.get(key, {}).items():
                    if k in self.lesson[key] or (key == "hazards" and k in rw_mods.HAZARDS) or key == "tools":
                        if k == "house_robots" and key == "hazards":
                            v = sim.house_list(v)
                        arena_changed |= key == "hazards" and v != self.lesson[key].get(k)
                        self.lesson[key][k] = v
            if isinstance(update.get("sound"), dict):  # kept between sessions: every sound comes back as last set
                self.lesson["sound"] = rw_sound.sound_settings(self.lesson.get("sound"), update["sound"])
                try:
                    with open(SOUND_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.lesson["sound"], f)
                except OSError:
                    pass
            if isinstance(update.get("ai_card_note"), str):  # the teacher's words on the learners' AI request card
                note = "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in update["ai_card_note"])
                self.lesson["ai_card_note"] = " ".join(note.split())[:300]
                try:
                    with open(CARD_NOTE_FILE, "w", encoding="utf-8") as f:
                        json.dump({"note": self.lesson["ai_card_note"]}, f)
                except OSError:
                    pass
            if isinstance(update.get("limits"), dict):  # the learners' ranges: kept between sessions, as the sound is
                self.lesson["limits"] = sim.clean_limits(update["limits"], self.lesson["limits"])
                try:
                    with open(LIMITS_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.lesson["limits"], f)
                except OSError:
                    pass
                await self.fit_learners()
            if rebuild:
                self.rebuild_arena(intro=new_battle)
            elif arena_changed:  # hazards start or stop mid-round: robots carry on where they are
                houses_before = [r.name for r in self.arena.robots if r.house]
                self.arena.set_hazards(self.lesson["hazards"])
                if houses_before != [r.name for r in self.arena.robots if r.house]:
                    self.roster_version += 1  # (only robots joining or leaving need the windows to redraw them)
                changes = [f"{HAZARD_WORDS[k]} {'on' if v else 'off'}" for k, v in update.get("hazards", {}).items()
                           if k in HAZARD_WORDS]
                self.arena.events.append((self.arena.time, ", ".join(changes) or "The Resident Robots have changed"))
            await self.broadcast_lesson()
        elif kind == "restart":  # a new round: a battle opens with the countdown
            self.rebuild_arena(intro=True)
        elif kind == "pause":
            self.paused = not self.paused
            self.arena.events.append((self.arena.time, "PAUSED" if self.paused else "GO!"))
        elif kind == "save_lesson":
            path = os.path.join(lab_teaching.DATA, "lesson_saved.json")
            with open(path, "w") as f:
                json.dump(self.lesson, f, indent=2)
            self.arena.events.append((self.arena.time, "Lesson settings saved"))

    def reload_mods(self, written):
        """Use mod files that an approved AI change just updated."""
        if "mods/rules.py" in written:
            sim.RULES.update(rw_mods.load_rules())
        if "mods/arena.py" in written:
            a = rw_mods.load_arena()
            self.lesson["hazards"], self.look = dict(a["hazards"]), a["look"]
        for p in self.learners():
            if f"mods/robots/{lab_teaching.slug(p.name)}.py" in written:
                p.design = self.teaching.load_saved_design(p.name) or p.design
        self.rebuild_arena()
        self.arena.events.append((self.arena.time, "An approved AI change is now in the game"))

    async def send(self, ws, msg):
        try:
            await ws.send(json.dumps(msg, separators=(",", ":")))
        except websockets.ConnectionClosed:
            pass

    def user_mods_msg(self):
        """For everyone's User mods tab: who made each mod, who'd like it switched on, and whose group is in
        (so the teacher's list can light up the mods made by the learners in this session)."""
        here = {p.name for p in self.learners()} | set(self.group)
        return {"makers": {k: v for k, v in self.mod_makers.items() if k in sim.USER_MODS},
                "votes": {k: v for k, v in self.mod_votes.items() if v and k in sim.USER_MODS},
                "arena_votes": {k: v for k, v in self.arena_votes.items() if v},
                "here": sorted(here)}

    def session_msg(self):
        """For the teacher's Accounts tab, on a class server with the club desk: the live session's group and who
        is allowed into it, the group whose proposed time comes next (and who is in it), and every learner the
        desk has."""
        if not LIVE_FILE:
            return {"desk": False}
        live = read_live()
        live = live if live and live.get("game") == GAME_ID else None
        name, g = next_group(desk_json("groups.json", {}), live.get("group") if live else None)
        return {"desk": True, "live": bool(live), "group": live.get("group", "") if live else "",
                "learners": sorted(live.get("learners", [])) if live else [],
                "next_group": name or "", "next_time": (g or {}).get("time", ""),
                "next": sorted((g or {}).get("learners", [])), "all": sorted(desk_json("learners.json", {}))}

    async def ask_desk(self, what):
        """Leave a request for the club desk (it looks every second). True if it could be left. (In the desk's
        inbox folder, in inbox/desk: that and its reports are the only folders of the desk's a game's server may
        write to on the class server.)"""
        folder = os.path.join(os.path.dirname(LIVE_FILE), "inbox", "desk")
        try:
            os.makedirs(folder, mode=0o700, exist_ok=True)
            path = os.path.join(folder, f"{int(time.time() * 1000)}_{GAME_ID}_{os.urandom(3).hex()}.json")
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(what, f)
            os.replace(path + ".tmp", path)
            return True
        except OSError:
            return False

    async def broadcast_lesson(self):
        teacher = self.teacher()
        if teacher:  # (learners aren't sent the lists of who is in which group)
            await self.send(teacher.ws, {"type": "session", "session": self.session})
        msg = {"type": "lesson", "lesson": self.lesson, "mods": self.user_mods_msg(),
               "class": [{"name": p.name, "role": p.role, "design": p.design, "default": p.default}
                         for p in self.players.values()] +
                        [{"name": CPU_NAME, "role": "computer", "design": self.cpu.design, "default": self.cpu.default,
                          "brain": self.cpu_own_brain is not None, "autopilot": self.cpu_autopilot,
                          "in_arena": self.cpu.robot is not None}]}
        for ws in list(self.players):
            await self.send(ws, msg)

    # ---------- every tick ----------
    def state(self):
        a = self.arena
        robots = []
        for r in a.robots:
            robots.append({"fl": 1 if r.flaming(a.time) else 0,
                "id": r.id, "pos": [round(v, 2) for v in r.pos], "quat": [round(v, 3) for v in tuple(r.np.getQuat())],
                "wpos": [round(v, 2) for v in r.weapon_np.getPos()],
                "wquat": [round(v, 3) for v in tuple(r.weapon_np.getQuat())],
                "speed": round(r.speed, 2), "hp": round(r.health, 1), "max": round(r.stats["armour"]),
                "ko": r.knocked_out, "rpm": round(r.weapon_rpm), "energy": round(r.weapon_energy()),
                # on: a weapon that toggles is switched on; any other weapon is firing right now
                "on": r.weapon_on if r.weapon in sim.TOGGLE_WEAPONS else a.time < r.fire_until,
                "dealt": round(r.damage_dealt), "hits": r.hits, "fc": r.fires,
                "act": 1 if a.time < r.fire_until else 0,
                # each part's health in % (body, armour, weapon, four wheels): the windows draw the hit bars from it
                "pt": [round(100 * max(0.0, r.health) / r.stats["armour"])] +
                      [round(100 * r.condition(k)) for k in sim.PARTS]})
            if r.rear_np is not None:  # the Flipper on both ends user mod: where its back plate is
                robots[-1]["w2"] = [round(v, 2) for v in r.rear_np.getPos()] + \
                    [round(v, 3) for v in tuple(r.rear_np.getQuat())]
            if a.time < r.boost_until:  # the boost button user mod: it is boosted
                robots[-1]["bo"] = 1
        time_left = self.time_left()
        winner = self.winner()
        impacts, streams = a.take_fx()
        return {"type": "state", "t": round(a.time, 2), "robots": robots, "hz": a.hazard_state(),
                "fx": {"impacts": [[[round(v, 2) for v in pos], round(dmg, 1), kind] for pos, dmg, kind in impacts[-20:]],
                       "streams": [[[round(v, 2) for v in pos], [round(v, 2) for v in d], n] for pos, d, n in streams[-30:]]},
                "events": [e for t, e in a.events if a.time - t < 4][-4:],
                "paused": self.paused, "practice": a.practice, "time_left": time_left, "winner": winner,
                "rd": 1 if a.real_damage else 0,
                # the countdown before a battle: how many seconds of it have gone (every window shows it together)
                "intro": None if self.intro_started is None else round(time.monotonic() - self.intro_started, 2)}

    def time_left(self):
        a = self.arena
        if self.intro_started is not None:  # (the battle's clock starts at ACTIVATE!)
            return self.lesson["time_limit"]
        return None if a.practice else max(0, self.lesson["time_limit"] - (a.time - self.fight_started))

    def winner(self):
        a = self.arena
        fighters = [r for r in a.robots if not r.house]  # Resident Robots don't win or lose
        if a.practice or len(fighters) < 2 or self.intro_started is not None:
            return ""
        alive = [r for r in fighters if not r.knocked_out]
        if len(alive) == 1:
            return f"{alive[0].name} WINS!"
        if not alive:
            return "DRAW!"
        if self.time_left() == 0:
            best = max(fighters, key=lambda r: r.health / r.stats["armour"])
            return f"Time! The judges pick {best.name}"
        return ""

    def roster(self):
        return {"type": "roster", "version": self.roster_version,
                "robots": [{"id": r.id, "owner": r.owner, "design": r.design} for r in self.arena.robots],
                "hazards": self.lesson["hazards"], "look": self.look, "user_mods": self.arena.user_mods,
                "mine": {p.name: (p.robot.id if p.robot else None) for p in self.players.values()}}

    async def delete_learner(self, username):
        name = lab_profiles.clean_name(username)
        for ws, q in list(self.players.items()):
            if q.role == "learner" and lab_profiles.slug(q.name) == lab_profiles.slug(name):
                del self.players[ws]
                await ws.close(4007, "Your account has been deleted by the teacher.")
        text = self.teaching.delete_learner(name)
        gone = lab_profiles.slug(name)
        if any(v and lab_profiles.slug(v) == gone for v in self.mod_makers.values()):  # their mods stay, unnamed
            self.mod_makers = {k: "" if lab_profiles.slug(v) == gone else v for k, v in self.mod_makers.items()}
            ai_pipeline.save_user_mod_makers(self.mod_makers)
        for votes in (self.mod_votes, self.arena_votes):
            for k in votes:
                votes[k] = [n for n in votes[k] if lab_profiles.slug(n) != gone]
        self.rebuild_arena()
        t = self.teacher()
        if t:
            await self.deliver([(t.ws, {"type": "notice", "text": text})] + self.teaching.teacher_update())
        await self.broadcast_lesson()

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
                # the same session, but the teacher has let someone in or taken someone out (the Accounts tab)
                self.group = sorted(mine.get("learners", []))
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in self.group:
                        self.players.pop(ws, None)
                        await ws.close(4009, "You aren't in this session.")
                        self.rebuild_arena()
            session = self.session_msg()
            if session != self.session:  # (for the teacher's Accounts tab)
                self.session = session
                await self.broadcast_lesson()
            if key != seen:
                seen, presence = key, {}
                allowed = set(mine.get("learners", [])) if mine else set()
                self.group, self.mod_votes, self.arena_votes = sorted(allowed), {}, {}  # a new session: new votes
                self.warnings = []
                await self.warn_teacher()
                self.lesson["cpu_level"] = cpu_brains.START_LEVEL  # ...and nothing attacks until the teacher says
                self.cpu_autopilot = False
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in allowed:
                        self.players.pop(ws, None)
                        await ws.close(4009, "The session has ended." if not mine else "You aren't in this group.")
                if mine:
                    self.teaching.apply_lesson(int(mine.get("lesson", 1)))
                    self.rebuild_arena()
                    self.arena.events.append((self.arena.time, f"Session started: {mine.get('group', '')}, lesson {mine.get('lesson', 1)}"))
                else:
                    self.rebuild_arena()
                    self.arena.events.append((self.arena.time, "The session has ended"))
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
        while pointer:
            try:
                with open(pointer, encoding="utf-8") as f:
                    wanted = f.read().strip() or None
            except OSError:
                wanted = None
            ready = wanted if wanted and wanted != lab_version.CODE else None
            if ready != self.live_ready:
                self.live_ready = ready
                for ws, p in list(self.players.items()):
                    if ready and p.role == "teacher":
                        await self.send(ws, {"type": "live_update", "id": ready})
            await asyncio.sleep(10)

    async def physics_loop(self):
        next_step, steps = time.perf_counter(), 0
        while True:
            next_step += sim.STEP
            if self.intro_started is not None and time.monotonic() - self.intro_started >= INTRO_SECONDS:
                self.end_intro()
            if not self.paused:  # (after a win the arena keeps working; the winner stays on screen until Restart)
                self.arena.step()
            steps += 1
            if steps % 30 == 0:  # twice a second: missions that are checked over time
                self.teaching.tick(self.arena.time)
            await asyncio.sleep(max(0.0, next_step - time.perf_counter()))

    async def send_loop(self):
        sent_version, ticks = {}, 0
        while True:
            await asyncio.sleep(SEND_RATE)
            if not self.players:
                continue
            ticks += 1
            if ticks % 20 == 0:  # once a second: missions and the teacher's outcome grid
                await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
            state = json.dumps(self.state(), separators=(",", ":"))
            roster = None
            for ws, p in list(self.players.items()):
                if sent_version.get(ws) != self.roster_version:
                    roster = roster or self.roster()
                    await self.send(ws, roster)
                    sent_version[ws] = self.roster_version
                try:
                    await ws.send(state)
                except websockets.ConnectionClosed:
                    pass


def code_role(code):
    """Which role a class code gives (compared in constant time, so the codes can't be guessed by timing)."""
    for role, real in (("teacher", TEACHER_CODE), ("learner", LEARNER_CODE)):
        if hmac.compare_digest(code.encode("utf-8"), real.encode("utf-8")):
            return role
    return None


def client_address(ws):
    """The computer connecting. Behind Caddy (on this same machine) that is in X-Forwarded-For."""
    host = (ws.remote_address or ("?",))[0]
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    forwarded = ws.request.headers.get("X-Forwarded-For") if local and ws.request is not None else None
    return forwarded.split(",")[-1].strip() if forwarded else host


def check_class_server_codes():
    """The class server won't start with missing, demo or short codes. Returns a problem, or None."""
    if "JOIN_CODE" not in os.environ or "TEACHER_CODE" not in os.environ:
        return "JOIN_CODE and TEACHER_CODE must be set (the setup script puts them in /etc/robotlab.env)."
    if LEARNER_CODE in DEMO_CODES.values() or TEACHER_CODE in DEMO_CODES.values():
        return "the demo codes CLUB42 and TEACH99 can't be used on the class server."
    if len(LEARNER_CODE) < 6 or len(TEACHER_CODE) < 16:
        return "the class code needs at least 6 characters and the teacher code at least 16."
    if LEARNER_CODE == TEACHER_CODE:
        return "the class code and teacher code must be different."
    return None


async def main():
    global CLASS_SERVER, OPEN_SIGNUP
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--bind", default="127.0.0.1",
                    help="address to listen on (127.0.0.1 = this computer only; the class server sits behind Caddy)")
    ap.add_argument("--class-server", action="store_true", help="the real class server: real codes required")
    ap.add_argument("--lesson", help="start from saved lesson settings (JSON)")
    args = ap.parse_args()
    CLASS_SERVER = args.class_server
    local_only = args.bind in ("127.0.0.1", "localhost", "::1")
    if CLASS_SERVER or not local_only:
        problem = check_class_server_codes()
        if problem:
            raise SystemExit("Robot Lab server not started: " + problem)
    OPEN_SIGNUP = os.environ.get("ROBOTLAB_OPEN_SIGNUP") == "1" or not CLASS_SERVER
    server = LabServer(args.lesson)
    if CLASS_SERVER:  # (the front door tells the Club Coders app which code this class runs)
        with open(os.path.join(lab_teaching.DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(lab_version.CODE)
    async with websockets.serve(server.handler, args.bind, args.port):
        if CLASS_SERVER:
            print(f"Robot Lab class server {lab_version.VERSION} on {args.bind}:{args.port}. "
                  f"Accounts are made by the teacher.")
        else:
            print(f"Robot Lab laptop test server on {args.bind}:{args.port}. "
                  f"Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}. A new username makes a profile.")
        await asyncio.gather(server.physics_loop(), server.send_loop(), server.watch_live(), server.watch_desk())


if __name__ == "__main__":
    asyncio.run(main())
