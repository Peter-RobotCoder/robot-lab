# Robot Lab Mission 2: Lights Out (prototype)

The second Story Mission (Jarvis's pedagogy research, 2026-10-22): **if / else** with the robot's sensors, and
**variables**. Same window, interpreter and rules style as Mission 1 (Wake-Up Call); Mission 1 is unchanged.

## Play it locally

No server, no login and nothing online. From `shared-world-demo`:

- **Pete's laptop (Windows):** double-click `19 Mission 2 Lights Out.bat`, or open Missions from the Club Coders
  app's first screen and press **F2** (or the MISSION 2 button), or in Git Bash:

      .venv/Scripts/python wake_up_call.py --mission lights_out

- **Linux (a worker):** `.venv/bin/python wake_up_call.py --mission lights_out`

Choose TITAN or RAZORBACK (1 or 2), press **C**, type the program, press **RUN** or **Ctrl+Enter**. Every run plays
**night 1, then 2, then 3**, each from the bottom of the road with a full battery: the rocks and the dark lamps are
in different places each night, so a fixed route fails. The HUD shows the night and the variables live.

## The story

Night has fallen over Brookfield. A storm has brought rocks down on the hill road to the radio mast and put some
of its lamps out. The robot (holding the front spinner from Mission 1) clears the rocks, repairs the dark lamps
(they stand on the bank on its left as it drives up the road) and, facing the mast, reports how many it repaired.

Energy: 30 each night. A square 1, the spinner 2, a repair 3 (even of a working lamp). Turning, sensors and
variables are free. The **Solar Panel** from Mission 1 (if `missions_progress.json` has it) gives 1 energy back
for every 5 squares. Stars: finish; 5 or more energy left every night; 15 or fewer lines.

## New pseudo code (on top of Mission 1's, minus pick up)

    if path blocked          if path clear          if rockfall in front          if lamp dark
    if energy less than 5    if lamps equals 3      (more than, less than, equals)
    else
    end                      (closes a repeat, an if or an else)
    set lamps to 0           add 1 to lamps         subtract 1 from count
    report lamps

Variables: `lamps`, `count`, `total`, `rocks` (a fixed list, so the did-you-mean hints work); `energy` can be read
but not changed. The Python way works too: `lamps = 0`, `lamps = lamps + 1`, `lamps += 1`,
`if robot.energy < 5:`, `if lamp_dark():`, `else:`, `print(lamps)`.

A program that earns all three stars (15 lines):

    set lamps to 0
    repeat 13 times
      if path blocked
        use spinner
      else
        move forward 1
      end
      if lamp dark
        turn left
        repair
        turn right
        add 1 to lamps
      end
    end
    report lamps

## Files

- `dictionary.json`: Mission 2's words. It `extends` `../wake_up_call/dictionary.json` and adds only if / else,
  variables and report (`mission_pseudo.extend`).
- `replay_mission.json`: 129 recorded missions (`replay_mission.py --mission lights_out --record`).
- In `shared-world-demo/`: `mission_lights_out.py` (the rules: the map, the three nights, the stars),
  `lights_out_test.py`, `replay_mission.py` (from jarvis/game-tests 3b3b293, extended to Mission 2); the window is
  `wake_up_call.py` (its `HillRoad` scene).

## Tests

    .venv/bin/python lights_out_test.py                        (Windows: .venv/Scripts/python)
    .venv/bin/python replay_mission.py --mission lights_out --window [all]
