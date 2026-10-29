"""Craft Lab's sounds (CHANGE 200), made from maths with the engine's sound kit (engine.rw_sound: noise, envelopes,
filters, a little reverb) the first time the game runs, and kept in assets/sfx. Nothing recorded, nothing anyone
else owns: square, saw, triangle and sine waves, filtered noise and echoes, in Club Coders' own synth sound.

The effects (SOUNDS):
- digging: dig_drill (stone, ores, bricks: a gritty drill tick), dig_cutter (logs, boards, leaves: a buzz-saw knock),
  dig_scoop (soil, turf, sand, snow: a crunch), dig_soft (by hand, or anything else: a soft tap);
- place, step, splash, pop (picking a thing up), eat, door, open (a Locker, Fabricator or Refinery opening),
  break (a tool or a suit piece worn out), hurt, build_done (the Fabricator's chime when a blueprint is built);
- the Overload Cell: overload_hum (about 3 s arming: an electric hum pulsing faster and higher) and
  overload_pulse (a deep bass thump with a sparkle tail);
- the creatures: fluff_chirp (a Fluff's soft rising chirp), beep and beep_happy (a Bleep, and a Bleep trading),
  zap, rift_open, rift_close and blink (a Glitch's zap, its rift tearing open and sealing, its blink), clank and
  magnet (a Rust Walker's metal and its magnet arm's grab);
- grow (a crop's chime), pod (a Recharge Pod's power-up sweep), shield (the suit's shield soaking a hit).
The tunes (MUSIC): music_day (bright, C major, 80 a minute) and music_night (A minor, sparser, 66 a minute), each a
seamless loop of 16 bars: an arpeggio with echoes, a pad, a bass, a little tune and a soft kick and hat.

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
VERSION = "2"  # (2: the Club Coders synth set: new names, no sheep, no fuse, synth-and-arpeggio tunes)
SOUNDS = ["dig_drill", "dig_cutter", "dig_scoop", "dig_soft", "place", "step", "splash", "pop", "eat", "door", "open",
          "break", "hurt", "zap", "clank", "beep", "beep_happy", "grow", "build_done", "fluff_chirp", "overload_hum",
          "overload_pulse", "rift_open", "rift_close", "blink", "magnet", "pod", "shield"]
MUSIC = ["music_day", "music_night"]
rng = np.random.default_rng(23)
R = K.RATE


def write(name, sig, peak=0.85, fade=True):
    sig = np.asarray(sig, np.float64).copy()
    if fade:  # (a one-shot: no click where it stops)
        n = min(len(sig), int(R * 0.008))
        sig[len(sig) - n:] *= np.linspace(1, 0, n)
        sig[:44] *= np.linspace(0, 1, min(44, len(sig)))  # (and none where it starts: a millisecond's fade in)
    m = np.max(np.abs(sig)) or 1.0
    sig = sig / m * peak
    import wave
    os.makedirs(SFX, exist_ok=True)
    with wave.open(os.path.join(SFX, name + ".wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(R)
        f.writeframes((sig * 32767).astype(np.int16).tobytes())


# ---------- building blocks ----------
def phase(f, n):
    """Cycles so far of a tone whose frequency f (a number or one per sample) may glide."""
    return np.cumsum(np.broadcast_to(np.asarray(f, np.float64), (n,))) / R


def shape(p, kind="sine", duty=0.5):
    p = p % 1
    if kind == "square":
        return np.where(p < duty, 1.0, -1.0)
    if kind == "saw":
        return 2 * p - 1
    if kind == "tri":
        return 2 * np.abs(2 * p - 1) - 1
    return np.sin(2 * np.pi * p)


def osc(f, secs, kind="sine", duty=0.5):
    return shape(phase(f, int(R * secs)), kind, duty)


def glide(f0, f1, secs, power=1.0):
    """A frequency sliding from f0 to f1 (on a musical, exponential, scale)."""
    x = K.t(secs)
    return f0 * (f1 / f0) ** ((x / secs) ** power)


def ar(secs, attack, release):
    """Up in attack seconds, held, down over the last release seconds."""
    x = K.t(secs)
    return np.clip(x / max(attack, 1e-5), 0, 1) * np.clip((secs - x) / max(release, 1e-5), 0, 1)


def low(sig, hi):
    return K.band(sig, None, hi)


def noise_hit(secs, lo, hi, decay, attack=0.001):
    x = K.t(secs)
    return K.band(rng.standard_normal(len(x)), lo, hi) * K.env(x, attack, decay)


def tone(f, secs, decay, kind="sine", duty=0.5, attack=0.003):
    return osc(f, secs, kind, duty) * K.env(K.t(secs), attack, decay)


def crush(sig, hold):
    """Sample-and-hold: the steppy, digital edge of an old chip."""
    return np.repeat(sig[::hold], hold)[:len(sig)]


def mix(secs, *parts):
    """Sounds added together, each (at seconds, signal) or a signal at 0."""
    out = np.zeros(int(R * secs))
    for p in parts:
        at, sig = p if isinstance(p, tuple) else (0.0, p)
        K.place(out, np.asarray(sig, np.float64), at)
    return out


# ---------- the effects ----------
def dig_drill():
    secs = 0.17
    x, n = K.t(secs), int(R * secs)
    motor = K.band(shape(phase(glide(190, 150, secs), n), "square", 0.3), 300, 3500)
    grit = K.band(rng.standard_normal(n), 2500, 9000)
    chatter = (shape(phase(55, n), "square", 0.35) + 1) / 2  # the bit ticking against the stone
    return mix(secs, (0.6 * motor + 0.9 * grit * chatter) * K.env(x, 0.002, 0.05),
               noise_hit(0.02, 3000, 10000, 0.004) * 1.5)


def dig_cutter():
    secs = 0.2
    x, n = K.t(secs), int(R * secs)
    buzz = shape(phase(glide(260, 170, secs), n), "saw") * (1 + 0.5 * shape(phase(32, n), "square"))
    return (K.band(buzz, 200, 3000) * K.env(x, 0.002, 0.06) * 0.7
            + K.thump(x, 70, 220, 0.015, 0.05) * 1.2 + noise_hit(secs, 500, 2500, 0.03) * 0.6)


def dig_scoop():
    secs = 0.22
    parts = [noise_hit(secs, 100, 900, 0.05) * 0.7, K.thump(K.t(secs), 50, 110, 0.01, 0.04) * 0.5]
    for _ in range(14):  # the grains crunching
        at = 0.12 * rng.random() ** 1.3
        parts.append((at, noise_hit(rng.uniform(0.006, 0.015), 300, 4000, 0.004) * rng.uniform(0.4, 1) * (1 - at / 0.15)))
    return mix(secs, *parts)


def dig_soft():
    secs = 0.14
    return noise_hit(secs, 500, 3000, 0.025, 0.003) * 0.8 + tone(300, secs, 0.02) * 0.5


def place():
    secs = 0.18
    x = K.t(secs)
    return mix(secs, K.thump(x, 70, 180, 0.02, 0.06), noise_hit(secs, 200, 1500, 0.025) * 0.5,
               (0.01, low(tone(523, 0.06, 0.02, "square", 0.25), 3000) * 0.18))


def step():
    secs = 0.09
    return noise_hit(secs, 250, 2200, 0.02) * 0.8 + K.thump(K.t(secs), 60, 120, 0.01, 0.025) * 0.6


def splash():
    secs = 0.6
    parts = [noise_hit(secs, 300, 6000, 0.18, 0.01)]
    for _ in range(8):  # bubbles: little rising blips
        f = rng.uniform(500, 1500)
        parts.append((rng.uniform(0.05, 0.4), osc(glide(f, f * 1.6, 0.04), 0.04) * K.env(K.t(0.04), 0.002, 0.015) * 0.3))
    return K.reverb(mix(secs, *parts), 0.4, 0.15, 5000, tail=False)


def pop():
    secs = 0.16
    f = glide(520, 1250, 0.12)
    up = (osc(f, 0.12) + low(osc(f, 0.12, "square", 0.25), 4000) * 0.15) * K.env(K.t(0.12), 0.002, 0.05)
    return mix(secs, up, (0.05, osc(glide(1250, 1600, 0.06), 0.06) * K.env(K.t(0.06), 0.002, 0.02) * 0.4))


def eat():
    secs = 0.36
    parts = []
    for k in range(3):
        bite = noise_hit(0.08, 700 + 150 * k, 5000, 0.025) + K.thump(K.t(0.08), 60, 140, 0.01, 0.02) * 0.4
        parts.append((0.12 * k, bite * (1 - 0.15 * k)))
    return mix(secs, *parts)


def door():
    secs = 0.4
    whoosh = K.band(rng.standard_normal(int(R * 0.3)), 400, 3000) * ar(0.3, 0.15, 0.12) * 0.6
    servo = low(osc(glide(180, 320, 0.3), 0.3, "saw"), 1500) * ar(0.3, 0.05, 0.08) * 0.3
    clunk = K.thump(K.t(0.1), 60, 160, 0.015, 0.05) + noise_hit(0.1, 200, 1500, 0.02) * 0.5
    return mix(secs, whoosh, servo, (0.29, clunk))


def open_():
    secs = 0.55
    servo = low(osc(glide(220, 440, 0.3), 0.3, "saw"), 2500) * ar(0.3, 0.02, 0.1) * 0.35
    air = K.band(rng.standard_normal(int(R * 0.3)), 500, 4000) * ar(0.3, 0.1, 0.1) * 0.3
    chime = tone(880, 0.25, 0.12, "tri") + tone(1320, 0.25, 0.1) * 0.5
    return mix(secs, servo, air, (0.28, chime * 0.6))


def break_():
    secs = 0.4
    down = crush(osc(glide(900, 160, secs), secs, "square", 0.4), 8) * K.env(K.t(secs), 0.002, 0.12) * 0.5
    return low(down, 6000) + noise_hit(secs, 1500, 8000, 0.06) * 0.5 + K.thump(K.t(secs), 80, 200, 0.01, 0.03) * 0.4


def hurt():
    secs = 0.28
    x = K.t(secs)
    buzz = low(osc(glide(260, 110, secs), secs, "square", 0.4), 1800) * K.env(x, 0.002, 0.09) * 0.6
    return buzz + K.thump(x, 55, 150, 0.02, 0.07) * 0.9 + noise_hit(secs, 100, 900, 0.05) * 0.4


def zap():
    secs = 0.3
    x, n = K.t(secs), int(R * secs)
    f = glide(2200, 180, secs) * (1 + 0.15 * np.sin(2 * np.pi * 70 * x))
    crackle = K.band(rng.standard_normal(n), 2000, 9000) * (shape(phase(90, n), "square") + 1) / 2
    return (low(shape(phase(f, n), "saw"), 6000) * 0.5 + crackle * 0.35) * K.env(x, 0.002, 0.1)


def clank():
    return K.metal(0.5, 210, 0.2, crack=0.6, thud=0.3)


def beep():
    return low(np.concatenate([tone(1200, 0.07, 0.05, "square"), tone(1600, 0.09, 0.05, "square")]), 5000)


def beep_happy():
    parts, at = [], 0.0
    for k, f in enumerate((1047, 1319, 1568)):
        secs = 0.16 if k == 2 else 0.08
        x = K.t(secs)
        ff = f * (1 + (0.02 * np.sin(2 * np.pi * 12 * x) if k == 2 else 0))
        parts.append((at, shape(phase(ff, len(x)), "square", 0.25) * K.env(x, 0.002, 0.06 if k == 2 else 0.04)))
        at += secs + 0.02
    return low(mix(0.45, *parts), 5000)


def grow():
    secs = 0.6
    return K.reverb(mix(secs, tone(1047, 0.4, 0.2, "tri"), (0.06, tone(1568, 0.4, 0.15) * 0.6),
                        (0.12, tone(2093, 0.2, 0.08) * 0.3)), 0.6, 0.2, 6000, tail=False)


def build_done():
    secs = 1.1
    parts = [(0.07 * k, low(tone(f, 0.25, 0.08, "square", 0.25), 5000) * 0.3) for k, f in enumerate((523, 659, 784, 1047))]
    for f in (1047, 1319, 1568):  # and the chord rings out
        parts.append((0.28, (tone(f, 0.75, 0.45) + tone(f, 0.75, 0.3, "tri") * 0.4) * 0.35))
    parts.append((0.3, tone(3136, 0.3, 0.07) * 0.12))
    return K.reverb(mix(secs, *parts), 1.0, 0.3, 7000, tail=False)


def fluff_chirp():
    def chirp(f0, f1, secs):
        f = glide(f0, f1, secs, 0.7)
        return (osc(f, secs) + osc(f, secs, "tri") * 0.3) * K.env(K.t(secs), 0.01, 0.05)
    return low(mix(0.38, chirp(650, 1250, 0.12), (0.15, chirp(800, 1500, 0.1) * 0.7)), 4000)


def overload_hum():
    """The Overload Cell arming: an electric hum rising from 70 to 220 Hz, pulsing from 3 to 4.5 times a second."""
    secs = 3.0
    x, n = K.t(secs), int(R * secs)
    base = glide(70, 220, secs, 1.3)
    pulse = 0.3 + 0.7 * (0.5 + 0.5 * np.cos(2 * np.pi * phase(3 + 1.5 * x / secs, n))) ** 2
    hum = (shape(phase(base, n), "saw") * 0.5 + shape(phase(base * 2.005, n), "square") * 0.25
           + shape(phase(base * 4, n)) * 0.2 * x / secs)
    return low(hum, 3000) * pulse * ar(secs, 0.15, 0.04)


def overload_pulse():
    secs = 1.8
    x, n = K.t(secs), int(R * secs)
    boom = np.sin(2 * np.pi * phase(32 + 98 * np.exp(-x / 0.08), n)) * K.env(x, 0.002, 0.45)
    parts = [boom, noise_hit(secs, 40, 400, 0.08) * 0.6]
    for _ in range(40):  # the sparkle: bright pings fading out
        at = min(0.05 + rng.exponential(0.25), 1.4)
        parts.append((at, tone(rng.uniform(2000, 6500), 0.25, 0.06) * 0.12 * (1 - at / 1.5)))
    return K.reverb(mix(secs, *parts), 1.4, 0.3, 6000, tail=False)


def rift_open():
    secs = 0.85
    x, n = K.t(secs), int(R * secs)
    drone = (shape(phase(glide(90, 180, secs), n), "saw") + shape(phase(glide(90, 180, secs) * 1.01, n), "saw"))
    drone = low(drone, 1500) * ar(secs, 0.5, 0.1) * (0.7 + 0.3 * np.sin(2 * np.pi * 13 * x)) * 0.35
    tear = K.band(rng.standard_normal(n), 800, 5000) * (x / secs) ** 3 * 0.25 * ar(secs, 0.01, 0.05)
    parts = [drone, tear]
    for at in secs * 0.97 * np.sqrt(rng.random(120)):  # the crackle, thicker as it opens
        parts.append((at, noise_hit(0.006, 1500, 9000, 0.0015) * rng.uniform(0.3, 1)))
    return mix(secs, *parts)


def rift_close():
    secs = 0.3
    n = int(R * 0.24)
    teeth = (shape(phase(glide(40, 260, 0.24), n), "square", 0.15) + 1) / 2  # a zip: teeth faster and faster
    zipper = K.band(rng.standard_normal(n), 1500, 8000) * teeth * 0.7
    whine = low(osc(glide(300, 1400, 0.24), 0.24, "saw"), 4000) * 0.3
    snap = K.thump(K.t(0.06), 80, 300, 0.008, 0.02) + noise_hit(0.06, 3000, 10000, 0.005)
    return mix(secs, (zipper + whine) * ar(0.24, 0.01, 0.05), (0.24, snap * 0.8))


def blink():
    secs = 0.18
    parts = []
    for k in range(13):  # 10 ms of a random chip voice each
        parts.append((0.01 * k, osc(rng.choice([300, 600, 900, 1200, 1800, 2400]), 0.01, "square",
                                    rng.choice([0.125, 0.25, 0.5])) * rng.uniform(0.4, 1)))
    parts.append((0.13, osc(glide(800, 3000, 0.05), 0.05, "square", 0.25) * 0.8))
    return low(crush(mix(secs, *parts), 6), 7000) * K.env(K.t(secs), 0.001, 0.12)


def magnet():
    secs = 0.5
    x, n = K.t(secs), int(R * secs)
    f = glide(110, 95, secs)
    hum = low(shape(phase(f, n), "saw") + shape(phase(f * 1.5, n), "saw") * 0.5, 1200)
    hum *= (0.6 + 0.4 * np.sin(2 * np.pi * 25 * x)) * K.env(x, 0.02, 0.25) * 0.5
    return hum + K.thump(x, 50, 180, 0.015, 0.07) * 1.2 + noise_hit(secs, 100, 1200, 0.03) * 0.5


def pod():
    secs = 0.75
    n = int(R * 0.7)
    f = glide(180, 1400, 0.7)
    sweep = (low(shape(phase(f, n), "saw"), 3000) * 0.35 + shape(phase(f * 1.5, n), "square") * 0.15
             + shape(phase(f * 2, n)) * 0.2) * ar(0.7, 0.05, 0.15) * (0.5 + 0.5 * K.t(0.7) / 0.7)
    parts = [low(sweep, 6000)] + [(0.35 + 0.1 * k, tone(f2, 0.2, 0.1) * 0.3) for k, f2 in enumerate((1568, 2093, 2637))]
    return K.reverb(mix(secs, *parts), 0.6, 0.2, 7000, tail=False)


def shield():
    secs = 0.35
    x = K.t(secs)
    shimmer = np.sin(2 * np.pi * 1760 * x + 2 * np.sin(2 * np.pi * 220 * x)) * K.env(x, 0.002, 0.05) * 0.3
    ping = tone(1760, secs, 0.09) + tone(2637, secs, 0.06) * 0.5 + shimmer + noise_hit(secs, 4000, 10000, 0.004) * 0.4
    return K.reverb(ping, 0.5, 0.2, 8000, tail=False)


EFFECTS = {"dig_drill": dig_drill, "dig_cutter": dig_cutter, "dig_scoop": dig_scoop, "dig_soft": dig_soft, "place": place,
           "step": step, "splash": splash, "pop": pop, "eat": eat, "door": door, "open": open_, "break": break_,
           "hurt": hurt, "zap": zap, "clank": clank, "beep": beep, "beep_happy": beep_happy, "grow": grow,
           "build_done": build_done, "fluff_chirp": fluff_chirp, "overload_hum": overload_hum,
           "overload_pulse": overload_pulse, "rift_open": rift_open, "rift_close": rift_close, "blink": blink,
           "magnet": magnet, "pod": pod, "shield": shield}
PEAKS = {"step": 0.6, "dig_soft": 0.65, "fluff_chirp": 0.7, "shield": 0.7, "overload_pulse": 0.9}


# ---------- the tunes ----------
def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def voice(f, secs, kind, duty=0.5, attack=0.004, decay=1e9, release=0.03, hi=None, vib=0.0, detune=0.0):
    """One note of a synth: a wave (two, a little apart, with detune), its envelope, a low-pass and vibrato."""
    x = K.t(secs)
    ff = f * (1 + vib * np.sin(2 * np.pi * 5.5 * x) * np.clip((x - 0.15) / 0.2, 0, 1))
    s = shape(phase(ff, len(x)), kind, duty)
    if detune:
        s = 0.5 * s + 0.5 * shape(phase(ff * (1 + detune), len(x)), kind, duty)
    s = s * np.clip(x / attack, 0, 1) * np.exp(-x / decay) * np.clip((secs - x) / release, 0, 1)
    return low(s, hi) if hi else s


def echo(sig, delay, feedback, taps):
    out = sig.copy()
    for k in range(1, taps + 1):
        d = int(R * delay * k)
        out[d:] += sig[:len(sig) - d] * feedback ** k
    return out


def kick(amp, decay=0.1):
    x = K.t(0.25)
    return np.sin(2 * np.pi * phase(45 + 110 * np.exp(-x / 0.025), len(x))) * K.env(x, 0.001, decay) * amp


def hat(amp, decay=0.02):
    return noise_hit(0.08, 7000, None, decay) * amp


def tune(bpm, chords, arps, arp_voice, bass, lead, lead_voice, drums, verb):
    """16 bars of 4 beats, as a seamless loop: chords (bass note, pad notes) two bars each; arps (one pattern per
    half: indices into the chord's notes and its octave, None a rest) in 8ths an octave up, with echoes; bass
    (beats, length, interval) each bar; lead (beat, note, beats) phrases from bars 5 and 13; drums(bar) -> hits."""
    b = 60 / bpm
    length = int(R * 64 * b)
    out, arp, mel = (np.zeros(length + R * 5) for _ in range(3))
    for c, (root, pad) in enumerate(chords):
        at = c * 8 * b
        for n in pad:  # the pad: two saws a little apart, soft and dark
            K.place(out, voice(midi(n), 8 * b + 0.6, "saw", attack=0.6, release=0.9, hi=verb["pad_hi"],
                               detune=0.006) * 0.045, at)
        tones = [n + 12 for n in pad] + [pad[0] + 24]
        for i in range(16):
            k = arps[c * 2 // len(chords)][i % len(arps[0])]
            if k is not None:
                K.place(arp, arp_voice(midi(tones[k])) * (1.2 if i % 4 == 0 else 1.0), at + i * b / 2)
        for bar in range(2):
            for beat, beats, iv in bass[bar]:
                K.place(out, voice(midi(root + iv), beats * b * 0.95, "tri", decay=verb["bass_decay"], release=0.05,
                                   hi=900) * 0.32, at + (bar * 4 + beat) * b)
    for start, phrase in zip((16, 48), lead):
        for beat, n, beats in phrase:
            K.place(mel, lead_voice(midi(n), beats * b), (start + beat) * b)
    for bar in range(16):
        for beat, sig in drums(bar):
            K.place(out, sig, (bar * 4 + beat) * b)
    out += echo(arp, 0.75 * b, verb["feedback"], 5) + echo(mel, 0.75 * b, verb["feedback"] * 0.8, 3)
    out = K.reverb(out, verb["secs"], verb["mix"], verb["bright"], tail=False)
    out = K.fold(out, length)
    out /= np.max(np.abs(out)) + 1e-9
    return np.tanh(1.6 * out) / np.tanh(1.6)  # (a gentle limit on the kicks' peaks: the tune sits a little louder)


def music_day():
    chords = [(48, [60, 64, 67, 71]), (45, [57, 60, 64, 67]), (41, [53, 57, 60, 64]), (43, [55, 59, 62, 64]),
              (48, [60, 64, 67, 71]), (40, [52, 55, 59, 62]), (41, [53, 57, 60, 64]), (43, [55, 60, 62, 67])]
    arps = [[0, 1, 2, 3, 4, 3, 2, 1], [0, 2, 1, 3, 2, 4, 3, 1]]
    bass = [[(0, 1.5, 0), (1.5, 0.5, 0), (2, 1.5, 12), (3.5, 0.5, 7)]] * 2
    lead = [[(0, 76, 1.5), (1.5, 74, 0.5), (2, 72, 2), (4, 71, 1), (5, 72, 1), (6, 76, 2), (8, 77, 1.5), (9.5, 76, 0.5),
             (10, 72, 2), (12, 74, 3), (15, 71, 1)],
            [(0, 72, 1), (1, 76, 1), (2, 79, 2), (4, 77, 1), (5, 76, 1), (6, 72, 2), (8, 74, 2), (10, 79, 2), (12, 74, 4)]]

    def drums(bar):
        hits = [(0, kick(0.38)), (2, kick(0.3))] + [(i + 0.5, hat(0.045)) for i in range(4)]
        if bar >= 8:  # a shaker in the second half
            hits += [(i * 0.25, hat(0.015, 0.012)) for i in range(16) if i % 2]
        return hits
    return tune(80, chords, arps,
                lambda f: voice(f, 0.36, "square", 0.25, 0.003, 0.16, 0.02, hi=3200) * 0.1, bass, lead,
                lambda f, secs: voice(f, secs, "saw", attack=0.02, decay=1.2, release=0.08, hi=2400, vib=0.004,
                                      detune=0.004) * 0.09,
                drums, {"pad_hi": 1500, "bass_decay": 0.5, "feedback": 0.35, "secs": 1.6, "mix": 0.22, "bright": 4000})


def music_night():
    chords = [(45, [57, 60, 64, 71]), (41, [53, 57, 60, 64]), (38, [50, 53, 57, 64]), (40, [52, 57, 59, 64]),
              (45, [57, 60, 64, 71]), (41, [53, 57, 60, 64]), (38, [50, 53, 57, 64]), (40, [52, 55, 59, 62])]
    arps = [[0, None, 2, 1, None, 3, 2, None], [0, 2, None, 3, 1, None, 4, None]]
    bass = [[(0, 4, 0)], [(0, 3, 0), (3, 1, 7)]]
    lead = [[(0, 76, 2), (3, 74, 1), (4, 72, 3), (8, 71, 2), (10, 69, 2), (12, 71, 4)],
            [(0, 77, 2), (2, 76, 2), (4, 74, 4), (8, 79, 2), (10, 76, 2), (12, 74, 2), (14, 71, 2)]]

    def bell(f, secs):
        secs = max(secs, 1.5)
        return (voice(f, secs, "sine", attack=0.005, decay=0.9, release=0.2) + voice(f * 2, secs, "sine", attack=0.005,
                decay=0.4, release=0.2) * 0.3 + voice(f * 3.01, secs, "sine", attack=0.005, decay=0.2, release=0.2)
                * 0.1) * 0.12

    def drums(bar):
        hits = [(0, kick(0.3, 0.12)), (2, hat(0.035, 0.03))]
        if bar >= 8:
            hits += [(1.5, hat(0.018)), (3.5, hat(0.018))]
        return hits
    return tune(66, chords, arps,
                lambda f: (voice(f, 0.6, "tri", attack=0.004, decay=0.25, release=0.05, hi=2500)
                           + voice(f, 0.6, "square", attack=0.004, decay=0.2, release=0.05, hi=2000) * 0.25) * 0.12,
                bass, lead, bell, drums,
                {"pad_hi": 1000, "bass_decay": 1.5, "feedback": 0.42, "secs": 2.2, "mix": 0.32, "bright": 3500})


# ---------- making and playing ----------
def make():
    for name in SOUNDS:
        write(name, EFFECTS[name](), PEAKS.get(name, 0.85))
    write("music_day", music_day(), peak=0.5, fade=False)
    write("music_night", music_night(), peak=0.45, fade=False)
    keep = {n + ".wav" for n in SOUNDS + MUSIC}
    for f in os.listdir(SFX):  # (the older set's: dig_pick, baa, fuse, blast, craft...)
        if f.endswith(".wav") and f not in keep:
            os.remove(os.path.join(SFX, f))
    with open(os.path.join(SFX, "version.txt"), "w") as f:
        f.write(VERSION)


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
