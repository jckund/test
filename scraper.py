#!/usr/bin/env python3
"""Scrape a Kalshi market event and track changes over time.

Target page:
  https://kalshi.com/markets/kxnascarrace/nascar-race/kxnascarrace-quas4aa26

The public website is protected by Cloudflare and cannot be scraped directly,
but Kalshi exposes the same data through its public, unauthenticated trade API.
This script reads the event and all of its nested markets from that API,
normalizes the fields we care about, and writes them to the ``data/`` folder.

Change tracking is done two ways:
  * ``data/snapshot.json`` always holds the latest normalized state. When run
    on a schedule and committed, git history becomes a full audit trail.
  * ``data/history.jsonl`` gets one appended record per run *in which something
    changed*, plus a compact list of exactly what changed.
  * ``data/CHANGES.md`` is a human-readable log of the most recent changes.

The script only touches files when the market state actually changes, so a
scheduled commit step can use ``git diff --quiet`` to avoid empty commits.

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

# Derived from the page URL's final path segment, upper-cased:
#   .../nascar-race/kxnascarrace-quas4aa26  ->  KXNASCARRACE-QUAS4AA26
EVENT_TICKER = os.environ.get("KALSHI_EVENT_TICKER", "KXNASCARRACE-QUAS4AA26")

PAGE_URL = (
    "https://kalshi.com/markets/kxnascarrace/nascar-race/"
    "kxnascarrace-quas4aa26"
)
API_BASE = "https://api.elections.kalshi.com/trade-api/v2"

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
RAW_PATH = os.path.join(DATA_DIR, "latest.json")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "snapshot.json")
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")
SERIES_PATH = os.path.join(DATA_DIR, "series.jsonl")
CHANGES_PATH = os.path.join(DATA_DIR, "CHANGES.md")

# Cap the price-series file so it stays small over a long-running event.
MAX_SERIES = 1000

# Per-market fields we compare between runs to detect a meaningful change.
TRACKED_FIELDS = [
    "status",
    "last_price",
    "yes_bid",
    "yes_ask",
    "no_bid",
    "no_ask",
    "volume",
    "open_interest",
]

USER_AGENT = "kalshi-nascar-tracker/1.0 (+https://github.com; scheduled scraper)"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _get_json(url: str, retries: int = 4) -> dict:
    """GET a URL and parse JSON, retrying with exponential backoff."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as err:
            last_err = err
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s
                print(f"  fetch failed ({err}); retrying in {wait}s", file=sys.stderr)
                time.sleep(wait)
    raise RuntimeError(f"failed to GET {url}: {last_err}")


