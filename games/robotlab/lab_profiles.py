"""Learner profiles: a username and password, and everything the learner has done, saved between lessons.

A profile is one JSON file in profiles/ (the robot itself is saved in mods/robots/<name>.py).
On the class server the teacher makes each learner's account (username and first password); learners can't
make their own. On a laptop-only test server (ws://127.0.0.1) a new username still makes a new profile.

Passwords are stored with scrypt (slow on purpose, so a copied profile can't be cracked quickly) and never
as text. Profiles made before scrypt (salted SHA-256) are upgraded the next time that learner logs in.
"""
import datetime
import hashlib
import hmac
import json
import os
import re
import secrets
import time

from ai_pipeline import slug

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(os.environ.get("ROBOTLAB_DATA", HERE), "profiles")
MIN_PASSWORD = 6          # for new passwords (older, shorter ones still work until the teacher changes them)
MAX_PROFILES = 200        # a class never needs more; stops a flood of made-up usernames filling the disk
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}  # about 16 MB and a few hundredths of a second per check


class LoginError(Exception):
    pass


class RateLimit:
    """At most `limit` failures per `window` seconds for each key (a username, or a computer's address)."""

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


WRONG_PASSWORDS = RateLimit(5)  # 5 wrong passwords a minute per username


def clean_name(text):
    return re.sub(r"[^A-Za-z0-9 ]", "", str(text)).strip()[:12]


def path_for(username):
    return os.path.join(PROFILES, f"{slug(username)}.json")


def _hash(salt, password):
    return "scrypt$" + hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"), **SCRYPT).hex()


def _old_hash(salt, password):  # profiles made before 28 September 2026
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _password_ok(profile, password):
    stored = profile.get("hash", "")
    made = _hash(profile["salt"], password) if stored.startswith("scrypt$") else _old_hash(profile["salt"], password)
    return hmac.compare_digest(made, stored)


def _set_hash(profile, password):
    profile["salt"] = secrets.token_hex(16)
    profile["hash"] = _hash(profile["salt"], password)


def check_new_password(password):
    if len(password) < MIN_PASSWORD:
        raise LoginError(f"Passwords need at least {MIN_PASSWORD} characters.")


def load(username):
    path = path_for(username)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(profile):
    os.makedirs(PROFILES, exist_ok=True)
    path = path_for(profile["name"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    os.replace(tmp, path)


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def _new_profile(name, password):
    if len(all_names()) >= MAX_PROFILES:
        raise LoginError(f"This server already has {MAX_PROFILES} profiles. The teacher needs to delete some.")
    now = _now()
    profile = {"name": name, "created": now, "last_login": None,
               "record": {"done": {}, "text": {}, "prediction": None}, "brain": None, "autopilot": False, "prefs": {}}
    _set_hash(profile, password)
    return profile


def login(username, password, allow_new=False):
    """Check a learner's username and password. Returns (profile, is_new).
    allow_new: a new username makes a new profile (laptop-only test servers); otherwise the teacher makes accounts."""
    name = clean_name(username)
    password = str(password or "")
    if not name:
        raise LoginError("Type a username (letters and numbers).")
    if not password:
        raise LoginError("Type your password.")
    key = slug(name)
    if WRONG_PASSWORDS.blocked(key):
        raise LoginError("Too many wrong passwords for that username. Wait a minute, then try again.")
    profile = load(name)
    if profile is None:
        if not allow_new:
            WRONG_PASSWORDS.failed(key)
            raise LoginError("Username or password not recognised. Your teacher makes your account: check the "
                             "username they gave you.")
        check_new_password(password)
        profile = _new_profile(name, password)
        profile["last_login"] = _now()
        save(profile)
        return profile, True
    if not _password_ok(profile, password):
        WRONG_PASSWORDS.failed(key)
        raise LoginError("Username or password not recognised. Ask your teacher if you've forgotten your password.")
    if not profile["hash"].startswith("scrypt$"):  # an older profile: store the password the stronger way now
        _set_hash(profile, password)
    profile["last_login"] = _now()
    save(profile)
    return profile, False


def ticket_profile(username):
    """The profile of a learner the club desk has already checked (a ticket): made on their first visit, with no
    password of its own (the desk holds the password, so the game never asks for one)."""
    name = clean_name(username)
    if not name:
        raise LoginError("That ticket has no username.")
    profile = load(name)
    if profile is None:
        profile = _new_profile(name, secrets.token_hex(16))
        profile["hash"] = "desk$"  # (no password login: the desk is the only way in)
    profile["last_login"] = _now()
    save(profile)
    return profile


def create(username, password):
    """For the teacher: make a learner's account. Returns the profile."""
    name = clean_name(username)
    if not name:
        raise LoginError("Usernames need letters or numbers (up to 12).")
    if load(name) is not None:
        raise LoginError(f"There is already an account called {name}.")
    password = str(password or "")
    check_new_password(password)
    profile = _new_profile(name, password)
    save(profile)
    return profile


def set_password(username, password):
    """For the teacher: give a learner a new password."""
    profile = load(username)
    if profile is None:
        raise LoginError("No profile with that username.")
    password = str(password or "")
    check_new_password(password)
    _set_hash(profile, password)
    save(profile)
    WRONG_PASSWORDS.fails.pop(slug(profile["name"]), None)


def delete(username):
    """For the teacher: delete a learner's profile file. Returns True if there was one."""
    path = path_for(username)
    if not os.path.exists(path):
        return False
    os.remove(path)
    return True


def all_names():
    if not os.path.isdir(PROFILES):
        return []
    names = []
    for f in sorted(os.listdir(PROFILES)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(PROFILES, f), encoding="utf-8") as fh:
                    names.append(json.load(fh)["name"])
            except (OSError, ValueError, KeyError):
                pass
    return names
