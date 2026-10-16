# Club Coders Live: the browser window

The teacher's desk and live view of a class in a browser (CHANGE 127, 13 October 2026; the desk CHANGE 129; every
game and every teacher tab CHANGE 130, 14 October 2026; the app's graphics CHANGE 131), served by the class server's own Caddy at
`https://play.clubcoders.co.uk/live/`. Nothing to install, so it runs on a school laptop, a Chromebook or a phone,
and through a school's filtering like any web page. Step one of the browser plan: the teacher can do everything
except play.

What it does now:

- logs in with the desk's teacher password (the one the app's Teacher screen takes), and stays connected to the
  desk (logging in again by itself if the Wi-Fi drops; the password is kept only in the page's memory). No class
  codes (CHANGE 141): a learner logs in with their username and waits in THE LOBBY until the teacher adds them to a
  game (only a laptop test server's address, ?host=&code=, still takes a code, for the tests). The login card
  scrolls on a short screen;
- the TEACHER DESK (`desk.js`): everything the app's Teacher screen does. Learners (add, with a starter password or
  one made up; reset; remove, pressed twice; print login slips), groups (name, proposed time, game, learners),
  Launch on a lesson, LAUNCH LEARNERS' WINDOWS, Stop (pressed twice), This session (who is here, missions
  completed, a note each; Back to lobby takes a learner out of the game, and a name from the lobby or the class
  adds them: their game opens at once; editing the live group does the same), Records (past sessions; Print makes the session summary and the learner cards, as the
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
    banner and timer; the woman, the man and Robin with the app's own skinned models and Mixamo moves on the lit
    tiers (`fightmodels.js`: `fight_model.py`'s clips, frames, blending, cartwheel and dressing, ported), the
    primitive stand-in until a model is loaded and on blocks;
- each game's own controls (Kart Lab: race, track, laps, grand prix; Robot Lab: practice or battle, restart, time,
  computer robots (up to four, CHANGE 140: each the teacher's to set up in Learners, in every arena or one) and their brain, real damage, the drop zone, arenas and who is where (CHANGE 142: a row
  for every robot, the teacher's, each learner's and each computer robot's, its name renamed there and its arena;
  Save settings keeps who is where for the mission), winner stays on or a
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
- the Garage and the code panel (CHANGE 135, `garage.js` and `schema.js`), as the game windows have them: the
  Garage's tables drawn from the game's design schema as `engine/garage.py` draws them (STRING VARIABLES with their
  boxes and choice buttons, "chosen by the teacher this mission", the line under a row; VARIABLE LISTS with the
  colour blocks and the custom block a colour typed in the code goes to; INTEGER VARIABLES: the points with -5 - + +5,
  their bars and the points used, the settings' sliders, fixed when the teacher's range is one value), Fight Lab's
  detailed look and combo editor, the stats readout, only what the mission's tools show, the five saved designs and
  BUILD, which sends what the window sends (`code` true when the design holds a value changed in the code). The
  code panel (C, or the Garage's Code button; the window's `code_viewed` goes when it opens) shows the design as
  Python with line numbers; APPLY CODE (or Ctrl+Enter) reads it as the window does, never running it, with the
  window's messages (a mistake: its line marked and selected; a value past the teacher's limits: "Unable to
  compile"; "Applied, but: ..."), RESET CODE and BUILD. The teacher's Learner view builds a learner's design, every
  learner's, the computer's and the teacher's own in the same garage (every row, with a "learner sees" box for each
  tool). `schema.js` is Python 3.12's tokenizer and grammar and `ast.literal_eval`, ported, so the code is read with
  Python's own error messages and line numbers; `schema_test.py` compares it with the windows' own Python;
- cameras per game, and the app's graphics tiers (CHANGE 131, `base3d.js` and `pbr.js`), lit the way the app lights
  them: simplepbr's shader (the one every game's window draws with) ported to the browser, with each game's own
  lights, exposure and sky from its gfx module, and the app's own texture sets and skies (`tex/`):
  - mesh (CHANGE 144, Kart Lab; CHANGE 145, Robot Lab): black, every triangle's edges in one line colour, the lines
    behind hidden;
  - lines (CHANGE 144, Kart Lab; CHANGE 145, Robot Lab): black, the outlines, folds and colour changes in the line
    colour, a ground grid (Kart Lab's every 10 m on the grass, Robot Lab's every 2 m on the floor's plates, none over
    the holes). Robot Lab's as its window's: each part that moves on its own has its own lines (the armour panels,
    the body, the beacon, the chain, the weapon, each wheel), the glowing parts' lines pulse as they glow, the cage's
    screens are their edges alone, the arena's name and the big screen's in the line colour, sparks in the line
    colour, debris as edges, no smoke or fire, no names on the decks;
  - blocks: flat colours, nothing lit (the floor every machine can draw, and the fallback without WebGL 2);
  - low: the app's lighting and the textures' colours, no shadows or reflections;
  - medium: + the normal maps, the sky's reflections, a 1024 shadow map;
  - high: + the occlusion maps, a 2048 shadow map, sharper textures at a slant;
  - ultra (CHANGE 144, Kart Lab, `kartfx.js`): + a soft 4096 shadow over 64 m, SSAO, bloom, 8x MSAA, the window's
    haze (exponential, mixed in before the tone curve), a sky dome with clouds, the world reflected in the paint under
    a clear coat, skid marks, sparks, the curved kart (`models/kart_ultra.json`) and the window's ultra circuit
    (`models/kart_scenery.json`, 4.7 MB, both from make_models.py): asphalt with a rubbered racing line, patches,
    edge lines, the chequered start and grid boxes, profiled kerbs, gravel traps, tyre walls, armco, the pit wall,
    striped grass with tufts, flowers, bushes, rocks and a pond, pines and broadleaf trees, the grandstand and its
    crowd, the pits and race control, the start gantry, marshals' posts, advertising boards, TV towers, and fields,
    hedges, farms and hills to the horizon. Each built-in track's parts are one mesh per material and its shapes
    (about 4,500 trees, tufts, tyre stacks, seats and fans) thin instances, one per shape part: about 60 meshes for
    350,000 triangles; the flat and the far cast no shadow (as the window's), and the reflection cube watches only
    the parts. Fetched only on ultra; until it has loaded (or for a track it hasn't) ultra draws the road, grass,
    hills and woods it drew before. On this laptop's Iris Xe at 1364 x 745 (headless Chrome, frame time with a forced
    finish, four karts on the grid) ultra takes 17 to 22 ms a frame with the circuit against 15 to 17 with the old
    land and woods (high: 5.6 and 6.7 ms, as before): about 2 ms of that is the 350,000 triangles drawn three times
    (the picture, the shadow map, the shading in corners), the rest pixels.
  - ultra (CHANGE 145, Robot Lab, `robotfx.js`): high's lights with a soft 4096 shadow over the arena's 26 m, 16x
    anisotropy, a gentle bloom and sharpening on a 4x MSAA picture, and the window's smooth robots and arena
    (`models/robot_ultra.json`, 1 MB, and `models/arena_ultra.json`, 4.8 MB, from make_models.py: the window's
    `robot_models.py` and `arena_models.py`): each robot's pieces placed as the window's `robot_models.layout` places
    them on the nodes the other tiers move (the body, the armour panels on their hinges, the beacon, the weapon, the
    chain, each wheel), a node's pieces one mesh with a texel a role for roughness, metal and glow (about 11 meshes a
    robot); the steel floor, its scars, the cage, the towers, the rig and roof, the stands with 560 seats and 464
    fans (thin instances), the big screen and the hall, in place of high's floor, walls, towers, rig, stands, crowd
    and screen box (the markings, hazards and user mods' items as high's); the hall in a faint haze. Fetched only on
    ultra; until both have loaded (or if they don't) ultra draws high's robots and arena. No SSAO (5 ms more a frame
    here) and no reflection probe: ultra costs about what high does.

  Each game draws its own tiers (Kart Lab and Robot Lab all seven, Fight Lab blocks to high); a tier it doesn't have
  is drawn as its nearest (mesh and lines as blocks, ultra as high). Auto never steps into or out of mesh and lines. The line colour
  (green, amber, cyan, white, magenta or any) is kept on the computer and in a learner's profile (`line_colour`).

  Each tier draws at most so many pixels (1.0 for mesh, lines and blocks, 1.1, 1.6, 2.4 and 3.7 million), however fine the screen: a 4K laptop
  at 300% would otherwise draw 7.7 million a frame where the app's window draws 0.9 million. The canvas's own
  multisampling smooths the edges; the tone curve is applied as each pixel is drawn, so there is no pass after the
  scene. Scenery that never moves is drawn as one mesh per material. Auto (CHANGE 139, `base3d.js`'s `AutoTier`) steps
  down one tier after three seconds under 28 frames a second and back up one after 25 seconds with headroom (with
  vsync the frame time sits at the screen's rate, so: 45 a second or more, no more than one frame over 25 ms a
  second), never past the class maximum or one above the best tier this computer has run cleanly; a tier stepped
  down from is held off for 10 minutes, twice as long each time it fails again (up to a day). The page remembers
  the tier, Auto and what Auto learnt on that computer (first visit: medium, high on a graphics card). The Graphics
  tab (a learner's Settings) has Auto and the four tiers (picking one turns Auto off, as the windows' Graphics: Low
  does), then every part of a tier to fine-tune (shadows off/512/1024/2048, normal maps, occlusion maps, the sky's
  reflections, anisotropic filtering, the pixels drawn, from 0.6 million to as fine as the screen; picking a tier
  sets them all back to its own), the canvas's multisampling (read as the page opens) and the frame rate box; and
  the browser's WebGL and WebGPU state, the renderer, how many pixels are drawn and how many meshes.
- the teacher's **class maximum** (CHANGE 139, the teacher's Graphics tab): blocks, low, medium, high or no limit,
  sent as the lesson's `gfx_max` (the windows' names: `basic` for blocks), kept by each class server between
  sessions (`gfx_max_saved.json`). A learner's page can't choose above it, part by part too, Auto never steps past
  it, and a page above it drops to it at once (back to the learner's own choice when it is lifted). The game windows
  obey it too (`engine/gfx_tiers.py`): a window opens at most at it, and one already open turns its shadow map,
  MSAA and LOD down to the maximum's at once (simplepbr's shaders are made as the window opens, so the rest waits
  for its next start); its monitor never steps up past it. The teacher's own view and window aren't held to it.

