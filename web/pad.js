// Game controllers on the page (CHANGE 170): engine/gamepad.py's twin, through the browser's Gamepad API.
//
// A pad plugged in by USB, or paired by Bluetooth in the computer's settings (Xbox, PlayStation, Nintendo Switch
// and most others), is the browser's once a button on it has been pressed with the page open. Chrome and Edge give
// the common ones the "standard" layout, so every game reads a pad by where a button is, not what it's called:
// south (Xbox A, PlayStation cross, Nintendo B), east (B, circle, Nintendo A), west (X, square, Nintendo Y),
// north (Y, triangle, Nintendo X), lb and rb (the shoulders), lt and rt (the triggers, 0 to 1), back, start, and
// up, down, left, right (the d-pad, which counts as the stick). read() gives the left stick (x right, y up, a dead
// zone in the middle), the triggers, the buttons held and those pressed since the last read.

export const DEAD = 0.22;
const STANDARD = {south: 0, east: 1, west: 2, north: 3, lb: 4, rb: 5, lt: 6, rt: 7, back: 8, start: 9,
                  up: 12, down: 13, left: 14, right: 15};

export function deadZone(x, y) {
    const r = Math.hypot(x, y);
    if (r < DEAD) return [0, 0];
    const k = Math.min(1, (r - DEAD) / (1 - DEAD)) / r;
    return [Math.max(-1, Math.min(1, x * k)), Math.max(-1, Math.min(1, y * k))];
}

// a trigger with its dead zone (the first tenth) taken out: 0 to 1 smoothly from there (engine/gamepad.trigger)
export function trigger(v) { return v <= 0.1 ? 0 : Math.min(1, (v - 0.1) / 0.9); }

export class Pads {
    constructor(list = () => (navigator.getGamepads ? [...navigator.getGamepads()] : [])) {
        this.list = list;
        this.was = new Set();
        this.id = null;
    }

    // the newest pad connected (the one last used, when there are several)
    pad() {
        const pads = this.list().filter(p => p && p.connected);
        if (!pads.length) return null;
        return pads.reduce((a, b) => (b.timestamp || 0) > (a.timestamp || 0) ? b : a);
    }

    read() {
        const p = this.pad();
        if (!p) { this.was = new Set(); return null; }
        if (p.id !== this.id) { this.id = p.id; this.was = new Set(); }
        const held = new Set(), b = p.buttons || [], ax = p.axes || [];
        const value = i => (b[i] ? (typeof b[i] === "object" ? (b[i].value || (b[i].pressed ? 1 : 0)) : Number(b[i])) : 0);
        for (const [name, i] of Object.entries(STANDARD)) if (value(i) > 0.5) held.add(name);
        let [x, y] = deadZone(ax[0] || 0, -(ax[1] || 0));  // (the browser's y is down)
        if (held.has("left") || held.has("right")) x = (held.has("right") ? 1 : 0) - (held.has("left") ? 1 : 0);
        if (held.has("up") || held.has("down")) y = (held.has("up") ? 1 : 0) - (held.has("down") ? 1 : 0);
        let lt = value(6), rt = value(7);
        lt = trigger(lt);
        rt = trigger(rt);
        const pressed = new Set([...held].filter(n => !this.was.has(n)));
        this.was = held;
        const [rx, ry] = deadZone(ax[2] || 0, -(ax[3] || 0));  // (CHANGE 202: the right stick, Craft Lab's looking about)
        return {x, y, lt, rt, held, pressed, rx, ry, name: p.id || "controller"};
    }
}
