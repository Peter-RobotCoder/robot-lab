"""A recorded race, replayed: the server's whole race (every kart's step, bumps, damage, power-ups, gates and laps)
must give the same numbers tick for tick as when it was recorded (CHANGE 162).

    python replay_test.py            (replay replay_race.json: exit code 0 = the same to the last bit)
    python replay_test.py --record   (record it again: after a change meant to change the numbers, with
                                       kart_sim.SIM_VERSION raised, in the same commit)

The recording is six computer karts at three levels racing two laps of the club circuit with real damage and every
power-up on: their inputs each tick (so a change to the computer drivers doesn't change the replay) and every
30 ticks a hash of the whole race's state with every kart's wire numbers. A replay that differs says the first
30 ticks it differs in, and which kart's which numbers. Factorio's build server replays its saved games every day
for the same reason: a change to the step that wasn't meant to change it shows up at once.
"""
import base64
import hashlib
import json
import os
import random
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kart_version  # noqa: E402,F401  (puts the engine on the path)
import cpu_brains  # noqa: E402
import kart_items  # noqa: E402
import kart_sim  # noqa: E402
import kart_track  # noqa: E402
from engine import wire  # noqa: E402

FILE = os.path.join(HERE, "replay_race.json")
SCHEMA = wire.Schema("kart", kart_sim.SCHEMA_FIELDS)
TICKS = 4200   # (the countdown, then about 66 s of racing)
EVERY = 30
DESIGNS = [{"speed": 40, "acceleration": 30, "grip": 30}, {"speed": 30, "acceleration": 40, "grip": 30},
           {"speed": 30, "acceleration": 30, "grip": 40}, {"speed": 50, "acceleration": 25, "grip": 25},
           {"speed": 25, "acceleration": 50, "grip": 25}, {"speed": 34, "acceleration": 33, "grip": 33}]
LEVELS = ["easy", "medium", "expert", "medium", "expert", "easy"]


def new_race():
    kart_sim.RULES.clear()
    kart_sim.RULES.update(kart_sim.DEFAULT_RULES)  # (not mods/rules.py: the teacher's own rules aren't the step)
    race = kart_sim.Race(kart_track.load("club"), SCHEMA, laps=2)
    race.set_damage(True)
    for i, d in enumerate(DESIGNS):
        race.add(i + 1, d)
    race.items = kart_items.Items(race, seed=7)
    race.start()
    return race


def state_text(race):
    """The whole race as text: every kart's wire numbers, the item boxes, shots and slicks, the laps."""
    parts = [",".join(map(str, SCHEMA.ints(race.karts[kid]))) for kid in sorted(race.karts)]
    items = race.items
    parts.append("".join(str(b[3]) for b in items.boxes))
    parts += [repr((sh["id"], sh["kind"], sh["x"], sh["y"], sh["h"], sh["age"])) for sh in items.shots]
    parts += [repr((sl["id"], sl["x"], sl["y"], sl["age"])) for sl in items.slicks]
    parts.append(repr((race.tick, race.phase, sorted(race.finish))))
    return ";".join(parts)


def record():
    race, rng = new_race(), random.Random(11)
    inputs, checkpoints, h = bytearray(), [], hashlib.md5()
    for tick in range(TICKS):
        step = {}
        for kid, level in zip(sorted(race.karts), LEVELS):
            th, st, bt = cpu_brains.drive(level, race.karts[kid], race)
            t, s, b = wire.quantise_input(th, st, bt | kart_items.cpu_use(race.karts[kid], race, rng))
            ti, si = round(t * 100), round(s * 100)
            inputs += bytes([ti & 0xFF, si & 0xFF, b])
            step[kid] = (ti / 100, si / 100, b)
        race.step_all(step)
        h.update(state_text(race).encode())
        if (tick + 1) % EVERY == 0:
            checkpoints.append([tick + 1, h.hexdigest(), [SCHEMA.ints(race.karts[kid]) for kid in sorted(race.karts)]])
    laps = {kid: k["lap"] for kid, k in race.karts.items()}
    data = {"sim_version": kart_sim.SIM_VERSION, "ticks": TICKS, "karts": len(DESIGNS),
            "inputs": base64.b64encode(zlib.compress(bytes(inputs), 9)).decode(), "checkpoints": checkpoints,
            "laps": laps, "hits": sum(race.hits.values())}
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Recorded {TICKS} ticks of {len(DESIGNS)} karts (laps {laps}, {data['hits']} bumps): {FILE}")


def replay():
    with open(FILE, encoding="utf-8") as f:
        data = json.load(f)
    if data["sim_version"] != kart_sim.SIM_VERSION:
        print(f"FAIL the recording is of SIM_VERSION {data['sim_version']}, the step is {kart_sim.SIM_VERSION}: "
              f"record it again (python replay_test.py --record) in the same commit as the change")
        return 1
    raw = zlib.decompress(base64.b64decode(data["inputs"]))
    race, h, n = new_race(), hashlib.md5(), data["karts"]
    signed = lambda v: v - 256 if v > 127 else v  # noqa: E731
    marks = {c[0]: c for c in data["checkpoints"]}
    for tick in range(data["ticks"]):
        step = {}
        for i, kid in enumerate(sorted(race.karts)):
            o = (tick * n + i) * 3
            step[kid] = (signed(raw[o]) / 100, signed(raw[o + 1]) / 100, raw[o + 2])
        race.step_all(step)
        h.update(state_text(race).encode())
        mark = marks.get(tick + 1)
        if mark and mark[1] != h.hexdigest():
            print(f"FAIL the race differs from its recording between ticks {tick + 1 - EVERY} and {tick + 1}:")
            names = [f[0] for f in kart_sim.SCHEMA_FIELDS]
            for kid, want in zip(sorted(race.karts), mark[2]):
                got = SCHEMA.ints(race.karts[kid])
                diff = [f"{names[j]} {want[j]} now {got[j]}" for j in range(len(want)) if want[j] != got[j]]
                if diff:
                    print(f"    kart {kid}: " + ", ".join(diff[:6]))
            print("    (if the step was meant to change: raise kart_sim.SIM_VERSION and record it again)")
            return 1
    laps = {str(kid): k["lap"] for kid, k in race.karts.items()}
    print(f"PASS the recorded race ({data['ticks']} ticks, {n} karts, laps {laps}, {data['hits']} bumps) replays to "
          f"the last bit")
    return 0


if __name__ == "__main__":
    if "--record" in sys.argv:
        record()
    else:
        sys.exit(replay())
