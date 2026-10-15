// A game's design as variables (engine/schema.py, ported line for line): the code panel writes the design as Python,
// one typed variable a line with a sentence above it, and reads the edited code back as data. Nothing is ever run:
// the code is read the way Python's own parser reads it (its tokenizer and grammar, the parts of them the code can
// reach, with the same error messages and line numbers), and the values are read as ast.literal_eval reads them.
// The garage's tables come from the same list of variables (engine/garage.py).
//
// The schema itself comes from schemas.json (make_schemas.py writes it from lab_sim.py, fight_sim.py and
// kart_sim.py): the class servers send the rules and the limits, but not the schema. A variable's own rules are
// Python functions there; here each is the function of the same name in FUNCTIONS, below.
//
// Python's values that JavaScript has no exact twin for come back from parseCode as small classes: PyFloat (a
// number written with a point: 25.0 is not 25 to an rgb colour), PyTuple, PySet, PyDict, PyBytes, PyComplex, PyStr
// (a string with a lone surrogate) and BigInt (an int too big for a number). applyValues stores plain numbers,
// strings and lists in the design (and a PyStr, which JSON writes as its string).
//
// What Python 3.12 reads that this doesn't, exactly: "\N{NAME}" escapes (the browser has no Unicode name list: a
// valid name is reported as unknown); code nested more than about 1,500 deep (the browser's stack runs out, and
// that is reported as the crash Python reports past about 3,000; nothing that deep can be a value). And a design
// that comes through JSON can't say 49.0 from 49: the app's code shows "points used: 49.0" for a float point, the
// page "49" (the servers only send whole points). schema_test.py compares the rest with the app's own Python.
//
//   codeLines(game, design, ctx)            the code panel's lines (engine.schema.code_lines)
//   parseCode(game, text, ctx)              {name: value}, or throws ParseError (lineno, message)
//   applyValues(game, design, values, ctx, allowed)   {changed, hidden, problems}
//   applyCode(game, design, text, opts)     everything APPLY CODE does in the app's window, without the window
//   codeCtx(game, opts), codeAllowed(game, tools, design), outsideLimits(game, values, limits, teacher)
//   checkDesign(game, design, limits), limits: defaultLimits, fullLimits, codeRoom
//   garageTables(game, design, ctx, tools, limits, opts), shown, canChange, outsideLesson
// game: a game's entry in schemas.json ({vars, limits, consts...}).

// ---------- Python's values ----------

export class PyFloat {  // a float: 25.0 (JavaScript's 25 is Python's int)
    constructor(v) { this.v = v; }
    valueOf() { return this.v; }
}
export class PyComplex { constructor(re, im) { this.re = re; this.im = im; } }
export class PyTuple { constructor(items) { this.items = items; } }
export class PyBytes { constructor(bytes) { this.bytes = bytes; } }
// A Python string with a lone surrogate in it: a learner types "\ud83e\udd16" in the code and Python reads two
// characters, not one emoji; a JavaScript string would join them. Written out, it is the joined string. (The code
// itself writes an emoji as one "\U0001f916" escape, so a design's emoji reads back as one character.)
export class PyStr {
    constructor(cps) { this.cps = cps; }
    toString() { let s = ""; for (const c of this.cps) s += String.fromCodePoint(c); return s; }
    toJSON() { return this.toString(); }
}
export const ELLIPSIS = Object.freeze({ellipsis: true});

// an exception Python raises that the app doesn't catch (the window would show its error and carry on)
export class PyError extends Error {
    constructor(type, message) { super(`${type}: ${message}`); this.type = type; this.pyMessage = message; }
}

// a line of code the app can't read: what its code panel says, "Line 3: ..."
export class ParseError extends Error {
    constructor(lineno, message) { super(message); this.lineno = lineno; this.message = message; }
}

function hashKey(v) {  // what makes two values the same key in a Python set or dictionary
    const num = x => (Number.isInteger(x) ? BigInt(x).toString() : String(x));
    if (v === null) return "N";
    if (typeof v === "bigint") return "n" + v.toString();
    if (typeof v === "boolean") return "n" + (v ? 1 : 0);
    if (typeof v === "number") return "n" + num(v);
    if (v instanceof PyFloat) return "n" + num(v.v);
    if (v instanceof PyComplex) return v.im === 0 ? "n" + num(v.re) : "c" + num(v.re) + "," + num(v.im);
    if (isStr(v)) return "s" + cpsOf(v).join(",");
    if (v instanceof PyTuple) return "t" + JSON.stringify(v.items.map(hashKey));
    if (v instanceof PyBytes) return "b" + v.bytes.join(",");
    if (v === ELLIPSIS) return "E";
    throw new PyError("TypeError", "unhashable type");
}

export class PySet {
    constructor() { this.map = new Map(); }
    add(v) { const k = hashKey(v); if (!this.map.has(k)) this.map.set(k, v); }
    get items() { return [...this.map.values()]; }
}

export class PyDict {
    constructor() { this.map = new Map(); }
    set(k, v) { const h = hashKey(k); const old = this.map.get(h); this.map.set(h, [old ? old[0] : k, v]); }
    get(k) {
        const e = this.map.get(hashKey(k));
        if (!e) throw new PyError("KeyError", pyRepr(k));
        return e[1];
    }
    get keys() { return [...this.map.values()].map(e => e[0]); }
    get values() { return [...this.map.values()].map(e => e[1]); }
}

function isDict(v) {  // a plain object from JSON (a Python dict), or a PyDict
    return v instanceof PyDict || (v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof PyFloat)
        && !(v instanceof PyComplex) && !(v instanceof PyTuple) && !(v instanceof PySet) && !(v instanceof PyBytes)
        && !(v instanceof PyStr)
        && v !== ELLIPSIS);
}
const has = (o, k) => o !== null && typeof o === "object" && Object.prototype.hasOwnProperty.call(o, k);
const pyGet = (o, k, dflt = null) => (has(o, k) ? o[k] : dflt);  // dict.get(k, default)
const cp = s => Array.from(s);  // a string's characters as Python counts them (code points)
const isStr = v => typeof v === "string" || v instanceof PyStr;
const cpsOf = v => (v instanceof PyStr ? v.cps : cp(v).map(c => c.codePointAt(0)));
function makeStr(cps) {  // Python's string of these characters: a JavaScript string, or a PyStr if it must be
    if (cps.some(c => c >= 0xd800 && c <= 0xdfff)) return new PyStr(cps);
    let s = "";
    for (const c of cps) s += String.fromCodePoint(c);
    return s;
}

// (a Python int is a number, or a BigInt when it is too big for a number to hold exactly)
function isNum(v) { return typeof v === "number" || typeof v === "bigint" || v instanceof PyFloat; }  // isinstance(v, (int, float)), not bool
function isInt(v) { return (typeof v === "number" && Number.isInteger(v)) || typeof v === "bigint"; }   // isinstance(v, int), not bool
const num = v => (v instanceof PyFloat ? v.v : typeof v === "boolean" ? (v ? 1 : 0) : typeof v === "bigint" ? Number(v) : v);

export function pyTruthy(v) {
    if (v === null || v === undefined || v === false) return false;
    if (typeof v === "number") return v !== 0;
    if (typeof v === "bigint") return v !== 0n;
    if (v instanceof PyFloat) return v.v !== 0;
    if (v instanceof PyComplex) return v.re !== 0 || v.im !== 0;
    if (isStr(v)) return cpsOf(v).length > 0;
    if (Array.isArray(v)) return v.length > 0;
    if (v instanceof PyTuple) return v.items.length > 0;
    if (v instanceof PySet || v instanceof PyDict) return v.map.size > 0;
    if (v instanceof PyBytes) return v.bytes.length > 0;
    if (isDict(v)) return Object.keys(v).length > 0;
    return true;
}

export function pyEq(a, b) {  // Python's ==
    const numeric = v => typeof v === "number" || typeof v === "bigint" || typeof v === "boolean" || v instanceof PyFloat
        || v instanceof PyComplex;
    if (numeric(a) && numeric(b) && (typeof a === "bigint" || typeof b === "bigint")) {  // (exactly, as Python does)
        const real = v => (v instanceof PyComplex ? (v.im === 0 ? v.re : NaN) : typeof v === "bigint" ? v : num(v));
        const x = real(a), y = real(b);
        if (typeof x === "bigint" && typeof y === "bigint") return x === y;
        const f = typeof x === "bigint" ? y : x, big = typeof x === "bigint" ? x : y;
        return Number.isInteger(f) && BigInt(f) === big;
    }
    if (numeric(a) && numeric(b)) {
        const c = v => (v instanceof PyComplex ? [v.re, v.im] : [num(v), 0]);
        const [ar, ai] = c(a), [br, bi] = c(b);
        return ar === br && ai === bi;
    }
    if (typeof a === "string" && typeof b === "string") return a === b;
    if (isStr(a) || isStr(b)) return isStr(a) && isStr(b) && cpsOf(a).join() === cpsOf(b).join();
    if (a === null || b === null) return a === b;
    if (Array.isArray(a) || Array.isArray(b)) {
        return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => pyEq(x, b[i]));
    }
    if (a instanceof PyTuple || b instanceof PyTuple) {
        return a instanceof PyTuple && b instanceof PyTuple && a.items.length === b.items.length
            && a.items.every((x, i) => pyEq(x, b.items[i]));
    }
    if (a instanceof PyBytes || b instanceof PyBytes) {
        return a instanceof PyBytes && b instanceof PyBytes && a.bytes.join() === b.bytes.join();
    }
    if (a instanceof PySet || b instanceof PySet) {
        return a instanceof PySet && b instanceof PySet && a.map.size === b.map.size && [...a.map.keys()].every(k => b.map.has(k));
    }
    if (isDict(a) && isDict(b)) {
        const pairs = d => (d instanceof PyDict ? [...d.map.values()] : Object.entries(d));
        const pa = pairs(a), pb = pairs(b);
        if (pa.length !== pb.length) return false;
        return pa.every(([k, v]) => pb.some(([k2, v2]) => pyEq(k, k2) && pyEq(v, v2)));
    }
    return a === b;
}

const pyIn = (v, list) => list.some(o => pyEq(v, o));

export function pyList(v) {  // list(v)
    if (Array.isArray(v)) return v.slice();
    if (v instanceof PyTuple) return v.items.slice();
    if (isStr(v)) return cpsOf(v).map(c => makeStr([c]));
    if (v instanceof PySet) return v.items;
    if (v instanceof PyDict) return v.keys;
    if (v instanceof PyBytes) return v.bytes.slice();
    if (isDict(v)) return Object.keys(v);
    throw new PyError("TypeError", "object is not iterable");
}

function pyLen(v) {
    if (Array.isArray(v)) return v.length;
    if (v instanceof PyTuple) return v.items.length;
    if (isStr(v)) return cpsOf(v).length;
    if (v instanceof PyBytes) return v.bytes.length;
    if (v instanceof PySet || v instanceof PyDict) return v.map.size;
    if (isDict(v)) return Object.keys(v).length;
    throw new PyError("TypeError", "object has no len()");
}

function pyIndex(seq, i) {  // seq[i]
    let items = null;
    if (Array.isArray(seq)) items = seq;
    else if (seq instanceof PyTuple) items = seq.items;
    else if (isStr(seq)) items = cpsOf(seq).map(c => makeStr([c]));
    else if (seq instanceof PyBytes) items = seq.bytes;
    if (items) {
        let n;
        if (typeof i === "boolean") n = i ? 1 : 0;
        else if (typeof i === "bigint") throw new PyError("IndexError", "index out of range");
        else if (isInt(i)) n = i;
        else if (i === Infinity || i === -Infinity) throw new PyError("IndexError", "cannot fit 'int' into an index-sized integer");
        else throw new PyError("TypeError", "indices must be integers or slices");
        if (n < 0) n += items.length;
        if (n < 0 || n >= items.length) throw new PyError("IndexError", "index out of range");
        return items[n];
    }
    if (seq instanceof PyDict) return seq.get(i);
    throw new PyError("TypeError", "object is not subscriptable");
}

// ---------- Python's ways of writing values ----------

function shortestDigits(ax) {  // the fewest digits that read back as ax (as repr() finds them): {digits, exp}
    const s = String(ax);
    let mant = s, e = 0;
    const k = s.indexOf("e");
    if (k >= 0) { mant = s.slice(0, k); e = Number(s.slice(k + 1)); }
    const [ip, fp = ""] = mant.split(".");
    let digits = ip + fp, exp = ip.length - 1 + e, lead = 0;
    while (lead < digits.length - 1 && digits[lead] === "0") { lead++; exp--; }
    digits = digits.slice(lead).replace(/0+$/, "") || "0";
    return {digits, exp};
}

function exactDigits(ax) {  // every digit of a double, exactly (as format() rounds from them): {digits, exp}
    const dv = new DataView(new ArrayBuffer(8));
    dv.setFloat64(0, ax);
    const hi = dv.getUint32(0), lo = dv.getUint32(4);
    let e = (hi >>> 20) & 0x7ff;
    let m = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
    if (e === 0) e = 1; else m |= 1n << 52n;
    e -= 1075;
    const s = e >= 0 ? (m << BigInt(e)).toString() : (m * 5n ** BigInt(-e)).toString();
    return {digits: s, exp: s.length - 1 + (e >= 0 ? 0 : e)};
}

export function floatRepr(x) {  // repr(float)
    if (Number.isNaN(x)) return "nan";
    if (x === Infinity) return "inf";
    if (x === -Infinity) return "-inf";
    if (x === 0) return Object.is(x, -0) ? "-0.0" : "0.0";
    const sign = x < 0 ? "-" : "";
    const {digits, exp} = shortestDigits(Math.abs(x));
    if (exp < -4 || exp >= 16) {
        const m = digits.length > 1 ? digits[0] + "." + digits.slice(1) : digits;
        return sign + m + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
    }
    if (exp >= 0) {
        const ip = digits.length > exp + 1 ? digits.slice(0, exp + 1) : digits.padEnd(exp + 1, "0");
        return sign + ip + "." + (digits.length > exp + 1 ? digits.slice(exp + 1) : "0");
    }
    return sign + "0." + "0".repeat(-exp - 1) + digits;
}

export function formatG(x) {  // f"{x:g}": six significant digits, rounded half to even from the exact value
    x = num(x);
    if (typeof x !== "number") throw new PyError("ValueError", "Unknown format code 'g'");
    if (Number.isNaN(x)) return "nan";
    if (x === Infinity) return "inf";
    if (x === -Infinity) return "-inf";
    if (x === 0) return Object.is(x, -0) ? "-0" : "0";
    const sign = x < 0 ? "-" : "", P = 6;
    let {digits, exp} = exactDigits(Math.abs(x));
    if (digits.length > P) {
        const keep = digits.slice(0, P), rest = digits.slice(P);
        const up = rest[0] > "5" || (rest[0] === "5" && (/[1-9]/.test(rest.slice(1)) || Number(keep[P - 1]) % 2 === 1));
        let ks = (BigInt(keep) + (up ? 1n : 0n)).toString();
        if (ks.length > P) { ks = ks.slice(0, P); exp += 1; }
        digits = ks;
    }
    digits = digits.replace(/0+$/, "") || "0";
    if (exp >= -4 && exp < P) {
        if (exp < 0) return sign + "0." + "0".repeat(-exp - 1) + digits;
        const ip = digits.slice(0, exp + 1).padEnd(exp + 1, "0"), fp = digits.slice(exp + 1);
        return sign + ip + (fp ? "." + fp : "");
    }
    const m = digits[0] + (digits.length > 1 ? "." + digits.slice(1) : "");
    return sign + m + "e" + (exp < 0 ? "-" : "+") + String(Math.abs(exp)).padStart(2, "0");
}

function intStr(x) {  // str(int)
    return Number.isSafeInteger(x) ? String(x) : BigInt(x).toString();
}

function numStr(x) {  // str() of a JSON number: whole numbers are Python's ints
    if (Number.isInteger(x)) return intStr(x);
    return floatRepr(x);
}

const PRINTABLE_NOT = /[\p{C}\p{Z}]/u;
function isPrintable(c) { return c === " " || !PRINTABLE_NOT.test(c); }  // str.isprintable(), one character

function strRepr(s) {  // repr(str)
    const text = String(s), quote = text.includes("'") && !text.includes('"') ? '"' : "'";
    let out = quote;
    for (const n of cpsOf(s)) {
        const c = String.fromCodePoint(n);
        if (c === quote || c === "\\") out += "\\" + c;
        else if (c === "\t") out += "\\t";
        else if (c === "\n") out += "\\n";
        else if (c === "\r") out += "\\r";
        else if (n < 0x20 || n === 0x7f) out += "\\x" + n.toString(16).padStart(2, "0");
        else if (n < 0x7f || isPrintable(c)) out += c;
        else if (n <= 0xff) out += "\\x" + n.toString(16).padStart(2, "0");
        else if (n <= 0xffff) out += "\\u" + n.toString(16).padStart(4, "0");
        else out += "\\U" + n.toString(16).padStart(8, "0");
    }
    return out + quote;
}

function complexPart(x) { const r = floatRepr(x); return r.endsWith(".0") ? r.slice(0, -2) : r; }

export function pyRepr(v) {
    if (isStr(v)) return strRepr(v);
    if (Array.isArray(v)) return "[" + v.map(pyRepr).join(", ") + "]";
    if (v instanceof PyTuple) return "(" + v.items.map(pyRepr).join(", ") + (v.items.length === 1 ? ",)" : ")");
    if (v instanceof PySet) return v.map.size ? "{" + v.items.map(pyRepr).join(", ") + "}" : "set()";
    if (v instanceof PyDict) return "{" + [...v.map.values()].map(([k, x]) => pyRepr(k) + ": " + pyRepr(x)).join(", ") + "}";
    if (v instanceof PyBytes) {
        let s = "";
        for (const b of v.bytes) {
            s += b === 0x27 ? "\\'" : b === 0x5c ? "\\\\" : b === 9 ? "\\t" : b === 10 ? "\\n" : b === 13 ? "\\r"
                : b < 0x20 || b >= 0x7f ? "\\x" + b.toString(16).padStart(2, "0") : String.fromCharCode(b);
        }
        return "b'" + s + "'";
    }
    if (isDict(v)) return "{" + Object.entries(v).map(([k, x]) => strRepr(k) + ": " + pyRepr(x)).join(", ") + "}";
    return pyStr(v);
}

export function pyStr(v) {  // str(v)
    if (v === null || v === undefined) return "None";
    if (v === true) return "True";
    if (v === false) return "False";
    if (typeof v === "number") return numStr(v);
    if (typeof v === "bigint") return v.toString();
    if (v instanceof PyFloat) return floatRepr(v.v);
    if (v instanceof PyComplex) {
        if (v.re === 0 && !Object.is(v.re, -0)) return complexPart(v.im) + "j";
        return "(" + complexPart(v.re) + (v.im < 0 || Object.is(v.im, -0) ? "-" : "+") + complexPart(Math.abs(v.im)) + "j)";
    }
    if (v === ELLIPSIS) return "Ellipsis";
    if (typeof v === "string") return v;
    if (v instanceof PyStr) return v.toString();
    return pyRepr(v);
}

// engine.schema.quote: a string as json.dumps writes it (ASCII only), but an emoji (beyond the first 65536 characters)
// as one \UXXXXXXXX escape, so the code reads back as the same one character
function jsonStr(s) {
    let out = '"';
    for (const c of cpsOf(s)) {  // (character by character as Python counts them: a PyStr's lone surrogates stay apart)
        if (c === 0x22) out += '\\"';
        else if (c === 0x5c) out += "\\\\";
        else if (c === 0x0a) out += "\\n";
        else if (c === 0x0d) out += "\\r";
        else if (c === 0x09) out += "\\t";
        else if (c === 0x08) out += "\\b";
        else if (c === 0x0c) out += "\\f";
        else if (c > 0xffff) out += "\\U" + c.toString(16).padStart(8, "0");
        else if (c < 0x20 || c > 0x7e) out += "\\u" + c.toString(16).padStart(4, "0");
        else out += String.fromCharCode(c);
    }
    return out + '"';
}

export function jsonDumps(v) {  // json.dumps(v), with Python's spaces after commas and colons
    if (v === null || v === undefined) return "null";
    if (v === true) return "true";
    if (v === false) return "false";
    if (typeof v === "bigint") return v.toString();
    if (typeof v === "number" || v instanceof PyFloat) {
        const x = num(v);
        if (Number.isNaN(x)) return "NaN";
        if (x === Infinity) return "Infinity";
        if (x === -Infinity) return "-Infinity";
        return typeof v === "number" ? numStr(x) : floatRepr(x);
    }
    if (isStr(v)) return jsonStr(v);
    if (Array.isArray(v)) return "[" + v.map(jsonDumps).join(", ") + "]";
    if (v instanceof PyTuple) return "[" + v.items.map(jsonDumps).join(", ") + "]";
    if (isDict(v)) {
        const entries = v instanceof PyDict ? [...v.map.values()] : Object.entries(v);
        return "{" + entries.map(([k, x]) => {
            let key;
            if (isStr(k)) key = String(k);
            else if (k === null) key = "null";
            else if (typeof k === "boolean") key = k ? "true" : "false";
            else if (isNum(k)) key = jsonDumps(k);
            else throw new PyError("TypeError", "keys must be str, int, float, bool or None");
            return jsonStr(key) + ": " + jsonDumps(x);
        }).join(", ") + "}";
    }
    throw new PyError("TypeError", "Object is not JSON serializable");
}

// Python's str.isspace(), and str.strip() with it
const SPACES = new Set([..."\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0     　"]);
for (let c = 0x2000; c <= 0x200a; c++) SPACES.add(String.fromCharCode(c));
const isSpace = c => SPACES.has(c);
function pyStrip(s) {
    const cs = cp(s);
    let a = 0, b = cs.length;
    while (a < b && isSpace(cs[a])) a++;
    while (b > a && isSpace(cs[b - 1])) b--;
    return cs.slice(a, b).join("");
}

