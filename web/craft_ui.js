// Craft Lab's HUD, screens and Esc menu on the page (CHANGE 202; the lab visor since CHANGE 207), as craft/craft_ui.py
// draws them in the window, in Club Coders' own look (the website's tokens: navy cards, a thin light line, the cyan
// and lime glows; Space Grotesk titles, Inter text, JetBrains Mono for the dev panel, Press Start 2P for slot counts):
//
//   the HUD      bottom left the status card (Health in lime with the Shield over its track in cyan, Energy in amber,
//                and what your Craft Bot is doing), the CAREFUL tag over it; bottom middle the Toolbelt (8 rounded
//                slots in a pill, the held one glowing cyan, counts in pixel letters, a lime-to-coral line for the
//                uses left; a tap on one chooses it, a phone); in the middle a cyan dot in a thin ring (the ring fills
//                clockwise as you dig; under water an amber ring empties: your air); the news in a pill at the top,
//                the log bottom right, a coral wash when hurt, and the dev panel top right (the ` key)
//   the screens  I: the Backpack, with tabs: BACKPACK (the suit's three slots on a lab-suit figure, the 6 x 5 Backpack;
//                a Locker's 6 x 4 above it with its name to type; a Refinery's conveyor: the queue, the refining
//                window glowing magenta while it works, the tray, the power gauge and its slot), BLUEPRINTS (search,
//                category chips, each row its parts had and needed and BUILD, the build queue's cyan bar), BOT (your
//                Craft Bot: what it does, its slots from its dock, GARAGE, CODE and BRAIN), and in Sandbox the
//                PALETTE. Click to pick up and put down, right click to split, Shift and click to send across, drag
//                and drop, SORT. The screens only ask (the window's click, build, sort, tab, locker_name,
//                creative_take and close messages): the server answers with the inventory as it now is.
//   the menu     Esc: the Club Coders logo, RESUME, GRAPHICS, CREDITS (THIRD_PARTY_NOTICES.md), QUIT.
//
// Every slot shows its item as the atlas's own tile (tex/craft_atlas.png, with the server's own blocks painted in:
// craft.js gives it as a picture), so the screens match the world on every tier. HTML over the canvas (#gamehud for
// the HUD, #craftscreen for a screen, #craftmenu for the menu).

import {B, nameOf} from "./craft_sim.js";

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

// craft_items' sizes: the Toolbelt (0 to 7, keys 1 to 8) and the Backpack (8 to 37, 6 across); a Locker 24 (6 x 4);
// a Refinery 17 (the queue 0 to 7, the power slot 8, the tray 9 to 16); the suit's three slots
export const TOOLBELT = 8, SLOTS = 38, BACKPACK_W = 6, LOCKER = 24, QUEUE = 8, TRAY = 8, POWER_SLOT = 8, SUIT = 3, BOT_SLOTS = 9;
export const REACH = 4.0;   // (craft_items.REACH: metres from a Fabricator's middle to build its blueprints)
export const CATEGORIES = ["Build", "Tools", "Suit", "Bot", "Food"];
const GROUPS = {any_log: ["log", "pine_log", "pale_log"], any_boards: ["boards", "pine_boards"], any_coal: ["coal", "charcoal"],
                any_fluff: ["fluff", "fluff_red", "fluff_yellow", "fluff_green", "fluff_blue", "fluff_purple", "fluff_black"]};
const GROUP_NAMES = {any_log: "Log (any)", any_boards: "Boards (any)", any_coal: "Coal or charcoal", any_fluff: "Fluff (any)"};
const SUIT_PARTS = ["visor", "vest", "boots"];
const PALETTE_CHIPS = ["All", "Blocks", "Machines", "Plants", "Items", "Tools", "Suit"];
const NOT_IN_PALETTE = new Set(["refinery_on", "door_top", "grain", "water", "magma", "lab_floor", "glitch_rift"]);
const KIND_TITLES = {locker: "LOCKER", refinery: "REFINERY", fabricator: "FABRICATOR", bot: "CRAFT BOT"};
const TABS = [["backpack", "BACKPACK"], ["blueprints", "BLUEPRINTS"], ["bot", "BOT"]];
const BP_PER_PAGE = 8, PALETTE_ACROSS = 14, PALETTE_PER_PAGE = 14 * 4;
const LIME = [182, 255, 59], CORAL = [255, 107, 91];
const RING_C = 2 * Math.PI * 10;  // (the crosshair ring's length: radius 10 in its 28 x 28 box)

