"""ROBIN - the club's fighting robot, in full detail.

A detailed 3D model (body "robin": the models/robin_*.gltf files, made in Blender by art/build_fighters.py and
art/robinlib.py). Metal plating in the fighter's colour, with the style's trim and light colours and the chest number.
Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between power, speed, defence and stamina (each 5-50).
Settings: percentages (size 80-120). Combo: a list of 2-5 moves (punch, kick, low, high).
Fighting style: kickboxer, boxer, capoeira, knives, swords or sticks. Weapon (armed styles only):
      knives: knife, dagger; swords: sword_shield, longsword, katana; sticks: stick, staff, glaive.
Look: shape (athletic, muscly, full: the frame), height (90-110 percent, just how it looks), win (victory, dance,
      bow, power_up).
Style: trim [r, g, b], lights [r, g, b] (the eyes, core and strips glow), number (on the chest, up to 10 characters).
"""

FIGHTER = {
    "name": "ROBIN",
    "body": "robin",
    "colour": [60, 130, 230],
    "special": "blast",
    "points": {"power": 25, "speed": 25, "defence": 30, "stamina": 20},
    "settings": {"walk_speed": 80, "sidestep_speed": 70, "jump_height": 70, "attack_speed": 70, "size": 100},
    "combo": ["punch", "punch", "kick"],
    "fighting_style": "kickboxer",
    "look": {"shape": "athletic", "height": 100, "win": "power_up"},
    "style": {"trim": [140, 145, 155], "lights": [90, 230, 255], "number": "RB-01"},
}
