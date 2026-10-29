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

// ---------- the Mods tab's items and the vote (CHANGE 143: as engine/hud.py build_mods and each window's stage_items) ----------
const STAGE_WORDS = {robotlab: {pit: "Drop zone open", floor_flipper: "Floor flipper", saws: "Floor saws", spikes: "Wall spikes"},
                     fightlab: {ring_out: "Ring-outs (no ropes)", electric_ropes: "Electric ropes", fire_jets: "Fire jets",
                                slippery: "Slippery ice", spikes: "Spikes"},
                     citylab: {traffic: "Traffic", robots: "Robots"},  // (CHANGE 201: city_server's hazards)
                     craftlab: {mobs: "Creatures (Glitch rifts at dusk, Rust Walkers)", energy: "Energy drains as you work",
                                hunger: "Energy drains as you work"}};  // (CHANGE 202, 207: craft_missions.NO_HAZARDS, craft_tabs.HAZARD_NAMES)

export function houseOn(app) {  // (lab_sim.house_list: True is all four, a list is those named)
    const all = Object.keys((app.state.rules || {}).house || {}), v = ((app.state.lesson || {}).hazards || {}).house_robots;
    return v === true ? all : Array.isArray(v) ? all.filter(n => v.includes(n)) : [];
}

// the game's own items: its hazards, and in Robot Lab each Resident Robot on its own (the server's ARENA_ITEMS has
// them by name, so each is its own vote): [{key, text, on, patch(on) -> the lesson change that switches it}]
export function stageItems(app) {
    const S = app.state, L = S.lesson || {}, R = S.rules || {}, hz = L.hazards || {}, game = app.game ? app.game.id : "";
    const words = STAGE_WORDS[game] || {};
    const keys = Object.keys(words).length ? Object.keys(words) : Object.keys(hz);
    const items = keys.filter(k => k !== "house_robots").map(k => {
        const v = hz[k];
        return {key: k, text: words[k] || pretty(k), on: v && typeof v === "object" ? Object.values(v).some(Boolean) : !!v,
                patch: on => ({hazards: {[k]: on}})};
    });
    if (R.house && "house_robots" in hz) {
        const on = houseOn(app);
        for (const n of Object.keys(R.house)) {
            items.push({key: n, text: `Resident Robot ${n}`, on: on.includes(n), house: true,
                        patch: v => ({hazards: {house_robots: [...on.filter(x => x !== n), ...(v ? [n] : [])]}})});
        }
    }
    return items;
}

// every user mod (the game's list, and what the server says is on or off) as {key: on}
export function allUserMods(app) {
    const S = app.state, game = app.game ? app.game.id : "";
    const known = Object.keys((((S.lessons || {})[game]) || {}).user_mods || {});
    return {...Object.fromEntries(known.map(k => [k, false])), ...((S.roster && S.roster.user_mods) || {}), ...((S.lesson || {}).user_mods || {})};
}

// the user mods as [key, made by a learner in this group], this group's own first (the window's mod_order)
export function modOrder(app) {
    const info = app.state.mods || {}, makers = info.makers || {};
    const here = new Set((info.here || []).map(n => String(n).toLowerCase()));
    const mods = Object.keys(allUserMods(app)).map(k => [k, !!makers[k] && here.has(String(makers[k]).toLowerCase())]);
    return mods.filter(m => m[1]).concat(mods.filter(m => !m[1]));
}

const votesText = n => n ? `${n} vote${n === 1 ? "" : "s"}` : "";

