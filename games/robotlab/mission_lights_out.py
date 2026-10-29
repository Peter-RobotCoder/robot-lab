"""Robot Lab Mission 2, Lights Out: the mission itself, with no drawing (as mission_wake_up.py is Mission 1's).
The second Story Mission (knowledge: clubcoders-pedagogy-engine.md): if / else with the robot's sensors, and variables.

Night has fallen over Brookfield. A storm has brought rocks down on the hill road up to the radio mast and put some
of the road's lamps out. Every night the rocks come down in different places and different lamps go dark, so a
fixed route fails: the program has to look (if path blocked ... else ...) and keep count (a variable).
  1 Rockfalls   if the path is blocked, use the spinner, else move forward
  2 Lamps       repair every dark lamp beside the road (a lamp post stands north of the road)
  3 Mast        reach the radio mast at the end of the road
  4 Report      face the mast and report how many lamps you repaired tonight: a variable's value
  5 Nights      the same program brings the lights back on three nights running
RUN plays the program on night 1, then night 2, then night 3, each from the start of the road with a full battery
(not, as in Mission 1, from where the robot stopped). A night that goes wrong (a bump, a wrong report, a flat
battery, a mistake) stops the run there; change the program and run again. Deterministic: the three nights are
fixed (NIGHTS), so a program always gives the same events.

Energy: the robot starts each night with 30. A square costs 1, using the spinner 2, a repair 3 (even of a lamp that
was working: it is opened up and checked). Turning, the sensors and the variables are free. The Solar Panel from
Mission 1 (mission_wake_up.UNLOCK, kept in missions_progress.json) gives back 1 energy for every 5 squares driven.
Stars: one for finishing, one for 5 or more energy left at the end of every night, one for 15 or fewer lines of code.
The robot holds the front spinner from Mission 1 all mission; there is nothing to pick up.

MISSION_VERSION numbers the rules: replay_mission.py --mission lights_out replays recorded programs and requires
the same events (as kart_sim.SIM_VERSION and kart/replay_test.py). A change MEANT to change the rules raises it and
records again in the same commit.
"""
import json
import os

import mission_wake_up as M1

MISSION_VERSION = 1
MISSION_ID = "lights_out"
ROBOTS, TOOLS, DIR_NAMES, DX, DY = M1.ROBOTS, M1.TOOLS, M1.DIR_NAMES, M1.DX, M1.DY
# # hill   . road   S start   L a lamp post (beside the road)   M the radio mast   F fence   ~ field
# V village paving   H house (Brookfield, lit since Mission 1)
MAP = [
    "################",
    "################",
    "##HH############",
    "#HVHL#L#L#L#L###",
    "#VVS..........M#",
    "#HVHFFFFFFFFFF##",
    "##HH~~~~~~~~~~##",
    "################",
]
W, H = len(MAP[0]), len(MAP)
ROAD_Y = 4
# Each night: where the rocks have come down (x along the road) and which lamps are dark (the x of the road square
# each stands beside). Three rocks a night, so a program needs the road's 10 squares and 3 clearings: 13 steps.
NIGHTS = [
    {"rocks": [5, 9, 12], "dark": [4, 8, 12]},
    {"rocks": [4, 6, 10], "dark": [6, 10]},
    {"rocks": [8, 9, 13], "dark": [4, 6, 12]},
]
RULES = {
    "energyStart": 30, "energyMax": 30, "solarEvery": 5,
    "cost": {"move": 1, "turn": 0, "use": 2, "repair": 3},
    "stars": {"energy": 5, "lines": 15},  # a star for finishing, one for this much left every night, one for this few lines
    "maxActions": 2000,  # (each night: every line done, an if's question and a variable's change too)
    "maxValue": 9999,
}
OBJECTIVES = [
    {"id": "rockfalls", "title": "Rockfalls", "text": "If the path is blocked, use the spinner; else move forward."},
    {"id": "lamps", "title": "Lamps", "text": "Repair every dark lamp beside the road."},
    {"id": "mast", "title": "Mast", "text": "Reach the radio mast at the end of the road."},
    {"id": "report", "title": "Report", "text": "Face the mast and report how many lamps you repaired."},
    {"id": "nights", "title": "Three nights", "text": "The same program works on all three nights."},
]
UNLOCK = None  # (Mission 2 gives no part: Mission 3 is not built)
SOLAR = M1.UNLOCK  # the part this mission uses, if Mission 1 unlocked it
STARTER = ["# Lights Out. Your program runs on three nights: the rocks and the dark lamps change each night.",
           "# Use if, else and a variable. The phrasebook below lists what the robot understands.", "", ""]
