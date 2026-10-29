"""Craft Lab's tests (CHANGE 200; our own world since CHANGE 207).

    python craft_test.py quick      the world, the meshes, the movement, the blueprints, the suit, the rules, the
                                    creatures and the rifts, the Bots, the mods, saving
    python craft_test.py server     a real server and two learners by hand (block changes for everyone, a dig out of
                                    reach refused, a blueprint built, snapshots, the teacher's keys, the missions)
    python craft_test.py online     two windows on one server over pretend school Wi-Fi: few corrections each
    python craft_test.py window     every graphics tier drawn offline, the night, the Backpack, a Craft Bot
    python craft_test.py            all of them
Test data goes to a temporary folder (and pictures there too). Exit code 0 = all fine.
"""
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="craftlab_test_")
os.environ["CRAFTLAB_DATA"] = TMP
PY = sys.executable
results = []

import craft_version  # noqa: E402,F401  (puts the engine on the path)
import craft_blocks as B  # noqa: E402
import craft_items as items  # noqa: E402
import craft_sim as sim  # noqa: E402
import craft_world as W  # noqa: E402

I, ID = B.ITEM_ID, B.ID


def check(name, ok, note=""):
    results.append((name, bool(ok), note))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  ({note})"), flush=True)


def run(name, fn):
    try:
        fn()
    except Exception as e:  # (report and carry on)
        import traceback
        check(name, False, f"{type(e).__name__}: {e} {traceback.format_exc()[-600:]}")


def flat_world(ground=10):
    """A small world of stone up to ground, air above: tests know exactly what is where."""
    w = W.World("small", 1, blank=True)
    w.blocks[:, :, :ground] = ID["stone"]
    w.blocks[:, :, 0] = ID["lab_floor"]
    w.spawn = (64.5, 64.5, float(ground))
    w.light_all()
    return w


def game_on(w, **rules):
    import craft_game
    g = craft_game.Game(w, dict({"mobs": False}, **rules))
    return g


def bp_index(makes):
    return next(i for i, bp in enumerate(items.blueprints()) if bp["makes"] == makes)


def stand(g, p, x, y, z=10.0):
    """A player put somewhere on the flat ground (p.state is a new dict each step)."""
    p.state.update(x=x, y=y, z=z, vx=0.0, vy=0.0, vz=0.0, fall=0.0)
    for _ in range(5):
        g.step({})


# ---------- quick ----------
def world_checks():
    a, b = W.World("small", 42), W.World("small", 42)
    same = hashlib.md5(a.blocks.tobytes()).hexdigest() == hashlib.md5(b.blocks.tobytes()).hexdigest()
    c = W.World("small", 43)
    check("The same seed makes the same island, another seed another", same and not (a.blocks == c.blocks).all())
    import numpy as np
    biomes = len(set(np.unique(a.biome).tolist()))
    kinds = set(np.unique(a.blocks).tolist())
    ores = {k for k in ("coal_ore", "copper_ore", "iron_ore") if ID[k] in kinds}
    x, y, z = (int(v) for v in a.spawn)
    check("The island has its biomes, its ores, caves and the sea, and you start on dry land",
          biomes >= 4 and len(ores) == 3 and ID["water"] in kinds and a.blocks[x, y, z - 1] not in (0, ID["water"]),
          f"biomes {biomes} ores {ores} under {B.BLOCKS[a.blocks[x, y, z - 1]]['key']}")
    m = W.World("medium", 2026)
    lockers = [r["locker"] for r in m.ruins if m.get(*r["locker"]) == ID["locker"]]
    heaps = [h for h in m.heaps if m.get(h[0], h[1], h[2]) in (ID["scrap_pile"], ID["rust_pile"])]
    fruit = int((m.blocks == ID["glowfruit_leaves"]).sum())
    check("A medium island has its own landmarks: ruined lab buildings with a Locker, 3 scrap heaps in the caves, "
          "Glowfruit trees and the Lab floor at the bottom", len(lockers) >= 1 and len(heaps) == 3 and fruit > 0
          and (m.blocks[:, :, 0] == ID["lab_floor"]).all(), f"lockers {lockers} heaps {m.heaps} fruit {fruit}")
    w = flat_world()
    open_sky = int(w.sky[64, 64, 12])
    w.set(64, 64, 14, ID["stone"])
    under = int(w.sky[64, 64, 13])
    w.set(70, 70, 10, ID["glowstick"])
    lit = int(w.glow[70, 70, 10]), int(w.glow[73, 70, 10])
    check("Light runs from 0 to 12: an open sky is 12, a block overhead dims it, a Glowstick lights 10 and less "
          "further off", open_sky == 12 and under < 12 and lit[0] == 10 and lit[1] == 7, f"{open_sky} {under} {lit}")


def mesh_checks():
    import craft_art
    import craft_mesh as M
    atlas, where = craft_art.build_atlas()
    t = M.Tables(where)
    w = W.World("small", 1, blank=True)
    w.blocks[5:7, 5:6, 5:6] = ID["stone"]  # (two stone blocks side by side: 10 faces, the two between hidden)
    out, lines = M.mesh_chunk(w, 0, 0, t, "mesh")
    quads = out[0].arrays()[2]
    out2, lines2 = M.mesh_chunk(w, 0, 0, t, "lines")
    check("A chunk's mesh has only the open faces (two blocks side by side: 10), mesh draws every edge, lines leave "
          "out the edges between the two", quads == 10 and len(lines) == 40 and len(lines2) == 32,
          f"{quads} quads, {len(lines)} and {len(lines2)} lines")
    big = W.World("small", 7)
    t0 = time.perf_counter()
    for key in big.chunks[:16]:
        M.mesh_chunk(big, key[0], key[1], t)
    each = (time.perf_counter() - t0) / 16 * 1000
    check("A chunk of the island meshes quickly (under 60 ms)", each < 60, f"{each:.0f} ms")
    pink = [n for n in where if (atlas[where[n][1] * 16:(where[n][1] + 1) * 16, where[n][0] * 16:(where[n][0] + 1) * 16, :3]
                                 == (255, 0, 255)).all(axis=-1).sum() > 20]
    cracks = [n for n in where if n.startswith("crack_")]
    rack = [where.get(f"server_rack_{k}") for k in range(4)]
    frames = all(r is not None for r in rack) and all(rack[k] == (rack[0][0] + k, rack[0][1]) for k in range(4))
    check("Every tile is drawn (none left pink), no crack tiles, the Server Rack's four frames side by side",
          not pink and not cracks and frames, f"pink {pink} cracks {cracks} rack {rack}")


