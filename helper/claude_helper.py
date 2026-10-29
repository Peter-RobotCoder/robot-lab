"""Claude for the browser (CHANGE 136): a computer of the teacher's does Club Coders Live's AI cards.

A game's teacher window sends an approved AI card to Claude Code on the teacher's laptop (engine/ai_pipeline.py).
A browser can't run Claude, so this does it for the browser. Started on a computer that has the club's project
folders and Claude Code logged in (the teacher's laptop, or any computer like it), it logs in to the club desk as
the teacher and waits. The browser's AI cards and Changes tabs send their requests through the desk: Claude runs
here, on this computer's own Claude login (so a Claude plan costs nothing extra per card), the change is tested
here and kept here (in ai_changes/, where Make my changes live finds it), and the browser passes kept mods on to
the class server as the window does. Nothing goes to Claude until the teacher presses Send to Claude on the page.

One card at a time goes to Claude for each game: the pipeline puts back whatever a change touched outside its own
files, so two at once would each undo the other's. Undo and switching a mod off or on wait until Claude is done.

    Claude for the browser.bat                         the teacher password: the one this computer's Club Coders
                                                       app remembers, or typed in here (never on a command line)
    python helper/claude_helper.py --server ws://127.0.0.1:8779 --password-stdin    a laptop desk (tests)
    python helper/claude_helper.py --worker robotlab   one game's pipeline (the helper starts one for each game)
"""
import argparse
import asyncio
import getpass
import json
import os
import queue
import socket
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # club-coders/ (or the public repository)
CLUB_SERVER = "wss://play.clubcoders.co.uk"
GAMES = {"robotlab": ("Robot Lab", "shared-world-demo"), "fightlab": ("Fight Lab", "BeatEmUp"),
         "kartlab": ("Kart Lab", "kart"), "citylab": ("City Lab", "city")}  # each game: its name and its folder in the club's development repository
TEACHER_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders", "teacher.json")
TEXT = 4000  # (card fields are cut to this, as a learner's card is)


def game_dir(game):
    """A game's folder: games/<game> in the public repository, or its own folder in the development one. (A test
    puts a copy elsewhere: CLUBCODERS_<GAME>_DIR.)"""
    for d in (os.environ.get(f"CLUBCODERS_{game.upper()}_DIR"), os.path.join(ROOT, "games", game),
              os.path.join(ROOT, "..", GAMES[game][1])):
        if d and os.path.exists(os.path.join(d, "ai_pipeline.py")):
            return os.path.abspath(d)
    return None


