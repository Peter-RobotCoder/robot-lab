"""The HUD kit: what every Club Coders game's window shares (the engine's, since 6 October 2026).

The panels' colours (a dark look and a light one), the text sizes, the words that explain themselves (hover tips),
the drawing helpers (label, word, button, check, text boxes), the side panel with its fixed header, scrolling
body and scroll bar, the Settings tab, this computer's settings file, and the code panel's moving and resizing.

A game's window inherits HudKit (with ShowBase) and calls setup() once, naming its settings folder and the modules
whose colour names should follow the look. Tabs and sections a game or a user mod adds are registered with
add_tab(), never written into this file.
"""
import json
import os

from direct.gui.DirectGui import DGG, DirectButton, DirectCheckButton, DirectEntry, DirectFrame, DirectLabel
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import MouseButton, TextNode

from engine import editor

APP = None  # the window (so any button click can end typing in a text box): set by setup_app
THEMED = [__import__(__name__)]  # modules whose colour names are swapped by set_theme (this one, and the games')


def setup_app(app):
    global APP
    APP = app


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


SETTINGS_DIR = None  # set by the game (setup): where this computer's settings.json lives
SETTINGS = {}        # this computer's settings: the code, the text size, the look, the wheel


def setup(settings_dir, *themed_modules):
    """Called once by a game's window: where this computer's settings live, and the modules whose colour names
    follow the look (the game's own module: its WHITE, YELLOW... are swapped when the look changes)."""
    global SETTINGS_DIR
    SETTINGS_DIR = settings_dir
    SETTINGS.update(load_json(os.path.join(settings_dir, "settings.json")))
    for m in themed_modules:
        if m not in THEMED:
            THEMED.append(m)
    set_theme(SETTINGS.get("theme", "dark"))  # (this computer's last choice, for the login screen on)
    return SETTINGS


def remember(key, value):
    """Keep a setting (the class code, the text size, the look) on this computer."""
    path = os.path.join(SETTINGS_DIR, "settings.json")
    data = load_json(path) | {key: value}
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


# The panels' colours: a dark look and a light one (CHANGE 57). set_theme swaps the names below; the HUD over the
# arena (the health bars, the key list, the banners) is always the dark look.
DARK = {"YELLOW": (1, .9, .35, 1), "WHITE": (1, 1, 1, 1), "GREY": (.75, .8, .9, 1), "RED": (1, .45, .4, 1),
        "GREEN": (.5, .95, .55, 1), "BLUE": (.55, .85, 1, 1), "ORANGE": (1, .7, .3, 1),
        "PANEL": (0.04, 0.05, 0.08, 0.88), "ON": (0.85, 0.65, 0.1, 1), "OFF": (0.2, 0.25, 0.35, 1),
        "BOX": (0.15, 0.17, 0.22, 1), "HANDLE": (0.1, 0.12, 0.18, 0.95)}
LIGHT = {"YELLOW": (0.55, 0.4, 0.0, 1), "WHITE": (0.08, 0.09, 0.12, 1), "GREY": (0.33, 0.36, 0.42, 1),
         "RED": (0.75, 0.12, 0.08, 1), "GREEN": (0.05, 0.45, 0.15, 1), "BLUE": (0.1, 0.33, 0.62, 1),
         "ORANGE": (0.72, 0.38, 0.0, 1), "PANEL": (0.92, 0.93, 0.95, 0.94), "ON": (0.95, 0.75, 0.2, 1),
         "OFF": (0.76, 0.79, 0.85, 1), "BOX": (1, 1, 1, 1), "HANDLE": (0.8, 0.82, 0.86, 0.95)}
YELLOW, WHITE, GREY, RED, GREEN, BLUE, ORANGE, PANEL, ON, OFF, BOX, HANDLE = (DARK[k] for k in DARK)
THEME = "dark"
TEXT_SIZES = {"small": 0.85, "medium": 1.0, "large": 1.3, "xlarge": 1.6}  # the side panel and the code (CHANGE 40)


