// Club Coders Live (CHANGE 127, 129, 130): the teacher's browser window on a class server.
//
// The page speaks the same protocol as a game's teacher window: a JSON hello (with the desk's ticket), then the
// lesson, the class, teaching data and notices, and the game's snapshots 30 times a second (Kart Lab's binary,
// wire.js; Robot Lab's and Fight Lab's JSON). The game's own file (kart.js, robot.js, fight.js) draws them two
// snapshots behind the newest, as the windows do (engine/interp.py), and carries its controls; teacher.js has the
// tabs every game shares. Learners' windows report how they are doing (fps, ping, stalls) and the Learners tab
// shows it. The teacher desk (desk.js) is the app's Teacher screen.
//
// Query string: ?host=ws://127.0.0.1:8782 for a laptop test server (the class picker is then "another server"),
// ?code=TEACH99 to prefill the code, ?tier=blocks|low|medium|high, ?version=1.9.1 (a class server wants the release's
// number; on the VPS the page reads it from /live/version).

import {TIERS, pageEngine, engineInfo, setSkyData} from "./base3d.js";
import {DeskLink, renderDesk} from "./desk.js";
import {KartGame} from "./kart.js";
import {RobotGame} from "./robot.js";
import {FightGame} from "./fight.js";
import {TEACHER_TABS, renderTeacherTab, missionRow, wireMissionRow, restartRow, wireRestartRow, download, esc} from "./teacher.js";

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const DELAY_MS = 80;            // how far behind the newest snapshot the page draws (two snapshots plus jitter)
const CLOSE_TEXT = {4001: "Wrong teacher code.", 4002: "A teacher window is already open on this class: close it first.",
                    4006: "This page is out of date for that server.", 4008: "Too many wrong tries: wait a minute.",
                    4011: "The ticket ran out: log in again.", 4010: "That group hasn't started.", 4009: "The session has ended."};
let engine = null;

