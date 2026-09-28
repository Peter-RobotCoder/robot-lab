"""Robot Wars sound: hit sounds, a crowd, music and arena ambience, made from maths (no recordings needed)
and cached in assets/sfx as WAV files the first time the game runs (about 20 seconds, once).

Layers, mixed together (the teacher picks each one and its volume):
    music   - "chip" (8-bit), "rock", or "yours" (every .mp3 / .ogg / .wav / .flac in the music folder)
    crowd   - a murmuring crowd that reacts: "ooh" at big hits, cheers at flips and knockouts, applause at the end
    arena   - a machinery hum with far-off clanks
    effects - the hits themselves, each kind sounding like its real contact, with variations

Hit sounds (contacts only): smash (spinner), launch (drum and vertical disc), hammer, flip (the plate's thud and
clang), saw, spikes, bump (robot into robot), wall, clang (anything else); grind (a floor saw on armour, looped).
Weapon sounds: spin (an electric motor whine: its pitch follows the weapon's real speed, so it bogs down when it hits
and winds back up), pneumatic (a flipper firing), swing (a hammer), chainsaw and flame (looped), motor (driving).
"""
import os
import random
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SFX = os.path.join(HERE, "assets", "sfx")
MUSIC_DIR = os.path.join(HERE, "music")
RATE = 44100
VERSION = "7"
MUSIC = {"off": "Off", "chip": "8-bit", "rock": "Rock", "yours": "Your music"}
BACKGROUNDS = MUSIC  # (older name)
HITS = {"spinner": "smash", "drum": "launch", "hammer": "hammer", "flip": "flip", "saw": "saw", "spikes": "spikes",
        "bump": "bump", "wall": "wall", "flame": None, "break": "smash"}
VARIANTS = 3
rng = np.random.default_rng(11)


# ---------- building blocks ----------
def t(secs):
    return np.arange(int(RATE * secs)) / RATE


def noise(n):
    return rng.standard_normal(n)


def env(x, attack=0.002, decay=0.3):
    return np.minimum(1, x / max(attack, 1e-5)) * np.exp(-x / decay)


def band(sig, lo, hi, soft=0.3):
    """Keep only frequencies between lo and hi (soft edges, zero phase)."""
    spec = np.fft.rfft(sig)
    lf = np.log2(np.fft.rfftfreq(len(sig), 1 / RATE) + 1e-3)
    gain = np.ones_like(lf)
    if lo:
        gain *= np.clip((lf - np.log2(lo)) / soft + 0.5, 0, 1)
    if hi:
        gain *= np.clip((np.log2(hi) - lf) / soft + 0.5, 0, 1)
    return np.fft.irfft(spec * gain, len(sig))


def fftconv(a, b):
    n = len(a) + len(b) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(b, size), size)[:n]


def reverb(sig, secs=1.2, mix=0.25, bright=5000, tail=True):
    """An arena-sized echo: the sound convolved with a decaying burst of noise."""
    x = t(secs)
    ir = band(noise(len(x)), 120, bright) * np.exp(-6.9 * x / secs)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    wet = fftconv(sig, ir)
    out = np.concatenate([sig, np.zeros(len(wet) - len(sig))]) if tail else sig.copy()
    return out + mix * wet[:len(out)] / (np.max(np.abs(wet)) + 1e-9) * np.max(np.abs(sig))


def modes(x, freqs, decays, amps):
    """A struck metal part: several inharmonic ringing modes."""
    out = np.zeros(len(x))
    for f, d, a in zip(freqs, decays, amps):
        out += a * np.sin(2 * np.pi * f * x + rng.random() * 6.28) * np.exp(-x / d)
    return out


def thump(x, low=55, high=140, drop=0.025, decay=0.12):
    """A body blow: a low sine that falls in pitch."""
    f = low + (high - low) * np.exp(-x / drop)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * env(x, 0.002, decay)


def saw_wave(f, x):
    return (f * x) % 1 * 2 - 1


