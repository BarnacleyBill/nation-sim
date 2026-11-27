"""The government: one president, elected by every adult for six months.

Once a week the government:
  - collects the head tax (if any) and pays subsidies and public works wages
  - lets the president act: change taxes, mint coins, fund public works,
    subsidize a trade, cap the grain price, hand out relief, or (if greedy)
    quietly skim the treasury
  - updates what every adult thinks of the president
  - runs the calendar of campaigns, elections, petitions and recall votes

The president decides the same way everyone does: by what they expect will
raise their own satisfaction -- which for a president mostly means keeping
supporters happy and getting re-elected, shaded by personality.
"""
from . import config as C
from .calendar import label
from .economy import labor_rate, house_price, food_need, food_stock, has_facility

# ---------------------------------------------------------------- setup


def ensure(w):
    """Give an older save a government if it has none yet."""
    g = w.gov
    if g:
        return g
    g.update({
        "term_start": w.day,
        "election_day": w.day + C.TERM_DAYS,
        "campaign_open": False,
        "candidates": [],
        "promises": [],
        "kept": [],
        "sales_tax": C.START_SALES_TAX,
        "head_tax": 0.0,
        "subsidies": {},
        "price_cap": None,
        "petition": None,
        "recall_vote_day": None,
        "skims": 0,
        "skimmed": 0.0,
        "minted": 0.0,
        "initial_money": round(money_supply(w), 1),
        "price_level": 1.0,
        "history": [],
        "last_action_day": -999,
        "tax_week": {},
    })
    if w.president in w.people:
        _begin_term(w, w.president, promises=[], announce=False)
    return g


def money_supply(w):
    return sum(h.coins for h in w.households.values()) + w.treasury


def adults(w):
    return [p for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE]


def president(w):
    return w.people.get(w.president)


def subsidy(w, job):
    s = w.gov.get("subsidies", {}).get(job)
    return s["rate"] if s else 0.0


# ---------------------------------------------------------------- weekly
def weekly(w, log):
    g = ensure(w)
    for p in w.people.values():
        p.gov_effect = 0.0
    _collect_and_pay(w, log)
    _expire_policies(w, log)
    if president(w):
        _president_acts(w, log)
    _update_approval(w, log)
    _calendar(w, log)
    g["tax_week"] = {}
    # the general price level slowly follows the amount of money about
    target = (money_supply(w) / max(1.0, g["initial_money"])) ** 0.7
    g["price_level"] += (target - g["price_level"]) * 0.1


def record_sales_tax(w, hid, amount):
    tw = w.gov.setdefault("tax_week", {})
    tw[str(hid)] = tw.get(str(hid), 0.0) + amount


def _collect_and_pay(w, log):
    g = w.gov
    # head tax, per adult, paid weekly by each household as far as it can
    if g["head_tax"] > 0:
        for h in w.households.values():
            n = sum(1 for m in h.members if w.people[m].age(w.day) >= C.ADULT_AGE)
            due = g["head_tax"] * n
            paid = min(due, max(0.0, h.coins))
            h.coins -= paid
            w.treasury += paid
            record_sales_tax(w, h.id, paid)
    # tax burden lowers opinion of the government
    rate = max(0.2, labor_rate(w)) * 7
    for hid, paid in g["tax_week"].items():
        h = w.households.get(int(hid))
        if not h:
            continue
        n = max(1, sum(1 for m in h.members if w.people[m].age(w.day) >= C.ADULT_AGE))
        hit = min(0.12, 0.6 * paid / n / rate)
        for m in h.members:
            w.people[m].gov_effect -= hit
    # subsidies, paid to every worker in the trade
    for job, s in list(g["subsidies"].items()):
        workers = [p for p in w.people.values() if p.job == job]
        total = s["rate"] * 7 * len(workers)
        if total > w.treasury:
            log.add(w.day, "subsidy_lapsed", f"The treasury could not pay the {job}s' subsidy; it has lapsed.",
                    importance=3, job=job)
            del g["subsidies"][job]
            continue
        w.treasury -= total
        for p in workers:
            w.households[p.household].coins += s["rate"] * 7
            p.gov_effect += 0.04
    # public works wages, and finishing projects
    for fid, f in list(w.facilities.items()):
        if f["status"] != "building":
            continue
        pay = min(f["cost"] / f["weeks"], f["cost"] - f["paid"])
        if pay > w.treasury:
            if not f.get("stalled"):
                f["stalled"] = True
                log.add(w.day, "works_stalled", f"Work on {C.FACILITIES[f['kind']]['name']} in "
                        f"{w.regions[f['region']].name} has stopped: the treasury is empty.",
                        region=f["region"], importance=3)
            continue
        f["stalled"] = False
        w.treasury -= pay
        f["paid"] += pay
        hired = [h for h in w.households.values() if h.region == f["region"] and h.members]
        if hired and pay > 0:
            picks = w.rng.sample(hired, min(len(hired), 5))
            for h in picks:
                h.coins += pay / len(picks)
                for m in h.members:
                    w.people[m].gov_effect += 0.02
        f["weeks_done"] += 1
        if f["weeks_done"] >= f["weeks"]:
            _finish_facility(w, log, fid, f)


