# nation-sim

A small, peaceful, medieval nation that runs on its own. About 500 people
live, work, trade, marry, move and die by simple rules. Each person has
needs (food, shelter, work, family, friends, standing, faith) and picks
whatever they expect will make them most satisfied.

One run of 7 days = one week of nation time. Run it once a night and a
new week (and later, a new issue of the paper) appears each morning.

## Build stages

1. **Core simulation** (done): land, weather, citizens, needs, jobs, trade
   in coins, houses and builders, births, deaths, inheritance, migration.
2. **Government** (done): president, 6-month terms, campaigns with
   promises, elections, recall petitions and votes (25% to force a vote,
   70% to remove), market and head taxes, minting with slow inflation,
   subsidies, grain price caps, relief, public works (wells, granaries,
   mills, roads, public houses), and greedy presidents who may skim.
3. Language and inventions.
4. The paper.
5. Stats page.
6. Nightly timer.

## Running

```
docker compose run --rm sim found            # start a new nation
docker compose run --rm sim run --days 7     # advance one week
docker compose run --rm sim status           # summary
docker compose run --rm sim events --days 7  # what happened
```

Everything lives in `./data`: the nation (`world.json.gz`), the event log
(`events.db`), and dated snapshots for rewinding.

## Layout

- `sim/config.py` all the tuning numbers
- `sim/genesis.py` founding the nation
- `sim/economy.py` work, trade, building, eating
- `sim/society.py` needs, friendships, jobs, moving, marriage
- `sim/lifecycle.py` births and deaths
- `sim/weather.py` weather and natural events
- `sim/government.py` the president, elections, recalls, taxes and spending
- `sim/engine.py` the daily loop and weekly stats
- `sim/events.py` the event log the paper reads from
