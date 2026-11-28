"""The weekly paper, written by citizen reporters from the event log.

Everything printed comes from what actually happened in the simulation.
Reporters are real citizens with their own region, trade and opinions,
which shade how they write but never what the facts are. Quotes come from
real citizens and match what that citizen actually thinks.

Each issue is saved as an HTML page (and a JSON copy, so a different
writer, such as an AI model, can be swapped in later without touching the
simulation).
"""
import html
import json
import os
import random

from . import config as C
from . import language
from .calendar import label, season, year, week_of_year
from .inventions import INVENTIONS

BEATS = ["editor", "politics", "land", "people"]
BEAT_TITLES = {"editor": "Editor", "politics": "Government correspondent",
               "land": "Land and markets correspondent", "people": "Town and family correspondent"}


# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s))


def person_name(w, pid):
    p = w.people.get(pid)
    if p:
        return p.name
    d = w.dead.get(pid)
    if d:
        return f"{d['given']} {d['family']}"
    return "an unknown person"


def town(w, region):
    return w.regions[region].town if region in w.regions else "?"


def rname(w, region):
    return w.regions[region].name if region in w.regions else "?"


class Writer:
    """Weaves native words into the English, glossing each the first time it appears."""

    def __init__(self, w, rng):
        self.w = w
        self.rng = rng
        self.glossed = set()

    def word(self, concept, english, region=None):
        entry = language.ensure(self.w)["words"].get(concept)
        if not entry:
            return esc(english)
        if region and entry["adoption"].get(region, 0) < 0.4 and not entry["established"]:
            return esc(english)
        native = language.word(self.w, concept, region)
        if concept in self.glossed:
            return f"<i>{esc(native)}</i>"
        self.glossed.add(concept)
        return f"<i>{esc(native)}</i> ({esc(english)})"

    def pick(self, options):
        return self.rng.choice(options)


# ---------------------------------------------------------------- staff
def _choose_staff(w, rng, beat, taken):
    pool = [p for p in w.people.values()
            if 20 <= p.age(w.day) <= 65 and p.id != w.president and p.id not in taken]
    if not pool:
        return None
    pool.sort(key=lambda p: p.traits["sociability"] + p.traits["ambition"] * 0.7 + p.reputation * 0.5
              + rng.random() * 0.6, reverse=True)
    p = pool[0]
    return {"id": p.id, "name": p.name, "region": p.region, "beat": beat, "since": w.day}


def ensure(w, log):
    st = w.paper
    if not st:
        st.update({"issue": 0, "staff": {}, "founded": w.day})
    rng = w.rng
    changes = []
    taken = {s["id"] for s in st["staff"].values()}
    for beat in BEATS:
        cur = st["staff"].get(beat)
        reason = None
        if cur:
            p = w.people.get(cur["id"])
            if p is None:
                reason = "died"
            elif p.age(w.day) >= C.RETIRE_AGE:
                reason = "retired"
            elif p.id == w.president:
                reason = "became president"
        if cur is None or reason:
            new = _choose_staff(w, rng, beat, taken)
            if new:
                taken.add(new["id"])
                from .model import note
                note(w.people[new["id"]], w.day, f"became the paper's {BEAT_TITLES[beat].lower()}")
                if cur:
                    changes.append((cur, reason, new))
                st["staff"][beat] = new
    if "newspaper" not in language.ensure(w)["words"]:
        editor = st["staff"].get("editor")
        language.coin(w, log, "newspaper", "the weekly paper", editor["region"] if editor else None)
    return st, changes


def reporter(w, st, beat):
    s = st["staff"].get(beat) or st["staff"].get("editor")
    p = w.people.get(s["id"]) if s else None
    return s, p


def byline(w, st, beat):
    s, p = reporter(w, st, beat)
    if not s:
        return ""
    return f"By {esc(s['name'])}, {BEAT_TITLES[beat].lower()}, {esc(town(w, s['region']))}"


def lean(p):
    """How warmly a reporter writes about the government, from -1 to 1."""
    if not p:
        return 0.0
    return max(-1.0, min(1.0, (p.approval - 0.5) * 2.5))


# ---------------------------------------------------------------- quotes from real citizens
def quote(w, wr, region=None, about="president", exclude=()):
    """A short quote from a citizen whose real feelings match what they say."""
    pres = w.people.get(w.president)
    pool = [p for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE and p.id not in exclude
            and p.id != w.president and (region is None or p.region == region)]
    if not pool:
        return ""
    p = wr.rng.choice(pool)
    job = p.job or "retired"
    who = f"{esc(p.name)}, a {esc(job)} of {esc(town(w, p.region))}"
    h = w.households[p.household]
    if about == "president" and pres:
        a = p.approval
        pn = esc(pres.given)
        if a >= 0.75:
            line = wr.pick([f"{pn} has done right by us.", f"I'd vote for {pn} again tomorrow.",
                            f"Things are better than they were. I give {pn} the credit."])
        elif a >= 0.5:
            line = wr.pick([f"{pn} is doing well enough, I suppose.", "No complaints worth the breath.",
                            f"I'll wait and see what {pn} does next."])
        elif a >= 0.3:
            line = wr.pick([f"I expected more from {pn}.", "Promises are cheap.",
                            "We could do better, and we will, come the next vote."])
        else:
            line = wr.pick([f"{pn} should go, and the sooner the better.", "I've had my fill of this lot.",
                            f"I'd sign any paper that sends {pn} home."])
        return _said(line, who)
    if about == "life":
        if p.hunger >= 3:
            line = wr.pick(["We haven't had a full meal in days.", "The larder is bare and the children feel it."])
        elif h.house is None:
            line = wr.pick(["We have no roof of our own. We sleep where kin will have us.",
                            "Every family deserves a house. We are still waiting for ours."])
        elif p.satisfaction >= 0.85:
            line = wr.pick(["It's been a good season for us.", "We want for nothing just now, thank the weather."])
        elif p.satisfaction >= 0.7:
            line = wr.pick(["We get by.", "Work is steady and the family is well."])
        else:
            line = wr.pick(["It's a hard time to be alive in Vomi.".replace("Vomi", esc(w.nation_name)),
                            "Nothing comes easy this year."])
        return _said(line, who)
    return ""


