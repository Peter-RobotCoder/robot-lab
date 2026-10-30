"""Experience 1's tests (CHANGE 210): the orientation, played in the real City Lab (engine/experience.py).

    ..\\shared-world-demo\\.venv\\Scripts\\python experience_test.py          (--quick: the first two only, no window)

1. the real server, in this process: a learner plays all nine objectives in the city (a walk, punches and kicks on a
   robot, into a parked car, 100 m on the road, a parcel from the DEPOT delivered, the garage's string, integer and
   list, a value changed in the code, a brain on autopilot, a street race against the computer's racers with the
   real countdown), then the result, the stars and the best kept
2. over the network, as the windows and the page are told: a learner's "experience" messages, SKIP to the end,
   START AGAIN; the teacher's "experience_class", END and START; the learner told it has ended
3. on your own: City Lab's window with --experience 1 starts its own server on this laptop, logs in and draws the
   experience over the city (a picture: experience_1.png here), and the server has stopped after the window has gone
   (the window stops it as it closes; part 2 shows the server stopping by itself once nobody is connected)
The test drives the learner's person and car itself, as the window's keys would, through the server's own step (a
"brain" that answers like the keys: a walk in the world's frame on foot, the pedals and the wheel in a car); where a
test can't sensibly steer, the computer's own drivers are at the wheel (cpu_brains: the traffic's on the road, an
expert racer in the race) and, for the brain objective, the real starter brain (brains/my_brain.py) in its sandbox.
The city is Little Lab (shorter walks: the same game). Test data goes to a temporary folder, never this computer's
own profiles. Exit code 0 = all fine.
"""
import copy
import json
import math
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
TMP = tempfile.mkdtemp(prefix="citylab_experience_test_")
os.environ["CITYLAB_DATA"] = TMP
os.environ["APPDATA"] = TMP  # (on your own, the server's data goes in APPDATA\ClubCoders\experiences)
import city_version  # noqa: E402,F401  (puts the engine on the path)
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note else ""), flush=True)


class FakeWs:
    """A learner's connection, for the server in this process (nothing is sent anywhere)."""