// ---------- blueprints (craft_items: ids, part_name, have, can_build) ----------
function partIds(part) {
    return new Set((GROUPS[part] || [part]).map(k => B.itemId[k]).filter(i => i !== undefined));
}
export function partName(part) { return GROUP_NAMES[part] || nameOf(B.itemId[part]); }
export function have(inv, part) {
    const want = partIds(part);
    return (inv || []).reduce((n, s) => n + (s && want.has(s[0]) ? s[1] : 0), 0);
}
export function canBuild(inv, bp) { return Object.entries(bp.parts || {}).every(([k, n]) => have(inv, k) >= n); }

// ---------- the atlas's tiles ----------
// the tile an item shows as (craft_ui.icon): a block's side (a plant's own face), else its icon
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
    document.documentElement.style.setProperty("--craft-tiles", `${tiles * 100}%`);
}

export function tileStyle(name) {
    const [col, row] = atlas.where[name] || atlas.where.particle || [0, 0], n = atlas.tiles - 1;
    return `background-position:${(col / n * 100).toFixed(4)}% ${(row / n * 100).toFixed(4)}%`;
}

function iconHtml(id, cls = "") {
    const t = id ? iconTile(id) : null;
    return t ? `<i class="cr-icon${cls}" style="${tileStyle(t)}"></i>` : "";
}

// one slot's insides: its icon, how many (pixel letters), and a uses line (lime to coral) for a worn tool or suit piece
export function slotHtml(slot, empty = null) {
    if (!slot) return empty ? `<i class="cr-icon cr-empty" style="${tileStyle(empty)}"></i>` : "";
    const [id, n, wear] = slot, it = B.items.get(id) || {};
    let bar = "";
    if ((it.tool || (it.suit !== undefined && it.suit !== null)) && it.uses && wear < it.uses) {
        const k = Math.max(0, wear / it.uses), c = LIME.map((v, i) => Math.round(v * k + CORAL[i] * (1 - k)));
        bar = `<b class="cr-uses" style="width:${(72 * k).toFixed(0)}%;background:rgb(${c.join(",")})"></b>`;
    }
    return iconHtml(id) + (n > 1 ? `<span class="cr-n">${n}</span>` : "") + bar;
}

const slotDiv = (area, i, cls = "") => `<div class="cr-slot${cls ? " " + cls : ""}" data-area="${area}" data-i="${i}"></div>`;

// ---------- the HUD (craft_ui.Hud) ----------
export class CraftHud {
    constructor() {
        this.news = {text: "", until: 0};
        this.picked = {text: "", until: 0, key: null};
        this.log = [];
        this.keys = {};
        this.onSelect = null;   // slot => ...: a tap on the Toolbelt (a phone)
    }

