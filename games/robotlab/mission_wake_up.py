"""Robot Lab Mission 1, Wake-Up Call: the mission itself, with no drawing. The prototype's mission
(missions/wake_up_call/prototype/cc_game.js) ported line for line: Mission.run takes a program from
mission_pseudo.parse_program and returns the events the 3D window animates. wake_up_call_test.py runs both on the
same programs and requires the same events.

TITAN or RAZORBACK has crash-landed in the hills above Brookfield. The whole valley is visible (no fog of war).
  1 Battery    the robot starts with 8 energy and every square costs 1: pick up the power cell (+25)
  2 Tool       pick up a tool from the supply crate: the front spinner, flipper, hammer or drum
  3 Blockage   face the rockfall in the pass and use the spinner (the other tools say why they don't work)
  4 Village    drive into Brookfield
  5 Repair     face the village power supply and repair it
Turning and picking up are free; using a tool costs 2, a repair 3. A run stops at a bump or a mistake and the robot
stays where it is: the next run carries on from there. A flat battery ends the mission.
Stars: one for finishing, one for 6 or more energy left, one for 20 or fewer lines of code run across the mission.
Finishing unlocks the Solar Panel for Mission 2 (save_progress).

MISSION_VERSION numbers the rules: replay_mission.py replays recorded programs and requires the same events as when
they were recorded (as kart_sim.SIM_VERSION and kart/replay_test.py). A change MEANT to change the rules raises it
and records again in the same commit; a change that wasn't shows up as a failed replay.
"""
import json
import os

MISSION_VERSION = 1

# The robots and tools are Robot Lab's own (mods/robots/*.py and lab_sim.WEAPONS).
# In the arena the tools are weapons; on this mission they are tools.
ROBOTS = {
    "TITAN": {
        "name": "TITAN", "colour": [235, 110, 20], "weapon": "wedge",
        "points": {"speed": 25, "attack": 25, "armour": 30, "control": 20},
        "settings": {"forward_speed": 85, "reverse_speed": 70, "turn_speed": 75, "acceleration": 75, "size": 105},
        "style": {"trim": [28, 28, 32], "lights": [255, 170, 40], "number": "TITAN"},
        "blurb": "A heavy wedge. Its own tool is the flipper.",
    },
    "RAZORBACK": {
        "name": "RAZORBACK", "colour": [200, 20, 28], "weapon": "spinner",
        "points": {"speed": 25, "attack": 35, "armour": 20, "control": 20},
        "settings": {"forward_speed": 80, "reverse_speed": 60, "turn_speed": 70, "acceleration": 70, "size": 100},
        "style": {"trim": [225, 225, 230], "lights": [60, 170, 255], "number": "RAZOR"},
        "blurb": "A low, quick robot. Its own tool is the front spinner.",
    },
}
TOOLS = {  # the mission's name for each: Robot Lab's weapon type
    "spinner": {"weapon": "spinner", "name": "Front spinner", "text": "a spinning bar at the front that stores energy: it grinds through rock"},
    "flipper": {"weapon": "wedge", "name": "Flipper", "text": "a wedge with a flipper: it scoops things up and lifts them"},
    "hammer": {"weapon": "hammer", "name": "Hammer", "text": "an arm that swings down over the top"},
    "drum": {"weapon": "drum", "name": "Drum", "text": "a vertical spinner: it throws things upwards"},
}
# # rock wall   . ground   S start   C power cell   T supply crate (the tools)   R rockfall
# V village     H house    G the village power supply
MAP = [
    "################",
    "#....T..########",
    "#.......#VVVVVV#",
    "#.C.....#VHVVHV#",
    "#.......RVVVVVV#",
    "#.......#VVHVGV#",
    "#S......#VVVVVV#",
    "################",
]
W, H = len(MAP[0]), len(MAP)
DX, DY = [0, 1, 0, -1], [-1, 0, 1, 0]  # north, east, south, west
DIR_NAMES = ["north", "east", "south", "west"]
RULES = {
    "energyStart": 8, "energyMax": 30, "cellCharge": 25,
    "cost": {"move": 1, "turn": 0, "use": 2, "repair": 3, "pick": 0},
    "stars": {"energy": 6, "lines": 20},  # a star for finishing, one for this much energy left, one for this few lines
    "maxActions": 2000,
}
OBJECTIVES = [
    {"id": "battery", "title": "Battery", "text": "Find a power cell and pick it up to recharge."},
    {"id": "tool", "title": "Tool", "text": "Pick up a tool from the supply crate."},
    {"id": "blockage", "title": "Blockage", "text": "Face the rockfall and use the right tool to clear it."},
    {"id": "village", "title": "Village", "text": "Drive into Brookfield village."},
    {"id": "repair", "title": "Repair", "text": "Face the village power supply and repair it."},
]
UNLOCK = {"id": "solar_panel", "name": "Solar Panel",
          "text": "A spare solar panel from Brookfield, fitted to your robot's back. In Mission 2 it recharges 1 energy "
                  "for every 5 squares you drive."}