// ---------- textwrap.wrap (Python's), for the sentences above each line ----------
const TW = "\\t\\n\\x0b\\x0c\\r ";
const W = "[\\p{L}\\p{N}_]", WP = "[\\p{L}\\p{N}_!\"'&.,?]", LT = "[\\p{L}\\p{Nl}\\p{No}_]";
const WORDSEP = new RegExp(
    `([${TW}]+` +                                                     // any whitespace
    `|(?<=${WP})-{2,}(?=${W})` +                                      // an em-dash between words
    `|[^${TW}]+?(?:-(?:(?<=${LT}{2}-)|(?<=${LT}-${LT}-))(?=${LT}-?${LT})` +  // a word, maybe hyphenated
    `|(?=[${TW}]|$)` +                                                // ...the end of a word
    `|(?<=${WP})(?=-{2,}${W})))`, "gu");                              // ...before an em-dash

function expandTabs(text) {
    let out = "", col = 0;
    for (const c of text) {
        if (c === "\t") { const n = 8 - (col % 8); out += " ".repeat(n); col += n; }
        else if (c === "\n" || c === "\r") { out += c; col = 0; }
        else { out += c; col += 1; }
    }
    return out;
}

export function wrap(text, width) {
    text = expandTabs(text).replace(/[\t\n\x0b\x0c\r]/g, " ");
    let chunks = [], last = 0, m;
    WORDSEP.lastIndex = 0;
    while ((m = WORDSEP.exec(text)) !== null) {
        if (m.index > last) chunks.push(text.slice(last, m.index));
        chunks.push(m[0]);
        last = m.index + m[0].length;
        if (m[0].length === 0) WORDSEP.lastIndex++;
    }
    if (last < text.length) chunks.push(text.slice(last));
    chunks = chunks.filter(c => c).map(cp).reverse();  // (each chunk as its characters, as Python counts them)
    const blank = c => c.every(isSpace);
    const lines = [];
    while (chunks.length) {
        let cur = [], len = 0;
        if (blank(chunks[chunks.length - 1]) && lines.length) chunks.pop();
        while (chunks.length) {
            const l = chunks[chunks.length - 1].length;
            if (len + l <= width) { cur.push(chunks.pop()); len += l; } else break;
        }
        if (chunks.length && chunks[chunks.length - 1].length > width) {  // a word longer than a line: broken
            const space = width < 1 ? 1 : width - len, chunk = chunks[chunks.length - 1];
            let end = space;
            if (chunk.length > space) {
                const hyphen = chunk.slice(0, space).lastIndexOf("-");
                if (hyphen > 0 && chunk.slice(0, hyphen).some(c => c !== "-")) end = hyphen + 1;
            }
            cur.push(chunk.slice(0, end));
            chunks[chunks.length - 1] = chunk.slice(end);
        }
        if (cur.length && blank(cur[cur.length - 1])) cur.pop();
        if (cur.length) lines.push(cur.map(c => c.join("")).join(""));
    }
    return lines;
}

// ---------- the code, written (engine.schema.code_lines) ----------

// (CHANGE 89) what each line of the code pop-up does, in plain words: one sentence above each line
export const COMMENTS = {
    int: "creating an integer variable called {name} and setting its value to {value} ({note})",
    float: "creating a decimal variable called {name} and setting its value to {value} ({note})",
    str: "creating a string variable called {name} and setting its value to {value} ({note})",
    str_plain: "creating a string variable called {name} and setting its value to {value}",
    options: "creating a list variable called {list} holding {note}",
    choice: "picking item {i} ({item}) from the list {list} and storing it in the string variable {name} (0 is the first)",
    choice_other: "creating a string variable called {name} and setting its value to {value} (the one chosen)",
    rgb: "creating a list variable called {name} holding three integers: red {r}, green {g}, blue {b} ({note})",
    list: "creating a list variable called {name} holding these values in order ({note})",
    list_plain: "creating a list variable called {name} holding these values in order",
};

function comment(key, words) {  // the sentence as comment lines, 60 letters a line
    const text = COMMENTS[key].replace(/\{(\w+)\}/g, (_, k) => pyStr(words[k]));
    return wrap(text, 60).map(line => "# " + line);
}

export function getVar(v, design) {
    let d = design;
    for (const k of v.path) {
        if (!isDict(d) || !has(d, k)) return null;
        d = d[k];
    }
    return d === undefined ? null : d;
}

export function setVar(v, design, value) {
    let d = design;
    for (const k of v.path.slice(0, -1)) {
        if (!has(d, k)) d[k] = {};
        d = d[k];
    }
    const last = v.path[v.path.length - 1];
    if (value === null && v.optional) delete d[last];
    else d[last] = value;
}

const varsOf = game => (Array.isArray(game) ? game : game.vars);
const fn = (game, name) => {
    const f = FUNCTIONS[name];
    if (!f) throw new Error(`schema.js doesn't know the function ${name}`);
    return (...args) => f(game, ...args);
};
const optionsOf = (game, v, ctx) => (v.options ? pyList(fn(game, v.options)(ctx)) : []);

export function codeLines(game, design, ctx) {
    const schema = varsOf(game);
    const group = g => schema.filter(v => v.group === g);
    const settings = group("settings"), points = group("points"), strings = group("strings"), lists = group("lists");
    const lines = [`# ${pyStr(ctx.title)} as Python code. Each line makes a variable:`, "#     name: type = value", ""];
    const ints = settings.concat(points);
    if (ints.length) {
        lines.push("# INTEGER VARIABLES (whole numbers)");
        for (const v of ints) {
            const value = getVar(v, design);
            if (value === null) continue;
            const x = num(value);
            if (!Number.isFinite(x)) throw new PyError(Number.isNaN(x) ? "ValueError" : "OverflowError", "int()");
            const kind = x === Math.trunc(x) ? "int" : "float";
            lines.push(...comment(kind, {name: v.name, value: formatG(value), note: v.note || "a whole number"}));
            lines.push(`${v.name}: ${kind} = ${formatG(value)}`);
        }
        if (points.length && ctx.points_total !== null && ctx.points_total !== undefined) {
            let used = 0, float = false;
            for (const v of points) {
                const x = getVar(v, design);
                if (!pyTruthy(x)) continue;
                used += num(x);
                if (x instanceof PyFloat || !Number.isInteger(num(x))) float = true;
            }
            lines.push(`# points used: ${float ? floatRepr(used) : intStr(used)} of ${pyStr(ctx.points_total)}`);
        }
        lines.push("");
    }
    if (strings.length) {
        lines.push("# STRING VARIABLES (text in quotes)");
        for (const v of strings) {
            const value = getVar(v, design);
            if (value === null && v.optional) continue;
            const text = jsonStr(isStr(value) ? value : pyStr(value));
            lines.push(...(v.note ? comment("str", {name: v.name, value: text, note: v.note})
                : comment("str_plain", {name: v.name, value: text})));
            lines.push(`${v.name}: str = ${text}`);
        }
        lines.push("");
    }
    if (lists.length) {
        lines.push("# VARIABLE LISTS (values in order, in square brackets)");
        for (const v of lists) {
            const value = getVar(v, design);
            if (value === null && v.optional) continue;
            if (v.kind === "rgb") {
                const c = pyList(pyTruthy(value) ? value : [0, 0, 0]);
                lines.push(...comment("rgb", {name: v.name, r: c[0], g: c[1], b: c[2], note: v.note || "each 0 to 255"}));
                lines.push(`${v.name}: list = [${pyStr(c[0])}, ${pyStr(c[1])}, ${pyStr(c[2])}]`);
            } else if (v.kind === "choice") {
                const options = optionsOf(game, v, ctx);
                lines.push(...comment("options", {list: v.list_name, note: v.list_note || "the choices"}));
                lines.push(`${v.list_name}: list = ${jsonDumps(options)}`);
                const i = options.findIndex(o => pyEq(value, o));
                if (i >= 0) {
                    lines.push(...comment("choice", {i, item: jsonDumps(value), list: v.list_name, name: v.name}));
                    lines.push(`${v.name}: str = ${v.list_name}[${i}]`);
                } else {
                    const text = jsonStr(isStr(value) ? value : pyStr(value));
                    lines.push(...comment("choice_other", {name: v.name, value: text}));
                    lines.push(`${v.name}: str = ${text}`);
                }
            } else if (v.kind === "words") {
                lines.push(...(v.note ? comment("list", {name: v.name, note: v.note}) : comment("list_plain", {name: v.name})));
                lines.push(`${v.name}: list = ${jsonDumps(pyList(pyTruthy(value) ? value : []))}`);
            } else {
                lines.push(...(v.note ? comment("list", {name: v.name, note: v.note}) : comment("list_plain", {name: v.name})));
                lines.push(`${v.name}: list = ${jsonDumps(value)}`);
            }
        }
    }
    while (lines.length && lines[lines.length - 1] === "") lines.pop();
    return lines;
}

// ---------- reading the code: Python's tokenizer (3.12), as much of it as the code can reach ----------

export class PySyntaxError extends Error {
    constructor(lineno, msg, fromTokenizer = false) { super(msg); this.lineno = lineno; this.msg = msg; this.fromTokenizer = fromTokenizer; }
}

const KEYWORDS = new Set(["False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda",
    "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"]);
const SOFT_KEYWORDS = new Set(["_", "case", "match", "type"]);
const TWO = new Set(["!=", "%=", "&=", "**", "*=", "+=", "-=", "->", "//", "/=", ":=", "<<", "<=", "<>", "==", ">=",
    ">>", "@=", "^=", "|="]);
const THREE = new Set(["**=", "//=", "<<=", ">>="]);
const ID_START = /[\p{XID_Start}_]/u, ID_CONTINUE = /\p{XID_Continue}/u;
const isDigit = c => c !== undefined && c >= "0" && c <= "9";
const isHex = c => c !== undefined && /[0-9a-fA-F]/.test(c);
const isIdStart = c => c !== undefined && (/[a-zA-Z_]/.test(c) || c.codePointAt(0) >= 128);
const isIdChar = c => c !== undefined && (/[a-zA-Z0-9_]/.test(c) || c.codePointAt(0) >= 128);
const hex4 = n => n.toString(16).toUpperCase().padStart(4, "0");

class Tokenizer {
    constructor(src) {
        this.cs = cp(src);
        this.pos = 0;
        this.line = 1;
        this.level = 0;
        this.parens = [];
        this.atbol = true;
        this.indents = [[0, 0]];  // the indentation of each open block: [columns, columns with a tab as one]
        this.pendin = 0;          // INDENT (+) or DEDENT (-) tokens still to give
        this.fmodes = [];         // the f-strings being read, innermost last (Python's tokenizer modes)
        this.stop = null;  // the error (or the end) the tokenizer stopped at
        this.lines = Math.max(1, src.split("\n").length - (src.endsWith("\n") ? 1 : 0));
    }

    eofLine() { return this.lines; }  // (at the end, Python's tokenizer is still on the last line)

    hard(msg, line = this.line) {  // (fstr: inside an f-string, where Python lets an earlier error stand)
        return (this.stop = {type: "ERROR", hard: true, msg, line, fstr: this.fmodes.length > 0});
    }

    soft(kind, line) { return (this.stop = {type: "ERROR", hard: false, kind, line}); }

    tok(type, start, extra = {}) {
        return {type, str: this.cs.slice(start, this.pos).join(""), line: this.startLine, level: this.level, start,
                end: this.pos, ...extra};
    }

    next() {
        if (this.stop) return this.stop;
        const fm = this.fmodes[this.fmodes.length - 1];
        if (fm && fm.kind === "fstring") return this.fstringNext(fm);
        const cs = this.cs;
        let blankline = false;
        for (;;) {
            if (this.atbol) {  // a line's indentation (every line has been stripped, but a \r inside one starts another)
                this.atbol = false;
                let col = 0, alt = 0, contCol = 0;
                for (;;) {
                    const c = cs[this.pos];
                    if (c === " ") { col++; alt++; this.pos++; }
                    else if (c === "\t") { col = (Math.floor(col / 8) + 1) * 8; alt++; this.pos++; }
                    else if (c === "\x0c") { col = alt = 0; this.pos++; }
                    else if (c === "\\") {
                        contCol = contCol || col;
                        if (cs[this.pos + 1] !== "\n") return this.soft("linecont", this.line);
                        this.pos += 2;
                        this.line++;
                        if (this.pos >= cs.length) return this.soft("eof", this.line - 1);
                    } else break;
                }
                const c = cs[this.pos];
                blankline = c === "#" || c === "\n";
                if (!blankline && this.level === 0) {
                    if (contCol) col = alt = contCol;
                    const [top, atop] = this.indents[this.indents.length - 1];
                    if (col === top) {
                        if (alt !== atop) return this.soft("tabspace", this.line);
                    } else if (col > top) {
                        if (this.indents.length >= 100) return this.soft("toodeep", this.line);
                        if (alt <= atop) return this.soft("tabspace", this.line);
                        this.pendin++;
                        this.indents.push([col, alt]);
                    } else {
                        while (this.indents.length > 1 && col < this.indents[this.indents.length - 1][0]) {
                            this.pendin--;
                            this.indents.pop();
                        }
                        const [now, anow] = this.indents[this.indents.length - 1];
                        if (col !== now) return this.soft("dedent", this.line);
                        if (alt !== anow) return this.soft("tabspace", this.line);
                    }
                }
            }
            if (this.pendin) {
                const type = this.pendin < 0 ? "DEDENT" : "INDENT";
                this.pendin += this.pendin < 0 ? 1 : -1;
                return {type, str: "", line: this.line, level: this.level};
            }
            while (cs[this.pos] === " " || cs[this.pos] === "\t" || cs[this.pos] === "\x0c") this.pos++;
            const start = this.pos;
            this.startLine = this.line;
            let c = cs[this.pos];
            if (c === "#") {
                while (this.pos < cs.length && cs[this.pos] !== "\n") this.pos++;
                c = cs[this.pos];
            }
            if (c === undefined) {
                if (this.level > 0) return this.soft("eof", this.eofLine());
                return (this.stop = {type: "ENDMARKER", str: "", line: this.eofLine(), level: 0});
            }
            if (isIdStart(c)) return this.name(start);
            if (c === "\n") {
                this.pos++;
                this.line++;
                this.atbol = true;
                if (blankline || this.level > 0) continue;
                return {type: "NEWLINE", str: "\n", line: this.startLine, level: 0};
            }
            if (c === ".") {
                if (isDigit(cs[this.pos + 1])) return this.number(start);
                if (cs[this.pos + 1] === "." && cs[this.pos + 2] === ".") { this.pos += 3; return this.tok("OP", start); }
                this.pos++;
                return this.tok("OP", start);
            }
            if (isDigit(c)) return this.number(start);
            if (c === '"' || c === "'") return this.string(start, start);
            if (c === "\\") {
                if (cs[this.pos + 1] !== "\n") return this.soft("linecont", this.line);
                this.pos += 2;
                this.line++;
                if (this.pos >= cs.length) return this.soft("eof", this.line - 1);
                continue;
            }
            if (fm && fm.exprStart >= 0 && c === ":" && fm.depth - 1 === fm.exprStart) {
                fm.kind = "fstring";  // (a replacement field's ':' : its format spec follows)
                fm.inSpec = true;
                this.pos++;
                return this.tok("OP", start);
            }
            const two = c + (cs[this.pos + 1] || ""), three = two + (cs[this.pos + 2] || "");
            if (TWO.has(two)) {
                this.pos += THREE.has(three) ? 3 : 2;
                return this.tok("OP", start);
            }
            if ("([{".includes(c)) {
                if (this.level >= 200) return this.hard("too many nested parentheses");
                this.parens.push({ch: c, line: this.line});
                this.level++;
                if (fm) fm.depth++;
                this.pos++;
                return this.tok("OP", start);
            }
            if (")]}".includes(c)) {
                if (fm && !fm.depth && c === "}") return this.hard("f-string: single '}' is not allowed");
                if (!this.level) return this.hard(`unmatched '${c}'`);
                this.level--;
                const open = this.parens.pop();
                if ((open.ch === "(" && c !== ")") || (open.ch === "[" && c !== "]") || (open.ch === "{" && c !== "}")) {
                    if (fm && open.ch === "{" && fm.depth - 1 === fm.exprStart) return this.hard(`f-string: unmatched '${c}'`);
                    return this.hard(open.line !== this.line
                        ? `closing parenthesis '${c}' does not match opening parenthesis '${open.ch}' on line ${open.line}`
                        : `closing parenthesis '${c}' does not match opening parenthesis '${open.ch}'`);
                }
                if (fm) {
                    fm.depth--;
                    if (fm.depth < 0) return this.hard(`f-string: unmatched '${c}'`);
                    if (c === "}" && fm.depth === fm.exprStart) {  // (the field ends)
                        fm.exprStart--;
                        fm.kind = "fstring";
                        fm.inSpec = false;
                    }
                }
                this.pos++;
                return this.tok("OP", start);
            }
            if (!isPrintable(c)) return this.hard(`invalid non-printable character U+${hex4(c.codePointAt(0))}`);
            this.pos++;
            return this.tok("OP", start);  // (any other mark: a token nothing in the grammar takes)
        }
    }

    name(start) {
        const cs = this.cs;
        let p = start, b = false, r = false, u = false, f = false;
        for (;;) {  // a string's prefix: b, r, u, f, br, rb, fr, rf
            const c = cs[p];
            if (!(b || u || f) && (c === "b" || c === "B")) b = true;
            else if (!(b || u || r || f) && (c === "u" || c === "U")) u = true;
            else if (!(r || u) && (c === "r" || c === "R")) r = true;
            else if (!(f || b || u) && (c === "f" || c === "F")) f = true;
            else break;
            p++;
            if (cs[p] === '"' || cs[p] === "'") return f ? this.fstringStart(start, p) : this.string(start, p);
        }
        p = start;
        let nonascii = false;
        while (isIdChar(cs[p])) { if (cs[p].codePointAt(0) >= 128) nonascii = true; p++; }
        this.pos = p;
        if (nonascii) {  // a letter Python doesn't take in a name
            const s = cs.slice(start, p);
            let bad = ID_START.test(s[0]) ? s.findIndex((c, i) => i > 0 && !ID_CONTINUE.test(c)) : 0;
            if (bad >= 0) {
                const ch = s[bad], n = ch.codePointAt(0);
                return this.hard(isPrintable(ch) ? `invalid character '${ch}' (U+${hex4(n)})`
                    : `invalid non-printable character U+${hex4(n)}`);
            }
        }
        return this.tok("NAME", start);
    }

    endOfNumber(c, kind) {  // a number straight into a letter: an error, unless the letters are a keyword
        const cs = this.cs, at = this.pos;
        const ahead = word => {
            for (let i = 0; i < word.length; i++) if (cs[at + 1 + i] !== word[i]) return false;
            return !isIdChar(cs[at + 1 + word.length]);
        };
        let r = false;
        if (c === "a") r = ahead("nd");
        else if (c === "e") r = ahead("lse");
        else if (c === "f") r = ahead("or");
        else if (c === "i") r = ["f", "n", "s"].includes(cs[at + 1]);
        else if (c === "o") r = ahead("r");
        else if (c === "n") r = ahead("ot");
        if (r) return true;  // (Python warns, and reads on)
        if (c !== undefined && c.codePointAt(0) < 128 && isIdChar(c)) { this.hard(`invalid ${kind} literal`); return false; }
        return true;
    }

    decimalTail() {  // digits, with single underscores between them
        const cs = this.cs;
        for (;;) {
            while (isDigit(cs[this.pos])) this.pos++;
            if (cs[this.pos] !== "_") return true;
            this.pos++;
            if (!isDigit(cs[this.pos])) { this.hard("invalid decimal literal"); return false; }
        }
    }

    number(start) {
        const cs = this.cs;
        const done = () => this.tok("NUMBER", start);
        let c = cs[this.pos];
        if (c === "0" && cs[this.pos + 1] !== ".") {
            this.pos++;
            c = cs[this.pos];
            const based = (letters, ok, kind) => {
                this.pos++;
                for (;;) {
                    if (cs[this.pos] === "_") this.pos++;
                    if (!ok(cs[this.pos])) {
                        if (kind !== "hexadecimal" && isDigit(cs[this.pos])) return this.hard(`invalid digit '${cs[this.pos]}' in ${kind} literal`);
                        return this.hard(`invalid ${kind} literal`);
                    }
                    while (ok(cs[this.pos])) this.pos++;
                    if (cs[this.pos] !== "_") break;
                }
                if (kind !== "hexadecimal" && isDigit(cs[this.pos])) return this.hard(`invalid digit '${cs[this.pos]}' in ${kind} literal`);
                if (!this.endOfNumber(cs[this.pos], kind)) return this.stop;
                return done();
            };
            if (c === "x" || c === "X") return based("x", isHex, "hexadecimal");
            if (c === "o" || c === "O") return based("o", ch => ch !== undefined && ch >= "0" && ch <= "7", "octal");
            if (c === "b" || c === "B") return based("b", ch => ch === "0" || ch === "1", "binary");
            let nonzero = false;
            for (;;) {  // 0, 00, 0_0: zeros (a leading zero before other digits was C's octal: refused)
                if (cs[this.pos] === "_") {
                    this.pos++;
                    if (!isDigit(cs[this.pos])) return this.hard("invalid decimal literal");
                }
                if (cs[this.pos] !== "0") break;
                this.pos++;
            }
            if (isDigit(cs[this.pos])) {
                nonzero = true;
                if (!this.decimalTail()) return this.stop;
            }
            c = cs[this.pos];
            if (c === ".") { this.pos++; return this.fraction(start); }
            if (c === "e" || c === "E") return this.exponent(start);
            if (c === "j" || c === "J") return this.imaginary(start);
            if (nonzero) {
                return this.hard("leading zeros in decimal integer literals are not permitted; use an 0o prefix for octal integers");
            }
            if (!this.endOfNumber(c, "decimal")) return this.stop;
            return done();
        }
        if (c === ".") { this.pos++; return this.fraction(start); }
        if (!this.decimalTail()) return this.stop;
        c = cs[this.pos];
        if (c === ".") { this.pos++; return this.fraction(start); }
        if (c === "e" || c === "E") return this.exponent(start);
        if (c === "j" || c === "J") return this.imaginary(start);
        if (!this.endOfNumber(c, "decimal")) return this.stop;
        return done();
    }

