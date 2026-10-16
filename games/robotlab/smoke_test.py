"""Quick check that the whole game still works (run after every AI change to the game's code).

    python smoke_test.py

1. every Python file compiles
2. the mods load and a test fight runs
3. the class server runs a Lesson 5 arena (every hazard and Resident Robot) for 10 seconds
4. four computer robots in the arenas the teacher chose, kept over a restart (CHANGE 140), and who is where (142)
5. pushing follows the robots' stats: one-on-one, two-on-one and two on a Resident Robot
6. the showcase (robot_wars.py) draws a frame
7. a real server with a learner window and a teacher window, logged in and drawing
8. a learner's window draws at mesh, lines and ultra (CHANGE 145: Robot Lab draws all seven tiers)
Test data goes to a temporary folder, never to the real profiles or evidence. Exit code 0 = all fine.
"""
import os
import py_compile
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="robotlab_smoke_")
os.environ["ROBOTLAB_DATA"] = TMP
os.chdir(HERE)
sys.path.insert(0, HERE)
PY = sys.executable
SKIP = {".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles"}
results = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, f"{time.time() - t0:.0f} s"))
    except Exception as e:  # report and carry on, so every problem is listed
        results.append((name, False, str(e)[-400:]))


def compile_all():
    bad = []
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            if f.endswith(".py"):
                try:
                    py_compile.compile(os.path.join(root, f), doraise=True)
                except py_compile.PyCompileError as e:
                    bad.append(str(e))
    if bad:
        raise RuntimeError("\n".join(bad))


def mods():
    import rw_mods
    rw_mods.load_all()
    rw_mods.test_fight(10)


def server_physics():
    import json
    import lab_server
    srv = lab_server.LabServer()
    srv.teaching.apply_lesson(5)
    srv.rebuild_arena()
    for _ in range(600):
        srv.arena.step()
    json.dumps(srv.state())
    srv.arena.set_hazards({"saws": False, "house_robots": ["BLAZE"]})
    for _ in range(60):
        srv.arena.step()


