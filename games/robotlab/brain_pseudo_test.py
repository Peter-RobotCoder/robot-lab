"""Checks for Robot Lab's brains in pseudo code (brain_pseudo.py, CHANGE 211): every line the phrasebook shows reads,
turns into Python and back again unchanged; the whole brain runs in the brain sandbox and drives as the pseudo code
says; Python typed in the Python column comes back as pseudo code, and a line that isn't known says so.

    python brain_pseudo_test.py
"""
import math
import sys

import brain_pseudo as B
import brain_rules
import brain_worker

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  ({detail})"))


def run_brain(source, me, enemies):
    brain = brain_worker.load(source, "my_brain.py")
    return brain_worker.run_tick(brain, "my_brain.py", {}, {"me": me, "enemies": enemies})


def robot(x, y, heading=0.0, armour=100.0):
    return {"x": x, "y": y, "heading": heading, "speed": 0.0, "armour": armour, "upside_down": False,
            "weapon_ready": True, "weapon_rpm": 0, "time": 1.0, "distance_to_wall": 5.0, "pit": [0.0, 0.0],
            "half_width": 0.5, "arena": 20.0}


def main():
    r = B.read(B.STARTER)
    check("The starter brain reads with no mistakes", not r["errors"] and r["source"], r["errors"])
    tree_ok = True
    try:
        import ast
        brain_rules.check_code(ast.parse(r["source"]))
    except brain_rules.RuleError as e:
        tree_ok = str(e)
    check("Its Python passes the brain sandbox's rules", tree_ok is True, tree_ok)
    me, near, far = robot(0, 0), robot(0, 2), robot(0, 12)  # (heading 0 faces +y: the enemy straight ahead)
    close = run_brain(r["source"], me, [near])
    away = run_brain(r["source"], me, [far])
    check("It attacks slowly when the enemy is close, and charges when it's far",
          close.get("r") == [0.4, 0.0, True] and away.get("r") == [1.0, 0.0, False], f"{close} {away}")
    check("With no enemy it sits still", run_brain(r["source"], me, []).get("r") == [0.0, 0.0, False])
    left = robot(-4, 4)
    turned = run_brain(B.read("turn towards enemy")["source"], me, [left])
    check("Turn towards enemy steers towards it (an enemy ahead on the left: steer left)",
          turned.get("r", [0, 0])[1] > 0, turned)
    fled = run_brain(B.read("turn away from enemy\ndrive forward")["source"], me, [left])
    check("Turn away from enemy steers the other way", fled.get("r", [0, 0])[1] < 0 and fled["r"][0] == 1.0, fled)

    examples = [p["example"] for p in B.C.dict["patterns"]]
    bad = []
    for p in B.C.dict["patterns"]:
        if p.get("opens") or p.get("middle") or p.get("closes"):
            continue
        row = B.read(p["example"])["rows"][0]
        back = B.line_to_pseudo(row["python_line"])
        if row["kind"] != "ok" or back != row["canonical"]:
            bad.append((p["example"], row.get("python_line"), back))
    check("Every action in the phrasebook turns into Python and back unchanged", not bad, bad)
    blocks = "if enemy in front\n  attack\nelse\n  turn towards enemy\nend\nif enemy distance less than 4\n  drive back\nend"
    rr = B.read(blocks)
    back, unknown = B.to_pseudo("\n".join(rr["body"]))
    check("A program with if, else and end goes to Python and back the same", not rr["errors"] and not unknown and
          [l.strip() for l in back.split("\n")] == [l.strip() for l in blocks.split("\n")], back)
    check("...indented by its blocks", back.split("\n")[1].startswith("  ") and not back.split("\n")[2].startswith(" "),
          back)

    words = {"if enemy closer than 3": "if enemy distance less than 3", "chase enemy": "turn towards enemy",
             "run away": "turn away from enemy", "fire": "attack", "if armour under 30": "if armour less than 30",
             "if enemy is on the left": "if enemy on left", "drive slow": "drive slowly",
             "if enemy distance < 4": "if enemy distance less than 4", "STOP!": "stop"}
    wrong = {t: B.read(t + ("\nattack\nend" if t.startswith("if") else ""))["rows"][0].get("canonical")
             for t in words}
    check("Other words, capitals, punctuation and < read as the phrasebook's words",
          all(wrong[t] == w for t, w in words.items()), {t: v for t, v in wrong.items() if v != words[t]})
    typo = B.read("drive forwad")["rows"][0]
    check("A slip is a mistake with a did-you-mean hint, never corrected", typo["kind"] == "error" and
          typo.get("hint") == "drive forward", typo)
    check("An if with no end is a mistake", B.read("if enemy in front\nattack")["errors"])
    check("While a line is a mistake there's no brain to run", B.read("drive forwad")["source"] is None)

    py = "steer = me.angle_to(enemy) / 30\nif me.distance_to(enemy) < 5:\n    attack = True\n# end of if\nx = 3"
    text, unknown = B.to_pseudo(py)
    lines = text.split("\n")
    check("Python typed in the Python column comes back as pseudo code",
          lines[:4] == ["turn towards enemy", "if enemy distance less than 5", "  attack", "end"], lines)
    check("...and a line of Python the phrasebook doesn't know is named and kept as typed",
          unknown == [5] and lines[4] == "x = 3", (unknown, lines))
    check("Spaces and a note after the code don't matter in the Python",
          B.line_to_pseudo("if   abs( me.angle_to(enemy) )<20:  # in my sights") == "if enemy in front")
    check("A number out of range in the Python isn't read", B.line_to_pseudo("if me.armour < 500:") is None)
    long = "\n".join(["attack"] * 200)
    check("At most 60 lines are read", len(B.read(long)["rows"]) == B.MAX_LINES)
    print(f"{sum(results)} of {len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
