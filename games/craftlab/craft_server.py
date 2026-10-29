"""The Craft Lab class server (CHANGE 200): the world everyone's window is a view of, and the lessons round it.

    python craft_server.py                       a laptop test server (codes CLUB42 and TEACH99)
    python craft_server.py --class-server        the real one (JOIN_CODE and TEACHER_CODE set, behind Caddy)

City Lab's server, for a world of blocks: 60 times a second it takes each window's latest numbered input
(engine.predict.ServerInputQueue), steps the game (craft_game.Game: everyone's movement with craft_sim's step, which
every window predicts its own player with, their Health, Energy and Shield, the creatures, the Craft Bots and their learners'
brains, the world's slow things), and 30 times a second sends each window a binary snapshot of the players, Bots,
creatures and dropped things near it (engine.wire), stamped with that window's last input applied. Everything else is
JSON: the world itself when a window joins (packed, in parts), each block that changes (to everyone), each
player's inventory and open screen, sounds, bursts and words, the lesson. The teaching layer is the engine's
(engine/teaching.py) with Craft Lab's own checks in craft_teaching.py.

A window digs and places at once and the server keeps or refuses it (a block it refuses goes back for that window).
The world is kept on disk (data/world) every two minutes and when the server stops; each learner's inventory,
place, spawn and Bot go in their profile, so they carry on next lesson.
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

import craft_version
sys.path.insert(0, craft_version.ENGINE_HOME)
from engine import club_ticket, gfx_tiers, predict, rw_sound, schema, wire  # noqa: E402
from engine.outbox import Outboxes  # noqa: E402
from engine.seats import Seats, dropped  # noqa: E402
from engine import lifecycle, tick_stats  # noqa: E402

import ai_pipeline  # noqa: E402
import craft_blocks as B  # noqa: E402
import craft_brain  # noqa: E402
import craft_design as design  # noqa: E402
import craft_game  # noqa: E402
import craft_items as items  # noqa: E402
import craft_missions as cm  # noqa: E402
import craft_mods  # noqa: E402
import craft_profiles  # noqa: E402
import craft_sim as sim  # noqa: E402
import craft_teaching  # noqa: E402
import craft_world  # noqa: E402

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
GAME_ID = "craftlab"
TICKET_KEY = os.environ.get("CLUBCODERS_TICKET_KEY")
LIVE_FILE = os.environ.get("CLUBCODERS_LIVE_FILE", "")
DESK_INBOX = os.environ.get("CLUBCODERS_DESK_INBOX")
DATA = craft_teaching.DATA
WORLD_DIR = os.path.join(DATA, "world")
CLASS_SERVER = False
OPEN_SIGNUP = False
BAD_LOGINS = craft_profiles.RateLimit(10)
BRAIN_UPLOAD_GAP = 3.0
MAX_LEARNERS = 30
MAX_PLAYERS = 40
SEND_RATE = 1 / 30
STATE_RATE = 1.0          # the "state" message (the time, the roster) at least this often
SAVE_EVERY = 120.0
SEE = 96.0                # a window is sent the things within this many metres of its player
PART = 256 * 1024         # the world goes in parts of this many bytes
KIND_WORLD = 9            # (a binary frame's first byte: a part of the world)
T0 = time.perf_counter()
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230), (240, 120, 40),
           (60, 200, 200), (230, 90, 160)]
TEACHER_COLOUR = (180, 90, 230)
SCHEMA = wire.Schema("craft", sim.SCHEMA_FIELDS)
IDLE = (0.0, 0.0, 0)
CARD_NOTE_FILE = os.path.join(DATA, "card_note_saved.json")
GFX_MAX_FILE = os.path.join(DATA, "gfx_max_saved.json")
LIMITS_FILE = os.path.join(DATA, "limits_saved.json")
MISSIONS_FILE = os.path.join(DATA, "mission_settings.json")
MISSION_KEYS = ("mode", "game_mode", "mobs", "time", "teacher_player", "designs_locked", "rules", "hazards", "tools",
                "limits", "user_mods", "mods_in_vote", "arena_in_vote")
TIMES = {"dawn": 0.95, "day": 0.3, "dusk": 0.62, "night": 0.8}


def clean_lesson(L):
    """A lesson (or saved mission settings) with the names from before CHANGE 207 as they are now: survival and
    creative are challenge and sandbox, the hunger rule and hazard is energy."""
    if not isinstance(L, dict):
        return L
    if L.get("game_mode") in B.MODE_ALIASES:
        L["game_mode"] = B.mode_of(L["game_mode"])
    for key in ("rules", "hazards"):
        if isinstance(L.get(key), dict) and "hunger" in L[key]:
            L[key].setdefault("energy", L[key].pop("hunger"))
    return L

WEEK1_LESSON = {
    "lesson_number": 1,
    "mode": "practice",
    "game_mode": "challenge",      # challenge or sandbox (for the learners; the teacher can be either)
    "mobs": False,                 # creatures (with the hazard "mobs")
    "time": "cycle",               # cycle (day and night come round), or held at dawn, day, dusk or night
    "teacher_player": True,
    "designs_locked": False,
    "rules": {"keep_items": True, "blasts": False, "energy": True, "falls_hurt": True},
    "hazards": dict(cm.NO_HAZARDS),
    "ai_card_note": "",
    "gfx_max": None,
    "limits": design.default_limits(),
    "user_mods": {},
    "sound": dict(rw_sound.DEFAULT_SOUND),
    "tools": copy.deepcopy(cm.LESSONS[1]["tools"]),
    "brains": False,
}


def server_ms():
    return int((time.perf_counter() - T0) * 1000) & 0xFFFFFFFF


def keep_presses(late, nxt):
    return (nxt[0], nxt[1], nxt[2] | late[2])


class Log:
    """What the teaching layer calls the world: its events ((time, words): the news) and the time; the players'
    game records are the units it checks."""

    def __init__(self, server):
        self.server = server
        self.events = []

    @property
    def time(self):
        return self.server.game.tick * sim.STEP

    def units(self):
        return [p.unit for p in self.server.players.values() if p.unit is not None]


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = design.default_design(f"{name[:8]} Bot" if role == "learner" else "Teacher Bot", colour)
        self.start_colour = list(colour)
        self.pid = None
        self.unit = None           # their craft_game.Player
        self.inputs = predict.ServerInputQueue(idle=IDLE, merge=keep_presses)
        self.profile = None
        self.perf = None
        self.ctrl_seq = None
        self.seen_snap = None
        self.seen_at = None
        self.brain_at = -BRAIN_UPLOAD_GAP


class CraftServer:
    def __init__(self, lesson_file=None, fresh=False):
        self.lesson = copy.deepcopy(WEEK1_LESSON)
        problems = craft_mods.use_mods()
        for msg in problems:
            print("Mods not used:", msg, flush=True)
        try:
            self.world_mod = craft_mods.load_world()
            self.lesson["rules"].update(craft_mods.load_rules())
        except craft_mods.ModError as e:
            print("Mods not used:", e, flush=True)
            self.world_mod = {"seed": 2026, "size": "medium", "mode": "challenge", "mobs": True, "day_length": 900}
        carried = os.path.join(DATA, "lesson_carried.json")
        if not lesson_file and os.path.exists(carried):
            lesson_file = carried
        if lesson_file and os.path.exists(lesson_file):
            with open(lesson_file) as f:
                saved = json.load(f)
            self.lesson.update({k: v for k, v in clean_lesson(saved).items() if k in WEEK1_LESSON or k in MISSION_KEYS})
            if lesson_file == carried:
                os.remove(carried)
        try:
            with open(MISSIONS_FILE, encoding="utf-8") as f:
                self.mission_settings = json.load(f)
            if not isinstance(self.mission_settings, dict):
                self.mission_settings = {}
            for v in self.mission_settings.values():
                clean_lesson(v)
        except (OSError, ValueError):
            self.mission_settings = {}
        self.lesson["saved_missions"] = self.saved_missions()
        try:
            with open(LIMITS_FILE, encoding="utf-8") as f:
                saved_limits = json.load(f)
        except (OSError, ValueError):
            saved_limits = None
        self.lesson["limits"] = design.clean_limits(saved_limits, design.clean_limits(self.lesson.get("limits")))
        for path, key, fix in ((CARD_NOTE_FILE, "ai_card_note", lambda d: str(d.get("note", ""))[:300]),
                               (GFX_MAX_FILE, "gfx_max", lambda d: gfx_tiers.class_max(d.get("gfx_max")))):
            try:
                with open(path, encoding="utf-8") as f:
                    self.lesson[key] = fix(json.load(f))
            except (OSError, ValueError, AttributeError):
                pass
        self.players = {}
        self.outboxes = Outboxes()
        self.seats = Seats()
        self.watchdog = lifecycle.Watchdog()
        self.ticks = tick_stats.TickStats("Craft Lab")
        self.group = []
        self.mod_votes, self.arena_votes = {}, {}
        self.mod_makers = ai_pipeline.user_mod_makers()
        self.warnings = []
        self.teacher_design = design.default_design("Teacher Bot", TEACHER_COLOUR)
        self.design_for_everyone = None
        self.paused = False
        self.roster_version = 0
        self.snap_seq = 0
        self.lesson_dirty = False
        self.saved_at = time.perf_counter()
        self.log = Log(self)
        world, extra = (None, {}) if fresh else craft_world.World.load(WORLD_DIR)
        if world is None:
            t0 = time.perf_counter()
            world = craft_world.World(self.world_mod["size"], self.world_mod["seed"])
            print(f"Craft Lab: a new world, seed {world.seed}, in {time.perf_counter() - t0:.1f} s", flush=True)
            extra = {}
        self.game = craft_game.Game(world, self.game_rules())
        self.game.load_extra(extra)
        self.packed = None
        self.teaching = craft_teaching.Teaching(self)
        if not lesson_file:
            self.teaching.apply_lesson(1)
        self.use_mission_settings()
        self.rebuild()

    def game_rules(self):
        L = self.lesson
        return {"mode": L.get("game_mode", "challenge"), "mobs": bool(L["hazards"].get("mobs") and L.get("mobs", True)),
                "pvp": False, "day_length": self.world_mod.get("day_length", craft_game.DAY_SECONDS),
                "time_runs": L.get("time", "cycle") == "cycle",
                "energy": bool(L["hazards"].get("energy", True)) and L["rules"].get("energy", True),
                **{k: bool(L["rules"].get(k, craft_game.DEFAULT_RULES[k])) for k in ("keep_items", "blasts", "falls_hurt")}}

    # ---------- the lesson's saved settings ----------
    def use_mission_settings(self):
        saved = self.mission_settings.get(str(self.lesson.get("lesson_number", 1)))
        self.lesson["brains"] = bool(self.lesson.get("tools", {}).get("brains"))
        if not isinstance(saved, dict):
            return False
        for key in MISSION_KEYS:
            if key in saved:
                self.lesson[key] = copy.deepcopy(saved[key])
        self.lesson["limits"] = design.clean_limits(self.lesson.get("limits"))
        for k, v in cm.NO_HAZARDS.items():
            self.lesson["hazards"].setdefault(k, v)
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

    # ---------- who is here ----------
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
        """The game from the lesson: its rules, and a player for everyone who should be in the world (a Sandbox or
        Challenge one, as the lesson says for learners)."""
        g = self.game
        g.rules.update(self.game_rules())
        if self.lesson.get("time", "cycle") in TIMES:
            g.time = (math.floor(g.time / g.rules["day_length"]) + TIMES[self.lesson["time"]]) * g.rules["day_length"]
        wanted = self.people_wanted()
        for p in list(self.players.values()) + self.seats.players():
            if p not in wanted and p.pid is not None and p.pid in g.players:
                self.keep_player(p)
                g.remove_player(p.pid)
                g.bots.pop(craft_game.craft_bot.BOT_BASE + p.pid, None)
                p.pid, p.unit = None, None
        for p in wanted:
            if p.pid is None:
                used = {q.pid for q in list(self.players.values()) + self.seats.players() if q.pid is not None}
                p.pid = next((i for i in range(MAX_PLAYERS) if i not in used), None)
                if p.pid is None:
                    continue
            creative = p.role == "teacher" or self.lesson.get("game_mode") == "sandbox"
            if p.pid not in g.players:
                saved = (p.profile or {}).get("craft") if p.role == "learner" else None
                p.unit = g.add_player(p.pid, p.name, creative=creative, saved=saved)
                bot = (saved or {}).get("bot")
                if bot and bot.get("dock"):
                    g.add_bot(p.pid, tuple(bot["dock"]), bot)
            else:
                p.unit = g.players[p.pid]
                if p.unit.creative != creative:
                    p.unit.creative = creative
                    g.inv_changed(p.pid)
            g.designs[p.pid] = design.fit_design(p.design)
        for p in wanted:
            if not self.seats.holding(p):
                self.teaching.attach(p)
        self.roster_version += 1

    def keep_player(self, p):
        """A learner's place in the world, inventory, spawn and Bot into their profile (for next time)."""
        if p.role != "learner" or p.profile is None or p.pid is None or p.pid not in self.game.players:
            return
        data = self.game.players[p.pid].to_save()
        bot = self.game.bot_of(p.pid)
        if bot is not None:
            data["bot"] = bot.to_save()
        p.profile["craft"] = data
        try:
            craft_profiles.save(p.profile)
        except OSError:
            pass

    def roster(self):
        return {"type": "roster", "version": self.roster_version,
                "players": {str(p.pid): {"name": p.name, "colour": p.design["colour"], "role": p.role,
                                         "wear": self.wear_of(p.pid)}
                            for p in list(self.players.values()) + self.seats.players() if p.pid is not None},
                "bots": {str(b.id): {"name": self.game.designs.get(b.owner, {}).get("name", "Bot"),
                                     "colour": self.game.designs.get(b.owner, {}).get("colour", [200, 200, 200]),
                                     "owner": b.owner} for b in self.game.bots.values()},
                "perf": {p.name: p.perf for p in self.players.values() if p.perf}}

    def wear_of(self, pid):
        """The suit a player wears, as three item ids (0: nothing there)."""
        q = self.game.players.get(pid)
        return [a[0] if a else 0 for a in q.suit] if q is not None else [0] * items.SUIT

    def rules_msg(self):
        return {"stats": design.STATS, "points_total": design.POINTS_TOTAL, "stat_min": design.STAT_MIN,
                "stat_max": design.STAT_MAX, "settings": design.SETTINGS, "stat_notes": design.STAT_NOTES,
                "full": design.full_limits(), "max_people": MAX_PLAYERS}

    def limits_for(self, player):
        return design.full_limits() if player.role == "teacher" else self.lesson["limits"]

    def mod_blueprint_outputs(self):
        try:
            return {B.new_key(r["makes"]) for r in craft_mods.load_blueprints()}
        except craft_mods.ModError:
            return set()

    def blueprints_msg(self):
        return {"type": "blueprints", "list": items.blueprints()}

    def mod_block_keys(self):
        return {b["key"] for b in B.BLOCKS if b.get("mod")}

    def world_parts(self):
        """The world packed for a window joining (worked out again only after the blocks have changed)."""
        if self.packed is None or self.packed[0] != self.game.tick:
            p = self.game.world.pack()
            self.packed = (self.game.tick, p)
        return self.packed[1]

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
        if CLASS_SERVER and hello.get("version") != craft_version.VERSION:
            page = craft_version.DOWNLOAD_PAGE or "your teacher"
            await ws.close(4006, f"Out of date: download Club Coders {craft_version.VERSION} from {page}"[:120])
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
                    profile, is_new = craft_profiles.ticket_profile(ticket["name"]), False
                else:
                    profile, is_new = await asyncio.to_thread(craft_profiles.login, hello.get("name", ""),
                                                              hello.get("password", ""), OPEN_SIGNUP)
            except craft_profiles.LoginError as e:
                BAD_LOGINS.failed(where)
                await ws.close(4004, str(e)[:120])
                return
            name = profile["name"]
        else:
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(ticket["name"] if ticket else hello.get("name", "")))[:12] or "Teacher"
        old = next((q for q in self.players.values()
                    if q.role == role and craft_profiles.slug(q.name) == craft_profiles.slug(name)), None)
        if old is not None:
            await self.outboxes.close(old.ws, 4005, "you logged in again somewhere else")
            self.players.pop(old.ws, None)
        if role == "learner" and len(self.learners()) >= MAX_LEARNERS:
            await ws.close(4003, f"the class is full ({MAX_LEARNERS} learners)")
            return
        colour = COLOURS[len(self.learners()) % len(COLOURS)] if role == "learner" else TEACHER_COLOUR
        p = Player(ws, role, name, colour)
        p.profile = profile
        held = self.seats.take(craft_profiles.slug(name)) if role == "learner" else None
        if old is not None:
            p.pid, p.unit = old.pid, old.unit
        elif held is not None:
            p.pid, p.unit = held.pid, held.unit
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
        self.log.events.append((self.log.time, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "me": p.pid, "lesson": self.lesson,
                             "design": p.design, "rules": self.rules_msg(), "game_rules": self.game.rules,
                             "prefs": (profile or {}).get("prefs", {}), "new_profile": bool(profile and is_new),
                             "code": craft_version.CODE, "mods": [b for b in B.BLOCKS if b.get("mod")],
                             "live_ready": getattr(self, "live_ready", None) if role == "teacher" else None})
        await self.send_world(ws)
        await self.send(ws, self.blueprints_msg())
        await self.send(ws, self.game.inventory_msg(p.pid) or {"type": "inventory"})
        await self.send(ws, self.state_msg())
        await self.broadcast_lesson()
        await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
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
                self.keep_player(p)
                self.teaching.save()
                if role == "learner" and dropped(ws) and p.pid is not None:
                    self.seats.hold(craft_profiles.slug(name), p)
                    print(f"- {name} dropped: their place is kept {self.seats.seconds:.0f} s", flush=True)
                    self.roster_version += 1
                else:
                    print(f"- {name} left", flush=True)
                    self.rebuild()
                await self.broadcast_lesson()

    async def send_world(self, ws):
        """The whole world for a window joining: a header, the blocks and the meta in parts, then the end."""
        packed = self.world_parts()
        data = packed["blocks"] + packed["meta"]
        parts = [data[i:i + PART] for i in range(0, len(data), PART)]
        await self.send(ws, {"type": "world_head", "size": packed["size"], "seed": packed["seed"],
                             "spawn": packed["spawn"], "blocks_len": len(packed["blocks"]), "parts": len(parts)})
        for i, part in enumerate(parts):
            await self.send(ws, bytes([KIND_WORLD]) + i.to_bytes(2, "little") + part)
        await self.send(ws, {"type": "world", "time": self.game.day_t,
                             "lockers": len(self.game.lockers)})

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
    GAME_ACTIONS = {"look", "select", "dig_start", "dig", "place", "right", "use_item", "attack", "click", "close",
                    "drop", "pick", "creative_take", "respawn", "build", "sort", "locker_name", "tab", "use_mob"}

    async def on_message(self, p, m):
        kind = m.get("type")
        if kind in self.GAME_ACTIONS:
            if p.pid is not None and not self.paused:
                self.game.action(p.pid, m)
                await self.flush()
            return
        if kind == "brain":
            if p.role == "learner" and not self.lesson.get("tools", {}).get("brains", True):
                await self.send(p.ws, {"type": "notice", "text": "Brains aren't switched on for this mission yet."})
                return
            await self.upload_brain(p, str(m.get("source", "")))
            return
        if kind == "autopilot":
            r = self.teaching.record(p.name)
            if r.brain is None:
                await self.send(p.ws, {"type": "notice", "text": "Upload your Bot's brain first (press U)."})
                return
            r.autopilot = bool(m["on"]) if "on" in m else not r.autopilot
            if r.autopilot:
                r.brain.error, r.brain.started, r.brain.memory = None, None, {}
            self.teaching.attach(p)
            self.teaching.save_profile(p.name)
            await self.send(p.ws, {"type": "notice", "text": "Autopilot on: your Craft Bot is running your brain."
                                   if r.autopilot else "Autopilot off."})
            await self.deliver([(p.ws, self.teaching.missions_msg(p))])
            return
        if kind not in ("control", "ping", "perf", "design", "design_for"):
            replies = self.teaching.on_message(p, m)
            if replies is not None:
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
        elif kind == "design":
            await self.on_design(p, m)
        elif p.role == "teacher":
            await self.teacher_command(p, m)

    async def on_design(self, p, m):
        if self.lesson["designs_locked"] and p.role == "learner":
            await self.send(p.ws, {"type": "design_result", "ok": False, "design": p.design,
                                   "problems": ["The teacher has locked designs for now."]})
            return
        hack = bool(m.get("code")) and p.role == "learner" and bool(self.lesson["tools"].get("code_view"))
        new = self.clean_design(p, m.get("design", {}), everything=hack or p.role == "teacher")
        limits = self.limits_for(p)
        if hack:
            limits = design.code_limits(limits)
        problems = design.check_design(new, limits)
        old = p.design
        outside = schema.outside_lesson(design.schema(), old, new, self.lesson["tools"]) if hack and not problems else []
        if not problems:
            p.design = new
            if p.pid is not None:
                self.game.designs[p.pid] = design.fit_design(new)
            self.roster_version += 1
            self.log.events.append((self.log.time, f"{p.name} rebuilt {new['name']}"))
        if p.unit is not None and not hasattr(p.unit, "hits"):  # (the engine's teaching layer notes a unit's hits
            p.unit.hits = 0                                      # at a build: a Craft Lab player has none)
        self.teaching.on_design(p, new, problems, not problems, old=old, by_code=bool(m.get("code")))
        if not problems and p.role == "learner":
            self.teaching.save_design(p.name, new)
        await self.send(p.ws, {"type": "design_result", "ok": not problems, "problems": problems, "design": p.design})
        await self.deliver(self.teaching.teacher_update() + ([(p.ws, self.teaching.missions_msg(p))]
                                                             if p.role == "learner" else []))
        if outside:
            self.warnings.append({"who": p.name, "time": time.strftime("%H:%M"), "changes": outside})
            t = self.teacher()
            if t:
                await self.send(t.ws, {"type": "warnings", "list": self.warnings[-200:]})

    def clean_design(self, p, d, everything=False):
        old, tools = p.design, self.lesson["tools"]
        d = d if isinstance(d, dict) else {}
        new = copy.deepcopy(old)
        new.setdefault("points", {})
        new.setdefault("settings", {})
        if everything or tools.get("name_and_colour"):
            if isinstance(d.get("name"), str):
                new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", d["name"]).strip()[:design.NAME_MAX] or old["name"]
            if isinstance(d.get("colour"), list):
                new["colour"] = d["colour"]
        pts = d.get("points") if isinstance(d.get("points"), dict) else d
        for k in design.STATS:
            if (everything or tools.get(k) or tools.get("points_table")) and k in pts:
                new["points"][k] = pts[k]
        return new

    async def build_for(self, p, d, quiet=False):
        new = copy.deepcopy(p.design)
        if isinstance(d.get("name"), str):
            new["name"] = re.sub(r"[^A-Za-z0-9 ]", "", d["name"]).strip()[:design.NAME_MAX] or new["name"]
        if "colour" in d:
            new["colour"] = d["colour"]
        pts = d.get("points") if isinstance(d.get("points"), dict) else d
        for key in design.STATS:
            if key in pts:
                new.setdefault("points", {})[key] = pts[key]
        problems = design.check_design(new, design.full_limits())
        if problems:
            if not quiet:
                await self.notice_teacher("Not built: " + "; ".join(problems))
            return problems
        p.design = new
        if p.pid is not None:
            self.game.designs[p.pid] = design.fit_design(new)
        self.teaching.save_design(p.name, new)
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
            loaded = await asyncio.to_thread(craft_brain.load_brain, source, p.name)
        except craft_brain.BrainError as e:
            loaded = e
        if self.players.get(p.ws) is not p:
            if not isinstance(loaded, Exception):
                loaded[0].close()
            return
        reply = self.teaching.upload_brain(p, source, loaded)
        await self.deliver([(p.ws, reply), (p.ws, self.teaching.missions_msg(p))] + self.teaching.teacher_update())

    async def teacher_command(self, t, m):
        kind = m.get("type")
        L = self.lesson
        g = self.game
        if kind == "delete_learner":
            await self.delete_learner(m.get("learner", ""))
        elif kind == "restart_server":
            self.save_world()
            self.teaching.save()
            self.carry_lesson()
            for ws in list(self.players):
                await self.send(ws, {"type": "notice", "big": True,
                                     "text": "THE SERVER IS RESTARTING to load changes\nyou'll reconnect in a few seconds"})
            await lifecycle.exit_after_closing(self.outboxes, self.players, 3)
        elif kind == "restart_clients":
            for ws, q in list(self.players.items()):
                if q.role == "learner":
                    await self.send(ws, {"type": "restart_client"})
        elif kind == "time":  # (T: on to the next of dawn, day, dusk, night, then the cycle again)
            order = ["dawn", "day", "dusk", "night", "cycle"]
            now = L.get("time", "cycle")
            L["time"] = order[(order.index(now) + 1) % len(order)] if now in order else "day"
            self.rebuild()
            await self.news({"dawn": "Dawn", "day": "Daytime", "dusk": "Dusk", "night": "Night falls",
                             "cycle": "Day and night come round again"}[L["time"]])
            await self.broadcast_lesson()
        elif kind == "mobs":
            L["hazards"]["mobs"] = not L["hazards"].get("mobs")
            L["mobs"] = True
            self.rebuild()
            await self.news("Creatures come out at night" if L["hazards"]["mobs"] else "No creatures")
            await self.broadcast_lesson()
        elif kind == "mode":
            L["game_mode"] = "sandbox" if L.get("game_mode") != "sandbox" else "challenge"
            self.rebuild()
            await self.news("SANDBOX: fly, any block, nothing hurts" if L["game_mode"] == "sandbox" else
                            "CHALLENGE: Health, Energy and Shield count")
            await self.broadcast_lesson()
        elif kind == "gather":  # (G: everyone to the teacher)
            me = g.players.get(t.pid) if t.pid is not None else None
            if me is not None:
                for q in g.players.values():
                    if q is not me:
                        q.state.update(x=me.state["x"] + (q.pid % 5 - 2) * 1.2, y=me.state["y"] + (q.pid // 5 % 5 - 2) * 1.2,
                                       z=me.state["z"], vx=0.0, vy=0.0, vz=0.0)
                        g.place_safely(q)
                await self.news("Everyone to the teacher")
        elif kind == "pause":
            self.paused = not self.paused
            await self.news("PAUSED" if self.paused else "GO!")
        elif kind == "kit":  # (K: a Bot dock and a stack of boards for everyone, to start Bot lessons quickly)
            for q in g.players.values():
                items.add(q.inv, B.ITEM_ID["dock"], 1)
                items.add(q.inv, B.ITEM_ID["boards"], 50)
                items.add(q.inv, B.ITEM_ID["glowstick"], 16)
                g.inv_changed(q.pid)
            await self.news("The teacher gave everyone a Bot dock, Boards and Glowsticks")
        elif kind == "new_world":
            try:
                seed = int(m.get("seed", 0)) or int(time.time()) % 1_000_000
            except (TypeError, ValueError):
                seed = int(time.time()) % 1_000_000
            size = m.get("size") if m.get("size") in craft_world.SIZES else self.world_mod.get("size", "medium")
            await self.new_world(seed, size)
        elif kind == "save_world":
            self.save_world()
            await self.notice_teacher("The world is saved.")
        elif kind == "design_for_all":
            d = m.get("design", {}) if isinstance(m.get("design"), dict) else {}
            built = [q.name for q in self.learners() if not await self.build_for(q, d, quiet=True)]
            self.design_for_everyone = d
            await self.notice_teacher(f"Built {d.get('name', '?')} for {', '.join(built) or 'nobody yet'}")
        elif kind == "design_for":
            q = next((x for x in self.learners() if x.name == m.get("learner")), None)
            if q is None:
                await self.notice_teacher("That learner isn't connected.")
                return
            await self.build_for(q, m.get("design", {}) if isinstance(m.get("design"), dict) else {})
        elif kind == "lesson":
            await self.update_lesson(m.get("lesson", {}) if isinstance(m.get("lesson"), dict) else {})
        elif kind == "save_lesson":
            self.save_mission_settings()
            await self.broadcast_lesson()
        elif kind == "restore_lesson":
            self.teaching.apply_lesson(L.get("lesson_number", 1))
            self.rebuild()
            await self.broadcast_lesson()

    async def news(self, text):
        self.game.events.append(("news", text))
        await self.flush()

    async def new_world(self, seed, size):
        """A new island for everyone (the old one kept as world_old), every window sent it."""
        self.save_world()
        try:
            old = WORLD_DIR + "_old"
            if os.path.isdir(old):
                import shutil
                shutil.rmtree(old, ignore_errors=True)
            if os.path.isdir(WORLD_DIR):
                os.replace(WORLD_DIR, old)
        except OSError:
            pass
        world = await asyncio.to_thread(craft_world.World, size, seed)
        rules = self.game.rules
        self.game = craft_game.Game(world, rules)
        self.packed = None
        for p in list(self.players.values()) + self.seats.players():
            p.pid, p.unit = None, None
            if p.profile is not None:
                p.profile.pop("craft", None)
        self.rebuild()
        for ws, p in list(self.players.items()):
            await self.send(ws, {"type": "welcome", "role": p.role, "name": p.name, "me": p.pid, "lesson": self.lesson,
                                 "design": p.design, "rules": self.rules_msg(), "game_rules": self.game.rules,
                                 "code": craft_version.CODE, "new_world": True})
            await self.send_world(ws)
            await self.send(ws, self.blueprints_msg())
            await self.send(ws, self.game.inventory_msg(p.pid) or {"type": "inventory"})
        await self.news(f"A new world (seed {seed})")

    async def update_lesson(self, update):
        L = self.lesson
        if isinstance(update.get("limits"), dict):
            L["limits"] = design.clean_limits(update["limits"], L["limits"])
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(LIMITS_FILE, "w", encoding="utf-8") as f:
                    json.dump(L["limits"], f)
            except OSError:
                pass
        if isinstance(update.get("ai_card_note"), str):
            note = "".join(ch if ch >= " " and ch != "\x7f" else " " for ch in update["ai_card_note"])
            L["ai_card_note"] = " ".join(note.split())[:300]
        if "gfx_max" in update:
            L["gfx_max"] = gfx_tiers.class_max(update["gfx_max"])
            try:
                os.makedirs(DATA, exist_ok=True)
                with open(GFX_MAX_FILE, "w", encoding="utf-8") as f:
                    json.dump({"gfx_max": L["gfx_max"]}, f)
            except OSError:
                pass
        for key in ("teacher_player", "designs_locked"):
            if key in update:
                L[key] = bool(update[key])
        if B.mode_of(update.get("game_mode")) in ("challenge", "sandbox"):
            L["game_mode"] = B.mode_of(update["game_mode"])
        if update.get("time") in list(TIMES) + ["cycle"]:
            L["time"] = update["time"]
        clean_lesson(update)
        if isinstance(update.get("rules"), dict):
            for k, v in update["rules"].items():
                if k in craft_mods.RULE_LIMITS:
                    L["rules"][k] = bool(v)
        for key in ("hazards", "tools"):
            for k, v in (update.get(key, {}) if isinstance(update.get(key), dict) else {}).items():
                if key == "hazards" and k not in cm.NO_HAZARDS:
                    continue
                if key == "tools" and k not in L["tools"]:
                    continue
                L[key][k] = bool(v)
        L["brains"] = bool(L["tools"].get("brains"))
        if "brains" in update:
            L["tools"]["brains"] = L["brains"] = bool(update["brains"])
        if "show_missions" in update:
            L["show_missions"] = self.paused = bool(update["show_missions"])
        if isinstance(update.get("sound"), dict):
            L["sound"] = rw_sound.sound_settings(L.get("sound"), update["sound"])
        self.rebuild()
        await self.broadcast_lesson()

    def carry_lesson(self):
        try:
            os.makedirs(DATA, exist_ok=True)
            with open(os.path.join(DATA, "lesson_carried.json"), "w") as f:
                json.dump(self.lesson, f, indent=2)
        except OSError:
            pass

    def reload_mods(self, written):
        """An approved AI change's mod files: the learners' blocks and blueprints into the game at once (a new block
        reaches the windows with the next lesson message: their atlas is drawn again), the rules, their Bots."""
        if any(f in written for f in ("mods/blocks.py", "mods/blueprints.py")):
            for msg in craft_mods.use_mods():
                print("Mods not used:", msg, flush=True)
            self.blueprints_dirty = True
        if "mods/rules.py" in written:
            try:
                self.lesson["rules"].update(craft_mods.load_rules())
            except craft_mods.ModError as e:
                print("Mods not used:", e, flush=True)
        for p in self.learners():
            if f"mods/bots/{craft_teaching.slug(p.name)}.py" in written:
                p.design = self.teaching.load_saved_design(p.name) or p.design
        self.rebuild()
        self.log.events.append((self.log.time, "An approved AI change is now in the game"))
        self.lesson_dirty = True

    def user_mods_msg(self):
        here = {p.name for p in self.learners()} | set(self.group)
        return {"makers": {k: v for k, v in self.mod_makers.items() if k in design.USER_MODS},
                "votes": {}, "arena_votes": {}, "here": sorted(here)}

    async def broadcast_lesson(self):
        msg = {"type": "lesson", "lesson": self.lesson, "mods": self.user_mods_msg(),
               "class": [{"name": p.name, "role": p.role, "design": p.design} for p in self.players.values()],
               "blocks": [b for b in B.BLOCKS if b.get("mod")], "tournament": None}
        for ws in list(self.players):
            await self.send(ws, msg)

    async def delete_learner(self, username):
        name = craft_profiles.clean_name(username)
        for ws, q in list(self.players.items()):
            if q.role == "learner" and craft_profiles.slug(q.name) == craft_profiles.slug(name):
                del self.players[ws]
                await self.outboxes.close(ws, 4007, "Your account has been deleted by the teacher.")
        text = self.teaching.delete_learner(name)
        self.rebuild()
        t = self.teacher()
        if t:
            await self.deliver([(t.ws, {"type": "notice", "text": text})] + self.teaching.teacher_update())
        await self.broadcast_lesson()

    # ---------- what happened, to the windows ----------
    def by_pid(self, pid):
        return next((p for p in self.players.values() if p.pid == pid), None)

    async def flush(self):
        """The game's events and the world's block changes, sent: to the player they are for, to those near, or to
        everyone."""
        g = self.game
        changes = g.world.take_changes()
        if changes:
            last = {}
            for c in changes:
                last[c[:3]] = c
            msg = json.dumps({"type": "blocks", "list": [list(map(int, c)) for c in last.values()]}, separators=(",", ":"))
            for ws in list(self.players):
                await self.send(ws, msg)
        inv, boxes = set(), set()
        for ev in g.events:
            kind = ev[0]
            if kind == "say":
                p = self.by_pid(ev[1])
                if p is not None:
                    await self.send(p.ws, {"type": "say", "text": ev[2]})
            elif kind == "news":
                for ws in list(self.players):
                    await self.send(ws, {"type": "news", "text": ev[1]})
            elif kind in ("sound", "burst"):
                x, y, z = ev[2:5] if kind == "sound" else ev[1:4]
                reach = 34.0 if kind == "sound" else 50.0
                msg = {"type": "sound", "name": ev[1], "at": [round(x, 2), round(y, 2), round(z, 2)],
                       "v": ev[5] if len(ev) > 5 else 1.0} if kind == "sound" else \
                    {"type": "burst", "at": [x, y, z], "tile": ev[4], "n": ev[5]}
                for ws, p in list(self.players.items()):
                    s = g.players[p.pid].state if p.pid in g.players else None
                    if s is not None and math.dist((s["x"], s["y"], s["z"]), (x, y, z)) < reach:
                        await self.send(ws, msg)
            elif kind == "inv":
                inv.add(ev[1])
            elif kind == "open":
                inv.add(ev[1])
            elif kind == "box":
                boxes.add(ev[1] if not isinstance(ev[1], list) else tuple(ev[1]))
            elif kind == "block":
                p = self.by_pid(ev[1])
                if p is not None:
                    x, y, z = ev[2:5]
                    await self.send(p.ws, {"type": "blocks", "list": [[x, y, z, g.world.get(x, y, z), g.world.get_meta(x, y, z)]]})
            elif kind == "wear":  # (what someone wears changed: everyone's windows dress them)
                self.roster_version += 1
            elif kind == "bubble":
                for ws in list(self.players):
                    await self.send(ws, {"type": "bubble", "id": ev[1], "text": ev[2]})
            elif kind in ("armed", "ring", "streak"):  # (an Overload Cell armed, its pulse, a Glitch pulled home)
                at = ev[1:4]
                msg = {"type": kind, "at": [round(v, 2) for v in at], "more": [round(v, 2) for v in ev[4:]]}
                for ws, p in list(self.players.items()):
                    s = g.players[p.pid].state if p.pid in g.players else None
                    if s is not None and math.dist((s["x"], s["y"], s["z"]), at) < 80:
                        await self.send(ws, msg)
        g.events = []
        for pid, q in g.players.items():
            if q.open is not None and (q.open[1] in boxes or (q.open[0], q.open[1]) in boxes):
                inv.add(pid)
        for pid in inv:
            p = self.by_pid(pid)
            if p is not None:
                await self.send(p.ws, g.inventory_msg(pid), "inventory")

    def state_msg(self):
        g = self.game
        return {"type": "state", "t": round(g.day_t, 4), "speed": g.speed, "paused": self.paused, "rules": g.rules,
                "sm": server_ms(), "events": [[t, e] for t, e in self.log.events[-4:]]}

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
            await self.flush()
            steps += 1
            if steps % 30 == 0:
                self.teaching.tick(self.game.tick * sim.STEP)
                for p in self.seats.expired():
                    print(f"- {p.name} didn't come back: their place has gone", flush=True)
                    self.keep_player(p)
                    self.rebuild()
                    await self.broadcast_lesson()
                if self.lesson_dirty:
                    self.lesson_dirty = False
                    await self.broadcast_lesson()
            if time.perf_counter() - self.saved_at > SAVE_EVERY:
                self.saved_at = time.perf_counter()
                await asyncio.to_thread(self.save_world)
                for p in self.learners():
                    self.keep_player(p)
            self.ticks.step(time.perf_counter() - start, max(0.0, start - next_step))
            self.watchdog.ping()
            if self.ticks.due() and self.players:
                print(self.ticks.report(self.outboxes, {ws: p.name for ws, p in self.players.items()}), flush=True)

    def step(self):
        g = self.game
        inputs = {}
        for p in self.players.values():
            if p.pid is None or p.pid not in g.players:
                continue
            inputs[p.pid] = p.inputs.pop_for_tick()
            p.ctrl_seq = p.inputs.applied
        for p in self.seats.players():
            if p.pid is not None:
                inputs[p.pid] = IDLE
        g.step(inputs)
        for q in g.players.values():  # (as the windows do: the same numbers next tick at both ends)
            q.state.update(SCHEMA.quantise(q.state))
            sel = q.inv[q.selected]
            q.state["held"] = sel[0] if sel else 0
            q.state["flags"] = (q.state["flags"] | sim.F_SWING) if q.swing > 0 else (q.state["flags"] & ~sim.F_SWING)

    def things(self):
        g = self.game
        out = [dict(q.state, id=pid) for pid, q in g.players.items()]
        out += [dict(b.state, id=bid) for bid, b in g.bots.items()]
        out += [dict(m["s"], id=mid) for mid, m in g.mobs.mobs.items()]
        out += [{"id": eid, "kind": 6, "x": it["x"], "y": it["y"], "z": it["z"], "held": it["item"]}
                for eid, it in g.items.items()]
        return out

    async def send_loop(self):
        sent_version, last_state, next_send, ticks = {}, 0.0, time.perf_counter(), 0
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
                for ws, p in list(self.players.items()):  # (each Bot's owner: what it is doing, for the HUD)
                    bot = self.game.bot_of(p.pid) if p.pid is not None else None
                    if bot is not None:
                        await self.send(ws, {"type": "bot_status", "doing": bot.action[0] if bot.action else "waiting",
                                             "stats": bot.stats, "running": bool(bot.brain and not bot.brain.error)},
                                        "bot_status")
                if getattr(self, "blueprints_dirty", False):
                    self.blueprints_dirty = False
                    for ws in list(self.players):
                        await self.send(ws, self.blueprints_msg())
            self.snap_seq = (self.snap_seq + 1) & 0xFFFF
            sm = server_ms()
            things = self.things()
            state = None
            if now - last_state > STATE_RATE:
                last_state = now
                state = json.dumps(self.state_msg(), separators=(",", ":"))
            roster = None
            for ws, p in list(self.players.items()):
                if backed_up(ws):
                    continue
                if sent_version.get(ws) != self.roster_version:
                    roster = roster or json.dumps(self.roster(), separators=(",", ":"))
                    await self.send(ws, roster, "roster")
                    sent_version[ws] = self.roster_version
                if state:
                    await self.send(ws, state, "state")
                me = self.game.players.get(p.pid) if p.pid is not None else None
                if me is not None:
                    x, y = me.state["x"], me.state["y"]
                    near = [e for e in things if e["id"] == p.pid or (e["x"] - x) ** 2 + (e["y"] - y) ** 2 < SEE * SEE]
                else:
                    near = things
                frame = wire.pack_snapshot(SCHEMA, sm, self.snap_seq, near[:255], ack=p.inputs.ack(),
                                           flags=min(15, p.inputs.depth()) << 4)
                await self.send(ws, frame, "snap")
            await asyncio.sleep(0)

    def save_world(self):
        try:
            self.game.world.save(WORLD_DIR, self.game.save_extra())
        except OSError as e:
            print("The world couldn't be saved:", e, flush=True)

    def before_exit(self):
        for p in list(self.players.values()):
            self.keep_player(p)
        self.save_world()
        self.teaching.save()

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
                        self.seats.take(craft_profiles.slug(p.name))
                        self.rebuild()
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in self.group:
                        self.players.pop(ws, None)
                        self.keep_player(p)
                        await self.outboxes.close(ws, 4009, "Your teacher took you out of this game: back to the lobby.")
                        self.rebuild()
            if key != seen:
                seen, presence = key, {}
                allowed = set(mine.get("learners", [])) if mine else set()
                self.group = sorted(allowed)
                self.seats.clear()
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in allowed:
                        self.players.pop(ws, None)
                        self.keep_player(p)
                        await self.outboxes.close(ws, 4009, "The session has ended." if not mine else "You aren't in this group.")
                if mine:
                    self.teaching.apply_lesson(int(mine.get("lesson", 1)))
                    self.rebuild()
                    self.log.events.append((self.log.time, f"Session started: {mine.get('group', '')}, lesson {mine.get('lesson', 1)}"))
                else:
                    self.rebuild()
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
        while pointer:
            try:
                with open(pointer, encoding="utf-8") as f:
                    wanted = f.read().strip() or None
            except OSError:
                wanted = None
            ready = wanted if wanted and wanted != craft_version.CODE else None
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


def backed_up(ws, limit=64 * 1024):
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
    ap.add_argument("--port", type=int, default=8785)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--class-server", action="store_true", help="the real class server: real codes required")
    ap.add_argument("--lesson", help="start from saved lesson settings (JSON)")
    ap.add_argument("--seed", type=int, default=None, help="a new world from this seed (the saved one kept as world_old)")
    ap.add_argument("--size", default=None, choices=list(craft_world.SIZES))
    ap.add_argument("--sandbox", "--creative", dest="sandbox", action="store_true",
                    help="the learners in Sandbox mode (--creative: its old name)")
    ap.add_argument("--mobs", action="store_true", help="creatures at night")
    args = ap.parse_args()
    CLASS_SERVER = args.class_server
    local_only = args.bind in ("127.0.0.1", "localhost", "::1")
    if CLASS_SERVER or not local_only:
        problem = check_class_server_codes()
        if problem:
            raise SystemExit("Craft Lab server not started: " + problem)
    OPEN_SIGNUP = os.environ.get("CRAFTLAB_OPEN_SIGNUP") == "1" or not CLASS_SERVER
    if args.seed is not None or args.size:
        craft_mods_world = {"seed": args.seed if args.seed is not None else 2026}
        if args.size:
            craft_mods_world["size"] = args.size
        server = CraftServer(args.lesson, fresh=True)
        server.world_mod.update(craft_mods_world)
        world = craft_world.World(server.world_mod["size"], server.world_mod["seed"])
        server.game = craft_game.Game(world, server.game_rules())
        server.rebuild()
    else:
        server = CraftServer(args.lesson)
    if args.sandbox:
        server.lesson["game_mode"] = "sandbox"
    if args.mobs:
        server.lesson["hazards"]["mobs"] = True
    server.rebuild()
    if CLASS_SERVER:
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(craft_version.CODE)
    tasks = [server.physics_loop(), server.send_loop(), server.watch_live(), server.watch_desk()]
    async with websockets.serve(server.handler, args.bind, args.port, compression=None, ping_interval=5,
                                ping_timeout=10, max_queue=8, max_size=2 ** 20):
        tick_stats.start_up()
        print(f"Craft Lab {'class' if CLASS_SERVER else 'laptop test'} server {craft_version.VERSION} on "
              f"{args.bind}:{args.port}, world seed {server.game.world.seed}."
              + ("" if CLASS_SERVER else f" Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}. A new username "
                                         f"makes a profile."), flush=True)
        await lifecycle.run(tasks, server.outboxes, server.players, server.before_exit)


if __name__ == "__main__":
    asyncio.run(main())
