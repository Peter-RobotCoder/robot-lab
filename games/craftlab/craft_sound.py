"""Craft Lab's sounds (CHANGE 200), made from maths with the engine's sound kit (engine.rw_sound: noise, envelopes,
filters, a little reverb) the first time the game runs, and kept in assets/sfx: digging (stone's tick, wood's knock,
soil's crunch, leaves' rustle), placing, footsteps, a splash, picking things up, eating, a door, a chest, crafting,
a tool breaking, being hurt, a fuse and a blast, the creatures (a Fluff's soft call, a Bleep's beeps, a Glitch's
zap, a Rust Walker's clank), a crop's chime; and a calm little tune for the day and another for the night.

Sounds() plays them: each one quieter the further away it is, a few at once at most.
"""
import math
import os

import numpy as np

import craft_version
import sys
sys.path.insert(0, craft_version.ENGINE_HOME)
from engine import rw_sound as K  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SFX = os.path.join(HERE, "assets", "sfx")
VERSION = "1"
rng = np.random.default_rng(23)


def write(name, sig, loop=False, peak=0.85):
    sig = np.asarray(sig, np.float64)
    m = np.max(np.abs(sig)) or 1.0
    sig = sig / m * peak
    import wave
    os.makedirs(SFX, exist_ok=True)
    with wave.open(os.path.join(SFX, name + ".wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(K.RATE)
        f.writeframes((sig * 32767).astype(np.int16).tobytes())


def noise_hit(secs, lo, hi, decay, attack=0.001):
    x = K.t(secs)
    return K.band(rng.standard_normal(len(x)), lo, hi) * K.env(x, attack, decay)


def tone(f, secs, decay, wave="sine"):
    x = K.t(secs)
    if wave == "square":
        s = np.sign(np.sin(2 * np.pi * f * x)) * 0.5
    elif wave == "tri":
        s = 2 * np.abs(2 * ((f * x) % 1) - 1) - 1
    else:
        s = np.sin(2 * np.pi * f * x)
    return s * K.env(x, 0.003, decay)


def sweep(f0, f1, secs, decay):
    x = K.t(secs)
    f = f0 + (f1 - f0) * x / secs
    return np.sin(2 * np.pi * np.cumsum(f) / K.RATE) * K.env(x, 0.003, decay)


def make():
    write("dig_pick", noise_hit(0.12, 1800, 7000, 0.03) + 0.4 * tone(1900, 0.12, 0.02))
    write("dig_axe", noise_hit(0.16, 300, 1600, 0.05) + 0.6 * tone(180, 0.16, 0.05))
    write("dig_shovel", noise_hit(0.2, 200, 2500, 0.07))
    write("dig_soft", noise_hit(0.22, 1500, 9000, 0.08, 0.01))
    write("dig_None", noise_hit(0.18, 400, 3000, 0.06))
    write("place", noise_hit(0.14, 120, 900, 0.04) + 0.7 * tone(110, 0.14, 0.05))
    write("step", noise_hit(0.08, 300, 2500, 0.025))
    write("splash", noise_hit(0.6, 300, 6000, 0.25, 0.02))
    write("pop", sweep(500, 1100, 0.12, 0.05))
    write("eat", np.concatenate([noise_hit(0.09, 800, 5000, 0.03) for _ in range(3)]))
    write("door", noise_hit(0.25, 150, 1200, 0.08) + 0.5 * sweep(300, 180, 0.25, 0.1))
    write("open", sweep(220, 330, 0.35, 0.2) * 0.6 + noise_hit(0.35, 300, 2000, 0.15) * 0.4)
    write("craft", tone(880, 0.25, 0.1) + 0.6 * tone(1320, 0.25, 0.08))
    write("break", noise_hit(0.3, 1000, 8000, 0.08) + tone(600, 0.3, 0.05, "square") * 0.3)
    write("hurt", tone(140, 0.25, 0.08) + noise_hit(0.25, 100, 800, 0.06) * 0.6)
    write("fuse", noise_hit(3.0, 3000, 9000, 2.0, 0.05) * 0.5)
    boom = noise_hit(1.6, 30, 600, 0.5) + 0.8 * sweep(90, 30, 1.6, 0.5)
    write("blast", K.reverb(boom, 1.2, 0.3, 2000))
    write("beep", np.concatenate([tone(1200, 0.07, 0.05, "square"), tone(1600, 0.09, 0.05, "square")]))
    write("baa", sweep(420, 360, 0.45, 0.25) * (1 + 0.3 * np.sin(2 * np.pi * 7 * K.t(0.45))))
    write("zap", sweep(1800, 200, 0.25, 0.12) * 0.7 + noise_hit(0.25, 2000, 8000, 0.05) * 0.4)
    write("clank", K.metal(0.5, 210, 0.2, crack=0.6, thud=0.3) if hasattr(K, "metal") else noise_hit(0.4, 200, 3000, 0.1))
    write("grow", tone(1046, 0.4, 0.2) + tone(1568, 0.4, 0.15) * 0.6)
    # the day's tune and the night's: a few soft notes over a slow pad, looped (a minute each)
    write("music_day", tune([60, 64, 67, 72, 69, 67, 64, 62], 72), loop=True, peak=0.5)
    write("music_night", tune([57, 60, 64, 62, 60, 57, 55, 57], 56), loop=True, peak=0.45)
    with open(os.path.join(SFX, "version.txt"), "w") as f:
        f.write(VERSION)


def tune(notes, bpm):
    beat = 60 / bpm
    total = beat * 64
    out = np.zeros(int(K.RATE * total))
    for bar in range(8):
        for k, n in enumerate(notes):
            if (bar * 3 + k) % 5 == 4:
                continue
            f = 440 * 2 ** ((n + (12 if bar % 4 == 3 else 0) - 69) / 12)
            note = tone(f, beat * 3, beat * 1.2, "tri") * 0.5
            note[:int(K.RATE * beat * 2)] += tone(f * 2, beat * 2, beat * 0.5) * 0.15
            K.place(out, note, (bar * 8 + k) * beat)
        root = 440 * 2 ** ((notes[0] - 12 - 69) / 12)
        pad = tone(root, beat * 8, beat * 6, "sine") * 0.35
        K.place(out, pad, bar * 8 * beat)
    return K.reverb(out, 1.5, 0.3, 3000, tail=False)


def ensure():
    try:
        with open(os.path.join(SFX, "version.txt")) as f:
            if f.read().strip() == VERSION:
                return
    except OSError:
        pass
    make()


class Sounds:
    """Plays Craft Lab's sounds in a window: play(name, at) quieter with distance from the listener."""

    def __init__(self, base, on=True):
        self.base, self.on = base, on
        self.cache = {}
        self.music = None
        self.music_name = None
        self.volume = 0.8
        self.music_volume = 0.35
        if on:
            ensure()

    def get(self, name):
        if name not in self.cache:
            path = os.path.join(SFX, name + ".wav")
            if not os.path.exists(path):
                self.cache[name] = None
            else:
                from panda3d.core import Filename
                self.cache[name] = [self.base.loader.loadSfx(Filename.fromOsSpecific(path)) for _ in range(3)]
        return self.cache[name]

    def play(self, name, at=None, listener=None, volume=1.0, rate=None):
        if not self.on:
            return
        clips = self.get(name)
        if not clips:
            return
        v = volume * self.volume
        if at is not None and listener is not None:
            d = math.dist(at, listener)
            if d > 32:
                return
            v *= max(0.0, 1 - d / 32) ** 1.5
        clip = next((c for c in clips if c.status() != c.PLAYING), clips[0])
        clip.setVolume(v)
        clip.setPlayRate(rate or (0.92 + rng.random() * 0.16))
        clip.play()

    def set_music(self, name):
        """The day's tune or the night's (or None), crossing over."""
        if not self.on or name == self.music_name:
            return
        if self.music is not None:
            self.music.stop()
        self.music_name = name
        self.music = None
        if name:
            from panda3d.core import Filename
            path = os.path.join(SFX, name + ".wav")
            if os.path.exists(path):
                self.music = self.base.loader.loadSfx(Filename.fromOsSpecific(path))
                self.music.setLoop(True)
                self.music.setVolume(self.music_volume)
                self.music.play()


if __name__ == "__main__":
    make()
    print("sounds made in", SFX)
