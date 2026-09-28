"""The fighting-game screen: two health bars, round wins, the round timer, energy meters, the big banners
(ROUND 1, FIGHT!, K.O.!), the combo counter and, in practice, the training readout.

Used by the class windows (fight_client.py) and the showcase (beat_em_up.py). Give update() one ring from the
server's state every frame; it draws the two fighters in that ring.
"""
from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

WHITE, GREY, YELLOW, RED = (1, 1, 1, 1), (0.75, 0.8, 0.9, 1), (1, 0.85, 0.2, 1), (1, 0.3, 0.25, 1)
BLUE, GREEN, ORANGE = (0.55, 0.85, 1, 1), (0.45, 0.95, 0.5, 1), (1, 0.6, 0.2, 1)
BAR_W, BAR_H = 0.86, 0.05
SPECIAL_COST = 50


def text(parent, s, x, y, scale, fg=WHITE, align=TextNode.ACenter):
    return OnscreenText(s, pos=(x, y), scale=scale, fg=fg, align=align, parent=parent, mayChange=True,
                        shadow=(0, 0, 0, 0.9))


class Side:
    """One fighter's half of the screen: name, health bar (with a white trail showing recent damage), round wins
    and energy meter. side = -1 (left) or 1 (right)."""

    def __init__(self, root, side):
        self.side = side
        self.root = root.attachNewNode(f"side{side}")
        a = TextNode.ALeft if side < 0 else TextNode.ARight
        self.name = text(self.root, "", 0, 0.915, 0.05, WHITE, a)
        self.owner = text(self.root, "", 0, 0.795, 0.03, GREY, a)
        self.frame = DirectFrame(parent=self.root, frameColor=(0.08, 0.08, 0.1, 0.9),
                                 frameSize=(-0.008, BAR_W + 0.008, -0.008, BAR_H + 0.008))
        self.trail = DirectFrame(parent=self.frame, frameColor=(1, 1, 1, 0.9), frameSize=(0, BAR_W, 0, BAR_H))
        self.fill = DirectFrame(parent=self.frame, frameColor=YELLOW, frameSize=(0, BAR_W, 0, BAR_H))
        self.pips = [DirectFrame(parent=self.root, frameColor=(0.2, 0.2, 0.25, 1), frameSize=(-0.018, 0.018, -0.018, 0.018))
                     for _ in range(3)]
        self.energy_back = DirectFrame(parent=self.root, frameColor=(0.08, 0.08, 0.1, 0.9),
                                       frameSize=(-0.006, 0.5 + 0.006, -0.006, 0.026))
        self.energy = DirectFrame(parent=self.energy_back, frameColor=BLUE, frameSize=(0, 0.5, 0, 0.02))
        self.energy_text = text(self.root, "", 0, -0.955, 0.03, BLUE, a)
        self.shown = 1.0  # the white trail catches up with the health a moment after a hit
        self.trail_at = 1.0

    def place(self, cx):
        """Line everything up either side of cx (the middle of the screen, or of the space beside a panel)."""
        s = self.side
        x0 = cx - 0.1 - BAR_W if s < 0 else cx + 0.1
        self.frame.setPos(x0, 0, 0.85)
        outer = x0 if s < 0 else x0 + BAR_W
        self.name.setPos(outer, 0.915)
        self.owner.setPos(outer, 0.795)
        for i, p in enumerate(self.pips):
            p.setPos(cx - 0.14 - i * 0.05 if s < 0 else cx + 0.14 + i * 0.05, 0, 0.8)
        self.energy_back.setPos(outer if s < 0 else outer - 0.5, 0, -0.86)
        self.energy_text.setPos(outer, -0.905)

    def update(self, f, info, rounds_to_win, dt):
        if f is None:
            self.root.hide()
            return
        self.root.show()
        name, owner, you = info
        self.name.setText(name + ("  (YOU)" if you else ""))
        self.name.setFg(YELLOW if you else WHITE)
        self.owner.setText(owner + ("   AUTOPILOT" if f.get("ap") else ""))
        share = max(0.0, min(1.0, f["hp"] / max(1.0, f["max"])))
        if share < self.shown:
            self.trail_at = max(self.trail_at, self.shown)
        self.shown = share
        self.trail_at = max(share, self.trail_at - dt * 0.35)
        colour = (0.3, 0.9, 0.35, 1) if share > 0.5 else YELLOW if share > 0.25 else RED
        for bar, amount in ((self.fill, share), (self.trail, self.trail_at)):
            w = BAR_W * amount
            # the bar shrinks towards the outside edge, like the classic arcade games
            bar["frameSize"] = (BAR_W - w, BAR_W, 0, BAR_H) if self.side < 0 else (0, w, 0, BAR_H)
        self.fill["frameColor"] = colour
        for i, p in enumerate(self.pips):
            p.show() if i < rounds_to_win else p.hide()
            p["frameColor"] = YELLOW if i < f["w"] else (0.2, 0.2, 0.25, 1)
        e = max(0.0, min(100.0, f["en"])) / 100
        self.energy["frameSize"] = (0, 0.5 * e, 0, 0.02) if self.side > 0 else (0.5 * (1 - e), 0.5, 0, 0.02)
        ready = f["en"] >= SPECIAL_COST
        self.energy["frameColor"] = (1, 0.8, 0.2, 1) if ready else BLUE
        self.energy_text.setText("SPECIAL READY" if ready else "ENERGY")
        self.energy_text.setFg(YELLOW if ready else BLUE)


