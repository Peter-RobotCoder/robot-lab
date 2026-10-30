"""Experience 1's tests (CHANGE 210): the orientation, played in the real Kart Lab (engine/experience.py).

    ..\\shared-world-demo\\.venv\\Scripts\\python experience_test.py      (--quick: the first two only, no window)

1. the real server, in this process: a learner plays all nine objectives on the Club Circuit (driving, top speed, a
   lap through the gates, two drift mini-turbos, an item picked up and used, the garage's string, integer and list,
   a value changed in the code, a brain on autopilot, a race against three computer karts with the real countdown),
   then the result, the stars and the best kept. A computer driver is at the wheel where a test can't steer: it
   goes through the server's own step, as a learner's keys or brain do
2. over the network, as the windows and the page are told: a learner's "experience" messages, SKIP to the end,
   START AGAIN; the teacher's "experience_class", END and START; the learner told it has ended
3. on your own: Kart Lab's window with --experience 1 starts its own server on this laptop, logs in and draws the
   experience over the track (a picture: experience_1.png here), and the server has stopped after the window has
   gone
Test data goes to a temporary folder, never this computer's own profiles. Exit code 0 = all fine.
"""
import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
PY = sys.executable
TMP = tempfile.mkdtemp(prefix="kart_experience_test_")
os.environ["KARTLAB_DATA"] = TMP
os.environ["APPDATA"] = TMP  # (on your own, the server's data goes in APPDATA\ClubCoders\experiences)
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note else ""), flush=True)


class FakeWs:
    """A learner's connection, for the server in this process (nothing is sent anywhere)."""
    remote_address = ("127.0.0.1", 0)
    request = None

    async def send(self, data):
        pass


