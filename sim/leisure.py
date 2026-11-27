"""Rest days, taverns, festivals and contests.

The last day of each week is a day off. People spend it in the way that
suits them: at the tavern, with family, practicing for the contests, or
making art (see arts.py).

Twice a year the president may pay for festivals: a harvest festival in
every region at the end of autumn, and a midwinter feast for the whole
nation. Festivals bring the contests: wrestling, footraces and archery.
"""
import math

from . import config as C
from .calendar import season, week_of_year
from .economy import drinks, labor_rate
from .model import note

SPORTS = {
    "wrestling": {"peak": 26, "width": 9, "max_age": 45, "name": "wrestling"},
    "footrace":  {"peak": 22, "width": 8, "max_age": 45, "name": "the footrace"},
    "archery":   {"peak": 34, "width": 14, "max_age": 60, "name": "archery"},
}
HARVEST_WEEK = 39     # last week of autumn
MIDWINTER_WEEK = 46   # the middle of winter


def ensure(w):
    sp = w.sports
    if not sp:
        sp.update({"regional": {s: {} for s in SPORTS}, "national": {s: None for s in SPORTS},
                   "titles": {}, "finals": {}})
    return sp


def rest_day(w, log):
    ensure(w)
    rng = w.rng
    day = w.day
    week = week_of_year(day)
    festival = None
    if week == HARVEST_WEEK:
        festival = "harvest"
    elif week == MIDWINTER_WEEK:
        festival = "midwinter"
    held = _festival(w, log, festival) if festival else set()

    tavern_goers = {}
    for p in list(w.people.values()):
        age = p.age(day)
        if p.region in held:
            p.leisure = min(1.0, p.leisure + 0.45)
            continue
        if age < 6:
            continue
        t = p.traits
        options = {"family": 0.4 + t["warmth"]}
        if drinks(p, day):
            options["tavern"] = 0.3 + t["sociability"]
        if age >= C.ADULT_AGE and age < 55:
            options["practice"] = 0.1 + t["boldness"] * 0.7 + 0.3 * (_best_sport_skill(p) > 20)
        from . import arts
        if arts.wants_art(p, day):
            options["art"] = t["creativity"] * 1.3
        choice = max(options, key=lambda k: options[k] + rng.random() * 0.6)
        if choice == "tavern":
            tavern_goers.setdefault(p.region, []).append(p)
        elif choice == "family":
            p.leisure = min(1.0, p.leisure + 0.25)
        elif choice == "practice":
            sport = max(SPORTS, key=lambda s: p.skills.get(s, 0) + rng.random() * 15)
            p.skills[sport] = p.skills.get(sport, 0) + 1
            p.leisure = min(1.0, p.leisure + 0.25)
        elif choice == "art":
            from . import arts
            arts.work_on(w, log, p)
            p.leisure = min(1.0, p.leisure + 0.3)
    for region, goers in tavern_goers.items():
        _tavern(w, log, region, goers)


def daily(w):
    """Leisure fades through the working week."""
    for p in w.people.values():
        p.leisure = max(0.0, p.leisure - 0.025)


def _best_sport_skill(p):
    return max(p.skills.get(s, 0) for s in SPORTS)


# ---------------------------------------------------------------- taverns
def _tavern(w, log, region, goers):
    from .society import _meet
    rng = w.rng
    for p in goers:
        h = w.households[p.household]
        if h.inv.get("ale", 0.0) >= 1:
            h.inv["ale"] -= 1
            p.leisure = min(1.0, p.leisure + 0.4)
            drank = True
        else:
            p.leisure = min(1.0, p.leisure + 0.15)
            drank = False
        for _ in range(3):
            other = rng.choice(goers)
            if other.id == p.id:
                continue
            before = p.friends.get(str(other.id), 0.0)
            _meet(w, p, other)
            # opinions about the president rub off between friends
            if p.friends.get(str(other.id), 0.0) > 0.2:
                mid = (p.approval + other.approval) / 2
                p.approval += (mid - p.approval) * 0.05
                other.approval += (mid - other.approval) * 0.05
            # drink and old grudges make for quarrels
            if drank and before < 0.05 and rng.random() < 0.007:
                for x, y in ((p, other), (other, p)):
                    x.friends[str(y.id)] = max(-1.0, x.friends.get(str(y.id), 0.0) - 0.35)
                if p.friends[str(other.id)] <= -0.3 and before > -0.3:
                    imp = 2 if _notable(w, p) or _notable(w, other) else 1
                    log.add(w.day, "tavern_quarrel", f"Words were exchanged at the tavern in "
                            f"{w.regions[region].town} between {p.name} and {other.name}, and not kindly.",
                            region=region, importance=imp, people=[p.id, other.id])
                    note(p, w.day, f"fell out with {other.name} at the tavern")
                    note(other, w.day, f"fell out with {p.name} at the tavern")