def _said(line, who):
    if line.endswith("."):
        line = line[:-1] + ","
    return f'"{line}" said {who}.'


# ---------------------------------------------------------------- articles
def _group(events, *types):
    return [e for e in events if e["type"] in types]


def articles(w, st, events, wr):
    """Build every story for the issue. Returns list of dicts."""
    out = []
    pres = w.people.get(w.president)
    pol_s, pol_p = reporter(w, st, "politics")
    tilt = lean(pol_p)

    def pres_word(region=None):
        return wr.word("president", "president", region)

    # --- elections
    for e in _group(events, "election"):
        d = e["data"]
        winner = d["winner"]
        tally = sorted(((int(k), v) for k, v in d["tally"].items()), key=lambda x: -x[1])
        wn = person_name(w, winner)
        wp = w.people.get(winner)
        runner = tally[1] if len(tally) > 1 else None
        margin = tally[0][1] - (runner[1] if runner else 0)
        if d.get("reelected"):
            head = wr.pick([f"{wn} Re-elected", f"{wn} Keeps the Presidency", f"Another Term for {wn}"])
        else:
            head = wr.pick([f"{wn} Wins the Presidency", f"{wn} Elected President", f"New President: {wn}"])
        close = "a narrow" if margin <= max(5, d["turnout"] * 0.05) else "a comfortable" if margin < d["turnout"] * 0.3 else "a sweeping"
        paras = [f"{esc(wn)}" + (f", a {esc(wp.job or 'retired person')} from {esc(town(w, wp.region))}," if wp else "")
                 + f" has won {close} victory in this week's {wr.word('election', 'election', e['region'])}, "
                 f"taking {tally[0][1]} of {d['turnout']} votes cast."]
        if runner:
            parts = [f"{esc(person_name(w, k))} with {v}" for k, v in tally[1:]]
            others = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
            paras.append(f"Finishing behind were {others}. {d['turnout']} of {d['eligible']} adults turned out "
                         f"to vote.")
        if tilt > 0.3 and d.get("reelected"):
            paras.append("The result is a vote of confidence in a steady hand.")
        elif tilt < -0.3 and d.get("reelected"):
            paras.append("Whether another six months of the same is what the nation needs remains to be seen.")
        q = quote(w, wr, region=e["region"])
        if q:
            paras.append(q)
        out.append({"section": "front", "score": 100, "headline": head, "paras": paras, "beat": "politics"})

    for e in _group(events, "campaign"):
        cands = [esc(person_name(w, c)) for c in e["people"]]
        paras = [f"The race for the presidency is under way. Standing are {', '.join(cands[:-1])} and {cands[-1]}."
                 if len(cands) > 1 else f"{cands[0]} stands unopposed for the presidency."]
        for c in _group(events, "candidate"):
            proms = c["data"].get("promises") or []
            cid = c["people"][0]
            cp = w.people.get(cid)
            if not cp:
                continue
            ptxt = ("; ".join(esc(x) for x in proms)) or "nothing in particular"
            paras.append(f"<b>{esc(cp.name)}</b>, {int(cp.age(w.day))}, a {esc(cp.job or 'retired person')} of "
                         f"{esc(town(w, cp.region))}, promises {ptxt}.")
        g = w.gov
        paras.append(f"The vote will be held in {label(g['election_day'])}.")
        out.append({"section": "front", "score": 80, "headline": wr.pick(["The Race Is On", "Candidates Declare",
                                                                           "Campaign Season Opens"]),
                    "paras": paras, "beat": "politics"})

    for e in _group(events, "special_election"):
        out.append({"section": "government", "score": 70, "headline": "Special Election Called",
                    "paras": [esc(e["summary"])], "beat": "politics"})

    # --- recalls and scandal
    for e in _group(events, "scandal"):
        pn = person_name(w, e["people"][0])
        coins = e["data"].get("coins", 0)
        paras = [f"{pres_word(e['region'])} {esc(pn)} has been found to have taken {coins:.0f} coins from "
                 f"the {wr.word('treasury', 'treasury')} for their own household."]
        if "scandal" in language.ensure(w)["words"]:
            entry = language.ensure(w)["words"]["scandal"]
            if entry["how"] == "eponym":
                paras.append(f"Already the word <i>{esc(language.word(w, 'scandal'))}</i> is being used "
                             "in the markets to mean stealing from the public purse.")
        q = quote(w, wr)
        if q:
            paras.append(q)
        out.append({"section": "front", "score": 95, "headline": wr.pick([f"Scandal: {pn} Took From the Treasury",
                                                                          "Treasury Coins Found Missing"]),
                    "paras": paras, "beat": "politics"})
    for e in _group(events, "petition"):
        starter = person_name(w, e["people"][0])
        pn = person_name(w, e["people"][1]) if len(e["people"]) > 1 else "the president"
        need = int(len([p for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE]) * C.PETITION_SHARE) + 1
        paras = [f"{esc(starter)} of {esc(rname(w, e['region']))} has begun a {wr.word('petition', 'recall petition', e['region'])} "
                 f"against {esc(pn)}. It needs {need} names within four weeks to force a vote."]
        q = quote(w, wr, region=e["region"])
        if q:
            paras.append(q)
        out.append({"section": "front", "score": 75, "headline": wr.pick(["Petition to Recall the President",
                                                                          "Names Gathered Against the President"]),
                    "paras": paras, "beat": "politics"})
    for e in _group(events, "recall_called", "recalled", "recall_failed", "petition_failed"):
        heads = {"recall_called": "Recall Vote Called", "recalled": "President Recalled",
                 "recall_failed": "President Survives Recall", "petition_failed": "Recall Petition Falls Short"}
        scores = {"recall_called": 85, "recalled": 100, "recall_failed": 90, "petition_failed": 50}
        out.append({"section": "front" if scores[e["type"]] >= 80 else "government", "score": scores[e["type"]],
                    "headline": heads[e["type"]], "paras": [esc(e["summary"])], "beat": "politics"})

    # --- government actions (grouped into one round-up)
    gov_lines = []
    for e in _group(events, "works_begun", "works_done", "relief", "subsidy", "subsidy_ended", "price_cap",
                    "price_cap_ended", "mint", "tax_up", "tax_down", "promise_kept", "promise_broken", "works_stalled",
                    "invention_reward_offered", "subsidy_lapsed"):
        text = esc(e["summary"])
        if e["type"] == "works_begun":
            kind = e["data"].get("kind")
            concept = {"house": "public_house"}.get(kind, kind)
            text = (f"President {esc(person_name(w, e['people'][0]))} has ordered "
                    f"{wr.word(concept, C.FACILITIES[kind]['name'], e['region'])} built in {esc(rname(w, e['region']))}, "
                    f"at a cost of {e['data'].get('cost', 0):.0f} coins.")
        if e["type"] == "tax_up":
            text = text.replace("raised taxes", f"raised {wr.word('tax', 'taxes')}")
        gov_lines.append(text)
    if gov_lines:
        paras = list(gov_lines)
        g = w.gov
        paras.append(f"The {wr.word('treasury', 'treasury')} now holds {w.treasury:.0f} coins. "
                     f"The market tax stands at {g['sales_tax']:.0%}"
                     + (f", with a head tax of {g['head_tax']:.2f} coins a week on every adult." if g["head_tax"] else "."))
        if tilt > 0.4:
            paras.append("It has been a busy week at the top, and much of it for the good.")
        elif tilt < -0.4:
            paras.append("Whether the public purse is being spent wisely is a question many are asking.")
        out.append({"section": "government", "score": 40 + 5 * len(gov_lines), "headline":
                    wr.pick(["From the President's Table", "This Week in Government", "Orders and Decrees"]),
                    "paras": paras, "beat": "politics"})

    # --- the land: disasters and plenty
    for e in _group(events, "storm", "drought", "flood", "blizzard", "harvest_blight", "harvest_good",
                    "fish_run", "fish_gone"):
        heads = {"storm": "Great Storm Strikes {r}", "drought": "Drought in {r}", "flood": "Floods in {r}",
                 "blizzard": "Blizzard Buries {r}", "harvest_blight": "Blight on the Grain in {r}",
                 "harvest_good": "Fine Harvest Expected in {r}", "fish_run": "Fish Run off {r}",
                 "fish_gone": "Fish Vanish from {r}"}
        concepts = {"drought": "drought", "flood": "flood", "blizzard": "blizzard", "harvest_blight": "blight",
                    "fish_run": "fish_run"}
        r = e["region"]
        body = esc(e["summary"])
        if e["type"] in concepts:
            called = wr.word(concepts[e['type']], e['type'].replace('harvest_', '').replace('_', ' '), r)
            if called.startswith("<i>"):
                body += f" Folk there are calling it {called}."
        paras = [body]
        q = quote(w, wr, region=r, about="life")
        if q and e["type"] in ("storm", "drought", "flood", "harvest_blight", "fish_gone"):
            paras.append(q)
        score = {"storm": 70, "drought": 65, "flood": 70, "blizzard": 55, "harvest_blight": 65,
                 "harvest_good": 40, "fish_run": 30, "fish_gone": 40}[e["type"]]
        out.append({"section": "land", "score": score, "headline": heads[e["type"]].format(r=rname(w, r)),
                    "paras": paras, "beat": "land"})
    hunger = _group(events, "hunger")
    if hunger:
        by_region = {}
        for e in hunger:
            by_region[e["region"]] = max(by_region.get(e["region"], 0), e["data"].get("count", 0))
        worst = max(by_region, key=by_region.get)
        paras = [f"Hunger has been reported this week in {', '.join(esc(rname(w, r)) for r in by_region)}. "
                 f"The worst is in {esc(rname(w, worst))}, where {by_region[worst]} people are going without "
                 "enough to eat."]
        q = quote(w, wr, region=worst, about="life")
        if q:
            paras.append(q)
        from .paper_extra import hunger_weeks
        wk = hunger_weeks(st, worst)
        if wk > 1:
            paras.append(f"It is the {wk}{'th' if 10 <= wk % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(wk % 10, 'th')} "
                         f"week running that {esc(rname(w, worst))} has gone short.")
        big = by_region[worst] >= 20
        out.append({"section": "front" if big else "land", "score": 85 if big else 45,
                    "headline": (f"Famine in {rname(w, worst)}" if big
                                 else f"Hunger in {rname(w, worst)}"),
                    "paras": paras, "beat": "land"})

    # --- inventions
    for e in _group(events, "invention"):
        key = e["data"]["invention"]
        spec = INVENTIONS[key]
        inv = w.people.get(e["people"][0])
        native = language.word(w, key, e["region"])
        paras = [esc(e["summary"]),
                 f"The new way is already being called <i>{esc(native)}</i> in {esc(rname(w, e['region']))}."
                 if native else ""]
        rew = _group(events, "invention_reward")
        for r_ in rew:
            if r_["people"] and r_["people"][0] == e["people"][0]:
                paras.append(esc(r_["summary"]))
        out.append({"section": "front", "score": 72, "headline": wr.pick([f"A Better {spec['short'].title()}",
                                                                         f"New Invention: The {spec['short'].title()}"]),
                    "paras": [p for p in paras if p], "beat": "land"})
    for e in _group(events, "invention_spread"):
        out.append({"section": "land", "score": 25, "headline": "A New Way Takes Hold",
                    "paras": [esc(e["summary"])], "beat": "land"})

    # --- notable deaths
    for e in _group(events, "death"):
        if e["importance"] >= 3:
            d = w.dead.get(e["people"][0], {})
            was_pres = e["data"].get("was_president")
            head = (f"President {person_name(w, e['people'][0])} Dies" if was_pres
                    else f"{person_name(w, e['people'][0])} Dies at {e['data'].get('age')}")
            out.append({"section": "front" if was_pres else "people", "score": 100 if was_pres else 35,
                        "headline": head, "paras": [esc(e["summary"])], "beat": "people"})

    for e in _group(events, "orphans_taken_in"):
        out.append({"section": "people", "score": 30, "headline": "Orphans Find a Home",
                    "paras": [esc(e["summary"])], "beat": "people"})
    for e in _group(events, "founding"):
        out.append({"section": "front", "score": 110, "headline": f"A Nation Is Born: {w.nation_name}",
                    "paras": [esc(e["summary"])], "beat": "editor"})
    return out


