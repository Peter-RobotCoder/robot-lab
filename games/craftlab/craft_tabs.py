"""Craft Lab's side panel of lesson tabs (CHANGE 206), on the engine's HUD kit (engine/hud.py) and lesson tabs
(engine/lesson_tabs.py), as the other games' windows have them. Tab opens and closes it (the mouse is let go while it
is open, so you can click in it).

    a learner   Mission (the lesson's missions, each objective ticked as it is done, the guidance, the written
                answers), AI card (a request to the teacher: My Craft Bot, The world, The rules), My card (the outcomes
                shown, what was done each session), Settings (text size, the look, the window)
    the teacher Controls (the mission, show the learners their Mission tab, Challenge or Sandbox, creatures,
                Energy, the time of day, the rules: keep your things, Overload Cells, falls hurt; everyone to me, a Bot kit
                each, pause; locking designs, what learners can change, user mods, the restart row), User mods,
                Warnings, Limits, Settings. The class's Learners, Outcomes, AI cards and Changes are on the
                teacher's page.

The Craft Bot's own panels (craft_panels.py: the Garage, the code, the brain) open from the Backpack's Bot tab (B).
"""
from direct.gui.DirectGui import DirectFrame

from engine import hud, lesson_tabs
from engine.hud import GREY, OFF, ON, PANEL, YELLOW, button, check, label

import craft_design as design
import craft_missions as cm

LEARNER_TABS = [("missions", "Mission"), ("ai", "AI card"), ("card", "My card"), ("settings", "Settings")]
TEACHER_TABS = [("teacher", "Controls"), ("mods", "User mods"), ("warnings", "Warnings"), ("limits", "Limits"),
                ("settings", "Settings")]
OFFLINE_TABS = [("settings", "Settings")]
PRETTY = {"points_table": "Points table", "dig": "Dig points", "build": "Build points", "speed": "Speed points",
          "name_and_colour": "Name and colour", "code_view": "Code view", "stats_readout": "Stats readout",
          "brains": "Brains (U and P)"}
HAZARD_NAMES = {"mobs": "Creatures (Glitch rifts at dusk, Rust Walkers)", "energy": "Energy drains as you work"}
RULE_NAMES = (("keep_items", "Keep your things when knocked out"), ("blasts", "Overload Cells"),
              ("falls_hurt", "Falls hurt"))
TIMES = (("cycle", "Day and night"), ("dawn", "Dawn"), ("day", "Day"), ("dusk", "Dusk"), ("night", "Night"))
send = lesson_tabs.send


