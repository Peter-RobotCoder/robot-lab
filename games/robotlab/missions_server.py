"""The Missions class server (CHANGE 195): the fifth game a class is launched into from the Club Coders app's
Teacher screen. The story missions (wake_up_call.py: Mission 1 "Wake-Up Call", Mission 2 "Lights Out") are played by
each learner in their own window; this server is the class around them.

    python missions_server.py                       a laptop test server (codes CLUB42 and TEACH99)
    python missions_server.py --class-server        the real one (JOIN_CODE and TEACHER_CODE set, behind Caddy)

It lets the launched group's learners in (the club desk's tickets, as every game's server), tells each window
which mission the lesson is (lesson 1 is Mission 1, lesson 2 Mission 2: mission_lessons.LESSON_MISSIONS), keeps
each learner's progress (the Solar Panel, the best stars) so it follows them to any laptop, marks the lesson's
objectives from what their windows report (a run finished, the stars, a failed run then a good one:
mission_lessons.MISSIONS), writes the session's report for the desk (who is here, what each learner completed)
and sends the teacher's window the class's progress every couple of seconds.

(CHANGE 198) The server runs the missions. A window (or the page) sends its program's text; the server reads it
with the same pseudo code (mission_pseudo.py, the mission's dictionary.json), runs it on that learner's mission
(mission_wake_up.py, mission_lights_out.py: the same Python the window runs alone) and sends back the events, which
the window animates as it animates its own. So the server knows where every robot is, and every window draws the
whole class in the one valley: the others' robots, dimmed, with their names, each on its own run (they never
bump: a learner's program never fails because of someone else's robot). Each learner's mission is kept by name, so
a window reopened, or a dropped connection, carries on where it was. A window played alone (no server) still runs
the mission itself.
    window -> server   start {mission, robot}    the mission from its start (also RESET)
                       program {mission, text}   run the program from where the robot is
                       parse {mission, text}     the hints and the Python beside each line (for the page)
    server -> window   state {mission, robot, state}     the learner's mission now (after start, or on coming back)
                       ran {status, before, events, state, stars, objectives, code_lines}
                                                 an event's state as only what changed ("d") since the one before
                       world {robots: [...]}     every robot in the class, on joining
                       robot {name, mission, robot, steps | gone}   someone's robot started, ran or left
(CHANGE 199) The welcome also carries "missions": each mission's map, objectives, rules, robots and tools, its
start, Mission 2's nights, lamps and mast, and the phrasebook (about), so the browser page (club-coders/web,
missions.js) draws and words them from the same Python the window plays, with no copy of its own.
"""
import argparse
import asyncio
import hmac
import ipaddress
import json
import os
import re
import sys
import time

import websockets

import lab_version
sys.path.insert(0, lab_version.ENGINE_HOME)
from engine import club_ticket, lifecycle  # noqa: E402

import lab_missions  # noqa: E402
import mission_lessons as ml  # noqa: E402
import mission_lights_out  # noqa: E402
import mission_pseudo as P  # noqa: E402
import mission_wake_up  # noqa: E402

DEMO_CODES = {"learner": "CLUB42", "teacher": "TEACH99"}
LEARNER_CODE = os.environ.get("JOIN_CODE", DEMO_CODES["learner"])
TEACHER_CODE = os.environ.get("TEACHER_CODE", DEMO_CODES["teacher"])
GAME_ID = "missions"
TICKET_KEY = os.environ.get("CLUBCODERS_TICKET_KEY")
LIVE_FILE = os.environ.get("CLUBCODERS_LIVE_FILE", "")
DESK_INBOX = os.environ.get("CLUBCODERS_DESK_INBOX")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("MISSIONS_DATA") or os.path.join(HERE, "data", "missions")
PROFILES = os.path.join(DATA, "profiles")
CLASS_SERVER = False
MAX_LEARNERS = 30
CLASS_EVERY = 2.0  # seconds between the teacher's class updates and the desk's report


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "x"


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class RateLimit:
    """Wrong tries per computer: more than `most` a minute are turned away for a minute."""

    def __init__(self, most=10):
        self.most, self.tries = most, {}

    def failed(self, where):
        self.tries.setdefault(where, []).append(time.time())

    def blocked(self, where):
        t = [x for x in self.tries.get(where, []) if time.time() - x < 60]
        self.tries[where] = t
        return len(t) >= self.most


