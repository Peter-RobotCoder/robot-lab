"""Craft Lab's people, creatures and Craft Bots, built from boxes with the atlas's faces (CHANGE 200, our own since
CHANGE 207), and moved from their wire records.

- A player is a Club Coder in a lab suit in their profile's colour: a big rounded head, a cyan visor across the eyes
  that glows in the dark, a backpack, short arms, chunky boots. The suit pieces they wear (visor, vest, boots) show
  in their material. Legs and arms swing with their speed, the head looks up and down, an arm swings as they dig.
- A Fluff is a round floating puff with big eyes on two tiny feet; it bobs as it goes, and when it has been brushed
  (F_SLEEP) it is a smaller, fluffed-down puff until it grows back.
- A Glitch is a flickering cluster of magenta and cyan pixels that keeps changing shape, with two bright eyes (it
  blinks from place to place: no hop).
- A Rust Walker is an old tracked robot, rust on a navy shell, coral eyes, a long magnet arm that swings to grab.
- A Bleep and a Craft Bot are Club Coders' own robots (the Bot wears the club's mark on its chest).
A red flash when hurt, a name over a player.
"""
import math
import random

from panda3d.core import TextNode, Vec3

import craft_blocks as B
import craft_gfx as gfx
import craft_sim as sim

KIND_NAMES = {v: k for k, v in sim.KINDS.items()}
WHITE = (1, 1, 1)
SUIT_TILES = {"fluff": "fluff_white", "copper": "copper_block", "iron": "iron_block", "neon": "neon_block"}
TAG_Z = {"player": 2.0, "bot": 1.6}


def rgb01(c):
    return tuple(max(0.0, min(1.0, v / 255.0)) for v in list(c)[:3]) if c else (0.9, 0.9, 0.9)


def faces(front, other):
    """Six tiles for a box whose front (+y, the way the model faces) is different."""
    return (other, other, front, other, other, other)


