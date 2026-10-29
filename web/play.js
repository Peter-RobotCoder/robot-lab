// Playing from the page (CHANGE 134): the keyboard as each game's window reads it, sent as the windows send it.
//
// Robot Lab (lab_client.send_controls): the arrows drive, Space fires (a tap is kept until it is sent); reversing,
// left and right arc the other way, as a car does. Fight Lab (fight_client): the arrows move your fighter the way
// they point on the screen (the camera decides, so right always moves right), A punch, S kick, D special, W throw,
// Space jump, F cartwheel, Shift blocks, X crouches. Kart Lab: the arrows (or WASD) drive, Shift drifts, Space (or
// E) uses your item, B is the handbrake, the throttle tapped then held drops the clutch (CHANGE 181), R respawns.
// Each control is numbered and sent the moment it changes, and otherwise 30 times a second (60 for the
// kart, as its window's clock runs), so one lost on the way is made good by the next and the server ignores one
// that comes late. While you type in the panel, or the page is behind another window, nothing is pressed.
// (CHANGE 170) A game controller works alongside the keys (pad.js): the stick or d-pad as the arrows; Robot Lab:
// the bottom face button fires; Fight Lab: left punch, bottom kick, right special, top jump, right shoulder throw,
// right trigger cartwheel, left shoulder blocks, left trigger crouches; Kart Lab: the bottom button or right trigger
// goes, the right button or left trigger brakes, the right shoulder drifts, the left shoulder or left button uses
// your item, Back (Minus) respawns; Start is I (the side panel) in all three. (CHANGE 187) A phone's touch controls
// (touch.js) are read in the pad's shape, so they drive the same way: the slider steers, GO and BRAKE the triggers, DRIFT
// the right shoulder, HANDBRAKE the top button, the item button the left one, RESET Back.
// (CHANGE 201) City Lab (city_client.read_keys): on foot WASD or the arrows walk (W is away from the camera: the game
// turns the keys into a move in the world, as the window's FootCamera.move_from_keys), Shift runs, Space jumps, J
// punches, K kicks, B blocks, E gets into the car beside you; in a car Kart Lab's keys (W go, S brake, A D steer, Shift
// drift, B handbrake, the clutch drop), E gets out; R back to the depot. A pad on foot: the stick walks, the bottom
// button jumps, the left punches, the right kicks, the top gets in, the left shoulder blocks, the right runs; in a car
// as Kart Lab's (the left button or shoulder gets out). Ticked as the kart's: every 1/60 s tick an input, predicted.
// (CHANGE 202) Craft Lab (craft_client.read_keys): WASD or the arrows walk the way you look (the game turns them into a
// move in the world's frame by its yaw), Space jumps (and swims up, and flies up), Shift sneaks (and flies down), W
// twice sprints; a pad's stick walks, the bottom button jumps, the right shoulder sprints, the left sneaks, the right
// stick looks about, the triggers dig and place, the top button opens the inventory, the left throws one. The game
// reads them itself (keysInput): the buttons JUMP 1, SPRINT 2, SNEAK 4, FLY 8, ticked and predicted as City Lab's.

import {Pads} from "./pad.js";

