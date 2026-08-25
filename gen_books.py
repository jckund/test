#!/usr/bin/env python3
"""Reusable builder for the manually-entered sportsbook JSON files.

Books other than Kalshi/FanDuel are entered by hand from a posted board. This
module turns raw ``(driver_name, american_odds)`` rows into the normalized
``data/cup/manual/<book>.json`` (and ``mfr_<book>.json`` / ``team_<book>.json``)
shape the dashboard expects: each driver gets ``implied`` (raw, with vig) and
``novig`` (de-vigged, normalized so a tier's probabilities sum to its number of
winners — 1 for winner/which-make/team, 3/5/10 for the finish tiers).

It also canonicalizes driver names to the Kalshi spelling so a book's
"Darrell Wallace Jr", "A.J. Allmendinger", "Michael Mcdowell", "Shane van
Gisbergen", "Daniel Suarez" all map onto the same driver the rest of the site
uses. Unknown names raise, so a typo fails loudly instead of silently forking a
driver into two rows.

USAGE (from a session, adapt the data to the pasted board):

    import gen_books as gb
    win = [("Ryan Blaney", 650), ("Joey Logano", 1000), ...]   # (name, american)
    t3  = [("Ryan Blaney", 275), ...]
    gb.write_book("betonline.json", "BetOnline",
                  {"winner": (win, 1), "top3": (t3, 3), "top10": (t10, 10)})
    gb.write_mfr("mfr_betonline.json", "BetOnline",
                 {"Chevrolet": 135, "Ford": 165, "Toyota": 220},          # which-make 3-way
                 {"Chevrolet": chevy_rows, "Ford": ford_rows, "Toyota": toy_rows})
    gb.write_team("team_betonline.json", "BetOnline", team_rows)

Dedup: within a tier the first occurrence of a canonical driver wins (books
sometimes list the same driver twice with different odds; keep the main-grid
row and drop the duplicate). No-vig assumes the tier's rows cover the field.

De-vig math: novig_i = implied_i * (number_of_winners / sum(implied)).
Run `python3 gen_books.py` for a self-test on synthetic rows.
"""

from __future__ import annotations

import json
import os
import unicodedata
from datetime import datetime, timezone

RACE = os.environ.get("RACE_NAME", "Quaker State 400 Available at Walmart")
BASE = os.environ.get("MANUAL_DIR", "data/cup/manual")

# Canonical Kalshi Cup driver names (the spelling the rest of the site uses).
CANON = [
    "Ryan Blaney", "Chase Elliott", "Tyler Reddick", "Joey Logano", "William Byron",
    "Carson Hocevar", "Christopher Bell", "Kyle Larson", "Denny Hamlin", "Chase Briscoe",
    "Austin Cindric", "Brad Keselowski", "Ross Chastain", "Bubba Wallace", "Chris Buescher",
    "Ty Gibbs", "Daniel Suárez", "Alex Bowman", "Ryan Preece", "Austin Hill", "Ricky Stenhouse",
    "Austin Dillon", "Erik Jones", "Michael McDowell", "Zane Smith", "AJ Allmendinger",
    "Shane Van Gisbergen", "Josh Berry", "Connor Zilisch", "Todd Gilliland", "Riley Herbst",
    "John H. Nemechek", "Noah Gragson", "Ty Dillon", "Cole Custer", "Cody Ware", "BJ McLeod",
    "Chad Finchum", "Corey Heim", "Casey Mears", "Daniel Dye", "Josh Bilicki",
    "Joey Gase", "Gray Gaulding",
]


