"""Club Coders Live: the browser page against a laptop Kart Lab server, driven through headless Chrome.

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\web_test.py      (from the ClubCodersAI folder)

Starts a club desk, a Kart Lab test server and a static server for this folder, opens the page in headless Chrome
(Google Chrome or Microsoft Edge, whichever is installed) over the DevTools protocol, and checks: a wrong teacher
password is refused; the right one opens the Teacher screen (the desk): learners added, a group made and launched,
which opens the class view with the desk's teacher ticket; the page draws the track and the karts from the server's
snapshots with no JavaScript errors;
START A RACE, TO THE GRID, a mission button and the track picker reach the server and come back in the lesson; the
graphics tier can be changed; then a note, LAUNCH LEARNERS' WINDOWS, STOP and the printed record, a password reset,
a learner removed, login slips, the teacher password changed; a learner's own page: her Garage drawn from the
game's schema, her code panel (APPLY CODE changes a value, a mistake is shown on its line, BUILD reaches the
server); the teacher's own garage in Robot Lab and Fight Lab; lessons.json, schemas.json and tex/ are up to date,
and schema_test.py passes (schema.js against the windows' Python). Screenshots are
kept in the test folder. Exit code 0 = every check passed; the test
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
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# the kart game: games/kartlab beside web/ in the public repository and the app, kart/ two folders up in the
# working folder (club-coders/web/)
KART = next((p for p in (os.path.join(os.path.dirname(HERE), "games", "kartlab"),
                         os.path.join(os.path.dirname(os.path.dirname(HERE)), "kart"))
             if os.path.isdir(p)), None)
DESK = os.path.join(os.path.dirname(HERE), "desk")  # (club-coders/desk, or desk/ in the public repository)


def game_folder(public, dev):  # (games/<game> in the public repository, the game's own folder in the working one)
    return next((p for p in (os.path.join(os.path.dirname(HERE), "games", public),
                             os.path.join(os.path.dirname(os.path.dirname(HERE)), dev)) if os.path.isdir(p)), None)


ROBOT, FIGHT = game_folder("robotlab", "shared-world-demo"), game_folder("fightlab", "BeatEmUp")
DESK_PASSWORD = "web-test-teacher-password"
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]

results = []


# (in the page) the scene drawn properly on a tier: on low and up the app's lighting (pbr.js) in use with every picture
# loaded, no mesh left holding a material that was thrown away, and no more pixels drawn than the tier allows
DRAWN_RIGHT = """(() => {
    const g = window.__state.scene, sc = g.scene, eng = sc.getEngine();
    const pbr = sc.materials.filter(m => m.getClassName() === 'ShaderMaterial' && m.name !== 'ccdepth');
    if (g.tier !== 'blocks' && !pbr.length) return 'no pbr materials on ' + g.tier;
    // (a headless picture ignores the canvas's alpha: a material whose alpha isn't a number draws nothing in a real
    // window, as 1.9.6 did, so the alpha is checked here and the canvas must be opaque)
    const noAlpha = pbr.filter(m => !(m._colors4 && m._colors4.baseColor && m._colors4.baseColor.a > 0)).map(m => m.name.split(':')[0]);
    if (noAlpha.length) return 'materials with no alpha: ' + noAlpha.slice(0, 5).join(', ');
    if (eng._gl.getContextAttributes().alpha) return 'the canvas is see-through';
    const waiting = pbr.filter(m => Object.values(m._textures || {}).some(t => !t.isReady())).map(m => m.name.split(':')[0]);
    if (waiting.length) return 'pictures not loaded: ' + waiting.slice(0, 5).join(', ');
    // (a shader that doesn't compile draws nothing and throws nothing: the effects' particles went missing that way)
    const broken = Object.values(eng._compiledEffects || {}).concat(sc.materials.map(m => m.getEffect && m.getEffect()))
        .filter(e => e && e.getCompilationError && e.getCompilationError()).map(e => e.name && (e.name.vertex || e.name.vertexElement || e.name) || '?');
    if (broken.length) return 'shaders that did not compile: ' + broken.slice(0, 3).map(String).join(', ');
    const lost = sc.meshes.filter(x => x.material && !sc.materials.includes(x.material)).map(x => x.name);
    if (lost.length) return 'meshes with a thrown-away material: ' + lost.slice(0, 5).join(', ');
    const budget = {blocks: 1.0e6, low: 1.1e6, medium: 1.6e6, high: 2.4e6}[g.tier];
    const px = eng.getRenderWidth() * eng.getRenderHeight();
    const css = window.innerWidth * window.innerHeight * Math.min(1, devicePixelRatio);
    if (px > Math.max(budget, css) * 1.02) return 'drawing ' + px + ' pixels on ' + g.tier;
    return 'ok';
})()"""


class StaticServer:
    """This folder over http (python -m http.server's handler), with Fight Lab's models at models/fightlab/ as the
    VPS serves them (Caddy: the release's games/fightlab/models)."""

    def __init__(self, port):
        from functools import partial
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import unquote, urlsplit
        models = os.path.join(FIGHT, "models") if FIGHT else None

        class Handler(SimpleHTTPRequestHandler):
            def translate_path(self, path):
                p = unquote(urlsplit(path).path)
                if p.startswith("/models/fightlab/"):
                    if not models:
                        return os.path.join(HERE, "no-such-file")
                    full = os.path.normpath(os.path.join(models, *p[len("/models/fightlab/"):].split("/")))
                    return full if full.startswith(models + os.sep) else os.path.join(HERE, "no-such-file")
                return super().translate_path(path)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, directory=HERE))
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def poll(self):  # (stop() treats it as a process)
        return None

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


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
    if isinstance(proc, StaticServer):
        proc.stop()
        return
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


