"""The games' pictures against their baselines, kept per renderer: a change to the drawing that wasn't meant shows up.

    python engine/image_diff.py                  Mission 1 and Kart Lab drawn offscreen (the standard pictures below)
                                                 and compared with baselines/<renderer>/: exit code 0 = each within
                                                 the thresholds, or no baseline here yet (said so)
    python engine/image_diff.py --update         record this computer's pictures as the baselines for its renderer
                                                 (in the same commit as a visual change that was meant)
    python engine/image_diff.py --only mission   (or kart) just those pictures; --shots DIR keeps the pictures there
    python engine/image_diff.py compare a.png b.png [--mask x0,y0,x1,y1 ...]     any two pictures

Baselines live in baselines/<renderer key>/<picture>.png at the top of the working folder, the key being what the
graphics driver calls itself (gsg.getDriverRenderer(), as engine.gfx_tiers.detect prints it: on the worker LT5
llvmpipe_LLVM_21.1.8_256_bits, on a laptop its GPU), so a software renderer's pictures are never compared with a
GPU's. No baseline for this renderer: the picture's statistics are printed (brightness, spread) and the picture is
PASS "no baseline here"; --update records it. Every picture is drawn with a fixed size, tier, camera, zoom and
moment (wake_up_call.py and kart_preview.py step time a sixtieth a frame for an offscreen picture, so the same frame
is drawn every run); the strip that shows the frame rate is masked. A picture differs when more than --share percent
of its pixels (0.5) differ by more than --pixel (25 of 255) in a channel: a diff picture (white where they differ)
is written beside it and its path printed. PIL and numpy only (both in the games' requirements). docs/game-tests.md
says how to run this and update the baselines; run it with shared-world-demo's .venv (Kart Lab uses it too).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BASELINES = os.path.join(ROOT, "baselines")
MISSION = os.path.join(ROOT, "shared-world-demo")
KART = os.path.join(ROOT, "kart")
RECORDING = os.path.join(MISSION, "missions", "wake_up_call", "replay_mission.json")
PY = sys.executable
KART_FPS_STRIP = (960, 690, 1280, 720)  # (the frame rate and the key list, bottom right of the kart's 1280 x 720)


def mission_shots(tmp):
    """The standard pictures of Mission 1: (name, command, cwd, masks, the files the command makes {name: path})."""
    out = []

    def one(name, extra, zoom=None):
        shot = os.path.join(tmp, name + ".png")
        cmd = [PY, "wake_up_call.py", "--offscreen", "--no-sound", "--robot", "titan", "--progress",
               os.path.join(tmp, name, "missions_progress.json"), "--screenshot", shot, "--after", "0.5"] + extra
        if zoom:
            cmd += ["--zoom", str(zoom)]
        out.append((name, cmd, MISSION, [], {name: shot}))
    one("mission_valley_high", ["--gfx", "high"])             # the valley as the mission starts, the solid look
    one("mission_zoomed_out_high", ["--gfx", "high"], 2.2)    # the whole map from the furthest zoom
    one("mission_valley_mesh", ["--gfx", "mesh"])             # the mesh look (the lines' fade past the camera)
    # the solution played by its recorded key presses: the code panel with the Python beside it, then the valley
    # with the rockfall cleared and Brookfield lit (the recording is replay_mission.py's)
    if os.path.exists(RECORDING):
        with open(RECORDING, encoding="utf-8") as f:
            case = json.load(f)["cases"][0]
        keys = [["key", "1" if case["robot"] == "TITAN" else "2"], ["key", "c"], ["key", "control-a"],
                ["type", case["runs"][0]], ["frames", 12], ["shot", "panel"], ["key", "control-enter"], ["wait"],
                ["key", "escape"], ["frames", 30], ["shot", "done"]]
        keys_file = os.path.join(tmp, "solution_keys.json")
        with open(keys_file, "w", encoding="utf-8") as f:
            json.dump([{"robot": case["robot"], "keys": keys}], f)
        shot = os.path.join(tmp, "mission_solution.png")
        cmd = [PY, "wake_up_call.py", "--offscreen", "--no-sound", "--fast", "--gfx", "high", "--progress",
               os.path.join(tmp, "solution", "missions_progress.json"), "--replay", keys_file, "--screenshot", shot]
        out.append(("mission_solution_high", cmd, MISSION, [],
                    {"mission_panel_high": shot.replace(".png", "_panel.png"),
                     "mission_done_high": shot.replace(".png", "_done.png")}))
    else:
        print(f"note: no {os.path.relpath(RECORDING, ROOT)} (python replay_mission.py --record makes it): "
              "no pictures of the solution")
    return out


def kart_shots(tmp):
    """The standard pictures of Kart Lab: kart_preview.py at the same moment of the same race on each tier."""
    out = []

    def one(name, extra):
        shot = os.path.join(tmp, name + ".png")
        cmd = [PY, "kart_preview.py", "--offscreen", "--screenshot", shot, "--after", "3"] + extra
        out.append((name, cmd, KART, [KART_FPS_STRIP], {name: shot}))
    one("kart_tv_low", ["--gfx", "low", "--camera", "tv"])                       # the grid from the TV camera
    one("kart_chase_medium", ["--gfx", "medium", "--camera", "chase"])           # behind the followed kart
    one("kart_night_lines", ["--gfx", "lines", "--time", "night", "--brake",     # the lines look at night
                             "--bodies", "coupe,supercar,rally,muscle", "--closeup"])
    return out


# ---------- the renderer's key ----------
def key_from(renderer):
    return re.sub(r"[^A-Za-z0-9.]+", "_", renderer).strip("_") or "unknown"


ASK = """
from panda3d.core import loadPrcFileData
loadPrcFileData("", "window-type offscreen\\nwin-size 64 64\\naudio-library-name null\\nnotify-level fatal\\n")
from direct.showbase.ShowBase import ShowBase
b = ShowBase()
print("RENDERER " + b.win.getGsg().getDriverRenderer())
"""


def renderer_key(given=None):
    """--key, else $RENDERER_KEY, else a 64 x 64 offscreen window asked what draws it."""
    if given:
        return key_from(given)
    if os.environ.get("RENDERER_KEY"):
        return key_from(os.environ["RENDERER_KEY"])
    r = subprocess.run([PY, "-c", ASK], capture_output=True, text=True, timeout=120, cwd=HERE)
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("RENDERER ")]
    if not line:
        print("couldn't ask the renderer its name (give --key): " + (r.stdout + r.stderr)[-400:])
        return "unknown"
    return key_from(line[0][9:])


# ---------- comparing ----------
def load(path):
    from PIL import Image
    import numpy as np
    return np.asarray(Image.open(path).convert("RGB")).astype(int)


def apply_masks(a, b, masks):
    """Black out the boxes to ignore (a frame rate, a clock) in both pictures."""
    for x0, y0, x1, y1 in masks:
        a[y0:y1, x0:x1] = 0
        b[y0:y1, x0:x1] = 0


def differing(a, b, pixel):
    """The share (0 to 1) of pixels whose biggest channel difference is over `pixel`, and which they are."""
    bad = abs(a - b).max(axis=2) > pixel
    return float(bad.mean()), bad


def write_diff(shot, bad, a):
    """Where they differ: white, over the picture darkened; X.diff.png beside X.png."""
    from PIL import Image
    import numpy as np
    out = (a // 4).astype("uint8")
    out[bad] = 255
    path = os.path.splitext(shot)[0] + ".diff.png"
    Image.fromarray(np.ascontiguousarray(out)).save(path)
    return path


def statistics(a):
    h, w = a.shape[:2]
    middle = a[h // 5: 4 * h // 5, w // 5: 4 * w // 5]
    return f"the middle averages {middle.mean():.0f} of 255, spread {middle.std():.0f}"


def compare(shot, base, masks, pixel, share, name=None):
    """0 = the same within the thresholds; 1 = different (the diff picture written and named)."""
    name = name or os.path.splitext(os.path.basename(shot))[0]
    a, b = load(shot), load(base)
    if a.shape != b.shape:
        print(f"FAIL {name}: sizes differ, {a.shape[1]}x{a.shape[0]} against the baseline's {b.shape[1]}x{b.shape[0]}")
        return 1
    apply_masks(a, b, masks)
    frac, bad = differing(a, b, pixel)
    if frac * 100 > share:
        path = write_diff(shot, bad, a)
        print(f"FAIL {name}: {frac * 100:.2f}% of pixels differ from {base} (allowed {share}%): see {path}")
        return 1
    print(f"PASS {name}: {frac * 100:.3f}% of pixels differ (allowed {share}%)")
    return 0


# ---------- the games' standard pictures ----------
def draw(name, cmd, cwd, timeout=600):
    """Run the game's picture command; its output, or None if it failed (said)."""
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"FAIL {name}: not drawn in {timeout} s")
        return None
    out = r.stdout + r.stderr
    if r.returncode != 0:
        print(f"FAIL {name}: exit {r.returncode} after {time.time() - t0:.0f} s:\n    " + "\n    ".join(out.splitlines()[-8:]))
        return None
    return out


