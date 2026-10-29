"""City Lab's pictures in the window (CHANGE 194): the city built from its data, the people, the cameras.

The lights, the sky, the time of day, the shader pipeline and the graphics tiers are Kart Lab's (kart_gfx.init, once);
the cars will be Kart Lab's (kart_gfx.KartVisual), the people Fight Lab's (fight_model.make: the woman, the man and
Robin as their skinned models, the built human and robot from fight_gfx), the robots Robot Lab's. Fight Lab's drawing
code keeps its own state (its materials, its tier), filled in here beside Kart Lab's instead of by its own init, which
would make a second set of lights and a second pipeline.

The city never moves, so it is built once into one mesh for each material (the roads, the pavements, the walls with
their colours, the windows, the roofs, the markings, the trees, the lamps...): about fifteen things to draw however big
the city is. Co-ordinates are the game's: x east, y north, z up, metres; the roads are at z 0 and the blocks stand a
kerb's height above them.
"""
import math
import os
import sys

import city_version  # noqa: F401  (the engine and the other games' folders on the path)
from panda3d.core import (NodePath, Point3, TextNode, TransparencyAttrib, Vec3)

from engine import gfx_tiers
from engine.rw_mesh import Mesh, cylinder
import kart_gfx
import city_map
import city_sim as sim

LOOK_TIERS = gfx_tiers.LOOKS
FLOOR = 3.2          # a storey's height (the windows' rows)
WIN_EVERY = 2.6      # a window every this many metres along a wall
SHOP_GLASS = 2.4     # a shop's window, the ground floor
PITCH = 2.4          # a house roof's rise
PERSON_LIFT = city_map.KERB_H  # (people on a block stand on the pavement, a kerb's height above the road)

PLACE_SIGNS = {"depot": "DEPOT", "garage": "GARAGE", "rank": "TAXI RANK", "arcade": "ARCADE"}
PLACE_COLOURS = {"depot": (0.95, 0.7, 0.15), "garage": (0.3, 0.8, 1.0), "rank": (1.0, 0.85, 0.1), "arcade": (1.0, 0.3, 0.9)}

# the city's materials: (texture set, colour, roughness, metal) for each mesh (kart_gfx.Materials.apply)
MATERIALS = {
    "road": ("tarmac", (0.82, 0.82, 0.86), 0.9, 0.0),
    "lot": ("asphalt", (0.78, 0.78, 0.8), 0.9, 0.0),
    "pave": ("concrete", (0.92, 0.9, 0.86), 0.85, 0.0),
    "kerb": ("concrete", (0.75, 0.74, 0.72), 0.8, 0.0),
    "grass": ("grass", (0.95, 1.0, 0.9), 0.95, 0.0),
    "water": ("water", (0.55, 0.7, 0.85), 0.15, 0.0),
    "walls": ("render", (1.0, 1.0, 1.0), 0.85, 0.0),
    "glass": (None, (0.16, 0.2, 0.26), 0.08, 0.6),
    "frames": (None, (0.85, 0.85, 0.82), 0.6, 0.0),
    "roof": ("concrete", (0.55, 0.55, 0.57), 0.9, 0.0),
    "tiles": (None, (0.55, 0.24, 0.18), 0.8, 0.0),
    "paint": (None, (0.95, 0.95, 0.92), 0.6, 0.0),
    "yellow": (None, (0.98, 0.78, 0.1), 0.6, 0.0),
    "steel": ("steel", (0.55, 0.57, 0.6), 0.45, 0.8),
    "lamp": (None, (1.0, 0.95, 0.8), 0.4, 0.0),
    "bark": ("bark", (0.9, 0.85, 0.8), 0.9, 0.0),
    "leaves": ("foliage", (0.75, 0.95, 0.7), 0.9, 0.0),
    "ramp": ("concrete", (0.85, 0.7, 0.3), 0.8, 0.0),
    "boards": (None, (0.12, 0.12, 0.16), 0.7, 0.0),
}
COLOURED = {"walls", "lot", "pave", "boards"}  # (these meshes carry a colour per vertex: every building its own paint)

_extra = {}


def init(base, tier="medium", line_colour=None):
    """The lights, sky, tiers and pipeline (Kart Lab's), and Fight Lab's drawing state beside them. Returns the
    simplepbr pipeline (None on basic, mesh and lines)."""
    pipeline = kart_gfx.init(base, tier, line_colour=line_colour)
    used = kart_gfx.tier()
    import fight_gfx  # (Fight Lab's: the people's built bodies and its materials)
    fight_gfx._state.clear()
    fight_gfx._state.update(mats=fight_gfx.Materials(base.loader, used), render=base.render, quality=used,
                            pipeline=pipeline, sun=kart_gfx._state.get("sun"))
    if kart_gfx._state.get("fog") is not None:
        fight_gfx._state["haze"] = kart_gfx._state["fog"]
    _extra["base"] = base
    return pipeline


def tier():
    return kart_gfx.tier()


def look():
    return tier() in LOOK_TIERS


def rgb01(c, fallback=(0.7, 0.7, 0.7)):
    if not c:
        return fallback
    return tuple(max(0.0, min(1.0, v / 255.0)) for v in list(c)[:3])


# ---------- building helpers (into a Mesh, in world co-ordinates) ----------
def quad(mesh, a, b, c, d, normal, uv=None, colour=None):
    """A quad a, b, c, d (in order round it) facing normal; uv: the four texture co-ordinates (else from the world)."""
    if colour is not None and mesh.c is not None:
        mesh.colour = (*colour, 1.0)
    if uv is None:
        mesh.poly([a, b, c, d], normal=normal)
    else:
        kart_gfx.quad(mesh, [a, b, c, d], uv, normal=normal)


def wall(mesh, x0, y0, x1, y1, z0, z1, normal, colour=None, tile=0.25):
    """A vertical wall from (x0, y0) to (x1, y1), z0 to z1, its texture in metres (tile repeats a metre)."""
    length = math.hypot(x1 - x0, y1 - y0)
    uv = [(0, z0 * tile), (length * tile, z0 * tile), (length * tile, z1 * tile), (0, z1 * tile)]
    quad(mesh, Vec3(x0, y0, z0), Vec3(x1, y1, z0), Vec3(x1, y1, z1), Vec3(x0, y0, z1), normal, uv, colour)


def flat(mesh, x0, y0, x1, y1, z, colour=None, tile=0.25, normal=(0, 0, 1)):
    uv = [(x0 * tile, y0 * tile), (x1 * tile, y0 * tile), (x1 * tile, y1 * tile), (x0 * tile, y1 * tile)]
    quad(mesh, Vec3(x0, y0, z), Vec3(x1, y0, z), Vec3(x1, y1, z), Vec3(x0, y1, z), Vec3(*normal), uv, colour)


def box(mesh, x0, y0, x1, y1, z0, z1, colour=None, top=True, tile=0.5):
    for (ax, ay, bx, by, n) in ((x0, y0, x1, y0, (0, -1, 0)), (x1, y0, x1, y1, (1, 0, 0)),
                                (x1, y1, x0, y1, (0, 1, 0)), (x0, y1, x0, y0, (-1, 0, 0))):
        wall(mesh, ax, ay, bx, by, z0, z1, Vec3(*n), colour, tile)
    if top:
        flat(mesh, x0, y0, x1, y1, z1, colour, tile)


