"""Bring an older saved nation up to date with newer rules."""
from . import config as C
from .model import note


def ensure_current(w):
    rng = w.rng
    for g in C.GOODS:
        w.prices.setdefault(g, C.START_PRICES[g])
        w.avg_prices.setdefault(g, C.START_PRICES[g])
        w.week_start_prices.setdefault(g, w.prices[g])
    for h in w.households.values():
        for g in C.GOODS:
            h.inv.setdefault(g, 0.0)
    for p in w.people.values():
        if "creativity" not in p.traits:
            p.traits["creativity"] = round(min(1.0, max(0.0, rng.gauss(0.5, 0.18))), 2)
        for j in C.JOBS:
            p.job_pref.setdefault(j, round(rng.uniform(0.85, 1.15), 2))
        p.needs.setdefault("leisure", 0.5)
        if not p.life:
            note(p, p.birth_day, f"born in {w.regions[p.region].town}")
