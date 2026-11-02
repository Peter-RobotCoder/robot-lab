"""The Brain panel's server side (CHANGE 211): the real Robot Lab server, in this process.

    .venv\\Scripts\\python brain_panel_test.py

- RUN: the panel's pseudo code is the learner's brain, autopilot on, and the pseudo code kept with their profile
- every version of a learner's code is kept (once each), and the learner's card counts them
- the page's questions: pseudo code read, and the Python column read back to pseudo code
- Mission 3 f, escape or attack in code: 3 hits landed by the code (ATTACK); 20 seconds unhit with an enemy close by
  (ESCAPE), a hit starting the 20 seconds again
- a battle won: every robot switches off
Test data goes to a temporary folder. Exit code 0 = all fine.
"""
import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="brain_panel_test_")
os.environ["ROBOTLAB_DATA"] = TMP
results = []


def check(name, ok, note=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note and not ok else ""), flush=True)


class FakeWs:
    pass


def main():
    import brain_pseudo
    import lab_profiles
    import lab_server
    import lab_sim as sim
    srv = lab_server.LabServer()
    t = srv.teaching
    t.apply_lesson(3)
    srv.lesson["teacher_robot"] = False
    srv.lesson["cpu_robots"] = 1
    srv.lesson["cpu_level"] = "none"
    srv.lesson["hazards"] = dict(srv.lesson["hazards"], pit=False, floor_flipper=False, saws=False, spikes=False)
    p = lab_server.Player(FakeWs(), "learner", "Tester", (60, 130, 230))
    p.profile = lab_profiles.login("Tester", "a good password", allow_new=True)[0]
    t.login(p)
    srv.players[p.ws] = p
    srv.rebuild_arena()
    sent = []

    async def fake_send(ws, msg):
        sent.append(msg)
    srv.send = fake_send

    async def fake_deliver(pairs):
        sent.extend(m for _, m in pairs if isinstance(m, dict))
    srv.deliver = fake_deliver

    def step(n=1):
        for _ in range(n):
            srv.arena.step()
            if int(srv.arena.time / sim.STEP) % 30 == 0:
                t.tick(srv.arena.time)
            srv.result(srv.arena[0] if hasattr(srv.arena, "__getitem__") else srv.arena)

    def run(pseudo):
        sent.clear()
        p.brain_at = -100  # (no wait between uploads in the test)
        asyncio.run(srv.on_message(p, {"type": "brain_run", "pseudo": pseudo}))
        return next((m for m in sent if m.get("type") == "brain_result"), {})

    r = t.record(p.name)
    reply = run("drive forwad")
    check("RUN with a mistake: refused, the line named", not reply.get("ok") and "Line 1" in reply.get("error", ""),
          reply)
    reply = run(brain_pseudo.STARTER)
    check("RUN: the pseudo code is the brain, and autopilot is on", reply.get("ok") and r.brain and r.autopilot
          and p.robot.brain is r.brain, reply)
    check("...the pseudo code is kept with the profile", t.profiles[p.name].get("brain_pseudo") == brain_pseudo.STARTER)
    check("...and comes back in the missions message (the panel shows it again)",
          t.missions_msg(p).get("brain_pseudo") == brain_pseudo.STARTER)
    v = t.code_versions(p.name)
    check("Every version is kept: one so far, written in pseudo code, with its Python",
          len(v) == 1 and v[0]["via"] == "pseudo" and v[0]["pseudo"] == brain_pseudo.STARTER
          and "def brain(me, enemies):" in v[0]["source"] and "if" in v[0]["features"], v)
    run(brain_pseudo.STARTER)
    check("...the same code again isn't kept twice", len(t.code_versions(p.name)) == 1)
    with open(os.path.join(HERE, "brains", "my_brain.py"), encoding="utf-8") as f:
        p.brain_at = -100
        asyncio.run(srv.on_message(p, {"type": "brain", "source": f.read()}))
    v = t.code_versions(p.name)
    check("...a brain uploaded from its file (U) is kept too", len(v) == 2 and v[1]["via"] == "file", [x["via"] for x in v])
    card = t.card_data(p.name).get("code") or {}
    check("The learner's card counts the versions, first and latest", card.get("versions") == 2
          and card["first"]["lines"] == 8 and card["latest"]["via"] == "file", card)

    q = lab_server.brain_code_msg({"type": "brain_code", "side": "pseudo", "text": "chase enemy\nfire",
                                   "phrasebook": True})
    check("The page asks: pseudo code read, each line's Python, and the phrasebook",
          q["ok"] and q["rows"][0]["python_line"] == "steer = me.angle_to(enemy) / 30" and q["phrasebook"]["patterns"],
          q)
    q = lab_server.brain_code_msg({"type": "brain_code", "side": "python",
                                   "text": "if me.distance_to(enemy) < 4:\n    attack = True\n# end of if\nprint(7)"})
    check("...and its Python column read back to pseudo code, the unknown line named",
          q["pseudo"].split("\n")[:3] == ["if enemy distance less than 4", "  attack", "end"] and q["unknown"] == [4]
          and not q["ok"], q)

    # Mission 3 f: ATTACK
    cpu = srv.cpus[0].robots[0]
    cpu.brain = None
    p.robot.reset() if hasattr(p.robot, "reset") else None
    reply = run("turn towards enemy\nattack\nif enemy distance less than 1\n  drive back\nelse\n  drive forward\nend")
    check("3 f is the first mission of lesson 3", next(iter(t.missions_msg(p)["missions"]))["id"] == "3f")
    start = p.robot.pos
    step(60 * 3)
    check("The code drives: three seconds later the robot has gone towards the computer robot",
          (p.robot.pos - cpu.pos).length() < (start - cpu.pos).length() - 1.0, f"{start} -> {p.robot.pos}")
    p.robot.hits += 2  # (the hits themselves are the arena's: two here, then one more)
    step(31)
    check("3 f ATTACK: not done at 2 hits", "3f" not in r.done)
    p.robot.hits += 1
    step(31)
    check("3 f ATTACK: 3 hits landed while the code drives", "ATTACK" in r.done.get("3f", {}).get("detail", ""),
          f"hits {p.robot.hits}")

    # Mission 3 f: ESCAPE (a fresh learner record; an enemy parked close by; the code keeps still and is never hit)
    r.done.pop("3f", None)
    r.code_run = None
    run("stop")
    cpu.reset()
    p.robot.start = (sim.Point3(cpu.pos.x + 3.0, cpu.pos.y, cpu.pos.z), 90.0)
    p.robot.reset()
    step(60 * 5)
    p.robot.times_hit += 1  # (a hit: the 20 seconds start again from here)
    step(60 * 12)
    check("3 f ESCAPE: not done yet after 12 s since a hit", "3f" not in r.done)
    step(60 * 10 + 31)
    run_now = dict(r.code_run or {}, robot=None, brain=None)
    check("3 f ESCAPE: 20 s with an enemy close by and no hit taken", "ESCAPE" in r.done.get("3f", {}).get("detail", ""),
          f"{r.done.get('3f')} {run_now} now {srv.arena.time:.1f} hit {p.robot.times_hit} "
          f"apart {(p.robot.pos - cpu.pos).length():.1f}")

    # the battle won: every robot switches off
    a = srv.arena[0] if hasattr(srv.arena, "__getitem__") else srv.arena
    t.on_message(p, {"type": "autopilot"})  # (off)
    p.robot.brain = None
    p.robot.start = (sim.Point3(0, 0, cpu.pos.z), 0.0)  # (the middle, facing up the arena: room to drive)
    p.robot.reset()
    cpu.reset()
    p.robot.drive(1.0, 0.0, True)
    step(60)
    flat = lambda: p.robot.np.node().getLinearVelocity().getXy().length()  # noqa: E731
    moving = flat()
    a.final = (p.robot, f"{p.robot.name} WINS!")
    step(120)
    still = flat()
    check("A battle won: every robot switches off (driven at full speed before, stopped after)",
          moving > 1.0 and still < 0.3 and not p.robot.weapon_on, f"{moving:.2f} -> {still:.2f}")
    print(f"{sum(results)} of {len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
