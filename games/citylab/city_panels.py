"""City Lab's side panel (docs/plans/city-lab.md step 6): the window's tabs, on the engine's HUD kit (engine/hud.py),
as Kart Lab's window has them.

    a learner   Mission (the lesson's missions, their objectives and guidance, the predicted delivery time, the
                written answers), Garage (the driver and car as variables: driver_name, car, look, colour and the
                100 points between speed, acceleration and grip), AI card (a request to the teacher: what should
                change, the idea, the variables, the test, the prediction, the three promises), My card (the
                outcomes shown and what was done each session), Settings (text size, the look, the window,
                the graphics)
    the teacher Controls (the mission, the city, the traffic, the robots, the parked cars, the computer's racers and
                their level, the jobs, the time of day, damage, START A STREET RACE, what learners can change),
                My driver (the teacher's own garage), User mods, Warnings, Limits, Settings. The class's Learners,
                Outcomes, AI cards and Changes are on the teacher's page (club-coders/web), which speaks the same
                messages to every game's server.
    offline     Garage and Settings.

    I or Tab opens and closes the panel, C the code panel (the design as Python: change it there and APPLY CODE or
    BUILD MY DRIVER), U uploads brains/my_brain.py and P switches the autopilot on and off.

The server (city_server.py, its teaching layer city_teaching.py) checks every build, holds it to the teacher's
limits and tells the teaching layer, which ticks the objectives. Offline the build is checked here.
"""
import copy
import os
from types import SimpleNamespace

from direct.gui.DirectGui import DGG, DirectFrame
from panda3d.core import TextNode

from engine import editor as code_editor
from engine import garage, hud, lesson_tabs, schema
from engine.hud import (GREEN, GREY, OFF, ON, ORANGE, PANEL, RED, WHITE, YELLOW, button, check, label,
                        remember)

import city_map
import city_missions as cm
import city_sim as sim
import cpu_brains

LEARNER_TABS = [("missions", "Mission"), ("garage", "Garage"), ("ai", "AI card"), ("card", "My card"),
                ("settings", "Settings")]
TEACHER_TABS = [("teacher", "Controls"), ("garage", "My driver"), ("mods", "User mods"), ("warnings", "Warnings"),
                ("limits", "Limits"), ("settings", "Settings")]
OFFLINE_TABS = [("garage", "Garage"), ("settings", "Settings")]
PRETTY = {"points_table": "Points table", "speed": "Top speed", "acceleration": "Acceleration", "grip": "Grip",
          "name_and_colour": "Name, car, look, colour", "code_view": "Code view (C)", "stats_readout": "Stats readout",
          "traffic": "Traffic", "brains": "Brains (U and P)"}
TOOL_ORDER = list(cm.ALL_TOOLS) + ["traffic", "brains"]
HAZARD_NAMES = {"traffic": "Traffic (the computer's cars)", "robots": "Robots on the pavements"}
JOB_NAMES = (("delivery", "Deliveries"), ("taxi", "Taxi"), ("race", "Street race"), ("roundup", "Round-up"))


def send(msg):
    if hud.SEND is not None:
        hud.SEND(msg)


def stats_text(design):
    """What the points buy a car, in words (the garage's stats readout): Kart Lab's sums, city_sim.stats_of."""
    st = sim.stats_of(design)
    to50 = (50 / 3.6) / max(0.1, st["accel"])
    return (f"Top speed {st['top'] * 3.6:.0f} km/h    0 to 50 km/h in {to50:.1f} s\n"
            f"Steering {st['steer']:.0f} degrees a second    a slide dies in {1 / max(0.1, st['grip']):.2f} s")


