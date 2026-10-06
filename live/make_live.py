"""Make my changes live: put a game's changed code on the class server, without a new download for learners.

    python club-coders/live/make_live.py robotlab          (or fightlab)
    python club-coders/live/make_live.py --new-key         once, before the first live update (see below)

What it does, stopping at the first problem:
  1. checks these live tools haven't been changed since they were committed (so nothing can have altered them to
     copy the key or its passphrase)
  2. copies the game from its folder on this laptop, exactly as a release would (the same files, the same checks
     for learners' data, class and teacher codes, and keys)
  3. compares it with the release installed on the class server: lists every changed file, and every new line
     that does something risky (runs programs, uses the network, writes or deletes files, runs text as code...).
     A library the app doesn't have needs a full release. You confirm you've reviewed the changes (the Changes
     tab shows them in full) before anything is signed. The list is a help, not a guarantee: only review is.
  4. signs it with the club's key (asks for the key's passphrase; the key is kept only on this laptop, locked)
  5. only then runs the game's smoke test and security test on the copy, with none of this laptop's settings
  6. sends it to the class server over SSH (ssh robotlab), which checks the signature again and gets it ready.
     Nothing changes for learners until you press Restart server in your teacher window: warn the class first.
     Their windows then reopen with the new code, and check the signature themselves before running it.

The key: --new-key makes it (asks for a passphrase of at least 12 characters, twice) and writes its public half to
live/live_key.pub. Commit that file and make a release: the app has the public half built in, and runs only code
signed with this key. Keep the key file (in %APPDATA%\\ClubCoders) and its passphrase private: never in git, email
or the cloud. If they might have leaked: make a new key (--new-key --replace-key) and a new release. The class
server only lets in the newest app, so the old key stops working for everyone.

Live code isn't in git yet: ask for the kept changes to be committed, so the next release includes them.
--test (the club's automated tests only) allows a passphrase in CLUBCODERS_KEY_PASSPHRASE and skips the questions.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CC = os.path.dirname(HERE)  # club-coders/
# (nothing in the club's folders is imported until they've been checked: see tools_unchanged)
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") not in (HERE, CC)]

import argparse  # noqa: E402
import ast  # noqa: E402
import base64  # noqa: E402
import getpass  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tarfile  # noqa: E402
import tempfile  # noqa: E402
import zipfile  # noqa: E402

CLUB = os.path.dirname(CC)
TOOLS_BRANCH = "refs/heads/club-coders"

KEY_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ClubCoders")
KEY_FILE = os.path.join(KEY_DIR, "live_signing_key.json")
PUBLIC_KEY = os.path.join(HERE, "live_key.pub")
HISTORY = os.path.join(KEY_DIR, "live_history")
SCRYPT = {"n": 2 ** 17, "r": 8, "p": 1}  # (slow to guess on purpose: about a quarter of a second per try)
RISKY_MODULES = {"subprocess", "socket", "ssl", "urllib", "http", "requests", "websockets", "ctypes", "winreg",
                 "webbrowser", "ftplib", "smtplib", "telnetlib", "multiprocessing", "shutil", "pickle", "marshal",
                 "importlib", "runpy", "zipimport", "tempfile", "glob", "pathlib"}
RISKY_CALLS = {"eval", "exec", "compile", "__import__", "getattr", "setattr", "globals", "vars", "system", "popen",
               "remove", "unlink", "rmdir", "removedirs", "rmtree", "rename", "startfile", "spawnl",
               "spawnle", "spawnv", "spawnve", "execv", "execve", "execl", "posix_spawn", "kill", "chmod",
               "create_subprocess_exec", "create_subprocess_shell", "open_connection", "start_server",
               "urlopen", "connect", "Popen", "check_output", "write_bytes", "write_text"}
OS_RISKY = {"replace", "rename", "remove", "unlink", "rmdir", "system", "popen", "startfile", "chmod", "kill",
            "execv", "execve", "spawnv", "spawnve", "posix_spawn", "putenv", "symlink", "link"}
TEST = False


def say(text):
    print(text, flush=True)


def ask(question):
    if TEST:
        return "yes"
    return input(question).strip()


def passphrase(prompt):
    if TEST and os.environ.get("CLUBCODERS_KEY_PASSPHRASE"):
        return os.environ["CLUBCODERS_KEY_PASSPHRASE"]
    return getpass.getpass(prompt)


# ---------- the key ----------
def lock(secret, phrase):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    salt, nonce = os.urandom(16), os.urandom(12)
    key = Scrypt(salt=salt, length=32, **SCRYPT).derive(phrase.encode())
    return {"kdf": "scrypt", **SCRYPT, "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
            "key": base64.b64encode(AESGCM(key).encrypt(nonce, secret, b"clubcoders-live-key")).decode()}


def unlock(locked, phrase):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    key = Scrypt(salt=base64.b64decode(locked["salt"]), length=32, n=locked["n"], r=locked["r"],
                 p=locked["p"]).derive(phrase.encode())
    try:
        return AESGCM(key).decrypt(base64.b64decode(locked["nonce"]), base64.b64decode(locked["key"]),
                                   b"clubcoders-live-key")
    except InvalidTag:
        raise SystemExit("That isn't the key's passphrase: nothing was signed or sent.") from None


def new_key(replace=False):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if os.path.exists(KEY_FILE) and not replace:
        raise SystemExit(f"There's already a key ({KEY_FILE}). Replacing it means every learner needs a new download "
                         "before live updates work again: use --new-key --replace-key if that's really what you want.")
    phrase = passphrase("Choose a passphrase for the key (at least 12 characters: three random words is good): ")
    if not TEST and getpass.getpass("Type it again: ") != phrase:
        raise SystemExit("The two passphrases were different: nothing was made.")
    if len(phrase) < 12:
        raise SystemExit("Use a passphrase of at least 12 characters (three random words is good).")
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    os.makedirs(KEY_DIR, exist_ok=True)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        json.dump(lock(raw, phrase), f)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    with open(PUBLIC_KEY, "w", encoding="utf-8", newline="\n") as f:
        f.write(base64.b64encode(public).decode() + "\n")
    say(f"Key made. Private half (locked with your passphrase; keep it private): {KEY_FILE}\n"
        f"Public half: {PUBLIC_KEY}\nNext: commit live/live_key.pub and make a release, so the app knows the key.")


def sign(data):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not os.path.exists(KEY_FILE):
        raise SystemExit("There's no key on this laptop yet: run make_live.py --new-key first.")
    with open(KEY_FILE, encoding="utf-8") as f:
        locked = json.load(f)
    key = Ed25519PrivateKey.from_private_bytes(unlock(locked, passphrase("The key's passphrase: ")))
    return key.sign(data)


# ---------- checks ----------
def tools_unchanged():
    """The club's tool files must be exactly as committed on the club-coders branch, with no extra Python files next
    to them: anything that changed them could be after the key's passphrase. (This catches changes by mistake or by
    simple tampering; code that can run as you on this laptop could still do harm, which is why every change is
    reviewed before it's kept or signed.)"""
    listed = subprocess.run(["git", "ls-tree", "-r", "--name-only", TOOLS_BRANCH, "club-coders/"], cwd=CLUB,
                            capture_output=True, text=True)
    committed = set(listed.stdout.split())
    if listed.returncode or not committed:
        raise SystemExit("STOP: can't find the club-coders branch to check the live tools against.")
    problems = []
    for folder in ("club-coders", "club-coders/live"):
        for name in os.listdir(os.path.join(CLUB, folder)):
            rel = f"{folder}/{name}"
            if name.endswith(".py") and rel not in committed:
                problems.append(f"{rel} (not part of the tools)")
    for rel in sorted(committed):
        if not (rel.endswith(".py") and rel.count("/") <= 2 and rel.startswith(("club-coders/live/", "club-coders/"))):
            continue
        if rel.count("/") == 2 and not rel.startswith("club-coders/live/"):
            continue
        blob = subprocess.run(["git", "show", f"{TOOLS_BRANCH}:{rel}"], cwd=CLUB, capture_output=True).stdout
        try:
            with open(os.path.join(CLUB, rel), "rb") as f:
                here = f.read()
        except OSError:
            problems.append(f"{rel} (missing)")
            continue
        if here.replace(b"\r\n", b"\n") != blob.replace(b"\r\n", b"\n"):
            problems.append(f"{rel} (changed)")
    if problems:
        raise SystemExit("STOP: the live tools aren't as committed, so they won't ask for the key's passphrase: " +
                         ", ".join(problems) + ". If you didn't change them, don't use them: ask for them to be checked.")


