# NASCAR Kalshi vs Sportsbook odds tracker

A dashboard comparing **Kalshi** (prediction market — treated as source of truth /
"fair") against sportsbooks for the current NASCAR Cup race. Kalshi and FanDuel are
scraped automatically in CI; other books are entered by hand from posted boards.
Published to GitHub Pages from `index.html` + the `data/` tree.

## Branches & deploy flow (IMPORTANT)

- **Pages / default / deploy branch:** `claude/nascar-page-scraper-mwi55a`. This is
  what CI runs and what GitHub Pages serves.
- **Dev branch:** develop changes here, then land the files on the deploy branch.
- To deploy data/code changes, put the files on the deploy branch and let
  `track.yml` publish. The pattern used in-session:
  ```
  git fetch origin claude/nascar-page-scraper-mwi55a
  git checkout -B _dl origin/claude/nascar-page-scraper-mwi55a
  git checkout <dev-branch> -- <files>        # bring over the edited files
  git commit -m "..." && git push origin _dl:claude/nascar-page-scraper-mwi55a
  git checkout <dev-branch> && git branch -D _dl
  ```
- A push that changes **`index.html` / `scraper.py` / `linewatch.py` / the workflow**
  auto-triggers `track.yml`. A **data-only** push does not — trigger it manually
  (`actions_run_trigger` → `run_workflow track.yml`, ref = deploy branch) to publish.
- Confirm a deploy by the deploy branch HEAD advancing / a `data: market update`
  commit landing (that = scrape+commit+Pages deploy completed).

## CI workflows

- **`track.yml`** — scrapes Kalshi every 15 min (also `workflow_dispatch`), runs
  `linewatch.py`, commits `data/` changes, deploys Pages. Runners have open egress
  (Kalshi is reachable there but NOT from a Claude session — the session proxy blocks
  kalshi.com, so always scrape via CI, never inline).
- **`fanduel.yml`** — scrapes FanDuel (headless Chromium), commits data only. Does
  **not** deploy — fire `track.yml` afterward to publish.
- **`linewatch.py`** — line-move watch: diffs each Cup market's YES price vs a
  committed baseline (`data/cup/watch_baseline.json`); on a move ≥3pp (or the fixed
  Cindric trip-wire) posts to the watch PR (`WATCH_PR_NUMBER` repo variable) so a
  subscribed session wakes only on a real move. Unset var ⇒ it just logs to the job
  summary + `data/cup/WATCH.md`.

## Data layout

- `data/cup/<tier>/snapshot.json` — Kalshi current state. `tier` ∈ winner/top3/top5/
  top10/top20. Markets keyed by ticker; each has `yes_bid`/`yes_ask`/`last_price`.
  **Use `yes_ask` as the YES price; fair ≈ mid of bid/ask.**
- `data/cup/<tier>/series.jsonl` — aligned price history (`{t, p:{ticker: cents}}`),
  for trajectories / line-move diffs.
- `data/cup/alerts.jsonl` — committed large-**trade** log (>$100), the source for
  "big trades" questions. Each row: driver, tier, side (yes/no), count, price_cents,
  value_usd, created_time.
- `data/cup/trades_window.jsonl` — rolling **6h log of ALL trades** (every size, not
  just >$100), for full-volume flow analysis. Compact one-line JSON per trade:
  `{trade_id, created_time, driver, tier, side, count, yes_price, no_price}`. Built
  each run from the trades already paginated for alerting (no extra API calls),
  deduped by `trade_id`, pruned to `TRADES_WINDOW_HOURS` (default 6). Watched
  (Cup) series only. `$ = count * price/100`; use `yes_price`/`no_price` by `side`.
- `data/cup/fanduel/{odds,manufacturers,teams}.json` — FanDuel scrape.
- `data/cup/manual/<book>.json`, `mfr_<book>.json`, `team_<book>.json` — hand-entered
  books. Books: fanduel (auto), caesars, betus, betonline, betboss, prime.

## Entering a hand-entered book

