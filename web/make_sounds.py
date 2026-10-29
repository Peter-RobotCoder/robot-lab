"""sfx/ for Club Coders Live: the games' own sounds, so the page sounds as the app's windows do.

Every sound is made from maths by the games themselves (nothing recorded, nothing anyone else owns):
- engine/rw_sound.py: Robot Lab's hits (three versions of each), its weapon and motor loops (each spinning
  weapon's own), the arena hum, the crowd and its reactions, the 8-bit and rock music, the countdown's robot voice
  (engine/rw_voice.py: 3, 2, 1, Activate, Go), Kart Lab's beeps, GO and the horn;
- Kart Lab's kart_sound.py: the tyres' squeal and the boost (k_ files; its engine is Robot Lab's motor loop);
- Fight Lab's fight_sound.py: punches, kicks, blocks, whooshes, specials, the bell and the K.O. boom (f_ files);
- (CHANGE 202) Craft Lab's craft_sound.py: digging (each tool's), placing, a splash, a pop, eating, a door, a chest,
  crafting, a tool breaking, being hurt, a fuse and a blast, the creatures' calls, a crop's chime, and the day's and
  the night's tunes (c_ files).

The games write them as WAVs in engine/assets/sfx the first time they run; this calls the same generators (making
any that are missing), then turns each one the page needs into a small MP3 (mono, 44.1 kHz as the app plays them,
LAME VBR) with ffmpeg, or a 16-bit mono 22.05 kHz WAV when there is no ffmpeg. "Your music" (the teacher's own
files in engine/music) is never copied here.

Two things keep the MP3s exact in every browser:
- a loop is saved with its first half second again on the end, and plays from loop_start for loop_len seconds:
  the region holds one whole period of the loop wherever a browser's decoder starts the audio (some add the
  encoder's delay, some take it away), so there is no click at the join;
- a one-shot's onset (the first sample above 5% of its peak, in the game's WAV) is in the manifest: the page
  measures it again in the decoded sound and starts that much in, so a hit is heard on the frame it lands.

sfx/manifest.json: each sound's files (its versions), loop, base volume, channel (the teacher's sound settings:
music, crowd, arena, effects, weapons, motors), which games use it, and for the sounds whose pitch follows the
game (the spinner's motor, the drive motor and kart engine, the tyres) the numbers the windows use.

    python make_sounds.py           write sfx/ beside this file (run after a sound generator changes)
    python make_sounds.py --check   exit 1 if sfx/ is out of date with the generators' version numbers

It needs the games' Python (numpy): shared-world-demo/.venv; and ffmpeg on the PATH for MP3. --check needs none.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "sfx")
MAKER = "1"           # this file's own version: change it when the conversion or the manifest changes
MP3_QUALITY = "5"     # LAME VBR quality (0 best .. 9 smallest): about 60-80 kbit/s for these mono sounds
LOOP_PAD = 0.5        # seconds of a loop's start saved again on its end
LOOP_START = 0.25     # where the page's loop region starts in the saved file
ONSET = 0.05          # a one-shot's onset: its first sample above this fraction of its peak

# the sounds the page needs: name -> (folder: rw/kart/fight, versions, loop, base volume, channel, games)
R, F, K, C = "robotlab", "fightlab", "kartlab", "craftlab"
HITS = ["clang", "smash", "launch", "hammer", "flip", "saw", "spikes", "bump", "wall", "pneumatic", "swing"]
FIGHT_VARIED = ["punch", "kick", "heavy", "block", "whoosh", "land", "metal"]
FIGHT_SINGLE = ["jump", "blast_fire", "blast_hit", "uppercut", "spin", "slam", "zap", "fire", "bell", "ko", "counter"]
# (CHANGE 202) craft_sound.make's sounds, and its two tunes (looped)
CRAFT = ["dig_pick", "dig_axe", "dig_shovel", "dig_soft", "dig_None", "place", "step", "splash", "pop", "eat", "door", "open",
         "craft", "break", "hurt", "fuse", "blast", "beep", "baa", "zap", "clank", "grow"]


def wanted(rw_variants=3, fight_variants=3):
    s = {}
    for name in HITS:  # (rw_sound.ONE_SHOTS) the hits and the weapons firing
        games = [R, F, K] if name == "wall" else [R, K] if name == "bump" else [R]
        channel = "weapons" if name in ("pneumatic", "swing") else "effects"
        s[name] = ("rw", rw_variants, False, 0.8 if channel == "weapons" else 1.0, channel, games)
    s["spin"] = ("rw", 0, True, 0.7, "weapons", [R])          # (rw_sound.LOOPS: rw_sound.SPIN_SOUNDS, a bar spinner's...)
    s["spin_drum"] = ("rw", 0, True, 0.7, "weapons", [R])     # (...a drum's...)
    s["spin_disc"] = ("rw", 0, True, 0.7, "weapons", [R])     # (...a vertical disc's)
    s["chainsaw"] = ("rw", 0, True, 0.55, "weapons", [R])
    s["flame"] = ("rw", 0, True, 0.6, "weapons", [R])
    s["grind"] = ("rw", 0, True, 0.5, "effects", [R])
    s["motor"] = ("rw", 0, True, 0.25, "motors", [R, K])
    s["arena"] = ("rw", 0, True, 0.6, "arena", [R])
    s["crowd"] = ("rw", 0, True, 0.7, "crowd", [R, F, K])
    for name in ("ooh", "cheer", "applause"):                 # (rw_sound.REACTIONS)
        s[name] = ("rw", 0, False, 1.0, "crowd", [R, F] if name == "ooh" else [R, F, K])
    s["beep"] = ("rw", 0, False, 0.6, "effects", [K])
    s["go"] = ("rw", 0, False, 0.8, "effects", [K])
    for name in ("say_3", "say_2", "say_1"):                  # (rw_sound.VOICE: the countdown's voice, CHANGE 153)
        s[name] = ("rw", 0, False, 0.9, "effects", [R, F])
    s["say_activate"] = ("rw", 0, False, 0.9, "effects", [R])
    s["say_go"] = ("rw", 0, False, 0.9, "effects", [F])
    s["horn"] = ("rw", 0, False, 0.9, "effects", [K])
    s["chip"] = ("rw", 0, True, 0.6, "music", [R, F])         # (rw_sound.MUSIC: "yours" is the teacher's own files)
    s["rock"] = ("rw", 0, True, 0.6, "music", [R, F])
    s["k_skid"] = ("kart", 0, True, 0.55, "effects", [K])
    s["k_boost"] = ("kart", 0, False, 0.8, "effects", [K])
    for name in FIGHT_VARIED:
        s["f_" + name] = ("fight", fight_variants, False, 1.0, "effects", [F])
    for name in FIGHT_SINGLE:
        s["f_" + name] = ("fight", 0, False, 1.0, "effects", [F])
    for name in CRAFT:
        s["c_" + name] = ("craft", 0, False, 1.0, "effects", [C])
    for name in ("music_day", "music_night"):
        s["c_" + name] = ("craft", 0, True, 0.35, "crowd", [C])  # (the page's tunes setting: the crowd's switch, craftFrame)
    return s


# the windows' numbers for the sounds whose pitch and loudness follow the game (rw_sound.Sounds.spinner,
# lab_client.machine_sounds, kart_sound.KartSounds.update): rate = a + b * x, volume = c + d * x (clamped)
PITCH = {
    "spin": {"hz": 40, "follows": "weapon rpm", "min_rpm": 30, "rate": [0.3, 1 / 380], "volume": [0.12, 1 / 900],
             "volume_max": 0.7, "rate_min": 0.2},
    "spin_drum": {"hz": 30, "follows": "weapon rpm", "min_rpm": 30, "rate": [0.3, 1 / 380], "volume": [0.12, 1 / 900],
                  "volume_max": 0.7, "rate_min": 0.2},
    "spin_disc": {"hz": 50, "follows": "weapon rpm", "min_rpm": 30, "rate": [0.3, 1 / 380], "volume": [0.12, 1 / 900],
                  "volume_max": 0.7, "rate_min": 0.2},
    "motor": {"hz": 170, "follows": "speed (Robot Lab: m/s; Kart Lab: the fraction of top speed)",
              "robot": {"rate": [0.6, 1 / 8], "volume_per_speed": 1 / 20, "volume_driven": 0.04, "volume_max": 0.25},
              "kart": {"rate": [0.55, 1.3], "volume": [0.18, 0.3], "boost_rate": 0.25, "boost_volume": 0.12}},
    "k_skid": {"follows": "the fraction of top speed, while drifting above 6 m/s", "min_speed": 6,
               "rate": [0.9, 0.3], "volume": [0.35, 0.2]},
}


# ---------- where the games are ----------
def roots():
    """The engine folder and each game's: the public repository (engine/, games/<game>) or the working one."""
    for top, kart, fight in ((os.path.dirname(HERE), os.path.join("games", "kartlab"), os.path.join("games", "fightlab")),
                             (os.path.dirname(os.path.dirname(HERE)), "kart", "BeatEmUp")):
        if all(os.path.isdir(os.path.join(top, d)) for d in ("engine", kart, fight)):
            return os.path.join(top, "engine"), os.path.join(top, kart), os.path.join(top, fight)
    return None, None, None


