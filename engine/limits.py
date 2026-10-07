"""The learners' limits (the engine's, layer C; CHANGE 31 and 62): the ranges a design is held to.

A game describes its ranges once (Spec): each setting's standard lowest and highest, the widest the teacher may
open them to, the points' standard and widest ranges, and the points to share. The teacher's Limits tab sends
new ranges; clean() makes them safe, fit() pulls a design back inside them.
"""


class Spec:
    def __init__(self, settings, full_settings, stats, stat_range, full_stat, points_total, full_points_total):
        """settings: {name: (lowest, highest, ...)}; full_settings: {name: (lowest, highest)}; stats: the points'
        names; stat_range and full_stat: (lowest, highest) for each point, standard and widest; points_total and
        full_points_total: the points to share, standard and the most."""
        self.settings, self.full_settings, self.stats = settings, full_settings, tuple(stats)
        self.stat_range, self.full_stat = tuple(stat_range), tuple(full_stat)
        self.points_total, self.full_points_total = points_total, full_points_total

    def default(self):
        """The learners' ranges as they are until the teacher changes them."""
        return {"settings": {k: [v[0], v[1]] for k, v in self.settings.items()},
                "points": {k: list(self.stat_range) for k in self.stats}, "points_total": self.points_total}

    def full(self):
        """The widest ranges: the teacher's own design is checked against these."""
        return {"settings": {k: list(v) for k, v in self.full_settings.items()},
                "points": {k: list(self.full_stat) for k in self.stats}, "points_total": self.full_points_total}

    def clean(self, new, old=None):
        """Limits sent by the teacher's window (or loaded from a file), made safe: every range inside the widest
        one, its lowest never above its highest. Anything missing or odd stays as it was (old, or the defaults)."""
        out, full = old or self.default(), self.full()
        out = {"settings": {k: list(v) for k, v in out["settings"].items()},
               "points": {k: list(v) for k, v in out["points"].items()}, "points_total": out["points_total"]}
        new = new if isinstance(new, dict) else {}
        for group in ("settings", "points"):
            for k, pair in (new.get(group) if isinstance(new.get(group), dict) else {}).items():
                if k not in out[group] or not (isinstance(pair, (list, tuple)) and len(pair) == 2):
                    continue
                if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in pair):
                    continue
                lo_full, hi_full = full[group][k]
                lo, hi = (max(lo_full, min(hi_full, v)) for v in pair)
                if group == "points":
                    lo, hi = int(round(lo)), int(round(hi))
                out[group][k] = [min(lo, hi), max(lo, hi)]
        total = new.get("points_total")
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            out["points_total"] = int(max(0, min(self.full_points_total, round(total))))
        return out

    def fit(self, d, limits):
        """A design pulled back inside the limits (the teacher has narrowed them): each value goes to the nearest
        one allowed, then points come off the biggest until the total fits. Returns the design (a copy if it
        changed)."""
        new = {**d, "points": dict(d["points"]), "settings": dict(d["settings"])}
        for k, (lo, hi) in limits["settings"].items():
            if k in new["settings"]:
                new["settings"][k] = max(lo, min(hi, new["settings"][k]))
        for k, (lo, hi) in limits["points"].items():
            if k in new["points"]:
                new["points"][k] = int(max(lo, min(hi, new["points"][k])))
        over = sum(new["points"].values()) - limits["points_total"]
        while over > 0:
            free = [k for k in self.stats if new["points"][k] > limits["points"][k][0]]
            if not free:
                break
            new["points"][max(free, key=lambda k: new["points"][k])] -= 1
            over -= 1
        return new if (new["points"], new["settings"]) != (d["points"], d["settings"]) else d

    def problems(self, d, limits=None):
        """What is outside the limits in a design's points and settings (the game checks the rest)."""
        limits = limits or self.default()
        out = []
        pts = d.get("points", {})
        if not isinstance(pts, dict) or set(pts) != set(self.stats):
            out.append(f"points must have exactly: {', '.join(self.stats)}")
        else:
            for k, v in pts.items():
                lo, hi = limits["points"][k]
                if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
                    out.append(f"{k} must be a whole number from {lo} to {hi}")
            if all(isinstance(v, int) for v in pts.values()) and sum(pts.values()) > limits["points_total"]:
                out.append(f"{sum(pts.values())} points used: the most you can spend is {limits['points_total']}")
        settings = d.get("settings", {})
        for k, (lo, hi) in limits["settings"].items():
            v = settings.get(k) if isinstance(settings, dict) else None
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi:
                out.append(f"{k} must be from {lo:g} to {hi:g}")
        return out
