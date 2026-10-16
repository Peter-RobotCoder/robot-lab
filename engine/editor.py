"""A small code editor for the game's windows, drawn with Panda3D text (a DirectEntry can't do any of this).

    click anywhere in the code to put the cursor there, then type
    the words are coloured as an IDE colours Python: keywords, strings, numbers, comments, names, brackets
    code that is too long for its box scrolls (mouse wheel, or move the cursor): the buttons under it stay put

CHANGE 143: it looks as the browser's code panel does since CHANGE 138 (the promo videos' code window): the navy
panel with its cyan edge, the title bar's three dots and the file's name (title_bar), JetBrains Mono (engine/fonts,
made from the website's font), the promo colours (a function's name and the types in cyan), the cursor's line and
its number, and a bracket beside the cursor marked with its partner. The light look is VS Code's Light+.

Keys while typing: arrows, Home, End, Backspace, Delete, Tab (4 spaces), Enter (the window decides: Robot Lab
applies the code), Shift+Enter (a new line).

The text, cursor and scroll position live in a plain dictionary the window keeps ({"lines", "cursor", "scroll"}),
so the editor can be drawn again (when its panel is redrawn) without losing anything.
"""
import math
import os
import re

from direct.gui.DirectGui import DGG, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.DirectObject import DirectObject
from panda3d.core import (Filename, Geom, GeomNode, GeomTrifans, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, MouseButton, PGButton, Point3, TextNode, TextProperties,
                          TextPropertiesManager)

WHEEL_UP = PGButton.getPressPrefix() + MouseButton.wheelUp().getName() + "-"  # (the mouse wheel over a panel)
WHEEL_DOWN = PGButton.getPressPrefix() + MouseButton.wheelDown().getName() + "-"


