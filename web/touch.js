// Touch controls (CHANGE 187): Kart Lab played on a phone or a tablet, with the fingers instead of the keys.
//
// An overlay over the race (#touchpad, built here): at the bottom left a steering slider (the thumb slid left or
// right steers by how far, let go it springs to the middle), at the bottom right the pedals GO and BRAKE (reverse),
// DRIFT (held, as Shift), the item button (tap: Space; it shows the item you hold), and two small ones, HANDBRAKE
// (held, as B) and RESET (tap, as R); at the top VIEW (V), WATCH (L) and FULL SCREEN, with a big FULL SCREEN button
// in the middle until the page is (the browser's address bar and tabs gone, the phone turned sideways). Every finger is its own pointer
// (several at once: steer and GO and DRIFT), kept to the button it landed on until it lifts, as a pedal is.
//
// play.js reads it as it reads a game controller (pad.js's shape: x right, the triggers rt and lt, the buttons held,
// those pressed since the last read), so the kart's controls, the clutch drop (GO tapped then held) and the carried
// taps are the one code. Shown when the page's Touch controls setting says so: Auto (a touchscreen whose main pointer
// is a finger: a phone, a tablet), On, Off; ?touch=1 or ?touch=0 in the address overrides it. body.touch rearranges
// the HUD round the controls (style.css).

const $ = id => document.getElementById(id);
const hundredths = v => Math.round(v * 100) / 100;
const DEAD = 0.06;        // the slider's middle, where the kart steers straight
const REACH = 0.8;        // the slider's share either side of the middle that reaches full lock

// a touchscreen whose main pointer is a finger (a phone or a tablet; a touch laptop's is its mouse or trackpad)
export function coarsePointer() {
    return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
}

export class TouchPad {
    constructor() {
        this.el = null;
        this.shown = false;
        this.fingers = new Map();   // pointerId -> {btn, el}: the fingers down and what each is on
        this.pressed = new Set();   // "item" and "reset" tapped since the last read
        this.steer = 0;             // the slider: -1 full left, 1 full right
        this.onKey = null;          // k => ...: VIEW and WATCH press the page's V and L
        this.onToast = null;        // text => ...: a word of advice (turn the phone sideways)
        this.item = "";
        this.hinted = false;
        const letGo = () => this.letGo();
        window.addEventListener("blur", letGo);
        document.addEventListener("visibilitychange", () => { if (document.hidden) letGo(); });
    }

    build() {
        const el = this.el = document.createElement("div");
        el.id = "touchpad";
        el.className = "hud";
        el.hidden = true;
        el.innerHTML = `
          <div class="tp-left"><div id="tp-steer" data-btn="steer"><span class="tp-arrow">&#9664;</span><span class="tp-arrow r">&#9654;</span><i class="tp-knob"></i></div></div>
          <div class="tp-right">
            <div class="tp-small"><button data-btn="hand">HAND<br>BRAKE</button><button data-btn="reset">RESET</button></div>
            <button class="tp-drift" data-btn="drift">DRIFT</button>
            <button class="tp-go" data-btn="go">GO</button>
            <button class="tp-item" id="tp-item" data-btn="item">ITEM</button>
            <button class="tp-brake" data-btn="brake">BRAKE</button>
          </div>
          <div class="tp-top"><button data-key="v">VIEW</button><button data-key="l">WATCH</button><button data-full title="Full screen">&#x26F6;</button></div>
          <button class="tp-fullbig" data-full>&#x26F6; FULL SCREEN<small>the whole screen, no browser bars</small></button>`;
        document.body.appendChild(el);
        document.addEventListener("fullscreenchange", () => this.fullChanged());
        this.fullChanged();
        el.addEventListener("pointerdown", e => this.down(e));
        // (VIEW, WATCH and FULL SCREEN on the click, after the finger lifts: a page may only go full screen on a
        // user's gesture, and a touch's pointerdown isn't one to the browser, its pointerup and click are)
        el.addEventListener("click", e => {
            const b = e.target.closest ? e.target.closest("[data-key], [data-full]") : null;
            if (!b) return;
            e.preventDefault();
            if (b.dataset.key) { if (this.onKey) this.onKey(b.dataset.key); } else this.fullscreen();
        });
        el.addEventListener("pointermove", e => this.move(e));
        el.addEventListener("pointerup", e => this.up(e));
        el.addEventListener("pointercancel", e => this.up(e));
        el.addEventListener("contextmenu", e => e.preventDefault());   // (a finger held: no menu)
        el.addEventListener("dblclick", e => e.preventDefault());
        this.knob = el.querySelector(".tp-knob");
        this.setItem(this.item);
    }

    show() {
        if (!this.el) this.build();
        this.el.hidden = false;
        this.shown = true;
        document.body.classList.add("touch");
        if (!this.hinted && this.onToast && window.innerHeight > window.innerWidth) {
            this.hinted = true;
            this.onToast("Turn your phone sideways to see the track; the full screen button is at the top");
        }
    }