class Learner:
    """A learner's window, scripted: logs in with the laptop server's learner code (a new name makes a profile)
    and keeps reading, so the teacher sees someone in the class."""

    def __init__(self, port, name):
        from websockets.sync.client import connect
        self.ws = connect(f"ws://127.0.0.1:{port}", max_size=None, open_timeout=20)
        self.ws.send(json.dumps({"type": "hello", "name": name, "code": "CLUB42", "password": name + "-pass-1",
                                 "version": ""}))
        self.notes = []
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            while True:
                m = self.ws.recv()
                if isinstance(m, str):
                    t = json.loads(m)
                    if t.get("type") in ("notice", "ai_card_result", "design_result"):
                        self.notes.append(t)
        except Exception:
            pass

    def send(self, msg):
        self.ws.send(json.dumps(msg))

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


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
    http = StaticServer(http_port)
    chrome = None
    extra = []  # (Claude for the browser)
    try:
        if not wait_port(kart_port) or not wait_port(http_port) or not wait_port(desk_port):
            raise RuntimeError("the kart server, the desk or the static server didn't start")
        chrome = Chrome(exe, os.path.join(work, "profile"))
        base = f"http://127.0.0.1:{http_port}/index.html?mode=teacher&desk=ws://127.0.0.1:{desk_port}&auto=0&cam=tv&tier=low"

        def wrong_password():
            chrome.open(base)
            chrome.wait_for("!!window.__state && !!window.__state.engine && !document.getElementById('deskform').hidden",
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
            chrome.wait_for("!document.getElementById('desk').hidden && window.__state.desk && window.__state.desk.ready",
                            20, "the Teacher screen")
            assert chrome.js("document.getElementById('deskpass').value") == "", "the password box wasn't emptied"
            assert chrome.js("window.__state.desk.state.live") is None
            assert "TEACHER DESK" in chrome.js("document.getElementById('deskbody').textContent")
        check("The teacher password opens the Teacher screen (the desk)", desk_login)

        def people():
            for name, starter in (("amy", "starter-amy"), ("ben", "")):
                chrome.js(f"document.getElementById('new-user').value = {json.dumps(name)}; "
                          f"document.getElementById('new-starter').value = {json.dumps(starter)}; "
                          "document.getElementById('dk-add').click()")
                chrome.wait_for(f"window.__state.desk.state.learners.some(L => L.name === {json.dumps(name)})", 10, f"{name} added")
            assert chrome.js("window.__state.desk.state.learners.find(L => L.name === 'amy').starter") == "starter-amy"
            assert chrome.js("window.__state.desk.state.learners.find(L => L.name === 'ben').starter.split('-').length") == 3
            assert "starter-amy" in chrome.js("document.getElementById('deskbody').textContent")
            chrome.js("document.getElementById('dk-newgroup').click()")
            chrome.wait_for("!!document.getElementById('g-name')", 5, "the group editor")
            chrome.js("{ const t = (id, v) => { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('input')); };"
                      "t('g-name', 'Year 7'); t('g-time', 'someday');"
                      "document.querySelectorAll('input[data-tick]').forEach(b => b.click());"
                      "document.getElementById('g-save').click(); }")
            chrome.wait_for("document.getElementById('dk-msg').textContent.includes('day and a time')", 10, "the desk refusing the time")
            assert chrome.js("!!document.getElementById('g-name')"), "the editor closed on an error"
            chrome.js("{ const e = document.getElementById('g-time'); e.value = 'tue 16:00'; e.dispatchEvent(new Event('input'));"
                      "document.getElementById('g-save').click(); }")
            chrome.wait_for("window.__state.desk.state.groups.length === 1", 10, "the group saved")
            g = chrome.js("JSON.stringify(window.__state.desk.state.groups[0])")
            chrome.screenshot(os.path.join(work, "people.png"))
            assert '"time":"Tuesday 16:00"' in g and '"learners":["amy","ben"]' in g and '"game":"kartlab"' in g, g
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("Learners are added (a starter password made up when left blank) and a group is made", people)

        def launch():
            chrome.js("document.querySelector('button[data-launch=\"0\"][data-lesson=\"2\"]').click()")
            chrome.wait_for("window.__state.desk.state.live && window.__state.desk.state.live.group === 'Year 7'", 10, "Year 7 live")
            chrome.wait_for("window.__state.connected === true", 30, "the class view opening by itself (a Kart Lab group)")
            assert chrome.js("window.__state.ticket && window.__state.ticket.game") == "kartlab"
            assert chrome.js("document.getElementById('desk').hidden") is True
            assert "LIVE: Year 7" in chrome.js("document.getElementById('btn-desk').textContent")
            assert "Teacher" in open(os.path.join(work, "server.log"), encoding="utf-8").read()
            # (the class server takes up the lesson within 2 s: the controls below start after it has)
            chrome.wait_for("window.__state.events.some(e => e.includes('Session started'))", 10, "the class server starting the session")
        check("Launch puts the group live and opens the Kart Lab view with the desk's teacher ticket", launch)

        def logged_in():
            chrome.wait_for("window.__state && window.__state.connected === true", 30, "the teacher's login")
            chrome.wait_for("window.__state.snaps.length > 10 && !!window.__state.roster", 20, "snapshots and the roster")
            assert chrome.js("window.__state.game.id") == "kartlab"
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
            chrome.js("document.querySelector('button[data-mission=\"3\"]').click()")
            chrome.wait_for("window.__state.lesson.lesson_number === 3", 10, "mission 3")
            chrome.js("{ const s = document.getElementById('sel-track'); s.value = 'oval'; s.dispatchEvent(new Event('change')); }")
            chrome.wait_for("window.__state.game.track && window.__state.game.track.name === 'Test Oval'", 10, "the oval")
            chrome.wait_for("window.__state.scene.track && window.__state.scene.track.name === 'Test Oval'", 10, "the oval drawn")
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("START A RACE, TO THE GRID, the mission buttons and the track picker reach the server", controls)

        def tiers():
            for tier in ("blocks", "high", "medium", "low"):
                chrome.js(f"window.__state.scene.setTier('{tier}')")
                time.sleep(1.0)
                assert chrome.js("window.__state.scene.tier") == tier
                assert chrome.js("window.__state.scene.trackMeshes.length") > 5
                assert chrome.js("window.__state.scene.karts.size") >= 3
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 15, f"Kart Lab drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                chrome.screenshot(os.path.join(work, f"kartlab_{tier}.png"))
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("The graphics tiers (blocks, low, medium, high: the app's lighting and textures) keep the track and the karts, "
              "load every picture and keep to their pixel budgets", tiers)

        def learners_tab():
            chrome.js("document.querySelector('#panel header button[data-tab=\"learners\"]').click(); document.getElementById('panel').classList.add('open')")
            rows = chrome.wait_for("document.querySelectorAll('#panelbody table tr').length", 5, "the Learners table")
            assert rows >= 2, f"{rows} rows"
            assert "Teacher" in chrome.js("document.getElementById('panelbody').textContent")
        check("The Learners tab lists who is here", learners_tab)

        def claude_cards():  # (CHANGE 136: Claude for the browser on a copy of Kart Lab, a stand-in for Claude)
            rules = os.path.join(KART, "mods", "rules.py")  # (the class server writes a kept mod into its own mods/)
            with open(rules, "rb") as f:
                before = f.read()
            try:
                claude_cards_steps()
            finally:
                with open(rules, "wb") as f:
                    f.write(before)

        def claude_cards_steps():
            copy = os.path.join(work, "claude")
            shutil.copytree(KART, os.path.join(copy, "kart"), ignore=shutil.ignore_patterns(
                ".venv", "__pycache__", "data", "profiles", "evidence", "ai_changes", "ai_requests", "brains", "assets"))
            shutil.copytree(os.path.join(os.path.dirname(KART), "engine") if os.path.isdir(os.path.join(os.path.dirname(KART), "engine"))
                            else os.path.join(os.path.dirname(os.path.dirname(KART)), "engine"), os.path.join(copy, "engine"),
                            ignore=shutil.ignore_patterns("__pycache__", "assets"))
            with open(os.path.join(copy, "fake_claude.py"), "w", encoding="utf-8") as f:
                f.write("import json, os\np = os.path.join('mods', 'rules.py')\nt = open(p, encoding='utf-8', newline='').read()\n"
                        "open(p, 'w', encoding='utf-8', newline='').write(t.replace('\"laps\": 3,', '\"laps\": 4,', 1))\n"
                        "print(json.dumps({'result': '- mods/rules.py: laps 3 -> 4', 'total_cost_usd': 0}))\n")
            helper = subprocess.Popen(
                [sys.executable, os.path.join(os.path.dirname(HERE), "helper", "claude_helper.py"), "--server",
                 f"ws://127.0.0.1:{desk_port}", "--password-stdin", "--games", "kartlab"], stdin=subprocess.PIPE,
                env={**env, "CLUBCODERS_KARTLAB_DIR": os.path.join(copy, "kart"), "KARTLAB_DATA": os.path.join(copy, "data"),
                     "CLAUDE_CMD": f'"{sys.executable}" "{os.path.join(copy, "fake_claude.py")}"'},
                stdout=open(os.path.join(work, "helper.log"), "w"), stderr=subprocess.STDOUT)
            extra.append(helper)
            helper.stdin.write((DESK_PASSWORD + "\n").encode())
            helper.stdin.flush()
            chrome.wait_for("!!window.__state.desk.claudeFor('kartlab') && !!window.__state.desk.claudeFor('kartlab').history", 40,
                            "Claude for the browser connected")
            chrome.js("window.__app.send({type: 'ai_card', card: {goal: 'One more lap', variables: 'laps = 4', test: 'Start a race and count the laps it shows', "
                      "predict: 'Four laps', target: 'rules', privacy: true, review: true, credit: true}})")
            chrome.js("document.querySelector('#panel header button[data-tab=\"cards\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-ccheck]')", 15, "the card's Check and send")
            assert chrome.js("document.querySelector('button[data-ctarget=\"rules\"]').classList.contains('on')")
            chrome.js("document.querySelector('button[data-ccheck]').click()")
            chrome.wait_for("(document.querySelector('pre.prompt') || {}).textContent.includes('mods/rules.py') && "
                            "!document.getElementById('c-send').disabled", 20, "the whole prompt, from Claude's computer")
            chrome.screenshot(os.path.join(work, "claude_check.png"))
            chrome.js("document.getElementById('c-send').click()")
            chrome.wait_for("!!document.querySelector('button[data-ckeep]')", 60, "the tested change, with Keep and Undo")
            assert "Test: passed" in chrome.js("document.querySelector('pre.claude').textContent")
            assert chrome.js("window.__state.teaching.cards.slice(-1)[0].status") == "working"
            chrome.js("document.querySelector('button[data-cdiff]').click()")
            chrome.wait_for("((document.querySelector('pre.diff .add') || {}).textContent || '').trim() === '+    \"laps\": 4,                 # laps in a race (1 to 9)'",
                            5, "the change's lines")
            chrome.screenshot(os.path.join(work, "claude_result.png"))
            chrome.js("document.querySelector('button[data-ckeep]').click()")
            chrome.wait_for("window.__state.teaching.cards.slice(-1)[0].status === 'ready'", 15, "the card kept for the learner")
            chrome.js("document.querySelector('#panel header button[data-tab=\"changes\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-mswitch=\"1\"]')", 15, "mod 1 in the Changes tab")
            chrome.js("document.querySelector('button[data-mswitch=\"1\"]').click()")
            chrome.wait_for("document.getElementById('panelbody').textContent.includes('Mod 1 switched off')", 15, "mod 1 switched off")
            assert '"laps": 3,' in open(os.path.join(copy, "kart", "mods", "rules.py"), encoding="utf-8").read()
            chrome.screenshot(os.path.join(work, "claude_changes.png"))
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("Claude for the browser: a card checked (the whole prompt), sent, tested, its lines shown, kept; the Changes tab "
              "switches the mod off", claude_cards)

        shot = os.path.join(work, "live.png")
        chrome.screenshot(shot)
        pupil = {}

        def learner_login():  # a learner's own page (another browser): the desk login, a starter password changed, waiting
            pupil["chrome"] = lc = Chrome(exe, os.path.join(work, "profile-amy"))
            lc.open(f"http://127.0.0.1:{http_port}/index.html?mode=learner&desk=ws://127.0.0.1:{desk_port}&auto=0&tier=blocks")
            lc.wait_for("!!window.__state && !document.getElementById('learnerform').hidden", 20, "the learner's login form")
            lc.js("document.getElementById('lname').value = 'amy'; document.getElementById('lpass').value = 'starter-amy';"
                  "document.getElementById('connect').click()")
            lc.wait_for("!document.getElementById('newpassform').hidden", 15, "the desk asking for her own password")
            lc.js("document.getElementById('npass').value = 'amys-own-1'; document.getElementById('npass2').value = 'amys-own-1';"
                  "document.getElementById('connect').click()")
            lc.wait_for("!document.getElementById('waitbox').hidden && document.getElementById('waittext').textContent.includes('wait')",
                        15, "waiting for the teacher (the learners' windows aren't launched yet)")
            assert lc.js("JSON.stringify(window.__errors)") == "[]"
        check("A learner logs in at the desk from the page: her own password first, then waiting for the teacher", learner_login)

        def session():
            chrome.js("document.getElementById('btn-desk').click()")
            chrome.wait_for("!document.getElementById('desk').hidden && !!document.querySelector('input[data-name=\"amy\"]')",
                            5, "This session on the desk")
            chrome.js("{ const n = document.querySelector('input[data-name=\"amy\"]'); n.value = 'Tuned her kart well';"
                      "document.querySelector('button[data-note=\"' + n.id.slice(5) + '\"]').click(); }")
            chrome.wait_for("(window.__state.desk.state.session.notes || {}).amy === 'Tuned her kart well'", 10, "the note saved")
            chrome.js("{ const n = document.querySelector('input[data-name=\"ben\"]'); n.focus(); n.value = 'half-typ'; }")
            chrome.js("document.getElementById('dk-open').click()")
            chrome.wait_for("window.__state.desk.state.live.learners_in === true", 10, "the learners' windows launched")
            if "chrome" in pupil:  # (the learner's page opens the game by itself, as the app does)
                lc = pupil["chrome"]
                lc.wait_for("window.__state.connected === true && window.__state.role === 'learner' && window.__state.game.id === 'kartlab'",
                            30, "amy's page opening Kart Lab as a learner")
                lc.wait_for("window.__state.game.myId() !== null && !!document.getElementById('kh-lap')", 20, "amy's kart and race display")
                tabs = lc.js("[...document.querySelectorAll('#panelhead button')].map(b => b.dataset.tab).join(',')")
                assert tabs.startswith("mission,garage,aicard,mycard,mods"), tabs
                lc.screenshot(os.path.join(work, "learner_kart.png"))
            assert chrome.js("document.querySelector('input[data-name=\"ben\"]').value") == "half-typ", \
                "typing was lost when the desk redrew"
            chrome.screenshot(os.path.join(work, "desk.png"))
        check("The session: a note, LAUNCH LEARNERS' WINDOWS, and the learner's page opens the game", session)

        def learner_garage():  # amy's Garage drawn from the schema; the code panel: APPLY CODE changes a value, BUILD
            if "chrome" not in pupil:
                return
            lc = pupil["chrome"]
            lc.js("const s = window.__app.send; window.__sent = []; window.__app.send = m => { window.__sent.push(m); s(m); };"
                  "document.getElementById('panel').classList.add('open');"
                  "document.querySelector('#panelhead button[data-tab=\"garage\"]').click()")
            lc.wait_for("!!document.getElementById('gz-build')", 10, "amy's Garage")
            # (the rows are the schema's: garageTables gives the same names the page shows)
            names = lc.js("[...document.querySelectorAll('#panelbody .gname')].map(e => e.textContent).join(',')")
            assert "GARAGE" in lc.js("document.getElementById('panelbody').textContent"), "no garage title"
            # (a learner's garage shows a variable when its tool is on: engine/garage.py's visible())
            for v in lc.js("window.__state.schemas.kartlab.vars.filter(v => !v.tool || window.__state.lesson.tools[v.tool]).map(v => v.name)"):
                assert v in names, f"{v} isn't in the garage ({names})"
            lc.screenshot(os.path.join(work, "learner_garage.png"))
            lc.js("document.getElementById('gz-code').click()")
            lc.wait_for("!document.getElementById('codepanel').hidden && document.getElementById('code-text').value.includes('speed: int =')",
                        10, "the code panel with amy's kart as Python")
            assert any(m.get("type") == "code_viewed" for m in lc.js("window.__sent")), "code_viewed wasn't sent"
            speed = lc.js("window.__state.draft.speed")
            lc.js("{ const t = document.getElementById('code-text');"
                  f" t.value = t.value.replace(/^speed: int = \\d+$/m, 'speed: int = {speed - 1}');"
                  " t.dispatchEvent(new Event('input')); document.getElementById('code-apply').click(); }")
            lc.wait_for(f"window.__state.draft.speed === {speed - 1} && window.__state.codeChanged === true", 10, "the code applied")
            assert "Applied" in lc.js("document.getElementById('code-msg').textContent"), lc.js("document.getElementById('code-msg').textContent")
            lc.wait_for(f"document.getElementById('panelbody').textContent.includes('{speed - 1}')", 5, "the garage showing the new value")
            lc.js("{ const t = document.getElementById('code-text'); t.value = t.value + '\\nx = [1, 2'; t.dispatchEvent(new Event('input'));"
                  " document.getElementById('code-apply').click(); }")
            lc.wait_for("document.getElementById('code-msg').textContent.includes('was never closed')", 5, "the mistake shown")
            assert lc.js("document.querySelector('#code-gutter b') !== null"), "the line with the mistake isn't marked"
            lc.screenshot(os.path.join(work, "learner_code.png"))
            lc.js("document.getElementById('code-reset').click(); document.getElementById('gz-build').click()")
            lc.wait_for(f"window.__state.myDesign.speed === {speed - 1}", 10, "the server building amy's kart from her code")
            sent = [m for m in lc.js("window.__sent") if m.get("type") == "design"]
            assert sent and sent[-1]["code"] is True, sent
            assert lc.js("window.__state.codeChanged") is False, "the code flags weren't cleared by the build"
            assert lc.js("JSON.stringify(window.__errors)") == "[]", lc.js("JSON.stringify(window.__errors)")
        check("A learner's Garage is drawn from the game's schema, and her code panel: APPLY CODE changes a value, a "
              "mistake is shown on its line, BUILD reaches the server (sent as code)", learner_garage)

        def session_stop():
            chrome.js("document.getElementById('dk-stop').click()")
            assert chrome.js("window.__state.desk.state.live") is not None, "one press stopped it"
            chrome.js("document.getElementById('dk-stop').click()")
            chrome.wait_for("window.__state.desk.state.live === null && !!window.__state.desk.record", 10, "the session stopped")
            chrome.wait_for("window.__state.connected === false", 10, "the class view closing at Stop")
            if "chrome" in pupil:  # (and back to waiting when the teacher stops)
                pupil["chrome"].wait_for("!document.getElementById('waitbox').hidden", 20, "amy's page waiting again after Stop")
                assert pupil["chrome"].js("JSON.stringify(window.__errors)") == "[]"
                pupil["chrome"].close()
            chrome.wait_for("(window.__state.desk.sessions || []).length === 1 && !!document.querySelector('button[data-print]')",
                            10, "the record in Records")
            chrome.js("window.print = () => { window.__printed = (window.__printed || 0) + 1; };"
                      "document.querySelector('button[data-print]').click()")
            chrome.wait_for("window.__printed === 1", 5, "the print box")
            text = chrome.js("document.getElementById('printout').textContent")
            with open(os.path.join(work, "records.pdf"), "wb") as f:  # (what the print box would make)
                f.write(base64.b64decode(chrome.call("Page.printToPDF", preferCSSPageSize=True)["data"]))
            for want in ("Session summary: Year 7", "Learner card: amy", "Tuned her kart well", "Kart Lab", "Variables"):
                assert want in text, f"{want!r} isn't in the printed record"
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("STOP (pressed twice) ends the session; its printed record", session_stop)

        def reset_remove():
            chrome.js("document.querySelector('button[data-dtab=\"people\"]').click()")
            before = chrome.js("window.__state.desk.state.learners.find(L => L.name === 'ben').starter")
            chrome.js("document.querySelector('button[data-reset=\"1\"]').click()")
            chrome.wait_for(f"window.__state.desk.state.learners.find(L => L.name === 'ben').starter !== {json.dumps(before)}",
                            10, "ben's new starter password")
            # (amy chose her own password from her page: she's removed, and ben's slip, with his new starter, is printed)
            chrome.js("document.querySelector('button[data-remove=\"0\"]').click()")
            assert chrome.js("window.__state.desk.state.learners.length") == 2, "one press removed amy"
            chrome.js("document.querySelector('button[data-remove=\"0\"]').click()")
            chrome.wait_for("window.__state.desk.state.learners.length === 1", 10, "amy removed")
            chrome.wait_for("!!document.getElementById('dk-slips')", 5, "the login slips button")
            chrome.js("document.getElementById('dk-slips').click()")
            starter = chrome.js("window.__state.desk.state.learners.find(L => L.name === 'ben').starter")
            assert starter and starter in chrome.js("document.getElementById('printout').textContent")
        check("A learner's password is reset, a learner removed (pressed twice), login slips printed", reset_remove)

        def change_password():
            new = "web-test-new-teacher-password"
            chrome.js("document.querySelector('button[data-dtab=\"password\"]').click()")
            chrome.js(f"document.getElementById('pw-now').value = {json.dumps(DESK_PASSWORD)};"
                      f"document.getElementById('pw-new').value = {json.dumps(new)};"
                      f"document.getElementById('pw-again').value = {json.dumps(new)};"
                      "document.getElementById('pw-change').click()")
            chrome.wait_for("document.getElementById('dk-msg').textContent.includes('is changed')", 10, "the password changed")
            chrome.js("document.getElementById('dk-logout').click()")
            chrome.wait_for("document.getElementById('login').style.display === 'grid'", 5, "the login screen")
            chrome.js(f"document.getElementById('deskpass').value = {json.dumps(DESK_PASSWORD)}; document.getElementById('connect').click()")
            chrome.wait_for("document.getElementById('status').textContent.includes('teacher password')", 10, "the old password refused")
            chrome.js(f"document.getElementById('deskpass').value = {json.dumps(new)}; document.getElementById('connect').click()")
            chrome.wait_for("!document.getElementById('desk').hidden && window.__state.desk && window.__state.desk.ready", 10,
                            "the new password logging in")
        check("The teacher password is changed from the page; the old one stops working", change_password)

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

        def no_errors():
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"

        def tab(name):
            chrome.js("document.getElementById('panel').classList.add('open');"
                      f"document.querySelector('#panelhead button[data-tab=\"{name}\"]').click()")
            time.sleep(0.3)

        game_env = {k: v for k, v in env.items() if not k.startswith("CLUBCODERS_")}
        game_env.update({"TEACHER_CODE": "TEACH99", "JOIN_CODE": "CLUB42"})
        servers = {}

        def start_server(key, folder, script, port, data_var):
            servers[key] = subprocess.Popen([sys.executable, script, "--port", str(port)], cwd=folder,
                                            env={**game_env, data_var: os.path.join(work, key)},
                                            stdout=open(os.path.join(work, key + ".log"), "a"), stderr=subprocess.STDOUT)
            if not wait_port(port, 60):
                raise RuntimeError(f"the {key} server didn't start")

        def open_game(port, game, extra=""):
            chrome.call("Page.navigate", url="about:blank")
            time.sleep(1.0)
            chrome.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/index.html?host=ws://127.0.0.1:{port}"
                                             f"&code=TEACH99&autoconnect=1&auto=0&tier=low{extra}")
            chrome.wait_for("window.__state && window.__state.connected === true && !!window.__state.game", 30, f"{game}'s login")
            assert chrome.js("window.__state.game.id") == game, chrome.js("window.__state.game.id")

        robot_port = free_port()

        def robot_lab():
            if ROBOT is None:
                print("    (Robot Lab isn't beside this folder: not tested)")
                return
            start_server("robotlab", ROBOT, "lab_server.py", robot_port, "ROBOTLAB_DATA")
            servers["amy"] = Learner(robot_port, "amy")
            open_game(robot_port, "robotlab", "&cam=overview")
            chrome.wait_for("window.__state.snaps.length > 10 && window.__state.scene.robots.size >= 3", 30,
                            "the robots (the teacher's, amy's and the computer's)")
            chrome.wait_for("window.__state.classList.some(p => p.name === 'amy')", 10, "amy in the class")
            for tier in ("blocks", "high", "medium", "low"):
                chrome.js(f"window.__state.scene.setTier('{tier}')")
                time.sleep(0.8)
                assert chrome.js("window.__state.scene.robots.size") >= 3, f"robots lost on {tier}"
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 15, f"Robot Lab drawn properly on {tier}")
            chrome.js("window.__app.send({type: 'restart'})")  # (new robots: the old ones go, their materials stay)
            time.sleep(3.0)
            chrome.wait_for(f"window.__state.scene.robots.size >= 3 && {DRAWN_RIGHT} === 'ok'", 20, "Robot Lab drawn properly after a restart")
            # B: the health bars just the title (Show) and back (Hide), kept on this computer (lab_client.toggle_hud)
            press_b = ("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'b'}));"
                       "window.dispatchEvent(new KeyboardEvent('keyup', {key: 'b'}))")
            chrome.js(press_b)
            chrome.wait_for("!document.querySelector('#places div[data-id]') && document.getElementById('rb-small').textContent === 'Show'"
                            " && localStorage.getItem('hud_small') === '1'", 5, "the health bars made small with B")
            chrome.js(press_b)
            chrome.wait_for("!!document.querySelector('#places div[data-id]') && document.getElementById('rb-small').textContent === 'Hide'"
                            " && localStorage.getItem('hud_small') === '0'", 5, "the health bars full again with B")
            time.sleep(1.0)
            chrome.screenshot(os.path.join(work, "robotlab.png"))
            no_errors()
        check("Robot Lab: the arena and the robots are drawn from its snapshots, on every tier; B makes the health bars small",
              robot_lab)

        def shared_tabs():
            if "amy" not in servers:
                return
            tab("rules")
            chrome.js("document.querySelector('input[data-tool=\"code_view\"]').click()")
            chrome.wait_for("window.__state.lesson.tools.code_view === false", 10, "code view switched off")
            chrome.js("document.querySelector('input[data-haz=\"saws\"]').click()")
            chrome.wait_for("window.__state.lesson.hazards.saws === true", 10, "the saws switched on")
            tab("outcomes")
            chrome.js("document.getElementById('oa-title').value = 'Explain your robot to a partner';"
                      "document.getElementById('oa-add').click()")
            added = chrome.wait_for("Object.keys(window.__state.teaching.edited['1'] || {}).find(k => k.startsWith('1t'))", 10,
                                    "the added objective")
            chrome.wait_for(f"!!document.querySelector('button[data-tick=\"{added}\"][data-who=\"amy\"]')", 10, "its tick button")
            chrome.js(f"document.querySelector('button[data-tick=\"{added}\"][data-who=\"amy\"]').click()")
            chrome.wait_for(f"window.__state.teaching.grid.amy.missions.includes('{added}')", 10,
                            "amy ticked for the teacher's own objective")
            chrome.js("document.getElementById('btn-missions-export').click()")
            chrome.wait_for("(window.__downloads || []).some(d => d.name.startsWith('missions_'))", 10, "the missions file")
            chrome.js("window.__app.send({type: 'missions_import', data: JSON.parse(window.__downloads.find(d => d.name.startsWith('missions_')).text)})")
            time.sleep(2.5)  # (an import used to break every teaching update after it)
            assert chrome.js("window.__state.connected && Date.now() - window.__state.teachingAt < 2000"), "teaching stopped after an import"
            chrome.js("document.getElementById('btn-export-csv').click()")
            csv = chrome.wait_for("((window.__downloads || []).find(d => d.name.startsWith('evidence_')) || {}).text", 10, "the evidence CSV")
            assert "amy" in csv and added in csv, csv[:300]
            servers["amy"].send({"type": "ai_card", "card": {"goal": "Make my robot bright green", "variables": "colour = [0, 255, 0]",
                                                            "test": "Build it then drive round the arena and look at it",
                                                            "predict": "It turns green", "privacy": True, "review": True,
                                                            "credit": True, "target": "robot"}})
            tab("cards")
            chrome.wait_for("(window.__state.teaching.cards || []).length >= 1 && !!document.querySelector('button[data-cst=\"rejected\"]')",
                            10, "amy's AI card on the page")
            chrome.js("document.querySelector('button[data-cst=\"rejected\"]').click()")
            chrome.wait_for("window.__state.teaching.cards[0].status === 'rejected'", 10, "the card sent back")
            tab("learners")
            chrome.js("document.querySelector('button[data-pick=\"amy\"]').click()")
            chrome.wait_for("window.__state.viewing && window.__state.viewing.for === 'amy' && document.getElementById('panelbody').textContent.includes('Mission')",
                            10, "amy's mission")
            chrome.js("document.querySelector('button[data-sub=\"build\"]').click()")
            time.sleep(0.3)
            chrome.js("document.getElementById('dz-name').value = 'Zap'; document.getElementById('dz-build').click()")
            chrome.wait_for("window.__state.classList.some(p => p.name === 'amy' && p.design.name === 'Zap')", 10, "amy's robot rebuilt as Zap")
            chrome.screenshot(os.path.join(work, "robotlab_their_robot.png"))
            chrome.js("document.querySelector('button[data-pick=\"*me\"]').click()")
            chrome.wait_for("!!document.getElementById('dz-build') && document.getElementById('panelbody').textContent.includes('MY ROBOT')",
                            10, "the teacher's own garage")
            chrome.js("document.querySelector('button[data-choice=\"weapon\"][data-i=\"2\"]').click()")
            chrome.wait_for("window.__state.draft.weapon === 'drum'", 5, "a weapon chosen in the garage")
            chrome.screenshot(os.path.join(work, "robotlab_garage.png"))
            for t in ("warnings", "camera", "graphics", "about", "controls"):
                tab(t)
            chrome.screenshot(os.path.join(work, "robotlab_panel.png"))
            no_errors()
        check("The shared teacher tabs: a tool and a hazard, an objective added and ticked, missions out and back in, "
              "the evidence CSV, an AI card sent back, a learner's mission and robot", shared_tabs)

        def restart():
            if "robotlab" not in servers:
                return
            tab("controls")
            chrome.js("document.getElementById('btn-restart-server').click()")
            chrome.js("document.getElementById('btn-restart-server').click()")
            end = time.time() + 15
            while servers["robotlab"].poll() is None and time.time() < end:
                time.sleep(0.2)
            assert servers["robotlab"].poll() is not None, "the server didn't restart"
            start_server("robotlab", ROBOT, "lab_server.py", robot_port, "ROBOTLAB_DATA")  # (as its .bat would)
            chrome.wait_for("window.__state.connected === true && window.__state.reconnects === 0 && window.__state.snaps.length > 5", 40,
                            "the page reconnecting by itself")
            no_errors()
        check("Restart server (pressed twice): the page reconnects by itself", restart)

        def fight_lab():
            if FIGHT is None:
                print("    (Fight Lab isn't beside this folder: not tested)")
                return
            port = free_port()
            start_server("fightlab", FIGHT, "fight_server.py", port, "FIGHTLAB_DATA")
            servers["ben"] = Learner(port, "ben")
            open_game(port, "fightlab", "&cam=tv")
            chrome.wait_for("window.__state.snaps.length > 10 && window.__state.scene.fighters.size >= 2", 30, "the fighters")
            chrome.wait_for("[...window.__state.scene.fighters.values()].some(f => Math.abs(f.n.rs.rotation.x) > 0.2)", 10,
                            "a fighter in its stance (posed)")
            for tier in ("blocks", "high", "medium", "low"):
                chrome.js(f"window.__state.scene.setTier('{tier}')")
                time.sleep(0.8)
                assert chrome.js("window.__state.scene.fighters.size") >= 2, f"fighters lost on {tier}"
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 15, f"Fight Lab drawn properly on {tier}")
            # the detailed bodies (woman, man, Robin): the app's own skinned model and moves (fightmodels.js, the files
            # from models/fightlab/) on the lit tiers, posed every frame; the primitive stand-in on blocks
            chrome.js("window.__app.send({type: 'cpu_robot', design: {name: 'Ava', body: 'woman', colour: [200, 40, 40], "
                      "look: {outfit: 'hoplite', hair: 'ponytail', hair_colour: [70, 40, 25], shape: 'athletic', height: 100, win: 'victory'}}})")
            model = ("[...window.__state.scene.fighters.values()].some(f => f.design.body === 'woman' && f.model && f.model.ready"
                     " && !f.body.isEnabled() && f.model.meshes.length > 5)")
            chrome.wait_for(model, 60, "the computer's woman drawn from the app's model")
            print(f"    model load (ms): {chrome.js('JSON.stringify(window.__fightModels.loadTimes)')}")
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 20, "Fight Lab drawn properly with a model")
            chrome.wait_for("(() => { const f = [...window.__state.scene.fighters.values()].find(f => f.model && f.model.ready);"
                            " const q = f && f.model.joints[0] && f.model.joints[0].rotationQuaternion.asArray().join();"
                            " const moved = !!q && window.__hips !== undefined && window.__hips !== q; window.__hips = q; return moved; })()",
                            15, "the model's joints posed from its moves")
            chrome.screenshot(os.path.join(work, "fightlab_model.png"))
            chrome.js("window.__state.scene.setTier('blocks')")
            time.sleep(0.8)
            assert chrome.js("[...window.__state.scene.fighters.values()].every(f => !f.model)"), "a model on blocks"
            chrome.js("window.__state.scene.setTier('low')")
            chrome.wait_for(model, 30, "the model again after the tier changed")
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 20, "Fight Lab drawn properly with a model, again")
            tab("controls")
            chrome.js("document.querySelector('button[data-mode=\"battle\"]').click()")
            chrome.wait_for("window.__state.lesson.mode === 'battle'", 10, "battle mode")
            # winner stays on: the Matches tab shows the live ring, who is waiting, the matches played (fight_client)
            mine = chrome.js("!!window.__state.lesson.teacher_fighter")
            chrome.js("window.__app.send({type: 'lesson', lesson: {teacher_fighter: true}})")
            chrome.wait_for("window.__state.lesson.teacher_fighter === true", 10, "the teacher's fighter in the class")
            tab("matches")
            chrome.js("document.getElementById('fm-stays').click()")
            chrome.wait_for("(window.__state.tournament || {}).kind === 'stays' && ['Ring 1: ', 'Waiting: ', 'Matches played: 0']"
                            ".every(t => document.getElementById('panelbody').textContent.includes(t))", 10,
                            "the winner-stays-on rings and queue in the Matches tab")
            chrome.js("document.getElementById('fm-stop').click()")
            chrome.wait_for("window.__state.tournament === null && !!document.getElementById('fm-stays')", 10, "winner stays on stopped")
            chrome.js(f"window.__app.send({{type: 'lesson', lesson: {{teacher_fighter: {'true' if mine else 'false'}}}}})")
            tab("rules")
            chrome.js("document.querySelector('input[data-haz=\"fire_jets\"]').click()")
            chrome.wait_for("window.__state.lesson.hazards.fire_jets === true", 10, "the fire jets")
            tab("learners")
            chrome.js("document.querySelector('button[data-pick=\"*me\"]').click()")
            chrome.wait_for("!!document.getElementById('dz-build') && document.getElementById('panelbody').textContent.includes('MY FIGHTER')",
                            10, "the teacher's own fighter garage")
            chrome.js("document.querySelector('button[data-choice=\"body\"][data-i=\"2\"]').click()")  # (the woman: her look)
            chrome.wait_for("window.__state.draft.body === 'woman' && !!document.querySelector('button[data-look=\"outfit\"]')", 5,
                            "the detailed body's look in the garage")
            chrome.screenshot(os.path.join(work, "fightlab_garage.png"))
            tab("camera")
            time.sleep(2.0)
            chrome.screenshot(os.path.join(work, "fightlab.png"))
            no_errors()
        check("Fight Lab: the rings and the posed fighters are drawn (a woman with the app's own model), and its controls "
              "reach the server (winner stays on: the rings and the queue)", fight_lab)
        for key, proc in servers.items():
            proc.close() if isinstance(proc, Learner) else stop(proc)

        def lessons_current():
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_lessons.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("lessons.json matches the games' lesson files", lessons_current)

        def textures_current():
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_textures.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("tex/ (the app's textures and skies) is up to date with the games' texture generators", textures_current)

        def schemas_current():
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_schemas.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("schemas.json (the games' design schemas) matches the games' files", schemas_current)

        def schema_js():  # (Node runs schema.js; without Node it says so and passes)
            r = subprocess.run([sys.executable, os.path.join(HERE, "schema_test.py")], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            last = (r.stdout.strip().splitlines() or [""])[-1]
            print(f"    schema_test: {last}")
            assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
        check("schema.js writes and reads the code exactly as the windows' Python does (schema_test.py)", schema_js)

        def sounds_current():
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_sounds.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("sfx/ (the games' sounds) is up to date with the games' sound generators", sounds_current)
        print(f"Screenshot and test data: {work}")
    finally:
        if chrome:
            chrome.close()
        stop(server)
        stop(http)
        for proc in extra:
            stop(proc)
        stop(desk)
    for name, ok, note in results:
        if not ok:
            print(f"FAIL {name}\n    {note}")
    print(f"{sum(ok for _, ok, _ in results)} of {len(results)} passed")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
