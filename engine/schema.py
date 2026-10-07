"""The design schema: a game's design (its robot, its fighter) described as variables (the engine's, layer B).

A game lists its variables once: each has the name the code uses, where it lives in the design dictionary, its
type, its group on the HUD (STRING VARIABLES, INTEGER VARIABLES: points or settings, VARIABLE LISTS), which lesson
tool lets the garage show it, and a comment. From that list the engine writes the design as Python (one typed
variable a line, in the HUD's groups), reads it back (APPLY CODE: nothing is run, the values are read as data), and
Layer B's garage draws the tables.

Kinds: "str" (text), "int" (a whole number; a setting the teacher's limits make a fraction shows as float), "rgb"
(a colour: [red, green, blue]), "choice" (one of a list of words: the code shows the list as its own variable and
picks from it, weapon: str = weapons[0]), "words" (a list of words, each from a list: a combo of moves).
"""
import ast
import json


class Var:
    def __init__(self, name, path, kind, group, tool=None, note="", options=None, list_name=None, list_note="",
                 max_len=16, optional=False, after=None, valid=None, garage=None, none_text="none", per_row=4,
                 step=0.13, fixed=None, describe=None, extra=None, unless=None, allowed_values=None, always=False):
        self.name, self.path, self.kind, self.group, self.tool, self.note = name, path, kind, group, tool, note
        # the garage (engine.garage): which table the row is in (a choice is a string row, even when the code
        # lists it), the row's buttons (per_row, step; none_text for an optional choice's "none" button),
        # fixed(design) when the buttons are not offered, describe(ctx, design) for a line under the row,
        # extra(window, frame, y, design) -> y for a section of the game's own after it, unless(design) to hide
        # the row, allowed_values(tools) for the values this mission's garage offers (hidden otherwise)
        self.garage = garage or ("strings" if kind == "choice" else group)
        self.none_text, self.per_row, self.step, self.fixed = none_text, per_row, step, fixed
        self.describe, self.extra, self.unless, self.allowed_values = describe, extra, unless, allowed_values
        self.always = always  # shown in the garage even when its tool is off (then read-only: the teacher's choice)
        self.options = options          # (ctx) -> the words offered, for "choice" and "words"
        self.valid = valid              # (ctx) -> every word accepted (wider than offered: hidden from this lesson)
        self.list_name = list_name      # for "choice": the list variable it is picked from in the code ("weapons")
        self.list_note = list_note      # ...and that list's comment
        self.max_len = max_len          # for "str": the most characters kept
        self.optional = optional        # may be missing from the design (a Resident Robot's model)
        self.after = after              # (design, ctx) called after a change: the game's own knock-on rules

    def get(self, design):
        d = design
        for k in self.path:
            if not isinstance(d, dict) or k not in d:
                return None
            d = d[k]
        return d

    def set(self, design, value):
        d = design
        for k in self.path[:-1]:
            d = d.setdefault(k, {})
        if value is None and self.optional:
            d.pop(self.path[-1], None)
        else:
            d[self.path[-1]] = value


def shown(var, tools):
    """Whether a lesson's garage shows this variable (its tool is on; no tool: always)."""
    return bool(tools.get(var.tool, True)) if var.tool else True


def row(code, note, width=28):
    return f"{code:<{width}}# {note}" if note else code


# (CHANGE 89) what each line of the code pop-up does, in plain words: one sentence above each line. The teacher
# can read them all here. {name} the variable, {value} what it is set to, {note} the game's own words for it,
# {list} a list's name, {i} an item's number, {item} that item, {r} {g} {b} a colour's numbers.
COMMENTS = {
    "int": "creating an integer variable called {name} and setting its value to {value} ({note})",
    "float": "creating a decimal variable called {name} and setting its value to {value} ({note})",
    "str": "creating a string variable called {name} and setting its value to {value} ({note})",
    "str_plain": "creating a string variable called {name} and setting its value to {value}",
    "options": "creating a list variable called {list} holding {note}",
    "choice": "picking item {i} ({item}) from the list {list} and storing it in the string variable {name} (0 is the first)",
    "choice_other": "creating a string variable called {name} and setting its value to {value} (the one chosen)",
    "rgb": "creating a list variable called {name} holding three integers: red {r}, green {g}, blue {b} ({note})",
    "list": "creating a list variable called {name} holding these values in order ({note})",
    "list_plain": "creating a list variable called {name} holding these values in order",
}


def comment(key, **words):
    """The sentence as comment lines, wrapped so it fits the code panel (60 letters a line)."""
    import textwrap
    return ["# " + line for line in textwrap.wrap(COMMENTS[key].format(**words), 60)]


