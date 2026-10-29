"""Craft Lab's people, creatures and Craft Bots, built from boxes with the atlas's faces (CHANGE 200), and moved
from their wire records: walking legs and arms that swing with their speed, a head that looks up and down, an arm
that swings when they dig or hit, a red flash when hurt, a Glitch that squashes as it hops, a name over a player.
"""
import math

from panda3d.core import TextNode

import craft_blocks as B
import craft_gfx as gfx
import craft_sim as sim

KIND_NAMES = {v: k for k, v in sim.KINDS.items()}


def rgb01(c):
    return tuple(max(0.0, min(1.0, v / 255.0)) for v in list(c)[:3]) if c else (0.9, 0.9, 0.9)


def faces(front, other):
    """Six tiles for a box whose front (+y, the way the model faces) is different."""
    return (other, other, front, other, other, other)


class Model:
    """One person or creature: a root (moved and turned), and the parts that swing."""

    def __init__(self, render, kind, colour=(200, 60, 50), name=None):
        self.kind = kind
        self.root = render.attachNewNode(f"{kind} model")
        self.body = self.root.attachNewNode("body")
        self.legs, self.arms, self.head = [], [], None
        self.phase = 0.0
        self.swing = 0.0
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
            t.setCardColor(0, 0, 0, 0.45)
            t.setCardAsMargin(0.2, 0.2, 0.08, 0.04)
            t.setCardDecal(True)
            self.tag = self.root.attachNewNode(t)
            self.tag.setBillboardPointEye()
            self.tag.setScale(0.28)
            self.tag.setZ(2.15)
            self.tag.setShaderOff(2)
            self.tag.setLightOff(2)
            self.tag.setFogOff(2)
            if self.kind == "bot":
                self.tag.setZ(1.62)  # (above its aerial, which tops out at 1.38)
        self.tag.node().setText(name)

    def say(self, text):
        """A speech bubble (a Craft Bot's "say"), or back to the name with None."""
        words = text or self.name
        if words and words != getattr(self, "_said", None):
            self._said = words
            self.make_tag(words)

    def limb(self, parent, pivot, lo, hi, tiles, colour):
        joint = parent.attachNewNode("joint")
        joint.setPos(*pivot)
        gfx.model(joint, [(lo, hi, tiles, colour)])
        return joint

    def build_player(self, c, rust=False):
        skin, top = ("rust_body", "rust_face") if rust else ("skin", "player_face")
        shirt = "rust_body" if rust else "shirt"
        legs = "rust_body" if rust else "trousers"
        tint = (0.95, 0.75, 0.6) if rust else c
        self.legs = [self.limb(self.body, (x, 0, 0.72), (-0.12, -0.12, -0.72), (0.12, 0.12, 0), legs,
                               (0.9, 0.9, 0.9)) for x in (-0.12, 0.12)]
        gfx.model(self.body, [((-0.24, -0.12, 0.72), (0.24, 0.12, 1.38), shirt, tint)])
        arm = "rust_body" if rust else "skin"
        self.arms = [self.limb(self.body, (x, 0, 1.36), (-0.11, -0.11, -0.64), (0.11, 0.11, 0), arm,
                               (1, 1, 1)) for x in (-0.36, 0.36)]
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0, 1.38)
        gfx.model(self.head, [((-0.24, -0.24, 0), (0.24, 0.24, 0.48), faces(top, "hair" if not rust else "rust_body"),
                               (1, 1, 1))])

    ARMOUR_TILES = {"cloth": "cloth_armour", "copper": "copper_block", "iron": "iron_block", "crystal": "crystal_block"}

    def wear(self, ids):
        """Dress a person in the armour they wear (four item ids, 0 for nothing): boxes a little bigger than the parts."""
        ids = tuple(int(i or 0) for i in (list(ids) + [0] * 4)[:4])
        if ids == getattr(self, "worn", (0, 0, 0, 0)) or self.kind != "player":
            return
        self.worn = ids
        for np_ in getattr(self, "armour_nodes", []):
            np_.removeNode()
        self.armour_nodes = []

        def piece(parent, lo, hi, tile):
            np_ = parent.attachNewNode("armour")
            gfx.model(np_, [(lo, hi, tile, (1, 1, 1))])
            self.armour_nodes.append(np_)
        for part, item_id in enumerate(ids):
            it = B.ITEMS.get(item_id)
            if not it or it.get("armour") != part:
                continue
            tile = self.ARMOUR_TILES.get(it["key"].split("_")[0], "iron_block")
            if part == 0:
                piece(self.head, (-0.27, -0.27, 0.24), (0.27, 0.27, 0.53), tile)
            elif part == 1:
                piece(self.body, (-0.26, -0.14, 0.74), (0.26, 0.14, 1.40), tile)
                for arm in self.arms:
                    piece(arm, (-0.125, -0.125, -0.3), (0.125, 0.125, 0.02), tile)
            elif part == 2:
                piece(self.body, (-0.26, -0.14, 0.62), (0.26, 0.14, 0.8), tile)
                for leg in self.legs:
                    piece(leg, (-0.135, -0.135, -0.5), (0.135, 0.135, 0.0), tile)
            else:
                for leg in self.legs:
                    piece(leg, (-0.14, -0.15, -0.74), (0.14, 0.15, -0.5), tile)

    def build_rust(self, c):
        self.build_player(c, rust=True)
        self.body.setScale(1.06)

    def build_fluff(self, c):
        self.legs = [self.limb(self.body, (x, y, 0.4), (-0.09, -0.09, -0.4), (0.09, 0.09, 0), "soil", (0.9, 0.85, 0.8))
                     for x in (-0.22, 0.22) for y in (-0.3, 0.3)]
        gfx.model(self.body, [((-0.34, -0.48, 0.38), (0.34, 0.42, 0.98), "fluff_wool", (1, 1, 1))])
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0.42, 0.78)
        gfx.model(self.head, [((-0.2, 0, -0.18), (0.2, 0.36, 0.22), faces("fluff_face", "fluff_wool"), (1, 1, 1))])

    def build_bleep(self, c):
        self.legs = [self.limb(self.body, (x, 0, 0.16), (-0.05, -0.16, -0.16), (0.05, 0.16, 0.16), "corestone",
                               (0.7, 0.7, 0.75)) for x in (-0.28, 0.28)]
        gfx.model(self.body, [((-0.24, -0.24, 0.12), (0.24, 0.24, 0.52), "bleep_body", (1, 1, 1))])
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0, 0.52)
        gfx.model(self.head, [((-0.2, -0.2, 0), (0.2, 0.2, 0.32), faces("bleep_face", "bleep_body"), (1, 1, 1)),
                              ((-0.02, -0.02, 0.32), (0.02, 0.02, 0.5), "iron_block", (1, 1, 1)),
                              ((-0.05, -0.05, 0.5), (0.05, 0.05, 0.58), "lumen", (1, 1, 1))])

    def build_glitch(self, c):
        gfx.model(self.body, [((-0.44, -0.44, 0), (0.44, 0.44, 0.88), faces("glitch_face", "glitch_body"), (1, 1, 1))])

    def build_bot(self, c):
        """A Craft Bot: Club Coders' own little robot, its yellow face and a dock-coloured body."""
        self.legs = [self.limb(self.body, (x, 0, 0.2), (-0.07, -0.2, -0.2), (0.07, 0.2, 0.2), "corestone",
                               (0.8, 0.8, 0.8)) for x in (-0.34, 0.34)]
        gfx.model(self.body, [((-0.3, -0.3, 0.14), (0.3, 0.3, 0.68), "dock_side", (1, 1, 1))])
        self.arms = [self.limb(self.body, (x, 0.0, 0.6), (-0.06, -0.06, -0.36), (0.06, 0.06, 0), "iron_block",
                               (1, 1, 1)) for x in (-0.37, 0.37)]
        self.head = self.body.attachNewNode("head")
        self.head.setPos(0, 0, 0.68)
        gfx.model(self.head, [((-0.26, -0.26, 0), (0.26, 0.26, 0.4), faces("bot_face", "copper_block"), (1, 1, 1)),
                              ((-0.03, -0.03, 0.4), (0.03, 0.03, 0.6), "iron_block", (1, 1, 1)),
                              ((-0.06, -0.06, 0.6), (0.06, 0.06, 0.7), "lumen", (1, 1, 1))])

    def update(self, s, dt, world=None):
        """Placed and posed from a record (craft_sim's: x, y, z, vx, vy, vz, yaw, pitch, flags)."""
        self.root.setPos(s["x"], s["y"], s["z"])
        self.root.setH(s["yaw"] - 90.0)
        speed = math.hypot(s["vx"], s["vy"])
        self.phase += dt * speed * 3.2
        a = math.sin(self.phase) * min(1.0, speed / 3.0) * 38
        for k, leg in enumerate(self.legs):
            leg.setP(a if k % 2 == 0 else -a)
        swing = bool(s["flags"] & sim.F_SWING)
        if swing:
            self.swing = 0.3
        self.swing = max(0.0, self.swing - dt)
        for k, arm in enumerate(self.arms):
            p = -a * 0.8 if k == 0 else a * 0.8
            if k == 1 and self.swing > 0:
                p = -70 * math.sin(self.swing / 0.3 * math.pi)
            if self.kind == "rust":
                p -= 70
            arm.setP(p)
        if self.head is not None:
            self.head.setP(max(-60, min(60, s.get("pitch", 0.0))) if self.kind == "player" else 0)
        if self.kind == "glitch":  # (it squashes as it lands and stretches as it leaps)
            k = max(-0.25, min(0.25, s["vz"] * 0.04))
            self.body.setScale(1 - k * 0.5, 1 - k * 0.5, 1 + k)
        if s["flags"] & sim.F_SLEEP:
            self.root.setR(90)
            self.root.setZ(s["z"] + 0.3)
        else:
            self.root.setR(0)
        self.body.setZ(-0.25 if s["flags"] & sim.F_SNEAK else 0.0)
        gfx.flash(self.root, bool(s["flags"] & sim.F_HURT))
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
