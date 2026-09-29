"""Which version of the game is running, where the class server is, and whether a newer version is out.

VERSION is the release number (the GitHub release tag without the "v"). The class server only lets in windows
running the same VERSION, so everyone in a lesson plays by the same rules. Change it for every release:
the release workflow refuses to build if the tag and VERSION don't match.

SERVER is where a window connects unless told otherwise. In the downloadable game it is the class server's
address (release_config.json, written by the release build from the ROBOTLAB_SERVER repository variable), so
learners type nothing. Run from the source files (the teacher's laptop) it is always the laptop test server, so
13 / 14 / 15 keep working however many builds have been made. ONLINE_SERVER is the club's class server, offered
on the login screen ("Play on: This computer / Online class").

CODE is a fingerprint of the game's Python files, used only with a laptop test server: a window running
different code from that server (after the teacher switches a mod or restarts it) reopens itself with the new code.
"""
import hashlib
import json
import os
import sys
import urllib.request

VERSION = "1.2.0"  # the Club Coders app's version (stamped by make_public_repo.py)
GITHUB_REPO = "Peter-RobotCoder/robot-lab"  # (stamped: the Club Coders releases page)
DOWNLOAD_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
LOCAL_SERVER = "ws://127.0.0.1:8780"
CLUB_SERVER = "wss://play.clubcoders.co.uk"  # the club's class server (the IONOS VPS)

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = bool(getattr(sys, "frozen", False))  # running as the downloaded Robot Lab.exe
BUNDLE = getattr(sys, "_MEIPASS", HERE)       # where the exe's bundled files are


def fingerprint():
    h = hashlib.sha1()
    for name in sorted(os.listdir(HERE)):
        if name.endswith(".py"):
            h.update(name.encode())
            with open(os.path.join(HERE, name), "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:12]


def _release_config():
    if not FROZEN:  # (only the downloaded app has release settings; the source files are the laptop version)
        return {}
    try:
        with open(os.path.join(BUNDLE, "release_config.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


CODE = fingerprint()
SERVER = _release_config().get("server") or LOCAL_SERVER
ONLINE_SERVER = _release_config().get("server") or CLUB_SERVER


def parse(version):
    """'v1.2.0' or '1.2.0' -> (1, 2, 0); anything else -> None."""
    try:
        return tuple(int(x) for x in str(version).lstrip("v").split("."))
    except ValueError:
        return None


def newer_release(timeout=4):
    """The newest release's version if it is newer than this one, else None (also None if GitHub can't be reached)."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "RobotLab"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            tag = json.load(r).get("tag_name", "")
    except Exception:
        return None
    latest, mine = parse(tag), parse(VERSION)
    return tag.lstrip("v") if latest and mine and latest > mine else None
