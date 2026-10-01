#!/usr/bin/env python3
"""Alert on NEW high-EV Kalshi lines, across every scraped race.

Two independent scans run per poll, each the CI-side twin of a dashboard tab:

  SG         -- Kalshi priced against SG's no-vig model probability.
                Tab: "Kalshi vs SG". Threshold EV_ALERT_THRESH.
  Consensus  -- Kalshi priced against the sportsbooks' average.
                Tab: "Kalshi vs Consensus". Threshold EV_CONSENSUS_THRESH.

They share this process, this state file and this Pushover call ON PURPOSE.
CLAUDE.md's warning is about two SEPARATE alert PATHS with separate dedup
state, which double-alerts; one process with one state file and namespaced keys
is the opposite of that. It also means the consensus scan needs no new
cron-job.org pinger — the existing ~5-minute ping at evalert.yml drives both.

READ THIS BEFORE TRUSTING A CONSENSUS ALERT. The consensus mirrors the
dashboard, which keeps the books' VIG IN (see index.html's CONSENSUS_WITH_VIG).
That inflates every driver's probability by the book margin, ~40-50% on these
boards, which biases the YES side UP and the NO side DOWN. So a consensus Yes
alert means "Kalshi is cheaper than the books' shaded price" — a LOWER bar than
beating their fair value, not a higher one. The SG scan is the fair-value read.
Set EV_CONSENSUS_WITH_VIG=0 to price consensus de-vigged instead, which also
restores the tier renormalization so it matches the de-vigged dashboard exactly.

For each series
that has both a Kalshi snapshot and an SG model book, it prices buying Kalshi
YES at its ask AND NO at its ask -- FEE-INCLUSIVE, matching index.html's
netCost() and alerts.py's net_american_odds() -- against SG's no-vig
probability (p for Yes, 1-p for No), and flags anything at or above
``EV_ALERT_THRESH`` percent. Both sides are scanned because when SG rates a
driver far BELOW Kalshi the tradeable edge is on NO; a YES-only scan showed
that as a deeply negative line and never alerted on it.

Only *new* lines alert. Dedup key is (source, series, tier, driver, side,
price_band) -- the source is part of the identity, so an SG alert never
suppresses the consensus alert for the same driver, or vice versa. SG keys keep
their original unprefixed shape so state written before the consensus scan
existed still suppresses them. Otherwise, so
a line that was already qualifying at the same price on the previous run stays
quiet; the same driver/market at a MATERIALLY different price is a new line and
alerts again (the price moving is the point). The band is ``EV_DEDUP_BUCKET_C``
cents wide so that sub-band jitter does not re-ping — this is what lets the poll
interval shrink without the ping rate rising with it. State lives in
``data/ev_alert_state.json`` and is committed by the workflow like the other
watch state, so it survives across runs.

Channels (all optional, all no-ops when unset):
  PUSHOVER_TOKEN /   Pushover application token + user key. Phone push, and the
  PUSHOVER_USER      only channel here that does not depend on GitHub's email
                     delivery (which notifies the web inbox but was not mailing).
  ALERT_WEBHOOK_URL  Slack/Discord/ntfy/generic incoming webhook
                     (shared with alerts.py). This is the hook a
                     Twilio/IFTTT/Zapier relay would use to fan out to SMS.
  WATCH_PR_NUMBER    issue/PR to comment on -- GitHub then emails its watchers,
                     which is the zero-setup email path.
  GITHUB_TOKEN       token used to post that comment (provided by Actions).

Env:
  EV_ALERT_THRESH    minimum EV percent to alert on, SG scan (default 30)
  EV_CONSENSUS_THRESH      minimum EV percent, consensus scan (default: the
                           same as EV_ALERT_THRESH)
  EV_CONSENSUS_WITH_VIG    1 (default) = consensus keeps the books' vig in,
                           matching the dashboard. 0 = de-vigged + renormalized.
  EV_CONSENSUS_MIN_BOOKS   books required before a driver's average counts as a
                           consensus at all (default 2)
  EV_DEDUP_BUCKET_C  price-band width in cents for dedup (default 2; 1 = alert
                     on every single-cent tick, the pre-banding behaviour)
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
try:
    DEDUP_BUCKET_C = max(1, int(os.environ.get("EV_DEDUP_BUCKET_C", "2")))
except ValueError:
    DEDUP_BUCKET_C = 2
# Consensus scan. Thresholds are separate so the two reads can be tuned
# independently -- they do NOT mean the same thing (see the module docstring).
CONSENSUS_THRESH = float(os.environ.get("EV_CONSENSUS_THRESH", str(THRESH)))
CONSENSUS_WITH_VIG = os.environ.get("EV_CONSENSUS_WITH_VIG", "1").strip() != "0"
try:
    CONSENSUS_MIN_BOOKS = max(1, int(os.environ.get("EV_CONSENSUS_MIN_BOOKS", "2")))
except ValueError:
    CONSENSUS_MIN_BOOKS = 2

# Sportsbooks feeding the consensus, mirroring index.html's BOOKS array minus
# its `model: true` entries. SG is excluded by construction: it is a model, not
# a book, it anchors the other scan, and it posts at ~0% vig so averaging it in
# would dilute exactly the margin the consensus view exists to show.
#
# Hardcoded rather than globbed data/<series>/manual/*.json deliberately. A
# glob would silently pull in a board the dashboard does not list, so the
# pager and the tab would disagree about what "consensus" means. Keep this in
# lockstep with index.html's BOOKS (and with its model flags).
CONSENSUS_BOOKS = (
    ("FanDuel", "fanduel/odds.json"),
    ("BetUS", "manual/betus.json"),
    ("Caesars", "manual/caesars.json"),
    ("Prime", "manual/prime.json"),
    ("BetBoss", "manual/betboss.json"),
    ("BetOnline", "manual/betonline.json"),
    ("BetRivers", "manual/betrivers.json"),
    ("VIP365", "manual/vip365.json"),
)

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
    yes_ask, then the no-side complement (100 - no_bid IS the yes ask), then
    last trade.

    NEVER falls back to yes_bid. A bid is the price you could SELL at; pricing
    a BUY there invents a trade that does not exist, and on a one-sided book
    (nothing offered, only a bid resting) it manufactures enormous phantom EV.
    A price of 100 is returned as-is rather than skipped here — the caller's
    0 < cost < 1 guard drops it — so that "no offer" stays visible as an
    untradeable 100 instead of silently resolving to the other side.
    """
    v = m.get("yes_ask")
    if isinstance(v, (int, float)):
        return float(v)
    nb = m.get("no_bid")
    if isinstance(nb, (int, float)):
        return float(100 - nb)
    lp = m.get("last_price")
    if isinstance(lp, (int, float)) and 0 < lp < 100:
        return float(lp)
    return None


