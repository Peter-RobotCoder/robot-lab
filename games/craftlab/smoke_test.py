"""Quick check that the whole game still works (run after every AI change to the game's code).

    python smoke_test.py

1. every Python file compiles
2. the mods load and the world runs for a while (a player walking, the creatures, the slow things)
3. a learner's Craft Bot brain loads in its sandbox and its Bot digs
4. the world offline (craft_client.py --offline) draws a frame
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
TMP = tempfile.mkdtemp(prefix="craftlab_smoke_")
os.environ["CRAFTLAB_DATA"] = TMP
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


def mods_and_world():
    r = subprocess.run([PY, "craft_mods.py"], capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(r.stdout[-600:] + r.stderr[-600:])


def bot_digs():
    import craft_blocks as B
    import craft_brain
    import craft_bot
    import craft_game
    import craft_world
    w = craft_world.World("small", 4)
    g = craft_game.Game(w, {"mobs": False})
    p = g.add_player(0, "Test")
    x, y, z = int(p.state["x"]), int(p.state["y"]), int(p.state["z"])
    w.set(x + 2, y, z, B.ID["dock"])
    g.use_block(0, x + 2, y, z)
    bot = g.bot_of(0)
    for k in range(1, 6):  # (a wall of soil in front of it, to dig through)
        w.set(x + 2 + k, y, z + 1, B.ID["soil"])
    fn, fname = craft_brain.load_brain(craft_bot.STARTER, "Test")
    g.bot_brains[0] = craft_brain.Autopilot(fn, fname)
    try:
        for _ in range(60 * 20):  # (in real time: the brain answers from its own process, a few ms each turn)
            g.step({})
            time.sleep(1 / 60)
            if bot.stats["dug"] >= 5:
                break
    finally:
        g.bot_brains[0].close()
    if bot.stats["dug"] < 5 or g.bot_brains[0].error:
        raise RuntimeError(f"the Bot dug {bot.stats['dug']} (error {g.bot_brains[0].error})")


def offline_window():
    shot = os.path.join(TMP, "offline.png")
    r = subprocess.run([PY, "craft_client.py", "--offline", "--seed", "3", "--size", "small", "--offscreen",
                        "--no-sound", "--after", "2", "--screenshot", shot],
                       capture_output=True, text=True, timeout=240, env=dict(os.environ, APPDATA=TMP))
    if r.returncode != 0 or not os.path.exists(shot):
        raise RuntimeError((r.stdout + r.stderr)[-800:])


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc):
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()


def server_and_windows():
    port = free_port()
    log = open(os.path.join(TMP, "server.log"), "w")
    server = subprocess.Popen([PY, "craft_server.py", "--port", str(port), "--seed", "3", "--size", "small"],
                              stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, CRAFTLAB_DATA=TMP))
    try:
        for _ in range(300):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        host = f"ws://127.0.0.1:{port}"
        windows = []
        for extra in (["--name", "Sam", "--password", "secret12"], ["--teacher", "--name", "Mr P"]):
            shot = os.path.join(TMP, f"{extra[1] if extra[0] != '--teacher' else 'teacher'}.png")
            windows.append((shot, subprocess.Popen([PY, "craft_client.py", "--host", host, "--offscreen", "--no-sound",
                                                    "--demo", "--after", "5", "--screenshot", shot] + extra,
                                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                                   env=dict(os.environ, APPDATA=TMP))))
        for shot, w in windows:
            out, _ = w.communicate(timeout=240)
            if w.returncode != 0 or not os.path.exists(shot):
                raise RuntimeError(out[-800:])
    finally:
        stop(server)
        log.close()


if __name__ == "__main__":
    for name, fn in (("Every Python file compiles", compile_all), ("The mods load and the world runs", mods_and_world),
                     ("A Craft Bot's brain loads and its Bot digs", bot_digs),
                     ("The world offline draws a frame", offline_window),
                     ("A server with a learner's window and a teacher's", server_and_windows)):
        check(name, fn)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + (f" ({note})" if ok else f":\n    {note}"), flush=True)
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
