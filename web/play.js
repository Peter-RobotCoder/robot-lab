// Playing from the page (CHANGE 134): the keyboard as each game's window reads it, sent as the windows send it.
//
// Robot Lab (lab_client.send_controls): the arrows drive, Space fires (a tap is kept until it is sent); reversing,
// left and right arc the other way, as a car does. Fight Lab (fight_client): the arrows move your fighter the way
// they point on the screen (the camera decides, so right always moves right), A punch, S kick, D special, W throw,
// Space jump, F cartwheel, Shift blocks, X crouches. Kart Lab: the arrows (or WASD) drive, Shift or Space drifts, R
// respawns. Each control is numbered and sent the moment it changes, and otherwise 30 times a second (60 for the
// kart, as its window's clock runs), so one lost on the way is made good by the next and the server ignores one
// that comes late. While you type in the panel, or the page is behind another window, nothing is pressed.

const MOVE_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " "]);
const FIGHT_PRESS = {a: "punch", s: "kick", d: "special", w: "throw", " ": "jump", f: "cartwheel"};

export class Keys {
    constructor() {
        this.down = new Set();
        this.taps = [];           // keys pressed since the last control went out (a quick tap isn't lost)
        this.typing = () => {
            const a = document.activeElement;
            return !!a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName) && a.type !== "checkbox" && a.type !== "button";
        };
        window.addEventListener("keydown", e => {
            if (this.typing() || e.ctrlKey || e.metaKey || e.altKey) return;
            const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
            if (MOVE_KEYS.has(e.key) && this.active) e.preventDefault();  // (the arrows and Space don't scroll the page)
            if (!this.down.has(k)) this.taps.push(k);
            this.down.add(k);
            if (this.onKey) this.onKey(k, e);
        });
        window.addEventListener("keyup", e => {
            const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
            this.down.delete(k);
        });
        // a key held as the page loses focus would never let go (its key-up never comes): let everything go
        window.addEventListener("blur", () => { this.down.clear(); this.taps = []; });
        document.addEventListener("visibilitychange", () => { if (document.hidden) { this.down.clear(); this.taps = []; } });
        this.active = false;
    }

    is(...names) {
        return !this.typing() && names.some(n => this.down.has(n));
    }

    takeTaps() {
        const t = this.taps;
        this.taps = [];
        return this.typing() ? [] : t;
    }
}

// one game's controls: control() gives this moment's control (or null: nothing to drive), send(msg) sends it
export class Controller {
    constructor(app, keys, kind) {
        this.app = app;
        this.keys = keys;
        this.kind = kind;            // "robot", "fight" or "kart"
        this.seq = 0;
        this.last = null;
        this.lastSend = 0;
        this.sent = new Map();       // seq -> when it went (the control delay, from the server's acks)
        this.ctrlMs = null;
    }

    robotControl() {
        const K = this.keys;
        let throttle = (K.is("ArrowUp") ? 1 : 0) - (K.is("ArrowDown") ? 1 : 0);
        let steer = (K.is("ArrowLeft") ? 1 : 0) - (K.is("ArrowRight") ? 1 : 0);
        if (throttle < 0) steer = -steer;  // (reversing: left and right arc the robot the other way, CHANGE 113)
        const fire = K.is(" ") || this.tapped.includes(" ");
        return {throttle, steer, fire};
    }

    fightControl() {
        const K = this.keys, game = this.app.game;
        const sx = (K.is("ArrowRight") ? 1 : 0) - (K.is("ArrowLeft") ? 1 : 0);
        const sy = (K.is("ArrowUp") ? 1 : 0) - (K.is("ArrowDown") ? 1 : 0);
        const block = K.is("Shift"), crouch = K.is("x");
        const hold = block && crouch ? "low_block" : block ? "block" : crouch ? "crouch" : "";
        let f = 0, s = 0;
        if ((sx || sy) && game && game.stick) [f, s] = game.stick(sx, sy);
        return {f: Math.round(f * 100) / 100, s: Math.round(s * 100) / 100, hold};
    }

    kartControl() {
        const K = this.keys;
        const throttle = (K.is("ArrowUp", "w") ? 1 : 0) - (K.is("ArrowDown", "s") ? 1 : 0);
        const steer = (K.is("ArrowLeft", "a") ? 1 : 0) - (K.is("ArrowRight", "d") ? 1 : 0);
        let buttons = 0;
        if (K.is("Shift", " ")) buttons |= 1;          // DRIFT
        if (this.tapped.includes("r")) buttons |= 4;   // RESPAWN (once per press)
        if (this.tapped.includes("e")) buttons |= 2;   // USE: your item (once per press: CHANGE 159)
        return {throttle, steer, buttons};
    }

    // called every frame: sends a control when it changed, or when it's time to repeat it
    tick(now) {
        const game = this.app.game;
        if (!game || !game.myId || game.myId() === null || game.myId() === undefined) { this.keys.active = false; return; }
        this.keys.active = true;
        this.tapped = this.keys.takeTaps();
        if (this.kind === "kart" && game.controlFrame) {  // (Kart Lab ticks its own inputs: its prediction needs them)
            const dt = Math.min(0.1, (now - (this.lastFrame || now)) / 1000);
            this.lastFrame = now;
            game.controlFrame(now, () => { const c = this.kartControl(); this.tapped = []; return c; }, dt);
            return;
        }
        let msg, press = null;
        if (this.kind === "robot") msg = this.robotControl();
        else if (this.kind === "fight") {
            msg = this.fightControl();
            const t = this.tapped.find(k => FIGHT_PRESS[k]);
            if (t) press = FIGHT_PRESS[t];
        } else msg = this.kartControl();
        const key = JSON.stringify(msg);
        const every = this.kind === "kart" ? 1000 / 60 : 1000 / 30;
        if (!press && key === this.last && now - this.lastSend < every) return;
        this.seq = (this.seq + 1) % 65536;
        const out = {type: "control", seq: this.seq, ...msg};
        if (press) out.press = press;
        if (this.kind === "kart" && game.sendInput) game.sendInput(msg, this.seq, now);  // (prediction: kart.js)
        else this.app.send(out);
        if ((this.kind === "robot" || this.kind === "fight") && game.controlSent) game.controlSent(msg, now);  // (yours drawn ahead: CHANGE 166, 167)
        this.sent.set(this.seq, now);
        if (this.sent.size > 90) for (const k of [...this.sent.keys()].slice(0, 30)) this.sent.delete(k);
        this.last = key;
        this.lastSend = now;
    }

    // a snapshot said which of our controls the server had applied: how long a key press takes to show
    ack(seq, now) {
        const at = this.sent.get(seq);
        if (at === undefined) return;
        const ms = now - at;
        this.ctrlMs = this.ctrlMs === null ? ms : this.ctrlMs * 0.8 + ms * 0.2;
    }
}