    fraction(start) {
        if (isDigit(this.cs[this.pos]) && !this.decimalTail()) return this.stop;
        const c = this.cs[this.pos];
        if (c === "e" || c === "E") return this.exponent(start);
        if (c === "j" || c === "J") return this.imaginary(start);
        if (!this.endOfNumber(c, "decimal")) return this.stop;
        return this.tok("NUMBER", start);
    }

    exponent(start) {
        const cs = this.cs, e = this.pos;
        this.pos++;
        let c = cs[this.pos];
        if (c === "+" || c === "-") {
            this.pos++;
            if (!isDigit(cs[this.pos])) return this.hard("invalid decimal literal");
        } else if (!isDigit(c)) {
            this.pos = e;  // ("1e" and then not a number: the e is the next word, if it is a keyword)
            if (!this.endOfNumber("e", "decimal")) return this.stop;
            return this.tok("NUMBER", start);
        }
        if (!this.decimalTail()) return this.stop;
        c = cs[this.pos];
        if (c === "j" || c === "J") return this.imaginary(start);
        if (!this.endOfNumber(c, "decimal")) return this.stop;
        return this.tok("NUMBER", start);
    }

    imaginary(start) {
        this.pos++;
        if (!this.endOfNumber(this.cs[this.pos], "imaginary")) return this.stop;
        return this.tok("NUMBER", start);
    }

    fstringStart(start, q) {  // f"...": its start, then its parts in the f-string mode (fstringNext)
        const cs = this.cs, quote = cs[q];
        let size = 1, p = q + 1;
        if (cs[p] === quote && cs[p + 1] === quote) { size = 3; p = q + 3; }
        if (this.fmodes.length + 1 >= 150) return this.hard("too many nested f-strings");
        const prefix = cs.slice(start, q).join("").toLowerCase();
        this.fmodes.push({kind: "fstring", quote, size, raw: prefix.includes("r"), depth: 0, exprStart: -1, inSpec: false,
                          line: this.line});
        this.pos = p;
        return this.tok("FSTRING_START", start);
    }

    fstringNext(fm) {  // Python's tok_get_fstring_mode: the text between replacement fields, and the end
        const cs = this.cs, start = this.pos;
        this.startLine = this.line;
        const middle = (p, text = p) => {  // (text: where the token's text ends: {{ is one { of text)
            this.pos = text;
            const t = this.tok("FSTRING_MIDDLE", start);
            this.pos = p;
            return t;
        };
        if (cs[this.pos] === "{" && cs[this.pos + 1] !== "{") {  // a field straight away: the normal mode reads it
            fm.exprStart++;
            if (fm.exprStart >= 3) return this.hard("f-string: expressions nested too deeply");
            fm.kind = "regular";
            return this.next();
        }
        let k = 0;
        while (k < fm.size && cs[this.pos + k] === fm.quote) k++;
        if (k === fm.size) {
            this.pos += fm.size;
            const t = this.tok("FSTRING_END", start);
            this.fmodes.pop();
            return t;
        }
        const inSpec = fm.inSpec && fm.exprStart >= 0;
        let p = this.pos, endq = 0, unicodeEscape = false;
        while (endq !== fm.size) {
            const c = cs[p];
            if (c === undefined || (fm.size === 1 && c === "\n")) {
                if (inSpec && c === "\n") { fm.kind = "regular"; fm.inSpec = false; return middle(p); }
                const at = c === undefined ? this.eofLine() : this.line;
                return this.hard(fm.size === 3 ? `unterminated triple-quoted f-string literal (detected at line ${at})`
                    : `unterminated f-string literal (detected at line ${at})`, fm.line);
            }
            p++;
            if (c === "\n") this.line++;
            if (c === fm.quote) { endq++; continue; }
            endq = 0;
            if (c === "{") {
                if (cs[p] !== "{" || inSpec) {
                    fm.exprStart++;
                    if (fm.exprStart >= 3) return this.hard("f-string: expressions nested too deeply");
                    fm.kind = "regular";
                    fm.inSpec = false;
                    return middle(p - 1);
                }
                return middle(p + 1, p);  // ({{ : one { of text)
            }
            if (c === "}") {
                if (unicodeEscape) return middle(p);
                if (cs[p] === "}" && !inSpec && fm.depth === 0) return middle(p + 1, p);
                fm.kind = "regular";
                return middle(p - 1);
            }
            if (c === "\\") {
                const peek = cs[p];
                if (peek === "{" || peek === "}") continue;
                if (!fm.raw && peek === "N") {
                    p++;
                    if (cs[p] === "{") { unicodeEscape = true; p++; }
                } else if (peek !== undefined) {
                    p++;
                    if (peek === "\n") this.line++;
                }
            }
        }
        return middle(p - fm.size);  // (the closing quotes: the next token)
    }

    string(start, q) {  // a string from its prefix (start) and its first quote (q)
        const cs = this.cs, quote = cs[q], first = this.line;
        let p = q + 1, size = 1, end = 0;
        if (cs[p] === quote) {
            if (cs[p + 1] === quote) { size = 3; p += 2; } else { end = 1; p += 1; }
        }
        const body = p;
        while (end !== size) {
            const c = cs[p];
            if (c === undefined || (size === 1 && c === "\n")) {
                const at = c === undefined ? this.eofLine() : this.line;
                const fm = this.fmodes[this.fmodes.length - 1];  // (a string in an f-string's field, with its quotes)
                if (fm && fm.quote === quote && fm.size === size) return this.hard("f-string: expecting '}'", first);
                return this.hard(size === 3 ? `unterminated triple-quoted string literal (detected at line ${at})`
                    : `unterminated string literal (detected at line ${at})`, first);
            }
            p++;
            if (c === "\n") this.line++;
            if (c === quote) end++;
            else {
                end = 0;
                if (c === "\\" && cs[p] !== undefined) { if (cs[p] === "\n") this.line++; p++; }
            }
        }
        this.pos = p;
        return {type: "STRING", str: cs.slice(start, p).join(""), line: first, level: this.level,
                prefix: cs.slice(start, q).join("").toLowerCase(), body: cs.slice(body, p - size)};
    }
}

// a string token's value (Python's string_parser.c): escapes, bytes, and the errors they can give
const SIMPLE_ESCAPES = {"\n": "", "\\": "\\", "'": "'", '"': '"', b: "\b", f: "\f", t: "\t", n: "\n", r: "\r", v: "\x0b", a: "\x07"};

function decodeStr(body) {
    // positions in Python's errors count each non-ASCII letter as 10 (it is rewritten as \UXXXXXXXX first)
    const width = [];
    for (let i = 0; i < body.length; i++) {
        const big = body[i].codePointAt(0) >= 128;
        width.push(big ? 10 : body[i] === "\\" && body[i + 1] !== undefined && body[i + 1].codePointAt(0) >= 128 ? 6 : 1);
    }
    const posOf = i => width.slice(0, i).reduce((a, b) => a + b, 0);
    const out = [], push = ch => { for (const c of ch) out.push(c.codePointAt(0)); };
    for (let i = 0; i < body.length;) {
        const c = body[i];
        if (c !== "\\") { push(c); i++; continue; }
        const e = body[i + 1];
        if (e === undefined) { push("\\"); i++; continue; }
        if (e.codePointAt(0) >= 128) { push("\\" + e); i += 2; continue; }
        if (e in SIMPLE_ESCAPES) { push(SIMPLE_ESCAPES[e]); i += 2; continue; }
        if (e >= "0" && e <= "7") {
            let j = i + 1, v = 0;
            while (j < i + 4 && body[j] >= "0" && body[j] <= "7") { v = v * 8 + Number(body[j]); j++; }
            out.push(v);
            i = j;
            continue;
        }
        const fail = (endIdx, why) => {
            throw new PySyntaxError(null, `(unicode error) 'unicodeescape' codec can't decode bytes in position ${posOf(i)}-${posOf(endIdx) - 1}: ${why}`);
        };
        if (e === "x" || e === "u" || e === "U") {
            const count = e === "x" ? 2 : e === "u" ? 4 : 8;
            const why = e === "x" ? "truncated \\xXX escape" : e === "u" ? "truncated \\uXXXX escape" : "truncated \\UXXXXXXXX escape";
            let j = i + 2, v = 0;
            for (let k = 0; k < count; k++, j++) {
                if (!isHex(body[j])) fail(j, why);
                v = v * 16 + parseInt(body[j], 16);
            }
            if (v > 0x10ffff) fail(j, "illegal Unicode character");
            out.push(v);
            i = j;
            continue;
        }
        if (e === "N") {  // \N{NAME}: Python looks the name up in its Unicode database, which the browser hasn't got
            let j = i + 2;
            if (body[j] !== "{") fail(j, "malformed \\N character escape");
            j++;
            while (j < body.length && body[j] !== "}") j++;
            if (j >= body.length || j === i + 3) fail(j, "malformed \\N character escape");
            fail(j + 1, "unknown Unicode character name");
        }
        push("\\" + e);  // (an unknown escape keeps its backslash: Python only warns)
        i += 2;
    }
    return makeStr(out);
}

function decodeBytes(body) {
    const bytes = [];
    for (let i = 0; i < body.length;) {
        const c = body[i];
        if (c !== "\\") { bytes.push(c.charCodeAt(0)); i++; continue; }
        const e = body[i + 1];
        if (e === undefined) { bytes.push(0x5c); i++; continue; }
        if (e in SIMPLE_ESCAPES) { const s = SIMPLE_ESCAPES[e]; if (s) bytes.push(s.charCodeAt(0)); i += 2; continue; }
        if (e >= "0" && e <= "7") {
            let j = i + 1, v = 0;
            while (j < i + 4 && body[j] >= "0" && body[j] <= "7") { v = v * 8 + Number(body[j]); j++; }
            bytes.push(v & 0xff);
            i = j;
            continue;
        }
        if (e === "x") {
            if (isHex(body[i + 2]) && isHex(body[i + 3])) { bytes.push(parseInt(body[i + 2] + body[i + 3], 16)); i += 4; continue; }
            throw new PySyntaxError(null, `(value error) invalid \\x escape at position ${i}`);
        }
        bytes.push(0x5c, e.charCodeAt(0));
        i += 2;
    }
    return new PyBytes(bytes);
}

function numberValue(s) {
    s = s.replace(/_/g, "");
    const low = s.toLowerCase();
    if (low.endsWith("j")) return new PyComplex(0, Number(s.slice(0, -1)));
    if (/^0[xob]/.test(low)) { const b = BigInt(s); return b <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(b) : b; }
    if (/[.e]/.test(low)) return new PyFloat(Number(s));
    const b = BigInt(s);
    return b <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(b) : b;
}

// ---------- reading the code: Python's grammar (3.12's python.gram, the parts the code can reach) ----------
// A PEG parser, as Python's is: each rule tries its alternatives in order and remembers (memo) what it found at
// each place. The first pass reads; when it fails, a second pass with the "invalid_" rules on finds the error's
// better message, and the tokenizer reads to the end in case a broken string or bracket is the real mistake.

const N = (t, at, props = {}) => ({t, lineno: at.line !== undefined ? at.line : at.lineno, ...props});

function exprName(e) {
    switch (e.t) {
        case "Attribute": return "attribute";
        case "Subscript": return "subscript";
        case "Starred": return "starred";
        case "Name": return "name";
        case "List": return "list";
        case "Tuple": return "tuple";
        case "Lambda": return "lambda";
        case "Call": return "function call";
        case "BoolOp": case "BinOp": case "UnaryOp": return "expression";
        case "GeneratorExp": return "generator expression";
        case "Yield": case "YieldFrom": return "yield expression";
        case "Await": return "await expression";
        case "ListComp": return "list comprehension";
        case "SetComp": return "set comprehension";
        case "DictComp": return "dict comprehension";
        case "Dict": return "dict literal";
        case "Set": return "set display";
        case "JoinedStr": return "f-string expression";
        case "Constant":
            if (e.value === null) return "None";
            if (e.value === false) return "False";
            if (e.value === true) return "True";
            if (e.value === ELLIPSIS) return "ellipsis";
            return "literal";
        case "Compare": return "comparison";
        case "IfExp": return "conditional expression";
        case "NamedExpr": return "named expression";
        default: return e.t;
    }
}

function invalidTarget(e, kind) {  // the part of an expression that can't be assigned to (kind: star, for, del)
    if (!e) return null;
    switch (e.t) {
        case "List": case "Tuple":
            for (const x of e.elts) { const bad = invalidTarget(x, kind); if (bad) return bad; }
            return null;
        case "Starred":
            return kind === "del" ? e : invalidTarget(e.value, kind);
        case "Compare":
            if (kind === "for") return e.ops[0] === "in" ? invalidTarget(e.left, kind) : null;
            return e;
        case "Name": case "Subscript": case "Attribute":
            return null;
        default:
            return e;
    }
}

class Parser {
    constructor(src) {
        this.tz = new Tokenizer(src);
        this.toks = [];
        this.mark = 0;
        this.invalid = false;
        this.memos = new Map();
    }

    tokError(t) {
        if (t.hard) return new PySyntaxError(t.line, t.msg, true);
        if (t.kind === "linecont") return new PySyntaxError(t.line, "unexpected character after line continuation character", true);
        if (t.kind === "dedent") return new PySyntaxError(t.line, "unindent does not match any outer indentation level", true);
        if (t.kind === "tabspace") return new PySyntaxError(t.line, "inconsistent use of tabs and spaces in indentation", true);
        if (t.kind === "toodeep") return new PySyntaxError(t.line, "too many levels of indentation", true);
        if (this.tz.level > 0) return this.neverClosed(true);
        return new PySyntaxError(t.line, "unexpected EOF while parsing", true);
    }

    neverClosed(fromTokenizer) {
        const open = this.tz.parens[this.tz.level - 1];
        return new PySyntaxError(open.line, `'${open.ch}' was never closed`, fromTokenizer);
    }

    tk(k = 0) {
        const i = this.mark + k;
        while (this.toks.length <= i) {
            const t = this.tz.next();
            this.toks.push(t);
            if (t.type === "ERROR") throw this.tokError(t);
        }
        if (this.toks[i].type === "ERROR") throw this.tokError(this.toks[i]);
        return this.toks[i];
    }

    lastTok() { return this.toks[this.toks.length - 1]; }

    raise(at, msg) { throw new PySyntaxError(at.line !== undefined ? at.line : at.lineno, msg); }

    raiseHere(msg) { throw new PySyntaxError(this.lastTok().line, msg); }  // (Python's RAISE_SYNTAX_ERROR: the last token read)

    memo(name, f) {
        const key = name + "@" + this.mark;
        const m = this.memos.get(key);
        if (m) { this.mark = m.end; return m.res; }
        const start = this.mark;
        const res = f();
        if (!res) this.mark = start;
        this.memos.set(key, {res, end: this.mark});
        return res;
    }

    attempt(f) {  // an alternative: on failure the place goes back
        const m = this.mark;
        const r = f();
        if (!r) this.mark = m;
        return r;
    }

    look(f) { const m = this.mark; const r = f(); this.mark = m; return !!r; }  // a lookahead

    isOp(s) { const t = this.tk(); return t.type === "OP" && t.str === s; }
    op(s) { if (this.isOp(s)) { const t = this.tk(); this.mark++; return t; } return null; }
    isKw(s) { const t = this.tk(); return t.type === "NAME" && t.str === s; }
    kw(s) { if (this.isKw(s)) { const t = this.tk(); this.mark++; return t; } return null; }
    isType(type) { return this.tk().type === type; }
    type(type) { if (this.isType(type)) { const t = this.tk(); this.mark++; return t; } return null; }
    nameTok() {
        const t = this.tk();
        if (t.type === "NAME" && !KEYWORDS.has(t.str)) { this.mark++; return t; }
        return null;
    }
    nameNode(t) { return N("Name", t, {id: /^[\x00-\x7f]*$/.test(t.str) ? t.str : t.str.normalize("NFKC")}); }

    gather(f, sep) {  // ','.f+
        const first = this.attempt(f);
        if (!first) return null;
        const out = [first];
        for (;;) {
            const m = this.mark;
            if (this.op(sep)) {
                const x = this.attempt(f);
                if (x) { out.push(x); continue; }
            }
            this.mark = m;
            return out;
        }
    }

    // ----- statements -----
    file() {
        const body = this.statements() || [];
        if (!this.type("ENDMARKER")) return null;
        return body;
    }

    statements() {
        const out = [];
        for (;;) {
            const s = this.attempt(() => this.statement());
            if (!s) break;
            out.push(...s);
        }
        return out.length ? out : null;
    }

    statement() {
        const c = this.attempt(() => this.compound_stmt());
        if (c) return [c];
        return this.attempt(() => this.simple_stmts());
    }

    simple_stmts() {
        const m = this.mark;
        const a = this.simple_stmt();
        if (a && !this.isOp(";") && this.type("NEWLINE")) return [a];
        this.mark = m;
        const list = this.gather(() => this.simple_stmt(), ";");
        if (list) {
            this.op(";");
            if (this.type("NEWLINE")) return list;
        }
        this.mark = m;
        return null;
    }

    simple_stmt() {
        return this.memo("simple_stmt", () => {
            const t0 = this.tk();
            let r;
            if ((r = this.attempt(() => this.assignment()))) return r;
            if (this.isKw("type") && (r = this.attempt(() => this.type_alias()))) return r;
            if ((r = this.attempt(() => this.star_expressions()))) return N("Expr", t0, {value: r});
            if (this.isKw("return") && (r = this.attempt(() => this.return_stmt()))) return r;
            if ((this.isKw("import") || this.isKw("from")) && (r = this.attempt(() => this.import_stmt()))) return r;
            if (this.isKw("raise") && (r = this.attempt(() => this.raise_stmt()))) return r;
            if (this.kw("pass")) return N("Pass", t0);
            if (this.isKw("del") && (r = this.attempt(() => this.del_stmt()))) return r;
            if (this.isKw("yield") && (r = this.attempt(() => this.yield_expr()))) return N("Expr", t0, {value: r});
            if (this.isKw("assert") && (r = this.attempt(() => this.assert_stmt()))) return r;
            if (this.kw("break")) return N("Break", t0);
            if (this.kw("continue")) return N("Continue", t0);
            if (this.isKw("global") && (r = this.attempt(() => this.names_stmt("global")))) return r;
            if (this.isKw("nonlocal") && (r = this.attempt(() => this.names_stmt("nonlocal")))) return r;
            return null;
        });
    }

    annotated_rhs() { return this.attempt(() => this.yield_expr()) || this.attempt(() => this.star_expressions()); }

    optional_value() {  // ['=' annotated_rhs]
        return this.attempt(() => (this.op("=") ? this.annotated_rhs() : null));
    }

    assignment() {
        const m = this.mark, t0 = this.tk();
        let r = this.attempt(() => {  // NAME ':' expression ['=' annotated_rhs]
            const a = this.nameTok();
            if (!a || !this.op(":")) return null;
            const b = this.expression();
            if (!b) return null;
            return N("AnnAssign", t0, {target: this.nameNode(a), annotation: b, value: this.optional_value(), simple: 1});
        });
        if (r) return r;
        r = this.attempt(() => {  // ('(' single_target ')' | single_subscript_attribute_target) ':' expression [...]
            const a = this.attempt(() => {
                if (!this.op("(")) return null;
                const b = this.single_target();
                return b && this.op(")") ? b : null;
            }) || this.attempt(() => this.single_subscript_attribute_target());
            if (!a || !this.op(":")) return null;
            const b = this.expression();
            if (!b) return null;
            return N("AnnAssign", t0, {target: a, annotation: b, value: this.optional_value(), simple: 0});
        });
        if (r) return r;
        r = this.attempt(() => {  // (star_targets '=')+ (yield_expr | star_expressions) !'='
            const targets = [];
            for (;;) {
                const z = this.attempt(() => { const t = this.star_targets(); return t && this.op("=") ? t : null; });
                if (!z) break;
                targets.push(z);
            }
            if (!targets.length) return null;
            const b = this.attempt(() => this.yield_expr()) || this.attempt(() => this.star_expressions());
            if (!b || this.isOp("=")) return null;
            return N("Assign", t0, {targets, value: b});
        });
        if (r) return r;
        let cut = false;
        r = this.attempt(() => {  // single_target augassign ~ (yield_expr | star_expressions)
            const a = this.single_target();
            if (!a || !this.augassign()) return null;
            cut = true;
            const c = this.attempt(() => this.yield_expr()) || this.attempt(() => this.star_expressions());
            return c ? N("AugAssign", t0, {target: a, value: c}) : null;
        });
        if (r || cut) return r;
        if (this.invalid) { this.invalid_assignment(); this.mark = m; }
        return null;
    }

    augassign() {
        const t = this.tk();
        if (t.type === "OP" && ["+=", "-=", "*=", "@=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", "**=", "//="].includes(t.str)) {
            this.mark++;
            return t;
        }
        return null;
    }

    star_targets_eq_loop() { while (this.attempt(() => { const t = this.star_targets(); return t && this.op("=") ? t : null; })); }

    invalid_assignment() {
        const m = this.mark;
        let a = this.invalid_ann_assign_target();
        if (a && this.op(":") && this.expression()) this.raise(a, `only single target (not ${exprName(a)}) can be annotated`);
        this.mark = m;
        a = this.star_named_expression();
        if (a && this.op(",")) {
            while (this.attempt(() => this.star_named_expressions()));
            if (this.op(":") && this.expression()) this.raise(a, "only single target (not tuple) can be annotated");
        }
        this.mark = m;
        a = this.expression();
        if (a && this.op(":") && this.expression()) this.raise(a, "illegal target for annotation");
        this.mark = m;
        this.star_targets_eq_loop();
        a = this.star_expressions();
        if (a && this.op("=")) {
            const bad = invalidTarget(a, "star");
            if (bad) this.raise(bad, `cannot assign to ${exprName(bad)}`);
            this.mark = m;
            return null;
        }
        this.mark = m;
        this.star_targets_eq_loop();
        a = this.yield_expr();
        if (a && this.op("=")) this.raise(a, "assignment to yield expression not possible");
        this.mark = m;
        a = this.star_expressions();
        if (a && this.augassign() && (this.attempt(() => this.yield_expr()) || this.attempt(() => this.star_expressions()))) {
            this.raise(a, `'${exprName(a)}' is an illegal expression for augmented assignment`);
        }
        this.mark = m;
        return null;
    }

