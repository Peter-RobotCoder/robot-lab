"""The HUD kit: what every Club Coders game's window shares (the engine's, since 6 October 2026).

The panels' colours (a dark look and a light one), the text sizes, the words that explain themselves (hover tips),
the drawing helpers (label, word, button, check, text boxes), the side panel with its fixed header, scrolling
body and scroll bar, the Settings tab, this computer's settings file, and the code panel's moving and resizing.

A game's window inherits HudKit (with ShowBase) and calls setup() once, naming its settings folder and the modules
whose colour names should follow the look. Tabs and sections a game or a user mod adds are registered with
add_tab(), never written into this file.
"""
import copy
import json
import os
import sys

from direct.gui.DirectGui import (DGG, DirectButton, DirectCheckButton, DirectEntry, DirectFrame, DirectLabel,
                                  DirectSlider)
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import MouseButton, PGItem, TextNode, WindowProperties

from engine import editor

APP = None  # the window (so any button click can end typing in a text box): set by setup_app
SEND = None  # the window's send(message) to its server: set by setup_app
THEMED = [sys.modules[__name__]]  # modules whose colour names are swapped by set_theme (this one, and the games')
# (__import__("engine.hud") gave the package, not this module, so the kit's own drawing stayed dark in light mode)


def setup_app(app, send=None):
    global APP, SEND
    APP, SEND = app, send


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
              "Its type is str. A string is made of chars: a char is one character from the ASCII set of "
              "characters, a letter, a digit, a space or a symbol.",
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
    reflections = ()                         # the objectives answered in writing (a box in the Mission tab)
    user_mods = {}                           # the game's user mods: key -> (title, what it does)
    STAGE_WORD = "ARENA"                     # the Mods tab's heading for the game's own items (hazards and so on)
    MODS_PER_PAGE = 7                        # user mods on one page of the Mods tab (under those items)
    LIMITS_TITLE = "LIMITS"                  # the Limits tab's heading, and its note on the size setting
    LIMITS_NOTE = "Size: 100 is the standard size."

    def init_hud(self):
        """Called once by the game's window, before any panel is drawn."""
        self.panel = self.panel_body = self.code_panel = None
        self.panel_bar, self.panel_drag, self.last_aspect = [], None, None
        self.head_bottom = 0.875
        self.tip = None  # the description of the word the mouse is over (CHANGE 44 and 45)
        self.open_objective = None  # the Mission tab: the objective whose guidance is dropped down (CHANGE 53)
        self.missions = None  # the server's missions message: the mission, its objectives, the learner's record
        self.mod_info, self.mods_page = {}, 0  # user mods: their makers, the votes and who is in this group
        self.warnings, self.warnings_seen = [], 0  # teacher: the Warnings tab, and how many of them have been seen
        self.limit_sliders, self.limits_draft, self.limits_moved = {}, None, False  # teacher: the Limits tab
        self.my_name = ""     # the player's name (a learner's tick on the Mods tab is a vote in their name)
        self.text_size = SETTINGS.get("text_size") if SETTINGS.get("text_size") in TEXT_SIZES else "medium"
        self.fullscreen, self.windowed = False, None  # (CHANGE 108)
        self.slots, self.slot_pick, self.slot_confirm = {}, 1, None  # saved designs (CHANGE 83): who -> slot -> design
        self.history, self.load_from = None, None  # (CHANGE 84, 86: the teacher's Load from row)
        self.loaded_note = ""
        self.full_button = button(self.aspect2d, "[ ]", 1.735, 0.965, self.toggle_fullscreen, None, 0.024, (0.2, 0.22, 0.28, 0.9))
        self.full_button["sortOrder"] = 20  # (above the side panel header)
        self.full_button.bind(DGG.WITHIN, lambda e: self.show_tip("Full screen: the game fills the screen, no title bar "
                                                                 "or taskbar. Press again for a window."))
        self.full_button.bind(DGG.WITHOUT, lambda e: self.hide_tip())
        if SETTINGS.get("fullscreen"):
            self.taskMgr.doMethodLater(0.5, lambda t: self.toggle_fullscreen() and None, "full screen at the start")
        self.panel_scroll = 0.0  # how far a side panel taller than the screen has been slid up (CHANGE 40)
        self.invert_scroll = bool(SETTINGS.get("invert_scroll"))  # the mouse wheel the other way up (Settings)
        self.invert_zoom = bool(SETTINGS.get("invert_zoom"))      # ...and for the camera's zoom, its own switch
        self.entries, self.entry_text, self.typing = {}, {}, None  # text boxes on screen, what they held, which has the keyboard
        self.code_editor = None
        self.custom_colour = None  # the garage's custom colour block: the colour the code last set (CHANGE 48)
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
            label(f, "hover over a word in capitals\nto see what it means", 1.68, 0.952, 0.017, GREY,
                  TextNode.ARight)
        for i, (key, text) in enumerate(tabs):
            b = button(f, tab_text(key, text) if tab_text else text, left + (i % across + 0.5) * (width / across),
                       (0.94 - (i // across) * 0.047) if teacher else 0.9, open_tab, [key],
                       0.024 if teacher else 0.022, ON if key == current else OFF)
            b["sortOrder"] = 10  # (above anything in the body that has slid up under the header)
        self.head_bottom = 0.865 if teacher else 0.875  # (the body shows below here; the header stays put)
        self.panel_body = self.panel.attachNewNode("body")
        return self.panel_body, 0.84 if teacher else 0.83

    # ---------- saved designs (CHANGE 83 to 87): five slots, the history, the teacher's loading ----------
    UNIT = "robot"          # (the game's word: robot, fighter)
    ALL_LEARNERS = "All learners"

    def took_slots(self, m):
        """A slots or history message from the server."""
        if m["type"] == "slots":
            self.slots[m["who"]] = m.get("slots", {})
        else:
            self.history = m.get("items", [])
        return self.tab in ("garage", "learners")

    def slot_action(self, do, n, who=None):
        """SAVE HERE, LOAD or DELETE on slot n: a save over a full slot and a delete ask first (press again)."""
        mine = self.slots.get(who or self.my_name, {})
        if do in ("save", "delete") and str(n) in mine and self.slot_confirm != (do, n):
            self.slot_confirm = (do, n)
            self.rebuild_panels()
            return
        self.slot_confirm = None
        if do == "load":
            self.take_design(mine[str(n)]["design"])
            self.loaded_note = f"Loaded {mine[str(n)]['name']} from slot {n}: press BUILD to use it."
        elif do == "save":
            SEND({"type": "slot", "do": "save", "n": n, "design": self.cur()})
        elif do == "delete":
            SEND({"type": "slot", "do": "delete", "n": n})
        self.rebuild_panels()

    def take_design(self, design):
        """A saved design goes into the garage (the draft being edited), ready to build."""
        d = self.cur()
        d.clear()
        d.update(copy.deepcopy(design))
        self.entry_text.pop(self.name_key(), None)
        if self.name_key() in self.entries:
            self.entries[self.name_key()].enterText(str(d.get("name", "")))
        self.code_shown = None

    def build_slots(self, f, y, view=None):
        """The garage's SAVED ROBOTS row(s). A learner: their five slots. The teacher's own garage: theirs. The
        Learner view: Load from the learner's slots, the teacher's own, or the history (LOAD only)."""
        unit = self.UNIT.upper()
        if view == self.ALL_LEARNERS:
            label(f, f"Build one {self.UNIT} here, then BUILD FOR ALL LEARNERS: every learner gets exactly it, and "
                     f"anyone who joins later. Their saved slots are not touched.", 0.82, y, 0.021, GREY, wrap=46)
            y -= 0.07
            return self.build_load_from(f, y, view)
        if view:
            return self.build_load_from(f, y, view)
        mine = self.slots.get(self.my_name, {})
        label(f, f"SAVED {unit}S", 0.82, y, 0.029, YELLOW)
        label(f, "pick a slot, then save, load or delete", 1.74, y, 0.02, GREY, TextNode.ARight)
        y -= 0.045
        for n in range(1, 6):
            held = mine.get(str(n))
            button(f, f"{n}: {held['name'] if held else 'empty'}", 0.9 + (n - 1) * 0.17, y + 0.008, self.pick_slot, [n],
                   0.022, ON if self.slot_pick == n else OFF)
        y -= 0.05
        n, held = self.slot_pick, mine.get(str(self.slot_pick))
        if self.slot_confirm == ("save", n):
            label(f, f"Overwrite {held['name']}?", 0.84, y, 0.024, ORANGE)
            button(f, "YES, SAVE", 1.12, y + 0.008, self.slot_action, ["save", n], 0.022, (0.6, 0.35, 0.1, 1))
            button(f, "No", 1.3, y + 0.008, self.cancel_slot, None, 0.022)
        elif self.slot_confirm == ("delete", n):
            label(f, f"Delete {held['name']}?", 0.84, y, 0.024, ORANGE)
            button(f, "YES, DELETE", 1.12, y + 0.008, self.slot_action, ["delete", n], 0.022, (0.6, 0.2, 0.15, 1))
            button(f, "No", 1.3, y + 0.008, self.cancel_slot, None, 0.022)
        else:
            button(f, "SAVE HERE", 0.9, y + 0.008, self.slot_action, ["save", n], 0.022, (0.15, 0.45, 0.65, 1))
            if held:
                button(f, "LOAD", 1.1, y + 0.008, self.slot_action, ["load", n], 0.022)
                button(f, "DELETE", 1.24, y + 0.008, self.slot_action, ["delete", n], 0.022)
            label(f, self.loaded_note, 1.4, y, 0.02, GREEN, wrap=22)
        y -= 0.06
        return y

    def pick_slot(self, n):
        self.slot_pick, self.slot_confirm = n, None
        self.rebuild_panels()

    def cancel_slot(self):
        self.slot_confirm = None
        self.rebuild_panels()

    def build_load_from(self, f, y, view):
        """The teacher's Learner view: load a saved design into this garage from the learner's slots, the teacher's
        own, or the history of every save (CHANGE 86)."""
        choices = [("mine", "My saved")] + ([("theirs", f"{view}'s saved")] if view != self.ALL_LEARNERS else []) + \
            [("history", "History")]
        label(f, "Load from", 0.82, y, 0.026, YELLOW)
        for i, (key, text) in enumerate(choices):
            button(f, text, 0.98 + i * 0.22, y + 0.008, self.set_load_from, [key, view], 0.022,
                   ON if self.load_from == key else OFF)
        label(f, self.loaded_note, 1.74, y - 0.035, 0.02, GREEN, TextNode.ARight)
        y -= 0.05
        if self.load_from == "history":
            items = self.history or []
            if not items:
                label(f, "Nothing saved yet." if self.history is not None else "Loading...", 0.84, y, 0.022, GREY)
                y -= 0.04
            for it in items[:12]:
                label(f, f"{it['when']}  {it['who']}  slot {it['slot']}:  {it['name']}", 0.84, y, 0.021)
                button(f, "LOAD", 1.6, y + 0.008, self.load_item, [it["design"], it["name"]], 0.02)
                y -= 0.036
        elif self.load_from in ("mine", "theirs"):
            who = self.my_name if self.load_from == "mine" else view
            slots = self.slots.get(who)
            if slots is None:
                label(f, "Loading...", 0.84, y, 0.022, GREY)
                y -= 0.04
            elif not slots:
                label(f, "No saved " + self.UNIT + "s.", 0.84, y, 0.022, GREY)
                y -= 0.04
            for n, held in sorted(slots.items() if slots else []):
                label(f, f"slot {n}:  {held['name']}", 0.84, y, 0.022)
                button(f, "LOAD", 1.6, y + 0.008, self.load_item, [held["design"], held["name"]], 0.02)
                y -= 0.036
        return y - 0.02

    def set_load_from(self, key, view):
        self.load_from = key
        if key == "history":
            SEND({"type": "history"})
        elif key == "theirs":
            SEND({"type": "slots_of", "name": view})
        self.rebuild_panels()

    def load_item(self, design, name):
        self.take_design(design)
        self.loaded_note = f"Loaded {name}: press BUILD to use it."
        self.rebuild_panels()

    def toggle_fullscreen(self):
        """CHANGE 108: a borderless window the size of the screen, or back to the window it was."""
        win = getattr(self, "win", None)
        if win is None or not hasattr(win, "requestProperties"):
            return
        wp = WindowProperties()
        if not self.fullscreen:
            cur = win.getProperties()
            self.windowed = (cur.getXSize(), cur.getYSize(), cur.getXOrigin(), cur.getYOrigin())
            wp.setUndecorated(True)
            wp.setOrigin(0, 0)
            wp.setSize(self.pipe.getDisplayWidth(), self.pipe.getDisplayHeight())
        else:
            w, h, x, y = self.windowed or (1280, 720, 60, 60)
            wp.setUndecorated(False)
            wp.setOrigin(max(0, x), max(0, y))
            wp.setSize(w, h)
        win.requestProperties(wp)
        self.fullscreen = not self.fullscreen
        self.full_button["text"] = "> <" if self.fullscreen else "[ ]"
        remember("fullscreen", self.fullscreen)

    def hud_prefs(self):
        """What a learner's profile keeps of these settings (so they follow them to any computer)."""
        return {"code_at": [round(v, 3) for v in self.code_at], "code_size": [round(v, 3) for v in self.code_size],
                "text_size": self.text_size, "theme": THEME, "invert_scroll": self.invert_scroll,
                "invert_zoom": self.invert_zoom, "last_tab": self.tab or getattr(self, "last_tab", None)}

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
        if isinstance(prefs.get("last_tab"), str):  # (CHANGE 103: I opens the HUD on the tab last used)
            self.last_tab = prefs["last_tab"]

    def toggle_panel(self):
        """I (CHANGE 103): the side panel closes, or opens on the tab last used."""
        if self.tab:
            self.last_tab, self.tab = self.tab, None
        else:
            self.tab = getattr(self, "last_tab", None) or self.FIRST_TAB
        self.code_shown = None
        self.rebuild_panels()

    FIRST_TAB = "missions"   # (the game sets it: the tab I opens before any has been used)
    panel_floor = -1.0       # the screen's y the side panel may reach down to (above the key list: CHANGE 104)

    def show_tip(self, text):
        """A word's description, beside the mouse (to its left: the panel is at the right edge of the screen)."""
        self.hide_tip()
        at = self.mouse_at()
        if at is None:
            return
        s = self.text_scale()  # (CHANGE 105: the description follows the text size; CHANGE 110: and the theme)
        self.tip = DirectFrame(frameColor=HANDLE, frameSize=(-0.76 * s, 0, -0.1, 0.03 * s),
                               pos=(max(at[0] - 0.02, 0.78 * s - self.getAspectRatio()), 0, at[1] - 0.03))
        t = label(self.tip, text, -0.74 * s, 0.0, 0.023 * s, WHITE, wrap=31)
        rows = t.textNode.getNumRows()
        self.tip["frameSize"] = (-0.76 * s, 0, -0.023 * s * 1.2 * rows - 0.01, 0.03 * s)

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
        bottom = max(-0.93, (self.panel_floor - pz) / s)  # ...down to the key list (CHANGE 104), or the panel's bottom
        content_bottom = self.body_bottom(bottom)
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

    def body_bottom(self, if_empty):
        """The lowest point of the tab's drawing, in panel units (with the body unslid). The tight bounds only
        measure the plain text: a button, tick box, slider or entry box (a PGItem) draws its frame and text in
        its own state nodes, which aren't measured, so a button at the very bottom of a tab is measured here
        from its position and frame."""
        body = self.panel_body
        lo, hi = body.getTightBounds()
        lowest = lo.z - body.getZ() if lo is not None else if_empty
        for n in body.findAllMatches("**/+PGItem"):
            frame = n.node().getFrame()
            lowest = min(lowest, n.getZ(body) + frame[2] * n.getSz(body))
        return lowest

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
        y -= 0.07
        label(f, "Version", 0.82, y, 0.03)
        label(f, self.version_text(), 1.12, y, 0.024, GREY)  # (CHANGE 106)

    VERSION = ""    # the game sets these: its release number...
    LIVE_ID = None  # ...and the live update's id when it is running one (lab_version.live_id())

    def version_text(self):
        text = f"Club Coders {self.VERSION}" if self.VERSION else "unknown"
        if self.LIVE_ID:
            text += f"  with live update {str(self.LIVE_ID)[:8]}"
        return text

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
        e.bind(DGG.B1PRESS, lambda ev, e=e: self.taskMgr.doMethodLater(0, self.place_cursor, "entry click", [e]))
        self.entries[key] = e
        return e

    def place_cursor(self, e, task=None):
        """CHANGE 92: a click in a text box puts the cursor at the letter clicked (from the click's x and the
        width of the text up to each letter), on every line of a box with several."""
        try:
            at = self.mouse_at()
            if at is None or e.isEmpty():
                return
            local = e.getRelativePoint(self.aspect2d, (at[0], 0, at[1]))  # (in the box's own units: the text's)
            text = e.get()
            tn = TextNode("measure")
            tn.setFont(e.guiItem.getTextDef(0).getFont())
            lines = text.split("\n")
            row = max(0, min(len(lines) - 1, int((0.8 - local.z) / 1.2)))  # (DirectEntry lines are 1.2 apart)
            line = lines[row]
            before = sum(len(l) + 1 for l in lines[:row])
            best, best_d = 0, None
            for i in range(len(line) + 1):
                d = abs(tn.calcWidth(line[:i]) - local.x)
                if best_d is None or d < best_d:
                    best, best_d = i, d
            e.setCursorPosition(before + best)
        except Exception:  # (a box being destroyed, or a font without widths: the click still focuses it)
            pass

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

    # ---------- the Mission tab (CHANGE 50 to 53, 56): the objectives, from the server's missions message ----------
    def build_missions(self, f, y, m=None, preview=False):
        m = m or self.missions
        self.top_speed_text = None
        if not m:
            label(f, "Waiting for missions...", 0.82, y, 0.03, GREY)
            return
        title = label(f, f"MISSION {m['lesson']}: {m['title']}", 0.82, y, 0.034, YELLOW, wrap=26)
        y -= 0.045 * title.textNode.getNumRows() + 0.005
        label(f, "Objectives. Click one to see what to do; a done one shows what you did.", 0.82, y, 0.021, GREY)
        y -= 0.045
        # (CHANGE 53) each objective is its title: done, the result is under it; not done, clicking the title drops
        # down its explanation and guidance. The teacher's Learner view shows everything.
        for i, mm in enumerate(m["missions"]):
            tick = "DONE" if mm["done"] else ("TEACHER" if mm["check"] == "teacher" else "TO DO")
            letter = f"{'abcdefgh'[i]}. " if i < 8 else ""
            text = f"[{tick}]  {letter}{mm['title']}"
            if preview:
                label(f, text, 0.82, y, 0.03, GREEN if mm["done"] else WHITE)
            else:
                opened = self.open_objective == mm["id"]
                bright = tuple(min(1.0, c * 1.25) for c in GREEN[:3]) + (1,)  # (bold green when clicked: CHANGE 95)
                colour = (bright if opened else GREEN) if mm["done"] else (YELLOW if opened else WHITE)
                text_button(f, text, 0.82, y, self.toggle_objective, [mm["id"]], 0.033 if opened and mm["done"] else 0.03,
                            colour)
            outcomes = label(f, " ".join(mm["outcomes"]), 1.74, y, 0.022, BLUE, TextNode.ARight)
            if mm["done"]:  # (CHANGE 95: a tick at the end of a done title, drawn: the font has no tick glyph)
                self.tick_mark(f, 1.74 - 0.022 * outcomes.textNode.calcWidth(" ".join(mm["outcomes"])) - 0.045, y + 0.008)
            y -= 0.04
            open_ = preview or self.open_objective == mm["id"]
            if mm["done"]:  # (the result; and the guidance too when it is dropped down: CHANGE 56)
                t = label(f, mm["detail"], 0.84, y, 0.024, GREEN, wrap=36)
                y -= 0.03 * t.textNode.getNumRows() + 0.01
            if open_:
                t = label(f, mm["text"], 0.84, y, 0.024, GREY, wrap=36)
                y -= 0.03 * t.textNode.getNumRows() + 0.01
            if preview:  # the teacher sees what the learner typed, not boxes to type in
                typed = m["text"].get(mm["id"])
                if typed and not mm["done"]:
                    label(f, f"They wrote: {typed}", 0.86, y, 0.022, BLUE, wrap=38)
                    y -= 0.045
                y -= 0.01
                continue
            if mm["id"] in self.reflections and not mm["done"] and open_:
                self.entry(f, f"reflect_{mm['id']}", 0.84, y, 30, 2, initial=m["text"].get(mm["id"], ""), scale=0.026)
                button(f, "Save", 1.66, y - 0.02, self.save_reflection, [mm["id"]], 0.026)
                y -= 0.09
            y -= 0.01
        if m["lesson"] >= 3:
            status = ("autopilot ON" if m["autopilot"] else "uploaded (press P for autopilot)") if m["brain"] \
                else "not uploaded yet (edit brains/my_brain.py, then press U)"
            label(f, f"Brain: {status}", 0.82, max(y, -0.8), 0.026, GREEN if m["brain"] else GREY)
            if m.get("brain_error"):
                label(f, f"Brain stopped: {m['brain_error']}", 0.82, max(y, -0.8) - 0.045, 0.024, RED, wrap=38)

    @staticmethod
    def tick_mark(f, x, y, size=0.022, colour=None):
        """A tick drawn from two bars (the HUD's font has no tick character)."""
        c = colour or GREEN
        short = DirectFrame(parent=f, frameColor=c, frameSize=(-0.004, 0.004, 0, size * 0.55),
                            pos=(x - size * 0.3, 0, y - size * 0.1))
        short.setR(-40)
        long_ = DirectFrame(parent=f, frameColor=c, frameSize=(-0.004, 0.004, 0, size), pos=(x, 0, y - size * 0.25))
        long_.setR(35)

    def toggle_objective(self, mid):
        """Drop down an objective's guidance in the Mission tab, or fold it away again."""
        self.open_objective = None if self.open_objective == mid else mid
        self.rebuild_panels()

    def save_reflection(self, mission):
        SEND({"type": "reflection", "mission": mission, "text": self.entries[f"reflect_{mission}"].get()})

    # ---------- the Mods tab (CHANGE 4 to 8, 55, 71): the game's items and the user mods, with votes ----------
    def mod_title(self, key):
        """A user mod's name with its maker's in front: "Sam's Spike pit"."""
        maker = (self.mod_info.get("makers") or {}).get(key)
        title = self.user_mods[key][0]
        return f"{maker}'s {title}" if maker else title

    def mod_order(self):
        """Every user mod as (key, its maker is in this group), with this group's own mods first."""
        makers = self.mod_info.get("makers", {})
        here = {n.lower() for n in self.mod_info.get("here", [])}
        mods = [(k, bool(makers.get(k)) and makers[k].lower() in here) for k in self.user_mods]
        return sorted(mods, key=lambda m: not m[1])  # (a stable sort: otherwise the order they were made in)

    @staticmethod
    def votes_text(voters, form="{}"):
        n = len(voters or [])
        return form.format(f"{n} vote{'' if n == 1 else 's'}") if n else ""

    def build_mods(self, f, y, as_learner=False):
        """The Mods tab: the arena's items, then the user mods. The teacher's ticks switch them on and off; a
        learner's tick is a vote for it (the teacher sees how many votes, and whose).
        as_learner: the teacher's preview of what a learner sees (the Learner view): the ticks do nothing."""
        L = self.lesson
        teacher = self.teacher and not as_learner
        vote = (lambda msg: None) if as_learner else SEND
        mods_on, votes, asked = L.get("user_mods", {}), self.mod_info.get("votes", {}), self.mod_info.get("arena_votes", {})
        in_vote = L.get("mods_in_vote", {})  # (CHANGE 55: a mod not in the vote is hidden from learners, unless on)
        arena_vote = L.get("arena_in_vote", {})  # (the same for the arena's hazards and Resident Robots)
        label(f, self.STAGE_WORD, 0.82, y, 0.036, YELLOW)
        label(f, "Your tick switches it on or off; \"in the vote\": learners see it and can vote for it." if teacher else
              "Tick what you'd like in the game: your teacher sees the votes.", 1.74, y, 0.021, GREY, TextNode.ARight)
        y -= 0.06
        items = self.stage_items()  # (the game's: its hazards and the like, with how the teacher switches each)
        if teacher and items:  # (CHANGE 101: every item into or out of the vote at once)
            self.vote_all_row(f, y, "arena_in_vote", [it[0] for it in items])
            y -= 0.045
        if not teacher:  # (an item out of the vote is hidden, unless it is on)
            items = [it for it in items if arena_vote.get(it[0], True) or it[2]]
        for key, text, on, switch in items:
            voters = asked.get(key, [])
            if teacher:
                check(f, " " + text, 0.84, y, on, switch, 0.024)
                check(f, " in the vote", 1.3, y, arena_vote.get(key, True),
                      lambda v, k=key: self.set_lesson({"arena_in_vote": {k: bool(v)}}), 0.022, GREY)
                if voters:
                    label(f, f"{len(voters)}: {', '.join(voters)}", 1.74, y, 0.02, BLUE, TextNode.ARight)
            elif arena_vote.get(key, True):
                check(f, " " + text + self.votes_text(voters, "  ({})") + ("   ON" if on else ""), 0.84, y,
                      self.my_name in voters, lambda v, k=key: vote({"type": "arena_vote", "item": k, "on": bool(v)}),
                      0.024, GREEN if on else WHITE)
            else:
                label(f, text + "   ON", 0.86, y, 0.024, GREEN)
            y -= 0.036
        y -= 0.03
        label(f, "USER MODS", 0.82, y, 0.036, YELLOW)
        y -= 0.05
        label(f, "Learners' ideas, built into the game. Tick a mod to switch it on or off: it works straight away.\n"
                 "Green: made by a learner in this group. \"In the vote\": learners see it and can vote for it." if teacher
              else "Learners' ideas, built into the game. Tick the ones you'd like in the game: your teacher\n"
                   "sees the votes and switches mods on.", 0.82, y, 0.021, GREY)
        y -= 0.085
        order = self.mod_order()
        if teacher and order:  # (CHANGE 101)
            self.vote_all_row(f, y, "mods_in_vote", [k for k, _ in order])
            y -= 0.045
        if not teacher:
            order = [(k, lit) for k, lit in order if in_vote.get(k, True) or mods_on.get(k)]
        if not order:
            label(f, "No user mods yet.", 0.84, y, 0.026, GREY)
        pages = max(1, (len(order) + self.MODS_PER_PAGE - 1) // self.MODS_PER_PAGE)
        self.mods_page = min(self.mods_page, pages - 1)
        for key, lit in order[self.mods_page * self.MODS_PER_PAGE:(self.mods_page + 1) * self.MODS_PER_PAGE]:
            voters, on = votes.get(key, []), bool(mods_on.get(key))
            if teacher:
                check(f, " " + self.mod_title(key), 0.84, y, on,
                      lambda v, k=key: self.set_lesson({"user_mods": {k: bool(v)}}), 0.028, GREEN if lit else WHITE)
                check(f, " in the vote", 1.47, y, in_vote.get(key, True),
                      lambda v, k=key: self.set_lesson({"mods_in_vote": {k: bool(v)}}), 0.022, GREY)
                if voters:  # (under the tick boxes: the names)
                    label(f, self.votes_text(voters, "{}: ") + ", ".join(voters), 1.74, y - 0.04, 0.021, BLUE,
                          TextNode.ARight)
            elif in_vote.get(key, True):
                check(f, " " + self.mod_title(key), 0.84, y, self.my_name in voters,
                      lambda v, k=key: vote({"type": "mod_vote", "mod": k, "on": bool(v)}), 0.028)
                label(f, self.votes_text(voters, "{}   ") + ("ON" if on else "off"), 1.74, y, 0.024,
                      GREEN if on else GREY, TextNode.ARight)
            else:  # on, but not in the vote: shown, with no tick to vote with
                label(f, self.mod_title(key), 0.86, y, 0.028, GREEN)
                label(f, "ON", 1.74, y, 0.024, GREEN, TextNode.ARight)
            y -= 0.04
            what = self.user_mods[key][1]
            narrow = teacher and bool(voters)
            label(f, what, 0.89, y, 0.021, GREY, wrap=30 if narrow else 40)
            y -= 0.03 * (len(what) // (40 if narrow else 62) + 1) + 0.025
        if pages > 1:
            button(f, "Back", 1.0, -0.87, self.page_mods, [-1], 0.023)
            label(f, f"page {self.mods_page + 1} of {pages}", 1.27, -0.875, 0.021, GREY, TextNode.ACenter)
            button(f, "More", 1.52, -0.87, self.page_mods, [1], 0.023)

    def vote_all_row(self, f, y, key, names):
        """Select all / Deselect all: every item in the vote, or none (then tick the few wanted)."""
        label(f, "In the vote:", 0.84, y, 0.022, GREY)
        button(f, "Select all", 1.08, y + 0.008, self.set_lesson, [{key: {n: True for n in names}}], 0.022)
        button(f, "Deselect all", 1.3, y + 0.008, self.set_lesson, [{key: {n: False for n in names}}], 0.022)

    def page_mods(self, delta):
        self.mods_page = max(0, self.mods_page + delta)
        self.rebuild_panels()

    def stage_items(self):
        """The game's own items for the Mods tab: [(key, text, on, switch(value))], the teacher's switch for each."""
        return []

    # ---------- the Warnings tab (CHANGE 34): a learner changed, in the code, what the garage hides ----------
    def build_warnings(self, f, y):
        label(f, "WARNINGS", 0.82, y, 0.036, YELLOW)
        y -= 0.05
        label(f, "A learner changed, in the code, a value this lesson's garage doesn't let them change.\n"
                 "The change was used (the limits still held). They haven't been told that you can see it.",
              0.82, y, 0.02, GREY)
        y -= 0.085
        if not self.warnings:
            label(f, "No warnings this session.", 0.82, y, 0.028, GREY)
        for w in reversed(self.warnings[-14:]):  # the newest first
            changes = ",  ".join(f"{what} {self.warning_value(old)} to {self.warning_value(new)}"
                                 for what, old, new in w["changes"])
            text = label(f, f"{w['time']}  {w['who']}:  {changes}", 0.82, y, 0.024, WHITE, wrap=37)
            y -= 0.03 * max(1, text.textNode.getNumRows()) + 0.02
            if y < -0.86:
                break
        if len(self.warnings) > 14:
            label(f, f"...and {len(self.warnings) - 14} earlier", 0.82, -0.9, 0.022, GREY)

    @staticmethod
    def warning_value(v):
        return f"{v:g}" if isinstance(v, float) else str(v)

    def warnings_tab_text(self, text):
        """The Warnings tab's name counts the warnings not seen yet."""
        if self.tab == "warnings":
            self.warnings_seen = len(self.warnings)
        unseen = len(self.warnings) - self.warnings_seen
        return f"{text} ({unseen})" if unseen > 0 else text

    def took_warnings(self, m):
        """The server's warnings message (the teacher's)."""
        self.warnings = m.get("list", [])
        self.warnings_seen = min(self.warnings_seen, len(self.warnings))

    # ---------- the Limits tab (CHANGE 31, 62): the ranges learners can choose from ----------
    def build_limits(self, f, y):
        """Two sliders for every setting and every point: the lowest and the highest a learner can choose. Each
        runs over the whole range (the teacher's own robot can use all of it). Letting a slider go sends the new
        limits to the class server, which keeps them between sessions and pulls back any robot outside them."""
        full = self.full_limits()
        limits = self.limits_draft = copy.deepcopy(self.lesson.get("limits") or self.default_limits())
        self.limit_sliders = {}
        label(f, self.LIMITS_TITLE, 0.82, y, 0.036, YELLOW)
        y -= 0.05
        label(f, "What the learners can choose from. Drag a slider, then let go: a robot outside the new limits\n"
                 "is pulled back to the nearest value allowed. Your own design can use every range in full.",
              0.82, y, 0.02, GREY)
        y -= 0.085

        def row(group, key, text, yy, lo_full, hi_full, value):
            label(f, text, 0.82, yy, 0.027)
            for which, x in ((0, 1.17), (1, 1.53)):
                s = DirectSlider(parent=f, range=(lo_full, hi_full), value=value[which], pageSize=5, scale=0.13,
                                 pos=(x, 0, yy + 0.008), command=self.limit_moved, extraArgs=[group, key, which],
                                 thumb_frameSize=(-0.05, 0.05, -0.16, 0.16))
                self.limit_sliders[(group, key, which)] = (s, label(f, f"{value[which]:g}", x + 0.145, yy, 0.026))

        for group, title, unit in (("settings", "SETTINGS  (percent)", "%"), ("points", "POINTS", "")):
            label(f, title, 0.82, y, 0.03, YELLOW)
            label(f, "lowest", 1.17, y, 0.024, GREY, TextNode.ACenter)
            label(f, "highest", 1.53, y, 0.024, GREY, TextNode.ACenter)
            y -= 0.055
            for key in limits[group]:
                row(group, key, self.pretty(key), y, *full[group][key], limits[group][key])
                y -= 0.055
            y -= 0.02
        label(f, "Points to share", 0.82, y, 0.027)
        s = DirectSlider(parent=f, range=(0, full["points_total"]), value=limits["points_total"], pageSize=20, scale=0.13,
                         pos=(1.17, 0, y + 0.008), command=self.limit_moved, extraArgs=["points_total", None, 0],
                         thumb_frameSize=(-0.05, 0.05, -0.16, 0.16))
        self.limit_sliders[("points_total", None, 0)] = (s, label(f, str(limits["points_total"]), 1.315, y, 0.026))
        y -= 0.08
        # (CHANGE 62) the standard limit is 50: each setting from its lowest up to 50% (size from 50% up to its
        # highest), each point 5 to 50. A robot outside the new limits is pulled back to the nearest value allowed.
        standard = {"settings": {k: ([50, v[1]] if k == "size" else [v[0], 50]) for k, v in self.rules["settings"].items()},
                    "points": {k: [self.rules["stat_min"], self.rules["stat_max"]] for k in self.rules["stats"]},
                    "points_total": self.rules["points_total"]}
        button(f, "Standard limits (50)", 0.97, y, self.set_lesson, [{"limits": standard}], 0.028)
        label(f, self.LIMITS_NOTE, 0.82, y - 0.06, 0.022, GREY)

    def limit_moved(self, group, key, which):
        """A limit's slider is being dragged: its number follows, and its lowest never passes its highest (the
        other slider is pushed along). Nothing is sent until the slider is let go (see tick)."""
        if (group, key, which) not in self.limit_sliders or self.limits_draft is None:
            return  # (the slider is still being made)
        s, text = self.limit_sliders[(group, key, which)]
        if group == "points_total":
            v = int(round(s["value"] / 5) * 5)
            if v != self.limits_draft["points_total"]:
                self.limits_draft["points_total"], self.limits_moved = v, True
            text.setText(str(v))
            return
        lo_full, hi_full = (self.full_limits())[group][key]
        v = max(lo_full, min(hi_full, int(round(s["value"]))))
        pair = self.limits_draft[group][key]
        if v == pair[which]:
            return
        pair[which], self.limits_moved = v, True
        text.setText(f"{v:g}")
        other = 1 - which
        if (pair[0] > pair[1]) and (group, key, other) in self.limit_sliders:
            pair[other] = v
            s2, text2 = self.limit_sliders[(group, key, other)]
            s2["value"] = v
            text2.setText(f"{v:g}")

    def limits_released(self):
        """Each frame: a limit's slider let go sends the new limits to the class server."""
        if self.limits_moved and not (self.mouseWatcherNode is not None and
                                      self.mouseWatcherNode.is_button_down(MouseButton.one())):
            self.limits_moved = False
            self.set_lesson({"limits": self.limits_draft})

    def full_limits(self):
        """The widest ranges (the game's)."""
        return self.rules.get("full") or self.default_limits()

    def default_limits(self):
        """The standard ranges (the game's)."""
        return {"settings": {k: [v[0], v[1]] for k, v in self.rules["settings"].items()},
                "points": {k: [self.rules["stat_min"], self.rules["stat_max"]] for k in self.rules["stats"]},
                "points_total": self.rules["points_total"]}

    def pretty(self, key):
        """A setting's name as the Limits tab shows it (the game may have nicer ones)."""
        return key.replace("_", " ").capitalize()
