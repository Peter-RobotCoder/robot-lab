"""Effects for Robot Wars: sparks at the hit point, smoke from damaged robots, flying debris, camera shake.

Kept cheap for low-spec laptops: a fixed pool of small pieces, reused.
"""
import math
import random

from panda3d.core import CardMaker, ColorBlendAttrib, PNMImage, Texture, TransparencyAttrib, Vec3

import rw_gfx
from engine.rw_mesh import bevel_box


def soft_dot_texture(size=64):
    img = PNMImage(size, size, 4)
    c = (size - 1) / 2
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            a = max(0.0, 1 - d) ** 1.8
            img.setXelA(x, y, 1, 1, 1, a)
    t = Texture("dot")
    t.load(img)
    return t


class Effects:
    def __init__(self, render, quality="high"):
        self.render = render
        self.rnd = random.Random()
        n_sparks = 400 if quality != "low" else 120
        # sparks: tiny glowing streaks, added on top of the scene (additive blend)
        self.spark_root = render.attachNewNode("sparks")
        self.spark_root.setLightOff(1)
        self.spark_root.setShaderOff(1)
        self.spark_root.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
        self.spark_root.setDepthWrite(False)
        self.spark_root.setBin("fixed", 30)
        spark_geom = bevel_box(0.012, 0.09, 0.012, 0.0).node()
        self.sparks = []
        for _ in range(n_sparks):
            np_ = self.spark_root.attachNewNode(spark_geom)
            np_.hide()
            self.sparks.append([np_, Vec3(0), 0.0, 0.0])  # node, velocity, life, max life
        # smoke: soft grey puffs that rise and fade
        dot = soft_dot_texture()
        cm = CardMaker("puff")
        cm.setFrame(-0.5, 0.5, -0.5, 0.5)
        self.smoke_root = render.attachNewNode("smoke")
        self.smoke_root.setLightOff(1)
        self.smoke_root.setShaderOff(1)
        self.smoke_root.setTransparency(TransparencyAttrib.M_alpha)
        self.smoke_root.setDepthWrite(False)
        self.smoke_root.setBin("fixed", 20)
        self.puffs = []
        for _ in range(90 if quality != "low" else 30):
            p = self.smoke_root.attachNewNode(cm.generate())
            p.setTexture(dot)
            p.setBillboardPointEye()
            p.hide()
            self.puffs.append([p, Vec3(0), 0.0, 0.0])
        self.fire_root = render.attachNewNode("fire")
        self.fire_root.setLightOff(1)
        self.fire_root.setShaderOff(1)
        self.fire_root.setAttrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                                       ColorBlendAttrib.O_one))  # soft round puffs, not squares
        self.fire_root.setDepthWrite(False)
        self.fire_root.setBin("fixed", 25)
        self.flames = []
        for _ in range(160 if quality != "low" else 50):
            f = self.fire_root.attachNewNode(cm.generate())
            f.setTexture(dot)
            f.setBillboardPointEye()
            f.hide()
            self.flames.append([f, Vec3(0), 0.0, 0.0])
        # debris: little chunks of armour
        self.debris = []
        self.shake = 0.0

    def _free(self, pool):
        for item in pool:
            if item[2] <= 0:
                return item
        return None

    def impact(self, pos, damage, kind, colour=(0.7, 0.7, 0.7)):
        """Sparks (and debris for big hits) where something hit."""
        count = {"flip": 8, "flame": 0, "bump": int(damage / 4), "wall": int(damage / 3)}.get(
            kind, int(min(40, 6 + damage * 1.5)))
        for _ in range(count):
            s = self._free(self.sparks)
            if s is None:
                break
            node = s[0]
            node.setPos(*pos)
            v = Vec3(self.rnd.uniform(-1, 1), self.rnd.uniform(-1, 1), self.rnd.uniform(0.2, 1.4))
            v.normalize()
            s[1] = v * self.rnd.uniform(3, 9)
            s[2] = s[3] = self.rnd.uniform(0.25, 0.6)
            node.show()
        if damage > 10 and kind in ("spinner", "drum", "hammer", "saw", "break"):
            for _ in range(int(min(6, damage / 5))):
                self.spawn_debris(pos, colour)
        self.shake = max(self.shake, min(0.35, damage / (200 if kind in ("bump", "wall") else 60)))

    def stream(self, pos, direction, count=4):
        """A shower of sparks thrown one way: a saw or chainsaw grinding into armour."""
        d = Vec3(*direction)
        for _ in range(count):
            s = self._free(self.sparks)
            if s is None:
                return
            s[0].setPos(*pos)
            v = d * self.rnd.uniform(5, 12) + Vec3(self.rnd.uniform(-1.5, 1.5), self.rnd.uniform(-1.5, 1.5),
                                                  self.rnd.uniform(0.5, 2.5))
            s[1] = v
            s[2] = s[3] = self.rnd.uniform(0.2, 0.55)
            s[0].show()

    def flame(self, pos, direction, amount=3):
        """Call each frame while a flame thrower fires: a jet of fire from the nozzle."""
        d = Vec3(*direction)
        for _ in range(amount):
            f = self._free(self.flames)
            if f is None:
                return
            f[0].setPos(pos[0], pos[1], pos[2])
            f[1] = d * self.rnd.uniform(4.5, 7.0) + Vec3(self.rnd.uniform(-0.6, 0.6), self.rnd.uniform(-0.6, 0.6),
                                                        self.rnd.uniform(0.2, 1.2))
            f[2] = f[3] = self.rnd.uniform(0.3, 0.45)
            f[0].show()
        if self.rnd.random() < 0.3:  # dark smoke at the end of the jet
            p = self._free(self.puffs)
            if p:
                p[0].setPos(pos[0] + d.x * 2.2, pos[1] + d.y * 2.2, pos[2] + 0.3)
                p[1] = Vec3(d.x, d.y, 1.2)
                p[2] = p[3] = self.rnd.uniform(0.8, 1.4)
                p[0].setColor(0.12, 0.1, 0.1, 1)
                p[0].show()

    def spawn_debris(self, pos, colour):
        node = rw_gfx.part(self.render, bevel_box(self.rnd.uniform(0.03, 0.08), self.rnd.uniform(0.03, 0.08), 0.012, 0.004),
                           "paint", colour)
        node.setPos(*pos)
        v = Vec3(self.rnd.uniform(-4, 4), self.rnd.uniform(-4, 4), self.rnd.uniform(2, 6))
        spin = Vec3(self.rnd.uniform(-700, 700), self.rnd.uniform(-700, 700), 0)
        self.debris.append([node, v, 4.0, spin])
        if len(self.debris) > 40:
            old = self.debris.pop(0)
            old[0].removeNode()

    def smoke(self, pos, amount):
        """Call each frame for a damaged robot: amount 0..1."""
        if self.rnd.random() > amount * 0.5:
            return
        p = self._free(self.puffs)
        if p is None:
            return
        p[0].setPos(pos[0] + self.rnd.uniform(-0.2, 0.2), pos[1] + self.rnd.uniform(-0.2, 0.2), pos[2] + 0.3)
        p[1] = Vec3(self.rnd.uniform(-0.2, 0.2), self.rnd.uniform(-0.2, 0.2), self.rnd.uniform(0.6, 1.2))
        p[2] = p[3] = self.rnd.uniform(1.2, 2.2)
        shade = self.rnd.uniform(0.15, 0.35)
        p[0].setColor(shade, shade, shade, 1)
        p[0].show()
        if amount > 0.7:
            f = self._free(self.flames)
            if f:
                f[0].setPos(pos[0] + self.rnd.uniform(-0.15, 0.15), pos[1] + self.rnd.uniform(-0.15, 0.15), pos[2] + 0.25)
                f[1] = Vec3(0, 0, self.rnd.uniform(1.0, 2.0))
                f[2] = f[3] = self.rnd.uniform(0.25, 0.5)
                f[0].show()

    def update(self, dt):
        g = Vec3(0, 0, -9.81)
        for s in self.sparks:
            if s[2] <= 0:
                continue
            s[2] -= dt
            if s[2] <= 0:
                s[0].hide()
                continue
            s[1] += g * dt
            node = s[0]
            node.setPos(node.getPos() + s[1] * dt)
            node.lookAt(node.getPos() + s[1])
            f = s[2] / s[3]
            node.setColor(1.0, 0.55 + 0.4 * f, 0.15 + 0.5 * f * f, 1)
            node.setScale(1, 0.5 + f, 1)
            if node.getZ() < 0.01 and s[1].z < 0:  # bounce off the floor
                s[1].z *= -0.35
                s[1].x *= 0.6
                s[1].y *= 0.6
        for p in self.puffs:
            if p[2] <= 0:
                continue
            p[2] -= dt
            if p[2] <= 0:
                p[0].hide()
                continue
            f = 1 - p[2] / p[3]
            p[0].setPos(p[0].getPos() + p[1] * dt)
            p[0].setScale(0.35 + f * 1.4)
            p[0].setAlphaScale(0.55 * (1 - f))
        for fl in self.flames:
            if fl[2] <= 0:
                continue
            fl[2] -= dt
            if fl[2] <= 0:
                fl[0].hide()
                continue
            f = fl[2] / fl[3]
            fl[1] *= max(0.0, 1 - dt * 2.5)  # flames slow down and rise
            fl[1].z += dt * 3.0
            fl[0].setPos(fl[0].getPos() + fl[1] * dt)
            fl[0].setScale(0.25 + 0.8 * (1 - f))
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
            if d[2] < 1:
                node.setAlphaScale(max(0.0, d[2]))
        self.debris = [d for d in self.debris if d[2] > 0 or d[0].removeNode()]
        self.shake = max(0.0, self.shake - dt * 1.2)

    def shake_offset(self):
        s = self.shake
        return Vec3(self.rnd.uniform(-s, s), self.rnd.uniform(-s, s), self.rnd.uniform(-s, s) * 0.5)
