"""The club's paper trail: learner cards, session summaries and the scheme of work, as PDFs on the teacher's laptop.

Made from a session's record (from the club desk: the group, game and lesson, who was there, what each learner
completed, the AI cards, the teacher's notes) and the game's own lesson file (lab_missions.py or fight_missions.py:
lessons, outcomes and, where written, each lesson's overall task and lesson pieces).

    learner card     one page per learner whose achievements changed in the session:
                     records\\<username>\\<date> session N.pdf
    session summary  one per session: records\\sessions\\<date> <group>.pdf
    scheme of work   one per game, from its lesson file: records\\Scheme of work - <game>.pdf

Usernames only: the teacher adds a real name from their own file where one is needed.
"""
import datetime
import importlib
import json
import os
import re
import sys

RECORDS = os.environ.get("CLUBCODERS_RECORDS") or os.path.join(os.path.expanduser("~"), "Documents", "Club Coders records")
LESSON_FILES = {"robotlab": "lab_missions", "fightlab": "fight_missions"}
TITLES = {"robotlab": "Robot Lab", "fightlab": "Fight Lab"}


def lesson_module(game, folder):
    """The game's lesson file, loaded from its folder (plain data: lessons, missions, outcomes)."""
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return importlib.import_module(LESSON_FILES[game])


def safe(text):
    return re.sub(r"[^A-Za-z0-9 _-]+", "_", str(text)).strip() or "x"


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=12)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8, leading=10, textColor=colors.HexColor("#555555")),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17, leading=21,
                             textColor=colors.HexColor("#1F4E8C"), spaceAfter=2),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=14,
                             textColor=colors.HexColor("#1F4E8C"), spaceBefore=8, spaceAfter=3),
        "green": ParagraphStyle("green", parent=base, textColor=colors.HexColor("#1B7A34")),
    }


def table(rows, widths, header=True, size=8.5):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", size), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BBBBBB")),
             ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", size), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7"))]
    t.setStyle(TableStyle(style))
    return t


def build_pdf(path, story):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.4 * cm,
                            bottomMargin=1.4 * cm, title=os.path.splitext(os.path.basename(path))[0], author="Club Coders")
    doc.build(story)
    return path


# ---------- what a lesson is about ----------
def lesson_info(lm, n):
    """Title, overall task (if written) and the outcomes a lesson teaches, from the game's lesson file."""
    n = int(n)
    lesson = lm.LESSONS.get(n, {})
    missions = {k: v for k, v in lm.MISSIONS.items() if v[0] == n}
    codes = sorted({o for v in missions.values() for o in v[3]})
    task = getattr(lm, "LESSON_TASKS", {}).get(n, "")
    return {"number": n, "title": lesson.get("title", f"Lesson {n}"), "task": task,
            "outcomes": [(c, lm.OUTCOMES[c][0], lm.OUTCOMES[c][1]) for c in codes if c in lm.OUTCOMES],
            "missions": [(k, v[1], v[3]) for k, v in missions.items()]}