def no_cents(m: dict):
    """Cost in cents to buy NO, as the dashboard's priceNo() resolves it:
    no_ask, then the yes-side complement (100 - yes_bid IS the no ask).

    NEVER falls back to no_bid — see yes_cents(). This is the exact shape the
    deep longshots take: yes_bid=0 / yes_ask=12 / no_bid=88 / no_ask=100, i.e.
    nobody is offering NO at all. Reading no_bid=88 there priced a No buy at a
    price only a seller could get, and against an SG fair of ~99.9% that shows
    up as a +80% "line" that cannot be taken.
    """
    v = m.get("no_ask")
    if isinstance(v, (int, float)):
        return float(v)
    yb = m.get("yes_bid")
    if isinstance(yb, (int, float)):
        return float(100 - yb)
    y = yes_cents(m)
    return None if y is None else float(100 - y)


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
    """Match index.html's normName(): first token + middle INITIALS + last
    token, accents/suffixes dropped.

    Middle tokens are reduced rather than dropped, and both halves of that
    matter. Reducing them is what lets FanDuel's "John Hunter Nemechek" meet
    Kalshi's "John H. Nemechek" and "A.J." meet "AJ". Keeping them is what
    stops "Austin J Hill" (#53) collapsing onto "Austin Hill" (#21) — two real
    drivers in the same Xfinity field. This function feeds the SG lookup, so a
    collision there would price one driver's Kalshi Yes against the other's
    model probability (0.9% vs 47.4% on top 10) and alert on a phantom edge.

    Keep this in lockstep with index.html's normName(); the dashboard and this
    alert path must agree on what counts as the same driver.
    """
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    toks = [t for t in "".join(ch if ch.isalnum() else " " for ch in s).split()
            if t not in ("jr", "sr", "ii", "iii", "iv")]
    if not toks:
        return ""
    if len(toks) == 1:
        return toks[0]
    return toks[0] + "".join(t[0] for t in toks[1:-1]) + toks[-1]