const state = {
    ws: null, connected: false, role: null, name: "", game: null,
    version: params.get("version") || "",
    lesson: null, rules: null, roster: null, race: null, classList: [], tournament: null, teaching: null,
    snaps: [], offset: null, lastSeq: null, missed: 0, stalls: 0, pingMs: 0, lastPong: 0, reconnects: 0,
    events: [], eventKeys: new Set(), tab: "controls", scene: null, game: null, tier: "low",
    fps: 0, frames: 0, fpsAt: performance.now(), autoTier: params.get("auto") !== "0",
    desk: null, deskUi: null, lessons: {}, watchGames: [], leaving: false,
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

// ---------- the desk: the teacher password gives a ticket for any class (CHANGE 128) ----------
function deskUrl() {
    return params.get("desk") || `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/desk`;
}

// The teacher desk (CHANGE 129): the page stays connected to the desk while logged in, and shows the Teacher screen
// (desk.js); watching a class asks the desk for a teacher ticket for it.
function deskLogin() {
    const password = $("deskpass").value;
    if (!password) return setStatus("The teacher password is needed.");
    setStatus("Logging in to the desk…", true);
    if (state.desk) state.desk.close();
    state.deskUi = {tab: null, editing: null, confirm: null, message: null};
    state.desk = new DeskLink(deskUrl(), password, {
        ready: first => {
            if (first) {
                $("deskpass").value = "";
                try { if (window.PasswordCredential) navigator.credentials.store(new PasswordCredential({id: "teacher", password})); } catch (e) { /* not offered */ }
                try { localStorage.setItem("mode", "desk"); } catch (e) { /* private window */ }
                setStatus("");
                showDesk();
                if (params.get("game")) watch(params.get("game"));
            }
            updateDeskButton();
        },
        changed: () => { if (deskShown()) drawDesk(); updateDeskButton(); },
        message: (text, ok) => { state.deskUi.message = {text, ok}; if (deskShown()) drawDesk(); else if (!ok) toast(text); },
        closed: text => {
            state.desk = null;
            updateDeskButton();
            hideDesk();
            dropView();
            showLogin();
            setStatus(text);
        },
    });
}

const DRAWN = new Set(["kartlab", "robotlab", "fightlab"]);  // the games this page draws

function deskShown() { return !$("desk").hidden; }

function showDesk() {
    if (!state.desk) return;
    $("login").style.display = "none";
    $("desk").hidden = false;
    $("panel").classList.remove("open");
    drawDesk();
}

function hideDesk() { $("desk").hidden = true; }

function drawDesk() {
    if (!state.desk || !state.desk.state) return;
    renderDesk($("deskbody"), {
        desk: state.desk, ui: state.deskUi, lessons: state.lessons, drawn: DRAWN, watchGames: state.watchGames,
        watching: state.connected && state.game ? state.game.id : null, watch, rerender: drawDesk, back: hideDesk, leave: leaveView,
        logout: deskLogout, stopped: leaveView, launched: game => { if (DRAWN.has(game)) watch(game); },
    });
}

function deskSay(text, ok = false) {
    if (!state.deskUi) return;
    state.deskUi.message = {text, ok};
    if (deskShown()) drawDesk();
}

function updateDeskButton() {
    const b = $("btn-desk"), live = state.desk && state.desk.state && state.desk.state.live;
    b.hidden = !state.desk;
    b.textContent = live ? `TEACHER DESK · LIVE: ${live.group}` : "TEACHER DESK";
}

function watch(game) {
    if (!state.desk) return;
    if (!DRAWN.has(game)) return deskSay("That game isn't drawn in the browser yet: open its teacher window from the app.");
    if (state.connected && state.ticket && state.ticket.game === game) { hideDesk(); return; }
    deskSay("Opening the class view…", true);
    state.desk.ask({type: "watch", game}, "watch").then(m => {
        state.ticket = m.watch;
        if (state.ws) { const old = state.ws; state.ws = null; state.connected = false; old.close(); }
        connect(m.watch.address, {ticket: m.watch.ticket, name: "Teacher"});
    }, e => deskSay(e.message));
}

function leaveView() {
    if (state.ws) { state.leaving = true; state.ws.close(); }
}

function dropView() {  // (close the class connection without its close message: the caller says what happened)
    if (!state.ws) return;
    const old = state.ws;
    state.ws = null;
    state.connected = false;
    old.close();
}

function deskLogout() {
    const desk = state.desk;
    state.desk = null;
    if (desk) desk.close();
    updateDeskButton();
    hideDesk();
    dropView();
    showLogin();
    setStatus("Logged out.", true);
}

function login() {
    if (state.codeMode) return connect();
    return deskLogin();
}

function setCodeMode(on) {
    state.codeMode = on;
    $("codeform").hidden = !on;
    $("deskform").hidden = on;
    $("switchmode").textContent = on ? "Use the teacher password instead" : "Use a class server's code instead";
    setStatus("");
}

function connect(address = null, how = null) {
    const url = address || wsUrl();
    const code = $("code").value.trim(), name = (how && how.name) || $("name").value.trim() || "Teacher";
    if (!url) return setStatus("Which server?");
    if (!how && !code) return setStatus("The class code is needed.");
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
    state.url = url;
    state.lastHow = {address: url, how};
    state.snaps = [];  // (a fresh class: nothing from the last one's clock)
    state.offset = state.lastSeq = null;
    ws.onopen = () => {
        const hello = how && how.ticket ? {type: "hello", name, ticket: how.ticket, version: state.version}
                                        : {type: "hello", name, code, version: state.version};
        ws.send(JSON.stringify(hello));
        setStatus("Logging in…", true);
    };
    ws.onmessage = ev => onMessage(ev.data);
    ws.onclose = ev => {
        if (state.ws !== ws) return;  // (replaced by another class's connection)
        let text = CLOSE_TEXT[ev.code] || ev.reason || (state.connected ? "The connection closed." : "Couldn't connect. Is the server there, and the address right?");
        const left = state.leaving, was = state.connected || state.reconnects > 0;
        state.connected = false;
        state.ws = null;
        state.leaving = false;
        if (!left && was && !(ev.code >= 4000 && ev.code < 4100) && state.reconnects < 30) {  // (a restart or the Wi-Fi)
            state.reconnects++;
            toast(state.expectRestart && Date.now() - state.expectRestart < 60000 ? "The class server is restarting: reconnecting…"
                                                                                : "Lost the class: reconnecting…", false, 4000);
            setTimeout(reconnect, Math.min(5000, 1000 + 500 * state.reconnects));
            return;
        }
        if (state.desk) {  // (back to the Teacher screen, still logged in to the desk)
            showDesk();
            deskSay(left ? "You've left the class view." : `The class view closed: ${text}`, left);
            return;
        }
        if (left) text = "Logged out.";
        showLogin();
        setStatus(text, left);
    };
    ws.onerror = () => { /* onclose follows with the reason */ };
    try {
        if (!how) { sessionStorage.setItem("code", code); localStorage.setItem("class", $("class").value); localStorage.setItem("name", name); }
        localStorage.setItem("mode", state.codeMode ? "code" : "desk");
    } catch (e) { /* private window */ }
}

function reconnect() {
    if (state.ws || state.connected) return;
    if (state.desk && state.ticket && !state.codeMode) {  // (a fresh ticket from the desk)
        state.desk.ask({type: "watch", game: state.ticket.game}, "watch").then(m => {
            state.ticket = m.watch;
            connect(m.watch.address, {ticket: m.watch.ticket, name: "Teacher"});
        }, () => setTimeout(reconnect, 3000));
        return;
    }
    if (state.lastHow) connect(state.lastHow.address, state.lastHow.how);
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
// What every game sends is kept here (the lesson, the class, the roster's perf, teaching, warnings...); the game
// (kart.js, robot.js, fight.js) draws its own world from its snapshots and the rest.
const GAMES = [KartGame, RobotGame, FightGame];
const GAME_BY_ID = {kartlab: KartGame, robotlab: RobotGame, fightlab: FightGame};

function startGame(m) {
    const wanted = (state.ticket && GAME_BY_ID[state.ticket.game] && !state.codeMode) ? GAME_BY_ID[state.ticket.game]
                   : GAMES.find(G => G.detect(m)) || RobotGame;
    if (state.game && state.game.constructor === wanted) return state.game;  // (a reconnect: keep what's drawn)
    if (state.game) state.game.dispose();
    state.game = new wanted(appApi);
    state.scene = state.game.scene;
    return state.game;
}

function onMessage(data) {
    const now = performance.now();
    if (data instanceof ArrayBuffer) {
        if (state.game) state.game.binary(data, now);
        return;
    }
    let m;
    try { m = JSON.parse(data); } catch (e) { return; }
    const game = state.game;
    switch (m.type) {
        case "welcome": {
            state.connected = true;
            state.reconnects = 0;
            state.role = m.role;
            state.rules = m.rules || {};
            state.lesson = m.lesson || null;
            state.myDesign = m.design || null;
            state.liveReady = m.live_ready || null;
            state.snaps = [];
            state.offset = state.lastSeq = null;
            const g = startGame(m);
            g.welcome(m);
            hideLogin();
            hideDesk();
            buildTabs();
            $("where").textContent = `${g.title} · ${state.url.replace(/^wss?:\/\//, "")} · ${m.role}`;
            addEvent(`Logged in to ${g.title} as ${m.name} (${m.role})`);
            send({type: "ping", t: Date.now()});
            if (params.get("panel")) { $("panel").classList.add("open"); state.tab = params.get("panel"); buildTabs(); }
            updatePills();
            renderPanel();
            return;
        }
        case "lesson":
            state.lesson = m.lesson || state.lesson;
            state.classList = m.class || [];
            state.tournament = m.tournament || null;
            state.mods = m.mods || state.mods;
            if (game) game.message(m);
            updatePills();
            renderPanelSoon();
            return;
        case "roster":
            state.roster = m;
            if (game) game.message(m);
            if (state.tab === "learners") renderPanelSoon();
            return;
        case "teaching":
            state.teachingAt = Date.now();
            if (JSON.stringify(m) !== state.teachingKey) {
                state.teachingKey = JSON.stringify(m);
                state.teaching = m;
                if (["outcomes", "cards", "learners"].includes(state.tab)) renderPanelSoon();
            }
            return;
        case "missions":
            if (m.for) { state.viewing = m; if (state.tab === "learners") renderPanelSoon(); }
            return;
        case "session":
            state.session = m.session || null;
            return;
        case "warnings":
            state.warnings = m.list || m.warnings || m.items || [];
            updateTabCounts();
            if (state.tab === "warnings") renderPanelSoon();
            return;
        case "history":
            state.history = m.items || [];
            if (state.tab === "learners") renderPanel();
            return;
        case "design_result":
            if (m.ok && !m.by_teacher) state.myDesign = m.design;
            toast(m.ok ? "Built." : `Not built: ${(m.problems || []).join("; ")}`, false, 5000);
            return;
        case "evidence_csv":
            download(m.name || "evidence.csv", m.text || "", "text/csv");
            toast(`Downloaded ${m.name}`);
            return;
        case "missions_file":
            download(m.name || "missions.json", m.text || "", "application/json");
            toast(`Downloaded ${m.name}`);
            return;
        case "live_update":
            state.liveReady = m.id || true;
            toast("A live update is ready on the class server.\nWarn the class, then press Restart server (Controls).", true, 12000);
            return;
        case "pong":
            if (m.t) state.pingMs = Date.now() - m.t;
            return;
        case "notice":
            toast(m.text || "", !!m.big, m.big ? 12000 : 5000);
            if (/RESTARTING|UPDATING/.test(m.text || "")) state.expectRestart = Date.now();
            return;
        case "restart_client":
            return;
        default:
            if (game) game.message(m);
    }
}

// the snapshots every game blends between: kept with the server's clock (sm), drawn DELAY_MS behind the newest
function pushSnap(snap, now) {
    snap.at = now;
    if (snap.seq !== undefined) {
        if (state.lastSeq !== null) {
            const gap = (snap.seq - state.lastSeq) & 0xFFFF;
            if (gap > 1 && gap < 1000) state.missed += gap - 1;
        }
        state.lastSeq = snap.seq;
    }
    // the clock offset between the server's ms and ours: the smallest arrival lag seen, drifting up slowly
    const lag = now - snap.sm;
    state.offset = state.offset === null ? lag : Math.min(lag, state.offset + 0.002 * (now - (state.offsetAt || now)));
    state.offsetAt = now;
    state.snaps.push(snap);
    if (state.snaps.length > 90) state.snaps.shift();
}

// {a, b, f}: the two snapshots around the moment to draw and how far between them (b null at the newest)
function samplePair(now) {
    const snaps = state.snaps;
    if (!snaps.length || state.offset === null) return null;
    const t = now - state.offset - DELAY_MS;
    for (let i = snaps.length - 1; i >= 0; i--) {
        if (snaps[i].sm <= t) {
            const a = snaps[i], b = snaps[i + 1] || null;
            return {a, b, f: b ? Math.max(0, Math.min(1, (t - a.sm) / Math.max(1, b.sm - a.sm))) : 0};
        }
    }
    return {a: snaps[0], b: null, f: 0};
}

// ---------- drawing ----------
let lastFrame = performance.now();
function loop() {
    const now = performance.now();
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    if (now - lastFrame > 100) state.stalls++;
    lastFrame = now;
    state.frames++;
    const covered = $("login").style.display !== "none" || deskShown();  // (nothing to see behind them: don't draw)
    if (now - state.fpsAt > 1000) {
        state.fps = Math.round(state.frames * 1000 / (now - state.fpsAt));
        state.frames = 0;
        state.fpsAt = now;
        renderPerf();
        // three slow seconds in a row (under 28 a second) while a game is drawn: one tier down, kept for next time
        state.slow = state.game && !covered && state.fps && state.fps < 28 ? (state.slow || 0) + 1 : 0;
        if (state.autoTier && state.scene && state.slow >= 3 && now - (state.tierAt || 0) > 8000) {
            const i = TIERS.indexOf(state.scene.tier);
            if (i > 0) { setTier(TIERS[i - 1]); state.tierAt = now; state.slow = 0; toast(`Graphics stepped down to ${TIERS[i - 1]} (the frame rate was ${state.fps})`); }
        }
        if (state.connected) {
            send({type: "ping", t: Date.now()});
            send({type: "perf", fps: state.fps, ping: Math.round(state.pingMs), tier: "web-" + state.tier, stalls: state.stalls, delay: DELAY_MS});
        }
    }
    if (state.game && !covered) {
        state.game.frame(now, dt);
        state.game.scene.render();
    }
    requestAnimationFrame(loop);
}

function setTier(tier) {
    state.tier = tier;
    try { localStorage.setItem("tier", tier); } catch (e) { /* storage blocked: chosen again next time */ }
    if (state.scene) state.scene.setTier(tier);
    if (state.tab === "graphics") renderPanel();
    renderPerf();
}

function renderPerf() {
    const info = engineInfo(engine);
    $("perf").innerHTML = `${state.fps} fps · ping ${Math.round(state.pingMs)} ms · stalls ${state.stalls} · missed ${state.missed}<br>` +
        `${state.tier} · ${info.width} x ${info.height} · WebGL${info.webgl || "?"}${info.webgpu ? " · WebGPU available" : ""} · ${esc(String(info.renderer || "").slice(0, 60))}`;
}

function updatePills() {
    const g = state.game;
    $("lessonpill").textContent = g ? g.pill() : "";
    $("camerapill").textContent = g && g.cameraPill ? g.cameraPill() : "";
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

// ---------- the side panel ----------
function allTabs() {
    const g = state.game;
    const gameTabs = g ? g.tabs() : [];
    return [gameTabs[0] || ["controls", "Controls"], ...TEACHER_TABS, ...gameTabs.slice(1), ["graphics", "Graphics"], ["about", "About"]];
}

function buildTabs() {
    const tabs = allTabs();
    if (!tabs.some(([k]) => k === state.tab)) state.tab = tabs[0][0];
    $("panelhead").innerHTML = tabs.map(([k, n]) => `<button data-tab="${k}" class="${k === state.tab ? "on" : ""}">${n}</button>`).join("");
    $("panelhead").querySelectorAll("button").forEach(b => b.onclick = () => {
        state.tab = b.dataset.tab;
        $("panelhead").querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
        renderPanel();
    });
    updateTabCounts();
}

function updateTabCounts() {
    const b = $("panelhead").querySelector('button[data-tab="warnings"]');
    if (b) b.textContent = (state.warnings || []).length ? `Warnings (${state.warnings.length})` : "Warnings";
}

let panelTimer = null;
function renderPanelSoon() {  // (several messages in a burst: draw the panel once)
    if (panelTimer) return;
    panelTimer = setTimeout(() => { panelTimer = null; renderPanel(); }, 120);
}

// typed text survives the redraws (the lesson and the teaching data arrive every second); a different page of
// the panel (another tab, learner or mission) starts clean
function renderPanel() {
    const body = $("panelbody");
    const key = [state.tab, state.pick, state.sub, state.editLesson, state.formSeq].join("|");
    const same = key === state.panelKey;
    state.panelKey = key;
    const values = {};
    let focus = null, sel = null;
    if (same) {
        body.querySelectorAll("input[id], select[id], textarea[id]").forEach(el => { if (el.type !== "checkbox" && el.type !== "file") values[el.id] = el.value; });
        const a = document.activeElement;
        if (a && body.contains(a) && a.id) { focus = a.id; try { sel = [a.selectionStart, a.selectionEnd]; } catch (e) { sel = null; } }
    }
    const scroll = body.scrollTop;
    drawPanel(body);
    for (const [id, v] of Object.entries(values)) {
        const el = body.querySelector("#" + CSS.escape(id));
        if (el) el.value = v;
    }
    if (focus) {
        const el = body.querySelector("#" + CSS.escape(focus));
        if (el) { el.focus(); try { if (sel && sel[0] !== null) el.setSelectionRange(...sel); } catch (e) { /* not text */ } }
    }
    if (same) body.scrollTop = scroll;
}

function drawPanel(body) {
    const g = state.game;
    if (!g) { body.innerHTML = "<p class='note'>Not connected.</p>"; return; }
    if (g.renderTab(state.tab, body)) return;
    if (renderTeacherTab(appApi, state.tab, body)) return;
    if (state.tab === "graphics") {
        const sc = state.scene, info = engineInfo(engine);
        body.innerHTML = `
          <h2>Graphics tier</h2>
          <div class="row">${TIERS.map(t => `<button data-tier="${t}" class="${state.tier === t ? "on" : ""}">${t}</button>`).join("")}
            <button id="btn-auto" class="${state.autoTier ? "on" : ""}">auto step-down</button></div>
          <div class="note">The app's tiers, lit by the app's own lighting. blocks: flat colours, nothing lit, the floor every
            machine draws. low: the app's lighting and textures, no shadows or reflections. medium: surface detail, the sky's
            reflections, shadows. high: sharper shadows and textures, and the most pixels. Each tier draws at most so many
            pixels however fine the screen. Auto steps down one tier after three seconds under 28 frames a second, and the
            page remembers the tier on this computer.</div>
          <h2>This browser</h2>
          <table><tr><th>WebGL</th><td>${info.webgl}</td></tr><tr><th>WebGPU</th><td>${info.webgpu ? "available (not used yet)" : "no"}</td></tr>
            <tr><th>Renderer</th><td>${esc(info.renderer)}</td></tr><tr><th>Screen</th><td>${window.innerWidth} x ${window.innerHeight} at ${devicePixelRatio}x</td></tr>
            <tr><th>Drawing</th><td>${info.width} x ${info.height} pixels (${info.ratio.toFixed(2)} per screen point)${sc ? `, ${sc.drawCalls()} meshes` : ""}</td></tr>
            <tr><th>Frame rate</th><td>${state.fps} fps, ${state.stalls} stalls, ${state.missed} missed snapshots</td></tr></table>
          <div class="note">These numbers from a school laptop and a Chromebook are the measurement nobody has published: note them down.</div>`;
        body.querySelectorAll("button[data-tier]").forEach(b => b.onclick = () => setTier(b.dataset.tier));
        $("btn-auto").onclick = () => { state.autoTier = !state.autoTier; renderPanel(); };
        return;
    }
    body.innerHTML = `
      <h2>About</h2>
      <p class="note">Club Coders Live ${esc(state.version || "")}: the teacher's desk and live view of a class in the browser. It
        joins the class server as the teacher window does, draws the game from the same 30-a-second snapshots, two behind so
        the picture is smooth, and sends the same commands. Kart Lab, Robot Lab and Fight Lab are drawn.</p>
      <p class="note">The TEACHER DESK button (top left) is the app's Teacher screen: learners, groups, Launch and Stop, this
        session's notes and the printed records.</p>
      <p class="note">What still needs the Club Coders app on your laptop: sending AI cards to Claude (Send, Keep, Undo) and the
        Changes tab, because Claude edits the game's files on your laptop. Not here yet: playing, and the learners' side.</p>
      <p class="note">Keys: <b>Tab</b> opens and closes this panel.</p>`;
}

// what the games and teacher.js reach the page through
const appApi = {
    get state() { return state; }, get game() { return state.game; }, get tier() { return state.tier; },
    get canvas() { return $("view"); }, get engine() { return engine; }, params,
    send, toast, addEvent, renderPanel, updatePills, pushSnap, samplePair, esc,
    missionRow: () => missionRow(appApi), wireMissionRow: body => wireMissionRow(appApi, body),
    restartRow: () => restartRow(appApi), wireRestartRow: body => wireRestartRow(appApi, body),
};

// ---------- start ----------
function setupUi() {
    $("class").onchange = () => {
        const other = $("class").value === "other";
        $("host").hidden = $("hostlabel").hidden = !other;
    };
    $("connect").onclick = () => login();
    $("code").onkeydown = e => { if (e.key === "Enter") connect(); };
    $("deskpass").onkeydown = e => { if (e.key === "Enter") deskLogin(); };
    $("switchmode").onclick = e => { e.preventDefault(); setCodeMode(!state.codeMode); };
    $("toggle").onclick = () => { $("panel").classList.toggle("open"); if ($("panel").classList.contains("open")) renderPanel(); };
    $("btn-desk").onclick = () => showDesk();
    document.addEventListener("keydown", e => {
        if (e.key === "Tab" && state.connected && !deskShown() && !/INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) { e.preventDefault(); $("panel").classList.toggle("open"); }
    });
    try {
        if (localStorage.getItem("class")) $("class").value = localStorage.getItem("class");
        if (localStorage.getItem("name")) $("name").value = localStorage.getItem("name");
        if (sessionStorage.getItem("code")) $("code").value = sessionStorage.getItem("code");
    } catch (e) { /* storage blocked */ }
    if (params.get("host")) { $("class").value = "other"; $("host").value = params.get("host"); $("host").hidden = $("hostlabel").hidden = false; }
    if (params.get("code")) $("code").value = params.get("code");
    let mode = null;
    try { mode = localStorage.getItem("mode"); } catch (e) { /* storage blocked */ }
    setCodeMode(!!(params.get("host") || params.get("code")) || (mode === "code" && !params.get("desk")));    if (params.get("name")) $("name").value = params.get("name");
}

// anything that goes wrong is shown on the page (a school laptop has no console open) and kept for the tests
window.__errors = [];
window.addEventListener("error", e => { window.__errors.push(String(e.message)); toast("Problem: " + e.message, false, 8000); });
window.addEventListener("unhandledrejection", e => { window.__errors.push(String(e.reason)); toast("Problem: " + e.reason, false, 8000); });
window.__state = state;  // (the tests read it, and send through the page)
window.__app = appApi;

async function main() {
    setupUi();
    // the tier: ?tier=, else the one kept on this computer, else medium (the app's first guess), high on a graphics card
    let kept = null;
    try { kept = localStorage.getItem("tier"); } catch (e) { /* storage blocked */ }
    state.tier = TIERS.includes(params.get("tier")) ? params.get("tier") : TIERS.includes(kept) ? kept : "medium";
    try {
        engine = state.engine = pageEngine($("view"));
        const info = engineInfo(engine);
        if (!params.get("tier") && !TIERS.includes(kept) && /NVIDIA|Radeon RX|Apple M|Arc\(TM\) A|RTX|GTX/i.test(info.renderer || "")) state.tier = "high";
        if (info.webgl < 2 && state.tier !== "blocks") state.tier = "blocks";  // (the app's lighting needs WebGL 2)
    } catch (e) {
        setStatus(`This browser can't draw the game (WebGL): ${e.message}`);
    }
    try {  // the sky's numbers for the reflections (tex/, made by make_textures.py)
        const r = await fetch("tex/manifest.json");
        if (r.ok) setSkyData(await r.json());
    } catch (e) { /* no reflections */ }
    try {  // (the lessons' names, for the printed records)
        const r = await fetch("lessons.json");
        if (r.ok) state.lessons = await r.json();
    } catch (e) { /* the records print the codes instead */ }
    const v = await pageVersion();
    $("pageversion").textContent = v || "(laptop test)";
    renderPerf();
    requestAnimationFrame(loop);
    if (params.get("autoconnect")) login();
}

main();
