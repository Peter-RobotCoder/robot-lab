# Club Coders Live: the browser window

The teacher's desk and live view of a class in a browser (CHANGE 127, 13 October 2026; the desk CHANGE 129; every
game and every teacher tab CHANGE 130, 14 October 2026), served by the class server's own Caddy at
`https://play.clubcoders.co.uk/live/`. Nothing to install, so it runs on a school laptop, a Chromebook or a phone,
and through a school's filtering like any web page. Step one of the browser plan: the teacher can do everything
except play.

What it does now:

- logs in with the desk's teacher password (the one the app's Teacher screen takes), and stays connected to the
  desk (logging in again by itself if the Wi-Fi drops; the password is kept only in the page's memory);
  "Use a class server's code instead" is still there for a laptop test server;
- the TEACHER DESK (`desk.js`): everything the app's Teacher screen does. Learners (add, with a starter password or
  one made up; reset; remove, pressed twice; print login slips), groups (name, proposed time, game, learners),
  Launch on a lesson, LAUNCH LEARNERS' WINDOWS, Stop (pressed twice), This session (who is here, missions
  completed, a note each), Records (past sessions; Print makes the session summary and the learner cards, as the
  app's PDFs, through the browser's print box: "Save as PDF" keeps them), Watch a class, and changing the teacher
  password. Launching a group opens its live view by itself; the view's TEACHER DESK button goes back. The desk
  hands the page a teacher ticket for a class (CHANGE 128), so no class code is needed;
- draws all three games from their servers' snapshots, two behind the newest so it is smooth:
  - Kart Lab (`kart.js`, `scene.js`): binary snapshots (`wire.js` reads `engine/wire.py`'s frames), the track
    built from the server's own track data (`track.js` is `kart_track.py` ported line for line);
  - Robot Lab (`robot.js`): the arena from `lab_sim.py`'s constants (the cage or the no-cage gutter, the drop
    zone's lid, the floor flipper, the saws, the wall spikes, the corner squares, the user mods' pits, pads and
    ramps), the robots built from their designs with their weapons (wedge, spinner, drum, vertical disc, hammer,
    flame thrower and its jet, laser and its beam, the Resident Robots' chainsaw), hits as sparks, the 8-second
    countdown, the winner; several arenas, one watched at a time;
  - Fight Lab (`fight.js`): the hall and its rings (ropes or the glowing open edge, fire jets, spikes, ice), the
    fighters built from their designs on the game's 13-joint skeleton and posed by its own pose code
    (`fight_gfx.py`'s stance, walks, attacks, blocks, falls, ported line for line), energy blasts, hits, each ring's
    banner and timer;
- each game's own controls (Kart Lab: race, track, laps, grand prix; Robot Lab: practice or battle, restart, time,
  computer robots and their brain, real damage, the drop zone, arenas and who is where, winner stays on or a
  knockout; Fight Lab: practice or battle, rounds, sparring partners and bosses, rings and who is where, matches,
  tournaments), the missions and their saved settings, and Restart server / Reopen learners' windows (the page
  reconnects by itself after a restart);
- the teacher tabs every game shares (`teacher.js`, the engine's teaching layer): **Learners** (who is here and
  how each window is doing; a learner's mission, ticking their teacher-checked objectives, building their design,
  their password; building for everyone, the computer's robot or fighter and its brain, the teacher's own; the
  game's accounts), **Outcomes** (the outcomes grid, ticking objectives, the evidence CSV as a download, the missions
  editor: words, show or hide, add, remove, reset, show learners, the missions file down and back up),
  **AI cards** (every card, the line on the learners' cards, With Claude / Kept / Send back with a note, Copy for
  Claude, putting a kept change's mod file on the server), **Rules** (what learners can see and change, weapons or
  specials allowed, hazards, Resident Robots, user mods and what's in the vote, the limits) and **Warnings**;
- cameras per game, and three graphics tiers, the start of the ladder every engine shares (`base3d.js`): blocks
  (flat colours, nothing lit), low (lit, one shadow map, fog), high (PBR, soft shadows, bloom, FXAA); auto steps
  down a tier when the frame rate stays under 24. The Graphics tab shows the browser's WebGL and WebGPU state and
  the renderer.

What still needs the Club Coders app on the teacher's laptop: sending an AI card to Claude (Send, Keep, Undo) and
the Changes tab, because Claude edits the game's files on the laptop and the change stays there until "Make my
changes live". Fight Lab's woman, man and Robin bodies are skinned 3D models (about 12 MB each plus textures, with
Mixamo animations): the page draws them as the primitive human or robot in their colours, with their weapon, until
it loads the models themselves (that needs Babylon's glTF loader, a route for the files, and a decision on serving
the Mixamo animations).

