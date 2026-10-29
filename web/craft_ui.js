// Craft Lab's HUD and screens on the page (CHANGE 202), as craft/craft_ui.py draws them in the window:
//
//   the HUD      the crosshair, the hotbar along the bottom (the slot you hold lit, how many of each, a tool's or a
//                piece of armour's wear), the armour row (a pip for each two points worn: CHANGE 203), hearts and food
//                over it (survival), bubbles when your head is under water, the name of what you just picked, the news
//                in the middle, the log bottom left, a red wash when hurt; a tap on a hotbar slot chooses it (a phone)
//   the screens  E: your inventory with the crafting grid (2 x 2) and what it makes, and what you wear (head, chest,
//                legs, feet); at a workbench 3 x 3; a chest's 27 slots; a smelter's three with its flame and arrow; a
//                Craft Bot's nine and what it is doing; creative: every block and item to take, a page at a time.
//                A click picks a stack up or puts it down (the right button: half, or one), shift and a click sends
//                a stack across; E or Esc closes. The screens only ask (the window's click, creative_take and close
//                messages): the server answers with the inventory as it now is, and the screen shows it.
//
// Every slot shows its item as the atlas's own tile (tex/craft_atlas.png, with the server's own blocks painted in:
// craft.js gives it as a picture), so the screens match the world on every tier. HTML over the canvas (#gamehud for the
// HUD, #craftscreen for a screen).

import {B, nameOf} from "./craft_sim.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
export const HOTBAR = 9, SLOTS = 36, CHEST = 27;
const NOT_IN_CREATIVE = new Set(["smelter_lit", "door_top", "wheat", "water", "magma", "corestone"]);
const TITLES = {inventory: "INVENTORY", workbench: "WORKBENCH", chest: "CHEST", smelter: "SMELTER", bot: "CRAFT BOT: what it carries"};
const PARTS = [["helmet", "head"], ["chest", "chest"], ["legs", "legs"], ["boots", "feet"]];

// the tile an item shows as (craft_ui.icon): a block's side (a plant's, a torch's own face), else its icon
export function iconTile(id) {
    const it = B.items.get(id);
    if (!it) return null;
    let name = it.icon;
    const b = it.block !== null && it.block !== undefined ? B.blocks[it.block] : null;
    if (b && b.tiles) {
        name = b.shape === "cube" ? b.tiles[1] : b.tiles[0];
        if (it.key === "door") name = "door_high";
    }
    return name || "particle";
}

// the atlas's picture and where its tiles are (craft.js sets them, the server's blocks painted in)
const atlas = {url: "tex/craft_atlas.png", where: {}, tiles: 16};
export function setAtlas(url, where, tiles = 16) {
    atlas.url = url;
    atlas.where = where;
    atlas.tiles = tiles;
    document.documentElement.style.setProperty("--craft-atlas", `url("${url}")`);
}

export function tileStyle(name) {
    const [col, row] = atlas.where[name] || atlas.where.particle || [0, 0], n = atlas.tiles - 1;
    return `background-position:${(col / n * 100).toFixed(4)}% ${(row / n * 100).toFixed(4)}%`;
}

function iconHtml(id) {
    const t = id ? iconTile(id) : null;
    return t ? `<i class="cr-icon" style="${tileStyle(t)}"></i>` : "";
}

// one slot's insides: its icon, how many, and a wear bar for a tool or a piece of armour that has been used
export function slotHtml(slot, empty = null) {
    if (!slot) return empty ? `<i class="cr-icon cr-empty" style="${tileStyle(empty)}"></i>` : "";
    const [id, n, wear] = slot, it = B.items.get(id) || {};
    let bar = "";
    if ((it.tool || (it.armour !== undefined && it.armour !== null)) && it.uses && wear < it.uses) {
        const k = Math.max(0, wear / it.uses);
        bar = `<b class="cr-wear" style="width:${(80 * k).toFixed(0)}%;background:rgb(${Math.round(255 * (1 - k))},${Math.round(255 * k)},51)"></b>`;
    }
    return iconHtml(id) + (n > 1 ? `<span class="cr-n">${n}</span>` : "") + bar;
}

