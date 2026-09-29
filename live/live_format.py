"""The format of a live code update, shared by the teacher's tool (make_live.py), the class server's tool
(deploy/robotlab-live) and the Club Coders app (launcher/club_coders.py, which has this file built in).

A live update is one game's code: a zip of the game's folder without its big files (textures, sounds, models,
music) and without its mods and brains (which stay where they are). Its id is a fingerprint of every file in it,
so anyone can check a folder really is that update, with nothing added. The teacher signs a short statement:

    clubcoders-live-2
    <game>
    <id>
    <the Club Coders version it is for>
    <sha256 of the zip>

with their Ed25519 key. The public half of the key is in live/live_key.pub (in the public repository, and built
into the app), so the app and the server can check an update came from the teacher's laptop, is for that game and
that version of the app, is that exact update, and wasn't changed on the way. Anything that fails a check is not
used. (Naming the version means an update made for an older release can't be sent to a newer one.)
"""
import hashlib
import io
import os
import zipfile

GAMES = ("robotlab", "fightlab")
LINK_DIRS = ("assets", "models", "music", "mods", "brains")  # not in an update: it links to the installed ones
ID_PATTERN = r"[0-9a-f]{24}"
MAX_ZIP = 20 * 1024 * 1024        # a live update is code: a few hundred KB
MAX_UNPACKED = 60 * 1024 * 1024
MAX_FILES = 2000
HEADER = b"clubcoders-live-2"


class LiveError(Exception):
    pass


def content_id(folder):
    """The update's id: a fingerprint of every file in the folder (all of them, compiled Python too, so nothing can
    be added unnoticed), except the links to the installed game's folders and the LIVE_ID file. The same on
    Windows and Linux."""
    h = hashlib.sha256()
    for root, dirs, files in os.walk(folder):
        rel_root = os.path.relpath(root, folder).replace("\\", "/")
        dirs[:] = sorted(d for d in dirs if not (rel_root == "." and d in LINK_DIRS))
        for name in sorted(files):
            rel = name if rel_root == "." else f"{rel_root}/{name}"
            if rel == "LIVE_ID":
                continue
            with open(os.path.join(root, name), "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")
            h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(data).digest())
    return h.hexdigest()[:24]


def statement(game, update_id, version, zip_bytes):
    """What the teacher signs: which game, which update, for which version of the app, and exactly which zip."""
    if game not in GAMES:
        raise LiveError(f"'{game}' isn't one of the club's games")
    return b"\n".join([HEADER, game.encode(), update_id.encode(), str(version).encode(),
                       hashlib.sha256(zip_bytes).hexdigest().encode()])


def check_signature(public_key_b64, game, update_id, version, zip_bytes, signature):
    """Raises LiveError unless the teacher's key signed exactly this update of this game, for this version."""
    import base64
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64.strip()))
        key.verify(signature, statement(game, update_id, version, zip_bytes))
    except (InvalidSignature, ValueError, TypeError):
        raise LiveError("the update isn't signed with the club's key for this version, so it wasn't used") from None


def safe_unpack(zip_bytes, dest):
    """Unpack an update, refusing anything odd: files outside its folder, links, too many or too big files."""
    if len(zip_bytes) > MAX_ZIP:
        raise LiveError("the update is too big to be a code update")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_UNPACKED:
            raise LiveError("the update unpacks to too many or too big files")
        for i in infos:
            parts = i.filename.replace("\\", "/").split("/")
            if (i.filename.startswith(("/", "\\")) or ".." in parts or ":" in i.filename
                    or (i.external_attr >> 16) & 0o170000 == 0o120000):  # (a link)
                raise LiveError(f"the update has a file in the wrong place: {i.filename}")
            if parts[0].lower() in LINK_DIRS:
                raise LiveError(f"the update tries to replace {parts[0]}/, which it may not")
        z.extractall(dest)
