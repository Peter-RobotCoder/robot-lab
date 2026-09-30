"""Fight Lab effects: sparks and flashes where hits land, guard flashes on blocks, electric sparks, flames,
dust when a fighter hits the floor, bits of armour flying off robots, and camera shake.

Kept cheap for low-spec laptops: a fixed pool of small pieces, reused.
"""
import math
import random

from panda3d.core import CardMaker, ColorBlendAttrib, PNMImage, Texture, TransparencyAttrib, Vec3

import fight_gfx
from rw_mesh import bevel_box

# spark colours: (start colour, end colour) for each kind of hit
SPARKS = {"hot": ((1.0, 0.95, 0.6), (1.0, 0.35, 0.05)), "blue": ((0.8, 0.95, 1.0), (0.2, 0.45, 1.0)),
          "white": ((1.0, 1.0, 1.0), (0.7, 0.7, 0.8)), "gold": ((1.0, 1.0, 0.6), (1.0, 0.6, 0.0))}
# kind: (sparks, spark colour, flash colour, flash size, ring?)
KINDS = {
    "punch": (10, "hot", (1.0, 0.95, 0.85), 0.5, False),
    "kick": (14, "hot", (1.0, 0.9, 0.75), 0.65, True),
    "low": (12, "hot", (1.0, 0.9, 0.75), 0.55, False),
    "high": (18, "hot", (1.0, 0.9, 0.7), 0.8, True),
    "special": (30, "blue", (0.6, 0.85, 1.0), 1.1, True),
    "counter": (36, "gold", (1.0, 0.85, 0.2), 1.3, True),
    "block": (8, "blue", (0.6, 0.8, 1.0), 0.55, False),
    "throw": (6, "white", (1.0, 1.0, 1.0), 0.6, True),
    "zap": (30, "blue", (0.4, 0.7, 1.0), 0.9, False),
    "fire": (8, "hot", (1.0, 0.5, 0.1), 0.8, False),
    "wall": (10, "white", (1.0, 1.0, 1.0), 0.6, False),
    "spikes": (16, "white", (1.0, 0.4, 0.3), 0.8, True),
    "land": (0, "white", None, 0.0, False),
    "ringout": (0, "white", (1.0, 0.6, 0.2), 1.0, True),
}


def soft_dot_texture(size=64):
    img = PNMImage(size, size, 4)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            img.setXelA(x, y, 1, 1, 1, max(0.0, 1 - d) ** 1.8)
    t = Texture("dot")
    t.load(img)
    return t


def ring_texture(size=64):
    """A thin bright ring: the shock wave of a big hit."""
    img = PNMImage(size, size, 4)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            img.setXelA(x, y, 1, 1, 1, max(0.0, 1 - abs(d - 0.8) / 0.15) ** 1.5)
    t = Texture("ring")
    t.load(img)
    return t


def add_blend(root, alpha=False):
    root.setLightOff(1)
    root.setShaderOff(1)
    if alpha:  # soft round puffs, not squares
        root.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                             ColorBlendAttrib.O_one))
    else:
        root.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
    root.setDepthWrite(False)


