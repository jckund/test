#!/usr/bin/env python3
"""Scrape Kalshi NASCAR race markets and track changes over time.

Race page:
  https://kalshi.com/markets/kxnascarrace/nascar-race/kxnascarrace-quas4aa26

Tracks several markets for the same race, each a separate Kalshi event:
  Winner, Top 3, Top 5, Top 10, Top 20 finishers.

The public website is Cloudflare-protected, but Kalshi's public trade API
serves the same data. For each event we read the nested markets, normalize the
fields we care about, and write them under ``data/<tier>/``. Change tracking:
  * ``data/<tier>/snapshot.json`` — normalized current state (git history == log)
  * ``data/<tier>/history.jsonl`` — append-only, one record per changed run
  * ``data/<tier>/series.jsonl``  — aligned price series for sparklines
  * ``data/<tier>/CHANGES.md``    — human-readable change log
  * ``data/index.json``           — the list of tracked tiers, for the dashboard

Only writes when a tier's market state actually changes, so a scheduled commit
step can use ``git diff`` to avoid empty commits.

Run manually with:  python3 scraper.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Race code from the page URL's event ticker: KXNASCARRACE-<RACE_CODE>.
# Change this one value (or the env var) to point at a different race.
RACE_CODE = os.environ.get("KALSHI_RACE_CODE", "QUAS4AA26")

# (tier key, display label, odds-column label, Kalshi series ticker)
TIERS = [
    ("winner", "Winner", "Win", "KXNASCARRACE"),
    ("top3", "Top 3", "Top 3", "KXNASCARTOP3"),
    ("top5", "Top 5", "Top 5", "KXNASCARTOP5"),
    ("top10", "Top 10", "Top 10", "KXNASCARTOP10"),
    ("top20", "Top 20", "Top 20", "KXNASCARTOP20"),
]
EVENTS = [
    {"key": k, "label": lbl, "odds_label": odl, "ticker": f"{series}-{RACE_CODE}"}
    for k, lbl, odl, series in TIERS
]

PAGE_URL = (
    "https://kalshi.com/markets/kxnascarrace/nascar-race/"
    "kxnascarrace-quas4aa26"
)
API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")
ACTIVITY_PATH = os.path.join(DATA_DIR, "activity.json")

# "Recent Activity" = recent trades. Kalshi's trades endpoint only filters by a
# single market ticker, so we poll each market and merge. Kept small per market
# and capped overall; regenerated (not committed) each run as a live feed.
TRADES_PER_MARKET = 10
ACTIVITY_MAX = 150

# Per-market fields we compare between runs to detect a meaningful change.
TRACKED_FIELDS = [
    "status", "last_price", "yes_bid", "yes_ask",
    "no_bid", "no_ask", "volume", "open_interest",
]
MAX_SERIES = 1000
USER_AGENT = "kalshi-nascar-tracker/2.0 (+https://github.com; scheduled scraper)"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _get_json(url: str, retries: int = 4) -> dict:
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
            last_err = err
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  fetch failed ({err}); retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"failed to GET {url}: {last_err}")


def fetch_event(ticker: str) -> dict:
    url = f"{API_BASE}/events/{ticker}?with_nested_markets=true"
    print(f"Fetching {url}", file=sys.stderr)
    return _get_json(url)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _price_cents(m: dict, base: str):
    """Price in integer cents. Kalshi's newer schema returns dollar strings
    (``last_price_dollars: "0.0100"``); other endpoints return integer cents
    (``last_price``). Support both."""
    v = m.get(base)
    if isinstance(v, (int, float)):
        return int(round(v))
    d = _to_float(m.get(base + "_dollars"))
    return None if d is None else int(round(d * 100))


def _count(m: dict, base: str):
    """Contract count. Newer schema uses fixed-point strings (``volume_fp``)."""
    v = m.get(base)
    if isinstance(v, (int, float)):
        return int(round(v))
    fp = _to_float(m.get(base + "_fp"))
    return None if fp is None else int(round(fp))


def _dollars(m: dict, base: str):
    v = m.get(base)
    if isinstance(v, (int, float)):
        return v
    d = _to_float(m.get(base + "_dollars"))
    return None if d is None else round(d, 2)


def _dollars_to_cents(s):
    d = _to_float(s)
    return None if d is None else int(round(d * 100))


def implied_yes_cents(m: dict):
    """Best estimate of P(yes) in cents. Thinly-traded markets often have a
    stale or zero last_price, so prefer the live yes bid/ask midpoint, then
    the no side (100 − no), then last trade, then a single quote."""
    yb, ya = m.get("yes_bid"), m.get("yes_ask")
    if isinstance(yb, int) and isinstance(ya, int):
        return round((yb + ya) / 2)
    nb, na = m.get("no_bid"), m.get("no_ask")
    if isinstance(nb, int) and isinstance(na, int):
        return 100 - round((nb + na) / 2)
    lp = m.get("last_price")
    if isinstance(lp, int) and lp > 0:
        return lp
    for v in (ya, yb):
        if isinstance(v, int):
            return v
    return None


def normalize(raw: dict, ev: dict) -> dict:
    event = raw.get("event", {}) or {}
    markets = raw.get("markets") or event.get("markets") or []

    norm_markets = {}
    for m in markets:
        ticker = m.get("ticker")
        if not ticker:
            continue
        norm_markets[ticker] = {
            "ticker": ticker,
            "name": m.get("yes_sub_title") or m.get("no_sub_title") or m.get("title"),
            "status": m.get("status"),
            "last_price": _price_cents(m, "last_price"),
            "yes_bid": _price_cents(m, "yes_bid"),
            "yes_ask": _price_cents(m, "yes_ask"),
            "no_bid": _price_cents(m, "no_bid"),
            "no_ask": _price_cents(m, "no_ask"),
            "volume": _count(m, "volume"),
            "volume_24h": _count(m, "volume_24h"),
            "open_interest": _count(m, "open_interest"),
            "liquidity": _dollars(m, "liquidity"),
        }

    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": PAGE_URL,
        "tier": ev["key"],
        "label": ev["label"],
        "odds_label": ev["odds_label"],
        "event_ticker": ev["ticker"],
        "event": {
            "title": event.get("title"),
            "sub_title": event.get("sub_title"),
            "series_ticker": event.get("series_ticker"),
            "category": event.get("category"),
        },
        "market_count": len(norm_markets),
        "markets": norm_markets,
    }


# ---------------------------------------------------------------------------
# Change detection
# ---------------------------------------------------------------------------

def load_previous(snapshot_path: str):
    if not os.path.exists(snapshot_path):
        return None
    try:
        with open(snapshot_path, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def diff_snapshots(prev, curr) -> list:
    changes = []
    curr_markets = curr.get("markets", {})
    if prev is None:
        return [{"type": "initial_snapshot", "market_count": len(curr_markets)}]

    prev_markets = prev.get("markets", {})
    for ticker, market in curr_markets.items():
        if ticker not in prev_markets:
            changes.append({"type": "market_added", "ticker": ticker, "name": market.get("name")})
            continue
        old = prev_markets[ticker]
        field_changes = {}
        for field in TRACKED_FIELDS:
            if market.get(field) != old.get(field):
                field_changes[field] = {"from": old.get(field), "to": market.get(field)}
        if field_changes:
            changes.append({
                "type": "market_changed", "ticker": ticker,
                "name": market.get("name"), "fields": field_changes,
            })
    for ticker in prev_markets:
        if ticker not in curr_markets:
            changes.append({"type": "market_removed", "ticker": ticker,
                            "name": prev_markets[ticker].get("name")})
    return changes


# ---------------------------------------------------------------------------
# Output (per tier)
# ---------------------------------------------------------------------------

def _cents(v) -> str:
    return f"{v}¢" if isinstance(v, (int, float)) else "—"


def write_outputs(base: str, raw: dict, curr: dict, changes: list) -> None:
    os.makedirs(base, exist_ok=True)

    with open(os.path.join(base, "latest.json"), "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, sort_keys=True)
        fh.write("\n")
    with open(os.path.join(base, "snapshot.json"), "w", encoding="utf-8") as fh:
        json.dump(curr, fh, indent=2, sort_keys=True)
        fh.write("\n")

    record = {"scraped_at": curr["scraped_at"], "change_count": len(changes), "changes": changes}
    with open(os.path.join(base, "history.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    _append_series(base, curr)
    _write_changes_md(base, curr, changes)


def _append_series(base: str, curr: dict) -> None:
    # Store the implied (mid-market) price so sparklines are meaningful even
    # for thinly-traded tiers where last_price barely moves.
    point = {"t": curr["scraped_at"],
             "p": {t: implied_yes_cents(m) for t, m in curr["markets"].items()}}
    path = os.path.join(base, "series.jsonl")
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    lines.append(json.dumps(point, separators=(",", ":")))
    lines = lines[-MAX_SERIES:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _write_changes_md(base: str, curr: dict, changes: list) -> None:
    path = os.path.join(base, "CHANGES.md")
    ts = curr["scraped_at"]
    lines = [f"### {ts}", ""]

    markets = sorted(curr["markets"].values(),
                     key=lambda m: (m.get("last_price") is None, -(m.get("last_price") or 0)))
    lines.append("| Driver | Last | Yes bid/ask | Volume | OI |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for m in markets:
        lines.append(
            f"| {m.get('name') or m.get('ticker')} | {_cents(m.get('last_price'))} "
            f"| {_cents(m.get('yes_bid'))} / {_cents(m.get('yes_ask'))} "
            f"| {m.get('volume') if m.get('volume') is not None else '—'} "
            f"| {m.get('open_interest') if m.get('open_interest') is not None else '—'} |")
    lines.append("")
    lines.append(f"**{len(changes)} change(s) since previous snapshot:**")
    lines.append("")
    for c in changes:
        if c["type"] == "initial_snapshot":
            lines.append(f"- Initial snapshot captured ({c['market_count']} markets).")
        elif c["type"] == "market_added":
            lines.append(f"- ➕ Added: {c.get('name') or c['ticker']}")
        elif c["type"] == "market_removed":
            lines.append(f"- ➖ Removed: {c.get('name') or c['ticker']}")
        elif c["type"] == "market_changed":
            parts = [f"{f} {mv['from']}→{mv['to']}" for f, mv in c["fields"].items()]
            lines.append(f"- {c.get('name') or c['ticker']}: " + "; ".join(parts))
    lines += ["", "---", ""]
    new_block = "\n".join(lines)

    header = (
        "# Change log\n\n"
        f"Tracking {curr['label']} — [{curr['event'].get('title') or curr['event_ticker']}]"
        f"({PAGE_URL})\n\nNewest first. Generated by `scraper.py`.\n\n"
    )
    existing = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        first_entry = content.find("### ")
        if first_entry != -1:
            existing = content[first_entry:]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + new_block + existing)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_event(ev: dict) -> dict | None:
    """Scrape one tier. Returns a summary dict, or None if the event is
    unavailable (e.g. a tier not offered for this race)."""
    try:
        raw = fetch_event(ev["ticker"])
    except Exception as e:  # noqa: BLE001 - skip a missing/failed tier, keep the rest
        print(f"skip {ev['key']} ({ev['ticker']}): {e}", file=sys.stderr)
        return None

    curr = normalize(raw, ev)
    base = os.path.join(DATA_DIR, ev["key"])
    prev = load_previous(os.path.join(base, "snapshot.json"))
    changes = diff_snapshots(prev, curr)

    if prev is not None and not changes:
        print(f"{ev['key']}: no changes.", file=sys.stderr)
    else:
        write_outputs(base, raw, curr, changes)
        print(f"{ev['key']}: {curr['market_count']} markets, {len(changes)} change(s).",
              file=sys.stderr)
    return {"key": ev["key"], "label": ev["label"], "odds_label": ev["odds_label"],
            "event_ticker": ev["ticker"]}


def fetch_trades(ticker: str, limit: int = TRADES_PER_MARKET) -> list:
    url = f"{API_BASE}/markets/trades?ticker={ticker}&limit={limit}"
    return _get_json(url).get("trades", []) or []


def build_activity() -> None:
    """Merge recent trades across every tracked market into data/activity.json.

    Kalshi's trades endpoint filters by a single market ticker only, so we poll
    each market. This file is a live feed — regenerated each run and published,
    but git-ignored so it doesn't churn history."""
    meta = {}  # market ticker -> (tier label, driver name)
    for ev in EVENTS:
        snap = load_previous(os.path.join(DATA_DIR, ev["key"], "snapshot.json"))
        if not snap:
            continue
        for tk, m in snap.get("markets", {}).items():
            meta[tk] = (ev["label"], m.get("name"))

    trades = {}
    for tk, (label, driver) in meta.items():
        try:
            for t in fetch_trades(tk):
                tid = t.get("trade_id")
                if not tid:
                    continue
                trades[tid] = {
                    "trade_id": tid,
                    "tier": label,
                    "driver": driver,
                    "ticker": tk,
                    "side": t.get("taker_side"),
                    "count": int(round(_to_float(t.get("count_fp")) or 0)),
                    "yes_price": _dollars_to_cents(t.get("yes_price_dollars")),
                    "no_price": _dollars_to_cents(t.get("no_price_dollars")),
                    "created_time": t.get("created_time"),
                }
        except Exception as e:  # noqa: BLE001 - skip a market, keep the feed
            print(f"trades failed for {tk}: {e}", file=sys.stderr)

    ordered = sorted(trades.values(), key=lambda x: x.get("created_time") or "",
                     reverse=True)[:ACTIVITY_MAX]
    out = {"updated_at": datetime.now(timezone.utc).isoformat(),
           "count": len(ordered), "trades": ordered}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ACTIVITY_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"activity: {len(ordered)} recent trades", file=sys.stderr)


def build_index() -> None:
    """Write data/index.json describing every tracked tier, read from each
    tier's on-disk snapshot (so it only changes when a snapshot changes)."""
    markets = []
    race_title = None
    for ev in EVENTS:
        snap = load_previous(os.path.join(DATA_DIR, ev["key"], "snapshot.json"))
        if not snap:
            continue
        markets.append({
            "key": ev["key"], "label": ev["label"], "odds_label": ev["odds_label"],
            "event_ticker": ev["ticker"],
            "title": snap.get("event", {}).get("title"),
            "market_count": snap.get("market_count"),
            "scraped_at": snap.get("scraped_at"),
        })
        race_title = race_title or (snap.get("event", {}) or {}).get("sub_title")

    index = {"race_title": race_title or "NASCAR Race",
             "source_url": PAGE_URL, "markets": markets}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")


def main() -> int:
    any_ok = False
    for ev in EVENTS:
        if process_event(ev) is not None:
            any_ok = True
    if not any_ok:
        print("No events could be scraped.", file=sys.stderr)
        return 1
    build_index()
    try:
        build_activity()
    except Exception as e:  # noqa: BLE001 - activity is best-effort
        print(f"activity build failed: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