def load_tools(check=True):
    """The club's own modules, once checked."""
    global lf, export
    if check:
        tools_unchanged()
    sys.path.insert(0, HERE)
    sys.path.insert(0, CC)
    import live_format as lf
    import make_public_repo as export


def risky_lines(folder, prefix=""):
    """{(file, what it does, the line's text)} for every line in the folder's .py files that does something risky,
    and {library} for every library imported. prefix: how the files are named in the list (engine/...)."""
    found, libraries = set(), set()
    local = {f[:-3] for f in os.listdir(folder) if f.endswith(".py")} | {"engine"}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            source = f.read()
        lines = source.splitlines()
        text = lambda n: lines[n.lineno - 1].strip() if 0 < n.lineno <= len(lines) else ""  # noqa: E731
        for node in ast.walk(ast.parse(source, name)):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m not in local:
                    libraries.add(m)
                if m in RISKY_MODULES:
                    found.add((prefix + name, f"uses {m}", text(node)))
            if isinstance(node, ast.Call):
                fn = node.func
                called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
                owner = fn.value.id if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) else None
                if called in RISKY_CALLS:
                    found.add((prefix + name, f"calls {called}()", text(node)))
                elif owner in RISKY_MODULES or (owner == "os" and called in OS_RISKY):
                    found.add((prefix + name, f"calls {owner}.{called}()", text(node)))
                if called == "open" and len(node.args) > 1 and not (
                        isinstance(node.args[1], ast.Constant) and str(node.args[1].value).startswith("r")):
                    found.add((prefix + name, "writes a file", text(node)))
            if isinstance(node, ast.Attribute) and node.attr in ("modules", "__builtins__", "__dict__", "__code__"):
                found.add((prefix + name, f"reaches into .{node.attr}", text(node)))
            if isinstance(node, ast.Name) and node.id == "__builtins__":
                found.add((prefix + name, "reaches into __builtins__", text(node)))
    return found, libraries


