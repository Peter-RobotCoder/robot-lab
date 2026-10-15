// The teacher tabs every game shares (CHANGE 130). Robot Lab, Fight Lab and Kart Lab all run the engine's teaching
// layer (engine/teaching.py), so these speak the same messages to all three: the Learners view (a learner's
// mission, building their design, their password; the game's own accounts), Outcomes (the grid, ticking
// teacher-checked objectives, the evidence CSV, the missions editor), AI cards, Rules (what learners can change,
// hazards, user mods and the vote, the limits) and Warnings. Built from what each game's server sends (its rules,
// lesson and class), not from a list per game, so a game's new tool or hazard shows up here by itself.

import {renderGarage, buildMine, draftOf, takeDesign, cpuOf} from "./garage.js";
const $ = id => document.getElementById(id);

export const TEACHER_TABS = [["learners", "Learners"], ["outcomes", "Outcomes"], ["cards", "AI cards"], ["changes", "Changes"],
                             ["rules", "Rules"], ["warnings", "Warnings"]];

const NAMES = {points_table: "Points table", code_view: "Code view", stats_readout: "Stats readout",
               name_and_colour: "Name and colour", choose_weapon: "Choose a weapon", weapon_toggle: "Weapon on/off",
               house_robots: "Resident Robots", brains: "Brains (autopilot)", cpu_karts: "Computer karts",
               choose_special: "Choose a special", combo_editor: "Combo editor", body_choice: "Body",
               fighting_style: "Fighting style", bosses: "Bosses", ring_out: "Ring out (no ropes)",
               electric_ropes: "Electric ropes", fire_jets: "Fire jets", floor_flipper: "Floor flipper",
               saws: "Floor saws", spikes: "Spikes", pit: "Drop zone open", slippery: "Slippery ice",
               bumping: "Bumping", forward_speed: "Forward speed", reverse_speed: "Reverse speed",
               turn_speed: "Turn speed", walk_speed: "Walk speed", sidestep_speed: "Sidestep speed",
               jump_height: "Jump height", attack_speed: "Attack speed"};

// a user mod's title and description, as the game's USER_MODS gives them (lessons.json, from make_lessons.py)
export function modInfo(app, key) {
    const game = app.game ? app.game.id : "";
    const m = ((((app.state.lessons || {})[game]) || {}).user_mods || {})[key];
    return m ? {title: m[0], text: m[1]} : {title: pretty(key), text: ""};
}

export function pretty(key) {
    return NAMES[key] || String(key).replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
}

export function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

export function download(name, text, type = "text/plain") {
    const url = URL.createObjectURL(new Blob([text], {type}));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    window.__downloads = (window.__downloads || []).concat([{name, size: text.length, text: text.slice(0, 200000)}]);  // (the tests read it)
}

// a press that must be repeated to happen (remove, delete, restart): the first press arms it for 5 seconds
export function twice(app, key, text, then) {
    const S = app.state;
    if (S.confirm === key && Date.now() - S.confirmAt < 5000) { S.confirm = null; then(); return; }
    S.confirm = key;
    S.confirmAt = Date.now();
    app.toast(text + " Press again to confirm.", false, 5000);
    app.renderPanel();
}

function armed(app, key) {
    return app.state.confirm === key && Date.now() - app.state.confirmAt < 5000;
}

// ---------- rows the games' Controls tabs use ----------
export function missionRow(app) {
    const L = app.state.lesson || {};
    const saved = (L.saved_missions || []).length ? `saved settings: mission ${L.saved_missions.join(", ")}` : "no saved settings yet";
    return `<h2>Mission</h2>
      <div class="row">${[1, 2, 3, 4, 5].map(n => `<button data-mission="${n}" class="${n === L.lesson_number ? "on" : ""}">${n}</button>`).join("")}
        <button id="btn-save">Save settings</button><button id="btn-restore">Restore</button></div>
      <div class="note">The mission sets the learners' tools and the hazards. Save keeps this mission's controls as they are now (${saved}).</div>`;
}

export function wireMissionRow(app, body) {
    body.querySelectorAll("button[data-mission]").forEach(b => b.onclick = () => app.send({type: "lesson_number", n: Number(b.dataset.mission)}));
    $("btn-save").onclick = () => app.send({type: "save_lesson"});
    $("btn-restore").onclick = () => app.send({type: "restore_lesson"});
}

export function restartRow(app) {
    const S = app.state;
    return `<h2>Code changes</h2>
      ${S.liveReady ? `<p class="ok">A live update is ready on the class server (${esc(S.liveReady)}). Warn the class, then press Restart server.</p>` : ""}
      <div class="row"><button id="btn-restart-server" class="stop">${armed(app, "restart") ? "PRESS AGAIN TO RESTART" : "Restart server"}</button>
        <button id="btn-reopen">Reopen learners' windows</button></div>
      <div class="note">Restart server loads new code (a live update, or a kept AI change): everyone gets a warning and their
        window reopens; this page reconnects by itself. Reopen learners' windows reopens just theirs.</div>`;
}

export function wireRestartRow(app, body) {
    $("btn-restart-server").onclick = () => twice(app, "restart", "Restart the class server: every window reconnects.", () => {
        app.state.expectRestart = Date.now();
        app.send({type: "restart_server"});
    });
    $("btn-reopen").onclick = () => { app.send({type: "restart_clients"}); app.toast("The learners' windows are reopening."); };
}

// (the design editors: garage.js, the window's garage drawn from the game's schema)

// ---------- the tabs ----------
export function renderTeacherTab(app, tab, body) {
    const fn = {learners: learnersTab, outcomes: outcomesTab, cards: cardsTab, changes: changesTab, rules: rulesTab,
                warnings: warningsTab}[tab];
    if (!fn) return false;
    fn(app, body);
    return true;
}

function learners(app) {  // the connected learners, from the lesson's class list
    return (app.state.classList || []).filter(p => p.role === "learner");
}

// the computer's robots or fighters the teacher sets up: Fight Lab's one, or Robot Lab's (CHANGE 140: up to four,
// each with its n; those past the lesson's Computer robots are left out, but never the first)
function computers(app) {
    const L = app.state.lesson || {};
    return (app.state.classList || []).filter(p => p.role === "computer" && !(p.n > Math.max(1, L.cpu_robots ?? 1)));
}
const cpuPick = c => c.n > 1 ? `*cpu${c.n}` : "*cpu";

function learnersTab(app, body) {
    const S = app.state, game = app.game, send = app.send;
    const perf = (S.roster && S.roster.perf) || {};
    const cpus = computers(app);
    const people = (S.classList || []).filter(p => p.role !== "computer" || cpus.includes(p));
    const extraHead = game.learnerHead ? game.learnerHead() : [];
    const rows = people.map(p => {
        const pf = perf[p.name] || {};
        const stalls = pf.stalls ?? "";
        const extra = game.learnerCells ? game.learnerCells(p) : [];
        const key = p.role === "computer" ? cpuPick(p) : p.name;
        return `<tr data-learner="${esc(key)}" class="${S.pick === key ? "picked" : ""}"><td>${esc(p.name)}</td><td>${esc(p.role)}</td>` +
               extra.map(c => `<td>${c}</td>`).join("") +
               `<td class="num">${pf.fps ?? ""}</td><td class="num">${pf.ping ?? ""}</td>` +
               `<td class="num ${Number(stalls) > 5 ? "bad" : ""}">${stalls}</td><td>${esc(pf.tier ?? "")}</td></tr>`;
    }).join("");
    const picks = [...learners(app).map(p => [p.name, p.name]), ["*all", "All learners"],
                   ...cpus.map(c => [cpuPick(c), c.n ? `Computer ${c.n}` : c.name]), ["*me", `My ${game.word}`]];
    if (!S.pick || (cpuOf(app, S.pick) && !picks.some(([k]) => k === S.pick)))  // (a computer robot no longer in use)
        S.pick = learners(app)[0] ? learners(app)[0].name : "*all";
    body.innerHTML = `
      <h2>Who is here</h2>
      <table><tr><th>Name</th><th>Role</th>${extraHead.map(h => `<th>${esc(h)}</th>`).join("")}<th>fps</th><th>ping</th><th>stalls</th><th>graphics</th></tr>${rows}</table>
      <div class="note">fps, ping and stalls come from each window every few seconds. Stalls are frames over 100 ms apart: a few a
        minute is the Wi-Fi; dozens means that laptop or the room's network needs looking at. Click a name to look at them.</div>
      <h2>Look at</h2>
      <div class="row">${picks.map(([k, n]) => `<button data-pick="${esc(k)}" class="${S.pick === k ? "on" : ""}">${esc(n)}</button>`).join("")}</div>
      <div id="pickbody"></div>
      ${accountsHtml(app)}`;
    body.querySelectorAll("tr[data-learner]").forEach(tr => tr.onclick = () => { S.pick = tr.dataset.learner; S.sub = null; S.viewDrafts = {}; app.renderPanel(); });
    body.querySelectorAll("button[data-pick]").forEach(b => b.onclick = () => { S.pick = b.dataset.pick; S.sub = null; S.formBase = null; S.viewDrafts = {}; app.renderPanel(); });
    pickBody(app, $("pickbody"));
    wireAccounts(app, body);
}