def _finish_facility(w, log, fid, f):
    f["status"] = "done"
    f["built_day"] = w.day
    region = w.regions[f["region"]]
    if f["kind"] == "house":
        from .model import House
        hid = w.new_id()
        house = House(id=hid, region=f["region"], built_day=w.day)
        w.houses[hid] = house
        waiting = sorted((h for h in w.households.values()
                          if h.region == f["region"] and h.house is None and h.members),
                         key=lambda h: h.homeless_since or 0)
        if waiting:
            h = waiting[0]
            house.household = h.id
            h.house = hid
            h.homeless_since = None
            head = w.people[h.members[0]]
            for m in h.members:
                w.people[m].gov_effect += 0.3
            log.add(w.day, "works_done", f"A public house in {region.town} has been given to the "
                    f"{head.family} family, who had no home.", region=f["region"], importance=3,
                    people=[head.id])
        else:
            log.add(w.day, "works_done", f"A public house in {region.town} is finished and stands empty.",
                    region=f["region"], importance=2)
        del w.facilities[fid]
        return
    for p in w.people.values():
        if p.region == f["region"]:
            p.gov_effect += 0.1
    log.add(w.day, "works_done", f"{C.FACILITIES[f['kind']]['name'].capitalize()} in "
            f"{region.name} is finished.", region=f["region"], importance=3, kind=f["kind"])


def _expire_policies(w, log):
    g = w.gov
    for job, s in list(g["subsidies"].items()):
        if s["until"] <= w.day:
            del g["subsidies"][job]
            log.add(w.day, "subsidy_ended", f"The subsidy for {job}s has ended.", importance=2, job=job)
    if g["price_cap"] and g["price_cap"]["until"] <= w.day:
        g["price_cap"] = None
        log.add(w.day, "price_cap_ended", "The cap on the price of grain has been lifted.", importance=3)


# ---------------------------------------------------------------- the president's choices
def _situation(w):
    hungry = {}
    for p in w.people.values():
        if p.hunger >= 5:
            hungry[p.region] = hungry.get(p.region, 0) + 1
    homeless = {}
    for h in w.households.values():
        if h.members and h.house is None:
            homeless[h.region] = homeless.get(h.region, 0) + 1
    pop = {}
    for p in w.people.values():
        pop[p.region] = pop.get(p.region, 0) + 1
    return hungry, homeless, pop


def facility_cost(w, kind):
    if kind == "house":
        return house_price(w) * 1.2
    return C.FACILITIES[kind]["labor_days"] * labor_rate(w) * 1.3


