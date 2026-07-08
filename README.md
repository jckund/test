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
