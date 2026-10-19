// Kart Lab in Club Coders Live: the binary snapshots (wire.js), the race, the places, the race controls and the
// cameras. The teacher tabs every game shares (learners, outcomes, AI cards, rules) are teacher.js's.

import {KART_FIELDS, KIND_SNAPSHOT, kindOf, unpackSnapshot} from "./wire.js";
import {Track, TRACKS} from "./track.js";
import {KartScene} from "./scene.js";
import {KartHud} from "./hud.js";
import {STEP, FLAGS_RACE, FLAG_FINISHED, BUMP_DISTANCE, DAMAGE_PARTS, PIT_SPEED, statsOf, fullState, makeStep, compare, coast} from "./kart_sim.js";
import {Predictor, InputLog, ErrorSmoother, LeadController, quantiseInput, packInput} from "./predict.js";
import {Sound} from "./sound.js";

const $ = id => document.getElementById(id);
// (CHANGE 159) the power-ups (kart_items.ITEMS), their codes 1 to 5 in this order, and their names on the screen
export const ITEM_NAMES = [["boost", "Boost"], ["oil", "Oil slick"], ["shot", "Bouncing shot"], ["homing", "Homing shot"], ["shield", "Shield"]];

export class KartGame {
    static detect(m) { return !!(m.rules && m.rules.tracks && m.track); }

    constructor(app) {
        this.app = app;
        this.id = "kartlab";
        this.title = "Kart Lab";
        this.word = "kart";
        this.scene = new KartScene(app.canvas, app.tier, app.engine);
        this.scene.setTrack(new Track(TRACKS.club));
        this.track = this.scene.track;
        this.trackKey = "";
        this.race = null;
        this.mods = ["mods/track.py", "mods/rules.py", "mods/karts/<username>.py"];
        this.controlKind = "kart";  // (play.js: the arrows or WASD drive, Shift or Space drifts, R respawns)
        this.hud = new KartHud();
        // your own kart, predicted as the window predicts it (kart_client: kart_sim.step on each 1/60 s tick with
        // your keys, sent as the 18-byte binary input; when a snapshot says which input the server applied, the
        // prediction is checked against it and, if it was wrong, put right and the inputs since replayed; the
        // picture eases over the correction instead of jumping)
        this.predictor = null;
        this.smoother = new ErrorSmoother({removeUp: true});
        this.lead = new LeadController();
        this.nextSeq = 0;
        this.snapSeq = 0;
        this.accum = 0;
        this.sentAt = new Map();
        this.mine = null;
        this.drawFrom = null;   // the predicted state before the newest tick: the kart is drawn between it and the
                                // newest, as far as the time since that tick (CHANGE 155)
        this.predStats = null;  // the stats the prediction steps with (a new design or track: predicted afresh)
        // (CHANGE 155) the other karts as the prediction sees them: from each snapshot, carried on a tick a step, so
        // a bump against one is predicted as the server makes it (bump_distance and bump_slowdown: the rules')
        this.world = {others: [], reach: BUMP_DISTANCE, slow: 0.3};
    }

    // the other karts in a snapshot, as copies the prediction may move
    setOthers(snap, id) {
        const R = this.app.state.rules || {}, b = R.bump || {};
        this.world.reach = Number.isFinite(b.distance) ? b.distance : BUMP_DISTANCE;
        this.world.slow = Number.isFinite(b.slowdown) ? b.slowdown : 0.3;
        const karts = new Map((((this.app.state.roster || {}).karts) || []).map(k => [k.id, k]));
        this.world.others = snap.entities.filter(e => e.id !== id).map(e => {  // (their steering and stats: CHANGE 159)
            const st = statsOf((karts.get(e.id) || {}).design || {});
            return {x: e.x, y: e.y, yaw: e.yaw, v: e.v, u: e.u || 0, steer: e.steer || 0, rate: st.steer, top: st.top,
                    bg: e.bg || 0};
        });
        this.world.damage = ((this.app.state.lesson || {}).damage ?? true) !== false;  // (CHANGE 158: real damage)
    }

