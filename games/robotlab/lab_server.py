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
import hmac
import ipaddress
import json
import os
import re
import time

import websockets

import cpu_brains
import lab_brain
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
BRAIN_UPLOAD_GAP = 3.0                   # seconds between one learner's brain uploads
MAX_LEARNERS = 4
SEND_RATE = 1 / 20
HERE = os.path.dirname(os.path.abspath(__file__))
COLOURS = [(220, 60, 50), (60, 130, 230), (60, 190, 90), (240, 190, 40), (180, 90, 230)]

# What learners can see and change. The teacher edits this live from the teacher screen.
WEEK1_LESSON = {
    "lesson_number": 1,            # which of the 5 lessons: sets missions, tools and hazards
    "mode": "practice",            # practice = no damage, robots come back; battle = real fight
    "time_limit": 120,             # seconds per battle
    "cpu_robots": 1,               # computer-driven sparring robots
    "cpu_level": "medium",         # how well they drive: empty (the teacher's demo brain), easy, medium, expert
    "teacher_robot": True,
    "designs_locked": False,       # stop design changes (e.g. during a battle)
    "real_damage": False,          # each part (wheels, weapon, armour, body) has hit points and comes off at zero
    "hazards": {"pit": True, "floor_flipper": False, "saws": False, "spikes": False, "house_robots": []},
    "sound": dict(rw_sound.DEFAULT_SOUND),  # what everyone hears: music, crowd, arena hum and hit sounds
    "tools": {                     # the learner's garage: what is shown and changeable
        "points_table": True,
        "forward_speed": True, "reverse_speed": True, "turn_speed": True, "acceleration": True, "size": True,
        "choose_weapon": False, "weapons": ["wedge", "spinner", "drum", "hammer"],
        "name_and_colour": True, "code_view": True, "stats_readout": True, "weapon_toggle": True,
        "house_robots": False,     # learners may drive a house robot
    },
}


HAZARD_WORDS = {"pit": "Drop zone", "floor_flipper": "Floor flipper", "saws": "Floor saws", "spikes": "Wall spikes"}


class Player:
    def __init__(self, ws, role, name, colour):
        self.ws, self.role, self.name = ws, role, name
        self.design = sim.default_design(name if role == "learner" else "Teacher Bot", colour,
                                         "wedge" if role == "learner" else "spinner")
        self.robot = None
        self.start_colour = list(colour)
        self.profile = None


