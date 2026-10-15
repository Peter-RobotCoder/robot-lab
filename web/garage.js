// The Garage and the code panel (CHANGE 135), as the game windows draw them: the tables from the game's design
// schema (engine/garage.py: STRING VARIABLES, VARIABLE LISTS, INTEGER VARIABLES), the window's own sections (Fight
// Lab's detailed look and combo editor), the stats readout, the five saved designs and BUILD; and the design as
// Python code (engine/schema.py through schema.js), edited and applied as the window's code panel does, in an
// editor drawn as the promo videos' code window (CHANGE 138).
//
// What is edited is the window's "draft": a copy of the design, built when BUILD sends it. BUILD sends what the
// window sends ({type: "design", design, code}: code is true when the draft holds a value changed in the code), so
// the class server, the teacher's Warnings and the missions ("hack the code") see the page as a window.
//
// who: null for your own design (a learner's, or the teacher's own with the widest limits); a learner's name, "*all"
// or "*cpu" for the teacher's Learner view (every row shown, with a "learner sees" box for each tool); "*cpu2" to
// "*cpu4" are Robot Lab's other computer robots (CHANGE 140).

import * as SC from "./schema.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const copy = x => JSON.parse(JSON.stringify(x ?? null));
const COLOUR = {red: "var(--red)", orange: "#ffb050", green: "var(--green)", grey: "var(--grey)", white: "var(--text)"};
const rgb = c => `rgb(${(c || [0, 0, 0]).slice(0, 3).map(v => Math.max(0, Math.min(255, Number(v) || 0))).join(",")})`;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function pyRound(x) {  // Python's round(): halves to even
    const f = Math.floor(x), d = x - f;
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
}

export function gameSchema(app) {
    const S = app.state;
    return S.schemas && app.game ? S.schemas[app.game.id] || null : null;
}

// ---------- what the garage edits, with which tools and limits (each window's cur(), tools(), limits()) ----------
function teacherRole(app) { return app.state.role !== "learner"; }

const isCpu = who => /^\*cpu\d?$/.test(who || "");

// the computer's robot or fighter a pick is ("*cpu": the first, or the only one; "*cpu2": Robot Lab's n 2), or null
export function cpuOf(app, who) {
    if (!isCpu(who)) return null;
    const n = Number(who.slice(4) || 1);
    return (app.state.classList || []).find(p => p.role === "computer" && (p.n || 1) === n) || null;
}

export function draftOf(app, who = null) {
    const S = app.state;
    if (!who) {
        if (!S.draft && S.myDesign) S.draft = copy(S.myDesign);
        return S.draft;
    }
    S.viewDrafts = S.viewDrafts || {};
    if (!S.viewDrafts[who]) {
        const people = S.classList || [];
        const base = isCpu(who) ? (cpuOf(app, who) || {}).design
            : who === "*all" ? (S.myDesign || {})  // ("All learners" starts from the teacher's own: CHANGE 85)
            : (people.find(p => p.name === who) || {}).design;
        S.viewDrafts[who] = copy(base || S.myDesign || {});
    }
    return S.viewDrafts[who];
}

export function toolsOf(app) {
    const S = app.state, L = S.lesson || {}, R = S.rules || {};
    if (!teacherRole(app)) return L.tools || {};
    const all = {};
    for (const k of Object.keys(L.tools || {})) all[k] = true;
    if (app.game.id === "robotlab") all.weapons = Object.keys(R.weapons || {});
    if (app.game.id === "fightlab") all.specials = Object.keys(R.specials || {});
    return all;
}

export function limitsOf(app, who = null) {
    const G = gameSchema(app), S = app.state, L = S.lesson || {}, R = S.rules || {};
    if (teacherRole(app) && !who) return R.full || SC.fullLimits(G);
    return L.limits || SC.defaultLimits(G);
}

function ctxOf(app, who, d) {
    const S = app.state;
    const name = who === "*all" ? "every learner" : isCpu(who) ? ((cpuOf(app, who) || {}).name || "the computer") : who;
    return SC.codeCtx(gameSchema(app), {rules: S.rules || {}, tools: toolsOf(app), limits: limitsOf(app, who), design: d,
                                        who: name, makers: (S.mods || {}).makers || {}});
}

