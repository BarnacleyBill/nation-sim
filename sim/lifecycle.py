"""Births and deaths, and what happens to a family when someone dies."""
import math

from . import config as C
from . import inventions
from .calendar import DAYS_PER_YEAR
from .model import Person, note

ACCIDENTS = {
    "fisher": "drowned when a boat went down",
    "miner": "was killed in a mine collapse",
    "woodcutter": "was crushed by a falling tree",
    "quarrier": "was killed in a fall at the quarry",
    "builder": "died in a fall from a house frame",
    "farmer": "was killed in an accident in the fields",
    "herder": "was killed by a bull",
    "smith": "died of burns from the forge",
    "weaver": "died in an accident at the loom",
}


def annual_mortality(age):
    if age < 1:
        return 0.09
    if age < 5:
        return 0.015
    if age < 40:
        return 0.01
    return 0.01 * math.exp(0.085 * (age - 40))


def daily(w, log, weather_hazard):
    _births(w, log)
    _deaths(w, log, weather_hazard)


# ---------------------------------------------------------------- births
def _births(w, log):
    rng = w.rng
    for p in list(w.people.values()):
        if p.sex != "f":
            continue
        if p.pregnant_until is not None:
            if w.day >= p.pregnant_until:
                _give_birth(w, log, p)
            continue
        if p.spouse not in w.people or w.day < p.fertile_after:
            continue
        age = p.age(w.day)
        if not (C.FERTILE_MIN <= age <= C.FERTILE_MAX):
            continue
        fert = 1.0 if age < 35 else max(0.1, 1.0 - (age - 35) * 0.09)
        kids_at_home = sum(1 for c in p.children if c in w.people and w.people[c].age(w.day) < C.ADULT_AGE)
        chance = 0.0021 * fert * (0.5 + p.mood) * min(1.0, p.fed) * (0.82 ** kids_at_home)
        if rng.random() < chance:
            p.pregnant_until = w.day + 270


def _give_birth(w, log, mother):
    rng = w.rng
    mother.pregnant_until = None
    mother.fertile_after = w.day + 300
    father = w.people.get(mother.spouse)
    hh = w.households[mother.household]
    n = 2 if rng.random() < 0.015 else 1
    babies = []
    for _ in range(n):
        sex = rng.choice("mf")
        given = _choose_name(w, sex, mother, father)
        pid = w.new_id()
        baby = Person(id=pid, given=given, family=father.family if father else mother.family,
                      sex=sex, birth_day=w.day, household=hh.id, region=hh.region,
                      traits={t: round(_inherit(rng, mother, father, t), 2) for t in C.TRAITS},
                      job_pref={j: round(rng.uniform(0.85, 1.15), 2) for j in C.JOBS},
                      mother=mother.id, father=father.id if father else None,
                      clothing=C.CLOTHING_LIFE)
        baby.needs = {k: 0.7 for k in C.NEEDS}
        parents_txt = f"{mother.name} and {father.name}" if father else mother.name
        note(baby, w.day, f"born in {w.regions[hh.region].town} to {parents_txt}")
        w.people[pid] = baby
        hh.members.append(pid)
        mother.children.append(pid)
        if father:
            father.children.append(pid)
        babies.append(baby)
        w.count("births")
    town = w.regions[hh.region].town
    parents = f"{mother.name} and {father.name}" if father else mother.name
    if n == 2:
        text = f"Twins, {babies[0].given} and {babies[1].given}, were born to {parents} in {town}."
    else:
        b = babies[0]
        text = f"A {'daughter' if b.sex == 'f' else 'son'}, {b.given}, was born to {parents} in {town}."
    for par in (mother, father):
        if par:
            note(par, w.day, f"had {'twins' if n == 2 else ('a daughter' if babies[0].sex == 'f' else 'a son')}, "
                 + " and ".join(b.given for b in babies))
    log.add(w.day, "birth", text, region=hh.region, importance=2 if n == 2 else 1,
            people=[b.id for b in babies] + [mother.id] + ([father.id] if father else []))
    if rng.random() < 0.012:
        kill(w, log, mother, "died in childbirth")


def _inherit(rng, mother, father, trait):
    parents = [x for x in (mother, father) if x]
    base = sum(x.traits[trait] for x in parents) / len(parents)
    return min(1.0, max(0.0, 0.5 * base + 0.5 * rng.gauss(0.5, 0.18)))


def _choose_name(w, sex, mother, father):
    rng = w.rng
    # sometimes children are named after a grandparent
    if rng.random() < 0.2:
        grands = []
        for par in (mother, father):
            if par:
                for g in (par.mother, par.father):
                    gp = w.people.get(g) or w.dead.get(g)
                    if gp:
                        gsex = gp.sex if isinstance(gp, Person) else gp.get("sex")
                        gname = gp.given if isinstance(gp, Person) else gp.get("given")
                        if gsex == sex and gname:
                            grands.append(gname)
        if grands:
            return rng.choice(grands)
    siblings = {w.people[c].given for c in mother.children if c in w.people}
    for _ in range(10):
        nm = rng.choice(w.name_pools[sex])
        if nm not in siblings:
            return nm
    return nm


