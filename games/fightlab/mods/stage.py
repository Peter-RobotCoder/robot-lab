"""The stage: which hazards are switched on and how it looks.

Learners' AI requests can change anything here (the teacher approves every change).
ring_out: the ring has no ropes, so a fighter knocked off the edge loses the round.
electric_ropes: the ropes zap anyone who touches them (only when ring_out is off, so there are ropes).
spikes: four spike patches near the edge hurt anyone pushed onto them.
"""

STAGE = {
    "hazards": {"ring_out": True, "electric_ropes": True, "fire_jets": True, "slippery": True, "spikes": True},
    "look": {
        "name": "FIGHT LAB",            # on the big screen and the ring mats
        "floor_colour": [40, 44, 70],   # the ring mat
        "rope_colour": [220, 40, 40],   # the ropes
        "crowd": True,                  # people in the stands
    },
}
