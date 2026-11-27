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
3. **Language and inventions** (done): a core vocabulary from the start;
   new words coined the first time something happens (by joining old
   words, naming after a person, or from scratch); words spreading region
   by region; sound changes that start in one region and spread, making
   dialects; 14 medieval inventions devised by experienced workers that
   spread through the nation and improve work, food keeping, safety and
   children's health.
4. **The paper** (done): a weekly issue written by four citizen reporters
   (editor, government, land and markets, town and family), each with
   their own region and opinions. Front page, government round-up, land
   and weather, markets table, words and speech, editorial, letters from
   real citizens, births/marriages/deaths, comings and goings. Native
   words are woven in and explained the first time they appear. Saved as
   HTML plus a JSON copy for a future AI writer.
5. **Stats page** (done): the state of the nation, with small charts.
6. **Nightly timer** (done, set up on the server).
7. **Life, leisure and art** (done): every person keeps a record of their
   big moments, feeding obituaries and a weekly citizen profile. The paper
   follows running stories (petitions, campaigns with straw polls, hunger,
   scandal aftermath), recaps each president's term, tracks broken
   promises, visits one region a week, and looks back one year. A weekly
   rest day; taverns and a brewer trade, where opinions spread and
   quarrels start; harvest festivals and a midwinter feast paid for by
   the president, with wrestling, footraces and archery; a creativity
   trait and art (songs, stories, carvings, paintings, tapestries) with
   native titles and verses, which spread, compete, become famous and can
   mock or praise the president. Presidents may commission art or raise a
   statue of themselves.

## Running

```
docker compose run --rm sim found            # start a new nation
docker compose run --rm sim run --days 7     # advance one week
docker compose run --rm sim status           # summary
docker compose run --rm sim events --days 7  # what happened
docker compose up -d web                     # serve data/site (paper + stats)
```

Each `run` publishes a new issue of the paper and refreshes the stats page
in `data/site/`.

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
- `sim/language.py` vocabulary, new words, sound changes and dialects
- `sim/inventions.py` inventions and how they spread
- `sim/paper.py` the weekly paper
- `sim/site.py` the stats page and home page
- `sim/paper_extra.py` follow-ups, recaps, profiles, obituaries, sports, arts
- `sim/leisure.py` rest days, taverns, festivals and contests
- `sim/arts.py` art and artists
- `sim/upgrade.py` brings older saves up to date
- `sim/engine.py` the daily loop and weekly stats
- `sim/events.py` the event log the paper reads from
