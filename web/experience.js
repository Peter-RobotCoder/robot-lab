// Experiences on the page (CHANGE 210): engine/experience.py's layer over any game, drawn as the windows draw it
// (engine/experience_hud.py). Over the game, never instead of it: the objective and how far you've got, the XP bar and
// your rank, the coach's words typed out, "+10 XP" and RANK UP as they happen, and the result card (START AGAIN). The
// Mission tab, the garage, the code panel and the brains are the game's own. The teacher sees the class instead: who is
// on which objective, their XP and rank, who has finished; the Controls tab's Mission row starts and ends it.
//
// The server's messages: "experience" (a learner's run, every second; {on: false} once when it ends) and
// "experience_class" (the teacher's). The page sends {type: "experience", do: "skip" | "again" | "action" | "start" | "stop"}.

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
const TYPE_RATE = 70;     // the coach's letters a second
const TOAST_MS = 3000;

function el(id, cls) {
    let e = document.getElementById(id);
    if (!e) {
        e = document.createElement("div");
        e.id = id;
        e.className = cls;
        e.hidden = true;
        document.body.appendChild(e);
    }
    return e;
}

export class ExperienceView {
    constructor(send) {
        this.send = send;
        this.m = null;          // a learner's run
        this.cls = null;        // the teacher's view of the class
        this.available = [];    // the game's experiences (the teacher's START buttons)
        this.saySeq = -1; this.sayText = ""; this.sayAt = 0;
        this.toastSeen = 0; this.toasts = [];
        this.closedCard = null;
        this.top = el("xp-top", "hud xpbox");
        this.coach = el("xp-coach", "hud xpbox");
        this.toastBox = el("xp-toasts", "hud");
        this.card = el("xp-card", "xpcard");
        this.classBox = el("xp-class", "hud xpbox");
        this.drawnKey = null;
        const tick = () => { this.frame(); requestAnimationFrame(tick); };
        requestAnimationFrame(tick);
        for (const box of [this.top, this.card, this.classBox]) {
            box.addEventListener("click", e => {
                const b = e.target.closest("button[data-xp]");
                if (!b) return;
                if (b.dataset.xp === "close") { this.closedCard = (this.m && this.m.result || {}).when; this.draw(); return; }
                const msg = {type: "experience", do: b.dataset.xp};
                if (b.dataset.action) msg.action = b.dataset.action;
                this.send(msg);
            });
        }
    }

    get on() { return !!(this.m || this.cls); }

    took(m) {
        if (m.type === "experience") {
            this.m = m.on ? m : null;
            if (m.on) {
                const say = m.say || [0, ""];
                if (say[0] !== this.saySeq) { this.saySeq = say[0]; this.sayText = say[1]; this.sayAt = performance.now(); }
                for (const [seq, words, kind] of m.toasts || []) {
                    if (seq > this.toastSeen) { this.toastSeen = seq; this.toasts = this.toasts.concat([[words, kind, performance.now()]]).slice(-3); }
                }
            }
        } else if (m.type === "experience_class") {
            this.cls = m.on ? m : null;
            this.available = m.available || this.available;
        }
        this.draw();
    }

