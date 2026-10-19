"""sin, cos, exp and atan2 for the kart step, the same to the last bit on every computer (CHANGE 162).

Kart Lab's server (Python on the VPS), the windows (Python on Windows) and the page (kart_sim.js in whichever
browser) must step a kart to the same numbers, or the prediction corrects for nothing. +, -, *, / and sqrt are
IEEE arithmetic, rounded the same everywhere; math.sin, math.cos, math.exp and math.atan2 are not: Python calls the
system's C library and each browser has its own, and they can differ in the last bit (rounded to the wire each
tick that's mostly hidden, but a value on the edge of a rounding flips a whole step). These are the C library's
own algorithms (musl's, from Sun's fdlibm: a range reduction and a fixed polynomial) written with + - * / only, in
the same order as their twins in club-coders/web/pymath.js, so both give the same bits by construction. They're
within an ulp or two of the system's (kart_sim_test.py checks both).
"""
import math
import struct

TOINT = 1.5 * 2.0 ** 52  # (x + TOINT - TOINT rounds x to a whole number, halves to even)

# pi / 2 in two parts (the first 33 bits, then the rest): n * PIO2_1 is exact for any n a kart's angle can need
INVPIO2 = 6.36619772367581382433e-01
PIO2_1 = 1.57079632673412561417e+00
PIO2_1T = 6.07710050650619224932e-11
PIO2_2, PIO2_2T = 6.07710050630396597660e-11, 2.02226624879595063154e-21
PIO2_3, PIO2_3T = 2.02226624871116645580e-21, 8.47842766036889956997e-32
PIO4 = 7.85398163397448278999e-01

S1, S2, S3 = -1.66666666666666324348e-01, 8.33333333332248946124e-03, -1.98412698298579493134e-04
S4, S5, S6 = 2.75573137070700676789e-06, -2.50507602534068634195e-08, 1.58969099521155010221e-10
C1, C2, C3 = 4.16666666666666019037e-02, -1.38888888888741095749e-03, 2.48015872894767294178e-05
C4, C5, C6 = -2.75573143513906633035e-07, 2.08757232129817482790e-09, -1.13596475577881948265e-11


def _ksin(x, y):
    """sin(x + y) for |x| <= pi/4, y the tail of the reduced angle."""
    z = x * x
    w = z * z
    r = S2 + z * (S3 + z * S4) + z * w * (S5 + z * S6)
    v = z * x
    return x - ((z * (0.5 * y - v * r) - y) - v * S1)


def _kcos(x, y):
    """cos(x + y) for |x| <= pi/4."""
    z = x * x
    w = z * z
    r = z * (C1 + z * (C2 + z * C3)) + w * w * (C4 + z * (C5 + z * C6))
    hz = 0.5 * z
    w = 1.0 - hz
    return w + (((1.0 - w) - hz) + (z * r - x * y))


def _reduce(x):
    """x as n * pi/2 + (y0 + y1), |y0 + y1| <= pi/4: (n mod 4, y0, y1)."""
    if -PIO4 <= x <= PIO4:
        return 0, x, 0.0
    fn = (x * INVPIO2 + TOINT) - TOINT
    r = x - fn * PIO2_1
    w = fn * PIO2_1T
    y0 = r - w
    ex = _exponent(x)
    if ex - _exponent(y0) > 16:  # (x near a multiple of pi/2: a second round, good to 118 bits, then a third)
        t = r
        w = fn * PIO2_2
        r = t - w
        w = fn * PIO2_2T - ((t - r) - w)
        y0 = r - w
        if ex - _exponent(y0) > 49:
            t = r
            w = fn * PIO2_3
            r = t - w
            w = fn * PIO2_3T - ((t - r) - w)
            y0 = r - w
    y1 = (r - y0) - w
    return int(fn) & 3, y0, y1


def _exponent(x):
    """The double's exponent field, as C reads it from the bits."""
    return (struct.unpack(">Q", struct.pack(">d", x))[0] >> 52) & 0x7FF


def sin(x):
    if x != x or x in (math.inf, -math.inf):
        return math.nan
    n, y0, y1 = _reduce(x)
    if n == 0:
        return _ksin(y0, y1)
    if n == 1:
        return _kcos(y0, y1)
    if n == 2:
        return -_ksin(y0, y1)
    return -_kcos(y0, y1)


def cos(x):
    if x != x or x in (math.inf, -math.inf):
        return math.nan
    n, y0, y1 = _reduce(x)
    if n == 0:
        return _kcos(y0, y1)
    if n == 1:
        return -_ksin(y0, y1)
    if n == 2:
        return -_kcos(y0, y1)
    return _ksin(y0, y1)


LN2HI, LN2LO, INVLN2 = 6.93147180369123816490e-01, 1.90821492927058770002e-10, 1.44269504088896338700e+00
P1, P2, P3 = 1.66666666666666019037e-01, -2.77777777770155933842e-03, 6.61375632143793436117e-05
P4, P5 = -1.65339022054652515390e-06, 4.13813679705723846039e-08


def exp(x):
    if x != x:
        return x
    if x > 709.0:
        return math.inf if x > 709.782712893384 else _exp(x)
    if x < -708.0:
        return 0.0 if x < -745.1332191019411 else _exp(x)
    return _exp(x)


