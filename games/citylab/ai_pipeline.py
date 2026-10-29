"""City Lab's AI pipeline: what is City Lab's own, on the engine's (engine/ai_pipeline.py): its folders and
files, and its words for the prompt to Claude. Every name the windows and the server use is the engine's.
    python ai_pipeline.py city Sam "..."    a request from a terminal
"""
import json
import os

import city_version  # noqa: F401  (puts the engine on the path)
from engine import ai_pipeline as _engine
from engine.ai_pipeline import *  # noqa: F401,F403
from engine.ai_pipeline import (AIChange, DATA, NEEDS_GAME, allowed_files, build_prompt, change_diff,  # noqa: F401
                                forget_user_mod_makers, history, maker_name, merge, name_user_mods,
                                open_in_editor, reapply, rollback, save_prompt, save_user_mod_makers, slug,
                                user_mod_keys, user_mod_makers)

HERE = os.path.dirname(os.path.abspath(__file__))


def driver_file_text(design, learner):
    """A mods/drivers file for a learner (their current design, in the same shape as the others)."""
    d = dict(design)
    lines = [f'"""{learner}\'s driver and car. Changed by AI requests that the teacher approves."""', "", "DRIVER = {"]
    for k, v in d.items():
        lines.append(f"    {json.dumps(k)}: {json.dumps(v).replace('true', 'True').replace('false', 'False')},")
    return "\n".join(lines + ["}", ""])


def _sim():
    import city_sim as sim
    return sim


def _rules_limits():
    import city_mods
    return city_mods.RULE_LIMITS


def _mod_files_text(sim, settings):
    return f"""- mods/drivers/*.py hold DRIVER = {{...}}: name (up to {sim.NAME_MAX} characters), colour [r, g, b] 0-255, body
  (the car's look only: one of {', '.join(sim.BODIES)}), look (the person: one of {', '.join(sim.LOOKS)}), and
  points {{"speed", "acceleration", "grip"}} (whole numbers {sim.STAT_MIN}-{sim.STAT_MAX}, total at most
  {sim.POINTS_TOTAL}).
- mods/city.py holds CITY = {{...}}: city (one of city_map.CITIES: harbour, village, metro), traffic (0-30 cars),
  robots (0-20) and cpu_level (easy, medium or expert: how the street racers drive).
- mods/rules.py holds RULES = {{...}}: the pay for each job and the bumps (on the server only; see
  city_mods.RULE_LIMITS for the ranges)."""


GAME_GUIDE = """HOW THE GAME IS BUILT (Python 3, Panda3D for the windows; the city itself is plain Python)
- city_map.py: the city as data, made from a seed (the streets, blocks, kerbs, ramps and places: the depot, the
  garage, the taxi rank, the arcade). city_sim.py: a person on foot, a car and a robot, each a pure deterministic
  step() every window runs too, to predict what it controls; and the World (getting in and out, bumps, punches,
  kicks, knockdowns). A change to how a person or car moves must stay deterministic (no random numbers, nothing
  read from outside the record, the input, the city and its stats).
- city_jobs.py: the jobs (deliveries, taxi runs, the street race, chips, the robot round-up) and their pay.
- cpu_brains.py: the computer's traffic, street racers and robots.
- city_server.py: the class server (logins, lessons, the teacher's controls, binary snapshots 30 times a second).
  city_teaching.py: missions and evidence. city_missions.py: lesson presets, missions, curriculum outcomes.
- city_client.py: the learner and teacher windows, which predict their own person or car (engine.predict) and
  blend everything else between snapshots (engine.interp). city_gfx.py: the city mesh, people, cars, robots,
  cameras, HUD and minimap; it borrows Kart Lab's, Fight Lab's and Robot Lab's drawing code.
- mods/: plain-data files (drivers, the city, rules) checked by city_mods.py.

RULES FOR A GAME CHANGE
- Keep everything that already works working. Change as little as the request needs.
- The game must still start. When you have finished, run the game's test with exactly this command (it is the
  only command you may run): .venv/Scripts/python city_test.py
  It checks every file compiles, the city, a person and a car behave, prediction agrees with the server, and
  the jobs pay. If anything fails, fix it and run the test again.
- Don't add new packages. Don't touch files outside the game folder (the other games' drawing code is theirs)."""


USER_MOD_GUIDE = """MAKE IT A SWITCHABLE USER MOD (the teacher switches it on and off in Controls)
- Add ONE entry to USER_MODS in city_sim.py: a short key (lower case letters and _), a name for the teacher's
  Controls (up to 20 characters) and one sentence saying what it does. Never put anyone's name in it.
- It is OFF by default, and while it's off the game must work exactly as it did before. Only do anything new
  while it's switched on: world.user_mods["<key>"] on the server (city_sim.World), and the window's copy of the
  switches for how it looks (city_gfx.py). A change to a person's or car's own step needs the switch on both ends
  the same way, or the window and the server disagree about where it is: prefer the world (server only) or the
  look (window only).
- The teacher can switch it at any time. World.set_user_mods() is called with the new switches.
- Nothing else is needed for the switch: the Controls tab lists every entry in USER_MODS, and the server and
  windows pass the switches on already."""


_engine.setup(_engine.Game(
    home=HERE, data=os.environ.get("CITYLAB_DATA") or os.path.join(HERE, "data"),
    protected={"ai_pipeline.py", "city_profiles.py", "city_brain.py", "brain_rules.py", "brain_worker.py",
               "city_version.py", "city_test.py"},
    skip_dirs={".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "brains",
               "data"},
    design_target="driver", design_dir="mods/drivers", design_var="DRIVER",
    world_target="city", world_file="mods/city.py",
    design_text=driver_file_text, sim=_sim, sim_file="city_sim.py", rules_limits=_rules_limits,
    mods_module="city_mods.py", mods_test="city_mods.py", showcase="city_client.py",
    intro="their city game (driving, jobs, robots and fighting)",
    needs_game_examples="a new job, a new kind of building, or new driving or fighting moves",
    mod_files_text=_mod_files_text, game_guide=GAME_GUIDE, user_mod_guide=USER_MOD_GUIDE))
DATA = _engine.DATA  # noqa: F811  (where the change history lives, for the windows)


if __name__ == "__main__":
    _engine.main()