    invalid_ann_assign_target() {
        return this.attempt(() => this.list()) || this.attempt(() => this.tuple()) || this.attempt(() => {
            if (!this.op("(")) return null;
            const a = this.invalid_ann_assign_target();
            return a && this.op(")") ? a : null;
        });
    }

    type_alias() {
        const t0 = this.tk();
        if (!this.kw("type")) return null;
        const n = this.nameTok();
        if (!n) return null;
        this.attempt(() => this.type_params());
        if (!this.op("=")) return null;
        const b = this.expression();
        return b ? N("TypeAlias", t0) : null;
    }

    type_params() {  // '[' ','.type_param+ [','] ']'
        if (!this.op("[") || !this.gather(() => this.type_param(), ",")) return null;
        this.op(",");
        return this.op("]");
    }

    type_param() {
        return this.memo("type_param", () => {
            const r = this.attempt(() => {
                if (!this.nameTok()) return null;
                this.attempt(() => (this.op(":") ? this.expression() : null));
                return true;
            });
            if (r) return r;
            for (const star of ["*", "**"]) {
                this.attempt(() => {
                    if (!this.op(star) || !this.nameTok()) return null;
                    const colon = this.op(":");
                    const e = colon && this.expression();
                    if (e) {
                        const what = star === "*" ? "TypeVarTuple" : "ParamSpec";
                        this.raise(colon, e.t === "Tuple" ? `cannot use constraints with ${what}` : `cannot use bound with ${what}`);
                    }
                    return null;
                });
                const t = this.attempt(() => this.op(star) && this.nameTok());
                if (t) return t;
            }
            return null;
        });
    }

    return_stmt() {
        const t0 = this.tk();
        if (!this.kw("return")) return null;
        this.attempt(() => this.star_expressions());
        return N("Return", t0);
    }

    raise_stmt() {
        const t0 = this.tk();
        if (!this.kw("raise")) return null;
        this.attempt(() => {
            if (!this.expression()) return null;
            this.attempt(() => (this.kw("from") ? this.expression() : null));
            return true;
        });
        return N("Raise", t0);
    }

    names_stmt(word) {
        const t0 = this.tk();
        if (!this.kw(word)) return null;
        return this.gather(() => this.nameTok(), ",") ? N("Global", t0) : null;
    }

    assert_stmt() {
        const t0 = this.tk();
        if (!this.kw("assert") || !this.expression()) return null;
        this.attempt(() => (this.op(",") ? this.expression() : null));
        return N("Assert", t0);
    }

    del_stmt() {
        const t0 = this.tk();
        const r = this.attempt(() => {
            if (!this.kw("del") || !this.del_targets()) return null;
            return this.isOp(";") || this.isType("NEWLINE") ? N("Delete", t0) : null;
        });
        if (r) return r;
        if (this.invalid) {
            this.attempt(() => {
                if (!this.kw("del")) return null;
                const a = this.star_expressions();
                const bad = a && invalidTarget(a, "del");
                if (bad) this.raise(bad, `cannot delete ${exprName(bad)}`);
                return null;
            });
        }
        return null;
    }

    dotted_name() { return this.gather(() => this.nameTok(), "."); }

    import_stmt() {
        const t0 = this.tk();
        if (this.invalid) {
            this.attempt(() => {
                const a = this.kw("import");
                if (a && this.gather(() => this.dotted_name(), ",") && this.kw("from") && this.dotted_name()) {
                    this.raise(a, "Did you mean to use 'from ... import ...' instead?");
                }
                return null;
            });
        }
        const r = this.attempt(() => {  // import dotted_as_names
            if (!this.kw("import")) return null;
            return this.gather(() => this.attempt(() => {
                if (!this.dotted_name()) return null;
                this.attempt(() => (this.kw("as") ? this.nameTok() : null));
                return true;
            }), ",") ? N("Import", t0) : null;
        });
        if (r) return r;
        const dots = () => { let n = 0; while (this.op(".") || this.op("...")) n++; return n; };
        return this.attempt(() => {
            if (!this.kw("from")) return null;
            const d = dots();
            if (!this.attempt(() => this.dotted_name()) && !d) return null;
            if (!this.kw("import")) return null;
            return this.import_from_targets() ? N("ImportFrom", t0) : null;
        });
    }

    import_from_targets() {
        const as_names = () => this.gather(() => this.attempt(() => {
            if (!this.nameTok()) return null;
            this.attempt(() => (this.kw("as") ? this.nameTok() : null));
            return true;
        }), ",");
        let r = this.attempt(() => {
            if (!this.op("(") || !as_names()) return null;
            this.op(",");
            return this.op(")");
        });
        if (r) return r;
        r = this.attempt(() => (as_names() && !this.isOp(",") ? true : null));
        if (r) return r;
        if (this.op("*")) return true;
        if (this.invalid) {
            this.attempt(() => {
                if (as_names() && this.op(",") && this.type("NEWLINE")) this.raiseHere("trailing comma not allowed without surrounding parentheses");
                return null;
            });
        }
        return null;
    }

    // ----- compound statements (each line is stripped, so a block is only ever the rest of its own line) -----
    compound_stmt() {
        let r;
        if ((this.isKw("def") || this.isOp("@") || this.isKw("async")) && (r = this.attempt(() => this.function_def()))) return r;
        if (this.isKw("if") && (r = this.attempt(() => this.if_stmt()))) return r;
        if ((this.isKw("class") || this.isOp("@")) && (r = this.attempt(() => this.class_def()))) return r;
        if ((this.isKw("with") || this.isKw("async")) && (r = this.attempt(() => this.with_stmt()))) return r;
        if ((this.isKw("for") || this.isKw("async")) && (r = this.attempt(() => this.for_stmt()))) return r;
        if (this.isKw("try") && (r = this.attempt(() => this.try_stmt()))) return r;
        if (this.isKw("while") && (r = this.attempt(() => this.while_stmt()))) return r;
        return this.attempt(() => this.match_stmt());
    }

    block() {
        return this.memo("block", () => {
            const m = this.mark;
            if (this.type("NEWLINE") && this.type("INDENT")) {
                const s = this.statements();
                if (s && this.type("DEDENT")) return s;
            }
            this.mark = m;
            const s = this.attempt(() => this.simple_stmts());
            if (s) return s;
            if (this.invalid && this.type("NEWLINE") && !this.isType("INDENT")) this.raiseHere("expected an indented block");
            this.mark = m;
            return null;
        });
    }

    forced(s) {  // &&':' : the mark must be there
        const t = this.tk();
        if (t.type === "OP" && t.str === s) { this.mark++; return t; }
        this.raise(t, `expected '${s}'`);
    }

    indentError(what, line) { this.raiseHere(`expected an indented block after ${what} on line ${line}`); }

    noBlock() { return this.op(":") && this.type("NEWLINE") && !this.isType("INDENT"); }

    if_like(word) {  // if_stmt / elif_stmt
        const m = this.mark, t0 = this.tk();
        if (this.invalid) {
            this.attempt(() => {
                if (this.kw(word) && this.named_expression() && this.type("NEWLINE")) this.raiseHere("expected ':'");
                return null;
            });
            this.attempt(() => {
                const a = this.kw(word);
                const e = a && this.named_expression();
                if (e && this.noBlock()) this.indentError(`'${word}' statement`, word === "if" ? e.lineno : a.line);
                return null;
            });
        }
        this.mark = m;
        if (!this.kw(word) || !this.named_expression() || !this.op(":") || !this.block()) { this.mark = m; return null; }
        if (this.attempt(() => this.if_like("elif"))) return N("If", t0);
        this.attempt(() => this.else_block());
        return N("If", t0);
    }

    if_stmt() { return this.if_like("if"); }

    else_block() {
        if (this.invalid) {
            this.attempt(() => {
                const a = this.kw("else");
                if (a && this.noBlock()) this.indentError("'else' statement", a.line);
                return null;
            });
        }
        if (!this.kw("else")) return null;
        this.forced(":");
        return this.block();
    }

    while_stmt() {
        const m = this.mark, t0 = this.tk();
        if (this.invalid) {
            this.attempt(() => {
                if (this.kw("while") && this.named_expression() && this.type("NEWLINE")) this.raiseHere("expected ':'");
                return null;
            });
            this.attempt(() => {
                const a = this.kw("while");
                if (a && this.named_expression() && this.noBlock()) this.indentError("'while' statement", a.line);
                return null;
            });
        }
        this.mark = m;
        if (!this.kw("while") || !this.named_expression() || !this.op(":") || !this.block()) { this.mark = m; return null; }
        this.attempt(() => this.else_block());
        return N("While", t0);
    }

    for_stmt() {
        const m = this.mark, t0 = this.tk();
        if (this.invalid) {
            this.attempt(() => {
                this.kw("async");
                if (this.kw("for") && this.star_targets() && this.kw("in") && this.star_expressions() && this.type("NEWLINE")) this.raiseHere("expected ':'");
                return null;
            });
            this.attempt(() => {
                this.kw("async");
                const a = this.kw("for");
                if (a && this.star_targets() && this.kw("in") && this.star_expressions() && this.noBlock()) this.indentError("'for' statement", a.line);
                return null;
            });
        }
        this.mark = m;
        this.kw("async");
        let cut = false;
        const r = this.attempt(() => {
            if (!this.kw("for") || !this.star_targets() || !this.kw("in")) return null;
            cut = true;
            if (!this.star_expressions() || !this.op(":") || !this.block()) return null;
            this.attempt(() => this.else_block());
            return N("For", t0);
        });
        if (r || cut) return r;
        this.mark = m;
        if (this.invalid) this.attempt(() => this.invalid_for_target());
        return null;
    }

    with_stmt() {
        const m = this.mark, t0 = this.tk();
        const items = () => this.gather(() => this.attempt(() => {
            if (!this.expression()) return null;
            this.attempt(() => (this.kw("as") ? this.star_target() : null));
            return true;
        }), ",");
        const bracketed = () => this.attempt(() => {  // '(' ','.(expressions ['as' star_target])+ ','? ')'
            if (!this.op("(")) return null;
            const ok = this.gather(() => this.attempt(() => {
                if (!this.expressions()) return null;
                this.attempt(() => (this.kw("as") ? this.star_target() : null));
                return true;
            }), ",");
            if (!ok) return null;
            this.op(",");
            return this.op(")");
        });
        if (this.invalid) {
            this.attempt(() => {
                this.kw("async");
                const a = this.kw("with");
                if (a && items() && this.noBlock()) this.indentError("'with' statement", a.line);
                return null;
            });
            this.attempt(() => {
                this.kw("async");
                const a = this.kw("with");
                if (a && bracketed() && this.noBlock()) this.indentError("'with' statement", a.line);
                return null;
            });
        }
        this.mark = m;
        this.kw("async");
        const r = this.attempt(() => {
            if (!this.kw("with")) return null;
            const ok = this.attempt(() => {
                if (!this.op("(") || !this.gather(() => this.with_item(), ",")) return null;
                this.op(",");
                return this.op(")") && this.op(":");
            }) || this.attempt(() => this.gather(() => this.with_item(), ",") && this.op(":"));
            return ok && this.block() ? N("With", t0) : null;
        });
        if (r) return r;
        this.mark = m;
        if (this.invalid) {
            this.attempt(() => {
                this.kw("async");
                if (this.kw("with") && items() && this.type("NEWLINE")) this.raiseHere("expected ':'");
                return null;
            });
            this.attempt(() => {
                this.kw("async");
                if (this.kw("with") && bracketed() && this.type("NEWLINE")) this.raiseHere("expected ':'");
                return null;
            });
        }
        return null;
    }

    with_item() {
        return this.attempt(() => {
            if (!this.expression() || !this.kw("as") || !this.star_target()) return null;
            return this.isOp(",") || this.isOp(")") || this.isOp(":") ? true : null;
        }) || (this.invalid && this.attempt(() => {
            if (this.expression() && this.kw("as")) {
                const a = this.expression();
                if (a && (this.isOp(",") || this.isOp(")") || this.isOp(":"))) {
                    const bad = invalidTarget(a, "star");
                    if (bad) this.raise(bad, `cannot assign to ${exprName(bad)}`);
                }
            }
            return null;
        })) || this.attempt(() => this.expression());
    }

    try_stmt() {
        const m = this.mark, t0 = this.tk();
        if (this.invalid) {
            this.attempt(() => {
                const a = this.kw("try");
                if (a && this.noBlock()) this.indentError("'try' statement", a.line);
                return null;
            });
            this.attempt(() => {
                if (this.kw("try") && this.op(":") && this.block() && !this.isKw("except") && !this.isKw("finally")) {
                    this.raiseHere("expected 'except' or 'finally' block");
                }
                return null;
            });
        }
        this.mark = m;
        if (!this.kw("try")) return null;
        this.forced(":");
        if (!this.block()) { this.mark = m; return null; }
        if (this.attempt(() => this.finally_block())) return N("Try", t0);
        let n = 0;
        while (this.attempt(() => this.except_block())) n++;
        if (!n) { this.mark = m; return null; }
        this.attempt(() => this.else_block());
        this.attempt(() => this.finally_block());
        return N("Try", t0);
    }

    except_block() {
        if (this.invalid) {
            this.attempt(() => {
                const a = this.kw("except");
                if (a && this.expression()) {
                    this.attempt(() => (this.kw("as") ? this.nameTok() : null));
                    if (this.noBlock()) this.indentError("'except' statement", a.line);
                }
                return null;
            });
            this.attempt(() => {
                const a = this.kw("except");
                if (a && this.noBlock()) this.indentError("'except' statement", a.line);
                return null;
            });
        }
        const r = this.attempt(() => {
            if (!this.kw("except") || !this.expression()) return null;
            this.attempt(() => (this.kw("as") ? this.nameTok() : null));
            return this.op(":") && this.block();
        }) || this.attempt(() => this.kw("except") && this.op(":") && this.block());
        if (r) return r;
        if (this.invalid) {
            this.attempt(() => {
                if (!this.kw("except")) return null;
                this.op("*");
                const a = this.expression();
                if (a && this.op(",") && this.expressions()) {
                    this.attempt(() => (this.kw("as") ? this.nameTok() : null));
                    if (this.op(":")) this.raise(a, "multiple exception types must be parenthesized");
                }
                return null;
            });
            this.attempt(() => {
                if (this.kw("except") && (this.op("*"), true) && this.expression()) {
                    this.attempt(() => (this.kw("as") ? this.nameTok() : null));
                    if (this.type("NEWLINE")) this.raiseHere("expected ':'");
                }
                return null;
            });
            this.attempt(() => {
                if (this.kw("except") && this.type("NEWLINE")) this.raiseHere("expected ':'");
                return null;
            });
            this.attempt(() => {
                if (this.kw("except") && this.op("*") && (this.type("NEWLINE") || this.op(":"))) this.raiseHere("expected one or more exception types");
                return null;
            });
        }
        return null;
    }

    finally_block() {
        if (this.invalid) {
            this.attempt(() => {
                const a = this.kw("finally");
                if (a && this.noBlock()) this.indentError("'finally' statement", a.line);
                return null;
            });
        }
        if (!this.kw("finally")) return null;
        this.forced(":");
        return this.block();
    }

    // a function's parameters (lam false) or a lambda's (lam true): python.gram's params and lambda_params
    many(f, least = 0) {  // f*, f+
        let n = 0;
        while (this.attempt(f)) n++;
        return n >= least ? n || true : null;
    }

    p_param(lam) {  // NAME [annotation]
        const n = this.nameTok();
        if (!n) return null;
        if (!lam) this.attempt(() => (this.op(":") ? this.expression() : null));
        return n;
    }

    p_close(lam) { return this.isOp(lam ? ":" : ")"); }

    p_default() {  // '=' expression | invalid_default
        const r = this.attempt(() => (this.op("=") ? this.expression() : null));
        if (r) return r;
        if (this.invalid) {
            this.attempt(() => {
                const a = this.op("=");
                if (a && (this.isOp(")") || this.isOp(","))) this.raise(a, "expected default value expression");
                return null;
            });
        }
        return null;
    }

    p_end(lam) { return this.op(",") || this.p_close(lam); }  // ',' | &')'  (or &':' for a lambda)

    p_no_default(lam) { return this.attempt(() => this.p_param(lam) && this.p_end(lam)); }
    p_with_default(lam) { return this.attempt(() => this.p_param(lam) && this.p_default() && this.p_end(lam)); }
    p_maybe_default(lam) {
        return this.attempt(() => {
            if (!this.p_param(lam)) return null;
            this.attempt(() => this.p_default());
            return this.p_end(lam);
        });
    }

    p_star_annotation() {  // NAME ':' star_expression, then ',' or &')'
        return this.attempt(() => this.nameTok() && this.op(":") && this.star_expression() && this.p_end(false));
    }

    p_slash_no_default(lam) {
        return this.attempt(() => this.many(() => this.p_no_default(lam), 1) && this.op("/") && this.p_end(lam));
    }

    p_slash_with_default(lam) {
        return this.attempt(() => this.many(() => this.p_no_default(lam)) && this.many(() => this.p_with_default(lam), 1)
            && this.op("/") && this.p_end(lam));
    }

    p_kwds(lam) {
        if (this.invalid) {
            this.attempt(() => {
                if (!this.op("**") || !this.p_param(lam)) return null;
                const a = this.op("=");
                if (a) this.raise(a, "var-keyword argument cannot have default value");
                return null;
            });
            this.attempt(() => {
                if (!this.op("**") || !this.p_param(lam) || !this.op(",")) return null;
                const t = this.tk();
                if (this.attempt(() => this.p_param(lam))) this.raise(t, "arguments cannot follow var-keyword argument");
                if (t.type === "OP" && ["*", "**", "/"].includes(t.str)) this.raise(t, "arguments cannot follow var-keyword argument");
                return null;
            });
        }
        return this.attempt(() => this.op("**") && this.p_no_default(lam));
    }

    p_star_etc(lam) {
        if (this.invalid) {
            this.attempt(() => {  // a bare * with nothing named after it
                const a = this.op("*");
                if (!a) return null;
                const close = lam ? ":" : ")";
                if (this.isOp(close) || (this.op(",") && (this.isOp(close) || this.isOp("**")))) {
                    if (lam) this.raiseHere("named arguments must follow bare *");
                    this.raise(a, "named arguments must follow bare *");
                }
                return null;
            });
            this.attempt(() => {
                if (!this.op("*") || !this.p_param(lam)) return null;
                const a = this.op("=");
                if (a) this.raise(a, "var-positional argument cannot have default value");
                return null;
            });
            this.attempt(() => {
                if (!this.op("*") || !(this.p_no_default(lam) || this.op(","))) return null;
                this.many(() => this.p_maybe_default(lam));
                const a = this.op("*");
                if (a && (this.p_no_default(lam) || this.op(","))) this.raise(a, "* argument may appear only once");
                return null;
            });
        }
        return this.attempt(() => this.op("*") && this.p_no_default(lam) && this.many(() => this.p_maybe_default(lam))
                && (this.attempt(() => this.p_kwds(lam)), true))
            || (!lam && this.attempt(() => this.op("*") && this.p_star_annotation()
                && this.many(() => this.p_maybe_default(lam)) && (this.attempt(() => this.p_kwds(lam)), true)))
            || this.attempt(() => this.op("*") && this.op(",") && this.many(() => this.p_maybe_default(lam), 1)
                && (this.attempt(() => this.p_kwds(lam)), true))
            || this.attempt(() => this.p_kwds(lam));
    }

    params(lam = false) {
        if (this.invalid) this.attempt(() => this.invalid_parameters(lam));
        const star = () => (this.attempt(() => this.p_star_etc(lam)), true);
        return this.attempt(() => this.p_slash_no_default(lam) && this.many(() => this.p_no_default(lam))
                && this.many(() => this.p_with_default(lam)) && star())
            || this.attempt(() => this.p_slash_with_default(lam) && this.many(() => this.p_with_default(lam)) && star())
            || this.attempt(() => this.many(() => this.p_no_default(lam), 1) && this.many(() => this.p_with_default(lam)) && star())
            || this.attempt(() => this.many(() => this.p_with_default(lam), 1) && star())
            || this.attempt(() => this.p_star_etc(lam));
    }

    invalid_parameters(lam) {
        const m = this.mark;
        const slash = () => this.p_slash_no_default(lam) || this.p_slash_with_default(lam);
        let a = this.op("/");
        if (a && this.op(",")) this.raise(a, "at least one argument must precede /");
        this.mark = m;
        if (slash()) {
            this.many(() => this.p_maybe_default(lam));
            a = this.op("/");
            if (a) this.raise(a, "/ may appear only once");
        }
        this.mark = m;
        this.p_slash_no_default(lam);
        this.many(() => this.p_no_default(lam));
        if (this.p_slash_with_default(lam) || this.many(() => this.p_with_default(lam), 1)) {
            const t = this.tk();
            if (this.p_no_default(lam)) this.raise(t, "parameter without a default follows parameter with a default");
        }
        this.mark = m;
        this.many(() => this.p_no_default(lam));
        a = this.op("(");
        if (a) {
            const inside = lam ? this.gather(() => this.nameTok(), ",") : this.many(() => this.p_no_default(lam), 1);
            if (inside) {
                this.op(",");
                if (this.op(")")) this.raise(a, lam ? "Lambda expression parameters cannot be parenthesized" : "Function parameters cannot be parenthesized");
            }
        }
        this.mark = m;
        slash();
        this.many(() => this.p_maybe_default(lam));
        if (this.op("*") && (this.op(",") || this.p_no_default(lam))) {
            this.many(() => this.p_maybe_default(lam));
            a = this.op("/");
            if (a) this.raise(a, "/ must be ahead of *");
        }
        this.mark = m;
        if (this.many(() => this.p_maybe_default(lam), 1) && this.op("/")) {
            a = this.op("*");
            if (a) this.raise(a, "expected comma between / and *");
        }
        this.mark = m;
        return null;
    }

