"""A game window opening itself again as a new process, then closing (CHANGE 189: one copy, shared by every game).

A window reopens itself to load new code (the class server runs different code), at a graphics tier chosen in its
Settings (the shaders and the window's multisampling are made as a window opens: CHANGE 149), or to try a mod on
the laptop. Robot Lab, Fight Lab, Kart Lab and the Missions window each did this with the same dozen lines: the
new process detached from this one, its output to window.log, the Club Coders app told the new process id
(CLUBCODERS_WINDOW_PID_FILE, CHANGE 154: the app follows the window it opened through every reopen), then os._exit.

    from engine import reopen
    reopen.reopen(__file__, argv, env, frozen=lab_version.FROZEN, log_dir=SETTINGS_DIR if FROZEN else HERE)

Each game still decides what travels to the new window (its login in an environment variable, its arguments) and
what is left out (--name and --password, --gfx when a tier was chosen).
"""
import os
import subprocess
import sys

PID_FILE_ENV = "CLUBCODERS_WINDOW_PID_FILE"  # (set by the Club Coders app on every game window it opens)
LOG = "window.log"


def program(script, frozen):
    """What runs the new window: the downloaded app's exe itself (it knows which game from the environment or its
    --game argument), else this Python with the window's own file."""
    return [sys.executable] if frozen else [sys.executable, os.path.abspath(script)]


def start(script, argv, env, frozen=False, log_dir=None, cwd=None):
    """Open the new window: the process, detached from this one on Windows, its output appended to window.log in
    log_dir (the game's own folder from the source files, the settings folder in the downloaded app). Raises OSError
    when it can't be started (nothing has closed: the caller carries on). The app that opened this window is told the
    new process id."""
    here = os.path.dirname(os.path.abspath(script))
    log_dir = log_dir or here
    cwd = cwd or (os.getcwd() if frozen else here)
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, LOG), "a") as log:
        child = subprocess.Popen(program(script, frozen) + list(argv), cwd=cwd, env=env, stdout=log, stderr=log,
                                 creationflags=flags)
    tell_app(child.pid)
    return child


def tell_app(pid):
    """The Club Coders app follows the window it opened by its process id: the new one's goes in the file the app
    named (CHANGE 154). Nothing when this window wasn't opened by the app, or the file can't be written."""
    path = os.environ.get(PID_FILE_ENV)
    if not path:
        return False
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(pid))
        return True
    except OSError:
        return False


def reopen(script, argv, env, frozen=False, log_dir=None, cwd=None):
    """start(), then end this process at once (os._exit: Panda's window closes with it, nothing else runs)."""
    start(script, argv, env, frozen, log_dir, cwd)
    os._exit(0)
