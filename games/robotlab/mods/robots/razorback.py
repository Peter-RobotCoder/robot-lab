"""RAZORBACK - a horizontal spinner. The computer drives it in the showcase.

Learners' AI requests can change anything here (the teacher approves every change).
Points: 100 to share between speed, attack, armour and control (each 5-50).
Settings: percentages (size 80-120).
Style: how it looks - trim colour, light colour, and the name painted on the deck.
"""

ROBOT = {
    "name": "RAZORBACK",
    "colour": [200, 20, 28],
    "weapon": "spinner",
    "points": {"speed": 25, "attack": 35, "armour": 20, "control": 20},
    "settings": {"forward_speed": 80, "reverse_speed": 60, "turn_speed": 70, "acceleration": 70, "size": 100},
    "style": {"trim": [225, 225, 230], "lights": [60, 170, 255], "number": "RAZOR"},
}
