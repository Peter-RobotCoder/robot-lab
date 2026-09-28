"""BLAZE - a fast fighting robot with an energy blast. You play BLAZE in the showcase.

Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between power, speed, defence and stamina (each 5-50).
Settings: percentages (size 80-120). Combo: a list of 2-5 moves (punch, kick, low, high).
Style: how it looks - trim colour, light colour (eyes), and the name on its chest.
"""

FIGHTER = {
    "name": "BLAZE",
    "body": "robot",
    "colour": [210, 60, 30],
    "special": "blast",
    "points": {"power": 25, "speed": 35, "defence": 20, "stamina": 20},
    "settings": {"walk_speed": 85, "sidestep_speed": 75, "jump_height": 70, "attack_speed": 75, "size": 100},
    "combo": ["punch", "punch", "kick"],
    "style": {"trim": [40, 40, 44], "lights": [255, 190, 40], "number": "BLAZE"},
}
