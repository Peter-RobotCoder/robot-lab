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
