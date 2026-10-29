"""The Club Coders pseudo code interpreter: the Wake-Up Call prototype's (missions/wake_up_call/prototype/cc_pseudo.js)
ported line for line, so the 3D window reads a learner's lines exactly as the 2D prototype did. wake_up_call_test.py
runs both on the same lines and requires the same results.

Deterministic: the same text always gives the same result. A line is lower-cased, its punctuation dropped, its filler
words dropped, its synonyms applied (until nothing changes) and its number words made digits; then it must match one
pattern exactly: the keywords, the values and their order. A line that doesn't is an error with, where one can be
found, a "did you mean" hint. The hint is only shown: nothing is ever corrected for the learner.

dictionary.json (the patterns, slots, fillers, synonyms and number words) is the source of truth: load(path) reads it.

Mission 2 (Lights Out) adds if / else and variables without changing a line of Mission 1's reading: its dictionary
"extends" Mission 1's (the base's patterns, slots, fillers, synonyms and number words, then its own added, changed
or removed: extend()), and everything new is switched on only by what a dictionary says:
  "symbols"        the Python signs read as words before the punctuation is dropped (= equals, + plus, < less than)
  a slot's "python"     a value's Python (path blocked -> robot.path_blocked()); "read_only" names it can't change
  a pattern's "block"   what it opens ("if"; a repeat is a repeat), "middle" (else: closes the if's lines, opens
                        its own), "end_python" (the Python beside the end that closes it), "assigns" (the slot it
                        changes), "alias" (another way to write a pattern: not in the phrasebook)
  a pattern's filler words ("set [name] to [v]") are shown but not matched, as a line's fillers are dropped
Mission 1's dictionary has none of these, so its lines read exactly as the prototype reads them.
"""
import json
import os
import re

LOOP_VARS = ["i", "j", "k"]
MAX_DEPTH = 3
SLOT = re.compile(r"^\[\w+\]$")
DIGITS = re.compile(r"^\d+$")
FILL = re.compile(r"\{(\w+)\}|\[(\w+)\]")


def is_slot(w):
    return bool(SLOT.match(w))


def slot_name(w):
    return w[1:-1]


def split_ws(text):
    """JavaScript's text.split(/\\s+/): every piece, the empty ones at the ends kept."""
    return re.split(r"\s+", text)


class Compiled:
    """The dictionary made ready to match against (compile in the prototype)."""

    def __init__(self, d):
        self.dict = d
        self.fillers = set(d["fillers"])
        # (a pattern's filler words, as "to" in "set [name] to [v]", are for reading: a line's are dropped)
        self.patterns = [dict(p, words=[w for w in split_ws(p["say"]) if w not in self.fillers]) for p in d["patterns"]]
        syn = [{"from": split_ws(k), "to": [w for w in split_ws(v) if w]} for k, v in d["synonyms"].items()]
        # the longest first, then in alphabetical order (as the prototype's sort)
        self.synonyms = sorted(syn, key=lambda s: (-len(s["from"]), " ".join(s["from"])))
        self.symbols = [(a, " " + b + " ") for a, b in d.get("symbols") or []]
        self.minus = d.get("minus")
        self.blocks = sorted({p.get("block", "repeat") for p in d["patterns"] if p.get("opens")},
                             key=lambda b: (b != "repeat", b))  # (what an end can close, for its messages)
        literals = set()
        for p in self.patterns:
            for w in p["words"]:
                if not is_slot(w):
                    literals.add(w)
        vocab = set(literals)
        for s in d["slots"].values():
            for v in s.get("values") or []:
                vocab.update(v.split(" "))
        for s in self.synonyms:
            vocab.update(s["from"])
        vocab.update(d["number_words"])
        vocab.update(self.fillers)
        self.literals = sorted(literals)
        self.vocab = sorted(vocab)
        self.vocab_set = set(vocab)
        self.lines = {}  # (parse_line's memory: text -> result)


def compile_dict(d):
    return Compiled(d)


