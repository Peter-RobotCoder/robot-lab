"""The garage's tables, drawn from a game's design schema (the engine's, layer B; CHANGE 46 to 48, 63, 64, 67).

STRING VARIABLES (name, a word chosen from a list...), VARIABLE LISTS (the colour's blocks, a list of words) and
INTEGER VARIABLES (points with their + and - buttons and bars; settings with their sliders), every heading
explaining itself. A game adds what is its own through the schema: a variable's describe() line under its row,
an extra() section drawn after it (a detailed body's look, a combo editor), and unless() to hide rows that don't
apply (a Resident Robot's points). The window provides: entry(), name_key(), change_points(stat, delta),
slider_moved(key), set_colour(rgb), rebuild_panels(), code_shown, custom_colour, sliders, stats.
"""
from direct.gui.DirectGui import DGG, DirectButton, DirectFrame, DirectSlider
from panda3d.core import TextNode

from engine import hud
from engine.hud import SWATCHES, button, label, word


def set_var(win, var, value, ctx):
    """A garage button: the variable takes the value, the game's knock-on rules run, the panels redraw."""
    var.set(win.cur(), value)
    if var.after:
        var.after(win.cur(), ctx)
    win.code_shown = None
    win.rebuild_panels()


def can_change(var, tools, value=None):
    """Whether this mission's garage lets the learner change the variable (to this value)."""
    if var.tool and not tools.get(var.tool):
        return False
    if var.allowed_values and value is not None:
        return value in var.allowed_values(tools)
    return True