class CityVisual:
    """The whole city, built once from its data (city_map.City)."""

    def __init__(self, parent, city):
        self.city = city
        self.root = parent.attachNewNode(f"city {city.key}")
        self.meshes = {k: Mesh(tile=1.0, colours=k in COLOURED) for k in MATERIALS}
        m = self.meshes
        self.ground(m)
        self.blocks(m)
        for b in city.buildings:
            self.building(m, b)
        self.markings(m)
        self.trees(m)
        self.lamps(m)
        self.ramps(m)
        self.edge(m)
        self.nodes = {}
        for key, mesh in m.items():
            if mesh.count == 0:
                continue
            tex, colour, rough, metal = MATERIALS[key]
            np_ = self.root.attachNewNode(mesh.node(f"city {key}"))
            kart_gfx.mats().apply(np_, tex if not look() else None, colour, rough, metal,
                                  emission=(0.0, 0.0, 0.0) if key != "lamp" else None)
            self.nodes[key] = np_
        self.signs()
        self.root.flattenStrong()
        if look():  # mesh and lines: the city's edges as lines, a ground grid on lines
            extra = None
            if tier() == "lines":
                from engine import line_look
                c = city
                extra = line_look.grid([(c.xmin, c.ymin, c.xmax, c.ymax)], kart_gfx.GRID, z=0.004)
            kart_gfx.outline(self.root, extra=extra)

    # ---------- the ground: the roads' asphalt, the verge, the water ----------
    def ground(self, m):
        c = self.city
        flat(m["road"], c.xmin, c.ymin, c.xmax, c.ymax, 0.0, tile=0.125)
        e = c.edge
        water_side = c.water
        sides = {"south": (e[0], e[1], e[2], c.ymin), "north": (e[0], c.ymax, e[2], e[3]),
                 "west": (e[0], c.ymin, c.xmin, c.ymax), "east": (c.xmax, c.ymin, e[2], c.ymax)}
        for side, (x0, y0, x1, y1) in sides.items():
            if side == water_side:
                # the quay: a strip of paving by the road, then the water a metre down, out to the horizon
                qx0, qy0, qx1, qy1 = x0, y0, x1, y1
                flat(m["pave"], qx0, qy0, qx1, qy1, 0.02, colour=(0.8, 0.78, 0.74))
                far = 400.0
                wx0, wy0, wx1, wy1 = {"south": (x0 - far, y0 - far, x1 + far, y0), "north": (x0 - far, y1, x1 + far, y1 + far),
                                      "west": (x0 - far, y0 - far, x0, y1 + far), "east": (x1, y0 - far, x1 + far, y1 + far)}[side]
                flat(m["water"], wx0, wy0, wx1, wy1, -1.0, tile=0.05)
            else:
                flat(m["grass"], x0, y0, x1, y1, 0.0, tile=0.2)
        # the land beyond the edge (where there is no water): grass to the horizon
        far = 500.0
        for side, rect in (("south", (e[0] - far, e[1] - far, e[2] + far, e[1])), ("north", (e[0] - far, e[3], e[2] + far, e[3] + far)),
                           ("west", (e[0] - far, e[1], e[0], e[3])), ("east", (e[2], e[1], e[2] + far, e[3]))):
            if side != water_side:
                flat(m["grass"], *rect, -0.02, tile=0.05)

    # ---------- the blocks: kerbs, pavements and what is inside ----------
    def blocks(self, m):
        c, h, pv = self.city, city_map.KERB_H, city_map.PAVE
        for b in c.blocks:
            x0, y0, x1, y1 = b["x0"], b["y0"], b["x1"], b["y1"]
            # the kerb's face all round
            for (ax, ay, bx, by, n) in ((x0, y0, x1, y0, (0, -1, 0)), (x1, y0, x1, y1, (1, 0, 0)),
                                        (x1, y1, x0, y1, (0, 1, 0)), (x0, y1, x0, y0, (-1, 0, 0))):
                wall(m["kerb"], ax, ay, bx, by, 0.0, h, Vec3(*n), tile=1.0)
            # the pavement: a ring round the inside
            tone = (0.95, 0.93, 0.9)
            flat(m["pave"], x0, y0, x1, y0 + pv, h, tone)
            flat(m["pave"], x0, y1 - pv, x1, y1, h, tone)
            flat(m["pave"], x0, y0 + pv, x0 + pv, y1 - pv, h, tone)
            flat(m["pave"], x1 - pv, y0 + pv, x1, y1 - pv, h, tone)
            ix0, iy0, ix1, iy1 = x0 + pv, y0 + pv, x1 - pv, y1 - pv
            kind = b["kind"]
            if kind == "park":
                flat(m["grass"], ix0, iy0, ix1, iy1, h, tile=0.2)
                # a path across it each way
                cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
                flat(m["pave"], ix0, cy - 1.0, ix1, cy + 1.0, h + 0.01, (0.85, 0.8, 0.68))
                flat(m["pave"], cx - 1.0, iy0, cx + 1.0, iy1, h + 0.012, (0.85, 0.8, 0.68))
            elif kind in ("carpark", "depot", "garage", "rank", "arcade"):
                flat(m["lot"], ix0, iy0, ix1, iy1, h + 0.002, (0.75, 0.75, 0.78) if kind == "carpark" else (0.8, 0.79, 0.77))
            elif kind == "houses":
                flat(m["grass"], ix0, iy0, ix1, iy1, h, tile=0.2)  # (the gardens; the houses stand on them)
            else:
                flat(m["pave"], ix0, iy0, ix1, iy1, h + 0.001, (0.82, 0.8, 0.76))  # (a courtyard)

    # ---------- a building ----------
    def building(self, m, b):
        h0 = city_map.KERB_H
        x0, y0, x1, y1, height = b["x0"], b["y0"], b["x1"], b["y1"], b["h"]
        top = h0 + height
        colour = rgb01(b["c"])
        kind = b["kind"]
        walls = m["walls"]
        for (ax, ay, bx, by, n) in ((x0, y0, x1, y0, (0, -1, 0)), (x1, y0, x1, y1, (1, 0, 0)),
                                    (x1, y1, x0, y1, (0, 1, 0)), (x0, y1, x0, y0, (-1, 0, 0))):
            wall(walls, ax, ay, bx, by, h0, top, Vec3(*n), colour)
            self.windows(m, ax, ay, bx, by, h0, top, Vec3(*n), kind)
        if b["roof"] == "pitched":
            self.pitched(m, x0, y0, x1, y1, top, colour)
        else:
            flat(m["roof"], x0, y0, x1, y1, top, tile=0.25)
            # a parapet a little above the roof, and a plant room on a tall one
            for (ax, ay, bx, by, n) in ((x0, y0, x1, y0, (0, -1, 0)), (x1, y0, x1, y1, (1, 0, 0)),
                                        (x1, y1, x0, y1, (0, 1, 0)), (x0, y1, x0, y0, (-1, 0, 0))):
                wall(walls, ax, ay, bx, by, top, top + 0.6, Vec3(*n), tuple(v * 0.85 for v in colour))
            if height > 18.0 and (x1 - x0) > 8 and (y1 - y0) > 8:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                box(m["roof"], cx - 2.5, cy - 2.0, cx + 2.5, cy + 2.0, top, top + 2.8, tile=0.25)

    def windows(self, m, ax, ay, bx, by, z0, z1, n, kind):
        """Rows of windows on a wall (2 cm proud of it, so they never flicker into it), a shop window and a door on
        the ground floor of a shop."""
        length = math.hypot(bx - ax, by - ay)
        if length < 2.5 or z1 - z0 < 2.5:
            return
        ux, uy = (bx - ax) / length, (by - ay) / length
        off = Vec3(n) * 0.03
        glass, frames = m["glass"], m["frames"]
        if kind in ("depot", "garage"):  # big doors instead of windows on the ground floor, a strip of windows above
            door_w = min(length * 0.5, 9.0)
            s0 = (length - door_w) / 2
            p, q = Vec3(ax + ux * s0, ay + uy * s0, z0), Vec3(ax + ux * (s0 + door_w), ay + uy * (s0 + door_w), z0)
            quad(frames, p + off, q + off, q + off + Vec3(0, 0, 4.2), p + off + Vec3(0, 0, 4.2), n)
            rows = [(z0 + 5.4, z0 + 6.6)] if z1 - z0 > 7.0 else []
        elif kind == "shop":
            rows = [(z0 + 0.4, z0 + SHOP_GLASS)] + [(z0 + FLOOR * k + 1.0, z0 + FLOOR * k + 2.4)
                                                    for k in range(1, int((z1 - z0 - 0.8) / FLOOR))]
        elif kind == "arcade":
            rows = [(z0 + 0.3, z0 + 3.2), (z0 + 6.0, z0 + 9.0)]
        else:
            rows = [(z0 + FLOOR * k + 0.9, z0 + FLOOR * k + 2.4) for k in range(int((z1 - z0 - 0.8) / FLOOR))]
            if kind == "house" and rows:
                rows = rows[:2]
        count = max(1, int(length / WIN_EVERY))
        gap = length / count
        for r, (za, zb) in enumerate(rows):
            if zb > z1 - 0.3:
                continue
            shop_row = kind == "shop" and r == 0
            width = gap * 0.8 if shop_row else min(1.4, gap * 0.6)
            for i in range(count):
                mid = gap * (i + 0.5)
                s0, s1 = mid - width / 2, mid + width / 2
                p = Vec3(ax + ux * s0, ay + uy * s0, za) + off
                q = Vec3(ax + ux * s1, ay + uy * s1, za) + off
                up = Vec3(0, 0, zb - za)
                quad(glass, p, q, q + up, p + up, n)
                # a sill under it
                sill = Vec3(0, 0, 0.12)
                quad(frames, p - sill, q - sill, q, p, n)

    def pitched(self, m, x0, y0, x1, y1, top, colour):
        """A house's roof: two slopes along the longer side, a gable at each end (in the wall's colour)."""
        tiles, walls = m["tiles"], m["walls"]
        if x1 - x0 >= y1 - y0:  # the ridge runs east to west
            cy = (y0 + y1) / 2
            r = top + PITCH
            quad(tiles, Vec3(x0, y0, top), Vec3(x1, y0, top), Vec3(x1, cy, r), Vec3(x0, cy, r), Vec3(0, -1, 1.2), None)
            quad(tiles, Vec3(x1, y1, top), Vec3(x0, y1, top), Vec3(x0, cy, r), Vec3(x1, cy, r), Vec3(0, 1, 1.2), None)
            for gx, nx in ((x0, -1), (x1, 1)):
                walls.colour = (*colour, 1.0)
                walls.poly([Vec3(gx, y0, top), Vec3(gx, y1, top), Vec3(gx, cy, r)], normal=Vec3(nx, 0, 0))
        else:
            cx = (x0 + x1) / 2
            r = top + PITCH
            quad(tiles, Vec3(x0, y1, top), Vec3(x0, y0, top), Vec3(cx, y0, r), Vec3(cx, y1, r), Vec3(-1, 0, 1.2), None)
            quad(tiles, Vec3(x1, y0, top), Vec3(x1, y1, top), Vec3(cx, y1, r), Vec3(cx, y0, r), Vec3(1, 0, 1.2), None)
            for gy, ny in ((y0, -1), (y1, 1)):
                walls.colour = (*colour, 1.0)
                walls.poly([Vec3(x0, gy, top), Vec3(x1, gy, top), Vec3(cx, gy, r)], normal=Vec3(0, ny, 0))

    # ---------- the roads' paint ----------
    def markings(self, m):
        c = self.city
        paint, z = m["paint"], 0.012
        half = city_map.ROAD / 2
        lane_edge = city_map.LANE * 2  # (between the lane and the parking strip)

        def dashes(ax, ay, bx, by, offset, dash=3.0, gap=3.0, w=0.12):
            length = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / length, (by - ay) / length
            lx, ly = -uy, ux
            s = 0.0
            while s < length - 0.5:
                e = min(length, s + dash)
                pa = (ax + ux * s + lx * (offset - w / 2), ay + uy * s + ly * (offset - w / 2))
                pb = (ax + ux * e + lx * (offset - w / 2), ay + uy * e + ly * (offset - w / 2))
                pc = (ax + ux * e + lx * (offset + w / 2), ay + uy * e + ly * (offset + w / 2))
                pd = (ax + ux * s + lx * (offset + w / 2), ay + uy * s + ly * (offset + w / 2))
                quad(paint, Vec3(*pa, z), Vec3(*pb, z), Vec3(*pc, z), Vec3(*pd, z), Vec3(0, 0, 1), [(0, 0), (1, 0), (1, 1), (0, 1)])
                s += dash + gap

        def zebra(cx, cy, along_x):
            """A crossing across the road at (cx, cy): stripes running along the road."""
            for k in range(-4, 5):
                o = k * 1.1
                if along_x:
                    x0, x1, y0, y1 = cx - 1.5, cx + 1.5, cy + o - 0.27, cy + o + 0.27
                else:
                    x0, x1, y0, y1 = cx + o - 0.27, cx + o + 0.27, cy - 1.5, cy + 1.5
                quad(paint, Vec3(x0, y0, z), Vec3(x1, y0, z), Vec3(x1, y1, z), Vec3(x0, y1, z), Vec3(0, 0, 1), [(0, 0), (1, 0), (1, 1), (0, 1)])

        for k in range(c.cols + 1):
            x = c.road_x(k)
            for mm in range(c.rows):
                ya, yb = c.road_y(mm) + half + 4.0, c.road_y(mm + 1) - half - 4.0
                dashes(x, ya, x, yb, 0.0)
                dashes(x, ya, x, yb, lane_edge, dash=1.0, gap=0.0, w=0.1)
                dashes(x, ya, x, yb, -lane_edge, dash=1.0, gap=0.0, w=0.1)
                zebra(x, c.road_y(mm) + half + 2.2, False)
                zebra(x, c.road_y(mm + 1) - half - 2.2, False)
        for mm in range(c.rows + 1):
            y = c.road_y(mm)
            for k in range(c.cols):
                xa, xb = c.road_x(k) + half + 4.0, c.road_x(k + 1) - half - 4.0
                dashes(xa, y, xb, y, 0.0)
                dashes(xa, y, xb, y, lane_edge, dash=1.0, gap=0.0, w=0.1)
                dashes(xa, y, xb, y, -lane_edge, dash=1.0, gap=0.0, w=0.1)
                zebra(c.road_x(k) + half + 2.2, y, True)
                zebra(c.road_x(k + 1) - half - 2.2, y, True)
        # the car parks' bays: a line each side of each bay
        for x, y, yaw in c.parking:
            bi = c.block_index(x, y)
            if bi is None or c.blocks[bi]["kind"] != "carpark":
                continue
            zz = city_map.KERB_H + 0.012
            for side in (-1.5, 1.5):
                quad(paint, Vec3(x + side - 0.06, y - 2.4, zz), Vec3(x + side + 0.06, y - 2.4, zz),
                     Vec3(x + side + 0.06, y + 2.4, zz), Vec3(x + side - 0.06, y + 2.4, zz), Vec3(0, 0, 1),
                     [(0, 0), (1, 0), (1, 1), (0, 1)])
        # the yellow lines round the places' yards
        for kind, (x0, y0, x1, y1) in c.zones.items():
            zz = city_map.KERB_H + 0.014
            for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
                length = math.hypot(bx - ax, by - ay)
                ux, uy = (bx - ax) / length, (by - ay) / length
                lx, ly = -uy * 0.1, ux * 0.1
                quad(m["yellow"], Vec3(ax, ay, zz), Vec3(bx, by, zz), Vec3(bx + lx, by + ly, zz), Vec3(ax + lx, ay + ly, zz),
                     Vec3(0, 0, 1), [(0, 0), (1, 0), (1, 1), (0, 1)])

    # ---------- trees, lamps, ramps, the edge ----------
    def trees(self, m):
        h0 = city_map.KERB_H
        for x, y, r, height in self.city.trees:
            cylinder(0.16, height * 0.25, "z", seg=7, tile=1.0, mesh=m["bark"], offset=Vec3(x, y, h0 + height * 0.25), caps=False)
            crown = max(1.2, height * 0.32)
            kart_gfx.ball(crown, seg=9, rings=6, mesh=m["leaves"], offset=Vec3(x, y, h0 + height * 0.62))

    def lamps(self, m):
        h0 = city_map.KERB_H
        steel, lamp = m["steel"], m["lamp"]
        for x, y in self.city.lamps:
            cylinder(0.07, 2.6, "z", seg=6, tile=1.0, mesh=steel, offset=Vec3(x, y, h0 + 2.6), caps=False)
            box(steel, x - 0.05, y - 0.05, x + 0.05, y + 0.05, h0 + 5.1, h0 + 5.25, tile=1.0)
            box(lamp, x - 0.22, y - 0.22, x + 0.22, y + 0.22, h0 + 5.0, h0 + 5.12, tile=1.0)

    def ramps(self, m):
        h0 = city_map.KERB_H
        L, H = city_map.RAMP_LEN, city_map.RAMP_H
        for rp in self.city.ramps:
            yr = math.radians(rp["yaw"])
            fx, fy = math.cos(yr), math.sin(yr)
            lx, ly = -fy, fx

            def at(a, c_, z):
                return Vec3(rp["x"] + fx * a + lx * c_, rp["y"] + fy * a + ly * c_, h0 + z)
            back, front, w = -L / 2, L / 2, 2.0
            up = Vec3(-fx * H, -fy * H, L)
            quad(m["ramp"], at(back, -w, 0), at(front, -w, H), at(front, w, H), at(back, w, 0), up, None)
            m["ramp"].poly([at(back, w, 0), at(front, w, H), at(front, w, 0)], normal=Vec3(lx, ly, 0))
            m["ramp"].poly([at(back, -w, 0), at(front, -w, 0), at(front, -w, H)], normal=Vec3(-lx, -ly, 0))
            quad(m["ramp"], at(front, -w, 0), at(front, w, 0), at(front, w, H), at(front, -w, H), Vec3(fx, fy, 0), None)
            # chevrons on the slope
            for k in range(3):
                a0 = back + 1.0 + k * 2.0
                a1 = a0 + 0.6
                z0, z1 = H * (a0 - back) / L + 0.01, H * (a1 - back) / L + 0.01
                quad(m["yellow"], at(a0, -w, z0), at(a1, -w, z1), at(a1, w, z1), at(a0, w, z0), up, [(0, 0), (1, 0), (1, 1), (0, 1)])

    def edge(self, m):
        """A railing round the city's edge (the barrier things are held at)."""
        e = self.city.edge
        steel = m["steel"]
        for (ax, ay, bx, by) in ((e[0], e[1], e[2], e[1]), (e[2], e[1], e[2], e[3]), (e[2], e[3], e[0], e[3]), (e[0], e[3], e[0], e[1])):
            length = math.hypot(bx - ax, by - ay)
            ux, uy = (bx - ax) / length, (by - ay) / length
            n = Vec3(-uy, ux, 0)
            for zr in (0.55, 0.95):
                quad(steel, Vec3(ax, ay, zr), Vec3(bx, by, zr), Vec3(bx, by, zr + 0.12), Vec3(ax, ay, zr + 0.12), n, None)
                quad(steel, Vec3(bx, by, zr), Vec3(ax, ay, zr), Vec3(ax, ay, zr + 0.12), Vec3(bx, by, zr + 0.12), -n, None)
            s = 0.0
            while s <= length:
                px, py = ax + ux * s, ay + uy * s
                box(steel, px - 0.05, py - 0.05, px + 0.05, py + 0.05, 0.0, 1.1, tile=1.0)
                s += 3.0

    # ---------- the four places' signs ----------
    def signs(self):
        c = self.city
        for kind, (dx, dy, _yaw) in c.places.items():
            words = PLACE_SIGNS.get(kind, kind.upper())
            colour = PLACE_COLOURS.get(kind, (1, 1, 1))
            # the board on the building's wall above the door (the doors face south, onto their yards)
            wall_y = dy + 2.0 - 0.06
            board = Mesh(colours=False)
            w = max(6.0, len(words) * 0.95)
            quad(board, Vec3(dx - w / 2, wall_y, 4.4), Vec3(dx + w / 2, wall_y, 4.4), Vec3(dx + w / 2, wall_y, 6.0),
                 Vec3(dx - w / 2, wall_y, 6.0), Vec3(0, -1, 0), [(0, 0), (1, 0), (1, 1), (0, 1)])
            bn = self.root.attachNewNode(board.node(f"sign {kind}"))
            kart_gfx.mats().apply(bn, None, (0.08, 0.08, 0.1), 0.6, 0.0)
            text = TextNode(f"sign {kind} words")
            text.setText(words)
            text.setAlign(TextNode.ACenter)
            text.setTextColor(*colour, 1)
            tn = self.root.attachNewNode(text)
            tn.setPos(dx, wall_y - 0.03, 4.75)
            tn.setScale(1.05)
            tn.setLightOff(1)
            tn.setShaderOff(1)
            tn.setDepthOffset(1)
            if look():
                tn.setColorScale(1, 1, 1, 1)

    def destroy(self):
        self.root.removeNode()


