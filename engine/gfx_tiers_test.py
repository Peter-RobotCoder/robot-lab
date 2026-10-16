"""Checks on the graphics tiers that need no window (run after any change to gfx_tiers.py).

    python engine\\gfx_tiers_test.py        (from the repository, with a game's .venv)

1. the heuristic puts real drivers' renderer strings in the right tier
2. prc_for gives each tier its texture, multisample and gl-version lines
3. the Monitor steps down (knobs first, then the saved tier) and up on synthetic frame times, with its own clock
4. resolve() follows --gfx, then the saved tier, then the saved detection, then medium
5. the whole ladder (CHANGE 144): each game draws its own tiers, the monitor never steps into or out of mesh and
   lines, and climbs into ultra only once it has run cleanly here
6. a game's own MSAA (Robot Lab's ultra keeps 4x) is what the monitor puts back on stepping up (CHANGE 145)
7. the looks' lines (engine.line_look: the edges of mesh and lines, the floor grid, the colour) and the ultra
   models' kit (engine.model_kit: round edges facing out, the files' packing) (CHANGE 145)
Exit code 0 = all fine.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine import gfx_tiers as g  # noqa: E402

results = []


def check(name, fn):
    try:
        fn()
        results.append((name, True, ""))
    except Exception as e:  # report and carry on, so every problem is listed
        results.append((name, False, f"{type(e).__name__}: {e}"))


def heuristic():
    expected = {
        "Intel(R) UHD Graphics 620": "medium",
        "Intel(R) UHD Graphics 630": "medium",
        "Intel(R) UHD Graphics 600": "low",
        "Intel(R) UHD Graphics 605": "low",
        "Intel(R) HD Graphics 4000": "low",
        "Intel(R) HD Graphics 620": "low",
        "Intel(R) UHD Graphics": "medium",
        "Intel(R) Iris(R) Xe Graphics": "medium",
        "Intel(R) Iris(R) Plus Graphics 640": "medium",
        "Intel(R) Arc(TM) A770 Graphics": "high",
        "NVIDIA GeForce RTX 3060/PCIe/SSE2": "high",
        "NVIDIA GeForce GTX 1660 Ti/PCIe/SSE2": "high",
        "NVIDIA GeForce GTX 1050": "medium",
        "NVIDIA GeForce GTX 970/PCIe/SSE2": "medium",
        "NVIDIA GeForce GTX 750 Ti/PCIe/SSE2": "medium",
        "NVIDIA GeForce GT 730/PCIe/SSE2": "low",
        "NVIDIA GeForce MX250/PCIe/SSE2": "medium",
        "AMD Radeon RX 6600": "high",
        "AMD Radeon(TM) Vega 8 Graphics": "medium",
        "AMD Radeon(TM) Graphics": "medium",
        "AMD Radeon 780M Graphics": "medium",
        "AMD Radeon HD 7700 Series": "low",
        "ATI Radeon HD 4850": "low",
        "llvmpipe (LLVM 15.0.7, 256 bits)": "low",
        "Mesa Intel(R) UHD Graphics 620 (KBL GT2)": "low",
        "GDI Generic": "low",
        "Microsoft Basic Render Driver": "low",
        "": "low",
    }
    wrong = [f"{s!r} -> {g.classify(s)} (wanted {t})" for s, t in expected.items() if g.classify(s) != t]
    if wrong:
        raise RuntimeError("\n".join(wrong))
    # "NVIDIA Corporation" contains "ati": the vendor must never make a card look like an old ATI one
    assert g.classify("NVIDIA Corporation GeForce RTX 4070") == "high"
    assert g.classify("Intel(R) UHD Graphics 620", gl=(2, 1)) == "basic", "GL 2.1 is basic"
    assert g.classify("NVIDIA GeForce RTX 3060", gl=(4, 6), ram_gb=16) == "high"
    assert g.classify("Intel(R) UHD Graphics 620", gl=(4, 6), ram_gb=3.9) == "low", "under 4 GB is low"
    assert g.physical_ram_gb() >= 0


def prc():
    for tier in g.TIERS:
        text = g.prc_for(tier)
        s = g.SETTINGS[tier]
        assert f"texture-scale {s['texture_scale']}\n" in text, tier
        assert "texture-minfilter linear-mipmap-linear" in text, tier
        assert f"texture-anisotropic-degree {s['aniso']}\n" in text, tier
        assert f"multisamples {s['msaa']}\n" in text, tier
        assert f"framebuffer-multisample {1 if s['msaa'] else 0}" in text, tier
        assert "gl-version" not in text, f"{tier}: gl-version capped the Intel Xe context at 3.2 / GLSL 1.50"
        assert "exclude-texture-scale" in text
    assert "multisamples 0" in g.prc_for("basic") and "multisamples 0" in g.prc_for("low")
    # the prc text must parse (Panda is importable without a window)
    from panda3d.core import ConfigVariableDouble, ConfigVariableInt, SamplerState, loadPrcFileData
    loadPrcFileData("gfx test", g.prc_for("low"))
    assert ConfigVariableDouble("texture-scale").getValue() == 0.5
    assert ConfigVariableInt("multisamples").getValue() == 0
    assert SamplerState.getDefault().getEffectiveMinfilter() == SamplerState.FT_linear_mipmap_linear, \
        "texture-minfilter linear-mipmap-linear wasn't understood"


class FakeLight:
    """A directional light's NodePath as the Monitor sees it: a shadow caster with a buffer size."""
    def __init__(self, size):
        self.size = size

    def node(self):
        return self

    def isShadowCaster(self):
        return self.size > 0

    def getShadowBufferSize(self):
        class V:
            x = self.size
        return V()

    def setShadowCaster(self, on, x=0, y=0):
        self.size = x if on else 0


