"""Fight Lab cameras: four views.

    fight     - Fight camera: side-on to the two fighters, like a TV fighting game. It keeps both in shot and
                stays on the same side as they circle round (it never jumps to the other side).
    shoulder  - Over the shoulder: behind you, looking past you at the other fighter
    ring      - Ring view: your ring from high up at the side
    all       - All rings: every ring from high up

Every view zooms in and out (mouse wheel, or + and -): wheel(factor) with factor < 1 zooms in.
Every view also swings round and tilts: drag with the right mouse button (or turn(degrees) for keys such as Q and E),
and reset_view() puts it back.
Call update() every frame with your fighter's and the other fighter's feet positions (Point3, or None).
"""
import math

from panda3d.core import MouseButton, Point3, Vec3

MODES = ["fight", "shoulder", "ring", "all"]
NAMES = {"fight": "Fight camera", "shoulder": "Over the shoulder", "ring": "Ring view", "all": "All rings"}


class FightCamera:
    def __init__(self, base, mode="fight"):
        self.base = base
        self.mode = mode if mode in MODES else "fight"
        self.pos = self.look = None
        self.fov = 50.0
        self.zoom = {m: 1.0 for m in MODES}  # 0.4 (close) to 2.5 (far) for each view
        self.side = None                     # the fight camera's side of the fighters: a direction on the floor
        self.rig_shown, self.rig_check = True, 0
        self.orbit, self.tilt = 0.0, 0.0      # your own view: degrees swung round, and tilted up (or down)
        self.drag_from = None
        self.shift = 0.0                     # a panel covers the right of the screen: aim this share to the left

    def turn(self, degrees):
        """Swing the view round the ring (keys)."""
        self.orbit = (self.orbit + degrees) % 360

    def reset_view(self):
        self.orbit, self.tilt = 0.0, 0.0

    def mouse_drag(self):
        """Dragging with the right mouse button swings the view round (left and right) and tilts it (up and down)."""
        mw = self.base.mouseWatcherNode
        if mw is None or not mw.hasMouse() or not mw.isButtonDown(MouseButton.three()):
            self.drag_from = None
            return
        x, y = mw.getMouseX(), mw.getMouseY()
        if self.drag_from is not None:
            self.orbit = (self.orbit - (x - self.drag_from[0]) * 150) % 360
            self.tilt = max(-12.0, min(55.0, self.tilt - (y - self.drag_from[1]) * 60))
        self.drag_from = (x, y)

    def swing(self, offset):
        """An offset from what the camera looks at, swung round by orbit and tilted up by tilt (degrees)."""
        a, t = math.radians(self.orbit), math.radians(self.tilt)
        x = offset.x * math.cos(a) - offset.y * math.sin(a)  # swung round (about the vertical)
        y = offset.x * math.sin(a) + offset.y * math.cos(a)
        across = math.hypot(x, y)
        if across < 1e-6:
            return Vec3(offset)
        keep = math.cos(t)  # tilting up: less across, more height
        return Vec3(x * keep, y * keep, offset.z + across * math.sin(t))

    def set_shift(self, share):
        """Keep the action in the part of the screen a side panel doesn't cover (0 = no panel, 0.14 = a panel)."""
        self.shift = share

    @property
    def name(self):
        return NAMES[self.mode]

    def cycle(self):
        self.set_mode(MODES[(MODES.index(self.mode) + 1) % len(MODES)])

    def set_mode(self, mode):
        if mode in MODES:
            self.mode = mode
            self.pos = None  # cut straight to the new view

    def wheel(self, factor):
        """Zoom the current view in (factor < 1) or out (factor > 1)."""
        self.zoom[self.mode] = max(0.4, min(2.5, self.zoom[self.mode] * factor))

    def settings(self):
        return {"mode": self.mode, "zoom": {m: round(z, 2) for m, z in self.zoom.items()},
                "orbit": round(self.orbit, 1), "tilt": round(self.tilt, 1)}

    def restore(self, saved):
        """Put back a view and zoom levels saved earlier (e.g. in a learner's profile)."""
        try:
            if saved.get("mode") in MODES:
                self.set_mode(saved["mode"])
            for m, z in (saved.get("zoom") or {}).items():
                if m in MODES:
                    self.zoom[m] = max(0.4, min(2.5, float(z)))
            self.orbit = float(saved.get("orbit", 0.0)) % 360
            self.tilt = max(-12.0, min(55.0, float(saved.get("tilt", 0.0))))
        except (TypeError, ValueError, AttributeError):
            pass

    def show_rig(self, show):
        """The high views look down past the lighting rig, so it is hidden then (checked twice a second)."""
        self.rig_check += 1
        if show == self.rig_shown and self.rig_check < 30:
            return
        self.rig_shown, self.rig_check = show, 0
        for rig in self.base.render.findAllMatches("**/lighting_rig"):
            rig.show() if show else rig.hide()

    def update(self, dt, me=None, enemy=None, ring_centre=(0, 0), centres=(), shake=Vec3(0)):
        self.mouse_drag()
        cx, cy = ring_centre
        centre = Point3(cx, cy, 0)
        mode = self.mode
        if mode == "shoulder" and (me is None or enemy is None):
            mode = "fight"
        k, fov = 4.0, 45.0
        if mode == "fight":
            a = me if me is not None else enemy
            b = enemy if (me is not None and enemy is not None) else None
            if a is None:
                a = centre
            mid = (a + b) / 2 if b is not None else Point3(a)
            line = Vec3(b - a) if b is not None else Vec3(1, 0, 0)
            line.z = 0
            if line.length() < 0.05:
                line = Vec3(1, 0, 0)
            line.normalize()
            side = Vec3(-line.y, line.x, 0)  # at right angles to the line between them
            if self.side is None:
                # first time: stand on the side where you (me) are on the left of the screen
                self.side = -side if me is not None and b is not None else Vec3(0, -1, 0)
            if side.dot(self.side) < 0:
                side = -side  # stay on the same side as before
            self.side = Vec3(self.side + (side - self.side) * min(1.0, dt * 6))
            self.side.normalize()
            gap = (b - a).length() if b is not None else 0.0
            dist = (4.3 + gap * 0.8) * self.zoom["fight"] * (1 + self.shift * 2)
            want = Point3(mid.x, mid.y, 0) + self.swing(self.side * dist + Vec3(0, 0, 1.3 + dist * 0.1))
            want.z += max(a.z, 0) * 0.5
            look = Point3(mid.x, mid.y, 1.0 + max(a.z, 0) * 0.5)
            k, fov = 5.0, 50.0
        elif mode == "shoulder":
            to = Vec3(enemy - me)
            to.z = 0
            if to.length() < 0.05:
                to = Vec3(0, 1, 0)
            to.normalize()
            right = Vec3(to.y, -to.x, 0)
            z = self.zoom["shoulder"]
            want = Point3(me.x, me.y, 0) + self.swing(-to * 3.2 * z + right * 0.9 + Vec3(0, 0, 2.2 + 0.4 * z))
            look = Point3(enemy.x, enemy.y, 0.8)
            k, fov = 6.0, 60.0
        elif mode == "ring":
            z = self.zoom["ring"]
            want = centre + self.swing(Vec3(0, -9.5 * z, 7.5 * z))
            look = centre + Vec3(0, 0.5, 0.4)
            k, fov = 3.0, 50.0
        else:
            pts = [Point3(x, y, 0) for x, y in centres] or [centre]
            xs, ys = [p.x for p in pts], [p.y for p in pts]
            mid = Point3((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0)
            span = max(max(xs) - min(xs), max(ys) - min(ys)) + 10
            z = self.zoom["all"]
            want = mid + self.swing(Vec3(0, -span * 0.75 * z, span * 0.75 * z))
            look = mid + Vec3(0, 1, 0)
            k, fov = 2.5, 55.0
        self.show_rig(mode in ("fight", "shoulder"))
        if self.pos is None:
            self.pos, self.look, self.fov = Point3(want), Point3(look), fov
        a = min(1.0, dt * k)
        self.pos += (want - self.pos) * a
        self.look += (look - self.look) * a
        self.fov += (fov - self.fov) * min(1.0, dt * 4)
        cam = self.base.camera
        cam.setPos(self.pos + shake)
        cam.lookAt(self.look)
        lens = self.base.camLens
        lens.setFov(self.fov)
        lens.setFilmOffset(lens.getFilmSize().x * self.shift, 0)  # (moves the picture left, clear of a panel)
        lens.setNear(0.1)
        lens.setFar(300)