    ready() {
        let el = $("gamehud");
        if (!el) {
            el = document.createElement("div");
            el.id = "gamehud";
            document.body.appendChild(el);
        }
        if ($("cr-toolbelt")) return el;
        el.className = "hud crafthud";
        el.innerHTML = `<div id="cr-dark"></div>
          <div class="cr-cross"><svg viewBox="0 0 28 28" width="28" height="28"><circle cx="14" cy="14" r="10" class="cr-track"/>
            <circle id="cr-fill" cx="14" cy="14" r="10" class="cr-fill" transform="rotate(-90 14 14)" stroke-dasharray="0 ${RING_C.toFixed(2)}"/></svg><i></i></div>
          <div id="cr-news"></div><div id="cr-title"></div><div id="cr-log"></div><div id="cr-dev" hidden></div>
          <div id="cr-careful" hidden>CAREFUL</div>
          <div id="cr-status">
            <div class="cr-bar" data-bar="hp"><div class="cr-label">HEALTH <span id="cr-shieldtext"></span></div>
              <div class="cr-track"><b class="cr-barfill" id="cr-hpfill"></b><b class="cr-shield" id="cr-shieldfill"></b></div><span class="cr-num" id="cr-hpnum"></span></div>
            <div class="cr-bar" data-bar="energy"><div class="cr-label">ENERGY</div>
              <div class="cr-track"><b class="cr-barfill" id="cr-energyfill"></b></div><span class="cr-num" id="cr-energynum"></span></div>
            <div id="cr-bot"></div>
          </div>
          <div id="cr-bottom"><div id="cr-picked"></div>
            <div id="cr-toolbelt">${Array.from({length: TOOLBELT}, (_, i) => `<div class="cr-slot" data-hot="${i}"></div>`).join("")}</div></div>`;
        $("cr-toolbelt").addEventListener("pointerdown", e => {
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

    // h: {inv (the inventory message), hp, energy, shield, shieldMax, creative, dig (0 to 1), air, airMax, underWater,
    //     careful, bot (the Bot line), hurt, now, title, dev (the dev panel's text, or "" hidden), hidden (no player
    //     of yours: the Toolbelt and the status card hidden)}
    update(h) {
        this.ready();
        const set = (id, html, key) => {
            if (this.keys[id] === key) return;
            this.keys[id] = key;
            $(id).innerHTML = html;
        };
        const flag = (id, on) => { const el = $(id); if (el.hidden === on) el.hidden = !on; };
        const inv = h.inv, now = h.now;
        flag("cr-bottom", !h.hidden);
        if (inv && inv.inv) {
            const sel = inv.selected || 0, belt = inv.inv.slice(0, TOOLBELT);
            set("cr-toolbelt", belt.map((s, i) => `<div class="cr-slot${i === sel ? " lit" : ""}" data-hot="${i}">${slotHtml(s)}</div>`).join(""),
                JSON.stringify([belt, sel]));
            const held = inv.inv[sel], pk = JSON.stringify([sel, held ? held[0] : null]);
            if (pk !== this.picked.key) this.picked = {key: pk, text: held ? nameOf(held[0]) : "", until: now + 2000};
        }
        const picked = now < this.picked.until ? this.picked.text : "";
        set("cr-picked", esc(picked), picked);
        // the status card (craft_ui.Hud.set_life): Health with the Shield over its track, Energy, the Bot's line
        const challenge = !h.creative && !h.hidden;
        flag("cr-status", challenge);
        if (challenge) {
            const hp = clamp100(h.hp), en = clamp100(h.energy), sh = clamp100(h.shield), mx = h.shieldMax || 0;
            const key = `${hp}:${en}:${sh}:${mx}`;
            if (this.keys.life !== key) {
                this.keys.life = key;
                $("cr-hpfill").style.width = `${hp}%`;
                $("cr-hpnum").textContent = String(Math.trunc(h.hp ?? 0));
                $("cr-energyfill").style.width = `${en}%`;
                $("cr-energynum").textContent = String(Math.trunc(h.energy ?? 0));
                $("cr-shieldfill").style.width = mx ? `${sh}%` : "0";
                $("cr-shieldtext").textContent = mx ? `SHIELD ${Math.trunc(h.shield || 0)}/${mx}` : "";
            }
            set("cr-bot", esc(h.bot || ""), h.bot || "");
        }
        flag("cr-careful", !!h.careful && !h.hidden);
        const dark = $("cr-dark");
        if (dark.classList.contains("hurt") !== !!(h.hurt && challenge)) dark.classList.toggle("hurt", !!(h.hurt && challenge));
        // the crosshair's ring (set_ring): how far through digging (cyan), or the air left under water (amber)
        let want = "";
        if (h.underWater && !h.creative && h.air < h.airMax) want = `air:${Math.round(h.air / h.airMax * 32)}`;
        else if (h.dig > 0) want = `dig:${Math.round(Math.min(1, h.dig) * 32)}`;
        if (this.keys.ring !== want) {
            this.keys.ring = want;
            const fill = $("cr-fill"), k = want ? Number(want.split(":")[1]) / 32 : 0;
            fill.setAttribute("stroke-dasharray", `${(k * RING_C).toFixed(2)} ${RING_C.toFixed(2)}`);
            fill.classList.toggle("air", want.startsWith("air"));
        }
        const news = now < this.news.until ? this.news.text : "";
        set("cr-news", news ? `<span>${esc(news).replace(/\n/g, "<br>")}</span>` : "", news);
        set("cr-log", this.log.map(t => `<div>${esc(t)}</div>`).join(""), this.log.join("\n"));
        set("cr-title", esc(h.title || ""), h.title || "");
        flag("cr-dev", !!h.dev);
        if (h.dev) set("cr-dev", esc(h.dev), h.dev);
    }
}

const clamp100 = v => Math.max(0, Math.min(100, Number(v) || 0));

// what a Sandbox palette item is filed under (craft_ui.Screen.palette_kind)
function paletteKind(it) {
    if (it.tool) return "Tools";
    if (it.suit !== undefined && it.suit !== null) return "Suit";
    if (it.block === null || it.block === undefined) return "Items";
    const b = B.blocks[it.block] || {};
    if (b.use || ["server_rack", "lumen"].includes(b.key)) return "Machines";
    if (["cross", "crop"].includes(b.shape) || String(b.key).includes("leaves") || ["log", "pine_log", "pale_log"].includes(b.key)) return "Plants";
    return "Blocks";
}

// ---------- the Backpack (craft_ui.Screen) ----------
export class CraftScreen {
    // msg: the inventory message (open: what is open, or null for the Backpack; tab); send(msg): the window's
    // messages. opts: {shiftHeld(), blueprints() (the server's list: a blueprint's number is its index),
    // nearFab() (a Fabricator within 4 blocks?), botHub(kind) (GARAGE, CODE, BRAIN: the page's own panels)}
    constructor(msg, send, opts = {}) {
        this.send = send;
        this.opts = opts;
        this.shiftHeld = opts.shiftHeld || (() => false);
        this.kind = msg.open || "inventory";
        this.creative = !!msg.creative;
        this.tab = msg.tab || "backpack";
        if (this.tab === "palette" && !this.creative) this.tab = "backpack";
        this.search = "";
        this.chip = "All";
        this.page = 0;
        this.drag = null;
        this.msg = msg;
        const el = this.el = document.createElement("div");
        el.id = "craftscreen";
        el.className = "hud";
        document.body.appendChild(el);
        el.addEventListener("contextmenu", e => e.preventDefault());
        el.addEventListener("pointermove", e => this.follow(e));
        el.addEventListener("pointerdown", e => this.down(e));
        el.addEventListener("click", e => this.clicked(e));
        el.addEventListener("input", e => this.typed(e));
        el.addEventListener("change", e => { if (e.target.id === "cs-locker") this.send({type: "locker_name", name: e.target.value}); });
        el.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.tagName === "INPUT") e.target.blur(); });
        el.addEventListener("wheel", e => { if (this.tab === "blueprints" || this.tab === "palette") { e.preventDefault(); this.turn(e.deltaY > 0 ? 1 : -1); } }, {passive: false});
        this.onUp = e => this.up(e);
        window.addEventListener("pointerup", this.onUp);
        this.build();
    }

