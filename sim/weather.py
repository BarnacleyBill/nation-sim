"""Weather and natural events, rolled once a week for each region.

Ordinary weather only nudges work. Rare events (storms, droughts, floods,
blizzards, good and bad harvests, fish runs) can change a season and
always make the news.
"""
from . import config as C
from .calendar import season, week_of_year, DAYS_PER_YEAR

COASTAL = {"coast", "tidewater"}


def weekly(w, log):
    """Returns per-region multipliers on the daily chance of dying (cold snaps)."""
    rng = w.rng
    day = w.day
    s = season(day)
    first_week_of_season = week_of_year(day) % 13 == 1
    hazard = {}
    for key, region in w.regions.items():
        # drop finished effects
        for name in list(region.effects):
            if region.effects[name]["until"] <= day:
                del region.effects[name]
        # ordinary weather
        if s == "winter":
            kinds, weights = ["fair", "rain", "snow"], [45, 25, 30 if key == "mountains" else 15]
        elif s == "summer":
            kinds, weights = ["fair", "rain", "hot"], [55, 25, 20]
        else:
            kinds, weights = ["fair", "rain"], [55, 45]
        region.weather = rng.choices(kinds, weights=weights)[0]
        region.weather_until = day + 7
        if region.weather == "snow":
            region.effects["snow"] = {"until": day + 7, "mult": {"outdoor": 0.75}}
        town = region.town
        # rare events
        if key in COASTAL and s in ("summer", "autumn") and rng.random() < 0.035:
            destroyed = _damage_houses(w, key, 0.05 if key == "coast" else 0.025)
            region.effects["storm"] = {"until": day + 7, "mult": {"fisher": 0.0, "outdoor": 0.5}}
            log.add(day, "storm", f"A great storm struck {region.name}. "
                    f"{_houses_text(destroyed)} Fishing boats stayed ashore all week.",
                    region=key, importance=4, houses_destroyed=destroyed)
        if s == "summer" and "drought" not in region.effects and rng.random() < 0.012:
            weeks = rng.randint(4, 8)
            region.effects["drought"] = {"until": day + 7 * weeks, "mult": {"farmer": 0.45, "herder": 0.8}}
            log.add(day, "drought", f"Drought has settled over {region.name}; the fields are parched.",
                    region=key, importance=4, weeks=weeks)
        if s == "spring" and key in ("tidewater", "piedmont") and rng.random() < 0.02:
            destroyed = _damage_houses(w, key, 0.015)
            region.effects["flood"] = {"until": day + 21, "mult": {"farmer": 0.6, "outdoor": 0.8}}
            log.add(day, "flood", f"The rivers of {region.name} burst their banks. {_houses_text(destroyed)}",
                    region=key, importance=4, houses_destroyed=destroyed)
        if s == "winter" and key == "mountains" and rng.random() < 0.06:
            region.effects["blizzard"] = {"until": day + 7, "mult": {"outdoor": 0.3}}
            hazard[key] = 2.0
            log.add(day, "blizzard", f"A blizzard buried {region.name}; little work was done all week.",
                    region=key, importance=3)
        if s == "autumn" and first_week_of_season:
            roll = rng.random()
            if roll < 0.12:
                region.effects["bumper"] = {"until": day + 91, "mult": {"farmer": 1.35}}
                log.add(day, "harvest_good", f"Farmers in {region.name} expect a fine harvest this year.",
                        region=key, importance=3)
            elif roll < 0.17:
                region.effects["blight"] = {"until": day + 91, "mult": {"farmer": 0.55}}
                log.add(day, "harvest_blight", f"Blight has struck the grain in {region.name}; "
                        "the harvest will be poor.", region=key, importance=4)
        if key in COASTAL and rng.random() < 0.02:
            if rng.random() < 0.6:
                region.effects["fish_run"] = {"until": day + 14, "mult": {"fisher": 1.6}}
                log.add(day, "fish_run", f"Great shoals of fish have appeared off {region.name}.",
                        region=key, importance=2)
            else:
                region.effects["fish_gone"] = {"until": day + 21, "mult": {"fisher": 0.4}}
                log.add(day, "fish_gone", f"The fish have vanished from the waters of {region.name}.",
                        region=key, importance=3)
        if region.weather == "snow" and key not in hazard:
            hazard[key] = 1.3
    return hazard


def _damage_houses(w, region, chance):
    destroyed = 0
    for house in list(w.houses.values()):
        if house.region == region and w.rng.random() < chance:
            destroyed += 1
            if house.household and house.household in w.households:
                h = w.households[house.household]
                h.house = None
                h.homeless_since = w.day
            del w.houses[house.id]
    return destroyed


def _houses_text(n):
    if n == 0:
        return "No houses were lost."
    if n == 1:
        return "One house was destroyed."
    return f"{n} houses were destroyed."