def _president_acts(w, log):
    g = w.gov
    pres = president(w)
    t = pres.traits
    hungry, homeless, pop = _situation(w)
    treasury = w.treasury
    building = sum(1 for f in w.facilities.values() if f["status"] == "building")
    supporters = g.get("supporter_regions", {})
    options = []   # (score, name, args)

    def support(region):
        return 1.0 + 0.5 * supporters.get(region, 0.0)

    def promised(kind, region=None, job=None):
        for pr in g["promises"]:
            if pr["kind"] == kind and pr.get("region") in (None, region) and pr.get("job") in (None, job):
                return 1.6
        return 1.0

    n_hungry = sum(hungry.values())
    if n_hungry >= 4:
        cost = n_hungry * 7 * max(0.3, w.prices["grain"]) * 1.2
        if cost < treasury * 0.5:
            options.append((0.03 * n_hungry * (0.5 + t["warmth"]) * promised("relief"), "relief", {}))
    for region, n in homeless.items():
        cost = facility_cost(w, "house")
        if n >= 2 and cost < treasury * 0.4:
            score = 0.08 * min(n, 8) * (0.4 + t["warmth"]) * support(region) * promised("house", region)
            options.append((score, "facility", {"kind": "house", "region": region}))
    if building < 2:
        for region, n in pop.items():
            for kind, base in (("well", 0.25), ("granary", 0.3), ("mill", 0.35), ("road", 0.3)):
                if has_facility(w, region, kind):
                    continue
                if kind == "mill" and w.regions[region].resources.get("farmland", 0) < 0.8:
                    continue
                cost = facility_cost(w, kind)
                if cost > treasury * 0.5:
                    continue
                score = (base * (n / 100) * (0.4 + t["ambition"]) * support(region)
                         * promised(kind, region) * (1.0 - 0.3 * (cost / max(1.0, treasury))))
                options.append((score, "facility", {"kind": kind, "region": region}))
    # subsidize the poorest large trade
    if not g["subsidies"] and treasury > 600:
        trades = {}
        for p in w.people.values():
            if p.job and p.job != "builder":
                trades.setdefault(p.job, []).append(p.income_ema)
        median = labor_rate(w)
        for job, incs in trades.items():
            if len(incs) < 8:
                continue
            avg = sum(incs) / len(incs)
            if avg < median * 0.75:
                score = 0.004 * len(incs) * (0.5 + t["warmth"]) * promised("subsidy", job=job)
                options.append((score, "subsidy", {"job": job, "rate": round(median * 0.15, 3)}))
    # grain price cap in a famine
    customary = C.START_PRICES["grain"] * g["price_level"]
    if not g["price_cap"] and w.prices["grain"] > 2.5 * customary and n_hungry >= 10:
        options.append((0.5 * (0.5 + t["warmth"]), "price_cap", {"max": round(2.0 * customary, 3)}))
    # money matters
    if treasury < 300:
        if t["boldness"] > 0.5:
            options.append((0.6 + t["boldness"] * 0.4, "mint", {}))
        else:
            options.append((0.6, "raise_tax", {}))
    elif treasury > 1200 and (g["sales_tax"] > 0.06 or g["head_tax"] > 0):
        options.append((0.35 + 0.4 * t["greed"] + 0.3 * (treasury > 2500), "lower_tax", {}))
    elif treasury > 4000 and g["sales_tax"] > 0.02:
        options.append((0.3 + 0.4 * t["greed"], "lower_tax", {}))
    if treasury > 400 and t["greed"] > 0.6 and w.rng.random() < (t["greed"] - 0.55) * 0.35:
        options.append((1.0, "skim", {}))

    if not options:
        return
    options.sort(key=lambda o: o[0], reverse=True)
    score, name, args = options[0]
    if score < 0.25 and name != "skim":
        return
    _do(w, log, pres, name, args)
    if len(options) > 1 and options[1][0] > 0.7 and options[1][1] != name and options[1][1] != "skim":
        _do(w, log, pres, options[1][1], options[1][2])


