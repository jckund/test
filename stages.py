#!/usr/bin/env python3
"""Book-vs-book comparison of the stage / pole markets captured by gen_stages.py.

There is **no Kalshi fair** for stage/pole markets, so this is purely relative:
it lines up each book's de-vigged win probability per driver, computes a
cross-book consensus (mean) and each book's deviation from it, and flags drivers
where a book is materially off consensus — i.e. a soft line to attack. With only
one book captured it just prints that book's de-vigged board.

  python stages.py [pole|stage1|stage2|all]     (default: all)

Reads data/cup/stages/*.json (override dir with STAGES_DIR).
"""
import glob
import json
import os
import sys

BASE = os.environ.get("STAGES_DIR", "data/cup/stages")
FLAG_PP = float(os.environ.get("STAGE_FLAG_PP", "2.0"))   # consensus-deviation flag, in points


def load_books() -> dict:
    out = {}
    for p in sorted(glob.glob(os.path.join(BASE, "*.json"))):
        d = json.load(open(p, encoding="utf-8"))
        out[d.get("source") or os.path.basename(p)] = d
    return out


def compare(market: str) -> None:
    books = load_books()
    have = {b: d for b, d in books.items() if market in (d.get("markets") or {})}
    if not have:
        print(f"\n=== {market} — no books captured ===")
        return
    table = {}   # driver -> {book: novig}
    for b, d in have.items():
        for drv in d["markets"][market]["drivers"]:
            table.setdefault(drv["name"], {})[b] = drv["novig"]
    bs = list(have)
    caps = " · ".join(f"{b} {have[b].get('captured_at','?')[11:16]}Z" for b in bs)
    print(f"\n=== {market} — {caps} (de-vigged win prob) ===")
    print(f"{'driver':20} " + " ".join(f"{b[:9]:>9}" for b in bs) +
          (f" {'cons':>7} {'maxdev':>7}" if len(bs) > 1 else ""))
    rows = []
    for drv, bv in table.items():
        present = [bv[b] for b in bs if b in bv]
        cons = sum(present) / len(present)
        dev = max((abs(bv[b] - cons) for b in bs if b in bv), default=0.0)
        rows.append((cons, drv, bv, dev))
    rows.sort(reverse=True)
    for cons, drv, bv, dev in rows:
        cells = " ".join((f"{bv[b] * 100:8.1f}%" if b in bv else f"{'—':>9}") for b in bs)
        extra = f" {cons * 100:6.1f}% {dev * 100:6.1f}pp" if len(bs) > 1 else ""
        star = "  <<soft" if (len(bs) > 1 and dev * 100 >= FLAG_PP) else ""
        print(f"{drv:20} {cells}{extra}{star}")
    if len(bs) == 1:
        print(f"(only {bs[0]} captured — add another book to compare)")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    markets = ["pole", "stage1", "stage2"] if which == "all" else [which]
    for m in markets:
        compare(m)
