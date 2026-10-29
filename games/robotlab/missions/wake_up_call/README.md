# Robot Lab Mission 1: Wake-Up Call (3D)

The reviewed 2D prototype (branch `prototype/wake-up-call`, `prototypes/wake-up-call/`, commit `bc99d59`) in Robot
Lab's 3D, as its own single-player window. The plan: `docs/plans/wake-up-call-3d.md`.

## Play it locally

No server, no login and nothing online. From `shared-world-demo`:

- **Pete's laptop (Windows):** double-click `18 Mission 1 Wake-Up Call.bat`, or in Git Bash:

      cd ~/Documents/Projects/ClubCodersAI/shared-world-demo
      .venv/Scripts/python wake_up_call.py

- **Linux (a worker):** `.venv/bin/python wake_up_call.py`

Choose TITAN or RAZORBACK (or press 1 or 2), then press **C** for the code panel. Type one instruction per line in
the **Pseudo code** tab (the Python appears beside each line; the **Code** tab shows the whole program), then press
**RUN** or **Ctrl+Enter**. **V** changes the view (the valley, behind the robot, from above), the mouse wheel zooms,
**R** restarts, **Esc** closes the panel (or quits).

Options: `--robot titan|razorback` (skip the choice), `--gfx mesh|lines|basic|low|medium|high|ultra`,
`--window 1600x900`, `--no-sound`, `--progress <file>`.

Finishing unlocks the **Solar Panel** for Mission 2, kept as the prototype keeps it
(`{"parts": ["solar_panel"], "missions": {"wake_up_call": {...}}}`) in `%APPDATA%\RobotLab\missions_progress.json`
(`~/RobotLab/` on Linux). Delete that file to lock it again.

A route that earns all three stars:

    move forward 3
    turn right
    move forward 1
    pick up power cell
    turn left
    move forward 2
    turn right
    move forward 3
    pick up spinner
    turn right
    move forward 3
    turn left
    move forward 2
    use spinner
    move forward 6
    turn right
    repair

## Files

- `dictionary.json`: the prototype's dictionary, unchanged: the source of truth for the pseudo code.
- `prototype/`: the prototype's interpreter (`cc_pseudo.js`), mission (`cc_game.js`) and tests (`tests.js`), as they
  are in its page. Not used by the game: `wake_up_call_test.py` runs them in V8 beside the Python port and requires
  the same results. `sync_prototype.py <prototype folder>` copies them again (`--check` compares).
- In `shared-world-demo/`: `wake_up_call.py` (the 3D window), `mission_pseudo.py` (the interpreter, ported line for
  line), `mission_wake_up.py` (the mission and the saved progress, ported line for line), `wake_up_call_test.py`.

## Tests

    .venv/Scripts/python wake_up_call_test.py      (Linux: .venv/bin/python)

The parity checks need `pip install mini-racer` in the venv (test-only; the game doesn't use it). Without it they
say "skipped".
