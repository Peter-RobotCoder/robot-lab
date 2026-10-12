"""Checks on the graphics tiers that need no window (run after any change to gfx_tiers.py).

    python engine\\gfx_tiers_test.py        (from the repository, with a game's .venv)

1. the heuristic puts real drivers' renderer strings in the right tier
2. prc_for gives each tier its texture, multisample and gl-version lines
3. the Monitor steps down (knobs first, then the saved tier) and up on synthetic frame times, with its own clock
4. resolve() follows --gfx, then the saved tier, then the saved detection, then medium
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


if __name__ == "__main__":
    check("Heuristic puts real renderer strings in the right tier", heuristic)
    check("prc_for gives each tier its lines", prc)
    check("Monitor steps down and up on synthetic frame times", monitor)
    check("resolve follows --gfx, the saved tier, the detection, then medium", resolve)
    for name, ok, note in results:
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else ":\n    " + note))
    sys.exit(0 if all(ok for _, ok, _ in results) else 1)
