// Missions in Club Coders Live (CHANGE 199, docs/plans/missions-browser.md steps 3 and 4): the story missions,
// Mission 1 "Wake-Up Call" and Mission 2 "Lights Out", played in 3D on the page as the mission window plays them
// (shared-world-demo/wake_up_call.py), in a class whose Missions server runs them (missions_server.py, CHANGE 198).
// The page never runs a mission itself: it sends the server what the window would, and plays back what comes:
//   start {mission, robot}    the mission from its start (a robot chosen, or RESET): state comes back
//   parse {mission, text}     as the typing pauses: each line's reading, its did-you-mean hint and its Python (parsed),
//                             for the code panel's Pseudo code tab (the Python beside each line) and its Code tab
//   program {mission, text}   RUN: the events come back (ran, each state as only what changed), played here as the
//                             window plays them (its DURATION table and easing, the robot driven, turned, bumping and
//                             using its tool, the scene's animate and landed: missionscene.js, the sounds)
//   mission {mission}         the mission this page is on (the teacher's class list shows it)
// The welcome carries each mission's map, rules, robots, tools and phrasebook (missions_server.about), so the HUD,
// the first screen and the phrasebook are worded from the mission's own Python; the words round them are the
// window's (TEXTS, STARTERS). world and robot: everyone else's robot in the valley, dimmed, their names over them,
// each of their runs played at the page's pace (the window's Ghost); class (the teacher's page): the class's
// progress top right and in the Class tab, where the teacher changes the mission for everyone (lesson).

import {MissionScene, heading, forward, SQ} from "./missionscene.js";
import {MissionHud} from "./hud.js";
import {codeTokens} from "./garage.js";
import {esc} from "./teacher.js";

const $ = id => document.getElementById(id);
// how long each event is animated (seconds): the window's, the prototype's, so a run feels the same
const DURATION = {move: 0.23, turn: 0.2, bump: 0.42, use: 0.65, objective: 0.7, complete: 0.9, flat: 0.6,
                  // (Mission 2's: a night begins, an if's question, a variable changes, the panel, a repair, a report)
                  night: 1.1, check: 0.14, set: 0.12, solar: 0.3, repair: 0.6, report: 0.8, stop: 0.5};
const SERVER_WAIT = 10000;  // ms a run waits for the server's answer before RUN is free again
const ORDER = ["wake_up_call", "lights_out"];  // (the first screen's order, F1 and F2)
const ROBOTS = ["TITAN", "RAZORBACK"];
// zoom 1 is the whole valley; the right mouse button drags the view at most this far past the map's edge (metres)
const ZOOM_MIN = 0.35, ZOOM_MAX = 2.2, PAN_REACH = 8.0;
const VIEWS = ["valley", "follow", "above"];
const VIEW_NAMES = {valley: "the whole valley", follow: "behind your robot", above: "from above"};
const STARTERS = {
    wake_up_call: ["# Wake-Up Call. Write one instruction per line, then press RUN (or Ctrl+Enter).",
                   "# The phrasebook below lists what the robot understands.", "", ""],
    lights_out: ["# Lights Out. Your program runs on three nights: the rocks and the dark lamps change each night.",
                 "# Use if, else and a variable. The phrasebook below lists what the robot understands.", "", ""],
};
// each mission's own words (the window's TEXTS, its line breaks let go: the page wraps them)
const TEXTS = {
    wake_up_call: {
        story: "Your robot has crash-landed in the hills above Brookfield, and the village's power has failed. Its battery is nearly flat. Find a power cell, pick up a tool from the supply crate, clear the rockfall in the pass, reach Brookfield and repair its power supply. You drive it with code.",
        rules: "The whole valley is in view. Every square you drive costs 1 energy; turning and picking up are free; using a tool costs 2 and a repair 3. Stars: one for finishing, one for {energy} or more energy left, one for {lines} or fewer lines of code run. Finishing unlocks a robot part for Mission 2.",
        legend: "Stars: finish   {energy}+ energy left   {lines} or fewer lines run",
        first: "Press C to open the code panel. First objective: find the power cell.",
        stopped: "The run stopped there. Your robot stays where it is: write the next lines and run again.",
        done: "Mission complete: the lights are on all over Brookfield.",
    },
    lights_out: {
        story: "Night has fallen over Brookfield. A storm has brought rocks down on the hill road to the radio mast and put some of its lamps out, in different places every night. One program has to work on three nights: look with if and else, keep count with a variable, and report the count from the mast.",
        rules: "Every run starts from the bottom of the road and plays nights 1, 2 and 3. A square costs 1 energy, the spinner 2, a repair 3; turning, the sensors and variables are free. Stars: one for finishing, one for {energy} or more energy left every night, one for {lines} or fewer lines of code.",
        legend: "Stars: finish   {energy}+ energy every night   {lines} or fewer lines",
        first: "Press C to open the code panel. Your program will run on three nights, from the start each time.",
        stopped: "That night went wrong, so the run stopped. Change the program and run again: every run starts from night 1.",
        done: "Mission complete: one program lit the hill road on all three nights.",
    },
};

const mod = (a, n) => ((a % n) + n) % n;  // (Python's %)
const ease = k => k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// a ran message's events with their whole states again (missions_server.unpack)
export function unpack(before, events) {
    let cur = Object.assign({}, before);
    return events.map(e => {
        cur = Object.assign({}, cur, e.d || {});
        const out = Object.assign({}, e, {state: cur});
        delete out.d;
        return out;
    });
}

// a line of Python coloured as the code panel colours it (garage.js's codeTokens)
function pyHtml(line) {
    let out = "", at = 0;
    for (const [s, e, c] of codeTokens(line).tokens) {
        out += esc(line.slice(at, s)) + `<span class="${c}">${esc(line.slice(s, e))}</span>`;
        at = e;
    }
    return out + esc(line.slice(at));
}

export class MissionsGame {
    static detect(m) { return !!m.runs_here; }  // (the Missions server's welcome: CHANGE 198)

