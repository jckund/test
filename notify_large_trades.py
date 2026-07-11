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


def activity_trades():
    subprocess.run(["git", "-C", REPO, "fetch", "-q", "origin", BRANCH],
                   capture_output=True)
    r = subprocess.run(["git", "-C", REPO, "show", f"origin/{BRANCH}:{ACT_PATH}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return []
    try:
        return json.loads(r.stdout).get("trades", []) or []
    except json.JSONDecodeError:
        return []


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


def main():
    seed = "--seed" in sys.argv  # record current qualifiers without printing
    seen = load_seen()
    fresh = []
    for t in activity_trades():
        tid = t.get("trade_id")
        if not tid or tid in seen:
            continue
        v = value_usd(t)
        if v is None or v <= THRESHOLD:
            continue
        seen.add(tid)
        fresh.append((v, t))
    if not fresh:
        return
    save_seen([t.get("trade_id") for _, t in fresh])
    if seed:
        print(f"seeded {len(fresh)} existing trade(s) over ${THRESHOLD:,.0f}",
              file=sys.stderr)
        return
    fresh.sort(key=lambda x: x[1].get("created_time") or "")
    for v, t in fresh:
        price = t.get("yes_price") if t.get("side") == "yes" else t.get("no_price")
        side = (t.get("side") or "").upper()
        print(f"${v:,.2f} — {t.get('driver') or t.get('ticker')} ({t.get('tier')}) "
              f"{t.get('count')} @ {price}¢ {side} [{t.get('created_time')}]")


if __name__ == "__main__":
    main()
