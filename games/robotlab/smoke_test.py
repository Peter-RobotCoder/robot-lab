"""Quick check that the whole game still works (run after every AI change to the game's code).

    python smoke_test.py

1. every Python file compiles
2. the mods load and a test fight runs
3. the class server runs a Lesson 5 arena (every hazard and house robot) for 10 seconds
4. the showcase (robot_wars.py) draws a frame
5. a real server with a learner window and a teacher window, logged in and drawing
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


if __name__ == "__main__":
    check("Every file compiles", compile_all)
    check("Mods load and a test fight runs", mods)
    check("Server runs a full arena", server_physics)
    check("Showcase draws", showcase)
    check("Learner and teacher windows log in and draw", windows)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note.replace("\n", "\n    ")))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
