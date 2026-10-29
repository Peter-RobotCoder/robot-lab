"""Craft Lab's screen (CHANGE 200): the HUD over the world and the screens you open.

    the HUD      the crosshair, the hotbar along the bottom (the slot you hold lit, how many of each), hearts and food
                 over it (survival), bubbles when your head is under water, the name of what you just picked, the
                 news in the middle, a log of what has happened bottom left, F3's numbers top left
    the screens  E: your inventory with the crafting grid (2 x 2) and what it makes; at a workbench 3 x 3; a chest's
                 27 slots; a smelter's three (what to smelt, the fuel, what it made) with its flame and arrow;
                 creative: every block and item to take. Click to pick up a stack, click again to put it down (right
                 click: half, or one), shift and click to send a stack across; Esc or E closes.

Every slot shows its item as the atlas's own tile, so the screens match the world on every tier. The screens only
ask (send): the game (offline) or the server (online) answers with the inventory as it now is.
"""
import math

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import CardMaker, TextNode, TransparencyAttrib

import craft_blocks as B
import craft_gfx as gfx
import craft_items as items

SLOT = 0.105           # a slot's size on screen (aspect2d units)
PANEL = (0.08, 0.09, 0.12, 0.92)
SLOT_COLOUR = (0.22, 0.24, 0.3, 0.95)
LIT = (0.95, 0.82, 0.3, 1)
WHITE, GREY, YELLOW, RED = (1, 1, 1, 1), (0.75, 0.8, 0.9, 1), (1, 0.9, 0.35, 1), (1, 0.45, 0.4, 1)


def icon(parent, item_id, size):
    """An item's icon (its tile from the atlas) as a card on parent, size across."""
    it = B.ITEMS.get(item_id)
    if it is None:
        return None
    name = it.get("icon")
    if it.get("block") is not None and B.BLOCKS[it["block"]]["tiles"]:
        tiles = B.BLOCKS[it["block"]]["tiles"]
        name = tiles[1] if B.BLOCKS[it["block"]]["shape"] == "cube" else tiles[0]
        if it["key"] == "door":
            name = "door_high"
    u0, v0, s = gfx.uv_of(name or "particle")
    cm = CardMaker("icon")
    h = size / 2
    cm.setFrame(-h, h, -h, h)
    cm.setUvRange((u0, v0), (u0 + s, v0 + s))
    np_ = parent.attachNewNode(cm.generate())
    np_.setTexture(gfx._state["atlas"])
    np_.setTransparency(TransparencyAttrib.M_alpha)
    return np_


class SlotView:
    """One slot on screen: its square, its icon and its count (and a wear bar for a tool)."""

    def __init__(self, parent, x, y, command=None, args=(), size=SLOT):
        self.size = size
        self.frame = DirectButton(parent=parent, frameColor=SLOT_COLOUR, frameSize=(-size / 2, size / 2, -size / 2, size / 2),
                                  pos=(x, 0, y), relief=DGG.FLAT, command=command, extraArgs=list(args),
                                  pressEffect=False, rolloverSound=None, clickSound=None)
        if command is not None:  # (a right click: half a stack, or one)
            self.frame.bind(DGG.B3PRESS, lambda e: command(*args, right=True))
        self.item = None
        self.icon = None
        self.count = OnscreenText("", pos=(size * 0.42, -size * 0.42), scale=size * 0.36, fg=WHITE, shadow=(0, 0, 0, 1),
                                  align=TextNode.ARight, parent=self.frame, mayChange=True)
        self.bar = DirectFrame(parent=self.frame, frameColor=(0.3, 1, 0.3, 1), frameSize=(0, 0, 0, 0))

    def show(self, slot):
        item_id = slot[0] if slot else None
        if item_id != self.item:
            if self.icon is not None:
                self.icon.removeNode()
            self.icon = icon(self.frame, item_id, self.size * 0.78) if item_id else None
            if self.icon is not None:
                self.icon.setY(-0.01)
                self.count.reparentTo(self.frame)
            self.item = item_id
        n = slot[1] if slot else 0
        self.count.setText(str(n) if n > 1 else "")
        it = B.ITEMS.get(item_id) if item_id else None
        if it and (it.get("tool") or it.get("armour") is not None) and slot[2] < it["uses"]:
            k = max(0.0, slot[2] / it["uses"])
            h = self.size / 2
            self.bar["frameSize"] = (-h * 0.8, -h * 0.8 + 1.6 * h * k, -h * 0.85, -h * 0.75)
            self.bar["frameColor"] = (1 - k, k, 0.2, 1)
        else:
            self.bar["frameSize"] = (0, 0, 0, 0)

    def lit(self, on):
        self.frame["frameColor"] = LIT if on else SLOT_COLOUR


