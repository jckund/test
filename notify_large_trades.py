#!/usr/bin/env python3
"""Print NASCAR Cup trades over a dollar threshold that haven't been reported yet.

Companion to the scheduled tracker. It reads the committed
``data/cup/activity.json`` (refreshed every ~15 min by the GitHub Actions
scraper on the tracker branch) and prints one compact line per NEW trade whose
value exceeds the threshold. A scheduling loop (a Claude "Routine" /
``send_later`` self-check) runs this and turns each printed line into a
notification.

Trade value = ``count * taker_price / 100`` — the cash the aggressor put in
(a YES taker pays the yes price, a NO taker pays the no price).

Dedup: reported trade IDs are remembered in a git-ignored state file so a trade
is printed once. Dedup is purely by trade ID — every unreported over-threshold
trade in the feed is surfaced regardless of age. (There is deliberately NO
"only recent trades" cutoff: the committed feed routinely holds trades over an
hour old, and a time cutoff was silently dropping real alerts. If the state
file is ever lost, the worst case is re-sending the current window's handful of
over-threshold trades once — far better than missing any.)

Env overrides:
  ALERT_MIN_USD    threshold in dollars (default 100)
  TRACKER_BRANCH   branch the scraper commits activity.json to
"""
import json
import os
import subprocess
import sys

DEFAULT_BRANCH = "claude/nascar-page-scraper-mwi55a"
ACT_PATH = "data/cup/activity.json"
# Authoritative, comprehensive alert log written by the scheduled scraper
# (alerts.py). Present once the alerting change is merged; preferred over the
# sampled activity feed because it can't miss a trade.
ALERTS_PATH = "data/cup/alerts.jsonl"
THRESHOLD = float(os.environ.get("ALERT_MIN_USD", "100"))


def repo_root():
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run(["git", "-C", here, "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else here


REPO = repo_root()
BRANCH = os.environ.get("TRACKER_BRANCH", DEFAULT_BRANCH)
# Git-ignored, repo-local so it survives within a checkout without being committed.
STATE = os.path.join(REPO, ".large_trade_seen.txt")


def load_seen():
    if not os.path.exists(STATE):
        return set()
    return {l.strip() for l in open(STATE) if l.strip()}


def save_seen(ids):
    with open(STATE, "a") as fh:
        for i in ids:
            fh.write(i + "\n")


def _git_show(path):
    subprocess.run(["git", "-C", REPO, "fetch", "-q", "origin", BRANCH],
                   capture_output=True)
    r = subprocess.run(["git", "-C", REPO, "show", f"origin/{BRANCH}:{path}"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _yes_implied_cents(price, side):
    """The market's implied YES (driver's-outcome) price in cents for a trade,
    regardless of which side the taker hit."""
    if not isinstance(price, (int, float)):
        return None
    return 100 - price if side == "no" else price


def american_odds(yes_cents):
    """American (moneyline) odds for the driver's outcome from its implied
    cents price, e.g. 6¢ -> '+1567', 60¢ -> '-150'. None if uncomputable."""
    if not isinstance(yes_cents, (int, float)) or yes_cents <= 0 or yes_cents >= 100:
        return None
    p = yes_cents / 100.0
    return f"+{round((1 - p) / p * 100)}" if p <= 0.5 else f"-{round(p / (1 - p) * 100)}"


def value_usd(t):
    side = t.get("side")
    if side == "yes":
        price = t.get("yes_price")
    elif side == "no":
        price = t.get("no_price")
    else:
        price = t.get("yes_price")
    if not isinstance(price, (int, float)):
        price = t.get("yes_price")
    count = t.get("count")
    if not isinstance(count, (int, float)) or not isinstance(price, (int, float)):
        return None
    return round(count * price / 100.0, 2)


def _candidates():
    """Yield (trade_id, value_usd, display_dict) for every over-threshold trade.

    Prefer the authoritative alerts.jsonl (comprehensive, already filtered by the
    scraper); fall back to computing from the sampled activity.json when the log
    isn't present yet (i.e. before the alerting change is merged)."""
    log = _git_show(ALERTS_PATH)
    if log and log.strip():
        for line in log.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                a = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid, v = a.get("trade_id"), a.get("value_usd")
            if tid and isinstance(v, (int, float)) and v > THRESHOLD:
                yield tid, round(v, 2), {
                    "driver": a.get("driver") or a.get("ticker"), "tier": a.get("tier"),
                    "count": a.get("count"), "price": a.get("price_cents"),
                    "side": a.get("side"), "created_time": a.get("created_time")}
        return
    raw = _git_show(ACT_PATH)
    if not raw:
        return
    try:
        trades = json.loads(raw).get("trades", []) or []
    except json.JSONDecodeError:
        return
    for t in trades:
        tid, v = t.get("trade_id"), value_usd(t)
        if tid and v is not None and v > THRESHOLD:
            price = t.get("yes_price") if t.get("side") == "yes" else t.get("no_price")
            yield tid, v, {
                "driver": t.get("driver") or t.get("ticker"), "tier": t.get("tier"),
                "count": t.get("count"), "price": price,
                "side": t.get("side"), "created_time": t.get("created_time")}


def main():
    seed = "--seed" in sys.argv  # record current qualifiers without printing
    seen = load_seen()
    fresh = []
    for tid, v, disp in _candidates():
        if tid in seen:
            continue
        seen.add(tid)
        fresh.append((tid, v, disp))
    if not fresh:
        return
    save_seen([tid for tid, _, _ in fresh])
    if seed:
        print(f"seeded {len(fresh)} existing trade(s) over ${THRESHOLD:,.0f}",
              file=sys.stderr)
        return
    fresh.sort(key=lambda x: x[2].get("created_time") or "")
    for _tid, v, d in fresh:
        side = (d.get("side") or "").upper()
        odds = american_odds(_yes_implied_cents(d.get("price"), d.get("side")))
        odds_s = f" [{odds}]" if odds else ""
        print(f"${v:,.2f} — {d.get('driver')} ({d.get('tier')}){odds_s} · "
              f"{d.get('count')} @ {d.get('price')}¢ {side} [{d.get('created_time')}]")


if __name__ == "__main__":
    main()
