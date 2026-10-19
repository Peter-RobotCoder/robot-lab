"""Kart Lab's AI pipeline: what is Kart Lab's own, on the engine's (engine/ai_pipeline.py): its folders and
files, and its words for the prompt to Claude. Every name the windows and the server use is the engine's.
    python ai_pipeline.py kart Sam "..."    a request from a terminal
"""
import json
import os

import kart_version  # noqa: F401  (puts the engine on the path)
from engine import ai_pipeline as _engine
from engine.ai_pipeline import *  # noqa: F401,F403
from engine.ai_pipeline import (AIChange, DATA, NEEDS_GAME, allowed_files, build_prompt, change_diff,  # noqa: F401
                                forget_user_mod_makers, history, maker_name, merge, name_user_mods,
                                open_in_editor, reapply, rollback, save_prompt, save_user_mod_makers, slug,
                                user_mod_keys, user_mod_makers)

HERE = os.path.dirname(os.path.abspath(__file__))


def kart_file_text(design, learner):
    """A mods/karts file for a learner (their current design, in the same shape as the other karts)."""
    d = dict(design)
    lines = [f'"""{learner}\'s kart. Changed by AI requests that the teacher approves."""', "", "KART = {"]
    for k, v in d.items():
        lines.append(f"    {json.dumps(k)}: {json.dumps(v).replace('true', 'True').replace('false', 'False')},")
    return "\n".join(lines + ["}", ""])


def _sim():
    import kart_sim as sim
    return sim


def _rules_limits():
    import kart_mods
    return kart_mods.RULE_LIMITS


def _mod_files_text(sim, settings):
    return f"""- mods/karts/*.py hold KART = {{...}}: name (up to 12 characters), colour [r, g, b] 0-255, body (its look only: one
  of {', '.join(sim.BODIES)}), and the three points speed, acceleration and grip (whole numbers
  {sim.STAT_MIN}-{sim.STAT_MAX}, total at most {sim.POINTS_TOTAL}).
- mods/track.py holds TRACK = {{...}}: track (one of the tracks in kart_track.TRACKS: club, oval, straight), laps
  (1-9), name (what the track is called, up to 16 characters) and cpu_level (easy, medium or expert).
- mods/rules.py holds RULES = {{...}}: laps, cpu_karts, countdown_seconds, bump_distance, bump_slowdown (the
  race's rules, on the server only; see kart_mods.RULE_LIMITS for the ranges)."""


GAME_GUIDE = """HOW THE GAME IS BUILT (Python 3, Panda3D for the windows; the racing itself is plain Python)
- kart_sim.py: the kart (a hand-written arcade step: speed, steering, slide, drift charge and boost, barriers, dash
  pads, oil) and the race (countdown, gates, laps, places, bumps, results). step() is pure and deterministic, and
  every window runs it too, to predict its own kart: a change to how a kart moves must stay deterministic (no
  random numbers, nothing read from outside the kart's state, the input, the track and its stats).
- kart_track.py: the tracks as data (TRACKS): a smooth loop through a few points, a width, dash pads and oil.
- kart_server.py: the class server (logins, lessons, the teacher's controls, the race, binary snapshots 30 times
  a second). kart_teaching.py: missions and evidence. kart_missions.py: lesson presets, missions, curriculum
  outcomes. cpu_brains.py: the computer drivers' levels.
- kart_client.py: the learner and teacher windows (garage, missions, AI card, teacher panels, code panel), which
  predict their own kart (engine.predict) and blend the others between snapshots (engine.interp).
- kart_gfx.py: the track mesh, the karts, cameras, HUD and minimap. kart_sound.py sounds.
- mods/: plain-data files (karts, the track, rules) checked by kart_mods.py.

RULES FOR A GAME CHANGE
- Keep everything that already works working. Change as little as the request needs.
- The game must still start. When you have finished, run the game's test with exactly this command (it is the
  only command you may run): .venv/Scripts/python kart_test.py
  It checks every file compiles, the track and the kart behave, prediction agrees with the server, the server
  runs a race for two windows, and the window draws. If anything fails, fix it and run the test again.
- Don't add new packages. Don't touch files outside the game folder."""


USER_MOD_GUIDE = """MAKE IT A SWITCHABLE USER MOD (the teacher switches it on and off in Controls)
- Add ONE entry to USER_MODS in kart_sim.py: a short key (lower case letters and _), a name for the teacher's
  Controls (up to 20 characters) and one sentence saying what it does. Never put anyone's name in it.
- It is OFF by default, and while it's off the game must work exactly as it did before. Only do anything new
  while it's switched on: race.user_mods["<key>"] on the server (kart_sim.Race), and the window's copy of the
  switches for how it looks (kart_gfx.py). A change to the kart's own step() needs the switch on both ends the
  same way, or the window and the server disagree about where the kart is: prefer the race (server only) or the
  look (window only).
- The teacher can switch it mid-race. Race.set_user_mods() is called with the new switches.
- Nothing else is needed for the switch: the Controls tab lists every entry in USER_MODS, and the server and
  windows pass the switches on already."""


_engine.setup(_engine.Game(
    home=HERE, data=os.environ.get("KARTLAB_DATA") or os.path.join(HERE, "data"),
    protected={"ai_pipeline.py", "kart_profiles.py", "kart_brain.py", "brain_rules.py", "brain_worker.py",
               "kart_version.py", "kart_test.py", "smoke_test.py", "security_test.py"},
    skip_dirs={".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "brains",
               "data"},
    design_target="kart", design_dir="mods/karts", design_var="KART",
    world_target="track", world_file="mods/track.py",
    design_text=kart_file_text, sim=_sim, sim_file="kart_sim.py", rules_limits=_rules_limits,
    mods_module="kart_mods.py", mods_test="kart_mods.py", showcase="kart_client.py",
    intro="their kart racing game", needs_game_examples="a new item, a new track feature, or new race mechanics",
    mod_files_text=_mod_files_text, game_guide=GAME_GUIDE, user_mod_guide=USER_MOD_GUIDE))
DATA = _engine.DATA  # noqa: F811  (where the change history lives, for the windows)


if __name__ == "__main__":
    _engine.main()