def release_copy(game, into):
    """The game as it is in the release installed on the class server (the public repository's version tag), and
    the engine with it (releases before 1.6.0 had none). -> (the game's folder, the engine's or None)"""
    tag = "v" + export.version()
    archive = subprocess.run(["git", "archive", "--format=tar", tag, f"games/{game}"], cwd=export.DEFAULT_TARGET,
                             capture_output=True)
    if archive.returncode:
        raise SystemExit(f"STOP: can't find release {tag} in {export.DEFAULT_TARGET} to compare with: "
                         f"{archive.stderr.decode(errors='replace').strip()}")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as t:
        t.extractall(into, filter="data")
    engine = subprocess.run(["git", "archive", "--format=tar", tag, "engine"], cwd=export.DEFAULT_TARGET,
                            capture_output=True)
    if not engine.returncode:
        with tarfile.open(fileobj=io.BytesIO(engine.stdout)) as t:
            t.extractall(into, filter="data")
    return os.path.join(into, "games", game), os.path.join(into, "engine") if not engine.returncode else None


def changed_files(old_folder, new_folder, prefix=""):
    """Every .py file that differs between two folders, as 'name (new / removed / changed)'."""
    out = []
    olds = set(os.listdir(old_folder)) if old_folder and os.path.isdir(old_folder) else set()
    news = set(os.listdir(new_folder)) if new_folder and os.path.isdir(new_folder) else set()
    for name in sorted(olds | news):
        if not name.endswith(".py"):
            continue
        a, b = os.path.join(old_folder or "", name), os.path.join(new_folder or "", name)
        old = open(a, encoding="utf-8").read().replace("\r\n", "\n") if old_folder and os.path.exists(a) else None
        new = open(b, encoding="utf-8").read().replace("\r\n", "\n") if new_folder and os.path.exists(b) else None
        if old != new:
            out.append(f"{prefix}{name} ({'new' if old is None else 'removed' if new is None else 'changed'})")
    return out


