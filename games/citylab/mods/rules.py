"""The city's rules. Plain data: an approved AI request may change these (city_mods.RULE_LIMITS has the ranges).
They live on the server only, so a rule change never makes a window and the server disagree about where a car is."""

RULES = {
    "traffic": 6,            # the computer's cars about town when the lesson has them (0 to 30)
    "robots": 6,             # robots on the pavements when the lesson has them (0 to 20)
    "parked": 10,            # cars parked for anyone to take (0 to 40)
    "delivery_pay": 50,      # a parcel delivered in time, plus a bonus for every second left (0 to 500)
    "taxi_fare": 40,         # a passenger taken to their stop, plus a tip that drops with every bump (0 to 500)
    "race_pay": 100,         # first place in a street race; second gets 60%, third 30% (0 to 1000)
    "roundup_pay": 15,       # each rogue robot powered down in a round-up (0 to 200)
    "chip_pay": 10,          # each chip cashed at the arcade (0 to 100)
    "bump_distance": 2.4,    # cars closer than this push each other apart, in metres (1 to 3.5)
    "bump_slowdown": 0.3,    # how much speed the faster car loses in a bump (0 to 1)
    "bump_transfer": 0.7,    # how much of the closing speed passes to the car in front (0 to 1)
}
