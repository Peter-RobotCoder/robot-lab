// Club Coders Live: the teacher desk in the browser (CHANGE 129). The same club desk the app's Teacher screen talks to
// (desk/club_desk.py): the learners, the groups, Launch and Stop, who is here and the notes, past sessions and their
// printed records. The page keeps one connection to the desk open while it is logged in; the teacher password
// lives only in this page's memory (to log in again if the connection drops), never in the address or storage.

export class DeskLink {
    // on: {ready(first), changed(), message(text, ok), closed(text)}
    constructor(url, password, on) {
        this.url = url;
        this.password = password;
        this.on = on;
        this.state = null;
        this.sessions = null;
        this.record = null;      // a session just stopped: its record, for printing
        this.waiting = [];       // [{key, resolve, reject}]: requests waiting for their answer
        this.ready = false;
        this.everIn = false;
        this.tries = 0;
        this.ended = false;
        this.claude = null;      // Claude for the browser (CHANGE 136): {machine, games, since, states: {game: ...}}, or none
        this.claudeAsks = new Map();
        this.claudeN = 0;
        this.open();
    }

    open() {
        let ws;
        try { ws = new WebSocket(this.url); } catch (e) { this.on.closed(`Can't reach the desk: ${e.message}`); return; }
        this.ws = ws;
        ws.onopen = () => ws.send(JSON.stringify({type: "teacher", password: this.password, claude: true}));
        ws.onmessage = ev => { let m; try { m = JSON.parse(ev.data); } catch (e) { return; } this.receive(m); };
        ws.onclose = () => {
            if (this.ws !== ws) return;
            this.ready = false;
            for (const w of this.waiting.splice(0)) w.reject(new Error("The connection to the desk closed."));
            for (const w of this.claudeAsks.values()) w.reject(new Error("The connection to the desk closed."));
            this.claudeAsks.clear();
            if (this.ended) return;
            if (this.everIn && this.tries < 30) {  // (logged in before: the Wi-Fi dropped; log in again by itself)
                this.tries++;
                this.on.message("Lost the connection to the desk: reconnecting…", false);
                setTimeout(() => { if (!this.ended) this.open(); }, Math.min(10000, 1000 * this.tries));
            } else {
                this.ended = true;
                this.on.closed(this.everIn ? "Lost the connection to the desk: log in again." : "Couldn't reach the desk on this server.");
            }
        };
    }

    receive(m) {
        if (m.claude_reply) {  // (Claude for the browser's answer to one request of this page's)
            const r = m.claude_reply, w = this.claudeAsks.get(r.rid);
            if (w) { this.claudeAsks.delete(r.rid); clearTimeout(w.timer); if (r.ok === false) w.reject(new Error(r.error || "Claude for the browser said no.")); else w.resolve(r); }
            return;
        }
        if ("claude" in m) {
            this.claude = m.claude;
            if (this.on.claude) this.on.claude();
            if (!m.state) return;
        }
        if (m.ok === false) {
            if (!this.ready) {  // (the login itself was refused)
                this.ended = true;
                try { this.ws.close(); } catch (e) { /* closed */ }
                this.on.closed(m.error || "The desk said no.");
                return;
            }
            const w = this.waiting.shift();
            if (w) w.reject(new Error(m.error || "The desk said no."));
            else this.on.message(m.error || "The desk said no.", false);
            return;
        }
        if ("own_password" in m) this.ownPassword = m.own_password;  // (false: the setup's teacher code: CHANGE 148)
        if (m.sessions) this.sessions = m.sessions;
        if (m.session_record) this.record = m.session_record;
        const i = this.waiting.findIndex(w => w.key in m);
        if (i >= 0) this.waiting.splice(i, 1)[0].resolve(m);
        if (m.state) {
            const first = !this.everIn, back = !this.ready;
            this.state = m.state;
            this.ready = this.everIn = true;
            if (back && !first) this.on.message("Connected to the desk again.", true);
            this.tries = 0;
            this.on.ready(first);
        }
        this.on.changed();
    }

    // send a command; the promise has the desk's answer (the message holding key), or the desk's error
    ask(msg, key = "done") {
        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.ready) {
                reject(new Error("Not connected to the desk just now: try again in a moment."));
                return;
            }
            this.waiting.push({key, resolve, reject});
            this.ws.send(JSON.stringify(msg));
        });
    }

    // Claude for the browser: a request for the teacher's computer running Claude (CHANGE 136); the promise has its
    // answer. game: the class's game; what: send, keep, undo, clear, prompt, diff, rollback, reapply, merge, forget...
    claudeAsk(game, what, args = {}) {
        return new Promise((resolve, reject) => {
            if (!this.ws || this.ws.readyState !== WebSocket.OPEN || !this.ready) {
                reject(new Error("Not connected to the desk just now: try again in a moment."));
                return;
            }
            const rid = ++this.claudeN;
            const timer = setTimeout(() => { if (this.claudeAsks.delete(rid)) reject(new Error("Claude's computer didn't answer.")); }, 60000);
            this.claudeAsks.set(rid, {resolve, reject, timer});
            this.ws.send(JSON.stringify({type: "claude", game, do: what, rid, ...args}));
        });
    }

    claudeFor(game) {  // what Claude's computer last said about this game, or null when it isn't connected for it
        const c = this.claude;
        return c && (c.games || []).includes(game) ? Object.assign({machine: c.machine}, (c.states || {})[game] || {}) : null;
    }

    close() {
        this.ended = true;
        try { this.ws.close(); } catch (e) { /* closed */ }
    }
}

