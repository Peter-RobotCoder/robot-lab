// Kart Lab in Club Coders Live: the binary snapshots (wire.js), the race, the places, the race controls and the
// cameras. The teacher tabs every game shares (learners, outcomes, AI cards, rules) are teacher.js's.

import {KART_FIELDS, KIND_SNAPSHOT, kindOf, unpackSnapshot} from "./wire.js";
import {Track, TRACKS} from "./track.js";
import {KartScene} from "./scene.js";
import {KartHud} from "./hud.js";
import {STEP, FLAGS_RACE, FLAG_FINISHED, statsOf, fullState, makeStep, compare} from "./kart_sim.js";
import {Predictor, InputLog, ErrorSmoother, LeadController, quantiseInput, packInput} from "./predict.js";
import {Sound} from "./sound.js";

const $ = id => document.getElementById(id);

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
    }

    welcome(m) {
        this.setTrack(m.track);
        this.mine = m.kart ?? null;  // (our own kart's id; the teacher's when "My kart in the race" is on)
        const p = this.app.params;
        if (p.get("cam")) this.scene.setMode(p.get("cam"), p.get("follow") !== null ? Number(p.get("follow")) : null);
        else if (this.app.state.role === "learner" && this.mine !== null) {  // (the view kept in their profile)
            const kept = (m.prefs || {}).camera;
            this.scene.setMode(["chase", "hood", "tv"].includes(kept) ? kept : "chase", this.mine);
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
        this.app.keepPrefs && this.app.keepPrefs({camera: next});
    }

    learnerTabs() { return [["camera", "Camera"]]; }

    setTrack(data) {
        const key = JSON.stringify(data);
        if (key === this.trackKey) return;
        this.trackKey = key;
        this.track = new Track(data);
        this.scene.setTrack(this.track);
    }

    // JSON messages the core passes on; true when this game used it (the core has already stored the common parts)
    message(m) {
        const S = this.app.state;
        switch (m.type) {
            case "lesson":
                if (m.track) this.setTrack(m.track);
                return false;
            case "roster":
                this.scene.setKarts(m.karts || []);
                this.renderPlaces();
                return true;
            case "race":
                m.at = Date.now();  // (go_in_ms counts from when it came: GO in our own clock)
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
            const design = (((this.app.state.roster || {}).karts) || []).find(k => k.id === id) || this.app.state.myDesign || {};
            this.predictor = new Predictor(makeStep(this.track, statsOf(design)), state, 0.05, new InputLog(this.nextSeq));
            this.smoother.clear();
            this.accum = 0;
            return;
        }
        if (snap.ack === 0) return;  // (the server hasn't applied an input of ours yet)
        const err = this.predictor.correct(state, snap.ack, STEP, compare);
        const moved = this.predictor.movedFrom;
        if (moved && err !== Infinity) {
            const n = this.predictor.state;
            const dyaw = ((((moved.yaw - n.yaw + 180) % 360) + 360) % 360 - 180) * Math.PI / 180;
            this.smoother.add([moved.x - n.x, moved.y - n.y, 0], dyaw);
        }
        const sent = this.sentAt.get(snap.ack);
        if (sent !== undefined && this.app.ctrl) {
            const ms = rx - sent;
            this.app.ctrl.ctrlMs = this.app.ctrl.ctrlMs === null ? ms : this.app.ctrl.ctrlMs * 0.8 + ms * 0.2;
        }
    }

    frozen() {
        const r = this.race;
        if (this.phase !== FLAGS_RACE) return true;
        return !!(r && r.go_in_ms !== null && r.go_in_ms !== undefined && Date.now() < (r.at || 0) + r.go_in_ms);
    }

    // play.js calls this every frame with a function reading the keys: whole 1/60 s ticks, each one input
    controlFrame(now, readKeys, dt) {
        if (this.predictor === null && this.predicting()) return;  // (nothing to predict from until the first snapshot)
        // (the lead multiplier stretches the time between ticks so the server keeps one or two of ours waiting; a
        // hitch of more than four ticks is skipped, not caught up)
        this.accum = Math.min(4 * STEP, this.accum + dt / this.lead.multiplier());
        while (this.accum >= STEP) {
            this.accum -= STEP;
            const k = readKeys();
            let inp = quantiseInput(k.throttle, k.steer, k.buttons);
            if (this.frozen()) inp = [0, 0, 0];
            let seq, prev;
            if (this.predictor) {
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
        const myId = this.myId();  // (your own kart: the prediction, now, with the correction easing out)
        if (this.predictor && myId !== null && states.has(myId)) {
            const mine = {...this.predictor.state};
            const [[ox, oy], oyaw] = this.smoother.offset(dt);
            mine.x += ox; mine.y += oy; mine.yaw += oyaw * 180 / Math.PI;
            states.set(myId, mine);
        }
        this.scene.frame(states, dt);
        if (pair && this.race && (this.race.phase === 1 || this.phaseFlags === 1)) this.renderCountdown();
        // your race (hud.js): lap, place, speed, the drift meter, wrong way, the minimap; the sounds (sound.js)
        const id = this.myId(), followed = id !== null ? id : this.scene.follow;
        const roster = this.app.state.roster || {};
        const designs = new Map((roster.karts || []).map(k => [k.id, k]));
        if (id !== null) {
            const colours = new Map([...designs].map(([k, d]) => [k, `rgb(${(d.colour || [200, 200, 200]).join(",")})`]));
            this.hud.update(states.get(id), states, this.race, this.track, id, colours);
        }
        if (this.app.sound) {
            const me = followed !== null && followed !== undefined ? states.get(followed) || null : null;
            const places = (this.race && this.race.places) || [];
            this.app.sound.kartFrame(me, this.race, {top: Sound.kartTop(designs.get(followed)), place: places.indexOf(followed) + 1,
                                                     karts: states, now: Date.now()});
        }
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

    renderRace() {
        const r = this.race;
        r.at = Date.now();
        const phase = r.phase === 0 ? (r.practice ? "Practice: the track is open" : "On the grid") : r.phase === 1 ? (r.practice ? "Practice" : `Racing · ${r.laps} laps`) : "Finished";
        $("phase").textContent = (r.paused ? "PAUSED · " : "") + phase;
        if (r.phase !== 1) $("countdown").textContent = r.phase === 2 ? "FINISH" : "";
        if (r.phase === 2 && r.results && !this.shownResults) {
            this.shownResults = true;
            const lines = r.results.map(([name, laps, t], i) => `${i + 1}. ${name}${t !== null && t !== undefined ? ` ${fmtTime(t)}` : ` (${laps} laps)`}`);
            this.app.toast(lines.join("\n"), true, 12000);
        }
        if (r.phase !== 2) this.shownResults = false;
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
            : sc.mode === "tv" ? "Camera: TV (drag to orbit, wheel to zoom)" : "Camera: overview";
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
              <div class="note">TV follows the leader (or the kart you pick below); drag to orbit, wheel to zoom. Chase sits behind one kart.</div>
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
        this.scene.dispose();
        $("places").innerHTML = "";
        $("countdown").textContent = $("phase").textContent = "";
    }
}

export function fmtTime(t) {
    const m = Math.floor(t / 60), s = (t - m * 60).toFixed(2).padStart(5, "0");
    return m ? `${m}:${s}` : `${s}s`;
}