def ground_lift(city, x, y):
    """How far above the road a person standing at (x, y) is drawn: on a block, the kerb's height."""
    return PERSON_LIFT if city.block_index(x, y) is not None else 0.0


# ---------- the people (Fight Lab's fighters) ----------
def fighter_design(design):
    """A City Lab design as Fight Lab's: the look is its body, the colour its colour."""
    import fight_sim
    body = design.get("look") if design.get("look") in fight_sim.BODIES else "woman"
    d = fight_sim.default_design(design.get("name", "Driver"), tuple(design.get("colour") or (200, 120, 40)), body=body)
    return d


class PersonVisual:
    """A person drawn by Fight Lab's code, posed from City Lab's record."""

    def __init__(self, parent, design):
        import fight_model
        self.design = design
        self.vis = fight_model.make(parent, fighter_design(design))
        self.root = self.vis.root
        self.stride = 0.0
        self.t = 0.0
        self.hurt_at = -10.0
        self.was_hurt = False
        self.shown = True

    def anim(self, p, dt):
        move, mp, flags, v = p["move"], p["mp"], p["flags"], p["v"]
        if move == sim.MOVE_PUNCH:
            return "punch", 3.0 * mp / sim.MOVE_TICKS[sim.MOVE_PUNCH]
        if move == sim.MOVE_KICK:
            return "kick", 3.0 * mp / sim.MOVE_TICKS[sim.MOVE_KICK]
        if move == sim.MOVE_BLOCK:
            return "block", 0.0
        if move == sim.MOVE_DOWN:
            return "knockdown", min(1.0, mp / 40.0)
        if move == sim.MOVE_GETUP:
            return "getup", min(1.0, mp / 40.0)
        if move == sim.MOVE_HURT:
            return "hitstun", min(1.0, mp / sim.MOVE_TICKS[sim.MOVE_HURT])
        if flags & sim.FLAG_AIR:
            return "jump", 0.5
        if v > 0.3:
            self.stride += dt * (v * 0.9 + 0.3)
            return "walk_f", self.stride
        return "idle", self.t

    def update(self, p, lift, dt):
        """p: the person's record (blended or predicted); lift: the ground's height under them."""
        self.t += dt
        if p["link"]:  # in a car: not drawn (the car is)
            self.root.hide()
            return
        hurt = bool(p["flags"] & sim.FLAG_HURT) or p["move"] == sim.MOVE_HURT
        if hurt and not self.was_hurt:
            self.hurt_at = self.t
        self.was_hurt = hurt
        a, k = self.anim(p, dt)
        s = {"id": p["id"], "pos": [p["x"], p["y"], p["z"] + lift], "h": p["yaw"] - 90.0, "a": a, "k": k,
             "hp": p["hp"], "max": sim.HEALTH, "en": 0, "w": 0, "hu": min(9.0, self.t - self.hurt_at), "hits": 0, "ap": 0}
        # running: the walk played faster (the models have no run of their own)
        speed_up = 1.0 + (0.9 if p["flags"] & sim.FLAG_RUN and a == "walk_f" else 0.0)
        self.vis.update(s, dt * speed_up)

    def set_label(self, text, colour=(1, 1, 1, 1)):
        if hasattr(self.vis, "set_label"):
            self.vis.set_label(text, colour)

    def destroy(self):
        self.vis.destroy()