BLOCKS = {
    "#": "Bump! A rocky hillside is in the way.",
    "R": "Bump! A rockfall blocks the road. If the path is blocked, use the spinner.",
    "L": "Bump! That's a lamp post.",
    "F": "Bump! That's the fence.",
    "M": "Bump! That's the radio mast.",
    "H": "Bump! That's a house.",
}


def find(ch):
    for y in range(H):
        x = MAP[y].find(ch)
        if x >= 0:
            return {"x": x, "y": y}
    return None


START = dict(find("S"), dir=1)  # (facing east, up the road)
MAST = find("M")
LAMPS = [x for x, t in enumerate(MAP[ROAD_Y - 1]) if t == "L"]


def tile_at(s, x, y):
    if x < 0 or y < 0 or x >= W or y >= H:
        return "#"
    if y == ROAD_Y and x in s["rocks"]:
        return "R"
    t = MAP[y][x]
    return "." if t == "S" else t


def walkable(t):
    return t in (".", "V")


class Stop(Exception):
    """This night ends here: a bump, a mistake or a flat battery (the run stops), or the report made (on to the next
    night)."""

    def __init__(self, ok=False):
        super().__init__()
        self.ok = ok


class Mission:
    def __init__(self, robot_name, solar=False):
        if robot_name not in ROBOTS:
            raise ValueError("No robot called " + str(robot_name))
        self.robot = ROBOTS[robot_name]
        self.s = {
            "x": START["x"], "y": START["y"], "dir": START["dir"], "energy": RULES["energyStart"], "tool": "spinner",
            "solar": bool(solar), "night": 1, "rocks": list(NIGHTS[0]["rocks"]), "dark": list(NIGHTS[0]["dark"]),
            "driven": 0, "repaired": 0, "atMast": False, "reported": False, "vars": {},
            "nightsDone": 0, "nightEnergy": [], "linesUsed": 0, "runs": 0, "failed": False, "complete": False,
        }

    def snapshot(self):
        s = dict(self.s)
        for k in ("rocks", "dark", "nightEnergy"):
            s[k] = list(s[k])
        s["vars"] = dict(s["vars"])
        return s

    def objectives(self, s=None):
        s = s or self.s
        night = not s["complete"]
        done = [not night or not s["rocks"], not night or not s["dark"], not night or s["atMast"],
                not night or s["reported"], s["complete"]]
        now = done.index(False) if False in done else -1
        return [dict({"done": done[i], "now": i == now}, **o) for i, o in enumerate(OBJECTIVES)]

    def stars(self, s=None):
        s = s or self.s
        energy = bool(s["nightEnergy"]) and min(s["nightEnergy"]) >= RULES["stars"]["energy"]
        lines = s["linesUsed"] <= RULES["stars"]["lines"]
        return {"complete": s["complete"], "energy": energy, "lines": lines,
                "count": 1 + (1 if energy else 0) + (1 if lines else 0) if s["complete"] else 0}

    def start_night(self, n):
        s = self.s
        s.update(x=START["x"], y=START["y"], dir=START["dir"], energy=RULES["energyStart"], night=n,
                 rocks=list(NIGHTS[n - 1]["rocks"]), dark=list(NIGHTS[n - 1]["dark"]), driven=0, repaired=0,
                 atMast=False, reported=False, vars={})

    def run(self, program, code_lines=0):
        """Run a parsed program on every night, from the start of the road each time: {"events": [...], "status":
        "complete" | "stopped"}. An event is {"type", "line", "msg", "tone", "state"} (the state just after it); a
        "night" event puts the robot back at the start (the window doesn't animate the jump)."""
        s = self.s
        if s["complete"]:
            return {"events": [], "status": "complete"}
        s["linesUsed"] = code_lines or 0  # (each run is the whole program: the stars count its lines, not a total)
        s["runs"] += 1
        s["nightsDone"], s["nightEnergy"] = 0, []
        events = []

        def say(type_, line, msg=None, tone=None):
            events.append({"type": type_, "line": line, "msg": msg, "tone": tone, "state": self.snapshot()})

        for n in range(1, len(NIGHTS) + 1):
            self.start_night(n)
            dark = len(s["dark"])
            say("night", 0, f"Night {n} of {len(NIGHTS)}: rocks have come down on the road and {dark} lamp"
                f"{'s are' if dark != 1 else ' is'} dark. Your program starts again from the top.", "info")
            actions = [0]
            try:
                self.exec_(program, say, actions)
                say("stop", 0, "The program ended before a report reached the radio mast. Face the mast and report "
                    "how many lamps you repaired.", "bad")
                return {"events": events, "status": "stopped"}
            except Stop as e:
                if not e.ok:
                    return {"events": events, "status": "stopped"}
            s["nightsDone"] = n
            s["nightEnergy"].append(s["energy"])
        s["complete"] = True
        say("complete", 0, "Three nights, one program: the hill road is lit and the radio mast is talking to "
            "Brookfield again.", "ok")
        return {"events": events, "status": "complete"}

    def value(self, name, line, say):
        s = self.s
        if name == "energy":
            return s["energy"]
        if name not in s["vars"]:
            say("info", line, f"{name} has no value yet: set it before you use it, for example: set {name} to 0.", "bad")
            raise Stop()
        return s["vars"][name]

    def assign(self, name, v, line, say):
        if v < 0 or v > RULES["maxValue"]:
            say("info", line, f"{name} would be {v}: the robot's variables hold whole numbers from 0 to "
                f"{RULES['maxValue']}.", "bad")
            raise Stop()
        self.s["vars"][name] = v
        say("set", line)

    def sense(self, sensor):
        s = self.s
        front = tile_at(s, s["x"] + DX[s["dir"]], s["y"] + DY[s["dir"]])
        if sensor == "path blocked":
            return not walkable(front)
        if sensor == "path clear":
            return walkable(front)
        if sensor == "rockfall in front":
            return front == "R"
        if sensor == "lamp dark":
            return any(s["y"] + dy == ROAD_Y - 1 and s["x"] + dx in s["dark"] for dx, dy in zip(DX, DY))
        raise ValueError(sensor)

    def exec_(self, ops, say, actions):
        s = self.s
        for op in ops:
            actions[0] += 1
            if actions[0] > RULES["maxActions"]:
                say("stop", op["line"], "That's too many steps for one night.", "bad")
                raise Stop()
            a, v, line = op["action"], op["values"], op["line"]
            if a == "repeat":
                for _ in range(v["n"]):
                    self.exec_(op["body"], say, actions)
                continue
            if a in ("if_sensor", "if_compare"):
                if a == "if_sensor":
                    yes = self.sense(v["sensor"])
                else:
                    x = self.value(v["reading"], line, say)
                    yes = {"less than": x < v["v"], "more than": x > v["v"], "equals": x == v["v"]}[v["cmp"]]
                say("check", line, None, "yes" if yes else "no")
                if yes:
                    self.exec_(op["body"], say, actions)
                elif op.get("else"):
                    self.exec_(op["else"], say, actions)
                continue
            if a in ("set", "set_eq"):
                self.assign(v["name"], v["v"], line, say)
                continue
            if a in ("add", "add_eq"):
                self.assign(v["name"], self.value(v["name"], line, say) + v["v"], line, say)
                continue
            if a in ("subtract", "subtract_eq"):
                self.assign(v["name"], self.value(v["name"], line, say) - v["v"], line, say)
                continue
            if a in ("calc_plus", "calc_minus"):
                x = self.value(v["reading"], line, say)
                self.assign(v["name"], x + v["v"] if a == "calc_plus" else x - v["v"], line, say)
                continue
            self.act(op, say)

    def pay(self, cost, what, line, say):
        s = self.s
        if s["energy"] >= cost:
            s["energy"] -= cost
            return
        say("flat", line, f"Not enough energy: {what} needs {cost} and the battery has {s['energy']}. Night "
            f"{s['night']} ends here: find a way that uses less (the if can save the spinner and the repairs).", "bad")
        raise Stop()

    def act(self, op, say):
        s, v, line = self.s, op["values"], op["line"]
        fx, fy = s["x"] + DX[s["dir"]], s["y"] + DY[s["dir"]]
        front = tile_at(s, fx, fy)
        a = op["action"]
        if a in ("move_forward", "move_back"):
            step = 1 if a == "move_forward" else -1
            for _ in range(v["n"]):
                nx, ny = s["x"] + DX[s["dir"]] * step, s["y"] + DY[s["dir"]] * step
                t = tile_at(s, nx, ny)
                if not walkable(t):
                    say("bump", line, BLOCKS.get(t, BLOCKS["#"]), "bad")
                    raise Stop()
                self.pay(RULES["cost"]["move"], "a square", line, say)
                s["x"], s["y"] = nx, ny
                s["driven"] += 1
                say("move", line)
                if (nx, ny) == (MAST["x"] - 1, MAST["y"]) and not s["atMast"]:
                    s["atMast"] = True
                    say("objective", line, "You've reached the radio mast at the top of the road.", "ok")
                if s["solar"] and s["driven"] % RULES["solarEvery"] == 0 and s["energy"] < RULES["energyMax"]:
                    s["energy"] += 1
                    say("solar", line, f"Solar Panel: +1 energy ({s['driven']} squares driven tonight).", "ok")
            return
        if a == "turn":
            s["dir"] = (s["dir"] + (3 if v["dir"] == "left" else 1)) % 4
            say("turn", line)
            return
        if a == "use":
            if v["tool"] != "spinner":
                say("info", line, f"Tonight you only have the front spinner: the {v['tool']} is back in Brookfield.", "bad")
                raise Stop()
            self.pay(RULES["cost"]["use"], "using the spinner", line, say)
            if front == "R":
                s["rocks"].remove(fx)
                say("use", line, "The front spinner grinds the rockfall away." + (" The road is clear tonight." if
                                                                                  not s["rocks"] else ""), "ok")
                return
            say("use", line, "The spinner whirrs, but there's no rockfall in front of you: 2 energy spent for "
                "nothing. (if path blocked can check first.)", "info")
            return
        if a == "repair":
            if front != "L":
                say("info", line, "There's nothing in front of you to repair. A lamp post stands beside the road: "
                    "turn to face it.", "bad")
                raise Stop()
            self.pay(RULES["cost"]["repair"], "a repair", line, say)
            if fx in s["dark"]:
                s["dark"].remove(fx)
                s["repaired"] += 1
                say("repair", line, "The lamp flickers and comes on." + (" Every lamp on the road is lit." if
                                                                         not s["dark"] else ""), "ok")
                return
            say("repair", line, "That lamp was working already: 3 energy spent checking it. (if lamp dark can check "
                "first.)", "info")
            return
        if a == "report":
            if front != "M":
                say("info", line, "Report from the radio mast: drive to the end of the road and face it.", "bad")
                raise Stop()
            n = self.value(v["reading"], line, say)
            if s["dark"]:
                say("report", line, f"You reported {n}, but {len(s['dark'])} lamp{'s are' if len(s['dark']) != 1 else ' is'}"
                    " still dark on the road. Repair them all before you report.", "bad")
                raise Stop()
            if n != s["repaired"]:
                say("report", line, f"You reported {n}, but you repaired {s['repaired']} lamp"
                    f"{'s' if s['repaired'] != 1 else ''} tonight. A variable that adds 1 at each repair keeps count.",
                    "bad")
                raise Stop()
            s["reported"] = True
            say("report", line, f"Report received: {n} lamp{'s' if n != 1 else ''} repaired. Night {s['night']} done!", "ok")
            raise Stop(ok=True)
        say("info", line, "The robot doesn't know how to do that on this mission.", "bad")
        raise Stop()


def new_mission(name, solar=False):
    return Mission(name, solar)


def record_finish(path, mission, robot_name):
    """The mission is done: the best result kept beside Mission 1's (no part to unlock). Returns the progress saved."""
    st = mission.stars()
    p = M1.load_progress(path)
    prev = p["missions"].get(MISSION_ID) or {}
    p["missions"][MISSION_ID] = {"complete": True, "bestStars": max(prev.get("bestStars") or 0, st["count"]),
                                 "robot": robot_name, "energyLeft": min(mission.s["nightEnergy"]),
                                 "linesUsed": mission.s["linesUsed"], "solar": mission.s["solar"]}
    try:  # (as Mission 1 saves it: the Solar Panel and Mission 1's result are kept as they were)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass
    return p


load_progress, has_part = M1.load_progress, M1.has_part
