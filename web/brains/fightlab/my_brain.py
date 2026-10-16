"""MY FIGHTER BRAIN - lesson 3.

This function runs 60 times a second when autopilot is on. In Fight Lab:
    U  uploads this file to the server      P  switches autopilot on and off

me     - your fighter:  me.x  me.y  (metres from the middle of the ring)  me.health (0-100)  me.energy (0-100)
                        me.special_ready  me.special  me.state  me.move  me.move_phase ("startup", "active",
                        "recovery" or "")  me.attacking  me.blocking  me.crouching  me.jumping  me.knocked_down
                        me.stunned  me.distance_to_edge  me.ring_out  me.time  me.wins
                        me.memory (a dictionary kept between ticks)
                        me.distance_to(thing)   me.centre (the middle of the ring)
enemy  - the other fighter (the same information, no memory), or None if nobody is in your ring

Return three things:
    forward  -1 (back away) to 1 (walk towards them)
    side     -1 (sidestep right) to 1 (sidestep left): circles round them, and dodges straight attacks
    action   one of: "punch" "kick" "low" "high" "throw" "special" "jump"  (a move: it starts once)
             or "block" "low_block" "crouch"  (held for as long as you keep returning it)
             or "" to do nothing

Tips: a punch reaches about 1.3 m, a kick 1.6 m. "block" stops high and mid attacks, "low_block" stops only
"low" sweeps (high attacks miss a crouching fighter anyway, but mid attacks hit it), and a throw goes straight
through any block. "kick" while walking forward (forward > 0.5) is the "high" kick.
Missions: use if / elif / else (3b), write your own function (3c), use me.memory (3d).
"""
import math


def brain(me, enemy):
    if enemy is None:
        return 0, 0, ""
    distance = me.distance_to(enemy)
    if distance > 1.2:
        return 1, 0, ""          # walk in
    return 0, 0, "punch"         # then punch
