"""The Missions class server running the missions (CHANGE 198): its runs the same as the window's own, and a class
seeing each other's robots.

    .venv\\Scripts\\python missions_server_test.py           everything (a minute or two)
    .venv\\Scripts\\python missions_server_test.py quick     no window

1. every recorded mission (missions/*/replay_mission.json: Mission 1's and Mission 2's, the fixed ones and the
   made-up ones) played through the server, a learner's programs sent as a window sends them: every run's status
   and events (each state rebuilt from what changed), the end state, the stars and the objectives the same as
   recorded through the mission's own Python
2. two learners: each sees the other's robot start, run (the steps end where its robot is) and leave; a third
   joining is told where everyone is
3. the lesson's objectives marked from the server's own runs (a failed run, then a three-star finish: 1a to 1d),
   the Solar Panel kept in the learner's progress here, and a learner coming back carries on where they were
4. the real window in the class (offscreen): the recorded Mission 1 key presses played into it, its runs sent to
   the server and played as the server's events give them, the same as recorded; another learner's robot drawn in
   its valley where that learner's run left it; a picture of the two
Test data goes to a temporary folder; the server runs on port 8890. Exit code 0 = all fine.
"""
import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import zlib

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
PY = sys.executable
PORT = 8890
URL = f"ws://127.0.0.1:{PORT}"
TMP = tempfile.mkdtemp(prefix="missions_server_test_")
QUICK = "quick" in sys.argv[1:]
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note and not ok else ""), flush=True)