    constructor(app) {
        this.app = app;
        this.id = "missions";
        this.title = "Missions";
        this.word = "robot";
        this.controlKind = null;  // (no keys driven: the robot is driven by the code)
        this.noBrains = true;     // (no brain to upload or autopilot: app.js's keys and key list)
        this.scene = new MissionScene(app.canvas, app.tier, app.engine);
        this.about = {};
        this.mid = null;
        this.A = null;            // this mission's about (its map, rules, robots, tools, phrasebook)
        this.robotName = null;
        this.s = null;            // the mission's state as the server has it (after the last run)
        this.view = null;         // where the robot is drawn: {x, y, h, state}
        this.queue = [];
        this.event = null;
        this.eventT = 0;
        this.playing = false;
        this.waiting = null;      // when a run was sent (performance.now()), until the server answers
        this.result = null;
        this.runLine = null;
        this.parsed = null;
        this.parseSent = this.parseGot = 0;
        this.dirty = false;
        this.codes = {};          // each mission's code, as typed
        this.logRows = [];
        this.ghosts = new Map();  // name -> {name, robot, mission, tool, at, anim, steps}
        this.back = null;
        this.progress = {parts: [], missions: {}};
        this.classMsg = null;
        this.speed = Number(app.params.get("speed")) || 1;  // (the events' pace: the tests play them faster)
        this.cam = {mode: "valley", zoom: 1, pan: [0, 0]};
        this.t = 0;
        this.hud = new MissionHud({reset: () => this.resetMission(), graphics: () => this.openGraphics(), home: () => this.resetCamera()});
        this.listeners = [];
        this.buildDom();
        this.hookMouse();
        document.body.classList.add("missionscreen");
    }

