# Kart Lab

A Mario Kart style racer for the club: four learners and the teacher against computer karts, on the class server
or offline on one laptop, with the learners' Python brains driving if they want. Built 11 to 12 October 2026 on
the engine's new netcode (`../NETCODE.md`).

## Run it

Double-click, in this folder (they use Robot Lab's `.venv`):

| File | What |
| --- | --- |
| `1 Kart Lab server.bat` | the laptop test server on port 8782 (codes CLUB42 and TEACH99) |
| `2 Kart Lab teacher.bat` | the teacher's window: **Enter** starts the race, **G** puts everyone on the grid, **T** changes the track |
| `3 Kart Lab learner.bat` | a learner's window (asks for a name) |
| `4 Kart Lab offline race.bat` | a race on this laptop against five computer karts, no server |
| `5 Check the game.bat` | the tests (`kart_test.py`) |

Keys: arrows or WASD drive, **Shift** (or Space) drifts (hold it through a bend, let go for a boost), **R** puts
you back on the track, **V** changes the camera, **Tab** opens your kart's design sheet (100 points between top
speed, acceleration and grip; the teacher's race controls are on the same panel), **U** uploads
`brains/my_brain.py` to drive your kart, **P** switches that autopilot on and off, the **Full screen** button (top
right) fills the screen and **Esc** comes back out of it (it never closes the window). Sound: the engine note follows
your speed, tyres squeal in a drift, a whoosh for a boost, beeps for the countdown (`--mute` for
none). Lap times show as you cross the line; offline, the best lap on each track is kept on this computer.

Command line: `kart_client.py --offline --cpu 5 --level expert --track oval --stats 50,25,25 --brain brains/demo_brain.py`;
`kart_server.py --track club --cpu 3 --level medium --laps 3 --autostart 5`. Tracks: `club` (the Club Circuit,
372 m with a hill), `oval`, `straight` (for netcode tests). `CLUBCODERS_LAG=60,15,0.02` before a window
pretends the network is a school's Wi-Fi.

## How it is built

| File | What |
| --- | --- |
| `kart_track.py` | the tracks as data: a smooth loop through a few points, a width, dash pads and oil; where any point is along and across the track; 8 gates a lap |
| `kart_sim.py` | the kart (a hand-written arcade step: speed, steering, slide, drift charge and boost, barriers, pads, oil) and the race (countdown, gates, laps, places, bumps, results). The step is pure and deterministic, so a window runs it to predict its own kart |
| `kart_server.py` | 60 Hz race, inputs from each window numbered and queued (`engine.predict.ServerInputQueue`), binary snapshots 30 times a second with that window's last input applied (`engine.wire`), JSON for everything else |
| `kart_client.py` | the window: predicts its own kart and reconciles with the server's snapshots (`engine.predict`), draws the others between snapshots (`engine.interp`), offline mode runs the race itself |
| `kart_gfx.py` | the track mesh, kart models, chase and TV cameras, the HUD and minimap |
| `kart_brain.py`, `brain_worker.py`, `brain_rules.py` | a learner's `brain(me, track, rivals)` in its own process, asked 20 times a second without ever holding the race up |
| `cpu_brains.py` | the computer drivers: easy, medium, expert (expert drifts) |
| `brains/demo_brain.py`, `brains/README.md` | the learners' starting brain and the brain API |
| `kart_test.py` | track, physics, prediction through 83 ms of pretend delay, the server with two windows, the window offline and online |

The design sheet is 100 points between speed, acceleration and grip (10 to 60 each), as Robot Lab's robots:
`--stats` for now; a garage comes with the lessons.

## The teaching layer (12 October 2026)

Kart Lab has the same lessons, missions and panel as Robot Lab and Fight Lab, on the engine's framework:

| File | What |
| --- | --- |
| `kart_missions.py` | Robot Lab's five lessons re-worded for karts: the same learning outcomes (VAR, DATA, ... EVAL), mission ids (1a to 5d), tools, guide, AI card rules; the teacher edits the text in the Outcomes tab |
| `kart_teaching.py` | which builds, laps, brains and reflections complete which objectives (`engine.teaching`) |
| `kart_profiles.py`, `kart_mods.py`, `mods/` | learners' accounts (scrypt), the karts as files (`mods/karts/<name>.py`), the track and rules files |
| `ai_pipeline.py` | AI cards: a kart, the track, the rules or the game, through the engine's pipeline |
| `kart_hud.py` + the panel in `kart_client.py` | the login screen; learner tabs Mission, Garage (the kart as variables, with APPLY CODE), AI card, My card, Mods, Settings; teacher tabs Controls, User mods, Races (a league of races), Learners, Accounts, Outcomes, AI cards, Changes, Limits, Warnings, My kart, Settings |
| `smoke_test.py`, `security_test.py` | the same checks Fight Lab has, for the kart |

Practice mode keeps the track open (the lesson's default); race mode is the teacher's START RACE. The server's
data (profiles, evidence, AI requests, the saved lesson) lives in `data/` here, or `KARTLAB_DATA`.

## What is not here yet

A kart preview in the garage, items beyond dash pads and oil, more proper tracks (`../GENRES.md`, Race Lab).
