"""Founding the nation: a few hundred people at the very basics.

The nation starts already settled: families in houses, people working,
a little money, a first president. It starts on the first day of autumn
in Year 1, so the first harvest is coming in.
"""
import random

from . import config as C
from . import names
from .model import World, Person, Household, House, Region

START_DAY = 2 * C.DAYS_PER_SEASON   # first day of autumn, Year 1


def _traits(rng):
    return {t: round(min(1.0, max(0.0, rng.gauss(0.5, 0.18))), 2) for t in C.TRAITS}


def _job_prefs(rng):
    return {j: round(rng.uniform(0.85, 1.15), 2) for j in C.JOBS}


def _pick_job(rng, region_res):
    weights = {}
    for job, spec in C.JOBS.items():
        res = spec["resource"]
        if res is None:
            weights[job] = {"smith": 0.03, "weaver": 0.05, "builder": 0.04}[job]
        else:
            weights[job] = region_res.get(res, 0) * {"farmer": 0.45, "fisher": 0.25, "herder": 0.18,
                                                      "woodcutter": 0.08, "quarrier": 0.05,
                                                      "miner": 0.05}[job]
    jobs = [j for j in weights if weights[j] > 0]
    return rng.choices(jobs, weights=[weights[j] for j in jobs])[0]


def found_nation(seed):
    rng = random.Random(seed)
    ph = names.make_phonology(rng)
    pools = names.build_name_pools(ph, rng)
    nation_name = names.place_name(ph, rng)

    w = World(day=START_DAY, seed=seed, nation_name=nation_name, phonology=ph,
              name_pools=pools, regions={}, people={}, households={}, houses={},
              projects={}, prices=dict(C.START_PRICES), treasury=C.START_TREASURY)
    w.rng = rng
    w.avg_prices = dict(C.START_PRICES)
    w.week_start_prices = dict(C.START_PRICES)

    used_places = {nation_name}
    for key, spec in C.REGIONS.items():
        rname = names.place_name(ph, rng)
        while rname in used_places:
            rname = names.place_name(ph, rng)
        used_places.add(rname)
        town = names.place_name(ph, rng)
        while town in used_places:
            town = names.place_name(ph, rng)
        used_places.add(town)
        w.regions[key] = Region(key=key, name=rname, town=town, resources=dict(spec["resources"]))

    for key, spec in C.REGIONS.items():
        target = spec["start_pop"]
        res = spec["resources"]
        pop = 0
        while pop < target:
            pop += _make_household(w, rng, key, res)
        # a few empty houses so early marriages have somewhere to go
        for _ in range(max(1, round(target * 0.04))):
            hid = w.new_id()
            w.houses[hid] = House(id=hid, region=key, built_day=START_DAY - rng.randint(200, 9000))

    _seed_friendships(w, rng)
    _first_president(w, rng)
    from .government import ensure
    from . import language
    ensure(w)
    language.ensure(w)
    return w


def _person(w, rng, sex, age_years, region, household, family=None):
    pid = w.new_id()
    birth = w.day - int(age_years * C.DAYS_PER_YEAR) - rng.randint(0, C.DAYS_PER_YEAR - 1)
    p = Person(id=pid, given=rng.choice(w.name_pools[sex]),
               family=family or rng.choice(w.name_pools["family"]),
               sex=sex, birth_day=birth, household=household, region=region,
               traits=_traits(rng), job_pref=_job_prefs(rng),
               clothing=rng.randint(20, C.CLOTHING_LIFE))
    p.needs = {n: 0.6 for n in C.NEEDS}
    w.people[pid] = p
    return p


def _make_household(w, rng, region, res):
    hid = w.new_id()
    kind = rng.choices(["family", "couple", "elder", "single"], weights=[66, 14, 12, 8])[0]
    members = []

    def marry(a, b):
        a.spouse, b.spouse = b.id, a.id
        a.friends[str(b.id)] = b.friends[str(a.id)] = 0.7

    if kind in ("family", "couple"):
        hage = rng.randint(20, 52) if kind == "family" else rng.randint(18, 30)
        wage_ = max(17, hage + rng.randint(-6, 3))
        husband = _person(w, rng, "m", hage, region, hid)
        wife = _person(w, rng, "f", wage_, region, hid)
        marry(husband, wife)
        members = [husband, wife]
        if kind == "family":
            n_kids = rng.choices([1, 2, 3, 4, 5, 6], weights=[14, 22, 24, 18, 12, 6])[0]
            span = min(wage_ - 17, 24)
            for _ in range(n_kids):
                if span < 0:
                    break
                kage = rng.randint(0, max(0, span))
                kid = _person(w, rng, rng.choice("mf"), kage, region, hid, family=husband.family)
                kid.father, kid.mother = husband.id, wife.id
                husband.children.append(kid.id)
                wife.children.append(kid.id)
                members.append(kid)
    elif kind == "elder":
        age = rng.randint(58, 74)
        elder = _person(w, rng, rng.choice("mf"), age, region, hid)
        elder.widowed = True
        members = [elder]
        if rng.random() < 0.5:   # an adult child still at home
            kid = _person(w, rng, rng.choice("mf"), rng.randint(18, 30), region, hid, family=elder.family)
            if elder.sex == "f":
                kid.mother = elder.id
            else:
                kid.father = elder.id
            elder.children.append(kid.id)
            members.append(kid)
    else:
        members = [_person(w, rng, rng.choice("mf"), rng.randint(18, 40), region, hid)]

    # jobs: adults usually share the household trade, sometimes not
    main_job = _pick_job(rng, res)
    for p in members:
        if p.age(w.day) >= C.ADULT_AGE and p.age(w.day) < C.RETIRE_AGE:
            p.job = main_job if rng.random() < 0.75 else _pick_job(rng, res)
            p.skills[p.job] = rng.randint(100, 3000)
            p.job_since = w.day - rng.randint(0, 2000)

    house = w.new_id()
    w.houses[house] = House(id=house, region=region, built_day=w.day - rng.randint(300, 12000), household=hid)
    n = len(members)
    workers = sum(1 for p in members if p.job)
    coins = C.START_COINS_PER_PERSON * n * rng.lognormvariate(0, 0.55)
    food_need = sum(C.FOOD_PER_ADULT if p.age(w.day) >= C.WORK_AGE else C.FOOD_PER_CHILD for p in members)
    inv = {g: 0.0 for g in C.GOODS}
    inv["grain"] = food_need * rng.uniform(10, 25)
    w.households[hid] = Household(id=hid, region=region, members=[p.id for p in members],
                                  house=house, coins=round(coins, 2), inv=inv,
                                  tool_days=workers * rng.uniform(20, 120), founded=w.day)
    return n


def _seed_friendships(w, rng):
    by_region = {}
    for p in w.people.values():
        by_region.setdefault(p.region, []).append(p)
    for group in by_region.values():
        for p in group:
            for other in rng.sample(group, min(len(group), rng.randint(2, 6))):
                if other.id == p.id or other.household == p.household:
                    continue
                f = round(rng.uniform(0.1, 0.55), 2)
                p.friends[str(other.id)] = f
                other.friends.setdefault(str(p.id), round(f * rng.uniform(0.6, 1.1), 2))


def _first_president(w, rng):
    candidates = [p for p in w.people.values() if 35 <= p.age(w.day) <= 62]
    candidates.sort(key=lambda p: p.traits["ambition"] + p.traits["sociability"] + rng.random() * 0.5,
                    reverse=True)
    pres = candidates[0]
    pres.reputation = 0.8
    w.president = pres.id