    function_def() {
        const m = this.mark, t0 = this.tk();
        while (this.attempt(() => this.op("@") && this.named_expression() && this.type("NEWLINE")));
        const at = this.tk();  // (a decorated function's line is its def's)
        if (this.invalid) {
            this.attempt(() => {
                this.kw("async");
                const a = this.kw("def");
                if (!a || !this.nameTok()) return null;
                this.attempt(() => this.type_params());
                if (!this.op("(")) return null;
                this.attempt(() => this.params());
                if (!this.op(")")) return null;
                this.attempt(() => (this.op("->") ? this.expression() : null));
                if (this.noBlock()) this.indentError("function definition", a.line);
                return null;
            });
        }
        this.kw("async");
        if (!this.kw("def") || !this.nameTok()) { this.mark = m; return null; }
        this.attempt(() => this.type_params());
        this.forced("(");
        this.attempt(() => this.params());
        if (!this.op(")")) { this.mark = m; return null; }
        this.attempt(() => (this.op("->") ? this.expression() : null));
        this.forced(":");
        if (!this.block()) { this.mark = m; return null; }
        return N("FunctionDef", at);
    }

    class_def() {
        const m = this.mark, t0 = this.tk();
        while (this.attempt(() => this.op("@") && this.named_expression() && this.type("NEWLINE")));
        const at = this.tk();
        const head = () => {
            const a = this.kw("class");
            if (!a || !this.nameTok()) return null;
            this.attempt(() => this.type_params());
            this.attempt(() => {
                if (!this.op("(")) return null;
                this.attempt(() => this.arguments());
                return this.op(")");
            });
            return a;
        };
        if (this.invalid) {
            const mm = this.mark;
            this.attempt(() => { if (head() && this.type("NEWLINE")) this.raiseHere("expected ':'"); return null; });
            this.attempt(() => { const a = head(); if (a && this.noBlock()) this.indentError("class definition", a.line); return null; });
            this.mark = mm;
        }
        if (!head() || !this.op(":") || !this.block()) { this.mark = m; return null; }
        return N("ClassDef", at);
    }

    match_stmt() {
        const t = this.tk();
        if (t.type !== "NAME" || t.str !== "match") return null;
        const subject = () => this.attempt(() => {
            const a = this.star_named_expression();
            if (!a || !this.op(",")) return null;
            this.attempt(() => this.star_named_expressions());
            return true;
        }) || this.attempt(() => this.named_expression());
        const m = this.mark;
        this.mark++;
        if (subject() && this.op(":") && this.type("NEWLINE") && this.type("INDENT")) {
            let n = 0;
            while (this.attempt(() => this.case_block())) n++;
            if (n && this.type("DEDENT")) return N("Match", t);
        }
        this.mark = m;
        if (this.invalid) {
            this.attempt(() => { this.mark++; if (subject() && this.type("NEWLINE")) this.raiseHere("expected ':'"); return null; });
            this.attempt(() => {
                this.mark++;
                if (subject() && this.noBlock()) this.indentError("'match' statement", t.line);
                return null;
            });
        }
        return null;
    }

    // ----- match statements' case blocks and patterns -----
    soft(word) { const t = this.tk(); if (t.type === "NAME" && t.str === word) { this.mark++; return t; } return null; }

    case_block() {
        const head = () => {
            const a = this.soft("case");
            if (!a || !this.patterns()) return null;
            this.attempt(() => this.kw("if") && this.named_expression());
            return a;
        };
        if (this.invalid) {
            this.attempt(() => { if (head() && this.type("NEWLINE")) this.raiseHere("expected ':'"); return null; });
            this.attempt(() => {
                const a = head();
                if (a && this.noBlock()) this.indentError("'case' statement", a.line);
                return null;
            });
        }
        return this.attempt(() => head() && this.op(":") && this.block());
    }

    patterns() { return this.attempt(() => this.open_sequence_pattern()) || this.attempt(() => this.pattern()); }

    pattern() { return this.attempt(() => this.as_pattern()) || this.attempt(() => this.or_pattern()); }

    as_pattern() {
        const r = this.attempt(() => this.or_pattern() && this.kw("as") && this.pattern_capture_target());
        if (r) return r;
        if (this.invalid) {
            this.attempt(() => {
                if (!this.or_pattern() || !this.kw("as")) return null;
                const a = this.soft("_");
                if (a) this.raise(a, "cannot use '_' as a target");
                const t = this.tk();
                if (!(t.type === "NAME" && !KEYWORDS.has(t.str))) {
                    const e = this.expression();
                    if (e) this.raise(e, "invalid pattern target");
                }
                return null;
            });
        }
        return null;
    }

    or_pattern() { return this.gather(() => this.closed_pattern(), "|"); }

    closed_pattern() {
        return this.memo("closed_pattern", () => this.attempt(() => this.literal_pattern())
            || this.attempt(() => this.pattern_capture_target()) || this.soft("_")
            || this.attempt(() => this.value_pattern()) || this.attempt(() => this.group_pattern())
            || this.attempt(() => this.sequence_pattern()) || this.attempt(() => this.mapping_pattern())
            || this.attempt(() => this.class_pattern()));
    }

    real_number() {
        const t = this.type("NUMBER");
        if (t && numberValue(t.str) instanceof PyComplex) this.raise(t, "real number required in complex literal");
        return t;
    }

    imaginary_number() {
        const t = this.type("NUMBER");
        if (t && !(numberValue(t.str) instanceof PyComplex)) this.raise(t, "imaginary number required in complex literal");
        return t;
    }

    literal_expr() {
        return this.attempt(() => {
            const n = this.attempt(() => this.type("NUMBER")) || this.attempt(() => this.op("-") && this.type("NUMBER"));
            return n && !this.isOp("+") && !this.isOp("-") ? n : null;
        }) || this.attempt(() => {
            if (!(this.real_number() || this.attempt(() => this.op("-") && this.real_number()))) return null;
            return (this.op("+") || this.op("-")) && this.imaginary_number();
        }) || (this.tk().type === "STRING" || this.tk().type === "FSTRING_START" ? this.attempt(() => this.strings()) : null)
            || this.kw("None") || this.kw("True") || this.kw("False");
    }

    literal_pattern() { return this.literal_expr(); }

    pattern_capture_target() {
        const t = this.tk();
        if (t.type === "NAME" && t.str === "_") return null;
        const n = this.nameTok();
        return n && !this.isOp(".") && !this.isOp("(") && !this.isOp("=") ? n : null;
    }

    attr() {  // name_or_attr '.' NAME
        const names = this.gather(() => this.nameTok(), ".");
        return names && names.length > 1 ? names : null;
    }

    name_or_attr() { return this.gather(() => this.nameTok(), "."); }

    value_pattern() { const a = this.attr(); return a && !this.isOp(".") && !this.isOp("(") && !this.isOp("=") ? a : null; }

    group_pattern() { return this.attempt(() => this.op("(") && this.pattern() && this.op(")")); }

    maybe_star_pattern() { return this.attempt(() => this.star_pattern()) || this.attempt(() => this.pattern()); }

    star_pattern() {
        return this.memo("star_pattern", () => this.attempt(() => this.op("*") && this.pattern_capture_target())
            || this.attempt(() => this.op("*") && this.soft("_")));
    }

    maybe_sequence_pattern() {
        const l = this.gather(() => this.maybe_star_pattern(), ",");
        if (l) this.op(",");
        return l;
    }

    open_sequence_pattern() {
        if (!this.maybe_star_pattern() || !this.op(",")) return null;
        this.attempt(() => this.maybe_sequence_pattern());
        return true;
    }

    sequence_pattern() {
        return this.attempt(() => {
            if (!this.op("[")) return null;
            this.attempt(() => this.maybe_sequence_pattern());
            return this.op("]");
        }) || this.attempt(() => {
            if (!this.op("(")) return null;
            this.attempt(() => this.open_sequence_pattern());
            return this.op(")");
        });
    }

    mapping_pattern() {
        const items = () => this.gather(() => this.attempt(() => {
            if (!(this.attempt(() => this.literal_expr()) || this.attempt(() => this.attr()))) return null;
            return this.op(":") && this.pattern();
        }), ",");
        const rest = () => this.attempt(() => this.op("**") && this.pattern_capture_target());
        return this.attempt(() => this.op("{") && this.op("}"))
            || this.attempt(() => { if (!this.op("{") || !rest()) return null; this.op(","); return this.op("}"); })
            || this.attempt(() => {
                if (!this.op("{") || !items() || !this.op(",") || !rest()) return null;
                this.op(",");
                return this.op("}");
            })
            || this.attempt(() => { if (!this.op("{") || !items()) return null; this.op(","); return this.op("}"); });
    }

    class_pattern() {
        const positional = () => this.gather(() => this.pattern(), ",");
        const keywords = () => this.gather(() => this.attempt(() => this.nameTok() && this.op("=") && this.pattern()), ",");
        const open = () => this.name_or_attr() && this.op("(");
        const r = this.attempt(() => open() && this.op(")"))
            || this.attempt(() => { if (!open() || !positional()) return null; this.op(","); return this.op(")"); })
            || this.attempt(() => { if (!open() || !keywords()) return null; this.op(","); return this.op(")"); })
            || this.attempt(() => {
                if (!open() || !positional() || !this.op(",") || !keywords()) return null;
                this.op(",");
                return this.op(")");
            });
        if (r) return r;
        if (this.invalid) {
            this.attempt(() => {
                if (!open()) return null;
                this.attempt(() => positional() && this.op(","));
                if (keywords() && this.op(",")) {
                    const t = this.tk();
                    if (positional()) this.raise(t, "positional patterns follow keyword patterns");
                }
                return null;
            });
        }
        return null;
    }

    // ----- expressions -----
    expressions() {
        const a = this.expression();
        if (!a) return null;
        while (this.attempt(() => (this.op(",") ? this.expression() : null)));
        this.op(",");
        return a;
    }

    expression() {
        return this.memo("expression", () => {
            if (this.invalid) {
                this.attempt(() => this.invalid_expression());
                this.attempt(() => this.invalid_legacy_expression());
            }
            return this.expression_body();
        });
    }

    expression_body() {
        const t0 = this.tk();
        const a = this.attempt(() => this.disjunction());
        if (a) {
            const r = this.attempt(() => {
                if (!this.kw("if")) return null;
                const b = this.disjunction();
                if (!b || !this.kw("else")) return null;
                const c = this.expression();
                return c ? N("IfExp", t0, {body: a, test: b, orelse: c}) : null;
            });
            return r || a;
        }
        return this.attempt(() => this.lambdef());
    }

    expression_without_invalid() {
        const saved = this.invalid;
        this.invalid = false;
        try {
            return this.attempt(() => this.expression_body());
        } finally {
            this.invalid = saved;
        }
    }

    invalid_expression() {
        const t0 = this.tk(), m0 = this.mark;
        let blocked = false;
        if (t0.type === "NAME" && !KEYWORDS.has(t0.str)) {
            if (this.tk(1).type === "STRING") blocked = true;
            if ([...SOFT_KEYWORDS].some(k => k.startsWith(t0.str))) blocked = true;  // (Python compares only the name's length)
        }
        if (!blocked) {
            const m = this.mark;
            const a = this.disjunction();
            if (a) {
                const b = this.expression_without_invalid();
                if (b) {
                    const legacy = a.t === "Name" && (a.id === "print" || a.id === "exec");
                    if (!legacy && this.toks[this.mark - 1].level !== 0) this.raise(a, "invalid syntax. Perhaps you forgot a comma?");
                    return null;  // (matched without an error: the rule stops here, as Python's does)
                }
            }
            this.mark = m;
        }
        const a = this.disjunction();
        if (a && this.kw("if")) {
            const b = this.disjunction();
            if (b && !this.isKw("else") && !this.isOp(":")) this.raise(a, "expected 'else' after 'if' expression");
        }
        this.mark = m0;
        const l = this.kw("lambda");
        if (l) {
            this.attempt(() => this.params(true));
            if (this.op(":") && this.isType("FSTRING_MIDDLE")) this.raise(l, "f-string: lambda expressions are not allowed without parentheses");
        }
        return null;
    }

    invalid_legacy_expression() {
        const a = this.nameTok();
        if (a && !this.isOp("(")) {
            const id = this.nameNode(a).id;
            if (this.star_expressions() && (id === "print" || id === "exec")) {
                this.raise(a, `Missing parentheses in call to '${id}'. Did you mean ${id}(...)?`);
            }
        }
        return null;
    }

    yield_expr() {
        const t0 = this.tk();
        if (!this.kw("yield")) return null;
        if (this.kw("from")) {
            const e = this.expression();
            return e ? N("YieldFrom", t0) : null;
        }
        this.attempt(() => this.star_expressions());
        return N("Yield", t0);
    }

    star_expressions() {
        const t0 = this.tk();
        const a = this.star_expression();
        if (!a) return null;
        const elts = [a];
        for (;;) {
            const c = this.attempt(() => (this.op(",") ? this.star_expression() : null));
            if (!c) break;
            elts.push(c);
        }
        if (elts.length > 1) { this.op(","); return N("Tuple", t0, {elts}); }
        if (this.op(",")) return N("Tuple", t0, {elts});
        return a;
    }

    star_expression() {
        return this.memo("star_expression", () => {
            const t0 = this.tk();
            const s = this.attempt(() => {
                if (!this.op("*")) return null;
                const v = this.bitwise_or();
                return v ? N("Starred", t0, {value: v}) : null;
            });
            return s || this.attempt(() => this.expression());
        });
    }

    star_named_expressions() {
        const list = this.gather(() => this.star_named_expression(), ",");
        if (!list) return null;
        this.op(",");
        return list;
    }

    star_named_expression() {
        const t0 = this.tk();
        const s = this.attempt(() => {
            if (!this.op("*")) return null;
            const v = this.bitwise_or();
            return v ? N("Starred", t0, {value: v}) : null;
        });
        return s || this.attempt(() => this.named_expression());
    }

    assignment_expression() {
        const t0 = this.tk();
        const a = this.nameTok();
        if (!a || !this.op(":=")) return null;
        const b = this.expression();
        return b ? N("NamedExpr", t0, {target: this.nameNode(a), value: b}) : null;
    }

    named_expression() {
        const a = this.attempt(() => this.assignment_expression());
        if (a) return a;
        if (this.invalid) this.attempt(() => this.invalid_named_expression());
        return this.attempt(() => {
            const e = this.expression();
            return e && !this.isOp(":=") ? e : null;
        });
    }

    invalid_named_expression() {
        return this.memo("invalid_named_expression", () => {
            const m = this.mark;
            let a = this.expression();
            if (a && this.op(":=") && this.expression()) this.raise(a, `cannot use assignment expressions with ${exprName(a)}`);
            this.mark = m;
            const n = this.nameTok();
            if (n && this.op("=")) {
                const b = this.bitwise_or();
                if (b && !this.isOp("=") && !this.isOp(":=")) this.raise(n, "invalid syntax. Maybe you meant '==' or ':=' instead of '='?");
            }
            this.mark = m;
            const blocked = this.look(() => this.attempt(() => this.list()) || this.attempt(() => this.tuple())
                || this.attempt(() => this.genexp()) || this.kw("True") || this.kw("None") || this.kw("False"));
            if (!blocked) {
                a = this.bitwise_or();
                if (a && this.op("=")) {
                    const b = this.bitwise_or();
                    if (b && !this.isOp("=") && !this.isOp(":=")) {
                        this.raise(a, `cannot assign to ${exprName(a)} here. Maybe you meant '==' instead of '='?`);
                    }
                }
            }
            this.mark = m;
            return null;
        });
    }

    disjunction() { return this.boolop("disjunction", "or", () => this.conjunction()); }
    conjunction() { return this.boolop("conjunction", "and", () => this.inversion()); }

    boolop(name, word, inner) {
        return this.memo(name, () => {
            const t0 = this.tk();
            const a = inner();
            if (!a) return null;
            const values = [a];
            for (;;) {
                const c = this.attempt(() => (this.kw(word) ? inner() : null));
                if (!c) break;
                values.push(c);
            }
            return values.length > 1 ? N("BoolOp", t0, {values}) : a;
        });
    }

    inversion() {
        return this.memo("inversion", () => {
            const t0 = this.tk();
            const n = this.attempt(() => {
                if (!this.kw("not")) return null;
                const e = this.inversion();
                return e ? N("UnaryOp", t0, {op: "Not", operand: e}) : null;
            });
            return n || this.attempt(() => this.comparison());
        });
    }

    comparison() {
        const t0 = this.tk();
        const a = this.bitwise_or();
        if (!a) return null;
        const ops = [], comparators = [];
        for (;;) {
            const pair = this.attempt(() => {
                const t = this.tk();
                let op = null;
                if (t.type === "OP" && ["==", "!=", "<=", "<", ">=", ">"].includes(t.str)) { this.mark++; op = t.str; }
                else if (this.isKw("not") && this.tk(1).type === "NAME" && this.tk(1).str === "in") { this.mark += 2; op = "not in"; }
                else if (this.kw("in")) op = "in";
                else if (this.isKw("is") && this.tk(1).type === "NAME" && this.tk(1).str === "not") { this.mark += 2; op = "is not"; }
                else if (this.kw("is")) op = "is";
                if (!op) return null;
                const b = this.bitwise_or();
                return b ? [op, b] : null;
            });
            if (!pair) break;
            ops.push(pair[0]);
            comparators.push(pair[1]);
        }
        return ops.length ? N("Compare", t0, {left: a, ops, comparators}) : a;
    }

    binop(name, opsList, inner) {  // a left-recursive rule, as a loop
        return this.memo(name, () => {
            const t0 = this.tk();
            let a = inner();
            if (!a) return null;
            for (;;) {
                const r = this.attempt(() => {
                    const t = this.tk();
                    if (t.type !== "OP" || !opsList.includes(t.str)) return null;
                    this.mark++;
                    return inner();
                });
                if (!r) break;
                a = N("BinOp", t0, {left: a, right: r});
            }
            return a;
        });
    }

    bitwise_or() { return this.binop("bitwise_or", ["|"], () => this.bitwise_xor()); }
    bitwise_xor() { return this.binop("bitwise_xor", ["^"], () => this.bitwise_and()); }
    bitwise_and() { return this.binop("bitwise_and", ["&"], () => this.shift_expr()); }
    shift_expr() { return this.binop("shift_expr", ["<<", ">>"], () => this.sum()); }
    sum() { return this.memo("sum_ops", () => this.sumOps()); }
    sumOps() {  // (sum keeps + and -: literal_eval reads 1+2j)
        const t0 = this.tk();
        let a = this.term();
        if (!a) return null;
        for (;;) {
            const r = this.attempt(() => {
                const t = this.tk();
                if (t.type !== "OP" || (t.str !== "+" && t.str !== "-")) return null;
                this.mark++;
                const b = this.term();
                return b ? [t.str, b] : null;
            });
            if (!r) break;
            a = N("BinOp", t0, {left: a, op: r[0] === "+" ? "Add" : "Sub", right: r[1]});
        }
        return a;
    }
    term() { return this.binop("term", ["*", "/", "//", "%", "@"], () => this.factor()); }

    factor() {
        return this.memo("factor", () => {
            const t0 = this.tk();
            const u = this.attempt(() => {
                const t = this.tk();
                if (t.type !== "OP" || !["+", "-", "~"].includes(t.str)) return null;
                this.mark++;
                const e = this.factor();
                return e ? N("UnaryOp", t0, {op: t.str === "+" ? "UAdd" : t.str === "-" ? "USub" : "Invert", operand: e}) : null;
            });
            return u || this.attempt(() => this.power());
        });
    }

    power() {
        const t0 = this.tk();
        const a = this.await_primary();
        if (!a) return null;
        const r = this.attempt(() => (this.op("**") ? this.factor() : null));
        return r ? N("BinOp", t0, {left: a, op: "Pow", right: r}) : a;
    }

    await_primary() {
        return this.memo("await_primary", () => {
            const t0 = this.tk();
            const w = this.attempt(() => {
                if (!this.kw("await")) return null;
                const p = this.primary();
                return p ? N("Await", t0, {value: p}) : null;
            });
            return w || this.attempt(() => this.primary());
        });
    }

    trailer(a, t0, lookahead) {  // one step after a primary: .name, (genexp), (arguments), [slices]
        return this.attempt(() => {
            if (this.op(".")) {
                const b = this.nameTok();
                return b && lookahead() ? N("Attribute", t0, {value: a, attr: b.str}) : null;
            }
            return null;
        }) || this.attempt(() => {
            if (!this.op("[")) return null;
            const s = this.slices();
            return s && this.op("]") && lookahead() ? N("Subscript", t0, {value: a, slice: s}) : null;
        }) || this.attempt(() => {
            const g = this.genexp();
            return g && lookahead() ? N("Call", t0, {func: a, args: [g], keywords: []}) : null;
        }) || this.attempt(() => {
            if (!this.op("(")) return null;
            const args = this.attempt(() => this.arguments()) || {args: [], keywords: []};
            return this.op(")") && lookahead() ? N("Call", t0, {func: a, args: args.args, keywords: args.keywords}) : null;
        });
    }

    primary() {
        return this.memo("primary", () => {
            const t0 = this.tk();
            let a = this.atom();
            if (!a) return null;
            for (;;) {  // (Python tries .name, then a generator, then a call, then [ ]: the same result)
                const next = this.attempt(() => {
                    if (this.op(".")) { const b = this.nameTok(); return b ? N("Attribute", t0, {value: a, attr: b.str}) : null; }
                    return null;
                }) || this.attempt(() => {
                    const g = this.genexp();
                    return g ? N("Call", t0, {func: a, args: [g], keywords: []}) : null;
                }) || this.attempt(() => {
                    if (!this.op("(")) return null;
                    const args = this.attempt(() => this.arguments()) || {args: [], keywords: []};
                    return this.op(")") ? N("Call", t0, {func: a, args: args.args, keywords: args.keywords}) : null;
                }) || this.attempt(() => {
                    if (!this.op("[")) return null;
                    const s = this.slices();
                    return s && this.op("]") ? N("Subscript", t0, {value: a, slice: s}) : null;
                });
                if (!next) break;
                a = next;
            }
            return a;
        });
    }

