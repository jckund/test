#!/usr/bin/env python3
"""Scrape Kalshi PGA golf markets for the tracked tournament(s).

Standalone companion to ``scraper.py`` (NASCAR). It writes its own data tree
and its own index (``data/golf.json``) so it NEVER touches the NASCAR
``data/series.json`` — the two trackers publish to the same GitHub Pages site
but are otherwise independent (NASCAR at ``/``, golf at ``/golf/``).

Kalshi files each golf finish tier under its own series, and the per-tournament
events all share one tournament-code suffix:

  Winner  KXPGATOUR-<code>     (series KXPGATOUR,   /pga-tour)
  Top 5   KXPGATOP5-<code>     (series KXPGATOP5,   /pga-top-5-finisher)
  Top 10  KXPGATOP10-<code>    (series KXPGATOP10,  /pga-top-10-finisher)
  Top 20  KXPGATOP20-<code>    (series KXPGATOP20,  /pga-top-20-finisher)

e.g. The Open Championship 2026 has code ``THOC26`` → KXPGATOUR-THOC26,
KXPGATOP5-THOC26, … Output tree per tournament:

  data/golf.json                        — list of tournaments (drives the tabs)
  data/<key>/index.json                 — that tournament's tier list
  data/<key>/<tier>/snapshot.json       — normalized current state
  data/<key>/<tier>/history.jsonl       — append-only change log
  data/<key>/<tier>/series.jsonl        — aligned price series for sparklines
  data/<key>/<tier>/CHANGES.md          — human-readable change log
  data/<key>/activity.json              — recent trades feed

The ``TOURNAMENTS`` config lists the tournament(s) to track by their Kalshi
code + a friendly tab label. To follow a different event, add/replace an entry
(the code is the suffix in the Kalshi URL, e.g. ``.../kxpgatour-thoc26`` →
``THOC26``).

Run manually with:  python3 golf_scraper.py
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

# (tier key, display label, odds-column label, Kalshi series ticker, URL path).
# Each golf finish tier is its OWN Kalshi series; the event ticker for a given
# tournament is "<series>-<code>". The URL path only builds the human-facing
# kalshi.com link shown on the dashboard.
TIERS = [
    ("winner", "Winner", "Win", "KXPGATOUR", "pga-tour"),
    ("top5", "Top 5", "Top 5", "KXPGATOP5", "pga-top-5-finisher"),
    ("top10", "Top 10", "Top 10", "KXPGATOP10", "pga-top-10-finisher"),
    ("top20", "Top 20", "Top 20", "KXPGATOP20", "pga-top-20-finisher"),
]
TIER_BY_KEY = {k: (k, lbl, odl, s, path) for (k, lbl, odl, s, path) in TIERS}

# Tournaments to track. `code` is the suffix in the Kalshi event ticker / URL
# (e.g. .../kxpgatour-thoc26 → "THOC26"). `key` names the data dir + dashboard
# tab; `title` is the heading shown on the page. `tiers` lists which finish
# tiers to scrape. Add an entry to follow another event.
TOURNAMENTS = [
    {"key": "theopen", "label": "The Open", "title": "The Open Championship",
     "code": "THOC26", "tiers": ["winner", "top5", "top10", "top20"]},
]

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
GOLF_INDEX_PATH = os.path.join(DATA_DIR, "golf.json")

try:
    TRADES_PER_MARKET = max(1, int(os.environ.get("KALSHI_TRADES_PER_MARKET", "10")))
except ValueError:
    TRADES_PER_MARKET = 10
ACTIVITY_MAX = 150

TRACKED_FIELDS = [
    "status", "last_price", "yes_bid", "yes_ask",
    "no_bid", "no_ask", "volume", "open_interest",
]
MAX_SERIES = 1000
USER_AGENT = "kalshi-golf-tracker/1.0 (+https://github.com; scheduled scraper)"
# Kalshi rate-limits bursts (HTTP 429); a small pause between calls keeps us
# under the limit while scraping several tiers x many players.
THROTTLE_S = 0.35


def tier_page_url(series_ticker: str, path: str, code: str) -> str:
    """Human-facing kalshi.com market page URL for a tier/tournament."""
    s = series_ticker.lower()
    return f"https://kalshi.com/markets/{s}/{path}/{s}-{code.lower()}"


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
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1) * (2 if code == 429 else 1)
                print(f"  fetch failed ({err}); retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"failed to GET {url}: {last_err}")


def fetch_event(ticker: str) -> dict:
    url = f"{API_BASE}/events/{ticker}?with_nested_markets=true"
    print(f"Fetching {url}", file=sys.stderr)
    return _get_json(url)


def resolve_tournaments() -> list:
    """Turn the TOURNAMENTS config into resolved dicts, each carrying a fully
    built list of per-tier events. The winner tier's page is the series link."""
    resolved = []
    for cfg in TOURNAMENTS:
        code = cfg["code"]
        events = []
        for tk in cfg["tiers"]:
            key, label, odds_label, series_ticker, path = TIER_BY_KEY[tk]
            events.append({
                "key": key, "label": label, "odds_label": odds_label,
                "ticker": f"{series_ticker}-{code}",
                "page_url": tier_page_url(series_ticker, path, code),
            })
        _, _, _, win_series, win_path = TIER_BY_KEY["winner"]
        resolved.append({
            "key": cfg["key"], "label": cfg["label"],
            "race_title": cfg["title"],
            "page_url": tier_page_url(win_series, win_path, code),
            "events": events,
        })
    return resolved


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
        "source_url": ev["page_url"],
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
                     key=lambda m: (m.get("last_price") is None, -(m.get("last_price") or 0)))
    lines.append("| Player | Last | Yes bid/ask | Volume | OI |")
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
# Per-tier / per-tournament processing
# ---------------------------------------------------------------------------