// ---------- the HUD (craft_ui.Hud) ----------
export class CraftHud {
    constructor() {
        this.news = {text: "", until: 0};
        this.picked = {text: "", until: 0, key: null};
        this.log = [];
        this.keys = {};
        this.onSelect = null;   // slot => ...: a tap on the hotbar (a phone)
    }

    ready() {
        let el = $("gamehud");
        if (!el) {
            el = document.createElement("div");
            el.id = "gamehud";
            document.body.appendChild(el);
        }
        if ($("cr-hotbar")) return el;
        el.className = "hud crafthud";
        el.innerHTML = `<div id="cr-dark"></div><div class="cr-cross">+</div><div id="cr-news"></div><div id="cr-title"></div>
          <div id="cr-log"></div><div id="cr-debug"></div>
          <div id="cr-bottom"><div id="cr-picked"></div>
            <div class="cr-rows"><div id="cr-armour" class="cr-pips"></div><div id="cr-bubbles" class="cr-pips right"></div></div>
            <div class="cr-rows"><div id="cr-hearts" class="cr-pips"></div><div id="cr-food" class="cr-pips right"></div></div>
            <div id="cr-hotbar">${Array.from({length: HOTBAR}, (_, i) => `<div class="cr-slot" data-hot="${i}"></div>`).join("")}</div></div>`;
        $("cr-hotbar").addEventListener("pointerdown", e => {
            const s = e.target.closest ? e.target.closest("[data-hot]") : null;
            if (!s) return;
            e.preventDefault();
            e.stopPropagation();
            if (this.onSelect) this.onSelect(Number(s.dataset.hot));
        });
        this.keys = {};
        return el;
    }

    clear() {
        const el = $("gamehud");
        if (el && el.classList.contains("crafthud")) { el.innerHTML = ""; el.className = "hud"; }
    }

    say(text, now, secs = 4) {
        this.news = {text: String(text || ""), until: now + secs * 1000};
    }

    addLog(text) {
        this.log = [...this.log, String(text || "")].slice(-6);
        this.keys.log = null;
    }

    // h: {inv (the inventory message), hp, food, breath, creative, underWater, hurt, now, title, debug, hidden (no
    //     player of yours: the hotbar and the life rows hidden)}
    update(h) {
        this.ready();
        const set = (id, html, key) => {
            if (this.keys[id] === key) return;
            this.keys[id] = key;
            $(id).innerHTML = html;
        };
        const inv = h.inv, now = h.now;
        $("cr-bottom").hidden = !!h.hidden;
        if (inv && inv.inv) {
            const sel = inv.selected || 0, bar = inv.inv.slice(0, HOTBAR);
            set("cr-hotbar", bar.map((s, i) => `<div class="cr-slot${i === sel ? " lit" : ""}" data-hot="${i}">${slotHtml(s)}</div>`).join(""),
                JSON.stringify([bar, sel]));
            const held = inv.inv[sel], pk = JSON.stringify([sel, held ? held[0] : null]);
            if (pk !== this.picked.key) {
                this.picked = {key: pk, text: held ? nameOf(held[0]) : "", until: now + 2000};
            }
        }
        set("cr-picked", esc(now < this.picked.until ? this.picked.text : ""), now < this.picked.until ? this.picked.text : "");
        // the life rows (craft_ui.Hud.set_life, set_armour): ten pips each, a half for an odd number
        const pips = (n, kind) => Array.from({length: 10}, (_, i) => {
            const on = n >= (i + 1) * 2, half = n === i * 2 + 1;
            return `<i class="cr-pip ${kind}${on ? " on" : half ? " half" : ""}"></i>`;
        }).join("");
        const survival = !h.creative;
        set("cr-hearts", survival ? pips(h.hp, "heart") : "", `${survival}:${h.hp}`);
        set("cr-food", survival ? pips(h.food, "food") : "", `${survival}:${h.food}`);
        const ap = inv ? inv.armour_points || 0 : 0;
        set("cr-armour", survival && ap ? pips(ap, "armour") : "", `${survival}:${ap}`);
        const b = Math.ceil(h.breath - 0.01);
        set("cr-bubbles", survival && h.underWater ? Array.from({length: 10}, (_, i) => `<i class="cr-pip bubble${b > i ? " on" : " gone"}"></i>`).join("") : "",
            `${survival && h.underWater}:${b}`);
        const dark = $("cr-dark");
        if (dark.classList.contains("hurt") !== !!h.hurt) dark.classList.toggle("hurt", !!h.hurt);
        const news = now < this.news.until ? this.news.text : "";
        set("cr-news", esc(news).replace(/\n/g, "<br>"), news);
        set("cr-log", this.log.map(t => `<div>${esc(t)}</div>`).join(""), this.log.join("\n"));
        set("cr-title", esc(h.title || ""), h.title || "");
        set("cr-debug", esc(h.debug || "").replace(/\n/g, "<br>"), h.debug || "");
    }
}