    // ---------- the page's boxes: the first screen, the code panel, the end card, the flat battery ----------
    buildDom() {
        const add = (id, html = "") => {
            const el = document.createElement("div");
            el.id = id;
            el.hidden = true;
            el.innerHTML = html;
            document.body.appendChild(el);
            return el;
        };
        this.introEl = add("missionintro");
        this.codeEl = add("missioncode", `<header><span class="dots"><i></i><i></i><i></i></span><span id="mc-file"></span>
            <button data-mtab="pseudo">Pseudo code</button><button data-mtab="code">Code</button><span class="spacer"></span>
            <button id="mc-close" title="C closes it too">✕</button></header>
          <div id="mc-pseudo" class="mcol">
            <div class="mc-heads"><span>PSEUDO CODE: type one instruction per line</span><span>THE SAME AS PYTHON</span></div>
            <div class="codebox"><pre id="mc-gutter"></pre><textarea id="mc-text" spellcheck="false" wrap="off" autocomplete="off" autocapitalize="off"></textarea><pre id="mc-py" class="mpy"></pre></div>
            <div id="mc-problems"></div>
            <div class="row"><button id="mc-run" class="go">RUN</button><span id="mc-runinfo"></span><span class="spacer"></span><button id="mc-reset" class="mreset">RESET</button></div>
            <div id="mc-book"></div>
          </div>
          <div id="mc-code" class="mcol" hidden><div class="note">YOUR PROGRAM AS PYTHON (read only: change it in the Pseudo code tab)</div><pre id="mc-whole" class="mpy"></pre></div>`);
        this.doneEl = add("missiondone");
        this.flatEl = add("missionflat", `<p>The battery is flat and the robot can't move.<br>Reset the mission (your code is kept) and try a shorter route.</p>
          <button class="mreset">RESET</button>`);
        this.flatEl.querySelector("button").onclick = () => this.resetMission();
        this.tab = "pseudo";
        this.codeEl.querySelectorAll("button[data-mtab]").forEach(b => b.onclick = () => this.openPanel(b.dataset.mtab));
        $("mc-close").onclick = () => this.closePanel();
        $("mc-run").onclick = () => this.runCode();
        $("mc-reset").onclick = () => this.resetMission();
        const ta = $("mc-text");
        ta.addEventListener("input", () => this.typed());
        ta.addEventListener("scroll", () => { $("mc-gutter").scrollTop = $("mc-py").scrollTop = ta.scrollTop; });
        ta.addEventListener("keydown", e => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this.runCode(); }
            else if (e.key === "Tab" && !e.shiftKey) {  // (two spaces: the lines inside a repeat or an if)
                e.preventDefault();
                ta.setRangeText("  ", ta.selectionStart, ta.selectionEnd, "end");
                this.typed();
            } else if (e.key === "Escape") { e.preventDefault(); this.closePanel(); }
        });
    }

    on(el, ev, fn, opts) {
        el.addEventListener(ev, fn, opts);
        this.listeners.push([el, ev, fn, opts]);
    }

    // the wheel zooms, the right mouse button held and dragged pans the view over the map (the window's mouse_drag)
    hookMouse() {
        const canvas = this.app.canvas;
        this.on(canvas, "wheel", e => {
            e.preventDefault();
            this.cam.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, this.cam.zoom * this.app.wheelZoom(e)));
        }, {passive: false});
        this.on(canvas, "contextmenu", e => e.preventDefault());
        this.on(canvas, "pointerdown", e => { if (e.button === 2) this.drag = [e.clientX, e.clientY]; });
        this.on(window, "pointerup", () => { this.drag = null; });
        this.on(window, "pointermove", e => {
            if (!this.drag || !(e.buttons & 2)) { this.drag = null; return; }
            const w = window.innerWidth, h = window.innerHeight, reach = 16 * this.cam.zoom;  // (metres for half the window)
            const dx = (e.clientX - this.drag[0]) / w * 2, dy = -(e.clientY - this.drag[1]) / h * 2;
            this.panBy(-dx * reach * w / h, -dy * reach);
            this.drag = [e.clientX, e.clientY];
        });
    }

    panBy(dx, dy) {
        if (!this.A) return;
        const W = this.A.map[0].length * SQ / 2 + PAN_REACH, H = this.A.map.length * SQ / 2 + PAN_REACH;
        this.cam.pan = [Math.max(-W, Math.min(W, this.cam.pan[0] + dx)), Math.max(-H, Math.min(H, this.cam.pan[1] + dy))];
    }

    // ---------- the class server's messages ----------
    welcome(m) {
        const again = !!this.mid;  // (back after a dropped connection: the same game, its mission carries on)
        this.role = m.role;
        this.name = m.name;
        this.about = m.missions || {};
        this.progress = m.progress && Array.isArray(m.progress.parts) ? m.progress : {parts: [], missions: {}};
        for (const g of this.ghosts.values()) this.scene.dropRobot("ghost " + g.name);
        this.ghosts.clear();  // (the world message says where everyone is now)
        const wanted = ((m.lesson || {}).mission in this.about) ? m.lesson.mission : ORDER.find(k => k in this.about);
        if (!wanted) return;
        this.parseSent = this.parseGot = 0;  // (a reading asked for on the lost connection never comes)
        if (again && this.mid === wanted && this.about[wanted]) {
            this.A = this.about[wanted];
            this.waiting = null;
            if (this.playing && !this.queue.length && !this.event) this.playing = false;
            this.requestParse();
            this.log("Back in the class.", "info");
        } else this.useMission(wanted, true);
        this.classText();
    }

    message(m) {
        switch (m.type) {
            case "lesson": {  // (the teacher chose another mission)
                const mid = (m.lesson || {}).mission;
                if (mid && mid in this.about && mid !== this.mid && !this.playing) {
                    this.useMission(mid);
                    this.log(`Your teacher chose ${this.about[mid].title}.`, "info");
                }
                return;
            }
            case "class":
                this.classMsg = m;
                this.classText();
                if (this.app.state.tab === "class") this.app.renderPanel();
                return;
            case "state":
                if (!m.state || typeof m.state !== "object") return;
                if (m.back) {  // (coming back to the class: the mission carries on once the same robot is chosen)
                    this.back = m;
                    if (this.robotName === m.robot && this.mid === m.mission && !this.playing) this.takeBack();
                    return;
                }
                if (m.mission === this.mid && m.robot === this.robotName && !this.playing) this.adopt(m.state);
                return;
            case "ran":
                this.serverRan(m);
                return;
            case "parsed":
                this.parseGot++;
                if (m.mission === this.mid && this.parseGot >= this.parseSent && !this.dirty) {
                    this.parsed = m;
                    this.refreshCode();
                }
                return;
            case "world":
                for (const r of m.robots || []) {
                    if (r && Array.isArray(r.at) && r.at.length === 4) this.worldRobot({name: r.name, mission: r.mission, robot: r.robot, steps: [["place", ...r.at]]});
                }
                return;
            case "robot":
                this.worldRobot(m);
                return;
        }
    }

    // ---------- the missions: the first screen chooses one ----------
    useMission(mid, first = false) {
        this.mid = mid;
        const A = this.A = this.about[mid];
        const stars = (A.rules || {}).stars || {};
        this.text = Object.fromEntries(Object.entries(TEXTS[mid] || TEXTS.wake_up_call).map(([k, v]) => [k, v.replace("{energy}", stars.energy).replace("{lines}", stars.lines)]));
        this.queue = [];
        this.event = null;
        this.playing = false;
        this.runLine = null;
        this.waiting = null;
        this.closePanel();
        this.closeDone();
        this.flatEl.hidden = true;
        this.scene.setMission(mid, A);
        this.scene.dropRobot("me");
        this.robotName = null;
        this.s = this.view = null;
        if (!(mid in this.codes)) this.codes[mid] = STARTERS[mid].join("\n");
        $("mc-text").value = this.codes[mid];
        $("mc-file").textContent = `${mid}.pseudo`;
        this.renderBook();
        this.parsed = null;
        this.requestParse();
        this.scene.show(this.startState());
        this.updateHud(this.startState());
        this.logRows = [];
        if (!first) this.log(`${A.title} chosen.`, "info");
        else this.hud.log([]);
        this.showIntro();
        if (!first) this.app.send({type: "mission", mission: mid});
        this.app.updatePills();
        if (["missions", "class"].includes(this.app.state.tab)) this.app.renderPanel();
    }

    chooseMission(mid) {
        if (mid !== this.mid && mid in this.about) this.useMission(mid);
    }

    titleText() {
        return this.A ? `MISSION ${this.A.number}: ${this.A.title.toUpperCase()}` : "MISSIONS";
    }

    hasSolar() {
        const solar = this.A && this.A.solar;
        return !!solar && (this.progress.parts || []).includes(solar.id);
    }

    // the mission's start as the page shows it until the server's state comes (the Solar Panel as the server fits it)
    startState() {
        const s = JSON.parse(JSON.stringify(this.A.start));
        if ("solar" in s) s.solar = this.hasSolar();
        return s;
    }

    showIntro() {
        const A = this.A, f = this.introEl;
        if (!A) return;
        let html = `<div class="mi-missions">${ORDER.filter(k => k in this.about).map((k, i) =>
            `<button data-mission="${k}" class="${k === this.mid ? "on" : ""}">F${i + 1}  MISSION ${this.about[k].number}: ${esc(this.about[k].title.toUpperCase())}</button>`).join("")}</div>
          <h1>${esc(this.titleText())}</h1><p class="mi-story">${esc(this.text.story)}</p>
          <p class="mi-choose">Choose your robot (or press 1 or 2)</p><div class="mi-cards">`;
        ROBOTS.forEach((name, i) => {
            const d = A.robots[name], c = d.colour || [200, 200, 200], colour = `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
            html += `<button class="mi-card" data-robot="${name}"><b style="color:${colour}">${i + 1}  ${esc(name)}</b>
              <span class="mi-blurb">${esc(d.blurb || "")}</span>${Object.entries(d.points || {}).map(([stat, v]) =>
                `<span class="mi-stat"><i>${esc(stat)}</i><em style="width:${v * 2.4}px;background:${colour}"></em><i>${v}</i></span>`).join("")}</button>`;
        });
        html += `</div><p class="mi-rules">${esc(this.text.rules)}</p><p class="mi-parts" id="mi-parts">${esc(this.partsText()[0])}</p>`;
        if (this.role === "teacher") html += `<p><button id="mi-watch">WATCH THE CLASS</button> <span class="note">or choose a robot and play too</span></p>`;
        f.innerHTML = html;
        $("mi-parts").className = "mi-parts" + (this.partsText()[1] ? " ok" : "");
        f.querySelectorAll("button[data-mission]").forEach(b => b.onclick = () => this.chooseMission(b.dataset.mission));
        f.querySelectorAll("button[data-robot]").forEach(b => b.onclick = () => this.choose(b.dataset.robot));
        if ($("mi-watch")) $("mi-watch").onclick = () => { f.hidden = true; };
        f.hidden = false;
    }

    // the part Mission 1 unlocks, or Mission 2 uses: [the words, whether it's yours]
    partsText() {
        const A = this.A;
        if (A.solar) {
            return this.hasSolar() ? [`${A.solar.name} fitted (from Mission 1): 1 energy back for every 5 squares you drive.`, true]
                                   : [`No ${A.solar.name} yet: finish Mission 1 to fit one. Mission 2 can be done without it.`, false];
        }
        const unlocked = A.unlock && (this.progress.parts || []).includes(A.unlock.id);
        return [unlocked ? `${A.unlock.name} unlocked: it carries over to Mission 2.` : "", !!unlocked];
    }

    // ---------- choosing a robot ----------
    choose(name) {
        if (!this.A || !ROBOTS.includes(name)) return;
        this.robotName = name;
        this.scene.holdRobot("me", this.A.robots[name], this.name || "", false);
        this.introEl.hidden = true;
        if (this.back && this.back.mission === this.mid && this.back.robot === name) { this.takeBack(); return; }
        this.resetMission();
    }

    takeBack() {
        const back = this.back;
        this.back = null;
        this.resetMission(false);
        this.adopt(back.state);
        this.log("Back in the class: your mission carries on where it was.", "info");
    }

    // The mission back to its start: the robot on its square, the battery, the tools on the crate, the rockfall, the
    // objectives and the stars; the code stays in the editor. Any time after a robot is chosen, even while a run is
    // being played (the playing stops) or after the battery went flat. The server's copy starts again too.
    resetMission(send = true) {
        if (!this.robotName || !this.A) return;
        if (send) this.app.send({type: "start", mission: this.mid, robot: this.robotName});
        this.queue = [];
        this.event = null;
        this.playing = false;
        this.runLine = null;
        this.waiting = null;
        this.bumped = false;
        this.app.sound.stop("tool");
        const s = this.s = this.startState();
        this.view = {x: s.x, y: s.y, h: heading(s.dir), state: s};
        this.holding = s.tool;  // (none in Mission 1; Mission 2's robot has the spinner from the start)
        this.scene.reset();
        this.scene.show(s);
        this.flatEl.hidden = true;
        this.closeDone();
        this.logRows = [];
        const dirs = this.A.dir_names || ["north", "east", "south", "west"];
        if (this.mid === "wake_up_call") {
            this.log(`${this.robotName} wakes up after the crash landing. Battery: ${s.energy} energy. It's facing ${dirs[s.dir]}.`, "info");
        } else {
            this.log(`${this.robotName} waits at the bottom of the hill road, facing ${dirs[s.dir]} up it, with ${s.energy} energy and the front spinner.`
                     + (s.solar ? " The Solar Panel is fitted." : ""), "info");
        }
        this.log(this.text.first, "info");
        this.updateHud(s);
        this.refreshCode();
    }

    // the mission as the class server has it: the robot, the place, the HUD and the code panel shown as that state says
    adopt(s) {
        if (!this.robotName) return;
        this.s = JSON.parse(JSON.stringify(s));
        this.view = {x: s.x, y: s.y, h: heading(s.dir), state: this.s};
        this.holding = this.s.tool;
        this.scene.reset();
        this.scene.show(this.s);
        this.flatEl.hidden = !this.s.failed;
        this.updateHud(this.s);
        this.refreshCode();
    }

    // ---------- the objectives and stars, as the missions' own objectives() and stars() work them out ----------
    objectives(s) {
        let done;
        if (this.mid === "lights_out") {
            const night = !s.complete;
            done = [!night || !(s.rocks || []).length, !night || !(s.dark || []).length, !night || !!s.atMast, !night || !!s.reported, !!s.complete];
        } else done = [s.cellTaken, s.toolPicked, s.rockCleared, s.inVillage, s.repaired].map(Boolean);
        const now = done.indexOf(false);
        return this.A.objectives.map((o, i) => Object.assign({done: done[i], now: i === now}, o));
    }

    stars(s) {
        const R = this.A.rules.stars;
        const energy = this.mid === "lights_out" ? (s.nightEnergy || []).length > 0 && Math.min(...s.nightEnergy) >= R.energy : s.energy >= R.energy;
        const lines = s.linesUsed <= R.lines;
        return {complete: !!s.complete, energy, lines, count: s.complete ? 1 + (energy ? 1 : 0) + (lines ? 1 : 0) : 0};
    }

    updateHud(s) {
        const A = this.A;
        if (!A || !s) return;
        const st = this.stars(s);
        this.hud.update({title: this.titleText(), robot: this.robotName, solar: "solar" in s ? !!s.solar : null, energy: s.energy,
                         max: A.rules.energyMax, tool: s.tool ? (A.tools[s.tool] || {}).name || s.tool : "none",
                         night: "night" in s ? [s.night, (A.nights || []).length] : null, lines: s.linesUsed,
                         linesWord: "vars" in s ? "Lines" : "Lines run", stars: [!!s.complete, s.complete && st.energy, s.complete && st.lines],
                         objectives: this.robotName ? this.objectives(s) : null, vars: "vars" in s ? s.vars : null, legend: this.text.legend});
    }

    log(msg, tone = null) {
        this.logRows = this.logRows.concat([[String(msg), tone]]).slice(-40);
        this.hud.log(this.logRows);
    }

    // who you are, top right; the teacher's page: the class's progress (each learner's mission, runs, last result
    // and the objectives done), as the teacher's window lists it
    classText() {
        if (this.role !== "teacher") { this.hud.classText(`CLASS: ${this.name || ""} (${this.role || "learner"})`); return; }
        const m = this.classMsg;
        if (!m) { this.hud.classText(`CLASS: ${this.name || "Teacher"} (teacher)\nwaiting for the class...`); return; }
        const lines = [`CLASS: lesson ${m.lesson ?? ""}, ${(m.learners || []).length} here`];
        for (const L of (m.learners || []).slice(0, 12)) lines.push(`${L.name}: M${L.mission === "wake_up_call" ? 1 : 2}  ${L.runs || 0} runs  ${this.lastWords(L.last)}  [${(L.done || []).join(" ") || "-"}]`);
        this.hud.classText(lines.join("\n"));
    }

    lastWords(last) {
        if (!last) return "not run yet";
        return last.complete ? `done, ${plural(last.stars || 0, "star")}` : `${last.objectives || 0}/${last.of || 0} steps`;
    }

    // ---------- the code panel (C): the Pseudo code tab, the Python beside each line, RUN, the phrasebook ----------
    typing() { return document.activeElement === $("mc-text"); }

    togglePanel() {
        if (this.codeEl.hidden) this.openPanel(); else this.closePanel();
    }

    openPanel(tab = null) {
        this.tab = tab || this.tab;
        this.codeEl.hidden = false;
        $("mc-pseudo").hidden = this.tab !== "pseudo";
        $("mc-code").hidden = this.tab !== "code";
        this.codeEl.querySelectorAll("button[data-mtab]").forEach(b => b.classList.toggle("on", b.dataset.mtab === this.tab));
        $("mc-file").textContent = `${this.mid}${this.tab === "pseudo" ? ".pseudo" : ".py"}`;
        this.hud.nowShown(false);  // (no room beside the panel: the objectives list marks what's now)
        this.refreshCode();
        if (this.tab === "pseudo") $("mc-text").focus();
    }

    closePanel() {
        if (!this.codeEl || this.codeEl.hidden) return;
        this.codeEl.hidden = true;
        if (this.typing()) $("mc-text").blur();
        this.hud.nowShown(true);
    }

    typed() {  // (the text changed: read again when the typing pauses, RUN off until then)
        this.codes[this.mid] = $("mc-text").value;
        this.dirty = true;
        $("mc-run").disabled = true;
        clearTimeout(this.parseTimer);
        this.parseTimer = setTimeout(() => this.requestParse(), 120);
        this.drawGutter();
    }

    requestParse() {
        this.dirty = false;
        this.parseSent++;
        this.app.send({type: "parse", mission: this.mid, text: $("mc-text").value});
    }

    drawGutter() {
        const n = $("mc-text").value.split("\n").length, bad = new Set(((this.parsed || {}).rows || []).filter(r => r.kind === "error").map(r => r.n));
        $("mc-gutter").innerHTML = Array.from({length: n}, (_, i) => bad.has(i + 1) ? `<b>${i + 1}</b>` : String(i + 1)).join("\n") + "\n";
    }

    // the server's reading of the code shown: the Python beside each line (the line being run lit), what's wrong
    // with the lines it can't read and the hint, RUN on when it can run (the window's refresh_code)
    refreshCode() {
        if (!this.codeEl || !this.A) return;
        const p = this.parsed;
        if (this.tab === "code") {
            $("mc-whole").innerHTML = (`from clubcoders import robot  # Robot Lab Mission ${this.A.number}: ${this.A.title}\n\n` + ((p && p.python) || "").replace(/\n+$/, ""))
                .split("\n").map(pyHtml).join("\n");
        }
        this.drawGutter();
        this.drawPython();
        const rows = [];
        const errors = p ? (p.rows || []).filter(r => r.kind === "error") : [];
        for (const r of errors) {
            rows.push([`Line ${r.n}: ${r.message || ""}${r.after ? `  ${r.after}` : ""}`, "bad"]);
            if (r.hint) rows.push([`      Did you mean: ${r.hint}?`, "hint"]);
        }
        if (p && !errors.length && p.code_lines) rows.push([`All ${plural(p.code_lines, "line")} understood.`, "ok"]);
        const most = 6;
        if (rows.length > most) {
            const shown = rows.slice(0, most - 1), more = errors.length - shown.filter(([, c]) => c === "bad").length;
            rows.splice(0, rows.length, ...shown, [`... and ${more} more`, "bad"]);
        }
        $("mc-problems").innerHTML = rows.map(([t, c]) => `<div class="${c}">${esc(t)}</div>`).join("");
        $("mc-runinfo").textContent = !p || this.dirty ? "Reading your code..." : errors.length ? "Fix the lines above to run."
            : `${plural(p.code_lines, "line")} of code   (Ctrl+Enter runs)`;
        const ok = this.canRun();
        $("mc-run").disabled = !ok;
    }

    drawPython() {
        const p = this.parsed, n = $("mc-text").value.split("\n").length, rows = (p && p.rows) || [];
        const out = [];
        for (let i = 0; i < n; i++) {
            const r = rows[i];
            if (!r) { out.push(""); continue; }
            const text = r.kind === "error" ? `<span class="err">${esc(r.python_line || "")}</span>` : pyHtml(r.python_line || "");
            out.push(this.runLine !== null && r.n === this.runLine ? `<span class="run">${text || " "}</span>` : text);
        }
        const py = $("mc-py");
        py.innerHTML = out.join("\n") + "\n";
        py.scrollTop = $("mc-text").scrollTop;
    }

    // the phrasebook, for reference only: words, no buttons (nothing is typed for the learner)
    renderBook() {
        const d = this.A.phrasebook || {patterns: [], slots: {}, synonyms: {}, fillers: []};
        const shown = d.patterns.filter(p => !p.alias), many = shown.length > 8;
        let html = `<h3>PHRASEBOOK  <small>(for reference: type the instructions yourself)</small></h3><div class="mc-says">`;
        for (const p of shown) html += `<div><b>${esc(p.say)}</b><span>${esc(p.meaning || "")}</span></div>`;
        html += `</div>`;
        if (many) {  // (Mission 2: the Python way of writing the new lines works too)
            html += `<p class="mc-py-way">The Python way works too:  ${esc(d.patterns.filter(p => p.alias).map(p => p.example).join("   "))}   if robot.energy &lt; 5:   print(lamps)</p>`;
        }
        const values = Object.entries(d.slots).filter(([k]) => shown.some(p => p.say.includes(`[${k}]`))).map(([k, s]) => `[${k}] ${s}`).join("   ");
        html += `<p class="mc-values">Values:  ${esc(values)}</p>`;
        if (!many) {
            html += `<p>Other words it knows:  ${esc(Object.entries(d.synonyms).filter(([k, v]) => k !== v).map(([k, v]) => `${k} = ${v}`).join(", "))}</p>
              <p>Ignored: capitals, punctuation and the filler words (${esc(d.fillers.join(", "))}). Number words (one to twenty) count as numbers. A line starting with # is a note.</p>`;
        }
        $("mc-book").innerHTML = html;
    }

    canRun() {
        const s = this.s, p = this.parsed;
        return !!(!this.playing && this.waiting === null && p && p.ok && p.code_lines > 0 && !this.dirty && this.robotName && s && !s.complete && !s.failed);
    }

    runCode() {
        if (!this.canRun()) { this.refreshCode(); return; }
        this.app.send({type: "program", mission: this.mid, text: $("mc-text").value});
        this.waiting = performance.now();
        this.playing = true;
        this.refreshCode();
    }

    // the class server's answer to a run: its events played as the window plays its own
    serverRan(m) {
        if (this.waiting === null || m.mission !== this.mid) return;
        this.waiting = null;
        const status = m.status;
        if (!["done", "complete", "flat", "stopped"].includes(status)) {
            this.playing = false;
            this.log({error: "The class server couldn't read a line of that program.", "too soon": "Wait a moment, then run again."}[status]
                     || `The class server: ${status}.`, "bad");
            if (status === "no mission") this.resetMission();  // (the server has restarted: the mission starts again there and here)
            this.refreshCode();
            return;
        }
        const events = unpack(m.before || this.s, m.events || []);
        if (m.state && typeof m.state === "object") this.s = m.state;
        this.ran = m;
        this.log(`Run ${this.s.runs}: ${plural(m.code_lines || 0, "line")}.`, "info");
        this.result = {status, events};
        this.queue = events.slice();
        this.playing = true;
        this.refreshCode();
    }

    // ---------- playing a run ----------
    nextEvent() {
        const ev = this.event = this.queue.shift(), V = this.view;
        this.eventT = 0;
        this.eventFrom = [V.x, V.y, V.h];
        const toH = heading(ev.state.dir), dh = mod(toH - V.h + 180, 360) - 180;  // (the short way round)
        this.eventTo = [ev.state.x, ev.state.y, V.h + dh];
        if (ev.msg) this.log(ev.msg, ev.tone);
        this.runLine = ev.line;
        this.drawPython();
        let before = V.state;
        const s = ev.state;
        if (ev.type === "night") {  // (Mission 2: the robot back at the bottom of the road at once, not driven there)
            this.eventFrom = this.eventTo = [s.x, s.y, toH];
            Object.assign(V, {x: s.x, y: s.y, h: toH, state: s});
            this.scene.reset();
            this.scene.show(s);
            this.updateHud(s);
            before = s;
        }
        if (s.tool !== before.tool) {  // (the tool in the robot's hands at once, gone from the crate)
            this.holding = s.tool;
            this.scene.show(Object.assign({}, before, {tool: s.tool}));
            this.sfx("clang", 0.5);
        }
        if (ev.type === "bump") this.sfx("bump", 0.7);
        else if (ev.type === "use") this.sfx({flipper: "pneumatic", hammer: "swing"}[s.tool] || "saw", 0.7);
        else if (ev.type === "objective" && s.cellTaken && !before.cellTaken) this.sfx("beep", 0.6);
        else if (ev.type === "complete") this.sfx("horn", 0.6);
        else if (ev.type === "flat") this.sfx("beep", 0.4, 0.6);
        else if (ev.type === "repair") this.sfx("clang", 0.5);
        else if (ev.type === "report" || ev.type === "solar") this.sfx("beep", ev.type === "report" ? 0.5 : 0.3, ev.tone === "ok" ? 1.0 : 0.6);
    }

    endEvent() {
        const ev = this.event, V = this.view, before = V.state, s = ev.state;
        Object.assign(V, {x: this.eventTo[0], y: this.eventTo[1], h: this.eventTo[2], state: s});
        this.scene.landed(ev, before);
        this.scene.show(s);
        this.updateHud(s);
        this.event = null;
    }

    finish() {
        this.playing = false;
        this.runLine = null;
        const r = this.result, s = this.s;
        Object.assign(this.view, {x: s.x, y: s.y, state: s});
        this.holding = s.tool;
        this.scene.show(s);
        this.updateHud(s);
        this.refreshCode();
        if (r.status === "complete") {
            this.recordFinish();
            this.closePanel();
            this.showDone();
        } else if (r.status === "flat") {
            if (s.failed) this.flatEl.hidden = false;
        } else if (r.status === "stopped") {
            this.log(this.text.stopped, "info");
        } else {
            const o = this.objectives(s).find(x => x.now);
            if (o) this.log(`Next: ${o.title}. ${o.text}`, "info");
        }
    }

    // a finish kept on this page as the server keeps it (the mission's record_finish): the part unlocked, the best stars
    recordFinish() {
        const A = this.A, st = this.stars(this.s), p = this.progress;
        if (A.unlock && !p.parts.includes(A.unlock.id)) p.parts.push(A.unlock.id);
        const prev = (p.missions || {})[this.mid] || {};
        p.missions = Object.assign({}, p.missions, {[this.mid]: {complete: true, bestStars: Math.max(prev.bestStars || 0, st.count),
                                                                 robot: this.robotName, energyLeft: this.s.energy, linesUsed: this.s.linesUsed}});
    }

    showDone() {
        const A = this.A, s = this.s, st = this.stars(s), R = A.rules.stars;
        let energy, lines;
        if ("nightEnergy" in s) {  // (Mission 2: the energy left at the end of each night, the program's lines)
            energy = `Energy left each night: ${s.nightEnergy.join(", ")}  (${st.energy ? "a star" : "no star"}: ${R.energy} or more every night earns one)`;
            lines = `Lines of code: ${s.linesUsed}  (${st.lines ? "a star" : "no star"}: ${R.lines} or fewer earns one; if and repeat save lines)`;
        } else {
            energy = `Energy left: ${s.energy}  (${st.energy ? "a star" : "no star"}: ${R.energy} or more earns one)`;
            lines = `Lines of code run: ${s.linesUsed}  (${st.lines ? "a star" : "no star"}: ${R.lines} or fewer earns one; repeat saves lines)`;
        }
        const part = A.unlock ? [`Unlocked: ${A.unlock.name}`, `${A.unlock.text} Kept with your class profile for Mission 2.`, true]
                              : [`${A.solar.name}: ${s.solar ? "fitted, from Mission 1" : "not fitted"}`,
                                 "Your stars are kept with your class profile. Mission 3, Supply Run (while loops), comes next.", !!s.solar];
        this.doneEl.innerHTML = `<h1>MISSION COMPLETE</h1>
          <div class="md-stars">${[true, st.energy, st.lines].map(on => `<i class="${on ? "on" : ""}">★</i>`).join("")}</div>
          <p>${esc(this.text.done)}</p><p class="${st.energy ? "ok" : "dim"}">${esc(energy)}</p><p class="${st.lines ? "ok" : "dim"}">${esc(lines)}</p>
          <div class="md-part"><span class="md-panel"><i></i><i></i><i></i></span><div><b class="${part[2] ? "ok" : "dim"}">${esc(part[0])}</b><p>${esc(part[1])}</p></div></div>
          <div class="md-btns"><button id="md-again" class="go">PLAY AGAIN</button><button id="md-close">CLOSE</button></div>`;
        $("md-again").onclick = () => { this.closeDone(); this.showIntro(); };
        $("md-close").onclick = () => this.closeDone();
        this.doneEl.hidden = false;
        this.doneStars = st.count;
    }

    closeDone() {
        if (this.doneEl) this.doneEl.hidden = true;
    }

    // ---------- everyone else's robots (the window's Ghost) ----------
    worldRobot(m) {
        const name = String(m.name || "").slice(0, 20);
        if (!name || name === this.name) return;
        if (m.gone) { this.dropGhost(name); return; }
        if (!(m.mission in this.about) || !ROBOTS.includes(m.robot)) return;
        let g = this.ghosts.get(name);
        if (!g || g.robot !== m.robot || g.mission !== m.mission) {
            if (g) this.dropGhost(name);
            g = {name, robot: m.robot, mission: m.mission, tool: null, at: null, anim: null, steps: []};
            this.ghosts.set(name, g);
        }
        for (const s of m.steps || []) if (Array.isArray(s) && s.length === 5) g.steps.push(s);
    }

    dropGhost(name) {
        this.ghosts.delete(name);
        this.scene.dropRobot("ghost " + name);
    }

    // each step of their runs played at the page's pace (faster when it has fallen behind); only the robots on this
    // page's mission are drawn
    updateGhost(g, dt) {
        let speed = 0, use = 0;
        while (!g.anim && g.steps.length) {
            const [kind, x, y, d, tool] = g.steps.shift();
            g.tool = tool;
            let h = heading(d);
            if (g.at) h = g.at[2] + mod(h - g.at[2] + 180, 360) - 180;  // (the short way round)
            if (kind === "place" || kind === "night" || !g.at) { g.at = [x, y, h]; continue; }
            g.anim = {from: g.at, to: [x, y, h], t: 0, dur: (DURATION[kind] ?? 0.45) * (g.steps.length > 30 ? 0.3 : 1), kind};
        }
        if (!g.at) return;
        let [x, y, h] = g.at;
        if (g.anim) {
            const a = g.anim;
            a.t += dt;
            const k = a.dur > 0 ? Math.min(1, a.t / a.dur) : 1, e = ease(k);
            [x, y, h] = a.from.map((c, i) => c + (a.to[i] - c) * e);
            if (a.kind === "move") speed = SQ / Math.max(0.05, a.dur) * Math.sin(Math.PI * k) * 1.6;
            else if (a.kind === "use") use = k;
            if (k >= 1) { g.at = a.to; g.anim = null; }
        }
        const key = "ghost " + g.name;
        this.scene.holdRobot(key, this.about[g.mission].robots[g.robot], g.name, true);
        this.scene.placeRobot(key, g.tool, x, y, h, speed, use);
    }

    // ---------- each frame ----------
    frame(now, dt) {
        const sound = this.app.sound;
        this.t += dt;
        sound.use("robotlab");  // (Robot Lab's sounds: the tools, the motors, the bumps and clangs)
        if (sound.ready && !this.preloaded) { this.preloaded = true; sound.preload(["beep", "horn"]); }
        if (this.waiting !== null && now - this.waiting > SERVER_WAIT) {
            this.waiting = null;
            this.playing = false;
            this.log("The class server didn't answer: press RUN again in a moment.", "warn");
            this.refreshCode();
        }
        let use = 0, speed = 0, nudge = 0;
        if (this.playing && this.waiting === null && this.view) {
            if (this.speed <= 0) {  // (no animation: every event at once)
                while (this.queue.length) { this.nextEvent(); this.endEvent(); }
                this.finish();
            } else {
                if (!this.event) { if (this.queue.length) this.nextEvent(); else this.finish(); }
                if (this.event) {
                    const ev = this.event, V = this.view, dur = (DURATION[ev.type] ?? 0.45) / this.speed;
                    this.eventT += dt;
                    const k = dur > 0 ? Math.min(1, this.eventT / dur) : 1, e = ease(k);
                    const [x0, y0, h0] = this.eventFrom, [x1, y1, h1] = this.eventTo;
                    Object.assign(V, {x: x0 + (x1 - x0) * e, y: y0 + (y1 - y0) * e, h: h0 + (h1 - h0) * e});
                    if (ev.type === "move") {  // (the wheels turn as it goes: backwards for move back)
                        speed = SQ / Math.max(0.05, dur) * Math.sin(Math.PI * k) * 1.6;
                        const f = forward(h1);
                        if ((x1 - x0) * f[0] * SQ + (y0 - y1) * f[1] * SQ < 0) speed = -speed;
                    } else if (ev.type === "bump") {
                        nudge = 0.3 * Math.sin(Math.PI * k);
                        if (k > 0.45 && !this.bumped && this.scene.fx) {
                            this.bumped = true;
                            const p = this.scene.world(V.x, V.y), f = forward(V.h);
                            this.scene.fx.impact([p[0] + f[0] * SQ * 0.6, p[1] + f[1] * SQ * 0.6, 0.4], 12, "bump", [0.6, 0.6, 0.6]);
                        }
                    } else if (ev.type === "use") use = k;
                    this.scene.animate(ev, V.state, k, this.eventT);  // (the rocks flying apart, the cell lifted...)
                    if (k >= 1) {
                        this.bumped = false;
                        this.scene.settle(ev);
                        this.endEvent();
                    }
                }
            }
        }
        if (this.robotName && this.view) {
            const tool = this.holding;
            this.scene.placeRobot("me", tool, this.view.x, this.view.y, this.view.h, speed, use, nudge);
            const weapons = sound.level ? sound.level("weapons") : 1;
            if ((tool === "spinner" || tool === "drum") && use > 0) sound.spinner("tool", 1400 * Math.sin(Math.PI * use), 0.6 * weapons, tool === "drum" ? "drum" : "spinner");
            else sound.stop("tool");
            sound.loop("motor", "motor", 0.05 + Math.min(0.3, Math.abs(speed) / 20), 0.6 + Math.abs(speed) / 8, {channel: "motors"});
        }
        for (const g of this.ghosts.values()) if (g.mission === this.mid) this.updateGhost(g, dt);
        const V = this.view, shown = !this.codeEl.hidden;
        this.scene.view = {mode: this.cam.mode, zoom: this.cam.zoom, pan: this.cam.pan, at: V ? [V.x, V.y] : null, h: V ? V.h : 0,
                           panel: shown ? Math.min(0.6, this.codeEl.offsetWidth / Math.max(1, window.innerWidth)) : 0};
        this.scene.frame(dt, this.t);
    }

    sfx(name, volume, rate = 1) {
        this.app.sound.play(name, {volume, rate, channel: "effects"});
    }

    // ---------- the page's keys and panel ----------
    // a key the page heard while not typing: true when it was this game's (or another game's that does nothing here)
    onKey(k, e) {
        const intro = !this.introEl.hidden;
        if (k === "F1" || k === "F2") {
            if (e && e.preventDefault) e.preventDefault();
            if (intro) this.chooseMission(ORDER[k === "F1" ? 0 : 1]);
            return true;
        }
        if (intro && (k === "1" || k === "2")) { this.choose(ROBOTS[Number(k) - 1]); return true; }
        if (k === "c") { if (!intro && this.doneEl.hidden) this.togglePanel(); return true; }
        if (k === "r") { if (!intro) this.resetMission(); return true; }
        if (k === "g") { this.openGraphics(); return true; }
        if (k === "Escape") {
            if (!this.codeEl.hidden) this.closePanel();
            else if (!this.doneEl.hidden) this.closeDone();
            return true;
        }
        return ["u", "p", "b", "l", "o", "[", "]", "f", " ", "Enter", "t", "q", "e"].includes(k);  // (other games' keys: nothing here)
    }

    openGraphics() {
        $("panel").classList.add("open");
        const b = document.querySelector('#panelhead button[data-tab="graphics"]');
        if (b) b.click();
    }

    // V: the whole valley, behind your robot, from above
    cycleCamera() {
        this.cam.mode = VIEWS[(VIEWS.indexOf(this.cam.mode) + 1) % VIEWS.length];
    }

    resetCamera() {  // Home (and HOME VIEW): the camera as it started
        this.cam = {mode: "valley", zoom: 1, pan: [0, 0]};
        this.app.updatePills();
    }

    zoom(dir, how) {  // + and - (app.js's zoomKey): dir 1 closer
        const f = how === "repeat" ? 0.92 : 0.85;
        this.cam.zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, this.cam.zoom * (dir > 0 ? f : 1 / f)));
    }

    pill() {
        return this.A ? `Mission ${this.A.number}: ${this.A.title}` : "Missions";
    }

    cameraPill() {
        return `Camera: ${VIEW_NAMES[this.cam.mode]} (V to change, wheel or +/- to zoom, right-drag to pan, Home back)`;
    }

    keyList() {
        return [["C", "the code panel (Ctrl+Enter runs your code in it)"], ["R", "reset the mission (your code is kept)"],
                ["V", "camera view"], ["Wheel, + and -", "zoom"], ["Right-drag", "pan over the map"], ["Home", "the camera back"],
                ["1 and 2", "TITAN or RAZORBACK (on the first screen)"], ["F1 and F2", "Mission 1 or Mission 2 (on the first screen)"],
                ["G", "graphics"], ["N", "sound on or off"]];
    }

    // the side panel's tabs (app.js's allTabs): no garage, AI cards or teacher tabs on a mission
    panelTabs(role) {
        return role === "learner" ? [["missions", "Mission"], ["graphics", "Settings"], ["about", "Keys"]]
                                  : [["class", "Class"], ["missions", "Mission"], ["graphics", "Graphics"], ["about", "About"]];
    }

    tabs() { return [["class", "Class"]]; }

    learnerTabs() { return []; }

    renderTab(tab, body) {
        if (tab === "missions") { this.missionTab(body); return true; }
        if (tab === "class") { this.classTab(body); return true; }
        return false;
    }

    missionTab(body) {
        const A = this.A;
        if (!A) { body.innerHTML = "<p class='note'>Waiting for the class server…</p>"; return; }
        const s = this.s || this.startState(), best = ((this.progress.missions || {})[this.mid] || {}).bestStars || 0;
        body.innerHTML = `<h2>${esc(this.titleText())}</h2><p class="note">${esc(this.text.story)}</p>
          <h2>Objectives</h2><table>${this.objectives(s).map(o => `<tr><td>${o.done ? "✓" : o.now ? "&gt;" : "○"}</td><td><b>${esc(o.title)}</b><br><span class="note">${esc(o.text)}</span></td></tr>`).join("")}</table>
          <p class="note">${esc(this.text.rules)}</p>
          <p class="${this.partsText()[1] ? "ok" : "note"}">${esc(this.partsText()[0])}</p>
          <p class="note">Your best: ${best ? `${plural(best, "star")}` : "not finished yet"}.</p>
          <div class="row"><button id="mt-code" class="go">CODE PANEL (C)</button><button id="mt-intro">CHOOSE A MISSION OR ROBOT</button></div>`;
        $("mt-code").onclick = () => { if (this.robotName) this.openPanel(); else this.app.toast("Choose your robot first."); };
        $("mt-intro").onclick = () => this.showIntro();
    }

    // the teacher's Class tab: each learner's mission, runs, last result and the lesson's objectives done; the
    // mission for everyone (the lesson: every page and window in the class goes to it)
    classTab(body) {
        const m = this.classMsg, L = (m && m.learners) || [];
        let html = `<h2>The mission for the class</h2><div class="row">${ORDER.filter(k => k in this.about).map((k, i) =>
            `<button data-lesson="${i + 1}" class="${m && m.lesson === i + 1 ? "on" : ""}">Mission ${this.about[k].number}: ${esc(this.about[k].title)}</button>`).join("")}</div>
          <div class="note">Every learner's page and window goes to it (not while their robot is running).</div>
          <h2>The class (${L.length})</h2>`;
        html += L.length ? `<table><tr><th>Learner</th><th>Mission</th><th>Runs</th><th>Last</th><th>Done</th></tr>${L.map(p =>
            `<tr><td>${esc(p.name)}</td><td>${p.mission === "wake_up_call" ? 1 : 2}</td><td class="num">${p.runs || 0}</td><td>${esc(this.lastWords(p.last))}</td><td>${esc((p.done || []).join(" ") || "-")}</td></tr>`).join("")}</table>`
            : `<p class="note">Nobody has joined yet.</p>`;
        body.innerHTML = html;
        body.querySelectorAll("button[data-lesson]").forEach(b => b.onclick = () => {
            this.app.send({type: "lesson", lesson: {lesson_number: Number(b.dataset.lesson)}});
            this.app.toast(`Mission ${b.dataset.lesson} for the class`);
        });
    }

    dispose() {
        for (const [el, ev, fn, opts] of this.listeners) el.removeEventListener(ev, fn, opts);
        this.listeners = [];
        clearTimeout(this.parseTimer);
        for (const el of [this.introEl, this.codeEl, this.doneEl, this.flatEl]) el.remove();
        document.body.classList.remove("missionscreen");
        this.app.sound.stop("tool");
        this.app.sound.stop("motor");
        this.scene.dispose();
    }
}
