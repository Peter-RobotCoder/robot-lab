"""City Lab's jobs: deliveries from the DEPOT, taxi runs from the RANK, street RACES, the ROUND-UP from the ARCADE,
the CHIPS hidden about the city and the stunt ramps (CHANGE 194). Server side: World steps the things, then
Jobs.tick(world) does the bookkeeping, pays into each person's "cash" and sets their "job" and "jp" fields (the
kind of job running and how far it has got), which every window and page reads from the snapshot; the words (the
address, the time left, the race's places) go in the JSON "jobs" message (state()).

A job starts when a person (on foot or in a car) comes into the ring at a place's door with no job running. The
teacher's lesson says which jobs run (lesson["jobs"]: delivery, taxi, race, roundup) and the rules the pay.
"""
import math

import city_version  # noqa: F401
import kart_math as kmath
import city_map
import city_sim as sim

NONE, DELIVERY, TAXI, RACE, ROUNDUP = 0, 1, 2, 3, 4
KINDS = {DELIVERY: "delivery", TAXI: "taxi", RACE: "race", ROUNDUP: "roundup"}
NAMES = {DELIVERY: "Delivery", TAXI: "Taxi run", RACE: "Street race", ROUNDUP: "Robot round-up"}
MARKER_R = 3.5          # the ring at a place's door
ARRIVE_R = 4.5          # close enough to an address
ARRIVE_SPEED = 3.0      # ...and slow enough
CHIP_R = 1.3
CHIP_BACK = 60 * 180    # a chip found comes back after 3 minutes
LATE_PAY = 20
DELIVERY_SPEED = 6.0    # the clock allows distance / this + DELIVERY_SLACK (the roads go round the blocks)
DELIVERY_SLACK = 25.0
TAXI_TIP = 30
TIP_PER_BUMP = 6
RACE_FORMING = 60 * 12  # seconds after the first car arrives before GO
RACE_COUNTDOWN = 60 * 3
RACE_CHECK_R = 7.0
RACE_OPEN_SPEED = 4.0   # a race opens only for a car nearly stopped on the line (not one driving through the junction)
ROUNDUP_REST = 60 * 20  # after a round-up, this long before the arcade starts another
RACE_PLACES = (1.0, 0.6, 0.3)
ROUNDUP_TICKS = 60 * 120
STUNT_PAY_PER_M = 1
STEP = sim.STEP


def dist(a, b):
    return kmath.hypot(a[0] - b[0], a[1] - b[1])