export function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

// ---------- the desk screen ----------
// ctx: {desk, ui: {tab, editing, confirm, message}, lessons, drawn (Set), watching (game or null), watchGames,
//       watch(game), leave(), logout(), rerender()}
export function renderDesk(root, ctx) {
    const kept = keepInputs(root);
    const {desk, ui} = ctx;
    const st = desk.state || {};
    const live = st.live;
    const games = st.games || {};
    const title = g => (games[g] && games[g].title) || g;
    if (live && ui.liveId !== live.id) { ui.liveId = live.id; ui.tab = "session"; }  // (a group just went live)
    if (!ui.tab || (ui.tab === "session" && !live)) ui.tab = live ? "session" : "people";
    const tabs = [...(live ? [["session", "This session"]] : []), ["people", "Learners & groups"], ["records", "Records"],
                  ["watch", "Watch a class"], ["password", "Teacher password"]];
    let liveBar;
    if (live) {
        const watchable = ctx.drawn.has(live.game);
        liveBar = `<span class="livetext">LIVE: ${esc(live.group)} (${esc(title(live.game))}, lesson ${esc(live.lesson)}, since ${esc(String(live.started || "").slice(-5))})</span>
          ${ctx.watching === live.game ? `<button id="dk-back" class="go">BACK TO THE CLASS VIEW</button>`
            : watchable ? `<button id="dk-watch" class="go">WATCH THE CLASS</button>`
            : `<span class="note">${esc(title(live.game))} isn't drawn in the browser yet: open its teacher window from the app.</span>`}
          ${live.learners_in === false ? `<button id="dk-open" class="go">LAUNCH LEARNERS' WINDOWS</button>`
                                       : `<span class="ok">learners' windows launched</span>`}
          <button id="dk-stop" class="stop">${ui.confirm === "stop" ? "PRESS AGAIN TO STOP" : "STOP"}</button>`;
    } else {
        liveBar = `<span class="note">Nothing is live. Launch a group (Learners &amp; groups) when the session starts.</span>
          ${ctx.watching ? `<button id="dk-back" class="go">BACK TO THE CLASS VIEW</button>` : ""}`;
    }
    root.innerHTML = `
      <div class="deskhead"><h1>TEACHER DESK</h1><span class="spacer"></span>
        ${ctx.watching ? `<button id="dk-leave">Leave the class view</button>` : ""}
        <button id="dk-logout">Log out</button></div>
      <div class="livebar">${liveBar}</div>
      <div class="tabs">${tabs.map(([k, n]) => `<button data-dtab="${k}" class="${ui.tab === k ? "on" : ""}">${n}</button>`).join("")}</div>
      <div id="dk-msg" class="${ui.message && ui.message.ok ? "ok" : "bad"}">${esc(ui.message ? ui.message.text : "")}</div>
      <div class="deskbody">${DESK_TABS[ui.tab](ctx, st, title)}</div>`;
    const on = (id, fn) => { const el = root.querySelector("#" + id); if (el) el.onclick = fn; };
    root.querySelectorAll("button[data-dtab]").forEach(b => b.onclick = () => {
        ui.tab = b.dataset.dtab; ui.confirm = null; ui.message = null;
        if (ui.tab === "records") ctx.desk.ask({type: "sessions"}, "sessions").then(ctx.rerender, e => say(ctx, e.message));
        if (ui.tab === "watch") ctx.desk.ask({type: "watch"}, "watch_games").then(m => { ctx.watchGames.splice(0, Infinity, ...m.watch_games); ctx.rerender(); }, e => say(ctx, e.message));
        ctx.rerender();
    });
    on("dk-logout", ctx.logout);
    on("dk-leave", ctx.leave);
    on("dk-back", ctx.back);
    on("dk-watch", () => ctx.watch(live.game));
    on("dk-open", () => command(ctx, {type: "open_learners"}));
    on("dk-stop", () => {
        if (ui.confirm !== "stop") { ui.confirm = "stop"; say(ctx, "Stop ends the session for everyone and files its record. Press again to stop.", false); return; }
        ui.confirm = null;
        command(ctx, {type: "stop"}, () => { ctx.stopped(); ui.tab = "records"; ctx.desk.ask({type: "sessions"}, "sessions").then(ctx.rerender, () => {}); });
    });
    DESK_WIRE[ui.tab](root, ctx, st);
    restoreInputs(root, kept);
}

function say(ctx, text, ok = false) {
    ctx.ui.message = {text, ok};
    ctx.rerender();
}

function command(ctx, msg, then = null) {
    ctx.desk.ask(msg).then(m => { ctx.ui.message = {text: m.done, ok: true}; if (then) then(m); ctx.rerender(); },
                           e => say(ctx, e.message));
}

// typed text survives the redraws (the desk sends its state every few seconds while a group is live)
function keepInputs(root) {
    const values = {};
    root.querySelectorAll("input[id], select[id], textarea[id]").forEach(el => {
        if (el.type === "checkbox") return;
        values[el.id] = el.value;
    });
    const a = document.activeElement;
    return {values, focus: a && root.contains(a) && a.id ? a.id : null,
            sel: a && a.selectionStart !== undefined ? [a.selectionStart, a.selectionEnd] : null};
}

function restoreInputs(root, kept) {
    for (const [id, v] of Object.entries(kept.values)) {
        const el = root.querySelector("#" + CSS.escape(id));
        if (el && el.dataset.fresh !== "1") el.value = v;
    }
    if (kept.focus) {
        const el = root.querySelector("#" + CSS.escape(kept.focus));
        if (el) { el.focus(); try { if (kept.sel) el.setSelectionRange(...kept.sel); } catch (e) { /* not text */ } }
    }
}

const DESK_TABS = {
    session(ctx, st) {
        const live = st.live, ses = st.session || {};
        const present = new Set(ses.present || []), done = ses.done || {}, notes = ses.notes || {};
        const missions = Object.values(done).reduce((a, b) => a + b, 0);
        const rows = (live.learners || []).map((name, i) => {
            const here = present.has(name);
            return `<tr><td class="${here ? "" : "away"}">${esc(name)}</td><td>${here ? "<span class='ok'>here</span>" : "<span class='note'>away</span>"}</td>
              <td class="num">${here ? (done[name] || 0) : ""}</td>
              <td class="grow"><input id="note-${i}" data-name="${esc(name)}" maxlength="400" value="${esc(notes[name] || "")}" placeholder="a note for this session"></td>
              <td><button data-note="${i}">Save</button> <button data-sout="${esc(name)}" title="Takes them out of the game, back to their lobby">Back to lobby</button></td></tr>`;
        }).join("");
        // (CHANGE 141) the lobby: who is logged in and waiting; adding a learner pulls them into the game at once
        const inGame = new Set(live.learners || []), lobby = (st.lobby || []).filter(n => !inGame.has(n));
        const others = (st.learners || []).map(L => L.name).filter(n => !inGame.has(n) && !lobby.includes(n));
        const addRow = names => names.map(n => `<button data-sin="${esc(n)}">${esc(n)} +</button>`).join(" ");
        return `<h2>This session</h2>
          <p>${present.size} of ${(live.learners || []).length} learners here · ${missions} missions completed · ${ses.cards || 0} AI cards</p>
          <table class="wide"><tr><th>Learner</th><th></th><th>Completed</th><th>Note (saved with the record at Stop)</th><th></th></tr>
            ${rows || "<tr><td class='note'>Nobody is in this game yet: add learners below.</td></tr>"}</table>
          <h2>In the lobby (${lobby.length})</h2>
          <div class="row">${lobby.length ? addRow(lobby) : "<span class='note'>Nobody is waiting in the lobby.</span>"}</div>
          ${others.length ? `<p class="note">Not logged in: ${addRow(others)}</p>` : ""}
          <p class="note">Press a name to add them to this game: from the lobby their game opens at once (once you have pressed
            LAUNCH LEARNERS' WINDOWS); anyone else goes straight in when they log in. Back to lobby takes a learner out of the game.
            Press Enter or Save after typing a note. "Completed" is the missions done in this session.
            STOP ends the session and files its record; print it from Records.</p>`;
    },
    people(ctx, st, title) {
        const ui = ctx.ui;
        const learners = st.learners || [];
        const lrows = learners.map((L, i) => `<tr><td>${esc(L.name)}</td>
            <td>${L.changed ? "<span class='note'>their own</span>" : `<span class="starter">starter: ${esc(L.starter)}</span>`}</td>
            <td class="note">${esc(L.last_login || "never")}</td>
            <td><button data-reset="${i}">Reset</button>
                <button data-remove="${i}" class="stop">${ui.confirm === "remove:" + L.name ? "Press again" : "Remove"}</button></td></tr>`).join("");
        const left = `<h2>Learners (${learners.length})</h2>
          <table class="wide"><tr><th>Username</th><th>Password</th><th>Last login</th><th></th></tr>
            ${lrows || "<tr><td class='note' colspan='4'>No learners yet: add them below.</td></tr>"}</table>
          <h2>Add a learner</h2>
          <div class="formrow"><label for="new-user">Username</label><input id="new-user" maxlength="12" autocomplete="off"></div>
          <div class="formrow"><label for="new-starter">Starter password</label><input id="new-starter" autocomplete="off" placeholder="blank: made up for you"></div>
          <div class="formrow"><span></span><button id="dk-add" class="go">Add</button></div>
          <p class="note">A starter password works once: the learner chooses their own when they first log in, and again after Reset.</p>
          ${learners.some(L => !L.changed) ? `<button id="dk-slips">Print login slips (learners with a starter password)</button>` : ""}`;
        let right;
        if (ui.editing) {
            const g = ui.editing;
            right = `<h2>${g.rename_from ? "Edit the group" : "New group"}</h2>
              <div class="formrow"><label for="g-name">Name</label><input id="g-name" maxlength="24" value="${esc(g.name)}" data-fresh="1"></div>
              <div class="formrow"><label for="g-time">Proposed time</label><input id="g-time" value="${esc(g.time || "")}" placeholder="like Tuesday 16:00, or empty" data-fresh="1"></div>
              <div class="formrow"><label for="g-game">Game</label><select id="g-game" data-fresh="1">${Object.entries(st.games || {}).map(([k, v]) =>
                  `<option value="${k}" ${k === g.game ? "selected" : ""}>${esc(v.title)}</option>`).join("")}</select></div>
              <h2>Learners in this group</h2>
              <div class="ticks">${learners.map((L, i) => `<label><input type="checkbox" data-tick="${i}" ${g.learners.includes(L.name) ? "checked" : ""}> ${esc(L.name)}</label>`).join("") || "<span class='note'>Add learners first.</span>"}</div>
              <div class="row"><button id="g-save" class="go">Save group</button><button id="g-cancel">Cancel</button></div>`;
        } else {
            const groups = st.groups || [];
            right = `<h2>Groups</h2>
              <table class="wide">${groups.map((g, i) => `<tr><td><b>${esc(g.name)}</b><br><span class="note">${esc(title(g.game))}, ${g.learners.length} learners${g.time ? `, ${esc(g.time)}` : ""}</span></td>
                <td>${st.live ? "" : `<span class="note">launch on lesson</span> ${(st.lessons || [1, 2, 3, 4, 5]).map(n => `<button data-launch="${i}" data-lesson="${n}" class="${n === 1 ? "go" : ""}">${n}</button>`).join("")}`}</td>
                <td><button data-edit="${i}">Edit</button> <button data-delgroup="${i}" class="stop">${ui.confirm === "group:" + g.name ? "Press again" : "Delete"}</button></td></tr>`).join("")
                || "<tr><td class='note'>No groups yet.</td></tr>"}</table>
              ${st.live ? "<p class='note'>A group is live: stop it before launching another.</p>" : "<p class='note'>A number launches the group on that lesson. Only that group's learners can log in while it is live.</p>"}
              <button id="dk-newgroup">New group</button>`;
        }
        return `<div class="cols"><div>${left}</div><div>${right}</div></div>`;
    },
    records(ctx) {
        const sessions = ctx.desk.sessions;
        if (!sessions) return "<p class='note'>Asking the desk…</p>";
        const rec = ctx.desk.record;
        // (CHANGE 143) one learner's cards on their own: everyone with a card in these sessions
        const named = [...new Set(sessions.flatMap(s => [...Object.keys((s.report || {}).done || {}), ...Object.keys(s.notes || {})]))].sort();
        const games = (ctx.desk.state || {}).games || {};
        return `<h2>Past sessions</h2>
          ${rec ? `<p class="ok">${esc(rec.group)} has stopped: its record is filed. <button data-print="${esc(rec.id)}" class="go">Print its record</button></p>` : ""}
          <table class="wide"><tr><th>Started</th><th>Group</th><th>Game</th><th>Lesson</th><th>Here</th><th></th></tr>
          ${sessions.map(s => `<tr><td>${esc(String(s.started || "").slice(0, 16))}</td><td>${esc(s.group)}</td><td>${esc((ctx.lessons[s.game] || {}).title || s.game)}</td>
            <td class="num">${esc(s.lesson)}</td><td class="num">${Object.keys((s.report || {}).present || {}).length}</td>
            <td><button data-print="${esc(s.id)}">Print</button> <button data-printsum="${esc(s.id)}" title="the session summary on its own">Summary only</button></td></tr>`).join("") || "<tr><td class='note' colspan='6'>No sessions yet.</td></tr>"}</table>
          <p class="note">Print makes the session summary and a card for each learner who completed something or has a note, as the
            app's Records does; Summary only prints just the summary. Choose "Save as PDF" in the print box to keep them as files.</p>
          <h2>One learner's records</h2>
          ${named.length ? `<div class="row"><select id="dk-recname">${named.map(n => `<option>${esc(n)}</option>`).join("")}</select>
              <button id="dk-printlearner">Print their cards</button></div>
            <p class="note">Every learner card of theirs from these sessions, oldest first (the app files them in the learner's own folder).</p>`
            : "<p class='note'>No learner has a card yet.</p>"}
          <h2>Scheme of work</h2>
          <div class="row">${Object.entries(games).map(([g, v]) => `<button data-scheme="${esc(g)}">Print scheme of work: ${esc(v.title)}</button>`).join("")}</div>
          <p class="note">Each game's lessons, outcomes with their curriculum references, missions and lesson pieces, from the game's lesson file.</p>`;
    },
    watch(ctx) {
        const games = ctx.watchGames;
        return `<h2>Watch a class</h2>
          <p class="note">Opens the class server's live view as the teacher, whether or not a group is live. Only one teacher window
            can be open on a class: close the app's teacher window first.</p>
          <div class="row">${games.map(g => ctx.drawn.has(g.game)
              ? `<button data-watchgame="${esc(g.game)}" class="go">${esc(g.name)}</button>`
              : `<button disabled title="not drawn in the browser yet">${esc(g.name)} (not drawn yet)</button>`).join("") || "<span class='note'>Asking the desk…</span>"}</div>`;
    },
    password() {
        return `<h2>Change the teacher password</h2>
          <p class="note">At least 12 characters (three words is good). Once it is changed, only the new password opens the Teacher
            screen, here and in the app: the old one, and the server's teacher code, stop working.</p>
          <form id="pw-form" onsubmit="return false" autocomplete="on">
          <input type="text" name="username" value="teacher" autocomplete="username" hidden>
          <div class="formrow"><label for="pw-now">Password now</label><input id="pw-now" type="password" autocomplete="current-password"></div>
          <div class="formrow"><label for="pw-new">New password</label><input id="pw-new" type="password" autocomplete="new-password"></div>
          <div class="formrow"><label for="pw-again">Type it again</label><input id="pw-again" type="password" autocomplete="new-password"></div>
          <div class="formrow"><span></span><button id="pw-change" class="go">Change it</button></div></form>`;
    },
};

const DESK_WIRE = {
    session(root, ctx, st) {
        const save = i => {
            const box = root.querySelector("#note-" + i);
            command(ctx, {type: "note", name: box.dataset.name, text: box.value});
        };
        root.querySelectorAll("button[data-note]").forEach(b => b.onclick = () => save(b.dataset.note));
        root.querySelectorAll("button[data-sin]").forEach(b => b.onclick = () => command(ctx, {type: "session_learner", name: b.dataset.sin, in: true}));
        root.querySelectorAll("button[data-sout]").forEach(b => b.onclick = () => command(ctx, {type: "session_learner", name: b.dataset.sout, in: false}));
        root.querySelectorAll("input[id^='note-']").forEach(el => el.onkeydown = e => { if (e.key === "Enter") save(el.id.slice(5)); });
    },
    people(root, ctx, st) {
        const ui = ctx.ui, learners = st.learners || [], groups = st.groups || [];
        const $r = id => root.querySelector("#" + id);
        const add = () => {
            const name = $r("new-user").value.trim(), starter = $r("new-starter").value.trim();
            if (!name) return say(ctx, "Type a username (letters and numbers, up to 12).");
            command(ctx, {type: "add_learner", name, starter}, () => { $r("new-user").value = ""; $r("new-starter").value = ""; $r("new-user").focus(); });
        };
        if ($r("dk-add")) $r("dk-add").onclick = add;
        if ($r("new-starter")) $r("new-starter").onkeydown = e => { if (e.key === "Enter") add(); };
        if ($r("new-user")) $r("new-user").onkeydown = e => { if (e.key === "Enter") $r("new-starter").focus(); };
        root.querySelectorAll("button[data-reset]").forEach(b => b.onclick = () =>
            command(ctx, {type: "reset_password", name: learners[b.dataset.reset].name}));
        root.querySelectorAll("button[data-remove]").forEach(b => b.onclick = () => {
            const name = learners[b.dataset.remove].name;
            if (ui.confirm !== "remove:" + name) {
                ui.confirm = "remove:" + name;
                return say(ctx, `Remove ${name} and delete everything the games keep about them? Press again to confirm.`);
            }
            ui.confirm = null;
            command(ctx, {type: "remove_learner", name});
        });
        if ($r("dk-slips")) $r("dk-slips").onclick = () => printSlips(learners.filter(L => !L.changed));
        root.querySelectorAll("button[data-launch]").forEach(b => b.onclick = () => {
            const g = groups[b.dataset.launch];
            say(ctx, `Launching ${g.name}…`, true);
            command(ctx, {type: "launch", group: g.name, lesson: Number(b.dataset.lesson)}, () => ctx.launched(g.game));
        });
        root.querySelectorAll("button[data-edit]").forEach(b => b.onclick = () => {
            const g = groups[b.dataset.edit];
            ui.editing = {name: g.name, game: g.game, time: g.time || "", learners: [...g.learners], rename_from: g.name};
            ctx.rerender();
        });
        root.querySelectorAll("button[data-delgroup]").forEach(b => b.onclick = () => {
            const name = groups[b.dataset.delgroup].name;
            if (ui.confirm !== "group:" + name) { ui.confirm = "group:" + name; return say(ctx, `Delete the group ${name}? Its learners stay. Press again to confirm.`); }
            ui.confirm = null;
            command(ctx, {type: "delete_group", name});
        });
        if ($r("dk-newgroup")) $r("dk-newgroup").onclick = () => {
            ui.editing = {name: "", game: Object.keys(st.games || {kartlab: 1}).includes("kartlab") ? "kartlab" : "robotlab", time: "", learners: [], rename_from: null};
            ctx.rerender();
        };
        if (ui.editing) {
            const g = ui.editing;
            $r("g-name").oninput = e => { g.name = e.target.value; };
            $r("g-time").oninput = e => { g.time = e.target.value; };
            $r("g-game").onchange = e => { g.game = e.target.value; };
            root.querySelectorAll("input[data-tick]").forEach(box => box.onchange = () => {
                const name = learners[box.dataset.tick].name;
                g.learners = box.checked ? [...new Set([...g.learners, name])] : g.learners.filter(n => n !== name);
            });
            $r("g-save").onclick = () => command(ctx, {type: "set_group", name: g.name, game: g.game, learners: g.learners,
                                                        rename_from: g.rename_from, time: g.time}, () => { ui.editing = null; });
            $r("g-cancel").onclick = () => { ui.editing = null; ui.message = null; ctx.rerender(); };
        }
    },
    records(root, ctx) {
        root.querySelectorAll("button[data-print]").forEach(b => b.onclick = () => {
            const all = ctx.desk.sessions || [];
            const rec = all.find(s => s.id === b.dataset.print) || (ctx.desk.record && ctx.desk.record.id === b.dataset.print ? ctx.desk.record : null);
            if (rec) printSession(rec, all, ctx.lessons);
        });
        root.querySelectorAll("button[data-printsum]").forEach(b => b.onclick = () => {
            const rec = (ctx.desk.sessions || []).find(s => s.id === b.dataset.printsum);
            if (rec) printPages(`${String(rec.started || "").slice(0, 10)} ${rec.group} summary`, summaryHtml(rec, ctx.lessons));
        });
        const pick = root.querySelector("#dk-printlearner");
        if (pick) pick.onclick = () => {
            const name = root.querySelector("#dk-recname").value, p = learnerPages(name, ctx.desk.sessions || [], ctx.lessons);
            if (!p.cards) return say(ctx, `${name} has no learner cards in these sessions.`);
            printPages(p.title, p.html);
        };
        root.querySelectorAll("button[data-scheme]").forEach(b => b.onclick = () => {  // (the app's Print scheme of work)
            const game = b.dataset.scheme;
            ctx.desk.ask({type: "scheme"}, "scheme").then(m => {
                const sc = (m.scheme || {})[game];
                if (!sc) return say(ctx, "That game's lesson file isn't on this server.");
                printPages(`Scheme of work - ${sc.title}`, schemeHtml(sc));
            }, e => say(ctx, e.message));
        });
    },
    watch(root, ctx) {
        root.querySelectorAll("button[data-watchgame]").forEach(b => b.onclick = () => ctx.watch(b.dataset.watchgame));
    },
    password(root, ctx) {
        const $r = id => root.querySelector("#" + id);
        const change = () => {
            const now = $r("pw-now").value, fresh = $r("pw-new").value, again = $r("pw-again").value;
            if (!now) return say(ctx, "Type the teacher password as it is now.");
            if (fresh.length < 12) return say(ctx, "The new password needs at least 12 characters: three words you'll remember is good.");
            if (fresh !== again) return say(ctx, "The two new passwords were different: type them again.");
            if (fresh === now) return say(ctx, "That is the password now: choose a different one.");
            ctx.desk.ask({type: "change_teacher_password", password: now, new: fresh}, "teacher_password_changed").then(() => {
                ctx.desk.password = fresh;  // (so the page logs in again with the new one if the connection drops)
                ctx.desk.ownPassword = true;
                try { if (window.PasswordCredential) navigator.credentials.store(new PasswordCredential({id: "teacher", password: fresh})); } catch (e) { /* not offered */ }
                ["pw-now", "pw-new", "pw-again"].forEach(id => { $r(id).value = ""; });
                say(ctx, "The teacher password is changed: use the new one here and in the app from now on.", true);
            }, e => say(ctx, e.message));
        };
        $r("pw-change").onclick = change;
        $r("pw-again").onkeydown = e => { if (e.key === "Enter") change(); };
    },
};

// ---------- printing (the browser's print box: paper, or Save as PDF) ----------
function printPages(title, html) {
    const box = document.getElementById("printout");
    box.innerHTML = html;
    const was = document.title;
    document.title = title;  // (the PDF's suggested file name)
    window.print();
    setTimeout(() => { document.title = was; }, 1000);
}

function printSlips(learners) {
    const host = location.host || "the club's server";
    printPages("Club Coders login slips", `<section class="sheet slips">${learners.map(L => `<div class="slip">
        <b>Club Coders</b><br>Username: <b>${esc(L.name)}</b><br>Starter password: <b>${esc(L.starter)}</b>
        <div class="small">Open the Club Coders app and log in. You'll choose your own password the first time.
          Keep it to yourself. (${esc(host)})</div></div>`).join("")}</section>`);
}

function lessonInfo(lm, n) {
    const missions = Object.entries((lm && lm.missions) || {}).filter(([, m]) => m[0] === Number(n));
    const codes = [...new Set(missions.flatMap(([, m]) => m[2]))].sort();
    return {number: n, title: (lm && lm.lessons[String(n)]) || `Lesson ${n}`, task: (lm && lm.tasks[String(n)]) || "",
            outcomes: codes.filter(c => lm && lm.outcomes[c]).map(c => [c, lm.outcomes[c][0]])};
}

function table(head, rows) {
    return `<table><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</table>`;
}

export function sessionPages(record, sessions, lessons) {
    // the session summary and a card per learner who completed something or has a note: what records.py makes
    const report = record.report || {}, notes = record.notes || {};
    const changed = [...new Set([...Object.keys(report.done || {}), ...Object.keys(notes)])].sort();
    const html = summaryHtml(record, lessons) + changed.map(name => cardHtml(record, name, sessions, lessons)).join("");
    return {title: `${String(record.started || "").slice(0, 10)} ${record.group}`, html, cards: changed.length};
}

// (CHANGE 143) records.py files each learner's cards in their own folder and each summary in sessions/: these print
// one session's summary on its own, and one learner's cards from every session that made one
function hasCard(record, name) {
    return name in ((record.report || {}).done || {}) || name in (record.notes || {});
}

export function learnerPages(name, sessions, lessons) {
    const mine = (sessions || []).filter(s => hasCard(s, name)).sort((a, b) => String(a.started).localeCompare(String(b.started)));
    return {title: `${name} learner cards`, html: mine.map(s => cardHtml(s, name, sessions, lessons)).join(""), cards: mine.length};
}

function lessonOf(record, lessons) {
    const lm = lessons[record.game] || null;
    return {lm, gameTitle: (lm && lm.title) || record.game, info: lessonInfo(lm, record.lesson || 1),
            outName: c => (lm && lm.outcomes[c] ? lm.outcomes[c][0] : c), date: String(record.started || "").slice(0, 10)};
}

function summaryHtml(record, lessons) {
    const lm = lessons[record.game] || null;
    const gameTitle = (lm && lm.title) || record.game;
    const report = record.report || {}, done = report.done || {}, totals = report.totals || {}, notes = record.notes || {};
    const info = lessonInfo(lm, record.lesson || 1);
    const present = Object.keys(report.present || {}).sort();
    const missing = (record.learners || []).filter(n => !present.includes(n)).sort();
    const codes = lm ? Object.keys(lm.outcomes) : [...new Set(Object.values(totals).flatMap(t => Object.keys(t)))].sort();
    const outName = c => (lm && lm.outcomes[c] ? lm.outcomes[c][0] : c);
    const date = String(record.started || "").slice(0, 10);
    let html = `<section class="sheet"><h1>Session summary: ${esc(record.group)}</h1>
      <p class="small">${esc(gameTitle)} - ${esc(record.started || "")} to ${esc(String(record.ended || "").slice(-5))} - lesson ${esc(info.number)}: ${esc(info.title)}</p>
      ${info.task ? `<p><b>Aim:</b> ${esc(info.task)}</p>` : ""}
      <h2>Who was here</h2><p><b>Present (${present.length}):</b> ${esc(present.join(", ") || "nobody")}
        ${missing.length ? `<br><b>Missing (${missing.length}):</b> ${esc(missing.join(", "))}` : ""}</p>
      <h2>Outcomes so far (this game)</h2>
      ${present.length ? table(["Learner", "This session", ...codes], present.map(n => [esc(n), String(Object.keys(done[n] || {}).length),
          ...codes.map(c => String((totals[n] || {})[c] || "-"))])) + `<p class="small">Codes: ${codes.map(c => `${esc(c)} ${esc(outName(c))}`).join("; ")}</p>` : "<p>Nobody was here.</p>"}
      <h2>Completed in this session</h2>`;
    const doneRows = [];
    for (const n of present) {
        for (const [mid, d] of Object.entries(done[n] || {}).sort((a, b) => String(a[1].time || "").localeCompare(String(b[1].time || "")))) {
            doneRows.push([esc(n), esc(d.title || mid), esc((d.outcomes || []).join(" ")), esc(String(d.time || "").slice(-5))]);
        }
    }
    html += doneRows.length ? table(["Learner", "Mission", "Outcomes", "When"], doneRows) : "<p>Nothing yet.</p>";
    const cards = report.cards || [];
    html += `<h2>AI cards</h2>` + (cards.length ? table(["Learner", "Status", "Request"], cards.map(c => [esc(c.learner), esc(c.status), esc(c.goal)])) : "<p>None in this session.</p>");
    if (Object.keys(notes).length) html += `<h2>Teacher's notes</h2>` + Object.entries(notes).sort().map(([n, t]) => `<p><b>${esc(n)}:</b> ${esc(t)}</p>`).join("");
    return html + `<p class="small">Usernames only. Printed from Club Coders Live, from the club desk's record.</p></section>`;
}

function cardHtml(record, name, sessions, lessons) {
    const {gameTitle, info, outName, date} = lessonOf(record, lessons);
    const report = record.report || {}, done = report.done || {}, totals = report.totals || {}, notes = record.notes || {};
    const attended = (sessions || []).filter(s => name in ((s.report || {}).present || {})).sort((a, b) => String(a.started).localeCompare(String(b.started)));
    const number = (attended.findIndex(s => s.id === record.id) + 1) || attended.length + 1;
    const mine = done[name] || {};
    const shown = Object.entries(totals[name] || {}).filter(([c, k]) => k).map(([c, k]) => [esc(outName(c)), String(k)]).sort();
    return `<section class="sheet"><h1>Learner card: ${esc(name)}</h1>
      <p class="small">${esc(gameTitle)} - session ${number} - ${esc(date)} - group ${esc(record.group)}</p>
      <h2>Lesson ${esc(info.number)}: ${esc(info.title)}</h2>
      ${info.task ? `<p><b>Aim:</b> ${esc(info.task)}</p>` : ""}
      <p><b>Learning outcomes for this lesson:</b> ${info.outcomes.map(([c, n]) => `${esc(n)} (${esc(c)})`).join("; ")}</p>
      <h2>What I achieved in this session</h2>
      ${Object.keys(mine).length ? table(["Mission", "Outcomes", "Evidence"], Object.entries(mine).sort((a, b) => String(a[1].time || "").localeCompare(String(b[1].time || "")))
          .map(([mid, d]) => [esc(d.title || mid), esc((d.outcomes || []).join(" ")), esc(d.detail || "")])) : "<p>No missions were completed in this session.</p>"}
      ${notes[name] ? `<p class="green"><b>Teacher's note:</b> ${esc(notes[name])}</p>` : ""}
      <h2>Outcomes shown so far in ${esc(gameTitle)}</h2>
      ${shown.length ? table(["Outcome", "Times shown"], shown) : "<p>None yet.</p>"}
      <h2>Sessions so far</h2>
      ${table(["Date", "Game", "Group", "Lesson", "Missions completed", "Note"], attended.map(s => [esc(String(s.started || "").slice(0, 10)),
          esc((lessons[s.game] || {}).title || s.game), esc(s.group), esc(s.lesson), String(Object.keys(((s.report || {}).done || {})[name] || {}).length),
          esc((s.notes || {})[name] || "")]))}
      <p class="small">Club Coders keeps usernames only.</p></section>`;
}

// the scheme of work (records.py scheme_of_work): one game's lessons from its lesson file, through the desk
export function schemeHtml(sc) {
    const date = new Date().toISOString().slice(0, 10);
    return Object.entries(sc.lessons || {}).sort((a, b) => Number(a[0]) - Number(b[0])).map(([n, lesson], i) => {
        const missions = Object.entries(sc.missions || {}).filter(([, v]) => v[0] === Number(n));
        const codes = [...new Set(missions.flatMap(([, v]) => v[3]))].sort().filter(c => (sc.outcomes || {})[c]);
        const pieces = Object.entries((sc.guide || {})[n] || {});
        return `<section class="sheet">
          ${i === 0 ? `<h1>Scheme of work: ${esc(sc.title)}</h1><p class="small">From the game's lesson file, ${esc(date)}. Five lessons; each
            mission gives evidence for the learning outcomes shown, checked by the game or ticked by the teacher.</p>` : ""}
          <h2>Lesson ${esc(n)}: ${esc(lesson.title)}</h2>
          ${lesson.task ? `<p><b>Overall task:</b> ${esc(lesson.task)}</p>` : ""}
          ${table(["Outcome", "Learners can", "Curriculum"], codes.map(c => [`${esc(sc.outcomes[c][0])} (${esc(c)})`, esc(sc.outcomes[c][1]), `<span class="small">${esc(sc.outcomes[c][2])}</span>`]))}
          ${table(["Mission", "What learners do", "Outcomes", "Checked by"], missions.map(([k, v]) => [esc(k), esc(v[2]), esc(v[3].join(" ")), v[4] === "teacher" ? "teacher" : "the game"]))}
          ${pieces.map(([c, p]) => `<h2>${esc(((sc.outcomes || {})[c] || [c])[0])}: ${esc(p.task)}</h2>
            ${(p.do || []).map((step, k) => `<p>${k + 1}. ${esc(step)}</p>`).join("")}
            <p><b>Explain or show:</b> ${esc(p.teach)}</p><p class="green"><b>Success looks like:</b> ${esc(p.success)}</p>`).join("")}</section>`;
    }).join("");
}

function printSession(record, sessions, lessons) {
    const p = sessionPages(record, sessions, lessons);
    printPages(p.title, p.html);
}

// A learner's login at the desk (CHANGE 134), as the app's login screen does it (launcher/club_coders.py): the
// username and password; a starter password must be changed first; then the desk says to wait for the group, or
// gives the game's address and a ticket. The link stays open while the learner plays, so when the teacher launches
// the next game it opens by itself; after a game ends the page tells the desk it is waiting again.
// on: {changePassword(name), waiting(text), go(go), message(text), closed(text)}
export class LearnerLink {
    constructor(url, name, password, on) {
        this.url = url;
        this.name = name;
        this.password = password;
        this.on = on;
        this.ended = false;
        this.everIn = false;
        this.tries = 0;
        this.open();
    }

    open() {
        let ws;
        try { ws = new WebSocket(this.url); } catch (e) { this.on.closed(`Can't reach the desk: ${e.message}`); return; }
        this.ws = ws;
        ws.onopen = () => ws.send(JSON.stringify({type: "login", name: this.name, password: this.password}));
        ws.onmessage = ev => { let m; try { m = JSON.parse(ev.data); } catch (e) { return; } this.receive(m); };
        ws.onclose = () => {
            if (this.ws !== ws || this.ended) return;
            if (this.everIn && this.tries < 30) {  // (the Wi-Fi: log in again by itself)
                this.tries++;
                setTimeout(() => { if (!this.ended) this.open(); }, Math.min(10000, 1000 * this.tries));
            } else {
                this.ended = true;
                this.on.closed(this.everIn ? "Lost the connection to the desk: log in again." : "Couldn't reach the desk on this server.");
            }
        };
    }

    receive(m) {
        if (m.ok === false) {
            if (!this.everIn) { this.ended = true; try { this.ws.close(); } catch (e) { /* closed */ } this.on.closed(m.error || "The desk said no."); }
            else this.on.message(m.error || "The desk said no.");
            return;
        }
        if (m.name) this.name = m.name;
        if (m.change_password) { this.on.changePassword(this.name); return; }
        this.everIn = true;
        this.tries = 0;
        if (m.changed) this.on.message("Password changed.");
        if (m.go) this.on.go(m.go);
        else if (m.waiting) this.on.waiting(m.message || "You're in the lobby: your game opens by itself when your teacher adds you to it.");
    }

    setPassword(newPassword) {
        this.ws.send(JSON.stringify({type: "set_password", name: this.name, password: this.password, new: newPassword}));
        this.password = newPassword;
    }

    wait(after) {  // (the game window closed: still logged in, waiting for the next launch)
        if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify({type: "wait", after}));
    }

    close() {
        this.ended = true;
        try { this.ws.close(); } catch (e) { /* closed */ }
    }
}