def set_theme(name):
    """The dark or the light look, for everything drawn after this (the panels are redrawn by the caller)."""
    global THEME
    THEME = "light" if name == "light" else "dark"
    for module in THEMED:
        module.__dict__.update(LIGHT if THEME == "light" else DARK)
    editor.set_theme(THEME)





SWATCHES = [(220, 60, 50), (240, 140, 30), (240, 200, 40), (60, 190, 90), (60, 130, 230), (180, 90, 230),
            (230, 90, 170), (230, 230, 230)]  # (the reds on the left, the greens in the middle, the blues on the right,
#                                              white last: CHANGE 48)
# The HUD explains its words (CHANGE 44 and 45): hovering over a word drawn with word() shows its tip. The simplest
# description of each that we could find; the teacher approves the wording.
TIPS = {
    "HUD": "Heads Up Display: the information and controls drawn over the top of the game, so you can see them "
           "while you play.",
    "GUI": "Graphical User Interface: a nice graphical way to talk to a computer, with buttons, boxes and sliders "
           "instead of typed commands.",
    "VARIABLE": "A variable is a name that holds a value. Change the value and the program behaves differently.",
    "STRING": "A string is text: letters, digits, spaces and symbols, in quotes. \"Richy\" is a string. "
              "Its type is str.",
    "INTEGER": "An integer is a whole number: 0, 25, 100 or -3, with no decimal point. Its type is int.",
    "LIST": "A list holds several values in order, in square brackets: [220, 60, 50]. Its type is list.",
    "str": "str: the string type. A string is text, made of chars. A char is one character from the ASCII set of "
           "characters: a letter, a digit, a space or a symbol.",
    "int": "int: the integer type. An integer is a whole number.",
    "list": "list: the list type. A list holds values in order, in square brackets.",
    "NAME": "The variable's name: how the code refers to it. In Python, lower-case words joined with _",
    "VALUE": "What the variable holds right now. The GUI changes it here; the code changes it with  name = value",
    "TYPE": "The type says what kind of value the variable holds: str (text), int (a whole number) or list.",
    "RGB": "The colour is a list of three integers: [red, green, blue], each from 0 (none) to 255 (full).",
    "PERCENT": "Each setting is a percentage: 100 is the standard robot, 50 is half of it.",
    "POINTS": "The points are shared out: raising one means lowering another (every choice is a trade-off).",
}

# Tabs and sections a game or a user mod adds to the HUD (registered, never edited into the engine)
EXTRA_TABS = []  # (key, text, builder(window, frame, y), for: "learner", "teacher" or "both")


def add_tab(key, text, builder, for_="both"):
    """A game, or a user mod in a game's folder, adds a tab to the side panel: builder(window, frame, y) draws it."""
    EXTRA_TABS[:] = [t for t in EXTRA_TABS if t[0] != key] + [(key, text, builder, for_)]


def extra_tabs(teacher):
    return [(k, t) for k, t, _, f in EXTRA_TABS if f == "both" or f == ("teacher" if teacher else "learner")]


def extra_builder(key):
    return next((b for k, _, b, _ in EXTRA_TABS if k == key), None)


def label(parent, text, x, y, scale=0.036, fg=None, align=TextNode.ALeft, wrap=None):
    return OnscreenText(text, pos=(x, y), scale=scale, fg=fg or WHITE, align=align, parent=parent, mayChange=True,
                        wordwrap=wrap)


def word(parent, text, x, y, scale=0.03, fg=None, tip=None, align=TextNode.ALeft):
    """A label that explains itself: while the mouse is over it, its tip (a key of TIPS, or its own words) shows
    beside the mouse (CHANGE 44 and 45)."""
    if not tip:
        return label(parent, text, x, y, scale, fg, align)
    w = DirectLabel(parent=parent, text=text, scale=scale, pos=(x, 0, y), text_fg=fg or WHITE, text_align=align,
                    frameColor=(0, 0, 0, 0), relief=DGG.FLAT, pad=(0.1, 0.1), state=DGG.NORMAL)
    w.bind(DGG.WITHIN, lambda e: APP is not None and APP.show_tip(TIPS.get(tip, tip)))
    w.bind(DGG.WITHOUT, lambda e: APP is not None and APP.hide_tip())
    return w


