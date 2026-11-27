"""The paper's deeper sections: follow-ups, term recaps, one year ago,
region reports, citizen profiles, obituaries, sports, arts and taverns.
"""
from . import config as C
from . import language
from .calendar import label, year
from .paper import esc, person_name, town, rname, reporter, lean, quote, _said

# ---------------------------------------------------------------- small helpers


def pron(sex):
    return ("she", "her", "her") if sex == "f" else ("he", "him", "his")


def mood_word(x):
    if x >= 0.85:
        return "in high spirits"
    if x >= 0.78:
        return "content"
    if x >= 0.7:
        return "getting by"
    if x >= 0.6:
        return "uneasy"
    return "unhappy"


def approval_word(x):
    if x >= 0.75:
        return "warmly"
    if x >= 0.55:
        return "well enough"
    if x >= 0.4:
        return "with growing doubt"
    if x >= 0.25:
        return "poorly"
    return "with open anger"


def _life_sentence(text):
    return text[0].upper() + text[1:] if text else text


def quote_from(w, wr, p):
    h = w.households[p.household]
    if p.hunger >= 3:
        line = "These have been hungry days."
    elif h.house is None:
        line = "All we want is a roof of our own."
    elif p.satisfaction >= 0.85:
        line = wr.pick(["I have been lucky, and I know it.", "I would not trade my life for anyone's."])
    elif p.satisfaction >= 0.7:
        line = wr.pick(["You take the good years with the bad.", "Work hard and be kind. That's all there is."])
    else:
        line = wr.pick(["It has not been an easy life.", "I have known better seasons than this one."])
    return _said(line, esc(p.given))


# ---------------------------------------------------------------- threads
def threads(w, st, events, wr):
    """Open new running stories and write follow-ups for old ones."""
    from .government import _vote_score
    th = st.setdefault("threads", [])
    out = []
    types = {e["type"] for e in events}
    issue = st["issue"]
    for e in events:
        if e["type"] == "petition":
            th.append({"kind": "petition", "opened": issue, "pres": e["people"][-1]})
        elif e["type"] == "campaign":
            th.append({"kind": "campaign", "opened": issue})
        elif e["type"] == "scandal":
            th.append({"kind": "scandal", "opened": issue, "pres": e["people"][0]})
        elif e["type"] == "hunger" and not any(t["kind"] == "hunger" and t["region"] == e["region"] for t in th):
            th.append({"kind": "hunger", "opened": issue, "region": e["region"], "weeks": 1, "quiet": 0})
    keep = []
    for t in th:
        fresh = t["opened"] == issue
        k = t["kind"]
        if k == "petition":
            pet = w.gov.get("petition")
            if not pet or w.president != t["pres"]:
                continue
            if not fresh:
                adults = sum(1 for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE)
                need = int(adults * C.PETITION_SHARE) + 1
                weeks = (w.day - pet["started"]) // 7
                out.append({"section": "government", "score": 55, "beat": "politics",
                            "headline": "The Petition: Week " + str(weeks),
                            "paras": [f"The petition to recall President {esc(person_name(w, t['pres']))} now carries "
                                      f"{pet['signatures']} of the {need} names it needs."]})
            keep.append(t)
        elif k == "campaign":
            if not w.gov.get("campaign_open"):
                continue
            if not fresh:
                cands = [(w.people[c["id"]], c["promises"]) for c in w.gov["candidates"] if c["id"] in w.people]
                if len(cands) >= 2:
                    pres = w.people.get(w.president)
                    pool = [p for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE]
                    sample = wr.rng.sample(pool, min(40, len(pool)))
                    tally = {c.id: 0 for c, _ in cands}
                    for v in sample:
                        best = max(cands, key=lambda cp: _vote_score(w, v, cp[0], cp[1], pres))[0]
                        tally[best.id] += 1
                    res = ", ".join(f"{esc(w.people[i].name)} {n}" for i, n in
                                    sorted(tally.items(), key=lambda x: -x[1]))
                    days = w.gov["election_day"] - w.day
                    out.append({"section": "front" if days <= 7 else "government", "score": 60, "beat": "politics",
                                "headline": "The Race: A Straw Poll",
                                "paras": [f"This paper asked {len(sample)} people across the nation whom they would "
                                          f"vote for today: {res}. The vote is in {max(1, days // 7)} "
                                          f"week{'s' if days > 13 else ''}."]})
            keep.append(t)
        elif k == "scandal":
            weeks = issue - t["opened"]
            if weeks > 4 or w.president != t["pres"]:
                continue
            if not fresh:
                ad = [p for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE]
                appr = sum(p.approval for p in ad) / max(1, len(ad))
                out.append({"section": "government", "score": 50, "beat": "politics",
                            "headline": "After the Scandal",
                            "paras": [f"{weeks} week{'s' if weeks > 1 else ''} after the treasury scandal, the nation "
                                      f"regards President {esc(person_name(w, t['pres']))} {approval_word(appr)}."]})
            keep.append(t)
        elif k == "hunger":
            if not fresh:
                if any(e["type"] == "hunger" and e["region"] == t["region"] for e in events):
                    t["weeks"] += 1
                    t["quiet"] = 0
                else:
                    t["quiet"] += 1
                    if t["quiet"] >= 2:
                        out.append({"section": "land", "score": 40, "beat": "land",
                                    "headline": f"Hunger Eases in {rname(w, t['region'])}",
                                    "paras": [f"After {t['weeks']} weeks of want, no one in "
                                              f"{esc(rname(w, t['region']))} is reported going hungry."]})
                        continue
            keep.append(t)
    st["threads"] = keep
    return out


