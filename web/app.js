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
// ?code=TEACH99 to prefill the code, ?tier=mesh|lines|blocks|low|medium|high|ultra, ?version=1.9.1 (a class server wants the release's
// number; on the VPS the page reads it from /live/version).

import {TIERS, GAME_TIERS, LINE_TIERS, TIER_SETTINGS, PARTS, SCREEN, AutoTier, pageEngine, engineInfo, setSkyData, setGraphics,
        cappedTier, tierSettings, cleanParts, gameTier, LINE_COLOURS, getLineColour, setLineColour, cleanColour} from "./base3d.js";
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
import {makeDraggable} from "./drag.js";
import {Snapshots} from "./interp.js";  // (CHANGE 175: the window's blending, delay following the network)
import {openBrainEditor, closeBrainEditor, brainEditorChanged, uploadMyBrain, brainsOn} from "./brain.js";

const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const CLOSE_TEXT = {4001: "Wrong teacher code.", 4002: "A teacher window is already open on this class: close it first.",
                    4006: "This page is out of date for that server.", 4008: "Too many wrong tries: wait a minute.",
                    4011: "The ticket ran out: log in again.", 4010: "That group hasn't started.", 4009: "The session has ended."};
let engine = null;
// (CHANGE 161) the renderer names of drawing done without the graphics card (Chrome's SwiftShader, Mesa's llvmpipe,
// Windows' basic display driver)
export const SOFTWARE_GL = /SwiftShader|llvmpipe|softpipe|Software|Microsoft Basic Render/i;

const state = {
    ws: null, connected: false, role: null, name: "", game: null,
    version: params.get("version") || "",
    lesson: null, rules: null, roster: null, race: null, classList: [], tournament: null, teaching: null,
    snaps: [], interp: new Snapshots(), offset: null, lastSeq: null, missed: 0, stalls: 0, pingMs: 0, pings: [], rttS: null, lastPong: 0, reconnects: 0,
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
    const password = $("lpass").value;
    if (!password) return setStatus("The teacher password is needed.");
    setStatus("Logging in to the desk…", true);
    if (state.desk) state.desk.close();
    state.deskUi = {tab: null, editing: null, confirm: null, message: null};
    state.desk = new DeskLink(deskUrl(), password, {
        ready: first => {
            if (first) {
                $("lpass").value = "";
                try { if (window.PasswordCredential) navigator.credentials.store(new PasswordCredential({id: "teacher", password})); } catch (e) { /* not offered */ }
                try { localStorage.setItem("lname", "teacher"); } catch (e) { /* private window */ }
                setStatus("");
                if (state.desk.ownPassword === false) {  // (still the server setup's teacher code: CHANGE 148)
                    state.deskUi.tab = "password";
                    state.deskUi.message = {text: "You logged in with the server's setup code: choose your own teacher password now.", ok: true};
                }
                showDesk();
                if (params.get("game")) watch(params.get("game"));
            }
            updateDeskButton();
        },
        changed: () => { if (deskShown()) drawDesk(); updateDeskButton(); },
        claude: () => claudeChanged(appApi),  // (Claude for the browser said something: CHANGE 136)
        message: (text, ok) => { state.deskUi.message = {text, ok}; if (deskShown()) drawDesk(); else if (!ok) toast(text); },
        closed: (text, tryLearner) => {
            state.desk = null;
            updateDeskButton();
            hideDesk();
            dropView();
            showLogin();
            if (tryLearner) return learnerLogin(text);  // (a learner called Teacher from before CHANGE 148: CHANGE 154)
            setStatus(text);
        },
    });
}

