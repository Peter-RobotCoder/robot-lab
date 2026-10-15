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

import {TIERS, TIER_SETTINGS, PARTS, SCREEN, AutoTier, pageEngine, engineInfo, setSkyData, setGraphics, cappedTier, tierSettings,
        cleanParts} from "./base3d.js";
import {DeskLink, LearnerLink, renderDesk} from "./desk.js";
import {KartGame} from "./kart.js";
import {RobotGame} from "./robot.js";
import {FightGame} from "./fight.js";
import {TEACHER_TABS, renderTeacherTab, missionRow, wireMissionRow, restartRow, wireRestartRow, download, esc, twice, claudeChanged} from "./teacher.js";
import {LEARNER_TABS, renderLearnerTab, uploadBrain} from "./learner.js";
import {setupCodePanel, toggleCode, renderCode, designResult} from "./garage.js";
import {Keys, Controller} from "./play.js";
import {Sound, SETTINGS_ROWS, MUSIC, HAS_MUSIC} from "./sound.js";
import {hideHud} from "./hud.js";

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
                try { localStorage.setItem("mode", "teacher"); } catch (e) { /* private window */ }
                setStatus("");
                showDesk();
                if (params.get("game")) watch(params.get("game"));
            }
            updateDeskButton();
        },
        changed: () => { if (deskShown()) drawDesk(); updateDeskButton(); },
        claude: () => claudeChanged(appApi),  // (Claude for the browser said something: CHANGE 136)
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

// A learner's login (CHANGE 134): the desk checks the username and password (a starter one is changed first), then
// says to wait or gives the game's address and a ticket; the page opens the game, and goes back to waiting after it
function learnerLogin() {
    const name = $("lname").value.trim(), password = $("lpass").value;
    if (!name || !password) return setStatus("Your username and password are needed.");
    setStatus("Logging in…", true);
    if (state.learnerLink) state.learnerLink.close();
    const link = state.learnerLink = new LearnerLink(deskUrl(), name, password, {
        changePassword: () => {
            showLoginPart("newpass");
            setStatus("Choose your own password to go on.", true);
        },
        waiting: text => {
            try { localStorage.setItem("mode", "learner"); localStorage.setItem("lname", link.name); } catch (e) { /* private window */ }
            $("lpass").value = "";
            if (state.ws && state.connected) return;  // (already playing: the desk's word is for later)
            showLogin();
            showLoginPart("wait");
            $("waittext").textContent = `Hello ${link.name}. ${text}`;
            setStatus("");
        },
        go: go => {
            $("lpass").value = "";
            state.liveId = go.live_id;
            state.ticket = {game: go.game, address: go.address, ticket: go.ticket};
            if (state.ws) dropView();
            $("waittext").textContent = "Opening the game…";
            connect(go.address, {ticket: go.ticket, name: link.name});
        },
        message: text => setStatus(text, /changed/i.test(text)),
        closed: text => {
            state.learnerLink = null;
            dropView();
            showLogin();
            showLoginPart("form");
            setStatus(text);
        },
    });
}

function setNewPassword() {
    const a = $("npass").value, b = $("npass2").value;
    if (a.length < 6) return setStatus("At least 6 characters, please.");
    if (a !== b) return setStatus("The two passwords aren't the same.");
    $("npass").value = $("npass2").value = "";
    state.learnerLink.setPassword(a);
    setStatus("Saving your password…", true);
}

// which part of the login card shows: the learner's form, the new password, waiting, or the teacher's forms
function showLoginPart(part) {
    const learner = state.mode === "learner";
    $("learnerform").hidden = !(learner && !state.codeMode && part === "form");
    $("newpassform").hidden = part !== "newpass";
    $("waitbox").hidden = part !== "wait";
    $("deskform").hidden = !(!learner && !state.codeMode && part === "form");
    $("codeform").hidden = !(state.codeMode && part === "form");
    $("connect").hidden = part === "wait";
    $("connect").textContent = part === "newpass" ? "SAVE MY PASSWORD" : "LOG IN";
    $("modetabs").hidden = part !== "form";
    state.loginPart = part;
}

function setMode(mode) {
    state.mode = mode;
    $("modetabs").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.mode === mode));
    showLoginPart("form");
    setStatus("");
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
    if (state.loginPart === "newpass") return setNewPassword();
    if (state.codeMode) return connect();
    if (state.mode === "learner") return learnerLogin();
    return deskLogin();
}

