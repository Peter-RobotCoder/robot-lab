"""Craft Lab's AI pipeline (CHANGE 200): what is Craft Lab's own, on the engine's (engine/ai_pipeline.py): its folders
and files, and its words for the prompt to Claude. Every name the windows and the server use is the engine's.
    python ai_pipeline.py craft Sam "..."    a request from a terminal
"""
import json
import os

import craft_version  # noqa: F401  (puts the engine on the path)
from engine import ai_pipeline as _engine
from engine.ai_pipeline import *  # noqa: F401,F403
from engine.ai_pipeline import (AIChange, DATA, NEEDS_GAME, allowed_files, build_prompt, change_diff,  # noqa: F401
                                forget_user_mod_makers, history, maker_name, merge, name_user_mods,
                                open_in_editor, reapply, rollback, save_prompt, save_user_mod_makers, slug,
                                user_mod_keys, user_mod_makers)

HERE = os.path.dirname(os.path.abspath(__file__))


def bot_file_text(design, learner):
    """A mods/bots file for a learner (their Craft Bot's design, in the same shape as the others)."""
    d = dict(design)
    lines = [f'"""{learner}\'s Craft Bot. Changed by AI requests that the teacher approves."""', "", "BOT = {"]
    for k, v in d.items():
        lines.append(f"    {json.dumps(k)}: {json.dumps(v).replace('true', 'True').replace('false', 'False')},")
    return "\n".join(lines + ["}", ""])


def _sim():
    import craft_design as sim
    return sim


def _rules_limits():
    import craft_mods
    return craft_mods.RULE_LIMITS


def _mod_files_text(sim, settings):
    return f"""- mods/bots/*.py hold BOT = {{...}}: name (up to {sim.NAME_MAX} characters), colour [r, g, b] 0-255, and
  points {{"dig", "build", "speed"}} (whole numbers {sim.STAT_MIN}-{sim.STAT_MAX}, total at most {sim.POINTS_TOTAL}).
- mods/blocks.py holds BLOCKS = [...]: new blocks, each {{"key", "name", "colour" [r, g, b], "hard" (seconds by hand,
  0.1-10), "light" (0-15), "tool" (pick, axe, shovel or None)}} (craft_mods.check_block says what is allowed).
- mods/recipes.py holds RECIPES = [...]: new recipes, as craft_items.RECIPES writes them ("makes", "count", and a
  "pattern" of letters with a "key", or "takes", a list).
- mods/world.py holds WORLD = {{...}}: seed, size (small, medium, large), mode (survival or creative), mobs (True or
  False), day_length (seconds, 120-3600).
- mods/rules.py holds RULES = {{...}}: keep_items, blasts, hunger, falls_hurt (True or False)."""


GAME_GUIDE = """HOW THE GAME IS BUILT (Python 3, Panda3D for the windows; the world itself is numpy arrays and plain Python)
- craft_blocks.py: every block and item (names, textures, hardness, tools, light, drops, food, fuel, smelting).
  craft_art.py draws every texture with code. craft_items.py: inventories, recipes, crafting.
- craft_world.py: the world (generated from a seed: heights, biomes, caves, ores, trees, water), its light and
  saving. craft_sim.py: a player's and a creature's movement, a pure deterministic step every window runs too, to
  predict its own player (no random numbers, nothing read from outside the record, the input and the world).
- craft_game.py: the rules (digging, placing, using blocks, health and food, smelters, crops, water, blasts).
  craft_mobs.py: the creatures. craft_bot.py: the Craft Bots that learners' brains drive.
- craft_server.py: the class server (logins, lessons, the teacher's controls, binary snapshots 30 times a second).
  craft_teaching.py: missions and evidence. craft_missions.py: lessons, missions, curriculum outcomes.
- craft_client.py: the windows. craft_gfx.py, craft_mesh.py, craft_models.py, craft_ui.py: the drawing and the HUD.
- mods/: plain-data files (bots, blocks, recipes, the world, the rules) checked by craft_mods.py.

RULES FOR A GAME CHANGE
- Keep everything that already works working. Change as little as the request needs.
- The game must still start. When you have finished, run the game's test with exactly this command (it is the
  only command you may run): .venv/Scripts/python craft_test.py quick
  It checks every file compiles, the world, a player's movement, crafting and the rules behave. If anything fails,
  fix it and run the test again.
- Don't add new packages. Don't touch files outside the game folder."""


USER_MOD_GUIDE = """MAKE IT A SWITCHABLE USER MOD (the teacher switches it on and off in Controls)
- Add ONE entry to USER_MODS in craft_design.py: a short key (lower case letters and _), a name for the teacher's
  Controls (up to 20 characters) and one sentence saying what it does. Never put anyone's name in it.
- It is OFF by default, and while it's off the game must work exactly as it did before. Only do anything new
  while it's switched on: game.rules["user_mods"]["<key>"] on the server (craft_game.Game).
- A change to a player's own movement needs the switch on both ends the same way, or the window and the server
  disagree about where they are: prefer the game's rules (server only) or the look (window only)."""


_engine.setup(_engine.Game(
    home=HERE, data=os.environ.get("CRAFTLAB_DATA") or os.path.join(HERE, "data"),
    protected={"ai_pipeline.py", "craft_profiles.py", "craft_brain.py", "brain_rules.py", "brain_worker.py",
               "craft_version.py", "craft_test.py"},
    skip_dirs={".venv", ".git", "__pycache__", "assets", "evidence", "ai_requests", "ai_changes", "profiles", "brains",
               "data"},
    design_target="bot", design_dir="mods/bots", design_var="BOT",
    world_target="world", world_file="mods/world.py",
    design_text=bot_file_text, sim=_sim, sim_file="craft_design.py", rules_limits=_rules_limits,
    mods_module="craft_mods.py", mods_test="craft_mods.py", showcase="craft_client.py",
    intro="their block-building game (digging, crafting, building, creatures and Craft Bots)",
    needs_game_examples="a new creature, a new kind of block that does something, or a new tool",
    mod_files_text=_mod_files_text, game_guide=GAME_GUIDE, user_mod_guide=USER_MOD_GUIDE))
DATA = _engine.DATA  # noqa: F811  (where the change history lives, for the windows)


if __name__ == "__main__":
    _engine.main()