function pickBody(app, box) {
    const S = app.state, send = app.send, game = app.game, L = S.lesson || {};
    const people = S.classList || [];
    const cpu = cpuOf(app, S.pick);
    if (S.pick === "*all" || S.pick === "*me" || cpu) {
        const who = S.pick === "*me" ? null : S.pick;
        const which = cpu && cpu.n ? {n: cpu.n} : {};  // (which computer robot: Robot Lab's, CHANGE 140)
        const arenas = L.arenas || 1, all = people.filter(p => p.role === "computer").length;
        box.innerHTML = `<div id="dzgarage"></div>
          <div class="row"><button id="dz-history">Load a saved design</button></div>
          ${S.history ? `<div class="row"><select id="dz-hist">${S.history.slice(0, 80).map((h, i) => `<option value="${i}">${esc(h.when)} ${esc(h.who)}: ${esc(h.name)}</option>`).join("")}</select><button id="dz-load">Load it</button></div>` : ""}
          ${S.pick === "*all" && L.start_design ? `<div class="row"><button id="dz-reset">Reset every learner to the mission's starting design</button></div>` : ""}
          ${S.pick === "*me" && L.start_design !== undefined ? `<div class="row"><button id="dz-start">Save as the learners' starting design</button>
              ${L.start_design ? `<button id="dz-standard">Standard again</button>` : ""}</div>
              <div class="note">The ${esc(game.word)} every learner starts this mission with (with their own name and colour); "Reset every
                learner" on All learners gives it to everyone now.</div>` : ""}
          ${cpu && "arena" in cpu ? `<h3>Where it is</h3><div class="row"><label>Computer robots</label><select id="cpu-count">${
                Array.from({length: all + 1}, (_, k) => `<option ${k === L.cpu_robots ? "selected" : ""}>${k}</option>`).join("")}</select>
              <label>Its arena</label><select id="cpu-arena"><option value="">Every arena</option>${
                Array.from({length: Math.max(arenas, (cpu.arena ?? -1) + 1)}, (_, k) => `<option value="${k}" ${cpu.arena === k ? "selected" : ""}>Arena ${k + 1}</option>`).join("")}</select></div>
              <div class="note">${!cpu.in_arena ? `It isn't in the arena: Computer robots is ${esc(L.cpu_robots)}.`
                : cpu.arena === null ? "It is in every arena: the same opponent for everyone."
                : cpu.in !== cpu.arena ? `Set to arena ${cpu.arena + 1}, but there ${arenas === 1 ? "is 1 arena" : `are ${arenas}`}: it is in arena ${cpu.in + 1}.`
                : `It is in arena ${cpu.arena + 1} only.`}</div>` : ""}
          ${cpu ? `<h3>Its brain</h3><div class="row"><button id="cpu-reset" class="stop">Reset: as it comes</button>
              <button id="cpu-auto" class="${cpu.autopilot ? "on" : ""}">Autopilot ${cpu.autopilot ? "on" : "off"}</button>
              <label class="filebtn">Upload its brain (.py)<input id="cpu-brain" type="file" accept=".py,text/x-python,text/plain" hidden></label></div>
              <div class="note">${cpu.brain ? "It has its own brain." : "No brain of its own yet."} Autopilot uses the uploaded brain.</div>` : ""}`;
        renderGarage(app, $("dzgarage"), {who, pre: "dz",
            after: S.pick === "*all" ? `<div class="note">Everyone connected gets exactly this, and so does anyone who joins this session.</div>` : "",
            build: d => {
                if (!who) return buildMine(app);
                const name = $("dz-name");  // (the window's send_design_for: the name as it is in the box)
                if (name) d.name = Array.from(name.value).slice(0, game.id === "kartlab" ? 12 : 16).join("");
                if (S.pick === "*all") send({type: "design_for_all", design: d});
                else send({type: "cpu_robot", ...which, design: d});
            }});
        $("dz-history").onclick = () => send({type: "history"});
        if ($("dz-load")) $("dz-load").onclick = () => {
            const h = S.history[Number($("dz-hist").value)];
            if (h && h.design) { takeDesign(app, h.design, who); S.formSeq = (S.formSeq || 0) + 1; app.renderPanel(); }
        };
        if ($("dz-reset")) $("dz-reset").onclick = () => send({type: "design_for_all", design: L.start_design, keep_own: true});
        if ($("dz-start")) $("dz-start").onclick = () => { send({type: "lesson", lesson: {start_design: draftOf(app)}}); app.toast("Saved as the learners' starting design."); };
        if ($("dz-standard")) $("dz-standard").onclick = () => send({type: "lesson", lesson: {start_design: null}});
        if ($("cpu-reset")) {
            $("cpu-reset").onclick = () => send({type: "cpu_robot", ...which, reset: true});
            $("cpu-auto").onclick = () => send({type: "cpu_robot", ...which, autopilot: !cpu.autopilot});
            $("cpu-brain").onchange = async e => { const f = e.target.files[0]; if (f) send({type: "cpu_robot", ...which, brain: await f.text()}); };
        }
        if ($("cpu-arena")) {
            $("cpu-arena").onchange = e => send({type: "cpu_robot", ...which, arena: e.target.value === "" ? null : Number(e.target.value)});
            $("cpu-count").onchange = e => send({type: "lesson", lesson: {cpu_robots: Number(e.target.value)}});
        }
        return;
    }
    const p = people.find(x => x.name === S.pick);
    if (!p) { box.innerHTML = `<p class="note">${esc(S.pick)} isn't connected now.</p>`; return; }
    S.sub = S.sub || "mission";
    const subs = [["mission", "Mission"], ["build", `Their ${game.word}`], ["cards", "AI cards"], ["login", "Password"]];
    let inner = "";
    if (S.sub === "mission") {
        const v = S.viewing && S.viewing.for === p.name ? S.viewing : null;
        if (S.viewAsked !== p.name) { S.viewAsked = p.name; send({type: "view_learner", name: p.name}); }
        inner = v ? `<h3>Mission ${esc(v.lesson)}: ${esc(v.title || "")}</h3>
            <table>${(v.missions || []).map(m => `<tr><td class="${m.done ? "ok" : ""}">${m.done ? "✓" : "·"}</td><td>${esc(m.id)}</td><td>${esc(m.title)}<div class="note">${esc(m.detail || "")}</div></td>
              <td>${!m.done && m.check === "teacher" ? `<button data-tick="${esc(m.id)}">Tick</button>` : ""}</td></tr>`).join("")}</table>
            <div class="row"><button id="v-refresh">Refresh</button></div>` : `<p class="note">Asking the server…</p>`;
    } else if (S.sub === "build") {
        const theirs = S.theirSlots && S.theirSlots.who === p.name ? S.theirSlots.slots || {} : null;
        inner = `<div id="dzgarage"></div>
          <div class="row"><button id="dz-theirs">Their saved ${esc(game.word)}s</button></div>
          ${theirs ? `<div class="row">${Object.keys(theirs).length ? Object.entries(theirs).map(([n, x]) =>
              `<button data-their="${esc(n)}">${Number(n) + 1}: ${esc(x.name)}</button>`).join("") : `<span class="note">Nothing saved.</span>`}</div>` : ""}
          <div class="note">Built with the widest limits, as the teacher window does; ${esc(p.name)} gets it straight away.</div>`;
    } else if (S.sub === "cards") {
        const cards = ((S.teaching || {}).cards || []).filter(c => c.learner === p.name);
        inner = cards.length ? cards.map(c => `<div class="objective"><b>${esc(c.goal || "")}</b> <span class="note">${esc(c.status || "")}${c.note ? ": " + esc(c.note) : ""}</span>
            <div class="note">Variables: ${esc(c.variables || "")}<br>Test: ${esc(c.test || "")}<br>Predict: ${esc(c.predict || "")}</div></div>`).join("")
            : `<p class="note">${esc(p.name)} hasn't sent an AI card yet. The AI cards tab handles them.</p>`;
    } else {
        inner = `<div class="formgrid"><label>New password</label><input id="pw-learner" type="text" autocomplete="off" placeholder="at least 6 characters"></div>
          <div class="row"><button id="pw-set" class="go">Set it</button></div>
          <div class="note">The game's own login (laptop and class-code servers). On the club's server, learners' passwords are on the TEACHER DESK.</div>`;
    }
    box.innerHTML = `<h2>${esc(p.name)}</h2><div class="row">${subs.map(([k, n]) => `<button data-sub="${k}" class="${S.sub === k ? "on" : ""}">${n}</button>`).join("")}</div>${inner}`;
    box.querySelectorAll("button[data-sub]").forEach(b => b.onclick = () => { S.sub = b.dataset.sub; S.formBase = null; app.renderPanel(); });
    if ($("dzgarage")) {
        renderGarage(app, $("dzgarage"), {who: p.name, pre: "dz", build: d => {
            const name = $("dz-name");  // (the window's send_design_for: the name as it is in the box)
            if (name) d.name = Array.from(name.value).slice(0, game.id === "kartlab" ? 12 : 16).join("");
            send({type: "design_for", learner: p.name, design: d});
        }});
    }
    box.querySelectorAll("button[data-tick]").forEach(b => b.onclick = () => { send({type: "tick", learner: p.name, mission: b.dataset.tick}); setTimeout(() => send({type: "view_learner", name: p.name}), 400); });
    if ($("v-refresh")) $("v-refresh").onclick = () => send({type: "view_learner", name: p.name});
    if ($("dz-theirs")) $("dz-theirs").onclick = () => send({type: "slots_of", name: p.name});
    box.querySelectorAll("button[data-their]").forEach(b => b.onclick = () => {
        const x = (S.theirSlots.slots || {})[b.dataset.their];
        takeDesign(app, Object.assign({}, p.design || {}, x.design || {}), p.name);
        S.formSeq = (S.formSeq || 0) + 1;
        app.renderPanel();
        app.toast(`Loaded ${x.name}: press BUILD FOR ${p.name.toUpperCase()} to give it them.`);
    });
    if ($("pw-set")) $("pw-set").onclick = () => {
        const pw = $("pw-learner").value;
        if (pw.length < 6) return app.toast("Passwords need at least 6 characters.");
        send({type: "set_password", learner: p.name, password: pw});
        $("pw-learner").value = "";
    };
}

