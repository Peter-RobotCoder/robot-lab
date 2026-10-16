"""Checks on Robot Lab's graphics tiers (CHANGE 145: mesh to ultra), run after changing rw_gfx.py, robot_models.py,
arena_models.py or lab_textures.py.

    python gfx_test.py

1. the ultra arena's holes are the physics' (lab_sim.floor_holes) for every user mod that cuts the floor
2. nothing of the ultra arena stands on the floor inside the cage, and nothing new stands between the cameras
   outside the cage and the arena (only the posts, as on the lower tiers), nor rises above the lower tiers' crowd
3. the ultra robots stay where the lower tiers' robots are (each node's pieces inside its parts, give or take a few
   centimetres), for every weapon, at the smallest, standard and largest sizes and as Resident Robots
4. the models' files read back to the window's numbers (model_kit's packing) and the textures are made
5. every tier draws the preview arena offscreen (mesh and lines with their lines, ultra with its arena and robots)
Exit code 0 = all fine.
"""
import math
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import lab_version  # noqa: E402,F401  (the engine package on the path)
import arena_models as am  # noqa: E402
import lab_sim as sim  # noqa: E402
import robot_models as rm  # noqa: E402
from engine import model_kit as mk  # noqa: E402

PY = sys.executable
TMP = tempfile.mkdtemp(prefix="robotlab_gfx_")
results = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, f"{time.time() - t0:.0f} s"))
    except Exception as e:  # report and carry on, so every problem is listed
        results.append((name, False, f"{type(e).__name__}: {e}"[-500:]))


def holes():
    for spike in (False, True):
        for flame in (False, True):
            mods = {"spike_pit": spike, "flame_pit": flame}
            assert am.floor_holes(spike, flame) == sim.floor_holes(None, mods), mods
            assert sorted(am.floor_rects(am.floor_holes(spike, flame))) == sorted(sim.floor_rects(None, mods)), mods
            names = {p.material for p in am.made()["groups"][am.floor_group(spike, flame)]}
            assert names == {"floor", "chrome"}, names
    assert am.SPIKES == sim.Arena.SPIKES and am.GUTTER == sim.Arena.GUTTER and am.ARENA == sim.ARENA


def clear_views():
    made = am.made()
    inside = sim.ARENA / 2 - 0.01
    for name, parts in made["groups"].items():
        for p in parts:
            for x, y, z in p.p:
                if abs(x) < inside and abs(y) < inside:  # (on the floor, inside the cage)
                    if name.startswith("floor") or name == "scars":
                        assert z < 0.006, (name, p.material, x, y, z)
                    elif name not in ("rig", "roof"):
                        raise AssertionError(("inside the cage", name, p.material, x, y, z))
                    else:
                        assert z > 8.4, ("the rig hangs low", x, y, z)
                # outside the cage, between the cameras and the arena: the posts only (the lower tiers' posts are
                # here too), the towers in the corners, and the rig and the screen high up
                d = max(abs(x), abs(y))
                if sim.ARENA / 2 + 0.5 < d < sim.ARENA / 2 + 2.5 and 1.32 < z < 6.6 and name != "hall":  # (to the stands)
                    near_post = min(abs(abs(x) - 10.25) + abs(y - round(y / 2) * 2), abs(abs(y) - 10.25) + abs(x - round(x / 2) * 2))
                    tower = math.hypot(abs(x) - 12.5, abs(y) - 12.5) < 0.9
                    assert near_post < 0.2 or tower, ("in the cameras' view", name, p.material, x, y, z)
    # nothing out in the hall rises over the lower tiers' crowd (4.8 m) within 20 m but the towers, rig, screen, hall
    for name in ("stands", "venue_floor", "venue_floor_open", "cage"):
        for p in made["groups"][name]:
            assert max(q[2] for q in p.p) < 4.8, (name, p.material, max(q[2] for q in p.p))
    for shape, rows in made["instances"].items():
        tall = max(q[2] for part in made["shapes"][shape] for q in part.p)
        for x, y, z, h, s, *_ in rows:
            assert z + tall * s < 4.85, (shape, x, y, z, tall * s)
            assert max(abs(x), abs(y)) > sim.ARENA / 2 + 2.5, (shape, x, y)


def rotate(p, hpr):
    """A point turned by Panda's heading (about z), pitch (about x) and roll (about y), in Panda's order."""
    h, pp, r = (math.radians(a) for a in hpr)
    x, y, z = p
    x, z = x * math.cos(r) + z * math.sin(r), -x * math.sin(r) + z * math.cos(r)   # roll about y
    y, z = y * math.cos(pp) - z * math.sin(pp), y * math.sin(pp) + z * math.cos(pp)  # pitch about x
    x, y = x * math.cos(h) - y * math.sin(h), x * math.sin(h) + y * math.cos(h)    # heading about z
    return (x, y, z)


