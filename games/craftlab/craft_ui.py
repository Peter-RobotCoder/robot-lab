"""Craft Lab's screen (CHANGE 200; the lab visor since CHANGE 207): the HUD over the world and the screens you open,
in Club Coders' own look (the website's colours and fonts: navy cards, a thin light line, cyan and lime glows).

    the HUD      bottom left the status card (Health in lime with the Shield over it in cyan, Energy in amber, and
                 what your Craft Bot is doing); bottom middle the Toolbelt (8 rounded slots, the held one glowing
                 cyan, counts in pixel letters, a lime-to-coral line for the uses left); in the middle a cyan dot in
                 a thin ring (the ring fills as you dig, and under water an amber ring empties: your air); a pill of
                 news at the top, the log bottom right, the CAREFUL tag, and the dev panel top right (` key)
    the screens  I: the Backpack, three tabs: BACKPACK (the suit's three slots, the 6 x 5 Backpack, a Locker's 6 x 4
                 above it, a Refinery's conveyor), BLUEPRINTS (search and category chips; each row its parts, had
                 and needed, and BUILD), BOT (your Craft Bot: what it does, its slots, the Garage, Code and Brain);
                 Sandbox adds the PALETTE. Click to pick up and put down, right click to split, Shift and click to
                 send to the other side, drag and drop, SORT. Esc or I closes.
    the menu     Esc: the Club Coders logo, Resume, Graphics, Save, Credits (the third-party notices), Quit.

Every slot shows its item as the atlas's own tile, so the screens match the world on every tier. The screens only
ask (send): the game (offline) or the server (online) answers with the inventory as it now is.
"""
import math
import os

import numpy as np
from direct.gui.DirectGui import DGG, DirectButton, DirectEntry, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (CardMaker, LineSegs, NodePath, Point3, SamplerState, TextNode, Texture, TransparencyAttrib)

import craft_blocks as B
import craft_gfx as gfx
import craft_items as items

HERE = os.path.dirname(os.path.abspath(__file__))


def hexc(h, a=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


# the website's own colours (ClubCodersWebsite/site/assets/style.css)
BG, BG2, BG3 = hexc("#090c17"), hexc("#0f1426"), hexc("#161c33")
INK, INK2, INK3 = hexc("#f3f6ff"), hexc("#b9c2e0"), hexc("#7f8ab0")
CYAN, LIME, MAGENTA, AMBER, CORAL = hexc("#3ee9ff"), hexc("#b6ff3b"), hexc("#ff4fd8"), hexc("#ffc638"), hexc("#ff6b5b")
LINE = (1, 1, 1, 0.08)
SLOT = 0.115        # a slot's size on screen (aspect2d units)
GAP = 0.013
STEP = SLOT + GAP
NOTICES = os.path.join(HERE, "THIRD_PARTY_NOTICES.md")
LOGO = os.path.join(HERE, "logo.png")


# ---------- fonts ----------
_fonts = {}


def font(kind="body"):
    """The website's fonts: title (Space Grotesk), body (Inter), mono (JetBrains Mono), pixel (Press Start 2P)."""
    if kind not in _fonts:
        try:
            from engine import club_fonts
            _fonts[kind] = club_fonts.font(None, kind)
        except Exception:
            _fonts[kind] = None
    return _fonts[kind]


def text(parent, s, x, y, scale=0.032, fg=INK, align=TextNode.ALeft, kind="body", wrap=None):
    kw = {"font": font(kind)} if font(kind) is not None else {}
    return OnscreenText(s, pos=(x, y), scale=scale, fg=fg, align=align, parent=parent, mayChange=True, wordwrap=wrap,
                        **kw)


# ---------- rounded cards ----------
_tex = {}


def card_texture(w, h, r, fill, line=LINE, glow=None, ppu=320):
    """A rounded card as a texture, w x h aspect2d units with corners r: its fill, a 1-pixel line round it, and a
    soft glow outside it (the margin given by glow's last value) when glow is a colour."""
    key = (round(w, 3), round(h, 3), round(r, 3), fill, line, glow)
    if key in _tex:
        return _tex[key]
    margin = glow[4] if glow else 0.0
    W, H = max(4, int((w + 2 * margin) * ppu)), max(4, int((h + 2 * margin) * ppu))
    W, H = min(W, 1024), min(H, 1024)
    sx, sy = W / (w + 2 * margin), H / (h + 2 * margin)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32) + 0.5
    px, py = xx / sx - margin, yy / sy - margin  # (units, from the card's corner)
    qx = np.abs(px - w / 2) - (w / 2 - r)
    qy = np.abs(py - h / 2) - (h / 2 - r)
    d = (np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r) * sx  # (pixels)
    img = np.zeros((H, W, 4), np.float32)
    inside = np.clip(0.5 - d, 0, 1)
    img[..., :3] = fill[:3]
    img[..., 3] = inside * fill[3]
    if line:
        edge = np.clip(1.2 - np.abs(d + 0.6), 0, 1) * line[3]
        a = img[..., 3]
        img[..., :3] = img[..., :3] * (1 - edge[..., None]) + np.array(line[:3]) * edge[..., None]
        img[..., 3] = np.maximum(a, edge)
    if glow:
        g = np.where(d > 0, np.exp(-d / (margin * sx * 0.4)), 0) * glow[3]
        a = img[..., 3]
        out = a + g * (1 - a)
        img[..., :3] = np.where(out[..., None] > 0, (img[..., :3] * a[..., None] + np.array(glow[:3]) * (g * (1 - a))[..., None])
                                / np.maximum(out, 1e-6)[..., None], img[..., :3])
        img[..., 3] = out
    data = np.clip(img[::-1] * 255, 0, 255).astype(np.uint8)
    t = Texture("card")
    t.setup2dTexture(W, H, Texture.T_unsigned_byte, Texture.F_rgba8)
    t.setRamImageAs(data[..., [2, 1, 0, 3]].tobytes(), "BGRA")
    t.setMinfilter(SamplerState.FT_linear)
    t.setMagfilter(SamplerState.FT_linear)
    t.setWrapU(SamplerState.WM_clamp)
    t.setWrapV(SamplerState.WM_clamp)
    _tex[key] = t
    return t