def _notable(w, p):
    sp = ensure(w)
    return (p.id == w.president or p.reputation > 0.7 or str(p.id) in sp["titles"]
            or p.id in {s["id"] for s in (w.paper.get("staff") or {}).values()})


# ---------------------------------------------------------------- festivals
def _festival(w, log, kind):
    """Returns the set of regions holding a festival today."""
    pres = w.people.get(w.president)
    regions = list(w.regions) if kind == "harvest" else ["all"]
    pop = sum(1 for _ in w.people.values())
    cost = labor_rate(w) * (0.4 if kind == "harvest" else 0.6) * pop
    name = "harvest festival" if kind == "harvest" else "midwinter feast"
    if pres is None:
        log.add(w.day, "festival_skipped", f"With no president to pay for it, there was no {name} this year.",
                importance=3)
        return set()
    t = pres.traits
    willing = 0.5 + 0.4 * t["warmth"] + 0.2 * t["ambition"] - 0.35 * t["greed"]
    if w.treasury < cost * 1.3 or w.rng.random() > willing:
        log.add(w.day, "festival_skipped", f"President {pres.name} would not pay for a {name} this year.",
                importance=3, people=[pres.id], cost=round(cost, 1))
        for p in w.people.values():
            p.approval = max(0.0, p.approval - 0.06)
        return set()
    w.treasury -= cost
    # most of the money goes on food and drink bought from local households
    hhs = [h for h in w.households.values() if h.members]
    for h in w.rng.sample(hhs, min(len(hhs), 25)):
        h.coins += cost / min(len(hhs), 25)
    for p in w.people.values():
        p.approval = min(1.0, p.approval + 0.03)
    if kind == "harvest":
        log.add(w.day, "festival", f"Harvest festivals were held in every town, paid for by President {pres.name} "
                f"at a cost of {cost:.0f} coins.", importance=3, people=[pres.id], kind=kind, cost=round(cost, 1))
        for region in w.regions:
            _mingle(w, [p for p in w.people.values() if p.region == region])
            _contests(w, log, region, kind)
        _romance(w, log)
        return set(w.regions)
    capital = max(w.regions, key=lambda r: sum(1 for p in w.people.values() if p.region == r))
    log.add(w.day, "festival", f"The midwinter feast was held in {w.regions[capital].town}, paid for by "
            f"President {pres.name} at a cost of {cost:.0f} coins. People came from every corner of "
            f"{w.nation_name}.", region=capital, importance=3, people=[pres.id], kind=kind, cost=round(cost, 1))
    _mingle(w, list(w.people.values()))
    _contests(w, log, None, kind)
    _romance(w, log)
    return set(w.regions)


def _romance(w, log):
    """Festivals are where many couples come together."""
    from .society import courtship
    for _ in range(3):
        courtship(w, log)


def _mingle(w, crowd):
    from .society import _meet
    rng = w.rng
    crowd = [p for p in crowd if p.age(w.day) >= 6]
    if len(crowd) < 2:
        return
    for p in crowd:
        for _ in range(4):
            q = rng.choice(crowd)
            if q.id != p.id:
                _meet(w, p, q)


