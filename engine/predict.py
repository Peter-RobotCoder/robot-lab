"""Client-side prediction plumbing with no game attached: input numbering, replay, visual smoothing, tick lead.

The client applies its own input the moment it is made and sends it numbered; the server applies the same
numbered inputs in order and echoes the last one it used with each snapshot. When the server's state for that
input arrives, the client compares it with what it predicted for that very tick (SuperTuxKart keeps
m_local_state[ticks] for this) and only when they differ does it replace its state and replay the inputs the
server has not seen yet. Corrections never touch the picture directly: the ErrorSmoother carries the visual
difference and fades it over a few frames (Fiedler's state synchronisation, STK's SmoothNetworkBody).

Nothing here knows what a state or an input is: the game supplies step(state, input, dt) and
compare(predicted, server) and keeps states as tuples or small dicts. See reports/Kart engine netcode and
graphics tiers.md, "Predict only the local kart" and "Snap the physics, smooth the picture".

Sequence numbers are u16 and wrap (a 60 Hz race wraps in 18 minutes), so every comparison goes through
seq_after / seq_diff rather than < and -.
"""
import math
from collections import deque

SEQ_MASK = 0xFFFF


def seq_diff(a, b):
    """a - b as a signed distance on the u16 circle (positive when a came after b)."""
    d = (a - b) & SEQ_MASK
    return d - 0x10000 if d >= 0x8000 else d


def seq_after(a, b):
    """True when a was numbered after b (and is not b), allowing for the wrap."""
    return 0 < ((a - b) & SEQ_MASK) < 0x8000


class InputLog:
    """The client's numbered inputs, oldest first, until the server acknowledges them.

    keep is how many of the newest entries trim() always leaves (the two that ride along with each input message
    for redundancy, and the newest itself); max_len stops the log growing while nothing is acknowledged (a stall
    or a reconnect: once the server answers again, the Predictor snaps anyway).
    """

    def __init__(self, first_seq=0, keep=3, max_len=1024):
        self.entries = deque(maxlen=max_len)  # (seq, input, local_t)
        self.next_seq = first_seq & SEQ_MASK
        self.keep = keep

    def add(self, input, local_t=0.0):
        """Number and keep an input; returns its seq."""
        seq = self.next_seq
        self.next_seq = (seq + 1) & SEQ_MASK
        self.entries.append((seq, input, local_t))
        return seq

    def since(self, ack_seq):
        """[(seq, input)] for every input numbered after ack_seq, in order: what a correction replays."""
        return [(s, i) for s, i, _ in self.entries if seq_after(s, ack_seq)]

    def previous(self, n=2):
        """The n inputs logged just before the newest one, most recent first: the redundant copies that go in the
        newest input's message (fewer when the log is that short)."""
        items = list(self.entries)[-(n + 1):-1]
        return [i for _, i, _ in reversed(items)]

    def trim(self, ack_seq):
        """Forget inputs the server has applied (at or before ack_seq), keeping the newest few for redundancy."""
        while len(self.entries) > self.keep and not seq_after(self.entries[0][0], ack_seq):
            self.entries.popleft()

    def newest(self):
        return self.entries[-1][0] if self.entries else None

    def __len__(self):
        return len(self.entries)


