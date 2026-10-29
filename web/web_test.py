"""Club Coders Live: the browser page against a laptop Kart Lab server, driven through headless Chrome.

    shared-world-demo\\.venv\\Scripts\\python club-coders\\web\\web_test.py      (from the ClubCodersAI folder)

Starts a club desk, a Kart Lab test server and a static server for this folder, opens the page in headless Chrome
(Google Chrome or Microsoft Edge, whichever is installed) over the DevTools protocol, and checks: a wrong teacher
password is refused; the right one opens the Teacher screen (the desk): learners added, a group made and launched,
which opens the class view with the desk's teacher ticket; the page draws the track and the karts from the server's
snapshots with no JavaScript errors;
the line tiers (mesh, lines: black, the edges as lines in the line colour) and ultra (its sky, after-effects and
reflections, and the window's circuit from models/kart_scenery.json, fetched on ultra alone) draw with no errors
(CHANGE 144); Robot Lab's line tiers and ultra too (the window's robots and arena from models/robot_ultra.json and
arena_ultra.json, fetched on ultra alone: CHANGE 145), and Fight Lab's (its fighters, the detailed model's lines
bending with it, and hall from models/fight_ultra.json and stage_ultra.json, fetched on ultra alone: CHANGE 147);
a game controller and a phone's touch controls, pretended (CHANGE 170, 187);
START A RACE, TO THE GRID, a mission button and the track picker reach the server and come back in the lesson; the
graphics tier can be changed; then a note, LAUNCH LEARNERS' WINDOWS, STOP and the printed record, a password reset,
a learner removed, login slips, the teacher password changed; a learner's own page: her Garage drawn from the
game's schema, her code panel (APPLY CODE changes a value, a mistake is shown on its line, BUILD reaches the
server); the teacher's own garage in Robot Lab and Fight Lab; (CHANGE 202) Craft Lab: the teacher's page watching a class
on every tier and at night, a learner's page over a pretend school Wi-Fi walking, jumping, digging, placing, crafting
planks, her Garage and the touch controls; lessons.json, schemas.json, craft.json and tex/ are up to date,
and schema_test.py passes (schema.js against the windows' Python). Screenshots are
kept in the test folder. Exit code 0 = every check passed; the test
says so and passes if no Chrome or Edge is installed. WEB_TEST_STOP_AFTER="a few words of a check's name" ends the
run after that check (a short run while working on the early checks).
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


def mission_program(test_file, name, fallback):
    """(CHANGE 199) A program a mission's own test keeps (wake_up_call_test.STEPS, lights_out_test.SOLUTION), read from
    its file without running it; the copy given here where the file isn't (a folder without the tests)."""
    import ast
    path = os.path.join(ROBOT or "", test_file)
    if ROBOT is None or not os.path.exists(path):
        return fallback
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            v = node.value
            value = ast.literal_eval(v.args[0]) if isinstance(v, ast.Call) else ast.literal_eval(v)  # (a "\n".join([...]))
            return "\n".join(x if isinstance(x, str) else x[1] for x in value)  # (STEPS: (objective, its lines))
    return fallback


# Mission 1's five steps as one program (17 lines, three stars) and Mission 2's solution (15 lines, three stars)
MISSION_1 = mission_program("wake_up_call_test.py", "STEPS", "\n".join([
    "move forward 3", "turn right", "move forward 1", "pick up power cell", "turn left", "move forward 2", "turn right",
    "move forward 3", "pick up spinner", "turn right", "move forward 3", "turn left", "move forward 2", "use spinner",
    "move forward 6", "turn right", "repair"]))
MISSION_2 = mission_program("lights_out_test.py", "SOLUTION", "\n".join([
    "set lamps to 0", "repeat 13 times", "  if path blocked", "    use spinner", "  else", "    move forward 1", "  end",
    "  if lamp dark", "    turn left", "    repair", "    turn right", "    add 1 to lamps", "  end", "end", "report lamps"]))
DESK_PASSWORD = "web-test-teacher-password"
BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/microsoft-edge"]

results = []


# (in the page) the scene drawn properly on a tier: on low and up the app's lighting (pbr.js) in use with every picture
# loaded, no mesh left holding a material that was thrown away, and no more pixels drawn than the tier allows (the
# line tiers' line shaders, CHANGE 144, have no base colour to check)
DRAWN_RIGHT = """(() => {
    const g = window.__state.scene, sc = g.scene, eng = sc.getEngine();
    const pbr = sc.materials.filter(m => m.getClassName() === 'ShaderMaterial' && m.name !== 'ccdepth' && !m.name.startsWith('cclines'));
    if (!['mesh', 'lines', 'blocks'].includes(g.tier) && !pbr.length) return 'no pbr materials on ' + g.tier;
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
    const budget = {mesh: 1.0e6, lines: 1.0e6, blocks: 1.0e6, low: 1.1e6, medium: 1.6e6, high: 2.4e6, ultra: 3.7e6}[g.tier];
    const px = eng.getRenderWidth() * eng.getRenderHeight();
    const css = window.innerWidth * window.innerHeight * Math.min(1, devicePixelRatio);
    if (px > Math.max(budget, css) * 1.02) return 'drawing ' + px + ' pixels on ' + g.tier;
    return 'ok';
})()"""

# (in the page, CHANGE 144) whether it has asked for the ultra circuit (4.7 MB, ultra's alone)
SCENERY_FETCHED = "performance.getEntriesByType('resource').some(e => e.name.includes('models/kart_scenery.json'))"
# (CHANGE 145) which of Robot Lab's ultra models it has asked for (1 MB and 4.8 MB, ultra's alone)
ROBOT_MODELS_FETCHED = ("performance.getEntriesByType('resource').map(e => e.name.split('/').pop())"
                        ".filter(n => n === 'robot_ultra.json' || n === 'arena_ultra.json').sort().join(',')")
# (CHANGE 147) which of Fight Lab's ultra models it has asked for (0.7 MB and 1.4 MB, ultra's alone)
FIGHT_MODELS_FETCHED = ("performance.getEntriesByType('resource').map(e => e.name.split('/').pop())"
                        ".filter(n => n === 'fight_ultra.json' || n === 'stage_ultra.json').sort().join(',')")


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


STOP_AFTER = os.environ.get("WEB_TEST_STOP_AFTER", "")  # (a few words of a check's name: the run ends after it, a short run)


class StopRun(Exception):
    pass


def check(name, fn):
    t0 = time.perf_counter()
    try:
        fn()
        results.append((name, True, ""))
        print(f"PASS {name}  {time.perf_counter() - t0:.0f} s", flush=True)
    except Exception as e:
        results.append((name, False, f"{type(e).__name__}: {e}"))
        print(f"FAIL {name}: {type(e).__name__}: {e}", flush=True)
    if STOP_AFTER and STOP_AFTER in name:
        raise StopRun(name)


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


