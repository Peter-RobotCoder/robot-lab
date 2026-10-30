"""An experience drawn over any Club Coders game's window (CHANGE 210; the experience itself: engine/experience.py).

Over the game, never instead of it: the objective and how far you've got (top centre, under the game's own banner),
the XP bar and your rank, the coach's words (bottom centre, typed out), "+10 XP" and RANK UP as they happen, and the
result card at the end (START AGAIN). The game's own panels stay what they are: the Mission tab lists the
experience's objectives, the garage, the code panel and the brains are the game's.

The teacher's window gets the class's view instead: who is on which objective, their XP and rank, and who has
finished; its Controls tab starts and ends it (controls_row).

A game's window makes one ExperienceHud(self, send, teacher) once it is logged in, passes it the server's
"experience" and "experience_class" messages (took), and may move it out of the way of its own HUD (top, bottom).
"""
import time

from direct.gui.DirectGui import DGG, DirectFrame
from panda3d.core import TextNode

from engine import hud

C = hud.DARK  # (always the dark look: it is drawn over the game, as the games' own HUDs are)
KIND = {"good": C["GREEN"], "rank": C["YELLOW"], "grey": C["GREY"]}
BACK = (0.03, 0.04, 0.07, 0.86)
TYPE_RATE = 70  # the coach's letters a second
TOAST_SECS = 3.0