class Hud:
    def __init__(self, app):
        self.app = app
        a2d = app.aspect2d
        self.cross = OnscreenText("+", pos=(0, -0.02), scale=0.07, fg=(1, 1, 1, 0.85), shadow=(0, 0, 0, 0.6), parent=a2d)
        self.bottom = app.a2dBottomCenter.attachNewNode("hotbar")
        self.hotbar = [SlotView(self.bottom, (i - 4) * (SLOT + 0.01), 0.08) for i in range(items.HOTBAR)]
        self.hearts = [DirectFrame(parent=self.bottom, frameColor=(0.85, 0.12, 0.15, 1),
                                   frameSize=(-0.018, 0.018, -0.018, 0.018), pos=(-0.47 + i * 0.045, 0, 0.17))
                       for i in range(10)]
        self.food = [DirectFrame(parent=self.bottom, frameColor=(0.75, 0.48, 0.2, 1), frameSize=(-0.018, 0.018, -0.018, 0.018),
                                 pos=(0.47 - i * 0.045, 0, 0.17)) for i in range(10)]
        self.armour = [DirectFrame(parent=self.bottom, frameColor=(0.75, 0.8, 0.9, 1), frameSize=(-0.016, 0.016, -0.016, 0.016),
                                   pos=(-0.47 + i * 0.045, 0, 0.215)) for i in range(10)]
        for a in self.armour:
            a.hide()
        self.bubbles = [DirectFrame(parent=self.bottom, frameColor=(0.55, 0.8, 1, 1), frameSize=(-0.014, 0.014, -0.014, 0.014),
                                    pos=(0.47 - i * 0.045, 0, 0.215)) for i in range(10)]
        self.picked = OnscreenText("", pos=(0, 0.26), scale=0.045, fg=WHITE, shadow=(0, 0, 0, 1), parent=self.bottom,
                                   mayChange=True)
        self.picked_until = 0.0
        self.news = OnscreenText("", pos=(0, 0.55), scale=0.06, fg=YELLOW, shadow=(0, 0, 0, 1), parent=a2d, mayChange=True)
        self.news_until = 0.0
        self.log = OnscreenText("", pos=(0.04, 0.5), scale=0.036, fg=WHITE, shadow=(0, 0, 0, 1), align=TextNode.ALeft,
                                parent=app.a2dBottomLeft, mayChange=True)
        self.log_lines = []
        self.debug = OnscreenText("", pos=(0.04, -0.07), scale=0.035, fg=WHITE, shadow=(0, 0, 0, 1), align=TextNode.ALeft,
                                  parent=app.a2dTopLeft, mayChange=True)
        self.title = OnscreenText("", pos=(-0.04, -0.07), scale=0.04, fg=YELLOW, shadow=(0, 0, 0, 1), align=TextNode.ARight,
                                  parent=app.a2dTopRight, mayChange=True)
        self.keys = OnscreenText("", pos=(0, 0.3), scale=0.032, fg=GREY, shadow=(0, 0, 0, 1), parent=app.a2dBottomCenter,
                                 mayChange=True)
        self.dark = DirectFrame(parent=a2d, frameColor=(0.5, 0, 0, 0.0), frameSize=(-3, 3, -2, 2))
        self.dark.hide()

    def set_hotbar(self, inv, selected, now):
        key = (tuple(tuple(x) if x else None for x in inv[:items.HOTBAR]), selected)
        if key == getattr(self, "_bar", None):
            return
        self._bar = key
        for i, v in enumerate(self.hotbar):
            v.show(inv[i])
            v.lit(i == selected)
        if getattr(self, "_sel", None) != (selected, inv[selected][0] if inv[selected] else None):
            self._sel = (selected, inv[selected][0] if inv[selected] else None)
            self.picked.setText(B.name_of(inv[selected][0]) if inv[selected] else "")
            self.picked_until = now + 2.0

    def set_life(self, hp, food, breath, creative, under_water, hurt):
        key = (hp, food, int(breath + 0.99) if under_water else -1, creative, hurt)
        if key == getattr(self, "_life", None):  # (nothing changed: the frames left alone)
            return
        self._life = key
        for i, h in enumerate(self.hearts):
            on = hp >= (i + 1) * 2
            half = hp == i * 2 + 1
            h["frameColor"] = (0.85, 0.12, 0.15, 1) if on else (0.85, 0.4, 0.4, 1) if half else (0.15, 0.08, 0.08, 0.8)
            h.show() if not creative else h.hide()
        for i, f in enumerate(self.food):
            on = food >= (i + 1) * 2
            half = food == i * 2 + 1
            f["frameColor"] = (0.75, 0.48, 0.2, 1) if on else (0.6, 0.45, 0.3, 1) if half else (0.12, 0.09, 0.06, 0.8)
            f.show() if not creative else f.hide()
        for i, b in enumerate(self.bubbles):
            b.show() if (under_water and not creative and breath > i) else b.hide()
        if hurt:
            self.dark["frameColor"] = (0.6, 0, 0, 0.22)
            self.dark.show()
        else:
            self.dark.hide()

    def set_armour(self, points, creative):
        """The armour row over the hearts: a pip for each two points worn (none shown when nothing is worn)."""
        key = (points, creative)
        if key == getattr(self, "_armour", None):
            return
        self._armour = key
        for i, a in enumerate(self.armour):
            if creative or not points:
                a.hide()
                continue
            on = points >= (i + 1) * 2
            half = points == i * 2 + 1
            a["frameColor"] = (0.78, 0.84, 0.95, 1) if on else (0.55, 0.6, 0.7, 1) if half else (0.14, 0.16, 0.2, 0.8)
            a.show()

    def say(self, text, now, secs=4.0):
        self.news.setText(text)
        self.news_until = now + secs

    def add_log(self, text):
        self.log_lines = (self.log_lines + [text])[-6:]
        self.log.setText("\n".join(self.log_lines))

    def tick(self, now):
        if now > self.news_until:
            self.news.setText("")
        if now > self.picked_until:
            self.picked.setText("")


