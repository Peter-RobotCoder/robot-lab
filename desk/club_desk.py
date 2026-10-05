"""The club desk: the club's learners, groups and the live session, and every login.

    python club_desk.py                       on the class server (behind Caddy at wss://<domain>/desk), reading
                                              the games' addresses from /etc/robotlab and the teacher's password
                                              (TEACHER_CODE) from /etc/robotlab.env
    python club_desk.py --games games.json    a laptop test: {"robotlab": "ws://127.0.0.1:8795", ...}, with
                                              TEACHER_CODE and CLUBCODERS_DESK_DATA set

What it keeps (in its data folder, usernames only): learners.json (username, scrambled password, the starter
password until it's changed), groups.json (name, game, learners), live.json (the launched group: the game servers
read it to know who may join and which lesson to start), an inbox per game (requests such as "delete this
learner's data", which the game server carries out), reports/<game>.json (what the game server says is
happening in the live session) and sessions/ (one record per session: the group, game, lesson, who was there,
what each learner completed, the AI cards handled and the teacher's notes).

The teacher logs in with the teacher password and manages learners and groups, launches a group and stops it.
A learner logs in with username and password: if their group is live they get a ticket (club_ticket.py) and the
game's address, otherwise they wait, connected, and are sent on the moment their group is launched. A starter
password works once: the learner must choose their own before going on.

Wrong passwords are limited (5 a minute per username, 10 a minute per computer), as in the games.
"""
import argparse
import asyncio
import datetime
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time

import websockets

import club_ticket

GAMES = {"robotlab": "Robot Lab", "fightlab": "Fight Lab"}
ETC = "/etc/robotlab"
DATA = os.environ.get("CLUBCODERS_DESK_DATA", "/var/lib/robotlab/desk")
PORT = 8779
MAX_LEARNERS = 200
MIN_PASSWORD = 6
MIN_TEACHER_PASSWORD = 12  # (the teacher's own password: three words is good)
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}  # (as the games' profiles)
LESSONS = (1, 2, 3, 4, 5)
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class DeskError(Exception):
    pass


class RateLimit:
    def __init__(self, limit, window=60.0):
        self.limit, self.window, self.fails = limit, window, {}

    def blocked(self, key):
        now = time.monotonic()
        recent = [t for t in self.fails.get(key, []) if now - t < self.window]
        if recent:
            self.fails[key] = recent
        else:
            self.fails.pop(key, None)
        return len(recent) >= self.limit

    def failed(self, key):
        self.fails.setdefault(key, []).append(time.monotonic())


WRONG_PASSWORDS, BAD_LOGINS = RateLimit(5), RateLimit(10)


def clean_name(text):
    return re.sub(r"[^A-Za-z0-9 ]", "", str(text)).strip()[:12]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "learner"


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def clean_time(text):
    """A group's proposed time: a day and a time each week, written "Tuesday 16:00" (Tue 4.00 is read too).
    Returns it tidied, or "" for none."""
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    m = re.fullmatch(r"([A-Za-z]{3,9})\.? (\d{1,2})[:.](\d{2})", text)
    day = next((d for d in DAYS if m and d.lower().startswith(m.group(1).lower())), None)
    if not day or int(m.group(2)) > 23 or int(m.group(3)) > 59:
        raise DeskError("Write the proposed time as a day and a time, like Tuesday 16:00 (or leave it empty).")
    return f"{day} {int(m.group(2)):02d}:{m.group(3)}"


def starter_password():
    """Three short words: easy to type from a letter, changed on first login."""
    words = ("red", "blue", "gold", "fox", "owl", "cat", "bee", "sun", "moon", "star", "oak", "elm", "jet", "sky",
             "ice", "fire", "rock", "wave", "leaf", "kite", "drum", "bell", "lamp", "gear", "bolt", "wire")
    return "-".join(secrets.choice(words) for _ in range(3))


