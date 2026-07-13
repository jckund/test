#!/usr/bin/env python3
"""Scrape Kalshi golf markets for one PGA Tour tournament.

Unlike NASCAR (where every tier lives under one winner series), Kalshi files
each golf tier under its **own** series, all sharing the tournament's event
suffix. For "2026 The Open Championship" (code ``THOC26``) the tiers we track:

  Winner    KXPGATOUR      -> KXPGATOUR-THOC26      (The Open Championship Winner)
  Top 5     KXPGATOP5      -> KXPGATOP5-THOC26      (Top 5 Finishers)
  Top 10    KXPGATOP10     -> KXPGATOP10-THOC26     (Top 10 Finishers)
  Make Cut  KXPGAMAKECUT   -> KXPGAMAKECUT-THOC26   (To Make the Cut)

Each event nests one market per golfer. We normalize the fields we care about
(last price, yes/no bid & ask, volume, open interest, status) and write one
folder per tier under ``data/golf/``:

  data/golf/index.json               — tier list + tournament title (dashboard)
  data/golf/<tier>/snapshot.json      — normalized current state
  data/golf/<tier>/latest.json        — full raw API response
  data/golf/<tier>/history.jsonl      — append-only change log (compact diff)
  data/golf/<tier>/series.jsonl       — aligned implied-price series (sparklines)
  data/golf/<tier>/CHANGES.md         — human-readable change log + standings
  data/golf/activity.json             — recent trades merged across tiers

Only writes a tier when something actually changed since the last snapshot, so
git history is the change log. Point it at another tournament with GOLF_CODE
(and, if the tiers differ, GOLF_TIERS). Python 3 stdlib only.

Run manually:  python3 golf_scraper.py
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

# Tournament event suffix. THOC26 == "2026 The Open Championship".
TOURNAMENT_CODE = os.environ.get("GOLF_CODE", "THOC26")

# The public Kalshi page the user watches (the winner market). Used as the
# source link in the dashboard/change logs.
PAGE_URL = os.environ.get(
    "GOLF_PAGE_URL",
    f"https://kalshi.com/markets/kxpgatour/pga-tour/kxpgatour-{TOURNAMENT_CODE.lower()}",
)

# (tier key, display label, odds-column label, Kalshi series ticker).
# Override with GOLF_TIERS as "key:Label:OddsLabel:SERIES,..." for another
# tournament whose series set differs.
DEFAULT_TIERS = [
    ("winner", "Winner", "Win", "KXPGATOUR"),
    ("top5", "Top 5", "Top 5", "KXPGATOP5"),
    ("top10", "Top 10", "Top 10", "KXPGATOP10"),
    ("makecut", "Make Cut", "Make Cut", "KXPGAMAKECUT"),
]


def _load_tiers():
    raw = os.environ.get("GOLF_TIERS")
    if not raw:
        return list(DEFAULT_TIERS)
    tiers = []
    for part in raw.split(","):
        bits = part.split(":")
        if len(bits) == 4:
            tiers.append(tuple(b.strip() for b in bits))
        else:
            print(f"ignoring malformed GOLF_TIERS entry: {part!r}", file=sys.stderr)
    return tiers or list(DEFAULT_TIERS)


TIERS = _load_tiers()

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data", "golf")
INDEX_PATH = os.path.join(DATA_DIR, "index.json")
ACTIVITY_PATH = os.path.join(DATA_DIR, "activity.json")

TRACKED_FIELDS = [
    "status", "last_price", "yes_bid", "yes_ask",
    "no_bid", "no_ask", "volume", "open_interest",
]
MAX_SERIES = 1000
ACTIVITY_MAX = 150
try:
    TRADES_PER_MARKET = max(1, int(os.environ.get("KALSHI_TRADES_PER_MARKET", "10")))
except ValueError:
    TRADES_PER_MARKET = 10

USER_AGENT = "kalshi-golf-tracker/1.0 (+https://github.com; scheduled scraper)"
# Kalshi rate-limits bursts (HTTP 429); a small pause between calls keeps us
# under the limit while scraping several tiers x ~165 golfers.
THROTTLE_S = 0.35


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _get_json(url: str, retries: int = 5) -> dict:
    last_err = None
    for attempt in range(retries):
        try:
            time.sleep(THROTTLE_S)
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
            last_err = err
            code = getattr(err, "code", None)
            # A 404 is a settled/withdrawn tier; don't waste retries on it.
            if code == 404:
                raise RuntimeError(f"not found: {url}") from err
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1) * (2 if code == 429 else 1)
                print(f"  fetch failed ({err}); retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"failed to GET {url}: {last_err}")


def fetch_event(ticker: str) -> dict:
    url = f"{API_BASE}/events/{ticker}?with_nested_markets=true"
    print(f"Fetching {url}", file=sys.stderr)
    return _get_json(url)


def fetch_trades(ticker: str, limit: int = TRADES_PER_MARKET) -> list:
    url = f"{API_BASE}/markets/trades?ticker={ticker}&limit={limit}"
    return _get_json(url).get("trades", []) or []


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _price_cents(m: dict, base: str):
    v = m.get(base)
    if isinstance(v, (int, float)):
        return int(round(v))
    d = _to_float(m.get(base + "_dollars"))
    return None if d is None else int(round(d * 100))


def _count(m: dict, base: str):
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


def normalize(raw: dict, tier: dict) -> dict:
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
        "tier": tier["key"],
        "label": tier["label"],
        "odds_label": tier["odds_label"],
        "event_ticker": tier["ticker"],
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
    page_url = curr.get("source_url", "")
    lines = [f"### {ts}", ""]

    markets = sorted(curr["markets"].values(),
                     key=lambda m: (implied_yes_cents(m) is None, -(implied_yes_cents(m) or 0)))
    lines.append("| Golfer | Implied | Last | Yes bid/ask | Volume | OI |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for m in markets:
        lines.append(
            f"| {m.get('name') or m.get('ticker')} | {_cents(implied_yes_cents(m))} "
            f"| {_cents(m.get('last_price'))} "
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
        f"({page_url})\n\nNewest first. Generated by `golf_scraper.py`.\n\n"
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
# Per-tier processing
# ---------------------------------------------------------------------------

def process_tier(tier: dict) -> dict | None:
    """Scrape one tier. Returns a summary + tournament title, or None if
    unavailable (e.g. a tier Kalshi hasn't posted for this tournament)."""
    try:
        raw = fetch_event(tier["ticker"])
    except Exception as e:  # noqa: BLE001 - skip a missing tier, keep the rest
        print(f"skip {tier['key']} ({tier['ticker']}): {e}", file=sys.stderr)
        return None

    curr = normalize(raw, tier)
    if not curr["market_count"]:
        print(f"skip {tier['key']} ({tier['ticker']}): no markets", file=sys.stderr)
        return None

    base = os.path.join(DATA_DIR, tier["key"])
    prev = load_previous(os.path.join(base, "snapshot.json"))
    changes = diff_snapshots(prev, curr)

    if prev is not None and not changes:
        print(f"{tier['key']}: no changes.", file=sys.stderr)
    else:
        write_outputs(base, raw, curr, changes)
        print(f"{tier['key']}: {curr['market_count']} markets, {len(changes)} change(s).",
              file=sys.stderr)

    return {
        "key": tier["key"], "label": tier["label"], "odds_label": tier["odds_label"],
        "event_ticker": tier["ticker"], "market_count": curr["market_count"],
        "scraped_at": curr["scraped_at"],
        "event_title": curr["event"].get("title"),
        "tournament": curr["event"].get("sub_title"),
    }


def build_activity(scraped: list) -> None:
    """Merge recent trades across all tiers into data/golf/activity.json."""
    trades = {}
    for s in scraped:
        base = os.path.join(DATA_DIR, s["key"])
        snap = load_previous(os.path.join(base, "snapshot.json"))
        if not snap:
            continue
        for tk, m in snap.get("markets", {}).items():
            try:
                for t in fetch_trades(tk):
                    tid = t.get("trade_id")
                    if not tid:
                        continue
                    trades[tid] = {
                        "trade_id": tid, "tier": s["label"], "golfer": m.get("name"),
                        "ticker": tk, "side": t.get("taker_side"),
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


def build_index(scraped: list) -> None:
    tournament = next((s.get("tournament") for s in scraped if s.get("tournament")), None)
    index = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tournament": tournament or TOURNAMENT_CODE,
        "tournament_code": TOURNAMENT_CODE,
        "source_url": PAGE_URL,
        "tiers": [{
            "key": s["key"], "label": s["label"], "odds_label": s["odds_label"],
            "event_ticker": s["event_ticker"], "title": s["event_title"],
            "market_count": s["market_count"], "scraped_at": s["scraped_at"],
        } for s in scraped],
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")


def main() -> int:
    tiers = [{"key": k, "label": lbl, "odds_label": odl,
              "ticker": f"{series}-{TOURNAMENT_CODE}"}
             for (k, lbl, odl, series) in TIERS]
    print(f"Scraping {len(tiers)} golf tier(s) for {TOURNAMENT_CODE}: "
          + ", ".join(t["ticker"] for t in tiers), file=sys.stderr)

    scraped = [s for s in (process_tier(t) for t in tiers) if s]
    if not scraped:
        print("No golf tiers could be scraped.", file=sys.stderr)
        return 1

    build_index(scraped)
    try:
        build_activity(scraped)
    except Exception as e:  # noqa: BLE001 - activity is best-effort
        print(f"activity build failed: {e}", file=sys.stderr)

    print(f"Done: {len(scraped)} tier(s) scraped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
