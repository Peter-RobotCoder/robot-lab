"""A learner whose connection drops keeps their place a while; nobody else is started again (CHANGE 164).

    python engine/seat_test.py [robot|fight|kart|city|craft|all]

A laptop server for the game (its seats held 6 s here, 45 in class), a teacher reading everything, learners Amy and
Ben. Ben moves away from his start. Amy's connection is cut (no goodbye: a lid shut). Then: her robot, fighter or
kart is still there, Ben hasn't been put back at his start; she logs in again and has the same one back; she closes
her window properly and hers goes at once; she's cut off again and doesn't come back, and after the 6 s hers goes.
Kart Lab, with two computer karts: they keep their own karts throughout (a learner leaving used to hand hers to one).
Exit code 0 = all fine.
"""
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stall_test as st  # noqa: E402  (the games, the servers, hello)

HOLD = 6.0
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({note})" if note and not ok else ""), flush=True)


class Watcher:
    """The teacher's connection, read all the time: the last roster and state."""

    def __init__(self, ws):
        self.ws, self.roster, self.state, self.alive = ws, None, None, True
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        while self.alive:
            try:
                m = self.ws.recv(timeout=1)
            except TimeoutError:
                continue
            except Exception:
                return
            if isinstance(m, str):
                m = json.loads(m)
                if m.get("type") == "roster":
                    self.roster = m
                elif m.get("type") == "state":
                    self.state = m


class Reader:
    """A learner's connection, read in the background (so it doesn't stall)."""

    def __init__(self, ws):
        self.ws, self.welcome = ws, None
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        while True:
            try:
                self.ws.recv(timeout=1)
            except TimeoutError:
                continue
            except Exception:
                return

    def cut(self):
        """Gone without a goodbye: the socket just closes."""
        sock = self.ws.socket
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


def learner(port, version, name):
    ws = st.hello(port, version, name=name, code="CLUB42", password=name.lower() + "pass1")
    return Reader(ws)


def units(game, w):
    """{owner: (id, position)} from what the teacher has."""
    out = {}
    if game == "robot" and w.state and w.roster:
        owners = {r["id"]: r["owner"] for r in w.roster["robots"]}
        for a in w.state["arenas"]:
            for r in a["robots"]:
                out[owners.get(r["id"], "?")] = (r["id"], r["pos"])
    elif game == "fight" and w.state and w.roster:
        owners = {f["id"]: f["owner"] for f in w.roster["fighters"]}
        for ring in w.state["rings"]:
            for f in ring["f"]:
                out[owners.get(f["id"], "?")] = (f["id"], f["pos"])
    elif game == "kart" and w.roster:
        for k in w.roster["karts"]:
            out[k["owner"] or f"cpu{k['id']}"] = (k["id"], None)
    elif game == "city" and w.roster:  # (CHANGE 194: a person each; the cars and robots are the computer's)
        for k in w.roster["people"]:
            out[k["owner"] or f"cpu{k['id']}"] = (k["id"], None)
    elif game == "craft" and w.roster:  # (CHANGE 200: a player each, by id; a kept place is still in the roster)
        for pid, k in w.roster["players"].items():
            if k["role"] == "learner":
                out[k["name"]] = (int(pid), None)
    return out


def wait(fn, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.2)
    return fn()


def far(a, b):
    return math.inf if a is None or b is None else math.dist(a[:2], b[:2])


