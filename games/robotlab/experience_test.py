"""Experience 1's tests (CHANGE 210): the orientation, played in the real Robot Lab (engine/experience.py).

    .venv\\Scripts\\python experience_test.py          (--quick: the first two only, no window)

1. the real server, in this process: a learner plays all nine objectives in the arena (driving, turning, top speed,
   the weapon, hits on Sparky 1, the garage's string, integer and list, a value changed in the code, a brain on
   autopilot, a battle against Sparky 1 with the real countdown), then the result, the stars and the best kept
2. over the network, as the windows and the page are told: a learner's "experience" messages, SKIP to the end,
   START AGAIN; the teacher's "experience_class", END and START; the learner told it has ended
3. on your own: Robot Lab's window with --experience 1 starts its own server on this laptop, logs in and draws the
   experience over the arena (a picture), and the server stops by itself after the window has gone
Test data goes to a temporary folder, never this computer's own profiles. Exit code 0 = all fine.
"""
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
PY = sys.executable
TMP = tempfile.mkdtemp(prefix="experience_test_")
os.environ["ROBOTLAB_DATA"] = TMP
os.environ["APPDATA"] = TMP  # (on your own, the server's data goes in APPDATA\ClubCoders\experiences)
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note else ""), flush=True)


class FakeWs:
    """A learner's connection, for the server in this process (nothing is sent anywhere)."""