# ---------------------------------------------------------------- regular sections
def markets(w, stats_prev, wr):
    rows = []
    prev = (stats_prev or {}).get("prices", {})
    for g in C.GOODS:
        now = w.prices[g]
        old = prev.get(g)
        if old:
            ch = (now - old) / old
            move = "steady" if abs(ch) < 0.03 else (f"up {ch:.0%}" if ch > 0 else f"down {-ch:.0%}")
        else:
            move = ""
        rows.append((g, f"{now:.2f}", move))
    return rows


def weather_lines(w, wr):
    words = {"fair": "fair", "rain": "rain", "snow": "snow", "hot": "hot and dry"}
    lines = []
    for key, r in w.regions.items():
        extra = [k for k in r.effects if k not in ("snow",)]
        notes = {"storm": "storm", "drought": "drought", "flood": "flooding", "blizzard": "blizzard",
                 "bumper": "a fine crop coming", "blight": "blight in the fields", "fish_run": "fish running",
                 "fish_gone": "no fish"}
        extra_txt = ", ".join(notes[x] for x in extra if x in notes)
        lines.append(f"<b>{esc(r.name)}</b>: {words.get(r.weather, r.weather)}"
                     + (f"; {extra_txt}" if extra_txt else ""))
    return lines


def announcements(w, events):
    births, marriages, deaths = [], [], []
    for e in events:
        if e["type"] == "birth":
            births.append(esc(e["summary"]))
        elif e["type"] == "marriage":
            marriages.append(esc(e["summary"]))
        elif e["type"] == "death":
            deaths.append(esc(e["summary"]))
    return births, marriages, deaths