def hunger_weeks(st, region):
    for t in st.get("threads", []):
        if t["kind"] == "hunger" and t["region"] == region:
            return t["weeks"]
    return 1


# ---------------------------------------------------------------- term recap
def term_recap(w, st, log, wr):
    g = w.gov
    pres = w.people.get(w.president)
    if not pres or not g.get("campaign_open") or not (0 < g["election_day"] - w.day <= 7):
        return None
    evs = log.between(g["term_start"], w.day, 2)
    count = lambda *t: sum(1 for e in evs if e["type"] in t)
    works = [e["data"].get("kind") for e in evs if e["type"] == "works_begun"]
    bits = []
    if works:
        names = {}
        for k in works:
            names[k] = names.get(k, 0) + 1
        plural = {"granary": "granaries", "house": "public houses", "mill": "mills", "road": "roads",
                  "well": "wells", "statue": "statues"}
        single = {"house": "public house"}
        bits.append("ordered " + ", ".join(f"{n} {plural.get(k, k + 's') if n > 1 else single.get(k, k)}"
                                           for k, n in names.items()) + " built")
    if count("relief"):
        bits.append(f"sent relief to the hungry {count('relief')} time{'s' if count('relief') > 1 else ''}")
    if count("subsidy"):
        bits.append("paid subsidies to " + ", ".join(sorted({e['data'].get('job', '') + 's' for e in evs
                                                             if e['type'] == 'subsidy'})))
    if count("tax_up"):
        bits.append(f"raised taxes {count('tax_up')} time{'s' if count('tax_up') > 1 else ''}")
    if count("tax_down"):
        bits.append(f"cut taxes {count('tax_down')} time{'s' if count('tax_down') > 1 else ''}")
    if count("mint"):
        bits.append("struck new coins")
    if count("festival"):
        bits.append(f"paid for {count('festival')} festival{'s' if count('festival') > 1 else ''}")
    if count("festival_skipped"):
        bits.append(f"refused to pay for {count('festival_skipped')} festival{'s' if count('festival_skipped') > 1 else ''}")
    if count("commission"):
        bits.append("paid an artist to praise the government")
    paras = [f"As President {esc(pres.name)} asks for another term, a look back at the last six months. "
             f"The president " + (", ".join(bits[:-1]) + " and " + bits[-1] if len(bits) > 1 else
                                  (bits[0] if bits else "did little that this paper recorded")) + "."]
    kept = len(g.get("kept", []))
    left = g.get("promises", [])
    if kept or left:
        paras.append(f"Of the promises made at the last election, {kept} {'was' if kept == 1 else 'were'} kept"
                     + (f"; still outstanding: {esc('; '.join(p['text'] for p in left))}." if left else "."))
    if count("scandal"):
        paras.append("The term was marked by scandal at the treasury.")
    paras.append(f"The treasury stands at {w.treasury:.0f} coins.")
    return {"section": "government", "score": 65, "beat": "politics", "headline": f"The Record of {pres.name}",
            "paras": paras}


# ---------------------------------------------------------------- one year ago
def year_ago(w, st, log):
    end = w.day - 1 - C.DAYS_PER_YEAR
    if end < st.get("founded", 0):
        return []
    evs = log.between(end - 6, end, 3)
    evs.sort(key=lambda e: -e["importance"])
    return [esc(e["summary"]) for e in evs[:4]]


