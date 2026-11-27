"""Run a nation for many years in memory and print a yearly summary (for tuning)."""
import sys, time, tempfile, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sim.genesis import found_nation
from sim.events import EventLog
from sim import engine

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
years = int(sys.argv[2]) if len(sys.argv) > 2 else 10
w = found_nation(seed)
log = EventLog(os.path.join(tempfile.mkdtemp(), "e.db"))
t = time.time()
for y in range(years * 4):
    engine.run(w, log, 91)
    s = engine.weekly_stats(w)
    pr = s["prices"]
    print(f"{s['label'][:22]:22} pop {s['population']:4} hh {s['households']:3} homeless {s['homeless_households']:3} "
          f"sat {s['satisfaction']:.2f} hungry {s['hungry']:3} food {s['median_food_days']:5} "
          f"grain {pr['grain']:.2f} fish {pr['fish']:.2f} tools {pr['tools']:.1f} cloth {pr['cloth']:.1f} timber {pr['timber']:.2f}")
    if y % 4 == 3:
        print("   jobs", dict(sorted(s["jobs"].items())), "regions", s["by_region"])
print("seconds", round(time.time() - t, 1))