def review(game, live_folder):
    """Every changed file, every new risky line, and the reviewer's yes: nothing is signed without it."""
    work = tempfile.mkdtemp(prefix="clubcoders_release_")
    live_engine = os.path.join(live_folder, "engine")
    try:
        released, released_engine = release_copy(game, work)
        before, before_libs = risky_lines(released)
        if released_engine:
            b2, l2 = risky_lines(released_engine, "engine/")
            before, before_libs = before | b2, before_libs | l2
        changed = changed_files(released, live_folder) + changed_files(released_engine, live_engine, "engine/")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    after, after_libs = risky_lines(live_folder)
    if os.path.isdir(live_engine):
        a2, l2 = risky_lines(live_engine, "engine/")
        after, after_libs = after | a2, after_libs | l2
    new_libraries = sorted(after_libs - before_libs - set(sys.stdlib_module_names))
    if new_libraries:
        raise SystemExit("STOP: this code needs " + ", ".join(new_libraries) + ", which the app doesn't have. "
                         "It needs a full release, not a live update.")
    if not changed:
        raise SystemExit(f"Nothing to send: {game}'s code is the same as the release on the class server.")
    old_lines = {(f, t) for f, _, t in before}
    new = sorted((f, what, t) for f, what, t in after if (f, t) not in old_lines)
    say(f"\nChanged since release v{export.version()}: " + ", ".join(changed))
    if new:
        say("\nNEW risky lines (this code runs on learners' computers: read each one):")
        for f, what, t in new:
            say(f"    {f}: {what}:  {t[:110]}")
    else:
        say("No new risky lines found (the list can't catch everything: your review of the changes is what counts).")
    if ask("\nHave you reviewed these changes (in the Changes tab) and are they safe to run on learners' computers? "
           "Type yes to sign them: ") != "yes":
        raise SystemExit("Stopped: nothing was signed or sent.")


# ---------- building the update ----------
def stage_game(game):
    """The game's folder on this laptop (what you tried and kept), copied as a release would copy it."""
    g = export.GAMES[game]
    g["source"] = os.path.join(export.CLUB, g["folder"])
    stage = tempfile.mkdtemp(prefix="clubcoders_live_")
    export.copy_game(game, stage)
    export.copy_engine(stage, os.path.join(export.CLUB, "engine"))  # (the engine goes inside the game's update)
    shutil.copytree(os.path.join(stage, "engine"), os.path.join(stage, "games", game, "engine"))
    problems = export.check(stage)
    if problems:
        shutil.rmtree(stage, ignore_errors=True)
        raise SystemExit("STOP: the update would include things that must never leave this laptop:\n  " +
                         "\n  ".join(problems))
    return stage, os.path.join(stage, "games", game)


