// Club Coders Live (CHANGE 127): the teacher's browser window on a class server.
//
// The page speaks the same protocol as a Kart Lab teacher window: a JSON hello, then JSON for the lesson, the
// roster, the race and notices, and binary snapshots 30 times a second (wire.js). It draws the race two
// snapshots behind the newest, as the windows do (engine/interp.py), and carries the teacher's minute-to-minute
// controls. Learners' windows report how they are doing (fps, ping, stalls...) and the Learners tab shows it.
//
// Query string: ?host=ws://127.0.0.1:8782 for a laptop test server (the class picker is then "another server"),
// ?code=TEACH99 to prefill the code, ?tier=blocks|low|high, ?version=1.9.1 (a class server wants the release's
// number; on the VPS the page reads it from /live/version).

import {KART_FIELDS, KIND_SNAPSHOT, kindOf, unpackSnapshot} from "./wire.js";
import {Track, TRACKS} from "./track.js";
import {KartScene, TIERS} from "./scene.js";

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const DELAY_MS = 80;            // how far behind the newest snapshot the page draws (two snapshots plus jitter)
const CLOSE_TEXT = {4001: "Wrong teacher code.", 4002: "A teacher window is already open on this class: close it first.",
                    4006: "This page is out of date for that server.", 4008: "Too many wrong tries: wait a minute."};

const state = {
    ws: null, connected: false, role: null, name: "", game: null,
    version: params.get("version") || "",
    lesson: null, rules: null, roster: null, race: null, classList: [], tournament: null,
    snaps: [], offset: null, lastSeq: null, missed: 0, stalls: 0, pingMs: 0, lastPong: 0,
    events: [], eventKeys: new Set(), tab: "controls", scene: null, track: null, trackKey: "",
    fps: 0, frames: 0, fpsAt: performance.now(), leader: null, autoTier: params.get("auto") !== "0",
};

// ---------- the page's version (a class server only admits its own release) ----------
async function pageVersion() {
    if (state.version) return state.version;
    try {
        const r = await fetch("version", {cache: "no-store"});
        if (r.ok) state.version = (await r.text()).trim();
    } catch (e) { /* a file:// or laptop page: the test server doesn't check */ }
    return state.version;
}

// ---------- login ----------
function wsUrl() {
    const cls = $("class").value;
    if (cls === "other" || params.get("host")) {
        return ($("host").value || params.get("host") || "").trim();
    }
    const base = `wss://${location.host}`;
    return cls === "class1" ? base + "/" : `${base}/${cls}`;
}

function setStatus(text, ok = false) {
    $("status").textContent = text;
    $("status").style.color = ok ? "var(--green)" : "var(--red)";
}

function connect() {
    const url = wsUrl();
    const code = $("code").value.trim(), name = $("name").value.trim() || "Teacher";
    if (!url) return setStatus("Which server?");
    if (!code) return setStatus("The teacher code is needed.");
    setStatus("Connecting…", true);
    let ws;
    try {
        ws = new WebSocket(url);
    } catch (e) {
        return setStatus(`Can't open ${url}: ${e.message}`);
    }
    ws.binaryType = "arraybuffer";
    state.ws = ws;
    state.name = name;
    ws.onopen = () => {
        ws.send(JSON.stringify({type: "hello", name, code, version: state.version}));
        setStatus("Logging in…", true);
    };
    ws.onmessage = ev => onMessage(ev.data);
    ws.onclose = ev => {
        const text = CLOSE_TEXT[ev.code] || ev.reason || (state.connected ? "The connection closed." : "Couldn't connect. Is the server there, and the address right?");
        state.connected = false;
        state.ws = null;
        showLogin();
        setStatus(text);
    };
    ws.onerror = () => { /* onclose follows with the reason */ };
    try { sessionStorage.setItem("code", code); localStorage.setItem("class", $("class").value); localStorage.setItem("name", name); } catch (e) { /* private window */ }
}

function showLogin() {
    $("login").style.display = "grid";
    $("toggle").hidden = true;
    $("panel").classList.remove("open");
}

