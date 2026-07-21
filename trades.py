#!/usr/bin/env python3
"""
Summarize the biggest Kalshi trades from the committed alert log
(data/cup/alerts.jsonl, each row a >$100 trade).

Separates directional flow from the "lay the field" premium-harvest pattern,
per the repo's analysis conventions:
  - YES buys, and NO buys at 80-90c  -> directional conviction
  - Winner-NO buys at >=90c across many drivers -> MM/premium harvest (discount)

CLI:
  python trades.py                 # today (UTC), full breakdown
  python trades.py --hours 2       # trailing 2 hours from the last trade
  python trades.py --date 2026-07-19
  python trades.py --min 300       # aggregate threshold for the positions table (default 300)
"""
import json, sys, os
from datetime import datetime, timedelta
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ALERTS = os.path.join(HERE, "data", "cup", "alerts.jsonl")

def ts(r):
    return datetime.fromisoformat(r['created_time'].replace('Z', '+00:00'))

def load():
    return sorted((json.loads(l) for l in open(ALERTS) if l.strip()), key=ts)

def pick(rows, hours=None, date=None):
    if hours is not None:
        cutoff = ts(rows[-1]) - timedelta(hours=hours)
        return [r for r in rows if ts(r) >= cutoff]
    if date is None:
        date = ts(rows[-1]).date().isoformat()
    return [r for r in rows if ts(r).date().isoformat() == date]

def summarize(rec, min_agg=300):
    if not rec:
        print("(no trades in window)"); return
    tot = sum(r['value_usd'] for r in rec)
    ys = sum(r['value_usd'] for r in rec if r.get('side') == 'yes')
    ns = sum(r['value_usd'] for r in rec if r.get('side') == 'no')
    lo, hi = ts(rec[0]).strftime('%H:%M'), ts(rec[-1]).strftime('%H:%M')
    print("%d trades (>$100 each) | $%.0f total | window %s-%s UTC" % (len(rec), tot, lo, hi))
    print("YES $%.0f   NO $%.0f\n" % (ys, ns))

    agg = defaultdict(float); cnt = defaultdict(int)
    for r in rec:
        k = (r.get('driver', '?'), r.get('tier', '?'), r.get('side', '?'))
        agg[k] += r['value_usd']; cnt[k] += 1
    print("=== biggest aggregate positions (driver/tier/side >= $%d) ===" % min_agg)
    for k, v in sorted(agg.items(), key=lambda x: -x[1]):
        if v >= min_agg:
            print("  %-18s %-6s %-3s n=%-3d $%8.0f" % (k[0][:18], k[1], k[2].upper(), cnt[k], v))

    yd = defaultdict(float)
    for r in rec:
        if r.get('side') == 'yes':
            yd[r['driver']] += r['value_usd']
    print("\n=== net YES by driver (directional) ===")
    for d, v in sorted(yd.items(), key=lambda x: -x[1])[:8]:
        print("  %-18s $%8.0f" % (d, v))

    lay = [r for r in rec if r.get('tier') == 'Winner' and r.get('side') == 'no'
           and r.get('price_cents', 0) >= 90]
    print("\nfield-lay (Winner-NO >=90c): %d trades, $%.0f, %d drivers -> discount as MM flow"
          % (len(lay), sum(r['value_usd'] for r in lay), len(set(r['driver'] for r in lay))))

if __name__ == "__main__":
    a = sys.argv[1:]
    hours = date = None; min_agg = 300
    if "--hours" in a: hours = float(a[a.index("--hours")+1])
    if "--date" in a: date = a[a.index("--date")+1]
    if "--min" in a: min_agg = int(a[a.index("--min")+1])
    summarize(pick(load(), hours=hours, date=date), min_agg=min_agg)
