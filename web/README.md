# Club Coders Live: the browser window

The teacher's desk and live view of a class in a browser (CHANGE 127, 13 October 2026; the desk CHANGE 129; every
game and every teacher tab CHANGE 130, 14 October 2026; the app's graphics CHANGE 131), served by the class server's own Caddy at
`https://play.clubcoders.co.uk/live/`. Nothing to install, so it runs on a school laptop, a Chromebook or a phone,
and through a school's filtering like any web page. Step one of the browser plan: the teacher can do everything
except play.

What it does now:

- one login form (CHANGE 148): a learner's username, or `teacher` and the desk's teacher password (the app's), and
  stays connected to the desk (logging in again by itself if the Wi-Fi drops; the password is kept only in the page's memory). No class
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
- draws all three games from their servers' snapshots (City Lab too: below), two behind the newest so it is smooth:
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
    tiers and on mesh and lines (`fightmodels.js`: `fight_model.py`'s clips, frames, blending, cartwheel and
    dressing, ported), the primitive stand-in until a model is loaded and on blocks;
- (CHANGE 199) plays the story Missions, Mission 1 "Wake-Up Call" and Mission 2 "Lights Out", in 3D as the mission
  window (`wake_up_call.py`) plays them, in a class whose Missions server runs every learner's program (CHANGE 198:
  `missions_server.py`; the page never runs a mission itself). `missionscene.js` builds the valley as the window's
  Valley does (the map from the server, 2 m a square: the hills, the grass and paving squares, the power cell, the
  supply crate and its four tools, the rockfall, Brookfield's houses, street lamps and power supply with its blinking
  warning light, the BROOKFIELD sign, the skid marks) and Mission 2's hill road at night as its HillRoad (the road up
  to the radio mast, the lamp posts lit as they are repaired, each night's rockfalls, the fence, the fields; the key
  light a dim blue moon), in Robot Lab's lights and effects, and the robots through robot.js's RobotScene (TITAN or
  RAZORBACK holding the tool it picked up, a model a tool as the window's RobotModel). `missions.js` is the game: the
  first screen (F1 and F2 the missions, 1 and 2 the robots; the teacher's has WATCH THE CLASS), the HUD (`hud.js`'s
  MissionHud: energy, tool and night, lines, the three stars, the objectives, Mission 2's variables, RESET, GRAPHICS,
  HOME VIEW, what to do now, the log), the code panel (C: the Pseudo code tab, the Python beside each line and each
  near miss's hint from the server's `parse`, RUN or Ctrl+Enter, RESET, the phrasebook from the mission's dictionary;
  the Code tab), each run's events played back as the window plays them (its timings and easing, the rocks flying
  apart, the power cell lifted, a lamp coming on, the sparks and Robot Lab's sounds), the done card (the stars, the
  energy and lines, the Solar Panel unlocked) and the flat battery's banner; everyone else's robot on the same mission,
  dimmed, their name on a card over it, each of their runs played at the page's pace. The teacher's page lists the
  class top right and in its Class tab, where the mission is changed for everyone. Every tier (mesh and lines with the
  lamps' lines dimming and brightening, blocks to high, ultra with the window's smooth robots). The welcome carries
  each mission's map, rules, robots, tools and phrasebook (`missions_server.about`), so nothing of the missions'
  Python is copied here but their objectives' and stars' sums;
