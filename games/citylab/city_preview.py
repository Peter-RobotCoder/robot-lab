"""City Lab's pictures of every graphics tier (step 7), and the frame rate on a school laptop's window.

    python city_preview.py                       the seven tiers driving through Harbour City, by day, and one sheet
    python city_preview.py --time night          the same at night (the lamps, the lit windows, the headlights)
    python city_preview.py --fps                 also: the frame rate of low and medium in a 1366 x 768 window
                                                 (a school laptop's screen), 15 seconds each, on this computer

Each picture is the real window (city_client.py --offline, the demo driver in a car), offscreen at 1280 x 720. The
pictures and the sheet go in --out (default: a folder in the computer's temp folder), and the sheet's path is printed.
"""
import argparse
import os
import statistics
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TIERS = ["mesh", "lines", "basic", "low", "medium", "high", "ultra"]


def picture(tier, out, time_of_day, demo):
    path = os.path.join(out, f"city_{tier}_{time_of_day}.png")
    env = dict(os.environ, APPDATA=tempfile.mkdtemp(prefix="citylab_preview_"))  # (no settings carried in)
    r = subprocess.run([sys.executable, "city_client.py", "--offline", "--offscreen", demo, "--gfx", tier, "--time",
                        time_of_day, "--screenshot", path, "--after", "7", "--mute"], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0 and os.path.exists(path)
    print(f"{tier:7s} {'ok' if ok else 'FAILED'}  {path}", flush=True)
    if not ok:
        print((r.stdout + r.stderr)[-800:])
    return path if ok else None


def fps(tier, secs=15):
    """The frame rate of a real window (1366 x 768, a school laptop's screen) driving about: the median of the
    seconds after the first five (the loading and the first frames are left out)."""
    env = dict(os.environ, APPDATA=tempfile.mkdtemp(prefix="citylab_preview_"))
    out = os.path.join(env["APPDATA"], "shot.png")
    r = subprocess.run([sys.executable, "city_client.py", "--offline", "--demo-drive", "--gfx", tier, "--window",
                        "1366x768", "--fps", "--mute", "--screenshot", out, "--after", str(secs)], cwd=HERE, env=env,
                       capture_output=True, text=True, timeout=300)
    rates = [int(line.split()[1]) for line in r.stdout.splitlines() if line.startswith("fps ")]
    return statistics.median(rates[5:]) if len(rates) > 6 else None


def sheet(paths, out, name):
    from PIL import Image, ImageDraw
    w, h = 640, 360
    cols = 2
    rows = (len(paths) + cols - 1) // cols
    img = Image.new("RGB", (w * cols, h * rows), (9, 12, 23))
    draw = ImageDraw.Draw(img)
    for i, (tier, p) in enumerate(paths):
        x, y = (i % cols) * w, (i // cols) * h
        if p:
            img.paste(Image.open(p).convert("RGB").resize((w, h)), (x, y))
        draw.rectangle((x, y, x + 90, y + 24), fill=(9, 12, 23))
        draw.text((x + 8, y + 6), tier.upper(), fill=(182, 255, 59))
    path = os.path.join(out, name)
    img.save(path)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "citylab_preview"))
    ap.add_argument("--time", choices=["day", "dusk", "night"], default="day")
    ap.add_argument("--on-foot", action="store_true", help="the demo person walking instead of driving")
    ap.add_argument("--fps", action="store_true")
    ap.add_argument("--tiers", default=",".join(TIERS))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    demo = "--demo" if a.on_foot else "--demo-drive"
    shots = [(t, picture(t, a.out, a.time, demo)) for t in a.tiers.split(",")]
    print("sheet:", sheet(shots, a.out, f"city_tiers_{a.time}.png"))
    if a.fps:
        for t in ("low", "medium"):
            print(f"fps {t}: {fps(t)} (1366 x 768, the demo driving)", flush=True)
    sys.exit(0 if all(p for _, p in shots) else 1)
