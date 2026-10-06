"""Fight Lab sound: punches, kicks, blocks, whooshes, specials, the bell and the K.O. boom, made from maths
(no recordings needed) and saved in assets/sfx as WAV files the first time the game runs (a few seconds, once).

The crowd, the music (8-bit, rock or your own) and the beeps come from rw_sound.py, the same as Robot Lab.
Every fight sound's file name starts with "f_", so it never clashes with a Robot Lab sound.

    FightSounds(base)             everything rw_sound.Sounds does (layers, music, crowd reactions), plus:
    .hit(kind, volume, robot)     a contact: punch, kick, low, high, special, blast, counter, block, throw,
                                  zap, fire, wall, land, ringout (robots get a clang of metal on top)
    .swing(move, volume)          an attack starting: punch, kick, low, high, jump_kick, throw, blast,
                                  uppercut, spin_kick, slam (and jump)
    .bell()   the ding-ding at the start of a round        .ko()   the big boom of a knockout
"""
import os

import numpy as np

from engine import rw_sound
from engine.rw_sound import RATE, SFX, band, env, modes, noise, reverb, rng, t, thump

VERSION = "1"
VARIANTS = 3
VARIED = ["punch", "kick", "heavy", "block", "whoosh", "land", "metal"]  # 3 versions each, so repeats don't sound the same
SINGLE = ["jump", "blast_fire", "blast_hit", "uppercut", "spin", "slam", "zap", "fire", "bell", "ko", "counter"]


def write(name, sig, peak=0.9):
    """Save a sound (every fight sound starts with f_)."""
    rw_sound.write("f_" + name, sig, peak=peak)


