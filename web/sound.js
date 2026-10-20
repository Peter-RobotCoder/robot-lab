// Club Coders Live's sound: the games' own sounds (sfx/, made by make_sounds.py from engine/rw_sound.py, Kart Lab's
// kart_sound.py and Fight Lab's fight_sound.py), mixed the way the app's windows mix them.
//
//     const sound = new Sound();              // nothing loads until the first click or key (browsers need one)
//     sound.robotFrame(arena, msg, impacts, myRobotId, {listener, weapons});    every frame, Robot Lab
//     sound.fightFrame(rings, impacts, watchedRing, {listener, robots});         every frame, Fight Lab
//     sound.kartFrame(myKart, race, {top, place, karts});                        every frame, Kart Lab
//
// The directors are the windows' own code ported line for line: lab_client.py (hit_sound, machine_sounds,
// show_intro and the layers), fight_client.py (draw_state's hits, event_sounds), kart_client.py (sounds) with
// kart_sound.KartSounds.update. Their volumes already include the teacher's settings, as the windows' do.
// play() and loop() are there for anything else; pass {channel} to have a setting's switch and volume applied.
//
// Settings are rw_sound.DEFAULT_SOUND's keys (music, music_volume, crowd, crowd_volume, arena, arena_volume,
// effects, volume, weapons, weapons_volume, motors, motors_volume), kept in this browser (localStorage) as the
// app keeps them on the teacher's computer. A loop that is not set again for half a second stops by itself, so a
// game that stops drawing (the desk shown, the tab hidden, another game) never leaves a whine playing.

// ---------- the settings (rw_sound.py) ----------
export const DEFAULT_SOUND = {music: "off", music_volume: 0.5, crowd: true, crowd_volume: 0.6, arena: false,
                              arena_volume: 0.4, effects: true, volume: 0.7, weapons: true, weapons_volume: 0.6,
                              motors: true, motors_volume: 0.6};
// the page's music choices ("yours", the teacher's own files, stays in the app)
export const MUSIC = {off: "Off", chip: "8-bit", rock: "Rock"};
// channel: [its switch, its volume] in the settings
export const CHANNELS = {music: [null, "music_volume"], crowd: ["crowd", "crowd_volume"], arena: ["arena", "arena_volume"],
                         effects: ["effects", "volume"], weapons: ["weapons", "weapons_volume"], motors: ["motors", "motors_volume"]};
// each game's Sound settings rows, as its window lays them out (switch key, its words, volume key)
export const SETTINGS_ROWS = {
    robotlab: [["crowd", "Crowd", "crowd_volume"], ["arena", "Arena hum", "arena_volume"], ["weapons", "Weapons", "weapons_volume"],
               ["motors", "Motors (the robots' drive motors)", "motors_volume"], ["effects", "Hit sounds", "volume"]],
    fightlab: [["crowd", "Crowd", "crowd_volume"], ["effects", "Hits and moves", "volume"]],
    kartlab: [],  // (the window has one switch: "Engine, tyres, the countdown and the finish", which is mute)
};
export const HAS_MUSIC = {robotlab: true, fightlab: true, kartlab: false};

const BOOLS = ["crowd", "arena", "effects", "weapons", "motors"];
const VOLUMES = ["music_volume", "crowd_volume", "arena_volume", "volume", "weapons_volume", "motors_volume"];

// rw_sound.sound_settings: the full, checked settings: saved ones (older lessons used "background"), plus a change
export function soundSettings(saved = null, change = null) {
    const s = {...DEFAULT_SOUND};
    saved = {...(saved || {})};
    if ("weapons" in saved && !("motors" in saved)) {  // (older settings had one switch for weapons and motors)
        saved.motors = saved.weapons;
        if (!("motors_volume" in saved)) saved.motors_volume = saved.weapons_volume ?? s.motors_volume;
    }
    const old = saved.background;
    delete saved.background;
    if (old === "beat") s.music = "rock";
    else if (old === "arena" || old === "off") { s.crowd = false; s.arena = old === "arena"; }
    for (const [k, v] of [...Object.entries(saved), ...Object.entries(change || {})]) {
        if (k === "music" && (v in MUSIC || v === "yours")) s.music = v;
        else if (BOOLS.includes(k)) s[k] = !!v;
        else if (VOLUMES.includes(k)) {
            const f = Number(v);
            if (Number.isFinite(f)) s[k] = Math.round(Math.max(0, Math.min(1, f)) * 100) / 100;
        }
    }
    return s;
}

// ---------- what the games' code calls each sound (rw_sound.py, fight_sound.py) ----------
const HITS = {spinner: "smash", drum: "launch", hammer: "hammer", flip: "flip", saw: "saw", spikes: "spikes",
              bump: "bump", wall: "wall", flame: null, break: "smash"};
const ALIASES = {crunch: "hammer"};
const FIGHT_HITS = {punch: [["punch", 1.0]], kick: [["kick", 1.0]], low: [["kick", 0.9]], high: [["heavy", 1.0]],
                    special: [["heavy", 1.0]], blast: [["blast_hit", 1.0]], counter: [["counter", 1.0], ["heavy", 0.8]],
                    block: [["block", 1.0]], throw: [["slam", 0.8]], zap: [["zap", 1.0]], fire: [["fire", 1.0]],
                    wall: [["wall", 0.9]], spikes: [["heavy", 0.9], ["wall", 0.6]], land: [["land", 1.0]], ringout: [["slam", 0.7]]};
