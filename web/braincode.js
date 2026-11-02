// Robot Lab's Brain panel on the page (CHANGE 211), the window's Brain panel (K): your robot's brain written in pseudo
// code on the left and Python on the right, each line of one the same line of the other, and either side typed. The
// page has no Python of its own to read pseudo code with, so it asks its class server (brain_pseudo.code_msg, the
// functions the window uses): {type: "brain_code", side, text} as the typing pauses, and the reply rewrites the OTHER
// side only (never the one being typed in), with each line's reading, what's wrong and the hint, as the Missions' code
// panel shows them (missions.js). Above the Python, greyed, the brain's start and below it its end: always the same,
// so they can't be changed. RUN (or Ctrl+Enter) sends the pseudo code as the learner's brain with autopilot on
// ({type: "brain_run"}); STOP switches autopilot off ({type: "autopilot"}, as P). Learners only, while the teacher has
// brains switched on (Controls); the panel starts from the pseudo code last run (the missions message's
// brain_pseudo), else the phrasebook's starter.

import {codeTokens} from "./garage.js";
import {esc} from "./teacher.js";

const $ = id => document.getElementById(id);
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const PAUSE_MS = 150;  // (the typing paused this long: the server reads it)

// a line of Python coloured as the code panel colours it (garage.js's codeTokens, as missions.js's pyHtml)
function pyHtml(line) {
    let out = "", at = 0;
    for (const [s, e, c] of codeTokens(line).tokens) {
        out += esc(line.slice(at, s)) + `<span class="${c}">${esc(line.slice(s, e))}</span>`;
        at = e;
    }
    return out + esc(line.slice(at));
}

export class BrainCode {
    constructor(app) {
        this.app = app;
        this.el = null;
        this.book = null;          // the phrasebook (asked for once, with the first question)
        this.last = null;          // the server's last reading that is still what's typed
        this.asked = this.got = 0; // questions sent and answers heard (an older answer is ignored)
        this.askedSide = null;
        this.askedText = null;
        this.dirty = null;         // the side typed in since the last question ("pseudo" or "python")
        this.touched = false;      // typed in at all (then the pseudo code last run never replaces it)
        this.wantStarter = false;  // nothing run before: the phrasebook's starter goes in when it comes
        this.shownFor = null;      // whose code is in the panel (another learner: theirs)
        this.autopilot = false;
        this.lead = null;          // the side whose scroll the other follows
    }

    // a learner in Robot Lab with brains switched on (lesson.tools.brains: the teacher's Controls)
    available() {
        const S = this.app.state, g = this.app.game;
        return !!(S.connected && g && g.id === "robotlab" && S.role === "learner" && ((S.lesson || {}).tools || {}).brains !== false);
    }

    get shown() { return !!this.el && !this.el.hidden; }