# ---------- the camera on foot ----------
class FootCamera:
    """Behind and above the person you watch, swinging round behind them as they go (slowly, so steering by the
    camera is steady). The keys move the person relative to this camera's heading (W is away from it).

    Views (V): behind, over the shoulder (closer, lower), above (the city from 60 m up). The mouse wheel zooms."""

    VIEWS = ("behind", "shoulder", "above")
    NAMES = {"behind": "Behind", "shoulder": "Over the shoulder", "above": "From above"}

    def __init__(self, base, city):
        self.base, self.city = base, city
        self.mode = "behind"
        self.zoom = 1.0
        self.yaw = 90.0       # the camera's heading (degrees, the game's: 0 = east)
        self.pos = None
        self.look = None
        base.camLens.setNear(0.2)
        base.camLens.setFar(2500)

    @property
    def name(self):
        return self.NAMES[self.mode]

    def cycle(self):
        self.mode = self.VIEWS[(self.VIEWS.index(self.mode) + 1) % len(self.VIEWS)]
        self.pos = None
        return self.name

    def wheel(self, factor):
        self.zoom = max(0.45, min(2.5, self.zoom * factor))

    def settings(self):
        return {"mode": self.mode, "zoom": self.zoom}

    def restore(self, saved):
        if isinstance(saved, dict):
            if saved.get("mode") in self.VIEWS:
                self.mode = saved["mode"]
            try:
                self.zoom = max(0.45, min(2.5, float(saved.get("zoom", 1.0))))
            except (TypeError, ValueError):
                pass

    def update(self, dt, x, y, z, heading, moving):
        """Follow a person at (x, y, z) facing heading (degrees); moving: they are walking (the camera swings round)."""
        if self.mode == "above":
            target = Point3(x, y, z)
            want = Point3(x, y - 25.0 * self.zoom, z + 60.0 * self.zoom)
            fov = 55
        else:
            if moving:
                d = (heading - self.yaw + 180.0) % 360.0 - 180.0
                self.yaw += d * min(1.0, dt * 1.6)
            dist, height, fov = (5.0, 2.3, 62) if self.mode == "behind" else (2.6, 1.75, 56)
            dist *= self.zoom
            yr = math.radians(self.yaw)
            fx, fy = math.cos(yr), math.sin(yr)
            target = Point3(x + fx * 1.5, y + fy * 1.5, z + 1.4)
            if self.mode == "shoulder":
                target += Vec3(-fy * 0.6, fx * 0.6, 0.15)
            dist = self.clear(x, y, z, -fx, -fy, dist)
            want = Point3(x - fx * dist, y - fy * dist, z + height * (0.6 + 0.4 * self.zoom))
            if self.mode == "shoulder":
                want += Vec3(-fy * 0.7, fx * 0.7, 0)
        if self.pos is None:
            self.pos, self.look = Point3(want), Point3(target)
        else:
            k = min(1.0, dt * 10.0)
            self.pos += (want - self.pos) * k
            self.look += (target - self.look) * min(1.0, dt * 14.0)
        self.base.camLens.setFov(fov)
        self.base.camera.setPos(self.pos)
        self.base.camera.lookAt(self.look)
        kart_gfx.follow_sun(x, y, z)

    def clear(self, x, y, z, dx, dy, dist):
        """The camera pulled in where a building is between it and the person (so you never look at a wall)."""
        steps = 10
        for i in range(1, steps + 1):
            d = dist * i / steps
            px, py = x + dx * d, y + dy * d
            _x, _y, hit = self.city.collide(px, py, 0.3)
            if hit == "building":
                return max(1.2, dist * (i - 1) / steps)
        return dist

    def move_from_keys(self, forward, right):
        """The keys' forward and right (-1 to 1 each) as a move in the world (x east, y north), magnitude up to 1."""
        yr = math.radians(self.yaw)
        fx, fy = math.cos(yr), math.sin(yr)
        rx, ry = fy, -fx  # (right of the camera's heading)
        mx, my = fx * forward + rx * right, fy * forward + ry * right
        mag = math.hypot(mx, my)
        if mag > 1.0:
            mx, my = mx / mag, my / mag
        return mx, my


