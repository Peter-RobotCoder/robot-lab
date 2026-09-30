"""Build the downloadable Club Coders app for Windows (both games): dist/ClubCoders-windows.zip.

    python release/build_windows.py --server wss://play.<club domain> [--tag v1.1.0] [--check]

The GitHub release workflow runs this on every version tag (the server address comes from the repository
variable ROBOTLAB_SERVER). It can also be run on the teacher's laptop to try a build before tagging.
  1. checks the tag matches VERSION (so the app and the class server agree)
  2. writes build/release_config.json with the class server's address (built in, so learners type nothing)
  3. makes each game's textures and sounds, so the first start is quick
  4. runs PyInstaller (release/clubcoders.spec) and adds each game's starter brain (brains/<game>/my_brain.py)
     and a short read-me next to the app
  5. zips it; --check also starts a laptop club desk and a class server for each game, has a teacher make a
     learner and launch a group for each game in turn, and has the built app log the learner in to it
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "Club Coders")
ZIP = os.path.join(DIST, "ClubCoders-windows.zip")
GAMES = {"robotlab": ("Robot Lab", "lab_server.py", "ROBOTLAB_DATA", "import rw_textures, rw_sound; "
                                                                   "rw_textures.ensure(); rw_sound.ensure()"),
         "fightlab": ("Fight Lab", "fight_server.py", "FIGHTLAB_DATA", "import rw_textures, rw_sound, fight_sound; "
                                                                      "rw_textures.ensure(); rw_sound.ensure(); "
                                                                      "fight_sound.ensure()")}

READ_ME = """CLUB CODERS
===========
1. Double-click "Club Coders.exe". The first time, Windows may say it doesn't know this app:
   choose "More info", then "Run anyway". (It is the club's own program, so Windows hasn't seen it before.)
2. Type the class code from your welcome letter and press GO. Your class's game opens:
   log in with the username and password from your welcome letter.
3. From the lesson where you write a brain, it's in the brains folder next to this file:
   brains\\robotlab\\my_brain.py (Robot Lab) or brains\\fightlab\\my_brain.py (Fight Lab).
   Open it with Notepad, then press U in the game to upload it.