def _exp(x):
    hi, lo, k = x, 0.0, 0
    if abs(x) > 0.5 * LN2HI:  # (x = k ln2 + r, |r| <= ln2 / 2)
        k = int(INVLN2 * x + (0.5 if x >= 0 else -0.5))  # (int() cuts toward zero, as C's (int))
        hi = x - k * LN2HI
        lo = k * LN2LO
        x = hi - lo
    elif abs(x) < 2.0 ** -28:
        return 1.0 + x
    xx = x * x
    c = x - xx * (P1 + xx * (P2 + xx * (P3 + xx * (P4 + xx * P5))))
    y = 1.0 + (x * c / (2.0 - c) - lo + hi)
    if k == 0:
        return y
    if -1021 <= k <= 1023:
        return y * _pow2(k)
    return y * _pow2(k // 2) * _pow2(k - k // 2)  # (near the ends: two exact halves)


def _pow2(k):
    return math.ldexp(1.0, k)  # (2**k exactly)


ATANHI = (4.63647609000806093515e-01, 7.85398163397448278999e-01, 9.82793723247329054082e-01,
          1.57079632679489655800e+00)
ATANLO = (2.26987774529616870924e-17, 3.06161699786838301793e-17, 1.39033110312309984516e-17,
          6.12323399573676603587e-17)
AT = (3.33333333333329318027e-01, -1.99999999998764832476e-01, 1.42857142725034663711e-01,
      -1.11111104054623557880e-01, 9.09088713343650656196e-02, -7.69187620504482999495e-02,
      6.66107313738753120669e-02, -5.83357013379057348645e-02, 4.97687799461593236017e-02,
      -3.65315727442169155270e-02, 1.62858201153657823623e-02)
PI, PI_LO = 3.1415926535897931160e+00, 1.2246467991473531772e-16


def atan(x):
    if x != x:
        return x
    neg = x < 0
    ax = -x if neg else x
    if ax >= 2.0 ** 66:
        z = ATANHI[3]
        return -z if neg else z
    if ax < 0.4375:
        if ax < 2.0 ** -27:
            return x
        i = -1
    elif ax < 1.1875:
        if ax < 0.6875:
            i, x = 0, (2.0 * ax - 1.0) / (2.0 + ax)
        else:
            i, x = 1, (ax - 1.0) / (ax + 1.0)
    elif ax < 2.4375:
        i, x = 2, (ax - 1.5) / (1.0 + 1.5 * ax)
    else:
        i, x = 3, -1.0 / ax
    z = x * x
    w = z * z
    s1 = z * (AT[0] + w * (AT[2] + w * (AT[4] + w * (AT[6] + w * (AT[8] + w * AT[10])))))
    s2 = w * (AT[1] + w * (AT[3] + w * (AT[5] + w * (AT[7] + w * AT[9]))))
    if i < 0:
        return x - x * (s1 + s2)
    z = ATANHI[i] - ((x * (s1 + s2) - ATANLO[i]) - x)
    return -z if neg else z


SPLIT = 134217729.0  # 2**27 + 1
DBL_MIN = 2.2250738585072014e-308


def _two_prod(x, y):
    """x * y as hi + lo, lo the exact rounding error (Dekker's product with Veltkamp's split, as pymath.js)."""
    z = x * y
    c = SPLIT * x
    xh = c - (c - x)
    xl = x - xh
    c = SPLIT * y
    yh = c - (c - y)
    yl = y - yh
    return z, ((xh * yh - z) + xh * yl + xl * yh) + xl * yl


def _vector_norm(vec, most):
    if most == math.inf:
        return most
    if most != most:
        return most
    if most == 0 or len(vec) <= 1:
        return most
    e = math.frexp(most)[1]
    if e < -1023:
        return DBL_MIN * _vector_norm([v / DBL_MIN for v in vec], most / DBL_MIN)
    scale = math.ldexp(1.0, -e)
    csum, frac1, frac2 = 1.0, 0.0, 0.0
    for x in vec:
        x *= scale
        hi, lo = _two_prod(x, x)
        s = csum + hi
        frac2 += (csum - s) + hi
        csum = s
        frac1 += lo
    h = math.sqrt(csum - 1.0 + (frac1 + frac2))
    hi, lo = _two_prod(-h, h)
    s = csum + hi
    frac2 += (csum - s) + hi
    csum = s
    frac1 += lo
    x = csum - 1.0 + (frac1 + frac2)
    h += x / (2.0 * h)
    return h / scale


def hypot(*args):
    """math.hypot as CPython 3.12 does it (pymath.js's hypot, line for line): the step's own copy, so a later
    Python's hypot can't change the numbers."""
    vec, most, nan = [], 0.0, False
    for a in args:
        x = abs(a)
        nan |= x != x
        if x > most:
            most = x
        vec.append(x)
    if most == math.inf:
        return most
    return _vector_norm(vec, math.nan if nan else most)


def _negative(v):  # (a negative zero counts)
    return v < 0 or (v == 0 and math.copysign(1.0, v) < 0)


def atan2(y, x):
    if x != x or y != y:
        return x + y
    if x == 1.0:
        return atan(y)
    m = (1 if _negative(y) else 0) | (2 if _negative(x) else 0)
    if y == 0:
        return (y, y, PI, -PI)[m]
    if x == 0:
        return -PI / 2 if m & 1 else PI / 2
    ax, ay = abs(x), abs(y)
    if ax == math.inf or ay == math.inf:
        return math.atan2(y, x)  # (never in a kart's step: the system's)
    if ay > ax * 2.0 ** 64:
        z = PI / 2 + 0.5 * PI_LO
    elif m & 2 and ay < ax * 2.0 ** -64:
        z = 0.0
    else:
        z = atan(ay / ax)
    if m == 0:
        return z
    if m == 1:
        return -z
    if m == 2:
        return PI - (z - PI_LO)
    return (z - PI_LO) - PI