function accountsHtml(app) {
    const S = app.state, T = S.teaching || {}, ses = S.session || {};
    const names = [...new Set([...(T.accounts || []), ...(ses.all || [])])].sort((a, b) => a.localeCompare(b));
    const inSession = new Set(ses.learners || []);
    return `<h2>Accounts on this game server (${names.length})</h2>
      <div class="note">The game's own records of each learner (their ${esc(app.game.word)}, evidence, AI cards). Deleting one removes all of
        it. ${ses.desk && ses.live ? "The tick lets a learner into this desk session, or takes them out." : ""}</div>
      <table>${names.slice(0, 200).map((n, i) => `<tr><td>${esc(n)}</td>
        ${ses.desk && ses.live ? `<td><label><input type="checkbox" data-sesn="${i}" ${inSession.has(n) ? "checked" : ""}> in this session</label></td>` : ""}
        <td><input id="acpw-${i}" placeholder="new password" autocomplete="off" size="12"></td>
        <td><button data-acpw="${i}">Set password</button> <button data-acdel="${i}" class="stop">${armed(app, "del:" + n) ? "Press again" : "Delete"}</button></td></tr>`).join("")
        || "<tr><td class='note'>No accounts yet.</td></tr>"}</table>
      <div class="formgrid"><label>Username</label><input id="ac-name" maxlength="12" autocomplete="off">
        <label>Password</label><input id="ac-pw" autocomplete="off" placeholder="at least 6 characters"></div>
      <div class="row"><button id="ac-add">Make account</button></div>`;
}

function wireAccounts(app, body) {
    const S = app.state, T = S.teaching || {}, ses = S.session || {}, send = app.send;
    const names = [...new Set([...(T.accounts || []), ...(ses.all || [])])].sort((a, b) => a.localeCompare(b));
    body.querySelectorAll("button[data-acpw]").forEach(b => b.onclick = () => {
        const i = Number(b.dataset.acpw), pw = $("acpw-" + i).value;
        if (pw.length < 6) return app.toast("Passwords need at least 6 characters.");
        send({type: "set_password", learner: names[i], password: pw});
    });
    body.querySelectorAll("button[data-acdel]").forEach(b => b.onclick = () => {
        const n = names[Number(b.dataset.acdel)];
        twice(app, "del:" + n, `Delete ${n} and everything this game keeps about them?`, () => send({type: "delete_learner", learner: n}));
    });
    body.querySelectorAll("input[data-sesn]").forEach(c => c.onchange = () => send({type: "session_learner", learner: names[Number(c.dataset.sesn)], in: c.checked}));
    $("ac-add").onclick = () => {
        const n = $("ac-name").value.trim(), pw = $("ac-pw").value;
        if (!n) return app.toast("Type a username.");
        if (pw.length < 6) return app.toast("Passwords need at least 6 characters.");
        send({type: "add_learner", learner: n, password: pw});
        $("ac-name").value = $("ac-pw").value = "";
    };
}