Sending an AI card to Claude (Check and send with the whole prompt, Send to Claude, Keep, Undo, sending again with
more allowed) and the Changes tab (each kept change as a mod: its lines, switched off and on, merged into the game,
removed) work as the windows' (CHANGE 136) when **Claude for the browser** is running on a computer of the
teacher's that has the project folders and Claude Code (`helper/claude_helper.py`, `Claude for the browser.bat`):
it logs in to the desk as the teacher, the page's requests reach it through the desk, Claude runs there on that
computer's own Claude login, and the change is tested and kept there, where Make my changes live finds a code
change. The page passes kept mods on to the class server as the window does (`mods_update`, `mod_makers`,
`card_status`). One card at a time goes to Claude (two at once would each undo the other's files), so Undo and
switching a mod waits until Claude is done. Without it the AI cards tab says how to start it and keeps the manual
buttons (With Claude, Kept, Send back, Copy for Claude, putting a kept mod file on the server). Still only in the
app: Try it on this laptop (it starts game servers on the teacher's own laptop).

The Garage differs from the windows' in small ways: no turning picture of the robot beside its title (Robot Lab's
preview), the name kept as it is typed (the window keeps it at Enter or BUILD: the same design is sent), and Enter
makes a new line in the code (Ctrl+Enter applies). What `schema.js` can't read exactly is in its header (`\N{NAME}`
escapes; code nested more than about 1,500 deep).

