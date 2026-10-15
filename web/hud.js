// The games' on-screen displays in the page (CHANGE 134), after the windows' own:
// - Fight Lab (fight_hud.py): the two fighters' health bars, with a white trail catching up after a hit and shrinking
//   towards the outside edge; round-win pips; the energy meters ("SPECIAL READY" at 50); the round timer, red under
//   10; the ring's label; the big banner (ROUND 1, FIGHT!, K.O.!); the combo counter on the attacker's side; in
//   practice, the training readout of the last hit. You are always on the left.
// - Kart Lab (kart_gfx.Hud): LAP n/N, your place, km/h, the drift and boost meter with its MINI TURBO and SUPER TURBO
//   marks, WRONG WAY, and the minimap with every kart.
// One element (#gamehud) over the 3D view, redrawn each frame from what the game already has.

const $ = id => document.getElementById(id);

function box() {
    let el = $("gamehud");
    if (!el) {
        el = document.createElement("div");
        el.id = "gamehud";
        el.className = "hud";
        document.body.appendChild(el);
    }
    return el;
}

export function hideHud() {
    const el = $("gamehud");
    if (el) { el.innerHTML = ""; el.className = "hud"; }
}

const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// ---------- Fight Lab ----------
export class FightHud {
    constructor() {
        this.trail = {};     // fighter id -> the white trail's share
        this.combo = [{text: "", until: 0}, {text: "", until: 0}];
        this.lastHit = "";
    }

    // ring: the watched ring from the newest snapshot; names: id -> {name, owner}; myId: yours (or null)
    update(ring, names, myId, roundsToWin, dt, now) {
        const el = box();
        if (!ring || !(ring.f || []).length) { el.innerHTML = ""; return; }
        el.className = "hud fighthud";
        const fs = ring.f;
        const order = fs.length === 2 && fs.some(f => f.id === myId) ? [...fs].sort((a, b) => (a.id === myId ? 0 : 1) - (b.id === myId ? 0 : 1)) : fs;
        // the combo counter: a new last hit of two or more, not blocked, shows on the attacker's side for 1.3 s
        const lh = ring.lh;
        const key = lh ? JSON.stringify(lh) : "";
        if (lh && key !== this.lastHit && !lh.blocked && (lh.combo || 0) >= 2) {
            const side = order.findIndex(f => f.id === lh.by);
            if (side >= 0) this.combo[side] = {text: `${lh.combo} HITS!${lh.counter ? "<br>COUNTER" : ""}`, until: now + 1300};
        }
        this.lastHit = key;
        const sides = [0, 1].map(i => {
            const f = order[i];
            if (!f) return `<div class="fside s${i}"></div>`;
            const info = names.get(f.id) || {name: "?", owner: ""};
            const share = Math.max(0, Math.min(1, f.hp / Math.max(1, f.max)));
            const t = this.trail[f.id] ?? share;
            this.trail[f.id] = Math.max(share, t - dt * 0.35);
            const colour = share > 0.5 ? "#4de65a" : share > 0.25 ? "#ffd933" : "#ff4d40";
            const en = Math.max(0, Math.min(100, f.en || 0)), ready = en >= 50;
            const pips = Array.from({length: roundsToWin}, (_, k) => `<i class="${k < (f.w || 0) ? "won" : ""}"></i>`).join("");
            const combo = now < this.combo[i].until ? `<div class="combo">${this.combo[i].text}</div>` : "";
            return `<div class="fside s${i}">
              <div class="fname ${f.id === myId ? "you" : ""}">${esc(info.name)}${f.id === myId ? "  (YOU)" : ""}</div>
              <div class="fbar"><b class="trail" style="width:${this.trail[f.id] * 100}%"></b><b class="fill" style="width:${share * 100}%;background:${colour}"></b></div>
              <div class="fowner">${esc(info.owner)}${f.ap ? "   AUTOPILOT" : ""}</div>
              <div class="pips">${pips}</div>
              <div class="energy"><b style="width:${en}%;background:${ready ? "#ffcc33" : "#8cd9ff"}"></b></div>
              <div class="etext ${ready ? "ready" : ""}">${ready ? "SPECIAL READY" : "ENERGY"}</div>${combo}</div>`;
        });
        const tl = ring.tl;
        const timer = tl === null || tl === undefined ? "" : `<div class="ftimer ${tl < 10 ? "low" : ""}">${Math.max(0, Math.floor(tl + 0.99))}</div>`;
        const bn = ring.bn || "";
        const big = ["K.O.!", "PERFECT!", "FIGHT!"].includes(bn);
        const banner = bn ? `<div class="fbanner ${big ? "big" : bn.length > 10 ? "long" : ""} ${["K.O.!", "RING OUT!"].includes(bn) ? "red" : ""}">${esc(bn)}</div>` : "";
        const sub = ring.ph === "ko" && bn && !bn.includes("WINS") ? `<div class="fsub">ROUND ${ring.rd}</div>` : "";
        let training = "";
        if (tl === null || tl === undefined) {
            if (lh) {
                const who = (names.get(lh.by) || {name: "?"}).name;
                const what = lh.blocked ? "BLOCKED" : (lh.combo || 0) > 1 ? `combo ${lh.combo}` : "hit";
                training = `TRAINING &nbsp; ${esc(who)}: ${esc(String(lh.move || "").replace(/_/g, " ").toUpperCase())} (${esc(lh.height || "")}) &nbsp; ${Number(lh.dmg || 0).toFixed(1)} damage &nbsp; ${what}${lh.counter ? " &nbsp; COUNTER HIT" : ""}`;
            } else training = "TRAINING &nbsp; practice: nobody loses health";
        }
        el.innerHTML = `${sides.join("")}<div class="fmid">${ring.lb ? `<div class="flabel">${esc(ring.lb)}</div>` : ""}${timer}</div>${banner}${sub}` +
                       (training ? `<div class="ftraining">${training}</div>` : "");
    }
}

