# NASCAR Kalshi vs Sportsbook odds tracker

A dashboard comparing **Kalshi** (prediction market — treated as source of truth /
"fair") against sportsbooks for the current NASCAR Cup race. Kalshi and FanDuel are
scraped automatically in CI; other books are entered by hand from posted boards.
Published to GitHub Pages from `index.html` + the `data/` tree.

## Start of week (new race — DO THIS FIRST)

At the top of a new race weekend, the #1 thing that breaks is the Kalshi
**SERIES matchers** in `scraper.py` still pointing at last week's race, so the
new race silently falls to the `xfinity` catch-all and everything downstream is
misclassified. Kickoff sequence:

1. **Re-point matchers + clear stale data.** Update the `SERIES` matchers in
   `scraper.py` (case-insensitive substring on the race name) for this week's
   Cup / Xfinity / Truck races; `xfinity` is the default catch-all. Clear stale
   lines from every book/tier across Cup + support series (don't carry last
   week's boards forward).
2. **First pull + deploy.** Run `fanduel.yml`, then `track.yml` (Kalshi scrape +
   publish). Confirm the deploy branch advanced / a `data: market update` landed.
3. **Then** enter hand books as they arrive (batch — see below) and answer
   analysis asks.

Canonical kickoff prompt: *"New race week. Cup is `<RACE>`, Xfinity is `<RACE>`,
Trucks is `<RACE>`. Update the SERIES matchers in `scraper.py`, clear all stale
lines, grab fresh Kalshi + FanDuel, deploy, and confirm."*

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
- `data/cup/team/snapshot.json` — Kalshi's actual "which team/org wins" market
  (Cup-only, best-effort). Same market shape as a tier. The scraper doesn't know
  Kalshi's team-series ticker from dev, so `discover_team_event()` probes
  `TEAM_SERIES_CANDIDATES` (override via `KALSHI_TEAM_SERIES`) and uses the first
  that yields markets — check the CI log line `team: matched …` for the real
  ticker and pin it to the front once known. The Team tab shows this as a
  separate **Kalshi (Yes/No)** column beside the driver-sum **Implied** line; if
  the market isn't found the column is hidden and only Implied shows.
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
**Batch the deploy (IMPORTANT — cost).** Do NOT deploy per book. As each book/tier
arrives, generate the file(s) and commit to the **dev branch only** (a quick one-line
confirm, no CI). Hold the deploy-branch land + `track.yml` fire + deploy-watch until
the user signals the batch is done ("deploy" / "that's all" / "go live" / "push it").
Then do **one** landing commit, **one** `track.yml` run, **one** watch for the whole
batch. This collapses the expensive poll/notify/confirm loop from once-per-book to
once-per-batch. (If the user explicitly wants a single book live immediately, deploy
it — but the default is stage-then-batch.)

**Collect-mode is the DEFAULT (IMPORTANT — cost).** The expensive part is not the number
of messages — it's processing each paste as it lands (regenerate → reconcile → stage →
push → confirm every time). Decouple pasting from processing. When the user signals
updates are coming ("updates incoming", "here comes…", "quick updates") OR starts pasting
multiple books, stay in **collect-mode**: acknowledge each paste with a one-line "got
<book> <tiers>" and do NOTHING else — no `gen_books`, no scripts, no staging, no CI. Just
accumulate the raw boards. Only on an explicit go signal ("deploy" / "go" / "go live" /
"that's all" / "push it") process the WHOLE batch in a single pass: generate every file,
reconcile once, one land, one `track.yml`/`fanduel.yml` fire, one watch. This lets the
user spread a batch across many messages (e.g. the 5-image-per-message cap) with no extra
cost — many paste messages still collapse to one processing pass. Prefer **text/CSV** over
screenshots when the book allows it (no image cap, cheaper to process, zero transcription
risk — BetUS/SG paste cleanly as text). Only break collect-mode early if the user asks for
a single book live now, or asks an analysis question mid-collect.

**Fire-and-trust deploys + terse confirms (cost).** CI is reliable — do NOT poll/watch
every deploy. Fire `track.yml`, then move on; verify opportunistically (a cheap
`git fetch` + HEAD/`data: market update` check next time you touch the branch), and
actively watch only when debugging a failure or when the user asks to confirm. Confirm
**per batch, not per push**. Keep post-deploy write-ups to ~1–2 lines; run line-move /
"notable steam" / EV summaries only when the user asks, not automatically. For deploy
status prefer `git fetch` over the GitHub Actions API (`actions_list`/`get_workflow_run`
return huge payloads) — reserve those for debugging.