- (CHANGE 201) plays City Lab (`city.js`), as the City Lab window (`city/city_client.py`) plays it, in a City Lab class: the
  city from the server's welcome (`city_map.City`'s JSON) built as the window's `city_gfx.CityVisual` builds it, one mesh a
  material (the roads, their dashes, lane edges and zebra crossings, the pavements and kerbs, the buildings in their
  colours with their rows of windows, shop windows and the depot's and garage's doors, flat roofs with a parapet and a
  plant room or the houses' pitched roofs, the parks and gardens, the car parks' bays and stunt ramps, the yards'
  yellow lines, trees, lamp posts, the railing round the edge, the quay and the water, the four places' signs) and
  the jobs as its `JobsVisual` has them (the rings at the depot, the rank, the arcade and the race line, the beam over
  your target with its address, the chips spinning on the pavements, the race's checkpoints, the next one bright);
  the people as Fight Lab's fighters (`fighters.js`: the woman, the man and Robin as the app's skinned models, the
  built human and robot), the cars as Kart Lab's sports cars (`cars.js`), the robots as Robot Lab's (the scene is a
  RobotScene, as the Missions' is: patrolling, their weapons winding up as they get cross, red when rogue, dark when
  powered down, a tag when hurt), sparks where a punch, a kick or a zap lands; Kart Lab's lights and its day, dusk and
  night (the headlights, the street lamps glowing). The binary snapshots (`wire.js`'s CITY_FIELDS, one record for
  people, cars and robots) blended two behind; your own person, or the car you drive, predicted as the window predicts
  it (`city_sim.js`: `city_sim.py`'s person and car steps and the city's questions they ask, ported line for line;
  `city_sim_test.py` proves them the same to the last bit). The keys are the window's (on foot WASD walks, W away from
  the camera, Shift runs, Space jumps, J punches, K kicks, B blocks, E gets in; in a car Kart Lab's, E gets out; R back
  to the depot; V the view: behind, over the shoulder, from above, chase, bonnet; the wheel zooms), a game pad's, and a
  phone's touch controls (in a car Kart Lab's with GET OUT, on foot a stick and the moves). The HUD (`hud.js`'s CityHud):
  your job in words with the arrow to its target, the minimap, your cash and chips, health, km/h and damage, the hint,
  the race's countdown, KNOCKED DOWN, PAUSED. The teacher's page: the whole city from above (V; L watches each person
  in turn, the Camera tab too), the Controls tab (START A STREET RACE, EVERYONE TO THE DEPOT, PAUSE, MEND MY CAR, the
  city, the traffic, the robots, the parked cars, the racers and their level, the jobs, the time of day, damage, the
  teacher in the city or watching, designs locked) and the keys Enter, G, F and P as the window's. Every tier (mesh and
  lines: the city's edges in the line colour, a grid on the ground on lines; ultra: the sky with clouds, the haze, the
  glow, the detailed cars near the camera, the smooth fighters and robots, skid marks and sparks). Not yet: City Lab's
  Garage and code panel (its lessons, docs/plans/city-lab.md step 6, bring them to the window and the page together);