def run_games(args):
    key = renderer_key(args.key)
    folder = os.path.join(BASELINES, key)
    tmp = args.shots or tempfile.mkdtemp(prefix="image_diff_")
    os.makedirs(tmp, exist_ok=True)
    print(f"renderer: {key}   pictures: {tmp}   baselines: {os.path.relpath(folder, ROOT)}")
    shots = []
    if args.only in (None, "mission"):
        shots += mission_shots(tmp)
    if args.only in (None, "kart"):
        shots += kart_shots(tmp)
    failed, passed, recorded, missing = 0, 0, 0, 0
    for name, cmd, cwd, masks, files in shots:
        t0 = time.time()
        if draw(name, cmd, cwd) is None:
            failed += 1
            continue
        for pic, path in files.items():
            if not os.path.exists(path):
                print(f"FAIL {pic}: no picture at {path}")
                failed += 1
                continue
            base = os.path.join(folder, pic + ".png")
            if args.update:
                os.makedirs(folder, exist_ok=True)
                shutil.copy2(path, base)
                print(f"recorded {pic} as {os.path.relpath(base, ROOT)} ({time.time() - t0:.0f} s)")
                recorded += 1
            elif not os.path.exists(base):
                print(f"PASS {pic}: no baseline here for {key} ({statistics(load(path))}; --update records it)")
                missing += 1
            elif compare(path, base, masks, args.pixel, args.share, pic):
                failed += 1
            else:
                passed += 1
    if args.update:
        print(f"RECORDED {recorded} baselines for {key}" + (f", {failed} not drawn" if failed else ""))
    else:
        print(f"PICTURES {'FAIL' if failed else 'PASS'}: {passed} the same as their baselines, {failed} differ or weren't "
              f"drawn, {missing} with no baseline for {key}")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("compare", nargs="*", help="compare A.png B.png: two pictures instead of the games'")
    ap.add_argument("--only", choices=["mission", "kart"])
    ap.add_argument("--update", action="store_true", help="record this computer's pictures as its renderer's baselines")
    ap.add_argument("--shots", help="keep the pictures in this folder (default: a temporary one, printed)")
    ap.add_argument("--key", help="the renderer's name (default: ask an offscreen window, or $RENDERER_KEY)")
    ap.add_argument("--mask", action="append", default=[], help="x0,y0,x1,y1 to ignore (compare)")
    ap.add_argument("--pixel", type=int, default=25, help="a channel difference that counts, 0 to 255 (25)")
    ap.add_argument("--share", type=float, default=0.5, help="percent of pixels allowed to differ (0.5)")
    args = ap.parse_args()
    if args.compare:
        if args.compare[0] != "compare" or len(args.compare) != 3:
            ap.error("compare A.png B.png")
        masks = [tuple(int(v) for v in m.split(",")) for m in args.mask]
        return compare(args.compare[1], args.compare[2], masks, args.pixel, args.share)
    return run_games(args)


if __name__ == "__main__":
    sys.exit(main())