def draw(win, f, y, design, schema, ctx, tools, limits, view=None, shown_box=None, teacher=False):
    """The three tables; returns the y below them. view: the teacher's Learner view (every row, with a tick box
    that sets whether the learner sees it: shown_box(tool, y)). teacher: the teacher's own design (every row)."""
    d = design
    ticked = set()

    def tick(tool, yy):
        if view and shown_box and tool and tool not in ticked:
            ticked.add(tool)
            shown_box(tool, yy)

    def heading(text, tip, yy):
        word(f, text, 0.82, yy, 0.029, hud.YELLOW, tip)

    def columns(yy, cols):
        for text, x, tip, *align in cols:
            word(f, text, x, yy, 0.02, hud.BLUE, tip, align[0] if align else TextNode.ALeft)

    def visible(var):
        if var.unless and var.unless(d):
            return False
        return bool(view or teacher or var.always or not var.tool or tools.get(var.tool))

    strings = [v for v in schema if v.garage == "strings" and visible(v)]
    lists = [v for v in schema if v.garage == "lists" and visible(v)]
    points = [v for v in schema if v.group == "points" and visible(v)]
    settings = [v for v in schema if v.group == "settings" and visible(v)]

    # STRING VARIABLES: text boxes, and words chosen from a list (a row of buttons when the mission allows)
    if strings:
        heading("STRING VARIABLES", "STRING", y)
        y -= 0.036
        columns(y, (("STRING NAME", 0.82, "NAME"), ("STRING VALUE", 1.08, "VALUE")))  # (no TYPE column: CHANGE 80)
        y -= 0.045
    for v in strings:
        value = v.get(d)
        word(f, v.name, 0.82, y, 0.028, hud.WHITE, "VARIABLE")
        if v.kind == "str":
            win.entry(f, win.name_key(), 1.08, y, 10, initial=str(value or ""),
                      command=lambda t, v=v: v.set(win.cur(), t[:v.max_len]))
        else:
            label(f, f'"{value}"' if value is not None else f'"{v.none_text}"' if v.none_text else '""', 1.08, y, 0.028,
                  hud.WHITE)
        tick(v.tool, y)
        y -= 0.05
        if v.kind == "choice":
            allowed = view or teacher or can_change(v, tools)
            if allowed and not (v.fixed and v.fixed(d)):
                options = list(v.options(ctx)) if v.options else []
                if v.optional:
                    options = [None] + options
                label(f, "choose:", 0.84, y, 0.022, hud.GREY)
                per_row, x0, step = v.per_row, 1.02, v.step
                for i, opt in enumerate(options):
                    text = v.none_text if opt is None else str(opt).replace("_", " ")
                    button(f, text, x0 + (i % per_row) * step, y + 0.008 - (i // per_row) * 0.045, set_var,
                           [win, v, opt, ctx], 0.022, hud.ON if opt == value else hud.OFF)
                y -= 0.045 * (1 + (max(0, len(options) - 1)) // per_row)
            else:
                label(f, "(chosen by the teacher this mission)", 1.08, y + 0.015, 0.02, hud.GREY)
                y -= 0.02
        if v.describe:
            text = v.describe(ctx, d)
            if text:
                t = label(f, text, 0.82, y, 0.022, hud.GREY, wrap=42)
                y -= 0.03 * t.textNode.getNumRows() + 0.01
        if v.extra:
            y = v.extra(win, f, y, d)
    if strings:
        y -= 0.01

    # VARIABLE LISTS: the colour's blocks (with their values, and a custom block the code sets), lists of words
    if lists:
        heading("VARIABLE LISTS", "LIST", y)
        y -= 0.055
    for v in lists:
        value = v.get(d)
        if v.kind == "rgb":
            word(f, v.name, 0.82, y, 0.028, hud.WHITE, "RGB")
            word(f, "list", 0.82, y - 0.034, 0.024, hud.BLUE, "list")
            c = list(value or [0, 0, 0])
            word(f, f"{v.name}: list = [{c[0]}, {c[1]}, {c[2]}]", 0.82, y - 0.075, 0.026, hud.WHITE,  # (CHANGE 81: the
                 f"The colour chosen, as the code says it: red {c[0]}, green {c[1]}, blue {c[2]}, each 0 to 255.")  # value, readable)
            swatches = [list(s) for s in SWATCHES]
            if c not in swatches:  # a colour typed in the code: the custom block holds it
                win.custom_colour = c
            blocks = swatches + [win.custom_colour]
            for i, block in enumerate(blocks):
                x = 0.96 + i * 0.095
                if block is None:  # no custom colour yet: an empty block, until the code sets one
                    DirectFrame(parent=f, frameColor=(0.25, 0.27, 0.32, 1), frameSize=(-0.03, 0.03, -0.02, 0.02),
                                pos=(x, 0, y))
                    label(f, "custom", x, y - 0.045, 0.013, hud.GREY, TextNode.ACenter)
                    continue
                big = 0.95 if block == c else 0.6
                b = DirectButton(parent=f, text="", scale=0.034, pos=(x, 0, y), relief=DGG.FLAT,
                                 frameColor=(*(ch / 255 for ch in block), 1), frameSize=(-0.9, 0.9, -big, big),
                                 command=win.set_colour, extraArgs=[block])
                rgb = f"[{block[0]}, {block[1]}, {block[2]}]"  # (CHANGE 81: the values show while the mouse is over it)
                b.bind(DGG.WITHIN, lambda e, t=rgb: hud.APP is not None and hud.APP.show_tip(f"{v.name} = {t}"))
                b.bind(DGG.WITHOUT, lambda e: hud.APP is not None and hud.APP.hide_tip())
            tick(v.tool, y)
            y -= 0.11
        elif v.kind == "words":
            word(f, v.name, 0.82, y, 0.028, hud.WHITE, "VARIABLE")
            word(f, "list", 1.44, y, 0.028, hud.BLUE, "list")
            label(f, f"{v.name}: list = {list(value or [])}".replace("'", '"'), 0.82, y - 0.034, 0.022, hud.GREY, wrap=42)
            tick(v.tool, y)
            y -= 0.07
            if v.extra:
                y = v.extra(win, f, y, d)
        else:
            word(f, v.name, 0.82, y, 0.028, hud.WHITE, "VARIABLE")
            label(f, f"{v.name}: list = {value}".replace("'", '"'), 0.82, y - 0.034, 0.022, hud.GREY, wrap=42)
            y -= 0.07

    # INTEGER VARIABLES: the points to share, and the settings
    if points or settings:
        heading("INTEGER VARIABLES", "INTEGER", y)
        y -= 0.04
    if points:
        total = limits["points_total"]
        used = sum(v.get(d) or 0 for v in points)
        word(f, "Points", 0.82, y, 0.027, hud.WHITE if used <= total else hud.RED, "POINTS")
        label(f, f"({used} of {total} used, {total - used} left)", 0.95, y, 0.023, hud.GREY if used <= total else hud.RED)
        tick(points[0].tool, y - 0.036)
        y -= 0.036
        columns(y, (("VARIABLE NAMES", 0.82, "NAME"), ("VARIABLE VALUE", 1.08, "VALUE"), ("share", 1.42, "POINTS")))
        y -= 0.045
        for v in points:
            stat, value = v.path[-1], v.get(d)
            word(f, v.name, 0.82, y, 0.027, hud.WHITE, "VARIABLE")
            for dx, delta, text in ((1.06, -5, "-5"), (1.14, -1, "-"), (1.28, 1, "+"), (1.36, 5, "+5")):
                button(f, text, dx, y + 0.008, win.change_points, [stat, delta], 0.024)
            label(f, str(value), 1.21, y, 0.03, hud.WHITE, TextNode.ACenter)
            DirectFrame(parent=f, frameColor=(0.2, 0.2, 0.22, 1), frameSize=(0, 0.3, 0, 0.02), pos=(1.42, 0, y))
            most = max(1, limits["points"][stat][1])
            DirectFrame(parent=f, frameColor=(0.9, 0.7, 0.15, 1), frameSize=(0, 0.3 * min(value, most) / most, 0, 0.02),
                        pos=(1.42, 0, y))
            y -= 0.05
        y -= 0.01
    win.sliders = {}
    if settings:
        word(f, "Settings", 0.82, y, 0.027, hud.WHITE, "PERCENT")
        label(f, "(percent)", 0.97, y, 0.023, hud.GREY)
        y -= 0.036
        columns(y, (("VARIABLE NAMES", 0.82, "NAME"), ("VARIABLE VALUE", 1.74 if not view else 1.5, "VALUE",
                                                        TextNode.ARight)))
        y -= 0.045
    for v in settings:
        k, value = v.path[-1], v.get(d)
        lo, hi = limits["settings"][k]
        word(f, v.name, 0.82, y, 0.027, hud.WHITE, "VARIABLE")
        if lo >= hi:  # the teacher's range is one value: nothing to slide
            win.sliders[k] = (None, label(f, f"{value:g}%  (set by the teacher)", 1.1, y, 0.027, hud.GREY))
            tick(v.tool, y)
            y -= 0.05
            continue
        s = DirectSlider(parent=f, range=(lo, hi), value=max(lo, min(hi, value)), pageSize=5, scale=0.17 if view else 0.2,
                         pos=(1.24 if view else 1.3, 0, y + 0.008), command=win.slider_moved, extraArgs=[k],
                         thumb_frameSize=(-0.04, 0.04, -0.12, 0.12))
        win.sliders[k] = (s, label(f, f"{value:g}%", 1.44 if view else 1.55, y, 0.027, hud.WHITE))
        tick(v.tool, y)
        y -= 0.05
    if settings:
        y -= 0.01
    return y
