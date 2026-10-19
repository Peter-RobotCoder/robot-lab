"""Game controllers for the windows (CHANGE 170): a USB or Bluetooth pad drives your robot, kart or fighter.

Panda3D finds them: Xbox pads through Windows' XInput; PlayStation, Nintendo Switch and other HID pads through raw
input (a Bluetooth pad once Windows has paired it, in Settings > Bluetooth). Every game reads the pad the same way,
by where a button is, not what it's called, so the layout is the same on every make:

    south  the bottom face button (Xbox A, PlayStation cross, Nintendo B)
    east   the right one          (Xbox B, PlayStation circle, Nintendo A)
    west   the left one           (Xbox X, PlayStation square, Nintendo Y)
    north  the top one            (Xbox Y, PlayStation triangle, Nintendo X)
    lb rb  the shoulder buttons;  lt rt the triggers (0 to 1);  back start;  up down left right: the d-pad

Pad.read() gives the state now: the left stick (x right, y up, -1 to 1, a dead zone in the middle; the d-pad
counts as the stick), the triggers, the buttons held, and the buttons pressed since the last read (a quick tap
between two frames isn't lost). The newest pad connected is the one used.
"""
import math

from panda3d.core import GamepadButton, InputDevice

DEAD = 0.22  # (a stick at rest is never quite at 0)

BUTTONS = {  # our name: Panda's buttons for it (a pad without names: its numbered buttons, the common HID order)
    "south": (GamepadButton.face_a(), GamepadButton.face_1()), "east": (GamepadButton.face_b(), GamepadButton.face_2()),
    "west": (GamepadButton.face_x(),), "north": (GamepadButton.face_y(),),
    "lb": (GamepadButton.lshoulder(),), "rb": (GamepadButton.rshoulder(),),
    "back": (GamepadButton.back(),), "start": (GamepadButton.start(),),
    "up": (GamepadButton.dpad_up(), GamepadButton.hat_up()), "down": (GamepadButton.dpad_down(), GamepadButton.hat_down()),
    "left": (GamepadButton.dpad_left(), GamepadButton.hat_left()),
    "right": (GamepadButton.dpad_right(), GamepadButton.hat_right()),
    "lt_button": (GamepadButton.ltrigger(),), "rt_button": (GamepadButton.rtrigger(),),
}
CLASSES = (InputDevice.DeviceClass.gamepad, InputDevice.DeviceClass.flight_stick)


def dead_zone(x, y):
    """The stick with its dead zone taken out, scaled so just past it is just past 0 (round, not square)."""
    r = math.hypot(x, y)
    if r < DEAD:
        return 0.0, 0.0
    k = min(1.0, (r - DEAD) / (1 - DEAD)) / r
    return max(-1.0, min(1.0, x * k)), max(-1.0, min(1.0, y * k))


def trigger(v):
    """A trigger with its dead zone (the first tenth) taken out, 0 to 1 smoothly from there."""
    return 0.0 if v <= 0.1 else min(1.0, (v - 0.1) / 0.9)


class PadState:
    def __init__(self, x=0.0, y=0.0, lt=0.0, rt=0.0, held=(), pressed=(), name=""):
        self.x, self.y, self.lt, self.rt = x, y, lt, rt
        self.held, self.pressed, self.name = set(held), set(pressed), name

    def __bool__(self):
        return bool(self.name)


class Pad:
    def __init__(self, base):
        self.base, self.device, self.was = base, None, set()
        self.buttons, self.axes = {}, {}
        for d in base.devices.getDevices():
            if d.device_class in CLASSES:
                self.use(d)
        base.accept("connect-device", self.connected)
        base.accept("disconnect-device", self.disconnected)

    def connected(self, d):
        if d.device_class in CLASSES:
            self.use(d)

    def disconnected(self, d):
        if d is self.device:
            self.device, self.was = None, set()
            others = [x for x in self.base.devices.getDevices() if x.device_class in CLASSES and x is not d]
            if others:
                self.use(others[-1])

    def use(self, d):
        self.device, self.was = d, set()
        self.buttons = {}
        for name, options in BUTTONS.items():
            for b in options:
                try:
                    found = d.findButton(b)
                except Exception:  # noqa: BLE001  (a device without that button)
                    continue
                if found is not None and found.known:
                    self.buttons[name] = b
                    break
        self.axes = {}
        for name, axis in (("x", InputDevice.Axis.left_x), ("y", InputDevice.Axis.left_y),
                           ("lt", InputDevice.Axis.left_trigger), ("rt", InputDevice.Axis.right_trigger),
                           ("x", InputDevice.Axis.x), ("y", InputDevice.Axis.y)):
            if name in self.axes:
                continue
            try:
                found = d.findAxis(axis)
            except Exception:  # noqa: BLE001
                continue
            if found is not None and found.known:
                self.axes[name] = axis

    def name(self):
        return self.device.name if self.device is not None else ""

    def read(self):
        d = self.device
        if d is None or not d.connected:
            return PadState()
        try:
            d.poll()
        except Exception:  # noqa: BLE001  (unplugged mid-read: no pad this frame)
            return PadState()
        held = set()
        for name, b in self.buttons.items():
            try:
                if d.findButton(b).pressed:
                    held.add(name)
            except Exception:  # noqa: BLE001
                pass
        val = {}
        for name, axis in self.axes.items():
            try:
                val[name] = d.findAxis(axis).value
            except Exception:  # noqa: BLE001
                val[name] = 0.0
        x, y = dead_zone(val.get("x", 0.0), val.get("y", 0.0))
        if "left" in held or "right" in held:
            x = ("right" in held) - ("left" in held)
        if "up" in held or "down" in held:
            y = ("up" in held) - ("down" in held)
        lt, rt = max(0.0, val.get("lt", 0.0)), max(0.0, val.get("rt", 0.0))
        lt, rt = max(lt, float("lt_button" in held)), max(rt, float("rt_button" in held))
        lt, rt = trigger(lt), trigger(rt)
        if lt > 0.5:
            held.add("lt")
        if rt > 0.5:
            held.add("rt")
        pressed = held - self.was
        self.was = held
        return PadState(x, y, lt, rt, held, pressed, d.name or "controller")
