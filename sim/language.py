"""The nation's language: a small vocabulary that grows and drifts.

- The nation starts with a core vocabulary of everyday words.
- When something new happens for the first time (the first election, the
  first granary, an invention) the people need a word for it. They coin
  one: by joining two words they already have, by naming it after a
  person, or from scratch.
- A new word starts in the region where it was coined and spreads through
  the nation week by week.
- Every so often the way people pronounce things shifts. A shift starts in
  one region and spreads to its neighbors over time. Regions that change
  at different times end up with different dialects.

The paper is written in English with these native words woven in.
"""
import re

from . import config as C
from . import names

# Everyday words the nation has from the start: concept -> English meaning.
CORE = {
    "sun": "sun", "moon": "moon", "water": "water", "river": "river", "sea": "sea",
    "hill": "hill", "mountain": "mountain", "field": "field", "forest": "forest",
    "rain": "rain", "snow": "snow", "storm": "storm", "wind": "wind", "stone": "stone",
    "grain": "grain", "bread": "bread", "fish": "fish", "sheep": "sheep", "cow": "cow",
    "wool": "wool", "wood": "wood", "iron": "iron", "fire": "fire", "house": "house",
    "path": "path", "wheel": "wheel", "hole": "hole", "fence": "fence", "net": "net",
    "mother": "mother", "father": "father", "child": "child", "friend": "friend",
    "elder": "elder", "chief": "leader", "people": "the people", "name": "name",
    "list": "list", "call": "call", "back": "back", "choose": "to choose", "day": "day",
    "coin": "coin", "price": "price", "gift": "gift", "thief": "thief", "new": "new",
    "dry": "dry", "rot": "rot", "plenty": "plenty", "hunger": "hunger", "anger": "anger",
    "keep": "to keep", "make": "to make", "good": "good", "great": "great", "old": "old",
    "spring": "spring", "summer": "summer", "autumn": "autumn", "winter": "winter",
    "farmer": "farmer", "fisher": "fisher", "herder": "herder", "woodcutter": "woodcutter",
    "quarrier": "quarrier", "miner": "miner", "smith": "smith", "weaver": "weaver",
    "builder": "builder", "market": "market", "home": "home", "death": "death",
    "birth": "birth", "marriage": "marriage", "harvest": "harvest",
    "ale": "ale", "song": "song", "game": "game",
}

# New concepts and how people might build a word for them from old ones.
NEW_CONCEPTS = {
    "president": ("president", ("chief", "people")),
    "election": ("election", ("choose", "day")),
    "candidate": ("candidate", ("name", "chief")),
    "petition": ("recall petition", ("name", "list")),
    "recall": ("recall vote", ("back", "call")),
    "scandal": ("theft from the treasury", ("coin", "thief")),
    "treasury": ("treasury", ("coin", "house")),
    "tax": ("tax", ("coin", "keep")),
    "mint": ("newly struck coin", ("new", "coin")),
    "subsidy": ("subsidy", ("gift", "coin")),
    "relief": ("relief for the hungry", ("bread", "gift")),
    "price_cap": ("price cap", ("price", "fence")),
    "well": ("public well", ("water", "hole")),
    "granary": ("granary", ("grain", "house")),
    "mill": ("grain mill", ("grain", "wheel")),
    "road": ("road", ("stone", "path")),
    "public_house": ("public house for the homeless", ("people", "house")),
    "drought": ("drought", ("dry", "summer")),
    "blight": ("blight", ("grain", "rot")),
    "flood": ("flood", ("river", "anger")),
    "blizzard": ("blizzard", ("snow", "storm")),
    "fish_run": ("great run of fish", ("fish", "plenty")),
    "famine": ("famine", ("great", "hunger")),
    "orphan": ("orphan taken in by others", ("child", "keep")),
    "newspaper": ("the weekly paper", ("people", "call")),
    "statue": ("statue", ("stone", "chief")),
    "festival": ("festival", ("great", "day")),
    "champion": ("champion", ("game", "chief")),
    "tavern": ("tavern", ("ale", "house")),
    "brewer": ("brewer", ("ale", "make")),
}

# Which event types first call for which concept.
EVENT_CONCEPTS = {
    "election": "election", "candidate": "candidate", "petition": "petition",
    "recall_called": "recall", "scandal": "scandal", "tax_up": "tax", "mint": "mint",
    "subsidy": "subsidy", "relief": "relief", "price_cap": "price_cap",
    "drought": "drought", "harvest_blight": "blight", "flood": "flood", "blizzard": "blizzard",
    "fish_run": "fish_run", "orphans_taken_in": "orphan",
    "festival": "festival", "contest": "champion", "tavern_quarrel": "tavern",
}
WORKS_CONCEPTS = {"well": "well", "granary": "granary", "mill": "mill", "road": "road",
                  "house": "public_house", "statue": "statue"}

