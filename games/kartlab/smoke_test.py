"""Quick check that the whole game still works (run after every AI change to the game's code).

    python smoke_test.py

1. every Python file compiles
2. the mods load and a test race runs
3. the class server runs a Lesson 5 race (computer karts, the gates, places) for 10 seconds, then a tournament
4. a learner's brain loads in its sandbox and drives
5. the offline race (kart_client.py --offline) draws a frame
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
TMP = tempfile.mkdtemp(prefix="kartlab_smoke_")
os.environ["KARTLAB_DATA"] = TMP
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
    import kart_mods
    kart_mods.load_all()
    kart_mods.test_race(10)


def server_physics():
    import json
    import kart_server
    import kart_sim as sim
    srv = kart_server.KartServer()
    srv.teaching.apply_lesson(5)
    srv.lesson["cpu_karts"] = 3
    srv.lesson["cpu_level"] = "expert"
    srv.rebuild()
    srv.race.start()
    for _ in range(600):
        srv.step()
    json.dumps(srv.roster())
    json.dumps(srv.race_msg())
    if srv.race.phase != sim.FLAGS_RACE:
        raise RuntimeError(f"10 seconds after the start the race is still in phase {srv.race.phase}")
    moved = [k for k in srv.race.karts.values() if k["cp"] > 0 or k["lap"] > 0]
    if not moved:
        raise RuntimeError("10 seconds of racing and no kart passed a gate")
    places = srv.race.places()
    if len(places) != len(srv.race.karts):
        raise RuntimeError(f"places() lists {len(places)} karts of {len(srv.race.karts)}")
    srv.tournament = kart_server.Tournament(["Ann", "Ben", "Cat"], shuffle=False)
    srv.rebuild()
    for _ in range(120):
        srv.step()
    json.dumps(srv.roster())
    json.dumps(srv.race_msg())
    if not getattr(srv.tournament, "label", lambda: "")():
        raise RuntimeError("the tournament has no round to show")


def brain_sandbox():
    import kart_brain
    import kart_sim as sim
    import kart_track
    import kart_version
    sys.path.insert(0, kart_version.ENGINE_HOME)
    from engine import wire
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        brain, fname = kart_brain.load_brain(f.read(), "smoke")
    try:
        auto = kart_brain.Autopilot(brain, fname)
        race = sim.Race(kart_track.load("club"), wire.Schema("kart", sim.SCHEMA_FIELDS))
        race.add(0, sim.default_design("Brain"))
        race.add(1, sim.default_design("Dummy"))
        race.start()
        for _ in range(60 * 8):
            out = auto(race.karts[0], race)
            race.step_all({0: out, 1: (0.0, 0.0, 0)})
            # the brain is asked asynchronously and answers a tick late at 60 Hz; stepped as fast as the computer
            # can, wait for its answer (a few ms at most) so it drives the race it sees, as brain_test's paced() does
            deadline = time.perf_counter() + 0.05
            while brain.pending is not None and brain.replies.empty() and time.perf_counter() < deadline:
                time.sleep(0.0005)
        if auto.error:
            raise RuntimeError(auto.error)
        if auto.ticks < 50:
            raise RuntimeError(f"the brain only ran {auto.ticks} times")
        if race.karts[0]["cp"] == 0 and race.karts[0]["lap"] == 0:
            raise RuntimeError("8 seconds of the starter brain and the kart passed no gate")
    finally:
        brain.close()


def run(cmd, timeout=150):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout,
                       env=dict(os.environ, KARTLAB_DATA=TMP))
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-600:])


def offline_race():
    shot = os.path.join(TMP, "offline.png")
    run([PY, "kart_client.py", "--offline", "--offscreen", "--autostart", "--mute", "--cpu", "3", "--after", "5",
         "--screenshot", shot])
    if not os.path.exists(shot):
        raise RuntimeError("the offline race didn't draw a frame")


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
    server = subprocess.Popen([PY, "kart_server.py", "--port", str(port)], cwd=HERE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, env=dict(os.environ, KARTLAB_DATA=TMP))
    try:
        time.sleep(4)
        if server.poll() is not None:
            raise RuntimeError("the server stopped: " + server.stderr.read().decode()[-400:])
        host = f"ws://127.0.0.1:{port}"
        for who, extra in (("learner", ["--name", "smoketest", "--password", "smoke123"]),
                           ("teacher", ["--name", "Smoke", "--teacher", "--code", "TEACH99"])):  # (the test
            # server's demo code, not a real one saved in teacher_settings.json)
            shot = os.path.join(TMP, f"{who}.png")
            run([PY, "kart_client.py", "--host", host, "--offscreen", "--mute", "--after", "6", "--screenshot", shot]
                + extra)
            if not os.path.exists(shot):
                raise RuntimeError(f"the {who} window didn't draw")
    finally:
        stop(server)


if __name__ == "__main__":
    check("Every file compiles", compile_all)
    check("Mods load and a test race runs", mods)
    check("Server runs a race, computer karts and a tournament", server_physics)
    check("A learner's brain runs in its sandbox", brain_sandbox)
    check("Offline race draws", offline_race)
    check("Learner and teacher windows log in and draw", windows)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note.replace("\n", "\n    ")))
    print("Screenshots and test data:", TMP)
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
