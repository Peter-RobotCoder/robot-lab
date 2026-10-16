// Your brain in the page (CHANGE 143). The windows' U uploads brains/my_brain.py, the starter shipped with each game
// (lab_client, fight_client and kart_client's upload_brain: brains/<username>.py first, else my_brain.py), and P
// switches autopilot on and off. The page has each game's starter too (web/brains/<game>/my_brain.py: copies of the
// games' own, served with the page) and this editor, in the code panel's look: Load starter, Upload (U), Download
// .py, Upload a file. What is typed is kept in this browser for each learner and game (localStorage
// "brain:<game>:<name>"), so U sends the brain the page holds: that draft, else the starter.

import {makeDraggable} from "./drag.js";

const $ = id => document.getElementById(id);
const starters = {};   // game -> the starter's text (once fetched)
let built = false, shownFor = null, sureAt = 0;

function gameId(app) { return app.game ? app.game.id : null; }
function word(app) { return (app.game && app.game.word) || {robotlab: "robot", kartlab: "kart", fightlab: "fighter"}[gameId(app)] || "robot"; }
function draftKey(app) { return `brain:${gameId(app) || "?"}:${app.state.name || ""}`; }

export function brainDraft(app) {
    try { return localStorage.getItem(draftKey(app)); } catch (e) { return null; }
}

function keepDraft(app, text) {
    try { localStorage.setItem(draftKey(app), text); } catch (e) { /* private window: kept while the page is open */ }
}

// the game's starter brain (web/brains/<game>/my_brain.py), or null when it can't be fetched
export async function starterBrain(game) {
    if (!game) return null;
    if (starters[game] !== undefined) return starters[game];
    try {
        const r = await fetch(`brains/${game}/my_brain.py`, {cache: "no-cache"});
        if (!r.ok) return null;
        starters[game] = await r.text();
        return starters[game];
    } catch (e) { return null; }
}

// the teacher's Autopilot tick in Controls (CHANGE 99): off, U and P do nothing for learners (the windows' brains_on)
export function brainsOn(app) {
    const S = app.state;
    if (S.role !== "learner" || ((S.lesson || {}).tools || {}).brains !== false) return true;
    app.toast("Brains aren't switched on for this mission yet.");
    return false;
}

export function sendBrain(app, text, name = "my_brain.py") {
    if (!brainsOn(app)) return false;
    if (!text || !text.trim()) { app.toast("That brain is empty."); return false; }
    app.send({type: "brain", source: text});
    app.toast(`Uploading ${name}...`);  // (the server's brain_result says how it went)
    say(`Sent to the class server: it checks it, then says whether your ${word(app)} can use it.`, true);
    return true;
}

// U: the brain the page holds (this learner's draft, else the game's starter), or a file chosen when there is none
export async function uploadMyBrain(app, pick) {
    if (!brainsOn(app)) return;
    const open = built && !$("brainpanel").hidden;
    let text = open ? $("brain-text").value : brainDraft(app);
    if (!text) text = await starterBrain(gameId(app));
    if (text) sendBrain(app, text);
    else pick();
}

// ---------- the editor ----------
function build(app) {
    if (built) return;
    built = true;
    const el = document.createElement("div");
    el.id = "brainpanel";
    el.hidden = true;
    el.innerHTML = `
      <header><span class="dots"><i></i><i></i><i></i></span><b id="brain-title">YOUR BRAIN</b><span id="brain-file">my_brain.py</span>
        <span class="spacer"></span><button id="brain-close" title="Close">✕</button></header>
      <div class="note" id="brain-help"></div>
      <textarea id="brain-text" spellcheck="false" wrap="off" autocomplete="off" autocapitalize="off"></textarea>
      <div class="row"><button id="brain-starter">Load starter</button><button id="brain-upload" class="go">Upload</button>
        <button id="brain-auto">Autopilot (P)</button><button id="brain-download">Download .py</button>
        <label class="filebtn">Upload a file<input type="file" id="brain-pick" accept=".py,.txt" hidden></label></div>
      <div id="brain-msg"></div>`;
    document.body.append(el);
    const ta = $("brain-text");
    ta.addEventListener("input", () => keepDraft(app, ta.value));
    ta.addEventListener("keydown", e => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); sendBrain(app, ta.value); }
        else if (e.key === "Escape") { e.preventDefault(); ta.blur(); }
        else if (e.key === "Tab") { e.preventDefault(); document.execCommand("insertText", false, "    "); }
    });
    $("brain-close").onclick = () => closeBrainEditor();
    $("brain-upload").onclick = () => sendBrain(app, ta.value);
    $("brain-auto").onclick = () => { if (brainsOn(app)) app.send({type: "autopilot"}); };
    $("brain-starter").onclick = async () => {
        const starter = await starterBrain(gameId(app));
        if (starter === null) return say("The starter brain couldn't be fetched: is the page still connected?", false);
        if (ta.value.trim() && ta.value !== starter && Date.now() - sureAt > 4000) {
            sureAt = Date.now();
            return say("Load starter again to replace what is here with the starter brain (download yours first to keep it).", false);
        }
        sureAt = 0;
        ta.value = starter;
        keepDraft(app, starter);
        say("The starter brain: change it, then Upload.", true);
    };
    $("brain-download").onclick = () => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([ta.value], {type: "text/x-python"}));
        a.download = "my_brain.py";
        document.body.append(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
    };
    $("brain-pick").onchange = async e => {
        const file = e.target.files[0];
        e.target.value = "";
        if (!file) return;
        const text = await file.text();
        ta.value = text;
        keepDraft(app, text);
        sendBrain(app, text, file.name);
    };
    makeDraggable(el, "brainpanel", {handle: "header", resize: true, minW: 320, minH: 240});
}

function say(text, ok) {
    const m = $("brain-msg");
    if (!m) return;
    m.textContent = text;
    m.className = ok ? "ok" : "bad";
}

// open the editor on this learner's draft (or the starter); open already: closed (as C toggles the code panel)
export async function openBrainEditor(app, toggle = false) {
    build(app);
    const el = $("brainpanel");
    if (toggle && !el.hidden) { closeBrainEditor(); return; }
    el.hidden = false;
    const key = draftKey(app);
    $("brain-title").textContent = `YOUR ${word(app).toUpperCase()}'S BRAIN`;
    $("brain-upload").textContent = `Upload to my ${word(app)} (U)`;
    $("brain-help").textContent = `Python that runs 60 times a second while autopilot is on. Upload it (U, or Ctrl+Enter), ` +
        `then P switches autopilot on and off. Kept in this browser as you type.`;
    if (shownFor !== key) {
        shownFor = key;
        say("", true);
        const draft = brainDraft(app);
        $("brain-text").value = draft !== null ? draft : "Fetching the starter brain…";
        if (draft === null) {
            const starter = await starterBrain(gameId(app));
            if (shownFor !== key) return;
            $("brain-text").value = starter !== null ? starter : "";
            if (starter === null) say("The starter brain couldn't be fetched: write yours here, or Upload a file.", false);
        }
    }
}

export function closeBrainEditor() {
    if (built) $("brainpanel").hidden = true;
}

// another game or learner: the editor (if open) shows theirs
export function brainEditorChanged(app) {
    if (!built) return;
    shownFor = null;
    if (!$("brainpanel").hidden) openBrainEditor(app);
}
