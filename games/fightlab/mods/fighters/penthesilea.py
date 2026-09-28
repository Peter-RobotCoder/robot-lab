"""PENTHESILEA - queen of the Amazons, with a leaf-bladed sword and a crescent shield.

A detailed 3D model (body "woman": the models/woman_*.gltf files, made in Blender by art/build_fighters.py).
Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between power, speed, defence and stamina (each 5-50).
Settings: percentages (size 80-120). Combo: a list of 2-5 moves (punch, kick, low, high).
Fighting style: kickboxer, boxer, capoeira, knives, swords or sticks. Weapon (armed styles only):
      knives: knife, dagger; swords: sword_shield, longsword, katana; sticks: stick, staff.
Colour: her clothes' main colour.
Look: outfit (hoplite, greek, commando, training, civilian), hair (ponytail, braid, long, bob, short, afro),
      hair_colour [r, g, b], shape (athletic, muscly, full), height (90-110 percent, just how she looks).
"""

FIGHTER = {
    "name": "PENTHESILEA",
    "body": "woman",
    "colour": [150, 18, 28],
    "special": "spin_kick",
    "points": {"power": 30, "speed": 30, "defence": 20, "stamina": 20},
    "settings": {"walk_speed": 85, "sidestep_speed": 80, "jump_height": 70, "attack_speed": 75, "size": 100},
    "combo": ["punch", "punch", "high"],
    "fighting_style": "swords",
    "weapon": "sword_shield",
    "look": {"outfit": "hoplite", "hair": "ponytail", "hair_colour": [70, 38, 22], "shape": "athletic", "height": 100},
}
