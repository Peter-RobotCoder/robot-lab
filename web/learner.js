// The learner's tabs (CHANGE 134), as the learner window's side panel has them (engine/hud.py and each game's
// window): Mission (the objectives with their guidance dropping down, ticks, the reflection boxes, the brain's
// state), the Garage (garage.js: the design's variables as the window's garage draws them, five saved designs), the
// AI card (the request to the teacher, the last three requests and the reviews), My card (the outcomes shown so far
// and what was done each day) and Mods (the votes for the arena's or stage's items and the user mods). The same
// messages the windows send, so the class server can't tell the page from a window.

import {esc, learnerModsHtml} from "./teacher.js";
import {renderGarage} from "./garage.js";

const $ = id => document.getElementById(id);

export const LEARNER_TABS = [["mission", "Mission"], ["garage", "Garage"], ["aicard", "AI card"], ["mycard", "My card"],
                             ["mods", "Mods"]];

// each game's words: what the AI card can change (the games' AI_TARGETS, the teacher-only one left out) and the
// objectives answered in writing (REFLECTIONS)
const GAME_WORDS = {
    robotlab: {targets: {robot: "My robot", arena: "The arena", rules: "The rules"}, reflections: ["2d", "5b"]},
    fightlab: {targets: {fighter: "My fighter", stage: "The stage", rules: "The rules"}, reflections: ["2e", "5b"]},
    kartlab: {targets: {kart: "My kart", track: "The track", rules: "The rules"}, reflections: ["2e", "5b"]},
    citylab: {targets: {driver: "My driver and car", city: "The city", rules: "The rules"}, reflections: ["2e", "5b"]},  // (CHANGE 201)
    craftlab: {targets: {bot: "My Craft Bot", world: "The world", rules: "The rules"}, reflections: ["5c"]},  // (CHANGE 202: craft_missions)
};

export function renderLearnerTab(app, tab, body) {
    const fn = {mission: missionTab, garage: garageTab, aicard: cardTab, mycard: myCardTab, mods: modsTab}[tab];
    if (!fn) return false;
    fn(app, body);
    return true;
}

function words(app) {
    return GAME_WORDS[app.game ? app.game.id : ""] || GAME_WORDS.robotlab;
}

// ---------- Mission ----------
function missionTab(app, body) {
    const S = app.state, m = S.myMissions;
    if (!m) { body.innerHTML = `<p class="note">Waiting for your mission from the class server…</p>`; return; }
    S.openObjective = S.openObjective ?? null;
    const reflect = new Set(words(app).reflections);
    let html = `<h2>Mission ${esc(m.lesson)}: ${esc(m.title || "")}</h2><div class="objectives">`;
    for (const o of m.missions || []) {
        const open = S.openObjective === o.id;
        html += `<div class="objective ${o.done ? "done" : ""}">
          <button class="objhead" data-obj="${esc(o.id)}"><span class="tick">${o.done ? "✓" : "○"}</span> ${esc(o.id)}. ${esc(o.title)}</button>`;
        if (open) {
            html += `<div class="objbody">${esc(o.text || "").replace(/\n/g, "<br>")}`;
            if (o.done && o.detail) html += `<div class="note ok">${esc(o.detail)}</div>`;
            if (o.check === "teacher" && !o.done) html += `<div class="note">Your teacher ticks this one.</div>`;
            if (reflect.has(o.id) && !o.done) {
                html += `<textarea id="reflect-${esc(o.id)}" rows="4" placeholder="Write your answer here">${esc((m.text || {})[o.id] || "")}</textarea>
                  <div class="row"><button data-reflect="${esc(o.id)}" class="go">Save</button></div>`;
            }
            html += `</div>`;
        }
        html += `</div>`;
    }
    html += `</div>`;
    // Kart Lab's own row (kart_client build_missions, CHANGE 143): the lap time predicted before a race, in Mission 2
    // (predict, test, compare) or once a prediction is kept
    const have = m.prediction ?? null;
    if (app.game && app.game.id === "kartlab" && (m.lesson === 2 || have !== null)) {
        html += `<h3>My predicted lap time</h3>
          <p class="note">Look at your kart's stats, then predict one lap in seconds. Race, then compare.</p>
          <div class="row"><input id="predict-lap" type="number" min="0" max="500" step="0.1" style="width: 6em" value="${have === null ? "" : esc(have)}">
            <span class="note">seconds</span><button id="btn-predict" class="go">Save</button></div>
          ${have !== null ? `<p class="ok">Predicted: ${esc(Number(have))} s${m.best_lap ? `   your best lap so far: ${Number(m.best_lap).toFixed(1)} s` : ""}</p>` : ""}`;
    }
    if (m.brain || m.brain_error || (m.lesson >= 3)) {
        html += `<h3>Your brain</h3><p class="note">${m.brain ? "A brain is uploaded." : "No brain uploaded yet."}
          ${m.autopilot ? " Autopilot is ON (P turns it off)." : ""}</p>`;
        if (m.brain_error) html += `<p class="note bad">${esc(m.brain_error)}</p>`;
        html += `<div class="row">${app.openBrainEditor ? `<button id="btn-brain-edit" class="go">Edit my brain</button>` : ""}
          <label class="filebtn">Upload a brain (.py)<input type="file" id="brain-file" accept=".py,.txt" hidden></label>
          <button id="btn-autopilot">${m.autopilot ? "Autopilot off" : "Autopilot on"}</button></div>`;
    }
    body.innerHTML = html;
    body.querySelectorAll("button[data-obj]").forEach(b => b.onclick = () => {
        S.openObjective = S.openObjective === b.dataset.obj ? null : b.dataset.obj;
        app.renderPanel();
    });
    body.querySelectorAll("button[data-reflect]").forEach(b => b.onclick = () => {
        const id = b.dataset.reflect;
        app.send({type: "reflection", mission: id, text: $("reflect-" + id).value});
        app.toast("Saved.");
    });
    if ($("btn-predict")) $("btn-predict").onclick = () => {
        const value = parseFloat($("predict-lap").value);
        if (!Number.isFinite(value)) return app.toast("Type the lap time you predict, in seconds (for example 42)");
        app.send({type: "prediction", value});
    };
    if ($("btn-brain-edit")) $("btn-brain-edit").onclick = () => app.openBrainEditor();  // (the page's brain editor: app.js, brain.js)
    if ($("brain-file")) $("brain-file").onchange = e => uploadBrain(app, e.target.files[0]);
    if ($("btn-autopilot")) $("btn-autopilot").onclick = () => app.send({type: "autopilot"});
}