def comings_goings(events):
    return [esc(e["summary"]) for e in events if e["type"] in ("household_moved", "left_home", "house_built")]


def words_corner(w, events, wr):
    lines = []
    for e in events:
        if e["type"] == "new_word":
            d = e["data"]
            lines.append(f"<i>{esc(d['word'])}</i>, meaning {esc(d['meaning'])}. First heard in "
                         f"{esc(rname(w, e['region']))}; " + esc(e["summary"].split(". It is ")[-1]))
        elif e["type"] in ("sound_change", "sound_change_complete"):
            lines.append(esc(e["summary"]))
    if not lines:
        dial = language.dialect_words(w)
        if dial and wr.rng.random() < 0.6:
            concept, meaning, forms = wr.rng.choice(dial)
            parts = {}
            for r, f in forms.items():
                parts.setdefault(f, []).append(rname(w, r))
            said = "; ".join(f"<i>{esc(f)}</i> in {esc(', '.join(rs))}" for f, rs in parts.items())
            lines.append(f"Did you know? The word for {esc(meaning)} is said differently across the nation: {said}.")
    return lines


def _letter_options(w, p, week_events, price_moves, pres):
    """Every letter this citizen could truthfully write this week, as (kind, text)."""
    out = []
    h = w.households[p.household]
    town_ = esc(town(w, p.region))
    region_ = esc(rname(w, p.region))
    pn = esc(pres.name) if pres else None
    # their own week
    for day, text in reversed(p.life[-5:]):
        if w.day - day > 21:
            break
        if text.startswith("had "):
            out.append(("parent", wr_pick_static(p.id, [
                f"Sir, our family has {esc(text[4:])} this month. I write so that everyone in {town_} may know it, "
                "and wish the child well.",
                f"Sir, we have {esc(text[4:])}, and both are well. My thanks to the neighbors who brought bread "
                "while we were busy."])))
        elif text.startswith("married "):
            spouse = esc(text[len("married "):].split(" in ")[0])
            out.append(("wedding", wr_pick_static(p.id, [
                f"Sir, I was married this month to {spouse}. My thanks to all who came, and to both our families "
                "for their kindness.",
                f"Sir, {spouse} and I are wed. We hope to keep a house as happy as the ones we grew up in.",
                f"Sir, let it be known that {spouse} has done me the honor of marrying me. "
                f"There is no luckier soul in {town_}."])))
        elif text.startswith("moved into a new house built by "):
            b = esc(text[len("moved into a new house built by "):])
            out.append(("house", f"Sir, after a long wait my household has a roof of its own, built by {b}. "
                                 "I could not ask for better work."))
        elif text.startswith("was given a public house"):
            out.append(("public_house", "Sir, my family has been given a public house. Whatever else is said of "
                                        "the government, it did right by us."))
        elif text.startswith("lost the family house"):
            out.append(("lost_house", "Sir, the weather took our house. We are lodging where we can. I ask any "
                                      "builder with time to spare to remember us."))
        elif text.startswith("was widowed"):
            out.append(("grief", f"Sir, I have lost my spouse. I want to thank my neighbors in {town_}, who have "
                                 "not let me eat alone."))
        elif text.startswith("won "):
            out.append(("champion", f"Sir, I thank everyone who cheered at the festival. I will defend the title "
                                    "next year, and I hope to see the same crowd."))
        elif text.startswith("made a "):
            work = esc(text[len("made a "):])
            out.append(("artist", f"Sir, I have finished a {work}. Anyone in {region_} who would like to hear or "
                                  "see it need only ask."))
        elif text.startswith("came up with "):
            out.append(("inventor", "Sir, I have found a better way of doing my work, and I will gladly show it "
                                    "to anyone in my trade who asks."))
    # trouble at home
    if h.house is None and h.homeless_since is not None and w.day - h.homeless_since > 28:
        weeks = (w.day - h.homeless_since) // 7
        out.append(("homeless", f"Sir, my household has been without a house of our own for {weeks} weeks. "
                                f"We are not idle people. I ask the {'president' if pres else 'government'} what is "
                                "to be done for families like mine."))
    if p.hunger >= 4:
        out.append(("hunger", "Sir, there is not enough bread on our table. I write so that those with full "
                              "stores will remember their neighbors."))
    # what happened in their region and their trade
    for e in week_events:
        if e.get("region") != p.region:
            continue
        t = e["type"]
        if t == "storm" and p.job == "fisher":
            out.append(("storm", "Sir, a week ashore is a week without fish. We fishers ask for patience from "
                                 "those who buy from us."))
        elif t == "fish_run" and p.job == "fisher":
            out.append(("fish_run", "Sir, the nets have not been so full in years. Come down to the water while "
                                    "the fish are cheap."))
        elif t in ("harvest_blight", "drought") and p.job == "farmer":
            out.append(("bad_crop", f"Sir, the fields of {region_} are failing us this year. I ask those who can "
                                    "to put grain aside for the winter."))
        elif t == "harvest_good" and p.job == "farmer":
            out.append(("good_crop", f"Sir, the grain in {region_} stands taller than I have ever seen it. "
                                     "There will be bread enough this winter."))
        elif t == "works_begun" and pres:
            kind = e["data"].get("kind")
            what = esc(C.FACILITIES.get(kind, {}).get("name", "new works"))
            cost = e["data"].get("cost", 0)
            if p.approval >= 0.55:
                out.append(("works_praise", f"Sir, {what} for {region_} is long overdue. I thank President {pn} "
                                            "for seeing it done."))
            elif p.approval < 0.4:
                out.append(("works_grumble", f"Sir, {cost:.0f} coins for {what} in {region_}. I would like to know "
                                             "who asked for it, and who will pay."))
    # prices
    g = price_moves.get("grain")
    if g is not None and abs(g) >= 0.12:
        if g < 0 and p.job == "farmer":
            out.append(("price_low", wr_pick_static(p.id, [
                f"Sir, grain fetches {abs(g):.0%} less than it did a week ago. A farmer cannot live on such prices.",
                f"Sir, another week, another fall in the price of grain, {abs(g):.0%} this time. Who will pay a fair "
                "price for honest work?"])))
        elif g < 0 and p.job and p.job not in ("farmer",):
            out.append(("price_cheap", wr_pick_static(p.id, [
                "Sir, bread is cheaper this week than I can remember. Long may it last.",
                "Sir, with grain this cheap, my family eats better than it has in years. I thank the farmers."])))
        elif g > 0 and p.job != "farmer":
            out.append(("price_dear", f"Sir, grain costs {g:.0%} more than last week. How are working families "
                                      "to keep up?"))
    # opinions of the president
    if pres and p.approval < 0.2:
        out.append(("against", wr_pick_static(p.id, [
            f"Sir, I have lost all faith in President {pn}. The sooner the people are asked again, the better.",
            f"Sir, I would like it known that not everyone in {region_} is content to be governed by {pn}."])))
    elif pres and p.approval > 0.9:
        out.append(("for", wr_pick_static(p.id, [
            f"Sir, amid all the grumbling, let one voice say that President {pn} has served us well.",
            f"Sir, I write only to thank President {pn} for a fair season."])))
    if p.job and w.gov.get("subsidies", {}).get(p.job):
        out.append(("subsidy", f"Sir, as a {esc(p.job)} I am grateful for the subsidy. It has kept my family's "
                               "hearth warm."))
    return out


