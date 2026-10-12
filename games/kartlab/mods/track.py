"""Which track the class races. Plain data: an approved AI request may change it (kart_mods.load_track checks it)."""

TRACK = {
    "track": "club",           # club (the Club Circuit, 372 m with a hill), oval or straight
    "laps": 3,                 # 1 to 9
    "name": "Club Circuit",    # what the track is called (up to 16 characters)
    "cpu_level": "medium",     # how the computer karts drive: easy, medium or expert
}