// the learner's Mods tab (the window's build_mods for a learner): an item out of the vote is hidden unless it is on,
// and then it is shown ON with no tick to vote with. preview: the teacher's look at it (the ticks do nothing)
export function learnerModsHtml(app, preview = false) {
    const S = app.state, L = S.lesson || {}, info = S.mods || {}, me = preview ? null : S.name;
    const arenaIn = L.arena_in_vote || {}, modsIn = L.mods_in_vote || {}, asked = info.arena_votes || {}, votes = info.votes || {};
    const game = app.game ? app.game.id : "", on = allUserMods(app);
    const off = preview ? "disabled" : "";
    const items = stageItems(app).filter(it => arenaIn[it.key] !== false || it.on);
    let html = `<h3>The ${game === "kartlab" ? "track" : game === "fightlab" ? "stage" : game === "citylab" ? "city" : "arena"}</h3>
      <p class="note">Tick what you'd like in the game: your teacher sees the votes.</p>`;
    html += items.length ? `<table>${items.map(it => {
        const voters = asked[it.key] || [];
        if (arenaIn[it.key] === false) return `<tr><td class="ok">${esc(it.text)}</td><td class="ok">ON</td></tr>`;
        return `<tr><td><label class="${it.on ? "ok" : ""}"><input type="checkbox" data-avote="${esc(it.key)}" ${me && voters.includes(me) ? "checked" : ""} ${off}>
            ${esc(it.text)}${voters.length ? ` (${votesText(voters.length)})` : ""}</label></td><td class="${it.on ? "ok" : "note"}">${it.on ? "ON" : "off"}</td></tr>`;
    }).join("")}</table>` : `<p class="note">Nothing here is in the vote at the moment.</p>`;
    html += `<h3>User mods</h3><p class="note">Learners' ideas, built into the game. Tick the ones you'd like in the game: your teacher
      sees the votes and switches mods on.</p>`;
    const order = modOrder(app).filter(([k]) => modsIn[k] !== false || on[k]);
    html += order.length ? `<table>${order.map(([k]) => {
        const maker = (info.makers || {})[k], m = modInfo(app, k), voters = votes[k] || [], title = esc(maker ? `${maker}'s ` : "") + esc(m.title);
        const what = m.text ? `<div class="note">${esc(m.text)}</div>` : "";
        if (modsIn[k] === false) return `<tr><td><span class="ok">${title}</span>${what}</td><td class="ok">ON</td></tr>`;
        return `<tr><td><label><input type="checkbox" data-mvote="${esc(k)}" ${me && voters.includes(me) ? "checked" : ""} ${off}> ${title}</label>${what}</td>
            <td class="${on[k] ? "ok" : "note"}">${voters.length ? votesText(voters.length) + " " : ""}${on[k] ? "ON" : "off"}</td></tr>`;
    }).join("")}</table>` : `<p class="note">No user mods yet.</p>`;
    return html;
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
               `<td class="num">${pf.fps ?? ""}</td><td class="num">${pf.ping ?? ""}</td><td class="num">${pf.ctrl ?? ""}</td>` +
               `<td class="num ${Number(stalls) > 5 ? "bad" : ""}">${stalls}</td><td>${esc(pf.tier ?? "")}</td></tr>`;
    }).join("");
    const picks = [...learners(app).map(p => [p.name, p.name]), ["*all", "All learners"],
                   ...cpus.map(c => [cpuPick(c), c.n ? `Computer ${c.n}` : c.name]), ["*me", `My ${game.word}`]];
    if (!S.pick || (cpuOf(app, S.pick) && !picks.some(([k]) => k === S.pick)))  // (a computer robot no longer in use)
        S.pick = learners(app)[0] ? learners(app)[0].name : "*all";
    body.innerHTML = `
      <h2>Who is here</h2>
      <table><tr><th>Name</th><th>Role</th>${extraHead.map(h => `<th>${esc(h)}</th>`).join("")}<th>fps</th><th>ping</th><th title="how long a key press takes to show, in ms (the window's key delay)">key delay</th><th>stalls</th><th>graphics</th></tr>${rows}</table>
      <div class="note">fps, ping, key delay and stalls come from each window every few seconds. Stalls are frames over 100 ms apart: a few a
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
    const subRow = list => `<div class="row">${list.map(([k, n]) => `<button data-sub="${k}" class="${S.sub === k ? "on" : ""}">${esc(n)}</button>`).join("")}</div>`;
    const wireSubs = () => box.querySelectorAll("button[data-sub]").forEach(b => b.onclick = () => {
        S.sub = b.dataset.sub; S.formBase = null; S.viewAsked = null; app.renderPanel();
    });
    // (CHANGE 143) a computer's robot or fighter has the window's Mission and Mods (as a learner sees them) too
    if (cpu) S.sub = ["garage", "mission", "mods"].includes(S.sub) ? S.sub : "garage";
    const cpuSubs = cpu ? subRow([["garage", "Garage"], ["mission", "Mission"], ["mods", "Mods"]]) : "";
    if (cpu && S.sub !== "garage") {
        box.innerHTML = cpuSubs + (S.sub === "mission" ? missionPreview(app, cpu.name, false)
            : `<p class="note">The Mods tab as a learner sees it (the computer's ${esc(game.word)} doesn't vote).</p>` + learnerModsHtml(app, true));
        wireSubs();
        if ($("v-refresh")) $("v-refresh").onclick = () => send({type: "view_learner", name: cpu.name});
        return;
    }
    if (S.pick === "*all" || S.pick === "*me" || cpu) {
        const who = S.pick === "*me" ? null : S.pick;
        const which = cpu && cpu.n ? {n: cpu.n} : {};  // (which computer robot: Robot Lab's, CHANGE 140)
        const arenas = L.arenas || 1, all = people.filter(p => p.role === "computer").length;
        box.innerHTML = `${cpuSubs}<div id="dzgarage"></div>
          ${loadFromHtml(app, S.pick, {mine: S.pick !== "*me"})}
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
                if (name) d.name = Array.from(name.value).slice(0, ["kartlab", "citylab"].includes(game.id) ? 12 : 16).join("");
                if (S.pick === "*all") send({type: "design_for_all", design: d});
                else send({type: "cpu_robot", ...which, design: d});
            }});
        wireSubs();
        wireLoadFrom(app, box, S.pick, {who});
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
        inner = missionPreview(app, p.name, true);
    } else if (S.sub === "build") {
        inner = `<div id="dzgarage"></div>
          ${loadFromHtml(app, p.name, {mine: true, theirs: p.name})}
          <div class="note">Built with the widest limits, as the teacher window does; ${esc(p.name)} gets it straight away.</div>`;
    } else if (S.sub === "cards") {  // (the card's words are under card: teaching.submit_card)
        const cards = ((S.teaching || {}).cards || []).filter(c => c.learner === p.name);
        inner = cards.length ? cards.map(c => {
            const k = c.card || {};
            return `<div class="objective"><b>#${esc(c.id)} ${esc(k.goal || "")}</b> <span class="note">${esc(STATUS_WORDS[c.status] || c.status || "")}${c.note ? ": " + esc(c.note) : ""}</span>
              <div class="note">Variables: ${esc(k.variables || "")}<br>Test: ${esc(k.test || "")}<br>Predict: ${esc(k.predict || "")}</div>
              ${c.review ? `<div class="note">Their review: ${Object.entries(c.review).map(([q, a]) => `<b>${esc(q)}</b> ${esc(a)}`).join(" · ")}</div>` : ""}</div>`;
        }).join("") : `<p class="note">${esc(p.name)} hasn't sent an AI card yet. The AI cards tab handles them.</p>`;
    } else {
        inner = `<div class="formgrid"><label>New password</label><input id="pw-learner" type="text" autocomplete="off" placeholder="at least 6 characters"></div>
          <div class="row"><button id="pw-set" class="go">Set it</button></div>
          <div class="note">The game's own login (laptop and class-code servers). On the club's server, learners' passwords are on the TEACHER DESK.</div>`;
    }
    box.innerHTML = `<h2>${esc(p.name)}</h2>${subRow(subs)}${inner}`;
    wireSubs();
    if ($("dzgarage")) {
        renderGarage(app, $("dzgarage"), {who: p.name, pre: "dz", build: d => {
            const name = $("dz-name");  // (the window's send_design_for: the name as it is in the box)
            if (name) d.name = Array.from(name.value).slice(0, ["kartlab", "citylab"].includes(game.id) ? 12 : 16).join("");
            send({type: "design_for", learner: p.name, design: d});
        }});
    }
    box.querySelectorAll("button[data-tick]").forEach(b => b.onclick = () => { send({type: "tick", learner: p.name, mission: b.dataset.tick}); setTimeout(() => send({type: "view_learner", name: p.name}), 400); });
    if ($("v-refresh")) $("v-refresh").onclick = () => send({type: "view_learner", name: p.name});
    wireLoadFrom(app, box, p.name, {who: p.name, theirs: p.name, base: p.design});
    if ($("pw-set")) $("pw-set").onclick = () => {
        const pw = $("pw-learner").value;
        if (pw.length < 6) return app.toast("Passwords need at least 6 characters.");
        send({type: "set_password", learner: p.name, password: pw});
        $("pw-learner").value = "";
    };
}

