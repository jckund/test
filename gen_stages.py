#!/usr/bin/env python3
"""Manual capture of NASCAR **stage / pole** "which driver wins" markets.

Stage 1, Stage 2 and pole are single-winner markets that the finish-tier pipeline
(``gen_books.py``) doesn't cover, and **Kalshi doesn't list them** — so there is
no "fair" anchor the way there is for win/top3/top5/top10. We store each book's
board de-vigged (no-vig normalized to a single winner) under
``data/cup/stages/<book>.json`` purely for **book-vs-book** comparison (see
``stages.py``). These files are NOT read by the dashboard.

Reuses ``gen_books`` canonicalization (Cup driver names) + implied/no-vig math.

    import gen_stages as gs
    gs.write_stages("caesars.json", "Caesars", {
        "pole":   [("Denny Hamlin", 350), ...],   # (name, american)
        "stage1": [("Denny Hamlin", 400), ...],
        "stage2": [("Denny Hamlin", 400), ...],
    })

Only the markets you pass are written, so a book that posts just Stage 1 is fine.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import gen_books as gb

RACE = os.environ.get("RACE_NAME", gb.RACE)
BASE = os.environ.get("STAGES_DIR", "data/cup/stages")
MARKETS = ("pole", "stage1", "stage2")


def _market(rows) -> dict:
    """rows: list of (name, american) for a single-winner market -> market dict."""
    seen, drivers = set(), []
    for name, a in rows:
        c = gb.canon(name)
        if c in seen:      # keep first (main-grid) occurrence, mirror gen_books
            continue
        seen.add(c)
        drivers.append((c, a))
    total = sum(gb.imp(a) for _, a in drivers)
    scale = 1.0 / total    # one winner -> novig sums to 1
    return {"number_of_winners": 1,
            "drivers": [{"name": c, "american": a, "implied": gb.imp(a), "novig": gb.imp(a) * scale}
                        for c, a in drivers]}


def write_stages(filename: str, source: str, markets: dict) -> dict:
    """markets: {market_key: [(name, american)]}. Writes BASE/filename."""
    obj = {"captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "source": source, "race": RACE, "manual": True,
           "markets": {k: _market(rows) for k, rows in markets.items()}}
    os.makedirs(BASE, exist_ok=True)
    with open(os.path.join(BASE, filename), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    return obj


if __name__ == "__main__":
    t = _market([("Denny Hamlin", 400), ("Ryan Blaney", 500), ("Kyle Larson", 650)])
    assert abs(sum(d["novig"] for d in t["drivers"]) - 1.0) < 1e-9
    print("gen_stages self-test OK")