# ---------- the cars (Kart Lab's sports cars) ----------
class CarVisual:
    """A car drawn by Kart Lab's code (kart_gfx.KartVisual with a sports car's body), placed from City Lab's record."""

    def __init__(self, parent, design):
        d = dict(design)
        d["body"] = design.get("body") if design.get("body") in sim.BODIES else "coupe"
        self.vis = kart_gfx.KartVisual(parent, d)
        self.root = self.vis.root
        self.design = design

    def update(self, c, lift, dt):
        """c: the car's record (blended); lift: the ground's height under it (a kerb's, on a block)."""
        flags = c["flags"]
        dmg = min(1.0, c["dmg"] / sim.DAMAGE_MAX)
        self.vis.update(c["x"], c["y"], c["z"] + lift, c["yaw"], c["steer"], c["v"], c["u"],
                        bool(flags & (sim.FLAG_DRIFT_L | sim.FLAG_DRIFT_R)), False, dt,
                        damage=[dmg * 0.6, dmg, dmg, dmg, dmg, dmg], shield=False,
                        braking=bool(flags & sim.FLAG_BRAKING),
                        spinning=bool(flags & (sim.FLAG_WHEELSPIN | sim.FLAG_HANDBRAKE)))

    def set_label(self, text, colour=(1, 1, 1, 1)):
        self.vis.set_label(text, colour)

    def destroy(self):
        self.vis.destroy()