    welcome(m) {
        this.setTrack(m.track);
        this.mine = m.kart ?? null;  // (our own kart's id; the teacher's when "My kart in the race" is on)
        const p = this.app.params;
        // the view kept in their profile: the window's {mode, zoom} (ChaseCamera.settings), or a plain mode as the
        // page kept it before CHANGE 143
        const kept = (m.prefs || {}).camera;
        const keptMode = typeof kept === "string" ? kept : kept && typeof kept === "object" ? kept.mode : null;
        const keptZoom = kept && typeof kept === "object" ? Number(kept.zoom) : NaN;
        if (Number.isFinite(keptZoom)) this.scene.zoom = Math.max(0.6, Math.min(1.5, keptZoom));
        if (p.get("cam")) this.scene.setMode(p.get("cam"), p.get("follow") !== null ? Number(p.get("follow")) : null);
        else if (this.app.state.role === "learner" && this.mine !== null) {
            this.scene.setMode(["chase", "hood", "tv"].includes(keptMode) ? keptMode : "chase", this.mine);
        }
    }

    myId() {
        const r = this.app.state.roster;
        if (r && r.mine && r.mine[this.app.state.name] !== undefined) this.mine = r.mine[this.app.state.name];
        return this.mine;
    }

    cycleCamera() {  // V: chasing your kart, the TV camera, the whole track
        const id = this.myId(), order = id !== null ? ["chase", "hood", "tv"] : ["chase", "tv", "overview"];  // (the window's: chase, hood, TV)
        const next = order[(order.indexOf(this.scene.mode) + 1) % order.length];
        this.scene.setMode(next, next !== "overview" ? id : null);
        this.keepCamera();
    }

    keepCamera() {  // (in the window's format, so the window and the page each find the other's: CHANGE 143)
        this.app.keepPrefs && this.app.keepPrefs({camera: this.scene.cameraSettings()});
    }

    // ---------- the keys app.js passes on (CHANGE 143) ----------
    // zoom(dir, how): dir 1 closer (the wheel up, +), -1 wider (the wheel down, -); how "wheel" (a notch: x0.88, the
    // "inverted wheel zoom" setting turns it round, as the window's invert_zoom does the wheel only), "key" (+ or -
    // pressed: x0.8 or x1.25) or "repeat" (held: x0.9 or x1.11). The window's numbers (kart_client, ChaseCamera.wheel:
    // the field of view x the square root). The whole track zooms by its distance on + and -, and leaves the wheel to
    // Babylon's own orbit. True when it zoomed.
    zoom(dir, how = "wheel") {
        if (!dir) return false;
        let d = dir > 0 ? 1 : -1;
        if (how === "wheel" && this.zoomInverted()) d = -d;
        const f = how === "key" ? [0.8, 1.25] : how === "repeat" ? [0.9, 1.11] : [0.88, 1 / 0.88];
        const factor = d > 0 ? f[0] : f[1];
        const sc = this.scene;
        if (sc.mode === "overview") {
            if (how === "wheel") return false;
            sc.camera.radius *= factor;
            return true;
        }
        sc.zoomBy(factor);
        this.keepCamera();
        return true;
    }

    zoomInverted() {  // (read wherever the setting is kept: the window's prefs name it invert_zoom)
        const S = this.app.state, P = S.prefs || {}, H = P.hud || {};
        return !!(P.zoom_invert ?? P.invert_zoom ?? H.zoom_invert ?? H.invert_zoom ?? S.zoomInvert ?? false);
    }

    resetCamera() {  // Home: the zoom back to 1, the view cut back to where it belongs (the whole track: as it starts)
        this.scene.resetCamera();
        this.keepCamera();
        return true;
    }

    // the teacher's keys (kart_client.start_game): Enter starts the race, G puts everyone on the grid, T the next
    // track. key: as play.js's Keys gives it ("Enter", "g", "t"); true when it was one of them
    teacherKey(key) {
        if (this.app.state.role === "learner") return false;
        const k = String(key || "").toLowerCase();
        if (k === "enter") this.app.send({type: "start"});
        else if (k === "g") this.app.send({type: "grid"});
        else if (k === "t") {  // (kart_client.next_track: the next in the list, round to the first)
            const S = this.app.state, names = Object.keys((S.rules && S.rules.tracks) || TRACKS);
            const cur = (S.lesson && S.lesson.track) || names[0], i = names.indexOf(cur);
            this.app.send({type: "lesson", lesson: {track: names[i >= 0 ? (i + 1) % names.length : 0]}});
        } else return false;
        return true;
    }

    // H: the window's key list (kart_hud.keys_text), a row a key, with the camera's zoom and Home after it
    keyList() {
        const teacher = this.app.state.role !== "learner";
        return [["Arrows/WASD", "drive"], ["Shift", "drift"], ["E", "use your item"], ["R", "respawn"], ["V", "view"], ["Tab/I", "HUD"], ["C", "code"],
                ...(teacher ? [["Enter", "start"], ["G", "grid"], ["T", "track"]] : [["U", "brain"], ["P", "autopilot"]]),
                ["N", "sound"], ["H", "help"], ["+/- or the wheel", "zoom"], ["Home", "the camera back to normal"]];
    }