function setCodeMode(on) {
    state.codeMode = on;
    showLoginPart("form");
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
                                        : {type: "hello", name, code, version: state.version, password: $("cpass").value};
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
        renderCode(appApi);
        if (!left && was && !(ev.code >= 4000 && ev.code < 4100) && state.reconnects < 30) {  // (a restart or the Wi-Fi)
            state.reconnects++;
            toast(state.expectRestart && Date.now() - state.expectRestart < 60000 ? "The class server is restarting: reconnecting…"
                                                                                : "Lost the class: reconnecting…", false, 4000);
            setTimeout(reconnect, Math.min(5000, 1000 + 500 * state.reconnects));
            return;
        }
        if (state.learnerLink && !left) {  // (a learner: the game ended or turned us away; back to waiting at the desk)
            showLogin();
            showLoginPart("wait");
            $("waittext").textContent = `${text} Waiting for your teacher…`;
            state.learnerLink.wait(state.liveId);
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
        localStorage.setItem("mode", state.codeMode ? "code" : state.mode === "learner" ? "learner" : "teacher");
    } catch (e) { /* private window */ }
}

function reconnect() {
    if (state.ws || state.connected) return;
    if (state.learnerLink && !state.codeMode) {  // (a learner: the desk gives a fresh ticket when the group is still live)
        state.learnerLink.wait(null);
        return;
    }
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
    $("login").style.display = "flex";
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
    hideHud();
    document.body.classList.remove("fightscreen");
    sound.stopAll();
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
            state.draft = m.design ? JSON.parse(JSON.stringify(m.design)) : null;  // (the garage's: the window's draft)
            state.myDefault = m.default || null;  // (Robot Lab: the lesson's starting robot, RESET CODE's)
            state.viewDrafts = {};
            state.codeShown = null;
            state.liveReady = m.live_ready || null;
            state.makersSent = null;  // (the class server hears who made each user mod again: claudeChanged)
            state.prefs = m.prefs || {};
            if (state.prefs.card) state.card = Object.assign({}, state.prefs.card);
            state.name = m.name || state.name;
            if (m.role === "learner" && !LEARNER_TABS.some(([k]) => k === state.tab)) state.tab = "mission";
            state.snaps = [];
            state.offset = state.lastSeq = null;
            classMaxHeard();  // (before the scene is made: it is made at the class maximum)
            const g = startGame(m);
            g.welcome(m);
            state.ctrl = g.controlKind ? new Controller(appApi, keys, g.controlKind) : null;
            sound.setLesson((m.lesson || {}).sound);
            hideLogin();
            hideDesk();
            buildTabs();
            $("where").textContent = `${g.title} · ${state.url.replace(/^wss?:\/\//, "")} · ${m.role}`;
            addEvent(`Logged in to ${g.title} as ${m.name} (${m.role})`);
            send({type: "ping", t: Date.now()});
            send({type: "slot", do: "list"});  // (my saved designs, as the windows ask: CHANGE 83)
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
            classMaxHeard();
            if (state.role === "teacher") claudeChanged(appApi, true);
            if (game) game.message(m);
            updatePills();
            renderPanelSoon();
            renderCode(appApi);  // (the code view may have been switched on or off)
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
            if (m.for) { state.viewing = m; if (state.tab === "learners") renderPanelSoon(); return; }
            // our own: the mission, the cards, my card (a learner's window, or the teacher's own)
            if (JSON.stringify(m) !== state.myMissionsKey) {
                state.myMissionsKey = JSON.stringify(m);
                state.myMissions = m;
                if (["mission", "aicard", "mycard"].includes(state.tab)) renderPanelSoon();
            }
            if (state.lesson && state.lesson.show_missions && state.role === "learner" && !state.shownMissions) {
                state.shownMissions = true;  // (the teacher's Show learners: the Mission tab opens by itself)
                state.tab = "mission";
                $("panel").classList.add("open");
                buildTabs();
                renderPanel();
            }
            return;
        case "slots":
            if (!m.who || m.who === state.name) { state.slots = m.slots || {}; if (state.tab === "garage") renderPanelSoon(); }
            else { state.theirSlots = m; if (state.tab === "learners") renderPanelSoon(); }
            return;
        case "ai_card_result":
            state.cardResult = {ok: m.ok, text: m.ok ? `Sent to your teacher.${(m.tips || []).length ? " Tips: " + m.tips.join(" ") : ""}`
                                                     : (m.problems || []).join(" ") + ((m.tips || []).length ? " " + m.tips.join(" ") : "")};
            if (m.ok && state.card) { state.card.goal = state.card.variables = state.card.test = state.card.predict = ""; keepPrefs({card: state.card}); }
            if (state.tab === "aicard") renderPanel();
            return;
        case "brain_result":
            toast(m.ok ? "Your brain is uploaded." : `Brain not used: ${m.error || ""}`, false, 6000);
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
        case "design_result":  // (the window's: the garage's draft is the built design again, or it says why not)
            designResult(appApi, m);
            state.formSeq = (state.formSeq || 0) + 1;
            if (state.tab === "garage" || state.tab === "learners") renderPanelSoon();
            toast(m.ok ? (m.by_teacher ? `Your teacher changed your ${game ? game.word : "design"}.` : "Built.")
                       : `Not built: ${(m.problems || []).join("; ")}`, false, 5000);
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
        case "restart_client":  // (the teacher's Reopen learners' windows: a page just connects again)
            if (state.role === "learner" && state.ws) { const old = state.ws; old.close(); }
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
    if (now - lastFrame > AutoTier.MISS_MS) state.missedFrames = (state.missedFrames || 0) + 1;
    lastFrame = now;
    state.frames++;
    const covered = $("login").style.display !== "none" || deskShown();  // (nothing to see behind them: don't draw)
    if (now - state.fpsAt > 1000) {
        state.fps = Math.round(state.frames * 1000 / (now - state.fpsAt));
        state.frames = 0;
        state.fpsAt = now;
        renderPerf();
        // Auto (base3d.js's AutoTier, CHANGE 139): one tier down after three seconds under 28 a second, one back up
        // after a stretch with no frames missed, never past the class maximum; kept for next time. A tier tuned by
        // hand part by part is only ever stepped down
        let step = state.autoTier && state.scene ? state.auto.second({fps: state.fps, missed: state.missedFrames || 0,
            tier: drawnTier(), cap: classCap(), active: !!state.game && !covered && !document.hidden, now}) : null;
        state.missedFrames = 0;
        if (state.auto.store.best !== state.bestKept) { state.bestKept = state.auto.store.best; keepGfx(); }  // (a tier run cleanly here)
        if (step && step.up && Object.keys(state.gfx.parts).length) step = null;
        if (step) {
            setTier(step.tier, true);
            toast(step.up ? `Graphics stepped up to ${step.tier} (no frames missed for ${AutoTier.UP_SECS} s)`
                          : `Graphics stepped down to ${step.tier} (the frame rate was ${state.fps})`);
        }
        if (state.connected) {
            send({type: "ping", t: Date.now()});
            send({type: "perf", fps: state.fps, ping: Math.round(state.pingMs), tier: "web-" + drawnTier(), stalls: state.stalls, delay: DELAY_MS,
                  ...(state.ctrl && state.ctrl.ctrlMs !== null ? {ctrl: Math.round(state.ctrl.ctrlMs)} : {})});
            if (state.prefsDirty && now - (state.prefsAt || 0) > 3000) { state.prefsDirty = false; state.prefsAt = now; send({type: "prefs", prefs: state.prefs}); }
        }
    }
    if (state.ctrl && state.connected && !covered) state.ctrl.tick(now);
    if (state.game && !covered) {
        state.game.frame(now, dt);
        state.game.scene.render();
    }
    requestAnimationFrame(loop);
}

