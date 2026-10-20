"""Kart Lab sound: the engine note rising with speed, tyres squealing in a drift, the boost's whoosh, the 3-2-1-GO
beeps, bumps and the finish, on top of the engine's sound kit (rw_sound: the crowd, music, the beeps and horn).

Two sounds are made here from maths the first time the game runs (a second, once) and saved in the engine's
assets/sfx folder with a k_ prefix; the rest are Robot Lab's (its motor loop is the engine, its bump and wall
sounds are ours too).

    snd = KartSounds(base)
    snd.update(now, v, top, drifting, boosting, racing)    every frame, for your own kart
    snd.countdown(n)   snd.boost()   snd.bump(volume)   snd.wall()   snd.finish(now)
"""
import os

import numpy as np

from engine import rw_sound
from engine.rw_sound import RATE, SFX, band, env, noise, t

VERSION = "1"


def write(name, sig, loop=False, peak=0.9):
    rw_sound.write("k_" + name, sig, loop=loop, peak=peak)


def make():
    os.makedirs(SFX, exist_ok=True)
    # the squeal of tyres sliding: a narrow band of noise whose pitch wobbles, looped
    secs = 2.0
    x = t(secs)
    wob = 1.0 + 0.08 * np.sin(2 * np.pi * 5.3 * x) + 0.05 * np.sin(2 * np.pi * 11.7 * x)
    squeal = band(noise(len(x)), 1800, 2600, soft=0.2) * wob + 0.35 * band(noise(len(x)), 3200, 4200, soft=0.2)
    write("skid", squeal, loop=True, peak=0.7)
    # the boost: a whoosh rising through a second
    secs = 1.1
    x = t(secs)
    pieces = []
    for i in range(8):  # (short filtered pieces, each a little higher, crossfaded by the envelope's overlap)
        lo = 300 + i * 420
        seg = band(noise(len(x)), lo, lo * 2.2, soft=0.3)
        centre = 0.1 + i * 0.12
        pieces.append(seg * np.exp(-((x - centre) / 0.12) ** 2))
    whoosh = sum(pieces) * env(x, attack=0.05, decay=0.9)
    tone = np.sin(2 * np.pi * (220 + 660 * x / secs) * x) * np.exp(-x * 2.5) * 0.25
    write("boost", whoosh + tone, peak=0.85)


def ensure():
    """Make the sounds the first time (and after a change to how they are made)."""
    marker = os.path.join(SFX, f"kart_version_{VERSION}.txt")
    rw_sound.ensure()
    if not os.path.exists(marker):
        print("Making the kart sounds (first run only, a second)...", flush=True)
        make()
        open(marker, "w").close()
    return SFX


class KartSounds(rw_sound.Sounds):
    """The engine's sound mixer (crowd, music, reactions, beeps) plus the kart's own."""

    def __init__(self, base, on=True):
        ensure()
        super().__init__(base, on)
        self.pool["k_skid"] = [self._load("k_skid")]
        self.pool["k_boost"] = [self._load("k_boost") for _ in range(2)]
        self.racing = False

    def update(self, now, v, top, drifting, boosting, racing, spinning=False):
        """Your own kart, every frame: the engine note follows the speed; the tyres squeal while drifting, and
        (CHANGE 181) while the back wheels spin or the handbrake locks them (spinning), at any speed, the engine
        revving with the clutch dropped."""
        if not self.on:
            return
        speed = min(1.0, abs(v) / max(1.0, top))
        revs = 0.35 if spinning and abs(v) < 6 else 0.0  # (the wheels spinning: the engine screams)
        self.loop("engine", "motor", 0.18 + 0.3 * speed + (0.12 if boosting else 0.0) + revs * 0.4,
                  0.55 + 1.3 * speed + (0.25 if boosting else 0.0) + revs * 2.0)
        if spinning:
            self.loop("skid", "k_skid", 0.5 + 0.1 * speed, 1.05 + 0.2 * speed)
        elif drifting and abs(v) > 6:
            self.loop("skid", "k_skid", 0.35 + 0.2 * speed, 0.9 + 0.3 * speed)
        else:
            self.stop("skid")
        self.layers("off", 0.0, racing, 0.3, False, 0)  # (the crowd murmurs while there is a race on)

    def countdown(self, n):
        """n = 3, 2, 1 beep; 0 is GO."""
        self.play("go" if n == 0 else "beep", 0.8, 1.0 if n else 1.0)

    def boost(self):
        self.play("k_boost", 0.8)

    def bump(self, volume=0.7):
        self.play("bump", volume)

    def wall(self, volume=0.6):
        self.play("wall", volume)

    def finish(self, now, first=False):
        self.play("horn", 0.9)
        self.react("cheer" if first else "applause", now)
