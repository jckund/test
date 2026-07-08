# Kalshi NASCAR market tracker

Scrapes and tracks changes to this Kalshi market over time:

**<https://kalshi.com/markets/kxnascarrace/nascar-race/kxnascarrace-quas4aa26>**
(event ticker `KXNASCARRACE-QUAS4AA26`)

## How it works

The public Kalshi website is behind Cloudflare and can't be scraped directly,
but Kalshi exposes the same data through its public, unauthenticated trade API:

```
GET https://api.elections.kalshi.com/trade-api/v2/events/KXNASCARRACE-QUAS4AA26?with_nested_markets=true
```

[`scraper.py`](scraper.py) fetches the event and all nested markets (one per
driver), normalizes the fields we care about (last price, yes/no bid & ask,
volume, open interest, status), and writes them to [`data/`](data/). It compares
each run against the previous snapshot and only writes when something actually
changed.

A GitHub Actions workflow ([`.github/workflows/track.yml`](.github/workflows/track.yml))
runs the scraper on a schedule (every 15 minutes) and commits any changes back
to the repo. **Git history is therefore the change log** — `git log -- data/`
shows every market update over time.

> Why a scheduled workflow instead of running locally? GitHub-hosted runners
> have unrestricted outbound internet. A Claude Code web session, by contrast,
> runs behind an egress proxy that blocks `kalshi.com`, so the scrape has to
> happen where the network allows it.

## Output files

| File | Contents |
| --- | --- |
| `data/snapshot.json` | Normalized current state of every market |
| `data/latest.json` | Full raw API response (for reference/debugging) |
| `data/history.jsonl` | Append-only; one line per run that had changes, with a compact diff |
| `data/CHANGES.md` | Human-readable change log, newest first, with a standings table |

## Running it manually

```bash
python3 scraper.py          # no dependencies — Python 3 stdlib only
```

Override the target market with an env var:

```bash
KALSHI_EVENT_TICKER=KXNASCARRACE-SOMEOTHER python3 scraper.py
```

## Adjusting the schedule

Edit the `cron` line in `.github/workflows/track.yml`. Note GitHub's scheduled
workflows are best-effort and may be delayed under load; ~5–15 minutes is the
practical floor. You can also trigger a run manually from the repo's **Actions**
tab (**Run workflow**).
