#!/usr/bin/env python3
"""Large-trade alerting for the Kalshi NASCAR tracker.

The scraper already pulls recent trades per market (see ``build_activity`` in
``scraper.py``). This module takes that trade list for a series — by default the
**Cup** series, i.e. every NASCAR Cup driver market — and raises an alert for any
single trade whose dollar value exceeds a threshold (default ``$100``).

"Trade value" is the cash the aggressor (taker) put in::

    value = count * taker_price_cents / 100

so 500 contracts bought at 43¢ is a $215 trade. Kalshi quotes whole-cent prices
1–99; ``yes_price`` and ``no_price`` sum to 100. We charge the taker their own
side's price (a YES taker pays ``yes_price``, a NO taker pays ``no_price``),
falling back to the YES price when the side is unknown.

Each new alert is:

  * appended to ``data/<series>/alerts.jsonl`` — committed, so git history is a
    durable log **and** the dedup source. The scraper reruns every 15 min on a
    fresh CI runner with no local state, so the committed log is what stops a
    trade from firing twice. (``data/activity.json`` is git-ignored and can't
    serve this purpose.)
  * prepended to ``data/<series>/ALERTS.md`` — human-readable, newest first.
  * written to the GitHub Actions job summary when running in CI.
  * POSTed to ``ALERT_WEBHOOK_URL`` if set — a Slack/Discord/Telegram or generic
    JSON incoming webhook. This is the actual "notify me" push.

Environment:
  ALERT_MIN_USD      threshold in dollars (default 100)
  ALERT_WEBHOOK_URL  optional Slack/Discord-compatible incoming webhook URL
  ALERT_SERIES       comma-separated series keys to watch (default "cup")
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_MIN_USD = 100.0
# Above this many new alerts in a single run, post one summary to the webhook
# instead of a message per trade (avoids a flood on backfill / busy sessions).
WEBHOOK_INDIVIDUAL_LIMIT = 10
WEBHOOK_TIMEOUT_S = 15


# ---------------------------------------------------------------------------
# Configuration (env-driven)
# ---------------------------------------------------------------------------

def min_usd() -> float:
    """Alert threshold in dollars. A trade alerts when its value is strictly
    greater than this (default $100)."""
    try:
        return float(os.environ.get("ALERT_MIN_USD", DEFAULT_MIN_USD))
    except ValueError:
        return DEFAULT_MIN_USD


def watched_series() -> set:
    """Series keys to alert on. Default is the Cup series only."""
    raw = os.environ.get("ALERT_SERIES", "cup")
    return {s.strip() for s in raw.split(",") if s.strip()}


def webhook_url() -> str:
    return os.environ.get("ALERT_WEBHOOK_URL", "").strip()


# ---------------------------------------------------------------------------
# Trade valuation
# ---------------------------------------------------------------------------

def _taker_price_cents(trade: dict):
    """The per-contract price (cents) the taker paid for their side."""
    side = trade.get("side")
    if side == "yes":
        price = trade.get("yes_price")
    elif side == "no":
        price = trade.get("no_price")
    else:
        price = None
    if not isinstance(price, (int, float)):
        price = trade.get("yes_price")  # fall back to the YES price
    return price if isinstance(price, (int, float)) else None


def trade_value_usd(trade: dict):
    """Dollar value of a trade, or ``None`` if it can't be computed."""
    count = trade.get("count")
    price = _taker_price_cents(trade)
    if not isinstance(count, (int, float)) or count <= 0 or price is None:
        return None
    return round(count * price / 100.0, 2)


# ---------------------------------------------------------------------------
# Persistence / dedup
# ---------------------------------------------------------------------------