def computer_robots():
    """CHANGE 140: four computer robots, each set up by the teacher and in its own arena (or every arena), are
    where they should be, and still are after the server starts again; an older computer_robot.json (the first
    one alone) still loads as computer robot 1."""
    import asyncio
    import json
    import lab_server

    class Window:  # (the teacher's, as the server sees it: what it is sent)
        def __init__(self):
            self.sent = []

        async def send(self, text):
            self.sent.append(json.loads(text))

    def where(srv):  # arena index -> the names of the computer's robots in it
        return {a.index: sorted(r.name for r in a.robots if r.owner == "Computer") for a in srv.arena}
    try:
        srv = lab_server.LabServer()
        srv.lesson.update(cpu_robots=4, arenas=2)
        srv.rebuild_arena()
        every = ["Sparky 1", "Sparky 2", "Sparky 3", "Sparky 4"]
        if where(srv) != {0: every, 1: every}:
            raise RuntimeError(f"every computer robot should start in every arena: {where(srv)}")
        ws = Window()
        srv.players[ws] = lab_server.Player(ws, "teacher", "Smoke", (180, 90, 230))
        d = dict(srv.cpus[2].design, name="Crusher")
        for m in ({"n": 2, "arena": 0}, {"n": 3, "design": d}, {"n": 3, "arena": 1}, {"n": 4, "arena": 5}):
            asyncio.run(srv.cpu_robot_command({"type": "cpu_robot", **m}))
        want = {0: ["Sparky 1", "Sparky 2"], 1: ["Crusher", "Sparky 1", "Sparky 4"]}  # (arena 6 of 2: the last one)
        if where(srv) != want:
            raise RuntimeError(f"the computer robots should be {want}: {where(srv)}")
        listed = [c for c in [m for m in ws.sent if m["type"] == "lesson"][-1]["class"] if c["role"] == "computer"]
        if [(c["n"], c["design"]["name"], c["arena"], c["in"]) for c in listed] != [
                (1, "Sparky 1", None, None), (2, "Sparky 2", 0, 0), (3, "Crusher", 1, 1), (4, "Sparky 4", 5, 1)]:
            raise RuntimeError(f"the class list's computer robots: {listed}")
        srv.players.clear()
        places = {"Teacher": 1, "amy": 0}  # (CHANGE 142: who is where is saved too; amy isn't here: nothing happens)
        srv.lesson["places"] = dict(places)
        srv.save_mission_settings()  # (Save settings: 4 computer robots, 2 arenas, the places for mission 1)
        again = lab_server.LabServer()  # the server starts again
        if where(again) != want or again.cpus[2].design["name"] != "Crusher":
            raise RuntimeError(f"after a restart the computer robots should be {want}: {where(again)}")
        away = [a.index for a in again.arena for r in a.robots if r.owner == "Teacher (away)"]
        if again.lesson["places"] != places or away != [1]:
            raise RuntimeError(f"after a restart the places should be {places}: {again.lesson['places']}, "
                               f"the teacher's robot in arena 2: {away}")
        os.remove(lab_server.MISSIONS_FILE)  # (no saved mission: the arenas still come from computer_robot.json)
        if lab_server.LabServer().lesson["cpu_arenas"] != [None, 0, 1, 5]:
            raise RuntimeError("computer_robot.json didn't keep the computer robots' arenas")
        old = dict(srv.cpus[0].design, name="Oldie")
        with open(lab_server.CPU_FILE, "w", encoding="utf-8") as f:
            json.dump({"design": old, "brain": ""}, f)  # (the file as it was before CHANGE 140)
        older = lab_server.LabServer()
        if [c.design["name"] for c in older.cpus] != ["Oldie", "Sparky 2", "Sparky 3", "Sparky 4"] \
                or older.lesson["cpu_arenas"] != [None] * 4:
            raise RuntimeError("an older computer_robot.json should load as computer robot 1")
    finally:
        for path in (lab_server.MISSIONS_FILE, lab_server.CPU_FILE):
            if os.path.exists(path):
                os.remove(path)


def pushing():
    """A robot is pushed along when the pushes on it beat its hold (lab_sim.PUSH_GRIP), and pushes add up."""
    import lab_sim as sim
    from panda3d.core import Point3

    def design(name, points, **settings):
        d = sim.default_design(name, (200, 60, 50), "hammer")
        d["points"] = dict(zip(sim.STATS, points))
        d["settings"].update(settings)
        return d

    def moved(pushers, target, side=True):
        """How far the pushers (side by side, driving north for 4 seconds) move the target parked in front."""
        arena = sim.Arena(hazards={"pit": False, "floor_flipper": False, "saws": False, "spikes": False,
                                   "house_robots": []})
        arena.practice = True
        robots = []
        for i, d in enumerate(pushers + [target]):
            last, house = i == len(pushers), d is None
            pos = Point3(0, 1.2 if house else 0.3, 0.6) if last else Point3((i - (len(pushers) - 1) / 2) * 1.7,
                                                                           -1.6 if target is None else -2.1, 0.5)
            if house:
                r = sim.Robot(arena, i, sim.house_design("CRUSHER", "hammer", (70, 72, 82)), pos, 0, None,
                              "Resident Robot", stats=sim.HOUSE_STATS, house=True)
                r.corner = (1, 1)
            else:
                r = sim.Robot(arena, i, d, pos, 90 if last and side else 0, None, d["name"])
            r.start_index = None if house else i
            arena.robots.append(r)
            arena.owner.update({n: r for n in r.parts})
            robots.append(r)
        for _ in range(90):
            arena.step()
        start = robots[-1].pos.y
        for _ in range(240):
            for r in robots[:-1]:
                r.drive(1.0, 0.0, False)
            arena.step()
        return robots[-1].pos.y - start

    standard = design("Standard", (25, 25, 25, 25))
    tank = design("Tank", (45, 5, 45, 5), size=120, acceleration=100)       # heavy, with a strong motor
    feather = design("Feather", (5, 45, 5, 45), size=80, acceleration=30)   # light, with a weak motor
    for text, far, pushers, target in (("a standard robot should push a standard robot", True, [standard], standard),
                                       ("a feather shouldn't push a standard robot", False, [feather], standard),
                                       ("two standard robots should push a tank", True, [standard, standard], tank),
                                       ("one tank shouldn't push a Resident Robot", False, [tank], None),
                                       ("two tanks should push a Resident Robot", True, [tank, tank], None)):
        metres = moved(pushers, target)
        if (metres > 1.0) != far:
            raise RuntimeError(f"{text}: it moved {metres:.2f} m")


