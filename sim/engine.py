"""The daily loop that moves the nation forward."""
from . import config as C
from . import economy, society, lifecycle, weather, government, language, inventions, leisure, arts, upgrade
from .calendar import is_week_start, is_week_end, season, label


def tick(w, log):
    if is_week_start(w.day):
        w.hazard = weather.weekly(w, log)
        government.weekly(w, log)
        language.weekly(w, log, log.between(w.day - 7, w.day - 1))
        inventions.weekly(w, log)
        arts.weekly(w, log)
        w.week_start_prices = dict(w.prices)
        _season_notice(w, log)
    economy.produce(w, log)
    economy.build(w, log)
    economy.market(w, log)
    economy.consume(w, log)
    society.socialize(w)
    leisure.daily(w)
    if economy.is_rest_day(w.day):
        leisure.rest_day(w, log)
    society.update_needs(w)
    society.choose_jobs(w, log)
    society.consider_moves(w, log)
    society.courtship(w, log)
    lifecycle.daily(w, log, w.hazard)
    inventions.daily(w, log)
    if is_week_end(w.day):
        _week_end(w, log)
    w.day += 1


def run(w, log, days):
    upgrade.ensure_current(w)
    for _ in range(days):
        tick(w, log)
    log.flush()


def _season_notice(w, log):
    if w.day % C.DAYS_PER_SEASON == 0:
        log.add(w.day, "season", f"{season(w.day).capitalize()} has begun. ({label(w.day)})",
                importance=1)


def _week_end(w, log):
    for g in C.GOODS:
        old = w.week_start_prices.get(g, w.prices[g])
        change = (w.prices[g] - old) / old if old else 0
        if abs(change) >= 0.2:
            direction = "rose" if change > 0 else "fell"
            imp = 3 if g in C.FOODS and abs(change) >= 0.3 else 2
            log.add(w.day, "price_swing", f"The price of {g} {direction} {abs(change):.0%} this week, "
                    f"to {w.prices[g]:.2f} coins.", importance=imp, good=g,
                    change=round(change, 3), price=round(w.prices[g], 3))
    hungry = {}
    for p in w.people.values():
        if p.hunger >= 5:
            hungry[p.region] = hungry.get(p.region, 0) + 1
    for region, n in hungry.items():
        if n >= 5:
            log.add(w.day, "hunger", f"{n} people in {w.regions[region].name} are going hungry.",
                    region=region, importance=4 if n >= 20 else 3, count=n)
    log.weekly(w.day, weekly_stats(w))
    w.week = {}


def weekly_stats(w):
    people = list(w.people.values())
    pop = len(people)
    by_region = {k: 0 for k in w.regions}
    jobs = {}
    for p in people:
        by_region[p.region] += 1
        if p.job:
            jobs[p.job] = jobs.get(p.job, 0) + 1
    hhs = [h for h in w.households.values() if h.members]
    homeless = sum(1 for h in hhs if h.house is None)
    coins_held = sum(h.coins for h in hhs)
    food_days = []
    for h in hhs:
        F = economy.food_need(w, h)
        if F:
            food_days.append(economy.food_stock(h) / F)
    food_days.sort()
    wealth = sorted((h.coins for h in hhs), reverse=True)
    top = wealth[:max(1, len(wealth) // 10)]
    near_hunger = 0
    for h in hhs:
        F = economy.food_need(w, h)
        if F and economy.food_stock(h) / F < 5 and h.coins < 5 * F * w.prices["grain"]:
            near_hunger += 1
    mood = {}
    for k in w.regions:
        ps = [p for p in people if p.region == k]
        ad = [p for p in ps if p.age(w.day) >= 16]
        mood[k] = {"satisfaction": round(sum(p.satisfaction for p in ps) / len(ps), 3) if ps else 0,
                   "approval": round(sum(p.approval for p in ad) / len(ad), 3) if ad else 0}
    return {
        "richest_tenth_share": round(sum(top) / max(1.0, sum(wealth)), 3),
        "near_hunger_households": near_hunger,
        "region_mood": mood,
        "artworks": w.week.get("artworks", 0),
        "day": w.day,
        "label": label(w.day),
        "population": pop,
        "by_region": by_region,
        "households": len(hhs),
        "homeless_households": homeless,
        "vacant_houses": sum(1 for x in w.houses.values() if x.household is None),
        "births": w.week.get("births", 0),
        "deaths": w.week.get("deaths", 0),
        "marriages": w.week.get("marriages", 0),
        "migrations": w.week.get("migrations", 0),
        "houses_built": w.week.get("houses_built", 0),
        "satisfaction": round(sum(p.satisfaction for p in people) / pop, 3) if pop else 0,
        "prices": {g: round(v, 3) for g, v in w.prices.items()},
        "jobs": jobs,
        "coins_held": round(coins_held, 1),
        "treasury": round(w.treasury, 1),
        "median_food_days": round(food_days[len(food_days) // 2], 1) if food_days else 0,
        "hungry": sum(1 for p in people if p.hunger >= 5),
        "government": government.summary(w),
        "new_words": w.week.get("new_words", 0),
        "words_known": len(language.ensure(w)["words"]),
        "dialect_words": len(language.dialect_words(w)),
        "inventions": [k for k in inventions.ensure(w)],
    }