def sim_checks():
    w = flat_world()
    s = sim.new_player(64.5, 64.5, 10.0)
    for _ in range(120):
        s = sim.step_player(s, (1.0, 0.0, 0), sim.STEP, w)
    walked = s["x"] - 64.5
    check("Walking: about 4.5 metres a second on flat ground", 7.9 < walked < 9.4, f"{walked:.2f} m in 2 s")
    w.blocks[70, 60:70, 10] = ID["stone"]  # (a wall one block high: a jump gets over it)
    s = sim.new_player(66.5, 64.5, 10.0)
    most = 0.0
    for i in range(240):
        s = sim.step_player(s, (1.0, 0.0, sim.JUMP_B if s["x"] > 68.8 else 0), sim.STEP, w)
    s2 = sim.new_player(40.5, 40.5, 10.0)
    for i in range(70):
        s2 = sim.step_player(s2, (0.0, 0.0, sim.JUMP_B if i == 10 else 0), sim.STEP, w)
        most = max(most, s2["z"] - 10.0)
    check("A jump lifts you 1.4 blocks: over a block, and you stand on top", s["x"] > 70.5 and 1.3 < most < 1.5,
          f"x {s['x']:.2f} z {s['z']:.2f}, highest {most:.2f}")
    w.blocks[75, 60:70, 10:13] = ID["stone"]  # (a wall three high: nothing gets over it)
    s = sim.new_player(73.5, 64.5, 10.0)
    for _ in range(240):
        s = sim.step_player(s, (1.0, 0.0, sim.JUMP_B), sim.STEP, w)
    check("A wall three blocks high stops you", s["x"] < 74.66, f"x {s['x']:.3f}")
    s = sim.new_player(40.5, 40.5, 20.0)
    most = 0.0
    for _ in range(120):
        s = sim.step_player(s, (0.0, 0.0, 0), sim.STEP, w)
        most = max(most, s["fall"])
    check("You fall and land on the ground (and the fall is measured)", abs(s["z"] - 10.0) < 1e-6 and most > 9,
          f"z {s['z']} fall {most:.1f}")
    w.blocks[50:60, 50:60, 9:14] = ID["water"]
    s = sim.new_player(55.5, 55.5, 9.0)
    for _ in range(90):
        s = sim.step_player(s, (0.0, 0.0, sim.JUMP_B), sim.STEP, w)
    check("In water, holding jump swims you up", s["z"] > 11, f"z {s['z']:.2f}")
    s = sim.new_player(30.5, 30.5, 10.0)
    for _ in range(60):
        s = sim.step_player(s, (0.0, 0.0, sim.FLY_B | sim.JUMP_B), sim.STEP, w, creative=True)
    flew = s["z"]
    s2 = sim.new_player(30.5, 30.5, 10.0)
    for _ in range(60):
        s2 = sim.step_player(s2, (0.0, 0.0, sim.FLY_B | sim.JUMP_B), sim.STEP, w, creative=False)
    check("Sandbox players fly; Challenge players can't", flew > 14 and s2["z"] < 12, f"{flew:.1f} {s2['z']:.1f}")
    w.blocks[20:25, 20:25, 10] = ID["stone"]  # (a ledge: Careful mode stops you stepping off its edge)
    s = sim.new_player(22.5, 22.5, 11.0)
    for _ in range(180):
        s = sim.step_player(s, (1.0, 0.0, sim.CAREFUL_B), sim.STEP, w)
    check("In Careful mode you don't step off an edge", s["z"] > 10.99 and s["x"] < 25.45, f"x {s['x']:.2f} z {s['z']:.2f}")
    import random
    from engine import wire
    schema = wire.Schema("craft", sim.SCHEMA_FIELDS)
    rng = random.Random(5)
    inputs = [(0.6 + rng.uniform(-0.4, 0.4), rng.uniform(-1, 1), rng.choice([0, 0, sim.JUMP_B, sim.SPRINT_B]))
              for _ in range(600)]
    world = flat_world()  # (with steps and pillars here and there, to bump into and jump onto)
    for k in range(80):
        world.blocks[rng.randrange(40, 100), rng.randrange(40, 100), 10:10 + rng.choice([1, 1, 3])] = ID["stone"]
    a = sim.new_player(*world.spawn)
    b = dict(a)
    for inp in inputs:
        a = sim.step_player(a, wire.quantise_input(*inp), sim.STEP, world)
        a.update(schema.quantise(a))
        b = sim.step_player(b, wire.quantise_input(*inp), sim.STEP, world)
        b.update(schema.quantise(b))
    moved = math.hypot(a["x"] - world.spawn[0], a["y"] - world.spawn[1])
    check("The step is deterministic: the same inputs give the same numbers to the last bit (a window predicts "
          "with it)", a == b and moved > 1, f"same {a == b}, moved {moved:.1f} m")
    w = flat_world()
    hit = sim.ray(w, 64.5, 64.5, 11.6, 0.0, 0.0, -1.0, 5)
    check("The ray from your eyes finds the block you look at, and the face it came in by",
          hit is not None and hit[0] == (64, 64, 9) and hit[1] == (0, 0, 1), str(hit))


