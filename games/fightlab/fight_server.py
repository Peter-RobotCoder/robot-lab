"""Fight Lab server: a ring for each learner (up to 4) and the teacher, with matches and tournaments.

The teacher decides what learners can see and change (the "lesson"), switches hazards on and off,
runs practice (no damage, like a game's training mode) or battles (rounds, knockouts, ring-outs), pairs
learners up for matches, and runs a knockout tournament. Learners design their fighter in their own window;
the server checks every design and rebuilds their fighter.

Rings: in a match two fighters share a ring. Everyone else has a ring of their own, with a computer sparring
partner when the teacher has those switched on.

Learners log in with a username and password, so if they disconnect they can log back in to the same fighter,
missions and settings.

Two ways to run it:
  python fight_server.py                  laptop test server: only this computer can join (ws://127.0.0.1:8781),
                                          demo codes CLUB42 / TEACH99, and a new username makes a new profile.
  python fight_server.py --class-server   the real class server (behind Caddy's wss://). It won't start without
                                          real codes in JOIN_CODE and TEACHER_CODE, the teacher makes every
                                          learner's account, and windows must run this server's version.
"""
import argparse
import asyncio
import copy
import hmac
import ipaddress
import json
import os
import sys
import random
import re
import time

import websockets

import ai_pipeline
import cpu_brains
import fight_brain
import fight_mods
import fight_profiles
import fight_sim as sim
import fight_teaching
import fight_version
sys.path.insert(0, fight_version.ENGINE_HOME)  # (the engine package, shared by every game)
from engine import club_ticket  # noqa: E402
from engine import schema  # noqa: E402
from engine import rw_sound  # noqa: E402
from engine.tournament import WinnerStaysOn  # noqa: E402

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
CLASS_SERVER = False   # set by --class-server in main()
OPEN_SIGNUP = False    # a new username makes a profile (laptop test servers only, unless FIGHTLAB_OPEN_SIGNUP=1)
BAD_LOGINS = fight_profiles.RateLimit(10)  # wrong codes or passwords: 10 a minute per computer
GAME_ID = "fightlab"  # (the club desk's name for this game)
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
BRAIN_UPLOAD_GAP = 3.0                     # seconds between one learner's brain uploads
MAX_LEARNERS = 4
SEND_RATE = 1 / 20
HERE = os.path.dirname(os.path.abspath(__file__))
CARD_NOTE_FILE = os.path.join(fight_teaching.DATA, "card_note_saved.json")  # the teacher's words on the AI card
LIMITS_FILE = os.path.join(fight_teaching.DATA, "limits_saved.json")  # the learners' ranges, kept between sessions
CPU_FILE = os.path.join(fight_teaching.DATA, "computer_fighter.json")  # the computer fighter, as the teacher set it up
CPU_NAME = "Computer fighter"  # its name in the teacher's Learner view (CHANGE 77: one design for every ring)
MISSIONS_FILE = os.path.join(fight_teaching.DATA, "mission_settings.json")  # the teacher's settings for each mission,
# kept by Save settings and used whenever that mission is chosen (CHANGE 58 and 59): these keys
MISSION_KEYS = ("mode", "round_time", "rounds_to_win", "cpu_opponents", "cpu_fighter", "teacher_fighter", "rings",
                "designs_locked", "user_mods", "mods_in_vote", "arena_in_vote", "hazards", "tools", "limits")
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230)]
CPU_NAMES = ["SPARKY", "RIVET", "JADE", "BOLT", "MIKO", "TANK"]
TEACHER_COLOUR = (180, 90, 230)

# What learners can see and change. The teacher edits this live from the teacher screen.
WEEK1_LESSON = {
    "lesson_number": 1,            # which of the 5 lessons: sets missions, tools and hazards
    "mode": "practice",            # practice = no damage (training mode); battle = rounds and knockouts
    "round_time": 60,              # seconds per round in a battle
    "rounds_to_win": 2,            # best of 3
    "cpu_opponents": True,         # a learner on their own gets a computer sparring partner
    "cpu_level": "medium",         # how well they fight: empty (the teacher's demo brain), easy, medium, expert
    "cpu_fighter": "sparring",     # who the computer plays: "sparring" fighters, or a boss (GOLIATH, ...)
    "teacher_fighter": False,      # the teacher's own fighter gets a ring too (and can be put in matches)
    "designs_locked": False,       # stop design changes (e.g. during a tournament)
    "matches": [],                 # pairs of names the teacher has put in the same ring
    "rings": 0,                    # CHANGE 75: how many rings (0 = one each, and matches share); with a number,
    "places": {},                  # who is in which (a learner's name, or "Teacher", -> its index), two to a ring,
                                   # and anyone not named takes the rings in turn
    "hazards": {"ring_out": True, "electric_ropes": False, "fire_jets": False, "slippery": False, "spikes": False},
    "ai_card_note": "",            # the teacher's own instructions, shown on every learner's AI request card
    "limits": sim.default_limits(),  # the learners' ranges for every setting and point (the teacher's Limits tab)
    "user_mods": {},               # features learners asked for (fight_sim.USER_MODS): the teacher switches them on
    "sound": dict(rw_sound.DEFAULT_SOUND),  # what everyone hears: music, crowd and hit sounds
    "tools": {                     # the learner's garage: what is shown and changeable
        "points_table": True,
        "walk_speed": True, "sidestep_speed": True, "jump_height": True, "attack_speed": True, "size": True,
        "choose_special": False, "specials": ["blast", "uppercut", "spin_kick", "slam"], "combo_editor": False,
        "fighting_style": True,    # boxer, kick boxer, capoeira, knives, swords, sticks (and the weapon)
        "name_and_colour": True, "body_choice": True, "code_view": True, "stats_readout": True,
        "bosses": False,           # learners may play as a boss
    },
}

HAZARD_WORDS = {"ring_out": "Ring-outs", "electric_ropes": "Electric ropes", "fire_jets": "Fire jets",
                "slippery": "Slippery ice", "spikes": "Spikes"}
STAGE_ITEMS = tuple(HAZARD_WORDS)  # what learners can vote for on the Mods tab (the stage's hazards)


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = sim.default_design(name if role == "learner" else "Sensei", colour,
                                         "blast" if role == "learner" else "spin_kick",
                                         "robot" if role == "learner" else "human")
        self.fighter = None
        self.start_colour = list(colour)
        self.profile = None