# ---------------------------------------------------------------- region report
def region_report(w, st, stats, wr):
    from .arts import popular_by_region
    keys = list(w.regions)
    r = keys[st["issue"] % len(keys)]
    reg = w.regions[r]
    ps = [p for p in w.people.values() if p.region == r]
    if not ps:
        return None
    jobs = {}
    for p in ps:
        if p.job:
            jobs[p.job] = jobs.get(p.job, 0) + 1
    top = sorted(jobs.items(), key=lambda x: -x[1])[:3]
    mood = stats["region_mood"].get(r, {})
    homeless = sum(1 for h in w.households.values() if h.region == r and h.members and h.house is None)
    paras = [f"This week the paper visits <b>{esc(reg.name)}</b>, home to {len(ps)} people, with its chief town at "
             f"{esc(reg.town)}. Most there work as " + ", ".join(f"{j}s ({n})" for j, n in top) + "."]
    paras.append(f"People here seem {mood_word(mood.get('satisfaction', 0.7))}, and they regard the president "
                 f"{approval_word(mood.get('approval', 0.5))}."
                 + (f" {homeless} {'household here has' if homeless == 1 else 'households here have'} "
                    "no house of their own." if homeless else ""))
    oldest = max(ps, key=lambda p: p.age(w.day))
    paras.append(f"The oldest soul in {esc(reg.name)} is {esc(oldest.name)}, at {int(oldest.age(w.day))}.")
    pop = popular_by_region(w).get(r)
    if pop:
        paras.append(f"The {pop['kind']} on everyone's lips here is '{esc(pop['title'])}' "
                     f"({esc(pop['title_en'])}) by {esc(pop['artist_name'])}.")
    dial = [(c, m, f) for c, m, f in language.dialect_words(w) if len(set(f.values())) > 1]
    for c, m, forms in dial:
        mine = forms[r]
        others = {v for k, v in forms.items() if k != r}
        if mine not in others:
            paras.append(f"Listen for the local way of speaking: here {esc(m)} is <i>{esc(mine)}</i>, "
                         f"not <i>{esc(sorted(others)[0])}</i> as elsewhere.")
            break
    q = quote(w, wr, region=r, about="life")
    if q:
        paras.append(q)
    return {"section": "region", "score": 0, "beat": "people", "headline": f"Around the Nation: {reg.name}",
            "paras": paras}


# ---------------------------------------------------------------- citizen profile
def profile(w, st, wr):
    done = set(st.setdefault("profiled", []))
    pool = [p for p in w.people.values() if p.age(w.day) >= 25 and p.id not in done and len(p.life) >= 5]
    if not pool:
        return None
    pool.sort(key=lambda p: len(p.life) + 4 * p.reputation + wr.rng.random() * 3, reverse=True)
    p = pool[0]
    st["profiled"].append(p.id)
    st["profiled"] = st["profiled"][-300:]
    he, him, his = pron(p.sex)
    paras = [f"{esc(p.name)} is {int(p.age(w.day))} and lives in {esc(town(w, p.region))}"
             + (f", where {he} works as a {esc(p.job)}." if p.job else ".")]
    shown = 0
    last_job_line = None
    for day, text in p.life:
        if text.startswith("became a "):
            last_job_line = (day, text)
            continue
        if text.startswith("born"):
            when = (f"in {esc(label(day).split(',')[0])}" if day >= st.get("founded", 0)
                    else "before the nation was founded")
            paras.append(f"{he.capitalize()} was {esc(text)}, {when}.")
        else:
            paras.append(f"In {esc(label(day).split(',')[0])}, {he} {esc(text)}.")
        shown += 1
        if shown >= 6:
            break
    paras.append(quote_from(w, wr, p))
    return {"section": "profile", "score": 0, "beat": "people", "headline": f"A Life in {w.nation_name}: {p.name}",
            "paras": paras}


# ---------------------------------------------------------------- obituaries
def obituaries(w, events, limit=3):
    out = []
    deaths = [e for e in events if e["type"] == "death" and e["data"].get("age", 0) >= 16]
    deaths.sort(key=lambda e: -(len(w.dead.get(e["people"][0], {}).get("life", []))
                                + 5 * w.dead.get(e["people"][0], {}).get("reputation", 0.5)))
    for e in deaths[:limit]:
        pid = e["people"][0]
        d = w.dead.get(pid)
        if not d:
            continue
        he, him, his = pron(d.get("sex"))
        name = f"{d['given']} {d['family']}"
        age = e["data"].get("age")
        life = d.get("life", [])
        s = [f"<b>{esc(name)}</b>, {age}, {esc(d['cause'])}."]
        if life and life[0][1].startswith("born"):
            s.append(f"{he.capitalize()} was {esc(life[0][1])}.")
        jobs = []
        for _, t in life:
            if t.startswith("became a "):
                j = t[len("became a "):].split(",")[0]
                if j not in jobs:
                    jobs.append(j)
        if not jobs and d.get("job"):
            jobs = [d["job"]]
        if jobs:
            s.append(f"{he.capitalize()} worked as a {esc(jobs[0])}" + (f", and later as a {esc(jobs[-1])}"
                                                                        if len(jobs) > 1 else "") + ".")
        for _, t in life:
            if t.startswith("married"):
                s.append(f"{he.capitalize()} {esc(t.split(' in ')[0])}.")
                break
        notable = [t for _, t in life if any(k in t for k in (
            "president", "came up with", "won ", "famous", "statue", "petition", "made a ", "built a house"))]
        for t in notable[:3]:
            s.append(f"{he.capitalize()} {esc(t)}.")
        kids = sum(1 for c in d.get("children", []) if c in w.people)
        if kids:
            s.append(f"{he.capitalize()} leaves {kids} living {'child' if kids == 1 else 'children'}.")
        out.append(" ".join(s))
    return out


