#!/usr/bin/env python3
"""
Kalshi finish-distribution EV model for NASCAR Cup matchups + book scans.

Kalshi = fair. Each driver's finish is modeled as a distribution over buckets
(win / 2-3 / 4-5 / 6-10 / 11-38) derived from the Kalshi winner/top3/top5/top10
markets (bid/ask midpoints). Matchup P(A ahead of B) is estimated by Monte-Carlo
sampling a finishing position for each from those buckets (shared tail ~ uniform).

Reads committed snapshots at data/cup/<tier>/snapshot.json — so it works in a
fresh session with no setup.

CLI:
  # Head-to-head matchups: each arg is "Driver A,oddsA,Driver B,oddsB"
  python ev_model.py h2h "Ty Gibbs,-201,Tyler Reddick,165" "Carson Hocevar,-176,Ryan Preece,147"

  # Book scan: value a book's tier prices vs Kalshi fair (raw implied)
  #   pass a manual book json + tier
  python ev_model.py book data/cup/manual/betus.json top3

Both print an EV table (edge in pp + EV% = model_P*decimal - 1), +EV first.
Import-friendly: pAhead(), buckets(), evPct() are reusable.
"""
import json, sys, os, unicodedata, random

HERE = os.path.dirname(os.path.abspath(__file__))
CUP = os.path.join(HERE, "data", "cup")
RNG_SEED = 21          # fixed so runs are reproducible
N_SAMPLES = 300_000

# Book/matchup inputs spell some drivers differently than the Kalshi snapshot
# (e.g. "John Hunter Nemechek" vs Kalshi's "John H. Nemechek", or a trailing
# "Jr"). Strip suffixes + punctuation and map the non-collapsing variants onto
# the Kalshi spelling so lookups don't silently return 0. Mirrors gen_books.
_ALIAS = {
    "john hunter nemechek": "john h nemechek",
    "darrell wallace": "bubba wallace",
}

def norm(s):
    n = (unicodedata.normalize('NFKD', s or '')
         .encode('ascii', 'ignore').decode().lower().replace('.', '').replace('-', ' '))
    n = ' '.join(n.split())
    for suf in (' jr', ' sr', ' ii', ' iii'):
        if n.endswith(suf):
            n = n[:-len(suf)]
    n = ' '.join(n.split())
    return _ALIAS.get(n, n)

def am_imp(o):
    o = int(o); return (-o)/((-o)+100) if o < 0 else 100/(o+100)

def dec(o):
    o = int(o); return 1 + (o/100 if o > 0 else 100/(-o))

def evPct(p, american):
    """Expected return per $1 staked = p*decimal - 1. >0 iff line longer than fair."""
    return p * dec(american) - 1

def _load_tier(tier):
    path = os.path.join(CUP, tier, "snapshot.json")
    d = json.load(open(path)); ms = d.get('markets', d)
    return {norm(m['name']): ((m['yes_bid'] + m['yes_ask']) / 2) / 100.0 for m in ms.values()}

def load_kalshi():
    return {t: _load_tier(t) for t in ('winner', 'top3', 'top5', 'top10')}

def buckets(nm, K):
    n = norm(nm)
    w  = K['winner'].get(n, 0)
    t3 = max(K['top3'].get(n, 0), w)
    t5 = max(K['top5'].get(n, 0), t3)
    t10 = max(K['top10'].get(n, 0), t5)
    return {'win': w, 'p23': max(0, t3-w), 'p45': max(0, t5-t3),
            'p610': max(0, t10-t5), 'p11': max(0, 1-t10)}

_RANGES = {'win': (1, 1), 'p23': (2, 3), 'p45': (4, 5), 'p610': (6, 10), 'p11': (11, 38)}

def _sample(b, rng):
    ks = list(b); ws = [b[k] for k in ks]; tot = sum(ws)
    if tot <= 0:
        return 38
    r = rng.random() * tot; c = 0
    for k, wt in zip(ks, ws):
        c += wt
        if r <= c:
            lo, hi = _RANGES[k]; return rng.uniform(lo, hi + 0.999)
    return 38

def pAhead(a, b, K, n=N_SAMPLES, seed=RNG_SEED):
    rng = random.Random(seed)
    ba, bb = buckets(a, K), buckets(b, K)
    wins = ties = 0
    for _ in range(n):
        pa, pb = _sample(ba, rng), _sample(bb, rng)
        if pa < pb: wins += 1
        elif pa == pb: ties += 1
    return (wins + ties * 0.5) / n

def _print_rows(rows):
    rows.sort(reverse=True)
    print("%-22s %6s %7s %7s %7s %8s" % ("bet", "odds", "modelP", "implied", "edge", "EV%"))
    for ev, nm, o, p, imp, edge in rows:
        print("%-22s %+6d %6.1f%% %6.1f%% %+6.1f %+7.1f%%" % (nm, o, p, imp, edge, ev*100))
    if not rows:
        print("(no +EV side found)")

def cmd_h2h(args):
    K = load_kalshi(); rows = []
    for spec in args:
        a, oa, b, ob = [x.strip() for x in spec.split(',')]
        oa, ob = int(oa), int(ob)
        pa = pAhead(a, b, K); pb = 1 - pa
        for nm, o, p in [(a, oa, pa), (b, ob, pb)]:
            ev = evPct(p, o)
            if ev > 0:
                rows.append((ev, nm, o, p*100, am_imp(o)*100, (p-am_imp(o))*100))
    _print_rows(rows)

def cmd_book(args):
    """Value each driver's book price in <tier> vs Kalshi fair (raw implied)."""
    path, tier = args[0], args[1]
    K = load_kalshi(); fair = K[tier]
    d = json.load(open(path)); rows = []
    for drv in d['tiers'][tier]['drivers']:
        p = fair.get(norm(drv['name']))
        o = drv.get('american')
        if p is None or o is None:
            continue
        ev = evPct(p, o)
        if ev > 0:
            rows.append((ev, drv['name'], o, p*100, am_imp(o)*100, (p-am_imp(o))*100))
    print("%s  %s vs Kalshi fair:" % (d.get('source', path), tier))
    _print_rows(rows)

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("h2h", "book"):
        print(__doc__); sys.exit(1)
    (cmd_h2h if sys.argv[1] == "h2h" else cmd_book)(sys.argv[2:])
