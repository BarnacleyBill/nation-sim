"""Fixed rules and starting numbers for the nation.

Everything that tunes how the world behaves lives here, so balancing the
simulation never means hunting through the logic files.
"""

# ---------------------------------------------------------------- calendar
DAYS_PER_WEEK = 7
WEEKS_PER_SEASON = 13
SEASONS = ["spring", "summer", "autumn", "winter"]
DAYS_PER_SEASON = DAYS_PER_WEEK * WEEKS_PER_SEASON      # 91
DAYS_PER_YEAR = DAYS_PER_SEASON * len(SEASONS)          # 364

# ---------------------------------------------------------------- ages
WORK_AGE = 14          # children start helping the household
ADULT_AGE = 16         # can marry, choose a job, move
ELDER_AGE = 60         # works at reduced pace
RETIRE_AGE = 70        # stops working
FERTILE_MIN, FERTILE_MAX = 16, 44
MAX_FRIENDS = 12

# ---------------------------------------------------------------- goods
GOODS = ["grain", "fish", "meat", "wool", "timber", "stone", "ore", "tools", "cloth", "ale"]
FOODS = ["grain", "fish", "meat"]
PERISHABLE = {"fish": 0.03, "meat": 0.012, "grain": 0.0008}  # share lost per day
START_PRICES = {
    "grain": 1.0, "fish": 1.1, "meat": 1.8, "wool": 1.2, "timber": 1.0,
    "stone": 1.2, "ore": 2.0, "tools": 10.0, "cloth": 5.0, "ale": 1.5,
}
PRICE_FLOOR = 0.3      # prices never fall below this share of the start price
PRICE_CEILING = 8.0    # ...or rise above this multiple of it

FOOD_PER_ADULT = 1.0   # food units eaten per day
FOOD_PER_CHILD = 0.6
TOOL_LIFE_DAYS = 120   # one tool lasts this many working days
TOOL_BONUS = 1.3       # output multiplier when working with tools
CLOTHING_LIFE = 150    # days a set of clothes lasts

# ---------------------------------------------------------------- jobs
# outputs: units produced per worker-day at full productivity
# resource: which regional resource the job draws on (None = workshop trade)
# season: which seasonal curve applies
# risk: daily chance of a fatal accident
JOBS = {
    "farmer":     {"outputs": {"grain": 1.15}, "resource": "farmland", "season": "crop", "risk": 0.000004},
    "fisher":     {"outputs": {"fish": 1.85}, "resource": "fishery", "season": "fish", "risk": 0.00002},
    "herder":     {"outputs": {"meat": 1.0, "wool": 0.6}, "resource": "pasture", "season": "herd", "risk": 0.000004},
    "woodcutter": {"outputs": {"timber": 3.0}, "resource": "forest", "season": "wood", "risk": 0.000015},
    "quarrier":   {"outputs": {"stone": 2.5}, "resource": "stone", "season": "flat", "risk": 0.000015},
    "miner":      {"outputs": {"ore": 1.6}, "resource": "ore", "season": "flat", "risk": 0.00003},
    "smith":      {"inputs": {"ore": 1.0, "timber": 0.5}, "outputs": {"tools": 0.5}, "resource": None, "season": "flat", "risk": 0.000004},
    "weaver":     {"inputs": {"wool": 2.0}, "outputs": {"cloth": 1.0}, "resource": None, "season": "flat", "risk": 0.000002},
    "builder":    {"outputs": {}, "resource": None, "season": "flat", "risk": 0.00001},
    "brewer":     {"inputs": {"grain": 1.5}, "outputs": {"ale": 2.0}, "resource": None, "season": "flat", "risk": 0.000002},
}

# How much each season helps each kind of work.
SEASON_CURVES = {
    "crop": {"spring": 0.5, "summer": 1.0, "autumn": 4.6, "winter": 0.0},
    "fish": {"spring": 1.0, "summer": 1.15, "autumn": 1.0, "winter": 0.55},
    "herd": {"spring": 1.1, "summer": 1.0, "autumn": 1.0, "winter": 0.8},
    "wood": {"spring": 1.0, "summer": 0.9, "autumn": 1.0, "winter": 1.1},
    "flat": {"spring": 1.0, "summer": 1.0, "autumn": 1.0, "winter": 1.0},
}

