"""The lesson tabs every Club Coders game's window shares (the engine's, since 29 October 2026): a learner's
My card (the outcomes shown, what was done each session) and AI request card (what should change, the idea, the
variables, the test, the prediction, the three promises; the requests sent and the review questions when one is
ready), the missions message's bookkeeping, and the teacher's restart row (code changes load when the server and
the windows restart). They speak the engine's teaching layer's messages (engine/teaching.py), so any game's server
answers them.

A game's window inherits LessonTabs before engine.hud.HudKit, calls init_lesson_tabs() once, and provides:
AI_TARGETS (key -> words: what an AI card may change, its "game" key the teacher's only), panel_note(text, secs),
restart_window(), my_name, missions, lesson, tab and rebuild_panels(from_game). The game draws its own tabs and
calls build_card(f, y) and build_ai_card(f, y) from them, took_missions(m) and card_result(m) from its messages.
"""
import json

from panda3d.core import TextNode

from engine import hud
from engine.hud import BLUE, GREEN, GREY, OFF, ON, ORANGE, RED, WHITE, YELLOW, button, check, label

AI_RULES = ("Only the teacher uses the AI.  Never put personal information in a request.\n"
            "Say what should change, how you will test it and what you predict.")
CARD_FIELDS = ("goal", "variables", "test", "predict")


def send(msg):
    if hud.SEND is not None:
        hud.SEND(msg)


