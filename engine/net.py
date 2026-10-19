"""Connection to the class server, shared by every game's window.

Messages are JSON, except state snapshots in binary (engine.wire), which arrive as {"type": "binary", "data": ...}
for the game to unpack. Every message is stamped with the time it arrived (engine.interp.RECEIVED, from
time.perf_counter(): on Windows time.monotonic() only moves every 15.6 ms on Python 3.12, which is too coarse).

Testing on one laptop: the environment variable CLUBCODERS_LAG makes the connection behave like a school Wi-Fi link:
    CLUBCODERS_LAG=60            60 ms each way
    CLUBCODERS_LAG=60,15         ...with up to 15 ms of jitter
    CLUBCODERS_LAG=60,15,0.02    ...and a 2% chance per message of a 200 ms stall (the messages behind it queue
                                 up and arrive together, as they do on a real link when a packet is lost)
"""
import atexit
import heapq
import json
import os
import queue
import random
import threading
import time

from websockets.sync.client import connect

RECEIVED = "_rx"
# The connection's settings. A game may change them before it connects (the kart game turns compression off:
# its snapshots are binary and already small, and deflate only makes them bigger).
OPTIONS = {"compression": "deflate", "max_queue": 8, "ping_interval": 5, "ping_timeout": 10, "open_timeout": 5}
STALL_SECONDS = 0.2


def lag_settings(text=None):
    """(lag, jitter, stall chance) from CLUBCODERS_LAG, or None when it isn't set."""
    text = os.environ.get("CLUBCODERS_LAG", "") if text is None else text
    if not text.strip():
        return None
    parts = [p.strip() for p in text.split(",")]
    try:
        lag = float(parts[0]) / 1000
        jitter = float(parts[1]) / 1000 if len(parts) > 1 else 0.0
        stall = float(parts[2]) if len(parts) > 2 else 0.0
    except ValueError:
        return None
    return lag, jitter, stall


class Delay:
    """A queue that hands things on after a pretend network delay, keeping their order (as TCP does: a message held
    up holds up everything behind it)."""

    def __init__(self, lag, jitter, stall, deliver):
        self.lag, self.jitter, self.stall, self.deliver = lag, jitter, stall, deliver
        self.heap, self.lock, self.wake = [], threading.Lock(), threading.Event()
        self.last_at, self.n = 0.0, 0
        threading.Thread(target=self._run, daemon=True).start()

    def put(self, item):
        at = time.perf_counter() + self.lag + random.random() * self.jitter
        if self.stall and random.random() < self.stall:
            at += STALL_SECONDS
        at = max(at, self.last_at)  # (never overtakes what was sent before)
        self.last_at = at
        with self.lock:
            heapq.heappush(self.heap, (at, self.n, item))
            self.n += 1
        self.wake.set()

    def _run(self):
        while True:
            with self.lock:
                head = self.heap[0] if self.heap else None
            if head is None:
                self.wake.wait()
                self.wake.clear()
                continue
            wait = head[0] - time.perf_counter()
            if wait > 0:
                self.wake.wait(wait)
                self.wake.clear()
                continue
            with self.lock:
                _, _, item = heapq.heappop(self.heap)
            self.deliver(item)


class Net:
    """Background thread that receives server messages into a queue."""

    def __init__(self, url, name, code, **hello_extra):
        self.url, self.hello = url, {"type": "hello", "name": name, "code": code, **hello_extra}
        self.inbox = queue.Queue()
        self.bytes_in = 0
        self.lag = lag_settings()
        self.delay_in = self.delay_out = None
        if self.lag:
            print(f"Pretend network: {self.lag[0] * 1000:.0f} ms each way, {self.lag[1] * 1000:.0f} ms jitter, "
                  f"{self.lag[2] * 100:.0f}% stalls (CLUBCODERS_LAG)", flush=True)
            self.delay_in = Delay(*self.lag, self._arrive_late)
            self.delay_out = Delay(*self.lag, self._send_now)
        self._connect()
        atexit.register(self.goodbye)

    def goodbye(self):
        """(CHANGE 164) The window closing on purpose says so (close code 1000): the server lets its place go at
        once. A connection that just stops (a lid shut, the Wi-Fi gone) keeps the place a while (engine.seats)."""
        try:
            self.ws.close_timeout = 0.5
            self.ws.close(1000, "window closed")
        except Exception:
            pass

    def _connect(self):
        # entered by hand: the connection lives as long as the game
        self.ws = connect(self.url, **OPTIONS).__enter__()
        self.ws.send(json.dumps(self.hello))
        threading.Thread(target=self._recv, args=(self.ws,), daemon=True).start()

    def reconnect(self):
        """Try to connect again with the same details (after a dropped connection). True if it worked."""
        try:
            self._connect()
            return True
        except Exception:
            return False

    def _deliver(self, m):
        (self.delay_in.put if self.delay_in else self.inbox.put)(m)

    def _arrive_late(self, m):
        """A message out of the pretend network: it "arrived" now, not when the real socket had it."""
        m[RECEIVED] = time.perf_counter()
        self.inbox.put(m)

    def _recv(self, ws):
        try:
            for raw in ws:
                self.bytes_in += len(raw)
                if isinstance(raw, bytes):
                    m = {"type": "binary", "data": raw}
                else:
                    m = json.loads(raw)
                m[RECEIVED] = time.perf_counter()
                self._deliver(m)
            reason, code = "", None
        except Exception as e:
            rcvd = getattr(e, "rcvd", None)
            reason, code = (rcvd.reason, rcvd.code) if rcvd else ("", None)
        if ws is self.ws:  # (an old connection closing after a reconnect doesn't count)
            rcvd = getattr(getattr(ws, "protocol", None), "close_rcvd", None)
            if rcvd and not reason:
                reason, code = rcvd.reason, rcvd.code
            self._deliver({"type": "closed", "reason": reason, "code": code, RECEIVED: time.perf_counter()})

    def _send_now(self, data):
        try:
            self.ws.send(data)
        except Exception:
            pass

    def send(self, msg):
        """A message to the server: a dict (sent as JSON) or bytes (sent as a binary frame)."""
        data = msg if isinstance(msg, (bytes, bytearray)) else json.dumps(msg, separators=(",", ":"))
        (self.delay_out.put if self.delay_out else self._send_now)(data)

    def latency(self):
        """The round trip the connection last measured with its own keepalive ping (seconds), or None."""
        try:
            return self.ws.latency or None
        except Exception:
            return None