def in_process():
    import city_server
    import city_sim as sim
    import cpu_brains
    from engine import experience
    srv = city_server.CityServer()
    t = srv.teaching
    before = copy.deepcopy(srv.lesson)
    check("the experience starts (on your own)", t.start_experience(1, solo=True))
    srv.lesson["teacher_player"] = False
    srv.lesson["city"] = "village"
    p = city_server.Player(FakeWs(), "learner", "Tester", (60, 130, 230))
    srv.players[p.ws] = p
    srv.rebuild()
    r = t.record(p.name)
    steps = [0]

    def step(n=1):
        for _ in range(n):
            srv.step()
            steps[0] += 1
            brain = p.unit.brain if p.unit is not None else None
            fn = getattr(brain, "fn", None)  # (the real brain's answer comes a tick late: wait for it, as brain_test does)
            if fn is not None and srv.world.tick % city_server.BRAIN_EVERY == 1:
                end = time.perf_counter() + 0.05
                while fn.pending is not None and fn.replies.empty() and time.perf_counter() < end:
                    time.sleep(0.0005)
            if steps[0] % 30 == 0:
                t.tick(srv.world.tick * sim.STEP)

    def obj():
        run = t.xrun(t.record(p.name))
        o = t.x_objective(run)
        return o["id"] if o else None

    def me():
        return srv.world.people[p.person]

    def done(oid):
        return oid in t.xrun(t.record(p.name))["done"]

    def until(oid, keys, seconds):
        """Step with keys at the controls (a brain-shaped function, or None for whatever is attached) until the
        objective is done (True) or the time is up."""
        end = steps[0] + int(seconds / sim.STEP)
        while obj() == oid and steps[0] < end:
            if keys is not None:
                p.unit.brain = keys  # (again each tick: the server's rebuild gives the person a new unit)
            step()
        return done(oid)

    def walk(points, run=True, stop_at=1.2):
        """On foot to each point in turn (the window's keys: a walk in the world's frame)."""
        def keys(person, world):
            while len(points) > 1 and math.hypot(points[0][0] - person["x"], points[0][1] - person["y"]) < stop_at:
                points.pop(0)
            tx, ty = points[0]
            dx, dy = tx - person["x"], ty - person["y"]
            d = math.hypot(dx, dy)
            if d < stop_at:
                return 0.0, 0.0, 0
            return dx / d, dy / d, sim.RUN if run and d > 4 else 0
        return keys

    def out_to_road(x, y):
        """Straight out to the middle of the nearest road (a corner can have a lamp post on it)."""
        rx, ry = srv.world.city.junction(*cpu_brains.nearest_junction(srv.world.city, x, y))
        return (rx, y) if abs(rx - x) < abs(ry - y) else (x, ry)

    def by_road(x, y, tx, ty):
        """The points to walk from (x, y) to (tx, ty) along the roads: the nearest junction, along and up the grid,
        then the road beside the target, then the target."""
        c = srv.world.city
        k, m = cpu_brains.nearest_junction(c, x, y)
        tk, tm = cpu_brains.nearest_junction(c, tx, ty)
        pts = [out_to_road(x, y), c.junction(k, m)]
        while k != tk:
            k += 1 if tk > k else -1
            pts.append(c.junction(k, m))
        while m != tm:
            m += 1 if tm > m else -1
            pts.append(c.junction(k, m))
        jx, jy = pts[-1]
        pts.append((tx, jy) if abs(tx - jx) > abs(ty - jy) else (jx, ty))
        return pts + [(tx, ty)]

    step(31)
    msg = t.experience_msg(p)
    check("the learner is told: on, objective 1, the coach's first words", msg["on"] and msg["index"] == 0
          and msg["objective"] == "Wake up" and "CC-01 here" in msg["say"][1], msg["hint"])
    check("the lesson it is played in: the robots and the traffic on, the jobs on, brains allowed",
          srv.lesson["hazards"] == {"traffic": True, "robots": True} and all(srv.lesson["jobs"].values())
          and srv.lesson["tools"]["brains"] and srv.world.robots, json.dumps(srv.lesson["hazards"]))
    c = srv.world.city
    k, m = cpu_brains.nearest_junction(c, me()["x"], me()["y"])
    check("1 walk: 10 m on foot", until("walk", walk([out_to_road(me()["x"], me()["y"]), c.junction(k, m),
                                                      c.junction(k + (1 if k < c.cols else -1), m)]), 30),
          f"{obj()} {t.experience_msg(p)['hint']}")

    def fight(person, world):  # (to the nearest robot that is up, facing it; punch and kick it when close)
        up = [x for x in world.robots.values() if x["hp"] > 0 and not x["link"]]
        if not up:
            return 0.0, 0.0, 0
        rb = min(up, key=lambda x: math.hypot(x["x"] - person["x"], x["y"] - person["y"]))
        dx, dy = rb["x"] - person["x"], rb["y"] - person["y"]
        d = math.hypot(dx, dy) or 1.0
        off = abs((math.degrees(math.atan2(dy, dx)) - person["yaw"] + 180) % 360 - 180)
        if d > 2.0 or off > 25:
            return dx / d, dy / d, sim.RUN if d > 6 else 0
        return 0.0, 0.0, sim.PUNCH if (steps[0] // 40) % 2 else sim.KICK
    check("2 robot: four punches and kicks landed on a robot", until("robot", fight, 120),
          f"{obj()} landed {srv.world.landed.get(p.person)}")

    def get_in(person, world):  # (to the nearest empty car, and E beside it)
        if person["link"]:
            return 0.0, 0.0, 0
        free = [x for x in world.cars.values() if not x["link"]]
        car = min(free, key=lambda x: math.hypot(x["x"] - person["x"], x["y"] - person["y"]))
        dx, dy = car["x"] - person["x"], car["y"] - person["y"]
        d = math.hypot(dx, dy) or 1.0
        if d < sim.ENTER_REACH:
            return 0.0, 0.0, sim.ACTION
        return dx / d, dy / d, sim.RUN if d > 5 else 0
    check("3 car: into a parked car (E)", until("car", get_in, 60), f"{obj()}")
    check("3 ...in it", me()["link"] != 0)
    lanes = {}

    def on_the_road(person, world):  # (the computer's traffic driver at the wheel: it keeps to its lane)
        cid = person["link"] - 1
        return cpu_brains.drive_car(cid, world.cars[cid], world, lanes) if person["link"] else (0.0, 0.0, 0)
    check("4 drive: 100 m on the road", until("drive", on_the_road, 60), f"{obj()} {t.experience_msg(p)['hint']}")
    # 5 the delivery: R back to the depot on foot, into its ring, and to the address along the roads
    p.unit.brain = lambda person, world: (0.0, 0.0, sim.RESPAWN)
    step(6)
    check("5 R: back at the depot, on foot", not me()["link"] and srv.world.city.in_zone("depot", me()["x"], me()["y"]),
          f"{me()['x']:.0f}, {me()['y']:.0f}")
    depot = srv.world.jobs.marker("depot")
    to_depot = walk([depot], run=False, stop_at=0.5)
    end = steps[0] + 20 * 60
    while srv.world.jobs.mine.get(p.person) is None and steps[0] < end:
        p.unit.brain = to_depot
        step()
    job = srv.world.jobs.mine.get(p.person) or {}
    check("5 a parcel from the DEPOT's ring", job.get("kind") == 1, json.dumps(job, default=str)[:200])
    if job.get("target"):
        route = walk(by_road(me()["x"], me()["y"], *job["target"]), stop_at=1.0)
        check("5 delivery: a parcel delivered to its address", until("delivery", route, 120),
              f"{obj()} at {me()['x']:.0f}, {me()['y']:.0f}, to {job['target']}")
    p.unit.brain = None
    # 6 the garage, as the window's BUILD MY DRIVER sends it (city_server's design message: on_design)

    def build(change, by_code):
        old = p.design
        new = copy.deepcopy(old)
        change(new)
        problems = sim.check_design(new, srv.limits_for(p))
        p.design = new
        srv.refit(p)
        t.on_design(p, new, problems, not problems, old=old, by_code=by_code)
        step(31)
        return problems
    build(lambda d: d.update(name="Zippy"), False)
    check("6 garage: a string alone isn't enough", obj() == "garage", f"{obj()}")
    problems = build(lambda d: (d["points"].update(speed=39, acceleration=28), d.update(colour=[60, 190, 90])), False)
    check("6 the design is one the server builds", not problems, "; ".join(problems))
    check("6 garage: a string, an integer and a list, built", obj() == "code", f"{obj()}")
    build(lambda d: d.update(body="rally"), True)
    check("7 code: a value changed in the code and built from there", obj() == "brain", f"{obj()}")
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        reply = t.upload_brain(p, f.read())
    check("8 the brain uploads", reply.get("ok"), reply.get("error"))
    r.autopilot = True  # (P: as city_server's autopilot message does)
    r.brain.error, r.brain.started = None, None
    t.attach(p)
    check("8 brain: autopilot on for 15 s", until("brain", None, 40),
          f"{obj()} {t.experience_msg(p)['hint']} {r.brain.error if r.brain else ''}")
    # 9 the street race: on your own it starts by itself, on the line, with the countdown
    step(31)
    race = srv.world.jobs.race
    check("9 a race, on your own: race mode, on the line in a car, the computer's racers, the countdown, autopilot "
          "off", srv.lesson["mode"] == "race" and race is not None and race["state"] == "forming"
          and me()["link"] - 1 in race["cars"] and len(srv.racers) == 2 and not r.autopilot
          and p.unit.brain is None, f"{srv.lesson['mode']} {race and race['state']}")
    t0 = steps[0]  # (the first race sat out on the line: the racers finish, and the time runs out on this one)
    while srv.world.jobs.race is not None and steps[0] - t0 < 240 / sim.STEP:
        p.unit.brain = lambda person, world: (0.0, 0.0, 0)
        step()
    step(31)
    msg = t.experience_msg(p)
    check("9 a race not finished: the coach says so, and REMATCH", "Not this time" in msg["say"][1]
          and msg["actions"] == [["rematch", "REMATCH"]] and not done("race"), f"{msg['say']} {msg['actions']}")
    t.experience_message(p, {"type": "experience", "do": "action", "action": "rematch"})
    race = srv.world.jobs.race
    check("9 REMATCH: on the line again, with two racers (the last ones gone off as traffic, the traffic as it was)",
          race is not None and race["state"] == "forming" and me()["link"] - 1 in race["cars"] and len(srv.racers) == 2
          and len(srv.traffic) == srv.lesson["traffic"], f"{race and race['state']} {len(srv.traffic)} traffic")
    for attempt in range(3):  # (the expert computer racer at the wheel for the test; a race not finished: REMATCH)
        memory = {}

        def racing(person, world):
            cid = person["link"] - 1
            return cpu_brains.drive_racer(cid, world.cars[cid], world, memory, "expert") if person["link"] else \
                (0.0, 0.0, 0)
        until("race", racing, 200)
        if obj() != "race":
            break
        while srv.world.jobs.race is not None:
            step()
        step(31)
        acts = t.experience_msg(p)["actions"]
        check("9 a race not finished offers a rematch", acts and acts[0][0] == "rematch", json.dumps(acts))
        t.experience_message(p, {"type": "experience", "do": "action", "action": "rematch"})
    check("9 the race finished", done("race"), f"{obj()}")
    step(31)
    msg = t.experience_msg(p)
    res = msg["result"] or {}
    check("the end: the result (XP, rank, stars, every objective)", res.get("xp", 0) >= 250 and res.get("stars", 0) >= 2
          and len(res.get("done", [])) == 9, json.dumps(res))
    check("after the race, practice again", srv.lesson["mode"] == "practice")
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
    check("START AGAIN: a new run from objective 1", obj() == "walk" and t.experience_msg(p)["xp"] == 0)
    check("the ranks", experience.rank_of(0, t.experience_def()) == "Rookie"
          and experience.rank_of(experience.max_xp(t.experience_def()), t.experience_def()) == "Club Coder")
    t.stop_experience()
    check("END: the lesson's own settings back", srv.lesson.get("experience") == 0
          and srv.lesson["cpu_level"] == before["cpu_level"] and srv.lesson["hazards"] == before["hazards"],
          f"{srv.lesson['cpu_level']} {srv.lesson['hazards']}")
    if r.brain:
        r.brain.close()


def over_the_network():
    from websockets.sync.client import connect
    from engine import experience
    info = experience.solo_start(HERE, "city_server.py", "citylab", 1, "CITYLAB_DATA")
    try:
        check("on your own: the server on this laptop starts", experience.solo_ready(info), experience.solo_last_words(info))

        def recv(ws, seconds):
            """The next JSON message (the 30-a-second binary snapshots passed over)."""
            end = time.time() + seconds
            while True:
                raw = ws.recv(timeout=max(0.1, end - time.time()))
                if not isinstance(raw, bytes):
                    return json.loads(raw)

        def hello(**fields):
            ws = connect(info["host"], open_timeout=5, max_size=None)
            ws.send(json.dumps({"type": "hello", "version": city_version.VERSION} | fields))
            while recv(ws, 10)["type"] != "welcome":
                pass
            return ws

        def wait_for(ws, test, seconds=10):
            end = time.time() + seconds
            while time.time() < end:
                m = recv(ws, max(0.1, end - time.time()))
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
        m = wait_for(me, lambda m: m["type"] == "lesson" and m["lesson"].get("experience") == 1)
        check("START: every window is told the lesson it is played in", m is not None
              and m["lesson"]["hazards"].get("robots"))
        m = wait_for(me, lambda m: m["type"] == "experience" and m["on"])
        check("...and it is on again for the class", m is not None)
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
    proc = subprocess.run([PY, "city_client.py", "--experience", "1", "--offscreen", "--screenshot", shot,
                           "--after", "9", "--gfx", "low", "--mute"], cwd=HERE, capture_output=True, text=True,
                          timeout=180)
    out = proc.stdout + proc.stderr
    check("the window: City Lab with --experience 1, its own server, logged in and drawn", os.path.exists(shot)
          and proc.returncode == 0 and "Traceback" not in out, out[-300:])
    if os.path.exists(shot):
        keep = os.path.join(HERE, "experience_1.png")
        shutil.copy(shot, keep)
        print(f"  picture: {keep}  ({time.time() - started:.0f} s)")
    # The window stops its own server as it closes (atexit: experience.solo_stop); a window that dies without closing
    # leaves it to the server's solo_watch, which stops it 15 s after the window has gone (over_the_network's check).
    log = os.path.join(TMP, "ClubCoders", "experiences", "citylab", "server.log")
    with open(log, encoding="utf-8", errors="replace") as f:
        text = f.read()
    port = int(re.search(r"127\.0\.0\.1:(\d+)", text).group(1)) if re.search(r"127\.0\.0\.1:(\d+)", text) else None
    end, listening = time.time() + 40, True
    while time.time() < end and listening and port:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
            time.sleep(1)
        except OSError:
            listening = False
    check("...and its server has stopped after the window had gone", port and not listening
          and "+ Player (learner)" in text, text[-200:])


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
