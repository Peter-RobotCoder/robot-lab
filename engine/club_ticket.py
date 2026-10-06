"""Tickets: how the club desk tells a game server that someone has logged in.

The desk checks a username and password once. It then gives the app a ticket: a small signed note saying who this
is (username and role), which game it is for, and when it runs out. The game server checks the signature with the
same key (a secret file the desk and the game servers share on the class server) and lets the person in without
asking for a password again. A ticket can't be made up or changed: any change breaks the signature.

This file is the same in club-coders/desk and in each game's folder (the tests check the copies agree).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time

TICKET_HOURS = 8  # a club session, with room for reconnecting


def load_key(path):
    """The shared secret (32 random bytes, hex), made the first time the desk starts."""
    try:
        with open(path, encoding="utf-8") as f:
            key = f.read().strip()
        if len(key) >= 64:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key + "\n")
    return key


def make(key, name, role, game, hours=TICKET_HOURS):
    body = json.dumps({"name": name, "role": role, "game": game, "exp": int(time.time() + hours * 3600),
                       "id": secrets.token_hex(4)}, separators=(",", ":")).encode()
    head = base64.urlsafe_b64encode(body).decode().rstrip("=")
    return head + "." + hmac.new(key.encode(), head.encode(), hashlib.sha256).hexdigest()


def peek(ticket):
    """What a ticket says, WITHOUT checking it (the app uses this for the name to show; a server never trusts it)."""
    try:
        head = str(ticket).split(".")[0]
        return json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
    except Exception:
        return None


def verify(key, ticket, game):
    """The ticket's contents if it is genuine, unexpired and for this game; otherwise None."""
    try:
        head, sig = str(ticket).split(".")
    except ValueError:
        return None
    if not hmac.compare_digest(hmac.new(key.encode(), head.encode(), hashlib.sha256).hexdigest(), sig):
        return None
    body = peek(ticket)
    if not body or body.get("game") != game or body.get("role") not in ("learner", "teacher"):
        return None
    if not isinstance(body.get("exp"), int) or body["exp"] < time.time():
        return None
    return body
