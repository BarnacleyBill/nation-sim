"""How people feel and the choices they make.

Every person has needs (food, shelter, work, family, friends, standing,
faith). Their satisfaction is a weighted mix of those needs, with the
weights shaped by personality. When a choice comes up -- change jobs,
move, court someone -- they pick whatever they expect will raise their
satisfaction the most.
"""
import math

from . import config as C
from .economy import (is_child, food_need, food_stock, resource_mult, season_mean,
                      skill_mult, labor_mult, house_price, labor_rate, job_counts, producer_counts, sellable_share,
                      builder_premium)
from .model import Household


# ---------------------------------------------------------------- needs
def weights_for(p):
    t = p.traits
    w = dict(C.BASE_WEIGHTS)
    w["standing"] *= 0.5 + t["ambition"] + 0.5 * t["greed"]
    w["work"] *= 0.7 + 0.6 * t["ambition"]
    w["social"] *= 0.5 + t["sociability"]
    w["family"] *= 0.6 + 0.8 * t["warmth"]
    w["faith"] *= 0.3 + 1.5 * t["piety"]
    return w


def update_needs(w):
    day = w.day
    incomes = sorted(p.income_ema for p in w.people.values() if p.job and p.income_ema > 0)
    median = incomes[len(incomes) // 2] if incomes else 1.0
    # wealth rank within each region (coins per household member, plus owning a house)
    wealth = {}
    for h in w.households.values():
        if h.members:
            wealth[h.id] = h.coins / len(h.members) + (house_price(w) / 6 if h.house else 0)
    rank = {}
    for key in w.regions:
        hs = sorted((h for h in w.households.values() if h.region == key and h.members),
                    key=lambda h: wealth[h.id])
        for i, h in enumerate(hs):
            rank[h.id] = (i + 0.5) / len(hs)
    kin_housed = {}
    for h in w.households.values():
        F = food_need(w, h) or 1
        days_food = food_stock(h) / F
        if h.house is None:
            kin_housed[h.id] = any(k.house and k.region == h.region for k in _kin(w, h))
        for m in h.members:
            p = w.people[m]
            age = p.age(day)
            n = p.needs
            n["food"] = 0.75 * p.fed + 0.25 * min(1.0, days_food / 20)
            if h.house:
                shelter = 0.8
            else:
                shelter = 0.45 if kin_housed.get(h.id) else 0.1
            n["shelter"] = shelter + (0.2 if p.clothing > 0 else 0.0)
            if age < C.WORK_AGE:
                n["work"] = 0.75
            elif age >= C.RETIRE_AGE:
                n["work"] = 0.7
            elif not p.job:
                n["work"] = 0.15
            else:
                n["work"] = 0.35 + 0.65 * min(1.0, p.income_ema / median)
            n["family"] = _family_need(w, p, age)
            pos = sorted((a for a in p.friends.values() if a > 0), reverse=True)[:4]
            neg = sum(1 for a in p.friends.values() if a < -0.4)
            n["social"] = max(0.0, min(1.0, sum(pos) / 2.4 - 0.08 * neg))
            n["standing"] = 0.7 * rank.get(h.id, 0.5) + 0.3 * p.reputation
            n["faith"] = 0.7   # religion arrives in a later stage
            wts = weights_for(p)
            p.satisfaction = sum(wts[k] * n[k] for k in C.NEEDS) / sum(wts.values())
            p.mood += (p.satisfaction - p.mood) * 0.03


def _family_need(w, p, age):
    if age < C.ADULT_AGE:
        parents_home = any(w.people.get(x) and w.people[x].household == p.household
                           for x in (p.mother, p.father))
        return 0.85 if parents_home else 0.5
    living_kids = sum(1 for c in p.children if c in w.people)
    if p.spouse in w.people:
        return min(1.0, 0.6 + 0.12 * living_kids)
    if p.widowed:
        return min(0.8, 0.35 + 0.08 * living_kids)
    if age < 24:
        return 0.55
    return max(0.25, 0.45 - 0.01 * (age - 24)) + min(0.3, 0.08 * living_kids)


def _kin(w, h):
    from .economy import kin_households
    return kin_households(w, h)


# ---------------------------------------------------------------- friendship
def socialize(w):
    rng = w.rng
    by_region = {}
    by_job = {}
    for p in w.people.values():
        if p.age(w.day) >= 6:
            by_region.setdefault(p.region, []).append(p)
            if p.job:
                by_job.setdefault((p.region, p.job), []).append(p)
    for p in list(w.people.values()):
        group = by_region.get(p.region)
        if not group or p.age(w.day) < 6:
            continue
        for _ in range(2):
            roll = rng.random()
            other = None
            if roll < 0.3 and p.friends:
                other = w.people.get(int(rng.choice(list(p.friends))))
            elif roll < 0.6 and p.job and len(by_job.get((p.region, p.job), [])) > 1:
                other = rng.choice(by_job[(p.region, p.job)])
            if other is None or other.region != p.region:
                other = rng.choice(group)
            if other.id == p.id:
                continue
            _meet(w, p, other)
    # feelings fade slowly without contact
    if w.day % 7 == 0:
        for p in w.people.values():
            for k in list(p.friends):
                p.friends[k] *= 0.985
                if abs(p.friends[k]) < 0.02 or int(k) not in w.people:
                    del p.friends[k]


def _meet(w, a, b):
    rng = w.rng
    ta, tb = a.traits, b.traits
    compat = (0.55 - 0.5 * abs(ta["sociability"] - tb["sociability"])
              - 0.4 * abs(ta["greed"] - tb["greed"]) - 0.3 * abs(ta["piety"] - tb["piety"])
              + 0.3 * (ta["warmth"] + tb["warmth"]) / 2)
    delta = 0.035 * (compat + rng.gauss(0, 0.45))
    for x, y in ((a, b), (b, a)):
        k = str(y.id)
        cur = x.friends.get(k, 0.0)
        x.friends[k] = max(-1.0, min(1.0, cur + delta * (1.0 - abs(cur) * 0.5)))
        if len(x.friends) > C.MAX_FRIENDS:
            weakest = min(x.friends, key=lambda f: abs(x.friends[f]) if int(f) != x.spouse else 9)
            del x.friends[weakest]


# ---------------------------------------------------------------- jobs
def job_value(w, p, job, region_key, counts, producers, extra=1):
    """Expected coins per day from a job, averaged over the year.

    Counts what the household would eat itself, plus a fair share of what
    the rest of the nation wants to buy, split among everyone making it.
    """
    region = w.regions[region_key]
    spec = C.JOBS[job]
    if job == "builder":
        targeted = {x.for_household for x in w.projects.values()}
        builders = counts.get((region_key, "builder"), 0) + extra - 1
        open_projects = sum(1 for x in w.projects.values() if x.region == region_key and x.builder is None)
        demand = sum(1 for h in w.households.values()
                     if h.region == region_key and h.house is None and h.members and h.id not in targeted
                     and h.coins >= C.HOUSE_TIMBER * w.prices["timber"])
        if demand + open_projects <= builders:
            return 0.1
        return labor_rate(w) * builder_premium(w, region_key) * skill_mult(p, job)
    rm = resource_mult(region, job, counts.get((region_key, job), 0) + extra)
    if rm <= 0:
        return 0.0
    mult = season_mean(job) * rm * skill_mult(p, job) * labor_mult(p, w.day) * C.TOOL_BONUS
    hh = w.households[p.household]
    n_workers = max(1, sum(1 for m in hh.members if w.people[m].job) + (extra if p.job is None else 0))
    food_share = food_need(w, hh) / n_workers
    value = 0.0
    for g, q in spec["outputs"].items():
        made = q * mult
        price = 0.25 * w.prices[g] + 0.75 * w.avg_prices[g]
        own = min(made, food_share) if g in C.FOODS else 0.0
        market = w.demand.get(g, 0.0) / (producers.get(g, 0) + extra)
        value += price * (own + min(made - own, market))
    for g, q in spec.get("inputs", {}).items():
        value -= q * mult * (0.25 * w.prices[g] + 0.75 * w.avg_prices[g])
    sub = w.gov.get("subsidies", {}).get(job)
    if sub:
        value += sub["rate"]
    return value


def choose_jobs(w, log):
    rng = w.rng
    counts = job_counts(w)
    producers = producer_counts(w)
    n_workers = sum(counts.values())
    switches_left = max(2, int(n_workers * 0.006))
    people = list(w.people.values())
    rng.shuffle(people)
    for p in people:
        age = p.age(w.day)
        if age < C.WORK_AGE:
            continue
        if age >= C.RETIRE_AGE:
            if p.job:
                log.add(w.day, "retired", f"{p.name} has retired from work as a {p.job}.",
                        region=p.region, importance=1, people=[p.id], job=p.job)
                counts[(p.region, p.job)] -= 1
                p.job = None
            continue
        if p.job and (rng.random() > 1 / 25 or switches_left <= 0):
            continue
        if age < C.ADULT_AGE and not p.job:
            # teenagers help with the family trade
            hh = w.households[p.household]
            trades = [w.people[m].job for m in hh.members if w.people[m].job]
            if trades:
                p.job = max(set(trades), key=trades.count)
                p.job_since = w.day
                counts[(p.region, p.job)] = counts.get((p.region, p.job), 0) + 1
                continue
        options = {}
        for job in C.JOBS:
            extra = 0 if job == p.job else 1
            v = job_value(w, p, job, p.region, counts, producers, extra)
            if v <= 0:
                continue
            options[job] = v * p.job_pref.get(job, 1.0)
        if not options:
            continue
        current = options.get(p.job, 0.0) * 1.2 if p.job else 0.0
        best = max(options, key=options.get)
        if best != p.job and options[best] > current * (1.05 + 0.1 * (1 - p.traits["boldness"])):
            old = p.job
            if old:
                counts[(p.region, old)] -= 1
                for g in C.JOBS[old]["outputs"]:
                    producers[g] -= 1
            counts[(p.region, best)] = counts.get((p.region, best), 0) + 1
            for g in C.JOBS[best]["outputs"]:
                producers[g] = producers.get(g, 0) + 1
            p.job = best
            p.job_since = w.day
            p.income_ema = 0.6 * p.income_ema
            switches_left -= 1
            if old:
                log.add(w.day, "job_change", f"{p.name} gave up work as a {old} to become a {best}.",
                        region=p.region, importance=1, people=[p.id], old=old, new=best)
            else:
                log.add(w.day, "first_job", f"{p.name} has started work as a {best}.",
                        region=p.region, importance=1, people=[p.id], job=best)
            w.count("job_changes")


# ---------------------------------------------------------------- moving
def vacant_house(w, region):
    for house in w.houses.values():
        if house.region == region and house.household is None:
            return house
    return None


def new_household(w, region, members, coins=0.0, inv=None):
    hid = w.new_id()
    h = Household(id=hid, region=region, members=[], house=None, coins=coins,
                  inv=inv or {g: 0.0 for g in C.GOODS}, founded=w.day, homeless_since=w.day)
    w.households[hid] = h
    for m in members:
        move_person(w, w.people[m], h)
    house = vacant_house(w, region)
    if house:
        house.household = hid
        h.house = house.id
        h.homeless_since = None
    return h


def move_person(w, p, new_hh):
    old = w.households.get(p.household)
    if old and p.id in old.members:
        old.members.remove(p.id)
        if not old.members:
            dissolve_household(w, old, heirs=[new_hh])
    new_hh.members.append(p.id)
    p.household = new_hh.id
    p.region = new_hh.region


def dissolve_household(w, h, heirs=()):
    """An empty household hands on its money and stores, and frees its house."""
    heirs = [x for x in heirs if x.id != h.id and x.members]
    if heirs:
        share = 1.0 / len(heirs)
        for x in heirs:
            x.coins += h.coins * share
            for g, q in h.inv.items():
                x.inv[g] = x.inv.get(g, 0.0) + q * share
    else:
        w.treasury += h.coins
    if h.house and h.house in w.houses:
        w.houses[h.house].household = None
    for proj in list(w.projects.values()):
        if proj.for_household == h.id:
            proj.for_household = None
    del w.households[h.id]


def _region_score(w, p, h, region_key, counts, producers):
    best = max((job_value(w, p, j, region_key, counts, producers,
                          0 if (region_key == p.region and j == p.job) else 1)
                for j in C.JOBS), default=0.0)
    score = best / max(0.5, labor_rate(w))
    if region_key == h.region:
        score += 0.25 + (0.4 if h.house else 0.0)
    else:
        score += 0.3 if vacant_house(w, region_key) else -0.2
    ties = 0
    for m in h.members:
        for fid, aff in w.people[m].friends.items():
            f = w.people.get(int(fid))
            if f and f.region == region_key and aff > 0.3:
                ties += 1
    return score + min(0.4, 0.05 * ties)


def consider_moves(w, log):
    rng = w.rng
    counts = job_counts(w)
    producers = producer_counts(w)
    for h in list(w.households.values()):
        if not h.members or h.id not in w.households:
            continue
        adults = [w.people[m] for m in h.members if w.people[m].age(w.day) >= C.ADULT_AGE]
        if not adults:
            continue
        head = max(adults, key=lambda a: a.traits["boldness"])
        if rng.random() > 1 / 90:
            continue
        here = _region_score(w, head, h, h.region, counts, producers)
        options = {r: _region_score(w, head, h, r, counts, producers) for r in C.NEIGHBORS[h.region]}
        best = max(options, key=options.get)
        if options[best] > here + 0.25 * (1.2 - head.traits["boldness"]):
            _move_household(w, log, h, best)

    # grown children leaving home to seek their fortune
    for p in list(w.people.values()):
        if p.spouse or p.age(w.day) < 18 or p.age(w.day) > 35 or rng.random() > 1 / 150:
            continue
        h = w.households[p.household]
        parents_home = any(w.people.get(x) and w.people[x].household == h.id for x in (p.mother, p.father))
        if not parents_home:
            continue
        here = _region_score(w, p, h, h.region, counts, producers) - 0.25
        options = {r: _region_score(w, p, h, r, counts, producers) for r in C.NEIGHBORS[h.region]}
        best = max(options, key=options.get)
        if options[best] > here + 0.3 * (1.2 - p.traits["boldness"]):
            share = h.coins / (len(h.members) + 1)
            h.coins -= share
            old_region = h.region
            nh = new_household(w, best, [p.id], coins=share)
            log.add(w.day, "left_home",
                    f"{p.name}, {int(p.age(w.day))}, left the family home in {w.regions[old_region].town} "
                    f"to seek work in {w.regions[best].name}.",
                    region=best, importance=1, people=[p.id], origin=old_region)
            w.count("migrations")


def _move_household(w, log, h, dest):
    origin = h.region
    if h.house and h.house in w.houses:
        w.houses[h.house].household = None
    h.house = None
    h.region = dest
    h.homeless_since = w.day
    for m in h.members:
        w.people[m].region = dest
    house = vacant_house(w, dest)
    if house:
        house.household = h.id
        h.house = house.id
        h.homeless_since = None
    for proj in list(w.projects.values()):
        if proj.for_household == h.id:
            proj.for_household = None
    head = w.people[h.members[0]]
    log.add(w.day, "household_moved",
            f"The {head.family} household ({len(h.members)} people) moved from {w.regions[origin].name} "
            f"to {w.regions[dest].name}.",
            region=dest, importance=2, people=list(h.members), origin=origin,
            housed=h.house is not None)
    w.count("migrations")


# ---------------------------------------------------------------- courtship
def _ancestors(w, pid, depth=2):
    out = set()
    frontier = [pid]
    for _ in range(depth):
        nxt = []
        for x in frontier:
            q = w.people.get(x) or None
            if q is None:
                d = w.dead.get(x)
                parents = (d.get("mother"), d.get("father")) if d else ()
            else:
                parents = (q.mother, q.father)
            for par in parents:
                if par:
                    out.add(par)
                    nxt.append(par)
        frontier = nxt
    return out


def too_close(w, a, b):
    if a.id in (b.mother, b.father) or b.id in (a.mother, a.father):
        return True
    return bool(_ancestors(w, a.id) & _ancestors(w, b.id))


def courtship(w, log):
    rng = w.rng
    singles = {}
    for p in w.people.values():
        age = p.age(w.day)
        if p.spouse is None and C.ADULT_AGE <= age <= 58:
            singles.setdefault((p.region, p.sex), []).append(p)
    married_today = set()
    for p in list(w.people.values()):
        if p.spouse is not None or p.id in married_today or rng.random() > 1 / 6:
            continue
        age = p.age(w.day)
        if not (C.ADULT_AGE <= age <= 58):
            continue
        other_sex = "f" if p.sex == "m" else "m"
        pool = [c for c in singles.get((p.region, other_sex), [])
                if c.spouse is None and c.id not in married_today
                and abs(c.age(w.day) - age) <= (10 if age < 30 else 15)]
        if not pool:
            continue
        known = [c for c in pool if p.friends.get(str(c.id), 0) > 0.15]
        if not known or rng.random() < 0.3:
            c = rng.choice(pool)
            _meet(w, p, c)   # getting acquainted
            continue
        c = max(known, key=lambda x: p.friends[str(x.id)])
        a_ab = p.friends.get(str(c.id), 0)
        a_ba = c.friends.get(str(p.id), 0)
        if a_ab > 0.45 and a_ba > 0.4 and not too_close(w, p, c):
            # the other person weighs the match
            accept = 0.4 + 0.4 * a_ba + 0.2 * p.reputation - 0.15 * c.traits["greed"] * (1 - _wealth01(w, p))
            if rng.random() < accept:
                marry(w, log, p, c)
                married_today.update((p.id, c.id))
        else:
            _meet(w, p, c)


def _wealth01(w, p):
    h = w.households[p.household]
    return min(1.0, h.coins / max(1, len(h.members)) / 120)


def marry(w, log, a, b):
    a.spouse, b.spouse = b.id, a.id
    a.widowed = b.widowed = False
    a.friends[str(b.id)] = max(a.friends.get(str(b.id), 0), 0.7)
    b.friends[str(a.id)] = max(b.friends.get(str(a.id), 0), 0.7)
    ha, hb = w.households[a.household], w.households[b.household]

    def heads_own_home(p, h):
        others = [w.people[m] for m in h.members if m != p.id]
        return h.house is not None and all(o.age(w.day) < C.ADULT_AGE or o.id in p.children for o in others)

    if heads_own_home(a, ha):
        move_person(w, b, ha)
        home = ha
    elif heads_own_home(b, hb):
        move_person(w, a, hb)
        home = hb
    else:
        dowry = 0.0
        for p, h in ((a, ha), (b, hb)):
            give = h.coins / (len(h.members) + 1)
            h.coins -= give
            dowry += give
        home = new_household(w, a.region, [a.id, b.id], coins=dowry)
        F = food_need(w, home)
        for h in (ha, hb):
            if h.id in w.households:
                share = min(h.inv["grain"] * 0.15, 10 * F)
                h.inv["grain"] -= share
                home.inv["grain"] += share
    where = w.regions[home.region].town
    note = "" if home.house else " They have no house of their own yet."
    log.add(w.day, "marriage", f"{a.name} and {b.name} were married in {where}.{note}",
            region=home.region, importance=2, people=[a.id, b.id], housed=home.house is not None)
    w.count("marriages")
