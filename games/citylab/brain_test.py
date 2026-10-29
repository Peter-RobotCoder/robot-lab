"""City Lab's brain test (docs/plans/city-lab.md step 6): the starter brain (brains/my_brain.py) and the demo
(brains/demo_brain.py), each loaded the way the server loads a learner's (checked by brain_rules.py, run in its own
process by brain_worker.py) and given a person in Little Lab with the jobs on. Each must walk to the depot, take a
parcel and deliver it to its address by itself, and a brain with a mistake must stop with the line it was on.

    python brain_test.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import city_version  # noqa: E402
sys.path.insert(0, city_version.ENGINE_HOME)
import city_brain  # noqa: E402
import city_jobs  # noqa: E402
import city_sim as sim  # noqa: E402
from engine import wire  # noqa: E402

results = []


def check(name, ok, note=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({note})" if note and not ok else f"  {note}" if note else ""),
          flush=True)


def run_brain(path, seconds=150.0):
    """The brain in a city of its own: (deliveries done, seconds the first took, the autopilot's error)."""
    with open(path, encoding="utf-8") as f:
        brain, fname = city_brain.load_brain(f.read(), os.path.basename(path))
    try:
        auto = city_brain.Autopilot(brain, fname)
        w = sim.World(sim.city_of("village"), wire.Schema("city", sim.SCHEMA_FIELDS))
        w.jobs = city_jobs.Jobs(w.city, sim.RULES)
        w.add_person(0, sim.default_design("Brain"))
        for _ in range(int(seconds * 60)):
            w.step_all({0: auto(w.people[0], w)})
            deadline = time.perf_counter() + 0.05  # (its answer comes a tick late: wait for it, so it sees the city)
            while brain.pending is not None and brain.replies.empty() and time.perf_counter() < deadline:
                time.sleep(0.0005)
            done = [d for d in getattr(w.jobs, "done", []) if d["kind"] == "delivery" and d["pid"] == 0]
            if done or auto.error:
                break
        return done, auto.error
    finally:
        brain.close()


if __name__ == "__main__":
    for name in ("my_brain.py", "demo_brain.py"):
        t0 = time.time()
        done, error = run_brain(os.path.join(HERE, "brains", name))
        check(f"brains/{name} walks to the depot, takes a parcel and delivers it by itself", bool(done) and not error,
              f"{done[0]['seconds']:.0f} s in the city, paid {done[0]['pay']} ({time.time() - t0:.0f} s here)" if done
              else f"error: {error}" if error else "no delivery in 150 s")
    bad = os.path.join(os.environ.get("TEMP", HERE), "citylab_bad_brain.py")
    with open(bad, "w", encoding="utf-8") as f:
        f.write("def brain(me, city, others):\n    speed = me.speed\n    return 1, 0 / (speed - speed)\n")
    done, error = run_brain(bad, seconds=3.0)
    check("a brain with a mistake stops and says which line", bool(error) and "line 3" in str(error), str(error))
    os.remove(bad)
    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)} of {len(results)} passed")
    sys.exit(1 if failed else 0)
