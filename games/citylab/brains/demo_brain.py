"""DEMO CITY BRAIN - the simplest brain that does something: walks to the depot for a parcel, then runs to the
address. Copy it to my_brain.py and make it yours (my_brain.py explains every field)."""


def brain(me, city, others):
    if not me.job:
        if me.distance_to(city.depot) < 2:
            return 0, 0  # (standing in the depot's ring: the parcel comes)
        return 0.8, me.angle_to(city.depot) / 90
    if me.target_distance < 6:
        return 0.3, me.angle_to_target / 90  # (slow by the beam: a delivery is made stopping there)
    return 1, me.angle_to_target / 90, "run"