def run(game):
    folder, script, data_var, module = st.GAMES[game]
    version = st.version_of(folder, module)
    work = tempfile.mkdtemp(prefix=f"seats_{game}_")
    port = st.free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("JOIN_CODE", "TEACHER_CODE")}
    env.update({data_var: os.path.join(work, "data"), "CLUBCODERS_SEAT_SECONDS": str(HOLD)})
    args = [sys.executable, script, "--port", str(port)] + (["--cpu", "2"] if game == "kart" else
                                                            ["--traffic", "1", "--robots", "1"] if game == "city" else [])
    server = subprocess.Popen(args, cwd=os.path.join(st.ROOT, folder), env=env,
                              stdout=open(os.path.join(work, "log"), "w"), stderr=subprocess.STDOUT)
    try:
        assert st.wait_port(port), "the server didn't start"
        w = Watcher(st.hello(port, version, name="Teacher", code="TEACH99"))
        amy, ben = learner(port, version, "Amy"), learner(port, version, "Ben")
        wait(lambda: {"Amy", "Ben"} <= set(units(game, w)), 10)
        if game == "robot":
            ben.ws.send(json.dumps({"type": "control", "throttle": 1.0, "steer": 0.3, "fire": False}))
        elif game == "fight":
            ben.ws.send(json.dumps({"type": "control", "f": 1.0, "s": 0.0}))
        elif game == "city":  # (on foot: the way to move, in the world's frame)
            ben.ws.send(json.dumps({"type": "control", "throttle": 1.0, "steer": 0.0, "buttons": 0, "seq": 1}))
        time.sleep(1.5)
        if game == "robot":
            ben.ws.send(json.dumps({"type": "control", "throttle": 0.0, "steer": 0.0, "fire": False}))
        elif game == "fight":
            ben.ws.send(json.dumps({"type": "control", "f": 0.0, "s": 0.0}))
        elif game == "city":
            ben.ws.send(json.dumps({"type": "control", "throttle": 0.0, "steer": 0.0, "buttons": 0, "seq": 2}))
        time.sleep(1.0)
        before = units(game, w)
        cpus = sorted(i for o, (i, _) in before.items() if o.startswith("cpu"))
        amy_id = before.get("Amy", (None,))[0]
        t_before = w.state["t"] if w.state else None
        amy.cut()
        time.sleep(2.0)
        now = units(game, w)
        key = "Amy (away)" if game in ("kart", "city") else "Amy"
        check(f"{game}: Amy's connection cut, her {UNIT[game]} is kept", now.get(key, (None,))[0] == amy_id, str(now))
        if game not in ("kart", "city", "craft"):  # (a rebuilt arena or stage starts its clock again: everyone back at their start)
            check(f"{game}: ...and nobody was started again (Ben where he was, the clock running on)",
                  w.state["t"] > t_before and (game == "fight" or far(before["Ben"][1], now["Ben"][1]) < 0.6),
                  f"t {t_before} then {w.state['t']}; Ben {before['Ben']} then {now.get('Ben')}")
        amy = learner(port, version, "Amy")
        wait(lambda: units(game, w).get("Amy", (None,))[0] == amy_id, 5)
        now = units(game, w)
        check(f"{game}: Amy logs in again and has the same {UNIT[game]} back", now.get("Amy", (None,))[0] == amy_id, str(now))
        if game not in ("kart", "city", "craft"):
            check(f"{game}: ...and still nobody was started again", w.state["t"] > t_before + 2 and
                  (game == "fight" or far(before["Ben"][1], now["Ben"][1]) < 0.6),
                  f"t {t_before} then {w.state['t']}; Ben {before['Ben']} then {now.get('Ben')}")
        amy.ws.close()
        gone = wait(lambda: not any(o.startswith("Amy") for o in units(game, w)), 3)
        check(f"{game}: Amy closes her window: her {UNIT[game]} goes at once", gone, str(units(game, w)))
        amy = learner(port, version, "Amy")
        wait(lambda: "Amy" in units(game, w), 5)
        amy.cut()
        time.sleep(1.0)
        kept = any(o.startswith("Amy") for o in units(game, w))
        gone = wait(lambda: not any(o.startswith("Amy") for o in units(game, w)), HOLD + 3)
        check(f"{game}: cut off again and not back: hers is kept, then goes after the {HOLD:.0f} s", kept and gone,
              str(units(game, w)))
        if game == "kart":
            after = sorted(i for o, (i, _) in units(game, w).items() if o.startswith("cpu"))
            check("kart: the computer karts kept their own karts throughout", after == cpus, f"{cpus} then {after}")
        w.alive = False
    except Exception as e:
        check(f"{game}: the test ran", False, repr(e))
    finally:
        st.stop(server)
        shutil.rmtree(work, ignore_errors=True)


UNIT = {"robot": "robot", "fight": "fighter", "kart": "kart", "city": "driver", "craft": "player"}


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for game in (list(st.GAMES) if which == "all" else [which]):
        run(game)
    bad = [r for r in results if not r[1]]
    print(f"{len(results) - len(bad)} of {len(results)} passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
