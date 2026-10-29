"""One window that stops reading mustn't hold up everyone else's game (CHANGE 160).

    python engine/stall_test.py [robot|fight|kart|city|all]

A laptop server for the game; a teacher's connection reading everything; a learner's connection that logs in and
then stops reading (a laptop lid half shut, a weak Wi-Fi corner: its socket's receive buffer is made tiny, so the
server's own buffer for it fills). The teacher's messages must keep coming: the longest gap between two is
measured for 12 s after the stall starts. Before CHANGE 160 Robot Lab and Fight Lab only skipped a stalled
connection over 64 KB, while the websockets library makes a send wait once 32 KB is waiting: everyone waited.
Exit code 0 = all fine.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from websockets.sync.client import connect

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def game_folder(working, public):
    """A game's folder: games/<game> in the public repository, its own folder in the working one."""
    return os.path.join("games", public) if os.path.isdir(os.path.join(ROOT, "games", public)) else working


GAMES = {  # folder, server, data folder's variable, version module
    "robot": (game_folder("shared-world-demo", "robotlab"), "lab_server.py", "ROBOTLAB_DATA", "lab_version"),
    "fight": (game_folder("BeatEmUp", "fightlab"), "fight_server.py", "FIGHTLAB_DATA", "fight_version"),
    "kart": (game_folder("kart", "kartlab"), "kart_server.py", "KARTLAB_DATA", "kart_version"),
    "city": (game_folder("city", "citylab"), "city_server.py", "CITYLAB_DATA", "city_version"),  # (CHANGE 194)
}
WATCH = 12.0
MOST_GAP = 0.5


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def version_of(folder, module):
    sys.path.insert(0, os.path.join(ROOT, folder))
    try:
        return __import__(module).VERSION
    finally:
        sys.path.pop(0)


def hello(port, version, sock=None, **fields):
    ws = connect(f"ws://127.0.0.1:{port}", open_timeout=10, max_size=None, sock=sock, max_queue=1,
                 compression=None if sock is not None else "deflate")
    ws.send(json.dumps({"type": "hello", "version": version} | fields))
    end = time.time() + 15
    while time.time() < end:
        m = ws.recv(timeout=15)
        if isinstance(m, str) and json.loads(m).get("type") == "welcome":
            return ws
    raise RuntimeError("no welcome")


def stop(p):
    if os.name == "nt":  # (the venv's python is a launcher: kill its child too)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
    else:
        p.kill()
    p.wait(timeout=10)


def run(game):
    folder, script, data_var, module = GAMES[game]
    version = version_of(folder, module)
    work = tempfile.mkdtemp(prefix=f"stall_{game}_")
    port = free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("JOIN_CODE", "TEACHER_CODE")}
    env[data_var] = os.path.join(work, "data")
    args = [sys.executable, script, "--port", str(port)] + (["--cpu", "3"] if game == "kart" else
                                                            ["--traffic", "2", "--robots", "1"] if game == "city" else [])
    server = subprocess.Popen(args, cwd=os.path.join(ROOT, folder), env=env, stdout=open(os.path.join(work, "log"), "w"),
                              stderr=subprocess.STDOUT)
    try:
        if not wait_port(port):
            return False, "the server didn't start"
        teacher = hello(port, version, name="Teacher", code="TEACH99")
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
        sock.connect(("127.0.0.1", port))
        slow = hello(port, version, sock=sock, name="Slowpoke", code="CLUB42", password="slowpoke1")
        # (from now on the slow one reads nothing: its one-message queue fills and its thread stops reading)
        gaps, last, end, count = [], time.perf_counter(), time.perf_counter() + WATCH, 0
        while time.perf_counter() < end:
            try:
                teacher.recv(timeout=5)
            except TimeoutError:
                pass
            now = time.perf_counter()
            gaps.append(now - last)
            last, count = now, count + 1
        teacher.close()
        try:
            slow.close()
        except Exception:
            pass
        worst = max(gaps)
        return worst < MOST_GAP, f"{count} messages in {WATCH:.0f} s, the longest gap {worst * 1000:.0f} ms"
    finally:
        stop(server)
        shutil.rmtree(work, ignore_errors=True)


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    games = list(GAMES) if which == "all" else [which]
    ok = True
    for game in games:
        good, note = run(game)
        ok &= good
        print(f"[{'PASS' if good else 'FAIL'}] {game}: a stalled window doesn't hold up the teacher's ({note})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
