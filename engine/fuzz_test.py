"""Odd and broken messages never break a game server (CHANGE 165).

    python engine/fuzz_test.py [robot|fight|kart|city|all] [messages]

A laptop server for the game, a teacher and a learner connected. Each sends seeded random messages: every kind the
server's own code handles (read from its source), with fields missing, of the wrong type, huge, NaN, negative,
nested, very long, or right; plus a few not JSON, not an object, and binary frames. After each message a ping must
come back as a pong (the server is still answering that window): a message that made the server close the window
(1011: an error in its code) or stop answering is a failure, and is shown, cut down to the fewest fields that still
do it. The server's log must have no error ("Traceback"), and afterwards what it sends no NaN or Infinity
(a number let in that spoils the game quietly). Exit code 0 = all fine.
"""
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stall_test as st  # noqa: E402

SEED = int(os.environ.get("FUZZ_SEED", 20261018))  # (another seed: FUZZ_SEED=...)
SKIP = {"restart_server", "restart_clients", "delete_learner", "delete_data", "export", "evidence", "reset_password",
        "remove_learner", "make_live", "shutdown", "save_settings", "live_restart",
        "mods_update"}  # (they end the test's own session; mods_update writes the game folder's mods/)
VALUES = [None, True, False, 0, 1, -1, 0.5, -0.5, 1e9, -1e9, 1e308, float("nan"), float("inf"), "", "x", "a" * 5000,
          [], [1, 2, 3], {}, {"a": 1}, [[1, 2], [3]], "ring", "medium", "on", 3, 100, -100]


def kinds_of(source):
    found = set(re.findall(r'kind == "([a-z_]+)"', source))
    for group in re.findall(r"kind in \(([^)]*)\)", source):
        found |= set(re.findall(r'"([a-z_]+)"', group))
    return sorted(found - SKIP - {"hello"})


def fields_of(source):
    """The field names the server reads from messages (m["x"], m.get("x"))."""
    return sorted(set(re.findall(r'\bm\[\s*"([a-z_A-Z0-9]+)"\s*\]', source)) |
                  set(re.findall(r'\bm\.get\(\s*"([a-z_A-Z0-9]+)"', source)) - {"type"})


def nested_of(source):
    """Every name the server reads with .get("...") or ["..."]: the keys an object inside a message may have (the
    lesson's settings, a design's parts, a card's fields)."""
    return sorted(set(re.findall(r'\.get\(\s*"([a-z_A-Z0-9]+)"', source)) |
                  set(re.findall(r'\[\s*"([a-z_A-Z0-9]+)"\s*\]', source)) - {"type"})


def value(rng, keys, depth=0):
    if depth < 2 and rng.random() < 0.2:
        return {rng.choice(keys): value(rng, keys, depth + 1) for _ in range(rng.randint(0, 5))}
    if depth < 2 and rng.random() < 0.1:
        return [value(rng, keys, depth + 1) for _ in range(rng.randint(0, 4))]
    return rng.choice(VALUES)


def message(rng, kinds, fields, keys):
    m = {"type": rng.choice(kinds)}
    for f in rng.sample(fields, rng.randint(0, min(6, len(fields)))):
        m[f] = value(rng, keys)
    return m


def dumps(m):
    return json.dumps(m, allow_nan=True)


class Server:
    def __init__(self, game):
        self.game = game
        folder, script, data_var, module = st.GAMES[game]
        self.version = st.version_of(folder, module)
        self.work = tempfile.mkdtemp(prefix=f"fuzz_{game}_")
        self.port = st.free_port()
        env = {k: v for k, v in os.environ.items() if k not in ("JOIN_CODE", "TEACHER_CODE")}
        env[data_var] = os.path.join(self.work, "data")
        self.log = os.path.join(self.work, "log")
        self.proc = subprocess.Popen([sys.executable, script, "--port", str(self.port)], cwd=os.path.join(st.ROOT, folder),
                                     env=env, stdout=open(self.log, "w"), stderr=subprocess.STDOUT)
        assert st.wait_port(self.port), "the server didn't start"
        with open(os.path.join(st.ROOT, folder, script), encoding="utf-8") as f:
            source = f.read()
        teaching = os.path.join(st.ROOT, "engine", "teaching.py")
        with open(teaching, encoding="utf-8") as f:
            source_all = source + f.read()
        self.kinds, self.fields, self.keys = kinds_of(source_all), fields_of(source_all), nested_of(source_all)

    def connect(self, who):
        if who == "teacher":
            return st.hello(self.port, self.version, name="Teacher", code="TEACH99")
        return st.hello(self.port, self.version, name="Fuzzy", code="CLUB42", password="fuzzy123")

    def stop(self):
        st.stop(self.proc)
        with open(self.log, encoding="utf-8", errors="replace") as f:
            text = f.read()
        shutil.rmtree(self.work, ignore_errors=True)
        return text