// a learner's (or a computer's) Mission tab as the teacher's Learner view shows it (engine/hud.py build_missions with
// preview, CHANGE 143): each objective's state, outcome codes and guidance, what was done, what they have typed in a
// box not yet done, and the brain with its error. tick: the teacher-checked ones get a Tick button
function missionPreview(app, name, tick) {
    const S = app.state, v = S.viewing && S.viewing.for === name ? S.viewing : null;
    if (S.viewAsked !== name) { S.viewAsked = name; app.send({type: "view_learner", name}); }
    if (!v) return `<p class="note">Asking the server…</p>`;
    const typed = v.text || {};
    let html = `<h3>Mission ${esc(v.lesson)}: ${esc(v.title || "")}</h3>`;
    (v.missions || []).forEach((m, i) => {
        const state = m.done ? "DONE" : m.check === "teacher" ? "TEACHER" : "TO DO";
        html += `<div class="objective preview ${m.done ? "done" : ""}">
          <div class="row"><b class="${m.done ? "ok" : ""}">[${state}]  ${i < 8 ? "abcdefgh"[i] + ". " : ""}${esc(m.title)}${m.done ? " ✓" : ""}</b>
            <span class="codes">${esc((m.outcomes || []).join(" "))}</span>
            ${tick && !m.done && m.check === "teacher" ? `<button data-tick="${esc(m.id)}">Tick</button>` : ""}</div>
          ${m.done && m.detail ? `<div class="note ok">${esc(m.detail)}</div>` : ""}
          <div class="note">${esc(m.text || "").replace(/\n/g, "<br>")}</div>
          ${typed[m.id] && !m.done ? `<div class="wrote">They wrote: ${esc(typed[m.id])}</div>` : ""}</div>`;
    });
    if (v.lesson >= 3) {
        const status = v.brain ? (v.autopilot ? "autopilot ON" : "uploaded (press P for autopilot)") : "not uploaded yet (edit brains/my_brain.py, then press U)";
        html += `<p class="${v.brain ? "ok" : "note"}">Brain: ${status}</p>${v.brain_error ? `<p class="bad">Brain stopped: ${esc(v.brain_error)}</p>` : ""}`;
    }
    return html + `<div class="row"><button id="v-refresh">Refresh</button></div>`;
}

