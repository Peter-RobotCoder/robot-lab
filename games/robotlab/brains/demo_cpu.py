"""THE DEMO COMPUTER ROBOT - for showing the class how a robot brain works.

Set the computer robots to "Empty" in the teacher Controls. They stand still until you press
"Upload demo brain", which sends this file to the server; then every computer robot runs it.
Change the code, upload again, and the class sees the difference straight away.

It works exactly like a learner's brain (brains/my_brain.py):
me       - this robot:   me.x  me.y  me.heading  me.speed (km/h)  me.armour (0-100)
                         me.upside_down  me.weapon_ready  me.weapon_rpm  me.time
                         me.distance_to_wall  me.memory (a dictionary kept between ticks)
                         me.distance_to(thing)  me.angle_to(thing)   (+ = turn left, - = turn right)
                         me.pit  me.centre   (places you can measure to)
enemies  - a list of the other robots (same information, no memory)

Return three things: throttle (-1 to 1), steer (-1 right to 1 left), attack (True or False).
"""


def brain(me, enemies):
    # Step 1: it does nothing yet.
    return 0, 0, False

    # Step 2: delete the line above, so it drives in a circle.
    # return 0.5, 0.5, False

    # Step 3: chase the first enemy: turn towards it, and attack when it's close.
    # if not enemies:
    #     return 0, 0, False
    # target = enemies[0]
    # steer = me.angle_to(target) / 30
    # attack = me.distance_to(target) < 2.5
    # return 1, steer, attack