MISSION_ID = "wake_up_call"


def find(ch):
    for y in range(H):
        x = MAP[y].find(ch)
        if x >= 0:
            return {"x": x, "y": y}
    return None


START = dict(find("S"), dir=0)


def tile_at(s, x, y):
    if x < 0 or y < 0 or x >= W or y >= H:
        return "#"
    t = MAP[y][x]
    if t == "R" and s["rockCleared"]:
        return "r"
    if t == "C" and s["cellTaken"]:
        return "."
    if t == "S":
        return "."
    return t


BLOCKS = {
    "#": "Bump! A rock wall is in the way.",
    "R": "Bump! The rockfall blocks the pass. Face it and use the right tool to clear it.",
    "H": "Bump! That's a house.",
    "G": "Bump! That's the village power supply. Face it and repair it.",
}
WHY_NOT = {
    "flipper": "The flipper lifts one rock and drops it again. The pile's too big to lift: a tool that cuts would grind through it.",
    "hammer": "The hammer chips at the rocks but the pile doesn't move. Something that spins and cuts sideways would grind through.",
    "drum": "The drum throws grit upwards but can't reach into the pile. A flat spinning bar at the front would cut into it.",
}


class Stop(Exception):
    """A run ends here (a bump, a mistake, a flat battery or the mission done)."""