def blueprint_checks():
    bad = []
    for bp in items.blueprints():
        inv = [None] * items.SLOTS
        for part, n in bp["parts"].items():
            items.add(inv, I[items.GROUPS.get(part, (part,))[0]], n)
        if not items.can_build(inv, bp) or not items.take_parts(inv, bp) or any(inv):
            bad.append(bp["makes"])
    check(f"Every one of the {len(items.blueprints())} blueprints can be built from its parts, and takes all of them",
          not bad, ", ".join(bad[:5]))
    hand = [bp["makes"] for bp in items.blueprints() if bp["station"] == "hand"]
    check("The four Quick Builds (by hand) are Boards, Rods, Glowsticks and the Fabricator",
          sorted(hand) == ["boards", "fabricator", "glowstick", "rod"], str(hand))
    inv = [None] * items.SLOTS
    left = items.add(inv, I["rubble"], 120)
    cur = items.click(inv, 0, None, right=True)
    check("Stacks of 50: 120 rubble fill two stacks and 20 more; a right click splits a stack in half",
          left == 0 and inv[0][1] == 25 and cur[1] == 25 and inv[1][1] == 50 and inv[2][1] == 20, f"{inv[:3]} {cur}")
    w = flat_world()
    g = game_on(w)
    p = g.add_player(0, "Sam")
    stand(g, p, 64.5, 64.5)
    p.inv = [None] * items.SLOTS
    items.add(p.inv, I["log"], 1)
    g.inv_changed(0)
    g.action(0, {"type": "build", "bp": bp_index("locker")})
    refused = not p.building
    g.action(0, {"type": "build", "bp": bp_index("boards")})
    for _ in range(80):
        g.step({})
    boards = items.count_of(p.inv, I["boards"])
    items.add(p.inv, I["boards"], 20)
    items.add(p.inv, I["rod"], 2)
    g.inv_changed(0)
    g.action(0, {"type": "build", "bp": bp_index("locker")})
    far = not p.building
    w.set(66, 64, 10, ID["fabricator"])
    g.action(0, {"type": "build", "bp": bp_index("locker")})
    for _ in range(60 * 3):
        g.step({0: (0.5, 0.0, 0)})  # (walking away while it builds)
    locker = items.count_of(p.inv, I["locker"])
    check("A blueprint is greyed until each part has been held; a Quick Build works anywhere; a Locker needs a "
          "Fabricator within 4 blocks, and finishes in your Backpack as you walk away",
          refused and boards == 3 and far and locker == 1, f"refused {refused} boards {boards} far {far} locker {locker}")
    p.inv = [None] * items.SLOTS
    p.inv[0] = [I["drill_mk1"], 1, 5]
    items.add(p.inv, I["copper_ingot"], 3)
    g.inv_changed(0)
    stand(g, p, 64.5, 64.5)
    g.action(0, {"type": "build", "bp": bp_index("drill_mk2")})
    for _ in range(60 * 5):
        g.step({})
    up = next((s for s in p.inv if s and s[0] == I["drill_mk2"]), None)
    check("A Mk1 Drill and 3 Copper ingots upgrade to a Mk2 Drill, with all its uses back",
          up is not None and up[2] == B.ITEMS[I["drill_mk2"]]["uses"] and not items.count_of(p.inv, I["drill_mk1"]),
          str(up))


def suit_checks():
    w = flat_world()
    g = game_on(w)
    p = g.add_player(0, "Sam")
    for _ in range(10):
        g.step({})
    p.inv = [None] * items.SLOTS
    p.inv[0] = items.new_slot(I["iron_visor"], 1)
    p.selected = 0
    g.action(0, {"type": "use_item"})
    p.inv[5] = items.new_slot(I["iron_vest"], 1)
    p.inv[6] = items.new_slot(I["iron_boots"], 1)
    g.action(0, {"type": "click", "area": "inv", "slot": 5, "shift": True})
    g.action(0, {"type": "click", "area": "inv", "slot": 6})            # (picked up...)
    g.action(0, {"type": "click", "area": "suit", "slot": 0})           # (...won't go on your head...)
    wrong = p.cursor is not None and p.cursor[0] == I["iron_boots"]
    g.action(0, {"type": "click", "area": "suit", "slot": 2})           # (...goes on your feet)
    worn = [B.ITEMS[a[0]]["key"] if a else None for a in p.suit]
    check("The suit is worn three ways (right click, Shift and click, into its slot), only in its own slot: an iron "
          "suit gives 30 Shield", wrong and worn == ["iron_visor", "iron_vest", "iron_boots"] and p.shield_max() == 30,
          f"{worn} {p.shield_max()}")
    for _ in range(60 * 20):  # (it fills up while nothing hurts you)
        g.step({})
    full = p.shield
    s = p.state
    s["hp"] = 100
    p.hurt_at = -10.0
    g.hurt(p, 14, "grab")
    soaked = (s["hp"], p.shield)
    for k in range(3):
        p.hurt_at = -10.0
        g.hurt(p, 10, "zap")
    after = s["hp"]
    uses = p.suit[0][2]
    s["hp"] = 100
    g.hurt(p, 16, "fell")
    fell = 100 - s["hp"]
    check("The Shield soaks hits completely until it is empty, then Health takes them; each soak wears the suit a "
          "little; a fall isn't soaked", full == 30 and soaked == (100, 16) and after == 86 and fell == 16
          and uses == B.ITEMS[I["iron_visor"]]["uses"] - 3, f"full {full} soaked {soaked} after {after} uses {uses}")
    saved = p.to_save()
    q = type(p)(9, "Copy", (5.0, 5.0, 11.0))
    q.load(json.loads(json.dumps(saved)))
    check("What you wear is saved with you (and its wear)", [a[0] if a else 0 for a in q.suit] ==
          [a[0] for a in p.suit] and q.suit[0][2] == uses)
    p.inv[3] = [I["drill_mk3"], 1, 17]
    g.action(0, {"type": "click", "area": "inv", "slot": 3, "shift": True})
    moved = next((sl for sl in p.inv[items.TOOLBELT:] if sl and sl[0] == I["drill_mk3"]), None)
    check("A worn Drill moved with Shift and click keeps its wear (it isn't mended)", moved is not None and moved[2] == 17,
          str(moved))