def load(path):
    return compile_dict(load_raw(path))


def load_raw(path):
    """A dictionary file as data, with the one it "extends" (a path beside it) under it."""
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if d.get("extends"):
        d = extend(load_raw(os.path.join(os.path.dirname(os.path.abspath(path)), d["extends"])), d)
    return d


def extend(base, more):
    """A mission's dictionary on top of the one it extends: the base's patterns (less "remove_patterns", with
    "change_patterns" applied), then its own; the slots, synonyms and number words merged (its own win); the fillers
    with its "add_fillers" and without its "remove_fillers"; its "symbols" and "minus"."""
    gone = set(more.get("remove_patterns") or [])
    changes = more.get("change_patterns") or {}
    out = dict(base)
    for k in ("name", "version", "mission", "notes", "symbols", "minus"):
        if k in more:
            out[k] = more[k]
    out["extends"] = more["extends"]
    out["patterns"] = [dict(p, **changes.get(p["id"], {})) for p in base["patterns"] if p["id"] not in gone] \
        + list(more.get("patterns") or [])
    out["slots"] = dict(base["slots"], **(more.get("slots") or {}))
    drop = set(more.get("remove_fillers") or [])
    out["fillers"] = [f for f in base["fillers"] if f not in drop] + \
        [f for f in more.get("add_fillers") or [] if f not in base["fillers"]]
    out["synonyms"] = dict(base["synonyms"], **(more.get("synonyms") or {}))
    for k in more.get("remove_synonyms") or []:
        out["synonyms"].pop(k, None)
    out["number_words"] = dict(base["number_words"], **(more.get("number_words") or {}))
    return out


def apply_synonyms(toks, c):
    for _ in range(6):
        out, i, changed = [], 0, False
        while i < len(toks):
            s = next((s for s in c.synonyms
                      if all(i + k < len(toks) and toks[i + k] == w for k, w in enumerate(s["from"]))), None)
            if s:
                out.extend(s["to"])
                if " ".join(s["to"]) != " ".join(s["from"]):
                    changed = True
                i += len(s["from"])
            else:
                out.append(toks[i])
                i += 1
        toks = out
        if not changed:
            break
    return toks


MINUS = re.compile(r"\s-|-\s|(?<=[a-z0-9])-(?=\d)|^-(?=\d)")  # (a - beside a space or before a digit: not pick-up)


def words(text, c):
    """text -> the words as typed, without case, punctuation or filler words (a dictionary's "symbols" read first,
    as words: lamps = lamps + 1 -> lamps equals lamps plus 1; "minus" for a - standing between two values, never
    inside a word as in pick-up)"""
    text = str(text).lower()
    for sign, word in c.symbols:
        text = text.replace(sign, word)
    if c.minus:
        text = MINUS.sub(" " + c.minus + " ", text)
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return [t for t in split_ws(text) if t and t not in c.fillers]


def tokenise(text, c):
    """text -> the words the patterns are matched against"""
    toks = apply_synonyms(words(text, c), c)
    toks = [t for t in toks if t not in c.fillers]
    nw = c.dict["number_words"]
    return [str(nw[t]) if t in nw else t for t in toks]


def match_pattern(p, toks, c):
    ws = p["words"]

    def rec(wi, ti, values):
        if wi == len(ws):
            return values if ti == len(toks) else None
        w = ws[wi]
        if not is_slot(w):
            return rec(wi + 1, ti + 1, values) if ti < len(toks) and toks[ti] == w else None
        name = slot_name(w)
        slot = c.dict["slots"][name]
        if slot["kind"] == "number":
            t = toks[ti] if ti < len(toks) else ""
            if not DIGITS.match(t or ""):
                return None
            n = int(t)
            if n < slot["min"] or n > slot["max"]:
                return None
            return rec(wi + 1, ti + 1, dict(values, **{name: n}))
        for v in slot["values"]:
            vw = v.split(" ")
            if all(ti + k < len(toks) and toks[ti + k] == x for k, x in enumerate(vw)):
                r = rec(wi + 1, ti + len(vw), dict(values, **{name: v}))
                if r is not None:
                    return r
        return None

    return rec(0, 0, {})


