"""Craft Lab's panels for the Craft Bot (CHANGE 200), on the right of the window:

    I   the GARAGE: your Bot's variables as every game's garage shows them (bot_name a string, dig / build / speed
        integers sharing 100 points, colour a list), BUILD MY BOT
    C   the CODE: the same design as Python (engine.schema), to change there and BUILD MY BOT from the code (it can
        change what the garage this lesson doesn't show: the teacher is told)
    B   the BRAIN: brains/my_bot.py in the code editor (engine.editor), SAVE AND UPLOAD (U), AUTOPILOT (P), and what
        the Bot is doing or the error that stopped it

The panels send the window's messages (design, brain, autopilot); offline the window answers them itself.
"""
import os
from types import SimpleNamespace

from direct.gui.DirectGui import DGG, DirectButton, DirectEntry, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

import craft_bot
import craft_design as design
import craft_version
import sys
sys.path.insert(0, craft_version.ENGINE_HOME)
from engine import editor, hud, schema  # noqa: E402

PANEL = (0.05, 0.06, 0.09, 0.93)
YELLOW, WHITE, GREY, RED, GREEN = (1, .9, .35, 1), (1, 1, 1, 1), (.75, .8, .9, 1), (1, .45, .4, 1), (.45, 1, .5, 1)
SWATCHES = [(220, 60, 50), (240, 140, 30), (240, 200, 40), (60, 190, 90), (60, 130, 230), (180, 90, 230),
            (230, 90, 160), (60, 200, 200), (240, 240, 240), (40, 40, 48)]


def ctx():
    return SimpleNamespace(title="MY CRAFT BOT", points_total=design.POINTS_TOTAL, weapons=[], all_weapons=[], house={},
                           rules={}, model=None, makers={})


def button(parent, text, x, y, command, args=(), scale=0.038, colour=(0.2, 0.3, 0.45, 1)):
    return DirectButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), command=command, extraArgs=list(args),
                        relief=DGG.FLAT, pad=(0.35, 0.18), frameColor=colour, text_fg=WHITE)


class Panel:
    def __init__(self, app):
        self.app = app
        self.root = DirectFrame(parent=app.a2dTopRight, frameColor=PANEL, frameSize=(-1.36, -0.03, -1.86, -0.12))
        self.typing_entries = []

    def typing(self):
        return any(e["focus"] for e in self.typing_entries) if self.typing_entries else False

    def destroy(self):
        self.root.destroy()


class Garage(Panel):
    """Your Craft Bot's variables, changed with buttons: a string, three integers, a list."""

    def __init__(self, app, d, tools, limits):
        super().__init__(app)
        self.d = {"name": d["name"], "colour": list(d["colour"]), "points": dict(d["points"]), "settings": {}}
        self.tools, self.limits = tools, limits
        r = self.root
        OnscreenText("GARAGE: your Craft Bot", pos=(-1.3, -0.2), scale=0.05, fg=YELLOW, align=TextNode.ALeft, parent=r)
        OnscreenText("STRING VARIABLES (text)", pos=(-1.3, -0.32), scale=0.034, fg=GREY, align=TextNode.ALeft, parent=r)
        OnscreenText("bot_name: str =", pos=(-1.3, -0.4), scale=0.036, fg=WHITE, align=TextNode.ALeft, parent=r)
        self.name = DirectEntry(parent=r, scale=0.04, pos=(-0.85, 0, -0.41), width=14, initialText=self.d["name"],
                                numLines=1, frameColor=(0.9, 0.9, 0.9, 1),
                                state=DGG.NORMAL if tools.get("name_and_colour") else DGG.DISABLED)
        self.typing_entries.append(self.name)
        OnscreenText("INTEGER VARIABLES (whole numbers): the points to share", pos=(-1.3, -0.52), scale=0.034, fg=GREY,
                     align=TextNode.ALeft, parent=r)
        self.values = {}
        for i, k in enumerate(design.STATS):
            y = -0.62 - i * 0.12
            OnscreenText(f"{k}: int =", pos=(-1.3, y), scale=0.038, fg=WHITE, align=TextNode.ALeft, parent=r)
            self.values[k] = OnscreenText("", pos=(-0.82, y), scale=0.04, fg=YELLOW, align=TextNode.ALeft, parent=r,
                                          mayChange=True)
            OnscreenText(design.STAT_NOTES[k], pos=(-1.3, y - 0.045), scale=0.026, fg=GREY, align=TextNode.ALeft, parent=r)
            on = tools.get(k) or tools.get("points_table")
            for j, step in enumerate((-5, -1, 1, 5)):
                if on:
                    button(r, f"{step:+d}", -0.62 + j * 0.13, y + 0.01, self.change, (k, step), 0.034)
        self.left = OnscreenText("", pos=(-1.3, -1.02), scale=0.036, fg=GREEN, align=TextNode.ALeft, parent=r, mayChange=True)
        OnscreenText("VARIABLE LISTS: colour = [red, green, blue]", pos=(-1.3, -1.12), scale=0.034, fg=GREY,
                     align=TextNode.ALeft, parent=r)
        for i, c in enumerate(SWATCHES):
            DirectButton(parent=r, frameColor=(c[0] / 255, c[1] / 255, c[2] / 255, 1), frameSize=(-0.045, 0.045, -0.045, 0.045),
                         pos=(-1.25 + i * 0.115, 0, -1.22), relief=DGG.FLAT, command=self.colour, extraArgs=[list(c)],
                         state=DGG.NORMAL if tools.get("name_and_colour") else DGG.DISABLED)
        self.colour_text = OnscreenText("", pos=(-1.3, -1.33), scale=0.034, fg=WHITE, align=TextNode.ALeft, parent=r,
                                        mayChange=True)
        stats = tools.get("stats_readout")
        self.stats = OnscreenText("", pos=(-1.3, -1.44), scale=0.03, fg=GREY, align=TextNode.ALeft, parent=r,
                                  mayChange=True) if stats else None
        button(r, "BUILD MY BOT", -0.7, -1.6, self.build, (), 0.05, (0.15, 0.55, 0.25, 1))
        self.msg = OnscreenText("", pos=(-0.7, -1.72), scale=0.03, fg=RED, parent=r, mayChange=True, wordwrap=40)
        self.show()

    def change(self, k, step):
        lo, hi = self.limits["points"][k]
        self.d["points"][k] = max(lo, min(hi, self.d["points"][k] + step))
        self.show()

    def colour(self, c):
        self.d["colour"] = c
        self.show()

    def show(self):
        for k in design.STATS:
            self.values[k].setText(str(self.d["points"][k]))
        left = self.limits["points_total"] - sum(self.d["points"].values())
        self.left.setText(f"{left} points left to share" if left >= 0 else f"{-left} points too many!")
        self.left.setFg(GREEN if left >= 0 else RED)
        self.colour_text.setText(f"colour: list = {self.d['colour']}")
        if self.stats is not None:
            st = design.stats_of(self.d)
            self.stats.setText(f"a dig takes {st['dig']:.2f} s x the block's hardness; a placement {st['build']:.2f} s; "
                               f"a move {st['move']:.2f} s")

    def build(self):
        self.d["name"] = self.name.get().strip() or self.d["name"]
        self.app.act_design(dict(self.d), by_code=False)

    def result(self, ok, problems):
        self.msg.setText("Built!" if ok else "Not built: " + "; ".join(problems))
        self.msg.setFg(GREEN if ok else RED)


