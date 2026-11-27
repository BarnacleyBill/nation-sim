"""Work, trade and eating.

Each day: people work and produce goods into their household's stores,
households trade at the nation's market, then everyone eats. Coins only
change hands, never appear or vanish, so the money supply stays fixed
until the government starts minting.
"""
import math

from . import config as C
from . import inventions
from .calendar import season

OUTDOOR = {"farmer", "fisher", "herder", "woodcutter", "quarrier", "builder"}


# ---------------------------------------------------------------- helpers
def is_child(p, day):
    return p.age(day) < C.WORK_AGE


def food_need(w, hh):
    return sum(C.FOOD_PER_CHILD if is_child(w.people[m], w.day) else C.FOOD_PER_ADULT
               for m in hh.members)


def food_stock(hh):
    return sum(hh.inv.get(g, 0.0) for g in C.FOODS)


def workers_of(w, hh):
    return [w.people[m] for m in hh.members if w.people[m].job]


def resource_mult(region, job, n_workers):
    res = C.JOBS[job]["resource"]
    if res is None:
        return 1.0
    r = region.resources.get(res, 0.0)
    if r <= 0:
        return 0.0
    cap = r * C.WORKERS_PER_RESOURCE
    crowd = 1.0 if n_workers <= cap else (cap / n_workers) ** 0.7
    return (0.6 + 0.4 * r) * crowd


def weather_mult(region, job):
    m = 1.0
    for eff in region.effects.values():
        mult = eff["mult"]
        if job in mult:
            m *= mult[job]
        elif "outdoor" in mult and job in OUTDOOR:
            m *= mult["outdoor"]
        elif "all" in mult:
            m *= mult["all"]
    return m


def skill_mult(p, job):
    return 0.75 + 0.5 * min(1.0, p.skills.get(job, 0) / 730)


def labor_mult(p, day):
    age = p.age(day)
    if age < C.ADULT_AGE:
        a = 0.5
    elif age >= C.ELDER_AGE:
        a = 0.7
    else:
        a = 1.0
    return a * (0.85 + 0.3 * p.traits["diligence"])


def season_mean(job):
    curve = C.SEASON_CURVES[C.JOBS[job]["season"]]
    return sum(curve.values()) / len(curve)


def sellable_share(w, hh, good, made):
    """Share of what was made that is actually worth something: either it sells,
    or (for food) the household eats it itself."""
    st = w.sell_through.get(good, 1.0)
    if good in C.FOODS and made > 0:
        n = max(1, len(workers_of(w, hh)))
        own = min(1.0, food_need(w, hh) / n / made)
        return max(st, own)
    return st