# ---------------------------------------------------------------- contests
def ability(w, p, sport):
    spec = SPORTS[sport]
    age = p.age(w.day)
    age_f = math.exp(-((age - spec["peak"]) / spec["width"]) ** 2)
    t = p.traits
    if sport == "wrestling":
        base = 0.55 + 0.3 * t["boldness"] + 0.15 * t["diligence"]
    elif sport == "footrace":
        base = 0.6 + 0.25 * t["diligence"] + 0.15 * t["boldness"]
    else:
        base = 0.5 + 0.35 * t["diligence"] + 0.15 * (1 - t["boldness"])
    practice = min(0.35, p.skills.get(sport, 0) / 120)
    return age_f * base + practice + w.rng.gauss(0, 0.12)


def _contests(w, log, region, kind):
    sp = ensure(w)
    rng = w.rng
    for sport, spec in SPORTS.items():
        if region:
            pool = [p for p in w.people.values() if p.region == region
                    and C.ADULT_AGE <= p.age(w.day) <= spec["max_age"]]
            pool.sort(key=lambda p: p.traits["boldness"] + p.traits["ambition"] * 0.5
                      + p.skills.get(sport, 0) / 40 + rng.random() * 0.5, reverse=True)
            entrants = pool[:8]
        else:
            ids = {pid for pid in sp["regional"][sport].values()}
            entrants = [w.people[i] for i in ids if i in w.people
                        and w.people[i].age(w.day) <= spec["max_age"]]
            if len(entrants) < 2:
                continue
        if len(entrants) < 2:
            continue
        scores = sorted(((ability(w, p, sport), p) for p in entrants), key=lambda x: -x[0])
        winner, runner = scores[0][1], scores[1][1]
        where = w.regions[region].name if region else "the nation"
        if region:
            prev = sp["regional"][sport].get(region)
            sp["regional"][sport][region] = winner.id
        else:
            prev = sp["national"].get(sport)
            sp["national"][sport] = winner.id
        defended = prev == winner.id
        dethroned = prev is not None and prev != winner.id and prev in (runner.id,)
        key = "-".join(str(x) for x in sorted((winner.id, runner.id))) + ":" + sport
        sp["finals"][key] = sp["finals"].get(key, 0) + 1
        rivalry = sp["finals"][key] >= 2
        sp["titles"][str(winner.id)] = sp["titles"].get(str(winner.id), 0) + 1
        winner.reputation = min(1.0, winner.reputation + (0.08 if region else 0.15))
        title = f"{'national' if not region else w.regions[region].name} {spec['name'].replace('the ', '')} champion"
        note(winner, w.day, f"won {spec['name']} at the {'midwinter feast' if not region else 'harvest festival'}"
             + (" and the national title" if not region else ""))
        bits = []
        if defended:
            bits.append("keeping the title")
        elif dethroned:
            bits.append("taking the title from the old champion")
        if rivalry:
            bits.append(f"the {sp['finals'][key]}{_th(sp['finals'][key])} time these two have met in a final")
        extra = (" (" + "; ".join(bits) + ")") if bits else ""
        sport_name = spec["name"].replace("the ", "")
        if region:
            text = (f"{winner.name}, {int(winner.age(w.day))}, of {w.regions[winner.region].town}, took the "
                    f"{sport_name} title in {where}, beating {runner.name} in the final{extra}.")
        else:
            text = (f"{winner.name}, {int(winner.age(w.day))}, of {w.regions[winner.region].town}, is the national "
                    f"{sport_name} champion, beating {runner.name} in the final{extra}.")
        log.add(w.day, "contest", text,
                region=region or winner.region, importance=3 if not region else 2,
                people=[winner.id, runner.id], sport=sport, national=not region,
                defended=defended, rivalry=rivalry, entrants=len(entrants))


def _th(n):
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def champions(w):
    sp = ensure(w)
    out = {}
    for sport in SPORTS:
        nat = sp["national"].get(sport)
        out[sport] = {"national": _pname(w, nat),
                      "regional": {w.regions[r].name: _pname(w, pid) for r, pid in sp["regional"][sport].items()}}
    return out


def _pname(w, pid):
    if pid is None:
        return None
    p = w.people.get(pid)
    if p:
        return p.name
    d = w.dead.get(pid)
    return f"{d['given']} {d['family']} (late)" if d else None