class Code(Panel):
    """Your Craft Bot as Python, to change and build from (engine.schema reads it back: nothing in it runs)."""

    def __init__(self, app, d):
        super().__init__(app)
        r = self.root
        OnscreenText("CODE: your Craft Bot as Python", pos=(-1.3, -0.2), scale=0.05, fg=YELLOW, align=TextNode.ALeft, parent=r)
        self.d = d
        self.state = {"lines": schema.code_lines(design.schema(), d, ctx()), "cursor": [0, 0], "scroll": 0}
        self.ed = editor.CodeEditor(app, r, self.state, -1.3, -0.28, 1.22, 26, 0.024)
        button(r, "BUILD MY BOT from the code", -0.7, -1.6, self.build, (), 0.045, (0.15, 0.55, 0.25, 1))
        self.msg = OnscreenText("", pos=(-0.7, -1.72), scale=0.03, fg=RED, parent=r, mayChange=True, wordwrap=40)

    def typing(self):
        return self.ed.focused

    def build(self):
        try:
            values = schema.parse_code("\n".join(self.state["lines"]), design.schema(), ctx())
        except schema.ParseError as e:
            self.msg.setText(str(e))
            self.msg.setFg(RED)
            return
        new = {"name": self.d["name"], "colour": list(self.d["colour"]), "points": dict(self.d["points"]), "settings": {}}
        changed, hidden, problems = schema.apply_values(design.schema(), new, values, ctx(), lambda v, x: True)
        if problems:
            self.msg.setText("; ".join(problems))
            self.msg.setFg(RED)
            return
        self.app.act_design(new, by_code=True)

    def result(self, ok, problems):
        self.msg.setText("Built from the code!" if ok else "Not built: " + "; ".join(problems))
        self.msg.setFg(GREEN if ok else RED)

    def destroy(self):
        self.ed.destroy()
        super().destroy()


class Brain(Panel):
    """brains/my_bot.py in the code editor: save it and upload it to your Bot, switch the autopilot on and off."""

    def __init__(self, app, path):
        super().__init__(app)
        self.path = path
        r = self.root
        OnscreenText("BRAIN: brains/my_bot.py", pos=(-1.3, -0.2), scale=0.05, fg=YELLOW, align=TextNode.ALeft, parent=r)
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(craft_bot.STARTER)
        with open(path, encoding="utf-8") as f:
            lines = f.read().replace("\r\n", "\n").split("\n")
        self.state = {"lines": lines, "cursor": [0, 0], "scroll": max(0, len(lines) - 26)}
        self.ed = editor.CodeEditor(app, r, self.state, -1.3, -0.28, 1.22, 26, 0.022)
        button(r, "SAVE AND UPLOAD (U)", -1.0, -1.56, self.upload, (), 0.04, (0.15, 0.55, 0.25, 1))
        button(r, "AUTOPILOT (P)", -0.42, -1.56, app.toggle_autopilot, (), 0.04)
        self.msg = OnscreenText("", pos=(-0.7, -1.68), scale=0.028, fg=GREY, parent=r, mayChange=True, wordwrap=44)

    def typing(self):
        return self.ed.focused

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.state["lines"]).rstrip() + "\n")
        except OSError as e:
            self.msg.setText(f"Couldn't save: {e}")

    def upload(self):
        self.save()
        self.app.upload_brain()

    def say(self, text, ok=True):
        self.msg.setText(text)
        self.msg.setFg(GREEN if ok else RED)

    def destroy(self):
        self.ed.destroy()
        super().destroy()


def hud_colours():
    return hud.YELLOW, hud.GREY