def code_lines(schema, design, ctx):
    """The design as Python: one typed variable a line, with a sentence above it saying what the line does, in the
    HUD's groups. ctx.title: "MY ROBOT"; ctx.points_total: the points to share (None: no points line)."""
    by_group = {g: [v for v in schema if v.group == g] for g in ("settings", "points", "strings", "lists")}
    lines = [f"# {ctx.title} as Python code. Each line makes a variable:", "#     name: type = value", ""]
    ints = by_group["settings"] + by_group["points"]
    if ints:
        lines.append("# INTEGER VARIABLES (whole numbers)")
        for v in ints:
            value = v.get(design)
            if value is None:
                continue
            kind = "int" if value == int(value) else "float"
            lines.extend(comment(kind, name=v.name, value=f"{value:g}", note=v.note or "a whole number"))
            lines.append(f"{v.name}: {kind} = {value:g}")
        if by_group["points"] and ctx.points_total is not None:
            used = sum(v.get(design) or 0 for v in by_group["points"])
            lines.append(f"# points used: {used} of {ctx.points_total}")
        lines.append("")
    if by_group["strings"]:
        lines.append("# STRING VARIABLES (text in quotes)")
        for v in by_group["strings"]:
            value = v.get(design)
            if value is None and v.optional:
                continue
            text = json.dumps(str(value))
            lines.extend(comment("str", name=v.name, value=text, note=v.note) if v.note else
                         comment("str_plain", name=v.name, value=text))
            lines.append(f"{v.name}: str = {text}")
        lines.append("")
    if by_group["lists"]:
        lines.append("# VARIABLE LISTS (values in order, in square brackets)")
        for v in by_group["lists"]:
            value = v.get(design)
            if value is None and v.optional:
                continue
            if v.kind == "rgb":
                c = list(value or [0, 0, 0])
                lines.extend(comment("rgb", name=v.name, r=c[0], g=c[1], b=c[2], note=v.note or "each 0 to 255"))
                lines.append(f"{v.name}: list = [{c[0]}, {c[1]}, {c[2]}]")
            elif v.kind == "choice":
                options = list(v.options(ctx)) if v.options else []
                lines.extend(comment("options", list=v.list_name, note=v.list_note or "the choices"))
                lines.append(f"{v.list_name}: list = {json.dumps(options)}")
                if value in options:
                    i = options.index(value)
                    lines.extend(comment("choice", i=i, item=json.dumps(value), list=v.list_name, name=v.name))
                    lines.append(f"{v.name}: str = {v.list_name}[{i}]")
                else:
                    lines.extend(comment("choice_other", name=v.name, value=json.dumps(str(value))))
                    lines.append(f"{v.name}: str = {json.dumps(str(value))}")
            elif v.kind == "words":
                lines.extend(comment("list", name=v.name, note=v.note) if v.note else comment("list_plain", name=v.name))
                lines.append(f"{v.name}: list = {json.dumps(list(value or []))}")
            else:
                lines.extend(comment("list", name=v.name, note=v.note) if v.note else comment("list_plain", name=v.name))
                lines.append(f"{v.name}: list = {json.dumps(value)}")
    while lines and lines[-1] == "":
        lines.pop()
    return lines


class ParseError(Exception):
    def __init__(self, lineno, message):
        super().__init__(message)
        self.lineno, self.message = lineno, message


def parse_code(text, schema, ctx):
    """The values the code gives, by variable name: {name: value}. Nothing is run: only  name: type = value  lines
    with plain values, and  name = list_name[i]  for a choice. Raises ParseError for a line it can't read."""
    text = "\n".join(line.strip() for line in text.split("\n"))  # (spaces and blank lines anywhere: CHANGE 88)
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        msg = e.msg if e.msg.endswith((".", "?", "!")) else e.msg + "."
        raise ParseError(e.lineno, f"{msg} Check the brackets, commas and quote marks.") from None
    choices = {v.list_name: v for v in schema if v.kind == "choice" and v.list_name}
    values = {}
    for st in tree.body:
        if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
            target, value = st.target.id, st.value
        elif isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            target, value = st.targets[0].id, st.value
        else:
            raise ParseError(st.lineno, "only lines like  name: type = value  are allowed.")
        if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) and value.value.id in choices:
            v = choices[value.value.id]
            options = values.get(v.list_name, list(v.options(ctx)) if v.options else [])
            try:
                i = ast.literal_eval(value.slice)
                values[target] = options[i]
            except (ValueError, TypeError, IndexError, KeyError):
                raise ParseError(st.lineno, f"{v.list_name}[...] needs a number from 0 (the first) to "
                                            f"{len(options) - 1} (the last).") from None
            continue
        try:
            values[target] = ast.literal_eval(value)
        except ValueError:
            raise ParseError(st.lineno, "only plain values are allowed: numbers, \"text\" and [lists].") from None
    return values