class CityWalker(Learner):
    """(CHANGE 201) A City Lab learner's window, scripted: logs in with the laptop server's learner code and walks
    round in a circle by the depot, an 18-byte input (engine.wire.pack_input) 60 times a second, as a window sends
    them, so the teacher's page sees someone walking."""

    def __init__(self, port, name):
        super().__init__(port, name)
        self.walking = True
        threading.Thread(target=self.walk, daemon=True).start()

    def walk(self):
        import math
        import struct
        frame = struct.Struct("<BHHIbbBbbBbbB")
        seq, t0 = 1, time.time()
        try:
            while self.walking:
                t = time.time() - t0
                mx, my = round(math.cos(t * 0.5) * 100), round(math.sin(t * 0.5) * 100)
                self.ws.send(frame.pack(2, seq & 0xFFFF, 0, int(t * 1000) & 0xFFFFFFFF, mx, my, 0, mx, my, 0, mx, my, 0))
                seq += 1
                time.sleep(1 / 60)
        except Exception:
            pass

    def close(self):
        self.walking = False
        super().close()


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
        # (what Chrome writes after that is read and dropped: a full pipe would stall the whole browser)
        def drain(pipe):
            for _ in pipe:
                pass
        threading.Thread(target=drain, args=(self.proc.stderr,), daemon=True).start()
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
            chrome.wait_for("!!window.__state && !!window.__state.engine && !document.getElementById('loginform').hidden",
                            20, "the page's script and the login form")
            # (CHANGE 148) one form for everyone: the username and the password, nothing else (no learner/teacher
            # tabs, no class codes); the username teacher is the teacher's
            shown = chrome.js("[...document.querySelectorAll('#login input, #login select')].filter(e => e.offsetParent)"
                              ".map(e => e.id).join(',')")
            assert shown == "lname,lpass", f"the login card shows more than the username and password: {shown}"
            assert not chrome.js("!!document.getElementById('modetabs')"), "the learner and teacher tabs are still there"
            chrome.js("document.getElementById('lname').value = 'teacher'; document.getElementById('lpass').value = 'not-the-password';"
                      "document.getElementById('connect').click()")
            text = chrome.wait_for("document.getElementById('status').textContent.includes('teacher password') && "
                                   "document.getElementById('status').textContent", 10, "the desk refusing")
            assert "isn't the teacher password" in text, text
            assert chrome.js("window.__state.connected") is False
        check("The desk refuses a wrong teacher password", wrong_password)

        def desk_login():  # (typed into the box, as the teacher does: never in the page's address)
            chrome.js(f"document.getElementById('lname').value = 'Teacher'; document.getElementById('lpass').value = {json.dumps(DESK_PASSWORD)}; "
                      "document.getElementById('connect').click()")
            chrome.wait_for("!document.getElementById('desk').hidden && window.__state.desk && window.__state.desk.ready",
                            20, "the Teacher screen")
            assert chrome.js("document.getElementById('lpass').value") == "", "the password box wasn't emptied"
            assert chrome.js("window.__state.desk.state.live") is None
            assert "TEACHER DESK" in chrome.js("document.getElementById('deskbody').textContent")
            # (CHANGE 148) still the server setup's teacher code: the desk opens on Teacher password, saying so
            assert chrome.js("!!document.querySelector('button[data-dtab=\"password\"].on')"), "not on the Teacher password tab"
            assert "setup code" in chrome.js("document.getElementById('dk-msg').textContent")
            chrome.js("document.querySelector('button[data-dtab=\"people\"]').click()")
        check("Username teacher and the teacher password open the Teacher screen (the desk), on Teacher password while "
              "it is the setup's code", desk_login)

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

        def kart_smooth():  # (CHANGE 155) the page's own kart predicted with its own design; the snapshots stamped by step
            chrome.wait_for("!!window.__state.game.predictor && window.__state.game.predStats !== null", 15, "the prediction")
            want = chrome.js("(() => { const g = window.__state.game, k = window.__state.roster.karts.find(k => k.id === g.myId());"
                             " const d = k.design; return JSON.stringify({top: 17.0 + 0.22 * d.speed, accel: 5.0 + 0.10 * d.acceleration,"
                             " grip: 6.0 + 0.10 * d.grip, steer: 95.0 + 1.0 * d.grip}); })()")
            assert chrome.js("window.__state.game.predStats") == want, (chrome.js("window.__state.game.predStats"), want)
            chrome.wait_for("window.__state.snaps.length > 30", 15, "a second of snapshots")  # (enough gaps to judge)
            gaps = chrome.js("(() => { const s = window.__state.snaps; return s.slice(1).map((n, i) => (n.sm - s[i].sm) >>> 0); })()")
            off = [g for g in gaps if abs(g - round(g / (1000 / 60)) * 1000 / 60) > 1.01]
            assert len(gaps) > 20 and not off, f"snapshot stamps not on the 1/60 s steps: {off[:10]} of {len(gaps)}"
        check("Kart Lab: your kart is predicted with its own design, and the snapshots are stamped by the step they show",
              kart_smooth)

        def kart_damage():  # (CHANGE 158) real damage: the teacher's switch, your damage panel, a damaged kart drawn
            chrome.js("document.getElementById('panel').classList.add('open');"
                      "document.querySelector('#panelhead button[data-tab=\"controls\"]').click()")
            chrome.wait_for("!!document.getElementById('btn-damage') && window.__state.lesson.damage !== false", 10, "Damage on")
            chrome.wait_for("!!document.getElementById('kh-dmg') && document.getElementById('kh-dmg').style.display !== 'none'", 10, "the damage panel")
            chrome.js("document.getElementById('btn-damage').click()")
            chrome.wait_for("window.__state.lesson.damage === false && document.getElementById('kh-dmg').style.display === 'none'", 10, "Damage off")
            chrome.wait_for("!!document.getElementById('btn-damage') && !document.getElementById('btn-damage').classList.contains('on')", 10, "the Controls tab again")
            chrome.js("document.getElementById('btn-damage').click()")
            chrome.wait_for("window.__state.lesson.damage === true", 10, "Damage on again")
            got = chrome.js("""(() => { const sc = window.__state.scene, [id, k] = [...sc.karts.entries()][0];
                const st = new Map([[id, {x: 0, y: 0, yaw: 0, v: 8, u: 0, flags: 0, steer: 0, dw: 10000, dfl: 9000, dfr: 0, drl: 0, drr: 0, de: 0}]]);
                for (let i = 0; i < 20; i++) sc.frame(st, 1 / 60);
                return {nose: !!k.nose && Math.abs(k.nose.rotation.x) > 0.15, fl: Math.abs(k.wheels[0].spin.rotation.x) > 0.01,
                        fr: k.wheels[1].spin.rotation.x === 0}; })()""")
            assert got["nose"] and got["fl"] and got["fr"], got
        check("Kart Lab: real damage switched off and on from Controls, your damage panel with it, a damaged kart's fairing "
              "hanging and its wheel leaning", kart_damage)

        def kart_items():  # (CHANGE 159) power-ups: the boxes drawn from the items messages, a switch, E sends USE
            chrome.wait_for("(window.__state.game.itemsBuf || []).length > 0", 10, "an items message")
            chrome.wait_for("(window.__state.scene.itemBoxes || []).length === 8 && window.__state.scene.itemBoxes.some(b => b.box.isEnabled())",
                            10, "the item boxes drawn")
            chrome.wait_for("!!document.querySelector('button[data-item=\"oil\"]')", 10, "the power-up switches")
            chrome.js("document.querySelector('button[data-item=\"oil\"]').click()")
            chrome.wait_for("window.__state.lesson.items && window.__state.lesson.items.oil === false && window.__state.lesson.items.shot === true",
                            10, "oil switched off, the rest on")
            chrome.wait_for("!!document.querySelector('button[data-item=\"oil\"]') && !document.querySelector('button[data-item=\"oil\"]').classList.contains('on')", 10, "the switches again")
            chrome.js("document.querySelector('button[data-item=\"oil\"]').click()")
            chrome.wait_for("window.__state.lesson.items.oil === true", 10, "oil on again")
            # E: the next input frame carries USE (2)
            got = chrome.js("""(() => { const c = window.__state.ctrl, k = c.keys; k.taps.push('e'); c.tapped = k.takeTaps();
                return c.kartControl().buttons; })()""")
            assert got & 2, got
        check("Kart Lab: power-ups drawn from the items messages (the boxes), each switched off and on from Controls, E "
              "sends USE", kart_items)

        def kart_night():  # (CHANGE 171 to 173) the time of day from Controls, the lamps, a sports car
            chrome.js("document.getElementById('panel').classList.add('open');"
                      "document.querySelector('#panelhead button[data-tab=\"controls\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-time=\"night\"]')", 10, "the Time of day buttons")
            chrome.js("document.querySelector('button[data-time=\"night\"]').click()")
            chrome.wait_for("window.__state.lesson.time === 'night' && window.__state.scene.time === 'night'", 15, "night")
            me = chrome.js("window.__state.game.myId()")
            chrome.js("window.__app.send({type: 'design', design: Object.assign({}, window.__state.roster.karts.find(k => k.id === "
                      f"{json.dumps(me)}).design, {{body: 'coupe'}})}}); true")
            chrome.wait_for(f"(window.__state.scene.karts.get({json.dumps(me)}) || {{}}).car === 'coupe'", 20, "the coupe drawn")
            got = chrome.js(f"""(() => {{ const sc = window.__state.scene, id = {json.dumps(me)}, k = sc.karts.get(id);
                const st = s => new Map([[id, {{x: 0, y: 0, yaw: 0, v: 8, u: 0, flags: s, steer: 0}}]]);
                sc.frame(st(0), 1 / 60); const lit = k.lamps.state;
                sc.frame(st(32), 1 / 60); const braking = k.lamps.state;
                return {{lit, braking, wheels: k.wheels.length, label: k.label.position.y, beam: sc.timeLook.beam}}; }})()""")
            assert got["lit"] == 1 and got["braking"] == 3 and got["wheels"] == 4 and got["label"] >= 1.15 and got["beam"] == 1, got
            chrome.js("window.__app.send({type: 'design', design: Object.assign({}, window.__state.roster.karts.find(k => k.id === "
                      f"{json.dumps(me)}).design, {{body: 'kart'}})}}); true")
            chrome.js("document.querySelector('button[data-time=\"day\"]').click()")
            chrome.wait_for(f"window.__state.scene.time === 'day' && !(window.__state.scene.karts.get({json.dumps(me)}) || {{}}).car",
                            20, "day and the kart again")
        check("Kart Lab: Night from Controls, the headlamps on and the brake lights with the braking flag, your kart a "
              "sports car (models/cars.json) and back", kart_night)

        def controller():  # (CHANGE 170) a game controller (pad.js), a pretend one through the Gamepad API
            got = chrome.js("""(() => {
                const pad = {id: 'Test pad (STANDARD GAMEPAD)', connected: true, timestamp: 1, axes: [0, 0, 0, 0],
                             buttons: Array.from({length: 17}, () => ({pressed: false, value: 0}))};
                const was = navigator.getGamepads;
                navigator.getGamepads = () => [null, pad];
                const c = window.__state.ctrl, out = {}, set = (i, v) => { pad.buttons[i] = {pressed: v > 0.5, value: v}; };
                c.tapped = [];  // (no keys: the check before left an E)
                try {
                    c.pad = c.pads.read(); out.idle = c.kartControl();
                    pad.axes = [-0.8, 0, 0, 0]; set(7, 1); set(5, 1); set(4, 1);   // stick left, right trigger, both shoulders
                    c.pad = c.pads.read(); out.kart = c.kartControl(); out.kart2 = c.kartControl();
                    set(7, 0); set(5, 0); set(4, 0); set(1, 1); pad.axes = [0, 0, 0, 0];  // the right face button: brake
                    c.pad = c.pads.read(); out.brake = c.kartControl();
                    set(1, 0); pad.axes = [0, -1, 0, 0]; set(0, 1);                 // stick up, the bottom face button
                    c.pad = c.pads.read(); out.robot = c.robotControl();
                    set(0, 0); set(4, 1); set(6, 1); pad.axes = [0, 0, 0, 0];      // left shoulder and left trigger
                    c.pad = c.pads.read(); out.fight = c.fightControl();
                    set(4, 0); set(6, 0); c.pad = c.pads.read();
                } finally { navigator.getGamepads = was; c.pad = null; }
                return out; })()""")
            assert got["idle"] == {"throttle": 0, "steer": 0, "buttons": 0}, got["idle"]
            k = got["kart"]
            assert k["throttle"] == 1 and k["steer"] > 0.6 and k["buttons"] & 1 and k["buttons"] & 2, k
            assert got["kart2"]["buttons"] & 1 and not got["kart2"]["buttons"] & 2, ("USE goes in one tick only", got["kart2"])
            assert got["brake"]["throttle"] == -1, got["brake"]
            assert got["robot"] == {"throttle": 1, "steer": 0, "fire": True}, got["robot"]
            assert got["fight"]["hold"] == "low_block", got["fight"]
        check("A game controller (a pretend one): Kart Lab's stick steers, the right trigger goes, the right face button "
              "brakes, the shoulders drift and use (once); Robot Lab's stick drives and the bottom button fires; Fight "
              "Lab's left shoulder and trigger block low", controller)

        def touch():  # (CHANGE 187) a phone's touch controls (touch.js), pretend fingers through pointer events
            got = chrome.js("""(() => {
                const A = window.__app, c = window.__state.ctrl, out = {};
                A.setTouch("on");
                const pad = document.getElementById("touchpad");
                out.shown = !!pad && !pad.hidden && document.body.classList.contains("touch");
                const q = sel => document.querySelector('#touchpad ' + sel);
                const mid = el => { const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2, r]; };
                const ev = (type, el, x, y, id) => el.dispatchEvent(new PointerEvent(type, {pointerId: id, pointerType: "touch", clientX: x, clientY: y, bubbles: true, isPrimary: id === 1}));
                const go = q('[data-btn="go"]'), brake = q('[data-btn="brake"]'), item = q('[data-btn="item"]'), drift = q('[data-btn="drift"]'), steer = q('#tp-steer');
                out.sizes = [go, brake, item, drift, steer].map(el => Math.round(Math.min(el.getBoundingClientRect().width, el.getBoundingClientRect().height)));
                c.tapped = [];
                c.pad = A.touch.read(); out.idle = c.kartControl();
                const [gx, gy] = mid(go), [sx, sy, sr] = mid(steer), [ix, iy] = mid(item), [dx, dy] = mid(drift), [bx, by] = mid(brake);
                ev("pointerdown", go, gx, gy, 1);                                   // one finger on GO
                ev("pointerdown", steer, sx, sy, 2); ev("pointermove", steer, sr.left + sr.width * 0.97, sy, 2);  // a thumb slid to the right end
                ev("pointerdown", item, ix, iy, 3);                                 // a tap on the item
                ev("pointerdown", drift, dx, dy, 4);                                // DRIFT held
                out.knob = steer.querySelector('.tp-knob').style.left;
                c.pad = A.touch.read(); out.kart = c.kartControl();
                c.pad = A.touch.read(); out.kart2 = c.kartControl();               // (the tap went once)
                ev("pointermove", steer, sr.left + sr.width * 0.5, sy, 2);          // the thumb back to the middle
                c.pad = A.touch.read(); out.mid = c.kartControl();
                ev("pointerup", go, gx, gy, 1); ev("pointerup", steer, sx, sy, 2); ev("pointerup", item, ix, iy, 3); ev("pointerup", drift, dx, dy, 4);
                ev("pointerdown", brake, bx, by, 5);
                c.pad = A.touch.read(); out.brake = c.kartControl();
                ev("pointerup", brake, bx, by, 5);
                c.pad = A.touch.read(); out.off = c.kartControl();
                out.on = [...document.querySelectorAll('#touchpad button.on')].length;
                out.fullbig = !q('.tp-fullbig').hidden;
                A.setTouch("off");
                out.hidden = pad.hidden && !document.body.classList.contains("touch");
                out.mode = A.touchMode();
                c.pad = null;
                return out; })()""")
            assert got["shown"], got
            assert all(s >= 56 for s in got["sizes"]), ("every control at least 56 px (a finger)", got["sizes"])
            # a phone's screen, upright and sideways: every control and button inside it, the speed box clear of the controls
            fit = """(() => {
                const r = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
                const inside = b => b && b.left >= 0 && b.top >= 0 && b.right <= innerWidth + 0.5 && b.bottom <= innerHeight + 0.5;
                const apart = (a, b) => !a || !b || a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
                const go = r('#touchpad [data-btn="go"]'), steer = r('#tp-steer'), speed = r('.karthud .kbottom'), right = r('#touchpad .tp-right');
                return {w: innerWidth, h: innerHeight, go: inside(go), steer: inside(steer), hud: inside(r('#hudbtn')), panel: inside(r('#toggle')),
                        top: inside(r('#touchpad .tp-top')), speedClear: apart(speed, right) && apart(speed, steer), map: inside(r('#kh-mapbox'))}; })()"""
            try:
                for name, w, h in (("portrait", 390, 844), ("landscape", 844, 390)):
                    chrome.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2, mobile=True)
                    chrome.js("window.__app.setTouch('on'); document.getElementById('panel').classList.remove('open')")
                    time.sleep(0.5)
                    f = chrome.js(fit)
                    chrome.screenshot(os.path.join(work, f"touch_{name}.png"))
                    assert f["w"] == w and f["h"] == h, f
                    assert all(f[k] for k in ("go", "steer", "hud", "panel", "top", "speedClear", "map")), (name, f)
                    # the panel open (it fills a phone's width): its button still on the screen, to close it again
                    chrome.js("document.getElementById('panel').classList.add('open')")
                    assert chrome.js(fit)["panel"], (name, "the PANEL button with the panel open")
                    chrome.js("document.getElementById('panel').classList.remove('open')")
            finally:
                chrome.call("Emulation.clearDeviceMetricsOverride")
                chrome.js("window.__app.setTouch('on')")
            idle = {"throttle": 0, "steer": 0, "buttons": 0}
            assert got["idle"] == idle, got["idle"]
            k = got["kart"]
            assert k["throttle"] == 1 and k["steer"] <= -0.95 and k["buttons"] & 2 and k["buttons"] & 1, ("GO, full right, the item, DRIFT", k)
            assert got["kart2"]["buttons"] & 1 and not got["kart2"]["buttons"] & 2, ("the item once", got["kart2"])
            assert got["mid"]["steer"] == 0 and got["mid"]["throttle"] == 1, got["mid"]
            assert got["knob"] != "" and got["knob"] != "50%", ("the knob moved", got["knob"])
            assert got["brake"]["throttle"] == -1 and got["brake"]["steer"] == 0, got["brake"]
            assert got["off"] == idle and got["on"] == 0, ("every finger lifted", got["off"], got["on"])
            assert got["fullbig"], "the big FULL SCREEN button shows until the page is full screen"
            assert got["hidden"] and got["mode"] == "off", got
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("A phone's touch controls (pretend fingers): the slider steers and springs back, GO and BRAKE, DRIFT held, the "
              "item once a tap, every control finger-sized, the big FULL SCREEN button, Off hides them", touch)

        def folded():  # (CHANGE 187) each box's – folds it to a pill, the HUD button hides them all; both kept
            got = chrome.js("""(() => {
                const A = window.__app, out = {};
                A.setTouch("off");  // (touch mode hides the log itself)
                A.hudMini.apply();
                const tap = el => el.dispatchEvent(new PointerEvent("pointerdown", {pointerId: 9, pointerType: "touch", bubbles: true}));
                const ev = document.getElementById("events"), btn = ev.querySelector(":scope > .mini-btn");
                out.hasBtn = !!btn;
                tap(btn);
                out.folded = ev.classList.contains("mini") && getComputedStyle(ev.querySelector("div")).display === "none" && getComputedStyle(ev.querySelector(".mini-pill")).display !== "none";
                out.kept = localStorage.getItem("hud_mini");
                tap(ev.querySelector(".mini-pill"));
                out.back = !ev.classList.contains("mini") && getComputedStyle(ev.querySelector("div")).display !== "none";
                out.lapBtn = !!document.querySelector(".karthud .ktop > .mini-btn") && !!document.querySelector("#kh-mapbox > .mini-btn");
                document.getElementById("hudbtn").click();
                out.clean = document.body.classList.contains("clean") && getComputedStyle(ev).display === "none" && getComputedStyle(document.getElementById("kh-mapbox")).display === "none";
                out.cleanKept = localStorage.getItem("hud_clean");
                out.countdownStays = getComputedStyle(document.getElementById("race")).display !== "none";
                out.words = document.getElementById("hudbtn").textContent;
                document.getElementById("hudbtn").click();
                out.cleanOff = !document.body.classList.contains("clean") && getComputedStyle(ev).display !== "none";
                return out; })()""")
            assert got["hasBtn"] and got["folded"] and got["kept"] == '["LOG"]', got
            assert got["back"] and got["lapBtn"], got
            assert got["clean"] and got["cleanKept"] == "1" and got["countdownStays"] and got["words"] == "HUD OFF", got
            assert got["cleanOff"], got
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("The information over the game folds away: a box's minus to a pill and back, the HUD button hides every box and "
              "brings them back, both kept on this computer", folded)

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

        def kart_parity():  # (CHANGE 143) Kart Lab's window: the TV stands, the zoom, Home, the teacher's T key
            g, sc = "window.__state.game", "window.__state.scene"
            assert chrome.js(f"{sc}.tvCameras().length") == 6, "not six TV camera stands"
            chrome.js(f"{sc}.setMode('tv')")
            time.sleep(1.5)  # (the camera cut to the nearest stand)
            assert chrome.js(f"(() => {{ const p = {sc}.camera.position; return {sc}.tvCameras().some(q => Math.hypot(q[0] - p.x, q[1] - p.z, q[2] - p.y) < 0.5); }})()"), \
                "the TV camera isn't on one of its stands"
            assert chrome.js(f"{g}.zoom(1, 'key')") is True
            assert chrome.js(f"{sc}.zoom") < 0.95, chrome.js(f"{sc}.zoom")
            chrome.js(f"{g}.resetCamera()")
            assert chrome.js(f"{sc}.zoom") == 1
            before = chrome.js("window.__state.lesson.track")
            assert chrome.js(f"{g}.teacherKey('t')") is True
            chrome.wait_for(f"window.__state.lesson.track !== {json.dumps(before)}", 10, "T: the next track")
            assert chrome.js(f"{g}.teacherKey('x')") is False
            assert chrome.js(f"{g}.keyList().some(([k, w]) => k === 'Enter')"), "Enter isn't in the teacher's key list"
            chrome.js(f"window.__app.send({{type: 'lesson', lesson: {{track: {json.dumps(before)}}}}})")
            chrome.wait_for(f"window.__state.lesson.track === {json.dumps(before)}", 10, "the track back")
            chrome.wait_for("window.__state.scene.track && window.__state.scene.track.name === 'Test Oval'", 10, "the oval drawn again")
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("Kart Lab as its window: six TV stands, the zoom and Home, the teacher's T key", kart_parity)

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
            # (CHANGE 161) the screen's ratio changing (a zoom, another screen) keeps the budget: Babylon's own
            # adaptToDeviceRatio scaled it a second time (medium at 1.25 drew 2.4 MP for 1.6)
            # (a zoom changes the CSS size with the ratio; the protocol's ratio alone fires no resize event)
            for ratio, w, h in ((1.25, 1300, 800), (2.0, 1400, 820), (1.0, 1400, 850)):
                chrome.call("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=ratio, mobile=False)
                chrome.wait_for(f"window.devicePixelRatio === {ratio}", 5, f"the page at {ratio} pixels a CSS pixel")
                time.sleep(0.5)
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 10, f"the pixel budget at {ratio} (last: {chrome.js(DRAWN_RIGHT)})")
                want = chrome.js("(async () => { const b = await import('./base3d.js'); return b.resolutionFor(window.__state.scene.tier); })()")
                got = chrome.js("1 / window.__state.scene.engine.getHardwareScalingLevel()")
                assert abs(got - want) < 1e-6, f"at {ratio} the canvas draws {got} pixels a CSS pixel, the tier wants {want}"
            chrome.call("Emulation.clearDeviceMetricsOverride")
            # (CHANGE 144) only ultra asks for the ultra circuit (4.7 MB): never a school laptop on low, nor on high
            assert not chrome.js(SCENERY_FETCHED), "the ultra circuit (models/kart_scenery.json) was fetched below ultra"
        check("The graphics tiers (blocks, low, medium, high: the app's lighting and textures) keep the track and the karts, "
              "load every picture and keep to their pixel budgets, and never fetch the ultra circuit", tiers)

        def software_gl():  # (CHANGE 161) drawing without the graphics card is recognised (it starts on blocks)
            names = ["Google SwiftShader", "ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)",
                     "llvmpipe (LLVM 15.0.7, 256 bits)", "ANGLE (Microsoft, Microsoft Basic Render Driver Direct3D11 vs_5_0 ps_5_0)",
                     "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x00009A49) Direct3D11 vs_5_0 ps_5_0, D3D11)",
                     "ANGLE (Intel, Mesa Intel(R) UHD Graphics 600 (GLK 2), OpenGL 4.6)", "Mali-G52 MC2", "Adreno (TM) 618",
                     "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"]
            got = chrome.js(f"(async () => {{ const {{SOFTWARE_GL}} = await import('./app.js'); "
                            f"return {json.dumps(names)}.map(n => SOFTWARE_GL.test(n)); }})()")
            assert got == [True, True, True, True, False, False, False, False, False], got
            assert chrome.js("window.__state.softwareGl") is False, "this computer's graphics card taken for software drawing"
        check("Drawing without a graphics card (SwiftShader, llvmpipe, the basic display driver) is recognised", software_gl)

        def line_tiers():  # (CHANGE 144) mesh and lines: black, every mesh's edges as lines (lines: outlines and a grid)
            for tier in ("mesh", "lines"):
                chrome.js(f"window.__app.setTier('{tier}')")
                time.sleep(1.0)
                assert chrome.js("window.__state.scene.tier") == tier
                assert chrome.js("window.__state.scene.karts.size") >= 3
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 15, f"Kart Lab drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                got = chrome.js("""(() => { const sc = window.__state.scene, s = sc.scene, c = s.clearColor;
                    const lines = s.meshes.filter(m => m.material && m.material.name.startsWith('cclines') && m.getTotalVertices() > 0);
                    return {black: c.r + c.g + c.b === 0, track: lines.some(m => m.name === 'tracklines'),
                            karts: lines.filter(m => m.name === 'kartlines').length, grid: lines.some(m => m.name === 'grid'),
                            segments: sc.lineStats && sc.lineStats.segments, ms: sc.lineStats && sc.lineStats.ms, smoke: !!sc.smoke,
                            lit: s.materials.some(m => m.getClassName() === 'ShaderMaterial' && m.name.includes(':'))}; })()""")
                print(f"    {tier}: {got['segments']} line segments for the track, built in {got['ms']} ms")
                assert got["black"] and got["track"] and got["karts"] >= 3 and not got["smoke"] and not got["lit"], got
                assert got["grid"] == (tier == "lines"), got
                chrome.screenshot(os.path.join(work, f"kartlab_{tier}.png"))
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("The line tiers (mesh: every triangle's edges; lines: the outlines and a ground grid) draw black with the "
              "lines, the karts' too", line_tiers)

        def ultra():  # (CHANGE 144) ultra: the sky, the land and woods, bloom, the reflection cube, skids, sparks (no SSAO: CHANGE 151)
            chrome.js("window.__app.setTier('ultra')")
            time.sleep(1.5)
            assert chrome.js("window.__state.scene.tier") == "ultra"
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 30, f"Kart Lab drawn properly on ultra (last: {chrome.js(DRAWN_RIGHT)})")
            got = chrome.js("""(() => { const sc = window.__state.scene, L = sc.lighting;
                return {sky: !!sc.sky && !sc.sky.isDisposed(), probe: !!sc.probe && sc.probe.renderList.length > 5,
                        ssao: !!(sc.fx && sc.fx.ssao), bloom: !!(sc.fx && sc.fx.pipeline.bloomEnabled), skids: !!sc.skids,
                        sparks: !!sc.sparks, forest: sc.forest.length, land: sc.trackMeshes.some(m => m.name.includes('land') || m.name.includes('mountains')),
                        shadow: L.rtt.getRenderSize(), soft: [...L.materials].some(m => m.options.defines.includes('SOFTSHADOW')),
                        coat: [...L.materials].some(m => m.options.defines.includes('CLEARCOAT') && m.options.defines.includes('PROBE'))}; })()""")
            assert got["sky"] and got["probe"] and not got["ssao"] and got["bloom"] and got["skids"] and got["sparks"], got
            assert got["forest"] >= 2 and got["shadow"] == 4096 and got["soft"] and got["coat"], got
            if os.path.exists(os.path.join(HERE, "models", "kart_ultra.json")):  # (the curved kart, make_models.py's)
                chrome.wait_for("[...window.__state.scene.karts.values()].every(k => k.curved)", 20, "the curved karts")
                # (CHANGE 157) a kart steering full left, drawn a second: its front wheels and its driver's head point
                # to its left (sin 26 and sin 16 degrees), the steering wheel turns, the arms follow the hands
                got = chrome.js("""(() => { const sc = window.__state.scene, [id, k] = [...sc.karts.entries()][0];
                    const st = new Map([[id, {x: 0, y: 0, yaw: 0, v: 0, u: 0, flags: 0, steer: 1}]]);
                    for (let i = 0; i < 60; i++) sc.frame(st, 1 / 60);
                    const left = BABYLON.Vector3.TransformNormal(new BABYLON.Vector3(0, 0, 1), k.root.getWorldMatrix()).normalize();
                    const fwd = n => BABYLON.Vector3.TransformNormal(new BABYLON.Vector3(1, 0, 0), n.getWorldMatrix()).normalize();
                    const sw = k.steerWheel, turned = q => Math.abs(q.w) < 0.9999;
                    return {wheels: k.wheels.filter(w => w.front).map(w => BABYLON.Vector3.Dot(fwd(w.pivot), left)),
                            head: sw && sw.head ? BABYLON.Vector3.Dot(fwd(sw.head.node), left) : null,
                            wheel: !!sw && turned(sw.node.rotationQuaternion), arms: sw ? sw.arms.filter(a => turned(a.arm.rotationQuaternion)).length : 0}; })()""")
                assert all(abs(w - 0.438) < 0.01 for w in got["wheels"]) and len(got["wheels"]) == 2, got
                assert got["head"] is not None and abs(got["head"] - 0.276) < 0.01 and got["wheel"] and got["arms"] == 2, got
            if os.path.exists(os.path.join(HERE, "models", "kart_scenery.json")):  # (the window's ultra circuit, CHANGE 144)
                chrome.wait_for("!!window.__state.scene.circuit", 30, "the ultra circuit (models/kart_scenery.json) drawn")
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 30, f"the circuit drawn properly (last: {chrome.js(DRAWN_RIGHT)})")
                got = chrome.js("""(() => { const sc = window.__state.scene, c = sc.circuit, L = sc.lighting;
                    const live = c.meshes.filter(m => !m.isDisposed() && sc.trackMeshes.includes(m));
                    return {fetched: %s, parts: c.parts, instances: c.instances, triangles: c.triangles, meshes: live.length,
                            thin: live.filter(m => m.thinInstanceCount > 1).length, tinted: live.filter(m => m.isVerticesDataPresent('instanceColor')).length,
                            casters: c.casters.filter(m => L.rtt.renderList.includes(m)).length,
                            flatCasting: c.meshes.filter(m => L.rtt.renderList.includes(m) && (m.ccFar || m.material.name.includes('asphalt') || m.material.name.includes('turf'))).length,
                            old: sc.trackMeshes.some(m => ['road', 'grass', 'land', 'mountains', 'firtrunk'].some(n => m.name.startsWith(n))),
                            pads: sc.trackMeshes.some(m => m.name === 'pads'), forest: sc.forest.length}; })()""" % SCENERY_FETCHED)
                print(f"    ultra circuit: {got['parts']} parts, {got['instances']} placed shapes, {got['triangles']} triangles, "
                      f"{got['meshes']} meshes ({got['thin']} as thin instances), {got['casters']} casting shadows")
                assert got["fetched"] and got["parts"] >= 15 and got["instances"] > 1000 and got["thin"] >= 20 and got["tinted"] >= 5, got
                assert got["casters"] >= 10 and got["flatCasting"] == 0 and not got["old"] and got["pads"] and got["forest"] >= 2, got
                # (CHANGE 151) the placed shapes' copies by cell, drawn into the shadow only where it reaches (never by
                # the camera), no geometry buffer (no SSAO); the start lights follow the
                # countdown (3 lit at 1.2 to 1.8 s to GO, none when not counting down, the file's timings); the pond's ripples move
                got = chrome.js("""(async () => { const sc = window.__state.scene, c = sc.circuit, L = sc.lighting;
                    const cells = c.meshes.filter(m => m.ccCell), rtt = L.rtt;
                    const inShadow = rtt.getCustomRenderList(0, rtt.renderList, rtt.renderList.length).filter(m => m.ccCell).length;
                    const em = () => c.lamps.map(m => m._vectors3.emission.x > 1 ? 1 : 0).join('');
                    const w = c.water[0], uv0 = w ? w.mesh.getVerticesData('uv')[0] : null;
                    // (a countdown 1.7 s from GO, looked at a quarter second on; the server's race messages held back meanwhile)
                    const g = window.__state.game, r0 = g.race, take = g.message;
                    g.message = m => m.type === 'race' ? true : take.call(g, m);
                    g.race = Object.assign({}, r0 || {}, {phase: 1, go_in_ms: 1700, at: Date.now()});
                    await new Promise(r => setTimeout(r, 250)); const lit = em();
                    g.message = take; g.race = r0; await new Promise(r => setTimeout(r, 300)); const out = em();
                    return {cells: cells.length, seen: cells.filter(m => m.layerMask !== 0).length, castCells: cells.filter(m => rtt.renderList.includes(m)).length,
                            inShadow, gbuffer: !!sc.fx.gbuffer,
                            // (CHANGE 155) no mesh of the circuit shares its geometry (a copy sharing the original's put its
                            // cell's thin instances in place of the original's: every tyre wall but one cell's gone)
                            shared: c.meshes.filter(m => m.geometry && m.geometry.meshes.length > 1).map(m => m.name).slice(0, 5),
                            drawn: c.meshes.filter(m => m.hasThinInstances && !m.ccCell).reduce((n, m) => n + m.thinInstanceCount, 0),
                            wholeCasting: c.meshes.filter(m => m.hasThinInstances && !m.ccCell && rtt.renderList.includes(m)).length,
                            lamps: c.lamps.length, lit, out, water: !!w && w.mesh.material.name.includes('water'),
                            moved: !!w && w.mesh.getVerticesData('uv')[0] !== uv0, lights: !!c.lights,
                            clubPond: await import('./kartfx.js').then(fx => { const d = fx.sceneryData(), m = d.materials.water;
                                return d.tracks.club.parts.some(p => p.material === 'water') && m.texture === 'water' && !!m.flows; })}; })()""")
                print(f"    ultra circuit by cell: {got['cells']} copies, {got['castCells']} casting, {got['inShadow']} in the shadow's box now")
                assert not got["shared"], f"circuit meshes sharing a geometry: {got['shared']}"
                assert got["cells"] >= 50 and got["seen"] == 0 and got["castCells"] >= 20 and got["wholeCasting"] == 0, got
                assert 0 < got["inShadow"] < got["castCells"] and not got["gbuffer"], got
                assert got["lamps"] == 5 and got["lit"] == "11100" and got["out"] == "00000", got
                # (the pond: the club's alone, the oval drawn here has none; its ripples moving when there is one)
                assert got["clubPond"] and got["lights"] and (got["water"] and got["moved"] or not got["water"] and not got["moved"]), got
            time.sleep(2.0)
            print(f"    ultra: {chrome.js('window.__state.fps')} fps here")
            chrome.screenshot(os.path.join(work, "kartlab_ultra.png"))
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
            chrome.js("window.__app.setTier('low')")
        check("Ultra draws its sky, glow (no SSAO, as the window), soft 4096 shadows, the world reflected in a clear coat, "
              "skid marks and sparks, and the window's circuit (models/kart_scenery.json: its parts, its shapes as thin "
              "instances, the flat and far casting no shadow) in place of the road, grass and woods (and the curved kart, "
              "if models/ has it)", ultra)

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
            lc.wait_for("!!window.__state && !document.getElementById('loginform').hidden", 20, "the learner's login form")
            # (CHANGE 141) on a phone-sized screen LOG IN can be reached (scrolled to, or since CHANGE 148's one short
            # form, already there); no class codes
            lc.call("Emulation.setDeviceMetricsOverride", width=360, height=420, deviceScaleFactor=1, mobile=True)
            time.sleep(0.5)
            assert lc.js("(() => { const b = document.getElementById('connect');"
                         " b.scrollIntoView(); const r = b.getBoundingClientRect();"
                         " return r.top >= 0 && r.bottom <= innerHeight; })()"), \
                "LOG IN can't be reached on a small screen"
            assert not lc.js("!!document.getElementById('switchmode')"), "the class-code link is still there"
            lc.call("Emulation.clearDeviceMetricsOverride")
            lc.js("document.getElementById('lname').value = 'amy'; document.getElementById('lpass').value = 'starter-amy';"
                  "document.getElementById('connect').click()")
            lc.wait_for("!document.getElementById('newpassform').hidden", 15, "the desk asking for her own password")
            lc.js("document.getElementById('npass').value = 'amys-own-1'; document.getElementById('npass2').value = 'amys-own-1';"
                  "document.getElementById('connect').click()")
            lc.wait_for("!document.getElementById('waitbox').hidden && document.getElementById('waittext').textContent.includes('lobby')",
                        15, "the lobby (the learners' windows aren't launched yet)")
            chrome.wait_for("(window.__state.desk.state.lobby || []).includes('amy')", 10, "amy in the desk's lobby list")
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

        def lobby():  # (CHANGE 141) the teacher takes a learner out (back to her lobby) and pulls her in again
            if "chrome" not in pupil:
                return
            lc = pupil["chrome"]
            chrome.js("document.querySelector('button[data-sout=\"amy\"]').click()")
            chrome.wait_for("!window.__state.desk.state.live.learners.includes('amy')", 10, "amy out of the live game")
            lc.wait_for("window.__state.connected === false && !document.getElementById('waitbox').hidden", 15, "amy's page back in her lobby")
            assert "lobby" in lc.js("document.getElementById('waittext').textContent")
            chrome.wait_for("!!document.querySelector('button[data-sin=\"amy\"]')", 10, "amy in the desk's lobby list")
            chrome.js("document.querySelector('button[data-sin=\"amy\"]').click()")
            chrome.wait_for("window.__state.desk.state.live.learners.includes('amy')", 10, "amy added to the live game")
            lc.wait_for("window.__state.connected === true && window.__state.role === 'learner' && window.__state.game.id === 'kartlab'",
                        30, "amy's game opening again by itself")
            assert lc.js("JSON.stringify(window.__errors)") == "[]"
        check("Back to lobby takes a learner out of the game (her page goes back to the lobby); adding her from the lobby "
              "opens her game again", lobby)

        def class_maximum():  # (CHANGE 139) the teacher's class maximum holds a learner's page; Auto's steps, simulated
            if "chrome" not in pupil:
                return
            lc = pupil["chrome"]
            lc.wait_for("window.__state.connected === true && window.__state.role === 'learner'", 30, "amy's page in the game")
            errors_before = lc.js("window.__errors.length")
            lc.js("window.__app.setTier('medium')")
            lc.wait_for("window.__state.scene.tier === 'medium'", 10, "amy's page on medium")
            chrome.js("document.getElementById('panel').classList.add('open'); document.querySelector('#panel header button[data-tab=\"graphics\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-gfxmax=\"low\"]')", 5, "the teacher's Class maximum row")
            chrome.js("document.querySelector('button[data-gfxmax=\"low\"]').click()")
            chrome.wait_for("window.__state.lesson.gfx_max === 'low'", 10, "the class server keeping the maximum")
            lc.wait_for("window.__state.scene.tier === 'low'", 10, "amy's page dropping to the maximum at once")
            lc.js("document.getElementById('panel').classList.add('open'); document.querySelector('#panelhead button[data-tab=\"graphics\"]').click()")
            lc.wait_for("!!document.querySelector('button[data-tier=\"high\"]')", 5, "amy's Settings tab")
            assert lc.js("document.querySelector('button[data-tier=\"high\"]').disabled && document.querySelector('button[data-part=\"shadow\"][data-val=\"2048\"]').disabled"), \
                "high (and 2048 shadows) can be chosen above the class maximum"
            lc.js("document.querySelector('button[data-tier=\"high\"]').click()")
            time.sleep(0.5)
            got = lc.js("[window.__state.scene.tier, window.__state.scene.settings.shadow]")
            assert got == ["low", 0], f"amy's page above the class maximum: {got}"
            assert chrome.js("!document.querySelector('button[data-tier=\"high\"]').disabled"), "the teacher's own view is held to the class maximum"
            chrome.js("document.querySelector('button[data-gfxmax=\"\"]').click()")
            lc.wait_for("window.__state.scene.tier === 'medium'", 10, "amy's page back on her own choice when the maximum is lifted")
            # (CHANGE 144) a class maximum of lines: her Kart Lab page draws lines (a game without them would draw blocks)
            chrome.js("document.querySelector('button[data-gfxmax=\"lines\"]').click()")
            chrome.wait_for("window.__state.lesson.gfx_max === 'lines'", 10, "the class server keeping lines as the maximum")
            lc.wait_for("window.__state.scene.tier === 'lines'", 10, "amy's page at a class maximum of lines")
            chrome.js("document.querySelector('button[data-gfxmax=\"\"]').click()")
            lc.wait_for("window.__state.scene.tier === 'medium'", 10, "amy's page back on medium")
            with open(os.path.join(work, "data", "gfx_max_saved.json"), encoding="utf-8") as f:
                saved = json.load(f)
            assert saved == {"gfx_max": None}, saved
            # Auto, fed seconds of frame rates (base3d.js's AutoTier): up after 25 s with headroom, down after 3 slow
            # seconds, the tier stepped down from held off (twice as long the second time), never past the maximum
            steps = lc.js("""(async () => { const {AutoTier} = await import('./base3d.js'); const out = [];
                let a = new AutoTier({}), t = 'medium', now = 0, wall = 1e12;
                const run = (secs, fps, missed, cap = null) => { for (let s = 0; s < secs; s++) { now += 1000; wall += 1000;
                    const r = a.second({fps, missed, tier: t, cap, now, wall}); if (r) { t = r.tier; out.push((r.up ? 'up:' : 'down:') + t); } } };
                run(30, 60, 0); run(4, 20, 30); run(60, 60, 0); wall += 660000; run(26, 60, 0); run(4, 20, 30); wall += 660000; run(30, 60, 0);
                out.push('|'); a = new AutoTier({}); t = 'low'; run(60, 60, 0, 'low'); run(30, 60, 5, 'medium'); run(60, 60, 1, 'medium');
                return out.join(','); })()""")
            assert steps == "up:high,down:medium,up:high,down:medium,|,up:medium", steps
            # (CHANGE 144) never down out of blocks or into the line tiers, never out of them; up into ultra after a clean
            # high run, never past the game's best tier (a game whose best is high: none since CHANGE 147, kept for one)
            steps = lc.js("""(async () => { const {AutoTier} = await import('./base3d.js'); const out = [];
                let a, t, now = 0, wall = 1e12;
                const run = (secs, fps, missed, top = 'ultra') => { for (let s = 0; s < secs; s++) { now += 1000; wall += 1000;
                    const r = a.second({fps, missed, tier: t, now, wall, top}); if (r) { t = r.tier; out.push((r.up ? 'up:' : 'down:') + t); } } };
                a = new AutoTier({}); t = 'blocks'; run(10, 10, 30); out.push(t);
                a = new AutoTier({}); t = 'lines'; run(10, 10, 30); run(60, 60, 0); out.push(t);
                a = new AutoTier({}); t = 'mesh'; run(60, 60, 0); out.push(t);
                a = new AutoTier({best: 'high'}); t = 'high'; run(30, 60, 0); out.push(t);
                a = new AutoTier({best: 'high'}); t = 'high'; run(30, 60, 0, 'high'); out.push(t);
                return out.join(','); })()""")
            assert steps == "blocks,lines,mesh,up:ultra,ultra,high", steps
            # (CHANGE 144) the line colour: at once on her lines, kept on this computer and in her profile (line_colour)
            lc.js("window.__app.setTier('lines')")
            lc.wait_for("window.__state.scene.tier === 'lines'", 10, "amy's page on lines")
            lc.js("window.__app.lineColour('#ffb000')")
            got = lc.js("[window.__state.scene.lineMats.map(m => m._colors4.color.r.toFixed(2) + ',' + m._colors4.color.g.toFixed(2)), "
                        "window.__state.prefs.line_colour, localStorage.getItem('line_colour')]")
            assert got[1] == "#ffb000" and got[2] == "#ffb000", got
            assert got[0] and all(c in ("1.00,0.69", "0.42,0.29") for c in got[0]), got
            lc.js("window.__app.lineColour('#33ff66')")
            lc.js("window.__app.setTier('blocks')")  # (as she came: the rest of the test is cheap to draw)
            errors = lc.js(f"JSON.stringify(window.__errors.slice({errors_before}))")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("The teacher's class maximum (Graphics tab) reaches a learner's page: she drops to it at once and can't choose "
              "above it; lifted, her own choice again; Auto steps up and down (simulated) without flapping", class_maximum)

        def learner_parity():  # (CHANGE 143) what a learner's window does that her page didn't
            if "chrome" not in pupil:
                return
            lc = pupil["chrome"]
            errors_before = lc.js("window.__errors.length")
            # (what the page itself sends: app.js's own send goes straight to the socket, not through window.__app)
            lc.js("{ const s = WebSocket.prototype.send; window.__wsSent = []; window.__wsSend = s;"
                  " WebSocket.prototype.send = function (d) { try { window.__wsSent.push(JSON.parse(d)); } catch (e) {} return s.call(this, d); }; }")
            # H: the key list on screen and off again; it lists U and P (her brain) as the window's does
            hidden = lc.js("document.getElementById('keyhelp').hidden")
            press_h = ("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'h'}));"
                       "window.dispatchEvent(new KeyboardEvent('keyup', {key: 'h'}))")
            lc.js(press_h)
            lc.wait_for(f"document.getElementById('keyhelp').hidden === {json.dumps(not hidden)}", 5, "H showing or hiding the key list")
            lc.js(press_h)
            text = lc.js("document.getElementById('keyhelp').textContent")
            assert "U" in text and "brain" in text.lower(), text[:300]
            # the game's starter brain (brains/my_brain.py), served beside the page, byte for byte
            with open(os.path.join(KART, "brains", "my_brain.py"), encoding="utf-8", newline="") as f:
                starter = f.read()
            served = lc.js("fetch('brains/kartlab/my_brain.py').then(r => r.ok ? r.text() : 'HTTP ' + r.status)")
            assert served.replace("\r\n", "\n") == starter.replace("\r\n", "\n"), \
                "web/brains/kartlab/my_brain.py isn't the game's brains/my_brain.py (copy it again)"
            # her perf report carries the windows' key delay (ctrl), for the teacher's table
            lc.wait_for("window.__wsSent.some(m => m.type === 'perf' && 'ctrl' in m)", 20, "a perf report with the key delay")
            lc.js("WebSocket.prototype.send = window.__wsSend; window.__wsSent = [];")
            # an AI card: My last requests shows its goal; kept by the teacher, her review goes back and is taken
            goal = "Make the boost last longer on the straight"
            lc.js("window.__app.send({type: 'ai_card', card: {goal: " + json.dumps(goal) + ", variables: 'boost_time = 2',"
                  " test: 'Race two laps and time the boost on the long straight', predict: 'The boost lasts longer',"
                  " privacy: true, review: true, credit: true}})")
            cid = lc.wait_for("((window.__state.myMissions.cards || []).find(k => (k.card || {}).goal === " + json.dumps(goal) + ") || {}).id",
                              10, "her card in her missions")
            chrome.js(f"window.__app.send({{type: 'card_status', id: {cid}, status: 'ready', note: 'Kept'}})")
            lc.js("document.getElementById('panel').classList.add('open'); document.querySelector('#panelhead button[data-tab=\"aicard\"]').click()")
            lc.wait_for(f"!!document.querySelector('button[data-review=\"{cid}\"]')", 10, "the review questions under her kept card")
            assert goal in lc.js("document.getElementById('panelbody').textContent"), "My last requests doesn't show the card's goal"
            lc.js(f"document.querySelectorAll('textarea[id^=\"rv-{cid}-\"]').forEach(t => t.value = 'The boost lasted longer and my laps were faster on the straight');"
                  f"document.querySelector('button[data-review=\"{cid}\"]').click()")
            lc.wait_for(f"(window.__state.myMissions.cards || []).some(k => k.id === {cid} && k.status === 'reviewed')", 10,
                        "her review taken by the server")
            # the teacher's Learners tab: her AI cards, with their words
            chrome.js("document.getElementById('panel').classList.add('open');"
                      "document.querySelector('#panelhead button[data-tab=\"learners\"]').click()")
            time.sleep(0.3)
            chrome.js("document.querySelector('button[data-pick=\"amy\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-sub=\"cards\"]')", 10, "amy's AI cards button")
            chrome.js("document.querySelector('button[data-sub=\"cards\"]').click()")
            chrome.wait_for(f"document.getElementById('panelbody').textContent.includes({json.dumps(goal)})", 10, "amy's card's goal in the teacher's view")
            assert "key delay" in chrome.js("document.getElementById('panelbody').textContent"), "no key delay column"
            # BACK TO THE LOBBY (pressed twice), as closing the game in the app; added again, her game opens again
            lc.js("document.getElementById('btn-lobby').click()")
            assert lc.js("window.__state.connected") is True, "one press left the game"
            lc.js("document.getElementById('btn-lobby').click()")
            lc.wait_for("window.__state.connected === false && !document.getElementById('waitbox').hidden", 15, "amy back in her lobby")
            # (as when her window closes, CHANGE 54: she stays in the session's list and the desk doesn't send her back
            # in by itself; the teacher's This session: Back to lobby, then her name from the lobby)
            time.sleep(1.0)
            assert lc.js("window.__state.connected") is False, "she was sent straight back into the game she left"
            chrome.js("document.getElementById('btn-desk').click()")
            chrome.wait_for("!!document.querySelector('button[data-sout=\"amy\"]')", 10, "amy in This session on the desk")
            chrome.js("document.querySelector('button[data-sout=\"amy\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-sin=\"amy\"]')", 15, "amy in the desk's lobby list")
            chrome.js("document.querySelector('button[data-sin=\"amy\"]').click()")
            lc.wait_for("window.__state.connected === true && window.__state.role === 'learner' && window.__state.game.id === 'kartlab'",
                        30, "amy's game opening again")
            chrome.js("document.getElementById('dk-back').click()")
            errors = lc.js(f"JSON.stringify(window.__errors.slice({errors_before}))")
            assert errors == "[]", f"JavaScript errors: {errors}"
            assert chrome.js("JSON.stringify(window.__errors)") == "[]", chrome.js("JSON.stringify(window.__errors)")
        check("A learner's page as her window: H's key list, the starter brain, the key delay, an AI card reviewed (and its "
              "words in the teacher's view), BACK TO THE LOBBY and in again", learner_parity)

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
            # (the editor, CHANGE 138: typed keys are highlighted as typed, the layer's text the textarea's, in its font)
            before = lc.js("document.getElementById('code-text').value")
            lc.js("{ const t = document.getElementById('code-text'); t.focus(); t.setSelectionRange(t.value.length, t.value.length); }")
            lc.call("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
            lc.call("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
            lc.call("Input.insertText", text="ok = len(f'{speed}') if True else None  # typed")
            # (the font comes in the background, font-display: swap: not asked for here, only waited for)
            lc.wait_for("[...document.fonts].some(f => f.family.includes('JetBrains') && f.status === 'loaded')", 10, "JetBrains Mono loaded")
            hl = lc.js("(() => { const t = document.getElementById('code-text'), h = document.getElementById('code-hl'), q = s => [...h.querySelectorAll(s)].map(e => e.textContent);"
                       " return {same: h.textContent === t.value, end: t.value.endsWith(\"\\nok = len(f'{speed}') if True else None  # typed\"), k: q('.k'), f: q('.f'), s: q('.s'), n: q('.n').length,"
                       " c: q('.c').pop(), mb: q('.mb').length, cur: document.querySelector('#code-gutter .cur') && document.querySelector('#code-gutter .cur').textContent,"
                       " lines: t.value.split('\\n').length, font: getComputedStyle(h).font === getComputedStyle(t).font && getComputedStyle(t).fontFamily.includes('JetBrains Mono'),"
                       " loaded: [...document.fonts].some(f => f.family.includes('JetBrains') && f.status === 'loaded'), file: document.getElementById('code-file').textContent}; })()")
            assert hl["same"] and hl["end"], f"the highlighted text isn't the textarea's: {hl}"
            assert {"if", "True", "else", "None"} <= set(hl["k"]) and "len" in hl["f"] and "f'{speed}'" in hl["s"] and hl["n"] > 0, hl
            assert hl["c"] == "# typed" and hl["cur"] == str(hl["lines"]) and hl["font"] and hl["loaded"] and hl["file"] == "my_kart.py", hl
            lc.screenshot(os.path.join(work, "learner_code_typed.png"))
            lc.js(f"{{ const t = document.getElementById('code-text'); t.value = {json.dumps(before)}; t.dispatchEvent(new Event('input')); }}")
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

        def records_apart():  # (CHANGE 143) the app's Records files a summary, a learner's cards and the scheme of work apart
            chrome.js("document.querySelector('button[data-printsum]').click()")
            chrome.wait_for("window.__printed === 2", 5, "the summary's print box")
            text = chrome.js("document.getElementById('printout').textContent")
            assert "Session summary" in text and "Learner card" not in text, text[:300]
            chrome.js("document.getElementById('dk-recname').value = 'amy'; document.getElementById('dk-printlearner').click()")
            chrome.wait_for("window.__printed === 3", 5, "amy's cards' print box")
            text = chrome.js("document.getElementById('printout').textContent")
            assert "Learner card: amy" in text and "Session summary" not in text, text[:300]
            chrome.js("document.querySelector('button[data-scheme=\"kartlab\"]').click()")
            chrome.wait_for("window.__printed === 4", 10, "the scheme of work's print box (from the desk)")
            text = chrome.js("document.getElementById('printout').textContent")
            assert "Scheme of work" in text and "Kart Lab" in text and "Success looks like" in text, text[:400]
            errors = chrome.js("JSON.stringify(window.__errors)")
            assert errors == "[]", f"JavaScript errors: {errors}"
        check("Records: a session's summary on its own, one learner's cards, a game's scheme of work (from the desk)", records_apart)

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
            chrome.wait_for("document.getElementById('login').style.display === 'flex'", 5, "the login screen")
            assert chrome.js("document.getElementById('lname').value").lower() == "teacher", "the username wasn't kept"
            chrome.js(f"document.getElementById('lpass').value = {json.dumps(DESK_PASSWORD)}; document.getElementById('connect').click()")
            chrome.wait_for("document.getElementById('status').textContent.includes('teacher password')", 10, "the old password refused")
            chrome.js(f"document.getElementById('lpass').value = {json.dumps(new)}; document.getElementById('connect').click()")
            chrome.wait_for("!document.getElementById('desk').hidden && window.__state.desk && window.__state.desk.ready", 10,
                            "the new password logging in")
            assert not chrome.js("!!document.querySelector('button[data-dtab=\"password\"].on')"), \
                "the teacher's own password still sent them to choose one"
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

        def start_server(key, folder, script, port, data_var, extra=()):  # (extra: the server's own arguments)
            servers[key] = subprocess.Popen([sys.executable, script, "--port", str(port), *extra], cwd=folder,
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
            # (CHANGE 145) Robot Lab draws all seven, as its window (no nearest tier): its Graphics tab shows the seven;
            # low to high never ask for ultra's models
            assert chrome.js(ROBOT_MODELS_FETCHED) == "", "Robot Lab's ultra models were fetched below ultra"
            tab("graphics")
            assert chrome.js("[...document.querySelectorAll('button[data-tier]')].map(b => b.dataset.tier).join(',')") == \
                "mesh,lines,blocks,low,medium,high,ultra"
            assert chrome.js("!!document.querySelector('button[data-linecol]')"), "no line colours on Robot Lab's Graphics tab"
            # (CHANGE 166) the robots drawn where they are now: every robot followed from the snapshots, each one's
            # drive from the roster, the Graphics tab's Movement row; "as sent" draws them blended again
            got = chrome.js("[window.__state.game.ahead.tracks.size, window.__state.game.drive.size, "
                            "!!document.querySelector('button[data-ahead=\"1\"].on'), window.__state.gfx.ahead]")
            assert got[0] >= 3 and got[1] >= 3 and got[2] and got[3] is True, f"the robots drawn ahead: {got}"
            chrome.js("document.querySelector('button[data-ahead=\"0\"]').click()")
            chrome.wait_for("window.__state.gfx.ahead === false && JSON.parse(localStorage.getItem('gfx')).ahead === false", 5,
                            "Movement: as sent, kept on this computer")
            chrome.js("document.querySelector('button[data-ahead=\"1\"]').click()")
            chrome.wait_for("window.__state.gfx.ahead === true", 5, "Movement: now again")
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
        check("Robot Lab: the arena and the robots are drawn from its snapshots, on every tier, ahead (the Movement row); "
              "B makes the health bars small", robot_lab)

        def robot_line_tiers():  # (CHANGE 145) mesh and lines as the window's: black, the arena's, the cage's screens'
            if "amy" not in servers:  # and every robot's edges as lines (each moving part's own), the grid on lines only
                return
            for tier in ("mesh", "lines"):
                chrome.js(f"window.__app.setTier('{tier}')")
                chrome.wait_for(f"window.__state.scene.tier === '{tier}' && window.__state.scene.robots.size >= 3 && {DRAWN_RIGHT} === 'ok'",
                                20, f"Robot Lab drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                time.sleep(1.0)  # (frames drawn: the glowing parts' lines pulsed)
                got = chrome.js("""(() => { const sc = window.__state.scene, s = sc.scene, c = s.clearColor;
                    const lines = s.meshes.filter(m => m.material && m.material.name.startsWith('cclines') && m.getTotalVertices() > 0);
                    const robots = [...sc.robots.values()];
                    return {black: c.r + c.g + c.b === 0, arena: lines.filter(m => m.name === 'arenalines').length,
                            screens: lines.some(m => m.name === 'screenlines'), pit: lines.some(m => m.name === 'pitlines'),
                            robots: robots.length, lined: robots.filter(v => v.root.getChildMeshes(false).some(m => m.name === 'robotlines')
                                && v.wheels.every(w => w.spin.getChildMeshes(true).some(m => m.name === 'wheellines'))
                                && v.panels.every(p => p.node.getChildMeshes(true).some(m => m.name === 'robotlines'))).length,
                            deckNames: robots.some(v => v.deckName), blur: robots.some(v => v.blur),
                            segments: sc.lineStats.segments, grid: sc.lineStats.grid, ms: sc.lineStats.ms, smoke: !sc.fx.look,
                            lit: s.materials.some(m => m.getClassName() === 'ShaderMaterial' && m.name.includes(':'))}; })()""")
                print(f"    {tier}: {got['segments']} line segments for the arena ({got['grid']} the grid), built in {got['ms']} ms")
                assert got["black"] and got["arena"] >= 1 and got["screens"] and got["pit"] and not got["lit"] and not got["smoke"], got
                assert got["lined"] == got["robots"] and not got["deckNames"] and not got["blur"], got
                assert (got["grid"] > 50) == (tier == "lines"), got
                chrome.screenshot(os.path.join(work, f"robotlab_{tier}.png"))
            # the line colour: at once on the arena's and the robots' lines
            chrome.js("window.__app.lineColour('#ffb000')")
            got = chrome.js("window.__state.scene.lineMats.filter(m => m._colors4).map(m => [m._colors4.color.r, m._colors4.color.g])")
            assert got and any(r > 0.99 for r, g in got) and all(abs(g / r - 0.69) < 0.02 for r, g in got if r > 0.01), got
            chrome.js("window.__app.lineColour('#33ff66')")
            assert chrome.js(ROBOT_MODELS_FETCHED) == "", "Robot Lab's ultra models were fetched on the line tiers"
            no_errors()
        check("Robot Lab's line tiers (mesh: every triangle's edges; lines: the outlines and a floor grid) draw black with the "
              "arena's, the screens' and every robot's lines, and change colour at once", robot_line_tiers)

        def robot_ultra():  # (CHANGE 145) ultra: the window's robots and arena, fetched now (and not before)
            if "amy" not in servers:
                return
            chrome.js("window.__app.setTier('ultra')")
            chrome.wait_for("window.__state.scene.tier === 'ultra'", 10, "Robot Lab on ultra")
            have = [n for n in ("robot_ultra.json", "arena_ultra.json") if os.path.exists(os.path.join(HERE, "models", n))]
            if len(have) < 2:
                print("    (models/ hasn't Robot Lab's ultra models: high's robots and arena drawn)")
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 30, "Robot Lab drawn properly on ultra without its models")
                return
            chrome.wait_for("window.__state.scene.ultraArena && window.__state.scene.ultraRobots && window.__state.scene.robots.size >= 3", 40,
                            "the window's robots and arena (models/robot_ultra.json, arena_ultra.json)")
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 30, f"Robot Lab drawn properly on ultra (last: {chrome.js(DRAWN_RIGHT)})")
            got = chrome.js("""(() => { const sc = window.__state.scene, u = sc.ultraParts, L = sc.lighting, list = L.rtt.renderList;
                const robots = [...sc.robots.values()];
                const own = robots.map(v => [...v.root.getChildMeshes(false), ...v.weapon.getChildMeshes(false)].filter(m => m.name.startsWith('robot ') && m.layerMask && m.isVisible).length);
                const robotCast = robots.map(v => [...v.root.getChildMeshes(false), ...v.weapon.getChildMeshes(false)].filter(m => list.includes(m)));
                return {fetched: %s, parts: u.parts, instances: u.instances, triangles: u.triangles,
                        crowd: u.meshes.filter(m => m.ccCrowd && m.isVerticesDataPresent('color')).length,
                        robotShadows: robotCast.every(c => c.length && c.every(m => m.layerMask === 0 && m.name.includes('shadow'))),
                        whole: robots.every(v => v.whole && v.whole.isVisible && v.apart.every(m => !m.isVisible)),
                        arenaShadow: u.casters.length && u.casters.every(m => m.layerMask === 0),
                        casters: u.casters.filter(m => list.includes(m)).length,
                        flatCasting: [...u.meshes, ...u.rig].filter(m => list.includes(m) && !m.ccCast).length,
                        rig: sc.rig.filter(m => m.name.startsWith('arena ')).length, own: Math.max(...own), fewest: Math.min(...own),
                        boxes: robots.some(v => v.root.getChildMeshes(false).some(m => m.name === 'box' || m.name === 'cyl')),
                        shadow: L.rtt.getRenderSize(), soft: [...L.materials].some(m => m.options.defines.includes('SOFTSHADOW')),
                        haze: [...L.materials].some(m => m.options.defines.includes('FOG')),
                        hazeNear: [...L.materials].some(m => m.options.defines.includes('FOG') && !m.name.endsWith(' far')),
                        atlas: [...L.materials].some(m => m.options.defines.includes('GLOWMAP') && m.options.defines.includes('MRMAP')),
                        bloom: !!(sc.after && sc.after.pipeline.bloomEnabled), ssao: !!(sc.after && sc.after.ssao)}; })()""" % ROBOT_MODELS_FETCHED)
            print(f"    ultra arena: {got['parts']} parts, {got['instances']} placed shapes, {got['triangles']} triangles; "
                  f"{got['fewest']} to {got['own']} meshes a robot; {got['casters']} arena parts casting shadows")
            assert got["fetched"] == "arena_ultra.json,robot_ultra.json" and got["parts"] >= 20 and got["instances"] > 500, got
            # (CHANGE 152) the crowd placed into a mesh a material and side; the shadow map draws the robots' coarser shadows and
            # the arena's casters as one mesh, never seen by the camera; a whole robot's body and panels one mesh
            assert got["crowd"] >= 8 and got["casters"] >= 1 and got["arenaShadow"] and got["flatCasting"] == 0 and got["rig"] >= 3, got
            assert got["robotShadows"] and got["whole"], got
            assert 4 <= got["fewest"] and got["own"] <= 9 and not got["boxes"], got
            assert got["shadow"] == 4096 and got["soft"] and got["haze"] and not got["hazeNear"] and got["atlas"] and got["bloom"], got
            assert not got["ssao"], got
            time.sleep(2.0)
            print(f"    ultra: {chrome.js('window.__state.fps')} fps here")
            chrome.screenshot(os.path.join(work, "robotlab_ultra.png"))
            chrome.js("window.__app.setTier('low')")
            chrome.wait_for(f"window.__state.scene.tier === 'low' && {DRAWN_RIGHT} === 'ok'", 15, "Robot Lab back on low")
            no_errors()
        check("Robot Lab's ultra draws the window's robots (a mesh a moving part, the roles from an atlas) and arena (its "
              "parts, the crowd and seats a mesh a material and side, the shadows as their own meshes, the hall in its haze) from "
              "models/robot_ultra.json and arena_ultra.json, fetched on ultra alone, with soft 4096 shadows and a glow",
              robot_ultra)

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
            # (CHANGE 142) the teacher's code panel for a learner: her robot as code, edited, REBUILD FOR AMY
            chrome.wait_for("!!document.getElementById('dz-code')", 5, "the Code button in amy's garage")
            chrome.js("document.getElementById('dz-code').click()")
            chrome.wait_for("!document.getElementById('codepanel').hidden && document.getElementById('code-title').textContent === \"AMY'S ROBOT AS PYTHON CODE\"",
                            5, "amy's robot as code")
            assert chrome.js("document.getElementById('code-rebuild').textContent") == "REBUILD FOR AMY"
            assert chrome.js("document.getElementById('code-teacher').hidden") is True, "the learners' start buttons on a learner's code"
            chrome.js("{ const t = document.getElementById('code-text'); t.value = t.value.replace('robot_name: str = \"Zap\"', 'robot_name: str = \"Zip\"');"
                      " t.dispatchEvent(new Event('input')); document.getElementById('code-rebuild').click(); }")
            chrome.wait_for("window.__state.classList.some(p => p.name === 'amy' && p.design.name === 'Zip')", 10, "amy's robot rebuilt from the code as Zip")
            chrome.screenshot(os.path.join(work, "robotlab_their_code.png"))
            chrome.js("document.getElementById('code-close').click()")
            chrome.js("document.querySelector('button[data-pick=\"*me\"]').click()")
            chrome.wait_for("!!document.getElementById('dz-build') && document.getElementById('panelbody').textContent.includes('MY ROBOT')",
                            10, "the teacher's own garage")
            chrome.js("document.querySelector('button[data-choice=\"weapon\"][data-i=\"2\"]').click()")
            chrome.wait_for("window.__state.draft.weapon === 'drum'", 5, "a weapon chosen in the garage")
            chrome.screenshot(os.path.join(work, "robotlab_garage.png"))
            # (the teacher's own code: the learners' starting robot for the mission, saved and back to standard)
            chrome.js("document.getElementById('dz-code').click()")
            chrome.wait_for("!document.getElementById('codepanel').hidden && !document.getElementById('code-teacher').hidden &&"
                            " document.getElementById('code-title').textContent === 'YOUR ROBOT AS PYTHON CODE'", 5, "your own robot as code")
            chrome.js("document.getElementById('code-save-start').click()")
            chrome.wait_for("!!(window.__state.lesson || {}).start_design && !!document.getElementById('code-standard')", 10,
                            "saved as the learners' starting robot")
            chrome.js("document.getElementById('code-standard').click()")
            chrome.wait_for("!(window.__state.lesson || {}).start_design", 10, "the standard starting robot again")
            chrome.js("document.getElementById('code-close').click()")
            for t in ("warnings", "camera", "graphics", "about", "controls"):
                tab(t)
            # (CHANGE 142) a drop-down in use isn't redrawn under the teacher: the panel's redraw waits
            assert chrome.js("(() => { const s = document.querySelector('#panelbody select'); s.focus();"
                             " s.dispatchEvent(new Event('pointerdown', {bubbles: true})); window.__app.renderPanel();"
                             " const kept = document.querySelector('#panelbody select') === s; s.blur(); return kept; })()"), \
                "the panel was redrawn under a drop-down in use"
            chrome.screenshot(os.path.join(work, "robotlab_panel.png"))
            no_errors()
        check("The shared teacher tabs: a tool and a hazard, an objective added and ticked, missions out and back in, "
              "the evidence CSV, an AI card sent back, a learner's mission and robot", shared_tabs)

        def computer_robots():  # CHANGE 140: the teacher sets up computer robot 2 and puts it in arena 2 alone
            if "amy" not in servers:
                return
            chrome.js("window.__app.send({type: 'lesson', lesson: {cpu_robots: 2, arenas: 2}})")
            chrome.wait_for("window.__state.lesson.cpu_robots === 2 && window.__state.lesson.arenas === 2", 10, "2 computer robots, 2 arenas")
            tab("learners")
            chrome.wait_for("!!document.querySelector('button[data-pick=\"*cpu2\"]')", 10, "Computer 2 in the Learners tab")
            chrome.js("document.querySelector('button[data-pick=\"*cpu2\"]').click()")
            chrome.wait_for("!!document.getElementById('dz-name') && !!document.getElementById('cpu-arena')", 10, "computer robot 2's garage")
            chrome.js("document.getElementById('dz-name').value = 'Crusher'; document.getElementById('dz-build').click()")
            cpu2 = "window.__state.classList.find(p => p.role === 'computer' && p.n === 2)"
            chrome.wait_for(f"{cpu2}.design.name === 'Crusher'", 10, "computer robot 2 renamed Crusher")
            chrome.wait_for("!!document.getElementById('cpu-arena')", 10, "its arena")
            chrome.js("const s = document.getElementById('cpu-arena'); s.value = '1'; s.dispatchEvent(new Event('change'))")
            chrome.wait_for(f"{cpu2}.arena === 1 && {cpu2}.in === 1", 10, "computer robot 2 set to arena 2")
            chrome.wait_for("(() => { const S = window.__state, mine = (S.roster.robots || []).filter(r => r.design.name === 'Crusher');"
                            " const snap = S.snaps[S.snaps.length - 1], ids = i => (snap.arenas[i] || {robots: []}).robots.map(r => r.id);"
                            " return mine.length === 1 && mine[0].arena === 1 && ids(1).includes(mine[0].id) && !ids(0).includes(mine[0].id)"
                            " && ids(0).length > 0; })()", 15, "Crusher in arena 2 only, in the snapshot")
            chrome.screenshot(os.path.join(work, "robotlab_computer_robot.png"))
            chrome.js("window.__app.send({type: 'lesson', lesson: {cpu_robots: 1, arenas: 1}})")
            no_errors()
        check("Robot Lab's computer robots: computer robot 2 renamed and put in arena 2 from the Learners tab", computer_robots)

        def arena_rows():  # CHANGE 142: every robot's name and arena on the Controls tab, kept by Save settings
            if "amy" not in servers:
                return
            chrome.js("window.__app.send({type: 'lesson', lesson: {cpu_robots: 2, arenas: 2}})")
            chrome.wait_for("window.__state.lesson.cpu_robots === 2 && window.__state.lesson.arenas === 2", 10, "2 computer robots, 2 arenas")
            tab("controls")
            chrome.wait_for("['me', 'l-amy', 'c1', 'c2'].every(k => document.getElementById('rb-nm-' + k) && document.getElementById('rb-at-' + k))",
                            10, "a row for each robot: the teacher's, amy's, computer robots 1 and 2")
            rename = ("((k, name) => { const el = document.getElementById('rb-nm-' + k); el.focus(); el.value = name;"
                      " el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'})); })")
            chrome.js(f"{rename}('c2', 'Basher'); {rename}('l-amy', 'Zorro!'); {rename}('me', 'Boss')")  # (the ! goes, as the server's)
            named = "window.__state.classList.some(p => {})"
            chrome.wait_for(" && ".join(named.format(t) for t in ("p.role === 'computer' && p.n === 2 && p.design.name === 'Basher'",
                                                                  "p.name === 'amy' && p.design.name === 'Zorro'",
                                                                  "p.role === 'teacher' && p.design.name === 'Boss'")),
                            10, "computer robot 2, amy's robot and the teacher's renamed from their rows")
            arena = "((k, v) => { const s = document.getElementById('rb-at-' + k); s.value = v; s.dispatchEvent(new Event('change')); })"
            chrome.js(f"{arena}('c2', '0'); {arena}('l-amy', '1'); {arena}('me', '1')")
            chrome.wait_for("(() => { const S = window.__state, L = S.lesson, c2 = S.classList.find(p => p.role === 'computer' && p.n === 2);"
                            " return L.places.amy === 1 && L.places.Teacher === 1 && c2.arena === 0 && c2.in === 0; })()", 10,
                            "amy and the teacher in arena 2, computer robot 2 in arena 1")
            chrome.wait_for("(() => { const R = window.__state.roster, at = n => (R.robots.find(r => r.id === R.mine[n]) || {}).arena;"
                            " return at('amy') === 1 && at(window.__state.name) === 1 && R.robots.filter(r => r.design.name === 'Basher').every(r => r.arena === 0); })()",
                            15, "the robots where they were put")
            servers["amy"].send({"type": "design", "design": {"name": "Blitz"}})  # (a name changed elsewhere shows in its row)
            chrome.wait_for("document.getElementById('rb-nm-l-amy').value === 'Blitz' && document.getElementById('rb-at-l-amy').value === '1'",
                            10, "amy's own new name in her row")
            chrome.screenshot(os.path.join(work, "robotlab_arenas.png"))
            chrome.js("document.getElementById('btn-save').click()")
            path, n = os.path.join(work, "robotlab", "mission_settings.json"), str(chrome.js("window.__state.lesson.lesson_number"))
            end, saved = time.time() + 10, {}
            while time.time() < end and saved.get("places") != {"amy": 1, "Teacher": 1}:
                time.sleep(0.25)
                try:
                    with open(path, encoding="utf-8") as f:
                        saved = json.load(f).get(n, {})
                except (OSError, ValueError):
                    pass
            assert saved.get("places") == {"amy": 1, "Teacher": 1}, f"Save settings didn't keep who is where: {saved.get('places')}"
            assert (saved.get("cpu_arenas") or [])[:2] == [None, 0], f"Save settings didn't keep the computer robots' arenas: {saved.get('cpu_arenas')}"
            chrome.js("window.__app.send({type: 'cpu_robot', n: 2, arena: null});"
                      "window.__app.send({type: 'lesson', lesson: {cpu_robots: 1, arenas: 1, places: {amy: null, Teacher: null}}})")
            chrome.wait_for("!!document.getElementById('rb-nm-me') && !document.getElementById('rb-at-me') && !document.getElementById('rb-nm-c2')"
                            " && document.getElementById('panelbody').textContent.includes('One arena: everyone is in arena 1')", 10,
                            "one arena: the names, no arena lists")
            os.remove(path)  # (the restart after this starts with the mission's own settings)
            no_errors()
        check("Robot Lab's Controls: every robot renamed and put in an arena from its row, kept by Save settings", arena_rows)

        def robot_parity():  # (CHANGE 143) what the Robot Lab window does that the page didn't
            if "amy" not in servers:
                return
            chrome.js("window.__app.send({type: 'lesson', lesson: {cpu_robots: 2, arenas: 2}})")
            chrome.wait_for("window.__state.lesson.cpu_robots === 2 && (window.__state.roster || {}).arenas === 2", 15, "2 computer robots, 2 arenas")
            g = "window.__state.game"
            # the camera as rw_camera's: O, Q, + and a sideways scroll on the full arena view, kept in the window's format; Home
            chrome.js(f"{g}.fullArena()")
            assert chrome.js(f"{g}.scene.mode") == "arena"
            before = chrome.js(f"{g}.scene.cam.settings()")
            chrome.js(f"{g}.turnCamera(20); {g}.zoom(-1); {g}.panCamera(1)")
            s = chrome.js(f"{g}.scene.cam.settings()")
            assert s["mode"] == "arena" and round((s["angles"]["arena"][0] - before["angles"]["arena"][0]) % 360) == 20, s
            assert s["arena"] < before["arena"] and s["pans"]["arena"] == 1, s
            assert set(s) >= {"dist", "fpv", "zoom", "arena", "centre", "orbit", "tilt", "angles", "pans"}, s
            chrome.js(f"{g}.resetCamera()")
            s = chrome.js(f"{g}.scene.cam.settings()")
            assert s["angles"]["arena"] == before["angles"]["arena"] and s["pans"]["arena"] == 0, s
            chrome.js(f"{g}.watchArena(1)")
            assert chrome.js(f"{g}.watched()") == 1, "] didn't watch arena 2"
            chrome.js(f"{g}.watchArena(1)")
            # PAUSED, big, as the window shows it
            chrome.js("window.__app.send({type: 'pause'})")
            chrome.wait_for("document.getElementById('countdown').textContent.includes('PAUSED')", 10, "PAUSED on the screen")
            chrome.js("window.__app.send({type: 'pause'})")
            chrome.wait_for("!document.getElementById('countdown').textContent.includes('PAUSED')", 10, "PAUSED gone again")
            # the teacher's look at amy: her mission as the window's preview, Load from's three places
            tab("learners")
            chrome.js("document.querySelector('button[data-pick=\"amy\"]').click()")
            chrome.wait_for("/\\[(TO DO|DONE|TEACHER)\\]/.test(document.getElementById('panelbody').textContent)", 10, "amy's mission as the window shows it")
            chrome.js("document.querySelector('button[data-sub=\"build\"]').click()")
            chrome.wait_for("document.querySelectorAll('button[data-lfrom]').length === 3", 10, "Load from: My saved, amy's saved, History")
            # computer robot 2: its Mission and Mods as a learner sees them
            chrome.js("document.querySelector('button[data-pick=\"*cpu2\"]').click()")
            chrome.wait_for("!!document.querySelector('button[data-sub=\"mods\"]')", 10, "computer robot 2's sub-tabs")
            chrome.js("document.querySelector('button[data-sub=\"mods\"]').click()")
            chrome.wait_for("document.getElementById('panelbody').textContent.includes('as a learner sees it')", 10, "its Mods as a learner sees them")
            chrome.js("document.querySelector('button[data-sub=\"garage\"]').click()")
            # the teacher's own garage: the robot turning on its pedestal, the window's word tips
            chrome.js("document.querySelector('button[data-pick=\"*me\"]').click()")
            chrome.wait_for("(() => { const c = document.querySelector('#panelbody canvas.gpreview'); return !!c && c.width > 0; })()", 10,
                            "the robot preview in the garage")
            assert chrome.js("!!document.querySelector('[data-tip=\"NAME\"]') && !!document.querySelector('[data-tip=\"RGB\"]')"), "no word tips"
            chrome.js("document.querySelector('[data-tip=\"NAME\"]').dispatchEvent(new Event('pointerover', {bubbles: true}))")
            chrome.wait_for("(() => { const t = document.getElementById('cc-tip'); return !!t && !t.hidden && t.textContent.length > 20; })()", 5,
                            "NAME's tip")
            # Rules: each Resident Robot in the vote on its own, as the window's
            tab("rules")
            chrome.wait_for("!!document.querySelector('input[data-house]')", 10, "the Resident Robots, one by one")
            chrome.js("window.__app.send({type: 'lesson', lesson: {cpu_robots: 1, arenas: 1}})")
            tab("controls")
            no_errors()
        check("Robot Lab as its window: the camera's swing, zoom and sideways move (kept in the window's format), ], PAUSED, "
              "a learner's mission preview and Load from, a computer robot's Mods, the garage's robot preview and word tips, "
              "the Resident Robots' votes", robot_parity)

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
            # (CHANGE 147) Fight Lab draws all seven, as its window (no nearest tier): its Graphics tab shows the seven and
            # the line colours; blocks to high never ask for ultra's models
            assert chrome.js(FIGHT_MODELS_FETCHED) == "", "Fight Lab's ultra models were fetched below ultra"
            tab("graphics")
            assert chrome.js("[...document.querySelectorAll('button[data-tier]')].map(b => b.dataset.tier).join(',')") == \
                "mesh,lines,blocks,low,medium,high,ultra"
            assert chrome.js("!!document.querySelector('button[data-linecol]')"), "no line colours on Fight Lab's Graphics tab"
            assert chrome.js("document.querySelector('button[data-tier=\"low\"]').classList.contains('on')")
            # (CHANGE 167) your fighter's footwork drawn at once: the Movement row, each fighter's footwork from the roster
            got = chrome.js("[!!document.querySelector('button[data-ahead=\"1\"].on'), window.__state.game.move.size, "
                            "!!window.__state.game.ahead]")
            assert got[0] and got[1] >= 2 and got[2], f"Fight Lab's Movement: {got}"
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
            # (CHANGE 143) the rings box as the window's: the mode line, B small and full again; the round time in tens
            chrome.wait_for("/PRACTICE|BATTLE/.test((document.querySelector('#places.fightboard #fb-mode') || {}).textContent || '')", 10,
                            "the rings box's mode line")
            chrome.js("window.__state.game.toggleBoard()")
            chrome.wait_for("document.getElementById('places').classList.contains('small') && !document.querySelector('#places .fring')", 5,
                            "the rings box small (B)")
            chrome.js("window.__state.game.toggleBoard()")
            chrome.wait_for("!document.getElementById('places').classList.contains('small') && !!document.querySelector('#places .fring')", 5,
                            "the rings box full again")
            assert chrome.js("window.__state.game.keyList().some(([k]) => k === 'B')"), "B isn't in Fight Lab's key list"
            tab("controls")
            rt = chrome.js("window.__state.lesson.round_time")
            chrome.js("document.getElementById('fb-time-up').click()")
            chrome.wait_for(f"window.__state.lesson.round_time === {min(300, rt + 10)}", 10, "the round time 10 s longer")
            chrome.js(f"window.__app.send({{type: 'lesson', lesson: {{round_time: {rt}}}}})")
            assert chrome.js(FIGHT_MODELS_FETCHED) == "", "Fight Lab's ultra models were fetched below ultra"
            no_errors()
        check("Fight Lab: the rings and the posed fighters are drawn (a woman with the app's own model) on blocks to high "
              "(the Graphics tab's seven), and its controls reach the server (winner stays on: the rings and the queue); the "
              "rings box with its mode line, small with B; the round time in tens", fight_lab)

        def fight_line_tiers():  # (CHANGE 147) mesh and lines as the window's: black, the rings', the hall's, the ropes'
            if "ben" not in servers:  # or open edge's and every fighter's edges as lines (each joint's own, the detailed
                return                # model's bending with it), the grids on lines only
            for tier in ("mesh", "lines"):
                chrome.js(f"window.__app.setTier('{tier}')")
                chrome.wait_for(f"window.__state.scene.tier === '{tier}' && window.__state.scene.fighters.size >= 2 && {DRAWN_RIGHT} === 'ok'",
                                20, f"Fight Lab drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                chrome.wait_for("[...window.__state.scene.fighters.values()].some(f => f.design.body === 'woman' && f.model && f.model.ready)",
                                60, f"the woman's model on {tier}")
                time.sleep(1.0)  # (frames drawn: the glowing parts' lines pulsed)
                got = chrome.js("""(() => { const sc = window.__state.scene, s = sc.scene, c = s.clearColor;
                    const lines = s.meshes.filter(m => m.material && m.material.name.startsWith('cclines') && m.getTotalVertices() > 0);
                    const fs = [...sc.fighters.values()], built = fs.filter(f => !f.model), models = fs.filter(f => f.model);
                    const own = f => f.lines.filter(([m]) => m.name === 'fighterlines' && m.parent && f.n[m.parent.name] === m.parent).length;
                    return {black: c.r + c.g + c.b === 0, stage: lines.filter(m => m.name === 'stagelines').length,
                            hall: lines.filter(m => m.name === 'halllines').length, edges: lines.some(m => m.name === 'edgelines' || m.name === 'ropelines'),
                            built: built.length, lined: built.filter(f => f.lines && own(f) >= 11).length,
                            outlines: built.filter(f => f.lines && f.lines.some(([m]) => m.material.name.startsWith('cclinesrim'))).length,
                            models: models.length, modelLines: models.filter(f => f.model.lines && f.model.lines.some(([m]) => m.skeleton)).length,
                            segments: sc.lineStats.segments, grid: sc.lineStats.grid, ms: sc.lineStats.ms, smoke: !sc.fx.look,
                            lit: s.materials.some(m => m.getClassName() === 'ShaderMaterial' && m.name.includes(':'))}; })()""")
                print(f"    {tier}: {got['segments']} line segments for the hall and rings ({got['grid']} the grids), built in {got['ms']} ms")
                assert got["black"] and got["stage"] >= 1 and got["hall"] >= 1 and got["edges"] and not got["lit"] and not got["smoke"], got
                assert got["built"] >= 1 and got["lined"] == got["built"] and got["models"] >= 1 and got["modelLines"] == got["models"], got
                assert got["outlines"] == (got["built"] if tier == "lines" else 0), got
                assert (got["grid"] > 50) == (tier == "lines"), got
                chrome.screenshot(os.path.join(work, f"fightlab_{tier}.png"))
            # the line colour: at once on the hall's, the rings' and the fighters' lines
            chrome.js("window.__app.lineColour('#ffb000')")
            got = chrome.js("window.__state.scene.lineMats.filter(m => m._colors4 && !m.ccTint).map(m => [m._colors4.color.r, m._colors4.color.g])")
            assert got and any(r > 0.99 for r, g in got) and all(abs(g / r - 0.69) < 0.02 for r, g in got if r > 0.01), got
            chrome.js("window.__app.lineColour('#33ff66')")
            assert chrome.js(FIGHT_MODELS_FETCHED) == "", "Fight Lab's ultra models were fetched on the line tiers"
            no_errors()
        check("Fight Lab's line tiers (mesh: every triangle's edges; lines: the outlines, the round fighters' too, and grids on "
              "the rings and the hall's floor) draw black with the hall's, the rings' and every fighter's lines (the detailed "
              "model's bending with it), and change colour at once", fight_line_tiers)

        def fight_ultra():  # (CHANGE 147) ultra: the window's fighters and hall, fetched now (and not before)
            if "ben" not in servers:
                return
            chrome.js("window.__app.setTier('ultra')")
            chrome.wait_for("window.__state.scene.tier === 'ultra'", 10, "Fight Lab on ultra")
            have = [n for n in ("fight_ultra.json", "stage_ultra.json") if os.path.exists(os.path.join(HERE, "models", n))]
            if len(have) < 2:
                print("    (models/ hasn't Fight Lab's ultra models: high's fighters and hall drawn)")
                chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 30, "Fight Lab drawn properly on ultra without its models")
                return
            chrome.wait_for("window.__state.scene.ultraStage && window.__state.scene.ultraFighters && window.__state.scene.fighters.size >= 2", 40,
                            "the window's fighters and hall (models/fight_ultra.json, stage_ultra.json)")
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 30, f"Fight Lab drawn properly on ultra (last: {chrome.js(DRAWN_RIGHT)})")
            got = chrome.js("""(() => { const sc = window.__state.scene, u = sc.ultraParts, L = sc.lighting, list = L.rtt.renderList;
                const built = [...sc.fighters.values()].filter(f => f.ultra);
                const own = built.map(f => f.root.getChildMeshes(false).filter(m => m.name.startsWith('fighter ')).length);
                const rings = sc.ultraRings.flatMap(r => r.meshes);
                return {fetched: %s, parts: u.parts, instances: u.instances, triangles: u.triangles, rings: rings.length,
                        crowd: u.meshes.filter(m => m.ccCrowd).length, tinted: u.meshes.filter(m => m.ccCrowd && m.isVerticesDataPresent('color')).length,
                        casters: rings.filter(m => list.includes(m)).length,
                        flatCasting: [...u.meshes, ...u.rig].filter(m => list.includes(m)).length,
                        rig: sc.rig.filter(m => m.name.startsWith('stage ')).length, built: built.length,
                        own: Math.max(...own), fewest: Math.min(...own),
                        boxes: built.some(f => f.root.getChildMeshes(false).some(m => ['box', 'cyl', 'capsule'].includes(m.name)
                            && !['blade', 'wood', 'shield'].some(k => m.material.name.startsWith(k)))),
                        shadow: L.rtt.getRenderSize(), soft: [...L.materials].some(m => m.options.defines.includes('SOFTSHADOW')),
                        haze: [...L.materials].some(m => m.options.defines.includes('FOG')),
                        hazeNear: [...L.materials].some(m => m.options.defines.includes('FOG') && !m.name.endsWith(' far')),
                        atlas: [...L.materials].some(m => m.options.defines.includes('GLOWMAP') && m.options.defines.includes('MRMAP')),
                        bloom: !!(sc.after && sc.after.pipeline.bloomEnabled), ssao: !!(sc.after && sc.after.ssao)}; })()""" % FIGHT_MODELS_FETCHED)
            print(f"    ultra hall: {got['parts']} parts, {got['instances']} placed shapes, {got['triangles']} triangles; "
                  f"{got['rings']} meshes in the rings; {got['fewest']} to {got['own']} meshes a fighter")
            assert got["fetched"] == "fight_ultra.json,stage_ultra.json" and got["parts"] >= 10 and got["instances"] > 1000, got
            assert got["crowd"] >= 24 and got["tinted"] == got["crowd"] and got["rings"] >= 5 and got["casters"] >= 3 and got["flatCasting"] == 0 and got["rig"] >= 3, got
            assert got["built"] >= 1 and 13 <= got["fewest"] and got["own"] <= 16 and not got["boxes"], got
            assert got["shadow"] == 4096 and got["soft"] and got["haze"] and not got["hazeNear"] and got["atlas"] and got["bloom"], got
            assert not got["ssao"], got
            time.sleep(2.0)
            print(f"    ultra: {chrome.js('window.__state.fps')} fps here")
            chrome.screenshot(os.path.join(work, "fightlab_ultra.png"))
            chrome.js("window.__app.setTier('low')")
            chrome.wait_for(f"window.__state.scene.tier === 'low' && {DRAWN_RIGHT} === 'ok'", 15, "Fight Lab back on low")
            no_errors()
        check("Fight Lab's ultra draws the window's fighters (a mesh a joint, the roles from an atlas) and hall (its parts, "
              "the rings for their size, the crowd and seats in twelve pieces of the stands, the flat and far casting no shadow, the hall "
              "in its haze) from models/fight_ultra.json and stage_ultra.json, fetched on ultra alone, with soft 4096 shadows "
              "and a glow", fight_ultra)

        # ---------- (CHANGE 199) the Missions on the page, run by the Missions server ----------
        missions_port = free_port()
        page = f"http://127.0.0.1:{http_port}/index.html?host=ws://127.0.0.1:{missions_port}&autoconnect=1&auto=0&speed=8"

        def press(key):  # (a key as the page hears it, not typed into anything)
            chrome.js(f"window.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(key)}}}));"
                      f"window.dispatchEvent(new KeyboardEvent('keyup', {{key: {json.dumps(key)}}}))")

        def type_code(text):
            chrome.js(f"{{ const t = document.getElementById('mc-text'); t.value = {json.dumps(text)}; t.dispatchEvent(new Event('input')); }}")

        def missions_1():
            if ROBOT is None:
                print("    (Robot Lab's folder, with the Missions server, isn't beside this folder: not tested)")
                return
            start_server("missions", ROBOT, "missions_server.py", missions_port, "MISSIONS_DATA")
            servers["ben"] = ben = Learner(missions_port, "ben")  # (another learner, as a window: his runs, his robot)
            ben.send({"type": "start", "mission": "wake_up_call", "robot": "RAZORBACK"})
            chrome.call("Page.navigate", url="about:blank")
            time.sleep(1.0)
            chrome.call("Page.navigate", url=page + "&code=CLUB42&name=amy&tier=low")
            chrome.wait_for("window.__state && window.__state.connected === true && !!window.__state.game", 30, "amy's login to the Missions class")
            assert chrome.js("[window.__state.game.id, window.__state.role, window.__state.game.mid].join()") == "missions,learner,wake_up_call"
            # the valley as the window builds it: the squares and hills, the power cell, the crate, the rockfall, the
            # power supply and the sign; the first screen (the missions, the two robots)
            got = chrome.js("""(() => { const sc = window.__state.scene, g = window.__state.game;
                return {cell: !!sc.cell, crate: !!sc.crate, tools: Object.keys(sc.tools || {}).length, rocks: sc.rockfall.parts.length,
                        supply: !!sc.supply, sign: sc.scene.meshes.some(m => m.name === 'words'), meshes: sc.scene.meshes.length,
                        intro: !document.getElementById('missionintro').hidden, cards: document.querySelectorAll('#missionintro button[data-robot]').length,
                        missions: document.querySelectorAll('#missionintro button[data-mission]').length,
                        phrasebook: document.querySelectorAll('#mc-book .mc-says b').length}; })()""")
            assert got["cell"] and got["crate"] and got["tools"] == 4 and got["rocks"] == 11 and got["supply"] and got["sign"], got
            assert got["intro"] and got["cards"] == 2 and got["missions"] == 2 and got["phrasebook"] >= 6, got
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 15, "the valley drawn properly on low")
            press("1")  # TITAN
            chrome.wait_for("window.__state.game.robotName === 'TITAN' && document.getElementById('missionintro').hidden"
                            " && !!window.__state.game.parsed && window.__state.scene.robots.has('me')", 10, "TITAN in the valley")
            chrome.wait_for("window.__state.game.ghosts.has('ben')", 10, "ben's robot from the world message")
            # ben runs: his robot drawn where his run takes it, dimmed, his name over it
            ben.send({"type": "program", "mission": "wake_up_call", "text": "move forward 3\nturn right\nmove forward 4"})
            chrome.wait_for("""(() => { const g = window.__state.game.ghosts.get('ben'), v = window.__state.scene.robots.get('ghost ben');
                return g && !g.anim && !g.steps.length && g.at[0] === 5 && g.at[1] === 3 && v && v.root.isEnabled() && v.label.isEnabled()
                    && v.tints.chassis && v.tints.chassis !== '1,1,1'; })()""", 30, "ben's robot driven to where his run left it, dimmed, his name over it")
            # C: the code panel; a near miss shows its hint (never corrected) and RUN stays off
            press("c")
            chrome.wait_for("!document.getElementById('missioncode').hidden", 5, "the code panel (C)")
            type_code("move forward 3\npick up the powr cell")
            chrome.wait_for("document.getElementById('mc-problems').textContent.includes('Did you mean')", 10, "the near miss's hint")
            assert chrome.js("document.getElementById('mc-run').disabled") is True, "RUN on with a line it can't read"
            assert "<b>2</b>" in chrome.js("document.getElementById('mc-gutter').innerHTML"), "the line not marked"
            assert chrome.js("document.getElementById('mc-text').value").endswith("powr cell"), "the line was corrected"
            # the five steps (wake_up_call_test.STEPS) as one program, the Python beside each line, RUN: three stars
            type_code(MISSION_1)
            chrome.wait_for("!document.getElementById('mc-run').disabled && document.getElementById('mc-problems').textContent.includes('All 17 lines understood')",
                            10, "RUN on with the five steps read")
            py = chrome.js("document.getElementById('mc-py').textContent")
            assert "robot.move_forward(3)" in py and 'robot.pick_up("power cell")' in py and "robot.repair()" in py, py
            chrome.js("document.querySelector('#missioncode button[data-mtab=\"code\"]').click()")
            assert "from clubcoders import robot" in chrome.js("document.getElementById('mc-whole').textContent")
            chrome.js("document.querySelector('#missioncode button[data-mtab=\"pseudo\"]').click()")
            chrome.js("document.getElementById('mc-run').click()")
            chrome.wait_for("window.__state.game.playing && window.__state.game.event", 15, "the run's events playing")
            chrome.wait_for("!document.getElementById('missiondone').hidden", 60, "MISSION COMPLETE")
            got = chrome.js("""(() => { const g = window.__state.game; return {stars: g.doneStars, complete: g.s.complete, lines: g.s.linesUsed,
                energy: g.s.energy, hud: document.querySelectorAll('#mh-stars i.on').length, done: document.querySelectorAll('#mh-objectives .done').length,
                solar: g.progress.parts.includes('solar_panel'), log: g.logRows.map(r => r[0]).join('|'), at: [g.view.x, g.view.y],
                card: document.getElementById('missiondone').textContent}; })()""")
            assert got["stars"] == 3 and got["complete"] and got["lines"] == 17 and got["energy"] == 8 and got["hud"] == 3 and got["done"] == 5, got
            assert got["solar"] and "Unlocked: Solar Panel" in got["card"] and "lights come on all over Brookfield" in got["log"], got
            assert "Run 1: 17 lines" in got["log"] and got["at"] == [13, 4], got
            chrome.js("document.getElementById('md-close').click()")
            time.sleep(1.5)
            chrome.screenshot(os.path.join(work, "missions_valley.png"))
            no_errors()
        check("Missions: the page logs in to a Missions class, draws the valley and TITAN, shows a near miss's hint, types the "
              "five steps (the Python beside each line) and finishes with three stars; another learner's robot (a raw "
              "client's) is drawn where his run left it, dimmed, his name over it", missions_1)

        def missions_tiers():  # every tier the page has, as the mission window's
            if "ben" not in servers:
                return
            tab("graphics")
            assert chrome.js("[...document.querySelectorAll('button[data-tier]')].map(b => b.dataset.tier).join(',')") == \
                "mesh,lines,blocks,low,medium,high,ultra"
            for tier in ("mesh", "lines", "blocks", "medium", "high", "ultra", "low"):
                chrome.js(f"window.__app.setTier('{tier}')")
                chrome.wait_for(f"window.__state.scene.tier === '{tier}' && window.__state.scene.robots.size >= 2 && {DRAWN_RIGHT} === 'ok'",
                                30, f"the valley drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                time.sleep(0.8)
                got = chrome.js("""(() => { const sc = window.__state.scene, s = sc.scene, c = s.clearColor;
                    const lines = s.meshes.filter(m => m.material && m.material.name.startsWith('cclines') && m.getTotalVertices() > 0);
                    const robots = [...sc.robots.values()];
                    return {black: c.r + c.g + c.b === 0, place: lines.filter(m => m.name === 'missionlines').length,
                            robots: robots.length, lined: robots.filter(v => v.root.getChildMeshes(false).some(m => m.name === 'robotlines')).length,
                            lamps: !!(sc.glows.warning && sc.glows.warning.lines), ultra: !!sc.ultraRobots, segments: sc.lineStats.segments,
                            lit: s.materials.some(m => m.getClassName() === 'ShaderMaterial' && m.name.includes(':'))}; })()""")
                if tier in ("mesh", "lines"):
                    print(f"    {tier}: {got['segments']} line segments for the valley")
                    assert got["black"] and got["place"] >= 10 and got["lined"] == got["robots"] and got["lamps"] and not got["lit"], got
                else:
                    assert not got["black"] and got["place"] == 0 and (got["lit"] or tier == "blocks"), got
                if tier == "ultra" and os.path.exists(os.path.join(HERE, "models", "robot_ultra.json")):
                    chrome.wait_for("window.__state.scene.ultraRobots && window.__state.scene.robots.size >= 2", 30, "the window's smooth robots on ultra")
                chrome.screenshot(os.path.join(work, f"missions_{tier}.png"))
            no_errors()
        check("Missions on every tier: mesh and lines (black, the valley's, the robots' and the lights' own lines), blocks to "
              "high, ultra (the window's smooth robots)", missions_tiers)

        def missions_2():  # Lights Out: the hill road at night, the recorded solution (lights_out_test.SOLUTION)
            if "ben" not in servers:
                return
            chrome.js("window.__state.game.showIntro()")
            press("F2")
            chrome.wait_for("window.__state.game.mid === 'lights_out' && !document.getElementById('missionintro').hidden"
                            " && window.__state.scene.mid === 'lights_out'", 10, "Mission 2 from the first screen (F2)")
            got = chrome.js("""(() => { const sc = window.__state.scene, e = x => sc.glows['lamp' + x].mat._vectors3.emission.x;
                return {lamps: Object.keys(sc.lamps).map(Number), piles: Object.keys(sc.piles).length, mast: !!sc.mast,
                        dark: [4, 8, 12].map(e), lit: [6, 10].map(e), moon: sc.look.pbr.sun.colour.join(),
                        ghost: sc.robots.has('ghost ben') && sc.robots.get('ghost ben').root.isEnabled()}; })()""")
            assert got["lamps"] == [4, 6, 8, 10, 12] and got["piles"] >= 8 and got["mast"] and got["moon"] == "0.38,0.45,0.75", got
            assert all(v < 0.1 for v in got["dark"]) and all(v > 5 for v in got["lit"]) and not got["ghost"], got
            press("1")
            chrome.wait_for("window.__state.game.s && window.__state.game.s.night === 1 && !!window.__state.game.parsed", 10, "Mission 2 started")
            press("c")
            type_code(MISSION_2)
            chrome.wait_for("!document.getElementById('mc-run').disabled", 10, "RUN on with the solution read")
            chrome.js("window.__state.game.closePanel(); document.getElementById('mc-run').click()")
            chrome.wait_for("document.getElementById('mh-tool').textContent.includes('Night 2 of 3') && "
                            "document.getElementById('mh-vars').textContent.includes('lamps = ')", 120, "night 2 and the variables in the HUD")
            time.sleep(1.5)
            chrome.screenshot(os.path.join(work, "missions_night.png"))
            chrome.wait_for("!document.getElementById('missiondone').hidden", 240, "MISSION COMPLETE on all three nights")
            got = chrome.js("""(() => { const g = window.__state.game, sc = window.__state.scene;
                return {stars: g.doneStars, nights: g.s.nightEnergy, lines: g.s.linesUsed, night3: g.logRows.some(r => r[0].startsWith('Night 3 of 3')),
                        lamps: Object.keys(sc.lamps).map(x => sc.glows['lamp' + x].mat._vectors3.emission.x), card: document.getElementById('missiondone').textContent}; })()""")
            assert got["stars"] == 3 and len(got["nights"]) == 3 and got["lines"] == 15 and got["night3"], got
            assert all(v > 5 for v in got["lamps"]) and "one program lit the hill road" in got["card"], got
            chrome.js("document.getElementById('md-close').click()")
            no_errors()
        check("Missions: Lights Out on the page: the hill road at night (the lamps dark and lit as the night has them), the "
              "recorded solution played to three stars, the nights and the variables in the HUD, every lamp lit at the end", missions_2)

        def missions_teacher():  # the teacher's page: the class listed, the mission changed for everyone
            if "ben" not in servers:
                return
            chrome.call("Page.navigate", url="about:blank")
            time.sleep(1.0)
            chrome.call("Page.navigate", url=page + "&code=TEACH99&tier=low")
            chrome.wait_for("window.__state && window.__state.connected === true && window.__state.game && window.__state.game.id === 'missions'", 30,
                            "the teacher's login to the Missions class")
            chrome.wait_for("!!document.getElementById('mi-watch')", 10, "WATCH THE CLASS on the teacher's first screen")
            chrome.js("document.getElementById('mi-watch').click()")
            chrome.wait_for("document.getElementById('mh-class').textContent.includes('ben:')", 10, "the class top right")
            chrome.wait_for("window.__state.scene.robots.has('ghost ben')", 10, "ben's robot on the teacher's page")
            tab("class")
            assert "ben" in chrome.js("document.getElementById('panelbody').textContent")
            assert chrome.js("[...document.querySelectorAll('#panelhead button')].map(b => b.dataset.tab).join(',')") == "class,missions,graphics,about"
            chrome.js("document.querySelector('button[data-lesson=\"2\"]').click()")
            chrome.wait_for("window.__state.game.classMsg.lesson === 2 && window.__state.game.mid === 'lights_out'", 10,
                            "Mission 2 for the class (the teacher's page goes to it too)")
            chrome.js("document.querySelector('button[data-lesson=\"1\"]').click()")
            no_errors()
        check("Missions: the teacher's page lists the class top right and in the Class tab, draws the learners' robots and "
              "changes the mission for everyone", missions_teacher)
        for key in list(servers):  # (the other games done with: the laptop's memory back for City Lab)
            proc = servers.pop(key)
            proc.close() if isinstance(proc, Learner) else stop(proc)

        # ---------- (CHANGE 201) City Lab on the page ----------
        city_port = free_port()
        CITY = game_folder("citylab", "city")
        CITY_STATE = """(() => { const g = window.__state.game, sc = g.scene, s = sc.scene, c = s ? s.clearColor : null;
            const lines = s ? s.meshes.filter(m => m.material && m.material.name.startsWith('cclines') && m.getTotalVertices() > 0) : [];
            return {built: !!sc.city && (sc.cityMeshes || []).length, karts: sc.karts.size, fighters: sc.fighters.size, robots: sc.robots.size,
                    black: !!c && c.r + c.g + c.b === 0, cityLines: lines.filter(m => m.name === 'citylines').length,
                    carLines: lines.filter(m => m.name === 'kartlines').length,
                    fighterLines: lines.filter(m => m.name === 'fighterlines' || m.name.endsWith(' lines') || m.name.endsWith(' rim')).length,
                    lit: s ? s.materials.some(m => m.getClassName() === 'ShaderMaterial' && m.name.startsWith('citywalls')) : false,
                    tier: sc.tier, time: sc.time, markers: Object.keys(sc.markers || {}).length, chips: sc.city ? sc.city.chips.length : 0}; })()"""

        def hold(key, secs):  # (a key held down for a while, as the page hears it)
            chrome.js(f"window.dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(key)}}}))")
            time.sleep(secs)
            chrome.js(f"window.dispatchEvent(new KeyboardEvent('keyup', {{key: {json.dumps(key)}}}))")

        def city_watch():  # the teacher's page watches a City Lab class: the city, a window's person and the cars moving
            if CITY is None:
                print("    (City Lab's folder isn't beside this one: not tested)")
                return
            start_server("citylab", CITY, "city_server.py", city_port, "CITYLAB_DATA")
            servers["ben-city"] = CityWalker(city_port, "ben")
            open_game(city_port, "citylab", "&cam=city")
            chrome.js("window.__app.send({type: 'lesson', lesson: {hazards: {traffic: true, robots: true}, traffic: 6, robots: 6}})")
            chrome.wait_for(f"(() => {{ const s = {CITY_STATE}; return s.built >= 10 && s.karts >= 16 && s.fighters >= 2 && s.robots >= 6; }})()", 40,
                            "the city, its cars (parked and traffic), the teacher and ben as fighters, the robots")
            got = chrome.js(CITY_STATE)
            assert got["markers"] == 3 and got["chips"] >= 20, got
            # ben (a window, scripted) walks, the traffic drives: both drawn moving
            where = "(() => { const g = window.__state.game, out = {}; for (const [id, e] of g.latest) out[id] = [e.x, e.y]; return out; })()"
            ben = chrome.wait_for("(() => { const r = window.__state.roster; return r && r.mine && r.mine.ben !== undefined && r.mine.ben !== null ? String(r.mine.ben) : null; })()", 10, "ben's person")
            a = chrome.js(where)
            time.sleep(3)
            b = chrome.js(where)
            moved = {int(k): ((b[k][0] - v[0]) ** 2 + (b[k][1] - v[1]) ** 2) ** 0.5 for k, v in a.items() if k in b}
            assert moved.get(int(ben), 0) > 3, f"ben didn't walk: {moved.get(int(ben))}"
            assert sum(1 for k, d in moved.items() if 32 <= k < 128 and d > 5) >= 3, f"the traffic didn't drive: {moved}"
            assert chrome.js(f"(() => {{ const f = window.__state.scene.fighters.get({ben}); return !!f && f.root.isEnabled(); }})()"), "ben not drawn"
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 20, "the city drawn properly on low")
            tab("graphics")
            assert chrome.js("[...document.querySelectorAll('button[data-tier]')].map(b => b.dataset.tier).join(',')") == \
                "mesh,lines,blocks,low,medium,high,ultra"
            for tier in ("mesh", "lines", "blocks", "medium", "high", "ultra", "low"):
                chrome.js(f"window.__app.setTier('{tier}')")
                chrome.wait_for(f"window.__state.scene.tier === '{tier}' && {DRAWN_RIGHT} === 'ok' && "
                                f"(() => {{ const s = {CITY_STATE}; return s.built >= 8 && s.karts >= 16 && s.fighters >= 2 && s.robots >= 6; }})()",
                                40, f"the city drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                time.sleep(1.0)
                got = chrome.js(CITY_STATE)
                if tier in ("mesh", "lines"):
                    print(f"    {tier}: {chrome.js('window.__state.scene.lineStats.segments')} line segments for the city")
                    assert got["black"] and got["cityLines"] >= 4 and got["carLines"] >= 10 and got["fighterLines"] >= 2 and not got["lit"], got
                else:
                    assert not got["black"] and got["cityLines"] == 0 and (got["lit"] or tier == "blocks"), got
                chrome.screenshot(os.path.join(work, f"city_{tier}.png"))
            # the teacher's Controls: night for everyone (the headlights, the street lamps), then day again
            tab("controls")
            assert chrome.js("!!document.getElementById('btn-start') && !!document.getElementById('sel-city') && "
                             "document.querySelectorAll('button[data-job]').length === 4")
            chrome.js("document.querySelector('button[data-time=\"night\"]').click()")
            chrome.wait_for("window.__state.scene.time === 'night' && (window.__state.lesson || {}).time === 'night'", 10, "night for the class")
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok'", 20, "the city drawn properly at night")
            time.sleep(1.0)
            chrome.screenshot(os.path.join(work, "city_night.png"))
            assert chrome.js("window.__state.scene.lighting.lights.count") >= 5, "no headlights at night"
            chrome.js("document.querySelector('button[data-time=\"day\"]').click()")
            chrome.wait_for("window.__state.scene.time === 'day'", 10, "day again")
            no_errors()
        check("City Lab: the teacher's page watches a City Lab class: the city built from the server's (its blocks, buildings, "
              "markings, places, rings and chips), the people as Fight Lab's fighters, the cars as Kart Lab's, the robots "
              "as Robot Lab's, a learner's window walking and the traffic driving, on every tier (mesh and lines black with the "
              "city's, the cars' and the fighters' lines), night from Controls", city_watch)

        def city_learner():  # a learner's page: logs in, walks, gets into a car and drives, predicted
            if "citylab" not in servers:
                return
            chrome.call("Page.navigate", url="about:blank")
            time.sleep(1.0)
            chrome.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/index.html?host=ws://127.0.0.1:{city_port}"
                                             "&code=CLUB42&name=amy&auto=0&tier=low")
            chrome.wait_for("!!window.__app && !!document.getElementById('cpass')", 20, "the page")
            time.sleep(1.0)
            chrome.js("document.getElementById('cpass').value = 'amy-pass-1'; document.getElementById('connect').click()")
            chrome.wait_for("window.__state && window.__state.connected === true && window.__state.game && window.__state.game.id === 'citylab'", 30,
                            "amy's login to the City Lab class")
            chrome.wait_for("!!window.__state.game.predictor && window.__state.game.predId === window.__state.game.myId()", 20, "her person predicted")
            p = "window.__state.game.predictor"
            a = chrome.js(f"[{p}.state.x, {p}.state.y]")
            hold("w", 2.5)  # (W walks away from the camera, by the keys as the window reads them)
            time.sleep(0.6)
            b = chrome.js(f"[{p}.state.x, {p}.state.y, {p}.corrections]")
            walked = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            server = chrome.js("(() => { const g = window.__state.game, e = g.latest.get(g.myId()); return [e.x, e.y]; })()")
            print(f"    walked {walked:.1f} m, {b[2]} corrections; the server has her {((server[0] - b[0]) ** 2 + (server[1] - b[1]) ** 2) ** 0.5:.2f} m from the prediction")
            assert walked > 4 and b[2] <= 3, b
            assert ((server[0] - b[0]) ** 2 + (server[1] - b[1]) ** 2) ** 0.5 < 0.1, "the server's person isn't where the page predicted"
            chrome.screenshot(os.path.join(work, "city_street.png"))
            # into the nearest car (the window's own test walk: demo_get_in), then the keys drive it
            chrome.js("window.__state.game.demo = 'getin'")
            chrome.wait_for("window.__state.game.driving() && window.__state.game.predId === window.__state.game.myCar()", 40, "in a car, predicted")
            chrome.js("window.__state.game.demo = null")
            time.sleep(0.5)
            speeds = []
            down = lambda k: chrome.js(f"window.dispatchEvent(new KeyboardEvent('keydown', {{key: '{k}'}}))")
            up = lambda k: chrome.js(f"window.dispatchEvent(new KeyboardEvent('keyup', {{key: '{k}'}}))")
            for keys, secs in ((["s"], 2.0), (["w", "a"], 2.5)):  # (out of the bay backwards, then away and round to the left)
                for k in keys:
                    down(k)
                for _ in range(int(secs / 0.25)):
                    time.sleep(0.25)
                    speeds.append(chrome.js(f"{p}.state.v"))
                if "w" in keys:
                    chrome.screenshot(os.path.join(work, "city_driving.png"))
                for k in keys:
                    up(k)
            c1 = chrome.js(f"[{p}.state.x, {p}.state.y, {p}.corrections]")
            drove = max(abs(v) for v in speeds)
            print(f"    drove at up to {drove * 3.6:.0f} km/h, {c1[2]} corrections in the car")
            assert drove > 5 and c1[2] <= 5, (speeds, c1)
            assert chrome.js("document.getElementById('ch-speed').textContent.endsWith('km/h')"), "no speed in the HUD"
            # the touch controls: the car's (the item button gets you out), then on foot the stick and the moves
            chrome.js("window.__app.setTouch('on')")
            chrome.wait_for("!document.getElementById('touchpad').hidden && !document.getElementById('touchpad').classList.contains('foot') "
                            "&& document.getElementById('tp-item').textContent === 'GET OUT'", 5, "the car's touch controls")
            for _ in range(40):  # (the brake, a moment at a time, to a stop)
                if abs(chrome.js(f"{p}.state.v")) < 1.0:
                    break
                hold("s", 0.12)
            press("e")
            chrome.wait_for("!window.__state.game.driving() && window.__state.game.predId === window.__state.game.myId()", 15, "out of the car, on foot")
            chrome.wait_for("document.getElementById('touchpad').classList.contains('foot')", 5, "the touch controls on foot")
            chrome.js("window.__app.setTouch('off')")
            no_errors()
        check("City Lab: a learner's page logs in, walks with the keys (her person predicted, the server agreeing), gets into "
              "a car and drives it with the keys (the car predicted, few corrections), the touch controls for a car and on foot",
              city_learner)
        for key, proc in servers.items():
            proc.close() if isinstance(proc, Learner) else stop(proc)
        servers.clear()

        # ---------- (CHANGE 202) Craft Lab on the page ----------
        craft_port = free_port()
        CRAFT = game_folder("craftlab", "craft")
        CRAFT_STATE = """(() => { const g = window.__state.game, sc = g.scene, s = sc.scene, c = s ? s.clearColor : null, st = sc.stats();
            const lines = s ? s.meshes.filter(m => m.material && m.material.ccLine && m.getTotalVertices() > 0) : [];
            return {world: !!g.world, chunks: st.chunks, meshes: st.meshes, chunkLines: st.lines, models: st.models,
                    black: !!c && c.r + c.g + c.b === 0, modelLines: lines.filter(m => !m.name.startsWith('chunklines')).length,
                    lit: s ? s.materials.some(m => m.getClassName() === 'ShaderMaterial' && m.name === 'craftsolid') : false,
                    shadow: !!sc.rtt, gl2: sc.engine.webGLVersion >= 2, sky: !!sc.sky, stars: !!(sc.sky && sc.sky.stars.isEnabled()),
                    clouds: sc.sky ? sc.sky.clouds.length : 0, wave: !!(sc.mats && sc.mats.solid && sc.mats.solid._floats && sc.mats.solid._floats.u_wave),
                    tier: sc.tier, time: sc.time}; })()"""

        def craft_watch():  # the teacher's page watches a Craft Lab class: the island, a learner's window walking, every tier
            if CRAFT is None:
                print("    (Craft Lab's folder isn't beside this one: not tested)")
                return
            start_server("craftlab", CRAFT, "craft_server.py", craft_port, "CRAFTLAB_DATA", ("--seed", "2026", "--size", "small"))
            servers["ben-craft"] = CityWalker(craft_port, "ben")  # (the same 18-byte inputs: a circle in the world's frame)
            open_game(craft_port, "craftlab", "&cam=free")
            chrome.wait_for(f"(() => {{ const s = {CRAFT_STATE}; return s.world && s.chunks >= 40 && s.models >= 2; }})()", 60,
                            "the island built (its chunks meshed) and the teacher and ben as models")
            ben = chrome.wait_for("(() => { const g = window.__state.game; const b = [...g.names.entries()].find(([, n]) => n.name === 'ben');"
                                  " return b ? String(b[0]) : null; })()", 10, "ben in the roster")
            where = f"(() => {{ const e = window.__state.game.latest.get({ben}); return e ? [e.x, e.y] : null; }})()"
            a = chrome.wait_for(where, 10, "ben in the snapshots")
            time.sleep(3)
            b = chrome.js(where)
            assert ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 > 1.5, f"ben didn't walk: {a} {b}"
            # L: the camera follows ben (the teacher's view of each learner in turn)
            press("l")
            chrome.wait_for(f"window.__state.game.view === 'follow' && window.__state.game.watch === {ben}", 5, "the camera on ben")
            time.sleep(1.0)
            chrome.screenshot(os.path.join(work, "craft_follow.png"))
            assert chrome.js(f"window.__state.scene.models.has({ben})"), "ben not drawn"
            chrome.js("window.__state.game.setView('free')")
            chrome.js("{ const g = window.__state.game, s = g.world.spawn; g.free = [s[0] - 24, s[1] - 24, s[2] + 16]; g.yaw = 45; g.pitch = -28; }")
            tab("graphics")
            assert chrome.js("[...document.querySelectorAll('button[data-tier]')].map(b => b.dataset.tier).join(',')") == \
                "mesh,lines,blocks,low,medium,high,ultra"
            for tier in ("mesh", "lines", "blocks", "low", "medium", "high", "ultra"):
                chrome.js(f"window.__app.setTier('{tier}')")
                chrome.wait_for(f"window.__state.scene.tier === '{tier}' && {DRAWN_RIGHT} === 'ok' && "
                                f"(() => {{ const s = {CRAFT_STATE}; return s.chunks >= 40 && s.models >= 2; }})()",
                                40, f"the island drawn properly on {tier} (last: {chrome.js(DRAWN_RIGHT)})")
                time.sleep(1.5)
                got = chrome.js(CRAFT_STATE)
                if tier in ("mesh", "lines"):
                    assert got["black"] and got["chunkLines"] >= 20 and got["modelLines"] >= 2 and not got["lit"] and not got["sky"], got
                else:
                    assert not got["black"] and got["lit"] and got["chunkLines"] == 0 and got["sky"], got
                    assert got["shadow"] == (tier in ("medium", "high", "ultra") and got["gl2"]), got
                    assert got["clouds"] == {"blocks": 0, "low": 1, "medium": 1, "high": 1, "ultra": 2}[tier], got
                    assert got["wave"] == (tier in ("high", "ultra")), got
                chrome.screenshot(os.path.join(work, f"craft_{tier}.png"))
            chrome.js("window.__app.setTier('medium')")
            # the teacher's Controls: night for everyone (the stars, the moon, the torches' light), then day again
            tab("controls")
            assert chrome.js("!!document.getElementById('cr-gather') && !!document.getElementById('cr-kit') && "
                             "document.querySelectorAll('button[data-time]').length === 5")
            chrome.js("document.querySelector('button[data-time=\"night\"]').click()")
            chrome.wait_for("(window.__state.lesson || {}).time === 'night' && Math.abs(window.__state.scene.time - 0.75) < 0.01", 10, "night for the class")
            chrome.wait_for(f"{DRAWN_RIGHT} === 'ok' && {CRAFT_STATE}.stars", 20, "the island at night, the stars out")
            time.sleep(1.0)
            chrome.screenshot(os.path.join(work, "craft_night.png"))
            chrome.js("document.querySelector('button[data-time=\"day\"]').click()")
            chrome.wait_for("(window.__state.lesson || {}).time === 'day' && !window.__state.scene.sky.stars.isEnabled()", 10, "day again")
            no_errors()
        check("Craft Lab: the teacher's page watches a Craft Lab class: the island from the server's packed world, meshed "
              "chunk by chunk as the window meshes it, the teacher and a learner's window as models (ben walking, L follows "
              "him), on every tier (mesh and lines black with the blocks' and the models' lines; blocks to ultra in Craft "
              "Lab's own shader, the clouds, the sun's shadows from medium, the waving leaves on high and ultra), night "
              "from Controls (the stars)", craft_watch)

        def craft_learner():  # a learner's page over a school's Wi-Fi: walks, jumps, digs, places, crafts planks, a phone
            if "craftlab" not in servers:
                return
            servers.pop("ben-craft").close()
            for top in (os.path.dirname(HERE), os.path.dirname(os.path.dirname(HERE))):
                if os.path.isdir(os.path.join(top, "engine")) and top not in sys.path:
                    sys.path.insert(0, top)
            from engine import fault_relay
            relay = free_port()
            fault_relay.run_relay(relay, craft_port, lag=60, jitter=15, stall=0.0, seed=5)  # (CLUBCODERS_LAG=60,15)
            chrome.call("Page.navigate", url="about:blank")
            time.sleep(1.0)
            chrome.call("Page.navigate", url=f"http://127.0.0.1:{http_port}/index.html?host=ws://127.0.0.1:{relay}"
                                             "&code=CLUB42&name=amy&auto=0&tier=low&lock=0")
            chrome.wait_for("!!window.__app && !!document.getElementById('cpass')", 20, "the page")
            time.sleep(1.0)
            chrome.js("document.getElementById('cpass').value = 'amy-pass-1'; document.getElementById('connect').click()")
            chrome.wait_for("window.__state && window.__state.connected === true && window.__state.game && window.__state.game.id === 'craftlab'", 30,
                            "amy's login to the Craft Lab class")
            g, p = "window.__state.game", "window.__state.game.predictor"
            chrome.wait_for(f"!!{p} && {g}.scene.stats().chunks >= 30 && !!{g}.inventory", 60, "her player predicted, the island drawn")
            time.sleep(1.5)
            # (the way with the most open ground ahead: the spawn may face a tree or a hill)
            open_way = f"""(() => {{ const g = {g}, s = g.predictor.state, cube = g.scene.tables.cube;
                let best = 0, most = -1;
                for (let a = 0; a < 360; a += 30) {{
                    let free = 0;
                    for (let d = 1; d <= 8; d++) {{
                        const x = Math.floor(s.x + Math.cos(a * Math.PI / 180) * d), y = Math.floor(s.y + Math.sin(a * Math.PI / 180) * d);
                        const z = Math.floor(s.z + 0.01);
                        if (cube[g.world.get(x, y, z)] || cube[g.world.get(x, y, z + 1)] || !cube[g.world.get(x, y, z - 1)]) break;
                        free++;
                    }}
                    if (free > most) {{ most = free; best = a; }}
                }}
                g.yaw = best; g.pitch = -10; return most; }})()"""
            chrome.js(open_way)
            time.sleep(2.0)  # (the lead on the server settled after the island's first meshing: as a window's, a few seconds in)
            a = chrome.js(f"[{p}.state.x, {p}.state.y, {p}.state.z]")
            hold("w", 2.0)
            time.sleep(1.0)
            b = chrome.js(f"[{p}.state.x, {p}.state.y, {p}.state.z, {p}.corrections]")
            walked = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            server = chrome.js(f"(() => {{ const e = {g}.latest.get({g}.me); return [e.x, e.y, e.z]; }})()")
            off = sum((server[i] - b[i]) ** 2 for i in range(3)) ** 0.5
            print(f"    walked {walked:.1f} m over 60 ms each way and 15 ms of jitter, {b[3]} corrections; the server has her {off:.3f} m from the prediction")
            assert walked > 2.5 and b[3] <= 3 and off < 0.05, (a, b, server)
            # a jump: the feet over a block and a quarter up
            z0 = chrome.js(f"{p}.state.z")
            hold(" ", 0.1)
            top = z0
            for _ in range(12):
                top = max(top, chrome.js(f"{p}.state.z"))
                time.sleep(0.05)
            assert top > z0 + 0.9, f"no jump: {z0} -> {top}"
            time.sleep(1.0)
            # dig the block at your feet in front (looked at), then put it back
            chrome.js(f"{g}.pitch = -65")
            time.sleep(0.4)
            hit = chrome.wait_for(f"JSON.stringify({g}.lookTarget())", 5, "a block looked at")
            pos, face = json.loads(hit)[:2]
            block = chrome.js(f"{g}.world.get({pos[0]}, {pos[1]}, {pos[2]})")
            before = chrome.js(f"JSON.stringify({g}.inventory.inv)")
            chrome.js(f"{g}.mouse.left = true")
            chrome.wait_for(f"{g}.world.get({pos[0]}, {pos[1]}, {pos[2]}) === 0", 8, "the block dug")
            chrome.js(f"{g}.mouse.left = false")
            chrome.wait_for(f"JSON.stringify({g}.inventory.inv) !== {json.dumps(before)}", 5, "what it dropped in her inventory")
            time.sleep(1.0)
            assert chrome.js(f"{g}.world.get({pos[0]}, {pos[1]}, {pos[2]})") == 0, "the server put the dug block back"
            inv = json.loads(chrome.js(f"JSON.stringify({g}.inventory.inv)"))
            slot = next(i for i, s in enumerate(inv[:9]) if s and s[0] != chrome.js(f"{g}.itemId('apple')"))
            got = inv[slot][0]
            press(str(slot + 1))
            chrome.wait_for(f"{g}.inventory.selected === {slot}", 5, "the slot chosen")
            # (somewhere clear of her own box, a few metres ahead: a block can't go where you stand)
            put = json.loads(chrome.wait_for(f"""(() => {{ const g = {g}, grass = g.itemId('tall_grass');
                const people = [...g.entities.values()].filter(e => e.kind === 0);
                for (const pitch of [-35, -45, -28, -55, -20, -65]) for (const turn of [0, 40, -40, 80, -80]) {{
                    g.pitch = pitch;
                    g.yaw = (g.yaw + turn + 360) % 360;
                    const hit = g.lookTarget();
                    if (hit) {{
                        const c = [0, 1, 2].map(i => hit[0][i] + hit[1][i]);
                        const clear = people.every(s => c[0] + 1 <= s.x - 0.3 || c[0] >= s.x + 0.3 || c[1] + 1 <= s.y - 0.3 || c[1] >= s.y + 0.3 ||
                                                         c[2] >= s.z + 1.8 || c[2] + 1 <= s.z);
                        if (clear && [0, grass].includes(g.world.get(...c))) return JSON.stringify(c);
                    }}
                    g.yaw = (g.yaw - turn + 360) % 360;
                }}
                return null; }})()""", 5, "a clear place to put it"))
            chrome.js(f"{g}.mouse.right = true")
            time.sleep(0.12)
            chrome.js(f"{g}.mouse.right = false")
            chrome.wait_for(f"{g}.world.get({put[0]}, {put[1]}, {put[2]}) === {got}", 8, f"block {got} put down at {put}")
            print(f"    dug block {block} at {pos} (block {got} in her inventory), put it down at {put}")
            chrome.screenshot(os.path.join(work, "craft_learner.png"))
            # planks in the inventory screen: the teacher makes the class creative (the creative box has every log)
            from websockets.sync.client import connect
            teacher, end = None, time.time() + 25
            while teacher is None:  # (the teacher's page of the check before may be a moment letting go of its place)
                ws = connect(f"ws://127.0.0.1:{craft_port}", max_size=None, open_timeout=20)
                ws.send(json.dumps({"type": "hello", "name": "Mr T", "code": "TEACH99", "version": ""}))
                try:
                    while json.loads(ws.recv(timeout=10)).get("type") != "welcome":
                        pass
                    teacher = ws
                except Exception:
                    if time.time() > end:
                        raise
                    time.sleep(2)
            def drain():  # (its messages read and dropped, so the server's outbox to it never fills)
                try:
                    while True:
                        teacher.recv()
                except Exception:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            teacher.send(json.dumps({"type": "mode"}))
            chrome.wait_for(f"{g}.creative()", 10, "creative for the class")
            press("e")
            chrome.wait_for(f"!!{g}.screen && {g}.screen.kind === 'inventory' && !!document.querySelector('#craftscreen [data-area=palette]')", 5, "the inventory screen")
            log, planks = chrome.js(f"{g}.itemId('log')"), chrome.js(f"{g}.itemId('planks')")
            k = chrome.js(f"{g}.screen.creativeItems.indexOf({log})")
            for _ in range(k // 36):
                chrome.js("document.getElementById('cs-next').click()")
            click = lambda sel, button=0: chrome.js(f"document.querySelector('#craftscreen {sel}').dispatchEvent(new PointerEvent('pointerdown', "
                                                    f"{{bubbles: true, button: {button}}}))")
            click(f'[data-area="palette"][data-i="{k % 36}"]')
            chrome.wait_for(f"!!{g}.inventory.cursor && {g}.inventory.cursor[0] === {log}", 5, "a stack of logs taken")
            click('[data-area="grid"][data-i="0"]', 2)  # (the right button: one log in the grid)
            chrome.wait_for(f"!!{g}.inventory.result && {g}.inventory.result[0] === {planks} && {g}.inventory.result[1] === 4", 5, "four planks shown")
            time.sleep(0.5)
            chrome.screenshot(os.path.join(work, "craft_inventory.png"))
            click('[data-area="inv"][data-i="9"]')  # (the logs left down in the inventory)
            chrome.wait_for(f"!{g}.inventory.cursor", 5, "the logs put down")
            click('[data-area="result"][data-i="0"]')
            chrome.wait_for(f"!!{g}.inventory.cursor && {g}.inventory.cursor[0] === {planks}", 5, "the planks made")
            click('[data-area="inv"][data-i="10"]')
            chrome.wait_for(f"!!{g}.inventory.inv[10] && {g}.inventory.inv[10][0] === {planks} && {g}.inventory.inv[10][1] === 4", 5, "the planks in her inventory")
            press("e")
            chrome.wait_for(f"!{g}.screen", 5, "the screen closed")
            teacher.send(json.dumps({"type": "mode"}))
            teacher.close()
            # her Craft Bot's Garage (the engine's, from schemas.json) and code panel: the code as Python, BUILD reaching the server
            tab("garage")
            chrome.wait_for("['bot_name', 'dig', 'build', 'speed', 'colour'].every(w => document.getElementById('panelbody').textContent.includes(w))"
                            " && !!document.getElementById('gz-build')", 10, "her Craft Bot's garage")
            chrome.js("document.getElementById('gz-build').click()")
            chrome.wait_for("(window.__state.garageMsg || [''])[0].startsWith('Built!')", 10, "her Bot built by the server")
            press("c")
            chrome.wait_for("!document.getElementById('codepanel').hidden && document.getElementById('code-text').value.includes('dig: int = ')"
                            " && document.getElementById('code-text').value.includes('# MY CRAFT BOT as Python code')", 5, "her Bot as Python in the code panel")
            press("c")
            chrome.js("document.getElementById('panel').classList.remove('open')")
            # the touch controls: the stick walks, a phone's layout
            chrome.js("window.__app.setTouch('on')")
            chrome.wait_for("!document.getElementById('touchpad').hidden && document.getElementById('touchpad').classList.contains('craft') "
                            "&& document.querySelectorAll('#touchpad .tp-cmoves [data-btn]').length === 8", 5, "the touch controls for Craft Lab")
            chrome.js(open_way)
            time.sleep(0.3)
            a = chrome.js(f"[{p}.state.x, {p}.state.y]")
            chrome.js("{ const r = document.getElementById('tp-cstick').getBoundingClientRect();"
                      "document.getElementById('tp-cstick').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, pointerId: 7, "
                      "clientX: r.left + r.width / 2, clientY: r.top + 4})); }")
            time.sleep(1.2)
            chrome.js("document.getElementById('tp-cstick').dispatchEvent(new PointerEvent('pointerup', {bubbles: true, pointerId: 7}))")
            time.sleep(0.4)
            b = chrome.js(f"[{p}.state.x, {p}.state.y]")
            assert ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5 > 1, f"the stick didn't walk her: {a} {b}"
            chrome.call("Emulation.setDeviceMetricsOverride", width=844, height=390, deviceScaleFactor=2, mobile=True)
            time.sleep(1.5)
            chrome.screenshot(os.path.join(work, "craft_phone.png"))
            chrome.call("Emulation.clearDeviceMetricsOverride")
            chrome.js("window.__app.setTouch('off')")
            corr = chrome.js(f"{p}.corrections")
            print(f"    {corr} corrections in all")
            assert corr <= 6, corr
            no_errors()
        check("Craft Lab: a learner's page over a school's Wi-Fi (60 ms each way, 15 ms of jitter) walks with the keys (her "
              "player predicted, the server agreeing to the centimetre), jumps, digs a block and puts it down again, crafts "
              "planks in the inventory screen (a stack taken, one put in the grid, the planks made and put away), her Craft "
              "Bot's Garage and code panel (BUILD reaching the server), the touch controls (the stick walks her) and a "
              "phone's layout", craft_learner)
        for key, proc in servers.items():
            proc.close() if isinstance(proc, Learner) else stop(proc)

        def craft_current():  # (CHANGE 202) Craft Lab's atlas and tables (make_craft.py, from craft_art and craft_blocks)
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_craft.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("craft.json and tex/craft_atlas.png (Craft Lab's tables and atlas) match craft/'s files", craft_current)

        def lessons_current():
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_lessons.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("lessons.json matches the games' lesson files", lessons_current)

        def textures_current():
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_textures.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("tex/ (the app's textures and skies) is up to date with the games' texture generators", textures_current)

        def models_current():  # (CHANGE 144) the curved ultra kart and circuit (kart_models.py, kart_scenery.py);
            # (CHANGE 145) Robot Lab's ultra robots and arena (robot_models.py, arena_models.py)
            r = subprocess.run([sys.executable, os.path.join(HERE, "make_models.py"), "--check"], capture_output=True, text=True)
            assert r.returncode == 0, r.stdout + r.stderr
        check("models/ (Kart Lab's curved ultra kart and ultra circuit, Robot Lab's ultra robots and arena, Fight Lab's "
              "ultra fighters and hall) is up to date with kart/kart_models.py, kart/kart_scenery.py, robot_models.py, "
              "arena_models.py, fight_models.py and stage_models.py", models_current)

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
    except StopRun as e:
        print(f"Stopped after that check, as WEB_TEST_STOP_AFTER asked. Screenshot and test data: {work}")
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