    build() {
        if (this.el) return;
        const el = this.el = document.createElement("div");
        el.id = "braincode";
        el.hidden = true;
        el.innerHTML = `<header><span class="dots"><i></i><i></i><i></i></span><b>YOUR ROBOT'S BRAIN</b><span id="bc-file">my_brain.pseudo</span>
            <span class="spacer"></span><button id="bc-close" title="K closes it too">✕</button></header>
          <div class="bcol">
            <div class="note">Say what your robot should do <i>now</i>: the lines are read again 60 times a second while your code drives.
              Type on either side: each line of pseudo code is that line of Python, and the other side follows.</div>
            <div class="bc-heads"><span>PSEUDO CODE: one instruction per line</span><span>PYTHON: the same, line for line</span></div>
            <div class="codebox bc-box">
              <div class="bc-row bc-fixed"><div class="bc-gut"></div><pre class="bc-side">(the brain's start:
 always the same)</pre><pre id="bc-start" class="mpy bc-dim"></pre></div>
              <div class="bc-row bc-main"><div class="bc-gut"><pre id="bc-gutter"></pre></div>
                <textarea id="bc-pseudo" spellcheck="false" wrap="off" autocomplete="off" autocapitalize="off"></textarea>
                <div class="bc-edit"><pre id="bc-hl" class="mpy" aria-hidden="true"></pre><textarea id="bc-python" spellcheck="false" wrap="off" autocomplete="off" autocapitalize="off"></textarea></div></div>
              <div class="bc-row bc-fixed bc-endrow"><div class="bc-gut"></div><pre class="bc-side">(its end)</pre><pre id="bc-end" class="mpy bc-dim"></pre></div>
            </div>
            <div id="bc-problems"></div>
            <div class="row"><button id="bc-run" class="go" disabled title="Ctrl+Enter runs it too">RUN</button>
              <button id="bc-stop" class="stop" title="Your code stops driving: you drive (P does the same)">STOP</button>
              <span id="bc-runinfo"></span></div>
            <div id="bc-result"></div>
            <div id="bc-book"></div>
          </div>`;
        document.body.appendChild(el);
        $("bc-close").onclick = () => this.close();
        $("bc-run").onclick = () => this.run();
        $("bc-stop").onclick = () => this.stop();
        for (const [id, side, tab] of [["bc-pseudo", "pseudo", "  "], ["bc-python", "python", "    "]]) {
            const ta = $(id), other = $(id === "bc-pseudo" ? "bc-python" : "bc-pseudo");
            ta.addEventListener("input", () => this.typed(side));
            // (both sides scroll together, the line numbers with them: the side under the mouse or the cursor leads, so
            // a shorter side, not read again yet, can't pull the other back)
            for (const ev of ["pointerenter", "focus", "wheel", "touchstart"]) ta.addEventListener(ev, () => { this.lead = ta; }, {passive: true});
            ta.addEventListener("scroll", () => {
                if ((!this.lead || this.lead === ta) && other.scrollTop !== ta.scrollTop) other.scrollTop = ta.scrollTop;
                this.place();
            });
            ta.addEventListener("keydown", e => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this.run(); }
                else if (e.key === "Tab" && !e.shiftKey) {  // (an indent: two spaces in pseudo code, four in Python)
                    e.preventDefault();
                    ta.setRangeText(tab, ta.selectionStart, ta.selectionEnd, "end");
                    this.typed(side);
                } else if (e.key === "Escape") { e.preventDefault(); this.close(); }
            });
        }
        if (this.app.makeDraggable) this.app.makeDraggable(el, "braincode", {handle: "header", resize: true, minW: 420, minH: 320});
    }

    toggle() {
        if (this.shown) this.close(); else this.open();
    }

    open() {
        if (!this.available()) return;
        this.build();
        this.el.hidden = false;
        const S = this.app.state, key = `${S.name || ""}`;
        if (this.shownFor !== key) {  // (first open, or another learner: the pseudo code last run, else the starter)
            this.shownFor = key;
            const kept = (S.myMissions || {}).brain_pseudo;
            $("bc-pseudo").value = kept || "";
            $("bc-python").value = "";
            this.last = null;
            this.touched = false;
            this.wantStarter = !kept;
            $("bc-result").textContent = "";
            this.ask("pseudo", true);
        }
        this.autopilot = !!(S.myMissions || {}).autopilot;
        this.drawFixed();
        this.draw();
        $("bc-pseudo").focus();
    }

    close() {
        if (!this.shown) return;
        const a = document.activeElement;
        if (a && this.el.contains(a)) a.blur();  // (the keys drive the robot again)
        this.el.hidden = true;
    }

    // a new connection, the lesson changed (brains switched off?), another game or learner: the button, and the panel
    // closed when it isn't for here any more
    changed(connected = false) {
        if (connected) { this.asked = this.got = 0; this.dirty = null; }
        if (this.shownFor !== null && this.shownFor !== `${this.app.state.name || ""}`) this.shownFor = null;
        const btn = $("btn-brain");
        if (btn) btn.hidden = !this.available();
        if (!this.available()) this.close();
        else if (connected && this.shown) this.ask("pseudo");  // (connected again: a question on the way was lost)
    }

    // ---------- the server reads what's typed ----------
    typed(side) {  // (read again when the typing pauses; RUN off until then)
        this.dirty = side;
        this.touched = true;
        $("bc-run").disabled = true;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.ask(side), PAUSE_MS);
        this.paint();
    }

    ask(side, phrasebook = !this.book) {
        clearTimeout(this.timer);
        const text = $(side === "python" ? "bc-python" : "bc-pseudo").value;
        this.asked++;
        this.askedAt = performance.now();
        this.askedSide = side;
        this.askedText = text;
        this.dirty = null;
        this.app.send(Object.assign({type: "brain_code", side, text}, phrasebook ? {phrasebook: true} : {}));
    }

    pending() {  // (a question not answered yet: an answer lost would leave RUN off for good, so 3 s is long enough)
        return this.got < this.asked && performance.now() - this.askedAt < 3000;
    }

    // the server's reading: the other side rewritten (if what was asked about is still what's typed)
    took(m) {
        this.got++;
        if (m.phrasebook) { this.book = m.phrasebook; this.drawFixed(); this.renderBook(); }
        if (!this.el) return;
        if (this.pending()) return;  // (a newer question is on its way: its answer is the one to show)
        this.got = this.asked;
        const side = m.side === "python" ? "python" : "pseudo", mine = $(side === "python" ? "bc-python" : "bc-pseudo");
        if (this.dirty || side !== this.askedSide || mine.value !== this.askedText) return;  // (typed since: asked again soon)
        if (this.wantStarter && side === "pseudo" && !mine.value && this.book) {  // (nothing run before: the starter)
            this.wantStarter = false;
            mine.value = this.book.starter || "";
            this.ask("pseudo");
            return;
        }
        this.wantStarter = false;
        const other = $(side === "python" ? "bc-pseudo" : "bc-python"), text = side === "python" ? m.pseudo : m.python;
        if (other.value !== text) {
            other.value = text || "";
            other.scrollTop = mine.scrollTop;
        }
        this.last = m;
        this.draw();
    }

    // ---------- drawing ----------
    drawFixed() {  // the brain's start and end, greyed (the phrasebook's, as brain_pseudo's START and END)
        if (!this.el || !this.book) return;
        $("bc-start").innerHTML = (this.book.start || []).map(pyHtml).join("\n");
        $("bc-end").innerHTML = (this.book.end || []).map(pyHtml).join("\n");
    }

    bad() {  // the line numbers marked: the lines it can't read, and the Python the phrasebook doesn't know
        const m = this.last, out = new Set();
        if (!m || this.dirty) return out;
        for (const r of m.rows || []) if (r.kind === "error") out.add(r.n);
        for (const n of m.unknown || []) out.add(n);
        return out;
    }

    paint() {  // the line numbers and the Python coloured, where the scroll puts them
        if (!this.el) return;
        const ps = $("bc-pseudo"), py = $("bc-python"), bad = this.bad();
        const n = Math.max(ps.value.split("\n").length, py.value.split("\n").length);
        $("bc-gutter").innerHTML = Array.from({length: n}, (_, i) => bad.has(i + 1) ? `<b>${i + 1}</b>` : String(i + 1)).join("\n") + "\n";
        $("bc-hl").innerHTML = py.value.split("\n").map((line, i) => bad.has(i + 1) ? `<span class="err">${esc(line) || " "}</span>` : pyHtml(line)).join("\n") + "\n";
        this.place();
    }

    place() {
        if (!this.el) return;
        const py = $("bc-python");
        $("bc-hl").style.transform = `translate(${-py.scrollLeft}px, ${-py.scrollTop}px)`;
        $("bc-gutter").style.transform = `translateY(${-$("bc-pseudo").scrollTop}px)`;
    }

    // what's wrong with the lines it can't read and the hint (missions.js's refreshCode), RUN on when it can run
    draw() {
        if (!this.el) return;
        this.paint();
        const m = this.last, rows = [];
        const unknown = new Set(m && !this.dirty ? m.unknown || [] : []);
        const errors = m && !this.dirty ? (m.rows || []).filter(r => r.kind === "error") : [];
        for (const r of errors) {
            if (unknown.has(r.n)) { rows.push([`Line ${r.n}: this Python isn't one the phrasebook knows.`, "bad"]); continue; }
            rows.push([`Line ${r.n}: ${r.message || ""}${r.after ? `  ${r.after}` : ""}`, "bad"]);
            if (r.hint) rows.push([`      Did you mean: ${r.hint}?`, "hint"]);
        }
        if (m && !this.dirty && !errors.length && m.lines) rows.push([`All ${plural(m.lines, "line")} understood.`, "ok"]);
        const most = 6;
        if (rows.length > most) {
            const shown = rows.slice(0, most - 1), more = errors.length - shown.filter(([, c]) => c === "bad").length;
            rows.splice(0, rows.length, ...shown, [`... and ${more} more`, "bad"]);
        }
        $("bc-problems").innerHTML = rows.map(([t, c]) => `<div class="${c}">${esc(t)}</div>`).join("");
        const reading = !m || this.dirty || this.pending();
        $("bc-runinfo").textContent = reading ? "Reading your code..." : errors.length ? "Fix the lines above to run."
            : !m.lines ? "Type what your robot should do, one instruction a line." : `${plural(m.lines, "line")} of code   (Ctrl+Enter runs)`;
        $("bc-run").disabled = !this.canRun();
        $("bc-stop").disabled = !this.autopilot;
        $("bc-file").textContent = this.autopilot ? "my_brain.pseudo   ● your code is driving" : "my_brain.pseudo";
    }

    // the phrasebook, for reference (missions.js's renderBook): each instruction and what it does, then the values
    renderBook() {
        if (!this.el || !this.book) return;
        const d = this.book;
        let html = `<h3>PHRASEBOOK  <small>(for reference: type the instructions yourself)</small></h3><div class="mc-says">`;
        for (const p of d.patterns || []) html += `<div><b>${esc(p.say)}</b><span>${esc(p.meaning || "")}</span></div>`;
        html += `</div>`;
        const values = Object.entries(d.values || {}).map(([k, s]) => `[${k}] ${s}`).join("   ");
        if (values) html += `<p class="mc-values">Values:  ${esc(values)}</p>`;
        html += `<p>A line starting with # is a note. Each line of Python on the right is one of these instructions (type it and the pseudo code follows).</p>`;
        $("bc-book").innerHTML = html;
    }

    // ---------- RUN and STOP ----------
    canRun() {
        const m = this.last;
        return !!(m && m.ok && m.lines > 0 && !this.dirty && !this.pending() && m.pseudo === $("bc-pseudo").value && this.available());
    }

    run() {
        if (!this.canRun()) { this.draw(); return; }
        // (the pseudo code indented by its if and else as it goes, as the window's panel shows it after a RUN)
        const m = this.last, ta = $("bc-pseudo"), lines = ta.value.split("\n");
        let pseudo = ta.value;
        if ((m.rows || []).length === lines.length) {
            pseudo = m.rows.map(r => (r.raw || "").trim() ? "  ".repeat(r.indent || 0) + r.raw.trim() : "").join("\n");
        }
        this.app.send({type: "brain_run", pseudo});
        this.say("Sent to the class server: it checks your code, then your robot runs it.", "info");
        if (pseudo !== ta.value) {
            ta.value = pseudo;
            this.ask("pseudo");
        }
        this.draw();
    }

    stop() {
        if (this.autopilot) this.app.send({type: "autopilot"});  // (P's toggle: only while it's on)
    }

    say(text, tone) {
        const r = $("bc-result");
        if (!r) return;
        r.textContent = text;
        r.className = tone;
    }

    // the server's brain_result (a RUN, or U): shown here while the panel is open (true), else app.js's toast
    result(m) {
        if (!this.shown) return false;
        this.say(m.ok ? (m.error || "Your brain is uploaded.") : `Not run: ${m.error || ""}`, m.ok ? "ok" : "bad");
        return true;
    }

    // our own missions message: autopilot on or off (STOP), and the pseudo code last run (RUN's, kept with the profile)
    missions(m) {
        this.autopilot = !!m.autopilot;
        if (!this.el) return;
        if (this.shownFor !== null && !this.touched && m.brain_pseudo && m.brain_pseudo !== $("bc-pseudo").value) {
            $("bc-pseudo").value = m.brain_pseudo;  // (it came after the panel opened: the starter wasn't theirs)
            this.wantStarter = false;
            this.ask("pseudo");
        }
        this.draw();
    }
}