class Tournament:
    """A knockout bracket: the entrants (padded with computer fighters to 2, 4 or 8), round by round."""

    def __init__(self, names, shuffle=True):
        names = list(names)
        if shuffle:
            random.shuffle(names)
        size = 2
        while size < len(names):
            size *= 2
        cpus = [f"CPU {CPU_NAMES[i]}" for i in range(size - len(names))]
        # humans meet computer fighters first, so no two computers meet in the first round
        firsts, seconds = names[:size // 2], names[size // 2:] + cpus
        self.rounds = [[[a, b, None] for a, b in zip(firsts, seconds)]]
        self.champion = None

    @property
    def current(self):
        return self.rounds[-1]

    def title(self, i=None):
        left = len(self.current)
        name = "FINAL" if left == 1 else "SEMI-FINAL" if left == 2 else "QUARTER-FINAL" if left == 4 else "ROUND 1"
        return name if i is None or left == 1 else f"{name} {i + 1}"

    def record(self, a, b, winner):
        """A match finished. Returns True when the whole round is done (and the next round is ready)."""
        for m in self.current:
            if {m[0], m[1]} == {a, b} and m[2] is None:
                m[2] = winner
        if any(m[2] is None for m in self.current):
            return False
        winners = [m[2] for m in self.current]
        if len(winners) == 1:
            self.champion = winners[0]
        else:
            self.rounds.append([[winners[i], winners[i + 1], None] for i in range(0, len(winners), 2)])
        return True

    def summary(self):
        return {"rounds": self.rounds, "champion": self.champion, "title": self.title()}


class FightServer:
    def __init__(self, lesson_file=None):
        self.lesson = copy.deepcopy(WEEK1_LESSON)
        carried = os.path.join(fight_teaching.DATA, "lesson_carried.json")  # (left by a restart for code changes)
        if not lesson_file and os.path.exists(carried):
            lesson_file = carried
        if lesson_file and os.path.exists(lesson_file):
            with open(lesson_file) as f:
                self.lesson.update(json.load(f))
            if lesson_file == carried:
                os.remove(carried)
            for k, v in WEEK1_LESSON["hazards"].items():  # (a hazard added by a code change starts off)
                self.lesson["hazards"].setdefault(k, v)
        try:
            with open(MISSIONS_FILE, encoding="utf-8") as f:
                self.mission_settings = json.load(f)  # mission number (as text) -> the teacher's saved settings
            if not isinstance(self.mission_settings, dict):
                self.mission_settings = {}
        except (OSError, ValueError):
            self.mission_settings = {}
        self.lesson["saved_missions"] = self.saved_missions()  # (the Controls tab says which have saved settings)
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
        self.use_mission_settings()
        self.players = {}        # websocket -> Player
        # the computer fighter: every ring's sparring partner is built from this design (the teacher sets it up in
        # the Learner view, with a brain of its own if they like); None = the partners as they come
        self.cpu_default = sim.default_design("SPARKY", (150, 150, 160), "blast", "robot")
        self.cpu_default["style"] = {"trim": [60, 60, 70], "lights": [120, 220, 255], "number": "SPARKY"}
        self.cpu_custom = None
        self.cpu = Player(None, "computer", CPU_NAME, (150, 150, 160))  # (named for the teaching framework's
        self.cpu_source, self.cpu_own_brain, self.cpu_autopilot = "", None, False  # Learner view: CHANGE 23)
        try:
            with open(CPU_FILE, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        if isinstance(saved.get("design"), dict) and not sim.check_design(saved["design"], sim.full_limits()):
            self.cpu_custom = saved["design"]
        self.cpu_saved_brain = str(saved.get("brain", ""))[:20000] if isinstance(saved, dict) else ""
        self.group = []          # the launched group's learners (from the club desk), here yet or not
        self.mod_votes = {}      # user mod -> the learners who'd like it switched on (this session)
        self.arena_votes = {}    # the same for the stage's hazards (STAGE_ITEMS)
        self.mod_makers = ai_pipeline.user_mod_makers()  # who made each user mod: their name goes in front of it
        self.warnings = []       # for the teacher: learners who changed, in the code, something outside the lesson
        self.teacher_design = sim.default_design("Sensei", TEACHER_COLOUR, "spin_kick", "human")
        self.paused = False
        self.roster_version = 0
        self.stage = None
        self.look = {}
        self.tournament = None
        self.match_names = {}    # ring index -> (name a, name b) for matches and tournament matches
        self.swaps = []          # winner stays on (CHANGE 76): (ring index, loser, challenger, when) still to do
        try:  # the mod rules and stage look (hazards come from the lesson)
            sim.RULES.update(fight_mods.load_rules())
            self.look = fight_mods.load_stage()["look"]
        except fight_mods.ModError as e:
            print("Mods not used:", e)
        self.teaching = fight_teaching.Teaching(self)
        self.demo_brain = None  # the teacher's demo brain for "empty" computer fighters (brains/demo_cpu.py)
        demo = os.path.join(HERE, "brains", "demo_cpu.py")
        if os.path.exists(demo):
            with open(demo, encoding="utf-8") as f:
                self.load_demo_brain(f.read())
        if self.cpu_saved_brain:  # (the computer fighter's own brain, kept from last time; its autopilot starts off)
            self.cpu_own_brain, _ = self.make_demo_brain(self.cpu_saved_brain)
            self.cpu_source = self.cpu_saved_brain if self.cpu_own_brain else ""
        if not lesson_file:
            self.teaching.apply_lesson(1)
        self.rebuild_stage()

    # ---------- the rings and who is in them ----------
    def fighters_wanted(self):
        """Everyone who gets a fighter: the learners, and the teacher if their fighter is switched on."""
        out = [(p.name, p.design, p) for p in self.learners()]
        t = self.teacher()
        if self.lesson.get("teacher_fighter"):
            out.append((t.name if t else "Sensei", t.design if t else self.teacher_design, t))
        return out

    def cpu_design(self, i):
        who = self.lesson.get("cpu_fighter", "sparring")
        if who in sim.BOSS_BY_NAME:
            return sim.boss_design(who)
        if self.cpu_custom is not None:  # the one the teacher set up (CHANGE 77): the same in every ring
            return copy.deepcopy(self.cpu_custom)
        rnd = random.Random(i * 7 + 3)
        special = rnd.choice(list(sim.SPECIALS))
        d = sim.default_design(CPU_NAMES[i % len(CPU_NAMES)], (150, 150, 160), special, ("robot", "human")[i % 2])
        d["style"] = {"trim": [60, 60, 70], "lights": [120, 220, 255], "number": d["name"]}
        return d

    def use_mission_settings(self):
        """The teacher's saved settings for the mission the class is on, over the mission's own defaults (the
        presets in fight_missions): every control they saved, including what learners see in the garage."""
        saved = self.mission_settings.get(str(self.lesson.get("lesson_number", 1)))
        if not isinstance(saved, dict):
            return False
        for key in MISSION_KEYS:
            if key in saved:
                self.lesson[key] = copy.deepcopy(saved[key])
        self.lesson["limits"] = sim.clean_limits(self.lesson.get("limits"))
        self.lesson["user_mods"] = {k: bool(v) for k, v in self.lesson.get("user_mods", {}).items() if k in sim.USER_MODS}
        for k, v in WEEK1_LESSON["hazards"].items():
            self.lesson["hazards"].setdefault(k, v)
        return True

    def saved_missions(self):
        return sorted(int(k) for k in self.mission_settings if str(k).isdigit())

    def save_mission_settings(self):
        n = str(self.lesson.get("lesson_number", 1))
        self.mission_settings[n] = {k: copy.deepcopy(self.lesson[k]) for k in MISSION_KEYS if k in self.lesson}
        self.lesson["saved_missions"] = self.saved_missions()
        try:
            with open(MISSIONS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.mission_settings, f, indent=2)
        except OSError:
            pass

    def rebuild_stage(self):
        """New rings (the mode, matches or hazards may have changed), then put everyone's fighter back in."""
        L = self.lesson
        self.stage = sim.Stage(hazards=L["hazards"], practice=L["mode"] == "practice",
                               rounds_to_win=L["rounds_to_win"], round_seconds=L["round_time"],
                               user_mods=L.get("user_mods"))
        wanted = self.fighters_wanted()
        by_name = {n: (n, d, p) for n, d, p in wanted}
        pairs = []
        if self.tournament and not self.tournament.champion:
            pairs = [(m[0], m[1]) for m in self.tournament.current if m[2] is None]
        else:
            pairs = [tuple(m) for m in L.get("matches", []) if m[0] in by_name and m[1] in by_name and m[0] != m[1]]
        self.match_names = {}
        used, cpu_count = set(), 0
        for p in self.players.values():
            p.fighter = None
        if L.get("rings") and not (self.tournament and not self.tournament.champion):  # CHANGE 75: the teacher's rings
            self.place_in_rings(wanted)
            return self.finish_stage()
        for a, b in pairs:
            if a in used or b in used or len(self.stage.rings) >= sim.MAX_RINGS:
                continue
            ring = self.stage.add_ring()
            for who in (a, b):
                if who in by_name:
                    self.place(ring, *by_name[who])
                    used.add(who)
                else:  # a computer fighter in the tournament
                    d = self.cpu_design(cpu_count)
                    d["name"] = who.replace("CPU ", "")[:16]
                    ring.add_fighter(d, brain=self.cpu_brain(), owner="Computer")
                    cpu_count += 1
            self.match_names[ring.index] = (a, b)
            if self.tournament:
                i = [(m[0], m[1]) for m in self.tournament.current].index((a, b))
                ring.label = self.tournament.title(i)
            else:
                ring.label = "MATCH"
        if getattr(self.tournament, "kind", "") == "stays":
            wanted = []  # winner stays on: whoever is waiting for a ring watches (CHANGE 76)
        for name, design, p in wanted:
            if name in used or len(self.stage.rings) >= sim.MAX_RINGS:
                continue
            ring = self.stage.add_ring()
            self.place(ring, name, design, p)
            if L.get("cpu_opponents"):
                ring.add_fighter(self.cpu_design(cpu_count), brain=self.cpu_brain(), owner="Computer")
                cpu_count += 1
            ring.label = "TRAINING" if self.stage.practice else ""
        self.finish_stage()

    def finish_stage(self):
        if not self.stage.rings:  # nobody here yet: a demo fight to watch
            ring = self.stage.add_ring()
            ring.add_fighter(self.teacher_design, brain=self.cpu_brain("medium"), owner="Teacher (away)")
            ring.add_fighter(self.cpu_design(0), brain=self.cpu_brain(), owner="Computer")
            ring.label = "DEMO"
        self.roster_version += 1
        self.stage.events.append((self.stage.time, "Practice: no damage" if self.stage.practice else "Battle!"))

    def place_in_rings(self, wanted):
        """CHANGE 75: the teacher's number of rings, two fighters to a ring: the people the teacher placed
        (Controls, Who is where) go where they were put, everyone else takes the rings in turn; a ring with one
        fighter gets a computer sparring partner (when they are on), and anyone who doesn't fit sits out."""
        L = self.lesson
        n = max(1, min(sim.MAX_RINGS, int(L["rings"])))
        rings = [self.stage.add_ring() for _ in range(n)]
        places = L.get("places", {})
        turn = 0
        for name, design, p in wanted:
            key = "Teacher" if (p is None or p.role == "teacher") else name
            i = places.get(key)
            if not (isinstance(i, int) and 0 <= i < n and len(rings[i].fighters) < 2):
                free = [j for j in range(n) if len(rings[j].fighters) < 2]
                if not free:
                    continue
                i = free[turn % len(free)]
                turn += 1
            self.place(rings[i], name, design, p)
        for i, ring in enumerate(rings):
            names = [f.owner for f in ring.fighters]
            if len(names) == 1 and L.get("cpu_opponents"):
                ring.add_fighter(self.cpu_design(i), brain=self.cpu_brain(), owner="Computer")
            if len(names) == 2:
                self.match_names[ring.index] = tuple(names)
                ring.label = "MATCH"
            elif not ring.fighters:
                ring.label = "EMPTY"
            else:
                ring.label = "TRAINING" if self.stage.practice else ""

    def place(self, ring, name, design, p):
        f = ring.add_fighter(design, brain=None if p else self.cpu_brain("medium"), owner=name if p else "Teacher (away)")
        if p is not None:
            p.fighter = f
            if p.role == "learner":
                self.teaching.attach(p)  # their uploaded brain fights if autopilot is on
        return f

    def cpu_brain(self, level=None):
        """What drives a computer fighter: the computer fighter's own brain while its autopilot is on, or the
        level's brain."""
        if level is None and self.cpu_own_brain is not None and self.cpu_autopilot:
            return self.cpu_own_brain
        return cpu_brains.for_level(level or self.lesson.get("cpu_level", "medium"), self.demo_brain)

    def cpu_state(self):
        """The computer fighter for the teacher's Learner view (in the class list)."""
        return {"name": CPU_NAME, "role": "computer", "design": self.cpu_custom or self.cpu_default,
                "default": self.cpu_default, "brain": self.cpu_own_brain is not None, "autopilot": self.cpu_autopilot,
                "in_arena": bool(self.lesson.get("cpu_opponents", 1))}

    def save_cpu(self):
        try:
            if self.cpu_custom is None and not self.cpu_source:
                if os.path.exists(CPU_FILE):
                    os.remove(CPU_FILE)  # (as it comes: nothing to keep)
                return
            with open(CPU_FILE + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"design": self.cpu_custom, "brain": self.cpu_source}, f)
            os.replace(CPU_FILE + ".tmp", CPU_FILE)
        except OSError:
            pass

    async def cpu_fighter_command(self, m):
        """The teacher sets up the computer fighter (the Learner view): its design, its own brain, its autopilot,
        or Reset (back to the sparring partners as they come, with no brain of its own)."""
        t = self.teacher()
        text = None
        if "design" in m:
            d = m["design"] if isinstance(m["design"], dict) else {}
            new = copy.deepcopy(self.cpu_custom or self.cpu_default)
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", str(d.get("name", new["name"])))[:16] or new["name"]
            for key in ("colour", "body", "special", "points", "settings", "combo", "fighting_style", "weapon",
                        "look", "style"):
                if key in d:
                    new[key] = d[key]
            if new.get("body") not in sim.MODEL_BODIES:
                new.pop("look", None)
            if not sim.weapons_for(sim.style_of(new)[0]):
                new.pop("weapon", None)
            new.pop("model", None)
            problems = sim.check_design(new, sim.full_limits())
            if not fight_mods.colour_ok(new.get("colour")):
                problems.append("colour must be three whole numbers from 0 to 255")
            if problems:
                text = "Not built: " + "; ".join(problems)
            else:
                self.cpu_custom = new
                self.rebuild_stage()
                text = f"Built {new['name']} for the computer: every ring's sparring partner"
                self.stage_event("The teacher rebuilt the computer fighter")
        elif m.get("reset"):
            old, self.cpu_own_brain = self.cpu_own_brain, None
            if old is not None:
                old.close()
            self.cpu_custom, self.cpu_source, self.cpu_autopilot = None, "", False
            self.rebuild_stage()
            text = "The computer fighter is back as it comes, with no brain of its own"
        elif "brain" in m:  # (loaded off the game loop: checking a brain can take a moment)
            source = str(m["brain"])[:20000]
            brain, problem = await asyncio.to_thread(self.make_demo_brain, source)
            if brain is None:
                text = f"Brain problem: {problem}"
            else:
                old, self.cpu_own_brain, self.cpu_source = self.cpu_own_brain, brain, source
                if old is not None:
                    old.close()
                text = "Brain uploaded for the computer fighter. Switch its autopilot on to use it."
        elif "autopilot" in m:
            self.cpu_autopilot = bool(m["autopilot"]) and self.cpu_own_brain is not None
            for f in self.stage.fighters():
                if f.owner == "Computer":
                    f.brain = self.cpu_brain()
        self.save_cpu()
        if t and text:
            await self.send(t.ws, {"type": "notice", "text": text})
        await self.broadcast_lesson()

    @staticmethod
    def make_demo_brain(source):
        """The teacher's demo brain (written like a learner's): (brain, None), or (None, the problem)."""
        try:
            fn, fname = fight_brain.load_brain(source, "demo_cpu")
        except fight_brain.BrainError as e:
            return None, str(e)
        return fight_brain.Autopilot(fn, fname), None

    def use_demo_brain(self, brain):
        """Computer fighters set to Empty now run this brain (the old one is closed)."""
        old, self.demo_brain = self.demo_brain, brain
        if old is not None and hasattr(old, "close"):
            old.close()
        if self.stage is not None:
            for f in self.stage.fighters():
                if f.owner == "Computer":
                    f.brain = self.cpu_brain()

    def load_demo_brain(self, source):
        brain, problem = self.make_demo_brain(source)
        if brain is not None:
            self.use_demo_brain(brain)
        return problem

    def learners(self):
        return [p for p in self.players.values() if p.role == "learner"]

    def teacher(self):
        return next((p for p in self.players.values() if p.role == "teacher"), None)

    def limits_for(self, player):
        """The ranges a design is held to: the learners' (as the teacher has set them), or the widest ones for the
        teacher's own fighter."""
        return sim.full_limits() if player.role == "teacher" else self.lesson["limits"]

    async def fit_learners(self):
        """The teacher has changed the limits: a learner's fighter outside them is pulled back to the nearest
        allowed values (and rebuilt, and saved), and the learner is told."""
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

    def outside_lesson(self, old, new):
        """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
        did it in the code): [[variable, the old value, the new value], ...] for the teacher's Warnings tab."""
        found = schema.outside_lesson(sim.schema(), old, new, self.lesson["tools"])
        if old.get("model") != new.get("model"):  # (a boss's special comes with it: not a change of theirs)
            found = [f for f in found if f[0] != "special"]
        if old.get("fighting_style") != new.get("fighting_style"):  # (a style's weapon comes with it)
            found = [f for f in found if f[0] != "weapon"]
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
        (the rules still hold, and the teacher is told: see outside_lesson)."""
        tools, old = self.lesson["tools"], player.design
        new = copy.deepcopy(old)
        if not isinstance(d, dict):
            return new
        if player.role == "teacher" or everything:
            tools = {k: True for k in tools} | {"specials": list(sim.SPECIALS)}
        if tools.get("name_and_colour"):
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", str(d.get("name", old["name"])))[:16] or old["name"]
            c = d.get("colour", old["colour"])
            if fight_mods.colour_ok(c):
                new["colour"] = c
        if tools.get("body_choice") and d.get("body") in sim.BODIES:
            new["body"] = d["body"]
            if new["body"] in sim.MODEL_BODIES:  # the detailed bodies' look (checked with the rest of the design)
                look = d.get("look") if isinstance(d.get("look"), dict) else old.get("look")
                new["look"] = dict(look) if isinstance(look, dict) else sim.default_look(new["body"])
            else:
                new.pop("look", None)
        if tools.get("body_choice") and isinstance(d.get("style"), dict):  # a robot's trim, lights and number
            st = {k: v for k, v in d["style"].items() if k in ("trim", "lights") and fight_mods.colour_ok(v)}
            if isinstance(d["style"].get("number"), str):
                st["number"] = re.sub(r"[^A-Za-z0-9 ]", "", d["style"]["number"])[:10]
            new["style"] = dict(old.get("style") or {}, **st)
        if tools.get("fighting_style") and d.get("fighting_style") in sim.STYLES:
            new["fighting_style"] = d["fighting_style"]
            weapons = sim.weapons_for(d["fighting_style"])
            if weapons:
                new["weapon"] = next(w for w in (d.get("weapon"), old.get("weapon"), weapons[0]) if w in weapons)
            else:
                new.pop("weapon", None)
        if tools.get("points_table") and isinstance(d.get("points"), dict):
            new["points"] = {k: d["points"].get(k, old["points"][k]) for k in sim.STATS}
        settings = d.get("settings", {}) if isinstance(d.get("settings"), dict) else {}
        for k in sim.SETTINGS:
            if tools.get(k) and k in settings:
                new["settings"][k] = settings[k]
        if tools.get("combo_editor") and "combo" in d:
            new["combo"] = d["combo"] if isinstance(d["combo"], list) else old["combo"]
            if isinstance(new["combo"], list):
                new["combo"] = [str(m)[:10] for m in new["combo"][:12]]
        if tools.get("choose_special") and d.get("special") in tools.get("specials", []):
            new["special"] = d["special"]
        if tools.get("bosses"):  # play as a boss instead of your own design
            if d.get("model") in sim.BOSS_BY_NAME:
                new["model"] = d["model"]
            else:
                new.pop("model", None)
        if new.get("model"):
            new["special"] = sim.BOSS_BY_NAME[new["model"]][1]
        elif new["special"] not in sim.SPECIALS:
            new["special"] = "blast"
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
        if CLASS_SERVER and hello.get("version") != fight_version.VERSION:
            # (the window shows this, with a button to the download page. A close reason can be at most 123 bytes)
            where = fight_version.DOWNLOAD_PAGE or "your teacher"
            await ws.close(4006, f"Out of date: download Club Coders {fight_version.VERSION} from {where}"[:120])
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
        profile, is_new = None, False
        if role == "learner":  # username and password (slow on purpose, so it's checked away from the game loop)
            try:
                if ticket:
                    profile, is_new = fight_profiles.ticket_profile(ticket["name"]), False
                else:
                    profile, is_new = await asyncio.to_thread(fight_profiles.login, hello.get("name", ""),
                                                              hello.get("password", ""), OPEN_SIGNUP)
            except fight_profiles.LoginError as e:
                BAD_LOGINS.failed(where)
                await ws.close(4004, str(e)[:120])  # (a close reason can be at most 123 bytes)
                return
            name = profile["name"]
            old = next((q for q in self.learners() if fight_profiles.slug(q.name) == fight_profiles.slug(name)), None)
            if old is not None:  # logged in again (e.g. after a dropped connection): the old connection goes
                await old.ws.close(4005, "you logged in again somewhere else")
                self.players.pop(old.ws, None)
            if len(self.learners()) >= MAX_LEARNERS:
                await ws.close(4003, "the class is full (4 learners)")
                return
        else:
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(ticket["name"] if ticket else hello.get("name", "")))[:12] or "Teacher"
        colour = COLOURS[len(self.learners()) % len(COLOURS)] if role == "learner" else TEACHER_COLOUR
        p = Player(ws, role, name, colour)
        p.profile = profile
        if role == "teacher":
            p.design = self.teacher_design
        else:
            saved = self.teaching.load_saved_design(name)
            if saved:  # their fighter from last time
                p.design = saved
            self.teaching.login(p)  # their missions, reflections, brain and settings from last time
            if getattr(self, "design_for_everyone", None) and p.role == "learner":  # (CHANGE 85)
                await self.build_for(p, self.design_for_everyone, quiet=True)
        self.players[ws] = p
        print(f"+ {name} ({role})")
        self.rebuild_stage()
        self.stage.events.append((self.stage.time, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "lesson": self.lesson,
                             "design": p.design, "rules": self.rules(),
                             "prefs": (profile or {}).get("prefs", {}), "new_profile": bool(profile and is_new),
                             "code": fight_version.CODE,
                             "live_ready": getattr(self, "live_ready", None) if role == "teacher" else None})
        await self.broadcast_lesson()
        await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
        if role == "teacher":
            await self.warn_teacher()
        try:
            async for raw in ws:
                m = json.loads(raw)
                if isinstance(m, dict):
                    await self.on_message(p, m)
        except (websockets.ConnectionClosed, json.JSONDecodeError):
            pass
        finally:
            if self.players.get(ws) is p:  # (not already replaced by the same learner logging in again)
                del self.players[ws]
                if role == "teacher":
                    self.teacher_design = p.design
                self.teaching.save()
                print(f"- {name} left")
                self.rebuild_stage()

    def rules(self):
        return {"stats": sim.STATS, "points_total": sim.POINTS_TOTAL, "stat_min": sim.STAT_MIN,
                "stat_max": sim.STAT_MAX, "settings": sim.SETTINGS, "specials": sim.SPECIALS, "bodies": sim.BODIES,
                "full": sim.full_limits(),  # the widest ranges: the teacher's own fighter, and the Limits tab's sliders
                "combo_moves": sim.COMBO_MOVES, "combo_min": sim.COMBO_MIN, "combo_max": sim.COMBO_MAX,
                "bosses": {name: v[1] for name, v in sim.BOSS_BY_NAME.items()}, "cpu_levels": cpu_brains.LEVELS,
                "model_bodies": list(sim.MODEL_BODIES), "human_bodies": list(sim.HUMAN_BODIES),
                "robin_style": sim.ROBIN_STYLE, "outfits": sim.OUTFITS, "hair_styles": sim.HAIR_STYLES,
                "shapes": sim.SHAPES, "height": [sim.HEIGHT_MIN, sim.HEIGHT_MAX], "styles": sim.STYLES,
                "wins": sim.WINS,
                "style_moves": {s: {m: v[0] for m, v in moves.items()} for s, moves in sim.STYLE_MOVES.items()},
                "weapons": {w: [v[0], v[1]] for w, v in sim.WEAPONS.items()}}

    async def deliver(self, replies):
        for ws, msg in replies:
            await self.send(ws, msg)

    async def build_for(self, p, d, quiet=False):
        """The teacher builds this fighter for learner p (the Learner view's BUILD FOR NAME; and for all:
        CHANGE 85). Returns the problems (none: built)."""
        new = copy.deepcopy(p.design)
        new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", str(d.get("name", new["name"])))[:16] or new["name"]
        for key in ("colour", "special", "points", "settings", "combo", "body", "look", "fighting_style"):
            if key in d:
                new[key] = d[key]
        if sim.weapons_for(sim.style_of(new)[0]):
            new["weapon"] = d.get("weapon", new.get("weapon"))
        else:
            new.pop("weapon", None)
        if d.get("model") in sim.BOSS_BY_NAME:
            new["model"], new["special"] = d["model"], sim.BOSS_BY_NAME[d["model"]][1]
        else:
            new.pop("model", None)
        problems = fight_mods.check_fighter(new)
        if problems:
            if not quiet:
                await self.notice_teacher("Not built: " + "; ".join(problems))
            return problems
        p.design = new
        self.refit(p)
        self.teaching.save_design(p.name, new)
        self.stage.events.append((self.stage.time, f"The teacher rebuilt {p.name}'s fighter"))
        await self.send(p.ws, {"type": "design_result", "ok": True, "problems": [], "design": new,
                               "by_teacher": True})
        if not quiet:
            await self.notice_teacher(f"Built {new['name']} for {p.name}")
        return []

    async def on_message(self, p, m):
        kind = m.get("type")
        if kind == "brain" and p.role == "learner":  # loaded in its own process, away from the game loop
            await self.upload_brain(p, str(m.get("source", "")))
            return
        if kind not in ("control", "ping", "design", "design_for", "cpu_brain"):
            replies = self.teaching.on_message(p, m)
            if replies is not None:
                broadcast = replies == "broadcast" or "broadcast" in replies
                if replies != "broadcast":
                    await self.deliver([r for r in replies if r != "broadcast"])
                if broadcast:
                    await self.broadcast_lesson()
                    await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
                return
        if kind == "control" and p.fighter is not None:
            try:
                fwd = max(-1.0, min(1.0, float(m.get("f", 0))))
                side = max(-1.0, min(1.0, float(m.get("s", 0))))
            except (TypeError, ValueError):
                return
            hold = m.get("hold") if m.get("hold") in sim.HOLDS else ""
            if p.fighter.brain is None:  # (autopilot drives when it's on)
                p.fighter.control = (fwd, side, hold)
                if m.get("press") in sim.PRESSES:
                    p.fighter.press(m["press"], self.stage.time)
        elif kind == "ping":
            await self.send(p.ws, {"type": "pong", "t": m.get("t")})
        elif kind in ("mod_vote", "arena_vote") and p.role == "learner":  # a tick on the learner's Mods tab
            votes, key, known = (self.mod_votes, m.get("mod"), sim.USER_MODS) if kind == "mod_vote" else \
                (self.arena_votes, m.get("item"), STAGE_ITEMS)
            in_vote = self.lesson.get("mods_in_vote" if kind == "mod_vote" else "arena_in_vote", {})
            if isinstance(key, str) and key in known and in_vote.get(key, True):
                votes[key] = [n for n in votes.get(key, []) if n != p.name] + ([p.name] if m.get("on") else [])
                await self.broadcast_lesson()
        elif kind == "design":
            if self.lesson["designs_locked"] and p.role == "learner":
                await self.send(p.ws, {"type": "design_result", "ok": False, "design": p.design,
                                       "problems": ["The teacher has locked designs for now."]})
                return
            # from the code panel a learner can change what the garage hides (while the lesson has the Code view)
            hack = bool(m.get("code")) and p.role == "learner" and bool(self.lesson["tools"].get("code_view"))
            new = self.clean_design(p, m.get("design", {}), everything=hack)
            problems = sim.check_design(new, self.limits_for(p))
            old = p.design  # (the missions compare the two: what the build changed, and how)
            outside = self.outside_lesson(old, new) if hack and not problems else []
            if not problems:
                p.design = new
                self.refit(p)
                self.stage.events.append((self.stage.time, f"{p.name} rebuilt {new['name']}"))
            self.teaching.on_design(p, new, problems, not problems, old=old, by_code=bool(m.get("code")))
            if not problems and p.role == "learner":
                self.teaching.save_design(p.name, new)  # autosave: their fighter is there next lesson
            await self.send(p.ws, {"type": "design_result", "ok": not problems, "problems": problems, "design": p.design})
            await self.deliver(self.teaching.teacher_update() + ([(p.ws, self.teaching.missions_msg(p))]
                                                                 if p.role == "learner" else []))
            if not problems:
                await self.broadcast_lesson()  # the teacher's class list shows the new design
            if outside:
                await self.warn_teacher(p, outside)
        elif p.role == "teacher":
            await self.teacher_command(m)

    def refit(self, p):
        """A player's new design goes into the ring they're in (same ring, same slot, same opponent)."""
        f = p.fighter
        if f is None or f not in self.stage.fighters():
            return
        ring, slot, wins = f.ring, f.slot, f.wins
        nf = sim.Fighter(ring, self.stage.new_id(), p.design, slot, None, p.name)
        ring.fighters[slot] = nf
        nf.wins = wins
        p.fighter = nf
        ring.start_round()
        if p.role == "learner":
            self.teaching.attach(p)
        self.roster_version += 1

    async def upload_brain(self, p, source):
        now = time.monotonic()
        if now - getattr(p, "brain_at", -BRAIN_UPLOAD_GAP) < BRAIN_UPLOAD_GAP:
            await self.send(p.ws, {"type": "brain_result", "ok": False,
                                   "error": "wait a few seconds before uploading again"})
            return
        p.brain_at = now
        try:
            loaded = await asyncio.to_thread(fight_brain.load_brain, source, p.name)
        except fight_brain.BrainError as e:
            loaded = e
        if self.players.get(p.ws) is not p:  # they left while it loaded
            if not isinstance(loaded, Exception):
                loaded[0].close()
            return
        reply = self.teaching.upload_brain(p, source, loaded)
        await self.deliver([(p.ws, reply), (p.ws, self.teaching.missions_msg(p))] + self.teaching.teacher_update())

    async def notice_teacher(self, text):
        t = self.teacher()
        if t:
            await self.send(t.ws, {"type": "notice", "text": text})

    async def teacher_command(self, m):
        kind = m.get("type")
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
        if kind == "delete_learner":  # everything the server keeps about them goes (they're disconnected first)
            await self.delete_learner(m.get("learner", ""))
            return
        if kind == "restart_server":  # load code changes ("3 Fight Lab server.bat" starts it again)
            self.teaching.save()
            self.carry_lesson()  # (the lesson carries on as it was: hazards, mode, matches, tools)
            for ws in list(self.players):
                await self.send(ws, {"type": "notice", "big": True,
                                     "text": "THE SERVER IS RESTARTING to load changes\nyou'll reconnect in a few seconds"})
            if CLASS_SERVER:  # the class server (a live update): everyone gets a warning, then it restarts
                for ws in list(self.players):
                    await self.send(ws, {"type": "notice", "big": True,
                                         "text": "THE GAME IS UPDATING\nback in 10 seconds: your window will reopen"})
                asyncio.get_running_loop().call_later(10, lambda: (self.teaching.save(), self.carry_lesson(), os._exit(3)))
                return
            print("Restarting to load code changes...")
            os._exit(3)
        if kind == "restart_clients":  # everyone's window reopens itself with the new code
            for ws, q in list(self.players.items()):
                if q.role == "learner":
                    await self.send(ws, {"type": "restart_client"})
            return
        if kind == "cpu_brain":  # the teacher's demo brain for "empty" computer fighters
            brain, problem = await asyncio.to_thread(self.make_demo_brain, str(m.get("source", ""))[:20000])
            if brain is not None:
                self.use_demo_brain(brain)
            await self.notice_teacher(f"Demo brain problem: {problem}" if problem else
                                      "Demo brain uploaded: computer fighters set to Empty now run it")
            return
        if kind == "cpu_robot" or (kind == "design_for" and m.get("learner") == CPU_NAME):  # the computer fighter
            await self.cpu_fighter_command(m)
            return
        if kind == "design_for_all":  # CHANGE 85: every learner gets exactly this fighter (and anyone who joins later)
            d = m.get("design", {}) if isinstance(m.get("design"), dict) else {}
            built, failed = [], []
            for p in self.learners():
                problems = await self.build_for(p, d, quiet=True)
                (failed if problems else built).append(p.name)
            self.design_for_everyone = d
            self.lesson["design_for_everyone"] = str(d.get("name", ""))[:16]
            await self.notice_teacher(f"Built {d.get('name', '?')} for {', '.join(built) or 'nobody yet'}"
                                      + (f"; not for {', '.join(failed)}" if failed else "") +
                                      ". Anyone who joins this session gets it too.")
            await self.broadcast_lesson()
            return
        if kind == "design_for":  # the teacher changes a learner's fighter for them
            p = next((q for q in self.learners() if q.name == m.get("learner")), None)
            if p is None:
                await self.notice_teacher("That learner isn't connected.")
                return
            await self.build_for(p, m.get("design", {}) if isinstance(m.get("design"), dict) else {})
            await self.broadcast_lesson()
            return
        if kind == "tournament":  # start or stop a tournament of everyone connected: a knockout, or winner stays on
            if m.get("start"):
                names = [n for n, _, _ in self.fighters_wanted()]
                if len(names) < 2:
                    await self.notice_teacher("A tournament needs at least 2 fighters (learners, or your own fighter).")
                    return
                if m.get("kind") == "stays":  # CHANGE 76: two rings live, the winner stays, the loser queues
                    self.tournament = WinnerStaysOn(names, live=max(1, min(sim.MAX_RINGS, int(m.get("live", 2)))))
                    self.stage_event("WINNER STAYS ON!  The loser goes to the back of the queue.")
                else:
                    self.tournament = Tournament(names)
                    self.stage_event("THE TOURNAMENT BEGINS!")
                self.swaps = []
                self.lesson["mode"] = "battle"
                self.lesson["designs_locked"] = True
            else:
                self.tournament = None
                self.lesson["designs_locked"] = False
            self.rebuild_stage()
            await self.broadcast_lesson()
            return
        if kind == "lesson":  # partial update from the teacher's screen
            update = m.get("lesson", {}) if isinstance(m.get("lesson"), dict) else {}
            rebuild, hazards_changed = False, False
            if update.get("cpu_level") in cpu_brains.LEVELS:  # straight away, no restart
                self.lesson["cpu_level"] = update["cpu_level"]
                for f in self.stage.fighters():
                    if f.owner == "Computer":
                        f.brain = self.cpu_brain()
                self.stage_event(f"Computer fighters: {cpu_brains.LEVELS[update['cpu_level']]}")
            if isinstance(update.get("limits"), dict):  # the learners' ranges: kept between sessions
                self.lesson["limits"] = sim.clean_limits(update["limits"], self.lesson["limits"])
                try:
                    with open(LIMITS_FILE, "w", encoding="utf-8") as f:
                        json.dump(self.lesson["limits"], f)
                except OSError:
                    pass
                await self.fit_learners()
            if isinstance(update.get("ai_card_note"), str):  # the teacher's words on the learners' AI request card
                note = "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in update["ai_card_note"])
                self.lesson["ai_card_note"] = " ".join(note.split())[:300]
                try:
                    with open(CARD_NOTE_FILE, "w", encoding="utf-8") as f:
                        json.dump({"note": self.lesson["ai_card_note"]}, f)
                except OSError:
                    pass
            if isinstance(update.get("mods_in_vote"), dict):  # which mods learners see and vote on (CHANGE 55)
                in_vote = {k: bool(v) for k, v in update["mods_in_vote"].items() if k in sim.USER_MODS}
                self.lesson["mods_in_vote"] = {**self.lesson.get("mods_in_vote", {}), **in_vote}
                for k, v in in_vote.items():
                    if not v:
                        self.mod_votes.pop(k, None)  # (its votes go with it)
            if isinstance(update.get("arena_in_vote"), dict):  # ...and which of the stage's items (CHANGE 71)
                in_vote = {k: bool(v) for k, v in update["arena_in_vote"].items() if k in STAGE_ITEMS}
                self.lesson["arena_in_vote"] = {**self.lesson.get("arena_in_vote", {}), **in_vote}
                for k, v in in_vote.items():
                    if not v:
                        self.arena_votes.pop(k, None)
            if isinstance(update.get("user_mods"), dict):  # straight away, no restart: the windows redraw the stage
                switched = {k: bool(v) for k, v in update["user_mods"].items() if k in sim.USER_MODS}
                self.lesson["user_mods"] = {**self.lesson.get("user_mods", {}), **switched}
                self.stage.set_user_mods(self.lesson["user_mods"])
                self.roster_version += 1
                if switched:
                    self.stage_event(", ".join(f"{sim.USER_MODS[k][0]} {'on' if v else 'off'}"
                                               for k, v in switched.items()))
            if update.get("cpu_fighter") in ["sparring"] + list(sim.BOSS_BY_NAME):
                rebuild |= update["cpu_fighter"] != self.lesson["cpu_fighter"]
                self.lesson["cpu_fighter"] = update["cpu_fighter"]
            for key in ("mode", "round_time", "rounds_to_win", "cpu_opponents", "teacher_fighter", "designs_locked"):
                if key in update:
                    rebuild |= key in ("mode", "cpu_opponents", "teacher_fighter", "rounds_to_win") \
                        and update[key] != self.lesson[key]
                    self.lesson[key] = update[key]
            if self.lesson["mode"] not in ("practice", "battle"):
                self.lesson["mode"] = "practice"
            try:
                self.lesson["round_time"] = max(20, min(300, int(self.lesson["round_time"])))
                self.lesson["rounds_to_win"] = max(1, min(3, int(self.lesson["rounds_to_win"])))
            except (TypeError, ValueError):
                self.lesson["round_time"], self.lesson["rounds_to_win"] = 60, 2
            self.stage.round_seconds = self.lesson["round_time"]
            if "rings" in update:  # CHANGE 75: how many rings (0 = automatic), and who is in which
                try:
                    n = max(0, min(sim.MAX_RINGS, int(update["rings"])))
                except (TypeError, ValueError):
                    n = 0
                rebuild |= n != self.lesson.get("rings", 0)
                self.lesson["rings"] = n
            if isinstance(update.get("places"), dict):
                places = dict(self.lesson.get("places", {}))
                for k, v in update["places"].items():
                    if isinstance(k, str) and len(k) <= 40:
                        if v is None:
                            places.pop(k, None)
                        elif isinstance(v, int) and 0 <= v < sim.MAX_RINGS:
                            places[k] = v
                rebuild |= places != self.lesson.get("places", {})
                self.lesson["places"] = places
            if "matches" in update and isinstance(update["matches"], list):
                pairs = [[str(a)[:16], str(b)[:16]] for a, b in
                         (m_ for m_ in update["matches"] if isinstance(m_, list) and len(m_) == 2)][:6]
                rebuild |= pairs != self.lesson["matches"]
                self.lesson["matches"] = pairs
            for key in ("hazards", "tools"):
                for k, v in (update.get(key, {}) if isinstance(update.get(key), dict) else {}).items():
                    if key == "hazards" and k not in fight_mods.HAZARDS:
                        continue
                    if key == "tools" and k not in self.lesson["tools"]:
                        continue
                    if k == "specials":
                        v = [s for s in v if s in sim.SPECIALS] if isinstance(v, list) else self.lesson["tools"][k]
                    else:
                        v = bool(v)
                    hazards_changed |= key == "hazards" and v != self.lesson[key].get(k)
                    self.lesson[key][k] = v
            if isinstance(update.get("sound"), dict):
                self.lesson["sound"] = rw_sound.sound_settings(self.lesson.get("sound"), update["sound"])
            if rebuild:
                if self.tournament and "mode" in update and self.lesson["mode"] == "practice":
                    self.tournament = None  # practice ends a tournament
                self.rebuild_stage()
            elif hazards_changed:  # hazards start or stop mid-round: fighters carry on where they are
                self.stage.set_hazards(self.lesson["hazards"])
                self.roster_version += 1  # (the windows redraw the rings with ropes or without)
                changes = [f"{HAZARD_WORDS[k]} {'on' if v else 'off'}" for k, v in update.get("hazards", {}).items()
                           if k in HAZARD_WORDS]
                self.stage_event(", ".join(changes))
            await self.broadcast_lesson()
        elif kind == "restart":  # new matches in every ring (a tournament replays its unfinished matches)
            self.rebuild_stage()
        elif kind == "pause":
            self.paused = not self.paused
            self.stage_event("PAUSED" if self.paused else "GO!")
        elif kind == "save_lesson":  # every control, for this mission: used whenever the mission is chosen
            self.save_mission_settings()
            path = os.path.join(fight_teaching.DATA, "lesson_saved.json")
            with open(path, "w") as f:
                json.dump(self.lesson, f, indent=2)
            self.stage_event(f"Mission {self.lesson.get('lesson_number', 1)} settings saved")
            await self.broadcast_lesson()
        elif kind == "restore_lesson":  # back to what was saved for this mission (or the mission's own defaults)
            n = self.lesson.get("lesson_number", 1)
            self.teaching.apply_lesson(n)
            self.rebuild_stage()
            self.stage_event(f"Mission {n} settings restored")
            await self.broadcast_lesson()

    def carry_lesson(self):
        """Save the lesson for the server that starts after a restart for code changes."""
        with open(os.path.join(fight_teaching.DATA, "lesson_carried.json"), "w") as f:
            json.dump(self.lesson, f, indent=2)

    def stage_event(self, text):
        self.stage.events.append((self.stage.time, text))

    def reload_mods(self, written):
        """Use mod files that an approved AI change just updated."""
        if "mods/rules.py" in written:
            sim.RULES.update(fight_mods.load_rules())
        if "mods/stage.py" in written:
            a = fight_mods.load_stage()
            self.lesson["hazards"], self.look = dict(a["hazards"]), a["look"]
        for p in self.learners():
            if f"mods/fighters/{fight_teaching.slug(p.name)}.py" in written:
                p.design = self.teaching.load_saved_design(p.name) or p.design
        self.rebuild_stage()
        self.stage_event("An approved AI change is now in the game")

    async def send(self, ws, msg):
        try:
            await ws.send(json.dumps(msg, separators=(",", ":")))
        except websockets.ConnectionClosed:
            pass

    def user_mods_msg(self):
        """For everyone's Mods tab: who made each mod, who'd like it switched on, and whose group is in."""
        here = {p.name for p in self.learners()} | set(self.group)
        return {"makers": {k: v for k, v in self.mod_makers.items() if k in sim.USER_MODS},
                "votes": {k: v for k, v in self.mod_votes.items() if v and k in sim.USER_MODS},
                "arena_votes": {k: v for k, v in self.arena_votes.items() if v},
                "here": sorted(here)}

    async def broadcast_lesson(self):
        msg = {"type": "lesson", "lesson": self.lesson, "mods": self.user_mods_msg(),
               "class": [{"name": p.name, "role": p.role, "design": p.design} for p in self.players.values()] +
                        [self.cpu_state()],
               "tournament": self.tournament.summary() if self.tournament else None}
        for ws in list(self.players):
            await self.send(ws, msg)

    # ---------- every tick ----------
    def state(self):
        st, now = self.stage, self.stage.time
        rings = [sim.ring_state(r, now) for r in st.rings]
        fx = st.take_fx()
        return {"type": "state", "t": round(now, 2), "rings": rings,
                "fx": [[[round(v, 2) for v in pos], round(dmg, 1), kind] for pos, dmg, kind in fx[-24:]],
                "events": [e for t, e in st.events if now - t < 4 and e][-4:],
                "paused": self.paused, "practice": st.practice, "rs": sim.RULES["ring_size"]}

    def roster(self):
        return {"type": "roster", "version": self.roster_version,
                "fighters": [{"id": f.id, "owner": f.owner, "design": f.design, "ring": f.ring.index, "slot": f.slot}
                             for f in self.stage.fighters()],
                "rings": [r.index for r in self.stage.rings], "hazards": self.stage.hazards, "look": self.look,
                "user_mods": self.stage.user_mods,
                "rs": sim.RULES["ring_size"],
                "mine": {p.name: (p.fighter.id if p.fighter else None) for p in self.players.values()}}

    def check_matches(self):
        """A tournament match finished: record the winner, and start the next round when they're all done.
        Winner stays on: the loser is swapped out of that ring (only) for the next challenger, a moment later."""
        if not self.tournament or self.tournament.champion:
            return False
        if getattr(self.tournament, "kind", "") == "stays":
            self.tournament.join([n for n, _, _ in self.fighters_wanted()])  # (anyone who has just come in)
            for r in self.stage.rings:
                names = self.match_names.get(r.index)
                if names and r.match_over and not getattr(r, "recorded", False):
                    r.recorded = True
                    champ = next((f for f in r.fighters if f.wins >= self.stage.rounds_to_win), None)
                    if champ is None or len(r.fighters) != 2:
                        continue
                    winner = names[r.fighters.index(champ)]
                    swap = self.tournament.record(names[0], names[1], winner)
                    if swap:
                        loser, challenger = swap
                        self.swaps.append((r.index, loser, challenger, time.perf_counter() + 4.0))
                        self.stage_event(f"{winner} stays on! {challenger} is next in ring {r.index + 1}"
                                         if challenger != loser else f"{winner} stays on! {loser} tries again")
                        self.lesson_dirty = True
            return False
        done = False
        for r in self.stage.rings:
            names = self.match_names.get(r.index)
            if names and r.match_over and not getattr(r, "recorded", False):
                r.recorded = True
                champ = next((f for f in r.fighters if f.wins >= self.stage.rounds_to_win), None)
                if champ is None or len(r.fighters) != 2:
                    continue
                winner = names[r.fighters.index(champ)]  # (the fighters are in the same order as the names)
                done |= self.tournament.record(names[0], names[1], winner)
        if done:
            if self.tournament.champion:
                self.stage_event(f"{self.tournament.champion} IS THE CHAMPION!")
            else:
                self.stage_event(f"Next: the {self.tournament.title()}")
            return True
        return False

    def do_swaps(self):
        """Winner stays on: swaps that are due. The loser's fighter leaves the ring, the challenger's comes in
        (built from their design as it is now), and the ring starts a new match. Returns True if any happened."""
        now = time.perf_counter()
        due = [s for s in self.swaps if s[3] <= now]
        self.swaps = [s for s in self.swaps if s[3] > now]
        wanted = {n: (d, p) for n, d, p in self.fighters_wanted()}
        for ring_index, loser, challenger, _ in due:
            ring = next((r for r in self.stage.rings if r.index == ring_index), None)
            if ring is None:
                continue
            names = list(self.match_names.get(ring_index, ()))
            for f in list(ring.fighters):
                if f.owner == loser or f.owner not in names:
                    for p in self.players.values():
                        if p.fighter is f:
                            p.fighter = None
                    ring.remove_fighter(f)
            if challenger in wanted and challenger not in [f.owner for f in ring.fighters]:
                d, p = wanted[challenger]
                self.place(ring, challenger, d, p)
            stay = [f.owner for f in ring.fighters if f.owner != challenger]
            self.match_names[ring_index] = (stay[0] if stay else "", challenger)
            ring.recorded = False
            ring.label = self.tournament.title(ring_index) if self.tournament else "MATCH"
        if due:
            self.roster_version += 1
        return bool(due)

    async def delete_learner(self, username):
        name = fight_profiles.clean_name(username)
        for ws, q in list(self.players.items()):
            if q.role == "learner" and fight_profiles.slug(q.name) == fight_profiles.slug(name):
                del self.players[ws]
                await ws.close(4007, "Your account has been deleted by the teacher.")
        text = self.teaching.delete_learner(name)
        gone = fight_profiles.slug(name)
        if any(v and fight_profiles.slug(v) == gone for v in self.mod_makers.values()):  # their mods stay, unnamed
            self.mod_makers = {k: "" if fight_profiles.slug(v) == gone else v for k, v in self.mod_makers.items()}
            ai_pipeline.save_user_mod_makers(self.mod_makers)
        for votes in (self.mod_votes, self.arena_votes):
            for k in votes:
                votes[k] = [n for n in votes[k] if fight_profiles.slug(n) != gone]
        self.rebuild_stage()
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
            if key != seen:
                seen, presence = key, {}
                allowed = set(mine.get("learners", [])) if mine else set()
                self.group, self.mod_votes, self.arena_votes = sorted(allowed), {}, {}  # a new session: new votes
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in allowed:
                        self.players.pop(ws, None)
                        await ws.close(4009, "The session has ended." if not mine else "You aren't in this group.")
                if mine:
                    self.teaching.apply_lesson(int(mine.get("lesson", 1)))
                    self.rebuild_stage()
                    self.stage_event(f"Session started: {mine.get('group', '')}, lesson {mine.get('lesson', 1)}")
                else:
                    self.rebuild_stage()
                    self.stage_event("The session has ended")
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
            ready = wanted if wanted and wanted != fight_version.CODE else None
            if ready != self.live_ready:
                self.live_ready = ready
                for ws, p in list(self.players.items()):
                    if ready and p.role == "teacher":
                        await self.send(ws, {"type": "live_update", "id": ready})
            await asyncio.sleep(10)

    async def physics_loop(self):
        next_step, steps, next_round_at = time.perf_counter(), 0, None
        while True:
            next_step += sim.STEP
            if not self.paused:
                self.stage.step()
            steps += 1
            if steps % 30 == 0:  # twice a second: missions that are checked over time, and the tournament
                self.teaching.tick(self.stage.time)
                if next_round_at is None and self.check_matches():
                    next_round_at = time.perf_counter() + (4.0 if not self.tournament.champion else 9999)
                    await self.broadcast_lesson()
                if self.swaps and self.do_swaps():
                    await self.broadcast_lesson()
                elif getattr(self, "lesson_dirty", False):
                    self.lesson_dirty = False
                    await self.broadcast_lesson()
            if next_round_at is not None and time.perf_counter() > next_round_at:
                next_round_at = None
                self.rebuild_stage()  # the next round of the tournament
                await self.broadcast_lesson()
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
                if backed_up(ws):  # a window that has stopped reading (a closed laptop lid): skip it, don't wait
                    continue
                if sent_version.get(ws) != self.roster_version:
                    roster = roster or self.roster()
                    await self.send(ws, roster)
                    sent_version[ws] = self.roster_version
                try:
                    await ws.send(state)
                except websockets.ConnectionClosed:
                    pass


def backed_up(ws, limit=256 * 1024):
    """True if a window hasn't read what it was sent (so sending more would only make everyone wait)."""
    transport = getattr(ws, "transport", None)
    try:
        return transport is not None and transport.get_write_buffer_size() > limit
    except Exception:
        return False


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
        return "JOIN_CODE and TEACHER_CODE must be set."
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
    ap.add_argument("--port", type=int, default=8781)
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
            raise SystemExit("Fight Lab server not started: " + problem)
    OPEN_SIGNUP = os.environ.get("FIGHTLAB_OPEN_SIGNUP") == "1" or not CLASS_SERVER
    server = FightServer(args.lesson)
    if CLASS_SERVER:  # (the front door tells the Club Coders app which code this class runs)
        with open(os.path.join(fight_teaching.DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(fight_version.CODE)
    async with websockets.serve(server.handler, args.bind, args.port):
        if CLASS_SERVER:
            print(f"Fight Lab class server {fight_version.VERSION} on {args.bind}:{args.port}. "
                  f"Accounts are made by the teacher.")
        else:
            print(f"Fight Lab laptop test server on {args.bind}:{args.port}. "
                  f"Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}. A new username makes a profile.")
        await asyncio.gather(server.physics_loop(), server.send_loop(), server.watch_live(), server.watch_desk())


if __name__ == "__main__":
    asyncio.run(main())
