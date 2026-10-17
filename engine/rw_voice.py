"""The countdown's voice: a robot announcer saying "three", "two", "one", "activate" and "go", made from maths as
the other sounds are (no recordings, no text-to-speech program, nothing anyone else owns), so the clips can ship
in the public repository and be made again on any computer.

How it speaks (a formant synthesiser, the way the first speaking machines did it):
- a buzzing throat: the vocal folds' pulses at the voice's pitch (an announcer's fall on each word), and breath;
- the mouth: each sound of a word (a phoneme) has its formants, the three resonances that make an "ee" an "ee"
  and an "oo" an "oo"; the throat's buzz goes through them, and they glide from one phoneme to the next;
- the hiss and pops of consonants: "th", "v", and the bursts of "t" and "g", as shaped noise;
- then the robot: the voice as if down a short metal tube.

    clips()                  {name: signal} for say_3, say_2, say_1, say_activate, say_go (44.1 kHz floats)
    make(write)              write each clip with rw_sound.write (rw_sound.make calls this)
"""
import numpy as np

RATE = 44100
FRAME, HOP, FFT = 512, 128, 2048   # the mouth changes shape every 3 ms (each frame filtered, then overlap-added)
PITCH = 112                         # the robot's voice (Hz): low
VOICE_RNG = 153                     # (its own random numbers, so the other sounds come out as they did before)
HISS = 0.10                         # the consonants' hiss beside the vowels (a burst is much quieter than a vowel)
COMB = ((0.0031, 0.4), (0.0062, 0.15))  # the robot's metal tube: echoes (s, loudness) a few milliseconds behind

# each phoneme: formants F1, F2, F3 (Hz), voicing, breath through the mouth, hiss, the hiss's band (Hz)
# (an adult man's formants, from the classic vowel measurements; closures are silent, bursts are short hisses)
PH = {
    #       F1    F2    F3   voice breath hiss  band
    "iy": (270, 2290, 3010, 1.0, 0.0, 0.0, None),    # thrEE
    "ih": (400, 1950, 2600, 1.0, 0.0, 0.0, None),    # actIvate
    "ae": (690, 1700, 2450, 1.0, 0.0, 0.0, None),    # Activate
    "ah": (620, 1180, 2400, 1.0, 0.0, 0.0, None),    # wOn
    "uf": (330, 1650, 2300, 1.0, 0.0, 0.0, None),    # twO: an English "oo" starts well forward...
    "uw": (310, 1250, 2250, 1.0, 0.0, 0.0, None),    # ...moves back...
    "u2": (320, 900, 2250, 1.0, 0.0, 0.0, None),     # ...and rounds at its end
    "oh": (540, 950, 2450, 1.0, 0.0, 0.0, None),     # gO, its start
    "oo": (380, 800, 2350, 1.0, 0.0, 0.0, None),     # gO, its end
    "ey": (480, 1950, 2600, 1.0, 0.0, 0.0, None),    # activAte, its start
    "yy": (330, 2250, 2850, 1.0, 0.0, 0.0, None),    # activAte, its end
    "r":  (350, 1050, 1550, 0.8, 0.0, 0.0, None),    # thRee: the low third formant is what makes an r
    "w":  (290, 640, 2200, 0.7, 0.0, 0.0, None),     # One
    "n":  (260, 1450, 2500, 0.45, 0.0, 0.0, "nasal"),  # oNe: a hum through the nose
    "v":  (260, 1400, 2400, 0.4, 0.0, 0.22, (1400, 7000)),  # actiVate
    "th": (350, 1400, 2500, 0.0, 0.0, 0.11, (1200, 9000)),  # THree: a soft, flat hiss
    "-":  (500, 1500, 2500, 0.0, 0.0, 0.0, None),    # a closure: silence
    "kc": (400, 1900, 2150, 0.0, 0.0, 0.0, None),    # a k's closure: the vowel before it pinches F2 and F3 together
    "t":  (400, 1800, 2700, 0.0, 0.0, 1.0, (2800, 9000)),   # a t's burst: high
    "g":  (300, 1100, 2100, 0.0, 0.0, 0.7, (1100, 3200)),   # a g's burst: lower
    "h":  (500, 1500, 2500, 0.0, 0.55, 0.0, None),   # breath after a t (takes the next vowel's formants)
}

