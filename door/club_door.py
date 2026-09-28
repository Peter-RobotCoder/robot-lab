"""The club's front door: which class (and which game) is this class code for?

The Club Coders app sends the class code a learner typed; the door answers with that class's game and address,
and the app opens the right game there. So learners have one app and one code, and when the teacher moves a
class to a different game, learners keep the same code and simply land in the new game.

    python club_door.py                          on the class server (behind Caddy at wss://<domain>/door):
                                                 reads the classes from /etc/robotlab (the files setup.sh and
                                                 robotlab-add-class make), again for every question, so a new
                                                 class or a change of game works straight away
    python club_door.py --classes test.json      a laptop test: [{"name", "game", "address", "code"}, ...]

It only answers "which class?": the game server itself still checks the code, the username and the password.
Wrong codes are limited to 10 a minute per computer, so codes can't be guessed.
"""
import argparse
import asyncio
import hmac
import ipaddress
import json
import os
import time

import websockets

GAMES = ("robotlab", "fightlab")
ETC = "/etc/robotlab"          # the domain, and one <class>.env per class (PORT, GAME, its own JOIN_CODE)
SHARED_ENV = "/etc/robotlab.env"  # the first class's JOIN_CODE (and the teacher code, which the door never uses)
PORT = 8779


class RateLimit:
    """At most `limit` wrong codes per `window` seconds for each computer."""

    def __init__(self, limit, window=60.0):
        self.limit, self.window, self.fails = limit, window, {}

    def blocked(self, key):
        now = time.monotonic()
        recent = [t for t in self.fails.get(key, []) if now - t < self.window]
        if recent:
            self.fails[key] = recent
        else:
            self.fails.pop(key, None)
        return len(recent) >= self.limit

    def failed(self, key):
        self.fails.setdefault(key, []).append(time.monotonic())


WRONG_CODES = RateLimit(10)


def read_env(path):
    """KEY=value lines (the files setup.sh writes); {} if the file can't be read."""
    values = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    values[k.strip()] = v.strip()
    except OSError:
        pass
    return values


def server_classes(etc=ETC, shared_env=SHARED_ENV):
    """The classes on this server: class1 at wss://<domain>, the others at wss://<domain>/<class>."""
    try:
        with open(os.path.join(etc, "domain"), encoding="utf-8") as f:
            domain = f.read().strip()
    except OSError:
        return []
    shared = read_env(shared_env)
    classes = []
    for name in sorted(os.listdir(etc)) if os.path.isdir(etc) else []:
        if not (name.startswith("class") and name.endswith(".env")):
            continue
        cls = name[:-4]
        env = read_env(os.path.join(etc, name))
        code = env.get("JOIN_CODE") or (shared.get("JOIN_CODE") if cls == "class1" else None)
        game = env.get("GAME", "robotlab")
        if code and game in GAMES:
            classes.append({"name": cls, "game": game, "code": code,
                            "address": f"wss://{domain}" + ("" if cls == "class1" else f"/{cls}")})
    return classes


def find(code, classes):
    """The class whose code this is (compared in constant time, so codes can't be guessed by timing), or None."""
    found = None
    for c in classes:
        if hmac.compare_digest(code.encode("utf-8"), c["code"].encode("utf-8")):
            found = c
    return found


def client_address(ws):
    """The computer asking. Behind Caddy (on this same machine) that is in X-Forwarded-For."""
    host = (ws.remote_address or ("?",))[0]
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = False
    forwarded = ws.request.headers.get("X-Forwarded-For") if local and ws.request is not None else None
    return forwarded.split(",")[-1].strip() if forwarded else host


def make_handler(load_classes):
    async def handler(ws):
        where = client_address(ws)
        try:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        except (asyncio.TimeoutError, ValueError, websockets.ConnectionClosed):
            return
        if not isinstance(msg, dict) or msg.get("type") != "find":
            await ws.send(json.dumps({"ok": False, "error": "The app asked something the door doesn't understand."}))
            return
        if WRONG_CODES.blocked(where):
            await ws.send(json.dumps({"ok": False, "error": "Too many wrong class codes from this computer. "
                                                            "Wait a minute, then try again."}))
            return
        code = str(msg.get("code", "")).strip()[:64]
        cls = find(code, load_classes()) if code else None
        if cls is None:
            WRONG_CODES.failed(where)
            await ws.send(json.dumps({"ok": False, "error": "That class code isn't right. Check your welcome "
                                                            "letter (it looks like abcd-efgh)."}))
            return
        await ws.send(json.dumps({"ok": True, "game": cls["game"], "address": cls["address"]}))
    return handler


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--bind", default="127.0.0.1", help="127.0.0.1: only Caddy (on this server) can reach it")
    ap.add_argument("--classes", help="laptop test: a JSON list of classes instead of /etc/robotlab")
    args = ap.parse_args()
    if args.classes:
        def load_classes():
            with open(args.classes, encoding="utf-8") as f:
                return json.load(f)
    else:
        load_classes = server_classes
    async with websockets.serve(make_handler(load_classes), args.bind, args.port, max_size=1024):
        print(f"Club Coders front door on {args.bind}:{args.port} "
              f"({len(load_classes())} classes)", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
