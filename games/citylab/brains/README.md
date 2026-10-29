# Writing a city brain

Your brain is one Python function in one file. The game calls it many times a second while autopilot is on and
does what it returns. Start from `demo_brain.py`.

Where it lives: in the game, press **Tab** for the panel and open the **Code** tab to write it there and upload
it; or edit `my_brain.py` in this folder (in the downloaded app: `brains\citylab\my_brain.py` next to the app)
and press **U** in the game to upload it. **P** switches the autopilot on and off. The teacher turns brains on
from the lesson where you write one.

```python
def brain(me, city, others):
    if not me.job:
        return 0.8, me.angle_to(city.depot) / 90
    return 1, me.angle_to_target / 90, "run"
```

## What to return

Two or three things: `throttle, steer` or `throttle, steer, action`.

| | range | meaning |
|---|---|---|
| `throttle` | -1 to 1 | on foot: forward (below 0 walks backwards); in a car: 1 flat out, 0 coast, below 0 brake and reverse |
| `steer` | -1 to 1 | on foot: which way to walk, 1 is a right angle to your left; in a car: the wheel, 1 full left |
| `action` | a word, or a list of words | `"run"`, `"jump"`, `"punch"`, `"kick"`, `"block"`, `"door"` (into the car beside you, or out of it); in a car `"drift"` and `"handbrake"` |

## `me` - you (or the car you're driving)

Every angle is in degrees, every distance in metres, speed in km/h. **Positive = left**, for angles, the same
as `steer`.

| field | meaning |
|---|---|
| `me.x`, `me.y`, `me.heading` | where you are and which way you face (0 = east, anticlockwise) |
| `me.speed` | km/h |
| `me.in_car` | True at the wheel: then x, y, heading and speed are the car's |
| `me.health` | 0 to 100; `me.knocked_down` while you're on the floor |
| `me.cash`, `me.chips` | what you've earned; the chips you hold (the arcade pays for them) |
| `me.damage` | the car's damage, 0 to 2500 (wrecked at the top: the garage mends it) |
| `me.job` | `"delivery"`, `"taxi"`, `"race"`, `"roundup"`, or `""` with no job |
| `me.target_x`, `me.target_y`, `me.target_name`, `me.target_distance`, `me.angle_to_target` | on a job: where to go (the address, the passenger, the next checkpoint) |
| `me.time_left` | a delivery's clock, seconds |
| `me.time` | seconds since the city started |
| `me.memory` | a dictionary that is yours: whatever you put in it is there next tick |
| `me.angle_to(thing)`, `me.distance_to(thing)` | to anything with `.x` and `.y` (a place, one of `others`) |

## `city` - the city

| field | meaning |
|---|---|
| `city.name` | Harbour City, Little Lab or Metro Lab |
| `city.west`, `city.south`, `city.east`, `city.north` | its edges (a fence) |
| `city.depot`, `city.garage`, `city.rank`, `city.arcade`, `city.carpark` | the door of each place: a spot with `.x` and `.y` (walk into the depot's ring for a parcel, drive into the rank's for a passenger) |
| `city.on` | `"street"`, `"junction"` or `"pavement"` |
| `city.road_heading`, `city.angle_to_road` | on a street: which way it runs (the way nearer to yours), and how far to turn to follow it |

## `others` - what is near you

A list, the nearest first, of up to 12 things within 60 m: `name`, `kind` (`"person"`, `"car"`, `"robot"`), `x`,
`y`, `heading`, `speed`, `distance`, `angle` (+ = to your left). A robot has `rogue` (chasing you: punch and kick
it down) and `off` (powered down). A car has `empty` (nobody driving: `"door"` beside it gets you in).

## Rules

The file may hold functions, settings (plain `NAME = value` lines) and `import math` or `import random`: nothing
else, no files, no `__` names. A brain that takes too long (a loop that never ends) is stopped and told so; the
city carries on for everyone else. Press **U** to upload again after a fix.
