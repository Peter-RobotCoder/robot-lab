"""Checks on Fight Lab's graphics tiers (CHANGE 147: mesh to ultra), run after changing fight_gfx.py, fight_model.py,
fight_models.py, stage_models.py or fight_textures.py.

    python gfx_test.py

1. the ultra fighters stay where the lower tiers' fighters are (each joint's pieces inside its parts, give or take a
   few centimetres), for the robot, the martial artist and the four bosses
2. nothing of an ultra ring stands over its canvas inside the ring (where the fighters move), at the smallest,
   standard and largest ring sizes, with ropes and with an open edge; the canvas reaches the ring's edge
3. nothing of the ultra hall stands on the rings or between the rings and the stands but the floor, the rig's towers
   (where the lower tiers' are) and what hangs over 7.5 m; the stands, fans and screens stay outside the hall
4. the models' files read back to the window's numbers (model_kit's packing) and the textures are made
5. every tier draws the preview offscreen (mesh and lines with their lines, the skinned fighters' too; ultra with its
   hall and fighters)
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
import fight_version  # noqa: E402
sys.path.insert(0, fight_version.ENGINE_HOME)  # (the engine package)
import fight_models as fm  # noqa: E402
import fight_sim as sim  # noqa: E402
import stage_models as stm  # noqa: E402
from engine import model_kit as mk  # noqa: E402

PY = sys.executable
TMP = tempfile.mkdtemp(prefix="fightlab_gfx_")
results = []


def check(name, fn):
    t0 = time.time()
    try:
        fn()
        results.append((name, True, f"{time.time() - t0:.0f} s"))
    except Exception as e:  # report and carry on, so every problem is listed
        results.append((name, False, f"{type(e).__name__}: {e}"[-500:]))


def rotate(p, hpr):
    """A point turned by Panda's heading (about z), pitch (about x) and roll (about y), in Panda's order."""
    h, pp, r = (math.radians(a) for a in hpr)
    x, y, z = p
    x, z = x * math.cos(r) + z * math.sin(r), -x * math.sin(r) + z * math.cos(r)   # roll about y
    y, z = y * math.cos(pp) - z * math.sin(pp), y * math.sin(pp) + z * math.cos(pp)  # pitch about x
    x, y = x * math.cos(h) - y * math.sin(h), x * math.sin(h) + y * math.cos(h)    # heading about z
    return (x, y, z)


class NoLook:
    """fight_gfx's materials, for building the lower tiers' fighters with no window (their shapes are all we need)."""
    quality = "high"

    def apply(self, np_, *args, **kwargs):
        return np_


def fighters_in_place():
    from panda3d.core import NodePath
    import fight_gfx
    fight_gfx._state.update(mats=NoLook(), quality="high")
    kit = fm.kit()
    designs = [sim.default_design("Robo", body="robot"), sim.default_design("Kai", body="human")]
    designs += [sim.boss_design(n) for n in sim.BOSS_BY_NAME]
    margin = 0.03  # (machined detail and padding a little proud of the lower tiers' boxes)
    for d in designs:
        fv = fight_gfx.FighterVisual(NodePath("test"), d)
        body = "robot" if fv.robot else "human"
        box = {}
        for joint, piece, pos, hpr, scale in fm.layout(body, d.get("model")):
            for part in kit[piece]:
                for q in part.p[::5]:
                    q = rotate((q[0] * scale[0], q[1] * scale[1], q[2] * scale[2]), hpr)
                    q = (q[0] + pos[0], q[1] + pos[1], q[2] + pos[2])
                    b = box.setdefault(joint, [list(q), list(q)])
                    for k in range(3):
                        b[0][k], b[1][k] = min(b[0][k], q[k]), max(b[1][k], q[k])
        for joint, (lo, hi) in box.items():
            node = fv.nodes[joint]
            parts = [c for c in node.getChildren() if c.getName() in ("geo", "glow")]
            pts = [c.getTightBounds(node) for c in parts]
            low = [min(p[0][k] for p in pts) - margin for k in range(3)]
            high = [max(p[1][k] for p in pts) + margin for k in range(3)]
            assert all(low[k] <= lo[k] and hi[k] <= high[k] for k in range(3)), \
                (d["name"], joint, [round(v, 3) for v in lo + hi], [round(v, 3) for v in low + high])
        fv.destroy()
    fight_gfx._state.clear()


def ring_parts(R, roped):
    """An ultra ring's parts placed for radius R, about the origin (as fight_gfx.StageVisual.ultra_ring)."""
    made = stm.made()["ring"]
    out = []
    for piece, pos, hpr, scale, grow in stm.ring_layout(R, roped):
        for p in made[piece]:
            h = math.radians(hpr[0])
            for x, y, z in p.p:
                r = math.hypot(x, y)
                if grow and r > 1e-9:
                    x, y = x * (r + grow) / r, y * (r + grow) / r
                x, y, z = x * scale[0], y * scale[1], z * scale[2]
                out.append((piece, p.material, pos[0] + math.cos(h) * x - math.sin(h) * y,
                            pos[1] + math.sin(h) * x + math.cos(h) * y, pos[2] + z))
    return out


