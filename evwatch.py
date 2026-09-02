#!/usr/bin/env python3
"""Alert on NEW high-EV Kalshi-vs-SG lines, across every scraped race.

This is the CI-side twin of the dashboard's "Kalshi vs SG" tab: for each series
that has both a Kalshi snapshot and an SG model book, it prices buying Kalshi
YES at its ask -- FEE-INCLUSIVE, matching index.html's netCost() and alerts.py's
net_american_odds() -- against SG's no-vig probability, and flags anything at or
above ``EV_ALERT_THRESH`` percent.

Only *new* lines alert. Dedup key is (series, tier, driver, yes_price_cents), so
a line that was already qualifying at the same price on the previous run stays
quiet; the same driver/market at a DIFFERENT price is a new line and alerts
again (the price moving is the point). State lives in
``data/ev_alert_state.json`` and is committed by the workflow like the other
watch state, so it survives across runs.

Channels (all optional, all no-ops when unset):
  PUSHOVER_TOKEN /   Pushover application token + user key. Phone push, and the
  PUSHOVER_USER      only channel here that does not depend on GitHub's email
                     delivery (which notifies the web inbox but was not mailing).
  ALERT_WEBHOOK_URL  Slack/Discord/ntfy/generic incoming webhook
                     (shared with alerts.py / linewatch.py). This is the hook a
                     Twilio/IFTTT/Zapier relay would use to fan out to SMS.
  WATCH_PR_NUMBER    issue/PR to comment on -- GitHub then emails its watchers,
                     which is the zero-setup email path.
  GITHUB_TOKEN       token used to post that comment (provided by Actions).

Env:
  EV_ALERT_THRESH    minimum EV percent to alert on (default 30)
  EV_ALERT_SERIES    comma-separated series keys (default: all in data/series.json)
  EV_ALERT_MENTION   GitHub @handle to mention in the PR comment. A mention is a
                     "Participating" notification, which GitHub emails by
                     default -- unlike a plain comment, which only reaches you if
                     you are subscribed to the thread. Empty = no mention.

Run manually with:  python3 evwatch.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Kalshi's standard trading fee: ceil(rate * contracts * p * (1-p)) charged on
# top of the execution price. Keep in lockstep with alerts.KALSHI_FEE_RATE and
# index.html's KALSHI_FEE_RATE.
KALSHI_FEE_RATE = 0.07

THRESH = float(os.environ.get("EV_ALERT_THRESH", "30"))
MENTION = os.environ.get("EV_ALERT_MENTION", "").strip()
SITE_URL = os.environ.get("EV_ALERT_URL", "").strip()
# Pushover caps message at 1024 chars and title at 250.
PUSHOVER_MSG_LIMIT = 1024
PUSHOVER_TITLE_LIMIT = 250
STATE_PATH = "data/ev_alert_state.json"
LOG_MD = "data/EV_ALERTS.md"
TIERS = ["winner", "top3", "top5", "top10", "top20"]
TIER_LABEL = {"winner": "Win", "top3": "Top 3", "top5": "Top 5",
              "top10": "Top 10", "top20": "Top 20"}


# ---------------------------------------------------------------- primitives

def yes_cents(m: dict):
    """Cost in cents to buy YES, as the dashboard's priceYes() resolves it:
    yes_ask, then yes_bid, then the no-side complement, then last trade."""
    for k in ("yes_ask", "yes_bid"):
        v = m.get(k)
        if isinstance(v, (int, float)) and 0 < v < 100:
            return float(v)
    nb = m.get("no_bid")
    if isinstance(nb, (int, float)) and 0 < nb < 100:
        return float(100 - nb)
    lp = m.get("last_price")
    if isinstance(lp, (int, float)) and 0 < lp < 100:
        return float(lp)
    return None


def net_cents(c: float):
    """Fee-inclusive cost in cents of one contract quoted at `c` cents."""
    p = c / 100.0
    return (p + KALSHI_FEE_RATE * p * (1 - p)) * 100.0


def american(c: float):
    """American odds for a cents price (use net_cents() first for net odds)."""
    p = c / 100.0
    if not 0 < p < 1:
        return "-"
    return ("-%d" % round(100 * p / (1 - p))) if p >= 0.5 else ("+%d" % round(100 * (1 - p) / p))


def norm_name(s: str) -> str:
    """Match index.html's normName(): first+last token, accents/suffixes dropped."""
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    toks = [t for t in "".join(ch if ch.isalnum() else " " for ch in s).split()
            if t not in ("jr", "sr", "ii", "iii", "iv")]
    if not toks:
        return ""
    return toks[0] if len(toks) == 1 else toks[0] + toks[-1]


