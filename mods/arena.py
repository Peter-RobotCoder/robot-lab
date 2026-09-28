"""The arena: which hazards are switched on and how it looks.

Learners' AI requests can change anything here (the teacher approves every change).
"""

ARENA = {
    "hazards": {"pit": True, "floor_flipper": True, "saws": True, "spikes": True, "house_robots": True},
    "look": {
        "name": "ROBOT LAB",            # painted in the middle of the floor and on the big screen
        "wall_colour": [155, 25, 20],   # the arena walls
        "crowd": True,                  # people in the stands
    },
}