def write(name, sig, loop=False, peak=0.9):
    sig = np.asarray(sig, dtype=float).copy()
    if loop:  # fold the end onto the start so the loop has no join
        n = min(int(RATE * 1.5), len(sig) // 4)
        tail = sig[-n:].copy()
        sig = sig[:-n]
        fade = np.linspace(0, 1, n)
        sig[:n] = sig[:n] * fade + tail * (1 - fade)
    sig = sig / (np.max(np.abs(sig)) + 1e-9) * peak
    with wave.open(os.path.join(SFX, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())


def place(out, sig, at):
    k = int(at * RATE)
    if k < len(out):
        out[k:k + len(sig)] += sig[:len(out) - k]


# ---------- hits ----------
PLATE = [1, 2.32, 4.25, 6.63, 9.38, 12.1]  # how a steel plate rings (inharmonic)


def metal(secs, base, decay, crack=1.0, thud=0.0, rattle=0.0, verb=0.18):
    """Armour being hit: a burst of crunching noise, lots of short, dense ringing (not a bell), a body thud."""
    x = t(secs)
    freqs = [base * r * rng.uniform(0.9, 1.1) for r in PLATE] + [base * rng.uniform(1.5, 16) for _ in range(10)]
    decays = [decay * rng.uniform(0.25, 0.7) for _ in freqs]
    sig = modes(x, freqs, decays, [rng.uniform(0.3, 1.0) / (1 + i * 0.15) for i in range(len(freqs))]) * 0.6
    sig *= 1 + 0.5 * band(noise(len(x)), 20, 300)  # the plate rattles against its frame: rough, not pure
    sig += crack * band(noise(len(x)), 1200, 11000) * env(x, 0.0004, 0.02) * 3.5
    sig += crack * band(noise(len(x)), 300, 3000) * env(x, 0.001, 0.05) * 1.5  # the crunch
    if thud:
        sig += thud * thump(x) * 3
    for _ in range(int(14 * rattle)):  # loose bits and debris clattering
        k = int(rng.uniform(0.02, 0.35) * RATE)
        if k < len(x) - 2000:
            sig[k:] += rng.uniform(0.1, 0.35) * modes(x[:len(x) - k], [rng.uniform(1800, 5200)], [0.02], [1])
    return reverb(sig, 0.9, verb)


def make_hits():
    for v in range(VARIANTS):
        write(f"clang_{v}", metal(0.7, rng.uniform(480, 640), 0.18, crack=1.0))
        # spinner: a crack like a gunshot, heavy ringing armour, bits flying
        write(f"smash_{v}", metal(1.0, rng.uniform(300, 420), 0.22, crack=2.2, thud=1.2, rattle=1.3, verb=0.25))
        # drum or vertical disc: a deep whack that throws the robot, and a whoosh
        s = metal(1.0, rng.uniform(220, 300), 0.16, crack=1.4, thud=2.0, rattle=0.6)
        x = t(1.0)
        s[:len(x)] += band(noise(len(x)), 300, 2500) * env(x, 0.06, 0.25) * 0.6
        write(f"launch_{v}", s)
        # hammer: a huge low thud and crunching metal
        x = t(0.9)
        s = thump(x, 42, 110, 0.03, 0.25) * 4 + band(noise(len(x)), 250, 2200) * env(x, 0.001, 0.07) * 2.5
        s += modes(x, [rng.uniform(160, 220) * r for r in PLATE[:4]], [0.1, 0.08, 0.06, 0.05], [0.8, 0.5, 0.35, 0.2])
        write(f"hammer_{v}", reverb(s, 1.1, 0.25))
        # flipper hit: the thud of the plate slamming into the other robot, and its clang
        x = t(0.8)
        s = thump(x, 60, 160, 0.02, 0.1) * 2.5
        k = int(0.01 * RATE)
        s[k:] += metal(0.8, rng.uniform(380, 520), 0.12, crack=0.8)[:len(x) - k] * 0.8
        write(f"flip_{v}", s)
        # flipper firing: a blast of compressed air and the clunk of the ram
        x = t(0.6)
        blast = band(noise(len(x)), 900, 9000) * env(x, 0.003, 0.09) * 2 + band(noise(len(x)), 200, 1200) * env(x, 0.01, 0.2)
        blast += modes(x, [rng.uniform(140, 190), rng.uniform(420, 520)], [0.05, 0.03], [1.2, 0.5]) * np.clip(
            (x - 0.03) * 400, 0, 1)
        write(f"pneumatic_{v}", reverb(blast, 0.7, 0.2))
        # hammer swing: a heavy whoosh through the air
        x = t(0.5)
        sweep = band(noise(len(x)), 150, 2500) * np.sin(np.pi * np.clip(x / 0.35, 0, 1)) ** 2
        write(f"swing_{v}", sweep + thump(x, 50, 90, 0.05, 0.3) * 0.3)
        # saw hitting armour: a screech with sparks
        x = t(0.6)
        squeal = np.sin(2 * np.pi * np.cumsum(2400 + 500 * np.sin(2 * np.pi * 37 * x)) / RATE)
        s = (band(noise(len(x)), 2500, 9000) * 1.2 + squeal * 0.6) * env(x, 0.004, 0.18)
        m = metal(0.6, 700, 0.06, crack=0.6)
        m[:len(s)] += s
        write(f"saw_{v}", reverb(m, 0.6, 0.15))
        # spikes: short sharp stabs
        write(f"spikes_{v}", metal(0.5, rng.uniform(900, 1200), 0.05, crack=1.8, thud=0.6))
        # robot into robot: a dull body blow with a little rattle
        x = t(0.5)
        s = thump(x, 70, 180, 0.015, 0.08) * 2 + band(noise(len(x)), 150, 1500) * env(x, 0.001, 0.03)
        s += modes(x, [rng.uniform(250, 380) * r for r in PLATE[:3]], [0.07, 0.05, 0.04], [0.4, 0.25, 0.15])
        write(f"bump_{v}", reverb(s, 0.8, 0.2))
        # into the wall: a hollow panel boom
        x = t(0.8)
        s = thump(x, 50, 120, 0.02, 0.18) * 2.5 + band(noise(len(x)), 80, 900) * env(x, 0.002, 0.12)
        s += modes(x, [rng.uniform(90, 130) * r for r in (1, 1.6, 2.7)], [0.3, 0.2, 0.12], [0.6, 0.4, 0.2])
        write(f"wall_{v}", reverb(s, 1.0, 0.3))


def make_loops():
    x = t(3.0)  # spinner: an electric motor whine (the game changes its pitch with the weapon's speed)
    f0 = 110
    whine = sum(np.sin(2 * np.pi * f0 * k * x + k * 0.7) * a for k, a in ((1, 1.0), (2, 0.55), (3, 0.3), (4, 0.18),
                                                                           (6, 0.1)))
    whine += np.sin(2 * np.pi * f0 * 7.5 * x) * 0.22  # the high whine of the motor drive
    brushes = np.sign(np.sin(2 * np.pi * f0 * 12 * x)) * 0.03  # a little crackle from the brushes
    passing = 0.85 + 0.15 * np.sin(2 * np.pi * f0 / 4 * x) ** 2  # the weapon passing by
    write("spin", (whine + brushes) * passing + band(noise(len(x)), 300, 1500) * 0.02, loop=True)
    x = t(2.0)  # chainsaw: a two-stroke engine and a rattling chain
    engine = np.sign(np.sin(2 * np.pi * 88 * x)) * 0.5 + np.sin(2 * np.pi * 176 * x) * 0.4
    rasp = band(noise(len(x)), 900, 4500) * (0.5 + 0.5 * np.abs(np.sin(2 * np.pi * 88 * x)))
    write("chainsaw", band(engine, 60, 3000) + rasp * 0.6, loop=True)
    x = t(2.0)  # motor whine
    whine = np.sin(2 * np.pi * 170 * x) + 0.5 * np.sin(2 * np.pi * 340 * x) + 0.3 * np.sin(2 * np.pi * 510 * x)
    write("motor", whine + band(noise(len(x)), 200, 2500) * 0.25, loop=True)
    x = t(2.0)  # saw grinding armour: screeching, crackling, never quite even
    grind = band(noise(len(x)), 2000, 10000) * (0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 7 * x)))
    grind += np.sin(2 * np.pi * np.cumsum(2900 + 700 * np.sin(2 * np.pi * 3 * x)) / RATE) * 0.5
    write("grind", grind, loop=True)
    x = t(3.0)  # flame thrower roar with crackles
    roar = band(noise(len(x)), 60, 900) * (0.7 + 0.3 * np.abs(band(noise(len(x)), 1, 12)))
    for _ in range(40):
        k = int(rng.uniform(0, 2.9) * RATE)
        roar[k:k + 600] += band(noise(600), 1500, 6000) * np.exp(-np.arange(600) / 120) * 2
    write("flame", roar, loop=True)
    x = t(8.0)  # arena hum: a breathing drone with far-off clanks
    drone = (np.sin(2 * np.pi * 55 * x) + 0.6 * np.sin(2 * np.pi * 110.5 * x) + 0.3 * np.sin(2 * np.pi * 164 * x))
    drone *= 0.7 + 0.3 * np.sin(2 * np.pi * 0.25 * x)
    drone += band(noise(len(x)), 40, 400) * 1.2
    for start in (1.3, 3.9, 6.2):
        k = int(start * RATE)
        clank = metal(0.9, rng.uniform(250, 400), 0.2, crack=0.3) * 0.25
        drone[k:k + len(clank)] += clank[:len(drone) - k]
    write("arena", drone, loop=True)