class ExperienceHud:
    def __init__(self, base, send, teacher=False, top=-0.235, bottom=0.2):
        self.base, self.send, self.teacher = base, send, teacher
        self.top, self.bottom = top, bottom
        self.m = None
        self.shown = True
        self.closed_card = None   # the result card closed (its run's start time): not shown again for that run
        self.say_seq, self.say_text, self.say_at = -1, "", 0.0
        self.toast_seen, self.toasts = 0, []
        self.root = base.aspect2d.attachNewNode("experience")
        self.top_node = base.a2dTopCenter.attachNewNode("experience top")
        self.bottom_node = base.a2dBottomCenter.attachNewNode("experience bottom")
        self.parts = []
        self.typed = self.toast_rows = None
        base.taskMgr.add(self.every_frame, "experience hud")

    # ---------- the server's messages ----------
    def took(self, m):
        kind = m.get("type")
        if kind == "experience" and not self.teacher:
            if not m.get("on"):
                if self.m is not None:
                    self.m = None
                    self.redraw()
                return
            old, self.m = self.m, m
            say = m.get("say") or [0, ""]
            if say[0] != self.say_seq:
                self.say_seq, self.say_text, self.say_at = say[0], say[1], time.perf_counter()
            for seq, words, kind_ in m.get("toasts", []):
                if seq > self.toast_seen:
                    self.toast_seen = seq
                    self.toasts = (self.toasts + [(words, KIND.get(kind_, C["WHITE"]), time.perf_counter())])[-3:]
            if old is None or self.drawn_sig(old) != self.drawn_sig(m):
                self.redraw()
            else:
                self.refresh()
        elif kind == "experience_class" and self.teacher:
            old, self.m = self.m, (m if m.get("on") else None)
            self.available = m.get("available", [])
            if (old is None) != (self.m is None) or (self.m and old and old != self.m):
                self.redraw()

    @staticmethod
    def drawn_sig(m):
        """What needs the parts drawn again (the rest is set in place by refresh)."""
        return (m.get("index"), m.get("actions"), bool(m.get("result")), m.get("n"), m.get("result"),
                [o["state"] for o in m.get("objectives", [])])

    @property
    def on(self):
        return self.m is not None

    def set_shown(self, shown):
        """The game's HUD switched off (or on again): the experience goes with it."""
        self.shown = shown
        for n in (self.root, self.top_node, self.bottom_node):
            n.show() if shown else n.hide()

    def destroy(self):
        self.base.taskMgr.remove("experience hud")
        for n in (self.root, self.top_node, self.bottom_node):
            n.removeNode()

    # ---------- drawing ----------
    def clear(self):
        for n in (self.root, self.top_node, self.bottom_node):
            for c in n.getChildren():
                c.removeNode()
        self.typed = self.toast_rows = None

    def redraw(self):
        self.clear()
        if self.m is None:
            return
        if self.teacher:
            return self.draw_class()
        m = self.m
        if m.get("result") and self.closed_card != m["result"].get("when"):
            self.draw_card(m)
        t, y = self.top_node, self.top
        DirectFrame(parent=t, frameColor=BACK, frameSize=(-0.72, 0.72, y - 0.215, y))
        self.obj_title = hud.label(t, "", 0, y - 0.05, 0.04, C["YELLOW"], TextNode.ACenter)
        self.obj_hint = hud.label(t, "", 0, y - 0.1, 0.031, C["WHITE"], TextNode.ACenter, wrap=46)
        DirectFrame(parent=t, frameColor=(0.15, 0.16, 0.2, 1), frameSize=(-0.5, 0.5, y - 0.17, y - 0.152))
        self.xp_bar = DirectFrame(parent=t, frameColor=C["BLUE"], frameSize=(-0.5, -0.49, y - 0.17, y - 0.152))
        self.xp_text = hud.label(t, "", 0, y - 0.202, 0.024, C["GREY"], TextNode.ACenter)
        if m.get("result") is None:
            hud.button(t, "Skip", 0.64, y - 0.198, self.send, [{"type": "experience", "do": "skip"}], 0.026)
            for i, (action, words) in enumerate(m.get("actions") or []):
                hud.button(t, words, 0, y - 0.26 - 0.06 * i, self.send,
                           [{"type": "experience", "do": "action", "action": action}], 0.032, (0.15, 0.5, 0.3, 1))
        b = self.bottom_node
        DirectFrame(parent=b, frameColor=BACK, frameSize=(-0.95, 0.95, self.bottom, self.bottom + 0.2))
        hud.label(b, m.get("coach", "COACH"), -0.92, self.bottom + 0.16, 0.03, C["BLUE"])
        self.typed = hud.label(b, "", -0.92, self.bottom + 0.115, 0.031, C["WHITE"], wrap=52)
        self.typed_n = -1
        self.toast_rows = [hud.label(self.root, "", 0, 0.42 - i * 0.075, 0.052, C["GREEN"], TextNode.ACenter)
                           for i in range(3)]
        for row in self.toast_rows:
            row.setShadow((0, 0, 0, 0.9))
        self.refresh()

    def refresh(self):
        m = self.m
        if m is None or self.teacher or self.typed is None:
            return
        n = len(m.get("objectives", []))
        if m.get("result") is None and m.get("objective"):
            self.obj_title.setText(f"EXPERIENCE {m['n']}   OBJECTIVE {m['index'] + 1} OF {n}:  {m['objective'].upper()}")
            self.obj_hint.setText(m.get("hint", ""))
        else:
            self.obj_title.setText(f"EXPERIENCE {m['n']}: {m['title'].upper()}   COMPLETE")
            self.obj_hint.setText("")
        xp, nxt = m.get("xp", 0), m.get("next")
        frac = min(1.0, xp / max(1, m.get("max_xp", 1)))  # (the bar is the whole experience's XP)
        y = self.top
        self.xp_bar["frameSize"] = (-0.5, -0.5 + max(0.01, frac), y - 0.17, y - 0.152)
        self.xp_text.setText(f"RANK: {m.get('rank', '').upper()}    {xp} XP" +
                             (f"    {nxt[0] - xp} XP to {nxt[1]}" if nxt else "    top rank!"))

    def draw_card(self, m):
        res = m["result"]
        card = DirectFrame(parent=self.root, frameColor=(0.02, 0.03, 0.06, 0.95), frameSize=(-0.85, 0.85, -0.6, 0.62))
        hud.label(card, f"EXPERIENCE {m['n']}: {m['title'].upper()}", 0, 0.52, 0.05, C["YELLOW"], TextNode.ACenter)
        hud.label(card, "COMPLETE", 0, 0.45, 0.04, C["YELLOW"], TextNode.ACenter)
        for i in range(3):
            s = hud.label(card, "*", -0.16 + i * 0.16, 0.25, 0.22, C["YELLOW"] if i < res["stars"] else (0.3, 0.3, 0.35, 1),
                          TextNode.ACenter)
            s.setShadow((0, 0, 0, 0.6))
        hud.label(card, f"{res['xp']} XP      rank: {res['rank'].upper()}", 0, 0.14, 0.042, C["WHITE"], TextNode.ACenter)
        rows = m.get("objectives", [])
        for i, o in enumerate(rows):
            col, x = divmod(i, (len(rows) + 1) // 2)
            mark = "+" if o["state"] == "done" else "-"
            hud.label(card, f"{mark}  {o['title']}", -0.7 + col * 0.75, 0.05 - x * 0.05, 0.03,
                      C["GREEN"] if o["state"] == "done" else C["GREY"])
        best = m.get("best") or {}
        secs = int(res.get("seconds", 0))
        hud.label(card, f"time {secs // 60}:{secs % 60:02d}      best {best.get('best_xp', res['xp'])} XP, "
                        f"finished {best.get('finished', 1)} time{'s' if best.get('finished', 1) != 1 else ''}",
                  0, -0.42, 0.03, C["GREY"], TextNode.ACenter)
        hud.button(card, "START AGAIN", -0.25, -0.52, self.send, [{"type": "experience", "do": "again"}], 0.04,
                   (0.15, 0.5, 0.3, 1))
        hud.button(card, "CLOSE", 0.25, -0.52, self.close_card, [res.get("when")], 0.04)

    def close_card(self, when):
        self.closed_card = when
        self.redraw()

    def draw_class(self):
        """The teacher's view: everyone's objective, XP and rank, and who has finished."""
        m = self.m
        rows = m.get("learners", [])
        t, y = self.top_node, self.top
        h = 0.1 + 0.042 * max(1, min(10, len(rows)))
        DirectFrame(parent=t, frameColor=BACK, frameSize=(-0.7, 0.7, y - h, y))
        done = sum(1 for r in rows if r["finished"] or r.get("times"))
        hud.label(t, f"EXPERIENCE {m['n']}: {m['title'].upper()}   {done} of {len(rows)} finished", -0.67, y - 0.05,
                  0.032, C["YELLOW"])
        hud.button(t, "END", 0.62, y - 0.045, self.send, [{"type": "experience", "do": "stop"}], 0.026, (0.6, 0.2, 0.15, 1))
        if not rows:
            hud.label(t, "Nobody is here yet.", -0.67, y - 0.1, 0.028, C["GREY"])
        for i, r in enumerate(rows[:10]):
            yy = y - 0.1 - i * 0.042
            hud.label(t, r["name"][:16], -0.67, yy, 0.028, C["WHITE"])
            now = ("FINISHED " + "*" * r["stars"]) if r["finished"] else f"{r['index'] + 1} of {r['of']}: {r['objective']}"
            hud.label(t, now[:30], -0.3, yy, 0.026, C["GREEN"] if r["finished"] else C["WHITE"])
            best = f"   best {r['best_xp']}" if r.get("best_xp") is not None else ""
            hud.label(t, f"{r['xp']} XP  {r['rank']}{best}", 0.67, yy, 0.026, C["GREY"], TextNode.ARight)
        if len(rows) > 10:
            hud.label(t, f"and {len(rows) - 10} more", -0.67, y - h + 0.012, 0.024, C["GREY"])

    def controls_row(self, parent, x, y, scale=0.028):
        """The teacher's Controls tab: start the game's experience for the class, or end it. Returns the next y."""
        hud.label(parent, "Experience", x, y, scale, C["YELLOW"] if hud.THEME == "dark" else hud.YELLOW)
        if self.m is not None:
            hud.button(parent, f"END EXPERIENCE {self.m['n']}", x + 0.32, y + 0.008, self.send,
                       [{"type": "experience", "do": "stop"}], scale * 0.85, (0.6, 0.2, 0.15, 1))
        else:
            for i, e in enumerate(getattr(self, "available", None) or [{"n": 1, "title": "Orientation"}]):
                hud.button(parent, f"START {e['n']}: {e['title']}", x + 0.32 + i * 0.4, y + 0.008, self.send,
                           [{"type": "experience", "do": "start", "n": e["n"]}], scale * 0.85, (0.15, 0.45, 0.65, 1))
        return y - 0.06

    # ---------- every frame: the coach's words typed out, the toasts ----------
    def every_frame(self, task):
        if self.typed is not None and self.shown:
            now = time.perf_counter()
            n = min(len(self.say_text), int((now - self.say_at) * TYPE_RATE))
            if n != self.typed_n:
                self.typed_n = n
                self.typed.setText(self.say_text[:n])
            live = [t for t in self.toasts if now - t[2] < TOAST_SECS]
            self.toasts = live
            for row, t in zip(self.toast_rows, list(reversed(live)) + [None] * 3):
                row.setText(t[0] if t else "")
                if t:
                    row.setFg(t[1])
        return task.cont