// ---------- a screen (craft_ui.Screen) ----------
export class CraftScreen {
    // msg: the inventory message (open: what is open, or null for your inventory); send(msg): the window's messages
    constructor(msg, send, shiftHeld) {
        this.send = send;
        this.shiftHeld = shiftHeld || (() => false);
        this.kind = msg.open || "inventory";
        this.page = 0;
        this.creativeItems = [...B.items.keys()].sort((a, b) => a - b).filter(i => !NOT_IN_CREATIVE.has(B.items.get(i).key));
        const el = this.el = document.createElement("div");
        el.id = "craftscreen";
        el.className = "hud";
        document.body.appendChild(el);
        this.build(msg);
        el.addEventListener("contextmenu", e => e.preventDefault());
        el.addEventListener("pointermove", e => this.follow(e));
        el.addEventListener("pointerdown", e => this.down(e));
        this.update(msg);
    }

    build(msg) {
        const k = this.kind, creative = !!msg.creative && k === "inventory";
        const slots = (area, n, cls = "") => Array.from({length: n}, (_, i) => `<div class="cr-slot ${cls}" data-area="${area}" data-i="${i}"></div>`).join("");
        let top = "";
        if (k === "inventory" || k === "workbench") {
            const w = msg.grid_w || 2;
            top = `<div class="cr-top">
                ${k === "inventory" ? `<div class="cr-armourcol">${PARTS.map((p, i) => `<div class="cr-slot" data-area="armour" data-i="${i}" title="${p[1]}"></div>`).join("")}
                  <div id="cs-points" class="cr-note"></div></div>` : ""}
                <div class="cr-grid w${w}">${slots("grid", w * w)}</div><div class="cr-arrow">&#10140;</div>
                <div class="cr-slot big" data-area="result" data-i="0"></div></div>
              <div class="cr-note">${w === 2 ? "Put things in the grid: what they make shows on the right." : "A workbench: 3 x 3 makes tools, armour, chests, doors, beds..."}</div>`;
        } else if (k === "chest") {
            top = `<div class="cr-box">${slots("chest", CHEST)}</div>`;
        } else if (k === "bot") {
            top = `<div class="cr-box">${slots("bot", 9)}</div><div id="cs-bot" class="cr-note"></div>
              <div class="cr-note">Give it blocks to build with (shift and click sends a stack); take what it dug.</div>`;
        } else if (k === "smelter") {
            top = `<div class="cr-top smelter"><div class="cr-col">${slots("smelter", 1)}<div class="cr-flame"><b id="cs-flame"></b></div>
                <div class="cr-slot" data-area="smelter" data-i="1"></div></div><div class="cr-progress"><b id="cs-arrow"></b></div>
                <div class="cr-slot big" data-area="smelter" data-i="2"></div></div>
              <div class="cr-note">top: what to smelt &nbsp; bottom: fuel (coal, wood)</div>`;
        }
        const palette = creative ? `<div class="cr-creative"><div class="cr-row"><span id="cs-page"></span><button id="cs-next">next page</button></div>
            <div class="cr-box">${slots("palette", 36)}</div></div>` : "";
        this.el.innerHTML = `<div class="cr-panel ${k}${creative ? " creative" : ""}"><div class="cr-head">${TITLES[k] || k.toUpperCase()}</div>${palette}${top}
            <div class="cr-inv">${Array.from({length: 27}, (_, i) => `<div class="cr-slot" data-area="inv" data-i="${i + HOTBAR}"></div>`).join("")}</div>
            <div class="cr-inv hot">${Array.from({length: HOTBAR}, (_, i) => `<div class="cr-slot" data-area="inv" data-i="${i}"></div>`).join("")}</div>
            <div id="cs-tip" class="cr-note"></div></div><div id="cs-cursor" class="cr-slot cursor"></div>`;
        if (creative) {
            $("cs-next").onclick = () => { this.page = (this.page + 1) % this.pages(); this.showPage(); };
            this.showPage();
        }
    }