## Files

| File | What |
| --- | --- |
| `index.html`, `style.css` | the page: login card, overlays, the desk, the side panel |
| `app.js` | the connection, the messages every game sends, the snapshot clock, the panel, the graphics tab |
| `desk.js` | the teacher desk: the desk connection, its screen, the printed records and login slips |
| `teacher.js` | the teacher tabs every game shares (the AI cards and Changes tabs talk to Claude for the browser through the desk) |
| `learner.js` | the learner's tabs: Mission, Garage, AI card, My card, Mods |
| `garage.js` | the Garage (the design's variables as `engine/garage.py` draws them, the window's own sections, the stats readout, the saved designs, BUILD) and the code panel (the design as Python, APPLY CODE, RESET CODE), for a learner, the teacher's own design and the Learner view |
| `schema.js` | the design schema in the browser (`engine/schema.py`, ported): the code written (`codeLines`) and read back (`parseCode`: Python 3.12's tokenizer, grammar and `literal_eval`, never run), `applyValues`, `applyCode` (the windows' APPLY CODE), the limits' checks, each game's design check, `garageTables`, the stats readouts |
| `schemas.json`, `make_schemas.py` | each game's design schema, limits and the constants its rules, garage and stats readout use, made from the games' own files (run `make_schemas.py` with the games' Python after a game's schema changes; the test checks it, and fails when a schema function's source changes until `schema.js` has been looked at) |
| `schema_test.py` | `schema.js` against the windows' own Python (their code_ctx, outside_limits, apply_code and update_stats_text, run without a window): thousands of designs and code texts, broken in every way; needs Node, says so and passes without it |
| `kart.js`, `scene.js`, `track.js`, `wire.js` | Kart Lab: its messages and controls, the track and karts, the track maths, the binary snapshots |
| `kartfx.js`, `models/`, `make_models.py` | Kart Lab's ultra tier (CHANGE 144): the sky, the after-effects, skid marks, sparks, and the curved kart and the circuit the window draws (`kart/kart_models.py` and `kart/kart_scenery.py`, pure Python, written to `models/` by `make_models.py`: run it after either changes; the test checks it) |
| `robot.js`, `robotfx.js` | Robot Lab: the arena, the robots, its controls; its effects, cameras and ultra tier (CHANGE 145: the window's robots and arena from `models/robot_ultra.json` and `arena_ultra.json`, written by `make_models.py` from the window's `robot_models.py` and `arena_models.py`) |
| `fight.js` | Fight Lab: the rings, the fighters and their poses, its controls |
| `fightmodels.js` | Fight Lab's detailed fighters (woman, man, Robin): the app's glTF models, fetched once per body and shape when one appears (from `models/fightlab/`: Caddy serves the release's `games/fightlab/models` there), posed and dressed as `fight_model.py` does it |
| `base3d.js` | what every scene shares: the engine, tiers and their pixel budgets, materials, labels, coordinate rules, texture coordinates in metres, merging what never moves |
| `pbr.js` | the app's lighting: simplepbr's shader as a Babylon ShaderMaterial, the key light's shadow, the sky's reflections, the tone curve |
| `tex/`, `make_textures.py` | the app's texture sets (512 x 512 JPEGs), each sky's reflections as simplepbr works them out (`env` for Robot Lab and Fight Lab, `sky` for Kart Lab: spherical harmonics in `manifest.json`, the blurred sky as a picture), simplepbr's BRDF table. Made with the games' Python (`shared-world-demo\.venv`): run `make_textures.py` after a texture generator or simplepbr changes; the test checks the version numbers |
| `lessons.json`, `make_lessons.py` | each game's lesson titles, aims, outcomes and missions for the printouts, made from the games' lesson files (run `make_lessons.py` after changing one; the test checks it) |
| `fonts/` | JetBrains Mono (OFL 1.1, `OFL.txt`), the code panel's font (CHANGE 138: the promo videos' code window, the Python highlighted as it is typed), served with the page so no font server is needed |
| `vendor/babylon.js` | Babylon.js 9.28.0 (Apache-2.0), served from the VPS so a school need only reach one domain |
| `vendor/babylon.glTF2FileLoader.min.js` | Babylon's glTF 2 loader, babylonjs-loaders 9.28.0 (Apache-2.0): loads Fight Lab's models |
| `web_test.py` | the test: a desk and laptop servers for all three games, the page in headless Chrome or Edge |

## Try it on a laptop

Start a game's laptop server (`1 Kart Lab server.bat`, or `python lab_server.py` in shared-world-demo,
`python fight_server.py` in BeatEmUp). Then, in this folder, `python -m http.server 8090` and open

    http://127.0.0.1:8090/index.html?host=ws://127.0.0.1:8782&code=TEACH99

