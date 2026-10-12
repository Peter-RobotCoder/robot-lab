"""The race's rules. Plain data: an approved AI request may change these (kart_mods.RULE_LIMITS has the ranges).
They live on the server only, so a rule change never makes a window and the server disagree about a kart."""

RULES = {
    "laps": 3,                 # laps in a race (1 to 9)
    "cpu_karts": 3,            # computer karts on the grid when the lesson has them (0 to 7)
    "countdown_seconds": 4.0,  # 3, 2, 1, GO (1 to 10)
    "bump_distance": 1.7,      # karts closer than this push each other apart, in metres (1 to 3)
    "bump_slowdown": 0.3,      # how much speed the faster kart loses in a bump (0 to 1)
}
