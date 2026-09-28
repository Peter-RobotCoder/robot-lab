"""KAITO - a martial artist with a rising uppercut. The computer plays KAITO in the showcase.

Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between power, speed, defence and stamina (each 5-50).
Settings: percentages (size 80-120). Combo: a list of 2-5 moves (punch, kick, low, high).
Style: how it looks - trim colour (belt, gloves, headband), light colour, skin colour.
"""

FIGHTER = {
    "name": "KAITO",
    "body": "human",
    "colour": [235, 235, 240],
    "special": "uppercut",
    "points": {"power": 30, "speed": 25, "defence": 25, "stamina": 20},
    "settings": {"walk_speed": 80, "sidestep_speed": 70, "jump_height": 70, "attack_speed": 70, "size": 100},
    "combo": ["punch", "kick", "high"],
    "style": {"trim": [200, 30, 30], "lights": [255, 255, 255], "skin": [224, 172, 128], "number": "KAITO"},
}