# ---------------------------------------------------------------- sports
def sports(w, events, wr):
    out = []
    from .leisure import SPORTS
    contests = [e for e in events if e["type"] == "contest"]
    fest = [e for e in events if e["type"] in ("festival", "festival_skipped")]
    for e in fest:
        out.append({"section": "front" if e["type"] == "festival_skipped" else "sports",
                    "score": 58 if e["type"] == "festival_skipped" else 45, "beat": "people",
                    "headline": "No Festival This Year" if e["type"] == "festival_skipped" else
                    ("The Harvest Festivals" if e["data"].get("kind") == "harvest" else "The Midwinter Feast"),
                    "paras": [esc(e["summary"])]})
    if contests:
        national = [e for e in contests if e["data"].get("national")]
        regional = [e for e in contests if not e["data"].get("national")]
        if national:
            paras = [esc(e["summary"]) for e in national]
            out.append({"section": "front", "score": 62, "beat": "people", "headline": "National Champions Crowned",
                        "paras": paras})
        if regional:
            by_sport = {}
            for e in regional:
                by_sport.setdefault(e["data"]["sport"], []).append(e)
            paras = []
            for sport, evs in by_sport.items():
                paras.append(f"<b>{esc(SPORTS[sport]['name'].replace('the ', '').capitalize())}.</b> "
                             + " ".join(esc(e["summary"]) for e in evs))
            out.append({"section": "sports", "score": 40, "beat": "people",
                        "headline": "Champions of the Harvest Games", "paras": paras})
    return out


# ---------------------------------------------------------------- arts
def review(w, st, work, wr):
    s, p = reporter(w, st, "people")
    if not p:
        return ""
    t = p.traits
    taste = {"solemn": t["piety"], "family": t["warmth"], "joyful": t["sociability"],
             "political": t["ambition"], "nature": 1 - t["ambition"]}.get(work.get("mood"), 0.5)
    score = work["quality"] + 0.25 * (taste - 0.5) + wr.rng.gauss(0, 0.08)
    verb = "hear" if work["kind"] in ("song", "story") else "see"
    if work.get("tone") == "mock":
        if p.approval > 0.6:
            return "This correspondent found it a cheap shot, however catchy."
        return "It is as sharp as it is true, and the taverns are taking it up."
    if work.get("tone") == "praise":
        if p.approval < 0.4:
            return "Flattery, and paid-for flattery at that."
        return "A fitting tribute, sincerely made."
    if score >= 0.75:
        return "A fine piece, the best this paper has come across in some time."
    if score >= 0.55:
        return f"Well worth the effort to {verb}."
    if score >= 0.35:
        return "Pleasant enough, if not memorable."
    return "This correspondent could not warm to it."


def arts_section(w, st, events, wr):
    from .arts import popular_by_region
    works = w.arts.get("works", {}) if w.arts else {}
    new = [e for e in events if e["type"] == "artwork"]
    new.sort(key=lambda e: -(e["data"].get("quality", 0) + (0.5 if e["data"].get("subject") in ("mock", "praise") else 0)))
    items = []
    for e in new[:3]:
        work = works.get(e["data"].get("work"))
        if not work:
            continue
        line = esc(e["summary"])
        verse = work.get("verse") or []
        vhtml = ""
        if verse:
            vhtml = ("<div style='margin:4px 0 4px 14px'>" + "<br>".join(f"<i>{esc(n)}</i>" for n, _ in verse)
                     + "<br><span style='font-size:13px'>(" + " / ".join(esc(en) for _, en in verse) + ")</span></div>")
        items.append(f"{line}{vhtml} {esc(review(w, st, work, wr))}")
    for e in events:
        if e["type"] in ("art_famous", "commission"):
            items.append(esc(e["summary"]))
    pops = popular_by_region(w)
    if pops:
        items.append("What people are singing and talking about: " + "; ".join(
            f"in {esc(rname(w, r))}, '{esc(x['title'])}' by {esc(x['artist_name'])}" for r, x in pops.items()) + ".")
    if not items:
        return None
    return {"section": "arts", "score": 0, "beat": "people", "headline": "Arts and Songs", "paras": items}


def taverns(events):
    return [esc(e["summary"]) for e in events if e["type"] == "tavern_quarrel"][:4]