function hideLogin() {
    $("login").style.display = "none";
    $("toggle").hidden = false;
}

function send(msg) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify(msg));
}

// ---------- messages ----------
function onMessage(data) {
    const now = performance.now();
    if (data instanceof ArrayBuffer) {
        if (kindOf(data) !== KIND_SNAPSHOT) return;
        const snap = unpackSnapshot(data, KART_FIELDS);
        snap.at = now;
        if (state.lastSeq !== null) {
            const gap = (snap.seq - state.lastSeq) & 0xFFFF;
            if (gap > 1 && gap < 1000) state.missed += gap - 1;
        }
        state.lastSeq = snap.seq;
        // the clock offset between the server's ms and ours: the smallest arrival lag seen, drifting up slowly
        const lag = now - snap.sm;
        state.offset = state.offset === null ? lag : Math.min(lag, state.offset + 0.002 * (now - (state.offsetAt || now)));
        state.offsetAt = now;
        state.snaps.push(snap);
        if (state.snaps.length > 90) state.snaps.shift();
        state.phaseFlags = snap.flags & 0x0F;
        return;
    }
    let m;
    try { m = JSON.parse(data); } catch (e) { return; }
    switch (m.type) {
        case "welcome": {
            state.connected = true;
            state.role = m.role;
            if (!(m.rules && m.rules.tracks) || !m.track) {
                state.game = "other";
                send({type: "ping", t: Date.now()});
                hideLogin();
                $("where").textContent = wsUrl();
                toast("This class is running Robot Lab or Fight Lab.\nThe browser draws Kart Lab first; the other two follow.", true, 8000);
                $("panelbody").innerHTML = "<h2>Not yet</h2><p class='note'>This class's game isn't drawn in the browser yet. Kart Lab classes are.</p>";
                return;
            }
            state.game = "kartlab";
            state.rules = m.rules;
            state.lesson = m.lesson;
            setTrack(m.track);
            hideLogin();
            $("where").textContent = `${wsUrl().replace(/^wss?:\/\//, "")} · ${m.role}`;
            addEvent(`Logged in as ${m.name} (${m.role})`);
            send({type: "ping", t: Date.now()});
            if (params.get("cam")) {  // (tests: ?cam=chase&follow=1, ?cam=overview)
                state.scene.setMode(params.get("cam"), params.get("follow") !== null ? Number(params.get("follow")) : null);
            }
            if (params.get("panel")) { $("panel").classList.add("open"); state.tab = params.get("panel"); }
            updatePills();
            renderPanel();
            break;
        }
        case "lesson":
            state.lesson = m.lesson || state.lesson;
            state.classList = m.class || [];
            state.tournament = m.tournament || null;
            if (m.track) setTrack(m.track);
            updatePills();
            if (state.tab === "controls" || state.tab === "learners") renderPanel();
            break;
        case "roster":
            state.roster = m;
            if (state.scene) state.scene.setKarts(m.karts || []);
            if (state.tab === "learners") renderPanel();
            renderPlaces();
            break;
        case "race":
            state.race = m;
            for (const e of m.events || []) addEvent(e);
            renderRace();
            renderPlaces();
            if (state.tab === "learners") renderPanel();
            break;
        case "pong":
            if (m.t) state.pingMs = Date.now() - m.t;
            break;
        case "notice":
            toast(m.text || "", !!m.big);
            break;
        case "warnings":
            state.warnings = m.warnings || m.items || [];
            break;
        case "restart_client":
            toast("The server asked windows to reopen: this page reconnects.", true, 4000);
            break;
        default:
            break;
    }
}

function setTrack(data) {
    const key = JSON.stringify(data);
    if (key === state.trackKey) return;
    state.trackKey = key;
    state.track = new Track(data);
    if (state.scene) state.scene.setTrack(state.track);
    state.hints = new Map();
    updatePills();
}