def _band(cents: float) -> int:
    """Price band a line falls in, for dedup. Set EV_DEDUP_BUCKET_C=1 to restore
    the old exact-cent behaviour (every 1c tick is a new alert)."""
    return int(cents) // DEDUP_BUCKET_C


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


def consensus_fair(skey: str, tier: str):
    """Mirror of index.html's consensusFair(): per-driver mean of the
    sportsbooks' probability for one series/tier.

    Returns {norm_name: (prob, n_books, [labels])}, dropping any driver fewer
    than CONSENSUS_MIN_BOOKS priced -- one book is not a consensus, it is that
    book.

    Two things must stay true of this function or the pager and the dashboard
    will disagree:

      The mean is over the books that priced HIM, not every book carrying the
      tier. A book that never listed a driver has no opinion on him, and
      treating that silence as a zero would bury every part-time entry.

      Renormalization is tied to the vig choice, not independent of it.
      Rescaling a tier so it sums to its winner count IS proportional
      de-vigging, so it must happen when (and only when) we are using novig.
      Doing it in the with-vig path would silently strip the margin back out
      and make EV_CONSENSUS_WITH_VIG a no-op.
    """
    acc, winners = {}, 0
    for label, rel in CONSENSUS_BOOKS:
        book = load_json(f"data/{skey}/{rel}")
        t = ((book or {}).get("tiers") or {}).get(tier)
        if not t:
            continue
        nw = t.get("number_of_winners")
        if isinstance(nw, (int, float)):
            winners = max(winners, int(nw))
        for d in t.get("drivers") or []:
            v = d.get("implied") if CONSENSUS_WITH_VIG else d.get("novig")
            if not isinstance(v, (int, float)) or not v > 0:
                continue
            k = norm_name(d.get("name", ""))
            if not k:
                continue
            e = acc.setdefault(k, {"sum": 0.0, "books": []})
            e["sum"] += float(v)
            e["books"].append(label)
    if not acc:
        return {}
    means = {k: e["sum"] / len(e["books"]) for k, e in acc.items()}
    total = sum(means.values())
    scale = (winners / total) if (not CONSENSUS_WITH_VIG and winners > 0 and total > 0) else 1.0
    return {k: (means[k] * scale, len(e["books"]), e["books"])
            for k, e in acc.items() if len(e["books"]) >= CONSENSUS_MIN_BOOKS}


def _lines(skey, race, tier, snap, fair_map, source, thresh, key_prefix):
    """Qualifying lines for one (series, tier) against one fair source.

    Shared by both scans so the pricing can never drift between them: the fee
    model, the side handling and the dedup shape are defined once here.
    """
    hits = []
    for m in (snap.get("markets") or {}).values():
        info = fair_map.get(norm_name(m.get("name", "")))
        if info is None:
            continue
        p, n_books, books = info
        if not 0 < p < 1:
            continue
        # Both sides are tradeable, and they are not redundant: when the fair
        # source rates a driver well BELOW Kalshi the edge is on NO, which a
        # YES-only scan reports as a deeply negative line and never flags.
        # Fair prob of the side bought is p for Yes, 1-p for No; the fee
        # formula is symmetric in the price, so net_cents() applies unchanged
        # to a No quote.
        for side, c, fair in (("Yes", yes_cents(m), p),
                              ("No", no_cents(m), 1.0 - p)):
            if c is None:
                continue
            cost = net_cents(c) / 100.0
            if not 0 < cost < 1:
                continue
            ev = (fair / cost - 1) * 100.0
            if ev < thresh:
                continue
            # Dedup identity: source, driver, market, side, price BAND. Banding
            # is what keeps the poll interval and the ping rate decoupled.
            # Keying on the exact cent meant a line oscillating 7c/8c/7c
            # re-alerted on every flip, so polling twice as often produced
            # roughly twice the pings for the same one bet. The source prefix
            # keeps the two scans from suppressing each other; it is empty for
            # SG so state written before the consensus scan existed still
            # suppresses those lines.
            tag = "" if side == "Yes" else f"{side}|"
            key = f"{key_prefix}{skey}|{tier}|{m.get('name')}|{tag}{_band(c)}"
            hits.append((key, {
                "series": skey, "race": race, "tier": tier,
                "driver": m.get("name"), "side": side, "source": source,
                "price_c": c, "net_c": net_cents(c),
                "fair": fair * 100, "books": n_books, "book_list": books,
                "ev": ev,
                "volume": m.get("volume"), "open_interest": m.get("open_interest"),
            }))
    return hits


