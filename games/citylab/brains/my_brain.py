"""MY CITY BRAIN - the starting example.

This function runs many times a second when autopilot is on. In City Lab:
    U  uploads this file to the server      P  switches autopilot on and off

me       - you:          me.x  me.y  me.heading  me.speed (km/h)  me.in_car  me.health  me.cash  me.chips
                         me.knocked_down  me.damage (the car's)  me.job ("delivery", "taxi", "race", "roundup" or "")
                         me.time (seconds since the city started)  me.memory (a dictionary kept between ticks)
                         on a job: me.target_x  me.target_y  me.target_name  me.target_distance (m)
                                   me.angle_to_target (degrees, + = turn left)  me.time_left (a delivery's clock)
                         me.angle_to(thing)  me.distance_to(thing)   (+ = turn left, - = turn right)
city     - the city:     city.name  city.west  city.south  city.east  city.north (its edges)
                         city.depot  city.garage  city.rank  city.arcade  city.carpark  (each a spot with .x .y)
                         city.on ("street", "junction" or "pavement")  city.road_heading  city.angle_to_road
others   - a list of what is near you, the nearest first: name, kind ("person", "car" or "robot"), x, y, heading,
                         speed, distance, angle (+ = to your left); a robot's rogue and off; a car's empty

Return two or three things:
    throttle  -1 to 1: on foot, forward (back if below 0); in a car, the pedals
    steer     -1 (right) to 1 (left): on foot, which way to walk (1 is a right angle to the left); in a car, the wheel
    action    a word, or a list of words (optional): "run", "jump", "punch", "kick", "block", "door" (get in the
              car beside you, or out of it); in a car "drift" and "handbrake"
"""


def brain(me, city, others):
    # Step 1: no job yet? Walk to the depot's ring: it hands you a parcel.
    if not me.job:
        if me.distance_to(city.depot) < 2:
            return 0, 0                      # standing in the ring: the job comes
        return 0.8, me.angle_to(city.depot) / 90

    # Step 2: on a job, head for the target. me.angle_to_target is how far to turn (+ left), so steer by it.
    steer = me.angle_to_target / 90
    throttle = 1 if me.target_distance > 6 else 0.3

    # Step 3: a rogue robot close by? Keep away from it (walk the other way) unless it's a round-up.
    for thing in others:
        if thing.kind == "robot" and thing.rogue and thing.distance < 6 and me.job != "roundup":
            steer = -1 if thing.angle > 0 else 1
            return 1, steer, "run"

    # Step 4: me.memory remembers things from one tick to the next (it starts empty). Here it counts the jobs.
    if me.memory.get("job") != me.job:
        me.memory["job"] = me.job
        me.memory["jobs_seen"] = me.memory.get("jobs_seen", 0) + 1

    # Things to try next:
    #   - get into a car for a long delivery: walk to the nearest car with .empty and return 0, 0, "door"
    #   - run when there's time to spare: return throttle, steer, "run" (it uses no energy, but you turn wider)
    #   - in a round-up, turn towards the nearest rogue robot and "kick" when thing.distance < 2
    return throttle, steer, "run" if me.target_distance > 20 else ""