// A learner's login (CHANGE 134): the desk checks the username and password (a starter one is changed first), then
// says to wait or gives the game's address and a ticket; the page opens the game, and goes back to waiting after it.
// teacherError: the teacher password was refused and the desk has a learner called Teacher (CHANGE 154): if they
// aren't let in either, the teacher's refusal is what shows.
function learnerLogin(teacherError) {
    const name = $("lname").value.trim(), password = $("lpass").value;
    if (!name || !password) return setStatus("Your username and password are needed.");
    setStatus("Logging in…", true);
    if (state.learnerLink) state.learnerLink.close();
    let inside = false;
    const link = state.learnerLink = new LearnerLink(deskUrl(), name, password, {
        changePassword: () => {
            inside = true;
            showLoginPart("newpass");
            setStatus("Choose your own password to go on.", true);
        },
        waiting: text => {
            inside = true;
            try { localStorage.setItem("lname", link.name); } catch (e) { /* private window */ }
            $("lpass").value = "";
            if (state.ws && state.connected) return;  // (already playing: the desk's word is for later)
            showLogin();
            showLoginPart("wait");
            $("waittext").textContent = `Hello ${link.name}. ${text}`;
            setStatus("");
        },
        go: go => {
            inside = true;
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
            setStatus(teacherError && !inside ? teacherError : text);
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

// which part of the login card shows: the username and password, a learner's new password, or waiting (the laptop
// test servers' class code form only with ?host= or ?code=)
function showLoginPart(part) {
    $("loginform").hidden = !(!state.codeMode && part === "form");
    $("newpassform").hidden = part !== "newpass";
    $("waitbox").hidden = part !== "wait";
    $("codeform").hidden = !(state.codeMode && part === "form");
    $("connect").hidden = part === "wait";
    $("connect").textContent = part === "newpass" ? "SAVE MY PASSWORD" : "LOG IN";
    $("loginnote").hidden = part !== "form";
    state.loginPart = part;
}

// (CHANGE 148) the one login form: the username teacher is the teacher (the desk lets no learner have it)
function isTeacher() { return $("lname").value.trim().toLowerCase() === "teacher"; }

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
    return isTeacher() ? deskLogin() : learnerLogin();
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
    state.interp = new Snapshots();
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
        renderKeyHelp();  // (CHANGE 143: the key list goes with the class)
        if (!left && was && !(ev.code >= 4000 && ev.code < 4100) && state.reconnects < 30) {  // (a restart or the Wi-Fi)
            state.reconnects++;
            const restarting = ev.code === 1012 || (state.expectRestart && Date.now() - state.expectRestart < 60000);
            toast(restarting ? "The class server is restarting: reconnecting…" : "Lost the class: reconnecting…", false, 4000);
            // (1012: the server closed every window to restart. Not the whole class at the same moment: CHANGE 160)
            setTimeout(reconnect, Math.min(5000, 1000 + 500 * state.reconnects) + Math.random() * 1500);
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
            const again = state.reconnects > 0;  // (a reconnect to the same class: CHANGE 143's Show learners)
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
            state.interp = new Snapshots();
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
            // (CHANGE 143) the learner's own settings from their profile (the windows' keys), the Show learners tick as
            // it stands, the windows' banners, Back to the lobby, the key list and the brain editor for this game
            if (m.role === "learner") restoreProfileSettings(state.prefs);
            else setLook();  // (the teacher's are this computer's: put where the game files read them)
            showMissionsChanged(again ? state.showMissionsSeen : false, (m.lesson || {}).show_missions);
            if (m.new_profile) toast(`Welcome, ${m.name || state.name}! Your profile is made: next time log in with the same username and password.`, false, 7000);
            else if (m.role !== "learner" && g.id === "kartlab") toast("Teacher: Enter starts the race, G puts everyone on the grid, T changes the track", false, 8000);
            $("btn-lobby").hidden = !(state.learnerLink && m.role === "learner");
            $("btn-lobby").textContent = "BACK TO THE LOBBY";
            renderKeyHelp();
            brainEditorChanged(appApi);
            updatePills();
            renderPanel();
            return;
        }
        case "lesson":
            state.lesson = m.lesson || state.lesson;
            showMissionsChanged(state.showMissionsSeen, (state.lesson || {}).show_missions);
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
            return;  // (the teacher's Show learners opens the Mission tab: showMissionsChanged, CHANGE 143)
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
            if (m.t) {
                state.pingMs = Date.now() - m.t;
                // (CHANGE 175) the round trip drawing ahead uses: the quickest of the last six, rising by at most
                // 10 ms a second, so one slow sample doesn't move every robot drawn ahead and back a second later
                state.pings.push(state.pingMs);
                if (state.pings.length > 6) state.pings.shift();
                const target = Math.min(...state.pings) / 1000;
                state.rttS = state.rttS === null || target < state.rttS ? target : Math.min(target, state.rttS + 0.01);
            }
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

// the snapshots every game blends between, kept with the server's clock (sm): interp.js (CHANGE 175), the
// window's engine/interp.py line for line, its delay following the network instead of a fixed 80 ms
function pushSnap(snap, now) {
    snap.at = now;
    if (snap.seq !== undefined) {
        if (state.lastSeq !== null) {
            const gap = (snap.seq - state.lastSeq) & 0xFFFF;
            if (gap > 1 && gap < 1000) state.missed += gap - 1;
        }
        state.lastSeq = snap.seq;
    }
    state.interp.push(snap, now);
    // (the clock offset between the server's ms and ours, as the games drawing ahead read it: now - offset is the
    // server's time now)
    const st = state.interp.serverTime(now);
    state.offset = st === null ? null : now - st;
    state.snaps.push(snap);  // (the newest for the places table)
    if (state.snaps.length > 90) state.snaps.shift();
}

// (CHANGE 159) the server's time (ms) the picture is drawn at: what samplePair blends to (null before a snapshot)
function renderTime(now) {
    return state.interp.renderTime(now);
}

// {a, b, f, extrapolating}: the two snapshots around the moment to draw and how far between them (b null with only
// one; f over 1 while carrying on past the newest for up to 100 ms)
function samplePair(now) {
    return state.interp.pair(now);
}

// ---------- drawing ----------
// (CHANGE 161) the screen's refresh: the browser calls loop() at the screen's rate, 120 a second and more on some
// laptops. There a frame is drawn every `every` refreshes, about 60 a second (half the work and the heat), and Auto
// judges by the screen: a missed frame is one later than the drawing interval and half a refresh (25 ms at 60 Hz, as
// AutoTier.MISS_MS; 21 ms drawing every other refresh at 120 Hz, where every frame sat under 25 ms however slow)
const refresh = {gaps: [], at: 0, ms: 1000 / 60, every: 1, last: performance.now()};
function measureRefresh(now) {
    const gap = now - refresh.last;
    refresh.last = now;
    if (gap > 2 && gap < 60) { refresh.gaps.push(gap); if (refresh.gaps.length > 120) refresh.gaps.shift(); }
    if (now - refresh.at > 1000 && refresh.gaps.length >= 30) {  // (the quickest tenth: the screen's own interval)
        refresh.at = now;
        const sorted = refresh.gaps.slice().sort((a, b) => a - b);
        refresh.ms = sorted[Math.floor(sorted.length * 0.1)];
        refresh.every = Math.max(1, Math.floor(1000 / 60 / refresh.ms + 0.25));
    }
}

let lastFrame = performance.now();
function loop() {
    const now = performance.now();
    measureRefresh(now);
    if (now - lastFrame < (refresh.every - 0.5) * refresh.ms) {  // (a fast screen: not this refresh)
        requestAnimationFrame(loop);
        return;
    }
    const dt = Math.min(0.1, (now - lastFrame) / 1000);
    if (now - lastFrame > 100) state.stalls++;
    if (now - lastFrame > (refresh.every + 0.5) * refresh.ms) state.missedFrames = (state.missedFrames || 0) + 1;
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
        // (CHANGE 144) the tier the game draws, but mesh and lines as chosen, so Auto leaves them alone even where a
        // game draws blocks for them; never past the game's best tier
        const tiers = gameTiers(), chosen = chosenTier();
        let step = state.autoTier && state.scene ? state.auto.second({fps: state.fps, missed: state.missedFrames || 0,
            tier: LINE_TIERS.includes(chosen) ? chosen : drawnTier(), cap: classCap(), top: tiers[tiers.length - 1],
            active: !!state.game && !covered && !document.hidden, now}) : null;
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
            // (CHANGE 143) as the windows send it: the key delay (ctrl, null until measured: the teacher's table shows
            // it as "key delay") and Kart Lab's prediction corrections (corr)
            const pred = state.game && state.game.predictor;
            const rep = state.interp.report();  // (CHANGE 175: the network's stalls and the delay, as the windows report them)
            send({type: "perf", fps: state.fps, ping: Math.round(state.pingMs), tier: "web-" + drawnTier() + (state.softwareGl ? " NO GPU" : ""),
                  stalls: rep.stalls, delay: rep.delay_ms, underruns: rep.underruns, hitches: state.stalls,
                  ctrl: state.ctrl && state.ctrl.ctrlMs !== null ? Math.round(state.ctrl.ctrlMs) : null,
                  ...(state.game && state.game.id === "kartlab" ? {corr: pred ? pred.corrections : null} : {})});
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
                 aa: kept.aa !== false, fps: kept.fps !== false,
                 ahead: params.get("ahead") === "0" ? false : kept.ahead !== false};  // (CHANGE 166: Movement)
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

// (CHANGE 144) the tiers the game in front draws (Kart Lab and Robot Lab all seven, CHANGE 145; Fight Lab blocks to
// high); the page's choice under the class maximum (kept page-wide: "lines" stays chosen in Fight Lab); and the tier
// the game draws for it (its nearest: lines as blocks there)
function gameTiers() {
    return (state.scene && state.scene.constructor.TIERS) || GAME_TIERS;
}

function chosenTier() {
    return cappedTier(state.tier, classCap());
}

function drawnTier() {
    return gameTier(chosenTier(), gameTiers());
}

// the scene drawn as chosen: the tier at most at the class maximum, the parts changed by hand (again: rebuilt
// though the tier is the same)
function applyGraphics(again = false) {
    setGraphics(state.gfx.parts, classCap());
    if (state.scene) state.scene.setTier(chosenTier(), again);
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

// (CHANGE 144) the line tiers' colour: recoloured at once, kept on this computer, and in a learner's profile as
// line_colour ("#rrggbb", the window's key); keep false when it came from their profile
function chooseLineColour(c, keep = true) {
    const colour = cleanColour(c);
    if (!colour) return;
    setLineColour(colour, state.scene);
    try { localStorage.setItem("line_colour", colour); } catch (e) { /* storage blocked */ }
    if (keep && state.role === "learner" && (state.prefs || {}).line_colour !== colour) keepPrefs({line_colour: colour});
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
    if (cap && TIERS.indexOf(state.tier) > TIERS.indexOf(cap)) toast(`Your teacher set the graphics to at most ${gameTier(cap, gameTiers())}.`, false, 6000);
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

// what each tier draws, for the Graphics tab (only the game's own are shown: CHANGE 144; a game's scene may say it
// its own way, its TIER_TEXT: Robot Lab's ultra, CHANGE 145; Fight Lab's lines and ultra, CHANGE 147)
const TIER_TEXT = {
    mesh: "mesh: black, and every triangle's edges in one colour (the basic mesh), the lines behind hidden.",
    lines: "lines: black, the outlines in one colour and a grid on the ground (an old vector arcade game).",
    blocks: "blocks: flat colours, nothing lit, the floor every machine draws.",
    low: "low: the app's lighting and textures, no shadows or reflections.",
    medium: "medium: surface detail, the sky's reflections, shadows.",
    high: "high: sharper shadows and textures, and more pixels.",
    ultra: "ultra: for a strong graphics card: soft shadows reaching far, shading in the corners, glow, the world reflected in the paint, a sky with clouds, hills, more trees, skid marks and sparks."};

function graphicsHtml() {
    const cap = classCap(), drawn = drawnTier(), now = tierSettings(drawn), top = cap ? TIER_SETTINGS[cap] : null;
    const tiers = gameTiers(), capShown = cap ? gameTier(cap, tiers) : null;
    const tuned = Object.keys(state.gfx.parts).length, aa = !!(engine && engine._gl && engine._gl.getContextAttributes().antialias);
    const over = (part, v) => top && (typeof v === "boolean" ? v && !top[part] : v > top[part]);
    const chosen = chosenTier();
    let html = `<h2>Graphics</h2>
      <div class="row"><button id="btn-auto" class="${state.autoTier ? "on" : ""}">Auto</button>${tiers.map(t =>
        `<button data-tier="${t}" class="${drawn === t ? "on" : ""}"${capShown && TIERS.indexOf(t) > TIERS.indexOf(capShown) ? " disabled" : ""}>${t}</button>`).join("")}</div>
      <div class="note">Drawing ${drawn}${chosen !== drawn ? ` (${chosen} chosen: this game draws ${drawn} for it)` : ""}${state.autoTier ? " (Auto: down a tier after three seconds under 28 frames a second, back up after " +
        `${AutoTier.UP_SECS} seconds with no frames missed${tiers.includes("lines") ? "; it never picks mesh or lines, or leaves them" : ""})` : ""}${tuned ? ", with parts changed below" : ""}.
        ${cap ? `Your teacher's class maximum is <b>${capShown}</b>: nothing above it can be chosen.` : ""}
        ${tiers.map(t => ((state.scene && state.scene.constructor.TIER_TEXT) || {})[t] || TIER_TEXT[t]).join(" ")} A tier picked here turns Auto off; picking a tier sets every part below to that tier's. Kept on this computer.</div>`;
    if (tiers.includes("lines")) {  // (the line tiers' colour: at once, kept on this computer and in a learner's profile)
        const lc = getLineColour();
        html += `<div class="row"><label>Line colour</label>${LINE_COLOURS.map(([n, c]) =>
            `<button data-linecol="${c}" class="${lc === c ? "on" : ""}" title="${n}"><span class="sw" style="background:${c}"></span> ${n}</button>`).join("")}
            <input type="color" data-linecolpick value="${lc}" title="any colour"></div>
          <div class="note">The colour of the lines on mesh and lines${state.role === "learner" ? " (yours: kept with your profile, as in the game window)" : " (kept on this computer)"}.</div>`;
    }
    html += `<h2>The parts</h2><table>`;
    for (const [part, label, choices, needs] of PART_ROWS) {
        const off = needs && !now[needs];  // (blocks: nothing lit, so no shadows, maps or reflections)
        html += `<tr><th>${esc(label)}</th><td>${choices.map(v => `<button data-part="${part}" data-val="${v}" class="${now[part] === v ? "on" : ""}"${off || over(part, v) ? " disabled" : ""}>${partText(part, v)}</button>`).join("")}</td></tr>`;
    }
    html += `<tr><th>Smooth edges (multisampling)</th><td><button data-aa="1" class="${state.gfx.aa ? "on" : ""}">on</button><button data-aa="0" class="${state.gfx.aa ? "" : "on"}">off</button>
        ${state.gfx.aa !== aa ? `<span class="note">from the next time the page opens</span>` : ""}</td></tr>
      <tr><th>Frame rate box</th><td><button data-fpsbox="1" class="${state.gfx.fps ? "on" : ""}">shown</button><button data-fpsbox="0" class="${state.gfx.fps ? "" : "on"}">hidden</button></td></tr>
      ${state.game && state.game.aheadNote ? `<tr><th>Movement</th><td><button data-ahead="1" class="${state.gfx.ahead ? "on" : ""}">now</button><button data-ahead="0" class="${state.gfx.ahead ? "" : "on"}">as sent</button>
        <span class="note">now: ${esc(state.game.aheadNote)}</span></td></tr>` : ""}</table>
      ${tuned ? `<div class="row"><button id="btn-parts-reset">Back to ${drawn}'s own</button></div>` : ""}
      <div class="note">${["mesh", "lines", "blocks"].includes(drawn) ? `On ${drawn} nothing is lit, so only the pixels count. ` : ""}Each tier draws at most so many pixels
        however fine the screen (${tiers.map(t => `${t} ${(TIER_SETTINGS[t].pixels / 1e6).toFixed(1)}`).join(", ")} million); more is sharper and slower.</div>`;
    if (state.role !== "learner") {
        const mx = (state.lesson || {}).gfx_max, mine = mx === "basic" ? "blocks" : mx;
        html += `<h2>Class maximum</h2><div class="row">${tiers.map(t => `<button data-gfxmax="${t}" class="${mine === t ? "on" : ""}">${t}</button>`).join("")}
            <button data-gfxmax="" class="${TIERS.includes(mine) ? "" : "on"}">no limit</button></div>
          ${TIERS.includes(mine) && !tiers.includes(mine) ? `<div class="note">The class maximum is ${mine} (another game's): this game draws ${gameTier(mine, tiers)} for it.</div>` : ""}
          <div class="note">The best graphics the class may choose. Learners' pages can't choose above it, Auto never steps past it,
            and a page above it drops to it at once. The game windows open at most at it (one already open turns its shadows
            and smoothing down now, the rest at its next start). Your own view isn't held to it. Kept for the next lesson.</div>`;
    }
    return html;
}

function wireGraphics(body) {
    $("btn-auto").onclick = () => { state.autoTier = !state.autoTier; state.auto.slow = state.auto.good = 0; keepGfx(); renderPanel(); renderPerf(); };
    body.querySelectorAll("button[data-tier]").forEach(b => b.onclick = () => setTier(b.dataset.tier));
    body.querySelectorAll("button[data-linecol]").forEach(b => b.onclick = () => { chooseLineColour(b.dataset.linecol); renderPanel(); });
    const pick = body.querySelector("input[data-linecolpick]");  // (no id: the panel's redraw keeps typed values by id)
    if (pick) {
        pick.oninput = e => chooseLineColour(e.target.value);  // (as it is dragged: at once)
        pick.onchange = () => renderPanel();
    }
    body.querySelectorAll("button[data-part]").forEach(b => b.onclick = () => {
        const v = b.dataset.val, value = v === "true" ? true : v === "false" ? false : Number(v);
        setPart(b.dataset.part, TIER_SETTINGS[drawnTier()][b.dataset.part] === value ? null : value);  // (the tier's own: not a change)
    });
    body.querySelectorAll("button[data-aa]").forEach(b => b.onclick = () => { state.gfx.aa = b.dataset.aa === "1"; keepGfx(); renderPanel(); });
    body.querySelectorAll("button[data-fpsbox]").forEach(b => b.onclick = () => { state.gfx.fps = b.dataset.fpsbox === "1"; keepGfx(); applyGraphics(); });
    body.querySelectorAll("button[data-ahead]").forEach(b => b.onclick = () => { state.gfx.ahead = b.dataset.ahead === "1"; keepGfx(); applyGraphics(); });
    if ($("btn-parts-reset")) $("btn-parts-reset").onclick = () => { state.gfx.parts = {}; keepGfx(); applyGraphics(true); };
    body.querySelectorAll("button[data-gfxmax]").forEach(b => b.onclick = () => {
        const t = b.dataset.gfxmax;
        send({type: "lesson", lesson: {gfx_max: t === "blocks" ? "basic" : t || null}});
        toast(t ? `Class maximum: ${t}` : "No class maximum");
    });
}

// (CHANGE 143) the windows' status line: the key delay (keys), Kart Lab's corrections, and AUTOPILOT (P) while your
// brain drives (shown even with the frame rate box hidden, as the window's status line always is)
function autopilotOn() {
    const g = state.game, b = g && g.race && g.race.brains ? g.race.brains[state.name] : null;
    return !!(state.connected && ((state.myMissions || {}).autopilot || (b && b.on)));
}

function renderPerf() {
    const box = $("perf"), shown = !state.gfx || state.gfx.fps, auto = autopilotOn();
    box.style.display = shown || auto ? "" : "none";
    const autoText = auto ? `<b class="autopilot">AUTOPILOT (P)</b>` : "";
    if (!shown) { box.innerHTML = autoText; return; }
    const info = engineInfo(engine), ctrl = state.ctrl && state.ctrl.ctrlMs !== null ? Math.round(state.ctrl.ctrlMs) : null;
    const pred = state.game && state.game.predictor;
    box.innerHTML = `${autoText ? autoText + " · " : ""}${state.fps} fps · ping ${Math.round(state.pingMs)} ms${ctrl !== null ? ` · keys ${ctrl} ms` : ""}` +
        ` · stalls ${state.stalls} · missed ${state.missed}${pred ? ` · corrections ${pred.corrections}` : ""}<br>` +
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
    // (CHANGE 143) the learner's panel says what it is, each word explaining itself (hud.draw_header: "HUD / GUI";
    // garage.js's hookTips shows a [data-tip]'s words)
    const words = state.role === "learner" ? `<div class="hudgui"><span class="tipword" data-tip="HUD">HUD</span> / <span class="tipword" data-tip="GUI">GUI</span>
        <small>hover over a word in capitals to see what it means</small></div>` : "";
    $("panelhead").innerHTML = words + tabs.map(([k, n]) => `<button data-tab="${k}" class="${k === state.tab ? "on" : ""}">${n}</button>`).join("");
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
    // (CHANGE 142) a drop-down in use isn't redrawn under the teacher (the panel is drawn every second: a redraw closed
    // an open list and lost its place for the cursor keys); it is drawn again once let alone for 8 s, or left
    const used = document.activeElement;
    if (used && used.tagName === "SELECT" && $("panelbody").contains(used) && Date.now() - (state.selectAt || 0) < 8000) {
        renderPanelSoon();
        return;
    }
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
            <tr><th>Renderer</th><td>${esc(info.renderer)}</td></tr><tr><th>Screen</th><td>${window.innerWidth} x ${window.innerHeight} at ${devicePixelRatio}x, ${Math.round(1000 / refresh.ms)} Hz${refresh.every > 1 ? ` (drawn every ${refresh.every})` : ""}</td></tr>
            <tr><th>Drawing</th><td>${info.width} x ${info.height} pixels (${info.ratio.toFixed(2)} per screen point)${sc ? `, ${sc.drawCalls()} meshes` : ""}</td></tr>
            <tr><th>Frame rate</th><td>${state.fps} fps, ${state.stalls} stalls, ${state.missed} missed snapshots</td></tr></table>
          <div class="note">These numbers from a school laptop and a Chromebook are the measurement nobody has published: note them down.</div>`;
        wireGraphics(body);
        // the window's own Settings: the text size and the look (kept on this computer)
        body.insertAdjacentHTML("beforeend", `<h2>Text and look</h2><div class="row">Text size ${[1, 2, 3, 4].map(k =>
            `<button data-tsize="${k}" class="${(state.textSize || 2) === k ? "on" : ""}">${["Small", "Normal", "Large", "Larger"][k - 1]}</button>`).join("")}</div>
          <div class="row">Look <button data-look="dark" class="${state.look !== "light" ? "on" : ""}">Dark</button><button data-look="light" class="${state.look === "light" ? "on" : ""}">Light</button></div>
          <div class="row">Mouse wheel <button data-iscroll="0" class="${state.invertScroll ? "" : "on"}">Normal</button><button data-iscroll="1" class="${state.invertScroll ? "on" : ""}">Inverted</button></div>
          <div class="note">Inverted: the wheel slides the panel and scrolls the code the other way up (old school).</div>
          <div class="row">Wheel zoom <button data-izoom="0" class="${state.invertZoom ? "" : "on"}">Normal</button><button data-izoom="1" class="${state.invertZoom ? "on" : ""}">Inverted</button></div>
          <div class="note">Normal: wheel up zooms in. Inverted: wheel up zooms out. ${state.role === "learner" ? "Yours: kept with your profile, as in the game windows." : "Kept on this computer."}</div>`);
        body.querySelectorAll("button[data-tsize]").forEach(b => b.onclick = () => { setLook({textSize: Number(b.dataset.tsize)}); renderPanel(); });
        body.querySelectorAll("button[data-look]").forEach(b => b.onclick = () => { setLook({look: b.dataset.look}); renderPanel(); });
        body.querySelectorAll("button[data-iscroll]").forEach(b => b.onclick = () => { setLook({invertScroll: b.dataset.iscroll === "1"}); renderPanel(); });
        body.querySelectorAll("button[data-izoom]").forEach(b => b.onclick = () => { setLook({invertZoom: b.dataset.izoom === "1"}); renderPanel(); });
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
    const keyTable = () => `<table>${keyList().map(([k, w]) => `<tr><td><b>${esc(k)}</b></td><td>${esc(w)}</td></tr>`).join("")}</table>`;
    if (state.role === "learner") {  // (the learner's key list, as the windows show it: the game's keyList, CHANGE 143)
        body.innerHTML = `<h2>Keys</h2>${keyTable()}
          <p class="note">Click the game first so the keys go to it. While you type in the panel, the keys type instead.
            H shows or hides this list over the game.</p>`;
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
      <p class="note">Keys: <b>Tab</b> opens and closes this panel.${g.id === "robotlab" ? " <b>B</b> makes the health bars small or full."
        : g.id === "fightlab" ? " <b>B</b> makes the rings box small or full." : ""} <b>H</b> shows or hides the key list over the game.</p>
      <h2>Keys</h2>${keyTable()}`;
}

// ---------- the keys' list (CHANGE 143): the Keys tab, and H's list over the game as the windows show theirs ----------
// The game's own (its keyList: [[key, what]]), else the windows' key lists here, then the keys every game shares
const KEYS = {
    robotlab: [["Arrows", "drive"], ["Space", "weapon"], ["V", "camera view"], ["L", "watch the next robot (then V for the view)"],
               ["O", "the full arena"], ["[ and ]", "watch another arena"],
               ["Wheel, + and -", "zoom"], ["Q and E", "swing the view round"], ["Home", "the view back as it was"],
               ["B", "the health bars: small or full"], ["N", "sound on or off"]],
    fightlab: [["Arrows", "move"], ["A", "punch (again for a combo)"], ["S", "kick (forward + S: high kick)"], ["D", "special"],
               ["W", "throw"], ["Space", "jump"], ["F", "cartwheel (when it's on)"], ["Shift", "block"], ["X", "crouch (X + Shift: low block)"],
               ["V", "camera view"], ["Q and E", "swing the view round"], ["Wheel, + and -", "zoom"], ["Home", "the view back as it was"],
               ["O", "every ring"], ["[ and ]", "watch another ring"], ["B", "the rings box: small or full"], ["N", "sound on or off"]],
    kartlab: [["Arrows or WASD", "drive"], ["Shift", "drift"], ["Space", "use your item"], ["B", "handbrake"], ["R", "respawn"],
              ["V", "camera view"], ["L", "watch the next kart"], ["Wheel, + and -", "zoom"], ["N", "sound on or off"]],
};

function keyList() {
    const g = state.game;
    if (!g) return [];
    const list = [...(g.keyList ? g.keyList() : KEYS[g.id] || [])];
    // (a key already in the game's rows, alone or as "Tab/I", "I or Tab"..., isn't listed twice)
    const has = k => list.some(([x]) => String(x).split(/\s*(?:\/|,| or | and )\s*/).includes(k));
    if (state.role !== "learner" && g.id === "kartlab" && !has("Enter")) list.push(["Enter", "start the race"], ["G", "everyone to the grid"], ["T", "the next track"]);
    if (state.role !== "learner" && g.fixMine && !has("F") && !has("Shift+F")) list.push([g.id === "fightlab" ? "Shift+F" : "F", "fix your own " + (g.id === "robotlab" ? "robot" : g.id === "fightlab" ? "fighter" : "kart")]);  // (CHANGE 182)
    for (const [k, what] of [["U", "upload your brain"], ["P", "autopilot on or off (your brain drives)"], ["N", "sound on or off"],
                             ["I", "the panel (or Tab)"], ["C", "your code"], ["H", "the key list over the game: shown or hidden"]]) {
        if (!has(k)) list.push([k, what]);
    }
    return list;
}

function renderKeyHelp() {
    let hidden = false;
    try { hidden = localStorage.getItem("keys_hidden") === "1"; } catch (e) { /* private window */ }
    const el = $("keyhelp");
    el.hidden = hidden || !state.connected || !state.game;
    if (!el.hidden) el.innerHTML = keyList().map(([k, w]) => `<span><b>${esc(k)}</b> ${esc(w)}</span>`).join("");
}

function toggleKeyHelp() {  // H (the windows' toggle_help: the key list at the bottom hidden or shown, kept)
    const hide = !$("keyhelp").hidden;
    try { localStorage.setItem("keys_hidden", hide ? "1" : "0"); } catch (e) { /* private window */ }
    renderKeyHelp();
    if (hide) toast("Keys hidden (H shows them)", false, 2000);
}

// what the games and teacher.js reach the page through
const appApi = {
    // (tier: the page's choice under the class maximum; each game's scene draws its nearest: CHANGE 144)
    get state() { return state; }, get game() { return state.game; }, get tier() { return chosenTier(); }, setTier: t => setTier(t),
    lineColour: c => chooseLineColour(c),
    get canvas() { return $("view"); }, get engine() { return engine; }, params,
    send, toast, addEvent, renderPanel, updatePills, pushSnap, samplePair, renderTime, esc,
    missionRow: () => missionRow(appApi), wireMissionRow: body => wireMissionRow(appApi, body),
    restartRow: () => restartRow(appApi), wireRestartRow: body => wireRestartRow(appApi, body),
    twice: (key, text, then) => twice(appApi, key, text, then), keepPrefs: p => keepPrefs(p),
    sendBinary: buf => { if (state.ws && state.ws.readyState === WebSocket.OPEN) state.ws.send(buf); },
    get keys() { return keys; }, get ctrl() { return state.ctrl; }, get role() { return state.role; }, get sound() { return sound; },
    openCode: () => toggleCode(appApi),
    // (CHANGE 143) the brain editor (learner.js's Brain button), a panel dragged and kept (Robot Lab's health bars), and
    // the Settings' Wheel zoom: wheelZoom(e) is the factor a wheel turn zooms by (under 1: in), turned round when inverted
    openBrainEditor: () => openBrainEditor(appApi), uploadMyBrain: () => uploadMyBrain(appApi, pickBrain),
    makeDraggable: (el, key, opts) => makeDraggable(el, key, opts),
    get invertZoom() { return !!state.invertZoom; }, get invertScroll() { return !!state.invertScroll; },
    wheelZoom: e => { const f = e.deltaY > 0 ? 1 / 0.88 : 0.88; return state.invertZoom ? 1 / f : f; },
};

// the window's text size (four) and dark or light look, and the mouse wheel's two switches: on this computer, and in a
// learner's profile in the windows' own keys (CHANGE 143: text_size small to xlarge, theme, invert_scroll, invert_zoom;
// hud.py's hud_prefs), so they follow them between the game windows and the page
const TEXT_KEYS = ["small", "medium", "large", "xlarge"];  // (the page's sizes 1 to 4)
function setLook(change = {}) {
    Object.assign(state, change);
    for (const k of [1, 2, 3, 4]) document.body.classList.toggle("text-" + k, (state.textSize || 2) === k && k !== 2);
    document.body.classList.toggle("light", state.look === "light");
    try {
        localStorage.setItem("look", JSON.stringify({textSize: state.textSize || 2, look: state.look || "dark",
                                                     invertScroll: !!state.invertScroll, invertZoom: !!state.invertZoom}));
    } catch (e) { /* private window */ }
    // the wheel's switches where the game files read them (kart.js and robot.js: state.prefs's invert_zoom, or
    // zoom_invert and wheel_invert; state.zoomInvert), the teacher's too (not sent: a teacher's are this computer's)
    state.zoomInvert = !!state.invertZoom;
    const wheel = {invert_scroll: !!state.invertScroll, invert_zoom: !!state.invertZoom, wheel_invert: !!state.invertScroll, zoom_invert: !!state.invertZoom};
    if (Object.keys(change).length && state.role === "learner") {
        keepPrefs({text_size: TEXT_KEYS[(state.textSize || 2) - 1], theme: state.look === "light" ? "light" : "dark", ...wheel});
    } else state.prefs = Object.assign(state.prefs || {}, wheel);
}
try {
    const saved = JSON.parse(localStorage.getItem("look") || "{}");
    state.textSize = saved.textSize; state.look = saved.look; state.invertScroll = !!saved.invertScroll; state.invertZoom = !!saved.invertZoom;
} catch (e) { /* none */ }
setLook();

// a learner's own settings as their profile keeps them (the windows' keys; the page's older "hud" as a fallback) and
// their sound (prefs.sound, the windows' my_sound): put in force without being sent back
function restoreProfileSettings(p) {
    p = p || {};
    const old = p.hud && typeof p.hud === "object" ? p.hud : {};
    const size = TEXT_KEYS.indexOf(p.text_size) + 1 || ([1, 2, 3, 4].includes(old.text_size) ? old.text_size : 0);
    if (size) state.textSize = size;
    if (p.theme === "dark" || p.theme === "light") state.look = p.theme;
    else if ("light" in old) state.look = old.light ? "light" : "dark";
    if ("invert_scroll" in p) state.invertScroll = !!p.invert_scroll;
    if ("invert_zoom" in p) state.invertZoom = !!p.invert_zoom;
    setLook();
    if (p.sound && typeof p.sound === "object") sound.useOwn(p.sound);
    if (cleanColour(p.line_colour)) chooseLineColour(p.line_colour, false);  // (CHANGE 144)
}

// (CHANGE 143) the teacher's Show learners (hud.show_missions_changed): ticked, a learner's Mission tab opens, every
// time it is ticked; unticked, it closes again (I opens the tab they had before)
function showMissionsChanged(was, now) {
    now = !!now;
    state.showMissionsSeen = now;
    if (state.role !== "learner" || !!was === now) return;
    const panel = $("panel"), open = panel.classList.contains("open");
    if (now) {
        if (!(open && state.tab === "mission")) state.tabBeforeMissions = state.tab !== "mission" ? state.tab : null;
        state.tab = "mission";
        panel.classList.add("open");
    } else if (state.tab === "mission") {
        panel.classList.remove("open");
        if (state.tabBeforeMissions) state.tab = state.tabBeforeMissions;
        state.tabBeforeMissions = null;
    }
    buildTabs();
    renderPanel();
}

// a learner's preferences (the camera, the half-typed AI card...) kept in their profile, as the windows do
function keepPrefs(p) {
    state.prefs = Object.assign({}, state.prefs || {}, p);
    state.prefsDirty = true;
}

// the games' sounds (sound.js): nothing plays until the first click or key, as browsers insist
const sound = new Sound({base: "sfx/"});
sound.onChange = s => { if (state.role === "learner") keepPrefs({sound: s}); };  // (their profile's, as the windows': CHANGE 143)

// the keyboard: playing (play.js), and the windows' keys for the panel and the rest
const keys = new Keys();
// (CHANGE 143) as each window binds them: U and P for the teacher's own robot, kart or fighter too; the camera's keys
// (O, [ and ], Home, + and -, Q and E) call the game's own (Fight Lab's camera keys are fight.js's own listener, so
// FightGame has none of these names); the teacher's Kart Lab keys (Enter, G, T); H the key list
keys.onKey = (k, e) => {
    if (!state.connected || deskShown()) return;
    const g = state.game, teacher = state.role !== "learner";
    const onPage = !(e.target && e.target.closest && e.target.closest("button, a, #panel, #codepanel, #brainpanel"));  // (Enter on a button presses it)
    if (k === "i") { $("panel").classList.toggle("open"); if ($("panel").classList.contains("open")) renderPanel(); }
    else if (k === "c" && g) toggleCode(appApi);
    else if (k === "p") { if (brainsOn(appApi)) send({type: "autopilot"}); }
    else if (k === "u" && g) uploadMyBrain(appApi, pickBrain);
    else if (k === "h") toggleKeyHelp();
    else if (k === "v" && g && g.cycleCamera) { g.cycleCamera(); updatePills(); }
    else if (k === "l" && g && g.cycleWatch) { g.cycleWatch(); updatePills(); }  // (CHANGE 183) the camera on the next player
    else if (k === "f" && teacher && g && g.fixMine && (g.id === "fightlab" ? e.shiftKey : !e.shiftKey)) g.fixMine();  // (CHANGE 182)
    else if (k === "b" && g && g.toggleBoard) g.toggleBoard();  // (Robot Lab's health bars, Fight Lab's rings box)
    else if (k === "n") { sound.toggleMute(); toast(sound.muted ? "Sound off (N)" : "Sound on (N)"); if (state.tab === "graphics") renderPanel(); }
    else if (!g) return;
    else if (k === "o" && g.fullArena) { g.fullArena(); updatePills(); }
    else if ((k === "[" || k === "]") && g.watchArena) { g.watchArena(k === "[" ? -1 : 1); updatePills(); }
    else if (k === "Home" && g.resetCamera) g.resetCamera();
    else if ((k === "+" || k === "=" || k === "-") && g.zoom) zoomKey(g, k === "-" ? -1 : 1, e.repeat ? "repeat" : "key");
    else if ((k === "q" || k === "e") && g.turnCamera) g.turnCamera(k === "q" ? (e.repeat ? 6 : 20) : (e.repeat ? -6 : -20));
    else if (teacher && onPage && ["Enter", "g", "t"].includes(k)) teacherKey(g, k);
    else if (k === " " && !teacher) weaponLocked(g);
};

// + and -: game.zoom(dir, how), dir 1 closer and -1 wider, how "key" (a press: the window's 0.8 and 1.25) or "repeat"
// (held: 0.9 and 1.11), raw (the game turns the wheel round itself for the inverted Wheel zoom; keys never are).
// (Robot Lab's zoom took (dir -1 closer, repeat) when this was written: it is called that way until robot.js takes
// the shared form and says so with zoomHow = true)
function zoomKey(g, dir, how) {
    if (g.id === "robotlab" && !g.zoomHow) g.zoom(-dir, how === "repeat");
    else g.zoom(dir, how);
}

// the teacher's own keys in a game (Kart Lab's Enter starts the race, G puts everyone on the grid, T the next track:
// kart_client); the game's teacherKey(key) when it has one (true: it was the game's)
function teacherKey(g, k) {
    if (g.teacherKey) { g.teacherKey(k); return; }
    if (g.id !== "kartlab") return;
    if (k === "Enter") send({type: "start"});
    else if (k === "g") send({type: "grid"});
    else if (k === "t") {
        const names = Object.keys((state.rules || {}).tracks || {}), cur = (state.lesson || {}).track;
        if (!names.length) return;
        const next = names.includes(cur) ? names[(names.indexOf(cur) + 1) % names.length] : names[0];
        send({type: "lesson", lesson: {track: next}});
        toast(`Track: ${state.rules.tracks[next]}`, false, 2500);
    }
}

// Space with the teacher's Weapon on/off switch locked (lab_client.space_pressed): a spinner, drum or vertical disc
// is switched with Space, so the learner is told why nothing happens
const TOGGLE_WEAPONS = ["spinner", "drum", "vdisc"];
function weaponLocked(g) {
    if (g.id !== "robotlab" || ((state.lesson || {}).tools || {}).weapon_toggle !== false) return;
    const id = g.myId ? g.myId() : null, r = id !== null ? ((state.roster || {}).robots || []).find(x => x.id === id) : null;
    if (r && TOGGLE_WEAPONS.includes((r.design || {}).weapon || "wedge")) toast("Weapon on/off is switched off for this mission: ask your teacher", false, 3000);
}

function pickBrain() {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".py,.txt";
    input.onchange = () => uploadBrain(appApi, input.files[0]);
    input.click();
}

// (CHANGE 143) a learner leaves the game for the lobby, as closing the game window does in the app (club_coders.py's
// watch_game): the desk is told {type: "wait", after: <this live session>}, so this game opens again only when the
// teacher adds them again (This session, or the live group edited: club_desk's done_with); the lobby waits as ever.
// Pressed twice (the first press asks), as a window isn't closed by a stray click
function leaveToLobby() {
    const b = $("btn-lobby");
    if (!state.learnerLink) return;
    if (!state.lobbySure || Date.now() - state.lobbySure > 4000) {
        state.lobbySure = Date.now();
        b.textContent = "SURE? PRESS AGAIN";
        setTimeout(() => { if (Date.now() - state.lobbySure >= 3900) b.textContent = "BACK TO THE LOBBY"; }, 4000);
        return;
    }
    state.lobbySure = 0;
    b.textContent = "BACK TO THE LOBBY";
    b.hidden = true;
    const after = state.liveId;
    dropView();
    state.ticket = null;
    state.showCode = false;
    renderCode(appApi);
    closeBrainEditor();
    sound.stopAll();
    renderKeyHelp();
    showLogin();
    showLoginPart("wait");
    $("waittext").textContent = "You've left the game. You're in the lobby: it opens again when your teacher adds you to it.";
    setStatus("");
    state.learnerLink.wait(after);
}

// (CHANGE 143) the Settings' Mouse wheel: Inverted slides the panel and scrolls the code the other way up, as the window's
function invertedWheel(e) {
    if (!state.invertScroll || e.ctrlKey) return;
    const el = e.target.closest && e.target.closest("#panelbody, #code-text, #brain-text");
    if (!el) return;
    e.preventDefault();
    const k = e.deltaMode === 1 ? 20 : e.deltaMode === 2 ? el.clientHeight : 1;
    el.scrollTop -= e.deltaY * k;
    el.scrollLeft -= e.deltaX * k;
}

// ---------- start ----------
function setupUi() {
    $("class").onchange = () => {
        const other = $("class").value === "other";
        $("host").hidden = $("hostlabel").hidden = !other;
    };
    $("connect").onclick = () => login();
    for (const id of ["lname", "lpass", "npass", "npass2"]) $(id).onkeydown = e => { if (e.key === "Enter") login(); };
    $("code").onkeydown = e => { if (e.key === "Enter") connect(); };
    $("lobby-logout").onclick = () => {  // (a learner leaves the lobby: logged out at the desk)
        if (state.learnerLink) state.learnerLink.close();
        state.learnerLink = null;
        showLoginPart("form");
        setStatus("Logged out.", true);
    };
    $("toggle").onclick = () => { $("panel").classList.toggle("open"); if ($("panel").classList.contains("open")) renderPanel(); };
    $("btn-desk").onclick = () => showDesk();
    $("btn-lobby").onclick = () => leaveToLobby();  // (CHANGE 143)
    document.addEventListener("wheel", invertedWheel, {passive: false, capture: true});
    window.addEventListener("pointerup", () => { state.dragging = false; });
    for (const kind of ["pointerdown", "keydown", "focusin", "change"]) {  // (a drop-down in use: see renderPanel)
        $("panelbody").addEventListener(kind, e => { if (e.target.tagName === "SELECT") state.selectAt = Date.now(); });
    }
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
    // the username as last time on this computer (teacher, if the teacher logged in here before CHANGE 148's one form)
    let was = "";
    try { was = localStorage.getItem("lname") || (/^(desk|teacher)$/.test(localStorage.getItem("mode") || "") ? "teacher" : ""); } catch (e) { /* storage blocked */ }
    $("lname").value = params.get("mode") === "teacher" ? "teacher" : was;
    setCodeMode(!!(params.get("host") || params.get("code")));  // (no class codes on the page: CHANGE 141)
    if (params.get("name")) $("name").value = params.get("name");
}

// anything that goes wrong is shown on the page (a school laptop has no console open) and kept for the tests
window.__errors = [];
window.addEventListener("error", e => { window.__errors.push(String(e.message)); toast("Problem: " + e.message, false, 8000); });
window.addEventListener("unhandledrejection", e => { window.__errors.push(String(e.reason)); toast("Problem: " + e.reason, false, 8000); });
window.__state = state;  // (the tests read it, and send through the page)
window.__app = appApi;
window.__refresh = refresh;  // (CHANGE 161: the tests read the screen's refresh)

async function main() {
    setupUi();
    // the tier: ?tier=, else the one kept on this computer, else medium (the app's first guess), high on a graphics card
    let kept = null;
    try { kept = localStorage.getItem("tier"); } catch (e) { /* storage blocked */ }
    state.tier = TIERS.includes(params.get("tier")) ? params.get("tier") : TIERS.includes(kept) ? kept : "medium";
    loadGfx();  // (CHANGE 139: Auto, the parts changed by hand, the multisampling, the frame rate box)
    if (TIERS.includes(params.get("tier"))) state.gfx.parts = {};  // (a tier in the address: its own parts)
    setGraphics(state.gfx.parts, null);
    try { setLineColour(localStorage.getItem("line_colour")); } catch (e) { /* storage blocked: the green */ }
    try {
        engine = state.engine = pageEngine($("view"), state.gfx.aa);
        const info = engineInfo(engine);
        if (!params.get("tier") && !TIERS.includes(kept) && /NVIDIA|Radeon RX|Apple M|Arc\(TM\) A|RTX|GTX/i.test(info.renderer || "")) state.tier = "high";
        // (CHANGE 161) no graphics card in use (Chrome's software drawing: hardware acceleration off or blocked on a
        // school computer): blocks, which Auto can't step up from, and the teacher's Learners table says so
        state.softwareGl = SOFTWARE_GL.test(info.renderer || "");
        if (state.softwareGl && !params.get("tier") && !["mesh", "lines"].includes(state.tier)) state.tier = "blocks";
        // (the app's lighting needs WebGL 2; blocks and the line tiers don't)
        if (info.webgl < 2 && !["mesh", "lines", "blocks"].includes(state.tier)) state.tier = "blocks";
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
    // (CHANGE 143) the code panel dragged by its title bar and resized by its corner, as the window's (hud.py's
    // code_at and code_size), its place kept on this computer
    makeDraggable($("codepanel"), "codepanel", {handle: "header", resize: true, minW: 340, minH: 240});
    try {  // (the lessons' names, for the printed records)
        const r = await fetch("lessons.json");
        if (r.ok) state.lessons = await r.json();
    } catch (e) { /* the records print the codes instead */ }
    const v = await pageVersion();
    $("pageversion").textContent = v || "(laptop test)";
    renderPerf();  // (shown or hidden as the frame rate box is set: CHANGE 143)
    requestAnimationFrame(loop);
    if (params.get("autoconnect")) login();
}

main();