def constant(path, name):
    """A module-level constant read without importing the file (so --check needs no numpy)."""
    with open(path, encoding="utf-8") as f:
        for node in ast.parse(f.read()).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
                return node.value.value
    return None


def craft_root():
    """(CHANGE 202) Craft Lab's folder: games/craftlab in the public repository, craft/ in the working one."""
    for folder in (os.path.join(os.path.dirname(HERE), "games", "craftlab"), os.path.join(os.path.dirname(os.path.dirname(HERE)), "craft")):
        if os.path.exists(os.path.join(folder, "craft_sound.py")):
            return folder
    return None


def versions():
    engine, kart, fight = roots()
    if engine is None:
        return None
    out = {"rw_sound": constant(os.path.join(engine, "rw_sound.py"), "VERSION"),
           "kart_sound": constant(os.path.join(kart, "kart_sound.py"), "VERSION"),
           "fight_sound": constant(os.path.join(fight, "fight_sound.py"), "VERSION"),
           "maker": MAKER}
    if craft_root():
        out["craft_sound"] = constant(os.path.join(craft_root(), "craft_sound.py"), "VERSION")
    return out


def check():
    try:
        with open(os.path.join(OUT, "manifest.json"), encoding="utf-8") as f:
            have = json.load(f)
    except (OSError, ValueError):
        print("sfx/manifest.json is missing: run make_sounds.py")
        return False
    want = versions()
    if want is None:
        print("sfx/: the games' sound files aren't beside this folder, so there is nothing to compare with")
        return True
    if have.get("versions") != want:
        print(f"sfx/ is out of date ({have.get('versions')} != {want}): run make_sounds.py")
        return False
    files = [f for s in have.get("sounds", {}).values() for f in s.get("files", [])]
    missing = [f for f in files if not os.path.exists(os.path.join(OUT, f))]
    if missing:
        print(f"sfx/ is missing {missing}: run make_sounds.py")
        return False
    print(f"sfx/ is up to date ({len(files)} files)")
    return True