export async function uploadBrain(app, file) {
    if (!file) return;
    const text = await file.text();
    app.send({type: "brain", source: text});
    app.toast(`Sent ${file.name} to the class server.`);
}

// ---------- Garage ----------
// the window's garage (engine/garage.py from the game's schema, and the window's own sections: garage.js)
function garageTab(app, body) {
    renderGarage(app, body, {pre: "gz"});
}

// ---------- AI card ----------
function cardTab(app, body) {
    const S = app.state, m = S.myMissions || {}, L = S.lesson || {};
    const W = words(app), targets = W.targets;
    S.card = S.card || {goal: "", variables: "", test: "", predict: "", privacy: false, review: false, credit: false,
                        target: Object.keys(targets)[0]};
    const c = S.card;
    let html = `<h2>AI card</h2>
      <p class="note">Ask for a change to the game. Your teacher reads every card and decides what goes to Claude.
        Never put anything personal on a card.</p>`;
    if (L.ai_card_note) html += `<div class="objective"><b>From your teacher:</b> ${esc(L.ai_card_note)}</div>`;
    html += `<h3>What should change?</h3><div class="row">${Object.entries(targets).map(([k, n]) =>
        `<button data-target="${k}" class="${c.target === k ? "on" : ""}">${esc(n)}</button>`).join("")}</div>
      <div class="formgrid wide">
        <label>My idea</label><textarea id="ai-goal" rows="3">${esc(c.goal)}</textarea>
        <label>Variables</label><textarea id="ai-variables" rows="2" placeholder="the names and values it should change">${esc(c.variables)}</textarea>
        <label>How I will test it</label><textarea id="ai-test" rows="2">${esc(c.test)}</textarea>
        <label>What I predict</label><textarea id="ai-predict" rows="2">${esc(c.predict)}</textarea>
      </div>
      <div class="ticks">
        <label><input type="checkbox" id="ai-privacy" ${c.privacy ? "checked" : ""}> Nothing personal is on this card</label>
        <label><input type="checkbox" id="ai-review" ${c.review ? "checked" : ""}> I will check what comes back</label>
        <label><input type="checkbox" id="ai-credit" ${c.credit ? "checked" : ""}> I will say the AI helped</label>
      </div>
      <div class="row"><button id="ai-send" class="go">SEND TO THE TEACHER</button></div>`;
    if (S.cardResult) html += `<div class="note ${S.cardResult.ok ? "ok" : "bad"}">${esc(S.cardResult.text)}</div>`;
    // the last three requests, as the window's card_list: the card's words are under card (teaching.submit_card),
    // and the first one kept ("ready") has the review questions under it ({key: question}: the answers go back
    // keyed the same, CHANGE 143)
    const mine = (m.cards || []).slice(-3), questions = Object.entries(m.review_questions || {});
    if (mine.length) {
        html += `<h3>My last requests</h3>`;
        for (const k of mine) {
            const done = ["ready", "reviewed"].includes(k.status);
            html += `<div class="objective"><b class="${done ? "ok" : ""}">#${esc(k.id)} ${esc(String(k.status || "").toUpperCase())}: ${esc((k.card || {}).goal || "")}</b>
              ${k.note ? `<div class="note">Teacher: ${esc(k.note)}</div>` : ""}`;
            if (k.status === "ready") {
                if (k.acknowledgement) html += `<div class="note">${esc(k.acknowledgement)}</div>`;
                html += questions.map(([q, text]) => `<label class="note">${esc(text)}</label><textarea id="rv-${esc(k.id)}-${esc(q)}" rows="2"></textarea>`).join("") +
                    `<div class="row"><button data-review="${esc(k.id)}" class="go">SUBMIT MY REVIEW</button></div></div>`;
                break;  // (the window stops at the card being reviewed)
            }
            html += `</div>`;
        }
    }
    body.innerHTML = html;
    const keep = () => {
        for (const k of ["goal", "variables", "test", "predict"]) c[k] = $("ai-" + k).value;
        for (const k of ["privacy", "review", "credit"]) c[k] = $("ai-" + k).checked;
        app.keepPrefs && app.keepPrefs({card: c, card_target: c.target});
    };
    body.querySelectorAll("textarea[id^='ai-'], input[id^='ai-']").forEach(el => el.addEventListener("change", keep));
    body.querySelectorAll("button[data-target]").forEach(b => b.onclick = () => { keep(); c.target = b.dataset.target; app.renderPanel(); });
    $("ai-send").onclick = () => {
        keep();
        app.send({type: "ai_card", card: {goal: c.goal, variables: c.variables, test: c.test, predict: c.predict,
                                         privacy: c.privacy, review: c.review, credit: c.credit, target: c.target}});
    };
    body.querySelectorAll("button[data-review]").forEach(b => b.onclick = () => {
        const id = b.dataset.review;  // (the card's number as a number: the server matches it with ==)
        const answers = Object.fromEntries(questions.map(([q]) => [q, ($(`rv-${id}-${q}`) || {}).value || ""]));
        app.send({type: "ai_review", id: Number(id), answers});
    });
}

