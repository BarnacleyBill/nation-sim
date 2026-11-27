"""The things that exist in the nation: people, households, houses, regions."""
import random
from dataclasses import dataclass, field, asdict, fields

from .calendar import age_years


@dataclass
class Person:
    id: int
    given: str
    family: str
    sex: str                      # "f" or "m"
    birth_day: int
    household: int
    region: str
    traits: dict
    job: str | None = None
    skills: dict = field(default_factory=dict)     # job -> days of experience
    job_pref: dict = field(default_factory=dict)   # job -> personal liking (0.8-1.2)
    spouse: int | None = None
    mother: int | None = None
    father: int | None = None
    children: list = field(default_factory=list)
    friends: dict = field(default_factory=dict)    # "id" -> feeling, -1 to 1
    needs: dict = field(default_factory=dict)
    satisfaction: float = 0.6
    mood: float = 0.6             # slow-moving satisfaction
    fed: float = 1.0              # recent share of meals eaten
    hunger: int = 0               # days in a row underfed
    clothing: int = 100           # days until clothes wear out
    reputation: float = 0.5
    pregnant_until: int | None = None
    fertile_after: int = 0
    widowed: bool = False
    income_ema: float = 0.0       # recent daily earnings
    job_since: int = 0
    approval: float = 0.6         # opinion of the current president, 0 to 1
    gov_effect: float = 0.0       # how government touched this person this week
    signed_petition: bool = False

    @property
    def name(self):
        return f"{self.given} {self.family}"

    def age(self, today):
        return age_years(self.birth_day, today)


@dataclass
class Household:
    id: int
    region: str
    members: list
    house: int | None
    coins: float
    inv: dict
    tool_days: float = 0.0
    founded: int = 0
    homeless_since: int | None = None


@dataclass
class House:
    id: int
    region: str
    built_day: int
    household: int | None = None


@dataclass
class Project:
    id: int
    region: str
    builder: int
    for_household: int | None
    progress: float = 0.0
    timber: float = 0.0
    stone: float = 0.0
    started: int = 0


@dataclass
class Region:
    key: str
    name: str
    town: str
    resources: dict
    weather: str = "fair"
    weather_until: int = 0
    effects: dict = field(default_factory=dict)   # name -> {"until": day, "mult": {...}}


@dataclass
class World:
    day: int
    seed: int
    nation_name: str
    phonology: dict
    name_pools: dict
    regions: dict
    people: dict
    households: dict
    houses: dict
    projects: dict
    prices: dict
    treasury: float
    president: int | None = None
    dead: dict = field(default_factory=dict)
    next_id: int = 1
    rng_state: list | None = None
    week: dict = field(default_factory=dict)        # counters for the current week
    last_trade: dict = field(default_factory=dict)  # good -> units traded yesterday
    avg_prices: dict = field(default_factory=dict)  # slow-moving "normal" price
    week_start_prices: dict = field(default_factory=dict)
    hazard: dict = field(default_factory=dict)      # region -> extra death risk this week
    sell_through: dict = field(default_factory=dict)  # good -> share of goods offered that sold
    demand: dict = field(default_factory=dict)        # good -> units households want per day (smoothed)
    gov: dict = field(default_factory=dict)           # government state, see government.py
    facilities: dict = field(default_factory=dict)    # "id" -> public works built or under way
    language: dict = field(default_factory=dict)      # see language.py
    inventions: dict = field(default_factory=dict)    # see inventions.py

    rng: random.Random = field(default=None, repr=False, compare=False)

    def new_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    # ------------------------------------------------------------ helpers
    def living_in(self, region):
        return [p for p in self.people.values() if p.region == region]

    def household_of(self, person):
        return self.households[person.household]

    def count(self, key, n=1):
        self.week[key] = self.week.get(key, 0) + n


# ---------------------------------------------------------------- saving
def _plain(obj):
    d = asdict(obj)
    return d


def world_to_dict(w):
    if w.rng is not None:
        st = w.rng.getstate()
        w.rng_state = [st[0], list(st[1]), st[2]]
    out = {}
    for f in fields(World):
        if f.name == "rng":
            continue
        v = getattr(w, f.name)
        if f.name in ("people", "households", "houses", "projects"):
            out[f.name] = {str(k): _plain(x) for k, x in v.items()}
        elif f.name == "regions":
            out[f.name] = {k: _plain(x) for k, x in v.items()}
        else:
            out[f.name] = v
    return out


def world_from_dict(d):
    d = dict(d)
    d["people"] = {int(k): Person(**v) for k, v in d["people"].items()}
    d["households"] = {int(k): Household(**v) for k, v in d["households"].items()}
    d["houses"] = {int(k): House(**v) for k, v in d["houses"].items()}
    d["projects"] = {int(k): Project(**v) for k, v in d["projects"].items()}
    d["regions"] = {k: Region(**v) for k, v in d["regions"].items()}
    d["dead"] = {int(k): v for k, v in d.get("dead", {}).items()}
    w = World(**d)
    w.rng = random.Random()
    if w.rng_state:
        st = w.rng_state
        w.rng.setstate((st[0], tuple(st[1]), st[2]))
    else:
        w.rng.seed(w.seed)
    return w
