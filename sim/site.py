"""The stats page and the front door of the nation's little website.

Every number on the stats page comes with context: what it was last week
and last season, a plain-words reading, and a line on what it measures.
Writes plain HTML files into data/site/.
"""
import html
import os

from . import config as C
from . import language
from .calendar import label, week_of_year, year, season
from .economy import customary_price
from .inventions import INVENTIONS
from .paper import CSS
from .paper_extra import approval_word, mood_word

EXTRA_CSS = """
.note{font-size:12px;color:#4a4237;margin:4px 0 0}
.summary{font-size:18px;line-height:1.5;border-bottom:1px solid #b9ab8f;padding-bottom:10px;margin-bottom:6px}
td.num,th.num{text-align:right;white-space:nowrap}
td.chg{font-size:13px;color:#4a4237}
"""


def esc(s):
    return html.escape(str(s))


def _get(row, path):
    cur = row
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _change(now, then, kind):
    """Plain words for a change: kind is 'pct' (a 0-1 share), 'count' or 'coins'."""
    if then is None or now is None:
        return ""
    d = now - then
    if kind == "pct":
        pts = round(d * 100)
        return "no change" if pts == 0 else f"{'up' if pts > 0 else 'down'} {abs(pts)} pt{'s' if abs(pts) != 1 else ''}"
    n = round(d)
    return "no change" if n == 0 else f"{'up' if n > 0 else 'down'} {abs(n)}"


def _both(now, prev, season_ago, kind):
    parts = []
    a = _change(now, prev, kind)
    b = _change(now, season_ago, kind)
    if a:
        parts.append(f"{a} on last week")
    if b:
        parts.append(f"{b} on last season")
    return "; ".join(parts)


def _table(rows):
    """rows of (label, value, change, meaning)"""
    out = ["<table><tr><th>Measure</th><th class='num'>Now</th><th>Change</th><th>What it means</th></tr>"]
    for lab, val, chg, meaning in rows:
        out.append(f"<tr><td>{esc(lab)}</td><td class='num'>{val}</td><td class='chg'>{esc(chg)}</td>"
                   f"<td class='chg'>{esc(meaning)}</td></tr>")
    out.append("</table>")
    return "".join(out)


def _short(lab):
    """'Year 2, spring, week 3' -> 'Y2 spring wk 3'"""
    try:
        y, s, wk = [x.strip() for x in lab.split(",")]
        return f"Y{y.split()[1]} {s} wk {wk.split()[1]}"
    except Exception:
        return lab


def _spark(points, fmt, width=300, height=70):
    """A small line chart with its first and last dates and its current value."""
    pts = [(lab, v) for lab, v in points if v is not None]
    if len(pts) < 2:
        return "<p class='note'>Not enough weeks yet to draw a trend.</p>"
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    xy = []
    for i, (_, v) in enumerate(pts):
        x = i * (width - 4) / (len(pts) - 1) + 2
        y = height - 6 - (v - lo) / span * (height - 12)
        xy.append(f"{x:.1f},{y:.1f}")
    return (f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' role='img'>"
            f"<polyline fill='none' stroke='#5a2d0c' stroke-width='2' points='{' '.join(xy)}'/></svg>"
            f"<div class='by'>Now {fmt(vals[-1])}. Range {fmt(lo)} to {fmt(hi)}, "
            f"{esc(pts[0][0])} to {esc(pts[-1][0])}.</div>")