class FightHUD:
    def __init__(self, parent):
        self.root = parent.attachNewNode("fight hud")
        self.sides = [Side(self.root, -1), Side(self.root, 1)]
        self.timer_back = DirectFrame(parent=self.root, frameColor=(0.05, 0.05, 0.07, 0.85),
                                      frameSize=(-0.085, 0.085, -0.06, 0.06))
        self.timer = text(self.root, "", 0, 0.85, 0.075, WHITE)
        self.label = text(self.root, "", 0, 0.945, 0.032, YELLOW)
        self.banner = OnscreenText("", pos=(0, 0.2), scale=0.16, fg=YELLOW, shadow=(0.3, 0.05, 0, 1), mayChange=True,
                                   parent=self.root)
        self.sub_banner = text(self.root, "", 0, 0.07, 0.05, WHITE)
        self.combo = [text(self.root, "", 0, 0.45, 0.075, ORANGE, a) for a in (TextNode.ALeft, TextNode.ARight)]
        self.combo_until = [0.0, 0.0]
        self.training = text(self.root, "", 0, -0.77, 0.032, GREEN)
        self.cx = None
        self.place(0.0)

    def place(self, cx):
        if cx == self.cx:
            return
        self.cx = cx
        for s in self.sides:
            s.place(cx)
        self.timer_back.setPos(cx, 0, 0.87)
        self.timer.setPos(cx, 0.845)
        self.label.setPos(cx, 0.945)
        self.banner.setPos(cx, 0.2)
        self.sub_banner.setPos(cx, 0.07)
        self.combo[0].setPos(cx - 1.25, 0.45)
        self.combo[1].setPos(cx + 1.25, 0.45)
        self.training.setPos(cx, -0.77)

    def show(self, on=True):
        self.root.show() if on else self.root.hide()

    def update(self, ring, names, my_id, now, dt, rounds_to_win=2, ring_name=""):
        """ring: one ring from the server state. names: fighter id -> (name, owner). my_id: your fighter's id."""
        if ring is None:
            self.show(False)
            return
        self.show(True)
        fs = ring["f"]
        order = sorted(fs, key=lambda f: 0 if f["id"] == my_id else 1) if len(fs) == 2 and \
            any(f["id"] == my_id for f in fs) else fs  # you are always on the left
        for i, side in enumerate(self.sides):
            f = order[i] if i < len(order) else None
            nm, owner = names.get(f["id"], ("?", "")) if f else ("", "")
            side.update(f, (nm, owner, f is not None and f["id"] == my_id), rounds_to_win, dt)
        tl = ring.get("tl")
        self.timer.setText("" if tl is None else f"{max(0, int(tl + 0.99))}")
        self.timer.setFg(RED if tl is not None and tl < 10 else WHITE)
        self.timer_back.show() if tl is not None else self.timer_back.hide()
        label = ring.get("lb") or ""
        self.label.setText(" - ".join(x for x in (ring_name, label) if x))
        # the big banner: ROUND 1, FIGHT!, K.O.!, PERFECT!, ... WINS!
        bn = ring.get("bn") or ""
        self.banner.setText(bn)
        big = bn in ("K.O.!", "PERFECT!", "FIGHT!")
        self.banner.setScale(0.2 if big else 0.13 if len(bn) > 10 else 0.16)
        self.banner.setFg(RED if bn in ("K.O.!", "RING OUT!") else YELLOW)
        self.sub_banner.setText(f"ROUND {ring['rd']}" if ring.get("ph") == "ko" and bn not in ("",) and
                                "WINS" not in bn else "")
        # the combo counter, on the attacker's side: "3 HITS!"
        lh = ring.get("lh")
        if lh and not lh.get("blocked") and lh.get("combo", 0) >= 2 and now - lh.get("t", -9) < 0.05 + dt + 0.1:
            side = next((i for i, f in enumerate(order) if f["id"] == lh["by"]), None)
            if side is not None:
                self.combo[side].setText(f"{lh['combo']} HITS!" + ("\nCOUNTER" if lh.get("counter") else ""))
                self.combo_until[side] = now + 1.3
        for i, c in enumerate(self.combo):
            if now > self.combo_until[i]:
                c.setText("")
        # training mode: what the last hit did
        if ring.get("tl") is None and lh:
            who = next((names.get(f["id"], ("?",))[0] for f in fs if f["id"] == lh["by"]), "?")
            what = "BLOCKED" if lh.get("blocked") else f"combo {lh['combo']}" if lh.get("combo", 0) > 1 else "hit"
            self.training.setText(f"TRAINING   {who}: {lh['move'].replace('_', ' ').upper()} ({lh['height']})   "
                                  f"{lh['dmg']:.1f} damage   {what}" + ("   COUNTER HIT" if lh.get("counter") else ""))
        elif ring.get("tl") is None:
            self.training.setText("TRAINING   practice: nobody loses health")
        else:
            self.training.setText("")

    def destroy(self):
        self.root.removeNode()