    tabs() { return this.creative ? [...TABS, ["palette", "PALETTE"]] : TABS; }

    typing() {
        const a = document.activeElement;
        return !!a && this.el.contains(a) && a.tagName === "INPUT";
    }

    // the panel drawn again for the tab shown (craft_ui.Screen.build)
    build() {
        const tabs = this.tabs().map(([k, w]) => `<button class="cr-tab${k === this.tab ? " on" : ""}" data-tab="${k}">${w}</button>`).join("");
        const what = KIND_TITLES[this.kind];
        const body = this[`build_${this.tab}`]();
        this.el.innerHTML = `<div class="cr-panel tab-${this.tab} kind-${this.kind}">
            <div class="cr-tabs">${tabs}${what ? `<span class="cr-kind">${what}</span>` : ""}<button class="cr-close" data-act="close" title="Close (Esc or I)">&#10005;</button></div>
            <div class="cr-body">${body}</div>
            <div class="cr-foot"><div class="cr-label">TOOLBELT</div>
              <div class="cr-grid belt">${Array.from({length: TOOLBELT}, (_, i) => slotDiv("inv", i)).join("")}</div>
              <div class="cr-hint">${this.tab === "palette" ? "" : "Click: pick up, put down &nbsp; Right click: split &nbsp; Shift + click: send across &nbsp; Drag and drop"}</div></div>
            <div id="cs-tip"></div></div><div id="cs-cursor" class="cr-slot cursor"></div>`;
        if (this.tab === "blueprints") this.fillBlueprints();
        if (this.tab === "palette") this.fillPalette();
        this.update(this.msg);
    }

    backpack() {
        return `<div class="cr-section backpack"><div class="cr-row"><span class="cr-label">BACKPACK</span><button class="cr-pill small" data-act="sort">SORT</button></div>
            <div class="cr-grid w6">${Array.from({length: SLOTS - TOOLBELT}, (_, i) => slotDiv("inv", i + TOOLBELT)).join("")}</div></div>`;
    }

    suitFigure() {  // (a lab-suit figure, its three slots at head, chest and feet)
        return `<div class="cr-suit"><div class="cr-figure"><i class="head"></i><i class="body"></i><i class="leg l"></i><i class="leg r"></i></div>
            ${SUIT_PARTS.map((p, i) => slotDiv("suit", i, `suit-${p}`)).join("")}<div id="cs-shield"></div></div>`;
    }