// ---------- the graphics (CHANGE 131, 139) ----------
// state.tier is this computer's choice (kept as "tier"), the one Auto moves; a learner's page draws it at most at
// the teacher's class maximum (the lesson's gfx_max: the windows' names, "basic" for blocks), and goes back to the
// choice when the maximum is lifted. state.gfx (kept as "gfx"): auto, the parts changed by hand, the canvas's
// multisampling (aa: read as the page opens), the frame rate box (fps) and Auto's memory (best, failed)
function loadGfx() {
    let kept = {};
    try { kept = JSON.parse(localStorage.getItem("gfx") || "{}") || {}; } catch (e) { /* storage blocked */ }
    state.gfx = {auto: kept.auto !== false, parts: cleanParts(kept.parts),
                 aa: kept.aa !== false, fps: kept.fps !== false};
    state.autoTier = params.get("auto") === "0" ? false : state.gfx.auto;
    state.auto = new AutoTier(kept.autoStore || {});
}

function keepGfx() {
    state.gfx.auto = state.autoTier;
    try { localStorage.setItem("gfx", JSON.stringify({...state.gfx, autoStore: state.auto.store})); } catch (e) { /* storage blocked */ }
}

function classCap() {  // the teacher's class maximum, on a learner's page (the teacher's own page isn't held to it)
    const v = state.lesson && state.lesson.gfx_max, t = v === "basic" ? "blocks" : v;
    return state.role === "learner" && TIERS.includes(t) ? t : null;
}

function drawnTier() {
    return cappedTier(state.tier, classCap());
}

