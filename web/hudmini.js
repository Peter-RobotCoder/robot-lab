// The information over the game, minimised (CHANGE 187): each box (the events log, the frame rate box, the standings,
// Kart Lab's LAP and place, speed and drift meter, minimap, damage panel, tyres and item) has a "–" at its corner that
// folds it to a small pill with its name (a tap on the pill brings it back; the item's words need no box), and the HUD button beside ≡ PANEL hides
// every box at once and brings them back (the countdown, WRONG WAY, the pit line, a toast and the results stay: they
// are the race). Both are kept on this computer (hud_mini, hud_clean), so a phone set up once stays clear. apply()
// runs every frame from app.js's loop, since the games rebuild their boxes (innerHTML) as they go.

const $ = id => document.getElementById(id);

// [selector, the pill's name]
export const BOXES = [["#events", "LOG"], ["#perf", "STATS"], ["#places", "PLACES"], ["#kh-mapbox", "MAP"], ["#kh-dmg", "DAMAGE"],
                      ["#kh-tyres", "TYRES"], [".karthud .kbottom", "SPEED"], [".karthud .ktop", "LAP"],
                      ["#mh-status", "MISSION"], ["#mh-log", "RUN LOG"],  // (the Missions': CHANGE 199)
                      ["#ch-mapbox", "CITY MAP"], ["#ch-health", "HEALTH"],  // (City Lab's: CHANGE 201)
                      ["#cr-log", "MESSAGES"], ["#cr-title", "WHO"]];  // (Craft Lab's: CHANGE 202)

export class HudMini {
    constructor() {
        this.mini = new Set();
        this.clean = false;
        try {
            this.mini = new Set(JSON.parse(localStorage.getItem("hud_mini") || "[]"));
            this.clean = localStorage.getItem("hud_clean") === "1";
        } catch (e) { /* storage blocked */ }
    }

    keep() {
        try {
            localStorage.setItem("hud_mini", JSON.stringify([...this.mini]));
            localStorage.setItem("hud_clean", this.clean ? "1" : "0");
        } catch (e) { /* private window */ }
    }

    toggle(name) {
        if (this.mini.has(name)) this.mini.delete(name); else this.mini.add(name);
        this.keep();
        this.apply();
    }

    // the HUD button: every box hidden, or back as each was
    toggleClean() {
        this.clean = !this.clean;
        this.keep();
        this.apply();
    }

    apply() {
        for (const [sel, name] of BOXES) {
            const el = document.querySelector(sel);
            if (!el) continue;
            if (!el.querySelector(":scope > .mini-btn")) {  // (the box rebuilt: its corner button and pill again)
                const b = document.createElement("button");
                b.className = "mini-btn";
                b.title = "Fold this away (a tap on its name brings it back)";
                b.textContent = "–";
                b.addEventListener("pointerdown", e => { e.preventDefault(); e.stopPropagation(); this.toggle(name); });
                b.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); });
                const p = document.createElement("i");  // (an i: the boxes style their own spans and divs)
                p.className = "mini-pill";
                p.textContent = name;
                p.title = "Bring it back";
                p.addEventListener("pointerdown", e => { e.preventDefault(); e.stopPropagation(); this.toggle(name); });
                el.appendChild(b);
                el.appendChild(p);
            }
            const on = this.mini.has(name);
            if (el.classList.contains("mini") !== on) el.classList.toggle("mini", on);
        }
        if (document.body.classList.contains("clean") !== this.clean) document.body.classList.toggle("clean", this.clean);
        const btn = $("hudbtn");
        if (btn) {
            const words = this.clean ? "HUD OFF" : "HUD";
            if (btn.textContent !== words) btn.textContent = words;
            btn.classList.toggle("off", this.clean);
        }
    }
}