def sweep_noise(secs, lo_start, lo_end, width=2.5, pieces=8):
    """Noise whose pitch slides from lo_start to lo_end: a whoosh. (Made from short filtered pieces, crossfaded.)"""
    x = t(secs)
    out = np.zeros(len(x))
    size = len(x) // pieces
    for i in range(pieces):
        lo = lo_start + (lo_end - lo_start) * i / max(1, pieces - 1)
        piece = band(noise(size * 2), lo, lo * width)
        window = np.hanning(size * 2)
        start = max(0, i * size - size // 2)
        seg = (piece * window)[:len(out) - start]
        out[start:start + len(seg)] += seg
    return out


# ---------- the sounds ----------
def make_variations():
    for v in range(VARIANTS):
        # punch: a snappy slap on the skin and a short thud in the body
        x = t(0.35)
        s = thump(x, rng.uniform(55, 70), rng.uniform(160, 200), 0.012, 0.06) * 2
        s += band(noise(len(x)), 800, 5000) * env(x, 0.0005, 0.015) * 2.2
        s += band(noise(len(x)), 120, 700) * env(x, 0.001, 0.04) * 0.8
        write(f"punch_{v}", reverb(s, 0.5, 0.12))
        # kick: the same, heavier and lower
        x = t(0.45)
        s = thump(x, rng.uniform(45, 55), rng.uniform(130, 160), 0.018, 0.1) * 2.6
        s += band(noise(len(x)), 500, 3500) * env(x, 0.0008, 0.02) * 2.0
        s += band(noise(len(x)), 90, 500) * env(x, 0.002, 0.06)
        write(f"kick_{v}", reverb(s, 0.6, 0.15))
        # heavy: a big hit (launchers, specials)
        x = t(0.9)
        s = thump(x, rng.uniform(38, 46), rng.uniform(110, 130), 0.03, 0.2) * 3.5
        s += band(noise(len(x)), 200, 2000) * env(x, 0.001, 0.06) * 1.5
        s += band(noise(len(x)), 1500, 8000) * env(x, 0.0005, 0.012) * 2.0
        write(f"heavy_{v}", reverb(s, 1.0, 0.25))
        # block: a muffled clack of arms taking the blow
        x = t(0.3)
        s = band(noise(len(x)), 400, 2500) * env(x, 0.0005, 0.012) * 2
        s += modes(x, [rng.uniform(850, 1000), rng.uniform(1350, 1500), rng.uniform(2200, 2500)], [0.025, 0.02, 0.015],
                   [0.6, 0.4, 0.25])
        s += thump(x, 80, 160, 0.01, 0.04) * 0.8
        write(f"block_{v}", reverb(s, 0.4, 0.1))
        # whoosh: a fist or foot swinging through the air
        x = t(0.3)
        s = sweep_noise(0.3, rng.uniform(500, 700), rng.uniform(1100, 1500)) * np.sin(np.pi * np.clip(x / 0.22, 0, 1)) ** 2
        write(f"whoosh_{v}", s)
        # land: a thud on the mat
        x = t(0.4)
        s = thump(x, 45, 90, 0.02, 0.12) * 2 + band(noise(len(x)), 80, 600) * env(x, 0.002, 0.05)
        write(f"land_{v}", reverb(s, 0.6, 0.15))
        # metal: the clang of a robot's armour, layered on top of its hits
        write(f"metal_{v}", rw_sound.metal(0.5, rng.uniform(500, 720), 0.12, crack=0.8))


def make_singles():
    # jump: a quick scuff and a small rising whoosh
    x = t(0.25)
    s = band(noise(len(x)), 300, 1800) * env(x, 0.001, 0.03) + sweep_noise(0.25, 300, 700, pieces=5) * env(x, 0.03, 0.08)
    write("jump", s)
    # blast (firing): an energy charge that rises, then a burst
    x = t(0.8)
    rise = np.clip(x / 0.25, 0, 1)
    f = 200 + 700 * rise ** 2 + 20 * np.sin(2 * np.pi * 30 * x)
    charge = np.sin(2 * np.pi * np.cumsum(f) / RATE) * rise * (x < 0.25)
    k = int(0.25 * RATE)
    y = x[:len(x) - k]
    burst = band(noise(len(y)), 300, 4000) * env(y, 0.002, 0.15) * 1.5
    burst += np.sin(2 * np.pi * np.cumsum(900 * np.exp(-y / 0.1) + 120) / RATE) * env(y, 0.001, 0.2)
    s = charge * 0.6
    s[k:] += burst
    write("blast_fire", reverb(s, 0.8, 0.2))
    # blast (hitting): an electric crackle and a thud
    x = t(0.6)
    gate = (rng.random(len(x)) < 0.08).astype(float)
    s = band(noise(len(x)), 1500, 9000) * np.convolve(gate, np.ones(60), "same") * env(x, 0.001, 0.12)
    s += thump(x, 55, 170, 0.015, 0.1) * 2
    write("blast_hit", reverb(s, 0.6, 0.15))
    # uppercut: a whoosh that rises
    x = t(0.45)
    s = sweep_noise(0.45, 250, 1600, pieces=10) * np.sin(np.pi * np.clip(x / 0.35, 0, 1)) ** 2
    s += np.sin(2 * np.pi * np.cumsum(150 + 500 * x / 0.45) / RATE) * env(x, 0.05, 0.15) * 0.15
    write("uppercut", s)
    # spin: a whoosh that goes round and round
    x = t(0.55)
    s = band(noise(len(x)), 300, 2500) * (0.5 + 0.5 * np.sin(2 * np.pi * 12 * x) ** 2) * np.sin(np.pi * x / 0.55)
    write("spin", s)
    # slam: a big crash onto the mat
    x = t(1.4)
    s = thump(x, 35, 100, 0.04, 0.35) * 4 + band(noise(len(x)), 150, 2500) * env(x, 0.001, 0.08) * 2
    s += band(noise(len(x)), 40, 300) * env(x, 0.005, 0.3) * 1.5
    write("slam", reverb(s, 1.4, 0.3))
    # zap: the electric ropes
    x = t(0.5)
    buzz = np.sign(np.sin(2 * np.pi * 120 * x)) * (0.6 + 0.4 * rng.random(len(x)))
    crackle = band(noise(len(x)), 3000, 11000) * (rng.random(len(x)) < 0.3)
    write("zap", (band(buzz, 100, 4000) * 0.7 + crackle) * env(x, 0.002, 0.2))
    # fire: a burst from a fire jet
    x = t(0.8)
    s = band(noise(len(x)), 60, 1500) * env(x, 0.02, 0.3) * 1.5
    for _ in range(15):
        k = int(rng.uniform(0, 0.6) * RATE)
        s[k:k + 500] += band(noise(500), 1500, 6000) * np.exp(-np.arange(500) / 100)
    write("fire", s)
    # bell: a boxing bell, ding-ding
    x = t(1.8)
    bell = modes(x, [820 * r for r in (1, 2.0, 2.76, 5.4, 8.9)], [0.9, 0.6, 0.4, 0.2, 0.1], [1, 0.5, 0.45, 0.2, 0.1])
    bell *= env(x, 0.001, 10)  # (the modes already decay)
    s = bell.copy()
    rw_sound.place(s, bell * 0.9, 0.28)
    write("bell", reverb(s, 1.0, 0.2, tail=False))
    # ko: a deep boom and a low brass sting
    x = t(2.2)
    s = thump(x, 30, 80, 0.08, 0.8) * 3 + np.sin(2 * np.pi * 45 * x) * env(x, 0.01, 1.2) * 1.5
    chord = sum(rw_sound.saw_wave(f, x) for f in (55, 82.5, 110, 130.8))
    s += band(chord, 40, 1200) * env(x, 0.02, 0.9) * 0.6
    write("ko", reverb(s, 2.0, 0.35))
    # counter: a sharp crack with a bright ping
    x = t(0.4)
    s = band(noise(len(x)), 2000, 10000) * env(x, 0.0003, 0.01) * 4 + thump(x, 80, 300, 0.008, 0.05) * 1.5
    s += np.sin(2 * np.pi * 2400 * x) * env(x, 0.001, 0.08) * 0.5
    write("counter", reverb(s, 0.6, 0.15))


def make():
    os.makedirs(SFX, exist_ok=True)
    make_variations()
    make_singles()


def ensure():
    """Make the sounds the first time (and after a change to how they are made)."""
    marker = os.path.join(SFX, f"fight_version_{VERSION}.txt")
    if not os.path.exists(marker):
        print("Making the fight sounds (first run only, a few seconds)...")
        make()
        open(marker, "w").close()
    return SFX


# ---------- playing ----------
# what each kind of contact sounds like (fight_sim's impacts), and how loud each part is
HIT_SOUNDS = {"punch": [("punch", 1.0)], "kick": [("kick", 1.0)], "low": [("kick", 0.9)],
              "high": [("heavy", 1.0)], "special": [("heavy", 1.0)], "blast": [("blast_hit", 1.0)],
              "counter": [("counter", 1.0), ("heavy", 0.8)], "block": [("block", 1.0)],
              "throw": [("slam", 0.8)], "zap": [("zap", 1.0)], "fire": [("fire", 1.0)],
              "wall": [("wall", 0.9)], "spikes": [("heavy", 0.9), ("wall", 0.6)], "land": [("land", 1.0)], "ringout": [("slam", 0.7)]}
METAL = {"punch": 0.5, "kick": 0.6, "low": 0.5, "high": 0.7, "special": 0.8, "blast": 0.5, "counter": 0.8,
         "block": 0.3, "throw": 0.6, "wall": 0.5, "land": 0.4}  # how much clang a robot adds
SWINGS = {"punch": ("whoosh", 0.45, 1.25), "kick": ("whoosh", 0.6, 0.9), "low": ("whoosh", 0.5, 0.85),
          "high": ("whoosh", 0.7, 0.8), "jump_kick": ("whoosh", 0.6, 0.9), "throw": ("whoosh", 0.4, 0.7),
          "blast": ("blast_fire", 0.9, 1.0), "uppercut": ("uppercut", 0.9, 1.0), "spin_kick": ("spin", 0.9, 1.0),
          "slam": ("whoosh", 0.6, 0.6), "jump": ("jump", 0.6, 1.0),
          "cartwheel": ("spin", 0.9, 0.8)}  # move: (sound, volume, speed)


class FightSounds(rw_sound.Sounds):
    """Robot Lab's sound mixer (music, crowd, reactions) plus the fight sounds."""

    def __init__(self, base, on=True):
        ensure()
        super().__init__(base, on)
        for name in VARIED:  # two copies of each version, so the same sound can overlap itself
            self.pool["f_" + name] = [self._load(f"f_{name}_{v}") for v in range(VARIANTS) for _ in range(2)]
        for name in SINGLE:
            self.pool["f_" + name] = [self._load("f_" + name) for _ in range(2)]

    def hit(self, kind, volume, robot=False):
        """The sound of a contact. A robot's hits have a clang of metal on top."""
        for name, loud in HIT_SOUNDS.get(kind, [("punch", 1.0)]):
            self.play(name if name == "wall" else "f_" + name, volume * loud)
        if robot and kind in METAL:
            self.play("f_metal", volume * METAL[kind])

    def swing(self, move, volume):
        """An attack starting: a whoosh through the air (or the special's own sound)."""
        name, loud, speed = SWINGS.get(move, ("whoosh", 0.5, 1.0))
        self.play("f_" + name, volume * loud, speed)

    def bell(self, volume=0.9):
        self.play("f_bell", volume)

    def ko(self, volume=1.0):
        self.play("f_ko", volume)


if __name__ == "__main__":  # python fight_sound.py: make the sounds again and check them
    import time
    import wave
    t0 = time.time()
    make()
    print(f"made in {time.time() - t0:.1f} s")
    for f in sorted(os.listdir(SFX)):
        if f.startswith("f_") and f.endswith(".wav"):
            with wave.open(os.path.join(SFX, f)) as w:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16) / 32767
            print(f"{f:22s} {len(data) / RATE:5.2f} s  peak {np.max(np.abs(data)):.2f}  rms {np.sqrt(np.mean(data ** 2)):.3f}")
