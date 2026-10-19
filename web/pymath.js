// Python's arithmetic where JavaScript's differs, so a port of a Python step gives Python's numbers to the last bit.
//
// Kart Lab's window and server step a kart with kart/kart_sim.py and round the result to the wire's precision each
// tick; the browser's port (kart_sim.js) must give the same numbers or its prediction drifts from the server's
// truth. Four things differ between the two languages:
//   - % on floats: Python's takes the sign of the divisor (floored), JavaScript's the sign of the dividend;
//   - round(): Python rounds a half to the even neighbour (banker's rounding), Math.round always up;
//   - math.hypot: Python's is its own algorithm (CPython's vector_norm: exact scaling, exact squares, compensated
//     sums and one correction step), Math.hypot is V8's, and the two can differ in the last bit;
//   - math.radians / math.degrees multiply by one constant (pi / 180), where x * Math.PI / 180 rounds twice.
// Everything else the step uses (+ - * /, sqrt, min, max, abs, floor) is IEEE arithmetic and identical.

const F64 = new Float64Array(1);
const U32 = new Uint32Array(F64.buffer);  // (little-endian on every machine a browser runs on: U32[1] is the top)

// Python's float % : the result takes the sign of n (CPython float_rem, line for line)
export function pyMod(a, n) {
    let m = a % n;  // (JavaScript's % is C's fmod)
    if (m) {
        if ((n < 0) !== (m < 0)) m += n;
    } else {
        m = n < 0 ? -0 : 0;  // (copysign(0, n))
    }
    return m;
}

// Python's round(x) to a whole number: a half goes to the even neighbour
export function pyRound(x) {
    if (!Number.isFinite(x)) return x;
    const f = Math.floor(x);
    const d = x - f;  // (exact: x and floor(x) share their high bits)
    if (d > 0.5) return f + 1;
    if (d < 0.5) return f;
    return f % 2 === 0 ? f : f + 1;
}

// math.copysign: the size of x with the sign of y (a negative zero counts as negative)
export function copysign(x, y) {
    const neg = y < 0 || (y === 0 && 1 / y < 0);
    return neg ? -Math.abs(x) : Math.abs(x);
}

const DEG_TO_RAD = Math.PI / 180.0, RAD_TO_DEG = 180.0 / Math.PI;  // (CPython's degToRad and radToDeg)
export function radians(x) { return x * DEG_TO_RAD; }
export function degrees(x) { return x * RAD_TO_DEG; }

// frexp's exponent: x = m * 2**e with 0.5 <= m < 1 (x positive and finite)
function frexpExp(x) {
    F64[0] = x;
    const e = (U32[1] >>> 20) & 0x7ff;
    if (e === 0) return frexpExp(x * 18446744073709551616) - 64;  // (a subnormal: scale up by 2**64 first)
    return e - 1022;
}

// 2**k exactly, for -1022 <= k <= 1023
function pow2(k) {
    U32[1] = (k + 1023) << 20;
    U32[0] = 0;
    return F64[0];
}

// x * y as hi + lo with lo the exact rounding error (Dekker's product with Veltkamp's split: the same lo as
// CPython's fma(x, y, -z) whenever nothing underflows, and a hypot's scaled values never come near that)
const SPLIT = 134217729;  // 2**27 + 1
function twoProd(x, y) {
    const z = x * y;
    let c = SPLIT * x;
    const xh = c - (c - x), xl = x - xh;
    c = SPLIT * y;
    const yh = c - (c - y), yl = y - yh;
    return [z, ((xh * yh - z) + xh * yl + xl * yh) + xl * yl];
}

const DBL_MIN = 2.2250738585072014e-308;

function vectorNorm(vec, max) {
    if (max === Infinity) return max;
    if (Number.isNaN(max)) return NaN;
    if (max === 0 || vec.length <= 1) return max;
    const maxE = frexpExp(max);
    if (maxE < -1023) return DBL_MIN * vectorNorm(vec.map(v => v / DBL_MIN), max / DBL_MIN);
    const scale = pow2(-maxE);
    let csum = 1.0, frac1 = 0.0, frac2 = 0.0;
    for (let x of vec) {
        x *= scale;                         // (lossless)
        const [hi, lo] = twoProd(x, x);     // (lossless)
        const s = csum + hi;                // (dl_fast_sum: lossless)
        frac2 += (csum - s) + hi;
        csum = s;
        frac1 += lo;
    }
    let h = Math.sqrt(csum - 1.0 + (frac1 + frac2));
    const [hi, lo] = twoProd(-h, h);
    const s = csum + hi;
    frac2 += (csum - s) + hi;
    csum = s;
    frac1 += lo;
    const x = csum - 1.0 + (frac1 + frac2);
    h += x / (2.0 * h);                     // (the differential correction)
    return h / scale;
}

