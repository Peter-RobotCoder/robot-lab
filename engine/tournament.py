"""Winner stays on (CHANGE 76): a queue of challengers and a few live rings (arenas). The winner of a match
stays in the ring, the loser goes to the back of the queue, and the next challenger comes in. It runs until
the teacher stops it. Both games use it: the server decides when a match is over and swaps the fighters.

    t = WinnerStaysOn(["amy", "ben", "cat", "dan", "eve"], live=2)
    t.current          -> [["amy", "ben", None], ["cat", "dan", None]]   (the live matches: a, b, winner)
    t.record("amy", "ben", "amy")  -> ("ben", "eve")  the loser out, the next challenger in (None: nobody waiting)
    t.summary()        -> what the windows show (the live matches, the queue, wins and streaks)
"""
import random


class WinnerStaysOn:
    kind = "stays"

    def __init__(self, names, live=2, shuffle=True):
        names = [n for n in names if n]
        if shuffle:
            random.shuffle(names)
        self.live = max(1, min(int(live), max(1, len(names) // 2)))
        self.queue = list(names)
        self.matches = []        # one a live ring: [a, b, None]; a slot is None while nobody is free to fill it
        self.wins = {n: 0 for n in names}
        self.streak = {n: 0 for n in names}
        self.played = 0
        self.champion = None     # (it never ends by itself: the teacher stops it)
        for _ in range(self.live):
            self.matches.append([self.queue.pop(0) if self.queue else None, self.queue.pop(0) if self.queue else None,
                                 None])

    @property
    def current(self):
        """The live matches with two fighters (what the server puts in the rings)."""
        return [m for m in self.matches if m[0] and m[1]]

    def title(self, i=None):
        return "WINNER STAYS ON" if i is None or len(self.current) == 1 else f"WINNER STAYS ON {i + 1}"

    def join(self, names):
        """Anyone new (a learner who has just come in) joins the back of the queue."""
        for n in names:
            if n and n not in self.wins:
                self.wins[n] = self.streak[n] = 0
                self.queue.append(n)
        self.fill()

    def leave(self, name):
        """Someone has gone (deleted, or disconnected for good): out of the queue and any live match."""
        self.queue = [n for n in self.queue if n != name]
        for m in self.matches:
            for k in (0, 1):
                if m[k] == name:
                    m[k] = None
        self.fill()

    def fill(self):
        """Empty slots in the live matches take the next challengers."""
        for m in self.matches:
            for k in (0, 1):
                if m[k] is None and self.queue:
                    m[k] = self.queue.pop(0)

    def record(self, a, b, winner):
        """A live match is over: the winner stays, the loser goes to the back of the queue and the next
        challenger takes their place. Returns (loser, challenger), or None if this wasn't a live match."""
        for m in self.matches:
            if {m[0], m[1]} == {a, b}:
                loser = b if winner == a else a
                self.wins[winner] = self.wins.get(winner, 0) + 1
                self.streak[winner] = self.streak.get(winner, 0) + 1
                self.streak[loser] = 0
                self.played += 1
                self.queue.append(loser)
                challenger = self.queue.pop(0)  # (with nobody else waiting, the loser comes straight back)
                m[0], m[1] = winner, challenger
                return loser, challenger
        return None

    def table(self):
        """Everyone, best first: (name, wins, streak)."""
        return sorted(((n, self.wins[n], self.streak[n]) for n in self.wins), key=lambda r: (-r[1], -r[2], r[0]))

    def summary(self):
        return {"kind": self.kind, "title": self.title(), "champion": None, "rounds": [],
                "live": [[m[0], m[1]] for m in self.matches], "queue": list(self.queue), "played": self.played,
                "table": self.table()}
