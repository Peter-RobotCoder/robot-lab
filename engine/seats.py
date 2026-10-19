"""A learner's place kept for a while when their connection drops (CHANGE 164).

A laptop lid shut, a Chromebook asleep, the Wi-Fi gone for a moment: the connection ends without the window saying
goodbye (no close frame). Before, the server took the learner's kart, robot or fighter away at once (Kart Lab and
Robot Lab rebuilt the race or the arena, Fight Lab the rings: everyone's started again); and when the page or the
window reconnected by itself a moment later, they were somewhere new. Now their place is held for HOLD_SECONDS
(Colyseus' allowReconnection, Nakama's reserved seat): their kart races on driven by the computer, their robot stands
still, the computer fights for their fighter, and when they log in again they're given it back where it is. A
window or page that closes on purpose says goodbye (close code 1000) and the place goes as before.
"""
import os
import time

HOLD_SECONDS = float(os.environ.get("CLUBCODERS_SEAT_SECONDS", 45.0))  # (the tests shorten it)


def dropped(ws):
    """True if the connection ended without a close frame from the other end (lost, not left)."""
    protocol = getattr(ws, "protocol", None)
    return protocol is not None and getattr(protocol, "close_rcvd", None) is None


class Seats:
    def __init__(self, seconds=HOLD_SECONDS):
        self.seconds = seconds
        self.held = {}  # slug -> [player, until (time.monotonic)]

    def hold(self, slug, player):
        self.held[slug] = [player, time.monotonic() + self.seconds]

    def take(self, slug):
        """The held player of that name (their place back), or None."""
        got = self.held.pop(slug, None)
        return got[0] if got else None

    def players(self):
        return [p for p, _ in self.held.values()]

    def holding(self, player):
        return any(p is player for p, _ in self.held.values())

    def expired(self):
        """The players whose time is up (no longer held)."""
        now = time.monotonic()
        gone = [slug for slug, (_, until) in self.held.items() if until <= now]
        return [self.held.pop(slug)[0] for slug in gone]

    def clear(self):
        """Everyone held let go (a new session, the teacher's Stop): their players."""
        out = self.players()
        self.held.clear()
        return out