def rules_checks():
    import craft_game
    w = flat_world()
    g = game_on(w)
    p = g.add_player(0, "Sam")
    for _ in range(30):
        g.step({})
    x, y, z = int(p.state["x"]), int(p.state["y"]), int(p.state["z"])
    p.inv[2] = items.new_slot(I["drill_mk1"], 1)
    p.selected = 2
    g.action(0, {"type": "dig_start", "x": x + 1, "y": y, "z": z - 1})
    g.action(0, {"type": "dig", "x": x + 1, "y": y, "z": z - 1})
    early = w.get(x + 1, y, z - 1) == ID["stone"]
    for _ in range(int(60 * B.dig_time(ID["stone"], B.ITEMS[I["drill_mk1"]])[0])):
        g.step({})
    g.action(0, {"type": "dig", "x": x + 1, "y": y, "z": z - 1})
    dug = w.get(x + 1, y, z - 1) == 0
    g.action(0, {"type": "dig_start", "x": x + 9, "y": y, "z": z - 1})
    for _ in range(600):
        g.step({})
    g.action(0, {"type": "dig", "x": x + 9, "y": y, "z": z - 1})
    check("A dig sent too soon is refused; in time it digs; out of reach is refused",
          early and dug and w.get(x + 9, y, z - 1) == ID["stone"])
    hand, hand_ok = B.dig_time(ID["stone"], None)
    drill, ok = B.dig_time(ID["stone"], B.ITEMS[I["drill_mk3"]])
    _, mk1_neon = B.dig_time(ID["neon_ore"], B.ITEMS[I["drill_mk1"]])
    _, mk2_neon = B.dig_time(ID["neon_ore"], B.ITEMS[I["drill_mk2"]])
    _, cutter = B.dig_time(ID["stone"], B.ITEMS[I["cutter_mk4"]])
    check("A Drill digs stone far faster than a hand and a hand gets nothing from it; Neon ore needs a Mk2 Drill; a "
          "Cutter is no Drill", drill < hand / 4 and ok and not hand_ok and not mk1_neon and mk2_neon and not cutter,
          f"{hand:.1f} s by hand, {drill:.2f} s with Mk3")
    stand(g, p, 30.5, 30.5)
    w.set(32, 30, 10, ID["soil"])
    p.selected = 0
    g.action(0, {"type": "dig_start", "x": 32, "y": 30, "z": 10})
    for _ in range(90):
        g.step({})
    g.action(0, {"type": "dig", "x": 32, "y": 30, "z": 10})
    for _ in range(120):  # (the soil it dropped, picked up by walking near it)
        g.step({0: (0.6, 0.0, 0)})
    check("What a block drops is picked up as you walk near it", items.count_of(p.inv, I["soil"]) == 1,
          str([sl for sl in p.inv if sl]))
    stand(g, p, 40.5, 40.5)
    p.inv[0] = items.new_slot(I["glowstick"], 4)
    p.selected = 0
    g.action(0, {"type": "right", "x": 42, "y": 40, "z": 9, "face": [0, 0, 1]})
    check("A Glowstick put down lights the blocks round it", w.get(42, 40, 10) == ID["glowstick"] and w.glow[44, 40, 10] >= 8,
          f"{B.BLOCKS[w.get(42, 40, 10)]['key']} {w.glow[44, 40, 10]}")
    p.inv[1] = items.new_slot(I["boards"], 10)
    p.selected = 1
    g.action(0, {"type": "right", "x": 40, "y": 40, "z": 9, "face": [0, 0, 1]})
    check("You can't put a block where you stand", w.get(40, 40, 10) == 0)
    p.inv[2] = items.new_slot(I["door"], 1)
    p.selected = 2
    g.action(0, {"type": "right", "x": 38, "y": 40, "z": 9, "face": [0, 0, 1]})
    placed = w.get(38, 40, 10) == ID["door"] and w.get(38, 40, 11) == ID["door_top"]
    g.action(0, {"type": "right", "x": 38, "y": 40, "z": 10, "face": [1, 0, 0]})
    opened = w.get_meta(38, 40, 10) & 4
    check("A door goes in two blocks high, and a right click opens it", placed and opened,
          f"{B.BLOCKS[w.get(38, 40, 10)]['key']} {w.get_meta(38, 40, 10)}")
    w.set(44, 42, 10, ID["refinery"])
    rf = craft_game.new_refinery()
    rf["slots"][0] = items.new_slot(ID["iron_ore"], 2)
    rf["slots"][1] = items.new_slot(I["rust"], 2)
    rf["slots"][items.POWER_SLOT] = items.new_slot(I["coal"], 1)
    g.refineries[(44, 42, 10)] = rf
    for _ in range(int(60 * (B.REFINE_SECONDS * 3 + 1))):
        g.step({})
    tray = [s for s in rf["slots"][items.POWER_SLOT + 1:] if s]
    lit = w.get(44, 42, 10) == ID["refinery_on"] or tray
    check("A Refinery with iron ore and 2 Rust in its queue and Coal in its power slot makes 3 Iron ingots, 6 s an "
          "item (2 Rust make one), and lights up while it works", tray and tray[0][0] == I["iron_ingot"] and
          tray[0][1] == 3 and lit and 2.9 < rf["power"] < 3.1, f"{tray} power {rf['power']}")
    p.energy = 40.0
    p.inv[3] = items.new_slot(I["grain_bar"], 1)
    p.selected = 3
    g.action(0, {"type": "use_item"})
    check("Eating a Grain bar gives 25 Energy", 64.9 < p.energy <= 65 and p.inv[3] is None, f"energy {p.energy}")
    p.energy = 30.0  # (no Health coming back while this is measured)
    hp = p.state["hp"]
    stand(g, p, 50.5, 50.5, 16.0)  # (6 blocks: 8 harm a block past 4)
    for _ in range(120):
        g.step({})
    fell = hp - p.state["hp"]
    stand(g, p, 52.5, 50.5, 14.0)  # (4 blocks: safe)
    hp2 = p.state["hp"]
    for _ in range(120):
        g.step({})
    check("A fall of 4 blocks is safe; 6 blocks costs 16 Health", fell == 16 and p.state["hp"] == hp2,
          f"{fell} then {hp2 - p.state['hp']}")
    p.energy = 70.0
    for _ in range(60 * 10):
        g.step({0: (1.0, 0.0, sim.SPRINT_B)})
    ran = 70.0 - p.energy
    check("Energy drains as you run (about 1 a second)", 9.0 < ran < 11.5, f"{ran:.2f} in 10 s")
    g.time = (g.day + 0.75) * g.rules["day_length"]
    stand(g, p, 40.5, 44.5)
    w.set(42, 44, 10, ID["pod"])
    t0 = g.day_t
    g.use_block(0, 42, 44, 10)
    secs = 0
    while g.is_night() and secs < 60 * 60:
        g.step({})
        secs += 1
    for _ in range(30):
        g.step({})
    check("Resting in a Recharge Pod at night (everyone in one) speeds the night by 20 times, and sets your wake "
          "point", not g.is_night() and p.has_pod and 4 * 60 < secs < 60 * 60 and not p.asleep,
          f"from {t0:.2f}: {secs / 60:.1f} s, now {g.day_t:.2f}")
    w2 = flat_world()
    g2 = game_on(w2)
    q = g2.add_player(0, "Wet")
    q.state.update(x=42.5, y=42.5, z=10.0)
    g2.step({})
    q.inv[0] = items.new_slot(I["water_canister"], 1)
    q.selected = 0
    g2.action(0, {"type": "right", "x": 40, "y": 40, "z": 9, "face": [0, 0, 1]})
    for _ in range(60 * 4):
        g2.step({})
    spread = int((w2.blocks == ID["water"]).sum())
    q.inv[0] = items.new_slot(I["canister"], 1)
    q.state.update(x=41.5, y=41.5, z=10.0)
    g2.step({})
    g2.use_block(0, 40, 40, 10)
    for _ in range(60 * 6):
        g2.step({})
    dried = int((w2.blocks == ID["water"]).sum())
    check("Water from a canister flows 4 blocks out (41 blocks), and dries up when the source is taken back",
          spread == 41 and dried == 0, f"{spread} then {dried}")
    w2.set(50, 50, 10, ID["soil"])
    w2.set(50, 50, 11, ID["sand"])
    w2.set(50, 50, 12, ID["sand"])
    q.state.update(x=49.5, y=48.5, z=10.0)
    q.inv[0] = None
    g2.action(0, {"type": "dig_start", "x": 50, "y": 50, "z": 10})
    for _ in range(120):
        g2.step({})
    g2.action(0, {"type": "dig", "x": 50, "y": 50, "z": 10})
    check("Sand falls into the gap under it", w2.get(50, 50, 10) == ID["sand"] and w2.get(50, 50, 11) == ID["sand"]
          and w2.get(50, 50, 12) == 0)
    w2.set(60, 60, 10, ID["overload_cell"])
    q.state.update(x=56.5, y=60.5, z=10.0, vx=0.0, vy=0.0)
    g2.step({})
    g2.use_block(0, 60, 60, 10)
    q.look = (0.0, 0.0)
    q.inv[0] = items.new_slot(I["glitch_shard"], 2)
    g2.action(0, {"type": "drop"})
    for _ in range(60 * 5):
        g2.step({})
    off = w2.get(60, 60, 10) == ID["overload_cell"]
    g2.rules["blasts"] = True
    g2.action(0, {"type": "drop"})
    armed = False
    for _ in range(60 * 5):
        g2.step({})
        armed = armed or bool(g2.overloads)
    gone = w2.get(60, 60, 10) == 0
    holes = sum(1 for dx in range(-3, 4) for dy in range(-3, 4) if w2.get(60 + dx, 60 + dy, 9) == 0)
    check("An Overload Cell isn't lit by a click; a Glitch shard thrown at it arms it only when the lesson allows "
          "Overload Cells; then it pulses, and the blocks round it become their drops",
          off and armed and gone and holes > 4 and g2.items, f"off {off} armed {armed} gone {gone} holes {holes}")


