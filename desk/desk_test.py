"""Tests for the club desk with both games' class servers, on this laptop.

    python club-coders/desk/desk_test.py      (from the ClubCodersAI folder, with the Robot Lab .venv's python)

Starts a desk and a class server for each game in temporary folders, then checks, as the app would:
  the teacher logs in, adds a learner, makes a group, launches it and stops it
  a learner with a starter password must choose their own; then they get a ticket and the game's address
  the game server lets that ticket in; refuses a learner who isn't in the live group, a made-up ticket, and a
    ticket for the other game; closes learners' windows when the group is stopped; starts the launched lesson
  a wrong password is refused; a learner removed by the teacher is deleted by the game (profile gone)
  the ticket file in each game is the same as the desk's
  the session: the game reports who is here and what they completed (lesson 1's first mission, done as the
    learner); the teacher's note is kept; Stop files the record with all of it; the learner's My card arrives
Exit code 0 = every check passed.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

from websockets.sync.client import connect

HERE = os.path.dirname(os.path.abspath(__file__))
# the games' folders: games/<game> beside desk/ in the public repository, the club's own folders one level up
PUBLIC = os.path.isdir(os.path.join(os.path.dirname(HERE), "games"))
CLUB = os.path.dirname(HERE) if PUBLIC else os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, CLUB if not PUBLIC else os.path.dirname(HERE))  # (the engine package: club_ticket)
from engine import club_ticket  # noqa: E402

TMP = tempfile.mkdtemp(prefix="desk_test_")
PY = sys.executable
DESK, RL, FL, KL, CL, ML = 8880, 8881, 8882, 8883, 8884, 8885
CR = 8960  # (Craft Lab, CHANGE 200: 8886 is the second desk's, below)
GAMES = {"robotlab": ("games/robotlab" if PUBLIC else "shared-world-demo", "lab_server.py", "ROBOTLAB_DATA", RL),
         "fightlab": ("games/fightlab" if PUBLIC else "BeatEmUp", "fight_server.py", "FIGHTLAB_DATA", FL),
         "kartlab": ("games/kartlab" if PUBLIC else "kart", "kart_server.py", "KARTLAB_DATA", KL),
         "citylab": ("games/citylab" if PUBLIC else "city", "city_server.py", "CITYLAB_DATA", CL),  # (CHANGE 194)
         "craftlab": ("games/craftlab" if PUBLIC else "craft", "craft_server.py", "CRAFTLAB_DATA", CR),  # (CHANGE 200)
         "missions": ("games/robotlab" if PUBLIC else "shared-world-demo", "missions_server.py", "MISSIONS_DATA", ML)}  # (CHANGE 195)
VERSION_MODULES = {"robotlab": "lab_version", "fightlab": "fight_version", "kartlab": "kart_version", "citylab": "city_version",
                   "craftlab": "craft_version", "missions": "lab_version"}
results, procs = [], []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))


def ask(ws, msg, want="ok"):
    ws.send(json.dumps(msg))
    seen, end = [], time.time() + 30
    while time.time() < end:  # (the desk sends the teacher its state now and then: read past it)
        m = json.loads(ws.recv(timeout=15))
        if want in m or "error" in m:
            return m
        seen.append(",".join(sorted(m)))
    raise AssertionError(f"no answer to {msg.get('type')} (got: {'; '.join(seen[:6])})")


def game_hello(port, hello, game_version):
    """(welcome message or None, close code or None) for a login at a game server."""
    with connect(f"ws://127.0.0.1:{port}", max_size=None) as ws:
        ws.send(json.dumps({"type": "hello", "version": game_version, **hello}))
        try:
            for _ in range(40):
                m = json.loads(ws.recv(timeout=10))
                if m.get("type") == "welcome":
                    return m, None
        except Exception as e:
            code = getattr(getattr(e, "rcvd", None), "code", None)
            return None, code
    return None, None


def game_version(folder, module):
    return subprocess.run([PY, "-c", f"import {module} as v; print(v.VERSION)"], cwd=os.path.join(CLUB, folder),
                          capture_output=True, text=True).stdout.strip()


try:
    desk_data = os.path.join(TMP, "desk")
    with open(os.path.join(TMP, "games.json"), "w") as f:
        json.dump({g: f"ws://127.0.0.1:{p}" for g, (_, _, _, p) in GAMES.items()}, f)
    env = dict(os.environ, CLUBCODERS_DESK_DATA=desk_data, TEACHER_CODE="desk-test-teacher-password",
               JOIN_CODE="desk-test-join", CLUBCODERS_TICKET_KEY=os.path.join(desk_data, "ticket_key"),
               CLUBCODERS_LIVE_FILE=os.path.join(desk_data, "live.json"))
    procs.append(subprocess.Popen([PY, os.path.join(HERE, "club_desk.py"), "--port", str(DESK), "--games",
                                   os.path.join(TMP, "games.json")], env=env,
                                  stdout=open(os.path.join(TMP, "desk.log"), "w"), stderr=subprocess.STDOUT))
    time.sleep(2)  # (the desk makes the ticket key first)
    for game, (folder, server, data_env, port) in GAMES.items():
        procs.append(subprocess.Popen([PY, server, "--class-server", "--port", str(port)], cwd=os.path.join(CLUB, folder),
                                      env=dict(env, **{data_env: os.path.join(TMP, game)},
                                               CLUBCODERS_DESK_INBOX=os.path.join(desk_data, "inbox", game)),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(8)
    versions = {g: game_version(f, VERSION_MODULES[g]) for g, (f, *_) in GAMES.items()}

    def one_ticket_file():  # (the desk and both games use the engine's club_ticket: no copies to drift apart)
        assert os.path.normcase(os.path.dirname(club_ticket.__file__)).endswith("engine"), club_ticket.__file__
        for folder, *_ in GAMES.values():
            assert not os.path.exists(os.path.join(CLUB, folder, "club_ticket.py")), folder
    check("the ticket file is the engine's, used by the desk and both games", one_ticket_file)

    teacher = connect(f"ws://127.0.0.1:{DESK}")
    check("teacher: a wrong password is refused",
          lambda: (lambda m: [] if "error" in m else 1 / 0)(ask(teacher, {"type": "teacher", "password": "nope"})))
    state = {}

    def teacher_login():
        m = ask(teacher, {"type": "teacher", "password": "desk-test-teacher-password"})
        assert m.get("ok") and "state" in m, m
        assert m.get("own_password") is False, "the setup's teacher code wasn't said to be the setup's"  # (CHANGE 148)
        state.update(m["state"])
        assert state["games"]["robotlab"]["title"] == "Robot Lab"
    check("teacher: logs in and gets the desk's state", teacher_login)

    def scheme_of_work():  # (CHANGE 143) the app's Print scheme of work and lesson guide, for the page: teachers only
        m = ask(teacher, {"type": "scheme"}, want="scheme")
        sc = m.get("scheme", {})
        assert {"robotlab", "fightlab", "kartlab", "citylab", "craftlab"} <= set(sc), sorted(sc)
        assert sc["robotlab"].get("guide", {}).get("1"), "Robot Lab's lesson guide is missing"
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "scheme"}, want="scheme")
            assert "scheme" not in m and "error" in m, m
    check("teacher: the scheme of work and lesson guide (a learner's connection is refused it)", scheme_of_work)

    def add_learners():
        for name, starter in (("Sam", "sam-starter"), ("Alex", ""), ("Jo", "jo-starter")):
            m = ask(teacher, {"type": "add_learner", "name": name, "starter": starter})
            assert m.get("ok"), m
        m = ask(teacher, {"type": "add_learner", "name": "Sam", "starter": "again"})
        assert not m.get("ok"), "a second Sam was allowed"
        for name in ("Teacher", "teacher", " TEACHER "):  # (CHANGE 148: the one login form's teacher)
            m = ask(teacher, {"type": "add_learner", "name": name, "starter": "teacher-starter"})
            assert not m.get("ok"), f"a learner called {name!r} was allowed"
        m = ask(teacher, {"type": "state"})
        names = [l["name"] for l in m.get("state", state)["learners"]] if "state" in m else None
    check("teacher: adds learners (a starter password is made when none is given; no duplicates; nobody called Teacher)",
          add_learners)

    def make_group():
        m = ask(teacher, {"type": "set_group", "name": "Tuesday", "game": "robotlab", "learners": ["Sam", "Alex"]})
        assert m.get("ok"), m
        m = ask(teacher, {"type": "set_group", "name": "Thursday", "game": "fightlab", "learners": ["Jo"]})
        assert m.get("ok"), m
    check("teacher: makes groups", make_group)

    def learner_before_launch():
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "wrong"})
            assert "error" in m and "not recognised" in m["error"]
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-starter"})
            assert m.get("change_password"), m
            m = ask(ws, {"type": "set_password", "name": "Sam", "password": "sam-starter", "new": "sam-own-pass"},
                    want="changed")
            assert m.get("ok"), m
            m = json.loads(ws.recv(timeout=10))
            assert m.get("waiting"), m
    check("learner: wrong password refused; starter must be changed; then waits for the group", learner_before_launch)

    def reset_then_change():  # (CHANGE 148) after the teacher's Reset the learner chooses their own again
        m = ask(teacher, {"type": "add_learner", "name": "Kim", "starter": "kim-starter"})
        assert m.get("ok"), m
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            ask(ws, {"type": "login", "name": "Kim", "password": "kim-starter"})
            m = ask(ws, {"type": "set_password", "name": "Kim", "password": "kim-starter", "new": "kim-own-pass"},
                    want="changed")
            assert m.get("ok"), m
        m = ask(teacher, {"type": "reset_password", "name": "Kim", "starter": "kim-reset"})
        assert m.get("ok"), m
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            assert "error" in ask(ws, {"type": "login", "name": "Kim", "password": "kim-own-pass"}), "the old one works"
            m = ask(ws, {"type": "login", "name": "Kim", "password": "kim-reset"})
            assert m.get("change_password"), f"a reset password didn't have to be changed: {m}"
        assert ask(teacher, {"type": "remove_learner", "name": "Kim"}).get("ok")
    check("learner: after the teacher resets their password, they choose their own again", reset_then_change)

    launched = {}

    def launch():
        m = ask(teacher, {"type": "launch", "group": "Tuesday", "lesson": 3})
        assert m.get("ok") and "teacher_window" not in m, m  # (the teacher opens their window when ready)
        m = ask(teacher, {"type": "teacher_window"})
        assert m.get("ok") and m["teacher_window"]["game"] == "robotlab", m
        launched.update(m["teacher_window"])
        m = ask(teacher, {"type": "launch", "group": "Thursday", "lesson": 1})
        assert not m.get("ok"), "two groups were live at once"
    check("teacher: launches a group (and can't launch a second while it's live)", launch)

    go = {}

    def learner_waits():
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"})
            assert m.get("ok") and not m.get("go"), m  # (the teacher hasn't launched the learners' windows yet)
    check("learner in the live group: logs in and waits until the teacher launches the learners' windows", learner_waits)

    def learner_go():
        m = ask(teacher, {"type": "open_learners"})
        assert m.get("ok"), m
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")
            assert m.get("go") and m["go"]["game"] == "robotlab" and m["go"]["lesson"] == 3, m
            go.update(m["go"])
    check("learner in the live group: after LAUNCH LEARNERS' WINDOWS, is sent to Robot Lab with a ticket", learner_go)

    def game_accepts():
        time.sleep(3)  # (the game server reads live.json every 2 s)
        welcome, code = game_hello(RL, {"ticket": go["ticket"]}, versions["robotlab"])
        assert welcome and welcome["name"] == "Sam", (welcome, code)
        assert welcome["lesson"]["lesson_number"] == 3, welcome["lesson"].get("lesson_number")
    check("Robot Lab: accepts the ticket, on the launched lesson", game_accepts)

    def teacher_window():
        welcome, code = game_hello(RL, {"ticket": launched["ticket"]}, versions["robotlab"])
        assert welcome and welcome["role"] == "teacher", (welcome, code)
    check("Robot Lab: accepts the teacher's ticket from Launch", teacher_window)

    def refusals():
        key = club_ticket.load_key(os.path.join(desk_data, "ticket_key"))
        _, code = game_hello(RL, {"ticket": club_ticket.make(key, "Jo", "learner", "robotlab")}, versions["robotlab"])
        assert code == 4010, f"a learner outside the group got in ({code})"
        _, code = game_hello(RL, {"ticket": club_ticket.make(key, "Sam", "learner", "fightlab")}, versions["robotlab"])
        assert code == 4011, f"a Fight Lab ticket got into Robot Lab ({code})"
        _, code = game_hello(RL, {"ticket": go["ticket"][:-4] + "0000"}, versions["robotlab"])
        assert code == 4011, f"a changed ticket got in ({code})"
        _, code = game_hello(FL, {"ticket": club_ticket.make(key, "Jo", "learner", "fightlab")}, versions["fightlab"])
        assert code == 4010, f"Fight Lab let a learner in with no live group ({code})"
        for port, game in ((RL, "robotlab"), (FL, "fightlab")):  # the old class code no longer lets a learner in
            _, code = game_hello(port, {"code": "desk-test-join", "name": "Sam", "password": "x"}, versions[game])
            assert code == 4010, f"{game} let a learner in with the class code ({code})"
    check("games refuse: a learner not in the group, a ticket for the other game, a changed ticket, the class code",
          refusals)

    def session_report():
        m = ask(teacher, {"type": "stop"})  # (lesson 3 was launched: relaunch on lesson 1, whose first mission is easy)
        m = ask(teacher, {"type": "launch", "group": "Tuesday", "lesson": 1})
        assert m.get("ok"), m
        assert ask(teacher, {"type": "open_learners"}).get("ok")
        time.sleep(3)
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            go.update(ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")["go"])
        with connect(f"ws://127.0.0.1:{RL}", max_size=None) as ws:
            ws.send(json.dumps({"type": "hello", "version": versions["robotlab"], "ticket": go["ticket"]}))
            welcome = None
            for _ in range(40):
                m = json.loads(ws.recv(timeout=10))
                if m.get("type") == "welcome":
                    welcome = m
                    break
            assert welcome and welcome["lesson"]["lesson_number"] == 1
            design = welcome["design"]
            design["name"] = "Sammy"  # Mission 1, objective a: change the robot's name (a string) and build
            ws.send(json.dumps({"type": "design", "design": design}))
            card, t0 = None, time.time()
            while time.time() - t0 < 15:
                m = json.loads(ws.recv(timeout=10))
                if m.get("type") == "missions" and any(x["id"] == "1a" and x["done"] for x in m["missions"]):
                    card = m.get("card")
                    break
            assert card is not None, "mission 1a wasn't completed, or no card came with the missions"
            assert card["outcomes"].get("VAR") == 1 and card["history"][0]["missions"][0]["id"] == "1a", card
            time.sleep(6)  # (the game reports to the desk every 2 s; the desk refreshes teachers every 5 s)
            m = ask(teacher, {"type": "state"})
            for _ in range(5):
                m = json.loads(teacher.recv(timeout=10))
                if "state" in m and (m["state"].get("session") or {}).get("present"):
                    break
            ses = m["state"]["session"]
            assert "Sam" in ses["present"] and ses["done"].get("Sam") == 1, ses
            m = ask(teacher, {"type": "note", "name": "Sam", "text": "Great start on variables"})
            assert m.get("ok"), m
    check("session: the game reports who is here and what they completed; the teacher's note is kept", session_report)

    def stop_closes():
        with connect(f"ws://127.0.0.1:{RL}", max_size=None) as ws:
            ws.send(json.dumps({"type": "hello", "version": versions["robotlab"], "ticket": go["ticket"]}))
            got = False
            for _ in range(40):
                if json.loads(ws.recv(timeout=10)).get("type") == "welcome":
                    got = True
                    break
            assert got
            m = ask(teacher, {"type": "stop"})
            assert m.get("ok"), m
            rec = m.get("session_record") or {}
            assert rec.get("group") == "Tuesday" and rec.get("ended") and rec["notes"].get("Sam"), rec
            assert "Sam" in (rec.get("report") or {}).get("present", {}), "the record has no report"
            assert "1a" in rec["report"]["done"].get("Sam", {}), "the record doesn't list Sam's mission"
            m = ask(teacher, {"type": "sessions"}, want="sessions")
            assert m["sessions"] and m["sessions"][0]["id"] == rec["id"], "the filed record isn't listed"
            closed = None
            try:
                for _ in range(200):
                    ws.recv(timeout=10)
            except Exception as e:
                closed = getattr(getattr(e, "rcvd", None), "code", None)
            assert closed == 4009, f"the learner's window wasn't closed on Stop ({closed})"
    check("Stop: the learner's window is closed; the session record is filed with the report and notes", stop_closes)

    def back_to_waiting():  # (CHANGE 54) the app says the game window closed: it waits, logged in, for the next launch
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="waiting")
            assert m.get("waiting"), m
            m = ask(ws, {"type": "wait", "after": go.get("live_id")}, want="waiting")
            assert m.get("waiting") and m.get("name") == "Sam", m
            m = ask(teacher, {"type": "launch", "group": "Tuesday", "lesson": 2})
            assert m.get("ok"), m
            assert ask(teacher, {"type": "open_learners"}).get("ok")  # (the teacher launches the learners' windows)
            m = json.loads(ws.recv(timeout=10))
            assert m.get("go") and m["go"]["lesson"] == 2 and m["go"].get("live_id"), m
            # they close that game's window themselves: the desk doesn't open the same game again by itself
            m = ask(ws, {"type": "wait", "after": m["go"]["live_id"]}, want="waiting")
            assert m.get("waiting"), m
            m = ask(teacher, {"type": "stop"})
            assert m.get("ok"), m
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "wait"})
            assert "error" in m, m  # (not logged in on this connection)
    check("after Stop: the app waits, logged in, and the next launch opens the next game by itself", back_to_waiting)

    def lobby_in_out():  # (CHANGE 141) the teacher pulls a learner in from the lobby, and sends them back to it
        assert ask(teacher, {"type": "launch", "group": "Tuesday", "lesson": 1}).get("ok")
        assert ask(teacher, {"type": "open_learners"}).get("ok")
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            assert ask(ws, {"type": "login", "name": "Jo", "password": "jo-starter"}).get("change_password")
            ask(ws, {"type": "set_password", "name": "Jo", "password": "jo-starter", "new": "jo-own-pass"}, want="changed")
            m = json.loads(ws.recv(timeout=10))
            assert m.get("waiting") and "lobby" in m.get("message", ""), m  # (Jo isn't in Tuesday: the lobby)
            m = ask(teacher, {"type": "state"})
            for _ in range(5):
                if "Jo" in m.get("state", {}).get("lobby", []):
                    break
                m = json.loads(teacher.recv(timeout=10))
            assert "Jo" in m["state"]["lobby"], m.get("state", {}).get("lobby")
            assert ask(teacher, {"type": "session_learner", "name": "Jo", "in": True}).get("ok")
            m = json.loads(ws.recv(timeout=10))
            assert m.get("go") and m["go"]["game"] == "robotlab", m  # (pulled in from the lobby at once)
            time.sleep(3)  # (the game reads live.json every 2 s)
            with connect(f"ws://127.0.0.1:{RL}", max_size=None) as game:
                game.send(json.dumps({"type": "hello", "version": versions["robotlab"], "ticket": m["go"]["ticket"]}))
                for _ in range(40):
                    if json.loads(game.recv(timeout=10)).get("type") == "welcome":
                        break
                assert ask(teacher, {"type": "session_learner", "name": "Jo", "in": False}).get("ok")
                closed = None
                try:
                    for _ in range(400):
                        game.recv(timeout=10)
                except Exception as e:
                    closed = getattr(getattr(e, "rcvd", None), "code", None)
                    reason = getattr(getattr(e, "rcvd", None), "reason", "")
                assert closed == 4009 and "lobby" in reason, f"Jo wasn't sent back to the lobby ({closed})"
            live_id = m["go"]["live_id"]
            m = ask(ws, {"type": "wait", "after": live_id}, want="waiting")  # (the app, back in the lobby)
            assert m.get("waiting"), m
            assert ask(teacher, {"type": "session_learner", "name": "Jo", "in": True}).get("ok")
            m = json.loads(ws.recv(timeout=10))
            assert m.get("go") and m["go"]["live_id"] == live_id, m  # (pulled in again, though it's the same game)
        # the live group edited: its game's learners follow (Alex out, Jo kept as the teacher added her)
        assert ask(teacher, {"type": "set_group", "name": "Tuesday", "game": "robotlab", "learners": ["Sam"]}).get("ok")
        m = ask(teacher, {"type": "state"})
        for _ in range(5):
            if "state" in m:
                break
            m = json.loads(teacher.recv(timeout=10))
        assert sorted(m["state"]["live"]["learners"]) == ["Jo", "Sam"], m["state"]["live"]
        assert ask(teacher, {"type": "set_group", "name": "Tuesday", "game": "robotlab", "learners": ["Sam", "Alex"]}).get("ok")
        assert ask(teacher, {"type": "stop"}).get("ok")
    check("the lobby: a learner added to the live game is pulled in, taken out goes back to the lobby (closed by the "
          "game), and can be pulled in again; editing the live group changes its game's learners", lobby_in_out)

    def city_lab_launch():  # (CHANGE 194) a group launched into City Lab: the learner's and the teacher's tickets
        assert ask(teacher, {"type": "set_group", "name": "City", "game": "citylab", "learners": ["Sam"]}).get("ok")
        assert ask(teacher, {"type": "launch", "group": "City", "lesson": 1}).get("ok")
        try:
            launched = ask(teacher, {"type": "teacher_window"})["teacher_window"]
            assert launched["game"] == "citylab" and launched.get("ticket"), launched
            assert ask(teacher, {"type": "open_learners"}).get("ok")
            with connect(f"ws://127.0.0.1:{DESK}") as ws:
                m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")
                assert m["go"]["game"] == "citylab", m
            time.sleep(3)  # (the game server reads live.json every 2 s)
            welcome, code = game_hello(CL, {"ticket": m["go"]["ticket"]}, versions["citylab"])
            assert welcome and welcome["name"] == "Sam" and welcome.get("me") is not None and welcome.get("city"), (welcome, code)
            welcome, code = game_hello(CL, {"ticket": launched["ticket"]}, versions["citylab"])
            assert welcome and welcome["role"] == "teacher", (welcome, code)
        finally:
            ask(teacher, {"type": "stop"})
    check("City Lab: a group launched into it; the learner's and the teacher's tickets open the city", city_lab_launch)

    def craft_lab_launch():  # (CHANGE 200) a group launched into Craft Lab: the learner's and the teacher's tickets
        assert ask(teacher, {"type": "set_group", "name": "Craft", "game": "craftlab", "learners": ["Sam"]}).get("ok")
        assert ask(teacher, {"type": "launch", "group": "Craft", "lesson": 1}).get("ok")
        try:
            launched = ask(teacher, {"type": "teacher_window"})["teacher_window"]
            assert launched["game"] == "craftlab" and launched.get("ticket"), launched
            assert ask(teacher, {"type": "open_learners"}).get("ok")
            with connect(f"ws://127.0.0.1:{DESK}") as ws:
                m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")
                assert m["go"]["game"] == "craftlab", m
            time.sleep(3)  # (the game server reads live.json every 2 s)
            welcome, code = game_hello(CR, {"ticket": m["go"]["ticket"]}, versions["craftlab"])
            assert welcome and welcome["name"] == "Sam" and welcome.get("me") is not None, (welcome, code)
            welcome, code = game_hello(CR, {"ticket": launched["ticket"]}, versions["craftlab"])
            assert welcome and welcome["role"] == "teacher", (welcome, code)
        finally:
            ask(teacher, {"type": "stop"})
    check("Craft Lab: a group launched into it; the learner's and the teacher's tickets open the island", craft_lab_launch)

    def missions_launch():  # (CHANGE 195) a group launched into Missions on lesson 2: Mission 2, a run reported
        assert ask(teacher, {"type": "set_group", "name": "Story", "game": "missions", "learners": ["Sam"]}).get("ok")
        assert ask(teacher, {"type": "launch", "group": "Story", "lesson": 2}).get("ok")
        launched = ask(teacher, {"type": "teacher_window"})["teacher_window"]
        assert launched["game"] == "missions" and launched.get("ticket"), launched
        assert ask(teacher, {"type": "open_learners"}).get("ok")
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")
            assert m["go"]["game"] == "missions" and m["go"]["lesson"] == 2, m
        time.sleep(3)
        welcome, code = game_hello(ML, {"ticket": launched["ticket"]}, versions["missions"])
        assert welcome and welcome["role"] == "teacher", (welcome, code)
        with connect(f"ws://127.0.0.1:{ML}", max_size=None) as game:
            game.send(json.dumps({"type": "hello", "version": versions["missions"], "ticket": m["go"]["ticket"]}))
            welcome = None
            for _ in range(20):
                w = json.loads(game.recv(timeout=10))
                if w.get("type") == "welcome":
                    welcome = w
                    break
            assert welcome and welcome["name"] == "Sam" and welcome["lesson"]["mission"] == "lights_out", welcome
            assert "progress" in welcome and "parts" in welcome["progress"], welcome
            game.send(json.dumps({"type": "run", "mission": "lights_out", "status": "flat", "objectives": [True, False, False, False, False],
                                  "complete": False, "stars": {"count": 0}, "energy_left": 0, "lines_used": 9, "robot": "TITAN"}))
            game.send(json.dumps({"type": "run", "mission": "lights_out", "status": "complete", "objectives": [True] * 5,
                                  "complete": True, "stars": {"count": 3, "energy": True, "lines": True},
                                  "energy_left": 12, "lines_used": 11, "robot": "TITAN"}))
            game.send(json.dumps({"type": "progress", "progress": {"parts": ["solar_panel"], "missions": {
                "lights_out": {"complete": True, "bestStars": 3}}}}))
            time.sleep(6)  # (the game reports to the desk every 2 s; the desk refreshes teachers every 5 s)
            m = ask(teacher, {"type": "state"})
            for _ in range(5):
                m = json.loads(teacher.recv(timeout=10))
                if "state" in m and (m["state"].get("session") or {}).get("present"):
                    break
            ses = m["state"]["session"]
            assert "Sam" in ses["present"] and ses["done"].get("Sam") == 4, ses  # (2a finished, 2b, 2c stars, 2d fixed)
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            again = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")["go"]["ticket"]
        with connect(f"ws://127.0.0.1:{ML}", max_size=None) as game:  # (the progress follows the learner: logged in again)
            game.send(json.dumps({"type": "hello", "version": versions["missions"], "ticket": again}))
            for _ in range(20):
                w = json.loads(game.recv(timeout=10))
                if w.get("type") == "welcome":
                    break
            assert w["progress"]["missions"]["lights_out"]["bestStars"] == 3, w["progress"]
        m = ask(teacher, {"type": "stop"})
        assert m.get("ok"), m
        rec = m.get("session_record") or {}
        assert "2a" in (rec.get("report") or {}).get("done", {}).get("Sam", {}), rec.get("report")
    try:
        check("Missions: a group launched into it on lesson 2 (Lights Out); the learner's window reports a failed run then "
              "a finish with three stars, the desk's session shows four objectives, the progress follows the learner",
              missions_launch)
    finally:
        if ask(teacher, {"type": "state"}).get("state", {}).get("live"):
            ask(teacher, {"type": "stop"})

    def removed():
        m = ask(teacher, {"type": "remove_learner", "name": "Sam"})
        assert m.get("ok"), m
        profile = os.path.join(TMP, "robotlab", "profiles", "sam.json")
        for _ in range(10):
            if not os.path.exists(profile):
                break
            time.sleep(1)
        assert not os.path.exists(profile), "Robot Lab still has Sam's profile"
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"})
            assert "error" in m
    check("removing a learner: the game deletes their data and they can't log in", removed)

    def teacher_password():
        code, new = "desk-test-teacher-password", "robots like custard"
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "change_teacher_password", "password": "a wrong guess", "new": new})
            assert "error" in m, "changed without the password as it is now"
            m = ask(ws, {"type": "change_teacher_password", "password": code, "new": "too short"})
            assert "error" in m, "a short password was allowed"
            m = ask(ws, {"type": "change_teacher_password", "password": code, "new": new})
            assert m.get("teacher_password_changed"), m
            assert "error" in ask(ws, {"type": "teacher", "password": code}), "the old teacher code still works"
            m = ask(ws, {"type": "teacher", "password": new})
            assert m.get("ok"), "the new password doesn't work"
            assert m.get("own_password") is True, "the teacher's own password was said to be the setup's"
        with open(os.path.join(desk_data, "teacher.json"), encoding="utf-8") as f:
            assert new not in f.read(), "the new password is kept as it was typed"
        os.remove(os.path.join(desk_data, "teacher.json"))  # (forgotten: the server's teacher code comes back)
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            assert ask(ws, {"type": "teacher", "password": code}).get("ok"), "the teacher code didn't come back"
    check("teacher: changes the teacher password (the old code stops; removing teacher.json brings it back)",
          teacher_password)

    def learner_called_teacher():  # (CHANGE 154) one added before CHANGE 148 refused the name still logs in
        with connect(f"ws://127.0.0.1:{DESK}") as ws:  # (no such learner here: nothing more to try)
            m = ask(ws, {"type": "teacher", "password": "not-the-teacher-password"})
            assert "error" in m and not m.get("try_learner"), m
        sys.path.insert(0, HERE)
        import club_desk
        store = club_desk.Store(os.path.join(TMP, "desk2"))
        store.add_learner("Tess", "tess-starter")
        store.set_password("Tess", "tess-own-pass", by_learner=True)
        store.learners["Teacher"] = store.learners.pop("Tess")  # (as an old learners.json would have them)
        store.save()
        port = DESK + 6  # (8886: past the five game servers, 8881 to 8885; Craft Lab's is 8960)
        procs.append(subprocess.Popen([PY, os.path.join(HERE, "club_desk.py"), "--port", str(port), "--games",
                                       os.path.join(TMP, "games.json")],
                                      env=dict(env, CLUBCODERS_DESK_DATA=os.path.join(TMP, "desk2")),
                                      stdout=open(os.path.join(TMP, "desk2.log"), "w"), stderr=subprocess.STDOUT))
        time.sleep(2)
        with connect(f"ws://127.0.0.1:{port}") as ws:
            m = ask(ws, {"type": "teacher", "password": "tess-own-pass"})
            assert "error" in m and m.get("try_learner"), f"the form wasn't told to try the learner: {m}"
            m = ask(ws, {"type": "login", "name": "teacher", "password": "tess-own-pass"})
            assert m.get("ok") and "error" not in m, f"the learner called Teacher wasn't let in: {m}"
        with connect(f"ws://127.0.0.1:{port}") as ws:  # (the real teacher password is still the teacher's)
            m = ask(ws, {"type": "teacher", "password": "desk-test-teacher-password"})
            assert m.get("ok") and "state" in m, m
    check("a learner called Teacher from before CHANGE 148 is tried as a learner after the teacher password",
          learner_called_teacher)
    teacher.close()
finally:
    for p in procs:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)

for name, ok, note in results:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "\n    " + note))
print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