# ---------------------------------------------------------------- deaths
def _deaths(w, log, weather_hazard):
    from .economy import has_facility
    rng = w.rng
    wells = {r: 0.88 for r in w.regions if has_facility(w, r, "well", include_building=False)}
    for p in list(w.people.values()):
        if p.id not in w.people:
            continue
        age = p.age(w.day)
        hz = annual_mortality(age) / DAYS_PER_YEAR * weather_hazard.get(p.region, 1.0) * wells.get(p.region, 1.0)
        if age < 5:
            hz *= inventions.multiplier(w, p.region, "health", "child")
        if p.hunger > 20:
            hz += 0.01 * (p.hunger - 20) / 10
        if rng.random() < hz:
            if p.hunger > 20:
                cause = "died of hunger"
            elif age >= 60:
                cause = "died of old age"
            elif age < 5:
                cause = "died of a childhood illness"
            else:
                cause = "died of an illness"
            kill(w, log, p, cause)
            continue
        if p.job and rng.random() < C.JOBS[p.job]["risk"] * inventions.multiplier(w, p.region, "safety", p.job):
            kill(w, log, p, ACCIDENTS.get(p.job, "died in an accident"))


def kill(w, log, p, cause):
    from .society import new_household, dissolve_household, move_person
    age = int(p.age(w.day))
    hh = w.households.get(p.household)
    region = p.region
    w.dead[p.id] = {"given": p.given, "family": p.family, "sex": p.sex,
                    "birth_day": p.birth_day, "death_day": w.day, "cause": cause,
                    "region": region, "mother": p.mother, "father": p.father,
                    "spouse": p.spouse, "job": p.job, "life": list(p.life),
                    "children": list(p.children), "reputation": p.reputation}
    del w.people[p.id]
    spouse = w.people.get(p.spouse)
    if spouse:
        spouse.spouse = None
        spouse.widowed = True
        spouse.friends.pop(str(p.id), None)
        note(spouse, w.day, f"was widowed when {p.given} {cause}")
    if p.pregnant_until:
        pass   # the unborn child is lost with the mother
    w.count("deaths")

    importance = 1 if cause == "died of old age" else 2
    if age >= 80:
        importance = 3
    if w.president == p.id:
        importance = 5
    town = w.regions[region].town
    if age < 1:
        who = f"{p.name}, an infant of {town}"
    else:
        desc = f"a {p.job}" if p.job else ("a child" if age < 14 else "")
        who = f"{p.name}, {age}" + (f", {desc}" if desc else "") + f", of {town}"
    log.add(w.day, "death", f"{who}, {cause}.", region=region, importance=importance,
            people=[p.id], age=age, cause=cause, was_president=(w.president == p.id))
    if w.president == p.id:
        w.president = None
        from .government import on_president_died
        on_president_died(w, log, p.id)

    if not hh:
        return
    hh.members.remove(p.id)
    if not hh.members:
        heirs = []
        for c in p.children:
            if c in w.people:
                heirs.append(w.households[w.people[c].household])
        _pass_on_house(w, hh, heirs)
        dissolve_household(w, hh, heirs=heirs)
        return
    adults = [w.people[m] for m in hh.members if w.people[m].age(w.day) >= C.ADULT_AGE]
    if adults:
        return
    # only children remain: kin take them in
    kids = [w.people[m] for m in hh.members]
    from .economy import kin_households
    carers = [k for k in kin_households(w, hh)
              if any(w.people[m].age(w.day) >= C.ADULT_AGE for m in k.members)]
    if not carers:
        friends = {}
        for k in kids:
            for fid, aff in k.friends.items():
                f = w.people.get(int(fid))
                if f and f.region == hh.region and f.age(w.day) >= C.ADULT_AGE:
                    friends[f.household] = friends.get(f.household, 0) + aff
        if friends:
            carers = [w.households[max(friends, key=friends.get)]]
    if not carers:
        carers = [max((h for h in w.households.values() if h.region == hh.region and h.id != hh.id
                       and h.members), key=lambda h: h.coins, default=None)]
    carer = carers[0]
    if carer is None:
        return
    names = ", ".join(k.given for k in kids)
    head = w.people[carer.members[0]]
    log.add(w.day, "orphans_taken_in",
            f"The orphaned {'child' if len(kids) == 1 else 'children'} of {p.name} ({names}) "
            f"have been taken in by the {head.family} household.",
            region=carer.region, importance=2, people=[k.id for k in kids] + [head.id])
    for k in kids:
        move_person(w, k, carer)
        note(k, w.day, f"was orphaned, and taken in by the {head.family} household")


def _pass_on_house(w, hh, heirs):
    """A house left empty goes to the eldest child who has none, if they live nearby."""
    if not hh.house:
        return
    for h in sorted(heirs, key=lambda h: h.founded):
        if h.house is None and h.region == hh.region:
            house = w.houses[hh.house]
            house.household = h.id
            h.house = house.id
            h.homeless_since = None
            hh.house = None
            return
