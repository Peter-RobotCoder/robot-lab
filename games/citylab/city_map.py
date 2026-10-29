"""The city as data: a grid of blocks between roads, the buildings on them, and what stands about.

City Lab's world is a small open city (CHANGE 194): streets on a grid with a ring road round the edge, blocks of
shops, offices and houses, a park, a car park with its stunt ramps, and the four places the jobs run from (the
delivery DEPOT, the GARAGE that mends cars, the taxi RANK and the ARCADE where the chips you find are counted).
Everything in it is a question the server, the windows, the brains and the computer drivers ask the same City
object: what is under this point (road, pavement, grass, a lot), what does a car or a person bump into here, where
is the kerb, which lane runs this way, where is the nearest address.

The city is generated from a few numbers (CITIES: how many blocks, how big, a seed) with the generator's own
random numbers (Rng, so the same on every computer), on the server only. It goes to every window and page as JSON
(to_data / from_data: the blocks, the buildings, the trees, the lamps, the ramps, the addresses...), so there is one
city and nobody has to port the generator. The grid itself (where the roads are) is a few sums, done again from the
same numbers at both ends.

Co-ordinates: metres, x east and y north, the city centred on (0, 0); yaw as Kart Lab's (degrees, 0 = +x,
anticlockwise). Cars drive on the left (the lane's centre LANE metres to the left of the road's middle, as you go).
"""
import math

import city_version  # noqa: F401  (puts the engine and the other games' folders on the path)
import kart_math as kmath  # (hypot and atan2 the same on every computer)

ROAD = 12.0        # a road, kerb to kerb: two lanes and a parking strip each side
PAVE = 2.5         # the pavement, inside the block's kerb line
LANE = 1.75        # a lane's centre from the road's middle (to the left as you go: the UK)
PARK_LANE = 4.75   # a kerbside parking bay's centre from the road's middle
KERB_H = 0.12      # the kerb's height (the picture, and the bump a car feels)
VERGE = 6.0        # beyond the ring road: grass (or the quay) to the city's edge
INSET = 0.5        # buildings stand this far behind the pavement
RAMP_LEN, RAMP_H = 7.0, 1.4   # a stunt ramp: its run and its lip

CITIES = {
    "harbour": {"name": "Harbour City", "cols": 6, "rows": 5, "block": 40.0, "seed": 7, "water": "south"},
    "village": {"name": "Little Lab", "cols": 3, "rows": 3, "block": 36.0, "seed": 3, "water": None},
    "metro": {"name": "Metro Lab", "cols": 8, "rows": 6, "block": 44.0, "seed": 11, "water": "east"},
}
DEFAULT_CITY = "harbour"

# the jobs' places, one block each (the kind of the block and the building on it)
PLACES = ("depot", "garage", "rank", "arcade")
BLOCK_KINDS = PLACES + ("park", "carpark", "shops", "offices", "houses")

STREETS = ["Ada Street", "Turing Street", "Lovelace Street", "Hopper Street", "Babbage Street", "Berners-Lee Street",
           "Hamilton Street", "Clarke Street", "Wilkes Street", "Shannon Street"]
ROADS = ["Harbour Road", "Station Road", "Mill Road", "Park Road", "Market Road", "Canal Road", "Forge Road",
         "Quay Road", "Bridge Road", "Orchard Road"]

# the building kinds the picture knows: colour families, roofs and window patterns are chosen here
PALETTES = {
    "shop": [(214, 120, 90), (236, 200, 150), (150, 170, 190), (210, 180, 120), (180, 140, 160)],
    "office": [(140, 160, 180), (110, 120, 135), (170, 185, 200), (90, 110, 140), (200, 205, 210)],
    "house": [(200, 150, 110), (225, 210, 180), (170, 120, 90), (190, 190, 170), (230, 220, 200)],
    "depot": [(120, 130, 140)], "garage": [(90, 90, 100)], "rank": [(190, 170, 130)], "arcade": [(120, 60, 160)],
}


