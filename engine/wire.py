"""Compact binary frames for the games' fast traffic: snapshots down, inputs up.

A JSON snapshot of 8 karts is about 1.2 kB and takes a laptop 78 µs to decode every tick; the same state as a
struct is under 200 bytes and decodes in a few µs (see reports/Kart engine netcode and graphics tiers.md). Every
number crosses the wire as a scaled integer (centimetres, yaw × 10,000...), and both ends round their own state
to that precision each tick, so the client's prediction and the server's truth start from identical numbers and
a correction is only ever a real difference, not quantisation noise.

Every binary frame starts with one kind byte so a receiver can route it without parsing:
    1 = snapshot (server to client), 2 = input (client to server), 3 = event (tick-stamped impulses etc.).
Slow traffic (hello, chat, lesson messages) stays JSON on the same socket; a text frame has no kind byte.

Only struct is used: this module must import on the client, the server and in tests without anything installed.
"""
import struct

KIND_SNAPSHOT, KIND_INPUT, KIND_EVENT = 1, 2, 3

# the struct codes a field may use, and the range each can hold (values are clamped into it, never refused:
# a kart 30 km off the track is the game's problem, a dropped connection would be ours)
_LIMITS = {"b": (-128, 127), "B": (0, 255), "h": (-32768, 32767), "H": (0, 65535),
           "i": (-2147483648, 2147483647), "I": (0, 4294967295)}


def kind_of(data):
    """The kind byte of a binary frame (0 for an empty one), so a receiver can route it."""
    return data[0] if data else 0


class Schema:
    """The named fields of one wire record: (name, struct code, scale), in wire order.

    A value v goes on the wire as round(v * scale) clamped to the code's range, and comes back as that integer
    divided by the scale (an int when the scale is 1, so flags and counters stay ints). quantise() does the round
    trip without the bytes: the server calls it on its own state each tick, the client on its prediction.
    """

    def __init__(self, name, fields):
        self.name = name
        self.fields = [(n, c, s) for n, c, s in fields]
        for n, c, s in self.fields:
            if c not in _LIMITS:
                raise ValueError(f"{name}.{n}: struct code {c!r} is not one of {''.join(_LIMITS)}")
            if not s or s < 0:
                raise ValueError(f"{name}.{n}: the scale must be positive")
        self.names = [n for n, _, _ in self.fields]
        self.format = "<" + "".join(c for _, c, _ in self.fields)
        self.struct = struct.Struct(self.format)
        self.size = self.struct.size
        self._quant = [(n, s) + _LIMITS[c] for n, c, s in self.fields]
        self._scales = [(n, s) for n, _, s in self.fields]
        self._scaled = [(n, s) for n, _, s in self.fields if s != 1]
        self._count = len(self.fields)
        self._id_names = ["id"] + self.names  # a snapshot record's keys, in wire order
        self._frames = {}  # snapshot frame structs by entity count (built once each: one pack call per frame)

    def ints(self, values, out=None):
        """The record's fields as the integers that go on the wire (a missing field is 0), appended to out."""
        out = [] if out is None else out
        get = values.get
        for name, scale, lo, hi in self._quant:
            v = round(get(name, 0) * scale)
            out.append(lo if v < lo else hi if v > hi else v)
        return out

    def raw(self, values):
        """ints() without the clamp: the fast path, since struct itself refuses an out-of-range value and the
        packer then falls back to ints()."""
        get = values.get
        return [round(get(n, 0) * s) for n, s in self._scales]

    def values(self, ints, offset=0):
        """A record dict from the wire integers starting at ints[offset] (the reverse of ints())."""
        d = dict(zip(self.names, ints[offset:offset + self._count]))
        for name, scale in self._scaled:
            d[name] /= scale
        return d

    def pack(self, values):
        try:
            return self.struct.pack(*self.raw(values))
        except struct.error:
            return self.struct.pack(*self.ints(values))

    def unpack(self, data, offset=0):
        return self.values(self.struct.unpack_from(data, offset))

    def quantise(self, values):
        """The values as they will be after a trip over the wire (rounded to its precision, clamped to its range)."""
        return self.values(self.ints(values))

    def frame(self, count):
        """The struct of a whole snapshot frame holding count records: kind, header, ack, then id + record each."""
        s = self._frames.get(count)
        if s is None:
            s = self._frames[count] = struct.Struct("<BIHBBH" + ("B" + self.format[1:]) * count)
        return s


# the snapshot header after the kind byte: server_ms u32, seq u16, count u8, flags u8, then the ack u16
_HEAD = struct.Struct("<IHBBH")
SNAPSHOT_OVERHEAD = 1 + _HEAD.size  # 11 bytes before the first record