def rings_clear():
    for R in (3.0, 4.5, 6.5):
        for roped in (True, False):
            pts = ring_parts(R, roped)
            canvas_edge = 0.0
            for piece, material, x, y, z in pts:
                r = math.hypot(x, y)
                if r < R - 0.005:
                    assert z < 0.005, ("over the canvas inside the ring", R, roped, piece, material, round(r, 3), z)
                if material == "canvas":
                    canvas_edge = max(canvas_edge, r)
            assert canvas_edge >= R, (R, roped, "the canvas stops short of the ring's edge", canvas_edge)
            if roped:  # the ropes' middles just outside the ring, as the lower tiers'
                rope = [math.hypot(x, y) for piece, _, x, y, z in pts if piece == "rope"]
                assert min(rope) > R + 0.0, (R, min(rope))


def hall_clear():
    made = stm.made()
    rect = (stm.X0, stm.Y0, stm.X1, stm.Y1)
    towers = [(x, y) for x in (stm.X0, stm.X1) for y in (0.0, 16.0)]
    for name, parts in made["groups"].items():
        for p in parts:
            for x, y, z in p.p:
                inside = rect[0] < x < rect[2] and rect[1] < y < rect[3]
                if name in ("stands", "screens"):
                    assert not inside, ("in the hall", name, p.material, x, y, z)
                    assert z < 8.1, (name, p.material, z)  # (the screens' top as the lower tiers', the stands lower)
                elif name == "floor":
                    assert z <= stm.FLOOR_Z + 0.025, (name, p.material, z)
                elif name == "rig":
                    tower = min(math.hypot(x - tx, y - ty) for tx, ty in towers) < 0.8
                    assert z > 7.5 or tower, ("the rig hangs low", x, y, z)
                elif inside:  # (the hall's walls and roof are far out and high up)
                    assert z > 7.5, (name, p.material, x, y, z)
    for shape, rows in made["instances"].items():
        tall = max(q[2] for part in made["shapes"][shape] for q in part.p)
        for x, y, z, h, s, *_ in rows:
            assert not (rect[0] < x < rect[2] and rect[1] < y < rect[3]), (shape, x, y)
            assert z + tall * s < 3.4, (shape, x, y, z, tall * s)


def files_read_back():
    for parts in list(fm.kit().values())[:6] + list(stm.made()["ring"].values())[:3]:
        for part in parts[:2]:
            packed = part.packed()
            pos, nrm, uv, col, alpha, idx = mk.unpack(packed)
            assert len(pos) == 3 * len(part.p) and idx == part.idx, part.name
            for i in range(0, len(part.p), 41):
                assert all(abs(a - b) < 0.003 + 1e-4 * max(1.0, abs(b)) for a, b in zip(pos[i * 3:i * 3 + 3], part.p[i])), part.name
                assert all(abs(a - b) < 0.012 for a, b in zip(nrm[i * 3:i * 3 + 3], part.n[i])), part.name
    model = fm.fighter()
    assert set(model["pieces"]) == set(fm.PIECES) and all(p["material"] in fm.ROLES for v in model["pieces"].values() for p in v)
    stage = stm.stage()
    assert all(p["material"] in stm.MATERIALS for d in ("ring", "groups", "shapes") for v in stage[d].values() for p in v)
    import fight_textures
    folder = fight_textures.ensure()
    for name in fight_textures.SETS:
        for kind in ("albedo", "mr", "normal"):
            assert os.path.getsize(os.path.join(folder, f"{name}_{kind}.png")) > 1000, (name, kind)


def tiers_draw():
    from PIL import Image
    for tier, view in (("mesh", ["--camera", "ring"]), ("lines", ["--closeup", "3"]), ("basic", ["--camera", "fight"]),
                       ("ultra", ["--camera", "ring", "--hazards", "ropes,electric_ropes"])):
        shot = os.path.join(TMP, f"{tier}.png")
        r = subprocess.run([PY, "fight_preview.py", "--gfx", tier, "--offscreen", "--after", "2", "--screenshot", shot]
                           + view, cwd=HERE, capture_output=True, text=True, timeout=240)
        assert r.returncode == 0 and os.path.exists(shot), (tier, (r.stdout + r.stderr)[-500:])
        img = Image.open(shot).convert("RGB").resize((160, 90))
        px = [img.getpixel((x, y)) for y in range(90) for x in range(160)]
        if tier in ("mesh", "lines"):  # black, with lines in the line colour (phosphor green)
            dark = sum(1 for p in px if max(p) < 30) / len(px)
            green = sum(1 for p in px if p[1] > 90 and p[1] > p[0] + 30) / len(px)
            assert dark > 0.2 and green > 0.03, (tier, dark, green)
        else:
            lit = sum(1 for p in px if sum(p) > 60) / len(px)  # (basic is the dimmest: about half)
            assert lit > 0.3, (tier, lit)
        assert "stage built in" in r.stdout and f"at {tier}" in r.stdout, r.stdout[-300:]


if __name__ == "__main__":
    check("The ultra fighters stay where the lower tiers' fighters are", fighters_in_place)
    check("Nothing of an ultra ring over its canvas inside the ring", rings_clear)
    check("Nothing of the ultra hall on the rings or between them and the stands", hall_clear)
    check("The models' files read back; the textures are made", files_read_back)
    check("Every tier draws the preview offscreen", tiers_draw)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + (f" ({note})" if ok else ":\n    " + note))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