// math.hypot(*args): CPython 3.12's, to the last bit
export function hypot(...args) {
    let max = 0, nan = false;
    const vec = args.map(a => {
        const x = Math.abs(a);
        if (Number.isNaN(x)) nan = true;
        if (x > max) max = x;
        return x;
    });
    if (max === Infinity) return Infinity;
    return vectorNorm(vec, nan ? NaN : max);
}

// ---------- sin, cos, exp, atan2 (CHANGE 162) ----------
// The system's sin, cos, exp and atan2 differ between Python (the C library) and each browser in the last bit, so
// the kart step uses these, kart/kart_math.py's twins line for line: musl's algorithms (from Sun's fdlibm: a range
// reduction and a fixed polynomial) with + - * / only, which are IEEE arithmetic and the same everywhere.
const TOINT = 1.5 * 2 ** 52;
const INVPIO2 = 6.36619772367581382433e-01, PIO2_1 = 1.57079632673412561417e+00, PIO2_1T = 6.07710050650619224932e-11;
const PIO4 = 7.85398163397448278999e-01;
const PIO2_2 = 6.07710050630396597660e-11, PIO2_2T = 2.02226624879595063154e-21;
const PIO2_3 = 2.02226624871116645580e-21, PIO2_3T = 8.47842766036889956997e-32;
const S1 = -1.66666666666666324348e-01, S2 = 8.33333333332248946124e-03, S3 = -1.98412698298579493134e-04;
const S4 = 2.75573137070700676789e-06, S5 = -2.50507602534068634195e-08, S6 = 1.58969099521155010221e-10;
const C1 = 4.16666666666666019037e-02, C2 = -1.38888888888741095749e-03, C3 = 2.48015872894767294178e-05;
const C4 = -2.75573143513906633035e-07, C5 = 2.08757232129817482790e-09, C6 = -1.13596475577881948265e-11;

function ksin(x, y) {
    const z = x * x, w = z * z;
    const r = S2 + z * (S3 + z * S4) + z * w * (S5 + z * S6);
    const v = z * x;
    return x - ((z * (0.5 * y - v * r) - y) - v * S1);
}

function kcos(x, y) {
    const z = x * x;
    let w = z * z;
    const r = z * (C1 + z * (C2 + z * C3)) + w * w * (C4 + z * (C5 + z * C6));
    const hz = 0.5 * z;
    w = 1.0 - hz;
    return w + (((1.0 - w) - hz) + (z * r - x * y));
}

function reduce(x) {  // x as n pi/2 + (y0 + y1): [n mod 4, y0, y1]
    if (-PIO4 <= x && x <= PIO4) return [0, x, 0.0];
    const fn = (x * INVPIO2 + TOINT) - TOINT;
    let r = x - fn * PIO2_1, w = fn * PIO2_1T;
    let y0 = r - w;
    const ex = exponent(x);
    if (ex - exponent(y0) > 16) {  // (x near a multiple of pi/2: a second round, good to 118 bits, then a third)
        let t = r;
        w = fn * PIO2_2;
        r = t - w;
        w = fn * PIO2_2T - ((t - r) - w);
        y0 = r - w;
        if (ex - exponent(y0) > 49) {
            t = r;
            w = fn * PIO2_3;
            r = t - w;
            w = fn * PIO2_3T - ((t - r) - w);
            y0 = r - w;
        }
    }
    const y1 = (r - y0) - w;
    return [((fn % 4) + 4) % 4, y0, y1];
}

function exponent(x) {  // the double's exponent field, as C reads it from the bits
    F64[0] = x;
    return (U32[1] >>> 20) & 0x7ff;
}

export function sin(x) {
    if (!Number.isFinite(x)) return NaN;
    const [n, y0, y1] = reduce(x);
    return n === 0 ? ksin(y0, y1) : n === 1 ? kcos(y0, y1) : n === 2 ? -ksin(y0, y1) : -kcos(y0, y1);
}

export function cos(x) {
    if (!Number.isFinite(x)) return NaN;
    const [n, y0, y1] = reduce(x);
    return n === 0 ? kcos(y0, y1) : n === 1 ? -ksin(y0, y1) : n === 2 ? -kcos(y0, y1) : ksin(y0, y1);
}

