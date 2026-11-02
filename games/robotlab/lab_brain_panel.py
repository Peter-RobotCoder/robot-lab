"""Robot Lab's Brain panel (K, CHANGE 211): a robot brain written in pseudo code and Python side by side, as the
Missions' code panel shows a mission's (wake_up_call.py), but both sides can be typed in: pseudo code on the left
writes the Python on the right, Python on the right writes the pseudo code on the left (brain_pseudo.py reads both).
RUN sends the pseudo code to the class server, which makes it this learner's brain and switches autopilot on; every
version run is kept there (engine/teaching.keep_code). The Code tab shows the whole brain as the server runs it.

A mixin for the Robot Lab window (lab_client.Lab): it uses the window's send, typing, banner_note and missions.
"""
import textwrap

from direct.gui.DirectGui import DGG, DirectButton, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.ShowBaseGlobal import globalClock
from panda3d.core import TextNode

import brain_pseudo
from engine import editor

ROWS = 14
WAIT = 0.15  # (seconds after the typing pauses before the other side is written)
RED, YELLOW, GREEN, GREY = (1, 0.42, 0.4, 1), (1, 0.85, 0.3, 1), (0.45, 0.9, 0.5, 1), (0.62, 0.66, 0.74, 1)


class BrainEditor(editor.CodeEditor):
    """The engine's code editor, telling the panel when its text changes (nothing typed is ever corrected)."""

    def __init__(self, *a, on_change=None, **k):
        self.on_change = on_change
        super().__init__(*a, **k)

    def changed(self):
        super().changed()
        if self.on_change:
            self.on_change()