def mob_checks():
    w = W.World("small", 12)
    g = game_on(w, mobs=True)
    p = g.add_player(0, "Dusk")
    g.mobs.age = 100
    g.time = 0.595 * g.rules["day_length"]
    for _ in range(60 * 6):
        g.step({})
    check("The world's first dusk, come round on the clock, is quiet (no rifts)", g.phase() == "dusk" and not g.rifts,
          f"{g.phase()}, {len(g.rifts)} rifts")
    g.time = 1.595 * g.rules["day_length"]
    for _ in range(60 * 25):
        g.step({})
    kinds = {m["kind"] for m in g.mobs.mobs.values()}
    check("The next dusk Glitch rifts open (1 to 3) and send out Glitches", 1 <= len(g.rifts) <= 3 and "glitch" in kinds,
          f"{len(g.rifts)} rifts {kinds}")
    g3 = game_on(W.World("small", 12), mobs=True)
    g3.add_player(0, "Set")
    g3.time = 0.62 * g3.rules["day_length"]
    for _ in range(30):
        g3.step({})
    check("A dusk set by hand on the first day opens rifts all the same", 1 <= len(g3.rifts) <= 3, f"{len(g3.rifts)} rifts")
    rid, r = next(iter(g.rifts.items()))
    x, y, z = r["cells"][0]
    p.state.update(x=x + 0.5, y=y - 1.5, z=z + 1.0)
    g.step({})
    p.inv[0] = items.new_slot(I["patch"], 1)
    p.selected = 0
    g.action(0, {"type": "right", "x": x, "y": y, "z": z, "face": [0, 0, 1]})
    check("A Patch closes a rift (the ground back as it was)", rid not in g.rifts and w.get(x, y, z) != ID["glitch_rift"]
          and p.stats["rifts"] == 1)
    g.mobs.mobs.clear()
    stand(g, p, p.state["x"], p.state["y"], p.state["z"])
    mid = g.mobs.add("glitch", p.state["x"] + 2.5, p.state["y"], p.state["z"])
    hp0 = p.state["hp"]
    for _ in range(120):
        g.step({0: (0.0, 0.0, 0)})
    hurt = p.state["hp"] < hp0
    ex, ey, ez = sim.eye(p.state)
    hits = 0
    while mid in g.mobs.mobs and hits < 20:
        m = g.mobs.mobs[mid]["s"]
        m.update(x=p.state["x"] + 1.0, y=p.state["y"], z=p.state["z"])
        g.mobs.hit(mid, 12, (ex, ey, ez), p)
        hits += 1
    gone = mid not in g.mobs.mobs  # (now: another rift's next Glitch may be given the same number)
    for _ in range(60):
        g.step({0: (0.2, 0.0, 0)})
    check("A Glitch zaps from a few blocks away; four Mk1 Zapper hits beat it, and it drops Glitch shards",
          hurt and gone and p.stats["killed"].get("glitch") == 1 and hits == 4,
          f"hurt {hurt} hits {hits}")
    g.time = (g.day + 0.94) * g.rules["day_length"]
    for _ in range(60 * 2):
        g.step({})
    check("At dawn the rifts seal and pull their Glitches back in", not g.rifts and not any(
        m["kind"] == "glitch" for m in g.mobs.mobs.values()), f"{len(g.rifts)} rifts")
    g2 = game_on(W.World("small", 12), mobs=True)
    q = g2.add_player(0, "Day")
    g2.time = 0.25 * g2.rules["day_length"]
    for _ in range(60 * 20):
        g2.step({})
    kinds = {m["kind"] for m in g2.mobs.mobs.values()}
    check("By day Fluffs and Bleeps wander the turf (no Glitches)", kinds & {"fluff", "bleep"} and "glitch" not in kinds,
          str(kinds))
    fid = g2.mobs.add("fluff", q.state["x"] + 1.5, q.state["y"], q.state["z"])
    q.inv = [None] * items.SLOTS
    q.selected = 0
    g2.action(0, {"type": "use_mob", "target": fid})
    got = items.count_of(q.inv, I["fluff"])
    g2.action(0, {"type": "use_mob", "target": fid})
    again = items.count_of(q.inv, I["fluff"])
    q.inv[0] = items.new_slot(I["zapper_mk1"], 1)
    g2.action(0, {"type": "attack", "target": fid})
    check("Brushing a Fluff with an empty hand gives Fluff (it grows back later); the Zapper won't fire at it",
          1 <= got <= 2 and again == got and g2.mobs.mobs[fid]["s"]["hp"] == 30, f"{got} {again}")