    slices() {
        const t0 = this.tk();
        const a = this.attempt(() => {
            const s = this.slice();
            return s && !this.isOp(",") ? s : null;
        });
        if (a) return a;
        const list = this.gather(() => this.attempt(() => this.slice()) || this.attempt(() => this.starred_expression()), ",");
        if (!list) return null;
        this.op(",");
        return N("Tuple", t0, {elts: list});
    }

    slice() {
        const t0 = this.tk();
        const s = this.attempt(() => {
            this.attempt(() => this.expression());
            if (!this.op(":")) return null;
            this.attempt(() => this.expression());
            this.attempt(() => {
                if (!this.op(":")) return null;
                this.attempt(() => this.expression());
                return true;
            });
            return N("Slice", t0);
        });
        return s || this.attempt(() => this.named_expression());
    }

    atom() {
        const t = this.tk();
        if (t.type === "NAME") {
            if (!KEYWORDS.has(t.str)) { this.mark++; return this.nameNode(t); }
            if (t.str === "True" || t.str === "False" || t.str === "None") {
                this.mark++;
                return N("Constant", t, {value: t.str === "True" ? true : t.str === "False" ? false : null});
            }
            return null;
        }
        if (t.type === "STRING" || t.type === "FSTRING_START") return this.strings();
        if (t.type === "NUMBER") { this.mark++; return N("Constant", t, {value: numberValue(t.str)}); }
        if (t.type !== "OP") return null;
        if (t.str === "(") return this.attempt(() => this.tuple()) || this.attempt(() => this.group()) || this.attempt(() => this.genexp());
        if (t.str === "[") return this.attempt(() => this.list()) || this.attempt(() => this.listcomp());
        if (t.str === "{") {
            return this.attempt(() => this.dict()) || this.attempt(() => this.set()) || this.attempt(() => this.dictcomp())
                || this.attempt(() => this.setcomp());
        }
        if (t.str === "...") { this.mark++; return N("Constant", t, {value: ELLIPSIS}); }
        return null;
    }

    strings() {
        return this.memo("strings", () => {
            const t0 = this.tk(), parts = [];
            for (;;) {
                const t = this.tk();
                if (t.type === "STRING") { this.mark++; parts.push(this.stringValue(t)); continue; }
                if (t.type === "FSTRING_START" && this.attempt(() => this.fstring())) { parts.push(FSTRING); continue; }
                break;
            }
            if (!parts.length) return null;
            const bytes = parts.filter(p => p instanceof PyBytes).length;
            if (bytes && bytes !== parts.length) this.raiseHere("cannot mix bytes and nonbytes literals");
            if (parts.some(p => p === FSTRING)) return N("JoinedStr", t0);
            if (bytes) return N("Constant", t0, {value: new PyBytes(parts.flatMap(p => p.bytes))});
            return N("Constant", t0, {value: parts.some(x => x instanceof PyStr) ? makeStr(parts.flatMap(cpsOf)) : parts.join("")});
        });
    }

    fstring() {  // FSTRING_START fstring_middle* FSTRING_END
        const start = this.type("FSTRING_START");
        if (!start) return null;
        const texts = [];
        for (;;) {
            if (this.attempt(() => this.fstring_replacement_field())) continue;
            const t = this.type("FSTRING_MIDDLE");
            if (!t) break;
            texts.push(t);
        }
        if (!this.type("FSTRING_END")) return null;
        for (const t of texts) {  // (Python's joined_str: the text between the fields, its escapes read)
            const text = t.str === "{{" || t.str === "}}" ? t.str[0] : t.str;
            if (/[rR]/.test(start.str) || !text.includes("\\")) continue;
            try { decodeStr(cp(text)); } catch (e) { if (e instanceof PySyntaxError) this.raiseHere(e.msg); throw e; }
        }
        return true;
    }

    format_spec_text() {  // a format spec's text: its escapes read at once (an error there is not a SyntaxError)
        const t = this.type("FSTRING_MIDDLE");
        if (t && t.str.includes("\\")) {
            try { decodeStr(cp(t.str)); } catch (e) { if (e instanceof PySyntaxError) throw new PyError("UnicodeDecodeError", e.msg); throw e; }
        }
        return t;
    }

    fstring_expr() { return this.attempt(() => this.yield_expr()) || this.attempt(() => this.star_expressions()); }

    fstring_replacement_field() {
        const r = this.attempt(() => {
            if (!this.op("{") || !this.fstring_expr()) return null;
            this.op("=");
            const conv = this.attempt(() => {
                const t = this.op("!");
                const n = t && this.nameTok();
                if (!n) return null;
                if (t.line !== n.line || t.end !== n.start) this.raise(t, "f-string: conversion type must come right after the exclamanation mark");
                return n;
            });
            this.attempt(() => {
                if (!this.op(":")) return null;
                while (this.format_spec_text() || this.attempt(() => this.fstring_replacement_field()));
                return true;
            });
            if (!this.op("}")) return null;
            if (conv) {
                const id = this.nameNode(conv).id;
                if (cp(id).length > 1 || !"sra".includes(id)) this.raise(conv, `f-string: invalid conversion character ${strRepr(id)}: expected 's', 'r', or 'a'`);
            }
            return true;
        });
        if (r) return r;
        if (this.invalid) this.attempt(() => this.invalid_replacement_field());
        return null;
    }

    raiseNext(msg) { this.raise(this.tk(), msg); }  // (Python's RAISE_SYNTAX_ERROR_ON_NEXT_TOKEN)

    invalid_replacement_field() {
        const m = this.mark, ends = (...ops) => ops.some(o => this.isOp(o));
        if (this.op("{")) {
            const t = this.tk();
            if (t.type === "OP" && ["=", "!", ":", "}"].includes(t.str)) this.raise(t, `f-string: valid expression required before '${t.str}'`);
            if (!this.look(() => this.fstring_expr())) this.raiseNext("f-string: expecting a valid expression after '{'");
        }
        this.mark = m;
        const field = () => this.op("{") && this.fstring_expr();
        if (field() && !ends("=", "!", ":", "}")) this.raiseNext("f-string: expecting '=', or '!', or ':', or '}'");
        this.mark = m;
        if (field() && this.op("=") && !ends("!", ":", "}")) this.raiseNext("f-string: expecting '!', or ':', or '}'");
        this.mark = m;
        if (field()) {
            this.op("=");
            if (this.op("!")) {
                if (ends(":", "}")) this.raiseNext("f-string: missing conversion character");
                if (!(this.tk().type === "NAME" && !KEYWORDS.has(this.tk().str))) this.raiseNext("f-string: invalid conversion character");
            }
        }
        this.mark = m;
        const head = () => { if (!field()) return false; this.op("="); this.attempt(() => this.op("!") && this.nameTok()); return true; };
        if (head() && !ends(":", "}")) this.raiseNext("f-string: expecting ':' or '}'");
        this.mark = m;
        if (head() && this.op(":")) {
            while (this.format_spec_text() || this.attempt(() => this.fstring_replacement_field()));
            if (!this.isOp("}")) this.raiseNext("f-string: expecting '}', or format specs");
        }
        this.mark = m;
        if (head() && !this.isOp("}")) this.raiseNext("f-string: expecting '}'");
        this.mark = m;
        return null;
    }

    stringValue(t) {  // (what Python's string rule does with each string as it reads it)
        const p = t.prefix;  // (f-strings are their own tokens: see fstring)
        if (p.includes("b")) {
            if (t.body.some(c => c.codePointAt(0) >= 0x80)) this.raise(t, "bytes can only contain ASCII literal characters");
            if (p.includes("r")) return new PyBytes(t.body.map(c => c.charCodeAt(0)));
            try { return decodeBytes(t.body); } catch (e) { if (e instanceof PySyntaxError) this.raiseHere(e.msg); throw e; }
        }
        if (p.includes("r")) return t.body.join("");
        try { return decodeStr(t.body); } catch (e) { if (e instanceof PySyntaxError) this.raiseHere(e.msg); throw e; }
    }

    tuple() {
        const t0 = this.tk();
        if (!this.op("(")) return null;
        const elts = this.attempt(() => {
            const a = this.star_named_expression();
            if (!a || !this.op(",")) return null;
            return [a, ...(this.attempt(() => this.star_named_expressions()) || [])];
        }) || [];
        return this.op(")") ? N("Tuple", t0, {elts}) : null;
    }

    group() {
        const r = this.attempt(() => {
            if (!this.op("(")) return null;
            const a = this.attempt(() => this.yield_expr()) || this.attempt(() => this.named_expression());
            return a && this.op(")") ? a : null;
        });
        if (r) return r;
        if (this.invalid) {
            this.attempt(() => {
                if (!this.op("(")) return null;
                const a = this.starred_expression();
                if (a && this.op(")")) this.raise(a, "cannot use starred expression here");
                return null;
            });
            this.attempt(() => {
                if (!this.op("(")) return null;
                const a = this.op("**");
                if (a && this.expression() && this.op(")")) this.raise(a, "cannot use double starred expression here");
                return null;
            });
        }
        return null;
    }

    genexp() {
        const t0 = this.tk();
        const r = this.attempt(() => {
            if (!this.op("(")) return null;
            const a = this.attempt(() => this.assignment_expression()) || this.attempt(() => {
                const e = this.expression();
                return e && !this.isOp(":=") ? e : null;
            });
            return a && this.for_if_clauses() && this.op(")") ? N("GeneratorExp", t0) : null;
        });
        if (r) return r;
        if (this.invalid) this.attempt(() => this.invalid_comprehension());
        return null;
    }

    list() {
        const t0 = this.tk();
        if (!this.op("[")) return null;
        const elts = this.attempt(() => this.star_named_expressions()) || [];
        return this.op("]") ? N("List", t0, {elts}) : null;
    }

    listcomp() {
        const t0 = this.tk();
        const r = this.attempt(() => this.op("[") && this.named_expression() && this.for_if_clauses() && this.op("]"));
        if (r) return N("ListComp", t0);
        if (this.invalid) this.attempt(() => this.invalid_comprehension());
        return null;
    }

    set() {
        const t0 = this.tk();
        if (!this.op("{")) return null;
        const elts = this.star_named_expressions();
        return elts && this.op("}") ? N("Set", t0, {elts}) : null;
    }

    setcomp() {
        const t0 = this.tk();
        const r = this.attempt(() => this.op("{") && this.named_expression() && this.for_if_clauses() && this.op("}"));
        if (r) return N("SetComp", t0);
        if (this.invalid) this.attempt(() => this.invalid_comprehension());
        return null;
    }

    dict() {
        const t0 = this.tk();
        const r = this.attempt(() => {
            if (!this.op("{")) return null;
            const pairs = this.attempt(() => this.double_starred_kvpairs()) || [];
            return this.op("}") ? N("Dict", t0, {keys: pairs.map(p => p[0]), values: pairs.map(p => p[1])}) : null;
        });
        if (r) return r;
        this.attempt(() => {  // (always, as Python's: only an alternative that is one invalid_ rule waits for the second pass)
            if (!this.op("{")) return null;
            this.invalid_double_starred_kvpairs();
            return null;
        });
        return null;
    }

    dictcomp() {
        const t0 = this.tk();
        const r = this.attempt(() => this.op("{") && this.kvpair() && this.for_if_clauses() && this.op("}"));
        if (r) return N("DictComp", t0);
        if (this.invalid) {
            this.attempt(() => {
                if (!this.op("{")) return null;
                const a = this.op("**");
                if (a && this.bitwise_or() && this.for_if_clauses() && this.op("}")) this.raise(a, "dict unpacking cannot be used in dict comprehension");
                return null;
            });
        }
        return null;
    }

    double_starred_kvpairs() {
        const list = this.gather(() => this.double_starred_kvpair(), ",");
        if (!list) return null;
        this.op(",");
        return list;
    }

    double_starred_kvpair() {
        return this.attempt(() => {
            if (!this.op("**")) return null;
            const v = this.bitwise_or();
            return v ? [null, v] : null;
        }) || this.attempt(() => this.kvpair());
    }

    kvpair() {
        const k = this.expression();
        if (!k || !this.op(":")) return null;
        const v = this.expression();
        return v ? [k, v] : null;
    }

    invalid_double_starred_kvpairs() {
        const m = this.mark;
        const list = this.gather(() => this.double_starred_kvpair(), ",");
        if (list && this.op(",")) this.invalid_kvpair();
        this.mark = m;
        this.invalid_kv_value();
        this.mark = m;
        return null;
    }

    invalid_kv_value() {  // expression ':' '*' ... and expression ':' with nothing after it
        const m = this.mark;
        if (this.expression() && this.op(":")) {
            const a = this.op("*");
            if (a && this.bitwise_or()) this.raise(a, "cannot use a starred expression in a dictionary value");
        }
        this.mark = m;
        if (this.expression()) {
            const c = this.op(":");
            if (c && (this.isOp("}") || this.isOp(","))) this.raise(c, "expression expected after dictionary key and ':'");
        }
        this.mark = m;
    }

    invalid_kvpair() {
        const m = this.mark;
        const a = this.expression();
        if (a && !this.isOp(":")) this.raise(a, "':' expected after dictionary key");
        this.mark = m;
        this.invalid_kv_value();
        this.mark = m;
        return null;
    }

    for_if_clauses() {
        const out = [];
        for (;;) {
            const c = this.attempt(() => this.for_if_clause());
            if (!c) break;
            out.push(c);
        }
        return out.length ? out : null;
    }

    for_if_clause() {
        const m = this.mark;
        let cut = false;
        const r = this.attempt(() => {
            this.kw("async");
            if (!this.kw("for") || !this.star_targets() || !this.kw("in")) return null;
            cut = true;
            if (!this.disjunction()) return null;
            while (this.attempt(() => (this.kw("if") ? this.disjunction() : null)));
            return true;
        });
        if (r || cut) return r;
        this.mark = m;
        if (this.invalid) this.attempt(() => this.invalid_for_target());
        return null;
    }

    invalid_for_target() {
        this.kw("async");
        if (!this.kw("for")) return null;
        const a = this.star_expressions();
        const bad = a && invalidTarget(a, "for");
        if (bad) this.raise(bad, `cannot assign to ${exprName(bad)}`);
        return null;
    }

    invalid_comprehension() {
        const m = this.mark;
        if (this.op("[") || this.op("(") || this.op("{")) {
            const a = this.starred_expression();
            if (a && this.for_if_clauses()) this.raise(a, "iterable unpacking cannot be used in comprehension");
        }
        this.mark = m;
        if (this.op("[") || this.op("{")) {
            const a = this.star_named_expression();
            if (a && this.op(",")) {
                const b = this.star_named_expressions();
                if (b && this.for_if_clauses()) this.raise(a, "did you forget parentheses around the comprehension target?");
            }
        }
        this.mark = m;
        if (this.op("[") || this.op("{")) {
            const a = this.star_named_expression();
            if (a && this.op(",") && this.for_if_clauses()) this.raise(a, "did you forget parentheses around the comprehension target?");
        }
        this.mark = m;
        return null;
    }

    arguments() {
        return this.memo("arguments", () => {
            const r = this.attempt(() => {
                const a = this.args();
                if (!a) return null;
                this.op(",");
                return this.isOp(")") ? a : null;
            });
            if (r) return r;
            if (this.invalid) this.attempt(() => this.invalid_arguments());
            return null;
        });
    }

    arg_item() {
        return this.attempt(() => this.starred_expression()) || this.attempt(() => {
            const a = this.attempt(() => this.assignment_expression()) || this.attempt(() => {
                const e = this.expression();
                return e && !this.isOp(":=") ? e : null;
            });
            return a && !this.isOp("=") ? a : null;
        });
    }

    args() {
        const r = this.attempt(() => {
            const items = this.gather(() => this.arg_item(), ",");
            if (!items) return null;
            const k = this.attempt(() => (this.op(",") ? this.kwargs() : null)) || [];
            return {args: items.concat(k.filter(x => x.t === "Starred")), keywords: k.filter(x => x.t !== "Starred")};
        });
        if (r) return r;
        const k = this.attempt(() => this.kwargs());
        return k ? {args: k.filter(x => x.t === "Starred"), keywords: k.filter(x => x.t !== "Starred")} : null;
    }

    kwargs() {
        return this.attempt(() => {
            const a = this.gather(() => this.kwarg_or_starred(), ",");
            if (!a || !this.op(",")) return null;
            const b = this.gather(() => this.kwarg_or_double_starred(), ",");
            return b ? a.concat(b) : null;
        }) || this.attempt(() => this.gather(() => this.kwarg_or_starred(), ","))
            || this.attempt(() => this.gather(() => this.kwarg_or_double_starred(), ","));
    }

    starred_expression() {
        const t0 = this.tk();
        if (this.invalid) {
            this.attempt(() => {
                const a = this.op("*");
                if (a && this.expression() && this.op("=") && this.expression()) this.raise(a, "cannot assign to iterable argument unpacking");
                return null;
            });
        }
        const s = this.attempt(() => {
            if (!this.op("*")) return null;
            const e = this.expression();
            return e ? N("Starred", t0, {value: e}) : null;
        });
        if (s) return s;
        if (this.op("*")) this.raiseHere("Invalid star expression");  // (not an invalid_ rule: the first pass says it too)
        return null;
    }

    kwarg(starStar) {
        const t0 = this.tk();
        if (this.invalid) this.attempt(() => this.invalid_kwarg());
        return this.attempt(() => {
            const n = this.nameTok();
            if (!n || !this.op("=")) return null;
            const e = this.expression();
            return e ? N("keyword", t0, {arg: n.str, value: e}) : null;
        }) || (starStar ? this.attempt(() => {
            if (!this.op("**")) return null;
            const e = this.expression();
            return e ? N("keyword", t0, {arg: null, value: e}) : null;
        }) : this.attempt(() => this.starred_expression()));
    }

    kwarg_or_starred() { return this.kwarg(false); }
    kwarg_or_double_starred() { return this.kwarg(true); }

    invalid_kwarg() {
        const m = this.mark, t = this.tk();
        if (t.type === "NAME" && (t.str === "True" || t.str === "False" || t.str === "None")) {
            this.mark++;
            if (this.op("=")) this.raise(t, `cannot assign to ${t.str}`);
        }
        this.mark = m;
        const a = this.nameTok();
        if (a && this.op("=") && this.expression() && this.for_if_clauses()) this.raise(a, "invalid syntax. Maybe you meant '==' or ':=' instead of '='?");
        this.mark = m;
        const t0 = this.tk();
        const nameEq = t0.type === "NAME" && !KEYWORDS.has(t0.str) && this.tk(1).type === "OP" && this.tk(1).str === "=";
        if (!nameEq) {
            const e = this.expression();
            if (e && this.op("=")) this.raise(e, 'expression cannot contain assignment, perhaps you meant "=="?');
        }
        this.mark = m;
        const s = this.op("**");
        if (s && this.expression() && this.op("=") && this.expression()) this.raise(s, "cannot assign to keyword argument unpacking");
        this.mark = m;
        return null;
    }

    invalid_arguments() {
        const m = this.mark;
        let ok = this.attempt(() => this.gather(() => this.arg_item(), ",") && this.op(",") && this.kwargs())
            || this.attempt(() => this.kwargs());
        if (ok) {
            const a = this.op(",");
            if (a && this.gather(() => this.attempt(() => { const x = this.starred_expression(); return x && !this.isOp("=") ? x : null; }), ",")) {
                this.raise(a, "iterable argument unpacking follows keyword argument unpacking");
            }
        }
        this.mark = m;
        let a = this.expression();
        if (a && this.for_if_clauses() && this.op(",")) {
            this.attempt(() => this.args()) || this.attempt(() => this.expression() && this.for_if_clauses());  // (read, as Python reads it)
            this.raise(a, "Generator expression must be parenthesized");
        }
        this.mark = m;
        const n = this.nameTok();
        if (n && this.op("=") && this.expression() && this.for_if_clauses()) this.raise(n, "invalid syntax. Maybe you meant '==' or ':=' instead of '='?");
        this.mark = m;
        this.attempt(() => this.args() && this.op(","));
        const n2 = this.nameTok();
        if (n2 && this.op("=") && (this.isOp(",") || this.isOp(")"))) this.raise(n2, "expected argument value expression");
        this.mark = m;
        const ar = this.args();
        if (ar && this.for_if_clauses()) {
            if (ar.args.length > 1) this.raise(ar.args[ar.args.length - 1], "Generator expression must be parenthesized");
            this.mark = m;
            return null;
        }
        this.mark = m;
        if (this.args() && this.op(",")) {
            a = this.expression();
            if (a && this.for_if_clauses()) this.raise(a, "Generator expression must be parenthesized");
        }
        this.mark = m;
        const ar2 = this.args();
        if (ar2 && this.op(",") && this.args()) {
            this.raiseHere(ar2.keywords.some(k => k.arg === null) ? "positional argument follows keyword argument unpacking"
                : "positional argument follows keyword argument");
        }
        this.mark = m;
        return null;
    }

    lambdef() {
        const t0 = this.tk();
        if (!this.kw("lambda")) return null;
        this.attempt(() => this.params(true));
        if (!this.op(":")) return null;
        const e = this.expression();
        return e ? N("Lambda", t0) : null;
    }

    // ----- targets -----
    t_lookahead() { return this.isOp("(") || this.isOp("[") || this.isOp("."); }

    t_primary() {
        return this.memo("t_primary", () => {
            const t0 = this.tk();
            let a = this.atom();
            if (!a || !this.t_lookahead()) return null;
            for (;;) {
                const next = this.trailer(a, t0, () => this.t_lookahead());
                if (!next) break;
                a = next;
            }
            return a;
        });
    }

