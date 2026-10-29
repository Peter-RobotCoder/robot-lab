# City Lab

A small open city for the club (CHANGE 194): each learner is a fighter on foot who can take any car and drive it,
with robots on the pavements and jobs to do (deliveries, taxi runs, street races, a robot round-up, chips to find).
It is being built in steps, each one something to try on the laptop: see `../docs/plans/city-lab.md`.

## Where it has got to

Step 1 (23 October 2026): the city offline. Walk it, run, jump, punch, kick and block.
Step 2 (23 October 2026): cars. Parked cars to take (E beside one), Kart Lab's handling, the computer's traffic
driving on the left and turning at junctions, headlights and brake lights at dusk and night.
Step 3 (23 October 2026): robots and fighting. Robot Lab's robots patrol the pavements; close up they get cross,
wind up their weapons and zap you; punch and kick one down (it reboots); sparks where a hit lands, your health bar,
knocked down and up again.
Step 4 (23 October 2026): the jobs. Rings at the depot (deliveries), the taxi rank, the arcade (chips paid, the
robot round-up) and the street race line; the beam over your target and the arrow at the top that points to it;
chips to find; the computer's racers; cash, the job, the countdown, the minimap and the news.
Step 5 (29 October 2026): online on the laptop. A server, a teacher's window and learners' windows in the same
city: everyone sees everyone walk, drive and fight; your own person and car answer the keys at once (predicted, as
Kart Lab's kart is) and everything else is blended between the server's snapshots. A log-in screen (a new username
makes a profile), reconnecting when the server restarts, reopening when the server runs newer code. The teacher's
Enter starts a street race for everyone, G sends everyone to the depot, F mends the teacher's car, P pauses. A
person drives as their design's points say (speed, acceleration and grip), in any car they take.

## Run it

Double-click, in this folder (it uses Robot Lab's `.venv`):

| File | What |
| --- | --- |
| `1 City Lab server.bat` | the laptop test server (codes CLUB42 and TEACH99; keep its window open) |
| `2 City Lab teacher.bat` | the teacher's window (asks your name) |
| `3 City Lab learner.bat` | a learner's window: log in with any new username and password to make a profile |
| `4 City Lab offline.bat` | the city on this laptop, no server |

On foot: WASD or the arrows walk (W is away from the camera), **Shift** runs, **Space** jumps, **J** punches,
**K** kicks, **B** blocks (half a zap or a hit gets through), **E** gets into the car beside you.
Driving: **W** goes, **S** brakes (then reverses), **A** and **D** steer, **Shift** drifts, **B** is the handbrake, the
throttle let go and pressed again from a standstill drops the clutch, **E** gets out (under 10 km/h).
Jobs: walk into the **DEPOT**'s ring for a parcel (stop at the beam of light at the address; the arrow at the top
points the way); drive into the **TAXI RANK**'s ring for a passenger (every bump costs the tip); stop a car on the
**STREET RACE** line to open a race (12 seconds to the start, the computer's racers line up beside you, round the
bright rings and back to the line); pick up the green **chips** on the pavements and walk into the **ARCADE**'s ring
to be paid for them; walk in with none for a **ROUND-UP** (the robots go rogue: power them down).
Always: **R** goes back to the depot, **V** changes the view (on foot: behind, over the shoulder, from above; in a
car: chase, bonnet), the mouse wheel zooms, **N** day, dusk, night (offline: online the teacher's lesson says),
**H** hides the key list, **F11** full screen (**Esc** leaves it). A game pad works too.
The teacher: **Enter** starts a street race for everyone (a car each on the line, and the computer's racers),
**G** sends everyone back to the depot, **F** mends your own car, **P** pauses the city.

Command line: `city_client.py --offline --city harbour|village|metro --look woman|man|robin|human|robot --gfx
mesh|lines|basic|low|medium|high|ultra --traffic 6 --parked 12 --robots 6 --time day|dusk|night`. `--demo-drive`
starts in a car driving by itself, `--demo-fight` beside a robot, kicking it, `--demo-job delivery|race` on a job. `--demo --offscreen --after 5 --screenshot city.png` takes a picture of the
person running by themselves.
Online: `city_client.py --host ws://127.0.0.1:8783 --name Sam --password ...`, or `--teacher --name "Mr P"`;
`city_server.py --city harbour --traffic 6 --robots 6 --level medium --autostart 10` (a street race 10 s after the
first window joins). `CLUBCODERS_LAG=60,15` makes the connection behave like a school's Wi-Fi (60 ms each way, 15 ms
of jitter); `CITYLAB_PREDICT_LOG=1` prints each correction of the prediction and what it was about.

## How it is built

| File | What |
| --- | --- |
| `city_version.py` | the version, and the path to the engine and to the other three games (City Lab draws their cars, fighters and robots) |
| `city_map.py` | the cities, generated from a seed and sent to every window as JSON: blocks, buildings, trees, lamps, ramps, the four places, addresses, parking, chips; what is under a point and what a thing bumps into |
| `city_sim.py` | the step for a person, a car (Kart Lab's handling) and a robot, deterministic so a window can predict; the wire record; the design; `World` |
| `city_jobs.py` | deliveries, taxi runs, street races, the round-up, chips, stunt jumps |
| `cpu_brains.py` | the traffic, the robots, the racers |
| `city_server.py` | the class server (Kart Lab's shape): logins, the lesson, the teacher's keys, the computer's cars, robots and racers, binary snapshots 30 times a second |
| `city_teaching.py`, `city_missions.py`, `city_profiles.py` | the lessons (the engine's teaching layer): which builds, jobs and brains complete which missions; the learners' profiles. The lessons' words and the panels for them come in step 6 |
| `city_brain.py`, `brain_worker.py`, `brain_rules.py` | a learner's brain, `brain(me, city, others)`, run safely in its own process (step 6 teaches it) |
| `city_mods.py`, `ai_pipeline.py` | the mod files (drivers, the city, the rules) and AI requests (step 6) |
| `city_gfx.py` | the city drawn (one mesh a material), the people (Fight Lab's models), the cars (Kart Lab's), the robots and sparks (Robot Lab's), the cameras on foot and in a car, the health bar |
| `city_client.py` | the window: offline, it runs the world itself; online, it predicts your person or car and blends the rest |
| `city_test.py` | the tests: `quick` for the simulation, `server` with the server, `online` with two windows over pretend Wi-Fi, `window` with the window offline, nothing for everything |