# Workers a region can support per point of a resource before returns shrink.
WORKERS_PER_RESOURCE = 30

# A house takes this much material and builder labor.
HOUSE_TIMBER = 8
HOUSE_STONE = 4
HOUSE_LABOR_DAYS = 24

# ---------------------------------------------------------------- regions
# Five regions shaped loosely like Virginia, east to west.
REGIONS = {
    "coast":     {"start_pop": 80,  "resources": {"farmland": 0.5, "fishery": 1.5, "pasture": 0.4, "forest": 0.4, "stone": 0.3, "ore": 0.0}},
    "tidewater": {"start_pop": 120, "resources": {"farmland": 1.2, "fishery": 1.0, "pasture": 0.6, "forest": 0.8, "stone": 0.2, "ore": 0.0}},
    "piedmont":  {"start_pop": 140, "resources": {"farmland": 1.4, "fishery": 0.2, "pasture": 1.0, "forest": 1.0, "stone": 0.8, "ore": 0.3}},
    "valley":    {"start_pop": 90,  "resources": {"farmland": 1.3, "fishery": 0.2, "pasture": 1.3, "forest": 0.8, "stone": 0.6, "ore": 0.4}},
    "mountains": {"start_pop": 70,  "resources": {"farmland": 0.4, "fishery": 0.3, "pasture": 0.8, "forest": 1.5, "stone": 1.5, "ore": 1.5}},
}
# Which regions border each other (people move between neighbors most easily).
NEIGHBORS = {
    "coast": ["tidewater"],
    "tidewater": ["coast", "piedmont"],
    "piedmont": ["tidewater", "valley"],
    "valley": ["piedmont", "mountains"],
    "mountains": ["valley"],
}

# ---------------------------------------------------------------- needs
NEEDS = ["food", "shelter", "work", "family", "social", "standing", "faith", "leisure"]
BASE_WEIGHTS = {"food": 3.0, "shelter": 2.0, "work": 1.5, "family": 1.5,
                "social": 1.0, "standing": 1.0, "faith": 0.5, "leisure": 0.8}
TRAITS = ["ambition", "greed", "piety", "sociability", "diligence", "warmth", "boldness", "creativity"]

# ---------------------------------------------------------------- rest and leisure
REST_DAY = 6                 # the last day of every week is a day off
WORK_BOOST = 7 / 6           # work days are a little more productive to make up for it
LIFE_RECORD_MAX = 30         # milestones kept per person

# ---------------------------------------------------------------- money
START_TREASURY = 2500
START_COINS_PER_PERSON = 45

# ---------------------------------------------------------------- government
TERM_DAYS = 182              # six months
CAMPAIGN_DAYS = 28           # candidates announce four weeks before the vote
SPECIAL_ELECTION_DAYS = 21   # after a recall or a death in office
PETITION_DAYS = 28           # how long a recall petition can gather names
PETITION_SHARE = 0.25        # share of adults who must sign to force a recall vote
RECALL_SHARE = 0.70          # share of votes needed to remove the president
START_SALES_TAX = 0.05       # share of every market sale paid to the treasury
MAX_SALES_TAX = 0.20

# Public works: labor_days sets the cost (paid out as wages), weeks the build time.
FACILITIES = {
    "well":    {"labor_days": 30,  "weeks": 3,  "name": "a public well"},
    "granary": {"labor_days": 80,  "weeks": 6,  "name": "a public granary"},
    "mill":    {"labor_days": 150, "weeks": 8,  "name": "a grain mill"},
    "road":    {"labor_days": 200, "weeks": 10, "name": "a new road"},
    "house":   {"labor_days": 0,   "weeks": 4,  "name": "a public house for a homeless family"},
    "statue":  {"labor_days": 60,  "weeks": 6,  "name": "a statue of the president"},
}