# ---------- the crowd: many synthetic voices ----------
FORMANTS = {"a": (800, 1150, 2900), "e": (400, 1700, 2600), "i": (300, 2200, 3000), "o": (450, 800, 2830),
            "u": (325, 700, 2530)}


def voice(secs, pitch, vowel, breath=0.25):
    """One person: a buzzing throat shaped by their mouth (formants). pitch: Hz over time."""
    n = int(RATE * secs)
    src = saw_wave(1, np.cumsum(pitch[:n]) / RATE) + noise(n) * breath
    f = np.fft.rfftfreq(n, 1 / RATE)
    shape = sum(g * np.exp(-((f - fm * rng.uniform(0.92, 1.08)) / bw) ** 2)
                for fm, g, bw in zip(FORMANTS[vowel], (1.0, 0.6, 0.25), (90, 120, 180)))
    return np.fft.irfft(np.fft.rfft(src) * shape, n)


def crowd_mix(secs, people, make_voice, verb=1.8, mix=0.45):
    out = np.zeros(int(RATE * secs))
    for _ in range(people):
        v = make_voice()
        out[:len(v)] += v[:len(out)]
    return reverb(band(out, 120, 6000), verb, mix)


def claps(secs, count, lo=0.0, hi=None, swell=None):
    n = int(RATE * secs)
    out = np.zeros(n)
    hi = hi or secs
    for _ in range(count):
        k = int(rng.uniform(lo, hi) * RATE)
        if k < n - 800:
            a = rng.uniform(0.3, 1.0) * (swell(k / RATE) if swell else 1)
            out[k:k + 800] += band(noise(800), 700, 3500) * np.exp(-np.arange(800) / 90) * a
    return out


