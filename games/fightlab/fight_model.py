"""Fighters that are detailed 3D models with real animation (models/<body>_<shape>.gltf, made in Blender: see art/).

A ModelFighterVisual works just like fight_gfx.FighterVisual (the same update, set_label, show_label, destroy,
chest_pos and head_pos), so the class windows and the showcase can use either. It plays the model's moves, lined up
with the fight engine: an attack's strike frame (from models/moves.json) lands exactly when the engine's attack is
"active", however fast or slow that fighter's attacks are.

Each model file holds every outfit, hairstyle and weapon; the design's "look" says which are shown, the hair
colour, and the height, and its weapon which weapon is held. The design's colour is the colour of the outfit's
main pieces. A fighting style's own moves are named "<style>.<move>" (for example "boxer.punch"); a style without
its own version of a move uses the sword-and-shield one.
"""
import json
import os

from direct.actor.Actor import Actor
from panda3d.core import Filename, Point3, TextNode

import fight_sim as sim

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")
FACING = 180.0      # the models face -y; the game's heading 0 faces +y
BLEND_TIME = 0.12   # seconds to blend from one move into the next
# a move a model has no animation for plays another (and in the end, idle)
FALLBACK = {"intro": "idle", "dizzy": "hitstun", "hit_body": "hitstun", "swept": "knockdown", "idle_hurt": "idle",
            "launched": "knockdown"}
TWO_HANDED = ("longsword", "katana", "staff", "glaive")
HURT = 0.25  # below this share of their health, they stand hurt


def anim_sets(style, weapon):
    """Where a fighter's moves come from, first choice first (art/build_fighters.py SETS), before the usual ones."""
    sets = [weapon] if weapon else []
    sets.append(style)
    if weapon in TWO_HANDED:
        sets.append("twohand")
    if style in ("boxer", "kickboxer", "knives"):
        sets.append("guard")
    return sets
WEAPON_PIECES = {"knife": ("knife",), "dagger": ("dagger",), "sword_shield": ("sword", "shield"),
                 "longsword": ("longsword",), "katana": ("katana",), "stick": ("stick",), "staff": ("staff",),
                 "glaive": ("glaive",)}

_moves = None


def model_file(body, shape):
    return os.path.join(MODELS, f"{body}_{shape}.gltf")


def available(body):
    return body in sim.MODEL_BODIES and os.path.exists(model_file(body, "athletic"))


def moves_info():
    global _moves
    if _moves is None:
        with open(os.path.join(MODELS, "moves.json"), encoding="utf-8") as f:
            _moves = json.load(f)
    return _moves


def full_look(design):
    look = sim.default_look(design.get("body"))
    if isinstance(design.get("look"), dict) and not sim.check_look(design["body"], design["look"]):
        look.update(design["look"])
    return look


