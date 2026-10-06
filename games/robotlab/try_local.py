"""Try it on this laptop: the teacher's one window leaves the class for a moment and opens on a test server here.

A kept AI change is on this laptop only: the class server gets it when the teacher makes it live. To look at it
first, the teacher's window (the AI cards tab, or Controls) calls start(): a test server starts on this laptop,
out of sight (it has no window of its own, and its data goes in a temporary folder, so every try starts clean).
When it answers (ready), the window reopens itself on it; "Back to the class" reopens it on the class again and
calls stop(). How the window gets there and back travels in one environment variable (see pack and unpack).

The same file is in each game's folder (as club_ticket.py is): the games share no code.
"""
import ast
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

PID_FILE = "try_server.pid"  # (in the game's folder: a test server left behind by a window that was closed is stopped)


def start(here, server, data_env):
    """Start a test server (the game's server file, e.g. lab_server.py) on a free port of this laptop.
    Returns ({"pid", "port", "data", "log"}, the program started: its poll() says if it has stopped)."""
    stop_left_behind(here)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    data = tempfile.mkdtemp(prefix="clubcoders_try_")
    log = os.path.join(data, "try_server.log")
    env = dict(os.environ, **{data_env: data}, PYTHONUNBUFFERED="1")
    for key in ("JOIN_CODE", "TEACHER_CODE", "CLUBCODERS_TICKET_KEY", "CLUBCODERS_LIVE_FILE", "CLUBCODERS_DESK_INBOX"):
        env.pop(key, None)  # (a laptop test server: the demo codes, no club desk)
    with open(log, "w") as out:
        proc = subprocess.Popen([sys.executable, os.path.join(here, server), "--port", str(port)], cwd=here, env=env,
                                stdout=out, stderr=out, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    info = {"pid": proc.pid, "port": port, "data": data, "log": log}
    try:
        with open(os.path.join(here, PID_FILE), "w") as f:
            json.dump(info, f)
    except OSError:
        pass
    return info, proc


def ready(info):
    """Is the test server answering yet?"""
    try:
        socket.create_connection(("127.0.0.1", info["port"]), timeout=0.2).close()
        return True
    except OSError:
        return False


def last_words(info, lines=3):
    """The end of what the test server said (when it didn't start: usually the mistake in the new code)."""
    try:
        with open(info["log"], encoding="utf-8", errors="replace") as f:
            return " ".join(line.strip() for line in f.read().strip().splitlines()[-lines:])[-300:]
    except OSError:
        return ""


def stop(info, here=None):
    """Stop the test server (and any brains it started) and throw its data away."""
    if not info:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(int(info["pid"]))], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.kill(int(info["pid"]), 9)
    except (OSError, ValueError, KeyError):
        pass
    data = str(info.get("data", ""))
    if os.path.basename(data).startswith("clubcoders_try_"):  # (only ever a folder this file made)
        for _ in range(5):  # (the server lets go of its files a moment after it stops)
            shutil.rmtree(data, ignore_errors=True)
            if not os.path.exists(data):
                break
            time.sleep(0.2)
    if here:
        try:
            os.remove(os.path.join(here, PID_FILE))
        except OSError:
            pass


def stop_left_behind(here):
    """A test server from an earlier try whose window was closed with the X: stop it."""
    try:
        with open(os.path.join(here, PID_FILE)) as f:
            info = json.load(f)
    except (OSError, ValueError):
        return
    if isinstance(info, dict) and "pid" in info and os.path.basename(str(info.get("data", ""))).startswith("clubcoders_try_"):
        stop(info, here)


def pack(info, back_argv, back_login, mods=(), lesson=None):
    """Everything the window on the test server needs: the server to stop afterwards, the user mods to switch on,
    the class's lesson number, and how this window was opened on the class (to go back the same way)."""
    return json.dumps({"server": info, "argv": list(back_argv), "login": list(back_login), "mods": list(mods),
                       "lesson": lesson})


def unpack(text):
    try:
        v = json.loads(text or "")
        return v if isinstance(v, dict) and isinstance(v.get("server"), dict) else None
    except ValueError:
        return None


def mod_keys(source):
    """The user mods a game's code has: the keys of its USER_MODS = {...} (read as text, never run)."""
    try:
        tree = ast.parse(source.decode("utf-8") if isinstance(source, bytes) else source or "")
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and [getattr(t, "id", None) for t in node.targets] == ["USER_MODS"] \
                and isinstance(node.value, ast.Dict):
            return {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    return set()