def _keep_promise(w, log, pres, kind, region=None, job=None):
    g = w.gov
    for pr in list(g["promises"]):
        if pr["kind"] == kind and pr.get("region") in (None, region) and pr.get("job") in (None, job):
            g["promises"].remove(pr)
            g["kept"].append(pr)
            log.add(w.day, "promise_kept", f"President {pres.name} has kept a campaign promise: {pr['text']}.",
                    importance=3, people=[pres.id], promise=pr["text"])
            return


def _do(w, log, pres, name, args):
    g = w.gov
    if name == "relief":
        given = 0.0
        for h in w.households.values():
            if not h.members:
                continue
            if any(w.people[m].hunger >= 5 for m in h.members):
                amt = food_need(w, h) * 7 * max(0.3, w.prices["grain"]) * 1.2
                if amt > w.treasury:
                    break
                w.treasury -= amt
                h.coins += amt
                given += amt
                for m in h.members:
                    w.people[m].gov_effect += 0.25
        for p in w.people.values():
            p.gov_effect += 0.03 * p.traits["warmth"]
        log.add(w.day, "relief", f"President {pres.name} ordered {given:.0f} coins of relief for hungry families.",
                importance=3, people=[pres.id], coins=round(given, 1))
        _keep_promise(w, log, pres, "relief")
    elif name == "facility":
        kind, region = args["kind"], args["region"]
        cost = facility_cost(w, kind)
        fid = str(w.new_id())
        w.facilities[fid] = {"kind": kind, "region": region, "status": "building", "cost": round(cost, 2),
                             "paid": 0.0, "weeks": C.FACILITIES[kind]["weeks"], "weeks_done": 0,
                             "started": w.day, "president": pres.id}
        for p in w.people.values():
            if p.region == region:
                p.gov_effect += 0.04
        log.add(w.day, "works_begun", f"President {pres.name} has ordered {C.FACILITIES[kind]['name']} built in "
                f"{w.regions[region].name}, at a cost of {cost:.0f} coins.", region=region, importance=3,
                people=[pres.id], kind=kind, cost=round(cost, 1))
        _keep_promise(w, log, pres, kind, region=region)
    elif name == "subsidy":
        job = args["job"]
        g["subsidies"][job] = {"rate": args["rate"], "until": w.day + 13 * 7, "since": w.day}
        log.add(w.day, "subsidy", f"President {pres.name} will pay every {job} a subsidy of {args['rate']:.2f} "
                f"coins a day for the next season.", importance=3, people=[pres.id], job=job, rate=args["rate"])
        _keep_promise(w, log, pres, "subsidy", job=job)
    elif name == "price_cap":
        g["price_cap"] = {"good": "grain", "max": args["max"], "until": w.day + 8 * 7}
        log.add(w.day, "price_cap", f"President {pres.name} has capped the price of grain at {args['max']:.2f} "
                "coins for eight weeks.", importance=4, people=[pres.id], max=args["max"])
        for p in w.people.values():
            p.gov_effect += -0.05 if p.job == "farmer" else 0.04
    elif name == "mint":
        amount = round(money_supply(w) * w.rng.uniform(0.04, 0.08))
        w.treasury += amount
        g["minted"] += amount
        log.add(w.day, "mint", f"President {pres.name} ordered {amount} new coins struck to refill the treasury.",
                importance=3, people=[pres.id], coins=amount)
        for p in w.people.values():
            p.gov_effect -= 0.02 * p.traits["greed"]
    elif name == "raise_tax":
        old = g["sales_tax"]
        if old < C.MAX_SALES_TAX:
            g["sales_tax"] = round(min(C.MAX_SALES_TAX, old + 0.02), 3)
        else:
            g["head_tax"] = round(g["head_tax"] + 0.1, 2)
        log.add(w.day, "tax_up", f"President {pres.name} raised taxes: the market tax is now "
                f"{g['sales_tax']:.0%}" + (f" and every adult owes {g['head_tax']:.2f} coins a week" if g["head_tax"] else "")
                + ".", importance=3, people=[pres.id], sales_tax=g["sales_tax"], head_tax=g["head_tax"])
        for p in w.people.values():
            p.gov_effect -= 0.05
    elif name == "lower_tax":
        if g["head_tax"] > 0:
            g["head_tax"] = round(max(0.0, g["head_tax"] - 0.1), 2)
        else:
            g["sales_tax"] = round(max(0.0, g["sales_tax"] - 0.01), 3)
        log.add(w.day, "tax_down", f"President {pres.name} cut taxes: the market tax is now {g['sales_tax']:.0%}.",
                importance=3, people=[pres.id], sales_tax=g["sales_tax"])
        for p in w.people.values():
            p.gov_effect += 0.04
        _keep_promise(w, log, pres, "lower_tax")
    elif name == "skim":
        amount = round(w.treasury * w.rng.uniform(0.03, 0.08), 1)
        w.treasury -= amount
        w.households[pres.household].coins += amount
        g["skims"] += 1
        g["skimmed"] += amount
        # nothing is logged publicly unless it is found out
    g["last_action_day"] = w.day


