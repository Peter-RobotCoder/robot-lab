"""Connection to the class server, shared by the 2D and 3D clients."""
import json
import queue
import threading

from websockets.sync.client import connect


class Net:
    """Background thread that receives server messages into a queue."""

    def __init__(self, url, name, code, **hello_extra):
        self.url, self.hello = url, {"type": "hello", "name": name, "code": code, **hello_extra}
        self.inbox = queue.Queue()
        self.bytes_in = 0
        self._connect()

    def _connect(self):
        # entered by hand: the connection lives as long as the game
        self.ws = connect(self.url, open_timeout=5).__enter__()
        self.ws.send(json.dumps(self.hello))
        threading.Thread(target=self._recv, args=(self.ws,), daemon=True).start()

    def reconnect(self):
        """Try to connect again with the same details (after a dropped connection). True if it worked."""
        try:
            self._connect()
            return True
        except Exception:
            return False

    def _recv(self, ws):
        try:
            for raw in ws:
                self.bytes_in += len(raw)
                self.inbox.put(json.loads(raw))
            reason, code = "", None
        except Exception as e:
            rcvd = getattr(e, "rcvd", None)
            reason, code = (rcvd.reason, rcvd.code) if rcvd else ("", None)
        if ws is self.ws:  # (an old connection closing after a reconnect doesn't count)
            rcvd = getattr(getattr(ws, "protocol", None), "close_rcvd", None)
            if rcvd and not reason:
                reason, code = rcvd.reason, rcvd.code
            self.inbox.put({"type": "closed", "reason": reason, "code": code})

    def send(self, msg):
        try:
            self.ws.send(json.dumps(msg, separators=(",", ":")))
        except Exception:
            pass
