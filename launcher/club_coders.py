"""Club Coders: one download for all the club's games.

Learners type their class code once. The front door on the class server (door/club_door.py) says which game
their class is playing and where, and this app opens that game there, with the class code filled in: the game's
own login then asks for the username and password as usual. When the teacher moves a class to another game,
learners keep the same app and the same code.

    Club Coders.exe                          the downloaded app: this window
    Club Coders.exe --game robotlab ...      the app running one game (how this window starts a game)
    python launcher/club_coders.py           from the source files; "This computer (test)" opens a game on the
                                             laptop test servers (Robot Lab ws://127.0.0.1:8780, Fight Lab 8781)

Test options: --server ws://127.0.0.1:8779 (a laptop front door), --code X --go (no clicking), --wait (wait for
the game and exit with its result), and --offscreen / --screenshot / --after / --name / --password, which are
passed on to the game.
"""
import argparse
import json
import os
import queue
import runpy
import subprocess
import sys
import threading
import time
import traceback

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository (this file is in launcher/)
BUNDLE = getattr(sys, "_MEIPASS", ROOT)
CLUB_SERVER = "wss://play.clubcoders.co.uk"
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders")

# each game: its window's file, the environment variable it reopens itself with (see run_as_game), and its
# laptop test server. dev: its folder in the club's development repository (next to club-coders/).
GAMES = {
    "robotlab": {"title": "Robot Lab", "client": "lab_client.py", "login_env": "ROBOTLAB_LOGIN",
                 "local": "ws://127.0.0.1:8780", "dev": "shared-world-demo"},
    "fightlab": {"title": "Fight Lab", "client": "fight_client.py", "login_env": "FIGHTLAB_LOGIN",
                 "local": "ws://127.0.0.1:8781", "dev": "BeatEmUp"},
}
PASS_ON = ("--offscreen", "--screenshot", "--after", "--name", "--password", "--gfx")


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def remember(key, value):
    """Keep a setting (the class code, where to play) on this computer."""
    path = os.path.join(SETTINGS_DIR, "settings.json")
    data = load_json(path) | {key: value}
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def release_config():
    """The downloaded app's settings (the class server's address and the version), made by the release build."""
    return load_json(os.path.join(BUNDLE, "release_config.json")) if FROZEN else {}


def game_dir(game):
    """Where a game's files are: inside the downloaded app, in the public repository, or in the club's own
    development folders."""
    for d in (os.path.join(BUNDLE, "games", game), os.path.join(ROOT, "games", game),
              os.path.join(ROOT, "..", GAMES[game]["dev"])):
        if os.path.exists(os.path.join(d, GAMES[game]["client"])):
            return os.path.abspath(d)
    raise SystemExit(f"{GAMES[game]['title']} isn't in this copy of Club Coders.")


# ---------- running a game ----------
def which_game(argv):
    """In the downloaded app, is this process meant to run a game? (game, its arguments) or (None, None).
    A game started by this window gets --game; a game reopening itself (to load new code, or when the teacher
    reopens everyone's windows) runs this same program again, and carries its login in its own variable."""
    if not FROZEN:
        return None, None
    if len(argv) >= 2 and argv[0] == "--game" and argv[1] in GAMES:
        return argv[1], argv[2:]
    for game, g in GAMES.items():
        if os.environ.get(g["login_env"]):
            return game, argv
    return None, None


def run_as_game(game, argv):
    """Become the game: its folder goes first on the import path and its window's file runs as the program."""
    sys.dont_write_bytecode = True  # (the app's folder may be read-only)
    folder = game_dir(game)
    script = os.path.join(folder, GAMES[game]["client"])
    sys.path.insert(0, folder)
    sys.argv = [script] + list(argv)
    runpy.run_path(script, run_name="__main__")


def start_game(game, argv, wait=False):
    """Open a game in its own window (its own process, so each game has its own files and settings)."""
    if FROZEN:
        cmd, cwd = [sys.executable, "--game", game] + argv, os.path.dirname(sys.executable)
    else:
        folder = game_dir(game)
        python = os.path.join(folder, ".venv", "Scripts", "python.exe")
        cmd, cwd = [python if os.path.exists(python) else sys.executable, GAMES[game]["client"]] + argv, folder
    shown = ["***" if i and argv[i - 1] == "--password" else a for i, a in enumerate(argv)]  # (never log a password)
    print(f"Opening {GAMES[game]['title']}: {' '.join(shown)}", flush=True)
    flags = 0 if wait else getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(cmd, cwd=cwd, creationflags=flags)
    return proc.wait() if wait else 0