// Load from (engine/hud.py build_load_from, CHANGE 143): a saved design into the garage being looked at, from the
// teacher's own five (My saved), this learner's (their saved) or the history of every save. view: whose garage
function loadFromHtml(app, view, {mine = true, theirs = null} = {}) {
    const S = app.state, lf = S.loadFrom && S.loadFrom.view === view ? S.loadFrom.key : null;
    const choices = [...(mine ? [["mine", "My saved"]] : []), ...(theirs ? [["theirs", `${theirs}'s saved`]] : []), ["history", "History"]];
    let html = `<div class="row"><b>Load from</b>${choices.map(([k, n]) => `<button data-lfrom="${k}" class="${lf === k ? "on" : ""}">${esc(n)}</button>`).join("")}
      ${lf && S.lfNote ? `<span class="ok">${esc(S.lfNote)}</span>` : ""}</div>`;
    if (!lf) return html;
    const slotRows = slots => Object.keys(slots).sort().map(n => [`slot ${n}:  ${slots[n].name}`, n]);
    const rows = lf === "history" ? (S.history ? S.history.slice(0, 40).map((it, i) => [`${it.when}  ${it.who}  slot ${it.slot}:  ${it.name}`, i]) : null)
        : lf === "mine" ? (S.slots ? slotRows(S.slots) : null)
        : (S.theirSlots && S.theirSlots.who === theirs ? slotRows(S.theirSlots.slots || {}) : null);
    if (rows === null) return html + `<p class="note">Loading…</p>`;
    if (!rows.length) return html + `<p class="note">${lf === "history" ? "Nothing saved yet." : `No saved ${esc(app.game.word)}s.`}</p>`;
    return html + `<div class="loadlist">${rows.map(([t, i]) => `<div class="row"><span>${esc(t)}</span><button data-lfload="${esc(i)}">LOAD</button></div>`).join("")}</div>`;
}

