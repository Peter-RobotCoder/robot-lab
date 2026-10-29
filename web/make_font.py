"""fonts/cc_sans.png and .json for Club Coders Live: the letters the games' windows write in the world (Inter, the
windows' default font since Panda3D's own unlicensed one was dropped: engine/club_fonts.py), so the page's Fight Lab
and Robot Lab write the rings' names, the hall's screens and the fighters' numbers in the same letters as their windows
(CHANGE 150; the page drew them in the browser's bold sans before, and in Panda's Perspective Sans till Inter).

- cc_sans.png: printable ASCII (32 to 126) drawn by Panda3D from engine/fonts/Inter-Regular.ttf at PPU pixels a unit,
  white with the letters in the alpha, packed as Panda packs them (its own glyph pages);
- cc_sans.json: {"version", "ppu", "size": [w, h], "line", "space", "glyphs": {char: [left, bottom, right, top, u0,
  v0, u1, v1, advance]}}: each glyph's quad in units (a TextNode's scale is the size of a unit: about the height of a
  line) about the pen on the baseline, its corners in the picture (0 to 1, v from the bottom, as Panda's), and how far
  the pen moves on. The page lays the quads out as a TextNode does (fightfx.js's drawWords: no kerning, as Panda's
  TextNodes don't kern either).

Inter is under the SIL Open Font License: fonts/OFL.txt beside the files.

    python make_font.py           write fonts/cc_sans.* beside this file
    python make_font.py --check   exit 1 if they differ from what Panda draws today

It needs Panda3D (shared-world-demo/.venv) and the engine folder (engine/fonts) beside or above this one.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fonts")
NAME = "cc_sans"
VERSION = 1       # (the file's layout, which fightfx.js checks: unchanged since panda_sans)
PPU = 96          # pixels a unit (a letter about 70 pixels tall: sharp at the size the page draws a ring's name)
PAGE = 1024


def engine_fonts():
    """engine/club_fonts.py: beside web/ in the public repository, two levels up in the working folder."""
    for up in (1, 2, 3):
        home = os.path.abspath(os.path.join(HERE, *([".."] * up)))
        if os.path.exists(os.path.join(home, "engine", "club_fonts.py")):
            if home not in sys.path:
                sys.path.insert(0, home)
            from engine import club_fonts
            return club_fonts
    raise SystemExit("can't find engine/club_fonts.py (the windows' fonts) above this folder")


def make():
    """(the PNG's bytes, the JSON's text) as Panda draws them now."""
    from panda3d.core import LVecBase4, PNMImage, StringStream, Texture, loadPrcFileData
    loadPrcFileData("", "window-type none\naudio-library-name null")
    default = engine_fonts().use_default()  # (the windows' default font, with the windows' line spacing)
    if default is None:
        raise SystemExit("Panda3D couldn't load engine/fonts/Inter-Regular.ttf")
    font = default.makeCopy()
    font.setPixelsPerUnit(PPU)
    font.setPageSize(PAGE, PAGE)
    font.setMinfilter(Texture.FT_linear)
    glyphs = {}
    for code in range(32, 127):
        g = font.getGlyph(code)
        if g is None:
            continue
        d, t = LVecBase4(), LVecBase4()
        quad = g.getQuad(d, t) if g.hasQuad() else False
        q = [round(v, 5) for v in (*d, *t)] if quad else [0, 0, 0, 0, 0, 0, 0, 0]
        glyphs[chr(code)] = q + [round(g.getAdvance(), 5)]
    if font.getNumPages() != 1:
        raise SystemExit("the letters need a second page: make PAGE bigger")
    page = font.getPage(0)
    img = PNMImage()
    page.store(img)
    out = PNMImage(img.getXSize(), img.getYSize(), 4)
    out.fill(1, 1, 1)
    for y in range(img.getYSize()):
        for x in range(img.getXSize()):
            out.setAlpha(x, y, img.getAlpha(x, y) if img.hasAlpha() else img.getGray(x, y))
    stream = StringStream()
    out.write(stream, NAME + ".png")
    data = {"version": VERSION, "ppu": PPU, "size": [img.getXSize(), img.getYSize()],
            "line": round(font.getLineHeight(), 5), "space": round(font.getSpaceAdvance(), 5), "glyphs": glyphs}
    return bytes(stream.getData()), json.dumps(data, separators=(",", ":")) + "\n"


def check():
    png, text = make()
    try:
        with open(os.path.join(OUT, NAME + ".json"), encoding="utf-8") as f:
            have = f.read()
        with open(os.path.join(OUT, NAME + ".png"), "rb") as f:
            have_png = f.read()
    except OSError:
        print(f"fonts/{NAME}.* are missing: run make_font.py")
        return False
    if have != text or have_png != png:
        print(f"fonts/{NAME}.* are out of date: run make_font.py")
        return False
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    png, text = make()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, NAME + ".png"), "wb") as f:
        f.write(png)
    with open(os.path.join(OUT, NAME + ".json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote fonts/{NAME}.png ({len(png) / 1e3:.0f} kB) and {NAME}.json ({len(json.loads(text)['glyphs'])} letters)")
