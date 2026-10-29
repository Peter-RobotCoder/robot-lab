"""Blocks of your own. Each one is a dictionary in the list: change one, or add another.

    key     the name the code uses: lower case letters, digits and _ (like club_block)
    name    the name on the screen (a string)
    colour  [red, green, blue], each from 0 to 255 (a list)
    hard    how many seconds it takes to dig by hand (a number)
    light   how much light it gives, 0 (none) to 12 (as bright as a Lumen block): an integer
    tool    "drill", "cutter", "scoop" or None (what digs it faster)
"""

BLOCKS = [
    {"key": "club_block", "name": "Club block", "colour": [30, 160, 170], "hard": 1.0, "light": 0, "tool": None},
]