function outcomesTab(app, body) {
    const S = app.state, T = S.teaching, send = app.send, L = S.lesson || {};
    if (!T) { body.innerHTML = "<p class='note'>Waiting for the server…</p>"; return; }
    const n = T.lesson || L.lesson_number || 1;
    const outs = T.outcomes || {};
    const codes = Object.keys(outs);
    const edited = T.edited || {};
    const thisLesson = edited[String(n)] || {};
    const taught = new Set(Object.values(thisLesson).flatMap(o => o[3] || []));
    const grid = T.grid || {};
    const names = Object.keys(grid);
    const teacherChecked = Object.entries(thisLesson).filter(([, o]) => o[4] === "teacher");
    const E = S.editLesson || n;
    const objs = Object.entries(edited[String(E)] || {});
    const hidden = new Set(((T.edits || {}).hidden) || []);
    body.innerHTML = `
      <h2>Outcomes shown (mission ${esc(n)})</h2>
      <div class="scrollx"><table><tr><th>Learner</th>${codes.map(c => `<th title="${esc(outs[c][0])}: ${esc(outs[c][1])}" class="${taught.has(c) ? "taught" : ""}">${esc(c)}</th>`).join("")}</tr>
        ${names.map(nm => `<tr><td>${esc(nm)}</td>${codes.map(c => { const k = (grid[nm].outcomes || {})[c] || 0; return `<td class="num ${k ? "ok" : ""}">${k || ""}</td>`; }).join("")}</tr>`).join("")
          || `<tr><td class="note" colspan="${codes.length + 1}">Nobody yet.</td></tr>`}</table></div>
      <div class="note">Highlighted codes are what this mission teaches. Hover a code for its name.</div>
      <h2>Teacher-checked objectives (mission ${esc(n)})</h2>
      ${teacherChecked.map(([id, o]) => `<div class="objective"><b>${esc(id)}</b> ${esc(o[1])}<div class="row">${names.map(nm => {
            const done = (grid[nm].missions || []).includes(id);
            return `<button data-tick="${esc(id)}" data-who="${esc(nm)}" class="${done ? "go" : ""}" ${done ? "disabled" : ""}>${done ? "✓ " : ""}${esc(nm)}</button>`;
        }).join("") || "<span class='note'>No learners.</span>"}</div></div>`).join("") || "<p class='note'>None in this mission.</p>"}
      <div class="row"><button id="btn-export-csv">Download the evidence (CSV)</button></div>
      <h2>Edit the missions</h2>
      <div class="row">${[1, 2, 3, 4, 5].map(k => `<button data-elesson="${k}" class="${k === E ? "on" : ""}">${k}</button>`).join("")}
        <button id="btn-show-missions" class="${L.show_missions ? "on" : ""}">${L.show_missions ? "Showing learners: stop" : "Show learners"}</button>
        <button id="btn-missions-reset" class="stop">${armed(app, "mreset") ? "Press again" : "Reset all to standard"}</button></div>
      <div class="note">Show learners pauses the class and opens every learner's Mission tab. Objectives you add are checked by you: tick them above.</div>
      ${objs.map(([id, o]) => `<div class="objective">
          <div class="row"><b>${esc(id)}</b> <span class="note">${esc((o[3] || []).join(" "))} · ${esc(o[4])}</span>
            <label><input type="checkbox" data-see="${esc(id)}" ${hidden.has(id) ? "" : "checked"}> learners see it</label></div>
          <input id="ot-${esc(id)}" class="wide" value="${esc(o[1])}">
          <textarea id="ox-${esc(id)}" rows="3" class="wide">${esc(o[2])}</textarea>
          <div class="row"><button data-osave="${esc(id)}">Save</button><button data-oauto="${esc(id)}" title="An AI card asking Claude to write this objective's automatic check: send it to Claude from the AI cards tab">Automate</button><button data-oremove="${esc(id)}" class="stop">${armed(app, "orm:" + id) ? "Press again" : "Remove"}</button></div></div>`).join("")}
      <h3>Add an objective to mission ${esc(E)}</h3>
      <input id="oa-title" class="wide" placeholder="title"><textarea id="oa-text" rows="3" class="wide" placeholder="what to do"></textarea>
      <div class="row"><button id="oa-add">Add</button></div>
      <h3>As a file</h3>
      <div class="row"><button id="btn-missions-export">Download the missions file</button>
        <label class="filebtn">Load an edited missions file<input id="missions-import" type="file" accept=".json,application/json" hidden></label></div>`;
    body.querySelectorAll("button[data-tick]").forEach(b => b.onclick = () => send({type: "tick", learner: b.dataset.who, mission: b.dataset.tick}));
    $("btn-export-csv").onclick = () => send({type: "export"});
    body.querySelectorAll("button[data-elesson]").forEach(b => b.onclick = () => { S.editLesson = Number(b.dataset.elesson); app.renderPanel(); });
    $("btn-show-missions").onclick = () => send({type: "lesson", lesson: {show_missions: !L.show_missions}});
    $("btn-missions-reset").onclick = () => twice(app, "mreset", "Put every mission back to its standard words?", () => send({type: "missions_edit", do: "reset"}));
    body.querySelectorAll("input[data-see]").forEach(c => c.onchange = () => send({type: "missions_edit", do: c.checked ? "show" : "hide", id: c.dataset.see}));
    body.querySelectorAll("button[data-osave]").forEach(b => b.onclick = () => {
        const id = b.dataset.osave;
        send({type: "missions_edit", do: "change", id, title: $("ot-" + id).value, text: $("ox-" + id).value});
        app.toast(`Saved ${id}`);
    });
    // AUTOMATE (the window's automate_objective): an AI card, target the game, asking Claude to write the check
    body.querySelectorAll("button[data-oauto]").forEach(b => b.onclick = () => {
        const id = b.dataset.oauto, o = (objs.find(([k]) => k === id) || [id, [E, "", "", [], "teacher"]])[1];
        const title = $("ot-" + id).value, text = $("ox-" + id).value, unit = app.game.word;
        const asked = o[4] === "teacher" ? "Automate the check for" : "Check that the automatic check still fits the wording of, and fix it if not,";
        send({type: "ai_card", card: {
            goal: `${asked} Mission ${E} objective ${id}, '${title}'. The game should tick it for a learner by itself, as the other objectives are checked by their id in the teaching module (build_checks when they build, tick_checks every half second, brain_checks for brains), when they do this: ${text} If it can't be checked automatically, say why and suggest wording that could be.`,
            variables: `The objective's id is ${id}. self.complete(p.name, '${id}', detail) marks it done with a detail saying what the learner did (their ${unit}'s values before and after).`,
            test: `Log in as a learner on a laptop test server, do objective ${id} as the text says, and watch the Mission tab: it should show DONE with the detail within a few seconds. Also check it does not tick when the learner has not done it.`,
            predict: `Objective ${id} ticks itself a moment after a learner does it, with no click from the teacher.`,
            privacy: true, review: true, credit: true, target: "game"}});
        app.toast(`Automate ${id}: an AI card is waiting in the AI cards tab: send it to Claude there.`, false, 8000);
    });
    body.querySelectorAll("button[data-oremove]").forEach(b => b.onclick = () => {
        const id = b.dataset.oremove;
        twice(app, "orm:" + id, `Take ${id} out of the mission?`, () => send({type: "missions_edit", do: "remove", id}));
    });
    $("oa-add").onclick = () => {
        const title = $("oa-title").value.trim(), text = $("oa-text").value.trim();
        if (!title) return app.toast("Give the objective a title.");
        send({type: "missions_edit", do: "add", lesson: E, title, text});
        $("oa-title").value = $("oa-text").value = "";
    };
    $("btn-missions-export").onclick = () => send({type: "missions_export"});
    $("missions-import").onchange = async e => {
        const f = e.target.files[0];
        if (!f) return;
        try { send({type: "missions_import", data: JSON.parse(await f.text())}); } catch (err) { app.toast("That file isn't a missions file (JSON)."); }
    };
}

const STATUS_WORDS = {waiting: "waiting for you", sent: "sent to the AI", working: "with Claude", ready: "kept: the learner tries it",
                      reviewed: "reviewed by the learner", rejected: "sent back"};
const NOTES = {working: "The teacher sent this to Claude",
               ready: "Kept. Try it, then answer the review questions. AI tool: Claude, used by the teacher.",
               rejected: "Please make the goal and test clearer, then send it again"};
const WORKING = "Claude is working...";

// ---------- Claude for the browser (CHANGE 136): the window's Send to Claude, Keep, Undo and Changes ----------
// Claude runs on a computer of the teacher's (helper/claude_helper.py, logged in to the desk), with that computer's
// own Claude login; the page sends it the card through the desk, and passes kept mods on to the class server here
// exactly as the window does (mods_update, mod_makers, card_status).
function claudeOf(app) {
    const desk = app.state.desk;
    return desk && app.game ? desk.claudeFor(app.game.id) : null;
}

