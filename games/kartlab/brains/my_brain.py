"""MY KART BRAIN - the starting example.

This function runs 60 times a second when autopilot is on. In the kart game:
    U  uploads this file to the server      P  switches autopilot on and off

me       - your kart:    me.x  me.y  me.heading  me.speed (km/h)  me.lateral (m from the middle, + = left)
                         me.track_width  me.progress (m round the race)  me.lap  me.laps  me.place  me.count
                         me.angle_to_track (degrees between you and the track's direction, + = turn left)
                         me.curve_ahead (how much the track turns in the next 15 m, + = left)
                         me.curve_far (the same over the next 35 m)
                         me.next_boost (m to the next dash pad)  me.next_boost_lateral (how far left it sits)
                         me.on_oil  me.boosting  me.drifting  me.charge  me.time (seconds since GO)
                         me.memory (a dictionary kept between ticks)
                         me.angle_to(thing)  me.distance_to(thing)   (+ = turn left, - = turn right)
track    - the track:    track.name  track.length  track.width  track.laps
                         track.point_ahead(metres)  the middle of the track that far ahead (a thing with .x .y)
rivals   - a list of the other karts: name, x, y, heading, speed, lateral, progress, place, and
                         rival.ahead (metres along the track in front of you: negative = behind you)

Return two or three things:
    throttle  -1 (brake / reverse) to 1 (flat out)
    steer     -1 (turn right) to 1 (turn left)
    drift     True to hold the drift button (optional). Drifting through a bend above a trot makes the kart
              turn tighter and builds a charge: let go and it pays out as a mini-turbo. Below about 30 km/h
              a drift just scrubs speed off.
"""

CORNER = 25      # a bend of more than this many degrees in the next 15 m is worth slowing for
DRIFT_BEND = 30  # ...and more than this, when you're going fast, is worth drifting through


def brain(me, track, rivals):
    # Step 1: look a little way up the track and turn towards it. The faster you go, the further you look,
    # so the line through the bends is smoother (8 m standing still, 18 m at 100 km/h).
    target = track.point_ahead(8 + me.speed / 10)
    angle = me.angle_to(target)             # degrees: + means the target is to your left
    steer = angle / 25                      # a full lock for 25 degrees or more (the game clamps it to -1..1)

    # Step 2: slow down for the bend ahead. me.curve_ahead is how many degrees the track turns in the next
    # 15 m; a gentle bend is fine flat out, a sharp one wants less throttle (the kart slides wide otherwise).
    bend = abs(me.curve_ahead)
    if bend > CORNER and me.speed > 60:
        throttle = 0.4
    else:
        throttle = 1

    # Step 3: drift through the sharp bends when you're fast enough for it to help. Holding the drift all the
    # way round builds the charge; it pays out as a boost on the way out.
    drift = bend > DRIFT_BEND and me.speed > 50

    # Step 4: me.memory remembers things from one tick to the next (it starts empty). Here it counts the laps
    # and notes when each one started, so you could print or compare lap times later.
    if me.memory.get("lap") != me.lap:
        me.memory["lap"] = me.lap
        me.memory["laps_started"] = me.memory.get("laps_started", 0) + 1
        me.memory["lap_start"] = me.time

    # Things to try next:
    #   - aim for the dash pads: when me.next_boost < 30, steer towards me.next_boost_lateral
    #   - keep off the oil: if me.on_oil, steer gently and don't brake
    #   - look at rivals[0].ahead: is someone just in front? Move over (steer away from their lateral)
    return throttle, steer, drift