class ModelFighterVisual:
    def __init__(self, parent, design):
        body = design.get("body")
        look = full_look(design)
        path = model_file(body, look["shape"])
        if not os.path.exists(path):
            path = model_file(body, "athletic")
        info = moves_info()
        self.fps, self.moves = info["fps"], info["moves"]
        self.root = parent.attachNewNode("fighter")
        self.actor = Actor(Filename.fromOsSpecific(path))
        self.actor.reparentTo(self.root)
        self.actor.setH(FACING)
        self.size = 1.3 if design.get("model") else design.get("settings", {}).get("size", 100) / 100
        self.actor.setScale(self.size * 0.975 * look["height"] / 100)  # (the models are 1.80 m; fighters 1.75 m)
        self.frames = {m: max(1, self.actor.getNumFrames(m)) for m in self.actor.getAnimNames()}
        self.actor.enableBlend()
        self.clip = self.prev = None
        self.clip_time, self.fade, self.frame = 0.0, 1.0, 0.0
        self.pos, self.h = None, 0.0
        self.tag, self.flashing = None, False
        self.style, weapon = sim.style_of(design)
        self.sets = anim_sets(self.style, weapon)
        self.win = look.get("win", "victory")
        self.dress(look, design.get("colour"), weapon)
        self.head = self.actor.exposeJoint(None, "modelRoot", "mixamorig:Head")
        self.chest = self.actor.exposeJoint(None, "modelRoot", "mixamorig:Spine2")

    def dress(self, look, colour, weapon):
        """Show the chosen outfit, hairstyle and weapon (hide the rest), and colour the clothes and the hair."""
        outfit, hair = look["outfit"], look["hair"]
        weapons = WEAPON_PIECES.get(weapon, ())
        # the tint multiplies the lighting's linear colours: screen colour -> linear, divided by the grey the
        # main pieces (0.85 on screen) and the hair (about 0.8) already are
        main = tuple(min(2.0, (c / 255) ** 2.2 / 0.7) for c in (colour or (200, 200, 200))) + (1,)
        hair_tint = tuple(min(2.5, 0.02 + (c / 255) ** 2.2 / 0.6) for c in look["hair_colour"]) + (1,)
        order = moves_info().get("outfits", [])
        bit = 1 << order.index(outfit) if outfit in order else 0
        for np_ in self.actor.findAllMatches("**/+GeomNode"):
            name = np_.getName()
            if name.startswith("skin."):  # skin under the outfit is left out, so it can't poke through
                show = not (int(name[5:]) & bit) if name[5:].isdigit() else True
            elif name.startswith("outfit_"):
                show = name.startswith(f"outfit_{outfit}.")
            elif name.startswith("hair."):
                show = name == f"hair.{hair}"
            elif name.startswith("weapon."):
                show = name[len("weapon."):] in weapons
            else:
                show = True
            if not show:
                np_.stash()
                continue
            if ".main_" in name:
                np_.setColorScale(*main)
            elif name.startswith("hair."):
                np_.setColorScale(*hair_tint)

    # ---------- which frame of which animation ----------
    def clip_for(self, a):
        """Which of the model's animations plays the engine's anim a: this style's (or weapon's) own, else the
        usual one, else a stand-in (FALLBACK)."""
        seen = set()
        while a and a not in seen:
            seen.add(a)
            for name in [f"{s}.{a}" for s in self.sets] + [a]:
                if name in self.frames and name in self.moves:
                    return name
            a = FALLBACK.get(a, "idle")
        return "idle"

    def frame_for(self, a, k):
        """The frame of clip a (a model animation, from clip_for) for the engine's progress k (see
        fight_sim.Fighter.anim)."""
        n = self.frames[a]
        m = self.moves[a]
        play = m["play"]
        if play == "loop":
            return a, (self.clip_time * self.fps) % n
        if play == "once":
            return a, min(n - 1, max(0.0, k) * (n - 1))
        if play == "reverse":
            return a, (1 - min(1.0, max(0.0, k))) * (n - 1)
        if play == "hold":
            return a, min(n - 1, self.clip_time * self.fps)
        # an attack: wind-up (k 0-1) up to the strike frame, the strike itself (1-2), then the recovery (2-3)
        peak = min(n - 2, max(1, m["peak"]))
        strike = max(1.0, 0.12 * (n - peak))
        if k < 1:
            f = k * peak
        elif k < 2:
            f = peak + (k - 1) * strike
        else:
            f = peak + strike + min(1.0, k - 2) * (n - 1 - peak - strike)
        return a, max(0.0, min(n - 1, f))

    def update(self, s, dt):
        """s: this fighter's state from the server (pos, h, a, k, hu...)."""
        x, y, z = s["pos"]
        target = Point3(x, y, z)
        if self.pos is None or (self.pos - target).length() > 2.5:
            self.pos = Point3(target)
        else:
            self.pos += (target - self.pos) * min(1.0, dt * 20)
        dh = (s["h"] - self.h + 180) % 360 - 180
        self.h += dh if abs(dh) > 60 else dh * min(1.0, dt * 22)
        self.root.setPos(self.pos)
        self.root.setH(self.h)
        a, k = s.get("a", "idle"), s.get("k", 0.0)
        if a == "win":
            a = f"win_{self.win}"
        elif a == "idle" and s.get("hp", 1) < HURT * s.get("max", 1):
            a = "idle_hurt"
        name = self.clip_for(a)
        if name != self.clip:  # a new move: blend from the old one over a moment
            self.prev, self.prev_frame = self.clip, self.frame
            self.clip, self.clip_time, self.fade = name, 0.0, 0.0
        else:
            self.clip_time += dt
        self.fade = min(1.0, self.fade + dt / BLEND_TIME)
        anim, frame = self.frame_for(name, k)
        self.frame = frame
        self.actor.pose(anim, int(frame))
        self.actor.setControlEffect(anim, self.fade)
        if self.prev and self.prev != anim:
            if self.fade < 1.0:
                self.actor.pose(self.prev, int(self.prev_frame))
                self.actor.setControlEffect(self.prev, 1.0 - self.fade)
            else:
                self.actor.setControlEffect(self.prev, 0.0)
                self.prev = None
        hurt = s.get("hu", 9) < 0.12  # a hit flash: bright for a moment
        if hurt != self.flashing:
            self.flashing = hurt
            self.actor.setColorScale((2.6, 2.3, 2.1, 1) if hurt else (1, 1, 1, 1))

    # ---------- the name tag ----------
    def show_label(self, on):
        if self.tag is not None:
            self.tag.show() if on else self.tag.hide()

    def set_label(self, text, colour=(1, 1, 1, 1)):
        if self.tag is None:
            node = TextNode("tag")
            node.setAlign(TextNode.ACenter)
            node.setCardColor(0.03, 0.04, 0.06, 0.7)
            node.setCardAsMargin(0.35, 0.35, 0.18, 0.12)
            self.tag = self.root.attachNewNode(node)
            self.tag.setBillboardPointEye()
            self.tag.setScale(0.15)
            self.tag.setLightOff(1)
            self.tag.setShaderOff(1)
            self.tag.setDepthTest(False)
            self.tag.setDepthWrite(False)
            self.tag.setBin("fixed", 60)
            self.tag.setZ(2.05 * self.size + 0.2)
        self.tag.node().setText(text)
        self.tag.node().setTextColor(*colour)

    def chest_pos(self):
        return self.chest.getPos(self.root.getParent())

    def head_pos(self):
        return self.head.getPos(self.root.getParent())

    def destroy(self):
        self.actor.cleanup()
        self.root.removeNode()


def make(parent, design):
    """The right visual for a design: a detailed model for the woman and man bodies, otherwise the built fighter."""
    if available(design.get("body")):
        return ModelFighterVisual(parent, design)
    import fight_gfx
    return fight_gfx.FighterVisual(parent, design)