# ---------------------------------------------------------------- public opinion
def _update_approval(w, log):
    g = w.gov
    pres = president(w)
    # a secret skim may come to light
    if pres and g["skims"] and w.rng.random() < min(0.5, 0.05 * g["skims"]):
        _scandal(w, log, pres)
    for p in adults(w):
        if not pres:
            p.approval += (0.55 - p.approval) * 0.1
            continue
        mood_effect = (p.satisfaction - 0.8) * 0.3
        friend = p.friends.get(str(pres.id), 0.0) * 0.05
        p.approval += p.gov_effect + mood_effect * 0.3 + friend * 0.3
        p.approval += (0.55 - p.approval) * 0.04        # opinions settle over time
        p.approval = max(0.0, min(1.0, p.approval))


def _scandal(w, log, pres):
    g = w.gov
    total = g["skimmed"]
    log.add(w.day, "scandal", f"Scandal: President {pres.name} has been found to have taken {total:.0f} coins "
            "from the treasury for their own household.", importance=5, people=[pres.id], coins=round(total, 1))
    pres.reputation = max(0.0, pres.reputation - 0.4)
    for p in adults(w):
        p.approval = max(0.0, p.approval - (0.25 + 0.15 * p.traits["piety"]))
    g["skims"] = 0
    g["skimmed"] = 0.0
    g["scandals"] = g.get("scandals", 0) + 1


# ---------------------------------------------------------------- calendar
def _calendar(w, log):
    g = w.gov
    day = w.day
    if not president(w) and g.get("recall_vote_day") is None and g["election_day"] > day + C.SPECIAL_ELECTION_DAYS:
        # the office is empty: call a special election
        g["election_day"] = day + C.SPECIAL_ELECTION_DAYS
        g["campaign_open"] = False
        log.add(day, "special_election", f"With the presidency empty, a special election will be held on "
                f"{label(g['election_day'])}.", importance=4)
    if not g["campaign_open"] and day >= g["election_day"] - C.CAMPAIGN_DAYS:
        _open_campaign(w, log)
    if day >= g["election_day"]:
        _hold_election(w, log)
        return
    _petitions(w, log)