# each word: (phoneme, seconds), pitch at its start and end (a slight fall, as an announcer says a word), loudness
WORDS = {
    "say_3": ([("th", 0.06), ("r", 0.10), ("iy", 0.28)], 1.4, 0.75, 1.0),
    "say_2": ([("-", 0.02), ("t", 0.012), ("h", 0.07), ("uf", 0.12), ("uw", 0.12), ("u2", 0.1)], 1.4, 0.75, 1.0),
    "say_1": ([("w", 0.07), ("ah", 0.20), ("n", 0.16)], 1.4, 0.75, 1.0),
    "say_activate": ([("ae", 0.13), ("kc", 0.055), ("t", 0.012), ("h", 0.035), ("ih", 0.07), ("v", 0.065),
                      ("ey", 0.12), ("yy", 0.08), ("-", 0.06), ("t", 0.012), ("h", 0.05)], 1.45, 0.75, 1.0),
    "say_go": ([("-", 0.025), ("g", 0.012), ("oh", 0.20), ("oo", 0.20)], 1.5, 0.8, 1.0),
}
NAMES = list(WORDS)
GLIDES = {"r": 0.12, "w": 0.10, "uw": 0.08, "ey": 0.1, "oh": 0.1}  # sounds the mouth moves through slowly (s)
FADES = {"th": 0.08, "v": 0.03, "n": 0.03}  # sounds that fade in and out rather than start at once (s)


def tracks(segments, glide=0.035):
    """Every parameter, frame by frame: each phoneme's values held through its middle, gliding to the next across
    the join (the formants over glide seconds; loudness changes quicker, so bursts stay sharp)."""
    times, rows = [], []
    at = 0.0
    for i, (ph, secs) in enumerate(segments):
        f1, f2, f3, av, ah, af, band = PH[ph]
        if ph == "h" and i + 1 < len(segments):  # breath takes the shape of the vowel after it
            f1, f2, f3 = PH[segments[i + 1][0]][:3]
            f1 = f1 * 0.8
        if ph in ("-", "t", "g") and i + 1 < len(segments) and PH[segments[i + 1][0]][3] > 0:
            f1, f2, f3 = (np.array(PH[segments[i + 1][0]][:3]) + np.array(PH[ph][:3])) / 2  # (the next vowel's locus)
        lo, hi = band if isinstance(band, tuple) else (1000, 8000)
        nasal = 1.0 if band == "nasal" else 0.0
        g = min(max(glide, (GLIDES if glide > 0.01 else FADES).get(ph, 0.0)), secs)
        times += [at + g / 2, at + secs - g / 2]
        rows += [[f1, f2, f3, av, ah, af, lo, hi, nasal]] * 2
        at += secs
    return np.array(times), np.array(rows, dtype=float), at


def resonances(freqs, f1, f2, f3, nasal):
    """The mouth's filter at one moment: the three formants and two higher fixed ones in a row (cascade), whose
    product leans the sound's highs down as a real voice's are; a nose hum takes most of the highs away."""
    gain = np.ones_like(freqs)
    for fc, bw in ((f1, 70 + 30 * nasal), (f2, 95), (f3, 150), (3500, 220), (4500, 300)):
        gain *= fc ** 2 / np.sqrt((fc ** 2 - freqs ** 2) ** 2 + (bw * freqs) ** 2)
    if nasal:
        gain *= 1 / (1 + (freqs / 700) ** 2) ** nasal * 0.9 + 0.1 * nasal * np.exp(-((freqs - 270) / 90) ** 2)
    return gain