// ---------- My card ----------
function myCardTab(app, body) {
    const card = (app.state.myMissions || {}).card;
    if (!card) { body.innerHTML = `<p class="note">Your card fills in as you complete objectives.</p>`; return; }
    // {outcomes: {code: how many objectives showed it}, outcome_names: {code: name}, history} (teaching.card_data)
    const shown = Object.entries(card.outcomes || {}).filter(([, n]) => n > 0);
    let html = `<h2>My card</h2><h3>Outcomes shown so far</h3>`;
    html += shown.length
        ? `<table>${shown.map(([o, n]) => `<tr><td>${esc(o)}</td><td>${esc((card.outcome_names || {})[o] || "")}</td><td class="note">${n}</td></tr>`).join("")}</table>`
        : `<p class="note">None yet.</p>`;
    const history = card.history || [];
    if (history.length) {
        html += `<h3>What I did</h3>`;
        for (const day of history) {
            html += `<div class="objective"><b>${esc(day.date)}</b><ul>${(day.missions || []).map(x =>
                `<li>${esc(x.id || "")} ${esc(x.title || "")}${x.detail ? ` <span class="note">${esc(x.detail)}</span>` : ""}</li>`).join("")}</ul></div>`;
        }
    }
    body.innerHTML = html;
}

// ---------- Mods (votes) ----------
function modsTab(app, body) {
    // what's in the vote (missing: in it), what is on, and who has voted, from the lesson message: the window's
    // build_mods (CHANGE 143: an item on but out of the vote shown ON with no tick; Robot Lab's Resident Robots each
    // their own vote; this group's own mods first)
    body.innerHTML = `<h2>Mods</h2>` + learnerModsHtml(app);
    body.querySelectorAll("input[data-avote]").forEach(el => el.onchange = () => {
        app.send({type: "arena_vote", item: el.dataset.avote, on: el.checked});
    });
    body.querySelectorAll("input[data-mvote]").forEach(el => el.onchange = () => {
        app.send({type: "mod_vote", mod: el.dataset.mvote, on: el.checked});
    });
}