def card(parent, x0, x1, y0, y1, r=0.03, fill=BG2, line=LINE, glow=None, pos=(0, 0)):
    """A rounded card from (x0, y0) to (x1, y1), drawn on parent."""
    m = glow[4] if glow else 0.0
    f = DirectFrame(parent=parent, frameColor=(1, 1, 1, 1), pos=(pos[0], 0, pos[1]),
                    frameSize=(x0 - m, x1 + m, y0 - m, y1 + m),
                    frameTexture=card_texture(x1 - x0, y1 - y0, r, tuple(fill), line, glow))
    f.setTransparency(TransparencyAttrib.M_alpha)
    return f


def pill_button(parent, words, x, y, command, args=(), scale=0.03, fill=BG3, fg=INK, w=None, glow=None):
    """A rounded button (the website's), words in Inter."""
    w = w or max(0.12, len(words) * scale * 0.62 + 0.06)
    h = scale * 1.7
    kw = {"text_font": font("bold")} if font("bold") is not None else {}
    b = DirectButton(parent=parent, text=words, text_scale=scale, text_fg=fg, text_pos=(0, -scale * 0.33),
                     frameColor=(1, 1, 1, 1), frameSize=(-w / 2, w / 2, -h / 2, h / 2), pos=(x, 0, y),
                     frameTexture=card_texture(w, h, h / 2, tuple(fill), (1, 1, 1, 0.16), glow), relief=DGG.FLAT,
                     command=command, extraArgs=list(args), pressEffect=True, rolloverSound=None, clickSound=None, **kw)
    b.setTransparency(TransparencyAttrib.M_alpha)
    return b


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


def picture(parent, path, x, y, w):
    """A PNG on the screen, w across (its own shape kept), or None if it isn't there."""
    if not os.path.exists(path):
        return None
    from panda3d.core import Filename, PNMImage
    img = PNMImage(Filename.fromOsSpecific(path))
    t = Texture("picture")
    t.load(img)
    h = w * img.getReadYSize() / max(1, img.getReadXSize())
    cm = CardMaker("picture")
    cm.setFrame(-w / 2, w / 2, -h / 2, h / 2)
    np_ = parent.attachNewNode(cm.generate())
    np_.setTexture(t)
    np_.setTransparency(TransparencyAttrib.M_alpha)
    np_.setPos(x, -0.01, y)
    return np_


class SlotView:
    """One slot on screen: its rounded square, its icon and its count (and a uses line for a tool or a suit piece).
    press(area, i, right) is called when it is pressed (left or right)."""

    def __init__(self, parent, x, y, area=None, i=0, press=None, size=SLOT, fill=BG3):
        self.size, self.area, self.i, self.fill = size, area, i, fill
        self.frame = DirectButton(parent=parent, frameColor=(1, 1, 1, 1), relief=DGG.FLAT, pos=(x, 0, y),
                                  frameSize=(-size / 2, size / 2, -size / 2, size / 2),
                                  frameTexture=card_texture(size, size, size * 0.16, fill),
                                  pressEffect=False, rolloverSound=None, clickSound=None)
        self.frame.setTransparency(TransparencyAttrib.M_alpha)
        if press is not None:
            self.frame.bind(DGG.B1PRESS, lambda e: press(area, i, False))
            self.frame.bind(DGG.B3PRESS, lambda e: press(area, i, True))
        self.glow = None
        self.item = None
        self.icon = None
        self.empty = None
        kw = {"font": font("pixel")} if font("pixel") is not None else {}
        self.count = OnscreenText("", pos=(size * 0.45, -size * 0.43), scale=size * 0.2, fg=INK, shadow=(0, 0, 0, 0.9),
                                  align=TextNode.ARight, parent=self.frame, mayChange=True, **kw)
        self.bar = DirectFrame(parent=self.frame, frameColor=LIME, frameSize=(0, 0, 0, 0))

    def show(self, slot):
        item_id = slot[0] if slot else None
        if item_id != self.item:
            if self.icon is not None:
                self.icon.removeNode()
            self.icon = icon(self.frame, item_id, self.size * 0.74) if item_id else None
            if self.icon is not None:
                self.icon.setY(-0.01)
                self.count.reparentTo(self.frame)
                self.bar.reparentTo(self.frame)
            self.item = item_id
        if self.empty is not None:
            self.empty.show() if item_id is None else self.empty.hide()
        n = slot[1] if slot else 0
        self.count.setText(str(n) if n > 1 else "")
        it = B.ITEMS.get(item_id) if item_id else None
        if it and (it.get("tool") or it.get("suit") is not None) and slot[2] < it["uses"]:
            k = max(0.0, slot[2] / it["uses"])
            h = self.size / 2
            self.bar["frameSize"] = (-h * 0.72, -h * 0.72 + 1.44 * h * k, -h * 0.9, -h * 0.82)
            self.bar["frameColor"] = tuple(LIME[i] * k + CORAL[i] * (1 - k) for i in range(3)) + (1,)
        else:
            self.bar["frameSize"] = (0, 0, 0, 0)

    def lit(self, on):
        """The held slot: a cyan line round it and the website's cyan glow behind it."""
        s = self.size
        if on and self.glow is None:
            m = s * 0.22
            self.glow = DirectFrame(parent=self.frame.getParent(), frameColor=(1, 1, 1, 1),
                                    frameSize=(-s / 2 - m, s / 2 + m, -s / 2 - m, s / 2 + m), pos=self.frame.getPos(),
                                    frameTexture=card_texture(s, s, s * 0.16, (0, 0, 0, 0), None, CYAN[:3] + (0.6, m)),
                                    sortOrder=-1)
            self.glow.setTransparency(TransparencyAttrib.M_alpha)
        if self.glow is not None:
            self.glow.show() if on else self.glow.hide()
        self.frame["frameTexture"] = card_texture(s, s, s * 0.16, CYAN[:3] + (0.22,) if on else self.fill,
                                                  CYAN if on else LINE)
        self.frame.setTransparency(TransparencyAttrib.M_alpha)


