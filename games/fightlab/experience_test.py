"""Experience 1's tests (CHANGE 210): the orientation, played in the real Fight Lab (engine/experience.py).

    .venv\\Scripts\\python experience_test.py          (--quick: the first two only, no window)

1. the real server, in this process: a learner plays all nine objectives in the ring (footwork, a sidestep round the
   computer fighter, hits on it with its brain off, a whole combo, a kick, a jump kick and the special, the garage's
   string, integer and list, a value changed in the code, a brain on autopilot, a bout against the computer fighter
   with the real countdown), then the result, the stars and the best kept
2. over the network, as the windows and the page are told: a learner's "experience" messages, SKIP to the end,
   START AGAIN; the teacher's "experience_class", END and START; the learner told it has ended
3. on your own: Fight Lab's window with --experience 1 starts its own server on this laptop, logs in and draws the
   experience over the ring (a picture), and the server stops by itself after the window has gone
Test data goes to a temporary folder, never this computer's own profiles. Exit code 0 = all fine.
"""
import json
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
os.environ["FIGHTLAB_DATA"] = TMP
os.environ["APPDATA"] = TMP  # (on your own, the server's data goes in APPDATA\ClubCoders\experiences)
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note else ""), flush=True)


class FakeWs:
    """A learner's connection, for the server in this process (nothing is sent anywhere)."""


def in_process():
    import fight_server
    import fight_sim as sim
    import cpu_brains
    from engine import experience
    srv = fight_server.FightServer()
    t = srv.teaching
    check("the experience starts (on your own)", t.start_experience(1, solo=True))
    p = fight_server.Player(FakeWs(), "learner", "Tester", (60, 130, 230))
    srv.players[p.ws] = p
    srv.rebuild_stage()
    steps = [0]

    def step(n=1):
        for _ in range(n):
            srv.stage.step()
            steps[0] += 1
            if steps[0] % 30 == 0:  # (twice a second, as the physics loop: the objectives measured)
                t.tick(srv.stage.time)

    def obj():
        run = t.xrun(t.record(p.name))
        o = t.x_objective(run)
        return o["id"] if o else None

    def until(oid_gone, brain, seconds):
        """A test driver at the wheel of the learner's fighter (as their keys would be: not their autopilot)."""
        end = steps[0] + int(seconds / sim.STEP)
        while obj() == oid_gone and steps[0] < end:
            if p.fighter.brain is not brain:  # (a rebuild makes a new fighter)
                p.fighter.brain = brain
            step()
        p.fighter.brain = None
        return obj() != oid_gone

    step(31)
    msg = t.experience_msg(p)
    check("the learner is told: on, objective 1, the coach's first words", msg["on"] and msg["index"] == 0
          and msg["objective"] == "Footwork" and "SENSEI here" in msg["say"][1], msg["hint"])
    ring = p.fighter.ring
    cpu = ring.enemy_of(p.fighter)
    check("a ring of your own, the computer fighter's brain off, practice, no hazards",
          cpu is not None and cpu.owner == "Computer" and srv.lesson["cpu_level"] == "empty" and srv.stage.practice
          and not any(srv.stage.hazards.values()), f"{srv.lesson['cpu_level']}, {cpu and cpu.name}")
    check("1 footwork: 4 m", until("footwork", lambda me, en, r: (1 if int(r.stage.time) % 2 else -1, 0, ""), 20),
          f"{obj()}")
    check("2 sidestep: a quarter of the way round", until("sidestep", lambda me, en, r: (0, 1, ""), 20), f"{obj()}")

    def puncher(me, en, r):  # (walk in, then punch: pressed every tick, so each hit that lands carries the combo on)
        return (1, 0, "") if sim.distance(me, en) > 1.0 else (0, 0, "punch")
    check("3 strikes: three hits on the computer fighter", until("strikes", puncher, 30), f"{obj()}")
    check("4 combo: the whole combo landed", until("combo", puncher, 30), f"{obj()}")

    def moves(me, en, r):  # (a kick, a jump and a kick in the air, and the special when the energy is there)
        if me.energy >= sim.RULES["special_cost"]:
            return 0, 0, "special"
        if sim.distance(me, en) > 0.9:
            return 1, 0, ""
        if me.airborne:
            return 0, 0, "kick"
        return 0, 0, "kick" if int(r.stage.time) % 2 else "jump"
    check("5 moves: a kick, a jump kick and the special", until("moves", moves, 60),
          f"{obj()} {t.xrun(t.record(p.name))['base'].get('kinds')}")
    # 6 the garage, as the window's BUILD MY FIGHTER sends it (fight_server's design message)

    def build(new, by_code):
        old = p.design
        check(f"the design is one the server builds ({'code' if by_code else 'garage'})",
              not sim.check_design(new, sim.code_limits(srv.limits_for(p)) if by_code else srv.limits_for(p)))
        p.design = new
        srv.refit(p)
        t.on_design(p, new, [], True, old=old, by_code=by_code)
        step(31)
    new = json.loads(json.dumps(p.design))
    new["name"] = "Rocky"
    build(new, False)
    check("6 garage: a string alone isn't enough", obj() == "garage", f"{obj()}")
    new = json.loads(json.dumps(new))
    new["settings"]["walk_speed"] = 90
    new["colour"] = [60, 190, 90]
    build(new, False)
    check("6 garage: a string, an integer and a list, built", obj() == "code", f"{obj()}")
    new = json.loads(json.dumps(new))
    new["settings"]["jump_height"] = 95
    build(new, True)
    check("7 code: a value changed in the code and built", obj() == "brain", f"{obj()}")
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        reply = t.upload_brain(p, f.read())
    t.on_message(p, {"type": "autopilot"})
    check("8 the brain uploads", reply.get("ok"), reply.get("error"))
    end = steps[0] + int(30 / sim.STEP)
    while obj() == "brain" and steps[0] < end:
        step()
    check("8 brain: autopilot 8 s", obj() != "brain", f"{obj()}")
    # 9 the bout: on your own it starts by itself, with the countdown
    step(31)
    ring = p.fighter.ring
    check("9 a bout, on your own: battle mode, the computer fighter's brain on, the countdown, autopilot off",
          srv.lesson["mode"] == "battle" and srv.lesson["cpu_level"] == "easy" and not srv.stage.practice
          and ring.phase in ("intro", "fight") and ring.enemy_of(p.fighter).brain is not None
          and not t.record(p.name).autopilot and p.fighter.brain is None, f"{srv.lesson['mode']} {ring.phase}")
    expert = cpu_brains.for_level("expert")  # (the expert computer driver at the wheel for the test)
    for _ in range(3):  # (a lost bout: REMATCH)
        until("bout", expert, 90)
        if obj() != "bout":
            break
        acts = t.experience_msg(p)["actions"]
        check("9 a lost bout offers a rematch", acts and acts[0][0] == "rematch", json.dumps(acts))
        t.experience_message(p, {"type": "experience", "do": "action", "action": "rematch"})
    check("9 the bout won", obj() is None, f"{obj()}")
    step(31)
    msg = t.experience_msg(p)
    res = msg["result"] or {}
    check("the end: the result (XP, rank, stars, every objective)", res.get("xp", 0) >= 250 and res.get("stars", 0) >= 2
          and len(res.get("done", [])) == 9, json.dumps(res))
    check("after the bout, practice again", srv.lesson["mode"] == "practice" and srv.lesson["cpu_level"] == "empty"
          and srv.stage.practice)
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
    check("START AGAIN: a new run from objective 1", obj() == "footwork" and t.experience_msg(p)["xp"] == 0)
    check("the ranks", experience.rank_of(0, t.experience_def()) == "Rookie"
          and experience.rank_of(experience.max_xp(t.experience_def()), t.experience_def()) == "Club Coder")
    check("the definition is whole, 250 XP", not experience.check_definition(t.experience_def())
          and experience.max_xp(t.experience_def()) == 250, json.dumps(experience.check_definition(t.experience_def())))
    t.stop_experience()
    check("END puts the lesson back as it was", srv.lesson["cpu_level"] == fight_server.WEEK1_LESSON["cpu_level"]
          and srv.lesson["hazards"]["ring_out"] and srv.lesson.get("experience") == 0, srv.lesson["cpu_level"])
    if t.record(p.name).brain is not None:
        t.record(p.name).brain.close()