def reaction(secs, rise, vowels, onset=0.35, hold=0.9):
    """One person reacting: a vowel whose pitch follows rise(x), starting at a slightly different moment."""
    def one():
        male = rng.random() < 0.5
        p0 = rng.uniform(110, 160) if male else rng.uniform(200, 290)
        x = t(secs)
        curve = p0 * rng.uniform(0.9, 1.1) * (1 + rise(x) * rng.uniform(0.6, 1.4)
                                              + 0.04 * np.sin(2 * np.pi * rng.uniform(4, 7) * x))
        start = rng.uniform(0, onset)
        e = np.clip((x - start) / 0.2, 0, 1) * np.exp(-np.clip(x - start - hold, 0, None) / 0.5)
        return voice(secs, curve, rng.choice(vowels), 0.3) * e * rng.uniform(0.3, 1.0)
    return one


def chatter(secs):
    """One person talking: short syllables, each its own vowel and pitch, with consonant hisses and pauses."""
    out = np.zeros(int(RATE * secs))
    p0 = rng.uniform(95, 140) if rng.random() < 0.5 else rng.uniform(170, 250)
    at = rng.uniform(0, 0.5)
    while at < secs - 0.4:
        if rng.random() < 0.2:  # a pause between phrases
            at += rng.uniform(0.3, 1.0)
            continue
        d = rng.uniform(0.1, 0.3)
        x = t(d)
        curve = p0 * rng.uniform(0.9, 1.15) * (1 + rng.uniform(-0.15, 0.15) * x / d)
        syl = voice(d, curve * np.ones(len(x)), rng.choice(list(FORMANTS)), 0.3) * np.sin(np.pi * x / d) ** 0.7
        if rng.random() < 0.4:  # a consonant: s, t, k...
            k = int(RATE * 0.05)
            syl[:k] += band(noise(k), 3000, 8000) * np.exp(-np.arange(k) / (k / 3)) * 0.3
        place(out, syl, at)
        at += d + rng.uniform(0.0, 0.08)
    return out * rng.uniform(0.25, 1.0)