def ring(parent, frac, radius, colour, width=2.0, segs=48):
    """An arc round the middle of the screen from the top, clockwise, frac of the way round."""
    ls = LineSegs("ring")
    ls.setThickness(width)
    ls.setColor(*colour)
    n = max(2, int(segs * frac) + 1)
    for k in range(n):
        a = math.pi / 2 - (frac * math.tau) * k / (n - 1)
        x, y = math.cos(a) * radius, math.sin(a) * radius
        (ls.moveTo if k == 0 else ls.drawTo)(x, 0, y)
    return parent.attachNewNode(ls.create())


class Hud:
    def __init__(self, app):
        self.app = app
        a2d = app.aspect2d
        # the crosshair: a cyan dot in a thin ring (the ring fills as you dig; under water it is your air)
        self.cross = a2d.attachNewNode("crosshair")
        dot = card(self.cross, -0.006, 0.006, -0.006, 0.006, 0.006, CYAN, None)
        dot.setTransparency(TransparencyAttrib.M_alpha)
        self.cross_ring = ring(self.cross, 1.0, 0.022, (1, 1, 1, 0.35), 1.2)
        self.cross_fill = None
        self._fill = None
        # the status card (bottom left): Health with the Shield over it, Energy, the Bot
        self.status = app.a2dBottomLeft.attachNewNode("status")
        card(self.status, 0.04, 0.66, 0.04, 0.3, 0.035, BG2[:3] + (0.86,))
        self.bars = {}
        for k, (key, words, colour, y) in enumerate((("hp", "HEALTH", LIME, 0.235), ("energy", "ENERGY", AMBER, 0.16))):
            text(self.status, words, 0.075, y + 0.022, 0.022, INK3, kind="bold")
            track = DirectFrame(parent=self.status, frameColor=BG, frameSize=(0.075, 0.54, y - 0.018, y + 0.006))
            fill = DirectFrame(parent=self.status, frameColor=colour, frameSize=(0.075, 0.54, y - 0.018, y + 0.006))
            num = text(self.status, "", 0.625, y - 0.016, 0.03, INK, TextNode.ARight, "bold")
            self.bars[key] = (track, fill, num, y)
        self.shield_bar = DirectFrame(parent=self.status, frameColor=CYAN[:3] + (0.9,), frameSize=(0, 0, 0, 0))
        self.shield_text = text(self.status, "", 0.19, 0.257, 0.022, CYAN, kind="bold")
        self.bot_line = text(self.status, "", 0.075, 0.07, 0.024, INK2)
        self.careful = card(app.a2dBottomLeft, 0.04, 0.26, 0.32, 0.37, 0.025, BG3, LINE, AMBER[:3] + (0.4, 0.012))
        text(self.careful, "CAREFUL", 0.15, 0.333, 0.025, AMBER, TextNode.ACenter, "bold")
        self.careful.hide()
        # the Toolbelt (bottom middle)
        self.bottom = app.a2dBottomCenter.attachNewNode("toolbelt")
        w = items.TOOLBELT * STEP + 0.03
        card(self.bottom, -w / 2, w / 2, 0.025, 0.025 + SLOT + 0.03, (SLOT + 0.03) / 2, BG2[:3] + (0.85,))
        self.toolbelt = [SlotView(self.bottom, (i - (items.TOOLBELT - 1) / 2) * STEP, 0.04 + SLOT / 2)
                         for i in range(items.TOOLBELT)]
        self.picked = text(self.bottom, "", 0, 0.205, 0.034, INK, TextNode.ACenter, "bold")
        self.picked_until = 0.0
        # news (a pill at the top), the log (bottom right), the title, the keys, the dev panel
        self.news = app.a2dTopCenter.attachNewNode("news")  # (each pill is made in here: hiding it hides them all)
        self.news_card = None
        self.news_until = 0.0
        self.news_text = ""
        self.log = text(app.a2dBottomRight, "", -0.04, 0.92, 0.028, INK2, TextNode.ARight)
        self.log.setShadow((0, 0, 0, 0.8))
        self.log_lines = []
        self.dev_card = None
        self.title = text(app.a2dTopLeft, "", 0.04, -0.07, 0.03, INK3, kind="bold")
        self.keys = text(app.a2dBottomCenter, "", 0, 0.29, 0.026, INK3, TextNode.ACenter)
        self.dark = DirectFrame(parent=a2d, frameColor=CORAL[:3] + (0.0,), frameSize=(-3, 3, -2, 2))
        self.dark.hide()
        self.debug = self  # (the old name for the dev panel's text: setText goes to dev())

    # ---------- what the HUD shows ----------
    def set_toolbelt(self, inv, selected, now):
        key = (tuple(tuple(x) if x else None for x in inv[:items.TOOLBELT]), selected)
        if key == getattr(self, "_belt", None):
            return
        self._belt = key
        for i, v in enumerate(self.toolbelt):
            v.show(inv[i])
            v.lit(i == selected)
        if getattr(self, "_sel", None) != (selected, inv[selected][0] if inv[selected] else None):
            self._sel = (selected, inv[selected][0] if inv[selected] else None)
            self.picked.setText(B.name_of(inv[selected][0]) if inv[selected] else "")
            self.picked_until = now + 2.0

    set_hotbar = set_toolbelt

    def set_life(self, hp, energy, shield, shield_max, creative, hurt):
        key = (hp, energy, shield, shield_max, creative, hurt)
        if key == getattr(self, "_life", None):
            return
        self._life = key
        if creative:
            self.status.hide()
            self.dark.hide()
            return
        self.status.show()
        for k, v in (("hp", hp), ("energy", energy)):
            track, fill, num, y = self.bars[k]
            fill["frameSize"] = (0.075, 0.075 + 0.465 * max(0, min(100, v)) / 100, y - 0.018, y + 0.006)
            num.setText(str(int(v)))
        y = self.bars["hp"][3]
        if shield_max:  # (the Shield over the Health bar's track, from its left)
            self.shield_bar["frameSize"] = (0.075, 0.075 + 0.465 * shield / 100, y - 0.004, y + 0.006)
            self.shield_text.setText(f"SHIELD {int(shield)}/{shield_max}")
        else:
            self.shield_bar["frameSize"] = (0, 0, 0, 0)
            self.shield_text.setText("")
        if hurt:
            self.dark["frameColor"] = CORAL[:3] + (0.18,)
            self.dark.show()
        else:
            self.dark.hide()

    def set_ring(self, dig, air, air_max, under_water):
        """The crosshair's ring: how far through digging (cyan), or the air left under water (amber)."""
        if under_water and air < air_max:
            want = ("air", round(air / air_max * 32))
        elif dig > 0:
            want = ("dig", round(min(1.0, dig) * 32))
        else:
            want = None
        if want == self._fill:
            return
        self._fill = want
        if self.cross_fill is not None:
            self.cross_fill.removeNode()
            self.cross_fill = None
        if want and want[1] > 0:
            self.cross_fill = ring(self.cross, want[1] / 32, 0.022, AMBER if want[0] == "air" else CYAN, 3.0)

    def set_bot(self, words):
        self.bot_line.setText(words)

    def set_careful(self, on):
        self.careful.show() if on else self.careful.hide()

    def say(self, words, now, secs=4.0):
        self.news_until = now + secs
        if words == self.news_text and self.news_card is not None:
            return
        self.news_text = words
        if self.news_card is not None:
            self.news_card.removeNode()
            self.news_card = None
        if not words:
            return
        lines = words.split("\n")
        w = min(2.6, max(len(line) for line in lines) * 0.019 + 0.12)
        h = 0.07 + 0.045 * (len(lines) - 1)
        self.news_card = self.news.attachNewNode("pill")
        card(self.news_card, -w / 2, w / 2, -0.13 - h, -0.13, h / 2 if len(lines) == 1 else 0.03, BG2[:3] + (0.9,),
             LINE, CYAN[:3] + (0.25, 0.015))
        text(self.news_card, words, 0, -0.13 - 0.047, 0.032, INK, TextNode.ACenter, "bold")

    def add_log(self, words):
        self.log_lines = (self.log_lines + [words])[-6:]
        self.log.setText("\n".join(self.log_lines))

    def dev(self, words):
        """The dev panel (`): a mono card top right with the numbers, or None to hide it."""
        if self.dev_card is not None:
            self.dev_card.removeNode()
            self.dev_card = None
        if not words:
            return
        n = words.count("\n") + 1
        self.dev_card = self.app.a2dTopRight.attachNewNode("dev")
        card(self.dev_card, -0.86, -0.04, -0.08 - 0.036 * n - 0.03, -0.06, 0.02, BG[:3] + (0.88,))
        text(self.dev_card, words, -0.83, -0.11, 0.026, INK2, kind="mono")

    def setText(self, words):  # (self.debug.setText: the dev panel)
        self.dev(words or None)

    def tick(self, now):
        if now > self.news_until and self.news_card is not None:
            self.news_card.removeNode()
            self.news_card = None
            self.news_text = ""
        if now > self.picked_until:
            self.picked.setText("")


