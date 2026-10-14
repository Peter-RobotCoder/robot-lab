# Club Coders Live: the browser window

The first step of the browser client (CHANGE 127, 13 October 2026): the teacher's live view of a class, served
by the class server's own Caddy at `https://play.clubcoders.co.uk/live/`. Nothing to install, so it runs on a
school laptop, a Chromebook or a phone, and through a school's filtering like any web page.

What it does now:

- logs in with the desk's teacher password (the one the app's Teacher screen takes), and stays connected to the
  desk (logging in again by itself if the Wi-Fi drops; the password is kept only in the page's memory);
  "Use a class server's code instead" is still there for a laptop test server;
- the TEACHER DESK (CHANGE 129, `desk.js`): everything the app's Teacher screen does. Learners (add, with a starter
  password or one made up; reset; remove, pressed twice; print login slips), groups (name, proposed time, game,
  learners), Launch on a lesson, LAUNCH LEARNERS' WINDOWS, Stop (pressed twice), This session (who is here,
  missions completed, a note each), Records (past sessions; Print makes the session summary and the learner
  cards, as the app's PDFs, through the browser's print box: "Save as PDF" keeps them), Watch a class, and
  changing the teacher password. Launching a Kart Lab group opens its live view by itself; the view's TEACHER DESK
  button goes back. The desk hands the page a teacher ticket for a class (CHANGE 128), so no class code is needed;
- draws a Kart Lab race from the server's binary snapshots (`wire.js` reads `engine/wire.py`'s frames), two
  snapshots behind the newest so it is smooth, on the track built from the server's own track data (`track.js`
  is `kart_track.py` ported line for line);
- the teacher's minute-to-minute controls: start, grid, pause, practice or race, the mission, the track, laps,
  computer karts, the teacher's kart, locked designs, the grand prix, save and restore;
- the Learners tab: who is here, their kart, lap, and what their window reports (fps, ping, stalls, graphics
  tier, whether their brain is driving), plus lap times;
- cameras: TV (follows the leader or a chosen kart; drag to orbit), chase, the whole track;
- three graphics tiers, the start of the ladder every engine shares: blocks (flat colours, nothing lit), low
  (lit, one shadow map, fog), high (PBR, soft shadows, bloom, FXAA); auto steps down a tier when the frame rate
  stays under 24. The Graphics tab shows the browser's WebGL and WebGPU state and the renderer: the numbers
  from a school laptop are the measurement nobody has published.

Not here yet: playing (a kart you drive: that needs `kart_sim.step()` in the browser for prediction), the learners'
side (login with a ticket, missions, garage, code, their brain in a Pyodide worker), Robot Lab and Fight Lab drawn,
and the Kart Lab teacher window's own tabs (AI cards, Outcomes, evidence ticks, restart server).

## Files

| File | What |
| --- | --- |
| `index.html`, `style.css` | the page: login card, overlays, the side panel |
| `app.js` | the connection and protocol, interpolation, the panel's tabs, the controls |
| `desk.js` | the teacher desk: the desk connection, its screen, the printed records and login slips |
| `lessons.json`, `make_lessons.py` | each game's lesson titles, aims, outcomes and missions for the printouts, made from the games' lesson files (run `make_lessons.py` after changing one; the test checks it) |
| `scene.js` | Babylon.js: the track mesh, grass, trees, karts, cameras, tiers |
| `track.js`, `wire.js` | the track maths and the snapshot format, ported from the Python |
| `vendor/babylon.js` | Babylon.js 9.28.0 (Apache-2.0), served from the VPS so a school need only reach one domain |
| `web_test.py` | the test: a laptop kart server, the page in headless Chrome or Edge over the DevTools protocol |

## Try it on a laptop

In the kart folder, start `1 Kart Lab server.bat` (or `python kart_server.py --cpu 3`). Then, in this folder,
`python -m http.server 8090` and open

    http://127.0.0.1:8090/index.html?host=ws://127.0.0.1:8782&code=TEACH99

Query options: `desk=ws://...` (a desk elsewhere), `game=kartlab` (watch it straight after logging in), `autoconnect=1`, `tier=blocks|low|high`, `auto=0` (no auto step-down), `cam=tv|chase|overview`
with `follow=<kart id>`, `panel=controls|learners|camera|graphics`, `version=1.9.2` (a class server wants the
release's number; on the VPS the page reads `/live/version`). Tab opens and closes the panel.

## Test

    shared-world-demo\.venv\Scripts\python club-coders\web\web_test.py

Fourteen checks: a wrong teacher password refused; the desk screen; learners added and a group made; Launch opening
the class view with the desk's ticket; snapshots, the drawing, the controls reaching the server, the tiers, the
Learners tab; a note, LAUNCH LEARNERS' WINDOWS, Stop and the printed record (kept as `records.pdf` in the test
folder, with screenshots); a reset, a removal, login slips; the teacher password changed; the class-code login;
lessons.json up to date.
It passes (and says so) on a computer without Chrome or Edge.