class Screen:
    """An open screen: the inventory (and the crafting grid), a workbench, a chest, a smelter, the creative box."""

    def __init__(self, app, msg, send):
        self.app, self.send = app, send
        self.root = DirectFrame(parent=app.aspect2d, frameColor=(0, 0, 0, 0.45), frameSize=(-3, 3, -2, 2))
        kind = msg.get("open") or "inventory"
        creative = msg.get("creative")
        self.kind = kind
        w = 9 * (SLOT + 0.01)
        top_h = 0.42 if kind != "chest" else 0.36
        self.panel = DirectFrame(parent=self.root, frameColor=PANEL,
                                 frameSize=(-w / 2 - 0.05, w / 2 + 0.05, -0.62, 0.3 + top_h + (0.55 if creative and kind == "inventory" else 0)))
        title = {"inventory": "INVENTORY", "workbench": "WORKBENCH", "chest": "CHEST", "smelter": "SMELTER",
                 "bot": "CRAFT BOT: what it carries"}.get(kind, kind.upper())
        OnscreenText(title, pos=(-w / 2, 0.3 + top_h - 0.07), scale=0.045, fg=YELLOW, align=TextNode.ALeft, parent=self.panel)
        self.inv = []
        for i in range(items.SLOTS):
            row = 3 if i < items.HOTBAR else (i - items.HOTBAR) // 9
            col = i % 9 if i < items.HOTBAR else (i - items.HOTBAR) % 9
            y = -0.55 if i < items.HOTBAR else -0.42 + (2 - row) * (SLOT + 0.01)
            self.inv.append(SlotView(self.panel, -w / 2 + SLOT / 2 + col * (SLOT + 0.01), y, self.click, ("inv", i)))
        self.grid, self.result, self.box, self.armour = [], None, [], []
        gy = 0.3
        if kind in ("inventory", "workbench"):
            n = msg.get("grid_w", 2)
            for i in range(n * n):
                self.grid.append(SlotView(self.panel, -0.3 + (i % n) * (SLOT + 0.01),
                                          gy + 0.17 - (i // n) * (SLOT + 0.01) + (0.0 if n == 3 else -0.05), self.click, ("grid", i)))
            OnscreenText("->", pos=(0.07, gy + 0.02), scale=0.06, fg=WHITE, parent=self.panel)
            self.result = SlotView(self.panel, 0.22, gy + 0.04, self.click, ("result", 0), size=SLOT * 1.2)
            OnscreenText("Put things in the grid: what they make shows on the right." if n == 2 else
                         "A workbench: 3 x 3 makes tools, armour, chests, doors, beds...",
                         pos=(0.06 if n == 2 else 0, gy - 0.12), scale=0.03, fg=GREY, parent=self.panel)
            if kind == "inventory":  # (what you wear, down the left: head, chest, legs, feet)
                for k, (part, _) in enumerate(B.ARMOUR_PARTS):
                    v = SlotView(self.panel, -w / 2 + SLOT / 2, 0.56 - k * (SLOT + 0.01), self.click, ("armour", k))
                    v.empty = self.slot_picture(v, part)
                    self.armour.append(v)
                self.points = OnscreenText("", pos=(-w / 2, 0.1), scale=0.03, fg=GREY, align=TextNode.ALeft,
                                           parent=self.panel, mayChange=True)
        elif kind == "chest":
            for i in range(items.CHEST):
                self.box.append(SlotView(self.panel, -w / 2 + SLOT / 2 + (i % 9) * (SLOT + 0.01),
                                         0.45 - (i // 9) * (SLOT + 0.01), self.click, ("chest", i)))
        elif kind == "bot":
            for i in range(9):
                self.box.append(SlotView(self.panel, -w / 2 + SLOT / 2 + i * (SLOT + 0.01), 0.45, self.click, ("bot", i)))
            info = msg.get("bot") or {}
            words = (f"{info.get('name', 'Your Bot')}: " + ("running your brain" if info.get("running") else
                     f"stopped: {info['error']}" if info.get("error") else "waiting (U uploads its brain, P the autopilot)"))
            st = info.get("stats") or {}
            OnscreenText(words, pos=(0, 0.3), scale=0.032, fg=WHITE, parent=self.panel, wordwrap=34)
            OnscreenText(f"dug {st.get('dug', 0)}   placed {st.get('placed', 0)}   moves {st.get('moves', 0)}",
                         pos=(0, 0.2), scale=0.03, fg=GREY, parent=self.panel)
            OnscreenText("Give it blocks to build with (shift and click sends a stack); take what it dug.", pos=(0, 0.13),
                         scale=0.028, fg=GREY, parent=self.panel)
        elif kind == "smelter":
            self.box = [SlotView(self.panel, -0.2, 0.52, self.click, ("smelter", 0)),
                        SlotView(self.panel, -0.2, 0.26, self.click, ("smelter", 1)),
                        SlotView(self.panel, 0.25, 0.39, self.click, ("smelter", 2), size=SLOT * 1.2)]
            self.flame = DirectFrame(parent=self.panel, frameColor=(1, 0.55, 0.15, 1), frameSize=(0, 0, 0, 0), pos=(-0.2, 0, 0.39))
            self.arrow = DirectFrame(parent=self.panel, frameColor=(1, 1, 1, 1), frameSize=(0, 0, 0, 0), pos=(-0.08, 0, 0.39))
            OnscreenText("top: what to smelt   bottom: fuel (coal, wood)", pos=(0, 0.12), scale=0.03, fg=GREY, parent=self.panel)
        self.palette = []
        if creative and kind == "inventory":
            self.page = 0
            self.page_text = OnscreenText("", pos=(w / 2 - 0.05, 0.3 + top_h + 0.47), scale=0.032, fg=GREY,
                                          align=TextNode.ARight, parent=self.panel, mayChange=True)
            DirectButton(parent=self.panel, text="next page", scale=0.035, pos=(w / 2 - 0.15, 0, 0.3 + top_h + 0.4),
                         command=self.next_page, relief=DGG.FLAT, frameColor=(0.2, 0.3, 0.45, 1), text_fg=WHITE)
            for i in range(36):
                self.palette.append(SlotView(self.panel, -w / 2 + SLOT / 2 + (i % 9) * (SLOT + 0.01),
                                             0.3 + top_h + 0.38 - (i // 9) * (SLOT + 0.01) - 0.05, self.take, (i,)))
            self.creative_items = [i for i in sorted(B.ITEMS) if B.ITEMS[i]["key"] not in
                                   ("smelter_lit", "door_top", "wheat", "water", "magma", "corestone")]
            self.show_page()
        self.cursor = None
        self.cursor_view = SlotView(app.aspect2d, 0, 0)
        self.cursor_view.frame["frameColor"] = (0, 0, 0, 0)
        self.cursor_view.frame.setBin("gui-popup", 50)
        self.tip = OnscreenText("", pos=(0, -0.7), scale=0.035, fg=WHITE, parent=self.root, mayChange=True)
        self.update(msg)

    def slot_picture(self, v, part):
        """An empty armour slot shows a faint picture of what goes there."""
        u0, v0, s = gfx.uv_of(f"slot_{part}")
        cm = CardMaker("slot")
        h = v.size * 0.39
        cm.setFrame(-h, h, -h, h)
        cm.setUvRange((u0, v0), (u0 + s, v0 + s))
        np_ = v.frame.attachNewNode(cm.generate())
        np_.setTexture(gfx._state["atlas"])
        np_.setTransparency(TransparencyAttrib.M_alpha)
        np_.setY(-0.005)
        return np_

    def show_page(self):
        start = self.page * 36
        for i, v in enumerate(self.palette):
            k = start + i
            v.show(items.new_slot(self.creative_items[k], 1) if k < len(self.creative_items) else None)
        pages = (len(self.creative_items) + 35) // 36
        self.page_text.setText(f"CREATIVE: everything (page {self.page + 1} of {pages})")

    def next_page(self):
        pages = (len(self.creative_items) + 35) // 36
        self.page = (self.page + 1) % pages
        self.show_page()

    def take(self, i, right=False):
        k = self.page * 36 + i
        if k < len(self.creative_items):
            self.send({"type": "creative_take", "item": self.creative_items[k], "right": right})

    def click(self, area, i, right=False):
        shift = self.app.mouseWatcherNode.is_button_down("shift") if self.app.mouseWatcherNode else False
        self.send({"type": "click", "area": area, "slot": i, "right": right, "shift": bool(shift)})

    def update(self, msg):
        for v, s in zip(self.inv, msg.get("inv") or []):
            v.show(s)
        for v, s in zip(self.grid, msg.get("grid") or []):
            v.show(s)
        for v, s in zip(self.armour, msg.get("armour") or []):
            v.show(s)
            v.empty.show() if s is None else v.empty.hide()
        if self.armour:
            pts = msg.get("armour_points", 0)
            self.points.setText(f"armour {pts} of 20: keeps off {min(80, pts * 4)}% of a hit" if pts else "")
        if self.result is not None:
            r = msg.get("result")
            self.result.show([r[0], r[1], 0] if r else None)
        if self.box:
            for v, s in zip(self.box, msg.get("box") or []):
                v.show(s)
        if self.kind == "smelter":
            b, p = msg.get("burn") or 0, msg.get("progress") or 0
            self.flame["frameSize"] = (-0.02, 0.02, -0.06, -0.06 + 0.12 * b)
            self.arrow["frameSize"] = (0, 0.22 * p, -0.012, 0.012)
        self.cursor = msg.get("cursor")
        self.cursor_view.show(self.cursor)

    def follow_mouse(self):
        mw = self.app.mouseWatcherNode
        if mw is not None and mw.hasMouse():
            m = mw.getMouse()
            ratio = self.app.getAspectRatio()
            self.cursor_view.frame.setPos(m.x * ratio, 0, m.y)
        hover = self.hovered()
        self.tip.setText(B.name_of(hover) if hover else "")

    def hovered(self):
        mw = self.app.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return None
        m = mw.getMouse()
        ratio = self.app.getAspectRatio()
        x, y = m.x * ratio, m.y
        for v in self.inv + self.grid + self.box + self.armour + self.palette + ([self.result] if self.result else []):
            p = v.frame.getPos(self.app.aspect2d)
            if abs(p.x - x) < v.size / 2 and abs(p.z - y) < v.size / 2 and v.item:
                return v.item
        return None

    def destroy(self):
        self.cursor_view.frame.destroy()
        self.root.destroy()


def heart_count(hp):
    return math.ceil(hp / 2)