// ---------- the Garage ----------
// opts: {who, pre (the element ids' start), title, build (design) -> sends it, after (html under BUILD), slots}
export function renderGarage(app, box, opts = {}) {
    const S = app.state, G = gameSchema(app), who = opts.who || null, pre = opts.pre || "gz";
    const d = draftOf(app, who);
    if (!G || !d) { box.innerHTML = `<p class="note">Waiting for your ${esc(app.game ? app.game.word : "design")}…</p>`; return; }
    const R = S.rules || {}, L = S.lesson || {}, tools = toolsOf(app), limits = limitsOf(app, who);
    const teacher = teacherRole(app), view = !!who, word = app.game.word, WORD = word.toUpperCase();
    const ctx = ctxOf(app, who, d);
    const T = SC.garageTables(G, d, ctx, tools, limits, {view, teacher: teacher && !who});
    const ticked = new Set(), seen = L.tools || {};
    const tick = tool => {  // (the teacher's Learner view: whether the learner sees and changes this)
        if (!view || !tool || ticked.has(tool)) return "";
        ticked.add(tool);
        return `<label class="sees"><input type="checkbox" data-sees="${esc(tool)}" ${seen[tool] ? "checked" : ""}> learner sees</label>`;
    };
    const title = opts.title || (who === "*all" ? `EVERY LEARNER'S ${WORD}` : isCpu(who) ? `${esc(ctx.title)}` : who ? `${esc(who.toUpperCase())}'S ${WORD}`
                                 : teacher ? `MY ${WORD}` : `GARAGE  -  your ${word} as variables`);
    let html = `<h2 class="gtitle">${title}</h2>`;
    if (app.game.id === "kartlab") html += `<p class="note">${esc(limits.points_total)} points between top speed, acceleration and grip: every choice is a trade-off.</p>`;
    if (!S.customColour && Array.isArray(d.colour) && !(G.consts.swatches || []).some(c => same(c, d.colour))) S.customColour = copy(d.colour);
    // STRING VARIABLES
    if (T.strings.length) html += `<div class="ghead" title="Text: letters, numbers and spaces in quotes">STRING VARIABLES</div>
        <div class="gcols"><span>STRING NAME</span><span>STRING VALUE</span></div>`;
    for (const row of T.strings) {
        const v = G.vars.find(x => x.name === row.name);
        html += `<div class="grow"><span class="gname">${esc(row.name)}</span>`;
        html += row.kind === "str"
            ? `<input id="${pre}-name" data-str="${esc(row.name)}" maxlength="${v.max_len}" value="${esc(row.text)}">`
            : `<span class="gvalue">${esc(row.text)}</span>`;
        html += `${tick(row.tool)}</div>`;
        if (row.choose) {
            html += `<div class="gchoose"><span class="note">choose:</span><div class="gbtns" style="grid-template-columns: repeat(${row.perRow}, auto)">` +
                row.choose.map((o, i) => `<button data-choice="${esc(row.name)}" data-i="${i}" class="${o.on ? "on" : ""}">${esc(o.text)}</button>`).join("") + `</div></div>`;
        } else if (row.chosenByTeacher) html += `<div class="note gsub">(chosen by the teacher this mission)</div>`;
        if (row.describe) html += `<div class="note gsub">${esc(row.describe).replace(/\n/g, "<br>")}</div>`;
        if (row.extra === "look_section") html += lookSection(app, d, teacher, tools);
    }
    // VARIABLE LISTS
    if (T.lists.length) html += `<div class="ghead" title="A list: values in order, in square brackets">VARIABLE LISTS</div>`;
    for (const row of T.lists) {
        html += `<div class="grow"><span class="gname">${esc(row.name)}</span><span class="gtype">list</span>${tick(row.tool)}</div>
          <div class="gcode">${esc(row.text)}</div>`;
        if (row.kind === "rgb") {
            const blocks = (G.consts.swatches || []).concat([S.customColour || null]);
            html += `<div class="swatches">` + blocks.map((c, i) => c === null
                ? `<span class="swatch empty" title="a colour typed in the code goes here">custom</span>`
                : `<button class="swatch ${same(c, d.colour) ? "on" : ""}" data-colour="${i}" style="background:${rgb(c)}" title="${esc(row.name)} = [${c.join(", ")}]"></button>`).join("") + `</div>`;
        }
        if (row.extra === "combo_section") html += comboSection(app, d, teacher, tools);
    }
    // INTEGER VARIABLES
    if (T.points || T.settings.length) html += `<div class="ghead" title="Whole numbers">INTEGER VARIABLES</div>`;
    if (T.points) {
        const P = T.points;
        html += `<div class="grow"><b style="color:${P.over ? "var(--red)" : "var(--text)"}">Points</b>
            <span class="note" style="color:${P.over ? "var(--red)" : "var(--grey)"}">(${P.used} of ${P.total} used, ${P.total - P.used} left)</span>${tick(P.rows[0] && P.rows[0].tool)}</div>
          <div class="gcols"><span>VARIABLE NAMES</span><span>VARIABLE VALUE</span><span>share</span></div>`;
        for (const p of P.rows) {
            const val = Number(p.value) || 0;
            html += `<div class="grow gpoints"><span class="gname">${esc(p.name)}</span>
              <button data-pts="${esc(p.stat)}" data-d="-5">-5</button><button data-pts="${esc(p.stat)}" data-d="-1">-</button>
              <span class="gnum">${esc(SC.pyStr(p.value))}</span>
              <button data-pts="${esc(p.stat)}" data-d="1">+</button><button data-pts="${esc(p.stat)}" data-d="5">+5</button>
              <span class="gbar"><i style="width:${(100 * Math.min(val, p.most) / p.most).toFixed(1)}%"></i></span></div>`;
        }
    }
    if (T.settings.length) {
        html += `<div class="grow"><b>Settings</b> <span class="note">(percent)</span></div>
          <div class="gcols"><span>VARIABLE NAMES</span><span>VARIABLE VALUE</span></div>`;
        for (const s of T.settings) {
            html += `<div class="grow"><span class="gname">${esc(s.name)}</span>`;
            html += s.fixed ? `<span class="note">${esc(s.text)}  (set by the teacher)</span>`
                : `<input type="range" class="gslider" data-set="${esc(s.key)}" min="${s.lo}" max="${s.hi}" step="any" value="${clamp(Number(s.value) || 0, s.lo, s.hi)}">
                   <span class="gnum" id="${pre}-set-${esc(s.key)}">${esc(s.text)}</span>`;
            html += `${tick(s.tool)}</div>`;
        }
    }
    if (SC.showsStats(G, d, tools)) html += `<div class="grow">${tick("stats_readout")}</div><pre class="gstats" id="${pre}-stats">${esc(SC.statsText(G, d))}</pre>`;
    if (!who) html += slotsHtml(app);
    else if (opts.loadFrom) html += opts.loadFrom;
    const label = opts.buildLabel || (who === "*all" ? "BUILD FOR ALL LEARNERS" : isCpu(who) ? `BUILD ${esc(ctx.title.replace(/'S \w+$/, ""))}` : who ? `${app.game.id === "robotlab" ? "REBUILD" : "BUILD"} FOR ${esc(who.toUpperCase())}`
                                      : `${app.game.id === "robotlab" ? "REBUILD" : "BUILD"} MY ${WORD}`);
    html += `<div class="row"><button id="${pre}-build" class="go">${label}</button>${opts.codeButton !== false ? `<button id="${pre}-code">Code (C)</button>` : ""}</div>`;
    if (!who && S.garageMsg && S.garageMsg[0]) html += `<div class="note" style="color:${COLOUR[S.garageMsg[1]] || "var(--grey)"}">${esc(S.garageMsg[0])}</div>`;
    if (!teacher && L.designs_locked) html += `<div class="note bad">Designs are locked by the teacher</div>`;
    if (opts.after) html += opts.after;
    box.innerHTML = html;
    wireGarage(app, box, {who, pre, d, ctx, limits, tools, opts});
}