def text_button(parent, text, x, y, command, args_=None, scale=0.03, fg=None):
    """Words that can be clicked (no box round them): an objective's title opens its guidance (CHANGE 53)."""
    def clicked(*a):
        if APP is not None:
            APP.stop_typing()
        command(*a)
    return DirectButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), command=clicked, extraArgs=args_ or [],
                        frameColor=(0, 0, 0, 0), text_fg=fg or WHITE, text_align=TextNode.ALeft, relief=DGG.FLAT,
                        pad=(0.1, 0.1))


def button(parent, text, x, y, command, args_=None, scale=0.036, colour=None):
    def clicked(*a):  # pressing a button ends typing, so the panel can redraw with the result
        if APP is not None:
            APP.stop_typing()
        command(*a)
    return DirectButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), command=clicked, extraArgs=args_ or [],
                        frameColor=colour or OFF, text_fg=WHITE, relief=DGG.FLAT, pad=(0.3, 0.15))


def check(parent, text, x, y, value, command, scale=0.032, fg=None):
    box = DirectCheckButton(parent=parent, text=text, scale=scale, pos=(x, 0, y), indicatorValue=1 if value else 0,
                            command=command, text_align=TextNode.ALeft, text_fg=fg or WHITE, frameColor=(0, 0, 0, 0),
                            boxPlacement="left")
    left, right, bottom, top = box.bounds  # a gap between the box and its text: Panda3D puts the box hard against
    box["frameSize"] = (left - 0.35, right, bottom, top)  # the first letter (a space in the text doesn't help)
    return box