def parse_tokens(toks, c):
    for p in c.patterns:
        values = match_pattern(p, toks, c)
        if values is not None:
            return {"pattern": p, "values": values}
    return None


def fill(template, values):
    def one(m):
        key = m.group(1) or m.group(2)
        return str(values[key]) if key in values else m.group(0)
    return FILL.sub(one, template)


def canonical(hit):
    return fill(hit["pattern"]["say"], hit["values"])


def python_values(values, c):
    """A line's values as its Python says them: a slot's "python" map (path blocked -> robot.path_blocked()), else
    as they are."""
    out = {}
    for k, v in values.items():
        m = c.dict["slots"].get(k, {}).get("python")
        out[k] = m.get(v, v) if isinstance(m, dict) else v
    return out


def distance(a, b):
    """Damerau-Levenshtein (optimal string alignment): a swapped pair of letters counts as one slip"""
    d = [[i] + [0] * len(b) for i in range(len(a) + 1)]
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[len(a)][len(b)]


def near_words(tok, c):
    if len(tok) < 3 or DIGITS.match(tok):
        return []
    limit = 1 if len(tok) <= 4 else 2
    best, out = limit + 1, []
    for w in c.vocab:
        if abs(len(w) - len(tok)) > limit:
            continue
        dd = distance(tok, w)
        if dd < best:
            best, out = dd, [w]
        elif dd == best:
            out.append(w)
    return out if best <= limit else []


def try_tokens(toks, c):
    return parse_tokens(tokenise(" ".join(toks), c), c)


def permutations(arr):
    if len(arr) <= 1:
        yield list(arr)
        return
    for i in range(len(arr)):
        rest = arr[:i] + arr[i + 1:]
        for p in permutations(rest):
            yield [arr[i]] + p


def typo_fixes(toks, c):
    """every way of replacing the unknown words with their nearest known words"""
    combos = [[]]
    any_ = False
    for t in toks:
        known = t in c.vocab_set or bool(DIGITS.match(t))
        opts = [t] if known else near_words(t, c)
        if not known and opts:
            any_ = True
        choices = opts if opts else [t]
        nxt = []
        for cmb in combos:
            for o in choices:
                if len(nxt) < 64:
                    nxt.append(cmb + [o])
        combos = nxt
    return combos if any_ else []


def reorder(toks, c):
    if len(toks) < 2 or len(toks) > 6:
        return None
    same = " ".join(toks)
    for p in permutations(toks):
        if " ".join(p) == same:
            continue
        hit = try_tokens(p, c)
        if hit:
            return hit
    return None


def slot_trouble(toks, c):
    """the keywords are right but the value is missing or wrong"""
    for p in c.patterns:
        si = next((i for i, w in enumerate(p["words"]) if is_slot(w)), -1)
        if si < 0:
            continue
        pre, post = p["words"][:si], p["words"][si + 1:]
        if len(toks) < len(pre) + len(post):
            continue
        if not all(toks[k] == w for k, w in enumerate(pre)):
            continue
        if not all(toks[len(toks) - len(post) + k] == w for k, w in enumerate(post)):
            continue
        middle = toks[len(pre):len(toks) - len(post)]
        slot = c.dict["slots"][slot_name(p["words"][si])]
        lead = " ".join(pre)
        if not middle:
            return {"kind": "missing",
                    "message": f'"{lead}" needs {slot["describe"]}: {p["say"]} (for example: {p["example"]}).'}
        if len(middle) == 1 and DIGITS.match(middle[0]) and slot["kind"] == "number":
            return {"kind": "range",
                    "message": f'Use a number from {slot["min"]} to {slot["max"]}: {p["say"]} (for example: {p["example"]}).'}
        return {"kind": "value",
                "message": f'"{" ".join(middle)}" doesn\'t fit here: "{lead}" needs {slot["describe"]}. The pattern is {p["say"]}.'}
    return None