def hex_colour(text, alpha=1.0):
    """"#ff4fd8" -> (r, g, b, a), each 0 to 1 (the browser's style.css writes its colours this way)."""
    text = text.lstrip("#")
    return tuple(int(text[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


def rgba(r, g, b, a=1.0):
    return (r / 255, g / 255, b / 255, a)


# CHANGE 143: the promo videos' colours (the browser's #codepanel in style.css), and VS Code's Light+ for the light look
DARK_COLOURS = {"keyword": hex_colour("#ff4fd8"), "function": hex_colour("#3ee9ff"), "type": hex_colour("#3ee9ff"),
                "string": hex_colour("#ffb02e"), "number": hex_colour("#b6ff3b"), "comment": hex_colour("#7f8bb0"),
                "bracket": hex_colour("#c3cbe8"), "other": hex_colour("#e6ebff")}
LIGHT_COLOURS = {"keyword": hex_colour("#0000ff"), "function": hex_colour("#795e26"), "type": hex_colour("#267f99"),
                 "string": hex_colour("#a31515"), "number": hex_colour("#098658"), "comment": hex_colour("#008000"),
                 "bracket": hex_colour("#1f1f1f"), "other": hex_colour("#1f1f1f")}
# the panel round the code (the window draws it with code_window), the box the code is in, and the editor's marks
DARK_LOOK = {"PANEL_BACK": rgba(10, 14, 30, 0.95), "PANEL_EDGE": rgba(62, 233, 255, 0.35),
             "PANEL_TEXT": hex_colour("#e6ebff"), "DIM": hex_colour("#9aa6c8"), "TITLE_BACK": rgba(62, 233, 255, 0.06),
             "BACK": rgba(4, 7, 18, 0.7), "BOX_EDGE": rgba(62, 233, 255, 0.12), "GUTTER_EDGE": rgba(76, 88, 124, 0.35),
             "GUTTER": hex_colour("#4c587c"), "GUTTER_CUR": hex_colour("#9aa6c8"), "CURSOR": hex_colour("#b6ff3b"),
             "LINE_BACK": rgba(62, 233, 255, 0.07), "SEL_BACK": rgba(62, 233, 255, 0.26),
             "MATCH_BACK": rgba(182, 255, 59, 0.2), "MATCH_EDGE": rgba(182, 255, 59, 0.6),
             "BOX_BACK": (0.15, 0.17, 0.22, 1), "BOX_TEXT": (1, 1, 1, 1), "BOX_CURSOR": (1, 1, 1, 1)}
LIGHT_LOOK = {"PANEL_BACK": hex_colour("#ffffff"), "PANEL_EDGE": hex_colour("#c5ccd8"),
              "PANEL_TEXT": hex_colour("#1f1f1f"), "DIM": hex_colour("#616161"), "TITLE_BACK": (0, 0, 0, 0.035),
              "BACK": hex_colour("#ffffff"), "BOX_EDGE": hex_colour("#e1e4ea"), "GUTTER_EDGE": hex_colour("#eceef2"),
              "GUTTER": hex_colour("#6e7681"), "GUTTER_CUR": hex_colour("#0b216f"), "CURSOR": hex_colour("#000000"),
              "LINE_BACK": (0, 0, 0, 0.045), "SEL_BACK": rgba(0, 120, 215, 0.24),
              "MATCH_BACK": rgba(0, 100, 0, 0.1), "MATCH_EDGE": hex_colour("#b9b9b9"),
              "BOX_BACK": (1, 1, 1, 1), "BOX_TEXT": (0.08, 0.09, 0.12, 1), "BOX_CURSOR": (0.1, 0.1, 0.1, 1)}
DOTS = (hex_colour("#ff5f57"), hex_colour("#febc2e"), hex_colour("#28c840"))  # the title bar's: red, amber, green
COLOURS = dict(DARK_COLOURS)
(PANEL_BACK, PANEL_EDGE, PANEL_TEXT, DIM, TITLE_BACK, BACK, BOX_EDGE, GUTTER_EDGE, GUTTER, GUTTER_CUR, CURSOR, LINE_BACK, SEL_BACK,
 MATCH_BACK, MATCH_EDGE, BOX_BACK, BOX_TEXT, BOX_CURSOR) = (DARK_LOOK[k] for k in DARK_LOOK)


def set_theme(name):
    """The dark or the light look for code drawn after this (the window redraws its code panel)."""
    light = name == "light"
    globals().update(LIGHT_LOOK if light else DARK_LOOK)
    COLOURS.clear()
    COLOURS.update(LIGHT_COLOURS if light else DARK_COLOURS)
    styles()


# Python as the browser's codeTokens (garage.js) splits it: a comment, a string (with any prefix: f"...", r'...'),
# a name, a number (0x1F, 1_000, 2.5e3, 3j), a bracket, or anything else (spaces, = , : and the like: plain text)
TOKEN = re.compile(r"""(?P<comment>\#.*)
                     |(?P<string>(?:[rRbBuUfF]{1,2})?(?:"(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?))
                     |(?P<name>[A-Za-z_]\w*)
                     |(?P<number>(?:0[xXoObB][\da-fA-F_]+|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?[jJ]?))
                     |(?P<bracket>[\[\]{}()])
                     |(?P<other>\s+|.)""", re.VERBOSE)
KEYWORDS = set(("False None True and as assert async await break case class continue def del elif else except "
                "finally for from global if import in is lambda match nonlocal not or pass raise return try while "
                "with yield").split())
TYPES = set("int float str list dict tuple set bool bytes".split())
CALL = re.compile(r"[ \t]*\(")
OPENS, CLOSES = "([{", ")]}"
MAX_LINES, MAX_LENGTH = 80, 110
FONTS = ("consola.ttf", "cour.ttf", "lucon.ttf")  # a font with every letter the same width (Windows has these)
OWN_FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "JetBrainsMono.ttf")  # (CHANGE 143)
_font = [None, False]  # the font, and whether we've looked for it


def code_font(base):
    """A fixed-width font for code: JetBrains Mono (the engine's own, as the browser's code panel), else one Windows
    has, else None (Panda3D's own font)."""
    if not _font[1]:
        _font[1] = True
        folder = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for path in [OWN_FONT] + [os.path.join(folder, name) for name in FONTS]:
            path = os.path.realpath(path)  # (its true capitals: Panda3D is fussy about them)
            if os.path.exists(path):
                try:
                    font = base.loader.loadFont(Filename.fromOsSpecific(path).getFullpath())
                    if font is not None and font.isValid():
                        font.setPixelsPerUnit(64)  # (sharp at the small size code is drawn)
                        _font[0] = font
                        break
                except Exception:
                    pass
    return _font[0]


def styles():
    """The colours as named text styles, so one piece of text can change colour part-way along."""
    mgr = TextPropertiesManager.getGlobalPtr()
    for kind, (r, g, b, _a) in COLOURS.items():
        props = TextProperties()
        props.setTextColor(r, g, b, 1)
        mgr.setProperties("code_" + kind, props)


def tokens(line):
    """A line of Python as (kind, text) pieces: keyword, function (the name after def or class, or a name called:
    print( ), type (int, str, list...), string, number, comment, bracket or other (plain text), as the browser's
    codeTokens has them (CHANGE 143)."""
    out, before = [], ""
    for m in TOKEN.finditer(line):
        kind, text = m.lastgroup, m.group()
        if kind == "name":
            kind = "keyword" if text in KEYWORDS else \
                "function" if before in ("def", "class") or CALL.match(line, m.end()) else \
                "type" if text in TYPES else "other"
            before = text
        elif kind != "other":
            before = ""
        out.append((kind, text))
    return out


def coloured(line):
    """The line with each piece marked with its style (\\1style\\1 text \\2 is Panda3D's way of writing that)."""
    return "".join(text if not text.strip() else f"\1code_{kind}\1{text}\2" for kind, text in tokens(line))


def bracket_pairs(lines):
    """Each bracket's partner, across the lines: {(line, col): (line, col)} both ways. Brackets in strings and
    comments don't count; a closing bracket that doesn't match the last one opened has no partner (as garage.js)."""
    pairs, open_ = {}, []
    for n, line in enumerate(lines):
        col = 0
        for kind, text in tokens(line):
            if kind == "bracket":
                if text in OPENS:
                    open_.append((n, col, text))
                elif open_ and open_[-1][2] == OPENS[CLOSES.index(text)]:
                    o = open_.pop()
                    pairs[(o[0], o[1])], pairs[(n, col)] = (n, col), (o[0], o[1])
            col += len(text)
    return pairs


def file_name(word, who=None):
    """The code panel's file name, as the browser's: my_robot.py, or (the teacher looking at a learner's) sam_robot.py."""
    if not who:
        return f"my_{word.lower()}.py"
    return f"{re.sub(r'[^a-z0-9]+', '_', str(who).lower()).strip('_') or 'their'}_{word.lower()}.py"


def dot(parent, x, y, radius, colour, sides=24):
    """A filled circle (the title bar's dots: a DirectFrame can only be a rectangle)."""
    data = GeomVertexData("dot", GeomVertexFormat.getV3(), Geom.UHStatic)
    w = GeomVertexWriter(data, "vertex")
    w.addData3(0, 0, 0)
    for i in range(sides + 1):
        a = 2 * math.pi * i / sides
        w.addData3(radius * math.cos(a), 0, radius * math.sin(a))
    fan = GeomTrifans(Geom.UHStatic)
    fan.addConsecutiveVertices(0, sides + 2)
    fan.closePrimitive()
    geom = Geom(data)
    geom.addPrimitive(fan)
    node = GeomNode("dot")
    node.addGeom(geom)
    np = parent.attachNewNode(node)
    np.setPos(x, 0, y)
    np.setColor(*colour)
    np.setTwoSided(True)
    return np


def code_window(rect, pos, edge=0.006):
    """The code panel's frame as the browser's (CHANGE 143): navy (white in the light look) with a cyan edge (grey).
    rect: (left, right, bottom, top). The window draws its title bar, the code and its buttons in it."""
    left, right, bottom, top = rect
    f = DirectFrame(frameColor=PANEL_EDGE, frameSize=(left - edge, right + edge, bottom - edge, top + edge), pos=pos)
    DirectFrame(parent=f, frameColor=PANEL_BACK, frameSize=rect)
    return f


def title_bar(base, parent, x, y, name, scale=0.02):
    """The promo videos' code window's title: three dots and the file's name (my_robot.py) after them, at x, y (the
    middle of the dots). Returns the x the name ends at."""
    r = scale * 0.42
    for i, colour in enumerate(DOTS):
        dot(parent, x + r + i * r * 2.9, y, r, colour)
    font = code_font(base)
    extra = {"font": font} if font is not None else {}
    at = x + r * 2 * 3 + r * 1.8 + scale * 0.4
    text = OnscreenText(name, pos=(at, y - scale * 0.32), scale=scale, fg=DIM, align=TextNode.ALeft, parent=parent,
                        mayChange=True, **extra)
    return at + text.textNode.getWidth() * scale


def clean(text):
    """Typed or loaded text as the editor keeps it: no tabs or control characters."""
    return "".join(ch for ch in str(text).replace("\t", "    ") if ch >= " " and ch != "\x7f")


CLIPBOARD = [""]  # the editor's own clipboard (CHANGE 88); the system's is used too where it can be reached


def clipboard_get():
    try:
        import ctypes
        import ctypes.wintypes as wt
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        if not u32.OpenClipboard(None):
            return CLIPBOARD[0]
        try:
            h = u32.GetClipboardData(13)  # CF_UNICODETEXT
            if not h:
                return CLIPBOARD[0]
            k32.GlobalLock.restype = ctypes.c_void_p
            p = k32.GlobalLock(ctypes.c_void_p(h))
            text = ctypes.wstring_at(p) if p else ""
            k32.GlobalUnlock(ctypes.c_void_p(h))
            return text
        finally:
            u32.CloseClipboard()
    except Exception:
        return CLIPBOARD[0]


def clipboard_set(text):
    CLIPBOARD[0] = text
    try:
        import ctypes
        u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
        if not u32.OpenClipboard(None):
            return
        try:
            u32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            k32.GlobalAlloc.restype = ctypes.c_void_p
            h = k32.GlobalAlloc(0x0042, len(data))  # GMEM_MOVEABLE | GMEM_ZEROINIT
            k32.GlobalLock.restype = ctypes.c_void_p
            p = k32.GlobalLock(ctypes.c_void_p(h))
            ctypes.memmove(p, data, len(data))
            k32.GlobalUnlock(ctypes.c_void_p(h))
            u32.SetClipboardData(13, ctypes.c_void_p(h))
        finally:
            u32.CloseClipboard()
    except Exception:
        pass


class CodeEditor(DirectObject):
    def __init__(self, base, parent, state, x, top, width, rows, scale=0.022, on_enter=None, on_focus=None,
                 read_only=False):
        """state: {"lines": [...], "cursor": [line, column], "scroll": first line shown}, kept by the window.
        x, top, width: the box, in the parent's own units. rows: how many lines of code it shows.
        read_only: plain text to read and scroll (the mouse wheel), not code to edit: no cursor, no colours."""
        self.base, self.parent, self.state, self.read_only = base, parent, state, read_only
        self.x, self.top, self.width, self.rows, self.scale = x, top, width, rows, scale
        self.on_enter, self.on_focus = on_enter, on_focus
        self.on_scroll = None  # (called whenever it's redrawn: the window can say how much is out of sight)
        self.focused = False
        self.line_h = scale * 1.8
        self.code_x = x + scale * 2.6  # (to the right of the line numbers)
        self.font = code_font(base)
        styles()
        self.measure = TextNode("measure")
        if self.font is not None:
            self.measure.setFont(self.font)
        state.setdefault("lines", [""])
        state.setdefault("cursor", [0, 0])
        state.setdefault("scroll", 0)
        height = rows * self.line_h + scale * 0.6
        e = 0.0025  # (CHANGE 143: the box's faint edge, and a line between the numbers and the code, as the browser's)
        self.edge = DirectFrame(parent=parent, frameColor=BOX_EDGE, frameSize=(x - e, x + width + e, top - height - e, top + e))
        self.back = DirectFrame(parent=parent, frameColor=BACK, frameSize=(x, x + width, top - height, top),
                                state=DGG.NORMAL)
        self.back.bind(DGG.B1PRESS, self.click)
        self.back.bind(WHEEL_UP, lambda e: self.wheel(3 if getattr(base, "invert_scroll", False) else -3))
        self.back.bind(WHEEL_DOWN, lambda e: self.wheel(-3 if getattr(base, "invert_scroll", False) else 3))
        self.gutter_edge = DirectFrame(parent=parent, frameColor=GUTTER_EDGE if not read_only else (0, 0, 0, 0),
                                       frameSize=(self.code_x - scale * 0.55, self.code_x - scale * 0.55 + 0.002,
                                                  top - height, top))
        self.line_back = DirectFrame(parent=parent, frameColor=LINE_BACK, frameSize=(0, width, -scale * 0.45,
                                                                                    self.line_h - scale * 0.45))
        cw, lo, hi, t = self.text_width("M"), -scale * 0.35, scale * 1.05, 0.0018
        self.match_backs = []  # a bracket beside the cursor and its partner: a soft box with a thin edge (CHANGE 143)
        for _ in range(2):
            b = DirectFrame(parent=parent, frameColor=MATCH_BACK, frameSize=(0, cw, lo, hi))
            for size in ((0, cw, lo, lo + t), (0, cw, hi - t, hi), (0, t, lo + t, hi - t), (cw - t, cw, lo + t, hi - t)):
                DirectFrame(parent=b, frameColor=MATCH_EDGE, frameSize=size)
            b.hide()
            self.match_backs.append(b)
        self.cursor = DirectFrame(parent=parent, frameColor=CURSOR,
                                  frameSize=(0, scale * 0.09, -scale * 0.35, scale * 1.05))
        self.anchor = None  # the other end of the selection (CHANGE 88), [line, col], or None
        self.dragging = False
        self.sel_backs = [DirectFrame(parent=parent, frameColor=SEL_BACK,
                                      frameSize=(0, 0.01, -scale * 0.35, scale * 1.05)) for _ in range(rows)]
        for b in self.sel_backs:
            b.hide()
        self.pairs, self.pairs_of = {}, None  # every bracket's partner, and the text they were found in
        extra = {"font": self.font} if self.font is not None else {}
        # how many letters fit across the box: a longer line is cut at the box's edge, not drawn over it
        self.cols = max(10, int((x + width - self.code_x - scale * 0.3) / max(1e-6, self.text_width("M"))))
        self.numbers, self.texts = [], []
        for i in range(rows):
            y = self.row_y(i)
            self.numbers.append(OnscreenText("", pos=(self.code_x - scale * 0.9, y), scale=scale * 0.85, fg=GUTTER,
                                             align=TextNode.ARight, parent=parent, mayChange=True, **extra))
            self.texts.append(OnscreenText("", pos=(self.code_x, y), scale=scale, fg=(*COLOURS["other"], 1),
                                           align=TextNode.ALeft, parent=parent, mayChange=True, **extra))
        if getattr(base, "buttonThrowers", None):  # (a window with no keyboard, as the tests use, has none)
            base.buttonThrowers[0].node().setKeystrokeEvent("keystroke")
        self.blink = None
        if read_only:
            self.tidy()
            self.refresh()
            return
        self.accept("keystroke", self.typed)
        for key, fn, args in (("backspace", self.erase, [-1]), ("delete", self.erase, [0]),
                              ("arrow_left", self.move, [0, -1]), ("arrow_right", self.move, [0, 1]),
                              ("arrow_up", self.move, [-1, 0]), ("arrow_down", self.move, [1, 0]),
                              ("shift-arrow_left", self.move, [0, -1, True]), ("shift-arrow_right", self.move, [0, 1, True]),
                              ("shift-arrow_up", self.move, [-1, 0, True]), ("shift-arrow_down", self.move, [1, 0, True]),
                              ("home", self.move_to, [0]), ("end", self.move_to, [None]),
                              ("shift-home", self.move_to, [0, True]), ("shift-end", self.move_to, [None, True]),
                              ("tab", self.typed, ["    "]), ("shift-enter", self.new_line, []),
                              ("enter", self.new_line, [])):  # (Return makes a new line: CHANGE 88)
            self.accept(key, self.when_focused, [fn, args])
            self.accept(key + "-repeat", self.when_focused, [fn, args])
        for key, fn in (("control-c", self.copy), ("control-x", self.cut), ("control-v", self.paste),
                        ("control-a", self.select_all)):
            self.accept(key, self.when_focused, [fn, []])
        self.accept("mouse1-up", self.drag_end)
        self.blink = base.taskMgr.doMethodLater(0.5, self.blink_cursor, "code cursor")
        self.tidy()
        self.refresh()

    # ---------- where things are ----------
    def row_y(self, row):
        return self.top - self.scale * 1.25 - row * self.line_h

    def text_width(self, text):
        return self.measure.calcWidth(text) * self.scale

    @property
    def lines(self):
        return self.state["lines"]

    def text(self):
        return "\n".join(self.lines)

    def tidy(self):
        """Keep the cursor inside the text and the scroll position inside the box."""
        lines, cur = self.lines, self.state["cursor"]
        if not lines:
            lines.append("")
        cur[0] = max(0, min(len(lines) - 1, cur[0]))
        cur[1] = max(0, min(len(lines[cur[0]]), cur[1]))
        self.state["scroll"] = max(0, min(max(0, len(lines) - self.rows), self.state["scroll"]))

    def show_cursor(self):
        """Scroll so the cursor's line is in the box."""
        line = self.state["cursor"][0]
        if line < self.state["scroll"]:
            self.state["scroll"] = line
        elif line >= self.state["scroll"] + self.rows:
            self.state["scroll"] = line - self.rows + 1

    def hidden(self):
        """How many lines are above and below the box: (above, below)."""
        return self.state["scroll"], max(0, len(self.lines) - self.rows - self.state["scroll"])

    # ---------- drawing ----------
    def refresh(self):
        self.tidy()
        first, (line, col) = self.state["scroll"], self.state["cursor"]
        for i in range(self.rows):
            n = first + i
            if n < len(self.lines):
                self.numbers[i].setText(str(n + 1))
                self.numbers[i].setFg(GUTTER_CUR if n == line and not self.read_only else GUTTER)  # (CHANGE 143)
                text = self.lines[n][:self.cols]
                self.texts[i].setText(text if self.read_only else coloured(text))
            else:
                self.numbers[i].setText("")
                self.texts[i].setText("")
        sel = self.selection()  # (the selected text, highlighted on each row it covers: CHANGE 88)
        for i in range(self.rows):
            n = first + i
            if sel and n < len(self.lines) and sel[0][0] <= n <= sel[1][0]:
                text = self.lines[n][:self.cols]
                c0 = sel[0][1] if n == sel[0][0] else 0
                c1 = sel[1][1] if n == sel[1][0] else len(text) + 1
                x0, x1 = self.text_width(text[:c0]), self.text_width(text[:min(c1, len(text))]) + \
                    (self.text_width(" ") if c1 > len(text) else 0)
                self.sel_backs[i]["frameSize"] = (0, max(0.004, x1 - x0), -self.scale * 0.35, self.scale * 1.05)
                self.sel_backs[i].setPos(self.code_x + x0, 0, self.row_y(i))
                self.sel_backs[i].show()
            else:
                self.sel_backs[i].hide()
        row = line - first
        if not self.read_only and 0 <= row < self.rows:  # (the cursor's line: fainter while typing is elsewhere)
            y = self.row_y(row)
            self.line_back.setPos(self.x, 0, y)
            self.line_back.setAlphaScale(1.0 if self.focused else 0.5)
            self.line_back.show()
        else:
            self.line_back.hide()
        if self.focused and 0 <= row < self.rows:
            self.cursor.setPos(self.code_x + self.text_width(self.lines[line][:col]), 0, self.row_y(row))
            self.cursor.show()
        else:
            self.cursor.hide()
        self.show_brackets(None if sel or not self.focused else (line, col))
        if self.on_scroll:
            self.on_scroll()

    def show_brackets(self, at):
        """A bracket just before the cursor (or else just after it) and its partner, each in a soft box (CHANGE 143)."""
        for b in self.match_backs:
            b.hide()
        if at is None or self.read_only:
            return
        if self.pairs_of != self.lines:
            self.pairs, self.pairs_of = bracket_pairs(self.lines), list(self.lines)
        line, col = at
        a = (line, col - 1) if (line, col - 1) in self.pairs else (line, col) if (line, col) in self.pairs else None
        if a is None:
            return
        for box, (n, c) in zip(self.match_backs, (a, self.pairs[a])):
            row = n - self.state["scroll"]
            if 0 <= row < self.rows and c < self.cols:
                box.setPos(self.code_x + self.text_width(self.lines[n][:c]), 0, self.row_y(row))
                box.show()

    def blink_cursor(self, task):
        if self.focused and 0 <= self.state["cursor"][0] - self.state["scroll"] < self.rows:
            self.cursor.hide() if not self.cursor.isHidden() else self.cursor.show()
        return task.again

    # ---------- the mouse ----------
    def click(self, event):
        """Put the cursor where the mouse clicked: the nearest gap between two letters on that line."""
        if self.read_only:
            return
        m = event.getMouse()
        p = self.parent.getRelativePoint(self.base.render2d, Point3(m.getX(), 0, m.getY()))
        self.anchor = None
        self.place(p.x, p.z)
        self.focus()
        self.anchor = list(self.state["cursor"])  # dragging from here selects (CHANGE 88)
        self.dragging = True
        self.base.taskMgr.add(self.drag_task, "code drag select")

    def drag_task(self, task):
        if not self.dragging:
            return task.done
        mw = self.base.mouseWatcherNode
        if mw is not None and mw.hasMouse():
            p = self.parent.getRelativePoint(self.base.render2d, Point3(mw.getMouseX(), 0, mw.getMouseY()))
            self.place(p.x, p.z)
        return task.cont

    def drag_end(self):
        if self.dragging:
            self.dragging = False
            if self.anchor == list(self.state["cursor"]):
                self.anchor = None
                self.refresh()

    # ---------- the selection (CHANGE 88) ----------
    def selection(self):
        """((line, col), (line, col)) from the first end to the last, or None."""
        if self.anchor is None or self.anchor == list(self.state["cursor"]):
            return None
        a, b = tuple(self.anchor), tuple(self.state["cursor"])
        return (a, b) if a < b else (b, a)

    def selected_text(self):
        sel = self.selection()
        if not sel:
            return ""
        (l0, c0), (l1, c1) = sel
        if l0 == l1:
            return self.lines[l0][c0:c1]
        return "\n".join([self.lines[l0][c0:]] + self.lines[l0 + 1:l1] + [self.lines[l1][:c1]])

    def delete_selection(self):
        """The selected text goes; the cursor lands where it started. Returns True if anything went."""
        sel = self.selection()
        if not sel:
            return False
        (l0, c0), (l1, c1) = sel
        self.lines[l0:l1 + 1] = [self.lines[l0][:c0] + self.lines[l1][c1:]]
        self.state["cursor"][:] = [l0, c0]
        self.anchor = None
        return True

    def select_all(self):
        self.anchor = [0, 0]
        self.state["cursor"][:] = [len(self.lines) - 1, len(self.lines[-1])]
        self.refresh()

    def copy(self):
        text = self.selected_text()
        if text:
            clipboard_set(text)

    def cut(self):
        self.copy()
        if self.delete_selection():
            self.changed()

    def paste(self):
        text = clipboard_get().replace("\r\n", "\n").replace("\r", "\n")
        if not text:
            return
        self.delete_selection()
        line, col = self.state["cursor"]
        parts = [clean(p) for p in text.split("\n")][:MAX_LINES]
        if len(self.lines) + len(parts) - 1 > MAX_LINES:
            parts = parts[:max(1, MAX_LINES - len(self.lines) + 1)]
        before, after = self.lines[line][:col], self.lines[line][col:]
        parts[0] = (before + parts[0])[:MAX_LENGTH]
        parts[-1] = (parts[-1] + after)[:MAX_LENGTH] if len(parts) > 1 else parts[0]
        if len(parts) == 1:
            parts[0] = (before + clean(text) + after)[:MAX_LENGTH]
            end_col = min(len(parts[0]), len(before) + len(clean(text)))
        else:
            end_col = len(parts[-1]) - len(after)
        self.lines[line:line + 1] = parts
        self.state["cursor"][:] = [line + len(parts) - 1, max(0, end_col)]
        self.changed()

    def place(self, x, y):
        row = int((self.top - self.scale * 0.3 - y) / self.line_h)
        line = max(0, min(len(self.lines) - 1, self.state["scroll"] + max(0, min(self.rows - 1, row))))
        text, want = self.lines[line], x - self.code_x
        col = min(range(len(text) + 1), key=lambda c: abs(self.text_width(text[:c]) - want))
        self.state["cursor"][:] = [line, col]
        self.refresh()

    def wheel(self, lines):
        self.state["scroll"] += lines
        self.refresh()

    # ---------- the keyboard ----------
    def focus(self):
        if not self.focused:
            self.focused = True
            if self.on_focus:
                self.on_focus()
        self.refresh()

    def blur(self):
        self.focused = False
        self.refresh()

    def when_focused(self, fn, args):
        if self.focused:
            fn(*args)

    def changed(self):
        self.show_cursor()
        self.refresh()

    def typed(self, key):
        if not self.focused:
            return
        key = clean(key)
        if key and self.delete_selection():  # (typing over a selection replaces it: CHANGE 88)
            pass
        line, col = self.state["cursor"]
        if key and len(self.lines[line]) + len(key) <= MAX_LENGTH:
            self.lines[line] = self.lines[line][:col] + key + self.lines[line][col:]
            self.state["cursor"][1] = col + len(key)
            self.changed()

    def erase(self, back):
        """Backspace (back = -1) or Delete (0): at the end of a line they join it to the next one. With a
        selection, either deletes the selection (CHANGE 88)."""
        if self.delete_selection():
            self.changed()
            return
        lines, (line, col) = self.lines, self.state["cursor"]
        if back and col == 0:
            if line == 0:
                return
            line, col = line - 1, len(lines[line - 1])
        elif back:
            col -= 1
        if col < len(lines[line]):
            lines[line] = lines[line][:col] + lines[line][col + 1:]
        elif line + 1 < len(lines) and len(lines[line]) + len(lines[line + 1]) <= MAX_LENGTH:
            lines[line] += lines.pop(line + 1)
        self.state["cursor"][:] = [line, col]
        self.changed()

    def new_line(self):
        self.delete_selection()
        lines, (line, col) = self.lines, self.state["cursor"]
        if len(lines) < MAX_LINES:
            indent = len(lines[line]) - len(lines[line].lstrip(" "))
            lines[line:line + 1] = [lines[line][:col], " " * min(indent, col) + lines[line][col:]]
            self.state["cursor"][:] = [line + 1, min(indent, col)]
            self.changed()

    def move(self, down, right, select=False):
        """The arrow keys; with Shift they extend the selection from where it started (CHANGE 88)."""
        if select and self.anchor is None:
            self.anchor = list(self.state["cursor"])
        elif not select:
            self.anchor = None
        lines, (line, col) = self.lines, self.state["cursor"]
        if down:
            line = max(0, min(len(lines) - 1, line + down))
            col = min(col, len(lines[line]))
        elif right > 0 and col == len(lines[line]) and line + 1 < len(lines):
            line, col = line + 1, 0
        elif right < 0 and col == 0 and line > 0:
            line, col = line - 1, len(lines[line - 1])
        else:
            col = max(0, min(len(lines[line]), col + right))
        self.state["cursor"][:] = [line, col]
        self.changed()

    def move_to(self, col, select=False):
        """Home (0) or End (None); with Shift, selecting."""
        if select and self.anchor is None:
            self.anchor = list(self.state["cursor"])
        elif not select:
            self.anchor = None
        line = self.state["cursor"][0]
        self.state["cursor"][1] = len(self.lines[line]) if col is None else col
        self.changed()

    def enter(self):
        if self.on_enter:
            self.on_enter()

    def destroy(self):
        self.ignoreAll()
        if self.blink is not None:
            self.base.taskMgr.remove(self.blink)
        for node in [self.edge, self.back, self.gutter_edge, self.line_back, self.cursor] + self.match_backs + \
                self.sel_backs + self.numbers + self.texts:
            node.destroy()


class TextBox(DirectObject):
    """A multi-line text box: prose that wraps at the box's edge, any length (it scrolls), the cursor placed by a
    click, text selected by dragging or Shift with the arrows, Ctrl+C, X, V and A, Return for a new paragraph.
    text: the words; on_change(text) is called after every edit; on_focus(key) / on_blur(key) tell the window
    which box is being typed in (its game keys rest meanwhile)."""

    def __init__(self, base, parent, key, x, top, width, rows, text="", scale=0.024, on_change=None, on_focus=None,
                 on_blur=None, max_length=20000):
        DirectObject.__init__(self)
        self.base, self.parent, self.key = base, parent, key
        self.x, self.top, self.width, self.rows, self.scale = x, top, width, rows, scale
        self.on_change, self.on_focus, self.on_blur, self.max_length = on_change, on_focus, on_blur, max_length
        self.text = clean_text(text)
        self.cursor, self.anchor, self.scroll = len(self.text), None, 0
        self.focused, self.dragging = False, False
        self.line_h = scale * 1.5
        self.measure = TextNode("measure")
        self.pad = scale * 0.4
        height = rows * self.line_h + self.pad * 2
        self.back = DirectFrame(parent=parent, frameColor=BOX_BACK, frameSize=(x, x + width, top - height, top),
                                state=DGG.NORMAL)
        self.back.bind(DGG.B1PRESS, self.click)
        self.cursor_bar = DirectFrame(parent=parent, frameColor=BOX_CURSOR,
                                      frameSize=(0, scale * 0.08, -scale * 0.3, scale * 1.0))
        self.sel_backs = [DirectFrame(parent=parent, frameColor=(0.25, 0.4, 0.7, 0.55),
                                      frameSize=(0, 0.01, -scale * 0.3, scale * 1.0)) for _ in range(rows)]
        self.texts = [OnscreenText("", pos=(x + self.pad, self.row_y(i)), scale=scale, fg=BOX_TEXT,
                                   align=TextNode.ALeft, parent=parent, mayChange=True) for i in range(rows)]
        self.more = OnscreenText("", pos=(x + width - self.pad, top - height + self.pad * 0.6), scale=scale * 0.7,
                                 fg=GUTTER, align=TextNode.ARight, parent=parent, mayChange=True)
        for b in self.sel_backs:
            b.hide()
        self.cursor_bar.hide()
        if getattr(base, "buttonThrowers", None):  # (letters arrive as "keystroke" events only once this is set:
            base.buttonThrowers[0].node().setKeystrokeEvent("keystroke")  # the code editor used to be the only one to)
        self.accept("keystroke", self.typed)
        for key_, fn, args in (("backspace", self.erase, [-1]), ("delete", self.erase, [0]),
                               ("arrow_left", self.move, [-1, False]), ("arrow_right", self.move, [1, False]),
                               ("shift-arrow_left", self.move, [-1, True]), ("shift-arrow_right", self.move, [1, True]),
                               ("arrow_up", self.move_row, [-1, False]), ("arrow_down", self.move_row, [1, False]),
                               ("shift-arrow_up", self.move_row, [-1, True]), ("shift-arrow_down", self.move_row, [1, True]),
                               ("home", self.move_end, [-1, False]), ("end", self.move_end, [1, False]),
                               ("shift-home", self.move_end, [-1, True]), ("shift-end", self.move_end, [1, True]),
                               ("enter", self.typed, ["\n"]), ("shift-enter", self.typed, ["\n"]),
                               ("tab", self.typed, ["    "])):
            self.accept(key_, self.when_focused, [fn, args])
            self.accept(key_ + "-repeat", self.when_focused, [fn, args])
        for key_, fn in (("control-c", self.copy), ("control-x", self.cut), ("control-v", self.paste),
                         ("control-a", self.select_all)):
            self.accept(key_, self.when_focused, [fn, []])
        self.accept("mouse1-up", self.drag_end)
        self.accept("wheel_up", self.when_over, [self.wheel, [-1]])
        self.accept("wheel_down", self.when_over, [self.wheel, [1]])
        self.refresh()

    # ---------- geometry ----------
    def row_y(self, i):
        return self.top - self.pad - self.line_h * (i + 1) + self.scale * 0.35

    def text_width(self, text):
        return self.measure.calcWidth(text) * self.scale

    def wrapped(self):
        """The text as rows: [(start index, row text)], each paragraph wrapped at the box's edge."""
        limit = self.width - self.pad * 2 - self.scale * 0.3
        rows, i = [], 0
        for para in self.text.split("\n"):
            start = i
            words, line, line_start = para.split(" "), "", i
            if para == "":
                rows.append((i, ""))
            else:
                line = ""
                for w in words:
                    trial = w if line == "" else line + " " + w
                    if line != "" and self.text_width(trial) > limit:
                        rows.append((line_start, line))
                        line_start += len(line) + 1
                        line = w
                    else:
                        line = trial
                    while self.text_width(line) > limit and len(line) > 1:  # (one word wider than the box)
                        cut = max(1, int(len(line) * limit / self.text_width(line)))
                        rows.append((line_start, line[:cut]))
                        line_start += cut
                        line = line[cut:]
                rows.append((line_start, line))
            i = start + len(para) + 1
        return rows

    def row_of(self, index, rows):
        for n, (start, text) in enumerate(rows):
            if start <= index <= start + len(text):
                if n + 1 < len(rows) and rows[n + 1][0] == index and not (n < len(rows) and rows[n][0] + len(text) < index):
                    pass
                return n
        return len(rows) - 1

    # ---------- drawing ----------
    def refresh(self):
        rows = self.wrapped()
        self.cursor = max(0, min(len(self.text), self.cursor))
        cur_row = self.row_of(self.cursor, rows)
        if self.focused:  # keep the cursor's row in view
            if cur_row < self.scroll:
                self.scroll = cur_row
            elif cur_row >= self.scroll + self.rows:
                self.scroll = cur_row - self.rows + 1
        self.scroll = max(0, min(max(0, len(rows) - self.rows), self.scroll))
        sel = self.selection()
        for i in range(self.rows):
            n = self.scroll + i
            if n < len(rows):
                start, text = rows[n]
                self.texts[i].setText(text)
                if sel and sel[0] < start + len(text) + 1 and sel[1] > start:
                    a, b = max(sel[0], start), min(sel[1], start + len(text) + (1 if n + 1 < len(rows) else 0))
                    x0 = self.text_width(text[:a - start])
                    x1 = self.text_width(text[:min(b - start, len(text))]) + (self.text_width(" ") if b - start > len(text) else 0)
                    self.sel_backs[i]["frameSize"] = (0, max(0.004, x1 - x0), -self.scale * 0.3, self.scale * 1.0)
                    self.sel_backs[i].setPos(self.x + self.pad + x0, 0, self.row_y(i))
                    self.sel_backs[i].show()
                else:
                    self.sel_backs[i].hide()
            else:
                self.texts[i].setText("")
                self.sel_backs[i].hide()
        hidden = len(rows) - self.rows
        self.more.setText(f"{len(rows) - self.scroll - self.rows} more below" if hidden > 0 and self.scroll < hidden
                          else (f"{self.scroll} more above" if self.scroll > 0 else ""))
        row = cur_row - self.scroll
        if self.focused and 0 <= row < self.rows:
            start, text = rows[cur_row]
            self.cursor_bar.setPos(self.x + self.pad + self.text_width(text[:self.cursor - start]), 0, self.row_y(row))
            self.cursor_bar.show()
        else:
            self.cursor_bar.hide()

    # ---------- the mouse ----------
    def mouse_index(self):
        mw = self.base.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return None
        p = self.parent.getRelativePoint(self.base.render2d, Point3(mw.getMouseX(), 0, mw.getMouseY()))
        rows = self.wrapped()
        row = int((self.top - self.pad - p.z) / self.line_h)
        n = max(0, min(len(rows) - 1, self.scroll + max(0, min(self.rows - 1, row))))
        start, text = rows[n]
        want = p.x - self.x - self.pad
        col = min(range(len(text) + 1), key=lambda c: abs(self.text_width(text[:c]) - want))
        return start + col

    def over(self):
        mw = self.base.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return False
        p = self.parent.getRelativePoint(self.base.render2d, Point3(mw.getMouseX(), 0, mw.getMouseY()))
        fs = self.back["frameSize"]
        return fs[0] <= p.x <= fs[1] and fs[2] <= p.z <= fs[3]

    def when_over(self, fn, args):
        if self.over():
            fn(*args)

    def click(self, event=None):
        i = self.mouse_index()
        if i is None:
            return
        self.focus()
        self.cursor, self.anchor = i, i
        self.dragging = True
        self.base.taskMgr.add(self.drag_task, f"textbox drag {self.key}")
        self.refresh()

    def drag_task(self, task):
        if not self.dragging:
            return task.done
        i = self.mouse_index()
        if i is not None and i != self.cursor:
            self.cursor = i
            self.refresh()
        return task.cont

    def drag_end(self):
        if self.dragging:
            self.dragging = False
            if self.anchor == self.cursor:
                self.anchor = None
            self.refresh()

    def wheel(self, step):
        self.scroll += step
        self.refresh()

    # ---------- focus ----------
    def focus(self):
        if not self.focused:
            self.focused = True
            if self.on_focus:
                self.on_focus(self.key)
        self.refresh()

    def blur(self):
        if self.focused:
            self.focused = False
            self.anchor = None
            if self.on_blur:
                self.on_blur(self.key)
            self.refresh()

    def when_focused(self, fn, args):
        if self.focused:
            fn(*args)

    # ---------- the selection ----------
    def selection(self):
        if self.anchor is None or self.anchor == self.cursor:
            return None
        return (min(self.anchor, self.cursor), max(self.anchor, self.cursor))

    def selected_text(self):
        sel = self.selection()
        return self.text[sel[0]:sel[1]] if sel else ""

    def delete_selection(self):
        sel = self.selection()
        if not sel:
            return False
        self.text = self.text[:sel[0]] + self.text[sel[1]:]
        self.cursor, self.anchor = sel[0], None
        return True

    def select_all(self):
        self.anchor, self.cursor = 0, len(self.text)
        self.refresh()

    def copy(self):
        if self.selected_text():
            clipboard_set(self.selected_text())

    def cut(self):
        self.copy()
        if self.delete_selection():
            self.changed()

    def paste(self):
        text = clean_text(clipboard_get())
        if not text:
            return
        self.delete_selection()
        self.insert(text)

    # ---------- editing ----------
    def changed(self):
        self.refresh()
        if self.on_change:
            self.on_change(self.text)

    def insert(self, text):
        room = self.max_length - len(self.text)
        text = text[:max(0, room)]
        if not text:
            return
        self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
        self.cursor += len(text)
        self.anchor = None
        self.changed()

    def typed(self, key):
        if not self.focused:
            return
        key = clean_text(key)
        if not key:
            return
        self.delete_selection()
        self.insert(key)

    def erase(self, back):
        if self.delete_selection():
            self.changed()
            return
        if back and self.cursor > 0:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1
        elif not back and self.cursor < len(self.text):
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        self.changed()

    def start_select(self, select):
        if select and self.anchor is None:
            self.anchor = self.cursor
        elif not select:
            self.anchor = None

    def move(self, step, select):
        self.start_select(select)
        self.cursor = max(0, min(len(self.text), self.cursor + step))
        self.refresh()

    def move_row(self, step, select):
        self.start_select(select)
        rows = self.wrapped()
        n = self.row_of(self.cursor, rows)
        start, text = rows[n]
        x = self.text_width(text[:self.cursor - start])
        m = max(0, min(len(rows) - 1, n + step))
        if m == n:
            self.cursor = 0 if step < 0 else len(self.text)
        else:
            s2, t2 = rows[m]
            col = min(range(len(t2) + 1), key=lambda c: abs(self.text_width(t2[:c]) - x))
            self.cursor = s2 + col
        self.refresh()

    def move_end(self, step, select):
        self.start_select(select)
        rows = self.wrapped()
        start, text = rows[self.row_of(self.cursor, rows)]
        self.cursor = start if step < 0 else start + len(text)
        self.refresh()

    # ---------- for the window ----------
    def get(self):
        return self.text

    def set(self, text):
        self.text = clean_text(text)
        self.cursor, self.anchor = min(self.cursor, len(self.text)), None
        self.refresh()

    def destroy(self):
        self.ignoreAll()
        self.dragging = False
        for n in [self.back, self.cursor_bar, self.more] + self.sel_backs + self.texts:
            try:
                n.destroy()
            except Exception:
                try:
                    n.removeNode()
                except Exception:
                    pass


def clean_text(text):
    """Prose as a text box keeps it: no tabs or control characters, but new lines stay."""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    return "".join(ch for ch in text if ch >= " " or ch == "\n")