const MOVE_KEYS = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", " "]);
const FIGHT_PRESS = {a: "punch", s: "kick", d: "special", w: "throw", " ": "jump", f: "cartwheel"};
const PAD_PRESS = [["west", "punch"], ["south", "kick"], ["east", "special"], ["north", "jump"], ["rb", "throw"], ["rt", "cartwheel"]];
const hundredths = v => Math.round(v * 100) / 100;  // (analogue, as the windows send it: half a push is half the speed)

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
            const k = typeof e.key !== "string" ? "" : e.key.length === 1 ? e.key.toLowerCase() : e.key;  // (a synthetic event may have no key)
            if (MOVE_KEYS.has(e.key) && this.active) e.preventDefault();  // (the arrows and Space don't scroll the page)
            if (!this.down.has(k)) this.taps.push(k);
            this.down.add(k);
            if (this.onKey) this.onKey(k, e);
        });
        window.addEventListener("keyup", e => {
            const k = typeof e.key !== "string" ? "" : e.key.length === 1 ? e.key.toLowerCase() : e.key;  // (a synthetic event may have no key)
            this.down.delete(k);
        });
        // a key held as the page loses focus would never let go (its key-up never comes): let everything go
        window.addEventListener("blur", () => { this.down.clear(); this.taps = []; if (this.onLetGo) this.onLetGo(); });
        document.addEventListener("visibilitychange", () => {
            if (document.hidden) { this.down.clear(); this.taps = []; if (this.onLetGo) this.onLetGo(); }
        });
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
        this.kind = kind;            // "robot", "fight", "kart" or "city"
        this.seq = 0;
        this.last = null;
        this.lastSend = 0;
        this.sent = new Map();       // seq -> when it went (the control delay, from the server's acks)
        this.ctrlMs = null;
        // (CHANGE 175) the tab hidden or the page unfocused: a neutral control goes at once (the frame loop that
        // would have sent it stops with the tab), so a kart, robot or fighter isn't left driving on the last keys
        keys.onLetGo = () => {
            const game = this.app.game;
            if (!game || !game.myId || game.myId() === null || game.myId() === undefined) return;
            this.seq = (this.seq + 1) % 65536;
            if (this.kind === "kart" || this.kind === "city" || this.kind === "craft") { if (game.sendNeutral) game.sendNeutral(); }
            else if (this.kind === "fight") this.app.send({type: "control", seq: this.seq, f: 0, s: 0, hold: ""});
            else this.app.send({type: "control", seq: this.seq, throttle: 0, steer: 0, fire: false});
            this.last = null;
        };
        this.pads = new Pads();      // (CHANGE 170) a USB or Bluetooth controller
        this.pad = null;             // ...as read this frame
        this.touch = null;           // (CHANGE 187) the phone's touch controls (app.js sets it), read as a pad
    }

    robotControl() {
        const K = this.keys;
        let throttle = (K.is("ArrowUp") ? 1 : 0) - (K.is("ArrowDown") ? 1 : 0);
        let steer = (K.is("ArrowLeft") ? 1 : 0) - (K.is("ArrowRight") ? 1 : 0);
        let fire = K.is(" ") || this.tapped.includes(" ");
        const pad = this.pad;
        if (pad && !throttle && !steer) {  // (the stick, the d-pad or the triggers)
            throttle = hundredths(pad.y || pad.rt - pad.lt);
            steer = hundredths(-pad.x);
        }
        if (pad) fire = fire || pad.held.has("south") || pad.pressed.has("south");
        if (throttle < 0) steer = -steer;  // (reversing: left and right arc the robot the other way, CHANGE 113)
        return {throttle, steer, fire};
    }

    fightControl() {
        const K = this.keys, game = this.app.game;
        let sx = (K.is("ArrowRight") ? 1 : 0) - (K.is("ArrowLeft") ? 1 : 0);
        let sy = (K.is("ArrowUp") ? 1 : 0) - (K.is("ArrowDown") ? 1 : 0);
        const pad = this.pad;
        if (pad && !sx && !sy) { sx = hundredths(pad.x); sy = hundredths(pad.y); }
        const block = K.is("Shift") || !!(pad && pad.held.has("lb")), crouch = K.is("x") || !!(pad && pad.held.has("lt"));
        const hold = block && crouch ? "low_block" : block ? "block" : crouch ? "crouch" : "";
        let f = 0, s = 0;
        if ((sx || sy) && game && game.stick) [f, s] = game.stick(sx, sy);
        return {f: Math.round(f * 100) / 100, s: Math.round(s * 100) / 100, hold};
    }

    kartControl() {
        const K = this.keys;
        let throttle = (K.is("ArrowUp", "w") ? 1 : 0) - (K.is("ArrowDown", "s") ? 1 : 0);
        let steer = (K.is("ArrowLeft", "a") ? 1 : 0) - (K.is("ArrowRight", "d") ? 1 : 0);
        let buttons = 0;
        if (K.is("Shift")) buttons |= 1;               // DRIFT
        if (K.is("b")) buttons |= 16;                  // HANDBRAKE (CHANGE 181)
        if (this.tapped.includes("r")) buttons |= 4;   // RESPAWN (once per press)
        if (this.tapped.includes("e") || this.tapped.includes(" ")) buttons |= 2;  // USE: your item (once per press: CHANGE 159; Space, CHANGE 181)
        const pad = this.pad;
        if (pad) {  // (CHANGE 170)
            if (!throttle) throttle = Math.max(pad.rt, pad.held.has("south") ? 1 : 0) - Math.max(pad.lt, pad.held.has("east") ? 1 : 0);
            if (!steer) steer = -pad.x;
            if (pad.held.has("rb")) buttons |= 1;
            if (pad.held.has("north")) buttons |= 16;
            if (pad.pressed.has("back")) buttons |= 4;
            if (pad.pressed.has("lb") || pad.pressed.has("west")) buttons |= 2;
            pad.pressed = new Set();  // (a press goes in one tick: the kart's are many a frame)
        }
        buttons |= this.launchButton(throttle > 0);
        this.consumed = true;
        return {throttle, steer, buttons};
    }

    // (CHANGE 201) City Lab's input (city_client.read_keys): in a car the pedals and the wheel as the kart's; on foot the
    // move in the world's frame (throttle x east, steer y north: the game's footMove from the keys and the camera) and
    // the buttons: RUN 1, ACTION 2 (E), RESPAWN 4 (R), BLOCK 16, PUNCH 32, KICK 64, JUMP 128
    cityControl() {
        const K = this.keys, game = this.app.game, pad = this.pad;
        let buttons = 0;
        if (this.tapped.includes("r")) buttons |= 4;
        if (this.tapped.includes("e")) buttons |= 2;
        if (game.driving && game.driving()) {
            let throttle = (K.is("ArrowUp", "w") ? 1 : 0) - (K.is("ArrowDown", "s") ? 1 : 0);
            let steer = (K.is("ArrowLeft", "a") ? 1 : 0) - (K.is("ArrowRight", "d") ? 1 : 0);
            if (K.is("Shift")) buttons |= 1;   // DRIFT
            if (K.is("b")) buttons |= 16;      // HANDBRAKE
            if (pad) {
                if (!throttle) throttle = Math.max(pad.rt, pad.held.has("south") ? 1 : 0) - Math.max(pad.lt, pad.held.has("east") ? 1 : 0);
                if (!steer) steer = -pad.x;
                if (pad.held.has("rb")) buttons |= 1;
                if (pad.held.has("north")) buttons |= 16;
                if (pad.pressed.has("back")) buttons |= 4;
                if (pad.pressed.has("west") || pad.pressed.has("lb")) buttons |= 2;
                pad.pressed = new Set();
            }
            buttons |= this.launchButton(throttle > 0);
            this.consumed = true;
            return {throttle, steer, buttons};
        }
        this.thWas = this.launchArmed = false;  // (on foot: the clutch is a car's)
        let forward = (K.is("ArrowUp", "w") ? 1 : 0) - (K.is("ArrowDown", "s") ? 1 : 0);
        let right = (K.is("ArrowRight", "d") ? 1 : 0) - (K.is("ArrowLeft", "a") ? 1 : 0);
        if (pad && !forward && !right) { forward = pad.y || 0; right = pad.x || 0; }
        if (K.is("Shift")) buttons |= 1;       // RUN
        if (K.is(" ")) buttons |= 128;         // JUMP
        if (K.is("b")) buttons |= 16;          // BLOCK
        if (this.tapped.includes("j")) buttons |= 32;  // PUNCH (once per press)
        if (this.tapped.includes("k")) buttons |= 64;  // KICK
        if (pad) {
            if (pad.held.has("south")) buttons |= 128;
            if (pad.pressed.has("west")) buttons |= 32;
            if (pad.pressed.has("east")) buttons |= 64;
            if (pad.held.has("lb")) buttons |= 16;
            if (pad.pressed.has("north")) buttons |= 2;
            if (pad.held.has("rb")) buttons |= 1;
            if (pad.pressed.has("back")) buttons |= 4;
            pad.pressed = new Set();
        }
        const [mx, my] = game.footMove ? game.footMove(forward, right) : [0, 0];
        this.consumed = true;
        return {throttle: mx, steer: my, buttons};
    }

    // (CHANGE 202) Craft Lab's input: the game's own reading of the keys and the pad (CraftGame.keysInput)
    craftControl() {
        const game = this.app.game;
        this.consumed = true;
        return game.keysInput ? game.keysInput(this.keys, this.pad, this.tapped) : {throttle: 0, steer: 0, buttons: 0};
    }

    // (CHANGE 181, kart_client.launch_button) the clutch dropped: the throttle let go and pressed again within 0.35 s
    // while the kart is nearly still arms LAUNCH, held until the throttle is let go (the step spins the back wheels
    // while the kart is under 6 m/s: a burnout, or a donut with the wheel turned)
    launchButton(pressed) {
        const now = performance.now(), game = this.app.game;
        if (pressed && !this.thWas) {
            const v = game && game.mySpeed ? game.mySpeed() : 0;
            if (now - (this.thReleased ?? -1e9) < 350 && Math.abs(v) < 3.0) this.launchArmed = true;
        } else if (!pressed && this.thWas) {
            this.thReleased = now;
            this.launchArmed = false;
        }
        this.thWas = pressed;
        return this.launchArmed && pressed ? 8 : 0;
    }

    // called every frame: sends a control when it changed, or when it's time to repeat it
    tick(now) {
        const game = this.app.game;
        if (!game || !game.myId || game.myId() === null || game.myId() === undefined) { this.keys.active = false; return; }
        this.keys.active = true;
        // (CHANGE 181) Kart Lab's taps wait for a tick: a frame with no tick in it (a 120 Hz screen draws two frames a
        // tick) threw the taps of that frame away, and a press of E (or R) was lost half the time
        const ticked = this.kind === "kart" || this.kind === "city" || this.kind === "craft";
        this.tapped = (ticked ? this.tapped || [] : []).concat(this.keys.takeTaps());
        let pad = this.pads.read();  // (CHANGE 170: every frame, so a button tapped between two isn't lost)
        const t = this.touch && this.touch.shown ? this.touch.read() : null;  // (CHANGE 187: a finger down, or no pad: the touch controls)
        if (t && (t.active || !pad)) pad = t;
        if (pad && this.padCarry) for (const b of this.padCarry) pad.pressed.add(b);  // (...nor between two ticks)
        this.padCarry = null;
        this.pad = pad;
        if (this.pad && this.keys.typing()) this.pad = null;
        if (this.pad && this.pad.pressed.has("start") && this.keys.onKey) this.keys.onKey("i", {target: null});
        if (ticked && game.controlFrame) {  // (Kart Lab, City Lab and Craft Lab tick their own inputs: their prediction needs them)
            const dt = Math.min(0.1, (now - (this.lastFrame || now)) / 1000);
            this.lastFrame = now;
            this.consumed = false;
            game.controlFrame(now, () => {
                const c = this.kind === "city" ? this.cityControl() : this.kind === "craft" ? this.craftControl() : this.kartControl();
                this.tapped = [];
                return c;
            }, dt);
            if (!this.consumed && this.pad && this.pad.pressed.size) this.padCarry = new Set(this.pad.pressed);
            if (this.tapped.length > 30) this.tapped = this.tapped.slice(-30);
            return;
        }
        let msg, press = null;
        if (this.kind === "robot") msg = this.robotControl();
        else if (this.kind === "fight") {
            msg = this.fightControl();
            // (CHANGE 182: Shift+F is the teacher's fix, app.js's, not a cartwheel)
            const t = this.tapped.find(k => FIGHT_PRESS[k] && !(k === "f" && this.keys.down.has("Shift")));
            if (t) press = FIGHT_PRESS[t];
            else if (this.pad) press = (PAD_PRESS.find(([b]) => this.pad.pressed.has(b)) || [])[1] || null;
        } else msg = this.kartControl();
        const key = JSON.stringify(msg);
        const every = this.kind === "kart" ? 1000 / 60 : 1000 / 30;
        if (!press && key === this.last && now - this.lastSend < every) return;
        this.seq = (this.seq + 1) % 65536;
        const out = {type: "control", seq: this.seq, ...msg};
        if (press) out.press = press;
        if (this.kind === "kart" && game.sendInput) game.sendInput(msg, this.seq, now);  // (prediction: kart.js)
        else this.app.send(out);
        if ((this.kind === "robot" || this.kind === "fight") && game.controlSent) game.controlSent(out, now);  // (yours drawn ahead: CHANGE 166, 167; the press: 193)
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
