"""MY ROBOT BRAIN - Mission 3.

This function runs 60 times a second when autopilot is on. In Robot Lab:
    U  uploads this file to the server      P  switches autopilot on and off

me       - your robot:   me.x  me.y  me.heading  me.speed (km/h)  me.armour (0-100)
                         me.upside_down  me.weapon_ready  me.weapon_rpm  me.time
                         me.distance_to_wall  me.memory (a dictionary kept between ticks)
                         me.distance_to(thing)  me.angle_to(thing)   (+ = turn left, - = turn right)
                         me.distance_from_left(thing)  me.distance_from_right(thing)
                             (0 to 100: how far the enemy is from a feeler 3 m out to your left, and one 3 m out
                              to your right, as a percentage of the arena. 0 = touching, 100 = the far corner)
                         me.pit  me.centre   (places you can measure to)
enemies  - a list of the other robots (same information, no memory)

Return three things:
    throttle  -1 (full reverse) to 1 (full speed ahead)
    steer     -1 (turn right) to 1 (turn left)
    attack    True to fire your weapon (a spinner or drum is switched on while this is True, and off while
              it's False: every robot starts with its weapon off)

BRAITENBERG VEHICLES: a robot with no sensors it has to read, two motors, and one wire from each side to a motor.
The game already knows where the enemy is, so each motor's speed is set straight from a distance.
    Direct wire:    the closer the enemy, the FASTER the motor   (speed = 100 - distance)
    Inhibited wire: the closer the enemy, the SLOWER the motor   (speed = distance)
    Straight wiring: the left distance drives the left motor.  Crossed: the left distance drives the right motor.

Missions: use if / elif / else (3b), write your own function (3c), use me.memory (3d).
"""
import math

VEHICLE = "aggression"  # try: "fear", "aggression", "love", "explorer"


def motors(left, right):
    """Turn two motor speeds (each -100 to 100, a percentage of what that motor can do) into what the game wants:
    throttle (how fast, both motors together) and steer (the difference between them)."""
    throttle = (left + right) / 200           # both motors at 100 = full speed ahead (1.0)
    steer = (right - left) / 200 * 6          # the right motor faster than the left = the robot turns left (+).
    steer = max(-1, min(1, steer))            # the two sides never differ by much, so the difference is boosted 6x
    return throttle, steer


def fear(me, enemy):
    """Straight wiring, direct: the near side's motor runs faster, so the robot turns AWAY and flees."""
    left_motor = 100 - me.distance_from_left(enemy)      # the enemy close to the left wheels: left motor fast
    right_motor = 100 - me.distance_from_right(enemy)    # the enemy close to the right wheels: right motor fast
    return motors(left_motor, right_motor)


def aggression(me, enemy):
    """Crossed wiring, direct: the far side's motor runs faster, so the robot turns TOWARDS the enemy and charges."""
    left_motor = 100 - me.distance_from_right(enemy)     # crossed: the right distance drives the left motor
    right_motor = 100 - me.distance_from_left(enemy)     # crossed: the left distance drives the right motor
    return motors(left_motor, right_motor)


def love(me, enemy):
    """Straight wiring, inhibited: the closer the enemy, the slower the motors. It comes close and slows to a stop."""
    left_motor = me.distance_from_left(enemy)            # far away = fast, close = slow
    right_motor = me.distance_from_right(enemy)
    return motors(left_motor, right_motor)


def explorer(me, enemy):
    """Crossed wiring, inhibited: slows down near the enemy and turns away, then speeds off to explore."""
    left_motor = me.distance_from_right(enemy)           # crossed
    right_motor = me.distance_from_left(enemy)
    return motors(left_motor, right_motor)


def brain(me, enemies):
    if not enemies:                                      # nobody to react to: sit still
        return 0, 0, False
    enemy = enemies[0]                                   # the first other robot
    if VEHICLE == "fear":
        throttle, steer = fear(me, enemy)
    elif VEHICLE == "love":
        throttle, steer = love(me, enemy)
    elif VEHICLE == "explorer":
        throttle, steer = explorer(me, enemy)
    else:
        throttle, steer = aggression(me, enemy)
    attack = me.distance_to(enemy) < 2.5                 # fire the weapon when the enemy is within 2.5 m
    return throttle, steer, attack