class CityPanels(lesson_tabs.LessonTabs):
    """The tabs' drawing and what their buttons do: a mixin for the City Lab window, before hud.HudKit."""
    FIRST_TAB = "missions"
    UNIT = "driver"
    STAGE_WORD = "CITY"
    LIMITS_TITLE = "LIMITS"
    LIMITS_NOTE = "The points each learner shares, and each one's range."
    CODE_PANEL = (-0.86, 0.12, -0.85, 0.36)
    CODE_ROWS = 19
    reflections = tuple(cm.REFLECTIONS)
    AI_TARGETS = cm.AI_TARGETS
    offline = False

    def init_panels(self, design, lesson, rules):
        """Once, when the city starts: the design being edited and everything the tabs keep."""
        self.panels_on = True
        self.schema = sim.schema()
        self.design = sim.fit_design(dict(design))
        self.draft = copy.deepcopy(self.design)
        self.lesson = self.fill_lesson(lesson)
        self.rules = dict(rules or {})
        self.tab = None
        self.show_code = False
        self.code_state = {"lines": [], "cursor": [0, 0], "scroll": 0}
        self.code_shown, self.code_msg = None, ("", GREY)
        self.code_changed = self.code_hack = False
        self.status_msg = ("", WHITE)
        self.init_lesson_tabs()
        self.class_list, self.mod_info = [], {}
        self.my_name = getattr(self, "my_name", "") or self.design.get("name", "")

    def fill_lesson(self, lesson):
        """The lesson as the panels need it, whatever the server sent (defaults for anything missing)."""
        L = {"lesson_number": 1, "city": city_map.DEFAULT_CITY, "traffic": 6, "robots": 6, "parked": 10, "racers": 2,
             "cpu_level": "medium", "tools": {}, "limits": None, "hazards": {}, "jobs": {k: True for k, _ in JOB_NAMES},
             "designs_locked": False, "damage": True, "time": "day", "show_missions": False, "ai_card_note": "",
             "saved_missions": [], "mode": "practice", "user_mods": {}, "mods_in_vote": {}, "arena_in_vote": {}}
        L.update(lesson or {})
        tools = {k: True for k in TOOL_ORDER}
        tools.update(L.get("tools") or {})
        L["tools"] = tools
        return L

    # ---------- which design the garage and the code panel are editing ----------
    def viewing(self):
        return None  # (the teacher's Learner view is on the teacher's page)

    def cur(self):
        return self.draft

    def tools(self):
        if self.teacher or self.offline:
            return {k: True for k in self.lesson["tools"]}
        return self.lesson["tools"]

    def full_limits(self):
        return sim.full_limits()

    def default_limits(self):
        return sim.default_limits()

    def limits(self):
        if self.teacher or self.offline:
            return self.full_limits()
        return self.lesson.get("limits") or self.default_limits()

    def pretty(self, key):
        return PRETTY.get(key, key.replace("_", " ").capitalize())

    def name_key(self):
        return "name_me"

    def my_tabs(self):
        return OFFLINE_TABS if self.offline else TEACHER_TABS if self.teacher else LEARNER_TABS

    # ---------- the panel ----------
    def open_tab(self, tab):
        self.tab = None if self.tab == tab else tab
        self.code_shown = None
        self.rebuild_panels()

    def toggle_code(self):
        self.show_code = not self.show_code
        if self.show_code and not self.teacher and not self.offline:
            send({"type": "code_viewed"})
        self.rebuild_panels()

    def rebuild_panels(self, from_game=False):
        """Redraw the side panel and the code panel. A redraw the game causes waits while you are typing."""
        if not getattr(self, "panels_on", False):
            return
        if from_game and self.typing:
            self.pending_rebuild = True
            return
        self.pending_rebuild = False
        self.keep_typing()
        self.close_code_editor()
        self.hide_tip()
        for p in (self.panel, self.code_panel):
            if p is not None:
                p.destroy()
        self.panel = self.code_panel = self.panel_body = None
        self.panel_bar = []
        if self.tab:
            f = self.panel = DirectFrame(frameColor=PANEL, frameSize=(0.78, 1.76, -0.93, 0.97))
            tabs = self.my_tabs() + ([] if self.offline else hud.extra_tabs(self.teacher))
            f, y0 = self.draw_header(f, tabs, self.open_tab, self.tab,
                                     lambda key, text: self.warnings_tab_text(text) if key == "warnings" else text)
            builders = {"garage": self.build_garage, "teacher": self.build_teacher_panel, "missions": self.build_missions,
                        "ai": self.build_ai_card, "card": self.build_card, "settings": self.build_settings,
                        "mods": self.build_mods, "warnings": self.build_warnings, "limits": self.build_limits}
            if self.tab in builders:
                builders[self.tab](f, y0)
            elif hud.extra_builder(self.tab) is not None:
                hud.extra_builder(self.tab)(self, f, y0)
            self.place_panel()
        if self.show_code and (self.teacher or self.offline or self.lesson["tools"].get("code_view", True)):
            self.build_code_panel()
        if self.typing == "code" and self.code_editor is not None:
            self.code_editor.focused = True
            self.code_editor.refresh()
        elif self.typing and self.typing not in self.entries:
            self.typing = None
        if hasattr(self, "panel_shown"):  # (the window moves what the panel covers)
            self.panel_shown(bool(self.tab))

    def panel_wheel(self, factor, step):
        """The mouse wheel: over a side panel taller than the screen it slides the panel; elsewhere it zooms."""
        at = self.mouse_at()
        s = self.text_scale()
        if self.panel is not None and at is not None and at[0] > 1.76 - 0.98 * s and self.panel_bar:
            self.panel_scroll += 0.12 * step * (-1 if self.invert_scroll else 1)
            self.place_panel()
        elif self.code_editor is None or not self.code_editor.focused:
            self.zoom(1 / factor if self.invert_zoom else factor)

    # ---------- the garage ----------
    def build_garage(self, f, y, view=None):
        tools, d = self.tools(), self.cur()
        label(f, "MY DRIVER AND CAR" if self.teacher else "GARAGE  -  your driver and car as variables", 0.82, y,
              0.038, YELLOW)
        y -= 0.05
        limits = self.limits()
        label(f, f"{limits['points_total']} points between top speed, acceleration and grip: every choice is a "
                 "trade-off. They go with you into any car you drive.", 0.82, y, 0.021, GREY, wrap=46)
        y -= 0.07
        y = garage.draw(self, f, y, d, self.schema, self.code_ctx(d), tools, limits, None, None, teacher=self.teacher)
        self.stats_text = None
        if tools.get("stats_readout", True):
            self.stats_text = label(f, stats_text(d), 0.82, y - 0.005, 0.022, GREEN, wrap=46)
            y -= 0.1
        if not self.offline:
            y = self.build_slots(f, y, None)  # (five saved designs: the engine's)
        button(f, "BUILD MY DRIVER", 1.27, y, self.send_design, None, 0.038, (0.15, 0.55, 0.25, 1))
        self.garage_msg = label(f, self.status_msg[0], 0.82, y - 0.06, 0.024, self.status_msg[1], wrap=40)
        if self.lesson.get("designs_locked") and not self.teacher:
            label(f, "Designs are locked by the teacher", 0.82, y - 0.12, 0.026, RED)

    def set_colour(self, colour):
        self.cur()["colour"] = list(colour)
        self.code_shown = None
        self.rebuild_panels()

    def change_points(self, stat, delta):
        d = self.cur()
        lo, hi = self.limits()["points"].get(stat, [sim.STAT_MIN, sim.STAT_MAX])
        pts = d.setdefault("points", {})
        pts[stat] = max(lo, min(hi, int(pts.get(stat, lo)) + delta))
        self.code_shown = None
        self.rebuild_panels()

    def slider_moved(self, k):  # (City Lab's design has no percentage settings; the engine's garage may still ask)
        s, text = self.sliders[k]
        self.cur().setdefault("settings", {})[k] = int(round(s["value"]))
        text.setText(f"{self.cur()['settings'][k]:g}%")

    def take_design(self, design):
        """A saved design loaded into the garage (the engine's slots)."""
        self.draft = sim.fit_design(dict(design))
        self.code_shown = None

    def send_design(self):
        """BUILD MY DRIVER: the design goes to the server (which checks it and tells the teaching layer); offline it
        is used at once."""
        if self.name_key() in self.entries and self.tools().get("name_and_colour", True):
            self.draft["name"] = self.entries[self.name_key()].get()[:sim.NAME_MAX]
        if self.offline:
            problems = sim.check_design(self.draft, self.limits())
            if problems:
                self.status_msg = ("Not built: " + "; ".join(problems[:3]), RED)
            else:
                self.design = sim.fit_design(copy.deepcopy(self.draft))
                self.draft = copy.deepcopy(self.design)
                remember("city_design", self.design)
                self.built_offline(self.design)
                self.status_msg = ("Built!", GREEN)
                self.code_shown = None
            self.rebuild_panels()
            return
        send({"type": "design", "design": self.draft, "code": bool(self.code_changed or self.code_hack)})
        self.status_msg = ("Building...", GREY)
        if self.tab == "garage" and getattr(self, "garage_msg", None) is not None:
            self.garage_msg.setText("Building...")

    def design_result(self, m):
        """The server's answer to a build (or the teacher changed this learner's design)."""
        if m.get("design"):
            self.design = sim.fit_design(dict(m["design"]))
        self.code_changed = self.code_hack = False
        if m.get("ok", True):
            self.draft = copy.deepcopy(self.design)
            self.code_shown = None
            self.entry_text.pop(self.name_key(), None)
            self.status_msg = ("Your teacher changed your driver." if m.get("by_teacher") else
                               "Built! Your driver and car have their new design.", GREEN)
            if m.get("by_teacher"):
                self.note("Your teacher changed your driver", 4)
            remember("city_design", self.design)
        else:
            self.status_msg = ("Not built: " + "; ".join(m.get("problems", [])), RED)
        if self.tab == "garage" or self.show_code:
            self.rebuild_panels(from_game=True)

    # ---------- the code panel: the design as Python ----------
    def code_ctx(self, d=None):
        return SimpleNamespace(title="MY DRIVER", points_total=self.limits()["points_total"],
                               design=d if d is not None else self.cur(), rules=self.rules)

    def code_lines(self, d):
        return schema.code_lines(self.schema, d, self.code_ctx(d))

    def build_code_panel(self):
        d = self.cur()
        self.code_size = self.code_fit(*self.code_size)
        self.code_at = self.code_place(*self.code_at)
        f, (left, right, bottom, top) = self.code_panel_top("driver")
        st, fresh = self.code_state, self.code_lines(d)
        if self.code_shown is None or st["lines"] == self.code_shown:  # not edited: the design as it is now
            st["lines"][:] = fresh
            self.code_shown = list(fresh)
        self.code_editor = code_editor.CodeEditor(self, f, st, -0.845, 0.21, right - left - 0.03, self.code_rows(),
                                                  0.024 * self.text_scale(), on_enter=self.apply_code,
                                                  on_focus=self.type_code)
        self.code_more = label(f, "", right - 0.02, 0.243, 0.019, code_editor.DIM, TextNode.ARight)
        self.code_editor.on_scroll = self.show_code_more
        self.show_code_more()
        button(f, "APPLY CODE", -0.64, bottom + 0.178, self.apply_code, None, 0.03, (0.15, 0.55, 0.25, 1))
        button(f, "RESET CODE", -0.36, bottom + 0.178, self.reset_code, None, 0.03)
        button(f, "BUILD MY DRIVER", -0.6, bottom + 0.112, self.build_from_code, None, 0.03, (0.15, 0.55, 0.25, 1))
        label(f, self.code_msg[0], -0.83, bottom + 0.055, 0.021, self.code_msg[1], wrap=39 + self.code_size[0] / 0.021)
        grip = DirectFrame(parent=f, frameColor=(0.35, 0.4, 0.5, 1), state=DGG.NORMAL,
                           frameSize=(right - 0.045, right, bottom, bottom + 0.045))
        grip.bind(DGG.B1PRESS, self.code_resize_start)
        label(f, "drag to resize", right - 0.055, bottom + 0.012, 0.015, GREY, TextNode.ARight)

    def show_code_more(self):
        above, below = self.code_editor.hidden()
        self.code_more.setText("" if not (above or below) else f"{above} lines above, {below} below")

    def close_code_editor(self):
        if self.code_editor is not None:
            self.code_editor.destroy()
            self.code_editor = None

    def refresh_code_panel(self):
        self.close_code_editor()
        if self.code_panel is not None:
            self.code_panel.destroy()
        self.build_code_panel()
        if self.typing == "code":
            self.code_editor.focused = True
            self.code_editor.refresh()

    def reset_code(self):
        self.code_state["lines"][:] = self.code_lines(self.cur())
        self.code_state["cursor"][:], self.code_state["scroll"] = [0, 0], 0
        self.code_shown = list(self.code_state["lines"])
        self.code_msg = ("The code is back to your driver as it is. Press APPLY CODE or BUILD to use it.", GREY)
        self.refresh_code_panel()

    def build_from_code(self):
        if self.apply_code():
            self.send_design()

    def outside_limits(self, values):
        """Each value in the code stays within the teacher's limits (the points total is the server's to check)."""
        limits, out = self.limits(), []
        for var in self.schema:
            if var.name not in values or var.group not in ("points", "settings"):
                continue
            rng = limits.get(var.group, {}).get(var.path[-1])
            v = values[var.name]
            if not rng or not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            if v > rng[1]:
                out.append(f"value too high for {var.name} (most allowed: {rng[1]:g})")
            elif v < rng[0]:
                out.append(f"value too low for {var.name} (least allowed: {rng[0]:g})")
        return out

    def apply_code(self):
        """Read the edited code as data (never run it) and change the design to match. True if all of it was used.
        Everything in the code can be changed, even what this mission's garage hides; the server holds the design
        to the rules all the same, and tells the teacher what was changed."""
        text = "\n".join(self.code_state["lines"])
        d = self.cur()
        ctx = self.code_ctx(d)
        try:
            values = schema.parse_code(text, self.schema, ctx)
        except schema.ParseError as e:
            self.code_msg = (f"Line {e.lineno}: {e.message}", RED)
            if e.lineno:
                self.code_state["cursor"][:] = [e.lineno - 1, 0]
                self.code_state["scroll"] = max(0, e.lineno - self.code_rows())
            self.refresh_code_panel()
            return False
        tools = self.tools()
        refused = self.outside_limits(values)
        if refused:
            self.code_msg = ("Unable to compile: " + "; ".join(refused[:2]), RED)
            self.code_shown = None
            self.rebuild_panels()
            return False
        changed, hidden, problems = schema.apply_values(self.schema, d, values, ctx,
                                                        lambda var, value: bool(tools.get(var.tool, True)))
        if changed:
            self.code_changed = True  # (the next build is sent as the code's: mission 1 d, hack the code)
        if hidden:
            self.code_hack = True
        if "driver_name" in changed:
            self.entry_text.pop(self.name_key(), None)
            if self.name_key() in self.entries:
                self.entries[self.name_key()].enterText(d["name"])
        problems += sim.check_design(d, self.limits())
        self.code_msg = (("Applied, but: " + "; ".join(problems[:3]), ORANGE) if problems else
                         ("Applied: the garage shows your changes. Press BUILD to use them.", GREEN))
        self.code_shown = None
        self.rebuild_panels()
        return not problems

    # ---------- missions ----------
    def build_missions(self, f, y, m=None, preview=False):
        """The engine's Mission tab, with City Lab's own row under it in mission 2: the delivery time a learner
        predicts before driving one (predict, test, compare)."""
        hud.HudKit.build_missions(self, f, y, m, preview)
        m = m or self.missions
        if not m or preview:
            return
        if m.get("lesson") == 2 or m.get("prediction") is not None:
            y = self.body_bottom(y) - 0.07
            label(f, "My predicted delivery time", 0.82, y, 0.028, YELLOW)
            y -= 0.045
            have = m.get("prediction")
            label(f, "Look at your car's points, then predict how many seconds a delivery from the DEPOT will take. "
                     "Deliver one, then compare.", 0.82, y, 0.021, GREY, wrap=46)
            y -= 0.075
            self.entry(f, "predict_delivery", 0.84, y, 6, initial="" if have is None else f"{have:g}", scale=0.03)
            label(f, "seconds", 1.1, y, 0.024, GREY)
            button(f, "Save", 1.3, y + 0.008, self.send_prediction, None, 0.026, (0.15, 0.55, 0.25, 1))
            if have is not None:
                best = m.get("best_delivery")
                label(f, f"Predicted: {have:g} s" + (f"   your quickest delivery: {best:.1f} s" if best else ""),
                      0.84, y - 0.05, 0.023, GREEN)

    def send_prediction(self):
        text = self.entries["predict_delivery"].get().strip() if "predict_delivery" in self.entries else ""
        try:
            value = float(text)
        except ValueError:
            self.note("Type the seconds you predict a delivery will take (for example 40)", 4)
            return
        send({"type": "prediction", "value": value})

    # ---------- brains: U uploads, P switches the autopilot ----------
    def panel_note(self, text, secs=4):
        self.note(text, secs)

    def brains_on(self):
        if self.teacher or self.offline or self.lesson.get("tools", {}).get("brains", True):
            return True
        self.note("Brains aren't switched on for this mission yet.", 3)
        return False

    def upload_brain(self):
        if self.offline:
            return self.note("Offline there is no brain: log in to a City Lab server to use one", 5)
        if not self.brains_on():
            return
        for path in (os.path.join(self.brains_dir, f"{self.my_name}.py"), os.path.join(self.brains_dir, "my_brain.py")):
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    send({"type": "brain", "source": fh.read()})
                self.note(f"Uploading {os.path.basename(path)}...")
                return
        self.note(f"No brain file: make {os.path.join(self.brains_dir, 'my_brain.py')} first", 5)

    def autopilot_key(self):
        if self.offline:
            return self.note("Offline there is no autopilot: log in to a City Lab server to use one", 5)
        if not self.brains_on():
            return
        if not (self.missions or {}).get("brain"):
            return self.note("Upload a brain first (U)", 3)
        send({"type": "autopilot", "on": not self.autopilot})

    # ---------- the teacher's Controls ----------
    def build_teacher_panel(self, f, y):
        L = self.lesson
        label(f, "Mission", 0.82, y, 0.03, YELLOW)
        for i, n in enumerate(sorted(cm.LESSONS)):
            button(f, str(n), 1.0 + i * 0.09, y + 0.008, send, [{"type": "lesson_number", "n": n}], 0.028,
                   ON if L.get("lesson_number") == n else OFF)
        button(f, "Save settings", 1.5, y + 0.008, send, [{"type": "save_lesson"}], 0.024)
        button(f, "Restore", 1.68, y + 0.008, send, [{"type": "restore_lesson"}], 0.024)
        saved = L.get("saved_missions") or []
        if saved:
            label(f, "saved settings: mission " + ", ".join(str(n) for n in saved), 1.74, y - 0.037, 0.015, GREY,
                  TextNode.ARight)
        y -= 0.06
        check(f, "Show learners their Mission tab (pauses the city)", 0.84, y, L.get("show_missions"),
              lambda v: self.set_lesson({"show_missions": bool(v)}), 0.024)
        y -= 0.05
        label(f, "Street race", 0.82, y, 0.028, YELLOW)
        button(f, "START A STREET RACE", 1.12, y + 0.008, send, [{"type": "start"}], 0.026, (0.15, 0.55, 0.25, 1))
        button(f, "Everyone to the depot", 1.45, y + 0.008, send, [{"type": "grid"}], 0.022)
        button(f, "Pause", 1.67, y + 0.008, send, [{"type": "pause"}], 0.022, ON if self.paused else OFF)
        y -= 0.055
        racers = int(L.get("racers", 2))
        label(f, f"Computer racers {racers}", 0.84, y, 0.024)
        button(f, "-", 1.16, y + 0.008, self.set_lesson, [{"racers": racers - 1}], 0.024)
        button(f, "+", 1.24, y + 0.008, self.set_lesson, [{"racers": racers + 1}], 0.024)
        level = L.get("cpu_level", "medium")
        for i, key in enumerate(cpu_brains.LEVELS):
            button(f, key.title(), 1.36 + i * 0.13, y + 0.008, self.set_lesson, [{"cpu_level": key}], 0.021,
                   ON if level == key else OFF)
        y -= 0.06
        label(f, "City", 0.82, y, 0.028, YELLOW)
        for i, (key, c) in enumerate(city_map.CITIES.items()):
            button(f, c["name"], 1.0 + i * 0.24, y + 0.008, self.set_lesson, [{"city": key}], 0.022,
                   ON if L.get("city") == key else OFF)
        y -= 0.055
        for i, (key, text, hi) in enumerate((("traffic", "Traffic cars", 30), ("robots", "Robots", 20),
                                             ("parked", "Parked cars", 40))):
            n = int(L.get(key, 0))
            x = 0.84 + i * 0.31
            label(f, f"{text} {n}", x, y, 0.022)
            button(f, "-", x + 0.2, y + 0.008, self.set_lesson, [{key: max(0, n - 1)}], 0.022)
            button(f, "+", x + 0.26, y + 0.008, self.set_lesson, [{key: min(hi, n + 1)}], 0.022)
        y -= 0.055
        haz = L.get("hazards") or {}
        for i, (key, text) in enumerate(HAZARD_NAMES.items()):
            check(f, text, 0.84 + i * 0.46, y, haz.get(key, True),
                  lambda v, k=key: self.set_lesson({"hazards": {k: bool(v)}}), 0.024)
        y -= 0.05
        label(f, "Jobs", 0.82, y, 0.028, YELLOW)
        jobs = L.get("jobs") or {}
        for i, (key, text) in enumerate(JOB_NAMES):
            check(f, text, 0.98 + i * 0.2, y, jobs.get(key, True),
                  lambda v, k=key: self.set_lesson({"jobs": {**{j: (L.get("jobs") or {}).get(j, True)
                                                                for j, _ in JOB_NAMES}, k: bool(v)}}), 0.022)
        y -= 0.05
        label(f, "Time of day", 0.82, y, 0.028, YELLOW)
        for i, (key, text) in enumerate((("day", "Day"), ("dusk", "Dusk"), ("night", "Night"))):
            button(f, text, 1.08 + i * 0.16, y + 0.008, self.set_lesson, [{"time": key}], 0.024,
                   ON if L.get("time", "day") == key else OFF)
        y -= 0.05
        check(f, "Damage (bumps dent a car till the GARAGE mends it)", 0.84, y, L.get("damage", True),
              lambda v: self.set_lesson({"damage": bool(v)}), 0.024)
        y -= 0.045
        check(f, "Lock designs", 0.84, y, L.get("designs_locked"), lambda v: self.set_lesson({"designs_locked": bool(v)}),
              0.024)
        if "teacher_player" in L:
            check(f, "Me in the city", 1.3, y, L.get("teacher_player"),
                  lambda v: self.set_lesson({"teacher_player": bool(v)}), 0.024)
        y -= 0.05
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
        keys = [k for k in TOOL_ORDER if k in L["tools"]]
        for i, k in enumerate(keys):
            check(f, self.pretty(k), 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.041, L["tools"].get(k, True),
                  lambda v, k=k: self.set_lesson({"tools": {k: bool(v)}}), 0.024)
        y -= 0.041 * ((len(keys) + 1) // 2) + 0.02
        label(f, "Learners, Outcomes, AI cards and Changes: the teacher's page (the club desk's Open page).", 0.82, y,
              0.02, GREY, wrap=48)
        y -= 0.06
        self.restart_row(f, y)

    def stage_items(self):
        """The city's hazards, for the User mods tab: the traffic and the robots."""
        L = self.lesson
        return [(hz, HAZARD_NAMES.get(hz, hz.replace("_", " ").capitalize()), bool(on),
                 lambda v, k=hz: self.set_lesson({"hazards": {k: bool(v)}}))
                for hz, on in (L.get("hazards") or {}).items()]

    def took_lesson(self, m):
        """The teacher's lesson as it is now (every window gets it when anything changes)."""
        new = self.fill_lesson(m.get("lesson") or {})
        rebuild = new != self.lesson and self.tab in ("garage", "teacher", "missions", "settings", "limits", "mods")
        mods = m.get("mods") or {}
        if mods != self.mod_info:
            rebuild = rebuild or self.tab in ("teacher", "mods")
            self.mod_info = mods
        self.show_missions_changed(self.lesson, new)
        self.lesson, self.class_list = new, m.get("class", self.class_list)
        if rebuild:
            self.rebuild_panels(from_game=True)