Then deploy (see flow above). Boards often list a driver twice (e.g. "Darrell Wallace
Jr" + "Bubba Wallace") — `gen_books` canonicalizes and keeps the first; use main-grid
values. **If a re-uploaded book omits a tier/market (a finish tier, the which-make
3-way, team board, etc.), REMOVE it — do not preserve the old values.** Books don't
always repost everything, so treat an absent line as pulled/stale rather than
carrying forward a prior capture. (Exception: a partial screenshot that's clearly
just cut off mid-board — e.g. the bottom longshots scrolled off — is not the same as
a tier being dropped; keep the off-screen rows for that same tier.)

**Clear stale data on every refresh (STANDING RULE — IMPORTANT).** Whenever doing a
refresh/deploy, proactively sweep the whole board for stale data and drop it — don't
wait to be asked. Stale = not from the current capture cycle. This covers:
- **Manual markets not re-provided** — a book's mfr/team/finish tier absent from the
  latest capture (per the don't-carry-forward rule above). Applies across all books.
- **Auto-scraped markets that stopped updating** — e.g. FanDuel `manufacturers.json` /
  `teams.json` whose `scraped_at` lags `odds.json` by many hours means FanDuel pulled
  that market (common on race day); delete the stale file (the scraper recreates it if
  the market returns). Compare each auto file's timestamp to the freshest one.
- **Concluded/settled support races** — once a support race (e.g. the Truck race) has
  run, drop its hand books; its Kalshi data settles on its own.
Sanity-check timestamps (`captured_at` / `scraped_at`) against the current race day and
against the freshest sibling file before publishing; flag or drop anything that lags.

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
  **STALE-SNAPSHOT GOTCHA (read before any EV run):** `ev_model.py`/`trades.py`
  read the **working-tree** `data/cup/**` files. CI commits fresh scrapes to the
  **deploy branch**, NOT to the dev branch, so the dev working copy goes stale
  (can be days old) and silently poisons every EV/trade number. Before running
  analysis, pull the live snapshots from deploy, e.g.
  `git fetch origin claude/nascar-page-scraper-mwi55a` then read the tier
  `snapshot.json` / `alerts.jsonl` from that ref (or point the script at a temp
  dir populated from it). Sanity-check a known driver's tier % against the live
  site before trusting the output.
- **`trades.py`** — biggest Kalshi trades from `alerts.jsonl`, splitting directional
  YES/NO from the field-lay harvest. `python trades.py [--hours N | --date YYYY-MM-DD]`.
- **`gen_stages.py` / `stages.py`** — hand-entered **stage/pole** markets (Stage 1,
  Stage 2, pole "which driver wins"). Kalshi doesn't list these, so there's **no fair
  anchor** — it's a **book-vs-book** view only. `gen_stages.write_stages("<book>.json",
  "<Book>", {"pole": rows, "stage1": rows, "stage2": rows})` writes
  `data/cup/stages/<book>.json` (de-vigged, 1 winner; reuses `gen_books` canon; not
  read by the dashboard). `python stages.py [pole|stage1|stage2|all]` lines the books
  up per driver with a consensus + deviation and flags soft lines. Stage 1 is largely a
  track-position market (anchor to pole/grid, not the win market); Stage 2 adds pit
  strategy; both carry heavy vig (~180%) so only relative/book-vs-book value matters.

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
- **Trade odds are reported NET OF KALSHI FEES.** Recorded trade `price_cents` are
  raw (pre-fee). When summarizing aggregated Kalshi trades, convert each execution
  price to American odds on the **fee-inclusive** effective price
  `p_net = p + 0.07·p·(1−p)` (Kalshi's fee ≈ `ceil(0.07·C·p·(1−p))`), NOT the raw
  price — e.g. $300 of Gibbs bought at 6¢ shows as **+1464 net**, not +1567 raw.
  Use `alerts.net_american_odds(price_cents)` / `alerts.fee_usd(count, price_cents)`.
  Fees are an estimate (standard 0.07 schedule; exact rate can vary by market).

## Standard task prompts

- "New race week. Cup is <RACE>, Xfinity is <RACE>, Trucks is <RACE>. Update the
  SERIES matchers in `scraper.py`, clear all stale lines, grab fresh Kalshi +
  FanDuel, deploy, and confirm." (start-of-week kickoff — see top of file)
- "<Book> <tier(s)>: <paste / screenshots / screen-recording>." (stage to dev;
  hold deploy for the batch — see 'Entering a hand-entered book')
- "Deploy" / "go live" / "that's all" — land the staged batch + refresh FanDuel + Kalshi.
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
