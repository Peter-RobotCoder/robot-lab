"""TITAN - a heavy wedge with a flipper. The robot you drive in the showcase.

Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between speed, attack, armour and control (each 5-50).
Settings: percentages (size 80-120).
Style: how it looks - trim colour, light colour, and the name painted on the deck.
"""

ROBOT = {
    "name": "TITAN",
    "colour": [235, 110, 20],
    "weapon": "wedge",
    "points": {"speed": 25, "attack": 25, "armour": 30, "control": 20},
    "settings": {"forward_speed": 85, "reverse_speed": 70, "turn_speed": 75, "acceleration": 75, "size": 105},
    "style": {"trim": [28, 28, 32], "lights": [255, 170, 40], "number": "TITAN"},
}