def bundle(folder, stage):
    """The update: the game's folder without its big files, mods and brains, as a zip. -> (id, zip bytes)"""
    out = os.path.join(stage, "bundle")
    shutil.copytree(folder, out, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log", *lf.LINK_DIRS,
                                                               "profiles", "evidence", "ai_requests", "ai_changes"))
    update_id = lf.content_id(out)
    with open(os.path.join(out, "LIVE_ID"), "w", encoding="utf-8", newline="\n") as f:
        f.write(update_id + "\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(out):
            dirs.sort()
            for name in sorted(files):
                path = os.path.join(root, name)
                z.write(path, os.path.relpath(path, out).replace("\\", "/"))
    return update_id, buf.getvalue()


def run_tests(game, folder, stage):
    """The game's tests on the copy, with none of this laptop's settings, keys or passwords in reach."""
    home = os.path.join(stage, "test_home")
    os.makedirs(home, exist_ok=True)
    keep = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC", "OS", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(TEMP=home, TMP=home, APPDATA=home, LOCALAPPDATA=home, USERPROFILE=home, HOME=home,
               ROBOTLAB_DATA=os.path.join(stage, "test_data"), FIGHTLAB_DATA=os.path.join(stage, "test_data"))
    for test in ("smoke_test.py", "security_test.py"):
        say(f"Running {game}'s {test} (a few minutes)...")
        r = subprocess.run([sys.executable, test], cwd=folder, capture_output=True, text=True, env=env)
        fails = [line for line in r.stdout.splitlines() if line.startswith("FAIL")]
        if r.returncode or fails:
            raise SystemExit(f"STOP: {test} failed, so this won't be sent:\n" + "\n".join(
                fails or r.stdout.splitlines()[-15:] + r.stderr.splitlines()[-15:]))
        say(f"  {test}: passed")


def main():
    global TEST
    ap = argparse.ArgumentParser(description="Put a game's changed code on the class server (see the notes above).")
    ap.add_argument("game", nargs="?", choices=("robotlab", "fightlab"))
    ap.add_argument("--new-key", action="store_true", help="make the club's signing key (once)")
    ap.add_argument("--replace-key", action="store_true")
    ap.add_argument("--no-upload", action="store_true", help="make and sign it, but don't send it")
    ap.add_argument("--out", help="where to keep the signed update (default: %%APPDATA%%\\ClubCoders\\live_history)")
    ap.add_argument("--test", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    TEST = args.test
    load_tools(check=not TEST)
    if args.new_key:
        return new_key(args.replace_key)
    if not args.game:
        ap.error("which game? robotlab or fightlab")
    if not os.path.exists(PUBLIC_KEY):
        raise SystemExit("There's no key yet: run make_live.py --new-key, then make a release, first.")
    version = export.version()
    stage, folder = stage_game(args.game)
    try:
        review(args.game, folder)
        update_id, zip_bytes = bundle(folder, stage)
        signature = sign(lf.statement(args.game, update_id, version, zip_bytes))  # (before any new code runs)
        with open(PUBLIC_KEY, encoding="utf-8") as f:
            lf.check_signature(f.read(), args.game, update_id, version, zip_bytes, signature)
        run_tests(args.game, folder, stage)
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    out = args.out or os.path.join(HISTORY, args.game)
    os.makedirs(out, exist_ok=True)
    for ext, data in ((".zip", zip_bytes), (".sig", signature)):
        with open(os.path.join(out, update_id + ext), "wb") as f:
            f.write(data)
    say(f"Signed live update {update_id} of {args.game} for Club Coders {version} ({len(zip_bytes) // 1024} KB), "
        f"kept in {out}")
    if args.no_upload:
        return
    tar = io.BytesIO()
    with tarfile.open(fileobj=tar, mode="w") as t:
        for ext, data in ((".zip", zip_bytes), (".sig", signature)):
            info = tarfile.TarInfo(update_id + ext)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    say("Sending it to the class server (it asks for your SSH key's passphrase)...")
    r = subprocess.run(["ssh", "robotlab", "sudo", "robotlab-live", "install", args.game, update_id],
                       input=tar.getvalue())
    if r.returncode:
        raise SystemExit("The class server didn't take it: see its message above. Nothing changed for learners.")


if __name__ == "__main__":
    main()