# ---------- the learner card ----------
def learner_card(record, name, sessions, lm, out_dir=RECORDS):
    """One page: this session for one learner, and their trail so far. Returns the PDF's path."""
    from reportlab.platypus import Paragraph, Spacer
    st = styles()
    report = record.get("report") or {}
    game, title = record["game"], TITLES.get(record["game"], record["game"])
    info = lesson_info(lm, record.get("lesson", 1))
    date = record.get("started", "")[:10]
    done = (report.get("done") or {}).get(name, {})
    totals = (report.get("totals") or {}).get(name, {})
    attended = [s for s in sessions if name in ((s.get("report") or {}).get("present") or {})]
    attended = sorted(attended, key=lambda s: s.get("started", ""))
    number = next((i + 1 for i, s in enumerate(attended) if s.get("id") == record.get("id")), len(attended) + 1)
    story = [Paragraph(f"Learner card: {esc(name)}", st["h1"]),
             Paragraph(f"{esc(title)}  -  session {number}  -  {esc(date)}  -  group {esc(record.get('group', ''))}",
                       st["small"]),
             Paragraph(f"Lesson {info['number']}: {esc(info['title'])}", st["h2"])]
    if info["task"]:
        story.append(Paragraph("<b>Aim:</b> " + esc(info["task"]), st["base"]))
    story.append(Paragraph("<b>Learning outcomes for this lesson:</b> " + "; ".join(
        f"{esc(n_)} ({esc(c)})" for c, n_, _ in info["outcomes"]), st["base"]))
    story.append(Paragraph("What I achieved in this session", st["h2"]))
    if done:
        rows = [["Mission", "Outcomes", "Evidence"]]
        for mid, d in sorted(done.items(), key=lambda kv: kv[1].get("time", "")):
            rows.append([Paragraph(esc(d.get("title", mid)), st["base"]), " ".join(d.get("outcomes", [])),
                         Paragraph(esc(d.get("detail", "")), st["base"])])
        story.append(table(rows, [180, 70, 250]))
    else:
        story.append(Paragraph("No missions were completed in this session.", st["base"]))
    note = (record.get("notes") or {}).get(name)
    if note:
        story.append(Paragraph("<b>Teacher's note:</b> " + esc(note), st["green"]))
    story.append(Paragraph(f"Outcomes shown so far in {esc(title)}", st["h2"]))
    shown = [(lm.OUTCOMES[c][0], n_) for c, n_ in totals.items() if n_ and c in lm.OUTCOMES]
    if shown:
        story.append(table([["Outcome", "Times shown"]] + [[a, str(b)] for a, b in sorted(shown)], [300, 90]))
    else:
        story.append(Paragraph("None yet.", st["base"]))
    story.append(Paragraph("Sessions so far", st["h2"]))
    rows = [["Date", "Game", "Group", "Lesson", "Missions completed", "Note"]]
    for s in attended:
        r = s.get("report") or {}
        rows.append([s.get("started", "")[:10], TITLES.get(s.get("game"), s.get("game", "")), s.get("group", ""),
                     str(s.get("lesson", "")), str(len((r.get("done") or {}).get(name, {}))),
                     Paragraph(esc((s.get("notes") or {}).get(name, "")), st["small"])])
    story.append(table(rows, [60, 60, 80, 40, 90, 170]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Club Coders keeps usernames only. This card was made on the teacher's computer.", st["small"]))
    path = os.path.join(out_dir, safe(name), f"{safe(date)} session {number}.pdf")
    return build_pdf(path, story)


# ---------- the session summary ----------
def session_summary(record, lm, out_dir=RECORDS, laptop_events=None):
    """One PDF for the teacher: the session at a glance. Returns its path."""
    from reportlab.platypus import Paragraph, Spacer
    st = styles()
    report = record.get("report") or {}
    game, title = record["game"], TITLES.get(record["game"], record["game"])
    info = lesson_info(lm, record.get("lesson", 1))
    present = sorted((report.get("present") or {}).keys())
    missing = sorted(set(record.get("learners", [])) - set(present))
    story = [Paragraph(f"Session summary: {esc(record.get('group', ''))}", st["h1"]),
             Paragraph(f"{esc(title)}  -  {esc(record.get('started', ''))} to {esc(record.get('ended', '')[-5:])}  -  "
                       f"lesson {info['number']}: {esc(info['title'])}", st["small"])]
    if info["task"]:
        story.append(Paragraph("<b>Aim:</b> " + esc(info["task"]), st["base"]))
    story.append(Paragraph("Who was here", st["h2"]))
    story.append(Paragraph(f"<b>Present ({len(present)}):</b> " + (", ".join(map(esc, present)) or "nobody") +
                           (f"<br/><b>Missing ({len(missing)}):</b> " + ", ".join(map(esc, missing)) if missing else ""),
                           st["base"]))
    story.append(Paragraph("Outcomes so far (this game)", st["h2"]))
    codes = [c for c in lm.OUTCOMES]
    rows = [["Learner", "This session"] + codes]
    totals = report.get("totals") or {}
    done = report.get("done") or {}
    for name in present:
        t = totals.get(name, {})
        rows.append([name, str(len(done.get(name, {})))] + [str(t.get(c, 0) or "-") for c in codes])
    if len(rows) > 1:
        story.append(table(rows, [70, 60] + [int(370 / max(1, len(codes)))] * len(codes), size=6.5))
        story.append(Paragraph("Codes: " + "; ".join(f"{c} {lm.OUTCOMES[c][0]}" for c in codes), st["small"]))
    story.append(Paragraph("Completed in this session", st["h2"]))
    rows = [["Learner", "Mission", "Outcomes", "When"]]
    for name in present:
        for mid, d in sorted(done.get(name, {}).items(), key=lambda kv: kv[1].get("time", "")):
            rows.append([name, Paragraph(esc(d.get("title", mid)), st["base"]), " ".join(d.get("outcomes", [])),
                         d.get("time", "")[-5:]])
    story.append(table(rows, [70, 260, 90, 60]) if len(rows) > 1 else Paragraph("Nothing yet.", st["base"]))
    cards = report.get("cards") or []
    story.append(Paragraph("AI cards", st["h2"]))
    if cards:
        rows = [["Learner", "Status", "Request"]]
        for c in cards:
            rows.append([c.get("learner", ""), c.get("status", ""), Paragraph(esc(c.get("goal", "")), st["base"])])
        story.append(table(rows, [70, 70, 340]))
    else:
        story.append(Paragraph("None in this session.", st["base"]))
    if laptop_events:
        story.append(Paragraph("Changes to the game (from this laptop)", st["h2"]))
        for line in laptop_events:
            story.append(Paragraph(esc(line), st["base"]))
    notes = record.get("notes") or {}
    if notes:
        story.append(Paragraph("Teacher's notes", st["h2"]))
        for name, text in sorted(notes.items()):
            story.append(Paragraph(f"<b>{esc(name)}:</b> {esc(text)}", st["base"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Usernames only. Made on the teacher's computer from the club desk's record.", st["small"]))
    path = os.path.join(out_dir, "sessions", f"{safe(record.get('started', '')[:10])} {safe(record.get('group', ''))}.pdf")
    return build_pdf(path, story)


def laptop_events(folder, started, ended):
    """Changes made on this laptop during the session: AI changes kept, merged or rolled back (the game folder's
    change log), and live updates signed. Only when the app runs from the source files; else empty."""
    events = []
    log = os.path.join(folder, "ai_changes", "log.json")
    try:
        with open(log, encoding="utf-8") as f:
            entries = json.load(f)
        entries = entries if isinstance(entries, list) else entries.get("changes", [])
        for e in entries:
            when = str(e.get("time", e.get("when", "")))
            if started[:16] <= when[:16] <= ended[:16]:
                events.append(f"AI change {e.get('n', '')}: {e.get('goal', e.get('summary', ''))[:90]} "
                              f"({e.get('status', '')}, {', '.join(e.get('files', []))})")
    except (OSError, ValueError):
        pass
    history = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders", "live_history")
    try:
        for game in os.listdir(history):
            for name in os.listdir(os.path.join(history, game)):
                if name.endswith(".zip"):
                    when = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(history, game, name)))
                    when = when.strftime("%Y-%m-%d %H:%M")
                    if started[:16] <= when <= ended[:16]:
                        events.append(f"Live update {name[:-4]} of {TITLES.get(game, game)} signed at {when[-5:]}")
    except OSError:
        pass
    return events


# ---------- the scheme of work ----------
def scheme_of_work(game, lm, out_dir=RECORDS):
    """One document per game from its lesson file: every lesson's title, overall task, outcomes with their
    curriculum references, missions, and (where written) the lesson pieces."""
    from reportlab.platypus import PageBreak, Paragraph
    st = styles()
    title = TITLES.get(game, game)
    story = [Paragraph(f"Scheme of work: {esc(title)}", st["h1"]),
             Paragraph(f"From the game's lesson file, {datetime.date.today()}. Five lessons; each mission gives evidence "
                       "for the learning outcomes shown, checked by the game or ticked by the teacher.", st["small"])]
    guide = getattr(lm, "GUIDE", {})
    for n in sorted(lm.LESSONS):
        info = lesson_info(lm, n)
        story.append(Paragraph(f"Lesson {n}: {esc(info['title'])}", st["h2"]))
        if info["task"]:
            story.append(Paragraph("<b>Overall task:</b> " + esc(info["task"]), st["base"]))
        rows = [["Outcome", "Learners can", "Curriculum"]]
        for c, name, can in info["outcomes"]:
            rows.append([f"{name} ({c})", Paragraph(esc(can), st["base"]), Paragraph(esc(lm.OUTCOMES[c][2]), st["small"])])
        story.append(table(rows, [110, 170, 200]))
        rows = [["Mission", "What learners do", "Outcomes", "Checked by"]]
        for k, v in lm.MISSIONS.items():
            if v[0] == n:
                rows.append([k, Paragraph(esc(v[2]), st["base"]), " ".join(v[3]), "teacher" if v[4] == "teacher" else "the game"])
        story.append(table(rows, [40, 300, 70, 70]))
        for code, piece in guide.get(n, {}).items():
            story.append(Paragraph(f"{esc(lm.OUTCOMES[code][0])}: {esc(piece['task'])}", st["h2"]))
            for i, step in enumerate(piece.get("do", []), 1):
                story.append(Paragraph(f"{i}. {esc(step)}", st["base"]))
            story.append(Paragraph("<b>Explain or show:</b> " + esc(piece.get("teach", "")), st["base"]))
            story.append(Paragraph("<b>Success looks like:</b> " + esc(piece.get("success", "")), st["green"]))
        if n != max(lm.LESSONS):
            story.append(PageBreak())
    path = os.path.join(out_dir, f"Scheme of work - {safe(title)}.pdf")
    return build_pdf(path, story)


# ---------- all of a session's PDFs ----------
def make_all(record, sessions, folder, out_dir=RECORDS):
    """The session summary and a card for every learner whose achievements changed (or who has a note).
    Returns the list of paths made."""
    game = record["game"]
    lm = lesson_module(game, folder)
    report = record.get("report") or {}
    made = []
    changed = set((report.get("done") or {}).keys()) | set((record.get("notes") or {}).keys())
    for name in sorted(changed):
        made.append(learner_card(record, name, sessions, lm, out_dir))
    made.append(session_summary(record, lm, out_dir, laptop_events(folder, record.get("started", ""),
                                                                    record.get("ended", record.get("started", "")))))
    return made
