"""Inventions: medieval improvements dreamed up by experienced workers.

Technology stays medieval, but within that people find better ways to work.
An experienced worker may come up with an improvement in their own trade.
It starts in their region and spreads as people copy it. Its benefit in a
region grows with how widely it has been taken up there.
"""
from . import config as C

# key: trade it comes from, what it does, plain description, and what it needs first
INVENTIONS = {
    "heavy_plow":   {"trade": "farmer", "effect": ("output", "farmer", 0.08), "needs": None,
                     "name": "a heavier plow that turns the soil deeper", "short": "heavy plow"},
    "crop_rotation": {"trade": "farmer", "effect": ("output", "farmer", 0.10), "needs": "heavy_plow",
                      "name": "rotating crops through three fields", "short": "three-field rotation"},
    "scythe":       {"trade": "farmer", "effect": ("output", "farmer", 0.05), "needs": None,
                     "name": "a long-bladed scythe for faster reaping", "short": "long scythe"},
    "drift_net":    {"trade": "fisher", "effect": ("output", "fisher", 0.10), "needs": None,
                     "name": "a drifting net that fishes while the crew rests", "short": "drift net"},
    "smoke_racks":  {"trade": "fisher", "effect": ("spoil", "fish", 0.5), "needs": None,
                     "name": "racks for smoking fish so it keeps for weeks", "short": "smoking rack"},
    "salt_curing":  {"trade": "herder", "effect": ("spoil", "meat", 0.5), "needs": None,
                     "name": "curing meat in salt so it keeps through winter", "short": "salt curing"},
    "sheepdogs":    {"trade": "herder", "effect": ("output", "herder", 0.08), "needs": None,
                     "name": "breeding dogs to work the flocks", "short": "sheepdog"},
    "two_man_saw":  {"trade": "woodcutter", "effect": ("output", "woodcutter", 0.12), "needs": None,
                     "name": "a two-man saw for felling trees", "short": "two-man saw"},
    "iron_wedges":  {"trade": "quarrier", "effect": ("output", "quarrier", 0.12), "needs": None,
                     "name": "iron wedges for splitting stone", "short": "iron wedge"},
    "shoring":      {"trade": "miner", "effect": ("safety", "miner", 0.5), "needs": None,
                     "name": "timber shoring to keep mine roofs from falling", "short": "mine shoring"},
    "bellows":      {"trade": "smith", "effect": ("output", "smith", 0.15), "needs": None,
                     "name": "great leather bellows for a hotter forge", "short": "great bellows"},
    "treadle_loom": {"trade": "weaver", "effect": ("output", "weaver", 0.2), "needs": None,
                     "name": "a loom worked by foot treadles", "short": "treadle loom"},
    "pulley_hoist": {"trade": "builder", "effect": ("output", "builder", 0.2), "needs": None,
                     "name": "a pulley hoist for raising beams", "short": "pulley hoist"},
    "remedies":     {"trade": None, "effect": ("health", "child", 0.85), "needs": None,
                     "name": "herbal remedies that ease childhood fevers", "short": "fever remedy"},
}

BASE_CHANCE = 0.000012  # per experienced worker per day, before personality


def ensure(w):
    if not hasattr(w, "inventions") or w.inventions is None:
        w.inventions = {}
    return w.inventions


def daily(w, log):
    inv = ensure(w)
    rng = w.rng
    reward = w.gov.get("invention_reward")
    boost = 1.5 if reward else 1.0
    open_by_trade = {}
    for key, spec in INVENTIONS.items():
        if key in inv:
            continue
        if spec["needs"] and spec["needs"] not in inv:
            continue
        open_by_trade.setdefault(spec["trade"], []).append(key)
    if not open_by_trade:
        return
    for p in w.people.values():
        if not p.job:
            continue
        exp = p.skills.get(p.job, 0)
        if exp < 2 * C.DAYS_PER_YEAR:
            continue
        options = open_by_trade.get(p.job, []) + (open_by_trade.get(None, []) if rng.random() < 0.15 else [])
        if not options:
            continue
        chance = BASE_CHANCE * boost * (0.5 + p.traits["ambition"]) * (0.5 + p.traits["diligence"])
        if rng.random() < chance:
            _invent(w, log, p, rng.choice(options))
            return   # at most one a day


def _invent(w, log, p, key):
    from . import language
    spec = INVENTIONS[key]
    w.inventions[key] = {"inventor": p.id, "inventor_name": p.name, "day": w.day, "region": p.region,
                         "adoption": {r: (0.25 if r == p.region else 0.0) for r in w.regions}}
    p.reputation = min(1.0, p.reputation + 0.2)
    from .model import note
    note(p, w.day, f"came up with {spec['name']}")
    town = w.regions[p.region].town
    job = p.job or "worker"
    log.add(w.day, "invention", f"{p.name}, a {job} of {town}, has come up with {spec['name']}.",
            region=p.region, importance=4, people=[p.id], invention=key)
    reward = w.gov.get("invention_reward")
    if reward and w.treasury >= reward["coins"]:
        w.treasury -= reward["coins"]
        w.count("treasury_out", reward["coins"])
        w.households[p.household].coins += reward["coins"]
        log.add(w.day, "invention_reward", f"{p.name} was paid the president's reward of {reward['coins']:.0f} "
                "coins for the invention.", region=p.region, importance=2, people=[p.id])
    language.coin(w, log, key, spec["short"], p.region, person=p, invention=True)
    w.count("inventions")


def weekly(w, log):
    """Inventions spread as neighbors copy one another."""
    for key, rec in ensure(w).items():
        ad = rec["adoption"]
        if all(v >= 0.95 for v in ad.values()):
            continue
        new = {}
        for r in w.regions:
            a = ad.get(r, 0.0)
            near = max((ad.get(n, 0.0) for n in C.NEIGHBORS[r]), default=0.0)
            a += 0.05 * a * (1 - a) + 0.012 * near * (1 - a)
            new[r] = min(1.0, a)
        rec["adoption"] = new
        if not rec.get("widespread") and sum(new.values()) / len(new) >= 0.6:
            rec["widespread"] = True
            log.add(w.day, "invention_spread", f"{INVENTIONS[key]['name'].capitalize()}, first devised by "
                    f"{rec['inventor_name']}, is now in use across most of the nation.", importance=3,
                    invention=key)


def multiplier(w, region, kind, target):
    """Combined effect of inventions of one kind ('output', 'spoil', 'safety', 'health') on a target."""
    m = 1.0
    for key, rec in (getattr(w, "inventions", None) or {}).items():
        ekind, etarget, amount = INVENTIONS[key]["effect"]
        if ekind != kind or etarget != target:
            continue
        a = rec["adoption"].get(region, 0.0)
        if kind == "output":
            m *= 1 + amount * a
        else:   # factors below 1 that reduce spoilage, accidents or illness
            m *= 1 - (1 - amount) * a
    return m
