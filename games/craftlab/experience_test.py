"""Experience 1's tests (CHANGE 210): the orientation, played in the real Craft Lab (engine/experience.py).

    ..\\shared-world-demo\\.venv\\Scripts\\python experience_test.py          (--quick: the first two only, no window)

1. the real server, in this process: a learner plays all nine objectives on the island (walking, two blocks put
   down, climbing onto them, two logs chopped by hand, Boards and a Fabricator built from the blueprints and the
   Fabricator put down, the garage's string, integer and list, a value changed in the code, the Bot kit, a Bot dock
   and its Bot digging on autopilot with brains/my_bot.py, the dusk brought on your own and a Glitch from a real rift
   defeated), then the result, the stars, the best kept, and the day back
2. over the network, as the windows and the page are told: a learner's "experience" messages, SKIP to the end,
   START AGAIN; the teacher's "experience_class", END and START; the learner told it has ended
3. on your own: Craft Lab's window with --experience 1 starts its own server on this laptop, logs in and draws the
   experience over the island (a picture: experience_1.png here), and the server stops by itself after the window
   has gone
Test data goes to a temporary folder, never this computer's own profiles or worlds. Exit code 0 = all fine.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
PY = sys.executable
TMP = tempfile.mkdtemp(prefix="experience_test_")
os.environ["CRAFTLAB_DATA"] = TMP
os.environ["APPDATA"] = TMP  # (on your own, the server's data goes in APPDATA\ClubCoders\experiences)
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note else ""), flush=True)


class FakeWs:
    """A learner's connection, for the server in this process (nothing is sent anywhere)."""


def test_island():
    """A small island the test knows: stone, turf on top (a rift opens in turf), the start in the middle. Saved
    where the server looks first, so the server in this process plays on it."""
    import craft_blocks as B
    import craft_world as W
    w = W.World("small", 1, blank=True)
    w.blocks[:, :, :9] = B.ID["stone"]
    w.blocks[:, :, 9] = B.ID["turf"]
    w.blocks[:, :, 0] = B.ID["lab_floor"]
    w.spawn = (64.5, 64.5, 10.0)
    w.light_all()
    w.save(os.path.join(TMP, "world"))


