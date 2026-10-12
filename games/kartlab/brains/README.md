# Writing a kart brain

Your brain is one Python function in one file. The game calls it 60 times a second while autopilot is on and
does what it returns. Start from `demo_brain.py`.

```python
def brain(me, track, rivals):
    target = track.point_ahead(8 + me.speed / 10)
    return 1, me.angle_to(target) / 25
```

## What to return

Two or three things: `throttle, steer` or `throttle, steer, drift`.

| | range | meaning |
|---|---|---|
| `throttle` | -1 to 1 | 1 flat out, 0 coast, below 0 brake (and reverse, slowly, once stopped) |
| `steer` | -1 to 1 | 1 full left, -1 full right (anything bigger is clamped) |
| `drift` | True / False | hold the drift button. Above about 30 km/h a drift turns tighter and builds `me.charge`; let go and it pays out as a mini-turbo (a super turbo if you held it long enough). Slower than that it only scrubs speed. |

## `me` - your kart

Every angle is in degrees, every distance in metres, speed in km/h. **Positive = left**, for angles and
for lateral positions, the same as `steer`.

| field | meaning |
|---|---|
| `me.x`, `me.y`, `me.heading` | where you are and which way you point (0 = along +x, anticlockwise) |
| `me.speed` | km/h |
| `me.lateral` | how far from the middle of the track you are: + left, - right. `me.track_width / 2` is the barrier |
| `me.track_width` | metres |
| `me.progress` | metres round the whole race (laps done × track length + metres along this lap) |
| `me.lap`, `me.laps` | laps completed, laps in the race |
| `me.place`, `me.count` | 1 for the leader; how many karts are racing |
| `me.angle_to_track` | the angle between your heading and the track's direction where you are: + turn left to straighten up |
| `me.curve_ahead` | how many degrees the track turns over the next 15 m (+ left). The number to brake for |
| `me.curve_far` | the same over the next 35 m, to see a corner coming early |
| `me.next_boost` | metres along the track to the next dash pad (a whole lap if there are none) |
| `me.next_boost_lateral` | how far left of the middle that pad sits |
| `me.on_oil`, `me.boosting`, `me.drifting` | True / False |
| `me.charge` | the drift charge built so far (270 = mini-turbo, 570 = super turbo) |
| `me.time` | seconds since GO |
| `me.memory` | a dictionary that is kept from one tick to the next (it starts empty) |
| `me.angle_to(thing)` | degrees to turn to face anything with `.x` and `.y`: a track point or a rival |
| `me.distance_to(thing)` | metres to it |

## `track`

| field | meaning |
|---|---|
| `track.name`, `track.length`, `track.width`, `track.laps` | the track's numbers (metres) |
| `track.point_ahead(metres)` | the middle of the track that far ahead of you, 0 to 35 m (a thing with `.x` and `.y`, so `me.angle_to(...)` works on it) |

## `rivals` - the other karts, a list

Each has `name`, `x`, `y`, `heading`, `speed`, `lateral`, `progress`, `place` as above (no memory), and
`rival.ahead`: metres along the track from you to it, positive in front, negative behind.
`rivals` may be empty.

## The rules

- The file may hold functions, `import math`, `import random`, and simple settings like `CORNER = 25` at the
  top. No classes, no files, no other imports, no names starting with `_`.
- A tick has 20 milliseconds and 5,000 lines. A brain that runs longer (a loop that never ends, a huge sum)
  is stopped and the error, with its line number, is shown to you. Fix it and upload again.
- A brain that crashes stops the autopilot; the kart coasts until you upload a fix.
- Your brain runs in its own small process with its own memory limit, so the worst it can do is stop itself.
- The file may be up to 20,000 characters.