// the scene drawn as chosen: the tier at most at the class maximum, the parts changed by hand (again: rebuilt
// though the tier is the same)
function applyGraphics(again = false) {
    setGraphics(state.gfx.parts, classCap());
    if (state.scene) state.scene.setTier(drawnTier(), again);
    $("perf").style.display = state.gfx.fps ? "" : "none";
    if (state.tab === "graphics") renderPanel();
    renderPerf();
}

// a tier picked (by hand: Auto goes off, as the windows' Graphics: Low; by Auto: auto true). Its parts are the
// tier's own again. A learner can't pick past the class maximum
function setTier(tier, auto = false) {
    if (!TIERS.includes(tier)) return;
    if (!auto) state.autoTier = false;
    state.tier = cappedTier(tier, classCap());
    state.gfx.parts = {};
    try { localStorage.setItem("tier", state.tier); } catch (e) { /* storage blocked: chosen again next time */ }
    keepGfx();
    applyGraphics(true);
}

function setPart(part, value) {
    if (value === null) delete state.gfx.parts[part];
    else state.gfx.parts[part] = value;
    keepGfx();
    applyGraphics(true);
}

// the lesson came: a class maximum new to this page is put in force at once (the scene comes down to it, or
// back up to the choice when it is lifted)
function classMaxHeard() {
    const cap = classCap();
    if (cap === state.capSeen) return;
    const was = state.capSeen;
    state.capSeen = cap;
    if (was === undefined && !state.scene) { setGraphics(state.gfx.parts, cap); return; }  // (the first: before the scene)
    applyGraphics(true);
    if (cap && TIERS.indexOf(state.tier) > TIERS.indexOf(cap)) toast(`Your teacher set the graphics to at most ${cap}.`, false, 6000);
    else if (!cap && was) toast(`Your teacher lifted the graphics limit: ${state.tier} again.`, false, 5000);
}

// the Graphics (a learner's Settings) tab's top: Auto and the tiers, every part of a tier, and for the teacher the
// class maximum (sent in the lesson: every learner's page and window is held to it)
const PART_ROWS = [  // [part, label, choices, what the tier part needs]
    ["shadow", "Shadows", PARTS.shadow, "pbr"], ["normal", "Surface detail (normal maps)", [false, true], "pbr"],
    ["occlusion", "Occlusion maps", [false, true], "pbr"], ["ibl", "The sky's reflections", [false, true], "pbr"],
    ["aniso", "Textures at a slant (anisotropic filtering)", PARTS.aniso, "pbr"], ["pixels", "Pixels drawn", PARTS.pixels, ""]];
const partText = (part, v) => v === true ? "on" : v === false ? "off" : part === "shadow" ? (v ? String(v) : "off")
    : part === "aniso" ? `${v}x` : v >= SCREEN ? "as the screen" : `${(v / 1e6).toFixed(1)} million`;

function graphicsHtml() {
    const cap = classCap(), drawn = drawnTier(), now = tierSettings(drawn), top = cap ? TIER_SETTINGS[cap] : null;
    const tuned = Object.keys(state.gfx.parts).length, aa = !!(engine && engine._gl && engine._gl.getContextAttributes().antialias);
    const over = (part, v) => top && (typeof v === "boolean" ? v && !top[part] : v > top[part]);
    let html = `<h2>Graphics</h2>
      <div class="row"><button id="btn-auto" class="${state.autoTier ? "on" : ""}">Auto</button>${TIERS.map(t =>
        `<button data-tier="${t}" class="${drawn === t ? "on" : ""}"${cap && TIERS.indexOf(t) > TIERS.indexOf(cap) ? " disabled" : ""}>${t}</button>`).join("")}</div>
      <div class="note">Drawing ${drawn}${state.autoTier ? " (Auto: down a tier after three seconds under 28 frames a second, back up after " +
        `${AutoTier.UP_SECS} seconds with no frames missed)` : ""}${tuned ? ", with parts changed below" : ""}.
        ${cap ? `Your teacher's class maximum is <b>${cap}</b>: nothing above it can be chosen.` : ""}
        blocks: flat colours, nothing lit, the floor every machine draws. low: the app's lighting and textures, no shadows or
        reflections. medium: surface detail, the sky's reflections, shadows. high: sharper shadows and textures, and the most
        pixels. A tier picked here turns Auto off; picking a tier sets every part below to that tier's. Kept on this computer.</div>
      <h2>The parts</h2><table>`;
    for (const [part, label, choices, needs] of PART_ROWS) {
        const off = needs && !now[needs];  // (blocks: nothing lit, so no shadows, maps or reflections)
        html += `<tr><th>${esc(label)}</th><td>${choices.map(v => `<button data-part="${part}" data-val="${v}" class="${now[part] === v ? "on" : ""}"${off || over(part, v) ? " disabled" : ""}>${partText(part, v)}</button>`).join("")}</td></tr>`;
    }
    html += `<tr><th>Smooth edges (multisampling)</th><td><button data-aa="1" class="${state.gfx.aa ? "on" : ""}">on</button><button data-aa="0" class="${state.gfx.aa ? "" : "on"}">off</button>
        ${state.gfx.aa !== aa ? `<span class="note">from the next time the page opens</span>` : ""}</td></tr>
      <tr><th>Frame rate box</th><td><button data-fpsbox="1" class="${state.gfx.fps ? "on" : ""}">shown</button><button data-fpsbox="0" class="${state.gfx.fps ? "" : "on"}">hidden</button></td></tr></table>
      ${tuned ? `<div class="row"><button id="btn-parts-reset">Back to ${drawn}'s own</button></div>` : ""}
      <div class="note">${drawn === "blocks" ? "On blocks nothing is lit, so only the pixels count. " : ""}Each tier draws at most so many pixels
        however fine the screen (blocks 1.0 million, low 1.1, medium 1.6, high 2.4); more is sharper and slower.</div>`;
    if (state.role !== "learner") {
        const mx = (state.lesson || {}).gfx_max, mine = mx === "basic" ? "blocks" : mx;
        html += `<h2>Class maximum</h2><div class="row">${TIERS.map(t => `<button data-gfxmax="${t}" class="${mine === t ? "on" : ""}">${t}</button>`).join("")}
            <button data-gfxmax="" class="${TIERS.includes(mine) ? "" : "on"}">no limit</button></div>
          <div class="note">The best graphics the class may choose. Learners' pages can't choose above it, Auto never steps past it,
            and a page above it drops to it at once. The game windows open at most at it (one already open turns its shadows
            and smoothing down now, the rest at its next start). Your own view isn't held to it. Kept for the next lesson.</div>`;
    }
    return html;
}