    learnerTabs() { return [["camera", "Camera"]]; }

    setTrack(data) {
        const key = JSON.stringify(data);
        if (key === this.trackKey) return;
        this.trackKey = key;
        this.track = new Track(data);
        this.scene.setTrack(this.track);
        this.predictor = null;  // (its step knows the old track: predicted afresh from the next snapshot, as the window)
    }

    // the stats of our own kart's design as the server has it: the roster's kart carries it under design (CHANGE
    // 155: the prediction had read the kart's entry itself, so every kart was predicted as 33, 33, 33 and anyone's
    // own design was put right several times a second)
    myStats(id) {
        const S = this.app.state, kart = (((S.roster || {}).karts) || []).find(k => k.id === id);
        return statsOf((kart && kart.design) || S.myDesign || {});
    }

    // JSON messages the core passes on; true when this game used it (the core has already stored the common parts)
    message(m) {
        const S = this.app.state;
        switch (m.type) {
            case "lesson":
                if (m.track) this.setTrack(m.track);
                this.scene.setTime(((m.lesson || S.lesson || {}).time) || "day");  // (CHANGE 172)
                return false;
            case "items": {  // (CHANGE 159) the power-ups out on the track, drawn as late as the karts; who was hit
                this.itemsBuf = (this.itemsBuf || []).concat([m]).slice(-12);
                for (const [kid, what, blocked] of m.hits || []) {
                    if (kid !== this.myId()) continue;
                    const words = {shot: "a shot", homing: "a homing shot", oil: "an oil slick"}[what] || what;
                    this.hud.note(blocked ? `Your shield stopped ${words}!` : `Hit by ${words}!`, 2);
                }
                return true;
            }
            case "roster":
                this.scene.setKarts(m.karts || []);
                this.renderPlaces();
                // (a new design for our kart, from the Garage or the teacher: predicted afresh, as the window does)
                if (this.predictor && this.mine !== null && JSON.stringify(this.myStats(this.myId())) !== this.predStats) this.predictor = null;
                return true;
            case "race":
                m.at = Date.now();  // (go_in_ms counts from when it came: GO in our own clock)
                // (GO kept for the lap clock once the countdown is over: the server stops sending it then)
                if (m.go_in_ms !== null && m.go_in_ms !== undefined) this.goAt = m.at + m.go_in_ms;
                else if (m.phase !== FLAGS_RACE) this.goAt = null;
                this.race = S.race = m;
                for (const e of m.events || []) this.app.addEvent(e);
                this.renderRace();
                this.renderPlaces();
                if (S.tab === "learners") this.app.renderPanel();
                return true;
            default:
                return false;
        }
    }

    binary(data, now) {
        if (kindOf(data) !== KIND_SNAPSHOT) return;
        const snap = unpackSnapshot(data, KART_FIELDS);
        this.app.pushSnap(snap, now);
        this.phaseFlags = snap.flags & 0x0F;
        this.onSnapshot(snap, now);
    }

    // ---------- prediction (kart_client.on_snapshot, client_tick) ----------
    predicting() {
        const S = this.app.state;
        return this.myId() !== null && this.app.params.get("predict") !== "0" && !((S.myMissions || {}).autopilot) && !this.finished;
    }

