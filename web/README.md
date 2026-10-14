# Club Coders Live: the browser window

The first step of the browser client (CHANGE 127, 13 October 2026): the teacher's live view of a class, served
by the class server's own Caddy at `https://play.clubcoders.co.uk/live/`. Nothing to install, so it runs on a
school laptop, a Chromebook or a phone, and through a school's filtering like any web page.

What it does now:

- logs in with the desk's teacher password (the one the app's Teacher screen takes): the desk lists the classes
  this server runs and hands the page a teacher ticket for the one picked (CHANGE 128), so no class code is ever
  needed; "Use a class server's code instead" is still there for a laptop test server;
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
side (login with a ticket, missions, garage, code, their brain in a Pyodide worker), Robot Lab and Fight Lab.

## Files

| File | What |
| --- | --- |
| `index.html`, `style.css` | the page: login card, overlays, the side panel |
| `app.js` | the connection and protocol, interpolation, the panel's tabs, the controls |
| `scene.js` | Babylon.js: the track mesh, grass, trees, karts, cameras, tiers |
| `track.js`, `wire.js` | the track maths and the snapshot format, ported from the Python |
| `vendor/babylon.js` | Babylon.js 9.28.0 (Apache-2.0), served from the VPS so a school need only reach one domain |
| `web_test.py` | the test: a laptop kart server, the page in headless Chrome or Edge over the DevTools protocol |

## Try it on a laptop

In the kart folder, start `1 Kart Lab server.bat` (or `python kart_server.py --cpu 3`). Then, in this folder,
`python -m http.server 8090` and open

    http://127.0.0.1:8090/index.html?host=ws://127.0.0.1:8782&code=TEACH99

Query options: `desk=ws://...` (a desk elsewhere), `game=kartlab`, `autoconnect=1`, `tier=blocks|low|high`, `auto=0` (no auto step-down), `cam=tv|chase|overview`
with `follow=<kart id>`, `panel=controls|learners|camera|graphics`, `version=1.9.2` (a class server wants the
release's number; on the VPS the page reads `/live/version`). Tab opens and closes the panel.

## Test

    shared-world-demo\.venv\Scripts\python club-coders\web\web_test.py

Eight checks: a wrong teacher password refused, the desk login and its ticket, snapshots, the drawing, the
controls reaching the server, the tiers, the Learners tab, and the class-code login.
It passes (and says so) on a computer without Chrome or Edge.