class Rng:
    """The generator's own random numbers (a 64-bit LCG): the same city from the same seed on every computer."""

    def __init__(self, seed):
        self.state = (seed * 2654435761 + 12345) & 0xFFFFFFFFFFFFFFFF

    def next(self):
        self.state = (self.state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        return (self.state >> 33) / 2147483648.0  # (0 to 1)

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self.next()

    def randint(self, lo, hi):
        return lo + int(self.next() * (hi - lo + 1)) if hi > lo else lo

    def choice(self, seq):
        return seq[int(self.next() * len(seq)) % len(seq)]

    def shuffle(self, seq):
        for i in range(len(seq) - 1, 0, -1):
            j = int(self.next() * (i + 1)) % (i + 1)
            seq[i], seq[j] = seq[j], seq[i]
        return seq


class City:
    """The city built from its data (from_data) or generated (generate)."""

    def __init__(self, data):
        self.key, self.name = data["key"], data["name"]
        self.cols, self.rows, self.block = int(data["cols"]), int(data["rows"]), float(data["block"])
        self.water = data.get("water")
        self.pitch = self.block + ROAD
        self.width, self.height = self.cols * self.pitch + ROAD, self.rows * self.pitch + ROAD
        self.xmin, self.ymin = -self.width / 2, -self.height / 2
        self.xmax, self.ymax = self.width / 2, self.height / 2
        self.edge = (self.xmin - VERGE, self.ymin - VERGE, self.xmax + VERGE, self.ymax + VERGE)  # the barrier
        self.blocks = data["blocks"]          # [{i, j, kind, x0, y0, x1, y1}] (the kerb rectangle)
        self.buildings = data["buildings"]    # [{x0, y0, x1, y1, h, kind, c, roof, b}]
        self.trees = data["trees"]            # [[x, y, r, h]]
        self.lamps = data["lamps"]            # [[x, y]]
        self.ramps = data["ramps"]            # [{x, y, yaw}]: the lip is RAMP_LEN / 2 ahead of (x, y)
        self.places = data["places"]          # kind -> [x, y, yaw]: the door of the depot, garage, rank, arcade
        self.zones = data["zones"]            # kind -> [x0, y0, x1, y1]: the yard that counts as being there
        self.addresses = data["addresses"]    # [[x, y, yaw, name]]: kerbside, where deliveries and taxi stops are
        self.spawns = data["spawns"]          # [[x, y, yaw]]: where players start, by the depot
        self.parking = data["parking"]        # [[x, y, yaw]]: where parked cars sit
        self.chips = data["chips"]            # [[x, y]]: the chips to find
        self.street_names, self.road_names = data["streets"], data["roads"]
        # the buildings, lamps and trees by block, for the collision test
        self._by_block = {}
        for n, b in enumerate(self.buildings):
            self._by_block.setdefault(b["b"], ([], []))[0].append(n)
        for n, (x, y, *_rest) in enumerate(self.trees):
            bi = self.block_index(x, y)
            if bi is not None:
                self._by_block.setdefault(bi, ([], []))[1].append(("t", n))
        for n, (x, y) in enumerate(self.lamps):
            bi = self.block_index(x, y)
            if bi is not None:
                self._by_block.setdefault(bi, ([], []))[1].append(("l", n))

    # ---------- the grid ----------
    def road_x(self, k):
        """The middle of vertical road k (0 to cols)."""
        return self.xmin + ROAD / 2 + k * self.pitch

    def road_y(self, m):
        """The middle of horizontal road m (0 to rows)."""
        return self.ymin + ROAD / 2 + m * self.pitch

    def block_rect(self, i, j):
        x0 = self.xmin + ROAD + i * self.pitch
        y0 = self.ymin + ROAD + j * self.pitch
        return x0, y0, x0 + self.block, y0 + self.block

    def block_index(self, x, y):
        """The index in self.blocks of the block (x, y) is on (its kerb rectangle), or None (on a road, or outside)."""
        fx = (x - self.xmin - ROAD) / self.pitch
        fy = (y - self.ymin - ROAD) / self.pitch
        i, j = math.floor(fx), math.floor(fy)
        if not (0 <= i < self.cols and 0 <= j < self.rows):
            return None
        if (fx - i) * self.pitch > self.block or (fy - j) * self.pitch > self.block:
            return None
        return j * self.cols + i

    def surface(self, x, y):
        """What is under (x, y): "road"; "pave" (a pavement); "grass" (a park, or the verge outside the ring road);
        "lot" (a car park, a yard, a forecourt); "court" (a courtyard); "quay" (by the water); "out" (past the edge)."""
        if x < self.edge[0] or x > self.edge[2] or y < self.edge[1] or y > self.edge[3]:
            return "out"
        if x < self.xmin or x > self.xmax or y < self.ymin or y > self.ymax:
            if self.water and self._water_side(x, y):
                return "quay"
            return "grass"
        bi = self.block_index(x, y)
        if bi is None:
            return "road"
        b = self.blocks[bi]
        if x < b["x0"] + PAVE or x > b["x1"] - PAVE or y < b["y0"] + PAVE or y > b["y1"] - PAVE:
            return "pave"
        kind = b["kind"]
        if kind == "park":
            return "grass"
        if kind in ("carpark", "depot", "garage", "rank", "arcade"):
            return "lot"
        return "court"

    def _water_side(self, x, y):
        return ((self.water == "south" and y < self.ymin) or (self.water == "north" and y > self.ymax)
                or (self.water == "east" and x > self.xmax) or (self.water == "west" and x < self.xmin))

    def locate_road(self, x, y):
        """Where (x, y) is on the roads: ("v", k, lateral) on vertical road k (lateral: metres east of its middle),
        ("h", m, lateral) on horizontal road m (metres north), ("x", k, m) in a junction, or None off the roads."""
        fx = (x - self.xmin) / self.pitch
        fy = (y - self.ymin) / self.pitch
        k, m = math.floor(fx + 1e-9), math.floor(fy + 1e-9)
        on_v = (fx - k) * self.pitch <= ROAD and 0 <= k <= self.cols
        on_h = (fy - m) * self.pitch <= ROAD and 0 <= m <= self.rows
        if on_v and on_h:
            return ("x", k, m)
        if on_v:
            return ("v", k, x - self.road_x(k))
        if on_h:
            return ("h", m, y - self.road_y(m))
        return None

    def lane(self, kind, n, direction):
        """The centre line of the lane going direction (+1 or -1) along road kind/n: for a vertical road the x of the
        lane (going north, +1, the left is west: minus), for a horizontal road its y."""
        if kind == "v":
            return self.road_x(n) - LANE * direction
        return self.road_y(n) + LANE * direction

    def junction(self, k, m):
        return self.road_x(k), self.road_y(m)

    # ---------- what is in the way ----------
    def collide(self, x, y, r):
        """(x, y) pushed out of anything a thing of radius r can't be in: the buildings (boxes), the lamps and trees
        (posts), the city's edge. Returns (x, y, hit) with hit None or the kind of thing hit ("building", "post",
        "edge"), the first found (a corner of two is pushed out of both over two ticks)."""
        hit = None
        e = self.edge
        if x < e[0] + r:
            x, hit = e[0] + r, "edge"
        elif x > e[2] - r:
            x, hit = e[2] - r, "edge"
        if y < e[1] + r:
            y, hit = e[1] + r, "edge"
        elif y > e[3] - r:
            y, hit = e[3] - r, "edge"
        bi = self.block_index(x, y)
        if bi is None:
            return x, y, hit
        buildings, posts = self._by_block.get(bi, ((), ()))
        for n in buildings:
            b = self.buildings[n]
            if b["x0"] - r < x < b["x1"] + r and b["y0"] - r < y < b["y1"] + r:
                # out along the shallowest side
                left, right = x - (b["x0"] - r), (b["x1"] + r) - x
                down, up = y - (b["y0"] - r), (b["y1"] + r) - y
                least = min(left, right, down, up)
                if least == left:
                    x = b["x0"] - r
                elif least == right:
                    x = b["x1"] + r
                elif least == down:
                    y = b["y0"] - r
                else:
                    y = b["y1"] + r
                hit = "building"
        for kind, n in posts:
            px, py, pr = (self.trees[n][0], self.trees[n][1], self.trees[n][2]) if kind == "t" else (self.lamps[n][0], self.lamps[n][1], 0.2)
            dx, dy = x - px, y - py
            reach = pr + r
            if dx * dx + dy * dy >= reach * reach:  # (the cheap test first: hypot the same on every computer is slow)
                continue
            d = kmath.hypot(dx, dy)
            if d < reach:
                if d < 1e-6:
                    dx, dy, d = 1.0, 0.0, 1.0
                x, y = px + dx / d * reach, py + dy / d * reach
                hit = "post"
        return x, y, hit

    def kerb_between(self, x0, y0, x1, y1):
        """Did a move from (x0, y0) to (x1, y1) cross a kerb (the road's edge)? The bump a car feels."""
        return (self.block_index(x0, y0) is None) != (self.block_index(x1, y1) is None)

    def ramp_height(self, x, y):
        """The height of the ramp under (x, y), or 0: a wedge RAMP_LEN long rising to RAMP_H at its lip, 4 m wide."""
        for rp in self.ramps:
            yr = math.radians(rp["yaw"])
            c, s = kmath.cos(yr), kmath.sin(yr)
            dx, dy = x - rp["x"], y - rp["y"]
            along = dx * c + dy * s
            across = -dx * s + dy * c
            if -RAMP_LEN / 2 <= along <= RAMP_LEN / 2 and abs(across) <= 2.0:
                return RAMP_H * (along + RAMP_LEN / 2) / RAMP_LEN
        return 0.0

    def in_zone(self, kind, x, y):
        z = self.zones.get(kind)
        return bool(z) and z[0] <= x <= z[2] and z[1] <= y <= z[3]

    def nearest_address(self, x, y):
        best, bd = None, math.inf
        for n, a in enumerate(self.addresses):
            d = math.hypot(a[0] - x, a[1] - y)
            if d < bd:
                best, bd = n, d
        return best, bd

    def bounds(self):
        return self.edge

    def to_data(self):
        return {"key": self.key, "name": self.name, "cols": self.cols, "rows": self.rows, "block": self.block,
                "water": self.water, "blocks": self.blocks, "buildings": self.buildings, "trees": self.trees,
                "lamps": self.lamps, "ramps": self.ramps, "places": self.places, "zones": self.zones,
                "addresses": self.addresses, "spawns": self.spawns, "parking": self.parking, "chips": self.chips,
                "streets": self.street_names, "roads": self.road_names}

    @classmethod
    def from_data(cls, data):
        return cls(data)


# ---------- the generator ----------
def _r(v):
    return round(v, 2)


def generate(key=DEFAULT_CITY):
    spec = CITIES[key]
    cols, rows, block, seed = spec["cols"], spec["rows"], float(spec["block"]), spec["seed"]
    rng = Rng(seed * 1000003 + cols * 101 + rows)
    base = City({"key": key, "name": spec["name"], "cols": cols, "rows": rows, "block": block, "water": spec.get("water"),
                 "blocks": [], "buildings": [], "trees": [], "lamps": [], "ramps": [], "places": {}, "zones": {},
                 "addresses": [], "spawns": [], "parking": [], "chips": [], "streets": [], "roads": []})
    n = cols * rows
    # the kinds: the four places, a park (two in a big city), a car park, then shops, offices and houses in turn
    kinds = list(PLACES) + ["park", "carpark"] + (["park"] if n >= 24 else [])
    fill = ["shops", "offices", "houses"]
    while len(kinds) < n:
        kinds.append(fill[len(kinds) % 3])
    kinds = kinds[:n]
    rng.shuffle(kinds)
    # the depot by the middle of the city (everyone starts there), the water's blocks never a park or offices
    mid = (rows // 2) * cols + cols // 2
    di = kinds.index("depot")
    kinds[di], kinds[mid] = kinds[mid], kinds[di]
    blocks, buildings, trees, lamps, ramps = [], [], [], [], []
    places, zones, addresses, spawns, parking, chips = {}, {}, [], [], [], []
    streets = [STREETS[k % len(STREETS)] for k in range(cols + 1)]
    roads = [ROADS[m % len(ROADS)] for m in range(rows + 1)]
    for j in range(rows):
        for i in range(cols):
            bi = j * cols + i
            kind = kinds[bi]
            x0, y0, x1, y1 = base.block_rect(i, j)
            blocks.append({"i": i, "j": j, "kind": kind, "x0": _r(x0), "y0": _r(y0), "x1": _r(x1), "y1": _r(y1)})
            # lamps at the corners, a metre in on the pavement
            for lx, ly in ((x0 + 1.0, y0 + 1.0), (x1 - 1.0, y0 + 1.0), (x0 + 1.0, y1 - 1.0), (x1 - 1.0, y1 - 1.0)):
                lamps.append([_r(lx), _r(ly)])
            # an address at the middle of each side, on the pavement facing the road
            number = 2 * (j * cols + i) + 1
            addresses.append([_r((x0 + x1) / 2), _r(y0 + 1.2), -90.0, f"{number} {roads[j]}"])
            addresses.append([_r((x0 + x1) / 2), _r(y1 - 1.2), 90.0, f"{number + 1} {roads[j + 1]}"])
            addresses.append([_r(x0 + 1.2), _r((y0 + y1) / 2), 180.0, f"{number} {streets[i]}"])
            addresses.append([_r(x1 - 1.2), _r((y0 + y1) / 2), 0.0, f"{number + 1} {streets[i + 1]}"])
            # kerbside parking: two bays along the south side and the west side of each block, in the road
            for t in (0.3, 0.6):
                parking.append([_r(x0 + (x1 - x0) * t), _r(y0 - ROAD / 2 + PARK_LANE), 0.0])
            for t in (0.35, 0.65):
                parking.append([_r(x0 - ROAD / 2 + PARK_LANE), _r(y0 + (y1 - y0) * t), 90.0])
            inner = (x0 + PAVE + INSET, y0 + PAVE + INSET, x1 - PAVE - INSET, y1 - PAVE - INSET)
            if kind in PLACES:
                _place_block(kind, bi, inner, rng, buildings, places, zones, spawns, parking, lamps)
            elif kind == "park":
                _park_block(inner, rng, trees)
            elif kind == "carpark":
                _carpark_block(inner, rng, parking, ramps, buildings, bi)
            elif kind == "offices":
                _office_block(bi, inner, rng, buildings)
            elif kind == "houses":
                _house_block(bi, inner, rng, buildings, trees)
            else:
                _shop_block(bi, inner, rng, buildings)
            # a chip on each block: on the pavement at a seeded spot along the north side
            t = rng.uniform(0.15, 0.85)
            chips.append([_r(x0 + (x1 - x0) * t), _r(y1 - 1.0)])
    data = base.to_data()
    data.update(blocks=blocks, buildings=buildings, trees=trees, lamps=lamps, ramps=ramps, places=places, zones=zones,
                addresses=addresses, spawns=spawns, parking=parking, chips=chips, streets=streets, roads=roads)
    return City(data)


def _box(bi, x0, y0, x1, y1, h, kind, colour, roof="flat"):
    return {"x0": _r(x0), "y0": _r(y0), "x1": _r(x1), "y1": _r(y1), "h": _r(h), "kind": kind,
            "c": list(colour), "roof": roof, "b": bi}


def _plots(a, b, rng, least, most):
    """Cut [a, b] into plots between least and most long: the cut points."""
    out, p = [a], a
    while b - p > most:
        step = rng.uniform(least, most)
        if b - (p + step) < least:
            break
        p += step
        out.append(p)
    out.append(b)
    return out


def _shop_block(bi, inner, rng, buildings):
    x0, y0, x1, y1 = inner
    depth = rng.uniform(10.0, 13.0)
    # a row of shops along the south and the north, flats above (6 to 10 m), the courtyard between
    for ya, yb in ((y0, y0 + depth), (y1 - depth, y1)):
        cuts = _plots(x0, x1, rng, 7.0, 12.0)
        for a, b in zip(cuts, cuts[1:]):
            h = rng.choice((6.0, 7.5, 9.0, 10.0))
            buildings.append(_box(bi, a, ya, b - 0.3, yb, h, "shop", rng.choice(PALETTES["shop"])))
    # a shorter building on the west side between them
    if y1 - y0 - 2 * depth > 8.0:
        buildings.append(_box(bi, x0, y0 + depth + 0.5, x0 + depth * 0.8, y1 - depth - 0.5, rng.choice((5.0, 6.5)),
                              "shop", rng.choice(PALETTES["shop"])))


def _office_block(bi, inner, rng, buildings):
    x0, y0, x1, y1 = inner
    w, d = x1 - x0, y1 - y0
    # one tower with a podium, or two towers
    if rng.next() < 0.5:
        buildings.append(_box(bi, x0, y0, x1, y0 + d * 0.55, rng.uniform(8.0, 12.0), "office", rng.choice(PALETTES["office"])))
        tw = w * rng.uniform(0.35, 0.5)
        tx = x0 + rng.uniform(0.0, w - tw)
        buildings.append(_box(bi, tx, y0 + 2.0, tx + tw, y0 + d * 0.5, rng.uniform(22.0, 40.0), "office", rng.choice(PALETTES["office"])))
        buildings.append(_box(bi, x0 + w * 0.15, y1 - d * 0.3, x1 - w * 0.15, y1, rng.uniform(9.0, 16.0), "office", rng.choice(PALETTES["office"])))
    else:
        for sx in (x0, x0 + w * 0.55):
            buildings.append(_box(bi, sx, y0, sx + w * 0.42, y1 - d * 0.35, rng.uniform(15.0, 32.0), "office", rng.choice(PALETTES["office"])))
        buildings.append(_box(bi, x0, y1 - d * 0.28, x1, y1, rng.uniform(6.0, 9.0), "office", rng.choice(PALETTES["office"])))


def _house_block(bi, inner, rng, buildings, trees):
    x0, y0, x1, y1 = inner
    # terraces along the south and north, gaps between houses, a tree in some gardens
    depth = 8.0
    for ya, yb, back in ((y0, y0 + depth, 1), (y1 - depth, y1, -1)):
        cuts = _plots(x0, x1, rng, 6.5, 9.0)
        for a, b in zip(cuts, cuts[1:]):
            gap = rng.uniform(0.6, 1.8)
            buildings.append(_box(bi, a, ya, b - gap, yb, rng.choice((7.0, 7.5, 8.5)), "house", rng.choice(PALETTES["house"]),
                                  roof="pitched"))
            if rng.next() < 0.5:
                trees.append([_r((a + b) / 2), _r(yb + back * 3.0), 0.45, _r(rng.uniform(4.0, 6.0))])
    for sx in (x0, x1 - 7.0):  # a pair of houses on each side between the terraces
        if y1 - y0 - 2 * depth > 10.0:
            buildings.append(_box(bi, sx, y0 + depth + 2.5, sx + 7.0, y1 - depth - 2.5, 7.5, "house", rng.choice(PALETTES["house"]),
                                  roof="pitched"))


def _park_block(inner, rng, trees):
    x0, y0, x1, y1 = inner
    count = int((x1 - x0) * (y1 - y0) / 110.0)
    for _ in range(count):
        trees.append([_r(rng.uniform(x0 + 1.5, x1 - 1.5)), _r(rng.uniform(y0 + 1.5, y1 - 1.5)), 0.5, _r(rng.uniform(5.0, 9.0))])


def _carpark_block(inner, rng, parking, ramps, buildings, bi):
    x0, y0, x1, y1 = inner
    # rows of bays across the middle, two ramps facing each other at the ends (a jump from one to the other)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    for row_y in (cy - 6.0, cy + 6.0):
        x = x0 + 4.0
        while x < x1 - 3.0:
            parking.append([_r(x), _r(row_y), 90.0])
            x += 3.2
    ramps.append({"x": _r(x0 + 6.0), "y": _r(cy), "yaw": 0.0})
    ramps.append({"x": _r(x1 - 6.0), "y": _r(cy), "yaw": 180.0})
    buildings.append(_box(bi, x0, y1 - 3.0, x0 + 4.0, y1, 3.0, "shop", (200, 200, 90)))  # the pay booth


def _place_block(kind, bi, inner, rng, buildings, places, zones, spawns, parking, lamps):
    x0, y0, x1, y1 = inner
    w = x1 - x0
    colour = PALETTES[kind][0]
    if kind == "depot":
        # the warehouse on the north half, its yard on the south: everyone starts in the yard
        buildings.append(_box(bi, x0, y0 + (y1 - y0) * 0.5, x1, y1, 9.0, "depot", colour))
        door = [_r((x0 + x1) / 2), _r(y0 + (y1 - y0) * 0.5 - 2.0), 90.0]
        zones[kind] = [_r(x0), _r(y0), _r(x1), _r(y0 + (y1 - y0) * 0.5)]
        for n in range(8):
            spawns.append([_r(x0 + 3.0 + n * (w - 6.0) / 7), _r(y0 + 3.0), -90.0])  # (facing the street)
        for n in range(4):
            parking.append([_r(x0 + 4.0 + n * 4.0), _r(y0 + (y1 - y0) * 0.5 - 6.0), 90.0])
    elif kind == "garage":
        buildings.append(_box(bi, x0, y1 - (y1 - y0) * 0.45, x1, y1, 6.0, "garage", colour))
        door = [_r((x0 + x1) / 2), _r(y1 - (y1 - y0) * 0.45 - 2.0), 90.0]
        zones[kind] = [_r(x0), _r(y0), _r(x1), _r(y1 - (y1 - y0) * 0.45)]  # the forecourt mends a car
        for n in range(3):
            parking.append([_r(x0 + 5.0 + n * 5.0), _r(y0 + 5.0), 90.0])
    elif kind == "rank":
        buildings.append(_box(bi, x0 + 2.0, y1 - (y1 - y0) * 0.5, x1 - 2.0, y1, 8.0, "rank", colour))
        door = [_r((x0 + x1) / 2), _r(y1 - (y1 - y0) * 0.5 - 2.0), 90.0]
        zones[kind] = [_r(x0), _r(y0), _r(x1), _r(y1 - (y1 - y0) * 0.5)]
        for n in range(4):
            parking.append([_r(x0 + 4.0 + n * 4.5), _r(y0 + 4.0), 90.0])
    else:  # the arcade: a bright box with a plaza in front
        buildings.append(_box(bi, x0 + 3.0, y0 + (y1 - y0) * 0.45, x1 - 3.0, y1 - 1.0, 11.0, "arcade", colour))
        door = [_r((x0 + x1) / 2), _r(y0 + (y1 - y0) * 0.45 - 2.0), 90.0]
        zones[kind] = [_r(x0), _r(y0), _r(x1), _r(y0 + (y1 - y0) * 0.45)]
    places[kind] = door


def load(key=DEFAULT_CITY):
    return generate(key)


if __name__ == "__main__":
    import json
    import sys
    c = generate(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CITY)
    d = c.to_data()
    print(c.name, f"{c.width:.0f} x {c.height:.0f} m,", len(c.blocks), "blocks,", len(c.buildings), "buildings,",
          len(c.trees), "trees,", len(c.lamps), "lamps,", len(c.parking), "parking bays,", len(c.chips), "chips,",
          len(json.dumps(d)), "bytes of JSON")
    for k, v in c.places.items():
        print(f"  {k}: door at {v}")