function wireLoadFrom(app, box, view, {who = null, theirs = null, base = null} = {}) {
    const S = app.state, send = app.send;
    box.querySelectorAll("button[data-lfrom]").forEach(b => b.onclick = () => {
        const key = b.dataset.lfrom;
        S.loadFrom = {view, key};
        S.lfNote = null;
        if (key === "history") { S.history = null; send({type: "history"}); }
        else if (key === "theirs") send({type: "slots_of", name: theirs});
        else if (!S.slots) send({type: "slot", do: "list"});
        app.renderPanel();
    });
    box.querySelectorAll("button[data-lfload]").forEach(b => b.onclick = () => {
        const key = (S.loadFrom || {}).key, i = b.dataset.lfload;
        const held = key === "history" ? (S.history || [])[Number(i)] : key === "mine" ? (S.slots || {})[i] : ((S.theirSlots || {}).slots || {})[i];
        if (!held || !held.design) return;
        takeDesign(app, base ? Object.assign({}, base, held.design) : held.design, who);
        S.lfNote = `Loaded ${held.name}: press BUILD to use it.`;
        S.formSeq = (S.formSeq || 0) + 1;
        app.renderPanel();
    });
}

// the accounts as the window lists them (CHANGE 143): with the club desk, this session's names first (green), then
// the next session's (orange: the group whose proposed time comes next), then everyone else
function accountNames(app) {
    const S = app.state, T = S.teaching || {}, ses = S.session || {};
    const here = new Set(ses.learners || []), coming = new Set(ses.next || []);
    const rank = n => here.has(n) ? 0 : coming.has(n) ? 1 : 2;
    return [...new Set([...(T.accounts || []), ...(ses.all || [])])]
        .sort((a, b) => rank(a) - rank(b) || a.toLowerCase().localeCompare(b.toLowerCase()));
}

function accountsHtml(app) {
    const S = app.state, ses = S.session || {};
    const names = accountNames(app);
    const inSession = new Set(ses.learners || []), coming = new Set(ses.next || []);
    const colours = ses.desk ? (ses.live ? `Green: in this session (${esc(ses.group)}).` : "No session is live.") +
        (ses.next_group ? ` <span class="orange">Orange: next, ${esc(ses.next_group)}${ses.next_time ? ` (${esc(ses.next_time)})` : ""}.</span>` : "") : "";
    return `<h2>Accounts on this game server (${names.length})</h2>
      <div class="note">The game's own records of each learner (their ${esc(app.game.word)}, evidence, AI cards). Deleting one removes all of
        it. ${ses.desk && ses.live ? "The tick lets a learner into this desk session, or takes them out." : ""}</div>
      ${colours ? `<div class="note">${colours}</div>` : ""}
      <table>${names.slice(0, 200).map((n, i) => `<tr><td class="${inSession.has(n) ? "ok" : coming.has(n) ? "orange" : ""}">${esc(n)}</td>
        ${ses.desk && ses.live ? `<td><label><input type="checkbox" data-sesn="${i}" ${inSession.has(n) ? "checked" : ""}> in this session</label></td>` : ""}
        <td><input id="acpw-${i}" placeholder="new password" autocomplete="off" size="12"></td>
        <td><button data-acpw="${i}">Set password</button> <button data-acdel="${i}" class="stop">${armed(app, "del:" + n) ? "Press again" : "Delete"}</button></td></tr>`).join("")
        || "<tr><td class='note'>No accounts yet.</td></tr>"}</table>
      <div class="formgrid"><label>Username</label><input id="ac-name" maxlength="12" autocomplete="off">
        <label>Password</label><input id="ac-pw" autocomplete="off" placeholder="at least 6 characters"></div>
      <div class="row"><button id="ac-add">Make account</button></div>`;
}

