"""Run a nation for many years in memory and print a summary each season (for tuning)."""
import sys, time, tempfile, os, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.genesis import found_nation
from sim.events import EventLog
from sim import engine

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
years = int(sys.argv[2]) if len(sys.argv) > 2 else 10
show = int(sys.argv[3]) if len(sys.argv) > 3 else 4   # importance of events to print
w = found_nation(seed)
path = os.path.join(tempfile.mkdtemp(), "e.db")
log = EventLog(path)
t = time.time()
last = w.day
for y in range(years * 4):
    engine.run(w, log, 91)
    s = engine.weekly_stats(w)
    g = s["government"]
    pr = s["prices"]
    print(f"{s['label'][:24]:24} pop {s['population']:4} homeless {s['homeless_households']:3} sat {s['satisfaction']:.2f} "
          f"hungry {s['hungry']:3} grain {pr['grain']:.2f} | pres {g['president']} appr {g['approval']:.2f} "
          f"treas {g['treasury']:.0f} tax {g['sales_tax']:.2f}/{g['head_tax']} lvl {g['price_level']} works {len(g['public_works'])}")
    for ev in log.between(last, w.day, show):
        print("     ", ev["summary"])
    last = w.day + 1
counts = collections.Counter(e["type"] for e in log.between(0, w.day, 1))
print(dict(counts.most_common()))
print("seconds", round(time.time() - t, 1))
