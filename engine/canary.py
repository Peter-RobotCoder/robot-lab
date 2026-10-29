"""Try a game server's code before a class runs it (CHANGE 168).

    python canary.py SERVER_SCRIPT [--seconds 20]       (run in the game's folder, as run-class.sh does)

A live update (a teacher's AI change made live) used to be started by the class server's next restart, whatever it
did: one that failed at start-up left the class with no server (systemd starting it again every 2 seconds), and one
that failed in its loop or sent nothing took the class down with it. run-class.sh now tries the update first: this
starts its server on a free port of this computer only, with a data folder of its own (nothing of the class's), as a
laptop test server with a teacher code of its own; logs in as the teacher; and wants 30 snapshots within the time,
the server still running, and no error ("Traceback") in what it printed. Exit code 0 = it ran; anything else (and
the reason, printed) = run-class.sh runs the release's own code instead. Google's canary rule at a class's size:
try the new code on something nobody depends on, judged on the things that matter, and go back by itself.
"""
import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from websockets.sync.client import connect

# (what the class's own server has that the try mustn't: its codes, the desk, the live update's pointer)
DROP = ("JOIN_CODE", "TEACHER_CODE", "PORT", "NOTIFY_SOCKET", "WATCHDOG_USEC", "WATCHDOG_PID")
DATA_VARS = ("ROBOTLAB_DATA", "FIGHTLAB_DATA", "KARTLAB_DATA", "CITYLAB_DATA")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def version_here():
    """The game's VERSION, from its version module (lab_version, fight_version, kart_version or city_version) in
    this folder."""
    for name in ("lab_version", "fight_version", "kart_version", "city_version"):
        if os.path.exists(f"{name}.py"):
            sys.path.insert(0, os.getcwd())
            try:
                return __import__(name).VERSION
            finally:
                sys.path.pop(0)
    return None


def stop(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    proc.wait(timeout=10)


def check(script, seconds=20.0):
    """(ok, why)."""
    work = tempfile.mkdtemp(prefix="canary_")
    port, code = free_port(), "canary-" + secrets.token_hex(12)
    env = {k: v for k, v in os.environ.items() if k not in DROP and not k.startswith("CLUBCODERS_")}
    env.update({v: os.path.join(work, "data") for v in DATA_VARS})
    env["TEACHER_CODE"], env["JOIN_CODE"] = code, "canary-" + secrets.token_hex(8)
    log = os.path.join(work, "log")
    proc = subprocess.Popen([sys.executable, script, "--port", str(port), "--bind", "127.0.0.1"], env=env,
                            stdout=open(log, "w"), stderr=subprocess.STDOUT)
    snapshots = 0
    try:
        if not wait_port(port, seconds):
            return False, "its server didn't start" + (" (it stopped)" if proc.poll() is not None else "")
        ws = connect(f"ws://127.0.0.1:{port}", open_timeout=10, max_size=None)
        ws.send(json.dumps({"type": "hello", "name": "Teacher", "code": code, "version": version_here()}))
        end = time.time() + seconds
        welcomed = False
        while time.time() < end and snapshots < 30:
            try:
                m = ws.recv(timeout=max(0.1, end - time.time()))
            except TimeoutError:
                break
            if isinstance(m, bytes):
                snapshots += welcomed
            else:
                kind = json.loads(m).get("type")
                welcomed |= kind == "welcome"
                snapshots += welcomed and kind == "state"
        ws.close()
        if not welcomed:
            return False, "it didn't let the teacher in"
        if snapshots < 30:
            return False, f"it sent {snapshots} snapshots in {seconds:.0f} s"
        if proc.poll() is not None:
            return False, "its server stopped"
        return True, f"{snapshots} snapshots"
    except Exception as e:  # noqa: BLE001  (whatever went wrong: not ready for the class)
        return False, f"{type(e).__name__}: {e}"
    finally:
        stop(proc)
        try:
            with open(log, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            text = ""
        shutil.rmtree(work, ignore_errors=True)
        if "Traceback" in text:
            check.error = text[text.index("Traceback"):][-1500:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--seconds", type=float, default=20.0)
    a = ap.parse_args()
    check.error = None
    ok, why = check(a.script, a.seconds)
    if ok and check.error:
        ok, why = False, "an error in what it printed:\n" + check.error
    print(f"Canary: {os.getcwd()} {'ran' if ok else 'is not ready'}: {why}", flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