function wireGraphics(body) {
    $("btn-auto").onclick = () => { state.autoTier = !state.autoTier; state.auto.slow = state.auto.good = 0; keepGfx(); renderPanel(); renderPerf(); };
    body.querySelectorAll("button[data-tier]").forEach(b => b.onclick = () => setTier(b.dataset.tier));
    body.querySelectorAll("button[data-part]").forEach(b => b.onclick = () => {
        const v = b.dataset.val, value = v === "true" ? true : v === "false" ? false : Number(v);
        setPart(b.dataset.part, TIER_SETTINGS[drawnTier()][b.dataset.part] === value ? null : value);  // (the tier's own: not a change)
    });
    body.querySelectorAll("button[data-aa]").forEach(b => b.onclick = () => { state.gfx.aa = b.dataset.aa === "1"; keepGfx(); renderPanel(); });
    body.querySelectorAll("button[data-fpsbox]").forEach(b => b.onclick = () => { state.gfx.fps = b.dataset.fpsbox === "1"; keepGfx(); applyGraphics(); });
    if ($("btn-parts-reset")) $("btn-parts-reset").onclick = () => { state.gfx.parts = {}; keepGfx(); applyGraphics(true); };
    body.querySelectorAll("button[data-gfxmax]").forEach(b => b.onclick = () => {
        const t = b.dataset.gfxmax;
        send({type: "lesson", lesson: {gfx_max: t === "blocks" ? "basic" : t || null}});
        toast(t ? `Class maximum: ${t}` : "No class maximum");
    });
}

function renderPerf() {
    const info = engineInfo(engine);
    $("perf").innerHTML = `${state.fps} fps · ping ${Math.round(state.pingMs)} ms · stalls ${state.stalls} · missed ${state.missed}<br>` +
        `${drawnTier()}${state.autoTier ? " (auto)" : ""} · ${info.width} x ${info.height} · WebGL${info.webgl || "?"}${info.webgpu ? " · WebGPU available" : ""} · ${esc(String(info.renderer || "").slice(0, 60))}`;
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
    if (state.role === "learner") {  // (the learner window's tabs, then the page's own)
        const own = g && g.learnerTabs ? g.learnerTabs() : [["camera", "Camera"]];
        return [...LEARNER_TABS, ...own, ["graphics", "Settings"], ["about", "Keys"]];
    }
    const gameTabs = g ? g.tabs() : [];
    return [gameTabs[0] || ["controls", "Controls"], ...TEACHER_TABS, ...gameTabs.slice(1), ["mission", "My mission"],
            ["graphics", "Graphics"], ["about", "About"]];
}