    onSnapshot(snap, rx) {
        this.snapSeq = snap.seq;
        this.phase = snap.flags & 3;
        this.lead.feed(snap.flags >> 4);
        const id = this.myId();
        const me = id !== null ? snap.entities.find(e => e.id === id) : null;
        if (!me) return;
        this.finished = !!(me.flags & FLAG_FINISHED);
        if (!this.predicting()) { this.predictor = null; return; }
        const state = fullState(me, this.track);
        if (!this.predictor) {  // (its numbering carries on from ours: the server ignores a number going back)
            const stats = this.myStats(id);
            this.predStats = JSON.stringify(stats);
            this.setOthers(snap, id);
            this.predictor = new Predictor(makeStep(this.track, stats, this.world), state, 0.05, new InputLog(this.nextSeq));
            this.drawFrom = state;
            this.smoother.clear();
            this.accum = 0;
            return;
        }
        if (snap.ack === 0) return;  // (the server hasn't applied an input of ours yet)
        // (the others as they were at the acknowledged tick: a replay carries them on from there; with nothing to
        // replay they are carried on to now, as far as our inputs the server hasn't had)
        const ahead = this.predictor.log.since(snap.ack).length;
        this.setOthers(snap, id);
        const err = this.predictor.correct(state, snap.ack, STEP, compare);
        const moved = this.predictor.movedFrom;
        if (!moved) for (let i = 0; i < ahead; i++) for (const o of this.world.others) coast(o, STEP);
        if (moved) {
            const n = this.predictor.state;
            const dyaw = ((((moved.yaw - n.yaw + 180) % 360) + 360) % 360 - 180) * Math.PI / 180;
            if (err !== Infinity) this.smoother.add([moved.x - n.x, moved.y - n.y, 0], dyaw);
            // (the state before the newest tick moved with the correction, so the picture between them doesn't jump)
            const f = this.drawFrom;
            this.drawFrom = err === Infinity || !f ? n : {...f, x: f.x + n.x - moved.x, y: f.y + n.y - moved.y, yaw: f.yaw - dyaw * 180 / Math.PI};
        }
        const sent = this.sentAt.get(snap.ack);
        if (sent !== undefined && this.app.ctrl) {
            const ms = rx - sent;
            this.app.ctrl.ctrlMs = this.app.ctrl.ctrlMs === null ? ms : this.app.ctrl.ctrlMs * 0.8 + ms * 0.2;
        }
    }

    sendNeutral() {  // (CHANGE 175) the tab hidden: one input with nothing pressed, numbered on from ours
        const seq = this.nextSeq;
        this.nextSeq = (seq + 1) & 0xFFFF;
        this.app.sendBinary(packInput(seq, this.snapSeq, Math.floor(performance.now()) >>> 0, 0, 0, 0, []));
    }

    frozen() {
        const r = this.race;
        if (this.phase !== FLAGS_RACE) return true;
        return !!(r && r.go_in_ms !== null && r.go_in_ms !== undefined && Date.now() < (r.at || 0) + r.go_in_ms);
    }

    // play.js calls this every frame with a function reading the keys: whole 1/60 s ticks, each one input
    controlFrame(now, readKeys, dt) {
        if (this.predictor === null && this.predicting()) return;  // (nothing to predict from until the first snapshot)
        if (this.race && this.race.paused) return;  // (CHANGE 175: nothing moves and nothing is sent while paused)
        // (the lead multiplier stretches the time between ticks so the server keeps one or two of ours waiting; a
        // hitch of up to 15 ticks is caught up (else the server repeats our last input for each: CHANGE 175), a
        // longer freeze skipped)
        this.accum = Math.min(15 * STEP, this.accum + dt / this.lead.multiplier());
        while (this.accum >= STEP) {
            this.accum -= STEP;
            const k = readKeys();
            let inp = quantiseInput(k.throttle, k.steer, k.buttons);
            if (this.frozen()) inp = [0, 0, 0];
            let seq, prev;
            if (this.predictor) {
                this.drawFrom = this.predictor.state;
                seq = this.predictor.apply(inp, STEP, now);
                prev = this.predictor.log.previous(2);
                this.nextSeq = this.predictor.log.nextSeq;
            } else {
                seq = this.nextSeq;
                prev = [];
                this.nextSeq = (seq + 1) & 0xFFFF;
            }
            this.sentAt.set(seq, now);
            if (this.sentAt.size > 128) for (const s of [...this.sentAt.keys()].slice(0, 64)) this.sentAt.delete(s);
            this.app.sendBinary(packInput(seq, this.snapSeq, Math.floor(now) >>> 0, inp[0], inp[1], inp[2], prev));
        }
    }

