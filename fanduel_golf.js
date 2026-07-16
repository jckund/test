#!/usr/bin/env node
/*
 * Scrape FanDuel's golf markets (outright winner + Top 5/10/20 finish) for the
 * tournament(s) tracked by golf_scraper.py, so they can be compared against the
 * Kalshi prices in the golf dashboard.
 *
 * Like the NASCAR FanDuel scraper, FanDuel has no public API and sits behind
 * bot protection, so we drive headless Chromium (Playwright) to the public golf
 * page and read the app's own `content-managed-page` / `getMarketPrices` JSON
 * response bodies. Runs only on a GitHub Actions runner (the Claude session's
 * egress proxy blocks sportsbooks).
 *
 * Output (per tournament): data/<key>/fanduel/odds.json — odds per tier,
 * normalized to raw implied win probability and a no-vig probability (raw scaled
 * to the tier's number-of-winners), keyed so the page matches players to Kalshi
 * by name. Same shape as the NASCAR scraper's odds.json so the dashboard's
 * comparison engine is reused unchanged.
 *
 * FanDuel golf market naming isn't documented, so this logs every captured
 * market name and matches tiers/tournament flexibly; refine the label lists
 * below from the CI logs if a market is missed.
 */

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const GOLF_URL = "https://nj.sportsbook.fanduel.com/golf";

// FanDuel finish-market labels -> our tier key (matches Kalshi's tier keys) and
// the number of players that "win" the market. Names vary ("Top 5 Finish",
// "Top 5 Finish (Incl. Ties)", …) so we match by substring, case-insensitive.
// The outright winner market has many aliases across cards.
const TIER_DEFS = [
  { key: "winner", winners: 1,
    labels: ["outright winner", "tournament winner", "winner (incl", "to win", "outright betting", "winner"] },
  { key: "top5", winners: 5, labels: ["top 5 finish", "top 5", "top-5"] },
  { key: "top10", winners: 10, labels: ["top 10 finish", "top 10", "top-10"] },
  { key: "top20", winners: 20, labels: ["top 20 finish", "top 20", "top-20"] },
];

const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

// American odds -> implied probability (0..1). Handles + and - integers.
function impliedProb(american) {
  if (typeof american !== "number" || american === 0) return null;
  return american > 0 ? 100 / (american + 100) : -american / (-american + 100);
}

// Read the tournaments the Kalshi golf scraper published (data/golf.json). Each
// tournament's title comes from its own data/<key>/index.json when present.
function readGolf() {
  let list = [];
  try {
    list = (JSON.parse(fs.readFileSync(path.join("data", "golf.json"), "utf8")).series) || [];
  } catch {
    return [];
  }
  return list.map((s) => {
    let title = s.race_title || "";
    try {
      title = JSON.parse(fs.readFileSync(path.join("data", s.key, "index.json"), "utf8")).race_title || title;
    } catch { /* keep golf.json value */ }
    return { key: s.key, label: s.label, race_title: title };
  });
}

// Does a market name look like a finish market for one of our tiers? Returns
// { key, winners } or null. We deliberately test the more specific tiers (top20)
// before the generic "winner" so "Top 20 Finish" isn't mis-read as a winner.
function matchTier(name) {
  const n = (name || "").toLowerCase();
  const ordered = [...TIER_DEFS].reverse(); // top20, top10, top5, winner
  for (const def of ordered) {
    if (def.labels.some((l) => n.includes(l))) return { key: def.key, winners: def.winners };
  }
  return null;
}

// Count how many tournament-title tokens (>=4 chars) appear in a market/event
// name — used to attribute a market to the right tournament when several are on
// the page. "The Open Championship" -> tokens ["open","championship"].
function titleScore(title, hay) {
  const toks = (title || "").toLowerCase().split(/[^a-z0-9]+/).filter((t) => t.length >= 4);
  const h = (hay || "").toLowerCase();
  return toks.reduce((a, t) => a + (h.includes(t) ? 1 : 0), 0);
}

function runnerAmerican(r) {
  return r.winRunnerOdds && r.winRunnerOdds.americanDisplayOdds
    ? r.winRunnerOdds.americanDisplayOdds.americanOdds
    : null;
}