def rounded(lo, hi, cut, tiles, colour):
    """A box with its edges taken off: three boxes, each a little short on two axes (a head, a puff of fluff)."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    return [((x0, y0 + cut, z0 + cut), (x1, y1 - cut, z1 - cut), tiles, colour),
            ((x0 + cut, y0, z0 + cut), (x1 - cut, y1, z1 - cut), tiles, colour),
            ((x0 + cut * 0.9, y0 + cut * 0.9, z0), (x1 - cut * 0.9, y1 - cut * 0.9, z1), tiles, colour)]


def glow(np_):
    """A part that shines in the dark (the visor, a Glitch's eyes, a Rust Walker's): drawn at full light whatever
    light it stands in (craft_gfx.glow_node when the drawing has one; else the creatures' shader told it is in full
    daylight, which keeps its fog and its hurt flash)."""
    f = getattr(gfx, "glow_node", None)
    if f is not None:
        f(np_)
        return
    if gfx.look():
        return
    np_.setShaderInput("u_here", (1.0, 0.0), 10)
    np_.setShaderInput("u_day", 1.0, 10)
    np_.setShaderInput("u_tint", Vec3(1, 1, 1), 10)


class Model:
    """One person or creature: a root (moved and turned), and the parts that swing."""

    def __init__(self, render, kind, colour=(200, 60, 50), name=None):
        self.kind = kind
        self.root = render.attachNewNode(f"{kind} model")
        self.body = self.root.attachNewNode("body")
        self.legs, self.arms, self.head = [], [], None
        self.phase = 0.0
        self.swing = 0.0
        self.t = 0.0
        self.worn = (0, 0, 0)
        self.suit_nodes = []
        c = rgb01(colour)
        build = getattr(self, "build_" + kind, self.build_player)
        build(c)
        gfx.ent_node(self.root)
        self.tag = None
        self.name = name
        if name:
            self.make_tag(name)

    def make_tag(self, name):
        if self.tag is None:
            t = TextNode("name")
            t.setText(name)
            t.setAlign(TextNode.ACenter)
            t.setTextColor(1, 1, 1, 1)
            t.setCardColor(0.035, 0.047, 0.09, 0.6)   # (the club's navy)
            t.setCardAsMargin(0.2, 0.2, 0.08, 0.04)
            t.setCardDecal(True)
            self.tag = self.root.attachNewNode(t)
            self.tag.setBillboardPointEye()
            self.tag.setScale(0.28)
            self.tag.setZ(TAG_Z.get(self.kind, 2.0))
            self.tag.setShaderOff(2)
            self.tag.setLightOff(2)
            self.tag.setFogOff(2)
        self.tag.node().setText(name)

    def say(self, text):
        """A speech bubble (a Craft Bot's "say"), or back to the name with None."""
        words = text or self.name
        if words and words != getattr(self, "_said", None):
            self._said = words
            self.make_tag(words)

    def limb(self, parent, pivot, parts):
        """A part that swings about pivot: its boxes [(lo, hi, tiles, colour)] hang from it."""
        joint = parent.attachNewNode("joint")
        joint.setPos(*pivot)
        gfx.model(joint, parts)
        return joint

    def shine(self, parent, parts, name="glow"):
        np_ = parent.attachNewNode(name)
        gfx.model(np_, parts)
        glow(np_)
        return np_

    # ---------- a Club Coder ----------
    def build_player(self, c):
        """0.7 wide and 1.7 tall (craft_sim's box), eyes at 1.55: legs to 0.55, the suit to 1.1, the head to 1.7."""
        suit = c
        self.legs = [self.limb(self.body, (x, 0, 0.55), [
            ((-0.11, -0.11, -0.4), (0.11, 0.11, 0), "suit", suit),
            ((-0.14, -0.16, -0.55), (0.14, 0.21, -0.37), "boot", WHITE)]) for x in (-0.13, 0.13)]
        gfx.model(self.body, [
            ((-0.25, -0.15, 0.53), (0.25, 0.15, 1.1), ("suit", "suit", "suit_front", "suit", "suit", "suit"), suit),
            ((-0.26, -0.16, 0.55), (0.26, 0.16, 0.64), ("glove", "glove", "belt", "glove", "glove", "glove"), WHITE),
            ((0.06, 0.15, 0.88), (0.18, 0.162, 1.0), "logo_mark", WHITE),          # (the club's badge)
            ((-0.18, -0.29, 0.66), (0.18, -0.15, 1.06), "backpack", WHITE)])
        self.arms = [self.limb(self.body, (x, 0, 1.06), [
            ((-0.085, -0.085, -0.31), (0.085, 0.085, 0.03), "suit", suit),
            ((-0.095, -0.095, -0.43), (0.095, 0.095, -0.31), "glove", WHITE)]) for x in (-0.335, 0.335)]
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0, 1.1)
        side, face, hair, skin = "coder_side", "coder_face", "coder_hair", "skin"
        gfx.model(self.head, [
            ((-0.30, -0.25, 0.05), (0.30, 0.25, 0.55), (side, side, side, hair, hair, skin), WHITE),
            ((-0.25, -0.30, 0.05), (0.25, 0.30, 0.55), (side, side, face, hair, hair, skin), WHITE),
            ((-0.255, -0.255, 0.0), (0.255, 0.255, 0.6), (side, side, face, hair, hair, skin), WHITE)])
        self.visor = self.shine(self.head, [((-0.31, 0.0, 0.28), (0.31, 0.32, 0.41), "visor_glow", WHITE)], "visor")

    def wear(self, ids):
        """Dress a Club Coder in the suit pieces worn (three item ids: visor, vest, boots; 0 for nothing), in their
        material, a little bigger than the parts they cover."""
        ids = tuple(int(i or 0) for i in (list(ids or ()) + [0] * 3)[:3])
        if ids == self.worn or self.kind != "player":
            return
        self.worn = ids
        for np_ in self.suit_nodes:
            np_.removeNode()
        self.suit_nodes = []

        def piece(parent, parts):
            np_ = parent.attachNewNode("suit piece")
            gfx.model(np_, parts)
            self.suit_nodes.append(np_)
        for part, item_id in enumerate(ids):
            it = B.ITEMS.get(item_id)
            if not it or it.get("suit") != part:
                continue
            tile = SUIT_TILES.get(it["key"].split("_")[0], "iron_block")
            if part == 0:    # the visor: a frame round the glowing band, ear pieces and a crest
                piece(self.head, [((-0.33, 0.0, 0.41), (0.33, 0.34, 0.46), tile, WHITE),
                                  ((-0.33, 0.0, 0.23), (0.33, 0.34, 0.28), tile, WHITE),
                                  ((-0.34, -0.09, 0.18), (0.34, 0.09, 0.46), tile, WHITE),
                                  ((-0.07, -0.33, 0.57), (0.07, 0.2, 0.67), tile, WHITE)])
            elif part == 1:  # the vest over the suit, pads on the shoulders, the badge on top
                piece(self.body, [((-0.28, -0.18, 0.66), (0.28, 0.18, 1.12), tile, WHITE),
                                  ((0.06, 0.18, 0.88), (0.18, 0.192, 1.0), "logo_mark", WHITE)])
                for arm in self.arms:
                    piece(arm, [((-0.105, -0.105, -0.12), (0.105, 0.105, 0.06), tile, WHITE)])
            else:            # the boots, over the boots
                for leg in self.legs:
                    piece(leg, [((-0.16, -0.18, -0.56), (0.16, 0.23, -0.34), tile, WHITE)])

    # ---------- the creatures ----------
    def build_fluff(self, c):
        self.legs = [self.limb(self.body, (x, 0, 0.26), [
            ((-0.03, -0.03, -0.22), (0.03, 0.03, 0.02), "fluff_foot", WHITE),
            ((-0.06, -0.05, -0.26), (0.06, 0.13, -0.2), "fluff_foot", WHITE)]) for x in (-0.14, 0.14)]
        self.puff = self.body.attachNewNode("puff")
        self.puff.setPos(0, 0, 0.6)
        tiles = ("fluff_white", "fluff_white", "fluff_face", "fluff_white", "fluff_white", "fluff_white")
        gfx.model(self.puff, rounded((-0.4, -0.4, -0.36), (0.4, 0.4, 0.36), 0.08, tiles, WHITE) +
                  [((-0.12, -0.14, 0.33), (0.12, 0.1, 0.44), "fluff_white", WHITE),
                   ((-0.46, -0.1, -0.06), (-0.38, 0.1, 0.12), "fluff_white", WHITE),
                   ((0.38, -0.1, -0.06), (0.46, 0.1, 0.12), "fluff_white", WHITE)])

    VOXEL = 0.2

    def build_glitch(self, c):
        """A cluster of pixels (small cubes), magenta and cyan, that changes shape; two bright eyes in front."""
        self.rng = random.Random(id(self))
        v = self.VOXEL
        self.cells = [(x, y, z) for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1)] + \
                     [(-2, 0, 0), (2, 0, 0), (0, 0, 2), (0, 0, -2), (0, -2, 0), (-2, 0, 1), (2, 0, -1), (1, -2, 1)]
        self.cluster = self.body.attachNewNode("cluster")
        self.cluster.setPos(0, 0, 0.55)
        self.voxels = []
        for k in range(19):
            np_ = self.cluster.attachNewNode("pixel")
            gfx.model(np_, [((-v / 2, -v / 2, -v / 2), (v / 2, v / 2, v / 2), "glitch_cyan" if k % 3 == 0 else
                             "glitch_body", WHITE)])
            glow(np_)  # (a Glitch is a bug of light: it shows in the dark)
            self.voxels.append(np_)
        self.eyes = self.shine(self.cluster, [((-0.17, 0.3, 0.04), (-0.05, 0.36, 0.16), "glitch_eye", WHITE),
                                              ((0.05, 0.3, 0.04), (0.17, 0.36, 0.16), "glitch_eye", WHITE)], "eyes")
        self.next_shape = 0.0
        self.reshape()

    def reshape(self):
        """A new shape: most of the cluster's middle, a few pixels further out, one or two jumped sideways."""
        r, v = self.rng, self.VOXEL
        inner = [p for p in self.cells if max(abs(q) for q in p) <= 1]
        outer = [p for p in self.cells if max(abs(q) for q in p) > 1]
        picked = r.sample(inner, 15) + r.sample(outer, 4)
        for np_, (x, y, z) in zip(self.voxels, picked):
            jump = v * 0.5 if r.random() < 0.12 else 0.0
            np_.setPos(x * v + jump * r.choice((-1, 1)), min(1, y) * v, z * v)
            np_.show() if r.random() < 0.92 else np_.hide()
        self.cluster.setX(v * 0.25 * r.choice((-1, 0, 0, 0, 1)))
        self.eyes.setX(0.02 * r.choice((-1, 0, 1)))

    def build_rust(self, c):
        """A Rust Walker: two tracks, a navy hull with rust on it, a head with coral eyes, a long magnet arm."""
        tr = ("track", "track", "tread", "tread", "tread", "tread")
        gfx.model(self.body, [((-0.38, -0.42, 0.0), (-0.16, 0.42, 0.3), tr, WHITE),
                              ((0.16, -0.42, 0.0), (0.38, 0.42, 0.3), tr, WHITE),
                              ((-0.16, -0.3, 0.08), (0.16, 0.3, 0.3), "metal_dark", WHITE)])
        self.hull = self.body.attachNewNode("hull")
        gfx.model(self.hull, [((-0.3, -0.3, 0.3), (0.3, 0.3, 0.98), "rust_body", WHITE),
                              ((-0.24, 0.3, 0.45), (0.24, 0.33, 0.8), "metal_dark", WHITE),
                              ((-0.06, -0.06, 0.98), (0.06, 0.06, 1.08), "metal_dark", WHITE),
                              ((-0.4, -0.06, 0.62), (-0.3, 0.06, 0.88), "rust_body", WHITE)])
        self.head = self.hull.attachNewNode("head")
        self.head.setPos(0, 0.04, 1.08)
        gfx.model(self.head, [((-0.2, -0.18, 0), (0.2, 0.2, 0.32), faces("rust_face", "rust_body"), WHITE),
                              ((0.09, -0.11, 0.32), (0.12, -0.08, 0.5), "metal_dark", WHITE)])
        self.shine(self.head, [((-0.15, 0.2, 0.18), (-0.05, 0.225, 0.26), "eye_coral", WHITE),
                               ((0.05, 0.2, 0.18), (0.15, 0.225, 0.26), "eye_coral", WHITE),
                               ((0.075, -0.125, 0.5), (0.135, -0.065, 0.56), "eye_coral", WHITE)], "eyes")
        self.arms = [self.limb(self.hull, (0.38, 0.05, 0.86), [
            ((-0.07, -0.07, -0.08), (0.07, 0.07, 0.08), "metal_dark", WHITE),
            ((-0.045, -0.045, -0.72), (0.045, 0.045, 0), "rust_body", WHITE),
            ((-0.15, -0.07, -0.8), (0.15, 0.07, -0.72), "magnet", WHITE),
            ((-0.15, -0.07, -0.95), (-0.07, 0.07, -0.8), "magnet", WHITE),
            ((0.07, -0.07, -0.95), (0.15, 0.07, -0.8), "magnet", WHITE),
            ((-0.15, -0.07, -1.0), (-0.07, 0.07, -0.95), "iron_block", WHITE),
            ((0.07, -0.07, -1.0), (0.15, 0.07, -0.95), "iron_block", WHITE)])]

    def build_bleep(self, c):
        self.legs = [self.limb(self.body, (x, 0, 0.16), [((-0.05, -0.16, -0.16), (0.05, 0.16, 0.16), "metal_dark",
                                                          (0.9, 0.9, 0.95))]) for x in (-0.28, 0.28)]
        gfx.model(self.body, [((-0.24, -0.24, 0.12), (0.24, 0.24, 0.52), "bleep_body", WHITE)])
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0, 0.52)
        gfx.model(self.head, [((-0.2, -0.2, 0), (0.2, 0.2, 0.32), faces("bleep_face", "bleep_body"), WHITE),
                              ((-0.02, -0.02, 0.32), (0.02, 0.02, 0.5), "iron_block", WHITE),
                              ((-0.05, -0.05, 0.5), (0.05, 0.05, 0.58), "lumen", WHITE)])

    def build_bot(self, c):
        """A Craft Bot: Club Coders' own little robot, its yellow face, a dock-coloured body, the club's mark on its
        chest."""
        self.legs = [self.limb(self.body, (x, 0, 0.2), [((-0.07, -0.2, -0.2), (0.07, 0.2, 0.2), "metal_dark", WHITE)])
                     for x in (-0.34, 0.34)]
        gfx.model(self.body, [((-0.3, -0.3, 0.14), (0.3, 0.3, 0.68), "dock_side", WHITE),
                              ((-0.14, 0.3, 0.27), (0.14, 0.312, 0.55), "logo_mark", WHITE)])
        self.arms = [self.limb(self.body, (x, 0.0, 0.6), [((-0.06, -0.06, -0.36), (0.06, 0.06, 0), "iron_block", WHITE)])
                     for x in (-0.37, 0.37)]
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0, 0.68)
        gfx.model(self.head, [((-0.26, -0.26, 0), (0.26, 0.26, 0.4), faces("bot_face", "copper_block"), WHITE),
                              ((-0.03, -0.03, 0.4), (0.03, 0.03, 0.6), "iron_block", WHITE),
                              ((-0.06, -0.06, 0.6), (0.06, 0.06, 0.7), "lumen", WHITE)])

    # ---------- every frame ----------
    def update(self, s, dt, world=None):
        """Placed and posed from a record (craft_sim's: x, y, z, vx, vy, vz, yaw, pitch, flags)."""
        self.t += dt
        flags = s["flags"]
        self.root.setPos(s["x"], s["y"], s["z"])
        self.root.setH(s["yaw"] - 90.0)
        speed = math.hypot(s["vx"], s["vy"])
        self.phase += dt * speed * 3.2
        moving = min(1.0, speed / 3.0)
        a = math.sin(self.phase) * moving * 38
        for k, leg in enumerate(self.legs):
            leg.setP(a if k % 2 == 0 else -a)
        if flags & sim.F_SWING:
            self.swing = 0.3
        self.swing = max(0.0, self.swing - dt)
        hit = math.sin(self.swing / 0.3 * math.pi) if self.swing > 0 else 0.0
        if self.kind == "rust":   # (the magnet arm reaches forward, and swings up and down to grab)
            for arm in self.arms:
                arm.setP(40 + 60 * hit + a * 0.15)
            self.hull.setZ(abs(math.sin(self.phase * 2)) * 0.03 * moving)
        else:
            for k, arm in enumerate(self.arms):
                p = -a * 0.8 if k == 0 else a * 0.8
                if k == 1 and self.swing > 0:
                    p = 70 * hit
                arm.setP(p)
        if self.head is not None:
            self.head.setP(max(-60, min(60, s.get("pitch", 0.0))) if self.kind == "player" else 0)
        if self.kind == "fluff":  # (it bobs as it floats along; brushed, it is a smaller puff till it grows back)
            bob = math.sin(self.t * 3.0) * 0.03 + abs(math.sin(self.phase)) * 0.06 * moving
            bare = bool(flags & sim.F_SLEEP)
            self.puff.setScale(0.72 if bare else 1.0)
            self.puff.setZ((0.5 if bare else 0.6) + bob)
        elif self.kind == "glitch":
            self.next_shape -= dt
            if self.next_shape <= 0:
                self.next_shape = self.rng.uniform(0.06, 0.22)
                self.reshape()
            self.cluster.setZ(0.55 + math.sin(self.t * 2.3) * 0.05)
        if self.kind == "player" and flags & sim.F_SLEEP:   # (lying in a Recharge Pod)
            self.root.setR(90)
            self.root.setZ(s["z"] + 0.3)
        else:
            self.root.setR(0)
        if self.kind == "player":
            self.body.setZ(-0.2 if flags & getattr(sim, "F_CAREFUL", 0) else 0.0)
        gfx.flash(self.root, bool(flags & sim.F_HURT))
        if world is not None:
            gfx.set_here(self.root, world, s["x"], s["y"], s["z"])

    def destroy(self):
        self.root.removeNode()


class ItemModel:
    """A thing dropped: its little cube or card, turning and bobbing."""

    def __init__(self, render, item_id):
        self.item = item_id
        self.root = render.attachNewNode("item")
        self.np = self.root.attachNewNode(gfx.item_geom(item_id, 0.3))
        if gfx.look():
            gfx.line_look.outline(self.np)
        gfx.ent_node(self.root)
        self.t = 0.0

    def update(self, s, dt, world=None):
        self.t += dt
        self.root.setPos(s["x"], s["y"], s["z"] + 0.15 + math.sin(self.t * 2.5) * 0.06)
        self.np.setH(self.t * 70)
        if world is not None:
            gfx.set_here(self.root, world, s["x"], s["y"], s["z"])

    def destroy(self):
        self.root.removeNode()