BAD_LOGINS = RateLimit()

# ---------- the missions, run here (CHANGE 198) ----------
RULES = {"wake_up_call": mission_wake_up, "lights_out": mission_lights_out}
ROBOTS = ("TITAN", "RAZORBACK")
MAX_TEXT = 6000         # characters in a program
RUN_GAP = float(os.environ.get("MISSIONS_RUN_GAP", 0.25))  # seconds between one learner's runs at least
STEP_TYPES = {"move", "turn", "bump", "use", "night", "complete", "flat", "repair", "objective", "report", "stop"}
_DICTIONARIES = {}


def dictionary(mid):
    """The mission's pseudo code, as its window loads it (missions/<mission>/dictionary.json)."""
    if mid not in _DICTIONARIES:
        _DICTIONARIES[mid] = P.load(os.path.join(HERE, "missions", mid, "dictionary.json"))
    return _DICTIONARIES[mid]


_ABOUT = {}


def about(mid):
    """(CHANGE 199) What the page needs to draw a mission and write its HUD and phrasebook, from the mission's own
    module and dictionary: the map, objectives, rules, robots and tools, the state it starts in, the story's number
    and title, the part it unlocks or uses, Mission 2's nights, lamps and mast, and the phrasebook's words."""
    if mid not in _ABOUT:
        G, d, story = RULES[mid], dictionary(mid).dict, lab_missions.STORY_MISSIONS[mid]
        info = {"map": G.MAP, "objectives": G.OBJECTIVES, "rules": G.RULES, "robots": G.ROBOTS, "tools": G.TOOLS,
                "dir_names": G.DIR_NAMES, "start": G.new_mission(ROBOTS[0]).snapshot(), "number": story["number"],
                "title": story["title"], "unlock": G.UNLOCK, "solar": getattr(G, "SOLAR", None),
                "phrasebook": {"patterns": [{k: p.get(k) for k in ("say", "meaning", "example", "alias")}
                                            for p in d["patterns"]],
                               "slots": {k: s.get("describe", "") for k, s in d["slots"].items()},
                               "synonyms": d.get("synonyms", {}), "fillers": d.get("fillers", [])}}
        if mid == "lights_out":
            info.update(nights=G.NIGHTS, lamps=G.LAMPS, road_y=G.ROAD_Y, mast=G.MAST)
        _ABOUT[mid] = info
    return _ABOUT[mid]


def changed(before, after):
    """What of a state changed: the event's "d" (the window rebuilds each event's whole state from these)."""
    return {k: v for k, v in after.items() if before.get(k) != v}


def unpack(before, events):
    """A ran message's events with their whole states again (as the window and the tests read them)."""
    cur, out = dict(before), []
    for e in events:
        cur = dict(cur, **e.get("d", {}))
        out.append(dict({k: v for k, v in e.items() if k != "d"}, state=cur))
    return out