const METAL = {punch: 0.5, kick: 0.6, low: 0.5, high: 0.7, special: 0.8, blast: 0.5, counter: 0.8, block: 0.3, throw: 0.6,
               wall: 0.5, land: 0.4};
const SWINGS = {punch: ["whoosh", 0.45, 1.25], kick: ["whoosh", 0.6, 0.9], low: ["whoosh", 0.5, 0.85], high: ["whoosh", 0.7, 0.8],
                jump_kick: ["whoosh", 0.6, 0.9], throw: ["whoosh", 0.4, 0.7], blast: ["blast_fire", 0.9, 1.0],
                uppercut: ["uppercut", 0.9, 1.0], spin_kick: ["spin", 0.9, 1.0], slam: ["whoosh", 0.6, 0.6],
                jump: ["jump", 0.6, 1.0], cartwheel: ["spin", 0.9, 0.8]};
const ATTACK_ANIMS = new Set(["punch", "kick", "low", "high", "jump_kick", "throw", "blast", "uppercut", "spin_kick", "slam", "cartwheel"]);
const REACT_GAP = {ooh: 2.5, cheer: 3.0, applause: 0.0};
const SPIN_SOUNDS = {spinner: "spin", drum: "spin_drum", vdisc: "spin_disc"};  // rw_sound.SPIN_SOUNDS
const INTRO = [2.5, 5.0, 8.0];  // lab_client.INTRO: the arena's name, who is fighting, then 3, 2, 1
const HOUSE_WEAPONS = {BLAZE: "flame", CRUSHER: "hammer", RIPSAW: "chainsaw", VORTEX: "vdisc"};
const FLAGS_RACE = 1, FLAG_DRIFT = 1 | 2, FLAG_FINISHED = 4, FLAG_BOOSTING = 16, FLAG_SPINNING = 64 | 128;  // kart_sim.py (CHANGE 181: wheelspin, the handbrake)
const BUMP_DISTANCE = 1.7;  // kart_sim.BUMP_DISTANCE
const MAX_SAME = 6;         // copies of one sound playing at once (the app's pool: 3 versions x 2)
const STALE_MS = 500;       // a loop not set again for this long stops

const clamp01 = v => Math.max(0, Math.min(1, v));
const dist = (a, b) => (a && b) ? Math.hypot(a[0] - b[0], a[1] - b[1], (a[2] || 0) - (b[2] || 0)) : 0;

function decode(ctx, data) {  // (older Safari has only the callback form)
    return new Promise((ok, bad) => {
        const p = ctx.decodeAudioData(data, ok, bad);
        if (p && p.then) p.then(ok, bad);
    });
}

export class Sound {
    // base: where sfx/ is; storageKey: where this browser keeps the settings (null: not kept); muted: start muted
    constructor({base = "sfx/", storageKey = "cc-sound", muted = false, settings = null} = {}) {
        this.base = base.endsWith("/") ? base : base + "/";
        this.storageKey = storageKey;
        this.own = settings || this._stored();   // this browser's own settings (null: the lesson's, else the defaults)
        this.settings = soundSettings(this.own);
        this.muted = muted;
        this.ctx = null;
        this.master = null;
        this.manifest = null;
        this.manifestLoading = null;
        this.buffers = new Map();      // file -> AudioBuffer
        this.loading = new Map();      // file -> Promise
        this.starts = new Map();       // file -> seconds to skip (a decoder's delay before a one-shot's onset)
        this.playing = new Map();      // name -> [{src, gain, file, at}]
        this.loops = new Map();        // key -> {src, gain, name, file, at}
        this.game = null;
        this.crowdVolume = 0.6;
        this.lastReaction = -99;
        this._resetDirectors();
        this._unlock = () => this.unlock();
        for (const ev of ["pointerdown", "keydown", "touchend"]) window.addEventListener(ev, this._unlock, {capture: true});
        this._watch = setInterval(() => this._sweep(), 250);
    }

    _stored() {
        if (!this.storageKey) return null;
        try {
            const raw = localStorage.getItem(this.storageKey);
            return raw ? JSON.parse(raw) : null;
        } catch (e) { return null; }
    }

    _resetDirectors() {
        this._r = {fireCounts: new Map(), wasKo: new Map(), lastWinner: null, introWas: false, beeped: new Set()};
        this._f = {lastPhase: new Map(), lastWinner: new Map(), lastAnim: new Map(), lastBanner: new Map()};
        this._k = {wasBoosting: false, wasFinished: false, cdLast: null, race: null, raceAt: 0, near: new Set(), bumpAt: 0, me: null};
    }

    // ---------- starting (after a click or a key) ----------
    get ready() { return !!(this.ctx && this.manifest && this.ctx.state === "running"); }