# ---------- one game's pipeline, in its own process (each game's ai_pipeline sets up the engine's for itself) ----------
def worker(game):
    folder = game_dir(game)
    os.chdir(folder)
    sys.path.insert(0, folder)
    proto = open(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")  # (the helper reads this; prints go to stderr)
    sys.stdout = sys.stderr
    # the requests come on a copy of stdin; stdin itself becomes nothing. (On Windows a program started while this
    # waits to read its stdin would wait too: the change's test, which Claude's thread starts, never ran.)
    requests = open(os.dup(0), encoding="utf-8")
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
    if os.name == "nt":
        import ctypes
        import msvcrt
        ctypes.windll.kernel32.SetStdHandle(-10, msvcrt.get_osfhandle(0))  # (STD_INPUT_HANDLE: what children get)
    sys.stdin = open(os.devnull, encoding="utf-8")
    import ai_pipeline as P
    jobs = {}           # card id -> {"change", "status", "started", "result", "target", "learner"}
    line = []           # the card ids waiting for Claude, in order (the first is Claude's now)
    todo = queue.Queue()
    out = threading.Lock()

    def emit(msg):
        with out:
            proto.write(json.dumps(msg) + "\n")
            proto.flush()

    def busy():
        return next((cid for cid in line if jobs.get(cid, {}).get("status") == "Claude is working..."), None)

    def view():
        shown = {}
        for cid, j in jobs.items():
            first = line[0] if line else None
            status = j["status"] if j["status"] != "Waiting" else \
                "Waiting for Claude" if first in (None, cid) else f"Waiting: Claude is finishing card #{first} first"
            shown[str(cid)] = {"status": status, "started": j["started"], "target": j["target"],
                               "learner": j["learner"], "result": j["result"]}
        log = list(reversed(P.history()))
        return {"jobs": shown, "makers": P.user_mod_makers(), "targets": list(P._engine.TARGET_NAMES),
                "history": [{k: e.get(k) for k in ("n", "card", "learner", "goal", "target", "time", "files",
                                                    "status", "merged", "summary")} for e in log[:60]],
                "merged_count": sum(e["status"] == "merged" for e in log)}

    def claude():  # (one card at a time)
        while True:
            cid = todo.get()
            j = jobs.get(cid)
            if j is None or j["status"] != "Waiting":
                continue
            j["status"], j["started"] = "Claude is working...", time.time()
            emit({"event": "state", "state": view()})
            try:
                j["result"] = j["change"].run(progress=lambda m: None)
                j["status"] = "Check it"
            except Exception as e:  # (shown on the page, as the window shows it)
                j["result"] = {"summary": f"Something went wrong: {e}", "test_ok": False, "test": "", "files": [],
                               "blocked": []}
                j["status"] = "Failed"
            if cid in line:
                line.remove(cid)
            emit({"event": "state", "state": view()})

    threading.Thread(target=claude, daemon=True).start()

    def card_of(m):
        card = m.get("card") if isinstance(m.get("card"), dict) else {}
        return {k: (v[:TEXT] if isinstance(v, str) else v) for k, v in card.items()}

    def mods_of(files):
        mods = {}
        for rel in files:
            path = os.path.join(folder, rel)
            if rel.startswith("mods/") and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    mods[rel] = fh.read()
        return mods

    def files_wait(what):  # (undo and the mod switches change the game's files: not while Claude is at work)
        cid = busy()
        if cid is not None:
            raise ValueError(f"Wait until Claude has finished card #{cid}, then {what}.")

    def handle(m):
        do = m.get("do")
        if do == "state":
            return {}
        if do == "prompt":  # exactly what Send to Claude sends, for the teacher to read first
            target = str(m.get("target"))
            return {"prompt": P.build_prompt(card_of(m), str(m.get("learner", "")), target,
                                             P.allowed_files(target, str(m.get("learner", ""))),
                                             target == "game" and bool(m.get("as_user_mod", True))), "target": target}
        cid = int(m.get("id", 0)) if do in ("send", "keep", "undo", "clear") else None
        if do == "send":
            if cid in jobs and jobs[cid]["status"] in ("Waiting", "Claude is working...", "Check it"):
                raise ValueError(f"Card #{cid} is with Claude already.")
            target = str(m.get("target"))
            change = P.AIChange(cid, str(m.get("learner", "")), card_of(m), target,
                                design=m.get("design") if isinstance(m.get("design"), dict) else None,
                                as_user_mod=target == "game" and bool(m.get("as_user_mod", True)))
            jobs[cid] = {"change": change, "status": "Waiting", "started": time.time(), "result": None,
                         "target": target, "learner": change.learner}
            line.append(cid)
            todo.put(cid)
            print(f"Card #{cid} ({change.learner}, {target}) sent to Claude", flush=True)
            return {"queued": len(line)}
        if do in ("keep", "undo", "clear"):
            j = jobs.get(cid)
            if j is None:
                raise ValueError(f"Card #{cid} isn't with Claude on this computer (it may have been restarted).")
            if do == "clear":  # (send again: the old result goes)
                if j["status"] in ("Waiting", "Claude is working..."):
                    raise ValueError(f"Claude is still on card #{cid}.")
                if j["status"] == "Check it" and (j["result"] or {}).get("files"):
                    raise ValueError(f"Keep or Undo card #{cid}'s change first.")
                jobs.pop(cid)
                return {}
            if j["status"] != "Check it" or not (j["result"] or {}).get("files"):
                raise ValueError(f"Card #{cid} has nothing to {do}.")
            change = j["change"]
            if do == "undo":
                files_wait("press Undo")
                change.undo()
                j["status"] = "Undone"
                return {}
            change.keep()
            j["status"] = "Kept"
            print(f"Card #{cid} kept", flush=True)
            makers = P.user_mod_makers()
            return {"mods": {k: v for k, v in change.contents().items() if k.startswith("mods/")},
                    "engine": [f for f in j["result"]["files"] if not f.startswith("mods/")],
                    "makers": {k: makers[k] for k in change.user_mods if makers.get(k)}}
        n = int(m.get("n", 0)) if do in ("diff", "rollback", "reapply", "merge", "forget") else None
        if do == "diff":
            return {"n": n, "diff": P.change_diff(n)[:200000]}
        if do in ("rollback", "reapply"):
            files_wait("switch it " + ("off" if do == "rollback" else "on"))
            res = (P.rollback if do == "rollback" else P.reapply)(n)
            if not res["ok"]:
                return {"ok": False, "error": res["message"], "clashes": res.get("clashes", [])}
            return {"mods": mods_of(res["files"]),
                    "engine": [f for f in res["files"] if f.endswith(".py") and not f.startswith("mods/")]}
        if do == "merge":
            res = P.merge(n)
            if not res["ok"]:
                return {"ok": False, "error": res["message"]}
            makers = P.user_mod_makers()
            return {"makers": {k: makers[k] for k in res["user_mods"] if makers.get(k)}}
        if do == "forget":
            res = P.forget(n)
            return {} if res["ok"] else {"ok": False, "error": res["message"]}
        if do == "forget_makers":  # (a deleted learner's name came off their mods on the class server)
            P.forget_user_mod_makers([str(k) for k in m.get("keys", [])][:100])
            return {}
        raise ValueError(f"Claude for the browser doesn't know '{do}'.")

    emit({"event": "state", "state": view()})
    for raw in requests:
        try:
            m = json.loads(raw)
        except ValueError:
            continue
        try:
            reply = {"ok": True, **handle(m)}
        except Exception as e:  # (the page shows it)
            reply = {"ok": False, "error": str(e)[:500]}
        emit({"rid": m.get("rid"), **reply})
        emit({"event": "state", "state": view()})


# ---------- the helper: the desk on one side, a worker for each game on the other ----------
class Worker:
    def __init__(self, game, helper):
        self.game, self.helper = game, helper
        self.waiting = {}
        self.n = 0
        self.proc = None

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, os.path.abspath(__file__), "--worker", self.game, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, limit=8 * 1024 * 1024)
        asyncio.ensure_future(self.read())

    async def read(self):
        while True:
            raw = await self.proc.stdout.readline()
            if not raw:
                print(f"{GAMES[self.game][0]}'s pipeline stopped.", flush=True)
                for fut in self.waiting.values():
                    fut.set_result({"ok": False, "error": "Claude for the browser's pipeline for this game stopped."})
                self.waiting.clear()
                return
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if m.get("event") == "state":
                self.state = m["state"]
                await self.helper.tell({"type": "claude_state", "game": self.game, "state": m["state"]})
            elif m.get("rid") in self.waiting:
                self.waiting.pop(m["rid"]).set_result({k: v for k, v in m.items() if k != "rid"})

    async def ask(self, m):
        if self.proc.returncode is not None:
            return {"ok": False, "error": "Claude for the browser's pipeline for this game stopped: start it again."}
        self.n += 1
        fut = asyncio.get_running_loop().create_future()
        self.waiting[self.n] = fut
        self.proc.stdin.write((json.dumps({**m, "rid": self.n}) + "\n").encode("utf-8"))
        await self.proc.stdin.drain()
        return await fut