class Play:
    """One learner's mission on the server: the mission's own Python (the window's, when it plays alone)."""

    def __init__(self, mid, robot, solar=False):
        self.mid, self.robot = mid, robot
        G = RULES[mid]
        self.m = G.new_mission(robot, solar=solar) if mid == "lights_out" else G.new_mission(robot)
        self.last_run = 0.0

    def run(self, text):
        """The program read and run from where the robot is: the ran message (status "error" when a line isn't
        understood: nothing runs, as the window's RUN stays off)."""
        parsed = P.parse_program(text, dictionary(self.mid))
        if parsed["program"] is None or not parsed["program"]:
            return {"type": "ran", "mission": self.mid, "status": "error", "events": [],
                    "errors": [{"n": r["n"], "message": r.get("message")} for r in parsed["errors"]][:20]}
        before = self.m.snapshot()
        result = self.m.run(parsed["program"], parsed["code_lines"])
        prev, events = before, []
        for e in result["events"]:
            events.append(dict({k: v for k, v in e.items() if k != "state"}, d=changed(prev, e["state"])))
            prev = e["state"]
        return {"type": "ran", "mission": self.mid, "robot": self.robot, "status": result["status"], "before": before,
                "events": events, "state": self.m.snapshot(), "stars": self.m.stars(),
                "objectives": self.m.objectives(), "code_lines": parsed["code_lines"]}

    def where(self):
        s = self.m.s
        return [s["x"], s["y"], s["dir"], s.get("tool")]

    def steps(self, ran):
        """What the others' windows animate of a run: each move, turn, bump, tool use... as [type, x, y, dir, tool]."""
        out = []
        for e in unpack(ran["before"], ran["events"]):
            s = e["state"]
            if e["type"] in STEP_TYPES:
                out.append([e["type"], s["x"], s["y"], s["dir"], s.get("tool")])
        return out[-400:]


def parse_rows(text, mid):
    """The program's lines read as the window's code panel reads them: what each says, the hints, the Python."""
    r = P.parse_program(text, dictionary(mid))
    return {"type": "parsed", "mission": mid, "ok": r["program"] is not None, "code_lines": r["code_lines"],
            "python": r["python"],
            "rows": [{"n": w["n"], "kind": w["kind"], "canonical": w.get("canonical"), "message": w.get("message"),
                      "hint": w.get("hint"), "after": w.get("after"), "indent": w["indent"],
                      "python_line": w["python_line"]} for w in r["rows"]]}


class Player:
    def __init__(self, ws, role, name):
        self.ws, self.role, self.name = ws, role, name
        self.mission = None     # the mission the window is on
        self.last = None        # the last run the window reported: {status, objectives, complete, stars, ...}
        self.runs = 0
        self.joined = now_text()


