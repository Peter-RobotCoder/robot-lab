"""The games' letters: four SIL Open Font License fonts in engine/fonts, for every Club Coders window.

Panda3D's built-in font (Perspective Sans, freeware with no licence text) is no longer used: every window writes in
Inter unless told otherwise, and Space Grotesk (titles), JetBrains Mono (code) and Press Start 2P (pixel art
numbers) are there to ask for. They are the Club Coders website's own fonts (its Latin subsets, as .ttf: Panda's
FreeType can't read woff2); each font's copyright line and the licence are in engine/fonts/OFL.txt.

    which      file (engine/fonts/)          made from
    "body"     Inter-Regular.ttf             the website's inter-latin.woff2 at weight 400 (static)
    "bold"     Inter-SemiBold.ttf            the same at weight 600
    "title"    SpaceGrotesk-Bold.ttf         the website's spacegrotesk-latin.woff2 at weight 700 (static)
    "mono"     JetBrainsMono.ttf             the website's jetbrainsmono-latin.woff2 (Regular; editor.py's code font)
    "pixel"    PressStart2P-Regular.ttf      the upstream file unchanged (google/fonts: it has a Reserved Font Name)

The API:

    use_default()        Before the window opens (ShowBase), once: makes Inter the default font of every TextNode,
                         OnscreenText and DirectGui item (the prc variable text-default-font) and gives it the line
                         spacing the windows were laid out for. hud.window_arg calls it, so the game clients
                         (Robot, Fight, Kart, City and Craft Lab, the missions) need do nothing; the windows that
                         don't use window_arg call it themselves. Returns the default TextFont (None if Panda3D or the
                         font is missing: the windows then write in Panda's own font, as before). Safe to call again.
    prc()                The prc line on its own ("text-default-font <path>\\n"), for a window that builds its prc
                         text in one string. Without use_default() the line spacing is Inter's own (1.21 lines).
    font(app_or_loader, which="body")
                         The TextFont for which ("body", "bold", "title", "mono" or "pixel"), loaded once and kept.
                         app_or_loader: the ShowBase (its .loader is used), a Loader, or None (Panda's FontPool).
                         "body" is the very font every TextNode already uses (the same object), so leave its settings
                         alone; call .makeCopy() first to change one (pixels per unit, filters, line height) for your
                         own text. Returns None if the file is missing or can't be read (Panda's own font is then
                         used where it is given: TextNode.setFont(None) is not allowed, so check).
                         e.g. OnscreenText("CRAFT LAB", font=club_fonts.font(base, "title"), scale=0.09)
    path(which)          The font file's own path (an OS path), e.g. for the page's make_font.py.
    panda_path(which)    The same as Panda wants it ("/c/Users/..."), with the file's true capitals.
    LINE_HEIGHT          The line spacing given to Inter ("body" and "bold"): 1.0 units a line. Panda's old font had
                         0.99, Inter has 1.21 of its own, which made every wrapped panel a fifth taller.

Only os and Panda3D are imported (and Panda3D only when asked), so the launcher can load this file on its own.
"""
import os

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
FILES = {"body": "Inter-Regular.ttf", "bold": "Inter-SemiBold.ttf", "title": "SpaceGrotesk-Bold.ttf",
         "mono": "JetBrainsMono.ttf", "pixel": "PressStart2P-Regular.ttf"}
DEFAULT = "body"
LINE_HEIGHT = 1.0
_TUNED_LINES = {"body": LINE_HEIGHT, "bold": LINE_HEIGHT}  # (the others keep their own: titles are one line)
_PIXELS_PER_UNIT = {"mono": 64, "pixel": 64}  # (sharp at the small sizes code and pixel numbers are drawn)
_cache = {}


def path(which=DEFAULT):
    """The font file for which ("body", "bold", "title", "mono", "pixel"), as an OS path (it may not exist)."""
    if which not in FILES:
        raise ValueError(f"no font {which!r}: one of {', '.join(FILES)}")
    return os.path.realpath(os.path.join(FONT_DIR, FILES[which]))  # (its true capitals: Panda3D is fussy about them)


def panda_path(which=DEFAULT):
    """The font file as Panda3D names files ("/c/Users/.../Inter-Regular.ttf")."""
    from panda3d.core import Filename
    return Filename.fromOsSpecific(path(which)).getFullpath()


def prc():
    """The prc line that makes Inter every TextNode's font (empty if the file is missing)."""
    if not os.path.exists(path(DEFAULT)):
        return ""
    return f"text-default-font {panda_path(DEFAULT)}\n"


def _tune(which, f):
    if which in _TUNED_LINES:
        f.setLineHeight(_TUNED_LINES[which])
    if which in _PIXELS_PER_UNIT and hasattr(f, "setPixelsPerUnit"):
        f.setPixelsPerUnit(_PIXELS_PER_UNIT[which])
    return f


def use_default():
    """Inter for every TextNode in this window (call before the window opens). The default TextFont, or None."""
    if "default" in _cache:
        return _cache["default"]
    try:
        from panda3d.core import TextProperties, loadPrcFileData
        line = prc()
        if not line:
            return None
        loadPrcFileData("club fonts", line)
        f = TextProperties.getDefaultFont()  # (loaded now, from text-default-font, through Panda's FontPool)
        if f is None or not f.isValid():
            return None
    except Exception:  # (no Panda3D here, or a font it couldn't read: Panda's own font, as before)
        return None
    _cache["default"] = _cache["body"] = _tune(DEFAULT, f)
    return f


def font(app_or_loader=None, which=DEFAULT):
    """The TextFont for which, loaded once (see the module's notes); None if it can't be had."""
    if which in _cache:
        return _cache[which]
    try:
        loader = getattr(app_or_loader, "loader", app_or_loader)
        if loader is not None and hasattr(loader, "loadFont"):
            f = loader.loadFont(panda_path(which))
        else:
            from panda3d.core import FontPool
            f = FontPool.loadFont(panda_path(which))
        if f is None or not f.isValid():
            return None
    except Exception:
        return None
    _cache[which] = _tune(which, f)
    return f