def diagnose(text, toks, c):
    """A line that matched no pattern: say why, and look for the one small change that would make it match.
    Tried in this order: a missing or out-of-range value, a misspelt word, the words in the wrong order, both,
    a missing keyword, one word too many, a value that doesn't fit. The first that works is the hint."""
    said = str(text).strip()
    typed = words(text, c)  # spelling is checked on the words as typed, before any synonym
    trouble = slot_trouble(toks, c)
    if trouble and trouble["kind"] != "value":
        return {"message": trouble["message"], "hint": None}
    for fixed in typo_fixes(typed, c):
        hit = try_tokens(fixed, c)
        if hit:
            return {"message": f'I don\'t know "{said}".', "hint": canonical(hit)}
    re_ = reorder(toks, c)
    if re_:
        return {"message": f'The words are right but in the wrong order. The pattern is {re_["pattern"]["say"]}.',
                "hint": canonical(re_)}
    for fixed in typo_fixes(typed, c):
        r2 = reorder(tokenise(" ".join(fixed), c), c)
        if r2:
            return {"message": f'I don\'t know "{said}". The pattern is {r2["pattern"]["say"]}.', "hint": canonical(r2)}
    for w in c.literals:
        for at in range(len(toks) + 1):
            hit = try_tokens(toks[:at] + [w] + toks[at:], c)
            if hit:
                return {"message": f'A keyword is missing. The pattern is {hit["pattern"]["say"]}.', "hint": canonical(hit)}
    for at in range(len(toks)):
        hit = try_tokens(toks[:at] + toks[at + 1:], c)
        if hit:
            return {"message": f'"{toks[at]}" isn\'t part of this instruction.', "hint": canonical(hit)}
    if trouble:
        return {"message": trouble["message"], "hint": None}
    starts = [p["say"] for p in c.patterns if toks and p["words"][0] == toks[0]]
    if starts:
        return {"message": f'Check how this is written: {" or ".join(starts)}.', "hint": None}
    return {"message": f'I don\'t recognise "{said}". Look in the phrasebook for what the robot understands.', "hint": None}


COMMENT = re.compile(r"^(#|//)")
COMMENT_LEAD = re.compile(r"^(#|//)\s?")


def parse_line(text, c):
    """One line, remembered: the window reads the whole program again at every key, and a line it can't read can
    take a moment to diagnose (every order of up to six words is tried). The same text always gives the same result."""
    key = str(text)
    if key not in c.lines:
        if len(c.lines) > 2000:
            c.lines.clear()
        c.lines[key] = read_line(key, c)
    return c.lines[key]


def read_line(text, c):
    trimmed = str(text).strip()
    if not trimmed:
        return {"kind": "blank"}
    if COMMENT.match(trimmed):
        return {"kind": "comment", "text": COMMENT_LEAD.sub("", trimmed, count=1)}
    toks = tokenise(trimmed, c)
    if not toks:
        return {"kind": "error", "message": "There's no instruction on this line, only filler words.", "hint": None}
    hit = parse_tokens(toks, c)
    if hit:
        return {"kind": "ok", "pattern": hit["pattern"], "values": hit["values"], "canonical": canonical(hit)}
    return dict({"kind": "error"}, **diagnose(trimmed, toks, c))


def block_words(c):
    """What an end can close, in words: "repeat" (Mission 1), "repeat or if" (Mission 2)."""
    return " or ".join(c.blocks)