def check_value(var, value, ctx):
    """A problem with a value for this variable (its type, or the words allowed), or None."""
    if var.kind == "str":
        return None if isinstance(value, str) else f"{var.name} must be text in quotes"
    if var.kind == "int":
        return None if isinstance(value, (int, float)) and not isinstance(value, bool) else f"{var.name} must be a number"
    if var.kind == "rgb":
        ok = isinstance(value, list) and len(value) == 3 and all(isinstance(c, int) and not isinstance(c, bool)
                                                                   and 0 <= c <= 255 for c in value)
        return None if ok else f"{var.name} must be a list of three whole numbers from 0 to 255"
    if var.kind == "choice":
        options = list(var.valid(ctx)) if var.valid else list(var.options(ctx)) if var.options else []
        if value is None and var.optional:
            return None
        return None if value in options else f"{var.name} must be one of: {', '.join(map(str, options))}"
    if var.kind == "words":
        options = list(var.options(ctx)) if var.options else None
        if not isinstance(value, list) or not all(isinstance(w, str) for w in value):
            return f"{var.name} must be a list of words in quotes"
        if options is not None and any(w not in options for w in value):
            return f"{var.name} may only have: {', '.join(options)}"
        return None
    return None


def apply_values(schema, design, values, ctx, allowed):
    """Put the code's values into the design. allowed(var, value): whether this lesson's garage lets the learner
    change it to that (if not, the change still goes in, and is listed as hidden: the teacher is told).
    -> (changed variable names, hidden variable names, problems)"""
    by_name = {v.name: v for v in schema}
    known = set(by_name) | {v.list_name for v in schema if v.list_name}
    changed, hidden, problems = [], [], []
    for name in values:
        if name not in known:
            problems.append(f"'{name}' isn't one of the variables")
    for v in schema:
        if v.name not in values:
            continue
        value = values[v.name]
        problem = check_value(v, value, ctx)
        if problem:
            problems.append(problem)
            continue
        if v.kind == "str":
            value = str(value)[:v.max_len]
        elif v.kind == "int" and v.group == "points" and value == int(value):
            value = int(value)
        if value == v.get(design):
            continue
        v.set(design, value)
        changed.append(v.name)
        if not allowed(v, value):
            hidden.append(v.name)
        if v.after:
            v.after(design, ctx)
    return changed, hidden, problems


def outside_lesson(schema, old, new, tools, allowed=None):
    """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
    did it in the code): [[variable, the old value, the new value], ...] for the teacher's Warnings tab.
    allowed(var, value): the game's own rule (default: the variable's tool is on and the value is offered)."""
    found = []
    for var in schema:
        a, b = var.get(old), var.get(new)
        if a == b:
            continue
        ok = allowed(var, b) if allowed else (shown(var, tools) and (not var.allowed_values or b in var.allowed_values(tools)))
        if not ok:
            found.append([var.name, "none" if a is None else a, "none" if b is None else b])
    return found


def outside_lesson(schema, old, new, tools, allowed=None):
    """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
    did it in the code): [[variable, the old value, the new value], ...] for the teacher's Warnings tab.
    allowed(var, value): the game's own rule (default: the variable's tool is on and the value is offered)."""
    found = []
    for var in schema:
        a, b = var.get(old), var.get(new)
        if a == b:
            continue
        ok = allowed(var, b) if allowed else (shown(var, tools) and (not var.allowed_values or b in var.allowed_values(tools)))
        if not ok:
            found.append([var.name, "none" if a is None else a, "none" if b is None else b])
    return found


def outside_lesson(schema, old, new, tools, allowed=None):
    """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
    did it in the code): [[variable, the old value, the new value], ...] for the teacher's Warnings tab.
    allowed(var, value): the game's own rule (default: the variable's tool is on and the value is offered)."""
    found = []
    for var in schema:
        a, b = var.get(old), var.get(new)
        if a == b:
            continue
        ok = allowed(var, b) if allowed else (shown(var, tools) and (not var.allowed_values or b in var.allowed_values(tools)))
        if not ok:
            found.append([var.name, "none" if a is None else a, "none" if b is None else b])
    return found


def outside_lesson(schema, old, new, tools, allowed=None):
    """What changed between two of a learner's designs that this lesson's garage doesn't let them change (they
    did it in the code): [[variable, the old value, the new value], ...] for the teacher's Warnings tab.
    allowed(var, value): the game's own rule (default: the variable's tool is on and the value is offered)."""
    found = []
    for var in schema:
        a, b = var.get(old), var.get(new)
        if a == b:
            continue
        ok = allowed(var, b) if allowed else (shown(var, tools) and (not var.allowed_values or b in var.allowed_values(tools)))
        if not ok:
            found.append([var.name, "none" if a is None else a, "none" if b is None else b])
    return found
