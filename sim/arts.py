"""Art: songs, stories, carvings, paintings and tapestries.

Creative people work on art on their rest days. When a piece is finished
it gets a title in the native language, a subject drawn from real life
(their own losses and loves, the nation's disasters, the president), and
a quality that depends on talent, practice and luck.

Works spread region by region the way words do: songs and stories travel
fastest, carvings and paintings mostly stay near home. A song that mocks
the president lowers approval wherever it is sung; a song of praise
raises it. Popular works make their makers famous.
"""
from . import config as C
from . import language
from .economy import labor_rate
from .model import note

# subject -> title words, English title, verse lines (concepts, English), and its mood
SUBJECTS = {
    "flood": (["river", "anger"], "The River's Anger", [
        (["river", "anger", "house"], "The river in its anger took the house"),
        (["child", "water", "home"], "The child looks for home across the water"),
        (["rain", "day", "great", "hunger"], "Rain all the day, and after it great hunger")], "solemn"),
    "storm": (["sea", "storm"], "The Sea-Storm", [
        (["sea", "storm", "fisher", "death"], "The sea-storm took the fisher down"),
        (["wind", "house", "stone"], "The wind tore the stones from the house"),
        (["mother", "sea", "call"], "A mother calls out to the sea")], "solemn"),
    "drought": (["dry", "summer"], "The Dry Summer", [
        (["sun", "field", "dry"], "The sun burned the fields dry"),
        (["rain", "call", "people"], "The people call for rain"),
        (["grain", "rot", "hunger"], "The grain withers, and hunger follows")], "solemn"),
    "blight": (["grain", "rot"], "The Rotting Grain", [
        (["grain", "rot", "field"], "Rot in the grain, rot in the field"),
        (["bread", "hunger", "winter"], "No bread for the winter, only hunger")], "solemn"),
    "famine": (["great", "hunger"], "The Great Hunger", [
        (["bread", "child", "hunger"], "No bread, and the children hungry"),
        (["coin", "price", "bread"], "Coins will not buy the bread")], "solemn"),
    "harvest": (["harvest", "plenty"], "Harvest Plenty", [
        (["grain", "plenty", "field"], "Grain in plenty in the fields"),
        (["autumn", "bread", "house"], "Autumn bread in every house")], "joyful"),
    "love": (["marriage", "day"], "The Wedding Day", [
        (["friend", "marriage", "spring"], "My friend, my bride, in the spring"),
        (["home", "fire", "good"], "A good fire in our home")], "family"),
    "grief": (["death", "winter"], "Death in Winter", [
        (["death", "winter", "home"], "Death came in winter to our home"),
        (["old", "friend", "call"], "I call my old friend, who does not answer")], "solemn"),
    "child": (["birth", "spring"], "A Birth in Spring", [
        (["child", "sun", "new"], "A new child, a new sun"),
        (["mother", "child", "day"], "Mother and child, all the day")], "family"),
    "lost_house": (["house", "back"], "The House That Was", [
        (["house", "stone", "call"], "I call the stones of my lost house"),
        (["wind", "home", "old"], "The wind lives in our old home now")], "solemn"),
    "invention": (["new", "make"], "The New Way", [
        (["new", "make", "good"], "A new way, and well made"),
        (["old", "path", "back"], "The old path is behind us")], "joyful"),
    "election": (["choose", "day"], "Choosing Day", [
        (["people", "choose", "chief"], "The people choose their leader"),
        (["name", "call", "day"], "Names called out all the day")], "political"),
    "sea": (["sea", "wind"], "Sea Wind", [
        (["sea", "wind", "fisher"], "The sea wind for the fisher"),
        (["sun", "water", "good"], "Sun on the water, and all is good")], "nature"),
    "river": (["river", "day"], "River Days", [
        (["river", "field", "plenty"], "The river feeds the fields"),
        (["water", "path", "old"], "Water on the old path")], "nature"),
    "hill": (["hill", "wind"], "Wind on the Hill", [
        (["hill", "wind", "sheep"], "Wind on the hill among the sheep"),
        (["sun", "hill", "home"], "The sun sets on the hill, and on home")], "nature"),
    "field": (["field", "sun"], "Sun on the Fields", [
        (["field", "sun", "farmer"], "Sun on the fields and the farmer"),
        (["grain", "wind", "summer"], "Grain in the summer wind")], "nature"),
    "mountain": (["mountain", "snow"], "Mountain Snow", [
        (["mountain", "snow", "old"], "Old snow on the mountain"),
        (["iron", "stone", "miner"], "Iron and stone for the miner")], "nature"),
    "mock": (["chief", "thief"], "The Thieving Leader", [
        (["chief", "coin", "thief"], "Our leader is a thief of coins"),
        (["coin", "house", "hole"], "There is a hole in the coin-house"),
        (["people", "call", "back"], "The people will call the leader back")], "political"),
    "praise": (["good", "chief"], "The Good Leader", [
        (["chief", "good", "people"], "A good leader for the people"),
        (["bread", "plenty", "house"], "Bread aplenty in every house")], "political"),
}
NATURE = {"coast": "sea", "tidewater": "river", "piedmont": "hill", "valley": "field", "mountains": "mountain"}
KINDS = {"song": 0.35, "story": 0.25, "carving": 0.2, "painting": 0.2}
SPREAD = {"song": 0.10, "story": 0.07, "carving": 0.03, "painting": 0.03, "tapestry": 0.03}
ART_THRESHOLD = 18.0
MIN_CREATIVITY = 0.72


