"""MY ROBOT BRAIN - lesson 3.

This function runs 60 times a second when autopilot is on. In Robot Lab:
    U  uploads this file to the server      P  switches autopilot on and off

me       - your robot:   me.x  me.y  me.heading  me.speed (km/h)  me.armour (0-100)
                         me.upside_down  me.weapon_ready  me.weapon_rpm  me.time
                         me.distance_to_wall  me.memory (a dictionary kept between ticks)
                         me.distance_to(thing)  me.angle_to(thing)   (+ = turn left, - = turn right)
                         me.pit  me.centre   (places you can measure to)
enemies  - a list of the other robots (same information, no memory)

Return three things:
    throttle  -1 (full reverse) to 1 (full speed ahead)
    steer     -1 (turn right) to 1 (turn left)
    attack    True to fire your weapon (a spinner or drum is switched on while this is True, and off while
              it's False: every robot starts with its weapon off)

Missions: use if / elif / else (3b), write your own function (3c), use me.memory (3d).
"""
import math


def brain(me, enemies):
    if not enemies:
        return 0, 0, False
    target = enemies[0]
    steer = me.angle_to(target) / 30
    throttle = 1
    attack = me.distance_to(target) < 2.5
    return throttle, steer, attack
