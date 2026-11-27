"""Command line for the nation.

  python -m sim found [--seed N] [--force]   start a new nation
  python -m sim run [--days 7]               advance the nation
  python -m sim status                       print a short summary
  python -m sim events [--days 7] [--min 2]  print recent events
"""
import argparse
import json
import os
import sys

from . import storage, engine, paper, site as website
from .events import EventLog
from .genesis import found_nation
from .calendar import label

DEFAULT_DATA = os.environ.get("NATION_DATA", "data")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sim")
    ap.add_argument("--data", default=DEFAULT_DATA, help="folder holding the nation's files")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("found")
    f.add_argument("--seed", type=int, default=None)
    f.add_argument("--force", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--no-paper", action="store_true", help="skip publishing the paper")
    sub.add_parser("paper", help="publish an issue covering the last week")
    sub.add_parser("status")
    e = sub.add_parser("events")
    e.add_argument("--days", type=int, default=7)
    e.add_argument("--min", type=int, default=2)
    args = ap.parse_args(argv)

    if args.cmd == "found":
        if storage.exists(args.data) and not args.force:
            sys.exit("A nation already exists here. Use --force to replace it.")
        if args.force and os.path.exists(storage.events_path(args.data)):
            os.remove(storage.events_path(args.data))
        seed = args.seed if args.seed is not None else int.from_bytes(os.urandom(4), "big")
        w = found_nation(seed)
        os.makedirs(args.data, exist_ok=True)
        log = EventLog(storage.events_path(args.data))
        pres = w.people[w.president]
        log.add(w.day, "founding", f"The nation of {w.nation_name} is founded with {len(w.people)} people. "
                f"{pres.name} is its first president.", importance=5, people=[pres.id])
        log.close()
        storage.save(w, args.data)
        print(f"Founded {w.nation_name} (seed {seed}) with {len(w.people)} people. {label(w.day)}.")
        return

    if not storage.exists(args.data):
        sys.exit("No nation found. Run: python -m sim found")
    w = storage.load(args.data)
    log = EventLog(storage.events_path(args.data))

    site = os.path.join(args.data, "site")
    if args.cmd == "run":
        engine.run(w, log, args.days)
        s = engine.weekly_stats(w)
        if not args.no_paper:
            weeks = log.recent_weeks(2)
            path = paper.publish(w, log, site, s, weeks[1] if len(weeks) > 1 else None)
            print(f"Published {path}")
        website.write_stats(w, log, site, s)
        log.flush()
        storage.save(w, args.data)
        storage.snapshot(w, args.data)
        log.close()
        print(f"{s['label']}: population {s['population']}, satisfaction {s['satisfaction']}, "
              f"grain {s['prices']['grain']}")
    elif args.cmd == "paper":
        s = engine.weekly_stats(w)
        weeks = log.recent_weeks(2)
        print("Published", paper.publish(w, log, site, s, weeks[1] if len(weeks) > 1 else None))
        website.write_stats(w, log, site, s)
        log.flush()
        storage.save(w, args.data)
    elif args.cmd == "status":
        print(json.dumps(engine.weekly_stats(w), indent=2))
    elif args.cmd == "events":
        for ev in log.between(w.day - args.days, w.day, args.min):
            print(f"[{label(ev['day'])}] {ev['summary']}")
    log.close()


if __name__ == "__main__":
    main()