def pack_snapshot(schema, server_ms, seq, entities, ack=0, flags=0):
    """One snapshot frame: every entity's record (each a dict with an "id" 0-255) in one struct call.

    server_ms comes from the tick counter, not the clock, so it is perfectly regular; ack is the last input seq
    the server applied for this client (each client gets its own frame when it differs); flags are the race state.
    """
    count = len(entities)
    if count > 255:
        raise ValueError("a snapshot holds at most 255 entities")
    head = [KIND_SNAPSHOT, server_ms & 0xFFFFFFFF, seq & 0xFFFF, count, flags & 0xFF, ack & 0xFFFF]
    vals = list(head)
    for e in entities:
        vals.append(e["id"] & 0xFF)
        vals += schema.raw(e)
    try:
        return schema.frame(count).pack(*vals)
    except struct.error:  # something out of range: the slow path clamps every field
        vals = head
        for e in entities:
            vals.append(e["id"] & 0xFF)
            schema.ints(e, vals)
        return schema.frame(count).pack(*vals)


def unpack_snapshot(schema, data):
    """The snapshot frame as a dict: sm (server_ms), seq, ack, flags and entities (record dicts with "id")."""
    if kind_of(data) != KIND_SNAPSHOT:
        raise ValueError("not a snapshot frame")
    sm, seq, count, flags, ack = _HEAD.unpack_from(data, 1)
    try:
        ints = schema.frame(count).unpack(data)
    except struct.error:
        raise ValueError(f"snapshot of {count} {schema.name}s should be {schema.frame(count).size} bytes, "
                         f"got {len(data)}") from None
    names, scaled, entities = schema._id_names, schema._scaled, []
    stride = len(names)
    for base in range(6, 6 + count * stride, stride):  # (one dict(zip()) per entity: the decode runs every tick)
        d = dict(zip(names, ints[base:base + stride]))
        for name, scale in scaled:
            d[name] /= scale
        entities.append(d)
    return {"sm": sm, "seq": seq, "ack": ack, "flags": flags, "entities": entities}


# an input: kind, then <HHIbbB> (seq, ack of snapshot, client_ms, throttle, steer, buttons: 11 bytes, not the 10
# the report counts), then the previous two inputs' throttle, steer, buttons so one lost or late message leaves
# no hole in the server's queue
_INPUT = struct.Struct("<BHHIbbBbbBbbB")
INPUT_SIZE = _INPUT.size  # 18
_NO_INPUT = (0, 0, 0)


def _i8(v):
    v = round(v * 100)
    return -128 if v < -128 else 127 if v > 127 else v


def _u8(v):
    v = int(v)
    return 0 if v < 0 else 255 if v > 255 else v


def quantise_input(throttle, steer, buttons=0):
    """(throttle, steer, buttons) as the server will see them: the client applies these, not what the pedal read,
    so its prediction uses the very numbers the server will."""
    return _i8(throttle) / 100, _i8(steer) / 100, _u8(buttons)


def pack_input(seq, snap_seq, client_ms, throttle, steer, buttons, previous=()):
    """One input frame. previous holds up to two (throttle, steer, buttons) tuples, the most recent first (the
    inputs for seq - 1 and seq - 2); missing ones go as zeros."""
    prev = list(previous)[:2]
    prev += [_NO_INPUT] * (2 - len(prev))
    return _INPUT.pack(KIND_INPUT, seq & 0xFFFF, snap_seq & 0xFFFF, client_ms & 0xFFFFFFFF,
                       _i8(throttle), _i8(steer), _u8(buttons),
                       _i8(prev[0][0]), _i8(prev[0][1]), _u8(prev[0][2]),
                       _i8(prev[1][0]), _i8(prev[1][1]), _u8(prev[1][2]))


def unpack_input(data):
    """The input frame as a dict: seq, ack (snapshot seq the client had seen), cms (client_ms), throttle, steer,
    buttons, and prev, the two earlier (throttle, steer, buttons) tuples for seq - 1 and seq - 2."""
    if kind_of(data) != KIND_INPUT:
        raise ValueError("not an input frame")
    try:
        _, seq, ack, cms, t, s, b, t1, s1, b1, t2, s2, b2 = _INPUT.unpack(data)
    except struct.error:
        raise ValueError(f"an input frame is {INPUT_SIZE} bytes, got {len(data)}") from None
    return {"seq": seq, "ack": ack, "cms": cms, "throttle": t / 100, "steer": s / 100, "buttons": b,
            "prev": [(t1 / 100, s1 / 100, b1), (t2 / 100, s2 / 100, b2)]}