class Predictor:
    """Advances the local state with each input and reconciles it with the server's acknowledged state.

    step(state, input, dt) -> state is the game's pure step; states are never looked inside here. A ring of the
    predicted states by seq lets correct() compare the server's state with what was predicted for exactly that
    tick, so a near-deterministic step makes most corrections no-ops and the state is only ever replaced when
    the server really disagrees. After a correction that moved the state, moved_from holds the prediction it
    replaced (the caller works out the visual error from it and hands that to an ErrorSmoother).
    """

    def __init__(self, step, state, ignore=0.05, log=None, ring=256):
        self.step, self.state = step, state
        self.ignore = ignore
        self.log = log if log is not None else InputLog()
        self.ring = ring
        self.predicted = {}  # seq -> the state predicted after applying that input (insertion = seq order)
        self.corrections = 0  # how many times the state was replaced (a diagnostic: ought to stay small)
        self.moved_from = None

    def apply(self, input, dt, local_t=0.0):
        """Log the input, step the state with it and remember the result against its seq; returns the seq."""
        seq = self.log.add(input, local_t)
        self.state = self.step(self.state, input, dt)
        self.predicted[seq] = self.state
        while len(self.predicted) > self.ring:
            del self.predicted[next(iter(self.predicted))]
        return seq

    def correct(self, server_state, ack_seq, dt, compare):
        """Reconcile with the server's state after it applied input ack_seq; returns the error compare() found.

        Below ignore nothing happens. Otherwise the state becomes the server's and the inputs after ack_seq are
        replayed in order, so the prediction is again the server's future with the inputs it has not had yet. An
        ack with no prediction behind it (a reconnect, or one older than the ring) counts as an unbounded error
        and snaps.
        """
        was = self.predicted.get(ack_seq)
        if was is None and self.predicted:  # (CHANGE 175) the server has run more ticks than we have inputs for (a
            newest = next(reversed(self.predicted))  # slow window dropping ticks): compared with our newest instead
            if seq_after(ack_seq, newest) and seq_diff(ack_seq, newest) < 64:
                was = self.predicted[newest]
        err = compare(was, server_state) if was is not None else math.inf
        if err < self.ignore:
            self.moved_from = None
        else:
            self.moved_from = self.state
            self.state = server_state
            for seq, input in self.log.since(ack_seq):
                self.state = self.step(self.state, input, dt)
                self.predicted[seq] = self.state
            self.corrections += 1
        for seq in list(self.predicted):  # (older than the acknowledged tick is of no further use; the tick
            if not seq_after(ack_seq, seq) or len(self.predicted) == 1:  # itself stays, and so does our newest,
                break                        # because the same ack comes again while the server has nothing new of
            del self.predicted[seq]          # ours (or has run past our newest), and that must not look like a reconnect)
        self.log.trim(ack_seq)
        return err


def _blend(lo_at, lo, hi_at, hi, x):
    if x <= lo_at:
        return lo
    if x >= hi_at:
        return hi
    return lo + (hi - lo) * (x - lo_at) / (hi_at - lo_at)


class ErrorSmoother:
    """The visual offset that hides a correction: added to the rendered pose, never to the physics state.

    When a correction moves the state, add() the move (old pose minus new pose) and the picture stays where it
    was; offset(dt) then shrinks it each frame so the picture slides to the truth. Position error decays 0.9 per
    frame at 60 fps, 0.95 when small (<= 0.25 m) and 0.85 when large (>= 1 m), blended between (Fiedler); yaw a
    little slower at 0.92 because a turning kart is the most visible thing on the track. Errors under 0.05 m are
    not worth hiding and over 4 m (or 45 degrees of yaw) the kart was teleported, so both show the truth at once
    (SuperTuxKart's min and max adjust lengths). remove_up drops the vertical part so the wheels stay on the slope.
    Positions are 3-tuples (Panda's z up: index 2); yaw is in radians.
    """

    def __init__(self, ignore=0.05, snap=4.0, snap_yaw=math.radians(45), decay=0.9, decay_small=(0.25, 0.95),
                 decay_large=(1.0, 0.85), yaw_decay=0.92, ignore_yaw=math.radians(0.5), remove_up=False,
                 adaptive=True, up_axis=2):
        self.ignore, self.snap, self.snap_yaw = ignore, snap, snap_yaw
        self.decay, self.decay_small, self.decay_large, self.adaptive = decay, decay_small, decay_large, adaptive
        self.yaw_decay, self.ignore_yaw = yaw_decay, ignore_yaw
        self.remove_up, self.up_axis = remove_up, up_axis
        self.dpos, self.dyaw = (0.0, 0.0, 0.0), 0.0
        self.snaps = 0

    def add(self, dpos, dyaw=0.0):
        """A correction moved the pose by dpos (old minus new) and dyaw: carry it so the picture does not jump.
        A new error during a fade adds to what is left of the old one, so the picture continues from where it is."""
        d = [a + b for a, b in zip(self.dpos, dpos)]
        if self.remove_up and len(d) > self.up_axis:
            d[self.up_axis] = 0.0
        yaw = _wrap_angle(self.dyaw + dyaw)
        if math.hypot(*d) > self.snap or abs(yaw) > self.snap_yaw:
            self.dpos, self.dyaw = tuple(0.0 for _ in d), 0.0
            self.snaps += 1
            return
        self.dpos = tuple(d) if math.hypot(*d) >= self.ignore else tuple(0.0 for _ in d)
        self.dyaw = yaw if abs(yaw) >= self.ignore_yaw else 0.0

    def offset(self, dt):
        """Fade by one frame of dt seconds and return (dpos, dyaw) to add to the rendered pose."""
        length = math.hypot(*self.dpos)
        if length:
            f = _blend(self.decay_small[0], self.decay_small[1], self.decay_large[0], self.decay_large[1],
                       length) if self.adaptive else self.decay
            f **= dt * 60
            d = tuple(a * f for a in self.dpos)
            self.dpos = d if length * f >= self.ignore else tuple(0.0 for _ in d)
        if self.dyaw:
            yaw = self.dyaw * self.yaw_decay ** (dt * 60)
            self.dyaw = yaw if abs(yaw) >= self.ignore_yaw else 0.0
        return self.dpos, self.dyaw

    def clear(self):
        self.dpos, self.dyaw = tuple(0.0 for _ in self.dpos), 0.0


