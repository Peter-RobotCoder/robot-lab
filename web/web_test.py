"""Club Coders Live: the browser page against a laptop Kart Lab server, driven through headless Chrome.

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\web_test.py      (from the ClubCodersAI folder)

Starts a club desk, a Kart Lab test server and a static server for this folder, opens the page in headless Chrome
(Google Chrome or Microsoft Edge, whichever is installed) over the DevTools protocol, and checks: a wrong teacher
password is refused; the right one logs in through the desk, which hands the page a ticket for the class; the page draws the track and the karts from the server's snapshots with no JavaScript errors;
START A RACE, TO THE GRID, a mission button and the track picker reach the server and come back in the lesson; the
graphics tier can be changed. A screenshot is kept in the test folder. Exit code 0 = every check passed; the test
says so and passes if no Chrome or Edge is installed.
"""
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# the kart game: games/kartlab beside web/ in the public repository and the app, kart/ two folders up in the
# working folder (club-coders/web/)
KART = next((p for p in (os.path.join(os.path.dirname(HERE), "games", "kartlab"),
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "kart"))
             if os.path.isdir(p)), None)
DESK = os.path.join(os.path.dirname(HERE), "desk")  # (club-coders/desk, or desk/ in the public repository)
DESK_PASSWORD = "web-test-teacher-password"
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]

results = []


def check(name, fn):
    t0 = time.perf_counter()
    try:
        fn()
        results.append((name, True, ""))
        print(f"PASS {name}  {time.perf_counter() - t0:.0f} s", flush=True)
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"FAIL {name}: {type(e).__name__}: {e}", flush=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