def make_crowd():
    secs = 14.0
    # 90 people chatting, heard from across a big arena: the highs are softer and there's a lot of echo
    bed = crowd_mix(secs, 90, lambda: chatter(secs), 2.2, 0.6)
    write("crowd", band(bed, 150, 4500), loop=True)
    write("ooh", crowd_mix(1.8, 45, reaction(1.8, lambda x: 0.25 * np.sin(np.pi * np.clip(x / 1.4, 0, 1)),
                                             ["u", "o"], 0.15, 0.6), 1.6, 0.5))
    x = t(3.5)
    cheer = crowd_mix(3.5, 50, reaction(3.5, lambda x: 0.35 * np.clip(x / 0.5, 0, 1), ["a", "e", "o"], 0.4, 1.2),
                      1.8, 0.5)
    for _ in range(4):  # whistles
        k = int(rng.uniform(0.2, 1.5) * RATE)
        y = x[:len(x) - k]
        f = rng.uniform(2200, 3000) * (1 + 0.1 * np.clip(y / 0.2, 0, 1)) * (1 + 0.01 * np.sin(2 * np.pi * 6 * y))
        cheer[k:k + len(y)] += np.sin(2 * np.pi * np.cumsum(f) / RATE) * env(y, 0.05, 0.6) * 0.08
    cheer[:len(x)] += claps(3.5, 250, 0.3, 3.3) * 0.15
    write("cheer", cheer)
    applause = claps(6.0, 2600, 0, 5.8,
                     swell=lambda s: min(1.0, s / 0.6) * (1 if s < 3.5 else max(0.0, (5.8 - s) / 2.3)))
    applause[:int(RATE * 3.5)] += cheer[:int(RATE * 3.5)] * 0.35
    write("applause", reverb(applause, 1.5, 0.35))


# ---------- music ----------
def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def pulse(f, secs, duty=0.25):
    return np.where(((f * t(secs)) % 1) < duty, 1.0, -1.0)


def tri(f, secs):
    return 2 * np.abs(2 * ((f * t(secs)) % 1) - 1) - 1


def fold(mix, length):
    """Make a loop: the reverb tail after the end is added back onto the start."""
    tail = mix[length:]
    mix = mix[:length].copy()
    mix[:len(tail)] += tail[:length]
    return mix


def make_chip():
    """8-bit: two square-wave channels, a triangle bass and noise drums, like an old games console."""
    step = 60 / 144 / 4  # a 16th note at 144 beats a minute
    chords = [(57, "m"), (57, "m"), (53, "M"), (53, "M"), (48, "M"), (48, "M"), (55, "M"), (55, "M")] * 2
    chords[-1] = (52, "M")
    melody = [[(69, 2), (72, 2), (76, 4), (74, 2), (72, 2), (71, 2), (69, 2)],
              [(64, 4), (69, 4), (72, 4), (71, 4)],
              [(72, 2), (74, 2), (77, 4), (76, 2), (74, 2), (72, 4)],
              [(69, 6), (None, 2), (72, 4), (74, 4)],
              [(76, 2), (79, 2), (84, 4), (83, 2), (81, 2), (79, 4)],
              [(76, 4), (72, 4), (79, 8)],
              [(74, 2), (76, 2), (79, 4), (81, 2), (79, 2), (74, 4)],
              [(71, 4), (74, 4), (79, 4), (None, 4)]]
    melody = melody + melody[:6] + [[(79, 2), (81, 2), (83, 4), (86, 4), (83, 4)], [(80, 4), (76, 4), (80, 4), (83, 4)]]
    length = int(RATE * len(chords) * 16 * step)
    out = np.zeros(length + RATE * 2)
    for b, ((root, kind), line) in enumerate(zip(chords, melody)):
        bar = b * 16 * step
        tones = [0, 3, 7, 12] if kind == "m" else [0, 4, 7, 12]
        for i in range(16):  # arpeggio
            place(out, pulse(midi(root + 12 + tones[i % 4]), step * 0.9, 0.125) * env(t(step * 0.9), 0.002, 0.06) * 0.12,
                  bar + i * step)
        for i, n in enumerate([0, 0, 12, 0, 0, 12, 0, 12]):  # triangle bass in 8ths
            place(out, tri(midi(root - 12 + n), step * 1.8) * env(t(step * 1.8), 0.003, 0.2) * 0.45, bar + i * 2 * step)
        pos = 0
        for note, steps in line:  # the tune, with a little vibrato on long notes
            if note is not None:
                x = t(steps * step * 0.95)
                f = midi(note) * (1 + 0.006 * np.sin(2 * np.pi * 6 * x) * np.clip((x - 0.12) / 0.1, 0, 1))
                s = np.where((np.cumsum(f) / RATE % 1) < 0.25, 1.0, -1.0)
                place(out, s * np.minimum(1, x / 0.005) * (0.75 + 0.25 * np.exp(-x / 0.08)) * 0.22, bar + pos * step)
            pos += steps
        for i in range(0, 16, 2):  # noise hi-hats
            x = t(step)
            place(out, band(noise(len(x)), 6000, None) * env(x, 0.001, 0.02) * 0.08, bar + i * step)
        for i in (0, 8, 10):  # kick
            x = t(0.2)
            place(out, np.sin(2 * np.pi * np.cumsum(150 * np.exp(-x / 0.03) + 45) / RATE) * env(x, 0.001, 0.09) * 0.5,
                  bar + i * step)
        for i in (4, 12):  # snare
            x = t(0.18)
            place(out, np.sign(noise(len(x))) * env(x, 0.001, 0.06) * 0.18, bar + i * step)
    write("chip", fold(out, length), peak=0.8)