async function main() {
  const tournaments = readGolf();
  console.log("Tournaments to match:", tournaments.map((t) => `${t.key}:${t.race_title}`).join(", ") || "(none)");
  if (!tournaments.length) { console.log("No data/golf.json yet; nothing to scrape."); return; }

  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    locale: "en-US",
    timezoneId: "America/New_York",
  });
  const page = await ctx.newPage();

  const events = {};
  const markets = {};
  page.on("response", async (r) => {
    if (!/content-managed-page|getMarketPrices/.test(r.url())) return;
    try {
      const att = (await r.json()).attachments || {};
      Object.assign(events, att.events || {});
      Object.assign(markets, att.markets || {});
    } catch { /* non-JSON or consumed body; ignore */ }
  });

  await page.goto(GOLF_URL, { waitUntil: "networkidle", timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(7000);
  await browser.close();

  const nMarkets = Object.keys(markets).length;
  console.log(`captured events=${Object.keys(events).length} markets=${nMarkets}`);
  if (!nMarkets) throw new Error("No FanDuel markets captured (page structure changed or blocked).");

  // Candidate finish markets, each tagged with the event name it belongs to (for
  // tournament attribution). Log them all so labels can be refined from CI logs.
  const candidates = [];
  for (const m of Object.values(markets)) {
    const hit = matchTier(m.marketName || "");
    if (!hit) continue;
    const evName = (events[m.eventId] && (events[m.eventId].name || events[m.eventId].eventName)) || "";
    candidates.push({ m, key: hit.key, winners: hit.winners, evName });
  }
  console.log("Candidate finish markets:");
  for (const c of candidates) console.log(`  [${c.key}] "${c.m.marketName}"  (event: "${c.evName}", runners: ${(c.m.runners || []).length})`);
  if (!candidates.length) throw new Error("No golf finish markets matched (see captured market names above).");

  for (const t of tournaments) emitTournament(t, candidates);
}

// Write one tournament's FanDuel odds under data/<key>/fanduel/odds.json.
function emitTournament(t, candidates) {
  const outDir = path.join("data", t.key, "fanduel");
  // Attribute each candidate to this tournament by title-token overlap against
  // the market name or its event name. Keep the best-scoring market per tier.
  const best = {}; // tierKey -> { m, winners, score }
  for (const c of candidates) {
    const score = Math.max(titleScore(t.race_title, c.m.marketName), titleScore(t.race_title, c.evName));
    if (score === 0) continue; // doesn't reference this tournament
    const runners = (c.m.runners || []).length;
    const prev = best[c.key];
    // Prefer the market with the strongest title match, then the most runners
    // (the real field market rather than a small special).
    if (!prev || score > prev.score || (score === prev.score && runners > (prev.m.runners || []).length)) {
      best[c.key] = { m: c.m, winners: c.winners, score };
    }
  }

  const tierKeys = Object.keys(best);
  if (!tierKeys.length) {
    console.log(`[${t.key}] no FanDuel markets reference "${t.race_title}"; skipping.`);
    return;
  }

  const tiers = {};
  for (const [tierKey, sel] of Object.entries(best)) {
    const m = sel.m;
    const players = [];
    for (const r of m.runners || []) {
      if (r.runnerStatus && r.runnerStatus !== "ACTIVE") continue;
      const american = runnerAmerican(r);
      const implied = impliedProb(american);
      if (implied == null) continue;
      players.push({ name: r.runnerName, american, implied });
    }
    if (!players.length) continue;
    // No-vig: scale raw implied so the field sums to the number of winners.
    const sum = players.reduce((a, d) => a + d.implied, 0);
    for (const d of players) d.novig = sum > 0 ? (d.implied * sel.winners) / sum : null;
    players.sort((a, b) => b.implied - a.implied);
    tiers[tierKey] = { market_name: m.marketName, number_of_winners: sel.winners, drivers: players };
    console.log(`[${t.key}] ${tierKey}: ${players.length} players (${m.marketName})`);
  }

  if (!Object.keys(tiers).length) {
    console.log(`[${t.key}] matched markets had no active runners; skipping.`);
    return;
  }

  const out = {
    scraped_at: new Date().toISOString(),
    source: "FanDuel",
    source_url: GOLF_URL,
    race: t.race_title,
    kalshi_race: t.race_title,
    tiers,
  };
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "odds.json"), JSON.stringify(out, null, 2) + "\n");
  console.log(`[${t.key}] wrote ${path.join(outDir, "odds.json")}`);
}

main().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
