#!/usr/bin/env python3
"""Kalshi Cup line-move watch — runs in CI, wakes a Claude session only on a move.

Companion to ``alerts.py`` (which watches large *trades*). This module watches
*prices*: after each scrape it compares every Cup market's YES price (``yes_ask``,
the cost in cents to buy Yes) against a committed baseline and raises an alert for
any market whose YES moved at least ``THRESH`` cents/pp since the last check. It
also carries a fixed-anchor trip-wire on Austin Cindric (Win / Top 3): if his YES
rises at least ``CIND_THRESH`` pp above the anchor — i.e. the market shortens him
toward Bookmaker/Prime's number — that fires too.

Why this lives in CI: GitHub-hosted runners have unrestricted egress (they can
reach kalshi.com) and public-repo Actions minutes are free, so polling here costs
nothing. On a real move we POST a comment to the watch PR (``WATCH_PR_NUMBER``);
that comment's webhook wakes the subscribed Claude session, which pushes the user.
No move → no comment → the session stays asleep. That is the whole point: the
expensive session wake happens only when something actually moved.

State is the committed baseline ``data/cup/watch_baseline.json`` (the CI runner is
stateless between runs, so the repo is the memory). The Cindric anchor is written
once and never rewritten; the per-market YES baseline is refreshed every run so
reported moves are "since last check", matching the old in-session watch.

Environment:
  WATCH_THRESH_PP    move threshold in pp (default 3)
  WATCH_PR_NUMBER    issue/PR number to comment on (the CI->session bridge)
  GITHUB_TOKEN       token used to post the comment (provided by Actions)
  GITHUB_REPOSITORY  "owner/repo" (provided by Actions)
  ALERT_WEBHOOK_URL  optional Slack/Discord/generic webhook (shared with alerts.py)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

TIERS = ["winner", "top3", "top5", "top10"]
TIER_LABEL = {"winner": "Win", "top3": "Top 3", "top5": "Top 5", "top10": "Top 10"}
DATA_DIR = "data/cup"
BASELINE = f"{DATA_DIR}/watch_baseline.json"
WATCH_MD = f"{DATA_DIR}/WATCH.md"

THRESH = float(os.environ.get("WATCH_THRESH_PP", "3"))
# Above this winner-YES, the race is effectively decided/settled (one driver
# pinned near 100c). Between race weekends the last race sits here until Kalshi
# rolls to the next event, so while the scraper is unpaused-but-idle we stay
# silent (no line-move/trip-wire email) unless a NEW race event is detected.
SETTLED_YES = float(os.environ.get("WATCH_SETTLED_YES_PP", "98"))
CIND_NAME = "Austin Cindric"
CIND_THRESH = 2.0
# Fixed anchor for the Cindric trip-wire (established from the in-session watch).
CIND_ANCHOR = {"winner": 6, "top3": 16}
# Bookmaker/Prime raw-implied reference (context only): Win +800 ~ 11c, Top3 +200 ~ 33c.
CIND_TGT = {"winner": 11, "top3": 33}


def yesc(m: dict):
    """YES price in cents (cost to buy Yes): yes_ask, then last_price, then yes_bid."""
    for k in ("yes_ask", "last_price", "yes_bid"):
        v = m.get(k)
        if isinstance(v, (int, float)) and 0 < v < 100:
            return float(v)
    return None


def american(c):
    """Rough American odds from a cents price, for readability in the alert."""
    if c is None:
        return "-"
    p = c / 100.0
    if p <= 0 or p >= 1:
        return "-"
    return ("-%d" % round(100 * p / (1 - p))) if p >= 0.5 else ("+%d" % round(100 * (1 - p) / p))


def load_snapshot(tier: str):
    try:
        with open(f"{DATA_DIR}/{tier}/snapshot.json") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_current():
    cur, scraped, leader = {}, None, 0.0
    for tk in TIERS:
        s = load_snapshot(tk)
        if not s:
            continue
        scraped = scraped or s.get("scraped_at")
        for m in s.get("markets", {}).values():
            c = yesc(m)
            cur[f"{tk}|{m['name']}"] = c
            if tk == "winner" and c is not None:
                leader = max(leader, c)
    return cur, scraped, leader


def read_event():
    """Canonical race identity from the winner snapshot.

    Returns (event_ticker, race_name, market_count). The winner tier's
    ``event_ticker`` (e.g. ``KXNASCARRACE-COKZS26``) uniquely identifies the
    race; when Kalshi rolls to the next week's race it changes wholesale, which
    is how we detect a *new race event* (as opposed to a price move within the
    same race). ``race_name`` is the human-readable subtitle for the alert.
    """
    s = load_snapshot("winner")
    if not s:
        return None, None, 0
    ev = s.get("event") or {}
    name = ev.get("sub_title") or ev.get("title")
    count = s.get("market_count") or len(s.get("markets", {}))
    return s.get("event_ticker"), name, count


def post_pr_comment(body: str) -> str:
    pr = os.environ.get("WATCH_PR_NUMBER", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not (pr and token and repo):
        return "pr-comment skipped (WATCH_PR_NUMBER / GITHUB_TOKEN / GITHUB_REPOSITORY unset)"
    url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments"
    data = json.dumps({"body": body}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return f"pr-comment posted ({resp.status})"
    except urllib.error.HTTPError as e:
        return f"pr-comment failed: HTTP {e.code} {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return f"pr-comment failed: {e}"


def post_webhook(body: str) -> str:
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return "webhook skipped (ALERT_WEBHOOK_URL unset)"
    payload = json.dumps({"text": body, "content": body}).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return f"webhook posted ({resp.status})"
    except Exception as e:  # noqa: BLE001
        return f"webhook failed: {e}"


def write_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        try:
            with open(path, "a") as fh:
                fh.write(text + "\n")
        except OSError:
            pass


def prepend_md(header: str, body: str) -> None:
    old = ""
    if os.path.exists(WATCH_MD):
        try:
            with open(WATCH_MD) as fh:
                old = fh.read()
        except OSError:
            old = ""
    with open(WATCH_MD, "w") as fh:
        fh.write(f"{header}\n\n{body}\n\n---\n\n{old}")


def main() -> int:
    cur, scraped, leader = read_current()
    event_ticker, race_name, market_count = read_event()
    if not cur:
        print("linewatch: no snapshots found; nothing to do.")
        return 0
    print(f"linewatch: scraped={scraped} leader_win_yes={leader:.0f}c thresh={THRESH:.0f}pp "
          f"event={event_ticker}")

    first_run = not os.path.exists(BASELINE)
    if first_run:
        base = {}
        anchor = dict(CIND_ANCHOR)
        base_event = None
    else:
        with open(BASELINE) as fh:
            saved = json.load(fh)
        base = saved.get("yes", {})
        anchor = saved.get("cindric_anchor", dict(CIND_ANCHOR))
        base_event = saved.get("event_ticker")

    # --- detect per-market moves since last check ---
    moves = []
    for key, c in cur.items():
        b = base.get(key)
        if b is None or c is None:
            continue
        d = c - b
        if abs(d) >= THRESH:
            tk, name = key.split("|", 1)
            moves.append((abs(d), d, TIER_LABEL[tk], name, b, c))
    moves.sort(reverse=True)

    # --- Cindric fixed-anchor trip-wire ---
    cind_alerts = []
    for t in ("winner", "top3"):
        a = anchor.get(t)
        c = cur.get(f"{t}|{CIND_NAME}")
        if a is None or c is None:
            continue
        if c - a >= CIND_THRESH:
            cind_alerts.append(
                f"Cindric {TIER_LABEL[t]} {a:.0f}c->{c:.0f}c (+{c - a:.0f}pp toward "
                f"Bookmaker ~{CIND_TGT[t]}c, now {american(c)})"
            )

    # --- detect a new race event (Kalshi rolled to next week's race) ---
    # A change in the winner-tier event_ticker means the whole board is a new
    # race, not a price move. When this fires the per-market diff above is empty
    # (no ticker/name carries over), so this is the sole, clean signal.
    new_race = bool(event_ticker and base_event and event_ticker != base_event)

    # --- persist baseline (YES + event refreshed every run; anchor fixed forever) ---
    with open(BASELINE, "w") as fh:
        json.dump(
            {
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scraped_at": scraped,
                "event_ticker": event_ticker,
                "race_name": race_name,
                "yes": cur,
                "cindric_anchor": anchor,
            },
            fh,
            indent=2,
        )

    if first_run:
        print("linewatch: baseline established (first run); no alert.")
        return 0

    # No live race to alert on: the winner market is settled (a driver pinned
    # near 100c) and this isn't a new-race flip. Stay silent so an unpaused-but-
    # idle scraper between weekends doesn't email line-move noise off a dead
    # board. A genuine new race (new_race) always alerts regardless.
    if leader >= SETTLED_YES and not new_race:
        print("linewatch: winner settled (leader %.0fc >= %.0f) and no new race; "
              "staying silent." % (leader, SETTLED_YES))
        return 0

    if not moves and not cind_alerts and not new_race:
        print("linewatch: no moves >= %.0fpp since last check." % THRESH)
        return 0

    # --- build alert text ---
    lines = []
    if new_race:
        lines.append(
            f"🏁 **New Kalshi NASCAR race detected:** {race_name or event_ticker} "
            f"(`{event_ticker}`) — {market_count} driver markets. "
            f"Previous event `{base_event}`."
        )
    if moves:
        top = moves[:10]
        extra = len(moves) - len(top)
        parts = [
            f"- **{name}** {tk}: {b:.0f}c -> {c:.0f}c ({american(c)}, {d:+.0f}pp)"
            for _, d, tk, name, b, c in top
        ]
        lines.append("**Kalshi Cup YES moves >= %.0fpp (since last check):**" % THRESH)
        lines.extend(parts)
        if extra > 0:
            lines.append(f"- (+{extra} more)")
    if cind_alerts:
        lines.append("**TRIP-WIRE — Cindric:** " + " ; ".join(cind_alerts))
    lines.append(f"\n_leader win YES {leader:.0f}c · scraped {scraped}_")
    body = "\n".join(lines)

    if new_race:
        header = f"### 🏁 New Kalshi NASCAR race — {race_name or event_ticker}"
    else:
        header = f"### 📊 Kalshi line move — {scraped}"
    print(body)
    write_summary(header + "\n\n" + body)
    prepend_md(header, body)
    print(post_pr_comment(header + "\n\n" + body))
    print(post_webhook(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