class FakePipeline:
    msaa_samples = 4


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def feed(mon, clock, seconds, dt, every_nth_slow=0, slow_dt=0.033):
    """seconds of frames of dt each (every nth one slow_dt long instead)."""
    n = int(seconds / dt)
    for i in range(n):
        this = slow_dt if every_nth_slow and i % every_nth_slow == 0 else dt
        clock.now += this
        mon.frame(this)


def monitor():
    tmp = tempfile.mkdtemp(prefix="gfx_tiers_test_")
    try:
        g.remember(tmp, gfx_detect={"heuristic_tier": "high"}, class_code="KEEP1")
        notes = []
        clock = Clock()
        light, pipe = FakeLight(2048), FakePipeline()
        mon = g.Monitor(tmp, "high", pipeline=pipe, lights=[light], on_note=notes.append, clock=clock)
        assert mon.steps == [("shadow", 1024), ("msaa", 0), ("shadow", 512)], mon.steps
        # warm-up: nothing is judged, however bad the frames
        feed(mon, clock, 4.5, 0.033)
        assert light.size == 2048 and pipe.msaa_samples == 4 and not notes
        # a good 3 s window after the warm-up: the tier is benchmarked clean
        feed(mon, clock, 4, 1 / 60)
        assert g.load_settings(tmp).get("gfx_benchmarked") == "high", g.load_settings(tmp)
        # 20% of frames missed: the knobs go first, one per window, then the saved tier, down to the floor
        def states(seconds, dt, every_nth_slow=0):
            seen = []
            for _ in range(int(seconds / 0.5)):
                feed(mon, clock, 0.5, dt, every_nth_slow)
                state = (light.size, pipe.msaa_samples, g.load_settings(tmp).get("gfx_tier"))
                if not seen or seen[-1] != state:
                    seen.append(state)
            return seen
        seen = states(30, 1 / 60, every_nth_slow=5)
        assert seen == [(2048, 4, None), (1024, 4, None), (1024, 0, None), (512, 0, None), (512, 0, "medium")], seen
        assert len(notes) == 1 and "Medium" in notes[0], notes  # (one tier a run; the next run judges again)
        assert g.load_settings(tmp).get("gfx_failed") == ["high"], g.load_settings(tmp)
        assert g.load_settings(tmp).get("class_code") == "KEEP1", "other settings must survive"
        r = mon.report()
        assert r["tier"] == "high" and r["missed_pct"] > 8 and 25 < r["fps"] < 60, r
        # 5% missed is within the budget: nothing moves
        before = dict(g.load_settings(tmp))
        feed(mon, clock, 7, 1 / 60, every_nth_slow=20)
        assert g.load_settings(tmp) == before
        # frames well under the budget for 10 s at a time: the knobs come back in reverse; the saved tier stays
        # at medium, because high failed here (the player's button can still choose it)
        seen = states(100, 0.008)
        assert seen == [(512, 0, "medium"), (1024, 0, "medium"), (1024, 4, "medium"), (2048, 4, "medium")], seen
        # with vsync the frame times sit on the budget: a run with no missed frame still climbs (one tier a run)
        g.remember(tmp, gfx_tier="low", gfx_failed=[])
        mon = g.Monitor(tmp, "low", pipeline=None, lights=[], on_note=notes.append, clock=clock)
        feed(mon, clock, 20, 1 / 60)
        assert g.load_settings(tmp).get("gfx_tier") == "medium", g.load_settings(tmp)
        # judge=False (the server is on this computer): the knobs turn, nothing is saved
        g.remember(tmp, gfx_tier="medium")
        before = dict(g.load_settings(tmp))
        light2, pipe2 = FakeLight(1024), FakePipeline()
        mon = g.Monitor(tmp, "medium", pipeline=pipe2, lights=[light2], on_note=notes.append, clock=clock, judge=False)
        feed(mon, clock, 30, 1 / 60, every_nth_slow=4)
        assert light2.size < 1024 and g.load_settings(tmp) == before, (light2.size, g.load_settings(tmp))
        # a run at low that misses frames stays at low: basic is never chosen by the monitor
        g.remember(tmp, gfx_tier="low")
        mon = g.Monitor(tmp, "low", pipeline=None, lights=[], on_note=notes.append, clock=clock)
        feed(mon, clock, 12, 1 / 60, every_nth_slow=4)
        assert g.load_settings(tmp).get("gfx_tier") == "low"
        # the player's --gfx is a floor: no tier is saved below it
        g.remember(tmp, gfx_tier="medium")
        mon = g.Monitor(tmp, "medium", override="medium", pipeline=None, lights=[], on_note=notes.append, clock=clock)
        assert mon.steps == []
        feed(mon, clock, 12, 1 / 60, every_nth_slow=4)
        assert g.load_settings(tmp).get("gfx_tier") == "medium"
        # a machine the heuristic calls low never gets more than medium saved
        g.remember(tmp, gfx_detect={"heuristic_tier": "low"}, gfx_tier="medium", gfx_benchmarked="high")
        before_notes = len(notes)
        mon = g.Monitor(tmp, "medium", clock=clock)
        feed(mon, clock, 5.5, 1 / 60)
        feed(mon, clock, 14, 0.008)
        assert g.load_settings(tmp).get("gfx_tier") == "medium" and len(notes) == before_notes, g.load_settings(tmp)
        # a fresh monitor on a fresh machine: a clean window saves the benchmark, nothing else
        shutil.rmtree(tmp)
        mon = g.Monitor(tmp, "medium", clock=clock)
        feed(mon, clock, 9, 1 / 60)
        assert g.load_settings(tmp) == {"gfx_benchmarked": "medium"}, g.load_settings(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def resolve():
    tmp = tempfile.mkdtemp(prefix="gfx_tiers_test_")
    try:
        assert g.resolve(tmp) == "medium", "a new machine starts on medium"
        assert g.resolve(tmp, "auto") == "medium" and g.resolve(tmp, None) == "medium"
        assert g.resolve(tmp, "basic") == "basic" and g.resolve(tmp, "high") == "high"
        g.remember(tmp, gfx_detect={"heuristic_tier": "high", "renderer": "test"})
        assert g.resolve(tmp) == "high", "the saved detection's heuristic"
        g.remember(tmp, gfx_tier="low")
        assert g.resolve(tmp) == "low", "the saved tier beats the heuristic"
        assert g.resolve(tmp, "medium") == "medium", "--gfx beats everything"
        g.remember(tmp, gfx_tier="silly")
        assert g.resolve(tmp) == "high", "a bad saved tier is ignored"
        assert g.below("basic") == "basic" and g.above("high") == "high" and g.below("high") == "medium"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def class_maximum():  # CHANGE 139: the teacher's gfx_max
    tmp = tempfile.mkdtemp(prefix="gfx_tiers_test_")
    try:
        assert g.class_max("blocks") == "basic" and g.class_max("low") == "low" and g.class_max("silly") is None
        assert g.class_max(None) is None and g.capped("high", "low") == "low" and g.capped("low", "high") == "low"
        g.remember(tmp, gfx_tier="high", class_code="KEEP1")
        clock = Clock()
        light, pipe = FakeLight(2048), FakePipeline()
        mon = g.Monitor(tmp, "high", pipeline=pipe, lights=[light], clock=clock)
        note = g.obey_class_max(tmp, "low", mon, "high")
        assert note and "Low" in note, note
        assert light.size == 512 and pipe.msaa_samples == 0, (light.size, pipe.msaa_samples)
        assert g.load_settings(tmp).get("gfx_class_max") == "low" and g.resolve(tmp) == "low" and g.resolve(tmp, "high") == "low"
        assert g.obey_class_max(tmp, "low", mon, "high") is None, "the note comes once"
        feed(mon, clock, 40, 0.008)  # (headroom: nothing climbs past the maximum)
        assert light.size == 512 and pipe.msaa_samples == 0 and g.load_settings(tmp).get("gfx_tier") == "high"
        g.obey_class_max(tmp, None, mon, "high")  # lifted: the run's own knobs come back, the next start is its own
        assert light.size == 2048 and pipe.msaa_samples == 4 and g.resolve(tmp) == "high"
        assert "gfx_class_max" not in g.load_settings(tmp) and g.load_settings(tmp).get("class_code") == "KEEP1"
        g.remember(tmp, gfx_tier="low", gfx_class_max="medium", gfx_benchmarked="high", gfx_detect={"heuristic_tier": "high"})
        mon = g.Monitor(tmp, "low", clock=clock)
        feed(mon, clock, 60, 1 / 60)  # (two climbs at most a run: one, and never past medium)
        assert g.load_settings(tmp).get("gfx_tier") == "medium", g.load_settings(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ladder():  # CHANGE 144: mesh < lines < basic < low < medium < high < ultra, each game its own
    kart = g.TIERS
    assert g.TIERS == ("mesh", "lines", "basic", "low", "medium", "high", "ultra") and g.CORE == ("basic", "low", "medium", "high")
    # a tier a game doesn't draw is drawn as its nearest
    assert [g.nearest(t) for t in g.TIERS] == ["basic", "basic", "basic", "low", "medium", "high", "high"]
    assert [g.nearest(t, kart) for t in g.TIERS] == list(g.TIERS) and g.nearest("silly") == "silly"
    # the steps never go into or out of the looks; ultra is a step for a game that draws it
    assert g.below("low", kart) == "basic" and g.below("basic", kart) == "basic" and g.below("lines", kart) == "lines"
    assert g.above("high", kart) == "ultra" and g.above("high") == "high" and g.below("ultra", kart) == "high"
    assert g.above("lines", kart) == "lines"
    # the heuristic never picks ultra, however strong the card
    assert g.classify("NVIDIA GeForce RTX 4090", gl=(4, 6), ram_gb=64) == "high"
    # every tier has its knobs and prc; the looks draw without simplepbr or textures worth the name
    for t in g.TIERS:
        assert set(g.SETTINGS[t]) == set(g.SETTINGS["basic"]), t
    assert not g.SETTINGS["mesh"]["simplepbr"] and not g.SETTINGS["lines"]["simplepbr"]
    assert g.SETTINGS["ultra"]["shadow"] > g.SETTINGS["high"]["shadow"] and g.SETTINGS["ultra"]["msaa"] >= 4
    tmp = tempfile.mkdtemp(prefix="gfx_tiers_test_")
    try:
        # resolve gives each game its own tier: Fight Lab draws lines as basic, ultra as high (Kart Lab and Robot Lab,
        # CHANGE 145, all seven)
        assert g.resolve(tmp, "lines") == "basic" and g.resolve(tmp, "lines", kart) == "lines"
        assert g.resolve(tmp, "ultra") == "high" and g.resolve(tmp, "ultra", kart) == "ultra"
        g.remember(tmp, gfx_tier="mesh")
        assert g.resolve(tmp, None, kart) == "mesh" and g.resolve(tmp) == "basic"
        # the class maximum is a place on the whole ladder: "lines" is lines (or mesh) in Kart Lab, basic elsewhere
        assert g.class_max("lines") == "lines" and g.class_max("ultra") == "ultra" and g.class_max("mesh") == "mesh"
        g.remember(tmp, gfx_tier="high", gfx_class_max="lines")
        assert g.resolve(tmp, None, kart) == "lines" and g.resolve(tmp) == "basic"
        g.remember(tmp, gfx_tier="mesh")
        assert g.resolve(tmp, None, kart) == "mesh", "mesh is under a maximum of lines"
        g.remember(tmp, gfx_tier="ultra", gfx_class_max="high")
        assert g.resolve(tmp, None, kart) == "high"
        g.forget(tmp, "gfx_class_max", "gfx_tier")
        # a class maximum of lines, heard by a Fight Lab learner already at basic, says nothing; at high it says Basic
        assert g.obey_class_max(tmp, "lines", None, "basic") is None
        note = g.obey_class_max(tmp, "lines", None, "high")
        assert note and "Basic" in note, note
        note = g.obey_class_max(tmp, "lines", None, "high", kart)
        assert note and "Lines" in note, note
        g.forget(tmp, "gfx_class_max")
        clock = Clock()
        # a run at lines is watched, never stepped down out of (nor into, from low) and never benchmarked
        g.remember(tmp, gfx_tier="lines", gfx_detect={"heuristic_tier": "high"})
        mon = g.Monitor(tmp, "lines", clock=clock, tiers=kart)
        feed(mon, clock, 30, 1 / 60, every_nth_slow=3)
        feed(mon, clock, 40, 0.008)
        s = g.load_settings(tmp)
        assert s.get("gfx_tier") == "lines" and "gfx_benchmarked" not in s and "gfx_failed" not in s, s
        g.remember(tmp, gfx_tier="low")
        mon = g.Monitor(tmp, "low", clock=clock, tiers=kart)
        feed(mon, clock, 30, 1 / 60, every_nth_slow=3)
        assert g.load_settings(tmp).get("gfx_tier") == "low", "the floor is still low, never lines or mesh"
        # ultra: never climbed into on the heuristic alone (high), only once it has run cleanly here
        g.remember(tmp, gfx_tier="high", gfx_failed=[], gfx_benchmarked="high")
        mon = g.Monitor(tmp, "high", clock=clock, tiers=kart)
        feed(mon, clock, 40, 0.008)
        assert g.load_settings(tmp).get("gfx_tier") == "high", g.load_settings(tmp)
        g.remember(tmp, gfx_benchmarked="ultra")
        mon = g.Monitor(tmp, "high", clock=clock, tiers=kart)
        feed(mon, clock, 40, 0.008)
        assert g.load_settings(tmp).get("gfx_tier") == "ultra", g.load_settings(tmp)
        # ...and stepped down out of like any tier (the knobs first: the 4096 shadow map halves to 512)
        light, pipe = FakeLight(4096), FakePipeline()
        pipe.msaa_samples = 8
        mon = g.Monitor(tmp, "ultra", pipeline=pipe, lights=[light], clock=clock, tiers=kart)
        feed(mon, clock, 60, 1 / 60, every_nth_slow=4)
        s = g.load_settings(tmp)
        assert light.size == 512 and pipe.msaa_samples == 0 and s.get("gfx_tier") == "high", (light.size, s)
        # a Fight Lab monitor (the core four) never steps up past high, whatever the settings say
        g.remember(tmp, gfx_tier="high", gfx_failed=[], gfx_benchmarked="ultra")
        mon = g.Monitor(tmp, "high", clock=clock)
        feed(mon, clock, 40, 0.008)
        assert g.load_settings(tmp).get("gfx_tier") == "high"
        # a tier chosen by hand in the window is kept: the monitor saves nothing over it
        g.remember(tmp, gfx_tier="medium", gfx_benchmarked="high")
        mon = g.Monitor(tmp, "medium", clock=clock, tiers=kart)
        g.remember(tmp, gfx_tier="lines")
        mon.chosen("lines")
        feed(mon, clock, 40, 0.008)
        assert g.load_settings(tmp).get("gfx_tier") == "lines"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def game_msaa():  # CHANGE 145: Robot Lab's ultra keeps 4x MSAA, not the tier's 8
    tmp = tempfile.mkdtemp(prefix="gfx_tiers_test_")
    try:
        clock = Clock()
        light, pipe = FakeLight(4096), FakePipeline()
        pipe.msaa_samples = 4
        mon = g.Monitor(None, "ultra", pipeline=pipe, lights=[light], clock=clock, tiers=g.TIERS)
        feed(mon, clock, 12, 1 / 60, every_nth_slow=2)  # (missed frames: the knobs come down)
        assert pipe.msaa_samples == 0 and light.size < 4096, (pipe.msaa_samples, light.size)
        feed(mon, clock, 200, 0.004)  # (headroom: they go back up, one a window)
        assert pipe.msaa_samples == 4 and light.size == 4096, (pipe.msaa_samples, light.size)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def looks():  # CHANGE 145: engine.line_look and engine.model_kit, shared by Kart Lab and Robot Lab
    from panda3d.core import NodePath
    from engine import line_look, model_geom, model_kit as mk
    from engine.rw_mesh import bevel_box
    cube = NodePath("cube")
    cube.attachNewNode(bevel_box(0.5, 0.5, 0.5, 0.0).node())
    pts, pairs = line_look.edges(cube, "mesh")
    assert len(pts) == 8 and len(pairs) == 18, (len(pts), len(pairs))  # (12 edges and a diagonal on each face)
    pts, pairs = line_look.edges(cube, "lines")
    assert len(pairs) == 12, len(pairs)  # (the outline: the diagonals lie flat)
    node = line_look.line_node("cube", pts, pairs, line_look.grid([(-2.0, -1.0, 2.0, 1.0)], 1.0))
    assert node.getGeom(0).getPrimitive(0).getNumPrimitives() == 12 + 3 + 1  # (inner lines only: x -1, 0, 1 and y 0)
    assert line_look.parse_colour("#ff0000") == (1.0, 0.0, 0.0) and line_look.parse_colour("green") == line_look.parse_colour(None)
    # a rounded box: every normal points out of it, and its triangles face the way of their normals
    part = mk.Part("box", "steel")
    mk.rounded_box(part, mk.Frame((1.0, 2.0, 3.0)), (0.3, 0.2, 0.1), 0.04, steps=3)
    for p, n in zip(part.p, part.n):
        assert mk.dot(mk.sub(p, (1.0, 2.0, 3.0)), n) > 0, (p, n)
        assert abs(p[0] - 1.0) <= 0.3001 and abs(p[1] - 2.0) <= 0.2001 and abs(p[2] - 3.0) <= 0.1001, p
    for i in range(0, len(part.idx), 3):
        a, b, c = (part.p[k] for k in part.idx[i:i + 3])
        assert mk.dot(mk.cross(mk.sub(b, a), mk.sub(c, a)), part.n[part.idx[i]]) > -1e-12
    # the files' packing reads back to a few millimetres, and the window makes one Geom of it
    pos, nrm, uv, col, alpha, idx = mk.unpack(part.packed())
    assert idx == part.idx and all(abs(a - b) < 0.002 for a, b in zip(pos, [c for q in part.p for c in q]))
    assert model_geom.node([part]).getGeom(0).getVertexData().getNumRows() == len(part.p)


if __name__ == "__main__":
    check("Heuristic puts real renderer strings in the right tier", heuristic)
    check("prc_for gives each tier its lines", prc)
    check("Monitor steps down and up on synthetic frame times", monitor)
    check("resolve follows --gfx, the saved tier, the detection, then medium", resolve)
    check("The class maximum caps resolve, the knobs in a run and the monitor's climb", class_maximum)
    check("The whole ladder: each game's own tiers, the looks and ultra", ladder)
    check("A game's own MSAA is what a step back up restores", game_msaa)
    check("The looks' lines and the ultra models' kit", looks)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