def in_process():
    import lab_server
    import lab_sim as sim
    import cpu_brains
    from engine import experience
    srv = lab_server.LabServer()
    t = srv.teaching
    check("the experience starts (on your own)", t.start_experience(1, solo=True))
    srv.lesson["teacher_robot"] = False
    p = lab_server.Player(FakeWs(), "learner", "Tester", (60, 130, 230))
    srv.players[p.ws] = p
    srv.rebuild_arena()
    steps = [0]

    def step(n=1):
        for _ in range(n):
            if srv.intro_started is not None and steps[0] * sim.STEP - intro_at[0] >= lab_server.INTRO_SECONDS:
                srv.end_intro()
            srv.arena.step()
            steps[0] += 1
            if steps[0] % 30 == 0:
                t.tick(srv.arena.time)

    intro_at = [0.0]

    def obj():
        run = t.xrun(t.record(p.name))
        o = t.x_objective(run)
        return o["id"] if o else None

    def until(oid_gone, drive, seconds):
        end = steps[0] + int(seconds / sim.STEP)
        while obj() == oid_gone and steps[0] < end:
            drive()
            step()
        return obj() != oid_gone

    def steer_to(x, y, speed=1.0, fire=False):
        r = p.robot
        want = math.degrees(math.atan2(y - r.pos.y, x - r.pos.x)) - 90
        ang = (want - r.np.getH() + 180) % 360 - 180
        r.drive(speed * (0.3 if abs(ang) > 60 else 1.0), max(-1.0, min(1.0, ang / 30)), fire)
        return math.hypot(x - r.pos.x, y - r.pos.y)

    step(31)
    msg = t.experience_msg(p)
    check("the learner is told: on, objective 1, the coach's first words", msg["on"] and msg["index"] == 0
          and msg["objective"] == "Wake up" and "CC-01 here" in msg["say"][1], msg["hint"])
    check("1 drive: 4 m driven", until("drive", lambda: p.robot.drive(1.0, 0.0, False), 20), f"{obj()}")
    check("2 turn: right round", until("turn", lambda: p.robot.drive(0.0, 1.0, False), 30), f"{obj()}")
    check("3 speed: 12 km/h", until("speed", lambda: steer_to(0, 0), 30), f"{obj()}")

    def fire_taps():
        p.robot.drive(0.0, 0.0, steps[0] % 20 < 2)
    check("4 weapon: used three times", until("weapon", fire_taps, 30), f"{obj()}")
    cpu = srv.cpus[0].robots[0]
    check("4 the target is the computer robot, its brain off", cpu.brain is None or srv.lesson["cpu_level"] == "none",
          srv.lesson["cpu_level"])
    expert = cpu_brains.for_level("expert")  # (the expert computer driver at the wheel: a wedge flips from the side)
    p.robot.brain = expert
    check("5 target: three hits on Sparky 1", until("target", lambda: None, 120), f"{obj()}")
    p.robot.brain = None
    # 6 the garage, as the window's REBUILD MY ROBOT sends it (lab_server's design message: on_design)
    old = p.design
    new = json.loads(json.dumps(old))
    new["name"] = "Zappy"
    srv.rebuild_robot(p, new)
    p.design = new
    t.on_design(p, new, [], True, old=old, by_code=False)
    step(31)
    check("6 garage: a string alone isn't enough", obj() == "garage", f"{obj()}")
    old, new = new, json.loads(json.dumps(new))
    new["settings"]["turn_speed"] = 90
    new["colour"] = [60, 190, 90]
    check("6 the design is one the server builds", not sim.check_design(new, srv.limits_for(p)))
    srv.rebuild_robot(p, new)
    p.design = new
    t.on_design(p, new, [], True, old=old, by_code=False)
    step(31)
    check("6 garage: a string, an integer and a list, rebuilt", obj() == "code", f"{obj()}")
    old, new = new, json.loads(json.dumps(new))
    new["settings"]["forward_speed"] = 95
    srv.rebuild_robot(p, new)
    p.design = new
    t.on_design(p, new, [], True, old=old, by_code=True)
    step(31)
    check("7 code: a value changed in the code and rebuilt", obj() == "brain", f"{obj()}")
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        reply = t.upload_brain(p, f.read())
    t.on_message(p, {"type": "autopilot"})
    check("8 the brain uploads", reply.get("ok"), reply.get("error"))
    check("8 brain: autopilot 8 s", until("brain", lambda: None, 30), f"{obj()}")
    # 9 the battle: on your own it starts by itself, with the countdown
    intro_at[0] = steps[0] * sim.STEP
    step(31)
    check("9 a battle, on your own: battle mode, Sparky 1's brain on, the countdown",
          srv.lesson["mode"] == "battle" and srv.lesson["cpu_level"] == "easy" and srv.intro_started is not None
          and not t.record(p.name).autopilot, srv.lesson["mode"])
    for _ in range(3):  # (the expert computer driver at the wheel for the test; a lost battle: REMATCH)
        def fight():
            if p.robot.brain is not expert:
                p.robot.brain = expert
        until("bout", fight, 90)
        if obj() != "bout":
            break
        acts = t.experience_msg(p)["actions"]
        check("9 a lost battle offers a rematch", acts and acts[0][0] == "rematch", json.dumps(acts))
        t.experience_message(p, {"type": "experience", "do": "action", "action": "rematch"})
        intro_at[0] = steps[0] * sim.STEP
    check("9 the battle won", obj() is None, f"{obj()}")
    step(31)
    msg = t.experience_msg(p)
    res = msg["result"] or {}
    check("the end: the result (XP, rank, stars, every objective)", res.get("xp", 0) >= 250 and res.get("stars", 0) >= 2
          and len(res.get("done", [])) == 9, json.dumps(res))
    check("after the battle, practice again", srv.lesson["mode"] == "practice" and srv.lesson["cpu_level"] == "none")
    check("the best result is kept for the profile", (t.record(p.name).xbest or {}).get("1", {}).get("finished") == 1)
    check("the Mission tab lists the nine objectives, done", all(m["done"] for m in t.missions_msg(p)["missions"])
          and t.missions_msg(p)["title"] == "Experience 1: Orientation")
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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def over_the_network():
    from websockets.sync.client import connect
    import lab_version
    from engine import experience
    info = experience.solo_start(HERE, "lab_server.py", "robotlab", 1, "ROBOTLAB_DATA")
    try:
        check("on your own: the server on this laptop starts", experience.solo_ready(info), experience.solo_last_words(info))

        def hello(**fields):
            ws = connect(info["host"], open_timeout=5, max_size=None)
            ws.send(json.dumps({"type": "hello", "version": lab_version.VERSION} | fields))
            while json.loads(ws.recv(timeout=10))["type"] != "welcome":
                pass
            return ws

        def wait_for(ws, test, seconds=10):
            end = time.time() + seconds
            while time.time() < end:
                m = json.loads(ws.recv(timeout=max(0.1, end - time.time())))
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
    proc = subprocess.run([PY, "lab_client.py", "--experience", "1", "--offscreen", "--screenshot", shot,
                           "--after", "9", "--gfx", "low"], cwd=HERE, capture_output=True, text=True, timeout=180)
    check("the window: Robot Lab with --experience 1, its own server, logged in and drawn", os.path.exists(shot),
          (proc.stdout + proc.stderr)[-300:])
    if os.path.exists(shot):
        keep = os.path.join(HERE, "experience_1.png")
        import shutil
        shutil.copy(shot, keep)
        print(f"  picture: {keep}  ({time.time() - started:.0f} s)")
    log = os.path.join(TMP, "ClubCoders", "experiences", "robotlab", "server.log")
    with open(log, encoding="utf-8", errors="replace") as f:
        text = f.read()
    port = int(text.split("127.0.0.1:")[1].split(".")[0]) if "127.0.0.1:" in text else None
    end, alive = time.time() + 60, True
    while time.time() < end and alive:  # (the window stops it as it closes; if it can't, the server stops itself)
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
            time.sleep(1)
        except (OSError, TypeError):
            alive = False
    check("...and its server has stopped now the window has gone", port and not alive, f"port {port}")


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