    draw() {
        const m = this.m;
        this.top.hidden = this.coach.hidden = !m;
        this.card.hidden = !(m && m.result && this.closedCard !== m.result.when);
        this.classBox.hidden = !this.cls;
        if (m) {
            const n = (m.objectives || []).length, next = m.next;
            const head = m.result ? `EXPERIENCE ${m.n}: ${esc(m.title).toUpperCase()} &nbsp; COMPLETE`
                : `EXPERIENCE ${m.n} &nbsp; OBJECTIVE ${m.index + 1} OF ${n}: &nbsp;${esc(m.objective).toUpperCase()}`;
            const pct = Math.max(1, Math.min(100, 100 * (m.xp || 0) / Math.max(1, m.max_xp || 1)));
            const buttons = m.result ? "" : (m.actions || []).map(([a, w]) => `<button class="go" data-xp="action" data-action="${esc(a)}">${esc(w)}</button>`).join("");
            this.top.innerHTML = `<div class="xphead">${head}</div>
              <div class="xphint">${m.result ? "" : esc(m.hint)}</div>
              <div class="xpbar"><span style="width:${pct.toFixed(1)}%"></span></div>
              <div class="xprank">RANK: ${esc(m.rank).toUpperCase()} &nbsp; ${m.xp} XP &nbsp; ${next ? `${next[0] - m.xp} XP to ${esc(next[1])}` : "top rank!"}
                ${m.result ? "" : `<button class="xpskip" data-xp="skip">Skip</button>`}</div>
              ${buttons ? `<div class="row xpacts">${buttons}</div>` : ""}`;
            if (!this.card.hidden && this.drawnKey !== JSON.stringify([m.result, m.objectives])) {
                this.drawnKey = JSON.stringify([m.result, m.objectives]);
                const r = m.result, best = m.best || {}, secs = r.seconds || 0, fin = best.finished || 1;
                this.card.innerHTML = `<h2>EXPERIENCE ${m.n}: ${esc(m.title).toUpperCase()}</h2><div class="xpdone">COMPLETE</div>
                  <div class="xpstars">${[0, 1, 2].map(i => `<span class="${i < r.stars ? "on" : ""}">★</span>`).join("")}</div>
                  <div class="xpscore">${r.xp} XP &nbsp; rank: ${esc(r.rank).toUpperCase()}</div>
                  <ul>${(m.objectives || []).map(o => `<li class="${o.state === "done" ? "done" : ""}">${o.state === "done" ? "+" : "–"} ${esc(o.title)}</li>`).join("")}</ul>
                  <div class="note">time ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")} &nbsp; best ${best.best_xp ?? r.xp} XP, finished ${fin} time${fin === 1 ? "" : "s"}</div>
                  <div class="row"><button class="go" data-xp="again">START AGAIN</button><button data-xp="close">CLOSE</button></div>`;
            }
            const coachName = `<div class="xpcoach">${esc(m.coach || "COACH")}</div>`;
            if (!this.coach.firstChild || this.coach.dataset.coach !== m.coach) {
                this.coach.dataset.coach = m.coach || "";
                this.coach.innerHTML = coachName + `<div class="xpsay"></div>`;
                this.typed = -1;
            }
        }
        if (this.cls) {
            const c = this.cls, rows = c.learners || [];
            const done = rows.filter(r => r.finished || r.times).length;
            this.classBox.innerHTML = `<div class="xphead">EXPERIENCE ${c.n}: ${esc(c.title).toUpperCase()} &nbsp; ${done} of ${rows.length} finished
                <button class="xpskip" data-xp="stop">END</button></div>
              ${rows.length ? `<table>${rows.slice(0, 12).map(r => `<tr><td>${esc(r.name)}</td>
                <td class="${r.finished ? "ok" : ""}">${r.finished ? "FINISHED " + "★".repeat(r.stars) : `${r.index + 1} of ${r.of}: ${esc(r.objective)}`}</td>
                <td class="note">${r.xp} XP ${esc(r.rank)}${r.best_xp != null ? ` · best ${r.best_xp}` : ""}</td></tr>`).join("")}</table>` : `<div class="note">Nobody is here yet.</div>`}
              ${rows.length > 12 ? `<div class="note">and ${rows.length - 12} more</div>` : ""}`;
        }
    }

    frame() {
        const now = performance.now();
        if (this.m) {
            const say = this.coach.querySelector(".xpsay");
            const n = Math.min(this.sayText.length, Math.floor((now - this.sayAt) / 1000 * TYPE_RATE));
            const k = `${this.saySeq}:${n}`;
            if (say && k !== this.typed) { this.typed = k; say.textContent = this.sayText.slice(0, n); }
        }
        const live = this.toasts.filter(t => now - t[2] < TOAST_MS);
        const key = live.map(t => t[0]).join("|");
        if (key !== this.toastKey) {
            this.toastKey = key;
            this.toasts = live;
            this.toastBox.hidden = !live.length;
            this.toastBox.innerHTML = live.slice().reverse().map(([w, kind]) => `<div class="xptoast ${esc(kind)}">${esc(w)}</div>`).join("");
        }
    }

    // ---------- the teacher's Controls tab (inside every game's Mission row) ----------
    rowHtml() {
        if (this.cls) return `<div class="row"><label>Experience</label><button id="xp-stop" style="background:#9a3326">END EXPERIENCE ${this.cls.n}</button></div>`;
        const list = this.available.length ? this.available : [{n: 1, title: "Orientation"}];
        return `<div class="row"><label>Experience</label>${list.map(e => `<button data-xpstart="${e.n}" class="go">START ${e.n}: ${esc(e.title)}</button>`).join("")}</div>
          <div class="note">An experience is a first session in the game itself: a coach, objectives one at a time, XP and ranks. Every learner has their own run; the box at the top shows how far each has got.</div>`;
    }

    wire(body) {
        body.querySelectorAll("button[data-xpstart]").forEach(b => b.onclick = () => this.send({type: "experience", do: "start", n: Number(b.dataset.xpstart)}));
        const stop = body.querySelector("#xp-stop");
        if (stop) stop.onclick = () => this.send({type: "experience", do: "stop"});
    }
}
