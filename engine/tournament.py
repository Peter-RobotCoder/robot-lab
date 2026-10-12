"""Tournaments. Both games use them: the server decides when a match is over and moves the fighters on.

Winner stays on (CHANGE 76): a queue of challengers and a few live rings (arenas). The winner of a match
stays in the ring, the loser goes to the back of the queue, and the next challenger comes in. It runs until
the teacher stops it.

    t = WinnerStaysOn(["amy", "ben", "cat", "dan", "eve"], live=2)
    t.current          -> [["amy", "ben", None], ["cat", "dan", None]]   (the live matches: a, b, winner)
    t.record("amy", "ben", "amy")  -> ("ben", "eve")  the loser out, the next challenger in (None: nobody waiting)
    t.summary()        -> what the windows show (the live matches, the queue, wins and streaks)

Knockout: the teacher picks the first round's line-ups (who meets who, in which ring). When every match of the
round is over, the winners meet in the next round (the winner of ring 1 v the winner of ring 2, and so on) until
one is champion. Anyone not in a line-up sits the round out and comes in next round (a bye).

    t = Knockout(["amy", "ben", "cat", "dan", "eve"], [["amy", "ben"], ["cat", "dan"]])
    t.current          -> [["amy", "ben", None], ["cat", "dan", None]]   (round 1; "eve" waits)
    t.record("amy", "ben", "amy"); t.record("cat", "dan", "dan"); t.round_over() -> True
    t.next_round()     -> True: round 2 is [["amy", "dan", None]] and "eve" still waits (an odd one out gets a bye)
    ...until next_round() returns False: t.champion is the last one standing
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


class Knockout:
    kind = "knockout"

    def __init__(self, names, lineups):
        names = [n for n in names if n]
        self.wins = {n: 0 for n in names}
        self.streak = {n: 0 for n in names}
        self.played = 0
        self.round = 1
        self.champion = None
        seen = set()
        self.matches = []      # this round's matches: [a, b, winner or None]
        for pair in lineups:
            a, b = (list(pair) + [None, None])[:2]
            if a and b and a != b and a in self.wins and b in self.wins and a not in seen and b not in seen:
                self.matches.append([a, b, None])
                seen |= {a, b}
        self.queue = [n for n in names if n not in seen]  # (not in a line-up: they wait for the next round)
        self.rounds = [self.matches]  # every round, the current one last (what the windows show)
        self.live = max(1, len(self.matches))

    @property
    def current(self):
        """This round's matches (what the server puts in the rings): nothing once there is a champion."""
        return [] if self.champion else [m for m in self.matches if m[0] and m[1]]

    def title(self, i=None):
        if self.champion:
            return f"CHAMPION: {self.champion}"
        text = f"KNOCKOUT ROUND {self.round}"
        return text if i is None or len(self.current) == 1 else f"{text}  MATCH {i + 1}"

    def join(self, names):
        """Anyone new (a learner who has just come in) waits for the next round."""
        for n in names:
            if n and n not in self.wins:
                self.wins[n] = self.streak[n] = 0
                self.queue.append(n)

    def leave(self, name):
        """Someone has gone: out of the waiting list; in a live match, the other robot goes through."""
        self.queue = [n for n in self.queue if n != name]
        for m in self.matches:
            if name in m[:2] and m[2] is None:
                m[2] = m[1] if m[0] == name else m[0]
        if self.champion == name:
            self.champion = None

    def record(self, a, b, winner):
        """A match of this round is over. Returns None: nobody is swapped in a knockout (see round_over)."""
        for m in self.matches:
            if {m[0], m[1]} == {a, b} and m[2] is None:
                winner = winner if winner in (a, b) else a
                loser = b if winner == a else a
                m[2] = winner
                self.wins[winner] = self.wins.get(winner, 0) + 1
                self.streak[winner] = self.streak.get(winner, 0) + 1
                self.streak[loser] = 0
                self.played += 1
        return None

    def round_over(self):
        return all(m[2] for m in self.matches)

    def next_round(self):
        """The round is over: the winners (and anyone waiting) make the next round's line-ups, in order. Returns
        True when a new round starts, False when the last one standing is the champion (or nobody is left)."""
        through = [m[2] for m in self.matches if m[2]] + self.queue
        through = list(dict.fromkeys(n for n in through if n in self.wins))
        if len(through) < 2:
            self.champion = through[0] if through else None
            self.matches, self.queue = [], []
            return False
        self.round += 1
        self.matches = [[through[i], through[i + 1], None] for i in range(0, len(through) - 1, 2)]
        self.queue = through[len(self.matches) * 2:]  # (an odd one out waits for the round after)
        self.rounds.append(self.matches)
        self.live = max(1, len(self.matches))
        return True

    def table(self):
        return sorted(((n, self.wins[n], self.streak[n]) for n in self.wins), key=lambda r: (-r[1], -r[2], r[0]))

    def summary(self):
        return {"kind": self.kind, "title": self.title(), "champion": self.champion, "round": self.round,
                "rounds": [[list(m) for m in r] for r in self.rounds],
                "live": [[m[0], m[1]] for m in self.current], "queue": list(self.queue), "played": self.played,
                "table": self.table()}
