"""Build the downloadable Robot Lab for Windows: dist/RobotLab-windows.zip.

    python release/build_windows.py --server wss://play.<club domain> [--tag v1.0.0] [--check]

The GitHub release workflow runs this on every version tag (the server address comes from the repository
variable ROBOTLAB_SERVER). It can also be run on the teacher's laptop to try a build before tagging.
  1. checks the tag matches lab_version.VERSION (so the game and the class server agree)
  2. writes release_config.json with the class server's address (built in, so learners type nothing)
  3. makes the textures and sounds, so the first start is quick
  4. runs PyInstaller (release/robotlab.spec) and adds brains/my_brain.py and a short read-me next to the app
  5. zips it; --check also starts a laptop test server and logs the built app into it
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
DIST = os.path.join(ROOT, "dist")
APP = os.path.join(DIST, "Robot Lab")
ZIP = os.path.join(DIST, "RobotLab-windows.zip")

READ_ME = """ROBOT LAB
=========
1. Double-click "Robot Lab.exe". The first time, Windows may say it doesn't know this app:
   choose "More info", then "Run anyway". (It is the club's own program, so Windows hasn't seen it before.)
2. Log in with the username, password and class code from your welcome letter.
3. From Lesson 3 you write your robot's brain in brains\\my_brain.py (open it with Notepad),
   then press U in the game to upload it.

Only use a nickname or first name as your username. Never put personal information in the game.
New versions: the game tells you when one is out. Download it from {page}
"""


def run(cmd, **kw):
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("ROBOTLAB_SERVER", ""), help="wss://play.<club domain>")
    ap.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""), help="the release tag, e.g. v1.0.0")
    ap.add_argument("--check", action="store_true", help="log the built app into a laptop test server")
    args = ap.parse_args()
    import lab_version
    if args.tag and args.tag.lstrip("v") != lab_version.VERSION:
        raise SystemExit(f"The tag {args.tag} doesn't match lab_version.VERSION ({lab_version.VERSION}). "
                         "Change VERSION in lab_version.py, commit, then tag that commit.")
    if not args.server.startswith("wss://"):
        raise SystemExit("The class server's address must start with wss:// (set the ROBOTLAB_SERVER repository "
                         "variable on GitHub, or use --server).")

    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)  # (not the game folder: the laptop game stays local)
    stray = os.path.join(ROOT, "release_config.json")
    if os.path.exists(stray):  # left by an older build: it would point the laptop's windows at the class server
        os.remove(stray)
    with open(os.path.join(ROOT, "build", "release_config.json"), "w", encoding="utf-8") as f:
        json.dump({"server": args.server, "version": lab_version.VERSION}, f)
    run([sys.executable, "-c", "import rw_textures, rw_sound; rw_textures.ensure(); rw_sound.ensure()"])
    shutil.rmtree(APP, ignore_errors=True)
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", DIST,
         "--workpath", os.path.join(ROOT, "build"), os.path.join("release", "robotlab.spec")])
    os.makedirs(os.path.join(APP, "brains"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "brains", "my_brain.py"), os.path.join(APP, "brains", "my_brain.py"))
    with open(os.path.join(APP, "READ ME.txt"), "w", encoding="utf-8") as f:
        f.write(READ_ME.format(page=lab_version.DOWNLOAD_PAGE))

    if os.path.exists(ZIP):
        os.remove(ZIP)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(APP):
            for name in files:
                path = os.path.join(folder, name)
                z.write(path, os.path.relpath(path, DIST))
    print(f"Built {ZIP} ({os.path.getsize(ZIP) / 1e6:.0f} MB), version {lab_version.VERSION}, server {args.server}")
    if args.check:
        check()


def check():
    """Start a laptop test server and log the built app into it (offscreen), as a learner would."""
    import tempfile
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    tmp = tempfile.mkdtemp(prefix="robotlab_build_check_")
    server = subprocess.Popen([sys.executable, "lab_server.py", "--port", str(port)], cwd=ROOT,
                              env=dict(os.environ, ROBOTLAB_DATA=tmp), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    shot = os.path.join(tmp, "learner.png")
    try:
        time.sleep(5)
        subprocess.run([os.path.join(APP, "Robot Lab.exe"), "--host", f"ws://127.0.0.1:{port}", "--name", "buildcheck",
                        "--password", "check123", "--offscreen", "--after", "8", "--screenshot", shot],
                       timeout=120)
    finally:
        server.kill()
    if not os.path.exists(shot):
        raise SystemExit("The built app didn't log in and draw (no screenshot).")
    print("Check passed: the built app logged in and drew the arena:", shot)


if __name__ == "__main__":
    main()
