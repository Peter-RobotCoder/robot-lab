"""A small code editor for the game's windows, drawn with Panda3D text (a DirectEntry can't do any of this).

    click anywhere in the code to put the cursor there, then type
    the words are coloured as an IDE colours Python: keywords, strings, numbers, comments, names, brackets
    code that is too long for its box scrolls (mouse wheel, or move the cursor): the buttons under it stay put

Keys while typing: arrows, Home, End, Backspace, Delete, Tab (4 spaces), Enter (the window decides: Robot Lab
applies the code), Shift+Enter (a new line).

The text, cursor and scroll position live in a plain dictionary the window keeps ({"lines", "cursor", "scroll"}),
so the editor can be drawn again (when its panel is redrawn) without losing anything.
"""
import keyword
import os
import re

from direct.gui.DirectGui import DGG, DirectFrame
from direct.gui.OnscreenText import OnscreenText
from direct.showbase.DirectObject import DirectObject
from panda3d.core import (Filename, MouseButton, PGButton, Point3, TextNode, TextProperties,
                          TextPropertiesManager)

WHEEL_UP = PGButton.getPressPrefix() + MouseButton.wheelUp().getName() + "-"  # (the mouse wheel over a panel)
WHEEL_DOWN = PGButton.getPressPrefix() + MouseButton.wheelDown().getName() + "-"

# the colours of Visual Studio's dark theme
DARK_COLOURS = {"keyword": (0.34, 0.61, 0.84), "string": (0.81, 0.57, 0.47), "number": (0.71, 0.81, 0.66),
                "comment": (0.42, 0.60, 0.33), "name": (0.61, 0.86, 1.0), "bracket": (1.0, 0.84, 0.0),
                "other": (0.83, 0.83, 0.83)}
LIGHT_COLOURS = {"keyword": (0.0, 0.0, 0.75), "string": (0.63, 0.13, 0.1), "number": (0.05, 0.5, 0.1),
                 "comment": (0.0, 0.5, 0.0), "name": (0.0, 0.1, 0.4), "bracket": (0.6, 0.35, 0.0),
                 "other": (0.15, 0.15, 0.15)}
DARK_BACK = ((0.118, 0.118, 0.118, 1), (0.17, 0.17, 0.19, 1), (0.52, 0.52, 0.52, 1), (1, 1, 1, 1))
LIGHT_BACK = ((1, 1, 1, 1), (0.93, 0.94, 0.97, 1), (0.55, 0.55, 0.6, 1), (0.1, 0.1, 0.1, 1))
COLOURS = dict(DARK_COLOURS)
BACK, LINE_BACK, GUTTER, CURSOR = DARK_BACK


def set_theme(name):
    """The dark or the light look for code drawn after this (the window redraws its code panel)."""
    global BACK, LINE_BACK, GUTTER, CURSOR
    light = name == "light"
    COLOURS.clear()
    COLOURS.update(LIGHT_COLOURS if light else DARK_COLOURS)
    BACK, LINE_BACK, GUTTER, CURSOR = LIGHT_BACK if light else DARK_BACK
    styles()
TOKEN = re.compile(r"""(?P<comment>\#.*)
                     |(?P<string>"(?:[^"\\]|\\.)*"?|'(?:[^'\\]|\\.)*'?)
                     |(?P<number>\b\d+(?:\.\d+)?\b)
                     |(?P<name>[A-Za-z_]\w*)
                     |(?P<bracket>[\[\]{}()])
                     |(?P<other>\s+|.)""", re.VERBOSE)
MAX_LINES, MAX_LENGTH = 80, 110
FONTS = ("consola.ttf", "cour.ttf", "lucon.ttf")  # a font with every letter the same width (Windows has these)
_font = [None, False]  # the font, and whether we've looked for it


def code_font(base):
    """A fixed-width font for code, or None (Panda3D's own font) if this computer has none of ours."""
    if not _font[1]:
        _font[1] = True
        folder = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        for name in FONTS:
            path = os.path.realpath(os.path.join(folder, name))  # (its true capitals: Panda3D is fussy about them)
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
    for kind, (r, g, b) in COLOURS.items():
        props = TextProperties()
        props.setTextColor(r, g, b, 1)
        mgr.setProperties("code_" + kind, props)


def tokens(line):
    """A line of Python as (kind, text) pieces: keyword, string, number, comment, name, bracket or other."""
    out = []
    for m in TOKEN.finditer(line):
        kind = m.lastgroup
        if kind == "name" and keyword.iskeyword(m.group()):
            kind = "keyword"
        out.append((kind, m.group()))
    return out


def coloured(line):
    """The line with each piece marked with its style (\\1style\\1 text \\2 is Panda3D's way of writing that)."""
    return "".join(text if not text.strip() else f"\1code_{kind}\1{text}\2" for kind, text in tokens(line))


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
        self.back = DirectFrame(parent=parent, frameColor=BACK, frameSize=(x, x + width, top - height, top),
                                state=DGG.NORMAL)
        self.back.bind(DGG.B1PRESS, self.click)
        self.back.bind(WHEEL_UP, lambda e: self.wheel(3 if getattr(base, "invert_scroll", False) else -3))
        self.back.bind(WHEEL_DOWN, lambda e: self.wheel(-3 if getattr(base, "invert_scroll", False) else 3))
        self.line_back = DirectFrame(parent=parent, frameColor=LINE_BACK, frameSize=(0, width, -scale * 0.45,
                                                                                    self.line_h - scale * 0.45))
        self.cursor = DirectFrame(parent=parent, frameColor=CURSOR,
                                  frameSize=(0, scale * 0.09, -scale * 0.35, scale * 1.05))
        self.anchor = None  # the other end of the selection (CHANGE 88), [line, col], or None
        self.dragging = False
        self.sel_backs = [DirectFrame(parent=parent, frameColor=(0.25, 0.4, 0.7, 0.55),
                                      frameSize=(0, 0.01, -scale * 0.35, scale * 1.05)) for _ in range(rows)]
        for b in self.sel_backs:
            b.hide()
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
        if self.focused and 0 <= row < self.rows:
            y = self.row_y(row)
            self.line_back.setPos(self.x, 0, y)
            self.cursor.setPos(self.code_x + self.text_width(self.lines[line][:col]), 0, y)
            self.line_back.show()
            self.cursor.show()
        else:
            self.line_back.hide()
            self.cursor.hide()
        if self.on_scroll:
            self.on_scroll()

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
        for node in [self.back, self.line_back, self.cursor] + self.numbers + self.texts:
            node.destroy()