def ensure(w):
    a = w.arts
    if not a:
        a.update({"works": {}, "commissions": {}, "last_commission": -9999})
    return a


def wants_art(p, day):
    return p.age(day) >= 12 and p.traits["creativity"] >= MIN_CREATIVITY


def work_on(w, log, p):
    ensure(w)
    p.art_progress += p.traits["creativity"] * w.rng.uniform(0.6, 1.0)
    p.skills["art"] = p.skills.get("art", 0) + 1
    if p.art_progress >= ART_THRESHOLD or str(p.id) in w.arts["commissions"]:
        p.art_progress = 0.0
        create(w, log, p)


def _pick_subject(w, log, p):
    rng = w.rng
    arts = ensure(w)
    com = arts["commissions"].pop(str(p.id), None)
    if com:
        return "praise", True
    pres = w.people.get(w.president)
    options = {}
    if pres:
        if p.approval < 0.25:
            options["mock"] = 1.2
        elif p.approval > 0.88:
            options["praise"] = 0.5
    for day, text in reversed(p.life[-6:]):
        if w.day - day > 140:
            break
        if text.startswith("was widowed"):
            options["grief"] = 1.5
        elif text.startswith("married"):
            options["love"] = 1.0
        elif text.startswith("had "):
            options["child"] = 0.8
        elif text.startswith("lost the family house"):
            options["lost_house"] = 1.4
    recent = log.between(w.day - 60, w.day, 4)
    for e in recent:
        t = e["type"]
        key = {"flood": "flood", "storm": "storm", "drought": "drought", "harvest_blight": "blight",
               "election": "election", "invention": "invention", "scandal": "mock"}.get(t)
        if t == "hunger" and e["data"].get("count", 0) >= 20:
            key = "famine"
        if key == "mock" and not (pres and p.approval < 0.45):
            continue
        if key:
            options[key] = options.get(key, 0) + (0.9 if e.get("region") == p.region else 0.4)
    if w.day % C.DAYS_PER_YEAR // C.DAYS_PER_SEASON == 2:
        options["harvest"] = 0.4
    options[NATURE.get(p.region, "field")] = 0.5
    keys = list(options)
    return rng.choices(keys, weights=[options[k] for k in keys])[0], False


def _native(w, concepts, region):
    return [language.word(w, c, region) or c for c in concepts]


def create(w, log, p):
    rng = w.rng
    arts = ensure(w)
    subject, commissioned = _pick_subject(w, log, p)
    title_c, title_en, verses, mood = SUBJECTS[subject]
    kinds = dict(KINDS)
    if p.job == "weaver":
        kinds["tapestry"] = kinds.pop("painting")
    kind = rng.choices(list(kinds), weights=list(kinds.values()))[0]
    a, b = _native(w, title_c, p.region)
    title = (language._clip(a) + b).capitalize()
    quality = max(0.05, min(1.0, 0.45 * p.traits["creativity"] + 0.35 * min(1.0, p.skills.get("art", 0) / 60)
                            + rng.gauss(0.1, 0.15)))
    verse = []
    if kind in ("song", "story"):
        for concepts, english in rng.sample(verses, min(2, len(verses))):
            verse.append([" ".join(_native(w, concepts, p.region)).capitalize(), english])
    tone = mood if mood == "political" and subject in ("mock", "praise") else None
    wid = str(w.new_id())
    work = {"kind": kind, "artist": p.id, "artist_name": p.name, "region": p.region, "day": w.day,
            "subject": subject, "title": title, "title_en": title_en, "quality": round(quality, 2),
            "tone": subject if tone else None, "target": w.president if tone else None,
            "verse": verse, "popularity": {r: (0.15 * quality if r == p.region else 0.0) for r in w.regions},
            "famous": False, "commissioned": commissioned, "mood": mood}
    arts["works"][wid] = work
    note(p, w.day, f"made a {kind}, '{title}' ({title_en})")
    town = w.regions[p.region].town
    about = ""
    if subject == "mock":
        about = " It mocks the president."
    elif subject == "praise":
        about = " It praises the president." + (" The president paid for it." if commissioned else "")
    imp = 2 if quality >= 0.6 or tone else 1
    log.add(w.day, "artwork", f"{p.name} of {town} has made a {kind}, '{title}' ({title_en}).{about}",
            region=p.region, importance=imp, people=[p.id], work=wid, kind=kind, title=title,
            title_en=title_en, quality=work["quality"], subject=subject, verse=verse)
    w.count("artworks")
    return work