def _seen_ids(alerts_path: str) -> set:
    """Trade IDs already alerted, read from the committed alerts log."""
    seen = set()
    if not os.path.exists(alerts_path):
        return seen
    with open(alerts_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                tid = json.loads(line).get("trade_id")
            except json.JSONDecodeError:
                continue
            if tid:
                seen.add(tid)
    return seen


def _append_jsonl(path: str, records: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt_usd(v: float) -> str:
    return f"${v:,.2f}"


def _one_line(series_label: str, a: dict) -> str:
    """A single compact human line describing an alert (used by the webhook)."""
    side = (a.get("side") or "").upper()
    return (
        f"🏁 {_fmt_usd(a['value_usd'])} {series_label} trade — "
        f"{a.get('driver') or a['ticker']} ({a.get('tier')}) · "
        f"{a['count']} @ {a['price_cents']}¢ {side} · "
        f"{a.get('created_time')}"
    )


def _md_item(series_label: str, a: dict) -> str:
    side = (a.get("side") or "").upper()
    return (
        f"- **{_fmt_usd(a['value_usd'])}** — {a.get('driver') or a['ticker']} "
        f"({a.get('tier')}) · {a['count']} @ {a['price_cents']}¢ {side} · "
        f"`{a['ticker']}` · {a.get('created_time')}"
    )


def _prepend_md(path: str, series_label: str, new_alerts: list, threshold: float) -> None:
    """Rewrite ALERTS.md with the new alerts on top. Content lines are all
    ``- `` list items, so we can safely split header from history."""
    old_items = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            old_items = [ln for ln in fh.read().splitlines() if ln.startswith("- ")]
    newest_first = sorted(new_alerts, key=lambda a: a.get("created_time") or "", reverse=True)
    new_items = [_md_item(series_label, a) for a in newest_first]
    header = (
        f"# Large-trade alerts — {series_label}\n\n"
        f"Single trades over {_fmt_usd(threshold)} (taker cash = count × price). "
        f"Newest first. Generated by `alerts.py`.\n\n"
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + "\n".join(new_items + old_items) + "\n")


def _write_step_summary(series_label: str, new_alerts: list, threshold: float) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"### 🏁 {len(new_alerts)} {series_label} trade(s) over {_fmt_usd(threshold)}",
        "",
        "| Time (UTC) | Driver | Tier | Side | Count | Price | Value |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for a in sorted(new_alerts, key=lambda a: a.get("created_time") or "", reverse=True):
        lines.append(
            f"| {a.get('created_time')} | {a.get('driver') or a['ticker']} | {a.get('tier')} "
            f"| {(a.get('side') or '').upper()} | {a['count']} | {a['price_cents']}¢ "
            f"| {_fmt_usd(a['value_usd'])} |"
        )
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n\n")
    except OSError as e:  # never let summary writing break the run
        print(f"  step summary write failed: {e}", file=sys.stderr)


def _post_webhook(url: str, text: str) -> None:
    if not url:
        return
    payload = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=WEBHOOK_TIMEOUT_S) as resp:
            resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"  alert webhook failed: {e}", file=sys.stderr)


def _notify_webhook(url: str, series_label: str, new_alerts: list, threshold: float) -> None:
    if not url:
        return
    if len(new_alerts) <= WEBHOOK_INDIVIDUAL_LIMIT:
        for a in sorted(new_alerts, key=lambda a: a.get("created_time") or ""):
            _post_webhook(url, _one_line(series_label, a))
    else:  # too many at once — one summary message instead of a flood
        biggest = max(new_alerts, key=lambda a: a["value_usd"])
        _post_webhook(
            url,
            f"🏁 {len(new_alerts)} {series_label} trades over {_fmt_usd(threshold)} "
            f"this run (biggest {_fmt_usd(biggest['value_usd'])} on "
            f"{biggest.get('driver') or biggest['ticker']}). See ALERTS.md.",
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_alert(series_label: str, trade: dict, value: float) -> dict:
    return {
        "trade_id": trade.get("trade_id"),
        "series": series_label,
        "tier": trade.get("tier"),
        "driver": trade.get("driver"),
        "ticker": trade.get("ticker"),
        "side": trade.get("side"),
        "count": int(trade.get("count") or 0),
        "price_cents": _taker_price_cents(trade),
        "value_usd": value,
        "created_time": trade.get("created_time"),
        "alerted_at": datetime.now(timezone.utc).isoformat(),
    }


def process(series_dir: str, series_label: str, trades: list,
            *, threshold: float = None, url: str = None) -> list:
    """Alert on any not-yet-seen trade in ``trades`` worth more than the
    threshold. Returns the list of new alert records (possibly empty)."""
    threshold = min_usd() if threshold is None else threshold
    url = webhook_url() if url is None else url
    alerts_path = os.path.join(series_dir, "alerts.jsonl")
    seen = _seen_ids(alerts_path)

    new_alerts = []
    for t in trades or []:
        tid = t.get("trade_id")
        if not tid or tid in seen:
            continue
        value = trade_value_usd(t)
        if value is None or value <= threshold:
            continue
        seen.add(tid)  # guard against duplicate IDs within this batch
        new_alerts.append(build_alert(series_label, t, value))

    if not new_alerts:
        return []

    # Append chronologically so the committed log reads oldest→newest.
    new_alerts_chrono = sorted(new_alerts, key=lambda a: a.get("created_time") or "")
    _append_jsonl(alerts_path, new_alerts_chrono)
    _prepend_md(os.path.join(series_dir, "ALERTS.md"), series_label, new_alerts, threshold)
    _write_step_summary(series_label, new_alerts, threshold)
    _notify_webhook(url, series_label, new_alerts, threshold)
    return new_alerts