class Helper:
    def __init__(self, server, password, games):
        self.url = server.rstrip("/") + "/desk"
        self.password = password
        self.games = games
        self.workers = {g: Worker(g, self) for g in games}
        self.ws = None

    async def tell(self, msg):
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps(msg))
            except Exception:
                pass

    async def answer(self, req):
        w = self.workers.get(req.get("game"))
        if w is None:
            reply = {"ok": False, "error": f"Claude for the browser on {socket.gethostname()} doesn't have that game."}
        else:
            reply = await w.ask({k: v for k, v in req.items() if k not in ("rid", "game")})
        await self.tell({"type": "claude_reply", "rid": req.get("rid"), **reply})

    async def run(self):
        for w in self.workers.values():
            await w.start()
        try:
            return await self.connected()
        finally:  # (the games' pipelines end with it: their stdin closes)
            for w in self.workers.values():
                if w.proc.returncode is None:
                    w.proc.stdin.close()
                    try:
                        await asyncio.wait_for(w.proc.wait(), 5)
                    except asyncio.TimeoutError:
                        w.proc.kill()

    async def connected(self):
        import websockets
        tries = 0
        while True:
            try:
                async with websockets.connect(self.url, max_size=None, open_timeout=15) as ws:
                    await ws.send(json.dumps({"type": "teacher", "password": self.password}))
                    first = json.loads(await ws.recv())
                    if not first.get("ok"):
                        print(f"The desk said: {first.get('error', 'no')}", flush=True)
                        return 1
                    self.ws, tries = ws, 0
                    await ws.send(json.dumps({"type": "claude_helper", "games": self.games,
                                              "machine": socket.gethostname()}))
                    for w in self.workers.values():
                        if getattr(w, "state", None) is not None:
                            await self.tell({"type": "claude_state", "game": w.game, "state": w.state})
                    print(f"Connected to {self.url}: Claude is ready for the browser's AI cards "
                          f"({', '.join(GAMES[g][0] for g in self.games)}). Leave this window open.", flush=True)
                    async for raw in ws:
                        m = json.loads(raw)
                        if isinstance(m.get("claude_request"), dict):
                            asyncio.ensure_future(self.answer(m["claude_request"]))
                        elif m.get("claude_replaced"):
                            print("Claude for the browser was started on another computer: this one stops.", flush=True)
                            return 0
            except Exception as e:  # (Wi-Fi gone, the server restarting...)
                self.ws = None
                tries += 1
                wait = min(30, 2 * tries)
                print(f"Not connected to the desk ({e.__class__.__name__}): trying again in {wait} s...", flush=True)
                await asyncio.sleep(wait)
            finally:
                self.ws = None


