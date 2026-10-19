"""A pretend bad network between a page (or a window) and a game server, for the tests (CHANGE 165).

    python engine/fault_relay.py LISTEN_PORT SERVER_PORT [--lag 80] [--jitter 40] [--stall 0.02] [--seed 1]

Every message either way waits lag ms, plus up to jitter ms more, and now and then (stall: the chance a second) the
link stops for 300 to 900 ms and then lets everything through at once, as school Wi-Fi does. A WebSocket runs over
TCP, so nothing is lost or reordered: things arrive late and in bunches. Seeded, so a test run is the same every
time. Chrome's own network throttling can't do this to a WebSocket (its packet loss and reordering are for WebRTC
only), and the windows' CLUBCODERS_LAG is inside the window. Also run_relay() for a test to start one in a thread.
"""
import argparse
import asyncio
import random
import threading
import time

import websockets


class Link:
    """One direction of one connection: messages released in order, each no earlier than its time."""

    def __init__(self, rng, lag, jitter, stall):
        self.rng, self.lag, self.jitter, self.stall = rng, lag / 1000, jitter / 1000, stall
        self.queue = asyncio.Queue()
        self.last = 0.0
        self.stalled_until = 0.0
        self.next_stall_check = time.monotonic()

    def put(self, msg):
        now = time.monotonic()
        if now >= self.next_stall_check:  # (once a second: does the link stop now?)
            self.next_stall_check = now + 1.0
            if self.rng.random() < self.stall:
                self.stalled_until = now + self.rng.uniform(0.3, 0.9)
        due = max(now + self.lag + self.rng.random() * self.jitter, self.stalled_until, self.last)
        self.last = due
        self.queue.put_nowait((due, msg))

    async def pump(self, ws):
        while True:
            due, msg = await self.queue.get()
            wait = due - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            await ws.send(msg)


async def relay(listen_port, server_port, lag=80, jitter=40, stall=0.02, seed=1, ready=None):
    counter = [0]

    async def handle(client):
        counter[0] += 1
        rng = random.Random(seed * 1000 + counter[0])
        async with websockets.connect(f"ws://127.0.0.1:{server_port}", max_size=None, compression=None,
                                      ping_interval=None) as upstream:
            up, down = Link(rng, lag, jitter, stall), Link(rng, lag, jitter, stall)

            async def read(src, link):
                async for msg in src:
                    link.put(msg)
            tasks = [asyncio.ensure_future(t) for t in (read(client, up), read(upstream, down), up.pump(upstream),
                                                        down.pump(client))]
            try:
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for t in tasks:
                    t.cancel()

    async with websockets.serve(handle, "127.0.0.1", listen_port, max_size=None, compression=None, ping_interval=None):
        if ready is not None:
            ready.set()
        await asyncio.Future()


def run_relay(listen_port, server_port, **opts):
    """Start a relay in a background thread (it lasts as long as the test)."""
    ready = threading.Event()
    threading.Thread(target=lambda: asyncio.run(relay(listen_port, server_port, ready=ready, **opts)),
                     daemon=True).start()
    ready.wait(10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("listen", type=int)
    ap.add_argument("server", type=int)
    ap.add_argument("--lag", type=float, default=80)
    ap.add_argument("--jitter", type=float, default=40)
    ap.add_argument("--stall", type=float, default=0.02)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    print(f"Pretend network on {a.listen} to the server on {a.server}: {a.lag:.0f} ms, jitter {a.jitter:.0f} ms, "
          f"stalls {a.stall * 100:.0f}% a second")
    asyncio.run(relay(a.listen, a.server, a.lag, a.jitter, a.stall, a.seed))


if __name__ == "__main__":
    main()