def ask_door(server, code, timeout=8.0):
    """Ask the club's front door which game and address this class code is for: the door's answer as a dict."""
    from websockets.sync.client import connect
    try:
        with connect(server.rstrip("/") + "/door", open_timeout=timeout, close_timeout=2, max_size=4096) as ws:
            ws.send(json.dumps({"type": "find", "code": code}))
            answer = json.loads(ws.recv(timeout=timeout))
    except Exception:
        return {"ok": False, "error": "Can't reach the club's server. Check your internet connection, then try "
                                      "again."}
    if answer.get("ok") and (answer.get("game") not in GAMES or
                             not str(answer.get("address", "")).startswith(("wss://", "ws://"))):
        return {"ok": False, "error": "The club's server gave an answer this app doesn't understand: download the "
                                      "newest Club Coders."}
    return answer


# ---------- the window ----------
def launcher(args, passed_on):
    from panda3d.core import loadPrcFileData
    loadPrcFileData("", "win-size 960 600\nwindow-title Club Coders\nframebuffer-multisample 1\nmultisamples 4\n")
    if args.offscreen:
        loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")
    from direct.gui.DirectGui import DGG, DirectButton, DirectEntry, DirectFrame
    from direct.gui.OnscreenText import OnscreenText
    from direct.showbase.ShowBase import ShowBase
    from panda3d.core import Filename, TextNode

    yellow, white, grey, red, green = (1, .9, .35, 1), (1, 1, 1, 1), (.75, .8, .9, 1), (1, .45, .4, 1), (.5, .95, .55, 1)
    on, off = (0.85, 0.65, 0.1, 1), (0.2, 0.25, 0.35, 1)
    server = args.server or release_config().get("server") or CLUB_SERVER
    version = release_config().get("version", "source files")
    saved = load_json(os.path.join(SETTINGS_DIR, "settings.json"))

    def label(parent, text, x, y, scale=0.05, fg=white, align=TextNode.ACenter, wrap=None):
        return OnscreenText(text, pos=(x, y), scale=scale, fg=fg, align=align, parent=parent, mayChange=True,
                            wordwrap=wrap)

    def button(parent, text, x, y, command, extra=(), scale=0.06, colour=off):
        return DirectButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), command=command,
                            extraArgs=list(extra), frameColor=colour, text_fg=white, relief=DGG.FLAT, pad=(0.5, 0.25))

    class Launcher(ShowBase):
        def __init__(self):
            super().__init__()
            self.setBackgroundColor(0.05, 0.06, 0.09)
            if args.code or args.server:  # (given a code or a server to ask: that's the online class)
                self.local = False
            else:
                self.local = (saved.get("where") == "local") if "where" in saved else not FROZEN
            self.results = queue.Queue()
            self.busy = False
            self.panel = None
            self.code_entry = None
            self.draw()
            self.taskMgr.add(self.check_results, "results")
            if args.go:
                self.taskMgr.doMethodLater(0.5, lambda t: self.go(), "go")

        def draw(self, message="", colour=grey):
            typed = self.code_entry.get() if self.code_entry is not None else (args.code or saved.get("class_code", ""))
            if self.panel is not None:
                self.panel.destroy()
            self.panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))  # backdrop
            f = DirectFrame(parent=self.panel, frameColor=(0.08, 0.1, 0.15, 1), frameSize=(-0.95, 0.95, -0.72, 0.72))
            label(f, "CLUB CODERS", 0, 0.52, 0.11, yellow)
            label(f, "The club's games: type your class code and your class's game opens", 0, 0.42, 0.04, grey)
            label(f, "Play on", -0.62, 0.26, 0.045, grey)
            for i, (local, text) in enumerate(((False, "Online class"), (True, "This computer (test)"))):
                button(f, text, -0.14 + i * 0.5, 0.265, self.set_where, [local], 0.045, on if self.local == local else off)
            self.code_entry = None
            if self.local:
                label(f, "Open a game on this computer's test server:", 0, 0.08, 0.045)
                for i, (game, g) in enumerate(GAMES.items()):
                    button(f, g["title"], -0.3 + i * 0.6, -0.08, self.open_local, [game], 0.075, (0.15, 0.45, 0.65, 1))
            else:
                label(f, "Class code", -0.52, 0.06, 0.055)
                self.code_entry = DirectEntry(parent=f, scale=0.06, pos=(-0.25, 0, 0.06), width=11, initialText=typed,
                                              numLines=1, focus=1, command=lambda t: self.go(),
                                              frameColor=(0.12, 0.14, 0.2, 1), text_fg=white)
                button(f, "GO", 0, -0.14, self.go, (), 0.08, (0.15, 0.55, 0.25, 1))
                label(f, "It's in your welcome letter, and it's remembered after the first time.", 0, -0.3, 0.035, grey)
            label(f, message, 0, -0.45, 0.042, colour, wrap=40)
            label(f, f"Club Coders {version}", 0.9, -0.68, 0.03, grey, TextNode.ARight)

        def set_where(self, local):
            self.local = local
            remember("where", "local" if local else "online")
            self.draw()

        def open_local(self, game):
            start_game(game, ["--host", GAMES[game]["local"]] + passed_on, wait=args.wait)
            self.finish()

        def go(self):
            if self.busy or self.code_entry is None:
                return
            code = self.code_entry.get().strip()
            if not code:
                return self.draw("Type the class code from your welcome letter.", red)
            self.busy = True
            self.draw("Finding your class...", grey)
            threading.Thread(target=lambda: self.results.put((code, ask_door(server, code))), daemon=True).start()

        def check_results(self, task):
            try:
                code, answer = self.results.get_nowait()
            except queue.Empty:
                return task.cont
            self.busy = False
            if not answer.get("ok"):
                self.draw(answer.get("error", "Something went wrong: try again."), red)
                if args.go and args.offscreen:  # (a test with no one to read it: show it, then stop)
                    self.finish(1)
                return task.cont
            remember("class_code", code)
            game = answer["game"]
            self.draw(f"Opening {GAMES[game]['title']}...", green)
            self.graphicsEngine.renderFrame()
            result = start_game(game, ["--host", answer["address"], "--code", code] + passed_on, wait=args.wait)
            self.finish(result)
            return task.done

        def finish(self, result=0):
            if args.screenshot_launcher:
                self.graphicsEngine.renderFrame()
                self.win.saveScreenshot(Filename.fromOsSpecific(args.screenshot_launcher))
            self.exit_code = result
            self.taskMgr.doMethodLater(0.2 if args.wait else 1.5, lambda t: self.userExit(), "bye")

    app = Launcher()
    try:
        app.run()
    except SystemExit:
        pass
    return getattr(app, "exit_code", 0)