// ---------- drawing ----------
function sample(now) {
    // the state to draw: two snapshots behind, blended between the two around that moment
    const snaps = state.snaps;
    if (!snaps.length || state.offset === null) return null;
    const t = now - state.offset - DELAY_MS;  // in server ms
    let a = null, b = null;
    for (let i = snaps.length - 1; i >= 0; i--) {
        if (snaps[i].sm <= t) { a = snaps[i]; b = snaps[i + 1] || null; break; }
    }
    if (!a) return snaps[0];
    if (!b) return a;
    const f = Math.max(0, Math.min(1, (t - a.sm) / Math.max(1, b.sm - a.sm)));
    const byId = new Map(b.entities.map(e => [e.id, e]));
    const entities = a.entities.map(e => {
        const n = byId.get(e.id);
        if (!n) return e;
        let dy = n.yaw - e.yaw;
        dy = ((dy + 180) % 360 + 360) % 360 - 180;
        return {...n, x: e.x + (n.x - e.x) * f, y: e.y + (n.y - e.y) * f, yaw: e.yaw + dy * f, v: e.v + (n.v - e.v) * f};
    });
    return {...a, entities};
}

let lastFrame = performance.now();
function loop() {
    const now = performance.now();
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    if (now - lastFrame > 100) state.stalls++;
    lastFrame = now;
    state.frames++;
    if (now - state.fpsAt > 1000) {
        state.fps = Math.round(state.frames * 1000 / (now - state.fpsAt));
        state.frames = 0;
        state.fpsAt = now;
        renderPerf();
        if (state.autoTier && state.scene && state.fps && state.fps < 24 && now - (state.tierAt || 0) > 8000) {
            const i = TIERS.indexOf(state.scene.tier);
            if (i > 0) { state.scene.setTier(TIERS[i - 1]); state.tierAt = now; toast(`Graphics stepped down to ${TIERS[i - 1]} (the frame rate was ${state.fps})`); if (state.tab === "graphics") renderPanel(); }
        }
        if (state.connected) {
            send({type: "ping", t: Date.now()});
            send({type: "perf", fps: state.fps, ping: Math.round(state.pingMs), tier: "web-" + (state.scene ? state.scene.tier : "?"), stalls: state.stalls, delay: DELAY_MS});
        }
    }
    if (state.scene) {
        const snap = sample(now);
        const states = new Map();
        if (snap) for (const e of snap.entities) states.set(e.id, e);
        if (state.race && state.race.places && state.race.places.length) state.scene.leader = state.race.places[0];
        state.scene.frame(states, dt);
        state.scene.render();
        if (snap && state.race && (state.race.phase === 1 || state.phaseFlags === 1)) renderCountdown();
    }
    requestAnimationFrame(loop);
}

function renderCountdown() {
    const r = state.race;
    if (!r) return;
    if (r.go_in_ms !== null && r.go_in_ms !== undefined) {
        const left = (r.go_in_ms - (Date.now() - (r.at || Date.now()))) / 1000;
        $("countdown").textContent = left > 0 ? Math.ceil(left) : (left > -1.5 ? "GO!" : "");
    } else {
        $("countdown").textContent = "";
    }
}

function renderRace() {
    const r = state.race;
    if (!r) return;
    r.at = Date.now();
    const phase = r.phase === 0 ? (r.practice ? "Practice: the track is open" : "On the grid") : r.phase === 1 ? (r.practice ? "Practice" : `Racing · ${r.laps} laps`) : "Finished";
    $("phase").textContent = (r.paused ? "PAUSED · " : "") + phase;
    if (r.phase !== 1) $("countdown").textContent = r.phase === 2 ? "FINISH" : "";
    if (r.phase === 2 && r.results) {
        const lines = r.results.map(([name, laps, t], i) => `${i + 1}. ${name}${t !== null && t !== undefined ? ` ${fmtTime(t)}` : ` (${laps} laps)`}`);
        toast(lines.join("\n"), true, 12000);
    }
}

function fmtTime(t) {
    const m = Math.floor(t / 60), s = (t - m * 60).toFixed(2).padStart(5, "0");
    return m ? `${m}:${s}` : `${s}s`;
}