class CarCamera(kart_gfx.ChaseCamera):
    """Kart Lab's chase camera, without its trackside TV cameras (a city has no track): chase and hood."""
    MODES = ("chase", "hood")
    NAMES = {"chase": "Chase", "hood": "Bonnet"}

    def __init__(self, base):
        super().__init__(base, "chase")

    def follow(self, dt, c, lift):
        self.update(dt, c["x"], c["y"], c["z"] + lift + 0.5, c["yaw"], c["v"], None)
        self.base.camLens.setFar(2500)


# ---------- the robots (Robot Lab's) ----------
_robot_state = {"ready": False}


def robots_ready(base):
    """Robot Lab's drawing state beside Kart Lab's (its materials and tier), once: rw_gfx.init would make a second
    set of lights and a second pipeline. False if Robot Lab's code can't be loaded here (a box robot is drawn)."""
    if _robot_state["ready"]:
        return _robot_state.get("ok", False)
    _robot_state["ready"] = True
    try:
        import rw_gfx
        used = tier()
        rw_gfx._state.clear()
        rw_gfx._state.update(mats=rw_gfx.Materials(base.loader, used), base=base, quality=used,
                             pipeline=kart_gfx._state.get("pipeline"), sun=kart_gfx._state.get("sun"))
        if kart_gfx._state.get("fog") is not None:
            rw_gfx._state["haze"] = kart_gfx._state["fog"]
        _robot_state["ok"] = True
    except Exception as e:  # noqa: BLE001
        print(f"City Lab: Robot Lab's robots not drawn ({type(e).__name__}: {e}); box robots instead", flush=True)
        _robot_state["ok"] = False
    return _robot_state["ok"]


class RobotVisual:
    """A robot drawn by Robot Lab's code (rw_gfx.RobotVisual), placed from City Lab's record: the chassis from the
    position and heading, the weapon on its pivot (spinning with the record's aux when it is a spinner or a drum), a red
    tint when it has gone rogue, dark when powered down. A name tag with its power when it is hurt."""

    def __init__(self, parent, design, base):
        self.design = design
        self.name = design.get("name", "ROBOT")
        self.angle = 0.0
        self.last_tag = None
        self.box = None
        if robots_ready(base):
            import lab_sim
            import rw_gfx
            self.vis = rw_gfx.RobotVisual(parent, design)
            self.root = self.vis.root
            weapon = lab_sim.design_weapon(design)
            sh = lab_sim.shapes(weapon, lab_sim.design_size(design))
            self.pivot = Vec3(sh["pivot"])
            self.axis = Vec3(sh["axis"])
            self.spins = weapon in ("spinner", "drum", "vdisc")
            self.ride = lab_sim.RIDE
        else:  # (a box with a disc: Robot Lab's code isn't here)
            self.vis = None
            self.root = parent.attachNewNode("robot")
            mesh = Mesh()
            from engine.rw_mesh import bevel_box
            bevel_box(0.6, 0.8, 0.2, 0.05, mesh=mesh, offset=Vec3(0, 0, 0.3))
            kart_gfx.part(self.root, mesh, "paint", rgb01(design.get("colour")), rough=0.5, metal=0.3)
            self.spins, self.ride = False, 0.0

    def update(self, r, lift, dt):
        from panda3d.core import Quat
        h = r["yaw"] - 90.0  # (Robot Lab's robots face +y: Panda's heading)
        q = Quat()
        q.setHpr((h, 0, 0))
        pos = Vec3(r["x"], r["y"], lift + self.ride)
        rogue, off = bool(r["flags"] & sim.FLAG_ROGUE), r["hp"] <= 0
        if self.vis is None:
            self.root.setPos(pos)
            self.root.setH(h)
        else:
            rate = min(2400.0, r["aux"] * 1.6)  # (degrees a second: the weapon winds up as the robot gets cross)
            self.angle = (self.angle + rate * dt) % 360.0
            spin = Quat()
            spin.setFromAxisAngle(self.angle if self.spins else 0.0, self.axis)
            wq = spin * q
            wpos = pos + q.xform(self.pivot)
            self.vis.update({"pos": [pos.x, pos.y, pos.z], "quat": list(q), "wpos": [wpos.x, wpos.y, wpos.z],
                             "wquat": list(wq), "speed": r["v"], "rpm": r["aux"] / 4.0, "on": True}, dt)
        if off:
            self.root.setColorScale(0.35, 0.35, 0.4, 1)
        elif rogue:
            self.root.setColorScale(1.4, 0.55, 0.5, 1)
        else:
            self.root.clearColorScale()
        tag = f"{self.name}  {r['hp']}%" if 0 < r["hp"] < sim.POWER else (f"{self.name}  REBOOTING" if off else "")
        if tag != self.last_tag:
            self.last_tag = tag
            if self.vis is not None and hasattr(self.vis, "set_label"):
                if tag:
                    self.vis.set_label(tag, (1, 0.45, 0.35, 1) if rogue else (1, 1, 1, 1))
                if getattr(self.vis, "tag", None) is not None:
                    (self.vis.tag.show if tag else self.vis.tag.hide)()

    def destroy(self):
        if self.vis is not None and hasattr(self.vis, "destroy"):
            self.vis.destroy()
        else:
            self.root.removeNode()


class Sparks:
    """Robot Lab's sparks (rw_fx.Effects): where a punch, a kick or a zap lands."""

    def __init__(self, render, base):
        self.fx = None
        if robots_ready(base):
            try:
                import rw_fx
                self.fx = rw_fx.Effects(render, tier())
            except Exception as e:  # noqa: BLE001
                print(f"City Lab: no sparks ({type(e).__name__}: {e})", flush=True)

    def hit(self, x, y, z, damage, kind="bump"):
        if self.fx is not None:
            self.fx.impact((x, y, z), damage, kind)

    def update(self, dt):
        if self.fx is not None:
            self.fx.update(dt)



class HealthBar:
    """Your health, bottom left: a bar that empties, amber then red as it gets low, white for a moment as a hit lands."""

    def __init__(self, parent):
        from direct.gui.DirectGui import DirectFrame
        from direct.gui.OnscreenText import OnscreenText
        self.frame = DirectFrame(parent=parent, frameColor=(0, 0, 0, 0.55), frameSize=(0, 0.62, 0, 0.07), pos=(0.05, 0, 0.06))
        self.fill = DirectFrame(parent=self.frame, frameColor=(0.3, 0.85, 0.35, 1), frameSize=(0, 0.6, 0, 0.05),
                                pos=(0.01, 0, 0.01))
        self.label = OnscreenText(parent=self.frame, text="HEALTH", pos=(0.01, 0.085), scale=0.035, fg=(1, 1, 1, 1),
                                  shadow=(0, 0, 0, 0.8), align=TextNode.ALeft)
        self.flash = 0.0
        self.shown = None

    def set(self, share, hurt=False):
        share = max(0.0, min(1.0, share))
        self.flash = 0.25 if hurt else max(0.0, self.flash - 0.02)
        key = (round(share, 3), round(self.flash, 2))
        if key == self.shown:
            return
        self.shown = key
        self.fill["frameSize"] = (0, 0.6 * share, 0, 0.05)
        colour = (0.3, 0.85, 0.35, 1) if share > 0.5 else (0.95, 0.75, 0.2, 1) if share > 0.25 else (0.95, 0.25, 0.2, 1)
        if self.flash > 0:
            colour = (1, 1, 1, 1)
        self.fill["frameColor"] = colour

    def show(self, on):
        (self.frame.show if on else self.frame.hide)()



