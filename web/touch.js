// Touch controls (CHANGE 187): Kart Lab played on a phone or a tablet, with the fingers instead of the keys; (CHANGE
// 201) City Lab too: in a car the same controls (the item button GET OUT), on foot a stick and the moves.
//
// An overlay over the race (#touchpad, built here): at the bottom left a steering slider (the thumb slid left or
// right steers by how far, let go it springs to the middle), at the bottom right the pedals GO and BRAKE (reverse),
// DRIFT (held, as Shift), the item button (tap: Space; it shows the item you hold), and two small ones, HANDBRAKE
// (held, as B) and RESET (tap, as R); at the top VIEW (V), WATCH (L) and FULL SCREEN, with a big FULL SCREEN button
// in the middle until the page is (the browser's address bar and tabs gone, the phone turned sideways). Every finger is its own pointer
// (several at once: steer and GO and DRIFT), kept to the button it landed on until it lifts, as a pedal is.
//
// (CHANGE 201) On foot in City Lab (setLayout("foot")): a stick at the bottom left (the thumb anywhere on it walks that
// way, by how far it is from the middle, the camera deciding which way is which as the keys do; let go it springs
// back), and RUN and BLOCK (held), PUNCH, KICK and GET IN (tapped), JUMP (held) and RESET at the bottom right.
//
// (CHANGE 202) Craft Lab (setLayout("craft")): the stick at the bottom left walks; a finger dragged anywhere else on
// the screen looks about (takeLook: the pixels it moved since the last frame); at the bottom right DIG and PLACE
// (held: the triggers, as a pad's), JUMP, SNEAK and RUN (held), FLY (creative), BAG (the inventory, E) and DROP
// (tapped); a tap on a hotbar slot (the HUD's) chooses it.
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
const STICK_DEAD = 0.12;  // (CHANGE 201) the stick's middle, where you stand still
const TAPS = ["item", "reset", "punch", "kick", "getin", "fly", "inv", "drop"];  // (the buttons that are tapped, not held)

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
        this.stick = [0, 0];        // (CHANGE 201) the stick on foot: x right, y up, each -1 to 1
        this.layout = "kart";       // kart, car (City Lab driving: the item button gets you out), foot (City Lab) or craft
        this.look = [0, 0];         // (CHANGE 202) Craft Lab: how far a finger has dragged to look about, since last taken
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
          <div class="tp-foot">
            <div class="tp-stickbox" id="tp-stick" data-btn="stick"><i class="tp-stickknob"></i></div>
            <div class="tp-moves"><button data-btn="run">RUN</button><button data-btn="block">BLOCK</button><button data-btn="reset">RESET</button>
              <button data-btn="punch">PUNCH</button><button data-btn="kick">KICK</button><button data-btn="getin">GET<br>IN</button>
              <button data-btn="jump">JUMP</button></div>
          </div>
          <div class="tp-craft">
            <div class="tp-stickbox" id="tp-cstick" data-btn="cstick"><i class="tp-stickknob"></i></div>
            <div class="tp-cmoves"><button data-btn="fly">FLY</button><button data-btn="inv">BAG</button><button data-btn="drop">DROP</button>
              <button data-btn="sneak">SNEAK</button><button data-btn="run">RUN</button><button data-btn="place">PLACE</button>
              <button data-btn="jump">JUMP</button><button data-btn="dig">DIG</button></div>
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
        this.stickKnob = el.querySelector("#tp-stick .tp-stickknob");
        this.cstickKnob = el.querySelector("#tp-cstick .tp-stickknob");
        this.setItem(this.item);
        this.el.classList.toggle("foot", this.layout === "foot");
        this.el.classList.toggle("craft", this.layout === "craft");
    }

    // (CHANGE 201) which controls: "kart" (Kart Lab), "car" (City Lab driving: the item button is GET OUT) or "foot"
    // (City Lab on foot: the stick and the moves)
    setLayout(name) {
        if (name === this.layout) return;
        const was = this.layout;
        this.layout = name;
        if (!this.el) return;
        this.el.classList.toggle("foot", name === "foot");
        this.el.classList.toggle("craft", name === "craft");
        if (name === "car") this.setItem("GET OUT");
        else if (was === "car") this.setItem("");
        this.letGo();
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
        this.setStick(0, 0);
    }

    down(e) {
        const b = e.target.closest ? e.target.closest("[data-btn]") : null;
        if (!b) {  // (CHANGE 202: Craft Lab, a finger anywhere else looks about)
            if (this.layout === "craft" && !(e.target.closest && e.target.closest("button, [data-hot]"))) {
                e.preventDefault();
                this.fingers.set(e.pointerId, {btn: "look", el: null, x: e.clientX, y: e.clientY});
            }
            return;
        }
        e.preventDefault();
        try { b.setPointerCapture(e.pointerId); } catch (err) { /* a pretend pointer (the tests) */ }
        const btn = b.dataset.btn;
        this.fingers.set(e.pointerId, {btn, el: b});
        if (btn === "steer") { this.steerAt(e.clientX); return; }
        if (btn === "stick" || btn === "cstick") { this.stickAt(e.clientX, e.clientY, btn); return; }
        b.classList.add("on");
        if (TAPS.includes(btn)) this.pressed.add(btn);
        if (navigator.vibrate) { try { navigator.vibrate(8); } catch (err) { /* not allowed */ } }
    }

    move(e) {
        const f = this.fingers.get(e.pointerId);
        if (f && f.btn === "steer") { e.preventDefault(); this.steerAt(e.clientX); }
        if (f && (f.btn === "stick" || f.btn === "cstick")) { e.preventDefault(); this.stickAt(e.clientX, e.clientY, f.btn); }
        if (f && f.btn === "look") {
            e.preventDefault();
            this.look[0] += e.clientX - f.x;
            this.look[1] += e.clientY - f.y;
            f.x = e.clientX;
            f.y = e.clientY;
        }
    }

    // (CHANGE 202) how far the looking finger has moved since the last call (screen pixels: x right, y down)
    takeLook() {
        const l = this.look;
        this.look = [0, 0];
        return l;
    }

    up(e) {
        const f = this.fingers.get(e.pointerId);
        if (!f) return;
        this.fingers.delete(e.pointerId);
        if (f.btn === "steer") {
            if (![...this.fingers.values()].some(o => o.btn === "steer")) this.setSteer(0);
        } else if (f.btn === "stick" || f.btn === "cstick") {
            if (![...this.fingers.values()].some(o => o.btn === "stick" || o.btn === "cstick")) this.setStick(0, 0);
        } else if (f.btn === "look") {
            /* (nothing held) */
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

    // (CHANGE 201) the thumb at screen (x, y) on the stick: still within STICK_DEAD of the middle, full speed at REACH
    // of its radius, never more than full
    stickAt(x, y, which = "stick") {
        const r = $(which === "cstick" ? "tp-cstick" : "tp-stick").getBoundingClientRect(), half = r.width / 2;
        if (!half) return;
        let sx = (x - (r.left + half)) / (half * REACH), sy = -(y - (r.top + r.height / 2)) / (half * REACH);
        const m = Math.hypot(sx, sy);
        if (m > 1) { sx /= m; sy /= m; }
        if (m < STICK_DEAD) { sx = 0; sy = 0; }
        this.setStick(sx, sy);
    }

    setStick(sx, sy) {
        this.stick = [sx, sy];
        const t = `translate(${(sx * REACH * 45).toFixed(1)}px, ${(-sy * REACH * 45).toFixed(1)}px)`;
        if (this.stickKnob) this.stickKnob.style.transform = t;
        if (this.cstickKnob) this.cstickKnob.style.transform = t;
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
        if (this.layout === "craft") {  // (CHANGE 202: the stick walks, DIG and PLACE the triggers, as a pad's)
            if (btns.has("jump")) held.add("south");
            if (btns.has("sneak")) held.add("lb");
            if (btns.has("run")) held.add("rb");
            for (const k of ["fly", "inv", "drop"]) if (taps.has(k)) pressed.add(k);
            return {x: hundredths(this.stick[0]), y: hundredths(this.stick[1]), lt: btns.has("place") ? 1 : 0, rt: btns.has("dig") ? 1 : 0,
                    held, pressed, active: this.fingers.size > 0 || pressed.size > 0, name: "touch"};
        }
        if (this.layout === "foot") {  // (CHANGE 201: as a pad on foot is read: the stick; south jumps, west punches...)
            if (btns.has("run")) held.add("rb");
            if (btns.has("block")) held.add("lb");
            if (btns.has("jump")) held.add("south");
            if (taps.has("punch")) pressed.add("west");
            if (taps.has("kick")) pressed.add("east");
            if (taps.has("getin")) pressed.add("north");
            return {x: hundredths(this.stick[0]), y: hundredths(this.stick[1]), lt: 0, rt: 0, held, pressed,
                    active: this.fingers.size > 0 || pressed.size > 0, name: "touch"};
        }
        return {x: hundredths(this.steer), y: 0, lt: btns.has("brake") ? 1 : 0, rt: btns.has("go") ? 1 : 0,
                held, pressed, active: this.fingers.size > 0 || pressed.size > 0, name: "touch"};
    }
}