function wireAccounts(app, body) {
    const send = app.send, names = accountNames(app);
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

// ---------- the lesson guide (CHANGE 143): Robot Lab's window reads it from its lesson file (lab_missions GUIDE,
// LESSON_TASKS, OUTCOMES' curriculum references); the page asks the club's desk, which reads the same file (its
// "scheme" command, as Print scheme of work). lessons.json carrying it as scheme is used first, if it ever does.
// {lessons: {n: {title, task}}, outcomes: {code: [name, can do, curriculum]}, missions: {id: [lesson, title, text,
// outcomes, check]}, guide: {n: {code: {task, do, teach, success}}}}
const GUIDE_GAMES = new Set(["robotlab"]);  // (the windows that show it: Fight Lab's and Kart Lab's don't)

export function guideOf(app) {
    const S = app.state, game = app.game.id, own = ((S.lessons || {})[game] || {}).scheme;
    if (own) return own;
    const desk = S.desk;
    if (!desk) return null;
    if (desk.scheme) return desk.scheme[game] || null;
    if (desk.ready && !desk.schemeAsked) {
        desk.schemeAsked = true;
        const got = scheme => { desk.scheme = scheme; app.renderPanel(); };  // (asked once: an older desk says no)
        desk.ask({type: "scheme"}, "scheme").then(m => got(m.scheme || {}), () => got({}));
    }
    return null;
}

function outcomePiece(app, G, code) {  // (the window's build_outcome_piece)
    const S = app.state, T = S.teaching || {}, grid = T.grid || {}, learners = Object.keys(grid);
    const [name, can, refs] = G.outcomes[code];
    const taughtIn = Object.keys(G.guide || {}).filter(k => code in G.guide[k]).map(Number).sort((a, b) => a - b);
    let gn = S.guideLesson || T.lesson || 1;
    if (!taughtIn.includes(gn) && taughtIn.length) gn = taughtIn[0];
    const piece = ((G.guide || {})[String(gn)] || {})[code] || {}, lesson = G.lessons[String(gn)] || {};
    const evidence = Object.entries(G.missions || {}).filter(([, v]) => v[0] === gn && (v[3] || []).includes(code));
    const shown = learners.filter(nm => (grid[nm].outcomes || {})[code]);
    return `<div class="row"><button id="op-back">&lt; All outcomes</button><span class="codes">${esc(code)}</span></div>
      <h2>${esc(String(name).toUpperCase())}</h2>
      <p><b>Learners can:</b> ${esc(can)}</p>
      <div class="row"><b>Taught in mission</b>${taughtIn.map(k => `<button data-oplesson="${k}" class="${k === gn ? "on" : ""}">${k}</button>`).join("")}</div>
      <h3>Mission ${esc(gn)}: ${esc(lesson.title || "")}</h3>
      ${lesson.task ? `<p class="blue">Overall task: ${esc(lesson.task)}</p>` : ""}
      ${piece.task ? `<p><b>Task: ${esc(piece.task)}</b></p>` : ""}
      <h3>What learners do</h3><ol>${(piece.do || []).map(s => `<li>${esc(s)}</li>`).join("")}</ol>
      <h3>What to explain or show</h3><p>${esc(piece.teach || "")}</p>
      <h3>Success looks like</h3><p class="ok">${esc(piece.success || "")}</p>
      <h3>Objectives that give evidence</h3>
      ${evidence.map(([mid, v]) => `<p>${esc(mid)}  ${esc(v[1])}  <span class="note">(${v[4] === "teacher" ? "the teacher ticks it" : "ticked by the game"})</span></p>`).join("") || "<p class='note'>None.</p>"}
      ${learners.length ? `<p class="note">Shown so far by ${shown.length} of ${learners.length}: ${esc(shown.join(", ") || "nobody yet")}</p>` : ""}
      <p class="note">Curriculum: ${esc(refs || "")}</p>`;
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
    // (CHANGE 143) Robot Lab's window has a lesson guide here: any mission's outcomes, each with its lesson piece
    const guided = GUIDE_GAMES.has(app.game.id), G = guided ? guideOf(app) : null;
    if (G && S.outcomeView && G.outcomes[S.outcomeView]) {
        body.innerHTML = outcomePiece(app, G, S.outcomeView);
        $("op-back").onclick = () => { S.outcomeView = null; app.renderPanel(); };
        body.querySelectorAll("button[data-oplesson]").forEach(b => b.onclick = () => { S.guideLesson = Number(b.dataset.oplesson); app.renderPanel(); });
        return;
    }
    const gn = guided ? (S.guideLesson || n) : n, gObjs = Object.entries(edited[String(gn)] || {});
    const gTaught = G ? new Set(Object.keys(G.guide[String(gn)] || {})) : new Set(gObjs.flatMap(([, o]) => o[3] || []));
    const lessonG = G ? G.lessons[String(gn)] || {} : {};
    // each outcome this mission teaches, with its objectives (click one for what it asks), as the windows list them
    const teaches = codes.filter(c => gTaught.has(c)).map(c => `<div class="outcome">
        ${G ? `<button data-opiece="${esc(c)}" class="go" title="its lesson piece">${esc(outs[c][0])}</button>` : `<b>${esc(outs[c][0])}</b>`} <span class="codes">${esc(c)}</span>
        ${gObjs.map(([mid, o], i) => (o[3] || []).includes(c) ? `<div><button class="link ${S.openOutcomeObj === mid ? "on" : ""}" data-oobj="${esc(mid)}">${i < 8 ? "abcdefgh"[i] : "+"}. ${esc(o[1])}</button>
            ${S.openOutcomeObj === mid ? `<div class="note">${esc(o[2]).replace(/\n/g, "<br>")}</div>` : ""}</div>` : "").join("")}</div>`).join("");
    body.innerHTML = `
      <h2>Outcomes shown (mission ${esc(guided ? gn : n)})</h2>
      ${guided ? `<div class="row"><b>Mission</b>${[1, 2, 3, 4, 5].map(k => `<button data-glesson="${k}" class="${k === gn ? "on" : ""}">${k}</button>`).join("")}
          <span class="note">(the class is on mission ${esc(n)})</span></div>
        ${G ? `<p><b>${esc(lessonG.title || "")}</b></p>${lessonG.task ? `<p class="blue">Overall task: ${esc(lessonG.task)}</p>` : ""}`
            : `<p class="note">${!S.desk ? "The lesson guide (each outcome's lesson piece) comes from the club's desk: log in through the desk to see it here."
                : S.desk.scheme ? "The club's desk didn't send the lesson guide (its server may need the latest release)." : "Asking the desk for the lesson guide…"}</p>`}` : ""}
      <div class="scrollx"><table><tr><th>Learner</th>${codes.map(c => `<th title="${esc(outs[c][0])}: ${esc(outs[c][1])}" class="${gTaught.has(c) ? "taught" : ""}">${esc(c)}</th>`).join("")}</tr>
        ${names.map(nm => `<tr><td>${esc(nm)}</td>${codes.map(c => { const k = (grid[nm].outcomes || {})[c] || 0; return `<td class="num ${k ? "ok" : ""}">${k || ""}</td>`; }).join("")}</tr>`).join("")
          || `<tr><td class="note" colspan="${codes.length + 1}">Nobody yet.</td></tr>`}</table></div>
      <div class="note">Highlighted codes are what this mission teaches. Hover a code for its name.${G ? " Click an outcome for its lesson piece." : ""}</div>
      ${teaches ? `<h3>What mission ${esc(gn)} teaches</h3>${teaches}` : ""}
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
          <div class="row"><button data-osave="${esc(id)}">Save</button><button data-oauto="${esc(id)}" title="An AI card asking Claude to write this objective's automatic check: send it to Claude from the AI cards tab">Automate</button><button data-oremove="${esc(id)}" class="stop">${armed(app, "orm:" + id) ? "Press again" : "Remove"}</button></div>
          ${names.length ? `<div class="row whodone">${names.filter(nm => nm !== S.name).map(nm =>
              `<span class="${(grid[nm].missions || []).includes(id) ? "ok" : "bad"}">${esc(nm)}</span>`).join("")}</div>` : ""}</div>`).join("")}
      ${names.length ? `<div class="note">Under each objective: green has done it, red not yet.</div>` : ""}
      <h3>Add an objective to mission ${esc(E)}</h3>
      <input id="oa-title" class="wide" placeholder="title"><textarea id="oa-text" rows="3" class="wide" placeholder="what to do"></textarea>
      <div class="row"><button id="oa-add">Add</button></div>
      <h3>As a file</h3>
      <div class="row"><button id="btn-missions-export">Download the missions file</button>
        <label class="filebtn">Load an edited missions file<input id="missions-import" type="file" accept=".json,application/json" hidden></label></div>`;
    body.querySelectorAll("button[data-tick]").forEach(b => b.onclick = () => send({type: "tick", learner: b.dataset.who, mission: b.dataset.tick}));
    body.querySelectorAll("button[data-glesson]").forEach(b => b.onclick = () => { S.guideLesson = Number(b.dataset.glesson); S.openOutcomeObj = null; app.renderPanel(); });
    body.querySelectorAll("button[data-opiece]").forEach(b => b.onclick = () => { S.outcomeView = b.dataset.opiece; app.renderPanel(); });
    body.querySelectorAll("button[data-oobj]").forEach(b => b.onclick = () => {
        S.openOutcomeObj = S.openOutcomeObj === b.dataset.oobj ? null : b.dataset.oobj;
        app.renderPanel();
    });
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
    // (CHANGE 143) the window's stage items: the hazards, and each Resident Robot as its own item with its own vote
    const items = stageItems(app);
    const userMods = allUserMods(app);
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
      <div class="ticks">${items.map(it =>
          `<label><input type="checkbox" ${it.house ? "data-house" : "data-haz"}="${esc(it.key)}" ${it.on ? "checked" : ""}> ${esc(it.text)}
             <small><input type="checkbox" data-avote="${esc(it.key)}" ${inVote("arena_in_vote", it.key) ? "checked" : ""}> in the vote${whoVoted("arena_votes", it.key)}</small></label>`).join("") || "<span class='note'>None in this game.</span>"}</div>
      ${items.length ? `<div class="row"><button data-voteall="arena_in_vote" data-on="1">All in the vote</button><button data-voteall="arena_in_vote" data-on="0">None in the vote</button></div>` : ""}
      <h2>User mods</h2>
      <div class="note">Green: made by a learner in this group.</div>
      <div class="ticks">${modOrder(app).map(([k, lit]) => {
          const v = userMods[k], maker = (mods.makers || {})[k], info = modInfo(app, k);
          return `<label title="${esc(info.text)}" class="${lit ? "ok" : ""}"><input type="checkbox" data-umod="${esc(k)}" ${v ? "checked" : ""}> ${esc(maker ? `${maker}'s ` : "")}${esc(info.title)}
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
        const keys = which === "mods_in_vote" ? Object.keys(userMods) : items.map(it => it.key);
        lessonSend({[which]: Object.fromEntries(keys.map(k => [k, on]))});
    });
    body.querySelectorAll("input[data-avote]").forEach(c => c.onchange = () => lessonSend({arena_in_vote: {[c.dataset.avote]: c.checked}}));
    body.querySelectorAll("input[data-umod]").forEach(c => c.onchange = () => lessonSend({user_mods: {[c.dataset.umod]: c.checked}}));
    body.querySelectorAll("input[data-mvote]").forEach(c => c.onchange = () => lessonSend({mods_in_vote: {[c.dataset.mvote]: c.checked}}));
    body.querySelectorAll("input[data-house]").forEach(c => c.onchange = () => {  // (the window's toggle_house)
        const it = items.find(x => x.house && x.key === c.dataset.house);
        if (it) lessonSend(it.patch(c.checked));
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
