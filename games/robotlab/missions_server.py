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
and sends the teacher's window the class's progress every couple of seconds. There is no world to step: the
missions run in the windows.
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

import mission_lessons as ml  # noqa: E402

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
                             "code": lab_version.CODE})
        if role == "teacher":
            await self.send(ws, self.class_msg())
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
        elif p.role == "teacher":
            await self.teacher_command(p, m)

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