class HudKit:
    """The side panel, settings and code panel mechanics a game's window inherits. The game sets: teacher (bool),
    CODE_PANEL and CODE_ROWS (its code panel's first place and size), and draws its own tabs."""
    teacher = False
    CODE_PANEL = (-0.86, 0.01, -0.85, 0.36)  # the code panel in its first place: left, right, bottom, top
    CODE_ROWS = 19                           # lines of code it shows at once (longer code scrolls)

    def init_hud(self):
        """Called once by the game's window, before any panel is drawn."""
        self.panel = self.panel_body = self.code_panel = None
        self.panel_bar, self.panel_drag, self.last_aspect = [], None, None
        self.head_bottom = 0.875
        self.tip = None  # the description of the word the mouse is over (CHANGE 44 and 45)
        self.text_size = SETTINGS.get("text_size") if SETTINGS.get("text_size") in TEXT_SIZES else "medium"
        self.panel_scroll = 0.0  # how far a side panel taller than the screen has been slid up (CHANGE 40)
        self.invert_scroll = bool(SETTINGS.get("invert_scroll"))  # the mouse wheel the other way up (Settings)
        self.invert_zoom = bool(SETTINGS.get("invert_zoom"))      # ...and for the camera's zoom, its own switch
        self.entries, self.entry_text, self.typing = {}, {}, None  # text boxes on screen, what they held, which has the keyboard
        self.code_editor = None
        self.code_at, self.code_drag = [0.0, 0.0], None  # how far the code panel has been dragged from its first place
        self.code_size, self.code_resize = [0.0, 0.0], None  # ...and how much wider and taller it has been made (CHANGE 60)

    def draw_header(self, f, tabs, open_tab, current, tab_text=None):
        """The side panel's fixed top: the learner's "HUD / GUI" words and the tab buttons (the teacher's in two
        rows). Returns the body node the tab's own drawing goes into, and the y it starts at."""
        teacher = self.teacher
        left, width = (0.8, 0.95) if teacher else (0.84, 0.9)
        across = (len(tabs) + 1) // 2 if teacher else len(tabs)  # (the teacher has too many tabs for one row)
        if not teacher:  # the learner's panel says what it is, and each word explains itself (CHANGE 44)
            word(f, "HUD", 0.81, 0.937, 0.036, YELLOW, "HUD")
            label(f, "/", 0.905, 0.937, 0.036, GREY)
            word(f, "GUI", 0.935, 0.937, 0.036, YELLOW, "GUI")
            label(f, "hover over a word in capitals\nto see what it means", 1.74, 0.952, 0.017, GREY,
                  TextNode.ARight)
        for i, (key, text) in enumerate(tabs):
            b = button(f, tab_text(key, text) if tab_text else text, left + (i % across + 0.5) * (width / across),
                       (0.94 - (i // across) * 0.047) if teacher else 0.9, open_tab, [key],
                       0.024 if teacher else 0.022, ON if key == current else OFF)
            b["sortOrder"] = 10  # (above anything in the body that has slid up under the header)
        self.head_bottom = 0.865 if teacher else 0.875  # (the body shows below here; the header stays put)
        self.panel_body = self.panel.attachNewNode("body")
        return self.panel_body, 0.84 if teacher else 0.83

    def hud_prefs(self):
        """What a learner's profile keeps of these settings (so they follow them to any computer)."""
        return {"code_at": [round(v, 3) for v in self.code_at], "code_size": [round(v, 3) for v in self.code_size],
                "text_size": self.text_size, "theme": THEME, "invert_scroll": self.invert_scroll,
                "invert_zoom": self.invert_zoom}

    def restore_hud_prefs(self, prefs):
        try:  # where they left the code panel
            self.code_at = self.code_place(float(prefs["code_at"][0]), float(prefs["code_at"][1]))
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        try:  # and how big they made it
            self.code_size = self.code_fit(float(prefs["code_size"][0]), float(prefs["code_size"][1]))
        except (KeyError, IndexError, TypeError, ValueError):
            pass
        if not self.teacher:  # their text size and look (the teacher's are this laptop's: settings.json)
            if prefs.get("text_size") in TEXT_SIZES:
                self.text_size = prefs["text_size"]
                remember("text_size", self.text_size)
            if prefs.get("theme") in ("dark", "light"):
                set_theme(prefs["theme"])
                remember("theme", THEME)
            if "invert_scroll" in prefs:
                self.invert_scroll = bool(prefs["invert_scroll"])
                remember("invert_scroll", self.invert_scroll)
            if "invert_zoom" in prefs:
                self.invert_zoom = bool(prefs["invert_zoom"])
                remember("invert_zoom", self.invert_zoom)

    def show_tip(self, text):
        """A word's description, beside the mouse (to its left: the panel is at the right edge of the screen)."""
        self.hide_tip()
        at = self.mouse_at()
        if at is None:
            return
        self.tip = DirectFrame(frameColor=(0.1, 0.12, 0.18, 0.97), frameSize=(-0.76, 0, -0.1, 0.03),
                               pos=(max(at[0] - 0.02, 0.78 - self.getAspectRatio()), 0, at[1] - 0.03))
        t = label(self.tip, text, -0.74, 0.0, 0.023, WHITE, wrap=31)
        rows = t.textNode.getNumRows()
        self.tip["frameSize"] = (-0.76, 0, -0.023 * 1.2 * rows - 0.01, 0.03)

    def hide_tip(self):
        if getattr(self, "tip", None) is not None:
            self.tip.destroy()
            self.tip = None

    def text_scale(self):
        return TEXT_SIZES.get(self.text_size, 1.0)

    def place_panel(self):
        """The side panel at the text size chosen: scaled about its top right corner, so it grows leftwards and
        downwards. Its title and tabs stay put; the tab's own drawing (the body) slides up under them when it is
        taller than the screen, cut off at the header and the screen's bottom, with a scroll bar at the right."""
        if self.panel is None or self.panel_body is None:
            return
        s, wide = self.text_scale(), self.getAspectRatio()
        self.last_aspect = wide
        self.panel.setScale(s)
        px, pz = 1.76 * (1 - s), 0.97 * (1 - s)
        self.panel.setPos(px, 0, pz)
        top = self.head_bottom                   # the body shows from here (panel units)...
        bottom = max(-0.93, (-1.0 - pz) / s)     # ...down to the screen's bottom (or the panel's)
        lo, hi = self.panel_body.getTightBounds()
        content_bottom = lo.z if lo is not None else bottom
        most = max(0.0, bottom - content_bottom + 0.03)  # how far the body can slide up
        self.panel_scroll = max(0.0, min(most, self.panel_scroll))
        self.panel_body.setZ(self.panel_scroll)
        for n in self.panel_bar:
            n.destroy()
        self.panel_bar = []
        if most <= 0:
            self.panel_body.clearScissor()
            return
        # cut the body off at the header and the screen's bottom (a scissor is set in screen fractions)
        def fx(u):
            return ((px + s * u) / wide + 1) / 2
        def fy(u):
            return (pz + s * u + 1) / 2
        self.panel_body.setScissor(max(0.0, fx(0.78)), min(1.0, fx(1.76)), max(0.0, fy(bottom)), min(1.0, fy(top)))
        # the scroll bar: a track down the right edge, and a thumb as long as the part that is in view
        track = DirectFrame(parent=self.panel, frameColor=(0.5, 0.5, 0.55, 0.5), state=DGG.NORMAL,
                            frameSize=(1.742, 1.772, bottom, top))
        track.bind(DGG.B1PRESS, self.bar_press)
        seen = (top - bottom) / (top - bottom + most)
        length = max(0.05, (top - bottom) * seen)
        thumb_top = top - (top - bottom - length) * (self.panel_scroll / most)
        thumb = DirectFrame(parent=self.panel, frameColor=(0.85, 0.75, 0.3, 0.95), state=DGG.NORMAL,
                            frameSize=(1.742, 1.772, thumb_top - length, thumb_top))
        thumb.bind(DGG.B1PRESS, self.bar_press)
        self.panel_bar = [track, thumb]
        self.panel_bar_geometry = (top, bottom, length, most)

    def slide_panel(self, step):
        self.panel_scroll += 0.2 * step
        self.place_panel()

    def bar_press(self, event=None):
        """The scroll bar was pressed: the thumb follows the mouse until the button is let go (and a press on the
        track above or below the thumb jumps there)."""
        at = self.mouse_at()
        if at is None or not self.panel_bar:
            return
        top, bottom, length, most = self.panel_bar_geometry
        s = self.text_scale()
        u = (at[1] - 0.97 * (1 - s)) / s  # the mouse, in panel units
        thumb_top = top - (top - bottom - length) * (self.panel_scroll / most)
        if not (thumb_top - length <= u <= thumb_top):  # on the track: the thumb's middle jumps to the mouse
            self.panel_scroll = most * (top - length / 2 - u) / max(1e-6, top - bottom - length)
            self.place_panel()
        self.panel_drag = (at[1], self.panel_scroll)
        self.taskMgr.remove("panel bar drag")
        self.taskMgr.add(self.bar_drag_task, "panel bar drag")

    def bar_drag_task(self, task):
        at, mw = self.mouse_at(), self.mouseWatcherNode
        if self.panel_drag is None or not self.panel_bar or at is None or not mw.is_button_down(MouseButton.one()):
            self.panel_drag = None
            return task.done
        top, bottom, length, most = self.panel_bar_geometry
        y0, scroll0 = self.panel_drag
        moved = (y0 - at[1]) / self.text_scale()  # (down the screen: the body slides up)
        self.panel_scroll = scroll0 + most * moved / max(1e-6, top - bottom - length)
        self.place_panel()
        return task.cont

    def wheel(self, factor, step):
        """The mouse wheel: over a side panel taller than the screen it slides the panel; elsewhere it zooms."""
        at = self.mouse_at()
        s = self.text_scale()
        if self.panel is not None and at is not None and at[0] > 1.76 - 0.98 * s and self.panel_bar:
            self.panel_scroll += 0.12 * step * (-1 if self.invert_scroll else 1)
            self.place_panel()
        else:
            self.cam.wheel(1 / factor if self.invert_zoom else factor)

    def set_text_size(self, size):
        self.text_size = size if size in TEXT_SIZES else "medium"
        remember("text_size", self.text_size)
        if getattr(self, "help", None) is not None:
            self.help.setScale(0.042 * self.text_scale())
        self.panel_scroll = 0.0
        self.rebuild_panels()

    def set_invert_scroll(self, on):
        self.invert_scroll = bool(on)
        remember("invert_scroll", self.invert_scroll)
        self.rebuild_panels()

    def set_invert_zoom(self, on):
        self.invert_zoom = bool(on)
        remember("invert_zoom", self.invert_zoom)
        self.rebuild_panels()

    def set_look(self, theme):
        set_theme(theme)
        remember("theme", THEME)
        self.rebuild_panels()

    def build_settings(self, f, y):
        label(f, "SETTINGS", 0.82, y, 0.036, YELLOW)
        y -= 0.05
        label(f, "Yours: kept " + ("on this computer." if self.teacher else "with your profile, for next time."), 0.82, y,
              0.022, GREY)
        y -= 0.07
        label(f, "Text size", 0.82, y, 0.03)
        for i, (key, text) in enumerate((("small", "Small"), ("medium", "Medium"), ("large", "Large"),
                                         ("xlarge", "Extra large"))):
            button(f, text, 1.03 + i * 0.19, y + 0.008, self.set_text_size, [key], 0.024,
                   ON if key == self.text_size else OFF)
        y -= 0.045
        label(f, "The side panel and the code. A panel taller than the screen slides: the mouse wheel over it,\n"
                 "Page Up and Page Down, or its scroll bar.", 0.82, y, 0.02, GREY)
        y -= 0.07
        label(f, "Look", 0.82, y, 0.03)
        for i, (key, text) in enumerate((("dark", "Dark"), ("light", "Light"))):
            button(f, text, 1.12 + i * 0.2, y + 0.008, self.set_look, [key], 0.026, ON if key == THEME else OFF)
        y -= 0.045
        label(f, "The panels and the code; the game's own display stays as it is.", 0.82, y, 0.02, GREY)
        y -= 0.07
        label(f, "Mouse wheel", 0.82, y, 0.03)
        for i, (on, text) in enumerate(((False, "Normal"), (True, "Inverted"))):
            button(f, text, 1.12 + i * 0.2, y + 0.008, self.set_invert_scroll, [on], 0.026,
                   ON if on == self.invert_scroll else OFF)
        y -= 0.045
        label(f, "Inverted: the wheel slides the panel and scrolls the code the other way up (old school).",
              0.82, y, 0.02, GREY)
        y -= 0.07
        label(f, "Wheel zoom", 0.82, y, 0.03)
        for i, (on, text) in enumerate(((False, "Normal"), (True, "Inverted"))):
            button(f, text, 1.12 + i * 0.2, y + 0.008, self.set_invert_zoom, [on], 0.026,
                   ON if on == self.invert_zoom else OFF)
        y -= 0.045
        label(f, "Normal: wheel up zooms in. Inverted: wheel up zooms out.", 0.82, y, 0.02, GREY)

    def start_typing(self, key):
        if self.typing == "code" and key != "code" and self.code_editor is not None:
            self.code_editor.blur()  # (typing moves from the code to a text box)
        self.typing = key

    def type_code(self):
        """The code panel was clicked: the keyboard goes to the code (not the game, or another text box)."""
        self.stop_typing()
        self.typing = "code"

    def stop_typing(self, key=None):
        if key is not None and key != self.typing:
            return
        if self.typing == "code" and getattr(self, "code_editor", None) is not None:
            self.code_editor.blur()
        e = self.entries.get(self.typing)
        self.typing = None
        if e is not None:
            try:
                e["focus"] = 0
            except Exception:
                pass

    def keep_typing(self):
        """Remember what is typed in text boxes, so redrawing a panel doesn't lose it."""
        for key, e in self.entries.items():
            try:
                self.entry_text[key] = e.get()
            except Exception:
                pass
        self.entries = {}

    def entry(self, parent, key, x, y, width=18, lines=1, initial="", command=None, scale=0.03, obscured=False):
        e = DirectEntry(parent=parent, initialText=self.entry_text.get(key, initial), scale=scale, width=width,
                        pos=(x, 0, y), numLines=lines, focus=0, frameColor=BOX, text_fg=WHITE,
                        obscured=1 if obscured else 0,
                        command=command, focusInCommand=self.start_typing, focusInExtraArgs=[key],
                        focusOutCommand=self.stop_typing, focusOutExtraArgs=[key])
        if key == self.typing:  # redrawn while typing: carry on typing in the new box
            e["focus"] = 1
            e.setCursorPosition(len(e.get()))
        self.entries[key] = e
        return e

    def code_rect(self):
        """The code panel's frame: its first size, plus how much wider and taller it has been dragged."""
        return (self.CODE_PANEL[0], self.CODE_PANEL[1] + self.code_size[0], self.CODE_PANEL[2] - self.code_size[1], self.CODE_PANEL[3])

    def code_rows(self):
        """Lines of code the panel shows at once: more when it has been made taller, fewer when the text is big."""
        return max(4, int((self.CODE_ROWS * 0.024 * 1.8 + self.code_size[1]) / (0.024 * self.text_scale() * 1.8)))

    def code_fit(self, dw, dh):
        """How much bigger the code panel may be: no wider or taller than the screen."""
        wide = self.getAspectRatio()
        return [max(0.0, min(2 * wide - (self.CODE_PANEL[1] - self.CODE_PANEL[0]) - 0.02, dw)),
                max(0.0, min(2 - (self.CODE_PANEL[3] - self.CODE_PANEL[2]) - 0.02, dh))]

    def code_place(self, x, y):
        """Where the code panel may be (how far from its first place): never off the edge of the screen."""
        wide = self.getAspectRatio()
        left, right, bottom, top = self.code_rect()
        return [max(-wide - left, min(wide - right, x)), max(-1 - bottom, min(1 - top, y))]

    def mouse_at(self):
        """The mouse's place on the screen, in the panels' units (or None if it is outside the window)."""
        mw = self.mouseWatcherNode
        if mw is None or not mw.hasMouse():
            return None
        return mw.getMouseX() * self.getAspectRatio(), mw.getMouseY()

    def code_drag_start(self, event=None):
        """The code panel's top was pressed: it follows the mouse until the button is let go."""
        at = self.mouse_at()
        if at is None:
            return
        self.code_drag = (at, list(self.code_at))
        self.taskMgr.remove("code panel drag")
        self.taskMgr.add(self.code_drag_task, "code panel drag")

    def code_drag_task(self, task):
        at, mw = self.mouse_at(), self.mouseWatcherNode
        if self.code_drag is None or self.code_panel is None or at is None or not mw.is_button_down(MouseButton.one()):
            self.code_drag = None  # (let go: the panel stays where it is, and that place is kept with their view)
            return task.done
        (x0, y0), (px, py) = self.code_drag
        self.code_at = self.code_place(px + at[0] - x0, py + at[1] - y0)
        self.code_panel.setPos(self.code_at[0], 0, self.code_at[1])
        return task.cont

    def code_resize_start(self, event=None):
        """The code panel's corner grip was pressed: the panel grows or shrinks with the mouse until it is let go."""
        at = self.mouse_at()
        if at is None:
            return
        self.code_resize = (at, list(self.code_size), list(self.code_size))
        self.taskMgr.remove("code panel resize")
        self.taskMgr.add(self.code_resize_task, "code panel resize")

    def code_resize_task(self, task):
        at, mw = self.mouse_at(), self.mouseWatcherNode
        if self.code_resize is None or self.code_panel is None or at is None or not mw.is_button_down(MouseButton.one()):
            if self.code_resize is not None and self.code_panel is not None and self.code_resize[2] != self.code_size:
                self.refresh_code_panel()  # (let go: drawn once more at its final size)
            self.code_resize = None
            return task.done
        (x0, y0), (w0, h0), drawn = self.code_resize
        self.code_size = self.code_fit(w0 + at[0] - x0, h0 - (at[1] - y0))
        self.code_at = self.code_place(*self.code_at)
        if abs(self.code_size[0] - drawn[0]) > 0.03 or abs(self.code_size[1] - drawn[1]) > 0.03:
            self.code_resize = ((x0, y0), (w0, h0), list(self.code_size))
            self.refresh_code_panel()
        return task.cont
