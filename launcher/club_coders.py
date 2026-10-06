"""Club Coders: one download for all the club's games.

Learners log in with their username and password. The club desk on the class server (desk/club_desk.py) checks
them and says which game their launched group is playing and where; this app opens that game there, already
logged in (a signed ticket). If their group hasn't been launched, the app waits and opens the game the moment it
is. A starter password works once: the learner chooses their own first.

The teacher logs in with the teacher password and gets the teacher desk: learners (add, reset a password,
remove), groups (name, game, learners) and Launch / Stop. Launch opens the teacher window in that game.

    Club Coders.exe                          the downloaded app: this window
    Club Coders.exe --game robotlab ...      the app running one game (how this window starts a game)
    python launcher/club_coders.py           from the source files; "This computer (test)" opens a game on the
                                             laptop test servers (Robot Lab ws://127.0.0.1:8780, Fight Lab 8781)

Live updates: the teacher can put new game code on the class server without a new download (live/make_live.py).
A class running one says which (its id). The app downloads it once from https://<server>/code/<game>/<id>.zip and
.sig, and before every use checks (live/live_format.py) that the teacher's key signed exactly that update of that
game (the key's public half is built into the app), and that it unpacks safely. Anything that fails a check isn't
run: the game runs the app's own code instead, and says it doesn't match the class.

Test options: --server ws://127.0.0.1:8779 (a laptop desk), --login USER PASS or --teacher-password X (no
clicking), --wait (wait for the game and exit with its result), and --offscreen / --screenshot / --after / --name /
--password, which are passed on to the game.
"""
import argparse
import hashlib
import json
import os
import queue
import re
import runpy
import shutil
import subprocess
import sys
import urllib.request
import threading
import time
import traceback
import webbrowser

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # the repository (this file is in launcher/)
if not FROZEN:
    sys.path.insert(0, os.path.join(ROOT, "live"))
import live_format  # noqa: E402  (the checks on live updates, shared with the server and the teacher's tool)
BUNDLE = getattr(sys, "_MEIPASS", ROOT)
CLUB_SERVER = "wss://play.clubcoders.co.uk"
MIN_TEACHER_PASSWORD = 12  # (the desk's rule for the teacher's own password: checked here too, to say so at once)
GITHUB_REPO = "Peter-RobotCoder/robot-lab"  # where the app's releases are
DOWNLOAD_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders")
LIVE_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or SETTINGS_DIR, "ClubCoders", "live")  # live updates

