"""My Craft Bot's brain. The Bot asks brain(bot, world) what to do next, does it, and asks again.

Press U in the game to upload this file, and P to switch the autopilot on (P again stops it).

What the Bot can see:
    bot.front, bot.above, bot.below, bot.behind, bot.left_side, bot.right_side   the blocks round it ("air", "log"...)
    bot.facing ("east", "north", "west", "south")    bot.x, bot.y, bot.z    bot.inventory   bot.has("planks")
    bot.dug, bot.placed, bot.moves                   how much it has done
    bot.memory                                       a dictionary it keeps between turns
    world.block(dx, dy, dz)    world.find("coal_ore")    world.day
What it can do (return one):
    "forward" "back" "up" "down" "left" "right" "dig" "dig_up" "dig_down" "wait"
    ("place", "planks")  ("place_up", "torch")  ("place_down", "rubble")  ("say", "Hello!")
"""


def brain(bot, world):
    # A tunnel: dig the block in front, then move into the gap. Ten blocks, then stop and say so.
    if bot.dug >= 10:
        return ("say", "Tunnel done!")
    if bot.front != "air":
        return "dig"
    return "forward"