    // Make the audio context and fetch the manifest. Called by the first click or key on the page (call it from
    // your own click handler too if you like: it does nothing the second time).
    unlock() {
        const AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        if (!this.ctx) {
            this.ctx = new AC();
            this.master = this.ctx.createGain();
            this.master.gain.value = this.muted ? 0 : 1;
            this.master.connect(this.ctx.destination);
        }
        this._loadManifest();
        const done = () => {  // (running: the page's clicks needn't call this again)
            if (this.ctx && this.ctx.state === "running") {
                for (const ev of ["pointerdown", "keydown", "touchend"]) window.removeEventListener(ev, this._unlock, {capture: true});
            }
        };
        if (this.ctx.state !== "running") this.ctx.resume().then(done, () => {});
        else done();
    }

    _loadManifest() {
        if (this.manifest || this.manifestLoading) return this.manifestLoading;
        this.manifestLoading = fetch(this.base + "manifest.json", {cache: "no-cache"})
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`sfx/manifest.json: ${r.status}`)))
            .then(m => { this.manifest = m; if (this.game) this.use(this.game); })
            .catch(e => { console.warn("Sound:", e.message || e); this.manifestLoading = null; });
        return this.manifestLoading;
    }

    // Which game is on: its sounds are fetched now (the directors call this themselves). Changing game stops
    // everything playing and forgets the last game's state.
    use(game) {
        if (game !== this.game) {
            this.stopAll();
            this._resetDirectors();
            this.game = game;
        }
        if (!this.manifest || !this.ctx) return;
        if (this._preloaded === game) return;
        this._preloaded = game;
        for (const name of (this.manifest.games || {})[game] || []) {
            const info = this.manifest.sounds[name];
            if (info && info.channel !== "music") for (const f of info.files) this._load(f, info);
        }
    }

    _load(file, info) {
        if (this.buffers.has(file)) return Promise.resolve(this.buffers.get(file));
        if (this.loading.has(file)) return this.loading.get(file);
        const p = fetch(this.base + file)
            .then(r => r.ok ? r.arrayBuffer() : Promise.reject(new Error(`${file}: ${r.status}`)))
            .then(data => decode(this.ctx, data))
            .then(buf => {
                this.buffers.set(file, buf);
                if (!info.loop) this.starts.set(file, this._lead(buf, info, info.files.indexOf(file)));
                return buf;
            })
            .catch(e => { console.warn("Sound:", e.message || e); this.loading.delete(file); return null; });
        this.loading.set(file, p);
        return p;
    }

    // a one-shot's onset found again in the decoded sound: some browsers keep the MP3 encoder's delay (25 ms)
    _lead(buf, info, i) {
        const data = buf.getChannelData(0);
        let peak = 0;
        for (let k = 0; k < data.length; k++) { const a = Math.abs(data[k]); if (a > peak) peak = a; }
        if (!peak) return 0;
        const level = (this.manifest.onset_threshold || 0.05) * peak, end = Math.min(data.length, Math.round(buf.sampleRate * 0.25));
        let k = 0;
        while (k < end && Math.abs(data[k]) <= level) k++;
        const lead = k / buf.sampleRate - ((info.onset || [])[i] || 0);
        return lead < 0.005 ? 0 : Math.min(0.1, lead);  // (Chrome trims the delay itself: within 2 ms, left alone)
    }

    // the decoded buffer for one of a sound's versions, or null (and its loading started)
    _buffer(info, file) {
        const buf = this.buffers.get(file);
        if (buf) return buf;
        this._load(file, info);
        return null;
    }

    // ---------- settings ----------
    // The lesson's sound settings: the start for a browser that has none of its own (as the windows' my_sound)
    setLesson(lessonSound) {
        if (!this.own) this.settings = soundSettings(lessonSound || null);
    }

    // Change settings ({music: "rock"}, {crowd_volume: 0.8}...): checked, applied and kept for next time (and
    // onChange(settings) told: CHANGE 143, a learner's go to their profile as the windows keep them, prefs.sound)
    set(change) {
        this.own = soundSettings(this.settings, change);
        this.settings = this.own;
        if (this.storageKey) {
            try { localStorage.setItem(this.storageKey, JSON.stringify(this.own)); } catch (e) { /* storage blocked */ }
        }
        if (this.onChange) this.onChange(this.settings);
        return this.settings;
    }

    // (CHANGE 143) a learner's own settings from their profile (the windows' prefs.sound, rw_sound.sound_settings'
    // format): this browser's from now on, as their window takes them from the profile
    useOwn(saved) {
        this.own = soundSettings(saved);
        this.settings = this.own;
        if (this.storageKey) {
            try { localStorage.setItem(this.storageKey, JSON.stringify(this.own)); } catch (e) { /* storage blocked */ }
        }
        return this.settings;
    }

    // a channel's level from the settings (0 when switched off or muted)
    level(channel) {
        const ch = CHANNELS[channel];
        if (!ch || this.muted) return this.muted ? 0 : 1;
        const [on, vol] = ch;
        if (channel === "music") return this.settings.music === "off" ? 0 : this.settings.music_volume;
        return this.settings[on] ? this.settings[vol] : 0;
    }

    setMuted(muted) {
        this.muted = !!muted;
        if (this.muted) this.stopAll();
        if (this.master) this.master.gain.setTargetAtTime(this.muted ? 0 : 1, this.ctx.currentTime, 0.02);
        return this.muted;
    }

    toggleMute() { return this.setMuted(!this.muted); }

    // ---------- playing ----------
    // A one-shot. opts: volume (0-1, default 1), rate (default 1; a little randomness is added as the app does unless
    // vary is false), channel (apply that setting), at + listener (game points [x, y, z]: quieter further away,
    // falloff metres to the quietest, floor the quietest fraction: the windows' 30 and 0.15), pan (-1 to 1).
    play(name, opts = {}) {
        name = ALIASES[name] || name;
        if (this.muted || !this.ready) return null;
        const info = this.manifest.sounds[name];
        if (!info) return null;
        let volume = opts.volume ?? 1;
        if (opts.channel) volume *= this.level(opts.channel);
        if (opts.at && opts.listener) volume *= Math.max(opts.floor ?? 0.15, 1 - dist(opts.at, opts.listener) / (opts.falloff ?? 30));
        volume = clamp01(volume);
        if (volume <= 0) return null;
        // a version not already playing (the app picks a free copy from its pool), else any
        const list = this.playing.get(name) || [];
        const busy = new Set(list.map(p => p.file));
        const ready = info.files.filter(f => this.buffers.has(f));
        info.files.forEach(f => this._buffer(info, f));
        if (!ready.length) return null;
        const free = ready.filter(f => !busy.has(f));
        const pick = (free.length ? free : ready);
        const file = pick[Math.floor(Math.random() * pick.length)];
        const ctx = this.ctx, src = ctx.createBufferSource(), gain = ctx.createGain();
        src.buffer = this.buffers.get(file);
        src.playbackRate.value = Math.max(0.05, (opts.rate ?? 1) * (opts.vary === false ? 1 : 0.95 + Math.random() * 0.1));
        gain.gain.value = volume;
        let out = gain;
        if (opts.pan && ctx.createStereoPanner) {
            const p = ctx.createStereoPanner();
            p.pan.value = Math.max(-1, Math.min(1, opts.pan));
            gain.connect(p);
            out = p;
        }
        src.connect(gain);
        out.connect(this.master);
        const rec = {src, gain, file, at: performance.now()};
        list.push(rec);
        while (list.length > MAX_SAME) { const old = list.shift(); try { old.src.stop(); } catch (e) { /* already stopped */ } }
        this.playing.set(name, list);
        src.onended = () => {
            const still = this.playing.get(name);
            if (still) { const i = still.indexOf(rec); if (i >= 0) still.splice(i, 1); }
            gain.disconnect();
            if (out !== gain) out.disconnect();
        };
        src.start(0, info.loop ? 0 : (this.starts.get(file) || 0));
        return src;
    }

    // Start or adjust a looping sound under a key (one per spinner: "spin3"). Call it every frame while it should
    // sound: set to 0 it keeps its place, and not called for half a second it stops. opts: channel.
    loop(key, name, volume = 1, rate = 1, opts = {}) {
        if (this.muted || !this.ready) return;
        const info = this.manifest.sounds[name];
        if (!info) return;
        if (opts.channel) volume *= this.level(opts.channel);
        volume = clamp01(volume);
        rate = Math.max(0.2, rate);
        let L = this.loops.get(key);
        if (L && L.name !== name) { this.stop(key); L = null; }
        const t = this.ctx.currentTime;
        if (!L) {
            const file = info.files[0], buf = this._buffer(info, file);
            if (!buf) return;
            const src = this.ctx.createBufferSource(), gain = this.ctx.createGain();
            src.buffer = buf;
            src.loop = true;
            const start = info.loop_start || 0, len = info.loop_len || buf.duration;
            src.loopStart = start;
            src.loopEnd = Math.min(buf.duration, start + len);
            src.playbackRate.value = rate;
            gain.gain.value = 0;
            src.connect(gain);
            gain.connect(this.master);
            src.start(0, start);
            L = {src, gain, name, file};
            this.loops.set(key, L);
        }
        L.at = performance.now();
        L.gain.gain.setTargetAtTime(volume, t, 0.03);       // (eased a little, so a speed change never clicks)
        L.src.playbackRate.setTargetAtTime(rate, t, 0.04);
    }

    // a loop's volume or rate alone (it must be playing: started with loop())
    setVolume(key, volume) {
        const L = this.loops.get(key);
        if (!L) return;
        L.at = performance.now();
        L.gain.gain.setTargetAtTime(clamp01(volume), this.ctx.currentTime, 0.03);
    }

    setRate(key, rate) {
        const L = this.loops.get(key);
        if (!L) return;
        L.at = performance.now();
        L.src.playbackRate.setTargetAtTime(Math.max(0.2, rate), this.ctx.currentTime, 0.04);
    }

    has(key) { return this.loops.has(key); }

    stop(key) {
        const L = this.loops.get(key);
        if (!L) return;
        this.loops.delete(key);
        const t = this.ctx.currentTime;
        L.gain.gain.setTargetAtTime(0, t, 0.02);
        try { L.src.stop(t + 0.1); } catch (e) { /* already stopped */ }
        L.src.onended = () => L.gain.disconnect();
    }

    // stop every loop whose key starts with prefix, except those in keys (spinners no longer spinning)
    keepOnly(prefix, keys) {
        for (const key of [...this.loops.keys()]) if (key.startsWith(prefix) && !keys.has(key)) this.stop(key);
    }

    stopAll() {
        for (const key of [...this.loops.keys()]) this.stop(key);
        for (const list of this.playing.values()) for (const p of list) { try { p.src.stop(); } catch (e) { /* stopped */ } }
        this.playing.clear();
    }

    _sweep() {
        const now = performance.now();
        for (const [key, L] of [...this.loops]) if (now - L.at > STALE_MS) this.stop(key);
    }

    dispose() {
        this.stopAll();
        clearInterval(this._watch);
        for (const ev of ["pointerdown", "keydown", "touchend"]) window.removeEventListener(ev, this._unlock, {capture: true});
        if (this.ctx) this.ctx.close().catch(() => {});
        this.ctx = null;
    }

    // ---------- rw_sound.Sounds ----------
    // a contact: the right sound for what hit what (Robot Lab's kinds)
    hit(kind, volume) {
        const name = kind in HITS ? HITS[kind] : "clang";
        if (name) this.play(name, {volume});
    }

    // a spinning weapon's motor (weapon: spinner, drum or vdisc, each its own: rw_sound.SPIN_SOUNDS): the pitch
    // follows its speed, so it bogs down on a hit and winds back up
    spinner(key, rpm, volume, weapon = "spinner") {
        const name = SPIN_SOUNDS[weapon] || "spin", p = this._pitch(name) || this._pitch("spin");
        if (rpm < p.min_rpm || volume <= 0) { this.stop(key); return; }
        this.loop(key, name, Math.min(p.volume_max, p.volume[0] + rpm * p.volume[1]) * volume, p.rate[0] + rpm * p.rate[1]);
    }

    // the countdown's voice (rw_sound.Sounds.say): word is 3, 2, 1, "activate" or "go", at its own pitch
    say(word, volume = 1) {
        const name = `say_${word}`;
        for (const p of this.playing.get(name) || []) { try { p.src.stop(); } catch (e) { /* stopped */ } }
        this.play(name, {volume, vary: false});
    }

    _pitch(name) {
        const m = this.manifest && this.manifest.sounds[name] && this.manifest.sounds[name].pitch;
        if (m) return m;
        return {spin: {min_rpm: 30, rate: [0.3, 1 / 380], volume: [0.12, 1 / 900], volume_max: 0.7},
                motor: {robot: {rate: [0.6, 1 / 8], volume_per_speed: 1 / 20, volume_driven: 0.04, volume_max: 0.25},
                        kart: {rate: [0.55, 1.3], volume: [0.18, 0.3], boost_rate: 0.25, boost_volume: 0.12}},
                k_skid: {min_speed: 6, rate: [0.9, 0.3], volume: [0.35, 0.2]}}[name];
    }

    // the background layers, every frame: any mix of music, the crowd and the arena hum
    layers(music = "off", musicVolume = 0.5, crowd = true, crowdVolume = 0.6, arena = false, arenaVolume = 0.4) {
        if (this.muted) { this.crowdVolume = 0; return; }
        if (music === "chip" || music === "rock") this.loop("music", music, musicVolume * 0.6);
        else this.stop("music");
        this.crowdVolume = crowd ? crowdVolume : 0;
        if (this.crowdVolume > 0) this.loop("crowd", "crowd", this.crowdVolume * 0.7);
        else this.stop("crowd");
        if (arena && arenaVolume > 0) this.loop("arena", "arena", arenaVolume * 0.6);
        else this.stop("arena");
    }

    // the crowd reacts: "ooh" (a big hit), "cheer" (a flip or a knockout), "applause" (the end); now in seconds
    react(what, now = performance.now() / 1000) {
        if (this.crowdVolume <= 0 || now - this.lastReaction < REACT_GAP[what]) return;
        this.lastReaction = now;
        this.play(what, {volume: Math.min(1, this.crowdVolume * 1.2)});
    }

    // ---------- Robot Lab (lab_client.py) ----------
    // Every frame. arena: the watched arena's state ({robots, hz, winner}: the latest message's, or blended);
    // msg: the state message's top ({intro, paused}); impacts: the arena's fx.impacts ([[pos, dmg, kind]...])
    // that arrived since the last call (or null); myRobotId: the robot whose drive motor is heard (the
    // teacher's own, else null). opts: listener (the camera as a game point [x, y, z]: Sound.listenerFrom(camera)),
    // weapons (id -> weapon: Sound.robotWeapons(roster.robots)), driving (the teacher is pressing drive keys),
    // now (seconds).
    robotFrame(arena, msg, impacts, myRobotId = null, opts = {}) {
        this.use("robotlab");
        const s = this.settings, now = opts.now ?? performance.now() / 1000, cam = opts.listener || null;
        if (this.muted) this.layers("off", 0, false, 0, false, 0);
        else this.layers(s.music, s.music_volume, s.crowd, s.crowd_volume, s.arena, s.arena_volume);
        for (const [pos, dmg, kind] of impacts || []) this._robotHit(pos, dmg, kind, now, cam);
        if (arena) this._machines(arena, msg || {}, myRobotId, opts, now, cam);
        else { this.stop("grind"); this.keepOnly("spin", new Set()); this.stop("flame"); this.stop("chainsaw"); this.stop("motor"); }
        this._intro(msg ? msg.intro : null, now);
    }

    // lab_client.hit_sound: quieter further from the camera, and the crowd's reaction
    _robotHit(pos, dmg, kind, now, cam) {
        const s = this.settings;
        if (this.muted) return;
        if (s.effects) {
            const far = dist(pos, cam);
            this.hit(kind, Math.min(1, 0.3 + dmg / 25) * Math.max(0.15, 1 - far / 30) * s.volume * 1.4);
        }
        if (kind === "flip" || kind === "break") this.react("cheer", now);
        else if (dmg >= 15 && kind !== "bump" && kind !== "wall") this.react("ooh", now);
    }

    // lab_client.machine_sounds: a floor saw grinding, each spinner's motor, flame throwers, chainsaws, flippers
    // firing, hammers swinging, your own drive motor; a knockout's cheer and the end's applause
    _machines(st, top, myId, opts, now, cam) {
        const s = this.settings, R = this._r, weapons = opts.weapons || {};
        const weapon = id => weapons instanceof Map ? weapons.get(id) : weapons[id];
        const hits = (this.muted || !s.effects) ? 0 : s.volume;
        const vol = (this.muted || !s.weapons) ? 0 : s.weapons_volume;
        const drive = (this.muted || !s.motors) ? 0 : s.motors_volume;
        const robots = st.robots || [];
        if (hits && ((st.hz && st.hz.saw_hot) || []).some(Boolean)) this.loop("grind", "grind", 0.5 * hits);
        else this.stop("grind");
        const near = r => Math.max(0.1, 1 - dist(r.pos, cam) / 25);
        const live = robots.filter(r => !r.ko);
        const spinners = live.filter(r => r.rpm > 30).sort((a, b) => near(b) - near(a)).slice(0, 4);
        for (const r of spinners) this.spinner(`spin${r.id}`, r.rpm, near(r) * vol, weapon(r.id));  // the four nearest
        this.keepOnly("spin", new Set(spinners.map(r => `spin${r.id}`)));
        const flames = live.filter(r => r.fl);
        if (vol && flames.length) this.loop("flame", "flame", 0.6 * vol * Math.max(...flames.map(near)));
        else this.stop("flame");
        const saws = live.filter(r => r.act && weapon(r.id) === "chainsaw");
        if (vol && saws.length) this.loop("chainsaw", "chainsaw", 0.55 * vol * Math.max(...saws.map(near)));
        else this.stop("chainsaw");
        for (const r of robots) {  // a flipper firing, a hammer swinging
            const fc = r.fc || 0, was = R.fireCounts.has(r.id) ? R.fireCounts.get(r.id) : fc;
            R.fireCounts.set(r.id, fc);
            const kind = weapon(r.id);
            if (fc > was && vol && (kind === "wedge" || kind === "hammer")) this.play(kind === "wedge" ? "pneumatic" : "swing", {volume: 0.8 * vol * near(r)});
        }
        const mine = myId === null || myId === undefined ? null : live.find(r => r.id === myId);
        if (drive && mine) {  // no idle hum: a robot standing still is silent, and the sound comes in as it moves
            const p = this._pitch("motor").robot, speed = Math.abs(mine.speed || 0);
            const driven = !!opts.driving && (top.intro === null || top.intro === undefined) && !top.paused;
            const power = Math.max(Math.max(0, speed - 0.1) * p.volume_per_speed, driven ? p.volume_driven : 0);
            this.loop("motor", "motor", Math.min(p.volume_max, power) * drive, p.rate[0] + speed * p.rate[1]);
        } else {
            this.stop("motor");
        }
        for (const r of robots) {
            if (r.ko && !R.wasKo.get(r.id)) this.react("cheer", now);
            R.wasKo.set(r.id, r.ko);
        }
        if (st.winner && st.winner !== R.lastWinner) this.react("applause", now);
        R.lastWinner = st.winner || null;
    }

    // lab_client.show_intro's sounds: a robot's voice says 3, 2, 1, then "Activate" with a cheer at ACTIVATE!
    // (CHANGE 153; t: seconds of it gone)
    _intro(t, now) {
        const s = this.settings, R = this._r;
        const loud = (this.muted || !s.effects) ? 0 : Math.min(1, s.volume / 0.7);
        const on = t !== null && t !== undefined;
        if (on) {
            if (!R.introWas || t < 1.0) R.beeped = new Set([3, 2, 1].filter(n => t > INTRO[1] + (4 - n)));  // (joined part-way)
            if (t >= INTRO[1]) {
                const n = Math.max(1, 3 - Math.floor(t - INTRO[1]));
                if (!R.beeped.has(n)) {
                    R.beeped.add(n);
                    this.say(n, 0.9 * loud);
                }
            }
        } else if (R.introWas) {
            this.say("activate", 0.9 * loud);
            if (!this.muted) this.react("cheer", now);
        }
        R.introWas = on;
    }

    // ---------- Fight Lab (fight_client.py) ----------
    // Every frame. rings: the state's rings ([{i, ph, bn, f: [{id, a, k, pos}]}]: the latest message's, or
    // blended); impacts: the message's fx ([[pos, dmg, kind]...]) that arrived since the last call (or null);
    // watchedRing: the ring the camera follows (FightGame.watched()). opts: robots (the fighter ids with a robot
    // body: Sound.fightRobots(roster.fighters), or a function id -> bool), listener, now.
    fightFrame(rings, impacts, watchedRing, opts = {}) {
        this.use("fightlab");
        const s = this.settings, now = opts.now ?? performance.now() / 1000, cam = opts.listener || null;
        rings = rings || [];
        if (this.muted) this.layers("off", 0, false, 0, false, 0);
        else this.layers(s.music, s.music_volume, s.crowd, s.crowd_volume, false, 0);
        const robots = opts.robots;
        const isRobot = id => typeof robots === "function" ? !!robots(id) : robots ? robots.has(id) : true;
        const all = rings.flatMap(r => r.f || []);
        for (const [pos, dmg, kind] of impacts || []) {  // draw_state: each hit by the fighter it landed on
            let victim = null, best = Infinity;
            for (const f of all) { const d = dist(f.pos, pos); if (d < best) { best = d; victim = f; } }
            const robot = victim ? isRobot(victim.id) : true;
            if (!this.muted && s.effects) {
                const far = dist(pos, cam);
                this.fightHit(kind, Math.min(1, 0.35 + dmg / 20) * Math.max(0.15, 1 - far / 30) * s.volume * 1.3, robot);
                if (kind === "counter" || dmg >= 14) this.react("ooh", now);
            }
        }
        this._fightEvents(rings, watchedRing, now);
    }

    // fight_sound.FightSounds.hit: a contact (a robot's hits have a clang of metal on top)
    fightHit(kind, volume, robot = false) {
        for (const [name, loud] of FIGHT_HITS[kind] || [["punch", 1.0]]) this.play(name === "wall" ? "wall" : "f_" + name, {volume: volume * loud});
        if (robot && kind in METAL) this.play("f_metal", {volume: volume * METAL[kind]});
    }

    // fight_sound.FightSounds.swing: an attack starting (a whoosh, or the special's own sound)
    swing(move, volume) {
        const [name, loud, speed] = SWINGS[move] || ["whoosh", 0.5, 1.0];
        this.play("f_" + name, {volume: volume * loud, rate: speed});
    }

    // fight_client.event_sounds: moves starting, the count's voice and the bell, knockouts and wins, the crowd's reactions
    _fightEvents(rings, watched, now) {
        const s = this.settings, F = this._f;
        const on = !this.muted && s.effects, vol = s.volume;  // (the state is kept while quiet, so nothing old plays later)
        for (const r of rings) {
            const near = r.i === watched ? 1.0 : 0.25, phase = F.lastPhase.get(r.i);
            const loud = Math.min(1, vol / 0.7);
            if (on && phase === "intro" && r.ph === "fight" && r.i === watched) { this.play("f_bell", {volume: 0.9}); this.say("go", 0.9 * loud); }
            else if (on && r.ph === "intro" && ["3", "2", "1"].includes(r.bn) && r.i === watched && F.lastBanner.get(r.i) !== r.bn) this.say(Number(r.bn), 0.9 * loud);
            F.lastBanner.set(r.i, r.bn);
            if (on && phase === "fight" && r.ph === "ko") {
                if (r.i === watched) this.play("f_ko", {volume: 1.0});
                this.react("cheer", now);
            }
            if (on && r.ph === "over" && F.lastWinner.get(r.i) !== r.bn) this.react("applause", now);
            F.lastWinner.set(r.i, r.ph === "over" ? r.bn : "");
            F.lastPhase.set(r.i, r.ph);
            for (const f of r.f || []) {
                const a = f.a, last = F.lastAnim.get(f.id);
                if (ATTACK_ANIMS.has(a) && (!last || last[0] !== a || f.k < last[1] - 0.5) && f.k < 1.5) {
                    if (on) this.swing(a, 0.7 * vol * near);
                } else if (a === "jump" && (!last || last[0] !== "jump")) {
                    // (the window asks for "jump", which its pool names "f_jump", so it is silent there: this is the
                    // sound fight_sound.py made for it)
                    if (on) this.play("f_jump", {volume: 0.4 * vol * near});
                }
                F.lastAnim.set(f.id, [a, f.k]);
            }
        }
    }

    // ---------- Kart Lab (kart_client.py, kart_sound.py) ----------
    // Every frame. me: the kart heard (the one the camera chases, or the teacher's own; null for none): a
    // snapshot entity ({id, x, y, v, flags}, blended is fine); race: the latest "race" message ({phase, go_in_ms,
    // places}; its `at`, Date.now() when it came, as kart.js sets it, else when this first saw it). opts: top (the
    // kart's top speed in m/s: Sound.kartTop(design)), place (1 = leading; else worked out from race.places),
    // karts (Map id -> entity: bumps are heard when another kart comes within reach of yours), now (ms, Date.now()).
    kartFrame(me, race, opts = {}) {
        this.use("kartlab");
        const K = this._k, now = opts.now ?? Date.now();
        if (race !== K.race) { K.race = race; K.raceAt = now; }
        const phase = race ? race.phase : 0;
        let goAt = null;
        if (race && race.go_in_ms !== null && race.go_in_ms !== undefined) goAt = (race.at ?? K.raceAt) + race.go_in_ms;
        const frozen = phase !== FLAGS_RACE || (goAt !== null && now < goAt);
        const racing = phase === FLAGS_RACE && !frozen;
        // the window has one switch (mute); the page's settings scale it, and at their defaults it is the window
        const rel = ch => { const [on, v] = CHANNELS[ch]; return this.settings[on] ? this.settings[v] / DEFAULT_SOUND[v] : 0; };
        const fx = rel("effects"), motors = rel("motors");
        if (this.muted) this.crowdVolume = 0;
        else this.layers("off", 0, racing, 0.3 * rel("crowd"), false, 0);  // (the crowd murmurs while there is a race on)
        if (me) {
            const flags = me.flags || 0, top = opts.top || 24.3;  // (24.3: kart_sim.stats_of for the default 33 points)
            const boosting = !!(flags & FLAG_BOOSTING), drifting = !!(flags & FLAG_DRIFT), spinning = !!(flags & FLAG_SPINNING);
            const v = me.v || 0, speed = Math.min(1, Math.abs(v) / Math.max(1, top));
            const e = this._pitch("motor").kart, sk = this._pitch("k_skid");
            if (!this.muted) {  // KartSounds.update (CHANGE 181: the back wheels spinning or locked squeal at any speed, the engine screams)
                const revs = spinning && Math.abs(v) < 6 ? 0.35 : 0;
                this.loop("engine", "motor", (e.volume[0] + e.volume[1] * speed + (boosting ? e.boost_volume : 0) + revs * 0.4) * motors,
                          e.rate[0] + e.rate[1] * speed + (boosting ? e.boost_rate : 0) + revs * 2.0);
                if (spinning) this.loop("skid", "k_skid", (0.5 + 0.1 * speed) * motors, 1.05 + 0.2 * speed);
                else if (drifting && Math.abs(v) > sk.min_speed) this.loop("skid", "k_skid", (sk.volume[0] + sk.volume[1] * speed) * motors, sk.rate[0] + sk.rate[1] * speed);
                else this.stop("skid");
            }
            if (boosting && !K.wasBoosting) this.play("k_boost", {volume: 0.8 * fx});
            K.wasBoosting = boosting;
            const finished = !!(flags & FLAG_FINISHED);
            if (finished && !K.wasFinished) {
                const places = (race && race.places) || [];
                const place = opts.place ?? (places.indexOf(me.id) + 1);
                this.play("horn", {volume: 0.9 * fx});
                this.react(place === 1 ? "cheer" : "applause", now / 1000);
            }
            K.wasFinished = finished;
            this._kartBumps(me, opts.karts, frozen, fx, now);
        } else {
            this.stop("engine");
            this.stop("skid");
        }
        // the countdown: 3, 2, 1 beeps and GO (kart_client.sounds)
        let cd = phase === FLAGS_RACE && goAt !== null ? Math.max(0, goAt - now) / 1000 : null;
        if (cd !== null && cd <= 0 && now - goAt > 1500) cd = null;
        const n = cd === null ? null : Math.ceil(cd - 1e-6);
        if (n !== K.cdLast && n !== null && n >= 0 && n <= 3) this.play(n === 0 ? "go" : "beep", {volume: 0.8 * fx});
        K.cdLast = n;
    }

    // a bump: the window hears its prediction being corrected; the page hears another kart come within reach
    _kartBumps(me, karts, frozen, fx, now) {
        const K = this._k;
        if (!karts || K.me !== me.id) { K.near = new Set(); K.me = me.id; }
        if (!karts) return;
        const near = new Set();
        for (const [id, k] of karts instanceof Map ? karts : Object.entries(karts).map(([i, k]) => [Number(i), k])) {
            if (id === me.id || !k) continue;
            if (Math.hypot(k.x - me.x, k.y - me.y) < BUMP_DISTANCE + 0.05) {
                near.add(id);
                if (!K.near.has(id) && !frozen && now - K.bumpAt > 250) {
                    K.bumpAt = now;
                    this.play("bump", {volume: Math.min(1, 0.45 + 0.05 * Math.abs((me.v || 0) - (k.v || 0))) * fx});
                }
            }
        }
        K.near = near;
    }

    // ---------- helpers for the games' files ----------
    // the camera as a game point (base3d.v3 swaps y and z): pass a Babylon camera
    static listenerFrom(camera) {
        const p = camera.globalPosition || camera.position;
        return [p.x, p.z, p.y];
    }

    // Robot Lab: each robot's weapon from the roster's robots (as robot.js builds them: lab_sim.design_weapon)
    static robotWeapons(robots) {
        const out = new Map();
        for (const r of robots || []) {
            const d = r.design || {};
            out.set(r.id, d.weapon || HOUSE_WEAPONS[d.model] || "wedge");
        }
        return out;
    }

    // Fight Lab: the fighters with a robot body (fight_client: design.body, a robot unless it says otherwise)
    static fightRobots(fighters) {
        return new Set((fighters || []).filter(f => ((f.design || {}).body || "robot") === "robot").map(f => f.id));
    }

    // Kart Lab: a kart's top speed in m/s (kart_sim.stats_of)
    static kartTop(design) {
        return 17.0 + 0.22 * ((design || {}).speed ?? 33);
    }
}
