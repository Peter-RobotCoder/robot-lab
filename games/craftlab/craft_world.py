"""Craft Lab's world (CHANGE 200): an island of blocks, generated from a seed, kept as numpy arrays.

    blocks[x, y, z]   the block at each place (craft_blocks ids; 0 is air), z up, x east, y north
    meta[x, y, z]     a number more for the blocks that need one: a door's way and whether it is open, a ladder's
                      wall, a crop's growth, a bed's half, a smelter's way
    sky[x, y, z]      the light from the sky (0 to 15): 15 straight down an open column, one less for each block
                      sideways under a roof
    glow[x, y, z]     the light from torches, lumen blocks, magma (0 to 15), one less for each block away

The island: layered noise for the heights, shaped so the edges go down into the sea; biomes from two more noises
(warm or cold, wet or dry): grassland and forests, a sandy desert with cacti, pale woods, snowy pine hills, rocky
peaks; beaches at the water's edge, soil over stone, corestone at the bottom; caves (two noise fields, open where
both are near zero), ores by depth (coal, copper, iron, and crystal deep down), magma pools in the deepest caves;
trees, berry bushes, tall grass and flowers. The same seed makes the same world on every computer, so a window
offline and the server online agree.

A world is cut into chunks 16 x 16 blocks across (and the whole height) for drawing and for the network: changing a
block marks its chunk (and its neighbour, at an edge) to be drawn again.
"""
import json
import os
import zlib

import numpy as np

import craft_blocks as B

CHUNK = 16
SIZES = {"small": (128, 128, 64), "medium": (192, 192, 64), "large": (256, 256, 80)}
DEFAULT_SIZE = "medium"
SEA = 20
ID = B.ID
WORLD_VERSION = 1
_T = None


def tables():
    global _T
    if _T is None or len(B.BLOCKS) != _T.get("n"):
        _T = B.tables()
        _T["n"] = len(B.BLOCKS)
        # light passes through: air, plants, torches, glass, leaves (a little), water (a little)
        dim = np.full(256, 15, np.uint8)
        for b in B.BLOCKS:
            if not b["opaque"] or b["shape"] != "cube":
                dim[b["id"]] = 1
        for k in ("leaves", "pine_leaves", "pale_leaves"):
            dim[ID[k]] = 2
        dim[ID["water"]] = 2
        dim[ID["ice"]] = 2
        _T["dim"] = dim
    return _T


# ---------- noise ----------
def value_noise_2d(shape, cell, rng):
    """Smooth noise from -1 to 1 over a shape (X, Y) with features about cell blocks across."""
    gx, gy = shape[0] // cell + 2, shape[1] // cell + 2
    grid = rng.random((gx, gy)) * 2 - 1
    x = np.arange(shape[0]) / cell
    y = np.arange(shape[1]) / cell
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = x - x0, y - y0
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a = grid[x0][:, y0]
    b = grid[x0 + 1][:, y0]
    c = grid[x0][:, y0 + 1]
    d = grid[x0 + 1][:, y0 + 1]
    fx, fy = fx[:, None], fy[None, :]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def fbm_2d(shape, cell, octaves, rng, gain=0.5):
    out, amp, total = np.zeros(shape), 1.0, 0.0
    for _ in range(octaves):
        out += value_noise_2d(shape, max(1, cell), rng) * amp
        total += amp
        amp *= gain
        cell //= 2
    return out / total


