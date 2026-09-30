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
sys.path.insert(0, HERE)
import club_ticket  # noqa: E402

TMP = tempfile.mkdtemp(prefix="desk_test_")
PY = sys.executable
DESK, RL, FL = 8880, 8881, 8882
GAMES = {"robotlab": ("games/robotlab" if PUBLIC else "shared-world-demo", "lab_server.py", "ROBOTLAB_DATA", RL),
         "fightlab": ("games/fightlab" if PUBLIC else "BeatEmUp", "fight_server.py", "FIGHTLAB_DATA", FL)}
results, procs = [], []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))


def ask(ws, msg, want="ok"):
    ws.send(json.dumps(msg))
    for _ in range(20):
        m = json.loads(ws.recv(timeout=15))
        if want in m or "error" in m:
            return m
    raise AssertionError("no answer")


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
                                   os.path.join(TMP, "games.json")], env=env, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL))
    time.sleep(2)  # (the desk makes the ticket key first)
    for game, (folder, server, data_env, port) in GAMES.items():
        procs.append(subprocess.Popen([PY, server, "--class-server", "--port", str(port)], cwd=os.path.join(CLUB, folder),
                                      env=dict(env, **{data_env: os.path.join(TMP, game)},
                                               CLUBCODERS_DESK_INBOX=os.path.join(desk_data, "inbox", game)),
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    time.sleep(8)
    versions = {g: game_version(f, "lab_version" if g == "robotlab" else "fight_version") for g, (f, *_) in GAMES.items()}

    def same_ticket_file():
        with open(os.path.join(HERE, "club_ticket.py"), "rb") as f:
            mine = f.read().replace(b"\r\n", b"\n")
        for folder, *_ in GAMES.values():
            with open(os.path.join(CLUB, folder, "club_ticket.py"), "rb") as f:
                assert f.read().replace(b"\r\n", b"\n") == mine, folder
    check("the ticket file is the same in the desk and both games", same_ticket_file)

    teacher = connect(f"ws://127.0.0.1:{DESK}")
    check("teacher: a wrong password is refused",
          lambda: (lambda m: [] if "error" in m else 1 / 0)(ask(teacher, {"type": "teacher", "password": "nope"})))
    state = {}

    def teacher_login():
        m = ask(teacher, {"type": "teacher", "password": "desk-test-teacher-password"})
        assert m.get("ok") and "state" in m, m
        state.update(m["state"])
        assert state["games"]["robotlab"]["title"] == "Robot Lab"
    check("teacher: logs in and gets the desk's state", teacher_login)

    def add_learners():
        for name, starter in (("Sam", "sam-starter"), ("Alex", ""), ("Jo", "jo-starter")):
            m = ask(teacher, {"type": "add_learner", "name": name, "starter": starter})
            assert m.get("ok"), m
        m = ask(teacher, {"type": "add_learner", "name": "Sam", "starter": "again"})
        assert not m.get("ok"), "a second Sam was allowed"
        m = ask(teacher, {"type": "state"})
        names = [l["name"] for l in m.get("state", state)["learners"]] if "state" in m else None
    check("teacher: adds learners (a starter password is made when none is given; no duplicates)", add_learners)

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

    launched = {}

    def launch():
        m = ask(teacher, {"type": "launch", "group": "Tuesday", "lesson": 3})
        assert m.get("ok") and m["teacher_window"]["game"] == "robotlab", m
        launched.update(m["teacher_window"])
        m = ask(teacher, {"type": "launch", "group": "Thursday", "lesson": 1})
        assert not m.get("ok"), "two groups were live at once"
    check("teacher: launches a group (and can't launch a second while it's live)", launch)

    go = {}

    def learner_go():
        with connect(f"ws://127.0.0.1:{DESK}") as ws:
            m = ask(ws, {"type": "login", "name": "Sam", "password": "sam-own-pass"}, want="go")
            assert m.get("go") and m["go"]["game"] == "robotlab" and m["go"]["lesson"] == 3, m
            go.update(m["go"])
    check("learner in the live group: logs in and is sent to Robot Lab with a ticket", learner_go)

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
            design["settings"]["forward_speed"] = 100  # mission 1a: change a variable and build
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
    teacher.close()
finally:
    for p in procs:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)

for name, ok, note in results:
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "\n    " + note))
print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed")
sys.exit(0 if all(ok for _, ok, _ in results) else 1)
