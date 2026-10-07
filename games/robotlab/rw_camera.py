"""Game cameras for Robot Wars and Robot Lab: five views.

    third  - Third person: behind your robot, following it
    fpv    - First person: from the front of your robot, looking where it's going
    zoom   - Zoomed arena follow: a TV camera on the arena rail that turns and zooms to keep the action in frame
    arena  - Full arena: the whole arena from above
    centre - Centre camera: a fixed camera, lower down, aimed at the middle of the arena (it never follows)

Every view zooms in and out (mouse wheel, or + and -): wheel(factor) with factor < 1 zooms in.
Every view also swings round and tilts: drag with the right mouse button (or turn(degrees) for keys such as Q and E);
reset_view() puts it back.

Call update() every frame with your robot's chassis node and the positions of the robots to keep in shot.
"""
import math

from panda3d.core import MouseButton, Point3, Vec3

MODES = ["third", "fpv", "zoom", "arena", "centre"]
NAMES = {"third": "Third person", "fpv": "First person", "zoom": "Zoomed arena follow", "arena": "Full arena",
         "centre": "Centre camera"}
HALF = 10.0  # half the arena size (metres)


class GameCamera:
    def __init__(self, base, mode="third"):
        self.base = base
        self.mode = mode if mode in MODES else "third"
        self.pos = self.look = None
        self.fov = 70.0
        self.dist = 6.5          # third person: how far behind (1.5 to 30 m)
        self.fpv_scale = 1.0     # first person: lens zoom (0.3 = telephoto, 1.3 = very wide)
        self.zoom_scale = 1.0    # zoomed follow: tighter or wider framing (0.2 to 4)
        self.arena_scale = 1.0   # full arena: closer or further away (0.35 to 2)
        self.centre_scale = 1.0  # centre camera: closer or further away (0.35 to 2)
        self.angles = {m: [0.0, 0.0] for m in MODES}  # each view's own swing round and tilt up, degrees (CHANGE 111)
        self.pans = {m: 0.0 for m in MODES}             # ...and how far it was moved sideways, metres (CHANGE 112)
        self.drag_from = None
        self.rig_shown, self.rig_check = True, 0
        self.look_z = 0.0        # (the height of what the view looks at: a swung camera stays above the floor)

    @property
    def orbit(self):
        return self.angles[self.mode][0]

    @orbit.setter
    def orbit(self, value):
        self.angles[self.mode][0] = value

    @property
    def tilt(self):
        return self.angles[self.mode][1]

    @tilt.setter
    def tilt(self, value):
        self.angles[self.mode][1] = value

    def turn(self, degrees):
        """Swing the view round (keys)."""
        self.orbit = (self.orbit + degrees) % 360

    def pan(self, metres):
        """Move the view sideways (sideways scroll on a touchpad: CHANGE 112), this view only."""
        self.pans[self.mode] = max(-12.0, min(12.0, self.pans[self.mode] + metres))

    def reset_view(self):
        """Home: this view back as it comes (its swing, tilt and sideways move)."""
        self.angles[self.mode] = [0.0, 0.0]
        self.pans[self.mode] = 0.0

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
        if not (self.orbit or self.tilt):
            return Vec3(offset)
        a, t = math.radians(self.orbit), math.radians(self.tilt)
        x = offset.x * math.cos(a) - offset.y * math.sin(a)  # swung round (about the vertical)
        y = offset.x * math.sin(a) + offset.y * math.cos(a)
        across = math.hypot(x, y)
        if across < 1e-6:
            return Vec3(offset)
        keep = math.cos(t)  # tilting up: less across, more height
        return Vec3(x * keep, y * keep, max(0.3 - self.look_z, offset.z + across * math.sin(t)))

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
        if self.mode == "third":
            self.dist = max(1.5, min(30.0, self.dist * factor))
        elif self.mode == "fpv":
            self.fpv_scale = max(0.3, min(1.3, self.fpv_scale * factor))
        elif self.mode == "zoom":
            self.zoom_scale = max(0.2, min(4.0, self.zoom_scale * factor))
        elif self.mode == "arena":
            self.arena_scale = max(0.35, min(2.0, self.arena_scale * factor))
        else:
            self.centre_scale = max(0.35, min(2.0, self.centre_scale * factor))

    def settings(self):
        return {"mode": self.mode, "dist": round(self.dist, 2), "fpv": round(self.fpv_scale, 2),
                "zoom": round(self.zoom_scale, 2), "arena": round(self.arena_scale, 2),
                "centre": round(self.centre_scale, 2), "orbit": round(self.orbit, 1), "tilt": round(self.tilt, 1),
                "angles": {m: [round(o, 1), round(t, 1)] for m, (o, t) in self.angles.items()},
                "pans": {m: round(p, 2) for m, p in self.pans.items()}}

    def restore(self, saved):
        """Put back a view and zoom levels saved earlier (e.g. in a learner's profile)."""
        try:
            if saved.get("mode") in MODES:
                self.set_mode(saved["mode"])
            self.dist = max(1.5, min(30.0, float(saved.get("dist", self.dist))))
            self.fpv_scale = max(0.3, min(1.3, float(saved.get("fpv", self.fpv_scale))))
            self.zoom_scale = max(0.2, min(4.0, float(saved.get("zoom", self.zoom_scale))))
            self.arena_scale = max(0.35, min(2.0, float(saved.get("arena", self.arena_scale))))
            self.centre_scale = max(0.35, min(2.0, float(saved.get("centre", self.centre_scale))))
            if isinstance(saved.get("angles"), dict):  # (each view's own: CHANGE 111)
                for m, (o, t) in saved["angles"].items():
                    if m in MODES:
                        self.angles[m] = [float(o) % 360, max(-12.0, min(55.0, float(t)))]
            else:  # (saved before each view had its own: the one swing goes to the view in use)
                self.orbit = float(saved.get("orbit", 0.0)) % 360
                self.tilt = max(-12.0, min(55.0, float(saved.get("tilt", 0.0))))
            if isinstance(saved.get("pans"), dict):
                for m, p in saved["pans"].items():
                    if m in MODES:
                        self.pans[m] = max(-12.0, min(12.0, float(p)))
        except (TypeError, ValueError, AttributeError):
            pass

    def show_rig(self, show):
        """The full arena view looks down from above the overhead lighting rig, so the rig is hidden then.
        (Checked every half second in case the arena was rebuilt.)"""
        self.rig_check += 1
        if show == self.rig_shown and self.rig_check < 30:
            return
        self.rig_shown, self.rig_check = show, 0
        for rig in self.base.render.findAllMatches("**/lighting_rig"):
            rig.show() if show else rig.hide()

    def update(self, dt, me=None, front=0.8, targets=(), shake=Vec3(0)):
        """me: your robot's chassis node (or None); front: how far its nose is from its middle;
        targets: positions of the robots still fighting, for the arena views."""
        self.mouse_drag()
        render = self.base.render
        live = [Point3(p) for p in targets if p.z > -1.0]
        centre = sum(live, Point3(0)) / len(live) if live else Point3(0, 0, 0)
        centre.z = 0.3
        mine = me.getPos(render) if me is not None else None
        if mine is not None and mine.z < -1.0:  # fallen in the pit: watch the arena instead
            mine = None
        if self.mode in ("third", "fpv") and mine is None:
            focus_mode = "zoom"
        else:
            focus_mode = self.mode
        k, fov = 5.0, 70.0
        if focus_mode == "third":
            fwd = me.getQuat(render).getForward()
            flat = Vec3(fwd.x, fwd.y, 0)
            if flat.length() < 0.1:
                flat = Vec3(0, 1, 0)
            flat.normalize()
            self.look_z = 0.0
            want = Point3(mine.x, mine.y, 0) + self.swing(Vec3(0, 0, self.dist * 0.55) - flat * self.dist)
            if self.dist < 9:  # low down: stay inside the arena, in front of the wall posts (higher up clears them)
                inside = HALF - 0.6
                back = Vec3(want.x - mine.x, want.y - mine.y, 0).length()
                want.x, want.y = max(-inside, min(inside, want.x)), max(-inside, min(inside, want.y))
                lost = back - Vec3(want.x - mine.x, want.y - mine.y, 0).length()
                want.z += max(0.0, lost) * 1.1  # squeezed by a wall: go up instead of back
            look = Point3(mine.x, mine.y, 0.4) + (flat * 2.0 if not (self.orbit or self.tilt) else Vec3(0))
        elif focus_mode == "fpv":
            q = me.getQuat(render)
            fwd, up = q.getForward(), q.getUp()
            flat = Vec3(fwd.x, fwd.y, 0)
            if flat.length() < 0.1 or up.z < 0.3:  # flipped over: keep looking the way we were
                flat = Vec3(self.look - self.pos) if self.pos is not None else Vec3(0, 1, 0)
                flat.z = 0
            flat.normalize()
            want = Point3(mine.x, mine.y, max(0.35, mine.z + 0.45)) + flat * (front + 0.15)
            self.look_z = 50.0  # (looking round from the robot: up and down are both fine)
            look = want - self.swing(Vec3(0, 0, 0.35) - flat * 6.0)
            k, fov = 14.0, 95.0 * self.fpv_scale
        elif focus_mode == "zoom":
            target = Point3(mine.x, mine.y, 0.3) if (mine is not None and self.mode != "zoom") else centre
            if self.mode == "zoom" and mine is not None and live:
                target = (Point3(mine.x, mine.y, 0.3) + centre) / 2
            # a TV camera sliding along the south rail, turning and zooming to fit the robots
            want = Point3(max(-8.0, min(8.0, target.x * 0.7)), -HALF - 1.2, 5.4)  # above the screen posts
            spread = max([(p - target).length() for p in live] + [1.5])
            self.look_z = target.z
            want = target + self.swing(want - target)
            dist = (want - target).length()
            fov = max(4.0, min(100.0, math.degrees(2 * math.atan((spread + 1.3) * self.zoom_scale / dist))))
            look = target
            k = 2.5
        elif focus_mode == "arena":  # full arena
            look = Point3(0, -2.0, 0)  # high and steep: all the floor (zoom moves the camera along its line)
            self.look_z = 0.0
            want, fov, k = look + self.swing((Point3(0, -HALF + 1.0, 17.0) - look) * self.arena_scale), 90.0, 3.0
        else:  # centre camera: fixed, lower down, aimed at the middle (it doesn't follow anyone)
            look = Point3(0, 0, 0.3)
            self.look_z = look.z
            want, fov, k = look + self.swing(Vec3(0, -HALF - 3.5, 6.5) * self.centre_scale), 62.0, 3.0
        self.show_rig(focus_mode != "arena")
        if self.pos is None:
            self.pos, self.look, self.fov = Point3(want), Point3(look), fov
        a = min(1.0, dt * k)
        self.pos += (want - self.pos) * a
        self.look += (look - self.look) * a
        self.fov += (fov - self.fov) * min(1.0, dt * 4)
        cam = self.base.camera
        shift = Vec3(0)
        if self.pans[self.mode]:  # moved sideways (CHANGE 112): the camera and what it looks at, across the view
            right = Vec3(self.look - self.pos).cross(Vec3(0, 0, 1))
            if right.length() > 1e-6:
                right.normalize()
                shift = right * self.pans[self.mode]
        cam.setPos(self.pos + shake + shift)
        cam.lookAt(self.look + shift)
        self.base.camLens.setFov(self.fov)
        self.base.camLens.setNear(0.05 if focus_mode == "fpv" else 0.2)