class Effects:
    def __init__(self, render, quality="high"):
        self.render = render
        self.rnd = random.Random()
        low = quality == "low"
        cm = CardMaker("card")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        dot, ring = soft_dot_texture(), ring_texture()
        # sparks: tiny glowing streaks
        self.spark_root = render.attachNewNode("sparks")
        add_blend(self.spark_root)
        self.spark_root.setBin("fixed", 30)
        spark_geom = bevel_box(0.012, 0.08, 0.012, 0.0).node()
        self.sparks = []
        for _ in range(120 if low else 360):
            np_ = self.spark_root.attachNewNode(spark_geom)
            np_.hide()
            self.sparks.append([np_, Vec3(0), 0.0, 0.0, "hot"])  # node, velocity, life, max life, colour
        # flashes (a bright blob) and shock rings, facing the camera
        self.flash_root = render.attachNewNode("flashes")
        add_blend(self.flash_root, alpha=True)
        self.flash_root.setBin("fixed", 32)
        self.flash_root.setDepthTest(False)  # a hit flash always shows, even half inside a fighter
        self.flashes = []
        for i in range(24 if low else 40):
            f = self.flash_root.attachNewNode(cm.generate())
            f.setTexture(ring if i % 2 else dot)
            f.setBillboardPointEye()
            f.hide()
            self.flashes.append([f, 0.0, 0.0, 0.0, i % 2 == 1, (1, 1, 1)])  # node, life, max, size, ring?, colour
        # smoke and dust: soft grey puffs
        self.smoke_root = render.attachNewNode("smoke")
        self.smoke_root.setLightOff(1)
        self.smoke_root.setShaderOff(1)
        self.smoke_root.setTransparency(TransparencyAttrib.M_alpha)
        self.smoke_root.setDepthWrite(False)
        self.smoke_root.setBin("fixed", 20)
        self.puffs = []
        for _ in range(30 if low else 80):
            p = self.smoke_root.attachNewNode(cm.generate())
            p.setTexture(dot)
            p.setBillboardPointEye()
            p.hide()
            self.puffs.append([p, Vec3(0), 0.0, 0.0])
        # flames
        self.fire_root = render.attachNewNode("fire")
        add_blend(self.fire_root, alpha=True)
        self.fire_root.setBin("fixed", 25)
        self.flames = []
        for _ in range(50 if low else 140):
            f = self.fire_root.attachNewNode(cm.generate())
            f.setTexture(dot)
            f.setBillboardPointEye()
            f.hide()
            self.flames.append([f, Vec3(0), 0.0, 0.0])
        self.debris = []
        self.shake = 0.0

    @staticmethod
    def _free(pool):
        for item in pool:
            if item[2 if len(item) != 6 else 1] <= 0:
                return item
        return None

    # ---------- things that happen ----------
    def impact(self, pos, damage, kind, colour=(0.7, 0.7, 0.7), robot=True):
        """Where a hit (or a block, a zap, a fall...) happened."""
        sparks, spark_col, flash_col, flash_size, shock = KINDS.get(kind, KINDS["punch"])
        n = int(sparks * (0.6 + min(1.5, damage / 12))) if robot or kind in ("zap", "counter", "special", "fire") \
            else int(sparks * 0.3)
        for _ in range(n):
            s = self._free(self.sparks)
            if s is None:
                break
            s[0].setPos(*pos)
            v = Vec3(self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1), self.rnd.uniform(-0.3, 1.2))
            v.normalize()
            s[1] = v * self.rnd.uniform(2.5, 8 if kind != "zap" else 5)
            s[2] = s[3] = self.rnd.uniform(0.15, 0.45)
            s[4] = spark_col
            s[0].show()
        if flash_col:
            size = flash_size * (0.8 + min(1.0, damage / 15) * 0.6)
            self.flash(pos, flash_col, size, ring=False, life=0.12)
            if shock or damage >= 12:
                self.flash(pos, flash_col, size * 1.3, ring=True, life=0.22)
        if kind == "fire":
            for _ in range(10):
                self.flame(pos, (0, 0, 1), 1)
        if kind in ("land", "ringout", "throw"):
            self.dust(pos, 6 if kind == "land" else 10)
        if robot and damage > 12 and kind in ("kick", "high", "special", "counter"):
            for _ in range(int(min(4, damage / 6))):
                self.spawn_debris(pos, colour)
        self.shake = max(self.shake, min(0.3, damage / (90 if kind not in ("block", "land") else 250)))

    def flash(self, pos, colour, size, ring=False, life=0.12):
        f = next((f for f in self.flashes if f[1] <= 0 and f[4] == ring), None)
        if f is None:
            return
        f[0].setPos(*pos)
        f[1] = f[2] = life
        f[3], f[5] = size, colour
        f[0].show()

    def dust(self, pos, amount=6):
        for _ in range(amount):
            p = self._free(self.puffs)
            if p is None:
                return
            p[0].setPos(pos[0] + self.rnd.uniform(-0.3, 0.3), pos[1] + self.rnd.uniform(-0.3, 0.3), max(0.05, pos[2]))
            p[1] = Vec3(self.rnd.uniform(-1.2, 1.2), self.rnd.uniform(-1.2, 1.2), self.rnd.uniform(0.2, 0.6))
            p[2] = p[3] = self.rnd.uniform(0.5, 0.9)
            shade = self.rnd.uniform(0.5, 0.7)
            p[0].setColor(shade, shade, shade * 1.05, 1)
            p[0].show()

    def flame(self, pos, direction, amount=3):
        d = Vec3(*direction)
        for _ in range(amount):
            f = self._free(self.flames)
            if f is None:
                return
            f[0].setPos(pos[0] + self.rnd.uniform(-0.2, 0.2), pos[1] + self.rnd.uniform(-0.2, 0.2), pos[2])
            f[1] = d * self.rnd.uniform(2.0, 4.0) + Vec3(self.rnd.uniform(-0.6, 0.6), self.rnd.uniform(-0.6, 0.6), 0.5)
            f[2] = f[3] = self.rnd.uniform(0.3, 0.5)
            f[0].show()

    def smoke(self, pos, amount):
        """Call each frame for a knocked-out robot: amount 0..1."""
        if self.rnd.random() > amount * 0.4:
            return
        p = self._free(self.puffs)
        if p is None:
            return
        p[0].setPos(pos[0] + self.rnd.uniform(-0.2, 0.2), pos[1] + self.rnd.uniform(-0.2, 0.2), pos[2] + 0.2)
        p[1] = Vec3(self.rnd.uniform(-0.2, 0.2), self.rnd.uniform(-0.2, 0.2), self.rnd.uniform(0.6, 1.2))
        p[2] = p[3] = self.rnd.uniform(1.2, 2.0)
        shade = self.rnd.uniform(0.15, 0.3)
        p[0].setColor(shade, shade, shade, 1)
        p[0].show()

    def spawn_debris(self, pos, colour):
        node = fight_gfx.part(self.render, bevel_box(self.rnd.uniform(0.02, 0.05), self.rnd.uniform(0.02, 0.05), 0.01,
                                                     0.003), "paint", colour)
        node.setPos(*pos)
        v = Vec3(self.rnd.uniform(-3, 3), self.rnd.uniform(-3, 3), self.rnd.uniform(2, 5))
        spin = Vec3(self.rnd.uniform(-700, 700), self.rnd.uniform(-700, 700), 0)
        self.debris.append([node, v, 3.0, spin])
        if len(self.debris) > 30:
            self.debris.pop(0)[0].removeNode()

    # ---------- every frame ----------
    def update(self, dt):
        g = Vec3(0, 0, -9.81)
        for s in self.sparks:
            if s[2] <= 0:
                continue
            s[2] -= dt
            if s[2] <= 0:
                s[0].hide()
                continue
            s[1] += g * dt * 0.6
            node = s[0]
            node.setPos(node.getPos() + s[1] * dt)
            node.lookAt(node.getPos() + s[1])
            f = s[2] / s[3]
            a, b = SPARKS[s[4]]
            node.setColor(*(y + (x - y) * f for x, y in zip(a, b)), 1)
            node.setScale(1, 0.5 + f, 1)
            if node.getZ() < 0.01 and s[1].z < 0:  # bounce off the floor
                s[1] = Vec3(s[1].x * 0.6, s[1].y * 0.6, -s[1].z * 0.35)
        for f in self.flashes:
            if f[1] <= 0:
                continue
            f[1] -= dt
            if f[1] <= 0:
                f[0].hide()
                continue
            t = 1 - f[1] / f[2]  # 0 at the start, 1 at the end
            grow = (0.4 + 1.0 * t) if f[4] else (1.0 + 0.5 * t)
            f[0].setScale(f[3] * grow)
            fade = 1 - t
            f[0].setColor(*f[5], fade)
        for p in self.puffs:
            if p[2] <= 0:
                continue
            p[2] -= dt
            if p[2] <= 0:
                p[0].hide()
                continue
            f = 1 - p[2] / p[3]
            p[1] *= max(0.0, 1 - dt * 2)
            p[0].setPos(p[0].getPos() + p[1] * dt)
            p[0].setScale(0.3 + f * 1.2)
            p[0].setAlphaScale(0.5 * (1 - f))
        for fl in self.flames:
            if fl[2] <= 0:
                continue
            fl[2] -= dt
            if fl[2] <= 0:
                fl[0].hide()
                continue
            f = fl[2] / fl[3]
            fl[1] *= max(0.0, 1 - dt * 2.5)
            fl[1].z += dt * 3.0
            fl[0].setPos(fl[0].getPos() + fl[1] * dt)
            fl[0].setScale(0.25 + 0.6 * (1 - f))
            fl[0].setColor(1.0 * f + 0.2, (0.35 + 0.4 * f * f) * f, 0.08 * f * f, 1)
        for d in self.debris:
            if d[2] <= 0:
                continue
            d[2] -= dt
            node = d[0]
            d[1] += g * dt
            p = node.getPos() + d[1] * dt
            if p.z < 0.02:
                p.z = 0.02
                d[1] = Vec3(d[1].x * 0.5, d[1].y * 0.5, -d[1].z * 0.3)
                d[3] *= 0.5
            node.setPos(p)
            node.setHpr(node.getHpr() + d[3] * dt)
        for d in [d for d in self.debris if d[2] <= 0]:
            d[0].removeNode()
        self.debris = [d for d in self.debris if d[2] > 0]
        self.shake = max(0.0, self.shake - dt * 1.2)

    def shake_offset(self):
        s = self.shake
        return Vec3(self.rnd.uniform(-s, s), self.rnd.uniform(-s, s), self.rnd.uniform(-s, s) * 0.5)