class Screen:
    """The Backpack (I) and what opens with it: a Locker, a Refinery, the Fabricator's blueprints, the Bot.

    msg: the inventory message (craft_game.inventory_msg). send(action): the window's act. bps: every blueprint
    (craft_items.blueprints(), or the server's list). near_fab(): is a Fabricator within 4 blocks?"""
    TABS = (("backpack", "BACKPACK"), ("blueprints", "BLUEPRINTS"), ("bot", "BOT"))

    def __init__(self, app, msg, send, bps, near_fab):
        self.app, self.send, self.bps, self.near_fab = app, send, bps, near_fab
        self.kind = msg.get("open") or "inventory"
        self.creative = bool(msg.get("creative"))
        self.tab = msg.get("tab") or "backpack"
        if self.tab == "palette" and not self.creative:
            self.tab = "backpack"
        self.root = DirectFrame(parent=app.aspect2d, frameColor=BG[:3] + (0.55,), frameSize=(-3, 3, -2, 2))
        self.panel = card(self.root, -1.05, 1.05, -0.95, 0.9, 0.06, BG2[:3] + (0.97,))
        self.fit = min(1.0, app.a2dRight / 1.08, app.a2dTop / 1.03)  # (smaller in a narrow or tall window)
        self.panel.setScale(self.fit)
        self.cursor = None
        self.cursor_view = SlotView(app.aspect2d, 0, 0)
        self.cursor_view.frame.setScale(self.fit)
        self.cursor_view.frame["frameTexture"] = None
        self.cursor_view.frame["frameColor"] = (0, 0, 0, 0)
        self.cursor_view.frame.setBin("gui-popup", 50)
        self.tip = text(self.root, "", 0, -0.99 * self.fit, 0.03, INK, TextNode.ACenter)
        self.search = None
        self.search_text = ""
        self.chip = "All"
        self.page = 0
        self.locker_entry = None
        self.drag = None
        self.msg = msg
        app.accept("mouse1-up", self.mouse_up)
        self.build()

    # ---------- drawing ----------
    def tabs(self):
        out = list(self.TABS)
        if self.creative:
            out.append(("palette", "PALETTE"))
        return out

    def build(self):
        """The panel drawn again for the tab shown (keeps the root, the cursor and the tip)."""
        if self.search is not None:
            self.search_text = self.search.get()
        self.search = self.locker_entry = None
        if getattr(self, "body", None) is not None:
            self.body.destroy()
        b = self.body = DirectFrame(parent=self.panel, frameColor=(0, 0, 0, 0))
        self.inv, self.box, self.suit, self.palette, self.rows = [], [], [], [], []
        x = -0.95
        for key, words in self.tabs():
            on = key == self.tab
            w = len(words) * 0.024 + 0.1
            pill_button(b, words, x + w / 2, 0.8, self.set_tab, (key,), 0.027, CYAN[:3] + (0.18,) if on else BG3,
                        CYAN if on else INK2, w, CYAN[:3] + (0.35, 0.012) if on else None)
            x += w + 0.02
        what = {"locker": "LOCKER", "refinery": "REFINERY", "fabricator": "FABRICATOR", "bot": "CRAFT BOT"}.get(self.kind)
        if what:
            text(b, what, 0.95, 0.785, 0.034, CYAN, TextNode.ARight, "title")
        text(b, "TOOLBELT", -0.95, -0.66, 0.022, INK3, kind="bold")
        for i in range(items.TOOLBELT):
            self.inv.append(SlotView(b, -0.95 + SLOT / 2 + i * STEP, -0.78, "inv", i, self.press))
        getattr(self, "build_" + self.tab)(b)
        self.update(self.msg)

    def grid(self, b, x0, y0, area, n, across, start=0):
        out = []
        for k in range(n):
            out.append(SlotView(b, x0 + SLOT / 2 + (k % across) * STEP, y0 - SLOT / 2 - (k // across) * STEP, area,
                                start + k, self.press))
        return out

    def backpack(self, b, x0, y0):
        text(b, "BACKPACK", x0, y0 + 0.02, 0.022, INK3, kind="bold")
        self.inv += self.grid(b, x0, y0, "inv", items.SLOTS - items.TOOLBELT, items.BACKPACK_W, items.TOOLBELT)
        pill_button(b, "SORT", x0 + items.BACKPACK_W * STEP - 0.07, y0 + 0.03, self.send, ({"type": "sort"},), 0.022)

    def build_backpack(self, b):
        if self.kind == "locker":  # (the Locker's 6 x 4 over your Backpack, with its name to type)
            text(b, "LOCKER", -0.45, 0.66, 0.022, INK3, kind="bold")
            self.locker_entry = DirectEntry(parent=b, scale=0.03, pos=(-0.25, 0, 0.655), width=14, numLines=1,
                                            initialText=self.msg.get("name") or "", frameColor=BG3,
                                            text_fg=INK, command=self.name_locker, focusOutCommand=self.name_locker_out,
                                            **({"entryFont": font("body")} if font("body") else {}))
            self.box = self.grid(b, -0.45, 0.63, "locker", items.LOCKER, 6)
            self.backpack(b, -0.45, 0.07)
        elif self.kind == "refinery":
            self.build_refinery(b)
            self.backpack(b, -0.45, 0.16)
        else:
            self.backpack(b, -0.45, 0.62)
        if self.kind not in ("refinery",):  # (the suit: a lab-suit figure, its three slots at head, chest and feet)
            fig = DirectFrame(parent=b, frameColor=(0, 0, 0, 0))
            card(fig, -0.86, -0.7, 0.45, 0.6, 0.075, BG3, LINE)        # (the head)
            card(fig, -0.9, -0.66, 0.06, 0.43, 0.05, BG3, LINE)        # (the body)
            card(fig, -0.89, -0.8, -0.24, 0.05, 0.03, BG3, LINE)       # (the legs)
            card(fig, -0.76, -0.67, -0.24, 0.05, 0.03, BG3, LINE)
            for k, (part, _) in enumerate(B.SUIT_PARTS):
                v = SlotView(b, -0.78, (0.525, 0.25, -0.2)[k], "suit", k, self.press, fill=BG2)
                u0, v0, s = gfx.uv_of(f"slot_{part}")
                cm = CardMaker("slot")
                h = SLOT * 0.36
                cm.setFrame(-h, h, -h, h)
                cm.setUvRange((u0, v0), (u0 + s, v0 + s))
                v.empty = v.frame.attachNewNode(cm.generate())
                v.empty.setTexture(gfx._state["atlas"])
                v.empty.setTransparency(TransparencyAttrib.M_alpha)
                v.empty.setY(-0.005)
                self.suit.append(v)
            self.shield_words = text(b, "", -0.78, -0.33, 0.024, CYAN, TextNode.ACenter, "bold")
        self.hint = text(b, "Click: pick up, put down   Right click: split   Shift + click: send across   Drag and "
                            "drop", 0.95, -0.66, 0.02, INK3, TextNode.ARight)

    def build_refinery(self, b):
        """The Refinery's conveyor: the queue (8) on the left, the window in the middle glowing magenta while it
        works, the tray (8) on the right, the power gauge and its slot."""
        text(b, "QUEUE", -0.95, 0.66, 0.022, INK3, kind="bold")
        self.box = self.grid(b, -0.95, 0.63, "refinery", items.QUEUE, 4)
        self.window = card(b, -0.36, 0.06, 0.37, 0.63, 0.05, BG, LINE)
        self.glow = DirectFrame(parent=b, frameColor=MAGENTA[:3] + (0.0,), frameSize=(-0.32, 0.02, 0.4, 0.6))
        text(b, "REFINING", -0.15, 0.31, 0.022, INK3, TextNode.ACenter, "bold")
        text(b, "TRAY", 0.16, 0.66, 0.022, INK3, kind="bold")
        self.box += self.grid(b, 0.16, 0.63, "refinery", items.TRAY, 4, items.POWER_SLOT + 1)
        text(b, "POWER", 0.77, 0.66, 0.022, INK3, kind="bold")
        self.gauge_track = DirectFrame(parent=b, frameColor=BG, frameSize=(0.9, 0.94, 0.38, 0.63))
        self.gauge = DirectFrame(parent=b, frameColor=AMBER, frameSize=(0.9, 0.94, 0.38, 0.38))
        power = SlotView(b, 0.8, 0.43, "refinery", items.POWER_SLOT, self.press)
        self.box.insert(items.POWER_SLOT, power)
        text(b, "Batteries, Coal, Logs or Boards power it: 6 s an item.", 0.95, 0.28, 0.02, INK3, TextNode.ARight)

    def build_blueprints(self, b):
        self.search = DirectEntry(parent=b, scale=0.03, pos=(-0.93, 0, 0.665), width=12, numLines=1,
                                  initialText=self.search_text, frameColor=BG3, text_fg=INK,
                                  **({"entryFont": font("body")} if font("body") else {}))
        text(b, "search", -0.93, 0.71, 0.02, INK3)
        x = -0.4
        for c in ("All",) + items.CATEGORIES:
            w = len(c) * 0.02 + 0.07
            on = c == self.chip
            pill_button(b, c, x + w / 2, 0.68, self.set_chip, (c,), 0.022, LIME[:3] + (0.2,) if on else BG3,
                        LIME if on else INK2, w)
            x += w + 0.015
        near = self.near_fab()
        unlocked = set(self.msg.get("unlocked") or [])
        inv = self.msg.get("inv") or []
        want = self.search_text.strip().lower()
        shown = [(i, bp) for i, bp in enumerate(self.bps)
                 if (self.chip == "All" or bp.get("category") == self.chip)
                 and (not want or want in B.name_of(B.ITEM_ID.get(bp["makes"], 0)).lower())]
        shown.sort(key=lambda ib: (ib[0] not in unlocked, ib[1]["station"] != "hand", ib[0]))
        per = 8
        pages = max(1, (len(shown) + per - 1) // per)
        self.page = min(self.page, pages - 1)
        for k, (i, bp) in enumerate(shown[self.page * per:(self.page + 1) * per]):
            y = 0.56 - k * 0.135
            ok = i in unlocked
            row = card(b, -0.95, 0.95, y - 0.12, y, 0.025, BG3 if ok else BG2, LINE)
            item_id = B.ITEM_ID[bp["makes"]]
            ic = icon(row, item_id, 0.09)
            if ic is not None:
                ic.setPos(-0.89, -0.01, y - 0.06)
                if not ok:
                    ic.setColorScale(0.4, 0.4, 0.45, 1)
            name = B.name_of(item_id) + (f"  x{bp['count']}" if bp["count"] > 1 else "")
            text(b, name, -0.82, y - 0.05, 0.03, INK if ok else INK3, kind="bold")
            text(b, f"{bp['seconds']:g} s" + ("   Quick Build" if bp["station"] == "hand" else ""), -0.82, y - 0.095,
                 0.02, INK3)
            px = -0.38
            for part, n in bp["parts"].items():
                got = items.have(inv, part)
                good = got >= n
                words = f"{'+' if good else 'x'} {items.part_name(part)} {min(got, n)}/{n}"
                text(b, words, px, y - 0.072, 0.022, (LIME if good else CORAL) if ok else INK3)
                px += len(words) * 0.0118 + 0.03
            if not ok:
                text(b, "Locked: hold one of each part", 0.92, y - 0.072, 0.022, INK3, TextNode.ARight)
            elif bp["station"] != "hand" and not near and not self.creative:
                text(b, "Needs a Fabricator", 0.92, y - 0.072, 0.022, AMBER, TextNode.ARight)
            else:
                can = self.creative or items.can_build(inv, bp)
                pill_button(b, "BUILD", 0.85, y - 0.06, self.send, ({"type": "build", "bp": i},), 0.024,
                            LIME[:3] + (0.25,) if can else BG2, LIME if can else INK3, 0.15,
                            LIME[:3] + (0.3, 0.012) if can else None)
        if pages > 1:
            pill_button(b, "<", 0.62, -0.56, self.turn, (-1,), 0.026, BG3, INK, 0.07)
            text(b, f"{self.page + 1} / {pages}", 0.74, -0.57, 0.024, INK2, TextNode.ACenter)
            pill_button(b, ">", 0.86, -0.56, self.turn, (1,), 0.026, BG3, INK, 0.07)
        self.queue_text = text(b, "", -0.95, -0.52, 0.024, INK2)
        self.queue_track = DirectFrame(parent=b, frameColor=BG, frameSize=(-0.95, -0.35, -0.6, -0.585))
        self.queue_bar = DirectFrame(parent=b, frameColor=CYAN, frameSize=(-0.95, -0.95, -0.6, -0.585))

    def build_bot(self, b):
        info = self.msg.get("bot") or {}
        if info:
            words = (f"{info.get('name', 'Your Bot')}: " + ("running your brain" if info.get("running") else
                     f"stopped: {info['error']}" if info.get("error") else "waiting (U uploads its brain, P the autopilot)"))
            st = info.get("stats") or {}
            text(b, words, -0.95, 0.64, 0.03, INK, kind="bold", wrap=40)
            text(b, f"doing: {info.get('doing', 'waiting')}    dug {st.get('dug', 0)}    placed {st.get('placed', 0)}    "
                    f"moves {st.get('moves', 0)}", -0.95, 0.56, 0.024, INK2)
        else:
            text(b, "No Craft Bot yet: build a Bot dock at the Fabricator (4 Copper ingots, 3 Rubble, a Battery), put it "
                    "down and right-click it.", -0.95, 0.64, 0.028, INK2, wrap=55)
        for k, (key, words) in enumerate((("garage", "GARAGE"), ("code", "CODE"), ("brain", "BRAIN"))):
            pill_button(b, words, -0.83 + k * 0.27, 0.46, self.app.bot_hub, (key,), 0.028, BG3, CYAN, 0.24,
                        CYAN[:3] + (0.25, 0.012))
        text(b, "U uploads brains/my_bot.py   P switches the autopilot on and off", 0.0, 0.45, 0.022, INK3)
        if self.kind == "bot":
            text(b, "WHAT IT CARRIES", -0.95, 0.36, 0.022, INK3, kind="bold")
            self.box = self.grid(b, -0.95, 0.33, "bot", 9, 9)
            self.backpack(b, -0.45, 0.1)
        else:
            text(b, "Right-click your Bot dock to give it blocks and take what it dug.", -0.95, 0.33, 0.024, INK3)
            self.backpack(b, -0.45, 0.2)

    PALETTE_CHIPS = ("All", "Blocks", "Machines", "Plants", "Items", "Tools", "Suit")

    def palette_kind(self, it):
        if it.get("tool"):
            return "Tools"
        if it.get("suit") is not None:
            return "Suit"
        if it.get("block") is None:
            return "Items"
        b = B.BLOCKS[it["block"]]
        if b["use"] or b["key"] in ("server_rack", "lumen"):
            return "Machines"
        if b["shape"] in ("cross", "crop") or "leaves" in b["key"] or b["key"] in ("log", "pine_log", "pale_log"):
            return "Plants"
        return "Blocks"

    def build_palette(self, b):
        """Sandbox: every block and item, by category, with search."""
        self.search = DirectEntry(parent=b, scale=0.03, pos=(-0.93, 0, 0.665), width=12, numLines=1,
                                  initialText=self.search_text, frameColor=BG3, text_fg=INK,
                                  **({"entryFont": font("body")} if font("body") else {}))
        text(b, "search", -0.93, 0.71, 0.02, INK3)
        x = -0.4
        for c in self.PALETTE_CHIPS:
            w = len(c) * 0.02 + 0.07
            on = c == self.chip
            pill_button(b, c, x + w / 2, 0.68, self.set_chip, (c,), 0.022, LIME[:3] + (0.2,) if on else BG3,
                        LIME if on else INK2, w)
            x += w + 0.015
        want = self.search_text.strip().lower()
        skip = ("refinery_on", "door_top", "grain", "water", "magma", "lab_floor", "glitch_rift")
        chip = self.chip if self.chip in self.PALETTE_CHIPS else "All"
        self.creative_items = [i for i in sorted(B.ITEMS) if B.ITEMS[i]["key"] not in skip
                               and (chip == "All" or self.palette_kind(B.ITEMS[i]) == chip)
                               and (not want or want in B.ITEMS[i]["name"].lower())]
        per = 14 * 4
        pages = max(1, (len(self.creative_items) + per - 1) // per)
        self.page = min(self.page, pages - 1)
        for k in range(per):
            n = self.page * per + k
            if n >= len(self.creative_items):
                break
            v = SlotView(b, -0.95 + SLOT / 2 + (k % 14) * STEP, 0.56 - (k // 14) * STEP, "palette", n, self.take)
            v.show(items.new_slot(self.creative_items[n], 1))
            self.palette.append(v)
        if pages > 1:
            pill_button(b, "<", 0.62, 0.0, self.turn, (-1,), 0.026, BG3, INK, 0.07)
            text(b, f"{self.page + 1} / {pages}", 0.74, -0.01, 0.024, INK2, TextNode.ACenter)
            pill_button(b, ">", 0.86, 0.0, self.turn, (1,), 0.026, BG3, INK, 0.07)
        text(b, "Click: a stack on the cursor   Right click: one   Put it in your Toolbelt below", -0.95, -0.02, 0.022,
             INK3)

    # ---------- what the buttons do ----------
    def set_tab(self, tab):
        self.tab = tab
        self.page = 0
        self.chip = "All"
        self.send({"type": "tab", "tab": tab if tab != "palette" else "backpack"})
        self.build()

    def set_chip(self, c):
        self.chip = c
        self.page = 0
        self.build()

    def turn(self, step):
        self.page = max(0, self.page + step)
        self.build()

    def scroll(self, step):
        if self.tab in ("blueprints", "palette"):
            self.turn(step)

    def name_locker(self, words):
        self.send({"type": "locker_name", "name": words})

    def name_locker_out(self):
        if self.locker_entry is not None:
            self.name_locker(self.locker_entry.get())

    def typing(self):
        return any(e is not None and e["focus"] for e in (self.search, self.locker_entry))

    def take(self, area, n, right=False):
        if n < len(getattr(self, "creative_items", [])):
            self.send({"type": "creative_take", "item": self.creative_items[n], "right": right})

    def press(self, area, i, right=False):
        mw = self.app.mouseWatcherNode
        shift = bool(mw and mw.is_button_down("shift"))
        self.send({"type": "click", "area": area, "slot": i, "right": right, "shift": shift})
        self.drag = (area, i) if not right and not shift and self.cursor is None else None

    def mouse_up(self):
        """Drag and drop: let go over another slot with something on the cursor, and it goes there."""
        drag, self.drag = self.drag, None
        if drag is None:
            return
        v = self.slot_under()
        if v is not None and (v.area, v.i) != drag and v.area not in (None, "palette"):
            self.send({"type": "click", "area": v.area, "slot": v.i, "right": False, "shift": False})

    def update(self, msg):
        self.msg = msg
        inv = msg.get("inv") or []
        for v in self.inv:
            v.show(inv[v.i] if v.i < len(inv) else None)
        for v, s in zip(self.suit, msg.get("suit") or []):
            v.show(s)
        if self.suit:
            mx = msg.get("shield_max", 0)
            self.shield_words.setText(f"SHIELD {mx}" if mx else "no suit")
        box = msg.get("box") or []
        for v in self.box:
            v.show(box[v.i] if v.i < len(box) else None)
        if self.kind == "refinery" and self.tab == "backpack" and hasattr(self, "gauge"):
            p, mx = msg.get("power") or 0, msg.get("power_max") or 12
            self.gauge["frameSize"] = (0.9, 0.94, 0.38, 0.38 + 0.25 * min(1.0, p / max(1, mx)))
        if self.tab == "blueprints" and hasattr(self, "queue_bar"):
            q = msg.get("building") or []
            if q:
                job = q[0]
                k = 1 - job["left"] / max(0.01, job["total"])
                self.queue_text.setText(f"Building {B.name_of(B.ITEM_ID[job['makes']])}" +
                                        (f"   (+{len(q) - 1} waiting)" if len(q) > 1 else ""))
                self.queue_bar["frameSize"] = (-0.95, -0.95 + 0.6 * max(0, min(1, k)), -0.6, -0.585)
            else:
                self.queue_text.setText("")
                self.queue_bar["frameSize"] = (-0.95, -0.95, -0.6, -0.585)
            if set(msg.get("unlocked") or []) != getattr(self, "_unlocked", None) or \
                    tuple(map(tuple, (s or (0, 0, 0) for s in inv))) != getattr(self, "_inv_key", None):
                if getattr(self, "_unlocked", None) is not None:
                    self._unlocked = set(msg.get("unlocked") or [])
                    self._inv_key = tuple(map(tuple, (s or (0, 0, 0) for s in inv)))
                    self.build()
                    return
                self._unlocked = set(msg.get("unlocked") or [])
                self._inv_key = tuple(map(tuple, (s or (0, 0, 0) for s in inv)))
        self.cursor = msg.get("cursor")
        self.cursor_view.show(self.cursor)

    def follow_mouse(self, t=0.0):
        mw = self.app.mouseWatcherNode
        if mw is not None and mw.hasMouse():
            self.cursor_view.frame.setPos(self.mouse_at(mw))
        v = self.slot_under()
        self.tip.setText(B.name_of(v.item) if v is not None and v.item else "")
        if self.search is not None and self.search.get() != self.search_text:
            self.search_text = self.search.get()
            self.page = 0
            focus = self.search["focus"]
            self.build()
            if focus and self.search is not None:
                self.search["focus"] = 1
        if self.kind == "refinery" and hasattr(self, "glow") and self.tab == "backpack":
            working = (self.msg.get("progress") or 0) > 0
            self.glow["frameColor"] = MAGENTA[:3] + ((0.35 + 0.25 * math.sin(t * 5)) if working else 0.0,)

    def slot_under(self):
        mw = self.app.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return None
        m = self.mouse_at(mw)
        half = self.fit / 2
        for v in self.inv + self.box + self.suit + self.palette:
            p = v.frame.getPos(self.app.aspect2d)
            if abs(p.x - m.x) < v.size * half and abs(p.z - m.z) < v.size * half:
                return v
        return None

    def mouse_at(self, mw):
        """The mouse in aspect2d's units (wide or tall windows alike)."""
        m = mw.getMouse()
        return self.app.aspect2d.getRelativePoint(self.app.render2d, Point3(m.x, 0, m.y))

    def hovered(self):
        v = self.slot_under()
        return v.item if v is not None else None

    def destroy(self):
        self.app.ignore("mouse1-up")
        self.cursor_view.frame.destroy()
        self.root.destroy()


class Menu:
    """Esc: the Club Coders logo, Resume, Graphics, Save, Credits and Quit. buttons: {"resume", "tiers" [(name, on)],
    "choose_tier", "save" (or None offline only), "quit"}."""

    def __init__(self, app, tier_now, tiers, resume, choose_tier, save, quit_):
        self.app = app
        self.root = DirectFrame(parent=app.aspect2d, frameColor=BG[:3] + (0.6,), frameSize=(-3, 3, -2, 2))
        self.card = card(self.root, -0.75, 0.75, -0.62, 0.66, 0.06, BG2[:3] + (0.97,), LINE, CYAN[:3] + (0.18, 0.03))
        if picture(self.card, LOGO, 0, 0.5, 0.62) is None:
            text(self.card, "CLUB CODERS", 0, 0.48, 0.07, INK, TextNode.ACenter, "title")
        text(self.card, "CRAFT LAB", 0, 0.33, 0.05, CYAN, TextNode.ACenter, "title")
        pill_button(self.card, "RESUME", 0, 0.2, resume, (), 0.036, LIME[:3] + (0.25,), LIME, 0.5, LIME[:3] + (0.3, 0.015))
        text(self.card, f"GRAPHICS: {tier_now}   (the window reopens at the one you choose)", 0, 0.08, 0.024, INK3,
             TextNode.ACenter)
        for i, t in enumerate(tiers):
            on = t == tier_now
            pill_button(self.card, t, -0.585 + i * 0.195, 0.0, choose_tier, (t,), 0.024,
                        CYAN[:3] + (0.25,) if on else BG3, CYAN if on else INK2, 0.18)
        y = -0.14
        if save is not None:
            pill_button(self.card, "SAVE MY WORLD", 0, y, save, (), 0.03, BG3, INK, 0.5)
            y -= 0.12
        pill_button(self.card, "CREDITS", 0, y, self.credits, (), 0.03, BG3, INK, 0.5)
        pill_button(self.card, "QUIT", 0, y - 0.12, quit_, (), 0.03, CORAL[:3] + (0.2,), CORAL, 0.5)
        self.notes = None

    def credits(self):
        """The third-party notices (THIRD_PARTY_NOTICES.md), a page at a time."""
        if self.notes is not None:
            self.notes.destroy()
            self.notes = None
            return
        try:
            with open(NOTICES, encoding="utf-8") as f:
                lines = [line.rstrip() for line in f.read().splitlines()]
        except OSError:
            lines = ["THIRD_PARTY_NOTICES.md is missing."]
        self.notes_lines = [line.replace("**", "").replace("`", "").lstrip("# ") for line in lines]
        self.notes_page = 0
        self.show_notes()

    def show_notes(self):
        if self.notes is not None:
            self.notes.destroy()
        per = 30
        pages = max(1, (len(self.notes_lines) + per - 1) // per)
        self.notes = card(self.root, -1.4, 1.4, -0.92, 0.9, 0.05, BG2[:3] + (0.98,), LINE)
        text(self.notes, "CREDITS: what Craft Lab is made with", -1.32, 0.8, 0.036, CYAN, kind="title")
        chunk = self.notes_lines[self.notes_page * per:(self.notes_page + 1) * per]
        text(self.notes, "\n".join(chunk), -1.32, 0.71, 0.024, INK2, kind="mono")
        pill_button(self.notes, "CLOSE", 1.2, 0.8, self.credits, (), 0.026, BG3, INK, 0.2)
        if pages > 1:
            pill_button(self.notes, "<", 0.9, -0.84, self.page, (-1,), 0.026, BG3, INK, 0.08)
            text(self.notes, f"{self.notes_page + 1} / {pages}", 1.03, -0.85, 0.024, INK2, TextNode.ACenter)
            pill_button(self.notes, ">", 1.16, -0.84, self.page, (1,), 0.026, BG3, INK, 0.08)

    def page(self, step):
        per = 30
        pages = max(1, (len(self.notes_lines) + per - 1) // per)
        self.notes_page = max(0, min(pages - 1, self.notes_page + step))
        self.show_notes()

    def destroy(self):
        self.root.destroy()