def wr_pick_static(seed, options):
    return options[seed % len(options)]


def letters(w, st, wr, week_events=(), price_moves=None, max_letters=2):
    """Letters from citizens with something real to say.

    Every possible letter in the nation is gathered first. Kinds the paper has not printed in its last
    few issues come first, no kind appears twice in an issue, and nobody writes in two issues running.
    """
    pres = w.people.get(w.president)
    price_moves = price_moves or {}
    staff = {s["id"] for s in st["staff"].values()}
    recent_kinds = st.setdefault("recent_letter_kinds", [])
    recent_writers = set(st.setdefault("recent_letter_writers", []))
    pool = []
    for p in w.people.values():
        if p.age(w.day) < C.ADULT_AGE or p.id == w.president or p.id in staff or p.id in recent_writers:
            continue
        for kind, text in _letter_options(w, p, week_events, price_moves, pres):
            pool.append((kind, text, p))
    wr.rng.shuffle(pool)
    # fresh kinds first; among those, rarer kinds before common ones
    counts = {}
    for kind, _, _ in pool:
        counts[kind] = counts.get(kind, 0) + 1
    pool.sort(key=lambda x: (x[0] in recent_kinds, counts[x[0]]))
    out, kinds, households, writers = [], set(), set(), []
    for kind, text, p in pool:
        if len(out) >= max_letters:
            break
        if kind in kinds or p.household in households:
            continue
        out.append((text, f"{esc(p.name)}, {esc(p.job or 'retired')}, {esc(town(w, p.region))}"))
        kinds.add(kind)
        households.add(p.household)
        writers.append(p.id)
        if p.spouse:
            writers.append(p.spouse)   # a couple won't both write about the same wedding
    if not out and "content" not in recent_kinds and wr.rng.random() < 0.5:
        happy = [p for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE and p.satisfaction > 0.88
                 and p.id not in staff and p.id not in recent_writers]
        if happy:
            p = wr.rng.choice(happy)
            out.append((f"Sir, I write simply to say that life in {esc(town(w, p.region))} is good this season, "
                        "and I wish the same for my countrymen.",
                        f"{esc(p.name)}, {esc(p.job or 'retired')}, {esc(town(w, p.region))}"))
            kinds.add("content")
            writers.append(p.id)
    st["recent_letter_kinds"] = (recent_kinds + sorted(kinds))[-6:]
    st["recent_letter_writers"] = (st["recent_letter_writers"] + writers)[-12:]
    return out