function buildTabs() {
    const tabs = allTabs();
    if (!tabs.some(([k]) => k === state.tab)) state.tab = tabs[0][0];
    $("panelhead").innerHTML = tabs.map(([k, n]) => `<button data-tab="${k}" class="${k === state.tab ? "on" : ""}">${n}</button>`).join("");
    $("panelhead").querySelectorAll("button").forEach(b => b.onclick = () => {
        state.tab = b.dataset.tab;
        $("panelhead").querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
        updateTabCounts();
        renderPanel();
    });
    updateTabCounts();
}

function updateTabCounts() {
    const b = $("panelhead").querySelector('button[data-tab="warnings"]');
    // (the window counts the warnings not yet seen: opening the tab sees them)
    const n = (state.warnings || []).length;
    if (state.tab === "warnings") state.warnSeen = n;
    const unseen = Math.max(0, n - (state.warnSeen || 0));
    if (b) b.textContent = unseen ? `Warnings (${unseen})` : "Warnings";
}

let panelTimer = null;
function renderPanelSoon() {  // (several messages in a burst: draw the panel once)
    if (panelTimer) return;
    panelTimer = setTimeout(() => { panelTimer = null; renderPanel(); }, 120);
}

// typed text survives the redraws (the lesson and the teaching data arrive every second); a different page of
// the panel (another tab, learner or mission) starts clean
function renderPanel() {
    if (state.dragging) { renderPanelSoon(); return; }  // (a garage slider is held: draw when it's let go)
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
    if (state.role === "learner" && renderLearnerTab(appApi, state.tab, body)) return;
    if (state.role !== "learner" && state.tab === "mission" && renderLearnerTab(appApi, "mission", body)) return;
    if (g.renderTab(state.tab, body)) return;
    if (state.role !== "learner" && renderTeacherTab(appApi, state.tab, body)) return;
    if (state.tab === "graphics") {
        const sc = state.scene, info = engineInfo(engine);
        body.innerHTML = graphicsHtml() + `
          <h2>This browser</h2>
          <table><tr><th>WebGL</th><td>${info.webgl}</td></tr><tr><th>WebGPU</th><td>${info.webgpu ? "available (not used yet)" : "no"}</td></tr>
            <tr><th>Renderer</th><td>${esc(info.renderer)}</td></tr><tr><th>Screen</th><td>${window.innerWidth} x ${window.innerHeight} at ${devicePixelRatio}x</td></tr>
            <tr><th>Drawing</th><td>${info.width} x ${info.height} pixels (${info.ratio.toFixed(2)} per screen point)${sc ? `, ${sc.drawCalls()} meshes` : ""}</td></tr>
            <tr><th>Frame rate</th><td>${state.fps} fps, ${state.stalls} stalls, ${state.missed} missed snapshots</td></tr></table>
          <div class="note">These numbers from a school laptop and a Chromebook are the measurement nobody has published: note them down.</div>`;
        wireGraphics(body);
        // the window's own Settings: the text size and the look (kept on this computer)
        body.insertAdjacentHTML("beforeend", `<h2>Text and look</h2><div class="row">Text size ${[1, 2, 3, 4].map(k =>
            `<button data-tsize="${k}" class="${(state.textSize || 2) === k ? "on" : ""}">${["Small", "Normal", "Large", "Larger"][k - 1]}</button>`).join("")}</div>
          <div class="row">Look <button data-look="dark" class="${state.look !== "light" ? "on" : ""}">Dark</button><button data-look="light" class="${state.look === "light" ? "on" : ""}">Light</button></div>`);
        body.querySelectorAll("button[data-tsize]").forEach(b => b.onclick = () => { setLook({textSize: Number(b.dataset.tsize)}); renderPanel(); });
        body.querySelectorAll("button[data-look]").forEach(b => b.onclick = () => { setLook({look: b.dataset.look}); renderPanel(); });
        // the sound (the windows' Settings rows: each sound with its switch and volume; N mutes)
        const gid = g.id, S2 = sound.settings, rows = SETTINGS_ROWS[gid] || [];
        let snd = `<h2>Sound</h2><div class="row"><button id="snd-mute" class="${sound.muted ? "" : "on"}">${sound.muted ? "Sound is off (N)" : "Sound is on (N)"}</button></div>`;
        if (HAS_MUSIC[gid]) snd += `<div class="row">Music ${Object.entries(MUSIC).map(([k, n]) => `<button data-music="${k}" class="${S2.music === k ? "on" : ""}">${n}</button>`).join("")}
            <input type="range" min="0" max="1" step="0.1" value="${S2.music_volume}" data-vol="music_volume"></div>`;
        for (const [on, label, vol] of rows) {
            snd += `<div class="row"><label><input type="checkbox" data-snd="${on}" ${S2[on] ? "checked" : ""}> ${esc(label)}</label>
              <input type="range" min="0" max="1" step="0.1" value="${S2[vol]}" data-vol="${vol}"></div>`;
        }
        body.insertAdjacentHTML("beforeend", snd);
        $("snd-mute").onclick = () => { sound.unlock(); sound.toggleMute(); renderPanel(); };
        body.querySelectorAll("button[data-music]").forEach(b => b.onclick = () => { sound.unlock(); sound.set({music: b.dataset.music}); renderPanel(); });
        body.querySelectorAll("input[data-snd]").forEach(el => el.onchange = () => sound.set({[el.dataset.snd]: el.checked}));
        body.querySelectorAll("input[data-vol]").forEach(el => el.onchange = () => sound.set({[el.dataset.vol]: Number(el.value)}));
        return;
    }
    if (state.role === "learner") {  // (the learner's key list, as the windows show it)
        const KEYS = {
            robotlab: [["Arrows", "drive"], ["Space", "weapon"], ["V", "camera"], ["B", "the health bars: small or full"], ["P", "autopilot"], ["U", "upload a brain"]],
            fightlab: [["Arrows", "move"], ["A", "punch (again for a combo)"], ["S", "kick (forward + S: high kick)"], ["D", "special"],
                       ["W", "throw"], ["Space", "jump"], ["F", "cartwheel (when it's on)"], ["Shift", "block"], ["X", "crouch (X + Shift: low block)"],
                       ["V", "camera"], ["P", "autopilot"], ["U", "upload a brain"]],
            kartlab: [["Arrows or WASD", "drive"], ["Shift or Space", "drift"], ["R", "respawn"], ["V", "camera"], ["P", "autopilot"], ["U", "upload a brain"]],
        }[g.id] || [];
        body.innerHTML = `<h2>Keys</h2><table>${[...KEYS, ["I or Tab", "this panel"], ["C", "your code"]].map(([k, w]) =>
            `<tr><td><b>${esc(k)}</b></td><td>${esc(w)}</td></tr>`).join("")}</table>
          <p class="note">Click the game first so the keys go to it. While you type in the panel, the keys type instead.</p>`;
        return;
    }
    body.innerHTML = `
      <h2>About</h2>
      <p class="note">Club Coders Live ${esc(state.version || "")}: the teacher's desk and live view of a class in the browser. It
        joins the class server as the teacher window does, draws the game from the same 30-a-second snapshots, two behind so
        the picture is smooth, and sends the same commands. Kart Lab, Robot Lab and Fight Lab are drawn.</p>
      <p class="note">The TEACHER DESK button (top left) is the app's Teacher screen: learners, groups, Launch and Stop, this
        session's notes and the printed records.</p>
      <p class="note">Sending AI cards to Claude (Send, Keep, Undo) and the Changes tab need Claude for the browser running on a
        computer of yours with Claude Code (it uses that computer's own Claude login). Still only in the app: Try it on this laptop.</p>
      <p class="note">Keys: <b>Tab</b> opens and closes this panel.${g.id === "robotlab" ? " <b>B</b> makes the health bars small or full." : ""}</p>`;
}