Only use a nickname or first name as your username. Never put personal information in the game.
New versions: the game tells you when one is out. Download it from {page}
"""


def run(cmd, cwd=ROOT, **kw):
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=cwd, **kw)


def version():
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("ROBOTLAB_SERVER", ""), help="wss://play.<club domain>")
    ap.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""), help="the release tag, e.g. v1.1.0")
    ap.add_argument("--check", action="store_true", help="have the built app find and log in to each game")
    args = ap.parse_args()
    v = version()
    if args.tag and args.tag.lstrip("v") != v:
        raise SystemExit(f"The tag {args.tag} doesn't match VERSION ({v}). Change VERSION (in club-coders/VERSION, "
                         "then export again), commit, then tag that commit.")
    if not args.server.startswith("wss://"):
        raise SystemExit("The class server's address must start with wss:// (set the ROBOTLAB_SERVER repository "
                         "variable on GitHub, or use --server).")

    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    config = {"server": args.server, "version": v}
    if not args.tag:  # (a laptop test build: it may be pointed at test servers here; a release never is)
        config["test_build"] = True
    key_file = os.path.join(ROOT, "live", "live_key.pub")
    if os.path.exists(key_file):  # the public half of the teacher's key: the app runs only live code signed with it
        with open(key_file, encoding="utf-8") as f:
            config["live_key"] = f.read().strip()
    elif args.tag:
        raise SystemExit("live/live_key.pub is missing, so this release couldn't take live updates. Make the key "
                         "(live/make_live.py --new-key), commit live_key.pub, export again, then tag.")
    else:
        print("Note: no live/live_key.pub, so this build won't take live updates.")
    with open(os.path.join(ROOT, "build", "release_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f)
    for game, (_, _, _, make_assets) in GAMES.items():
        run([sys.executable, "-c", make_assets], cwd=os.path.join(ROOT, "games", game))
    shutil.rmtree(APP, ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", DIST,
         "--workpath", os.path.join(ROOT, "build"), os.path.join("release", "clubcoders.spec")])
    for game in GAMES:  # learners edit these, so they sit next to the app, not inside it
        os.makedirs(os.path.join(APP, "brains", game), exist_ok=True)
        shutil.copy(os.path.join(ROOT, "games", game, "brains", "my_brain.py"),
                    os.path.join(APP, "brains", game, "my_brain.py"))
    with open(os.path.join(APP, "READ ME.txt"), "w", encoding="utf-8") as f:
        f.write(READ_ME.format(page="https://github.com/Peter-RobotCoder/robot-lab/releases/latest"))

    if os.path.exists(ZIP):
        os.remove(ZIP)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(APP):
            for name in files:
                path = os.path.join(folder, name)
                z.write(path, os.path.relpath(path, DIST))
    print(f"Built {ZIP} ({os.path.getsize(ZIP) / 1e6:.0f} MB), Club Coders {v}, server {args.server}")
    if args.check:
        check()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def check():
    """A laptop club desk and a class server for each game. A teacher makes a learner and launches a group for
    each game in turn; the built app must log the learner in and open that game (offscreen), as a learner would."""
    from websockets.sync.client import connect
    tmp = tempfile.mkdtemp(prefix="clubcoders_build_check_")
    desk_port, procs = free_port(), []
    desk_data = os.path.join(tmp, "desk")
    env = dict(os.environ, CLUBCODERS_DESK_DATA=desk_data, TEACHER_CODE="build-check-teacher-code",
               JOIN_CODE="build-check-join", CLUBCODERS_TICKET_KEY=os.path.join(desk_data, "ticket_key"),
               CLUBCODERS_LIVE_FILE=os.path.join(desk_data, "live.json"))

    def ask(ws, msg, want="ok"):
        ws.send(json.dumps(msg))
        for _ in range(20):
            m = json.loads(ws.recv(timeout=15))
            if want in m or "error" in m:
                return m
    try:
        games = {}
        for game, (title, server, data_env, _) in GAMES.items():
            port = free_port()
            games[game] = f"ws://127.0.0.1:{port}"
            procs.append(subprocess.Popen(
                [sys.executable, server, "--class-server", "--port", str(port)], cwd=os.path.join(ROOT, "games", game),
                env=dict(env, **{data_env: os.path.join(tmp, game)},
                         CLUBCODERS_DESK_INBOX=os.path.join(desk_data, "inbox", game)),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        with open(os.path.join(tmp, "games.json"), "w", encoding="utf-8") as f:
            json.dump(games, f)
        procs.append(subprocess.Popen([sys.executable, os.path.join("desk", "club_desk.py"), "--port", str(desk_port),
                                       "--games", os.path.join(tmp, "games.json")], cwd=ROOT, env=env,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        time.sleep(8)
        with connect(f"ws://127.0.0.1:{desk_port}") as t:
            ask(t, {"type": "teacher", "password": "build-check-teacher-code"})
            ask(t, {"type": "add_learner", "name": "buildcheck", "starter": "check-starter"})
        with connect(f"ws://127.0.0.1:{desk_port}") as s:
            ask(s, {"type": "login", "name": "buildcheck", "password": "check-starter"})
            ask(s, {"type": "set_password", "name": "buildcheck", "password": "check-starter", "new": "check12345"},
                want="changed")
        for game, (title, *_) in GAMES.items():
            with connect(f"ws://127.0.0.1:{desk_port}") as t:
                ask(t, {"type": "teacher", "password": "build-check-teacher-code"})
                ask(t, {"type": "set_group", "name": f"{game} group", "game": game, "learners": ["buildcheck"]})
                m = ask(t, {"type": "launch", "group": f"{game} group", "lesson": 1})
                if not m.get("ok"):
                    raise SystemExit(f"The desk couldn't launch {title}: {m.get('error')}")
                time.sleep(4)
                shot = os.path.join(tmp, f"{game}.png")
                subprocess.run([os.path.join(APP, "Club Coders.exe"), "--server", f"ws://127.0.0.1:{desk_port}",
                                "--login", "buildcheck", "check12345", "--wait", "--offscreen", "--after", "10",
                                "--screenshot", shot],
                               env=dict(os.environ, APPDATA=os.path.join(tmp, "appdata")), timeout=240)
                if not os.path.exists(shot):
                    raise SystemExit(f"The built app didn't open {title} for the launched group (no screenshot).")
                print(f"Check passed: the learner's login opened {title}, logged in and drew it: {shot}")
                ask(t, {"type": "stop"})
    finally:
        for p in procs:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)


if __name__ == "__main__":
    main()