# ---------- the jobs in the city (step 4): the places' rings, the target's beam, the arrow, chips, checkpoints ----------
JOB_COLOURS = {"depot": (1.0, 0.72, 0.15), "rank": (1.0, 0.9, 0.1), "arcade": (1.0, 0.3, 0.9), "race": (0.3, 0.9, 1.0),
               "delivery": (1.0, 0.72, 0.15), "taxi": (1.0, 0.9, 0.1), "roundup": (1.0, 0.3, 0.3), "chip": (0.3, 1.0, 0.55)}
MARKER_WORDS = {"depot": "DELIVERIES", "rank": "TAXI (in a car)", "arcade": "CHIPS PAID  /  ROUND-UP", "race": "STREET RACE (stop here)"}


def glow(np_, colour, alpha=1.0):
    """Drawn as it is, unlit, see-through: the jobs' signs over the city."""
    np_.setLightOff(1)
    np_.setShaderOff(1)
    np_.setFogOff(1)
    np_.setColor(*colour, alpha)
    if alpha < 1.0:
        np_.setTransparency(TransparencyAttrib.M_alpha)
        np_.setDepthWrite(False)
        np_.setBin("transparent", 10)
    np_.setTwoSided(True)
    return np_


def ring_mesh(r_in, r_out, seg=40):
    m = Mesh()
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)
        m.poly([Vec3(c0 * r_in, s0 * r_in, 0), Vec3(c0 * r_out, s0 * r_out, 0), Vec3(c1 * r_out, s1 * r_out, 0),
                Vec3(c1 * r_in, s1 * r_in, 0)], normal=Vec3(0, 0, 1))
    return m


def wall_mesh(r, h, seg=32):
    m = Mesh()
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        p0, p1 = Vec3(math.cos(a0) * r, math.sin(a0) * r, 0), Vec3(math.cos(a1) * r, math.sin(a1) * r, 0)
        m.poly([p0, p1, p1 + Vec3(0, 0, h), p0 + Vec3(0, 0, h)], normal=p0 + p1)
    return m


def float_text(parent, words, colour, scale=0.9):
    t = TextNode(f"label {words}")
    t.setText(words)
    t.setAlign(TextNode.ACenter)
    t.setTextColor(*colour, 1)
    t.setShadow(0.05, 0.05)
    t.setShadowColor(0, 0, 0, 0.9)
    np_ = parent.attachNewNode(t)
    np_.setScale(scale)
    np_.setBillboardPointEye()
    np_.setLightOff(1)
    np_.setShaderOff(1)
    np_.setFogOff(1)
    np_.setBin("fixed", 50)
    np_.setDepthWrite(False)
    return np_


class Marker:
    """A glowing ring on the ground, a see-through wall round it and its words above: where a job starts."""

    def __init__(self, parent, x, y, z, colour, words, radius):
        self.root = parent.attachNewNode("marker")
        self.root.setPos(x, y, z + 0.03)
        glow(self.root.attachNewNode(ring_mesh(radius - 0.35, radius).node("ring")), colour, 0.95)
        self.wall = glow(self.root.attachNewNode(wall_mesh(radius, 1.4).node("wall")), colour, 0.22)
        self.label = float_text(self.root, words, colour, 0.8)
        self.label.setZ(3.0)
        self.t = 0.0

    def update(self, dt, on=True):
        self.t += dt
        (self.root.show if on else self.root.hide)()
        if on:
            self.wall.setAlphaScale(0.6 + 0.4 * math.sin(self.t * 3.0))


class JobsVisual:
    """Everything the jobs show in the city: the rings at the places' doors and the race line, the beam of light over
    your job's target with an arrow over your head pointing at it, the chips (spinning green discs, gone when found),
    the race's checkpoints while you race."""

    def __init__(self, parent, city):
        self.city = city
        self.root = parent.attachNewNode("jobs")
        h0 = city_map.KERB_H
        self.markers = {}
        for kind in ("depot", "rank", "arcade"):
            d = city.places.get(kind)
            if d:
                self.markers[kind] = Marker(self.root, d[0], d[1], h0, JOB_COLOURS[kind], MARKER_WORDS[kind], 3.5)
        self.race_marker = None
        self.race_at = None
        # the target's beam, and the arrow over your head
        self.beam = glow(self.root.attachNewNode(wall_mesh(1.3, 45.0, 24).node("beam")), (1, 0.8, 0.2), 0.32)
        self.beam.hide()
        self.beam_label = float_text(self.root, "", (1, 1, 1), 1.0)
        self.beam_label.hide()
        arrow = Mesh()
        arrow.poly([Vec3(1.1, 0, 0), Vec3(-0.3, 0.6, 0), Vec3(-0.3, 0.22, 0), Vec3(-0.9, 0.22, 0), Vec3(-0.9, -0.22, 0),
                    Vec3(-0.3, -0.22, 0), Vec3(-0.3, -0.6, 0)], normal=Vec3(0, 0, 1))
        self.arrow = glow(self.root.attachNewNode(arrow.node("arrow")), (1, 0.85, 0.2), 0.9)
        self.arrow.hide()
        # the chips
        self.chips = []
        disc = Mesh()
        cylinder(0.32, 0.04, "x", seg=16, mesh=disc)
        for x, y in city.chips:
            c = glow(self.root.attachNewNode(disc.node("chip")), JOB_COLOURS["chip"], 1.0)
            c.setPos(x, y, h0 + 0.8)
            self.chips.append(c)
        # the checkpoints (made when a race shows)
        self.checks = []
        self.t = 0.0

    def set_race_line(self, x, y):
        if self.race_at == (x, y):
            return
        if self.race_marker is not None:
            self.race_marker.root.removeNode()
        self.race_at = (x, y)
        self.race_marker = Marker(self.root, x, y, 0.0, JOB_COLOURS["race"], MARKER_WORDS["race"], 6.0)

    def update(self, dt, jobs, me, my_id, my_car):
        """jobs: the jobs message (Jobs.state); me: your person's record (drawn); my_car: your car's id or None."""
        self.t += dt
        if not jobs:
            return
        enabled = jobs.get("enabled", {})
        for kind, m in self.markers.items():
            on = enabled.get({"depot": "delivery", "rank": "taxi", "arcade": "roundup"}[kind], True) or kind == "arcade"
            m.update(dt, on)
        if jobs.get("line"):
            self.set_race_line(*jobs["line"])
            race = jobs.get("race")
            self.race_marker.update(dt, enabled.get("race", True) and (race is None or race["state"] != "racing"))
        gone = set(jobs.get("chips_gone", ()))
        for i, c in enumerate(self.chips):
            if i in gone:
                c.hide()
            else:
                c.show()
                c.setH((self.t * 120.0 + i * 40) % 360)
                c.setZ(city_map.KERB_H + 0.8 + 0.15 * math.sin(self.t * 2.5 + i))
        mine = (jobs.get("mine") or {}).get(str(my_id)) or (jobs.get("mine") or {}).get(my_id)
        target = mine.get("target") if mine else None
        if target:
            colour = JOB_COLOURS.get(mine["kind"], (1, 0.8, 0.2))
            lift = ground_lift(self.city, target[0], target[1])
            self.beam.setPos(target[0], target[1], lift)
            self.beam.setColor(*colour, 0.32)
            self.beam.show()
            self.beam_label.node().setText(mine.get("name", ""))
            self.beam_label.setPos(target[0], target[1], lift + 6.0)
            self.beam_label.show()
            self.arrow.hide()  # (the way to go is the HUD's arrow: CompassArrow; one over your head read edge on)
        else:
            self.beam.hide()
            self.beam_label.hide()
            self.arrow.hide()
        # the checkpoints: the race's course while you are in it, the next one bright
        race = jobs.get("race")
        in_race = race is not None and my_car is not None and str(my_car) in (race.get("cars") or {})
        course = race["course"] if in_race else []
        while len(self.checks) < len(course):
            self.checks.append(Marker(self.root, 0, 0, 0, JOB_COLOURS["race"], "", 7.0))
        nxt = None
        if in_race:
            cp = race["cars"][str(my_car)]
            nxt = (cp + 1) % len(course) if race["state"] == "racing" else 1
        for i, m in enumerate(self.checks):
            if i < len(course):
                m.root.setPos(course[i][0], course[i][1], 0.03)
                m.update(dt, True)
                m.root.setColorScale(1, 1, 1, 1 if i == nxt else 0.25)
                m.label.node().setText("NEXT" if i == nxt else ("FINISH" if i == 0 else ""))
            else:
                m.update(dt, False)