def weekly(w, log):
    arts = ensure(w)
    pres = w.people.get(w.president)
    for wid, work in list(arts["works"].items()):
        pop = work["popularity"]
        q = work["quality"]
        rate = SPREAD[work["kind"]] * (0.5 + q)
        new = {}
        for r in w.regions:
            a = pop.get(r, 0.0)
            near = max((pop.get(n, 0.0) for n in C.NEIGHBORS[r]), default=0.0)
            spill = 0.02 * near * q if work["kind"] in ("song", "story") else 0.004 * near * q
            a += rate * a * (1 - a) * (q > 0.35) + spill * (1 - a)
            a *= 0.985   # old favorites fade
            new[r] = min(1.0, a)
        work["popularity"] = new
    # people can only sing and talk about so many works at once: works compete
    for r in w.regions:
        total = sum(work["popularity"].get(r, 0.0) for work in arts["works"].values())
        if total > 1.5:
            f = 1.5 / total
            for work in arts["works"].values():
                work["popularity"][r] = work["popularity"].get(r, 0.0) * f
    for wid, work in list(arts["works"].items()):
        new = work["popularity"]
        q = work["quality"]
        avg = sum(new.values()) / len(new)
        if not work["famous"] and avg >= 0.3:
            work["famous"] = True
            artist = w.people.get(work["artist"])
            if artist:
                artist.reputation = min(1.0, artist.reputation + 0.15)
                note(artist, w.day, f"became famous for the {work['kind']} '{work['title']}'")
            log.add(w.day, "art_famous", f"The {work['kind']} '{work['title']}' ({work['title_en']}) by "
                    f"{work['artist_name']} is now known throughout {w.nation_name}.", importance=3,
                    people=[work["artist"]], work=wid)
        # mocking and praising songs move opinion wherever they are popular
        if work["tone"] and pres and work["target"] == pres.id:
            sign = -0.012 if work["tone"] == "mock" else 0.006
            for p in w.people.values():
                if p.age(w.day) >= C.ADULT_AGE:
                    p.approval = max(0.0, min(1.0, p.approval + sign * new.get(p.region, 0.0) * q))
        if avg < 0.01 and not work["famous"] and w.day - work["day"] > 2 * C.DAYS_PER_YEAR:
            del arts["works"][wid]


def popular_by_region(w, threshold=0.2):
    arts = ensure(w)
    out = {}
    for r in w.regions:
        best = None
        for wid, work in arts["works"].items():
            v = work["popularity"].get(r, 0.0)
            if v >= threshold and (best is None or v > best[1]):
                best = (wid, v)
        if best:
            out[r] = arts["works"][best[0]]
    return out


def commission(w, log, pres):
    arts = ensure(w)
    pool = [p for p in w.people.values() if p.traits["creativity"] >= MIN_CREATIVITY and p.id != pres.id
            and p.age(w.day) >= C.ADULT_AGE]
    if not pool:
        return False
    artist = max(pool, key=lambda p: p.reputation + p.traits["creativity"] + p.skills.get("art", 0) / 100)
    coins = round(labor_rate(w) * 25)
    if w.treasury < coins:
        return False
    w.treasury -= coins
    w.households[artist.household].coins += coins
    arts["commissions"][str(artist.id)] = {"by": pres.id, "day": w.day}
    arts["last_commission"] = w.day
    note(artist, w.day, f"was paid {coins} coins by President {pres.name} to make a work of praise")
    log.add(w.day, "commission", f"President {pres.name} has paid {artist.name} of {w.regions[artist.region].town} "
            f"{coins} coins to make a work in praise of the nation's leadership.", region=artist.region,
            importance=3, people=[pres.id, artist.id], coins=coins)
    return True