def editorial(w, st, stats, wr):
    s, p = reporter(w, st, "editor")
    if not p:
        return None
    pres = w.people.get(w.president)
    hungry = stats.get("hungry", 0)
    homeless = stats.get("homeless_households", 0)
    bits = []
    if hungry >= 15:
        bits.append(f"{hungry} of our people are going hungry. No nation can call itself well while that is so.")
    if homeless >= 5:
        bits.append(f"{homeless} households have no house of their own. Our builders and our "
                    f"{'president' if pres else 'government'} must do better.")
    if pres:
        t = lean(p)
        if t > 0.4:
            bits.append(f"This paper believes President {esc(pres.name)} has the nation on a good course.")
        elif t < -0.4:
            bits.append(f"This paper does not believe President {esc(pres.name)} is serving the nation as well "
                        "as the nation deserves.")
    if not bits:
        return None
    return {"paras": bits, "by": f"{esc(s['name'])}, editor"}


# ---------------------------------------------------------------- render
CSS = """
body{margin:0;background:#efe7d6;color:#1d1a16;font-family:Georgia,'Times New Roman',serif;line-height:1.45}
.page{max-width:980px;margin:0 auto;padding:18px 16px 60px;background:#f7f1e3;box-shadow:0 0 0 1px #d8ccb3}
.mast{text-align:center;border-bottom:4px double #1d1a16;padding-bottom:8px;margin-bottom:6px}
.mast h1{font-size:56px;letter-spacing:2px;margin:6px 0 0;font-variant:small-caps;font-weight:700}
.mast .sub{font-style:italic}
.dateline{display:flex;justify-content:space-between;font-size:13px;border-bottom:1px solid #1d1a16;
  padding:4px 0;margin-bottom:14px;flex-wrap:wrap;gap:6px}
h2{font-size:26px;line-height:1.15;margin:0 0 4px}
h3{font-size:19px;line-height:1.2;margin:0 0 3px}
.by{font-size:12px;font-style:italic;color:#4a4237;margin-bottom:6px}
.lead{border-bottom:1px solid #b9ab8f;padding-bottom:12px;margin-bottom:12px}
.lead h2{font-size:34px}
.cols{column-count:2;column-gap:28px;column-rule:1px solid #cbbd9f}
.story{break-inside:avoid;margin-bottom:16px}
.section{margin-top:20px;border-top:2px solid #1d1a16;padding-top:6px}
.section>h4{font-variant:small-caps;letter-spacing:1px;font-size:17px;margin:0 0 8px}
table{border-collapse:collapse;font-size:14px;width:100%}
td,th{border-bottom:1px solid #d4c7aa;padding:3px 6px;text-align:left}
ul{padding-left:18px;margin:4px 0}
li{margin-bottom:4px}
.letter{font-style:italic;margin-bottom:10px}
.letter .sig{font-style:normal;font-size:13px;text-align:right}
.staff{font-size:12px;color:#4a4237}
.nav{font-size:13px;text-align:center;margin-top:24px}
a{color:#5a2d0c}
@media(max-width:700px){.cols{column-count:1}.mast h1{font-size:40px}.lead h2{font-size:27px}}
"""