# ---------- making ----------
def read_wav(path):
    import numpy as np
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit mono")
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    return data, rate


def onset(data):
    import numpy as np
    peak = float(np.max(np.abs(data))) if len(data) else 0.0
    above = np.nonzero(np.abs(data) > ONSET * peak)[0] if peak > 0 else []
    return int(above[0]) if len(above) else 0


def encode(data, rate, out, ffmpeg):
    """One sound as an MP3 (ffmpeg) or a 16-bit mono 22.05 kHz WAV."""
    import numpy as np
    pcm = (np.clip(data, -1, 1 - 1 / 32768) * 32768).astype("<i2").tobytes()
    if ffmpeg:
        cmd = [ffmpeg, "-v", "error", "-y", "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
               "-c:a", "libmp3lame", "-q:a", MP3_QUALITY, "-map_metadata", "-1", "-id3v2_version", "0",
               "-write_id3v1", "0", out]
        subprocess.run(cmd, input=pcm, check=True)
        return
    from engine import rw_sound  # (its zero-phase filter: everything above 10 kHz goes before halving the rate)
    half = rw_sound.band(data, None, 10000, soft=0.15)[::2] if rate == 44100 else data
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate // 2 if rate == 44100 else rate)
        w.writeframes((np.clip(half, -1, 1 - 1 / 32768) * 32768).astype("<i2").tobytes())


