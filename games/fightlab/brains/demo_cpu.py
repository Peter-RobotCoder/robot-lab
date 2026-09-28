"""THE DEMO COMPUTER FIGHTER - for showing the class how a fighter brain works.

Set the computer level to "Empty" in the teacher Controls. The computer fighters stand still until you press
"Upload demo brain", which sends this file to the server; then every computer fighter runs it.
Change the code, upload again, and the class sees the difference straight away.

It works exactly like a learner's brain (brains/my_brain.py):
me     - this fighter: me.x  me.y  me.health  me.energy  me.special_ready  me.attacking  me.blocking
                       me.distance_to_edge  me.memory ...  me.distance_to(thing)
enemy  - the other fighter (or None)
Return three things: forward (-1 to 1), side (-1 to 1), action ("punch", "kick", "block", ... or "").
"""


def brain(me, enemy):
    # Step 1: it does nothing yet.
    return 0, 0, ""

    # Step 2: delete the line above, so it circles round the other fighter.
    # return 0, 1, ""

    # Step 3: walk in and punch; block when they attack.
    # if enemy is None:
    #     return 0, 0, ""
    # if enemy.attacking and me.distance_to(enemy) < 2:
    #     return 0, 0, "block"
    # if me.distance_to(enemy) > 1.2:
    #     return 1, 0, ""
    # return 0, 0, "punch"