def bot_checks():
    import craft_brain
    import craft_bot
    w = flat_world()
    g = game_on(w)
    g.add_player(0, "Coder")
    w.set(64, 67, 10, ID["dock"])
    g.use_block(0, 64, 67, 10)
    bot = g.bot_of(0)
    bot.facing = 1
    for k in range(1, 12):
        w.set(64, 67 + k, 11, ID["soil"])
    tower = ("def brain(bot, world):\n    if bot.placed >= 5:\n        return 'wait'\n    if bot.below == 'air':\n"
             "        return ('place_down', 'planks')\n    return 'up'\n")  # (planks: an old name, still understood)
    try:
        fn, fname = craft_brain.load_brain(craft_bot.STARTER, "Coder")
        g.bot_brains[0] = craft_brain.Autopilot(fn, fname)
        for _ in range(60 * 30):
            g.step({})
            time.sleep(1 / 120)
            if bot.stats["dug"] >= 10:
                break
        tunnel = bot.stats["dug"]
        g.bot_brains[0].close()
        bot.inv[0] = items.new_slot(I["boards"], 8)
        bot.home()
        bot.cell = [60, 60, 11]
        bot.settle()
        fn, fname = craft_brain.load_brain(tower, "Coder")
        g.bot_brains[0] = craft_brain.Autopilot(fn, fname)
        for _ in range(60 * 30):
            g.step({})
            time.sleep(1 / 120)
            if bot.stats["placed"] >= 5:
                break
        built = sum(1 for z in range(9, 18) if w.get(60, 60, z) == ID["boards"])
        g.bot_brains[0].close()
        bad = "def brain(bot, world):\n    return bot.nothing_here\n"
        fn, fname = craft_brain.load_brain(bad, "Coder")
        g.bot_brains[0] = craft_brain.Autopilot(fn, fname)
        for _ in range(60):
            g.step({})
            time.sleep(1 / 120)
        error = g.bot_brains[0].error
        g.bot_brains[0].close()
        g.rules["blasts"] = True
        bot.home()
        bot.facing = 0
        w.set(65, 67, 11, ID["overload_cell"])
        arm = "def brain(bot, world):\n    if bot.front == 'overload_cell':\n        return ('use', 'overload_cell')\n    return 'wait'\n"
        fn, fname = craft_brain.load_brain(arm, "Coder")
        g.bot_brains[0] = craft_brain.Autopilot(fn, fname)
        for _ in range(60 * 3):
            g.step({})
            time.sleep(1 / 120)
            if g.overloads:
                break
        armed = bool(g.overloads)
        g.bot_brains[0].close()
    finally:
        for b in g.bot_brains.values():
            if b is not None:
                b.close()
    check("A Craft Bot's brain runs safely in its own process: the starter digs a tunnel of 10, another builds a "
          "tower (an old block name still works), a brain with a mistake stops with its line, and ('use', "
          "'overload_cell') arms a Cell", tunnel >= 10 and built >= 5 and error and "line 2" in error and armed,
          f"dug {tunnel}, tower {built}, error {error}, armed {armed}")
    try:
        craft_brain.load_brain("import os\ndef brain(bot, world):\n    return 'wait'\n", "Coder")
        refused = False
    except craft_brain.BrainError:
        refused = True
    check("A brain that imports os is refused before it runs", refused)


def mods_checks():
    import craft_mods
    problems = craft_mods.use_mods()
    bp = next((b for b in items.blueprints() if b["makes"] == "club_block"), None)
    check("The mods' block and blueprint are in the game (soil and sand build two Club blocks)",
          not problems and "club_block" in ID and bp is not None and bp["count"] == 2, f"{problems} {bp}")
    bad = craft_mods.check_block({"key": "Bad Key", "name": "", "colour": [300, 0, 0], "hard": 99, "light": 20, "tool": "spoon"})
    check("A learner's block with mistakes is refused, each one said", len(bad) == 6, "; ".join(bad))
    bad = craft_mods.check_blueprint({"makes": "nothing", "count": 99, "parts": {"stuff": 0}, "station": "moon"})
    old = craft_mods.check_blueprint({"makes": "planks", "count": 4, "parts": {"log": 1}})
    check("A learner's blueprint with mistakes is refused, each one said; one with old names (planks) still loads",
          len(bad) == 5 and not old, "; ".join(bad) + f" | {old}")


def save_checks():
    w = W.World("small", 21)
    w.set(10, 10, 30, ID["brick"])
    folder = os.path.join(TMP, "save")
    w.save(folder, {"time": 123.0})
    back, extra = W.World.load(folder)
    check("A world saved and loaded again is the same, with the game's own things",
          back is not None and (back.blocks == w.blocks).all() and extra.get("time") == 123.0 and back.heaps == w.heaps)
    with open(os.path.join(folder, "world.json"), encoding="utf-8") as f:
        info = json.load(f)
    info["version"] = 1
    with open(os.path.join(folder, "world.json"), "w", encoding="utf-8") as f:
        json.dump(info, f)
    old, _ = W.World.load(folder)
    import craft_game
    p = craft_game.Player(0, "Old", (5.0, 5.0, 11.0))
    p.load({"inv": [[3, 5, 0]] + [None] * 35, "stats": {"deaths": 2}})
    check("A save from before CHANGE 207 is made again, not misread (an old world, an old inventory)",
          old is None and not any(p.inv) and p.stats["deaths"] == 2)