const LN2HI = 6.93147180369123816490e-01, LN2LO = 1.90821492927058770002e-10, INVLN2 = 1.44269504088896338700e+00;
const P1 = 1.66666666666666019037e-01, P2 = -2.77777777770155933842e-03, P3 = 6.61375632143793436117e-05;
const P4 = -1.65339022054652515390e-06, P5 = 4.13813679705723846039e-08;

export function exp(x) {
    if (Number.isNaN(x)) return x;
    if (x > 709.0 && x > 709.782712893384) return Infinity;
    if (x < -708.0 && x < -745.1332191019411) return 0.0;
    let hi = x, lo = 0.0, k = 0;
    if (Math.abs(x) > 0.5 * LN2HI) {
        k = Math.trunc(INVLN2 * x + (x >= 0 ? 0.5 : -0.5));
        hi = x - k * LN2HI;
        lo = k * LN2LO;
        x = hi - lo;
    } else if (Math.abs(x) < 2 ** -28) {
        return 1.0 + x;
    }
    const xx = x * x;
    const c = x - xx * (P1 + xx * (P2 + xx * (P3 + xx * (P4 + xx * P5))));
    const y = 1.0 + (x * c / (2.0 - c) - lo + hi);
    if (k === 0) return y;
    if (-1021 <= k && k <= 1023) return y * pow2(k);
    const half = Math.floor(k / 2);
    return y * pow2(half) * pow2(k - half);
}

const ATANHI = [4.63647609000806093515e-01, 7.85398163397448278999e-01, 9.82793723247329054082e-01, 1.57079632679489655800e+00];
const ATANLO = [2.26987774529616870924e-17, 3.06161699786838301793e-17, 1.39033110312309984516e-17, 6.12323399573676603587e-17];
const AT = [3.33333333333329318027e-01, -1.99999999998764832476e-01, 1.42857142725034663711e-01, -1.11111104054623557880e-01,
            9.09088713343650656196e-02, -7.69187620504482999495e-02, 6.66107313738753120669e-02, -5.83357013379057348645e-02,
            4.97687799461593236017e-02, -3.65315727442169155270e-02, 1.62858201153657823623e-02];
const PI = 3.1415926535897931160e+00, PI_LO = 1.2246467991473531772e-16;

export function atan(x) {
    if (Number.isNaN(x)) return x;
    const neg = x < 0, ax = neg ? -x : x;
    if (ax >= 2 ** 66) return neg ? -ATANHI[3] : ATANHI[3];
    let i;
    if (ax < 0.4375) {
        if (ax < 2 ** -27) return x;
        i = -1;
    } else if (ax < 1.1875) {
        if (ax < 0.6875) { i = 0; x = (2.0 * ax - 1.0) / (2.0 + ax); } else { i = 1; x = (ax - 1.0) / (ax + 1.0); }
    } else if (ax < 2.4375) {
        i = 2; x = (ax - 1.5) / (1.0 + 1.5 * ax);
    } else {
        i = 3; x = -1.0 / ax;
    }
    let z = x * x;
    const w = z * z;
    const s1 = z * (AT[0] + w * (AT[2] + w * (AT[4] + w * (AT[6] + w * (AT[8] + w * AT[10])))));
    const s2 = w * (AT[1] + w * (AT[3] + w * (AT[5] + w * (AT[7] + w * AT[9]))));
    if (i < 0) return x - x * (s1 + s2);
    z = ATANHI[i] - ((x * (s1 + s2) - ATANLO[i]) - x);
    return neg ? -z : z;
}

const negative = v => v < 0 || (v === 0 && 1 / v < 0);  // (a negative zero counts)

export function atan2(y, x) {
    if (Number.isNaN(x) || Number.isNaN(y)) return x + y;
    if (x === 1.0) return atan(y);
    const m = (negative(y) ? 1 : 0) | (negative(x) ? 2 : 0);
    if (y === 0) return [y, y, PI, -PI][m];
    if (x === 0) return m & 1 ? -PI / 2 : PI / 2;
    const ax = Math.abs(x), ay = Math.abs(y);
    if (ax === Infinity || ay === Infinity) return Math.atan2(y, x);  // (never in a kart's step: the system's)
    let z;
    if (ay > ax * 2 ** 64) z = PI / 2 + 0.5 * PI_LO;
    else if (m & 2 && ay < ax * 2 ** -64) z = 0.0;
    else z = atan(ay / ax);
    if (m === 0) return z;
    if (m === 1) return -z;
    if (m === 2) return PI - (z - PI_LO);
    return (z - PI_LO) - PI;
}