function lookSection(app, d, teacher, tools) {  // fight_client.look_section / build_look: a detailed body's look
    const R = app.state.rules || {}, C = gameSchema(app).consts;
    if (!((R.model_bodies || []).includes(d.body) && (teacher || tools.body_choice))) return "";
    if (!("look" in d)) d.look = copy(C.default_look[d.body]);  // (the window's setdefault: drawing it gives the design a look)
    const look = d.look || {}, human = (R.human_bodies || ["woman", "man"]).includes(d.body);
    const rows = (human ? [["Outfit", "outfit", Object.keys(R.outfits || {})], ["Hair", "hair", (R.hair_styles || {})[d.body] || []]] : [])
        .concat([[human ? "Shape" : "Frame", "shape", Object.keys(R.shapes || {})], ["Win", "win", Object.keys(R.wins || {})]]);
    let html = `<div class="glook">`;
    for (const [text, key, options] of rows) {
        html += `<div class="grow"><span class="gname">${esc(text)}</span><div class="gbtns" style="grid-template-columns: repeat(5, auto)">` +
            options.map(o => `<button data-look="${esc(key)}" data-v="${esc(o)}" class="${look[key] === o ? "on" : ""}">${esc(o)}</button>`).join("") + `</div></div>`;
    }
    const swatchRow = (text, list, current, attr) => `<div class="grow"><span class="gname">${esc(text)}</span><span class="swatches">` +
        list.map((c, i) => `<button class="swatch small ${same(c, current) ? "on" : ""}" ${attr}="${i}" style="background:${rgb(c)}"></button>`).join("") + `</span></div>`;
    if (human) html += swatchRow("Hair colour", C.hair_swatches, look.hair_colour, "data-hair");
    else {
        const style = d.style && typeof d.style === "object" ? d.style : (d.style = {});
        html += swatchRow("Trim", C.trim_swatches, style.trim || (R.robin_style || {}).trim, "data-trim");
        html += swatchRow("Lights", C.light_swatches, style.lights || (R.robin_style || {}).lights, "data-lights");
    }
    const [lo, hi] = R.height || [90, 110], h = look.height ?? 100;
    html += `<div class="grow"><span class="gname">Height</span><input type="range" class="gslider" data-height="1" min="${lo}" max="${hi}" step="any" value="${h}">
      <span class="gnum" id="look-height">${SC.formatF(h, 0)}%</span></div></div>`;
    return html;
}