- (CHANGE 202) plays Craft Lab (`craft.js`), as the Craft Lab window (`craft/craft_client.py`) plays it, in a Craft Lab
  class: the island comes as the window's does (a `world_head` message, the blocks and their meta zipped in binary parts
  of kind 9, then `world`), inflated by the browser itself (DecompressionStream), its sky and torch light worked out as
  `craft_world.light_region` works them out and each chunk meshed as `craft_mesh.py` meshes it (`craft_mesh.js`: only the
  open faces, the corner shading, the light baked into each corner; the same bytes, `craft_sim_test.py` says so), the
  nearest first and a few milliseconds a frame, again where a block changes. Drawn by Craft Lab's own shader on every
  tier (the atlas's pixels, `tex/craft_atlas.png` from `make_craft.py`, nearest close to and mipmapped far off, times the
  corner shading and the light, the sky's part with the time of day, the torches' warm, fog into the sky's colour at
  the tier's view: mesh 72 m, lines 96, blocks 64, low 80, medium 112, high 144, ultra 224): the sun's shadows from
  medium, waving leaves, plants and water on high and ultra, the sky through the day, the sun and the moon, the stars,
  the clouds (low and up, two layers on ultra); mesh and lines black with every face's edges, or only the folds and
  where the block changes, fading into the dark. The players (dressed in the armour they wear: CHANGE 203), the
  creatures (Fluff, Bleep, Glitch, Rust Walker), the Craft Bots and things dropped as the window's `craft_models` boxes,
  legs and arms swinging, a red flash when hurt, names over the players and Bots, a Bot's words; the held item, the block
  you look at outlined, the crack as you dig, bits flying. Your player predicted with `craft_sim.js` (`craft_sim.py`'s
  step, to the last bit), the rest blended two snapshots behind (`wire.js`'s CRAFT_FIELDS). The keys are the window's
  (play.js's craft controls: WASD, the mouse once the game is clicked, Space, Shift, W twice to sprint, 1 to 9 and the
  wheel, the left button digs, the right places or uses, Q throws one, E the inventory, F flies in creative, V the view,
  B the Bot's brain, U and P; the teacher's T, M, G, K, N and F9), a game pad's (the right stick looks), and a phone's
  touch controls (touch.js: a stick, a finger dragged to look, DIG, PLACE, JUMP, SNEAK, RUN, FLY, BAG and DROP). The
  HUD and the screens (`craft_ui.js`: the hotbar, hearts, food, armour and breath, the news and the log; the inventory
  with its crafting grid and armour slots, the workbench, chest, smelter, Bot and creative screens, a click and a
  shift-click as the window's, sent as its `click` and `creative_take`). The Craft Bot's Garage and code panel are the
  page's own (`schemas.json`'s craftlab, from `craft_design.py`). The teacher's page flies free (V) or follows each
  learner (L, the Camera tab) and has the Controls tab (everyone to me, a Bot kit each, pause, saving the world, the time
  of day, survival or creative, creatures, hunger, keeping things, falls, blasts, the teacher in the world, designs
  locked, a new world from a seed); Craft Lab's sounds (`sfx/`'s c_ files: craft_sound.py's) and the day's and night's
  tunes;
- (CHANGE 187) Kart Lab on a phone or a tablet (`touch.js`): on-screen controls over the race, a steering slider
  (the thumb slid left or right, springing back), GO, BRAKE, DRIFT, your item (the button says what you hold), HANDBRAKE
  and RESET, VIEW and WATCH, and FULL SCREEN (a big button until the page is: the browser's bars gone and the phone
  sideways where it allows; an iPhone has no page full screen, so added to the home screen the page opens that way,
  `manifest.webmanifest`). Read by `play.js` as a game controller is. Settings: Touch controls Auto (a touchscreen
  whose main pointer is a finger), On, Off; `?touch=1`. A phone starts on the low tier. Every box over the game
  (the log, the stats, the standings, LAP, speed, the minimap, damage, tyres, the item) has a – that folds it to a
  pill, and the HUD button beside ≡ PANEL hides them all and brings them back, both kept (`hudmini.js`);
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
  - mesh (CHANGE 144, Kart Lab; CHANGE 145, Robot Lab; CHANGE 147, Fight Lab): black, every triangle's edges in one
    line colour, the lines behind hidden;
  - lines (CHANGE 144, Kart Lab; CHANGE 145, Robot Lab; CHANGE 147, Fight Lab): black, the outlines, folds and colour
    changes in the line colour, a ground grid (Kart Lab's every 10 m on the grass, Robot Lab's every 2 m on the
    floor's plates, none over the holes, Fight Lab's every 1 m on each ring's canvas and every 2 m on the hall's
    floor). Robot Lab's as its window's: each part that moves on its own has its own lines (the armour panels,
    the body, the beacon, the chain, the weapon, each wheel), the glowing parts' lines pulse as they glow, the cage's
    screens are their edges alone, the arena's name and the big screen's in the line colour, sparks in the line
    colour, debris as edges, no smoke or fire, no names on the decks. Fight Lab's as its window's: each joint of a
    built fighter its own lines, and on lines its outline (the round limbs and head have few folds: their back faces
    pushed out in the line colour, `base3d.js`'s `silhouette`); the woman, the man and Robin black with lines on a
    copy of their skinned vertices, so they bend with every move (`skinnedLines`), and their outline; the ropes' and
    an open edge's lines pulse as they glow, a fire jet a flame of lines, a blast a ball of lines, the names on the
    canvas, the screens and the fighters' backs in the line colour, sparks and shock rings in the line colour, debris
    as edges, no smoke, dust, fire or soft flash;
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

  - ultra (CHANGE 147, Fight Lab, `fightfx.js`): high's lights with a soft 4096 shadow, 16x anisotropy, a gentle
    bloom and sharpening on a 4x MSAA picture, and the window's smooth fighters and hall (`models/fight_ultra.json`,
    0.7 MB, and `models/stage_ultra.json`, 1.4 MB, from make_models.py: the window's `fight_models.py` and
    `stage_models.py`): each built fighter's pieces placed as `fight_models.layout` places them on the joints the
    poses move, a joint's pieces one mesh with a texel a role for roughness, metal and glow (13 meshes a fighter);
    each ring for its size as `stage_models.ring_layout` places its pieces (the canvas, the padded platform with the
    club's boards, the steps, the posts and ropes), the hall's floor and walkways, the stands with 1000 seats and 734
    fans (thin instances), the screens, the rig, walls and roof (hidden by the ring and all rings views), in place of
    high's platform, mat, posts, pads, ropes, floor, stands, crowd, screen boxes and truss (the markings, logo, open
    edge, jets, spikes and ice as high's); the hall's far parts in a faint haze. The woman, the man and Robin as on
    high. Fetched only on ultra; until both have loaded (or if they don't) ultra draws high's fighters and hall.

  Each game draws its own tiers (all three all seven since CHANGE 147, the Missions too since CHANGE 199, City Lab since CHANGE 201); a tier a game doesn't have would be drawn as
  its nearest (mesh and lines as blocks, ultra as high). Auto never steps into or out of mesh and lines. The line colour
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
  tab (a learner's Settings) has Auto and the game's tiers (the seven since CHANGE 147, with the line colours; picking one turns Auto off, as the windows' Graphics: Low
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
| `fight.js`, `fightfx.js` | Fight Lab: the rings and the hall, its controls; its effects, cameras and ultra tier (CHANGE 147: the window's fighters and hall from `models/fight_ultra.json` and `stage_ultra.json`, written by `make_models.py` from the window's `fight_models.py` and `stage_models.py`) |
| `fighters.js` | (CHANGE 201) Fight Lab's fighters, built and posed: the poses (`fight_gfx.py`'s, ported), the rim lines, and FighterParts, the methods Fight Lab's and City Lab's scenes share (moved out of `fight.js`, unchanged) |
| `cars.js` | (CHANGE 201) Kart Lab's karts and sports cars, built and drawn each frame, their lamps, headlights and smoke, the times of day: CarParts, the methods Kart Lab's and City Lab's scenes share (moved out of `scene.js`, unchanged) |
| `city.js`, `city_sim.js` | (CHANGE 201) City Lab: the game and its scene (the city from the server's JSON, the jobs, the people, cars and robots, the cameras, the Controls tab, the prediction); `city_sim.py`'s person and car steps and the city's questions, ported line for line |
| `missions.js`, `missionscene.js` | the Missions (CHANGE 199): the game (the first screen, the code panel, the runs from the Missions server played back, the others' robots, the done card, the teacher's Class tab) and its places (Mission 1's valley, Mission 2's hill road at night, the robots as Robot Lab's) |
| `fightmodels.js` | Fight Lab's detailed fighters (woman, man, Robin): the app's glTF models, fetched once per body and shape when one appears (from `models/fightlab/`: Caddy serves the release's `games/fightlab/models` there), posed and dressed as `fight_model.py` does it |
| `base3d.js` | what every scene shares: the engine, tiers and their pixel budgets, materials, labels, coordinate rules, texture coordinates in metres, merging what never moves |
| `pbr.js` | the app's lighting: simplepbr's shader as a Babylon ShaderMaterial, the key light's shadow, the sky's reflections, the tone curve |
| `tex/`, `make_textures.py` | the app's texture sets (512 x 512 JPEGs), each sky's reflections as simplepbr works them out (`env` for Robot Lab and Fight Lab, `sky` for Kart Lab: spherical harmonics in `manifest.json`, the blurred sky as a picture), simplepbr's BRDF table. Made with the games' Python (`shared-world-demo\.venv`): run `make_textures.py` after a texture generator or simplepbr changes; the test checks the version numbers |
| `lessons.json`, `make_lessons.py` | each game's lesson titles, aims, outcomes and missions for the printouts, made from the games' lesson files (run `make_lessons.py` after changing one; the test checks it) |
| `fonts/` | JetBrains Mono (OFL 1.1, `OFL.txt`), the code panel's font (CHANGE 138: the promo videos' code window, the Python highlighted as it is typed), served with the page so no font server is needed |
| `vendor/babylon.js` | Babylon.js 9.28.0 (Apache-2.0), served from the VPS so a school need only reach one domain |
| `vendor/babylon.glTF2FileLoader.min.js` | Babylon's glTF 2 loader, babylonjs-loaders 9.28.0 (Apache-2.0): loads Fight Lab's models |
| `web_test.py` | the test: a desk and laptop servers for all four games and the Missions, the page in headless Chrome or Edge |
| `craft.js`, `craft_sim.js`, `craft_mesh.js`, `craft_ui.js` | (CHANGE 202) Craft Lab: the game and its scene (the world from the server's parts, the chunks, the shader, the sky, the models, the prediction, the keys, the Controls tab); `craft_sim.py`'s step and the world's light, ported to the last bit; `craft_mesh.py`'s chunk meshes, byte for byte; the HUD and the screens |
| `craft.json`, `tex/craft_atlas.png`, `make_craft.py` | (CHANGE 202) Craft Lab's blocks and items and the atlas `craft_art.py` draws (run `make_craft.py` after craft_art, craft_blocks or craft_mesh changes; the test checks it) |
| `craft_sim_test.py`, `craft_sim_golden.json` | (CHANGE 202) `craft_sim.js` and `craft_mesh.js` against Craft Lab's own Python with node: the light, every chunk's meshes, the world's questions, hundreds of players' runs tick for tick to the last bit, compare, the prediction's corrections, the Garage's schema; the fingerprint for `craft_sim.SIM_VERSION` |
| `city_sim_test.py`, `city_sim_golden.json` | (CHANGE 201) `city_sim.js` against City Lab's own Python with node: the city's questions, thousands of people's walks and cars' drives tick for tick to the last bit, compare, the prediction's corrections; the fingerprint for `city_sim.SIM_VERSION` |

## Try it on a laptop

Start a game's laptop server (`1 Kart Lab server.bat`, or `python lab_server.py` in shared-world-demo,
`python fight_server.py` in BeatEmUp). Then, in this folder, `python -m http.server 8090` and open

    http://127.0.0.1:8090/index.html?host=ws://127.0.0.1:8782&code=TEACH99

(Robot Lab 8780, Fight Lab 8781, Kart Lab 8782, City Lab 8783 (`1 City Lab server.bat`: a learner logs in with `&code=CLUB42&name=amy`
and a password in the form); Craft Lab 8785 (`1 Craft Lab server.bat`, the same); the Missions 8784, `python missions_server.py` in shared-world-demo,
where a learner logs in with `&code=CLUB42&name=amy` and the teacher with `&code=TEACH99`.) Query options: `desk=ws://...` (a desk elsewhere), `game=kartlab`
(watch it straight after logging in), `autoconnect=1`, `tier=mesh|lines|blocks|low|medium|high|ultra`, `auto=0` (no Auto),
`cam=tv|chase|overview` with `follow=<id>`, `panel=<tab>`, `speed=8` (the Missions' runs played 8 times faster), `version=1.9.7` (a class server wants the release's
number; on the VPS the page reads `/live/version`), `models=<url>` (where Fight Lab's models are: by default
`models/fightlab/` beside the page, then `../games/fightlab/models/` or `../../BeatEmUp/models/` when the page is
served from higher up; `python -m http.server` in this folder can't reach them, so serve the ClubCodersAI folder
and open `/club-coders/web/index.html`, or the fighters stay stand-ins). Tab opens and closes the panel.

## Test

    shared-world-demo\.venv\Scripts\python club-coders\web\web_test.py

Fifty-eight checks. The desk: a wrong teacher password refused; the desk screen; learners added and a group made;
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
fighters on blocks to high (ultra's models never fetched there, the Graphics tab showing seven), the detailed model, its controls, the teacher's own garage (the woman's look); its line tiers (CHANGE 147: black, the rings', the hall's, the ropes' or open edge's and every fighter's lines, each joint's own, the detailed model's on its skin, the outlines and grids on lines only, the line colour at once); ultra (the window's fighters and hall from `models/fight_ultra.json` and `stage_ultra.json`, fetched then and not before: parts, rings, thin instances, no shadow from the flat or far, the haze on far parts alone, 13 meshes a fighter, soft 4096 shadows, the glow, no SSAO). The Missions (CHANGE 199), against a laptop Missions server: a learner's page
draws the valley (the power cell, the crate and its tools, the rockfall, the power supply, the sign) and the first
screen, chooses TITAN with 1, shows a near miss's hint (not corrected, RUN off), types Mission 1's five steps
(`wake_up_call_test.STEPS`, read from its file) with the Python beside each line, runs them to three stars (17 lines,
8 energy, the Solar Panel unlocked); another learner, a raw client, runs and his robot is drawn where his run left it,
dimmed, his name over it; every tier (mesh and lines black with the valley's, the robots' and the lights' own lines;
ultra's smooth robots); Mission 2 from F2, the hill road at night (the lamps dark and lit as night 1 has them, the
moon), `lights_out_test.SOLUTION` played to three stars (the nights and the variables in the HUD, every lamp lit at
the end); the teacher's page (WATCH THE CLASS, the class top right and in the Class tab, a learner's robot drawn, the
mission changed for everyone). City Lab (CHANGE 201), against a laptop City Lab server: the teacher's page (the city built,
its rings and chips, 16 cars as Kart Lab's, the teacher and a scripted window as fighters, six robots, the window's person
walking and the traffic driving; every tier, mesh and lines black with the city's, the cars' and the fighters' own lines;
night from the Controls tab, the headlights); a learner's page (her person walked with the keys and predicted, the server
agreeing to the centimetre; into a parked car, driven with the keys, the car predicted with few corrections, km/h in the
HUD; the touch controls for a car and, out of it, on foot). Craft Lab (CHANGE 202), against a laptop Craft Lab server on the
small island from seed 2026: the teacher's page (the island meshed chunk by chunk, the teacher and a window's learner as models,
him walking, L following him; every tier, mesh and lines black with the blocks' and the models' lines, blocks to ultra in
Craft Lab's shader with the clouds, the sun's shadows from medium and the waving leaves on high and ultra; night from
Controls, the stars); a learner's page over a pretend school Wi-Fi (engine/fault_relay.py, 60 ms each way and 15 ms of
jitter: walking with the keys, predicted, the server agreeing to the centimetre; a jump; a block dug and put down again;
planks crafted in the inventory screen from the creative box; her Craft Bot's Garage and code panel, BUILD reaching the
server; the touch controls' stick walking her; a phone's layout). lessons.json, schemas.json, craft.json,
tex/ and sfx/ up to date; `schema_test.py` passing. Screenshots of each game are kept in the test folder. It passes (and says so) on a computer without Chrome
or Edge.