function noClaude(app) {
    return app.state.desk
        ? `Claude's computer isn't connected. On the computer with Claude Code (your laptop), start <b>Claude for the browser</b>
           (club-coders\\Claude for the browser.bat): it logs in to this desk, and Send to Claude, Keep and Undo appear here.`
        : "Send to Claude works when this page is logged in through the club's desk (and Claude for the browser is running).";
}

function targetWord(app, C, key) {  // (the window's words: Their robot, The arena, The rules, The whole game)
    const keys = (C && C.targets) || [];
    return key === "game" ? "The whole game" : key === "rules" ? "The rules" : key === keys[0] ? `Their ${app.game.word}` : `The ${key}`;
}

function cardTarget(app, c, C) {
    const S = app.state, keys = (C && C.targets) || [];
    const t = (S.cardTargets || {})[c.id] || (c.card || {}).target;
    return keys.includes(t) ? t : keys[0] || t;
}

function asUserMod(app, c) {
    return ((app.state.cardUserMod || {})[c.id]) !== false;
}

function targetsRow(app, c, C) {
    const target = cardTarget(app, c, C);
    return `<div class="row">${(C.targets || []).map(k => `<button data-ctarget="${esc(k)}" data-cid="${c.id}" class="${k === target ? "on" : ""}">${esc(targetWord(app, C, k))}</button>`).join("")}</div>` +
        (target === "game" ? `<label class="check"><input type="checkbox" data-cusermod="${c.id}" ${asUserMod(app, c) ? "checked" : ""}> Make it a switchable User Mod (off until you switch it on in Controls)</label>` : "");
}

function diffHtml(diff) {  // added lines green, removed red, as the window's preview
    return `<pre class="diff">${String(diff).split("\n").map(ln => {
        const cls = ln.startsWith("+++") || ln.startsWith("---") ? "file" : ln.startsWith("+") ? "add" : ln.startsWith("-") ? "del" : ln.startsWith("@@") ? "hunk" : "";
        return cls ? `<span class="${cls}">${esc(ln)}</span>` : esc(ln);
    }).join("\n")}</pre>`;
}

function claudeCard(app, c, C) {
    const S = app.state, job = (C.jobs || {})[String(c.id)], res = job && job.result;
    if (job && (job.status === WORKING || job.status.startsWith("Waiting"))) {
        const took = Math.max(0, Math.round(Date.now() / 1000 - job.started));
        return job.status === WORKING
            ? `<p class="claudework">Claude is working on it (${esc(targetWord(app, C, job.target))}), ${took} s so far: usually under a minute, a few minutes for whole-game changes, then it is tested...</p>`
            : `<p class="note">${esc(job.status)}</p>`;
    }
    if (res) {
        const files = res.files || [], good = res.test_ok && files.length;
        let html = `<pre class="claude ${good ? "ok" : "bad"}">${esc(String(res.summary || "").slice(0, 1500))}\n${res.test_ok ? "Test: passed" : "Test: FAILED - " + esc(String(res.test || "").slice(-300))}` +
                   `${(res.blocked || []).length ? "\nThrown away (outside the allowed files): " + esc(res.blocked.join(", ")) : ""}</pre>`;
        if (files.length) html += `<p class="note">Changed: ${esc(files.join(", "))}</p>`;
        if (res.diff) html += `<div class="row"><button data-cdiff="${c.id}">${S.cardDiff === c.id ? "Hide the changes" : "Show the changes"}</button></div>` + (S.cardDiff === c.id ? diffHtml(res.diff) : "");
        if (job.status === "Check it" && files.length) {
            html += `<div class="row"><button class="go" data-ckeep="${c.id}">Keep</button><button class="stop" data-cundo="${c.id}">Undo</button></div>`;
        } else if (job.status === "Check it" || job.status === "Failed") {  // nothing changed: try again, maybe as a game change
            if (res.needs_game) html += `<div class="row"><button data-cretry="${c.id}" data-target="game">Allow the whole game: check and send again</button></div>`;
            html += `<p class="warn">Nothing was changed. Choose what Claude may change and send again:</p>${targetsRow(app, c, C)}
                     <div class="row"><button data-cretry="${c.id}">Check and send again</button><button data-cst="rejected" data-cid="${c.id}" class="stop">Reject</button></div>`;
        } else if (job.status === "Kept" && res.code_changed) {
            html += `<p class="warn">Kept on ${esc(C.machine)} only. For the class: Make my changes live.bat on that computer (then Restart
                     server). A user mod then appears in Controls, to switch on.</p>`;
        }
        return html;
    }
    if (["waiting", "sent", "working"].includes(c.status)) {
        return targetsRow(app, c, C) + `<div class="row"><button class="go" data-ccheck="${c.id}">Check and send</button>
                 <button data-cprompt="${c.id}">Copy prompt</button><button data-cst="rejected" data-cid="${c.id}" class="stop">Reject</button></div>`;
    }
    return "";
}

function promptArgs(app, c, C) {
    const target = cardTarget(app, c, C);
    return {card: c.card || {}, learner: c.learner, target, as_user_mod: target === "game" && asUserMod(app, c)};
}

// before anything goes to Claude: the whole card and the whole prompt, on screen (the window's CHECK BEFORE SENDING)
function checkView(app, c, C) {
    const S = app.state, k = c.card || {}, args = promptArgs(app, c, C), key = JSON.stringify([c.id, args]);
    if (!S.cardPrompt || S.cardPrompt.key !== key) {
        S.cardPrompt = {key, text: null};
        app.state.desk.claudeAsk(app.game.id, "prompt", args).then(r => { if (S.cardPrompt.key === key) { S.cardPrompt.text = r.prompt; app.renderPanel(); } },
                                                                 e => { if (S.cardPrompt.key === key) { S.cardPrompt.text = `(${e.message})`; app.renderPanel(); } });
    }
    const ticks = [["privacy", "no personal information"], ["review", "will review and test the code"], ["credit", "will say where AI helped"]]
        .filter(([q]) => k[q]).map(([, t]) => t);
    return `<h2>Check before sending   #${esc(c.id)} ${esc(c.learner)}</h2>
      ${[["goal", "Idea"], ["variables", "Variables and values"], ["test", "How they will test it"], ["predict", "Their prediction"]]
          .map(([q, t]) => `<p><b>${t}:</b> ${esc(k[q] || "")}</p>`).join("")}
      <p class="note">Ticked: ${esc(ticks.join(", ") || "nothing")}</p>
      <div class="row"><button class="go" id="c-send" ${S.cardPrompt.text === null ? "disabled" : ""}>Send to Claude</button>
        <button data-cprompt="${c.id}">Copy prompt</button><button id="c-back">Back</button></div>
      <h2>The whole prompt   (${esc(targetWord(app, C, args.target))})</h2>
      <pre class="prompt">${S.cardPrompt.text === null ? "Asking Claude's computer for the prompt…" : esc(S.cardPrompt.text)}</pre>`;
}