def process_event(ev: dict, series_dir: str) -> dict | None:
    """Scrape one tier of one tournament. Returns a summary, or None."""
    try:
        raw = fetch_event(ev["ticker"])
    except Exception as e:  # noqa: BLE001 - skip a missing/failed tier, keep the rest
        print(f"skip {ev['key']} ({ev['ticker']}): {e}", file=sys.stderr)
        return None

    curr = normalize(raw, ev)
    if not curr["market_count"]:
        print(f"skip {ev['key']} ({ev['ticker']}): no markets", file=sys.stderr)
        return None

    base = os.path.join(series_dir, ev["key"])
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


def _norm_trade(t: dict, label: str, player, ticker: str) -> dict | None:
    tid = t.get("trade_id")
    if not tid:
        return None
    return {
        "trade_id": tid, "tier": label, "driver": player, "ticker": ticker,
        "side": t.get("taker_side"),
        "count": int(round(_to_float(t.get("count_fp")) or 0)),
        "yes_price": _dollars_to_cents(t.get("yes_price_dollars")),
        "no_price": _dollars_to_cents(t.get("no_price_dollars")),
        "created_time": t.get("created_time"),
    }


def _series_market_meta(events: list, series_dir: str) -> dict:
    meta = {}
    for ev in events:
        snap = load_previous(os.path.join(series_dir, ev["key"], "snapshot.json"))
        if not snap:
            continue
        for tk, m in snap.get("markets", {}).items():
            meta[tk] = (ev["label"], m.get("name"))
    return meta


def build_activity(events: list, series_dir: str) -> list:
    """Merge recent trades across this tournament's markets into activity.json."""
    trades = {}
    for tk, (label, player) in _series_market_meta(events, series_dir).items():
        try:
            for t in fetch_trades(tk):
                norm = _norm_trade(t, label, player, tk)
                if norm:
                    trades[norm["trade_id"]] = norm
        except Exception as e:  # noqa: BLE001 - skip a market, keep the feed
            print(f"trades failed for {tk}: {e}", file=sys.stderr)

    ordered = sorted(trades.values(), key=lambda x: x.get("created_time") or "",
                     reverse=True)[:ACTIVITY_MAX]
    out = {"updated_at": datetime.now(timezone.utc).isoformat(),
           "count": len(ordered), "trades": ordered}
    os.makedirs(series_dir, exist_ok=True)
    with open(os.path.join(series_dir, "activity.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")
    print(f"activity: {len(ordered)} recent trades", file=sys.stderr)
    return ordered


def build_index(events: list, series_dir: str, race_title: str, page_url: str) -> None:
    """Write <key>/index.json describing the tournament's tracked tiers."""
    markets = []
    for ev in events:
        snap = load_previous(os.path.join(series_dir, ev["key"], "snapshot.json"))
        if not snap:
            continue
        markets.append({
            "key": ev["key"], "label": ev["label"], "odds_label": ev["odds_label"],
            "event_ticker": ev["ticker"],
            "title": snap.get("event", {}).get("title"),
            "market_count": snap.get("market_count"),
            "scraped_at": snap.get("scraped_at"),
        })
    index = {"race_title": race_title or "PGA Tournament", "source_url": page_url, "markets": markets}
    os.makedirs(series_dir, exist_ok=True)
    with open(os.path.join(series_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2)
        fh.write("\n")


def process_tournament(rs: dict) -> dict | None:
    """Scrape every available tier of one tournament into data/<key>/."""
    series_dir = os.path.join(DATA_DIR, rs["key"])
    events = rs["events"]

    scraped = [process_event(ev, series_dir) for ev in events]
    scraped = [s for s in scraped if s]
    if not scraped:
        print(f"tournament {rs['key']}: no tiers available; skipping.", file=sys.stderr)
        return None

    build_index(events, series_dir, rs["race_title"], rs["page_url"])
    try:
        build_activity(events, series_dir)
    except Exception as e:  # noqa: BLE001 - activity is best-effort
        print(f"activity build failed for {rs['key']}: {e}", file=sys.stderr)

    return {"key": rs["key"], "label": rs["label"], "race_title": rs["race_title"],
            "full": False, "source_url": rs["page_url"],
            "tiers": [s["key"] for s in scraped],
            "scraped_at": datetime.now(timezone.utc).isoformat()}


def write_golf_index(entries: list) -> None:
    """Write data/golf.json (the golf site's tournament list). Kept separate
    from NASCAR's data/series.json."""
    os.makedirs(DATA_DIR, exist_ok=True)
    out = {"updated_at": datetime.now(timezone.utc).isoformat(), "series": entries}
    with open(GOLF_INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
        fh.write("\n")


def main() -> int:
    resolved = resolve_tournaments()
    if not resolved:
        print("No tournaments configured.", file=sys.stderr)
        return 1
    print("Tracking tournament(s): " + ", ".join(
        f"{r['key']} ({r['race_title']})" for r in resolved), file=sys.stderr)

    entries = []
    for rs in resolved:
        summary = process_tournament(rs)
        if summary:
            entries.append(summary)
    if not entries:
        print("No tournaments could be scraped.", file=sys.stderr)
        return 1
    write_golf_index(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
