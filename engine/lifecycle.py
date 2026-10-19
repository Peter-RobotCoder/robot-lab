"""A game server's start and stop (CHANGE 160).

- Stopping (systemd's SIGTERM when the VPS updates, Ctrl+C, the teacher's Restart server): every window is told
  1012 ("service restart") after what was already waiting for it, so the page and the windows say "the class server
  is restarting" and reconnect (each after its own random wait, so the class doesn't all knock at once). Before,
  the process just ended and every window saw a dropped connection.
- systemd's watchdog: when the unit sets WatchdogSec=, the physics loop pings it (Watchdog.ping, at most once a
  second); a loop that stops for longer is restarted by systemd. Off the VPS nothing is sent.
"""
import asyncio
import os
import signal
import socket
import time
import traceback

import websockets

RESTART_REASON = "The class server is restarting: back in a moment."


async def close_all(outboxes, players, seconds=2.0):
    """1012 to every window (after what's waiting for it), then wait up to `seconds` for them to close."""
    for ws in list(players):
        await outboxes.close(ws, 1012, RESTART_REASON)
    end = time.perf_counter() + seconds
    while time.perf_counter() < end and any(not getattr(box, "closed", True) for box in outboxes.boxes.values()):
        await asyncio.sleep(0.05)


async def exit_after_closing(outboxes, players, code, before=None):
    """Close every window, then end the process with `code` (3: the teacher's restart; systemd starts it again)."""
    if before is not None:
        before()
    await close_all(outboxes, players)
    os._exit(code)


async def run(tasks, outboxes, players, before_exit=None):
    """Run the server's loops until they end or the process is told to stop (SIGTERM, SIGINT where the system
    lets asyncio catch them: Linux; on Windows Ctrl+C ends it as before)."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, AttributeError, ValueError, RuntimeError):
            pass
    running = asyncio.gather(*tasks)
    waiter = asyncio.ensure_future(stop.wait())
    done, _ = await asyncio.wait({running, waiter}, return_when=asyncio.FIRST_COMPLETED)
    if running in done:
        waiter.cancel()
        running.result()
        return
    print("Stopping: telling every window the server is restarting", flush=True)
    if before_exit is not None:
        before_exit()
    await close_all(outboxes, players)
    running.cancel()
    try:
        await running
    except (asyncio.CancelledError, Exception):
        pass


class Watchdog:
    def __init__(self):
        self.address = os.environ.get("NOTIFY_SOCKET") if os.environ.get("WATCHDOG_USEC") else None
        if self.address and self.address.startswith("@"):  # (an abstract socket)
            self.address = "\0" + self.address[1:]
        self.last = 0.0
        self.sock = None

    def notify(self, text):
        if not self.address or not hasattr(socket, "AF_UNIX"):
            return
        try:
            if self.sock is None:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self.sock.sendto(text.encode(), self.address)
        except OSError:
            pass

    def ping(self):
        now = time.monotonic()
        if self.address and now - self.last >= 1.0:
            self.last = now
            self.notify("WATCHDOG=1")


_reported = {}


async def handle(on_message, p, m):
    """(CHANGE 165) One message from a window, handled: an error in the server's code over it is written to the log
    (with its traceback, once a minute for the same error) and the message dropped, not the window's connection (an
    error used to end it: a learner's page sent one odd control and was thrown out of the class)."""
    try:
        await on_message(p, m)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001  (the server carries on whatever went wrong)
        if isinstance(e, websockets.ConnectionClosed):
            raise
        key = (type(e).__name__, str(e)[:80], str(m.get("type"))[:40])
        now = time.monotonic()
        if now - _reported.get(key, -1e9) > 60:
            _reported[key] = now
            print(f"Error over a {key[2]!r} message from {getattr(p, 'name', '?')} (the message was dropped):",
                  flush=True)
            traceback.print_exc()