class MissionsServer:
    def __init__(self):
        self.players = {}
        self.lesson = 1
        self.group = []
        self.live_id = None
        self.started = ""
        self.records = {}       # learner -> {"done": {mission id: {"time", "detail"}}, "failed": {mid: True}}
        self.progress = {}      # learner -> the window's progress file ({"parts", "missions"})
        self.presence = {}
        self.plays = {}         # (role, slug of the name) -> Play: each person's mission, kept while they're away
        self.watchdog = lifecycle.Watchdog()
        os.makedirs(PROFILES, exist_ok=True)
        for f in os.listdir(PROFILES):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(PROFILES, f), encoding="utf-8") as fh:
                        saved = json.load(fh)
                    self.records[saved["name"]] = saved.get("record") or {"done": {}, "failed": {}}
                    self.progress[saved["name"]] = saved.get("progress") or {"parts": [], "missions": {}}
                except (OSError, ValueError, KeyError, TypeError):
                    pass

    # ---------- the lesson ----------
    @property
    def mission_id(self):
        return ml.LESSON_MISSIONS.get(self.lesson, "wake_up_call")

    def lesson_msg(self):
        return {"type": "lesson", "lesson": {"lesson_number": self.lesson, "mission": self.mission_id,
                                            "title": ml.LESSONS.get(self.lesson, ml.LESSONS[1])["title"]}}

    # ---------- who is here ----------
    def learners(self):
        return [p for p in self.players.values() if p.role == "learner"]

    def teacher(self):
        return next((p for p in self.players.values() if p.role == "teacher"), None)

    def record(self, name):
        return self.records.setdefault(name, {"done": {}, "failed": {}})

    def save_profile(self, name):
        try:
            os.makedirs(PROFILES, exist_ok=True)
            path = os.path.join(PROFILES, slug(name) + ".json")
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"name": name, "record": self.record(name),
                           "progress": self.progress.get(name) or {"parts": [], "missions": {}}}, f, indent=1)
            os.replace(path + ".tmp", path)
        except OSError:
            pass

    def delete_learner(self, name):
        gone = slug(name)
        for store in (self.records, self.progress, self.presence):
            for k in [k for k in store if slug(k) == gone]:
                del store[k]
        self.plays.pop(("learner", gone), None)
        try:
            os.remove(os.path.join(PROFILES, gone + ".json"))
        except OSError:
            pass

    # ---------- what a window reports ----------
    def complete(self, name, mid, detail):
        r = self.record(name)
        if mid not in r["done"]:
            r["done"][mid] = {"time": now_text(), "detail": detail[:200]}
            return True
        return False

    def on_run(self, p, m):
        """A run's result from a learner's window: the mission's objectives marked (finished, the stars, a failed
        run put right)."""
        mid = m.get("mission") if m.get("mission") in ml.MISSION_LESSONS else self.mission_id
        lesson = ml.MISSION_LESSONS[mid]
        status = str(m.get("status", ""))[:20]
        stars = m.get("stars") if isinstance(m.get("stars"), dict) else {}
        objectives = m.get("objectives") if isinstance(m.get("objectives"), list) else []
        done_n = sum(1 for o in objectives if o)
        p.mission, p.runs = mid, p.runs + 1
        p.last = {"mission": mid, "status": status, "objectives": done_n, "of": len(objectives),
                  "complete": bool(m.get("complete")), "stars": int(stars.get("count", 0) or 0),
                  "energy": m.get("energy_left"), "lines": m.get("lines_used"), "robot": str(m.get("robot", ""))[:12]}
        r = self.record(p.name)
        if p.role != "learner":
            return
        if status in ("flat", "stopped", "failed") and not m.get("complete"):
            r["failed"][mid] = True
        if m.get("complete"):
            words = f"{p.last['robot']} finished with {p.last['stars']} star{'s' if p.last['stars'] != 1 else ''}, " \
                    f"{p.last['energy']} energy left, {p.last['lines']} lines"
            self.complete(p.name, f"{lesson}a", words)
            if stars.get("energy"):
                self.complete(p.name, f"{lesson}b", f"{p.last['energy']} energy left")
            if stars.get("lines"):
                self.complete(p.name, f"{lesson}c", f"{p.last['lines']} lines")
            if r["failed"].get(mid):
                self.complete(p.name, f"{lesson}d", "A run that failed, then one that finished")
        self.save_profile(p.name)

    def class_msg(self):
        """The class's progress, for the teacher's window (and the desk's report): each learner's mission, run
        count, last result and the objectives done this lesson."""
        out = []
        for p in sorted(self.learners(), key=lambda q: q.name.lower()):
            done = [mid for mid in self.record(p.name)["done"] if mid in ml.missions_for(self.lesson)]
            out.append({"name": p.name, "mission": p.mission or self.mission_id, "runs": p.runs, "last": p.last,
                        "done": sorted(done), "stars": max([0] + [int(v.get("bestStars") or 0) for v in
                                                                  (self.progress.get(p.name) or {}).get("missions", {}).values()])})
        return {"type": "class", "learners": out, "lesson": self.lesson}

    def session_report(self):
        since = self.started
        done = {}
        for name, r in self.records.items():
            new = {mid: {"time": info.get("time", ""), "detail": info.get("detail", ""), "title": ml.MISSIONS[mid][1],
                         "outcomes": list(ml.MISSIONS[mid][3]), "check": ml.MISSIONS[mid][4]}
                   for mid, info in r["done"].items() if mid in ml.MISSIONS and str(info.get("time", "")) >= since}
            if new:
                done[name] = new
        totals = {name: {c: sum(1 for mid in r["done"] if mid in ml.MISSIONS and c in ml.MISSIONS[mid][3])
                         for c in ml.OUTCOMES} for name, r in self.records.items()}
        return {"since": since, "present": self.presence, "done": done, "cards": [], "lesson": self.lesson,
                "totals": totals}

    # ---------- connections ----------
    async def send(self, ws, msg):
        try:
            await ws.send(json.dumps(msg, separators=(",", ":")))
        except websockets.ConnectionClosed:
            pass

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
            page = lab_version.DOWNLOAD_PAGE or "your teacher"
            await ws.close(4006, f"Out of date: download Club Coders {lab_version.VERSION} from {page}"[:120])
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
            name = ticket["name"]
        else:
            role = code_role(str(hello.get("code", "")))
            if role == "learner" and TICKET_KEY:
                await ws.close(4010, "Log in through the Club Coders app: your teacher launches your group there.")
                return
            if role is None:
                BAD_LOGINS.failed(where)
                await ws.close(4001, "wrong class code")
                return
            name = re.sub(r"[^A-Za-z0-9 ]", "", str(hello.get("name", "")))[:12] or ("Teacher" if role == "teacher" else "")
            if not name:
                await ws.close(4004, "Type a username.")
                return
        if role == "teacher" and self.teacher():
            await ws.close(4002, "a teacher is already connected")
            return
        old = next((q for q in self.players.values() if q.role == role and slug(q.name) == slug(name)), None)
        if old is not None:  # (the same person again: a window reopened at another tier, or opened twice)
            self.players.pop(old.ws, None)
            try:
                await old.ws.close(4005, "you logged in again somewhere else")
            except Exception:
                pass
        if role == "learner" and len(self.learners()) >= MAX_LEARNERS:
            await ws.close(4003, f"the class is full ({MAX_LEARNERS} learners)")
            return
        p = Player(ws, role, name)
        self.players[ws] = p
        print(f"+ {name} ({role})", flush=True)
        if role == "learner":
            self.presence.setdefault(name, {"first": now_text()})["last"] = now_text()
        await self.send(ws, {"type": "welcome", "role": role, "name": name, "lesson": self.lesson_msg()["lesson"],
                             "progress": self.progress.get(name) or {"parts": [], "missions": {}},
                             "code": lab_version.CODE, "runs_here": True,
                             "missions": {mid: about(mid) for mid in RULES}})
        if role == "teacher":
            await self.send(ws, self.class_msg())
        await self.send(ws, self.world_msg(p))
        play = self.plays.get((role, slug(name)))
        if play is not None:  # (back: a reopened window, a dropped connection: the mission carries on where it was)
            await self.send(ws, {"type": "state", "mission": play.mid, "robot": play.robot, "state": play.m.snapshot(),
                                 "back": True})
            await self.tell_others(p, {"type": "robot", "name": name, "mission": play.mid, "robot": play.robot,
                                       "steps": [["place"] + play.where()]})
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
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
            if self.players.get(ws) is p:
                del self.players[ws]
                print(f"- {name} left", flush=True)
                if role == "learner":
                    self.save_profile(name)
                await self.tell_others(p, {"type": "robot", "name": name, "gone": True})

    async def on_message(self, p, m):
        kind = m.get("type")
        if kind == "ping":
            await self.send(p.ws, {"type": "pong", "t": m.get("t")})
        elif kind == "run":
            self.on_run(p, m)
            t = self.teacher()
            if t is not None:
                await self.send(t.ws, self.class_msg())
        elif kind == "progress" and p.role == "learner":
            prog = m.get("progress")
            if isinstance(prog, dict) and isinstance(prog.get("parts"), list) and isinstance(prog.get("missions"), dict):
                self.progress[p.name] = {"parts": [str(x)[:40] for x in prog["parts"][:20]],
                                         "missions": {str(k)[:40]: v for k, v in list(prog["missions"].items())[:20]
                                                      if isinstance(v, dict)}}
                self.save_profile(p.name)
        elif kind == "mission" and p.role == "learner":  # (which mission the window is on now)
            if m.get("mission") in ml.MISSION_LESSONS:
                p.mission = m["mission"]
        elif kind in ("start", "reset"):
            await self.start_play(p, m)
        elif kind == "program":
            await self.run_play(p, m)
        elif kind == "parse":
            if m.get("mission") in RULES:
                await self.send(p.ws, parse_rows(str(m.get("text", ""))[:MAX_TEXT], m["mission"]))
        elif p.role == "teacher":
            await self.teacher_command(p, m)

    # ---------- the missions, run here (CHANGE 198) ----------
    def world_msg(self, me):
        """Every other robot in the class, where it is now (for a window joining)."""
        here = {(q.role, slug(q.name)): q for q in self.players.values() if q is not me}
        robots = [{"name": here[k].name, "role": k[0], "mission": play.mid, "robot": play.robot, "at": play.where()}
                  for k, play in self.plays.items() if k in here]
        return {"type": "world", "robots": robots}

    async def tell_others(self, me, msg):
        for q in list(self.players.values()):
            if q is not me:
                await self.send(q.ws, msg)

    async def start_play(self, p, m):
        """The mission from its start (the robot chosen, or RESET). Mission 2's Solar Panel is fitted when this
        learner's progress here has it (Mission 1 finished)."""
        mid, robot = m.get("mission"), str(m.get("robot", "")).upper()
        if mid not in RULES or robot not in ROBOTS:
            await self.send(p.ws, {"type": "notice", "text": "That isn't a mission and robot this server knows."})
            return
        solar = mission_wake_up.UNLOCK["id"] in (self.progress.get(p.name) or {}).get("parts", [])
        play = self.plays[(p.role, slug(p.name))] = Play(mid, robot, solar)
        p.mission = mid
        await self.send(p.ws, {"type": "state", "mission": mid, "robot": robot, "state": play.m.snapshot(),
                               "stars": play.m.stars(), "objectives": play.m.objectives()})
        await self.tell_others(p, {"type": "robot", "name": p.name, "mission": mid, "robot": robot,
                                   "steps": [["place"] + play.where()]})

    async def run_play(self, p, m):
        """A program run on this person's mission: the events back to their window, the steps to everyone else's,
        the lesson's objectives marked from the result (the server's own, so nobody can claim a finish)."""
        play = self.plays.get((p.role, slug(p.name)))
        if play is None or m.get("mission") != play.mid:
            await self.send(p.ws, {"type": "ran", "mission": m.get("mission"), "status": "no mission", "events": []})
            return
        if time.time() - play.last_run < RUN_GAP:
            await self.send(p.ws, {"type": "ran", "mission": play.mid, "status": "too soon", "events": []})
            return
        play.last_run = time.time()
        ran = play.run(str(m.get("text", ""))[:MAX_TEXT])
        await self.send(p.ws, ran)
        if ran["status"] == "error":
            return
        s, st = play.m.s, ran["stars"]
        self.on_run(p, {"mission": play.mid, "status": ran["status"], "objectives": [o["done"] for o in ran["objectives"]],
                        "complete": bool(s.get("complete")), "stars": st, "energy_left": s.get("energy"),
                        "lines_used": s.get("linesUsed"), "robot": play.robot})
        if s.get("complete") and p.role == "learner":
            self.finished(p.name, play)
        await self.tell_others(p, {"type": "robot", "name": p.name, "mission": play.mid, "robot": play.robot,
                                   "steps": play.steps(ran)})
        t = self.teacher()
        if t is not None:
            await self.send(t.ws, self.class_msg())

    def finished(self, name, play):
        """A finish kept in the learner's progress here, by the mission's own record_finish (the Solar Panel, the
        best stars), so it follows them to any laptop."""
        path = os.path.join(PROFILES, slug(name) + ".finish.json")
        try:
            os.makedirs(PROFILES, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.progress.get(name) or {"parts": [], "missions": {}}, f)
            self.progress[name] = RULES[play.mid].record_finish(path, play.m, play.robot)
        except OSError:
            return
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        self.save_profile(name)

    async def teacher_command(self, p, m):
        kind = m.get("type")
        if kind == "lesson":
            n = (m.get("lesson") or {}).get("lesson_number") if isinstance(m.get("lesson"), dict) else m.get("lesson_number")
            if isinstance(n, int) and n in ml.LESSONS:
                self.lesson = n
                await self.broadcast(self.lesson_msg())
        elif kind == "delete_learner":
            self.delete_learner(str(m.get("learner", "")))
            await self.send(p.ws, {"type": "notice", "text": f"{m.get('learner', '')}'s mission progress was removed."})
        elif kind == "class":
            await self.send(p.ws, self.class_msg())

    async def broadcast(self, msg):
        for ws in list(self.players):
            await self.send(ws, msg)

    # ---------- the loops ----------
    async def class_loop(self):
        while True:
            await asyncio.sleep(CLASS_EVERY)
            self.watchdog.ping()
            t = self.teacher()
            if t is not None:
                await self.send(t.ws, self.class_msg())
            for p in self.learners():
                self.presence.setdefault(p.name, {"first": now_text()})["last"] = now_text()

    async def watch_desk(self):
        if not LIVE_FILE:
            return
        seen = None
        report_file = os.path.join(os.path.dirname(LIVE_FILE), "reports", f"{GAME_ID}.json")
        while True:
            live = read_live()
            mine = live if live and live.get("game") == GAME_ID else None
            key = mine["id"] if mine else None
            if key == seen and mine and sorted(mine.get("learners", [])) != self.group:
                self.group = sorted(mine.get("learners", []))
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in self.group:
                        self.players.pop(ws, None)
                        await ws.close(4009, "Your teacher took you out of this game: back to the lobby.")
            if key != seen:
                seen = key
                allowed = set(mine.get("learners", [])) if mine else set()
                self.group, self.presence = sorted(allowed), {}
                for ws, p in list(self.players.items()):
                    if p.role == "learner" and p.name not in allowed:
                        self.players.pop(ws, None)
                        await ws.close(4009, "The session has ended." if not mine else "You aren't in this group.")
                if mine:
                    n = int(mine.get("lesson", 1)) if str(mine.get("lesson", 1)).isdigit() else 1
                    self.lesson = n if n in ml.LESSONS else max(ml.LESSONS)
                    self.started = str(mine.get("started", ""))
                    self.live_id = mine["id"]
                    await self.broadcast(self.lesson_msg())
                    print(f"Session started: {mine.get('group', '')}, lesson {self.lesson} ({self.mission_id})", flush=True)
            if mine:
                for p in self.learners():
                    self.presence.setdefault(p.name, {"first": now_text()})["last"] = now_text()
                try:
                    os.makedirs(os.path.dirname(report_file), exist_ok=True)
                    report = {"live_id": mine["id"], "game": GAME_ID, **self.session_report()}
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
                            self.delete_learner(str(request["delete_learner"]))
                    finally:
                        try:
                            os.remove(path)
                        except OSError:
                            pass
            await asyncio.sleep(2)


