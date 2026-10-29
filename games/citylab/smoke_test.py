"""Quick check that the whole game still works (run after every AI change to the game's code).

    python smoke_test.py

1. every Python file compiles
2. the mods load and the city runs for a while
3. the class server runs a street race (the computer's racers, the checkpoints) for 20 seconds
4. a learner's brain loads in its sandbox and walks
5. the city offline (city_client.py --offline) draws a frame
6. a real server with a learner window and a teacher window, logged in and drawing
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
TMP = tempfile.mkdtemp(prefix="citylab_smoke_")
os.environ["CITYLAB_DATA"] = TMP
os.chdir(HERE)
sys.path.insert(0, HERE)
PY = sys.executable
SKIP = {".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "data"}
results = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, f"{time.time() - t0:.0f} s"))
    except Exception as e:  # report and carry on, so every problem is listed
        results.append((name, False, f"{type(e).__name__}: {str(e)[-400:]}"))


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
    import city_mods
    city_mods.load_all()
    city_mods.test_city(10)


def server_physics():
    import asyncio
    import json
    import city_server
    srv = city_server.CityServer()
    srv.teaching.apply_lesson(5)
    srv.lesson["racers"] = 3
    srv.lesson["cpu_level"] = "expert"
    srv.rebuild()
    asyncio.run(srv.start_race())
    for _ in range(1200):  # (8 s on the grid and the countdown, then 12 s of racing)
        srv.step()
    json.dumps(srv.roster())
    json.dumps(srv.jobs_msg())
    race = srv.world.jobs.race
    if race is None or race["state"] != "racing":
        raise RuntimeError(f"20 seconds after the start the race is {race and race['state']}")
    moved = [cid for cid, cp in race["cars"].items() if cp > 0]
    if not moved:
        raise RuntimeError("12 seconds of racing and no racer passed a checkpoint")
    if len(srv.racers) != 3:
        raise RuntimeError(f"{len(srv.racers)} computer racers of 3")


def brain_sandbox():
    import city_brain
    import city_jobs
    import city_sim as sim
    import city_version
    sys.path.insert(0, city_version.ENGINE_HOME)
    from engine import wire
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        brain, fname = city_brain.load_brain(f.read(), "smoke")
    try:
        auto = city_brain.Autopilot(brain, fname)
        w = sim.World(sim.city_of(), wire.Schema("city", sim.SCHEMA_FIELDS))
        w.jobs = city_jobs.Jobs(w.city, sim.RULES)
        p = w.add_person(0, sim.default_design("Brain"))
        start = (p["x"], p["y"])
        for _ in range(60 * 8):
            out = auto(w.people[0], w)
            w.step_all({0: out})
            # the brain is asked asynchronously and answers a tick late at 60 Hz; stepped as fast as the computer
            # can, wait for its answer (a few ms at most) so it walks the city it sees
            deadline = time.perf_counter() + 0.05
            while brain.pending is not None and brain.replies.empty() and time.perf_counter() < deadline:
                time.sleep(0.0005)
        if auto.error:
            raise RuntimeError(auto.error)
        if auto.ticks < 50:
            raise RuntimeError(f"the brain only ran {auto.ticks} times")
        p = w.people[0]
        if abs(p["x"] - start[0]) + abs(p["y"] - start[1]) < 3.0 and not w.jobs.mine:
            raise RuntimeError("8 seconds of the starter brain and the person hardly moved")
    finally:
        brain.close()


def run(cmd, timeout=150):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout,
                       env=dict(os.environ, CITYLAB_DATA=TMP))
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-600:])


def offline_city():
    shot = os.path.join(TMP, "offline.png")
    run([PY, "city_client.py", "--offline", "--offscreen", "--demo", "--mute", "--after", "5", "--screenshot", shot])
    if not os.path.exists(shot):
        raise RuntimeError("the offline city didn't draw a frame")


def stop(proc):
    """Stop the server and anything it started (a venv's python.exe can be a launcher whose child is the real
    interpreter, and proc.kill() alone leaves that child, and its port, behind)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.kill()


def windows():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([PY, "city_server.py", "--port", str(port)], cwd=HERE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, env=dict(os.environ, CITYLAB_DATA=TMP))
    try:
        time.sleep(4)
        if server.poll() is not None:
            raise RuntimeError("the server stopped: " + server.stderr.read().decode()[-400:])
        host = f"ws://127.0.0.1:{port}"
        for who, extra in (("learner", ["--name", "smoketest", "--password", "smoke123"]),
                           ("teacher", ["--name", "Smoke", "--teacher", "--code", "TEACH99"])):  # (the test
            # server's demo code, not a real one saved in teacher_settings.json)
            shot = os.path.join(TMP, f"{who}.png")
            run([PY, "city_client.py", "--host", host, "--offscreen", "--mute", "--after", "6", "--screenshot", shot]
                + extra)
            if not os.path.exists(shot):
                raise RuntimeError(f"the {who} window didn't draw")
    finally:
        stop(server)


if __name__ == "__main__":
    check("Every file compiles", compile_all)
    check("Mods load and the city runs", mods)
    check("Server runs a street race with computer racers", server_physics)
    check("A learner's brain runs in its sandbox", brain_sandbox)
    check("Offline city draws", offline_city)
    check("Learner and teacher windows log in and draw", windows)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note.replace("\n", "\n    ")))
    print("Screenshots and test data:", TMP)
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