class Chrome:
    """Headless Chrome over the DevTools protocol: one page, evaluate JavaScript, take a picture."""

    def __init__(self, exe, profile):
        from websockets.sync.client import connect
        self.proc = subprocess.Popen([exe, "--headless=new", "--no-first-run", "--no-default-browser-check",
                                      f"--user-data-dir={profile}", "--window-size=1400,850", "--hide-scrollbars",
                                      "--remote-debugging-port=0", "--remote-allow-origins=*", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                     encoding="utf-8", errors="replace")
        url = None
        end = time.time() + 30
        while time.time() < end:
            line = self.proc.stderr.readline()
            if "DevTools listening on" in line:
                url = line.split("DevTools listening on", 1)[1].strip()
                break
            if self.proc.poll() is not None:
                break
        if not url:
            raise RuntimeError("Chrome didn't say where its DevTools socket is")
        self.ws = connect(url, max_size=64 * 1024 * 1024).__enter__()  # (closed by hand in close())
        self.n = 0
        self.session = None

    def call(self, method, **params):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params}
        if self.session:
            msg["sessionId"] = self.session
        self.ws.send(json.dumps(msg))
        while True:
            reply = json.loads(self.ws.recv(timeout=30))
            if reply.get("id") == self.n:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def open(self, url):
        target = self.call("Target.createTarget", url="about:blank")["targetId"]
        self.session = self.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]
        self.call("Runtime.enable")
        self.call("Page.enable")
        self.call("Page.navigate", url=url)

    def js(self, expression):
        r = self.call("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("text", "") + " " + str(r["exceptionDetails"].get("exception", {}).get("description", "")))
        return r.get("result", {}).get("value")

    def wait_for(self, expression, seconds=20, what=None):
        end = time.time() + seconds
        last = None
        while time.time() < end:
            last = self.js(expression)
            if last:
                return last
            time.sleep(0.25)
        raise TimeoutError(f"{what or expression} didn't happen in {seconds} s (last: {last!r})")

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        with open(path, "wb") as f:
            f.write(base64.b64decode(data))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        stop(self.proc)


def main():
    if KART is None:
        print("The kart game's folder isn't beside this one: nothing to test against.")
        return 1
    exe = next((p for p in BROWSERS if os.path.exists(p)), None)
    if exe is None:
        print("No Chrome or Edge on this computer: the browser page isn't tested here (it passes).")
        return 0
    work = tempfile.mkdtemp(prefix="clubcoders_web_")
    kart_port, http_port, desk_port = free_port(), free_port(), free_port()
    desk_data = os.path.join(work, "desk")
    with open(os.path.join(work, "games.json"), "w") as f:
        json.dump({"kartlab": f"ws://127.0.0.1:{kart_port}"}, f)
    env = {**os.environ, "KARTLAB_DATA": os.path.join(work, "data"), "PYTHONUNBUFFERED": "1",
           "CLUBCODERS_DESK_DATA": desk_data, "TEACHER_CODE": DESK_PASSWORD, "JOIN_CODE": "web-test-join",
           "CLUBCODERS_TICKET_KEY": os.path.join(desk_data, "ticket_key"),
           "CLUBCODERS_LIVE_FILE": os.path.join(desk_data, "live.json")}
    desk = subprocess.Popen([sys.executable, os.path.join(DESK, "club_desk.py"), "--port", str(desk_port), "--games",
                             os.path.join(work, "games.json")], env=env,
                            stdout=open(os.path.join(work, "desk.log"), "w"), stderr=subprocess.STDOUT)
    wait_port(desk_port)  # (the desk makes the ticket key first; the kart server reads it at each ticket)
    server = subprocess.Popen([sys.executable, "kart_server.py", "--port", str(kart_port), "--cpu", "2",
                               "--level", "easy", "--laps", "2"], cwd=KART, env={**env, "TEACHER_CODE": "TEACH99"},
                              stdout=open(os.path.join(work, "server.log"), "w"), stderr=subprocess.STDOUT)
    http = subprocess.Popen([sys.executable, "-m", "http.server", str(http_port), "--bind", "127.0.0.1"], cwd=HERE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = None
    try:
        if not wait_port(kart_port) or not wait_port(http_port) or not wait_port(desk_port):
            raise RuntimeError("the kart server, the desk or the static server didn't start")
        chrome = Chrome(exe, os.path.join(work, "profile"))
        base = f"http://127.0.0.1:{http_port}/index.html?desk=ws://127.0.0.1:{desk_port}&auto=0&cam=tv&tier=low"

        def wrong_password():
            chrome.open(base)
            chrome.wait_for("!!window.__state && !!window.__state.scene && !document.getElementById('deskform').hidden",
                            20, "the page's script and the teacher password box")
            chrome.js("document.getElementById('deskpass').value = 'not-the-password'; document.getElementById('connect').click()")
            text = chrome.wait_for("document.getElementById('status').textContent.includes('teacher password') && "
                                   "document.getElementById('status').textContent", 10, "the desk refusing")
            assert "isn't the teacher password" in text, text
            assert chrome.js("window.__state.connected") is False
        check("The desk refuses a wrong teacher password", wrong_password)

        def desk_login():  # (typed into the box, as the teacher does: never in the page's address)
            chrome.js(f"document.getElementById('deskpass').value = {json.dumps(DESK_PASSWORD)}; "
                      "document.getElementById('connect').click()")
            chrome.wait_for("window.__state.connected === true", 30, "the login with the desk's ticket")
            assert chrome.js("window.__state.ticket && window.__state.ticket.game") == "kartlab"
            assert "Teacher" in open(os.path.join(work, "server.log"), encoding="utf-8").read()
        check("The teacher password logs in through the desk, which gives a ticket for the Kart Lab class", desk_login)

        def logged_in():
            chrome.wait_for("window.__state && window.__state.connected === true", 30, "the teacher's login")
            chrome.wait_for("window.__state.snaps.length > 10 && !!window.__state.roster", 20, "snapshots and the roster")
            assert chrome.js("window.__state.game") == "kartlab"
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("The page logs in as the teacher and receives snapshots and the roster", logged_in)

        def draws():
            meshes = chrome.js("window.__state.scene.trackMeshes.length")
            assert meshes > 10, f"only {meshes} track meshes"
            karts = chrome.js("window.__state.scene.karts.size")
            assert karts >= 3, f"{karts} karts drawn (teacher + 2 computer karts expected)"
            moving = chrome.js("(() => { const s = window.__state.snaps; const a = s[0].entities, b = s[s.length - 1].entities;"
                               " return a.some(e => { const n = b.find(x => x.id === e.id); return n && Math.hypot(n.x - e.x, n.y - e.y) > 0.5; }); })()")
            assert moving, "no kart moved between the first and last snapshot"
            info = chrome.js("JSON.stringify(window.__state.scene.gpuInfo())")
            print(f"    browser: {info}")
            assert chrome.js("document.getElementById('places').children.length") >= 3
        check("The track and the karts are drawn, and the karts move", draws)

        def controls():
            assert chrome.js("window.__state.lesson.mode") == "practice"
            chrome.js("document.getElementById('btn-start').click()")
            chrome.wait_for("window.__state.lesson.mode === 'race'", 10, "race mode after START A RACE")
            chrome.wait_for("!!document.getElementById('btn-start') && document.getElementById('btn-start').textContent !== 'START A RACE'", 10, "the button renaming itself")
            chrome.js("document.getElementById('btn-start').click()")
            chrome.wait_for("window.__state.race && window.__state.race.phase === 1", 10, "the race starting")
            chrome.js("document.getElementById('btn-grid').click()")
            chrome.wait_for("window.__state.race && window.__state.race.phase === 0", 10, "everyone back on the grid")
            chrome.js("document.querySelector('button[data-mission=\"2\"]').click()")
            chrome.wait_for("window.__state.lesson.lesson_number === 2", 10, "mission 2")
            chrome.js("const s = document.getElementById('sel-track'); s.value = 'oval'; s.dispatchEvent(new Event('change'))")
            chrome.wait_for("window.__state.track && window.__state.track.name === 'Test Oval'", 10, "the oval")
            chrome.wait_for("window.__state.scene.track && window.__state.scene.track.name === 'Test Oval'", 10, "the oval drawn")
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("START A RACE, TO THE GRID, the mission buttons and the track picker reach the server", controls)

        def tiers():
            for tier in ("blocks", "high", "low"):
                chrome.js(f"window.__state.scene.setTier('{tier}')")
                time.sleep(1.0)
                assert chrome.js("window.__state.scene.tier") == tier
                assert chrome.js("window.__state.scene.trackMeshes.length") > 10
                assert chrome.js("window.__state.scene.karts.size") >= 3
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("The graphics tier changes without losing the track or the karts", tiers)

        def learners_tab():
            chrome.js("document.querySelector('#panel header button[data-tab=\"learners\"]').click(); document.getElementById('panel').classList.add('open')")
            rows = chrome.wait_for("document.querySelectorAll('#panelbody table tr').length", 5, "the Learners table")
            assert rows >= 2, f"{rows} rows"
            assert "Teacher" in chrome.js("document.getElementById('panelbody').textContent")
        check("The Learners tab lists who is here", learners_tab)

        shot = os.path.join(work, "live.png")
        chrome.screenshot(shot)

        def code_login():  # the other way in: a class server's own code (a laptop test server)
            chrome.call("Page.navigate", url="about:blank")  # (the desk's teacher lets go of the class first)
            time.sleep(1.5)
            chrome.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/index.html?host=ws://127.0.0.1:{kart_port}"
                                             f"&code=TEACH99&autoconnect=1&auto=0&tier=blocks")
            chrome.wait_for("window.__state && window.__state.connected === true", 30, "the login with the class code")
            assert chrome.js("window.__state.codeMode") is True
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("A class server's code still works (laptop test servers)", code_login)
        print(f"Screenshot and test data: {work}")
    finally:
        if chrome:
            chrome.close()
        stop(server)
        stop(http)
        stop(desk)
    for name, ok, note in results:
        if not ok:
            print(f"FAIL {name}\n    {note}")
    print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
