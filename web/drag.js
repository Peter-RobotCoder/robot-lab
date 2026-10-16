// Panels moved and resized as in the windows (CHANGE 143): hud.py's code panel (dragged by its title bar, resized by
// its corner: code_at, code_size) and Robot Lab's health bars (dragged by their title: lab_client's hud_at). The page
// keeps each place on this computer (localStorage "place:<key>"), put back on the screen when the window is smaller;
// a double click on the handle puts the panel back where it started.
//
// makeDraggable(el, key, {handle, resize, minW, minH}): handle is a CSS selector inside el to drag by (null: anywhere
// on el), matched as the pointer goes down, so it may be drawn again under it (the health bars are, 30 times a second).
// Buttons, boxes and links inside the handle are left to work. resize adds a corner grip. It gives {apply, reset,
// release}: apply puts the kept place in force again, reset forgets it, release takes it all off el (another game).

const NOT_A_HANDLE = "button, input, select, textarea, a, label, .dragsize";

export function makeDraggable(el, key, {handle = null, resize = false, minW = 240, minH = 140} = {}) {
    if (!el) return {apply() {}, reset() {}, release() {}};
    const store = "place:" + key;
    let place = null, drag = null;
    try { place = JSON.parse(localStorage.getItem(store) || "null"); } catch (e) { place = null; }
    const keep = () => { try { localStorage.setItem(store, JSON.stringify(place)); } catch (e) { /* private window */ } };
    let grip = null;
    if (resize) {
        grip = document.createElement("div");
        grip.className = "dragsize";
        grip.title = "Drag to make it bigger or smaller";
        el.append(grip);
    }
    el.classList.add("draggable");

    // the kept place, on the screen: the whole panel when it fits, and never its title bar off the top
    function apply() {
        if (!place) return;
        const vw = window.innerWidth, vh = window.innerHeight;
        const w = place.w ? Math.max(minW, Math.min(place.w, vw - 8)) : null;
        const h = place.h ? Math.max(minH, Math.min(place.h, vh - 8)) : null;
        const ew = w || el.offsetWidth || 200, eh = h || el.offsetHeight || 60;
        const x = Math.max(0, Math.min(place.x, vw - ew)), y = Math.max(0, Math.min(place.y, vh - Math.min(eh, 40)));
        Object.assign(el.style, {left: x + "px", top: y + "px", right: "auto", bottom: "auto", transform: "none"});
        if (w) el.style.width = w + "px";
        if (h) { el.style.height = h + "px"; el.style.maxHeight = "none"; }
    }

    function reset() {
        place = null;
        try { localStorage.removeItem(store); } catch (e) { /* private window */ }
        for (const p of ["left", "top", "right", "bottom", "transform", "width", "height", "maxHeight"]) el.style[p] = "";
    }

    function onDown(e) {
        if (e.button !== undefined && e.button !== 0) return;
        const t = e.target;
        const sizing = grip && (t === grip);
        if (!sizing) {
            if (t.closest && t.closest(NOT_A_HANDLE)) return;
            if (handle && !(t.closest && t.closest(handle) && el.contains(t.closest(handle)))) return;
        }
        const r = el.getBoundingClientRect();
        drag = {sizing, px: e.clientX, py: e.clientY, x: r.left, y: r.top, w: r.width, h: r.height, id: e.pointerId};
        try { el.setPointerCapture(e.pointerId); } catch (err) { /* gone */ }
        e.preventDefault();
    }

    function onMove(e) {
        if (!drag || e.pointerId !== drag.id) return;
        const dx = e.clientX - drag.px, dy = e.clientY - drag.py;
        if (drag.sizing) place = {x: drag.x, y: drag.y, w: Math.round(drag.w + dx), h: Math.round(drag.h + dy)};
        else place = {x: Math.round(drag.x + dx), y: Math.round(drag.y + dy), ...(resize ? {w: Math.round(drag.w), h: Math.round(drag.h)} : {})};
        apply();
    }

    function onUp(e) {
        if (!drag || (e && e.pointerId !== drag.id)) return;
        drag = null;
        if (place) keep();
    }

    function onDouble(e) {
        const t = e.target;
        if (t.closest && t.closest(NOT_A_HANDLE)) return;
        if (handle && !(t.closest && t.closest(handle))) return;
        reset();
    }

    const listeners = [[el, "pointerdown", onDown], [el, "pointermove", onMove], [el, "pointerup", onUp],
                       [el, "pointercancel", onUp], [el, "dblclick", onDouble], [window, "resize", apply]];
    for (const [target, ev, fn] of listeners) target.addEventListener(ev, fn);
    apply();

    function release() {
        for (const [target, ev, fn] of listeners) target.removeEventListener(ev, fn);
        if (grip) grip.remove();
        el.classList.remove("draggable");
        for (const p of ["left", "top", "right", "bottom", "transform", "width", "height", "maxHeight"]) el.style[p] = "";
    }

    return {apply, reset, release};
}