// ---------- Kart Lab ----------
const MINI_TURBO = 270, SUPER_TURBO = 570, CHARGE_MAX = SUPER_TURBO;  // (the bar is full at SUPER TURBO, as the window's)

function ordinal(n) {
    const s = ["th", "st", "nd", "rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export class KartHud {
    constructor() {
        this.mapKey = "";
    }

    // me: our kart's state (interpolated or predicted), states: every kart, race: the race message, track
    update(me, states, race, track, myId, colours) {
        const el = box();
        if (!me || !race) { el.innerHTML = ""; this.built = false; return; }  // (emptied: built again when there's a kart)
        el.className = "hud karthud";
        const laps = race.laps || 3, places = race.places || [];
        const place = places.indexOf(myId) + 1;
        const lap = Math.min(laps, Math.max(1, (me.lap || 0) + 1));
        const kmh = Math.round(Math.abs(me.v || 0) * 3.6);
        const charge = Math.max(0, Math.min(CHARGE_MAX, me.charge || 0));
        const wrong = (me.flags & 8) && race.phase === 1;
        if (!this.built || this.mapKey !== track.name || !$("kh-lap")) this.build(el, track);  // (or the page emptied it)
        $("kh-lap").textContent = race.phase === 2 && (me.flags & 4) ? "FINISHED" : laps >= 99 ? `LAP ${lap}` : `LAP ${lap}/${laps}`;  // (practice: laps without end)
        $("kh-place").textContent = place ? `${ordinal(place)} of ${places.length}` : "";
        $("kh-speed").textContent = `${kmh} km/h`;
        $("kh-drift").style.width = `${charge / CHARGE_MAX * 100}%`;
        const flash = Math.floor(performance.now() / 100) % 2;
        $("kh-drift").style.background = charge >= SUPER_TURBO ? (flash ? "#fff299" : "#ff9933") : charge >= MINI_TURBO ? "#ff9933" : "#8cd9ff";
        $("kh-dlabel").textContent = charge >= SUPER_TURBO ? "SUPER TURBO" : charge >= MINI_TURBO ? "MINI TURBO" : "DRIFT";
        $("kh-wrong").style.display = wrong && Math.floor(performance.now() / 400) % 2 === 0 ? "block" : "none";
        this.drawMap(states, myId, colours);
    }

    build(el, track) {
        el.innerHTML = `<div class="ktop"><div id="kh-lap"></div><div id="kh-place"></div></div>
          <div id="kh-wrong">WRONG WAY</div>
          <div class="kbottom"><div class="kdrift"><span id="kh-dlabel">DRIFT</span><div class="kmeter"><b id="kh-drift"></b>
            <i style="left:${MINI_TURBO / CHARGE_MAX * 100}%"></i></div></div>
            <div id="kh-speed"></div></div>
          <canvas id="kh-map" width="220" height="220"></canvas>`;
        this.track = track;
        this.mapKey = track.name;
        this.built = true;
        const [x0, y0, x1, y1] = track.bounds();
        const s = 200 / Math.max(x1 - x0, y1 - y0);
        this.toMap = (x, y) => [10 + (x - x0) * s, 210 - (y - y0) * s];
        // the outline, drawn once into its own canvas
        const bg = this.outline = document.createElement("canvas");
        bg.width = bg.height = 220;
        const c = bg.getContext("2d");
        c.strokeStyle = "rgba(230,235,245,0.9)";
        c.lineWidth = 5;
        c.lineJoin = "round";
        c.beginPath();
        track.pts.forEach((p, i) => { const [mx, my] = this.toMap(p[0], p[1]); if (i) c.lineTo(mx, my); else c.moveTo(mx, my); });
        c.closePath();
        c.stroke();
        const a = track.point(0, track.half), b = track.point(0, -track.half);
        c.strokeStyle = "#fff";
        c.lineWidth = 3;
        c.beginPath();
        c.moveTo(...this.toMap(a[0], a[1]));
        c.lineTo(...this.toMap(b[0], b[1]));
        c.stroke();
    }

    drawMap(states, myId, colours) {
        const cv = $("kh-map");
        if (!cv) return;
        const c = cv.getContext("2d");
        c.clearRect(0, 0, 220, 220);
        c.drawImage(this.outline, 0, 0);
        for (const [id, st] of states) {
            const [mx, my] = this.toMap(st.x, st.y);
            c.fillStyle = colours.get(id) || "#ccc";
            c.beginPath();
            c.arc(mx, my, id === myId ? 6 : 4, 0, Math.PI * 2);
            c.fill();
            if (id === myId) { c.strokeStyle = "#fff"; c.lineWidth = 2; c.stroke(); }
        }
    }
}
