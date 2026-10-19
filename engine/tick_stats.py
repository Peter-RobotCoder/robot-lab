"""How a game server's physics loop is keeping time, logged every 10 s while anyone is connected (CHANGE 160).

When a class says "it's laggy", the server's log says whether the server was the reason: each line has the physics
step's work time (median, 99th percentile, worst, in ms), how late the steps started, the steps skipped after a
stall, Python's garbage collection (how many passes and the longest), and each window's bytes a second and the
snapshots dropped for it (a slow window). The 60 Hz step has 16.7 ms; with four game servers on two processors the
99th percentile should stay under about 7 ms (40%).

Also start_up(): gc.freeze() once the server has loaded, so the garbage collector no longer walks everything made
at start-up (the models, the lessons, the tracks) on every full pass.
"""
import gc
import time

EVERY = 10.0


def start_up():
    gc.collect()
    gc.freeze()


class TickStats:
    def __init__(self, name):
        self.name = name
        self.work, self.late = [], []
        self.skipped = 0
        self.gc_runs, self.gc_worst, self._gc_start = 0, 0.0, None
        self.next_report = time.perf_counter() + EVERY
        gc.callbacks.append(self._gc)

    def _gc(self, phase, info):
        if phase == "start":
            self._gc_start = time.perf_counter()
        elif self._gc_start is not None:
            self.gc_runs += 1
            self.gc_worst = max(self.gc_worst, time.perf_counter() - self._gc_start)
            self._gc_start = None

    def step(self, work, late):
        """One physics step: its work time and how late it started (seconds)."""
        self.work.append(work)
        self.late.append(late)

    def skip(self, steps):
        self.skipped += steps

    def due(self):
        return time.perf_counter() >= self.next_report

    def report(self, outboxes=None, names=None):
        """The line for the log (and the counts start again). names: websocket -> who, for the bytes per window."""
        now = time.perf_counter()
        seconds = EVERY + (now - self.next_report)
        self.next_report = now + EVERY
        work, late = sorted(self.work), sorted(self.late)
        self.work, self.late = [], []

        def pc(values, q):
            return values[min(len(values) - 1, int(q * len(values)))] * 1000 if values else 0.0
        line = (f"[ticks] {self.name}: {len(work)} steps, work {pc(work, 0.5):.2f}/{pc(work, 0.99):.2f}/"
                f"{pc(work, 1.0):.1f} ms (median/99%/worst), late {pc(late, 0.5):.1f}/{pc(late, 0.99):.1f}/"
                f"{pc(late, 1.0):.0f} ms, skipped {self.skipped}, gc {self.gc_runs} (worst {self.gc_worst * 1000:.1f} ms)")
        self.skipped, self.gc_runs, self.gc_worst = 0, 0, 0.0
        if outboxes is not None:
            parts = []
            for ws, box in list(outboxes.boxes.items()):
                who = (names or {}).get(ws, "?")
                parts.append(f"{who} {box.sent_bytes / seconds / 1000:.1f} kB/s" +
                             (f" ({box.dropped} dropped)" if box.dropped else ""))
                box.sent_bytes, box.dropped = 0, 0
            if parts:
                line += "; " + ", ".join(parts)
        return line