class Mission:
    def __init__(self, robot_name):
        if robot_name not in ROBOTS:
            raise ValueError("No robot called " + str(robot_name))
        self.robot = ROBOTS[robot_name]
        self.s = {
            "x": START["x"], "y": START["y"], "dir": START["dir"], "energy": RULES["energyStart"], "tool": None,
            "cellTaken": False, "toolPicked": False, "rockCleared": False, "inVillage": False, "repaired": False,
            "linesUsed": 0, "runs": 0, "failed": False, "complete": False,
        }

    def snapshot(self):
        return dict(self.s)

    def objectives(self, s=None):
        s = s or self.s
        done = [s["cellTaken"], s["toolPicked"], s["rockCleared"], s["inVillage"], s["repaired"]]
        now = done.index(False) if False in done else -1
        return [dict({"done": done[i], "now": i == now}, **o) for i, o in enumerate(OBJECTIVES)]

    def stars(self, s=None):
        s = s or self.s
        energy, lines = s["energy"] >= RULES["stars"]["energy"], s["linesUsed"] <= RULES["stars"]["lines"]
        return {"complete": s["complete"], "energy": energy, "lines": lines,
                "count": 1 + (1 if energy else 0) + (1 if lines else 0) if s["complete"] else 0}

    def run(self, program, code_lines=0):
        """Run a parsed program from where the robot is: {"events": [...], "status": "done" | "complete" | "flat" |
        "stopped"}. An event is {"type", "line", "msg", "tone", "state"} (the state just after it)."""
        s = self.s
        if s["complete"] or s["failed"]:
            return {"events": [], "status": "complete" if s["complete"] else "flat"}
        s["linesUsed"] += code_lines or 0
        s["runs"] += 1
        events = []

        def say(type_, line, msg=None, tone=None):
            events.append({"type": type_, "line": line, "msg": msg, "tone": tone, "state": self.snapshot()})

        actions = [0]

        def pay(cost, what, line):
            if s["energy"] >= cost:
                s["energy"] -= cost
                return
            on_cell = tile_at(s, s["x"], s["y"]) == "C"
            msg = f"Not enough energy: {what} needs {cost} and the battery has {s['energy']}."
            if s["energy"] < RULES["cost"]["move"] and not on_cell:
                s["failed"] = True
                msg += " The battery is flat. Restart the mission and plan a shorter route (or reach the power cell sooner)."
            say("flat", line, msg, "bad")
            raise Stop()

        def exec_(ops):
            for op in ops:
                if op["action"] == "repeat":
                    for _ in range(op["values"]["n"]):
                        exec_(op["body"])
                    continue
                actions[0] += 1
                if actions[0] > RULES["maxActions"]:
                    say("stop", op["line"], "That's too many steps for one run.", "bad")
                    raise Stop()
                self.act(op, say, pay)

        status = "done"
        try:
            exec_(program)
        except Stop:
            status = "complete" if s["complete"] else "flat" if s["failed"] else "stopped"
        return {"events": events, "status": status}

    def act(self, op, say, pay):
        s, v, line = self.s, op["values"], op["line"]

        def front():
            return tile_at(s, s["x"] + DX[s["dir"]], s["y"] + DY[s["dir"]])

        action = op["action"]
        if action in ("move_forward", "move_back"):
            step = 1 if action == "move_forward" else -1
            for _ in range(v["n"]):
                nx, ny = s["x"] + DX[s["dir"]] * step, s["y"] + DY[s["dir"]] * step
                t = tile_at(s, nx, ny)
                if t in BLOCKS:
                    say("bump", line, BLOCKS[t], "bad")
                    raise Stop()
                pay(RULES["cost"]["move"], "a square", line)
                s["x"], s["y"] = nx, ny
                say("move", line)
                if t == "V" and not s["inVillage"]:
                    s["inVillage"] = True
                    say("objective", line, "You've reached Brookfield village! Now find the power supply.", "ok")
            return
        if action == "turn":
            s["dir"] = (s["dir"] + (3 if v["dir"] == "left" else 1)) % 4
            say("turn", line, None)
            return
        if action == "pick_up":
            here = tile_at(s, s["x"], s["y"])
            if v["item"] == "power cell":
                if here != "C":
                    say("info", line, "There's no power cell on this square.", "bad")
                    raise Stop()
                s["cellTaken"] = True
                before = s["energy"]
                s["energy"] = min(RULES["energyMax"], s["energy"] + RULES["cellCharge"])
                say("objective", line, f"Power cell fitted: energy {before} → {s['energy']}.", "ok")
                return
            if here != "T":
                say("info", line, f"There's no {v['item']} here. The tools are in the supply crate.", "bad")
                raise Stop()
            if s["tool"] == v["item"]:
                say("info", line, f"You're already holding the {v['item']}.", "info")
                return
            old = s["tool"]
            s["tool"] = v["item"]
            first = not s["toolPicked"]
            s["toolPicked"] = True
            say("objective" if first else "info", line,
                (f"You put the {old} back and picked up the {v['item']}" if old else f"You picked up the {v['item']}")
                + f" ({TOOLS[v['item']]['text']}).", "ok" if first else "info")
            return
        if action == "use":
            if s["tool"] != v["tool"]:
                say("info", line, f"You're holding the {s['tool']}, not the {v['tool']}." if s["tool"] else
                    f"You aren't holding a {v['tool']}. Pick one up from the supply crate first.", "bad")
                raise Stop()
            pay(RULES["cost"]["use"], f"using the {v['tool']}", line)
            t = front()
            if t == "R":
                if v["tool"] == "spinner":
                    s["rockCleared"] = True
                    say("use", line, "The front spinner grinds through the rockfall. The pass is clear!", "ok")
                    return
                say("use", line, WHY_NOT[v["tool"]], "info")
                return
            say("use", line, f"The {v['tool']} works, but there's nothing in front of you to use it on.", "info")
            return
        if action == "repair":
            if front() != "G":
                say("info", line, "There's nothing in front of you to repair.", "bad")
                raise Stop()
            pay(RULES["cost"]["repair"], "a repair", line)
            s["repaired"] = True
            s["complete"] = True
            say("complete", line, "The power supply hums back to life. The lights come on all over Brookfield!", "ok")
            raise Stop()
        say("info", line, "The robot doesn't know how to do that yet.", "bad")
        raise Stop()


def new_mission(name):
    return Mission(name)


# ---------- progress kept for Mission 2 ----------
# As the prototype keeps it in the browser (localStorage "clubcoders.robotlab.progress"):
# {"parts": ["solar_panel"], "missions": {"wake_up_call": {"complete", "bestStars", "robot", "energyLeft", "linesUsed"}}}
def load_progress(path):
    try:
        with open(path, encoding="utf-8") as f:
            p = json.load(f)
        if isinstance(p, dict) and isinstance(p.get("parts"), list) and isinstance(p.get("missions"), dict):
            return p
    except (OSError, ValueError):
        pass
    return {"parts": [], "missions": {}}


def record_finish(path, mission, robot_name):
    """The mission is done: the Solar Panel unlocked and the best result kept. Returns the progress saved."""
    st = mission.stars()
    p = load_progress(path)
    if UNLOCK["id"] not in p["parts"]:
        p["parts"].append(UNLOCK["id"])
    prev = p["missions"].get(MISSION_ID) or {}
    p["missions"][MISSION_ID] = {"complete": True, "bestStars": max(prev.get("bestStars") or 0, st["count"]),
                                 "robot": robot_name, "energyLeft": mission.s["energy"],
                                 "linesUsed": mission.s["linesUsed"]}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass  # (a read-only folder: kept for this visit only, as the prototype in a private window)
    return p


def has_part(path, part):
    return part in load_progress(path)["parts"]