    pages() { return Math.max(1, Math.ceil(this.creativeItems.length / 36)); }

    showPage() {
        const start = this.page * 36;
        this.el.querySelectorAll('[data-area="palette"]').forEach(s => {
            const id = this.creativeItems[start + Number(s.dataset.i)];
            s.innerHTML = id ? slotHtml([id, 1, (B.items.get(id) || {}).uses || 0]) : "";
            s.dataset.item = id || "";
        });
        $("cs-page").textContent = `CREATIVE: everything (page ${this.page + 1} of ${this.pages()})`;
    }

    // a click: what the window's Screen.click sends (the right button: right; shift held: shift)
    down(e) {
        const s = e.target.closest ? e.target.closest("[data-area]") : null;
        if (!s) return;
        e.preventDefault();
        const area = s.dataset.area, i = Number(s.dataset.i), right = e.button === 2;
        if (area === "palette") {
            const id = this.creativeItems[this.page * 36 + i];
            if (id) this.send({type: "creative_take", item: id, right});
            return;
        }
        this.send({type: "click", area, slot: i, right, shift: !!(e.shiftKey || this.shiftHeld())});
    }

    follow(e) {
        const c = $("cs-cursor");
        if (c) { c.style.left = `${e.clientX}px`; c.style.top = `${e.clientY}px`; }
        const s = e.target.closest ? e.target.closest("[data-area]") : null;
        const id = s ? this.itemAt(s) : null;
        const tip = id ? nameOf(id) : "";
        if ($("cs-tip").textContent !== tip) $("cs-tip").textContent = tip;
    }

    itemAt(s) {
        const area = s.dataset.area, i = Number(s.dataset.i), m = this.msg || {};
        const pick = {inv: m.inv, grid: m.grid, chest: m.box, bot: m.box, smelter: m.box, armour: m.armour}[area];
        if (area === "palette") return this.creativeItems[this.page * 36 + i] || null;
        if (area === "result") return m.result ? m.result[0] : null;
        const slot = pick ? pick[i] : null;
        return slot ? slot[0] : null;
    }

    update(msg) {
        this.msg = msg;
        const fill = (area, list, empty = null) => this.el.querySelectorAll(`[data-area="${area}"]`).forEach(s => {
            const slot = (list || [])[Number(s.dataset.i)] || null, html = slotHtml(slot, empty ? empty(Number(s.dataset.i)) : null);
            if (s.innerHTML !== html) s.innerHTML = html;
        });
        fill("inv", msg.inv);
        fill("grid", msg.grid);
        fill("armour", msg.armour, i => `slot_${PARTS[i][0]}`);
        const r = msg.result;
        fill("result", [r ? [r[0], r[1], 0] : null]);
        if (["chest", "bot", "smelter"].includes(this.kind)) fill(this.kind, msg.box);
        if ($("cs-points")) {
            const pts = msg.armour_points || 0;
            $("cs-points").textContent = pts ? `armour ${pts} of 20: keeps off ${Math.min(80, pts * 4)}% of a hit` : "";
        }
        if (this.kind === "smelter") {
            $("cs-flame").style.height = `${Math.round((msg.burn || 0) * 100)}%`;
            $("cs-arrow").style.width = `${Math.round((msg.progress || 0) * 100)}%`;
        }
        if (this.kind === "bot" && $("cs-bot")) {
            const info = msg.bot || {}, st = info.stats || {};
            $("cs-bot").textContent = `${info.name || "Your Bot"}: ` + (info.running ? "running your brain" : info.error ? `stopped: ${info.error}`
                : "waiting (U uploads its brain, P the autopilot)") + `   dug ${st.dug || 0}   placed ${st.placed || 0}   moves ${st.moves || 0}`;
        }
        const c = $("cs-cursor"), html = slotHtml(msg.cursor || null);
        if (c && c.innerHTML !== html) c.innerHTML = html;
    }

    destroy() {
        this.el.remove();
    }
}