    build_backpack() {
        let top = "";
        if (this.kind === "locker") {
            top = `<div class="cr-section"><div class="cr-row"><span class="cr-label">LOCKER</span>
                <input id="cs-locker" maxlength="24" placeholder="name it (Sam's ores)" value="${esc(this.msg.name || "")}"></div>
                <div class="cr-grid w6">${Array.from({length: LOCKER}, (_, i) => slotDiv("locker", i)).join("")}</div></div>`;
        } else if (this.kind === "refinery") {
            // (the conveyor: the queue, the window glowing magenta while it works, the tray, the power gauge and slot)
            top = `<div class="cr-conveyor">
                <div class="cr-section"><span class="cr-label">QUEUE</span><div class="cr-grid w4">${Array.from({length: QUEUE}, (_, i) => slotDiv("refinery", i)).join("")}</div></div>
                <div class="cr-refining"><div id="cs-window"><b></b></div><span class="cr-label">REFINING</span></div>
                <div class="cr-section"><span class="cr-label">TRAY</span><div class="cr-grid w4">${Array.from({length: TRAY}, (_, i) => slotDiv("refinery", POWER_SLOT + 1 + i)).join("")}</div></div>
                <div class="cr-section power"><span class="cr-label">POWER</span><div class="cr-powerrow">${slotDiv("refinery", POWER_SLOT)}<div class="cr-gauge"><b id="cs-gauge"></b></div></div></div>
              </div><div class="cr-hint">Batteries, Coal, Logs or Boards power it: 6 s an item.</div>`;
            return top + this.backpack();
        }
        return `<div class="cr-backpackrow">${this.suitFigure()}<div class="cr-col">${top}${this.backpack()}</div></div>`;
    }

    searchRow(chips) {
        return `<div class="cr-row search"><input id="cs-search" placeholder="search" value="${esc(this.search)}">
            ${chips.map(c => `<button class="cr-chip${c === this.chip ? " on" : ""}" data-chip="${c}">${c}</button>`).join("")}</div>`;
    }

    build_blueprints() {
        return `${this.searchRow(["All", ...CATEGORIES])}<div id="cs-rows" class="cr-rows"></div>
            <div class="cr-pager" id="cs-pager"></div>
            <div class="cr-queue"><div id="cs-queue"></div><div class="cr-qtrack"><b id="cs-qbar"></b></div></div>`;
    }

    // the blueprints' rows (redrawn as what you hold changes, the search and the chips kept)
    fillBlueprints() {
        const rows = $("cs-rows");
        if (!rows) return;
        const bps = (this.opts.blueprints && this.opts.blueprints()) || [], m = this.msg || {}, inv = m.inv || [];
        const unlocked = new Set(m.unlocked || []), near = this.opts.nearFab ? this.opts.nearFab() : false;
        const want = this.search.trim().toLowerCase();
        const shown = bps.map((bp, i) => [i, bp]).filter(([, bp]) => (this.chip === "All" || bp.category === this.chip)
            && (!want || nameOf(B.itemId[bp.makes]).toLowerCase().includes(want)));
        shown.sort((a, b) => (unlocked.has(a[0]) ? 0 : 1) - (unlocked.has(b[0]) ? 0 : 1) || (a[1].station !== "hand") - (b[1].station !== "hand") || a[0] - b[0]);
        const pages = Math.max(1, Math.ceil(shown.length / BP_PER_PAGE));
        this.page = Math.min(this.page, pages - 1);
        rows.innerHTML = shown.slice(this.page * BP_PER_PAGE, (this.page + 1) * BP_PER_PAGE).map(([i, bp]) => {
            const ok = unlocked.has(i), id = B.itemId[bp.makes];
            const parts = Object.entries(bp.parts || {}).map(([part, n]) => {
                const got = have(inv, part), good = got >= n;
                return `<span class="${ok ? (good ? "good" : "bad") : ""}">${good ? "&#10003;" : "&#10007;"} ${esc(partName(part))} ${Math.min(got, n)}/${n}</span>`;
            }).join("");
            let act;
            if (!ok) act = `<span class="cr-note">Locked: hold one of each part</span>`;
            else if (bp.station !== "hand" && !near && !this.creative) act = `<span class="cr-need">Needs a Fabricator</span>`;
            else {
                const can = this.creative || canBuild(inv, bp);
                act = `<button class="cr-build${can ? " can" : ""}" data-build="${i}">BUILD</button>`;
            }
            return `<div class="cr-bp${ok ? "" : " locked"}" data-bp="${i}">${iconHtml(id, ok ? "" : " dim")}
                <div class="cr-bpname"><b>${esc(nameOf(id))}${bp.count > 1 ? `  x${bp.count}` : ""}</b>
                  <small>${Number(bp.seconds)} s${bp.station === "hand" ? " &nbsp; Quick Build" : ""}</small></div>
                <div class="cr-parts">${parts}</div><div class="cr-act">${act}</div></div>`;
        }).join("") || `<div class="cr-note">${bps.length ? "No blueprint matches." : "The blueprints are on their way from the server."}</div>`;
        $("cs-pager").innerHTML = pages > 1 ? `<button class="cr-pill small" data-page="-1">&lt;</button><span>${this.page + 1} / ${pages}</span><button class="cr-pill small" data-page="1">&gt;</button>` : "";
        this.bpKey = JSON.stringify([m.unlocked || [], inv, near, bps.length]);
    }

