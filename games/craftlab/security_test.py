"""Checks the Craft Lab class server's safety features (run before each release, next to smoke_test.py).

    python security_test.py

1. the class server won't start without real codes, or with the demo codes
2. wrong class code, old game version and unknown usernames are turned away
3. the teacher makes an account; the learner logs in with it; passwords are stored with scrypt
4. too many wrong passwords are blocked for a minute
5. a Bot brain that tries a gigantic sum only stops itself: the server keeps answering
6. the evidence export reaches the teacher's computer
7. deleting a learner disconnects them and removes their profile
The world itself travels as binary frames on the same connection (its parts, then snapshots): the helpers here
skip those frames.
Test data goes to a temporary folder, never to the real profiles or evidence. Exit code 0 = all fine.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time

from websockets.sync.client import connect

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import craft_version  # noqa: E402

PY = sys.executable
TMP = tempfile.mkdtemp(prefix="craftlab_security_")
LEARNER_CODE, TEACHER_CODE = "craft-2026", "teacher-" + "x" * 20
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    proc.kill()


def start(env_codes, port):
    env = dict(os.environ, CRAFTLAB_DATA=TMP)
    env.pop("JOIN_CODE", None)
    env.pop("TEACHER_CODE", None)
    env.update(env_codes)
    return subprocess.Popen([PY, "craft_server.py", "--class-server", "--port", str(port), "--seed", "5", "--size",
                             "small"], cwd=HERE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def recv_json(ws, timeout):
    """The next JSON message, skipping the world's binary frames."""
    end = time.time() + timeout
    while True:
        raw = ws.recv(timeout=max(0.05, end - time.time()))
        if isinstance(raw, bytes):
            if time.time() >= end:
                raise TimeoutError("only binary frames")
            continue
        return json.loads(raw)


def hello(port, **fields):
    """Connect and say hello. Returns (the connection, the first message) or (None, (close code, reason))."""
    ws = connect(f"ws://127.0.0.1:{port}", open_timeout=5, max_size=None, compression=None)
    ws.send(json.dumps({"type": "hello", "version": craft_version.VERSION} | fields))
    try:
        while True:
            m = recv_json(ws, 10)
            if m["type"] == "welcome":
                return ws, m
    except Exception:
        rcvd = ws.protocol.close_rcvd
        return None, (rcvd.code, rcvd.reason) if rcvd else (None, "")


def wait_for(ws, kind, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        try:
            m = recv_json(ws, max(0.1, end - time.time()))
        except TimeoutError:
            return None
        if m["type"] == kind:
            return m
    return None


def main():
    for label, codes in (("no codes", {}), ("demo codes", {"JOIN_CODE": "CLUB42", "TEACHER_CODE": "TEACH99"})):
        p = start(codes, free_port())
        try:
            p.wait(timeout=30)
            check(f"Class server refuses to start with {label}", p.returncode != 0,
                  p.stderr.read().decode()[-200:])
        except subprocess.TimeoutExpired:
            stop(p)
            check(f"Class server refuses to start with {label}", False, "it started")

    port = free_port()
    server = start({"JOIN_CODE": LEARNER_CODE, "TEACHER_CODE": TEACHER_CODE}, port)
    try:
        time.sleep(8)
        if server.poll() is not None:
            raise RuntimeError("the server stopped: " + server.stderr.read().decode()[-400:])
        _, why = hello(port, name="amy", code="CLUB42", password="whatever")
        check("Wrong class code is turned away", why[0] == 4001, str(why))
        _, why = hello(port, name="amy", code=LEARNER_CODE, password="whatever", version="0.9.0")
        check("An old game version is turned away", why[0] == 4006 and "Out of date" in why[1],
              str(why))
        _, why = hello(port, name="stranger", code=LEARNER_CODE, password="letmein1")
        check("An unknown username can't make an account", why[0] == 4004, str(why))

        teacher, _ = hello(port, name="Teacher", code=TEACHER_CODE)
        teacher.send(json.dumps({"type": "add_learner", "learner": "Amy", "password": "short"}))
        note = wait_for(teacher, "notice")
        check("Short passwords are refused", note and "6 characters" in note["text"], str(note))
        teacher.send(json.dumps({"type": "add_learner", "learner": "Amy", "password": "rocket42"}))
        note = wait_for(teacher, "notice")
        check("The teacher makes an account", note and "Account made" in note["text"], str(note))
        with open(os.path.join(TMP, "profiles", "amy.json"), encoding="utf-8") as f:
            stored = json.load(f)
        check("The password is stored with scrypt, not as text", stored["hash"].startswith("scrypt$")
              and "rocket42" not in json.dumps(stored))

        amy, welcome = hello(port, name="Amy", code=LEARNER_CODE, password="rocket42")
        check("The learner logs in with the teacher's account", amy is not None, str(welcome))

        for _ in range(5):
            hello(port, name="Bob", code=LEARNER_CODE, password="wrong-one")
        _, why = hello(port, name="Bob", code=LEARNER_CODE, password="wrong-one")
        check("Too many wrong tries are blocked for a minute", why[0] in (4004, 4008) and "Wait a minute" in why[1],
              str(why))

        teacher.send(json.dumps({"type": "lesson", "lesson": {"tools": {"brains": True}}}))  # (CHANGE 99: brains on)
        time.sleep(1)
        bomb = "def helper(x=10 ** 10 ** 8):\n    return x\n\n\ndef brain(bot, world):\n    return 'wait'\n"
        t0 = time.time()
        amy.send(json.dumps({"type": "brain", "source": bomb}))
        res = wait_for(amy, "brain_result", 20)
        amy.send(json.dumps({"type": "ping", "t": 0}))
        pong = wait_for(amy, "pong", 5)
        check("A brain with a gigantic sum only stops itself", res and not res["ok"] and "too long" in res["error"]
              and pong is not None and time.time() - t0 < 15, f"upload={res} pong={pong}")

        teacher.send(json.dumps({"type": "export"}))
        csv_msg = wait_for(teacher, "evidence_csv")
        check("The evidence export reaches the teacher's computer", csv_msg and csv_msg["text"].startswith("Learner"))

        teacher.send(json.dumps({"type": "delete_learner", "learner": "Amy"}))
        note = wait_for(teacher, "notice")
        try:
            while True:
                amy.recv(timeout=5)
        except Exception:
            pass
        closed = amy.protocol.close_rcvd
        check("Deleting a learner disconnects them and removes their profile",
              closed and closed.code == 4007 and not os.path.exists(os.path.join(TMP, "profiles", "amy.json")),
              f"{note} {closed}")
    finally:
        stop(server)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        results.append(("Test run", False, repr(e)))
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else f":\n    {note}"))
    sys.exit(0 if results and all(ok for _, ok, _ in results) else 1)