    hide() {
        if (this.el) this.el.hidden = true;
        this.shown = false;
        this.letGo();
        document.body.classList.remove("touch");
    }

    // every finger lifted (the page hidden, the controls hidden): nothing stays pressed
    letGo() {
        for (const f of this.fingers.values()) if (f.el) f.el.classList.remove("on");
        this.fingers.clear();
        this.pressed = new Set();
        this.setSteer(0);
    }

    down(e) {
        const b = e.target.closest ? e.target.closest("[data-btn]") : null;
        if (!b) return;
        e.preventDefault();
        try { b.setPointerCapture(e.pointerId); } catch (err) { /* a pretend pointer (the tests) */ }
        const btn = b.dataset.btn;
        this.fingers.set(e.pointerId, {btn, el: b});
        if (btn === "steer") { this.steerAt(e.clientX); return; }
        b.classList.add("on");
        if (btn === "item" || btn === "reset") this.pressed.add(btn);
        if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) { /* not allowed */ } }
    }

    move(e) {
        const f = this.fingers.get(e.pointerId);
        if (f && f.btn === "steer") { e.preventDefault(); this.steerAt(e.clientX); }
    }

    up(e) {
        const f = this.fingers.get(e.pointerId);
        if (!f) return;
        this.fingers.delete(e.pointerId);
        if (f.btn === "steer") {
            if (![...this.fingers.values()].some(o => o.btn === "steer")) this.setSteer(0);
        } else if (![...this.fingers.values()].some(o => o.btn === f.btn)) f.el.classList.remove("on");
    }

    // the thumb at screen x on the slider: straight within DEAD of the middle, full lock at REACH of the half width
    steerAt(x) {
        const r = $("tp-steer").getBoundingClientRect(), half = r.width / 2;
        if (!half) return;
        let s = (x - (r.left + half)) / (half * REACH);
        s = Math.max(-1, Math.min(1, s));
        if (Math.abs(s) < DEAD) s = 0;
        this.setSteer(s);
    }

    setSteer(s) {
        this.steer = s;
        if (this.knob) this.knob.style.left = `${50 + s * REACH * 50}%`;
    }

    // the item button's words: the item you hold (kart.js, each frame), or ITEM
    setItem(name) {
        this.item = name || "";
        const b = $("tp-item");
        if (!b) return;
        const words = this.item ? this.item.toUpperCase() : "ITEM";
        if (b.textContent !== words) b.textContent = words;
        b.classList.toggle("has", !!this.item);
    }

    // the page the whole screen, no address bar or tabs, sideways where the browser lets a page ask (Android's
    // Chrome does; an iPhone's Safari has no full screen for a page: there, the page added to the home screen opens
    // without the browser's bars, manifest.webmanifest, and the button says how)
    fullscreen() {
        const d = document;
        if (d.fullscreenElement) { if (d.exitFullscreen) d.exitFullscreen().catch(() => {}); return; }
        if (!d.fullscreenEnabled || !d.documentElement.requestFullscreen) {
            if (this.onToast) this.onToast("This browser has no full screen for a page. Share, then Add to Home Screen: Club Coders opens from there with no browser bars.");
            return;
        }
        const p = d.documentElement.requestFullscreen({navigationUI: "hide"});
        if (p && p.then) p.then(() => {
            const o = screen.orientation;
            if (o && o.lock) o.lock("landscape").catch(() => {});
        }).catch(err => {
            this.fullError = String(err && err.message || err);  // (the tests and a console read it)
            if (this.onToast) this.onToast("The browser wouldn't go full screen (" + this.fullError + "); try its own full screen or Add to Home Screen.");
        });
    }

    // in full screen (or opened from the home screen) the big button goes; the small one says EXIT
    fullChanged() {
        if (!this.el) return;
        const full = !!document.fullscreenElement || (window.matchMedia && window.matchMedia("(display-mode: standalone), (display-mode: fullscreen)").matches);
        this.el.querySelector(".tp-fullbig").hidden = full;
        this.el.querySelector(".tp-top [data-full]").innerHTML = full ? "&#x26F6; EXIT" : "&#x26F6;";
    }

    // this moment's reading in pad.js's shape: x the slider (right positive), rt GO, lt BRAKE, DRIFT as the right
    // shoulder, HANDBRAKE as the top button, the item as the left button and RESET as Back (pressed: once each tap);
    // active: a finger is down or a tap waits, so a game controller plugged in as well is read when this is idle
    read() {
        const btns = new Set([...this.fingers.values()].map(f => f.btn));
        const taps = this.pressed;
        this.pressed = new Set();
        const held = new Set(), pressed = new Set();
        if (btns.has("drift")) held.add("rb");
        if (btns.has("hand")) held.add("north");
        if (taps.has("item")) pressed.add("west");
        if (taps.has("reset")) pressed.add("back");
        return {x: hundredths(this.steer), y: 0, lt: btns.has("brake") ? 1 : 0, rt: btns.has("go") ? 1 : 0,
                held, pressed, active: this.fingers.size > 0 || pressed.size > 0, name: "touch"};
    }
}