def _wrap_angle(a):
    """a brought into (-pi, pi], so a correction across the seam is a small turn, not a full one."""
    return a - 2 * math.pi * math.floor((a + math.pi) / (2 * math.pi))


class LeadController:
    """Keeps the server's input buffer for this client between one and two ticks deep.

    The server echoes how many of our inputs it holds unapplied. Empty means it had to repeat our last input (the
    Rocket League desync); deep means our inputs wait, adding lag. Rather than repeat or drop, the client runs
    slightly fast or slow: feed() the echoed depth each snapshot and multiply the real time between client ticks
    by multiplier(): under 1 the client ticks more often and fills the buffer, over 1 it ticks less often and
    drains it. An EWMA of the depth means one odd reading cannot jolt the pace, and inside the band the pace is
    exactly 1.0 so a healthy connection is never nudged at all. With an accumulator the use is:
        acc += frame_dt; while acc >= DT * lead.multiplier(): acc -= DT * lead.multiplier(); tick()
    """

    def __init__(self, low=1.0, high=2.0, gain=0.1, limit=0.1, alpha=0.2):
        self.low, self.high, self.gain, self.limit, self.alpha = low, high, gain, limit, alpha
        self.depth = None  # the smoothed depth (None until the first reading)

    def feed(self, buffer_depth):
        """Take the depth the server echoed; returns the multiplier for the next tick."""
        if self.depth is None:
            self.depth = float(buffer_depth)
        else:
            self.depth += self.alpha * (buffer_depth - self.depth)
        return self.multiplier()

    def multiplier(self):
        d = self.depth
        if d is None or self.low <= d <= self.high:
            return 1.0
        m = 1.0 - self.gain * (self.low - d) if d < self.low else 1.0 + self.gain * (d - self.high)
        return min(1.0 + self.limit, max(1.0 - self.limit, m))

    def reset(self):
        self.depth = None


