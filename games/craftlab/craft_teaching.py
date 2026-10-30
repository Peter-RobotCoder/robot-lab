"""Craft Lab's teaching (CHANGE 200): what is Craft Lab's own on top of the engine's framework (engine/teaching.py):
which builds, blueprints, nights, rifts and Bot brains complete which objectives, and where learners' Bot designs are kept.

The server calls into this. Everything a learner achieves is saved as evidence against the learning outcomes in
craft_missions.py, so the teacher can see (and export) who has shown what. What a learner has done in the world
comes from their player's stats in the game (craft_game.Player.stats: mined, placed, built, refined, defeated,
nights, rifts patched, what their Bot did).
"""
import asyncio
import math
import os

import craft_version  # noqa: F401  (puts the engine on the path)
import craft_blocks as B
import craft_brain
import craft_design as sim
import craft_items as items
import craft_sim
import craft_missions as cm
import craft_mods
import craft_profiles
from ai_pipeline import bot_file_text, slug
from engine import teaching

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("CRAFTLAB_DATA") or os.path.join(HERE, "data")
BOTS_DIR = os.path.join(DATA, "mods", "bots")
now_text = teaching.now_text


class Record(teaching.Record):
    def __init__(self, name):
        super().__init__(name)
        self.nights_at = None      # the nights survived when this lesson's checks began (2 c counts from here)