function renderPlaces() {
    const r = state.race, roster = state.roster;
    if (!r || !roster) return;
    const karts = new Map((roster.karts || []).map(k => [k.id, k]));
    const latest = state.snaps.length ? new Map(state.snaps[state.snaps.length - 1].entities.map(e => [e.id, e])) : new Map();
    const rows = (r.places || []).map((id, i) => {
        const k = karts.get(id) || {name: "?", colour: [128, 128, 128]};
        const e = latest.get(id);
        const lap = e ? Math.min(e.lap + 1, r.laps || e.lap + 1) : "";
        const c = (k.colour || [128, 128, 128]).map(v => Math.round(v));
        return `<div data-id="${id}"><span class="n">${i + 1}</span><span class="sw" style="background:rgb(${c.join(",")})"></span>` +
               `<span>${esc(k.name)}${k.cpu ? ` <small>(cpu)</small>` : ""}</span><span class="lap">${lap !== "" ? `lap ${lap}` : ""}</span></div>`;
    });
    $("places").innerHTML = rows.join("") || "<div><small>No karts yet</small></div>";
    $("places").querySelectorAll("div[data-id]").forEach(el => el.onclick = () => followKart(Number(el.dataset.id)));
}

function followKart(id) {
    if (!state.scene) return;
    if (state.scene.follow === id && state.scene.mode === "chase") state.scene.setMode("tv", null);
    else state.scene.setMode("chase", id);
    updatePills();
    if (state.tab === "camera") renderPanel();
}

function renderPerf() {
    const s = state.scene;
    const info = s ? s.gpuInfo() : {};
    $("perf").innerHTML = `${state.fps} fps · ping ${Math.round(state.pingMs)} ms · stalls ${state.stalls} · missed ${state.missed}<br>` +
        `${s ? s.tier : ""} · WebGL${info.webgl || "?"}${info.webgpu ? " · WebGPU available" : ""} · ${esc(String(info.renderer || "").slice(0, 60))}`;
}

function updatePills() {
    const L = state.lesson;
    $("lessonpill").textContent = L ? `Mission ${L.lesson_number} · ${state.track ? state.track.name : L.track} · ${L.mode === "race" ? "race" : "practice"}` : "";
    const sc = state.scene;
    $("camerapill").textContent = sc ? (sc.mode === "chase" ? `Camera: chasing kart ${sc.follow}` : sc.mode === "tv" ? "Camera: TV (drag to orbit, wheel to zoom)" : "Camera: overview") : "";
}

function addEvent(text) {
    const key = text + "|" + Math.floor(Date.now() / 60000);
    if (state.eventKeys.has(key)) return;
    state.eventKeys.add(key);
    state.events.push(text);
    if (state.events.length > 6) state.events.shift();
    $("events").innerHTML = state.events.map(e => `<div>${esc(e)}</div>`).join("");
}

let toastTimer = null;
function toast(text, big = false, ms = 3500) {
    const t = $("toast");
    t.textContent = text;
    t.className = "hud" + (big ? " big" : "");
    t.style.display = "block";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.style.display = "none"; }, ms);
}

function esc(s) {
    return String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}