# each game: its window's file, the environment variable it reopens itself with (see run_as_game), and its
# laptop test server. dev: its folder in the club's development repository (next to club-coders/).
GAMES = {
    "robotlab": {"title": "Robot Lab", "client": "lab_client.py", "login_env": "ROBOTLAB_LOGIN",
                 "reopen_env": "ROBOTLAB_REOPENED",
                 "local": "ws://127.0.0.1:8780", "dev": "shared-world-demo"},
    "fightlab": {"title": "Fight Lab", "client": "fight_client.py", "login_env": "FIGHTLAB_LOGIN",
                 "reopen_env": "FIGHTLAB_REOPENED",
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


def newer_release(mine, timeout=5):
    """The newest release's version if it is newer than this app's (mine, "1.4.2"), else None: also None if GitHub
    can't be reached, or this isn't a downloaded app (the source files have no version number)."""
    def parse(v):
        try:
            return tuple(int(x) for x in str(v).lstrip("v").split("."))
        except ValueError:
            return None
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "ClubCoders"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            tag = str(json.load(r).get("tag_name", ""))
    except Exception:
        return None
    latest, mine = parse(tag), parse(mine)
    return tag.lstrip("v") if latest and mine and latest > mine else None


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


# ---------- live updates ----------
def engine_home(folder):
    """The folder holding engine/ for a game's folder (the game's version file searches the same way)."""
    for up in (0, 1, 2, 3):
        candidate = os.path.abspath(os.path.join(folder, *([".."] * up)))
        if os.path.isdir(os.path.join(candidate, "engine")):
            return candidate
    return folder


def release_code_id(folder):
    """The code the app came with: the same fingerprint the game's own version file makes (its CODE): the game's
    Python files and the engine's."""
    h = hashlib.sha1()
    engine = os.path.join(engine_home(folder), "engine")
    for where, prefix in ((folder, ""), (engine, "engine/")):
        for name in sorted(os.listdir(where)) if os.path.isdir(where) else []:
            if name.endswith(".py"):
                h.update((prefix + name).encode())
                with open(os.path.join(where, name), "rb") as f:
                    h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


def test_build():
    """The club's own test builds (made without a release tag) and the source files take test servers on this
    laptop (ws://, CLUBCODERS_CODE_URL). The released app only ever talks to the club's server over wss/https."""
    return not FROZEN or bool(release_config().get("test_build"))


def code_url(address):
    """Where a class server's live updates are: https://<its host>/code. (Test builds can be pointed at a laptop
    test server with CLUBCODERS_CODE_URL; every update is checked the same way wherever it came from.)"""
    if os.environ.get("CLUBCODERS_CODE_URL") and test_build():
        return os.environ["CLUBCODERS_CODE_URL"].rstrip("/")
    host = address.split("://", 1)[-1].split("/", 1)[0]
    return f"https://{host}/code"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ClubCoders"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(live_format.MAX_ZIP + 1)
    if len(data) > live_format.MAX_ZIP:
        raise live_format.LiveError("the update is too big to be a code update")
    return data


def remove_folder(folder):
    """Delete a live update's folder, taking its links out first (so nothing they point at is touched)."""
    for p in live_format.link_paths(folder):
        if os.path.isjunction(p) or os.path.islink(p):
            os.rmdir(p) if os.path.isjunction(p) else os.unlink(p)
    shutil.rmtree(folder, ignore_errors=True)


def link_big_files(folder, bundled):
    """The update uses the app's own textures, sounds, models, mods and brains, and the engine's made textures and
    sounds (links, remade if the app moved)."""
    import _winapi
    pairs = [(os.path.join(bundled, d), os.path.join(folder, d)) for d in live_format.LINK_DIRS]
    if os.path.isdir(os.path.join(folder, "engine")):  # (the update carries the engine's code: its assets are the app's)
        pairs.append((os.path.join(engine_home(bundled), "engine", "assets"), os.path.join(folder, "engine", "assets")))
    for target, link in pairs:
        d = os.path.relpath(link, folder)
        if not os.path.isdir(target):
            continue
        if os.path.isjunction(link) and os.path.realpath(link) == os.path.realpath(target):
            continue
        if os.path.isjunction(link) or os.path.islink(link):
            os.rmdir(link) if os.path.isjunction(link) else os.unlink(link)
        elif os.path.exists(link):
            raise live_format.LiveError(f"{d} in the live update's folder isn't a link")
        _winapi.CreateJunction(target, link)


def live_code(game, address, wanted):
    """The folder with the class's live update, checked (and downloaded the first time), or None when the class runs
    the code that came with this app. Raises LiveError if it can't be used safely."""
    bundled = game_dir(game)
    if not wanted or wanted == release_code_id(bundled):
        return None
    if not re.fullmatch(live_format.ID_PATTERN, wanted):
        raise live_format.LiveError(f"'{wanted}' isn't a live update's id")
    key, version = release_config().get("live_key"), release_config().get("version")
    if not key:
        raise live_format.LiveError("this copy of the app doesn't take live updates: download the newest Club Coders")
    store = os.path.join(LIVE_DIR, game)
    os.makedirs(store, exist_ok=True)
    zip_path, sig_path, folder = (os.path.join(store, wanted + ".zip"), os.path.join(store, wanted + ".sig"),
                                  os.path.join(store, wanted))
    saved = os.path.exists(zip_path) and os.path.exists(sig_path)
    if saved:
        with open(zip_path, "rb") as f:
            data = f.read()
        with open(sig_path, "rb") as f:
            signature = f.read()
        try:
            live_format.check_signature(key, game, wanted, version, data, signature)  # (a saved copy: every time)
        except live_format.LiveError:  # damaged on this computer: fetched once more (and checked again)
            for path in (zip_path, sig_path):
                os.remove(path)
            saved = False
    if not saved:
        base = code_url(address)
        data, signature = fetch(f"{base}/{game}/{wanted}.zip"), fetch(f"{base}/{game}/{wanted}.sig")
        live_format.check_signature(key, game, wanted, version, data, signature)
        for path, content in ((zip_path, data), (sig_path, signature)):
            with open(path + ".part", "wb") as f:
                f.write(content)
            os.replace(path + ".part", path)
    if not os.path.isdir(folder) or live_format.content_id(folder) != wanted:
        part = folder + ".part"
        remove_folder(part)
        live_format.safe_unpack(data, part)
        with open(os.path.join(part, "LIVE_ID"), encoding="utf-8") as f:
            marked = f.read().strip()
        if live_format.content_id(part) != wanted or marked != wanted:
            remove_folder(part)
            raise live_format.LiveError("the update's files aren't the update that was signed")
        remove_folder(folder)
        os.replace(part, folder)
    link_big_files(folder, bundled)
    return folder


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
    """Become the game: its folder goes first on the import path and its window's file runs as the program.
    The class's code is the app's own, or a checked live update: the one the front door named (CLUBCODERS_CODE),
    or the one the class server asked a window to reopen with (the game's REOPENED variable)."""
    sys.dont_write_bytecode = True  # (the app's folder may be read-only)
    import tempfile
    sys.pycache_prefix = tempfile.mkdtemp(prefix="clubcoders_pyc_")  # (so no compiled file in a game's folder runs)
    folder = game_dir(game)
    wanted = os.environ.pop("CLUBCODERS_CODE", None) or os.environ.get(GAMES[game]["reopen_env"])
    address = argv[argv.index("--host") + 1] if "--host" in argv[:-1] else ""
    if wanted and address:
        try:
            live = live_code(game, address, wanted)
            if live:
                folder = live
                print(f"Using live update {wanted} of {GAMES[game]['title']}", flush=True)
        except Exception as e:  # (not used: the game runs the app's own code, and says it doesn't match the class)
            print(f"Live update {wanted} not used: {e}", flush=True)
    script = os.path.join(folder, GAMES[game]["client"])
    sys.path.insert(0, folder)
    sys.argv = [script] + list(argv)
    runpy.run_path(script, run_name="__main__")


def start_game(game, argv, wait=False, code=None):
    """Open a game in its own window (its own process, so each game has its own files and settings). code: the
    code the class runs, from the front door (a live update is checked before it's used)."""
    if FROZEN:
        cmd, cwd = [sys.executable, "--game", game] + argv, os.path.dirname(sys.executable)
    else:
        folder = game_dir(game)
        python = os.path.join(folder, ".venv", "Scripts", "python.exe")
        cmd, cwd = [python if os.path.exists(python) else sys.executable, GAMES[game]["client"]] + argv, folder
    shown = ["***" if i and argv[i - 1] == "--password" else a for i, a in enumerate(argv)]  # (never log a password)
    print(f"Opening {GAMES[game]['title']}: {' '.join(shown)}", flush=True)
    flags = 0 if wait else getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    env = dict(os.environ, CLUBCODERS_CODE=code) if code else None
    proc = subprocess.Popen(cmd, cwd=cwd, creationflags=flags, env=env)
    return proc.wait() if wait else proc


# ---------- the club desk connection ----------
class DeskLink:
    """A connection to the club desk, kept open: what the desk sends arrives in a queue the window reads each frame."""

    def __init__(self, server):
        self.url = server.rstrip("/") + "/desk"
        self.inbox = queue.Queue()
        self.ws = None
        self.open = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        from websockets.sync.client import connect
        try:
            with connect(self.url, open_timeout=10, close_timeout=2, max_size=64 * 1024) as ws:
                self.ws, self.open = ws, True
                self.inbox.put({"_open": True})
                while True:
                    self.inbox.put(json.loads(ws.recv()))
        except Exception as e:
            self.open = False
            self.inbox.put({"_closed": True, "_why": str(e)})

    def send(self, msg):
        try:
            self.ws.send(json.dumps(msg))
            return True
        except Exception:
            return False

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def esc_text(text):
    return str(text)


def address_ok(address):
    secure = ("wss://", "ws://") if test_build() else ("wss://",)
    return isinstance(address, str) and address.startswith(secure)


# ---------- the window ----------
def launcher(args, passed_on):
    from panda3d.core import loadPrcFileData
    loadPrcFileData("", "win-size 1100 700\nwindow-title Club Coders\nframebuffer-multisample 1\nmultisamples 4\n")
    if args.offscreen:
        loadPrcFileData("", "window-type offscreen\naudio-library-name null\n")
    from direct.gui.DirectGui import DGG, DirectButton, DirectCheckButton, DirectEntry, DirectFrame
    from direct.gui.OnscreenText import OnscreenText
    from direct.showbase.ShowBase import ShowBase
    from panda3d.core import Filename, TextNode, WindowProperties

    yellow, white, grey, red, green = (1, .9, .35, 1), (1, 1, 1, 1), (.75, .8, .9, 1), (1, .45, .4, 1), (.5, .95, .55, 1)
    blue = (.55, .85, 1, 1)
    on, off, go_col, warn_col = (0.85, 0.65, 0.1, 1), (0.2, 0.25, 0.35, 1), (0.15, 0.55, 0.25, 1), (0.6, 0.2, 0.15, 1)
    server = args.server or release_config().get("server") or CLUB_SERVER
    version = release_config().get("version", "source files")
    saved = load_json(os.path.join(SETTINGS_DIR, "settings.json"))
    teacher_file = os.path.join(SETTINGS_DIR, "teacher.json")

    def label(parent, text, x, y, scale=0.045, fg=white, align=TextNode.ACenter, wrap=None):
        return OnscreenText(text, pos=(x, y), scale=scale, fg=fg, align=align, parent=parent, mayChange=True,
                            wordwrap=wrap)

    def button(parent, text, x, y, command, extra=(), scale=0.05, colour=off):
        return DirectButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), command=command,
                            extraArgs=list(extra), frameColor=colour, text_fg=white, relief=DGG.FLAT, pad=(0.5, 0.25))

    def entry(parent, x, y, width, initial="", secret=False, scale=0.05, command=None):
        return DirectEntry(parent=parent, scale=scale, pos=(x, 0, y), width=width, initialText=initial, numLines=1,
                           obscured=1 if secret else 0, frameColor=(0.12, 0.14, 0.2, 1), text_fg=white,
                           command=command)

    def check(parent, text, x, y, value, command, scale=0.04):
        return DirectCheckButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), indicatorValue=1 if value else 0,
                                 command=command, text_align=TextNode.ALeft, text_fg=white, frameColor=(0, 0, 0, 0),
                                 boxPlacement="left")

    class Launcher(ShowBase):
        def __init__(self):
            super().__init__()
            self.setBackgroundColor(0.05, 0.06, 0.09)
            self.local = (saved.get("where") == "local") if "where" in saved else not FROZEN
            if args.login or args.teacher_password:
                self.local = False
            self.link = None
            self.panel = None
            self.screen = "home"
            self.message = ("", grey)
            self.me = None            # the learner's username once the desk knows them
            self.password = ""        # (kept only until the game opens: a starter password change needs it)
            self.state = {}           # the desk's state, for the teacher screen
            self.editing = None       # the group being edited on the teacher screen
            self.trying_password = None  # a teacher password sent to the desk, not yet accepted
            self.new_teacher_password = None  # a new teacher password sent to the desk, not yet accepted
            self.newer, self.newer_shown = args.test_newer, False  # a newer release of the app is out (its version)
            if FROZEN:  # (asked in the background: the window doesn't wait for GitHub)
                threading.Thread(target=lambda: setattr(self, "newer", newer_release(version)), daemon=True).start()
            if args.test_screen:
                self.screen = args.test_screen
            self.teacher_proc = None  # the teacher's game window, while the app has one open
            self.game_proc = None     # a learner's game window, while it is open (the app waits behind it)
            self.game_title, self.live_id, self.came_back = "", None, False
            self.teacher_view = "session"  # while a group is live: "session" or "desk" (learners and groups)
            self.pending_record = None  # a session just stopped, waiting for "make the PDFs?"
            self.sessions = []        # past sessions' records, from the desk
            self.page = 0
            self.fields = {}
            self.draw()
            self.taskMgr.add(self.read_desk, "desk")
            if args.snap:  # (tests: a picture of this window after a few seconds, then close)
                self.taskMgr.doMethodLater(args.snap, lambda t: self.finish(), "snap")
            if args.login:
                self.taskMgr.doMethodLater(0.5, lambda t: self.log_in(*args.login), "auto")
            elif args.teacher_password:
                self.taskMgr.doMethodLater(0.5, lambda t: self.teacher_login(args.teacher_password), "auto")
                if args.test_stop:  # (tests: stop the live group and make its PDFs, then close)
                    self.taskMgr.doMethodLater(3, lambda t: self.stop(), "test_stop")

        # ---------- drawing ----------
        def say(self, text, colour=grey):
            self.message = (text, colour)
            self.draw()

        def field(self, key):
            e = self.fields.get(key)
            return e.get().strip() if e is not None else ""

        def draw(self):
            keep = {k: e.get() for k, e in self.fields.items()}
            if self.panel is not None:
                self.panel.destroy()
            self.fields = {}
            self.panel = DirectFrame(frameColor=(0.05, 0.06, 0.09, 1), frameSize=(-3, 3, -1.2, 1.2))
            f = DirectFrame(parent=self.panel, frameColor=(0.08, 0.1, 0.15, 1), frameSize=(-1.5, 1.5, -0.92, 0.92))
            getattr(self, "draw_" + self.screen)(f, keep)
            label(f, self.message[0], 0, -0.8, 0.04, self.message[1], wrap=60)
            label(f, f"Club Coders {version}", 1.46, -0.89, 0.028, grey, TextNode.ARight)

        def draw_home(self, f, keep):
            label(f, "CLUB CODERS", 0, 0.7, 0.11, yellow)
            label(f, "Play on", -0.62, 0.5, 0.04, grey)
            for i, (local, text) in enumerate(((False, "Online class"), (True, "This computer (test)"))):
                button(f, text, -0.2 + i * 0.5, 0.505, self.set_where, [local], 0.042, on if self.local == local else off)
            if self.local:
                label(f, "Open a game on this computer's test server:", 0, 0.25, 0.045)
                for i, (game, g) in enumerate(GAMES.items()):
                    button(f, g["title"], -0.3 + i * 0.6, 0.08, self.open_local, [game], 0.07, (0.15, 0.45, 0.65, 1))
            else:
                label(f, "Username", -0.55, 0.27, 0.05)
                self.fields["user"] = entry(f, -0.25, 0.27, 12, keep.get("user", saved.get("username", "")),
                                            command=lambda t: self.fields["pass"].setFocus())
                label(f, "Password", -0.55, 0.12, 0.05)
                self.fields["pass"] = entry(f, -0.25, 0.12, 12, keep.get("pass", ""), secret=True,
                                            command=lambda t: self.log_in())
                button(f, "LOG IN", 0, -0.08, self.log_in, (), 0.07, go_col)
                label(f, "Use the username and password from your welcome letter. Your class's game opens by itself.",
                      0, -0.25, 0.033, grey, wrap=55)
            button(f, "Teacher", 1.3, -0.72, self.show, ["teacher_login"], 0.035)
            if self.newer:  # this app is out of date: say so here, before anyone logs in, with the way to the new one
                self.newer_shown = True
                label(f, f"Club Coders {self.newer} is out. This is {version}: download the new one to play with "
                         "your class.", 0, -0.43, 0.04, yellow, wrap=50)
                button(f, "Download the new Club Coders", 0, -0.58, webbrowser.open, [DOWNLOAD_PAGE], 0.045, go_col)
            if "user" in self.fields and not keep.get("user"):
                self.fields["user"].setFocus()

        def draw_change_password(self, f, keep):
            label(f, "CHOOSE YOUR OWN PASSWORD", 0, 0.6, 0.07, yellow)
            label(f, f"Hello {self.me}. Your starter password only works once: choose your own now (at least 6 "
                     "characters). Keep it to yourself.", 0, 0.42, 0.036, grey, wrap=50)
            label(f, "New password", -0.6, 0.15, 0.05)
            self.fields["new1"] = entry(f, -0.2, 0.15, 12, keep.get("new1", ""), secret=True,
                                        command=lambda t: self.fields["new2"].setFocus())
            label(f, "Type it again", -0.6, 0.0, 0.05)
            self.fields["new2"] = entry(f, -0.2, 0.0, 12, keep.get("new2", ""), secret=True,
                                        command=lambda t: self.change_password())
            button(f, "SAVE MY PASSWORD", 0, -0.22, self.change_password, (), 0.06, go_col)

        def draw_waiting(self, f, keep):
            label(f, "NOT STARTED YET" if not self.came_back else "WAITING FOR THE NEXT GAME", 0, 0.55, 0.08, yellow)
            label(f, (f"Hello {self.me}. Your group hasn't started yet: wait for your teacher.\n"
                      "The game will open by itself as soon as it does.") if not self.came_back else
                     (f"The game has closed. You're still logged in, {self.me}: when your teacher starts the "
                      "next game it will open by itself.\nClose this window to leave."),
                  0, 0.25, 0.045, white, wrap=45)
            button(f, "Log out", 0, -0.3, self.log_out, (), 0.045)

        def draw_playing(self, f, keep):
            label(f, "PLAYING", 0, 0.55, 0.08, yellow)
            label(f, f"{self.game_title} is open in its own window.\nWhen it closes you come back here, still "
                     "logged in, ready for the next game.", 0, 0.25, 0.045, white, wrap=45)

        # ---------- the game, while it is open (CHANGE 54) ----------
        def minimised(self, on):
            """The app's window out of the way while the game is open, and back in front when the game closes."""
            if args.offscreen:
                return
            props = WindowProperties()
            props.setMinimized(on)
            if not on:
                props.setForeground(True)
            self.win.requestProperties(props)

        def watch_game(self, task):
            if self.game_proc is None:
                return task.done
            if self.game_proc.poll() is None:
                return task.cont
            self.game_proc = None  # the game window closed: the teacher stopped it, or the learner closed it
            self.came_back = True
            self.minimised(False)
            if self.link is not None and self.link.open:
                self.show("waiting")
                self.ask_desk({"type": "wait", "after": self.live_id})  # (the desk's next launch reaches this app)
            else:  # (the desk connection went while the game was open: once logged in again, the next game opens)
                self.show("home")
                self.say("The game has closed. Log in again, and the next game will open by itself.", grey)
            return task.done

        def draw_teacher_login(self, f, keep):
            label(f, "TEACHER", 0, 0.6, 0.09, yellow)
            label(f, "Teacher password", -0.62, 0.25, 0.05)
            label(f, "(the password you chose; or, until you choose one, the teacher code the server setup printed)",
                  0, 0.42, 0.035, grey)
            remembered = load_json(teacher_file).get("password", "")
            self.fields["tpass"] = entry(f, -0.2, 0.25, 14, keep.get("tpass", remembered), secret=True,
                                         command=lambda t: self.teacher_login())
            self.remember_teacher = check(f, " Remember it on this computer", -0.62, 0.1,
                                          bool(remembered) or getattr(self, "_remember", True),
                                          lambda v: setattr(self, "_remember", bool(v)))
            button(f, "LOG IN", 0, -0.1, self.teacher_login, (), 0.07, go_col)
            button(f, "Change teacher password", 0.75, -0.1, self.show, ["teacher_password"], 0.04)
            button(f, "Back", -1.3, -0.72, self.show, ["home"], 0.035)
            self.fields["tpass"].setFocus()

        def draw_teacher_password(self, f, keep):
            label(f, "CHANGE THE TEACHER PASSWORD", 0, 0.62, 0.075, yellow)
            label(f, f"Choose one you'll remember: at least {MIN_TEACHER_PASSWORD} characters (three words is good). "
                     "Once it is changed, only the new password opens the Teacher screen: the old one, and the "
                     "server's teacher code, stop working.", 0, 0.47, 0.034, grey, wrap=62)
            remembered = load_json(teacher_file).get("password", "")
            label(f, "Password now", -0.62, 0.2, 0.05)
            self.fields["tnow"] = entry(f, -0.2, 0.2, 16, keep.get("tnow", keep.get("tpass", remembered)), secret=True,
                                        command=lambda t: self.fields["tnew1"].setFocus())
            label(f, "New password", -0.62, 0.06, 0.05)
            self.fields["tnew1"] = entry(f, -0.2, 0.06, 16, keep.get("tnew1", ""), secret=True,
                                         command=lambda t: self.fields["tnew2"].setFocus())
            label(f, "Type it again", -0.62, -0.08, 0.05)
            self.fields["tnew2"] = entry(f, -0.2, -0.08, 16, keep.get("tnew2", ""), secret=True,
                                         command=lambda t: self.change_teacher_password())
            button(f, "CHANGE IT", -0.2, -0.3, self.change_teacher_password, (), 0.06, go_col)
            button(f, "Cancel", 0.4, -0.3, self.show, ["teacher_login"], 0.045)
            self.fields["tnew1" if self.fields["tnow"].get() else "tnow"].setFocus()

        def draw_teacher(self, f, keep):
            st, live = self.state, self.state.get("live")
            games = st.get("games", {})
            # the live session
            label(f, "TEACHER DESK", -1.44, 0.82, 0.06, yellow, TextNode.ALeft)
            if live:
                label(f, f"LIVE: {live['group']}  ({games.get(live['game'], {}).get('title', live['game'])}, "
                         f"lesson {live['lesson']}, since {live['started'][-5:]})", -1.44, 0.72, 0.042, green,
                      TextNode.ALeft)
                button(f, "Open teacher window", 0.55, 0.735, self.open_teacher_window, (), 0.038, (0.15, 0.45, 0.65, 1))
                button(f, "Stop", 1.05, 0.735, self.stop, (), 0.038, warn_col)
            else:
                label(f, "Nothing is live. Launch a group when the session starts.", -1.44, 0.72, 0.042, grey,
                      TextNode.ALeft)
            button(f, "Log out", 1.32, 0.82, self.teacher_logout, (), 0.032)
            button(f, "Records", 1.1, 0.82, self.open_records, (), 0.032)
            if live:  # (the session, or the learners and groups, e.g. to reset a password mid-session)
                chosen, other = (0.2, 0.5, 0.75, 1), (0.16, 0.2, 0.28, 1)
                button(f, "This session", -0.27, 0.735, self.set_view, ["session"], 0.032,
                       chosen if self.teacher_view == "session" else other)
                button(f, "Learners & groups", 0.08, 0.735, self.set_view, ["desk"], 0.032,
                       chosen if self.teacher_view == "desk" else other)
                if self.teacher_view == "session":
                    return self.draw_session(f, keep)
            # learners (left)
            label(f, "LEARNERS", -1.44, 0.6, 0.045, yellow, TextNode.ALeft)
            learners = st.get("learners", [])
            per_page = 12
            pages = max(1, (len(learners) + per_page - 1) // per_page)
            self.page = min(self.page, pages - 1)
            y = 0.52
            for L in learners[self.page * per_page:(self.page + 1) * per_page]:
                label(f, L["name"], -1.44, y, 0.04, white, TextNode.ALeft)
                status = "password changed" if L["changed"] else f"starter: {L['starter']}"
                label(f, status, -1.05, y, 0.03, grey if L["changed"] else blue, TextNode.ALeft)
                button(f, "Reset", -0.35, y + 0.008, self.reset_password, [L["name"]], 0.028)
                button(f, "Remove", -0.18, y + 0.008, self.remove_learner, [L["name"]], 0.028, warn_col)
                y -= 0.075
            if pages > 1:
                button(f, "<", -1.4, -0.4, self.turn_page, [-1], 0.03)
                label(f, f"{self.page + 1} / {pages}", -1.25, -0.41, 0.03, grey)
                button(f, ">", -1.1, -0.4, self.turn_page, [1], 0.03)
            label(f, "Add a learner", -1.44, -0.5, 0.04, yellow, TextNode.ALeft)
            label(f, "Username", -1.44, -0.58, 0.035, grey, TextNode.ALeft)
            self.fields["new_user"] = entry(f, -1.2, -0.58, 10, keep.get("new_user", ""), scale=0.04)
            label(f, "Starter password (blank = made up)", -1.44, -0.66, 0.03, grey, TextNode.ALeft)
            self.fields["new_starter"] = entry(f, -0.78, -0.66, 10, keep.get("new_starter", ""), scale=0.04,
                                               command=lambda t: self.add_learner())
            button(f, "Add", -0.15, -0.65, self.add_learner, (), 0.036, go_col)
            # groups (right)
            label(f, "GROUPS", 0.05, 0.6, 0.045, yellow, TextNode.ALeft)
            y = 0.52
            for g in st.get("groups", []):
                title = games.get(g["game"], {}).get("title", g["game"])
                when = f", {g['time']}" if g.get("time") else ""
                label(f, f"{g['name']}  ({title}, {len(g['learners'])} learners{when})", 0.05, y, 0.038, white,
                      TextNode.ALeft)
                if not live:
                    label(f, "lesson", 0.72, y - 0.001, 0.028, grey, TextNode.ALeft)
                    for n in st.get("lessons", [1, 2, 3, 4, 5]):
                        button(f, str(n), 0.86 + (n - 1) * 0.065, y + 0.007, self.launch, [g["name"], n], 0.028,
                               go_col if n == 1 else off)
                button(f, "Edit", 1.2, y + 0.007, self.edit_group, [g["name"]], 0.028)
                button(f, "Delete", 1.36, y + 0.007, self.delete_group, [g["name"]], 0.028, warn_col)
                y -= 0.075
            if not live:
                label(f, "(a number launches the group on that lesson)", 0.05, y, 0.028, grey, TextNode.ALeft)
                y -= 0.06
            button(f, "New group", 0.2, y - 0.01, self.edit_group, [None], 0.036, (0.15, 0.45, 0.65, 1))

        def draw_session(self, f, keep):
            """While a group is live: who is here, what they've completed, and a note for each."""
            st, live = self.state, self.state["live"]
            ses = st.get("session") or {}
            present, done, notes = ses.get("present", []), ses.get("done", {}), ses.get("notes", {})
            label(f, "THIS SESSION", -1.44, 0.6, 0.045, yellow, TextNode.ALeft)
            label(f, f"{len(present)} of {len(live['learners'])} learners here   -   "
                     f"{sum(done.values())} missions completed   -   {ses.get('cards', 0)} AI cards", -1.44, 0.52,
                  0.036, white, TextNode.ALeft)
            label(f, "Learner", -1.44, 0.44, 0.03, grey, TextNode.ALeft)
            label(f, "Completed", -0.95, 0.44, 0.03, grey, TextNode.ALeft)
            label(f, "Note for this session (saved with the record when you press Stop)", -0.55, 0.44, 0.03, grey,
                  TextNode.ALeft)
            y = 0.37
            for name in live["learners"][:14]:
                here = name in present
                label(f, name, -1.44, y, 0.038, white if here else grey, TextNode.ALeft)
                label(f, str(done.get(name, 0)) if here else "away", -0.95, y, 0.036, green if done.get(name) else grey,
                      TextNode.ALeft)
                self.fields[f"note_{name}"] = entry(f, -0.55, y, 34, keep.get(f"note_{name}", notes.get(name, "")),
                                                    scale=0.034, command=lambda t, n=name: self.save_note(n))
                button(f, "Save", 1.33, y + 0.007, self.save_note, [name], 0.028)
                y -= 0.065
            label(f, "Press Enter or Save after typing a note. Stop ends the session and files its record.", -1.44,
                  y - 0.02, 0.03, grey, TextNode.ALeft)

        def save_note(self, name):
            self.ask_desk({"type": "note", "name": name, "text": self.field(f"note_{name}")})

        def draw_make_pdfs(self, f, keep):
            r = self.pending_record or {}
            if args.test_stop:
                self.taskMgr.doMethodLater(0.5, lambda t: (self.make_pdfs(r), self.finish()) and None, "test_pdfs")
            report = r.get("report") or {}
            changed = sorted(set((report.get("done") or {}).keys()) | set((r.get("notes") or {}).keys()))
            label(f, "SESSION STOPPED", 0, 0.6, 0.08, yellow)
            label(f, f"{esc_text(r.get('group', ''))}  ({GAMES.get(r.get('game'), {}).get('title', '')}, lesson "
                     f"{r.get('lesson', '')}): {len((report.get('present') or {}))} learners were here.", 0, 0.42, 0.045)
            label(f, "Make the PDFs for this session? A card for each of: " + (", ".join(changed) or "nobody (no "
                     "achievements or notes)") + ", and the session summary.", 0, 0.28, 0.038, grey, wrap=50)
            label(f, "They go in Documents\\Club Coders records.", 0, 0.14, 0.036, grey)
            button(f, "Yes, make them", -0.35, -0.05, self.make_pdfs, [r], 0.055, go_col)
            button(f, "Not now", 0.35, -0.05, self.skip_pdfs, (), 0.055)
            label(f, "Not now keeps the record: the PDFs can be made later from Records.", 0, -0.25, 0.033, grey)

        def draw_records(self, f, keep):
            label(f, "RECORDS", -1.44, 0.82, 0.06, yellow, TextNode.ALeft)
            label(f, "Past sessions (newest first). PDFs go in Documents\\Club Coders records.", -1.44, 0.72, 0.036,
                  grey, TextNode.ALeft)
            for i, game in enumerate(GAMES):
                button(f, f"Print scheme of work: {GAMES[game]['title']}", 0.3 + i * 0.62, 0.82, self.print_scheme, [game],
                       0.032, (0.15, 0.45, 0.65, 1))
            y = 0.6
            for s in self.sessions[:12]:
                report = s.get("report") or {}
                label(f, f"{s.get('started', '')[:16]}  {s.get('group', '')}  ({GAMES.get(s.get('game'), {}).get('title', '')}, "
                         f"lesson {s.get('lesson', '')}, {len(report.get('present') or {})} here)", -1.44, y, 0.036, white,
                      TextNode.ALeft)
                button(f, "Make PDFs", 1.25, y + 0.007, self.make_pdfs, [s], 0.03)
                y -= 0.07
            if not self.sessions:
                label(f, "No sessions yet.", -1.44, y, 0.036, grey, TextNode.ALeft)
            button(f, "Back", -1.3, -0.72, self.show, ["teacher"], 0.035)

        def open_records(self):
            self.ask_desk({"type": "sessions"})
            self.show("records")

        def make_pdfs(self, record):
            import records
            self.pending_record = None
            try:
                folder = game_dir(record["game"])
                made = records.make_all(record, self.sessions, folder)
                self.show("teacher")
                self.say(f"Made {len(made)} PDFs in Documents\\Club Coders records", green)
            except Exception as e:
                self.show("teacher")
                self.say(f"The PDFs couldn't be made: {e}", red)

        def skip_pdfs(self):
            self.pending_record = None
            self.show("teacher")
            self.say("The record is kept: make its PDFs later from Records.", grey)

        def print_scheme(self, game):
            import records
            try:
                folder = game_dir(game)
                path = records.scheme_of_work(game, records.lesson_module(game, folder))
                self.say(f"Printed: {path}", green)
            except Exception as e:
                self.say(f"The scheme of work couldn't be made: {e}", red)

        def draw_group(self, f, keep):
            g = self.editing
            label(f, "GROUP", -1.44, 0.82, 0.06, yellow, TextNode.ALeft)
            label(f, "Name", -1.44, 0.64, 0.045, white, TextNode.ALeft)
            self.fields["gname"] = entry(f, -1.15, 0.64, 14, keep.get("gname", g["name"]), scale=0.045)
            label(f, "Proposed time", -0.38, 0.64, 0.045, white, TextNode.ALeft)
            self.fields["gtime"] = entry(f, 0.02, 0.64, 10, keep.get("gtime", g.get("time", "")), scale=0.045)
            label(f, "a day and a time each week, like Tuesday 16:00 (or empty)", 0.02, 0.575, 0.03, grey, TextNode.ALeft)
            label(f, "Game", -1.44, 0.5, 0.045, white, TextNode.ALeft)
            for i, (game, info) in enumerate(self.state.get("games", {}).items()):
                button(f, info["title"], -1.0 + i * 0.4, 0.51, self.pick_game, [game], 0.04, on if g["game"] == game else off)
            label(f, "Learners in this group (tick them)", -1.44, 0.36, 0.045, white, TextNode.ALeft)
            names = [L["name"] for L in self.state.get("learners", [])]
            for i, name in enumerate(names[:48]):
                col, row = i % 4, i // 4
                check(f, " " + name, -1.44 + col * 0.72, 0.27 - row * 0.07, name in g["learners"],
                      lambda v, n=name: self.tick(n, bool(v)), 0.038)
            button(f, "Save group", -0.3, -0.75, self.save_group, (), 0.05, go_col)
            button(f, "Cancel", 0.3, -0.75, self.show, ["teacher"], 0.05)

        # ---------- the desk ----------
        def link_up(self):
            if self.link is None or not self.link.open:
                self.link = DeskLink(server)
            return self.link

        def read_desk(self, task):
            if self.newer and not self.newer_shown and self.screen == "home":  # (GitHub has answered: say so)
                self.draw()
            if self.link is None:
                return task.cont
            try:
                while self.link is not None:  # (on_desk drops the link when the desk's connection closed)
                    m = self.link.inbox.get_nowait()
                    self.on_desk(m)
            except queue.Empty:
                pass
            return task.cont

        def on_desk(self, m):
            if m.get("_open"):
                if self.pending:
                    self.link.send(self.pending)
                    self.pending = None
                return
            if m.get("_closed"):
                if self.screen in ("waiting", "teacher", "group"):
                    self.say("Lost the connection to the club's server: log in again.", red)
                    self.show("home")
                elif self.pending:
                    self.pending = None
                    self.say("Can't reach the club's server. Check your internet connection, then try again.", red)
                self.link = None
                return
            if "error" in m and not m.get("ok"):
                if self.screen == "teacher_login" and getattr(self, "trying_password", None):
                    self.teacher_refused()
                if self.screen == "waiting":
                    self.screen = "home"
                self.say(m["error"], red)  # (say redraws the screen with the message; show would wipe it)
                return
            if m.get("teacher_password_changed"):
                return self.teacher_password_changed()
            if "state" in m:
                self.state = m["state"]
                if getattr(self, "trying_password", None):
                    self.teacher_accepted()
                elif self.screen in ("teacher", "group"):
                    self.draw()
            if m.get("session_record"):  # Stop: the record is filed; ask about the PDFs once the sessions arrive
                self.pending_record = m["session_record"]
                self.ask_desk({"type": "sessions"})
            if m.get("sessions") is not None:
                self.sessions = m["sessions"]
                if self.pending_record:
                    self.show("make_pdfs")
                elif self.screen == "records":
                    self.draw()
            if m.get("done"):
                self.say(m["done"], green)
            if m.get("teacher_window"):
                w = m["teacher_window"]
                if self.teacher_proc is not None and self.teacher_proc.poll() is None:
                    self.say("Your teacher window is already open.", grey)
                elif address_ok(w.get("address")):
                    self.teacher_proc = start_game(w["game"], ["--host", w["address"], "--teacher", "--name", "Teacher",
                                                              "--ticket", w["ticket"]] + passed_on, wait=False,
                                                   code=w.get("code"))
            if m.get("change_password"):
                self.me = m.get("name", self.me)
                self.show("change_password")
            elif m.get("waiting"):
                self.me = m.get("name", self.me)
                self.show("waiting")
            elif m.get("go"):
                g = m["go"]
                if g.get("game") in GAMES and address_ok(g.get("address")):
                    self.say(f"Opening {GAMES[g['game']]['title']}...", green)
                    self.graphicsEngine.renderFrame()
                    argv = ["--host", g["address"], "--ticket", g["ticket"]] + passed_on
                    if args.wait:  # (tests: run the game to its end, then exit with its result)
                        self.finish(start_game(g["game"], argv, wait=True, code=g.get("code")))
                    else:  # (CHANGE 54) the app stays open behind the game, still logged in: when the game window
                        self.game_proc = start_game(g["game"], argv, code=g.get("code"))  # closes, it comes back
                        self.game_title, self.live_id = GAMES[g["game"]]["title"], g.get("live_id")
                        self.show("playing")
                        self.minimised(True)
                        self.taskMgr.remove("watch game")
                        self.taskMgr.add(self.watch_game, "watch game")
                else:
                    self.say("The club's server gave an answer this app doesn't understand: download the newest "
                             "Club Coders.", red)
            elif m.get("ok") and m.get("name") and self.screen == "home":
                self.me = m["name"]

        pending = None

        def ask_desk(self, msg):
            """Send to the desk, connecting first if needed."""
            link = self.link_up()
            if link.open:
                link.send(msg)
            else:
                self.pending = msg

        # ---------- learners ----------
        def set_where(self, local):
            self.local = local
            remember("where", "local" if local else "online")
            self.draw()

        def open_local(self, game):
            start_game(game, ["--host", GAMES[game]["local"]] + passed_on, wait=args.wait)
            self.finish()

        def log_in(self, user=None, password=None):
            user = user or self.field("user")
            password = password or self.field("pass")
            if not user or not password:
                return self.say("Type your username and your password.", red)
            self.password = password
            remember("username", user)
            self.say("Logging in...", grey)
            self.ask_desk({"type": "login", "name": user, "password": password})

        def change_password(self):
            a, b = self.field("new1"), self.field("new2")
            if len(a) < 6:
                return self.say("Passwords need at least 6 characters.", red)
            if a != b:
                return self.say("The two passwords were different: type them again.", red)
            self.ask_desk({"type": "set_password", "name": self.me, "password": self.password, "new": a})
            self.password = a

        def log_out(self):
            if self.link:
                self.link.close()
            self.link, self.me, self.password = None, None, ""
            self.show("home")

        # ---------- the teacher ----------
        def teacher_login(self, password=None):
            password = password or self.field("tpass")
            if not password:
                return self.say("Type the teacher password.", red)
            self.trying_password = password  # (remembered, and the Teacher screen shown, once the desk says yes)
            self.screen = "teacher_login"
            self.say("Logging in...", grey)
            self.ask_desk({"type": "teacher", "password": password})

        def change_teacher_password(self):
            now_, new, again = (self.fields[k].get() if k in self.fields else "" for k in ("tnow", "tnew1", "tnew2"))
            if not now_:
                return self.say("Type the teacher password as it is now.", red)
            if len(new) < MIN_TEACHER_PASSWORD:
                return self.say(f"The new password needs at least {MIN_TEACHER_PASSWORD} characters: three words "
                                "you'll remember is good.", red)
            if new != again:
                return self.say("The two new passwords were different: type them again.", red)
            if new == now_:
                return self.say("That is the password now: choose a different one.", red)
            self.new_teacher_password = new
            self.say("Changing it...", grey)
            self.ask_desk({"type": "change_teacher_password", "password": now_, "new": new})

        def teacher_password_changed(self):
            """The desk has changed it. If this computer remembers the teacher password, it now remembers the new one."""
            new, self.new_teacher_password = self.new_teacher_password, None
            try:
                if new and load_json(teacher_file).get("password"):
                    with open(teacher_file, "w", encoding="utf-8") as fh:
                        json.dump({"password": new}, fh)
            except OSError:
                pass
            for e in self.fields.values():  # (nothing typed on that screen is carried to the next)
                e.enterText("")
            self.screen = "teacher_login"
            self.say("The teacher password is changed. Log in with the new one.", green)

        def teacher_accepted(self):
            password, self.trying_password = self.trying_password, None
            try:
                if getattr(self, "_remember", True):
                    os.makedirs(SETTINGS_DIR, exist_ok=True)
                    with open(teacher_file, "w", encoding="utf-8") as fh:
                        json.dump({"password": password}, fh)
            except OSError:
                pass
            self.show("teacher")

        def teacher_refused(self):
            self.trying_password = None
            try:  # (a remembered password the desk refuses is forgotten, so it isn't offered again)
                os.remove(teacher_file)
            except OSError:
                pass

        def teacher_logout(self):
            if self.link:
                self.link.close()
            self.link, self.state = None, {}
            self.show("home")

        def add_learner(self):
            self.ask_desk({"type": "add_learner", "name": self.field("new_user"), "starter": self.field("new_starter")})

        def reset_password(self, name):
            self.ask_desk({"type": "reset_password", "name": name})

        def remove_learner(self, name):
            if getattr(self, "confirm_remove", None) != name:
                self.confirm_remove = name
                return self.say(f"Remove {name} and delete everything the games keep about them? Press Remove again "
                                "to confirm.", red)
            self.confirm_remove = None
            self.ask_desk({"type": "remove_learner", "name": name})

        def turn_page(self, step):
            self.page = max(0, self.page + step)
            self.draw()

        def edit_group(self, name):
            g = next((g for g in self.state.get("groups", []) if g["name"] == name), None)
            self.editing = {"name": g["name"] if g else "", "game": g["game"] if g else "robotlab",
                            "learners": list(g["learners"]) if g else [], "rename_from": g["name"] if g else None,
                            "time": g.get("time", "") if g else ""}
            self.show("group")

        def pick_game(self, game):
            self.editing["game"] = game
            self.draw()

        def tick(self, name, on_):
            L = self.editing["learners"]
            if on_ and name not in L:
                L.append(name)
            elif not on_ and name in L:
                L.remove(name)

        def save_group(self):
            g = self.editing
            self.ask_desk({"type": "set_group", "name": self.field("gname"), "game": g["game"], "learners": g["learners"],
                           "rename_from": g["rename_from"], "time": self.field("gtime")})
            self.show("teacher")

        def delete_group(self, name):
            self.ask_desk({"type": "delete_group", "name": name})

        def launch(self, group, lesson):
            self.say(f"Launching {group}...", grey)
            self.ask_desk({"type": "launch", "group": group, "lesson": lesson})

        def open_teacher_window(self):
            self.ask_desk({"type": "teacher_window"})

        def stop(self):
            if self.teacher_proc is not None and self.teacher_proc.poll() is None:  # (the learners' windows close
                self.teacher_proc.terminate()                                       # from the server's side)
            self.teacher_proc = None
            self.ask_desk({"type": "stop"})

        def set_view(self, view):
            self.teacher_view = view
            self.draw()

        # ---------- screens ----------
        def show(self, screen):
            self.screen = screen
            self.message = ("", grey)
            self.draw()

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
    ap.add_argument("--login", nargs=2, metavar=("USERNAME", "PASSWORD"), help="log in straight away (tests)")
    ap.add_argument("--teacher-password", help="open the teacher desk straight away (tests)")
    ap.add_argument("--wait", action="store_true", help="wait for the game, then exit with its result (tests)")
    ap.add_argument("--screenshot-launcher", help="save a picture of this window before it closes (tests)")
    ap.add_argument("--snap", type=float, help="close this window after this many seconds (tests)")
    ap.add_argument("--test-stop", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--test-screen", help=argparse.SUPPRESS)  # (tests: start on this screen, e.g. teacher_password)
    ap.add_argument("--test-newer", help=argparse.SUPPRESS)   # (tests: as if this newer version were out)
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
