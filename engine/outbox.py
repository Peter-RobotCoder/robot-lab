"""Each connection's messages, sent by its own task, so a game server's loops never wait for one slow window
(CHANGE 160).

The websockets library makes a send wait while more than 32 KB is waiting to go out to that window. A server
loop that awaits every window's send in turn then waits for the slowest: one laptop with its lid half shut, or in
a weak Wi-Fi corner, held up every other learner's game (engine/stall_test.py). Here a server puts a message in the
window's Outbox and carries on; the Outbox's task sends them in order. A snapshot is put with a key ("state"): one
not yet sent is dropped for the newer (only the newest matters), so a slow window gets fewer snapshots, never an
ever-longer queue of old ones. A window so far behind that its queue still grows past MOST is cut off (the page and
the windows reconnect by themselves).
"""
import asyncio
from collections import deque

import websockets

MOST = 400  # messages waiting (keyed ones are only ever one each): more than this, the window has stopped reading


class Outbox:
    def __init__(self, ws, most=MOST):
        self.ws, self.most = ws, most
        self.items = deque()  # (data, key): key None for a message that must arrive, else the kind that's replaced
        self.wake = asyncio.Event()
        self.dropped = 0  # snapshots replaced before they were sent (a slow window)
        self.sent_bytes = 0
        self.closed = False
        self.task = asyncio.get_running_loop().create_task(self._run())

    def put(self, data, key=None):
        if self.closed:
            return
        if key is not None and self.items:
            kept = deque(item for item in self.items if item[1] != key)
            self.dropped += len(self.items) - len(kept)
            self.items = kept
        if len(self.items) >= self.most:
            self.cut_off()
            return
        self.items.append((data, key))
        self.wake.set()

    def close(self, code=1000, reason=""):
        """Close the connection once what's already waiting has been sent (a notice before the close)."""
        if not self.closed:
            self.items.append(((code, reason), "close"))
            self.wake.set()

    def waiting(self):
        return len(self.items)

    def cut_off(self):
        self.closed = True
        self.items.clear()
        transport = getattr(self.ws, "transport", None)
        if transport is not None:
            transport.abort()

    def stop(self):
        """The connection is over: stop the task (what's waiting is dropped)."""
        self.closed = True
        self.items.clear()
        self.task.cancel()

    async def _run(self):
        try:
            while True:
                while not self.items:
                    self.wake.clear()
                    await self.wake.wait()
                data, key = self.items.popleft()
                if key == "close":
                    self.closed = True
                    await self.ws.close(*data)
                    return
                await self.ws.send(data)
                self.sent_bytes += len(data)
        except (websockets.ConnectionClosed, ConnectionError):
            self.closed = True
        except asyncio.CancelledError:
            pass


class Outboxes:
    """A server's Outboxes, one per connection. send() never waits; a connection without one (not yet logged in, or
    gone) is sent to directly."""

    def __init__(self):
        self.boxes = {}

    def open(self, ws):
        box = self.boxes.get(ws)
        if box is None:
            box = self.boxes[ws] = Outbox(ws)
        return box

    def drop(self, ws):
        box = self.boxes.pop(ws, None)
        if box is not None:
            box.stop()

    def get(self, ws):
        return self.boxes.get(ws)

    async def send(self, ws, data, key=None):
        box = self.boxes.get(ws)
        if box is not None:
            box.put(data, key)
            return
        try:
            await ws.send(data)
        except websockets.ConnectionClosed:
            pass

    async def close(self, ws, code=1000, reason=""):
        """Close after what's waiting; without an Outbox, close now (as before)."""
        box = self.boxes.get(ws)
        if box is not None:
            box.close(code, reason)
            return
        await ws.close(code, reason)