# Ways pronunciation can shift: (plain description, pattern, replacement)
SOUND_CHANGES = [
    ("dropping the last vowel of longer words", r"(?<=[^aeiouy]{1})(?<=\w{4})[aeiouy]$", ""),
    ("softening k to ch before e and i", r"k(?=[ei])", "ch"),
    ("softening t to d between vowels", r"(?<=[aeiouy])t(?=[aeiouy])", "d"),
    ("softening p to f between vowels", r"(?<=[aeiouy])p(?=[aeiouy])", "f"),
    ("turning 'ou' into 'u'", r"ou", "u"),
    ("turning 'ae' into 'e'", r"ae", "e"),
    ("turning s into h at the start of words", r"^s(?=[aeiouy])", "h"),
    ("turning a into o before n and m", r"a(?=[nm])", "o"),
    ("turning 'ei' into 'i'", r"ei", "i"),
    ("dropping h after other consonants", r"(?<=[bdgkpt])h", ""),
    ("turning d into th at the end of words", r"d$", "th"),
    ("turning v into w", r"v", "w"),
]


def ensure(w):
    lang = getattr(w, "language", None)
    if lang:
        # newer versions added everyday words; give older nations those too
        missing = [c for c in CORE if c not in lang["words"]]
        if missing:
            used = _all_forms(w)
            for concept in missing:
                form = _fresh(w, used, syllables=w.rng.choice([1, 2]))
                lang["words"][concept] = {
                    "meaning": CORE[concept], "origin": None, "coined": None, "how": "old",
                    "forms": {r: form for r in w.regions}, "adoption": {r: 1.0 for r in w.regions},
                    "established": True}
        return lang
    lang = {"words": {}, "changes": [], "next_change_day": w.day + 400}
    w.language = lang
    rng = w.rng
    used = set()
    for concept, meaning in CORE.items():
        form = _fresh(w, used, syllables=rng.choice([1, 1, 2]))
        lang["words"][concept] = {
            "meaning": meaning, "origin": None, "coined": None, "how": "old",
            "forms": {r: form for r in w.regions}, "adoption": {r: 1.0 for r in w.regions},
            "established": True,
        }
    # the founding already gave the nation a president and a treasury
    for concept in ("president", "treasury"):
        form, how, parts = _coin_form(w, concept, None, used)
        lang["words"][concept] = {
            "meaning": NEW_CONCEPTS[concept][0], "origin": None, "coined": w.day, "how": how,
            "parts": parts, "forms": {r: form for r in w.regions},
            "adoption": {r: 1.0 for r in w.regions}, "established": True,
        }
    return lang


def word(w, concept, region=None):
    """The native word for a concept as spoken in a region (or its origin), or None."""
    entry = ensure(w)["words"].get(concept)
    if not entry:
        return None
    if region and region in entry["forms"]:
        return entry["forms"][region]
    if entry["origin"] and entry["origin"] in entry["forms"]:
        return entry["forms"][entry["origin"]]
    return next(iter(entry["forms"].values()))


def _all_forms(w):
    return {f for e in w.language["words"].values() for f in e["forms"].values()}


def _fresh(w, used, syllables=None):
    for _ in range(50):
        f = names.word(w.phonology, w.rng, syllables=syllables)
        if 2 <= len(f) <= 9 and f not in used:
            used.add(f)
            return f.lower()
    return f.lower()


def _clip(form):
    """Shorten a word for use as the first half of a compound."""
    if len(form) <= 4:
        return form
    m = re.match(r"^[^aeiouy]*[aeiouy]+[^aeiouy]?", form)
    return m.group(0) if m else form[:3]


def _coin_form(w, concept, region, used, person=None):
    rng = w.rng
    words = w.language["words"]
    parts_concepts = NEW_CONCEPTS.get(concept, (None, None))[1]
    roll = rng.random()
    if person is not None and roll < 0.5:
        form = person.given.lower()
        if len(form) > 5:
            form = _clip(form) + rng.choice(["en", "ar", "is", "o"])
        return form, "eponym", [person.name]
    if parts_concepts and roll < 0.75 and all(p in words for p in parts_concepts):
        a, b = (word(w, p, region) for p in parts_concepts)
        form = _clip(a) + b
        if form not in used:
            used.add(form)
            return form, "compound", list(parts_concepts)
    return _fresh(w, used, syllables=rng.choice([2, 2, 3])), "new", []


