"""DEMO CITY BRAIN - the simplest brain that does something: walks to the depot for a parcel, then walks towards the
address. Copy it to my_brain.py and make it yours (my_brain.py explains every field)."""


def brain(me, city, others):
    if not me.job:
        return 0.8, me.angle_to(city.depot) / 90
    return 1, me.angle_to_target / 90, "run"