def recording(mission):
    with open(os.path.join(HERE, "missions", mission, "replay_mission.json"), encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"], json.loads(zlib.decompress(base64.b64decode(data["results"])))


def same(x):
    return json.loads(json.dumps(x, sort_keys=True))


def start_server():
    log = open(os.path.join(TMP, "server.log"), "w", encoding="utf-8")
    proc = subprocess.Popen([PY, "missions_server.py", "--port", str(PORT)], stdout=log, stderr=subprocess.STDOUT,
                            env={**os.environ, "MISSIONS_DATA": TMP, "MISSIONS_RUN_GAP": "0"})
    for _ in range(150):
        try:
            socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
            return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("the server stopped: " + open(log.name, encoding="utf-8").read()[-2000:])
            time.sleep(0.1)
    raise RuntimeError("the server didn't start")


def stop(proc):
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()
    try:
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        pass


class Learner:
    """A window's side of the class, by hand: logged in, its messages read in order."""

    async def open(self, name, role="learner"):
        self.ws = await websockets.connect(URL, max_size=None)
        await self.ws.send(json.dumps({"type": "hello", "name": name,
                                       "code": "TEACH99" if role == "teacher" else "CLUB42"}))
        self.name, self.seen = name, []
        self.welcome = await self.wait("welcome")
        return self

    async def send(self, m):
        await self.ws.send(json.dumps(m))

    async def wait(self, kind, seconds=10, test=None):
        deadline = time.time() + seconds
        while True:
            for i, m in enumerate(self.seen):
                if m.get("type") == kind and (test is None or test(m)):
                    return self.seen.pop(i)
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError(f"{self.name}: no {kind} message")
            self.seen.append(json.loads(await asyncio.wait_for(self.ws.recv(), left)))

    async def close(self):
        await self.ws.close()


def unpack(before, events):
    cur, out = dict(before), []
    for e in events:
        cur = dict(cur, **e.get("d", {}))
        out.append(dict({k: v for k, v in e.items() if k != "d"}, state=cur))
    return out


async def play_case(L, mission, case):
    """A recorded case through the server, in replay_mission.py's result shape."""
    parts = ["solar_panel"] if case.get("solar") else []
    await L.send({"type": "progress", "progress": {"parts": parts, "missions": {}}})
    await L.send({"type": "start", "mission": mission, "robot": case["robot"]})
    st = await L.wait("state")
    out, final = [], st
    for text in case["runs"]:
        await L.send({"type": "program", "mission": mission, "text": text})
        ran = await L.wait("ran")
        if ran["status"] == "error":
            out.append({"error": True})
            continue
        out.append({"status": ran["status"], "events": [{k: e.get(k) for k in ("type", "line", "msg", "tone", "state")}
                                                         for e in unpack(ran["before"], ran["events"])]})
        final = ran
    out.append({"final": final["state"], "stars": final["stars"], "objectives": final["objectives"]})
    return out


def first_difference(want, got):
    for r, (a, b) in enumerate(zip(want, got)):
        if a == b:
            continue
        if "final" in a or "final" in b:
            k = next((k for k in ("final", "stars", "objectives") if a.get(k) != b.get(k)), "?")
            return f"the end: {k}"
        if a.get("status") != b.get("status") or a.get("error") != b.get("error"):
            return f"run {r + 1}: status was {a.get('status', 'error')}, now {b.get('status', 'error')}"
        for e, (x, y) in enumerate(zip(a.get("events", []), b.get("events", []))):
            if x != y:
                field = next((k for k in x if x.get(k) != y.get(k)), "?")
                return f"run {r + 1}, event {e + 1}: {field} was {x.get(field)!r}, now {y.get(field)!r}"
        return f"run {r + 1}: {len(a.get('events', []))} events recorded, now {len(b.get('events', []))}"
    return f"{len(want)} runs recorded, now {len(got)}"


async def replays():
    for mission in ("wake_up_call", "lights_out"):
        cases, want = recording(mission)
        L = await Learner().open("Replay" + mission[:4])
        bad = []
        for i, (case, w) in enumerate(zip(cases, want)):
            got = same(await play_case(L, mission, case))
            if got != same(w):
                bad.append(f"case {i + 1}: {first_difference(same(w), got)}")
        await L.close()
        check(f"{mission}: all {len(cases)} recorded missions played through the server give the recorded runs, end "
              f"state, stars and objectives", not bad, "; ".join(bad[:3]))


async def class_together():
    a = await Learner().open("Ana")
    b = await Learner().open("Ben")
    await a.send({"type": "start", "mission": "wake_up_call", "robot": "TITAN"})
    placed = await b.wait("robot", test=lambda m: m.get("name") == "Ana")
    await a.send({"type": "program", "mission": "wake_up_call", "text": "move forward 2\nturn right\nmove forward 1"})
    ran = await a.wait("ran")
    moved = await b.wait("robot", test=lambda m: m.get("name") == "Ana" and len(m.get("steps") or []) > 1)
    end = ran["state"]
    steps = moved["steps"]
    check("a second learner sees the first's robot start, and its run's steps (ending where it is)",
          placed["steps"][0][0] == "place" and placed["robot"] == "TITAN" and [s[0] for s in steps] ==
          ["move", "move", "turn", "move"] and steps[-1][1:4] == [end["x"], end["y"], end["dir"]], json.dumps(steps)[:200])
    c = await Learner().open("Cal")
    world = await c.wait("world")
    ana = next((r for r in world["robots"] if r["name"] == "Ana"), None)
    check("a learner joining is told where everyone's robot is",
          ana is not None and ana["at"][:3] == [end["x"], end["y"], end["dir"]] and ana["mission"] == "wake_up_call",
          json.dumps(world)[:200])
    await a.close()
    gone = await b.wait("robot", test=lambda m: m.get("name") == "Ana" and m.get("gone"))
    check("a learner leaving: the others are told", bool(gone))
    await b.close()
    await c.close()


async def objectives_and_coming_back():
    import wake_up_call_test as T  # (the solution and its steps: Mission 1's own cases)
    L = await Learner().open("Dee")
    await L.send({"type": "start", "mission": "wake_up_call", "robot": "TITAN"})
    await L.wait("state")
    await L.send({"type": "program", "mission": "wake_up_call", "text": "move forward 20"})
    bump = await L.wait("ran")
    await L.send({"type": "start", "mission": "wake_up_call", "robot": "TITAN"})
    await L.wait("state")
    await L.send({"type": "program", "mission": "wake_up_call", "text": "move forward 1"})
    await L.wait("ran")
    await L.close()
    L = await Learner().open("Dee")
    back = await L.wait("state", test=lambda m: m.get("back"))
    check("a learner coming back carries on where they were (their robot one square up)",
          back["state"]["y"] == 5 and back["state"]["runs"] == 1, json.dumps(back["state"])[:200])
    await L.send({"type": "start", "mission": "wake_up_call", "robot": "RAZORBACK"})
    await L.wait("state")
    for text in ("move forward 9", "turn right"):  # (a run that stops: a bump)
        await L.send({"type": "program", "mission": "wake_up_call", "text": text})
        await L.wait("ran")
    await L.send({"type": "program", "mission": "wake_up_call", "text": "move forward 30"})
    await L.wait("ran")  # (flat battery: the mission over)
    await L.send({"type": "start", "mission": "wake_up_call", "robot": "TITAN"})
    await L.wait("state")
    await L.send({"type": "program", "mission": "wake_up_call", "text": T.SOLUTION})
    done = await L.wait("ran")
    await L.close()
    with open(os.path.join(TMP, "profiles", "dee.json"), encoding="utf-8") as f:
        saved = json.load(f)
    marked = sorted(saved["record"]["done"])
    check("the objectives marked from the server's own runs: a failed run, then a three-star finish (1a to 1d)",
          bump["status"] in ("stopped", "flat") and done["status"] == "complete" and done["stars"]["count"] == 3
          and marked == ["1a", "1b", "1c", "1d"], f"{bump['status']} {done['status']} {marked}")
    check("the finish kept in the learner's progress on the server: the Solar Panel, three stars",
          "solar_panel" in saved["progress"]["parts"] and saved["progress"]["missions"]["wake_up_call"]["bestStars"] == 3,
          json.dumps(saved["progress"])[:200])
    L = await Learner().open("Dee")
    await L.send({"type": "start", "mission": "lights_out", "robot": "TITAN"})
    st = await L.wait("state", test=lambda m: m.get("mission") == "lights_out")
    check("Mission 2 on the server fits the Solar Panel Mission 1 unlocked", st["state"]["solar"] is True)
    await L.close()


async def ghost_for_window():
    bo = await Learner().open("Bo")
    await bo.send({"type": "start", "mission": "wake_up_call", "robot": "RAZORBACK"})
    await bo.wait("state")
    await bo.send({"type": "program", "mission": "wake_up_call", "text": "move forward 3\nturn right\nmove forward 2"})
    ran = await bo.wait("ran")
    return bo, ran["state"]


def window_in_class():
    cases, want = recording("wake_up_call")
    cases, want = cases[:5], want[:5]  # (the fixed missions, as replay_mission.py --window plays them)
    keys = [dict(c) for c in cases]
    k0 = keys[0]["keys"]  # (the picture: just after the robot is chosen, before the code panel opens)
    keys[0]["keys"] = k0[:1] + [["frames", 60], ["shot", "class"]] + k0[1:]
    path = os.path.join(TMP, "keys.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(keys, f)

    async def with_bo():
        bo, at = await ghost_for_window()
        shot = os.path.join(TMP, "window.png")
        r = await asyncio.to_thread(subprocess.run, [
            PY, "wake_up_call.py", "--offscreen", "--no-sound", "--fast", "--host", URL, "--name", "Sam",
            "--progress", os.path.join(TMP, "sam.json"), "--replay", path, "--screenshot", shot],
            capture_output=True, text=True, timeout=900)
        await bo.close()
        return r, at, shot
    r, at, shot = asyncio.run(with_bo())
    out = r.stdout + r.stderr
    played = [json.loads(ln[7:]) for ln in out.splitlines() if ln.startswith("REPLAY {")]
    bad = [f"case {d['case'] + 1}: {first_difference(same(want[d['case']]), same(d['result']))}"
           for d in played if same(d["result"]) != same(want[d["case"]])]
    check("the window in a class: the five recorded Mission 1 missions played by their key presses, run by the server, "
          "the same as recorded", len(played) == 5 and not bad and "Traceback" not in out,
          "; ".join(bad[:3]) or out[-1500:])
    ghosts = next((json.loads(ln[len("REPLAY GHOSTS "):]) for ln in out.splitlines() if ln.startswith("REPLAY GHOSTS ")), {})
    check("the window draws another learner's robot where that learner's run left it",
          ghosts.get("Bo") == ["wake_up_call", "RAZORBACK", [at["x"], at["y"]]], json.dumps(ghosts))
    pic = shot.replace(".png", "_class.png")
    check("a picture of the class: Sam's robot and Bo's", os.path.exists(pic) and os.path.getsize(pic) > 50000, pic)


if __name__ == "__main__":
    server = start_server()
    try:
        for fn in (replays, class_together, objectives_and_coming_back):
            try:
                asyncio.run(fn())
            except Exception as e:  # (report and carry on)
                check(fn.__name__, False, repr(e))
        if not QUICK:
            try:
                window_in_class()
            except Exception as e:
                check("window_in_class", False, repr(e))
    finally:
        stop(server)
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} passed  (test data: {TMP})")
    sys.exit(1 if failed else 0)