def parse_program(text, c):
    """the whole program: every line checked, the repeats (and a mission's ifs and elses) matched to their ends, the
    Python beside each line. Returns {"rows", "errors", "program" (None while any line is an error), "code_lines",
    "python"}; a row is {"n", "raw", "kind", "indent", "python_line", ...} and an op in the program {"action",
    "values", "line", "body"} (an if's also "else": its else's lines, or None when it has none)."""
    rows = [dict({"n": i + 1, "raw": raw}, **parse_line(raw, c)) for i, raw in enumerate(re.split(r"\r?\n", str(text)))]
    root = {"body": []}
    stack = [{"node": root, "row": None}]

    def block(frame):
        return frame["row"]["pattern"].get("block", "repeat")

    for r in rows:
        r["indent"] = len(stack) - 1
        if r["kind"] == "blank":
            r["python"] = ""
            continue
        if r["kind"] == "comment":
            r["python"] = "# " + r["text"]
            continue
        if r["kind"] != "ok":
            continue
        p = r["pattern"]
        if p.get("middle"):  # (else: the if's own lines end here and the else's begin, up to the end)
            top = stack[-1]
            if len(stack) == 1 or block(top) != p["middle"] or top.get("middle"):
                r.update(kind="error", message=f"This {p['say']} has no {p['middle']} above it to belong to.", hint=None)
                continue
            r["indent"] = len(stack) - 2
            if not top["node"]["body"]:
                r.update(kind="error", message=f"This {p['middle']} has nothing inside it to do before the {p['say']}.",
                         hint=None)
            r["python"] = p["python"]
            top["middle"], top["then"] = r, top["node"]["body"]
            top["node"]["body"] = []
            continue
        if p.get("closes"):
            if len(stack) == 1:
                r.update(kind="error", message=f"This end has no {block_words(c)} to close.", hint=None)
                r["indent"] = 0
                continue
            top = stack.pop()
            r["indent"] = len(stack) - 1
            kind = block(top)
            if top.get("middle"):  # (an if with an else: the lines since the else are the else's)
                top["node"]["else"], top["node"]["body"] = top["node"]["body"], top["then"]
                if not top["node"]["else"]:
                    r.update(kind="error", message=f"This {top['middle']['pattern']['say']} has nothing inside it to do.",
                             hint=None)
            elif not top["node"]["body"]:
                r.update(kind="error", message="This repeat has nothing inside it to repeat." if kind == "repeat" else
                         f"This {kind} has nothing inside it to do.", hint=None)
            r["python"] = top["row"]["pattern"].get("end_python") or p["python"]
            continue
        op = {"action": p["id"], "values": r["values"], "line": r["n"]}
        r["python"] = fill(p["python"], dict({"var": LOOP_VARS[len(stack) - 1] if len(stack) - 1 < len(LOOP_VARS) else "n"},
                                             **python_values(r["values"], c)))
        if p.get("assigns"):  # (a name the program may read but not change: energy, the robot's battery)
            why = (c.dict["slots"][p["assigns"]].get("read_only") or {}).get(r["values"].get(p["assigns"]))
            if why:
                r.update(kind="error", message=why, hint=None)
        stack[-1]["node"]["body"].append(op)
        if p.get("opens"):
            if len(stack) > MAX_DEPTH:
                r.update(kind="error", message=f"A {block_words(c)} can be {MAX_DEPTH} deep at most.", hint=None)
            op["body"] = []
            if p.get("block"):
                op["else"] = None
            stack.append({"node": op, "row": r})
    for s in stack[1:]:
        if s["row"]["kind"] == "ok":
            kind = block(s)
            s["row"].update(kind="error", message=f"This {kind} needs an end.", hint=None,
                            after="Add a line that says end after the lines to repeat." if kind == "repeat" else
                            f"Add a line that says end after the {kind}'s lines.")
    errors = [r for r in rows if r["kind"] == "error"]
    for r in rows:
        pad = "    " * r["indent"]
        if r["kind"] == "error":
            r["python_line"] = pad + "# ? line " + str(r["n"]) + " isn't understood yet"
        else:
            r["python_line"] = pad + r["python"] if r.get("python") else ""
    return {
        "rows": rows, "errors": errors,
        "program": None if errors else root["body"],
        "code_lines": len([r for r in rows if r["kind"] in ("ok", "error")]),
        "python": "\n".join(r["python_line"] for r in rows),
    }