def _streak(history, good):
    """How many weeks running a price has moved the same way, and which way."""
    prices = [p for p in (_get(r, ["prices", good]) for r in history) if p is not None]
    direction, n = None, 0
    for i in range(len(prices) - 1, 0, -1):
        c = (prices[i] - prices[i - 1]) / prices[i - 1] if prices[i - 1] else 0
        d = "up" if c > 0.01 else "down" if c < -0.01 else None
        if d is None or (direction and d != direction):
            break
        direction = d
        n += 1
    return n, direction


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _summary(w, s, prev, g, moves_down, moves_up):
    pres = w.people.get(w.president)
    day = s.get("day", w.day - 1)
    lines = [f"{season(day).capitalize()} of Year {year(day)}."]
    sat = s["satisfaction"]
    psat = _get(prev, ["satisfaction"]) if prev else None
    trend = ""
    if psat is not None:
        d = sat - psat
        trend = " and steady" if abs(d) < 0.01 else (" and rising" if d > 0 else " and slipping")
    lines.append(f"People are {mood_word(sat)}{trend}, at {sat:.0%} satisfaction.")
    if s.get("hungry", 0):
        lines.append(f"{s['hungry']} {'person is' if s['hungry'] == 1 else 'people are'} going hungry.")
    if s.get("homeless_households", 0) >= 3:
        lines.append(f"{s['homeless_households']} households have no house of their own.")
    if len(moves_down) >= 5:
        lines.append("Prices are falling across the market"
                     + (" as the harvest comes in." if season(day) == "autumn" else "."))
    elif len(moves_up) >= 5:
        lines.append("Prices are rising across the market.")
    if pres:
        lines.append(f"The nation regards President {esc(pres.name)} {approval_word(g['approval'])} "
                     f"({g['approval']:.0%}).")
        if g["petition"]:
            lines.append(f"A recall petition has {g['petition']['signatures']} of the {g['petition']['needed']} "
                         "names it needs.")
        elif g["days_to_election"] <= 28:
            lines.append(f"The next vote is in {max(1, g['days_to_election'] // 7)} weeks.")
    else:
        lines.append("The presidency is empty until a special election.")
    return " ".join(lines)