def value_noise_3d(shape, cell, rng):
    gx, gy, gz = (s // c + 2 for s, c in zip(shape, cell))
    grid = rng.random((gx, gy, gz)).astype(np.float32) * 2 - 1
    axes = []
    for n, c in zip(shape, cell):
        t = np.arange(n, dtype=np.float32) / c
        i = t.astype(int)
        f = t - i
        axes.append((i, f * f * (3 - 2 * f)))
    (xi, fx), (yi, fy), (zi, fz) = axes
    fx, fy, fz = fx[:, None, None], fy[None, :, None], fz[None, None, :]
    out = np.zeros(shape, np.float32)
    for dx in (0, 1):
        wx = fx if dx else 1 - fx
        for dy in (0, 1):
            wy = fy if dy else 1 - fy
            for dz in (0, 1):
                wz = fz if dz else 1 - fz
                out += grid[np.ix_(xi + dx, yi + dy, zi + dz)] * wx * wy * wz
    return out


def ranked(a):
    """a's values replaced by their rank, from 0 to 1 (so a threshold is a share of the island)."""
    flat = a.ravel()
    out = np.empty(flat.size)
    out[np.argsort(flat, kind="stable")] = np.linspace(0, 1, flat.size)
    return out.reshape(a.shape)


# ---------- the world ----------
class World:
    def __init__(self, size=DEFAULT_SIZE, seed=1, blank=False):
        self.size_key = size if size in SIZES else DEFAULT_SIZE
        self.X, self.Y, self.Z = SIZES[self.size_key]
        self.seed = int(seed)
        self.blocks = np.zeros((self.X, self.Y, self.Z), np.uint8)
        self.meta = np.zeros((self.X, self.Y, self.Z), np.uint8)
        self.sky = np.zeros((self.X, self.Y, self.Z), np.uint8)
        self.glow = np.zeros((self.X, self.Y, self.Z), np.uint8)
        self.dirty = set()          # chunks to draw again: (cx, cy)
        self.changes = []           # [(x, y, z, block, meta)] since the last time someone took them
        self.spawn = (self.X // 2 + 0.5, self.Y // 2 + 0.5, float(self.Z - 4))
        self.biome = np.zeros((self.X, self.Y), np.uint8)
        if not blank:
            self.generate()
            self.light_all()

    @property
    def chunks(self):
        return [(cx, cy) for cx in range(self.X // CHUNK) for cy in range(self.Y // CHUNK)]

    # ---------- making it ----------
    def generate(self):
        X, Y, Z = self.X, self.Y, self.Z
        rng = np.random.default_rng(self.seed)
        heightn = fbm_2d((X, Y), 64, 5, rng)
        hills = fbm_2d((X, Y), 32, 3, rng)
        warm = fbm_2d((X, Y), 96, 2, rng)
        wet = fbm_2d((X, Y), 80, 2, rng)
        # the island: higher in the middle, down to the sea bed at the edges
        xs = (np.arange(X) - X / 2) / (X / 2)
        ys = (np.arange(Y) - Y / 2) / (Y / 2)
        edge = np.sqrt(xs[:, None] ** 2 + ys[None, :] ** 2)
        island = np.clip(1.15 - edge * 1.1, -0.6, 1.0)
        peaks = np.maximum(0.0, hills) ** 1.5 * 34
        height = SEA - 6 + island * 22 + heightn * 14 + peaks * np.clip(island, 0, 1)
        height = np.clip(height, 3, Z - 12).astype(int)
        # biomes: 0 grass, 1 forest, 2 desert, 3 pale woods, 4 snow, 5 peaks, 6 beach, 7 sea
        warm, wet = ranked(warm), ranked(wet)  # (0 to 1, evenly: every island has some of each biome)
        biome = np.zeros((X, Y), np.uint8)
        biome[wet > 0.55] = 1
        biome[(warm > 0.76) & (wet < 0.55)] = 2
        biome[(warm > 0.18) & (warm < 0.4) & (wet > 0.5)] = 3
        biome[warm < 0.18] = 4
        biome[height > SEA + 24] = 5
        beach = (height <= SEA + 1) & (height >= SEA - 1)
        biome[beach & (biome != 4)] = 6
        biome[height < SEA - 2] = 7
        self.biome = biome
        z = np.arange(Z)[None, None, :]
        h = height[:, :, None]
        b = self.blocks
        b[:] = 0
        b[z <= h] = ID["stone"]
        top = biome[:, :, None]
        soil_depth = 3 + (fbm_2d((X, Y), 8, 1, rng) > 0)[:, :, None]
        under = (z < h) & (z >= h - soil_depth)
        surface = z == h
        sandy = (top == 2) | (top == 6) | (top == 7)
        b[under & ~sandy] = ID["soil"]
        b[under & sandy] = ID["sand"]
        b[under & (top == 2) & (z < h - 2)] = ID["sandstone"]
        b[surface & ~sandy] = ID["grass"]
        b[surface & sandy] = ID["sand"]
        b[surface & (top == 4)] = ID["snow"]
        b[surface & (top == 5)] = ID["stone"]
        b[surface & (top == 5) & (h > SEA + 30)] = ID["snow"]
        b[(z < h) & (z >= h - 2) & (top == 5)] = ID["stone"]
        sea_floor = surface & (top == 7)
        clay = fbm_2d((X, Y), 6, 1, rng)[:, :, None] > 0.45
        b[sea_floor & clay] = ID["clay"]
        b[sea_floor & ~clay & (fbm_2d((X, Y), 10, 1, rng)[:, :, None] > 0.2)] = ID["grit"]
        # caves: open where two noises are both near zero, under the surface, over the bottom
        n1 = value_noise_3d((X, Y, Z), (24, 24, 12), rng)
        n2 = value_noise_3d((X, Y, Z), (20, 20, 10), rng)
        cave = (np.abs(n1) < 0.08) & (np.abs(n2) < 0.12) & (z < h - 3) & (z > 3)
        big = value_noise_3d((X, Y, Z), (40, 40, 16), rng) > 0.55
        cave |= big & (z < h - 6) & (z > 4) & (z < SEA - 2)
        b[cave] = 0
        # ores, by depth (in stone only)
        stone = b == ID["stone"]
        r3 = rng.random((X, Y, Z), dtype=np.float32)
        for key, deepest, share, blob in (("coal_ore", Z, 0.012, 0.35), ("copper_ore", SEA + 14, 0.008, 0.3),
                                          ("iron_ore", SEA + 4, 0.0065, 0.3), ("crystal_ore", 14, 0.0016, 0.2)):
            seeds = stone & (r3 < share) & (z < deepest)
            grown = seeds.copy()
            for axis in (0, 1, 2):
                for s in (1, -1):
                    grown |= np.roll(seeds, s, axis) & (rng.random((X, Y, Z), dtype=np.float32) < blob)
            b[grown & stone] = ID[key]
            r3 = rng.random((X, Y, Z), dtype=np.float32)
        # magma pools in the deepest caves; corestone floor
        b[(b == 0) & (z <= 6)] = ID["magma"]
        b[:, :, 0] = ID["corestone"]
        b[:, :, 1][rng.random((X, Y)) < 0.5] = ID["corestone"]
        # the sea (and ice on cold water)
        water = (b == 0) & (z <= SEA)
        open_above = np.cumsum((b[:, :, ::-1] != 0), axis=2)[:, :, ::-1] == 0
        b[water & (open_above | (z > h))] = ID["water"]
        b[(b == ID["water"]) & (z == SEA) & (top == 4)] = ID["ice"]
        self.height = height
        self.plants(rng)
        self.spawn = self.find_spawn()

    def plants(self, rng):
        """Trees, bushes, grass and flowers on the land; cacti in the desert."""
        X, Y = self.X, self.Y
        b = self.blocks
        density = {0: 0.004, 1: 0.03, 2: 0.0, 3: 0.022, 4: 0.012, 5: 0.0015, 6: 0.0}
        r = rng.random((X, Y))
        r2 = rng.random((X, Y))
        for x in range(3, X - 3):
            for y in range(3, Y - 3):
                zt = int(self.height[x, y])
                if zt >= self.Z - 12 or zt < SEA:
                    continue
                ground = b[x, y, zt]
                kind = int(self.biome[x, y])
                if ground not in (ID["grass"], ID["snow"], ID["sand"]):
                    continue
                if b[x, y, zt + 1] != 0:
                    continue
                if kind == 2 and ground == ID["sand"]:
                    if r[x, y] < 0.006:
                        for k in range(1, 2 + int(r2[x, y] * 3)):
                            b[x, y, zt + k] = ID["cactus"]
                    continue
                if r[x, y] < density.get(kind, 0):
                    self.tree(x, y, zt + 1, "pine" if kind == 4 else "pale" if kind == 3 else "oak", r2[x, y])
                elif ground == ID["grass"]:
                    if r[x, y] < density.get(kind, 0) + 0.004:
                        b[x, y, zt + 1] = ID["berry_bush"]
                        self.meta[x, y, zt + 1] = 1  # (with berries)
                    elif r[x, y] < 0.16 and kind in (0, 1):
                        b[x, y, zt + 1] = ID["tall_grass"]
                    elif r[x, y] < 0.175 and kind in (0, 1):
                        b[x, y, zt + 1] = ID["flower_red"] if r2[x, y] < 0.5 else ID["flower_yellow"]

    def tree(self, x, y, z, kind, k):
        b = self.blocks
        log, leaf = {"oak": ("log", "leaves"), "pine": ("pine_log", "pine_leaves"), "pale": ("pale_log", "pale_leaves")}[kind]
        tall = 4 + int(k * 3) + (2 if kind == "pale" else 0)
        if z + tall + 3 >= self.Z:
            return
        for dz in range(tall):
            b[x, y, z + dz] = ID[log]
        top = z + tall
        if kind == "pine":
            for dz in range(-4, 2):
                r = max(0, (2 - dz) // 2) if dz > -4 else 2
                for dx in range(-r, r + 1):
                    for dy in range(-r, r + 1):
                        if abs(dx) + abs(dy) <= r + 1 and b[x + dx, y + dy, top + dz] == 0:
                            b[x + dx, y + dy, top + dz] = ID[leaf]
            b[x, y, top + 1] = ID[leaf]
            return
        for dz in range(-2, 2):
            r = 2 if dz < 0 else 1
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    corner = abs(dx) == r and abs(dy) == r
                    if corner and (dz >= 0 or (x * 7 + y * 13 + dz) % 3 == 0):
                        continue
                    if b[x + dx, y + dy, top + dz] == 0:
                        b[x + dx, y + dy, top + dz] = ID[leaf]

    def find_spawn(self):
        """Dry land near the middle of the island: the highest grass in the middle few dozen blocks."""
        cx, cy = self.X // 2, self.Y // 2
        best = None
        for r in range(0, self.X // 2, 2):
            for dx, dy in ((r, 0), (-r, 0), (0, r), (0, -r), (r, r), (-r, -r), (r, -r), (-r, r)):
                x, y = cx + dx, cy + dy
                if not (0 <= x < self.X and 0 <= y < self.Y):
                    continue
                z = self.top(x, y)
                if self.blocks[x, y, z] in (ID["grass"], ID["sand"], ID["snow"]) and SEA < z < self.Z - 8:
                    best = (x + 0.5, y + 0.5, float(z + 1))
                    break
            if best:
                return best
        return (cx + 0.5, cy + 0.5, float(self.Z - 4))

    def top(self, x, y):
        """The highest block that isn't air in a column (0 if none)."""
        col = np.nonzero(self.blocks[x, y] != 0)[0]
        return int(col[-1]) if len(col) else 0

    # ---------- the light ----------
    def light_all(self):
        self.sky[:] = 0
        self.glow[:] = 0
        self.light_region(0, 0, self.X, self.Y)

    def light_region(self, x0, y0, x1, y1):
        """Sky and block light worked out again over a box of columns (and 15 blocks round it, light's reach): the
        sky straight down each open column, then both spread sideways and down, one level less a block."""
        t = tables()
        m = 15
        ax0, ay0 = max(0, x0 - m), max(0, y0 - m)
        ax1, ay1 = min(self.X, x1 + m), min(self.Y, y1 + m)
        b = self.blocks[ax0:ax1, ay0:ay1]
        dim = t["dim"][b]
        # the sky: full light down each column until a block dims it
        stop = np.cumsum(dim[:, :, ::-1] >= 15, axis=2)[:, :, ::-1]
        loss = np.cumsum(np.where(dim[:, :, ::-1] < 15, dim[:, :, ::-1] - 1, 0), axis=2)[:, :, ::-1]
        sky = np.where(stop == 0, np.clip(15 - loss, 0, 15), 0).astype(np.int16)
        glow = t["light"][b].astype(np.int16)
        passes = dim < 15
        for _ in range(14):
            for arr in (sky, glow):
                best = arr.copy()
                best[1:] = np.maximum(best[1:], arr[:-1])
                best[:-1] = np.maximum(best[:-1], arr[1:])
                best[:, 1:] = np.maximum(best[:, 1:], arr[:, :-1])
                best[:, :-1] = np.maximum(best[:, :-1], arr[:, 1:])
                best[:, :, 1:] = np.maximum(best[:, :, 1:], arr[:, :, :-1])
                best[:, :, :-1] = np.maximum(best[:, :, :-1], arr[:, :, 1:])
                spread = np.where(passes, best - dim, 0)
                np.maximum(arr, spread, out=arr)
        glow = np.maximum(glow, t["light"][b])
        ix0, iy0 = x0 - ax0, y0 - ay0
        self.sky[x0:x1, y0:y1] = np.clip(sky[ix0:ix0 + x1 - x0, iy0:iy0 + y1 - y0], 0, 15)
        self.glow[x0:x1, y0:y1] = np.clip(glow[ix0:ix0 + x1 - x0, iy0:iy0 + y1 - y0], 0, 15)

    # ---------- reading and changing ----------
    def inside(self, x, y, z):
        return 0 <= x < self.X and 0 <= y < self.Y and 0 <= z < self.Z

    def get(self, x, y, z):
        if 0 <= x < self.X and 0 <= y < self.Y and 0 <= z < self.Z:
            return int(self.blocks[x, y, z])
        return ID["corestone"] if z < 0 else 0

    def get_meta(self, x, y, z):
        return int(self.meta[x, y, z]) if self.inside(x, y, z) else 0

    def set(self, x, y, z, bid, meta=0, light=True, record=True):
        """A block put in (or air, to take one out): its chunk and any it touches drawn again, the light near it
        worked out again. Returns False outside the world."""
        if not self.inside(x, y, z):
            return False
        self.blocks[x, y, z] = bid
        self.meta[x, y, z] = meta
        if light:  # (a torch taken away darkens 14 blocks round it: all of that is worked out again)
            self.light_region(max(0, x - 14), max(0, y - 14), min(self.X, x + 15), min(self.Y, y + 15))
        self.mark(x, y, 15 if light else 1)
        if record:
            self.changes.append((x, y, z, bid, meta))
        return True

    def mark(self, x, y, reach=1):
        """The chunks within reach blocks of (x, y) need drawing again (light reaches 15 blocks)."""
        for cx in range(max(0, (x - reach) // CHUNK), min(self.X // CHUNK - 1, (x + reach) // CHUNK) + 1):
            for cy in range(max(0, (y - reach) // CHUNK), min(self.Y // CHUNK - 1, (y + reach) // CHUNK) + 1):
                self.dirty.add((cx, cy))

    def take_changes(self):
        out, self.changes = self.changes, []
        return out

    def apply_changes(self, changes):
        """Block changes from the server (or a save): light worked out once over the box they cover."""
        if not changes:
            return
        xs = [c[0] for c in changes]
        ys = [c[1] for c in changes]
        for x, y, z, bid, meta in changes:
            if self.inside(x, y, z):
                self.blocks[x, y, z] = bid
                self.meta[x, y, z] = meta
                self.mark(x, y, 15)
        self.light_region(max(0, min(xs) - 14), max(0, min(ys) - 14), min(self.X, max(xs) + 15), min(self.Y, max(ys) + 15))

    # ---------- sending and saving ----------
    def pack(self):
        """The whole world for a window joining: its size, seed and the blocks and meta zipped (a few hundred KB)."""
        return {"size": self.size_key, "seed": self.seed, "spawn": self.spawn, "version": WORLD_VERSION,
                "blocks": zlib.compress(self.blocks.tobytes(), 6), "meta": zlib.compress(self.meta.tobytes(), 6)}

    @classmethod
    def unpack(cls, data):
        w = cls(data["size"], data["seed"], blank=True)
        w.blocks[:] = np.frombuffer(zlib.decompress(data["blocks"]), np.uint8).reshape(w.blocks.shape)
        w.meta[:] = np.frombuffer(zlib.decompress(data["meta"]), np.uint8).reshape(w.meta.shape)
        w.spawn = tuple(data.get("spawn") or w.find_spawn())
        w.height = np.array([[w.top(x, y) for y in range(w.Y)] for x in range(w.X)])
        w.light_all()
        return w

    def save(self, folder, extra=None):
        """The world kept on disk: blocks.bin and meta.bin zipped, and world.json (its size, seed, spawn and the
        game's own things: chests, smelters, players' places)."""
        os.makedirs(folder, exist_ok=True)
        p = self.pack()
        for name in ("blocks", "meta"):
            tmp = os.path.join(folder, name + ".bin.tmp")
            with open(tmp, "wb") as f:
                f.write(p[name])
            os.replace(tmp, os.path.join(folder, name + ".bin"))
        info = {"size": self.size_key, "seed": self.seed, "spawn": list(self.spawn), "version": WORLD_VERSION,
                "extra": extra or {}}
        tmp = os.path.join(folder, "world.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(info, f)
        os.replace(tmp, os.path.join(folder, "world.json"))

    @classmethod
    def load(cls, folder):
        """A saved world, and its extra; None when there is none (or it is from another version)."""
        try:
            with open(os.path.join(folder, "world.json"), encoding="utf-8") as f:
                info = json.load(f)
            if info.get("version") != WORLD_VERSION:
                return None, {}
            data = dict(info)
            for name in ("blocks", "meta"):
                with open(os.path.join(folder, name + ".bin"), "rb") as f:
                    data[name] = f.read()
            return cls.unpack(data), info.get("extra") or {}
        except (OSError, ValueError, KeyError, zlib.error):
            return None, {}
