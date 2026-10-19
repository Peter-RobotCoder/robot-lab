"""The page playing Kart Lab over a bad network (CHANGE 165).

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\net_test.py [seconds]      (from the ClubCodersAI folder)

A laptop Kart Lab server with three computer karts racing, and the page driving its own kart round the track (a
simple driver steering for the road ahead), first straight to the server and then through engine/fault_relay.py:
80 ms each way, 40 ms of jitter, and now and then the link stopping for up to 0.9 s and then letting everything
through at once (seeded, though the computer karts and the timing differ every run). Checks, for the bad network:
the page stays connected, no JavaScript errors, the prediction's corrections stay few, and the kart as drawn never
jumps (the most it moves between two frames, but for a correction over 4 m after a long stall, which the prediction
draws at once on purpose: 1.9.19 did that too, 1 or 2 times a run). Exit code 0 = all fine.
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import web_test as wt  # noqa: E402

KART = next(p for p in (os.path.join(os.path.dirname(HERE), "games", "kartlab"),
                        os.path.join(os.path.dirname(os.path.dirname(HERE)), "kart")) if os.path.isdir(p))
ENGINE = next(p for p in (os.path.join(os.path.dirname(HERE), "engine"),
                          os.path.join(os.path.dirname(os.path.dirname(HERE)), "engine")) if os.path.isdir(p))
sys.path.insert(0, os.path.dirname(ENGINE))
from engine import fault_relay  # noqa: E402

DRIVE = """(() => {
  const g = window.__state.game, c = window.__state.ctrl;
  window.__net = {jump: 0, frames: 0, last: null, snapped: 0, steps: 0};
  c.kartControl = () => {  // (full throttle, steering at a point 8 m down the road)
    const st = g.predictor ? g.predictor.state : null;
    if (!st) return {throttle: 1, steer: 0, buttons: 0};
    const at = g.track.locate(st.x, st.y, st.seg ?? null), [tx, ty] = g.track.point(at.s + 8, 0);
    let d = Math.atan2(ty - st.y, tx - st.x) * 180 / Math.PI - st.yaw;
    d = ((d + 180) % 360 + 360) % 360 - 180;
    return {throttle: 1, steer: Math.max(-1, Math.min(1, d / 20)), buttons: 0};
  };
  const scene = window.__state.scene.scene;
  scene.onAfterRenderObservable.add(() => {  // the own kart as drawn: the most it moves between two frames
    const k = window.__state.scene.karts.get(g.myId());
    if (!k) return;
    const p = k.root.position, n = window.__net, S = window.__state;
    const snapped = g.smoother ? g.smoother.snaps : 0;  // (a correction over 4 m is drawn at once, on purpose: not a jump)
    if (n.last && snapped === n.snapped) {
        const d = Math.hypot(p.x - n.last[0], p.z - n.last[1]);
        if (d > 1.2) n.steps++;
        if (d > n.jump) {  // (what was going on: how long since a snapshot came, the prediction's corrections)
            n.jump = d;
            const snaps = S.snaps, last = snaps[snaps.length - 1];
            n.at = {jump: +d.toFixed(2), gap: last ? Math.round(performance.now() - (last.at || 0)) : null,
                    corr: g.predictor.corrections, snapped: g.smoother ? g.smoother.snaps : null};
        }
    }
    n.last = [p.x, p.z];
    n.snapped = snapped;
    n.frames++;
  });
  return true;
})()"""


def drive(port, code, http_port, work, seconds, label):
    chrome = wt.Chrome(next(p for p in wt.BROWSERS if os.path.exists(p)), os.path.join(work, "profile_" + label))
    try:
        chrome.open(f"http://127.0.0.1:{http_port}/index.html?host=ws://127.0.0.1:{port}&auto=0&tier=low&cam=chase")
        chrome.wait_for("!!window.__state && !!document.getElementById('connect').onclick && "
                        "!document.getElementById('code').hidden", 20, "the code box")
        chrome.js(f"document.getElementById('code').value = {json.dumps(code)}; document.getElementById('connect').click()")
        chrome.wait_for("window.__state.connected === true && !!window.__state.game && !!window.__state.game.predictor",
                        40, "the prediction")
        time.sleep(3)
        chrome.js(DRIVE)
        c0 = chrome.js("window.__state.game.predictor.corrections")
        time.sleep(seconds)
        got = chrome.js("({corr: window.__state.game.predictor.corrections, connected: window.__state.connected, "
                        "reconnects: window.__state.reconnects, jump: window.__net.jump, frames: window.__net.frames, "
                        "fps: window.__state.fps, errors: window.__errors, at: window.__net.at, steps: window.__net.steps})")
        got["corr"] -= c0
        return got
    finally:
        chrome.close()


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 25
    work = tempfile.mkdtemp(prefix="net_test_")
    code = "local-" + secrets.token_hex(12)
    port, relay_port, http_port = wt.free_port(), wt.free_port(), wt.free_port()
    env = {**os.environ, "KARTLAB_DATA": os.path.join(work, "data"), "TEACHER_CODE": code}
    server = subprocess.Popen([sys.executable, "kart_server.py", "--port", str(port), "--cpu", "3"], cwd=KART, env=env,
                              stdout=open(os.path.join(work, "server.log"), "w"), stderr=subprocess.STDOUT)
    http = None
    ok = True
    try:
        assert wt.wait_port(port, 60), "the kart server didn't start"
        http = wt.StaticServer(http_port)
        fault_relay.run_relay(relay_port, port, lag=80, jitter=40, stall=0.08, seed=7)
        good = drive(port, code, http_port, work, seconds, "good")
        bad = drive(relay_port, code, http_port, work, seconds, "bad")
        print(f"  good network: {good['corr']} corrections in {seconds:.0f} s, the kart drawn moving at most "
              f"{good['jump']:.2f} m a frame, {good['fps']} fps")
        print(f"  bad network (80 ms, 40 ms jitter, stalls): {bad['corr']} corrections, at most {bad['jump']:.2f} m a "
              f"frame, {bad['fps']} fps, reconnects {bad['reconnects']} (the biggest: {bad.get('at')})")
        checks = [
            ("the page stays connected over the bad network", bad["connected"] and not bad["reconnects"]),
            ("no JavaScript errors", not good["errors"] and not bad["errors"]),
            ("the prediction's corrections stay few (at most 5 a second: in traffic they're mostly bumps, 1 to 3 a "
             "second)", bad["corr"] <= 5 * seconds),
            (f"the kart as drawn doesn't jump: {bad['steps']} frames moved it over 1.2 m (racing speed is 0.4 m a frame); "
             f"at most 5, after the stalls (the relay stops the link about twice in 25 s: the server's input queue runs "
             f"dry and it moves on without our keys)", bad["steps"] <= 5 and not good["steps"]),
        ]
        for name, passed in checks:
            ok &= bool(passed)
            print(f"{'PASS' if passed else 'FAIL'}  {name}")
    finally:
        if http is not None:
            wt.stop(http)
        wt.stop(server)
    print("all passed" if ok else "something failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