def apply_mods(t, files):
    """Check and save changed mod files (blocks, blueprints, the world, the rules, learners' Bots), then use them."""
    written = []
    if not isinstance(files, dict):
        return "Nothing to apply"
    readers = {"mods/blocks.py": craft_mods.load_blocks, "mods/blueprints.py": craft_mods.load_blueprints,
               "mods/world.py": craft_mods.load_world, "mods/rules.py": craft_mods.load_rules}
    for rel, text in files.items():
        rel = str(rel).replace("\\", "/")
        name_part = rel[len("mods/bots/"):]
        ok = rel in readers or (rel.startswith("mods/bots/") and rel.endswith(".py") and "/" not in name_part
                                and ".." not in rel)
        if not ok:
            return f"Not applied: {rel} isn't a mod file"
        path = os.path.join(BOTS_DIR, name_part) if rel.startswith("mods/bots/") else os.path.join(HERE, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".check"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(str(text))
        try:
            if rel.startswith("mods/bots/"):
                craft_mods.load_bot(tmp)
            else:
                var = {"mods/blocks.py": "BLOCKS", "mods/blueprints.py": "BLUEPRINTS", "mods/world.py": "WORLD",
                       "mods/rules.py": "RULES"}[rel]
                craft_mods.read_value(tmp, var)
        except craft_mods.ModError as e:
            os.remove(tmp)
            return f"Not applied: {e}"
        os.replace(tmp, path)
        written.append(rel)
    t.server.reload_mods(written)
    return "Applied: " + ", ".join(written) if written else "Nothing to apply"


GAME = teaching.Game(slug_word="craftlab", missions=cm, profiles=craft_profiles, brain=craft_brain, sim=sim, data=DATA,
                     designs=BOTS_DIR, design_text=bot_file_text, load_design=craft_mods.load_bot,
                     mod_error=craft_mods.ModError, apply_mods=apply_mods, slug=slug,
                     unit=lambda p: p.unit, world=lambda server: server.log,
                     units=lambda log: list(log.units()),
                     rebuild=lambda server: server.rebuild())


class Teaching(teaching.Teaching):
    record_class = Record
    reflections = cm.REFLECTIONS

    def __init__(self, server):
        super().__init__(server, GAME)

    # ---------- what the server asks ----------
    def attach(self, p):
        """The learner's brain drives their Craft Bot while the autopilot is on (the teacher's too)."""
        r = self.record(p.name)
        game = self.server.game
        if p.pid is None:
            return
        game.bot_brains[p.pid] = r.brain if (r.brain and r.autopilot) else None

    # ---------- the game's own: what completes which objective ----------
    def build_rejected(self, p, r, problems, new=None, by_code=False):
        total = self.server.lesson["limits"]["points_total"]
        pts = (new or {}).get("points") if isinstance((new or {}).get("points"), dict) else {}
        spent = sum(v for v in (pts.get(k) for k in sim.STATS) if isinstance(v, int) and not isinstance(v, bool))
        if by_code and spent > total:
            self.complete(p.name, "2f", f"Tried to spend {spent} points in the code: refused, the most is {total}")

    def build_checks(self, p, r, new, old, by_code):
        self.experience_garage(p, new, old, by_code)  # (Experience 1's garage and code objectives: CHANGE 210)
        pts, was_pts = new.get("points", {}), old.get("points", sim.default_design()["points"])
        if not by_code:
            was = old.get("name", p.name)
            if new["name"] != was:
                self.complete(p.name, "1a", f'bot_name "{was}" became "{new["name"]}" (a string, with the GUI)')
            changed = [k for k in sim.STATS if pts.get(k) != was_pts.get(k)]
            if len(changed) >= 2:
                self.complete(p.name, "1b", ", ".join(f"{k} = {pts[k]}" for k in changed) + " (integers, with the GUI)")
            if new["colour"] != old.get("colour"):
                self.complete(p.name, "1c", f"colour = {new['colour']} (a list, with the GUI)")
        limits = self.server.lesson["limits"]
        edge = [k for k in sim.STATS if pts[k] in limits["points"][k]]
        if edge:
            self.complete(p.name, "2e", "Boundary value accepted: " + ", ".join(f"{k} = {pts[k]}" for k in edge))

    def tick_checks(self, p, r, unit, world, now):
        st = unit.stats
        built, placed, bot = st.get("built", {}), st.get("placed", {}), st.get("bot", {})
        if built.get("fabricator") and built.get("drill_mk1"):
            self.complete(p.name, "1e", "Built a Fabricator and a Mk1 Drill")
        if len(built) >= 5:
            self.complete(p.name, "2a", "Built " + ", ".join(sorted(built)[:8]))
        if st.get("refined", {}).get("iron_ingot"):
            self.complete(p.name, "2b", f"Refined {st['refined']['iron_ingot']} iron ingot(s)")
        nights = st.get("nights", 0)
        if r.nights_at is None:
            r.nights_at = nights
        elif nights > r.nights_at:
            self.complete(p.name, "2c", "Survived a night")
        mod_made = self.server.mod_blueprint_outputs()
        made = sorted(k for k in built if k in mod_made)
        if made:
            self.complete(p.name, "2d", "Built a blueprint of their own: " + ", ".join(made))
        if r.brain and r.autopilot and r.brain.seconds_running(now) >= 20:
            self.complete(p.name, "3a", f"Bot brain ran for {r.brain.seconds_running(now):.0f} s without an error")
        if bot.get("bot_dug", 0) >= 10:
            self.complete(p.name, "3c", f"The Craft Bot dug {bot['bot_dug']} blocks by itself")
        if bot.get("bot_placed", 0) >= 10:
            self.complete(p.name, "3d", f"The Craft Bot placed {bot['bot_placed']} blocks by itself")
        if bot.get("bot_ore", 0):
            self.complete(p.name, "4d", "The Craft Bot mined an ore by itself")
        killed = st.get("killed", {})
        if killed.get("glitch") or killed.get("rust"):
            self.complete(p.name, "4e", "Defeated " + ", ".join(f"{n} {k}" for k, n in killed.items() if k in ("glitch", "rust")))
        if st.get("rifts", 0):
            self.complete(p.name, "4f", f"Patched {st['rifts']} Glitch rift(s)")
        if sum(placed.values()) >= 100 and placed.get("door") and placed.get("pod") and placed.get("glowstick"):
            self.complete(p.name, "5a", f"Placed {sum(placed.values())} blocks, with a door, a Recharge Pod and Glowsticks")
        mods = self.server.mod_block_keys()
        own = sorted(k for k in placed if k in mods)
        if own:
            self.complete(p.name, "5b", "Placed a block of their own: " + ", ".join(own))

    def reflected(self, p, r, mission, text):
        if mission == "5c" and len(text.split()) >= cm.REFLECTIONS["5c"]:
            self.complete(p.name, "5c", text)

    def brain_checks(self, p, r):
        f = r.brain_features
        if "count" in f or "memory" in f:
            self.complete(p.name, "3b", "Brain counts (bot.dug, bot.placed or bot.memory) and stops")
        if "for" in f or "while" in f:
            self.complete(p.name, "3e", "Brain uses a " + ("for" if "for" in f else "while") + " loop")
        if "if" in f:
            self.complete(p.name, "4a", "Brain uses if / elif / else")
        if "own_function" in f:
            self.complete(p.name, "4b", "Brain calls its own helper function")
        if "memory" in f:
            self.complete(p.name, "4c", "Brain keeps state in bot.memory")

    # ---------- Experience 1, Orientation (CHANGE 210): what each objective measures, on the real island ----------
    # Everything is measured from the player's own game record (craft_game.Player: where they stand, their stats of
    # what they placed, mined, built and defeated, what their Bot dug), by how much it has gone up since the objective
    # began: nothing is drawn or made for the experience. The garage and the code are counted as they are built
    # (build_checks).
    def experience_value(self, p, r, oid, unit, log, now, run):
        if unit is None or oid in ("garage", "code"):
            return None
        b, v, s, st = run["base"], run["value"], unit.state, unit.stats
        counts = {"placed": sum(st.get("placed", {}).values()),
                  "logs": sum(st.get("mined", {}).get(k, 0) for k in items.GROUPS["any_log"]),
                  "boards": sum(st.get("built", {}).get(k, 0) for k in items.GROUPS["any_boards"]),
                  "fab_built": st.get("built", {}).get("fabricator", 0),
                  "fab_placed": st.get("placed", {}).get("fabricator", 0),
                  "bot_dug": st.get("bot", {}).get("bot_dug", 0),
                  "glitches": st.get("killed", {}).get("glitch", 0)}
        ground = bool(s["flags"] & craft_sim.F_GROUND)
        if b.get("unit") is not unit:  # (the objective's start, or a new player after a new world: measured from here)
            b.update(unit=unit, pos=(s["x"], s["y"]), ground=s["z"] if ground else None, **counts)
            b.setdefault("deaths", st.get("deaths", 0))
            return None
        got = {k: max(0, n - b[k]) for k, n in counts.items()}
        b.update(counts)
        if oid == "walk":
            x, y = s["x"], s["y"]
            step = math.hypot(x - b["pos"][0], y - b["pos"][1])
            b["pos"] = (x, y)
            return v + (step if step < 5 and not unit.asleep else 0.0)  # (a jump to a Pod or the start isn't walking)
        if oid == "climb":  # (each time you stand higher than you last stood: up onto a block, up a hill)
            if not ground:
                return None
            was, b["ground"] = b.get("ground"), s["z"]
            up = s["z"] - was if was is not None else 0.0
            return v + (round(up) if 0.5 < up < 4 else 0)
        if oid == "place":
            return v + got["placed"]
        if oid == "chop":
            return v + got["logs"]
        if oid == "fabricator":  # (three steps, in any order: Boards built, a Fabricator built, a Fabricator put down)
            steps = b.setdefault("steps", [])
            steps += [k for k in ("boards", "fab_built", "fab_placed") if got[k] and k not in steps]
            return float(len(steps))
        if oid == "brain":
            return v + got["bot_dug"]
        if oid == "glitch" and got["glitches"]:
            if st.get("deaths", 0) == b["deaths"]:  # (never knocked out on the way)
                self.experience_bonus(p.name, "glitch")
            return 1.0
        return None

    def x_built(self, name, oid, kinds=None):
        """A build counts towards the garage objective (the kinds of variable it changed) or the code one."""
        if self.experience is None:
            return
        run = self.xrun(self.record(name))
        o = self.x_objective(run)
        if o is None or o["id"] != oid:
            return
        self.x_measuring(run)
        if kinds is None:
            run["value"] = 1.0
        else:
            have = set(run["base"].get("kinds", [])) | kinds
            run["base"]["kinds"] = sorted(have)
            run["value"] = float(len(have & {"string", "integer", "list"}))

    def experience_garage(self, p, new, old, by_code):
        if by_code:
            if teaching.design_changes(old, new, sim.schema()):
                self.x_built(p.name, "code")
            return
        kinds = set()
        if new.get("name") != old.get("name", p.name):
            kinds.add("string")
        if any(new.get("points", {}).get(k) != (old.get("points") or {}).get(k) for k in sim.STATS):
            kinds.add("integer")
        if new.get("colour") != old.get("colour"):
            kinds.add("list")
        self.x_built(p.name, "garage", kinds)

    def experience_begin(self, p, r, oid, unit, log, run):
        if run["index"] == 0 and self.solo:
            self.solo_fresh(p)
        if oid == "brain":
            self.bot_kit_for(p)
        if oid == "glitch" and self.solo:
            self.solo_dusk(run)

    def experience_actions(self, p, r, oid, run):
        g = self.server.game
        if oid == "glitch" and self.solo and g.is_night() and not g.rifts and \
                not any(m["kind"] == "glitch" for m in g.mobs.mobs.values()):
            return [["rifts", "OPEN THE RIFTS AGAIN"]]  # (none opened near you, or every one patched)
        return []

    def experience_action(self, p, r, action, run):
        o = self.x_objective(run)
        if action == "rifts" and self.solo and o is not None and o["id"] == "glitch" and self.server.game.is_night():
            self.server.game.open_rifts()

    def experience_ended(self, p, r, oid, run):
        if oid == "glitch" and self.solo:
            self.solo_calm(run)

    def experience_reset(self, p, r, run):
        if self.solo:
            self.solo_calm(run)

    def solo_fresh(self, p):
        """On your own, every run starts as a new player does: the game's own starter kit, at the island's start
        (what you carried last time stays in your profile's past; the Bot and your Fabricators stay where they are)."""
        g, q = self.server.game, p.unit
        if q is None:
            return
        g.close(q)
        q.inv, q.cursor, q.building = [None] * items.SLOTS, None, []
        g.starter_kit(q)
        q.state.update(x=g.world.spawn[0], y=g.world.spawn[1], z=g.world.spawn[2], vx=0.0, vy=0.0, vz=0.0)
        g.place_safely(q)
        g.inv_changed(q.pid)

    def bot_kit_for(self, p):
        """The Brains objective: the teacher's Bot kit (K) for this learner, if they've no Bot and no dock yet."""
        g, q = self.server.game, p.unit
        if q is None or g.bot_of(q.pid) is not None or any(s and s[0] == B.ITEM_ID["dock"] for s in q.inv):
            return
        self.server.bot_kit(q)

    def solo_dusk(self, run):
        """On your own: the dusk brought, with creatures on, as the teacher's T and M do: the game opens its Glitch
        rifts (a dusk that is set opens them, even on a world's first night)."""
        L = self.server.lesson
        run["base"].setdefault("was", {"time": L.get("time"), "hazards": dict(L.get("hazards") or {}),
                                       "mobs": L.get("mobs", True)})
        L.update(time="dusk", mobs=True, hazards=dict(L.get("hazards") or {}, mobs=True))
        self.server.rebuild()
        self.tell_everyone()

    def solo_calm(self, run):
        """The day back as the experience plays it (its dawn seals the rifts and pulls the Glitches home)."""
        was = run["base"].pop("was", None)
        if was:
            self.server.lesson.update(was)
            self.server.rebuild()
            self.tell_everyone()

    def tell_everyone(self):
        """The lesson changed under the windows (the dusk on your own): they are told as the teacher's changes are."""
        try:
            asyncio.get_running_loop().create_task(self.server.broadcast_lesson())
        except RuntimeError:  # (no loop running: a test calling this directly)
            pass