def _key(name: str) -> str:
    """Normalize a name to a match key: strip accents/punctuation/suffixes, lowercase."""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    n = n.lower().replace(".", "").replace("-", " ")
    for suf in (" jr", " sr", " ii", " iii"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return " ".join(n.split())


# For non-NASCAR trackers (golf) the canonical roster isn't a fixed list — it's
# whatever players Kalshi lists for the event. Point CANON_SNAPSHOT at a scraped
# winner snapshot (e.g. data/tourchamp/winner/snapshot.json) and the roster +
# exact name spellings come straight from it; the NASCAR driver list and aliases
# don't apply.
_CANON_SNAPSHOT = os.environ.get("CANON_SNAPSHOT")
if _CANON_SNAPSHOT:
    import json as _json
    with open(_CANON_SNAPSHOT, encoding="utf-8") as _fh:
        _snap = _json.load(_fh)
    CANON = sorted({(m.get("name") or "").strip()
                    for m in _snap.get("markets", {}).values() if m.get("name")})
    _ALIAS = {}
else:
    # Aliases whose key doesn't collapse onto the canonical spelling.
    _ALIAS = {"john hunter nemechek": "John H. Nemechek", "darrell wallace": "Bubba Wallace"}

_BYKEY = {_key(c): c for c in CANON}


def canon(name: str) -> str:
    """Canonical Kalshi spelling for a book's driver name. Raises on unknown."""
    k = _key(name)
    if k in _ALIAS:
        return _ALIAS[k]
    if k in _BYKEY:
        return _BYKEY[k]
    raise KeyError(f"gen_books: no canonical driver for {name!r} (key {k!r})")


def imp(american: int) -> float:
    """Implied probability (with vig) from American odds."""
    return 100.0 / (american + 100) if american > 0 else (-american) / ((-american) + 100.0)


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_tier(rows, n_winners: int) -> dict:
    """rows: list of (name, american). Returns a tier dict with implied+novig."""
    seen, drivers = set(), []
    for name, a in rows:
        c = canon(name)
        if c in seen:
            continue
        seen.add(c)
        drivers.append((c, a, imp(a)))
    total = sum(ip for _, _, ip in drivers)
    scale = n_winners / total
    return {
        "number_of_winners": n_winners,
        "drivers": [{"name": c, "american": a, "implied": ip, "novig": ip * scale}
                    for c, a, ip in drivers],
    }


def write_book(filename: str, source: str, tiers: dict) -> dict:
    """tiers: {tier_key: (rows, n_winners)}. Writes BASE/filename, returns the object."""
    obj = {"captured_at": _ts(), "source": source, "race": RACE, "manual": True,
           "tiers": {t: build_tier(rows, nw) for t, (rows, nw) in tiers.items()}}
    with open(f"{BASE}/{filename}", "w") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    return obj


def write_mfr(filename: str, source: str, which_make: dict, makes: dict) -> dict:
    """which_make: {make: american} (3-way). makes: {make: [(name, american)]}."""
    s = sum(imp(a) for a in which_make.values())
    win = {mk: {"american": a, "implied": imp(a), "novig": imp(a) / s} for mk, a in which_make.items()}
    mk_out = {}
    for mk, rows in makes.items():
        ss = sum(imp(a) for _, a in rows)
        mk_out[mk] = {"drivers": [{"name": canon(n), "american": a, "implied": imp(a), "novig": imp(a) / ss}
                                  for n, a in rows]}
    obj = {"captured_at": _ts(), "source": source, "race": RACE, "winner": win, "makes": mk_out}
    with open(f"{BASE}/{filename}", "w") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    return obj


def write_team(filename: str, source: str, teams) -> dict:
    """teams: list of (team_name, american). Team names are used as-is."""
    s = sum(imp(a) for _, a in teams)
    win = {nm: {"american": a, "implied": imp(a), "novig": imp(a) / s} for nm, a in teams}
    obj = {"captured_at": _ts(), "source": source, "race": RACE, "winner": win}
    with open(f"{BASE}/{filename}", "w") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    return obj


if __name__ == "__main__":
    # Self-test: canonicalization + no-vig normalization.
    assert canon("Darrell Wallace Jr") == "Bubba Wallace"
    assert canon("A.J. Allmendinger") == "AJ Allmendinger"
    assert canon("Shane van Gisbergen") == "Shane Van Gisbergen"
    assert canon("John Hunter Nemechek") == "John H. Nemechek"
    assert canon("Daniel Suarez") == "Daniel Suárez"
    t = build_tier([("Ryan Blaney", 650), ("Joey Logano", 1000), ("Kyle Larson", 1200)], 1)
    assert abs(sum(d["novig"] for d in t["drivers"]) - 1.0) < 1e-9
    print("gen_books self-test OK — canonicalization and no-vig normalization pass")