def make_rock():
    """Rock: drums, a driving bass and distorted power-chord guitars, with a lead line in the chorus."""
    eighth = 60 / 128 / 2
    roots = [40, 48, 43, 50] * 4  # E, C, G, D
    length = int(RATE * len(roots) * 8 * eighth)
    out = np.zeros(length + RATE * 3)
    drums = np.zeros_like(out)

    def guitar(root, secs, muted):
        x = t(secs)
        s = sum(saw_wave(midi(root + iv) * d, x) for iv in (0, 7, 12) for d in (0.997, 1.003))
        s = band(np.tanh(s * 3.5), 90, 1800 if muted else 4200)  # distortion, then a speaker cabinet
        return s * (env(x, 0.003, 0.09) if muted else np.minimum(1, x / 0.01) * np.exp(-x / 1.4))

    def kick():
        x = t(0.35)
        return np.sin(2 * np.pi * np.cumsum(50 + 110 * np.exp(-x / 0.03)) / RATE) * env(x, 0.001, 0.18) \
            + band(noise(len(x)), 2000, 8000) * env(x, 0.0005, 0.004) * 0.5

    def snare():
        x = t(0.3)
        return band(noise(len(x)), 900, 8000) * env(x, 0.001, 0.09) + np.sin(2 * np.pi * 185 * x) * env(x, 0.001, 0.05)

    def hat(open_=False):
        x = t(0.3 if open_ else 0.08)
        return band(noise(len(x)), 7000, None) * env(x, 0.0005, 0.12 if open_ else 0.02)

    lead = [[(71, 2), (69, 2), (67, 2), (64, 2)], [(67, 3), (69, 1), (72, 4)], [(74, 2), (71, 2), (67, 4)],
            [(69, 3), (71, 1), (74, 2), (76, 2)]] * 2
    for b, root in enumerate(roots):
        bar = b * 8 * eighth
        chorus = b >= 8
        if chorus:  # open, ringing chords
            place(out, guitar(root, 8 * eighth, False) * 0.5, bar)
            place(out, guitar(root, 4 * eighth, False) * 0.25, bar + 4 * eighth)
        else:  # palm-muted chugs
            for i in range(8):
                place(out, guitar(root, eighth * 0.95, True) * 0.45, bar + i * eighth)
        for i in range(8):  # bass
            x = t(eighth * 0.9)
            place(out, band(np.tanh(saw_wave(midi(root - 12), x) * 2) * env(x, 0.004, 0.25), 40, 900) * 0.55,
                  bar + i * eighth)
        for i in (0, 2, 4, 6) if chorus else (0, 3, 4):
            place(drums, kick() * 0.9, bar + i * eighth)
        for i in (2, 6):
            place(drums, snare() * 0.7, bar + i * eighth)
        for i in range(8):
            place(drums, hat(open_=chorus and i % 2 == 1) * 0.25, bar + i * eighth)
        if b in (0, 8):  # crash
            x = t(1.6)
            place(drums, band(noise(len(x)), 3000, None) * env(x, 0.002, 0.6) * 0.35, bar)
        if chorus:  # lead guitar
            pos = 0
            for note, n in lead[b - 8]:
                x = t(n * eighth * 0.95)
                f = midi(note) * (1 + 0.012 * np.sin(2 * np.pi * 5.5 * x) * np.clip((x - 0.15) / 0.1, 0, 1))
                s = np.tanh(saw_wave(1, np.cumsum(f) / RATE) * 4)
                place(out, band(s, 200, 5000) * np.minimum(1, x / 0.01) * np.exp(-x / 2) * 0.22, bar + pos * eighth)
                pos += n
    write("rock", fold(reverb(out, 1.3, 0.2, tail=False) + drums, length), peak=0.85)


