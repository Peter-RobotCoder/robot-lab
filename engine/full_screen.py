"""Full screen for a window without the HUD (the previews): a button in the top right corner, and Esc to come back
out of it; Esc never closes the window (CHANGE 146). The games' windows have the same in engine/hud.py."""
from direct.gui.DirectGui import DGG, DirectButton
from panda3d.core import TextNode, WindowProperties

ENTER = "Full screen"                 # the button's words in a window...
LEAVE = "Exit full screen (Esc)"      # ...and in full screen
COLOUR = (0.15, 0.42, 0.62, 0.95)  # (blue: easy to find)


def corner_button(base, command, scale=0.03):
    """The full screen button, held to the window's top right corner whatever its shape (its top 0.01 below the
    edge). Drawn after the window's own drawing, side panels made later included (setting sortOrder after a widget
    is made does nothing)."""
    b = DirectButton(parent=base.a2dTopRight, text=ENTER, scale=scale, pos=(-0.02, 0, -0.01 - scale * 0.85),
                     command=command, frameColor=COLOUR, text_fg=(1, 1, 1, 1), text_align=TextNode.ARight,
                     relief=DGG.FLAT, pad=(0.3, 0.15))
    b.setBin("gui-popup", 0)
    return b


class FullScreen:
    """A borderless window the size of the screen, or back to the window it was (as the HUD's toggle_fullscreen)."""
    def __init__(self, base):
        self.base, self.on, self.windowed = base, False, None
        self.button = corner_button(base, self.toggle)
        base.accept("escape", self.leave)

    def toggle(self):
        win = self.base.win
        wp = WindowProperties()
        if not self.on:
            cur = win.getProperties()
            self.windowed = (cur.getXSize(), cur.getYSize(), cur.getXOrigin(), cur.getYOrigin())
            wp.setUndecorated(True)
            wp.setOrigin(0, 0)
            wp.setSize(self.base.pipe.getDisplayWidth(), self.base.pipe.getDisplayHeight())
        else:
            w, h, x, y = self.windowed
            wp.setUndecorated(False)
            wp.setOrigin(max(0, x), max(0, y))
            wp.setSize(w, h)
        win.requestProperties(wp)
        self.on = not self.on
        self.button["text"] = LEAVE if self.on else ENTER

    def leave(self):
        """Esc: out of full screen (in a window it does nothing)."""
        if self.on:
            self.toggle()