def in_process():
    test_island()
    import craft_blocks as B
    import craft_items as items
    import craft_server
    import craft_sim as sim
    from engine import experience
    I, ID = B.ITEM_ID, B.ID
    srv = craft_server.CraftServer()
    t = srv.teaching
    g, w = srv.game, srv.game.world
    check("the test island is the server's", w.size_key == "small" and w.get(64, 64, 9) == ID["turf"])
    check("the experience starts (on your own)", t.start_experience(1, solo=True))
    p = craft_server.Player(FakeWs(), "learner", "Tester", (60, 130, 230))
    srv.players[p.ws] = p
    srv.rebuild()
    q = p.unit
    check("played in the day, held, with no creatures", srv.lesson["time"] == "day" and not g.rules["mobs"]
          and not g.rules["time_runs"] and g.phase() == "day", f"{srv.lesson['time']} {g.rules['mobs']}")
    steps = [0]

    def step(n=1, inp=(0.0, 0.0, 0), real=False):
        for _ in range(n):
            g.step({q.pid: inp})
            steps[0] += 1
            if steps[0] % 30 == 0:
                t.tick(g.tick * sim.STEP)
                g.events.clear()
                w.take_changes()
            if real:  # (a Bot's brain answers from its own process, in real time)
                time.sleep(1 / 120)

    def obj():
        run = t.xrun(t.record(p.name))
        o = t.x_objective(run)
        return o["id"] if o else None

    def until(oid_gone, seconds, inp=(0.0, 0.0, 0), real=False, each=None):
        end = steps[0] + int(seconds / sim.STEP)
        while obj() == oid_gone and steps[0] < end:
            if each:
                each()
            step(1, inp, real)
        return obj() != oid_gone

    def at():
        s = q.state
        return int(s["x"] // 1), int(s["y"] // 1), int(round(s["z"]))

    def hold(key):
        """The thing to hand: into the Toolbelt (slot 8 if it was in the Backpack) and chosen, as 1 to 8 do."""
        i = next(k for k, sl in enumerate(q.inv) if sl and sl[0] == I[key])
        if i >= items.TOOLBELT:
            q.inv[7], q.inv[i] = q.inv[i], q.inv[7]
            i = 7
        g.action(q.pid, {"type": "select", "slot": i})

    step(31)
    msg = t.experience_msg(p)
    check("the learner is told: on, objective 1, the coach's first words", msg["on"] and msg["index"] == 0
          and msg["objective"] == "Boot up" and "CC-01 here" in msg["say"][1], msg["hint"])
    check("on your own, a run starts with the game's own starter kit (3 apples, 5 Rubble)",
          [tuple(s[:2]) if s else None for s in q.inv[:2]] == [(I["apple"], 3), (I["rubble"], 5)], json.dumps(q.inv[:3]))
    check("1 walk: 5 metres", until("walk", 10, (1.0, 0.0, 0)), f"{obj()}")
    step(60)  # (standing still)
    x, y, z = at()
    hold("rubble")
    g.action(q.pid, {"type": "place", "x": x + 2, "y": y, "z": z, "face": [0, 0, 1]})
    g.action(q.pid, {"type": "place", "x": x + 3, "y": y, "z": z + 1, "face": [0, 0, 1]})
    check("2 place: two blocks put down", until("place", 3) and w.get(x + 2, y, z) == ID["rubble"], f"{obj()}")
    step(31)  # (each objective starts on the tick after the last one: measured from there)
    for want in (z + 1, z + 2):  # (forward and jumping until up on the next block, then standing there a moment)
        end = steps[0] + 300
        while steps[0] < end and not (q.state["z"] >= want - 0.01 and q.state["flags"] & sim.F_GROUND):
            step(1, (1.0, 0.0, sim.JUMP_B))
        step(60)
    check("3 climb: up two blocks (Space)", until("climb", 3), f"{obj()} z {q.state['z']:.1f}")
    q.state.update(x=64.5, y=64.5, z=10.0, vx=0.0, vy=0.0, vz=0.0)  # (back down by the start)
    g.place_safely(q)
    step(30)
    x, y, z = at()
    for k in (0, 1):  # (a trunk two logs high beside you)
        w.set(x + 1, y, z + k, ID["log"])
    for k in (1, 0):
        secs, _ = B.dig_time(ID["log"], None)
        g.action(q.pid, {"type": "dig_start", "x": x + 1, "y": y, "z": z + k})
        step(int(secs / sim.STEP) + 2)
        g.action(q.pid, {"type": "dig", "x": x + 1, "y": y, "z": z + k})
    step(30, (1.0, 0.0, 0))  # (over what dropped)
    step(30)
    logs = sum(s[1] for s in q.inv if s and s[0] == I["log"])
    check("4 chop: two logs, by hand, picked up", until("chop", 3) and logs == 2, f"{obj()} logs {logs}")
    step(31)
    bps = items.blueprints()

    def build(makes, secs):
        g.action(q.pid, {"type": "build", "bp": next(i for i, bp in enumerate(bps) if bp["makes"] == makes)})
        step(int(secs / sim.STEP) + 5)
    build("boards", 1)
    build("boards", 1)
    build("fabricator", 3)
    step(31)
    run = t.xrun(t.record(p.name))
    check("5 fabricator: two of its three steps (Boards, a Fabricator built)", obj() == "fabricator"
          and run["value"] == 2, f"{obj()} {run['value']}")
    x, y, z = at()
    hold("fabricator")
    g.action(q.pid, {"type": "place", "x": x + 2, "y": y + 1, "z": z, "face": [0, 0, 1]})
    check("5 fabricator: put down, all three", until("fabricator", 3) and w.get(x + 2, y + 1, z) == ID["fabricator"],
          f"{obj()}")
    # 6 the garage, as the window's BUILD MY BOT sends it (craft_server's design message: on_design)
    old = p.design
    new = json.loads(json.dumps(old))
    new["name"] = "Zappy"
    p.design = new
    t.on_design(p, new, [], True, old=old, by_code=False)
    step(31)
    check("6 garage: a string alone isn't enough", obj() == "garage", f"{obj()}")
    old, new = new, json.loads(json.dumps(new))
    new["points"].update(dig=44, build=23)
    new["colour"] = [60, 190, 90]
    check("6 the design is one the server builds", not srv.teaching.g.sim.check_design(new, srv.limits_for(p)))
    p.design = new
    t.on_design(p, new, [], True, old=old, by_code=False)
    step(31)
    check("6 garage: a string, an integer and a list, rebuilt", obj() == "code", f"{obj()}")
    old, new = new, json.loads(json.dumps(new))
    new["points"]["speed"] = 30
    p.design = new
    t.on_design(p, new, [], True, old=old, by_code=True)
    step(31)
    check("7 code: a value changed in the code and rebuilt", obj() == "brain", f"{obj()}")
    step(31)
    check("8 the Bot kit (the teacher's K) is given: a BOT DOCK", any(s and s[0] == I["dock"] for s in q.inv))
    x, y, z = at()
    hold("dock")
    q.look = (0.0, 0.0)  # (facing east: the Bot comes out facing the way you look)
    g.action(q.pid, {"type": "place", "x": x + 2, "y": y, "z": z, "face": [0, 0, 1]})
    g.action(q.pid, {"type": "right", "x": x + 2, "y": y, "z": z, "face": [0, 0, 1]})
    bot = g.bot_of(q.pid)
    for k in range(3, 9):  # (a hill in front of it)
        w.set(x + k, y, z + 1, ID["soil"])
    with open(os.path.join(HERE, "brains", "my_bot.py"), encoding="utf-8") as f:
        reply = t.upload_brain(p, f.read())
    r = t.record(p.name)
    r.autopilot = True  # (P, as craft_server's "autopilot" message does it)
    r.brain.error, r.brain.started, r.brain.memory = None, None, {}
    t.attach(p)
    check("8 the dock is down, its Bot out, the brain uploaded", bot is not None and reply.get("ok"), reply.get("error"))
    try:
        check("8 brain: the Bot digs 3 blocks on autopilot", until("brain", 30, real=True),
              f"{obj()} dug {bot.stats['dug'] if bot else '-'}")
    finally:
        r.autopilot = False
        t.attach(p)
    # 9 the Glitch hunt: on your own the dusk comes, with creatures, and the game's rifts open
    step(31)
    check("9 on your own, the dusk is brought with creatures on", srv.lesson["time"] == "dusk"
          and g.rules["mobs"] and g.phase() == "dusk", f"{srv.lesson['time']} {g.phase()}")
    step(60)
    check("9 the game's Glitch rifts open", 1 <= len(g.rifts) <= 3, f"{len(g.rifts)} rifts")
    end = steps[0] + int(15 / sim.STEP)
    while steps[0] < end and not any(m["kind"] == "glitch" for m in g.mobs.mobs.values()):
        step(1)
    glitches = [mid for mid, m in g.mobs.mobs.items() if m["kind"] == "glitch"]
    check("9 a Glitch comes out of a rift", glitches, f"{len(g.mobs.mobs)} creatures")

    def strike():  # (the learner by the Glitch, hitting it with the left button, as the window sends it)
        m = g.mobs.mobs.get(glitches[0]) if glitches else None
        if m is None or steps[0] % 20:
            return
        q.state.update(x=m["s"]["x"] - 1.5, y=m["s"]["y"], z=m["s"]["z"], vx=0.0, vy=0.0, vz=0.0)
        g.action(q.pid, {"type": "attack", "target": glitches[0]})
    check("9 glitch: a Glitch defeated", until("glitch", 30, each=strike), f"{obj()} {q.stats['killed']}")
    step(31)
    msg = t.experience_msg(p)
    res = msg["result"] or {}
    check("the end: the result (XP with the bonus, the top rank, three stars, every objective)",
          res.get("xp") == 275 and res.get("rank") == "Club Coder" and res.get("stars") == 3
          and len(res.get("done", [])) == 9, json.dumps(res))
    step(240)
    check("after the hunt, the day again: the rifts sealed, the Glitches gone, no creatures",
          srv.lesson["time"] == "day" and not srv.lesson["hazards"]["mobs"] and not g.rules["mobs"] and not g.rifts
          and not any(m["kind"] == "glitch" for m in g.mobs.mobs.values()), f"{srv.lesson['time']} {len(g.rifts)}")
    check("the best result is kept for the profile", (t.record(p.name).xbest or {}).get("1", {}).get("finished") == 1)
    check("the Mission tab lists the nine objectives, done", all(m["done"] for m in t.missions_msg(p)["missions"])
          and t.missions_msg(p)["title"] == "Experience 1: Orientation" and len(t.missions_msg(p)["missions"]) == 9)
    report = t.session_report("2000-01-01", [p.name])
    check("the desk's session report says who finished", report["experiences"].get("Tester", [{}])[0].get("n") == 1)
    path = t.export()
    with open(path, encoding="utf-8") as f:
        check("the evidence CSV has the experience", "Experience 1" in f.read())
    cls = t.experience_class_msg()
    check("the teacher's view: finished, with the stars", cls["learners"][0]["finished"]
          and cls["learners"][0]["stars"] == res.get("stars"), json.dumps(cls["learners"]))
    q.inv[0] = None
    t.experience_message(p, {"type": "experience", "do": "again"})
    step(31)
    check("START AGAIN: a new run from objective 1, with the starter kit again", obj() == "walk"
          and t.experience_msg(p)["xp"] == 0 and q.inv[0] and q.inv[0][0] == I["apple"])
    d = t.experience_def()
    check("the ranks, and 250 XP to earn (with a 25 XP bonus)", experience.rank_of(0, d) == "Rookie"
          and experience.rank_of(experience.max_xp(d), d) == "Club Coder" and experience.max_xp(d) == 250
          and not experience.check_definition(d))
    t.stop_experience()
    check("the experience ended: the lesson as it was (the cycle, the Mission tab the lesson's)",
          srv.lesson["time"] == "cycle" and srv.lesson["experience"] == 0
          and t.missions_msg(p)["title"] != "Experience 1: Orientation", srv.lesson["time"])
    for b in g.bot_brains.values():
        if b is not None:
            b.close()
    if r.brain is not None:
        r.brain.close()


def over_the_network():
    from websockets.sync.client import connect
    import craft_version
    from engine import experience
    info = experience.solo_start(HERE, "craft_server.py", "craftlab", 1, "CRAFTLAB_DATA")
    try:
        check("on your own: the server on this laptop starts", experience.solo_ready(info), experience.solo_last_words(info))

        def hello(**fields):
            ws = connect(info["host"], open_timeout=10, max_size=None, compression=None)
            ws.send(json.dumps({"type": "hello", "version": craft_version.VERSION} | fields))
            while wait_json(ws, 30)["type"] != "welcome":
                pass
            return ws

        def wait_json(ws, seconds):
            end = time.time() + seconds
            while True:
                raw = ws.recv(timeout=max(0.1, end - time.time()))
                if not isinstance(raw, bytes):  # (snapshots and the world's parts are binary)
                    return json.loads(raw)

        def wait_for(ws, test, seconds=10):
            end = time.time() + seconds
            while time.time() < end:
                try:
                    m = wait_json(ws, max(0.1, end - time.time()))
                except TimeoutError:
                    return None
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
        check("...with the island kept for next time", os.path.exists(os.path.join(info["data"], "world", "world.json")))
    finally:
        experience.solo_stop(info)


def the_window():
    shot = os.path.join(TMP, "experience_window.png")
    started = time.time()
    proc = subprocess.run([PY, "craft_client.py", "--experience", "1", "--offscreen", "--screenshot", shot,
                           "--after", "9", "--gfx", "low", "--no-sound"], cwd=HERE, capture_output=True, text=True,
                          timeout=240)
    check("the window: Craft Lab with --experience 1, its own server, logged in and drawn", os.path.exists(shot),
          (proc.stdout + proc.stderr)[-300:])
    if os.path.exists(shot):
        keep = os.path.join(HERE, "experience_1.png")
        shutil.copy(shot, keep)
        print(f"  picture: {keep}  ({time.time() - started:.0f} s)")
    log = os.path.join(TMP, "ClubCoders", "experiences", "craftlab", "server.log")
    end, text = time.time() + 90, ""
    while time.time() < end and "the window has gone" not in text:
        time.sleep(2)
        with open(log, encoding="utf-8", errors="replace") as f:
            text = f.read()
    check("...and its server stopped by itself after the window had gone", "the window has gone" in text, text[-200:])


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
