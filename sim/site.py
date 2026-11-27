"""The stats page and the front door of the nation's little website.

Writes plain HTML files into data/site/. A small web server container
serves that folder; Caddy points a subdomain at it.
"""
import html
import os

from . import config as C
from . import language
from .calendar import label
from .inventions import INVENTIONS
from .paper import CSS


def esc(s):
    return html.escape(str(s))


def _spark(values, width=300, height=60):
    """A tiny line chart as inline SVG."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    pts = []
    for i, v in enumerate(vals):
        x = i * (width - 4) / (len(vals) - 1) + 2
        y = height - 4 - (v - lo) / span * (height - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    return (f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' role='img'>"
            f"<polyline fill='none' stroke='#5a2d0c' stroke-width='2' points='{' '.join(pts)}'/></svg>"
            f"<div class='by'>low {lo:.2f}, high {hi:.2f}</div>")


def write_stats(w, log, out_dir, stats):
    history = list(reversed(log.recent_weeks(104)))
    g = stats["government"]
    pres = w.people.get(w.president)
    week_events = log.between(w.day - 7, w.day - 1, 1)
    new_words = [e for e in week_events if e["type"] == "new_word"]
    new_inv = [e for e in week_events if e["type"] == "invention"]
    rows = []

    def row(k, v):
        rows.append(f"<tr><th>{esc(k)}</th><td>{v}</td></tr>")

    h = [f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' "
         f"content='width=device-width,initial-scale=1'><title>{esc(w.nation_name)}: the state of the nation</title>"
         f"<style>{CSS}</style></head><body><div class='page'><div class='mast'><h1>{esc(w.nation_name)}</h1>"
         f"<div class='sub'>The state of the nation, {esc(stats['label'])}</div></div>"]

    # people
    row("Population", stats["population"])
    row("This week", f"{stats['births']} births, {stats['deaths']} deaths, {stats['marriages']} marriages")
    row("Households", f"{stats['households']} ({stats['homeless_households']} without a house)")
    row("Average satisfaction", f"{stats['satisfaction']:.0%}")
    row("Going hungry", stats["hungry"])
    row("Households close to hunger", stats.get("near_hunger_households", 0))
    row("Coins held by the richest tenth of households", f"{stats.get('richest_tenth_share', 0):.0%}")
    mood = stats.get("region_mood", {})
    regions = "".join(f"<tr><td>{esc(w.regions[k].name)}</td><td>{n}</td>"
                      f"<td>{mood.get(k, {}).get('satisfaction', 0):.0%}</td>"
                      f"<td>{mood.get(k, {}).get('approval', 0):.0%}</td></tr>" for k, n in stats["by_region"].items())
    h.append("<div class='section'><h4>People</h4><table>" + "".join(rows) + "</table>"
             "<h3 style='margin-top:10px'>By region</h3><table><tr><th>Region</th><th>People</th>"
             f"<th>Satisfaction</th><th>Approval</th></tr>{regions}</table></div>")

    # government
    rows = []
    row("President", esc(g["president"] or "none"))
    if pres:
        row("Term", f"began {esc(g['term_start'])}; {g['days_to_election']} days to the next vote "
                    f"({esc(g['next_election'])})")
    row("Approval", f"{g['approval']:.0%}")
    if g["petition"]:
        row("Recall petition", f"{g['petition']['signatures']} of {g['petition']['needed']} names")
    if g["recall_vote"]:
        row("Recall vote", esc(g["recall_vote"]))
    if g["candidates"]:
        row("Candidates", esc(", ".join(g["candidates"])))
    if g["promises"]:
        row("Promises outstanding", esc("; ".join(g["promises"])))
    h.append("<div class='section'><h4>Government</h4><table>" + "".join(rows) + "</table></div>")

    # treasury
    rows = []
    row("Treasury", f"{g['treasury']:.0f} coins")
    row("Market tax", f"{g['sales_tax']:.0%}" + (f", head tax {g['head_tax']:.2f} a week" if g["head_tax"] else ""))
    row("Coins in circulation", f"{g['money_supply']:.0f}" + (f" ({g['minted']:.0f} minted)" if g["minted"] else ""))
    row("Price level", f"{g['price_level']:.2f} (1.00 at the founding)")
    if g["subsidies"]:
        row("Subsidies", esc(", ".join(f"{j} {r:.2f}/day" for j, r in g["subsidies"].items())))
    works = [f for f in g["public_works"] if f["status"] == "building"]
    if works:
        row("Being built", esc(", ".join(f"{f['kind']} in {w.regions[f['region']].name}" for f in works)))
    done = [f for f in g["public_works"] if f["status"] == "done"]
    if done:
        row("Public works", esc(", ".join(f"{f['kind']} ({w.regions[f['region']].name})" for f in done)))
    h.append("<div class='section'><h4>Treasury</h4><table>" + "".join(rows) + "</table></div>")

    # economy
    prices = "".join(f"<tr><td>{esc(k)}</td><td>{v:.2f}</td></tr>" for k, v in stats["prices"].items())
    jobs = "".join(f"<tr><td>{esc(k)}</td><td>{v}</td></tr>"
                   for k, v in sorted(stats["jobs"].items(), key=lambda x: -x[1]))
    h.append("<div class='section'><h4>Economy</h4><div class='cols'><div class='story'><h3>Prices</h3>"
             f"<table>{prices}</table></div><div class='story'><h3>Workers by trade</h3><table>{jobs}</table>"
             "</div></div></div>")

    # language and inventions
    lines = [f"<i>{esc(e['data']['word'])}</i>: {esc(e['data']['meaning'])}" for e in new_words]
    lang_rows = (f"<p>{stats['words_known']} words known; {stats['dialect_words']} said differently in different "
                 "regions.</p>")
    lang_rows += ("<p>New this week: " + "; ".join(lines) + "</p>") if lines else "<p>No new words this week.</p>"
    invs = [INVENTIONS[k]["short"] for k in stats["inventions"]]
    inv_rows = (f"<p>Known: {esc(', '.join(invs))}.</p>" if invs else "<p>None yet.</p>")
    if new_inv:
        inv_rows += "<p>New this week: " + "; ".join(esc(e["summary"]) for e in new_inv) + "</p>"
    h.append("<div class='section'><h4>Language</h4>" + lang_rows + "</div>")
    h.append("<div class='section'><h4>Inventions</h4>" + inv_rows + "</div>")

    # games and arts
    from . import leisure, arts
    champs = leisure.champions(w)
    crow = "".join(f"<tr><td>{esc(s)}</td><td>{esc(c['national'] or '-')}</td><td>"
                   + esc(", ".join(f"{r}: {n}" for r, n in c["regional"].items() if n) or "-") + "</td></tr>"
                   for s, c in champs.items())
    h.append("<div class='section'><h4>Champions</h4><table><tr><th>Contest</th><th>National</th><th>Regional</th></tr>"
             f"{crow}</table></div>")
    works = arts.ensure(w)["works"]
    famous = [x for x in works.values() if x["famous"]]
    pops = arts.popular_by_region(w)
    art_html = f"<p>{len(works)} works remembered; {len(famous)} famous.</p>"
    if pops:
        art_html += "<p>Most popular now: " + "; ".join(
            f"{esc(w.regions[r].name)}: '{esc(x['title'])}' ({esc(x['title_en'])}), a {esc(x['kind'])} by "
            f"{esc(x['artist_name'])}" for r, x in pops.items()) + "</p>"
    if famous:
        art_html += "<p>Famous works: " + "; ".join(
            f"'{esc(x['title'])}' ({esc(x['title_en'])}) by {esc(x['artist_name'])}" for x in famous[-8:]) + "</p>"
    h.append("<div class='section'><h4>Arts</h4>" + art_html + "</div>")

    # charts
    if len(history) >= 2:
        h.append("<div class='section'><h4>Over time</h4><div class='cols'>"
                 "<div class='story'><h3>Population</h3>" + _spark([x["population"] for x in history]) + "</div>"
                 "<div class='story'><h3>Grain price</h3>" + _spark([x["prices"]["grain"] for x in history]) + "</div>"
                 "<div class='story'><h3>Satisfaction</h3>" + _spark([x["satisfaction"] for x in history]) + "</div>"
                 "<div class='story'><h3>Treasury</h3>" + _spark([x.get("government", {}).get("treasury")
                                                                  for x in history]) + "</div>"
                 "</div></div>")
    h.append("<div class='nav'><a href='../paper/index.html'>Read the paper</a> | <a href='../index.html'>Home</a></div>")
    h.append("</div></body></html>")
    sdir = os.path.join(out_dir, "stats")
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(h))
    _home(w, out_dir, stats)


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