def load_json(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------- scan

def series_keys():
    override = os.environ.get("EV_ALERT_SERIES", "").strip()
    if override:
        return [s.strip() for s in override.split(",") if s.strip()]
    idx = load_json("data/series.json") or {}
    return [s.get("key") for s in idx.get("series", []) if s.get("key")]


def scan():
    """Every qualifying line right now, as (key, row) pairs."""
    hits = []
    for skey in series_keys():
        sg = load_json(f"data/{skey}/manual/sg.json")
        if not sg or not sg.get("tiers"):
            continue
        race = sg.get("race") or skey
        for tier in TIERS:
            sg_tier = (sg["tiers"] or {}).get(tier)
            snap = load_json(f"data/{skey}/{tier}/snapshot.json")
            if not sg_tier or not snap:
                continue
            model = {}
            for d in sg_tier.get("drivers") or []:
                if isinstance(d.get("novig"), (int, float)):
                    model[norm_name(d.get("name", ""))] = float(d["novig"])
            for m in (snap.get("markets") or {}).values():
                c = yes_cents(m)
                if c is None:
                    continue
                p = model.get(norm_name(m.get("name", "")))
                if p is None:
                    continue
                cost = net_cents(c) / 100.0
                if not 0 < cost < 1:
                    continue
                ev = (p / cost - 1) * 100.0
                if ev < THRESH:
                    continue
                # Dedup identity: same driver, same market, same price = same bet.
                key = f"{skey}|{tier}|{m.get('name')}|{c:.0f}"
                hits.append((key, {
                    "series": skey, "race": race, "tier": tier,
                    "driver": m.get("name"), "yes_c": c, "net_c": net_cents(c),
                    "sg": p * 100, "ev": ev,
                    "volume": m.get("volume"), "open_interest": m.get("open_interest"),
                }))
    return hits


# ------------------------------------------------------------------ notify

def post_pr_comment(body: str) -> str:
    pr = os.environ.get("WATCH_PR_NUMBER", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not (pr and token and repo):
        return "pr-comment skipped (WATCH_PR_NUMBER / GITHUB_TOKEN / GITHUB_REPOSITORY unset)"
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        data=json.dumps({"body": body}).encode(), method="POST")
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


def pushover_body(rows) -> str:
    """Compact one-line-per-row body that fits Pushover's 1024-char cap."""
    lines = [f"{r['driver']} - {TIER_LABEL.get(r['tier'], r['tier'])} - "
             f"{r['yes_c']:.0f}c {american(r['net_c'])} net - "
             f"SG {r['sg']:.1f}% - EV +{r['ev']:.0f}%" for r in rows]
    kept, used = [], 0
    for ln in lines:
        # +24 leaves room for a trailing "+N more" line.
        if used + len(ln) + 1 + 24 > PUSHOVER_MSG_LIMIT:
            break
        kept.append(ln); used += len(ln) + 1
    if len(kept) < len(lines):
        kept.append(f"+{len(lines) - len(kept)} more")
    return "\n".join(kept)


def post_pushover(rows) -> str:
    token = os.environ.get("PUSHOVER_TOKEN", "").strip()
    user = os.environ.get("PUSHOVER_USER", "").strip()
    if not (token and user):
        return "pushover skipped (PUSHOVER_TOKEN / PUSHOVER_USER unset)"
    import urllib.parse
    n = len(rows)
    fields = {
        "token": token,
        "user": user,
        "title": f"{n} new {THRESH:.0f}%+ EV line{'' if n == 1 else 's'}"[:PUSHOVER_TITLE_LIMIT],
        "message": pushover_body(rows)[:PUSHOVER_MSG_LIMIT],
    }
    if SITE_URL:
        fields["url"] = SITE_URL
        fields["url_title"] = "Open dashboard"
    req = urllib.request.Request("https://api.pushover.net/1/messages.json",
                                 data=urllib.parse.urlencode(fields).encode(),
                                 method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return f"pushover sent ({resp.status})"
    except urllib.error.HTTPError as e:
        return f"pushover failed: HTTP {e.code} {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return f"pushover failed: {e}"


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
    if os.path.exists(LOG_MD):
        try:
            with open(LOG_MD) as fh:
                old = fh.read()
        except OSError:
            old = ""
    with open(LOG_MD, "w") as fh:
        fh.write(f"{header}\n\n{body}\n\n---\n\n{old}")


def fmt(rows) -> str:
    lines = [f"| Race | Market | Driver | Yes | Net | Net odds | SG | EV |",
             f"|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['race']} | {TIER_LABEL.get(r['tier'], r['tier'])} | {r['driver']} "
            f"| {r['yes_c']:.0f}c | {r['net_c']:.2f}c | {american(r['net_c'])} "
            f"| {r['sg']:.1f}% | **+{r['ev']:.1f}%** |")
    return "\n".join(lines)


# --------------------------------------------------------------------- main

def main() -> int:
    hits = scan()
    state = load_json(STATE_PATH) or {}
    prev = set(state.get("keys") or [])
    cur_keys = [k for k, _ in hits]

    new = [(k, r) for k, r in hits if k not in prev]
    new.sort(key=lambda kr: -kr[1]["ev"])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"evwatch: thresh={THRESH:.0f}% qualifying={len(hits)} "
          f"new={len(new)} carried={len(hits) - len(new)}")

    # Persist AFTER computing new, so this run's set is next run's baseline.
    with open(STATE_PATH, "w") as fh:
        json.dump({"updated_at": now, "thresh": THRESH,
                   "keys": sorted(cur_keys)}, fh, indent=2)

    if not new:
        write_summary(f"**EV watch** — no new lines >= +{THRESH:.0f}% "
                      f"({len(hits)} still qualifying).")
        return 0

    rows = [r for _, r in new]
    table = fmt(rows)
    head = (f"### New Kalshi vs SG lines >= +{THRESH:.0f}% EV — {len(rows)} "
            f"({now})")
    note = ("_EV is net of Kalshi fees (cost = p + 0.07·p·(1−p)); SG fair is the "
            "no-vig model probability. A line stays quiet until its price changes._")
    # Lead with the mention: it is what turns this comment into an emailed
    # notification for someone who is not subscribed to the thread.
    lead = f"{MENTION} " if MENTION else ""
    body = f"{lead}{head}\n\n{table}\n\n{note}"

    print(body)
    write_summary(body)
    prepend_md(head, f"{table}\n\n{note}")
    print(" ", post_pushover(rows))
    print(" ", post_webhook(body))
    print(" ", post_pr_comment(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