// ---------- the side panel ----------
function renderPanel() {
    const body = $("panelbody");
    const L = state.lesson, R = state.rules;
    if (state.tab === "controls") {
        if (!L || !R) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return; }
        const tracks = Object.entries(R.tracks || {}).map(([k, n]) => `<option value="${k}" ${k === L.track ? "selected" : ""}>${esc(n)}</option>`).join("");
        const levels = (R.cpu_levels || []).map(l => `<option ${l === L.cpu_level ? "selected" : ""}>${l}</option>`).join("");
        const missions = [1, 2, 3, 4, 5].map(n => `<button data-mission="${n}" class="${n === L.lesson_number ? "on" : ""}">${n}</button>`).join("");
        const racing = state.race && state.race.phase === 1;
        body.innerHTML = `
          <h2>The race</h2>
          <div class="row">
            <button id="btn-start" class="go">${L.mode === "practice" ? "START A RACE" : racing ? "RESTART" : "START"}</button>
            <button id="btn-grid">TO THE GRID</button>
            <button id="btn-pause" class="${state.race && state.race.paused ? "on" : ""}">${state.race && state.race.paused ? "RESUME" : "PAUSE"}</button>
          </div>
          <div class="note">${L.mode === "practice" ? "Practice: the track is open and laps are timed. START A RACE closes it until GO." : "Race mode: START begins the countdown; TO THE GRID lines everyone up again."}</div>
          <div class="row"><label>Mode</label>
            <button data-mode="practice" class="${L.mode !== "race" ? "on" : ""}">Practice</button>
            <button data-mode="race" class="${L.mode === "race" ? "on" : ""}">Race</button></div>
          <div class="row"><label>Grand prix</label>
            ${state.tournament ? `<span>${esc(state.tournament.title || state.tournament.label || "running")}</span> <button id="btn-gp-stop" class="stop">END IT</button>`
                               : `<select id="gp-races"><option>2</option><option selected>3</option><option>4</option><option>5</option></select> races <button id="btn-gp" class="go">START THE GRAND PRIX</button>`}
          </div>
          <h2>Mission</h2>
          <div class="row">${missions}</div>
          <div class="note">The mission sets the learners' tools and the track's switches. Its text is edited in the Kart Lab teacher window's Outcomes tab for now.</div>
          <h2>The track</h2>
          <div class="row"><label>Track</label><select id="sel-track">${tracks}</select></div>
          <div class="row"><label>Laps</label><select id="sel-laps">${[1, 2, 3, 4, 5].map(n => `<option ${n === L.laps ? "selected" : ""}>${n}</option>`).join("")}</select></div>
          <div class="row"><label>Computer karts</label><select id="sel-cpu">${[0, 1, 2, 3, 4, 5, 6, 7].map(n => `<option ${n === L.cpu_karts ? "selected" : ""}>${n}</option>`).join("")}</select>
            <select id="sel-level">${levels}</select></div>
          <div class="row"><label>Teacher's kart</label><button id="btn-tkart" class="${L.teacher_kart ? "on" : ""}">${L.teacher_kart ? "On the grid" : "Not racing"}</button></div>
          <div class="row"><label>Designs</label><button id="btn-lock" class="${L.designs_locked ? "on" : ""}">${L.designs_locked ? "Locked" : "Learners may change them"}</button></div>
          <div class="row"><button id="btn-save">SAVE THESE SETTINGS FOR THE MISSION</button><button id="btn-restore">RESTORE</button></div>`;
        const lessonSend = patch => send({type: "lesson", lesson: patch});
        $("btn-start").onclick = () => send({type: "start"});
        $("btn-grid").onclick = () => send({type: "grid"});
        $("btn-pause").onclick = () => send({type: "pause"});
        body.querySelectorAll("button[data-mode]").forEach(b => b.onclick = () => lessonSend({mode: b.dataset.mode}));
        body.querySelectorAll("button[data-mission]").forEach(b => b.onclick = () => send({type: "lesson_number", n: Number(b.dataset.mission)}));
        $("sel-track").onchange = e => lessonSend({track: e.target.value});
        $("sel-laps").onchange = e => lessonSend({laps: Number(e.target.value)});
        $("sel-cpu").onchange = e => lessonSend({cpu_karts: Number(e.target.value)});
        $("sel-level").onchange = e => lessonSend({cpu_level: e.target.value});
        $("btn-tkart").onclick = () => lessonSend({teacher_kart: !L.teacher_kart});
        $("btn-lock").onclick = () => lessonSend({designs_locked: !L.designs_locked});
        $("btn-save").onclick = () => send({type: "save_lesson"});
        $("btn-restore").onclick = () => send({type: "restore_lesson"});
        if ($("btn-gp")) $("btn-gp").onclick = () => send({type: "tournament", start: true, races: Number($("gp-races").value)});
        if ($("btn-gp-stop")) $("btn-gp-stop").onclick = () => send({type: "tournament", start: false});
    } else if (state.tab === "learners") {
        const roster = state.roster, race = state.race;
        const perf = (roster && roster.perf) || {};
        const brains = (race && race.brains) || {};
        const latest = state.snaps.length ? new Map(state.snaps[state.snaps.length - 1].entities.map(e => [e.id, e])) : new Map();
        const people = state.classList.length ? state.classList : [];
        const rows = people.map(p => {
            const kid = roster && roster.mine ? roster.mine[p.name] : null;
            const e = kid !== null && kid !== undefined ? latest.get(kid) : null;
            const pf = perf[p.name] || {};
            const b = brains[p.name];
            const stalls = pf.stalls ?? "";
            return `<tr><td>${esc(p.name)}</td><td>${p.role}</td><td>${esc((p.design && p.design.name) || "")}</td>` +
                   `<td class="num">${e ? e.lap : ""}</td><td class="num">${pf.fps ?? ""}</td><td class="num">${pf.ping ?? ""}</td>` +
                   `<td class="num ${Number(stalls) > 5 ? "bad" : ""}">${stalls}</td><td>${pf.tier ?? ""}</td>` +
                   `<td>${b ? (b.on ? "<span class='ok'>driving</span>" : b.has ? "loaded" : "") : ""}${b && b.error ? ` <span class='bad'>error</span>` : ""}</td></tr>`;
        }).join("");
        body.innerHTML = `
          <h2>Who is here</h2>
          <table><tr><th>Name</th><th>Role</th><th>Kart</th><th>Lap</th><th>fps</th><th>ping</th><th>stalls</th><th>graphics</th><th>brain</th></tr>${rows}</table>
          <div class="note">fps, ping and stalls come from each learner's window every few seconds. Stalls are frames that arrived late
            (over 100 ms apart): a few a minute is the Wi-Fi; dozens means that laptop or the room's network needs looking at.</div>
          <h2>Lap times</h2>
          <table>${Object.entries((race && race.lap_times) || {}).map(([kid, times]) => {
              const k = roster && roster.karts ? roster.karts.find(x => String(x.id) === kid) : null;
              const t = Array.isArray(times) ? times : [];
              return `<tr><td>${esc(k ? k.name : kid)}</td><td class="num">${t.length ? fmtTime(Math.min(...t)) : ""}</td><td>${t.map(fmtTime).join(", ")}</td></tr>`;
          }).join("") || "<tr><td class='note'>No laps yet</td></tr>"}</table>`;
    } else if (state.tab === "camera") {
        const sc = state.scene;
        const karts = (state.roster && state.roster.karts) || [];
        body.innerHTML = `
          <h2>Camera</h2>
          <div class="row"><button data-cam="tv" class="${sc.mode === "tv" ? "on" : ""}">TV</button>
            <button data-cam="overview" class="${sc.mode === "overview" ? "on" : ""}">Whole track</button></div>
          <div class="note">TV follows the leader (or the kart you pick below); drag to orbit, wheel to zoom. Chase sits behind one kart.</div>
          <h2>Chase a kart</h2>
          <div class="row">${karts.map(k => `<button data-follow="${k.id}" class="${sc.mode === "chase" && sc.follow === k.id ? "on" : ""}">${esc(k.name)}</button>`).join("") || "<span class='note'>No karts yet</span>"}</div>`;
        body.querySelectorAll("button[data-cam]").forEach(b => b.onclick = () => { sc.setMode(b.dataset.cam, null); updatePills(); renderPanel(); });
        body.querySelectorAll("button[data-follow]").forEach(b => b.onclick = () => followKart(Number(b.dataset.follow)));
    } else if (state.tab === "graphics") {
        const sc = state.scene, info = sc.gpuInfo();
        body.innerHTML = `
          <h2>Graphics tier</h2>
          <div class="row">${TIERS.map(t => `<button data-tier="${t}" class="${sc.tier === t ? "on" : ""}">${t}</button>`).join("")}
            <button id="btn-auto" class="${state.autoTier ? "on" : ""}">auto step-down</button></div>
          <div class="note">blocks: flat colours, nothing lit, the floor every machine draws. low: lit, one shadow map, fog.
            high: PBR materials, soft shadows, bloom and antialiasing. Auto steps down one tier when the frame rate stays under 24.</div>
          <h2>This browser</h2>
          <table><tr><th>WebGL</th><td>${info.webgl}</td></tr><tr><th>WebGPU</th><td>${info.webgpu ? "available (not used yet)" : "no"}</td></tr>
            <tr><th>Renderer</th><td>${esc(info.renderer)}</td></tr><tr><th>Screen</th><td>${window.innerWidth} x ${window.innerHeight} at ${devicePixelRatio}x</td></tr>
            <tr><th>Frame rate</th><td>${state.fps} fps, ${state.stalls} stalls, ${state.missed} missed snapshots</td></tr></table>
          <div class="note">These numbers from a school laptop and a Chromebook are the measurement nobody has published: note them down.</div>`;
        body.querySelectorAll("button[data-tier]").forEach(b => b.onclick = () => { sc.setTier(b.dataset.tier); renderPanel(); renderPerf(); });
        $("btn-auto").onclick = () => { state.autoTier = !state.autoTier; renderPanel(); };
    } else {
        body.innerHTML = `
          <h2>About</h2>
          <p class="note">Club Coders Live ${esc(state.version || "")}: the teacher's view of a class in the browser, the first step of
            the browser window. It joins the class server as the teacher window does, draws the race from the same
            30-a-second snapshots, two snapshots behind so the picture is smooth, and sends the same commands.</p>
          <p class="note">Not here yet: playing (a kart you drive), the learners' lessons and garage, Robot Lab and Fight Lab.
            Those are the next steps.</p>
          <p class="note">Keys: <b>Tab</b> opens and closes this panel.</p>`;
    }
}

