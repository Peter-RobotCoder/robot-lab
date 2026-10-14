// The teacher tabs every game shares (CHANGE 130). Robot Lab, Fight Lab and Kart Lab all run the engine's teaching
// layer (engine/teaching.py), so these speak the same messages to all three: the Learners view (a learner's
// mission, building their design, their password; the game's own accounts), Outcomes (the grid, ticking
// teacher-checked objectives, the evidence CSV, the missions editor), AI cards, Rules (what learners can change,
// hazards, user mods and the vote, the limits) and Warnings. Built from what each game's server sends (its rules,
// lesson and class), not from a list per game, so a game's new tool or hazard shows up here by itself.

const $ = id => document.getElementById(id);

export const TEACHER_TABS = [["learners", "Learners"], ["outcomes", "Outcomes"], ["cards", "AI cards"],
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

// ---------- the design editor (a learner's, everyone's, the computer's, the teacher's own) ----------
const CHOICES = {weapon: "weapons", special: "specials", body: "bodies", fighting_style: "styles"};

function statsOf(base, rules) {
    return (rules.stats || []).map(k => [k, base.points ? (base.points[k] ?? 0) : (base[k] ?? 0)]);
}

function designForm(app, base, pre) {
    const R = app.state.rules || {};
    const full = R.full || {};
    const c = (base.colour || [200, 120, 40]).map(v => Math.max(0, Math.min(255, Math.round(v))));
    const hex = "#" + c.map(v => v.toString(16).padStart(2, "0")).join("");
    let html = `<div class="formgrid">
      <label>Name</label><input id="${pre}-name" maxlength="16" value="${esc(base.name || "")}">
      <label>Colour</label><input id="${pre}-colour" type="color" value="${hex}">`;
    for (const [key, list] of Object.entries(CHOICES)) {
        if (base[key] === undefined && !(key === "weapon" && R.weapons && base.fighting_style !== undefined)) continue;
        const opts = Object.keys(R[list] || {});
        if (!opts.length) continue;
        const blank = key === "weapon" && base.fighting_style !== undefined;  // (Fight Lab: only armed styles have one)
        html += `<label>${pretty(key)}</label><select id="${pre}-${key}">${blank ? `<option value="">none</option>` : ""}${opts.map(o =>
            `<option value="${esc(o)}" ${o === base[key] ? "selected" : ""}>${esc(pretty(o))}</option>`).join("")}</select>`;
    }
    if (Array.isArray(base.combo)) {
        html += `<label>Combo</label><input id="${pre}-combo" value="${esc(base.combo.join(", "))}" title="${esc(Object.keys(R.combo_moves || {}).join(", "))}">`;
    }
    html += `</div><h3>Points (${R.points_total ?? ""} to share)</h3><div class="formgrid">`;
    for (const [k, v] of statsOf(base, R)) {
        const range = (full.points || {})[k] || [R.stat_min ?? 0, R.stat_max ?? 100];
        html += `<label>${pretty(k)}</label><input id="${pre}-p-${k}" type="number" min="${range[0]}" max="${range[1]}" value="${v}">`;
    }
    html += `</div>`;
    if (base.settings && Object.keys(base.settings).length) {
        html += `<h3>Settings</h3><div class="formgrid">`;
        for (const [k, v] of Object.entries(base.settings)) {
            const range = (full.settings || {})[k] || (R.settings && R.settings[k] ? R.settings[k].slice(0, 2) : [0, 200]);
            html += `<label>${pretty(k)}</label><input id="${pre}-s-${k}" type="number" min="${range[0]}" max="${range[1]}" value="${v}">`;
        }
        html += `</div>`;
    }
    return html;
}

function readDesign(app, base, pre) {
    const R = app.state.rules || {};
    const d = JSON.parse(JSON.stringify(base || {}));
    const val = id => { const el = $(id); return el ? el.value : null; };
    d.name = (val(`${pre}-name`) || d.name || "").trim();
    const hex = val(`${pre}-colour`);
    if (hex) d.colour = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
    for (const key of Object.keys(CHOICES)) {
        const v = val(`${pre}-${key}`);
        if (v === null) continue;
        if (v === "") delete d[key]; else d[key] = v;
    }
    const combo = val(`${pre}-combo`);
    if (combo !== null) d.combo = combo.split(/[\s,]+/).filter(Boolean);
    for (const k of R.stats || []) {
        const v = val(`${pre}-p-${k}`);
        if (v === null) continue;
        if (d.points) d.points[k] = Number(v); else d[k] = Number(v);
    }
    for (const k of Object.keys(d.settings || {})) {
        const v = val(`${pre}-s-${k}`);
        if (v !== null) d.settings[k] = Number(v);
    }
    return d;
}

// ---------- the tabs ----------
export function renderTeacherTab(app, tab, body) {
    const fn = {learners: learnersTab, outcomes: outcomesTab, cards: cardsTab, rules: rulesTab, warnings: warningsTab}[tab];
    if (!fn) return false;
    fn(app, body);
    return true;
}

function learners(app) {  // the connected learners, from the lesson's class list
    return (app.state.classList || []).filter(p => p.role === "learner");
}

function learnersTab(app, body) {
    const S = app.state, game = app.game, send = app.send;
    const perf = (S.roster && S.roster.perf) || {};
    const people = S.classList || [];
    const extraHead = game.learnerHead ? game.learnerHead() : [];
    const rows = people.map(p => {
        const pf = perf[p.name] || {};
        const stalls = pf.stalls ?? "";
        const extra = game.learnerCells ? game.learnerCells(p) : [];
        return `<tr data-learner="${esc(p.name)}" class="${S.pick === p.name ? "picked" : ""}"><td>${esc(p.name)}</td><td>${esc(p.role)}</td>` +
               extra.map(c => `<td>${c}</td>`).join("") +
               `<td class="num">${pf.fps ?? ""}</td><td class="num">${pf.ping ?? ""}</td>` +
               `<td class="num ${Number(stalls) > 5 ? "bad" : ""}">${stalls}</td><td>${esc(pf.tier ?? "")}</td></tr>`;
    }).join("");
    const cpu = people.find(p => p.role === "computer");
    const picks = [...learners(app).map(p => [p.name, p.name]), ["*all", "All learners"],
                   ...(cpu ? [["*cpu", cpu.name]] : []), ["*me", `My ${game.word}`]];
    if (!S.pick) S.pick = learners(app)[0] ? learners(app)[0].name : "*all";
    body.innerHTML = `
      <h2>Who is here</h2>
      <table><tr><th>Name</th><th>Role</th>${extraHead.map(h => `<th>${esc(h)}</th>`).join("")}<th>fps</th><th>ping</th><th>stalls</th><th>graphics</th></tr>${rows}</table>
      <div class="note">fps, ping and stalls come from each window every few seconds. Stalls are frames over 100 ms apart: a few a
        minute is the Wi-Fi; dozens means that laptop or the room's network needs looking at. Click a name to look at them.</div>
      <h2>Look at</h2>
      <div class="row">${picks.map(([k, n]) => `<button data-pick="${esc(k)}" class="${S.pick === k ? "on" : ""}">${esc(n)}</button>`).join("")}</div>
      <div id="pickbody"></div>
      ${accountsHtml(app)}`;
    body.querySelectorAll("tr[data-learner]").forEach(tr => tr.onclick = () => { S.pick = tr.dataset.learner; S.sub = null; app.renderPanel(); });
    body.querySelectorAll("button[data-pick]").forEach(b => b.onclick = () => { S.pick = b.dataset.pick; S.sub = null; S.formBase = null; app.renderPanel(); });
    pickBody(app, $("pickbody"));
    wireAccounts(app, body);
}

function pickBody(app, box) {
    const S = app.state, send = app.send, game = app.game, L = S.lesson || {};
    const people = S.classList || [];
    if (S.pick === "*all" || S.pick === "*me" || S.pick === "*cpu") {
        const cpu = people.find(p => p.role === "computer");
        const me = people.find(p => p.role === "teacher");
        const base = S.formBase || (S.pick === "*cpu" ? (cpu && cpu.design) : S.pick === "*me" ? (S.myDesign || (me && me.design))
                     : ((learners(app)[0] || me || {}).design)) || {};
        const label = S.pick === "*all" ? "BUILD FOR ALL LEARNERS" : S.pick === "*cpu" ? `BUILD THE ${(cpu ? cpu.name : "computer").toUpperCase()}` : `BUILD MY ${game.word.toUpperCase()}`;
        box.innerHTML = `<h2>${S.pick === "*all" ? "Build for every learner" : S.pick === "*cpu" ? esc(cpu ? cpu.name : "The computer") : `My ${game.word}`}</h2>
          ${S.pick === "*all" ? `<div class="note">Everyone connected gets exactly this, and so does anyone who joins this session.</div>` : ""}
          ${designForm(app, base, "dz")}
          <div class="row"><button id="dz-build" class="go">${label}</button><button id="dz-history">Load a saved design</button></div>
          ${S.history ? `<div class="row"><select id="dz-hist">${S.history.slice(0, 80).map((h, i) => `<option value="${i}">${esc(h.when)} ${esc(h.who)}: ${esc(h.name)}</option>`).join("")}</select><button id="dz-load">Load it</button></div>` : ""}
          ${S.pick === "*all" && L.start_design ? `<div class="row"><button id="dz-reset">Reset every learner to the mission's starting design</button></div>` : ""}
          ${S.pick === "*cpu" ? `<h3>Its brain</h3><div class="row"><button id="cpu-reset" class="stop">Reset: as it comes</button>
              <button id="cpu-auto" class="${cpu && cpu.autopilot ? "on" : ""}">Autopilot ${cpu && cpu.autopilot ? "on" : "off"}</button>
              <label class="filebtn">Upload its brain (.py)<input id="cpu-brain" type="file" accept=".py,text/x-python,text/plain" hidden></label></div>
              <div class="note">${cpu && cpu.brain ? "It has its own brain." : "No brain of its own yet."} Autopilot uses the uploaded brain.</div>` : ""}`;
        $("dz-build").onclick = () => {
            const d = readDesign(app, base, "dz");
            if (S.pick === "*all") send({type: "design_for_all", design: d});
            else if (S.pick === "*cpu") send({type: "cpu_robot", design: d});
            else { send({type: "design", design: d, code: false}); }
        };
        $("dz-history").onclick = () => send({type: "history"});
        if ($("dz-load")) $("dz-load").onclick = () => { S.formBase = (S.history[Number($("dz-hist").value)] || {}).design || null; S.formSeq = (S.formSeq || 0) + 1; app.renderPanel(); };
        if ($("dz-reset")) $("dz-reset").onclick = () => send({type: "design_for_all", design: L.start_design, keep_own: true});
        if ($("cpu-reset")) {
            $("cpu-reset").onclick = () => send({type: "cpu_robot", reset: true});
            $("cpu-auto").onclick = () => send({type: "cpu_robot", autopilot: !(cpu && cpu.autopilot)});
            $("cpu-brain").onchange = async e => { const f = e.target.files[0]; if (f) send({type: "cpu_robot", brain: await f.text()}); };
        }
        return;
    }
    const p = people.find(x => x.name === S.pick);
    if (!p) { box.innerHTML = `<p class="note">${esc(S.pick)} isn't connected now.</p>`; return; }
    S.sub = S.sub || "mission";
    const subs = [["mission", "Mission"], ["build", `Their ${game.word}`], ["login", "Password"]];
    let inner = "";
    if (S.sub === "mission") {
        const v = S.viewing && S.viewing.for === p.name ? S.viewing : null;
        if (S.viewAsked !== p.name) { S.viewAsked = p.name; send({type: "view_learner", name: p.name}); }
        inner = v ? `<h3>Mission ${esc(v.lesson)}: ${esc(v.title || "")}</h3>
            <table>${(v.missions || []).map(m => `<tr><td class="${m.done ? "ok" : ""}">${m.done ? "✓" : "·"}</td><td>${esc(m.id)}</td><td>${esc(m.title)}<div class="note">${esc(m.detail || "")}</div></td>
              <td>${!m.done && m.check === "teacher" ? `<button data-tick="${esc(m.id)}">Tick</button>` : ""}</td></tr>`).join("")}</table>
            <div class="row"><button id="v-refresh">Refresh</button></div>` : `<p class="note">Asking the server…</p>`;
    } else if (S.sub === "build") {
        inner = `${designForm(app, S.formBase || p.design || {}, "dz")}
          <div class="row"><button id="dz-build" class="go">BUILD FOR ${esc(p.name.toUpperCase())}</button></div>
          <div class="note">Built with the widest limits, as the teacher window does; ${esc(p.name)} gets it straight away.</div>`;
    } else {
        inner = `<div class="formgrid"><label>New password</label><input id="pw-learner" type="text" autocomplete="off" placeholder="at least 6 characters"></div>
          <div class="row"><button id="pw-set" class="go">Set it</button></div>
          <div class="note">The game's own login (laptop and class-code servers). On the club's server, learners' passwords are on the TEACHER DESK.</div>`;
    }
    box.innerHTML = `<h2>${esc(p.name)}</h2><div class="row">${subs.map(([k, n]) => `<button data-sub="${k}" class="${S.sub === k ? "on" : ""}">${n}</button>`).join("")}</div>${inner}`;
    box.querySelectorAll("button[data-sub]").forEach(b => b.onclick = () => { S.sub = b.dataset.sub; S.formBase = null; app.renderPanel(); });
    box.querySelectorAll("button[data-tick]").forEach(b => b.onclick = () => { send({type: "tick", learner: p.name, mission: b.dataset.tick}); setTimeout(() => send({type: "view_learner", name: p.name}), 400); });
    if ($("v-refresh")) $("v-refresh").onclick = () => send({type: "view_learner", name: p.name});
    if ($("dz-build")) $("dz-build").onclick = () => send({type: "design_for", learner: p.name, design: readDesign(app, S.formBase || p.design || {}, "dz")});
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
          <div class="row"><button data-osave="${esc(id)}">Save</button><button data-oremove="${esc(id)}" class="stop">${armed(app, "orm:" + id) ? "Press again" : "Remove"}</button></div></div>`).join("")}
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

function cardsTab(app, body) {
    const S = app.state, T = S.teaching || {}, L = S.lesson || {}, send = app.send, game = app.game;
    const all = (T.cards || []).slice().reverse();
    const cards = S.allCards ? all : all.filter(c => !["reviewed", "rejected"].includes(c.status));
    body.innerHTML = `
      <h2>AI cards</h2>
      <div class="note">Learners ask for a change to the game on a card. Claude makes the change on your laptop (the Club Coders
        app's AI cards tab: Send to Claude, Keep or Undo). Here you can read every card, send it back, mark where it is,
        copy it for Claude, and put a kept change's file on the server.</div>
      <div class="formgrid"><label>On the learners' cards</label><input id="card-note" maxlength="300" value="${esc(L.ai_card_note || "")}" placeholder="a line from you on every learner's card"></div>
      <div class="row"><button id="card-note-save">Save the line</button>
        <button id="cards-all" class="${S.allCards ? "on" : ""}">${S.allCards ? "Showing every card" : "Showing open cards"}</button></div>
      ${cards.map(c => {
          const k = c.card || {};
          return `<div class="card">
            <div class="row"><b>#${esc(c.id)} ${esc(c.learner)}</b><span class="note">${esc(c.time)} · ${esc(k.target)} · ${esc(STATUS_WORDS[c.status] || c.status)}</span></div>
            <p><b>Goal:</b> ${esc(k.goal)}</p>${k.variables ? `<p><b>Variables:</b> ${esc(k.variables)}</p>` : ""}
            <p><b>Test:</b> ${esc(k.test)}</p>${k.predict ? `<p><b>Prediction:</b> ${esc(k.predict)}</p>` : ""}
            <p class="note">${k.privacy ? "✓" : "✗"} no personal details · ${k.review ? "✓" : "✗"} will review · ${k.credit ? "✓" : "✗"} will credit the AI</p>
            ${c.note ? `<p class="note">Your note: ${esc(c.note)}</p>` : ""}
            ${c.review ? `<p class="note">Their review: ${Object.entries(c.review).map(([q, a]) => `<b>${esc(q)}</b> ${esc(a)}`).join(" · ")}</p>` : ""}
            <input id="cn-${c.id}" class="wide" maxlength="200" placeholder="a note for the learner (optional)">
            <div class="row"><button data-cst="working" data-cid="${c.id}">With Claude</button><button data-cst="ready" data-cid="${c.id}" class="go">Kept</button>
              <button data-cst="rejected" data-cid="${c.id}" class="stop">Send back</button><button data-ccopy="${c.id}">Copy for Claude</button></div></div>`;
      }).join("") || "<p class='note'>No cards.</p>"}
      <h2>Put a kept change on the server</h2>
      <div class="note">After Keep on your laptop, a change to these files can go straight to the class: choose which file and
        load it from your laptop. The server checks it before using it.</div>
      <div class="formgrid"><label>File</label><select id="mod-path">${game.mods.map(m => `<option>${esc(m)}</option>`).join("")}</select>
        <label>Learner's username</label><input id="mod-user" placeholder="for a learner's own file"></div>
      <div class="row"><label class="filebtn">Choose the file and send it<input id="mod-file" type="file" accept=".py,text/plain" hidden></label></div>`;
    $("card-note-save").onclick = () => send({type: "lesson", lesson: {ai_card_note: $("card-note").value}});
    $("cards-all").onclick = () => { S.allCards = !S.allCards; app.renderPanel(); };
    body.querySelectorAll("button[data-cst]").forEach(b => b.onclick = () => {
        const id = Number(b.dataset.cid), status = b.dataset.cst;
        send({type: "card_status", id, status, note: $("cn-" + id).value.trim() || NOTES[status]});
    });
    body.querySelectorAll("button[data-ccopy]").forEach(b => b.onclick = async () => {
        const c = (T.cards || []).find(x => String(x.id) === b.dataset.ccopy);
        if (!c) return;
        const k = c.card || {};
        const text = `A learner (${c.learner}) asks for a change to ${game.title} (${k.target}).\nGoal: ${k.goal}\nVariables: ${k.variables}\n` +
                     `How they will test it: ${k.test}\nTheir prediction: ${k.predict}\nKeep the change small and explain it in comments a learner can follow.`;
        try { await navigator.clipboard.writeText(text); app.toast("Copied: paste it into Claude."); } catch (e) { app.toast("This browser wouldn't copy it."); }
    });
    $("mod-file").onchange = async e => {
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
    const votes = (which, k) => ((mods[which] || {})[k] || []).length;
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
             <small><input type="checkbox" data-avote="${esc(k)}" ${inVote("arena_in_vote", k) ? "checked" : ""}> in the vote${votes("arena_votes", k) ? ` (${votes("arena_votes", k)})` : ""}</small></label>`).join("") || "<span class='note'>None in this game.</span>"}</div>
      ${R.house ? `<div class="row"><label>Resident Robots</label>${Object.keys(R.house).map(n => {
          const on = haz.house_robots === true || (Array.isArray(haz.house_robots) && haz.house_robots.includes(n));
          return `<button data-house="${esc(n)}" class="${on ? "on" : ""}">${esc(n)}</button>`; }).join("")}</div>` : ""}
      <h2>User mods</h2>
      <div class="ticks">${Object.entries(userMods).map(([k, v]) => {
          const maker = (mods.makers || {})[k];
          return `<label><input type="checkbox" data-umod="${esc(k)}" ${v ? "checked" : ""}> ${esc(maker ? `${maker}'s ` : "")}${esc(pretty(k))}
            <small><input type="checkbox" data-mvote="${esc(k)}" ${inVote("mods_in_vote", k) ? "checked" : ""}> in the vote${votes("votes", k) ? ` (${votes("votes", k)})` : ""}</small></label>`;
      }).join("") || "<span class='note'>No user mods in this game yet.</span>"}</div>
      <h2>Limits</h2>
      <div class="note">The lowest and highest each learner may choose, and the points to share. Builds outside are pulled back in.</div>
      <table><tr><th></th><th>lowest</th><th>highest</th></tr>
        ${Object.keys(full.points || {}).map(k => { const [lo, hi] = pair("points", k); return `<tr><td>${esc(pretty(k))}</td><td><input type="number" id="lim-p-${k}-0" value="${lo}" size="4"></td><td><input type="number" id="lim-p-${k}-1" value="${hi}" size="4"></td></tr>`; }).join("")}
        ${Object.keys(full.settings || {}).map(k => { const [lo, hi] = pair("settings", k); return `<tr><td>${esc(pretty(k))}</td><td><input type="number" id="lim-s-${k}-0" value="${lo}" size="4"></td><td><input type="number" id="lim-s-${k}-1" value="${hi}" size="4"></td></tr>`; }).join("")}
        <tr><td>Points to share</td><td colspan="2"><input type="number" id="lim-total" value="${limits.points_total ?? R.points_total ?? 100}" size="4"></td></tr></table>
      <div class="row"><button id="lim-save" class="go">Save the limits</button><button id="lim-standard">Standard limits</button></div>`;
    body.querySelectorAll("input[data-tool]").forEach(c => c.onchange = () => lessonSend({tools: {[c.dataset.tool]: c.checked}}));
    body.querySelectorAll("button[data-list]").forEach(b => b.onclick = () => {
        const k = b.dataset.list, cur = new Set(tools[k] || []);
        if (cur.has(b.dataset.item)) cur.delete(b.dataset.item); else cur.add(b.dataset.item);
        if (!cur.size) return app.toast("Leave at least one.");
        lessonSend({tools: {[k]: [...cur]}});
    });
    body.querySelectorAll("input[data-haz]").forEach(c => c.onchange = () => lessonSend({hazards: {[c.dataset.haz]: c.checked}}));
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
        for (const k of Object.keys(full.settings || {})) out.settings[k] = R.settings && R.settings[k] ? R.settings[k].slice(0, 2) : full.settings[k];
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
