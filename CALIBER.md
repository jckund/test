# Caliber Collision location watcher

Separate from the NASCAR dashboard in this repo. Scrapes every Caliber Collision
location weekly, diffs against the previous week, and **emails new / removed
locations** — nothing is sent on a quiet week.

## How it works

The store locator at <https://www.caliber.com/find-a-location> is a Next.js
front-end over a **dotCMS** backend. Individual shops are the dotCMS content type
`Center`, served anonymously by the Content REST API. Pulling the full live set
is the programmatic equivalent of clicking into every state on the directory
(~2,950 centers across 41 states).

> caliber.com is **not reachable from a Claude session** (the egress proxy blocks
> it), so the scrape only ever runs in GitHub Actions, never inline. Same
> constraint as the Kalshi scraper.

Pipeline (all standard-library Python, no third-party Actions):

| File | Role |
|------|------|
| `caliber_scraper.py` | Pages the dotCMS `Center` API, writes the normalized snapshot. |
| `caliber_report.py`  | Diffs this week's scrape vs the committed baseline by stable `identifier`; builds the email; logs the change. |
| `caliber_sendmail.py`| Sends the email over Gmail/Workspace SMTP (`smtplib`). |
| `.github/workflows/caliber_locations.yml` | Weekly cron that runs the three in order and commits the new baseline. |

## Data

- `data/caliber/locations.json` — `{identifier: {centerId, name, address1, city,
  state, zip, phone, email, latitude, longitude, openDate, status, url}}`, sorted.
  Changes **only** when a location is added / removed / edited, so the git history
  is a clean audit trail and the weekly diff is trivial.
- `data/caliber/meta.json` — run heartbeat (`captured_at`, `count`, `states`).
  Rewritten every run; kept out of `locations.json` so a timestamp bump is never
  mistaken for a change.
- `data/caliber/changes.jsonl` — one row per week that had a change (added /
  removed names), appended over time.

New/removed is tracked by presence (dotCMS `identifier`). Address or hours edits
to an existing shop are not treated as "new/removed".

## Setup — required before emails can send

Email needs two repository secrets. **Settings → Secrets and variables → Actions
→ New repository secret:**

| Secret | Value |
|--------|-------|
| `MAIL_USERNAME` | Your Google address, e.g. `justin@vivecollision.com`. Also appears as the From. |
| `MAIL_PASSWORD` | A Google **app password** (16 chars), *not* your normal password. |

Getting a Gmail/Workspace app password: enable **2-Step Verification** on the
Google account, then create one at <https://myaccount.google.com/apppasswords>
(pick "Mail"). Paste the 16-character value as `MAIL_PASSWORD`.

Optional: repository **variable** `MAIL_TO` to send somewhere other than the
default `justin@vivecollision.com`. To use a non-Gmail SMTP server, set env
`SMTP_HOST`/`SMTP_PORT` in the workflow (defaults `smtp.gmail.com:465`).

## Enabling the weekly run

GitHub only fires `schedule` and `workflow_dispatch` from a repository's
**default branch**. This pipeline currently lives on
`claude/location-scraper-weekly-email-2wu2yc`, so:

- **To activate the weekly cron** (Mondays 13:00 UTC), merge these files to the
  repository's default branch. Until then the cron will not fire.
- While on the feature branch, the workflow also triggers on **push** to those
  files, which is how it was tested.

The first run on any fresh branch **seeds the baseline silently** (no email),
because everything would otherwise look "new". Real new/removed emails start from
the second run onward.

## Manual test / run

Once on the default branch: **Actions → "Caliber locations weekly watch" → Run
workflow**. Or push a change to any of the `caliber_*.py` files on the feature
branch. Check the run log for the `+N new / −M removed` summary; if secrets are
set and there was a change, the email goes out.