    // the state to draw: two snapshots behind, blended between the two around that moment
    frame(now, dt) {
        const pair = this.app.samplePair(now);
        const states = new Map();
        if (pair) {
            const {a, b, f} = pair;
            const byId = b ? new Map(b.entities.map(e => [e.id, e])) : new Map();
            for (const e of a.entities) {
                const n = byId.get(e.id);
                if (!n) { states.set(e.id, e); continue; }
                let dy = n.yaw - e.yaw;
                dy = ((dy + 180) % 360 + 360) % 360 - 180;
                states.set(e.id, {...n, x: e.x + (n.x - e.x) * f, y: e.y + (n.y - e.y) * f, yaw: e.yaw + dy * f, v: e.v + (n.v - e.v) * f});
            }
        }
        if (this.race && this.race.places && this.race.places.length) this.scene.leader = this.race.places[0];
        // (CHANGE 151) seconds to GO for ultra's start lights (null when the race isn't counting down)
        const r = this.race, counting = r && r.phase === FLAGS_RACE && r.go_in_ms !== null && r.go_in_ms !== undefined;
        this.scene.countdown = counting ? (r.go_in_ms - (Date.now() - (r.at || Date.now()))) / 1000 : null;
        const myId = this.myId();  // (your own kart: the prediction, now, with the correction easing out)
        if (this.predictor && myId !== null && states.has(myId)) {
            // (CHANGE 155) drawn between the last two ticks by the time since the newest: the page's frames don't
            // keep time with the 1/60 s ticks (a frame with none, the next with two), and whole ticks drew the kart
            // stopping and jumping
            const mine = between(this.drawFrom, this.predictor.state, this.accum / STEP);
            const [[ox, oy], oyaw] = this.smoother.offset(dt);
            mine.x += ox; mine.y += oy; mine.yaw += oyaw * 180 / Math.PI;
            states.set(myId, mine);
        }
        this.scene.frame(states, dt);
        this.scene.drawItems(this.itemsAt(this.app.renderTime ? this.app.renderTime(now) : null), dt);  // (CHANGE 159)
        if (pair && this.race && (this.race.phase === 1 || this.phaseFlags === 1)) this.renderCountdown();
        // your race (hud.js): lap, place, speed, the drift meter, wrong way, the minimap; the sounds (sound.js)
        const id = this.myId(), followed = id !== null ? id : this.scene.follow;
        const roster = this.app.state.roster || {};
        const designs = new Map((roster.karts || []).map(k => [k.id, k]));
        if (id !== null) {
            const colours = new Map([...designs].map(([k, d]) => [k, `rgb(${(d.colour || [200, 200, 200]).join(",")})`]));
            this.laps(states.get(id), Date.now());
            // (CHANGE 158) the damage panel with the lesson's real damage on; PIT: REPAIRING in the PIT box at pit speed
            const me = states.get(id), damageOn = ((this.app.state.lesson || {}).damage ?? true) !== false;
            let inPit = false;
            if (damageOn && me && DAMAGE_PARTS.some(p => me[p] > 0) && Math.abs(me.v || 0) < PIT_SPEED) {
                const at = this.track.locate(me.x, me.y, me.seg ?? null);
                inPit = this.track.inPit(at.s, at.lateral);
            }
            this.hud.update(me, states, this.race, this.track, id, colours, damageOn, inPit);
        }
        if (this.app.sound) {
            const me = followed !== null && followed !== undefined ? states.get(followed) || null : null;
            const places = (this.race && this.race.places) || [];
            this.app.sound.kartFrame(me, this.race, {top: Sound.kartTop(designs.get(followed)), place: places.indexOf(followed) + 1,
                                                     karts: states, now: Date.now()});
        }
    }

    // (CHANGE 159) the items to draw at the server's time t (ms): the messages either side, the shots blended
    itemsAt(t) {
        const buf = this.itemsBuf || [];
        if (!buf.length) return null;
        if (t === null) return buf[buf.length - 1];
        let a = null, b = null;
        for (const m of buf) {
            if (m.sm <= t) a = m;
            else if (!b && a) b = m;
        }
        if (!a) return buf[0];
        if (!b) return a;
        const f = Math.max(0, Math.min(1, (t - a.sm) / Math.max(1, b.sm - a.sm)));
        const later = new Map(b.shots.map(sh => [sh[0], sh]));
        const shots = a.shots.map(sh => {
            const n = later.get(sh[0]);
            if (!n) return sh;
            const dh = ((n[4] - sh[4] + 180) % 360 + 360) % 360 - 180;
            return [sh[0], sh[1], sh[2] + (n[2] - sh[2]) * f, sh[3] + (n[3] - sh[3]) * f, sh[4] + dh * f];
        });
        return {boxes: a.boxes, shots, slicks: a.slicks};
    }

    renderCountdown() {
        const r = this.race;
        if (r.go_in_ms !== null && r.go_in_ms !== undefined) {
            const left = (r.go_in_ms - (Date.now() - (r.at || Date.now()))) / 1000;
            $("countdown").textContent = left > 0 ? Math.ceil(left) : (left > -1.5 ? "GO!" : "");
        } else {
            $("countdown").textContent = "";
        }
    }