function cardsTab(app, body) {
    const S = app.state, T = S.teaching || {}, L = S.lesson || {}, send = app.send, game = app.game, desk = S.desk;
    const C = claudeOf(app);
    const all = (T.cards || []).slice().reverse();
    const cards = S.allCards ? all : all.filter(c => !["reviewed", "rejected"].includes(c.status));
    const checking = C && all.find(c => c.id === S.cardCheck);
    if (checking) {
        body.innerHTML = checkView(app, checking, C);
    } else {
        if (C === null) S.cardCheck = null;
        body.innerHTML = `
      <h2>AI cards</h2>
      ${C ? `<div class="note">Choose what Claude may change, then Send to Claude: it runs on ${esc(C.machine)}, with that computer's own
          Claude login. The whole game lets Claude change anything (new weapons, hazards, rules, graphics). Every change is tested
          before you Keep it, and kept changes can be switched off later in the Changes tab.</div>`
          : `<p class="warn">${noClaude(app)}</p><div class="note">Meanwhile you can read every card, send it back, mark where it is,
          copy it for Claude, and put a kept change's file on the server.</div>`}
      <div class="formgrid"><label>On the learners' cards</label><input id="card-note" maxlength="300" value="${esc(L.ai_card_note || "")}" placeholder="a line from you on every learner's card"></div>
      <div class="row"><button id="card-note-save">Save the line</button>
        <button id="cards-all" class="${S.allCards ? "on" : ""}">${S.allCards ? "Showing every card" : "Showing open cards"}</button></div>
      ${cards.map(c => {
          const k = c.card || {}, job = C && (C.jobs || {})[String(c.id)];
          return `<div class="card">
            <div class="row"><b>#${esc(c.id)} ${esc(c.learner)}</b><span class="note">${esc(c.time)} · ${esc(k.target)} · ${esc(job ? job.status : STATUS_WORDS[c.status] || c.status)}</span></div>
            <p><b>Goal:</b> ${esc(k.goal)}</p>${k.variables ? `<p><b>Variables:</b> ${esc(k.variables)}</p>` : ""}
            <p><b>Test:</b> ${esc(k.test)}</p>${k.predict ? `<p><b>Prediction:</b> ${esc(k.predict)}</p>` : ""}
            <p class="note">${k.privacy ? "✓" : "✗"} no personal details · ${k.review ? "✓" : "✗"} will review · ${k.credit ? "✓" : "✗"} will credit the AI</p>
            ${c.note ? `<p class="note">Your note: ${esc(c.note)}</p>` : ""}
            ${c.review ? `<p class="note">Their review: ${Object.entries(c.review).map(([q, a]) => `<b>${esc(q)}</b> ${esc(a)}`).join(" · ")}</p>` : ""}
            <input id="cn-${c.id}" class="wide" maxlength="200" placeholder="a note for the learner (optional)">
            ${C ? claudeCard(app, c, C)
                : `<div class="row"><button data-cst="working" data-cid="${c.id}">With Claude</button><button data-cst="ready" data-cid="${c.id}" class="go">Kept</button>
              <button data-cst="rejected" data-cid="${c.id}" class="stop">Send back</button><button data-ccopy="${c.id}">Copy for Claude</button></div>`}</div>`;
      }).join("") || "<p class='note'>No cards.</p>"}
      ${C ? "" : `<h2>Put a kept change on the server</h2>
      <div class="note">After Keep on your laptop, a change to these files can go straight to the class: choose which file and
        load it from your laptop. The server checks it before using it.</div>
      <div class="formgrid"><label>File</label><select id="mod-path">${game.mods.map(m => `<option>${esc(m)}</option>`).join("")}</select>
        <label>Learner's username</label><input id="mod-user" placeholder="for a learner's own file"></div>
      <div class="row"><label class="filebtn">Choose the file and send it<input id="mod-file" type="file" accept=".py,text/plain" hidden></label></div>`}`;
    }
    const card = id => (T.cards || []).find(x => String(x.id) === String(id));
    const note = (id, status) => { const el = $("cn-" + id); return (el && el.value.trim()) || NOTES[status]; };
    const ask = (what, args) => desk.claudeAsk(game.id, what, args);
    const fail = e => app.toast(e.message, false, 6000);
    if ($("card-note-save")) $("card-note-save").onclick = () => send({type: "lesson", lesson: {ai_card_note: $("card-note").value}});
    if ($("cards-all")) $("cards-all").onclick = () => { S.allCards = !S.allCards; app.renderPanel(); };
    body.querySelectorAll("button[data-cst]").forEach(b => b.onclick = () => {
        const id = Number(b.dataset.cid), status = b.dataset.cst;
        send({type: "card_status", id, status, note: note(id, status)});
    });
    body.querySelectorAll("button[data-ccopy]").forEach(b => b.onclick = async () => {
        const c = card(b.dataset.ccopy);
        if (!c) return;
        const k = c.card || {};
        const text = `A learner (${c.learner}) asks for a change to ${game.title} (${k.target}).\nGoal: ${k.goal}\nVariables: ${k.variables}\n` +
                     `How they will test it: ${k.test}\nTheir prediction: ${k.predict}\nKeep the change small and explain it in comments a learner can follow.`;
        try { await navigator.clipboard.writeText(text); app.toast("Copied: paste it into Claude."); } catch (e) { app.toast("This browser wouldn't copy it."); }
    });
    if ($("mod-file")) $("mod-file").onchange = async e => {
        const f = e.target.files[0];
        if (!f) return;
        let path = $("mod-path").value;
        if (path.includes("<username>")) {
            const user = $("mod-user").value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
            if (!user) return app.toast("Type the learner's username for their file.");
            path = path.replace("<username>", user);
        }
        send({type: "mods_update", files: {[path]: await f.text()}});
    };
    if (!C) return;
    // what Claude may change, and whether a whole-game change is a user mod
    body.querySelectorAll("button[data-ctarget]").forEach(b => b.onclick = () => {
        S.cardTargets = Object.assign(S.cardTargets || {}, {[b.dataset.cid]: b.dataset.ctarget});
        app.renderPanel();
    });
    body.querySelectorAll("input[data-cusermod]").forEach(b => b.onchange = () => {
        S.cardUserMod = Object.assign(S.cardUserMod || {}, {[b.dataset.cusermod]: b.checked});
        app.renderPanel();
    });
    body.querySelectorAll("button[data-ccheck]").forEach(b => b.onclick = () => { S.cardCheck = Number(b.dataset.ccheck); app.renderPanel(); });
    body.querySelectorAll("button[data-cprompt]").forEach(b => b.onclick = () => {  // (the same prompt Send uses)
        const c = card(b.dataset.cprompt);
        if (c) ask("prompt", promptArgs(app, c, C)).then(async r => {
            try { await navigator.clipboard.writeText(r.prompt); app.toast(`Prompt #${c.id} copied: paste it into Claude`); } catch (e) { app.toast("This browser wouldn't copy it."); }
        }, fail);
    });
    body.querySelectorAll("button[data-cdiff]").forEach(b => b.onclick = () => {
        S.cardDiff = S.cardDiff === Number(b.dataset.cdiff) ? null : Number(b.dataset.cdiff);
        app.renderPanel();
    });
    body.querySelectorAll("button[data-cretry]").forEach(b => b.onclick = () => {  // (send again: its prompt is shown first)
        const id = Number(b.dataset.cretry);
        if (b.dataset.target) S.cardTargets = Object.assign(S.cardTargets || {}, {[id]: b.dataset.target});
        ask("clear", {id}).then(() => { S.cardCheck = id; app.renderPanel(); }, fail);
    });
    body.querySelectorAll("button[data-ckeep]").forEach(b => b.onclick = () => {
        const id = Number(b.dataset.ckeep);
        b.disabled = true;
        ask("keep", {id}).then(r => {
            if (Object.keys(r.makers || {}).length) send({type: "mod_makers", makers: r.makers, new: true});  // (a new user mod: the learner's name in front)
            if (Object.keys(r.mods || {}).length) send({type: "mods_update", files: r.mods});
            send({type: "card_status", id, status: "ready", note: "Kept. " + ((r.engine || []).length ? "It is in the game after the restart. " : "") +
                                                                  "Try it, then answer the review questions. AI tool: Claude, used by the teacher."});
        }, e => { b.disabled = false; fail(e); });
    });
    body.querySelectorAll("button[data-cundo]").forEach(b => b.onclick = () => {
        const id = Number(b.dataset.cundo);
        b.disabled = true;
        ask("undo", {id}).then(() => send({type: "card_status", id, status: "rejected",
                                           note: "The teacher undid this change. Try making your request clearer."}),
                              e => { b.disabled = false; fail(e); });
    });
    if (checking) {
        $("c-back").onclick = () => { S.cardCheck = null; app.renderPanel(); };
        $("c-send").onclick = () => {
            $("c-send").disabled = true;
            const learner = (S.classList || []).find(p => p.name === checking.learner);
            ask("send", {id: checking.id, design: learner ? learner.design : null, ...promptArgs(app, checking, C)}).then(() => {
                S.cardCheck = null;  // (back to the list of requests, where its progress shows)
                send({type: "card_status", id: checking.id, status: "working", note: NOTES.working});
                app.renderPanel();
            }, e => { $("c-send").disabled = false; fail(e); });
        };
    }
}