// ---------- start ----------
function setupUi() {
    $("class").onchange = () => {
        const other = $("class").value === "other";
        $("host").hidden = $("hostlabel").hidden = !other;
    };
    $("connect").onclick = connect;
    $("code").onkeydown = e => { if (e.key === "Enter") connect(); };
    $("toggle").onclick = () => $("panel").classList.toggle("open");
    document.addEventListener("keydown", e => {
        if (e.key === "Tab" && state.connected) { e.preventDefault(); $("panel").classList.toggle("open"); }
    });
    document.querySelectorAll("#panel header button").forEach(b => b.onclick = () => {
        document.querySelectorAll("#panel header button").forEach(x => x.classList.toggle("on", x === b));
        state.tab = b.dataset.tab;
        renderPanel();
    });
    try {
        if (localStorage.getItem("class")) $("class").value = localStorage.getItem("class");
        if (localStorage.getItem("name")) $("name").value = localStorage.getItem("name");
        if (sessionStorage.getItem("code")) $("code").value = sessionStorage.getItem("code");
    } catch (e) { /* storage blocked */ }
    if (params.get("host")) { $("class").value = "other"; $("host").value = params.get("host"); $("host").hidden = $("hostlabel").hidden = false; }
    if (params.get("code")) $("code").value = params.get("code");
    if (params.get("name")) $("name").value = params.get("name");
}

// anything that goes wrong is shown on the page (a school laptop has no console open) and kept for the tests
window.__errors = [];
window.addEventListener("error", e => { window.__errors.push(String(e.message)); toast("Problem: " + e.message, false, 8000); });
window.addEventListener("unhandledrejection", e => { window.__errors.push(String(e.reason)); toast("Problem: " + e.reason, false, 8000); });
window.__state = state;  // (the tests read it)

async function main() {
    setupUi();
    const tier = TIERS.includes(params.get("tier")) ? params.get("tier") : "low";
    try {
        state.scene = new KartScene($("view"), tier);
        const info = state.scene.gpuInfo();
        if (!params.get("tier") && /NVIDIA|Radeon RX|Apple M|Arc\(TM\) A|RTX|GTX/i.test(info.renderer || "")) state.scene.setTier("high");
        state.scene.setTrack(new Track(TRACKS.club));
        state.track = state.scene.track;
    } catch (e) {
        setStatus(`This browser can't draw the game (WebGL): ${e.message}`);
    }
    const v = await pageVersion();
    $("pageversion").textContent = v || "(laptop test)";
    renderPerf();
    requestAnimationFrame(loop);
    if (params.get("autoconnect")) connect();
}

main();