def over_the_network():
    from websockets.sync.client import connect
    import fight_version
    from engine import experience
    info = experience.solo_start(HERE, "fight_server.py", "fightlab", 1, "FIGHTLAB_DATA")
    try:
        check("on your own: the server on this laptop starts", experience.solo_ready(info), experience.solo_last_words(info))

        def hello(**fields):
            ws = connect(info["host"], open_timeout=5, max_size=None)
            ws.send(json.dumps({"type": "hello", "version": fight_version.VERSION} | fields))
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
        seen = {}  # (the lesson comes first, to everyone; then the learner's missions, and the experience off)

        def told(m):
            if m["type"] == "lesson" and not m["lesson"].get("experience"):
                seen.setdefault("lesson", m)
            elif m["type"] == "missions" and not m.get("experience"):
                seen.setdefault("missions", m)
            elif m["type"] == "experience" and not m["on"]:
                seen.setdefault("off", m)
            return len(seen) == 3
        wait_for(me, told)
        check("END: the learner is told it has ended", "off" in seen)
        m = seen.get("lesson")
        check("...and the lesson's own settings are back (the computer fighter's level, the hazards)",
              m is not None and m["lesson"]["cpu_level"] != "empty" and m["lesson"]["hazards"]["ring_out"],
              json.dumps((m or {}).get("lesson", {}).get("cpu_level")))
        m = seen.get("missions")
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
    proc = subprocess.run([PY, "fight_client.py", "--experience", "1", "--offscreen", "--screenshot", shot,
                           "--after", "9", "--gfx", "low"], cwd=HERE, capture_output=True, text=True, timeout=180)
    check("the window: Fight Lab with --experience 1, its own server, logged in and drawn", os.path.exists(shot),
          (proc.stdout + proc.stderr)[-300:])
    if os.path.exists(shot):
        keep = os.path.join(HERE, "experience_1.png")
        import shutil
        shutil.copy(shot, keep)
        print(f"  picture: {keep}  ({time.time() - started:.0f} s)")
    log = os.path.join(TMP, "ClubCoders", "experiences", "fightlab", "server.log")
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
