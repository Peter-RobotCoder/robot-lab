"""Checks that matches work: the teacher puts two learners in a match, then fights a learner, and both sides of each
fight land hits. Also that a learner's fighting style and weapon are kept (and a weapon only goes with its style),
and that a restart for code changes keeps the lesson as it was.

    python match_test.py

Test data goes to a temporary folder, never to the real profiles or evidence. Exit code 0 = all fine.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

GAME = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, GAME)
from websockets.sync.client import connect  # noqa: E402

PY = sys.executable
results = []


def check(name, ok, note=""):
    results.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"   {note}"), flush=True)


class Client:
    """A window's connection: keeps reading in the background (like the real window) and remembers the latest."""

    def __init__(self, port, **hello):
        self.ws = connect(f"ws://127.0.0.1:{port}", open_timeout=5, max_size=None)
        self.ws.send(json.dumps({"type": "hello"} | hello))
        self.last, self.lock = {}, threading.Lock()
        threading.Thread(target=self.read, daemon=True).start()
        self.wait(lambda: "welcome" in self.last)

    def read(self):
        try:
            for raw in self.ws:
                m = json.loads(raw)
                with self.lock:
                    self.last[m["type"]] = m
        except Exception:
            pass

    def send(self, **m):
        self.ws.send(json.dumps(m))

    def wait(self, cond, secs=10):
        end = time.time() + secs
        while time.time() < end:
            with self.lock:
                if cond():
                    return True
            time.sleep(0.05)
        return False

    def ring_with(self, *owners):
        roster = self.last.get("roster")
        if not roster:
            return None
        rings = {f["owner"]: f["ring"] for f in roster["fighters"]}
        vals = {rings.get(o) for o in owners}
        return vals.pop() if len(vals) == 1 and None not in vals else None

    def fighter(self, owner):
        roster, state = self.last.get("roster"), self.last.get("state")
        fid = next((f["id"] for f in roster["fighters"] if f["owner"] == owner), None)
        return next((f for r in state["rings"] for f in r["f"] if f["id"] == fid), None)


def fight(clients, secs):
    """Each takes a turn to attack while the other walks in (so we see that each can hit the other)."""
    for attacker in clients:
        end = time.time() + secs / len(clients)
        while time.time() < end:
            for c in clients:
                if c is attacker:
                    c.send(type="control", f=1, s=0, hold="", press="punch")
                else:
                    c.send(type="control", f=1, s=0, hold="")
            time.sleep(0.1)


def main():
    with socket.socket() as sock:  # (a free port, so it never clashes with a real server)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    data = tempfile.mkdtemp(prefix="fightlab_fights_")
    server = subprocess.Popen([PY, "fight_server.py", "--port", str(port)], cwd=GAME,
                              env=dict(os.environ, FIGHTLAB_DATA=data), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        time.sleep(4)
        t = Client(port, name="MrP", code="TEACH99")
        a = Client(port, name="Ann", code="CLUB42", password="annann1")
        b = Client(port, name="Ben", code="CLUB42", password="benben1")
        # 1. the teacher puts the two learners in a match
        t.send(type="lesson", lesson={"matches": [["Ann", "Ben"]], "mode": "battle"})
        ok = t.wait(lambda: t.ring_with("Ann", "Ben") is not None)
        check("The teacher's match puts Ann and Ben in the same ring", ok)
        fight([a, b], 10)
        ann, ben = a.fighter("Ann"), a.fighter("Ben")
        check("Ann and Ben both land hits on each other", ann and ben and ann["hits"] > 0 and ben["hits"] > 0,
              f"Ann {ann and ann['hits']}, Ben {ben and ben['hits']}")
        # 2. the teacher fights a learner
        t.send(type="lesson", lesson={"teacher_fighter": True, "matches": [["MrP", "Ann"]]})
        ok = t.wait(lambda: t.ring_with("MrP", "Ann") is not None)
        check("The teacher's own fighter shares a ring with Ann", ok,
              str([(f["owner"], f["ring"]) for f in (t.last.get("roster") or {}).get("fighters", [])]))
        check("Ben gets a ring of his own (with a sparring partner)",
              t.ring_with("Ben", "Computer") is not None or t.ring_with("Ben") is not None)
        before_t = (t.fighter("MrP") or {}).get("hits", 0)
        before_a = (t.fighter("Ann") or {}).get("hits", 0)
        fight([t, a], 10)
        tf, af = t.fighter("MrP"), t.fighter("Ann")
        check("The teacher lands hits on Ann, and Ann on the teacher",
              tf and af and tf["hits"] > before_t and af["hits"] > before_a,
              f"teacher {tf and tf['hits']}, Ann {af and af['hits']}")
        ring = next(r for r in t.last["state"]["rings"] if any(f["id"] == tf["id"] for f in r["f"]))
        check("It is a real battle (rounds and health going down)", ring["tl"] is not None and
              min(f["hp"] / f["max"] for f in ring["f"]) < 1.0, str(ring["ph"]))
        # 3. fighting styles: the style and weapon are kept, and a weapon never goes with the wrong style

        def build(**design):
            with a.lock:
                a.last.pop("design_result", None)
            a.send(type="design", design=design)
            a.wait(lambda: "design_result" in a.last)
            return a.last.get("design_result", {}).get("design", {})
        d = build(fighting_style="swords", weapon="katana")
        ok = d.get("fighting_style") == "swords" and d.get("weapon") == "katana"
        d = build(fighting_style="boxer", weapon="katana")
        ok = ok and d.get("fighting_style") == "boxer" and "weapon" not in d
        d = build(fighting_style="knives", weapon="katana")
        check("Fighting styles: the style and weapon are kept, and a weapon only goes with its own style",
              ok and d.get("fighting_style") == "knives" and d.get("weapon") == "knife", str(d))
        # 4. a restart for code changes (Restart server) keeps the lesson: hazards, mode and matches
        t.send(type="lesson", lesson={"hazards": {"spikes": True, "slippery": True}, "mode": "battle"})
        t.wait(lambda: t.last.get("lesson", {}).get("lesson", {}).get("hazards", {}).get("spikes") is True)
        t.send(type="restart_server")
        code = server.wait(timeout=15)
        server = subprocess.Popen([PY, "fight_server.py", "--port", str(port)], cwd=GAME,  # (as the .bat does)
                                  env=dict(os.environ, FIGHTLAB_DATA=data), stdout=subprocess.DEVNULL,
                                  stderr=subprocess.STDOUT)
        time.sleep(4)
        t2 = Client(port, name="MrP", code="TEACH99")
        hz = t2.last.get("lesson", {}).get("lesson", {}).get("hazards", {})
        check("A restart for code changes keeps the lesson (spikes and ice still on, still a battle)",
              code == 3 and hz.get("spikes") is True and hz.get("slippery") is True and
              t2.last["lesson"]["lesson"].get("mode") == "battle", f"exit {code}, hazards {hz}")
    finally:
        server.kill()
    print(f"{sum(results)}/{len(results)} passed")


if __name__ == "__main__":
    main()
    sys.exit(0 if results and all(results) else 1)
