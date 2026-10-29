"""Recipes of your own, written as craft_items.RECIPES writes them.

A pattern is a list of strings (each letter a thing; . is an empty place) with a key saying what each letter is:
    {"makes": "torch", "count": 4, "pattern": ["C", "S"], "key": {"C": "coal", "S": "stick"}}
Or no pattern, just the things that go in, in any places:
    {"makes": "planks", "count": 4, "takes": ["log"]}
"""

RECIPES = [
    {"makes": "club_block", "count": 2, "takes": ["soil", "sand"]},
]
