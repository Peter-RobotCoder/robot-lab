/* The Club Coders pseudo code interpreter. Deterministic: the same text always gives the same result.
   A line is lower-cased, its punctuation dropped, its filler words dropped, its synonyms applied (until nothing
   changes) and its number words made digits; then it must match one pattern exactly: the keywords, the values
   and their order. A line that doesn't is an error with, where one can be found, a "did you mean" hint. The hint
   is only shown: nothing is ever corrected for the learner. */
(function (root) {
  "use strict";
  const isSlot = (w) => /^\[\w+\]$/.test(w);
  const slotName = (w) => w.slice(1, -1);
  const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const LOOP_VARS = ["i", "j", "k"];
  const MAX_DEPTH = 3;

  function compile(dict) {
    const patterns = dict.patterns.map((p) => Object.assign({}, p, { words: p.say.split(/\s+/) }));
    const synonyms = Object.keys(dict.synonyms).map((k) => ({ from: k.split(/\s+/), to: dict.synonyms[k].split(/\s+/).filter(Boolean) }))
      .sort((a, b) => b.from.length - a.from.length || (a.from.join(" ") < b.from.join(" ") ? -1 : 1));
    const fillers = new Set(dict.fillers);
    const literals = new Set();
    patterns.forEach((p) => p.words.forEach((w) => { if (!isSlot(w)) literals.add(w); }));
    const vocab = new Set(literals);
    Object.values(dict.slots).forEach((s) => (s.values || []).forEach((v) => v.split(" ").forEach((w) => vocab.add(w))));
    synonyms.forEach((s) => s.from.forEach((w) => vocab.add(w)));
    Object.keys(dict.number_words).forEach((w) => vocab.add(w));
    fillers.forEach((w) => vocab.add(w));
    return { dict, patterns, synonyms, fillers, literals: [...literals].sort(), vocab: [...vocab].sort() };
  }

  function applySynonyms(toks, c) {
    for (let pass = 0; pass < 6; pass++) {
      const out = []; let i = 0, changed = false;
      while (i < toks.length) {
        const s = c.synonyms.find((s) => s.from.every((w, k) => toks[i + k] === w));
        if (s) { out.push(...s.to); if (s.to.join(" ") !== s.from.join(" ")) changed = true; i += s.from.length; }
        else out.push(toks[i++]);
      }
      toks = out;
      if (!changed) break;
    }
    return toks;
  }

  // text -> the words as typed, without case, punctuation or filler words
  function words(text, c) {
    return String(text).toLowerCase().replace(/[^a-z0-9\s]+/g, " ").split(/\s+/).filter((t) => t && !c.fillers.has(t));
  }
  // text -> the words the patterns are matched against
  function tokenise(text, c) {
    let toks = applySynonyms(words(text, c), c);
    toks = toks.filter((t) => !c.fillers.has(t));
    return toks.map((t) => (has(c.dict.number_words, t) ? String(c.dict.number_words[t]) : t));
  }

  function matchPattern(p, toks, c) {
    const words = p.words;
    function rec(wi, ti, values) {
      if (wi === words.length) return ti === toks.length ? values : null;
      const w = words[wi];
      if (!isSlot(w)) return toks[ti] === w ? rec(wi + 1, ti + 1, values) : null;
      const name = slotName(w), slot = c.dict.slots[name];
      if (slot.kind === "number") {
        const t = toks[ti];
        if (!/^\d+$/.test(t || "")) return null;
        const n = parseInt(t, 10);
        if (n < slot.min || n > slot.max) return null;
        return rec(wi + 1, ti + 1, Object.assign({}, values, { [name]: n }));
      }
      for (const v of slot.values) {
        const vw = v.split(" ");
        if (vw.every((x, k) => toks[ti + k] === x)) {
          const r = rec(wi + 1, ti + vw.length, Object.assign({}, values, { [name]: v }));
          if (r) return r;
        }
      }
      return null;
    }
    return rec(0, 0, {});
  }

  function parseTokens(toks, c) {
    for (const p of c.patterns) {
      const values = matchPattern(p, toks, c);
      if (values) return { pattern: p, values };
    }
    return null;
  }

  const fill = (template, values) => template.replace(/\{(\w+)\}|\[(\w+)\]/g, (m, a, b) => (has(values, a || b) ? String(values[a || b]) : m));
  const canonical = (hit) => fill(hit.pattern.say, hit.values);

  // Damerau-Levenshtein (optimal string alignment): a swapped pair of letters counts as one slip
  function distance(a, b) {
    const d = [];
    for (let i = 0; i <= a.length; i++) { d[i] = [i]; }
    for (let j = 0; j <= b.length; j++) { d[0][j] = j; }
    for (let i = 1; i <= a.length; i++) {
      for (let j = 1; j <= b.length; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
    return d[a.length][b.length];
  }

  function nearWords(tok, c) {
    if (tok.length < 3 || /^\d+$/.test(tok)) return [];
    const limit = tok.length <= 4 ? 1 : 2;
    let best = limit + 1, out = [];
    for (const w of c.vocab) {
      if (Math.abs(w.length - tok.length) > limit) continue;
      const d = distance(tok, w);
      if (d < best) { best = d; out = [w]; } else if (d === best) out.push(w);
    }
    return best <= limit ? out : [];
  }

  function tryTokens(toks, c) { return parseTokens(tokenise(toks.join(" "), c), c); }

  function* permutations(arr) {
    if (arr.length <= 1) { yield arr.slice(); return; }
    for (let i = 0; i < arr.length; i++) {
      const rest = arr.slice(0, i).concat(arr.slice(i + 1));
      for (const p of permutations(rest)) yield [arr[i]].concat(p);
    }
  }

  function typoFixes(toks, c) {  // every way of replacing the unknown words with their nearest known words
    let combos = [[]];
    let any = false;
    for (const t of toks) {
      const known = c.vocab.includes(t) || /^\d+$/.test(t);
      const opts = known ? [t] : nearWords(t, c);
      if (!known && opts.length) any = true;
      const choices = opts.length ? opts : [t];
      const next = [];
      for (const cmb of combos) for (const o of choices) if (next.length < 64) next.push(cmb.concat([o]));
      combos = next;
    }
    return any ? combos : [];
  }

  function reorder(toks, c) {
    if (toks.length < 2 || toks.length > 6) return null;
    const same = toks.join(" ");
    for (const p of permutations(toks)) {
      if (p.join(" ") === same) continue;
      const hit = tryTokens(p, c);
      if (hit) return hit;
    }
    return null;
  }

  function slotTrouble(toks, c) {  // the keywords are right but the value is missing or wrong
    for (const p of c.patterns) {
      const si = p.words.findIndex(isSlot);
      if (si < 0) continue;
      const pre = p.words.slice(0, si), post = p.words.slice(si + 1);
      if (toks.length < pre.length + post.length) continue;
      if (!pre.every((w, k) => toks[k] === w)) continue;
      if (!post.every((w, k) => toks[toks.length - post.length + k] === w)) continue;
      const middle = toks.slice(pre.length, toks.length - post.length);
      const slot = c.dict.slots[slotName(p.words[si])];
      const lead = pre.join(" ");
      if (!middle.length) return { kind: "missing", message: `"${lead}" needs ${slot.describe}: ${p.say} (for example: ${p.example}).` };
      if (middle.length === 1 && /^\d+$/.test(middle[0]) && slot.kind === "number")
        return { kind: "range", message: `Use a number from ${slot.min} to ${slot.max}: ${p.say} (for example: ${p.example}).` };
      return { kind: "value", message: `"${middle.join(" ")}" doesn't fit here: "${lead}" needs ${slot.describe}. The pattern is ${p.say}.` };
    }
    return null;
  }

  // A line that matched no pattern: say why, and look for the one small change that would make it match.
  // Tried in this order: a missing or out-of-range value, a misspelt word, the words in the wrong order, both,
  // a missing keyword, one word too many, a value that doesn't fit. The first that works is the hint.
  function diagnose(text, toks, c) {
    const said = String(text).trim();
    const typed = words(text, c);  // spelling is checked on the words as typed, before any synonym
    const trouble = slotTrouble(toks, c);
    if (trouble && trouble.kind !== "value") return { message: trouble.message, hint: null };
    for (const fixed of typoFixes(typed, c)) {
      const hit = tryTokens(fixed, c);
      if (hit) return { message: `I don't know "${said}".`, hint: canonical(hit) };
    }
    const re = reorder(toks, c);
    if (re) return { message: `The words are right but in the wrong order. The pattern is ${re.pattern.say}.`, hint: canonical(re) };
    for (const fixed of typoFixes(typed, c)) {
      const r2 = reorder(tokenise(fixed.join(" "), c), c);
      if (r2) return { message: `I don't know "${said}". The pattern is ${r2.pattern.say}.`, hint: canonical(r2) };
    }
    for (const w of c.literals) {
      for (let at = 0; at <= toks.length; at++) {
        const hit = tryTokens(toks.slice(0, at).concat([w], toks.slice(at)), c);
        if (hit) return { message: `A keyword is missing. The pattern is ${hit.pattern.say}.`, hint: canonical(hit) };
      }
    }
    for (let at = 0; at < toks.length; at++) {
      const hit = tryTokens(toks.slice(0, at).concat(toks.slice(at + 1)), c);
      if (hit) return { message: `"${toks[at]}" isn't part of this instruction.`, hint: canonical(hit) };
    }
    if (trouble) return { message: trouble.message, hint: null };
    const starts = c.patterns.filter((p) => p.words[0] === toks[0]).map((p) => p.say);
    if (starts.length) return { message: `Check how this is written: ${starts.join(" or ")}.`, hint: null };
    return { message: `I don't recognise "${said}". Look in the phrasebook for what the robot understands.`, hint: null };
  }

  function parseLine(text, c) {
    const trimmed = String(text).trim();
    if (!trimmed) return { kind: "blank" };
    if (/^(#|\/\/)/.test(trimmed)) return { kind: "comment", text: trimmed.replace(/^(#|\/\/)\s?/, "") };
    const toks = tokenise(trimmed, c);
    if (!toks.length) return { kind: "error", message: "There's no instruction on this line, only filler words.", hint: null };
    const hit = parseTokens(toks, c);
    if (hit) return { kind: "ok", pattern: hit.pattern, values: hit.values, canonical: canonical(hit) };
    return Object.assign({ kind: "error" }, diagnose(trimmed, toks, c));
  }

  // the whole program: every line checked, the repeats matched to their ends, the Python beside each line
  function parseProgram(text, c) {
    const rows = String(text).split(/\r?\n/).map((raw, i) => Object.assign({ n: i + 1, raw }, parseLine(raw, c)));
    const root = { body: [] };
    const stack = [{ node: root, row: null }];
    for (const r of rows) {
      r.indent = stack.length - 1;
      if (r.kind === "blank") { r.python = ""; continue; }
      if (r.kind === "comment") { r.python = "# " + r.text; continue; }
      if (r.kind !== "ok") continue;
      const p = r.pattern;
      if (p.closes) {
        if (stack.length === 1) { Object.assign(r, { kind: "error", message: "This end has no repeat to close.", hint: null }); r.indent = 0; continue; }
        const top = stack.pop();
        r.indent = stack.length - 1;
        if (!top.node.body.length) Object.assign(r, { kind: "error", message: "This repeat has nothing inside it to repeat.", hint: null });
        r.python = p.python;
        continue;
      }
      const op = { action: p.id, values: r.values, line: r.n };
      r.python = fill(p.python, Object.assign({ var: LOOP_VARS[stack.length - 1] || "n" }, r.values));
      stack[stack.length - 1].node.body.push(op);
      if (p.opens) {
        if (stack.length > MAX_DEPTH) { Object.assign(r, { kind: "error", message: `A repeat can be ${MAX_DEPTH} deep at most.`, hint: null }); }
        op.body = [];
        stack.push({ node: op, row: r });
      }
    }
    for (const s of stack.slice(1)) {
      if (s.row.kind === "ok") Object.assign(s.row, { kind: "error", message: "This repeat needs an end.", hint: null, after: "Add a line that says end after the lines to repeat." });
    }
    const errors = rows.filter((r) => r.kind === "error");
    for (const r of rows) {
      const pad = "    ".repeat(r.indent);
      r.pythonLine = r.kind === "error" ? pad + "# ? line " + r.n + " isn't understood yet" : (r.python ? pad + r.python : "");
    }
    return {
      rows, errors,
      program: errors.length ? null : root.body,
      codeLines: rows.filter((r) => r.kind === "ok" || r.kind === "error").length,
      python: rows.map((r) => r.pythonLine).join("\n"),
    };
  }

  root.CCPseudo = { compile, tokenise, parseLine, parseProgram, distance, canonical };
})(typeof window !== "undefined" ? window : globalThis);