def render(w, st, issue, data):
    paper_word = language.word(w, "newspaper") or "Gazette"
    title = f"The {paper_word.capitalize()}"
    h = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<title>{esc(title)}, issue {issue}</title><style>{CSS}</style></head><body><div class='page'>"]
    h.append(f"<div class='mast'><h1>{esc(title)}</h1><div class='sub'>The weekly paper of the nation of "
             f"{esc(w.nation_name)}</div></div>")
    h.append(f"<div class='dateline'><span>Issue {issue}</span><span>{esc(data['date'])}</span>"
             f"<span>Population {data['population']}</span></div>")
    stories = data["stories"]
    front = [s for s in stories if s["section"] == "front"]
    rest = [s for s in stories if s["section"] != "front"]
    if front:
        lead = front[0]
        h.append(f"<div class='lead'><h2>{esc(lead['headline'])}</h2><div class='by'>{lead['by']}</div>"
                 + "".join(f"<p>{x}</p>" for x in lead["paras"]) + "</div>")
        if len(front) > 1:
            h.append("<div class='cols'>")
            for s in front[1:]:
                h.append(_story(s))
            h.append("</div>")
    for sec, title_ in (("government", "Government"), ("land", "The Land"), ("sports", "Festivals and Games"),
                        ("people", "People")):
        group = [s for s in rest if s["section"] == sec]
        if group:
            h.append(f"<div class='section'><h4>{title_}</h4><div class='cols'>"
                     + "".join(_story(s) for s in group) + "</div></div>")
    if data.get("arts"):
        a = data["arts"]
        h.append(f"<div class='section'><h4>Arts and Songs</h4><div class='by'>{data['people_by']}</div><ul>"
                 + "".join(f"<li>{x}</li>" for x in a["paras"]) + "</ul></div>")
    for key, sec_title in (("region", "Around the Nation"), ("profile", "A Life")):
        s_ = data.get(key)
        if s_:
            h.append(f"<div class='section'><h4>{sec_title}</h4><h3>{esc(s_['headline'])}</h3>"
                     f"<div class='by'>{data['people_by']}</div>" + "".join(f"<p>{x}</p>" for x in s_["paras"])
                     + "</div>")
    # markets and weather
    h.append("<div class='section'><h4>Markets and Weather</h4><div class='cols'><div class='story'>"
             f"<h3>Prices at Market</h3><div class='by'>{data['land_by']}</div><table><tr><th>Good</th><th>Coins</th>"
             "<th>Since last week</th></tr>"
             + "".join(f"<tr><td>{esc(g)}</td><td>{p}</td><td>{esc(m)}</td></tr>" for g, p, m in data["markets"])
             + "</table></div><div class='story'><h3>Weather This Week</h3><ul>"
             + "".join(f"<li>{x}</li>" for x in data["weather"]) + "</ul></div></div></div>")
    if data["words"]:
        h.append("<div class='section'><h4>Words and Speech</h4><ul>"
                 + "".join(f"<li>{x}</li>" for x in data["words"]) + "</ul></div>")
    if data["editorial"]:
        ed = data["editorial"]
        h.append("<div class='section'><h4>From the Editor</h4>" + "".join(f"<p>{x}</p>" for x in ed["paras"])
                 + f"<div class='by'>{ed['by']}</div></div>")
    if data["letters"]:
        h.append("<div class='section'><h4>Letters</h4>" + "".join(
            f"<div class='letter'>{t}<div class='sig'>{s}</div></div>" for t, s in data["letters"]) + "</div>")
    if data.get("obituaries"):
        h.append("<div class='section'><h4>Obituaries</h4>" + "".join(f"<p>{x}</p>" for x in data["obituaries"])
                 + "</div>")
    b, m, d = data["births"], data["marriages"], data["deaths"]
    if b or m or d:
        h.append("<div class='section'><h4>Births, Marriages and Deaths</h4><div class='cols'>")
        for title_, items in (("Births", b), ("Marriages", m), ("Deaths", d)):
            if items:
                h.append(f"<div class='story'><h3>{title_}</h3><ul>" + "".join(f"<li>{x}</li>" for x in items)
                         + "</ul></div>")
        h.append("</div></div>")
    if data.get("taverns"):
        h.append("<div class='section'><h4>From the Taverns</h4><ul>"
                 + "".join(f"<li>{x}</li>" for x in data["taverns"]) + "</ul></div>")
    if data["comings"]:
        h.append("<div class='section'><h4>Comings and Goings</h4><ul>"
                 + "".join(f"<li>{x}</li>" for x in data["comings"]) + "</ul></div>")
    if data.get("year_ago"):
        h.append("<div class='section'><h4>One Year Ago</h4><ul>"
                 + "".join(f"<li>{x}</li>" for x in data["year_ago"]) + "</ul></div>")
    h.append("<div class='section staff'>" + esc(data["staff_line"]) + "</div>")
    prev_link = f"<a href='issue-{issue - 1:04d}.html'>Previous issue</a> | " if issue > 1 else ""
    h.append(f"<div class='nav'>{prev_link}<a href='archive.html'>All issues</a></div>")
    h.append("</div></body></html>")
    return "".join(h)


