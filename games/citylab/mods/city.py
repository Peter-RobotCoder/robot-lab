"""Which city the class plays. Plain data: an approved AI request may change it (city_mods.load_city checks it)."""

CITY = {
    "city": "harbour",         # harbour (Harbour City, 6 by 5 blocks), village (Little Lab, 3 by 3) or metro (Metro Lab, 8 by 6)
    "traffic": 6,              # the computer's cars about town (0 to 30)
    "robots": 6,               # robots on the pavements (0 to 20)
    "cpu_level": "medium",     # how the computer's street racers drive: easy, medium or expert
}