    build_bot() {
        const info = this.msg.bot || null, st = (info && info.stats) || {};
        const words = info ? `${esc(info.name || "Your Bot")}: ${info.running ? "running your brain" : info.error ? `stopped: ${esc(info.error)}`
            : "waiting (U uploads its brain, P the autopilot)"}` : "";
        const head = info ? `<div class="cr-botname">${words}</div>
              <div class="cr-note">doing: ${esc(info.doing || "waiting")} &nbsp; dug ${st.dug || 0} &nbsp; placed ${st.placed || 0} &nbsp; moves ${st.moves || 0}</div>`
            : `<div class="cr-note big">No Craft Bot yet: build a Bot dock at the Fabricator (4 Copper ingots, 3 Rubble, a Battery), put it down and right-click it.</div>`;
        const carries = this.kind === "bot" ? `<div class="cr-section"><span class="cr-label">WHAT IT CARRIES</span>
              <div class="cr-grid w9">${Array.from({length: BOT_SLOTS}, (_, i) => slotDiv("bot", i)).join("")}</div></div>`
            : `<div class="cr-note">Right-click your Bot dock to give it blocks and take what it dug.</div>`;
        return `<div class="cr-section">${head}<div class="cr-row">${[["garage", "GARAGE"], ["code", "CODE"], ["brain", "BRAIN"]]
            .map(([k, w]) => `<button class="cr-pill hub" data-hub="${k}">${w}</button>`).join("")}
            <span class="cr-note">U uploads brains/my_bot.py &nbsp; P switches the autopilot on and off</span></div></div>${carries}${this.backpack()}`;
    }

    build_palette() {
        return `${this.searchRow(PALETTE_CHIPS)}<div id="cs-palette" class="cr-grid w14"></div><div class="cr-pager" id="cs-pager"></div>
            <div class="cr-note">Click: a stack on the cursor &nbsp; Right click: one &nbsp; Put it in your Toolbelt below</div>`;
    }

    fillPalette() {
        const want = this.search.trim().toLowerCase(), chip = PALETTE_CHIPS.includes(this.chip) ? this.chip : "All";
        this.creativeItems = [...B.items.keys()].sort((a, b) => a - b).filter(i => {
            const it = B.items.get(i);
            return !NOT_IN_PALETTE.has(it.key) && (chip === "All" || paletteKind(it) === chip) && (!want || String(it.name).toLowerCase().includes(want));
        });
        const pages = Math.max(1, Math.ceil(this.creativeItems.length / PALETTE_PER_PAGE));
        this.page = Math.min(this.page, pages - 1);
        const start = this.page * PALETTE_PER_PAGE, list = this.creativeItems.slice(start, start + PALETTE_PER_PAGE);
        $("cs-palette").innerHTML = list.map((id, k) => `<div class="cr-slot" data-area="palette" data-i="${start + k}">${slotHtml([id, 1, (B.items.get(id) || {}).uses || 0])}</div>`).join("");
        $("cs-pager").innerHTML = pages > 1 ? `<button class="cr-pill small" data-page="-1">&lt;</button><span>${this.page + 1} / ${pages}</span><button class="cr-pill small" data-page="1">&gt;</button>` : "";
    }

    // ---------- what the buttons do ----------
    clicked(e) {
        const b = e.target.closest ? e.target.closest("button") : null;
        if (!b) return;
        e.preventDefault();
        if (b.dataset.tab) this.setTab(b.dataset.tab);
        else if (b.dataset.chip) { this.chip = b.dataset.chip; this.page = 0; this.refill(); this.markChips(); }
        else if (b.dataset.page) this.turn(Number(b.dataset.page));
        else if (b.dataset.build !== undefined) this.send({type: "build", bp: Number(b.dataset.build)});
        else if (b.dataset.act === "sort") this.send({type: "sort"});
        else if (b.dataset.act === "close" && this.opts.close) this.opts.close();
        else if (b.dataset.hub && this.opts.botHub) this.opts.botHub(b.dataset.hub);
    }

