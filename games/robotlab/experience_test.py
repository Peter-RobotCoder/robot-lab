"""Experience 1's tests (CHANGE 197): the orientation played through by itself, and pictures of it.

    .venv\\Scripts\\python experience_test.py

1. the ranks and the saved best result (no window)
2. the window plays every objective through (experience_1.py --selftest: drive, turn, the rings, the weapon, the
   dummy, the garage's variables and REBUILD, the code, the brain, the bout, the result card, the saved best)
3. a picture of the rings objective, and of the garage
Test data goes to a temporary folder, never this computer's own result. Exit code 0 = all fine.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
PY = sys.executable
TMP = tempfile.mkdtemp(prefix="experience_test_")
results = []


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note else ""), flush=True)


def ranks_and_saving():
    src = open(os.path.join(HERE, "experience_1.py"), encoding="utf-8").read()
    ranks = src[src.index("RANKS = "):].split("\n")[0]  # (the ranks, the numbers and the saving: not the window)
    g = {"PROGRESS": os.path.join(TMP, "best.json")}
    exec(compile("import json\nimport os\n" + ranks + "\n" + src[src.index("def rank_of"):src.index("def ring_mesh")],
                 "experience_1.py", "exec"), g)
    ok = (g["rank_of"](0) == "Rookie" and g["rank_of"](60) == "Cadet" and g["rank_of"](320) == "Club Coder"
          and g["next_rank"](59) == (60, "Cadet") and g["next_rank"](400) is None)
    path = os.path.join(TMP, "best.json")
    g["save_progress"]({"xp": 120, "stars": 1, "seconds": 300.0}, path)
    best = g["save_progress"]({"xp": 90, "stars": 2, "seconds": 250.0}, path)
    check("the ranks, and the best result kept (the most XP and stars, the quickest time, how many finishes)",
          ok and best["best_xp"] == 120 and best["best_stars"] == 2 and best["best_time"] == 250.0
          and best["finished"] == 2, json.dumps(best)[:120])


def played_through():
    shot = os.path.join(TMP, "end.png")
    r = subprocess.run([PY, "experience_1.py", "--offscreen", "--selftest", "--no-sound", "--progress",
                        os.path.join(TMP, "selftest.json"), "--screenshot", shot],
                       capture_output=True, text=True, timeout=600)
    out = r.stdout + r.stderr
    line = next((ln for ln in out.splitlines() if ln.startswith("SELFTEST")), "no SELFTEST line")
    check("the window plays every objective through: " + line[9:], r.returncode == 0 and "SELFTEST PASS" in out
          and "Traceback" not in out, out[-1500:] if r.returncode else "")
    check("pictures: the end card, the garage and the code", all(os.path.exists(shot.replace(".png", s + ".png"))
                                                                for s in ("", "_garage", "_code")), TMP)


def rings_picture():
    shot = os.path.join(TMP, "rings.png")
    r = subprocess.run([PY, "experience_1.py", "--offscreen", "--no-sound", "--objective", "3", "--after", "4",
                        "--progress", os.path.join(TMP, "rings.json"), "--screenshot", shot],
                       capture_output=True, text=True, timeout=300)
    check("a picture of the rings objective", r.returncode == 0 and os.path.exists(shot)
          and os.path.getsize(shot) > 50000, (r.stdout + r.stderr)[-600:] if r.returncode else shot)


if __name__ == "__main__":
    for fn in (ranks_and_saving, played_through, rings_picture):
        try:
            fn()
        except Exception as e:  # (report and carry on)
            check(fn.__name__, False, repr(e))
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} passed  (pictures: {TMP})")
    sys.exit(1 if failed else 0)
