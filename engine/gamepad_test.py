"""engine/gamepad.py with a pretend controller (CHANGE 170): no pad needed.

    shared-world-demo\\.venv\\Scripts\\python engine\\gamepad_test.py      (from the ClubCodersAI folder)

A pretend Panda3D device with the buttons and axes of an Xbox-style pad, and one with only numbered buttons and
a hat (a generic HID pad): the stick's dead zone, the d-pad as the stick, the triggers, a press counted once, a
pad unplugged and another used, a pad with no names still found. Exit code 0 = all fine.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from panda3d.core import GamepadButton, InputDevice  # noqa: E402
from engine import gamepad  # noqa: E402

results = []


def check(name, ok, note=""):
    results.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({note})" if note and not ok else ""))


class State:
    def __init__(self, known=True):
        self.known, self.pressed, self.value = known, False, 0.0


class Device:
    def __init__(self, name, buttons, axes, cls=InputDevice.DeviceClass.gamepad):
        self.name, self.device_class, self.connected = name, cls, True
        self.b = {str(b): State() for b in buttons}
        self.a = {str(a): State() for a in axes}
        self.polls = 0

    def findButton(self, b):
        return self.b.get(str(b), State(False))

    def findAxis(self, a):
        return self.a.get(str(a), State(False))

    def poll(self):
        self.polls += 1

    def press(self, b, on=True):
        self.b[str(b)].pressed = on

    def axis(self, a, v):
        self.a[str(a)].value = v


class Devices:
    def __init__(self, devs):
        self.devs = devs

    def getDevices(self):
        return list(self.devs)


class Base:
    def __init__(self, devs):
        self.devices, self.events = Devices(devs), {}

    def accept(self, name, fn):
        self.events[name] = fn


G, A = GamepadButton, InputDevice.Axis
XBOX = ([G.face_a(), G.face_b(), G.face_x(), G.face_y(), G.lshoulder(), G.rshoulder(), G.back(), G.start(),
         G.dpad_up(), G.dpad_down(), G.dpad_left(), G.dpad_right()],
        [A.left_x, A.left_y, A.left_trigger, A.right_trigger])


def main():
    pad_dev = Device("Xbox Controller", *XBOX)
    base = Base([pad_dev])
    pad = gamepad.Pad(base)
    s = pad.read()
    check("an idle pad: connected, nothing held, the stick at 0", s and not s.held and (s.x, s.y) == (0.0, 0.0) and pad_dev.polls == 1)
    pad_dev.axis(A.left_x, 0.15)
    pad_dev.axis(A.left_y, -0.1)
    s = pad.read()
    check("a stick resting a little off the middle reads 0 (the dead zone)", (s.x, s.y) == (0.0, 0.0))
    pad_dev.axis(A.left_x, 0.0)
    pad_dev.axis(A.left_y, 1.0)
    s = pad.read()
    check("the stick pushed up reads y = 1", abs(s.y - 1.0) < 1e-9 and s.x == 0.0, f"{s.x}, {s.y}")
    pad_dev.axis(A.left_y, 0.61)
    s = pad.read()
    half = (0.61 - gamepad.DEAD) / (1 - gamepad.DEAD)
    check(f"analogue: the stick half way reads half ({s.y:.2f}), a trigger half way half ({gamepad.trigger(0.55):.2f})",
          abs(s.y - half) < 1e-9 and abs(gamepad.trigger(0.55) - 0.5) < 1e-9 and gamepad.trigger(0.08) == 0.0)
    pad_dev.axis(A.left_y, 1.0)
    pad_dev.press(G.face_a())
    pad_dev.axis(A.right_trigger, 0.9)
    s = pad.read()
    check("the bottom face button and the right trigger: held, pressed once", {"south", "rt"} <= s.held and
          {"south", "rt"} <= s.pressed and abs(s.rt - 0.8 / 0.9) < 1e-9, f"{s.held} {s.pressed} {s.rt}")
    s = pad.read()
    check("...still held, not pressed again", "south" in s.held and not s.pressed)
    pad_dev.press(G.dpad_left())
    s = pad.read()
    check("the d-pad counts as the stick", s.x == -1 and "left" in s.pressed)
    other = Device("Wireless Controller", *XBOX)
    base.devices.devs.append(other)
    base.events["connect-device"](other)
    check("a second pad plugged in is the one used", pad.name() == "Wireless Controller")
    base.devices.devs.remove(other)
    other.connected = False
    base.events["disconnect-device"](other)
    check("...unplugged, the first is used again", pad.name() == "Xbox Controller")
    pad_dev.connected = False
    check("a pad that has gone reads as no pad", not pad.read())
    generic = Device("USB Gamepad", [G.face_1(), G.face_2(), G.hat_up(), G.hat_down(), G.hat_left(), G.hat_right()],
                     [A.x, A.y], InputDevice.DeviceClass.flight_stick)
    gp = gamepad.Pad(Base([generic]))
    generic.press(G.face_1())
    generic.press(G.hat_right())
    generic.axis(A.y, 0.8)
    s = gp.read()
    check("a pad with numbered buttons and a hat: button 1 as the bottom one, the hat as the d-pad, its x and y",
          "south" in s.held and s.x == 1 and s.y > 0.5, f"{s.held} {s.x} {s.y}")
    print(f"{sum(results)} of {len(results)} passed")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
