"""Fight Lab's AI pipeline: what is Fight Lab's own, on the engine's (engine/ai_pipeline.py): its folders and
files, and its words for the prompt to Claude. Every name the windows and the server use is the engine's.
    python ai_pipeline.py fighter Sam "..."    a request from a terminal
"""
import json
import os

import fight_version  # noqa: F401  (puts the engine on the path)
from engine import ai_pipeline as _engine
from engine.ai_pipeline import *  # noqa: F401,F403
from engine.ai_pipeline import (AIChange, DATA, NEEDS_GAME, allowed_files, build_prompt, change_diff,  # noqa: F401
                                forget_user_mod_makers, history, maker_name, merge, name_user_mods,
                                open_in_editor, reapply, rollback, save_prompt, save_user_mod_makers, slug,
                                user_mod_keys, user_mod_makers)

HERE = os.path.dirname(os.path.abspath(__file__))


def fighter_file_text(design, learner):
    """A mods/fighters file for a learner (their current design, in the same shape as the other fighters)."""
    d = dict(design)
    d.setdefault("style", {"trim": [30, 30, 34], "lights": [255, 120, 40], "number": d.get("name", learner)[:8]})
    lines = [f'"""{learner}\'s fighter. Changed by AI requests that the teacher approves."""', "", "FIGHTER = {"]
    for k, v in d.items():
        lines.append(f"    {json.dumps(k)}: {json.dumps(v).replace('true', 'True').replace('false', 'False')},")
    return "\n".join(lines + ["}", ""])


def _sim():
    import fight_sim as sim
    return sim


def _rules_limits():
    import fight_mods
    return fight_mods.RULE_LIMITS


def _mod_files_text(sim, settings):
    return f"""- mods/fighters/*.py hold FIGHTER = {{...}}: name, body ({', '.join(sim.BODIES)}), colour [r, g, b] 0-255,
  special ({', '.join(sim.SPECIALS)}), points (power, speed, defence, stamina: whole numbers {sim.STAT_MIN}-{sim.STAT_MAX},
  total at most {sim.POINTS_TOTAL}), settings (percent):
{settings}
  combo: a list of {sim.COMBO_MIN} to {sim.COMBO_MAX} moves from {', '.join(sim.COMBO_MOVES)};
  style: trim [r, g, b], lights [r, g, b] (a robot's eyes), skin [r, g, b] (a human's skin), number (text on
  the chest, up to 10 characters), and optionally model (one of {', '.join(sim.BOSS_BY_NAME)}) to play as a boss.
  The detailed 3D bodies ("woman", "man") also have look: outfit ({', '.join(sim.OUTFITS)}), hair (woman:
  {', '.join(sim.HAIR_STYLES['woman'])}; man: {', '.join(sim.HAIR_STYLES['man'])}), hair_colour [r, g, b], shape
  ({', '.join(sim.SHAPES)}), height ({sim.HEIGHT_MIN}-{sim.HEIGHT_MAX}) and win (how they celebrate: {', '.join(sim.WINS)});
  their colour is their clothes' main colour. Robin (body "robin", the detailed robot) has look shape, height and
  win only; its style trim, lights and number are its trim plating, glowing lights and chest number.
  fighting_style ({', '.join(sim.STYLES)}; left out = kickboxer) changes what the attack buttons do (fight_sim
  STYLE_MOVES); an armed style also needs weapon ({'; '.join(f"{s}: {', '.join(sim.weapons_for(s))}"
  for s in sim.STYLES if sim.weapons_for(s))}).
- mods/stage.py holds STAGE = {{...}}: hazards (ring_out, electric_ropes, fire_jets, slippery: True/False) and look
  (name up to 16 characters, floor_colour [r, g, b], rope_colour [r, g, b], crowd True/False)."""