def write_stats(w, log, out_dir, stats):
    s = stats
    history = list(reversed(log.recent_weeks(104)))
    if not history or history[-1].get("day") != s.get("day"):
        history.append(s)
    prev = history[-2] if len(history) >= 2 else None
    season_ago = history[-14] if len(history) >= 14 else None
    g = s["government"]
    pres = w.people.get(w.president)
    events_week = log.between(w.day - 7, w.day - 1, 1)
    moves = {}
    for good, now in s["prices"].items():
        old = _get(prev, ["prices", good]) if prev else None
        if old:
            moves[good] = (now - old) / old
    moves_down = [k for k, c in moves.items() if c <= -0.05]
    moves_up = [k for k, c in moves.items() if c >= 0.05]

    def P(*path):
        return _get(prev, list(path)) if prev else None

    def S(*path):
        return _get(season_ago, list(path)) if season_ago else None

    h = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' "
         f"content='width=device-width,initial-scale=1'><title>{esc(w.nation_name)}: the state of the nation</title>"
         f"<style>{CSS}{EXTRA_CSS}</style></head><body><div class='page'><div class='mast'><h1>{esc(w.nation_name)}</h1>"
         f"<div class='sub'>The state of the nation, {esc(s['label'])}</div></div>"]
    h.append(f"<p class='summary'>{_summary(w, s, prev, g, moves_down, moves_up)}</p>")

    # ---------------- people
    sat_word = mood_word(s["satisfaction"])
    rows = [
        ("Population", s["population"], _both(s["population"], P("population"), S("population"), "count"),
         "Everyone alive in the nation."),
        ("Births, marriages, deaths", f"{s['births']}, {s['marriages']}, {s['deaths']}", "",
         "Counted over the last seven days."),
        ("Households", s["households"], _both(s["households"], P("households"), S("households"), "count"),
         "Families living together. Marriages and children leaving home make new ones."),
        ("Households without a house", s["homeless_households"],
         _both(s["homeless_households"], P("homeless_households"), S("homeless_households"), "count"),
         "They lodge with kin until a builder or the government houses them."),
        ("Average satisfaction", f"{s['satisfaction']:.0%}",
         _both(s["satisfaction"], P("satisfaction"), S("satisfaction"), "pct"),
         f"How well needs are met, weighted by personality. Reads as '{sat_word}'. Below 70%, people grow restless."),
        ("Going hungry", s["hungry"], _both(s["hungry"], P("hungry"), S("hungry"), "count"),
         "People underfed five or more days running. After about three weeks, hunger can kill."),
        ("Households close to hunger", s.get("near_hunger_households", 0),
         _both(s.get("near_hunger_households", 0), P("near_hunger_households"), S("near_hunger_households"), "count"),
         "Less than five days of food and not enough coin to buy more."),
        ("Coins held by the richest tenth", f"{s.get('richest_tenth_share', 0):.0%}",
         _both(s.get("richest_tenth_share", 0), P("richest_tenth_share"), S("richest_tenth_share"), "pct"),
         "Share of all household coins held by the wealthiest 10% of households. An even split would be 10%."),
    ]
    h.append("<div class='section'><h4>People</h4>" + _table(rows) + "</div>")

    # ---------------- regions
    mood = s.get("region_mood", {})
    reg_rows = []
    for k, r in w.regions.items():
        ps = [p for p in w.people.values() if p.region == k]
        jobs = {}
        for p in ps:
            if p.job:
                jobs[p.job] = jobs.get(p.job, 0) + 1
        main = max(jobs, key=jobs.get) if jobs else "-"
        homeless = sum(1 for x in w.households.values() if x.region == k and x.members and x.house is None)
        hungry = sum(1 for p in ps if p.hunger >= 5)
        m = mood.get(k, {})
        reg_rows.append(f"<tr><td>{esc(r.name)}<div class='note'>the {esc(k)}; chief town {esc(r.town)}</div></td>"
                        f"<td class='num'>{len(ps)}</td><td class='num'>{m.get('satisfaction', 0):.0%}</td>"
                        f"<td class='num'>{m.get('approval', 0):.0%}</td><td class='num'>{homeless}</td>"
                        f"<td class='num'>{hungry}</td><td>{esc(main)}</td></tr>")
    h.append("<div class='section'><h4>Regions</h4><table><tr><th>Region</th><th class='num'>People</th>"
             "<th class='num'>Satisfied</th><th class='num'>Approve</th><th class='num'>No house</th>"
             "<th class='num'>Hungry</th><th>Main trade</th></tr>" + "".join(reg_rows) + "</table>"
             "<p class='note'>Satisfied is the region's average satisfaction. Approve is its adults' average "
             "opinion of the president. People can only move to neighboring regions.</p></div>")

    # ---------------- government
    gov = w.gov
    rows = []
    if pres:
        terms = gov.get("terms", 1)
        rows.append(("President", esc(pres.name), "",
                     f"{int(pres.age(w.day))}, a {pres.job or 'retired person'} from {w.regions[pres.region].name}, "
                     f"in their {_ordinal(terms)} term."))
        wk = (w.day - gov["term_start"]) // 7 + 1
        rows.append(("Term", f"week {wk} of {C.TERM_DAYS // 7}", "",
                     f"Next vote {g['next_election']}, in {g['days_to_election']} days. "
                     "Terms last six months; presidents may run again."))
    else:
        rows.append(("President", "none", "", f"A special election is set for {g['next_election']}."))
    rows.append(("Approval", f"{g['approval']:.0%}",
                 _both(g["approval"], P("government", "approval"), S("government", "approval"), "pct"),
                 f"Adults' average opinion of the president, read as '{approval_word(g['approval'])}'. "
                 "50% is neutral."))
    need = int(sum(1 for p in w.people.values() if p.age(w.day) >= C.ADULT_AGE) * C.PETITION_SHARE) + 1
    if g["petition"]:
        rows.append(("Recall petition", f"{g['petition']['signatures']} of {g['petition']['needed']}", "",
                     "Names gathered. Reaching the target within four weeks forces a recall vote; "
                     "70% of that vote removes the president."))
    elif g["recall_vote"]:
        rows.append(("Recall vote", esc(g["recall_vote"]), "", "70% of votes cast are needed to remove the president."))
    else:
        rows.append(("Recall petition", "none", "",
                     f"One can start when a fifth of adults strongly disapprove. It would need {need} names."))
    if g["candidates"]:
        rows.append(("Candidates", esc(", ".join(g["candidates"])), "", "Standing in the coming vote."))
    if g["promises"]:
        rows.append(("Promises still to keep", esc("; ".join(g["promises"])), "",
                     "Made at the last election. Any left at the end of the term are reported as broken."))
    if pres:
        names = {"works_begun": "public works ordered", "relief": "relief handed out", "subsidy": "subsidies",
                 "tax_up": "tax rises", "tax_down": "tax cuts", "mint": "coin mintings",
                 "festival": "festivals paid for", "festival_skipped": "festivals refused",
                 "commission": "art commissioned", "promise_kept": "promises kept"}
        tally = {}
        for e in log.between(gov["term_start"], w.day, 2):
            if e["type"] in names:
                tally[names[e["type"]]] = tally.get(names[e["type"]], 0) + 1
        rows.append(("This term so far", esc("; ".join(f"{k}: {n}" for k, n in tally.items()) or "nothing yet"), "",
                     "Everything the president has done since the term began."))
    h.append("<div class='section'><h4>Government</h4>" + _table(rows) + "</div>")

    # ---------------- treasury
    rows = [("Treasury", f"{g['treasury']:.0f} coins",
             _both(g["treasury"], P("government", "treasury"), S("government", "treasury"), "coins"),
             "Coins the government holds.")]
    tin, tout, mint = s.get("treasury_in"), s.get("treasury_out"), s.get("minted_week", 0)
    if tin is not None:
        rows.append(("Money in and out this week",
                     f"+{tin:.0f} / -{tout:.0f}" + (f" / +{mint:.0f} minted" if mint else ""), "",
                     "In: market and head taxes, and estates with no heirs. Out: public works wages, subsidies, "
                     "relief, festivals, commissions and rewards."))
        recent = [r for r in history[-4:] if r.get("treasury_out") is not None]
        avg_out = sum(r["treasury_out"] for r in recent) / len(recent)
        avg_in = sum(r["treasury_in"] for r in recent) / len(recent)
        if avg_out > avg_in:
            rows.append(("Reserve", f"about {g['treasury'] / (avg_out - avg_in):.0f} weeks", "",
                         "How long the treasury lasts if the last few weeks' spending continues, after taxes."))
        else:
            rows.append(("Reserve", "not shrinking", "", "Taxes have covered spending in recent weeks."))
    rows.append(("Taxes", f"{g['sales_tax']:.0%} market" + (f", {g['head_tax']:.2f} a head weekly" if g["head_tax"] else ""),
                 "", "Every market sale pays the market tax. A head tax, if set, is due from every adult each week."))
    pop = max(1, s["population"])
    rows.append(("Coins in circulation", f"{g['money_supply']:.0f}", f"{g['money_supply'] / pop:.0f} per person",
                 "All coins in the nation, held by households and the treasury."
                 + (f" {g['minted']:.0f} have been minted since the founding." if g["minted"]
                    else " None have been minted since the founding.")))
    rows.append(("Price level", f"{g['price_level']:.2f}", "",
                 "1.00 at the founding. Rises slowly as minting adds coins, which lifts what people think is a "
                 "normal price."))
    if g["subsidies"]:
        rows.append(("Subsidies", esc(", ".join(f"{j} {r:.2f} a day" for j, r in g["subsidies"].items())), "",
                     "Paid to every worker in that trade."))
    works = [f for f in g["public_works"] if f["status"] == "building"]
    done = [f for f in g["public_works"] if f["status"] == "done"]
    wtxt = ", ".join(f"{f['kind']} in {w.regions[f['region']].name} (being built)" for f in works)
    dtxt = ", ".join(f"{f['kind']} in {w.regions[f['region']].name}" for f in done)
    rows.append(("Public works", esc("; ".join(x for x in (wtxt, dtxt) if x) or "none"), "",
                 "A well cuts deaths, a granary keeps grain, a mill or road raises output, all in their own region."))
    h.append("<div class='section'><h4>Treasury</h4>" + _table(rows) + "</div>")

    # ---------------- prices
    prow = []
    for good, now in s["prices"].items():
        normal = customary_price(w, good)
        vs = now / normal - 1
        n, d = _streak(history, good)
        streak = f"{d} {n} week{'s' if n != 1 else ''} running" if d else "steady"
        wkc = moves.get(good)
        week_txt = (f"{'up' if wkc > 0 else 'down'} {abs(wkc):.0%}" if wkc is not None and abs(wkc) >= 0.01
                    else "steady")
        prow.append(f"<tr><td>{esc(good)}</td><td class='num'>{now:.2f}</td><td class='num'>{normal:.2f}</td>"
                    f"<td class='chg'>{abs(vs):.0%} {'below' if vs < 0 else 'above'}</td>"
                    f"<td class='chg'>{esc(week_txt)}</td><td class='chg'>{esc(streak)}</td></tr>")
    h.append("<div class='section'><h4>Prices</h4><table><tr><th>Good</th><th class='num'>Coins</th>"
             "<th class='num'>Normal</th><th>Against normal</th><th>This week</th><th>Trend</th></tr>"
             + "".join(prow) + "</table><p class='note'>Normal is the price people think is fair; sellers hold "
             "back when prices drop below it. A price can move at most 3% a day, about 19% in a week, and never "
             "falls below 30% of normal. Most families grow their own food, so food prices mostly reflect what "
             "craftspeople and townsfolk buy.</p></div>")

    # ---------------- trades
    trow = []
    total = max(1, sum(s["jobs"].values()))
    waiting = sum(1 for x in w.households.values() if x.members and x.house is None)
    for job, n in sorted(s["jobs"].items(), key=lambda x: -x[1]):
        then = S("jobs", job)
        chg = (_change(n, then, "count") + " on last season") if then is not None else ""
        outs_ = list(C.JOBS[job]["outputs"])
        if job == "builder":
            market = f"{waiting} famil{'y' if waiting == 1 else 'ies'} waiting for a house"
        elif outs_:
            st_ = min(w.sell_through.get(o, 1.0) for o in outs_)
            market = "selling well" if st_ >= 0.8 else "some goes unsold" if st_ >= 0.4 else "most goes unsold"
            if job in ("farmer", "fisher", "herder"):
                market += "; families eat much of their own"
        else:
            market = ""
        trow.append(f"<tr><td>{esc(job)}</td><td class='num'>{n}</td><td class='num'>{n / total:.0%}</td>"
                    f"<td class='chg'>{esc(chg)}</td><td class='chg'>{esc(market)}</td></tr>")
    h.append("<div class='section'><h4>Trades</h4><table><tr><th>Trade</th><th class='num'>Workers</th>"
             "<th class='num'>Share</th><th>Change</th><th>Market for it</th></tr>" + "".join(trow) + "</table>"
             "<p class='note'>Workers switch trades when another clearly pays better. 'Market for it' is how much "
             "of what the trade makes has been selling lately; too much unsold pulls workers away.</p></div>")

    # ---------------- language
    lang = language.ensure(w)
    new_words = [e for e in events_week if e["type"] == "new_word"]
    lw = f"<p>{s['words_known']} words in use; {s['dialect_words']} said differently in different regions.</p>"
    lw += ("<p>New this week: " + "; ".join(f"<i>{esc(e['data']['word'])}</i>, {esc(e['data']['meaning'])}"
                                           for e in new_words) + ".</p>") if new_words else "<p>No new words this week.</p>"
    changes = lang.get("changes", [])
    if changes:
        ch = changes[-1]
        lw += (f"<p>Latest change in speech: {esc(ch['desc'])}, begun in {esc(w.regions[ch['origin']].name)}, now heard "
               f"in {len(ch['regions'])} of {len(w.regions)} regions.</p>")
    elif lang.get("next_change_day"):
        lw += (f"<p>No changes in speech yet. The first is expected around "
               f"{esc(', '.join(label(lang['next_change_day']).split(', ')[:2]))}.</p>")
    lw += ("<p class='note'>A word is coined the first time something new happens, then spreads region by region. "
           "Changes in pronunciation start in one region and spread slowly, creating dialects.</p>")
    h.append("<div class='section'><h4>Language</h4>" + lw + "</div>")

    # ---------------- inventions
    invs = getattr(w, "inventions", None) or {}
    if invs:
        irow = "".join(f"<tr><td>{esc(INVENTIONS[k]['short'])}</td><td>{esc(r['inventor_name'])}</td>"
                       f"<td>{esc(w.regions[r['region']].name)}</td>"
                       f"<td class='num'>{sum(r['adoption'].values()) / len(r['adoption']):.0%}</td></tr>"
                       for k, r in invs.items())
        h.append("<div class='section'><h4>Inventions</h4><table><tr><th>Invention</th><th>Inventor</th>"
                 f"<th>Region</th><th class='num'>In use</th></tr>{irow}</table>"
                 "<p class='note'>In use is the average share of each region that has taken it up. Its benefit grows "
                 "with it.</p></div>")
    else:
        h.append("<div class='section'><h4>Inventions</h4><p>None yet.</p><p class='note'>Workers with two or more "
                 "years in a trade come up with about one improvement a year between them.</p></div>")

    # ---------------- champions
    from . import leisure, arts
    champs = leisure.champions(w)
    if any(c["national"] or any(c["regional"].values()) for c in champs.values()):
        crow = "".join(f"<tr><td>{esc(sp)}</td><td>{esc(c['national'] or 'not yet decided')}</td><td>"
                       + esc(", ".join(f"{r}: {n}" for r, n in c["regional"].items() if n) or "-") + "</td></tr>"
                       for sp, c in champs.items())
        h.append("<div class='section'><h4>Champions</h4><table><tr><th>Contest</th><th>National</th>"
                 f"<th>Regional</th></tr>{crow}</table><p class='note'>Regional titles are won at the harvest "
                 "festivals; regional champions meet for the national titles at the midwinter feast.</p></div>")
    else:
        y = year(w.day) if week_of_year(w.day) <= leisure.HARVEST_WEEK else year(w.day) + 1
        h.append(f"<div class='section'><h4>Champions</h4><p>No contests held yet. The first are at the harvest "
                 f"festival in Year {y}, autumn, week {leisure.HARVEST_WEEK}, if the president pays for it.</p></div>")

    # ---------------- arts
    works_all = arts.ensure(w)["works"]
    famous = [x for x in works_all.values() if x["famous"]]
    pops = arts.popular_by_region(w)
    ah = f"<p>{len(works_all)} works remembered; {len(famous)} famous.</p>"
    if pops:
        ah += "<p>Most popular now: " + "; ".join(
            f"{esc(w.regions[r].name)}: '{esc(x['title'])}' ({esc(x['title_en'])}), a {esc(x['kind'])} by "
            f"{esc(x['artist_name'])}" for r, x in pops.items()) + ".</p>"
    if famous:
        ah += "<p>Famous works: " + "; ".join(
            f"'{esc(x['title'])}' ({esc(x['title_en'])}) by {esc(x['artist_name'])}" for x in famous[-8:]) + ".</p>"
    ah += ("<p class='note'>About one person in ten is creative enough to make art on rest days, and each piece "
           "takes a few months. Works spread and compete for attention; the best become famous.</p>")
    h.append("<div class='section'><h4>Arts</h4>" + ah + "</div>")

    # ---------------- charts
    labs = [_short(r.get("label", "")) for r in history]
    series = [
        ("Population", [r.get("population") for r in history], lambda v: f"{v:.0f}"),
        ("Grain price", [_get(r, ["prices", "grain"]) for r in history], lambda v: f"{v:.2f}"),
        ("Satisfaction", [r.get("satisfaction") for r in history], lambda v: f"{v:.0%}"),
        ("Treasury", [_get(r, ["government", "treasury"]) for r in history], lambda v: f"{v:.0f}"),
    ]
    h.append("<div class='section'><h4>Over time</h4><div class='cols'>"
             + "".join(f"<div class='story'><h3>{t}</h3>{_spark(list(zip(labs, vals)), f)}</div>"
                       for t, vals, f in series)
             + "</div><p class='note'>One point per week, covering up to the last two years.</p></div>")
    h.append("<div class='nav'><a href='../paper/index.html'>Read the paper</a> | <a href='../index.html'>Home</a></div>")
    h.append("</div></body></html>")
    sdir = os.path.join(out_dir, "stats")
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(h))
    _home(w, out_dir, s)


def _home(w, out_dir, stats):
    paper_word = (language.word(w, "newspaper") or "gazette").capitalize()
    page = (f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{esc(w.nation_name)}</title><style>{CSS}</style>"
            f"</head><body><div class='page'><div class='mast'><h1>{esc(w.nation_name)}</h1>"
            f"<div class='sub'>{esc(stats['label'])} &middot; {stats['population']} people</div></div>"
            f"<ul style='font-size:20px'><li><a href='paper/index.html'>The {esc(paper_word)}</a>, the latest issue</li>"
            f"<li><a href='paper/archive.html'>Every issue</a></li>"
            f"<li><a href='stats/index.html'>The state of the nation</a></li></ul></div></body></html>")
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