def make():
    os.makedirs(SFX, exist_ok=True)
    make_hits()
    make_loops()
    make_crowd()
    make_chip()
    make_rock()
    x = t(0.18)
    write("beep", np.sin(2 * np.pi * 880 * x) * env(x, 0.005, 0.12))
    x = t(0.6)
    write("go", (np.sin(2 * np.pi * 1320 * x) + 0.5 * np.sin(2 * np.pi * 1760 * x)) * env(x, 0.005, 0.35))
    x = t(1.4)
    write("horn", (np.sign(np.sin(2 * np.pi * 220 * x)) + np.sign(np.sin(2 * np.pi * 277 * x))) * 0.5
          * np.minimum(1, x / 0.02) * np.minimum(1, (1.4 - x) / 0.2))


def ensure():
    marker = os.path.join(SFX, f"version_{VERSION}.txt")
    if not os.path.exists(marker):
        print("Making the game's sounds (first run only, about 20 seconds)...")
        make()
        open(marker, "w").close()
    return SFX


def your_music():
    """Music files the teacher has put in the music folder."""
    if not os.path.isdir(MUSIC_DIR):
        return []
    return sorted(os.path.join(MUSIC_DIR, f) for f in os.listdir(MUSIC_DIR)
                  if f.lower().endswith((".mp3", ".ogg", ".wav", ".flac")))


# ---------- the teacher's sound settings (shared by the server and the windows) ----------
DEFAULT_SOUND = {"music": "off", "music_volume": 0.5, "crowd": True, "crowd_volume": 0.6, "arena": False,
                 "arena_volume": 0.4, "effects": True, "volume": 0.7, "weapons": True, "weapons_volume": 0.6}


def sound_settings(saved=None, change=None):
    """The full, checked sound settings: saved ones (older lessons used "background"), plus any change."""
    s = dict(DEFAULT_SOUND)
    saved = dict(saved or {})
    old = saved.pop("background", None)  # (the older single choice)
    if old == "beat":
        s["music"] = "rock"
    elif old in ("arena", "off"):
        s["crowd"], s["arena"] = False, old == "arena"
    for k, v in list(saved.items()) + list((change or {}).items()):
        if k == "music" and v in MUSIC:
            s[k] = v
        elif k in ("crowd", "arena", "effects", "weapons"):
            s[k] = bool(v)
        elif k in ("music_volume", "crowd_volume", "arena_volume", "volume", "weapons_volume"):
            try:
                s[k] = round(max(0.0, min(1.0, float(v))), 2)
            except (TypeError, ValueError):
                pass
    return s


# ---------- playing ----------
ONE_SHOTS = ["clang", "smash", "launch", "hammer", "flip", "saw", "spikes", "bump", "wall", "pneumatic", "swing"]
LOOPS = ["spin", "motor", "grind", "flame", "arena", "crowd", "chainsaw"]
REACTIONS = ["ooh", "cheer", "applause"]
ALIASES = {"crunch": "hammer"}  # (older names)