# ---------- the server ----------
def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def stop(proc):
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        proc.kill()


def start_server(port, extra=(), data=TMP):
    log = open(os.path.join(TMP, f"server_{port}.log"), "w")
    proc = subprocess.Popen([PY, "craft_server.py", "--port", str(port), "--seed", "8", "--size", "small", *extra],
                            stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ, CRAFTLAB_DATA=data))
    for _ in range(300):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return proc
        except OSError:
            if proc.poll() is not None:
                raise RuntimeError("the server stopped: " + open(log.name).read()[-1500:])
            time.sleep(0.1)
    raise RuntimeError("the server didn't start")


class Client:
    def __init__(self, port, name, password=None, teacher=False):
        from websockets.sync.client import connect
        self.ws = connect(f"ws://127.0.0.1:{port}", open_timeout=10, max_size=None, compression=None)
        hello = {"type": "hello", "name": name, "code": "TEACH99" if teacher else "CLUB42",
                 "version": craft_version.VERSION}
        if password:
            hello["password"] = password
        self.ws.send(json.dumps(hello))
        self.seen, self.snaps = [], 0
        self.welcome = self.wait("welcome", 15)
        self.wait("world", 30)

    def send(self, m):
        self.ws.send(json.dumps(m))

    def wait(self, kind, seconds=10, test=None):
        end = time.time() + seconds
        while True:
            for i, m in enumerate(self.seen):
                if m.get("type") == kind and (test is None or test(m)):
                    return self.seen.pop(i)
            left = end - time.time()
            if left <= 0:
                return None
            try:
                raw = self.ws.recv(timeout=left)
            except TimeoutError:
                return None
            if isinstance(raw, bytes):
                if raw[:1] == b"\x01":
                    self.snaps += 1
                    self.last_snap = raw
                continue
            self.seen.append(json.loads(raw))

    def close(self):
        self.ws.close()


def server_checks():
    port = free_port()
    server = start_server(port)
    try:
        sam = Client(port, "Sam", "secret12")
        amy = Client(port, "Amy", "secret34")
        inv = sam.wait("inventory", 5)
        me = sam.welcome["me"]
        sam.wait("nothing", 1.5)  # (a second and a half of snapshots)
        check("Two learners log in, are each sent the world and their inventory, and see snapshots",
              sam.welcome and amy.welcome and inv is not None and sam.wait("roster", 3) is not None and sam.snaps > 0,
              f"{sam.welcome is not None} {inv is not None} snaps {sam.snaps}")
        from engine import wire
        schema = wire.Schema("craft", sim.SCHEMA_FIELDS)
        snap = wire.unpack_snapshot(schema, sam.last_snap)
        mine = next(e for e in snap["entities"] if e["id"] == me)
        x, y, z = int(math.floor(mine["x"])), int(math.floor(mine["y"])), int(math.floor(mine["z"]))
        sam.send({"type": "dig_start", "x": x + 1, "y": y, "z": z - 1})
        time.sleep(4.5)
        sam.send({"type": "dig", "x": x + 1, "y": y, "z": z - 1})
        changed = amy.wait("blocks", 5, test=lambda m: [x + 1, y, z - 1] in [c[:3] for c in m["list"]])
        far = (x, y, 2)  # (deep under your feet: out of reach)
        sam.send({"type": "dig_start", "x": far[0], "y": far[1], "z": far[2]})
        time.sleep(0.2)
        sam.send({"type": "dig", "x": far[0], "y": far[1], "z": far[2]})
        back = sam.wait("blocks", 5, test=lambda m: list(far) in [c[:3] for c in m["list"]])
        check("A dig in reach changes the block for everyone; one out of reach is refused and sent back",
              changed is not None and back is not None and back["list"][0][3] != 0, f"{changed} {back}")
        teacher = Client(port, "Mr P", teacher=True)
        teacher.send({"type": "kit"})
        got = sam.wait("inventory", 5, test=lambda m: any(s and s[0] == I["dock"] for s in m["inv"]))
        teacher.send({"type": "time"})
        state = sam.wait("state", 5)
        check("The teacher's K gives everyone a Bot dock, T moves the time of day on", got is not None and state is not None)
        bps = sam.wait("blueprints", 5) or {"list": []}
        rod = next((i for i, bp in enumerate(bps["list"]) if bp["makes"] == "rod"), None)
        sam.send({"type": "build", "bp": rod})
        made = sam.wait("inventory", 5, test=lambda m: any(s and s[0] == I["rod"] for s in m["inv"]))
        check("Blueprints on the server: the list is sent, and BUILD makes Rods from the teacher's Boards",
              rod is not None and made is not None, f"rod {rod}")
        sam.send({"type": "design", "design": {"name": "Digger", "colour": [60, 190, 90],
                                               "points": {"dig": 50, "build": 25, "speed": 25}}})
        res = sam.wait("design_result", 5)
        mm = sam.wait("missions", 5, test=lambda m: "1a" in (m.get("done") or {}) or "1a" in json.dumps(m))
        check("A Bot built in the garage completes lesson 1's string, integer and list missions",
              res and res["ok"] and mm is not None, f"{res}")
        sam.close()
        amy.close()
        teacher.close()
    finally:
        stop(server)


# ---------- two windows ----------
def online_checks():
    port = free_port()
    data = os.path.join(TMP, "online")  # (its own class: the server checks' Amy has another password)
    os.makedirs(data, exist_ok=True)
    server = start_server(port, data=data)
    try:
        host = f"ws://127.0.0.1:{port}"
        env = dict(os.environ, APPDATA=TMP, CLUBCODERS_LAG="60,15")
        wins = []
        for who in ("Sam", "Amy"):
            shot = os.path.join(TMP, f"online_{who}.png")
            wins.append((who, shot, subprocess.Popen([PY, "craft_client.py", "--host", host, "--name", who, "--password",
                                                      "secret12", "--offscreen", "--no-sound", "--demo", "--gfx", "low",
                                                      "--after", "14", "--screenshot", shot],
                                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)))
        notes = []
        for who, shot, w in wins:
            out, _ = w.communicate(timeout=300)
            corr = [int(line.split()[-1]) for line in out.splitlines() if line.startswith("perf corr")]
            notes.append((who, w.returncode, os.path.exists(shot), corr[-1] if corr else None, out[-400:]))
        ok = all(rc == 0 and pic and c is not None and c <= 25 for _, rc, pic, c, _ in notes)
        check("Two windows on one server over pretend school Wi-Fi (60 ms, 15 ms jitter): each walks and jumps for "
              "14 s with few corrections", ok, str([(n, rc, pic, c) for n, rc, pic, c, _ in notes]) +
              " " + " ".join(o for *_, o in notes if True)[:600])
    finally:
        stop(server)