function comboSection(app, d, teacher, tools) {  // fight_client.combo_section: click a move to change it
    const R = app.state.rules || {};
    if (!(teacher || tools.combo_editor)) return "";
    const combo = d.combo || [];
    return `<div class="note gsub">${R.combo_min} to ${R.combo_max} moves; press A again after each hit. Click a move to change it.</div>
      <div class="gbtns" style="grid-template-columns: repeat(4, auto)">${combo.map((m, i) => `<button data-combo="${i}" class="move">${i + 1}. ${esc(m)}</button>`).join("")}</div>
      <div class="row"><button data-combolen="1">+ add a move</button><button data-combolen="-1">- last move</button></div>`;
}

// the five saved designs (engine/hud.py build_slots): pick a slot, then save, load or delete (asked first)
function slotsHtml(app) {
    const S = app.state, mine = S.slots || {}, word = app.game.word.toUpperCase();
    const n = S.slotPick || 1, held = mine[String(n)];
    let html = `<div class="ghead">SAVED ${word}S <span class="note">pick a slot, then save, load or delete</span></div><div class="row">`;
    for (let k = 1; k <= 5; k++) {
        const h = mine[String(k)];
        html += `<button data-slot="${k}" class="${n === k ? "on" : ""}">${k}: ${esc(h ? h.name : "empty")}</button>`;
    }
    html += `</div><div class="row">`;
    if (S.slotConfirm && S.slotConfirm[1] === n && held) {
        const del = S.slotConfirm[0] === "delete";
        html += `<span style="color:#ffb050">${del ? "Delete" : "Overwrite"} ${esc(held.name)}?</span>
          <button data-slotdo="${del ? "delete" : "save"}" class="${del ? "stop" : "go"}">${del ? "YES, DELETE" : "YES, SAVE"}</button><button data-slotdo="no">No</button>`;
    } else {
        html += `<button data-slotdo="save" style="background:#26739f">SAVE HERE</button>` +
            (held ? `<button data-slotdo="load">LOAD</button><button data-slotdo="delete">DELETE</button>` : "") +
            (S.loadedNote ? `<span class="note ok">${esc(S.loadedNote)}</span>` : "");
    }
    return html + `</div>`;
}

// take a saved design into the garage (engine/hud.py take_design)
export function takeDesign(app, design, who = null) {
    const d = draftOf(app, who);
    for (const k of Object.keys(d)) delete d[k];
    Object.assign(d, copy(design));
    app.state.codeShown = null;
}

function changed(app) {  // (the window: code_shown = None, rebuild_panels)
    app.state.codeShown = null;
    app.renderPanel();
    renderCode(app);
}