// what the games and teacher.js reach the page through
const appApi = {
    get state() { return state; }, get game() { return state.game; }, get tier() { return drawnTier(); }, setTier: t => setTier(t),
    get canvas() { return $("view"); }, get engine() { return engine; }, params,
    send, toast, addEvent, renderPanel, updatePills, pushSnap, samplePair, esc,
    missionRow: () => missionRow(appApi), wireMissionRow: body => wireMissionRow(appApi, body),
    restartRow: () => restartRow(appApi), wireRestartRow: body => wireRestartRow(appApi, body),
    twice: (key, text, then) => twice(appApi, key, text, then), keepPrefs: p => keepPrefs(p),
    sendBinary: buf => { if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(buf); },
    get keys() { return keys; }, get ctrl() { return state.ctrl; }, get role() { return state.role; }, get sound() { return sound; },
    openCode: () => toggleCode(appApi),
};

// the window's text size (four) and dark or light look: on this computer, and in a learner's profile as the windows keep them
function setLook(change = {}) {
    Object.assign(state, change);
    for (const k of [1, 2, 3, 4]) document.body.classList.toggle("text-" + k, (state.textSize || 2) === k && k !== 2);
    document.body.classList.toggle("light", state.look === "light");
    try { localStorage.setItem("look", JSON.stringify({textSize: state.textSize || 2, look: state.look || "dark"})); } catch (e) { /* private window */ }
    if (Object.keys(change).length && state.role === "learner") keepPrefs({hud: {text_size: state.textSize || 2, light: state.look === "light"}});
}
try { const saved = JSON.parse(localStorage.getItem("look") || "{}"); state.textSize = saved.textSize; state.look = saved.look; } catch (e) { /* none */ }
setLook();