    // your lap times, told as you cross the line (kart_client.laps): the clock starts at GO, the best is this race's.
    // (Joined after GO, or in practice, where the track opens with no countdown: the clock starts at the first line
    // crossed, with nothing told for that part lap.)
    laps(me, now) {
        const r = this.race;
        if (!me || !r || r.phase !== FLAGS_RACE) { this.lapSeen = null; return; }
        const lap = me.lap || 0;
        if (this.lapSeen === null || this.lapSeen === undefined) {
            this.lapSeen = lap;
            this.lapStarted = this.goAt ?? null;
            this.bestLap = null;
            return;
        }
        if (lap > this.lapSeen && (this.lapStarted === null || now > this.lapStarted + 5000)) {
            const started = this.lapStarted;
            this.lapSeen = lap;
            this.lapStarted = now;
            if (started === null) return;
            const took = (now - started) / 1000, best = this.bestLap === null || took < this.bestLap;
            if (best) this.bestLap = took;
            this.hud.note(`Lap ${lap}: ${took.toFixed(1)} s` + (best ? "   NEW BEST" : `   (best ${this.bestLap.toFixed(1)} s)`), 4);
        }
    }

    renderRace() {
        const r = this.race;
        r.at = Date.now();
        // (on the grid the window says what everyone waits for: kart_client.draw)
        const phase = r.phase === 0 ? (r.practice ? "Practice: the track is open" : "Waiting for the teacher to start the race")
            : r.phase === 1 ? (r.practice ? "Practice" : `Racing · ${r.laps} laps`) : "Finished";
        $("phase").textContent = (r.paused ? "PAUSED · " : "") + phase;
        if (r.phase !== 1) $("countdown").textContent = r.phase === 2 ? "FINISH" : "";
        // the results stay up until the next race, as the window's panel does (kart_gfx.Hud: CHANGE 143)
        this.hud.results(r.phase === 2 ? r.results : null);
    }

    renderPlaces() {
        const r = this.race, roster = this.app.state.roster, esc = this.app.esc;
        if (!r || !roster) return;
        const karts = new Map((roster.karts || []).map(k => [k.id, k]));
        const snaps = this.app.state.snaps;
        const latest = snaps.length ? new Map(snaps[snaps.length - 1].entities.map(e => [e.id, e])) : new Map();
        const rows = (r.places || []).map((id, i) => {
            const k = karts.get(id) || {name: "?", colour: [128, 128, 128]};
            const e = latest.get(id);
            const lap = e ? Math.min(e.lap + 1, r.laps || e.lap + 1) : "";
            const c = (k.colour || [128, 128, 128]).map(v => Math.round(v));
            return `<div data-id="${id}"><span class="n">${i + 1}</span><span class="sw" style="background:rgb(${c.join(",")})"></span>` +
                   `<span>${esc(k.name)}${k.cpu ? ` <small>(cpu)</small>` : ""}</span><span class="lap">${lap !== "" ? `lap ${lap}` : ""}</span></div>`;
        });
        $("places").innerHTML = rows.join("") || "<div><small>No karts yet</small></div>";
        $("places").querySelectorAll("div[data-id]").forEach(el => el.onclick = () => this.followKart(Number(el.dataset.id)));
    }

    followKart(id) {
        const sc = this.scene;
        if (sc.follow === id && sc.mode === "chase") sc.setMode("tv", null);
        else sc.setMode("chase", id);
        this.app.updatePills();
        if (this.app.state.tab === "camera") this.app.renderPanel();
    }

    pill() {
        const L = this.app.state.lesson;
        return L ? `Mission ${L.lesson_number} · ${this.track ? this.track.name : L.track} · ${L.mode === "race" ? "race" : "practice"}` : "";
    }

    cameraPill() {
        const sc = this.scene;
        return sc.mode === "chase" ? `Camera: chasing kart ${sc.follow}` : sc.mode === "hood" ? "Camera: hood (V to change)"
            : sc.mode === "tv" ? "Camera: TV (V to change, wheel to zoom)" : "Camera: overview (drag to orbit, wheel to zoom)";
    }

    tabs() { return [["controls", "Controls"], ["camera", "Camera"]]; }

    // the Learners table's game columns
    learnerHead() { return ["Kart", "Lap", "brain"]; }
    learnerCells(p) {
        const S = this.app.state, roster = S.roster, esc = this.app.esc;
        const kid = roster && roster.mine ? roster.mine[p.name] : null;
        const snaps = S.snaps;
        const e = kid !== null && kid !== undefined && snaps.length ? snaps[snaps.length - 1].entities.find(x => x.id === kid) : null;
        const b = ((this.race && this.race.brains) || {})[p.name];
        return [esc((p.design && p.design.name) || ""), e ? e.lap : "",
                `${b ? (b.on ? "<span class='ok'>driving</span>" : b.has ? "loaded" : "") : ""}${b && b.error ? " <span class='bad'>error</span>" : ""}`];
    }