Not here yet: playing (a kart you drive: `kart_sim.step()` in the browser for prediction), the learners' side
(login with a ticket, missions, garage, code, their brain in a Pyodide worker).

## Files

| File | What |
| --- | --- |
| `index.html`, `style.css` | the page: login card, overlays, the desk, the side panel |
| `app.js` | the connection, the messages every game sends, the snapshot clock, the panel, the graphics tab |
| `desk.js` | the teacher desk: the desk connection, its screen, the printed records and login slips |
| `teacher.js` | the teacher tabs every game shares |
| `kart.js`, `scene.js`, `track.js`, `wire.js` | Kart Lab: its messages and controls, the track and karts, the track maths, the binary snapshots |
| `robot.js` | Robot Lab: the arena, the robots, its controls |
| `fight.js` | Fight Lab: the rings, the fighters and their poses, its controls |
| `base3d.js` | what every scene shares: the engine, tiers, materials, labels, coordinate rules |
| `lessons.json`, `make_lessons.py` | each game's lesson titles, aims, outcomes and missions for the printouts, made from the games' lesson files (run `make_lessons.py` after changing one; the test checks it) |
| `vendor/babylon.js` | Babylon.js 9.28.0 (Apache-2.0), served from the VPS so a school need only reach one domain |
| `web_test.py` | the test: a desk and laptop servers for all three games, the page in headless Chrome or Edge |

## Try it on a laptop

Start a game's laptop server (`1 Kart Lab server.bat`, or `python lab_server.py` in shared-world-demo,
`python fight_server.py` in BeatEmUp). Then, in this folder, `python -m http.server 8090` and open

    http://127.0.0.1:8090/index.html?host=ws://127.0.0.1:8782&code=TEACH99

(Robot Lab 8780, Fight Lab 8781, Kart Lab 8782.) Query options: `desk=ws://...` (a desk elsewhere), `game=kartlab`
(watch it straight after logging in), `autoconnect=1`, `tier=blocks|low|high`, `auto=0` (no auto step-down),
`cam=tv|chase|overview` with `follow=<id>`, `panel=<tab>`, `version=1.9.5` (a class server wants the release's
number; on the VPS the page reads `/live/version`). Tab opens and closes the panel.

## Test

    shared-world-demo\.venv\Scripts\python club-coders\web\web_test.py

Eighteen checks. The desk: a wrong teacher password refused; the desk screen; learners added and a group made;
Launch opening the class view with the desk's ticket; a note, LAUNCH LEARNERS' WINDOWS, Stop and the printed
record (kept as `records.pdf` in the test folder); a reset, a removal, login slips; the teacher password changed.
Kart Lab: snapshots, the drawing, the controls, the tiers, the Learners tab, the class-code login. Robot Lab, with a
scripted learner: the arena and robots on every tier; the shared tabs (a tool and a hazard, an objective added and
ticked, missions out and back in, the evidence CSV, an AI card sent back, a learner's mission and robot rebuilt);
Restart server and the page reconnecting. Fight Lab: the rings and posed fighters, its controls. lessons.json up to
date. Screenshots of each game are kept in the test folder. It passes (and says so) on a computer without Chrome
or Edge.
