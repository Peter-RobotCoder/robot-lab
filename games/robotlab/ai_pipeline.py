"""Robot Lab's AI pipeline: what is Robot Lab's own, on the engine's (engine/ai_pipeline.py): its folders and
files, and its words for the prompt to Claude. Every name the windows and the server use is the engine's.
    python ai_pipeline.py robot Sam "..."    a request from a terminal
"""
import json
import os

import lab_version  # noqa: F401  (puts the engine on the path)
from engine import ai_pipeline as _engine
from engine.ai_pipeline import *  # noqa: F401,F403
from engine.ai_pipeline import (AIChange, DATA, NEEDS_GAME, allowed_files, build_prompt, change_diff,  # noqa: F401
                                forget_user_mod_makers, history, maker_name, merge, name_user_mods,
                                open_in_editor, reapply, rollback, save_prompt, save_user_mod_makers, slug,
                                user_mod_keys, user_mod_makers)

HERE = os.path.dirname(os.path.abspath(__file__))


def robot_file_text(design, learner):
    """A mods/robots file for a learner who doesn't have one yet (their current design)."""
    d = dict(design)
    d.setdefault("style", {"trim": [30, 30, 34], "lights": [255, 120, 40], "number": d.get("name", learner)[:8]})
    body = json.dumps(d, indent=4).replace("true", "True").replace("false", "False")
    return (f'"""{learner}\'s robot. Changed by AI requests that the teacher approves."""\n\n'
            f"ROBOT = {body}\n")


def _sim():
    import lab_sim as sim
    return sim


def _rules_limits():
    import rw_mods
    return rw_mods.RULE_LIMITS


def _mod_files_text(sim, settings):
    return f"""- mods/robots/*.py hold ROBOT = {{...}}: name, colour [r, g, b] 0-255, weapon (wedge, spinner, drum, hammer),
  points (speed, attack, armour, control: whole numbers {sim.STAT_MIN}-{sim.STAT_MAX}, total at most {sim.POINTS_TOTAL}),
  settings (percent):
{settings}
  style: trim [r, g, b], lights [r, g, b], number (text on the deck, up to 10 characters), and optionally
  model (one of {', '.join(sim.HOUSE_BY_NAME)}) to drive a Resident Robot.
- mods/arena.py holds ARENA = {{...}}: hazards (pit, floor_flipper, saws, spikes: True/False; house_robots: True,
  False or a list of names) and look (name up to 16 characters, wall_colour [r, g, b], crowd True/False)."""


GAME_GUIDE = """HOW THE GAME IS BUILT (Python 3, Panda3D with Bullet physics)
- lab_sim.py: all the physics, run by the server: robots built from designs (points, settings, weapons), weapon
  hits, the arena, hazards (drop zone, floor flipper, saws, wall spikes) and the Resident Robots (BLAZE, CRUSHER,
  RIPSAW, VORTEX). shapes() gives each weapon's sizes, and the graphics use the same numbers.
- lab_server.py: the class server (logins, lessons, the teacher's controls, sending the state 20 times a second).
  lab_teaching.py: missions and evidence. lab_missions.py: lesson presets, missions, curriculum outcomes.
- lab_client.py: the learner and teacher windows (garage, missions, AI card, teacher panels, code panel).
- rw_gfx.py: how the arena and robots look (RobotVisual draws each weapon; ArenaVisual draws the hazards).
  rw_fx.py sparks, smoke and flames; rw_sound.py sounds; rw_camera.py cameras; rw_mesh.py shapes.
- robot_wars.py: the single-player showcase (TITAN v RAZORBACK).
- mods/: plain-data files (robots, arena, rules) checked by rw_mods.py.
A new game feature usually needs the physics in lab_sim.py AND how it looks in rw_gfx.py (and a control in
lab_client.py / lab_server.py if the teacher or learner switches it). A new weapon needs: an entry in WEAPONS,
a shape in shapes(), its body in Robot.__init__, how it moves in Robot.tick, what it does in weapon_contact,
and its model in RobotVisual.

RULES FOR A GAME CHANGE
- Keep everything that already works working. Change as little as the request needs.
- The game must still start. When you have finished, run the game's test with exactly this command (it is the
  only command you may run): .venv/Scripts/python smoke_test.py
  It checks every file compiles, the server runs a full arena, and the showcase and both windows start. If
  anything fails, fix it and run the test again.
- Don't add new packages. Don't touch files outside the game folder."""


USER_MOD_GUIDE = """MAKE IT A SWITCHABLE USER MOD (the teacher switches it on and off in Controls)
- Add ONE entry to USER_MODS in lab_sim.py: a short key (lower case letters and _), a name for the teacher's
  Controls (up to 20 characters) and one sentence saying what it does. Never put anyone's name in it: the game
  puts the learner's first name in front by itself ("Sam's Spike pit").
- It is OFF by default, and while it's off the game must work exactly as it did before. Only do anything new
  while it's switched on: arena.user_mods["<key>"] in the physics (lab_sim.py; a robot can read
  self.arena.user_mods), and user_mods_on(user_mods)["<key>"] in ArenaVisual (rw_gfx.py) for how it looks.
- The teacher can switch it mid-round. Arena.set_user_mods() is called with the new switches: if your mod changes
  something already built (like the arena's edge in Arena.build_edge), rebuild it there. The windows redraw the
  arena by themselves when a mod is switched.
- Nothing else is needed for the switch: the teacher's Controls and everyone's User mods tab list every entry in
  USER_MODS, and the server and windows pass the switches on already."""


_engine.setup(_engine.Game(
    home=HERE, data=os.environ.get("ROBOTLAB_DATA", HERE),
    protected={"ai_pipeline.py", "lab_profiles.py", "robot_loader.py", "lab_brain.py", "brain_rules.py",
             "brain_worker.py", "lab_version.py", "smoke_test.py", "security_test.py"},
    skip_dirs={".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "brains"},
    design_target="robot", design_dir="mods/robots", design_var="ROBOT",
    world_target="arena", world_file="mods/arena.py",
    design_text=robot_file_text, sim=_sim, sim_file="lab_sim.py", rules_limits=_rules_limits,
    mods_module="rw_mods.py", mods_test="rw_mods.py", showcase="robot_wars.py",
    intro="their Robot Wars game", needs_game_examples="a new kind of weapon, a second weapon, or new game mechanics",
    mod_files_text=_mod_files_text, game_guide=GAME_GUIDE, user_mod_guide=USER_MOD_GUIDE))
DATA = _engine.DATA  # noqa: F811  (where the change history lives, for the windows)


if __name__ == "__main__":
    _engine.main()