    renderTab(tab, body) {
        const app = this.app, S = app.state, L = S.lesson, R = S.rules, send = app.send, esc = app.esc;
        if (tab === "controls") {
            if (!L || !R) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return; }
            const tracks = Object.entries(R.tracks || {}).map(([k, n]) => `<option value="${k}" ${k === L.track ? "selected" : ""}>${esc(n)}</option>`).join("");
            const levels = (R.cpu_levels || []).map(l => `<option ${l === L.cpu_level ? "selected" : ""}>${l}</option>`).join("");
            const racing = this.race && this.race.phase === 1;
            const T = S.tournament;
            body.innerHTML = `
              ${app.missionRow()}
              <h2>The race</h2>
              <div class="row">
                <button id="btn-start" class="go">${L.mode === "practice" ? "START A RACE" : racing ? "RESTART" : "START"}</button>
                <button id="btn-grid">TO THE GRID</button>
                <button id="btn-pause" class="${this.race && this.race.paused ? "on" : ""}">${this.race && this.race.paused ? "RESUME" : "PAUSE"}</button>
              </div>
              <div class="note">${L.mode === "practice" ? "Practice: the track is open and laps are timed. START A RACE closes it until GO." : "Race mode: START begins the countdown; TO THE GRID lines everyone up again."}</div>
              <div class="row"><label>Mode</label>
                <button data-mode="practice" class="${L.mode !== "race" ? "on" : ""}">Practice</button>
                <button data-mode="race" class="${L.mode === "race" ? "on" : ""}">Race</button></div>
              <div class="row"><label>Grand prix</label>
                ${T ? `<span>${esc(T.title || T.label || "running")}</span> <button id="btn-gp-stop" class="stop">END IT</button>`
                    : `<select id="gp-races"><option>2</option><option selected>3</option><option>4</option><option>5</option></select> races <button id="btn-gp" class="go">START THE GRAND PRIX</button>`}
              </div>
              ${T && T.standings ? `<table>${T.standings.map(([n, pts], i) => `<tr><td>${i + 1}.</td><td>${esc(n)}</td><td class="num">${pts} pts</td></tr>`).join("")}</table>
                 ${T.champion ? `<p class="ok">Champion: ${esc(T.champion)}</p>` : ""}` : ""}
              <h2>The track</h2>
              <div class="row"><label>Track</label><select id="sel-track">${tracks}</select></div>
              <div class="row"><label>Laps</label><select id="sel-laps">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<option ${n === L.laps ? "selected" : ""}>${n}</option>`).join("")}</select></div>
              <div class="row"><label>Computer karts</label><select id="sel-cpu">${[0, 1, 2, 3, 4, 5, 6, 7].map(n => `<option ${n === L.cpu_karts ? "selected" : ""}>${n}</option>`).join("")}</select>
                <select id="sel-level">${levels}</select></div>
              <div class="row"><label>Teacher's kart</label><button id="btn-tkart" class="${L.teacher_kart ? "on" : ""}">${L.teacher_kart ? "On the grid" : "Not racing"}</button></div>
              <div class="row"><label>Designs</label><button id="btn-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
              <div class="row"><label>Damage</label><button id="btn-damage" class="${L.damage !== false ? "on" : ""}">${L.damage !== false ? "On: hits slow a kart till it's mended" : "Off"}</button></div>
              <div class="note">Real damage: barriers and other karts damage the front wing, the wheels and the engine. A damaged kart is slower or pulls to one side; it mends by itself, quickly driving slowly through the PIT box. Off mends every kart.</div>
              <div class="row"><label>Time of day</label>${[["day", "Day"], ["dusk", "Dusk"], ["night", "Night"]].map(([k, t]) => `<button data-time="${k}" class="${(L.time || "day") === k ? "on" : ""}">${t}</button>`).join("")}</div>
              <div class="note">Every window and page draws the race at that time; at dusk and night the headlights come on (CHANGE 172).</div>
              <div class="row"><label>Power-ups</label>${ITEM_NAMES.map(([k, t]) => `<button data-item="${k}" class="${(L.items || {})[k] !== false ? "on" : ""}">${t}</button>`).join("")}</div>
              <div class="note">Item boxes give a random power-up (better ones further back); E uses it. Each one on or off; with all off there are no boxes.</div>
              ${app.restartRow()}`;
            const lessonSend = patch => send({type: "lesson", lesson: patch});
            app.wireMissionRow(body);
            $("btn-start").onclick = () => send({type: "start"});
            $("btn-grid").onclick = () => send({type: "grid"});
            $("btn-pause").onclick = () => send({type: "pause"});
            body.querySelectorAll("button[data-mode]").forEach(b => b.onclick = () => lessonSend({mode: b.dataset.mode}));
            $("sel-track").onchange = e => lessonSend({track: e.target.value});
            $("sel-laps").onchange = e => lessonSend({laps: Number(e.target.value)});
            $("sel-cpu").onchange = e => lessonSend({cpu_karts: Number(e.target.value)});
            $("sel-level").onchange = e => lessonSend({cpu_level: e.target.value});
            $("btn-tkart").onclick = () => lessonSend({teacher_kart: !L.teacher_kart});
            $("btn-lock").onclick = () => lessonSend({designs_locked: !L.designs_locked});
            // (CHANGE 158, 159) the lesson as it is at the click, not as it was drawn: a second click before the panel is
            // drawn again would send the first's again
            const now = () => this.app.state.lesson || L;
            $("btn-damage").onclick = () => lessonSend({damage: now().damage === false});
            body.querySelectorAll("button[data-time]").forEach(b => b.onclick = () => lessonSend({time: b.dataset.time}));
            body.querySelectorAll("button[data-item]").forEach(b => b.onclick = () => {  // (CHANGE 159)
                const on = Object.fromEntries(ITEM_NAMES.map(([k]) => [k, (now().items || {})[k] !== false]));
                lessonSend({items: {...on, [b.dataset.item]: !on[b.dataset.item]}});
            });
            if ($("btn-gp")) $("btn-gp").onclick = () => send({type: "tournament", start: true, races: Number($("gp-races").value)});
            if ($("btn-gp-stop")) $("btn-gp-stop").onclick = () => send({type: "tournament", start: false});
            app.wireRestartRow(body);
            return true;
        }
        if (tab === "camera") {
            const sc = this.scene;
            const karts = (S.roster && S.roster.karts) || [];
            body.innerHTML = `
              <h2>Camera</h2>
              <div class="row"><button data-cam="tv" class="${sc.mode === "tv" ? "on" : ""}">TV</button>
                <button data-cam="overview" class="${sc.mode === "overview" ? "on" : ""}">Whole track</button></div>
              <div class="note">TV: six trackside cameras, the nearest one watching the leader (or the kart you pick below). Chase sits behind one kart.
                The wheel or + and - zoom, Home puts the camera back. Whole track: drag to orbit.</div>
              <h2>Chase a kart</h2>
              <div class="row">${karts.map(k => `<button data-follow="${k.id}" class="${sc.mode === "chase" && sc.follow === k.id ? "on" : ""}">${esc(k.name)}</button>`).join("") || "<span class='note'>No karts yet</span>"}</div>
              <h2>Lap times</h2>
              <table>${Object.entries((this.race && this.race.lap_times) || {}).map(([kid, times]) => {
                  const k = karts.find(x => String(x.id) === kid);
                  const t = Array.isArray(times) ? times : [];
                  return `<tr><td>${esc(k ? k.name : kid)}</td><td class="num">${t.length ? fmtTime(Math.min(...t)) : ""}</td><td>${t.map(fmtTime).join(", ")}</td></tr>`;
              }).join("") || "<tr><td class='note'>No laps yet</td></tr>"}</table>`;
            body.querySelectorAll("button[data-cam]").forEach(b => b.onclick = () => { sc.setMode(b.dataset.cam, null); app.updatePills(); app.renderPanel(); });
            body.querySelectorAll("button[data-follow]").forEach(b => b.onclick = () => this.followKart(Number(b.dataset.follow)));
            return true;
        }
        return false;
    }

    dispose() {
        this.hud.results(null);
        this.scene.dispose();
        $("places").innerHTML = "";
        $("countdown").textContent = $("phase").textContent = "";
    }
}

// a kart's state a fraction f of the way from a to b (the position, speed and heading; the rest b's)
function between(a, b, f) {
    if (!a || !(f > 0)) return {...(a || b)};
    if (f >= 1) return {...b};
    const dy = ((b.yaw - a.yaw + 180) % 360 + 360) % 360 - 180;
    return {...b, x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, yaw: a.yaw + dy * f, v: a.v + (b.v - a.v) * f,
            u: (a.u || 0) + ((b.u || 0) - (a.u || 0)) * f};
}

export function fmtTime(t) {
    const m = Math.floor(t / 60), s = (t - m * 60).toFixed(2).padStart(5, "0");
    return m ? `${m}:${s}` : `${s}s`;
}