// Claude for the browser said something: the class server hears who made each user mod, as the window tells it
// when it connects (and a name the server took off, for a deleted learner, comes off Claude's computer's list too)
export function claudeChanged(app, fromLesson = false) {
    const S = app.state, C = claudeOf(app);
    if (C && C.makers && S.role === "teacher" && S.connected) {
        const named = Object.fromEntries(Object.entries(C.makers).filter(([, who]) => who));
        const key = JSON.stringify(named);
        if (Object.keys(named).length && key !== S.makersSent) {
            S.makersSent = key;
            app.send({type: "mod_makers", makers: named, new: false});
        }
        const gone = Object.entries((S.mods || {}).makers || {}).filter(([k, who]) => who === "" && C.makers[k]).map(([k]) => k);
        if (gone.length && JSON.stringify(gone) !== S.makersGone) {
            S.makersGone = JSON.stringify(gone);
            S.desk.claudeAsk(app.game.id, "forget_makers", {keys: gone}).catch(() => {});
        }
    }
    if (!fromLesson && ["cards", "changes"].includes(S.tab)) app.renderPanel();
}

// the window's Changes tab: the kept changes as mods, switched off and on, merged into the game, or removed
function changesTab(app, body) {
    const S = app.state, game = app.game, C = claudeOf(app), send = app.send;
    if (!C || !C.history) {
        body.innerHTML = `<h2>Mods</h2><p class="warn">${noClaude(app)}</p>`;
        return;
    }
    const mods = C.history.filter(e => e.status !== "merged"), merged = C.history.filter(e => e.status === "merged");
    const count = C.merged_count || merged.length;
    const world = (C.targets || [])[1] || "world";
    body.innerHTML = `<h2>Mods</h2>
      <div class="note">Changes made with Claude, newest first (kept on ${esc(C.machine)}). Switch a mod off if it causes problems, and on
        again to bring it back. Merge into game makes it a permanent part of the game.</div>
      ${mods.map(e => {
          const on = e.status === "kept";
          return `<div class="card"><div class="row"><button data-mswitch="${e.n}" data-how="${on ? "rollback" : "reapply"}" class="${on ? "go" : ""}">${on ? "ON" : "OFF"}</button>
              <b>${e.n}. ${esc(String(e.goal || "").slice(0, 80))}</b></div>
            <p class="note">Designed by ${esc(e.learner)} (${esc(targetWord(app, C, e.target))}, ${esc(String(e.time || "").slice(5))})</p>
            <p class="note">Files: ${esc((e.files || []).join(", "))}</p>
            <div class="row"><button data-mdiff="${e.n}">${S.changeView === e.n ? "Hide" : "Show changes"}</button>
              ${on ? `<button class="go" data-mmerge="${e.n}">Merge into game</button>` : `<button class="stop" data-mforget="${e.n}">Remove</button>`}</div>
            ${S.changeView === e.n ? (S.changeDiff && S.changeDiff.n === e.n ? diffHtml(S.changeDiff.diff || "(no changes)") : "<p class='note'>Asking for the changes…</p>") : ""}</div>`;
      }).join("") || "<p class='note'>No mods waiting: kept AI changes appear here.</p>"}
      ${count ? `<h2>Merged into the game (${count})</h2>` + merged.slice(0, 3).map(e => `<p class="note">${e.n}. ${esc(String(e.goal || "").slice(0, 60))} - designed by ${esc(e.learner)}, merged ${esc(String(e.merged || "").slice(5))}</p>`).join("") +
                 (count > 3 ? `<p class="note">and ${count - 3} earlier</p>` : "") : ""}
      ${S.changeMsg ? `<p class="${S.changeMsg.ok ? "ok" : S.changeMsg.clash ? "warn" : "bad"}">${esc(S.changeMsg.text)}</p>` : ""}
      ${restartRow(app)}`;
    const ask = (what, n) => S.desk.claudeAsk(game.id, what, {n});
    const say = (text, ok = true, clash = false) => { S.changeMsg = {text, ok, clash}; app.renderPanel(); };
    body.querySelectorAll("button[data-mswitch]").forEach(b => b.onclick = () => {
        const n = Number(b.dataset.mswitch), how = b.dataset.how;
        ask(how, n).then(r => {
            if (Object.keys(r.mods || {}).length) send({type: "mods_update", files: r.mods});
            say(`Mod ${n} ${how === "rollback" ? "switched off" : "switched on"}. ` + ((r.engine || []).length
                ? `Its code reaches the class with Make my changes live on ${C.machine} (then Restart server).`
                : `The ${world}, rules and ${game.word}s have been updated.`));
        }, e => say(e.message, false, /changed again since/.test(e.message)));
    });
    body.querySelectorAll("button[data-mdiff]").forEach(b => b.onclick = () => {
        const n = Number(b.dataset.mdiff);
        S.changeView = S.changeView === n ? null : n;
        if (S.changeView === n && !(S.changeDiff && S.changeDiff.n === n)) ask("diff", n).then(r => { S.changeDiff = r; app.renderPanel(); }, e => say(e.message, false));
        app.renderPanel();
    });
    body.querySelectorAll("button[data-mmerge]").forEach(b => b.onclick = () => {
        const n = Number(b.dataset.mmerge);
        ask("merge", n).then(r => {
            if (Object.keys(r.makers || {}).length) send({type: "mod_makers", makers: r.makers, new: true});  // (the learner's name in front)
            if (S.changeView === n) S.changeView = null;
            say(`Mod ${n} is now a permanent part of the game.`);
        }, e => say(e.message, false));
    });
    body.querySelectorAll("button[data-mforget]").forEach(b => b.onclick = () => {
        const n = Number(b.dataset.mforget);
        ask("forget", n).then(() => { if (S.changeView === n) S.changeView = null; say(`Mod ${n} was removed from the list (the game is as it was without it).`); },
                              e => say(e.message, false));
    });
    wireRestartRow(app, body);
}