function wireGarage(app, box, {who, pre, d, ctx, limits, tools, opts}) {
    const S = app.state, G = gameSchema(app), R = S.rules || {}, id = app.game.id;
    const name = box.querySelector("input[data-str]");
    if (name) name.oninput = () => {  // (the window's name box: kept in the design as it is typed)
        const v = G.vars.find(x => x.name === name.dataset.str);
        SC.setVarAfter(G, v.name, d, Array.from(name.value).slice(0, v.max_len).join(""), ctx);
        renderCode(app);
    };
    box.querySelectorAll("button[data-choice]").forEach(b => b.onclick = () => {
        const row = SC.garageTables(G, d, ctx, tools, limits, {view: !!who, teacher: teacherRole(app) && !who}).strings
            .find(r => r.name === b.dataset.choice);
        SC.setVarAfter(G, b.dataset.choice, d, row.choose[Number(b.dataset.i)].value, ctx);
        changed(app);
    });
    box.querySelectorAll("button[data-colour]").forEach(b => b.onclick = () => {
        const blocks = (G.consts.swatches || []).concat([S.customColour || null]);
        d.colour = copy(blocks[Number(b.dataset.colour)]);
        changed(app);
    });
    box.querySelectorAll("button[data-pts]").forEach(b => b.onclick = () => {  // (each window's change_points)
        const stat = b.dataset.pts, delta = Number(b.dataset.d);
        if (id === "kartlab") {
            const [lo, hi] = (limits.points || {})[stat] || [R.stat_min, R.stat_max];
            d[stat] = clamp(Math.trunc(Number(d[stat] ?? lo)) + delta, lo, hi);
        } else if (id === "fightlab") {
            d.points[stat] = clamp(d.points[stat] + delta, R.stat_min, R.stat_max);
        } else {
            const [lo, hi] = limits.points[stat];
            d.points[stat] = clamp(d.points[stat] + delta, lo, hi);
        }
        changed(app);
    });
    // (a slider being dragged: the panel waits to redraw, or the drag would be dropped)
    box.querySelectorAll("input[type=range]").forEach(el => { el.onpointerdown = () => { S.dragging = true; }; });
    box.querySelectorAll("input[data-set]").forEach(el => el.oninput = () => {  // (each window's slider_moved)
        const k = el.dataset.set, [lo, hi] = limits.settings[k];
        const v = id === "robotlab" ? clamp(pyRound(Number(el.value)), lo, hi) : pyRound(Number(el.value));
        if (id === "kartlab") d[k] = v; else d.settings[k] = v;
        const t = $(`${pre}-set-${k}`);
        if (t) t.textContent = `${SC.formatG(v)}%`;
        const st = $(`${pre}-stats`);
        if (st) st.textContent = SC.statsText(G, d);
        renderCode(app);  // (just the code panel: redrawing the garage would drop the slider)
    });
    box.querySelectorAll("button[data-look]").forEach(b => b.onclick = () => {
        if (!d.look || typeof d.look !== "object") d.look = copy(G.consts.default_look[d.body]);
        d.look[b.dataset.look] = b.dataset.v;
        changed(app);
    });
    const swatchSet = (attr, list, put) => box.querySelectorAll(`button[${attr}]`).forEach(b => b.onclick = () => {
        put(copy(list[Number(b.getAttribute(attr))]));
        changed(app);
    });
    if (G.consts.hair_swatches) {
        swatchSet("data-hair", G.consts.hair_swatches, c => { (d.look = d.look || copy(G.consts.default_look[d.body])).hair_colour = c; });
        swatchSet("data-trim", G.consts.trim_swatches, c => { (d.style = d.style || {}).trim = c; });
        swatchSet("data-lights", G.consts.light_swatches, c => { (d.style = d.style || {}).lights = c; });
    }
    box.querySelectorAll("input[data-height]").forEach(el => el.oninput = () => {
        const v = pyRound(Number(el.value));
        (d.look = d.look || copy(G.consts.default_look[d.body])).height = v;
        const t = $("look-height");
        if (t) t.textContent = `${v}%`;
        renderCode(app);
    });
    box.querySelectorAll("button[data-combo]").forEach(b => b.onclick = () => {
        const moves = Object.keys(R.combo_moves || {}), i = Number(b.dataset.combo), c = d.combo;
        c[i] = moves.includes(c[i]) ? moves[(moves.indexOf(c[i]) + 1) % moves.length] : moves[0];
        changed(app);
    });
    box.querySelectorAll("button[data-combolen]").forEach(b => b.onclick = () => {
        const c = d.combo;
        if (Number(b.dataset.combolen) > 0 && c.length < R.combo_max + 1) c.push("punch");
        else if (Number(b.dataset.combolen) < 0 && c.length > 1) c.pop();
        changed(app);
    });
    box.querySelectorAll("input[data-sees]").forEach(el => el.onchange = () =>
        app.send({type: "lesson", lesson: {tools: {[el.dataset.sees]: el.checked}}}));
    box.querySelectorAll("button[data-slot]").forEach(b => b.onclick = () => {
        S.slotPick = Number(b.dataset.slot);
        S.slotConfirm = null;
        app.renderPanel();
    });
    box.querySelectorAll("button[data-slotdo]").forEach(b => b.onclick = () => {  // (engine/hud.py slot_action)
        const n = S.slotPick || 1, mine = S.slots || {}, held = mine[String(n)], what = b.dataset.slotdo;
        if (what === "no") { S.slotConfirm = null; app.renderPanel(); return; }
        if ((what === "save" || what === "delete") && held && !(S.slotConfirm && S.slotConfirm[0] === what && S.slotConfirm[1] === n)) {
            S.slotConfirm = [what, n];
            app.renderPanel();
            return;
        }
        S.slotConfirm = null;
        if (what === "load") {
            takeDesign(app, held.design);
            S.loadedNote = `Loaded ${held.name} from slot ${n}: press BUILD to use it.`;
            S.formSeq = (S.formSeq || 0) + 1;
            renderCode(app);
        } else if (what === "save") app.send({type: "slot", do: "save", n, design: d});
        else if (what === "delete") app.send({type: "slot", do: "delete", n});
        app.renderPanel();
    });
    const build = $(`${pre}-build`);
    if (build) build.onclick = () => (opts.build ? opts.build(d) : buildMine(app));
    const code = $(`${pre}-code`);
    if (code) code.onclick = () => toggleCode(app);
}