def overlap_add(src, shape_at):
    """Filter src through a shape that changes every frame: each windowed frame's spectrum times the shape there,
    added back together (a Hann window every quarter frame adds up to 2)."""
    n = len(src)
    win = np.hanning(FRAME + 1)[:-1]
    out = np.zeros(n + FFT)
    freqs = np.fft.rfftfreq(FFT, 1 / RATE)
    for start in range(-FRAME, n, HOP):
        lo, hi = max(0, start), min(n, start + FRAME)
        if hi <= lo:
            continue
        frame = np.zeros(FRAME)
        frame[lo - start:hi - start] = src[lo:hi]
        if not frame.any():
            continue
        y = np.fft.irfft(np.fft.rfft(frame * win, FFT) * shape_at((start + FRAME / 2) / RATE, freqs), FFT)
        a = start
        if a < 0:
            y, a = y[-a:], 0
        out[a:a + len(y)] += y[:len(out) - a]
    return out[:n + FFT // 2] / 2


def throat(ph):
    """The vocal folds (ph: where each sample is in its period, 0 to 1): they open over 40% of a period and snap
    shut in 16% (Rosenberg's pulse); the air's flow changing is what leaves the lips, so this is its slope."""
    op, cl = 0.4, 0.16
    flow = np.where(ph < op, 0.5 * (1 - np.cos(np.pi * ph / op)),
                    np.where(ph < op + cl, np.cos(np.pi / 2 * (ph - op) / cl), 0.0))
    d = np.diff(flow, prepend=flow[0])
    return d / (np.max(np.abs(d)) + 1e-9)


def speak(segments, p0, p1, rng):
    """One word: the throat's buzz and breath through the gliding mouth, plus the consonants' hiss."""
    times, rows, secs = tracks(segments)            # the formants glide over 35 ms...
    qtimes, qrows, _ = tracks(segments, 0.006)      # ...loudness changes in 6 ms, so bursts stay sharp
    n = int((secs + 0.02) * RATE)
    x = np.arange(n) / RATE
    at = lambda col: np.interp(x, times, rows[:, col])     # noqa: E731 (a parameter, sample by sample)
    quick = lambda col: np.interp(x, qtimes, qrows[:, col])  # noqa: E731
    pitch = PITCH * (p0 + (p1 - p0) * np.clip(x / max(secs, 1e-3), 0, 1))
    pitch *= 1 + 0.004 * np.sin(2 * np.pi * 5.5 * x)  # (a tiny wobble: even a robot's voice isn't a test tone)
    phase = np.cumsum(pitch) / RATE
    buzz = throat(phase % 1)
    breath, hiss = rng.standard_normal(n), rng.standard_normal(n)
    end = np.clip((secs - x) / 0.06, 0, 1) ** 2  # the voice dies away at the end of the word (no click)
    av, ah = quick(3) * end, quick(4) * end
    voiced = buzz * av + breath * (0.04 * av + 0.9 * ah)
    f1, f2, f3, lo, hi, nasal = at(0), at(1), at(2), at(6), at(7), at(8)
    k = lambda t: min(n - 1, max(0, int(t * RATE)))  # noqa: E731
    mouth = overlap_add(voiced, lambda t, fr: resonances(fr, f1[k(t)], f2[k(t)], f3[k(t)], nasal[k(t)]))

    def band(t, fr):  # the hiss's band, soft-edged
        lf = np.log2(fr + 1)
        return np.clip((lf - np.log2(lo[k(t)])) / 0.4 + 0.5, 0, 1) * np.clip((np.log2(hi[k(t)]) - lf) / 0.6 + 0.5, 0, 1)
    return mouth / (np.max(np.abs(mouth)) + 1e-9) + overlap_add(hiss * quick(5), band) * HISS


def robot(sig):
    """The robot: the voice heard again a few milliseconds later, as down a short metal tube (a hard, metallic
    edge that a real voice hasn't)."""
    out = sig.copy()
    for delay, gain in COMB:
        d = int(delay * RATE)
        out[d:] += gain * sig[:-d]
    return out


def clips():
    """Each word, ready to save: the voice, the robot's tube, nothing below 90 Hz or above 7.5 kHz, a soft start
    and end. (No echo: the arena's crowd is round it already, and an echo blurs the words.)"""
    from engine import rw_sound
    out = {}
    for i, (name, (segments, p0, p1, loud)) in enumerate(WORDS.items()):
        rng = np.random.default_rng(VOICE_RNG + i)  # (each word its own breath and hiss)
        s = rw_sound.band(robot(speak(segments, p0, p1, rng)), 90, 7500)
        s[:64] *= np.linspace(0, 1, 64)
        s[-1000:] *= np.linspace(1, 0, 1000)
        out[name] = s * loud
    return out


def make(write):
    for name, sig in clips().items():
        write(name, sig, peak=0.9)
