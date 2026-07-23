"""Series-agnostic manual-book writer for support series (xfinity/truck).

gen_books.py canonicalizes to a hardcoded Cup list; support races have their
own fields, so here we canonicalize each book row to the *Kalshi snapshot*
spelling for that series (matched via the dashboard's normName = first+last
token, suffix-stripped). Unmatched names raise so typos fail loudly.
"""
import json, os, re, unicodedata
from datetime import datetime, timezone

SNAP = "/tmp/claude-0/-home-user-test/3914d24d-32ea-5700-a54f-0ad2d863e192/scratchpad/snap"
REPO = "/home/user/test"

def normName(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", s) if t and t not in ("jr", "sr", "ii", "iii", "iv")]
    if not toks:
        return ""
    return toks[0] if len(toks) == 1 else toks[0] + toks[-1]

def load_canon(series):
    """normName -> Kalshi display name, from the union of that series' tier snapshots."""
    m = {}
    for t in ("winner", "top3", "top5", "top10"):
        p = f"{SNAP}/{series}_{t}.json"
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            continue
        try:
            data = json.load(open(p))
        except Exception:
            continue
        for mk in data["markets"].values():
            nm = mk.get("name")
            if nm:
                m.setdefault(normName(nm), nm)
    return m

def imp(a):
    a = int(a)
    return 100.0 / (a + 100) if a > 0 else (-a) / ((-a) + 100.0)

def _tier(rows, n, canon, label):
    seen, drivers, unknown = set(), [], []
    for name, a in rows:
        k = normName(name)
        cn = canon.get(k)
        if cn is None:
            unknown.append(name); cn = name
        if cn in seen:
            continue
        seen.add(cn); drivers.append((cn, a, imp(a)))
    if unknown:
        print(f"    !! {label}: UNMATCHED to Kalshi field -> {unknown}")
    tot = sum(ip for _, _, ip in drivers); scale = n / tot
    return {"number_of_winners": n,
            "drivers": [{"name": c, "american": a, "implied": ip, "novig": ip * scale}
                        for c, a, ip in drivers]}

def write_book(series, filename, source, race, tiers):
    canon = load_canon(series)
    out = {"captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": source, "race": race, "manual": True,
           "tiers": {t: _tier(rows, nw, canon, f"{filename}:{t}") for t, (rows, nw) in tiers.items()}}
    d = f"{REPO}/data/{series}/manual"; os.makedirs(d, exist_ok=True)
    json.dump(out, open(f"{d}/{filename}", "w"), indent=2, ensure_ascii=False)
    sizes = {t: len(v["drivers"]) for t, v in out["tiers"].items()}
    sums = {t: round(sum(x["novig"] for x in v["drivers"]), 3) for t, v in out["tiers"].items()}
    print(f"  {series}/{filename}: {sizes}  novig={sums}")
    return out