def _open_campaign(w, log):
    g = w.gov
    g["campaign_open"] = True
    pres = president(w)
    pool = [p for p in adults(w) if 25 <= p.age(w.day) <= 70]
    scored = []
    for p in pool:
        friends = sum(1 for a in p.friends.values() if a > 0.3)
        s = (0.5 * p.traits["ambition"] + 0.3 * p.reputation + 0.2 * p.traits["boldness"]
             + 0.02 * friends + 0.3 * p.needs.get("standing", 0.5) + w.rng.gauss(0, 0.12))
        if pres and p.id == pres.id:
            s += 0.2 if p.approval > 0.3 else -0.5
        scored.append((s, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    runners = [p for s, p in scored[:4] if s > 0.65][:3]
    if pres and pres not in runners and pres.age(w.day) < C.RETIRE_AGE and pres.traits["ambition"] > 0.35:
        runners = [pres] + runners[:2]
    if len(runners) < 2:
        runners = [p for s, p in scored[:2]]
    g["candidates"] = []
    for c in runners:
        promises = _platform(w, c)
        g["candidates"].append({"id": c.id, "promises": promises})
        ptext = "; ".join(pr["text"] for pr in promises) or "no particular promises"
        incumbent = " (the sitting president)" if pres and c.id == pres.id else ""
        log.add(w.day, "candidate", f"{c.name}{incumbent}, {int(c.age(w.day))}, a {c.job or 'retired person'} "
                f"from {w.regions[c.region].name}, is standing for president, promising: {ptext}.",
                region=c.region, importance=3, people=[c.id], promises=[pr["text"] for pr in promises])
    log.add(w.day, "campaign", f"The campaign has begun. {len(runners)} candidates are standing; "
            f"the vote is on {label(g['election_day'])}.", importance=4, people=[c.id for c in runners])


def _platform(w, c):
    """Promises grow out of the candidate's own situation and their neighbors' troubles."""
    hungry, homeless, pop = _situation(w)
    t = c.traits
    out = []
    region = c.region
    rname = w.regions[region].name
    if homeless.get(region, 0) >= 2 and t["warmth"] > 0.4:
        out.append({"kind": "house", "region": region, "text": f"to build homes for the homeless of {rname}"})
    if sum(hungry.values()) >= 5:
        out.append({"kind": "relief", "text": "to feed the hungry"})
    if c.job and c.job != "builder" and t["greed"] + t["ambition"] > 1.0:
        out.append({"kind": "subsidy", "job": c.job, "text": f"to support the {c.job}s"})
    if t["ambition"] > 0.5:
        for kind in ("mill", "granary", "road", "well"):
            if not has_facility(w, region, kind) and not (kind == "mill" and
                                                           w.regions[region].resources.get("farmland", 0) < 0.8):
                out.append({"kind": kind, "region": region, "text": f"to build {C.FACILITIES[kind]['name']} in {rname}"})
                break
    if t["greed"] > 0.55 or w.gov["sales_tax"] >= 0.08 or w.gov["head_tax"] > 0:
        out.append({"kind": "lower_tax", "text": "to cut taxes"})
    w.rng.shuffle(out)
    return out[:2]


def _vote_score(w, v, c, promises, pres):
    s = 0.4 * v.friends.get(str(c.id), 0.0)
    if c.id == v.id:
        return 9.0
    if c.region == v.region:
        s += 0.25
    if c.job and c.job == v.job:
        s += 0.15
    s += 0.3 * (c.reputation - 0.5)
    h = w.households[v.household]
    for pr in promises:
        k = pr["kind"]
        if k == "house" and pr.get("region") == v.region:
            s += 0.45 if h.house is None else 0.08
        elif k == "relief":
            s += 0.4 if v.hunger >= 3 else 0.05 * v.traits["warmth"]
        elif k == "subsidy" and pr.get("job") == v.job:
            s += 0.3
        elif k in C.FACILITIES and pr.get("region") == v.region:
            s += 0.15
        elif k == "lower_tax":
            s += 0.1 + 0.2 * v.traits["greed"]
    if pres and c.id == pres.id:
        s += (v.approval - 0.5) * 1.4 + 0.08 * len(w.gov["kept"])
        s -= 0.07 * w.gov.get("terms", 1)   # people tire of the same face
    return s + w.rng.gauss(0, 0.2)


def _hold_election(w, log):
    g = w.gov
    pres = president(w)
    cands = [(w.people[c["id"]], c["promises"]) for c in g["candidates"] if c["id"] in w.people]
    if not cands:
        # everyone standing has died; reopen the campaign
        g["election_day"] = w.day + C.SPECIAL_ELECTION_DAYS
        g["campaign_open"] = False
        return
    tally = {c.id: 0 for c, _ in cands}
    region_votes = {}
    voted = 0
    for v in adults(w):
        engaged = 0.55 + 0.6 * abs(v.approval - 0.5) + 0.15 * v.traits["sociability"]
        if w.rng.random() > engaged:
            continue
        best = max(cands, key=lambda cp: _vote_score(w, v, cp[0], cp[1], pres))[0]
        tally[best.id] += 1
        voted += 1
        region_votes.setdefault(best.id, {}).setdefault(v.region, 0)
        region_votes[best.id][v.region] += 1
    winner_id = max(tally, key=lambda k: (tally[k], w.people[k].reputation))
    winner = w.people[winner_id]
    eligible = len(adults(w))
    results = ", ".join(f"{w.people[k].name} {n}" for k, n in sorted(tally.items(), key=lambda x: -x[1]))
    re = pres and winner.id == pres.id
    text = (f"{winner.name} has been {'re-elected' if re else 'elected'} president of {w.nation_name}. "
            f"Votes: {results}. {voted} of {eligible} adults voted.")
    log.add(w.day, "election", text, region=winner.region, importance=5,
            people=list(tally), tally={str(k): v for k, v in tally.items()}, turnout=voted, eligible=eligible,
            winner=winner.id, reelected=bool(re))
    if pres:
        g["history"].append({"id": pres.id, "name": pres.name, "start": g["term_start"], "end": w.day,
                             "how": "re-elected" if re else "lost re-election" if pres.id in tally else "stepped down"})
    promises = next(pr for c, pr in cands if c.id == winner.id)
    # supporters: which regions gave the winner the most votes, relative to size
    reg = region_votes.get(winner.id, {})
    top = max(reg.values()) if reg else 1
    g["supporter_regions"] = {r: n / top for r, n in reg.items()}
    _begin_term(w, winner.id, promises, announce=False)


def _begin_term(w, pid, promises, announce=True):
    g = w.gov
    winner = w.people[pid]
    if w.president != pid:
        for p in adults(w):
            p.approval = 0.55 + 0.25 * max(0.0, p.friends.get(str(pid), 0.0))
    g["terms"] = g.get("terms", 0) + 1 if w.president == pid else 1
    w.president = pid
    winner.reputation = min(1.0, winner.reputation + 0.1)
    g["term_start"] = w.day
    g["election_day"] = w.day + C.TERM_DAYS
    g["campaign_open"] = False
    g["candidates"] = []
    g["promises"] = list(promises)
    g["kept"] = []
    g["petition"] = None
    g["recall_vote_day"] = None
    g["skims"] = 0
    g["skimmed"] = 0.0
    for p in w.people.values():
        p.signed_petition = False


def _petitions(w, log):
    g = w.gov
    pres = president(w)
    if not pres:
        return
    people = adults(w)
    n = len(people)
    if g.get("recall_vote_day") is not None:
        if w.day >= g["recall_vote_day"]:
            _recall_vote(w, log, pres, people)
        return
    pet = g["petition"]
    if pet is None:
        if g["election_day"] - w.day < 42 or w.day - g["term_start"] < 28:
            return   # too close to an election, or too early in a term
        if w.day < g.get("petition_cooldown", 0):
            return   # people are weary of petitions after the last one
        unhappy = [p for p in people if p.approval < 0.3]
        if len(unhappy) < n * 0.2:
            return
        starter = max(unhappy, key=lambda p: p.traits["boldness"] + p.traits["ambition"] - p.approval)
        if w.rng.random() > 0.3 + starter.traits["boldness"] * 0.4:
            return
        g["petition"] = {"started": w.day, "by": starter.id, "signatures": 0}
        starter.signed_petition = True
        log.add(w.day, "petition", f"{starter.name} of {w.regions[starter.region].name} has begun a petition to "
                f"recall President {pres.name}. It needs {int(n * C.PETITION_SHARE) + 1} names in four weeks.",
                region=starter.region, importance=4, people=[starter.id, pres.id])
        pet = g["petition"]
    for p in people:
        if not p.signed_petition and p.approval < 0.28 and w.rng.random() < 0.3 + (0.28 - p.approval):
            p.signed_petition = True
    pet["signatures"] = sum(1 for p in people if p.signed_petition)
    need = n * C.PETITION_SHARE
    if pet["signatures"] >= need:
        g["recall_vote_day"] = w.day + 7
        log.add(w.day, "recall_called", f"The petition to recall President {pres.name} has {pet['signatures']} names, "
                f"enough to force a vote. The recall vote is in one week.", importance=5, people=[pres.id],
                signatures=pet["signatures"])
    elif w.day - pet["started"] >= C.PETITION_DAYS:
        log.add(w.day, "petition_failed", f"The petition to recall President {pres.name} fell short with "
                f"{pet['signatures']} of the {int(need) + 1} names needed.", importance=3, people=[pres.id],
                signatures=pet["signatures"])
        g["petition"] = None
        g["petition_cooldown"] = w.day + 91
        for p in people:
            p.signed_petition = False


def _recall_vote(w, log, pres, people):
    g = w.gov
    yes = no = 0
    for p in people:
        if w.rng.random() > 0.5 + 0.6 * abs(p.approval - 0.5):
            continue
        if p.approval + w.rng.gauss(0, 0.08) < 0.4:
            yes += 1
        else:
            no += 1
    total = max(1, yes + no)
    share = yes / total
    g["recall_vote_day"] = None
    g["petition"] = None
    g["petition_cooldown"] = w.day + 91
    for p in people:
        p.signed_petition = False
    if share >= C.RECALL_SHARE:
        log.add(w.day, "recalled", f"President {pres.name} has been recalled: {yes} voted to remove, {no} to keep "
                f"({share:.0%}). A special election will follow.", importance=5, people=[pres.id], yes=yes, no=no)
        g["history"].append({"id": pres.id, "name": pres.name, "start": g["term_start"], "end": w.day,
                             "how": "recalled"})
        pres.reputation = max(0.0, pres.reputation - 0.2)
        w.president = None
        g["promises"] = []
        g["election_day"] = w.day + C.SPECIAL_ELECTION_DAYS
        g["campaign_open"] = False
    else:
        log.add(w.day, "recall_failed", f"President {pres.name} survived the recall vote: {yes} voted to remove, "
                f"{no} to keep ({share:.0%}, short of the {C.RECALL_SHARE:.0%} needed).", importance=5,
                people=[pres.id], yes=yes, no=no)
        for p in people:
            p.approval += 0.05


def on_president_died(w, log, pres_id):
    g = ensure(w)
    g["history"].append({"id": pres_id, "name": w.dead[pres_id]["given"] + " " + w.dead[pres_id]["family"],
                         "start": g["term_start"], "end": w.day, "how": "died in office"})
    g["promises"] = []
    g["petition"] = None
    g["recall_vote_day"] = None


def summary(w):
    g = ensure(w)
    pres = president(w)
    people = adults(w)
    approval = sum(p.approval for p in people) / max(1, len(people))
    return {
        "president": pres.name if pres else None,
        "term_start": label(g["term_start"]),
        "next_election": label(g["election_day"]),
        "days_to_election": g["election_day"] - w.day,
        "approval": round(approval, 3),
        "petition": ({"signatures": g["petition"]["signatures"], "needed": int(len(people) * C.PETITION_SHARE) + 1}
                     if g["petition"] else None),
        "recall_vote": label(g["recall_vote_day"]) if g.get("recall_vote_day") else None,
        "sales_tax": g["sales_tax"],
        "head_tax": g["head_tax"],
        "subsidies": {j: s["rate"] for j, s in g["subsidies"].items()},
        "price_cap": g["price_cap"],
        "treasury": round(w.treasury, 1),
        "money_supply": round(money_supply(w), 1),
        "minted": g["minted"],
        "price_level": round(g["price_level"], 3),
        "public_works": [{"kind": f["kind"], "region": f["region"], "status": f["status"]}
                         for f in w.facilities.values()],
        "candidates": [w.people[c["id"]].name for c in g["candidates"] if c["id"] in w.people],
        "promises": [p["text"] for p in g["promises"]],
    }
