"""Claude for the browser's test (CHANGE 136): a laptop desk, the helper on a copy of Kart Lab, a stand-in for Claude,
and a scripted browser page asking through the desk: the prompt, Send, the queue, Keep (and the mod files to pass
on), Undo, the change history (the diff, switched off and on, merged, removed), a second helper taking over, and
what the page hears when no helper is connected. Nothing touches the real game folders or Claude.

    python helper/claude_helper_test.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # club-coders/
DEV = os.path.dirname(ROOT)   # the development repository (kart/, engine/ beside club-coders/)
KART = next((p for p in (os.path.join(ROOT, "games", "kartlab"), os.path.join(DEV, "kart"))  # (the public repository, or ours)
             if os.path.exists(os.path.join(p, "ai_pipeline.py"))), None)
ENGINE = next((p for p in (os.path.join(ROOT, "engine"), os.path.join(DEV, "engine")) if os.path.isdir(p)), None)
PASSWORD = "helper-test-teacher-password"
FAKE_CLAUDE = '''import json, os, sys, time
# a stand-in for Claude Code: puts the laps up by two in mods/rules.py, says what it did as Claude's JSON does
time.sleep(float(os.environ.get("FAKE_CLAUDE_WAIT", "0")))
path = os.path.join("mods", "rules.py")
text = open(path, encoding="utf-8", newline="").read()
for a, b in (('"laps": 3,', '"laps": 5,'), ('"laps": 5,', '"laps": 7,'), ('"laps": 7,', '"laps": 3,')):
    if a in text:
        text = text.replace(a, b, 1)
        break
open(path, "w", encoding="utf-8", newline="").write(text)
print(json.dumps({"result": "- mods/rules.py: laps up by two", "total_cost_usd": 0.0}))
'''
# Two cards at once, as a game window sends them (CHANGE 137): the rules card's Claude takes 3 s and edits
# mods/rules.py; the track card's edits mods/track.py at once. Before the fix the rules card, finishing last, put the
# track file back (it was outside its own files and differed from its snapshot), so the track card's work was lost.
FAKE_BY_TARGET = '''import json, os, sys, time
prompt = sys.argv[sys.argv.index("-p") + 1]
track = "mods/track.py" in prompt.split("LEARNER'S REQUEST")[0]
path = os.path.join("mods", "track.py" if track else "rules.py")
if not track:
    time.sleep(3)
text = open(path, encoding="utf-8", newline="").read()
text = text.replace('"name": "Club Circuit"', '"name": "Club Two"', 1) if track else text.replace('"laps": 3,', '"laps": 5,', 1)
open(path, "w", encoding="utf-8", newline="").write(text)
print(json.dumps({"result": "- " + path.replace(os.sep, "/") + ": changed", "total_cost_usd": 0.0}))
'''
TWO_CARDS = '''import json, sys, threading, time
sys.path.insert(0, ".")
import ai_pipeline as P
card = {"goal": "x", "variables": "", "test": "", "predict": ""}
a, b = P.AIChange(1, "amy", card, "rules"), P.AIChange(2, "ben", card, "track")
ta = threading.Thread(target=a.run, kwargs={"progress": lambda m: None})
ta.start()
time.sleep(0.5)  # (the rules card is with Claude: the track card comes second, as a teacher's second click)
tb = threading.Thread(target=b.run, kwargs={"progress": lambda m: None})
tb.start()
time.sleep(0.5)
seen = {"busy": P.busy(), "b_waiting": b.waiting, "switch": P.rollback(1)["message"]}
try:
    a.undo()
    seen["undo"] = "allowed"
except RuntimeError as e:
    seen["undo"] = str(e)
ta.join()
tb.join()
seen.update(a_files=a.result["files"], b_files=b.result["files"], a_blocked=a.result["blocked"],
            b_blocked=b.result["blocked"], b_after_a=b.started >= a.started + 3, busy_after=P.busy())
print(json.dumps(seen))
'''
results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
        print(f"PASS {name}")
    except Exception as e:  # (every check runs; the failures are listed at the end)
        results.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"FAIL {name}: {type(e).__name__}: {e}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_port(port, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        try:
            socket.create_connection(("127.0.0.1", port), 0.5).close()
            return True
        except OSError:
            time.sleep(0.2)
    return False


def stop(proc):  # (the helper's game pipelines too: the whole tree)
    if proc and proc.poll() is None:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True) if os.name == "nt" \
            else proc.kill()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            pass


class Page:
    """The browser page's side of the desk, scripted: logs in as the teacher with claude: true."""

    def __init__(self, port):
        from websockets.sync.client import connect
        self.ws = connect(f"ws://127.0.0.1:{port}/desk", max_size=None, open_timeout=10)
        self.ws.send(json.dumps({"type": "teacher", "password": PASSWORD, "claude": True}))
        first = json.loads(self.ws.recv())
        assert first.get("ok") and "claude" in first, first
        self.claude = first["claude"]
        self.rid = 0

    def pump(self, seconds=0.2, until=None):
        end = time.time() + seconds
        reply = None
        while time.time() < end:
            try:
                m = json.loads(self.ws.recv(timeout=max(0.01, end - time.time())))
            except TimeoutError:
                break
            if "claude" in m:
                self.claude = m["claude"]
            if "claude_reply" in m and until is not None and m["claude_reply"].get("rid") == until:
                reply = m["claude_reply"]
                break
        return reply

    def ask(self, what, seconds=60, **args):
        self.rid += 1
        self.ws.send(json.dumps({"type": "claude", "game": "kartlab", "do": what, "rid": self.rid, **args}))
        reply = self.pump(seconds, until=self.rid)
        assert reply is not None, f"no answer to {what}"
        return reply

    def kart(self):
        return ((self.claude or {}).get("states") or {}).get("kartlab")

    def wait(self, test, seconds, what):
        end = time.time() + seconds
        while time.time() < end:
            k = self.kart()
            if k is not None and test(k):
                return k
            self.pump(0.3)
        raise AssertionError(f"waited {seconds} s for {what}: {json.dumps(self.kart())[:600]}")