GAME_GUIDE = """HOW THE GAME IS BUILT (Python 3, Panda3D for the windows; the fighting itself is plain Python)
- fight_sim.py: all the fighting, run by the server: fighters built from designs (points, settings, special, combo),
  MOVES (each move's timing, damage, reach, height), hits, blocks, combos, juggles, the rings, ring-outs, hazards
  (electric ropes, fire jets, slippery ice) and rounds. BOSSES are the big computer fighters.
- fight_server.py: the class server (logins, lessons, the teacher's controls, rings and matches, the tournament,
  sending the state 20 times a second). fight_teaching.py: missions and evidence. fight_missions.py: lesson
  presets, missions, curriculum outcomes. cpu_brains.py: the computer fighters' levels.
- fight_client.py: the learner and teacher windows (garage, missions, AI card, teacher panels, code panel).
- fight_gfx.py: how the stage and fighters look (FighterVisual poses every move; StageVisual draws the rings and
  hazards). fight_model.py: the detailed 3D fighters (models/*.gltf, made in Blender by art/build_fighters.py; new
  outfits or hairstyles need Blender, so they are a job for the teacher, not a code change). fight_fx.py hit sparks
  and flashes, fight_sound.py sounds, fight_camera.py cameras.
- beat_em_up.py: the single-player showcase (BLAZE v KAITO).
- mods/: plain-data files (fighters, stage, rules) checked by fight_mods.py.
A new move usually needs an entry in MOVES and how it starts in Ring.start_action (fight_sim.py), and its pose in
FighterVisual (fight_gfx.py), plus a key in fight_client.py / beat_em_up.py if a player presses it.

RULES FOR A GAME CHANGE
- Keep everything that already works working. Change as little as the request needs.
- The game must still start. When you have finished, run the game's test with exactly this command (it is the
  only command you may run): .venv/Scripts/python smoke_test.py
  It checks every file compiles, the server runs full rings, and the showcase and both windows start. If
  anything fails, fix it and run the test again.
- Don't add new packages. Don't touch files outside the game folder."""


USER_MOD_GUIDE = """MAKE IT A SWITCHABLE USER MOD (the teacher switches it on and off in Controls)
- Add ONE entry to USER_MODS in fight_sim.py: a short key (lower case letters and _), a name for the teacher's
  Controls (up to 20 characters) and one sentence saying what it does. Never put anyone's name in it.
- It is OFF by default, and while it's off the game must work exactly as it did before. Only do anything new
  while it's switched on: stage.user_mods["<key>"] in the fighting (fight_sim.py; a ring reads self.stage.user_mods,
  a fighter self.ring.stage.user_mods), and self.user_mods["<key>"] in StageVisual (fight_gfx.py) for how it looks.
- The teacher can switch it mid-match. Stage.set_user_mods() is called with the new switches: if your mod changes
  something already built, rebuild it there. The windows redraw the stage by themselves when a mod is switched.
- Nothing else is needed for the switch: the Controls tab lists every entry in USER_MODS, and the server and
  windows pass the switches on already."""


_engine.setup(_engine.Game(
    home=HERE, data=os.environ.get("FIGHTLAB_DATA", HERE),
    protected={"ai_pipeline.py", "fight_profiles.py", "fight_brain.py", "brain_rules.py", "brain_worker.py",
             "fight_version.py", "smoke_test.py", "security_test.py"},
    skip_dirs={".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "brains",
             "models", "art"},  # (models and art: the 3D fighters, rebuilt in Blender, never changed by an AI request)
    design_target="fighter", design_dir="mods/fighters", design_var="FIGHTER",
    world_target="stage", world_file="mods/stage.py",
    design_text=fighter_file_text, sim=_sim, sim_file="fight_sim.py", rules_limits=_rules_limits,
    mods_module="fight_mods.py", mods_test="fight_mods.py", showcase="beat_em_up.py",
    intro="their beat 'em up game", needs_game_examples="a new move, a new special, or new game mechanics",
    mod_files_text=_mod_files_text, game_guide=GAME_GUIDE, user_mod_guide=USER_MOD_GUIDE))
DATA = _engine.DATA  # noqa: F811  (where the change history lives, for the windows)


if __name__ == "__main__":
    _engine.main()