def in_process():
    import kart_server
    import kart_sim as sim
    import cpu_brains
    from engine import experience
    srv = kart_server.KartServer()
    t = srv.teaching
    before = json.loads(json.dumps({k: srv.lesson.get(k) for k in ("mode", "laps", "hazards", "tools", "cpu_level")}))
    check("the experience starts (on your own)", t.start_experience(1, solo=True))
    srv.lesson["teacher_kart"] = False
    p = kart_server.Player(FakeWs(), "learner", "Tester", (60, 130, 230))
    srv.players[p.ws] = p
    srv.rebuild()
    check("its lesson: the Club Circuit, practice, no computer karts yet, every power-up on",
          srv.lesson["track"] == "club" and srv.race.practice and not srv.cpu_levels
          and all(srv.lesson["items"].values()) and srv.track_name == "Club Circuit", srv.track_name)
    steps = [0]
    expert = [None]  # (the computer driver at the wheel, as a learner's keys would be: None = hands off)

    def step(n=1):
        for _ in range(n):
            if expert[0] is not None and p.unit is not None and not t.record(p.name).autopilot:
                p.unit.brain = expert[0]  # (the server's step asks it as it asks a brain: CHANGE 210's test only)
            srv.step()
            steps[0] += 1
            if steps[0] % 30 == 0:
                t.tick(srv.race.tick * sim.STEP)

    def obj():
        run = t.xrun(t.record(p.name))
        o = t.x_objective(run)
        return o["id"] if o else None

    def until(oid_gone, drive, seconds):
        expert[0] = drive
        end = steps[0] + int(seconds / sim.STEP)
        while obj() == oid_gone and steps[0] < end:
            step()
        expert[0] = None
        return obj() != oid_gone

    def ace(k, race):  # (the expert computer driver: it drifts through the sharp bends)
        return cpu_brains.drive("expert", k, race)

    def ace_with_items(k, race):  # (...and uses whatever it picks up at once)
        th, st, bt = ace(k, race)
        return th, st, bt | (sim.USE if k.get("item") else 0)

    def design(d, code=False):
        asyncio.run(srv.on_design(p, {"type": "design", "design": d, "code": code}))

    step(31)
    msg = t.experience_msg(p)
    check("the learner is told: on, objective 1, the coach's first words", msg["on"] and msg["index"] == 0
          and msg["objective"] == "Engines on" and "CC-01 here" in msg["say"][1], msg["hint"])
    check("1 drive: 30 m driven", until("drive", lambda k, race: (1.0, 0.0, 0), 20), f"{obj()}")
    check("2 speed: 60 km/h", until("speed", ace, 30), f"{obj()}")
    check("3 lap: all 8 gates", until("lap", ace, 60), f"{obj()} {t.xrun(t.record(p.name))['value']}")
    check("4 drift: two mini-turbos", until("drift", ace, 120), f"{obj()} {t.xrun(t.record(p.name))['value']}")
    check("5 item: picked up from a box and used", until("item", ace_with_items, 90), f"{obj()}")
    # 6 the garage, as the window's BUILD MY KART sends it (kart_server's design message: on_design)
    new = json.loads(json.dumps(p.design))
    new["name"] = "Zoomer"
    design(new)
    step(31)
    check("6 garage: a string alone isn't enough", obj() == "garage" and p.design["name"] == "Zoomer", f"{obj()}")
    new = json.loads(json.dumps(p.design))
    new.update(speed=40, acceleration=30, grip=30, colour=[60, 190, 90])
    check("6 the design is one the server builds", not sim.check_design(new, srv.limits_for(p)))
    design(new)
    step(31)
    check("6 garage: a string, an integer and a list, built", obj() == "code" and p.design["speed"] == 40, f"{obj()}")
    new = json.loads(json.dumps(p.design))
    new["grip"] = 25
    design(new, code=True)
    step(31)
    check("7 code: a value changed in the code and built", obj() == "brain" and p.design["grip"] == 25, f"{obj()}")
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        source = f.read()
    asyncio.run(srv.upload_brain(p, source))
    r = t.record(p.name)
    check("8 the brain uploads", r.brain is not None and not r.brain.error)
    asyncio.run(srv.on_message(p, {"type": "autopilot"}))
    check("8 brain: autopilot 8 s", until("brain", None, 30), f"{obj()}")
    # 9 the race: on your own it starts by itself, with the countdown
    step(31)
    check("9 a race, on your own: race mode, three easy computer karts, the countdown, autopilot off",
          srv.lesson["mode"] == "race" and len(srv.cpu_levels) == 3 and set(srv.cpu_levels.values()) == {"easy"}
          and srv.race.phase == sim.FLAGS_RACE and srv.race.countdown() is not None and not r.autopilot
          and srv.race.laps == 2, f"{srv.lesson['mode']} {srv.cpu_levels}")
    srv.rebuild()  # (a build during the countdown puts everyone back on the grid: on your own, nobody presses Enter)
    acts = t.experience_msg(p)["actions"]
    check("9 a race left on the grid offers START THE RACE", srv.race.phase == sim.FLAGS_GRID and acts
          and acts[0][0] == "start", json.dumps(acts))
    t.experience_message(p, {"type": "experience", "do": "action", "action": "start"})
    check("...which starts it, with the countdown", srv.race.phase == sim.FLAGS_RACE and srv.race.countdown())
    check("9 the race finished", until("race", ace, 180), f"{obj()} {srv.race.finish}")
    step(31)
    msg = t.experience_msg(p)
    res = msg["result"] or {}
    check("the end: the result (XP, rank, stars, every objective)", res.get("xp", 0) >= 250 and res.get("stars", 0) >= 2
          and len(res.get("done", [])) == 9, json.dumps(res))
    check("first place: the race winner's bonus", res.get("bonus") and res.get("stars") == 3 and res.get("xp") == 275,
          json.dumps(res))
    check("after the race, practice again (no computer karts)", srv.lesson["mode"] == "practice" and srv.race.practice
          and not srv.cpu_levels and not srv.lesson["hazards"]["cpu_karts"])
    check("the best result is kept for the profile", (t.record(p.name).xbest or {}).get("1", {}).get("finished") == 1)
    check("the Mission tab lists the nine objectives, done", all(m["done"] for m in t.missions_msg(p)["missions"])
          and len(t.missions_msg(p)["missions"]) == 9 and t.missions_msg(p)["title"] == "Experience 1: Orientation")
    report = t.session_report("2000-01-01", [p.name])
    check("the desk's session report says who finished", report["experiences"].get("Tester", [{}])[0].get("n") == 1)
    path = t.export()
    with open(path, encoding="utf-8") as f:
        check("the evidence CSV has the experience", "Experience 1" in f.read())
    cls = t.experience_class_msg()
    check("the teacher's view: finished, with the stars", cls["learners"][0]["finished"]
          and cls["learners"][0]["stars"] == res.get("stars"), json.dumps(cls["learners"]))
    t.experience_message(p, {"type": "experience", "do": "again"})
    check("START AGAIN: a new run from objective 1", obj() == "drive" and t.experience_msg(p)["xp"] == 0)
    check("the ranks", experience.rank_of(0, t.experience_def()) == "Rookie"
          and experience.rank_of(experience.max_xp(t.experience_def()), t.experience_def()) == "Club Coder")
    t.stop_experience()
    srv.rebuild()
    check("END: the lesson's own settings back", srv.lesson.get("experience") == 0
          and {k: srv.lesson.get(k) for k in before} == before, json.dumps({k: srv.lesson.get(k) for k in before}))
    if r.brain is not None:
        r.brain.close()


