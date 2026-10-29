"""Blueprints of your own, written as craft_items.BLUEPRINTS writes them. Each one is a dictionary in the list.

    makes     the name of what it makes: a block or an item ("locker", "club_block")
    count     how many it makes (1 to 50)
    parts     a dictionary: each part's name and how many it needs, like {"boards": 6, "rod": 2}
              (a group will do too: "any_log", "any_boards", "any_coal", "any_fluff")
    seconds   how long it takes to build (0.5 to 30)
    station   "hand" (build it anywhere) or "fabricator" (within 4 blocks of a Fabricator)
"""

BLUEPRINTS = [
    {"makes": "club_block", "count": 2, "parts": {"soil": 1, "sand": 1}, "seconds": 2, "station": "fabricator"},
]