    subscript_attribute_target(t0) {  // t_primary '.' NAME !t_lookahead | t_primary '[' slices ']' !t_lookahead
        return this.attempt(() => {
            const a = this.t_primary();
            if (!a || !this.op(".")) return null;
            const b = this.nameTok();
            return b && !this.t_lookahead() ? N("Attribute", t0, {value: a, attr: b.str}) : null;
        }) || this.attempt(() => {
            const a = this.t_primary();
            if (!a || !this.op("[")) return null;
            const s = this.slices();
            return s && this.op("]") && !this.t_lookahead() ? N("Subscript", t0, {value: a, slice: s}) : null;
        });
    }

    single_subscript_attribute_target() { return this.subscript_attribute_target(this.tk()); }

    single_target() {
        return this.attempt(() => this.single_subscript_attribute_target()) || this.attempt(() => {
            const n = this.nameTok();
            return n ? this.nameNode(n) : null;
        }) || this.attempt(() => {
            if (!this.op("(")) return null;
            const a = this.single_target();
            return a && this.op(")") ? a : null;
        });
    }

    star_targets() {
        const t0 = this.tk();
        const a = this.star_target();
        if (!a) return null;
        if (!this.isOp(",")) return a;
        const elts = [a];
        for (;;) {
            const c = this.attempt(() => (this.op(",") ? this.star_target() : null));
            if (!c) break;
            elts.push(c);
        }
        this.op(",");
        return N("Tuple", t0, {elts});
    }

    star_target() {
        return this.memo("star_target", () => {
            const t0 = this.tk();
            const s = this.attempt(() => {
                if (!this.op("*") || this.isOp("*")) return null;
                const v = this.star_target();
                return v ? N("Starred", t0, {value: v}) : null;
            });
            return s || this.attempt(() => this.target_with_star_atom());
        });
    }

    target_with_star_atom() {
        return this.memo("target_with_star_atom", () => {
            const t0 = this.tk();
            return this.subscript_attribute_target(t0) || this.attempt(() => this.star_atom());
        });
    }

    star_atom() {
        const t0 = this.tk();
        const n = this.nameTok();
        if (n) return this.nameNode(n);
        return this.attempt(() => {
            if (!this.op("(")) return null;
            const a = this.target_with_star_atom();
            return a && this.op(")") ? a : null;
        }) || this.attempt(() => {
            if (!this.op("(")) return null;
            const a = this.attempt(() => this.star_targets_tuple_seq()) || [];
            return this.op(")") ? N("Tuple", t0, {elts: a}) : null;
        }) || this.attempt(() => {
            if (!this.op("[")) return null;
            const a = this.attempt(() => {
                const l = this.gather(() => this.star_target(), ",");
                if (l) this.op(",");
                return l;
            }) || [];
            return this.op("]") ? N("List", t0, {elts: a}) : null;
        });
    }

    star_targets_tuple_seq() {
        const a = this.star_target();
        if (!a) return null;
        const out = [a];
        for (;;) {
            const c = this.attempt(() => (this.op(",") ? this.star_target() : null));
            if (!c) break;
            out.push(c);
        }
        if (out.length > 1) { this.op(","); return out; }
        return this.op(",") ? out : null;
    }

    del_targets() {
        const l = this.gather(() => this.del_target(), ",");
        if (l) this.op(",");
        return l;
    }

    del_target() {
        return this.memo("del_target", () => {
            const t0 = this.tk();
            return this.subscript_attribute_target(t0) || this.attempt(() => {
                const n = this.nameTok();
                return n ? this.nameNode(n) : null;
            }) || this.attempt(() => {
                if (!this.op("(")) return null;
                const a = this.del_target();
                return a && this.op(")") ? a : null;
            }) || this.attempt(() => {
                if (!this.op("(")) return null;
                this.attempt(() => this.del_targets());
                return this.op(")") ? N("Tuple", t0, {elts: []}) : null;
            }) || this.attempt(() => {
                if (!this.op("[")) return null;
                this.attempt(() => this.del_targets());
                return this.op("]") ? N("List", t0, {elts: []}) : null;
            });
        });
    }

    // ----- when it fails -----
    fullSourceCheck(err) {  // Python reads the rest: a broken string, number or bracket further on is the real error
        const errLine = this.lastTok().line;
        for (;;) {
            const t = this.tz.next();
            if (t.type === "ERROR") {
                if (t.hard) return t.fstr ? err : new PySyntaxError(t.line, t.msg, true);
                // (inside an f-string, Python lets the first error stand)
                if (this.tz.level > 0 && errLine > this.tz.parens[this.tz.level - 1].line && !this.tz.fmodes.length) {
                    return this.neverClosed(true);
                }
                return err;
            }
            if (t.type === "ENDMARKER") return err;
        }
    }
}

const FSTRING = Object.freeze({fstring: true});

function astDepth(stmts) {  // how deep the statements' nodes go (the module is 1)
    let most = 1;
    const stack = stmts.map(s => [s, 2]);
    const isNode = v => v !== null && typeof v === "object" && typeof v.t === "string";
    while (stack.length) {
        const [n, d] = stack.pop();
        if (d > most) most = d;
        for (const k in n) {
            const v = n[k];
            if (isNode(v)) stack.push([v, d + 1]);
            else if (Array.isArray(v)) for (const x of v) if (isNode(x)) stack.push([x, d + 1]);
        }
    }
    return most;
}

export function pythonParse(text) {  // ast.parse(text): the statements, or a PySyntaxError
    try {
        const tree = parseText(text);
        // (Python makes its own objects of the nodes, and stops past about 3000 deep: an error the app doesn't catch)
        if (astDepth(tree) > 2998) throw new PyError("RecursionError", "maximum recursion depth exceeded during ast construction");
        return tree;
    } catch (e) {
        if (e instanceof RangeError) throw new PyError("MemoryError", "Parser stack overflowed - Python source too complex to parse");
        throw e;
    }
}

function parseText(text) {
    if (text.includes("\0")) throw new PySyntaxError(null, "source code string cannot contain null bytes");
    if (/\p{Cs}/u.test(text)) throw new PyError("UnicodeEncodeError", "surrogates not allowed");
    let src = text.replace(/\r\n?/g, "\n");
    if (src && !src.endsWith("\n")) src += "\n";
    const p = new Parser(src);
    let tree;
    try {
        tree = p.file();
    } catch (e) {
        if (e instanceof PySyntaxError && !e.fromTokenizer) throw p.fullSourceCheck(e);
        throw e;
    }
    if (tree) return tree;
    const last = p.lastTok();
    p.mark = 0;
    p.memos = new Map();
    p.invalid = true;
    try {
        p.file();
    } catch (e) {
        if (e instanceof PySyntaxError && !e.fromTokenizer) throw p.fullSourceCheck(e);
        throw e;
    }
    if (last.type === "INDENT" || last.type === "DEDENT") {
        throw new PySyntaxError(p.lastTok().line, last.type === "INDENT" ? "unexpected indent" : "unexpected unindent");
    }
    throw p.fullSourceCheck(new PySyntaxError(last.line, "invalid syntax"));
}

// ast.literal_eval, on the parser's nodes
const malformed = () => { throw new PyError("ValueError", "malformed node or string"); };

function convertNum(node) {
    if (!node || node.t !== "Constant") malformed();
    const v = node.value;
    if (typeof v === "number" || typeof v === "bigint" || v instanceof PyFloat || v instanceof PyComplex) return v;
    return malformed();
}

function convertSignedNum(node) {
    if (node && node.t === "UnaryOp" && (node.op === "UAdd" || node.op === "USub")) {
        const v = convertNum(node.operand);
        if (node.op === "UAdd") return v;
        if (typeof v === "number") return 0 - v;
        if (typeof v === "bigint") return -v;
        if (v instanceof PyFloat) return new PyFloat(-v.v);
        return new PyComplex(-v.re, -v.im);
    }
    return convertNum(node);
}

export function literalEval(node) {
    switch (node && node.t) {
        case "Constant": return node.value;
        case "Tuple": return new PyTuple(node.elts.map(literalEval));
        case "List": return node.elts.map(literalEval);
        case "Set": {
            const s = new PySet();
            for (const e of node.elts) s.add(literalEval(e));
            return s;
        }
        case "Call":
            if (node.func.t === "Name" && node.func.id === "set" && !node.args.length && !node.keywords.length) return new PySet();
            break;
        case "Dict": {
            const d = new PyDict();
            for (let i = 0; i < node.keys.length; i++) {
                const k = node.keys[i] === null ? malformed() : literalEval(node.keys[i]);
                d.set(k, literalEval(node.values[i]));
            }
            return d;
        }
        case "BinOp":
            if (node.op === "Add" || node.op === "Sub") {
                const left = convertSignedNum(node.left), right = convertNum(node.right);
                if ((typeof left === "number" || typeof left === "bigint" || left instanceof PyFloat) && right instanceof PyComplex) {
                    const l = num(left);
                    return node.op === "Add" ? new PyComplex(l + right.re, right.im) : new PyComplex(l - right.re, 0 - right.im);
                }
            }
            break;
    }
    return convertSignedNum(node);
}

// ---------- the code, read back (engine.schema.parse_code) ----------

export function parseCode(game, text, ctx) {
    const schema = varsOf(game);
    text = text.split("\n").map(pyStrip).join("\n");  // (spaces and blank lines anywhere: CHANGE 88)
    let tree;
    try {
        tree = pythonParse(text);
    } catch (e) {
        if (!(e instanceof PySyntaxError)) throw e;
        const msg = /[.?!]$/.test(e.msg) ? e.msg : e.msg + ".";
        throw new ParseError(e.lineno, `${msg} Check the brackets, commas and quote marks.`);
    }
    const choices = new Map();
    for (const v of schema) if (v.kind === "choice" && v.list_name) choices.set(v.list_name, v);
    const values = Object.create(null);
    for (const st of tree) {
        let target, value;
        if (st.t === "AnnAssign" && st.target.t === "Name" && st.value) { target = st.target.id; value = st.value; }
        else if (st.t === "Assign" && st.targets.length === 1 && st.targets[0].t === "Name") { target = st.targets[0].id; value = st.value; }
        else throw new ParseError(st.lineno, "only lines like  name: type = value  are allowed.");
        if (value.t === "Subscript" && value.value.t === "Name" && choices.has(value.value.id)) {
            const v = choices.get(value.value.id);
            const fallback = optionsOf(game, v, ctx);
            const options = v.list_name in values ? values[v.list_name] : fallback;
            try {
                values[target] = pyIndex(options, literalEval(value.slice));
            } catch (e) {
                if (!(e instanceof PyError) || !["ValueError", "TypeError", "IndexError", "KeyError"].includes(e.type)) throw e;
                throw new ParseError(st.lineno, `${v.list_name}[...] needs a number from 0 (the first) to ${pyLen(options) - 1} (the last).`);
            }
            continue;
        }
        try {
            values[target] = literalEval(value);
        } catch (e) {
            if (e instanceof PyError && e.type === "ValueError") {
                throw new ParseError(st.lineno, 'only plain values are allowed: numbers, "text" and [lists].');
            }
            throw e;
        }
    }
    return values;
}

// ---------- the values, checked and put in the design (engine.schema.check_value, apply_values) ----------

export function checkValue(game, v, value, ctx) {
    if (v.kind === "str") return isStr(value) ? null : `${v.name} must be text in quotes`;
    if (v.kind === "int") return isNum(value) ? null : `${v.name} must be a number`;
    if (v.kind === "rgb") {
        const ok = Array.isArray(value) && value.length === 3 && value.every(c => isInt(c) && c >= 0 && c <= 255);
        return ok ? null : `${v.name} must be a list of three whole numbers from 0 to 255`;
    }
    if (v.kind === "choice") {
        const options = v.valid ? pyList(fn(game, v.valid)(ctx)) : optionsOf(game, v, ctx);
        if (value === null && v.optional) return null;
        return pyIn(value, options) ? null : `${v.name} must be one of: ${options.map(pyStr).join(", ")}`;
    }
    if (v.kind === "words") {
        const options = v.options ? optionsOf(game, v, ctx) : null;
        if (!Array.isArray(value) || !value.every(isStr)) return `${v.name} must be a list of words in quotes`;
        if (options !== null && value.some(w => !pyIn(w, options))) return `${v.name} may only have: ${options.join(", ")}`;
        return null;
    }
    return null;
}

const plain = v => (v instanceof PyFloat ? v.v : Array.isArray(v) ? v.map(plain) : v);  // (as the design keeps it)

export function applyValues(game, design, values, ctx, allowed) {
    const schema = varsOf(game);
    const known = new Set(schema.map(v => v.name).concat(schema.filter(v => v.list_name).map(v => v.list_name)));
    const changed = [], hidden = [], problems = [];
    for (const name in values) if (!known.has(name)) problems.push(`'${name}' isn't one of the variables`);
    for (const v of schema) {
        if (!(v.name in values)) continue;
        let value = values[v.name];
        const problem = checkValue(game, v, value, ctx);
        if (problem) { problems.push(problem); continue; }
        if (v.kind === "str") value = makeStr(cpsOf(value).slice(0, v.max_len));
        else if (v.kind === "int" && v.group === "points") {
            const x = num(value);
            if (!Number.isFinite(x)) throw new PyError(Number.isNaN(x) ? "ValueError" : "OverflowError", "int()");
            if (x === Math.trunc(x)) value = Math.trunc(x) + 0;
        }
        if (pyEq(value, getVar(v, design))) continue;
        setVar(v, design, plain(value));
        changed.push(v.name);
        if (!allowed(v, value)) hidden.push(v.name);
        if (v.after) fn(game, v.after)(design, ctx);
    }
    return {changed, hidden, problems};
}

export function shown(v, tools) {  // whether a lesson's garage shows this variable (its tool is on; no tool: always)
    return v.tool ? pyTruthy(pyGet(tools, v.tool, true)) : true;
}

export function canChange(game, v, tools, value = null) {  // engine.garage.can_change
    if (v.tool && !pyTruthy(pyGet(tools, v.tool))) return false;
    if (v.allowed_values && value !== null) return pyIn(value, pyList(fn(game, v.allowed_values)(tools)));
    return true;
}

export function outsideLesson(game, old, now, tools, allowed = null) {  // engine.schema.outside_lesson
    const found = [];
    for (const v of varsOf(game)) {
        const a = getVar(v, old), b = getVar(v, now);
        if (pyEq(a, b)) continue;
        const ok = allowed ? allowed(v, b)
            : shown(v, tools) && (!v.allowed_values || pyIn(b, pyList(fn(game, v.allowed_values)(tools))));
        if (!ok) found.push([v.name, a === null ? "none" : a, b === null ? "none" : b]);
    }
    return found;
}

// ---------- each game's own rules (the functions schemas.json names) ----------

const weaponsFor = (game, style) => Object.entries(game.consts.weapons).filter(([, s]) => s === style).map(([w]) => w);
function styleOf(game, d) {  // fight_sim.style_of: a design's fighting style and weapon
    let style = pyGet(d, "fighting_style", "kickboxer");
    if (!pyIn(style, game.consts.styles)) style = "kickboxer";
    return [style, weaponsFor(game, style).length ? pyGet(d, "weapon") : null];
}
const uniq = list => list.filter((x, i) => list.findIndex(y => pyEq(x, y)) === i);  // dict.fromkeys(list)
const houseWeapons = ctx => uniq(Object.values(ctx.house || {}));

export const FUNCTIONS = {
    // options (ctx) -> the words offered; valid (ctx) -> every word accepted
    lab_weapon_options: (game, ctx) => {
        const extra = pyTruthy(ctx.model) ? houseWeapons(ctx).filter(w => !pyIn(w, pyList(ctx.weapons))) : [];
        return pyList(ctx.weapons).concat(extra);
    },
    lab_weapon_valid: (game, ctx) => pyList(ctx.all_weapons).concat(houseWeapons(ctx).filter(w => !pyIn(w, pyList(ctx.all_weapons)))),
    house_names: (game, ctx) => pyList(ctx.house),
    body_names: (game, ctx) => pyList(ctx.bodies),
    boss_names: (game, ctx) => pyList(ctx.bosses),
    mission_specials: (game, ctx) => ctx.specials,
    all_specials: (game, ctx) => ctx.all_specials,
    style_names: (game, ctx) => pyList(ctx.styles),
    style_weapons: (game, ctx) => weaponsFor(game, styleOf(game, ctx.design)[0]),
    combo_move_names: (game, ctx) => pyList(ctx.combo_moves),
    // allowed_values (tools) -> the values this mission's garage offers
    lab_weapons_allowed: (game, tools) => pyList(pyGet(tools, "weapons", [])).concat(game.consts.house_weapons),
    fight_specials_allowed: (game, tools) => pyGet(tools, "specials", []),
    // unless / fixed (design) -> the row is hidden / the buttons aren't offered
    has_model: (game, d) => pyTruthy(pyGet(d, "model")),
    has_model_or_unarmed: (game, d) => pyTruthy(pyGet(d, "model")) || !weaponsFor(game, styleOf(game, d)[0]).length,
    // after (design, ctx): the game's knock-on rules after a change
    nothing: () => {},
    lab_model_changed: (game, d, ctx) => {  // a Resident Robot comes with its own weapon; a learner's design needs a learner's
        if (pyTruthy(pyGet(d, "model"))) d.weapon = pyGet(ctx.house, d.model, pyGet(d, "weapon"));
        else if (!pyIn(pyGet(d, "weapon"), pyList(ctx.all_weapons))) d.weapon = "wedge";
    },
    fight_body_changed: (game, d, ctx) => {  // a detailed 3D body gets its standard look (and Robin its trim and lights)
        const body = pyGet(d, "body");
        if (pyIn(body, game.consts.model_bodies) && !isDict(pyGet(d, "look"))) d.look = JSON.parse(JSON.stringify(game.consts.default_look[body]));
        if (body === "robin" && !isDict(pyGet(d, "style"))) d.style = JSON.parse(JSON.stringify(game.consts.robin_style));
    },
    fight_model_changed: (game, d, ctx) => {  // playing as a boss: its special is its own
        if (pyTruthy(pyGet(d, "model"))) d.special = pyGet(ctx.bosses, d.model, pyGet(d, "special"));
    },
    fight_special_changed: (game, d, ctx) => {
        if (pyTruthy(pyGet(d, "model"))) {
            if (!has(d, "special")) throw new PyError("KeyError", "'special'");
            d.special = pyGet(ctx.bosses, d.model, d.special);
        }
    },
    fight_style_changed: (game, d, ctx) => {  // an armed style has a weapon from its own list; an unarmed one has none
        const weapons = weaponsFor(game, styleOf(game, d)[0]);
        if (weapons.length && !pyIn(pyGet(d, "weapon"), weapons)) d.weapon = weapons[0];
        else if (!weapons.length) delete d.weapon;
    },
    // describe (ctx, design) -> the line under a garage row
    lab_weapon_text: (game, ctx, d) => {
        let words = pyGet(ctx.rules.weapons, d.weapon);
        if (!pyTruthy(words)) words = pyGet(ctx.rules.house_weapons, d.weapon, d.weapon);
        const maker = pyGet(ctx.makers || {}, d.weapon);
        if (pyTruthy(maker)) words += `  (made by ${pyStr(maker)})`;
        if (pyTruthy(pyGet(d, "model"))) {
            return words + "\nResident Robots are heavy (190 kg) with armour 400 and big wheels. The points aren't " +
                "used; the settings scale it (100% = as it comes).";
        }
        return words;
    },
    fight_special_text: (game, ctx, d) => {
        if (pyTruthy(pyGet(d, "model"))) {
            return pyGet(ctx.rules.specials, d.special, d.special) + "\nBosses are big and strong (260 health) " +
                "but slow. Their stats are fixed, so points and settings aren't used.";
        }
        return pyGet(ctx.rules.specials, d.special, "");
    },
    fight_style_text: (game, ctx, d) => {
        const [style, weapon] = styleOf(game, d);
        const moves = pyGet(ctx.rules.style_moves, style, {});
        const what = pyTruthy(weapon) ? ctx.rules.weapons[weapon][1] : ctx.rules.styles[style];
        return `${pyStr(what)}\nA ${pyStr(pyGet(moves, "punch"))}   S ${pyStr(pyGet(moves, "kick"))}   ` +
            `X+S ${pyStr(pyGet(moves, "low"))}   forward+S ${pyStr(pyGet(moves, "high"))}`;
    },
    // extra: a section the window draws itself (the detailed body's look, the combo editor)
    look_section: null,
    combo_section: null,
};

// ---------- the learners' limits (engine/limits.py) ----------

export function defaultLimits(game) {
    const L = game.limits;
    const settings = {};
    for (const [k, v] of Object.entries(L.settings)) settings[k] = [v[0], v[1]];
    const points = {};
    for (const k of L.stats) points[k] = L.stat_range.slice();
    return {settings, points, points_total: L.points_total};
}

export function fullLimits(game) {
    const L = game.limits;
    const settings = {};
    for (const [k, v] of Object.entries(L.full_settings)) settings[k] = v.slice();
    const points = {};
    for (const k of L.stats) points[k] = L.full_stat.slice();
    return {settings, points, points_total: L.full_points_total};
}

export function codeRoom(game, limits) {  // CHANGE 124: up to twice the teacher's highest, or the widest, whichever is smaller
    const full = fullLimits(game), out = {settings: {}, points: {}, points_total: limits.points_total};
    for (const group of ["settings", "points"]) {
        for (const [k, [lo, hi]] of Object.entries(limits[group])) {
            if (!has(full[group], k)) throw new PyError("KeyError", k);
            out[group][k] = [lo, Math.min(num(hi) * 2, full[group][k][1])];
        }
    }
    return out;
}