// BUILD MY ROBOT / FIGHTER / KART: the window's send_design
export function buildMine(app, fromCode = false) {
    const S = app.state, G = gameSchema(app), d = draftOf(app);
    if (!d) return;
    const name = $("gz-name") || $("dz-name");
    const nameTool = app.game.id === "kartlab" ? (toolsOf(app).name_and_colour ?? true) : toolsOf(app).name_and_colour;
    if (name && nameTool) d.name = Array.from(name.value).slice(0, app.game.id === "kartlab" ? 12 : 16).join("");
    app.send({type: "design", design: d, code: !!(fromCode || S.codeHack || S.codeChanged)});
    S.garageMsg = ["Building...", "grey"];
    S.codeBuilding = fromCode && app.game.id === "robotlab";
    if (G) app.renderPanel();
}

// what the window does with a design_result (its own design: built, refused, or changed by the teacher)
export function designResult(app, m) {
    const S = app.state, id = app.game ? app.game.id : "", word = app.game ? app.game.word : "design";
    if (m.design) S.myDesign = m.design;
    if (m.ok !== false) {
        S.draft = copy(S.myDesign);
        S.codeShown = null;
        S.garageMsg = [m.by_teacher ? `Your teacher changed your ${word}.` : id === "robotlab" ? "Built! Your robot is back at its start square."
                       : id === "fightlab" ? "Built! Your fighter is back at the start of the round." : "Built! Your kart has its new design.", "green"];
        if (S.codeBuilding) S.codeMsg = ["Built from your code! Your robot is back at its start square.", "green"];
    } else {
        S.garageMsg = ["Not built: " + (m.problems || []).join("; "), "red"];
        if (S.codeBuilding) S.codeMsg = S.garageMsg;
    }
    S.codeBuilding = S.codeHack = S.codeChanged = false;
    renderCode(app);
}

// ---------- the code panel (each window's build_code_panel, apply_code, reset_code) ----------
function codeAllowed(app) {
    const t = toolsOf(app);
    return teacherRole(app) || (app.game.id === "kartlab" ? (t.code_view ?? true) : !!t.code_view);
}

export function toggleCode(app) {  // C, or the garage's Code button (the window's toggle_code)
    const S = app.state;
    if (!gameSchema(app) || !draftOf(app)) { app.toast("Your design hasn't arrived yet."); return; }
    S.showCode = !S.showCode;
    if (S.showCode && !teacherRole(app)) app.send({type: "code_viewed"});
    if (S.showCode && !codeAllowed(app)) app.toast("Your teacher hasn't switched the code view on this mission.");
    S.codeShown = null;
    renderCode(app);
}

export function renderCode(app) {
    const S = app.state, el = $("codepanel");
    if (!el) return;
    const G = gameSchema(app), d = G && draftOf(app);
    if (!S.showCode || !G || !d || !S.connected || !codeAllowed(app)) { el.hidden = true; return; }
    el.hidden = false;
    const ctx = ctxOf(app, null, d), word = app.game.word.toUpperCase();
    const fresh = SC.codeLines(G, d, ctx).join("\n");
    if (S.codeShown === null || S.codeShown === undefined || S.codeText === S.codeShown) {  // (not edited: the design as it is)
        S.codeText = fresh;
        S.codeShown = fresh;
        S.codeErr = null;
    }
    $("code-title").textContent = `YOUR ${word} AS PYTHON CODE`;
    if ($("code-file")) $("code-file").textContent = `my_${app.game.word.toLowerCase()}.py`;
    $("code-rebuild").textContent = app.game.id === "robotlab" ? "REBUILD MY ROBOT" : `BUILD MY ${word}`;
    const ta = $("code-text");
    if (ta.value !== S.codeText) ta.value = S.codeText;
    paint();
    const msg = S.codeMsg || ["", "grey"];
    $("code-msg").textContent = msg[0];
    $("code-msg").style.color = COLOUR[msg[1]] || "var(--grey)";
}

let app_ = null;

// ---------- the code panel as an editor (CHANGE 138): the promo videos' code window ----------
// The Python is drawn highlighted in a <pre> (#code-hl) under the textarea, whose own text is transparent (only its
// caret and selection show): the same font, lines and padding, moved with the textarea's scroll. Under both, a bar
// on the cursor's line and one on the mistake's; a bracket beside the cursor is marked with its partner.
const PY_KEYWORDS = new Set(("False None True and as assert async await break case class continue def del elif else except " +
    "finally for from global if import in is lambda match nonlocal not or pass raise return try while with yield").split(" "));
