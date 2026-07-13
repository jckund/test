# Kalshi NASCAR market tracker

Scrapes and tracks changes to this Kalshi market over time:

**<https://kalshi.com/markets/kxnascarrace/nascar-race/kxnascarrace-quas4aa26>**
(event ticker `KXNASCARRACE-QUAS4AA26`)

## Tracked markets

The race page groups several markets, each a separate Kalshi event. All are
tracked, one folder per tier under `data/`:

| Tier | Folder | Event ticker |
| --- | --- | --- |
| Winner | `data/winner/` | `KXNASCARRACE-QUAS4AA26` |
| Top 3 finishers | `data/top3/` | `KXNASCARTOP3-QUAS4AA26` |
| Top 5 finishers | `data/top5/` | `KXNASCARTOP5-QUAS4AA26` |
| Top 10 finishers | `data/top10/` | `KXNASCARTOP10-QUAS4AA26` |
| Top 20 finishers | `data/top20/` | `KXNASCARTOP20-QUAS4AA26` |

## How it works

The public Kalshi website is behind Cloudflare and can't be scraped directly,
but Kalshi exposes the same data through its public, unauthenticated trade API:

```
GET https://api.elections.kalshi.com/trade-api/v2/events/<EVENT_TICKER>?with_nested_markets=true
```

[`scraper.py`](scraper.py) fetches each tier's event and all nested markets (one
per driver), normalizes the fields we care about (last price, yes/no bid & ask,
volume, open interest, status), and writes them to `data/<tier>/`. It compares
each run against the previous snapshot and only writes when something actually
changed. A top-level `data/index.json` lists the tiers for the dashboard.

To track a different race, change `KALSHI_RACE_CODE` (default `QUAS4AA26`) — the
event tickers are built from that code.

A GitHub Actions workflow ([`.github/workflows/track.yml`](.github/workflows/track.yml))
runs the scraper on a schedule (every 15 minutes) and commits any changes back
to the repo. **Git history is therefore the change log** — `git log -- data/`
shows every market update over time.

> Why a scheduled workflow instead of running locally? GitHub-hosted runners
> have unrestricted outbound internet. A Claude Code web session, by contrast,
> runs behind an egress proxy that blocks `kalshi.com`, so the scrape has to
> happen where the network allows it.

## Golf tracker (PGA Tour)

Alongside NASCAR, [`golf_scraper.py`](golf_scraper.py) tracks a Kalshi golf
tournament across four tiers:

**<https://kalshi.com/markets/kxpgatour/pga-tour/kxpgatour-thoc26>**
(2026 The Open Championship)

| Tier | Folder | Kalshi series | Event ticker |
| --- | --- | --- | --- |
| Winner | `data/golf/winner/` | `KXPGATOUR` | `KXPGATOUR-THOC26` |
| Top 5 | `data/golf/top5/` | `KXPGATOP5` | `KXPGATOP5-THOC26` |
| Top 10 | `data/golf/top10/` | `KXPGATOP10` | `KXPGATOP10-THOC26` |
| Make Cut | `data/golf/makecut/` | `KXPGAMAKECUT` | `KXPGAMAKECUT-THOC26` |

Unlike NASCAR (all tiers under one winner series), Kalshi files **each golf tier
under its own series**, sharing the tournament's event suffix (`-THOC26`). Each
event nests one market per golfer (~165). The scraper normalizes the same fields
(last price, yes/no bid & ask, volume, open interest, status), writes per-tier
`snapshot.json` / `latest.json` / `history.jsonl` / `series.jsonl` / `CHANGES.md`
under `data/golf/<tier>/`, plus a top-level `data/golf/index.json` (tier list +
tournament title) and `data/golf/activity.json` (recent trades merged across
tiers). It only writes a tier when something changed, so **git history is the
change log** — `git log -- data/golf/`.

A separate workflow ([`.github/workflows/golf.yml`](.github/workflows/golf.yml))
runs it every 15 minutes on GitHub's runners (whose open network can reach the
Kalshi API — a Claude Code web session's egress proxy cannot) and commits any
changes back. Scheduled runs only fire from the repo's default branch; until
this is merged there, use the **Run workflow** button (`workflow_dispatch`) or a
push to the feature branch to trigger it.

Point it at a different event with `GOLF_CODE` (e.g. `GOLF_CODE=PGC26` for the
PGA Championship). If that event's tier series differ, override `GOLF_TIERS` as
`key:Label:OddsLabel:SERIES,...`:

```bash
GOLF_CODE=THOC26 python3 golf_scraper.py     # no dependencies — stdlib only
```

## Large-trade alerts

[`alerts.py`](alerts.py) watches the **Cup series** (every NASCAR Cup driver
market) and raises an alert on any **single trade worth more than $100**.

Alerting does **not** sample. For each Cup market, the scraper paginates
*every* trade created since roughly the last run (`min_ts` + cursor, in
`collect_alert_trades`), so no large trade can slip through between polls no
matter how busy the market. This is separate from the dashboard's `activity.json`
feed, which still shows just the most recent trades per market.