function limitProblems(game, d, limits) {  // Spec.problems: the points and settings outside the limits
    limits = limits || defaultLimits(game);
    const stats = game.limits.stats, out = [];
    const pts = has(d, "points") ? d.points : {};
    const same = isDict(pts) && Object.keys(pts).length === stats.length && stats.every(k => has(pts, k));
    const pyInt = v => typeof v === "boolean" || isInt(v);
    if (!same) out.push(`points must have exactly: ${stats.join(", ")}`);
    else {
        for (const [k, v] of Object.entries(pts)) {
            const [lo, hi] = limits.points[k];
            if (!isInt(v) || !(lo <= v && v <= hi)) out.push(`${k} must be a whole number from ${pyStr(lo)} to ${pyStr(hi)}`);
        }
        const values = Object.values(pts);
        if (values.every(pyInt)) {
            const total = values.reduce((a, v) => a + num(v), 0);
            if (total > limits.points_total) out.push(`${total} points used: the most you can spend is ${pyStr(limits.points_total)}`);
        }
    }
    const settings = has(d, "settings") ? d.settings : {};
    for (const [k, [lo, hi]] of Object.entries(limits.settings)) {
        const v = isDict(settings) ? pyGet(settings, k) : null;
        if (!isNum(v) || !(lo <= num(v) && num(v) <= hi)) out.push(`${k} must be from ${formatG(lo)} to ${formatG(hi)}`);
    }
    return out;
}

function checkLook(game, body, look) {  // fight_sim.check_look
    const C = game.consts;
    if (!isDict(look)) return ["look must be a dictionary"];
    const problems = [];
    if (C.human_bodies.includes(body)) {
        if (!pyIn(pyGet(look, "outfit"), C.outfits)) problems.push(`look outfit must be one of ${C.outfits.join(", ")}`);
        const hair = pyGet(C.hair_styles, body, []);
        if (!pyIn(pyGet(look, "hair"), hair)) problems.push(`look hair must be one of ${hair.join(", ")}`);
        const c = pyGet(look, "hair_colour");
        if (!(Array.isArray(c) && c.length === 3 && c.every(v => isInt(v) && v >= 0 && v <= 255))) {
            problems.push("look hair_colour must be three whole numbers from 0 to 255");
        }
    }
    if (!pyIn(pyGet(look, "shape"), C.shapes)) problems.push(`look shape must be one of ${C.shapes.join(", ")}`);
    const h = pyGet(look, "height");
    if (!isNum(h) || !(C.height[0] <= num(h) && num(h) <= C.height[1])) problems.push(`look height must be from ${C.height[0]} to ${C.height[1]}`);
    if (!pyIn(pyGet(look, "win", "victory"), C.wins)) problems.push(`look win must be one of ${C.wins.join(", ")}`);
    return problems;
}

export function checkDesign(game, d, limits = null) {  // each game's sim.check_design
    const C = game.consts, kind = game.title;
    if (kind === "Kart Lab") {
        if (!isDict(d)) return ["the design must be a dictionary"];
        const problems = [];
        const name = pyGet(d, "name");
        if (!isStr(name) || !pyStrip(String(name))) problems.push("name must be some text");
        else if (cpsOf(name).length > C.name_max) problems.push(`name can be at most ${C.name_max} characters`);
        const c = pyGet(d, "colour");
        if (!(Array.isArray(c) && c.length === 3 && c.every(v => isInt(v) && v >= 0 && v <= 255))) {
            problems.push("colour must be three whole numbers from 0 to 255, [red, green, blue]");
        }
        limits = limits || defaultLimits(game);
        for (const k of game.limits.stats) {
            const [lo, hi] = limits.points[k];
            const v = pyGet(d, k);
            if (!isInt(v) || !(lo <= v && v <= hi)) problems.push(`${k} must be a whole number from ${pyStr(lo)} to ${pyStr(hi)}`);
        }
        const vals = game.limits.stats.map(k => pyGet(d, k));
        if (vals.every(isInt)) {
            const total = vals.reduce((a, v) => a + v, 0);
            if (total > limits.points_total) problems.push(`${total} points used: the most you can spend is ${pyStr(limits.points_total)}`);
        }
        return problems;
    }
    if (kind === "Robot Lab") {
        const problems = limitProblems(game, d, limits);
        const house = Object.keys(C.house);
        if (has(d, "model")) {
            if (!pyIn(d.model, house)) problems.push(`model must be one of ${house.join(", ")} (or leave it out)`);
            else if (!pyIn(pyGet(d, "weapon"), C.weapons) && !pyIn(pyGet(d, "weapon"), C.house_weapons)) {
                problems.push(`weapon must be one of ${C.weapons.concat(C.house_weapons).join(", ")}`);
            }
        } else if (!pyIn(pyGet(d, "weapon"), C.weapons)) problems.push(`weapon must be one of ${C.weapons.join(", ")}`);
        return problems;
    }
    // Fight Lab
    if (!isDict(d)) return ["the design must be a dictionary"];
    const problems = limitProblems(game, d, limits);
    const body = pyGet(d, "body");
    if (!pyIn(body, C.bodies)) problems.push(`body must be one of ${C.bodies.join(", ")}`);
    else if (C.model_bodies.includes(body) && has(d, "look")) problems.push(...checkLook(game, body, d.look));
    const combo = pyGet(d, "combo");
    if (!Array.isArray(combo)) problems.push('combo must be a list, for example ["punch", "punch", "kick"]');
    else if (!(C.combo_min <= combo.length && combo.length <= C.combo_max)) {
        problems.push(`combo must have ${C.combo_min} to ${C.combo_max} moves (it has ${combo.length})`);
    } else if (combo.some(m => !pyIn(m, C.combo_moves))) problems.push(`each combo move must be one of ${C.combo_moves.join(", ")}`);
    const style = pyGet(d, "fighting_style", "kickboxer");
    if (!pyIn(style, C.styles)) problems.push(`fighting_style must be one of ${C.styles.join(", ")}`);
    else if (weaponsFor(game, style).length) {
        if (!pyIn(pyGet(d, "weapon"), weaponsFor(game, style))) {
            problems.push(`a ${pyStr(style)} fighter's weapon must be one of ${weaponsFor(game, style).join(", ")}`);
        }
    } else if (pyGet(d, "weapon") !== null) problems.push(`a ${pyStr(style)} fighter has no weapon (leave weapon out)`);
    if (has(d, "model")) {
        if (!pyIn(d.model, Object.keys(C.bosses))) problems.push(`model must be one of ${Object.keys(C.bosses).join(", ")} (or leave it out)`);
        else if (!pyEq(pyGet(d, "special"), C.bosses[d.model])) problems.push(`${pyStr(d.model)}'s special is ${C.bosses[d.model]}`);
    } else if (!pyIn(pyGet(d, "special"), C.specials)) problems.push(`special must be one of ${C.specials.join(", ")}`);
    return problems;
}

// ---------- the code panel's window side: what each game's window does around the schema ----------

export function codeCtx(game, {rules, tools = {}, limits, design, who = null, makers = {}}) {  // each window's code_ctx()
    const title = (who ? `${who.toUpperCase()}'S ` : "MY ") + game.word;
    const ctx = {title, points_total: limits.points_total, rules};
    if (game.title === "Robot Lab") {
        ctx.weapons = pyList(pyTruthy(pyGet(tools, "weapons")) ? tools.weapons : rules.weapons);
        ctx.all_weapons = pyList(rules.weapons);
        ctx.house = pyGet(rules, "house", {});
        ctx.model = pyGet(design, "model");
        ctx.makers = makers || {};
    } else if (game.title === "Fight Lab") {
        ctx.design = design;
        ctx.bodies = rules.bodies;
        ctx.bosses = pyGet(rules, "bosses", {});
        ctx.specials = pyList(pyTruthy(pyGet(tools, "specials")) ? tools.specials : rules.specials);
        ctx.all_specials = pyList(rules.specials);
        ctx.styles = pyGet(rules, "styles", {});
        ctx.combo_moves = pyGet(rules, "combo_moves", {});
    } else {
        ctx.design = design;
    }
    return ctx;
}

export function codeAllowed(game, tools, design) {  // what this mission's garage lets the learner change (apply_code's allowed)
    const toolOn = v => pyTruthy(v.tool === null ? true : pyGet(tools, v.tool, true));
    if (game.title === "Robot Lab") {
        return (v, value) => {
            if (v.name === "weapon") {
                return pyTruthy(pyGet(tools, "choose_weapon")) && (pyIn(value, pyList(pyGet(tools, "weapons", [])))
                    || (pyTruthy(pyGet(design, "model")) && pyIn(value, game.consts.house_weapons)));
            }
            return toolOn(v);
        };
    }
    if (game.title === "Fight Lab") {
        return (v, value) => {
            if (v.name === "special") return pyTruthy(pyGet(tools, "choose_special")) && pyIn(value, pyList(pyGet(tools, "specials", [])));
            return toolOn(v);
        };
    }
    return toolOn;
}

export function outsideLimits(game, values, limits, teacher = false) {  // CHANGE 91: each value in the code within the limits
    if (game.client_code_room && !teacher) limits = codeRoom(game, limits);
    const out = [];
    for (const v of varsOf(game)) {
        if (!(v.name in values) || (v.group !== "points" && v.group !== "settings")) continue;
        const rng = pyGet(pyGet(limits, v.group, {}), v.path[v.path.length - 1]);
        const x = values[v.name];
        if (!pyTruthy(rng) || !isNum(x)) continue;
        if (num(x) > num(rng[1])) out.push(`value too high for ${v.name} (most allowed: ${formatG(rng[1])})`);
        else if (num(x) < num(rng[0])) out.push(`value too low for ${v.name} (least allowed: ${formatG(rng[0])})`);
    }
    return out;
}

// APPLY CODE, as each game's window does it (without the window): reads the code, refuses a value past the
// limits, puts the values in the design (it changes the design given) and checks it.
// -> {ok, message, colour, lineno, changed, hidden, codeChanged, codeHack}
export function applyCode(game, design, text, {ctx, tools = {}, limits, teacher = false, viewing = null}) {
    let values;
    try {
        values = parseCode(game, text, ctx);
    } catch (e) {
        if (!(e instanceof ParseError)) throw e;
        return {ok: false, message: `Line ${e.lineno === null ? "None" : e.lineno}: ${e.message}`, colour: "red", lineno: e.lineno};
    }
    if (game.old_name && game.old_name in values) {
        return {ok: false, message: "The code is now one variable a line: press RESET CODE to see it.", colour: "red"};
    }
    const refused = outsideLimits(game, values, limits, teacher);
    if (refused.length) return {ok: false, message: "Unable to compile: " + refused.slice(0, 2).join("; "), colour: "red"};
    const {changed, hidden, problems} = applyValues(game, design, values, ctx, codeAllowed(game, tools, design));
    problems.push(...checkDesign(game, design, limits));
    const build = game.title === "Robot Lab" ? "REBUILD MY ROBOT" : "BUILD";
    return {
        ok: !problems.length, changed, hidden, problems,
        codeChanged: changed.length > 0 && !viewing, codeHack: hidden.length > 0 && !viewing,
        message: problems.length ? "Applied, but: " + problems.slice(0, 3).join("; ")
            : `Applied: the garage shows your changes. Press ${build} to use them.`,
        colour: problems.length ? "orange" : "green",
    };
}

// ---------- the garage's stats readout (each window's update_stats_text) ----------

export function formatF(x, n) {  // f"{x:.nf}": rounded half to even from the exact value, as Python does
    x = num(x);
    if (Number.isNaN(x)) return "nan";
    if (!Number.isFinite(x)) return x > 0 ? "inf" : "-inf";
    const sign = x < 0 || Object.is(x, -0) ? "-" : "";
    let scaled;  // the value times 10^n, rounded, as digits
    if (x === 0) scaled = "0";
    else {
        const {digits, exp} = exactDigits(Math.abs(x));
        const keep = exp + 1 + n;  // (how many of the digits are before the rounding point)
        if (keep < 0) scaled = "0";
        else if (keep >= digits.length) scaled = digits + "0".repeat(keep - digits.length);
        else {
            const k = digits.slice(0, keep), rest = digits.slice(keep);
            const last = k ? Number(k[k.length - 1]) : 0;
            const up = rest[0] > "5" || (rest[0] === "5" && (/[1-9]/.test(rest.slice(1)) || last % 2 === 1));
            scaled = (BigInt(k || "0") + (up ? 1n : 0n)).toString();
        }
    }
    scaled = scaled.padStart(n + 1, "0");
    return sign + (n ? scaled.slice(0, -n) + "." + scaled.slice(-n) : scaled);
}

function moveName(game, style, name) {  // fight_sim.move_name
    const m = (game.consts.style_moves[style] || {})[name];
    return m ? m[0] : name.replace(/_/g, " ");
}

function moveMods(game, style, weapon, name) {  // fight_sim.move_mods: (damage, reach, time) multipliers
    const m = (game.consts.style_moves[style] || {})[name] || ["", 1.0, 1.0, 1.0];
    let [, dmg, reach, time] = m;
    const w = game.consts.weapon_mods[weapon];
    if (w && game.consts.weapon_moves.includes(name)) { dmg *= w[0]; reach *= w[1]; time *= w[2]; }
    return [dmg, reach, time];
}

// The stats readout under the garage's tables: what the points and settings buy, in the window's words ("" when the
// design can't be worked out, as the window leaves it blank)
export function statsText(game, d) {
    try {
        const C = game.consts;
        if (game.title === "Kart Lab") {  // (kart_hud.stats_text, kart_sim.stats_of)
            const [sp, ac, gr] = game.limits.stats.map(k => pyGet(d, k, 33));
            const st = {top: 17.0 + 0.22 * sp, accel: 5.0 + 0.10 * ac, grip: 6.0 + 0.10 * gr, steer: 95.0 + 1.0 * gr};
            const to60 = (60 / 3.6) / Math.max(0.1, st.accel);
            return `Top speed ${formatF(st.top * 3.6, 0)} km/h    0 to 60 km/h in ${formatF(to60, 1)} s\n` +
                `Steering ${formatF(st.steer, 0)} degrees a second    a slide dies in ${formatF(1 / Math.max(0.1, st.grip), 2)} s`;
        }
        const p = d.points, s = d.settings;
        if (game.title === "Robot Lab") {  // (lab_sim.build_stats, lab_client.update_stats_text)
            const size = s.size / 100;
            const grip = 1.2 + 0.035 * p.control, mass = (22 + 0.3 * p.armour) * size ** 2;
            if (!(mass > 0)) return "";  // (as above)
            const weight = (C.standard_mass / mass) ** 0.5;
            const top = (3 + 0.2 * p.speed) * (0.5 + 0.5 * weight);
            const accel = (1.5 + 0.12 * p.speed) * (0.3 + 0.7 * s.acceleration / 100) * weight;
            const st = {push: mass * accel, hold: C.push_grip * grip * mass * 9.81, forward_max: top * s.forward_speed / 100,
                        reverse_max: top * s.reverse_speed / 100, accel,
                        turn_rate: ((60 + 4 * p.control) * s.turn_speed / 100) * (Math.PI / 180) / Math.max(size, 0.5),
                        grip: 1.2 + 0.035 * p.control, self_right: 4.0 - 0.06 * p.control,
                        armour: (50 + 4 * p.armour) * size ** 2, mass: (22 + 0.3 * p.armour) * size ** 2,
                        power: 0.6 + 0.02 * p.attack, flip_strength: p.attack / C.stat_max};
            if ([...Object.values(st)].some(v => typeof v !== "number" || Number.isNaN(v)) || st.accel === 0) return "";
            return `Top speed ${formatF(st.forward_max * 3.6, 0)} km/h forward, ${formatF(st.reverse_max * 3.6, 0)} reverse\n` +
                `0-3 m/s in ${formatF(3 / st.accel, 1)} s    Turn ${formatF(st.turn_rate * 57.3, 0)} deg/s\n` +
                `Armour ${formatF(st.armour, 0)}    Mass ${formatF(st.mass, 0)} kg    Weapon power x${formatF(st.power, 2)}\n` +
                `Self-rights after ${formatF(st.self_right, 1)} s    Grip ${formatF(st.grip, 2)}\n` +
                `Pushes with ${formatF(st.push, 0)} N    Holds against ${formatF(st.hold, 0)} N` +
                (pyGet(d, "weapon") === "wedge" ? `\nFlipper strength ${formatF(st.flip_strength * 100, 0)}%  (100% flips Resident Robots)` : "");
        }
        // Fight Lab (fight_sim.build_stats and stats_text: the readout isn't shown for a boss)
        const [style, weapon] = styleOf(game, d);
        const boss = has(C.bosses, pyGet(d, "model"));
        const size = boss ? 0 : s.size / 100, perk = C.style_movement[style] || {};
        const quick = boss ? 0 : 1.15 - 0.006 * p.speed;
        if (!boss && !(size > 0)) return "";  // (Python stops at a division by nothing, or the root of a negative size)
        const st = boss ? Object.assign({}, C.boss_stats) : {health: (80 + 3 * p.stamina) * size ** 2,
                    damage: (0.6 + 0.02 * p.power) * (1.3 - 0.43 * s.attack_speed / 100),
                    taken: 1.25 - 0.01 * p.defence,
                    walk: (1.6 + 0.05 * p.speed) * s.walk_speed / 100 / size ** 0.5,
                    sidestep: (2.0 + 0.05 * p.speed) * s.sidestep_speed / 100 / size ** 0.5 * (perk.sidestep ?? 1),
                    jump: (3.0 + 0.03 * p.speed) * Math.sqrt(s.jump_height / 100) * (perk.jump ?? 1),
                    attack_time: quick * (1.35 - 0.5 * s.attack_speed / 100) * size ** 0.5,
                    energy_rate: 2 + 0.08 * p.stamina, getup: 1.0 - 0.008 * p.stamina};
        if ([...Object.values(st)].some(v => typeof v !== "number" || Number.isNaN(v))) return "";
        const jumpH = st.jump ** 2 / (2 * C.gravity);
        const name = moveName(game, style, "punch");
        const cap = name ? name[0].toUpperCase() + name.slice(1).toLowerCase() : name;
        return `Health ${formatF(st.health, 0)}    Damage x${formatF(st.damage, 2)}    Takes x${formatF(st.taken, 2)} damage\n` +
            `Walk ${formatF(st.walk, 1)} m/s    Sidestep ${formatF(st.sidestep, 1)} m/s    Jump ${formatF(jumpH, 2)} m high\n` +
            `${cap} comes out in ${formatF(C.punch_startup * st.attack_time * moveMods(game, style, weapon, "punch")[2], 2)} s    ` +
            `Energy +${formatF(st.energy_rate, 1)} a second    Up after ${formatF(st.getup, 1)} s`;
    } catch (e) {
        return "";
    }
}

// whether the garage shows the stats readout (each window's build_garage)
export function showsStats(game, d, tools) {
    if (game.title === "Kart Lab") return pyTruthy(pyGet(tools, "stats_readout", true));
    return pyTruthy(pyGet(tools, "stats_readout")) && !pyTruthy(pyGet(d, "model"));
}

// a garage button (engine.garage.set_var): the variable takes the value, then the game's knock-on rules run
export function setVarAfter(game, name, design, value, ctx) {
    const v = varsOf(game).find(x => x.name === name);
    if (!v) return;
    setVar(v, design, value);
    if (v.after) fn(game, v.after)(design, ctx);
}

// ---------- the garage's tables (engine/garage.py draw(), as data for the page to draw) ----------
export function garageTables(game, design, ctx, tools, limits, {view = false, teacher = false} = {}) {
    const schema = varsOf(game), d = design;
    const visible = v => {
        if (v.unless && fn(game, v.unless)(d)) return false;
        return Boolean(view || teacher || v.always || !v.tool || pyTruthy(pyGet(tools, v.tool)));
    };
    const strings = [], lists = [], points = [], settings = [];
    for (const v of schema.filter(v => v.garage === "strings" && visible(v))) {
        const value = getVar(v, d), row = {name: v.name, kind: v.kind, tool: v.tool, value};
        if (v.kind === "str") row.text = pyStr(pyTruthy(value) ? value : "");
        else row.text = value !== null ? `"${pyStr(value)}"` : v.none_text ? `"${v.none_text}"` : '""';
        if (v.kind === "choice") {
            const allowed = view || teacher || canChange(game, v, tools);
            if (allowed && !(v.fixed && fn(game, v.fixed)(d))) {
                let options = optionsOf(game, v, ctx);
                if (v.optional) options = [null].concat(options);
                row.choose = options.map(o => ({value: o, text: o === null ? v.none_text : pyStr(o).replace(/_/g, " "),
                                                on: pyEq(o, value)}));
                row.perRow = v.per_row;
            } else row.chosenByTeacher = true;
        }
        if (v.describe) row.describe = fn(game, v.describe)(ctx, d) || null;
        if (v.extra) row.extra = v.extra;
        strings.push(row);
    }
    for (const v of schema.filter(v => v.garage === "lists" && visible(v))) {
        const value = getVar(v, d), row = {name: v.name, kind: v.kind, tool: v.tool, value};
        if (v.kind === "rgb") {
            const c = pyList(pyTruthy(value) ? value : [0, 0, 0]);
            row.text = `${v.name}: list = [${pyStr(c[0])}, ${pyStr(c[1])}, ${pyStr(c[2])}]`;
        } else if (v.kind === "words") {
            row.text = `${v.name}: list = ${pyRepr(pyList(pyTruthy(value) ? value : []))}`.replace(/'/g, '"');
            if (v.extra) row.extra = v.extra;
        } else row.text = `${v.name}: list = ${pyStr(value)}`.replace(/'/g, '"');
        lists.push(row);
    }
    const pointVars = schema.filter(v => v.group === "points" && visible(v));
    let used = 0;
    for (const v of pointVars) { const x = getVar(v, d); if (pyTruthy(x)) used += num(x); }
    for (const v of pointVars) {
        const stat = v.path[v.path.length - 1];
        points.push({name: v.name, tool: v.tool, stat, value: getVar(v, d), most: Math.max(1, limits.points[stat][1])});
    }
    for (const v of schema.filter(v => v.group === "settings" && visible(v))) {
        const k = v.path[v.path.length - 1], value = getVar(v, d);
        const [lo, hi] = limits.settings[k];
        settings.push({name: v.name, tool: v.tool, key: k, value, lo, hi, fixed: lo >= hi, text: `${formatG(value)}%`});
    }
    return {strings, lists, settings,
            points: pointVars.length ? {total: limits.points_total, used, over: used > limits.points_total, rows: points} : null};
}