class Sounds:
    """Loads the sounds into Panda3D and mixes the layers. With no sound card (or in offscreen tests) it's quiet."""

    def __init__(self, base, on=True):
        from panda3d.core import Filename
        self.Filename = Filename
        ensure()
        self.on, self.base = on, base
        self.pool = {}
        for name in ONE_SHOTS:  # two copies of each variation, so hits can overlap
            self.pool[name] = [self._load(f"{name}_{v}") for v in range(VARIANTS) for _ in range(2)]
        for name in LOOPS + REACTIONS + ["beep", "go", "horn"]:
            self.pool[name] = [self._load(name)]
        self.loops = {}
        self.music, self.music_snd, self.playlist = "off", None, []
        self.crowd_volume = 0.6
        self.last_reaction = -99.0

    def _load(self, name, path=None):
        try:
            return self.base.loader.loadSfx(self.Filename.fromOsSpecific(path or os.path.join(SFX, name + ".wav")))
        except Exception:
            return None

    def play(self, name, volume=1.0, rate=1.0):
        name = ALIASES.get(name, name)
        sounds = [s for s in self.pool.get(name, []) if s is not None]
        if not self.on or not sounds:
            return
        free = [s for s in sounds if s.status() != s.PLAYING] or sounds
        snd = random.choice(free)
        snd.setVolume(max(0.0, min(1.0, volume)))
        snd.setPlayRate(rate * random.uniform(0.95, 1.05))
        snd.play()

    def hit(self, kind, volume):
        """The sound of a contact: the right one for what hit what."""
        name = HITS.get(kind, "clang")
        if name:
            self.play(name, volume)

    def loop(self, key, name, volume, rate=1.0):
        """Start or adjust a looping sound (spinner hum, motor, grinding saw, flame, crowd, arena hum)."""
        if not self.on:
            return
        snd = self.loops.get(key)
        if snd is None:
            snd = self._load(name)  # its own copy, so several of the same loop can play (one per spinner)
            if snd is None:
                return
            snd.setLoop(True)
            snd.setVolume(0.0)
            snd.play()
            self.loops[key] = snd
        snd.setVolume(max(0.0, min(1.0, volume)))
        snd.setPlayRate(max(0.2, rate))

    def stop(self, key):
        snd = self.loops.pop(key, None)
        if snd is not None:
            snd.stop()

    def keep_only(self, prefix, keys):
        """Stop every loop whose key starts with prefix, except those in keys (e.g. spinners no longer spinning)."""
        for key in [k for k in self.loops if k.startswith(prefix) and k not in keys]:
            self.stop(key)

    def spinner(self, key, rpm, volume):
        """A spinning weapon's motor: the pitch follows its speed, so it bogs down on a hit and winds back up."""
        if rpm < 30 or volume <= 0:
            self.stop(key)
            return
        self.loop(key, "spin", min(0.7, 0.12 + rpm / 900) * volume, 0.3 + rpm / 380)

    def layers(self, music="off", music_volume=0.5, crowd=True, crowd_volume=0.6, arena=False, arena_volume=0.4):
        """Set the background layers: any mix of music, crowd and arena hum (call every frame)."""
        if not self.on:
            return
        self.set_music(music, music_volume)
        self.crowd_volume = crowd_volume if crowd else 0.0
        if self.crowd_volume > 0:
            self.loop("crowd", "crowd", self.crowd_volume * 0.7)
        else:
            self.stop("crowd")
        if arena and arena_volume > 0:
            self.loop("arena", "arena", arena_volume * 0.6)
        else:
            self.stop("arena")

    def set_music(self, choice, volume):
        if choice != self.music:
            if self.music_snd is not None:
                self.music_snd.stop()
            self.music, self.music_snd, self.playlist = choice, None, []
            if choice in ("chip", "rock"):
                self.music_snd = self._load(choice)
                if self.music_snd is not None:
                    self.music_snd.setLoop(True)
                    self.music_snd.setVolume(max(0.0, min(1.0, volume * 0.6)))
                    self.music_snd.play()
        if choice == "yours" and (self.music_snd is None or self.music_snd.status() != self.music_snd.PLAYING):
            if not self.playlist:  # the teacher's own tracks, shuffled, one after another
                self.playlist = your_music()
                random.shuffle(self.playlist)
            self.music_snd = self._load(None, self.playlist.pop()) if self.playlist else None
            if self.music_snd is not None:
                self.music_snd.setVolume(max(0.0, min(1.0, volume * 0.6)))
                self.music_snd.play()
        if self.music_snd is not None:
            self.music_snd.setVolume(max(0.0, min(1.0, volume * 0.6)))

    def react(self, what, now):
        """The crowd reacts: "ooh" (a big hit), "cheer" (a flip or a knockout), "applause" (the end)."""
        if self.crowd_volume <= 0 or now - self.last_reaction < {"ooh": 2.5, "cheer": 3.0, "applause": 0.0}[what]:
            return
        self.last_reaction = now
        self.play(what, min(1.0, self.crowd_volume * 1.2))

    def background(self, name, volume=0.4):
        """(The older single background choice, for anything that still uses it.)"""
        self.layers("rock" if name == "beat" else "off", volume, name == "crowd", volume, name == "arena", volume)

    def stop_all(self):
        for snd in self.loops.values():
            snd.stop()
        self.loops = {}
        if self.music_snd is not None:
            self.music_snd.stop()
        self.music, self.music_snd = "off", None