const PY_TYPES = new Set("int float str list dict tuple set bool bytes".split(" "));
// comment | string (any prefix; triple-quoted across lines; one left open runs to the line's end, or the text's) | name | number | bracket
const PY_TOKEN = /(#[^\n]*)|((?:[rRbBuUfF]{1,2})?(?:'''[\s\S]*?(?:'''|$)|"""[\s\S]*?(?:"""|$)|'(?:[^'\\\n]|\\[\s\S])*'?|"(?:[^"\\\n]|\\[\s\S])*"?))|([A-Za-z_]\w*)|((?:0[xXoObB][\da-fA-F_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?[jJ]?))|([()[\]{}])/g;
const CALL = /[ \t]*\(/y;

export function codeTokens(text) {  // [[start, end, class]] and each bracket's partner (exported for the test)
    const tokens = [], pairs = new Map(), open = [];
    let m, before = "";
    PY_TOKEN.lastIndex = 0;
    while ((m = PY_TOKEN.exec(text))) {
        const s = m.index, e = s + m[0].length;
        let c = m[1] ? "c" : m[2] ? "s" : m[4] ? "n" : m[5] ? "p" : null;
        if (m[3]) {
            CALL.lastIndex = e;
            c = PY_KEYWORDS.has(m[3]) ? "k" : (before === "def" || before === "class" || CALL.test(text)) ? "f" : PY_TYPES.has(m[3]) ? "t" : null;
            before = m[3];
        } else before = "";
        if (m[5]) {
            if ("([{".includes(m[5])) open.push(s);
            else if (open.length && text[open[open.length - 1]] === {")": "(", "]": "[", "}": "{"}[m[5]]) {
                const o = open.pop();
                pairs.set(o, s).set(s, o);
            }
        }
        if (c) tokens.push([s, e, c]);
        if (!m[0].length) PY_TOKEN.lastIndex++;
    }
    return {tokens, pairs};
}

const HL = {text: null, tokens: [], pairs: new Map(), marks: null, gutter: null};

function paint() {  // the highlighted text, the gutter, the bars, all where the textarea's scroll puts them
    const ta = $("code-text"), hl = $("code-hl");
    if (!ta || !hl) return;
    const S = app_ && app_.state, text = ta.value;
    if (HL.text !== text) Object.assign(HL, {text, marks: null}, codeTokens(text));
    const at = ta.selectionStart === ta.selectionEnd && document.activeElement === ta ? ta.selectionStart : -1;
    const a = at < 0 ? -1 : HL.pairs.has(at - 1) ? at - 1 : HL.pairs.has(at) ? at : -1, b = a < 0 ? -1 : HL.pairs.get(a);
    if (HL.marks !== `${a},${b}`) {
        HL.marks = `${a},${b}`;
        let out = "", i = 0;
        for (const [s, e, c] of HL.tokens) {
            out += esc(text.slice(i, s)) + `<span class="${c}${s === a || s === b ? " mb" : ""}">${esc(text.slice(s, e))}</span>`;
            i = e;
        }
        hl.innerHTML = out + esc(text.slice(i));
    }
    const caret = ta.selectionDirection === "backward" ? ta.selectionStart : ta.selectionEnd;
    const line = text.slice(0, caret).split("\n").length, n = text.split("\n").length, err = S ? S.codeErr : null;
    if (HL.gutter !== `${n},${line},${err}`) {
        HL.gutter = `${n},${line},${err}`;
        let out = "";
        for (let i = 1; i <= n; i++) out += (err === i ? `<b>${i}</b>` : i === line ? `<span class="cur">${i}</span>` : String(i)) + "\n";
        $("code-gutter").innerHTML = out;
    }
    const cs = getComputedStyle(ta), lh = parseFloat(cs.lineHeight) || 20, top = parseFloat(cs.paddingTop) || 0;
    hl.style.transform = `translate(${-ta.scrollLeft}px, ${-ta.scrollTop}px)`;
    $("code-gutter").style.transform = `translateY(${-ta.scrollTop}px)`;
    const bar = (id, lineno) => {
        $(id).hidden = !lineno;
        if (lineno) $(id).style.transform = `translateY(${top + (lineno - 1) * lh - ta.scrollTop}px)`;
    };
    bar("code-curline", line);
    bar("code-errline", err);
}

function selectLine(lineno) {  // the cursor goes to the line with the mistake (as the window's)
    const ta = $("code-text"), lines = ta.value.split("\n");
    let start = 0;
    for (let i = 0; i < lineno - 1 && i < lines.length; i++) start += lines[i].length + 1;
    const end = start + (lines[lineno - 1] || "").length;
    ta.focus();
    ta.setSelectionRange(start, end);
    ta.scrollTop = Math.max(0, (lineno - 4) * parseFloat(getComputedStyle(ta).lineHeight || "18"));
    paint();
}

// APPLY CODE: read the code (schema.js, never run), change the design to match. True if all of it was used.
export function applyCodeNow(app) {
    const S = app.state, G = gameSchema(app), d = draftOf(app);
    if (!G || !d) return false;
    const ctx = ctxOf(app, null, d);
    let r;
    try {
        r = SC.applyCode(G, d, S.codeText ?? "", {ctx, tools: toolsOf(app), limits: limitsOf(app), teacher: teacherRole(app), viewing: null});
    } catch (e) {  // (the window would stop here with Python's error: the page says so and carries on)
        S.codeMsg = [`The code can't be read: ${e.message}`, "red"];
        renderCode(app);
        return false;
    }
    S.codeMsg = [r.message, r.colour];
    if (r.lineno !== undefined) {  // (a line it can't read: the code stays as typed, the mistake is picked out)
        S.codeErr = r.lineno;
        renderCode(app);
        if (r.lineno) selectLine(r.lineno);
        return undefined;
    }
    if (r.message.startsWith("The code is now")) { renderCode(app); return undefined; }
    if (r.codeChanged) S.codeChanged = true;
    if (r.codeHack) S.codeHack = true;
    if (r.changed && r.changed.includes("colour") && Array.isArray(d.colour) && !(G.consts.swatches || []).some(c => same(c, d.colour))) {
        S.customColour = copy(d.colour);  // (the garage's custom block takes it)
    }
    S.codeShown = null;  // (applied, or refused: the code is the design's again)
    S.formSeq = (S.formSeq || 0) + 1;  // (the garage's boxes take the new values)
    app.renderPanel();
    renderCode(app);
    return r.ok;
}

function resetCode(app) {
    const S = app.state, G = gameSchema(app), d = draftOf(app), id = app.game.id, word = app.game.word;
    if (id === "robotlab") {  // (lab_client.reset_code: back to the lesson's starting robot; only the code changes)
        const L = S.lesson || {}, start = L.start_design, mine = S.myDefault || d;
        let base = mine;
        if (start && typeof start === "object" && !Array.isArray(start) && !teacherRole(app)) {
            base = copy(start);
            base.name = mine.name ?? S.name;
            base.colour = mine.colour ?? base.colour;
        }
        S.codeText = SC.codeLines(G, base, ctxOf(app, null, d)).join("\n");
        S.codeMsg = ["The code is back to the starting robot. Press APPLY CODE or REBUILD to use it.", "grey"];
    } else {
        S.codeText = SC.codeLines(G, d, ctxOf(app, null, d)).join("\n");
        S.codeShown = S.codeText;
        S.codeMsg = [`The code is back to your ${word} as it is. Press APPLY CODE or BUILD to use it.`, "grey"];
    }
    S.codeErr = null;
    $("code-text").value = S.codeText;
    renderCode(app);
}

export function setupCodePanel(app) {  // (once, at the start)
    app_ = app;
    const ta = $("code-text"), box = ta.parentNode, gut = document.createElement("div"), edit = document.createElement("div");
    // the editor's window (CHANGE 138): the title bar's three dots and the file's name; the gutter, the bars and the
    // highlighted text under the textarea
    $("codepanel").querySelector("header").insertAdjacentHTML("afterbegin", '<span class="dots"><i></i><i></i><i></i></span>');
    $("code-close").insertAdjacentHTML("beforebegin", '<span id="code-file"></span>');
    gut.className = "gut";
    gut.append($("code-gutter"));
    edit.className = "edit";
    edit.innerHTML = '<div class="line" id="code-curline" hidden></div><div class="line err" id="code-errline" hidden></div><pre id="code-hl" aria-hidden="true"></pre>';
    edit.append(ta);
    box.append(gut, edit);
    ta.addEventListener("input", () => { app.state.codeText = ta.value; paint(); });
    ta.addEventListener("scroll", paint);
    for (const ev of ["keyup", "mouseup", "focus", "blur", "select"]) ta.addEventListener(ev, paint);
    document.addEventListener("selectionchange", () => { if (document.activeElement === ta) paint(); });
    ta.addEventListener("keydown", e => {
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); applyCodeNow(app); }
        else if (e.key === "Escape") { e.preventDefault(); ta.blur(); }
        else if (e.key === "Tab") { e.preventDefault(); document.execCommand("insertText", false, "    "); }
    });
    $("code-apply").onclick = () => applyCodeNow(app);
    $("code-reset").onclick = () => resetCode(app);
    $("code-rebuild").onclick = () => {  // (APPLY CODE, then build: lab's rebuild_from_code, the others' build_from_code)
        if (!applyCodeNow(app)) return;
        if (app.game.id === "robotlab") { app.state.codeMsg = ["Building...", "grey"]; buildMine(app, true); }
        else buildMine(app);
        renderCode(app);
    };
    $("code-close").onclick = () => toggleCode(app);
}
