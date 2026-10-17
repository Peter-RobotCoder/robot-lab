"""fonts/panda_sans.png and .json for Club Coders Live: the letters the games' windows write in the world (Panda3D's own
built-in font, which every TextNode uses unless told otherwise), so the page's Fight Lab writes its rings' names, the
hall's screens and the fighters' numbers in the same letters as its window (CHANGE 150; the page drew them in the
browser's bold sans before).

- panda_sans.png: printable ASCII (32 to 126) drawn by Panda's font at PPU pixels a unit, white with the letters in the
  alpha, packed as Panda packs them (its own glyph pages);
- panda_sans.json: {"version", "ppu", "size": [w, h], "line", "space", "glyphs": {char: [left, bottom, right, top, u0,
  v0, u1, v1, advance]}}: each glyph's quad in units (a TextNode's scale is the size of a unit: about the height of a
  line) about the pen on the baseline, its corners in the picture (0 to 1, v from the bottom, as Panda's), and how far
  the pen moves on. The page lays the quads out as a TextNode does (fightfx.js's drawWords: no kerning, as Panda's
  default font has none).

    python make_font.py           write fonts/panda_sans.* beside this file
    python make_font.py --check   exit 1 if they differ from what Panda draws today

It needs Panda3D (shared-world-demo/.venv).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "fonts")
VERSION = 1
PPU = 96          # pixels a unit (a letter about 70 pixels tall: sharp at the size the page draws a ring's name)
PAGE = 1024


def make():
    """(the PNG's bytes, the JSON's text) as Panda draws them now."""
    from panda3d.core import LVecBase4, PNMImage, StringStream, TextProperties, Texture, loadPrcFileData
    loadPrcFileData("", "window-type none\naudio-library-name null")
    font = TextProperties.getDefaultFont().makeCopy()
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
    out.write(stream, "panda_sans.png")
    data = {"version": VERSION, "ppu": PPU, "size": [img.getXSize(), img.getYSize()],
            "line": round(font.getLineHeight(), 5), "space": round(font.getSpaceAdvance(), 5), "glyphs": glyphs}
    return bytes(stream.getData()), json.dumps(data, separators=(",", ":")) + "\n"


def check():
    png, text = make()
    try:
        with open(os.path.join(OUT, "panda_sans.json"), encoding="utf-8") as f:
            have = f.read()
        with open(os.path.join(OUT, "panda_sans.png"), "rb") as f:
            have_png = f.read()
    except OSError:
        print("fonts/panda_sans.* are missing: run make_font.py")
        return False
    if have != text or have_png != png:
        print("fonts/panda_sans.* are out of date: run make_font.py")
        return False
    return True


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    png, text = make()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "panda_sans.png"), "wb") as f:
        f.write(png)
    with open(os.path.join(OUT, "panda_sans.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote fonts/panda_sans.png ({len(png) / 1e3:.0f} kB) and panda_sans.json ({len(json.loads(text)['glyphs'])} letters)")