# ---------- the files ----------
class Store:
    def __init__(self, data):
        self.data = data
        os.makedirs(data, mode=0o700, exist_ok=True)
        self.learners = self._read("learners.json", {})
        self.groups = self._read("groups.json", {})
        self.live = self._read("live.json", None)
        self.key = club_ticket.load_key(os.path.join(data, "ticket_key"))

    def _read(self, name, default):
        try:
            with open(os.path.join(self.data, name), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    def _write(self, name, value):
        path = os.path.join(self.data, name)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2)
        os.replace(path + ".tmp", path)

    def save(self):
        self._write("learners.json", self.learners)
        self._write("groups.json", self.groups)
        self._write("live.json", self.live)

    # ---------- the teacher's password ----------
    def check_teacher(self, password, code):
        """Is this the teacher password? Until the teacher chooses one, it is the teacher code the server's setup
        made (code). Once one is chosen (teacher.json: scrambled, as the learners' are), only that one works.
        (Read each time, so removing teacher.json on the server brings the code back without a restart.)"""
        own = self._read("teacher.json", None)
        if isinstance(own, dict) and own.get("salt") and own.get("hash"):
            return hmac.compare_digest(self._hash(str(own["salt"]), str(password or "")), str(own["hash"]))
        return hmac.compare_digest(str(password or "").encode(), code.encode())

    def set_teacher_password(self, new):
        new = str(new or "")
        if len(new) < MIN_TEACHER_PASSWORD:
            raise DeskError(f"The teacher password needs at least {MIN_TEACHER_PASSWORD} characters: three words "
                            "you'll remember is good.")
        if len(new) > 200:
            raise DeskError("That password is too long.")
        salt = secrets.token_hex(16)
        self._write("teacher.json", {"salt": salt, "hash": self._hash(salt, new), "changed": now()})

    def from_games(self):
        """What the games' servers have asked the desk to do (each leaves a file in inbox/desk/, as the desk leaves
        its requests to a game in inbox/<game>/): read, then removed."""
        folder = os.path.join(self.data, "inbox", "desk")
        asked = []
        for entry in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
            if not entry.endswith(".json"):
                continue
            path = os.path.join(folder, entry)
            try:
                with open(path, encoding="utf-8") as f:
                    what = json.load(f)
                if isinstance(what, dict):
                    asked.append(what)
            except (OSError, ValueError):
                pass
            try:
                os.remove(path)
            except OSError:
                pass
        return asked

    def session_learner(self, username, allowed, live_id, game):
        """The teacher's tick in the game's Accounts tab: a learner is let into the live session, or taken out
        of it (the session only: the group is as it was). True if anything changed."""
        name, rec = self.find(username)
        live = self.live
        if rec is None or not live or live.get("id") != live_id or live.get("game") != game:
            return False
        if bool(allowed) == (name in live["learners"]):
            return False
        live["learners"] = live["learners"] + [name] if allowed else [n for n in live["learners"] if n != name]
        self.save()
        return True

    def request(self, game, what):
        """Something for a game's server to do (it reads its inbox every couple of seconds)."""
        inbox = os.path.join(self.data, "inbox", game)
        os.makedirs(inbox, mode=0o700, exist_ok=True)
        path = os.path.join(inbox, f"{int(time.time() * 1000)}_{secrets.token_hex(3)}.json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(what, f)
        os.replace(path + ".tmp", path)

    # ---------- learners ----------
    @staticmethod
    def _hash(salt, password):
        return "scrypt$" + hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), **SCRYPT).hex()

    def find(self, username):
        key = slug(clean_name(username))
        for name, rec in self.learners.items():
            if slug(name) == key:
                return name, rec
        return None, None

    def add_learner(self, username, starter):
        name = clean_name(username)
        if not name:
            raise DeskError("Usernames need letters or numbers (up to 12).")
        if self.find(name)[0] is not None:
            raise DeskError(f"There is already a learner called {name}.")
        if len(self.learners) >= MAX_LEARNERS:
            raise DeskError(f"The club already has {MAX_LEARNERS} learners.")
        starter = str(starter or "").strip() or starter_password()
        if len(starter) < MIN_PASSWORD:
            raise DeskError(f"Passwords need at least {MIN_PASSWORD} characters.")
        salt = secrets.token_hex(16)
        self.learners[name] = {"salt": salt, "hash": self._hash(salt, starter), "starter": starter, "changed": False,
                               "created": now(), "last_login": None}
        self.save()
        return name

    def set_password(self, username, password, by_learner=False):
        name, rec = self.find(username)
        if rec is None:
            raise DeskError("No learner with that username.")
        password = str(password or "")
        if len(password) < MIN_PASSWORD:
            raise DeskError(f"Passwords need at least {MIN_PASSWORD} characters.")
        rec["salt"] = secrets.token_hex(16)
        rec["hash"] = self._hash(rec["salt"], password)
        rec["starter"] = None if by_learner else password  # (a reset by the teacher is a new starter)
        rec["changed"] = by_learner
        self.save()
        return name

    def remove_learner(self, username):
        name, rec = self.find(username)
        if rec is None:
            raise DeskError("No learner with that username.")
        del self.learners[name]
        for g in self.groups.values():
            g["learners"] = [n for n in g["learners"] if n != name]
        if self.live and name in self.live.get("learners", []):
            self.live["learners"] = [n for n in self.live["learners"] if n != name]
        self.save()
        for game in GAMES:  # every game deletes what it keeps about them (profile, robot or fighter, evidence)
            self.request(game, {"delete_learner": name})
        return name

    def check_password(self, username, password):
        """(name, record) if the password is right, else None (with the same limits as the games)."""
        name, rec = self.find(username)
        if rec is None:
            return None
        key = slug(name)
        if WRONG_PASSWORDS.blocked(key):
            raise DeskError("Too many wrong passwords for that username. Wait a minute, then try again.")
        if not hmac.compare_digest(self._hash(rec["salt"], str(password or "")), rec["hash"]):
            WRONG_PASSWORDS.failed(key)
            return None
        rec["last_login"] = now()
        self.save()
        return name, rec

    # ---------- groups ----------
    def set_group(self, name, game, learners, rename_from=None, time=None):
        """time: the group's proposed time ("Tuesday 16:00", or "" for none). Left out (None), it stays as it was."""
        name = re.sub(r"[^A-Za-z0-9 \-]", "", str(name)).strip()[:24]
        if not name:
            raise DeskError("Give the group a name (letters and numbers).")
        if game not in GAMES:
            raise DeskError("Choose a game.")
        old = self.groups.get(rename_from) or self.groups.get(name) or {}
        time = old.get("time", "") if time is None else clean_time(time)
        if rename_from and rename_from in self.groups and rename_from != name:
            del self.groups[rename_from]
        known = [n for n in self.learners if n in (learners or [])]
        self.groups[name] = {"game": game, "learners": known, "time": time}
        self.save()
        return name

    def delete_group(self, name):
        if name not in self.groups:
            raise DeskError("No group with that name.")
        if self.live and self.live.get("group") == name:
            raise DeskError("That group is live: stop it first.")
        del self.groups[name]
        self.save()

    # ---------- the live session ----------
    def launch(self, group, lesson):
        if group not in self.groups:
            raise DeskError("No group with that name.")
        if self.live:
            raise DeskError(f"{self.live['group']} is live: stop it first.")
        lesson = int(lesson) if str(lesson).isdigit() else 1
        if lesson not in LESSONS:
            raise DeskError("Lessons are 1 to 5.")
        g = self.groups[group]
        self.live = {"id": secrets.token_hex(4), "group": group, "game": g["game"], "lesson": lesson,
                     "learners": list(g["learners"]), "started": now()}
        self.save()
        self.session_notes = {}
        try:  # (an old report from the game's last session must not be read as this one's)
            os.remove(os.path.join(self.data, "reports", f"{g['game']}.json"))
        except OSError:
            pass

    def report(self):
        """What the live group's game server says is happening (present learners, what they completed, cards)."""
        if not self.live:
            return None
        try:
            with open(os.path.join(self.data, "reports", f"{self.live['game']}.json"), encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, ValueError):
            return None
        return report if report.get("live_id") == self.live["id"] else None

    def note(self, username, text):
        name, rec = self.find(username)
        if rec is None:
            raise DeskError("No learner with that username.")
        if not self.live:
            raise DeskError("Notes are for the live session: launch a group first.")
        self.session_notes[name] = str(text)[:400]
        return name

    def stop(self):
        """End the session: its record (the desk's live details, the game's report and the notes) is filed."""
        if not self.live:
            raise DeskError("Nothing is live.")
        record = {**self.live, "ended": now(), "report": self.report(),
                  "notes": dict(getattr(self, "session_notes", {}))}
        folder = os.path.join(self.data, "sessions")
        os.makedirs(folder, mode=0o700, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")  # (the files list newest first by name)
        self._write(os.path.join("sessions", f"{stamp}_{record['id']}.json"), record)
        self.live = None
        self.session_notes = {}
        self.save()
        return record

    def sessions(self, limit=30):
        """The most recent sessions' records, newest first."""
        folder = os.path.join(self.data, "sessions")
        names = sorted(os.listdir(folder), reverse=True) if os.path.isdir(folder) else []
        out = []
        for name in names[:limit]:
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    out.append(json.load(f))
            except (OSError, ValueError):
                pass
        return out

    def state(self):
        """What the teacher's screen shows."""
        session = None
        if self.live:
            report = self.report() or {}
            done = report.get("done", {})
            session = {"present": sorted(report.get("present", {})),
                       "done": {n: len(ms) for n, ms in done.items()},
                       "cards": len(report.get("cards", [])), "notes": dict(getattr(self, "session_notes", {}))}
        return {"learners": [{"name": n, "changed": r["changed"], "starter": r["starter"], "created": r["created"],
                              "last_login": r["last_login"]} for n, r in sorted(self.learners.items())],
                "groups": [{"name": n, "game": g["game"], "learners": g["learners"], "time": g.get("time", "")}
                           for n, g in sorted(self.groups.items())],
                "games": {k: {"title": v} for k, v in GAMES.items()}, "live": self.live, "lessons": list(LESSONS),
                "session": session}


# ---------- where each game is ----------
def read_env(path):
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
    except OSError:
        pass
    return values


def server_games(etc=ETC):
    """{game: wss address} from the class files: the first class playing each game is that game's server."""
    try:
        with open(os.path.join(etc, "domain"), encoding="utf-8") as f:
            domain = f.read().strip()
    except OSError:
        return {}
    games = {}
    for name in sorted(os.listdir(etc)) if os.path.isdir(etc) else []:
        if name.startswith("class") and name.endswith(".env"):
            cls = name[:-4]
            game = read_env(os.path.join(etc, name)).get("GAME", "robotlab")
            if game in GAMES and game not in games:
                games[game] = {"address": f"wss://{domain}" + ("" if cls == "class1" else f"/{cls}"),
                               "running": os.path.join("/var/lib/robotlab", cls, *(["fightlab"] if game == "fightlab"
                                                                                  else []), "running_code")}
    return games


def running_code(game_info):
    """The code that game's server runs now (its running_code file): a live update's id, or None."""
    try:
        with open(game_info.get("running", ""), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def client_address(ws):
    host = (ws.remote_address or ("?",))[0]
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    forwarded = ws.request.headers.get("X-Forwarded-For") if local and ws.request is not None else None
    return forwarded.split(",")[-1].strip() if forwarded else host


# ---------- the connections ----------
class Desk:
    def __init__(self, store, games, teacher_password):
        self.store, self.games, self.teacher_password = store, games, teacher_password
        self.teachers = set()    # teacher connections
        self.tick = None
        self.waiting = {}        # learner connections waiting for their group: ws -> name

    def go_message(self, name):
        """Where a learner goes now: their live group's game, with a ticket; or None."""
        live = self.store.live
        if not live or name not in live.get("learners", []) or live["game"] not in self.games:
            return None
        info = self.games[live["game"]]
        return {"go": {"game": live["game"], "address": info["address"], "lesson": live["lesson"],
                       "code": running_code(info),
                       "ticket": club_ticket.make(self.store.key, name, "learner", live["game"])}}

    async def tell_teachers(self):
        msg = json.dumps({"state": self.store.state()})
        for ws in list(self.teachers):
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                self.teachers.discard(ws)

    async def send_waiting(self):
        for ws, name in list(self.waiting.items()):
            go = self.go_message(name)
            if go:
                try:
                    await ws.send(json.dumps({"ok": True, **go}))
                except websockets.ConnectionClosed:
                    pass
                self.waiting.pop(ws, None)

    async def game_requests(self):
        """Carry out what the games' servers have asked for (checked every second)."""
        changed = False
        for what in self.store.from_games():
            if "session_learner" in what:
                changed |= self.store.session_learner(what["session_learner"], what.get("in"), what.get("live_id"),
                                                      what.get("game"))
        if changed:
            await self.tell_teachers()
            await self.send_waiting()  # (a learner just let in, who was waiting, goes straight to the game)

    async def handler(self, ws):
        where = client_address(ws)
        role = None
        try:
            async for raw in ws:
                try:
                    m = json.loads(raw)
                    if not isinstance(m, dict):
                        raise ValueError
                except ValueError:
                    await ws.send(json.dumps({"ok": False, "error": "The desk didn't understand that."}))
                    continue
                kind = m.get("type")
                if kind in ("login", "set_password", "teacher", "change_teacher_password"):
                    if BAD_LOGINS.blocked(where):
                        await ws.send(json.dumps({"ok": False, "error": "Too many wrong tries from this computer. "
                                                                        "Wait a minute, then try again."}))
                        continue
                try:
                    if kind == "teacher":
                        if not self.store.check_teacher(m.get("password", ""), self.teacher_password):
                            BAD_LOGINS.failed(where)
                            raise DeskError("That isn't the teacher password.")
                        role = "teacher"
                        self.teachers.add(ws)
                        await ws.send(json.dumps({"ok": True, "state": self.store.state()}))
                    elif kind == "change_teacher_password":  # (from the login screen: it needs the password as it is now)
                        if not self.store.check_teacher(m.get("password", ""), self.teacher_password):
                            BAD_LOGINS.failed(where)
                            raise DeskError("That isn't the teacher password as it is now: nothing was changed.")
                        self.store.set_teacher_password(m.get("new", ""))
                        print("The teacher password was changed", flush=True)
                        await ws.send(json.dumps({"ok": True, "teacher_password_changed": True}))
                    elif kind == "login":
                        await self.learner_login(ws, where, m)
                    elif kind == "set_password":
                        found = self.store.check_password(m.get("name", ""), m.get("password", ""))
                        if not found:
                            BAD_LOGINS.failed(where)
                            raise DeskError("Username or password not recognised.")
                        name = self.store.set_password(found[0], m.get("new", ""), by_learner=True)
                        await ws.send(json.dumps({"ok": True, "changed": True}))
                        await self.after_login(ws, name)
                        await self.tell_teachers()
                    elif role == "teacher":
                        await self.teacher_command(ws, m)
                    else:
                        await ws.send(json.dumps({"ok": False, "error": "Log in first."}))
                except DeskError as e:
                    await ws.send(json.dumps({"ok": False, "error": str(e)}))
        finally:
            self.teachers.discard(ws)
            self.waiting.pop(ws, None)

    async def learner_login(self, ws, where, m):
        found = await asyncio.to_thread(self.store.check_password, m.get("name", ""), m.get("password", ""))
        if not found:
            BAD_LOGINS.failed(where)
            raise DeskError("Username or password not recognised. Ask your teacher if you've forgotten your password.")
        name, rec = found
        if not rec["changed"]:  # a starter password: choose your own before going on
            await ws.send(json.dumps({"ok": True, "name": name, "change_password": True}))
            return
        await ws.send(json.dumps({"ok": True, "name": name}))
        await self.after_login(ws, name)

    async def after_login(self, ws, name):
        go = self.go_message(name)
        if go:
            await ws.send(json.dumps({"ok": True, **go}))
        else:
            self.waiting[ws] = name
            await ws.send(json.dumps({"ok": True, "waiting": True, "message": "Your group hasn't started yet: wait "
                                                                                 "for your teacher."}))

    def teacher_window(self):
        live, s = self.store.live, self.store
        info = self.games[live["game"]]
        return {"game": live["game"], "address": info["address"], "code": running_code(info),
                "ticket": club_ticket.make(s.key, "Teacher", "teacher", live["game"])}

    async def teacher_command(self, ws, m):
        kind, s = m.get("type"), self.store
        if kind == "add_learner":
            name = s.add_learner(m.get("name", ""), m.get("starter", ""))
            reply = {"ok": True, "done": f"{name} added"}
        elif kind == "reset_password":
            name = s.set_password(m.get("name", ""), m.get("starter", "") or starter_password())
            reply = {"ok": True, "done": f"{name} has a new starter password"}
        elif kind == "remove_learner":
            name = s.remove_learner(m.get("name", ""))
            reply = {"ok": True, "done": f"{name} removed: the games are deleting their data"}
        elif kind == "set_group":
            name = s.set_group(m.get("name", ""), m.get("game", ""), m.get("learners", []), m.get("rename_from"),
                               m.get("time"))
            reply = {"ok": True, "done": f"Group {name} saved"}
        elif kind == "delete_group":
            s.delete_group(m.get("name", ""))
            reply = {"ok": True, "done": "Group deleted"}
        elif kind == "launch":
            s.launch(m.get("group", ""), m.get("lesson", 1))
            live = s.live
            if live["game"] not in self.games:
                s.stop()
                raise DeskError(f"{GAMES[live['game']]} isn't set up on this server yet.")
            reply = {"ok": True, "done": f"{live['group']} is live: press Open teacher window when you're ready"}
        elif kind == "teacher_window":  # (open the live group's teacher window again)
            if not s.live:
                raise DeskError("Nothing is live: launch a group first.")
            reply = {"ok": True, "teacher_window": self.teacher_window()}
        elif kind == "note":
            name = s.note(m.get("name", ""), m.get("text", ""))
            reply = {"ok": True, "done": f"Note for {name} saved"}
        elif kind == "stop":
            record = s.stop()
            present = len((record.get("report") or {}).get("present", {}))
            reply = {"ok": True, "done": f"Stopped: {present} learners were in this session; its record is filed",
                     "session_record": record}
        elif kind == "sessions":
            reply = {"ok": True, "sessions": s.sessions()}
        elif kind == "state":
            reply = {"ok": True}
        else:
            raise DeskError("The desk didn't understand that.")
        await ws.send(json.dumps(reply))
        await self.tell_teachers()
        await self.send_waiting()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--bind", default="127.0.0.1", help="127.0.0.1: only Caddy (on this server) can reach it")
    ap.add_argument("--games", help="laptop test: a JSON file {game: address} instead of /etc/robotlab")
    args = ap.parse_args()
    teacher_password = os.environ.get("TEACHER_CODE", "")
    if len(teacher_password) < 8:
        raise SystemExit("The desk needs the teacher password in TEACHER_CODE (at least 8 characters).")
    if args.games:
        with open(args.games, encoding="utf-8") as f:
            games = {g: (v if isinstance(v, dict) else {"address": v}) for g, v in json.load(f).items()}
    else:
        games = server_games()
    desk = Desk(Store(DATA), games, teacher_password)
    async def refresh():  # (the teacher's screen follows the live session: who's here, what they've completed)
        seconds = 0
        while True:
            await asyncio.sleep(1)
            seconds += 1
            await desk.game_requests()
            if seconds % 5 == 0 and desk.store.live and desk.teachers:
                await desk.tell_teachers()
    async with websockets.serve(desk.handler, args.bind, args.port, max_size=16 * 1024):
        print(f"Club desk on {args.bind}:{args.port}: {len(desk.store.learners)} learners, "
              f"{len(desk.store.groups)} groups, games {', '.join(games) or 'none'}", flush=True)
        await refresh()


if __name__ == "__main__":
    asyncio.run(main())
