"""Game rules. Change the numbers to change how the game plays.

Learners' AI requests can change anything here (the teacher approves every change).
"""

RULES = {
    "round_seconds": 60,        # length of a round in a battle
    "damage_multiplier": 1.0,   # all attack damage is multiplied by this
    "chip_damage": 0.1,         # share of an attack's damage that still gets through a block
    "combo_scaling": 0.85,      # each extra hit in a combo does this share of the one before
    "knockback": 1.0,           # how far hits push fighters back
    "gravity": 9.81,            # m/s squared: lower is floatier jumps and longer juggles
    "special_cost": 50,         # energy a special move uses (the meter holds 100)
    "energy_gain": 1.0,         # how quickly the energy meter fills
    "ring_size": 4.5,           # the ring's radius in metres
    "hazard_damage": 1.0,       # electric ropes and fire jets damage multiplier
    "fire_jet_every": 5.0,      # seconds between fire jet bursts
}