Use `gen_books.py` (canonicalizes driver names + no-vig normalizes). See its
docstring. Roughly:
```python
import gen_books as gb
gb.write_book("caesars.json", "Caesars",
              {"winner": (win_rows, 1), "top3": (t3, 3), "top5": (t5, 5), "top10": (t10, 10)})
gb.write_mfr("mfr_caesars.json", "Caesars", which_make_3way, {"Chevrolet":..,"Ford":..,"Toyota":..})
gb.write_team("team_caesars.json", "Caesars", team_rows)
```
Then deploy (see flow above). Boards often list a driver twice (e.g. "Darrell Wallace
Jr" + "Bubba Wallace") — `gen_books` canonicalizes and keeps the first; use main-grid
values. **If a re-uploaded book omits a tier/market (a finish tier, the which-make
3-way, team board, etc.), REMOVE it — do not preserve the old values.** Books don't
always repost everything, so treat an absent line as pulled/stale rather than
carrying forward a prior capture. (Exception: a partial screenshot that's clearly
just cut off mid-board — e.g. the bottom longshots scrolled off — is not the same as
a tier being dropped; keep the off-screen rows for that same tier.)

**Capture completeness (IMPORTANT):** For every book **except Prime**, transcribe the
**full board** — a single mid-pack or longshot driver moving meaningfully matters, so
never shortcut to just the favorites. **Prime only** is the exception: its sportsbook
reprices the whole board by a few points each capture (proportional drift) rather than
moving individual drivers, so on a Prime refresh eyeball the top ~6 favorites vs the
live Prime board and, if none moved meaningfully (more than a few %), treat it as drift
and skip the re-entry. Never apply this favorites-only shortcut to any other book.

## Analysis scripts

- **`ev_model.py`** — finish-distribution EV model (implements the matchup convention
  below). `python ev_model.py h2h "Ty Gibbs,-201,Tyler Reddick,165" ...` prints an EV
  table (edge pp + EV% = model_P·decimal−1), +EV first. `python ev_model.py book
  data/cup/manual/<book>.json <tier>` values a book's tier vs Kalshi fair. Reads the
  committed `data/cup/<tier>/snapshot.json` — no setup. NOTE: the `book` scan is only
  meaningful **pre-race**; once the race is live the Kalshi snapshot reflects running
  order and pre-race book prices look absurdly +EV.
- **`trades.py`** — biggest Kalshi trades from `alerts.jsonl`, splitting directional
  YES/NO from the field-lay harvest. `python trades.py [--hours N | --date YYYY-MM-DD]`.

## Analysis conventions

- **Kalshi = fair.** A book bet is +EV iff Kalshi's fair prob > the book's raw
  (with-vig) implied prob. For matchups, estimate P(A finishes ahead of B) from each
  driver's finish-tier distribution (win/top3/top5/top10 → bucket CDF, shared tail as
  ~50/50), then compare to the offered price.
- **`novig`** = de-vigged, normalized so a tier sums to its winner count. **`implied`**
  = raw price you actually pay. Use raw implied for EV vs a book.
- **Trades: separate signal from noise.** Big **Winner-NO** buys at high-90¢ across
  many drivers at once = a "lay the field" / premium-harvest / MM flow — NOT
  directional; discount it. **YES** buys (and NO at 80–90¢) are directional
  conviction. Cross-confirm price moves against trade flow and FanDuel.
- Report line moves at a **≥3pp** threshold by default.

## Standard task prompts

- "Trigger a fresh Kalshi scrape (`track.yml`) and confirm the site updated."
- "Refresh FanDuel (`fanduel.yml`), deploy, and report line moves ≥3pp vs the prior board."
- "Updated <Book> lines: <paste>. Regenerate the manual JSON with `gen_books.py`,
  deploy, and report the major moves."
- "Summarize the biggest Kalshi trades in the last 30 min from `alerts.jsonl` —
  separate directional YES/NO from the field-lay harvest."
- "Show Kalshi YES-price moves ≥3pp over the last hour (now vs recent) with live
  bid/ask; flag which are cross-confirmed."
- "Scan every book vs Kalshi fair (mid) across all tiers and rank +EV spots."
- "Is <Driver A> <odds> to beat <Driver B> a good bet?"

## Notes

- Repo is **public** ⇒ GitHub Actions minutes are free; scrape frequency is not a cost
  concern. The real cost is waking a large-context Claude session repeatedly — prefer
  the CI `linewatch.py` event-driven path over a fixed-interval self-wake loop.
- Kalshi is NOT reachable from a Claude session (proxy blocks it) — scrape via CI only.