    markChips() { this.el.querySelectorAll("[data-chip]").forEach(c => c.classList.toggle("on", c.dataset.chip === this.chip)); }

    refill() {
        if (this.tab === "blueprints") this.fillBlueprints();
        else if (this.tab === "palette") this.fillPalette();
    }

    setTab(tab) {
        this.tab = tab;
        this.page = 0;
        this.chip = "All";
        this.search = "";
        this.send({type: "tab", tab: tab !== "palette" ? tab : "backpack"});
        this.build();
    }

    turn(step) {
        if (this.tab !== "blueprints" && this.tab !== "palette") return;
        this.page = Math.max(0, this.page + step);
        this.refill();
    }

    typed(e) {
        if (e.target.id !== "cs-search") return;
        this.search = e.target.value;
        this.page = 0;
        this.refill();
    }

    // a press on a slot: what the window's Screen.press sends (the right button: right; Shift held: shift), and
    // drag and drop from it when nothing is on the cursor
    down(e) {
        const s = e.target.closest ? e.target.closest("[data-area]") : null;
        if (!s) return;
        e.preventDefault();
        const area = s.dataset.area, i = Number(s.dataset.i), right = e.button === 2;
        if (area === "palette") {
            const id = (this.creativeItems || [])[i];
            if (id) this.send({type: "creative_take", item: id, right});
            return;
        }
        const shift = !!(e.shiftKey || this.shiftHeld());
        this.send({type: "click", area, slot: i, right, shift});
        this.drag = !right && !shift && !(this.msg && this.msg.cursor) ? [area, i] : null;
    }

    // drag and drop: let go over another slot with something on the cursor, and it goes there
    up(e) {
        const drag = this.drag;
        this.drag = null;
        if (!drag || e.button !== 0) return;
        const under = document.elementFromPoint(e.clientX, e.clientY), s = under && under.closest ? under.closest("[data-area]") : null;
        if (!s || !this.el.contains(s) || s.dataset.area === "palette") return;
        if (s.dataset.area === drag[0] && Number(s.dataset.i) === drag[1]) return;
        this.send({type: "click", area: s.dataset.area, slot: Number(s.dataset.i), right: false, shift: false});
    }

    follow(e) {
        const c = $("cs-cursor");
        if (c) { c.style.left = `${e.clientX}px`; c.style.top = `${e.clientY}px`; }
        const s = e.target.closest ? e.target.closest("[data-area], [data-bp]") : null;
        let id = null;
        if (s && s.dataset.area) id = this.itemAt(s);
        const tip = id ? nameOf(id) : "";
        const t = $("cs-tip");
        if (t && t.textContent !== tip) t.textContent = tip;
    }

    itemAt(s) {
        const area = s.dataset.area, i = Number(s.dataset.i), m = this.msg || {};
        if (area === "palette") return (this.creativeItems || [])[i] || null;
        const list = {inv: m.inv, suit: m.suit, locker: m.box, bot: m.box, refinery: m.box}[area];
        const slot = list ? list[i] : null;
        return slot ? slot[0] : null;
    }

    update(msg) {
        this.msg = msg;
        const fill = (area, list, empty = null) => this.el.querySelectorAll(`[data-area="${area}"]`).forEach(s => {
            const i = Number(s.dataset.i), slot = (list || [])[i] || null, html = slotHtml(slot, empty ? empty(i) : null);
            if (s.innerHTML !== html) s.innerHTML = html;
        });
        fill("inv", msg.inv);
        fill("suit", msg.suit, i => `slot_${SUIT_PARTS[i]}`);
        if (["locker", "bot", "refinery"].includes(this.kind)) fill(this.kind, msg.box);
        const sh = $("cs-shield");
        if (sh) sh.textContent = msg.shield_max ? `SHIELD ${msg.shield_max}` : "no suit";
        const name = $("cs-locker");
        if (name && document.activeElement !== name && name.value !== (msg.name || "")) name.value = msg.name || "";
        if (this.kind === "refinery" && $("cs-gauge")) {
            const p = msg.power || 0, mx = msg.power_max || 12;
            $("cs-gauge").style.height = `${Math.round(Math.min(1, p / Math.max(1, mx)) * 100)}%`;
            $("cs-window").classList.toggle("working", (msg.progress || 0) > 0);
        }
        if (this.tab === "blueprints" && $("cs-queue")) {
            const q = msg.building || [];
            if (q.length) {
                const job = q[0], k = 1 - job.left / Math.max(0.01, job.total);
                $("cs-queue").textContent = `Building ${nameOf(B.itemId[job.makes])}` + (q.length > 1 ? `   (+${q.length - 1} waiting)` : "");
                $("cs-qbar").style.width = `${Math.round(Math.max(0, Math.min(1, k)) * 100)}%`;
            } else {
                $("cs-queue").textContent = "";
                $("cs-qbar").style.width = "0";
            }
            const near = this.opts.nearFab ? this.opts.nearFab() : false, bps = this.opts.blueprints ? this.opts.blueprints() : [];
            if (JSON.stringify([msg.unlocked || [], msg.inv || [], near, bps.length]) !== this.bpKey) this.fillBlueprints();
        }
        if (this.tab === "bot") {  // (the Bot's words as it works)
            const key = JSON.stringify(msg.bot || null);
            if (this.botKey !== undefined && this.botKey !== key) { this.botKey = key; this.build(); return; }
            this.botKey = key;
        }
        const c = $("cs-cursor"), html = slotHtml(msg.cursor || null);
        if (c && c.innerHTML !== html) c.innerHTML = html;
    }