def over_the_network():
    from websockets.sync.client import connect
    import kart_version
    from engine import experience
    info = experience.solo_start(HERE, "kart_server.py", "kartlab", 1, "KARTLAB_DATA")
    try:
        check("on your own: the server on this laptop starts", experience.solo_ready(info), experience.solo_last_words(info))

        def hello(**fields):
            ws = connect(info["host"], open_timeout=5, max_size=None)
            ws.send(json.dumps({"type": "hello", "version": kart_version.VERSION} | fields))
            while True:
                raw = ws.recv(timeout=10)
                if not isinstance(raw, bytes) and json.loads(raw)["type"] == "welcome":
                    return ws

        def wait_for(ws, test, seconds=10):
            end = time.time() + seconds
            while time.time() < end:
                raw = ws.recv(timeout=max(0.1, end - time.time()))
                if isinstance(raw, bytes):  # (the karts' snapshots)
                    continue
                m = json.loads(raw)
                if test(m):
                    return m
            return None
        me = hello(code="CLUB42", name=experience.SOLO_NAME, password=experience.SOLO_PASSWORD)
        m = wait_for(me, lambda m: m["type"] == "experience")
        check("the learner's window is told the experience, every second", m and m["on"] and m["solo"]
              and len(m["objectives"]) == 9, (m or {}).get("hint"))
        for i in range(9):
            me.send(json.dumps({"type": "experience", "do": "skip"}))
            wait_for(me, lambda m: m["type"] == "experience" and m["index"] == i + 1)
        m = wait_for(me, lambda m: m["type"] == "experience" and m.get("result"))
        check("SKIP to the end: finished, no XP, one star", m and m["result"]["xp"] == 0 and m["result"]["stars"] == 1,
              json.dumps((m or {}).get("result")))
        me.send(json.dumps({"type": "experience", "do": "again"}))
        m = wait_for(me, lambda m: m["type"] == "experience" and not m.get("result"))
        check("START AGAIN", m and m["index"] == 0)
        teacher = hello(code="TEACH99", name="Teacher")
        m = wait_for(teacher, lambda m: m["type"] == "experience_class")
        check("the teacher sees each learner's objective", m and m["on"] and m["learners"][0]["name"] == "Player",
              json.dumps((m or {}).get("learners")))
        teacher.send(json.dumps({"type": "experience", "do": "stop"}))
        m = wait_for(me, lambda m: m["type"] == "experience" and not m["on"])
        check("END: the learner is told it has ended", m is not None)
        m = wait_for(me, lambda m: m["type"] == "missions" and not m.get("experience"))
        check("...and the Mission tab is the lesson's again", m is not None and m["title"] != "Experience 1: Orientation")
        teacher.send(json.dumps({"type": "experience", "do": "start", "n": 1}))
        m = wait_for(me, lambda m: m["type"] == "experience" and m["on"])
        check("START: on again for the class", m is not None)
        me.close()
        teacher.close()
        end = time.time() + 40
        while time.time() < end and info["proc"].poll() is None:
            time.sleep(0.5)
        check("on your own, the server stops by itself when nobody is left", info["proc"].poll() is not None)
    finally:
        experience.solo_stop(info)


def the_window():
    shot = os.path.join(TMP, "experience_window.png")
    started = time.time()
    proc = subprocess.run([PY, "kart_client.py", "--experience", "1", "--offscreen", "--screenshot", shot,
                           "--after", "9", "--gfx", "low"], cwd=HERE, capture_output=True, text=True, timeout=180)
    check("the window: Kart Lab with --experience 1, its own server, logged in and drawn", os.path.exists(shot),
          (proc.stdout + proc.stderr)[-300:])
    if os.path.exists(shot):
        keep = os.path.join(HERE, "experience_1.png")
        shutil.copy(shot, keep)
        print(f"  picture: {keep}  ({time.time() - started:.0f} s)")
    # its server has stopped: the window stops it as it closes (engine.experience.solo_stop, at exit), and if that
    # missed (the window killed) it stops by itself (solo_watch: tested over the network above)
    log = os.path.join(TMP, "ClubCoders", "experiences", "kartlab", "server.log")
    with open(log, encoding="utf-8", errors="replace") as f:
        text = f.read()
    port = re.search(r"127\.0\.0\.1:(\d+)", text)
    end, up = time.time() + 40, True
    while port and up and time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", int(port.group(1))), timeout=0.5).close()
            time.sleep(2)
        except OSError:
            up = False
    check("...and its server stopped after the window had gone", port and not up, text[-200:])


if __name__ == "__main__":
    for fn in (in_process, over_the_network) + (() if "--quick" in sys.argv else (the_window,)):
        try:
            fn()
        except Exception as e:  # (report and carry on)
            import traceback
            traceback.print_exc()
            check(fn.__name__, False, repr(e)[-300:])
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} passed" + (": FAILED " + "; ".join(failed) if failed else ""))
    sys.exit(1 if failed else 0)
