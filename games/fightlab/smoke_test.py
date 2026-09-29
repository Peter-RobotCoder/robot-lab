"""Quick check that the whole game still works (run after every AI change to the game's code).

    python smoke_test.py

1. every Python file compiles
2. the mods load and a test fight runs
3. the class server runs a Lesson 5 battle (every hazard, a boss, a match and a tournament) for 10 seconds
4. a learner's brain loads in its sandbox and fights
5. the showcase (beat_em_up.py) draws a frame, with the detailed 3D fighters (Penthesilea v Achilles)
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
TMP = tempfile.mkdtemp(prefix="fightlab_smoke_")
os.environ["FIGHTLAB_DATA"] = TMP
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
    import fight_mods
    fight_mods.load_all()
    fight_mods.test_fight(10)


def server_physics():
    import json
    import fight_server
    srv = fight_server.FightServer()
    srv.teaching.apply_lesson(5)
    srv.lesson["teacher_fighter"] = True
    srv.lesson["cpu_fighter"] = "GOLIATH"
    srv.lesson["hazards"] = {"ring_out": False, "electric_ropes": True, "fire_jets": True, "slippery": True}
    srv.rebuild_stage()
    for _ in range(600):
        srv.stage.step()
    json.dumps(srv.state())
    json.dumps(srv.roster())
    if not any(f.hits for f in srv.stage.fighters()):
        raise RuntimeError("10 seconds of fighting and nobody landed a hit")
    srv.stage.set_hazards({"ring_out": True, "electric_ropes": False})
    srv.tournament = fight_server.Tournament(["Ann", "Ben", "Cat"], shuffle=False)
    srv.rebuild_stage()
    for _ in range(120):
        srv.stage.step()
    json.dumps(srv.state())
    labels = [r.label for r in srv.stage.rings]
    if labels[:2] != ["SEMI-FINAL 1", "SEMI-FINAL 2"] or any(len(r.fighters) != 2 for r in srv.stage.rings):
        raise RuntimeError(f"the tournament should start with 2 semi-finals, not {labels}")


def brain_sandbox():
    import fight_brain
    import fight_sim as sim
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        fn, fname = fight_brain.load_brain(f.read(), "smoke")
    auto = fight_brain.Autopilot(fn, fname)
    try:
        st = sim.Stage(practice=True)
        ring = st.add_ring()
        ring.add_fighter(sim.default_design("Brain"), brain=auto, owner="smoke")
        ring.add_fighter(sim.default_design("Dummy"), brain=None)
        for _ in range(240):
            st.step()
        if auto.error:
            raise RuntimeError(auto.error)
        if auto.ticks < 100:
            raise RuntimeError(f"the brain only ran {auto.ticks} times")
    finally:
        auto.close()


def run(cmd, timeout=150):
    r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout,
                       env=dict(os.environ, FIGHTLAB_DATA=TMP))
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr)[-600:])


def showcase():
    shot = os.path.join(TMP, "showcase.png")
    run([PY, "beat_em_up.py", "--offscreen", "--skip-intro", "--autoplay", "--no-sound", "--after", "4",
         "--you", "penthesilea", "--cpu", "achilles",
         "--screenshot", shot])
    if not os.path.exists(shot):
        raise RuntimeError("the showcase didn't draw a frame")


def windows():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([PY, "fight_server.py", "--port", str(port)], cwd=HERE, stdout=subprocess.DEVNULL,
                              stderr=subprocess.PIPE, env=dict(os.environ, FIGHTLAB_DATA=TMP))
    try:
        time.sleep(4)
        if server.poll() is not None:
            raise RuntimeError("the server stopped: " + server.stderr.read().decode()[-400:])
        host = f"ws://127.0.0.1:{port}"
        for who, extra in (("learner", ["--name", "smoketest", "--password", "smoke123"]),
                           ("teacher", ["--name", "Smoke", "--teacher", "--code", "TEACH99"])):  # (the test
            # server's demo code, not a real one saved in teacher_settings.json)
            shot = os.path.join(TMP, f"{who}.png")
            run([PY, "fight_client.py", "--host", host, "--offscreen", "--after", "6", "--screenshot", shot] + extra)
            if not os.path.exists(shot):
                raise RuntimeError(f"the {who} window didn't draw")
    finally:
        server.kill()


if __name__ == "__main__":
    check("Every file compiles", compile_all)
    check("Mods load and a test fight runs", mods)
    check("Server runs full rings, a boss and a tournament", server_physics)
    check("A learner's brain runs in its sandbox", brain_sandbox)
    check("Showcase draws", showcase)
    check("Learner and teacher windows log in and draw", windows)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note.replace("\n", "\n    ")))
    print("Screenshots and test data:", TMP)
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