class ServerInputQueue:
    """One player's inputs on the server: numbered, filled from the redundant copies, one applied per tick.

    push() takes a decoded input message (its seq, the input, and prev: the inputs for seq - 1 and seq - 2, most
    recent first) and ignores anything at or before the last applied seq. A hole of up to max_gap is filled from
    prev, so a late or lost message costs nothing; a bigger hole (a reconnect) is skipped rather than waited
    for, because a later message having arrived means the earlier one never will. pop_for_tick() gives the input
    to apply this tick: the next in sequence if it is here, else the last applied again (and counts the repeat,
    which the LeadController on the client is there to make rare). applied is what the snapshot echoes as ack.

    (CHANGE 175) Each number is one tick, on both sides. A dry tick uses up the next number with the last input
    (as Overwatch's, Unity's and Photon's tick-indexed servers run tick T with the last input when T's hasn't come),
    and that input is dropped when it comes late, keeping only its button presses for the next one applied. The
    window predicted that number with its own input, so its prediction is the one to compare with, and a repeated
    tick only corrects it when the keys really changed meanwhile; comparing at the input applied, as before, made
    every dry tick a correction of one tick's movement, and the late inputs then queued for seconds. A window that
    has fallen behind (slow, not late: half a second of its inputs stale with no fresh one) is picked up where it is. Never
    more than max_depth wait (the oldest go; Source caps at 24 ticks), and after idle_after dry ticks the idle
    input is used (a window gone: its kart coasts to a stop).
    """

    def __init__(self, idle=None, max_gap=2, max_depth=12, idle_after=60, merge=None, behind_after=30):
        self.idle, self.max_gap = idle, max_gap
        self.max_depth, self.idle_after, self.behind_after = max_depth, idle_after, behind_after
        self.merge = merge  # merge(late input, next input) -> the next with the late one's presses kept
        self.queue = {}  # seq -> input, all after floor
        self.floor = None  # nothing at or before this seq is accepted: the last applied, or the first seen - 1
        self.applied = None  # the seq of the input applied last (a repeated one counts)
        self.last_input = idle
        self.late = None  # a late input dropped since the last tick (its presses go into the next)
        self.repeats = 0  # ticks with nothing new to apply (buffer ran dry)
        self.skipped = 0  # inputs given up on (holes wider than the redundancy covers, or over max_depth)
        self.dropped = 0  # inputs that came after their tick had been run
        self.dry = 0  # dry ticks in a row
        self.stale_run = 0  # late inputs in a row with no fresh one between (a window behind, not a burst)

    def push(self, seq, input, prev=()):
        """Queue an input; False if it was stale. prev fills the holes just before it."""
        seq &= SEQ_MASK
        if self.floor is None:
            self.floor = (seq - 1) & SEQ_MASK
        elif not seq_after(seq, self.floor):
            self.stale_run += 1
            if self.stale_run > self.behind_after and seq_diff(self.floor, seq) < 600:  # (half a second of nothing
                self.skipped += seq_diff(self.floor, seq)  # but late ones: a window behind, not a burst after a stall:
                self.floor = (seq - 1) & SEQ_MASK            # picked up where it is)
                self.queue.clear()
            else:
                self.dropped += 1
                self.late = input if self.late is None or self.merge is None else self.merge(self.late, input)
                return False
        self.stale_run = 0
        self.queue[seq] = input
        for back, p in enumerate(list(prev)[:self.max_gap], 1):
            s = (seq - back) & SEQ_MASK
            if seq_after(s, self.floor) and s not in self.queue:
                self.queue[s] = p
        while len(self.queue) > self.max_depth:  # (too many waiting: the oldest are given up on)
            oldest = min(self.queue, key=lambda s: seq_diff(s, self.floor))
            del self.queue[oldest]
            self.floor = oldest
            self.skipped += 1
        return True

    def pop_for_tick(self):
        """The input to apply this tick."""
        if self.floor is None:
            return self.last_input  # (nothing from this window yet: no number to use up)
        nxt = (self.floor + 1) & SEQ_MASK
        if not self.queue:
            self.repeats += 1
            self.dry += 1
            self.floor = self.applied = nxt  # (this tick's number, with the last input)
            return self.idle if self.dry > self.idle_after else self.last_input
        self.dry = 0
        if nxt not in self.queue:
            nxt = min(self.queue, key=lambda s: seq_diff(s, self.floor))
            self.skipped += seq_diff(nxt, self.floor) - 1
        inp = self.queue.pop(nxt)
        if self.late is not None:  # (a late input's presses: kept, not lost)
            if self.merge is not None:
                inp = self.merge(self.late, inp)
            self.late = None
        self.last_input = inp
        self.floor = self.applied = nxt
        return inp

    def drain(self):
        """While the game is paused: nothing is applied, so everything waiting goes (the newest kept as the last
        input) and the numbering stays level with the window's, which sends nothing while paused."""
        if self.queue:
            newest = max(self.queue, key=lambda s: seq_diff(s, self.floor))
            self.last_input = self.queue[newest]
            self.floor = self.applied = newest
            self.queue.clear()
        self.late = None
        self.dry = 0

    def ack(self):
        """What the snapshot echoes (0 before any input)."""
        return 0 if self.applied is None else self.applied

    def depth(self):
        """How many inputs wait unapplied (echoed to the client for its LeadController)."""
        return len(self.queue)