def log_to_file():
    """The downloaded app has no console: what it prints (and any error) goes to club-coders.log in its settings
    folder, which the teacher can ask for if something goes wrong on a learner's computer."""
    if FROZEN and sys.stderr is None:
        try:
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            sys.stdout = sys.stderr = open(os.path.join(SETTINGS_DIR, "club-coders.log"), "a", encoding="utf-8",
                                           buffering=1)
            print(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(sys.argv[1:3])}")
        except OSError:
            pass


def main():
    log_to_file()
    try:
        _main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        if "--offscreen" in sys.argv:  # (a test: stop, rather than wait for someone to close an error box)
            sys.stdout.flush()
            os._exit(1)
        raise


def _main():
    game, argv = which_game(sys.argv[1:])
    if game:
        return run_as_game(game, argv)
    ap = argparse.ArgumentParser(description="Club Coders: opens your class's game.", allow_abbrev=False)
    ap.add_argument("--server", help=f"the club's server (default: {CLUB_SERVER})")
    ap.add_argument("--code", help="class code (normally typed in the window)")
    ap.add_argument("--go", action="store_true", help="look the code up straight away")
    ap.add_argument("--wait", action="store_true", help="wait for the game, then exit with its result (tests)")
    ap.add_argument("--screenshot-launcher", help="save a picture of this window before it closes (tests)")
    ap.add_argument("--offscreen", action="store_true")
    args, rest = ap.parse_known_args()
    passed_on, i = [], 0
    rest = (["--offscreen"] if args.offscreen else []) + rest
    while i < len(rest):  # only the options the games understand are passed on
        if rest[i] in PASS_ON:
            takes_value = rest[i] != "--offscreen"
            passed_on += rest[i:i + 1 + takes_value]
            i += 1 + takes_value
        else:
            i += 1
    sys.exit(launcher(args, passed_on))


if __name__ == "__main__":
    main()