def scan():
    """Every qualifying line right now, as (key, row) pairs, across both scans."""
    hits = []
    for skey in series_keys():
        sg = load_json(f"data/{skey}/manual/sg.json")
        race = (sg or {}).get("race") or skey
        for tier in TIERS:
            snap = load_json(f"data/{skey}/{tier}/snapshot.json")
            if not snap:
                continue

            # --- scan 1: Kalshi vs SG's no-vig model fair -------------------
            sg_tier = ((sg or {}).get("tiers") or {}).get(tier)
            if sg_tier:
                model = {}
                for d in sg_tier.get("drivers") or []:
                    if isinstance(d.get("novig"), (int, float)):
                        model[norm_name(d.get("name", ""))] = (float(d["novig"]), None, [])
                hits += _lines(skey, race, tier, snap, model, "SG", THRESH, "")

            # --- scan 2: Kalshi vs the sportsbook consensus -----------------
            cons = consensus_fair(skey, tier)
            if cons:
                hits += _lines(skey, race, tier, snap, cons, "Consensus",
                               CONSENSUS_THRESH, "cons|")
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
    lines = [f"[{r['source'][:4]}] {r['driver']} - {TIER_LABEL.get(r['tier'], r['tier'])} "
             f"{r['side']} - {r['price_c']:.0f}c {american(r['net_c'])} net - "
             f"fair {american(r['fair'])} - EV +{r['ev']:.0f}%" for r in rows]
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
    # Name the source(s) in the title: an SG line and a consensus line are not
    # the same claim, and the title is all you see on a locked phone.
    srcs = sorted({r["source"] for r in rows})
    what = "/".join(srcs) if srcs else "EV"
    fields = {
        "token": token,
        "user": user,
        "title": f"{n} new {what} EV line{'' if n == 1 else 's'}"[:PUSHOVER_TITLE_LIMIT],
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
    lines = ["| Race | Market | Driver | Side | Vs | Price | Net | Net odds | Fair | Books | EV |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['race']} | {TIER_LABEL.get(r['tier'], r['tier'])} | {r['driver']} "
            f"| {r['side']} | {r['source']} | {r['price_c']:.0f}c | {r['net_c']:.2f}c "
            f"| {american(r['net_c'])} | {american(r['fair'])} ({r['fair']:.1f}%) "
            f"| {r['books'] if r['books'] else '-'} | **+{r['ev']:.1f}%** |")
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
    by_src = {}
    for _, r in hits:
        by_src[r["source"]] = by_src.get(r["source"], 0) + 1
    print(f"evwatch: sg_thresh={THRESH:.0f}% cons_thresh={CONSENSUS_THRESH:.0f}% "
          f"cons_vig={'in' if CONSENSUS_WITH_VIG else 'out'} "
          f"qualifying={len(hits)} ({by_src}) "
          f"new={len(new)} carried={len(hits) - len(new)}")

    # Persist AFTER computing new, so this run's set is next run's baseline.
    with open(STATE_PATH, "w") as fh:
        json.dump({"updated_at": now, "thresh": THRESH,
                   "keys": sorted(cur_keys)}, fh, indent=2)

    if not new:
        write_summary(f"**EV watch** — no new lines (SG >= +{THRESH:.0f}%, "
                      f"consensus >= +{CONSENSUS_THRESH:.0f}%); "
                      f"{len(hits)} still qualifying.")
        return 0

    rows = [r for _, r in new]
    table = fmt(rows)
    counts = ", ".join(f"{k} {v}" for k, v in sorted(
        {r["source"]: sum(1 for x in rows if x["source"] == r["source"]) for r in rows}.items()))
    head = f"### New high-EV Kalshi lines — {len(rows)} ({counts}) ({now})"
    vig = "WITH the books' vig in" if CONSENSUS_WITH_VIG else "de-vigged"
    note = ("_EV is net of Kalshi fees (cost = p + 0.07·p·(1−p)). "
            f"**SG** rows price against SG's no-vig model fair (>= +{THRESH:.0f}%). "
            f"**Consensus** rows price against the sportsbooks' average, {vig} "
            f"(>= +{CONSENSUS_THRESH:.0f}%) — that margin biases consensus Yes EV "
            "UP and No EV DOWN, so a consensus Yes means Kalshi beats the books' "
            "shaded price, not their fair value. A line stays quiet until its "
            "price changes._")
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