**Trade value** is the cash the aggressor (taker) put in:

```
value = count × taker_price / 100
```

so 500 contracts bought at 43¢ is a **$215** trade. Kalshi prices are whole
cents 1–99; a YES taker pays the yes price, a NO taker pays the no price. The
threshold is strict (a trade must be *over* the amount), so an exactly-$100
trade does not alert.

Each new alert is:

- appended to `data/cup/alerts.jsonl` — **committed**, so git history is a durable
  log *and* the dedup source. The scraper reruns every 15 min on a fresh runner
  with no local state, so the committed log is what stops a trade from firing
  twice (`data/activity.json` is git-ignored and can't serve this).
- prepended to `data/cup/ALERTS.md` — human-readable, newest first.
- written to the **GitHub Actions job summary** (visible on the run page).
- POSTed to a **webhook** if one is configured — the actual "notify me" push.

### Getting notified

Add a repository secret named **`ALERT_WEBHOOK_URL`** (**Settings → Secrets and
variables → Actions → New repository secret**) pointing at any Slack/Discord/
Telegram or generic incoming webhook that accepts `{"text": "..."}`. The
workflow passes it to the scraper automatically. Without it, alerts still land
in `data/cup/ALERTS.md` and the job summary — and if you **watch the repo** on
GitHub, each alert commit is itself a notification.

### Tuning

All via env (set in [`track.yml`](.github/workflows/track.yml) or on the command
line):

| Env var | Default | Meaning |
| --- | --- | --- |
| `ALERT_MIN_USD` | `100` | Alert threshold in dollars |
| `ALERT_SERIES` | `cup` | Comma-separated series keys to watch (e.g. `cup,truck`) |
| `ALERT_WEBHOOK_URL` | — | Slack/Discord/generic incoming webhook |
| `ALERT_LOOKBACK_MIN` | `20` | How far back the alert fetch paginates each run. Keep it ≥ the schedule interval plus a safety margin; per-trade dedup absorbs the overlap |
| `KALSHI_TRADES_PER_MARKET` | `10` (workflow sets `50`) | Recent trades pulled per market **for the dashboard `activity.json` feed only** — does not affect alert coverage |

> **Coverage:** because the alert fetch paginates *all* trades in the lookback
> window (not a fixed sample), a large trade is caught as long as it happened
> within `ALERT_LOOKBACK_MIN` of a run and the run's pagination completes.
> Keep `ALERT_LOOKBACK_MIN` comfortably above the schedule interval so
> consecutive runs overlap and nothing falls in a gap.

## Viewing it

[`index.html`](index.html) is a static, dependency-free dashboard that reads the
files below and renders a driver leaderboard with **American (moneyline) odds**,
per-driver price **sparklines**, and a live change feed, with **tabs to switch
between tiers** (Winner / Top 3 / Top 5 / Top 10 / Top 20) plus an **Activity**
tab showing recent trades across all tiers. It auto-refreshes every 60 seconds.

Odds and ranking use each market's **mid-market implied price** (yes bid/ask
midpoint, falling back to the no side, then last trade), so thinly-traded tiers
don't show gaps where the last trade is stale or zero.

It's published to **GitHub Pages via GitHub Actions**: the same workflow that
scrapes also assembles `index.html` + `data/` and deploys them, so the site
updates on every run. One-time setup: repo **Settings → Pages → Build and
deployment → Source → GitHub Actions**. The live URL is then
`https://<owner>.github.io/<repo>/`.

## Output files

Written per tier, e.g. `data/winner/…`, `data/top10/…`:

| File | Contents |
| --- | --- |
| `data/<tier>/snapshot.json` | Normalized current state of every market |
| `data/<tier>/latest.json` | Full raw API response (for reference/debugging) |
| `data/<tier>/history.jsonl` | Append-only; one line per run that had changes, with a compact diff |
| `data/<tier>/series.jsonl` | Append-only aligned price series (last price per driver per run) — powers the dashboard sparklines |
| `data/<tier>/CHANGES.md` | Human-readable change log, newest first, with a standings table |
| `data/index.json` | List of tracked tiers (drives the dashboard tabs) |
| `data/activity.json` | Recent trades merged across all tiers (live feed; regenerated each run, git-ignored) |
| `data/cup/alerts.jsonl` | Append-only log of large-trade alerts (one JSON per line; committed — doubles as the dedup source) |
| `data/cup/ALERTS.md` | Human-readable large-trade alert log, newest first |

## Running it manually

```bash
python3 scraper.py          # no dependencies — Python 3 stdlib only
```

Point it at a different race with an env var:

```bash
KALSHI_RACE_CODE=SOMEOTHERCODE python3 scraper.py
```

## Adjusting the schedule

Edit the `cron` line in `.github/workflows/track.yml`. Note GitHub's scheduled
workflows are best-effort and may be delayed under load; ~5–15 minutes is the
practical floor. You can also trigger a run manually from the repo's **Actions**
tab (**Run workflow**).