function rulesTab(app, body) {
    const S = app.state, L = S.lesson, R = S.rules || {}, send = app.send, mods = S.mods || {};
    if (!L) { body.innerHTML = "<p class='note'>Waiting for the lesson…</p>"; return; }
    const lessonSend = patch => send({type: "lesson", lesson: patch});
    const tools = L.tools || {};
    const flags = Object.entries(tools).filter(([, v]) => typeof v === "boolean");
    const lists = Object.entries(tools).filter(([, v]) => Array.isArray(v));
    const haz = L.hazards || {};
    const userMods = {...((S.roster && S.roster.user_mods) || {}), ...(L.user_mods || {})};
    const inVote = (which, k) => (L[which] || {})[k] !== false;
    const voters = (which, k) => (mods[which] || {})[k] || [];
    const votes = (which, k) => voters(which, k).length;
    const whoVoted = (which, k) => votes(which, k) ? ` (${votes(which, k)}: ${esc(voters(which, k).join(", "))})` : "";
    const limits = L.limits || {}, full = R.full || {};
    const pair = (group, k) => ((limits[group] || {})[k]) || ((full[group] || {})[k]) || [0, 100];
    body.innerHTML = `
      <h2>What learners can see and change</h2>
      <div class="ticks">${flags.map(([k, v]) => `<label><input type="checkbox" data-tool="${esc(k)}" ${v ? "checked" : ""}> ${esc(pretty(k))}</label>`).join("")}</div>
      ${lists.map(([k, v]) => `<div class="row"><label>${esc(pretty(k))} allowed</label>${Object.keys(R[k] || {}).map(o =>
          `<button data-list="${esc(k)}" data-item="${esc(o)}" class="${v.includes(o) ? "on" : ""}">${esc(pretty(o))}</button>`).join("")}</div>`).join("")}
      <h2>Hazards</h2>
      <div class="ticks">${Object.entries(haz).filter(([, v]) => typeof v === "boolean").map(([k, v]) =>
          `<label><input type="checkbox" data-haz="${esc(k)}" ${v ? "checked" : ""}> ${esc(pretty(k))}
             <small><input type="checkbox" data-avote="${esc(k)}" ${inVote("arena_in_vote", k) ? "checked" : ""}> in the vote${whoVoted("arena_votes", k)}</small></label>`).join("") || "<span class='note'>None in this game.</span>"}</div>
      <div class="row"><button data-voteall="arena_in_vote" data-on="1">All in the vote</button><button data-voteall="arena_in_vote" data-on="0">None in the vote</button></div>
      ${R.house ? `<div class="row"><label>Resident Robots</label>${Object.keys(R.house).map(n => {
          const on = haz.house_robots === true || (Array.isArray(haz.house_robots) && haz.house_robots.includes(n));
          return `<button data-house="${esc(n)}" class="${on ? "on" : ""}">${esc(n)}</button>`; }).join("")}</div>` : ""}
      <h2>User mods</h2>
      <div class="ticks">${Object.entries(userMods).map(([k, v]) => {
          const maker = (mods.makers || {})[k], info = modInfo(app, k);
          return `<label title="${esc(info.text)}"><input type="checkbox" data-umod="${esc(k)}" ${v ? "checked" : ""}> ${esc(maker ? `${maker}'s ` : "")}${esc(info.title)}
            <small><input type="checkbox" data-mvote="${esc(k)}" ${inVote("mods_in_vote", k) ? "checked" : ""}> in the vote${whoVoted("votes", k)}</small>
            ${info.text ? `<div class="note">${esc(info.text)}</div>` : ""}</label>`;
      }).join("") || "<span class='note'>No user mods in this game yet.</span>"}</div>
      ${Object.keys(userMods).length ? `<div class="row"><button data-voteall="mods_in_vote" data-on="1">All in the vote</button><button data-voteall="mods_in_vote" data-on="0">None in the vote</button></div>` : ""}
      <h2>Limits</h2>
      <div class="note">The lowest and highest each learner may choose, and the points to share. Builds outside are pulled back in.</div>
      <table><tr><th></th><th>lowest</th><th>highest</th></tr>
        ${Object.keys(full.points || {}).map(k => { const [lo, hi] = pair("points", k); return `<tr><td>${esc(pretty(k))}</td><td><input type="number" id="lim-p-${k}-0" value="${lo}" size="4"></td><td><input type="number" id="lim-p-${k}-1" value="${hi}" size="4"></td></tr>`; }).join("")}
        ${Object.keys(full.settings || {}).map(k => { const [lo, hi] = pair("settings", k); return `<tr><td>${esc(pretty(k))}</td><td><input type="number" id="lim-s-${k}-0" value="${lo}" size="4"></td><td><input type="number" id="lim-s-${k}-1" value="${hi}" size="4"></td></tr>`; }).join("")}
        <tr><td>Points to share</td><td colspan="2"><input type="number" id="lim-total" value="${limits.points_total ?? R.points_total ?? 100}" size="4"></td></tr></table>
      <div class="row"><button id="lim-save" class="go">Save the limits</button><button id="lim-standard">Standard limits (50)</button></div>`;
    body.querySelectorAll("input[data-tool]").forEach(c => c.onchange = () => lessonSend({tools: {[c.dataset.tool]: c.checked}}));
    body.querySelectorAll("button[data-list]").forEach(b => b.onclick = () => {
        const k = b.dataset.list, cur = new Set(tools[k] || []);
        if (cur.has(b.dataset.item)) cur.delete(b.dataset.item); else cur.add(b.dataset.item);
        if (!cur.size) return app.toast("Leave at least one.");
        lessonSend({tools: {[k]: [...cur]}});
    });
    body.querySelectorAll("input[data-haz]").forEach(c => c.onchange = () => lessonSend({hazards: {[c.dataset.haz]: c.checked}}));
    body.querySelectorAll("button[data-voteall]").forEach(b => b.onclick = () => {  // (CHANGE 101: every item in or out at once)
        const which = b.dataset.voteall, on = b.dataset.on === "1";
        const keys = which === "mods_in_vote" ? Object.keys(userMods) : Object.keys(haz).filter(k => typeof haz[k] === "boolean");
        lessonSend({[which]: Object.fromEntries(keys.map(k => [k, on]))});
    });
    body.querySelectorAll("input[data-avote]").forEach(c => c.onchange = () => lessonSend({arena_in_vote: {[c.dataset.avote]: c.checked}}));
    body.querySelectorAll("input[data-umod]").forEach(c => c.onchange = () => lessonSend({user_mods: {[c.dataset.umod]: c.checked}}));
    body.querySelectorAll("input[data-mvote]").forEach(c => c.onchange = () => lessonSend({mods_in_vote: {[c.dataset.mvote]: c.checked}}));
    body.querySelectorAll("button[data-house]").forEach(b => b.onclick = () => {
        const all = Object.keys(R.house);
        const cur = new Set(haz.house_robots === true ? all : Array.isArray(haz.house_robots) ? haz.house_robots : []);
        if (cur.has(b.dataset.house)) cur.delete(b.dataset.house); else cur.add(b.dataset.house);
        lessonSend({hazards: {house_robots: [...cur]}});
    });
    $("lim-save").onclick = () => {
        const out = {settings: {}, points: {}, points_total: Number($("lim-total").value)};
        for (const k of Object.keys(full.points || {})) out.points[k] = [Number($(`lim-p-${k}-0`).value), Number($(`lim-p-${k}-1`).value)];
        for (const k of Object.keys(full.settings || {})) out.settings[k] = [Number($(`lim-s-${k}-0`).value), Number($(`lim-s-${k}-1`).value)];
        lessonSend({limits: out});
    };
    $("lim-standard").onclick = () => {
        const out = {settings: {}, points: {}, points_total: R.points_total ?? 100};
        for (const k of Object.keys(full.points || {})) out.points[k] = [R.stat_min ?? full.points[k][0], R.stat_max ?? full.points[k][1]];
        // (the window's standard, CHANGE 62: each setting from its lowest up to 50, size from 50 up to its highest)
        for (const k of Object.keys(full.settings || {})) {
            const [lo, hi] = R.settings && R.settings[k] ? R.settings[k].slice(0, 2) : full.settings[k];
            out.settings[k] = k === "size" ? [50, hi] : [lo, 50];
        }
        lessonSend({limits: out});
    };
}

function warningsTab(app, body) {
    const list = app.state.warnings || [];
    body.innerHTML = `<h2>Warnings</h2>
      <div class="note">A learner changed, in the code, a value this mission's garage doesn't let them change. Newest first.</div>
      <table>${list.slice().reverse().slice(0, 40).map(w => `<tr><td>${esc(w.time)}</td><td>${esc(w.who)}</td><td>${(w.changes || []).map(([k, a, b]) =>
          `${esc(k)} ${esc(a)} to ${esc(b)}`).join(", ")}</td></tr>`).join("") || "<tr><td class='note'>None.</td></tr>"}</table>`;
}