def _story(s):
    return (f"<div class='story'><h3>{esc(s['headline'])}</h3><div class='by'>{s['by']}</div>"
            + "".join(f"<p>{x}</p>" for x in s["paras"]) + "</div>")


# ---------------------------------------------------------------- publish
def publish(w, log, out_dir, stats, stats_prev=None):
    st, changes = ensure(w, log)
    st["issue"] += 1
    issue = st["issue"]
    end = w.day - 1
    start = max(0, end - 6)
    events = log.between(start, end, 1)
    if issue == 1:
        events = log.between(0, end, 1)   # the first issue covers everything since the founding
    rng = random.Random(w.seed * 7919 + issue)
    wr = Writer(w, rng)
    from . import paper_extra as X
    follow = X.threads(w, st, events, wr)
    stories = articles(w, st, events, wr) + follow + X.sports(w, events, wr)
    price_moves = X.price_moves(w, stats_prev)
    for extra in (X.market_trend(w, st, price_moves), X.week_roundup(w, events)):
        if extra:
            stories.append(extra)
    recap = X.term_recap(w, st, log, wr)
    if recap:
        stories.append(recap)
    for cur, reason, new in changes:
        stories.append({"section": "people", "score": 20, "headline": "Changes at This Paper",
                        "paras": [f"Our {BEAT_TITLES[new['beat']].lower()}, {esc(cur['name'])}, has {reason}. "
                                  f"{esc(new['name'])} of {esc(town(w, new['region']))} takes up the post."],
                        "beat": "editor"})
    stories.sort(key=lambda s: s["score"], reverse=True)
    # keep the front page to the biggest few stories
    front_seen = 0
    for s in stories:
        if s["section"] == "front":
            front_seen += 1
            if front_seen > 4:
                s["section"] = {"politics": "government", "land": "land"}.get(s["beat"], "people")
        s["by"] = byline(w, st, s["beat"])
    if not any(s["section"] == "front" for s in stories) and stories and stories[0]["score"] >= 30:
        stories[0]["section"] = "front"
    if not any(s["section"] == "front" for s in stories):
        # a quiet week: lead with how people are faring
        q = quote(w, wr, about="life")
        stories.insert(0, {"section": "front", "score": 1, "headline": wr.pick(
            ["A Quiet Week", "All Is Calm", "Little to Report, and Glad of It"]),
            "paras": [f"It was a quiet week across {esc(w.nation_name)}."] + ([q] if q else []),
            "beat": "people", "by": byline(w, st, "people")})
    b, m, d = announcements(w, events)
    staff_line = "This paper is written by " + "; ".join(
        f"{s['name']} ({BEAT_TITLES[beat].lower()}, {town(w, s['region'])})" for beat, s in st["staff"].items()) + "."
    data = {
        "issue": issue, "date": f"{label(end)}", "population": stats["population"], "stories": stories,
        "markets": markets(w, stats_prev, wr), "weather": weather_lines(w, wr),
        "words": words_corner(w, events, wr), "editorial": editorial(w, st, stats, wr),
        "letters": letters(w, st, wr, events, price_moves), "births": b, "marriages": m, "deaths": d,
        "comings": comings_goings(events)[:12], "staff_line": staff_line, "land_by": byline(w, st, "land"),
        "arts": X.arts_section(w, st, events, wr), "region": X.region_report(w, st, stats, wr),
        "profile": X.profile(w, st, wr), "obituaries": X.obituaries(w, events), "year_ago": X.year_ago(w, st, log),
        "taverns": X.taverns(events), "people_by": byline(w, st, "people"),
    }
    pdir = os.path.join(out_dir, "paper")
    os.makedirs(pdir, exist_ok=True)
    page = render(w, st, issue, data)
    with open(os.path.join(pdir, f"issue-{issue:04d}.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(pdir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(pdir, f"issue-{issue:04d}.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in data.items()}, f)
    st.setdefault("index", []).append({"issue": issue, "date": data["date"],
                                       "headline": stories[0]["headline"] if stories else ""})
    _archive(w, st, pdir)
    log.add(w.day, "paper", f"Issue {issue} of the paper was published.", importance=1, issue=issue)
    return os.path.join(pdir, f"issue-{issue:04d}.html")


def _archive(w, st, pdir):
    paper_word = language.word(w, "newspaper") or "Gazette"
    rows = "".join(f"<li><a href='issue-{x['issue']:04d}.html'>Issue {x['issue']}</a> &mdash; {esc(x['date'])}: "
                   f"{esc(x['headline'])}</li>" for x in reversed(st["index"]))
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>The {esc(paper_word.capitalize())}: all issues</title>"
            f"<style>{CSS}</style></head><body><div class='page'><div class='mast'><h1>The "
            f"{esc(paper_word.capitalize())}</h1><div class='sub'>Every issue</div></div><ul>{rows}</ul>"
            f"<div class='nav'><a href='index.html'>Latest issue</a></div></div></body></html>")
    with open(os.path.join(pdir, "archive.html"), "w", encoding="utf-8") as f:
        f.write(page)