// a learner's preferences (the camera, the half-typed AI card...) kept in their profile, as the windows do
function keepPrefs(p) {
    state.prefs = Object.assign({}, state.prefs || {}, p);
    state.prefsDirty = true;
}

// the games' sounds (sound.js): nothing plays until the first click or key, as browsers insist
const sound = new Sound({base: "sfx/"});

// the keyboard: playing (play.js), and the windows' keys for the panel and the rest
const keys = new Keys();
keys.onKey = (k, e) => {
    if (!state.connected || deskShown()) return;
    if (k === "i") { $("panel").classList.toggle("open"); if ($("panel").classList.contains("open")) renderPanel(); }
    else if (k === "c" && state.game) toggleCode(appApi);
    else if (k === "p" && state.role === "learner") send({type: "autopilot"});
    else if (k === "u" && state.role === "learner") pickBrain();
    else if (k === "v" && state.game && state.game.cycleCamera) { state.game.cycleCamera(); updatePills(); }
    else if (k === "b" && state.game && state.game.toggleBoard) state.game.toggleBoard();  // (Robot Lab's health bars)
    else if (k === "n") { sound.toggleMute(); toast(sound.muted ? "Sound off (N)" : "Sound on (N)"); if (state.tab === "graphics") renderPanel(); }
};

function pickBrain() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".py,.txt";
    input.onchange = () => uploadBrain(appApi, input.files[0]);
    input.click();
}

// ---------- start ----------
function setupUi() {
    $("class").onchange = () => {
        const other = $("class").value === "other";
        $("host").hidden = $("hostlabel").hidden = !other;
    };
    $("connect").onclick = () => login();
    $("modetabs").querySelectorAll("button").forEach(b => b.onclick = () => { setMode(b.dataset.mode); try { localStorage.setItem("mode", b.dataset.mode); } catch (e) { /* private */ } });
    for (const id of ["lname", "lpass", "npass", "npass2"]) $(id).onkeydown = e => { if (e.key === "Enter") login(); };
    $("code").onkeydown = e => { if (e.key === "Enter") connect(); };
    $("deskpass").onkeydown = e => { if (e.key === "Enter") deskLogin(); };
    $("lobby-logout").onclick = () => {  // (a learner leaves the lobby: logged out at the desk)
        if (state.learnerLink) state.learnerLink.close();
        state.learnerLink = null;
        showLoginPart("form");
        setStatus("Logged out.", true);
    };
    $("toggle").onclick = () => { $("panel").classList.toggle("open"); if ($("panel").classList.contains("open")) renderPanel(); };
    $("btn-desk").onclick = () => showDesk();
    window.addEventListener("pointerup", () => { state.dragging = false; });
    window.addEventListener("pointercancel", () => { state.dragging = false; });
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
    try { mode = localStorage.getItem("mode"); if (localStorage.getItem("lname")) $("lname").value = localStorage.getItem("lname"); } catch (e) { /* storage blocked */ }
    // learner or teacher: ?mode=, else as last time on this computer ("desk" was the teacher's before CHANGE 134), else a learner
    state.mode = params.get("mode") || (mode === "desk" || mode === "teacher" ? "teacher" : "learner");
    $("modetabs").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.mode === state.mode));
    setCodeMode(!!(params.get("host") || params.get("code")));  // (no class codes on the page: CHANGE 141)
    if (params.get("name")) $("name").value = params.get("name");
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
    loadGfx();  // (CHANGE 139: Auto, the parts changed by hand, the multisampling, the frame rate box)
    if (TIERS.includes(params.get("tier"))) state.gfx.parts = {};  // (a tier in the address: its own parts)
    setGraphics(state.gfx.parts, null);
    try {
        engine = state.engine = pageEngine($("view"), state.gfx.aa);
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
    try {  // the games' design schemas: the garage's tables and the code panel (schemas.json, made by make_schemas.py)
        const r = await fetch("schemas.json");
        if (r.ok) state.schemas = await r.json();
    } catch (e) { /* no garage or code panel until it loads */ }
    setupCodePanel(appApi);
    try {  // (the lessons' names, for the printed records)
        const r = await fetch("lessons.json");
        if (r.ok) state.lessons = await r.json();
    } catch (e) { /* the records print the codes instead */ }
    const v = await pageVersion();
    $("pageversion").textContent = v || "(laptop test)";
    renderPerf();
    $("perf").style.display = state.gfx.fps ? "" : "none";
    requestAnimationFrame(loop);
    if (params.get("autoconnect")) login();
}

main();