class CraftTabs(lesson_tabs.LessonTabs):
    """The lesson tabs' drawing and buttons: a mixin for the Craft Lab window, before hud.HudKit."""
    FIRST_TAB = "missions"
    AI_TARGETS = cm.AI_TARGETS
    reflections = tuple(cm.REFLECTIONS)
    STAGE_WORD = "WORLD"
    LIMITS_TITLE = "LIMITS"
    LIMITS_NOTE = "The points each learner's Craft Bot shares, and each one's range."
    offline = False

    def init_tabs(self, lesson):
        self.tabs_on = True
        self.lesson = self.fill_lesson(lesson)
        self.tab = None
        self.mod_info, self.class_list = {}, []
        self.init_lesson_tabs()

    def fill_lesson(self, lesson):
        L = {"lesson_number": 1, "game_mode": "challenge", "time": "cycle", "rules": {}, "hazards": {}, "tools": {},
             "limits": None, "designs_locked": False, "teacher_player": True, "show_missions": False,
             "ai_card_note": "", "user_mods": {}, "mods_in_vote": {}, "arena_in_vote": {}}
        L.update(lesson or {})
        return L

    def my_tabs(self):
        return OFFLINE_TABS if self.offline else TEACHER_TABS if self.teacher else LEARNER_TABS

    def full_limits(self):
        return design.full_limits()

    def default_limits(self):
        return design.default_limits()

    def pretty(self, key):
        return PRETTY.get(key, key.replace("_", " ").capitalize())

    def open_tab(self, tab):
        self.tab = None if self.tab == tab else tab
        self.rebuild_panels()

    def rebuild_panels(self, from_game=False):
        if not getattr(self, "tabs_on", False):
            return
        if from_game and self.typing:
            self.pending_rebuild = True
            return
        self.pending_rebuild = False
        self.keep_typing()
        self.hide_tip()
        if self.panel is not None:
            self.panel.destroy()
        self.panel = self.panel_body = None
        self.panel_bar = []
        if self.tab:
            f = self.panel = DirectFrame(frameColor=PANEL, frameSize=(0.78, 1.76, -0.93, 0.97))
            tabs = self.my_tabs() + ([] if self.offline else hud.extra_tabs(self.teacher))
            f, y0 = self.draw_header(f, tabs, self.open_tab, self.tab,
                                     lambda key, text: self.warnings_tab_text(text) if key == "warnings" else text)
            builders = {"missions": self.build_missions, "ai": self.build_ai_card, "card": self.build_card,
                        "settings": self.build_settings, "teacher": self.build_teacher_panel, "mods": self.build_mods,
                        "warnings": self.build_warnings, "limits": self.build_limits}
            if self.tab in builders:
                builders[self.tab](f, y0)
            elif hud.extra_builder(self.tab) is not None:
                hud.extra_builder(self.tab)(self, f, y0)
            self.place_panel()
        elif self.typing and self.typing not in self.entries:
            self.typing = None
        if hasattr(self, "tabs_shown"):
            self.tabs_shown(bool(self.tab))

    # ---------- the teacher's Controls ----------
    def build_teacher_panel(self, f, y):
        L = self.lesson
        label(f, "Mission", 0.82, y, 0.03, YELLOW)
        for i, n in enumerate(sorted(cm.LESSONS)):
            button(f, str(n), 1.0 + i * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.028,
                   ON if L.get("lesson_number") == n else OFF)
        y -= 0.06
        check(f, "Show learners their Mission tab (pauses the game)", 0.84, y, L.get("show_missions"),
              lambda v: self.set_lesson({"show_missions": bool(v)}), 0.024)
        y -= 0.05
        label(f, "The class", 0.82, y, 0.028, YELLOW)
        button(f, "Everyone to me", 1.08, y + 0.008, send, [{"type": "gather"}], 0.022)
        button(f, "A Bot kit each", 1.33, y + 0.008, send, [{"type": "kit"}], 0.022)
        button(f, "Pause", 1.56, y + 0.008, send, [{"type": "pause"}], 0.022)
        y -= 0.055
        label(f, "Learners play", 0.82, y, 0.028, YELLOW)
        for i, (key, text) in enumerate((("challenge", "Challenge"), ("sandbox", "Sandbox"))):
            button(f, text, 1.1 + i * 0.2, y + 0.008, self.set_lesson, [{"game_mode": key}], 0.024,
                   ON if L.get("game_mode", "challenge") == key else OFF)
        y -= 0.055
        label(f, "Time", 0.82, y, 0.028, YELLOW)
        for i, (key, text) in enumerate(TIMES):
            button(f, text, 0.98 + i * 0.16 + (0.04 if i else 0), y + 0.008, self.set_lesson, [{"time": key}], 0.021,
                   ON if L.get("time", "cycle") == key else OFF)
        y -= 0.055
        haz = L.get("hazards") or {}
        for i, (key, text) in enumerate(HAZARD_NAMES.items()):
            check(f, text, 0.84, y - i * 0.045, haz.get(key, False),
                  lambda v, k=key: self.set_lesson({"hazards": {k: bool(v)}}), 0.024)
        y -= 0.045 * len(HAZARD_NAMES) + 0.01
        label(f, "Rules", 0.82, y, 0.028, YELLOW)
        y -= 0.045
        rules = L.get("rules") or {}
        for i, (key, text) in enumerate(RULE_NAMES):
            check(f, text, 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.043, rules.get(key, key != "blasts"),
                  lambda v, k=key: self.set_lesson({"rules": {k: bool(v)}}), 0.022)
        y -= 0.043 * ((len(RULE_NAMES) + 1) // 2) + 0.01
        check(f, "Lock designs", 0.84, y, L.get("designs_locked"), lambda v: self.set_lesson({"designs_locked": bool(v)}),
              0.024)
        check(f, "Me in the world", 1.3, y, L.get("teacher_player", True),
              lambda v: self.set_lesson({"teacher_player": bool(v)}), 0.024)
        y -= 0.055
        label(f, "User mods  (learners' ideas: on or off at any time)", 0.82, y, 0.028, YELLOW)
        y -= 0.043
        mods_on = L.get("user_mods", {})
        if not self.user_mods:
            label(f, "None yet. An AI card sent as 'The whole game' can be made a switchable User Mod.", 0.84, y + 0.01,
                  0.019, GREY)
        for i, (key, (mod_name, _)) in enumerate(self.user_mods.items()):
            check(f, " " + mod_name, 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.043, mods_on.get(key),
                  lambda v, k=key: self.set_lesson({"user_mods": {k: bool(v)}}), 0.026)
        y -= 0.043 * max(1, (len(self.user_mods) + 1) // 2)
        label(f, "Learners can see and change", 0.82, y, 0.026, YELLOW)
        y -= 0.045
        keys = [k for k in cm.ALL_TOOLS + ["brains"] if k in (L.get("tools") or {})]
        for i, k in enumerate(keys):
            check(f, self.pretty(k), 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.041, L["tools"].get(k, True),
                  lambda v, k=k: self.set_lesson({"tools": {k: bool(v)}}), 0.024)
        y -= 0.041 * ((len(keys) + 1) // 2) + 0.02
        label(f, "Learners, Outcomes, AI cards and Changes: the teacher's page (the club desk's Open page).", 0.82, y,
              0.02, GREY, wrap=48)
        y -= 0.06
        self.restart_row(f, y)

    def stage_items(self):
        """The world's hazards, for the User mods tab: the creatures and Energy."""
        L = self.lesson
        return [(hz, HAZARD_NAMES.get(hz, hz.replace("_", " ").capitalize()), bool(on),
                 lambda v, k=hz: self.set_lesson({"hazards": {k: bool(v)}}))
                for hz, on in (L.get("hazards") or {}).items()]

    def took_lesson(self, m):
        new = self.fill_lesson(m.get("lesson") or {})
        rebuild = new != self.lesson and self.tab in ("teacher", "missions", "limits", "mods", "ai")
        mods = m.get("mods") or {}
        if mods != self.mod_info:
            rebuild = rebuild or self.tab in ("teacher", "mods")
            self.mod_info = mods
        self.show_missions_changed(self.lesson, new)
        self.lesson = new
        if rebuild:
            self.rebuild_panels(from_game=True)