class Minimap:
    """The city from above, top right: the blocks, the four places in their colours, you (white), the other people
    (blue), the cars (grey), the robots (red: orange when cross, magenta when rogue), the chips (green), your job's
    target (yellow) and the race's checkpoints."""

    SIZE = 0.56

    def __init__(self, parent, city):
        from panda3d.core import CardMaker
        self.city = city
        e = city.edge
        self.x0, self.y0 = e[0], e[1]
        self.k = self.SIZE / max(e[2] - e[0], e[3] - e[1])
        w, h = (e[2] - e[0]) * self.k, (e[3] - e[1]) * self.k
        self.root = parent.attachNewNode("minimap")
        self.root.setPos(-w - 0.04, 0, -h - 0.04)
        cm = CardMaker("map")
        cm.setFrame(-0.01, w + 0.01, -0.01, h + 0.01)
        bg = self.root.attachNewNode(cm.generate())
        bg.setColor(0.05, 0.06, 0.08, 0.75)
        bg.setTransparency(TransparencyAttrib.M_alpha)
        cm.setFrame(*self.rect(city.xmin, city.ymin, city.xmax, city.ymax))
        roads = self.root.attachNewNode(cm.generate())
        roads.setColor(0.42, 0.43, 0.47, 1)
        blocks = self.root.attachNewNode("blocks")
        for b in city.blocks:
            cm.setFrame(*self.rect(b["x0"], b["y0"], b["x1"], b["y1"]))
            n = blocks.attachNewNode(cm.generate())
            colour = {"park": (0.22, 0.42, 0.22), "carpark": (0.3, 0.3, 0.33)}.get(b["kind"], (0.16, 0.17, 0.2))
            kind = b["kind"]
            if kind in JOB_COLOURS:
                colour = tuple(c * 0.55 for c in JOB_COLOURS[kind])
            n.setColor(*colour, 1)
        blocks.flattenStrong()
        cm.setFrame(-0.008, 0.008, -0.008, 0.008)
        self.dot = cm.generate()
        self.dots = []
        self.used = 0
        self.root.setBin("fixed", 70)

    def rect(self, x0, y0, x1, y1):
        return ((x0 - self.x0) * self.k, (x1 - self.x0) * self.k, (y0 - self.y0) * self.k, (y1 - self.y0) * self.k)

    def put(self, x, y, colour, size=1.0):
        if self.used >= len(self.dots):
            d = self.root.attachNewNode(self.dot.makeCopy())
            self.dots.append(d)
        d = self.dots[self.used]
        self.used += 1
        d.show()
        d.setPos((x - self.x0) * self.k, 0, (y - self.y0) * self.k)
        d.setScale(size)
        d.setColor(*colour, 1)

    def update(self, things, my_id, jobs, my_car):
        self.used = 0
        if jobs:
            gone = set(jobs.get("chips_gone", ()))
            for i, (x, y) in enumerate(self.city.chips):
                if i not in gone:
                    self.put(x, y, JOB_COLOURS["chip"], 0.6)
            race = jobs.get("race")
            if race and my_car is not None and str(my_car) in (race.get("cars") or {}):
                for x, y in race["course"]:
                    self.put(x, y, JOB_COLOURS["race"], 1.4)
            mine = (jobs.get("mine") or {}).get(str(my_id)) or (jobs.get("mine") or {}).get(my_id)
            if mine and mine.get("target"):
                self.put(mine["target"][0], mine["target"][1], (1, 0.85, 0.15), 2.0)
        for tid, t in things.items():
            kind = sim.kind_of(tid)
            if kind == "car":
                self.put(t["x"], t["y"], (0.8, 0.8, 0.85) if tid != my_car else (1, 1, 1), 0.8 if tid != my_car else 1.6)
            elif kind == "robot":
                c = (1, 0.25, 0.9) if t["flags"] & sim.FLAG_ROGUE else (1, 0.55, 0.1) if t["flags"] & sim.FLAG_CROSS else (0.95, 0.25, 0.2)
                if t["hp"] <= 0:
                    c = (0.4, 0.4, 0.4)
                self.put(t["x"], t["y"], c, 0.9)
            elif tid != my_id and not t["link"]:
                self.put(t["x"], t["y"], (0.4, 0.75, 1.0), 1.0)
        me = things.get(my_id)
        if me is not None:
            self.put(me["x"], me["y"], (1, 1, 1), 1.7)
        for d in self.dots[self.used:]:
            d.hide()

    def show(self, on):
        (self.root.show if on else self.root.hide)()



class CompassArrow:
    """The way to your job's target, top middle under its words: an arrow turned to point where the target is from
    where the camera looks (up the screen is straight ahead)."""

    def __init__(self, parent):
        from panda3d.core import GeomNode
        m = Mesh()
        pts = [(0, 0.075), (-0.055, -0.01), (-0.02, -0.01), (-0.02, -0.06), (0.02, -0.06), (0.02, -0.01), (0.055, -0.01)]
        m.poly([Vec3(x, 0, z) for x, z in pts], normal=Vec3(0, -1, 0))
        self.np = parent.attachNewNode(m.node("compass"))
        self.np.setPos(0, 0, -0.28)
        self.np.setTwoSided(True)
        self.np.setLightOff(1)
        self.np.setShaderOff(1)
        self.np.hide()

    def point(self, bearing, camera_yaw, colour):
        """bearing, camera_yaw: degrees in the game's frame (0 = east, anticlockwise)."""
        rel = (bearing - camera_yaw + 180.0) % 360.0 - 180.0  # (positive: to the left)
        self.np.setR(-rel)
        self.np.setColor(*colour, 1)
        self.np.show()

    def hide(self):
        self.np.hide()