def run(cmd, timeout=120):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout,
                       env=dict(os.environ, ROBOTLAB_DATA=TMP))
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-600:])


def showcase():
    shot = os.path.join(TMP, "showcase.png")
    run([PY, "robot_wars.py", "--offscreen", "--skip-intro", "--autoplay", "--no-sound", "--after", "4",
         "--screenshot", shot])
    if not os.path.exists(shot):
        raise RuntimeError("the showcase didn't draw a frame")


def windows():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([PY, "lab_server.py", "--port", str(port)], cwd=HERE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, env=dict(os.environ, ROBOTLAB_DATA=TMP))
    try:
        time.sleep(4)
        if server.poll() is not None:
            raise RuntimeError("the server stopped: " + server.stderr.read().decode()[-400:])
        host = f"ws://127.0.0.1:{port}"
        for who, extra in (("learner", ["--name", "smoketest", "--password", "smoke123"]),
                           ("teacher", ["--name", "Smoke", "--teacher"])):
            shot = os.path.join(TMP, f"{who}.png")
            run([PY, "lab_client.py", "--host", host, "--offscreen", "--after", "6", "--screenshot", shot] + extra)
            if not os.path.exists(shot):
                raise RuntimeError(f"the {who} window didn't draw")
    finally:
        server.kill()


def tiers():
    """A learner's window at mesh, lines and ultra: it logs in and draws, in the tier asked for (CHANGE 145)."""
    import numpy as np
    from PIL import Image
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([PY, "lab_server.py", "--port", str(port)], cwd=HERE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, env=dict(os.environ, ROBOTLAB_DATA=TMP))
    try:
        time.sleep(4)
        if server.poll() is not None:
            raise RuntimeError("the server stopped: " + server.stderr.read().decode()[-400:])
        for tier in ("mesh", "lines", "ultra"):
            shot = os.path.join(TMP, f"learner_{tier}.png")
            run([PY, "lab_client.py", "--host", f"ws://127.0.0.1:{port}", "--offscreen", "--after", "6", "--screenshot", shot,
                 "--gfx", tier, "--name", "smoketest", "--password", "smoke123"], timeout=180)
            if not os.path.exists(shot):
                raise RuntimeError(f"the {tier} window didn't draw")
            px = np.asarray(Image.open(shot).convert("RGB")).astype(int)
            green = ((px[..., 1] > 120) & (px[..., 1] > px[..., 0] + 50)).mean()  # (the lines: phosphor green)
            if tier != "ultra" and green < 0.01:
                raise RuntimeError(f"no lines in the {tier} window ({green:.4f} of it green)")
    finally:
        server.kill()


if __name__ == "__main__":
    check("Every file compiles", compile_all)
    check("Mods load and a test fight runs", mods)
    check("Server runs a full arena", server_physics)
    check("Four computer robots in their arenas and who is where, kept over a restart", computer_robots)
    check("Pushing follows the stats", pushing)
    check("Showcase draws", showcase)
    check("Learner and teacher windows log in and draw", windows)
    check("A learner's window draws at mesh, lines and ultra", tiers)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note.replace("\n", "\n    ")))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