    // the server's blueprints changed (a mod's): the rows again
    blueprintsChanged() { if (this.tab === "blueprints") this.fillBlueprints(); }

    destroy() {
        window.removeEventListener("pointerup", this.onUp);
        this.el.remove();
    }
}

// ---------- the Esc menu (craft_ui.Menu) ----------
export class CraftMenu {
    // opts: {tier (now), tiers, resume(), chooseTier(t), quit() (the page's leave: the lobby or the desk; returns the
    // button's words now, as a second press may be asked for)}
    constructor(opts) {
        this.opts = opts;
        const el = this.el = document.createElement("div");
        el.id = "craftmenu";
        el.className = "hud";
        document.body.appendChild(el);
        el.addEventListener("click", e => this.clicked(e));
        el.addEventListener("contextmenu", e => e.preventDefault());
        this.build();
    }

    build() {
        const o = this.opts;
        this.el.innerHTML = `<div class="cr-menu"><img class="cr-logo" src="cc_logo.svg" alt="Club Coders"><div class="cr-brand">CLUB CODERS</div>
            <div class="cr-menutitle">CRAFT LAB</div>
            <button class="cr-pill wide resume" data-menu="resume">RESUME</button>
            <div class="cr-note">GRAPHICS: ${esc(o.tier)}</div>
            <div class="cr-row tiers">${(o.tiers || []).map(t => `<button class="cr-chip${t === o.tier ? " on" : ""}" data-tier="${t}">${t}</button>`).join("")}</div>
            <button class="cr-pill wide" data-menu="credits">CREDITS</button>
            <button class="cr-pill wide quit" data-menu="quit" id="cm-quit">${esc(o.quitWords || "QUIT")}</button></div>
          <div class="cr-credits" id="cm-credits" hidden><div class="cr-row"><span class="cr-menutitle small">CREDITS: what Craft Lab is made with</span>
            <button class="cr-pill small" data-menu="close">CLOSE</button></div><pre id="cm-notes">Loading THIRD_PARTY_NOTICES.md…</pre></div>`;
    }

    clicked(e) {
        const b = e.target.closest ? e.target.closest("button") : null;
        if (!b) return;
        e.preventDefault();
        const o = this.opts, what = b.dataset.menu;
        if (b.dataset.tier) {
            o.tier = b.dataset.tier;
            if (o.chooseTier) o.chooseTier(o.tier);
            this.build();
        } else if (what === "resume") o.resume();
        else if (what === "credits") this.credits();
        else if (what === "close") $("cm-credits").hidden = true;
        else if (what === "quit" && o.quit) { const words = o.quit(); if (words && $("cm-quit")) $("cm-quit").textContent = words; }
    }

    // the third-party notices (THIRD_PARTY_NOTICES.md) in a scrolling mono card
    async credits() {
        const box = $("cm-credits");
        box.hidden = false;
        if (this.notes) return;
        try {
            const r = await fetch("THIRD_PARTY_NOTICES.md", {cache: "no-cache"});
            if (!r.ok) throw new Error(String(r.status));
            this.notes = (await r.text()).split(/\r?\n/).map(l => l.replace(/\*\*/g, "").replace(/`/g, "").replace(/^#+\s*/, "")).join("\n");
        } catch (err) {
            this.notes = "THIRD_PARTY_NOTICES.md is missing.";
        }
        if ($("cm-notes")) $("cm-notes").textContent = this.notes;
    }

    destroy() { this.el.remove(); }
}