def answers(ws, seconds=3.0):
    """A ping comes back as a pong: the server still answers this window."""
    t = time.time()
    ws.send(json.dumps({"type": "ping", "t": t}))
    end = time.time() + seconds
    while time.time() < end:
        m = ws.recv(timeout=max(0.05, end - time.time()))
        if isinstance(m, str) and '"pong"' in m and json.loads(m).get("t") == t:
            return True
    return False


def breaks(server, who, raw):
    """Whether this one message breaks the window's connection (on a fresh one)."""
    ws = server.connect(who)
    try:
        ws.send(raw)
        return not answers(ws)
    except Exception:
        return True
    finally:
        try:
            ws.close()
        except Exception:
            pass


def shrink(server, who, m):
    """The message with as few fields as still break it."""
    for key in [k for k in m if k != "type"]:
        smaller = {k: v for k, v in m.items() if k != key}
        if breaks(server, who, dumps(smaller)):
            m = smaller
    return m


def distinct_errors(log):
    """Each different error in the log: where it happened (the last line of the game's own code) and what."""
    out = []
    for block in log.split("Traceback (most recent call last):")[1:]:
        lines = block.strip().splitlines()
        where = [ln.strip() for ln in lines if ln.strip().startswith("File ") and ".venv" not in ln]
        what = next((ln for ln in reversed(lines) if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Exit)", ln)), "?")
        text = f"{where[-1] if where else '?'}: {what.strip()[:160]}".replace(st.ROOT + os.sep, "")
        if text not in out:
            out.append(text)
    return out


def run(game, count):
    rng = random.Random(SEED)
    server = Server(game)
    problems = []
    try:
        for who in ("learner", "teacher"):
            ws = server.connect(who)
            sent = 0
            while sent < count:
                r = rng.random()
                if r < 0.03:
                    raw = rng.choice(["not json", "[1,2,3]", "42", "null", '"text"', "{", ""])
                    m = None
                elif r < 0.05:
                    raw = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 40)))
                    m = None
                else:
                    m = message(rng, server.kinds, server.fields, server.keys)
                    raw = dumps(m)
                sent += 1
                try:
                    ws.send(raw)
                    ok = answers(ws)
                except Exception:
                    ok = False
                if not ok:
                    code = getattr(getattr(ws.protocol, "close_rcvd", None), "code", None)
                    small = shrink(server, who, m) if isinstance(m, dict) else raw
                    problems.append(f"{who}: {str(small)[:300]} (closed {code})")
                    if len(problems) >= 8:
                        break
                    ws = server.connect(who)
            # what the server says afterwards: no number spoilt (a NaN or infinity let in spoils a whole game quietly)
            end, bad = time.time() + 1.5, set()
            while time.time() < end:
                try:
                    msg = ws.recv(timeout=0.5)
                except TimeoutError:
                    continue
                if isinstance(msg, str) and ("NaN" in msg or "Infinity" in msg):
                    bad.add(json.loads(msg).get("type"))
            if bad:
                problems.append(f"{who}: afterwards the server sends NaN or Infinity in its {sorted(bad)} messages")
        log = server.stop()
    except Exception:
        log = server.stop()
        raise
    errors = distinct_errors(log)
    if errors:
        problems.append(f"the server's log has {len(errors)} different errors:\n" + "\n".join(errors))
    ok = not problems
    print(f"[{'PASS' if ok else 'FAIL'}] {game}: {count} odd messages each from a learner and the teacher "
          f"({len(server.kinds)} kinds, {len(server.fields)} fields) never break the server", flush=True)
    for p in problems:
        print("    " + p.replace("\n", "\n    "))
    return ok


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    ok = True
    for game in (list(st.GAMES) if which == "all" else [which]):
        ok &= run(game, count)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
