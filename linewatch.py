#!/usr/bin/env python3
"""Kalshi golf line-move watch — runs in CI, wakes a Claude session only on a move.

Companion to ``alerts.py`` (which watches large *trades*). This module watches
*prices*: after each scrape it compares every tracked market's YES price
(``yes_ask``, the cost in cents to buy Yes) against a committed baseline and
raises an alert for any market whose YES moved at least ``THRESH`` cents/pp since
the last check.

Why this lives in CI: GitHub-hosted runners have unrestricted egress (they can
reach kalshi.com) and public-repo Actions minutes are free, so polling here costs
nothing. On a real move we POST a comment to the watch PR (``WATCH_PR_NUMBER``);
that comment's webhook wakes the subscribed Claude session, which pushes the user.
No move → no comment → the session stays asleep. That is the whole point: the
expensive session wake happens only when something actually moved.

State is the committed baseline ``data/theopen/watch_baseline.json`` (the CI runner
is stateless between runs, so the repo is the memory). The per-market YES baseline
is refreshed every run so reported moves are "since last check".

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

TIERS = ["winner", "top5", "top10", "top20"]
TIER_LABEL = {"winner": "Win", "top5": "Top 5", "top10": "Top 10", "top20": "Top 20"}
DATA_DIR = "data/theopen"
BASELINE = f"{DATA_DIR}/watch_baseline.json"
WATCH_MD = f"{DATA_DIR}/WATCH.md"

THRESH = float(os.environ.get("WATCH_THRESH_PP", "3"))


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
    if not cur:
        print("linewatch: no snapshots found; nothing to do.")
        return 0
    print(f"linewatch: scraped={scraped} leader_win_yes={leader:.0f}c thresh={THRESH:.0f}pp")

    first_run = not os.path.exists(BASELINE)
    if first_run:
        base = {}
    else:
        with open(BASELINE) as fh:
            saved = json.load(fh)
        base = saved.get("yes", {})

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

    # --- persist baseline (YES refreshed every run so moves are "since last check") ---
    with open(BASELINE, "w") as fh:
        json.dump(
            {
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scraped_at": scraped,
                "yes": cur,
            },
            fh,
            indent=2,
        )

    if first_run:
        print("linewatch: baseline established (first run); no alert.")
        return 0

    if not moves:
        print("linewatch: no moves >= %.0fpp since last check." % THRESH)
        return 0

    # --- build alert text ---
    lines = []
    if moves:
        top = moves[:10]
        extra = len(moves) - len(top)
        parts = [
            f"- **{name}** {tk}: {b:.0f}c -> {c:.0f}c ({american(c)}, {d:+.0f}pp)"
            for _, d, tk, name, b, c in top
        ]
        lines.append("**Kalshi YES moves >= %.0fpp (since last check):**" % THRESH)
        lines.extend(parts)
        if extra > 0:
            lines.append(f"- (+{extra} more)")
    lines.append(f"\n_leader win YES {leader:.0f}c · scraped {scraped}_")
    body = "\n".join(lines)

    header = f"### 📊 Kalshi line move — {scraped}"
    print(body)
    write_summary(header + "\n\n" + body)
    prepend_md(header, body)
    print(post_pr_comment(header + "\n\n" + body))
    print(post_webhook(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