class BrainPanel:
    def brain_init(self, send, teacher=False):
        self.brain_send, self.brain_teacher = send, teacher
        self.brain_node = None
        self.brain_tab = "both"
        self.brain_p = {"lines": [""], "cursor": [0, 0], "scroll": 0}   # the pseudo code side
        self.brain_y = {"lines": [""], "cursor": [0, 0], "scroll": 0}   # the Python side
        self.brain_loaded = False
        self.brain_due = None       # (which side was typed in, and when to write the other)
        self.brain_parsed = None
        self.brain_unknown = []
        self.brain_said = ("", GREY)
        self.brain_eds = {}
        self.brain_syncing = False

    # ---------- opening and closing ----------
    def toggle_brain(self):
        if self.brain_node is not None:
            self.close_brain()
            return
        if not self.brains_on():
            self.banner_note("Brains aren't switched on for this mission yet", 3)
            return
        if not self.brain_loaded:  # (what they ran last time, kept with their profile; else the starter)
            text = (getattr(self, "missions", None) or {}).get("brain_pseudo") or brain_pseudo.STARTER
            self.brain_p["lines"][:] = text.split("\n")
            self.brain_loaded = True
            self.brain_read("pseudo")
        self.open_brain()

    def close_brain(self):
        if self.typing in ("brain_pseudo", "brain_python"):
            self.stop_typing()
        for ed in self.brain_eds.values():
            ed.destroy()
        self.brain_eds = {}
        if self.brain_node is not None:
            self.brain_node.destroy()
            self.brain_node = None

    def open_brain(self, tab=None):
        self.close_brain()
        self.brain_tab = tab or self.brain_tab
        a = self.getAspectRatio()
        # (on the left, over the health bars, up to the side panel's edge (0.78): the HUD's missions stay in sight)
        pw = self.brain_w = min(1.9, a + 0.76)
        left = 0.02
        self.brain_r = right = left + pw
        p = self.brain_node = editor.code_window((left, right, -1.97, -0.03), (0, 0, 0))
        p.reparentTo(self.a2dTopLeft)
        p.setBin("gui-popup", 5)  # (over the health bars, the battle's words and the news)
        x0 = left + 0.03
        editor.title_bar(self, p, x0, -0.075, "my_brain.pseudo" if self.brain_tab == "both" else "my_brain.py",
                         scale=0.026)
        for i, (key, text) in enumerate((("both", "Pseudo code + Python"), ("code", "Whole brain"))):
            DirectButton(parent=p, text=text, scale=0.03, pos=(left + 0.8 + i * 0.42, 0, -0.085),
                         command=self.open_brain, extraArgs=[key], relief=DGG.FLAT, pad=(0.4, 0.25),
                         frameColor=(0.2, 0.55, 0.65, 1) if key == self.brain_tab else (0.12, 0.15, 0.22, 1),
                         text_fg=(1, 1, 1, 1))
        DirectButton(parent=p, text="X", scale=0.034, pos=(right - 0.05, 0, -0.087), command=self.close_brain,
                     relief=DGG.FLAT, pad=(0.35, 0.2), frameColor=(0.3, 0.12, 0.12, 1), text_fg=(1, 1, 1, 1))
        if self.brain_tab == "code":
            self.build_brain_code(p, x0)
        else:
            self.build_brain_both(p, x0)

    def build_brain_both(self, p, x0):
        pw, scale = self.brain_w, 0.025
        ew = (pw - 0.1) / 2
        px = x0 + ew + 0.04
        dim = editor.DIM
        font = editor.code_font(self)
        extra = {"font": font} if font is not None else {}
        OnscreenText("PSEUDO CODE: what your robot does, one line each", pos=(x0, -0.16), scale=0.022, fg=dim,
                     align=TextNode.ALeft, parent=p)
        OnscreenText("PYTHON: the same, line for line (type here too)", pos=(px, -0.16), scale=0.022, fg=dim,
                     align=TextNode.ALeft, parent=p)
        # (the brain's start, which never changes: grey, above the Python side's lines)
        OnscreenText("def brain(me, enemies):   # enemy: the nearest; throttle, steer, attack = 0, 0, False",
                     pos=(px, -0.205), scale=min(0.018, ew / 50), fg=GREY, align=TextNode.ALeft, parent=p, **extra)
        top = -0.235
        self.brain_eds = {
            "pseudo": BrainEditor(self, p, self.brain_p, x0, top, ew, ROWS, scale=scale,
                                  on_change=lambda: self.brain_typed("pseudo"),
                                  on_focus=lambda: self.brain_focus("pseudo")),
            "python": BrainEditor(self, p, self.brain_y, px, top, ew, ROWS, scale=scale,
                                  on_change=lambda: self.brain_typed("python"),
                                  on_focus=lambda: self.brain_focus("python"))}
        for side, ed in self.brain_eds.items():
            ed.on_scroll = lambda side=side: self.brain_scrolled(side)
        bottom = top - ROWS * scale * 1.8 - scale * 0.6
        OnscreenText("    return throttle, steer, attack", pos=(px, bottom - 0.03), scale=0.018, fg=GREY,
                     align=TextNode.ALeft, parent=p, **extra)
        y = bottom - 0.08
        self.brain_problems = [OnscreenText("", pos=(x0, y - i * 0.04), scale=0.024, fg=RED, align=TextNode.ALeft,
                                            parent=p, mayChange=True, wordwrap=(pw - 0.08) / 0.024) for i in range(4)]
        y -= 4 * 0.04 + 0.03
        self.brain_run_button = DirectButton(parent=p, text="RUN", scale=0.042, pos=(x0 + 0.1, 0, y),
                                             command=self.brain_run, relief=DGG.FLAT, pad=(0.5, 0.2),
                                             frameColor=(0.2, 0.6, 0.3, 1), text_fg=(1, 1, 1, 1))
        DirectButton(parent=p, text="STOP", scale=0.034, pos=(x0 + 0.33, 0, y + 0.003), command=self.brain_stop,
                     relief=DGG.FLAT, pad=(0.5, 0.25), frameColor=(0.7, 0.25, 0.2, 1), text_fg=(1, 1, 1, 1))
        self.brain_status = OnscreenText(self.brain_said[0], pos=(x0 + 0.5, y - 0.005), scale=0.024, fg=self.brain_said[1],
                                         align=TextNode.ALeft, parent=p, mayChange=True, wordwrap=(pw - 0.6) / 0.024)
        self.build_brain_phrasebook(p, x0, y - 0.07)
        self.brain_show()

    def build_brain_phrasebook(self, p, x0, top):
        """For reference only: the words, what they do, an example (nothing is inserted for the learner)."""
        book = brain_pseudo.phrasebook()
        pw = self.brain_w
        DirectFrame(parent=p, frameColor=(1, 1, 1, 0.04), frameSize=(x0 - 0.01, self.brain_r - 0.02, -1.95, top + 0.02))
        OnscreenText("PHRASEBOOK  (type the words yourself; the Python beside each works too)", pos=(x0, top - 0.035),
                     scale=0.024, fg=YELLOW, align=TextNode.ALeft, parent=p)
        font = editor.code_font(self)
        extra = {"font": font} if font is not None else {}
        colw = (pw - 0.1) / 2
        step = 0.062
        for i, pat in enumerate(book["patterns"]):
            x, y = x0 + (i % 2) * colw, top - 0.08 - (i // 2) * step
            OnscreenText(pat["say"], pos=(x, y), scale=0.022, fg=editor.COLOURS["function"], align=TextNode.ALeft,
                         parent=p, **extra)
            OnscreenText(textwrap.shorten(pat["meaning"], int(colw / 0.0095), placeholder="..."), pos=(x, y - 0.026),
                         scale=0.017, fg=GREY, align=TextNode.ALeft, parent=p)
        y = top - 0.08 - ((len(book["patterns"]) + 1) // 2) * step
        values = "   ".join(f"[{k}] {v}" for k, v in book["values"].items())
        OnscreenText("Values:  " + values, pos=(x0, y), scale=0.017, fg=(1, 1, 1, 1), align=TextNode.ALeft, parent=p,
                     wordwrap=(pw - 0.08) / 0.017)

    def build_brain_code(self, p, x0):
        OnscreenText("YOUR WHOLE BRAIN AS PYTHON (what RUN gives the class server: change it on the other tab)",
                     pos=(x0, -0.16), scale=0.022, fg=editor.DIM, align=TextNode.ALeft, parent=p)
        parsed = self.brain_parsed or brain_pseudo.read("\n".join(self.brain_p["lines"]))
        text = parsed["source"] or brain_pseudo.source_of(parsed["body"])
        state = {"lines": text.rstrip("\n").split("\n"), "cursor": [0, 0], "scroll": 0}
        self.brain_eds = {"code": editor.CodeEditor(self, p, state, x0, -0.18, self.brain_w - 0.08, 36, scale=0.025,
                                                    read_only=True)}

    # ---------- typing ----------
    def brain_focus(self, side):
        """A side was clicked: the keyboard goes to it (not the game, a text box or the other side)."""
        other = self.brain_eds.get("python" if side == "pseudo" else "pseudo")
        if other is not None:
            other.blur()
        if self.typing and self.typing not in ("brain_pseudo", "brain_python"):
            self.stop_typing()
        self.typing = "brain_" + side

    def stop_typing(self, key=None):
        if self.typing in ("brain_pseudo", "brain_python") and (key is None or key == self.typing):
            for ed in getattr(self, "brain_eds", {}).values():
                ed.blur()
        super().stop_typing(key)

    def brain_typed(self, side):
        self.brain_due = (side, self.now_brain() + WAIT)
        if getattr(self, "brain_run_button", None) is not None and self.brain_node is not None:
            self.brain_run_button["state"] = DGG.DISABLED  # (until it has been read)

    def now_brain(self):
        return globalClock.getFrameTime()

    def brain_tick(self):
        """Every frame: the other side written once the typing has paused."""
        if self.brain_due and self.now_brain() >= self.brain_due[1]:
            side, self.brain_due = self.brain_due[0], None
            self.brain_read(side)
            self.brain_show()

    def brain_read(self, side):
        """Read the side typed in and write the other one (never the side being typed in)."""
        if side == "python":
            pseudo, self.brain_unknown = brain_pseudo.to_pseudo("\n".join(self.brain_y["lines"]))
            self.brain_p["lines"][:] = pseudo.split("\n")
        else:
            self.brain_unknown = []
        self.brain_parsed = brain_pseudo.read("\n".join(self.brain_p["lines"]))
        if side == "pseudo":
            self.brain_y["lines"][:] = list(self.brain_parsed["body"])
        n = len(self.brain_p["lines"])  # (the two sides keep the same lines)
        self.brain_y["lines"][n:] = []
        self.brain_y["lines"].extend([""] * (n - len(self.brain_y["lines"])))

    def brain_scrolled(self, side):
        """The two sides scroll together, line beside line."""
        if self.brain_syncing:
            return
        me, other = self.brain_eds.get(side), self.brain_eds.get("python" if side == "pseudo" else "pseudo")
        if me is None or other is None or other.state["scroll"] == me.state["scroll"]:
            return
        self.brain_syncing = True
        other.state["scroll"] = me.state["scroll"]
        other.refresh()
        self.brain_syncing = False

    def brain_show(self):
        """The two sides drawn again, and what's wrong (or that it can run) under them."""
        if self.brain_node is None or self.brain_tab != "both":
            return
        for ed in self.brain_eds.values():
            ed.refresh()
        parsed = self.brain_parsed or brain_pseudo.read("\n".join(self.brain_p["lines"]))
        rows = [(f"Line {n}: this Python isn't one the phrasebook knows (see the phrasebook below)", RED)
                for n in self.brain_unknown]
        for r in parsed["errors"]:
            if r["n"] in self.brain_unknown:
                continue
            rows.append((f"Line {r['n']}: {r['message']}" + (f"  {r['after']}" if r.get("after") else ""), RED))
            if r.get("hint"):
                rows.append((f"      Did you mean: {r['hint']}?", YELLOW))
        if not rows and parsed["code_lines"]:
            n = parsed["code_lines"]
            rows.append((f"All {n} line{'' if n == 1 else 's'} understood. RUN gives your robot this brain "
                         "(Ctrl+Enter runs too).", GREEN))
        if len(rows) > len(self.brain_problems):
            more = len(rows) - len(self.brain_problems) + 1
            rows = rows[:len(self.brain_problems) - 1] + [(f"... and {more} more", RED)]
        for i, t in enumerate(self.brain_problems):
            text, colour = rows[i] if i < len(rows) else ("", RED)
            t.setText(text)
            t.setFg(colour)
        ok = parsed["source"] is not None and not self.brain_unknown and self.brain_due is None
        self.brain_run_button["state"] = DGG.NORMAL if ok else DGG.DISABLED
        self.brain_run_button["frameColor"] = (0.2, 0.6, 0.3, 1) if ok else (0.22, 0.25, 0.3, 1)

    # ---------- RUN and STOP ----------
    def brain_run(self):
        if self.brain_due is not None:
            side, self.brain_due = self.brain_due[0], None
            self.brain_read(side)
        parsed = self.brain_parsed
        if parsed is None or parsed["source"] is None or self.brain_unknown:
            self.brain_say("Fix the lines in red first.", RED)
            return
        if self.brain_teacher:  # (the teacher's demo brain is Controls' Upload demo brain)
            self.brain_say("RUN drives a learner's robot: try it in a learner's window.", GREY)
            return
        text = brain_pseudo.indent("\n".join(self.brain_p["lines"]))  # (tidied: each line indented by its block)
        self.brain_p["lines"][:] = text.split("\n")
        self.brain_read("pseudo")
        self.brain_send({"type": "brain_run", "pseudo": text})
        self.brain_say("Sending your code to the class server...", GREY)
        self.brain_show()

    def brain_stop(self):
        if (getattr(self, "missions", None) or {}).get("autopilot"):
            self.brain_send({"type": "autopilot"})
            self.brain_say("Stopped: you're driving again.", GREY)
        else:
            self.brain_say("Your code isn't driving (RUN starts it).", GREY)

    def brain_say(self, text, colour):
        self.brain_said = (text, colour)
        if self.brain_node is not None and getattr(self, "brain_status", None) is not None and self.brain_tab == "both":
            self.brain_status.setText(text)
            self.brain_status.setFg(colour)

    def brain_result(self, m):
        """The class server's answer to RUN (or to U)."""
        self.brain_say(m.get("error", ""), GREEN if m.get("ok") else RED)