def coin(w, log, concept, meaning, region, person=None, invention=False):
    """Make a word for something new, starting in one region."""
    lang = ensure(w)
    if concept in lang["words"]:
        return lang["words"][concept]
    region = region or max(w.regions, key=lambda r: sum(1 for p in w.people.values() if p.region == r))
    used = _all_forms(w)
    form, how, parts = _coin_form(w, concept, region, used, person=person)
    entry = {"meaning": meaning, "origin": region, "coined": w.day, "how": how, "parts": parts,
             "forms": {r: form for r in w.regions},
             "adoption": {r: (0.3 if r == region else 0.0) for r in w.regions},
             "established": False}
    lang["words"][concept] = entry
    if how == "compound":
        lit = "-".join(lang["words"][p]["meaning"].replace("to ", "") for p in parts)
        origin = f"a joining of older words meaning '{lit}'"
    elif how == "eponym":
        origin = f"named after {parts[0]}"
    else:
        origin = "a word with no older roots"
    w.count("new_words")
    log.add(w.day, "new_word", f"A new word is heard in {w.regions[region].name}: '{form}', meaning {meaning}. "
            f"It is {origin}.", region=region, importance=2, concept=concept, word=form, how=how,
            meaning=meaning, parts=parts)
    return entry


# ---------------------------------------------------------------- weekly
def weekly(w, log, last_week_events):
    lang = ensure(w)
    for ev in last_week_events:
        concept = EVENT_CONCEPTS.get(ev["type"])
        if ev["type"] == "works_begun":
            concept = WORKS_CONCEPTS.get(ev["data"].get("kind"))
        if ev["type"] == "hunger" and ev["data"].get("count", 0) >= 20:
            concept = "famine"
        if ev["type"] in ("job_change", "first_job") and "brewer" in (ev["data"].get("new"), ev["data"].get("job")):
            concept = "brewer"
        if not concept or concept in lang["words"]:
            continue
        person = None
        if concept == "scandal" and ev["people"]:
            pres = w.people.get(ev["people"][0])
            if pres:
                person = pres
        coin(w, log, concept, NEW_CONCEPTS[concept][0], ev.get("region"), person=person)
    _spread_words(w, log)
    _sound_change(w, log)


def _spread_words(w, log):
    for concept, e in w.language["words"].items():
        if e["established"]:
            continue
        ad = e["adoption"]
        new = {}
        for r in w.regions:
            a = ad.get(r, 0.0)
            near = max((ad.get(n, 0.0) for n in C.NEIGHBORS[r]), default=0.0)
            a += 0.06 * a * (1 - a) + 0.02 * near * (1 - a)
            new[r] = min(1.0, a)
        e["adoption"] = new
        if all(v >= 0.5 for v in new.values()):
            e["established"] = True
            log.add(w.day, "word_established", f"The word '{word(w, concept)}' ({e['meaning']}) is now used "
                    "throughout the nation.", importance=1, concept=concept)


def _sound_change(w, log):
    lang = w.language
    rng = w.rng
    # spread changes already under way to neighboring regions
    for ch in lang["changes"]:
        if len(ch["regions"]) == len(w.regions):
            continue
        for r in w.regions:
            if r in ch["regions"]:
                continue
            if any(n in ch["regions"] for n in C.NEIGHBORS[r]) and rng.random() < 0.015:
                ch["regions"].append(r)
                _apply(w, ch, r)
                if len(ch["regions"]) == len(w.regions):
                    log.add(w.day, "sound_change_complete", f"The whole nation now speaks with the change "
                            f"that began in {w.regions[ch['origin']].name}: {ch['desc']}.", importance=2)
                else:
                    log.add(w.day, "sound_change_spread", f"The way of speaking that began in "
                            f"{w.regions[ch['origin']].name} ({ch['desc']}) has reached {w.regions[r].name}.",
                            region=r, importance=1)
    # start a new change now and then
    if w.day >= lang["next_change_day"]:
        lang["next_change_day"] = w.day + rng.randint(450, 700)
        done = {c["desc"] for c in lang["changes"]}
        options = [c for c in SOUND_CHANGES if c[0] not in done]
        if not options:
            return
        desc, pattern, repl = rng.choice(options)
        weights = {r: sum(1 for p in w.people.values() if p.region == r) + 1 for r in w.regions}
        origin = rng.choices(list(weights), weights=list(weights.values()))[0]
        ch = {"desc": desc, "pattern": pattern, "repl": repl, "origin": origin,
              "started": w.day, "regions": [origin]}
        lang["changes"].append(ch)
        examples = _apply(w, ch, origin)
        ex = ", ".join(f"'{a}' now sounds like '{b}'" for a, b in examples[:2])
        log.add(w.day, "sound_change", f"Young people in {w.regions[origin].name} have taken to "
                f"{desc}" + (f": {ex}" if ex else "") + ". Their elders grumble.",
                region=origin, importance=2, desc=desc)


def _apply(w, ch, region):
    examples = []
    for concept, e in w.language["words"].items():
        old = e["forms"].get(region)
        if not old:
            continue
        new = re.sub(ch["pattern"], ch["repl"], old)
        if new and new != old and len(new) >= 2:
            e["forms"][region] = new
            examples.append((old, new))
    w.rng.shuffle(examples)
    return examples


def dialect_words(w):
    """Words that are said differently in different parts of the nation."""
    out = []
    for concept, e in w.language["words"].items():
        forms = set(e["forms"].values())
        if len(forms) > 1:
            out.append((concept, e["meaning"], dict(e["forms"])))
    return out