(Robot Lab 8780, Fight Lab 8781, Kart Lab 8782.) Query options: `desk=ws://...` (a desk elsewhere), `game=kartlab`
(watch it straight after logging in), `autoconnect=1`, `tier=mesh|lines|blocks|low|medium|high|ultra`, `auto=0` (no Auto),
`cam=tv|chase|overview` with `follow=<id>`, `panel=<tab>`, `version=1.9.7` (a class server wants the release's
number; on the VPS the page reads `/live/version`), `models=<url>` (where Fight Lab's models are: by default
`models/fightlab/` beside the page, then `../games/fightlab/models/` or `../../BeatEmUp/models/` when the page is
served from higher up; `python -m http.server` in this folder can't reach them, so serve the ClubCodersAI folder
and open `/club-coders/web/index.html`, or the fighters stay stand-ins). Tab opens and closes the panel.

## Test

    shared-world-demo\.venv\Scripts\python club-coders\web\web_test.py

Twenty-five checks. The desk: a wrong teacher password refused; the desk screen; learners added and a group made;
Launch opening the class view with the desk's ticket; a learner's own page (her own password, waiting, the game
opening by itself; her Garage drawn from the schema, her code panel: APPLY CODE changing a value, a mistake shown
on its line, BUILD reaching the server sent as code); a note, LAUNCH LEARNERS' WINDOWS, Stop and the printed
record (kept as `records.pdf` in the test folder); a reset, a removal, login slips; the teacher password changed.
Kart Lab: snapshots, the drawing, the controls, the four tiers (each with the app's lighting, every picture loaded, no mesh left holding a thrown-away material, the pixel budget kept, the ultra circuit never fetched), the line tiers, ultra (its effects and the window's circuit: parts, thin instances, no shadow from the flat or far), the teacher's class maximum holding the learner's page (and Auto's steps, fed simulated frame rates), the Learners tab, the class-code login. Robot Lab, with a
scripted learner: the arena and robots on blocks to high (ultra's models never fetched there) and the Graphics tab's
seven tiers; the line tiers (CHANGE 145: black, the arena's, the screens' and every robot's lines, each moving part's
own, the floor grid on lines only, the line colour at once); ultra (the window's robots and arena from `models/`,
fetched then: parts, thin instances, the flat and far casting no shadow, the haze on the far parts alone, a few
meshes a robot, soft 4096 shadows, the glow, no SSAO); the shared tabs (a tool and a hazard, an objective added and
ticked, missions out and back in, the evidence CSV, an AI card sent back, a learner's mission and robot rebuilt);
the teacher's own garage (a weapon chosen); computer robot 2 renamed and put in arena 2 from the Learners tab (the
snapshot has it there alone); the Controls tab's Arenas rows (computer robot 2, amy's robot and the teacher's renamed
and put in an arena, a name amy changes showing in her row, Save settings keeping who is where); Restart server and
the page reconnecting. Fight Lab: the rings and posed
fighters on its four tiers (lines drawn as blocks, ultra as high, the Graphics tab showing four), the detailed model, its controls, the teacher's own garage (the woman's look). lessons.json, schemas.json,
tex/ and sfx/ up to date; `schema_test.py` passing. Screenshots of each game are kept in the test folder. It passes (and says so) on a computer without Chrome
or Edge.
