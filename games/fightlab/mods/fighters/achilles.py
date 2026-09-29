"""ACHILLES - the greatest hero of the Greeks at Troy, and Penthesilea's rival.

A detailed 3D model (body "man": the models/man_*.gltf files, made in Blender by art/build_fighters.py).
Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between power, speed, defence and stamina (each 5-50).
Settings: percentages (size 80-120). Combo: a list of 2-5 moves (punch, kick, low, high).
Fighting style: kickboxer, boxer, capoeira, knives, swords or sticks. Weapon (armed styles only):
      knives: knife, dagger; swords: sword_shield, longsword, katana; sticks: stick, staff.
Colour: his clothes' main colour.
Look: outfit (hoplite, greek, commando, training, civilian), hair (short, classic, spiky, crop, afro, long),
      hair_colour [r, g, b], shape (athletic, muscly, full), win (victory, dance, bow, power_up),
      height (90-110 percent, just how he looks).
"""

FIGHTER = {
    "name": "ACHILLES",
    "body": "man",
    "colour": [30, 60, 150],
    "special": "uppercut",
    "points": {"power": 35, "speed": 25, "defence": 20, "stamina": 20},
    "settings": {"walk_speed": 80, "sidestep_speed": 70, "jump_height": 70, "attack_speed": 70, "size": 100},
    "combo": ["punch", "kick", "high"],
    "fighting_style": "swords",
    "weapon": "sword_shield",
    "look": {"outfit": "hoplite", "hair": "classic", "hair_colour": [200, 160, 90], "shape": "muscly", "height": 104},
}