def main():
    work = tempfile.mkdtemp(prefix="clubcoders_helper_")
    kart = os.path.join(work, "kart")
    shutil.copytree(KART, kart, ignore=shutil.ignore_patterns(
        ".venv", "__pycache__", "data", "profiles", "evidence", "ai_changes", "ai_requests", "brains", "assets"))
    shutil.copytree(ENGINE, os.path.join(work, "engine"),
                    ignore=shutil.ignore_patterns("__pycache__", "assets"))
    with open(os.path.join(work, "fake_claude.py"), "w", encoding="utf-8") as f:
        f.write(FAKE_CLAUDE)
    rules = os.path.join(kart, "mods", "rules.py")
    original = open(rules, encoding="utf-8").read()
    desk_port = free_port()
    with open(os.path.join(work, "games.json"), "w") as f:
        json.dump({"kartlab": "ws://127.0.0.1:1"}, f)
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "TEACHER_CODE": PASSWORD,
           "CLUBCODERS_DESK_DATA": os.path.join(work, "desk"), "CLUBCODERS_TICKET_KEY": os.path.join(work, "desk", "key"),
           "CLUBCODERS_LIVE_FILE": os.path.join(work, "desk", "live.json"), "KARTLAB_DATA": os.path.join(work, "data"),
           "CLUBCODERS_KARTLAB_DIR": kart, "CLAUDE_CMD": f'"{sys.executable}" "{os.path.join(work, "fake_claude.py")}"',
           "FAKE_CLAUDE_WAIT": "2"}
    desk = subprocess.Popen([sys.executable, os.path.join(ROOT, "desk", "club_desk.py"), "--port", str(desk_port),
                             "--games", os.path.join(work, "games.json")], env=env,
                            stdout=open(os.path.join(work, "desk.log"), "w"), stderr=subprocess.STDOUT)

    def helper(log):
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "claude_helper.py"), "--server",
                              f"ws://127.0.0.1:{desk_port}", "--password-stdin", "--games", "kartlab"], env=env,
                             stdin=subprocess.PIPE, stdout=open(os.path.join(work, log), "w"), stderr=subprocess.STDOUT)
        p.stdin.write((PASSWORD + "\n").encode())
        p.stdin.flush()
        return p

    helpers = []
    page = None
    try:
        assert wait_port(desk_port), "the desk didn't start"

        def two_cards():  # (the engine's pipeline as the game windows use it: no helper, no desk)
            track = os.path.join(kart, "mods", "track.py")
            keep = {p: open(p, "rb").read() for p in (rules, track)}
            with open(os.path.join(work, "fake_by_target.py"), "w", encoding="utf-8") as f:
                f.write(FAKE_BY_TARGET)
            with open(os.path.join(work, "two_cards.py"), "w", encoding="utf-8") as f:
                f.write(TWO_CARDS)
            try:
                r = subprocess.run([sys.executable, os.path.join(work, "two_cards.py")], cwd=kart, capture_output=True,
                                   text=True, timeout=180, env={**env, "CLAUDE_CMD": f'"{sys.executable}" "{os.path.join(work, "fake_by_target.py")}"'})
                seen = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
                assert seen, r.stdout[-1500:] + r.stderr[-1500:]
                assert seen["a_files"] == ["mods/rules.py"] and seen["b_files"] == ["mods/track.py"], seen
                assert seen["a_blocked"] == [] and seen["b_blocked"] == [], seen
                assert '"laps": 5,' in open(rules, encoding="utf-8").read(), "the rules card's change was lost"
                assert '"name": "Club Two"' in open(track, encoding="utf-8").read(), "the track card's change was lost"
                assert seen["busy"] and seen["b_waiting"] and seen["b_after_a"] and not seen["busy_after"], seen
                assert seen["undo"].startswith("Wait until Claude has finished"), seen
                assert seen["switch"].startswith("Wait until Claude has finished"), seen
            finally:
                for p, data in keep.items():
                    with open(p, "wb") as f:
                        f.write(data)
        check("Two cards at once (as a window sends them): the second waits its turn and both changes are kept; Undo "
              "and the mod switches wait while Claude works", two_cards)

        def no_helper():
            p = Page(desk_port)
            assert p.claude is None, p.claude
            r = p.ask("state", 10)
            assert r["ok"] is False and "isn't connected" in r["error"], r
            p.ws.close()
        check("Without Claude's computer the page hears so, and a request is answered with why", no_helper)

        nonlocal_page = {}

        def connects():
            helpers.append(helper("helper1.log"))
            p = nonlocal_page["p"] = Page(desk_port)
            k = p.wait(lambda k: "history" in k, 40, "the helper's Kart Lab state")
            assert p.claude["games"] == ["kartlab"] and p.claude["machine"], p.claude
            assert k["targets"] == ["kart", "track", "rules", "game"], k["targets"]
            assert k["jobs"] == {} and k["history"] == [], k
        check("Claude for the browser logs in to the desk and the page gets its state", connects)
        page = nonlocal_page.get("p")
        card = {"goal": "More laps in a race", "variables": "laps = 5", "test": "Race and count the laps",
                "predict": "Five laps", "target": "rules", "privacy": True, "review": True, "credit": True}

        def prompt():
            r = page.ask("prompt", card=card, learner="amy", target="rules", as_user_mod=False)
            assert r["ok"] and "mods/rules.py" in r["prompt"] and "More laps in a race" in r["prompt"], r
            assert "amy" in r["prompt"] and r["target"] == "rules"
        check("The page gets exactly the prompt Send to Claude sends", prompt)

        def send_and_queue():
            assert page.ask("send", id=1, card=card, learner="amy", target="rules", as_user_mod=False)["ok"]
            assert page.ask("send", id=2, card=card, learner="ben", target="rules", as_user_mod=False)["ok"]
            k = page.wait(lambda k: k["jobs"].get("1", {}).get("status") == "Claude is working..." and "2" in k["jobs"], 20,
                          "card 1 with Claude")
            assert k["jobs"]["2"]["status"].startswith("Waiting: Claude is finishing card #1"), k["jobs"]["2"]
            r = page.ask("send", id=1, card=card, learner="amy", target="rules")
            assert r["ok"] is False and "already" in r["error"], r
            k = page.wait(lambda k: k["jobs"]["1"]["status"] == "Check it", 60, "card 1's result")
            res = k["jobs"]["1"]["result"]
            assert res["files"] == ["mods/rules.py"] and res["test_ok"], res
            assert '+    "laps": 5,' in res["diff"], res["diff"]
        check("Send: one card at a time with Claude, the next one waiting, then the tested result", send_and_queue)

        def undo_waits():
            k = page.kart()
            if k["jobs"]["2"]["status"] == "Claude is working...":
                r = page.ask("undo", id=1)
                assert r["ok"] is False and "Wait until Claude has finished card #2" in r["error"], r
            page.wait(lambda k: k["jobs"]["2"]["status"] == "Check it", 60, "card 2's result")
        check("Undo waits while Claude is at work on another card", undo_waits)

        def keep():
            assert '"laps": 7,' in open(rules, encoding="utf-8").read()  # (card 1: 5, then card 2 on top: 7)
            r = page.ask("undo", id=2)
            assert r["ok"], r
            assert '"laps": 5,' in open(rules, encoding="utf-8").read()
            r = page.ask("keep", id=1)
            assert r["ok"] and '"laps": 5,' in r["mods"]["mods/rules.py"] and r["engine"] == [], r
            k = page.wait(lambda k: k["history"], 10, "the kept change in the history")
            assert k["jobs"]["1"]["status"] == "Kept" and k["jobs"]["2"]["status"] == "Undone"
            assert k["history"][0]["n"] == 1 and k["history"][0]["status"] == "kept", k["history"]
            assert page.ask("keep", id=1)["ok"] is False
            r = page.ask("clear", id=2)
            assert r["ok"], r
            assert "2" not in page.wait(lambda k: "2" not in k["jobs"], 10, "card 2 cleared")["jobs"]
        check("Undo puts the file back; Keep records the change and returns the mod file to pass on", keep)

        def history():
            d = page.ask("diff", n=1)
            assert d["ok"] and '-    "laps": 3,' in d["diff"] and '+    "laps": 5,' in d["diff"], d
            r = page.ask("rollback", n=1)
            assert r["ok"] and '"laps": 3,' in r["mods"]["mods/rules.py"], r
            assert open(rules, encoding="utf-8").read() == original
            assert page.ask("merge", n=1)["ok"] is False  # (switched off: can't be merged)
            r = page.ask("reapply", n=1)
            assert r["ok"] and '"laps": 5,' in open(rules, encoding="utf-8").read(), r
            r = page.ask("merge", n=1)
            assert r["ok"], r
            k = page.wait(lambda k: k["history"][0]["status"] == "merged", 10, "merged")
            assert k["merged_count"] == 1
            assert page.ask("forget", n=1)["ok"] is False  # (merged: it stays)
        check("The change history: the diff, switched off and on (the mod file each time), merged", history)

        def forget():
            assert page.ask("send", id=3, card=card, learner="amy", target="rules")["ok"]
            page.wait(lambda k: k["jobs"].get("3", {}).get("status") == "Check it", 60, "card 3's result")
            assert page.ask("keep", id=3)["ok"]
            assert page.ask("forget", n=2)["ok"] is False  # (on: switch it off first)
            assert page.ask("rollback", n=2)["ok"]
            assert page.ask("forget", n=2)["ok"]
            k = page.wait(lambda k: len(k["history"]) == 1, 10, "mod 2 removed")
            assert '"laps": 5,' in open(rules, encoding="utf-8").read()
        check("A mod switched off can be removed for good", forget)

        def bad_requests():
            assert page.ask("send", id=4, card=card, learner="amy", target="nonsense")["ok"] is False
            assert page.ask("explode")["ok"] is False
            assert page.ask("keep", id=99)["ok"] is False
        check("Requests it can't do are answered with why", bad_requests)

        def taken_over():
            helpers.append(helper("helper2.log"))
            end = time.time() + 30
            while helpers[0].poll() is None and time.time() < end:
                time.sleep(0.3)
            assert helpers[0].poll() is not None, "the first helper didn't stop"
            k = page.wait(lambda k: "history" in k and k["jobs"] == {}, 40, "the second helper's state")
            assert len(k["history"]) == 1 and k["jobs"] == {}, k
            stop(helpers[1])
            end = time.time() + 15
            while page.claude is not None and time.time() < end:
                page.pump(0.3)
            assert page.claude is None, "the page wasn't told Claude's computer went"
        check("A second computer takes over from the first; when it goes, the page hears so", taken_over)

        def the_launcher_unchanged():  # (the app's Teacher screen doesn't ask for Claude's messages)
            from websockets.sync.client import connect
            with connect(f"ws://127.0.0.1:{desk_port}/desk", max_size=64 * 1024) as ws:
                ws.send(json.dumps({"type": "teacher", "password": PASSWORD}))
                m = json.loads(ws.recv())
                assert m.get("ok") and "claude" not in m, m
        check("The app's Teacher screen gets the desk's messages as before", the_launcher_unchanged)
    finally:
        if page:
            page.ws.close()
        for h in helpers:
            stop(h)
        stop(desk)
    for name, ok, note in results:
        if not ok:
            print(f"FAIL {name}\n    {note}")
    print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed  (logs: {work})")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
