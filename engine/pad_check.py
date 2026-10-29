"""Which controllers the windows can see, and what each button and stick does (CHANGE 170).

    shared-world-demo\\.venv\\Scripts\\python engine\\pad_check.py      (from the ClubCodersAI folder)

A small window listing every controller Panda3D has found (its name, make and model, the kind of device) and,
for the one the games use, the buttons held and the stick and triggers as the games read them (engine/gamepad.py:
south, east, west, north, lb, rb, lt, rt, back, start, the d-pad). Plug a pad in, or pair it by Bluetooth, while
it's open: it shows up. Close the window to stop. What it finds is kept in pad_check.log in the temp folder.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from panda3d.core import TextNode, loadPrcFileData  # noqa: E402

loadPrcFileData("", "win-size 900 520\nwindow-title Controller check\naudio-library-name null\n")
from direct.showbase.ShowBase import ShowBase  # noqa: E402
from engine import club_fonts, gamepad  # noqa: E402
club_fonts.use_default()  # (the windows' letters: Inter, SIL OFL, not Panda3D's own unlicensed font)

LOG = os.path.join(tempfile.gettempdir(), "pad_check.log")


class Check(ShowBase):
    def __init__(self):
        super().__init__()
        self.setBackgroundColor(0.08, 0.09, 0.12, 1)
        self.text = TextNode("info")
        self.text.setTextColor(1, 1, 1, 1)
        node = self.aspect2d.attachNewNode(self.text)
        node.setScale(0.055)
        node.setPos(-1.55, 0, 0.85)
        self.pad = gamepad.Pad(self)
        self.seen = set()
        self.log = open(LOG, "w", encoding="utf-8")
        self.taskMgr.add(self.frame, "pad check")

    def frame(self, task):
        lines = ["Controllers found:"]
        for d in self.devices.getDevices():
            what = (f"{d.name or '?'}  ({d.device_class.name}, {d.manufacturer or '?'}, "
                    f"vendor {d.vendor_id:04x} product {d.product_id:04x})")
            lines.append("  " + what)
            if what not in self.seen:
                self.seen.add(what)
                self.log.write("found " + what + "\n")
                self.log.flush()
        if len(lines) == 1:
            lines.append("  none: plug one in, or pair it by Bluetooth")
        s = self.pad.read()
        lines.append("")
        if s:
            lines.append(f"Used by the games: {s.name}")
            lines.append(f"  stick x {s.x:+.2f}  y {s.y:+.2f}    triggers left {s.lt:.2f}  right {s.rt:.2f}")
            lines.append(f"  held: {' '.join(sorted(s.held)) or '-'}")
            lines.append(f"  buttons it has: {' '.join(sorted(self.pad.buttons)) or 'none known'}")
            lines.append(f"  sticks and triggers it has: {' '.join(sorted(self.pad.axes)) or 'none known'}")
            if s.pressed:
                self.log.write(f"pressed {' '.join(sorted(s.pressed))}  (stick {s.x:+.2f} {s.y:+.2f})\n")
                self.log.flush()
        else:
            lines.append("No controller in use.")
        self.text.setText("\n".join(lines))
        return task.cont


Check().run()