def build():
    import numpy as np
    engine, kart, fight = roots()
    if engine is None:
        sys.exit("make_sounds.py: can't find engine/, Kart Lab and Fight Lab beside this folder")
    sys.path[:0] = [os.path.dirname(engine), kart, fight]
    from engine import rw_sound
    import kart_sound
    import fight_sound
    sfx = kart_sound.ensure()   # (rw_sound.ensure() first, then the kart's own: each makes only what is missing)
    fight_sound.ensure()
    craft_sfx = None
    if craft_root():  # (CHANGE 202: Craft Lab's own, made in its assets/sfx)
        sys.path.insert(0, craft_root())
        import craft_sound
        craft_sound.ensure()
        craft_sfx = craft_sound.SFX
    ffmpeg = shutil.which("ffmpeg")
    ext = "mp3" if ffmpeg else "wav"
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith((".mp3", ".wav", ".json")):
            os.remove(os.path.join(OUT, f))
    sounds, games, seconds = {}, {R: [], F: [], K: [], C: []}, 0.0
    for name, (where, variants, loop, volume, channel, used) in wanted(rw_sound.VARIANTS, fight_sound.VARIANTS).items():
        if where == "craft" and craft_sfx is None:
            continue
        sources = [f"{name}_{v}" for v in range(variants)] if variants else [name]
        entry = {"files": [], "loop": loop, "volume": volume, "channel": channel, "games": used}
        for src in sources:
            data, rate = read_wav(os.path.join(craft_sfx, src[2:] + ".wav") if where == "craft" else os.path.join(sfx, src + ".wav"))
            secs = len(data) / rate
            seconds += secs
            if loop:
                pad = int(LOOP_PAD * rate)
                data = np.concatenate([data, data[:pad]])
                entry["loop_start"], entry["loop_len"] = LOOP_START, round(secs, 6)
            else:
                entry.setdefault("onset", []).append(round(onset(data) / rate, 5))
                entry.setdefault("seconds", []).append(round(secs, 3))
            out = f"{src}.{ext}"
            encode(data, rate, os.path.join(OUT, out), ffmpeg)
            entry["files"].append(out)
        if name in PITCH:
            entry["pitch"] = PITCH[name]
        sounds[name] = entry
        for g in used:
            games[g].append(name)
    files = [f for s in sounds.values() for f in s["files"]]
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in files)
    manifest = {"versions": versions(), "format": ext,
                "encoding": f"MP3, mono, 44.1 kHz, LAME VBR -q:a {MP3_QUALITY} (ffmpeg)" if ffmpeg
                else "WAV, 16-bit mono, 22.05 kHz (no ffmpeg on this computer)",
                "loop_pad": LOOP_PAD, "onset_threshold": ONSET, "bytes": total, "seconds": round(seconds, 1),
                "left_out": {"yours": "the teacher's own music files (engine/music): never copied to the page"},
                "games": games, "sounds": sounds}
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    wavs = [os.path.join(craft_sfx, n[2:] + ".wav") if n.startswith("c_") and craft_sfx else os.path.join(sfx, n + ".wav")
            for n in (f.rsplit(".", 1)[0] for f in files)]
    print(f"wrote {len(files)} {ext.upper()} files and manifest.json to {OUT}: {total / 1e6:.2f} MB "
          f"({seconds:.0f} s of sound; the game's WAVs are {sum(os.path.getsize(p) for p in wavs if os.path.exists(p)) / 1e6:.1f} MB)")
    if not ffmpeg:
        print("(no ffmpeg on the PATH: the files are 16-bit mono 22.05 kHz WAVs; install ffmpeg for MP3s about "
              "a tenth of the size)")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    build()