def read_live():
    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            live = json.load(f)
        return live if isinstance(live, dict) and live.get("id") else None
    except (OSError, ValueError, TypeError):
        return None


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


async def main():
    global CLASS_SERVER
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8784)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--class-server", action="store_true", help="the real class server: real codes required")
    ap.add_argument("--lesson", type=int, default=None, choices=sorted(ml.LESSONS), help="start on this mission")
    args = ap.parse_args()
    CLASS_SERVER = args.class_server
    local_only = args.bind in ("127.0.0.1", "localhost", "::1")
    if CLASS_SERVER or not local_only:
        problem = check_class_server_codes()
        if problem:
            raise SystemExit("Missions server not started: " + problem)
    server = MissionsServer()
    if args.lesson:
        server.lesson = args.lesson
    if CLASS_SERVER:
        os.makedirs(DATA, exist_ok=True)
        with open(os.path.join(DATA, "running_code"), "w", encoding="utf-8") as f:
            f.write(lab_version.CODE)
    async with websockets.serve(server.handler, args.bind, args.port, ping_interval=5, ping_timeout=10, max_queue=8):
        print(f"Missions {'class' if CLASS_SERVER else 'laptop test'} server {lab_version.VERSION} on "
              f"{args.bind}:{args.port}, lesson {server.lesson} ({server.mission_id})."
              + ("" if CLASS_SERVER else f" Codes: learners {LEARNER_CODE}, teacher {TEACHER_CODE}."), flush=True)
        await asyncio.gather(server.class_loop(), server.watch_desk())


if __name__ == "__main__":
    asyncio.run(main())