class LabServer:
    def __init__(self, lesson_file=None):
        self.lesson = copy.deepcopy(WEEK1_LESSON)
        if lesson_file and os.path.exists(lesson_file):
            with open(lesson_file) as f:
                self.lesson.update(json.load(f))
        self.players = {}        # websocket -> Player
        self.teacher_design = sim.default_design("Teacher Bot", (180, 90, 230), "spinner")
        self.paused, self.fight_started = False, 0.0
        self.roster_version = 0
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
    def rebuild_arena(self):
        """New arena (hazards may have changed), then put everyone's robot back in."""
        self.arena = sim.Arena(hazards=self.lesson["hazards"])
        self.arena.practice = self.lesson["mode"] == "practice"
        self.arena.real_damage = bool(self.lesson.get("real_damage"))
        start = 0
        for p in self.learners():
            p.robot = self.arena.add_robot(p.design, brain=None, owner=p.name, start=start)
            self.teaching.attach(p)  # their uploaded brain drives it if autopilot is on
            start += 1
        t = self.teacher()
        if self.lesson["teacher_robot"]:
            owner = t.name if t else "Teacher (away)"
            r = self.arena.add_robot(t.design if t else self.teacher_design, brain=None if t else sim.chase_brain,
                                     owner=owner, start=start)
            if t:
                t.robot = r
            start += 1
        elif t:
            t.robot = None
        for i in range(self.lesson["cpu_robots"]):
            if start < len(sim.Arena.STARTS):
                cpu = sim.default_design(f"Sparky {i + 1}", (150, 150, 160), ["wedge", "spinner", "drum", "hammer"][i % 4])
                self.arena.add_robot(cpu, brain=self.cpu_brain(), owner="Computer", start=start)
                start += 1
        self.fight_started = self.arena.time
        self.roster_version += 1
        self.arena.events.append((self.arena.time, "Practice: no damage" if self.arena.practice else "FIGHT!"))

    def cpu_brain(self):
        return cpu_brains.for_level(self.lesson.get("cpu_level", "medium"), self.demo_brain)

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
            for r in self.arena.robots:
                if r.owner == "Computer":
                    r.brain = self.cpu_brain()

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

    def clean_design(self, player, d):
        """Keep only what this lesson lets learners change; everything else stays as it was."""
        tools, old = self.lesson["tools"], player.design
        new = copy.deepcopy(old)
        if player.role == "teacher":
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
        if tools.get("house_robots"):  # drive a house robot instead of your own design
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
            await ws.close(4006, f"Out of date: get Robot Lab {lab_version.VERSION} from {lab_version.DOWNLOAD_PAGE}")
            return
        role = code_role(str(hello.get("code", "")))
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
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(hello.get("name", "")))[:12] or "Teacher"
        colour = COLOURS[len(self.learners()) % len(COLOURS)] if role == "learner" else (180, 90, 230)
        p = Player(ws, role, name, colour)
        p.profile = profile
        if role == "teacher":
            p.design = self.teacher_design
        else:
            saved = self.teaching.load_saved_design(name)
            if saved:  # their robot from last time
                p.design = saved
            self.teaching.login(p)  # their missions, reflections, brain and settings from last time
        self.players[ws] = p
        print(f"+ {name} ({role})")
        self.rebuild_arena()
        self.arena.events.append((self.arena.time, f"{name} joined"))
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "lesson": self.lesson,
                             "design": p.design, "rules": self.rules(),
                             "prefs": (profile or {}).get("prefs", {}), "new_profile": bool(profile and is_new),
                             "code": lab_version.CODE,
                             "live_ready": getattr(self, "live_ready", None) if role == "teacher" else None})  # (see lab_version)
        await self.broadcast_lesson()
        await self.deliver(self.teaching.teacher_update() + self.teaching.learner_updates())
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
        if kind == "control" and p.robot is not None:
            p.robot.control = (max(-1.0, min(1.0, float(m["throttle"]))), max(-1.0, min(1.0, float(m["steer"]))),
                               bool(m["fire"]))
        elif kind == "weapon" and p.robot is not None and (p.role == "teacher" or self.lesson["tools"]["weapon_toggle"]):
            p.robot.weapon_on = not p.robot.weapon_on
        elif kind == "ping":
            await self.send(p.ws, {"type": "pong", "t": m.get("t")})
        elif kind == "design":
            if self.lesson["designs_locked"] and p.role == "learner":
                await self.send(p.ws, {"type": "design_result", "ok": False, "problems": ["The teacher has locked designs for now."],
                                       "design": p.design})
                return
            new = self.clean_design(p, m.get("design", {}))
            problems = sim.check_design(new)
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
            name = lab_profiles.clean_name(m.get("learner", ""))
            for ws, q in list(self.players.items()):
                if q.role == "learner" and lab_profiles.slug(q.name) == lab_profiles.slug(name):
                    del self.players[ws]
                    await ws.close(4007, "Your account has been deleted by the teacher.")
            text = self.teaching.delete_learner(name)
            self.rebuild_arena()
            t = self.teacher()
            if t:
                await self.deliver([(t.ws, {"type": "notice", "text": text})] + self.teaching.teacher_update())
            await self.broadcast_lesson()
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
        if kind == "pit":  # open or close the drop zone, straight away (no restart)
            self.lesson["hazards"]["pit"] = bool(m.get("open"))
            self.arena.set_pit(self.lesson["hazards"]["pit"])
            self.arena.events.append((self.arena.time, "The drop zone is OPEN" if self.lesson["hazards"]["pit"]
                                      else "The drop zone is closed"))
            await self.broadcast_lesson()
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
            problems = sim.check_design(new)
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
                for r in self.arena.robots:
                    if r.owner == "Computer":
                        r.brain = self.cpu_brain()
                self.arena.events.append((self.arena.time, f"Computer robots: {cpu_brains.LEVELS[update['cpu_level']]}"))
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
            if isinstance(update.get("sound"), dict):
                self.lesson["sound"] = rw_sound.sound_settings(self.lesson.get("sound"), update["sound"])
            if rebuild:
                self.rebuild_arena()
            elif arena_changed:  # hazards start or stop mid-round: robots carry on where they are
                houses_before = [r.name for r in self.arena.robots if r.house]
                self.arena.set_hazards(self.lesson["hazards"])
                if houses_before != [r.name for r in self.arena.robots if r.house]:
                    self.roster_version += 1  # (only robots joining or leaving need the windows to redraw them)
                changes = [f"{HAZARD_WORDS[k]} {'on' if v else 'off'}" for k, v in update.get("hazards", {}).items()
                           if k in HAZARD_WORDS]
                self.arena.events.append((self.arena.time, ", ".join(changes) or "The house robots have changed"))
            await self.broadcast_lesson()
        elif kind == "restart":
            self.rebuild_arena()
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

    async def broadcast_lesson(self):
        msg = {"type": "lesson", "lesson": self.lesson,
               "class": [{"name": p.name, "role": p.role, "design": p.design} for p in self.players.values()]}
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
                "ko": r.knocked_out, "on": r.weapon_on, "rpm": round(r.weapon_rpm), "energy": round(r.weapon_energy()),
                "dealt": round(r.damage_dealt), "hits": r.hits, "fc": r.fires,
                "act": 1 if a.time < r.fire_until and r.weapon_on else 0,
                # each part's health in % (body, armour, weapon, four wheels): the windows draw the hit bars from it
                "pt": [round(100 * max(0.0, r.health) / r.stats["armour"])] +
                      [round(100 * r.condition(k)) for k in sim.PARTS]})
        time_left = self.time_left()
        winner = self.winner()
        impacts, streams = a.take_fx()
        return {"type": "state", "t": round(a.time, 2), "robots": robots, "hz": a.hazard_state(),
                "fx": {"impacts": [[[round(v, 2) for v in pos], round(dmg, 1), kind] for pos, dmg, kind in impacts[-20:]],
                       "streams": [[[round(v, 2) for v in pos], [round(v, 2) for v in d], n] for pos, d, n in streams[-30:]]},
                "events": [e for t, e in a.events if a.time - t < 4][-4:],
                "paused": self.paused, "practice": a.practice, "time_left": time_left, "winner": winner,
                "rd": 1 if a.real_damage else 0}

    def time_left(self):
        a = self.arena
        return None if a.practice else max(0, self.lesson["time_limit"] - (a.time - self.fight_started))

    def winner(self):
        a = self.arena
        fighters = [r for r in a.robots if not r.house]  # house robots don't win or lose
        if a.practice or len(fighters) < 2:
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
                "hazards": self.lesson["hazards"], "look": self.look,
                "mine": {p.name: (p.robot.id if p.robot else None) for p in self.players.values()}}

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
        await asyncio.gather(server.physics_loop(), server.send_loop(), server.watch_live())


if __name__ == "__main__":
    asyncio.run(main())