# ---------- pictures ----------
def picture(name, extra, after=3.0):
    shot = os.path.join(TMP, f"{name}.png")
    r = subprocess.run([PY, "craft_client.py", "--offline", "--seed", "11", "--offscreen", "--no-sound", "--after",
                        str(after), "--screenshot", shot] + extra, capture_output=True, text=True, timeout=300,
                       env=dict(os.environ, APPDATA=os.path.join(TMP, "appdata_" + name)))
    return shot, r


def tab_checks():
    """(CHANGE 206) The side panel of lesson tabs (Tab), each drawn from a server's messages: a learner's Mission and
    AI card, the teacher's Controls; offline the Settings."""
    port = free_port()
    data = os.path.join(TMP, "tabs")
    os.makedirs(data, exist_ok=True)
    server = start_server(port, data=data)
    try:
        host = f"ws://127.0.0.1:{port}"
        runs = [("missions", ["--host", host, "--name", "Kit", "--password", "secret56", "--tab", "missions"]),
                ("ai", ["--host", host, "--name", "Kit", "--password", "secret56", "--tab", "ai"]),
                ("teacher", ["--host", host, "--teacher", "--tab", "teacher"]),
                ("offline", ["--offline", "--tab", "settings"])]
        bad = []
        for what, extra in runs:
            shot = os.path.join(TMP, f"tab_{what}.png")
            r = subprocess.run([PY, "craft_client.py", *extra, "--offscreen", "--no-sound", "--gfx", "low", "--after",
                                "4", "--screenshot", shot], capture_output=True, text=True, timeout=300,
                               env=dict(os.environ, APPDATA=os.path.join(TMP, "appdata_tab_" + what)))
            out = r.stdout + r.stderr
            if r.returncode != 0 or "Traceback" in out or not os.path.exists(shot):
                bad.append(f"{what}: {out[-300:]}")
        check("The lesson tabs (Tab): a learner's Mission and AI card, the teacher's Controls, offline the Settings",
              not bad, " | ".join(bad))
    finally:
        stop(server)


def brightness(path):
    from PIL import Image, ImageStat
    im = Image.open(path).convert("L").crop((0, 0, 1600, 700))
    return ImageStat.Stat(im).mean[0]


def window_checks():
    pose = ["--pose", "96.5,80.5,40,60,-25"]
    notes, ok = [], True
    for tier in ("mesh", "lines", "basic", "low", "medium", "high", "ultra"):
        shot, r = picture(f"tier_{tier}", ["--gfx", tier] + pose)
        good = r.returncode == 0 and os.path.exists(shot) and "Traceback" not in r.stdout + r.stderr
        b = brightness(shot) if good else 0
        good = good and (2 < b < 60 if tier in ("mesh", "lines") else 60 < b < 230)
        ok &= good
        notes.append(f"{tier} {b:.0f}" + ("" if good else " " + (r.stdout + r.stderr)[-300:]))
    check("Every graphics tier draws the island (mesh and lines: lines on black)", ok, "; ".join(notes))
    script = os.path.join(TMP, "night.json")
    with open(script, "w") as f:
        json.dump([["time", 0.8], ["set", "glowstick", 3, -2, 0], ["set", "lumen", 6, 0, 0], ["wait", 1.5]], f)
    shot, r = picture("night", ["--gfx", "medium", "--script", script, "--no-mobs"], 2.5)
    b = brightness(shot) if os.path.exists(shot) else 0
    check("Night is dark but Glowsticks and Lumen blocks light it", r.returncode == 0 and 3 < b < 45, f"{b:.0f}")
    script = os.path.join(TMP, "inv.json")
    with open(script, "w") as f:
        json.dump([["give", "log", 6], ["give", "drill_mk2", 1], ["give", "iron_vest", 1], ["wait", 0.3],
                   ["screen", "inventory"], ["wait", 1]], f)
    shot, r = picture("inventory", ["--gfx", "low", "--script", script] + pose, 2.0)
    out = r.stdout + r.stderr
    check("The Backpack opens with what you carry", r.returncode == 0 and os.path.exists(shot) and "Traceback" not in out,
          out[-300:])
    script = os.path.join(TMP, "blueprints.json")
    with open(script, "w") as f:
        json.dump([["give", "log", 6], ["give", "rubble", 4], ["wait", 0.3], ["screen", "blueprints"], ["wait", 1]], f)
    shot, r = picture("blueprints", ["--gfx", "low", "--script", script] + pose, 2.0)
    out = r.stdout + r.stderr
    check("The Blueprints tab lists what you can build", r.returncode == 0 and os.path.exists(shot) and
          "Traceback" not in out, out[-300:])
    script = os.path.join(TMP, "bot.json")
    with open(script, "w") as f:
        json.dump([["dock", 3, 0], ["wait", 0.5], ["close"], ["call", "upload_brain"], ["wait", 1.0],
                   ["call", "toggle_autopilot"], ["view", "behind"], ["wait", 6]], f)
    shot, r = picture("bot", ["--gfx", "medium", "--script", script, "--no-mobs"], 9)
    out = r.stdout + r.stderr
    check("A Craft Bot comes out of its dock and runs the starter brain in the window", r.returncode == 0
          and os.path.exists(shot) and "Traceback" not in out, out[-400:])


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("quick", "all"):
        for fn in (world_checks, mesh_checks, sim_checks, blueprint_checks, suit_checks, rules_checks, mob_checks,
                   bot_checks, mods_checks, save_checks):
            run(fn.__name__, fn)
    if what in ("server", "all"):
        run("server_checks", server_checks)
    if what in ("online", "all"):
        run("online_checks", online_checks)
        run("tab_checks", tab_checks)
    if what in ("window", "all"):
        run("window_checks", window_checks)
    failed = [n for n, ok, _ in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} passed  (pictures and data: {TMP})")
    sys.exit(1 if failed else 0)