def fetch_event() -> dict:
    """Fetch the event and all nested markets from the Kalshi API."""
    url = f"{API_BASE}/events/{EVENT_TICKER}?with_nested_markets=true"
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
    (e.g. ``last_price_dollars: "0.0100"``); older/other endpoints return
    integer cents directly (``last_price``). Support both."""
    v = m.get(base)
    if isinstance(v, (int, float)):
        return int(round(v))
    d = _to_float(m.get(base + "_dollars"))
    return None if d is None else int(round(d * 100))


def _count(m: dict, base: str):
    """Contract count. Newer schema uses fixed-point strings (``volume_fp``);
    older uses plain integers (``volume``)."""
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


def normalize(raw: dict) -> dict:
    """Reduce the raw API payload to the fields we track."""
    event = raw.get("event", {}) or {}
    markets = raw.get("markets") or event.get("markets") or []

    norm_markets = {}
    for m in markets:
        ticker = m.get("ticker")
        if not ticker:
            continue
        norm_markets[ticker] = {
            "ticker": ticker,
            # For NASCAR "which driver wins", the driver name lives here.
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
        "event_ticker": EVENT_TICKER,
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

def load_previous() -> dict | None:
    if not os.path.exists(SNAPSHOT_PATH):
        return None
    try:
        with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def diff_snapshots(prev: dict | None, curr: dict) -> list[dict]:
    """Return a list of change records describing what moved since last run."""
    changes: list[dict] = []
    curr_markets = curr.get("markets", {})

    if prev is None:
        changes.append({"type": "initial_snapshot", "market_count": len(curr_markets)})
        return changes

    prev_markets = prev.get("markets", {})

    for ticker, market in curr_markets.items():
        if ticker not in prev_markets:
            changes.append({
                "type": "market_added",
                "ticker": ticker,
                "name": market.get("name"),
            })
            continue
        old = prev_markets[ticker]
        field_changes = {}
        for field in TRACKED_FIELDS:
            if market.get(field) != old.get(field):
                field_changes[field] = {"from": old.get(field), "to": market.get(field)}
        if field_changes:
            changes.append({
                "type": "market_changed",
                "ticker": ticker,
                "name": market.get("name"),
                "fields": field_changes,
            })

    for ticker in prev_markets:
        if ticker not in curr_markets:
            changes.append({
                "type": "market_removed",
                "ticker": ticker,
                "name": prev_markets[ticker].get("name"),
            })

    return changes


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _cents(v) -> str:
    return f"{v}¢" if isinstance(v, (int, float)) else "—"


def write_outputs(raw: dict, curr: dict, changes: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    # Full raw payload (pretty) for reference / debugging.
    with open(RAW_PATH, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=2, sort_keys=True)
        fh.write("\n")

    # Normalized current state.
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as fh:
        json.dump(curr, fh, indent=2, sort_keys=True)
        fh.write("\n")

    # Append one compact history record per run with changes.
    record = {
        "scraped_at": curr["scraped_at"],
        "change_count": len(changes),
        "changes": changes,
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, separators=(",", ":")) + "\n")

    _append_series(curr)
    _write_changes_md(curr, changes)


def _append_series(curr: dict) -> None:
    """Append one aligned price point per change run for sparklines.

    Each line is ``{"t": <iso>, "p": {ticker: last_price, ...}}`` capturing
    every market's last price at that moment, so the dashboard can draw a
    per-driver trend line. Trimmed to the most recent MAX_SERIES points.
    """
    point = {
        "t": curr["scraped_at"],
        "p": {t: m.get("last_price") for t, m in curr["markets"].items()},
    }

    lines: list[str] = []
    if os.path.exists(SERIES_PATH):
        with open(SERIES_PATH, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    lines.append(json.dumps(point, separators=(",", ":")))
    lines = lines[-MAX_SERIES:]

    with open(SERIES_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _write_changes_md(curr: dict, changes: list[dict]) -> None:
    """Human-readable log: prepend the newest change block to CHANGES.md."""
    ts = curr["scraped_at"]
    lines = [f"### {ts}", ""]

    # Current standings table.
    markets = sorted(
        curr["markets"].values(),
        key=lambda m: (m.get("last_price") is None, -(m.get("last_price") or 0)),
    )
    lines.append("| Driver | Last | Yes bid/ask | Volume | OI |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for m in markets:
        lines.append(
            f"| {m.get('name') or m.get('ticker')} "
            f"| {_cents(m.get('last_price'))} "
            f"| {_cents(m.get('yes_bid'))} / {_cents(m.get('yes_ask'))} "
            f"| {m.get('volume') if m.get('volume') is not None else '—'} "
            f"| {m.get('open_interest') if m.get('open_interest') is not None else '—'} |"
        )
    lines.append("")

    # What changed this run.
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
            parts = []
            for field, mv in c["fields"].items():
                parts.append(f"{field} {mv['from']}→{mv['to']}")
            lines.append(f"- {c.get('name') or c['ticker']}: " + "; ".join(parts))
    lines.append("")
    lines.append("---")
    lines.append("")

    new_block = "\n".join(lines)

    header = (
        "# Change log\n\n"
        f"Tracking [{curr['event'].get('title') or EVENT_TICKER}]"
        f"({PAGE_URL})\n\n"
        "Newest first. Generated by `scraper.py`.\n\n"
    )

    existing = ""
    if os.path.exists(CHANGES_PATH):
        with open(CHANGES_PATH, encoding="utf-8") as fh:
            content = fh.read()
        marker = "---\n\n"  # split off the old header
        idx = content.find(marker)
        # Preserve everything after the intro header of the previous file.
        first_entry = content.find("### ")
        if first_entry != -1:
            existing = content[first_entry:]

    with open(CHANGES_PATH, "w", encoding="utf-8") as fh:
        fh.write(header + new_block + existing)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    raw = fetch_event()
    curr = normalize(raw)
    prev = load_previous()
    changes = diff_snapshots(prev, curr)

    if prev is not None and not changes:
        print("No changes since last run.", file=sys.stderr)
        # Still refresh latest.json + snapshot timestamp? No: keep files stable
        # so the commit step sees a clean tree and skips an empty commit.
        return 0

    write_outputs(raw, curr, changes)
    print(f"Wrote snapshot with {curr['market_count']} markets; "
          f"{len(changes)} change(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