class LessonTabs:
    AI_TARGETS = {"game": "The game (teacher only)"}

    def init_lesson_tabs(self):
        self.card_checks = {"privacy": False, "review": False, "credit": False}
        self.card_msg = ("", WHITE)
        self.card_target = next(iter(self.AI_TARGETS))
        self.sig = {}
        self.missions = None
        self.autopilot = False
        self.needs_restart = False

    def panel_note(self, text, secs=4):
        """Words for a few seconds (the game's own way of showing them)."""

    def build_card(self, f, y):
        """The learner's own card: the outcomes they have shown so far, and what they did each session."""
        card = (self.missions or {}).get("card")
        label(f, f"MY CARD  -  {self.my_name}", 0.82, y, 0.036, YELLOW)
        if not card:
            label(f, "Waiting for your card...", 0.82, y - 0.06, 0.028, GREY)
            return
        y -= 0.06
        label(f, "Outcomes I've shown so far", 0.82, y, 0.03, YELLOW)
        y -= 0.045
        shown = [(card["outcome_names"].get(o, o), n) for o, n in card["outcomes"].items() if n]
        if not shown:
            label(f, "None yet: complete a mission to start your card.", 0.84, y, 0.026, GREY)
            y -= 0.04
        for i, (title_, n) in enumerate(shown):
            label(f, f"{title_}: {n}", 0.84 + (i % 2) * 0.46, y - (i // 2) * 0.038, 0.026, GREEN)
        y -= 0.038 * ((len(shown) + 1) // 2) + 0.02
        label(f, "What I did", 0.82, y, 0.03, YELLOW)
        y -= 0.045
        for day in card["history"]:
            label(f, day["date"], 0.84, y, 0.028, WHITE)
            y -= 0.038
            for mm in day["missions"]:
                label(f, f"Mission {mm['lesson']}: {mm['title']}", 0.88, y, 0.025, GREY)
                label(f, " ".join(mm["outcomes"]), 1.74, y, 0.022, BLUE, TextNode.ARight)
                y -= 0.034
                if mm.get("detail"):
                    t = label(f, mm["detail"], 0.92, y, 0.022, GREEN, wrap=44)
                    y -= 0.028 * t.textNode.getNumRows() + 0.008
            y -= 0.012
        if not card["history"]:
            label(f, "Nothing yet.", 0.84, y, 0.026, GREY)

    def took_missions(self, m):
        """The server's missions message: the mission, its objectives, the learner's record."""
        self.missions = m
        self.autopilot = bool(m.get("autopilot"))
        sig = json.dumps(m, sort_keys=True)
        if sig != self.sig.get("missions"):
            self.sig["missions"] = sig
            if self.tab in ("missions", "ai", "card"):
                self.rebuild_panels(from_game=True)

    # ---------- the AI request card ----------
    def build_ai_card(self, f, y):
        label(f, "AI REQUEST CARD", 0.82, y, 0.04, YELLOW)
        y -= 0.055
        label(f, AI_RULES, 0.82, y, 0.023, BLUE, wrap=42)
        y -= 0.1
        note = str(self.lesson.get("ai_card_note") or "").strip()
        if note:
            words = label(f, "From your teacher:  " + note, 0.82, y, 0.025, ORANGE, wrap=36)
            y -= 0.03 * max(1, words.textNode.getNumRows()) + 0.025
        label(f, "What should change?", 0.82, y, 0.027)
        y -= 0.05
        shown = [(k, t) for k, t in self.AI_TARGETS.items() if k != "game"]
        for i, (key, text) in enumerate(shown):
            button(f, text, 0.96 + i * 0.27, y + 0.008, self.set_card_target, [key], 0.022,
                   ON if key == self.card_target else OFF)
        y -= 0.07
        for key, text in (("goal", "My idea"), ("variables", "Variables and values it needs"),
                          ("test", "How I will test it"), ("predict", "What I predict will happen")):
            rows = 6 if key in ("goal", "test") else 4
            label(f, text, 0.82, y, 0.027)
            self.textbox(f, f"card_{key}", 0.84, y - 0.02, 0.8, rows, scale=0.024)
            y -= 0.075 + rows * 0.036
        for key, text in (("privacy", "No personal information (names, school, email, address)"),
                          ("review", "I will review and test the AI's code"),
                          ("credit", "I will say where AI helped")):
            check(f, text, 0.84, y, self.card_checks[key], lambda v, k=key: self.card_checks.__setitem__(k, bool(v)), 0.026)
            y -= 0.045
        button(f, "SEND TO THE TEACHER", 1.27, y - 0.01, self.send_card, None, 0.036, (0.15, 0.45, 0.65, 1))
        y -= 0.07
        self.card_text = label(f, self.card_msg[0], 0.82, y, 0.024, self.card_msg[1], wrap=40)
        y -= 0.1
        self.card_list(f, y, (self.missions or {}).get("cards", []))

    def card_list(self, f, y, cards):
        if cards:
            label(f, "Requests", 0.82, y, 0.028, YELLOW)
            y -= 0.045
        for c in cards[-3:]:
            label(f, f"#{c['id']} {c['status'].upper()}: {c['card']['goal'][:40]}", 0.84, y, 0.024,
                  GREEN if c["status"] in ("ready", "reviewed") else GREY)
            y -= 0.04
            if c.get("note"):
                label(f, f"Teacher: {c['note']}", 0.86, y, 0.022, BLUE, wrap=40)
                y -= 0.04
            if c["status"] == "ready":
                self.build_review(f, y, c)
                return

    def build_review(self, f, y, c):
        label(f, c.get("acknowledgement", ""), 0.84, y, 0.022, BLUE)
        y -= 0.04
        for key, q in self.missions["review_questions"].items():
            label(f, q, 0.84, y, 0.022, WHITE, wrap=44)
            self.entry(f, f"review_{key}", 0.84, y - 0.04, 30, 1, scale=0.024)
            y -= 0.085
        button(f, "SUBMIT MY REVIEW", 1.27, max(y, -0.88), self.send_review, [c["id"]], 0.032, (0.15, 0.55, 0.25, 1))

    def send_review(self, cid):
        answers = {k: self.entries[f"review_{k}"].get() for k in self.missions["review_questions"]}
        send({"type": "ai_review", "id": cid, "answers": answers})

    def set_card_target(self, key):
        self.card_target = key
        self.rebuild_panels()

    def send_card(self):
        card = {k: self.entries[f"card_{k}"].get() for k in CARD_FIELDS}
        self.stop_typing()
        self.card_msg = ("Sending...", GREY)
        if getattr(self, "card_text", None) is not None:
            self.card_text.setText("Sending...")
        send({"type": "ai_card", "card": card | self.card_checks | {"target": self.card_target}})

    def card_result(self, m):
        if m.get("ok"):
            self.card_msg = ("Sent! The teacher will look at it." + (" Tip: " + " ".join(m["tips"]) if m.get("tips") else ""),
                             GREEN)
            for k in CARD_FIELDS:
                self.entry_text.pop(f"card_{k}", None)
                if f"card_{k}" in self.entries:
                    self.set_entry(f"card_{k}", "")
        else:
            self.card_msg = ("Not sent: " + " ".join(m.get("problems", [])), RED)
        try:
            self.card_text.setText(self.card_msg[0])
            self.card_text.setFg(self.card_msg[1])
        except Exception:
            pass
        if self.tab == "ai":
            self.rebuild_panels(from_game=True)

    def restart_row(self, f, y):
        label(f, "Code changes" + ("  (waiting: restart to use them)" if self.needs_restart else ""), 0.82, y, 0.026,
              ORANGE if self.needs_restart else YELLOW)
        y -= 0.05
        button(f, "Restart server", 0.95, y, self.restart_server, None, 0.024,
               (0.6, 0.35, 0.1, 1) if self.needs_restart else OFF)
        button(f, "Reopen learners' windows", 1.25, y, send, [{"type": "restart_clients"}], 0.024)
        button(f, "Reopen mine", 1.6, y, self.restart_window, None, 0.024)

    def restart_server(self):
        self.needs_restart = False
        send({"type": "restart_server"})

    def set_lesson(self, change):
        send({"type": "lesson", "lesson": change})