def robots_in_place():
    kit = rm.kit()
    for weapon in ("wedge", "spinner", "drum", "hammer", "flame", "laser", "chainsaw", "vdisc"):
        for size, house in ((0.8, False), (1.0, False), (1.2, False), (1.6, True)):
            sh = sim.shapes(weapon, size, house)
            h = sh["half"]
            box = {}
            for node, piece, pos, hpr, scale in rm.layout(weapon, size / sh["k"], house, sh):
                for part in kit[piece]:
                    for q in part.p[::7]:
                        q = rotate((q[0] * scale[0], q[1] * scale[1], q[2] * scale[2]), hpr)
                        q = (q[0] + pos[0], q[1] + pos[1], q[2] + pos[2])
                        b = box.setdefault(node, [list(q), list(q)])
                        for k in range(3):
                            b[0][k], b[1][k] = min(b[0][k], q[k]), max(b[1][k], q[k])
            lo, hi = box["chassis"]
            # the body: the hull's box, its bumpers and lamps a few centimetres proud, the weapon's mounts forward
            assert lo[0] > -h.x - 0.06 and hi[0] < h.x + 0.06, (weapon, size, "body across", lo, hi)
            # (under: never through the floor, which is the wheels' radius under their axles, 8 cm up the body; the
            # disc's slot plates on a small robot come lowest, as the lower tiers' do)
            wr, ww = (rm.HOUSE_WHEEL if house else rm.WHEEL)
            assert lo[1] > -h.y - 0.12 and lo[2] > 0.08 - wr - 0.02, (weapon, size, "body back or under", lo)
            for i in range(4):
                lo, hi = box[f"wheel{i}"]
                assert max(abs(v) for v in lo[1:] + hi[1:]) <= wr + 0.002, (weapon, "wheel radius", lo, hi)
                assert max(abs(lo[0]), abs(hi[0])) <= ww + 0.012, (weapon, "wheel width", lo, hi)
            lo, hi = box["deck"]
            assert lo[2] > -0.04 * size - 0.01 and hi[2] < 0.1 * size, (weapon, size, "deck", lo, hi)
            for side in ("skirt_r", "skirt_l"):
                lo, hi = box[side]
                assert hi[2] < 0.03 and lo[2] > -h.z * 1.45 and max(abs(lo[0]), abs(hi[0])) < 0.06, (weapon, side, lo, hi)
            lo, hi = box["weapon"]
            # the weapon: inside the physics' shape for it, give or take its machined detail
            if weapon == "wedge":
                assert hi[0] <= sh["plate"].x + 0.02 and hi[1] <= 2 * sh["plate"].y + 0.02 and lo[1] > -0.06, (lo, hi)
            elif weapon == "spinner":
                assert hi[0] <= sh["bar"].x * 1.03 + 0.01 and abs(lo[2]) < 0.09, (lo, hi)
            elif weapon in ("drum", "vdisc"):
                r = sh["drum"][0] if weapon == "drum" else sh["disc"][0]
                assert max(hi[1], hi[2], -lo[1], -lo[2]) < r * 1.35 + 0.01, (weapon, lo, hi)
            elif weapon == "hammer":
                assert hi[1] < 2 * sh["arm"].y + sh["head"].y + 0.03, (lo, hi)


def files_read_back():
    for parts in list(rm.kit().values())[:6] + list(am.made()["groups"].values())[:3]:
        for part in parts[:2]:
            packed = part.packed()
            pos, nrm, uv, col, alpha, idx = mk.unpack(packed)
            assert len(pos) == 3 * len(part.p) and idx == part.idx, part.name
            for i in range(0, len(part.p), 41):
                assert all(abs(a - b) < 0.003 + 1e-4 * max(1.0, abs(b)) for a, b in zip(pos[i * 3:i * 3 + 3], part.p[i])), part.name
                assert all(abs(a - b) < 0.012 for a, b in zip(nrm[i * 3:i * 3 + 3], part.n[i])), part.name
    model = rm.robot()
    assert set(model["pieces"]) == set(rm.PIECES) and all(p["material"] in rm.ROLES for v in model["pieces"].values() for p in v)
    arena = am.arena()
    assert all(p["material"] in am.MATERIALS for v in list(arena["groups"].values()) + list(arena["shapes"].values()) for p in v)
    import lab_textures
    folder = lab_textures.ensure()
    for name in lab_textures.SETS:
        for kind in ("albedo", "mr", "normal"):
            assert os.path.getsize(os.path.join(folder, f"{name}_{kind}.png")) > 1000, (name, kind)


def tiers_draw():
    from PIL import Image
    for tier in ("mesh", "lines", "basic", "ultra"):
        shot = os.path.join(TMP, f"{tier}.png")
        r = subprocess.run([PY, "lab_preview.py", "--gfx", tier, "--offscreen", "--camera", "centre", "--after", "2",
                            "--screenshot", shot], cwd=HERE, capture_output=True, text=True, timeout=240)
        assert r.returncode == 0 and os.path.exists(shot), (tier, (r.stdout + r.stderr)[-500:])
        img = Image.open(shot).convert("RGB").resize((160, 90))
        px = [img.getpixel((x, y)) for y in range(90) for x in range(160)]
        if tier in ("mesh", "lines"):  # black, with lines in the line colour (phosphor green)
            dark = sum(1 for p in px if max(p) < 30) / len(px)
            green = sum(1 for p in px if p[1] > 90 and p[1] > p[0] + 30) / len(px)
            assert dark > 0.3 and green > 0.03, (tier, dark, green)
        else:
            lit = sum(1 for p in px if sum(p) > 120) / len(px)
            assert lit > 0.5, (tier, lit)
        assert "arena built in" in r.stdout and f"at {tier}" in r.stdout, r.stdout[-300:]


if __name__ == "__main__":
    check("The ultra floor's holes are the physics'", holes)
    check("Nothing of the ultra arena in the cage or in the cameras' views", clear_views)
    check("The ultra robots stay where the lower tiers' robots are", robots_in_place)
    check("The models' files read back; the textures are made", files_read_back)
    check("Every tier draws the arena offscreen", tiers_draw)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + (f" ({note})" if ok else ":\n    " + note))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