def teacher_password(from_stdin):
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    try:
        with open(TEACHER_FILE, encoding="utf-8") as f:
            remembered = json.load(f).get("password", "")
        if remembered:
            print("Using the teacher password this computer's Club Coders app remembers.", flush=True)
            return remembered
    except (OSError, ValueError, AttributeError):
        pass
    return getpass.getpass("Teacher password (the one you log in to the Teacher screen with): ")


def main():
    ap = argparse.ArgumentParser(description="Claude for the browser: Club Coders Live's AI cards, on this computer")
    ap.add_argument("--server", default=CLUB_SERVER, help="the club's server (a laptop desk: ws://127.0.0.1:8779)")
    ap.add_argument("--password-stdin", action="store_true", help="read the teacher password from stdin (tests)")
    ap.add_argument("--games", help="only these games, e.g. kartlab,robotlab (default: every game folder here)")
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        return worker(args.worker)
    wanted = args.games.split(",") if args.games else list(GAMES)
    games = [g for g in GAMES if g in wanted and game_dir(g)]
    if not games:
        raise SystemExit("No game folders here: run this from the club's project folders (ClubCodersAI).")
    print("CLAUDE FOR THE BROWSER\nThe browser's AI cards go to Claude Code on this computer, with its own Claude login.",
          flush=True)
    password = teacher_password(args.password_stdin)
    if not password:
        raise SystemExit("No teacher password: nothing was done.")
    try:
        return asyncio.run(Helper(args.server, password, games).run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