def labor_rate(w):
    """What a day of ordinary work is currently worth, in coins."""
    incomes = sorted(p.income_ema for p in w.people.values() if p.job and p.income_ema > 0)
    if not incomes:
        return 2.0
    return max(0.5, incomes[len(incomes) // 2])


def house_price(w, region=None):
    premium = builder_premium(w, region) if region else 1.3
    return (C.HOUSE_TIMBER * w.prices["timber"] + C.HOUSE_STONE * w.prices["stone"]
            + C.HOUSE_LABOR_DAYS * labor_rate(w) * premium)


def producer_counts(w):
    """How many workers in the whole nation make each good."""
    out = {}
    for p in w.people.values():
        if p.job:
            for g in C.JOBS[p.job]["outputs"]:
                out[g] = out.get(g, 0) + 1
    return out


def facility_bonus(w, region, job):
    m = 1.0
    for f in w.facilities.values():
        if f["status"] != "done" or f["region"] != region:
            continue
        if f["kind"] == "mill" and job == "farmer":
            m *= 1.12
        elif f["kind"] == "road" and job in ("farmer", "fisher", "herder", "woodcutter", "quarrier", "miner"):
            m *= 1.04
    return m


def has_facility(w, region, kind, include_building=True):
    return any(f["region"] == region and f["kind"] == kind
               and (include_building or f["status"] == "done")
               for f in w.facilities.values())


def customary_price(w, good):
    """The price people think is normal, which rises as more money circulates."""
    return C.START_PRICES[good] * w.gov.get("price_level", 1.0)


def job_counts(w):
    counts = {}
    for p in w.people.values():
        if p.job:
            k = (p.region, p.job)
            counts[k] = counts.get(k, 0) + 1
    return counts


# ---------------------------------------------------------------- production
def produce(w, log):
    day = w.day
    sname = season(day)
    counts = job_counts(w)
    for hh in w.households.values():
        region = w.regions[hh.region]
        for p in workers_of(w, hh):
            job = p.job
            if job == "builder":
                continue  # builders work on projects, see build()
            spec = C.JOBS[job]
            mult = (C.SEASON_CURVES[spec["season"]][sname]
                    * resource_mult(region, job, counts.get((hh.region, job), 1))
                    * weather_mult(region, job)
                    * facility_bonus(w, hh.region, job)
                    * inventions.multiplier(w, hh.region, "output", job)
                    * skill_mult(p, job) * labor_mult(p, day))
            if _glutted(w, hh, spec):
                # nobody is buying: work slackens and the time goes to rest
                mult *= 0.25
            if hh.tool_days >= 1:
                mult *= C.TOOL_BONUS
                hh.tool_days -= 1
            # workshop trades need raw materials on hand
            frac = 1.0
            inputs = spec.get("inputs", {})
            for g, q in inputs.items():
                need = q * mult
                if need > 0:
                    frac = min(frac, hh.inv.get(g, 0.0) / need)
            frac = max(0.0, min(1.0, frac))
            value = 0.0
            for g, q in inputs.items():
                used = q * mult * frac
                hh.inv[g] -= used
                value -= used * w.prices[g]
            for g, q in spec["outputs"].items():
                made = q * mult * frac
                hh.inv[g] = hh.inv.get(g, 0.0) + made
                value += made * w.prices[g] * sellable_share(w, hh, g, made)
            p.income_ema = 0.97 * p.income_ema + 0.03 * value
            p.skills[job] = p.skills.get(job, 0) + 1


def _glutted(w, hh, spec):
    """True when the household's stores of everything this job makes are already full."""
    outs = spec["outputs"]
    if not outs:
        return False
    F = food_need(w, hh)
    for g, q in outs.items():
        if g == "grain":
            cap = 200 * F + 60 * q
        elif g in ("fish", "meat"):
            cap = 3 * F + 4 * q
        else:
            cap = 25 * q
        if hh.inv.get(g, 0.0) < cap:
            return False
    return True


def builder_premium(w, region):
    """Builders charge more when many families are waiting for a house."""
    backlog = sum(1 for h in w.households.values()
                  if h.region == region and h.house is None and h.members)
    return 1.3 + 0.1 * min(10, backlog)


# ---------------------------------------------------------------- building
def build(w, log):
    day = w.day
    for p in list(w.people.values()):
        if p.job != "builder":
            continue
        hh = w.households[p.household]
        proj = next((x for x in w.projects.values() if x.builder == p.id), None)
        if proj is None:
            proj = next((x for x in w.projects.values()
                         if x.region == p.region and x.builder is None), None)
            if proj:
                proj.builder = p.id
        if proj is None:
            proj = _start_project(w, p, hh)
        if proj is None:
            p.income_ema *= 0.97   # idle
            continue
        # move materials from the builder's stores onto the site
        for g, total in (("timber", C.HOUSE_TIMBER), ("stone", C.HOUSE_STONE)):
            have = getattr(proj, g)
            moved = min(hh.inv.get(g, 0.0), total - have)
            if moved > 0:
                hh.inv[g] -= moved
                setattr(proj, g, have + moved)
        mat = min(proj.timber / C.HOUSE_TIMBER, proj.stone / C.HOUSE_STONE)
        allowed = C.HOUSE_LABOR_DAYS * mat
        work = (skill_mult(p, "builder") * labor_mult(p, day) * weather_mult(w.regions[p.region], "builder")
                * inventions.multiplier(w, p.region, "output", "builder"))
        if proj.progress < allowed:
            proj.progress = min(allowed, proj.progress + work)
            p.skills["builder"] = p.skills.get("builder", 0) + 1
        p.income_ema = (0.97 * p.income_ema
                        + 0.03 * labor_rate(w) * builder_premium(w, p.region) * min(1.0, work))
        if proj.progress >= C.HOUSE_LABOR_DAYS - 1e-6 and mat >= 1 - 1e-6:
            _finish_project(w, log, proj, p, hh)


def _start_project(w, builder, bhh):
    price = house_price(w)
    deposit = C.HOUSE_TIMBER * w.prices["timber"] + C.HOUSE_STONE * w.prices["stone"]
    targeted = {x.for_household for x in w.projects.values()}
    waiting = [h for h in w.households.values()
               if h.region == builder.region and h.house is None and h.id not in targeted
               and h.coins >= deposit and h.members]
    if not waiting:
        return None
    waiting.sort(key=lambda h: h.homeless_since or 0)
    client = waiting[0]
    client.coins -= deposit
    bhh.coins += deposit
    pid = w.new_id()
    from .model import Project
    proj = Project(id=pid, region=builder.region, builder=builder.id,
                   for_household=client.id, started=w.day)
    w.projects[pid] = proj
    return proj


def _finish_project(w, log, proj, builder, bhh):
    from .model import House
    hid = w.new_id()
    house = House(id=hid, region=proj.region, built_day=w.day)
    w.houses[hid] = house
    client = w.households.get(proj.for_household)
    if not client or client.house is not None or client.region != proj.region or not client.members:
        client = next((h for h in w.households.values()
                       if h.region == proj.region and h.house is None and h.members), None)
    price = house_price(w, proj.region)
    paid_already = C.HOUSE_TIMBER * w.prices["timber"] + C.HOUSE_STONE * w.prices["stone"]
    if client:
        due = max(0.0, price - paid_already)
        pay = min(due, client.coins * 0.85)
        client.coins -= pay
        bhh.coins += pay
        house.household = client.id
        client.house = hid
        client.homeless_since = None
        head = w.people[client.members[0]]
        log.add(w.day, "house_built",
                f"{builder.name} finished a new house in {w.regions[proj.region].town} for the {head.family} household.",
                region=proj.region, importance=2, people=[builder.id, head.id], price=round(price, 1))
    else:
        log.add(w.day, "house_built",
                f"{builder.name} finished a new house in {w.regions[proj.region].town}; it stands empty.",
                region=proj.region, importance=1, people=[builder.id])
    w.count("houses_built")
    del w.projects[proj.id]


# ---------------------------------------------------------------- market
def willing_share(w, good):
    """Sellers hold back when the price is below the customary price.
    Perishable goods must be sold soon, so their sellers hold back less."""
    ratio = w.prices[good] / customary_price(w, good)
    power = 0.7 if good in ("fish", "meat") else 1.5
    return min(1.0, max(0.05, ratio ** power))


def _clear(w, good, offers, requests):
    share = willing_share(w, good)
    if share < 1.0:
        offers = {k: v * share for k, v in offers.items()}
    total_o = sum(offers.values())
    total_r = sum(requests.values())
    traded = min(total_o, total_r)
    price = w.prices[good]
    tax = w.gov.get("sales_tax", 0.0)
    tax_week = w.gov.setdefault("tax_week", {})
    if traded > 1e-9:
        fo, fr = traded / total_o, traded / total_r
        for hid, q in offers.items():
            hh = w.households[hid]
            sold = q * fo
            hh.inv[good] -= sold
            hh.coins += sold * price * (1 - tax)
            if tax:
                w.treasury += sold * price * tax
                tax_week[str(hid)] = tax_week.get(str(hid), 0.0) + sold * price * tax
        for hid, q in requests.items():
            hh = w.households[hid]
            got = q * fr
            hh.inv[good] = hh.inv.get(good, 0.0) + got
            hh.coins -= got * price
    # prices drift toward balancing supply and demand
    if total_o < 1e-9 and total_r < 1e-9:
        price += (w.avg_prices[good] - price) * 0.01
    else:
        ratio = (total_r + 0.5) / (total_o + 0.5)
        price *= min(1.03, max(0.97, ratio ** 0.08))
    base = customary_price(w, good)
    price = min(base * C.PRICE_CEILING, max(base * C.PRICE_FLOOR, price))
    cap = w.gov.get("price_cap")
    if cap and cap["good"] == good:
        price = min(price, cap["max"])
    w.prices[good] = price
    w.last_trade[good] = traded
    w.demand[good] = 0.97 * w.demand.get(good, total_r) + 0.03 * total_r
    st = traded / total_o if total_o > 1e-9 else 1.0
    w.sell_through[good] = 0.9 * w.sell_through.get(good, 1.0) + 0.1 * st
    return traded


def target_food_days(w):
    """Households store more food when it is cheap and less when it is dear."""
    cheapness = min(w.prices[g] / w.avg_prices[g] for g in C.FOODS)
    return min(160.0, max(10.0, 28.0 * (1.0 / cheapness) ** 1.5))


def market(w, log):
    hhs = [h for h in w.households.values() if h.members]
    need = {h.id: food_need(w, h) for h in hhs}
    target = target_food_days(w)
    spent = {h.id: 0.0 for h in hhs}

    # food, cheapest first
    for g in sorted(C.FOODS, key=lambda x: w.prices[x]):
        price = w.prices[g]
        offers, requests = {}, {}
        for h in hhs:
            F = need[h.id]
            stock = food_stock(h)
            perish = h.inv["fish"] + h.inv["meat"]
            if g in ("fish", "meat"):
                keep = 2 * F
            else:
                keep = max(0.0, target * F - perish)
            surplus = h.inv[g] - keep
            if surplus > 0.01:
                offers[h.id] = surplus
                continue
            deficit = max(0.0, target * F - stock)
            if g in ("fish", "meat"):
                deficit = min(deficit, max(0.0, 4 * F - perish))
            share = 0.95 if stock < 5 * F else 0.6
            budget = max(0.0, h.coins * share - spent[h.id])
            q = min(deficit, budget / price)
            if q > 0.01:
                requests[h.id] = q
                spent[h.id] += q * price
        _clear(w, g, offers, requests)

    # raw materials, tools and cloth
    keep = {h.id: _material_keep(w, h) for h in hhs}
    for g in ("wool", "timber", "stone", "ore"):
        price = w.prices[g]
        offers, requests = {}, {}
        for h in hhs:
            k = keep[h.id].get(g, 0.0)
            have = h.inv.get(g, 0.0)
            if have > k + 0.01:
                offers[h.id] = have - k
            elif k > have + 0.01:
                q = min(k - have, max(0.0, h.coins * 0.5) / price)
                if q > 0.01:
                    requests[h.id] = q
        _clear(w, g, offers, requests)

    # tools: buy when the household's tools are wearing out
    price = w.prices["tools"]
    offers, requests = {}, {}
    for h in hhs:
        n_work = len(workers_of(w, h))
        if h.inv.get("tools", 0) > 0.01:
            # smiths re-equip themselves first, then sell the rest
            if h.tool_days < n_work * 20 and h.inv["tools"] >= 1:
                h.inv["tools"] -= 1
                h.tool_days += C.TOOL_LIFE_DAYS
            if h.inv["tools"] > 0.01:
                offers[h.id] = h.inv["tools"]
            continue
        if n_work and h.tool_days < n_work * 20:
            want = math.ceil((n_work * 60 - h.tool_days) / C.TOOL_LIFE_DAYS)
            q = min(want, max(0.0, h.coins * 0.35) / price)
            if q > 0.05:
                requests[h.id] = q
    _clear(w, "tools", offers, requests)
    for hid in requests:
        h = w.households[hid]
        got = h.inv.get("tools", 0.0)
        h.tool_days += got * C.TOOL_LIFE_DAYS
        h.inv["tools"] = 0.0

    # cloth: replace worn-out clothes
    price = w.prices["cloth"]
    offers, requests = {}, {}
    ragged = {}
    for h in hhs:
        r = [w.people[m] for m in h.members if w.people[m].clothing < 25]
        ragged[h.id] = r
        have = h.inv.get("cloth", 0.0)
        if have - len(r) > 0.01:
            offers[h.id] = have - len(r)
        elif r:
            q = min(len(r) - have, max(0.0, h.coins * 0.3) / price)
            if q > 0.05:
                requests[h.id] = q
    _clear(w, "cloth", offers, requests)
    for h in hhs:
        for p in sorted(ragged[h.id], key=lambda x: x.clothing):
            if h.inv.get("cloth", 0.0) >= 1:
                h.inv["cloth"] -= 1
                p.clothing += C.CLOTHING_LIFE

    for g in C.GOODS:
        w.avg_prices[g] += (w.prices[g] - w.avg_prices[g]) / 120


def _material_keep(w, h):
    keep = {}
    for p in workers_of(w, h):
        for g, q in C.JOBS[p.job].get("inputs", {}).items():
            keep[g] = keep.get(g, 0.0) + q * 10
        if p.job == "builder":
            proj = next((x for x in w.projects.values() if x.builder == p.id), None)
            if proj:
                keep["timber"] = keep.get("timber", 0.0) + max(0.0, C.HOUSE_TIMBER - proj.timber)
                keep["stone"] = keep.get("stone", 0.0) + max(0.0, C.HOUSE_STONE - proj.stone)
    return keep


# ---------------------------------------------------------------- eating
def consume(w, log):
    for h in w.households.values():
        if not h.members:
            continue
        F = food_need(w, h)
        left = F
        for g in ("fish", "meat", "grain"):
            take = min(left, h.inv.get(g, 0.0))
            h.inv[g] -= take
            left -= take
        if left > 0:
            # with nothing in the larder, people forage, glean and snare what they can
            per_head = 0.12 if season(w.day) == "winter" else 0.3
            left = max(0.0, left - per_head * len(h.members))
        frac = 1.0 if F <= 0 else (F - left) / F
        for m in h.members:
            p = w.people[m]
            p.fed = 0.85 * p.fed + 0.15 * frac
            if frac < 0.6:
                p.hunger += 1
            else:
                p.hunger = max(0, p.hunger - 2)
            p.clothing = max(-1, p.clothing - 1)
        granary = has_facility(w, h.region, "granary", include_building=False)
        for g, rate in C.PERISHABLE.items():
            if g == "grain" and granary:
                rate *= 0.4
            rate *= inventions.multiplier(w, h.region, "spoil", g)
            h.inv[g] *= (1 - rate)
    _kin_support(w, log)


def kin_households(w, h):
    """Households of this household's parents, children, siblings and spouses."""
    out = set()
    for m in h.members:
        p = w.people[m]
        rel = [p.mother, p.father, p.spouse] + list(p.children)
        for parent_id in (p.mother, p.father):
            par = w.people.get(parent_id)
            if par:
                rel.extend(par.children)
        for r in rel:
            q = w.people.get(r)
            if q and q.household != h.id:
                out.add(q.household)
    return [w.households[x] for x in out if x in w.households]


def _kin_support(w, log):
    gp = w.prices["grain"]
    for h in w.households.values():
        if not h.members:
            continue
        F = food_need(w, h)
        if food_stock(h) >= 3 * F or h.coins >= 5 * F * gp:
            continue
        donors = kin_households(w, h)
        # good friends nearby help too
        for m in h.members:
            for fid, aff in w.people[m].friends.items():
                f = w.people.get(int(fid))
                if f and aff > 0.5 and f.region == h.region and f.household != h.id:
                    donors.append(w.households[f.household])
        for d in donors:
            adults = [w.people[x] for x in d.members if not is_child(w.people[x], w.day)]
            if not adults:
                continue
            warmth = sum(a.traits["warmth"] for a in adults) / len(adults)
            if w.rng.random() > warmth:
                continue
            dF = food_need(w, d)
            spare = d.inv["grain"] - 25 * dF
            if spare > 1:
                give = min(spare, 7 * F)
                d.inv["grain"] -= give
                h.inv["grain"] += give
                w.count("kin_help")
                break
            if d.coins > 80:
                give = min(40.0, d.coins * 0.1)
                d.coins -= give
                h.coins += give
                w.count("kin_help")
                break
