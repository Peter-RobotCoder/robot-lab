"""Game rules. Change the numbers to change how the game plays.

Learners' AI requests can change anything here (the teacher approves every change).
"""

RULES = {
    "match_seconds": 180,          # length of a battle
    "damage_multiplier": 1.0,      # all weapon damage is multiplied by this
    "spinner_energy_share": 0.6,   # share of a spinner's stored energy handed to the robot it hits
    "max_launch_speed": 7.0,       # m/s: the most any hit can throw a robot (about 2.5 m of air)
    "flip_power": 1.0,             # wedge flipper launch multiplier
    "gravity": 9.81,               # m/s squared
    "hazard_damage": 1.0,          # saw and spike damage multiplier
    "floor_flipper_every": 4.0,    # seconds between floor flipper shots
    "saw_cycle": 5.0,              # saws rise once every this many seconds...
    "saw_up_seconds": 2.0,         # ...and stay up this long
}