class Jobs:
    def __init__(self, city, rules, enabled=None, seed=1):
        self.city, self.rules = city, rules
        self.enabled = dict(enabled or {"delivery": True, "taxi": True, "race": True, "roundup": True})
        self.mine = {}          # person id -> the job dict: kind, stage, target, name, deadline, pay, bumps, car, passenger
        self.chips_gone = {}    # chip index -> the tick it comes back
        self.race = None        # {"course": [(x, y)], "cars": {cid: checkpoint index}, "done": [cid...], "go": tick, "state"}
        self.roundup = None     # {"rogues": set(rid), "down": {rid: pid}, "ends": tick, "by": pid}
        self.events = []        # (tick, text), moved to the world's each tick
        self.changed = True     # the state() message wants sending
        self.rng = city_map.Rng(seed)
        self.courses = self.make_courses()
        self.course_n = 0
        self.taxi_stops = {}    # robot id -> (x, y) the passenger's stop
        self.done = []          # the jobs finished, oldest first (the teaching layer's evidence): see finished()

    # ---------- the places ----------
    def marker(self, kind):
        """The ring at a place's door: (x, y)."""
        d = self.city.places.get(kind)
        return (d[0], d[1]) if d else None

    def make_courses(self):
        """Three race courses through the streets: loops of junctions, from the car park's corner."""
        c = self.city
        courses = []
        for n in range(3):
            k0 = 1 + (n % max(1, c.cols - 1))
            m0 = 1
            w = max(1, min(c.cols - 1, 2 + n))
            h = max(1, min(c.rows - 1, 2 + (n + 1) % 2))
            k1, m1 = min(c.cols, k0 + w), min(c.rows, m0 + h)
            pts = [c.junction(k0, m0), c.junction(k1, m0), c.junction(k1, m1), c.junction(k0, m1)]
            if n == 2 and c.cols >= 4 and c.rows >= 3:
                pts = [c.junction(k0, m0), c.junction(k1, m0), c.junction(k1, m1 - 1), c.junction(k0 + 1, m1 - 1),
                       c.junction(k0 + 1, m1), c.junction(k0, m1)]
            courses.append([(round(x, 2), round(y, 2)) for x, y in pts])
        return courses

    def race_line(self):
        """Where a race starts: the first junction of the course."""
        return self.courses[self.course_n % len(self.courses)][0]

    def grid_slots(self, n):
        """n places on the grid behind the line, two abreast, facing along the course's first leg: (x, y, yaw)."""
        course = self.courses[self.course_n % len(self.courses)]
        (lx, ly), (nx, ny) = course[0], course[1]
        yaw = math.degrees(math.atan2(ny - ly, nx - lx))
        fx, fy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        out = []
        for k in range(n):
            row, side = k // 2, (1 if k % 2 else -1)
            out.append((lx - fx * (8.0 + row * 5.5) - fy * side * 1.8, ly - fy * (8.0 + row * 5.5) + fx * side * 1.8, yaw))
        return out

    # ---------- what World tells us ----------
    def left(self, pid):
        self.mine.pop(pid, None)
        if self.race and self.race["cars"]:
            pass
        self.changed = True

    def entered(self, world, pid, cid):
        j = self.mine.get(pid)
        if j and j["kind"] == TAXI and j["stage"] == 1 and j.get("passenger") in world.robots:
            pass  # the passenger needs the car stopped by them, see tick

    def bumped(self, world, pid):
        j = self.mine.get(pid)
        if j:
            j["bumps"] = j.get("bumps", 0) + 1

    def powered_down(self, world, pid, rid):
        if self.roundup and rid in self.roundup["rogues"] and rid not in self.roundup["down"]:
            self.roundup["down"][rid] = pid
            self.pay(world, pid, self.rules.get("roundup_pay", 15), f"powered down {world.designs[rid]['name']}")
            self.changed = True

    def stunt(self, world, pid, length):
        pay = int((length - sim.STUNT_LEAST) * STUNT_PAY_PER_M) + 5
        self.pay(world, pid, pay, f"a {length:.0f} m stunt jump")

    def pay(self, world, pid, amount, what):
        p = world.people.get(pid)
        if p is None:
            return
        p["cash"] = min(65535, p["cash"] + int(amount))
        self.events.append((world.tick, f"{world.name(pid)} earned {int(amount)} for {what}"))
        self.changed = True

    def finished(self, world, pid, kind, j, pay, place=None, late=False):
        """A job done, kept for the teaching layer: who, which, how long it took, what it paid, the place in a race,
        and whether a brain was driving."""
        unit = getattr(world, "units", {}).get(pid)
        self.done.append({"tick": world.tick, "pid": pid, "kind": KINDS[kind], "pay": int(pay), "place": place,
                          "late": late, "seconds": round((world.tick - j.get("started", world.tick)) * STEP, 2),
                          "brain": bool(unit is not None and getattr(unit, "brain", None) is not None)})
        del self.done[:-200]

    # ---------- the tick ----------
    def tick(self, world):
        self.chips(world)
        for pid, p in world.people.items():
            j = self.mine.get(pid)
            car = world.cars.get(p["link"] - 1) if p["link"] else None
            speed = abs(car["v"]) if car else p["v"]
            if j is None:
                self.offers(world, pid, p, car)
            elif j["kind"] == DELIVERY:
                self.delivery(world, pid, p, j, car, speed)
            elif j["kind"] == TAXI:
                self.taxi(world, pid, p, j, car, speed)
            elif j["kind"] == ROUNDUP:
                self.roundup_tick(world, pid, p, j)
            j = self.mine.get(pid)
            p["job"] = j["kind"] if j else 0
            p["jp"] = j.get("stage", 0) if j else 0
            if p["job"] == DELIVERY:
                p["flags"] |= sim.FLAG_PARCEL
            else:
                p["flags"] &= ~sim.FLAG_PARCEL
        self.race_tick(world)
        self.roundup_world(world)
        if self.events:
            world.events.extend(self.events)
            self.events = []

    def offers(self, world, pid, p, car):
        """A person with no job at a place's ring starts one."""
        at = (p["x"], p["y"])
        if self.enabled.get("delivery") and dist(at, self.marker("depot") or (1e9, 1e9)) < MARKER_R and p["lk"] == 0:
            self.start_delivery(world, pid, p)
        elif self.enabled.get("taxi") and car is not None and dist(at, self.marker("rank") or (1e9, 1e9)) < MARKER_R + 2:
            self.start_taxi(world, pid, p, car)
        elif self.enabled.get("roundup") and dist(at, self.marker("arcade") or (1e9, 1e9)) < MARKER_R and not car:
            if self.cash_chips(world, pid, p) == 0 and self.roundup is None and world.robots \
                    and world.tick >= getattr(self, "roundup_after", 0):
                self.start_roundup(world, pid)
        elif self.enabled.get("race") and car is not None and self.race is not None and self.race["state"] == "forming" \
                and dist(at, self.race_line()) < RACE_CHECK_R and (car["id"] not in self.race["cars"]):
            self.race["cars"][car["id"]] = 0
            self.mine[pid] = {"kind": RACE, "stage": 0, "car": car["id"]}
            self.events.append((world.tick, f"{world.name(pid)} is on the grid"))
            self.changed = True
        elif self.enabled.get("race") and car is not None and self.race is None and dist(at, self.race_line()) < RACE_CHECK_R \
                and abs(car["v"]) < RACE_OPEN_SPEED:
            self.race = {"course": self.courses[self.course_n % len(self.courses)], "cars": {car["id"]: 0}, "done": [],
                         "go": world.tick + RACE_FORMING, "state": "forming", "pay": {}}
            self.mine[pid] = {"kind": RACE, "stage": 0, "car": car["id"]}
            self.events.append((world.tick, f"{world.name(pid)} opened a street race: drive to the line to join"))
            self.changed = True

    def far_address(self, world, at, least=70.0):
        picks = [a for a in self.city.addresses if dist(at, a) > least]
        if not picks:
            picks = list(self.city.addresses)
        return self.rng.choice(picks)

    def start_delivery(self, world, pid, p):
        a = self.far_address(world, (p["x"], p["y"]))
        d = dist((p["x"], p["y"]), a)
        allowed = d / DELIVERY_SPEED + DELIVERY_SLACK
        self.mine[pid] = {"kind": DELIVERY, "stage": 1, "target": (a[0], a[1]), "name": a[3],
                          "deadline": world.tick + int(allowed / STEP), "pay": self.rules.get("delivery_pay", 50), "bumps": 0,
                          "started": world.tick}
        self.events.append((world.tick, f"{world.name(pid)}: a parcel for {a[3]}, {allowed:.0f} s"))
        self.changed = True

    def delivery(self, world, pid, p, j, car, speed):
        if dist((p["x"], p["y"]), j["target"]) < ARRIVE_R and speed < ARRIVE_SPEED:
            late = world.tick > j["deadline"]
            left = max(0, (j["deadline"] - world.tick) * STEP)
            pay = LATE_PAY if late else j["pay"] + int(left)
            self.pay(world, pid, pay, f"delivering to {j['name']}" + (" (late)" if late else ""))
            self.finished(world, pid, DELIVERY, j, pay, late=late)
            world.deliveries = getattr(world, "deliveries", {})
            world.deliveries[pid] = world.deliveries.get(pid, 0) + 1
            del self.mine[pid]
        elif world.tick > j["deadline"] + int(60 / STEP):  # a minute late: the parcel is taken back
            self.events.append((world.tick, f"{world.name(pid)}'s parcel was taken back: too late"))
            del self.mine[pid]
            self.changed = True

    def start_taxi(self, world, pid, p, car):
        free = [rid for rid, r in world.robots.items() if not r["link"] and r["hp"] > 0 and not (r["flags"] & sim.FLAG_ROGUE)
                and rid not in self.taxi_stops]
        if not free:
            return
        rid = free[self.rng.randint(0, len(free) - 1)]
        r = world.robots[rid]
        pickup = self.far_address(world, (p["x"], p["y"]), 50.0)
        r.update(x=pickup[0], y=pickup[1], yaw=pickup[2], v=0.0, u=0.0)
        r["flags"] |= sim.FLAG_CROSS * 0  # (a passenger is never cross)
        stop = self.far_address(world, (pickup[0], pickup[1]), 80.0)
        self.taxi_stops[rid] = (stop[0], stop[1])
        self.mine[pid] = {"kind": TAXI, "stage": 1, "target": (pickup[0], pickup[1]), "name": pickup[3], "passenger": rid,
                          "stop": (stop[0], stop[1]), "stop_name": stop[3], "pay": self.rules.get("taxi_fare", 40), "bumps": 0,
                          "car": car["id"], "started": world.tick}
        self.events.append((world.tick, f"{world.name(pid)}: pick up {world.designs[rid]['name']} at {pickup[3]}"))
        self.changed = True

    def taxi(self, world, pid, p, j, car, speed):
        rid = j["passenger"]
        r = world.robots.get(rid)
        if r is None or car is None or car["id"] != j.get("car"):
            if car is None and j["stage"] >= 1:
                pass  # out of the car: the job waits (the passenger does too) until they are back in a car
            if r is None:
                self.taxi_stops.pop(rid, None)
                del self.mine[pid]
                self.changed = True
            elif car is not None:
                j["car"] = car["id"]
            return
        if j["stage"] == 1:
            if dist((car["x"], car["y"]), j["target"]) < ARRIVE_R + 1 and speed < ARRIVE_SPEED:
                r["link"] = car["id"] + 1
                j["stage"], j["target"], j["name"] = 2, j["stop"], j["stop_name"]
                self.events.append((world.tick, f"{world.designs[rid]['name']} got in: to {j['stop_name']}"))
                self.changed = True
        elif j["stage"] == 2:
            fx, fy = sim.facing(car["yaw"])
            r.update(x=car["x"] - fx * 1.2, y=car["y"] - fy * 1.2, z=car["z"] + 0.3, yaw=car["yaw"], v=0.0, u=0.0)
            if dist((car["x"], car["y"]), j["target"]) < ARRIVE_R + 1 and speed < ARRIVE_SPEED:
                r["link"] = 0
                r.update(x=j["target"][0], y=j["target"][1], z=0.0)
                tip = max(0, TAXI_TIP - TIP_PER_BUMP * j.get("bumps", 0))
                self.pay(world, pid, j["pay"] + tip, f"the fare to {j['name']}" + (f" and a {tip} tip" if tip else ""))
                self.finished(world, pid, TAXI, j, j["pay"] + tip)
                world.taxi_runs = getattr(world, "taxi_runs", {})
                world.taxi_runs[pid] = world.taxi_runs.get(pid, 0) + 1
                self.taxi_stops.pop(rid, None)
                del self.mine[pid]

    def start_roundup(self, world, world_pid):
        rogues = {rid for rid, r in world.robots.items() if not r["link"] and rid not in self.taxi_stops}
        if not rogues:
            return
        for rid in rogues:
            world.robots[rid]["flags"] |= sim.FLAG_ROGUE
        self.roundup = {"rogues": rogues, "down": {}, "ends": world.tick + ROUNDUP_TICKS, "by": world_pid}
        for pid in world.people:
            if pid not in self.mine:
                self.mine[pid] = {"kind": ROUNDUP, "stage": len(rogues)}
        self.events.append((world.tick, f"ROUND-UP: {len(rogues)} robots have gone rogue. Power them down!"))
        self.changed = True

    def roundup_tick(self, world, pid, p, j):
        if self.roundup is None:
            del self.mine[pid]
            self.changed = True
            return
        j["stage"] = len(self.roundup["rogues"]) - len(self.roundup["down"])

    def roundup_world(self, world):
        if self.roundup is None:
            return
        ru = self.roundup
        over = world.tick >= ru["ends"] or len(ru["down"]) >= len(ru["rogues"])
        if over:
            for rid in ru["rogues"]:
                r = world.robots.get(rid)
                if r:
                    r["flags"] &= ~sim.FLAG_ROGUE
            best = {}
            for rid, pid in ru["down"].items():
                best[pid] = best.get(pid, 0) + 1
            words = ", ".join(f"{world.name(pid)} {n}" for pid, n in sorted(best.items(), key=lambda kv: -kv[1])) or "nobody scored"
            self.events.append((world.tick, f"Round-up over: {words}"))
            self.roundup_after = world.tick + ROUNDUP_REST
            for pid, j in list(self.mine.items()):
                if j["kind"] == ROUNDUP:
                    del self.mine[pid]
            self.roundup = None
            self.changed = True

    def chips(self, world):
        for idx, back in list(self.chips_gone.items()):
            if world.tick >= back:
                del self.chips_gone[idx]
                self.changed = True
        for pid, p in world.people.items():
            if p["link"] or p["move"] in (sim.MOVE_DOWN, sim.MOVE_GETUP):
                continue
            for idx, c in enumerate(self.city.chips):
                if idx in self.chips_gone:
                    continue
                if dist((p["x"], p["y"]), c) < CHIP_R:
                    self.chips_gone[idx] = world.tick + CHIP_BACK
                    held = (p["aux"] >> 8) + 1
                    p["aux"] = (min(255, held) << 8) | (p["aux"] & 255)
                    world.chips_found[pid] = world.chips_found.get(pid, 0) + 1
                    self.events.append((world.tick, f"{world.name(pid)} found a chip ({held} held: the ARCADE pays for them)"))
                    self.changed = True

    def cash_chips(self, world, pid, p):
        held = p["aux"] >> 8
        if held:
            self.pay(world, pid, held * self.rules.get("chip_pay", 10), f"{held} chips")
            p["aux"] &= 255
        return held

    def race_tick(self, world):
        r = self.race
        if r is None:
            return
        if r["state"] == "forming":
            if world.tick >= r["go"] - RACE_COUNTDOWN:
                r["state"] = "countdown"
                self.events.append((world.tick, "Street race: 3..."))
                self.changed = True
        elif r["state"] == "countdown":
            if world.tick >= r["go"]:
                r["state"] = "racing"
                r["ends"] = world.tick + 60 * 180
                self.events.append((world.tick, "GO!"))
                self.changed = True
        elif r["state"] == "racing":
            course = r["course"]
            for cid, cp in list(r["cars"].items()):
                car = world.cars.get(cid)
                if car is None or cid in r["done"]:
                    continue
                target = course[(cp + 1) % len(course)] if cp + 1 <= len(course) else course[0]
                if dist((car["x"], car["y"]), target) < RACE_CHECK_R:
                    r["cars"][cid] = cp + 1
                    pid = car["link"] - 1 if car["link"] else None
                    if pid in self.mine and self.mine[pid]["kind"] == RACE:
                        self.mine[pid]["stage"] = cp + 1
                    if cp + 1 >= len(course):  # round, and back to the line
                        r["done"].append(cid)
                        place = len(r["done"])
                        if pid is not None and pid in world.people:
                            share = RACE_PLACES[place - 1] if place <= len(RACE_PLACES) else 0.0
                            if share:
                                self.pay(world, pid, int(self.rules.get("race_pay", 100) * share), f"finishing {place}{'st' if place == 1 else 'nd' if place == 2 else 'rd' if place == 3 else 'th'} in the street race")
                            else:
                                self.events.append((world.tick, f"{world.name(pid)} finished the street race"))
                            j = dict(self.mine.get(pid) or {}, started=r.get("go", world.tick))
                            self.finished(world, pid, RACE, j, int(self.rules.get("race_pay", 100) * share), place=place)
                            world.races_won = getattr(world, "races_won", {})
                            if place == 1:
                                world.races_won[pid] = world.races_won.get(pid, 0) + 1
                            del self.mine[pid]
                        self.changed = True
            if len(r["done"]) >= len(r["cars"]) or world.tick >= r["ends"]:
                for pid, j in list(self.mine.items()):
                    if j["kind"] == RACE:
                        del self.mine[pid]
                self.race = None
                self.course_n += 1
                self.events.append((world.tick, "The street race is over"))
                self.changed = True

    # ---------- what everyone sees ----------
    def state(self, world):
        """The JSON "jobs" message's body: each person's job in words, the race, the round-up, the chips gone."""
        mine = {}
        for pid, j in self.mine.items():
            m = {"kind": KINDS[j["kind"]], "stage": j.get("stage", 0)}
            if "target" in j:
                m["target"] = [j["target"][0], j["target"][1]]
                m["name"] = j.get("name", "")
            if "deadline" in j:
                m["left"] = round(max(0.0, (j["deadline"] - world.tick) * STEP), 1)
            if j["kind"] == TAXI:
                m["passenger"] = j["passenger"]
            mine[pid] = m
        race = None
        if self.race:
            r = self.race
            race = {"state": r["state"], "course": [list(p) for p in r["course"]], "cars": {str(k): v for k, v in r["cars"].items()},
                    "done": r["done"], "go_in": round(max(0.0, (r["go"] - world.tick) * STEP), 2)}
        roundup = None
        if self.roundup:
            ru = self.roundup
            roundup = {"left": len(ru["rogues"]) - len(ru["down"]), "ends_in": round(max(0.0, (ru["ends"] - world.tick) * STEP), 1)}
        return {"mine": mine, "race": race, "roundup": roundup, "chips_gone": sorted(self.chips_gone),
                "line": list(self.race_line()), "markers": {k: list(v) for k in ("depot", "rank", "arcade") for v in [self.marker(k)] if v},
                "enabled": self.enabled}
